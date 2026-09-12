"""Pilot go/kill criterion evaluation and report rendering."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from collie.contracts import EpisodeResult, ParseOutcome, ShockFamily
from collie.eval.efficiency import frontier_from_results, pareto_frontier
from collie.eval.intervals import paired_interval
from collie.eval.operational import time_to_recovery
from collie.eval.prereg import Preregistration

__all__ = [
    "BASELINE_ARM",
    "CONTRIBUTION_ARM",
    "CriterionVerdict",
    "PilotDecision",
    "PilotManifest",
    "compute_builtin_pilot_intervals",
    "compute_builtin_pilot_metrics",
    "evaluate_pilot",
    "pilot_manifest_from_records",
    "render_pilot_report",
    "validate_go_intervals",
    "validate_pilot_record_count",
    "write_pilot_manifest",
]

CONTRIBUTION_ARM = "arm10_shockspec_eprocess"
BASELINE_ARM = "arm1_capped_base_stock"


@dataclass(frozen=True, slots=True)
class CriterionVerdict:
    id: str
    estimate: float | None
    ci_low: float | None
    ci_high: float | None
    threshold: float | None
    operator: str
    passed: bool
    source: str


@dataclass(frozen=True, slots=True)
class PilotDecision:
    date: str
    go: tuple[CriterionVerdict, ...]
    kill: tuple[CriterionVerdict, ...]

    @property
    def decision(self) -> str:
        if any(verdict.passed for verdict in self.kill):
            return "kill-or-reframe"
        if all(verdict.passed for verdict in self.go):
            return "go"
        return "no-go"


@dataclass(frozen=True, slots=True)
class PilotManifest:
    schema_version: int
    created_at: str
    requested_episodes: int
    observed_episode_results: int
    seeds: tuple[str, ...]
    templates: tuple[str, ...]
    freeze_manifest_sha256: str | None
    records_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "requested_episodes": self.requested_episodes,
            "observed_episode_results": self.observed_episode_results,
            "seeds": list(self.seeds),
            "templates": list(self.templates),
            "freeze_manifest_sha256": self.freeze_manifest_sha256,
            "records_sha256": self.records_sha256,
        }


def _file_sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pilot_manifest_from_records(
    results: Sequence[EpisodeResult],
    *,
    requested_episodes: int,
    freeze_manifest_path: Path | None = None,
    records_path: Path | None = None,
) -> PilotManifest:
    """Capture pilot seeds/templates before any later freeze drift can spend them silently."""
    seeds = sorted({result.independent_unit_id for result in results if result.independent_unit_id})
    templates = sorted(
        {
            record.template_id
            for result in results
            for record in result.records
            if record.template_id
        }
    )
    return PilotManifest(
        schema_version=1,
        created_at=dt.date.today().isoformat(),
        requested_episodes=requested_episodes,
        observed_episode_results=len(results),
        seeds=tuple(str(seed) for seed in seeds),
        templates=tuple(str(template) for template in templates),
        freeze_manifest_sha256=_file_sha256(freeze_manifest_path),
        records_sha256=_file_sha256(records_path),
    )


def write_pilot_manifest(path: Path, manifest: PilotManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def validate_pilot_record_count(results: Sequence[EpisodeResult]) -> None:
    """Require 100-150 paired independent units with provenance ids."""
    missing = [result.episode_id for result in results if not result.independent_unit_id]
    if missing:
        raise ValueError(
            "pilot records must carry independent_unit_id for paired evaluation; "
            f"missing examples: {missing[:5]}"
        )
    units = {result.independent_unit_id for result in results}
    if not 100 <= len(units) <= 150:
        raise ValueError(f"pilot records must cover 100-150 independent units; found {len(units)}")
    by_unit: dict[str, set[str]] = {}
    for result in results:
        by_unit.setdefault(str(result.independent_unit_id), set()).add(result.arm_id)
    incomplete = [
        unit
        for unit, arms in by_unit.items()
        if not {CONTRIBUTION_ARM, BASELINE_ARM}.issubset(arms)
    ]
    if incomplete:
        raise ValueError(
            "pilot records must include paired contribution and baseline arms for every "
            f"independent unit; incomplete examples: {incomplete[:5]}"
        )


def _compare(estimate: float | None, operator: str, threshold: float | None) -> bool:
    if estimate is None or threshold is None:
        return False
    match operator:
        case ">=":
            return estimate >= threshold
        case ">":
            return estimate > threshold
        case "<=":
            return estimate <= threshold
        case "<":
            return estimate < threshold
        case "==":
            return estimate == threshold
        case _:
            raise ValueError(f"unsupported criterion operator {operator!r}")


def _threshold(value: Any, thresholds: Mapping[str, Any]) -> float | None:
    if value == "none":
        return None
    resolved = thresholds.get(value, value) if isinstance(value, str) else value
    if not isinstance(resolved, int | float):
        raise ValueError(f"criterion threshold {value!r} is not numeric")
    return float(resolved)


def _verdict(
    item: Mapping[str, Any],
    metrics: Mapping[str, float],
    *,
    intervals: Mapping[str, tuple[float, float]],
    thresholds: Mapping[str, Any],
    default_operator: str,
) -> CriterionVerdict:
    criterion_id = str(item["id"])
    operator = str(item.get("operator", default_operator))
    threshold = _threshold(item["threshold"], thresholds)
    estimate = metrics.get(criterion_id)
    return CriterionVerdict(
        id=criterion_id,
        estimate=None if estimate is None else float(estimate),
        ci_low=intervals.get(criterion_id, (None, None))[0],
        ci_high=intervals.get(criterion_id, (None, None))[1],
        threshold=threshold,
        operator=operator,
        passed=_compare(None if estimate is None else float(estimate), operator, threshold),
        source=str(item.get("source", "computed")),
    )


def evaluate_pilot(
    prereg: Preregistration,
    metrics: Mapping[str, float],
    *,
    intervals: Mapping[str, tuple[float, float]] | None = None,
    require_go_intervals: bool = False,
) -> PilotDecision:
    """Evaluate every registered go criterion and kill trigger against frozen thresholds."""
    intervals = intervals or {}
    if require_go_intervals:
        validate_go_intervals(prereg, intervals)
    go = tuple(
        _verdict(
            item,
            metrics,
            intervals=intervals,
            thresholds={},
            default_operator=str(item.get("operator", ">=")),
        )
        for item in prereg.data["go_criteria"]
    )
    kill_thresholds = prereg.data["kill_thresholds"]
    kill = tuple(
        _verdict(
            item,
            metrics,
            intervals=intervals,
            thresholds=kill_thresholds,
            default_operator=str(item.get("operator", ">=")),
        )
        for item in prereg.data["kill_triggers"]
    )
    return PilotDecision(date=dt.date.today().isoformat(), go=go, kill=kill)


def validate_go_intervals(
    prereg: Preregistration, intervals: Mapping[str, tuple[float, float]]
) -> None:
    """Require every registered pilot go criterion to have a finite interval."""
    missing: list[str] = []
    invalid: list[str] = []
    for item in prereg.data["go_criteria"]:
        criterion_id = str(item["id"])
        interval = intervals.get(criterion_id)
        if interval is None:
            missing.append(criterion_id)
            continue
        low, high = interval
        if not np.isfinite(low) or not np.isfinite(high) or low > high:
            invalid.append(criterion_id)
    if missing or invalid:
        parts = []
        if missing:
            parts.append(f"missing intervals: {missing}")
        if invalid:
            parts.append(f"invalid intervals: {invalid}")
        raise ValueError("formal pilot go criteria require paired intervals; " + "; ".join(parts))


def _mean(results: Sequence[EpisodeResult], arm: str, attr: str) -> float | None:
    values = [float(getattr(result, attr)) for result in results if result.arm_id == arm]
    if not values:
        return None
    return float(np.mean(values))


def _mean_interval(
    values: Sequence[float], *, confidence: float = 0.95
) -> tuple[float, float] | None:
    if not values:
        return None
    if len(values) == 1:
        value = float(values[0])
        return value, value
    from statistics import NormalDist

    alpha = 1.0 - confidence
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    estimate = float(np.mean(values))
    half_width = float(z * np.std(values, ddof=1) / np.sqrt(len(values)))
    return estimate - half_width, estimate + half_width


def _has_active_spec(result: EpisodeResult) -> bool:
    return any(record.active_spec_id for record in result.records)


def _is_null_result(result: EpisodeResult) -> bool:
    return result.family is ShockFamily.NO_CHANGE


def compute_builtin_pilot_metrics(
    results: Sequence[EpisodeResult],
    *,
    call_budget_per_episode: int | None = None,
    shock_periods: Mapping[str, int] | None = None,
) -> dict[str, float]:
    """Compute metrics that are available directly from stored episode results."""
    metrics: dict[str, float] = {}
    arm10_profit = _mean(results, CONTRIBUTION_ARM, "total_profit")
    arm1_profit = _mean(results, BASELINE_ARM, "total_profit")
    arm10_lost = _mean(results, CONTRIBUTION_ARM, "total_lost_sales")
    arm1_lost = _mean(results, BASELINE_ARM, "total_lost_sales")
    arm10_fill = _mean(results, CONTRIBUTION_ARM, "fill_rate")

    if arm10_profit is not None and arm1_profit is not None:
        lift = arm10_profit - arm1_profit
        metrics["profit_lift"] = lift
        metrics["negative_profit_lift"] = lift
    if arm10_lost is not None and arm1_lost is not None:
        metrics["lost_sales_reduction"] = arm1_lost - arm10_lost
    if arm10_fill is not None:
        metrics["fill_rate_floor"] = arm10_fill
    arm10_results = [result for result in results if result.arm_id == CONTRIBUTION_ARM]
    arm10_calls = [log for result in arm10_results for log in result.calls]
    if arm10_calls:
        parser_failures = [log.outcome is ParseOutcome.FALLBACK for log in arm10_calls]
        metrics["parser_failure_rate"] = float(np.mean(parser_failures))
    null_results = [result for result in arm10_results if _is_null_result(result)]
    if null_results:
        false_activations = [_has_active_spec(result) for result in null_results]
        metrics["false_activation_rate"] = float(np.mean(false_activations))
        metrics["false_activation_control"] = 1.0 - metrics["false_activation_rate"]
    if shock_periods:
        recoveries = [
            time_to_recovery(result.records, shock_period=shock_periods[result.episode_id])
            for result in arm10_results
            if result.episode_id in shock_periods
        ]
        recovery_values = [float(value) for value in recoveries if value is not None]
        if recovery_values:
            metrics["recovery_time"] = float(np.mean(recovery_values))
    if arm10_results:
        cost_points = frontier_from_results(
            results,
            lambda group: float(sum(log.usd_cost for result in group for log in result.calls)),
        )
        cost_frontier = {point.arm for point in pareto_frontier(cost_points)}
        metrics["cost_frontier"] = 1.0 if CONTRIBUTION_ARM in cost_frontier else 0.0
    if call_budget_per_episode is not None:
        calls = [len(result.calls) for result in arm10_results]
        if calls:
            metrics["budget_overrun_rate"] = float(
                np.mean([count > call_budget_per_episode for count in calls])
            )
    return metrics


def compute_builtin_pilot_intervals(
    results: Sequence[EpisodeResult], *, shock_periods: Mapping[str, int] | None = None
) -> dict[str, tuple[float, float]]:
    """Compute paired intervals for built-in pilot go criteria available from records."""
    intervals: dict[str, tuple[float, float]] = {}
    try:
        profit = paired_interval(
            results,
            treatment=CONTRIBUTION_ARM,
            control=BASELINE_ARM,
            endpoint="cumulative_undiscounted_profit",
        )
        intervals["profit_lift"] = (profit.ci_low, profit.ci_high)
    except ValueError:
        pass
    try:
        lost_sales = paired_interval(
            results,
            treatment=BASELINE_ARM,
            control=CONTRIBUTION_ARM,
            endpoint="total_lost_sales_units",
        )
        intervals["lost_sales_reduction"] = (lost_sales.ci_low, lost_sales.ci_high)
    except ValueError:
        pass
    arm10_results = [result for result in results if result.arm_id == CONTRIBUTION_ARM]
    fill_interval = _mean_interval([result.fill_rate for result in arm10_results])
    if fill_interval is not None:
        intervals["fill_rate_floor"] = fill_interval
    if shock_periods:
        recoveries = [
            time_to_recovery(result.records, shock_period=shock_periods[result.episode_id])
            for result in arm10_results
            if result.episode_id in shock_periods
        ]
        recovery_interval = _mean_interval(
            [float(value) for value in recoveries if value is not None]
        )
        if recovery_interval is not None:
            intervals["recovery_time"] = recovery_interval
    return intervals


def _render_verdicts(title: str, verdicts: Sequence[CriterionVerdict]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| id | estimate | ci_low | ci_high | operator | threshold | verdict | source |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for verdict in verdicts:
        estimate = "missing" if verdict.estimate is None else f"{verdict.estimate:.6g}"
        ci_low = "missing" if verdict.ci_low is None else f"{verdict.ci_low:.6g}"
        ci_high = "missing" if verdict.ci_high is None else f"{verdict.ci_high:.6g}"
        threshold = "none" if verdict.threshold is None else f"{verdict.threshold:.6g}"
        outcome = "pass" if verdict.passed else "fail"
        lines.append(
            f"| `{verdict.id}` | {estimate} | {ci_low} | {ci_high} | "
            f"`{verdict.operator}` | {threshold} | {outcome} | {verdict.source} |"
        )
    return [*lines, ""]


def render_pilot_report(
    decision: PilotDecision, *, episodes: int, manifest_path: Path | None = None
) -> str:
    """Render the dated pilot decision."""
    lines = [
        f"# Pilot report ({decision.date})",
        "",
        f"Requested episodes: {episodes}",
        "",
    ]
    if manifest_path is not None:
        lines.extend([f"Pilot manifest: `{manifest_path}`", ""])
    lines.extend([f"Decision: **{decision.decision}**", ""])
    lines.extend(_render_verdicts("Go Criteria", decision.go))
    lines.extend(_render_verdicts("Kill Or Reframe Triggers", decision.kill))
    return "\n".join(lines)
