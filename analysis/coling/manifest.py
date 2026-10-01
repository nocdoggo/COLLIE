"""Capture manifest: the exact set of capture files the corpus is built from.

``corpus.capture_files`` takes every ``<14-digit timestamp>.csv`` in the capture folder, so one
file more or less changes event ids, counts and the hash of the sealed outcome file. This module
fixes the set. It writes ``analysis/coling/out/capture_manifest.csv``, one row per capture file,
sorted by name:

* ``file``: the file name;
* ``timestamp``: the Internet Archive's capture time (UTC, ``YYYYMMDDhhmmss``), which with the
  target URL identifies the capture (``web.archive.org/web/<timestamp>id_/<url>``);
* ``bytes``: the file's size;
* ``sha256``: the hash of the file's bytes.

The manifest is plain CSV with ``\\n`` line ends and nothing else, so its own sha256 (printed, and
recorded in the registration) changes exactly when a file is added, removed or altered.

Report. Besides the manifest's sha256 the script prints the number of captures and of distinct
capture days (UTC), the first and last capture, captures and capture days per year, days with
more than one capture, gaps between capture days of more than 60 days (as ``corpus.gap_summary``
reports them) and the files that ``corpus.read_capture`` rejects (the corpus skips those).

Index. ``fetch_wayback_csv.py`` leaves ``cdx.json`` in the capture folder: the captures the
archive's index listed with status 200 and type text/csv when the fetch ran, each with the
archive's digest of the content (base32 of its SHA-1). The report checks every file against its
digest and lists the indexed captures that have no file, with the reason:

* ``repeat``: the content is that of the indexed captures just before it, back to one that has a
  file (the fetcher stores each distinct content once), so the corpus sees the same table at
  that point. The line says whether the repeat falls on the same day as the file it repeats or
  on a later day, and whether that day has no capture in the manifest;
* ``return``: the content is that of an earlier file, with different content in between. The
  table went back to an earlier state that the corpus does not see, so the capture should be
  fetched;
* ``not_fetched``: no file holds this content.

The index is not part of the manifest: it grows as the archive adds captures, and the capture
set does not.

Check. ``compare(directory)`` returns the differences between a folder and the manifest (files
missing, files not listed, content changed, a manifest that is missing or malformed), empty when
they agree. ``verify(directory)`` is the same check for a caller that must not go on with another
capture set, the corpus builder first of all: it returns the empty list when the folder is the
manifest's capture set and raises ``CaptureSetError`` (a ``SystemExit`` that lists the
differences) when it is not, so a caller that ignores the result still stops.
``verify(directory, refuse=False)`` returns the list instead.

Writing again. On the same folder the script writes the same bytes. When it replaces a manifest
with other content it says so and lists what changed; the registered manifest is the one whose
sha256 is in the registration, and ``--check --pin <sha256 prefix>`` tests for exactly that one.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.manifest [--captures external_data/fda_wayback_csv]
        [--out analysis/coling/out/capture_manifest.csv]
    PYTHONPATH=. python -m analysis.coling.manifest --check [--pin <sha256 prefix>]

The second form compares the folder with the manifest and writes nothing; it exits with status 1
on any difference.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from analysis.coling import corpus

CAPTURES = Path("external_data/fda_wayback_csv")
MANIFEST = Path("analysis/coling/out/capture_manifest.csv")
INDEX_NAME = "cdx.json"
FIELDS = ("file", "timestamp", "bytes", "sha256")
LONG_GAP_DAYS = 60  # as in corpus.gap_summary
SHORT = 16  # hash prefix length used in the registration record
MAX_SHOWN = 20  # differences listed in a CaptureSetError message

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def capture_rows(directory: Path) -> list[dict[str, str]]:
    """One manifest row per file that ``corpus.capture_files`` returns, sorted by name."""
    rows = []
    for path in sorted(corpus.capture_files(directory), key=lambda p: p.name):
        raw = path.read_bytes()
        rows.append(
            {
                "file": path.name,
                "timestamp": path.stem,
                "bytes": str(len(raw)),
                "sha256": sha256_hex(raw),
            }
        )
    return rows


def manifest_text(rows: Iterable[dict[str, str]]) -> str:
    """The manifest as CSV text: a header line and one line per row, ``\\n`` line ends."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_manifest(rows: Iterable[dict[str, str]], path: Path) -> str:
    """Write the manifest and return the sha256 of its content."""
    data = manifest_text(rows).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_hex(data)


