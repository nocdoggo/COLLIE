"""Demand shock families 1-3 (Task 6.2): persistent increase, persistent decrease, pulse.

The effect is **multiplicative on the baseline draw**, never a re-draw, which is what lets the
twin share the pre-onset path exactly: scaling and rounding are applied to a copy of the same
integer cells the twin keeps. Onset is drawn ``U{14..22}`` on the onset stream and recorded only
in the incident; nothing in the emitted series marks it.

Families 1 and 2 are persistent: the registered duration is the run from onset to horizon, and
``params.duration`` is not consulted for them (the family *is* the persistence). Family 3 pulses
for 2-4 periods, truncating at the horizon.
"""

from __future__ import annotations

import numpy as np

from collie.contracts import HiddenIncident
from collie.data.families.base import (
    FAMILY_SHOCK,
    TRAIN_PERIODS,
    FamilyParams,
    GeneratedEpisode,
    as_demand_cells,
    draw_baseline,
    draw_onset,
    episode_rngs,
)

__all__ = ["DEMAND_FAMILIES", "MAGNITUDE_SETS", "PULSE_DURATION", "generate"]

DEMAND_FAMILIES = (1, 2, 3)

MAGNITUDE_SETS: dict[int, tuple[float, ...]] = {
    1: (1.25, 1.5),
    2: (0.6, 0.75),
    3: (1.5, 2.0),
}
"""Registered multiplier sets per numbered family (brief §3.5)."""

PULSE_DURATION = (2, 4)
"""Family 3 duration range, inclusive."""


def _validate_magnitude(family: int, magnitude: float) -> None:
    if family in (1, 3) and magnitude <= 1.0:
        raise ValueError(
            f"family {family} is an increase; magnitude must exceed 1, got {magnitude}"
        )
    if family == 2 and not 0.0 < magnitude < 1.0:
        raise ValueError(f"family 2 is a decrease; magnitude must lie in (0, 1), got {magnitude}")


def generate(*, seed: int, horizon: int, params: FamilyParams) -> GeneratedEpisode:
    """Generate one shocked demand episode plus its unshocked twin from one seed."""
    if params.family not in DEMAND_FAMILIES:
        raise ValueError(
            f"demand.generate handles families {DEMAND_FAMILIES}, got {params.family}; "
            "supply families live in collie.data.families.supply"
        )
    rngs = episode_rngs(seed)
    onset = params.onset if params.onset is not None else draw_onset(rngs.onset)
    if onset > horizon:
        raise ValueError(
            f"onset {onset} is beyond the horizon {horizon}: the shock would never materialize "
            "and the twin would equal the episode everywhere"
        )
    magnitude = (
        params.magnitude
        if params.magnitude is not None
        else float(rngs.params.choice(MAGNITUDE_SETS[params.family]))
    )
    _validate_magnitude(params.family, magnitude)

    if params.family == 3:
        duration = (
            params.duration
            if params.duration is not None
            else int(rngs.params.integers(PULSE_DURATION[0], PULSE_DURATION[1] + 1))
        )
        if duration < 1:
            raise ValueError(f"pulse duration must be >= 1, got {duration}")
    else:
        duration = horizon - onset + 1

    baseline = draw_baseline(rngs.baseline, params.baseline, horizon)
    last = min(horizon, onset + duration - 1)
    scaled = as_demand_cells(np.asarray(baseline[onset - 1 : last]) * magnitude)
    demand = (*baseline[: onset - 1], *scaled, *baseline[last:])

    lead_times = (float(params.baseline_lead_time),) * horizon
    incident = HiddenIncident(
        family=FAMILY_SHOCK[params.family],
        onset_period=onset,
        magnitude=magnitude,
        duration=last - onset + 1,
        conditional_independence=True,  # demand-only families perturb a single stream
        seed=seed,
    )
    return GeneratedEpisode(
        demand=demand,
        lead_times=lead_times,
        pause_active=(),
        incident=incident,
        twin_demand=baseline,
        twin_lead_times=lead_times,
        train_demand=draw_baseline(rngs.train, params.baseline, TRAIN_PERIODS),
    )
