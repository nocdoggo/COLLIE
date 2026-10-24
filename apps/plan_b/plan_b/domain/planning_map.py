"""Projections of runtime records back to planning 0.2.0 artifacts.

Planning objects forbid additional properties, so each projection emits exactly the planning
fields (contract section 1): ``artifact_type`` and ``schema_version`` are added, times are UTC
ISO strings ending in ``Z``, ``required_hold_ids`` are the bound hold ids, ``not_applicable``
checks are omitted and ``unsupported`` checks become ``passed: false``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from plan_b.domain.models import (
    PLANNING_SCHEMA_VERSION,
    ActionReceipt,
    Assignment,
    CandidateResult,
    ObservationRecord,
    TimeWindow,
)
from plan_b.domain.timeutil import fmt_ts


def _unique(values: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(values))


def _window(window: TimeWindow) -> dict[str, str]:
    return {"start": fmt_ts(window.start), "end": fmt_ts(window.end)}


def _assignment(assignment: Assignment) -> dict[str, Any]:
    return {
        "activity_id": assignment.activity_id,
        "start": fmt_ts(assignment.start),
        "end": fmt_ts(assignment.end),
        "resource_ids": _unique(assignment.resource_ids),
    }


def to_planning_candidate(
    c: CandidateResult, *, event_id: str, revision: int, goal_version: int
) -> dict[str, Any]:
    """``candidate_plan``: ``plan_id`` = candidate id, report ref = report id."""
    return {
        "artifact_type": "candidate_plan",
        "schema_version": PLANNING_SCHEMA_VERSION,
        "plan_id": c.candidate_id,
        "event_id": event_id,
        "based_on_revision": revision,
        "goal_version": goal_version,
        "assignments": [_assignment(a) for a in c.assignments],
        "changed_activity_ids": _unique(c.changed_activity_ids),
        "required_hold_ids": _unique(
            [h.bound_hold_id for h in c.required_holds if h.bound_hold_id is not None]
        ),
        "incremental_committed_cents": c.incremental_committed_cents,
        "assumptions": _unique([a.text for a in c.assumptions]),
        "constraint_status": c.constraint_status,
        "constraint_report_ref": c.report_id,
        "rationale": c.rationale,
    }


def to_planning_report(
    c: CandidateResult,
    *,
    event_id: str,
    revision: int,
    goal_version: int,
    checked_at: datetime,
) -> dict[str, Any]:
    """``constraint_report`` for one candidate; ``not_applicable`` checks are omitted."""
    checks: list[dict[str, Any]] = []
    for check in c.checks:
        if check.status == "not_applicable":
            continue
        detail = check.detail
        if check.status == "unsupported":
            detail = f"Unsupported, not checked: {detail}"
        checks.append(
            {
                "constraint_id": check.constraint_id,
                "passed": check.status == "passed",
                "detail": detail,
            }
        )
    if not checks:
        raise ValueError(f"candidate {c.candidate_id} has no applicable check to project")
    if not c.execution_preconditions:
        raise ValueError(f"candidate {c.candidate_id} has no execution preconditions")
    return {
        "artifact_type": "constraint_report",
        "schema_version": PLANNING_SCHEMA_VERSION,
        "report_id": c.report_id,
        "event_id": event_id,
        "candidate_plan_id": c.candidate_id,
        "state_revision": revision,
        "goal_version": goal_version,
        "checked_at": fmt_ts(checked_at),
        "result": c.constraint_status,
        "checks": checks,
        "assumptions": [a.text for a in c.assumptions],
        "execution_preconditions": list(c.execution_preconditions),
    }


def to_planning_receipt(r: ActionReceipt) -> dict[str, Any]:
    """``action_receipt`` with the planning fields only (runtime extras are dropped)."""
    return {
        "artifact_type": "action_receipt",
        "schema_version": PLANNING_SCHEMA_VERSION,
        "receipt_id": r.receipt_id,
        "event_id": r.event_id,
        "tool": r.tool,
        "request_idempotency_key": r.request_idempotency_key,
        "grant_id": r.grant_id,
        "status": r.status,
        "revision_before": r.revision_before,
        "revision_after": r.revision_after,
        "executed_at": fmt_ts(r.executed_at),
        "simulation": r.simulation,
        "state_changes": [change.model_dump(mode="json") for change in r.state_changes],
        "committed_delta_cents": r.committed_delta_cents,
        "reserved_delta_cents": r.reserved_delta_cents,
        "related_plan_id": r.related_plan_id,
        "constraint_report_ref": r.constraint_report_ref,
        "error_code": r.error_code,
        "actor_id": r.actor_id,
        "request_digest": r.request_digest,
    }


def to_planning_observation_record(
    rec: ObservationRecord, *, revision_before: int, ingested_at: datetime
) -> dict[str, Any]:
    """``observation_record``: the planning Observation plus revision and ingestion time."""
    obs = rec.observation
    return {
        "artifact_type": "observation_record",
        "schema_version": PLANNING_SCHEMA_VERSION,
        "event_id": obs.event_id,
        "revision_before": revision_before,
        "revision_after": rec.revision_after,
        "ingested_at": fmt_ts(ingested_at),
        "observation": {
            "observation_id": obs.observation_id,
            "event_id": obs.event_id,
            "entity_id": obs.entity_id,
            "kind": obs.kind,
            "source_id": obs.source_id,
            "source_record_id": obs.source_record_id,
            "correlation_group": obs.correlation_group,
            "observed_at": fmt_ts(obs.observed_at),
            "received_at": fmt_ts(obs.received_at),
            "valid_window": _window(obs.valid_window),
            "authority_scope": obs.authority_scope,
            "text": obs.text,
            "supersedes": _unique(obs.supersedes),
        },
    }
