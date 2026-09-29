"""Fresh-seed episode layouts for the confirmation runs. Exploratory; dev/cal generator only.

The registered pilot spent dev indices 0-1 and cal indices 0-1 of every family, and the other
dev/cal units have been scored or inspected elsewhere (``make table-main``, the module-06
diagnostic, trigger calibration). The confirmation therefore draws from a new reserved pool
that no run has touched:

    seed = family * 1_000_000 + FRESH_BASE + i,    i = 0 .. n_per_family - 1.

``FRESH_BASE`` sits between the dev/cal pools (50_000 / 60_000) and the extrapolation and OOD
pools, and :func:`assert_fresh_pool` checks disjointness against every registered pool. Units
alternate the dev and cal labels (``i`` even: dev) so both template files are exercised; the
label only selects templates. Parameters follow the dev/cal combo discipline exactly: the
``k``-th unit of a split and family takes ``COMBO_A[family][k % len]`` (set A only; the held-out
combos and extrapolation slices never appear), and the onset is the generator's own draw.

Every builder takes a keyword ``base`` (default ``FRESH_BASE``). The confirmation seeds are
sealed until the registered run: structural tests and scripted end-to-end checks use the
throwaway pool ``THROWAWAY_BASE`` (900_000) instead, which is checked against the registered
pools in the same way.

Each unit yields the four paired information conditions plus one unshocked twin. Within a family,
units ``i % 4 in {0, 3}`` get a silent twin and the others a false-alert twin, so every block of
four units holds two of each, one per split; nulls are therefore balanced over families and
splits rather than concentrated in families 1-2 as in the registered pilot.

Alerts come from module 03's renderer (``render_condition_batch``) through an in-memory manifest
in the frozen manifest's row format, with the pilot's template-selection rule ``bank-v1`` applied
to the split-local slot index ``SLOT_BASE + k``. Only ``dev.yaml`` and ``cal.yaml`` are loaded.

Stochastic-lead stratum (exploratory). :func:`build_stochastic_lead_layout` builds family-4 units
``i = 12 .. 23`` (seeds disjoint from the main layout's ``i = 0 .. 11``) with the same unit
construction, conditions, twins and alerts, but with noisy per-order lead times. For the order
placed in period ``t`` the lead time is ``max(0, L_t + xi_t)``, where ``L_t`` is the generator's
deterministic lead (the baseline lead before onset, the disrupted lead from onset) and the
``xi_t`` are iid with the pmf ``LEAD_NOISE_PMF`` on ``LEAD_NOISE_SUPPORT``, drawn from
``numpy.random.default_rng(seed + LEAD_NOISE_SEED_OFFSET)``. The twin uses the same ``xi_t``
around the baseline lead (``max(0, L_base + xi_t)``, no shift), so episode and twin agree on
every pre-onset lead time. Lost shipments (``inf``) are left as they are. The noise is applied to
the ``GeneratedEpisode`` before :func:`collie.data.writer.write_pair`; the generator and the
incident record are unchanged.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from analysis.real_content_pilot.alerts import (
    ALERT_ID,
    GAP_GENERATOR_FAMILY,
    NULL_FALSE_ALERT_PERIOD,
    EpisodeAlerts,
    _checked,
    load_dev_cal_bank,
    null_false_alert_template,
    select_templates,
)
from collie.contracts import (
    AlertMessage,
    InformationCondition,
    ShockFamily,
    Split,
)
from collie.data.alerts.audit import default_audit_config
from collie.data.alerts.bank import render_alert
from collie.data.alerts.conditions import render_condition_batch
from collie.data.families import generate_episode
from collie.data.families.base import DEFAULT_BASELINE_LEAD_TIME, FamilyParams, GeneratedEpisode
from collie.data.splits import (
    COMBO_A,
    CONDITIONS,
    FAMILIES,
    assert_seed_pools_disjoint,
    combo_params,
    seed_pools,
)
from collie.data.writer import write_pair
from collie.eval.truth import EpisodeTruth, episode_truth_from_incident
from collie.sim.loader import LoadedInstance, load_instance
from collie.trigger.demo import DEMO_HORIZON

FRESH_BASE = 100_000
"""The confirmation pool. Sealed: no arm is run and no outcome is computed on it before the
registered run."""
THROWAWAY_BASE = 900_000
"""The pool for structural tests and scripted end-to-end checks. Supports no claim."""
FAMILY_STRIDE = 1_000_000
"""Seeds of one family occupy ``family * FAMILY_STRIDE + [0, FAMILY_STRIDE)``."""
SLOT_BASE = 100
"""Split-local template slot index offset: ``tpl_{split}_f{family}_{SLOT_BASE + k}``."""
FAMILY_NAMES = {
    1: "demand_level",
    2: "demand_level",
    3: "temporary_pulse",
    4: "lead_time_shift",
    5: "shipment_loss",
    6: "compound",
}

STOCHASTIC_FAMILY = 4
STOCHASTIC_FIRST_INDEX = 12
STOCHASTIC_N_UNITS = 12
LEAD_NOISE_SEED_OFFSET = 7_000_000
"""The noise generator for a unit with seed ``s`` is ``default_rng(s + LEAD_NOISE_SEED_OFFSET)``."""
LEAD_NOISE_SUPPORT = (-2, -1, 0, 1, 2)
LEAD_NOISE_PMF = (2 / 99, 27 / 99, 48 / 99, 18 / 99, 4 / 99)
"""P(xi = -2, -1, 0, 1, 2) = (2, 27, 48, 18, 4) / 99: the finite delays of
``collie.verify.arrival.REGISTERED_NULL_LAW``, (0.02, 0.27, 0.48, 0.18, 0.04) on delays 0..4,
renormalised over the finite delays (sum 0.99; the 0.01 loss mass is dropped) and centred on
their mode, delay 2. The mean of xi is -5/99."""
STOCHASTIC_LEAD_STRATUM = "stochastic_lead"


@dataclass(frozen=True)
class FreshUnit:
    family: int
    index: int
    seed: int
    split: Split
    k: int
    params: FamilyParams
    promised_lead_time: int

    @property
    def unit_id(self) -> str:
        return f"unit-f{self.family}-s{self.seed}"

    @property
    def slot(self) -> str:
        return f"tpl_{self.split.value}_f{self.family}_{SLOT_BASE + self.k:03d}"

    def rollout_id(self, condition: InformationCondition) -> str:
        return f"{self.split.value}/f{self.family}/s{self.seed}/{condition.value}"

    @property
    def null_condition(self) -> InformationCondition:
        silent = self.index % 4 in (0, 3)
        return InformationCondition.NO_ALERT if silent else InformationCondition.UNRELIABLE

    @property
    def null_episode_id(self) -> str:
        # The twin of the unit's no-alert rollout; its own condition is ``null_condition``.
        return f"{self.rollout_id(InformationCondition.NO_ALERT)}__twin"


def fresh_seed(family: int, index: int, *, base: int = FRESH_BASE) -> int:
    if base < 0 or index < 0 or base + index >= FAMILY_STRIDE:
        raise ValueError(
            f"base {base} + index {index} must lie in [0, {FAMILY_STRIDE}) so that seeds stay "
            "inside their family's range"
        )
    return family * FAMILY_STRIDE + base + index


def fresh_unit(family: int, index: int, *, base: int = FRESH_BASE) -> FreshUnit:
    """The ``index``-th unit of ``family``: dev for even ``index``, cal for odd, combo set A."""
    split = Split.DEV if index % 2 == 0 else Split.CAL
    k = index // 2
    combo = COMBO_A[family][k % len(COMBO_A[family])]
    params = FamilyParams(family, **combo_params(family, combo))
    promised = (
        params.baseline_lead_time
        if params.baseline_lead_time is not None
        else DEFAULT_BASELINE_LEAD_TIME
    )
    seed = fresh_seed(family, index, base=base)
    return FreshUnit(family, index, seed, split, k, params, int(promised))


def fresh_units(n_per_family: int, *, base: int = FRESH_BASE) -> tuple[FreshUnit, ...]:
    if n_per_family < 1 or n_per_family > 1_000:
        raise ValueError("n_per_family must be in 1..1000")
    units = [fresh_unit(family, i, base=base) for family in FAMILIES for i in range(n_per_family)]
    assert_fresh_pool(units)
    return tuple(units)


def assert_fresh_pool(
    units: Sequence[FreshUnit],
    *,
    name: str = "fresh_commitment",
    others: Mapping[str, frozenset[int]] | None = None,
) -> None:
    """Raise unless ``units`` have distinct seeds disjoint from every registered pool and from
    every pool in ``others``."""
    pool = frozenset(u.seed for u in units)
    if len(pool) != len(units):
        raise ValueError("duplicate fresh seeds")
    pools = {**seed_pools(), **(others or {})}
    if name in pools:
        raise ValueError(f"pool name {name!r} is already taken")
    assert_seed_pools_disjoint({**pools, name: pool})


def stochastic_lead_units(
    *,
    base: int = FRESH_BASE,
    first_index: int = STOCHASTIC_FIRST_INDEX,
    n_units: int = STOCHASTIC_N_UNITS,
) -> tuple[FreshUnit, ...]:
    """Family-4 units ``first_index .. first_index + n_units - 1`` of the pool at ``base``.

    Checked disjoint from the registered pools, from the main layout's units ``0 ..
    first_index - 1`` of every family, and (as integers) from the noise generators' seeds.
    """
    if first_index < 0:
        raise ValueError("first_index must be non-negative")
    if n_units < 1 or n_units > 1_000:
        raise ValueError("n_units must be in 1..1000")
    units = tuple(
        fresh_unit(STOCHASTIC_FAMILY, i, base=base)
        for i in range(first_index, first_index + n_units)
    )
    others = {
        "stochastic_lead_noise": frozenset(u.seed + LEAD_NOISE_SEED_OFFSET for u in units),
    }
    if first_index > 0:
        others["fresh_commitment"] = frozenset(u.seed for u in fresh_units(first_index, base=base))
    assert_fresh_pool(units, name="fresh_commitment_stochastic_lead", others=others)
    return units


def lead_noise(seed: int, horizon: int = DEMO_HORIZON) -> tuple[int, ...]:
    """The unit's ``xi_1 .. xi_horizon``, iid ``LEAD_NOISE_PMF`` on ``LEAD_NOISE_SUPPORT``."""
    rng = np.random.default_rng(seed + LEAD_NOISE_SEED_OFFSET)
    draws = rng.choice(len(LEAD_NOISE_SUPPORT), size=horizon, p=np.asarray(LEAD_NOISE_PMF))
    return tuple(LEAD_NOISE_SUPPORT[int(j)] for j in draws)


