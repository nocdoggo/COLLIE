"""Metric definitions of ``plan_b.evaluation.metrics`` (``08_evaluation.md``, "Outcomes and
definitions" and the pantry metrics table), on small synthetic traces and on a real executed
pantry trace (P0 through the real runner and executor)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from plan_b.evaluation.export_trace import build_trace
from plan_b.evaluation.metrics import (
    class_success,
    extraction_labels,
    invalid_attempts,
    pantry_metrics,
    plan_churn,
    preparation_cost,
    recovery,
    verification_effort,
)
from plan_b.evaluation.scoring import public_summary
from plan_b.scenarios.runner import run_case
from plan_b.store.database import Database

AGENT = "coordinator_agent"


def call(
    tool: str, status: str = "succeeded", code: str | None = None, **args: Any
) -> dict[str, Any]:
    return {
        "tool": tool,
        "actor_id": "agent_demo",
        "actor_role": AGENT,
        "envelope_status": status,
        "error_code": code,
        "request": {"arguments": args},
        "requested_at": "2026-11-05T21:40:00Z",
        "completed_at": "2026-11-05T21:42:00Z",
    }


def apply_receipt(at: str, status: str = "applied") -> dict[str, Any]:
    return {
        "receipt_id": f"rcpt_{at}",
        "tool": "apply_plan",
        "status": status,
        "actor_role": AGENT,
        "actor_id": "agent_demo",
        "executed_at": at,
        "revision_after": 9,
        "committed_delta_cents": 3500,
    }


def trace_of(**parts: Any) -> dict[str, Any]:
    final = {
        "clock": "2026-11-05T23:00:00Z",
        "goal": {"hard_end": "2026-11-05T23:00:00Z"},
        "observations": [
            {
                "channel": "fixture_initial",
                "observation": {
                    "observation_id": "obs_notice_01",
                    "kind": "notice",
                    "source_record_id": "msg_a",
                    "received_at": "2026-11-05T21:40:00Z",
                    "entity_id": "projector",
                },
            },
            {
                "channel": "scenario_delivery",
                "observation": {
                    "observation_id": "obs_0002",
                    "kind": "notice",
                    "source_record_id": "msg_b",
                    "received_at": "2026-11-05T21:50:00Z",
                    "entity_id": "projector",
                },
            },
        ],
        "holds": [],
        "budget": {"reserved_cents": 0},
    } | parts.pop("final", {})
    return {"tool_calls": [], "receipts": [], "decisions": [], "final_state": final} | parts


def test_invalid_attempts_and_verification_effort_count_the_coordinators_calls() -> None:
    trace = trace_of(
        tool_calls=[
            call("query_status", entity_id="projector", fact="delivery_eta"),
            call("query_status", "unavailable", entity_id="projector", fact="delivery_eta"),
            call("query_status", entity_id="backup_projector", fact="availability"),
            call("apply_plan", "rejected", "REVISION_CONFLICT"),
            call("hold_resource", "rejected", "GRANT_REQUIRED"),
            call("query_status", entity_id="x", fact="y") | {"actor_role": "participant"},
        ]
    )
    assert invalid_attempts(trace) == {
        "count": 2,
        "by_code": {"GRANT_REQUIRED": 1, "REVISION_CONFLICT": 1},
        "by_tool": {"apply_plan": 1, "hold_resource": 1},
    }
    # A retry of the same source is a repeated check, never a new source.
    assert verification_effort(trace) == {
        "status_checks": 3,
        "distinct_sources": 2,
        "repeated_checks": 1,
        "failed_checks": 1,
        "simulated_minutes": 6,
    }


def test_recovery_delay_runs_from_the_actionable_update_and_unrecovered_carries_the_horizon() -> (
    None
):
    case = {"requires_recovery": True, "actionable_record_ids": ["msg_b"]}
    late = trace_of(
        receipts=[apply_receipt("2026-11-05T21:45:00Z"), apply_receipt("2026-11-05T22:05:00Z")]
    )
    # The first applied plan change at or after the update (21:50) is the 22:05 one.
    assert recovery(late, case, True) | {"update_at": None} == {
        "required": True,
        "update_at": None,
        "recovered": True,
        "delay_minutes": 15,
        "horizon_minutes": 70,
        "note": None,
    }
    unrecovered = recovery(trace_of(), case, False)
    assert unrecovered is not None
    assert (unrecovered["recovered"], unrecovered["delay_minutes"]) == (False, 70)
    # A plan change in an episode whose outcome failed is not a valid recovery.
    failed = recovery(late, case, False)
    assert failed is not None and (failed["recovered"], failed["delay_minutes"]) == (False, 70)
    # Without designated records the first notice is the update.
    first = recovery(late, {"requires_recovery": True}, True)
    assert first is not None and first["delay_minutes"] == 5
    assert recovery(late, {"requires_recovery": False}, True) is None


def test_churn_and_preparation_cost_come_from_receipts_and_holds() -> None:
    trace = trace_of(
        receipts=[
            apply_receipt("2026-11-05T21:45:00Z"),
            apply_receipt("2026-11-05T21:46:00Z", "rejected"),
        ],
        final={
            "holds": [
                {
                    "actor_id": "agent_demo",
                    "created_at": "2026-11-05T21:40:00Z",
                    "terminal_at": "2026-11-05T21:50:00Z",
                    "effective_status": "expired",
                    "hold_fee_cents": 200,
                },
                {
                    "actor_id": "agent_demo",
                    "created_at": "2026-11-05T22:50:00Z",
                    "terminal_at": None,
                    "effective_status": "active",
                    "hold_fee_cents": 0,
                },
            ],
            "budget": {"reserved_cents": 1000},
        },
    )
    assert plan_churn(trace) == {
        "committed_revisions": 1,
        "altered_assignments": 0,
        "previously_valid_altered": 0,
        "total": 1,
    }
    prep = preparation_cost(trace)
    assert (prep["holds"], prep["hold_minutes"], prep["hold_fee_cents"]) == (2, 20, 200)
    assert (prep["expired_holds"], prep["unreleased_holds"], prep["reserved_cents_at_end"]) == (
        1,
        1,
        1000,
    )


def _reading(oid: str, **fields: Any) -> dict[str, Any]:
    return {
        "observation_id": oid,
        "change_spec": {"change_kind": fields.pop("kind", "delay")},
        "subject_resource_id": fields.pop("subject", "projector"),
        "claimed_eta": fields.pop("eta", "2026-11-05T22:25:00Z"),
        "standing": fields.pop("standing", "claim"),
        "failure": fields.pop("failure", None),
    }


def test_extraction_labels_compare_the_recorded_reading_with_the_annotation() -> None:
    annotation = {
        "source_record_id": "msg_a",
        "resource_id": "projector",
        "effective_time": "2026-11-05T17:25:00-05:00",
        "claimed_change": "delay",
    }
    case = {"annotations": [annotation, annotation | {"source_record_id": "msg_b"}]}

    def labels(*readings: dict[str, Any]) -> list[str]:
        trace = trace_of(
            decisions=[{"kind": "verify", "details": {"interpretations": list(readings)}}]
        )
        found = extraction_labels(trace, case)
        assert found is not None
        return [entry["label"] for entry in found]

    assert labels(_reading("obs_notice_01")) == ["correct", "not_recorded"]
    assert labels(
        _reading("obs_notice_01", eta="2026-11-05T22:40:00Z"),
        _reading("obs_0002", kind="availability"),
    ) == [
        "incorrect",
        "incorrect",
    ]
    assert labels(_reading("obs_notice_01", kind="unresolved", standing="unresolved")) == [
        "abstained",
        "not_recorded",
    ]
    assert labels(_reading("obs_notice_01", failure="malformed_output")) == [
        "malformed",
        "not_recorded",
    ]
    assert labels(_reading("obs_notice_01", failure="unknown_entity")) == [
        "rejected",
        "not_recorded",
    ]
    quiet = {"annotations": [annotation | {"claimed_change": "no_change"}]}
    trace = trace_of(
        decisions=[
            {
                "kind": "unresolved",
                "details": {"interpretations": [_reading("obs_notice_01", kind="unresolved")]},
            }
        ]
    )
    assert [e["label"] for e in extraction_labels(trace, quiet) or []] == ["correct"]
    assert extraction_labels(trace, {"annotations": []}) is None


def test_infeasibility_needs_a_named_blocking_constraint_and_no_completed_goal() -> None:
    case = {"outcome_class": "infeasible"}
    named = {"kind": "infeasible", "summary": "x", "details": {"blocking_constraints": ["budget"]}}
    vague = {"kind": "infeasible", "summary": "cannot do it", "details": {}}
    outcome = {"goal_complete": False, "violations": []}
    assert class_success(case, outcome, trace_of(decisions=[named]), None) == (
        True,
        [],
        "policy",
    )
    ok, why, _ = class_success(case, outcome, trace_of(decisions=[vague]), None)
    assert not ok and why == ["no infeasibility decision names a blocking constraint"]
    # A constraint named only in the summary text is not a structured explanation.
    textual = vague | {"summary": "Blocking: activity_windows, dependencies"}
    ok, why, _ = class_success(case, outcome, trace_of(decisions=[textual]), None)
    assert not ok
    ok, why, _ = class_success(
        case, outcome | {"violations": ["budget: over"]}, trace_of(decisions=[named]), None
    )
    assert not ok and why == ["1 executed violation(s)"]


@pytest.fixture(scope="module")
def pantry_trace(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], dict[str, Any]]:
    db = Database(tmp_path_factory.mktemp("pantry") / "p.sqlite3")
    result = run_case(db, "pantry_dev01")
    trace = build_trace(db, result.episode_id, policy_id=result.report.policy_id)
    return trace, public_summary(result.report)


def test_pantry_metrics_on_the_executed_canonical_trace(
    pantry_trace: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    trace, outcome = pantry_trace
    metrics = pantry_metrics(trace, outcome)
    assert metrics is not None
    assert metrics["receipt_integrity_ok"], metrics["receipt_integrity_problems"]
    assert (
        metrics["duplicate_or_unauthorized_credits"] == 0 and metrics["conservation_failures"] == 0
    )
    assert metrics["targets"] == [
        {
            "target_id": "kits_40",
            "original_target": 40,
            "current_target": 40,
            "on_time": 40,
            "late": 0,
            "distributed": 40,
            "service_deficit": 0,
            "supply_shortfall": 0,
            "attained": True,
        }
    ]
    pools = {p["resource_id"]: p for p in metrics["pools"]}
    assert (pools["pantry_stock"]["opening"], pools["pantry_stock"]["received"]) == (24, 16)
    assert pools["partner_stock"]["transferred_out"] == 16
    assert class_success(
        {"outcome_class": "target", "target_quantity": 40}, outcome, trace, metrics
    ) == (True, [], None)


def test_pantry_integrity_flags_agent_attestation_double_credit_and_bad_movements(
    pantry_trace: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    trace, outcome = pantry_trace
    forged = copy.deepcopy(trace)
    receipt_id = forged["final_state"]["stock"]["receipts"][0]["receipt_id"]
    for r in forged["receipts"]:
        if r["receipt_id"] == receipt_id:
            r["actor_role"] = AGENT
    found = pantry_metrics(forged, outcome)
    assert found is not None and found["duplicate_or_unauthorized_credits"] == 1
    assert "attested by the coordinator" in found["credit_findings"][0]

    doubled = copy.deepcopy(trace)
    stock = doubled["final_state"]["stock"]
    stock["receipts"].append(stock["receipts"][0] | {"stock_receipt_id": "srec_dup"})
    found = pantry_metrics(doubled, outcome)
    assert found is not None
    assert any("credited 2 times" in f for f in found["credit_findings"])
    assert any("received for a 16-unit hold" in f for f in found["credit_findings"])

    moved = copy.deepcopy(trace)
    for m in moved["final_state"]["stock"]["movements"]:
        if m["kind"] == "receipt":
            m["delta"] = 15
    found = pantry_metrics(moved, outcome)
    assert found is not None and not found["receipt_integrity_ok"]
    assert any("receipt movement" in p for p in found["receipt_integrity_problems"])
    # Lowering the target to claim success is caught.
    lowered = copy.deepcopy(trace)
    lowered["final_state"]["stock"]["service"][0]["target_quantity"] = 30
    metrics = pantry_metrics(lowered, outcome)
    ok, why, _ = class_success({"outcome_class": "target"}, outcome, lowered, metrics)
    assert not ok and "kits_40: target changed from 40" in why
