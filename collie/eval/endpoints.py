"""Primary endpoint aggregation and preregistered stratum weighting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from collie.contracts import EpisodeResult
from collie.eval.guards import assert_aggregation_unit_frame, result_frame

__all__ = [
    "CompatibilitySummary",
    "EndpointSummary",
    "aggregate_primary_endpoints",
    "compatibility_summaries",
    "equal_weighted_mean",
    "stratum_weighted_endpoints",
    "weighted_metric_by_field",
]


@dataclass(frozen=True, slots=True)
class EndpointSummary:
    arm: str
    endpoint: str
    value: float
    n_units: int


@dataclass(frozen=True, slots=True)
class CompatibilitySummary:
    arm: str
    metric: str
    value: float
    n_units: int
    harness: str


def aggregate_primary_endpoints(results: Sequence[EpisodeResult]) -> tuple[EndpointSummary, ...]:
    """Aggregate the two primary endpoints by arm after the unit guard passes."""
    frame = result_frame(results)
    assert_aggregation_unit_frame(frame)
    summaries: list[EndpointSummary] = []
    for arm, group in frame.groupby("arm", sort=True):
        summaries.append(
            EndpointSummary(
                arm=str(arm),
                endpoint="cumulative_undiscounted_profit",
                value=float(group["total_profit"].mean()),
                n_units=int(group["independent_unit_id"].nunique()),
            )
        )
        summaries.append(
            EndpointSummary(
                arm=str(arm),
                endpoint="total_lost_sales_units",
                value=float(group["total_lost_sales"].mean()),
                n_units=int(group["independent_unit_id"].nunique()),
            )
        )
    return tuple(summaries)


def weighted_metric_by_field(
    frame: pd.DataFrame,
    *,
    value_col: str,
    field: str,
    weights: Mapping[str, float],
) -> float:
    """Weight a metric by one registered prevalence field, such as split or family."""
    missing = {value_col, field} - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns for weighted compatibility metric: {sorted(missing)}")
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        subset = frame[frame[field] == key]
        if subset.empty:
            continue
        total += float(subset[value_col].mean()) * float(weight)
        used += float(weight)
    if used == 0.0:
        raise ValueError("no populated strata for weighted compatibility metric")
    return total / used


def compatibility_summaries(
    results: Sequence[EpisodeResult],
    *,
    deployment_weights: Mapping[str, float] | None = None,
    deployment_field: str = "split",
    harness: str = "eval",
) -> tuple[CompatibilitySummary, ...]:
    """Report official-normalized reward in reproducibility-friendly compatibility views."""
    frame = result_frame(results)
    assert_aggregation_unit_frame(frame)
    summaries: list[CompatibilitySummary] = []
    for arm, group in frame.groupby("arm", sort=True):
        summaries.append(
            CompatibilitySummary(
                arm=str(arm),
                metric="official_normalized_reward_micro",
                value=float(group["normalized_reward"].mean()),
                n_units=int(group["independent_unit_id"].nunique()),
                harness=harness,
            )
        )
        if deployment_weights:
            summaries.append(
                CompatibilitySummary(
                    arm=str(arm),
                    metric=f"official_normalized_reward_{deployment_field}_mixture",
                    value=weighted_metric_by_field(
                        group,
                        value_col="normalized_reward",
                        field=deployment_field,
                        weights=deployment_weights,
                    ),
                    n_units=int(group["independent_unit_id"].nunique()),
                    harness=harness,
                )
            )
    return tuple(summaries)


def equal_weighted_mean(
    frame: pd.DataFrame, *, value_col: str, strata: Sequence[str], weights: Mapping[tuple, float]
) -> float:
    """Mean within each stratum, then combine by explicit weights."""
    missing = {value_col, *strata} - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns for weighted mean: {sorted(missing)}")
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        if not isinstance(key, tuple):
            key = (key,)
        if len(key) != len(strata):
            raise ValueError(f"weight key {key!r} does not match strata {strata!r}")
        mask = pd.Series(True, index=frame.index)
        for col, value in zip(strata, key, strict=True):
            mask &= frame[col] == value
        subset = frame[mask]
        if subset.empty:
            continue
        total += float(subset[value_col].mean()) * float(weight)
        used += float(weight)
    if used == 0.0:
        raise ValueError("no populated strata for weighted mean")
    return total / used


def stratum_weighted_endpoints(
    results: Sequence[EpisodeResult], weights: Mapping[tuple, float]
) -> tuple[EndpointSummary, ...]:
    """Compute primary endpoints with caller-supplied stratum weights."""
    frame = result_frame(results)
    assert_aggregation_unit_frame(frame)
    summaries: list[EndpointSummary] = []
    for arm, group in frame.groupby("arm", sort=True):
        for endpoint, col in (
            ("cumulative_undiscounted_profit", "total_profit"),
            ("total_lost_sales_units", "total_lost_sales"),
        ):
            summaries.append(
                EndpointSummary(
                    arm=str(arm),
                    endpoint=endpoint,
                    value=equal_weighted_mean(
                        group,
                        value_col=col,
                        strata=("family", "information_condition"),
                        weights=weights,
                    ),
                    n_units=int(group["independent_unit_id"].nunique()),
                )
            )
    return tuple(summaries)