def read_manifest(path: Path) -> list[dict[str, str]]:
    """The manifest's rows; ``ValueError`` when the file is not ASCII text with its four columns."""
    with path.open(newline="", encoding="ascii") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"{path}: not a capture manifest (columns {reader.fieldnames})")
        rows = list(reader)
    for number, row in enumerate(rows, start=1):
        if None in row or None in row.values():  # more or fewer cells than columns
            raise ValueError(f"{path}: row {number} does not have {len(FIELDS)} cells")
    return rows


def differences(expected: Iterable[dict[str, str]], found: Iterable[dict[str, str]]) -> list[str]:
    """Compare two sets of manifest rows by file name; one line per file that differs."""
    expected, found = list(expected), list(found)
    want = {row["file"]: row for row in expected}
    have = {row["file"]: row for row in found}
    listed = Counter(row["file"] for row in expected)
    out = [
        f"{name}: listed {n} times in the manifest" for name, n in sorted(listed.items()) if n > 1
    ]
    for name in sorted(want.keys() | have.keys()):
        a, b = want.get(name), have.get(name)
        if b is None:
            out.append(f"{name}: in the manifest, not in the folder")
        elif a is None:
            out.append(f"{name}: in the folder, not in the manifest")
        elif (a["bytes"], a["sha256"]) != (b["bytes"], b["sha256"]):
            out.append(
                f"{name}: content differs (manifest {a['bytes']} bytes, sha256 "
                f"{a['sha256'][:SHORT]}; folder {b['bytes']} bytes, sha256 {b['sha256'][:SHORT]})"
            )
    return out


def compare(directory: Path, manifest: Path = MANIFEST, pin: str = "") -> list[str]:
    """Differences between the capture files in ``directory`` and the manifest; empty when equal.

    ``pin``, when given, is a prefix of the manifest's registered sha256; a manifest with another
    hash is reported as a difference too, so a regenerated manifest cannot pass for the
    registered one.
    """
    directory, manifest = Path(directory), Path(manifest)
    if not manifest.is_file():
        return [f"{manifest}: no manifest"]
    try:
        expected = read_manifest(manifest)
    except UnicodeDecodeError:
        return [f"{manifest}: not a capture manifest (not ASCII text)"]
    except ValueError as error:
        return [str(error)]
    out = []
    digest = sha256_hex(manifest.read_bytes())
    if pin and not digest.startswith(pin.lower()):
        out.append(f"{manifest}: sha256 {digest[: max(SHORT, len(pin))]} does not start with {pin}")
    return out + differences(expected, capture_rows(directory))


class CaptureSetError(SystemExit):
    """The capture folder is not the manifest's capture set; ``differences`` holds every line."""

    def __init__(self, directory: Path, manifest: Path, differences: Sequence[str]) -> None:
        self.differences = list(differences)
        lines = [
            f"{directory}: not the capture set of {manifest} ({len(self.differences)} differences)",
            *(f"  {line}" for line in self.differences[:MAX_SHOWN]),
        ]
        if len(self.differences) > MAX_SHOWN:
            lines.append(f"  ... and {len(self.differences) - MAX_SHOWN} more")
        super().__init__("\n".join(lines))


