"""Regression tests for the audit findings of the domain area.

REQ-01: references resolve and the initial plan is feasible at load (public fixture), and a
private case's references resolve against its public scenario. REQ-03 / F3: scoring and
preview readiness go through the domain adapter of the episode's own profile. REQ-12: the
runner does not wake the policy once nothing it does can be accepted. F9: database triggers
protect history, also against REPLACE (every store connection turns on recursive_triggers).
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plan_b.api.app import create_app
from plan_b.domain import fixtures, projection
from plan_b.domain.adapters.campus import CampusAdapter
from plan_b.domain.adapters.outcome import DomainOutcome, Violation
from plan_b.domain.fixtures import load_public_scenario, public_scenario_path
from plan_b.domain.models import (
    ActorContext,
    EpisodeHistory,
    EvaluationRequest,
    EventStateView,
    PolicyRunResult,
    PrivateCase,
    PublicScenario,
)
from plan_b.evaluation import scoring
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import episode_history, run_case, tick_loop
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.episodes import create_episode
from plan_b.store.projection_db import TRACE_VIEWER, build_snapshot, build_view, capture_snapshot
from plan_b.world import world
from plan_b.world.validate import validate_case
from plan_b.world.world import case_path, load_case
from tests.conftest import Sandbox, at
from tests.test_api import CODE, _auth, _moderator

ADAPTER = CampusAdapter()
Json = dict[str, Any]
# The shipped files, resolved before any test points the loaders at scratch copies.
SHIPPED_PUBLIC = public_scenario_path("dev_fixture_01")
SHIPPED_DEV01 = case_path("dev01")


def _public_json() -> Json:
    data: Json = json.loads(SHIPPED_PUBLIC.read_text())
    return data


def _private_json() -> Json:
    data: Json = json.loads(SHIPPED_DEV01.read_text())
    return data


def _by(items: list[Json], key: str, value: str) -> Json:
    return next(i for i in items if i[key] == value)


@pytest.fixture
def scratch_public(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[Json], None]:
    """Point the public fixture loader at a scratch copy (the shipped file is untouched)."""
    folder = tmp_path / "public"
    folder.mkdir()
    monkeypatch.setattr(fixtures, "PUBLIC_DIR", folder)

    def write(data: Json) -> None:
        (folder / "campus_showcase.json").write_text(json.dumps(data))

    return write


@pytest.fixture
def scratch_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Point the private case loader at a scratch folder holding the shipped dev01 plus the
    mutated copies written by the test."""
    folder = tmp_path / "private"
    folder.mkdir()
    (folder / "dev01.json").write_text(SHIPPED_DEV01.read_text())
    monkeypatch.setattr(world, "PRIVATE_DIR", folder)
    load_case.cache_clear()

    def write(name: str, data: Json) -> None:
        (folder / f"{name}.json").write_text(json.dumps(data))

    yield write
    load_case.cache_clear()


# ---------------------------------------------------------------------- REQ-01 public


def _set(path: tuple[Any, ...], value: Any) -> Callable[[Json], None]:
    def mutate(d: Json) -> None:
        target: Any = d
        for step in path[:-1]:
            target = target[step]
        target[path[-1]] = value

    return mutate


def _principal(pid: str, field: str, value: Any) -> Callable[[Json], None]:
    def mutate(d: Json) -> None:
        _by(d["principals"], "principal_id", pid)[field] = value

    return mutate


def _grant(gid: str, field: str, value: Any) -> Callable[[Json], None]:
    def mutate(d: Json) -> None:
        _by(d["authority_grants"], "grant_id", gid)[field] = value

    return mutate


def _resource(rid: str, update: Callable[[Json], None]) -> Callable[[Json], None]:
    def mutate(d: Json) -> None:
        update(_by(d["resources"], "resource_id", rid))

    return mutate


def _drop_assignment(aid: str) -> Callable[[Json], None]:
    def mutate(d: Json) -> None:
        st = d["initial_state"]
        st["assignments"] = [a for a in st["assignments"] if a["activity_id"] != aid]

    return mutate


def _move_welcome(d: Json) -> None:
    welcome = _by(d["initial_state"]["assignments"], "activity_id", "welcome")
    welcome["start"], welcome["end"] = "2026-11-05T16:45:00-05:00", "2026-11-05T16:55:00-05:00"


