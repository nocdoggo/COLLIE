"""Seed registry, split construction, and the integrity suite (Task 8.1-8.4).

One seed-family pair is one **independent unit**; the four information conditions of a unit are
paired replays of a single incident, never four samples. ``Rollout.independent_unit_id`` is the
field module 07 aggregates over — the only thing preventing a fourfold overstatement of sample
size.

Seed layout (provisional in wave 3, frozen here):

```
seed(family, split, i) = family * 1_000_000 + base + i
  base: test 0, dev 50_000, cal 60_000
reserved ranges, disjoint by construction:
  extrapolation  family * 1_000_000 + 30_000 + i
  OOD            70_000_000 + i
  null controls  80_000_000 + i      (the 20 silent + 20 false-alert test controls)
  null bank      90_000_000 + ...    (wave 6; collie/data/nullbank.py consumes it)
```

Combo discipline: dev/cal draw severity x duration combos from set A only; set B is held out
and occurs only at test (``held_out_combo=True`` on the incident). The extrapolation slice uses
preregistered values inside wider family hulls that no split's main grid contains; the OOD slice
is one composition of familiar primitives (temporary pulse x shipment loss) that no family
produces. Both slices are built but not exercised this sprint (module brief, deferred section).

Baselines: main-split episodes use the stationary-IID registered law (p01 v1 anchor). The other
registered conditional laws are exercised through the null-bank strata, which is where the
calibration claim needs them (derivation note §9).

Alert **template slots** (``tpl_*``) are assigned here so the frozen assignments exist before any
test trajectory runs; module 03 binds text to slots. Slots are namespaced by split, which is what
makes integrity assertion 2 structural rather than aspirational.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from collie.contracts import (
    HiddenIncident,
    InformationCondition,
    ShockFamily,
    Split,
    SupplyEffect,
    SupplyEffectKind,
)
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
    "COMBO_A",
    "CONDITIONS",
    "EXTRAPOLATION_COMBO",
    "FAMILIES",
    "HELD_OUT_COMBO",
    "NULL_BANK_BASE",
    "NULL_CONTROL_BASE",
    "OOD_BASE",
    "SEEDS_PER_FAMILY",
    "Rollout",
    "RolloutSlice",
    "Unit",
    "assert_held_out_combos_absent",
    "assert_no_test_templates",
    "assert_seed_pools_disjoint",
    "assert_units_resolve",
    "build_rollouts",
    "build_units",
    "combo_params",
    "generate_ood_episode",
    "required_confirmatory_seeds",
    "seed_for",
]

FAMILIES = (1, 2, 3, 4, 5, 6)
SEEDS_PER_FAMILY = {Split.TEST: 25, Split.DEV: 6, Split.CAL: 4}
_SPLIT_BASE = {Split.TEST: 0, Split.DEV: 50_000, Split.CAL: 60_000}

EXTRAPOLATION_BASE = 30_000
EXTRAPOLATION_SEEDS_PER_FAMILY = 2
OOD_BASE = 70_000_000
NULL_CONTROL_BASE = 80_000_000
NULL_BANK_BASE = 90_000_000

N_SILENT_NULL = 20
N_FALSE_ALERT_NULL = 20

CONDITIONS = (
    InformationCondition.NO_ALERT,
    InformationCondition.EARLY_ACCURATE,
    InformationCondition.LATE_ACCURATE,
    InformationCondition.UNRELIABLE,
)


class RolloutSlice(StrEnum):
    MAIN = "main"
    HELD_OUT_COMBO = "held_out_combo"
    EXTRAPOLATION = "extrapolation"
    OOD = "ood"
    SILENT_NULL = "silent_null"
    FALSE_ALERT_NULL = "false_alert_null"


# ---------------------------------------------------------------------------
# combos
# ---------------------------------------------------------------------------

# Combo vocabulary per family: (magnitude,) for 1-2; (magnitude, duration) for 3;
# (baseline_lead, disrupted_lead) for 4; (loss_length, baseline_lead) for 5;
# (magnitude, duration, pause_length) for 6.
Combo = tuple[float, ...]

_COMBO_GRID: dict[int, tuple[Combo, ...]] = {
    1: ((1.25,), (1.5,)),
    2: ((0.6,), (0.75,)),
    3: ((1.5, 2.0), (1.5, 3.0), (1.5, 4.0), (2.0, 2.0), (2.0, 3.0), (2.0, 4.0)),
    4: ((1.0, 3.0), (1.0, 4.0), (2.0, 3.0), (2.0, 4.0)),
    5: ((1.0, 2.0), (2.0, 2.0), (3.0, 2.0)),
    6: tuple(
        (m, float(d), float(p)) for m in (1.25, 1.5) for d in range(6, 11) for p in range(3, 6)
    ),
}

HELD_OUT_COMBO: dict[int, Combo] = {
    1: (1.5,),
    2: (0.6,),
    3: (2.0, 4.0),
    4: (2.0, 4.0),
    5: (3.0, 2.0),
    6: (1.5, 10.0, 5.0),
}
"""Combo set B: the extreme corner of each family's grid, occurring only at test."""

