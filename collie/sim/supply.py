"""Supply physics: lead time, shipment loss, transit pause.

The reference implementation (``eval/run_baseline_policy.py``, ``eval/evaluate_results.py``)
keys in-transit inventory by **absolute arrival period**::

    if not isinf(L):
        in_transit[period + L] += qty
    arrivals = in_transit.pop(period, 0)

That representation cannot express a transit pause, because an arrival date fixed at order time
can never be deferred. So this module carries **remaining transit time per cohort** instead, and
:class:`LeadTimeSupply` is written to be *exactly* equivalent to the arrival-keyed reference
whenever no pause is active. Task 4's differential suite is what proves that claim, and the
equivalence is the reason a paused episode is still scored by the official evaluator's rules.

Per-period sequence, mirroring ``docs/env_contract.md`` §3:

1. :meth:`LeadTimeSupply.in_transit_total` — read at decision time. Includes units that will
   land this very period, because the arrival pop happens *after* the decision. Excludes the
   order about to be placed.
2. :meth:`LeadTimeSupply.dispatch` — schedule this period's order.
3. :meth:`LeadTimeSupply.receive` — deliver cohorts whose transit is complete, then advance the
   transit clock by one period unless this period is paused.

Two semantics are deliberate and load-bearing:

**Lost shipments.** ``lead_time = inf`` means the shipment never arrives. The authoritative
``eval/`` path never adds it to in-transit; ``env.py`` keeps it in in-transit forever
(``docs/env_contract.md`` §6). ``lost_orders_visible`` selects between them so the legacy arms
can be run under the harness they were defined against, and defaults to the ``eval/`` path.

**Pause blocks progress, not arrival.** A cohort whose transit is already complete
(``remaining == 0``) lands even during a pause; a pause freezes the clock of cohorts still
moving. This keeps the invariant that units with ``remaining == 0`` at decision time always
land this period — which is precisely the reference semantics, and what the OR compiler's
pipeline crediting relies on. A pause of length ``k`` therefore delays every still-moving
shipment by exactly ``k`` periods.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from collie.contracts import SupplyRealization

__all__ = ["ArrivalKeyedSupply", "Cohort", "LeadTimeSupply"]


@dataclass(slots=True)
class Cohort:
    """One dispatched order still in transit. ``remaining == 0`` means it lands this period."""

    quantity: float
    remaining: int


@dataclass(slots=True)
class LeadTimeSupply:
    """Cohort-based supply process. Implements the :class:`~collie.contracts.SupplyProcess` protocol.

    ``realization`` is hidden state: it is held here and never surfaced through an observation.
    """

    realization: SupplyRealization
    lost_orders_visible: bool = False
    """``False`` = authoritative ``eval/`` semantics (lost units vanish). ``True`` reproduces
    ``env.py``, which keeps lost units in in-transit forever."""

    _cohorts: list[Cohort] = field(default_factory=list, repr=False)
    _lost_total: float = 0.0
    _dispatched_total: float = 0.0
    _delivered_total: float = 0.0

    def __post_init__(self) -> None:
        for period, lt in enumerate(self.realization.lead_times, start=1):
            if math.isinf(lt):
                continue
            if lt < 0:
                raise ValueError(
                    f"period {period}: negative lead time {lt}. The reference implementation "
                    "would schedule such an order into the past, where it is never popped and "
                    "silently strands in transit forever."
                )

    # -- protocol -----------------------------------------------------------

    def dispatch(self, period: int, qty: float) -> None:
        """Schedule ``qty`` ordered at ``period``. A lost shipment creates no cohort."""
        lead_time = self._lead_time(period)
        self._dispatched_total += qty
        if math.isinf(lead_time):
            self._lost_total += qty
            return
        # int() truncation toward zero, matching the reference's `int(actual_lead_time)`.
        self._cohorts.append(Cohort(quantity=qty, remaining=int(lead_time)))

    def receive(self, period: int) -> float:
        """Deliver completed cohorts, then advance the transit clock unless ``period`` is paused."""
        arrived = 0.0
        still_moving: list[Cohort] = []
        for cohort in self._cohorts:
            if cohort.remaining == 0:
                arrived += cohort.quantity
            else:
                still_moving.append(cohort)

        if not self._is_paused(period):
            for cohort in still_moving:
                cohort.remaining -= 1

        self._cohorts = still_moving
        self._delivered_total += arrived
        return arrived

    def in_transit_total(self, period: int) -> float:
        """Scalar in-transit inventory, with no shipment ages exposed.

        ``period`` is unused: the cohort clock already encodes position. It stays in the
        signature because :class:`~collie.contracts.SupplyProcess` declares it, and a
        supply process that *does* need the period must remain substitutable here.
        """
        total = math.fsum(c.quantity for c in self._cohorts)
        if self.lost_orders_visible:
            total += self._lost_total
        return total

    # -- diagnostics (evaluation side only) ---------------------------------

    @property
    def lost_total(self) -> float:
        return self._lost_total

    @property
    def dispatched_total(self) -> float:
        return self._dispatched_total

    @property
    def delivered_total(self) -> float:
        return self._delivered_total

    @property
    def undelivered_total(self) -> float:
        """Units dispatched that never landed: lost shipments plus anything still moving."""
        return self._dispatched_total - self._delivered_total

    # -- internals ----------------------------------------------------------

    def _lead_time(self, period: int) -> float:
        lead_times = self.realization.lead_times
        if not 1 <= period <= len(lead_times):
            raise IndexError(
                f"period {period} is outside the supply realization (1..{len(lead_times)})"
            )
        return lead_times[period - 1]

    def _is_paused(self, period: int) -> bool:
        pause = self.realization.pause_active
        if not pause:
            return False
        if not 1 <= period <= len(pause):
            return False
        return pause[period - 1]


@dataclass(slots=True)
class ArrivalKeyedSupply:
    """Literal transcription of the reference in-transit dict. Test oracle only.

    Kept deliberately naive and pause-free so the equivalence suite compares
    :class:`LeadTimeSupply` against the reference's *actual shape*, not against a second copy
    of our own reasoning. Production code uses :class:`LeadTimeSupply`.
    """

    realization: SupplyRealization
    _in_transit: dict[int, float] = field(default_factory=dict, repr=False)

    def dispatch(self, period: int, qty: float) -> None:
        lead_time = self.realization.lead_times[period - 1]
        if math.isinf(lead_time):
            return
        arrival_period = period + int(lead_time)
        self._in_transit[arrival_period] = self._in_transit.get(arrival_period, 0.0) + qty

    def receive(self, period: int) -> float:
        return self._in_transit.pop(period, 0.0)

    def in_transit_total(self, period: int) -> float:
        return math.fsum(self._in_transit.values())