def _set_terms(field: str, value: Any) -> Callable[[Json], None]:
    def update(r: Json) -> None:
        r["terms"][field] = value

    return update


# One mutation per probe of the audit, and the problem validate_config must report for it.
PUBLIC_MUTATIONS: dict[str, tuple[Callable[[Json], None], str]] = {
    "lifecycle unknown activity": (
        _set(("initial_state", "lifecycle", 0, "activity_id"), "ghost_activity"),
        "initial lifecycle record for unknown activity ghost_activity",
    ),
    "checkin unknown resource": (
        _set(("initial_state", "checked_in", 0, "resource_id"), "ghost_resource"),
        "initial check-in for unregistered resource ghost_resource",
    ),
    "checkin unknown principal": (
        _set(("initial_state", "checked_in", 0, "principal_id"), "ghost_principal"),
        "initial check-in by unknown principal ghost_principal",
    ),
    "observation unknown entity": (
        _set(("visible_observations", 0, "entity_id"), "ghost_entity"),
        "observation obs_notice_01: unknown entity ghost_entity",
    ),
    "observation other event": (
        _set(("visible_observations", 0, "event_id"), "e_other_event"),
        "observation obs_notice_01 is for event e_other_event",
    ),
    "grant other event": (
        _grant("grant_coordinator_demo", "event_id", "e_other_event"),
        "grant grant_coordinator_demo is for event e_other_event",
    ),
    "principal speaks for unknown": (
        _principal("participant_host", "speaks_for_resource_ids", ["ghost_resource"]),
        "principal participant_host speaks for unknown resource ghost_resource",
    ),
    "terms unknown status source": (
        _resource("projector", _set_terms("status_source_id", "ghost_source")),
        "projector status source ghost_source is not registered",
    ),
    "required activity unassigned": (
        _drop_assignment("closing"),
        "initial plan fails required_activities: Required activities without an assignment: "
        "closing",
    ),
    "assignment outside window": (
        _move_welcome,
        "initial plan fails activity_windows: welcome 16:45-16:55 is outside its window "
        "17:00-17:10",
    ),
    "grant principal_id unknown": (
        _grant("grant_coordinator_demo", "principal_id", "ghost_principal"),
        "grant grant_coordinator_demo: unknown principal ghost_principal",
    ),
    "principal grant role mismatch": (
        _grant("grant_host_self", "principal_role", "organizer"),
        "principal participant_host (participant) holds grant grant_host_self, issued to "
        "participant_host (organizer)",
    ),
    "initial_state other event": (
        _set(("initial_state", "event_id"), "e_other_event"),
        "initial state is for event e_other_event, not e_showcase_01",
    ),
    "initial plan over venue capacity": (
        _set(("goal", "attendance_target"), 100),
        "initial plan fails occupancy_capacity",
    ),
}


def test_shipped_fixtures_load_and_resolve() -> None:
    public = load_public_scenario()
    assert ADAPTER.validate_config(public) == []
    for ref in ("dev01", "dev02", "dev04", "dev05", "dev06"):
        assert validate_case(public, load_case(ref)) == [], ref


@pytest.mark.parametrize("name", sorted(PUBLIC_MUTATIONS))
def test_broken_public_reference_is_refused_at_load(
    name: str, db: Database, scratch_public: Callable[[Json], None]
) -> None:
    mutate, expected = PUBLIC_MUTATIONS[name]
    data = _public_json()
    mutate(data)
    problems = ADAPTER.validate_config(PublicScenario.model_validate(data))
    assert any(expected in p for p in problems), problems
    scratch_public(data)
    with db.write() as conn, pytest.raises(ValueError, match="failed adapter validation"):
        create_episode(conn)
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM episodes").fetchone()["n"] == 0


