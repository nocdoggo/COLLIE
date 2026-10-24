"""Receipts reconcile with the revision log (the audit guide's receipt rule, strengthened).

Every revision has exactly one ``state_transitions`` row naming its cause (``repo.bump_revision``
writes both under one compare-and-swap). A handler that changes operational state bumps the
revision once, after its writes, with a cause of its own; the executor then stores the receipt
with ``revision_before`` (after the modeled duration) and ``revision_after``. So:

* an applied receipt that moved the revision moved it by exactly one, and the transition at its
  ``revision_after`` has the cause its tool writes and names exactly what the receipt changed:
  the hold, observation or grant, the applied candidate, the goal version, or the check-in
  record that the call wrote;
* an applied receipt that did not move the revision changed nothing: no state changes and no
  money (a deduplicated observation, for example), so it cannot borrow another receipt's
  transition;
* a rejected receipt changed nothing, and its call left the revision where it found it;
* every transition only a tool can cause is backed by exactly one applied receipt.

Checked over every development case run, the demo-rejections run and a run that applies every
receipt tool (no development run applies ``update_goal`` or ``release_hold``), and over the
deduplicated-observation path directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from plan_b.domain.models import (
    ActionReceipt,
    CheckInView,
    EpisodeHistory,
    EventStateView,
    ToolCallRecord,
    TransitionView,
)
from plan_b.scenarios.demos import rejected_actions_run
from plan_b.scenarios.runner import audit_view, episode_history, run_case
from plan_b.store.database import Database
from tests.conftest import Sandbox

DEV_CASES = ("dev01", "dev02", "dev04", "dev05", "dev06")

# The cause each receipt tool's handler records with its one revision bump (handlers.py).
CAUSE_BY_TOOL = {
    "hold_resource": "hold_created",
    "release_hold": "hold_released",
    "apply_plan": "plan_applied",
    "check_in": "check_in",
    "submit_observation": "observation",
    "update_goal": "goal_updated",
    "update_grant": "grant_updated",
}
# Causes no engine step or read tool writes ("observation" is also written by query_status and
# by world-event delivery, which have no receipt).
RECEIPT_ONLY_CAUSES = frozenset(CAUSE_BY_TOOL.values()) - {"observation"}
# The state-change field whose entity is the transition's reference, per tool.
REF_FIELD = {
    "hold_resource": "status",
    "release_hold": "status",
    "submit_observation": "observation",
    "update_grant": "version",
}


def _checkin_record(receipt: ActionReceipt, checkins: Sequence[CheckInView]) -> CheckInView | None:
    """The check-in record a check_in receipt's call wrote: the same principal, resource and
    instant, from a session. The receipt must name that record, not just its resource."""
    resources = {c.entity_id for c in receipt.state_changes}
    records = [
        k
        for k in checkins
        if k.channel == "participant_session"
        and k.principal_id == receipt.actor_id
        and k.resource_id in resources
        and k.at == receipt.executed_at
    ]
    if len(records) != 1:
        return None
    named = {c.after.get("checkin_id") for c in receipt.state_changes if isinstance(c.after, dict)}
    return records[0] if named == {records[0].checkin_id} else None


def expected_cause_ref(receipt: ActionReceipt, checkins: Sequence[CheckInView]) -> str | None:
    """The ``cause_ref`` the transition of an applied, revision-moving receipt must carry."""
    if receipt.tool == "apply_plan":
        return receipt.related_plan_id
    if receipt.tool == "update_goal":
        versions = {c.after for c in receipt.state_changes if c.field == "version"}
        return f"goal_v{versions.pop()}" if len(versions) == 1 else None
    if receipt.tool == "check_in":
        record = _checkin_record(receipt, checkins)
        return record.checkin_id if record is not None else None
    field = REF_FIELD.get(receipt.tool)
    ids = {c.entity_id for c in receipt.state_changes if c.field == field}
    return ids.pop() if len(ids) == 1 else None


def reconciliation_problems(history: EpisodeHistory, checkins: Sequence[CheckInView]) -> list[str]:
    """Every breach of the receipt rule in one episode's persisted history and check-ins."""
    problems: list[str] = []
    transitions: dict[int, TransitionView] = {}
    for t in history.transitions:
        if t.revision in transitions:
            problems.append(f"revision {t.revision} has two transitions")
        transitions[t.revision] = t
    # The call that executed each receipt: a replay returns the original receipt from a later
    # call, so the first call naming a receipt is the one that produced it.
    calls: dict[str, ToolCallRecord] = {}
    for c in sorted(history.tool_calls, key=lambda c: c.seq):
        if c.receipt_id is not None:
            calls.setdefault(c.receipt_id, c)
    backing: dict[int, list[ActionReceipt]] = {}
    for r in history.receipts:
        where = (
            f"{r.receipt_id} ({r.tool}, {r.status}, rev {r.revision_before}->{r.revision_after})"
        )
        moved = r.revision_after - r.revision_before
        call = calls.get(r.receipt_id)
        # The call's envelope carries the episode revision right after it: nothing else may
        # move the revision between the receipt and the end of its call.
        if call is not None and call.revision_after != r.revision_after:
            problems.append(f"{where}: its call ended at revision {call.revision_after}")
        if r.status == "applied" and moved > 0:
            if moved != 1:
                problems.append(f"{where}: moved the revision by {moved}")
            own = transitions.get(r.revision_after)
            expected = CAUSE_BY_TOOL.get(r.tool)
            ref = expected_cause_ref(r, checkins)
            if own is None:
                problems.append(f"{where}: no transition at revision {r.revision_after}")
            elif expected is None or own.cause_kind != expected:
                problems.append(f"{where}: transition cause {own.cause_kind!r}, not {expected!r}")
            elif ref is None:
                problems.append(f"{where}: the receipt names no single record of its own")
            elif own.cause_ref != ref:
                problems.append(f"{where}: transition names {own.cause_ref!r}, not {ref!r}")
            backing.setdefault(r.revision_after, []).append(r)
        elif r.status == "applied" and moved == 0:
            if r.state_changes or r.committed_delta_cents or r.reserved_delta_cents:
                problems.append(f"{where}: no revision change but reports state changes")
        elif r.status == "applied":
            problems.append(f"{where}: revision went backwards")
        elif moved != 0 or r.state_changes or r.committed_delta_cents or r.reserved_delta_cents:
            problems.append(f"{where}: a rejected receipt reports a change")
    for revision, receipts in backing.items():
        if len(receipts) > 1:
            ids = ", ".join(r.receipt_id for r in receipts)
            problems.append(f"revision {revision} is claimed by {ids}")
    for t in transitions.values():
        if t.cause_kind in RECEIPT_ONLY_CAUSES and len(backing.get(t.revision, [])) != 1:
            problems.append(
                f"transition {t.revision} ({t.cause_kind} {t.cause_ref}) is not backed by one "
                "applied receipt"
            )
    return problems


