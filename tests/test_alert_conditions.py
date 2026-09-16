"""Paired replay tests exercise nonconstant paths and nonempty template slots."""

from dataclasses import replace
from pathlib import Path

import pytest

from collie.contracts import AlertKind, InformationCondition, ShockFamily, assert_no_hidden_state
from collie.data.alerts.bank import load_alert_bank
from collie.data.alerts.conditions import (
    ExogenousDraws,
    load_manifest,
    manifest_unit,
    render_conditions,
)
from collie.fakes import fixture_episode

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    # Take identity and timing from the real manifest and generate the trajectory with fakes; add a nonempty slot so slot-consistency assertions cannot pass vacuously.
    manifest = load_manifest(ROOT / "manifests/shockspec_v1.json")
    row = next(r for r in manifest["rollouts"] if r["split"] == "dev" and r["family"] == 1)
    episode = fixture_episode(
        ShockFamily(row["shock_family"]),
        seed=row["seed"],
        onset=row["onset"],
        horizon=manifest["horizon"],
    )
    bank = load_alert_bank(ROOT / "collie/data/alerts/templates")
    templates = [
        t for t in bank if t.split.value == "dev" and t.family.value == row["shock_family"]
    ]
    accurate = next(t for t in templates if t.kind is AlertKind.ACCURATE)
    accurate = replace(
        accurate,
        text="{desk}: " + accurate.text,
        slots={"desk": ("Sales desk", "Account team"), **accurate.slots},
    )
    return dict(
        manifest=manifest,
        independent_unit_id=row["independent_unit_id"],
        demand=episode.demand,
        lead_times=episode.supply.lead_times,
        pause_active=episode.supply.pause_active,
        onset=episode.incident.onset_period,
        accurate=accurate,
        unreliable=next(t for t in templates if t.kind is AlertKind.OVERSTATED),
    )


def test_four_conditions_share_exogenous_draws(inputs):
    # Check the shared object, byte fingerprint and message times together, proving the trajectory is fixed while the information condition really changes.
    result = render_conditions(**inputs)
    assert len(result) == 4
    assert len({r.exogenous.fingerprint_bytes() for r in result}) == 1
    assert all(r.exogenous is result[0].exogenous for r in result)
    assert result[0].exogenous.slot_draws
    assert result[0].message is None
    assert result[1].message.period == inputs["onset"] - 1
    assert result[2].message.period == inputs["onset"] + 2
    assert result[1].message.text == result[2].message.text
    assert result[3].message.text != result[1].message.text


def test_independent_unit_id_on_every_rollout(inputs):
    for rollout in render_conditions(**inputs):
        row = manifest_unit(inputs["manifest"], rollout.independent_unit_id)
        assert rollout.seed == row["seed"]
        assert rollout.manifest_template_slot == (row["template_id"] if rollout.message else None)


def test_runner_boundary_has_no_hidden_truth(inputs):
    # Inspect the message maps handed to the runner, ensuring hidden labels never enter policy-visible objects.
    for rollout in render_conditions(**inputs):
        alerts, ids = rollout.runner_alerts()
        assert_no_hidden_state(alerts)
        assert all(not hasattr(alert, "template_id") for alert in alerts.values())
        if alerts:
            assert list(ids.values()) == [rollout.template_id]


def test_conflicting_seed_in_manifest_raises(inputs):
    # Deliberately give one unit two seeds to confirm the system rejects the false pairing.
    import copy

    manifest = copy.deepcopy(inputs["manifest"])
    rows = [
        r for r in manifest["rollouts"] if r["independent_unit_id"] == inputs["independent_unit_id"]
    ]
    rows[1]["seed"] += 1
    with pytest.raises(ValueError, match="one seed"):
        render_conditions(**(inputs | {"manifest": manifest}))


