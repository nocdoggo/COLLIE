"""Defensive verifier branches required by the module-05 100% coverage gate."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from collie.contracts import (
    AnalysisClass,
    Direction,
    DurationBin,
    LifecycleState,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    TargetStream,
)
from collie.data.families.base import BaselineKind, BaselineSpec
from collie.verify.alpha import alpha_schedule
from collie.verify.arrival import (
    ArrivalEProcess,
    ArrivalForwardFilter,
    ArrivalModel,
    ArrivalState,
    RegisteredArrivalLaw,
    _arrival_null_chunk,
    _changed_laws_for,
    _durations_for_family,
    _run_forked_chunks,
    _run_spawned_chunks,
    _wilson,
    advance_counter,
    brute_force_sequence_probability,
    run_arrival_null_calibration,
    transition_state,
)
from collie.verify.demand import (
    DemandEProcess,
    RegisteredDemandLaw,
    _log_rounded_normal_mass,
    _logdiffexp,
    _wilson_interval,
    run_null_calibration,
)
from collie.verify.demand import (
    main as demand_main,
)
from collie.verify.eprocess import EMPIRICAL_ONLY, EProcessPoint, MixtureEProcess, _logsumexp
from collie.verify.lifecycle import (
    CompoundAlphaAllocation,
    CompoundVerifier,
    LifecycleManager,
    RegisteredRetirementRules,
    compound_alpha_allocation,
    compound_demo_timeline,
    compound_evidence_point,
    maximum_lifetime,
)
from collie.verify.registry import resolve_spec
from tests.test_arrival_forward import _arrival_spec
from tests.test_eprocess_demand import _spec as demand_spec
from tests.test_lifecycle import _spec as lifecycle_spec


def test_alpha_and_eprocess_defensive_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="max_proposals must be positive"):
        alpha_schedule(0.05, max_proposals=0)
    with monkeypatch.context() as scoped:
        scoped.setattr("builtins.sum", lambda _: 1.0)
        with pytest.raises(AssertionError, match="schedule spends"):
            alpha_schedule(0.05)

    assert _logsumexp((-math.inf, -math.inf)) == -math.inf
    assert _logsumexp((math.inf, 0.0)) == math.inf
    for kwargs, message in (
        ({"tau_j": -1, "alpha_j": 0.1, "weights": (1.0,)}, "tau_j"),
        ({"tau_j": 0, "alpha_j": 1.0, "weights": (1.0,)}, "alpha_j"),
        ({"tau_j": 0, "alpha_j": 0.1, "weights": ()}, "at least one"),
        ({"tau_j": 0, "alpha_j": 0.1, "weights": (0.0, 1.0)}, "positive"),
        ({"tau_j": 0, "alpha_j": 0.1, "weights": (0.4, 0.4)}, "sum to one"),
    ):
        with pytest.raises(ValueError, match=message):
            MixtureEProcess(**kwargs)
    process = MixtureEProcess(tau_j=0, alpha_j=0.1, weights=(1.0,))
    assert process.activation_period is None
    with pytest.raises(ValueError, match="expected 1 component"):
        process.update(1, ())
    for invalid in (math.nan, math.inf):
        with pytest.raises(ValueError, match=r"never nan or \+inf"):
            process.update(1, (invalid,))


def test_demand_probability_and_constructor_guards() -> None:
    assert _logdiffexp(2.0, -math.inf) == 2.0
    assert _logdiffexp(1.0, 1.0) == -math.inf
    assert _log_rounded_normal_mass(-1.0, 1.0, 1.0) == -math.inf
    with pytest.raises(ValueError, match="standard deviation"):
        _log_rounded_normal_mass(1.0, 1.0, 0.0)

    baseline = BaselineSpec()
    with pytest.raises(ValueError, match="multiplier"):
        RegisteredDemandLaw(baseline, multiplier=0.0)
    with pytest.raises(ValueError, match="active_duration"):
        RegisteredDemandLaw(baseline, active_duration=0)
    dependent = RegisteredDemandLaw(BaselineSpec(BaselineKind.DEPENDENT))
    assert not dependent.theorem_backed
    seasonal = RegisteredDemandLaw(BaselineSpec(BaselineKind.SEASONAL))
    assert seasonal.log_pmf(100.0, period=2, history=()) < 0.0
    overdispersed = RegisteredDemandLaw(BaselineSpec(BaselineKind.OVERDISPERSED, sd=50.0))
    assert overdispersed.log_pmf(-1.0, period=1, history=()) == -math.inf
    assert overdispersed._base_log_pmf(-1.0, period=1, history=()) == -math.inf
    invalid_overdispersed = RegisteredDemandLaw(
        BaselineSpec(BaselineKind.OVERDISPERSED, mean=100.0, sd=10.0)
    )
    with pytest.raises(ValueError, match="variance greater than mean"):
        invalid_overdispersed.log_pmf(100.0, period=1, history=())
    assert RegisteredDemandLaw(baseline).log_pmf(1.5, period=1, history=()) == -math.inf

    alternative = RegisteredDemandLaw(baseline, multiplier=1.2, active_from=1)
    with pytest.raises(ValueError, match="at least one"):
        DemandEProcess(RegisteredDemandLaw(baseline), (), 0, 0.1)
    with pytest.raises(ValueError, match="more observations"):
        DemandEProcess(RegisteredDemandLaw(baseline), (alternative,), 0, 0.1, (100.0,))


def test_demand_compilation_and_calibration_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = BaselineSpec()
    down = DemandEProcess.for_level_change(
        baseline=baseline,
        direction=Direction.DEMAND_DOWN,
        tau_j=1,
        alpha_episode=0.05,
    )
    assert down.alternatives
    with pytest.raises(ValueError, match="cannot use direction"):
        DemandEProcess.for_level_change(
            baseline=baseline,
            direction=Direction.MIXED,
            tau_j=1,
            alpha_episode=0.05,
        )

    import collie.verify.demand as demand_module

    compound = demand_spec(
        target_stream=TargetStream.BOTH,
        shock_family=ShockFamily.COMPOUND,
        direction=Direction.MIXED,
        prospective_signature="sig_compound",
    )
    registered = demand_module.resolve_spec(compound)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            demand_module,
            "resolve_spec",
            lambda _: replace(registered, stream=TargetStream.DEMAND),
        )
        with pytest.raises(ValueError, match="both-stream"):
            DemandEProcess.from_spec(compound, baseline=baseline, alpha_episode=0.05)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            demand_module,
            "resolve_spec",
            lambda _: replace(registered, direction=Direction.DEMAND_UP),
        )
        with pytest.raises(ValueError, match="direction"):
            DemandEProcess.from_spec(compound, baseline=baseline, alpha_episode=0.05)
    with monkeypatch.context() as scoped:
        scoped.setattr(demand_module, "resolve_spec", lambda _: registered)
        no_window = compound.model_copy(update={"onset_window": None})
        with pytest.raises(ValueError, match="onset window"):
            DemandEProcess.from_spec(no_window, baseline=baseline, alpha_episode=0.05)

    level = demand_spec()
    level_registered = demand_module.resolve_spec(level)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            demand_module,
            "resolve_spec",
            lambda _: replace(level_registered, direction=Direction.DEMAND_DOWN),
        )
        with pytest.raises(ValueError, match="does not match"):
            DemandEProcess.from_spec(level, baseline=baseline, alpha_episode=0.05)
    with monkeypatch.context() as scoped:
        scoped.setattr(demand_module, "resolve_spec", lambda _: level_registered)
        no_window = level.model_copy(update={"onset_window": None})
        with pytest.raises(ValueError, match="onset window"):
            DemandEProcess.from_spec(no_window, baseline=baseline, alpha_episode=0.05)
        unsupported = level.model_copy(update={"shock_family": ShockFamily.SHIPMENT_LOSS})
        with pytest.raises(ValueError, match="unsupported demand"):
            DemandEProcess.from_spec(unsupported, baseline=baseline, alpha_episode=0.05)

    verifier = DemandEProcess.for_level_change(
        baseline=baseline,
        direction=Direction.DEMAND_UP,
        tau_j=0,
        alpha_episode=0.05,
    )
    assert verifier.activation_period is None
    with pytest.raises(ValueError, match="zero mass"):
        verifier.observe(1, -1.0)

    assert _wilson_interval(0, 1)[0] == 0.0
    assert _wilson_interval(1, 1)[1] == 1.0
    with pytest.raises(ValueError, match="trials must be positive"):
        _wilson_interval(0, 0)
    with pytest.raises(ValueError, match="replications"):
        run_null_calibration(replications=0, alpha_episode=0.05, horizon=5, tau_j=1, seed=1)
    with pytest.raises(ValueError, match="tau_j"):
        run_null_calibration(replications=1, alpha_episode=0.05, horizon=5, tau_j=5, seed=1)
    with pytest.raises(SystemExit):
        demand_main([])


def test_arrival_law_state_and_filter_guards() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        advance_counter(-1, paused=False)
    assert advance_counter(0, paused=False) == 0
    assert advance_counter(2, paused=True) == 2
    assert advance_counter(2, paused=False) == 1

    invalid_laws = (
        ((), 1.0, 0.0, "at least delay zero"),
        ((-0.1,), 1.1, 0.0, "non-negative"),
        ((0.4,), 0.4, 0.0, "sum to one"),
        ((1.0,), 0.0, 2.0, "pause_probability"),
    )
    for delays, loss, pause, message in invalid_laws:
        with pytest.raises(ValueError, match=message):
            RegisteredArrivalLaw(delays, loss, pause)
    always_pause = RegisteredArrivalLaw((1.0,), 0.0, 1.0)
    assert always_pause.pause_outcomes == ((True, 1.0),)

    with pytest.raises(ValueError, match="unsupported arrival family"):
        _changed_laws_for(ShockFamily.DEMAND_LEVEL, always_pause, MagnitudeBin.MEDIUM)
    assert len(_changed_laws_for(ShockFamily.LEAD_TIME_SHIFT, always_pause, MagnitudeBin.HIGH)) == 1
    with pytest.raises(ValueError, match="magnitude bin"):
        _changed_laws_for(ShockFamily.LEAD_TIME_SHIFT, always_pause, MagnitudeBin.NONE)
    assert _durations_for_family(ShockFamily.LEAD_TIME_SHIFT) == (None,)

    with pytest.raises(ValueError, match="remaining-zero"):
        ArrivalState(())
    with pytest.raises(ValueError, match="finite and non-negative"):
        ArrivalState((-1.0,))
    with pytest.raises(ValueError, match="maximum_delay"):
        ArrivalState.empty(-1)
    state = ArrivalState.empty(1)
    with pytest.raises(ValueError, match="dispatch quantity"):
        transition_state(state, dispatch_quantity=-1.0, delay=0, paused=False)
    with pytest.raises(ValueError, match="outside the registered state"):
        transition_state(state, dispatch_quantity=1.0, delay=2, paused=False)

    shorter = RegisteredArrivalLaw((1.0,), 0.0)
    longer = RegisteredArrivalLaw((0.5, 0.5), 0.0)
    with pytest.raises(ValueError, match="finite state space"):
        ArrivalModel(shorter, longer, active_from=1)
    with pytest.raises(ValueError, match="active_from"):
        ArrivalModel(shorter, shorter)
    with pytest.raises(ValueError, match="active_duration"):
        ArrivalModel(shorter, shorter, active_from=1, active_duration=0)

    filter_ = ArrivalForwardFilter(ArrivalModel(shorter))
    with pytest.raises(ValueError, match="consecutive"):
        filter_.step(period=2, dispatch_quantity=0.0, receipt=0.0)
    with pytest.raises(ValueError, match="receipt"):
        filter_.step(period=1, dispatch_quantity=0.0, receipt=-1.0)
    impossible = RegisteredArrivalLaw((0.0,), 1.0)
    impossible_filter = ArrivalForwardFilter(ArrivalModel(impossible))
    with pytest.raises(ValueError, match="impossible"):
        impossible_filter.step(period=1, dispatch_quantity=0.0, receipt=1.0)
    with pytest.raises(ValueError, match="sequences must align"):
        brute_force_sequence_probability(shorter, (1.0,), ())
    zero_branches = RegisteredArrivalLaw((1.0, 0.0), 0.0, pause_probability=0.0)
    assert brute_force_sequence_probability(zero_branches, (0.0,), (0.0,)) == 1.0
    explicit_zero_branches = SimpleNamespace(
        outcomes=((0, 1.0), (1, 0.0)),
        pause_outcomes=((False, 1.0), (True, 0.0)),
    )
    assert brute_force_sequence_probability(explicit_zero_branches, (0.0,), (0.0,)) == 1.0


def test_arrival_eprocess_and_calibration_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _arrival_spec()
    null = ArrivalModel()
    with pytest.raises(ValueError, match="at least one"):
        ArrivalEProcess(null, (), 0, 0.1)
    other_law = RegisteredArrivalLaw((1.0,), 0.0)
    with pytest.raises(ValueError, match="share the registered finite state"):
        ArrivalEProcess(
            null,
            (ArrivalModel(other_law),),
            0,
            0.1,
            family=ShockFamily.SHIPMENT_LOSS,
        )

    import collie.verify.arrival as arrival_module

    registered = arrival_module.resolve_spec(spec)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            arrival_module,
            "resolve_spec",
            lambda _: replace(registered, stream=TargetStream.DEMAND),
        )
        with pytest.raises(ValueError, match="registered arrival"):
            ArrivalEProcess.from_spec(spec, alpha_episode=0.05, preproposal_history=((0, 0),) * 2)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            arrival_module,
            "resolve_spec",
            lambda _: replace(registered, direction=Direction.ARRIVAL_DELAYED),
        )
        with pytest.raises(ValueError, match="direction"):
            ArrivalEProcess.from_spec(spec, alpha_episode=0.05, preproposal_history=((0, 0),) * 2)
    with monkeypatch.context() as scoped:
        scoped.setattr(arrival_module, "resolve_spec", lambda _: registered)
        with pytest.raises(ValueError, match="onset window"):
            ArrivalEProcess.from_spec(
                spec.model_copy(update={"onset_window": None}),
                alpha_episode=0.05,
                preproposal_history=((0, 0),) * 2,
            )
    verifier = ArrivalEProcess.from_spec(
        spec, alpha_episode=0.05, preproposal_history=((0, 0),) * 2
    )
    assert verifier.activation_period is None
    assert verifier.trace == ()

    assert _wilson(0, 2)[0] == 0.0
    assert _wilson(2, 2)[1] == 1.0
    with pytest.raises(ValueError, match="registered arrival family"):
        run_arrival_null_calibration(
            family=ShockFamily.DEMAND_LEVEL, replications=1, horizon=3, workers=1
        )
    with pytest.raises(ValueError, match="replications"):
        run_arrival_null_calibration(
            family=ShockFamily.SHIPMENT_LOSS, replications=0, horizon=3, workers=1
        )
    with pytest.raises(ValueError, match="tau_j"):
        run_arrival_null_calibration(
            family=ShockFamily.SHIPMENT_LOSS, replications=1, horizon=1, tau_j=1, workers=1
        )
    with pytest.raises(ValueError, match="workers"):
        run_arrival_null_calibration(
            family=ShockFamily.SHIPMENT_LOSS, replications=1, horizon=3, tau_j=1, workers=0
        )
    assert (
        run_null_calibration(
            replications=1, alpha_episode=0.05, horizon=3, tau_j=1, seed=1
        ).replications
        == 1
    )
    assert (
        run_arrival_null_calibration(
            family=ShockFamily.SHIPMENT_LOSS,
            replications=32,
            horizon=2,
            tau_j=1,
            workers=2,
        ).replications
        == 32
    )
    assert (
        run_arrival_null_calibration(
            family=ShockFamily.SHIPMENT_LOSS,
            replications=1,
            horizon=2,
            tau_j=1,
            workers=1,
        ).replications
        == 1
    )
    with pytest.raises(RuntimeError, match=r"worker .* failed"):
        _run_forked_chunks((("not", "a", "valid", "worker", "argument", "tuple"),))


def test_spawned_arrival_worker_failure_surfaces_the_worker_index() -> None:
    with pytest.raises(RuntimeError, match=r"worker local-.* failed"):
        _run_spawned_chunks((("not", "a", "valid", "worker", "argument", "tuple"),))


def test_demand_calibration_counts_an_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AlwaysActivates:
        activated = True

        def observe(self, period: int, value: float) -> None:
            del period, value

    import collie.verify.demand as demand_module

    monkeypatch.setattr(
        demand_module.DemandEProcess,
        "for_level_change",
        classmethod(lambda cls, **kwargs: _AlwaysActivates()),
    )
    summary = run_null_calibration(replications=1, alpha_episode=0.05, horizon=2, tau_j=1, seed=1)
    assert summary.activations == 1


def test_arrival_calibration_counts_an_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    class _AlwaysActivates:
        activated = True

        def observe(self, period: int, dispatch: float, receipt: float) -> None:
            del period, dispatch, receipt

    import collie.verify.arrival as arrival_module

    monkeypatch.setattr(
        arrival_module.ArrivalEProcess,
        "from_spec",
        classmethod(lambda cls, *args, **kwargs: _AlwaysActivates()),
    )
    activations = _arrival_null_chunk(
        ShockFamily.SHIPMENT_LOSS,
        (0,),
        2,
        1,
        0.05,
        1,
        (1.0, 1.0),
    )
    assert activations == 1


def test_registry_rejects_abstention_and_stream_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    abstention = demand_spec().model_copy(
        update={
            "shock_family": ShockFamily.NO_CHANGE,
            "direction": Direction.NONE,
            "target_stream": TargetStream.NONE,
            "prospective_signature": "sig_none",
            "onset_window": None,
            "magnitude_bin": None,
            "persistence": Persistence.NONE,
            "duration_bin": DurationBin.NONE,
        }
    )
    with pytest.raises(ValueError, match="abstention"):
        resolve_spec(abstention)
    spec = demand_spec()
    import collie.verify.registry as registry

    construction = registry.resolve_spec_shape(spec.shock_family, spec.prospective_signature)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            registry,
            "resolve_spec_shape",
            lambda *_: replace(construction, stream=TargetStream.ARRIVAL),
        )
        with pytest.raises(ValueError, match="target_stream"):
            registry.resolve_spec(spec)


def test_lifecycle_configuration_and_manager_guards() -> None:
    with pytest.raises(ValueError, match="remaining_horizon"):
        maximum_lifetime(DurationBin.SHORT, Persistence.TRANSIENT, remaining_horizon=0)
    with pytest.raises(ValueError, match="non-none"):
        maximum_lifetime(DurationBin.NONE, Persistence.NONE, remaining_horizon=2)
    with pytest.raises(ValueError, match="unsupported persistence"):
        maximum_lifetime(DurationBin.SHORT, object(), remaining_horizon=2)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="refutation_e_value"):
        RegisteredRetirementRules(refutation_e_value=1.0)
    with pytest.raises(ValueError, match="refutation_streak"):
        RegisteredRetirementRules(refutation_streak=0)
    with pytest.raises(ValueError, match="compound specs"):
        compound_alpha_allocation(
            alpha_episode=0.05, proposal_index=1, family=ShockFamily.DEMAND_LEVEL
        )

    with pytest.raises(ValueError, match="episode_horizon"):
        LifecycleManager(episode_horizon=0)
    with pytest.raises(ValueError, match="provisional"):
        LifecycleManager(
            episode_horizon=5,
            analysis_class=AnalysisClass.CONFIRMATORY,
            bounded_provisional=True,
        )
    with pytest.raises(ValueError, match="exactly two"):
        LifecycleManager(episode_horizon=5, max_proposals=1)
    manager = LifecycleManager(episode_horizon=5)
    with pytest.raises(ValueError, match="precede"):
        manager.propose(lifecycle_spec(tau_j=5))
    with pytest.raises(ValueError, match="proposal_index"):
        manager.propose(lifecycle_spec(proposal_index=2))

    abstention = lifecycle_spec().model_copy(
        update={
            "shock_family": ShockFamily.NO_CHANGE,
            "direction": Direction.NONE,
            "target_stream": TargetStream.NONE,
            "prospective_signature": "sig_none",
            "onset_window": None,
            "magnitude_bin": None,
            "persistence": Persistence.NONE,
            "duration_bin": DurationBin.NONE,
        }
    )
    with pytest.raises(ValueError, match="abstention"):
        manager.propose(abstention)
    with pytest.raises(ValueError, match="compound timeline"):
        compound_demo_timeline(lifecycle_spec(), episode_horizon=10)

    manager = LifecycleManager(episode_horizon=20)
    first = manager.propose(lifecycle_spec())
    second = manager.propose(lifecycle_spec(proposal_index=2, tau_j=6))
    first.state = LifecycleState.ACTIVE
    second.state = LifecycleState.ACTIVE
    with pytest.raises(AssertionError, match="at most one"):
        _ = manager.active


def _evidence(
    period: int,
    *,
    e_value: float = 1.0,
    threshold: float = 40.0,
    activated: bool = False,
    activation_period: int | None = None,
    validity: str = "anytime_valid",
    analysis: AnalysisClass = AnalysisClass.EXPLORATORY,
) -> EProcessPoint:
    return EProcessPoint(
        period=period,
        e_value=e_value,
        threshold=threshold,
        activated=activated,
        activation_period=activation_period,
        validity_label=validity,
        analysis_class=analysis,
    )


def test_lifecycle_rejects_malformed_evidence_and_ignores_terminal_updates() -> None:
    manager = LifecycleManager(episode_horizon=20)
    proposal = manager.propose(lifecycle_spec())
    with pytest.raises(TypeError, match="EProcessPoint"):
        proposal.consume(object())  # type: ignore[arg-type]
    malformed = (
        (_evidence(4), "strictly after"),
        (_evidence(5, threshold=41.0), "threshold"),
        (
            _evidence(5, analysis=AnalysisClass.CONFIRMATORY),
            "analysis classes",
        ),
        (_evidence(5, activated=True), "retain its crossing"),
        (_evidence(5, activation_period=5), "non-activated"),
        (
            _evidence(5, activated=True, activation_period=4, e_value=40.0),
            "post-proposal",
        ),
        (
            _evidence(5, activated=True, activation_period=5, e_value=1.0),
            "threshold crossing",
        ),
    )
    for point, message in malformed:
        with pytest.raises(ValueError, match=message):
            proposal.consume(point)

    confirmatory = LifecycleManager(
        episode_horizon=20, analysis_class=AnalysisClass.CONFIRMATORY
    ).propose(lifecycle_spec())
    with pytest.raises(ValueError, match="empirical_only"):
        confirmatory.consume(
            _evidence(
                5,
                validity=EMPIRICAL_ONLY,
                analysis=AnalysisClass.CONFIRMATORY,
            )
        )

    proposal.consume(_evidence(5))
    with pytest.raises(ValueError, match="increase strictly"):
        proposal.consume(_evidence(5))
    manager.advance(proposal.expiry_period)
    assert proposal.consume(_evidence(6)) is None

    active = LifecycleManager(episode_horizon=20).propose(lifecycle_spec())
    active.consume(_evidence(5, e_value=40.0, activated=True, activation_period=5))
    active.low_evidence_streak = 1
    active.consume(_evidence(6, e_value=1.0, activated=True, activation_period=5))
    assert active.low_evidence_streak == 0


def test_compound_evidence_guards_and_activation_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocation = CompoundAlphaAllocation(0.025, 0.0125, 0.0125, "split")
    demand = _evidence(5, threshold=80.0)
    arrival = _evidence(5, threshold=80.0)
    with pytest.raises(ValueError, match="same period"):
        compound_evidence_point(demand, replace(arrival, period=6), allocation=allocation)
    with pytest.raises(ValueError, match="analysis classes"):
        compound_evidence_point(
            demand,
            replace(arrival, analysis_class=AnalysisClass.CONFIRMATORY),
            allocation=allocation,
        )
    with pytest.raises(ValueError, match="demand threshold"):
        compound_evidence_point(replace(demand, threshold=1.0), arrival, allocation=allocation)
    with pytest.raises(ValueError, match="arrival threshold"):
        compound_evidence_point(demand, replace(arrival, threshold=1.0), allocation=allocation)
    with pytest.raises(ValueError, match="demand activation"):
        compound_evidence_point(
            replace(demand, activated=True, activation_period=5, e_value=1.0),
            arrival,
            allocation=allocation,
        )
    with pytest.raises(ValueError, match="arrival activation"):
        compound_evidence_point(
            demand,
            replace(arrival, activated=True, activation_period=5, e_value=1.0),
            allocation=allocation,
        )
    with pytest.raises(ValueError, match="retain both"):
        compound_evidence_point(
            replace(demand, activated=True, activation_period=None, e_value=80.0),
            replace(arrival, activated=True, activation_period=5, e_value=80.0),
            allocation=allocation,
        )

    valid = compound_evidence_point(demand, arrival, allocation=allocation)
    compound = LifecycleManager(episode_horizon=20).propose(
        lifecycle_spec(family=ShockFamily.COMPOUND)
    )
    with pytest.raises(TypeError, match="two separately"):
        compound.consume(demand)
    with pytest.raises(ValueError, match="derived from both"):
        compound.consume(replace(valid, validity_label="tampered"))

    fake_demand = SimpleNamespace(activated=True, activation_period=5, alpha_j=0.0125)
    fake_arrival = SimpleNamespace(activated=True, activation_period=6, alpha_j=0.0125)
    verifier = CompoundVerifier(
        lifecycle_spec(family=ShockFamily.COMPOUND),
        allocation,
        fake_demand,  # type: ignore[arg-type]
        fake_arrival,  # type: ignore[arg-type]
    )
    assert verifier.activated
    assert verifier.activation_period == 6
    inactive = CompoundVerifier(
        lifecycle_spec(family=ShockFamily.COMPOUND),
        allocation,
        SimpleNamespace(activated=False, activation_period=None),  # type: ignore[arg-type]
        fake_arrival,  # type: ignore[arg-type]
    )
    assert inactive.activation_period is None

    with pytest.raises(ValueError, match="compound ShockSpec"):
        CompoundVerifier.from_spec(
            lifecycle_spec(),
            baseline=BaselineSpec(),
            alpha_episode=0.05,
            demand_history_before_proposal=(100.0,) * 4,
            arrival_history_before_proposal=((0.0, 0.0),) * 4,
            null_arrival_law=__import__(
                "collie.verify.arrival", fromlist=["REGISTERED_NULL_LAW"]
            ).REGISTERED_NULL_LAW,
        )

    import collie.verify.lifecycle as lifecycle_module

    compound_spec = lifecycle_spec(family=ShockFamily.COMPOUND)
    with monkeypatch.context() as scoped:
        scoped.setattr(
            lifecycle_module.DemandEProcess,
            "from_spec",
            classmethod(lambda cls, *args, **kwargs: SimpleNamespace(alpha_j=999.0)),
        )
        scoped.setattr(
            lifecycle_module.ArrivalEProcess,
            "from_spec",
            classmethod(lambda cls, *args, **kwargs: SimpleNamespace(alpha_j=0.0125)),
        )
        with pytest.raises(AssertionError, match="demand verifier"):
            CompoundVerifier.from_spec(
                compound_spec,
                baseline=BaselineSpec(),
                alpha_episode=0.05,
                demand_history_before_proposal=(100.0,) * 4,
                arrival_history_before_proposal=((0.0, 0.0),) * 4,
                null_arrival_law=lifecycle_module.RegisteredArrivalLaw((1.0,), 0.0),
            )
    with monkeypatch.context() as scoped:
        scoped.setattr(
            lifecycle_module.DemandEProcess,
            "from_spec",
            classmethod(lambda cls, *args, **kwargs: SimpleNamespace(alpha_j=0.0125)),
        )
        scoped.setattr(
            lifecycle_module.ArrivalEProcess,
            "from_spec",
            classmethod(lambda cls, *args, **kwargs: SimpleNamespace(alpha_j=999.0)),
        )
        with pytest.raises(AssertionError, match="arrival verifier"):
            CompoundVerifier.from_spec(
                compound_spec,
                baseline=BaselineSpec(),
                alpha_episode=0.05,
                demand_history_before_proposal=(100.0,) * 4,
                arrival_history_before_proposal=((0.0, 0.0),) * 4,
                null_arrival_law=lifecycle_module.RegisteredArrivalLaw((1.0,), 0.0),
            )
