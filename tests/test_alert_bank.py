"""CP1 production-bank acceptance and hostile-input regression tests."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from collie.data.alerts.bank import (
    assert_no_text_leakage,
    load_template_file,
    render_alert,
    scan_text_for_leakage,
    validate_bank_composition,
    validate_no_repeated_renderings,
    validate_template_leakage,
    validate_wording_holdout,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE_YAML = '- id: tpl_001\n  family: transit_pause\n  split: dev\n  kind: overstated\n  wording_family: wf_customs_hold\n\n  text: "Freight forwarder reports {port} congestion; {product} containers held {vague_duration}."\n\n  slots:\n    port:\n      - Rotterdam\n      - Felixstowe\n      - Ningbo\n    product:\n      - component\n      - finished-goods\n      - packaging\n    vague_duration:\n      - for now\n      - until further notice\n      - indefinitely\n\n  alert_spec:\n    family: transit_pause\n    target_stream: arrival\n    direction: arrival_interrupted\n    onset_window: [-1, 1]\n    magnitude_bin: medium\n    persistence: transient\n    duration_bin: "4_8"\n    prospective_signature: sig_arrival_stall\n    kind: overstated'
LEAKY_YAML = '- id: leaky_001\n  family: transit_pause\n  split: dev\n  kind: overstated\n  wording_family: wf_intentionally_leaky\n  text: "Transit capacity will be half the usual amount starting period 17 for exactly 4 weeks."\n  slots: {}\n  alert_spec:\n    family: transit_pause\n    target_stream: arrival\n    direction: arrival_interrupted\n    onset_window: [-1, 1]\n    magnitude_bin: medium\n    persistence: transient\n    duration_bin: "4_8"\n    prospective_signature: sig_arrival_stall\n    kind: overstated'


def _prototype():
    # 测试样例内嵌在本文件, 并写入临时目录验证加载器; 提交时无需额外 fixture 文件。
    with TemporaryDirectory() as directory:
        path = Path(directory) / "prototype.yaml"
        path.write_text(PROTOTYPE_YAML)
        return load_template_file(path)[0]


def test_valid_prototype_loads(tmp_path) -> None:
    path = tmp_path / "prototype.yaml"
    path.write_text(PROTOTYPE_YAML)
    templates = load_template_file(path)
    assert len(templates) >= 1
    assert templates[0].template_id == "tpl_001"


def test_loader_rejects_unknown_enum(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
- id: bad_001
  family: transit_pause
  split: dev
  kind: impossible_kind
  wording_family: wf_bad
  text: "Supplier sent an update."
  slots: {}
  alert_spec:
    family: transit_pause
    target_stream: arrival
    direction: arrival_interrupted
    onset_window: [-1, 1]
    magnitude_bin: medium
    persistence: transient
    duration_bin: "4_8"
    prospective_signature: sig_arrival_stall
    kind: overstated
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_template_file(path)


def test_loader_rejects_missing_slot(tmp_path: Path) -> None:
    path = tmp_path / "missing_slot.yaml"
    path.write_text(
        """
- id: bad_002
  family: transit_pause
  split: dev
  kind: accurate
  wording_family: wf_missing_slot
  text: "Shipment at {port} may be delayed."
  slots: {}
  alert_spec:
    family: transit_pause
    target_stream: arrival
    direction: arrival_interrupted
    onset_window: [-1, 1]
    magnitude_bin: medium
    persistence: transient
    duration_bin: "4_8"
    prospective_signature: sig_arrival_stall
    kind: accurate
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="placeholders have no slot values"):
        load_template_file(path)


def test_render_is_deterministic() -> None:
    template = _prototype()
    first = render_alert(template, seed=42)
    second = render_alert(template, seed=42)
    assert first == second
    assert first.alert_spec == template.alert_spec


def test_render_substitutes_slots() -> None:
    template = replace(
        _prototype(),
        text="Shipment at {port} contains {product}.",
        slots={"port": ("Rotterdam",), "product": ("components",)},
    )
    rendered = render_alert(template, seed=42)
    assert rendered.text == "Shipment at Rotterdam contains components."


