"""Task 22 — ShockSpec arms 8, 9, 10: one proposal call set, three activation policies.

The two load-bearing tests are the shared-call-set test (identical prompts at the same state
collapse to one physical call with one charged copy per arm) and the divergence test
(identical proposals, different activation traces). Both use the full channel stack.
"""

from __future__ import annotations

import hashlib
import math
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings

from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import (
    ARM8_ARM_ID,
    ARM9_ARM_ID,
    ARM10_ARM_ID,
    CONTRADICTION_PERIODS,
    EProcessActivation,
    HeuristicRollbackActivation,
    ImmediateActivation,
    ShockSpecArm,
)
from collie.contracts import (
    ControlConfig,
    Direction,
    DurationBin,
    LifecycleState,
    MagnitudeBin,
    ParseOutcome,
    PeriodObservation,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
    find_hidden_state,
)
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.fakes.fake_verifier import FakeVerifier
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from collie.trigger.detectors import PeriodicEveryK
from collie.trigger.protocol import MaxProposalsWrapper
from tests.strategies_arms import demand_streams
from tests.test_arms_direct import _RecordingTransport, _ScriptedTrigger
from tests.test_episode_runner import make_instance

PAYLOAD = ProposalPayload(
    target_stream=TargetStream.DEMAND,
    shock_family=ShockFamily.DEMAND_LEVEL,
    direction=Direction.DEMAND_UP,
    onset_window=(1, 3),
    magnitude_bin=MagnitudeBin.MEDIUM,
    persistence=Persistence.PERSISTENT,
    duration_bin=DurationBin.LONGER,
    evidence_refs=(),
    prospective_signature="sig_demand_level_up",
)


class _Prompter:
    """Deterministic proposal prompt from observable fields only."""

    def prompt(self, obs: PeriodObservation) -> str:
        alert = obs.alert.text if obs.alert else ""
        return (
            f"propose|p={obs.period}|on_hand={obs.on_hand}|transit={obs.in_transit_total}"
            f"|prev_demand={obs.prev_demand}|alert={alert}"
        )


class _Parser:
    """A fixed payload for any text; ``None`` (unusable) for the sentinel 'BAD'."""

    def __init__(self, payload: ProposalPayload | None = PAYLOAD):
        self.payload = payload

    def parse(self, text: str) -> ProposalPayload | None:
        return None if text == "BAD" else self.payload


def _factory(config: ControlConfig, demands: tuple[float, ...]) -> OrCompilerController:
    # No specific instance in scope here; every instance in this file carries the
    # ``make_instance`` default cap, so ``math.inf`` matches the contract exactly.
    return OrCompilerController(order_cap=math.inf, config=config, train_demand=demands)


def _harness(root: Path, default: str = "OK"):
    transport = _RecordingTransport(default=default)
    ledger = CallLedger()
    metered = MeteredClient(
        transport=transport,
        endpoint=scripted_endpoint(),
        cache=DiskCache(root / "cache"),
        ledger=ledger,
    )
    return transport, ledger, metered


def _arm(metered, instance, activation, *, arm_id, trigger=None, parser=None) -> ShockSpecArm:
    promised = instance.spec.promised_lead_time
    return ShockSpecArm(
        channel=metered.channel(arm_id=arm_id, episode_id=instance.spec.episode_id),
        prompter=_Prompter(),
        parser=parser or _Parser(),
        compiler=GridCompiler(),
        activation=activation,
        baseline=OrCompilerController(
            order_cap=instance.spec.order_cap, config=baseline_config_for(promised)
        ),
        controller_factory=_factory,
        trigger=trigger or _ScriptedTrigger({5}),
        baseline_config=baseline_config_for(promised),
        arm_id=arm_id,
    )


def _spec(**overrides) -> ShockSpec:
    from dataclasses import asdict

    base = dict(
        asdict(PAYLOAD),
        tau_j=5,
        proposal_index=1,
        model_id="t",
        decoding_hash="det-v1",
        prompt_hash="0" * 64,
    )
    base.update(overrides)
    return ShockSpec(**base)


# ---------------------------------------------------------------------------
# the two load-bearing tests
# ---------------------------------------------------------------------------


