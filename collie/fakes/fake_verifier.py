"""A verifier that activates on a caller-supplied schedule.

Lets branch G build and test arms 8-10 and the lifecycle wiring before branch F's e-processes
exist, and lets branch F's lifecycle tests run without a likelihood.

It deliberately accepts **no** hidden state: its ``observe`` signature takes only the observable
stream, mirroring the real verifier's constraint that only ``Y_r`` for ``r > tau_j`` may enter.
A fake with a looser interface than the real thing would let a leak pass unnoticed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from collie.contracts import LifecycleState, ShockSpec

__all__ = ["FakeVerifier"]


@dataclass
class FakeVerifier:
    """Activate a proposal after a fixed number of post-proposal observations.

    ``activate_after=0`` reproduces arm 8 (immediate, unverified). ``activate_after=None`` never
    activates, which is the useful control for "the hypothesis was proposed but never earned
    influence".
    """

    activate_after: int | None = 2
    refute_at: int | None = None
    """Post-activation observation count at which a registered contradiction rule fires."""
    max_lifetime: int | None = None
    """Observations after activation before expiry. Mirrors the schema-defined maximum."""

    spec: ShockSpec | None = None
    tau_j: int | None = None
    state: LifecycleState = LifecycleState.PROPOSED
    observations_since_proposal: int = 0
    observations_since_activation: int = 0
    activation_period: int | None = None
    history: list[tuple[int, LifecycleState]] = field(default_factory=list)

    def reset(self) -> None:
        self.spec = None
        self.tau_j = None
        self.state = LifecycleState.PROPOSED
        self.observations_since_proposal = 0
        self.observations_since_activation = 0
        self.activation_period = None
        self.history.clear()

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        """Freeze a proposal (``baseline`` is accepted and ignored: this stand-in has no null model) at ``tau_j``. Evidence may only come from strictly later periods."""
        self.spec = spec
        self.tau_j = spec.tau_j
        self.state = LifecycleState.PROPOSED
        self.observations_since_proposal = 0
        self.observations_since_activation = 0
        self.history.append((spec.tau_j, LifecycleState.PROPOSED))

    def observe(self, period: int, value: float) -> LifecycleState:
        """Feed one post-proposal observation and return the resulting lifecycle state.

        Raises if handed an observation at or before ``tau_j``: the future-only boundary is the
        property under test, so violating it must be loud even in a fake.
        """
        if self.spec is None or self.tau_j is None:
            return self.state
        if period <= self.tau_j:
            raise ValueError(
                f"future-only violation: observation at period {period} is not strictly after "
                f"tau_j={self.tau_j}"
            )
        if self.state in (
            LifecycleState.REFUTED,
            LifecycleState.EXPIRED,
            LifecycleState.SUPERSEDED,
        ):
            return self.state

        self.observations_since_proposal += 1

        if self.state is LifecycleState.PROPOSED:
            if self.activate_after is not None and (
                self.observations_since_proposal >= self.activate_after
            ):
                self.state = LifecycleState.ACTIVE
                self.activation_period = period
                self.history.append((period, self.state))
            return self.state

        self.observations_since_activation += 1
        if self.refute_at is not None and self.observations_since_activation >= self.refute_at:
            self.state = LifecycleState.REFUTED
            self.history.append((period, self.state))
        elif (
            self.max_lifetime is not None
            and self.observations_since_activation >= self.max_lifetime
        ):
            self.state = LifecycleState.EXPIRED
            self.history.append((period, self.state))
        return self.state

    @property
    def is_active(self) -> bool:
        return self.state is LifecycleState.ACTIVE

    @property
    def activation_delay(self) -> int | None:
        """Proposal-to-activation delay in periods — a primary reported outcome, not a footnote."""
        if self.activation_period is None or self.tau_j is None:
            return None
        return self.activation_period - self.tau_j
