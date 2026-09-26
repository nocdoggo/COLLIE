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

from collie.arms.base_stock import ARM1_ARM_ID
from collie.arms.controls import DETECTOR_CONTROL_ARM_ID
from collie.arms.oracle import ORACLE_ARM_ID
from collie.arms.shockspec import ARM10_ARM_ID
from collie.contracts import Direction, EpisodeResult, ParseOutcome, ShockFamily, Split
from collie.eval.efficiency import frontier_from_results, pareto_frontier
from collie.eval.intervals import paired_interval, stratum_weighted_paired_interval
from collie.eval.operational import cvar10, time_to_recovery
from collie.eval.prereg import Preregistration, primary_stratum_weights
from collie.eval.truth import EpisodeTruth, wrong_spec_exposure

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
    "validate_pilot_intervals",
    "validate_pilot_metrics",
    "validate_pilot_record_count",
    "write_pilot_manifest",
]

CONTRIBUTION_ARM = ARM10_ARM_ID
BASELINE_ARM = ARM1_ARM_ID
HEADROOM_RAW_PROFIT_LIFT = 0.05
HEADROOM_CVAR10_LIFT = 0.10


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
    truth_sha256: str | None = None

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
            "truth_sha256": self.truth_sha256,
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
    truth_path: Path | None = None,
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
        truth_sha256=_file_sha256(truth_path),
    )


