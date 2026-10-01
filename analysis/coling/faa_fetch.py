"""Collect FAA Command Center (ATCSCC) advisories from the public advisory database.

The database at ``www.fly.faa.gov/adv/`` (a US federal government work) serves one list page per
UTC day and one page per advisory:

- list: ``/adv/adv_list?whichAdvisories=ATCSCC&advisoryCategory=All&date=YYYY-MM-DD&...``
- advisory: ``/adv/adv_otherdis?adv_date=MMDDYYYY&advn=N``

This collector walks a range of days, saves the list page, then every advisory the list links to,
as served, under ``<out>/<yyyymmdd>/list.html`` and ``<out>/<yyyymmdd>/adv_<nnn>.html``. It reads
nothing from a list page except the advisory numbers.

Politeness: one neutral User-Agent with no personal details, no cookies, no redirects followed,
at least ``--delay`` seconds (never less than one) between the end of one request and the start
of the next, exponential backoff on errors, and a stop after repeated failures. A file on disk is
never fetched again, so a rerun resumes where the last run stopped. Every request is logged, and
``manifest.csv`` (file, bytes, sha256) is rewritten from the files on disk when a run ends.

``www.fly.faa.gov/robots.txt`` does not exist: on 1 October 2026 it answered 302 to ``/fly/``,
which answered 302 to the status home page on another host. With no robots file there is no rule
to apply; the collector still checks at start and stops if a real robots file appears that
disallows ``/adv/``.

Usage::

    uv run python -m analysis.coling.faa_fetch --start 2026-04-01 --end 2026-04-30
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path

HOST = "https://www.fly.faa.gov"
ROBOTS_URL = HOST + "/robots.txt"
LIST_URL = (
    HOST + "/adv/adv_list?whichAdvisories=ATCSCC&advisoryCategory=All&date={iso}"
    "&airflow=true&_airflow=on&ctop=true&_ctop=on&gStop=true&_gStop=on"
    "&gDelay=true&_gDelay=on&route=true&_route=on&other=true&_other=on"
)
ADV_URL = HOST + "/adv/adv_otherdis?adv_date={mmddyyyy}&advn={number}"
USER_AGENT = "collie-research-fetch/0.1 (academic research; polite, cached)"
MIN_DELAY = 1.0
BACKOFF = (5.0, 20.0, 80.0, 320.0)  # seconds before each retry of one item
MAX_CONSECUTIVE_FAILED = 3  # items that failed after every retry, in a row
MAX_TOTAL_FAILED = 15

ADV_LINK = re.compile(r"adv_otherdis\?adv_date=(\d{8})&(?:amp;)?advn=(\d+)")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect, so no request leaves the advisory database's host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl}", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class StopFetching(RuntimeError):
    """Raised when the collector must stop: too many failures, or robots disallows."""


class Fetcher:
    """One polite client: rate limit, retries with backoff, and a request log."""

    def __init__(self, delay: float, log_path: Path, sleep=time.sleep, opener=_OPENER):
        self.delay = max(float(delay), MIN_DELAY)
        self.log_path = log_path
        self.sleep = sleep
        self.opener = opener
        self.last_end = 0.0
        self.requests = 0
        self.failed_in_a_row = 0
        self.failed_total = 0
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{stamp} {message}"
        with self.log_path.open("a") as f:
            f.write(line + "\n")
        print(line, flush=True)

    def _once(self, url: str) -> tuple[int, bytes]:
        wait = self.delay - (time.monotonic() - self.last_end)
        if wait > 0:
            self.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        self.requests += 1
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.status, response.read()
        finally:
            self.last_end = time.monotonic()

    def get(self, url: str, must_contain: bytes) -> bytes | None:
        """Body of ``url`` if it arrives with status 200 and contains ``must_contain``.

        Retries with exponential backoff. Returns None when every try failed; raises
        StopFetching after too many failed items.
        """
        for attempt in range(len(BACKOFF) + 1):
            try:
                status, body = self._once(url)
                if status == 200 and must_contain in body:
                    self.failed_in_a_row = 0
                    return body
                problem = f"status {status}, {len(body)} bytes, expected marker missing"
            except urllib.error.HTTPError as error:
                problem = f"HTTP {error.code} {error.reason}"
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                problem = f"{type(error).__name__}: {error}"
            if attempt < len(BACKOFF):
                self.log(f"RETRY {url} ({problem}); waiting {BACKOFF[attempt]:.0f}s")
                self.sleep(BACKOFF[attempt])
            else:
                self.log(f"FAILED {url} ({problem})")
        self.failed_in_a_row += 1
        self.failed_total += 1
        if self.failed_in_a_row >= MAX_CONSECUTIVE_FAILED or self.failed_total >= MAX_TOTAL_FAILED:
            raise StopFetching(
                f"{self.failed_in_a_row} items failed in a row, {self.failed_total} in this run"
            )
        return None


def check_robots(fetcher: Fetcher) -> str:
    """Fetch robots.txt once and say what it allows; raise StopFetching if /adv/ is disallowed.

    A redirect, an error status or a page that is not a robots file all mean that the host
    publishes no robots rules.
    """
    wait = fetcher.delay - (time.monotonic() - fetcher.last_end)
    if wait > 0:
        fetcher.sleep(wait)
    request = urllib.request.Request(ROBOTS_URL, headers={"User-Agent": USER_AGENT})
    fetcher.requests += 1
    try:
        with fetcher.opener.open(request, timeout=60) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise StopFetching(f"robots.txt answered {error.code}; treated as disallow") from error
        return f"no robots file (HTTP {error.code} {error.reason})"
    finally:
        fetcher.last_end = time.monotonic()
    text = body.decode("utf-8", "replace")
    if status != 200 or not re.search(r"(?im)^\s*(user-agent|disallow|allow)\s*:", text):
        return f"no robots file (status {status}, not a robots document)"
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(text.splitlines())
    for url in (LIST_URL.format(iso="2026-04-01"), ADV_URL.format(mmddyyyy="04012026", number=1)):
        if not parser.can_fetch(USER_AGENT, url):
            raise StopFetching(f"robots.txt disallows {url}")
    return "robots file found; /adv/ pages allowed"


def advisory_numbers(list_html: bytes, day: dt.date) -> list[int]:
    """Advisory numbers linked from one day's list page, ascending, without duplicates."""
    want = day.strftime("%m%d%Y")
    found = {
        int(number)
        for date, number in ADV_LINK.findall(list_html.decode("latin-1"))
        if date == want
    }
    return sorted(found)


