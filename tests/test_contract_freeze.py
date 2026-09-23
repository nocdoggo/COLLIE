"""Gate 1 — the contract freeze tripwire and the gate's own checklist.

Gate 1 is the point where all eight branches start building against a fixed vocabulary. Its four
conditions are asserted here so "the gate passed" is a checkable claim rather than a recollection:

1. ``collie/contracts.py`` is frozen and matches its recorded hash.
2. The accounting-equivalence report exists and records exact agreement.
3. Arm 1 reproduces the published OR baseline, and runs under both harnesses.
4. A deviations log exists with the rule that permits change only when declared.

The tag itself is a git operation and is deliberately not asserted here; a test that demanded a
particular tag would fail on every fork and every shallow clone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.freeze_contracts import (
    DEVIATIONS_PATH,
    FREEZE_PATH,
    FROZEN_FILES,
    current_records,
    deviation_declared,
    drift,
    hash_file,
    load_freeze,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# condition 1 — the freeze
# ---------------------------------------------------------------------------


def test_the_freeze_record_exists_and_is_well_formed() -> None:
    frozen = load_freeze()
    assert frozen["gate"] == "gate1"
    assert frozen["schema_version"] == 1
    assert frozen["frozen_at"], "the freeze must carry the date it was taken"
    assert set(frozen["files"]) == set(FROZEN_FILES)
    for record in frozen["files"].values():
        assert len(record["sha256"]) == 64
        assert record["lines"] > 0
        assert record["bytes"] > 0


def test_frozen_contracts_have_not_drifted() -> None:
    """The tripwire. If this fails, either declare a deviation or revert the edit."""
    changed = drift()
    if not changed:
        return
    undeclared = [(p, o, n) for p, o, n in changed if not deviation_declared(p, n)]
    assert not undeclared, (
        "frozen contract changed without a declared deviation:\n  "
        + "\n  ".join(f"{p}: {o[:12]} -> {n[:12]}" for p, o, n in undeclared)
        + "\n\nGate 1 froze collie/contracts.py so every branch could build against it. To change "
        "it: add a dated entry to prereg/deviations.md naming the file and its new sha256, then "
        "run `uv run python -m tools.freeze_contracts`."
    )
    pytest.fail(
        "the deviation is declared but the freeze record is stale; re-run "
        "`uv run python -m tools.freeze_contracts` so the record matches reality"
    )


def test_the_hash_ignores_line_endings_only(tmp_path: Path) -> None:
    """A CRLF checkout must not look like an edit, but a real edit must."""
    unix = tmp_path / "a.py"
    windows = tmp_path / "b.py"
    edited = tmp_path / "c.py"
    unix.write_bytes(b"x = 1\ny = 2\n")
    windows.write_bytes(b"x = 1\r\ny = 2\r\n")
    edited.write_bytes(b"x = 1\ny = 3\n")

    assert hash_file(tmp_path / "a.py").sha256 == hash_file(tmp_path / "b.py").sha256
    assert hash_file(tmp_path / "a.py").sha256 != hash_file(tmp_path / "c.py").sha256


def test_a_stale_deviation_cannot_authorise_a_later_edit() -> None:
    """Declaring a deviation requires the *new* hash, not just the filename.

    Otherwise one entry from months ago would license every future edit to that file.
    """
    path = FROZEN_FILES[0]
    assert not deviation_declared(path, "0" * 64), (
        "a hash that was never declared must not count as declared"
    )
    live = next(r for r in current_records() if r.path == path)
    frozen_sha = load_freeze()["files"][path]["sha256"]
    assert frozen_sha == live.sha256
    if deviation_declared(path, live.sha256):
        assert not deviation_declared(path, "f" * 64), (
            "an accepted deviation must not authorise a later, different edit"
        )


def test_the_deviations_log_states_the_rule() -> None:
    text = DEVIATIONS_PATH.read_text(encoding="utf-8")
    assert "contract_freeze.json" in text
    assert "freeze_manifest.json" in text, "the Gate 2 artefact must be anticipated"
    assert "sha256" in text
    for gate in ("Gate 1", "Gate 2", "Gate 3"):
        assert gate in text


# ---------------------------------------------------------------------------
# condition 2 — the equivalence report
# ---------------------------------------------------------------------------


def test_the_equivalence_report_records_exact_agreement() -> None:
    report = (REPO_ROOT / "reports" / "equivalence_report.md").read_text(encoding="utf-8")
    assert "maximum absolute difference: **0.0**" in report, (
        "Gate 1 requires exact accounting agreement, not agreement within a tolerance"
    )
    assert "216 instances" in report
    assert "648" in report


def test_the_equivalence_instance_set_is_committed_and_large_enough() -> None:
    path = REPO_ROOT / "manifests" / "equivalence_instances.txt"
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(lines) >= 200, f"only {len(lines)} instances committed"
    labels = {"lead_time_0", "lead_time_4", "lead_time_stochastic"}
    covered = {label for line in lines for label in labels if label in line.split("/")}
    assert covered == labels, f"missing lead-time strata: {labels - covered}"


# ---------------------------------------------------------------------------
# condition 3 — arm 1 from both harnesses
# ---------------------------------------------------------------------------


def test_arm1_report_confirms_both_harnesses_and_exact_reproduction() -> None:
    report = (REPO_ROOT / "reports" / "arm1_or_baseline.md").read_text(encoding="utf-8")
    assert "1320/1320" in report, "order-level identity under the env harness"
    assert "880/1320" in report, "and where the eval harness still agrees"
    assert "arm 1, `env` harness" in report
    assert "arm 1, `eval` harness" in report
    assert "0.44471016183446377" in report, "the published figure must be named"


# ---------------------------------------------------------------------------
# condition 4 — the gate is self-describing
# ---------------------------------------------------------------------------


def test_gate1_artifacts_all_exist() -> None:
    """One place that lists what Gate 1 produced, so a missing artefact is loud."""
    required = [
        FREEZE_PATH,
        DEVIATIONS_PATH,
        REPO_ROOT / "manifests" / "benchmark_v1.json",
        REPO_ROOT / "manifests" / "equivalence_instances.txt",
        REPO_ROOT / "reports" / "equivalence_report.md",
        REPO_ROOT / "reports" / "arm1_or_baseline.md",
        REPO_ROOT / "docs" / "env_contract.md",
        REPO_ROOT / "docs" / "derivation_note.md",
    ]
    missing = [p.relative_to(REPO_ROOT).as_posix() for p in required if not p.is_file()]
    assert not missing, f"Gate 1 artefacts missing: {missing}"


def test_the_benchmark_pin_is_consistent_across_artifacts() -> None:
    """The manifest and the equivalence set must describe the same benchmark commit."""
    manifest_commit = json.loads(
        (REPO_ROOT / "manifests" / "benchmark_v1.json").read_text(encoding="utf-8")
    )["benchmark_commit"]
    selection = (REPO_ROOT / "manifests" / "equivalence_instances.txt").read_text(encoding="utf-8")
    assert f"benchmark_commit: {manifest_commit}" in selection, (
        "the equivalence set was selected against a different benchmark commit than the audit"
    )
