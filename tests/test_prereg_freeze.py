from __future__ import annotations

import copy

import pytest

from collie.eval.prereg import (
    load_preregistration,
    primary_stratum_weights,
    render_preregistration_summary,
    validate_preregistration,
)
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


def test_prereg_parses_as_draft_until_owner_values_land() -> None:
    prereg = load_preregistration(require_final=False)
    assert prereg.is_draft
    assert len(prereg.data["kill_thresholds"]) == 7
    with pytest.raises(ValueError, match="draft"):
        validate_preregistration(prereg.data, require_final=True)


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


def test_missing_registered_files_are_explicit_until_upstream_modules_land() -> None:
    missing = set(missing_registered_files())
    assert "collie/spec/registry.py" in missing
    assert "collie/control/mapping.py" in missing


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
