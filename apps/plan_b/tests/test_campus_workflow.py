"""Clock, lifecycle, readiness and execution semantics on the campus fixture."""

from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import Sandbox, at


def _lifecycle(sb: Sandbox) -> dict[str, str]:
    return {a.definition.activity_id: a.lifecycle for a in sb.view().activities}


def _apply_swap(sb: Sandbox) -> None:
    sb.query()
    env = sb.evaluate()
    res = sb.apply(sb.candidate(env, "Swap"), env, "k-swap")
    assert res.receipt.status == "applied"


def test_setup_started_history_is_loaded_and_immutable(sandbox: Sandbox) -> None:
    v = sandbox.view()
    setup = next(a for a in v.activities if a.definition.activity_id == "setup")
    assert setup.lifecycle == "started" and setup.history[0].at == at("16:30")
    sandbox.hold_backup("h")  # gives the ledger a row to protect
    conn = sandbox.raw()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE activities SET lifecycle = 'planned'"
                " WHERE episode_id = ? AND activity_id = 'setup'",
                (sandbox.episode_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE activity_events SET at = 'x' WHERE episode_id = ?", (sandbox.episode_id,)
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM ledger WHERE episode_id = ?", (sandbox.episode_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE receipts SET status = 'applied' WHERE episode_id = ?", (sandbox.episode_id,)
            )

    finally:
        conn.close()


def test_advancing_processes_intermediate_events_in_order(sandbox: Sandbox) -> None:
    sandbox.check_in("participant_presenter", "presenter", "p")
    sandbox.check_in("participant_facilitator", "facilitator", "f")
    sandbox.advance_to("17:15")  # one call crosses 16:50, 17:00, 17:10
    tr = [(t.cause_kind, t.cause_ref, t.at) for t in sandbox.view().transitions]
    kinds = [(k, r) for k, r, _ in tr]
    i_setup = kinds.index(("activity_completed", "setup"))
    i_welcome_start = kinds.index(("activity_started", "welcome"))
    i_welcome_done = kinds.index(("activity_completed", "welcome"))
    i_demo = kinds.index(("activity_failed", "demonstrations"))
    assert i_setup < i_welcome_start < i_welcome_done < i_demo
    # Equal timestamp 17:10: welcome completes before the next activity's start is judged.
    assert tr[i_welcome_done][2] == tr[i_demo][2] == at("17:10")
    revisions = [t.revision for t in sandbox.view().transitions]
    assert revisions == sorted(revisions) and len(set(revisions)) == len(revisions)


def test_eta_alone_cannot_start_demonstrations(sandbox: Sandbox) -> None:
    sandbox.query()  # reported ETA 17:25, but the plan keeps demonstrations at 17:10
    sandbox.check_in("participant_presenter", "presenter", "p")
    sandbox.advance_to("17:10")
    demos = next(
        a for a in sandbox.view().activities if a.definition.activity_id == "demonstrations"
    )
    assert demos.lifecycle == "failed"
    assert any("projector not yet observed" in r for r in demos.history[-1].reasons)


def test_missing_participant_readiness_prevents_execution(sandbox: Sandbox) -> None:
    _apply_swap(sandbox)
    sandbox.check_in("participant_presenter", "presenter", "p")
    sandbox.advance_to("17:10")  # facilitator never checked in
    life = _lifecycle(sandbox)
    assert life["skills_exchange"] == "failed"
    skills = next(
        a for a in sandbox.view().activities if a.definition.activity_id == "skills_exchange"
    )
    assert any("facilitator has not checked in" in r for r in skills.history[-1].reasons)
    sandbox.advance_to("18:00")
    assert _lifecycle(sandbox)["closing"] == "failed"  # predecessor never completed


def test_check_in_marks_activity_ready_from_evidence(sandbox: Sandbox) -> None:
    _apply_swap(sandbox)
    assert _lifecycle(sandbox)["skills_exchange"] == "planned"
    sandbox.check_in("participant_facilitator", "facilitator", "f")
    skills = next(
        a for a in sandbox.view().activities if a.definition.activity_id == "skills_exchange"
    )
    assert skills.lifecycle == "ready"
    assert skills.readiness is not None and skills.readiness.pending  # welcome still due


def test_genuine_disruption_recovers_through_state_transitions(sandbox: Sandbox) -> None:
    _apply_swap(sandbox)
    sandbox.advance_to("17:05")
    sandbox.check_in("participant_facilitator", "facilitator", "f")
    sandbox.advance_to("17:20")
    sandbox.check_in("participant_presenter", "presenter", "p")
    sandbox.advance_to("18:00")
    v = sandbox.view()
    assert {a.definition.activity_id: a.lifecycle for a in v.activities} == {
        "setup": "completed",
        "welcome": "completed",
        "demonstrations": "completed",
        "skills_exchange": "completed",
        "closing": "completed",
    }
    demos = next(a for a in v.activities if a.definition.activity_id == "demonstrations")
    started = next(e for e in demos.history if e.state == "started")
    assert started.at == at("17:30") and any("projector available" in m for m in started.reasons)
    closing_done = next(
        t
        for t in v.transitions
        if t.cause_kind == "activity_completed" and t.cause_ref == "closing"
    )
    closed = next(t for t in v.transitions if t.cause_kind == "event_closed")
    expired = [t for t in v.transitions if t.cause_kind == "grant_expired"]
    # Inclusive 18:00 deadline: completion first, then grant expiry, then event close.
    assert closing_done.at == closed.at == at("18:00")
    assert closing_done.revision < min(t.revision for t in expired) < closed.revision
    assert v.budget.committed_cents == 0


