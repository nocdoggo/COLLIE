"""Shared hypothesis strategies for the arms/harness suite (brief §9.1).

``tests/strategies.py`` owns the generator-side strategies (seeds, horizons, family params);
this module owns the arms-side ones. Import from there rather than redefining, so a registered
range that moves moves everywhere at once.
"""

from __future__ import annotations

from collections.abc import Sequence

from hypothesis import strategies as st

from collie.contracts import AlertMessage, PeriodObservation
from tests.strategies import seeds  # re-exported so arms tests share the generator's seed space

__all__ = [
    "alert_placements",
    "budgets",
    "decoding",
    "demand_streams",
    "make_observations",
    "periods",
    "seeds",
    "windows",
]

periods = st.integers(min_value=1, max_value=50)
windows = st.integers(min_value=0, max_value=10)
budgets = st.integers(min_value=0, max_value=20)
# Demand cells are integer-valued (env contract §8.1); the strategies match that domain rather
# than the brief's float sketch, which would test a domain we never emit.
demand_streams = st.lists(st.integers(min_value=0, max_value=500), min_size=5, max_size=60)
alert_placements = st.lists(periods, max_size=8, unique=True)
decoding = st.sampled_from(["det-v1", "seed-1", "seed-2", "seed-3"])


def make_observations(
    demands: Sequence[float],
    *,
    alert_at: Sequence[int] = (),
    promised_lead_time: int = 2,
) -> list[PeriodObservation]:
    """Build the observation stream of an episode with demand path ``demands``.

    The observation at period ``t`` carries ``prev_demand = demands[t-2]`` (0.0 at period 1, the
    reference's pre-loop initialisation). Everything a trigger may not read is held at a neutral
    constant, so a test that accidentally depends on inventory state is testing nothing.
    """
    alerts = {
        p: AlertMessage(alert_id=f"alert_{p}", period=p, text=f"advisory at period {p}")
        for p in alert_at
    }
    return [
        PeriodObservation(
            period=t,
            date=f"Period_{t}",
            on_hand=0.0,
            in_transit_total=0.0,
            prev_order=0.0,
            prev_arrivals=0.0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
            promised_lead_time=promised_lead_time,
            prev_demand=0.0 if t == 1 else float(demands[t - 2]),
            alert=alerts.get(t),
        )
        for t in range(1, len(demands) + 1)
    ]