def noisy_lead_times(lead_times: Sequence[float], xi: Sequence[int]) -> tuple[float, ...]:
    """``max(0, L_t + xi_t)`` per order period; ``inf`` (a lost shipment) is kept."""
    out = []
    for value, noise in zip(lead_times, xi, strict=True):
        if math.isinf(value):
            out.append(value)
            continue
        if value != int(value):
            raise ValueError(f"non-integer lead time {value}")
        out.append(float(max(0, int(value) + int(noise))))
    return tuple(out)


def stochastic_lead_episode(ep: GeneratedEpisode, xi: Sequence[int]) -> GeneratedEpisode:
    """``ep`` with the same noise ``xi`` added to the episode's and the twin's lead times."""
    return replace(
        ep,
        lead_times=noisy_lead_times(ep.lead_times, xi),
        twin_lead_times=noisy_lead_times(ep.twin_lead_times, xi),
    )


@dataclass
class Layout:
    instances: list[tuple[LoadedInstance, int]]
    truths: tuple[EpisodeTruth, ...]
    manifest: dict
    units: tuple[FreshUnit, ...]
    profit: float
    holding: float
    stratum: str = "main"

    @property
    def episode_ids(self) -> tuple[str, ...]:
        return tuple(i.spec.episode_id for i, _ in self.instances)


