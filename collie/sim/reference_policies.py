"""Deterministic reference policies. Instrumentation for the Task 4 equivalence suite.

These are **not** research arms. Their only job is to drive the state machine hard enough that
any disagreement between our runner and the official pipeline shows up, and to stay frozen while
the real arms evolve. Arm 1's capped base-stock policy lives in ``collie/arms/`` and is free to
change without invalidating the equivalence evidence.

:func:`reference_order` is a pure function of the observable state. Both sides of the differential
call *this* function, so the arithmetic cannot drift between them; what the differential then
actually tests is the surrounding machinery — scheduling, arrival timing, the in-transit scalar,
censoring, and accounting.

The three kinds are chosen to cover the parts of the contract most likely to break:

``constant``    exercises arrival scheduling and the ``L = 0`` same-period landing.
``base_stock``  exercises ``on_hand + in_transit``, the term that the two upstream harnesses
                genuinely disagree about for lost shipments (``docs/env_contract.md`` §6). If our
                in-transit scalar were off by one period, only this kind would notice.
``chase``       exercises the full observation surface: previous demand, previous order, and
                previous arrivals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from collie.contracts import Decision, PeriodObservation

__all__ = ["ReferenceController", "ReferenceParams", "reference_order"]

ReferenceKind = Literal["constant", "base_stock", "chase"]


@dataclass(frozen=True, slots=True)
class ReferenceParams:
    """Parameters of a reference policy.

    ``train_mean`` is supplied by the caller rather than derived from ``train.csv`` inside the
    policy. That keeps the differential focused: both sides receive the identical number, so a
    mismatch in train parsing surfaces as its own explicit assertion instead of contaminating
    the accounting comparison.
    """

    kind: ReferenceKind = "base_stock"
    train_mean: float = 0.0
    constant_qty: int = 7
    target_multiplier: float = 1.5
    chase_gain: float = 1.25


def reference_order(
    params: ReferenceParams,
    *,
    period: int,
    on_hand: float,
    in_transit: float,
    prev_demand: float,
    prev_order: float,
    prev_arrivals: float,
    promised_lead_time: int,
) -> float:
    """Pure order rule. Identical code on both sides of the differential."""
    if params.kind == "constant":
        return float(params.constant_qty)

    if params.kind == "base_stock":
        # Cover promised lead time plus the current period, scaled.
        target = params.train_mean * (promised_lead_time + 1) * params.target_multiplier
        return max(0.0, target - on_hand - in_transit)

    if params.kind == "chase":
        # Chase last period's demand, credit the pipeline, and nudge on a disappointing arrival.
        base = prev_demand * params.chase_gain if period > 1 else params.train_mean
        shortfall = max(0.0, prev_order - prev_arrivals)
        target = base * (promised_lead_time + 1) + 0.25 * shortfall
        return max(0.0, target - on_hand - in_transit)

    raise ValueError(f"unknown reference kind {params.kind!r}")


@dataclass(slots=True)
class ReferenceController:
    """COLLIE-side adapter. Implements :class:`~collie.contracts.Controller`."""

    params: ReferenceParams
    arm_id: str = "reference"

    def reset(self) -> None:
        """Stateless by construction, so there is nothing to clear.

        Deliberate: a reference policy that carried state would make the differential sensitive
        to reset ordering, which is not what Task 4 is testing.
        """

    def order(self, obs: PeriodObservation) -> Decision:
        quantity = reference_order(
            self.params,
            period=obs.period,
            on_hand=obs.on_hand,
            in_transit=obs.in_transit_total,
            # Uncensored mode by contract for the equivalence suite; the official policy
            # interface receives true previous demand.
            prev_demand=obs.prev_demand if obs.prev_demand is not None else 0.0,
            prev_order=obs.prev_order,
            prev_arrivals=obs.prev_arrivals,
            promised_lead_time=obs.promised_lead_time,
        )
        return Decision(period=obs.period, order_quantity=quantity, arm_id=self.arm_id)