def test_render_ignores_slot_mapping_order() -> None:
    template = _prototype()
    reordered = replace(
        template,
        slots=dict(reversed(list(template.slots.items()))),
    )
    assert render_alert(template, 42) == render_alert(reordered, 42)


def test_render_is_stable_across_processes() -> None:
    # 更换 PYTHONHASHSEED 启动两个进程, 验证结果不依赖 Python 进程级随机哈希。
    script = """
from collie.data.alerts.bank import render_alert
from tests.test_alert_bank import _prototype

template = _prototype()

for seed in range(10):
    print(render_alert(template, seed).text)
"""
    outputs = []
    for hash_seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=env,
                text=True,
                encoding="utf-8",
            )
        )
    assert outputs[0] == outputs[1]


def test_leakage_scan_rejects_a_leaky_fixture(tmp_path) -> None:
    # 先证明样例结构合法, 再验证它因可见文本泄漏而失败, 避免把解析失败误当成扫描有效。
    path = tmp_path / "leaky_alert.yaml"
    path.write_text(LEAKY_YAML)
    # First prove this is structurally loadable, then reject its visible text.
    template = load_template_file(path)[0]
    rendered = render_alert(template, seed=42)
    findings = scan_text_for_leakage(rendered.text)
    assert any(item.startswith("exact_multiplier:") for item in findings)
    assert any(item.startswith("exact_onset:") for item in findings)
    assert any(item.startswith("exact_duration:") for item in findings)
    with pytest.raises(ValueError, match="alert text leakage"):
        assert_no_text_leakage(rendered.text)


@pytest.mark.parametrize(
    "text",
    [
        "Demand will be 1.5 times normal.",
        "Orders will increase by 50%.",
        "Only half the usual capacity is available.",
        "The hidden family is demand_level.",
        "A level shift has occurred.",
        "Disruption begins starting period 17.",
        "Containers will be held for exactly 4 weeks.",
    ],
)
def test_leakage_scan_detects_documented_patterns(text: str) -> None:
    with pytest.raises(ValueError, match="alert text leakage"):
        assert_no_text_leakage(text)


def test_leakage_scan_accepts_informative_vague_text() -> None:
    text = (
        "The supplier expects deliveries to take longer than usual; "
        "the recovery timeline remains uncertain."
    )
    assert scan_text_for_leakage(text) == ()
    assert_no_text_leakage(text)


@pytest.mark.parametrize(
    "literal",
    [
        "private_incident_marker",
        "benchmark_pattern_alpha",
        "article_042",
        "instances/example_case.json",
    ],
)
def test_leakage_scan_rejects_supplied_hidden_values(literal: str) -> None:
    # Synthetic values test the mechanism, not actual benchmark metadata.
    with pytest.raises(ValueError, match="forbidden_literal"):
        assert_no_text_leakage(
            f"Internal reference: {literal}",
            forbidden_literals=(literal,),
        )


def test_prototype_render_passes_leakage_scan() -> None:
    rendered = render_alert(_prototype(), seed=42)
    assert_no_text_leakage(rendered.text)


def _raw_prototype():
    return yaml.safe_load(PROTOTYPE_YAML)[0]


def _load_raw(tmp_path, raw):
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump([raw]), encoding="utf-8")
    return load_template_file(path)[0]


@pytest.mark.parametrize(
    "location,key,value",
    [
        ("outer", "unexpected", 1),
        ("hidden", "tau_j", 17),
        ("outer", "text", 42),
        ("outer", "id", ""),
        ("outer", "slots", {"port": [42]}),
        ("hidden", "onset_window", [True, 1]),
        ("hidden", "onset_window", [2, 1]),
        ("hidden", "onset_window", [1, 2, 3]),
        ("hidden", "onset_window", None),
        ("hidden", "magnitude_bin", None),
        ("hidden", "target_stream", "none"),
        ("hidden", "kind", "accurate"),
        ("hidden", "family", "demand_level"),
        ("outer", "kind", "neutral"),
        ("outer", "text", "Update {port.name}"),
        ("outer", "text", "Update {port!r}"),
    ],
)
def test_strict_loader_rejects_invalid_structure(tmp_path, location, key, value):
    raw = _raw_prototype()
    target = raw if location == "outer" else raw["alert_spec"]
    target[key] = value
    with pytest.raises(ValueError):
        _load_raw(tmp_path, raw)