def _write_atomic(path: Path, body: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(body)
    tmp.replace(path)


def fetch_day(fetcher: Fetcher, out: Path, day: dt.date) -> tuple[int, int]:
    """Fetch one day's list and advisories. Returns (advisories listed, files newly fetched)."""
    folder = out / day.strftime("%Y%m%d")
    folder.mkdir(parents=True, exist_ok=True)
    list_path = folder / "list.html"
    fetched = 0
    if list_path.exists():
        list_html = list_path.read_bytes()
    else:
        marker = f"ADVISORIES FOR {day.isoformat()}".encode()
        url = LIST_URL.format(iso=day.isoformat())
        list_html = fetcher.get(url, marker)
        if list_html is None:
            return 0, 0
        _write_atomic(list_path, list_html)
        fetcher.log(f"OK {url} {len(list_html)} bytes -> {list_path}")
        fetched += 1
    numbers = advisory_numbers(list_html, day)
    for number in numbers:
        path = folder / f"adv_{number:03d}.html"
        if path.exists():
            continue
        url = ADV_URL.format(mmddyyyy=day.strftime("%m%d%Y"), number=number)
        body = fetcher.get(url, b"ADVZY")
        if body is None:
            continue
        _write_atomic(path, body)
        fetcher.log(f"OK {url} {len(body)} bytes -> {path}")
        fetched += 1
    missing = sum(not (folder / f"adv_{n:03d}.html").exists() for n in numbers)
    fetcher.log(f"DAY {day.isoformat()} listed {len(numbers)} fetched {fetched} missing {missing}")
    return len(numbers), fetched


def write_manifest(out: Path) -> int:
    """Rewrite ``manifest.csv`` (file, bytes, sha256) from every saved page under ``out``."""
    rows = []
    for path in sorted(out.glob("*/*.html")):
        body = path.read_bytes()
        rows.append((str(path.relative_to(out)), len(body), hashlib.sha256(body).hexdigest()))
    tmp = out / "manifest.csv.part"
    with tmp.open("w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(("file", "bytes", "sha256"))
        writer.writerows(rows)
    tmp.replace(out / "manifest.csv")
    return len(rows)


def days_between(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.faa_fetch")
    ap.add_argument("--start", type=dt.date.fromisoformat, required=True)
    ap.add_argument("--end", type=dt.date.fromisoformat, required=True)
    ap.add_argument("--out", type=Path, default=Path("external_data/faa_atcscc/2026"))
    ap.add_argument("--log", type=Path, default=Path("results/coling/faa/fetch.log"))
    ap.add_argument("--delay", type=float, default=MIN_DELAY, help="seconds; at least 1")
    ap.add_argument("--manifest-only", action="store_true", help="rewrite the manifest and exit")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.manifest_only:
        print(f"manifest: {write_manifest(args.out)} files -> {args.out / 'manifest.csv'}")
        return 0
    today = dt.datetime.now(dt.UTC).date()
    if args.end >= today:
        ap.error(f"--end must be a finished UTC day (before {today.isoformat()})")
    fetcher = Fetcher(args.delay, args.log)
    with (args.out / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another collector is running on this folder; not starting", file=sys.stderr)
            return 2
        fetcher.log(f"START {args.start} to {args.end}, delay {fetcher.delay:.1f}s -> {args.out}")
        status = 0
        try:
            fetcher.log(f"ROBOTS {ROBOTS_URL}: {check_robots(fetcher)}")
            for day in days_between(args.start, args.end):
                fetch_day(fetcher, args.out, day)
        except StopFetching as stop:
            fetcher.log(f"STOP {stop}")
            status = 1
        files = write_manifest(args.out)
        fetcher.log(f"END requests {fetcher.requests}, files on disk {files}, status {status}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
