"""Observation models: what a controller may see at decision time.

Two modes, and the difference between them is substantive rather than cosmetic
(``docs/env_contract.md`` §4):

``UNCENSORED`` reproduces the official policy interface exactly. The benchmark hands the policy
``previous_demand`` — the *true* demand of the prior period, even if a stockout meant part of it
was never sold. Arm 1 must be run this way for its number to be comparable to the published
figure.

``CENSORED`` replaces demand with what a real operator records: units sold, plus an availability
indicator. Availability is derived only from observables (``on_hand`` at the end of the prior
period), so it reveals nothing hidden while still marking which sales figures are right-censored.
This is a different observation model, and the derivation note treats results under it as
empirical-only.

Period 1 carries ``0.0`` on the active channel rather than ``None``. That is the reference's own
initialization (``previous_demand = 0.0`` before the loop), not a measurement, and matching it
keeps arm 1 bit-identical to the official runner.
"""

from __future__ import annotations

from dataclasses import dataclass

from collie.contracts import (
    AlertMessage,
    EpisodeSpec,
    ObservationMode,
    PeriodObservation,
)

__all__ = ["PriorPeriod", "build_observation"]


@dataclass(frozen=True, slots=True)
class PriorPeriod:
    """Realized quantities from period ``t-1``, before any censoring is applied."""

    demand: float
    units_sold: float
    on_hand_end: float
    order_quantity: float
    arrivals: float


def build_observation(
    spec: EpisodeSpec,
    *,
    period: int,
    date: str,
    on_hand: float,
    in_transit_total: float,
    profit_per_unit: float,
    holding_cost_per_unit: float,
    prior: PriorPeriod | None,
    alert: AlertMessage | None = None,
) -> PeriodObservation:
    """Assemble the observation for ``period``.

    ``prior`` is ``None`` only at period 1. Per-period ``profit_per_unit`` and
    ``holding_cost_per_unit`` are passed explicitly because the benchmark carries them as
    columns; they happen to be constant within every shipped instance, but the runner reads the
    column rather than assuming that.
    """
    censored = spec.observation_mode is ObservationMode.CENSORED

    prev_demand: float | None
    prev_sales: float | None
    prev_availability: bool | None

    if prior is None:
        # Reference initialization, not an observation.
        prev_demand = None if censored else 0.0
        prev_sales = 0.0 if censored else None
        prev_availability = None
        prev_order = 0.0
        prev_arrivals = 0.0
    else:
        prev_demand = None if censored else prior.demand
        prev_sales = prior.units_sold if censored else None
        prev_availability = (prior.on_hand_end > 0.0) if censored else None
        prev_order = prior.order_quantity
        prev_arrivals = prior.arrivals

    return PeriodObservation(
        period=period,
        date=date,
        on_hand=on_hand,
        in_transit_total=in_transit_total,
        prev_order=prev_order,
        prev_arrivals=prev_arrivals,
        profit_per_unit=profit_per_unit,
        holding_cost_per_unit=holding_cost_per_unit,
        promised_lead_time=spec.promised_lead_time,
        prev_demand=prev_demand,
        prev_sales=prev_sales,
        prev_availability=prev_availability,
        product_text=spec.product_text,
        alert=alert,
    )
