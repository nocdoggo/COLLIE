"""Arms 8, 9, and 10 — ShockSpec proposals under three activation policies.

One :class:`ShockSpecArm` base owns proposal, compilation, and lifecycle; the three arms differ
*only* in the injected activation policy (brief §6.4), so any difference in outcomes is the
verification stage, never the invocation. The sharing is physical: all three build the same
proposal prompt at the same decision point, and the cache collapses those to one physical call
with one charged copy per arm.

Lifecycle rules (frozen contracts + derivation note §5):

* A spec influences nothing while ``PROPOSED`` — the baseline controller (arm 1's math via the
  injected controller) orders. Influence begins only when the activation policy says so.
* Provenance is stamped by the arm, never the model: ``tau_j`` is the proposal period,
  ``proposal_index`` is 1-based (the verifier's alpha allocation is ``alpha_j = alpha * 2^-j``,
  at most two proposals — the shared trigger's ``MaxProposalsWrapper`` enforces the cap).
* Evidence enters the policy strictly after ``tau_j``: at decision period ``t`` the arm feeds
  ``Y_{t-1}`` and only when ``t - 1 > tau_j``, so the future-only boundary holds by
  construction (the fake verifier raises on violation; the real one will inherit the seam).

The activation policies:

* ``ImmediateActivation`` (arm 8): ACTIVE at proposal, never verifies, never rolls back.
* ``HeuristicRollbackActivation`` (arm 9): ACTIVE at proposal, then a residual guard: the value
  stream is compared against the pre-proposal baseline statistics the arm hands over at
  registration, and ``CONTRADICTION_PERIODS`` consecutive contradictions refute the spec (the
  order path reverts to baseline). The guard's constants are module 06's heuristic, registered
  here and reviewed at Gate 2 — arm 9 exists to answer "a heuristic guard would do", so it must
  be a real guard, not a strawman.
* ``EProcessActivation`` (arm 10): defers entirely to the injected verifier
  (``collie/fakes/fake_verifier.py`` today, module 05's e-processes unchanged later).

What the model is asked and how its answer validates belongs to module 02 (``SpecPrompter`` /
``SpecParser`` seams); the ShockSpec-to-ControlConfig mapping belongs to module 04
(``SpecCompiler`` seam); activation under verification belongs to module 05
(``ActivationPolicy`` seam). No concrete implementation of any of those is imported here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from collie.arms.history import BenchmarkHistory
from collie.arms.protocols import (
    ActivationPolicy,
    RepairingSpecPrompter,
    SpecCompiler,
    SpecParser,
    SpecPrompter,
)
from collie.contracts import (
    ControlConfig,
    Controller,
    Decision,
    Direction,
    LifecycleState,
    ParseOutcome,
    PeriodObservation,
    ShockSpec,
    TargetStream,
    Trigger,
)
from collie.llm.client import ArmCallChannel

__all__ = [
    "ARM8_ARM_ID",
    "ARM9_ARM_ID",
    "ARM10_ARM_ID",
    "CONTRADICTION_PERIODS",
    "CONTRADICTION_Z",
    "EProcessActivation",
    "HeuristicRollbackActivation",
    "ImmediateActivation",
    "ShockSpecArm",
]

ARM8_ARM_ID = "arm8_spec_immediate"
ARM9_ARM_ID = "arm9_spec_heuristic_rollback"
ARM10_ARM_ID = "arm10_spec_eprocess"

CONTRADICTION_Z = 1.0
"""Arm 9's guard: an observation contradicts the spec's direction when it sits more than one
baseline standard deviation on the wrong side of the baseline mean."""

CONTRADICTION_PERIODS = 2
"""Arm 9's guard: this many *consecutive* contradictions refute the spec."""


