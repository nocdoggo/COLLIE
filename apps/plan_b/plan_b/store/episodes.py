"""Loading a clean episode from fixtures, and reset.

Reset never deletes: it closes the previous episode (revoking its sessions) and creates a new
episode with a fresh identifier and the fixture's initial state. Holds, receipts, idempotency
records, evaluations, observations and policy memory are all episode-scoped, so nothing
carries over, while the closed episode's records remain available for audit and export.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime

from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.fixtures import load_public_scenario, public_scenario_sha256
from plan_b.domain.models import RUNTIME_VERSION, ObservationRecord
from plan_b.domain.timeutil import fmt_ts
from plan_b.store import repo
from plan_b.store.engine import refresh_ready
from plan_b.store.projection_db import capture_snapshot
from plan_b.store.sessions import revoke_episode_sessions
from plan_b.world.validate import validate_case_ref
from plan_b.world.world import NO_CASE, available_cases, case_sha256


def close_episode(conn: sqlite3.Connection, episode_id: str) -> None:
    conn.execute(
        "UPDATE episodes SET status = 'closed', closed_wall = ? WHERE episode_id = ?"
        " AND status = 'active'",
        (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), episode_id),
    )
    revoke_episode_sessions(conn, episode_id)


def create_episode(
    conn: sqlite3.Connection,
    *,
    scenario_id: str = "dev_fixture_01",
    case_ref: str = NO_CASE,
    close_others: bool = True,
) -> str:
    if case_ref != NO_CASE and case_ref not in available_cases():
        raise KeyError(f"unknown case {case_ref!r}")
    sc = load_public_scenario(scenario_id)
    problems = adapter_for(sc.profile_id).validate_config(sc)
    if problems:
        raise ValueError("public scenario failed adapter validation: " + "; ".join(problems))
    if case_ref != NO_CASE:
        problems = validate_case_ref(sc, case_ref)
        if problems:
            raise ValueError(f"private case {case_ref} failed validation: " + "; ".join(problems))
    if close_others:
        for row in conn.execute("SELECT episode_id FROM episodes WHERE status = 'active'"):
            close_episode(conn, row["episode_id"])
    episode_id = f"ep_{secrets.token_hex(6)}"
    st = sc.initial_state
    conn.execute(
        "INSERT INTO episodes (episode_id, scenario_id, profile_id, event_id, status, clock,"
        " revision, goal_version, plan_version, public_fixture_sha256, runtime_version,"
        " created_wall) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, 1, ?, ?, ?)",
        (
            episode_id,
            sc.scenario_id,
            sc.profile_id,
            sc.event_id,
            fmt_ts(st.clock),
            st.revision,
            sc.goal.version,
            public_scenario_sha256(scenario_id),
            RUNTIME_VERSION,
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        ),
    )
    conn.execute(
        "INSERT INTO episode_private (episode_id, case_ref, case_sha256) VALUES (?, ?, ?)",
        (episode_id, case_ref, case_sha256(case_ref) if case_ref != NO_CASE else "0" * 64),
    )
    conn.execute(
        "INSERT INTO scenario_config (episode_id, public_json) VALUES (?, ?)",
        (episode_id, sc.model_dump_json()),
    )
    conn.execute(
        "INSERT INTO goals (episode_id, version, body_json, created_at, created_by)"
        " VALUES (?, ?, ?, ?, 'fixture')",
        (episode_id, sc.goal.version, sc.goal.model_dump_json(), fmt_ts(st.clock)),
    )
    for a in sc.activities:
        conn.execute(
            "INSERT INTO activities (episode_id, activity_id, definition_json, lifecycle)"
            " VALUES (?, ?, ?, 'planned')",
            (episode_id, a.activity_id, a.model_dump_json()),
        )
    for lc in st.lifecycle:
        repo.append_activity_event(
            conn,
            episode_id,
            activity_id=lc.activity_id,
            state=lc.state,
            at=lc.at,
            revision=st.revision,
            reasons=(f"recorded in {lc.source_ref}",),
        )
    for r in sc.resources:
        conn.execute(
            "INSERT INTO resources (episode_id, resource_id, definition_json, status, status_basis)"
            " VALUES (?, ?, ?, ?, 'catalog')",
            (episode_id, r.resource_id, r.model_dump_json(), r.initial_status),
        )
    conn.execute(
        "INSERT INTO plans (episode_id, plan_version, assignments_json) VALUES (?, 1, ?)",
        (episode_id, repo.dumps([a.model_dump(mode="json") for a in st.assignments])),
    )
    for obs in sc.visible_observations:
        repo.insert_observation(
            conn,
            episode_id,
            ObservationRecord(
                observation=obs,
                channel="fixture_initial",
                submitted_by=None,
                revision_after=st.revision,
                structured=None,
            ),
        )
    for i, c in enumerate(st.checked_in):
        conn.execute(
            "INSERT INTO checkins (episode_id, checkin_id, principal_id, resource_id, at,"
            " available_start, available_end, observation_id, channel)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'fixture_initial')",
            (
                episode_id,
                f"chk_fixture_{i + 1:02d}",
                c.principal_id,
                c.resource_id,
                fmt_ts(c.at),
                fmt_ts(c.available.start),
                fmt_ts(c.available.end),
            ),
        )
    for g in sc.authority_grants:
        conn.execute(
            "INSERT INTO grants (episode_id, grant_id, version, body_json, principal_id, revoked,"
            " is_current, issued_at) VALUES (?, ?, 1, ?, ?, 0, 1, ?)",
            (episode_id, g.grant_id, g.model_dump_json(), g.principal_id, fmt_ts(st.clock)),
        )
    conn.execute(
        "INSERT INTO state_transitions (episode_id, revision, at, cause_kind, cause_ref, summary)"
        " VALUES (?, ?, ?, 'episode_loaded', ?, ?)",
        (
            episode_id,
            st.revision,
            fmt_ts(st.clock),
            sc.scenario_id,
            f"Loaded {sc.profile_id} fixture {sc.scenario_id} at revision {st.revision}",
        ),
    )
    refresh_ready(conn, episode_id)
    capture_snapshot(conn, episode_id)
    return episode_id
