from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from collie.arms.base_stock import ARM1_ARM_ID
from collie.arms.llm_to_or import ARM7_ARM_ID
from collie.arms.shockspec import ARM9_ARM_ID, ARM10_ARM_ID
from collie.contracts import Direction, MagnitudeBin, ShockFamily, TargetStream
from collie.control.grid import (
    BASELINE_CONFIG,
    GAMMA_VALUES,
    L_EFF_VALUES,
    M_VALUES,
    all_configs,
)
from collie.control.mapping import CANONICAL_SHAPES, _make_spec, compile_spec
from collie.eval.prereg import (
    load_preregistration,
    primary_stratum_weights,
    render_preregistration_summary,
    validate_preregistration,
)
from collie.spec.registry import ONSET_WINDOWS, SIGNATURES
from collie.trigger.calibration import FROZEN
from collie.verify.registry import CONSTRUCTIONS
from tools.freeze import REGISTERED_FILES, FileRecord, changed_records, missing_registered_files


def final_prereg() -> dict:
    draft = load_preregistration(require_final=False).data
    data = copy.deepcopy(dict(draft))
    data["metadata"] = {"version": 1, "draft": False, "frozen_before_test_runs": True}
    data["trigger_thresholds"] = {"alert_or_detector": 1.0, "cusum": 2.0, "page_hinkley": 3.0}
    data["controller_grid"] = {"order_cap": 250.0, "labelled_as_ours": True}
    data["compiler_mapping_table"] = {"entries": [{"family": "no_change", "config": "baseline"}]}
    data["schema_thresholds"] = {"minimum_evidence_refs": 1, "trust_region_overlap": 0.5}
    data["oracle_mappings"] = {"entries": [{"family": "no_change", "config": "baseline"}]}
    data["trust_region"] = {"definition": "registered finite overlap rule"}
    for item in data["go_criteria"]:
        item["threshold"] = 0.0
    for key in data["kill_thresholds"]:
        data["kill_thresholds"][key] = 0.0
    return data


def test_real_preregistration_is_final() -> None:
    prereg = load_preregistration(require_final=True)
    assert not prereg.is_draft
    assert len(prereg.data["kill_thresholds"]) == 7
    assert prereg.data["metadata"]["frozen_before_test_runs"] is True


def test_prereg_parses_and_is_complete_when_final_values_are_supplied() -> None:
    validate_preregistration(final_prereg(), require_final=True)


def test_all_seven_kill_thresholds_are_numeric() -> None:
    data = final_prereg()
    assert len(data["kill_thresholds"]) == 7
    assert all(isinstance(v, int | float) for v in data["kill_thresholds"].values())


def test_holm_family_has_six_members() -> None:
    assert len(final_prereg()["holm_family"]["members"]) == 6


def test_prereg_summary_prints_registered_commitments() -> None:
    summary = render_preregistration_summary(final_prereg())
    assert "Confirmatory contrasts" in summary
    for contrast in final_prereg()["confirmatory_contrasts"]:
        assert contrast["id"] in summary
    assert "Holm family" in summary
    assert "Kill thresholds" in summary
    for key in final_prereg()["kill_thresholds"]:
        assert key in summary


def test_stratum_weights_sum_to_one() -> None:
    data = final_prereg()
    for section in data["stratum_weights"].values():
        assert sum(section.values()) == pytest.approx(1.0)
    assert sum(primary_stratum_weights(data).values()) == pytest.approx(1.0)


def test_freeze_manifest_covers_every_registered_file_name() -> None:
    assert set(REGISTERED_FILES) >= {
        "collie/contracts.py",
        "prereg/prereg_v1.yaml",
        "manifests/shockspec_v1.json",
    }


def test_all_registered_method_files_exist() -> None:
    assert missing_registered_files() == ()


def test_method_freeze_is_complete_with_final_preregistration() -> None:
    manifest = json.loads(Path("prereg/freeze_manifest.json").read_text(encoding="utf-8"))
    assert manifest["preregistration_final"] is True
    assert manifest["complete"] is True
    assert manifest["incomplete_reasons"] == []


def test_approved_pilot_thresholds_and_policy_are_registered() -> None:
    data = load_preregistration(require_final=True).data
    assert {item["id"]: item["threshold"] for item in data["go_criteria"]} == {
        "profit_lift": 0.0,
        "lost_sales_reduction": 0.0,
        "false_activation_control": 0.95,
        "wrong_family_exposure": 0.10,
        "fill_rate_floor": 0.95,
        "cost_frontier": 1.0,
        "recovery_time": 4.0,
    }
    assert data["kill_thresholds"] == {
        "insufficient_headroom": 3,
        "detector_indistinguishable": 0.0,
        "false_activation_rate": 0.10,
        "wrong_family_activation_rate": 0.25,
        "parser_failure_rate": 0.10,
        "budget_overrun_rate": 0.10,
        "negative_profit_lift": 0.0,
    }
    assert data["pilot_policy"]["call_budget_per_episode"] == 4
    assert data["pilot_policy"]["never_recovered_value"] == 51
    assert "prereg/threshold_rationale.md" in REGISTERED_FILES


def test_trigger_thresholds_match_frozen_calibration() -> None:
    thresholds = load_preregistration(require_final=False).data["trigger_thresholds"]
    assert thresholds["mu0"] == FROZEN.mu0
    assert thresholds["sigma0"] == FROZEN.sigma0
    assert thresholds["cusum_k"] == FROZEN.cusum_k
    assert thresholds["cusum_h"] == FROZEN.cusum_h
    assert thresholds["page_hinkley_delta"] == FROZEN.ph_delta
    assert thresholds["page_hinkley_threshold"] == FROZEN.ph_threshold
    assert thresholds["refractory_window"] == FROZEN.refractory_window
    assert thresholds["max_proposals"] == FROZEN.max_proposals


