"""Invented-data tests of conditional machine-reference workload arithmetic."""

from dataclasses import replace

import pytest

from analysis.coling.followup.execution import PICOS_PER_DOLLAR
from analysis.coling.followup.workload import (
    ExtraPilotCalls, ReferenceBatches, ReferencePilot, RequestCostBounds, StudySize, plan_workload,
)


FULL = StudySize(100, 50, 80)
REDUCED = StudySize(60, 30, 50)
HYBRID = StudySize(60, 30, 80)
ILLUSTRATIVE_BATCHES = ReferenceBatches(10, 10, 2)
ILLUSTRATIVE_PILOT = ReferencePilot(12, 12, 3)
REFERENCE_LANES = ("M1", "M2", "MADJ")


def row(workload, stage, lane):
    return next(item for item in workload.rows if item.stage == stage and item.lane == lane)


def test_full_package_counts_every_reference_pass_and_worst_adjudication():
    plan = plan_workload(FULL, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=16)
    tested = sum(item.first_attempts for item in plan.rows if item.lane in {"T1", "T2"})
    references = sum(item.first_attempts for item in plan.rows if item.lane in {"M1", "M2", "MADJ"})
    assert (tested, references, plan.first_attempts) == (1180, 204, 1384)
    assert row(plan, "N", "MADJ").first_attempts == 10
    assert row(plan, "C_absent", "M1").first_attempts == 5
    assert row(plan, "C_specified", "M1").first_attempts == 5
    role = row(plan, "R", "M2")
    assert (role.unit, role.units, role.batch_size, role.first_attempts) == ("four_variant_seed", 80, 2, 40)
    assert row(plan, "R_four_variants", "T1").first_attempts == 320
    assert plan.planned_attempts_with_quota == 1400 and plan.fits_attempt_ceiling_with_quota
    assert plan.attempts_if_every_request_retries == 2768 and not plan.fits_if_every_request_retries
    assert plan.shared_retry_quota_required
    assert dict(plan.pilot_first_attempts_by_lane) == {"T1": 20, "T2": 20, "M1": 8, "M2": 8, "MADJ": 8}
    assert plan.fits_pilot_return_ceiling_if_all_return
    assert plan.fits_cost_ceiling_with_quota is None


def test_one_more_retry_overflows_the_proposed_ceiling():
    plan = plan_workload(FULL, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=17)
    assert plan.planned_attempts_with_quota == 1401 and not plan.fits_attempt_ceiling_with_quota


def test_minimal_seed_grouping_is_still_insufficient_for_full_package():
    plan = plan_workload(FULL, ReferenceBatches(1, 1, 1), retry_allowance=0)
    assert plan.first_attempts == 2020
    assert row(plan, "R", "M1").first_attempts == 80
    assert not plan.fits_attempt_ceiling_with_quota


def test_reduced_package_and_uneven_final_batch():
    plan = plan_workload(REDUCED, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=525)
    assert plan.first_attempts == 875
    assert plan.planned_attempts_with_quota == 1400
    assert row(plan, "pilot_R", "M1").first_attempts == 2
    assert row(plan, "pilot_N", "M1").first_attempts == 2
    assert not plan.fits_if_every_request_retries


