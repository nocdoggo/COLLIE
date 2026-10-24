"""Row-level helpers: every function takes an open connection inside a transaction."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from plan_b.domain.models import (
    ActionReceipt,
    ActivityDef,
    ActivityLifecycleEvent,
    AttemptView,
    AuthorityGrant,
    CheckInView,
    CommitmentView,
    DistributionView,
    EvaluationResult,
    EventGoal,
    ExpectedShipment,
    HoldView,
    Observation,
    ObservationRecord,
    PlanView,
    PolicyDecision,
    PublicScenario,
    ResourceDef,
    StatusCheckView,
    StatusFacts,
    StockAllocationView,
    StockMovementView,
    StockReceiptView,
    TimeWindow,
    ToolCallRecord,
    TransitionView,
)
from plan_b.domain.timeutil import fmt_ts, parse_ts


@dataclass(frozen=True)
class EpisodeRow:
    episode_id: str
    scenario_id: str
    profile_id: str
    event_id: str
    status: str
    clock: datetime
    revision: int
    goal_version: int
    plan_version: int
    public_fixture_sha256: str


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def get_episode(conn: sqlite3.Connection, episode_id: str) -> EpisodeRow:
    row = conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
    if row is None:
        raise KeyError(f"episode {episode_id} not found")
    return EpisodeRow(
        episode_id=row["episode_id"],
        scenario_id=row["scenario_id"],
        profile_id=row["profile_id"],
        event_id=row["event_id"],
        status=row["status"],
        clock=parse_ts(row["clock"]),
        revision=row["revision"],
        goal_version=row["goal_version"],
        plan_version=row["plan_version"],
        public_fixture_sha256=row["public_fixture_sha256"],
    )


def current_episode_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT episode_id FROM episodes WHERE status = 'active' "
        "ORDER BY created_wall DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return row["episode_id"] if row else None


def next_seq(conn: sqlite3.Connection, episode_id: str, name: str) -> int:
    row = conn.execute(
        "SELECT counters_json FROM episodes WHERE episode_id = ?", (episode_id,)
    ).fetchone()
    counters = json.loads(row["counters_json"])
    value = int(counters.get(name, 0)) + 1
    counters[name] = value
    conn.execute(
        "UPDATE episodes SET counters_json = ? WHERE episode_id = ?",
        (dumps(counters), episode_id),
    )
    return value


def get_flag(conn: sqlite3.Connection, episode_id: str, name: str) -> bool:
    row = conn.execute(
        "SELECT counters_json FROM episodes WHERE episode_id = ?", (episode_id,)
    ).fetchone()
    return bool(json.loads(row["counters_json"]).get(f"flag:{name}", False))


def set_flag(conn: sqlite3.Connection, episode_id: str, name: str) -> None:
    row = conn.execute(
        "SELECT counters_json FROM episodes WHERE episode_id = ?", (episode_id,)
    ).fetchone()
    counters = json.loads(row["counters_json"])
    counters[f"flag:{name}"] = True
    conn.execute(
        "UPDATE episodes SET counters_json = ? WHERE episode_id = ?",
        (dumps(counters), episode_id),
    )


def set_clock(conn: sqlite3.Connection, episode_id: str, at: datetime) -> None:
    conn.execute("UPDATE episodes SET clock = ? WHERE episode_id = ?", (fmt_ts(at), episode_id))


def bump_revision(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    at: datetime,
    cause_kind: str,
    cause_ref: str | None,
    summary: str,
) -> int:
    """Advance the revision by exactly one (compare-and-swap inside the open transaction)."""
    ep = get_episode(conn, episode_id)
    new_revision = ep.revision + 1
    cur = conn.execute(
        "UPDATE episodes SET revision = ? WHERE episode_id = ? AND revision = ?",
        (new_revision, episode_id, ep.revision),
    )
    if cur.rowcount != 1:
        raise RuntimeError("revision compare-and-swap failed inside a write transaction")
    conn.execute(
        "INSERT INTO state_transitions (episode_id, revision, at, cause_kind, cause_ref, summary)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (episode_id, new_revision, fmt_ts(at), cause_kind, cause_ref, summary),
    )
    return new_revision


# ---------------------------------------------------------------------------
# Scenario configuration
# ---------------------------------------------------------------------------


@lru_cache(maxsize=64)
def _parse_scenario(text: str) -> PublicScenario:
    return PublicScenario.model_validate_json(text)


def scenario(conn: sqlite3.Connection, episode_id: str) -> PublicScenario:
    row = conn.execute(
        "SELECT public_json FROM scenario_config WHERE episode_id = ?", (episode_id,)
    ).fetchone()
    return _parse_scenario(row["public_json"])


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def goal(conn: sqlite3.Connection, episode_id: str, version: int | None = None) -> EventGoal:
    if version is None:
        version = get_episode(conn, episode_id).goal_version
    row = conn.execute(
        "SELECT body_json FROM goals WHERE episode_id = ? AND version = ?", (episode_id, version)
    ).fetchone()
    return EventGoal.model_validate_json(row["body_json"])


def goal_history(conn: sqlite3.Connection, episode_id: str) -> tuple[EventGoal, ...]:
    rows = conn.execute(
        "SELECT body_json FROM goals WHERE episode_id = ? ORDER BY version", (episode_id,)
    )
    return tuple(EventGoal.model_validate_json(r["body_json"]) for r in rows)


def activity_rows(
    conn: sqlite3.Connection, episode_id: str
) -> tuple[tuple[ActivityDef, ...], dict[str, str]]:
    rows = conn.execute(
        "SELECT definition_json, lifecycle FROM activities WHERE episode_id = ? ORDER BY rowid",
        (episode_id,),
    ).fetchall()
    defs = tuple(ActivityDef.model_validate_json(r["definition_json"]) for r in rows)
    lifecycles = {d.activity_id: r["lifecycle"] for d, r in zip(defs, rows, strict=True)}
    return defs, lifecycles


def activity_history(
    conn: sqlite3.Connection, episode_id: str
) -> tuple[ActivityLifecycleEvent, ...]:
    rows = conn.execute(
        "SELECT * FROM activity_events WHERE episode_id = ? ORDER BY seq", (episode_id,)
    )
    return tuple(
        ActivityLifecycleEvent(
            seq=r["seq"],
            activity_id=r["activity_id"],
            state=r["state"],
            at=parse_ts(r["at"]),
            revision=r["revision"],
            reasons=tuple(json.loads(r["reasons_json"])),
            evidence_refs=tuple(json.loads(r["evidence_json"])),
        )
        for r in rows
    )


def append_activity_event(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    activity_id: str,
    state: str,
    at: datetime,
    revision: int,
    reasons: tuple[str, ...] = (),
    evidence: tuple[str, ...] = (),
) -> None:
    seq = next_seq(conn, episode_id, "activity_event")
    conn.execute(
        "INSERT INTO activity_events (episode_id, seq, activity_id, state, at, revision,"
        " reasons_json, evidence_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            seq,
            activity_id,
            state,
            fmt_ts(at),
            revision,
            dumps(list(reasons)),
            dumps(list(evidence)),
        ),
    )
    conn.execute(
        "UPDATE activities SET lifecycle = ? WHERE episode_id = ? AND activity_id = ?",
        (state, episode_id, activity_id),
    )


def resource_rows(conn: sqlite3.Connection, episode_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM resources WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    ).fetchall()


def resource_def(row: sqlite3.Row) -> ResourceDef:
    return ResourceDef.model_validate_json(row["definition_json"])


def plan(conn: sqlite3.Connection, episode_id: str, version: int | None = None) -> PlanView:
    if version is None:
        version = get_episode(conn, episode_id).plan_version
    row = conn.execute(
        "SELECT * FROM plans WHERE episode_id = ? AND plan_version = ?", (episode_id, version)
    ).fetchone()
    return _plan_from_row(row)


def _plan_from_row(row: sqlite3.Row) -> PlanView:
    return PlanView.model_validate(
        {
            "plan_version": row["plan_version"],
            "assignments": json.loads(row["assignments_json"]),
            "applied_receipt_id": row["receipt_id"],
            "candidate_id": row["candidate_id"],
            "applied_at": row["applied_at"],
        }
    )


def plan_history(conn: sqlite3.Connection, episode_id: str) -> tuple[PlanView, ...]:
    rows = conn.execute(
        "SELECT * FROM plans WHERE episode_id = ? ORDER BY plan_version", (episode_id,)
    )
    return tuple(_plan_from_row(r) for r in rows)


def holds(conn: sqlite3.Connection, episode_id: str) -> tuple[HoldView, ...]:
    rows = conn.execute("SELECT * FROM holds WHERE episode_id = ? ORDER BY rowid", (episode_id,))
    out = []
    for r in rows:
        consumable = bool(r["consumable"])
        out.append(
            HoldView(
                hold_id=r["hold_id"],
                resource_id=r["resource_id"],
                activity_id=r["activity_id"],
                quantity=r["quantity"],
                window=TimeWindow(start=parse_ts(r["window_start"]), end=parse_ts(r["window_end"])),
                created_at=parse_ts(r["created_at"]),
                expires_at=parse_ts(r["expires_at"]),
                commitment_cutoff=parse_ts(r["commitment_cutoff"])
                if r["commitment_cutoff"]
                else None,
                reserved_cents=r["reserved_cents"],
                hold_fee_cents=r["hold_fee_cents"],
                status=r["status"],
                effective_status=r["status"],
                actor_id=r["actor_id"],
                grant_id=r["grant_id"],
                commitment_id=r["commitment_id"],
                terminal_at=parse_ts(r["terminal_at"]) if r["terminal_at"] else None,
                created_receipt_id=r["created_receipt_id"],
                terminal_receipt_id=r["terminal_receipt_id"],
                consumable=consumable,
                # A reusable resource's hold has no consumable remainder to show.
                remaining_quantity=r["remaining_quantity"] if consumable else None,
                purpose=r["purpose"],
                destination_resource_id=r["destination_resource_id"],
                service_target_id=r["service_target_id"],
            )
        )
    return tuple(out)


def commitments(conn: sqlite3.Connection, episode_id: str) -> tuple[CommitmentView, ...]:
    rows = conn.execute(
        "SELECT * FROM commitments WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    )
    return tuple(
        CommitmentView(
            commitment_id=r["commitment_id"],
            resource_id=r["resource_id"],
            activity_id=r["activity_id"],
            window=TimeWindow(start=parse_ts(r["window_start"]), end=parse_ts(r["window_end"])),
            committed_cents=r["committed_cents"],
            source_hold_id=r["source_hold_id"],
            plan_version=r["plan_version"],
            status=r["status"],
            created_at=parse_ts(r["created_at"]),
            receipt_id=r["receipt_id"],
            actor_id=r["actor_id"],
            grant_id=r["grant_id"],
        )
        for r in rows
    )


def checkins(conn: sqlite3.Connection, episode_id: str) -> tuple[CheckInView, ...]:
    rows = conn.execute("SELECT * FROM checkins WHERE episode_id = ? ORDER BY rowid", (episode_id,))
    return tuple(
        CheckInView(
            checkin_id=r["checkin_id"],
            principal_id=r["principal_id"],
            resource_id=r["resource_id"],
            at=parse_ts(r["at"]),
            available=TimeWindow(
                start=parse_ts(r["available_start"]), end=parse_ts(r["available_end"])
            ),
            observation_id=r["observation_id"],
            channel=r["channel"],
        )
        for r in rows
    )


def grant_rows(
    conn: sqlite3.Connection, episode_id: str, *, current_only: bool
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM grants WHERE episode_id = ?"
    if current_only:
        sql += " AND is_current = 1"
    sql += " ORDER BY grant_id, version"
    return conn.execute(sql, (episode_id,)).fetchall()


def current_grant(
    conn: sqlite3.Connection, episode_id: str, grant_id: str
) -> tuple[AuthorityGrant, int, bool] | None:
    row = conn.execute(
        "SELECT * FROM grants WHERE episode_id = ? AND grant_id = ? AND is_current = 1",
        (episode_id, grant_id),
    ).fetchone()
    if row is None:
        return None
    return (
        AuthorityGrant.model_validate_json(row["body_json"]),
        row["version"],
        bool(row["revoked"]),
    )


def grant_usage(conn: sqlite3.Connection, episode_id: str, grant_id: str) -> tuple[int, int]:
    """(committed_cents, reserved_cents) currently attributed to a grant, from the ledger."""
    row = conn.execute(
        "SELECT COALESCE(SUM(committed_delta_cents), 0) AS c,"
        " COALESCE(SUM(reserved_delta_cents), 0) AS r FROM ledger"
        " WHERE episode_id = ? AND grant_id = ?",
        (episode_id, grant_id),
    ).fetchone()
    return int(row["c"]), int(row["r"])


def ledger_totals(conn: sqlite3.Connection, episode_id: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT COALESCE(SUM(committed_delta_cents), 0) AS c,"
        " COALESCE(SUM(reserved_delta_cents), 0) AS r FROM ledger WHERE episode_id = ?",
        (episode_id,),
    ).fetchone()
    return int(row["c"]), int(row["r"])


def append_ledger(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    at: datetime,
    kind: str,
    committed_delta: int,
    reserved_delta: int,
    grant_id: str,
    hold_id: str | None = None,
    commitment_id: str | None = None,
    receipt_id: str | None = None,
) -> None:
    seq = next_seq(conn, episode_id, "ledger")
    conn.execute(
        "INSERT INTO ledger (episode_id, seq, at, kind, committed_delta_cents,"
        " reserved_delta_cents, hold_id, commitment_id, grant_id, receipt_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            seq,
            fmt_ts(at),
            kind,
            committed_delta,
            reserved_delta,
            hold_id,
            commitment_id,
            grant_id,
            receipt_id,
        ),
    )


def observations(conn: sqlite3.Connection, episode_id: str) -> tuple[ObservationRecord, ...]:
    rows = conn.execute(
        "SELECT * FROM observations WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    )
    return tuple(_obs_from_row(r) for r in rows)


def _obs_from_row(r: sqlite3.Row) -> ObservationRecord:
    return ObservationRecord(
        observation=Observation.model_validate_json(r["body_json"]),
        channel=r["channel"],
        submitted_by=r["submitted_by"],
        revision_after=r["revision_after"],
        structured=StatusFacts.model_validate_json(r["structured_json"])
        if r["structured_json"]
        else None,
    )


def observation_by_source(
    conn: sqlite3.Connection, episode_id: str, source_id: str, source_record_id: str
) -> ObservationRecord | None:
    row = conn.execute(
        "SELECT * FROM observations WHERE episode_id = ? AND source_id = ?"
        " AND source_record_id = ?",
        (episode_id, source_id, source_record_id),
    ).fetchone()
    return _obs_from_row(row) if row else None


def observation_exists(conn: sqlite3.Connection, episode_id: str, observation_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM observations WHERE episode_id = ? AND observation_id = ?",
        (episode_id, observation_id),
    ).fetchone()
    return row is not None


def insert_observation(conn: sqlite3.Connection, episode_id: str, rec: ObservationRecord) -> None:
    obs = rec.observation
    conn.execute(
        "INSERT INTO observations (episode_id, observation_id, source_id, source_record_id,"
        " body_json, channel, submitted_by, structured_json, received_at, revision_after)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            obs.observation_id,
            obs.source_id,
            obs.source_record_id,
            obs.model_dump_json(),
            rec.channel,
            rec.submitted_by,
            rec.structured.model_dump_json() if rec.structured else None,
            fmt_ts(obs.received_at),
            rec.revision_after,
        ),
    )


def receipts(
    conn: sqlite3.Connection, episode_id: str, actor_id: str | None = None
) -> tuple[ActionReceipt, ...]:
    if actor_id is None:
        rows = conn.execute(
            "SELECT body_json FROM receipts WHERE episode_id = ? ORDER BY rowid", (episode_id,)
        )
    else:
        rows = conn.execute(
            "SELECT body_json FROM receipts WHERE episode_id = ? AND actor_id = ? ORDER BY rowid",
            (episode_id, actor_id),
        )
    return tuple(ActionReceipt.model_validate_json(r["body_json"]) for r in rows)


def receipt(conn: sqlite3.Connection, episode_id: str, receipt_id: str) -> ActionReceipt | None:
    row = conn.execute(
        "SELECT body_json FROM receipts WHERE episode_id = ? AND receipt_id = ?",
        (episode_id, receipt_id),
    ).fetchone()
    return ActionReceipt.model_validate_json(row["body_json"]) if row else None


def decisions(conn: sqlite3.Connection, episode_id: str) -> tuple[PolicyDecision, ...]:
    rows = conn.execute(
        "SELECT body_json FROM policy_decisions WHERE episode_id = ? ORDER BY seq", (episode_id,)
    )
    return tuple(PolicyDecision.model_validate_json(r["body_json"]) for r in rows)


def insert_decision(
    conn: sqlite3.Connection, episode_id: str, decision: PolicyDecision
) -> PolicyDecision:
    """Store a decision under an episode-scoped id assigned here, so a policy instance created
    after a restart (whose own counter starts again) can never collide with earlier ids."""
    seq = next_seq(conn, episode_id, "decision_row")
    stored = decision.model_copy(update={"decision_id": f"dec_{seq:04d}"})
    conn.execute(
        "INSERT INTO policy_decisions (episode_id, seq, decision_id, at, revision, body_json)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            seq,
            stored.decision_id,
            fmt_ts(stored.at),
            stored.revision,
            stored.model_dump_json(),
        ),
    )
    return stored


def latest_evaluation(conn: sqlite3.Connection, episode_id: str) -> EvaluationResult | None:
    row = conn.execute(
        "SELECT body_json FROM evaluations WHERE episode_id = ? AND hypothetical = 0"
        " ORDER BY rowid DESC LIMIT 1",
        (episode_id,),
    ).fetchone()
    return EvaluationResult.model_validate_json(row["body_json"]) if row else None


def transitions(conn: sqlite3.Connection, episode_id: str) -> tuple[TransitionView, ...]:
    rows = conn.execute(
        "SELECT * FROM state_transitions WHERE episode_id = ? ORDER BY revision", (episode_id,)
    )
    return tuple(
        TransitionView(
            revision=r["revision"],
            at=parse_ts(r["at"]),
            cause_kind=r["cause_kind"],
            cause_ref=r["cause_ref"],
            summary=r["summary"],
        )
        for r in rows
    )


def tool_calls(conn: sqlite3.Connection, episode_id: str) -> tuple[ToolCallRecord, ...]:
    rows = conn.execute("SELECT * FROM tool_calls WHERE episode_id = ? ORDER BY seq", (episode_id,))
    return tuple(
        ToolCallRecord(
            seq=r["seq"],
            call_id=r["call_id"],
            actor_id=r["actor_id"],
            actor_role=r["actor_role"],
            tool=r["tool"],
            requested_at=parse_ts(r["requested_at"]) if r["requested_at"] else None,
            completed_at=parse_ts(r["completed_at"]) if r["completed_at"] else None,
            revision_before=r["revision_before"],
            revision_after=r["revision_after"],
            envelope_status=r["envelope_status"],
            error_code=r["error_code"],
            receipt_id=r["receipt_id"],
            request=json.loads(r["request_json"]),
            envelope=json.loads(r["envelope_json"]),
        )
        for r in rows
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    """Logged request bodies may be malformed; project only genuine strings."""
    return value if isinstance(value, str) else None


def status_checks(conn: sqlite3.Connection, episode_id: str) -> tuple[StatusCheckView, ...]:
    rows = conn.execute(
        "SELECT * FROM tool_calls WHERE episode_id = ? AND tool = 'query_status' ORDER BY seq",
        (episode_id,),
    )
    out = []
    for r in rows:
        request = json.loads(r["request_json"])
        envelope = json.loads(r["envelope_json"])
        args = _mapping(request.get("arguments"))
        data = _mapping(envelope.get("data"))
        obs = _mapping(data.get("observation"))
        freshness = _mapping(data.get("freshness"))
        error = _mapping(envelope.get("error"))
        out.append(
            StatusCheckView(
                call_id=r["call_id"],
                actor_id=r["actor_id"],
                entity_id=_text(args.get("entity_id")),
                fact=_text(args.get("fact")),
                requested_at=parse_ts(r["requested_at"]) if r["requested_at"] else None,
                completed_at=parse_ts(r["completed_at"]) if r["completed_at"] else None,
                envelope_status=r["envelope_status"],
                error_code=r["error_code"],
                observation_id=_text(_mapping(obs.get("observation")).get("observation_id")),
                deduplicated=data.get("deduplicated") is True,
                stale=freshness.get("stale") if isinstance(freshness.get("stale"), bool) else None,
                reason=_text(data.get("reason") or error.get("message")),
            )
        )
    return tuple(out)


def attempts(
    conn: sqlite3.Connection, episode_id: str, actor_id: str | None = None
) -> tuple[AttemptView, ...]:
    sql = (
        "SELECT call_id, completed_at, actor_id, tool, envelope_status, error_code FROM tool_calls"
        " WHERE episode_id = ? AND receipt_id IS NULL AND envelope_status = 'rejected'"
    )
    params: tuple[Any, ...] = (episode_id,)
    if actor_id is not None:
        sql += " AND actor_id = ?"
        params = (episode_id, actor_id)
    rows = conn.execute(sql + " ORDER BY seq", params)
    return tuple(
        AttemptView(
            call_id=r["call_id"],
            at=parse_ts(r["completed_at"]) if r["completed_at"] else None,
            actor_id=r["actor_id"],
            tool=r["tool"],
            envelope_status=r["envelope_status"],
            error_code=r["error_code"],
        )
        for r in rows
    )


# ---------------------------------------------------------------------------
# Consumable stock ledgers (migration 0004, runtime 1.1.0)
# ---------------------------------------------------------------------------


def _ts(value: datetime | None) -> str | None:
    return fmt_ts(value) if value is not None else None


def stock_movements(conn: sqlite3.Connection, episode_id: str) -> tuple[StockMovementView, ...]:
    rows = conn.execute(
        "SELECT * FROM stock_movements WHERE episode_id = ? ORDER BY seq", (episode_id,)
    )
    return tuple(
        StockMovementView(
            seq=r["seq"],
            at=parse_ts(r["at"]),
            resource_id=r["resource_id"],
            kind=r["kind"],
            quantity=r["quantity"],
            delta=r["delta"],
            counterpart_resource_id=r["counterpart_resource_id"],
            reference=r["reference"],
            hold_id=r["hold_id"],
            shipment_id=r["shipment_id"],
            receipt_id=r["receipt_id"],
            revision=r["revision"],
        )
        for r in rows
    )


def append_stock_movement(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    at: datetime,
    resource_id: str,
    kind: str,
    quantity: int,
    revision: int,
    counterpart_resource_id: str | None = None,
    reference: str | None = None,
    hold_id: str | None = None,
    shipment_id: str | None = None,
    receipt_id: str | None = None,
) -> None:
    """One on-hand change. Credits (opening, receipt) are positive, debits negative."""
    delta = quantity if kind in ("opening", "receipt") else -quantity
    seq = next_seq(conn, episode_id, "stock_movement")
    conn.execute(
        "INSERT INTO stock_movements (episode_id, seq, at, resource_id, kind, quantity, delta,"
        " counterpart_resource_id, reference, hold_id, shipment_id, receipt_id, revision)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            seq,
            fmt_ts(at),
            resource_id,
            kind,
            quantity,
            delta,
            counterpart_resource_id,
            reference,
            hold_id,
            shipment_id,
            receipt_id,
            revision,
        ),
    )


def expected_shipments(conn: sqlite3.Connection, episode_id: str) -> tuple[ExpectedShipment, ...]:
    rows = conn.execute(
        "SELECT * FROM expected_shipments WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    )
    return tuple(
        ExpectedShipment(
            shipment_id=r["shipment_id"],
            destination_resource_id=r["destination_resource_id"],
            quantity=r["quantity"],
            received_quantity=r["received_quantity"],
            expected_at=parse_ts(r["expected_at"]) if r["expected_at"] else None,
            source_ref=r["source_ref"],
        )
        for r in rows
    )


def insert_expected_shipment(
    conn: sqlite3.Connection, episode_id: str, shipment: ExpectedShipment
) -> None:
    conn.execute(
        "INSERT INTO expected_shipments (episode_id, shipment_id, destination_resource_id,"
        " quantity, received_quantity, expected_at, source_ref) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            shipment.shipment_id,
            shipment.destination_resource_id,
            shipment.quantity,
            shipment.received_quantity,
            _ts(shipment.expected_at),
            shipment.source_ref,
        ),
    )


def stock_receipts(conn: sqlite3.Connection, episode_id: str) -> tuple[StockReceiptView, ...]:
    rows = conn.execute(
        "SELECT * FROM stock_receipts WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    )
    return tuple(
        StockReceiptView(
            stock_receipt_id=r["stock_receipt_id"],
            receipt_reference=r["receipt_reference"],
            kind=r["kind"],
            resource_id=r["resource_id"],
            source_resource_id=r["source_resource_id"],
            source_hold_id=r["source_hold_id"],
            shipment_id=r["shipment_id"],
            quantity=r["quantity"],
            unit=r["unit"],
            source_observation_id=r["source_observation_id"],
            at=parse_ts(r["at"]),
            actor_id=r["actor_id"],
            receipt_id=r["receipt_id"],
            revision=r["revision"],
        )
        for r in rows
    )


def stock_receipt_by_reference(
    conn: sqlite3.Connection, episode_id: str, reference: str
) -> StockReceiptView | None:
    return next(
        (r for r in stock_receipts(conn, episode_id) if r.receipt_reference == reference), None
    )


def insert_stock_receipt(conn: sqlite3.Connection, episode_id: str, rec: StockReceiptView) -> None:
    conn.execute(
        "INSERT INTO stock_receipts (episode_id, stock_receipt_id, receipt_reference, kind,"
        " resource_id, source_resource_id, source_hold_id, shipment_id, quantity, unit,"
        " source_observation_id, at, actor_id, receipt_id, revision)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            rec.stock_receipt_id,
            rec.receipt_reference,
            rec.kind,
            rec.resource_id,
            rec.source_resource_id,
            rec.source_hold_id,
            rec.shipment_id,
            rec.quantity,
            rec.unit,
            rec.source_observation_id,
            fmt_ts(rec.at),
            rec.actor_id,
            rec.receipt_id,
            rec.revision,
        ),
    )


def stock_allocations(conn: sqlite3.Connection, episode_id: str) -> tuple[StockAllocationView, ...]:
    rows = conn.execute(
        "SELECT * FROM stock_allocations WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    )
    return tuple(
        StockAllocationView(
            allocation_id=r["allocation_id"],
            resource_id=r["resource_id"],
            service_target_id=r["service_target_id"],
            activity_id=r["activity_id"],
            quantity=r["quantity"],
            remaining_quantity=r["remaining_quantity"],
            source_hold_id=r["source_hold_id"],
            plan_version=r["plan_version"],
            created_at=parse_ts(r["created_at"]),
            receipt_id=r["receipt_id"],
            actor_id=r["actor_id"],
            grant_id=r["grant_id"],
        )
        for r in rows
    )


def insert_stock_allocation(
    conn: sqlite3.Connection, episode_id: str, alloc: StockAllocationView
) -> None:
    conn.execute(
        "INSERT INTO stock_allocations (episode_id, allocation_id, resource_id,"
        " service_target_id, activity_id, quantity, remaining_quantity, source_hold_id,"
        " plan_version, created_at, receipt_id, actor_id, grant_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            alloc.allocation_id,
            alloc.resource_id,
            alloc.service_target_id,
            alloc.activity_id,
            alloc.quantity,
            alloc.remaining_quantity,
            alloc.source_hold_id,
            alloc.plan_version,
            fmt_ts(alloc.created_at),
            alloc.receipt_id,
            alloc.actor_id,
            alloc.grant_id,
        ),
    )


def distributions(conn: sqlite3.Connection, episode_id: str) -> tuple[DistributionView, ...]:
    rows = conn.execute(
        "SELECT * FROM distributions WHERE episode_id = ? ORDER BY rowid", (episode_id,)
    )
    return tuple(
        DistributionView(
            distribution_id=r["distribution_id"],
            distribution_reference=r["distribution_reference"],
            resource_id=r["resource_id"],
            service_target_id=r["service_target_id"],
            activity_id=r["activity_id"],
            quantity=r["quantity"],
            unit=r["unit"],
            goal_version=r["goal_version"],
            allocation_ids=tuple(json.loads(r["allocation_ids_json"])),
            at=parse_ts(r["at"]),
            on_time=bool(r["on_time"]),
            actor_id=r["actor_id"],
            receipt_id=r["receipt_id"],
            revision=r["revision"],
        )
        for r in rows
    )


def distribution_by_reference(
    conn: sqlite3.Connection, episode_id: str, reference: str
) -> DistributionView | None:
    return next(
        (d for d in distributions(conn, episode_id) if d.distribution_reference == reference),
        None,
    )


def insert_distribution(conn: sqlite3.Connection, episode_id: str, rec: DistributionView) -> None:
    conn.execute(
        "INSERT INTO distributions (episode_id, distribution_id, distribution_reference,"
        " resource_id, service_target_id, activity_id, quantity, unit, goal_version,"
        " allocation_ids_json, at, on_time, actor_id, receipt_id, revision)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            rec.distribution_id,
            rec.distribution_reference,
            rec.resource_id,
            rec.service_target_id,
            rec.activity_id,
            rec.quantity,
            rec.unit,
            rec.goal_version,
            dumps(list(rec.allocation_ids)),
            fmt_ts(rec.at),
            int(rec.on_time),
            rec.actor_id,
            rec.receipt_id,
            rec.revision,
        ),
    )


def principal(conn: sqlite3.Connection, episode_id: str, principal_id: str) -> Any:
    sc = scenario(conn, episode_id)
    for p in sc.principals:
        if p.principal_id == principal_id:
            return p
    return None