def verify(
    directory: Path, manifest: Path = MANIFEST, pin: str = "", refuse: bool = True
) -> list[str]:
    """Check ``directory`` against the manifest and refuse a capture set that differs from it.

    Returns the differences as ``compare`` lists them, which is the empty list when the folder
    is the manifest's capture set. With ``refuse`` (the default) any difference raises
    ``CaptureSetError`` instead, so that a build stops whatever its caller does with the result;
    ``refuse=False`` returns the list.
    """
    found = compare(directory, manifest, pin)
    if found and refuse:
        raise CaptureSetError(Path(directory), Path(manifest), found)
    return found


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def capture_time(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d%H%M%S")


def capture_day(stamp: str) -> date:
    return capture_time(stamp).date()


def long_gaps(stamps: Iterable[str], over: int = LONG_GAP_DAYS) -> list[str]:
    """Gaps between consecutive capture days of more than ``over`` days."""
    days = sorted({capture_day(s) for s in stamps})
    return [f"{a}..{b} ({(b - a).days} d)" for a, b in pairwise(days) if (b - a).days > over]


def coverage(stamps: Iterable[str]) -> dict[str, Any]:
    """Counts of captures and capture days (UTC), overall and per year, and the long gaps."""
    stamps = sorted(stamps)
    per_day = Counter(capture_day(s) for s in stamps)
    return {
        "captures": len(stamps),
        "capture_days": len(per_day),
        "first": stamps[0] if stamps else "",
        "last": stamps[-1] if stamps else "",
        "captures_per_year": dict(sorted(Counter(s[:4] for s in stamps).items())),
        "days_per_year": dict(sorted(Counter(str(d.year) for d in per_day).items())),
        "days_with_several_captures": {str(d): n for d, n in sorted(per_day.items()) if n > 1},
        "long_gaps": long_gaps(stamps),
    }


def rejected_by_parser(directory: Path) -> list[str]:
    """Capture files that ``corpus.read_capture`` refuses, which the corpus builder skips."""
    out = []
    for path in corpus.capture_files(directory):
        try:
            corpus.read_capture(path)
        except corpus.CaptureFormatError as error:
            out.append(str(error))
    return out


# ---------------------------------------------------------------------------
# The archive's index
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unused:
    """An indexed capture with no file: ``kind`` is repeat, return or not_fetched."""

    timestamp: str
    kind: str
    reason: str


def archive_digest(raw: bytes) -> str:
    """The digest the archive's index gives for a payload: base32 of its SHA-1."""
    return base64.b32encode(hashlib.sha1(raw).digest()).decode("ascii")


def read_index(directory: Path) -> list[dict[str, str]]:
    """The index rows the fetcher saved, in time order; empty when there is no index file.

    ``ValueError`` when the file is not a list of rows with a timestamp and a digest.
    """
    path = directory / INDEX_NAME
    if not path.is_file():
        return []
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) and {"timestamp", "digest"} <= row.keys() for row in rows
    ):
        raise ValueError(f"{path}: not a list of captures with timestamp and digest")
    return sorted(rows, key=lambda row: row["timestamp"])


def unused_index_rows(index: Sequence[dict[str, str]], on_disk: Iterable[str]) -> list[Unused]:
    """Indexed captures with no file, each with the reason (see the module docstring).

    ``index`` is in time order; ``on_disk`` holds the timestamps of the capture files.
    """
    stamps = set(on_disk)
    days = {capture_day(s) for s in stamps}
    last = max(stamps, default="")
    out = []
    for i, row in enumerate(index):
        stamp = row["timestamp"]
        if stamp in stamps:
            continue
        same = [j for j in range(i) if index[j]["digest"] == row["digest"]]
        stored = [j for j in same if index[j]["timestamp"] in stamps]
        if not stored:
            reason = "content not on disk; "
            reason += "later than the last file" if stamp > last else "inside the covered span"
            if same:
                reason += f"; same content as {index[same[0]]['timestamp']}, which has no file"
            out.append(Unused(stamp, "not_fetched", reason))
            continue
        start = i  # first row of the run of captures with this content that ends just before
        while start > 0 and index[start - 1]["digest"] == row["digest"]:
            start -= 1
        twin = index[stored[-1]]["timestamp"]  # the nearest earlier file with this content
        day = capture_day(stamp)
        apart = (day - capture_day(twin)).days
        when = "the same day" if apart == 0 else f"{apart} day{'s' if apart > 1 else ''} later"
        uncovered = "" if day in days else f"; no capture is used for {day}"
        if stored[-1] >= start:
            reason = f"same content as {twin}, {when}, nothing different in between{uncovered}"
            out.append(Unused(stamp, "repeat", reason))
        else:
            reason = f"same content as {twin}, {when}, after different content{uncovered}"
            out.append(Unused(stamp, "return", f"{reason}; should be fetched"))
    return out


def index_check(directory: Path, index: Sequence[dict[str, str]]) -> dict[str, list[str]]:
    """Capture files against the index: not listed, digest equal, digest different."""
    digests = {row["timestamp"]: row["digest"] for row in index}
    out: dict[str, list[str]] = {"not_in_index": [], "digest_equal": [], "digest_differs": []}
    for path in corpus.capture_files(directory):
        if path.stem not in digests:
            out["not_in_index"].append(path.name)
        elif archive_digest(path.read_bytes()) == digests[path.stem]:
            out["digest_equal"].append(path.name)
        else:
            out["digest_differs"].append(path.name)
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def show_time(stamp: str) -> str:
    return f"{stamp} ({capture_time(stamp):%Y-%m-%d %H:%M:%S} UTC)" if stamp else "none"


def show_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in counts.items()) or "none"