def test_blind_madj_hybrid_adds_a_fourth_pass_to_every_stage_and_pilot():
    three_passes = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                                 retry_allowance=180)
    explicit_default = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                                     retry_allowance=180, blind_madj=False)
    four_passes = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                                retry_allowance=180, blind_madj=True)
    assert three_passes == explicit_default
    tested = sum(item.first_attempts for item in four_passes.rows if item.lane in {"T1", "T2"})
    references = sum(item.first_attempts for item in four_passes.rows if item.lane in REFERENCE_LANES)
    assert (tested, references, four_passes.first_attempts) == (980, 240, 1220)
    assert three_passes.first_attempts == 1160  # 980 tested + 3 * 60 reference
    assert four_passes.planned_attempts_with_quota == 1400
    assert four_passes.fits_attempt_ceiling_with_quota
    assert four_passes.attempts_if_every_request_retries == 2440
    assert not four_passes.fits_if_every_request_retries
    assert four_passes.shared_retry_quota_required
    assert dict(four_passes.pilot_first_attempts_by_lane) == {
        "T1": 20, "T2": 20, "M1": 8, "M2": 8, "MADJ": 16,
    }
    assert four_passes.fits_pilot_return_ceiling_if_all_return
    assert not any(item.stage.startswith(("blind_", "pilot_blind_")) for item in three_passes.rows)

    for prefix, expected in (
        ("", {"N": 6, "C_absent": 3, "C_specified": 3, "R": 40}),
        ("pilot_", {"N": 2, "C_absent": 2, "C_specified": 2, "R": 2}),
    ):
        for stage, attempts in expected.items():
            ordinary = [item for item in four_passes.rows
                        if item.stage == prefix + stage and item.lane in REFERENCE_LANES]
            blind = [item for item in four_passes.rows if item.stage == prefix + "blind_" + stage]
            assert len(ordinary) == 3 and {item.lane for item in ordinary} == set(REFERENCE_LANES)
            assert len(blind) == 1 and blind[0].lane == "MADJ"
            assert all(item.first_attempts == attempts for item in ordinary + blind)
            assert sum(item.first_attempts for item in ordinary + blind) == 4 * attempts
            exposed = row(four_passes, prefix + stage, "MADJ")
            assert (blind[0].unit, blind[0].units, blind[0].batch_size, blind[0].pilot) == (
                exposed.unit, exposed.units, exposed.batch_size, exposed.pilot,
            )
            assert ordinary == [item for item in three_passes.rows
                                if item.stage == prefix + stage and item.lane in REFERENCE_LANES]

    pilot_n = row(four_passes, "pilot_blind_N", "MADJ")
    pilot_r = row(four_passes, "pilot_blind_R", "MADJ")
    assert (pilot_n.units, pilot_n.batch_size, pilot_n.first_attempts) == (12, 10, 2)
    assert (pilot_r.unit, pilot_r.units, pilot_r.batch_size, pilot_r.first_attempts) == (
        "four_variant_seed", 3, 2, 2,
    )


def test_one_administrative_attempt_reduces_the_hybrid_retry_headroom():
    no_admin = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                             retry_allowance=179, blind_madj=True)
    explicit_zero = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                                  retry_allowance=179, blind_madj=True, administrative_attempts=0)
    plan = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=179, blind_madj=True, administrative_attempts=1)
    assert no_admin == explicit_zero
    assert (no_admin.model_first_attempts, no_admin.administrative_attempts) == (1220, 0)
    assert (plan.model_first_attempts, plan.administrative_attempts, plan.first_attempts) == (1220, 1, 1221)
    assert sum(item.first_attempts for item in plan.rows) == plan.first_attempts
    admin = row(plan, "administrative", "ADMIN")
    assert (admin.unit, admin.units, admin.batch_size, admin.first_attempts, admin.pilot) == (
        "attempt", 1, 1, 1, False,
    )
    assert plan.pilot_first_attempts_by_lane == no_admin.pilot_first_attempts_by_lane
    assert plan.fits_pilot_return_ceiling_if_all_return
    assert plan.planned_attempts_with_quota == 1400 and plan.fits_attempt_ceiling_with_quota
    assert plan.attempts_if_every_request_retries == 2441
    assert plan.shared_retry_quota_required
    assert plan.fits_cost_ceiling_with_quota is None

    over = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=180, blind_madj=True, administrative_attempts=1)
    assert over.planned_attempts_with_quota == 1401 and not over.fits_attempt_ceiling_with_quota


