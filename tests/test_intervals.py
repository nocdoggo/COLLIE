from __future__ import annotations

import pytest

from collie.contracts import AnalysisClass, EpisodeResult, InformationCondition, ShockFamily
from collie.eval.intervals import (
    bootstrap_paired_interval,
    holm_adjust,
    paired_differences,
    paired_interval,
    paired_randomization_pvalue,
    stratum_weighted_paired_interval,
    wilcoxon_signed_rank_pvalue,
)


def result(
    arm: str,
    unit: str,
    profit: float,
    *,
    family: ShockFamily = ShockFamily.DEMAND_LEVEL,
    condition: InformationCondition = InformationCondition.NO_ALERT,
    confirmatory: bool = True,
) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"e-{unit}-{arm}",
        arm_id=arm,
        total_profit=profit,
        total_holding_cost=0.0,
        total_reward=profit,
        total_demand=100.0,
        total_sold=100.0,
        total_lost_sales=0.0,
        perfect_foresight=100.0,
        normalized_reward=profit / 100.0,
        independent_unit_id=unit,
        family=family,
        information_condition=condition,
        analysis_class=(AnalysisClass.CONFIRMATORY if confirmatory else AnalysisClass.EXPLORATORY),
    )


def test_paired_differences_align_on_independent_unit() -> None:
    diffs = paired_differences(
        (
            result("t", "u1", 12.0),
            result("c", "u1", 10.0),
            result("t", "u2", 9.0),
            result("c", "u2", 8.0),
        ),
        treatment="t",
        control="c",
        endpoint="cumulative_undiscounted_profit",
    )
    assert diffs == (2.0, 1.0)


def test_paired_interval_reports_units_and_ci() -> None:
    interval = paired_interval(
        (
            result("t", "u1", 12.0),
            result("c", "u1", 10.0),
            result("t", "u2", 9.0),
            result("c", "u2", 8.0),
        ),
        treatment="t",
        control="c",
        endpoint="cumulative_undiscounted_profit",
    )
    assert interval.estimate == 1.5
    assert interval.n_units == 2
    assert interval.ci_low < interval.estimate < interval.ci_high


def test_paired_interval_refuses_duplicate_confirmatory_unit_rows() -> None:
    with pytest.raises(ValueError, match="more than one row"):
        paired_differences(
            (
                result("t", "u1", 12.0),
                result("t", "u1", 13.0),
                result("c", "u1", 10.0),
            ),
            treatment="t",
            control="c",
            endpoint="cumulative_undiscounted_profit",
        )


def test_stratum_weighted_paired_interval_uses_registered_weights() -> None:
    interval = stratum_weighted_paired_interval(
        (
            result("t", "u1", 12.0, family=ShockFamily.DEMAND_LEVEL),
            result("c", "u1", 10.0, family=ShockFamily.DEMAND_LEVEL),
            result("t", "u2", 110.0, family=ShockFamily.SHIPMENT_LOSS),
            result("c", "u2", 100.0, family=ShockFamily.SHIPMENT_LOSS),
            result("t", "u3", 210.0, family=ShockFamily.SHIPMENT_LOSS),
            result("c", "u3", 200.0, family=ShockFamily.SHIPMENT_LOSS),
        ),
        treatment="t",
        control="c",
        endpoint="cumulative_undiscounted_profit",
        weights={
            (ShockFamily.DEMAND_LEVEL.value, InformationCondition.NO_ALERT.value): 0.5,
            (ShockFamily.SHIPMENT_LOSS.value, InformationCondition.NO_ALERT.value): 0.5,
        },
    )
    assert interval.estimate == 6.0
    assert interval.n_units == 3


def test_paired_randomization_pvalue_is_two_sided_exact_for_small_samples() -> None:
    assert paired_randomization_pvalue((1.0, 1.0)) == 0.5
    assert paired_randomization_pvalue((0.0, 0.0)) == 1.0


def test_wilcoxon_signed_rank_pvalue_handles_all_zero_differences() -> None:
    assert wilcoxon_signed_rank_pvalue((0.0, 0.0)) == 1.0


def test_bootstrap_paired_interval_resamples_unit_differences() -> None:
    low, high = bootstrap_paired_interval((1.0, 2.0, 3.0), resamples=500, seed=7)
    assert 1.0 <= low <= 2.0
    assert 2.0 <= high <= 3.0


def test_holm_adjust_preserves_monotone_step_down_order() -> None:
    adjusted = holm_adjust({"b": 0.04, "a": 0.01, "c": 0.03})
    assert adjusted == {"a": 0.03, "c": 0.06, "b": 0.06}


def test_paired_differences_rejects_an_unsupported_endpoint() -> None:
    with pytest.raises(ValueError, match="unsupported paired endpoint"):
        paired_differences(
            (result("t", "u1", 12.0), result("c", "u1", 10.0)),
            treatment="t",
            control="c",
            endpoint="holding_cost",
        )


