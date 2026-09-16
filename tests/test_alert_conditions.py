"""Paired replay tests exercise nonconstant paths and nonempty template slots."""

from dataclasses import replace
from pathlib import Path

import pytest

from collie.contracts import AlertKind, InformationCondition, ShockFamily, assert_no_hidden_state
from collie.data.alerts.bank import load_alert_bank
from collie.data.alerts.conditions import load_manifest, manifest_unit, render_conditions
from collie.fakes import fixture_episode

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def inputs():
    # 从真实 manifest 取身份与时间信息, 用 fake 产生轨迹; 加入非空槽位, 避免槽位一致性断言空泛通过。
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
        accurate, text="{desk}: " + accurate.text, slots={"desk": ("Sales desk", "Account team")}
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
    # 同时检查共享对象、字节指纹和消息时间, 证明轨迹固定而信息条件确实发生变化。
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
    # 检查输出给 runner 的消息映射, 确保隐藏标签不会进入策略可见对象。
    for rollout in render_conditions(**inputs):
        alerts, ids = rollout.runner_alerts()
        assert_no_hidden_state(alerts)
        assert all(not hasattr(alert, "template_id") for alert in alerts.values())
        if alerts:
            assert list(ids.values()) == [rollout.template_id]


def test_conflicting_seed_in_manifest_raises(inputs):
    # 故意让同一 unit 对应两个 seed, 确认系统拒绝伪配对。
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
    # 正负零数值相等但字节不同, 用它验证这里执行的是位级一致性检查。
    result = render_conditions(**inputs)[0].exogenous
    a = replace(result, demand=(0.0, *result.demand[1:]))
    b = replace(result, demand=(-0.0, *result.demand[1:]))
    assert a.demand == b.demand
    assert a.fingerprint_bytes() != b.fingerprint_bytes()


def test_supply_losses_and_pauses_are_identical(inputs):
    # 显式放入丢货和暂停事件, 避免只用正常供给路径就声称覆盖了这些状态。
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
    # 构造不同身份但相同文本的两个 unit, 检查批量分配不会放过重复刺激。
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
