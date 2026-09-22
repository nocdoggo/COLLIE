"""Injection seams between the arms (module 06) and modules 02, 04, and 05.

The arm ladder is built against these protocols and receives every collaborator by injection
(module brief §3): no arm imports a concrete compiler, controller, parser, or verifier. All
three owning modules have landed, and every seam below is satisfied by its real implementation
without either side changing shape:

* module 02 — ``collie.spec.adapters.ShockSpecPrompter`` satisfies ``SpecPrompter`` and
  ``RepairingSpecPrompter``, ``collie.spec.adapters.ShockSpecParser`` satisfies ``SpecParser``;
* module 04 — ``collie.control.mapping.GridCompiler`` satisfies ``SpecCompiler`` and
  ``collie.control.controller.OrCompilerController`` the shared ``Controller`` seam;
* module 05 — ``collie.verify.VerifierActivationPolicy`` satisfies ``ActivationPolicy``.

All of them are wired in ``tests/conftest.py`` and ``tools/run_arms.py``; the fakes in
``collie/fakes/`` stay as the isolation stand-ins that prove no arm depends on a concrete
collaborator (``tests/test_arms_isolation.py``), not as substitutes for a missing module.

The shapes are deliberately minimal — they state what the *arms* need, not what the owning
module will offer, so neither side guesses at the other's design decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from collie.contracts import (
    ControlConfig,
    Direction,
    DurationBin,
    LifecycleState,
    MagnitudeBin,
    PeriodObservation,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)

__all__ = [
    "ActivationPolicy",
    "ProposalPayload",
    "RepairingSpecPrompter",
    "SpecCompiler",
    "SpecParser",
    "SpecPrompter",
]


@dataclass(frozen=True, slots=True)
class ProposalPayload:
    """The model-controlled fields of a proposal — everything provenance is not.

    Provenance (``tau_j``, ``proposal_index``, ``model_id``, ``decoding_hash``, ``prompt_hash``)
    is stamped by the arm after validation, never accepted from the model
    (``collie/contracts.py``'s ``ShockSpec`` docstring). This is what module 02's parser returns
    when a proposal text validates against the registry; ``None`` from the parser means
    unusable.
    """

    target_stream: TargetStream
    shock_family: ShockFamily
    direction: Direction
    onset_window: tuple[int, int] | None
    magnitude_bin: MagnitudeBin | None
    persistence: Persistence
    duration_bin: DurationBin
    evidence_refs: tuple[str, ...]
    prospective_signature: str


@runtime_checkable
class SpecParser(Protocol):
    """Module 02's seam: raw proposal text to a validated payload, or ``None`` if unusable."""

    def parse(self, text: str) -> ProposalPayload | None:
        """Validate one proposal text against the registry. ``None`` routes to the fallback."""
        ...


@runtime_checkable
class SpecPrompter(Protocol):
    """Module 02's other seam: the proposal prompt for one decision point.

    The arm owns *when* a proposal happens (the shared trigger); module 02 owns what the model
    is asked and how the answer is validated. Keeping the prompt behind this protocol is what
    lets arms 8/9/10 share one physical call set: identical prompt bytes at the same decision
    point hit the same cache entry regardless of which arm asked.
    """

    def prompt(self, obs: PeriodObservation) -> str:
        """The proposal prompt text for this observation. Deterministic in its inputs."""
        ...


@runtime_checkable
class SpecCompiler(Protocol):
    """Module 04's seam: a ShockSpec to a ControlConfig, given what is currently running."""

    def compile(self, spec: ShockSpec, *, current: ControlConfig) -> ControlConfig:
        """Map one typed hypothesis onto the control grid. Pure: no state, no hidden truth."""
        ...


@runtime_checkable
class ActivationPolicy(Protocol):
    """Module 05's seam: decides when a PROPOSED spec earns influence over orders.

    Mirrors ``collie/fakes/fake_verifier.py``'s constraint: evidence enters only as the
    observable stream, strictly after ``tau_j``. The three arms 8/9/10 differ *only* in the
    injected implementation of this protocol (brief §6.4).

    A policy may additionally define the optional hooks ``prime(demand_history,
    arrival_history)`` and ``condition(period, demand, *, dispatch, receipt)``, discovered by
    the arm through duck typing: they transfer already-observed pre-proposal history for
    conditioning without admitting it to the e-process product. Module 05's
    ``VerifierActivationPolicy`` implements them; policies that need no conditioning simply
    omit them, and an implementation that needs them but forgets one fails loudly at
    ``register`` or ``observe``.
    """

    def reset(self) -> None:
        """Drop all episode state. The runner resets arms between episodes; policies follow."""
        ...

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        """Freeze a proposal. Evidence may only come from periods strictly after ``tau_j``.

        ``baseline`` is the ``(mean, sd)`` of the pre-proposal demand history, supplied by the
        arm because only the arm has the observation stream. It is keyword-only and optional so
        a policy that needs no null estimate can ignore it. Declaring it here is not cosmetic:
        ``ShockSpecArm`` passes it, so a policy written to a signature without it raises
        ``TypeError`` on the first proposal.
        """
        ...

    def observe(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        """Feed one post-proposal period of evidence; return the lifecycle state.

        Three channels, all observable, all indexed by ``period``: ``demand`` is the period's
        (uncensored) demand; ``dispatch`` is the arm's own order sent at ``period`` — known
        before that period's receipt is observed, per the runner's event order; ``receipt``
        is the arrivals during ``period``. A demand-side policy reads ``demand``; an
        arrival-side construction needs ``(dispatch, receipt)``; a compound needs all three.
        ``None`` means the channel was not supplied, and a policy that needs it must raise
        rather than silently degrade.
        """
        ...

    @property
    def is_active(self) -> bool:
        """Whether the registered hypothesis currently influences orders."""
        ...

    @property
    def state(self) -> LifecycleState:
        """The current lifecycle state of the registered hypothesis."""
        ...


@runtime_checkable
class RepairingSpecPrompter(SpecPrompter, Protocol):
    """Optional history/reset/repair seam; legacy one-shot prompters remain valid."""

    def observe(self, obs: PeriodObservation) -> None: ...

    def reset(self) -> None: ...

    def repair_prompt(self) -> str: ...
