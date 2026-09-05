"""The null-audit bank (Task 8.5, R5): 1,000 well-specified nulls plus 300 fragility episodes.

The bank measures the **pipeline's** false-activation rate, so every episode is an ordinary
unshocked instance on disk (no ``incident.json``, no sidecar) paired with a fixed alert
schedule. Five strata mirror the registered conditional laws the theorem-backed headline cells
use; stationary IID is one sanity stratum, not the whole bank.

| stratum | registered law | implementation |
|---|---|---|
| stationary IID | fixed mean and variance | ``BaselineSpec()`` (p01 v1 anchor) |
| seasonal | registered seasonal mean | period 10, amplitude 30 (p07 v1) |
| overdispersed | registered dispersion | negative binomial, sd 50 |
| dependent | registered AR structure | AR(1), phi 0.7 (p10 v1) |
| censored | sales given availability | stationary demand, CENSORED observation mode |

Fragility episodes carry no target shock but **violate** the registered law: an IID-registered
episode that is actually autocorrelated, a variance change at mid-episode, unmodelled
seasonality, or outliers. They are reported separately and never pooled with the 1,000.

Non-reuse (R5.5) is structural: the bank lives at seeds ``NULL_BANK_BASE + i`` reserved in the
registry, every row carries ``split = null_audit``, and a test asserts no tuning, compiler, or
confirmatory code path references the bank's seed range.

One null-audit episode is one independent exogenous trajectory with one fixed alert schedule and
at most two proposal opportunities — the registered ``PROPOSAL_PERIODS``, constant across the
bank so the schedule is preregistrable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from collie.contracts import ObservationMode, Split
from collie.data.families.base import (
    DEFAULT_BASELINE_LEAD_TIME,
    TRAIN_PERIODS,
    BaselineKind,
    BaselineSpec,
    as_demand_cells,
    draw_baseline,
    episode_rngs,
)
from collie.data.splits import NULL_BANK_BASE

__all__ = [
    "BANK_SIZE",
    "FRAGILITY_SIZE",
    "PROPOSAL_PERIODS",
    "STRATUM_BASELINE",
    "FragilityViolation",
    "NullAlertSchedule",
    "NullEpisode",
    "NullGroup",
    "NullRow",
    "NullStratum",
    "build_nullbank",
    "generate_null_episode",
]

BANK_SIZE = 1_000
FRAGILITY_SIZE = 300
STRATUM_SIZE = 200

PROPOSAL_PERIODS = (12, 24)
"""Registered proposal opportunities: one before the shock window, one after its midpoint."""


class NullStratum(StrEnum):
    STATIONARY_IID = "stationary_iid"
    SEASONAL = "seasonal"
    OVERDISPERSED = "overdispersed"
    DEPENDENT = "dependent"
    CENSORED = "censored"


class FragilityViolation(StrEnum):
    AUTOCORRELATION = "unexpected_autocorrelation"
    VARIANCE_CHANGE = "variance_change"
    SEASONALITY = "unmodelled_seasonality"
    OUTLIERS = "outliers"


class NullGroup(StrEnum):
    WELL_SPECIFIED = "well_specified"
    FRAGILITY = "fragility"


class NullAlertSchedule(StrEnum):
    SILENT = "silent"
    NEUTRAL = "neutral"
    FALSE = "false"
    DISTRACTOR = "distractor"


_SCHEDULES = tuple(NullAlertSchedule)

STRATUM_BASELINE: dict[NullStratum, BaselineSpec] = {
    NullStratum.STATIONARY_IID: BaselineSpec(BaselineKind.STATIONARY_IID),
    NullStratum.SEASONAL: BaselineSpec(BaselineKind.SEASONAL),
    NullStratum.OVERDISPERSED: BaselineSpec(BaselineKind.OVERDISPERSED, sd=50.0),
    NullStratum.DEPENDENT: BaselineSpec(BaselineKind.DEPENDENT),
    # The censored stratum shares the stationary law; what changes is the observation model.
    NullStratum.CENSORED: BaselineSpec(BaselineKind.STATIONARY_IID),
}

# Fragility laws: each violates the registered IID null in one named way.
_FRAGILITY_AUTOCORRELATION_PHI = 0.5
_FRAGILITY_VARIANCE_RATIO = 2.0
_FRAGILITY_SEASONAL_AMPLITUDE = 30.0
_FRAGILITY_SEASONAL_PERIOD = 10
_FRAGILITY_N_OUTLIERS = 3
_FRAGILITY_OUTLIER_MULTIPLIER = 4.0


@dataclass(frozen=True, slots=True)
class NullRow:
    """One bank episode's registration row."""

    null_id: str
    seed: int
    split: Split  # always NULL_AUDIT
    group: NullGroup
    stratum: NullStratum | None  # set for the well-specified group
    violation: FragilityViolation | None  # set for the fragility group
    schedule: NullAlertSchedule
    alert_period: int | None  # None on silent schedules
    observation_mode: ObservationMode
    proposal_periods: tuple[int, int]
    horizon: int
    relpath: str


@dataclass(frozen=True, slots=True)
class NullEpisode:
    """One unshocked trajectory. No twin, no incident: there is nothing to pair or hide."""

    demand: tuple[float, ...]
    lead_times: tuple[float, ...]
    train_demand: tuple[float, ...]


