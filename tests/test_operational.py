from __future__ import annotations

import pytest

from collie.contracts import EpisodeResult, RunRecord
from collie.eval.operational import (
    cvar10,
    episode_operational_summary,
    max_stockout_streak,
    operational_summaries,
    post_recovery_excess_inventory,
    time_to_recovery,
    worst_decile,
)


def record(period: int, demand: float, sold: float, *, on_hand_end: float = 0.0) -> RunRecord:
    return RunRecord(
        episode_id="e",
        arm_id="a",
        period=period,
        date=f"p{period}",
        on_hand_start=0.0,
        in_transit_start=0.0,
        order_quantity=0.0,
        arrivals=0.0,
        demand=demand,
        units_sold=sold,
        lost_sales=demand - sold,
        on_hand_end=on_hand_end,
        period_profit=sold,
        period_holding=0.0,
    )


def test_time_to_recovery_never_recovers_fixture() -> None:
    records = tuple(record(t, 100.0, 80.0) for t in range(1, 8))
    assert time_to_recovery(records, shock_period=2) is None


def test_time_to_recovery_double_touch_with_dip_fixture() -> None:
    sold = [100, 70, 95, 94, 96, 97, 98]
    records = tuple(record(t, 100.0, float(s)) for t, s in enumerate(sold, start=1))
    assert time_to_recovery(records, shock_period=2) == 3


def test_max_stockout_streak() -> None:
    sold = [100, 90, 80, 100, 99, 80, 100]
    records = tuple(record(t, 100.0, float(s)) for t, s in enumerate(sold, start=1))
    assert max_stockout_streak(records) == 2


def test_cvar10_uses_the_worst_decile() -> None:
    assert cvar10([1.0, 2.0, 3.0, 100.0]) == 1.0


def test_post_recovery_excess_inventory_starts_at_sustained_recovery() -> None:
    sold = [100, 70, 95, 94, 96, 97, 98]
    inventories = [10, 12, 30, 40, 50, 60, 70]
    records = tuple(
        record(t, 100.0, float(s), on_hand_end=float(inv))
        for t, (s, inv) in enumerate(zip(sold, inventories, strict=True), start=1)
    )
    assert post_recovery_excess_inventory(records, shock_period=2, baseline_inventory=10.0) == 50.0


def test_operational_summaries_group_by_arm() -> None:
    result = EpisodeResult(
        episode_id="e",
        arm_id="a",
        total_profit=10.0,
        total_holding_cost=1.0,
        total_reward=9.0,
        total_demand=100.0,
        total_sold=95.0,
        total_lost_sales=5.0,
        perfect_foresight=100.0,
        normalized_reward=0.09,
        records=(record(1, 100.0, 95.0),),
        independent_unit_id="u",
    )
    rows = operational_summaries((result,))
    values = {(row.arm, row.metric): row.value for row in rows}
    assert values[("a", "fill_rate")] == 0.95
    assert values[("a", "lost_sales_units")] == 5.0


def test_operational_summaries_include_recovery_inventory_when_shock_period_known() -> None:
    sold = [100, 70, 95, 94, 96, 97, 98]
    records = tuple(
        record(t, 100.0, float(s), on_hand_end=20.0) for t, s in enumerate(sold, start=1)
    )
    result = EpisodeResult(
        episode_id="e",
        arm_id="a",
        total_profit=10.0,
        total_holding_cost=1.0,
        total_reward=9.0,
        total_demand=100.0,
        total_sold=95.0,
        total_lost_sales=5.0,
        perfect_foresight=100.0,
        normalized_reward=0.09,
        records=records,
        independent_unit_id="u",
    )
    rows = operational_summaries((result,), shock_periods={"e": 2}, baseline_inventory={"e": 10.0})
    values = {(row.arm, row.metric): row.value for row in rows}
    assert values[("a", "time_to_recovery")] == 3.0
    assert values[("a", "post_recovery_excess_inventory")] == 10.0


def test_worst_decile_of_empty_input_is_empty() -> None:
    assert worst_decile(()) == ()


def test_cvar10_rejects_empty_sequences() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        cvar10(())


def test_time_to_recovery_requires_a_positive_sustain_window() -> None:
    with pytest.raises(ValueError, match="sustain must be positive"):
        time_to_recovery((record(1, 100.0, 100.0),), shock_period=0, sustain=0)


def test_post_recovery_excess_inventory_is_none_when_never_recovered() -> None:
    records = tuple(record(t, 100.0, 80.0, on_hand_end=20.0) for t in range(1, 8))
    assert post_recovery_excess_inventory(records, shock_period=2) is None


def test_episode_operational_summary_reports_period_level_metrics() -> None:
    sold = [100, 70, 95, 94, 96, 97, 98]
    records = tuple(
        record(t, 100.0, float(s), on_hand_end=20.0) for t, s in enumerate(sold, start=1)
    )
    result = EpisodeResult(
        episode_id="e",
        arm_id="a",
        total_profit=10.0,
        total_holding_cost=1.0,
        total_reward=9.0,
        total_demand=100.0,
        total_sold=95.0,
        total_lost_sales=5.0,
        perfect_foresight=100.0,
        normalized_reward=0.09,
        records=records,
        independent_unit_id="u",
    )
    summary = episode_operational_summary(result, shock_period=2)
    assert summary["fill_rate"] == 0.95
    assert summary["lost_sales_units"] == 5.0
    assert summary["holding_cost"] == 1.0
    assert summary["max_stockout_streak"] == 6
    assert summary["time_to_recovery"] == 3
    assert summary["post_recovery_excess_inventory"] == 20.0