@pytest.mark.parametrize("kind", [AlertKind.OVERSTATED, AlertKind.AMBIGUOUS, AlertKind.DISTRACTOR])
def test_all_unreliable_kinds(inputs, kind):
    bank = load_alert_bank(ROOT / "collie/data/alerts/templates")
    template = next(
        t
        for t in bank
        if t.kind is kind
        and t.split == inputs["accurate"].split
        and t.family == inputs["accurate"].family
    )
    result = render_conditions(**(inputs | {"unreliable": template}))
    assert result[-1].condition is InformationCondition.UNRELIABLE
    assert result[-1].alert_spec.kind is kind


def test_bad_template_split_raises(inputs):
    from collie.contracts import Split

    with pytest.raises(ValueError, match="split/family"):
        render_conditions(**(inputs | {"accurate": replace(inputs["accurate"], split=Split.TEST)}))


def test_out_of_horizon_not_silently_clipped(inputs):
    with pytest.raises(ValueError, match="timestamp"):
        render_conditions(**inputs, unreliable_offset=1000)


def test_signed_zero_changes_bitwise_fingerprint(inputs):
    # Positive and negative zero compare equal numerically but differ in bytes; use them to verify this is a bitwise consistency check.
    result = render_conditions(**inputs)[0].exogenous
    a = replace(result, demand=(0.0, *result.demand[1:]))
    b = replace(result, demand=(-0.0, *result.demand[1:]))
    assert a.demand == b.demand
    assert a.fingerprint_bytes() != b.fingerprint_bytes()


def test_supply_losses_and_pauses_are_identical(inputs):
    # Insert loss and pause events explicitly, so coverage of these states is not claimed from the normal supply path alone.
    import math

    n = len(inputs["demand"])
    modified = inputs | {
        "lead_times": (math.inf, 3.0, *inputs["lead_times"][2:]),
        "pause_active": (True, *((False,) * (n - 1))),
    }
    result = render_conditions(**modified)
    assert result[0].exogenous.losses[0]
    assert result[0].exogenous.pause_active[0]
    assert len({r.exogenous.fingerprint_bytes() for r in result}) == 1


def test_batch_rejects_text_reuse_across_independent_units(inputs):
    # Build two units with different identities but the same text, checking that batch allocation does not let repeated stimuli through.
    import copy

    from collie.data.alerts.conditions import render_condition_batch

    # Same text, different unit: finite scheduling guard must reject it.
    request = copy.deepcopy(inputs)
    uid = inputs["independent_unit_id"]
    for row in request["manifest"]["rollouts"]:
        if row["independent_unit_id"] == uid:
            row["independent_unit_id"] = "second-unit"
            row["seed"] += 100
    request["independent_unit_id"] = "second-unit"
    # Use no-slot accurate template so the different seed cannot change wording.
    for kwargs in (inputs, request):
        kwargs["accurate"] = replace(
            kwargs["accurate"], text="Sales expects heavier routine orders.", slots={}
        )
    with pytest.raises(ValueError, match="repeated rollout"):
        render_condition_batch([inputs, request])


def test_demand_down_cannot_use_an_up_template(inputs):
    import copy

    manifest = copy.deepcopy(inputs["manifest"])
    for row in manifest["rollouts"]:
        if row["independent_unit_id"] == inputs["independent_unit_id"]:
            row["magnitude"] = 0.75
    with pytest.raises(ValueError, match="direction"):
        render_conditions(**(inputs | {"manifest": manifest}))