def _alert_period(seed: int, schedule: NullAlertSchedule) -> int | None:
    if schedule is NullAlertSchedule.SILENT:
        return None
    rngs = episode_rngs(seed)
    return int(rngs.params.integers(10, 21))


def build_nullbank(horizon: int = 50) -> tuple[NullRow, ...]:
    """All 1,300 rows: 200 per stratum, then 75 per fragility violation, schedules balanced
    over silent / neutral / false / distractor in both groups."""
    rows: list[NullRow] = []
    for s, stratum in enumerate(NullStratum):
        for j in range(STRATUM_SIZE):
            i = s * STRATUM_SIZE + j
            schedule = _SCHEDULES[j % len(_SCHEDULES)]
            seed = NULL_BANK_BASE + i
            rows.append(
                NullRow(
                    null_id=f"nb{i:04d}",
                    seed=seed,
                    split=Split.NULL_AUDIT,
                    group=NullGroup.WELL_SPECIFIED,
                    stratum=stratum,
                    violation=None,
                    schedule=schedule,
                    alert_period=_alert_period(seed, schedule),
                    observation_mode=(
                        ObservationMode.CENSORED
                        if stratum is NullStratum.CENSORED
                        else ObservationMode.UNCENSORED
                    ),
                    proposal_periods=PROPOSAL_PERIODS,
                    horizon=horizon,
                    relpath=f"null_audit/{stratum.value}/nb{i:04d}",
                )
            )
    for v, violation in enumerate(FragilityViolation):
        for j in range(FRAGILITY_SIZE // len(FragilityViolation)):
            i = BANK_SIZE + v * (FRAGILITY_SIZE // len(FragilityViolation)) + j
            # balanced globally across the fragility group: 75 per schedule exactly
            schedule = _SCHEDULES[(i - BANK_SIZE) % len(_SCHEDULES)]
            seed = NULL_BANK_BASE + i
            rows.append(
                NullRow(
                    null_id=f"nb{i:04d}",
                    seed=seed,
                    split=Split.NULL_AUDIT,
                    group=NullGroup.FRAGILITY,
                    stratum=None,
                    violation=violation,
                    schedule=schedule,
                    alert_period=_alert_period(seed, schedule),
                    observation_mode=ObservationMode.UNCENSORED,
                    proposal_periods=PROPOSAL_PERIODS,
                    horizon=horizon,
                    relpath=f"null_audit/fragility/{violation.value}/nb{i:04d}",
                )
            )
    return tuple(rows)


def generate_null_episode(row: NullRow) -> NullEpisode:
    """Generate the trajectory for one bank row. Well-specified rows follow their stratum's
    registered law exactly; fragility rows violate the IID null as registered above."""
    rngs = episode_rngs(row.seed)
    spec = STRATUM_BASELINE[row.stratum] if row.stratum is not None else BaselineSpec()

    if row.group is NullGroup.WELL_SPECIFIED:
        demand = draw_baseline(rngs.baseline, spec, row.horizon)
    else:
        iid = BaselineSpec(BaselineKind.STATIONARY_IID)
        match row.violation:
            case FragilityViolation.AUTOCORRELATION:
                demand = draw_baseline(
                    rngs.baseline,
                    BaselineSpec(BaselineKind.DEPENDENT, ar_phi=_FRAGILITY_AUTOCORRELATION_PHI),
                    row.horizon,
                )
            case FragilityViolation.VARIANCE_CHANGE:
                # Same draws, doubled deviation from the mean after the midpoint.
                base = np.asarray(draw_baseline(rngs.baseline, iid, row.horizon))
                half = row.horizon // 2
                base[half:] = spec.mean + (base[half:] - spec.mean) * _FRAGILITY_VARIANCE_RATIO
                demand = as_demand_cells(base)
            case FragilityViolation.SEASONALITY:
                base = np.asarray(draw_baseline(rngs.baseline, iid, row.horizon))
                t = np.arange(row.horizon)
                demand = as_demand_cells(
                    base
                    + _FRAGILITY_SEASONAL_AMPLITUDE
                    * np.sin(2.0 * np.pi * t / _FRAGILITY_SEASONAL_PERIOD)
                )
            case FragilityViolation.OUTLIERS:
                cells = list(draw_baseline(rngs.baseline, iid, row.horizon))
                picks = rngs.params.choice(row.horizon, size=_FRAGILITY_N_OUTLIERS, replace=False)
                for t in picks:
                    # registered violation: 4x the mean, not 4x the cell, so the magnitude
                    # is unambiguous whatever the underlying draw was
                    cells[int(t)] = _FRAGILITY_OUTLIER_MULTIPLIER * spec.mean
                demand = tuple(cells)
            case _:  # pragma: no cover - StrEnum is exhaustive above
                raise ValueError(f"unhandled violation {row.violation}")

    train = draw_baseline(rngs.train, spec, TRAIN_PERIODS)
    return NullEpisode(
        demand=demand,
        lead_times=(float(DEFAULT_BASELINE_LEAD_TIME),) * row.horizon,
        train_demand=train,
    )
