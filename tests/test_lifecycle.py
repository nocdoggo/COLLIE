"""Complete lifecycle, supersession, and compound-accounting tests."""

from __future__ import annotations

import inspect

import pytest

from collie.contracts import (
    AnalysisClass,
    Direction,
    DurationBin,
    LifecycleState,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.verify.eprocess import EProcessPoint
from collie.verify.lifecycle import (
    RETIREMENT_CLAIM,
    CompoundVerifier,
    LifecycleManager,
    compound_alpha_allocation,
    compound_evidence_point,
    maximum_lifetime,
)


def _spec(
    *,
    proposal_index: int = 1,
    tau_j: int = 4,
    family: ShockFamily = ShockFamily.DEMAND_LEVEL,
) -> ShockSpec:
    if family is ShockFamily.COMPOUND:
        stream, direction, signature = TargetStream.BOTH, Direction.MIXED, "sig_compound"
    else:
        stream, direction, signature = (
            TargetStream.DEMAND,
            Direction.DEMAND_UP,
            "sig_demand_level_up",
        )
    return ShockSpec(
        target_stream=stream,
        shock_family=family,
        direction=direction,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.PERSISTENT,
        duration_bin=DurationBin.LONGER,
        evidence_refs=(f"obs_t{tau_j}",),
        prospective_signature=signature,
        tau_j=tau_j,
        proposal_index=proposal_index,
        model_id="test",
        decoding_hash="frozen",
        prompt_hash="frozen",
    )


def _point(
    period: int,
    *,
    e_value: float = 1.0,
    threshold: float = 40.0,
    activated: bool = False,
) -> EProcessPoint:
    return EProcessPoint(
        period=period,
        e_value=e_value,
        threshold=threshold,
        activated=activated,
        activation_period=period if activated else None,
        validity_label="anytime_valid",
        analysis_class=AnalysisClass.EXPLORATORY,
    )


def test_transition_table_coverage() -> None:
    # proposed -> active
    manager = LifecycleManager(episode_horizon=50)
    proposed = manager.propose(_spec())
    assert proposed.control_mode == "baseline_or"
    manager.consume(1, _point(5, e_value=40.0, activated=True))
    assert proposed.state is LifecycleState.ACTIVE
    assert proposed.control_mode == "verified_adaptation"

    # active -> refuted
    manager.consume(1, _point(6, e_value=0.4, threshold=40.0, activated=True))
    manager.consume(1, _point(7, e_value=0.3, threshold=40.0, activated=True))
    assert proposed.state is LifecycleState.REFUTED

    # proposed -> expired and active -> expired
    for activate in (False, True):
        manager = LifecycleManager(episode_horizon=50)
        proposal = manager.propose(_spec())
        if activate:
            manager.consume(1, _point(5, e_value=40.0, activated=True))
        manager.advance(proposal.expiry_period)
        assert proposal.state is LifecycleState.EXPIRED

    # proposed -> superseded and active -> superseded
    for activate in (False, True):
        manager = LifecycleManager(episode_horizon=50)
        predecessor = manager.propose(_spec())
        if activate:
            manager.consume(1, _point(5, e_value=40.0, activated=True))
        manager.propose(_spec(proposal_index=2, tau_j=6))
        manager.consume(2, _point(7, threshold=80.0))
        assert predecessor.state is LifecycleState.SUPERSEDED

    terminal = manager.proposals[1]
    with pytest.raises(ValueError, match="illegal lifecycle transition"):
        terminal._transition(8, LifecycleState.ACTIVE, "illegal")

    # The named checkpoint test covers the complement of the complete legal table too.
    legal = {
        LifecycleState.PROPOSED: {
            LifecycleState.ACTIVE,
            LifecycleState.EXPIRED,
            LifecycleState.SUPERSEDED,
        },
        LifecycleState.ACTIVE: {
            LifecycleState.REFUTED,
            LifecycleState.EXPIRED,
            LifecycleState.SUPERSEDED,
        },
    }
    proposal = LifecycleManager(episode_horizon=50).propose(_spec())
    for source in LifecycleState:
        for target in LifecycleState:
            if target in legal.get(source, set()):
                continue
            proposal.state = source
            with pytest.raises(ValueError, match="illegal lifecycle transition"):
                proposal._transition(8, target, "illegal-table-case")


def test_no_stale_belief() -> None:
    manager = LifecycleManager(episode_horizon=50)
    proposal = manager.propose(_spec())
    manager.consume(1, _point(5, e_value=40.0, activated=True))
    assert manager.active is proposal
    manager.advance(proposal.expiry_period)
    assert manager.active is None
    assert proposal.state is LifecycleState.EXPIRED
    assert proposal.history[-1].retirement_claim == RETIREMENT_CLAIM


def test_third_proposal_rejected() -> None:
    manager = LifecycleManager(episode_horizon=50)
    manager.propose(_spec())
    manager.propose(_spec(proposal_index=2, tau_j=6))
    with pytest.raises(ValueError, match="third proposal rejected"):
        manager.propose(_spec(proposal_index=3, tau_j=8))


def test_superseding_spec_was_itself_tested() -> None:
    manager = LifecycleManager(episode_horizon=50)
    first = manager.propose(_spec())
    manager.consume(1, _point(5, e_value=40.0, activated=True))
    second = manager.propose(_spec(proposal_index=2, tau_j=6))
    assert first.state is LifecycleState.ACTIVE
    assert second.state is LifecycleState.PROPOSED
    assert second.control_mode == "baseline_or"

    # Only the successor's own first post-commitment evidence can supersede the predecessor.
    manager.consume(2, _point(7, e_value=2.0, threshold=80.0))
    assert second.evidence_points == 1
    assert first.state is LifecycleState.SUPERSEDED
    assert second.state is LifecycleState.PROPOSED
    assert manager.active is None
    assert not hasattr(second, "supersede")


def test_marginal_product_path_is_unreachable() -> None:
    import collie.verify.lifecycle as lifecycle

    source = inspect.getsource(lifecycle)
    assert "multiply_marginal" not in source
    assert not hasattr(lifecycle, "multiply_marginal_likelihoods")
    allocation = compound_alpha_allocation(
        alpha_episode=0.05, proposal_index=1, family=ShockFamily.COMPOUND
    )
    assert allocation.construction == "separate_eprocesses_alpha_split"
    threshold = 1.0 / allocation.demand_alpha
    only_demand_crossed = compound_evidence_point(
        _point(5, e_value=threshold, threshold=threshold, activated=True),
        _point(5, e_value=1.0, threshold=threshold),
        allocation=allocation,
    )
    assert not only_demand_crossed.activated
    assert not hasattr(only_demand_crossed, "e_value")


def test_compound_uses_alpha_splitting() -> None:
    first = compound_alpha_allocation(
        alpha_episode=0.05, proposal_index=1, family=ShockFamily.COMPOUND
    )
    second = compound_alpha_allocation(
        alpha_episode=0.05, proposal_index=2, family=ShockFamily.COMPOUND
    )
    assert first.proposal_alpha == pytest.approx(0.025)
    assert first.demand_alpha == first.arrival_alpha == pytest.approx(0.0125)
    assert second.proposal_alpha == pytest.approx(0.0125)
    assert second.demand_alpha == second.arrival_alpha == pytest.approx(0.00625)
    assert first.demand_alpha + first.arrival_alpha == first.proposal_alpha
    with pytest.raises(ValueError, match="only for compound"):
        compound_alpha_allocation(
            alpha_episode=0.05, proposal_index=1, family=ShockFamily.DEMAND_LEVEL
        )


def test_compound_needs_both_separately_thresholded_streams() -> None:
    manager = LifecycleManager(episode_horizon=50)
    proposal = manager.propose(_spec(family=ShockFamily.COMPOUND))
    allocation = compound_alpha_allocation(
        alpha_episode=0.05, proposal_index=1, family=ShockFamily.COMPOUND
    )
    stream_threshold = 1.0 / allocation.demand_alpha

    one_stream = compound_evidence_point(
        _point(5, e_value=stream_threshold, threshold=stream_threshold, activated=True),
        _point(5, e_value=1.0, threshold=stream_threshold),
        allocation=allocation,
    )
    assert not one_stream.activated
    assert not hasattr(one_stream, "e_value")
    assert one_stream.validity_label == "anytime_valid_via_splitting"
    manager.consume(1, one_stream)
    assert proposal.state is LifecycleState.PROPOSED

    both_streams = compound_evidence_point(
        _point(6, e_value=stream_threshold, threshold=stream_threshold, activated=True),
        _point(6, e_value=stream_threshold, threshold=stream_threshold, activated=True),
        allocation=allocation,
    )
    manager.consume(1, both_streams)
    assert proposal.state is LifecycleState.ACTIVE
    assert proposal.activation_delay == 2
    assert proposal.history[-1].activation_delay == 2


def test_compound_spec_builds_two_real_eprocesses() -> None:
    from collie.data.families.base import BaselineSpec
    from collie.verify.arrival import REGISTERED_NULL_LAW

    spec = _spec(family=ShockFamily.COMPOUND)
    verifier = CompoundVerifier.from_spec(
        spec,
        baseline=BaselineSpec(),
        alpha_episode=0.05,
        demand_history_before_proposal=(100.0,) * spec.tau_j,
        arrival_history_before_proposal=((10.0, 0.0),) * spec.tau_j,
        null_arrival_law=REGISTERED_NULL_LAW,
    )
    assert verifier.demand.alpha_j == verifier.allocation.demand_alpha
    assert verifier.arrival.alpha_j == verifier.allocation.arrival_alpha

    manager = LifecycleManager(episode_horizon=50)
    manager.propose(spec)
    for period in range(spec.tau_j + 1, spec.tau_j + 9):
        point = verifier.observe(
            period,
            demand_value=175.0,
            dispatch_quantity=10.0,
            receipt=0.0,
        )
        manager.consume(spec.proposal_index, point)
        if manager.active is not None:
            break
    assert verifier.activated
    assert manager.active is not None


def test_confirmatory_runner_refuses_the_exploratory_flag() -> None:
    with pytest.raises(ValueError, match="confirmatory runner refuses"):
        LifecycleManager(
            episode_horizon=50,
            analysis_class=AnalysisClass.CONFIRMATORY,
            bounded_provisional=True,
        )
    exploratory = LifecycleManager(episode_horizon=50, bounded_provisional=True)
    exploratory.propose(_spec())
    assert exploratory.output_records[0].analysis_class is AnalysisClass.EXPLORATORY
    assert exploratory.output_records[0].exploratory_provisional


def test_maximum_lifetime_combines_duration_and_persistence() -> None:
    assert maximum_lifetime(DurationBin.SHORT, Persistence.TRANSIENT, remaining_horizon=46) == 3
    assert maximum_lifetime(DurationBin.MEDIUM, Persistence.TRANSIENT, remaining_horizon=46) == 8
    assert maximum_lifetime(DurationBin.SHORT, Persistence.PERSISTENT, remaining_horizon=46) == 46
    assert maximum_lifetime(DurationBin.LONGER, Persistence.PERSISTENT, remaining_horizon=46) == 46


def test_activation_requires_an_eprocess_point() -> None:
    manager = LifecycleManager(episode_horizon=50)
    manager.propose(_spec())
    with pytest.raises(TypeError, match="EProcessPoint"):
        manager.consume(1, True)  # type: ignore[arg-type]
    assert manager.proposals[1].state is LifecycleState.PROPOSED


def test_lifecycle_rejects_an_unregistered_spec_before_proposal() -> None:
    manager = LifecycleManager(episode_horizon=50)
    invalid = _spec().model_copy(update={"onset_window": (0, 0)})
    with pytest.raises(ValueError, match="unregistered onset_window"):
        manager.propose(invalid)
    assert manager.proposals == {}


def test_evidence_threshold_must_match_proposal_alpha() -> None:
    manager = LifecycleManager(episode_horizon=50)
    manager.propose(_spec())
    with pytest.raises(ValueError, match="alpha allocation"):
        manager.consume(1, _point(5, e_value=20.0, threshold=20.0, activated=True))


def test_activation_metadata_must_be_post_proposal_and_causal() -> None:
    manager = LifecycleManager(episode_horizon=50)
    manager.propose(_spec())
    invalid = EProcessPoint(
        period=5,
        e_value=40.0,
        threshold=40.0,
        activated=True,
        activation_period=4,
        validity_label="anytime_valid",
        analysis_class=AnalysisClass.EXPLORATORY,
    )
    with pytest.raises(ValueError, match="post-proposal"):
        manager.consume(1, invalid)


def test_retirement_rules_are_explicitly_outside_activation_theorem() -> None:
    manager = LifecycleManager(episode_horizon=50)
    manager.propose(_spec())
    record = manager.output_records[0]
    assert record.retirement_claim == "empirical_outside_activation_theorem"
    assert record.activation_claim == "model_conditional_anytime_valid_per_episode_false_activation"
    assert record.expiry_period == 50
    assert record.refutation_e_value == 0.5
    assert record.refutation_streak == 2
    assert record.evidence_validity_label is None