# ---------------------------------------------------------------------------
# activation policies
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ImmediateActivation:
    """Arm 8's policy: a proposal is active the moment it is registered. No verification."""

    _state: LifecycleState = LifecycleState.PROPOSED
    _spec: ShockSpec | None = None

    def reset(self) -> None:
        self._state = LifecycleState.PROPOSED
        self._spec = None

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        del baseline  # immediate activation needs no baseline statistics
        self._spec = spec
        self._state = LifecycleState.ACTIVE

    def observe(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        del demand, dispatch, receipt  # immediate activation never looks at evidence
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state is LifecycleState.ACTIVE

    @property
    def state(self) -> LifecycleState:
        return self._state


@dataclass(slots=True)
class HeuristicRollbackActivation:
    """Arm 9's policy: active at once, refuted by a residual guard.

    The baseline statistics (mean, std) of the spec-relevant stream over the pre-proposal
    history are handed over at registration. A post-activation observation contradicts the
    spec when it lands more than ``CONTRADICTION_Z`` baseline standard deviations on the wrong
    side of the baseline mean for the spec's direction; ``CONTRADICTION_PERIODS`` consecutive
    contradictions refute. Terminal states stay terminal, matching the frozen lifecycle.
    """

    _state: LifecycleState = LifecycleState.PROPOSED
    _spec: ShockSpec | None = None
    _baseline: tuple[float, float] | None = None
    _streak: int = 0

    def reset(self) -> None:
        self._state = LifecycleState.PROPOSED
        self._spec = None
        self._baseline = None
        self._streak = 0

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        if baseline is None:
            raise ValueError(
                "the rollback guard needs the pre-proposal baseline statistics; without them "
                "'residual-based' would be a label, not a computation"
            )
        self._spec = spec
        self._baseline = baseline
        self._state = LifecycleState.ACTIVE
        self._streak = 0

    def observe(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        del dispatch  # the rollback guard tests residuals, not the order book
        if self._state is not LifecycleState.ACTIVE:
            return self._state
        assert self._spec is not None and self._baseline is not None
        if self._contradicts(demand, receipt):
            self._streak += 1
        else:
            self._streak = 0
        if self._streak >= CONTRADICTION_PERIODS:
            self._state = LifecycleState.REFUTED
        return self._state

    def _contradicts(self, demand: float, receipt: float | None) -> bool:
        """Whether the spec-relevant channel speaks against the claimed direction."""
        assert self._spec is not None and self._baseline is not None  # observe() gates this
        mean, std = self._baseline
        direction = self._spec.direction
        if direction is Direction.DEMAND_UP:
            return demand < mean - CONTRADICTION_Z * std
        if direction is Direction.DEMAND_DOWN:
            return demand > mean + CONTRADICTION_Z * std
        if direction in (Direction.ARRIVAL_DELAYED, Direction.ARRIVAL_INTERRUPTED):
            if receipt is None:
                raise ValueError("an arrival-direction rollback needs the receipt channel")
            return receipt > mean + CONTRADICTION_Z * std
        return False  # none/mixed directions: the guard stays silent

    @property
    def is_active(self) -> bool:
        return self._state is LifecycleState.ACTIVE

    @property
    def state(self) -> LifecycleState:
        return self._state


@dataclass(slots=True)
class EProcessActivation:
    """Arm 10's policy: defer to the injected verifier (FakeVerifier in tests; module 05's
    ``VerifierActivationPolicy`` in production wiring, which additionally implements the
    optional ``prime``/``condition`` conditioning hooks the arm discovers by duck typing).

    The verifier's interface — ``register(spec, *, baseline)``, ``observe(period, demand, *,
    dispatch, receipt) -> LifecycleState``, ``is_active``, ``reset()`` — is deliberately the
    future-only one: the e-process may only see ``Y_r`` for ``r > tau_j``.
    """

    verifier: object  # FakeVerifier-shaped; typed as object so module 05 drops in unchanged

    def reset(self) -> None:
        self.verifier.reset()

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        self.verifier.register(spec, baseline=baseline)

    def observe(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        return self.verifier.observe(period, demand, dispatch=dispatch, receipt=receipt)

    @property
    def is_active(self) -> bool:
        return self.verifier.is_active

    @property
    def state(self) -> LifecycleState:
        return self.verifier.state


# ---------------------------------------------------------------------------
# the arm
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ShockSpecArm:
    """Arms 8/9/10. Owns proposal, compilation, and lifecycle; parameterised by activation.

    Every collaborator is injected (module brief §3): the channel, the prompter, the parser,
    the compiler, the activation policy, the baseline controller, the controller factory for
    compiled configs, and the shared (wrapped) trigger. The baseline controller is fed every
    observation regardless, so its estimator never skips; the experimental controller is
    created on first activation and fed every observation from then on, so its estimator is
    continuous too.
    """

    channel: ArmCallChannel
    prompter: SpecPrompter
    parser: SpecParser
    compiler: SpecCompiler
    activation: ActivationPolicy
    baseline: Controller
    controller_factory: Callable[[ControlConfig, tuple[float, ...]], Controller]
    """Builds the experimental controller at activation: the compiled config plus the demand
    history observed so far, so its estimator starts continuous rather than empty."""
    trigger: Trigger
    baseline_config: ControlConfig
    arm_id: str = ARM8_ARM_ID
    _history: BenchmarkHistory = field(init=False, repr=False)
    _specs: list[ShockSpec] = field(default_factory=list, repr=False)
    _experimental: Controller | None = field(default=None, repr=False)
    _compiled: ControlConfig | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._history = BenchmarkHistory(arm_id=self.arm_id)

    def reset(self) -> None:
        self._history.reset()
        if isinstance(self.prompter, RepairingSpecPrompter):
            self.prompter.reset()
        self._specs = []
        self._experimental = None
        self._compiled = None
        self.activation.reset()
        self.baseline.reset()

    def order(self, obs: PeriodObservation) -> Decision:
        self.channel.set_period(obs.period)
        self._history.observe(obs)
        if isinstance(self.prompter, RepairingSpecPrompter):
            self.prompter.observe(obs)
        self._history.record_demand(obs)

        lifecycle = self._lifecycle_step(obs)
        proposed = self._maybe_propose(obs)
        if proposed:
            lifecycle = self.activation.state

        # Activation can flip on either step (a proposal, or the verifier's observe), so the
        # transition is checked once, in one place.
        latest = self._specs[-1] if self._specs else None
        if self.activation.is_active and latest is not None and self._experimental is None:
            self._activate(latest)
            lifecycle = self.activation.state

        # Both controllers see every observation; the *decision* comes from whichever the
        # lifecycle permits. Baseline runs while PROPOSED (and after REFUTED/EXPIRED).
        baseline_decision = self.baseline.order(obs)
        experimental_decision = (
            self._experimental.order(obs) if self._experimental is not None else None
        )

        if self.activation.is_active and latest is not None and experimental_decision is not None:
            quantity = experimental_decision.order_quantity
            active_spec_id = f"spec-{latest.proposal_index}@tau{latest.tau_j}"
            config = self._compiled
        else:
            quantity = baseline_decision.order_quantity
            active_spec_id = None
            config = None
        self._history.note_dispatch(obs.period, quantity)
        return Decision(
            period=obs.period,
            order_quantity=quantity,
            arm_id=self.arm_id,
            llm_called=proposed,
            triggered=proposed,
            active_spec_id=active_spec_id,
            control_config=config,
            lifecycle_state=lifecycle if latest is not None else None,
        )

    # -- internals -----------------------------------------------------------

    def _lifecycle_step(self, obs: PeriodObservation) -> LifecycleState | None:
        """Feed the evidence stream, strictly post-tau. Returns the current lifecycle state.

        All three channels of the evidence period go through; which of them a policy tests is
        the policy's business, decided by the registered spec's construction — the arm does
        not pre-select a stream.
        """
        if not self._specs:
            return None
        latest = self._specs[-1]
        evidence_period = obs.period - 1
        if evidence_period < latest.tau_j:
            return self.activation.state
        if evidence_period == latest.tau_j:
            condition = getattr(self.activation, "condition", None)
            if condition is not None:
                return condition(
                    evidence_period,
                    self._history.demands[evidence_period - 1],
                    dispatch=self._history.dispatch_at(evidence_period),
                    receipt=self._history.arrivals[evidence_period - 1],
                )
            return self.activation.state
        return self.activation.observe(
            evidence_period,
            self._history.demands[evidence_period - 1],
            dispatch=self._history.dispatch_at(evidence_period),
            receipt=self._history.arrivals[evidence_period - 1],
        )

    def _maybe_propose(self, obs: PeriodObservation) -> bool:
        """One proposal call if the trigger fires. Returns whether a call was made."""
        if not self.trigger.should_propose(obs):
            return False
        prompt = self.prompter.prompt(obs)
        raw_text = self.channel.complete_attempt(prompt, decoding_hash="det-v1", attempt_index=1)
        call_id = self.channel.last_call_id
        assert call_id is not None  # the channel stamps every call
        payload = self.parser.parse(raw_text)
        outcome = ParseOutcome.ACCEPTED
        if payload is None:
            self.channel.settle(call_id, ParseOutcome.FALLBACK)
            if not isinstance(self.prompter, RepairingSpecPrompter):
                return True
            prompt = self.prompter.repair_prompt()
            raw_text = self.channel.complete_attempt(
                prompt, decoding_hash="det-v1", attempt_index=2
            )
            call_id = self.channel.last_call_id
            assert call_id is not None
            payload = self.parser.parse(raw_text)
            if payload is None:
                self.channel.settle(call_id, ParseOutcome.FALLBACK)
                return True
            outcome = ParseOutcome.ACCEPTED_AFTER_REPAIR
        self.channel.settle(call_id, outcome)
        spec = ShockSpec(
            **asdict(payload),
            tau_j=obs.period,
            proposal_index=len(self._specs) + 1,
            model_id=self.channel.model_id,
            decoding_hash="det-v1",
            prompt_hash=hashlib.sha256(prompt.encode()).hexdigest(),
        )
        if spec.is_abstention:
            return True
        prime = getattr(self.activation, "prime", None)
        if prime is not None:
            prefix = range(1, spec.tau_j)
            prime(
                tuple(self._history.demands),
                tuple(
                    (self._history.dispatch_at(period), self._history.arrivals[period - 1])
                    for period in prefix
                ),
            )
        self.activation.register(spec, baseline=self._baseline_stats(spec))
        self._specs.append(spec)
        return True

    def _activate(self, spec: ShockSpec) -> None:
        """Compile once and create the experimental controller once, with the demand history.

        The factory receives demands through period ``t-2``: the experimental controller
        records ``t-1``'s demand itself when its ``order`` is called at the switch period
        ``t``, so handing it the full history would count that cell twice.
        """
        self._compiled = self.compiler.compile(spec, current=self.baseline_config)
        self._experimental = self.controller_factory(self._compiled, self._history.demands[:-1])

    def _baseline_stats(self, spec: ShockSpec) -> tuple[float, float]:
        """Pre-proposal (mean, std) of the spec-relevant stream, for the rollback guard."""
        import math

        if spec.target_stream is TargetStream.ARRIVAL:
            samples = self._history.arrivals
        else:
            samples = self._history.demands
        if not samples:
            return 0.0, 0.0
        mean = sum(samples) / len(samples)
        variance = (
            sum((s - mean) ** 2 for s in samples) / (len(samples) - 1) if len(samples) > 1 else 0.0
        )
        return mean, math.sqrt(variance)
