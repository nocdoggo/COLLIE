"""Reduced and full Monte Carlo calibration entry point for Module 05."""

from __future__ import annotations

import pytest

from collie.contracts import AnalysisClass
from collie.data.families.base import BaselineKind, BaselineSpec
from collie.verify.demand import run_null_calibration
from collie.verify.eprocess import ANYTIME_VALID, EMPIRICAL_ONLY


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
        horizon=50,
        tau_j=12,
        seed=20260905,
        baseline=baseline,
    )
    assert summary.rate <= summary.proposal_alpha
    assert summary.proposal_alpha == pytest.approx(summary.alpha_episode / 2.0)
    assert summary.wilson_low <= summary.rate <= summary.wilson_high
    expected_label = EMPIRICAL_ONLY if baseline.kind is BaselineKind.DEPENDENT else ANYTIME_VALID
    assert summary.validity_label == expected_label
    assert summary.analysis_class is AnalysisClass.EXPLORATORY
