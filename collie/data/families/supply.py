"""Supply shock families 4-6 (Task 7): lead-time shift, lost-shipment burst, compound+pause.

Families 4 and 5 ride on the per-period ``lead_time`` column of ``test.csv`` — no sidecar is
needed (env contract §7): the shift rewrites the column from onset onward, and a lost shipment
is ``inf`` on the affected order periods. Family 6 is the one family that needs ``supply.csv``:
both harnesses fix ``arrival_day`` at order time, and a transit pause must freeze cohorts
*already in transit*, which no order-time lead time can express.

Pause semantics are the frozen ones of ``collie/sim/supply.py`` (env contract §8.3), consistent
with Stockpyl's transit-pausing disruption type (research notes §3): a pause freezes the transit
clock of cohorts still moving, never holds back a cohort whose transit is already complete, and
delays each still-moving cohort by exactly the pause length. The generator emits only the
``pause_active`` column; the physics is the runner's.

For the pure supply families (4, 5) the demand path is the twin's: the divergence shows up in
``lead_times``, not in ``demand``, and ``magnitude`` stays 1.0 following the fixture convention
(``fakes/fake_generator.py``). Family 6 is compound: one incident drives both streams, so
``conditional_independence`` is **False** — derivation note §7 prohibits multiplying marginal
likelihood ratios for it, and module 05 reads this flag to choose the joint path.
"""

from __future__ import annotations

import math

import numpy as np

from collie.contracts import HiddenIncident, SupplyEffect, SupplyEffectKind
from collie.data.families.base import (
    DEFAULT_BASELINE_LEAD_TIME,
    FAMILY_SHOCK,
    TRAIN_PERIODS,
    FamilyParams,
    GeneratedEpisode,
    as_demand_cells,
    draw_baseline,
    draw_onset,
    episode_rngs,
)

__all__ = [
    "COMPOUND_DURATION",
    "COMPOUND_MAGNITUDES",
    "COMPOUND_PAUSE",
    "LOSS_LENGTHS",
    "SHIFT_BASELINES",
    "SHIFT_DISRUPTED",
    "SUPPLY_FAMILIES",
    "generate",
]

SUPPLY_FAMILIES = (4, 5, 6)

SHIFT_BASELINES = (1, 2)
SHIFT_DISRUPTED = (3, 4)
LOSS_LENGTHS = (1, 3)  # inclusive range of consecutive lost order periods

COMPOUND_MAGNITUDES = (1.25, 1.5)
COMPOUND_DURATION = (6, 10)  # inclusive demand-multiplier duration
COMPOUND_PAUSE = (3, 5)  # inclusive transit-pause length, starting at onset


def _shift(
    horizon: int, onset: int, params: FamilyParams, rngs
) -> tuple[tuple[float, ...], SupplyEffect, int, int]:
    baseline_lt = (
        params.baseline_lead_time
        if params.baseline_lead_time is not None
        else int(rngs.params.choice(SHIFT_BASELINES))
    )
    if baseline_lt not in SHIFT_BASELINES:
        raise ValueError(f"family 4 baseline lead time must be in {SHIFT_BASELINES}")
    disrupted_lt = (
        params.disrupted_lead_time
        if params.disrupted_lead_time is not None
        else int(rngs.params.choice(SHIFT_DISRUPTED))
    )
    if disrupted_lt not in SHIFT_DISRUPTED or disrupted_lt <= baseline_lt:
        raise ValueError(
            f"family 4 disrupted lead time must be in {SHIFT_DISRUPTED} and exceed the "
            f"baseline, got {disrupted_lt} against baseline {baseline_lt}"
        )
    duration = horizon - onset + 1
    lead_times = (float(baseline_lt),) * (onset - 1) + (float(disrupted_lt),) * duration
    effect = SupplyEffect(
        SupplyEffectKind.LEAD_TIME_SHIFT, onset, duration, disrupted_lead_time=disrupted_lt
    )
    return lead_times, effect, baseline_lt, duration


def _loss(
    horizon: int, onset: int, params: FamilyParams, rngs
) -> tuple[tuple[float, ...], SupplyEffect, int, int]:
    baseline_lt = (
        params.baseline_lead_time
        if params.baseline_lead_time is not None
        else DEFAULT_BASELINE_LEAD_TIME
    )
    if baseline_lt < 0:
        raise ValueError(f"baseline lead time must be non-negative, got {baseline_lt}")
    loss_length = (
        params.loss_length
        if params.loss_length is not None
        else int(rngs.params.integers(LOSS_LENGTHS[0], LOSS_LENGTHS[1] + 1))
    )
    if loss_length < 1:
        raise ValueError(f"loss burst must cover at least one period, got {loss_length}")
    duration = min(loss_length, horizon - onset + 1)
    lead_times = tuple(
        math.inf if onset - 1 <= t < onset - 1 + duration else float(baseline_lt)
        for t in range(horizon)
    )
    effect = SupplyEffect(SupplyEffectKind.SHIPMENT_LOSS, onset, duration)
    return lead_times, effect, baseline_lt, duration


