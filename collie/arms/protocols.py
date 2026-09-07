"""Injection seams between the arms (module 06) and modules 02, 04, and 05.

The arm ladder is built against these protocols and receives every collaborator by injection
(module brief §3): no arm imports a concrete compiler, controller, parser, or verifier. When the
owning modules land, their implementations must satisfy these protocols unchanged; until then
``tests/conftest.py`` wires the temporary stand-ins in ``reference_control.py`` and the fakes in
``collie/fakes/``.

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
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)

__all__ = [
    "ActivationPolicy",
    "ProposalPayload",
    "SpecCompiler",
    "SpecParser",
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
    """

    def register(self, spec: ShockSpec) -> None:
        """Freeze a proposal. Evidence may only come from periods strictly after ``tau_j``."""
        ...

    def observe(self, period: int, value: float) -> LifecycleState:
        """Feed one post-proposal observation; return the resulting lifecycle state."""
        ...

    @property
    def is_active(self) -> bool:
        """Whether the registered hypothesis currently influences orders."""
        ...

    @property
    def state(self) -> LifecycleState:
        """The current lifecycle state of the registered hypothesis."""
        ...