def test_paired_differences_requires_complete_units() -> None:
    with pytest.raises(ValueError, match="no complete independent units"):
        paired_differences(
            (result("t", "u1", 12.0), result("c", "u2", 10.0)),
            treatment="t",
            control="c",
            endpoint="cumulative_undiscounted_profit",
        )


def test_paired_randomization_pvalue_rejects_empty_sequences() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        paired_randomization_pvalue(())


def test_paired_randomization_pvalue_uses_the_normal_path_beyond_twenty_units() -> None:
    differences = tuple(float(index % 5 - 2) for index in range(21))
    pvalue = paired_randomization_pvalue(differences)
    assert 0.0 < pvalue < 1.0


def test_paired_randomization_pvalue_handles_zero_variance_large_samples() -> None:
    assert paired_randomization_pvalue((3.0,) * 21) == 0.0
    assert paired_randomization_pvalue((0.0,) * 21) == 1.0


def test_wilcoxon_signed_rank_pvalue_averages_tied_ranks() -> None:
    tied = wilcoxon_signed_rank_pvalue((1.0, -1.0, 2.0))
    untied = wilcoxon_signed_rank_pvalue((1.0, -2.0, 3.0))
    assert 0.0 < tied < 1.0
    assert tied != untied


def test_bootstrap_paired_interval_rejects_empty_sequences() -> None:
    with pytest.raises(ValueError, match="empty sequence"):
        bootstrap_paired_interval(())


def test_bootstrap_paired_interval_requires_positive_resamples() -> None:
    with pytest.raises(ValueError, match="resamples must be positive"):
        bootstrap_paired_interval((1.0, 2.0), resamples=0)


def test_paired_interval_collapses_to_the_estimate_for_one_unit() -> None:
    interval = paired_interval(
        (result("t", "u1", 12.0), result("c", "u1", 10.0)),
        treatment="t",
        control="c",
        endpoint="cumulative_undiscounted_profit",
    )
    assert interval.estimate == 2.0
    assert interval.ci_low == interval.ci_high == 2.0
    assert interval.n_units == 1


def test_stratum_weighted_interval_rejects_an_unsupported_endpoint() -> None:
    with pytest.raises(ValueError, match="unsupported paired endpoint"):
        stratum_weighted_paired_interval(
            (result("t", "u1", 12.0), result("c", "u1", 10.0)),
            treatment="t",
            control="c",
            endpoint="holding_cost",
            weights={},
        )


def test_stratum_weighted_interval_wraps_scalar_keys_and_checks_arity() -> None:
    with pytest.raises(ValueError, match="does not match strata"):
        stratum_weighted_paired_interval(
            (result("t", "u1", 12.0), result("c", "u1", 10.0)),
            treatment="t",
            control="c",
            endpoint="cumulative_undiscounted_profit",
            weights={"demand_level": 1.0},
        )


def test_stratum_weighted_interval_requires_registered_stratum_columns() -> None:
    with pytest.raises(ValueError, match="missing stratum column"):
        stratum_weighted_paired_interval(
            (result("t", "u1", 12.0), result("c", "u1", 10.0)),
            treatment="t",
            control="c",
            endpoint="cumulative_undiscounted_profit",
            weights={("demand_level",): 1.0},
            strata=("absent_column",),
        )


def test_stratum_weighted_interval_skips_unpopulated_and_unpaired_strata() -> None:
    interval = stratum_weighted_paired_interval(
        (
            result("t", "u1", 12.0, family=ShockFamily.DEMAND_LEVEL),
            result("c", "u1", 10.0, family=ShockFamily.DEMAND_LEVEL),
            result("t", "u2", 20.0, family=ShockFamily.SHIPMENT_LOSS),
            result("c", "u3", 20.0, family=ShockFamily.SHIPMENT_LOSS),
            result("t", "u4", 5.0, family=ShockFamily.TEMPORARY_PULSE),
        ),
        treatment="t",
        control="c",
        endpoint="cumulative_undiscounted_profit",
        weights={
            (ShockFamily.DEMAND_LEVEL.value, InformationCondition.NO_ALERT.value): 0.25,
            (ShockFamily.SHIPMENT_LOSS.value, InformationCondition.NO_ALERT.value): 0.25,
            (ShockFamily.TEMPORARY_PULSE.value, InformationCondition.NO_ALERT.value): 0.25,
            (ShockFamily.LEAD_TIME_SHIFT.value, InformationCondition.NO_ALERT.value): 0.25,
        },
    )
    assert interval.estimate == 2.0
    assert interval.n_units == 1


def test_stratum_weighted_interval_requires_a_populated_stratum() -> None:
    with pytest.raises(ValueError, match="no complete populated strata"):
        stratum_weighted_paired_interval(
            (result("t", "u1", 12.0), result("c", "u1", 10.0)),
            treatment="t",
            control="c",
            endpoint="cumulative_undiscounted_profit",
            weights={(ShockFamily.SHIPMENT_LOSS.value, InformationCondition.NO_ALERT.value): 1.0},
        )