EXTRAPOLATION_COMBO: dict[int, Combo] = {
    1: (1.35,),
    2: (0.7,),
    3: (1.75, 3.0),
    4: (1.0, 4.0),
    5: (2.0, 4.0),
    6: (1.35, 7.0, 4.0),
}
"""Preregistered unseen values inside wider family hulls. For the integer-grid families these
are unplayed *combinations* of registered values — (1→4) for family 4, a loss burst on a
baseline lead time of 4 for family 5 — which is why they are excluded from set A below."""

COMBO_A: dict[int, tuple[Combo, ...]] = {
    family: tuple(
        c for c in grid if c != HELD_OUT_COMBO[family] and c != EXTRAPOLATION_COMBO[family]
    )
    for family, grid in _COMBO_GRID.items()
}


def combo_params(family: int, combo: Combo) -> dict[str, float | int]:
    """Map a combo tuple onto ``FamilyParams`` fields."""
    match family:
        case 1 | 2:
            return {"magnitude": combo[0]}
        case 3:
            return {"magnitude": combo[0], "duration": int(combo[1])}
        case 4:
            return {"baseline_lead_time": int(combo[0]), "disrupted_lead_time": int(combo[1])}
        case 5:
            return {"loss_length": int(combo[0]), "baseline_lead_time": int(combo[1])}
        case 6:
            return {
                "magnitude": combo[0],
                "duration": int(combo[1]),
                "pause_length": int(combo[2]),
            }
        case _:  # pragma: no cover - FAMILIES is closed and validated elsewhere
            raise ValueError(f"no combo vocabulary for family {family}")


def combo_of_params(params: FamilyParams) -> Combo:
    """Invert :func:`combo_params`: the combo a params object encodes. The manifest records
    this per rollout so held-out-combo discipline is auditable from the artifact alone."""
    match params.family:
        case 1 | 2:
            return (params.magnitude,)
        case 3:
            return (params.magnitude, float(params.duration))
        case 4:
            return (float(params.baseline_lead_time), float(params.disrupted_lead_time))
        case 5:
            return (float(params.loss_length), float(params.baseline_lead_time))
        case 6:
            return (params.magnitude, float(params.duration), float(params.pause_length))
        case _:  # pragma: no cover - FamilyParams validates 1-6
            raise ValueError(f"no combo vocabulary for family {params.family}")


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def seed_for(family: int, split: Split, index: int) -> int:
    if family not in FAMILY_SHOCK:
        raise ValueError(f"family must be one of {FAMILIES}, got {family}")
    if not 0 <= index < SEEDS_PER_FAMILY[split]:
        raise ValueError(f"index {index} outside the {split} pool of {SEEDS_PER_FAMILY[split]}")
    return family * 1_000_000 + _SPLIT_BASE[split] + index


