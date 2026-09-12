from __future__ import annotations

import pytest

from collie.contracts import EpisodeResult, InformationCondition, ShockFamily, Split
from collie.eval.endpoints import (
    aggregate_primary_endpoints,
    compatibility_summaries,
    stratum_weighted_endpoints,
)


def result(
    arm: str,
    unit: str,
    profit: float,
    lost: float,
    *,
    family: ShockFamily | None = None,
    condition: InformationCondition | None = None,
    split: Split | None = None,
) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"e-{unit}-{arm}",
        arm_id=arm,
        total_profit=profit,
        total_holding_cost=0.0,
        total_reward=profit,
        total_demand=100.0,
        total_sold=100.0 - lost,
        total_lost_sales=lost,
        perfect_foresight=100.0,
        normalized_reward=profit / 100.0,
        independent_unit_id=unit,
        split=split,
        family=family,
        information_condition=condition,
    )


def test_primary_endpoint_means_by_arm() -> None:
    rows = aggregate_primary_endpoints(
        (
            result("a", "u1", 10.0, 2.0),
            result("a", "u2", 20.0, 4.0),
            result("b", "u1", 30.0, 1.0),
        )
    )
    values = {(row.arm, row.endpoint): row.value for row in rows}
    assert values[("a", "cumulative_undiscounted_profit")] == 15.0
    assert values[("a", "total_lost_sales_units")] == 3.0
    assert values[("b", "cumulative_undiscounted_profit")] == 30.0


def test_stratum_weighting_matches_prereg_shape() -> None:
    rows = stratum_weighted_endpoints(
        (
            result(
                "a",
                "u1",
                10.0,
                2.0,
                family=ShockFamily.DEMAND_LEVEL,
                condition=InformationCondition.NO_ALERT,
            ),
            result(
                "a",
                "u2",
                30.0,
                4.0,
                family=ShockFamily.TEMPORARY_PULSE,
                condition=InformationCondition.NO_ALERT,
            ),
        ),
        {
            ("demand_level", "no_alert"): 0.75,
            ("temporary_pulse", "no_alert"): 0.25,
        },
    )
    values = {(row.arm, row.endpoint): row.value for row in rows}
    assert values[("a", "cumulative_undiscounted_profit")] == 15.0


def test_compatibility_summaries_report_micro_and_weighted_mixture() -> None:
    rows = compatibility_summaries(
        (
            result("a", "u1", 10.0, 0.0, split=Split.DEV),
            result("a", "u2", 30.0, 0.0, split=Split.CAL),
        ),
        deployment_weights={"dev": 0.70, "cal": 0.15, "test": 0.15},
        harness="eval",
    )
    values = {(row.arm, row.metric): row for row in rows}
    assert values[("a", "official_normalized_reward_micro")].value == 0.2
    weighted = values[("a", "official_normalized_reward_split_mixture")]
    assert weighted.value == pytest.approx((0.1 * 0.70 + 0.3 * 0.15) / 0.85)
    assert weighted.harness == "eval"
