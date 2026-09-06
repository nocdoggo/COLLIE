"""Reduced and full Monte Carlo calibration entry point for Module 05."""

from __future__ import annotations

import pytest

from collie.data.families.base import BaselineKind, BaselineSpec
from collie.verify.demand import run_null_calibration


@pytest.mark.slow
@pytest.mark.parametrize(
    "baseline",
    [
        BaselineSpec(BaselineKind.STATIONARY_IID),
        BaselineSpec(BaselineKind.SEASONAL),
        BaselineSpec(BaselineKind.OVERDISPERSED, sd=50.0),
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
    assert summary.rate <= summary.alpha_episode
    assert summary.proposal_alpha == pytest.approx(summary.alpha_episode / 2.0)
    assert summary.wilson_low <= summary.rate <= summary.wilson_high


def test_demand_dependent_null_is_excluded_from_the_formal_calibration() -> None:
    with pytest.raises(ValueError, match="latent-state filter"):
        run_null_calibration(
            replications=1,
            alpha_episode=0.05,
            horizon=50,
            tau_j=12,
            seed=20260905,
            baseline=BaselineSpec(BaselineKind.DEPENDENT),
        )