def _distractor_raw():
    raw = _raw_prototype()
    raw["kind"] = "distractor"
    raw["alert_spec"].update(
        family="no_change",
        kind="distractor",
        target_stream="none",
        direction="none",
        onset_window=None,
        magnitude_bin=None,
        persistence="none",
        duration_bin="none",
        prospective_signature="test_only_unregistered_signature",
    )
    return raw


def test_distractor_keeps_outer_family_and_no_change_truth(tmp_path):
    t = _load_raw(tmp_path, _distractor_raw())
    assert t.family.value == "transit_pause"
    assert t.alert_spec.family.value == "no_change"
    assert t.alert_spec.magnitude_bin is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_stream", "arrival"),
        ("direction", "arrival_delayed"),
        ("onset_window", [-1, 1]),
        ("magnitude_bin", "medium"),
    ],
)
def test_rejects_malformed_no_change(tmp_path, field, value):
    raw = _distractor_raw()
    raw["alert_spec"][field] = value
    with pytest.raises(ValueError):
        _load_raw(tmp_path, raw)


def test_rejects_duplicate_yaml_key(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("- id: first\n  id: second\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate YAML key"):
        load_template_file(path)


def test_scans_every_slot_and_boundary():
    # 泄漏片段分散在相邻槽位中, 只有检查所有拼接结果才能发现。
    template = replace(
        _prototype(),
        text="Capacity is {amount}{unit}.",
        slots={"amount": ("uncertain", "50"), "unit": ("", "%")},
    )
    with pytest.raises(ValueError, match="exact_multiplier"):
        validate_template_leakage(template)


def test_all_slot_scan_accepts_prototype():
    validate_template_leakage(_prototype())


def test_excessive_slot_product_is_not_silently_sampled():
    with pytest.raises(ValueError, match="excessive"):
        validate_template_leakage(_prototype(), max_combinations=1)


def test_wording_holdout_rejects_test_overlap():
    from collie.contracts import Split

    first = _prototype()
    second = replace(first, template_id="other", split=Split.TEST)
    with pytest.raises(ValueError, match="wording families"):
        validate_wording_holdout((first, second))
    validate_wording_holdout((first, replace(second, wording_family="new_test_wording")))


def test_cross_template_render_collision_is_rejected():
    first = _prototype()
    second = replace(first, template_id="other")
    with pytest.raises(ValueError, match="repeated rendered text"):
        validate_no_repeated_renderings((first, second))


def test_prototype_is_not_a_complete_bank():
    with pytest.raises(ValueError, match="expected 180"):
        validate_bank_composition((_prototype(),))


def test_composition_checker_uses_every_cell():
    # Synthetic objects exercise counts only: these are NOT authored production templates.
    # 这里的合成模板只测试计数器; 正式 180 条模板另由下方 bank fixture 验收。
    from collie.contracts import AlertKind, ShockFamily, Split

    base = _prototype()
    templates = []
    for family in set(ShockFamily) - {ShockFamily.NO_CHANGE}:
        for split in (Split.DEV, Split.CAL, Split.TEST):
            for kind, count in (
                (AlertKind.ACCURATE, 4),
                (AlertKind.OVERSTATED, 2),
                (AlertKind.AMBIGUOUS, 2),
                (AlertKind.DISTRACTOR, 2),
            ):
                for index in range(count):
                    templates.append(
                        replace(
                            base,
                            template_id=f"{family}-{split}-{kind}-{index}",
                            family=family,
                            split=split,
                            kind=kind,
                        )
                    )
    validate_bank_composition(tuple(templates))
    broken = list(templates)
    broken[0] = replace(broken[0], kind=AlertKind.NEUTRAL)
    with pytest.raises(ValueError, match="4/2/2/2"):
        validate_bank_composition(tuple(broken))


@pytest.fixture(scope="module")
def bank():
    # 直接加载准备提交的正式模板库, 避免只对 prototype 测试就宣称 CP1 已完成。
    from collie.data.alerts.bank import load_alert_bank

    return load_alert_bank(ROOT / "collie/data/alerts/templates")


def test_total_is_180(bank):
    assert len(bank) == 180


def test_composition_per_family_split_cell(bank):
    validate_bank_composition(bank)


def test_distractors_are_no_change(bank):
    distractors = [t for t in bank if t.kind.value == "distractor"]
    assert len(distractors) == 36
    assert all(t.alert_spec.family.value == "no_change" for t in distractors)


def test_instantiation_is_deterministic(bank):
    for template in bank:
        for seed in (0, 42, 1001):
            assert render_alert(template, seed) == render_alert(template, seed)


def test_template_id_survives_instantiation(bank):
    for template in bank:
        assert render_alert(template, 42).template_id == template.template_id


def test_no_repeated_rendered_string_within_split(bank):
    validate_no_repeated_renderings(bank)


def test_no_test_wording_family_in_dev_or_cal(bank):
    validate_wording_holdout(bank)


def test_alert_spec_vocabulary_matches_shockspec(bank):
    # 显式映射 family 到 shock_family, 再构造冻结 ShockSpec; 不把字段名称差异当作词表不一致。
    from dataclasses import asdict

    from collie.contracts import ShockSpec

    for template in bank:
        payload = asdict(template.alert_spec)
        payload["shock_family"] = payload.pop("family")
        payload.pop("kind")
        spec = ShockSpec(
            **payload,
            evidence_refs=(),
            tau_j=0,
            proposal_index=1,
            model_id="test",
            decoding_hash="test",
            prompt_hash="test",
        )
        for key, value in payload.items():
            assert getattr(spec, key) == value


def test_production_bank_leakage_against_manifests(bank):
    from collie.data.alerts.bank import forbidden_from_metadata

    forbidden = forbidden_from_metadata(
        ROOT / "manifests/benchmark_v1.json", ROOT / "manifests/shockspec_v1.json"
    )
    assert len(forbidden) > 1000
    for template in bank:
        validate_template_leakage(template, forbidden_literals=forbidden)


def test_incident_metadata_is_scanned(tmp_path):
    from collie.data.alerts.bank import forbidden_from_metadata

    incident = tmp_path / "incident.json"
    incident.write_text('{"nested": {"secret": "private_marker", "magnitude": 1.75}}')
    forbidden = forbidden_from_metadata(
        ROOT / "manifests/benchmark_v1.json", ROOT / "manifests/shockspec_v1.json", [incident]
    )
    for text in (
        "private_marker",
        "1.75",
        "p01_stationary_iid",
        "108775044",
        "real_trajectory/lead_time_0/108775044",
    ):
        with pytest.raises(ValueError, match="leakage"):
            assert_no_text_leakage(text, forbidden_literals=forbidden)


def test_rollout_reuse_allowed_only_for_paired_unit(bank):
    # 同 unit 复用是配对设计, 不同 unit 复用则违反刺激唯一性; 两条路径都必须验证。
    from collie.data.alerts.bank import validate_rollout_renderings

    rendered = render_alert(bank[0], 0)
    validate_rollout_renderings([("unit-a", rendered), ("unit-a", rendered)])
    with pytest.raises(ValueError, match="repeated rollout"):
        validate_rollout_renderings([("unit-a", rendered), ("unit-b", rendered)])


def test_registry_injection_rejects_illegal_pairing():
    # 用小型测试映射验证拒绝机制; 测试通过不代表真实模块 02 registry 已完成集成。
    from collie.data.alerts.bank import validate_registry

    template = _prototype()
    kwargs = dict(
        onset_windows=((-1, 1),), family_signatures={template.family: {"sig_arrival_stall"}}
    )
    validate_registry((template,), **kwargs)
    with pytest.raises(ValueError, match="family/signature"):
        validate_registry(
            (
                replace(
                    template,
                    alert_spec=replace(
                        template.alert_spec, prospective_signature="sig_demand_level_up"
                    ),
                ),
            ),
            **kwargs,
        )
    with pytest.raises(ValueError, match="onset window"):
        validate_registry(
            (replace(template, alert_spec=replace(template.alert_spec, onset_window=(8, 9))),),
            **kwargs,
        )