def _valid_draw_kwargs(**overrides):
    base = dict(
        demand=(10.0, 12.0),
        lead_times=(2.0, 2.0),
        pause_active=(False, False),
        onset=1,
        slot_draws=(("tpl_001:port", "Rotterdam"),),
    )
    return base | overrides


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("demand", [10.0, 12.0], "immutable tuples"),
        ("lead_times", [2.0, 2.0], "immutable tuples"),
        ("demand", (), "demand and lead times must align"),
        ("lead_times", (2.0,), "demand and lead times must align"),
        ("pause_active", [False, False], "pause path must align"),
        ("pause_active", (False,), "pause path must align"),
        ("slot_draws", [("tpl_001:port", "Rotterdam")], "immutable string pairs"),
        ("slot_draws", (["tpl_001:port", "Rotterdam"],), "immutable string pairs"),
        ("slot_draws", (("tpl_001:port",),), "immutable string pairs"),
        ("slot_draws", (("tpl_001:port", 7),), "immutable string pairs"),
        ("onset", 0, "onset outside trajectory"),
        ("onset", 3, "onset outside trajectory"),
        ("onset", True, "onset outside trajectory"),
        ("demand", (float("nan"), 12.0), "finite and nonnegative"),
        ("demand", (-1.0, 12.0), "finite and nonnegative"),
        ("lead_times", (float("nan"), 2.0), "invalid lead time"),
        ("lead_times", (-1.0, 2.0), "invalid lead time"),
        ("pause_active", (0, False), "pause values must be booleans"),
    ],
)
def test_exogenous_draws_reject_malformed_trajectories(field, value, message):
    with pytest.raises(ValueError, match=message):
        ExogenousDraws(**_valid_draw_kwargs(**{field: value}))


def _four_row_manifest(template_id="tpl_001"):
    rows = []
    for condition in ("no_alert", "early_accurate", "late_accurate", "unreliable"):
        rows.append(
            {
                "independent_unit_id": "u1",
                "seed": 7,
                "split": "dev",
                "shock_family": "transit_pause",
                "onset": 5,
                "information_condition": condition,
                "template_id": template_id,
            }
        )
    return {"rollouts": rows}


def test_manifest_unit_rejects_unknown_and_malformed_units():
    with pytest.raises(ValueError, match="unknown independent unit"):
        manifest_unit({"rollouts": []}, "ghost")
    with pytest.raises(ValueError, match="exactly four"):
        manifest_unit({"rollouts": _four_row_manifest()["rollouts"][:3]}, "u1")
    with pytest.raises(ValueError, match="one manifest template slot"):
        manifest_unit(_four_row_manifest(template_id=""), "u1")
    divergent = _four_row_manifest()
    divergent["rollouts"][1]["template_id"] = "tpl_other"
    with pytest.raises(ValueError, match="one manifest template slot"):
        manifest_unit(divergent, "u1")


def test_trajectory_must_agree_with_manifest_onset_and_horizon(inputs):
    with pytest.raises(ValueError, match="onset/horizon"):
        render_conditions(**(inputs | {"onset": inputs["onset"] + 1}))
    with pytest.raises(ValueError, match="onset/horizon"):
        render_conditions(**(inputs | {"demand": inputs["demand"][:-1]}))


def test_accurate_condition_requires_accurate_kind(inputs):
    with pytest.raises(ValueError, match="requires an accurate template"):
        render_conditions(
            **(inputs | {"accurate": replace(inputs["accurate"], kind=AlertKind.OVERSTATED)})
        )


def test_unreliable_condition_rejects_accurate_kind(inputs):
    with pytest.raises(ValueError, match="overstated/ambiguous/distractor"):
        render_conditions(**(inputs | {"unreliable": inputs["accurate"]}))


def test_unreliable_offset_must_be_an_integer(inputs):
    with pytest.raises(ValueError, match="offset must be an integer"):
        render_conditions(**inputs, unreliable_offset="1")
    with pytest.raises(ValueError, match="offset must be an integer"):
        render_conditions(**inputs, unreliable_offset=True)


def test_batch_returns_rollouts_for_a_consistent_allocation(inputs):
    from collie.data.alerts.conditions import render_condition_batch

    result = render_condition_batch([inputs])
    assert len(result) == 1
    assert len(result[0]) == 4
    assert result[0][0].condition is InformationCondition.NO_ALERT
