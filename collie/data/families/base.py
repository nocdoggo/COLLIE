"""Baseline demand processes and twin construction (Task 6.1).

The baseline is drawn from the stationary members of the official InventoryBench pattern
vocabulary (``docs/module01_research_notes.md`` §1), so a shocked episode is a perturbation of a
process the benchmark already contains rather than a new distribution a reviewer could attribute
the result to. The same process code serves the shocked families and, later, the registered null
laws of ``collie/data/nullbank.py``.

Twin construction. Families scale a *copy* of the baseline draw from onset onward, so the shocked
series and its twin agree on every pre-onset cell by construction, not by tolerance. Rounding is
applied to the same underlying draw on both sides, which is what makes the pre-onset invariance a
structural property instead of a numerical coincidence.

Seeding follows NEP 19: one ``SeedSequence`` per episode, sub-streams spawned in a fixed
positional order, explicit ``Generator`` threading, no global state. Bitwise reproducibility
rests on the pinned numpy in ``uv.lock`` plus the byte-stability tests, never on unseeded draws.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from collie.contracts import HiddenIncident, ShockFamily

__all__ = [
    "DEFAULT_BASELINE_LEAD_TIME",
    "FAMILY_SHOCK",
    "ONSET_HI",
    "ONSET_LO",
    "TRAIN_PERIODS",
    "BaselineKind",
    "BaselinePair",
    "BaselineSpec",
    "EpisodeRngs",
    "FamilyParams",
    "GeneratedEpisode",
    "as_demand_cells",
    "draw_baseline",
    "draw_onset",
    "episode_rngs",
    "generate_baseline",
]

ONSET_LO = 14
ONSET_HI = 22
"""Onset is uniform on {14..22} for every family and recorded only in incident.json."""

TRAIN_PERIODS = 5
"""Every official synthetic train.csv carries exactly five rows (research notes §1)."""

DEFAULT_BASELINE_LEAD_TIME = 2
"""Fallback when ``params.baseline_lead_time`` is left to the seed. Matches the promised lead
time of the official stochastic subtree, whose actual law is centred on 2."""


class BaselineKind(StrEnum):
    """The registered baseline conditional laws; mirrors the five null-bank strata."""

    STATIONARY_IID = "stationary_iid"
    SEASONAL = "seasonal"
    OVERDISPERSED = "overdispersed"
    DEPENDENT = "dependent"


@dataclass(frozen=True, slots=True)
class BaselineSpec:
    """Parameters of one baseline demand process.

    Defaults anchor to official patterns (research notes §1): p01 v1 for the stationary kind,
    p07 v1 (period 10, amplitude 30) for seasonal, p10 v1 (phi 0.7, innovation sd 25, initial
    value equal to the mean) for dependent. The overdispersed kind registers its dispersion
    through ``sd`` and maps ``(mean, sd)`` onto a negative binomial.
    """

    kind: BaselineKind = BaselineKind.STATIONARY_IID
    mean: float = 100.0
    sd: float = 25.0
    seasonal_period: int = 10
    seasonal_amplitude: float = 30.0
    ar_phi: float = 0.7

    def __post_init__(self) -> None:
        if self.mean <= 0:
            raise ValueError(f"mean must be positive, got {self.mean}")
        if self.sd <= 0:
            raise ValueError(f"sd must be positive, got {self.sd}")
        if self.seasonal_period < 2:
            raise ValueError(f"seasonal_period must be >= 2, got {self.seasonal_period}")
        if not -1.0 < self.ar_phi < 1.0:
            raise ValueError(f"ar_phi must lie in (-1, 1), got {self.ar_phi}")


def as_demand_cells(draws: Sequence[float]) -> tuple[float, ...]:
    """Round half-up and clip at zero.

    Every official demand cell is integer-valued (env contract §8.1) and exact integer
    accounting is what makes the equivalence suite's 0.0 max-abs-diff possible, so emitted cells
    must be integers too. Half-up — ``floor(x + 0.5)`` — rather than Python's banker's rounding:
    deterministic, platform-independent, and the rule a reviewer would re-implement. Ties have
    measure zero under continuous draws; the clip matches the ``min = 0`` truncation visible in
    the official p01 v2 data.
    """
    rounded = np.floor(np.asarray(draws, dtype=float) + 0.5)
    return tuple(float(max(0.0, v)) for v in rounded)


def draw_baseline(rng: np.random.Generator, spec: BaselineSpec, horizon: int) -> tuple[float, ...]:
    """Draw ``horizon`` integer-valued demand cells from the registered baseline process."""
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")
    match spec.kind:
        case BaselineKind.STATIONARY_IID:
            raw: Sequence[float] = rng.normal(spec.mean, spec.sd, horizon)
        case BaselineKind.SEASONAL:
            t = np.arange(horizon)
            raw = (
                spec.mean
                + spec.seasonal_amplitude * np.sin(2.0 * np.pi * t / spec.seasonal_period)
                + rng.normal(0.0, spec.sd, horizon)
            )
        case BaselineKind.OVERDISPERSED:
            var = spec.sd**2
            if var <= spec.mean:
                raise ValueError(
                    f"overdispersed requires sd**2 > mean, got sd={spec.sd}, mean={spec.mean}"
                )
            # var = mean + mean**2 / k, so k = mean**2 / (var - mean) and p = mean / var.
            k = spec.mean**2 / (var - spec.mean)
            raw = rng.negative_binomial(k, spec.mean / var, horizon)
        case BaselineKind.DEPENDENT:
            innovations = rng.normal(0.0, spec.sd, horizon)
            path = np.empty(horizon)
            prev = spec.mean  # official p10: initial value 100, i.e. the long-run mean
            for i in range(horizon):
                prev = spec.mean + spec.ar_phi * (prev - spec.mean) + innovations[i]
                path[i] = prev
            raw = path
    return as_demand_cells(raw)


@dataclass(frozen=True, slots=True)
class EpisodeRngs:
    """The four independent sub-streams of one episode.

    Spawn order is fixed and positional — baseline, onset, params, train — and stream identity
    is never derived from set or dict iteration order, so regeneration is byte-stable across
    processes and machines (research notes §5).
    """

    baseline: np.random.Generator
    onset: np.random.Generator
    params: np.random.Generator
    train: np.random.Generator


def episode_rngs(seed: int) -> EpisodeRngs:
    """Derive one episode's sub-streams from its seed via ``SeedSequence.spawn``."""
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")
    children = np.random.SeedSequence(seed).spawn(4)
    return EpisodeRngs(*(np.random.Generator(np.random.PCG64(child)) for child in children))