@pytest.fixture(scope="module")
def runs(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, tuple[EpisodeHistory, EventStateView]]:
    db = Database(tmp_path_factory.mktemp("receipts") / "receipts.sqlite3")
    out: dict[str, tuple[EpisodeHistory, EventStateView]] = {}
    for ref in DEV_CASES:
        result = run_case(db, ref)
        out[ref] = (result.history, result.final_view)
    episode_id, _ = rejected_actions_run(db)
    out["demo_rejections"] = (episode_history(db, episode_id), audit_view(db, episode_id))
    return out


@pytest.mark.parametrize("run", [*DEV_CASES, "demo_rejections"])
def test_receipts_reconcile_with_the_revision_log(
    runs: dict[str, tuple[EpisodeHistory, EventStateView]], run: str
) -> None:
    history, view = runs[run]
    assert any(r.status == "applied" for r in history.receipts)
    assert reconciliation_problems(history, view.checkins) == []


def test_demo_rejections_cover_both_receipt_outcomes(
    runs: dict[str, tuple[EpisodeHistory, EventStateView]],
) -> None:
    # The demo run is the one that exercises rejected receipts across tools; the rule above is
    # not satisfied vacuously there.
    history, _ = runs["demo_rejections"]
    rejected = {r.tool for r in history.receipts if r.status == "rejected"}
    applied = {r.tool for r in history.receipts if r.status == "applied"}
    assert {"apply_plan", "check_in"} <= rejected
    assert {"hold_resource", "apply_plan", "check_in", "submit_observation"} <= applied
    assert "update_grant" in applied