def test_blind_madj_batches_each_uneven_stage_and_pilot_separately():
    size = StudySize(11, 11, 3, primary_pilot_responses_per_model=0)
    plan = plan_workload(size, ILLUSTRATIVE_BATCHES, reference_pilot=ReferencePilot(11, 11, 3),
                         retry_allowance=0, blind_madj=True)
    assert plan.first_attempts == 176  # 112 tested + 4 * (8 evaluation + 8 pilot)
    for prefix in ("", "pilot_"):
        for stage in ("N", "C_absent", "C_specified", "R"):
            assert row(plan, prefix + "blind_" + stage, "MADJ").first_attempts == 2
            assert row(plan, prefix + stage, "MADJ").first_attempts == 2


@pytest.mark.parametrize(
    "size,tested,references,first", [(FULL, 1180, 272, 1452), (REDUCED, 740, 180, 920)],
)
def test_blind_madj_full_and_reduced_packages(size, tested, references, first):
    plan = plan_workload(size, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=0, blind_madj=True)
    assert sum(item.first_attempts for item in plan.rows if item.lane in {"T1", "T2"}) == tested
    assert sum(item.first_attempts for item in plan.rows if item.lane in REFERENCE_LANES) == references
    assert plan.first_attempts == first
    assert plan.fits_attempt_ceiling_with_quota is (first <= 1400)
    assert plan.attempts_if_every_request_retries == 2 * first
    assert not plan.fits_if_every_request_retries


def test_blind_madj_role_80_counts_all_reference_pilots_or_only_role_pilot():
    size = StudySize(0, 0, 80)
    all_pilots = plan_workload(size, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                               retry_allowance=0, blind_madj=True)
    role_pilot = plan_workload(size, ILLUSTRATIVE_BATCHES, reference_pilot=ReferencePilot(0, 0, 3),
                               retry_allowance=0, blind_madj=True)
    assert (all_pilots.first_attempts, role_pilot.first_attempts) == (872, 848)
    assert all_pilots.first_attempts - role_pilot.first_attempts == 24
    assert row(all_pilots, "N", "MADJ").first_attempts == 0
    for stage in ("N", "C_absent", "C_specified"):
        assert row(all_pilots, "pilot_blind_" + stage, "MADJ").first_attempts == 2
        assert row(role_pilot, "pilot_blind_" + stage, "MADJ").first_attempts == 0
    assert row(all_pilots, "blind_R", "MADJ").first_attempts == 40
    assert dict(all_pilots.pilot_first_attempts_by_lane)["MADJ"] == 16
    assert dict(role_pilot.pilot_first_attempts_by_lane)["MADJ"] == 4


@pytest.mark.parametrize(
    "pilot,model_first,total_first,retries",
    [(ILLUSTRATIVE_PILOT, 872, 873, 527), (ReferencePilot(0, 0, 3), 848, 849, 551)],
)
def test_role_80_with_one_administrative_attempt(pilot, model_first, total_first, retries):
    plan = plan_workload(StudySize(0, 0, 80), ILLUSTRATIVE_BATCHES, reference_pilot=pilot,
                         retry_allowance=retries, blind_madj=True, administrative_attempts=1)
    assert (plan.model_first_attempts, plan.first_attempts, plan.retry_allowance) == (
        model_first, total_first, retries,
    )
    assert plan.planned_attempts_with_quota == 1400 and plan.fits_attempt_ceiling_with_quota
    assert plan.attempts_if_every_request_retries == total_first + model_first
    assert not plan.fits_if_every_request_retries
    assert plan.administrative_attempts == 1
    over = plan_workload(StudySize(0, 0, 80), ILLUSTRATIVE_BATCHES, reference_pilot=pilot,
                         retry_allowance=retries + 1, blind_madj=True, administrative_attempts=1)
    assert over.planned_attempts_with_quota == 1401 and not over.fits_attempt_ceiling_with_quota


