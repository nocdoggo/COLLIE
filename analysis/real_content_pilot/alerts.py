"""Module 03 alert-bank messages for the registered 120-episode pilot. Exploratory.

This replaces the frozen demo stand-in (``tools/run_arms.py::_demo_alert``) with messages built
by module 03's own API: ``load_template_file``, ``render_condition_batch`` (which applies the
registered timing schedule and pairing checks) and ``render_alert``. Only ``dev.yaml`` and
``cal.yaml`` are ever loaded; ``test.yaml`` is never opened.

Module 03 registers the renderer and the schedule, but three things this pilot needs are not
registered anywhere, so they are fixed here, deterministically, before any live call (PLAN.md):

1. **Template selection, rule ``bank-v1``.** The manifest carries a template *slot* per unit
   (``tpl_{split}_f{family}_{i:02d}``), not a bank id. For slot index ``i`` and position
   ``p = 2*i + (0 for dev, 1 for cal)``: the accurate template is the ``i % 4``-th accurate
   template of that split and family (sorted by id); the unreliable template's kind cycles
   ``overstated, ambiguous, distractor`` by ``p % 3``, and it is the ``i % 2``-th template of that
   kind.
2. **Generator family 2 (demand level down) has no bank coverage.** Every dev/cal
   ``demand_level`` template is demand-up, and ``render_conditions`` refuses to pair one with a
   demand-down unit. Those 16 episodes therefore get no alert in any condition; only the demand
   CUSUM can fire on them. Recorded per episode as ``none:bank_gap_demand_down``.
3. **Null controls.** The pilot's 24 nulls are unshocked twins with no manifest rows. Silent
   nulls (``no_alert``) get nothing. False-alert nulls (``unreliable``) get one accurate-kind
   ``demand_level`` message at period 10 (the frozen demo's null alert period), claiming a demand
   rise that never happens: the ``(2 + i) % 4``-th accurate template, which no shocked unit in the
   pilot uses.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from collie.contracts import (
    AlertKind,
    AlertMessage,
    InformationCondition,
    ShockFamily,
    Split,
    assert_no_hidden_state,
)
from collie.data.alerts.audit import default_audit_config
from collie.data.alerts.bank import (
    AlertTemplate,
    assert_no_text_leakage,
    load_template_file,
    render_alert,
)
from collie.data.alerts.conditions import load_manifest, manifest_unit, render_condition_batch
from collie.sim.loader import LoadedInstance
from tools.run_arms import _demo_alert, _demo_template_ids

REPO = Path(__file__).resolve().parents[2]
BANK_DIR = REPO / "collie" / "data" / "alerts" / "templates"
BANK_FILES = ("dev.yaml", "cal.yaml")
"""Only the dev and cal template files. The test wording families are never loaded."""
MANIFEST_PATH = REPO / "manifests" / "shockspec_v1.json"

SELECTION_RULE = "bank-v1"
UNRELIABLE_KINDS = (AlertKind.OVERSTATED, AlertKind.AMBIGUOUS, AlertKind.DISTRACTOR)
NULL_FALSE_ALERT_PERIOD = 10
"""The period of the frozen demo's null alert (``tools/run_arms.py::_demo_alert``)."""
ALERT_ID = "operational-alert"
"""The id module 03's ``render_conditions`` gives every message."""
GAP_GENERATOR_FAMILY = 2
"""Generator family 2 (demand level down): no demand-down template exists in dev or cal."""


@dataclass(frozen=True)
class EpisodeAlerts:
    """The alert channel of one episode: what the runner delivers, plus its provenance."""

    episode_id: str
    source: str
    alerts: dict[int, AlertMessage]
    template_ids: dict[int, str]
    template_kind: str | None

    def to_row(self) -> dict:
        if len(self.alerts) > 1:
            raise ValueError(f"{self.episode_id}: more than one alert per episode")
        period, message = next(iter(self.alerts.items()), (None, None))
        return {
            "episode_id": self.episode_id,
            "source": self.source,
            "period": period,
            "template_id": self.template_ids.get(period) if period is not None else None,
            "template_kind": self.template_kind,
            "text": None if message is None else message.text,
        }


def load_dev_cal_bank() -> tuple[AlertTemplate, ...]:
    """The dev and cal templates only, loaded file by file so test.yaml is never read."""
    templates: list[AlertTemplate] = []
    for name in BANK_FILES:
        templates.extend(load_template_file(BANK_DIR / name))
    bad = [t.template_id for t in templates if t.split not in (Split.DEV, Split.CAL)]
    if bad:
        raise ValueError(f"non-dev/cal templates in the dev/cal files: {bad[:5]}")
    return tuple(templates)


def slot_index(slot: str) -> int:
    """``tpl_dev_f1_00`` -> 0: the unit's index within its split and generator family."""
    return int(slot.rsplit("_", 1)[1])


def templates_of(
    bank: Sequence[AlertTemplate], *, split: Split, family: ShockFamily, kind: AlertKind
) -> list[AlertTemplate]:
    return sorted(
        (t for t in bank if t.split is split and t.family is family and t.kind is kind),
        key=lambda t: t.template_id,
    )