def test_tool_durations_advance_modeled_time(sandbox: Sandbox) -> None:
    assert sandbox.clock() == at("16:40")
    sandbox.evaluate()
    assert sandbox.clock() == at("16:40")  # evaluation is instantaneous
    sandbox.query()
    assert sandbox.clock() == at("16:42")
    sandbox.hold_backup("h")
    assert sandbox.clock() == at("16:43")
    sandbox.agent.call("get_event_state", arguments={})
    assert sandbox.clock() == at("16:43")


def test_repeated_reads_do_not_churn_revisions(sandbox: Sandbox) -> None:
    rev = sandbox.revision()
    for _ in range(3):
        sandbox.agent.call("get_event_state", arguments={})
        sandbox.agent.call("list_resources", arguments={})
        sandbox.evaluate()
    assert sandbox.revision() == rev
    sandbox.advance(1)  # a minute with no events
    assert sandbox.revision() == rev


def test_goal_change_invalidates_old_candidates(sandbox: Sandbox) -> None:
    sandbox.query()
    env = sandbox.evaluate()
    swap = sandbox.candidate(env, "Swap")
    g = sandbox.organizer.call(
        "update_goal",
        arguments={"preference_preset": "preserve_order", "reason": "test"},
        idempotency_key="g1",
        expected_revision=sandbox.revision(),
        expected_goal_version=1,
    )
    assert g.receipt.status == "applied" and g.data["goal"]["version"] == 2
    v = sandbox.view()
    assert v.goal.required_activity_ids == v.goal_history[0].required_activity_ids
    assert v.goal.hard_end == v.goal_history[0].hard_end and v.goal.budget_cents == 15000
    stale = sandbox.agent.call(
        "apply_plan",
        arguments={
            "candidate_plan_id": swap["candidate_id"],
            "constraint_report_ref": swap["report_id"],
        },
        idempotency_key="k-old",
        expected_revision=sandbox.revision(),
        expected_goal_version=2,
    )
    assert stale.receipt.error_code == "CANDIDATE_STALE"
    fresh = sandbox.evaluate()
    assert fresh.data["goal_version"] == 2


def test_forged_or_hypothetical_candidate_references_rejected(sandbox: Sandbox) -> None:
    sandbox.query()
    env = sandbox.evaluate()
    swap = sandbox.candidate(env, "Swap")
    keep = next(
        c for c in env.data["candidates"] if c["candidate_id"] == env.data["keep_candidate_id"]
    )
    forged = sandbox.apply(swap, env, "k-forge", report=keep["report_id"])
    assert forged.receipt.error_code == "CANDIDATE_REPORT_MISMATCH"
    missing = sandbox.apply({**swap, "candidate_id": "cand_9999_deadbeef"}, env, "k-missing")
    assert missing.receipt.error_code == "CANDIDATE_NOT_FOUND"
    hypo = sandbox.evaluate(
        hypotheses=[
            {
                "resource_id": "projector",
                "assume_ready_at": at("17:00").isoformat(),
                "label": "what-if",
            }
        ]
    )
    assert hypo.data["hypothetical"] is True
    h_keep = next(
        c for c in hypo.data["candidates"] if c["candidate_id"] == hypo.data["keep_candidate_id"]
    )
    res = sandbox.apply(h_keep, hypo, "k-hypo")
    assert res.receipt.error_code == "CANDIDATE_HYPOTHETICAL"
    keep_now = sandbox.apply(keep, env, "k-keep")
    assert keep_now.receipt.error_code in {"CANDIDATE_NOT_APPLICABLE", "UNSUPPORTED_ACTION"}
    infeasible = next(c for c in env.data["candidates"] if c["constraint_status"] == "infeasible")
    res = sandbox.apply(infeasible, env, "k-infeasible")
    assert res.receipt.error_code == "CANDIDATE_NOT_APPLICABLE"
    assert sandbox.view().plan.plan_version == 1


def test_hold_changes_revision_so_candidate_must_be_refreshed(sandbox: Sandbox) -> None:
    sandbox.raise_committed_limit()
    env = sandbox.evaluate()
    sub = sandbox.candidate(env, "Use backup_projector")
    assert not sub["applicable_now"]  # needs a hold first
    sandbox.hold_backup("h")
    stale = sandbox.apply(sub, env, "k-stale-sub")
    assert stale.receipt.error_code in {"REVISION_CONFLICT", "CANDIDATE_STALE"}
    env2 = sandbox.evaluate()
    sub2 = sandbox.candidate(env2, "Use backup_projector")
    assert sub2["applicable_now"]
    ok = sandbox.apply(sub2, env2, "k-sub")
    assert ok.receipt.status == "applied" and ok.receipt.committed_delta_cents == 3500


def test_backup_plan_executes_with_committed_booking(sandbox: Sandbox) -> None:
    sandbox.hold_backup("h")
    sandbox.raise_committed_limit()
    env = sandbox.evaluate()
    sandbox.apply(sandbox.candidate(env, "Use backup_projector"), env, "k-sub")
    sandbox.check_in("participant_presenter", "presenter", "p")
    sandbox.advance_to("17:10")
    demos = next(
        a for a in sandbox.view().activities if a.definition.activity_id == "demonstrations"
    )
    assert demos.lifecycle == "started"
    assert any("booking committed" in m for m in demos.history[-1].reasons)