@pytest.mark.parametrize("pilot,model_first,total_first,retries", [
    (ReferencePilot(0, 0, 3), 880, 881, 519),
    (ILLUSTRATIVE_PILOT, 904, 905, 495),
])
def test_role_80_option_budgets_all_16_reserve_seeds_for_each_reference_stage(
    pilot, model_first, total_first, retries,
):
    plan = plan_workload(StudySize(0, 0, 80), ILLUSTRATIVE_BATCHES, reference_pilot=pilot,
                         retry_allowance=retries, blind_madj=True, administrative_attempts=1,
                         reference_reserve_role_seeds=16)
    assert (plan.model_first_attempts, plan.first_attempts, plan.planned_attempts_with_quota) == (
        model_first, total_first, 1400)
    reserve = [item for item in plan.rows if item.stage in {"reserve_R", "reserve_blind_R"}]
    assert len(reserve) == 4 and all(item.unit == "four_variant_seed" and item.units == 16
                                     and item.batch_size == 2 and item.first_attempts == 8
                                     and not item.pilot for item in reserve)
    assert {item.lane for item in reserve if item.stage == "reserve_R"} == set(REFERENCE_LANES)
    assert [item.lane for item in reserve if item.stage == "reserve_blind_R"] == ["MADJ"]
    assert sum(item.first_attempts for item in reserve) == 32
    assert sum(item.first_attempts for item in plan.rows if item.stage == "R_four_variants") == 640
    assert plan.fits_attempt_ceiling_with_quota and plan.fits_cost_ceiling_with_quota is None


@pytest.mark.parametrize("reserves,model_first,total_first,retries", [
    (0, 1012, 1013, 387), (16, 1076, 1077, 323),
])
def test_role_80_single_seed_reference_batches_with_optional_reserve_review(
    reserves, model_first, total_first, retries,
):
    plan = plan_workload(StudySize(0, 0, 80), ReferenceBatches(10, 10, 1),
                         reference_pilot=ReferencePilot(0, 0, 3), retry_allowance=retries,
                         blind_madj=True, administrative_attempts=1,
                         reference_reserve_role_seeds=reserves)
    assert (plan.model_first_attempts, plan.first_attempts, plan.planned_attempts_with_quota) == (
        model_first, total_first, 1400)
    assert row(plan, "R", "M1").first_attempts == 80
    assert row(plan, "pilot_R", "M1").first_attempts == 3
    assert row(plan, "blind_R", "MADJ").first_attempts == 80
    assert row(plan, "pilot_blind_R", "MADJ").first_attempts == 3
    if reserves:
        assert row(plan, "reserve_R", "M1").first_attempts == 16
        assert row(plan, "reserve_blind_R", "MADJ").first_attempts == 16
    assert plan.fits_attempt_ceiling_with_quota and plan.fits_cost_ceiling_with_quota is None


@pytest.mark.parametrize("bad", [True, False, -1, 17, 1.5, "16", None])
def test_role_reference_reserve_count_is_fixed_and_bounded(bad):
    with pytest.raises(ValueError):
        plan_workload(StudySize(0, 0, 80), ILLUSTRATIVE_BATCHES, retry_allowance=0,
                      reference_reserve_role_seeds=bad)
    with pytest.raises(ValueError, match="assigned role programme"):
        plan_workload(StudySize(0, 0, 0), ILLUSTRATIVE_BATCHES, retry_allowance=0,
                      reference_reserve_role_seeds=1)


def test_blind_madj_role_50_fits_even_with_one_retry_per_request():
    plan = plan_workload(StudySize(0, 0, 50), ILLUSTRATIVE_BATCHES,
                         reference_pilot=ReferencePilot(0, 0, 3), retry_allowance=548, blind_madj=True)
    assert plan.first_attempts == 548
    assert plan.planned_attempts_with_quota == plan.attempts_if_every_request_retries == 1096
    assert plan.fits_attempt_ceiling_with_quota and plan.fits_if_every_request_retries
    assert not plan.shared_retry_quota_required
    assert dict(plan.pilot_first_attempts_by_lane) == {"T1": 20, "T2": 20, "M1": 2, "M2": 2, "MADJ": 4}


