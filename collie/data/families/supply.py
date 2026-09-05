"""Supply shock families 4-5 (Task 7.1-7.2): persistent lead-time shift, lost-shipment burst.

Both ride on the per-period ``lead_time`` column of ``test.csv`` — no sidecar is needed (env
contract §7): the shift rewrites the column from onset onward, and a lost shipment is ``inf`` on
the affected order periods. Family 6 (transit pause) is the only family that needs
``supply.csv`` and lives in wave 4.

For supply families the demand path is the twin's: the divergence shows up in ``lead_times``,
not in ``demand``. ``magnitude`` follows the fixture convention (``fakes/fake_generator.py``)
and stays 1.0; the load-bearing parameter travels in ``supply_effect.disrupted_lead_time``.
"""

from __future__ import annotations

import math

from collie.contracts import HiddenIncident, SupplyEffect, SupplyEffectKind
from collie.data.families.base import (
    DEFAULT_BASELINE_LEAD_TIME,
    FAMILY_SHOCK,
    TRAIN_PERIODS,
    FamilyParams,
    GeneratedEpisode,
    draw_baseline,
    draw_onset,
    episode_rngs,
)

__all__ = ["LOSS_LENGTHS", "SHIFT_BASELINES", "SHIFT_DISRUPTED", "SUPPLY_FAMILIES", "generate"]

SUPPLY_FAMILIES = (4, 5)

SHIFT_BASELINES = (1, 2)
SHIFT_DISRUPTED = (3, 4)
LOSS_LENGTHS = (1, 3)  # inclusive range of consecutive lost order periods


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

    if params.family == 4:
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
            SupplyEffectKind.LEAD_TIME_SHIFT,
            onset,
            duration,
            disrupted_lead_time=disrupted_lt,
        )
    else:
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

    baseline = draw_baseline(rngs.baseline, params.baseline, horizon)
    twin_lead_times = (float(baseline_lt),) * horizon
    incident = HiddenIncident(
        family=FAMILY_SHOCK[params.family],
        onset_period=onset,
        magnitude=1.0,
        duration=duration,
        conditional_independence=True,  # supply-only families perturb a single stream
        supply_effect=effect,
        seed=seed,
    )
    return GeneratedEpisode(
        demand=baseline,
        lead_times=lead_times,
        pause_active=(),
        incident=incident,
        twin_demand=baseline,
        twin_lead_times=twin_lead_times,
        train_demand=draw_baseline(rngs.train, params.baseline, TRAIN_PERIODS),
    )