def _submit(sb: Sandbox, key: str, **arguments: Any) -> ActionReceipt:
    env = sb.client("participant_presenter").call(
        "submit_observation", arguments=arguments, idempotency_key=key
    )
    assert env.receipt is not None, env.error
    return env.receipt


def _applied(env: Any) -> ActionReceipt:
    assert env.receipt is not None and env.receipt.status == "applied", (env.error, env.receipt)
    receipt: ActionReceipt = env.receipt
    return receipt


def test_every_receipt_tool_reconciles_when_applied(sandbox: Sandbox) -> None:
    # One applied receipt of each tool through the real executor: the organizer changes the
    # goal's preference preset, the coordinator holds the backup and releases it, the
    # organizer raises the coordinator's limit, the presenter checks in and sends an update,
    # and the coordinator applies the swap.
    sb = sandbox
    goal = _applied(
        sb.organizer.call(
            "update_goal",
            arguments={"preference_preset": "preserve_order", "reason": "test: keep the order"},
            idempotency_key="goal-1",
            expected_revision=sb.revision(),
            expected_goal_version=1,
        )
    )
    held = sb.hold_backup("hold-1")
    hold = _applied(held)
    assert held.data is not None
    hold_id = held.data["hold"]["hold_id"]
    release = _applied(
        sb.agent.call(
            "release_hold",
            arguments={"hold_id": hold_id, "reason": "test: not needed"},
            idempotency_key="release-1",
            expected_revision=sb.revision(),
        )
    )
    grant = _applied(sb.raise_committed_limit())
    checked = _applied(sb.check_in("participant_presenter", "presenter", "pres-1"))
    observed = _submit(sb, "obs-1", text="Running five minutes late.", client_record_id="r1")
    assert sb.query().status == "succeeded"
    env = sb.evaluate()
    assert env.data is not None and env.data["goal_version"] == 2
    swap = sb.candidate(env, "Swap")
    plan = _applied(sb.apply(swap, env, "apply-1"))

    view = sb.view()
    history = episode_history(sb.db, sb.episode_id)
    assert {r.tool for r in history.receipts if r.status == "applied"} == set(CAUSE_BY_TOOL)
    assert reconciliation_problems(history, view.checkins) == []

    (checkin,) = [k for k in view.checkins if k.principal_id == "participant_presenter"]
    (observation,) = [o for o in view.observations if o.observation.source_record_id == "r1"]
    by_revision = {t.revision: (t.cause_kind, t.cause_ref) for t in history.transitions}
    assert {
        r.tool: by_revision[r.revision_after]
        for r in (goal, hold, release, grant, checked, observed, plan)
    } == {
        "update_goal": ("goal_updated", "goal_v2"),
        "hold_resource": ("hold_created", hold_id),
        "release_hold": ("hold_released", hold_id),
        "update_grant": ("grant_updated", "grant_coordinator_demo"),
        "check_in": ("check_in", checkin.checkin_id),
        "submit_observation": ("observation", observation.observation.observation_id),
        "apply_plan": ("plan_applied", swap["candidate_id"]),
    }
    # The check-in's reference is its record, never the role it checked in for.
    assert checkin.checkin_id != "presenter"
    assert view.goal.version == 2 and view.goal.preference_preset == "preserve_order"
    assert next(h for h in view.holds if h.hold_id == hold_id).status == "released"