@pytest.mark.parametrize("seeds,first,all_retries,all_fit", [(80, 806, 1612, False), (50, 521, 1042, True)])
def test_illustrative_role_only_scope_counts_all_variants_and_reference_pilot(seeds, first, all_retries, all_fit):
    size = StudySize(0, 0, seeds)
    pilot = ReferencePilot(0, 0, 3)
    plan = plan_workload(size, ILLUSTRATIVE_BATCHES, reference_pilot=pilot, retry_allowance=0)
    assert plan.first_attempts == first
    assert plan.attempts_if_every_request_retries == all_retries
    assert plan.fits_if_every_request_retries is all_fit
    assert row(plan, "R_four_variants", "T1").first_attempts == 4 * seeds
    assert row(plan, "R", "MADJ").first_attempts == (seeds + 1) // 2
    assert row(plan, "pilot_R", "M1").first_attempts == 2


def test_conditional_cost_counts_retries_at_highest_lane_rate_first():
    rates = RequestCostBounds("0.001", "0.003", "0.005", "0.002", "0.004")
    plan = plan_workload(FULL, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         retry_allowance=16, cost_bounds=rates)
    assert plan.first_cost_bound_picos == 3_108_000_000_000
    assert plan.retry_cost_bound_picos == 80_000_000_000
    assert plan.cost_bound_with_quota_picos == 3_188_000_000_000
    assert plan.fits_cost_ceiling_with_quota
    small_cap = plan_workload(FULL, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                              retry_allowance=16, cost_bounds=rates, programme_cap_usd="3.187")
    assert not small_cap.fits_cost_ceiling_with_quota


def test_blind_and_exposed_madj_share_the_rate_for_first_attempts_and_retries():
    rates = RequestCostBounds("0.001", "0.002", "0.003", "0.004", "0.005")
    ordinary = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                             retry_allowance=180, cost_bounds=rates, programme_cap_usd="3")
    blind = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                          retry_allowance=180, blind_madj=True, cost_bounds=rates, programme_cap_usd="3")
    assert ordinary.first_cost_bound_picos == 2_190_000_000_000
    assert ordinary.retry_cost_bound_picos == 720_000_000_000
    assert ordinary.cost_bound_with_quota_picos == 2_910_000_000_000
    assert ordinary.fits_cost_ceiling_with_quota
    assert blind.first_cost_bound_picos == 2_490_000_000_000
    # All 120 MADJ attempts, then all 60 M2 attempts, are assigned retries.
    assert blind.retry_cost_bound_picos == 840_000_000_000
    assert blind.cost_bound_with_quota_picos == 3_330_000_000_000
    assert not blind.fits_cost_ceiling_with_quota


def test_administrative_cost_must_be_independent_and_known_for_total_cost_fit():
    rates = RequestCostBounds("0.001", "0.002", "0.003", "0.004", "0.005")
    kwargs = dict(reference_pilot=ILLUSTRATIVE_PILOT, retry_allowance=179, blind_madj=True,
                  cost_bounds=rates, programme_cap_usd="3.33")
    model_only = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, **kwargs)
    unknown = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, administrative_attempts=1, **kwargs)
    explicit_zero = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, administrative_attempts=1,
                                  administrative_cost_bound_usd="0", **kwargs)
    priced = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, administrative_attempts=1,
                           administrative_cost_bound_usd="0.01", **kwargs)

    assert model_only.first_cost_bound_picos == 2_490_000_000_000
    assert model_only.retry_cost_bound_picos == 836_000_000_000
    assert unknown.first_cost_bound_picos is None
    assert unknown.retry_cost_bound_picos == model_only.retry_cost_bound_picos
    assert unknown.cost_bound_with_quota_picos is None
    assert unknown.fits_cost_ceiling_with_quota is None
    assert explicit_zero.first_cost_bound_picos == model_only.first_cost_bound_picos
    assert explicit_zero.cost_bound_with_quota_picos == 3_326_000_000_000
    assert explicit_zero.fits_cost_ceiling_with_quota
    assert priced.first_cost_bound_picos == 2_500_000_000_000
    assert priced.retry_cost_bound_picos == model_only.retry_cost_bound_picos
    assert priced.cost_bound_with_quota_picos == 3_336_000_000_000
    assert not priced.fits_cost_ceiling_with_quota

    missing_model_prices = plan_workload(
        HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT, retry_allowance=179,
        blind_madj=True, administrative_attempts=1, administrative_cost_bound_usd="0.01",
    )
    assert missing_model_prices.first_cost_bound_picos is None
    assert missing_model_prices.retry_cost_bound_picos is None
    assert missing_model_prices.cost_bound_with_quota_picos is None
    assert missing_model_prices.fits_cost_ceiling_with_quota is None


