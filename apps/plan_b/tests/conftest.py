"""Shared fixtures: a real SQLite store, real episodes and real scoped sessions."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from plan_b.domain.models import EventStateView, ToolEnvelope
from plan_b.domain.timeutil import parse_ts
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.engine import advance_by, advance_to
from plan_b.store.episodes import create_episode
from plan_b.store.projection_db import TRACE_VIEWER, build_view
from plan_b.store.sessions import issue_session
from plan_b.tools.client import InProcessToolClient, LoseResponse

DAY = "2026-11-05"


def at(hhmm: str) -> datetime:
    """Event-local wall time on the fictional event date (America/New_York, -05:00)."""
    return parse_ts(f"{DAY}T{hhmm}:00-05:00")


class Sandbox:
    """One loaded episode with a client per principal, all through the real executor."""

    def __init__(self, db: Database, case_ref: str = "dev01") -> None:
        self.db = db
        with db.write() as conn:
            self.episode_id = create_episode(conn, case_ref=case_ref)
        self._clients: dict[str, InProcessToolClient] = {}
        self.tokens: dict[str, str] = {}

    def client(self, principal_id: str, lose: LoseResponse | None = None) -> InProcessToolClient:
        if principal_id not in self._clients or lose is not None:
            with self.db.write() as conn:
                token, session = issue_session(conn, self.episode_id, principal_id)
            self.tokens[principal_id] = token
            c = InProcessToolClient(
                self.db,
                token,
                principal_id=principal_id,
                event_id="e_showcase_01",
                grant_id=session.grant_id,
                lose_response=lose,
            )
            if lose is not None:
                return c
            self._clients[principal_id] = c
        return self._clients[principal_id]

    @property
    def agent(self) -> InProcessToolClient:
        return self.client("agent_demo")

    @property
    def organizer(self) -> InProcessToolClient:
        return self.client("organizer_demo")

    def advance(self, minutes: int) -> None:
        with self.db.write() as conn:
            advance_by(conn, self.episode_id, minutes)

    def advance_to(self, hhmm: str) -> None:
        with self.db.write() as conn:
            advance_to(conn, self.episode_id, at(hhmm))

    def view(self) -> EventStateView:
        with self.db.read() as conn:
            return build_view(conn, self.episode_id, TRACE_VIEWER, visibility="audit")

    def revision(self) -> int:
        with self.db.read() as conn:
            return repo.get_episode(conn, self.episode_id).revision

    def clock(self) -> datetime:
        with self.db.read() as conn:
            return repo.get_episode(conn, self.episode_id).clock

    def count(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        with self.db.read() as conn:
            sql = f"SELECT COUNT(*) AS n FROM {table} WHERE episode_id = ?"
            if where:
                sql += f" AND {where}"
            return int(conn.execute(sql, (self.episode_id, *params)).fetchone()["n"])

    def ledger(self) -> tuple[int, int]:
        with self.db.read() as conn:
            return repo.ledger_totals(conn, self.episode_id)

    def raw(self) -> sqlite3.Connection:
        return self.db.connect()

    # --- common flows -----------------------------------------------------------------

    def query(self, entity: str = "projector", fact: str = "delivery_eta") -> ToolEnvelope:
        return self.agent.call("query_status", arguments={"entity_id": entity, "fact": fact})

    def evaluate(self, client: InProcessToolClient | None = None, **args: Any) -> ToolEnvelope:
        return (client or self.agent).call("evaluate_candidates", arguments=args)

    def candidate(self, env: ToolEnvelope, label_prefix: str) -> dict[str, Any]:
        assert env.data is not None
        for c in env.data["candidates"]:
            if c["label"].startswith(label_prefix) and " + " not in c["label"]:
                return c
        raise AssertionError(f"no candidate labeled {label_prefix!r}")

    def apply(
        self,
        cand: dict[str, Any],
        env: ToolEnvelope,
        key: str,
        *,
        client: InProcessToolClient | None = None,
        report: str | None = None,
    ) -> ToolEnvelope:
        assert env.data is not None
        return (client or self.agent).call(
            "apply_plan",
            arguments={
                "candidate_plan_id": cand["candidate_id"],
                "constraint_report_ref": report or cand["report_id"],
            },
            idempotency_key=key,
            expected_revision=env.data["revision"],
            expected_goal_version=env.data["goal_version"],
        )

    def hold_backup(self, key: str, start: str = "17:10", end: str = "17:30") -> ToolEnvelope:
        return self.agent.call(
            "hold_resource",
            arguments={
                "resource_id": "backup_projector",
                "activity_id": "demonstrations",
                "window": {"start": at(start).isoformat(), "end": at(end).isoformat()},
            },
            idempotency_key=key,
            expected_revision=self.revision(),
        )

    def raise_committed_limit(self, cents: int = 3500, key: str = "org-raise") -> ToolEnvelope:
        return self.organizer.call(
            "update_grant",
            arguments={
                "target_grant_id": "grant_coordinator_demo",
                "max_total_committed_cents": cents,
                "reason": "test: organizer approves the backup booking",
            },
            idempotency_key=key,
            expected_revision=self.revision(),
        )

    def check_in(self, principal: str, resource: str, key: str) -> ToolEnvelope:
        return self.client(principal).call(
            "check_in", arguments={"resource_id": resource}, idempotency_key=key
        )


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "plan_b_test.sqlite3")


@pytest.fixture
def sandbox(db: Database) -> Sandbox:
    return Sandbox(db, "dev01")


@pytest.fixture
def make_sandbox(db: Database) -> Iterator[Any]:
    def make(case_ref: str = "dev01") -> Sandbox:
        return Sandbox(db, case_ref)

    yield make