def select_templates(
    bank: Sequence[AlertTemplate], *, split: Split, family: ShockFamily, slot: str
) -> tuple[AlertTemplate, AlertTemplate]:
    """Rule ``bank-v1``: (accurate, unreliable) for one unit. See the module docstring."""
    i = slot_index(slot)
    position = 2 * i + (0 if split is Split.DEV else 1)
    accurate = templates_of(bank, split=split, family=family, kind=AlertKind.ACCURATE)
    kind = UNRELIABLE_KINDS[position % len(UNRELIABLE_KINDS)]
    unreliable = templates_of(bank, split=split, family=family, kind=kind)
    if not accurate or not unreliable:
        raise ValueError(f"no {family.value}/{split.value} templates for rule {SELECTION_RULE}")
    return accurate[i % len(accurate)], unreliable[i % len(unreliable)]


def null_false_alert_template(
    bank: Sequence[AlertTemplate], *, split: Split, slot: str
) -> AlertTemplate:
    """The false-alert null's message: an accurate-kind demand-up claim no shocked unit uses."""
    accurate = templates_of(
        bank, split=split, family=ShockFamily.DEMAND_LEVEL, kind=AlertKind.ACCURATE
    )
    return accurate[(2 + slot_index(slot)) % len(accurate)]


def _checked(episode: EpisodeAlerts) -> EpisodeAlerts:
    for message in episode.alerts.values():
        assert_no_hidden_state(message, context=f"alert for {episode.episode_id}")
        assert_no_text_leakage(message.text)
    return episode


def pilot_bank_alerts(instances: Sequence[LoadedInstance]) -> dict[str, EpisodeAlerts]:
    """Bank messages for every pilot episode in ``instances``, keyed by episode id."""
    manifest = load_manifest(MANIFEST_PATH)
    rows = {row["rollout_id"]: row for row in manifest["rollouts"]}
    bank = load_dev_cal_bank()
    kinds = {t.template_id: t.kind.value for t in bank}
    offset = default_audit_config()["unreliable_offset"]

    # One render per shocked unit; its condition rollouts are paired replays of one trajectory.
    units: dict[str, tuple[dict, LoadedInstance]] = {}
    for instance in instances:
        if instance.incident is None:
            continue
        row = rows[instance.spec.episode_id]
        if int(row["family"]) == GAP_GENERATOR_FAMILY:
            continue
        units.setdefault(row["independent_unit_id"], (row, instance))
    requests, unit_ids = [], []
    for unit_id, (row, instance) in sorted(units.items()):
        split = Split(row["split"])
        slot = manifest_unit(manifest, unit_id)["template_id"]
        accurate, unreliable = select_templates(
            bank, split=split, family=ShockFamily(row["shock_family"]), slot=slot
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
    by_unit = {
        unit_id: {rollout.condition: rollout for rollout in rollouts}
        for unit_id, rollouts in zip(unit_ids, rendered, strict=True)
    }

    out: dict[str, EpisodeAlerts] = {}
    for instance in instances:
        episode_id = instance.spec.episode_id
        condition = instance.spec.information_condition
        if instance.incident is not None:
            row = rows[episode_id]
            if int(row["family"]) == GAP_GENERATOR_FAMILY:
                out[episode_id] = EpisodeAlerts(
                    episode_id, "none:bank_gap_demand_down", {}, {}, None
                )
                continue
            rollout = by_unit[row["independent_unit_id"]][condition]
            if rollout.exogenous.demand != tuple(float(v) for v in instance.demand):
                raise ValueError(f"{episode_id}: condition rollout is not a paired replay")
            alerts, template_ids = rollout.runner_alerts()
            kind = None if rollout.template_id is None else kinds[rollout.template_id]
            source = "none:no_alert" if not alerts else f"bank:{condition.value}"
            out[episode_id] = _checked(
                EpisodeAlerts(episode_id, source, dict(alerts), dict(template_ids), kind)
            )
            continue
        # A null twin: episode id "<rollout_id>__twin"; its source rollout carries the unit.
        row = rows[episode_id.removesuffix("__twin")]
        if condition is InformationCondition.NO_ALERT:
            out[episode_id] = EpisodeAlerts(episode_id, "none:silent_null", {}, {}, None)
            continue
        if condition is not InformationCondition.UNRELIABLE:
            raise ValueError(f"{episode_id}: unexpected null condition {condition}")
        split = Split(row["split"])
        slot = manifest_unit(manifest, row["independent_unit_id"])["template_id"]
        template = null_false_alert_template(bank, split=split, slot=slot)
        message = AlertMessage(
            ALERT_ID, NULL_FALSE_ALERT_PERIOD, render_alert(template, int(row["seed"])).text
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


def pilot_demo_alerts(instances: Sequence[LoadedInstance]) -> dict[str, EpisodeAlerts]:
    """The frozen demo stand-in, exactly as ``run_ladder`` builds it (for equivalence checks)."""
    out: dict[str, EpisodeAlerts] = {}
    for instance in instances:
        alerts = _demo_alert(instance)
        out[instance.spec.episode_id] = EpisodeAlerts(
            instance.spec.episode_id,
            "demo",
            alerts,
            _demo_template_ids(instance, alerts),
            None,
        )
    return out
