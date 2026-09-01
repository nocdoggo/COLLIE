"""Period and episode accounting, mirroring the audited evaluator exactly.

Every number this module produces has a line-for-line counterpart in
``eval/evaluate_results.py``. The mapping, from ``docs/env_contract.md`` §3 step 4:

===========================  ==========================================================
this module                  reference
===========================  ==========================================================
:func:`clamp_order`          ``order_quantity = max(0, int(order_quantity))``
:func:`settle_period`        ``units_sold = min(demand, on_hand)``; ``on_hand -= sold``
                             ``period_profit = p * units_sold``
                             ``period_holding = h * on_hand``  ← **ending** inventory
:func:`aggregate_episode`    ``total_reward = total_profit - total_holding_cost``
                             ``perfect = profit[0] * total_demand``
                             ``normalized = max(0, reward / perfect)``
===========================  ==========================================================

Holding is charged on **ending** inventory, so units that arrive and sell within the same period
are never held. Unmet demand is lost, never backordered.

Exact float equality with the reference is attainable, not merely approximate, because the audit
confirmed every demand, profit, and holding-cost cell in all 1,320 instances is integer-valued.
Orders are integers after :func:`clamp_order`, so on-hand stays integral and every product and
sum here is exact in float64. :func:`aggregate_episode` therefore promises exact agreement, and
``tests/test_accounting_equivalence.py`` holds it to a maximum absolute difference of ``0.0``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from collie.contracts import (
    AnalysisClass,
    EpisodeResult,
    EpisodeSpec,
    RunRecord,
)

__all__ = ["PeriodAccounting", "aggregate_episode", "clamp_order", "settle_period"]


@dataclass(frozen=True, slots=True)
class PeriodAccounting:
    """Outcome of demand resolution and reward computation for one period."""

    units_sold: float
    lost_sales: float
    on_hand_end: float
    period_profit: float
    period_holding: float


def clamp_order(raw_quantity: float, order_cap: float) -> float:
    """Apply the benchmark's own clamp, then our registered cap.

    ``max(0, int(q))`` is upstream's, and truncates toward zero, so ``2.9 -> 2`` and
    ``-2.9 -> 0``. The cap is **ours**: the benchmark imposes none
    (``docs/env_contract.md`` §2.3), so it is registered in ``prereg/prereg_v1.yaml`` and
    defaults to ``inf`` wherever equivalence with the official pipeline is being tested.
    """
    if math.isnan(raw_quantity):
        raise ValueError("order quantity is NaN; a controller must return a number")
    if raw_quantity == math.inf:
        raise ValueError(
            "order quantity is +inf; a controller must return a finite number "
            "(an unbounded cap does not license an unbounded order)"
        )
    quantity = float(max(0, int(raw_quantity)))
    return min(quantity, order_cap)


def settle_period(
    *,
    on_hand_after_arrivals: float,
    demand: float,
    profit_per_unit: float,
    holding_cost_per_unit: float,
) -> PeriodAccounting:
    """Resolve demand and compute the period reward (reference steps 3 and 4)."""
    units_sold = min(demand, on_hand_after_arrivals)
    on_hand_end = on_hand_after_arrivals - units_sold
    return PeriodAccounting(
        units_sold=units_sold,
        lost_sales=demand - units_sold,
        on_hand_end=on_hand_end,
        period_profit=profit_per_unit * units_sold,
        period_holding=holding_cost_per_unit * on_hand_end,
    )


def aggregate_episode(
    spec: EpisodeSpec,
    *,
    arm_id: str,
    records: Sequence[RunRecord],
    perfect_foresight_profit_per_unit: float,
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY,
    calls: tuple = (),
) -> EpisodeResult:
    """Aggregate per-period records into the episode score.

    ``perfect_foresight_profit_per_unit`` is the **first row's** profit, which is what
    ``compute_perfect_foresight_reward`` reads. Passing it in rather than taking it from
    ``spec`` keeps the equivalence argument explicit: if a future instance ever varied profit
    within an episode, this is the single place where our number and the official number would
    part company, and the caller would have to say so.
    """
    total_profit = 0.0
    total_holding = 0.0
    total_sold = 0.0
    total_demand = 0.0
    total_lost = 0.0
    for record in records:
        total_profit += record.period_profit
        total_holding += record.period_holding
        total_sold += record.units_sold
        total_demand += record.demand
        total_lost += record.lost_sales

    total_reward = total_profit - total_holding
    perfect_foresight = perfect_foresight_profit_per_unit * total_demand
    normalized = max(0.0, total_reward / perfect_foresight) if perfect_foresight > 0 else 0.0

    return EpisodeResult(
        episode_id=spec.episode_id,
        arm_id=arm_id,
        total_profit=total_profit,
        total_holding_cost=total_holding,
        total_reward=total_reward,
        total_demand=total_demand,
        total_sold=total_sold,
        total_lost_sales=total_lost,
        perfect_foresight=perfect_foresight,
        normalized_reward=normalized,
        records=tuple(records),
        calls=calls,
        independent_unit_id=spec.independent_unit_id,
        split=spec.split,
        family=spec.family,
        information_condition=spec.information_condition,
        analysis_class=analysis_class,
    )