def write_pilot_manifest(path: Path, manifest: PilotManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def validate_pilot_record_count(
    results: Sequence[EpisodeResult], *, prereg: Preregistration | None = None
) -> None:
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
    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for result in results:
        key = (str(result.independent_unit_id), result.arm_id)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise ValueError(
            "pilot records must contain at most one row per (independent_unit_id, arm); "
            f"duplicate examples: {duplicates[:5]}"
        )
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
    shocked_incomplete = [
        unit
        for unit, arms in by_unit.items()
        if any(
            result.independent_unit_id == unit
            and result.family not in {None, ShockFamily.NO_CHANGE}
            for result in results
        )
        and not {ORACLE_ARM_ID, DETECTOR_CONTROL_ARM_ID}.issubset(arms)
    ]
    if prereg is not None and shocked_incomplete:
        raise ValueError(
            "formal shocked pilot units must include oracle and detector-control arms; "
            f"incomplete examples: {shocked_incomplete[:5]}"
        )
    if prereg is None:
        return
    invalid_split = [
        result.episode_id for result in results if result.split not in {Split.DEV, Split.CAL}
    ]
    if invalid_split:
        raise ValueError(
            "formal pilot records must come only from dev/cal splits; "
            f"invalid examples: {invalid_split[:5]}"
        )
    required_strata = set(primary_stratum_weights(prereg.data))
    for arm in (CONTRIBUTION_ARM, BASELINE_ARM):
        observed = {
            (result.family.value, result.information_condition.value)
            for result in results
            if result.arm_id == arm
            and result.family is not None
            and result.information_condition is not None
        }
        missing_strata = sorted(required_strata - observed)
        if missing_strata:
            raise ValueError(
                f"formal pilot arm {arm!r} is missing registered strata: {missing_strata[:5]}"
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
    use_conservative_interval: bool = False,
) -> CriterionVerdict:
    criterion_id = str(item["id"])
    operator = str(item.get("operator", default_operator))
    threshold = _threshold(item["threshold"], thresholds)
    estimate = metrics.get(criterion_id)
    comparison_value = None if estimate is None else float(estimate)
    interval = intervals.get(criterion_id)
    if use_conservative_interval and interval is not None:
        if operator in {">=", ">"}:
            comparison_value = float(interval[0])
        elif operator in {"<=", "<"}:
            comparison_value = float(interval[1])
    passed = _compare(comparison_value, operator, threshold)
    if criterion_id == "method_freeze_or_quarantine_violation" and threshold is None:
        passed = estimate is not None and float(estimate) != 0.0
    return CriterionVerdict(
        id=criterion_id,
        estimate=None if estimate is None else float(estimate),
        ci_low=intervals.get(criterion_id, (None, None))[0],
        ci_high=intervals.get(criterion_id, (None, None))[1],
        threshold=threshold,
        operator=operator,
        passed=passed,
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
        validate_pilot_intervals(prereg, intervals)
        validate_pilot_metrics(prereg, metrics)
    go = tuple(
        _verdict(
            item,
            metrics,
            intervals=intervals,
            thresholds={},
            default_operator=str(item.get("operator", ">=")),
            use_conservative_interval=require_go_intervals,
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


def validate_pilot_intervals(
    prereg: Preregistration, intervals: Mapping[str, tuple[float, float]]
) -> None:
    """Require finite intervals for every statistical go/kill pilot criterion."""
    registered = [
        *(str(item["id"]) for item in prereg.data["go_criteria"]),
        *(
            str(item["id"])
            for item in prereg.data["kill_triggers"]
            if item["id"] != "method_freeze_or_quarantine_violation"
        ),
    ]
    missing = [criterion_id for criterion_id in registered if criterion_id not in intervals]
    invalid = [
        criterion_id
        for criterion_id in registered
        if criterion_id in intervals
        and (
            not np.isfinite(intervals[criterion_id][0])
            or not np.isfinite(intervals[criterion_id][1])
            or intervals[criterion_id][0] > intervals[criterion_id][1]
        )
    ]
    if missing or invalid:
        parts = []
        if missing:
            parts.append(f"missing intervals: {missing}")
        if invalid:
            parts.append(f"invalid intervals: {invalid}")
        raise ValueError("formal pilot criteria require intervals; " + "; ".join(parts))


def validate_pilot_metrics(prereg: Preregistration, metrics: Mapping[str, float]) -> None:
    """Require a finite estimate for every registered formal-pilot verdict."""
    registered = [
        *(str(item["id"]) for item in prereg.data["go_criteria"]),
        *(str(item["id"]) for item in prereg.data["kill_triggers"]),
    ]
    missing = [criterion_id for criterion_id in registered if criterion_id not in metrics]
    invalid = [
        criterion_id
        for criterion_id in registered
        if criterion_id in metrics and not np.isfinite(metrics[criterion_id])
    ]
    if missing or invalid:
        parts = []
        if missing:
            parts.append(f"missing estimates: {missing}")
        if invalid:
            parts.append(f"invalid estimates: {invalid}")
        raise ValueError("formal pilot requires every registered criterion; " + "; ".join(parts))


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


def _pilot_recovery_values(
    results: Sequence[EpisodeResult],
    shock_periods: Mapping[str, int],
    *,
    never_recovered_value: float | None = None,
) -> list[float]:
    eligible = [result for result in results if not _is_null_result(result)]
    missing = [result.episode_id for result in eligible if result.episode_id not in shock_periods]
    if missing:
        raise ValueError(f"recovery_time is missing shock periods for episodes: {missing[:5]}")
    recoveries = [
        time_to_recovery(result.records, shock_period=shock_periods[result.episode_id])
        for result in eligible
    ]
    if any(value is None for value in recoveries) and never_recovered_value is None:
        raise ValueError(
            "recovery_time includes episodes that never recover; register a censoring or "
            "horizon-plus-one rule before issuing a formal pilot verdict"
        )
    return [float(never_recovered_value if value is None else value) for value in recoveries]


def _wrong_family_exposure(result: EpisodeResult) -> float | None:
    """Return the fraction of periods exposed to an active wrong-family spec."""
    if result.family is None or result.family is ShockFamily.NO_CHANGE or not result.records:
        return None
    wrong_periods = 0
    for record in result.records:
        if record.active_spec_id is not None and record.active_spec is None:
            raise ValueError(
                "active_spec_id requires active_spec provenance for wrong-family evaluation"
            )
        if record.active_spec is not None and record.active_spec.shock_family != result.family:
            wrong_periods += 1
    return wrong_periods / len(result.records)


def _cost_frontier_status(results: Sequence[EpisodeResult]) -> float:
    cost_points = frontier_from_results(
        results,
        lambda group: float(sum(log.usd_cost for result in group for log in result.calls)),
    )
    frontier_arms = {point.arm for point in pareto_frontier(cost_points)}
    return 1.0 if CONTRIBUTION_ARM in frontier_arms else 0.0


def _cost_frontier_interval(
    results: Sequence[EpisodeResult], *, resamples: int = 2_000, seed: int = 0
) -> tuple[float, float] | None:
    """Bootstrap frontier membership by resampling complete independent units."""
    by_unit: dict[str, list[EpisodeResult]] = {}
    for result in results:
        if result.independent_unit_id is not None:
            by_unit.setdefault(result.independent_unit_id, []).append(result)
    if not by_unit:
        return None
    groups = tuple(by_unit.values())
    if len(groups) == 1:
        status = _cost_frontier_status(groups[0])
        return status, status
    rng = np.random.default_rng(seed)
    statuses = np.empty(resamples, dtype=float)
    for index in range(resamples):
        sampled = rng.integers(0, len(groups), size=len(groups))
        draw = [result for group_index in sampled for result in groups[int(group_index)]]
        statuses[index] = _cost_frontier_status(draw)
    return tuple(float(value) for value in np.quantile(statuses, [0.025, 0.975]))


def _terminal_parser_failures(result: EpisodeResult) -> tuple[bool, ...]:
    """One terminal parse outcome per proposal period, after any repair attempt."""
    by_period: dict[int, list] = {}
    for log in result.calls:
        by_period.setdefault(log.period, []).append(log)
    return tuple(
        max(logs, key=lambda log: log.attempt_index).outcome is ParseOutcome.FALLBACK
        for _period, logs in sorted(by_period.items())
    )


def _relative_lift(treatment: float, control: float) -> float:
    denominator = abs(control)
    if denominator == 0.0:
        if treatment > control:
            return float("inf")
        return 0.0 if treatment == control else float("-inf")
    return (treatment - control) / denominator


def _headroom_key(result: EpisodeResult, truths: Mapping[str, EpisodeTruth] | None) -> str | None:
    if result.family is None or result.family is ShockFamily.NO_CHANGE:
        return None
    if truths is None:
        return result.family.value
    truth = truths.get(result.episode_id)
    if truth is None:
        return result.family.value
    if truth.family is ShockFamily.DEMAND_LEVEL:
        return f"{truth.family.value}:{truth.direction.value}"
    return truth.family.value


def _headroom_required_keys(truths: Mapping[str, EpisodeTruth] | None) -> tuple[str, ...]:
    if truths is None:
        return tuple(family.value for family in ShockFamily if family is not ShockFamily.NO_CHANGE)
    return (
        f"{ShockFamily.DEMAND_LEVEL.value}:{Direction.DEMAND_UP.value}",
        f"{ShockFamily.DEMAND_LEVEL.value}:{Direction.DEMAND_DOWN.value}",
        ShockFamily.TEMPORARY_PULSE.value,
        ShockFamily.LEAD_TIME_SHIFT.value,
        ShockFamily.SHIPMENT_LOSS.value,
        ShockFamily.COMPOUND.value,
    )


def _headroom_family_values(
    results: Sequence[EpisodeResult],
    truths: Mapping[str, EpisodeTruth] | None = None,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Paired oracle and ARM1 profit arrays for every registered shocked family."""
    values: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    missing: list[str] = []
    for family in _headroom_required_keys(truths):
        by_unit: dict[str, dict[str, float]] = {}
        for result in results:
            if _headroom_key(result, truths) != family or result.independent_unit_id is None:
                continue
            if result.arm_id not in {ORACLE_ARM_ID, BASELINE_ARM}:
                continue
            by_unit.setdefault(str(result.independent_unit_id), {})[result.arm_id] = float(
                result.total_profit
            )
        complete = [
            arms for arms in by_unit.values() if ORACLE_ARM_ID in arms and BASELINE_ARM in arms
        ]
        if not complete:
            missing.append(family)
            continue
        values[family] = (
            np.asarray([arms[ORACLE_ARM_ID] for arms in complete], dtype=float),
            np.asarray([arms[BASELINE_ARM] for arms in complete], dtype=float),
        )
    if missing:
        raise ValueError(f"headroom evaluation is missing paired oracle/ARM1 families: {missing}")
    return values


def _headroom_count_from_values(
    values: Mapping[str, tuple[np.ndarray, np.ndarray]],
) -> int:
    passing = 0
    for oracle, baseline in values.values():
        raw_lift = _relative_lift(float(np.mean(oracle)), float(np.mean(baseline)))
        cvar_lift = _relative_lift(cvar10(tuple(oracle)), cvar10(tuple(baseline)))
        passing += raw_lift >= HEADROOM_RAW_PROFIT_LIFT or cvar_lift >= HEADROOM_CVAR10_LIFT
    return int(passing)


def _headroom_interval(
    results: Sequence[EpisodeResult],
    *,
    truths: Mapping[str, EpisodeTruth] | None = None,
    resamples: int = 2_000,
    seed: int = 0,
) -> tuple[float, float]:
    values = _headroom_family_values(results, truths)
    rng = np.random.default_rng(seed)
    counts = np.empty(resamples, dtype=float)
    for draw_index in range(resamples):
        draw: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for family, (oracle, baseline) in values.items():
            sampled = rng.integers(0, len(oracle), size=len(oracle))
            draw[family] = oracle[sampled], baseline[sampled]
        counts[draw_index] = _headroom_count_from_values(draw)
    return tuple(float(value) for value in np.quantile(counts, [0.025, 0.975]))


def compute_builtin_pilot_metrics(
    results: Sequence[EpisodeResult],
    *,
    call_budget_per_episode: int | None = None,
    shock_periods: Mapping[str, int] | None = None,
    stratum_weights: Mapping[tuple[str, str], float] | None = None,
    never_recovered_value: float | None = None,
    truths: Mapping[str, EpisodeTruth] | None = None,
) -> dict[str, float]:
    """Compute metrics that are available directly from stored episode results."""
    metrics: dict[str, float] = {}
    arm10_profit = _mean(results, CONTRIBUTION_ARM, "total_profit")
    arm1_profit = _mean(results, BASELINE_ARM, "total_profit")
    arm10_lost = _mean(results, CONTRIBUTION_ARM, "total_lost_sales")
    arm1_lost = _mean(results, BASELINE_ARM, "total_lost_sales")
    arm10_fill = _mean(results, CONTRIBUTION_ARM, "fill_rate")

    if stratum_weights is not None:
        profit_contrast = stratum_weighted_paired_interval(
            results,
            treatment=CONTRIBUTION_ARM,
            control=BASELINE_ARM,
            endpoint="cumulative_undiscounted_profit",
            weights=stratum_weights,
        )
        lost_sales_contrast = stratum_weighted_paired_interval(
            results,
            treatment=BASELINE_ARM,
            control=CONTRIBUTION_ARM,
            endpoint="total_lost_sales_units",
            weights=stratum_weights,
        )
        lift = profit_contrast.estimate
        metrics["profit_lift"] = lift
        metrics["negative_profit_lift"] = lift
        metrics["lost_sales_reduction"] = lost_sales_contrast.estimate
    else:
        if arm10_profit is not None and arm1_profit is not None:
            lift = arm10_profit - arm1_profit
            metrics["profit_lift"] = lift
            metrics["negative_profit_lift"] = lift
        if arm10_lost is not None and arm1_lost is not None:
            metrics["lost_sales_reduction"] = arm1_lost - arm10_lost
    if arm10_fill is not None:
        metrics["fill_rate_floor"] = arm10_fill
    arm10_results = [result for result in results if result.arm_id == CONTRIBUTION_ARM]
    parser_failures = [
        failed for result in arm10_results for failed in _terminal_parser_failures(result)
    ]
    if parser_failures:
        metrics["parser_failure_rate"] = float(np.mean(parser_failures))
    null_results = [result for result in arm10_results if _is_null_result(result)]
    if null_results:
        false_activations = [_has_active_spec(result) for result in null_results]
        metrics["false_activation_rate"] = float(np.mean(false_activations))
        metrics["false_activation_control"] = 1.0 - metrics["false_activation_rate"]
    non_null_results = [result for result in arm10_results if not _is_null_result(result)]
    wrong_family_exposures = [
        exposure
        for result in non_null_results
        if (exposure := _wrong_family_exposure(result)) is not None
    ]
    if wrong_family_exposures:
        metrics["wrong_family_exposure"] = float(np.mean(wrong_family_exposures))
        metrics["wrong_family_activation_rate"] = float(
            np.mean([exposure > 0.0 for exposure in wrong_family_exposures])
        )
    if truths is not None:
        missing_truth = [
            result.episode_id for result in non_null_results if result.episode_id not in truths
        ]
        if missing_truth:
            raise ValueError(f"wrong-spec evaluation is missing truth: {missing_truth[:5]}")
        exact_exposures = [
            wrong_spec_exposure(result, truths[result.episode_id]) for result in non_null_results
        ]
        if exact_exposures:
            metrics["wrong_spec_exposure"] = float(np.mean(exact_exposures))
    if shock_periods:
        recovery_values = _pilot_recovery_values(
            arm10_results,
            shock_periods,
            never_recovered_value=never_recovered_value,
        )
        if recovery_values:
            metrics["recovery_time"] = float(np.mean(recovery_values))
    if arm10_results:
        metrics["cost_frontier"] = _cost_frontier_status(results)
    if any(result.arm_id == ORACLE_ARM_ID for result in results):
        metrics["insufficient_headroom"] = float(
            _headroom_count_from_values(_headroom_family_values(results, truths))
        )
    if any(result.arm_id == DETECTOR_CONTROL_ARM_ID for result in results):
        detector = paired_interval(
            results,
            treatment=CONTRIBUTION_ARM,
            control=DETECTOR_CONTROL_ARM_ID,
            endpoint="cumulative_undiscounted_profit",
        )
        metrics["detector_indistinguishable"] = detector.estimate
    if call_budget_per_episode is not None:
        calls = [len(result.calls) for result in arm10_results]
        if calls:
            metrics["budget_overrun_rate"] = float(
                np.mean([count > call_budget_per_episode for count in calls])
            )
    return metrics


def compute_builtin_pilot_intervals(
    results: Sequence[EpisodeResult],
    *,
    shock_periods: Mapping[str, int] | None = None,
    stratum_weights: Mapping[tuple[str, str], float] | None = None,
    never_recovered_value: float | None = None,
    call_budget_per_episode: int | None = None,
    truths: Mapping[str, EpisodeTruth] | None = None,
) -> dict[str, tuple[float, float]]:
    """Compute paired intervals for built-in pilot go criteria available from records."""
    intervals: dict[str, tuple[float, float]] = {}
    try:
        profit = (
            stratum_weighted_paired_interval(
                results,
                treatment=CONTRIBUTION_ARM,
                control=BASELINE_ARM,
                endpoint="cumulative_undiscounted_profit",
                weights=stratum_weights,
            )
            if stratum_weights is not None
            else paired_interval(
                results,
                treatment=CONTRIBUTION_ARM,
                control=BASELINE_ARM,
                endpoint="cumulative_undiscounted_profit",
            )
        )
        intervals["profit_lift"] = (profit.ci_low, profit.ci_high)
    except ValueError:
        pass
    try:
        lost_sales = (
            stratum_weighted_paired_interval(
                results,
                treatment=BASELINE_ARM,
                control=CONTRIBUTION_ARM,
                endpoint="total_lost_sales_units",
                weights=stratum_weights,
            )
            if stratum_weights is not None
            else paired_interval(
                results,
                treatment=BASELINE_ARM,
                control=CONTRIBUTION_ARM,
                endpoint="total_lost_sales_units",
            )
        )
        intervals["lost_sales_reduction"] = (lost_sales.ci_low, lost_sales.ci_high)
    except ValueError:
        pass
    arm10_results = [result for result in results if result.arm_id == CONTRIBUTION_ARM]
    fill_interval = _mean_interval([result.fill_rate for result in arm10_results])
    if fill_interval is not None:
        intervals["fill_rate_floor"] = fill_interval
    null_results = [result for result in arm10_results if _is_null_result(result)]
    false_activation_control = _mean_interval(
        [0.0 if _has_active_spec(result) else 1.0 for result in null_results]
    )
    if false_activation_control is not None:
        intervals["false_activation_control"] = false_activation_control
        intervals["false_activation_rate"] = tuple(
            1.0 - value for value in reversed(false_activation_control)
        )
    wrong_family_exposure = _mean_interval(
        [
            exposure
            for result in arm10_results
            if (exposure := _wrong_family_exposure(result)) is not None
        ]
    )
    if wrong_family_exposure is not None:
        intervals["wrong_family_exposure"] = wrong_family_exposure
    wrong_family_activation = _mean_interval(
        [
            float(exposure > 0.0)
            for result in arm10_results
            if (exposure := _wrong_family_exposure(result)) is not None
        ]
    )
    if wrong_family_activation is not None:
        intervals["wrong_family_activation_rate"] = wrong_family_activation
    if truths is not None:
        non_null_results = [result for result in arm10_results if not _is_null_result(result)]
        missing_truth = [
            result.episode_id for result in non_null_results if result.episode_id not in truths
        ]
        if missing_truth:
            raise ValueError(f"wrong-spec evaluation is missing truth: {missing_truth[:5]}")
        wrong_spec_interval = _mean_interval(
            [wrong_spec_exposure(result, truths[result.episode_id]) for result in non_null_results]
        )
        if wrong_spec_interval is not None:
            intervals["wrong_spec_exposure"] = wrong_spec_interval
    cost_frontier = _cost_frontier_interval(results)
    if cost_frontier is not None:
        intervals["cost_frontier"] = cost_frontier
    if shock_periods:
        recovery_interval = _mean_interval(
            _pilot_recovery_values(
                arm10_results,
                shock_periods,
                never_recovered_value=never_recovered_value,
            )
        )
        if recovery_interval is not None:
            intervals["recovery_time"] = recovery_interval
    parser_episode_rates = [
        float(np.mean(failures))
        for result in arm10_results
        if (failures := _terminal_parser_failures(result))
    ]
    parser_interval = _mean_interval(parser_episode_rates)
    if parser_interval is not None:
        intervals["parser_failure_rate"] = parser_interval
    if call_budget_per_episode is not None:
        budget_interval = _mean_interval(
            [float(len(result.calls) > call_budget_per_episode) for result in arm10_results]
        )
        if budget_interval is not None:
            intervals["budget_overrun_rate"] = budget_interval
    if "profit_lift" in intervals:
        intervals["negative_profit_lift"] = intervals["profit_lift"]
    if any(result.arm_id == ORACLE_ARM_ID for result in results):
        intervals["insufficient_headroom"] = _headroom_interval(results, truths=truths)
    if any(result.arm_id == DETECTOR_CONTROL_ARM_ID for result in results):
        detector = paired_interval(
            results,
            treatment=CONTRIBUTION_ARM,
            control=DETECTOR_CONTROL_ARM_ID,
            endpoint="cumulative_undiscounted_profit",
        )
        intervals["detector_indistinguishable"] = (detector.ci_low, detector.ci_high)
    return intervals


def _render_verdicts(
    title: str, verdicts: Sequence[CriterionVerdict], *, kill_triggers: bool = False
) -> list[str]:
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
        if kill_triggers:
            outcome = "triggered" if verdict.passed else "clear"
        else:
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
    lines.extend(_render_verdicts("Kill Or Reframe Triggers", decision.kill, kill_triggers=True))
    return "\n".join(lines)