def test_initial_plan_may_fail_only_evidence_dependent_checks(
    db: Database, scratch_public: Callable[[Json], None]
) -> None:
    # A projector already reported unknown at load is a scenario (the keep candidate fails
    # resource_status), not a configuration error; it still loads.
    data = _public_json()
    _by(data["resources"], "resource_id", "projector")["initial_status"] = "unknown"
    scenario = PublicScenario.model_validate(data)
    assert ADAPTER.validate_config(scenario) == []
    grant = next(g for g in scenario.authority_grants if g.grant_id == "grant_coordinator_demo")
    actor = ActorContext(
        principal_id="agent_demo",
        role="coordinator_agent",
        grant=grant,
        grant_version=1,
        grant_valid=True,
        committed_used_cents=0,
        reserved_used_cents=0,
    )
    result = ADAPTER.evaluate(
        projection.initial_snapshot(scenario),
        actor,
        EvaluationRequest(templates=("keep",)),
        "eval_0001",
    )
    keep = next(c for c in result.candidates if c.candidate_id == result.keep_candidate_id)
    assert [c.constraint_id for c in keep.checks if c.status == "failed"] == ["resource_status"]
    scratch_public(data)
    with db.write() as conn:
        assert create_episode(conn).startswith("ep_")


# ---------------------------------------------------------------------- REQ-01 private


def _status(index: int, field: str, value: str) -> Callable[[Json], None]:
    return _set(("status_model", index, field), value)


PRIVATE_MUTATIONS: dict[str, tuple[Callable[[Json], None], str]] = {
    "p_status_typo": (_status(0, "entity_id", "projecter"), "status_model[0]: unknown resource"),
    "p_status_fact_typo": (
        _status(0, "fact", "delivery_etaa"),
        "status_model[0]: projector has no queryable fact delivery_etaa",
    ),
    "p_arrival_typo": (
        _set(("world_events", 0, "entity_id"), "projecter"),
        "world_events[0]: arrival of unknown resource projecter",
    ),
    "p_script_principal_typo": (
        _set(("actor_scripts", 0, "principal_id"), "participant_facilitatr"),
        "actor_scripts[0] (participant_check_in): unknown principal participant_facilitatr",
    ),
    "p_script_resource_typo": (
        _set(("actor_scripts", 1, "resource_id"), "presentr"),
        "actor_scripts[1] (participant_check_in): unknown resource presentr",
    ),
    "p_rule_grant_typo": (
        _set(("actor_scripts", 2, "target_grant_id"), "grant_coordinator_dmo"),
        "actor_scripts[2] (organizer_authorization_rule): unknown grant grant_coordinator_dmo",
    ),
    "p_rule_resource_typo": (
        _set(("actor_scripts", 2, "resource_ids"), ["backup_projectr"]),
        "actor_scripts[2] (organizer_authorization_rule): unknown resource backup_projectr",
    ),
    "p_other_scenario": (
        _set(("scenario_id",), "dev_fixture_99"),
        "is for scenario dev_fixture_99, not dev_fixture_01",
    ),
}


@pytest.mark.parametrize("name", sorted(PRIVATE_MUTATIONS))
def test_broken_private_reference_is_refused_at_load(
    name: str, db: Database, scratch_private: Callable[[str, Json], None]
) -> None:
    mutate, expected = PRIVATE_MUTATIONS[name]
    data = _private_json()
    data["case_ref"] = name
    mutate(data)
    problems = validate_case(load_public_scenario(), PrivateCase.model_validate(data))
    assert any(expected in p for p in problems), problems
    scratch_private(name, data)
    with db.write() as conn, pytest.raises(ValueError, match=f"private case {name} failed"):
        create_episode(conn, case_ref=name)
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM episodes").fetchone()["n"] == 0


def test_run_case_refuses_a_status_typo_before_running(
    db: Database, scratch_private: Callable[[str, Json], None]
) -> None:
    # The audit's probe: this copy of dev01 used to run and report matches_expectation=True.
    data = _private_json()
    data["case_ref"] = "p_status_typo"
    _status(0, "entity_id", "projecter")(data)
    scratch_private("p_status_typo", data)
    with pytest.raises(ValueError, match="unknown resource projecter"):
        run_case(db, "p_status_typo")
    with db.read() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM episodes").fetchone()["n"] == 0
    assert run_case(db, "dev01").report.matches_expectation  # the scratch dev01 still runs


# ---------------------------------------------------------------------- REQ-03 / F3


class _StubOutcomeAdapter:
    """Returns a fixed domain outcome, built on the campus adapter's activities: shows that
    score_episode takes goal attainment and domain violations from the adapter."""

    def __init__(self, *violations: Violation) -> None:
        self.violations = violations
        self.calls: list[str] = []

    def score_outcome(self, final: EventStateView, history: EpisodeHistory) -> DomainOutcome:
        self.calls.append(final.profile_id)
        return DomainOutcome(
            activities=ADAPTER.score_outcome(final, history).activities,
            goal_attained=True,
            unmet=(),
            violations=self.violations,
        )


