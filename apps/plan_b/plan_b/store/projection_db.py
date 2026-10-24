"""Build visible projections from the store.

Only public tables are read here. ``episode_private`` and ``world_events_processed`` are never
touched, so a projection cannot carry private runner input.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Literal

from plan_b.domain.models import (
    RUNTIME_VERSION,
    ActorContext,
    EventStateView,
    GrantView,
    PlanningSnapshot,
    ViewerInfo,
)
from plan_b.domain.projection import (
    activity_views,
    budget_view,
    resource_view,
    with_effective_status,
)
from plan_b.domain.timeutil import parse_ts
from plan_b.store import repo

SANDBOX_LABEL = "Fictional sandbox: no real bookings, purchases, deliveries, or messages"

Visibility = Literal["audit", "principal"]


def build_snapshot(
    conn: sqlite3.Connection, episode_id: str, *, apply_lead_minutes: int = 0
) -> PlanningSnapshot:
    """``apply_lead_minutes`` sets ``effective_at`` = clock + lead: an evaluation passes the
    apply_plan duration so "applicable now" holds when the apply executes; apply_plan's own
    revalidation (already at execution time) passes 0."""
    ep = repo.get_episode(conn, episode_id)
    sc = repo.scenario(conn, episode_id)
    goal = repo.goal(conn, episode_id)
    plan = repo.plan(conn, episode_id)
    holds = with_effective_status(repo.holds(conn, episode_id), ep.clock)
    commitments = repo.commitments(conn, episode_id)
    checkins = repo.checkins(conn, episode_id)
    resources = tuple(
        resource_view(
            repo.resource_def(r),
            status=r["status"],
            status_basis=r["status_basis"],
            status_observation_id=r["status_observation_id"],
            status_observed_at=parse_ts(r["status_observed_at"])
            if r["status_observed_at"]
            else None,
            reported_eta=parse_ts(r["reported_eta"]) if r["reported_eta"] else None,
            plan=plan,
            holds=holds,
            commitments=commitments,
        )
        for r in repo.resource_rows(conn, episode_id)
    )
    defs, lifecycles = repo.activity_rows(conn, episode_id)
    activities = activity_views(
        definitions=defs,
        lifecycles=lifecycles,
        history=repo.activity_history(conn, episode_id),
        plan=plan,
        resources=resources,
        checkins=checkins,
        commitments=commitments,
        clock=ep.clock,
    )
    return PlanningSnapshot(
        event_id=ep.event_id,
        revision=ep.revision,
        clock=ep.clock,
        goal=goal,
        planning=sc.planning,
        activities=activities,
        resources=resources,
        plan=plan,
        holds=holds,
        commitments=commitments,
        checkins=checkins,
        budget=budget_view(goal, holds, commitments),
        effective_at=ep.clock + timedelta(minutes=apply_lead_minutes),
    )


def _grant_views(
    conn: sqlite3.Connection, episode_id: str, *, current_only: bool
) -> list[GrantView]:
    from plan_b.domain.models import AuthorityGrant

    ep = repo.get_episode(conn, episode_id)
    out: list[GrantView] = []
    for row in repo.grant_rows(conn, episode_id, current_only=current_only):
        grant = AuthorityGrant.model_validate_json(row["body_json"])
        revoked = bool(row["revoked"])
        committed, reserved = repo.grant_usage(conn, episode_id, grant.grant_id)
        out.append(
            GrantView(
                grant=grant,
                version=row["version"],
                revoked=revoked,
                valid_now=bool(row["is_current"]) and not revoked and ep.clock < grant.expires_at,
                committed_used_cents=committed,
                reserved_used_cents=reserved,
                issued_receipt_id=row["issued_receipt_id"],
            )
        )
    return out


def actor_context(
    conn: sqlite3.Connection, episode_id: str, principal_id: str, grant_id: str | None, role: str
) -> ActorContext:
    ep = repo.get_episode(conn, episode_id)
    if grant_id is None:
        return ActorContext(
            principal_id=principal_id,
            role=role,  # type: ignore[arg-type]
            grant=None,
            grant_version=None,
            grant_valid=False,
            committed_used_cents=0,
            reserved_used_cents=0,
        )
    found = repo.current_grant(conn, episode_id, grant_id)
    if found is None:
        raise KeyError(f"grant {grant_id} not found")
    grant, version, revoked = found
    committed, reserved = repo.grant_usage(conn, episode_id, grant_id)
    return ActorContext(
        principal_id=principal_id,
        role=role,  # type: ignore[arg-type]
        grant=grant,
        grant_version=version,
        grant_valid=not revoked and ep.clock < grant.expires_at,
        committed_used_cents=committed,
        reserved_used_cents=reserved,
    )


def build_view(
    conn: sqlite3.Connection,
    episode_id: str,
    viewer: ViewerInfo,
    *,
    visibility: Visibility,
) -> EventStateView:
    """Role-filtered visible state. ``audit`` (organizer, moderator, trace export) shows every
    receipt, attempt and grant; ``principal`` shows only the viewer's own receipts, attempts
    and grant. Facts (schedule, resources, observations, check-ins, holds, decisions) are
    public to every event session."""
    ep = repo.get_episode(conn, episode_id)
    sc = repo.scenario(conn, episode_id)
    snap = build_snapshot(conn, episode_id)
    current = _grant_views(conn, episode_id, current_only=True)
    history = _grant_views(conn, episode_id, current_only=False)
    if visibility == "principal":
        mine = {viewer.grant_id}
        current = [g for g in current if g.grant.grant_id in mine]
        history = [g for g in history if g.grant.grant_id in mine]
        receipts = repo.receipts(conn, episode_id, actor_id=viewer.principal_id)
        attempts = repo.attempts(conn, episode_id, actor_id=viewer.principal_id)
    else:
        receipts = repo.receipts(conn, episode_id)
        attempts = repo.attempts(conn, episode_id)
    return EventStateView(
        runtime_version=RUNTIME_VERSION,
        episode_id=ep.episode_id,
        event_id=ep.event_id,
        scenario_id=ep.scenario_id,
        profile_id=ep.profile_id,
        fictional=True,
        sandbox_label=SANDBOX_LABEL,
        timezone=sc.timezone,
        episode_status=ep.status,  # type: ignore[arg-type]
        clock=ep.clock,
        revision=ep.revision,
        goal=snap.goal,
        goal_history=repo.goal_history(conn, episode_id),
        activities=snap.activities,
        plan=snap.plan,
        plan_history=repo.plan_history(conn, episode_id),
        resources=snap.resources,
        holds=snap.holds,
        commitments=snap.commitments,
        checkins=snap.checkins,
        budget=snap.budget,
        grants=tuple(current),
        grant_history=tuple(history),
        observations=repo.observations(conn, episode_id),
        status_sources=sc.status_sources,
        status_checks=repo.status_checks(conn, episode_id),
        receipts=receipts,
        attempts=attempts,
        decisions=repo.decisions(conn, episode_id),
        latest_evaluation=repo.latest_evaluation(conn, episode_id),
        transitions=repo.transitions(conn, episode_id),
        declared_assumptions=sc.declared_assumptions,
        tool_durations_minutes=dict(sc.tool_durations_minutes),
        viewer=viewer,
    )


TRACE_VIEWER = ViewerInfo(
    principal_id="trace_export", role="moderator", display_name="Recorded trace", grant_id=None
)


def capture_snapshot(conn: sqlite3.Connection, episode_id: str) -> None:
    """Store the sanitized audit projection for the current revision.

    One snapshot per revision. A later call at the same revision (a status check, an evaluation,
    a rejected receipt or recorded decisions, none of which change the revision) refreshes the
    stored view so replay shows those facts, while ``at`` keeps the time the revision was first
    captured: a frame's time is when its revision came into being; ``state.clock`` is when the
    view was last refreshed."""
    ep = repo.get_episode(conn, episode_id)
    view = build_view(conn, episode_id, TRACE_VIEWER, visibility="audit")
    conn.execute(
        "INSERT INTO revision_snapshots (episode_id, revision, at, view_json) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(episode_id, revision) DO UPDATE SET view_json = excluded.view_json",
        (
            episode_id,
            ep.revision,
            view.clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
            view.model_dump_json(),
        ),
    )