def draw_onset(rng: np.random.Generator) -> int:
    """Onset is uniform on {14..22} inclusive and recorded only in ``incident.json``."""
    return int(rng.integers(ONSET_LO, ONSET_HI + 1))


FAMILY_SHOCK: dict[int, ShockFamily] = {
    1: ShockFamily.DEMAND_LEVEL,
    2: ShockFamily.DEMAND_LEVEL,
    3: ShockFamily.TEMPORARY_PULSE,
    4: ShockFamily.LEAD_TIME_SHIFT,
    5: ShockFamily.SHIPMENT_LOSS,
    6: ShockFamily.COMPOUND,
}
"""The numbered families of the brief (§3.5) map onto ``ShockFamily``. Families 1 and 2 share
``DEMAND_LEVEL`` and are distinguished by direction: 1 is always an increase, 2 always a
decrease. Splits and null-strata counts are stated per *numbered* family, so the number is the
primary key everywhere in this module."""


@dataclass(frozen=True, slots=True)
class FamilyParams:
    """Everything a family's ``generate`` needs besides the seed and horizon.

    Any field left ``None`` is drawn from the family's registered range on the params stream,
    so a seed alone reproduces the full episode; tests pin fields explicitly to recover them.
    Explicit values outside the registered sets are legitimate — the extrapolation slice
    (brief §3.6) is built from exactly such values — but they must keep the family's direction.
    """

    family: int
    baseline: BaselineSpec = BaselineSpec()
    onset: int | None = None
    magnitude: float | None = None
    duration: int | None = None
    baseline_lead_time: int | None = None
    disrupted_lead_time: int | None = None
    loss_length: int | None = None
    pause_length: int | None = None

    def __post_init__(self) -> None:
        if self.family not in FAMILY_SHOCK:
            raise ValueError(f"family must be one of {sorted(FAMILY_SHOCK)}, got {self.family}")
        if self.onset is not None and not ONSET_LO <= self.onset <= ONSET_HI:
            raise ValueError(f"onset must lie in {{{ONSET_LO}..{ONSET_HI}}}, got {self.onset}")


@dataclass(frozen=True, slots=True)
class GeneratedEpisode:
    """One shocked episode, with its twin and its hidden truth returned *alongside*.

    Mirrors ``collie/fakes/fake_generator.py``: hidden truth travels next to the observable
    episode, never inside it, so handing the whole object to a policy is a type-level mistake
    the isolation walk catches. ``train_demand`` extends the sketched interface: the writer
    needs it for ``train.csv`` and it must come from the same seed as everything else.
    """

    demand: tuple[float, ...]
    lead_times: tuple[float, ...]  # math.inf encodes a lost shipment
    pause_active: tuple[bool, ...]  # () when no pause
    incident: HiddenIncident
    twin_demand: tuple[float, ...]
    twin_lead_times: tuple[float, ...]
    train_demand: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class BaselinePair:
    """Wave-1 shape: one seed in, the baseline and its (still identical) twin out."""

    baseline: tuple[float, ...]
    twin: tuple[float, ...]
    train: tuple[float, ...]


def generate_baseline(*, seed: int, horizon: int, spec: BaselineSpec | None = None) -> BaselinePair:
    """Draw the baseline path, its twin, and the five train cells from one seed.

    No shock logic lives here. The twin is the same object as the baseline: with no shock
    applied there is nothing to distinguish, and later waves must construct theirs by scaling a
    copy so the pre-onset invariance stays structural.
    """
    spec = spec if spec is not None else BaselineSpec()
    rngs = episode_rngs(seed)
    baseline = draw_baseline(rngs.baseline, spec, horizon)
    train = draw_baseline(rngs.train, spec, TRAIN_PERIODS)
    return BaselinePair(baseline=baseline, twin=baseline, train=train)