def build_layout(
    root: Path,
    n_per_family: int,
    *,
    profit: float = 4.0,
    holding: float = 1.0,
    base: int = FRESH_BASE,
) -> Layout:
    """Materialise every unit's four conditions and its twin under ``root``."""
    units = fresh_units(n_per_family, base=base)
    episodes = [generate_episode(seed=u.seed, horizon=DEMO_HORIZON, params=u.params) for u in units]
    return _materialise(root, units, episodes, profit=profit, holding=holding)


def build_stochastic_lead_layout(
    root: Path,
    *,
    base: int = FRESH_BASE,
    first_index: int = STOCHASTIC_FIRST_INDEX,
    n_units: int = STOCHASTIC_N_UNITS,
    profit: float = 4.0,
    holding: float = 1.0,
) -> Layout:
    """Materialise the stochastic-lead stratum (module docstring) under ``root``."""
    units = stochastic_lead_units(base=base, first_index=first_index, n_units=n_units)
    episodes = []
    for unit in units:
        ep = generate_episode(seed=unit.seed, horizon=DEMO_HORIZON, params=unit.params)
        episodes.append(stochastic_lead_episode(ep, lead_noise(unit.seed, len(ep.demand))))
    manifest_extra = {
        "stratum": STOCHASTIC_LEAD_STRATUM,
        "lead_noise": {
            "pmf": list(LEAD_NOISE_PMF),
            "rule": "max(0, L_t + xi_t); twin max(0, L_base + xi_t); inf kept",
            "seed_offset": LEAD_NOISE_SEED_OFFSET,
            "support": list(LEAD_NOISE_SUPPORT),
        },
    }
    row_extra = {u.seed: {"lead_noise_seed": u.seed + LEAD_NOISE_SEED_OFFSET} for u in units}
    return _materialise(
        root,
        units,
        episodes,
        profit=profit,
        holding=holding,
        stratum=STOCHASTIC_LEAD_STRATUM,
        manifest_extra=manifest_extra,
        row_extra=row_extra,
    )


