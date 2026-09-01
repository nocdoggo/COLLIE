"""Task 2 acceptance tests: the audited contract is complete, correct, and byte-stable.

Guards collie-shock-generator R1.1-R1.7. These tests read the committed manifest so they stay
fast; `test_manifest_regenerates_byte_identically` is the one that touches the benchmark.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "manifests" / "benchmark_v1.json"
CONTRACT = REPO_ROOT / "docs" / "env_contract.md"


@pytest.fixture(scope="module")
def manifest() -> dict:
    if not MANIFEST.is_file():
        pytest.skip("manifest not built yet; run `make audit`")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_instance_census_matches_the_published_benchmark(manifest: dict) -> None:
    """R1.1: 720 synthetic + 600 real = 1,320."""
    counts = manifest["counts"]
    assert counts["instances_total"] == 1320
    assert counts["by_trajectory_type"] == {
        "real_trajectory": 600,
        "synthetic_trajectory": 720,
    }
    assert counts["real_articles"] == 200
    assert len(counts["synthetic_families"]) == 10
    assert sorted(counts["synthetic_cost_ratios"]) == ["high", "low", "med"]


def test_horizon_is_unanimous_and_real_is_47(manifest: dict) -> None:
    """R1.2: resolved from the CSVs, not from either document's prose."""
    horizons = manifest["horizon"]["observation_counts_by_type"]
    assert horizons["real_trajectory"] == [47], "real horizon must be exactly 47 decisions"
    assert horizons["synthetic_trajectory"] == [50]
    # unanimity matters: a mixed histogram would mean the horizon is instance-dependent
    assert all(r["observation_count"] == 47 for r in manifest["instances"] if r["article_id"])


def test_sweep_totals_are_derived_and_match_the_independent_figure(manifest: dict) -> None:
    """R1.6: derived by summing observation_count, not transcribed."""
    totals = manifest["derived_sweep_totals"]
    by_type = totals["decisions_by_trajectory_type"]
    assert by_type["synthetic_trajectory"] == 720 * 50 == 36_000
    assert by_type["real_trajectory"] == 600 * 47 == 28_200
    assert totals["always_online_calls_full_benchmark"] == 64_200
    # and the sum is internally consistent with the per-instance records
    assert sum(r["observation_count"] for r in manifest["instances"]) == 64_200


def test_promised_versus_actual_lead_times_are_both_recorded(manifest: dict) -> None:
    """R1.3: the two documents describe different quantities; record both."""
    assert manifest["promised_lead_time_by_dir"] == {
        "lead_time_0": 0,
        "lead_time_4": 4,
        "lead_time_stochastic": 2,
    }
    check = manifest["upstream_constant_check"]
    assert check["agrees"], f"our mirrored mapping drifted from upstream: {check}"

    actual_by_label: dict[str, set[str]] = {}
    for rec in manifest["instances"]:
        actual_by_label.setdefault(rec["lead_time_label"], set()).update(rec["actual_lead_times"])
    assert actual_by_label["lead_time_0"] == {"0"}
    assert actual_by_label["lead_time_4"] == {"4"}
    assert actual_by_label["lead_time_stochastic"] == {"1", "2", "3", "inf"}


def test_lost_shipments_exist_only_under_stochastic_lead_times(manifest: dict) -> None:
    """`inf` encodes a lost shipment; it must not leak into the deterministic settings."""
    lossy = [r for r in manifest["instances"] if r["n_lost_periods"] > 0]
    assert lossy, "expected some instances with lost shipments"
    assert all(r["lead_time_label"] == "lead_time_stochastic" for r in lossy)


def test_order_cap_is_absent_upstream_and_flagged_as_ours(manifest: dict) -> None:
    """R1.4: no cap exists, so ours must be explicitly marked as defined by us."""
    cap = next(r for r in manifest["resolutions"] if "Order cap" in r["question"])
    assert cap["defined_by_us"] is True
    assert "NO CAP EXISTS" in cap["answer"]
    assert cap["evidence"]


def test_every_required_semantic_is_resolved_with_evidence(manifest: dict) -> None:
    """R1.5: event ordering, lost-order semantics, and observability are all recorded."""
    questions = " ".join(r["question"] for r in manifest["resolutions"])
    for topic in (
        "horizon",
        "Lead-time",
        "Order cap",
        "in-transit",
        "event ordering",
        "lost or backordered",
        "shipment ages",
    ):
        assert topic in questions, f"no resolution covers {topic!r}"
    for res in manifest["resolutions"]:
        assert res["answer"].strip(), f"empty answer for {res['question']!r}"
        assert res["evidence"], f"no evidence cited for {res['question']!r}"


def test_harness_divergence_on_lost_orders_is_recorded_with_a_decision(manifest: dict) -> None:
    """The two simulators disagree; the contract must name the authoritative one."""
    res = next(r for r in manifest["resolutions"] if "in-transit total" in r["question"])
    assert "DIVERGE" in res["answer"]
    assert "eval/ path as AUTHORITATIVE" in res["answer"]


def test_profit_is_constant_within_every_instance(manifest: dict) -> None:
    """The evaluator's perfect-foresight bound reads profit from the first row only;
    that is safe only if profit does not vary within an instance."""
    assert all(r["constant_profit"] for r in manifest["instances"])


def test_contract_document_exists_and_states_what_we_defined() -> None:
    assert CONTRACT.is_file(), "docs/env_contract.md is the human-readable Task 2 output"
    text = CONTRACT.read_text(encoding="utf-8")
    for required in (
        "64,200",  # derived sweep total
        "47 decisions",  # resolved horizon
        "no upper bound on the order",  # cap finding
        "Things we defined ourselves",  # explicit provenance section
        "eval/` path is authoritative",  # divergence decision
        "transit pause",  # what the sidecar is actually needed for
    ):
        assert required in text, f"env_contract.md must state: {required!r}"


@pytest.mark.needs_benchmark
def test_manifest_regenerates_byte_identically(tmp_path: Path) -> None:
    """R1.7: the manifest must be diffable in review, so regeneration is byte-stable."""
    out = tmp_path / "regen.json"
    subprocess.run(
        [sys.executable, "-m", "tools.audit_benchmark", "--out", str(out), "--quiet"],
        cwd=REPO_ROOT,
        check=True,
    )
    assert out.read_bytes() == MANIFEST.read_bytes(), (
        "manifest is not byte-stable across runs; remove any nondeterminism "
        "(timestamps, set iteration order, unstable float formatting)"
    )
