"""Planning 0.2.0 projections of runtime records validate against the planning schema."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from plan_b.domain.adapters.campus import CampusAdapter
from plan_b.domain.fixtures import load_public_scenario
from plan_b.domain.models import (
    AccessibilityRequirement,
    ActionReceipt,
    ActorContext,
    CandidateResult,
    EvaluationRequest,
    EvaluationResult,
    ObservationRecord,
    PlanningSnapshot,
    StateChange,
    StatusFacts,
)
from plan_b.domain.planning_map import (
    to_planning_candidate,
    to_planning_observation_record,
    to_planning_receipt,
    to_planning_report,
)
from plan_b.domain.projection import initial_snapshot

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "PEEAI_plan" / "schemas" / "planning.schema.json"
)
SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
SCENARIO = load_public_scenario()
TZ = ZoneInfo("America/New_York")
ADAPTER = CampusAdapter()
DIGEST = "eb37a6040c1590eb8216265918b0f0264d68754bf26069c0d2c1eec03d22a123"

FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=ValueError)
def _utc_date_time(value: object) -> bool:
    """RFC 3339 date-time with an explicit offset (the default checker needs an extra package)."""
    if not isinstance(value, str):
        return True
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.tzinfo is not None and "T" in value


def at(hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(2026, 11, 5, hour, minute, tzinfo=TZ).astimezone(UTC)


def validate(artifact: dict[str, Any], definition: str) -> None:
    """Validate against one planning definition and against the root ``oneOf``."""
    scoped = {
        "$schema": SCHEMA["$schema"],
        "$defs": SCHEMA["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    Draft202012Validator(scoped, format_checker=FORMATS).validate(artifact)
    Draft202012Validator(SCHEMA, format_checker=FORMATS).validate(artifact)


def times_in(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if (key in ("start", "end") or key.endswith("_at")) and isinstance(item, str):
                found.append(item)
            found.extend(times_in(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(times_in(item))
    return found


def coordinator() -> ActorContext:
    grant = next(g for g in SCENARIO.authority_grants if g.grant_id == "grant_coordinator_demo")
    return ActorContext(
        principal_id="agent_demo",
        role="coordinator_agent",
        grant=grant,
        grant_version=1,
        grant_valid=True,
        committed_used_cents=0,
        reserved_used_cents=0,
    )


def eta_snapshot() -> PlanningSnapshot:
    snap = initial_snapshot(SCENARIO)
    resources = tuple(
        r.model_copy(
            update={
                "status_basis": "status_observation",
                "status_observation_id": "obs_status_02",
                "status_observed_at": at("16:40"),
                "reported_eta": at("17:25"),
            }
        )
        if r.definition.resource_id == "projector"
        else r
        for r in snap.resources
    )
    return snap.model_copy(update={"resources": resources, "revision": 4, "clock": at("16:42")})


def evaluation(snap: PlanningSnapshot) -> EvaluationResult:
    return ADAPTER.evaluate(snap, coordinator(), EvaluationRequest(), "eval_0001")


def by_label(result: EvaluationResult, label: str) -> CandidateResult:
    return next(c for c in result.candidates if c.label == label)


def project(c: CandidateResult, result: EvaluationResult) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = to_planning_candidate(
        c, event_id=result.event_id, revision=result.revision, goal_version=result.goal_version
    )
    report = to_planning_report(
        c,
        event_id=result.event_id,
        revision=result.revision,
        goal_version=result.goal_version,
        checked_at=result.evaluated_at,
    )
    return candidate, report


def test_feasible_candidate_and_report_validate() -> None:
    result = evaluation(eta_snapshot())
    swap = by_label(result, "Swap demonstrations and skills exchange")
    candidate, report = project(swap, result)
    validate(candidate, "CandidatePlan")
    validate(report, "ConstraintReport")
    assert candidate["plan_id"] == swap.candidate_id
    assert candidate["constraint_report_ref"] == swap.report_id == report["report_id"]
    assert report["candidate_plan_id"] == swap.candidate_id
    assert candidate["based_on_revision"] == 4 and report["state_revision"] == 4
    assert candidate["constraint_status"] == report["result"] == "feasible_under_assumptions"
    assert candidate["changed_activity_ids"] == ["demonstrations", "skills_exchange"]
    assert candidate["required_hold_ids"] == []
    assert len(candidate["assignments"]) == 5
    assert all(check["passed"] for check in report["checks"])
    # not_applicable checks are omitted, never emitted as a successful placeholder.
    projected = {check["constraint_id"] for check in report["checks"]}
    omitted = {c.constraint_id for c in swap.checks if c.status == "not_applicable"}
    assert omitted == {"substitute_compatibility", "accessibility", "commitment_cutoff"}
    assert projected.isdisjoint(omitted)
    assert len(projected) == len(swap.checks) - len(omitted)
    assert report["execution_preconditions"] == list(swap.execution_preconditions)
    for text in times_in(candidate) + times_in(report):
        assert text.endswith("Z"), text
    assert report["checked_at"] == "2026-11-05T21:42:00Z"


def test_infeasible_and_unknown_candidates_validate() -> None:
    result = evaluation(eta_snapshot())
    keep = by_label(result, "Keep the current plan")
    candidate, report = project(keep, result)
    validate(candidate, "CandidatePlan")
    validate(report, "ConstraintReport")
    assert candidate["constraint_status"] == "infeasible"
    failed = [check["constraint_id"] for check in report["checks"] if not check["passed"]]
    assert failed == ["arrival_assumptions"]

    snap = eta_snapshot()
    requirement = AccessibilityRequirement(
        requirement_id="acc_captions",
        kind="live_captioning",
        activity_ids=("demonstrations",),
        detail="Live captions during demonstrations",
    )
    goal = snap.goal.model_copy(update={"accessibility_requirements": (requirement,)})
    unknown_result = evaluation(snap.model_copy(update={"goal": goal}))
    swap = by_label(unknown_result, "Swap demonstrations and skills exchange")
    assert swap.constraint_status == "unknown"
    candidate, report = project(swap, unknown_result)
    validate(candidate, "CandidatePlan")
    validate(report, "ConstraintReport")
    accessibility = next(c for c in report["checks"] if c["constraint_id"] == "accessibility")
    assert accessibility["passed"] is False
    assert accessibility["detail"].startswith("Unsupported")


def test_bound_hold_ids_are_projected() -> None:
    result = evaluation(eta_snapshot())
    substitute = by_label(result, "Use backup_projector instead of projector for demonstrations")
    assert substitute.required_holds and substitute.required_holds[0].bound_hold_id is None
    candidate, _ = project(substitute, result)
    assert candidate["required_hold_ids"] == []
    bound = substitute.model_copy(
        update={
            "required_holds": (
                substitute.required_holds[0].model_copy(update={"bound_hold_id": "hold_0001"}),
            )
        }
    )
    candidate, _ = project(bound, result)
    validate(candidate, "CandidatePlan")
    assert candidate["required_hold_ids"] == ["hold_0001"]
    assert candidate["incremental_committed_cents"] == 3500


def _receipt(**update: Any) -> ActionReceipt:
    fields: dict[str, Any] = {
        "runtime_version": "1.0.0",
        "receipt_id": "rcpt_0005",
        "episode_id": "ep_0001",
        "event_id": "e_showcase_01",
        "tool": "apply_plan",
        "request_idempotency_key": "demo_commit_swap_001",
        "request_digest": DIGEST,
        "grant_id": "grant_coordinator_demo",
        "grant_version": 1,
        "actor_id": "agent_demo",
        "actor_role": "coordinator_agent",
        "status": "applied",
        "revision_before": 4,
        "revision_after": 5,
        "requested_at": at("16:42"),
        "executed_at": at("16:43"),
        "simulation": True,
        "state_changes": (
            StateChange(
                entity_id="demonstrations",
                field="scheduled_window",
                before={"start": at("17:10"), "end": at("17:30")},
                after={"start": at("17:30"), "end": at("17:50")},
            ),
        ),
        "committed_delta_cents": 0,
        "reserved_delta_cents": 0,
        "related_plan_id": "cand_0001_dc26f35f",
        "constraint_report_ref": "rpt_0001_dc26f35f",
        "error_code": None,
        "error_message": None,
        "summary": "Applied the swap of demonstrations and skills exchange.",
    }
    fields.update(update)
    return ActionReceipt(**fields)


def test_applied_receipt_validates() -> None:
    receipt = _receipt()
    projected = to_planning_receipt(receipt)
    validate(projected, "ActionReceipt")
    assert projected["executed_at"] == "2026-11-05T21:43:00Z"
    assert projected["state_changes"][0]["after"] == {
        "start": "2026-11-05T22:30:00Z",
        "end": "2026-11-05T22:50:00Z",
    }
    for runtime_only in ("episode_id", "grant_version", "actor_role", "requested_at", "summary"):
        assert runtime_only not in projected


def test_rejected_receipt_validates() -> None:
    receipt = _receipt(
        status="rejected",
        revision_after=4,
        state_changes=(),
        error_code="CANDIDATE_STALE",
        error_message="The candidate was evaluated at revision 3.",
        summary="Rejected: stale candidate.",
    )
    projected = to_planning_receipt(receipt)
    validate(projected, "ActionReceipt")
    assert projected["status"] == "rejected"
    assert projected["error_code"] == "CANDIDATE_STALE"
    assert projected["state_changes"] == []
    assert projected["revision_before"] == projected["revision_after"]


def test_observation_records_validate() -> None:
    notice = ObservationRecord(
        observation=SCENARIO.visible_observations[0],
        channel="fixture_initial",
        submitted_by=None,
        revision_after=3,
    )
    projected = to_planning_observation_record(notice, revision_before=3, ingested_at=at("16:40"))
    validate(projected, "ObservationRecord")
    assert projected["observation"]["observed_at"] == "2026-11-05T21:39:00Z"
    assert projected["observation"]["valid_window"]["end"] == "2026-11-05T23:00:00Z"

    status = notice.observation.model_copy(
        update={
            "observation_id": "obs_status_02",
            "kind": "status",
            "source_id": "supplier_status_adapter",
            "source_record_id": "order_P17_revision_4",
            "observed_at": at("16:40"),
            "received_at": at("16:42"),
            "authority_scope": "resource_status",
            "text": "Order P17 reports a delayed projector delivery with estimated arrival 17:25.",
        }
    )
    record = ObservationRecord(
        observation=status,
        channel="status_tool",
        submitted_by="agent_demo",
        revision_after=4,
        structured=StatusFacts(
            fact="delivery_eta",
            status_code="delayed",
            domain_status="expected",
            reported_eta=at("17:25"),
        ),
    )
    projected = to_planning_observation_record(record, revision_before=3, ingested_at=at("16:42"))
    validate(projected, "ObservationRecord")
    assert (projected["revision_before"], projected["revision_after"]) == (3, 4)
    assert "channel" not in projected and "structured" not in projected
    for text in times_in(projected):
        assert text.endswith("Z"), text


def test_schema_rejects_runtime_extras() -> None:
    """The planning schema really is strict, so the checks above are meaningful."""
    projected = to_planning_receipt(_receipt())
    projected["episode_id"] = "ep_0001"
    with pytest.raises(ValidationError, match="Additional properties"):
        validate(projected, "ActionReceipt")
    for bad_time in ("16:43", "2026-11-05T21:43:00"):
        projected = to_planning_receipt(_receipt())
        projected["executed_at"] = bad_time
        with pytest.raises(ValidationError, match="date-time"):
            validate(projected, "ActionReceipt")


def test_accessibility_without_a_subject_is_omitted_from_the_report() -> None:
    """A requirement no remaining activity is subject to is never projected as passed."""
    snap = eta_snapshot()
    requirement = AccessibilityRequirement(
        requirement_id="acc_step_free",
        kind="venue_capability",
        activity_ids=("setup",),
        capability="step_free_access",
        detail="Step-free access",
    )
    activities = tuple(
        v.model_copy(update={"lifecycle": "completed", "readiness": None})
        if v.definition.activity_id == "setup"
        else v
        for v in snap.activities
    )
    goal = snap.goal.model_copy(update={"accessibility_requirements": (requirement,)})
    result = evaluation(snap.model_copy(update={"goal": goal, "activities": activities}))
    swap = by_label(result, "Swap demonstrations and skills exchange")
    _, report = project(swap, result)
    validate(report, "ConstraintReport")
    assert "accessibility" not in {check["constraint_id"] for check in report["checks"]}