def seed_pools() -> dict[str, frozenset[int]]:
    """Every reserved seed range, keyed by pool name. The disjointness assertion runs over
    this, so a pool only counts as reserved once it is registered here."""
    pools: dict[str, frozenset[int]] = {}
    for split in (Split.TEST, Split.DEV, Split.CAL):
        pools[split.value] = frozenset(
            seed_for(f, split, i) for f in FAMILIES for i in range(SEEDS_PER_FAMILY[split])
        )
    pools["extrapolation"] = frozenset(
        f * 1_000_000 + EXTRAPOLATION_BASE + i
        for f in FAMILIES
        for i in range(EXTRAPOLATION_SEEDS_PER_FAMILY)
    )
    pools["ood"] = frozenset({OOD_BASE})
    pools["null_control"] = frozenset(
        NULL_CONTROL_BASE + i for i in range(N_SILENT_NULL + N_FALSE_ALERT_NULL)
    )
    pools["null_bank"] = frozenset(NULL_BANK_BASE + i for i in range(1300))
    return pools


# ---------------------------------------------------------------------------
# units and rollouts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Unit:
    """One independent seed-family pair. Its condition rollouts are paired replays."""

    independent_unit_id: str
    split: Split
    family: int | None  # None on the OOD unit, which is no single family
    seed: int
    slice: RolloutSlice
    params: FamilyParams | None
    promised_lead_time: int
    template_id: str | None
    held_out_combo: bool


@dataclass(frozen=True, slots=True)
class Rollout:
    """One episode-condition rollout. ``params``/``promised_lead_time`` are ``None`` on the
    null controls, which carry no shock and no family."""

    rollout_id: str
    split: Split
    family: int | None
    seed: int
    information_condition: InformationCondition
    independent_unit_id: str
    slice: RolloutSlice
    template_id: str | None
    promised_lead_time: int | None
    params: FamilyParams | None


def _promised_lead_time(params: FamilyParams) -> int:
    """The registered promise: the twin's constant baseline lead time (research notes §6)."""
    return (
        params.baseline_lead_time
        if params.baseline_lead_time is not None
        else DEFAULT_BASELINE_LEAD_TIME
    )


def _main_units(split: Split) -> tuple[Unit, ...]:
    units: list[Unit] = []
    for family in FAMILIES:
        for i in range(SEEDS_PER_FAMILY[split]):
            held_out = split is Split.TEST and i >= SEEDS_PER_FAMILY[split] - 5
            combo = (
                HELD_OUT_COMBO[family] if held_out else COMBO_A[family][i % len(COMBO_A[family])]
            )
            params = FamilyParams(family, **combo_params(family, combo))
            seed = seed_for(family, split, i)
            units.append(
                Unit(
                    independent_unit_id=f"unit-f{family}-s{seed}",
                    split=split,
                    family=family,
                    seed=seed,
                    slice=RolloutSlice.HELD_OUT_COMBO if held_out else RolloutSlice.MAIN,
                    params=params,
                    promised_lead_time=_promised_lead_time(params),
                    template_id=f"tpl_{split.value}_f{family}_{i:02d}",
                    held_out_combo=held_out,
                )
            )
    return tuple(units)


def _slice_units() -> tuple[Unit, ...]:
    """The extrapolation and OOD slices. Test-split seeds, flagged, outside the 640."""
    units: list[Unit] = []
    for family in FAMILIES:
        for i in range(EXTRAPOLATION_SEEDS_PER_FAMILY):
            params = FamilyParams(family, **combo_params(family, EXTRAPOLATION_COMBO[family]))
            seed = family * 1_000_000 + EXTRAPOLATION_BASE + i
            units.append(
                Unit(
                    independent_unit_id=f"unit-xf{family}-s{seed}",
                    split=Split.TEST,
                    family=family,
                    seed=seed,
                    slice=RolloutSlice.EXTRAPOLATION,
                    params=params,
                    promised_lead_time=_promised_lead_time(params),
                    template_id=f"tpl_test_xf{family}_{i:02d}",
                    held_out_combo=False,
                )
            )
    # OOD: one held-out composition of familiar primitives — a temporary demand pulse crossed
    # with a shipment-loss burst — that no single family produces. Parameters are all from the
    # registered ranges; only the composition is unseen. Generated by generate_ood_episode.
    units.append(
        Unit(
            independent_unit_id=f"unit-ood-s{OOD_BASE}",
            split=Split.TEST,
            family=None,
            seed=OOD_BASE,
            slice=RolloutSlice.OOD,
            params=None,
            promised_lead_time=DEFAULT_BASELINE_LEAD_TIME,
            template_id="tpl_test_ood_00",
            held_out_combo=False,
        )
    )
    return tuple(units)