def generate(*, seed: int, horizon: int, params: FamilyParams) -> GeneratedEpisode:
    """Generate one supply-shocked episode plus its unshocked twin from one seed."""
    if params.family not in SUPPLY_FAMILIES:
        raise ValueError(
            f"supply.generate handles families {SUPPLY_FAMILIES}, got {params.family}; "
            "demand families live in collie.data.families.demand"
        )
    rngs = episode_rngs(seed)
    onset = params.onset if params.onset is not None else draw_onset(rngs.onset)
    if onset > horizon:
        raise ValueError(
            f"onset {onset} is beyond the horizon {horizon}: the shock would never materialize "
            "and the twin would equal the episode everywhere"
        )

    baseline = draw_baseline(rngs.baseline, params.baseline, horizon)
    demand = baseline
    pause: tuple[bool, ...] = ()
    magnitude = 1.0
    conditional_independence = True

    if params.family == 4:
        lead_times, effect, baseline_lt, duration = _shift(horizon, onset, params, rngs)
    elif params.family == 5:
        lead_times, effect, baseline_lt, duration = _loss(horizon, onset, params, rngs)
    else:
        # Family 6, compound: a demand multiplier for 6-10 periods with a 3-5 period transit
        # pause starting at onset. Params stream order is fixed: magnitude, duration, pause.
        baseline_lt = (
            params.baseline_lead_time
            if params.baseline_lead_time is not None
            else DEFAULT_BASELINE_LEAD_TIME
        )
        if baseline_lt < 1:
            raise ValueError(
                f"family 6 needs a pipeline to freeze; baseline lead time must be >= 1, "
                f"got {baseline_lt}"
            )
        magnitude = (
            params.magnitude
            if params.magnitude is not None
            else float(rngs.params.choice(COMPOUND_MAGNITUDES))
        )
        if magnitude <= 1.0:
            raise ValueError(f"family 6 is an increase; magnitude must exceed 1, got {magnitude}")
        duration = (
            params.duration
            if params.duration is not None
            else int(rngs.params.integers(COMPOUND_DURATION[0], COMPOUND_DURATION[1] + 1))
        )
        if duration < 1:
            raise ValueError(f"compound duration must be >= 1, got {duration}")
        pause_length = (
            params.pause_length
            if params.pause_length is not None
            else int(rngs.params.integers(COMPOUND_PAUSE[0], COMPOUND_PAUSE[1] + 1))
        )
        if pause_length < 1:
            raise ValueError(f"pause length must be >= 1, got {pause_length}")

        # The registered ranges must fit whole: a compound episode whose duration or pause is
        # truncated by the horizon is no longer a registered compound episode.
        room = horizon - onset + 1
        if room < COMPOUND_DURATION[0] or room < COMPOUND_PAUSE[0]:
            raise ValueError(
                f"family 6 at onset {onset} needs at least {COMPOUND_DURATION[0]} periods of "
                f"runway (duration 6-10, pause 3-5), got {room} (horizon {horizon})"
            )
        duration = min(duration, room)
        pause_length = min(pause_length, room)
        last = onset - 1 + duration
        demand = (
            *baseline[: onset - 1],
            *as_demand_cells(np.asarray(baseline[onset - 1 : last]) * magnitude),
            *baseline[last:],
        )
        pause = tuple(onset - 1 <= t < onset - 1 + pause_length for t in range(horizon))
        lead_times = (float(baseline_lt),) * horizon
        effect = SupplyEffect(SupplyEffectKind.TRANSIT_PAUSE, onset, pause_length)
        conditional_independence = False

    incident = HiddenIncident(
        family=FAMILY_SHOCK[params.family],
        onset_period=onset,
        magnitude=magnitude,
        duration=duration,
        conditional_independence=conditional_independence,
        supply_effect=effect,
        seed=seed,
    )
    return GeneratedEpisode(
        demand=demand,
        lead_times=lead_times,
        pause_active=pause,
        incident=incident,
        twin_demand=baseline,
        twin_lead_times=(float(baseline_lt),) * horizon,
        train_demand=draw_baseline(rngs.train, params.baseline, TRAIN_PERIODS),
    )
