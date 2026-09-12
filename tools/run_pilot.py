"""Pilot runner for the frozen evaluation path.

The final pilot depends on module 06's real arm assembly.  This tool already enforces the
method-freeze/quarantine rule and provides the report shape; it intentionally refuses to fake
the missing arm engine.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from collie.eval.pilot import (
    compute_builtin_pilot_intervals,
    compute_builtin_pilot_metrics,
    evaluate_pilot,
    pilot_manifest_from_records,
    render_pilot_report,
    validate_go_intervals,
    validate_pilot_record_count,
    write_pilot_manifest,
)
from collie.eval.prereg import load_preregistration
from collie.eval.records import load_episode_results_jsonl
from tools.freeze import FREEZE_PATH, drift, load_freeze

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "reports" / "pilot_manifest.json"


def _quarantine_check(manifest_path: Path) -> None:
    frozen = load_freeze()
    if not frozen.get("complete", False):
        missing = [
            path for path, record in frozen.get("files", {}).items() if record.get("missing")
        ]
        raise SystemExit(
            "method freeze is incomplete; pilot cannot issue a formal verdict until "
            "registered files exist: " + ", ".join(missing)
        )
    changed = drift()
    if not changed:
        return
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        seeds = manifest.get("seeds", [])
        templates = manifest.get("templates", [])
        raise SystemExit(
            "method freeze changed after pilot episodes were manifest. Quarantine applies to "
            f"{len(seeds)} seeds and {len(templates)} templates in {manifest_path}."
        )
    raise SystemExit("method freeze drifted before pilot execution; repair freeze/deviations first")


def _load_int_mapping(path: Path | None) -> dict[str, int] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return {str(key): int(value) for key, value in payload.items()}


def _load_interval_mapping(path: Path) -> dict[str, tuple[float, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    intervals: dict[str, tuple[float, float]] = {}
    for key, value in payload.items():
        if not isinstance(value, list | tuple) or len(value) != 2:
            raise SystemExit(f"{path}: interval for {key!r} must be [ci_low, ci_high]")
        low, high = value
        intervals[str(key)] = (float(low), float(high))
    return intervals


def render_not_ready_report(episodes: int) -> str:
    today = dt.date.today().isoformat()
    return "\n".join(
        [
            f"# Pilot report ({today})",
            "",
            f"Requested episodes: {episodes}",
            "",
            "Status: not run.",
            "",
            "Reason: module 06 has not yet produced the real arm engine and stored "
            "EpisodeResult records. The pilot runner is wired to enforce preregistration "
            "and quarantine, but it will not fabricate pilot estimates.",
            "",
            "Decision: pending.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episodes", type=int, default=120)
    ap.add_argument("--report", type=Path, default=REPO_ROOT / "reports" / "pilot_report.md")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--records", type=Path, help="stored EpisodeResult JSONL from the pilot run")
    ap.add_argument(
        "--metrics", type=Path, help="JSON object of precomputed pilot metric estimates"
    )
    ap.add_argument(
        "--intervals",
        type=Path,
        help="JSON object mapping pilot metric id to [ci_low, ci_high]",
    )
    ap.add_argument(
        "--call-budget-per-episode",
        type=int,
        help="registered per-episode call budget for budget_overrun_rate",
    )
    ap.add_argument(
        "--shock-periods",
        type=Path,
        help="JSON object mapping episode_id to shock period for recovery_time",
    )
    args = ap.parse_args(argv)

    if not 100 <= args.episodes <= 150:
        raise SystemExit("--episodes must be between 100 and 150 for the registered pilot")
    if (args.metrics or args.intervals) and not args.records:
        raise SystemExit(
            "--metrics/--intervals may supplement stored pilot records, but cannot drive a formal "
            "pilot verdict without --records provenance"
        )
    prereg = load_preregistration(require_final=bool(args.records))

    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.records:
        _quarantine_check(args.manifest)
        metrics = {}
        intervals = {}
        results = load_episode_results_jsonl(args.records)
        validate_pilot_record_count(results)
        shock_periods = _load_int_mapping(args.shock_periods)
        metrics.update(
            compute_builtin_pilot_metrics(
                results,
                call_budget_per_episode=args.call_budget_per_episode,
                shock_periods=shock_periods,
            )
        )
        intervals.update(compute_builtin_pilot_intervals(results, shock_periods=shock_periods))
        manifest = pilot_manifest_from_records(
            results,
            requested_episodes=args.episodes,
            freeze_manifest_path=FREEZE_PATH,
            records_path=args.records,
        )
        write_pilot_manifest(args.manifest, manifest)
        if args.metrics:
            loaded = json.loads(args.metrics.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise SystemExit("--metrics must point to a JSON object")
            metrics.update({str(key): float(value) for key, value in loaded.items()})
        if args.intervals:
            intervals.update(_load_interval_mapping(args.intervals))
        validate_go_intervals(prereg, intervals)
        decision = evaluate_pilot(prereg, metrics, intervals=intervals, require_go_intervals=True)
        args.report.write_text(
            render_pilot_report(decision, episodes=args.episodes, manifest_path=args.manifest),
            encoding="utf-8",
        )
        print(f"wrote pilot report: {args.report} ({decision.decision})")
        return 0 if decision.decision == "go" else 1

    args.report.write_text(render_not_ready_report(args.episodes), encoding="utf-8")
    print(f"wrote pending pilot report: {args.report}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
