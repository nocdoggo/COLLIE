"""Two-rater audit CLI: emit the scoring sheet, then report agreement and pruning.

``--prepare`` writes an empty sheet (stdout by default, so preparing never touches the tree
unless asked). ``--report`` reads the completed sheet, validates it against the current bank,
and prints per-criterion Cohen's kappa, the leakage removal log, and the audit status. It
exits nonzero unless the audit is complete, clean, and team-confirmed, so a blank or stale
sheet can never masquerade as a finished audit.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from collie.data.alerts.audit import (
    SHEET_COLUMNS,
    audit_ratings,
    default_audit_config,
    rating_sheet_rows,
    read_ratings,
    review_samples,
    write_rating_sheet,
)
from collie.data.alerts.bank import load_alert_bank
from tools.build_alert_bank import review_sample

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RATINGS = ROOT / "reports" / "alert_audit_ratings.csv"


def _samples(templates_dir: Path, config: dict):
    bank = load_alert_bank(templates_dir)
    selected = review_sample(bank, config["render_sample_size"])
    return review_samples(bank, selected, config["render_seed"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="emit an empty scoring sheet")
    mode.add_argument("--report", action="store_true", help="score a completed sheet")
    parser.add_argument(
        "--ratings",
        type=Path,
        help=f"sheet path (report default: {DEFAULT_RATINGS.relative_to(ROOT)}; "
        "prepare default: stdout)",
    )
    parser.add_argument("--templates", type=Path, default=ROOT / "collie/data/alerts/templates")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="report: assert the team has confirmed these are the final human ratings",
    )
    args = parser.parse_args(argv)
    config = default_audit_config()
    try:
        samples = _samples(args.templates, config)
        if args.prepare:
            if args.ratings is None:
                writer = csv.DictWriter(sys.stdout, fieldnames=list(SHEET_COLUMNS))
                writer.writeheader()
                writer.writerows(rating_sheet_rows(samples, config["raters"]))
            else:
                write_rating_sheet(args.ratings, samples, config["raters"])
                print(f"rating sheet written: {args.ratings} ({len(samples)} samples)")
            return 0
        ratings_path = args.ratings if args.ratings is not None else DEFAULT_RATINGS
        if not ratings_path.is_file():
            print(f"human ratings missing: {ratings_path}")
            return 2
        ratings = read_ratings(ratings_path, samples)
        if args.confirm:
            config["status"] = "confirmed"
        result = audit_ratings(samples, ratings, config)
        _print_report(result)
        return 0 if result["status"] == "ready" else 2
    except (ValueError, FileExistsError, OSError) as exc:
        print(f"AUDIT FAILED: {exc}", file=sys.stderr)
        return 2


def _print_report(result: dict) -> None:
    print("Per-criterion Cohen's kappa:")
    for criterion, value in result["kappa"].items():
        print(f"  {criterion}: {'undefined (degenerate)' if value is None else f'{value:.3f}'}")
    print(f"Leakage removals: {len(result['removals'])}")
    for removal in result["removals"]:
        print(
            f"  {removal['template_id']} ({removal['sample_id']}, {removal['rater']}): "
            f"{removal['reason']}"
        )
    print(f"Adjudicated disagreements: {len(result['adjudication_log'])}")
    print(f"Retained templates: {len(result['retained_template_ids'])}")
    if result["fallback_required"]:
        print(
            "Low agreement: bank shrinks to "
            f"{len(result['retained_template_ids'])} templates; "
            "a dated prereg deviation is required."
        )
    print(f"Audit status: {result['status']}")


if __name__ == "__main__":
    raise SystemExit(main())