def test_administrative_only_cost_rounds_up_per_attempt_and_cannot_retry():
    empty = StudySize(0, 0, 0, primary_pilot_responses_per_model=0)
    plan = plan_workload(empty, ILLUSTRATIVE_BATCHES, retry_allowance=0, administrative_attempts=3,
                         administrative_cost_bound_usd="0.000000000000000000001")
    assert (plan.model_first_attempts, plan.administrative_attempts, plan.first_attempts) == (0, 3, 3)
    assert plan.attempts_if_every_request_retries == 3
    assert not plan.shared_retry_quota_required
    assert all(count == 0 for _, count in plan.pilot_first_attempts_by_lane)
    assert plan.first_cost_bound_picos == plan.cost_bound_with_quota_picos == 3
    assert plan.retry_cost_bound_picos == 0 and plan.fits_cost_ceiling_with_quota

    unknown = plan_workload(empty, ILLUSTRATIVE_BATCHES, retry_allowance=0, administrative_attempts=3)
    assert unknown.first_cost_bound_picos is None and unknown.cost_bound_with_quota_picos is None
    assert unknown.retry_cost_bound_picos == 0 and unknown.fits_cost_ceiling_with_quota is None
    with pytest.raises(ValueError, match="one retry per model"):
        plan_workload(empty, ILLUSTRATIVE_BATCHES, retry_allowance=1, administrative_attempts=3)


def test_administrative_attempts_do_not_expand_model_retry_quota_or_retry_cost():
    size = StudySize(1, 0, 0, primary_pilot_responses_per_model=0)
    rates = RequestCostBounds("0.001", "0.002", "0.003", "0.004", "0.005")
    plan = plan_workload(size, ReferenceBatches(1, 1, 1), retry_allowance=5,
                         administrative_attempts=2, cost_bounds=rates, administrative_cost_bound_usd="0.9")
    assert (plan.model_first_attempts, plan.administrative_attempts, plan.first_attempts) == (5, 2, 7)
    assert plan.planned_attempts_with_quota == plan.attempts_if_every_request_retries == 12
    assert not plan.shared_retry_quota_required
    assert plan.first_cost_bound_picos == 1_815_000_000_000
    assert plan.retry_cost_bound_picos == 15_000_000_000  # five model attempts, no ADMIN retries
    assert plan.cost_bound_with_quota_picos == 1_830_000_000_000
    with pytest.raises(ValueError, match="one retry per model"):
        plan_workload(size, ReferenceBatches(1, 1, 1), retry_allowance=6, administrative_attempts=2)


def test_retry_allocation_spills_to_the_next_most_expensive_lane():
    size = StudySize(1, 0, 0, primary_pilot_responses_per_model=0)
    rates = RequestCostBounds("0.001", "0.002", "0.010", "0.004", "0.003")
    plan = plan_workload(size, ReferenceBatches(1, 1, 1), retry_allowance=3, cost_bounds=rates)
    assert plan.first_attempts == 5
    assert plan.retry_cost_bound_picos == 17_000_000_000  # M1 + M2 + MADJ


