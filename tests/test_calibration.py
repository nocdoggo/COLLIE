"""Reduced and full Monte Carlo calibration entry point for Module 05."""

from __future__ import annotations

import random

import pytest

from collie.contracts import AnalysisClass, MagnitudeBin, ShockFamily
from collie.data.families.base import BaselineKind, BaselineSpec
from collie.data.families.supply import LOSS_LENGTHS
from collie.data.nullbank import PROPOSAL_PERIODS, build_nullbank
from collie.verify.arrival import (
    ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY,
    REGISTERED_LOSS_ALTERNATIVES,
    REGISTERED_NULL_LAW,
    ArrivalEProcess,
    ArrivalModel,
    run_arrival_null_calibration,
    sample_arrival_model_path,
)
from collie.verify.demand import run_null_calibration
from collie.verify.eprocess import ANYTIME_VALID, EMPIRICAL_ONLY

ARRIVAL_FAMILIES = (
    ShockFamily.LEAD_TIME_SHIFT,
    ShockFamily.SHIPMENT_LOSS,
    ShockFamily.TRANSIT_PAUSE,
)
CALIBRATION_HORIZON = build_nullbank()[0].horizon
CALIBRATION_PROPOSAL_PERIOD = PROPOSAL_PERIODS[0]


def test_arrival_calibration_rejects_an_empty_evidence_horizon() -> None:
    tau_j = CALIBRATION_PROPOSAL_PERIOD
    with pytest.raises(ValueError, match="tau_j must lie"):
        run_arrival_null_calibration(
            family=ShockFamily.SHIPMENT_LOSS,
            replications=1,
            horizon=tau_j,
            tau_j=tau_j,
        )


@pytest.mark.slow
@pytest.mark.parametrize(
    "baseline",
    [
        BaselineSpec(BaselineKind.STATIONARY_IID),
        BaselineSpec(BaselineKind.SEASONAL),
        BaselineSpec(BaselineKind.OVERDISPERSED, sd=50.0),
        BaselineSpec(BaselineKind.DEPENDENT),
    ],
    ids=lambda spec: spec.kind.value,
)
def test_demand_false_activation_calibration(
    request: pytest.FixtureRequest, baseline: BaselineSpec
) -> None:
    replications = request.config.getoption("--replications")
    summary = run_null_calibration(
        replications=replications,
        alpha_episode=0.05,
        horizon=CALIBRATION_HORIZON,
        tau_j=CALIBRATION_PROPOSAL_PERIOD,
        seed=20260905,
        baseline=baseline,
    )
    assert summary.rate <= summary.proposal_alpha
    assert summary.proposal_alpha == pytest.approx(summary.alpha_episode / 2.0)
    assert summary.wilson_low <= summary.rate <= summary.wilson_high
    expected_label = EMPIRICAL_ONLY if baseline.kind is BaselineKind.DEPENDENT else ANYTIME_VALID
    assert summary.validity_label == expected_label
    assert summary.analysis_class is AnalysisClass.EXPLORATORY


@pytest.mark.slow
@pytest.mark.parametrize("family", ARRIVAL_FAMILIES, ids=lambda family: family.value)
def test_arrival_false_activation_calibration(
    request: pytest.FixtureRequest, family: ShockFamily
) -> None:
    replications = request.config.getoption("--replications")
    summary = run_arrival_null_calibration(
        family=family,
        replications=replications,
        horizon=CALIBRATION_HORIZON,
    )
    assert summary.rate <= summary.proposal_alpha
    assert summary.proposal_alpha == pytest.approx(summary.alpha_episode / 2.0)
    assert summary.wilson_low <= summary.rate <= summary.wilson_high
    assert summary.validity_label == ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY
    assert summary.analysis_class is AnalysisClass.EXPLORATORY


def test_arrival_power_sanity_under_registered_loss_shift() -> None:
    from collie.verify.arrival import _spec_for_family

    tau_j = CALIBRATION_PROPOSAL_PERIOD
    spec = _spec_for_family(
        ShockFamily.SHIPMENT_LOSS,
        tau_j=tau_j,
        magnitude_bin=MagnitudeBin.HIGH,
    )
    horizon = CALIBRATION_HORIZON
    dispatches = (10.0,) * horizon
    shifted_model = ArrivalModel(
        baseline=REGISTERED_NULL_LAW,
        changed=REGISTERED_LOSS_ALTERNATIVES[-1],
        active_from=tau_j + 1,
        active_duration=LOSS_LENGTHS[1],
    )
    receipts = sample_arrival_model_path(shifted_model, dispatches, rng=random.Random(41))
    verifier = ArrivalEProcess.from_spec(
        spec,
        alpha_episode=0.05,
        preproposal_history=tuple(zip(dispatches[:tau_j], receipts[:tau_j], strict=True)),
    )
    for period in range(tau_j + 1, horizon + 1):
        verifier.observe(period, dispatches[period - 1], receipts[period - 1])
        if verifier.activated:
            break
    assert verifier.activated
    assert verifier.activation_period is not None
