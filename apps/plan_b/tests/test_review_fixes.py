"""Regression tests for verified findings of the independent Wave 1 review (backend core).

Each test fails on the behavior the review reproduced and passes with the fix.
"""

from __future__ import annotations

import json
import stat
import threading
import time
from pathlib import Path

import pytest

from plan_b.api.app import load_moderator_code
from plan_b.domain.models import (
    ParticipantCheckInScript,
    PolicyDecision,
    PolicyRunResult,
)
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import ScriptedActors, tick_loop
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.engine import advance_to
from plan_b.store.episodes import create_episode
from plan_b.store.sessions import AuthError, issue_session
from plan_b.tools import handlers
from plan_b.tools.executor import execute
from tests.conftest import Sandbox, at

# --- clock_execution-01: the latest check-in is the person's declaration -------------------


def test_narrower_later_check_in_supersedes_earlier(sandbox: Sandbox) -> None:
    sandbox.check_in("participant_presenter", "presenter", "p1")  # 16:40 until 18:00
    sandbox.advance_to("16:45")
    narrower = sandbox.client("participant_presenter").call(
        "check_in",
        arguments={
            "resource_id": "presenter",
            "available": {"start": at("16:45").isoformat(), "end": at("17:15").isoformat()},
        },
        idempotency_key="p2",
    )
    assert narrower.receipt.status == "applied"
    sandbox.advance_to("17:10")
    demos = next(
        a for a in sandbox.view().activities if a.definition.activity_id == "demonstrations"
    )
    assert demos.lifecycle == "failed"
    assert any("latest check-in" in r and "presenter" in r for r in demos.history[-1].reasons)


# --- clock_execution-02: the steward refuses a hold the world says is unavailable ----------


def test_hold_refused_when_steward_reports_resource_unavailable(make_sandbox) -> None:  # noqa: ANN001
    sb = make_sandbox("dev05")  # backup committed elsewhere in the hidden world
    res = sb.hold_backup("h")
    assert res.receipt.status == "rejected" and res.receipt.error_code == "RESOURCE_UNAVAILABLE"
    assert sb.count("holds") == 0 and sb.ledger() == (0, 0)
    assert "backup_desk_record_8" not in res.model_dump_json()  # no private record leaks
    assert "committed to another event" not in res.model_dump_json()


def test_hold_allowed_when_steward_confirms(sandbox: Sandbox) -> None:
    assert sandbox.hold_backup("h").receipt.status == "applied"


# --- clock_execution-05 / authority_privacy-4: no clock movement without authority ---------


def test_revoked_grant_moves_no_clock_and_own_receipts_stay_readable(sandbox: Sandbox) -> None:
    held = sandbox.hold_backup("h-before")
    assert held.receipt.status == "applied"
    sandbox.organizer.call(
        "update_grant",
        arguments={"target_grant_id": "grant_coordinator_demo", "revoke": True, "reason": "test"},
        idempotency_key="rv",
        expected_revision=sandbox.revision(),
    )
    clock = sandbox.clock()
    for _ in range(3):
        q = sandbox.query()
        assert q.error.code == "GRANT_REVOKED"
    h = sandbox.hold_backup("h-after")
    assert h.receipt.status == "rejected" and h.receipt.error_code == "GRANT_REVOKED"
    assert sandbox.clock() == clock  # a principal with no authority cannot move shared time
    lookup = sandbox.agent.call("get_action_receipt", arguments={"idempotency_key": "h-before"})
    assert lookup.status == "succeeded" and lookup.data["lookup_status"] == "found"


# --- clock_execution-04 / -06: scheduled actors act at their exact instants -----------------


