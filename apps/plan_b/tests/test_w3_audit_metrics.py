"""Metric fixes of the Wave 3 freeze audit (``08_evaluation.md`` definitions), from real
development traces where the shape matters and small synthetic traces otherwise.

* Extraction labels read P2/P3's recorded change specs (they name their observation in
  ``evidence_refs``), P0's frozen parser replayed over the episode, and the event id (D1).
* Supported partial fulfillment and infeasibility read only structured fields: no digit or
  constraint name in a summary counts (D2).
* Modeled cost does not add hold fees again: committed money already includes them (D3).
* The recovery median counts unrecovered episodes at their horizon, as a lower bound (D4).
* Plan churn counts previously valid assignments only: one already failing its hard checks is
  repaired, not churned (D5).
* A trace that no longer matches its record is a failure, not scored silently (D7).
* Verification provenance: a verify decision reporting success cites a successful check; a
  status observation from any actor's successful check is linked (D10).
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from plan_b.evaluation.export_trace import build_trace
from plan_b.evaluation.metrics import (
    class_success,
    episode_metrics,
    extraction_labels,
    pantry_metrics,
    plan_churn,
    policy_aggregate,
    suite_metrics,
)
from plan_b.evaluation.run import load_results, run_evaluation
from plan_b.evaluation.scoring import public_summary
from plan_b.scenarios.runner import run_case
from plan_b.store.database import Database
from tests.test_eval_metrics import trace_of

ANNOTATION = {
    "source_record_id": "delivery_message_17",
    "event_id": "e_showcase_01",
    "resource_id": "projector",
    "effective_time": "2026-11-05T17:25:00-05:00",
    "claimed_change": "delay",
    "booking_ref": "P17",
}


@pytest.fixture(scope="module")
def dev01_p0(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    db = Database(tmp_path_factory.mktemp("dev01") / "p.sqlite3")
    result = run_case(db, "dev01")
    return build_trace(db, result.episode_id, policy_id=result.report.policy_id)


# ---------------------------------------------------------------------------------- D1


def test_a_live_change_spec_is_matched_to_its_observation_by_evidence_refs() -> None:
    spec = {
        "artifact_type": "change_spec",
        "change_id": "chg_obs_notice_01",
        "change_kind": "delay",
        "event_id": "e_showcase_01",
        "evidence_refs": ["obs_notice_01"],
        "subject_id": "projector",
    }
    case = {"annotations": [ANNOTATION | {"source_record_id": "msg_a"}]}

    def label(*items: dict[str, Any]) -> list[dict[str, Any]]:
        trace = trace_of(
            decisions=[{"kind": "verify", "details": {"interpretations": list(items)}}]
        )
        return extraction_labels(trace, case) or []

    assert [e["label"] for e in label(spec)] == ["correct"]
    wrong = label(spec | {"event_id": "e_other"})
    assert wrong[0]["label"] == "incorrect" and wrong[0]["mismatched"] == ["event_id"]
    lost = {"observation_id": "obs_notice_01", "failure": "provider_error"}
    assert [e["label"] for e in label(lost)] == ["not_recorded"]


def test_p0s_reading_is_its_frozen_parser_replayed(dev01_p0: dict[str, Any]) -> None:
    case = {"annotations": [ANNOTATION]}
    assert extraction_labels(dev01_p0, case) == [
        {
            "source_record_id": "delivery_message_17",
            "observation_id": "obs_notice_01",
            "label": "not_recorded",
            "mismatched": [],
        }
    ]
    labels = extraction_labels(dev01_p0, case, "P0") or []
    assert [(e["label"], e["mismatched"]) for e in labels] == [("correct", [])]
    late = extraction_labels(
        dev01_p0,
        {"annotations": [ANNOTATION | {"effective_time": "2026-11-05T17:40:00-05:00"}]},
        "P0",
    )
    assert late is not None and late[0]["mismatched"] == ["effective_time"]


# ---------------------------------------------------------------------------------- D2


def _partial(decision: dict[str, Any]) -> tuple[bool, list[str], str | None]:
    pantry = {
        "targets": [
            {
                "target_id": "kits_40",
                "original_target": 40,
                "current_target": 40,
                "on_time": 34,
                "service_deficit": 6,
                "attained": False,
            }
        ],
        "conservation_failures": 0,
    }
    case = {"outcome_class": "partial", "achievable_on_time": 34, "target_quantity": 40}
    outcome = {"goal_complete": False, "violations": []}
    return class_success(case, outcome, trace_of(decisions=[decision]), pantry)


def test_the_reported_deficit_comes_from_structured_fields_only() -> None:
    base = {"kind": "infeasible", "details": {"blocking_constraints": ["stock_transfer"]}}
    wrong = base | {
        "summary": "infeasible at revision 16",
        "details": base["details"] | {"shortfall_quantity": 16, "target_id": "kits_40"},
    }
    assert _partial(wrong)[0] is False  # the "6" in "16" is not a report of six
    right = base | {
        "summary": "infeasible at revision 12",
        "details": base["details"]
        | {"chosen_by": "model", "shortfalls": [{"target_id": "kits_40", "shortfall_quantity": 6}]},
    }
    assert _partial(right) == (True, [], "model")
    textual = base | {"summary": "covers 34, leaving 6 unfulfilled"}
    assert _partial(textual)[0] is False


# ---------------------------------------------------------------------------------- D3, D4


def test_modeled_cost_counts_each_hold_fee_once(dev01_p0: dict[str, Any]) -> None:
    trace = copy.deepcopy(dev01_p0)
    hold = {
        "hold_id": "hold_x",
        "actor_id": "agent_demo",
        "created_at": "2026-11-05T21:41:00Z",
        "terminal_at": "2026-11-05T21:51:00Z",
        "effective_status": "expired",
        "hold_fee_cents": 200,
    }
    trace["final_state"]["holds"] = [hold]
    record = {
        "status": "completed",
        "outcome": {"goal_complete": True, "committed_cents": 200, "violations": []},
        "trace": {"verify": "intact"},
    }
    plan = {"key": "k", "case_ref": "dev01", "policy": "P0", "seed": None, "trial": 1}
    entry = {"plan": plan | {"position": 1}, "record": record, "trace": trace}
    row = episode_metrics(entry, {"outcome_class": "goal", "suite": "campus"})
    assert row["preparation"]["hold_fee_cents"] == 200
    assert row["modeled_cost_cents"] == row["committed_cents"] == 200


def test_the_recovery_median_counts_unrecovered_episodes_at_their_horizon() -> None:
    def row(recovered: bool, delay: int) -> dict[str, Any]:
        return {
            "status": "completed",
            "outcome_class": "goal",
            "negative_control": False,
            "success": recovered,
            "case_id": "C01",
            "plan_churn": {"total": 0},
            "recovery": {"recovered": recovered, "delay_minutes": delay, "horizon_minutes": 80},
        }

    rec = policy_aggregate([row(True, 3), row(False, 80), row(False, 80)])["recovery"]
    assert (rec["recovered"], rec["required"]) == (1, 3)
    assert rec["median_minutes"] == 80 and rec["median_is_lower_bound"] is True
    assert rec["median_recovered_minutes"] == 3 and rec["unrecovered_horizons"] == [80, 80]


# ---------------------------------------------------------------------------------- D5


def test_churn_counts_only_previously_valid_assignments(dev01_p0: dict[str, Any]) -> None:
    """dev01: the swap moves demonstrations (already failing its arrival check: the projector's
    ETA is after its start) and skills exchange (valid): one revision, one churned assignment."""
    assert plan_churn(dev01_p0) == {
        "committed_revisions": 1,
        "altered_assignments": 2,
        "previously_valid_altered": 1,
        "total": 2,
    }


# ---------------------------------------------------------------------------------- D7


def test_a_trace_that_no_longer_matches_its_record_is_a_failure(tmp_path: Path) -> None:
    out = tmp_path / "tampered"
    run_evaluation(
        suite="campus", cases=["dev01"], policies=["P0"], seeds=[], out=out, log=lambda _l: None
    )
    path = out / "episodes" / "dev01__P0__once" / "trace.json.gz"
    trace = json.loads(gzip.decompress(path.read_bytes()))
    trace["receipts"] = [r for r in trace["receipts"] if r["tool"] != "apply_plan"]
    path.write_bytes(gzip.compress(json.dumps(trace).encode(), mtime=0))
    row = suite_metrics(load_results(out))["episodes"][0]
    assert row["status"] == "integrity_failed" and row["success"] is False
    assert "trace sha256 differs from its record" in row["failure_reasons"]


# ---------------------------------------------------------------------------------- D10


@pytest.fixture(scope="module")
def pantry(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], dict[str, Any]]:
    db = Database(tmp_path_factory.mktemp("pantry") / "p.sqlite3")
    result = run_case(db, "pantry_dev01")
    trace = build_trace(db, result.episode_id, policy_id=result.report.policy_id)
    return trace, public_summary(result.report)


def test_a_verify_decision_reporting_success_cites_a_successful_check(
    pantry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    trace, outcome = pantry
    found = pantry_metrics(trace, outcome)
    assert found is not None and found["receipt_integrity_ok"], found
    forged = copy.deepcopy(trace)
    verify = next(d for d in forged["decisions"] if d["kind"] == "verify")
    for call in forged["tool_calls"]:
        if call["call_id"] in verify["tool_call_refs"]:
            call["envelope_status"] = "unavailable"
    found = pantry_metrics(forged, outcome)
    assert found is not None and any(
        "cites no successful status check" in p for p in found["receipt_integrity_problems"]
    )


def test_a_status_observation_from_another_actors_check_is_linked(
    pantry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    trace, outcome = pantry
    staff = copy.deepcopy(trace)
    for call in staff["tool_calls"]:
        if call["tool"] == "query_status":
            call["actor_role"] = "staff"
    found = pantry_metrics(staff, outcome)
    assert found is not None
    assert not [p for p in found["receipt_integrity_problems"] if "status observation" in p]


def test_churn_reads_a_resource_level_failure_as_the_activity_using_it(
    dev01_p0: dict[str, Any],
) -> None:
    """A failed check that names only a resource (an unavailable projector) marks the activity
    whose kept assignment uses it as already invalid (re-audit R2)."""
    trace = copy.deepcopy(dev01_p0)
    for evaluation in trace["evaluations"].values():
        keep = next(
            c
            for c in evaluation["candidates"]
            if c["candidate_id"] == evaluation["keep_candidate_id"]
        )
        for check in keep["checks"]:
            if check["status"] == "failed":
                check["entity_ids"] = ["projector"]  # the resource only
    assert plan_churn(trace)["previously_valid_altered"] == 1  # demonstrations is not churn


def test_unmeasured_recovery_episodes_make_the_median_unbounded() -> None:
    def row(status: str, recovered: bool | None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": status,
            "outcome_class": "goal",
            "negative_control": False,
            "success": bool(recovered),
            "case_id": "C01",
            "requires_recovery": True,
        }
        if status == "completed":
            out |= {
                "plan_churn": {"total": 0},
                "recovery": {"recovered": True, "delay_minutes": 5, "horizon_minutes": 80},
            }
        return out

    rec = policy_aggregate([row("completed", True), row("timeout", None), row("crashed", None)])
    rec = rec["recovery"]
    assert rec["median_unbounded"] is True and rec["median_minutes"] is None
    assert rec["unrecovered_unmeasured"] == 2
    all_ok = policy_aggregate([row("completed", True)] * 3)["recovery"]
    assert all_ok["median_minutes"] == 5 and all_ok["median_unbounded"] is False