def test_arms_8_9_10_share_one_physical_proposal_call_set(tmp_path) -> None:
    """Identical prompts at the same decision point: one physical call, three charged."""
    instance = make_instance(demand=(5.0,) * 10, lead_times=(0.0,) * 10)
    transport, ledger, metered = _harness(tmp_path)
    arms = [
        _arm(metered, instance, ImmediateActivation(), arm_id=ARM8_ARM_ID),
        _arm(
            metered,
            instance,
            HeuristicRollbackActivation(),
            arm_id=ARM9_ARM_ID,
        ),
        _arm(
            metered,
            instance,
            EProcessActivation(FakeVerifier(activate_after=2)),
            arm_id=ARM10_ARM_ID,
        ),
    ]
    for arm in arms:
        EpisodeRunner(instance).run(arm)
    # One firing (period 5), identical prompt bytes -> one physical call total.
    assert transport.n_calls == 1
    charged = ledger.charged_entries()
    assert len(charged) == 3
    assert {c.arm_id for c in charged} == {ARM8_ARM_ID, ARM9_ARM_ID, ARM10_ARM_ID}
    assert all(c.outcome is ParseOutcome.ACCEPTED for c in charged)
    assert len({c.prompt_hash for c in charged}) == 1  # the same bytes
    ledger.assert_conserved()


def test_identical_proposals_divergent_activation_traces(tmp_path) -> None:
    """The divergence test: if the traces agreed, the activation mechanism would do nothing."""
    # Demand falls off a cliff at period 8; the scripted proposal claims demand_up.
    demand = (10.0,) * 7 + (2.0,) * 5
    instance = make_instance(demand=demand, lead_times=(0.0,) * 12)
    _, _, metered = _harness(tmp_path)
    arms = {
        ARM8_ARM_ID: _arm(metered, instance, ImmediateActivation(), arm_id=ARM8_ARM_ID),
        ARM9_ARM_ID: _arm(metered, instance, HeuristicRollbackActivation(), arm_id=ARM9_ARM_ID),
        ARM10_ARM_ID: _arm(
            metered,
            instance,
            EProcessActivation(FakeVerifier(activate_after=2)),
            arm_id=ARM10_ARM_ID,
        ),
    }
    traces = {}
    for arm_id, arm in arms.items():
        outcome = EpisodeRunner(instance).run(arm)
        traces[arm_id] = [d.lifecycle_state for d in outcome.decisions]

    t8, t9, t10 = traces[ARM8_ARM_ID], traces[ARM9_ARM_ID], traces[ARM10_ARM_ID]
    # Arm 8: active from the proposal period and never looks back.
    assert t8[:4] == [None] * 4
    assert t8[4:] == [LifecycleState.ACTIVE] * 8
    # Arm 10: proposed at 5, evidence at 6 and 7, active from the period-8 decision.
    assert t10[4:7] == [LifecycleState.PROPOSED] * 3
    assert t10[7:] == [LifecycleState.ACTIVE] * 5
    # Arm 9: active from 5, contradicted once the drop lands, refuted after the streak.
    assert t9[4:9] == [LifecycleState.ACTIVE] * 5
    assert t9[9:] == [LifecycleState.REFUTED] * 3
    # Pairwise divergence.
    assert t8 != t9 and t9 != t10 and t8 != t10


# ---------------------------------------------------------------------------
# lifecycle and accounting discipline
# ---------------------------------------------------------------------------


def test_proposed_spec_influences_nothing(tmp_path) -> None:
    """A never-activating verifier: every order is the baseline's, bit for bit."""
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0), lead_times=(0.0,) * 4)
    _, _, metered = _harness(tmp_path)
    arm = _arm(
        metered,
        instance,
        EProcessActivation(FakeVerifier(activate_after=None)),
        arm_id=ARM10_ARM_ID,
    )
    outcome = EpisodeRunner(instance).run(arm)
    check = OrCompilerController(order_cap=math.inf, config=baseline_config_for(0))
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected
    assert all(d.active_spec_id is None and d.control_config is None for d in outcome.decisions)
    assert all(d.lifecycle_state is LifecycleState.PROPOSED for d in outcome.decisions[4:])


