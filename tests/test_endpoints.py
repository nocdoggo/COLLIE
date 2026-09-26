from __future__ import annotations

import pandas as pd
import pytest

from collie.contracts import EpisodeResult, InformationCondition, ShockFamily, Split
from collie.eval.endpoints import (
    aggregate_primary_endpoints,
    compatibility_summaries,
    equal_weighted_mean,
    stratum_weighted_endpoints,
    weighted_metric_by_field,
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


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"arm": "a", "family": "demand_level", "split": "dev", "value": 10.0},
            {"arm": "a", "family": "temporary_pulse", "split": "cal", "value": 30.0},
        ]
    )


def test_weighted_metric_by_field_requires_its_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        weighted_metric_by_field(frame(), value_col="value", field="absent", weights={"dev": 1.0})


def test_weighted_metric_by_field_requires_populated_strata() -> None:
    with pytest.raises(ValueError, match="no populated strata"):
        weighted_metric_by_field(frame(), value_col="value", field="split", weights={"test": 1.0})


def test_equal_weighted_mean_requires_its_columns() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        equal_weighted_mean(
            frame(),
            value_col="value",
            strata=("family", "absent"),
            weights={("demand_level", "x"): 1.0},
        )


def test_equal_weighted_mean_wraps_scalar_keys_and_checks_arity() -> None:
    with pytest.raises(ValueError, match="does not match strata"):
        equal_weighted_mean(
            frame(),
            value_col="value",
            strata=("family", "split"),
            weights={"demand_level": 1.0},
        )
    assert (
        equal_weighted_mean(
            frame(), value_col="value", strata=("family",), weights={"demand_level": 1.0}
        )
        == 10.0
    )


def test_equal_weighted_mean_skips_unpopulated_strata() -> None:
    value = equal_weighted_mean(
        frame(),
        value_col="value",
        strata=("family",),
        weights={"demand_level": 0.5, "absent_family": 0.5},
    )
    assert value == 10.0


def test_equal_weighted_mean_requires_at_least_one_populated_stratum() -> None:
    with pytest.raises(ValueError, match="no populated strata"):
        equal_weighted_mean(
            frame(),
            value_col="value",
            strata=("family",),
            weights={"absent_family": 1.0},
        )
