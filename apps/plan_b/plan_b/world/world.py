"""The private sandbox world: hidden status trajectories and timed exogenous events.

This package is the only code that loads ``scenarios/private/*.json``. It is used by the
executor (to answer ``query_status`` from the declared observation model at the current
time), by the clock engine (to deliver due world events) and by the runner. Its answers are
limited to what a real source would return at that moment; it never hands out the case
itself, future records or outcome predicates.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from plan_b.domain.digest import file_sha256
from plan_b.domain.models import PrivateCase, StatusRecord, WorldEvent

PRIVATE_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "private"
NO_CASE = "none"


def available_cases() -> list[str]:
    return sorted(p.stem for p in PRIVATE_DIR.glob("*.json"))


def case_path(case_ref: str) -> Path:
    if case_ref not in available_cases():
        raise KeyError(f"unknown case {case_ref!r}")
    return PRIVATE_DIR / f"{case_ref}.json"


@lru_cache(maxsize=32)
def load_case(case_ref: str) -> PrivateCase:
    return PrivateCase.model_validate_json(case_path(case_ref).read_text())


def case_sha256(case_ref: str) -> str:
    return file_sha256(str(case_path(case_ref)))


class World:
    """Answers derived from one private case. ``World(None)`` is an empty world: every status
    query is unknown and nothing arrives."""

    def __init__(self, case: PrivateCase | None) -> None:
        self._case = case

    @property
    def has_case(self) -> bool:
        return self._case is not None

    def status_answer(self, entity_id: str, fact: str, at: datetime) -> StatusRecord | None:
        """Latest status record for (entity, fact) available at ``at``, or None."""
        if self._case is None:
            return None
        records = [
            r
            for r in self._case.status_model
            if r.entity_id == entity_id and r.fact == fact and r.available_from <= at
        ]
        if not records:
            return None
        return max(records, key=lambda r: r.available_from)

    def due_events(self, processed: set[int], up_to: datetime) -> list[tuple[int, WorldEvent]]:
        if self._case is None:
            return []
        return [
            (i, ev)
            for i, ev in enumerate(self._case.world_events)
            if i not in processed and ev.at <= up_to
        ]

    def next_event_time(self, processed: set[int], after: datetime) -> datetime | None:
        if self._case is None:
            return None
        times = [
            ev.at
            for i, ev in enumerate(self._case.world_events)
            if i not in processed and ev.at > after
        ]
        return min(times) if times else None


def world_for_episode(conn: sqlite3.Connection, episode_id: str) -> World:
    row = conn.execute(
        "SELECT case_ref FROM episode_private WHERE episode_id = ?", (episode_id,)
    ).fetchone()
    if row is None or row["case_ref"] == NO_CASE:
        return World(None)
    return World(load_case(row["case_ref"]))


def processed_world_events(conn: sqlite3.Connection, episode_id: str) -> set[int]:
    rows = conn.execute(
        "SELECT event_index FROM world_events_processed WHERE episode_id = ?", (episode_id,)
    )
    return {r["event_index"] for r in rows}


def mark_processed(
    conn: sqlite3.Connection, episode_id: str, index: int, at: str, outcome: str
) -> None:
    conn.execute(
        "INSERT INTO world_events_processed (episode_id, event_index, processed_at, outcome)"
        " VALUES (?, ?, ?, ?)",
        (episode_id, index, at, outcome),
    )
