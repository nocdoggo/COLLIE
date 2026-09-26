"""Pilot runner for records produced by the frozen real-engine path.

The tool enforces preregistration, record provenance, paired coverage, and quarantine. It
can either evaluate stored records or assemble the registered dev/cal pilot with the same
runner used by the arm ladder.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
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
from collie.eval.prereg import load_preregistration, primary_stratum_weights
from collie.eval.records import load_episode_results_jsonl
from collie.eval.truth import (
    load_episode_truth_jsonl,
    shock_periods_from_truth,
    truth_by_episode,
)
from tools.freeze import FREEZE_PATH, drift, load_freeze
from tools.run_arms import run_pilot_artifacts

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "reports" / "pilot_manifest.json"
DEFAULT_RECORDS = REPO_ROOT / "reports" / "pilot_records.jsonl"
DEFAULT_TRUTH = REPO_ROOT / "reports" / "pilot_truth.jsonl"


def _quarantine_check(manifest_path: Path) -> None:
    frozen = load_freeze()
    if not frozen.get("complete", False):
        reasons = frozen.get("incomplete_reasons") or ["unspecified incomplete freeze"]
        raise SystemExit(
            "method freeze is incomplete; pilot cannot issue a formal verdict: "
            + "; ".join(str(reason) for reason in reasons)
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
            "Reason: no stored pilot EpisodeResult records were supplied. Run the frozen "
            "real-engine path first, then pass its JSONL output with --records. The pilot "
            "runner will not fabricate pilot estimates.",
            "",
            "Decision: pending.",
            "",
        ]
    )


def _evaluate_records(
    *,
    prereg,
    records_path: Path,
    truth_path: Path,
    shock_periods_path: Path | None,
    call_budget_per_episode: int | None,
    report_path: Path,
    manifest_path: Path,
    episodes: int,
) -> int:
    _quarantine_check(manifest_path)
    metrics = {}
    intervals = {}
    results = load_episode_results_jsonl(records_path)
    validate_pilot_record_count(results, prereg=prereg)
    truths = truth_by_episode(load_episode_truth_jsonl(truth_path))
    shock_periods = shock_periods_from_truth(truths)
    if shock_periods_path is not None:
        supplied = _load_int_mapping(shock_periods_path)
        if supplied != shock_periods:
            raise SystemExit("--shock-periods disagrees with the registered truth sidecar")
    weights = primary_stratum_weights(prereg.data)
    policy = prereg.data["pilot_policy"]
    registered_call_budget = int(policy["call_budget_per_episode"])
    if call_budget_per_episode is not None and call_budget_per_episode != registered_call_budget:
        raise SystemExit(
            f"--call-budget-per-episode must match the registered value {registered_call_budget}"
        )
    never_recovered_value = float(policy["never_recovered_value"])
    metrics.update(
        compute_builtin_pilot_metrics(
            results,
            call_budget_per_episode=registered_call_budget,
            shock_periods=shock_periods,
            stratum_weights=weights,
            never_recovered_value=never_recovered_value,
            truths=truths,
        )
    )
    metrics["method_freeze_or_quarantine_violation"] = 0.0
    intervals.update(
        compute_builtin_pilot_intervals(
            results,
            shock_periods=shock_periods,
            stratum_weights=weights,
            never_recovered_value=never_recovered_value,
            call_budget_per_episode=registered_call_budget,
            truths=truths,
        )
    )
    manifest = pilot_manifest_from_records(
        results,
        requested_episodes=episodes,
        freeze_manifest_path=FREEZE_PATH,
        records_path=records_path,
        truth_path=truth_path,
    )
    write_pilot_manifest(manifest_path, manifest)
    validate_go_intervals(prereg, intervals)
    decision = evaluate_pilot(prereg, metrics, intervals=intervals, require_go_intervals=True)
    report_path.write_text(
        render_pilot_report(decision, episodes=episodes, manifest_path=manifest_path),
        encoding="utf-8",
    )
    print(f"wrote pilot report: {report_path} ({decision.decision})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episodes", type=int, default=120)
    ap.add_argument("--report", type=Path, default=REPO_ROOT / "reports" / "pilot_report.md")
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--records", type=Path, help="stored EpisodeResult JSONL from the pilot run")
    ap.add_argument(
        "--records-out",
        type=Path,
        default=DEFAULT_RECORDS,
        help="where the generated pilot EpisodeResult JSONL is written when --records is absent",
    )
    ap.add_argument(
        "--truth",
        type=Path,
        help="evaluation-only EpisodeTruth JSONL emitted by the real pilot harness",
    )
    ap.add_argument(
        "--truth-out",
        type=Path,
        default=DEFAULT_TRUTH,
        help="where generated pilot truth JSONL is written when --records is absent",
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
    prereg = load_preregistration(require_final=True)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.records:
        if args.truth is None:
            raise SystemExit("--truth is required with --records for formal pilot provenance")
        return _evaluate_records(
            prereg=prereg,
            records_path=args.records,
            truth_path=args.truth,
            shock_periods_path=args.shock_periods,
            call_budget_per_episode=args.call_budget_per_episode,
            report_path=args.report,
            manifest_path=args.manifest,
            episodes=args.episodes,
        )

    _quarantine_check(args.manifest)
    args.records_out.parent.mkdir(parents=True, exist_ok=True)
    args.truth_out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        run_pilot_artifacts(
            Path(tmp),
            episodes=args.episodes,
            records_out=args.records_out,
            truth_out=args.truth_out,
        )
    return _evaluate_records(
        prereg=prereg,
        records_path=args.records_out,
        truth_path=args.truth_out,
        shock_periods_path=args.shock_periods,
        call_budget_per_episode=args.call_budget_per_episode,
        report_path=args.report,
        manifest_path=args.manifest,
        episodes=args.episodes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
