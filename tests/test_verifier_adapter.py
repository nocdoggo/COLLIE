"""The production verifier through the exact activation seam used by arm 10."""

from __future__ import annotations

import inspect

import pytest

from collie.arms.protocols import ActivationPolicy
from collie.contracts import (
    Direction,
    DurationBin,
    LifecycleState,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.verify import VerifierActivationPolicy
from collie.verify.adapter import MIN_BASELINE_PARAMETER


def _spec(
    *,
    family: ShockFamily = ShockFamily.DEMAND_LEVEL,
    stream: TargetStream = TargetStream.DEMAND,
    direction: Direction = Direction.DEMAND_UP,
    signature: str = "sig_demand_level_up",
    tau_j: int = 4,
    proposal_index: int = 1,
) -> ShockSpec:
    return ShockSpec(
        target_stream=stream,
        shock_family=family,
        direction=direction,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.TRANSIENT,
        duration_bin=DurationBin.SHORT,
        evidence_refs=(f"obs_t{tau_j}",),
        prospective_signature=signature,
        tau_j=tau_j,
        proposal_index=proposal_index,
        model_id="adapter-test",
        decoding_hash="frozen",
        prompt_hash="frozen",
    )


def _condition(policy: VerifierActivationPolicy, spec: ShockSpec) -> None:
    prefix = (100.0,) * max(spec.tau_j - 1, 0)
    arrivals = ((0.0, 0.0),) * len(prefix)
    policy.prime(prefix, arrivals)
    policy.register(spec, baseline=(100.0, 25.0))
    if spec.tau_j:
        state = policy.condition(spec.tau_j, 100.0, dispatch=0.0, receipt=0.0)
        assert state is LifecycleState.PROPOSED


def test_adapter_is_runtime_and_signature_conformant() -> None:
    policy = VerifierActivationPolicy(episode_horizon=12)
    assert isinstance(policy, ActivationPolicy)
    for method in ("register", "observe"):
        assert set(inspect.signature(getattr(type(policy), method)).parameters) == set(
            inspect.signature(getattr(ActivationPolicy, method)).parameters
        )


def test_baseline_tuple_maps_to_a_registered_baseline_spec() -> None:
    policy = VerifierActivationPolicy(episode_horizon=12)
    spec = _spec()
    policy.prime((100.0,) * 3, ((0.0, 0.0),) * 3)
    policy.register(spec, baseline=(123.0, 17.0))
    assert policy.baseline_spec is not None
    assert (policy.baseline_spec.mean, policy.baseline_spec.sd) == (123.0, 17.0)

    policy.reset()
    policy.prime((0.0,) * 3, ((0.0, 0.0),) * 3)
    policy.register(spec, baseline=(0.0, 0.0))
    assert policy.baseline_spec is not None
    assert (policy.baseline_spec.mean, policy.baseline_spec.sd) == (
        MIN_BASELINE_PARAMETER,
        MIN_BASELINE_PARAMETER,
    )


def test_demand_adapter_keeps_evidence_future_only_and_exports_validity() -> None:
    policy = VerifierActivationPolicy(episode_horizon=7)
    spec = _spec()
    _condition(policy, spec)
    with pytest.raises(ValueError, match="strictly after tau_j"):
        policy.observe(spec.tau_j, 100.0)
    for period in range(spec.tau_j + 1, 8):
        policy.observe(period, 100.0)
    assert policy.state is LifecycleState.EXPIRED
    assert policy.output_records[-1].evidence_validity_label == "anytime_valid"


@pytest.mark.parametrize(
    ("spec", "expected_label"),
    [
        (
            _spec(
                family=ShockFamily.TRANSIT_PAUSE,
                stream=TargetStream.ARRIVAL,
                direction=Direction.ARRIVAL_INTERRUPTED,
                signature="sig_arrival_stall",
            ),
            "anytime_valid_collie_shockspec_only",
        ),
        (
            _spec(
                family=ShockFamily.COMPOUND,
                stream=TargetStream.BOTH,
                direction=Direction.MIXED,
                signature="sig_compound",
            ),
            "anytime_valid_via_splitting",
        ),
    ],
)
def test_arrival_and_compound_adapters_consume_all_required_channels(
    spec: ShockSpec, expected_label: str
) -> None:
    policy = VerifierActivationPolicy(episode_horizon=7)
    _condition(policy, spec)
    with pytest.raises(ValueError, match="requires dispatch and receipt"):
        policy.observe(5, 100.0)
    for period in range(5, 8):
        policy.observe(period, 100.0, dispatch=0.0, receipt=0.0)
    assert policy.output_records[-1].evidence_validity_label == expected_label


def test_adapter_rejects_incomplete_or_invalid_registration_context() -> None:
    policy = VerifierActivationPolicy(episode_horizon=12)
    spec = _spec()
    with pytest.raises(ValueError, match="requires baseline"):
        policy.register(spec)
    with pytest.raises(ValueError, match="finite and non-negative"):
        policy.register(spec, baseline=(100.0, float("nan")))
    with pytest.raises(ValueError, match="expected 3, got 0"):
        policy.register(spec, baseline=(100.0, 25.0))
    with pytest.raises(RuntimeError, match="register a proposal"):
        policy.observe(5, 100.0)


def test_adapter_conditioning_guards_and_terminal_short_circuit() -> None:
    policy = VerifierActivationPolicy(episode_horizon=7)
    spec = _spec()
    with pytest.raises(ValueError, match="equal length"):
        policy.prime((100.0,), ())
    policy.prime((100.0,) * 3, ((0.0, 0.0),) * 3)
    policy.register(spec, baseline=(100.0, 25.0))
    with pytest.raises(RuntimeError, match="finish conditioning"):
        policy.prime((100.0,) * 3, ((0.0, 0.0),) * 3)
    with pytest.raises(ValueError, match="must equal tau_j"):
        policy.condition(3, 100.0, dispatch=0.0, receipt=0.0)
    with pytest.raises(ValueError, match="requires both"):
        policy.condition(4, 100.0)
    policy.condition(4, 100.0, dispatch=0.0, receipt=0.0)
    with pytest.raises(RuntimeError, match="already conditioned"):
        policy.condition(4, 100.0, dispatch=0.0, receipt=0.0)
    for period in range(5, 8):
        policy.observe(period, 100.0)
    assert policy.observe(8, 100.0) is LifecycleState.EXPIRED


def test_adapter_rejects_misaligned_arrival_prefix_and_unconditioned_evidence() -> None:
    policy = VerifierActivationPolicy(episode_horizon=12)
    spec = _spec()
    policy.prime((100.0,) * 3, ((0.0, 0.0),) * 3)
    policy._arrival_history = ()
    with pytest.raises(ValueError, match="dispatch/receipt"):
        policy.register(spec, baseline=(100.0, 25.0))

    policy.reset()
    policy.prime((100.0,) * 3, ((0.0, 0.0),) * 3)
    policy.register(spec, baseline=(100.0, 25.0))
    with pytest.raises(RuntimeError, match=r"condition\(period=tau_j"):
        policy.observe(5, 100.0)

    policy._demand_history = ()
    with pytest.raises(ValueError, match="end exactly"):
        policy._build_verifier(spec)


def test_adapter_builds_tau_zero_proposal_without_conditioning() -> None:
    policy = VerifierActivationPolicy(episode_horizon=3)
    spec = _spec(tau_j=0)
    policy.prime((), ())
    policy.register(spec, baseline=(100.0, 25.0))
    assert policy.observe(1, 100.0) is LifecycleState.PROPOSED


def test_real_adapter_runs_end_to_end_through_shockspec_arm(tmp_path) -> None:
    from dataclasses import replace

    from collie.arms.shockspec import ARM10_ARM_ID
    from collie.sim.runner import EpisodeRunner
    from tests.test_arms_shockspec import PAYLOAD, _arm, _harness, _Parser
    from tests.test_episode_runner import make_instance

    instance = make_instance(demand=(100.0,) * 8, lead_times=(0.0,) * 8)
    _, _, metered = _harness(tmp_path)
    policy = VerifierActivationPolicy(episode_horizon=8)
    arm = _arm(
        metered,
        instance,
        policy,
        arm_id=ARM10_ARM_ID,
        parser=_Parser(replace(PAYLOAD, onset_window=(0, 2))),
    )
    outcome = EpisodeRunner(instance).run(arm)
    assert outcome.decisions[4].lifecycle_state is LifecycleState.PROPOSED
    assert policy.baseline_spec is not None
    assert policy.output_records[0].reason == "proposal_frozen"
