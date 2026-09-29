"""Fetch every Wayback Machine capture of the FDA's consolidated drug-shortage CSV.

The FDA's table (a US federal government work) is served at
``accessdata.fda.gov/scripts/drugshortages/Drugshortages.cfm`` as ``text/csv``; the Internet
Archive holds captures from October 2019. This lists the captures through the CDX API and
downloads each raw capture (``id_`` URLs), politely: a neutral User-Agent with no personal
details, one request every ``--delay`` seconds, and a local cache so reruns fetch only what is
missing. Raw files go to the git-ignored ``external_data/``; the repository keeps derived tables.

Usage::

    uv run python -m analysis.coling.fetch_wayback_csv [--out external_data/fda_wayback_csv] [--delay 6]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

TARGET = "accessdata.fda.gov/scripts/drugshortages/Drugshortages.cfm"
CDX = "https://web.archive.org/cdx/search/cdx?" + urllib.parse.urlencode(
    {
        "url": TARGET,
        "output": "json",
        "filter": "mimetype:text/csv",
        "fl": "timestamp,statuscode,digest,length",
    }
)
RAW = "https://web.archive.org/web/{ts}id_/https://" + TARGET
USER_AGENT = "collie-research-fetch/0.1 (academic research; polite, cached)"


def get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.fetch_wayback_csv")
    ap.add_argument("--out", type=Path, default=Path("external_data/fda_wayback_csv"))
    ap.add_argument("--delay", type=float, default=6.0)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = json.loads(get(CDX))
    captures = [dict(zip(rows[0], r, strict=True)) for r in rows[1:]]
    captures = [c for c in captures if c["statuscode"] == "200"]
    (args.out / "cdx.json").write_text(json.dumps(captures, indent=1) + "\n")
    seen: set[str] = set()
    fetched = 0
    for c in captures:
        path = args.out / f"{c['timestamp']}.csv"
        if c["digest"] in seen or path.exists():
            seen.add(c["digest"])
            continue
        seen.add(c["digest"])
        time.sleep(args.delay)
        try:
            path.write_bytes(get(RAW.format(ts=c["timestamp"])))
            fetched += 1
        except Exception as error:  # log and continue; a rerun retries
            print(f"{c['timestamp']}: {error}", flush=True)
    print(f"{len(captures)} captures listed, {len(seen)} distinct, {fetched} fetched -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