def _materialise(
    root: Path,
    units: Sequence[FreshUnit],
    episodes: Sequence[GeneratedEpisode],
    *,
    profit: float,
    holding: float,
    stratum: str = "main",
    manifest_extra: Mapping[str, object] | None = None,
    row_extra: Mapping[int, Mapping[str, object]] | None = None,
) -> Layout:
    instances: list[tuple[LoadedInstance, int]] = []
    truths: list[EpisodeTruth] = []
    rows: list[dict] = []
    for unit, ep in zip(units, episodes, strict=True):
        onset = int(ep.incident.onset_period)
        for condition in CONDITIONS:
            rollout_id = unit.rollout_id(condition)
            write_pair(root, ep, relpath=rollout_id, profit=profit, holding=holding)
            loaded = load_instance(
                root / rollout_id,
                episode_id=rollout_id,
                promised_lead_time=unit.promised_lead_time,
                split=unit.split,
            )
            spec = replace(
                loaded.spec, independent_unit_id=unit.unit_id, information_condition=condition
            )
            instance = replace(loaded, spec=spec)
            instances.append((instance, unit.seed))
            truths.append(episode_truth_from_incident(rollout_id, unit.unit_id, instance.incident))
            rows.append(
                {
                    "family": unit.family,
                    "independent_unit_id": unit.unit_id,
                    "information_condition": condition.value,
                    "magnitude": unit.params.magnitude,
                    "onset": onset,
                    "promised_lead_time": unit.promised_lead_time,
                    "rollout_id": rollout_id,
                    "seed": unit.seed,
                    "shock_family": FAMILY_NAMES[unit.family],
                    "split": unit.split.value,
                    "template_id": (
                        None if condition is InformationCondition.NO_ALERT else unit.slot
                    ),
                    **(row_extra or {}).get(unit.seed, {}),
                }
            )
        null_loaded = load_instance(
            root / unit.null_episode_id,
            episode_id=unit.null_episode_id,
            promised_lead_time=unit.promised_lead_time,
            split=unit.split,
        )
        null_spec = replace(
            null_loaded.spec,
            family=ShockFamily.NO_CHANGE,
            independent_unit_id=f"unit-null-f{unit.family}-s{unit.seed}",
            information_condition=unit.null_condition,
        )
        instances.append((replace(null_loaded, spec=null_spec), unit.seed))
    manifest = {"horizon": DEMO_HORIZON, "rollouts": rows, **(manifest_extra or {})}
    return Layout(instances, tuple(truths), manifest, tuple(units), profit, holding, stratum)


