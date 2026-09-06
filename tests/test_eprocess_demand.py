"""Module 05 CP1 acceptance tests for demand-side mixture LR e-processes."""

from __future__ import annotations

import math

import pytest

from collie.contracts import (
    Direction,
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.data.families.base import BaselineKind, BaselineSpec
from collie.verify.demand import DemandEProcess, RegisteredDemandLaw
from collie.verify.eprocess import NO_FINITE_SAMPLE_GUARANTEE, MixtureEProcess
from collie.verify.registry import CONSTRUCTIONS, resolve_construction, resolve_spec_shape


def _spec(**overrides: object) -> ShockSpec:
    payload: dict[str, object] = {
        "target_stream": TargetStream.DEMAND,
        "shock_family": ShockFamily.DEMAND_LEVEL,
        "direction": Direction.DEMAND_UP,
        "onset_window": (-1, 1),
        "magnitude_bin": MagnitudeBin.MEDIUM,
        "persistence": Persistence.PERSISTENT,
        "duration_bin": DurationBin.LONGER,
        "evidence_refs": ("obs_t10",),
        "prospective_signature": "sig_demand_level_up",
        "tau_j": 10,
        "proposal_index": 1,
        "model_id": "fake-open-weight-7b",
        "decoding_hash": "det-v1",
        "prompt_hash": "prompt-v1",
    }
    payload.update(overrides)
    return ShockSpec.model_validate(payload)


def test_no_observation_at_or_before_tau_j_enters_the_product() -> None:
    verifier = DemandEProcess.for_level_change(
        baseline=BaselineSpec(),
        direction=Direction.DEMAND_UP,
        tau_j=10,
        alpha_episode=0.05,
    )
    assert verifier.e_value == pytest.approx(1.0)
    for period in (9, 10):
        with pytest.raises(ValueError, match="future-only violation"):
            verifier.observe(period, 150.0)
        assert verifier.e_value == pytest.approx(1.0)
        assert verifier.trace == ()


def test_mixture_integral_is_exact() -> None:
    process = MixtureEProcess(tau_j=4, alpha_j=0.05, weights=(0.25, 0.75))
    first = process.update(5, (math.log(2.0), math.log(0.5)))
    assert first.e_value == pytest.approx(0.25 * 2.0 + 0.75 * 0.5)
    second = process.update(6, (math.log(3.0), math.log(4.0)))
    assert second.e_value == pytest.approx(0.25 * (2.0 * 3.0) + 0.75 * (0.5 * 4.0))


def test_registered_null_comes_from_the_contract() -> None:
    low = RegisteredDemandLaw(BaselineSpec(mean=80.0, sd=10.0))
    high = RegisteredDemandLaw(BaselineSpec(mean=140.0, sd=10.0))
    assert low.log_pmf(80.0, period=1, history=()) > high.log_pmf(80.0, period=1, history=())
    assert high.log_pmf(140.0, period=1, history=()) > low.log_pmf(140.0, period=1, history=())


def test_rounded_normal_null_is_a_probability_distribution() -> None:
    law = RegisteredDemandLaw(BaselineSpec(mean=100.0, sd=25.0))
    mass = math.fsum(math.exp(law.log_pmf(float(y), period=1, history=())) for y in range(350))
    assert mass == pytest.approx(1.0, abs=1e-11)
    assert law.log_pmf(100, period=1, history=()) == law.log_pmf(100.0, period=1, history=())


def test_overdispersed_null_is_a_probability_distribution() -> None:
    law = RegisteredDemandLaw(BaselineSpec(BaselineKind.OVERDISPERSED, sd=50.0))
    mass = math.fsum(math.exp(law.log_pmf(y, period=1, history=())) for y in range(1000))
    assert mass == pytest.approx(1.0, abs=1e-11)


def test_e_process_is_a_supermartingale_under_the_null() -> None:
    null = RegisteredDemandLaw(BaselineSpec(mean=100.0, sd=25.0))
    alternative = RegisteredDemandLaw(
        BaselineSpec(mean=100.0, sd=25.0), multiplier=1.5, active_from=1
    )
    expectation = math.fsum(
        math.exp(null.log_pmf(float(y), period=1, history=()))
        * math.exp(
            alternative.log_pmf(float(y), period=1, history=())
            - null.log_pmf(float(y), period=1, history=())
        )
        for y in range(450)
    )
    assert expectation == pytest.approx(1.0, abs=1e-10)


def test_construction_registry_resolves_both_registered_keys() -> None:
    assert len(CONSTRUCTIONS) == 7
    by_compiler = resolve_construction("demand_level_up")
    by_spec = resolve_spec_shape(by_compiler.family, by_compiler.signature)
    assert by_compiler is by_spec
    with pytest.raises(KeyError, match="unregistered predictive_model"):
        resolve_construction("model_selected_its_own_test")


def test_shockspec_compiles_to_a_fixed_demand_mixture() -> None:
    level = DemandEProcess.from_spec(
        _spec(),
        baseline=BaselineSpec(),
        alpha_episode=0.05,
        history_before_proposal=(100.0,) * 10,
    )
    assert len(level.alternatives) == 6  # two magnitudes x three registered onset positions

    pulse = DemandEProcess.from_spec(
        _spec(
            shock_family=ShockFamily.TEMPORARY_PULSE,
            prospective_signature="sig_demand_pulse",
            persistence=Persistence.TRANSIENT,
            duration_bin=DurationBin.SHORT,
        ),
        baseline=BaselineSpec(),
        alpha_episode=0.05,
    )
    assert len(pulse.alternatives) == 18  # two magnitudes x three onsets x three durations


def test_demand_verifier_rejects_an_arrival_spec() -> None:
    with pytest.raises(ValueError, match="target stream"):
        DemandEProcess.from_spec(
            _spec(
                target_stream=TargetStream.ARRIVAL,
                shock_family=ShockFamily.LEAD_TIME_SHIFT,
                direction=Direction.ARRIVAL_DELAYED,
                prospective_signature="sig_arrival_delay",
            ),
            baseline=BaselineSpec(),
            alpha_episode=0.05,
        )


def test_activation_requires_crossing_one_over_alpha() -> None:
    process = MixtureEProcess(tau_j=2, alpha_j=0.1, weights=(1.0,))
    before = process.update(3, (math.log(9.99),))
    assert not before.activated
    assert before.e_value < before.threshold
    crossing = process.update(4, (math.log(10.0 / 9.99),))
    assert crossing.e_value == pytest.approx(crossing.threshold)
    assert crossing.activated
    assert crossing.activation_period == 4
    after = process.update(5, (math.log(0.001),))
    assert after.e_value < after.threshold
    assert after.activated, "activation is a stopping event and remains recorded"
    assert after.activation_period == 4


def test_evidence_periods_must_be_strictly_increasing() -> None:
    process = MixtureEProcess(tau_j=2, alpha_j=0.1, weights=(1.0,))
    process.update(3, (0.0,))
    with pytest.raises(ValueError, match="increase strictly"):
        process.update(3, (0.0,))


def test_plug_in_variant_is_labelled_unguaranteed() -> None:
    verifier = DemandEProcess.for_level_change(
        baseline=BaselineSpec(),
        direction=Direction.DEMAND_UP,
        tau_j=2,
        alpha_episode=0.05,
        history_before_proposal=(90.0, 110.0),
        plug_in=True,
    )
    point = verifier.observe(3, 100.0)
    assert verifier.validity_label == NO_FINITE_SAMPLE_GUARANTEE
    assert point.validity_label == NO_FINITE_SAMPLE_GUARANTEE


def test_dependent_rounded_null_is_not_overclaimed() -> None:
    verifier = DemandEProcess.for_level_change(
        baseline=BaselineSpec(BaselineKind.DEPENDENT),
        direction=Direction.DEMAND_UP,
        tau_j=2,
        alpha_episode=0.05,
        history_before_proposal=(100.0, 105.0),
    )
    assert verifier.observe(3, 103.0).validity_label == NO_FINITE_SAMPLE_GUARANTEE


def test_genuine_persistent_shift_has_power() -> None:
    verifier = DemandEProcess.for_level_change(
        baseline=BaselineSpec(mean=100.0, sd=25.0),
        direction=Direction.DEMAND_UP,
        tau_j=5,
        alpha_episode=0.05,
        history_before_proposal=(100.0,) * 5,
    )
    for period in range(6, 16):
        verifier.observe(period, 175.0)
        if verifier.activated:
            break
    assert verifier.activated