def build_units(split: Split) -> tuple[Unit, ...]:
    units = list(_main_units(split))
    if split is Split.TEST:
        units.extend(_slice_units())
    return tuple(units)


def build_rollouts(split: Split) -> tuple[Rollout, ...]:
    """All rollouts of one split: four paired conditions per unit, plus the test null controls."""
    rollouts: list[Rollout] = []
    for unit in build_units(split):
        label = f"f{unit.family}" if unit.family is not None else unit.slice.value
        for condition in CONDITIONS:
            rollouts.append(
                Rollout(
                    rollout_id=f"{unit.split.value}/{label}/s{unit.seed}/{condition.value}",
                    split=unit.split,
                    family=unit.family,
                    seed=unit.seed,
                    information_condition=condition,
                    independent_unit_id=unit.independent_unit_id,
                    slice=unit.slice,
                    template_id=(
                        unit.template_id if condition is not InformationCondition.NO_ALERT else None
                    ),
                    promised_lead_time=unit.promised_lead_time,
                    params=unit.params,
                )
            )
    if split is Split.TEST:
        for i in range(N_SILENT_NULL + N_FALSE_ALERT_NULL):
            silent = i < N_SILENT_NULL
            seed = NULL_CONTROL_BASE + i
            rollouts.append(
                Rollout(
                    rollout_id=f"test/null/s{seed}/{'silent' if silent else 'false_alert'}",
                    split=Split.TEST,
                    family=None,
                    seed=seed,
                    information_condition=(
                        InformationCondition.NO_ALERT if silent else InformationCondition.UNRELIABLE
                    ),
                    independent_unit_id=f"unit-null-s{seed}",
                    slice=(RolloutSlice.SILENT_NULL if silent else RolloutSlice.FALSE_ALERT_NULL),
                    template_id=None if silent else f"tpl_test_null_{i:02d}",
                    promised_lead_time=DEFAULT_BASELINE_LEAD_TIME,
                    params=None,
                )
            )
    return tuple(rollouts)


# ---------------------------------------------------------------------------
# the five integrity assertions
# ---------------------------------------------------------------------------


def assert_seed_pools_disjoint(pools: dict[str, frozenset[int]] | None = None) -> None:
    pools = pools if pools is not None else seed_pools()
    names = sorted(pools)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            overlap = pools[left] & pools[right]
            assert not overlap, f"seed pools {left} and {right} overlap on {sorted(overlap)[:5]}"


def assert_no_test_templates(rollouts_by_split: dict[Split, tuple[Rollout, ...]]) -> None:
    test_templates = {
        r.template_id for r in rollouts_by_split[Split.TEST] if r.template_id is not None
    }
    for split in (Split.DEV, Split.CAL):
        leaked = {
            r.template_id for r in rollouts_by_split[split] if r.template_id is not None
        } & test_templates
        assert not leaked, f"test template ids present in {split}: {sorted(leaked)}"


def assert_held_out_combos_absent(rollouts_by_split: dict[Split, tuple[Rollout, ...]]) -> None:
    for split in (Split.DEV, Split.CAL):
        bad = [
            r.rollout_id
            for r in rollouts_by_split[split]
            if r.slice
            in (RolloutSlice.HELD_OUT_COMBO, RolloutSlice.EXTRAPOLATION, RolloutSlice.OOD)
        ]
        assert not bad, f"held-out or slice rollouts present in {split}: {bad}"


