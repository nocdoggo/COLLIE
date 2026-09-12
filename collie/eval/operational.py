"""Operational metrics computed directly from episode records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from collie.contracts import EpisodeResult, RunRecord

__all__ = [
    "OperationalSummary",
    "cvar10",
    "max_stockout_streak",
    "operational_summaries",
    "post_recovery_excess_inventory",
    "time_to_recovery",
    "worst_decile",
]


@dataclass(frozen=True, slots=True)
class OperationalSummary:
    arm: str
    metric: str
    value: float
    n_episodes: int


def worst_decile(values: Sequence[float]) -> tuple[float, ...]:
    if not values:
        return ()
    ordered = tuple(sorted(float(v) for v in values))
    n = max(1, int(np.ceil(len(ordered) * 0.10)))
    return ordered[:n]


def cvar10(values: Sequence[float]) -> float:
    decile = worst_decile(values)
    if not decile:
        raise ValueError("cannot compute CVaR10 over an empty sequence")
    return float(np.mean(decile))


def max_stockout_streak(records: Sequence[RunRecord]) -> int:
    longest = 0
    current = 0
    for record in records:
        if record.lost_sales > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def time_to_recovery(
    records: Sequence[RunRecord], *, shock_period: int, threshold: float = 0.95, sustain: int = 3
) -> int | None:
    """First post-shock period starting a sustained fill-rate recovery window."""
    if sustain < 1:
        raise ValueError("sustain must be positive")
    post = [record for record in records if record.period > shock_period]
    for idx in range(0, len(post) - sustain + 1):
        window = post[idx : idx + sustain]
        ok = all(_period_fill_rate(record) >= threshold for record in window)
        if ok:
            return window[0].period - shock_period
    return None


def post_recovery_excess_inventory(
    records: Sequence[RunRecord], *, shock_period: int, baseline_inventory: float = 0.0
) -> float | None:
    delay = time_to_recovery(records, shock_period=shock_period)
    if delay is None:
        return None
    first_period = shock_period + delay
    inventories = [r.on_hand_end for r in records if r.period >= first_period]
    if not inventories:
        return None
    return float(np.mean(inventories) - baseline_inventory)


def _period_fill_rate(record: RunRecord) -> float:
    return record.units_sold / record.demand if record.demand > 0 else 1.0


def episode_operational_summary(
    result: EpisodeResult, *, shock_period: int
) -> dict[str, float | int | None]:
    return {
        "fill_rate": result.fill_rate,
        "lost_sales_units": result.total_lost_sales,
        "holding_cost": result.total_holding_cost,
        "max_stockout_streak": max_stockout_streak(result.records),
        "time_to_recovery": time_to_recovery(result.records, shock_period=shock_period),
        "post_recovery_excess_inventory": post_recovery_excess_inventory(
            result.records, shock_period=shock_period
        ),
    }


def operational_summaries(
    results: Sequence[EpisodeResult],
    *,
    shock_periods: Mapping[str, int] | None = None,
    baseline_inventory: Mapping[str, float] | None = None,
) -> tuple[OperationalSummary, ...]:
    """Aggregate operational metrics by arm from stored episode records."""
    shock_periods = shock_periods or {}
    baseline_inventory = baseline_inventory or {}
    by_arm: dict[str, list[EpisodeResult]] = {}
    for result in results:
        by_arm.setdefault(result.arm_id, []).append(result)

    summaries: list[OperationalSummary] = []
    for arm, group in sorted(by_arm.items()):
        profits = [result.total_profit for result in group]
        summaries.extend(
            [
                OperationalSummary(arm, "cvar10_profit", cvar10(profits), len(group)),
                OperationalSummary(arm, "worst_decile_profit", min(profits), len(group)),
                OperationalSummary(
                    arm,
                    "fill_rate",
                    float(np.mean([result.fill_rate for result in group])),
                    len(group),
                ),
                OperationalSummary(
                    arm,
                    "lost_sales_units",
                    float(np.mean([result.total_lost_sales for result in group])),
                    len(group),
                ),
                OperationalSummary(
                    arm,
                    "holding_cost",
                    float(np.mean([result.total_holding_cost for result in group])),
                    len(group),
                ),
                OperationalSummary(
                    arm,
                    "max_stockout_streak",
                    float(np.mean([max_stockout_streak(result.records) for result in group])),
                    len(group),
                ),
            ]
        )
        recoveries = [
            time_to_recovery(result.records, shock_period=shock_periods[result.episode_id])
            for result in group
            if result.episode_id in shock_periods
        ]
        recovery_values = [value for value in recoveries if value is not None]
        if recovery_values:
            summaries.append(
                OperationalSummary(
                    arm, "time_to_recovery", float(np.mean(recovery_values)), len(recovery_values)
                )
            )
        excess_inventory = [
            post_recovery_excess_inventory(
                result.records,
                shock_period=shock_periods[result.episode_id],
                baseline_inventory=baseline_inventory.get(result.episode_id, 0.0),
            )
            for result in group
            if result.episode_id in shock_periods
        ]
        excess_values = [value for value in excess_inventory if value is not None]
        if excess_values:
            summaries.append(
                OperationalSummary(
                    arm,
                    "post_recovery_excess_inventory",
                    float(np.mean(excess_values)),
                    len(excess_values),
                )
            )
    return tuple(summaries)