def test_a_deduplicated_observation_does_not_claim_the_original_transition(
    sandbox: Sandbox,
) -> None:
    # A browser resend of an unknown outcome reuses the request and its idempotency key, so it
    # can only replay the original receipt. Only a dismiss-and-retype sends a new key, with the
    # earlier client record id: that request is a duplicate of the first, not a second change.
    message = {"text": "Running five minutes late, still coming.", "client_record_id": "web-obs-1"}
    first = _submit(sandbox, "obs-1", **message)
    assert first.status == "applied"
    assert first.revision_after == first.revision_before + 1
    second = _submit(sandbox, "obs-2", **message)
    if second.receipt_id != first.receipt_id:
        # A receipt of its own: a no-op, never a second claim on revision_after.
        assert second.status == "applied"
        assert second.revision_after == second.revision_before == first.revision_after
        assert second.state_changes == ()
    view = sandbox.view()
    records = [o for o in view.observations if o.observation.source_record_id == "web-obs-1"]
    assert len(records) == 1
    history = episode_history(sandbox.db, sandbox.episode_id)
    assert reconciliation_problems(history, view.checkins) == []
    (claim,) = [t for t in history.transitions if t.revision == first.revision_after]
    assert claim.cause_kind == "observation"
    assert claim.cause_ref == records[0].observation.observation_id


def test_the_rule_catches_a_receipt_that_borrows_a_transition(sandbox: Sandbox) -> None:
    # The audit guide's weaker rule ("revision_after has a transition") accepts a receipt that
    # reports a change at a revision it did not produce; this rule does not.
    first = _submit(sandbox, "obs-1", text="Running late.", client_record_id="r1")
    history = episode_history(sandbox.db, sandbox.episode_id)
    checkins = sandbox.view().checkins
    borrowed = first.model_copy(
        update={
            "receipt_id": "rcpt_9999",
            "revision_before": first.revision_after,
            "request_idempotency_key": "obs-borrowed",
        }
    )
    forged = history.model_copy(update={"receipts": (*history.receipts, borrowed)})
    assert any(
        "no revision change but reports state changes" in p
        for p in reconciliation_problems(forged, checkins)
    )
    double = first.model_copy(update={"receipt_id": "rcpt_9998"})
    forged = history.model_copy(update={"receipts": (*history.receipts, double)})
    assert any("is claimed by" in p for p in reconciliation_problems(forged, checkins))


def test_a_check_in_transition_must_name_its_check_in_record(sandbox: Sandbox) -> None:
    # The check-in receipt names its role as the changed entity; the transition must name the
    # check-in record the call wrote, so a transition naming the role is a breach.
    receipt = _applied(sandbox.check_in("participant_presenter", "presenter", "pres-1"))
    history = episode_history(sandbox.db, sandbox.episode_id)
    checkins = sandbox.view().checkins
    (record,) = [k for k in checkins if k.principal_id == "participant_presenter"]
    assert reconciliation_problems(history, checkins) == []
    assert [c.entity_id for c in receipt.state_changes] == ["presenter"]

    def naming(ref: str) -> EpisodeHistory:
        transitions = tuple(
            t.model_copy(update={"cause_ref": ref}) if t.revision == receipt.revision_after else t
            for t in history.transitions
        )
        return history.model_copy(update={"transitions": transitions})

    assert any(
        f"transition names 'presenter', not {record.checkin_id!r}" in p
        for p in reconciliation_problems(naming("presenter"), checkins)
    )
    # A receipt that names another record than the one its call wrote is a breach too.
    other = receipt.model_copy(
        update={
            "state_changes": tuple(
                c.model_copy(update={"after": {**c.after, "checkin_id": "chk_9999"}})
                for c in receipt.state_changes
            )
        }
    )
    forged = history.model_copy(
        update={
            "receipts": tuple(
                other if r.receipt_id == receipt.receipt_id else r for r in history.receipts
            )
        }
    )
    assert any(
        "names no single record of its own" in p for p in reconciliation_problems(forged, checkins)
    )