def coverage_lines(rows: Sequence[dict[str, str]], rejected: Sequence[str]) -> list[str]:
    cov = coverage(row["timestamp"] for row in rows)
    lines = [
        f"captures: {cov['captures']} files on {cov['capture_days']} days (UTC), "
        f"{sum(int(row['bytes']) for row in rows)} bytes",
        f"first capture: {show_time(cov['first'])}",
        f"last capture: {show_time(cov['last'])}",
        f"captures per year: {show_counts(cov['captures_per_year'])}",
        f"capture days per year: {show_counts(cov['days_per_year'])}",
        f"days with more than one capture: {show_counts(cov['days_with_several_captures'])}",
        f"gaps of more than {LONG_GAP_DAYS} days: {len(cov['long_gaps'])}",
        *(f"  {gap}" for gap in cov["long_gaps"]),
        f"files the parser rejects (skipped by the corpus): {len(rejected)}",
        *(f"  {message}" for message in rejected),
    ]
    return lines


def index_lines(directory: Path, rows: Sequence[dict[str, str]]) -> list[str]:
    path = directory / INDEX_NAME
    try:
        index = read_index(directory)
    except ValueError as error:
        return [f"index: unreadable ({error}); captures without a file cannot be listed"]
    if not index:
        return [f"index: no rows in {path}; captures without a file cannot be listed"]
    cov = coverage(row["timestamp"] for row in index)
    check = index_check(directory, index)
    unused = unused_index_rows(index, (row["timestamp"] for row in rows))
    kinds = Counter(u.kind for u in unused)
    lines = [
        f"index {path}: {cov['captures']} captures on {cov['capture_days']} days, "
        f"{cov['first']} to {cov['last']}; sha256 {sha256_hex(path.read_bytes())[:SHORT]}",
        f"  indexed captures per year: {show_counts(cov['captures_per_year'])}",
        f"  indexed capture days per year: {show_counts(cov['days_per_year'])}",
        f"  files with the archive's digest: {len(check['digest_equal'])}; "
        f"with another digest: {len(check['digest_differs'])}; "
        f"not in the index: {len(check['not_in_index'])}",
        *(f"    digest differs: {name}" for name in check["digest_differs"]),
        *(f"    not in the index: {name}" for name in check["not_in_index"]),
        f"  indexed captures with no file: {len(unused)} ({show_counts(dict(sorted(kinds.items())))})",
        *(f"    {u.timestamp}  {u.kind}: {u.reason}" for u in unused),
    ]
    return lines


def changes_to(path: Path, rows: Sequence[dict[str, str]]) -> list[str]:
    """What writing ``rows`` to ``path`` changes: nothing for no file or one with the same bytes."""
    if not path.is_file():
        return []
    old = path.read_bytes()
    if old == manifest_text(rows).encode("ascii"):
        return []
    was = sha256_hex(old)[:SHORT]
    try:
        changed = differences(read_manifest(path), rows)
    except ValueError:
        return [f"REPLACED a file that was not a capture manifest (sha256 {was})"]
    if not changed:
        return [
            f"REPLACED a manifest of the same files that was written differently (sha256 {was})"
        ]
    return [
        f"REPLACED a manifest with other content (sha256 {was}); the folder against it:",
        *(f"  {line}" for line in changed),
    ]


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.manifest")
    ap.add_argument("--captures", type=Path, default=CAPTURES)
    ap.add_argument("--out", type=Path, default=MANIFEST, help="the manifest file")
    ap.add_argument(
        "--check",
        action="store_true",
        help="compare the folder with the manifest and write nothing; exit 1 when they differ",
    )
    ap.add_argument(
        "--pin",
        default="",
        help="with --check: a prefix of the registered sha256 the manifest must have",
    )
    args = ap.parse_args(None if argv is None else list(argv))
    if args.pin and not args.check:
        ap.error("--pin goes with --check")
    if args.check:
        found = compare(args.captures, args.out, args.pin)
        for line in found:
            print(line)
        if args.out.is_file():
            print(f"manifest {args.out} sha256 {sha256_hex(args.out.read_bytes())}")
        print(
            f"{args.captures}: " + (f"{len(found)} differences" if found else "as in the manifest")
        )
        return 1 if found else 0
    rows = capture_rows(args.captures)
    if not rows:
        raise SystemExit(f"no capture files in {args.captures}")
    replaced = changes_to(args.out, rows)
    digest = write_manifest(rows, args.out)
    print(f"manifest {args.out} sha256 {digest} (short {digest[:SHORT]})")
    for line in replaced:
        print(line)
    for line in coverage_lines(rows, rejected_by_parser(args.captures)):
        print(line)
    for line in index_lines(args.captures, rows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
