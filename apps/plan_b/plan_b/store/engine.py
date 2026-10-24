"""Clock advancement and event processing inside an open write transaction.

Every state-changing event increments the revision by one, records a transition, refreshes
readiness previews and stores a public snapshot. See ``domain/clock.py`` for the ordering.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.clock import validate_advance
from plan_b.domain.models import (
    Observation,
    ObservationRecord,
    StatusFacts,
    TimeWindow,
    TransitionView,
    WorldEvent,
)
from plan_b.domain.timeutil import fmt_ts, local_label, parse_ts
from plan_b.store import repo
from plan_b.store.projection_db import build_snapshot, capture_snapshot
from plan_b.world.world import (
    World,
    mark_processed,
    processed_world_events,
    world_for_episode,
)


def advance_by(conn: sqlite3.Connection, episode_id: str, minutes: int) -> list[TransitionView]:
    ep = repo.get_episode(conn, episode_id)
    return advance_to(conn, episode_id, validate_advance(ep.clock, minutes))


def advance_to(conn: sqlite3.Connection, episode_id: str, target: datetime) -> list[TransitionView]:
    ep = repo.get_episode(conn, episode_id)
    if ep.status != "active":
        raise ValueError("a closed episode's clock no longer moves")
    if target < ep.clock:
        raise ValueError("the scenario clock cannot move backward")
    world = world_for_episode(conn, episode_id)
    start_revision = ep.revision
    # Catch up anything scheduled at or before the current instant (registered late).
    run_due_scheduled(conn, episode_id, ep.clock)
    while True:
        t = _next_event_time(
            conn, episode_id, world, after=repo.get_episode(conn, episode_id).clock
        )
        if t is None or t > target:
            break
        repo.set_clock(conn, episode_id, t)
        _process_instant(conn, episode_id, world, t)
    repo.set_clock(conn, episode_id, target)
    return [tr for tr in repo.transitions(conn, episode_id) if tr.revision > start_revision]


def _next_event_time(
    conn: sqlite3.Connection, episode_id: str, world: World, *, after: datetime
) -> datetime | None:
    times: list[datetime] = []
    plan = repo.plan(conn, episode_id)
    by_activity = {a.activity_id: a for a in plan.assignments}
    _, lifecycles = repo.activity_rows(conn, episode_id)
    for aid, state in lifecycles.items():
        a = by_activity.get(aid)
        if a is None:
            continue
        if state == "started" and a.end > after:
            times.append(a.end)
        if state in ("planned", "ready") and a.start > after:
            times.append(a.start)
    nxt = world.next_event_time(processed_world_events(conn, episode_id), after)
    if nxt is not None:
        times.append(nxt)
    row = conn.execute(
        "SELECT MIN(due_at) AS due FROM scheduled_actions WHERE episode_id = ?"
        " AND status = 'pending' AND due_at > ?",
        (episode_id, fmt_ts(after)),
    ).fetchone()
    if row["due"] is not None:
        times.append(parse_ts(row["due"]))
    for h in repo.holds(conn, episode_id):
        if h.status == "active" and h.expires_at > after:
            times.append(h.expires_at)
    for _grant_id, expires in _unexpired_grants(conn, episode_id):
        if expires > after:
            times.append(expires)
    goal = repo.goal(conn, episode_id)
    if not repo.get_flag(conn, episode_id, "event_closed") and goal.hard_end > after:
        times.append(goal.hard_end)
    return min(times) if times else None


def _unexpired_grants(conn: sqlite3.Connection, episode_id: str) -> list[tuple[str, datetime]]:
    from plan_b.domain.models import AuthorityGrant

    out = []
    for row in repo.grant_rows(conn, episode_id, current_only=True):
        if row["revoked"]:
            continue
        g = AuthorityGrant.model_validate_json(row["body_json"])
        if not repo.get_flag(conn, episode_id, f"grant_expired:{g.grant_id}:{row['version']}"):
            out.append((g.grant_id, g.expires_at))
    return out


def _after_change(conn: sqlite3.Connection, episode_id: str) -> None:
    refresh_ready(conn, episode_id)
    capture_snapshot(conn, episode_id)


def _process_instant(conn: sqlite3.Connection, episode_id: str, world: World, t: datetime) -> None:
    # 1. completions (inclusive deadline)
    plan = repo.plan(conn, episode_id)
    by_activity = {a.activity_id: a for a in plan.assignments}
    defs, lifecycles = repo.activity_rows(conn, episode_id)
    for d in defs:
        a = by_activity.get(d.activity_id)
        if a is not None and lifecycles[d.activity_id] == "started" and a.end == t:
            rev = repo.bump_revision(
                conn,
                episode_id,
                at=t,
                cause_kind="activity_completed",
                cause_ref=d.activity_id,
                summary=f"{d.label} completed at {local_label(t)}",
            )
            repo.append_activity_event(
                conn, episode_id, activity_id=d.activity_id, state="completed", at=t, revision=rev
            )
            _after_change(conn, episode_id)

    # 2. world events due now
    for index, ev in world.due_events(processed_world_events(conn, episode_id), t):
        _deliver_world_event(conn, episode_id, index, ev, t)

    # 2b. scheduled exogenous actor actions due now (after world events, before starts)
    run_due_scheduled(conn, episode_id, t)

    # 3. hold expiries
    for h in repo.holds(conn, episode_id):
        if h.status == "active" and h.expires_at <= t:
            conn.execute(
                "UPDATE holds SET status = 'expired', terminal_at = ? WHERE episode_id = ?"
                " AND hold_id = ?",
                (fmt_ts(t), episode_id, h.hold_id),
            )
            repo.append_ledger(
                conn,
                episode_id,
                at=t,
                kind="expire_reserve",
                committed_delta=0,
                reserved_delta=-h.reserved_cents,
                grant_id=h.grant_id,
                hold_id=h.hold_id,
            )
            repo.bump_revision(
                conn,
                episode_id,
                at=t,
                cause_kind="hold_expired",
                cause_ref=h.hold_id,
                summary=(
                    f"Hold {h.hold_id} on {h.resource_id} expired at {local_label(t)};"
                    f" {h.reserved_cents} reserved cents returned"
                ),
            )
            _after_change(conn, episode_id)

    # 4. grant expiries
    for row in repo.grant_rows(conn, episode_id, current_only=True):
        from plan_b.domain.models import AuthorityGrant

        g = AuthorityGrant.model_validate_json(row["body_json"])
        flag = f"grant_expired:{g.grant_id}:{row['version']}"
        if not row["revoked"] and g.expires_at <= t and not repo.get_flag(conn, episode_id, flag):
            repo.set_flag(conn, episode_id, flag)
            repo.bump_revision(
                conn,
                episode_id,
                at=t,
                cause_kind="grant_expired",
                cause_ref=g.grant_id,
                summary=(
                    f"Grant {g.grant_id} expired at {local_label(t)};"
                    " new actions need a valid grant"
                ),
            )
            _after_change(conn, episode_id)

    # 5. starts (strict execution readiness)
    plan = repo.plan(conn, episode_id)
    by_activity = {a.activity_id: a for a in plan.assignments}
    defs, lifecycles = repo.activity_rows(conn, episode_id)
    adapter = adapter_for(repo.get_episode(conn, episode_id).profile_id)
    for d in sorted(
        (d for d in defs if d.activity_id in by_activity),
        key=lambda d: (by_activity[d.activity_id].start, d.activity_id),
    ):
        a = by_activity[d.activity_id]
        _, lifecycles = repo.activity_rows(conn, episode_id)
        if lifecycles[d.activity_id] not in ("planned", "ready") or a.start != t:
            continue
        report = adapter.check_readiness(build_snapshot(conn, episode_id), d.activity_id, t)
        if report.ready:
            rev = repo.bump_revision(
                conn,
                episode_id,
                at=t,
                cause_kind="activity_started",
                cause_ref=d.activity_id,
                summary=f"{d.label} started at {local_label(t)}",
            )
            repo.append_activity_event(
                conn,
                episode_id,
                activity_id=d.activity_id,
                state="started",
                at=t,
                revision=rev,
                reasons=report.met,
                evidence=report.evidence_refs,
            )
        else:
            rev = repo.bump_revision(
                conn,
                episode_id,
                at=t,
                cause_kind="activity_failed",
                cause_ref=d.activity_id,
                summary=(
                    f"{d.label} could not start at {local_label(t)}: " + "; ".join(report.unmet)
                ),
            )
            repo.append_activity_event(
                conn,
                episode_id,
                activity_id=d.activity_id,
                state="failed",
                at=t,
                revision=rev,
                reasons=report.unmet,
                evidence=report.evidence_refs,
            )
        _after_change(conn, episode_id)

    # 6. event close
    goal = repo.goal(conn, episode_id)
    if goal.hard_end <= t and not repo.get_flag(conn, episode_id, "event_closed"):
        repo.set_flag(conn, episode_id, "event_closed")
        _, lifecycles = repo.activity_rows(conn, episode_id)
        done = sum(1 for aid in goal.required_activity_ids if lifecycles.get(aid) == "completed")
        repo.bump_revision(
            conn,
            episode_id,
            at=t,
            cause_kind="event_closed",
            cause_ref=None,
            summary=(
                f"Event window closed at {local_label(t)}; {done} of "
                f"{len(goal.required_activity_ids)} required activities completed"
            ),
        )
        _after_change(conn, episode_id)


def _deliver_world_event(
    conn: sqlite3.Connection, episode_id: str, index: int, ev: WorldEvent, t: datetime
) -> None:
    existing = repo.observation_by_source(conn, episode_id, ev.source_id, ev.source_record_id)
    if existing is not None:
        # A re-delivered source record is not new evidence: no observation, no revision.
        mark_processed(
            conn,
            episode_id,
            index,
            fmt_ts(t),
            f"duplicate_of:{existing.observation.observation_id}",
        )
        return
    ep = repo.get_episode(conn, episode_id)
    goal = repo.goal(conn, episode_id)
    obs_id = f"obs_{repo.next_seq(conn, episode_id, 'observation'):04d}"
    valid = validity_window(min(ev.observed_at, t), goal.hard_end)
    observation = Observation(
        observation_id=obs_id,
        event_id=ep.event_id,
        entity_id=ev.entity_id,
        kind=ev.observation_kind,
        source_id=ev.source_id,
        source_record_id=ev.source_record_id,
        correlation_group=ev.correlation_group,
        observed_at=ev.observed_at,
        received_at=t,
        valid_window=valid,
        authority_scope=ev.authority_scope,
        text=ev.text,
        supersedes=ev.supersedes,
    )
    structured = None
    channel = "scenario_delivery"
    if ev.kind == "resource_arrival":
        channel = "arrival_record"
        if ev.new_status is not None:
            structured = StatusFacts(
                fact="arrival",
                status_code="arrived",
                domain_status=ev.new_status,
                reported_eta=None,
            )
    rev = repo.bump_revision(
        conn,
        episode_id,
        at=t,
        cause_kind="observation",
        cause_ref=obs_id,
        summary=(
            f"{'Arrival recorded' if ev.kind == 'resource_arrival' else 'Message received'}"
            f" for {ev.entity_id} from {ev.source_id} at {local_label(t)}"
        ),
    )
    repo.insert_observation(
        conn,
        episode_id,
        ObservationRecord(
            observation=observation,
            channel=channel,  # type: ignore[arg-type]
            submitted_by=None,
            revision_after=rev,
            structured=structured,
        ),
    )
    if ev.kind == "resource_arrival" and ev.new_status is not None:
        # Same newer-only rule as status queries: a record older than the current basis does
        # not overwrite it (the scorer reconstructs status the same way).
        conn.execute(
            "UPDATE resources SET status = ?, status_basis = 'arrival_observation',"
            " status_observation_id = ?, status_observed_at = ?, reported_eta = NULL"
            " WHERE episode_id = ? AND resource_id = ?"
            " AND (status_basis = 'catalog' OR status_observed_at IS NULL"
            " OR status_observed_at <= ?)",
            (
                ev.new_status,
                obs_id,
                fmt_ts(ev.observed_at),
                episode_id,
                ev.entity_id,
                fmt_ts(ev.observed_at),
            ),
        )
    mark_processed(conn, episode_id, index, fmt_ts(t), f"observation:{obs_id}")
    _after_change(conn, episode_id)


def run_due_scheduled(conn: sqlite3.Connection, episode_id: str, t: datetime) -> int:
    """Execute pending scheduled actor actions due at or before ``t`` through the executor,
    each with its actor's own session, in (due time, registration) order."""
    from plan_b.tools.executor import execute_in  # executor imports this module

    rows = conn.execute(
        "SELECT * FROM scheduled_actions WHERE episode_id = ? AND status = 'pending'"
        " AND due_at <= ? ORDER BY due_at, order_index",
        (episode_id, fmt_ts(t)),
    ).fetchall()
    for r in rows:
        _, env = execute_in(
            conn,
            r["tool"],
            json.loads(r["body_json"]),
            session_id=r["session_id"],
            fill_expected_revision=bool(r["fill_expected_revision"]),
        )
        conn.execute(
            "UPDATE scheduled_actions SET status = 'done', executed_at = ?, call_id = ?,"
            " envelope_status = ?, receipt_id = ?, receipt_status = ?, error_code = ?"
            " WHERE episode_id = ? AND action_id = ?",
            (
                fmt_ts(t),
                env.call_id,
                env.status,
                env.receipt.receipt_id if env.receipt else None,
                env.receipt.status if env.receipt else None,
                env.error.code if env.error else None,
                episode_id,
                r["action_id"],
            ),
        )
    return len(rows)


def validity_window(start: datetime, hard_end: datetime) -> TimeWindow:
    """An observation is considered relevant from its source time through the event end."""
    end = hard_end if hard_end > start else start + timedelta(minutes=1)
    return TimeWindow(start=start, end=end)


def refresh_ready(conn: sqlite3.Connection, episode_id: str) -> None:
    """Record planned<->ready preview transitions at the current revision (no increment)."""
    snap = build_snapshot(conn, episode_id)
    for view in snap.activities:
        if view.lifecycle not in ("planned", "ready") or view.readiness is None:
            continue
        want = "ready" if view.readiness.ready else "planned"
        if want != view.lifecycle:
            repo.append_activity_event(
                conn,
                episode_id,
                activity_id=view.definition.activity_id,
                state=want,
                at=snap.clock,
                revision=snap.revision,
                reasons=view.readiness.met if want == "ready" else view.readiness.unmet,
                evidence=view.readiness.evidence_refs,
            )
