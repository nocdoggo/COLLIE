"""Snapshot openFDA's drug-shortage records (public domain, CC0; https://open.fda.gov/license/).

Each run writes ``external_data/openfda/fda_shortages_<YYYY-MM-DD>.json`` (git-ignored): the full
result list, in API order.
Repeated snapshots give realised recoveries for notices that state an expected one.

Usage::

    uv run python -m analysis.coling.fetch_fda [--out-dir external_data/openfda]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

URL = "https://api.fda.gov/drug/shortages.json?limit={limit}&skip={skip}"
PAGE = 1000


def fetch() -> list[dict]:
    rows: list[dict] = []
    while True:
        req = urllib.request.Request(
            URL.format(limit=PAGE, skip=len(rows)),
            headers={"User-Agent": "collie-research-fetch/0.1 (academic research; polite, cached)"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
        rows += payload["results"]
        if len(rows) >= payload["meta"]["results"]["total"] or not payload["results"]:
            return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.fetch_fda")
    ap.add_argument("--out-dir", type=Path, default=Path("external_data/openfda"))
    args = ap.parse_args(argv)
    rows = fetch()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"fda_shortages_{dt.date.today().isoformat()}.json"
    path.write_text(json.dumps(rows, sort_keys=True) + "\n")
    print(f"{len(rows)} records -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