def test_scheduled_check_in_runs_inside_another_callers_tool_duration(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    script = ParticipantCheckInScript(
        kind="participant_check_in",
        at=at("16:41"),
        principal_id="participant_facilitator",
        resource_id="facilitator",
        available_start=at("16:41"),
        available_end=at("18:00"),
    )
    actors = ScriptedActors(db, sb.episode_id, (script,))
    actors.schedule_initial()
    sb.query()  # 16:40 -> 16:42; the 16:41 check-in happens during this duration
    checkins = [c for c in sb.view().checkins if c.resource_id == "facilitator"]
    assert len(checkins) == 1 and checkins[0].at == at("16:41")
    assert actors.log[0]["executed_at"] == "2026-11-05T21:41:00Z"
    assert actors.log[0]["receipt_status"] == "applied"


def test_scheduled_check_in_at_start_instant_counts_like_an_arrival(db: Database) -> None:
    sb = Sandbox(db, "dev04")  # projector arrives 16:58; demonstrations starts 17:10
    script = ParticipantCheckInScript(
        kind="participant_check_in",
        at=at("17:10"),
        principal_id="participant_presenter",
        resource_id="presenter",
        available_start=at("17:10"),
        available_end=at("18:00"),
    )
    ScriptedActors(db, sb.episode_id, (script,)).schedule_initial()
    sb.advance_to("17:11")
    demos = next(a for a in sb.view().activities if a.definition.activity_id == "demonstrations")
    assert demos.lifecycle == "started", demos.history[-1].reasons


# --- transactions-01: sub-minute arguments are a 400, unexpected errors keep evidence ------


def test_sub_minute_argument_is_rejected_with_evidence(sandbox: Sandbox) -> None:
    token = sandbox.client("participant_facilitator")._token  # noqa: SLF001
    body = {
        "tool": "check_in",
        "event_id": "e_showcase_01",
        "idempotency_key": "s1",
        "arguments": {
            "resource_id": "facilitator",
            "available": {"start": "2026-11-05T21:40:00Z", "end": "2026-11-05T21:40:00.500Z"},
        },
    }
    status, env = execute(sandbox.db, token, "check_in", body)
    assert status == 400 and env.error.code == "INVALID_REQUEST"
    assert any(a.error_code == "INVALID_REQUEST" for a in sandbox.view().attempts)
    assert sandbox.count("checkins") == 1


def test_unexpected_handler_error_rolls_back_and_is_recorded(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = handlers.HANDLERS["hold_resource"]

    def explode(ctx):  # noqa: ANN001, ANN202
        original(ctx)  # performs the whole hold, then fails
        raise RuntimeError("simulated defect")

    monkeypatch.setitem(handlers.HANDLERS, "hold_resource", explode)
    res = sandbox.hold_backup("boom")
    assert res.status == "rejected" and res.error.code == "INTERNAL_ERROR"
    assert sandbox.count("holds") == 0 and sandbox.ledger() == (0, 0) and sandbox.revision() == 3
    assert sandbox.count("tool_calls", "error_code = 'INTERNAL_ERROR'") == 1


# --- transactions-02: reset never deadlocks with a policy session being issued ---------------


def test_policy_host_does_not_hold_its_lock_while_waiting_for_sqlite(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    host = PolicyHost(db)
    conn = db.connect()
    conn.execute("BEGIN IMMEDIATE")  # another writer holds the SQLite lock
    worker = threading.Thread(target=lambda: host.client(sb.episode_id))
    worker.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    host.forget(sb.episode_id)  # must not wait for the SQLite lock
    assert time.monotonic() - t0 < 1.0
    conn.execute("ROLLBACK")
    conn.close()
    worker.join(timeout=10)
    assert not worker.is_alive()


# --- authority_privacy-1: decision ids are unique across policy instances --------------------


class _OneDecisionPolicy:
    policy_id = "test/1"

    def run(self, client, max_tool_calls: int = 16) -> PolicyRunResult:  # noqa: ANN001
        env = client.call("get_event_state", arguments={})
        d = PolicyDecision(
            decision_id="dec_0001",
            policy_id=self.policy_id,
            at=env.scenario_time,
            revision=env.revision,
            kind="keep",
            summary="kept",
        )
        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(d,), tool_calls=1
        )


def test_policy_restart_cannot_collide_decision_ids(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    PolicyHost(db, _OneDecisionPolicy).run(sb.episode_id)
    PolicyHost(db, _OneDecisionPolicy).run(sb.episode_id)  # a restarted server: fresh instance
    ids = [d.decision_id for d in sb.view().decisions]
    assert ids == ["dec_0001", "dec_0002"]


# --- authority_privacy-2: a reset stops runs on the closed episode ---------------------------


def test_closed_episode_cannot_advance_or_issue_sessions(db: Database) -> None:
    old = Sandbox(db, "dev01")
    with db.write() as conn:
        create_episode(conn, case_ref="dev01")  # reset closes `old`
    runs = tick_loop(db, PolicyHost(db), old.episode_id, minutes=30, run_policy=True, actors=None)
    assert runs == [] and old.clock() == at("16:40")
    with db.write() as conn, pytest.raises(ValueError):
        advance_to(conn, old.episode_id, at("16:50"))
    with db.write() as conn, pytest.raises(AuthError) as exc:
        issue_session(conn, old.episode_id, "agent_demo")
    assert exc.value.code == "EPISODE_CLOSED"


# --- authority_privacy-5 / -7: logged bodies are sanitized and projections robust ------------


def test_unvalidated_body_values_are_not_logged(sandbox: Sandbox) -> None:
    token = sandbox.client("participant_facilitator")._token  # noqa: SLF001
    body = {
        "tool": "check_in",
        "event_id": "e_showcase_01",
        "idempotency_key": "x",
        "session_token": "SECRET-VALUE-123",
        "arguments": {"resource_id": "facilitator"},
    }
    status, _ = execute(sandbox.db, token, "check_in", body)
    assert status == 400
    with sandbox.db.read() as conn:
        logged = [r["request_json"] for r in conn.execute("SELECT request_json FROM tool_calls")]
    assert logged and all("SECRET-VALUE-123" not in r for r in logged)
    assert any("session_token" in r for r in logged)  # the field name is evidence


def test_malformed_status_query_is_an_envelope_not_a_500(sandbox: Sandbox) -> None:
    body = {
        "tool": "query_status",
        "event_id": "e_showcase_01",
        "arguments": {"entity_id": 7, "fact": []},
    }
    status, env = execute(sandbox.db, sandbox.agent._token, "query_status", body)  # noqa: SLF001
    assert status == 400 and env.error.code == "INVALID_REQUEST"
    assert sandbox.view().status_checks[-1].entity_id is None  # projected safely


# --- authority_privacy-6: a frame keeps the time its revision came into being ----------------


def test_snapshot_time_is_revision_creation_time(sandbox: Sandbox) -> None:
    sandbox.advance_to("16:45")
    sandbox.evaluate()  # refreshes the revision-3 snapshot at 16:45
    with sandbox.db.read() as conn:
        row = conn.execute(
            "SELECT at, view_json FROM revision_snapshots WHERE episode_id = ? AND revision = 3",
            (sandbox.episode_id,),
        ).fetchone()
    assert row["at"] == "2026-11-05T21:40:00Z"
    assert json.loads(row["view_json"])["latest_evaluation"] is not None


# --- authority_privacy-8: reset-closed sessions report EPISODE_CLOSED -----------------------


def test_reset_session_reports_episode_closed(db: Database) -> None:
    old = Sandbox(db, "dev01")
    token = old.agent._token  # noqa: SLF001
    with db.write() as conn:
        create_episode(conn, case_ref="dev01")
    status, env = execute(
        db,
        token,
        "get_event_state",
        {"tool": "get_event_state", "event_id": "e_showcase_01", "arguments": {}},
    )
    assert status == 401 and env.error.code == "EPISODE_CLOSED"


# --- authority_privacy-9: the moderator code file is owner-only from creation --------------


def test_moderator_code_file_is_owner_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLAN_B_MODERATOR_CODE", raising=False)
    var = tmp_path / "var"
    code = load_moderator_code(var)
    path = var / "moderator_code.txt"
    assert code and stat.S_IMODE(path.stat().st_mode) == 0o600
    path.chmod(0o644)
    assert load_moderator_code(var) == code and stat.S_IMODE(path.stat().st_mode) == 0o600


# --- planner_policy-05: an exhausted tool budget is re-woken on the next tick ----------------


class _BudgetPolicy:
    policy_id = "test/budget"

    def __init__(self) -> None:
        self.runs = 0

    def run(self, client, max_tool_calls: int = 16) -> PolicyRunResult:  # noqa: ANN001
        self.runs += 1
        client.call("get_event_state", arguments={})
        status = "budget_exhausted" if self.runs == 1 else "waiting"
        return PolicyRunResult(policy_id=self.policy_id, status=status, decisions=(), tool_calls=1)


def test_budget_exhausted_policy_is_rewoken(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    policy = _BudgetPolicy()
    tick_loop(
        db, PolicyHost(db, lambda: policy), sb.episode_id, minutes=2, run_policy=True, actors=None
    )
    assert policy.runs >= 2


def test_scheduled_actions_are_absent_from_public_views(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    script = ParticipantCheckInScript(
        kind="participant_check_in",
        at=at("17:20"),
        principal_id="participant_presenter",
        resource_id="presenter",
        available_start=at("17:20"),
        available_end=at("18:00"),
    )
    ScriptedActors(db, sb.episode_id, (script,)).schedule_initial()
    text = sb.view().model_dump_json()
    assert "act_001" not in text and "2026-11-05T22:20:00Z" not in text  # the future check-in
    with db.read() as conn:
        assert repo.get_episode(conn, sb.episode_id).revision == 3


# --- second-round findings from the re-verification of the fixes ---------------------------


class _ResettingPolicy:
    """Resets the episode in the middle of its run, then reports a decision."""

    policy_id = "test/reset"

    def __init__(self, db: Database) -> None:
        self.db = db

    def run(self, client, max_tool_calls: int = 16) -> PolicyRunResult:  # noqa: ANN001
        env = client.call("get_event_state", arguments={})
        with self.db.write() as conn:
            create_episode(conn, case_ref="dev01")
        d = PolicyDecision(
            decision_id="dec_0001",
            policy_id=self.policy_id,
            at=env.scenario_time,
            revision=env.revision,
            kind="keep",
            summary="kept",
        )
        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(d,), tool_calls=1
        )


def test_reset_during_a_policy_run_writes_nothing_into_the_closed_episode(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    result = PolicyHost(db, lambda: _ResettingPolicy(db)).run(sb.episode_id)
    assert result.decisions == ()
    assert sb.view().decisions == () and sb.view().episode_status == "closed"


def test_policy_run_after_reset_is_a_clean_stop(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    with db.write() as conn:
        create_episode(conn, case_ref="dev01")
    result = PolicyHost(db).run(sb.episode_id)  # no cached client: session issue is refused
    assert result.status == "stopped" and "not run" in result.note


def test_returned_decision_ids_are_the_stored_ids(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    PolicyHost(db, _OneDecisionPolicy).run(sb.episode_id)
    second = PolicyHost(db, _OneDecisionPolicy).run(sb.episode_id)
    assert [d.decision_id for d in second.decisions] == ["dec_0002"]
    assert [d.decision_id for d in sb.view().decisions] == ["dec_0001", "dec_0002"]


class _QueryOncePolicy:
    policy_id = "test/query-once"

    def __init__(self) -> None:
        self.runs: list[str] = []

    def run(self, client, max_tool_calls: int = 16) -> PolicyRunResult:  # noqa: ANN001
        env = client.call("get_event_state", arguments={})
        self.runs.append(env.data["clock"])
        if len(self.runs) == 1:
            client.call(
                "query_status", arguments={"entity_id": "projector", "fact": "delivery_eta"}
            )
        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(), tool_calls=2
        )


def test_actor_action_inside_the_policys_own_tool_call_wakes_it(db: Database) -> None:
    from plan_b.domain.models import ParticipantObservationScript

    sb = Sandbox(db, "dev01")
    script = ParticipantObservationScript(
        kind="participant_observation",
        at=at("16:41"),
        principal_id="participant_facilitator",
        entity_id=None,
        text="I am here early.",
        client_record_id="fac-early",
    )
    ScriptedActors(db, sb.episode_id, (script,)).schedule_initial()
    policy = _QueryOncePolicy()
    tick_loop(
        db, PolicyHost(db, lambda: policy), sb.episode_id, minutes=3, run_policy=True, actors=None
    )
    # First run at 16:40 (its query spans 16:40-16:42 and the observation lands at 16:41);
    # the next tick must wake it again instead of waiting for an unrelated change.
    assert policy.runs[:2] == ["2026-11-05T21:40:00Z", "2026-11-05T21:43:00Z"]


def test_action_due_at_the_starting_clock_runs_at_that_instant(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    script = ParticipantCheckInScript(
        kind="participant_check_in",
        at=at("16:40"),
        principal_id="participant_facilitator",
        resource_id="facilitator",
        available_start=at("16:40"),
        available_end=at("18:00"),
    )
    ScriptedActors(db, sb.episode_id, (script,)).schedule_initial()
    checkins = [c for c in sb.view().checkins if c.resource_id == "facilitator"]
    assert len(checkins) == 1 and checkins[0].at == at("16:40") and sb.clock() == at("16:40")


def test_old_join_code_after_reset_reports_episode_closed(db: Database) -> None:
    from plan_b.store.sessions import issue_join_code, redeem_join_code

    sb = Sandbox(db, "dev01")
    with db.write() as conn:
        code = issue_join_code(conn, sb.episode_id, "participant_facilitator")
        create_episode(conn, case_ref="dev01")
    with db.write() as conn, pytest.raises(AuthError) as exc:
        redeem_join_code(conn, code)
    assert exc.value.code == "EPISODE_CLOSED"


def test_out_of_range_time_is_a_400_not_a_500(sandbox: Sandbox) -> None:
    token = sandbox.client("participant_facilitator")._token  # noqa: SLF001
    body = {
        "tool": "submit_observation",
        "event_id": "e_showcase_01",
        "idempotency_key": "far",
        "arguments": {"text": "x", "observed_at": "9999-12-31T23:59:00-05:00"},
    }
    status, env = execute(sandbox.db, token, "submit_observation", body)
    assert status == 400 and env.error.code == "INVALID_REQUEST"


class _IncompletePolicy:
    policy_id = "test/incomplete"

    def __init__(self) -> None:
        self.runs = 0

    def run(self, client, max_tool_calls: int = 16) -> PolicyRunResult:  # noqa: ANN001
        self.runs += 1
        client.call("get_event_state", arguments={})
        return PolicyRunResult(
            policy_id=self.policy_id,
            status="waiting",
            decisions=(),
            tool_calls=1,
            incomplete=self.runs == 1,
        )


def test_incomplete_policy_run_is_rewoken(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    policy = _IncompletePolicy()
    tick_loop(
        db, PolicyHost(db, lambda: policy), sb.episode_id, minutes=2, run_policy=True, actors=None
    )
    assert policy.runs >= 2


_DELAY = "projector delivery may be about 25 minutes later than the promised 5 p.m. arrival"


@pytest.mark.parametrize(
    ("text", "asserted", "verify"),
    [
        # Whole supported forms are claims.
        ("Order P17 has been cancelled.", True, None),
        (f"Our {_DELAY}.", True, None),
        # Genuine reports with extra clauses are never parsed partially: verification only
        # (by order reference), or nothing when no resource is identified unambiguously.
        ("Order P17 was cancelled and will not be delivered today.", False, "projector"),
        ("Order P17 was cancelled because the van could not reach campus.", False, "projector"),
        ("Order P17 was cancelled, we may send a replacement later.", False, "projector"),
        ("Order P17 was cancelled because of a depot error.", False, "projector"),
        (f"Our {_DELAY} because the van cannot reach campus.", False, "projector"),
        (f"FYI {_DELAY}.", False, "projector"),
        # Non-asserted forms, including the round-2 messages that clause scoping asserted.
        ("Order P17 has not been cancelled.", False, "projector"),
        ("If order P17 is cancelled we will let you know.", False, "projector"),
        ("Rumours that order P17 was cancelled are false.", False, "projector"),
        ("We could not confirm whether order P17 was cancelled.", False, "projector"),
        ("If the van breaks down, order P17 will be cancelled.", False, "projector"),
        ("Unless we find another van, order P17 will be cancelled.", False, "projector"),
        ("Order P17 will be cancelled, unless payment arrives by noon.", False, "projector"),
        ("If you want, order P17 can be cancelled.", False, "projector"),
        ("In the event of a breakdown, order P17 will be cancelled.", False, "projector"),
        ("Order P17 was cancelled, but not anymore.", False, "projector"),
        ("Order P17 was cancelled though that was an error on our side.", False, "projector"),
        ("Order P17 was cancelled, possibly.", False, "projector"),
        (f"In case of heavy traffic, our {_DELAY}.", False, "projector"),
        (f"If traffic is bad, our {_DELAY}.", False, "projector"),
        (f"Our {_DELAY}, if the truck is held up at the depot.", False, "projector"),
        (f"Earlier we said the {_DELAY}, but that is no longer the case.", False, "projector"),
        (
            "Order P17 was showing as cancelled on our system this morning, but that turned out "
            "to be a sync error. It's fixed now and your delivery is going ahead.",
            False,
            "projector",
        ),
    ],
)
def test_only_whole_supported_forms_are_asserted(
    text: str, asserted: bool, verify: str | None
) -> None:
    from datetime import date

    from plan_b.domain.fixtures import load_public_scenario
    from plan_b.domain.models import Observation, ObservationRecord, TimeWindow
    from plan_b.domain.projection import initial_snapshot
    from plan_b.evaluation.policies.parser import interpret_observation

    snap = initial_snapshot(load_public_scenario())
    t = at("16:40")
    obs = Observation(
        observation_id="o1",
        event_id="e_showcase_01",
        entity_id="e_showcase_01",
        kind="notice",
        source_id="delivery_contact",
        source_record_id="r1",
        correlation_group="g",
        observed_at=t,
        received_at=t,
        valid_window=TimeWindow(start=t, end=at("18:00")),
        authority_scope="self_report",
        text=text,
        supersedes=(),
    )
    rec = ObservationRecord(
        observation=obs, channel="scenario_delivery", submitted_by=None, revision_after=3
    )
    interp = interpret_observation(
        rec,
        resources=snap.resources,
        event_date=date(2026, 11, 5),
        timezone="America/New_York",
        goal=snap.goal,
        event_id="e_showcase_01",
    )
    assert interp.applicable is asserted, interp.reasons
    assert interp.verify_subject_id == verify, interp.reasons
    if asserted:
        assert interp.subject_id == "projector"
    else:
        assert interp.change_kind == "unresolved" and interp.unresolved_fields == ("wording",)