def layout_alerts(layout: Layout) -> dict[str, EpisodeAlerts]:
    """Module 03 bank messages for every episode of a fresh layout (rule ``bank-v1``)."""
    manifest = layout.manifest
    rows = {row["rollout_id"]: row for row in manifest["rollouts"]}
    by_unit = {u.unit_id: u for u in layout.units}
    bank = load_dev_cal_bank()
    kinds = {t.template_id: t.kind.value for t in bank}
    offset = default_audit_config()["unreliable_offset"]

    first: dict[str, LoadedInstance] = {}
    for instance, _ in layout.instances:
        if instance.incident is not None:
            first.setdefault(str(instance.spec.independent_unit_id), instance)
    requests, unit_ids = [], []
    for unit_id, instance in sorted(first.items()):
        unit = by_unit[unit_id]
        if unit.family == GAP_GENERATOR_FAMILY:
            continue
        accurate, unreliable = select_templates(
            bank, split=unit.split, family=ShockFamily(FAMILY_NAMES[unit.family]), slot=unit.slot
        )
        horizon = instance.spec.horizon
        requests.append(
            {
                "manifest": manifest,
                "independent_unit_id": unit_id,
                "demand": tuple(float(v) for v in instance.demand),
                "lead_times": tuple(float(v) for v in instance.supply.lead_times),
                "pause_active": tuple(instance.supply.pause_active) or (False,) * horizon,
                "onset": instance.incident.onset_period,
                "accurate": accurate,
                "unreliable": unreliable,
                "unreliable_offset": offset,
            }
        )
        unit_ids.append(unit_id)
    rendered = render_condition_batch(requests)
    rendered_by_unit = {
        unit_id: {rollout.condition: rollout for rollout in rollouts}
        for unit_id, rollouts in zip(unit_ids, rendered, strict=True)
    }

    out: dict[str, EpisodeAlerts] = {}
    for instance, _ in layout.instances:
        episode_id = instance.spec.episode_id
        condition = instance.spec.information_condition
        if instance.incident is not None:
            unit = by_unit[str(instance.spec.independent_unit_id)]
            if unit.family == GAP_GENERATOR_FAMILY:
                out[episode_id] = EpisodeAlerts(
                    episode_id, "none:bank_gap_demand_down", {}, {}, None
                )
                continue
            rollout = rendered_by_unit[unit.unit_id][condition]
            if rollout.exogenous.demand != tuple(float(v) for v in instance.demand):
                raise ValueError(f"{episode_id}: condition rollout is not a paired replay")
            alerts, template_ids = rollout.runner_alerts()
            kind = None if rollout.template_id is None else kinds[rollout.template_id]
            source = "none:no_alert" if not alerts else f"bank:{condition.value}"
            out[episode_id] = _checked(
                EpisodeAlerts(episode_id, source, dict(alerts), dict(template_ids), kind)
            )
            continue
        source_row = rows[episode_id.removesuffix("__twin")]
        unit = by_unit[source_row["independent_unit_id"]]
        if condition is InformationCondition.NO_ALERT:
            out[episode_id] = EpisodeAlerts(episode_id, "none:silent_null", {}, {}, None)
            continue
        template = null_false_alert_template(bank, split=unit.split, slot=unit.slot)
        message = AlertMessage(
            ALERT_ID, NULL_FALSE_ALERT_PERIOD, render_alert(template, unit.seed).text
        )
        out[episode_id] = _checked(
            EpisodeAlerts(
                episode_id,
                "bank:false_alert_null",
                {NULL_FALSE_ALERT_PERIOD: message},
                {NULL_FALSE_ALERT_PERIOD: template.template_id},
                template.kind.value,
            )
        )
    return out