def assert_units_resolve(rollouts: tuple[Rollout, ...]) -> None:
    by_unit: dict[str, set[int]] = {}
    for r in rollouts:
        by_unit.setdefault(r.independent_unit_id, set()).add(r.seed)
    bad = {u: s for u, s in by_unit.items() if len(s) != 1}
    assert not bad, f"independent units resolving to != 1 seed: {bad}"


def required_confirmatory_seeds(
    calibrated_effects: Sequence[float], *, alpha: float = 0.05, power: float = 0.8
) -> int:
    """The preregistered power rule (R4.7): paired one-sample sizing on per-unit effect sizes.

    It consumes **calibration effect sizes only**. That is enforced two ways, because a rule
    the caller could feed test results to is not a rule: the signature accepts a bare sequence
    of floats (no rollouts, no records, no split to smuggle test data through), and
    ``tests/test_splits.py`` inspects the source statically — the body references no global
    that could carry test data and calls nothing but ``math``/``statistics``.
    """
    if len(calibrated_effects) < 2:
        raise ValueError("the power rule needs at least two calibration units")
    mean = statistics.fmean(calibrated_effects)
    sd = statistics.stdev(calibrated_effects)
    if mean <= 0:
        raise ValueError(f"calibration shows no positive effect to size against (mean {mean})")
    if sd == 0.0:
        return 1
    z_a = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z_p = statistics.NormalDist().inv_cdf(power)
    return math.ceil(((z_a + z_p) * sd / mean) ** 2)


# ---------------------------------------------------------------------------
# the OOD composition
# ---------------------------------------------------------------------------

OOD_SPEC = {"magnitude": 2.0, "duration": 3, "loss_length": 2}
"""The one held-out composition: a family-3 pulse crossed with a family-5 loss burst. Every
value is from the registered ranges; only the composition is unseen by any split."""


def generate_ood_episode(*, seed: int, horizon: int, onset: int | None = None) -> GeneratedEpisode:
    """Build the OOD episode from base primitives: pulse scaling plus an inf lead-time burst.

    The incident parses as ``compound`` with a ``shipment_loss`` effect — one latent disruption
    drives both streams, so ``conditional_independence`` is False. It is deliberately not a
    family-6 episode (no pause), which is what makes the composition out-of-distribution.
    """
    rngs = episode_rngs(seed)
    onset = onset if onset is not None else draw_onset(rngs.onset)
    duration = int(OOD_SPEC["duration"])
    loss_length = int(OOD_SPEC["loss_length"])
    magnitude = float(OOD_SPEC["magnitude"])
    if onset > horizon or onset - 1 + max(duration, loss_length) > horizon:
        raise ValueError(f"OOD episode at onset {onset} does not fit the horizon {horizon}")

    spec = FamilyParams(3).baseline  # the registered stationary-IID default
    baseline = draw_baseline(rngs.baseline, spec, horizon)
    last = onset - 1 + duration
    demand = (
        *baseline[: onset - 1],
        *as_demand_cells(np.asarray(baseline[onset - 1 : last]) * magnitude),
        *baseline[last:],
    )
    lead_times = tuple(
        math.inf if onset - 1 <= t < onset - 1 + loss_length else float(DEFAULT_BASELINE_LEAD_TIME)
        for t in range(horizon)
    )
    incident = HiddenIncident(
        family=ShockFamily.COMPOUND,
        onset_period=onset,
        magnitude=magnitude,
        duration=duration,
        conditional_independence=False,
        supply_effect=SupplyEffect(SupplyEffectKind.SHIPMENT_LOSS, onset, loss_length),
        seed=seed,
    )
    return GeneratedEpisode(
        demand=demand,
        lead_times=lead_times,
        pause_active=(),
        incident=incident,
        twin_demand=baseline,
        twin_lead_times=(float(DEFAULT_BASELINE_LEAD_TIME),) * horizon,
        train_demand=draw_baseline(rngs.train, spec, TRAIN_PERIODS),
    )
