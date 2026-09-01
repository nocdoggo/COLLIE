"""Trivial controllers used to prove the harness works before any method exists.

:class:`NullController` never orders, which makes hand-computing expected accounting easy.
:class:`ConstantController` orders a fixed quantity, which is the reference policy used by the
Task 4 differential equivalence suite: with a deterministic policy, any divergence from the
official pipeline is attributable to accounting rather than to policy randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from collie.contracts import Decision, PeriodObservation

__all__ = ["ConstantController", "NullController"]


@dataclass
class NullController:
    """Orders nothing, ever."""

    arm_id: str = "null"
    seen: list[PeriodObservation] = field(default_factory=list)

    def reset(self) -> None:
        self.seen.clear()

    def order(self, obs: PeriodObservation) -> Decision:
        self.seen.append(obs)
        return Decision(period=obs.period, order_quantity=0.0, arm_id=self.arm_id)


@dataclass
class ConstantController:
    """Orders the same quantity every period. Deterministic by construction."""

    quantity: float = 100.0
    arm_id: str = "constant"
    seen: list[PeriodObservation] = field(default_factory=list)

    def reset(self) -> None:
        self.seen.clear()

    def order(self, obs: PeriodObservation) -> Decision:
        self.seen.append(obs)
        return Decision(period=obs.period, order_quantity=self.quantity, arm_id=self.arm_id)