def test_ceil_cost_and_floor_cap_with_exact_sub_picodollar_arithmetic():
    size = StudySize(1, 0, 0, primary_pilot_responses_per_model=0)
    rates = RequestCostBounds("0.000000000000000000001", "0", "0", "0", "0")
    plan = plan_workload(size, ReferenceBatches(1, 1, 1), retry_allowance=0,
                         cost_bounds=rates, programme_cap_usd="0.000000000001999999999999999999")
    assert plan.first_cost_bound_picos == plan.programme_cap_picos == 1
    assert plan.fits_cost_ceiling_with_quota
    with pytest.raises(ValueError, match="below one picodollar"):
        plan_workload(size, ReferenceBatches(1, 1, 1), retry_allowance=0,
                      programme_cap_usd="0.0000000000009")


def test_other_pilot_and_paid_checks_count_against_all_relevant_limits():
    plan = plan_workload(REDUCED, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                         extra_pilot=ExtraPilotCalls(T1=1, M1=13), retry_allowance=0)
    assert plan.first_attempts == 889
    assert dict(plan.pilot_first_attempts_by_lane)["T1"] == 21
    assert dict(plan.pilot_first_attempts_by_lane)["M1"] == 21
    assert not plan.fits_pilot_return_ceiling_if_all_return


def test_both_madj_pilot_stages_count_toward_the_same_model_ceiling():
    at_limit = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                             extra_pilot=ExtraPilotCalls(MADJ=4), retry_allowance=0, blind_madj=True)
    over_limit = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                               extra_pilot=ExtraPilotCalls(MADJ=5), retry_allowance=0, blind_madj=True)
    ordinary = plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, reference_pilot=ILLUSTRATIVE_PILOT,
                             extra_pilot=ExtraPilotCalls(MADJ=5), retry_allowance=0)
    assert dict(at_limit.pilot_first_attempts_by_lane)["MADJ"] == 20
    assert at_limit.fits_pilot_return_ceiling_if_all_return
    assert dict(over_limit.pilot_first_attempts_by_lane)["MADJ"] == 21
    assert not over_limit.fits_pilot_return_ceiling_if_all_return
    assert dict(ordinary.pilot_first_attempts_by_lane)["MADJ"] == 13
    assert ordinary.fits_pilot_return_ceiling_if_all_return


def test_empty_design_and_every_first_request_retry():
    empty = StudySize(0, 0, 0, primary_pilot_responses_per_model=0)
    plan = plan_workload(empty, ReferenceBatches(1, 1, 1), retry_allowance=0)
    assert plan.first_attempts == 0 and plan.fits_if_every_request_retries
    assert not plan.shared_retry_quota_required
    blind_empty = plan_workload(empty, ReferenceBatches(1, 1, 1), retry_allowance=0, blind_madj=True)
    assert blind_empty.first_attempts == 0 and blind_empty.fits_if_every_request_retries
    assert row(blind_empty, "blind_N", "MADJ").first_attempts == 0
    small = plan_workload(replace(empty, natural_notices=1), ReferenceBatches(1, 1, 1), retry_allowance=5)
    assert small.first_attempts == 5 and small.attempts_if_every_request_retries == 10
    assert not small.shared_retry_quota_required


@pytest.mark.parametrize("bad", [None, 0, 1, -1, 1.0, "False", [], {}])
def test_blind_madj_must_be_an_explicit_boolean(bad):
    with pytest.raises(TypeError, match="blind_madj must be a boolean"):
        plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, retry_allowance=0, blind_madj=bad)


@pytest.mark.parametrize("bad", [True, False, -1, -999, 1.0, "1", None])
def test_administrative_attempts_must_be_nonnegative_integers(bad):
    with pytest.raises(ValueError, match="administrative_attempts"):
        plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, retry_allowance=0, administrative_attempts=bad)


@pytest.mark.parametrize("bad", ["-1", "NaN", "Infinity", "not money"])
def test_rejects_invalid_administrative_cost_bounds(bad):
    with pytest.raises(ValueError, match="administrative request cost"):
        plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, retry_allowance=0,
                      administrative_attempts=1, administrative_cost_bound_usd=bad)


@pytest.mark.parametrize("bad", [True, False, 0.1, 0])
def test_administrative_cost_bound_must_be_a_decimal_string(bad):
    with pytest.raises(TypeError, match="administrative request cost"):
        plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, retry_allowance=0,
                      administrative_attempts=1, administrative_cost_bound_usd=bad)


