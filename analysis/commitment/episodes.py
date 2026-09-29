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

Each unit yields the four paired information conditions plus one unshocked twin. Twins alternate
silent (``k`` even) and false-alert (``k`` odd) within a family and split, so nulls are balanced
over families rather than concentrated in families 1-2 as in the registered pilot.

Alerts come from module 03's renderer (``render_condition_batch``) through an in-memory manifest
in the frozen manifest's row format, with the pilot's template-selection rule ``bank-v1`` applied
to the split-local slot index ``SLOT_BASE + k``. Only ``dev.yaml`` and ``cal.yaml`` are loaded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

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
from collie.data.families.base import DEFAULT_BASELINE_LEAD_TIME, FamilyParams
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
        return InformationCondition.NO_ALERT if self.k % 2 == 0 else InformationCondition.UNRELIABLE

    @property
    def null_episode_id(self) -> str:
        # The twin of the unit's no-alert rollout; its own condition is ``null_condition``.
        return f"{self.rollout_id(InformationCondition.NO_ALERT)}__twin"


def fresh_seed(family: int, index: int) -> int:
    return family * 1_000_000 + FRESH_BASE + index


def fresh_units(n_per_family: int) -> tuple[FreshUnit, ...]:
    if n_per_family < 1 or n_per_family > 1_000:
        raise ValueError("n_per_family must be in 1..1000")
    units = []
    for family in FAMILIES:
        for i in range(n_per_family):
            split = Split.DEV if i % 2 == 0 else Split.CAL
            k = i // 2
            combo = COMBO_A[family][k % len(COMBO_A[family])]
            params = FamilyParams(family, **combo_params(family, combo))
            promised = (
                params.baseline_lead_time
                if params.baseline_lead_time is not None
                else DEFAULT_BASELINE_LEAD_TIME
            )
            units.append(
                FreshUnit(family, i, fresh_seed(family, i), split, k, params, int(promised))
            )
    assert_fresh_pool(units)
    return tuple(units)


def assert_fresh_pool(units: Sequence[FreshUnit]) -> None:
    pool = frozenset(u.seed for u in units)
    if len(pool) != len(units):
        raise ValueError("duplicate fresh seeds")
    assert_seed_pools_disjoint({**seed_pools(), "fresh_commitment": pool})


@dataclass
class Layout:
    instances: list[tuple[LoadedInstance, int]]
    truths: tuple[EpisodeTruth, ...]
    manifest: dict
    units: tuple[FreshUnit, ...]
    profit: float
    holding: float

    @property
    def episode_ids(self) -> tuple[str, ...]:
        return tuple(i.spec.episode_id for i, _ in self.instances)


def build_layout(
    root: Path, n_per_family: int, *, profit: float = 4.0, holding: float = 1.0
) -> Layout:
    """Materialise every unit's four conditions and its twin under ``root``."""
    units = fresh_units(n_per_family)
    instances: list[tuple[LoadedInstance, int]] = []
    truths: list[EpisodeTruth] = []
    rows: list[dict] = []
    for unit in units:
        ep = generate_episode(seed=unit.seed, horizon=DEMO_HORIZON, params=unit.params)
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
    manifest = {"horizon": DEMO_HORIZON, "rollouts": rows}
    return Layout(instances, tuple(truths), manifest, units, profit, holding)


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