def test_score_episode_takes_goal_attainment_from_the_adapter(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.advance_to("16:55")
    final, history = sandbox.view(), episode_history(sandbox.db, sandbox.episode_id)
    plain = scoring.score_episode(final, history)
    real = ADAPTER.score_outcome(final, history)
    assert plain.goal_complete is False and real.goal_attained is False  # setup still running
    assert plain.activities == real.activities
    assert plain.violations == tuple(v.message for v in real.violations)

    attained = _StubOutcomeAdapter()
    monkeypatch.setattr(scoring, "adapter_for", lambda profile_id: attained)
    assert scoring.score_episode(final, history).goal_complete is True
    assert attained.calls == ["campus_showcase"]

    violated = _StubOutcomeAdapter(Violation("stub_rule", "stub_rule: injected by the adapter"))
    monkeypatch.setattr(scoring, "adapter_for", lambda profile_id: violated)
    report = scoring.score_episode(final, history)
    assert report.violations == ("stub_rule: injected by the adapter",)
    assert report.goal_complete is False  # attained, but a violation was executed


class _SpyAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def check_readiness(
        self, snapshot: Any, activity_id: str, at: datetime, *, mode: str = "execution"
    ) -> Any:
        self.calls.append((activity_id, mode))
        return ADAPTER.check_readiness(snapshot, activity_id, at, mode=mode)


def test_preview_readiness_goes_through_the_adapter(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = load_public_scenario()
    direct = projection.initial_snapshot(scenario)
    with sandbox.db.read() as conn:
        stored = build_snapshot(conn, sandbox.episode_id)
    spy = _SpyAdapter()
    profiles: list[str] = []

    def adapter_for(profile_id: str) -> _SpyAdapter:
        profiles.append(profile_id)
        return spy

    monkeypatch.setattr(projection, "adapter_for", adapter_for)
    via_spy = projection.initial_snapshot(scenario)
    not_started = [v.definition.activity_id for v in direct.activities if v.readiness]
    assert not_started == ["welcome", "demonstrations", "skills_exchange", "closing"]
    assert spy.calls == [(aid, "preview") for aid in not_started]
    assert profiles == [scenario.profile_id]
    assert via_spy == direct  # same readiness as before the routing
    spy.calls.clear()
    with sandbox.db.read() as conn:
        assert build_snapshot(conn, sandbox.episode_id) == stored  # the store path as well
    assert [mode for _, mode in spy.calls] == ["preview"] * len(not_started)


def test_store_preview_readiness_asks_the_episodes_own_profile(
    db: Database, scratch_public: Callable[[Json], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A profile other than the shipped one: the store path must not fall back to campus_showcase.
    data = _public_json()
    data["profile_id"] = "community_skills_exchange"
    scratch_public(data)
    with db.write() as conn:
        episode_id = create_episode(conn)
        assert repo.get_episode(conn, episode_id).profile_id == "community_skills_exchange"
    spy = _SpyAdapter()
    profiles: list[str] = []

    def adapter_for(profile_id: str) -> _SpyAdapter:
        profiles.append(profile_id)
        return spy

    monkeypatch.setattr(projection, "adapter_for", adapter_for)
    with db.read() as conn:
        snapshot = build_snapshot(conn, episode_id)  # planner and engine snapshots
        view = build_view(conn, episode_id, TRACE_VIEWER, visibility="audit")  # views, export
    assert profiles == ["community_skills_exchange"] * 2
    not_started = [v.definition.activity_id for v in snapshot.activities if v.readiness]
    assert not_started and spy.calls == [(aid, "preview") for aid in not_started] * 2
    assert view.profile_id == "community_skills_exchange"
    # No caller can leave the profile out any more.
    profile = inspect.signature(projection.activity_views).parameters["profile_id"]
    assert profile.default is inspect.Parameter.empty


# ---------------------------------------------------------------------- REQ-12


class _ClockRecorder:
    """Records the scenario clock at every wake; makes no tool call."""

    policy_id = "test/clock-recorder"

    def __init__(self, db: Database, episode: list[str], seen: list[datetime]) -> None:
        self.db, self.episode, self.seen = db, episode, seen

    def run(self, client: Any, max_tool_calls: int = 16) -> PolicyRunResult:
        with self.db.read() as conn:
            self.seen.append(repo.get_episode(conn, self.episode[0]).clock)
        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(), tool_calls=0
        )


def test_policy_is_not_woken_once_the_coordinator_grant_expired(
    db: Database, scratch_public: Callable[[Json], None]
) -> None:
    data = _public_json()
    _grant("grant_coordinator_demo", "expires_at", "2026-11-05T17:30:00-05:00")(data)
    scratch_public(data)
    with db.write() as conn:
        episode = [create_episode(conn)]
    seen: list[datetime] = []
    runs = tick_loop(
        db,
        PolicyHost(db, lambda: _ClockRecorder(db, episode, seen)),
        episode[0],
        minutes=None,
        run_policy=True,
        actors=None,
    )
    assert runs and seen and max(seen) < at("17:30")
    with db.read() as conn:
        late = [t for t in repo.transitions(conn, episode[0]) if t.at >= at("17:30")]
    # Public state kept changing after the expiry (starts, failures, close): only the expired
    # grant kept the policy asleep.
    assert {t.cause_kind for t in late} >= {"grant_expired", "event_closed"}


def test_policy_is_not_woken_at_the_event_close(db: Database) -> None:
    with db.write() as conn:
        episode = [create_episode(conn, case_ref="dev01")]
    seen: list[datetime] = []
    tick_loop(
        db,
        PolicyHost(db, lambda: _ClockRecorder(db, episode, seen)),
        episode[0],
        minutes=None,
        run_policy=True,
        actors=None,
    )
    assert seen and max(seen) < at("18:00")
    with db.read() as conn:
        assert repo.get_episode(conn, episode[0]).clock == at("18:00")
        assert repo.get_flag(conn, episode[0], "event_closed")


# ---------------------------------------------------------------------- F9


def _refused(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...], message: str) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=message):
        conn.execute(sql, params)


def test_history_tables_refuse_deletes_and_edits(sandbox: Sandbox) -> None:
    sandbox.query()  # a status_tool observation, besides the fixture notice
    sandbox.evaluate()  # stored candidates
    assert sandbox.hold_backup("h").receipt.status == "applied"  # a receipt
    ep = (sandbox.episode_id,)
    conn = sandbox.raw()
    try:
        for table, message in (
            ("receipts", "receipts are durable and immutable"),
            ("observations", "observations are immutable"),
            ("candidates", "stored candidates are immutable"),
            ("plans", "plan history is append-only"),
            ("goals", "goal history is append-only"),
            ("activities", "activities are never deleted"),
        ):
            assert sandbox.count(table) > 0, table
            _refused(conn, f"DELETE FROM {table} WHERE episode_id = ?", ep, message)
        # Moving setup by rewriting the stored plan is refused, like any plan or goal edit.
        _refused(
            conn,
            "UPDATE plans SET assignments_json = replace(assignments_json, '21:30:00Z',"
            " '21:45:00Z') WHERE episode_id = ?",
            ep,
            "plan history is append-only",
        )
        _refused(conn, "UPDATE goals SET body_json = '{}' WHERE episode_id = ?", ep, "append-only")
        _refused(
            conn,
            "UPDATE activities SET definition_json = '{}' WHERE episode_id = ?",
            ep,
            "an activity definition is fixed",
        )
    finally:
        conn.close()
    assert "0003_history_guards" in sandbox.db.schema_versions()


def _with_history(sandbox: Sandbox) -> Sandbox:
    """dev01 with a row in every guarded table: the fixture's plan v1, goal v1, setup's
    activity_events row and notice, a status observation, candidates, and a hold (its receipt and
    ledger row) that has been released, so the hold is terminal."""
    sandbox.query()
    sandbox.evaluate()
    assert sandbox.hold_backup("h").receipt.status == "applied"
    released = sandbox.agent.call(
        "release_hold",
        arguments={"hold_id": "hold_0001", "reason": "test"},
        idempotency_key="rel",
        expected_revision=sandbox.revision(),
    )
    assert released.receipt is not None and released.receipt.status == "applied"
    return sandbox


# table -> (column rewritten in the first row, its new value, the guard's refusal)
REPLACE_PROBES: dict[str, tuple[str, Callable[[Any], Any], str]] = {
    "ledger": ("committed_delta_cents", lambda v: v + 1000, "ledger is append-only"),
    "receipts": ("body_json", lambda v: "{}", "receipts are durable and immutable"),
    "plans": (  # plan v1: the audit's "move setup" edit, done by REPLACE instead of UPDATE
        "assignments_json",
        lambda v: v.replace("21:30:00Z", "21:45:00Z"),
        "plan history is append-only",
    ),
    "activity_events": ("at", lambda v: "2026-11-05T21:45:00Z", "activity history is append-only"),
    "observations": ("body_json", lambda v: "{}", "observations are immutable"),
    "candidates": ("body_json", lambda v: "{}", "stored candidates are immutable"),
    "goals": ("body_json", lambda v: "{}", "goal history is append-only"),
    "activities": ("definition_json", lambda v: "{}", "activities are never deleted"),
    "holds": ("status", lambda v: "active", "holds are never deleted"),  # revive a released hold
}


@pytest.mark.parametrize("table", sorted(REPLACE_PROBES))
def test_replace_cannot_rewrite_a_guarded_row(sandbox: Sandbox, table: str) -> None:
    # REPLACE deletes the conflicting row; with recursive_triggers on, that delete fires the
    # table's DELETE guard (0001 or 0003), so the row cannot be rewritten this way either.
    column, rewrite, message = REPLACE_PROBES[table]
    _with_history(sandbox)
    first = f"SELECT rowid, * FROM {table} WHERE episode_id = ? ORDER BY rowid LIMIT 1"
    conn = sandbox.raw()
    try:
        before = dict(conn.execute(first, (sandbox.episode_id,)).fetchone())
        row = {k: v for k, v in before.items() if k != "rowid"}
        tampered = {**row, column: rewrite(row[column])}
        assert tampered != row, table
        cols, marks = ", ".join(tampered), ", ".join("?" * len(tampered))
        for verb in ("INSERT OR REPLACE", "REPLACE"):
            _refused(
                conn,
                f"{verb} INTO {table} ({cols}) VALUES ({marks})",
                (*tampered.values(),),
                message,
            )
        assert dict(conn.execute(first, (sandbox.episode_id,)).fetchone()) == before
    finally:
        conn.close()
    if table == "holds":
        assert sandbox.view().holds[0].status == "released"


def test_every_store_connection_turns_on_recursive_triggers(sandbox: Sandbox) -> None:
    def on(conn: sqlite3.Connection) -> bool:
        return bool(conn.execute("PRAGMA recursive_triggers").fetchone()[0])

    raw = sandbox.raw()
    try:
        assert on(raw)
    finally:
        raw.close()
    with sandbox.db.read() as conn:
        assert on(conn)
    with sandbox.db.write() as conn:
        assert on(conn)
    # The limit the 0003 header states: a connection that leaves the pragma off (a bare sqlite3
    # shell) still gets a REPLACE through, so the refusals above are the pragma's doing.
    bare = sqlite3.connect(sandbox.db.path, isolation_level=None)
    try:
        assert not bare.execute("PRAGMA recursive_triggers").fetchone()[0]
        bare.execute("BEGIN IMMEDIATE")
        replaced = bare.execute(
            "INSERT OR REPLACE INTO plans SELECT * FROM plans"
            " WHERE episode_id = ? AND plan_version = 1",
            (sandbox.episode_id,),
        )
        assert replaced.rowcount == 1
        bare.execute("ROLLBACK")
    finally:
        bare.close()


def test_dev02_run_reset_and_restart_pass_the_guards(tmp_path: Path) -> None:
    # Every app write (hold, commit, apply_plan, the clock engine, the revision_snapshots upsert)
    # still works with recursive_triggers on, across a reset and a restart on the same file.
    var = tmp_path / "var"
    path = var / "plan_b.sqlite3"
    first = run_case(Database(path), "dev02")
    assert first.report.matches_expectation and first.report.committed_cents == 3500
    assert first.report.applied_plans == 1 and first.report.violations == ()
    with Database(path).write() as conn:
        reset = create_episode(conn, case_ref="dev02")  # what the moderator reset does
        assert repo.get_episode(conn, first.episode_id).status == "closed"
    restarted = Database(path)  # a new process: nothing is left to migrate
    assert restarted.migrate() == []
    assert restarted.schema_versions() == [
        "0001_initial",
        "0002_scheduled_actions",
        "0003_history_guards",
        "0004_consumable_stock",
    ]
    second = run_case(restarted, "dev02")
    assert second.report.matches_expectation and second.report.committed_cents == 3500
    with restarted.write() as conn:
        assert repo.get_episode(conn, reset).status == "closed"
        # Capturing the same revision twice takes the upsert's DO UPDATE path: still one row.
        capture_snapshot(conn, second.episode_id)
        capture_snapshot(conn, second.episode_id)
        rows = conn.execute(
            "SELECT COUNT(*) AS n, COUNT(DISTINCT revision) AS d FROM revision_snapshots"
            " WHERE episode_id = ?",
            (second.episode_id,),
        ).fetchone()
        assert rows["n"] == rows["d"] > 1
    # The HTTP app on the restarted file: a moderator reset and an export both succeed.
    api = TestClient(
        create_app(path, var_dir=var, moderator_code=CODE, web_dist=tmp_path / "no_dist")
    )
    mod = _moderator(api)
    reset_http = api.post("/api/moderator/episodes", json={"case_ref": "dev02"}, headers=_auth(mod))
    assert reset_http.status_code == 200, reset_http.text
    assert api.post("/api/moderator/policy/run", json={}, headers=_auth(mod)).status_code == 200
    assert api.post("/api/moderator/export", headers=_auth(mod)).status_code == 200


def _set_lifecycle(conn: sqlite3.Connection, episode_id: str, activity: str, state: str) -> int:
    cur = conn.execute(
        "UPDATE activities SET lifecycle = ? WHERE episode_id = ? AND activity_id = ?",
        (state, episode_id, activity),
    )
    return cur.rowcount


def test_lifecycle_moves_only_forward(sandbox: Sandbox) -> None:
    ep = sandbox.episode_id
    conn = sandbox.raw()
    try:
        # demonstrations is planned: the audit's probe skipped started; ready cannot skip it either.
        _refused(
            conn,
            "UPDATE activities SET lifecycle = 'completed'"
            " WHERE episode_id = ? AND activity_id = 'demonstrations'",
            (ep,),
            "illegal lifecycle transition",
        )
        assert _set_lifecycle(conn, ep, "demonstrations", "ready") == 1
        _refused(
            conn,
            "UPDATE activities SET lifecycle = 'completed'"
            " WHERE episode_id = ? AND activity_id = 'demonstrations'",
            (ep,),
            "illegal lifecycle transition",
        )
        assert _set_lifecycle(conn, ep, "demonstrations", "planned") == 1
        assert _set_lifecycle(conn, ep, "demonstrations", "started") == 1
        assert _set_lifecycle(conn, ep, "demonstrations", "completed") == 1
        assert _set_lifecycle(conn, ep, "closing", "canceled") == 1
        for state in ("failed", "canceled", "completed", "started"):
            with pytest.raises(sqlite3.IntegrityError, match="lifecycle transition"):
                _set_lifecycle(conn, ep, "closing", state)
        # setup started at load; it cannot start again or go back (0001 and 0003 together).
        for state in ("started", "planned", "canceled"):
            with pytest.raises(sqlite3.IntegrityError, match="lifecycle transition"):
                _set_lifecycle(conn, ep, "setup", state)
    finally:
        conn.close()


def test_legitimate_history_writes_still_work(sandbox: Sandbox) -> None:
    # apply_plan inserts plan v2, the clock engine records ready/started/completed/failed, and
    # an organizer goal change inserts goal v2: all of it passes the triggers.
    sandbox.query()
    env = sandbox.evaluate()
    assert sandbox.apply(sandbox.candidate(env, "Swap"), env, "k").receipt.status == "applied"
    changed = sandbox.organizer.call(
        "update_goal",
        arguments={"preference_preset": "preserve_order", "reason": "test"},
        idempotency_key="goal-2",
        expected_revision=sandbox.revision(),
        expected_goal_version=1,
    )
    assert changed.receipt is not None and changed.receipt.status == "applied", changed
    sandbox.advance_to("18:00")
    view = sandbox.view()
    assert [p.plan_version for p in view.plan_history] == [1, 2]
    assert [g.version for g in view.goal_history] == [1, 2]
    assert {a.lifecycle for a in view.activities} <= {"completed", "failed"}
    states = {e.state for a in view.activities for e in a.history}
    assert {"started", "completed"} <= states