def test_confirmatory_contrasts_use_real_arm_ids() -> None:
    contrasts = load_preregistration(require_final=False).data["confirmatory_contrasts"]
    assert contrasts == [
        {"id": "arm10_vs_arm1", "treatment": ARM10_ARM_ID, "control": ARM1_ARM_ID},
        {"id": "arm10_vs_arm7", "treatment": ARM10_ARM_ID, "control": ARM7_ARM_ID},
        {"id": "arm10_vs_arm9", "treatment": ARM10_ARM_ID, "control": ARM9_ARM_ID},
    ]


def test_controller_grid_matches_code() -> None:
    grid = load_preregistration(require_final=False).data["controller_grid"]
    assert tuple(grid["demand_multipliers"]) == M_VALUES
    assert tuple(grid["effective_lead_times"]) == L_EFF_VALUES
    assert tuple(grid["pipeline_credit_weights"]) == GAMMA_VALUES
    assert grid["config_count"] == len(all_configs()) == 72
    assert grid["baseline"] == {
        "m": BASELINE_CONFIG.m,
        "l_eff": BASELINE_CONFIG.l_eff,
        "gamma": BASELINE_CONFIG.gamma,
        "predictive_model": BASELINE_CONFIG.predictive_model,
    }


def _enum(enum_type, value: str):
    return enum_type(value)


def test_compiler_mapping_matches_the_code() -> None:
    table = load_preregistration(require_final=False).data["compiler_mapping_table"]
    entries = {
        (
            _enum(ShockFamily, item["family"]),
            _enum(Direction, item["direction"]),
            _enum(TargetStream, item["target_stream"]),
        ): item["by_magnitude"]
        for item in table["entries"]
    }
    assert set(entries) == set(CANONICAL_SHAPES)
    magnitudes = tuple(m for m in MagnitudeBin if m.value != "none")
    for shape in CANONICAL_SHAPES:
        family, direction, stream = shape
        for magnitude in magnitudes:
            spec = _make_spec(family, direction, magnitude, stream, tag="prereg-test")
            config = compile_spec(spec)
            registered = entries[shape][magnitude.value]
            assert registered == {
                "m": config.m,
                "l_eff": config.l_eff,
                "gamma": config.gamma,
                "predictive_model": config.predictive_model,
            }


def test_schema_registry_matches_the_code() -> None:
    schema = load_preregistration(require_final=False).data["schema_thresholds"]
    assert tuple(tuple(window) for window in schema["onset_windows"]) == ONSET_WINDOWS
    assert tuple(schema["signatures"]) == SIGNATURES
    assert schema["minimum_evidence_refs"] == 0


def test_oracle_mappings_match_verifier_registry() -> None:
    prereg_entries = load_preregistration(require_final=False).data["oracle_mappings"]["entries"]
    registered = {item["predictive_model"]: item for item in prereg_entries}
    assert set(registered) == set(CONSTRUCTIONS)
    for key, construction in CONSTRUCTIONS.items():
        assert registered[key] == {
            "predictive_model": construction.predictive_model,
            "family": construction.family.value,
            "signature": construction.signature,
            "stream": construction.stream.value,
            "direction": construction.direction.value,
            "construction": construction.construction,
            "validity": construction.validity,
        }


def test_pilot_criteria_register_comparison_directions() -> None:
    data = load_preregistration(require_final=False).data
    go_operators = {item["id"]: item["operator"] for item in data["go_criteria"]}
    assert go_operators == {
        "profit_lift": ">=",
        "lost_sales_reduction": ">=",
        "false_activation_control": ">=",
        "wrong_family_exposure": "<=",
        "fill_rate_floor": ">=",
        "cost_frontier": ">=",
        "recovery_time": "<=",
    }
    kill_operators = {item["id"]: item["operator"] for item in data["kill_triggers"]}
    assert kill_operators == {
        "insufficient_headroom": "<=",
        "detector_indistinguishable": "<=",
        "false_activation_rate": ">=",
        "wrong_family_activation_rate": ">=",
        "parser_failure_rate": ">=",
        "budget_overrun_rate": ">=",
        "negative_profit_lift": "<=",
        "method_freeze_or_quarantine_violation": "==",
    }


def test_deliberate_edit_turns_the_guard_red() -> None:
    frozen = {
        "git_sha": "old-git",
        "files": {
            "registered.py": {
                "sha256": "old-file",
                "lines": 1,
                "bytes": 3,
                "missing": False,
            }
        },
    }
    changed = changed_records(
        frozen,
        (
            FileRecord(
                path="registered.py",
                sha256="new-file",
                lines=1,
                bytes=3,
            ),
        ),
        current_git_sha="old-git",
    )
    assert changed == [("registered.py", "old-file", "new-file")]


def test_git_sha_change_turns_the_guard_red() -> None:
    frozen = {"git_sha": "old-git", "files": {}}
    changed = changed_records(frozen, (), current_git_sha="new-git")
    assert changed == [("<git-sha>", "old-git", "new-git")]


def test_descendant_commit_does_not_invalidate_frozen_base_sha() -> None:
    frozen = {"git_sha": "base-git", "files": {}}
    changed = changed_records(
        frozen,
        (),
        current_git_sha="descendant-git",
        recorded_git_is_ancestor=True,
    )
    assert changed == []