@pytest.mark.parametrize("bad", [True, -1, 1.0, "1"])
def test_counts_must_be_nonnegative_integers(bad):
    with pytest.raises(ValueError):
        StudySize(bad, 0, 0)
    with pytest.raises(ValueError):
        ReferencePilot(natural_notices=bad)
    with pytest.raises(ValueError):
        ExtraPilotCalls(M1=bad)


@pytest.mark.parametrize("bad", [True, 0, -1, 2.0, "2"])
def test_batch_sizes_are_positive_integers(bad):
    with pytest.raises(ValueError):
        ReferenceBatches(bad, 1, 1)


def test_rejects_attempt_cap_increase_excess_retries_and_primary_pilot_overflow():
    with pytest.raises(ValueError, match="1400"):
        plan_workload(REDUCED, ILLUSTRATIVE_BATCHES, retry_allowance=0, attempt_ceiling=1401)
    with pytest.raises(ValueError, match="one retry"):
        plan_workload(StudySize(0, 0, 0, 0), ILLUSTRATIVE_BATCHES, retry_allowance=1)
    with pytest.raises(ValueError, match="pilot"):
        StudySize(0, 0, 0, 21)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "not money"])
def test_rejects_invalid_monetary_bounds(bad):
    with pytest.raises(ValueError):
        RequestCostBounds(bad, "0", "0", "0", "0")
    with pytest.raises(ValueError):
        plan_workload(REDUCED, ILLUSTRATIVE_BATCHES, retry_allowance=0, programme_cap_usd=bad)


def test_rejects_float_costs_and_a_programme_cap_increase():
    with pytest.raises(TypeError):
        RequestCostBounds(0.1, "0", "0", "0", "0")
    with pytest.raises(ValueError, match="cannot exceed"):
        plan_workload(REDUCED, ILLUSTRATIVE_BATCHES, retry_allowance=0, programme_cap_usd="10.000000000001")
    assert PICOS_PER_DOLLAR == 10**12


@pytest.mark.parametrize("component", ["size", "batches", "pilot", "extra", "cost"])
def test_planning_revalidates_mutated_typed_inputs(component):
    size = StudySize(1, 1, 1)
    batches = ReferenceBatches(1, 1, 1)
    pilot = ReferencePilot(1, 1, 1)
    extra = ExtraPilotCalls()
    cost = RequestCostBounds("0.001", "0.001", "0.001", "0.001", "0.001")
    target, attribute, invalid = {
        "size": (size, "natural_notices", -1),
        "batches": (batches, "role_seeds", 0),
        "pilot": (pilot, "convention_notices", -1),
        "extra": (extra, "M1", -1),
        "cost": (cost, "T1", "NaN"),
    }[component]
    object.__setattr__(target, attribute, invalid)
    with pytest.raises((TypeError, ValueError)):
        plan_workload(size, batches, reference_pilot=pilot, extra_pilot=extra,
                      retry_allowance=0, cost_bounds=cost)


def test_planning_refuses_subclasses_that_bypass_input_validation():
    class UncheckedSize(StudySize):
        def __post_init__(self):
            pass

    invalid = UncheckedSize(-10000, 0, 0)
    with pytest.raises(TypeError):
        plan_workload(invalid, ILLUSTRATIVE_BATCHES, retry_allowance=0)


@pytest.mark.parametrize("bad", ["1e101", "1e-101", "0e999999999", "1" * 257])
def test_request_cost_strings_have_bounded_numeric_complexity(bad):
    with pytest.raises(ValueError, match="supported"):
        RequestCostBounds(bad, "0", "0", "0", "0")
    with pytest.raises(ValueError, match="supported"):
        plan_workload(HYBRID, ILLUSTRATIVE_BATCHES, retry_allowance=0,
                      administrative_attempts=1, administrative_cost_bound_usd=bad)