def test_parse_failure_is_counted_and_the_baseline_runs_on(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, ledger, metered = _harness(tmp_path, default="BAD")
    arm = _arm(
        metered,
        instance,
        ImmediateActivation(),
        arm_id=ARM8_ARM_ID,
        trigger=_ScriptedTrigger({2}),
    )
    outcome = EpisodeRunner(instance).run(arm)
    assert all(d.lifecycle_state is None for d in outcome.decisions)
    assert [c.outcome for c in ledger.charged_entries()] == [ParseOutcome.FALLBACK]
    check = OrCompilerController(order_cap=math.inf, config=baseline_config_for(0))
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected


def test_the_two_proposal_cap_holds_through_the_real_wrapper(tmp_path) -> None:
    """The cap lives in the shared wrapper, not the arm: an every-period schedule yields 2."""
    instance = make_instance(demand=(5.0,) * 8, lead_times=(0.0,) * 8)
    transport, _, metered = _harness(tmp_path)
    trigger = MaxProposalsWrapper(PeriodicEveryK(periods=(3, 4, 5, 6)), limit=2)
    arm = _arm(metered, instance, ImmediateActivation(), arm_id=ARM8_ARM_ID, trigger=trigger)
    EpisodeRunner(instance).run(arm)
    assert transport.n_calls == 2
    assert len(arm._specs) == 2
    assert [s.proposal_index for s in arm._specs] == [1, 2]


def test_provenance_is_stamped_by_the_arm_not_the_model(tmp_path) -> None:
    instance = make_instance(demand=(5.0,) * 6, lead_times=(0.0,) * 6)
    transport, _, metered = _harness(tmp_path)
    arm = _arm(metered, instance, ImmediateActivation(), arm_id=ARM8_ARM_ID)
    EpisodeRunner(instance).run(arm)
    (spec,) = arm._specs
    assert spec.tau_j == 5 and spec.proposal_index == 1
    assert spec.model_id == "scripted-fake-7b"
    assert spec.decoding_hash == "det-v1"
    (prompt,) = [p for p, _ in transport.seen]
    assert spec.prompt_hash == hashlib.sha256(prompt.encode()).hexdigest()


def test_refutation_reverts_orders_to_baseline(tmp_path) -> None:
    demand = (10.0,) * 7 + (2.0,) * 5
    instance = make_instance(demand=demand, lead_times=(0.0,) * 12)
    _, _, metered = _harness(tmp_path)
    arm = _arm(metered, instance, HeuristicRollbackActivation(), arm_id=ARM9_ARM_ID)
    outcome = EpisodeRunner(instance).run(arm)
    check = OrCompilerController(order_cap=math.inf, config=baseline_config_for(0))
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    refuted_at = [
        d.period for d in outcome.decisions if d.lifecycle_state is LifecycleState.REFUTED
    ]
    assert refuted_at  # the drop refuted the demand_up spec
    for d, exp in zip(outcome.decisions, expected, strict=True):
        if d.period >= refuted_at[0]:
            assert d.order_quantity == exp


# ---------------------------------------------------------------------------
# policy units
# ---------------------------------------------------------------------------


def test_heuristic_rollback_requires_baseline_statistics() -> None:
    with pytest.raises(ValueError, match="baseline statistics"):
        HeuristicRollbackActivation().register(_spec(), baseline=None)


def test_activation_policy_units() -> None:
    immediate = ImmediateActivation()
    immediate.register(_spec(), baseline=(10.0, 2.0))
    assert immediate.is_active
    assert immediate.observe(6, 0.0) is LifecycleState.ACTIVE  # never looks back

    eprocess = EProcessActivation(FakeVerifier(activate_after=1))
    eprocess.register(_spec(), baseline=None)
    assert not eprocess.is_active
    assert eprocess.observe(6, 0.0) is LifecycleState.ACTIVE
    eprocess.reset()
    assert eprocess.state is LifecycleState.PROPOSED

    rollback = HeuristicRollbackActivation()
    rollback.register(_spec(), baseline=(10.0, 1.0))
    assert rollback.is_active
    for i in range(CONTRADICTION_PERIODS):
        rollback.observe(6 + i, 0.0)  # far below a demand_up claim
    assert rollback.state is LifecycleState.REFUTED
    # Terminal: further evidence changes nothing.
    assert rollback.observe(9, 999.0) is LifecycleState.REFUTED


def test_shockspec_arms_are_isolated(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _harness(tmp_path)
    for activation in (
        ImmediateActivation(),
        HeuristicRollbackActivation(),
        EProcessActivation(FakeVerifier(activate_after=2)),
    ):
        arm = _arm(metered, instance, activation, arm_id="iso-check")
        assert find_hidden_state(arm) == []
        EpisodeRunner(instance, check_controller_isolation=True).run(arm)


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------


@given(demands=demand_streams)
@settings(max_examples=20)
def test_shockspec_arm_legality_and_conservation(demands) -> None:
    """Order legality, accounting conservation, and physical <= charged for all three arms."""
    instance = make_instance(
        demand=tuple(float(d) for d in demands), lead_times=(0.0,) * len(demands)
    )
    with tempfile.TemporaryDirectory() as td:
        _, ledger, metered = _harness(Path(td))
        arms = [
            _arm(metered, instance, ImmediateActivation(), arm_id=ARM8_ARM_ID),
            _arm(metered, instance, HeuristicRollbackActivation(), arm_id=ARM9_ARM_ID),
            _arm(
                metered,
                instance,
                EProcessActivation(FakeVerifier(activate_after=2)),
                arm_id=ARM10_ARM_ID,
            ),
        ]
        for arm in arms:
            outcome = EpisodeRunner(instance).run(arm)
            for obs, dec in zip(outcome.observations, outcome.decisions, strict=True):
                assert dec.period == obs.period
                assert dec.order_quantity >= 0 and float(dec.order_quantity).is_integer()
    ledger.assert_conserved()
    physical = sum(1 for c in ledger.entries if c.physical)
    assert physical <= len(ledger.charged_entries())


def test_rollback_guard_direction_branches() -> None:
    """Every direction branch of the guard: demand_down, arrival interruption, and silence."""
    down = HeuristicRollbackActivation()
    down.register(_spec(direction=Direction.DEMAND_DOWN), baseline=(10.0, 1.0))
    assert not down._contradicts(5.0, None)  # a drop AGREES with demand_down
    assert down._contradicts(15.0, None)  # a surge contradicts it

    arrival = HeuristicRollbackActivation()
    arrival.register(_spec(direction=Direction.ARRIVAL_INTERRUPTED), baseline=(3.0, 1.0))
    assert not arrival._contradicts(0.0, 0.0)  # no arrivals AGREES with an interruption
    assert arrival._contradicts(0.0, 9.0)  # a fat arrival contradicts it

    silent = HeuristicRollbackActivation()
    silent.register(_spec(direction=Direction.NONE), baseline=(10.0, 1.0))
    assert not silent._contradicts(0.0, None)
    assert not silent._contradicts(999.0, None)


def test_rollback_guard_reads_the_receipt_channel_not_the_demand_channel() -> None:
    """An arrival-direction spec is refuted by a receipt spike with calm demand, and is
    deaf to a demand spike with calm receipts — the channels must not be crossed."""
    arrival = HeuristicRollbackActivation()
    arrival.register(_spec(direction=Direction.ARRIVAL_INTERRUPTED), baseline=(3.0, 1.0))
    for i in range(CONTRADICTION_PERIODS):
        arrival.observe(6 + i, 999.0, receipt=9.0)  # demand screams, receipts confirm anyway
    assert arrival.state is LifecycleState.REFUTED

    undisturbed = HeuristicRollbackActivation()
    undisturbed.register(_spec(direction=Direction.ARRIVAL_INTERRUPTED), baseline=(3.0, 1.0))
    for i in range(CONTRADICTION_PERIODS):
        undisturbed.observe(6 + i, 999.0, receipt=0.0)  # demand spike, receipts quiet
    assert undisturbed.state is LifecycleState.ACTIVE


def test_rollback_guard_raises_when_the_receipt_channel_is_missing() -> None:
    """A missing channel is a loud error, never a silently skipped check."""
    arrival = HeuristicRollbackActivation()
    arrival.register(_spec(direction=Direction.ARRIVAL_INTERRUPTED), baseline=(3.0, 1.0))
    with pytest.raises(ValueError, match="receipt channel"):
        arrival.observe(6, 5.0)


def test_arrival_stream_spec_feeds_the_arrival_evidence(tmp_path) -> None:
    """An arrival-targeted spec draws its baseline statistics from the arrival stream."""
    payload = ProposalPayload(
        target_stream=TargetStream.ARRIVAL,
        shock_family=ShockFamily.TRANSIT_PAUSE,
        direction=Direction.ARRIVAL_INTERRUPTED,
        onset_window=(1, 3),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.TRANSIENT,
        duration_bin=DurationBin.MEDIUM,
        evidence_refs=(),
        prospective_signature="sig_arrival_stall",
    )
    instance = make_instance(demand=(5.0,) * 8, lead_times=(2.0,) * 8)
    _, _, metered = _harness(tmp_path)
    arm = _arm(
        metered,
        instance,
        EProcessActivation(FakeVerifier(activate_after=2)),
        arm_id=ARM10_ARM_ID,
        parser=_Parser(payload),
    )
    outcome = EpisodeRunner(instance).run(arm)
    states = [d.lifecycle_state for d in outcome.decisions]
    assert states[4] is LifecycleState.PROPOSED  # proposed at period 5
    assert LifecycleState.ACTIVE in states  # and the evidence stream activated it later


class _RecordingPolicy:
    """Captures every evidence triple the arm feeds, never activates."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, float, float, float]] = []

    def reset(self) -> None:
        self.calls.clear()

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        del baseline

    def observe(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        assert dispatch is not None and receipt is not None
        self.calls.append((period, demand, dispatch, receipt))
        return LifecycleState.PROPOSED

    @property
    def is_active(self) -> bool:
        return False

    @property
    def state(self) -> LifecycleState:
        return LifecycleState.PROPOSED


def test_the_arm_feeds_all_three_evidence_channels_aligned_to_the_period(tmp_path) -> None:
    """The widened seam, end to end: demand, own dispatch, and receipt of the SAME period,
    with the receipt equal to the arm's dispatch two periods earlier under L=2."""
    policy = _RecordingPolicy()
    instance = make_instance(demand=(5.0,) * 8, lead_times=(2.0,) * 8)
    _, _, metered = _harness(tmp_path)
    arm = _arm(metered, instance, policy, arm_id=ARM10_ARM_ID)
    outcome = EpisodeRunner(instance).run(arm)
    orders = {d.period: d.order_quantity for d in outcome.decisions}

    assert policy.calls, "the proposal at period 5 must be followed by evidence"
    first_period = policy.calls[0][0]
    assert first_period == 6  # strictly after tau_j=5, never at or before it
    for period, demand, dispatch, receipt in policy.calls:
        assert demand == 5.0
        assert dispatch == orders[period]  # the arm's own decision record
        assert receipt == orders[period - 2]  # L=2: this period's arrivals were ordered then


def test_proposal_at_period_1_has_empty_baseline_stats(tmp_path) -> None:
    """A proposal on the first period: no history yet, baseline stats are (0, 0)."""
    instance = make_instance(demand=(5.0,) * 4, lead_times=(0.0,) * 4)
    _, _, metered = _harness(tmp_path)
    arm = _arm(
        metered,
        instance,
        HeuristicRollbackActivation(),
        arm_id=ARM9_ARM_ID,
        trigger=_ScriptedTrigger({1}),
    )
    EpisodeRunner(instance).run(arm)
    assert arm.activation._baseline == (0.0, 0.0)
    assert arm._specs[0].tau_j == 1


def test_dispatch_book_remembers_every_period_and_is_loud_about_gaps() -> None:
    """The FIFO queue is consumed by arrivals; the dispatch book is the durable record."""
    from collie.arms.history import BenchmarkHistory

    history = BenchmarkHistory(arm_id="t")
    history.note_dispatch(1, 7.0)
    history.note_dispatch(2, 3.0)
    assert history.dispatch_at(1) == 7.0
    assert history.dispatch_at(2) == 3.0
    with pytest.raises(KeyError, match="no dispatch at period 3"):
        history.dispatch_at(3)
    history.reset()
    with pytest.raises(KeyError, match="no dispatch at period 1"):
        history.dispatch_at(1)
