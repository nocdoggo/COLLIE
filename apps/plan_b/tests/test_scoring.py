"""State-based outcome scoring from synthetic persisted records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from plan_b.domain.fixtures import load_public_scenario
from plan_b.domain.models import (
    ActionReceipt,
    ActivityLifecycleEvent,
    ActivityView,
    Assignment,
    BudgetView,
    CheckInView,
    CommitmentView,
    EpisodeHistory,
    EventStateView,
    GrantView,
    Observation,
    ObservationRecord,
    OutcomePredicate,
    PlanView,
    PolicyDecision,
    PrivateCase,
    StateChange,
    StatusFacts,
    TimeWindow,
    ToolCallRecord,
    ViewerInfo,
)
from plan_b.domain.projection import initial_snapshot
from plan_b.domain.timeutil import parse_ts
from plan_b.evaluation.scoring import public_summary, score_episode

SC = load_public_scenario()
SNAP = initial_snapshot(SC)
COORD = next(g for g in SC.authority_grants if g.grant_id == "grant_coordinator_demo")
DEFS = {a.activity_id: a for a in SC.activities}


def local(hhmm: str) -> datetime:
    return parse_ts(f"2026-11-05T{hhmm}:00-05:00")


def assignment(aid: str, start: str, end: str, *resources: str) -> Assignment:
    return Assignment(activity_id=aid, start=local(start), end=local(end), resource_ids=resources)


PLAN_V1 = SNAP.plan
SWAPPED = tuple(
    assignment("demonstrations", "17:30", "17:50", *a.resource_ids)
    if a.activity_id == "demonstrations"
    else assignment("skills_exchange", "17:10", "17:30", *a.resource_ids)
    if a.activity_id == "skills_exchange"
    else a
    for a in PLAN_V1.assignments
)
SUBSTITUTED = tuple(
    assignment("demonstrations", "17:10", "17:30", "main_room", "backup_projector", "presenter")
    if a.activity_id == "demonstrations"
    else a
    for a in PLAN_V1.assignments
)


class Timeline:
    """Lifecycle events with increasing seq and revision."""

    def __init__(self) -> None:
        self.events: list[ActivityLifecycleEvent] = []

    def add(self, aid: str, state: str, at: str, revision: int, *reasons: str) -> None:
        self.events.append(
            ActivityLifecycleEvent(
                seq=len(self.events) + 1,
                activity_id=aid,
                state=state,  # type: ignore[arg-type]
                at=local(at),
                revision=revision,
                reasons=reasons,
            )
        )

    def views(self, plan: PlanView) -> tuple[ActivityView, ...]:
        out = []
        by_plan = {a.activity_id: a for a in plan.assignments}
        for aid, definition in DEFS.items():
            history = tuple(e for e in self.events if e.activity_id == aid)
            lifecycle = history[-1].state if history else "planned"
            out.append(
                ActivityView(
                    definition=definition,
                    lifecycle=lifecycle,
                    history=history,
                    assignment=by_plan.get(aid),
                    readiness=None,
                )
            )
        return tuple(out)


def observation(
    oid: str,
    at: str,
    revision: int,
    *,
    kind: str = "status",
    entity: str = "projector",
    structured: StatusFacts | None = None,
    channel: str = "status_tool",
    text: str = "record",
) -> ObservationRecord:
    t = local(at)
    return ObservationRecord(
        observation=Observation(
            observation_id=oid,
            event_id=SC.event_id,
            entity_id=entity,
            kind=kind,  # type: ignore[arg-type]
            source_id="source",
            source_record_id=f"src_{oid}",
            correlation_group="g",
            observed_at=t,
            received_at=t,
            valid_window=TimeWindow(start=t, end=SC.goal.hard_end),
            authority_scope="resource_status" if kind == "status" else "self_report",
            text=text,
            supersedes=(),
        ),
        channel=channel,  # type: ignore[arg-type]
        submitted_by=None,
        revision_after=revision,
        structured=structured,
    )


NOTICE = ObservationRecord(
    observation=SC.visible_observations[0],
    channel="fixture_initial",
    submitted_by=None,
    revision_after=3,
)


def eta_status(oid: str, at: str, revision: int, eta: str) -> ObservationRecord:
    return observation(
        oid,
        at,
        revision,
        structured=StatusFacts(
            fact="delivery_eta",
            status_code="delayed",
            domain_status="expected",
            reported_eta=local(eta),
        ),
    )


def arrival(oid: str, at: str, revision: int) -> ObservationRecord:
    return observation(
        oid,
        at,
        revision,
        channel="arrival_record",
        structured=StatusFacts(
            fact="arrival", status_code="arrived", domain_status="available", reported_eta=None
        ),
    )


def checkin(cid: str, rid: str, at: str, oid: str | None = None) -> CheckInView:
    return CheckInView(
        checkin_id=cid,
        principal_id=f"participant_{rid}",
        resource_id=rid,
        at=local(at),
        available=TimeWindow(start=local(at), end=SC.goal.hard_end),
        observation_id=oid,
        channel="participant_session" if oid else "fixture_initial",
    )


def receipt(
    rid: str,
    tool: str,
    at: str,
    before: int,
    *,
    status: str = "applied",
    changes: tuple[StateChange, ...] = (),
    actor: str = "agent_demo",
    committed: int = 0,
) -> ActionReceipt:
    return ActionReceipt(
        runtime_version="1.0.0",
        receipt_id=rid,
        episode_id="ep_test",
        event_id=SC.event_id,
        tool=tool,
        request_idempotency_key=f"key_{rid}",
        request_digest="0" * 64,
        grant_id=COORD.grant_id,
        grant_version=1,
        actor_id=actor,
        actor_role="coordinator_agent" if actor == "agent_demo" else "organizer",
        status=status,  # type: ignore[arg-type]
        revision_before=before,
        revision_after=before + 1 if status == "applied" else before,
        requested_at=local(at),
        executed_at=local(at),
        simulation=True,
        state_changes=changes if status == "applied" else (),
        committed_delta_cents=committed if status == "applied" else 0,
        reserved_delta_cents=0,
        related_plan_id=None,
        constraint_report_ref=None,
        error_code=None if status == "applied" else "BUDGET_EXCEEDED",
        error_message=None,
        summary=f"{tool} {status}",
    )


def window_change(aid: str) -> StateChange:
    return StateChange(entity_id=aid, field="scheduled_window", before={}, after={})


def grant(version: int, limit: int, issued: str | None, used: int = 0) -> GrantView:
    return GrantView(
        grant=COORD.model_copy(update={"max_total_committed_cents": limit}),
        version=version,
        revoked=False,
        valid_now=False,
        committed_used_cents=used,
        reserved_used_cents=0,
        issued_receipt_id=issued,
    )


def tool_call(seq: int, tool: str, status: str, receipt_id: str | None = None) -> ToolCallRecord:
    return ToolCallRecord(
        seq=seq,
        call_id=f"call_{seq:04d}",
        actor_id="agent_demo",
        actor_role="coordinator_agent",
        tool=tool,
        requested_at=local("16:40"),
        completed_at=local("16:40"),
        revision_before=3,
        revision_after=3,
        envelope_status=status,  # type: ignore[arg-type]
        error_code=None,
        receipt_id=receipt_id,
        request={},
        envelope={},
    )


def decision(n: int, kind: str, **details: Any) -> PolicyDecision:
    return PolicyDecision(
        decision_id=f"dec_{n:04d}",
        policy_id="rules/1.0.0",
        at=local("16:44"),
        revision=5,
        kind=kind,  # type: ignore[arg-type]
        summary=f"{kind} decision",
        details=details,
    )


def final_view(
    *,
    timeline: Timeline,
    plans: tuple[PlanView, ...],
    observations: tuple[ObservationRecord, ...],
    checkins: tuple[CheckInView, ...],
    receipts: tuple[ActionReceipt, ...] = (),
    commitments: tuple[CommitmentView, ...] = (),
    grants: tuple[GrantView, ...] = (),
    committed: int = 0,
) -> EventStateView:
    plan = plans[-1]
    history = grants or (grant(1, 0, None),)
    return EventStateView(
        runtime_version="1.0.0",
        episode_id="ep_test",
        event_id=SC.event_id,
        scenario_id=SC.scenario_id,
        profile_id=SC.profile_id,
        fictional=True,
        sandbox_label="Fictional local sandbox",
        timezone=SC.timezone,
        episode_status="closed",
        clock=SC.goal.hard_end,
        revision=30,
        goal=SC.goal,
        goal_history=(SC.goal,),
        activities=timeline.views(plan),
        plan=plan,
        plan_history=plans,
        resources=SNAP.resources,
        holds=(),
        commitments=commitments,
        checkins=checkins,
        budget=BudgetView(
            budget_cents=SC.goal.budget_cents,
            committed_cents=committed,
            reserved_cents=0,
            remaining_cents=SC.goal.budget_cents - committed,
        ),
        grants=(history[-1],),
        grant_history=history,
        observations=observations,
        receipts=receipts,
        attempts=(),
        decisions=(),
        latest_evaluation=None,
        transitions=(),
        declared_assumptions=SC.declared_assumptions,
        tool_durations_minutes=SC.tool_durations_minutes,
        viewer=ViewerInfo(
            principal_id="moderator", role="moderator", display_name="Moderator", grant_id=None
        ),
    )


def private_case(
    expected: str, predicates: tuple[tuple[str, str, dict[str, Any]], ...]
) -> PrivateCase:
    return PrivateCase(
        artifact="plan_b.private_case",
        runtime_version="1.0.0",
        case_ref="case_test",
        scenario_id=SC.scenario_id,
        never_expose_to_agent=True,
        planning_label="TEST",
        description="synthetic test case",
        derived_from=None,
        status_model=(),
        world_events=(),
        actor_scripts=(),
        outcome_predicates=tuple(
            OutcomePredicate(predicate_id=pid, kind=kind, params=params, description=pid)  # type: ignore[arg-type]
            for pid, kind, params in predicates
        ),
        expected_outcome=expected,  # type: ignore[arg-type]
    )


def full_day(t: Timeline, demos: tuple[str, str], skills: tuple[str, str]) -> None:
    """Every activity starts and completes; revisions increase with time."""
    t.add("setup", "started", "16:30", 3)
    t.add("setup", "completed", "16:50", 6)
    t.add("welcome", "started", "17:00", 7)
    t.add("welcome", "completed", "17:10", 9)
    first, second = sorted(
        [("demonstrations", demos), ("skills_exchange", skills)], key=lambda x: x[1]
    )
    t.add(first[0], "started", first[1][0], 10)
    t.add(first[0], "completed", first[1][1], 13)
    t.add(second[0], "started", second[1][0], 14)
    t.add(second[0], "completed", second[1][1], 15)
    t.add("closing", "started", "17:50", 16)
    t.add("closing", "completed", "18:00", 17)


DEV01_LIKE: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("all_required", "all_required_completed_by_deadline", {}),
    (
        "welcome_1700",
        "activity_started_at",
        {"activity_id": "welcome", "at": "2026-11-05T17:00:00-05:00"},
    ),
    ("no_violations", "no_executed_violations", {}),
    ("within_limits", "committed_within_limits", {}),
    ("no_early_equipment", "no_equipment_start_before_arrival", {}),
    ("no_spend", "committed_spend_equals", {"cents": 0}),
    ("one_plan", "applied_plan_count", {"count": 1}),
)


def _success() -> tuple[EventStateView, EpisodeHistory]:
    t = Timeline()
    full_day(t, demos=("17:30", "17:50"), skills=("17:10", "17:30"))
    apply = receipt(
        "rcpt_apply",
        "apply_plan",
        "16:43",
        4,
        changes=(
            window_change("demonstrations"),
            window_change("skills_exchange"),
            StateChange(entity_id="demonstrations", field="resource_ids", before=[], after=[]),
            StateChange(entity_id="plan", field="plan_version", before=1, after=2),
        ),
    )
    plan2 = PlanView(
        plan_version=2,
        assignments=SWAPPED,
        applied_receipt_id="rcpt_apply",
        candidate_id="cand_0001_x",
        applied_at=local("16:43"),
    )
    final = final_view(
        timeline=t,
        plans=(PLAN_V1, plan2),
        observations=(
            NOTICE,
            eta_status("obs_0004", "16:42", 4, "17:25"),
            observation("obs_0005", "17:05", 8, kind="check_in", entity="facilitator"),
            observation("obs_0006", "17:20", 11, kind="check_in", entity="presenter"),
            arrival("obs_0007", "17:24", 12),
        ),
        checkins=(
            SNAP.checkins[0],
            checkin("chk_2", "facilitator", "17:05", "obs_0005"),
            checkin("chk_3", "presenter", "17:20", "obs_0006"),
        ),
        receipts=(apply,),
    )
    history = EpisodeHistory(
        tool_calls=(
            tool_call(1, "get_event_state", "succeeded"),
            tool_call(2, "query_status", "succeeded"),
            tool_call(3, "apply_plan", "succeeded", "rcpt_apply"),
            tool_call(4, "check_in", "rejected"),
        ),
        transitions=(),
        decisions=(decision(1, "verify"), decision(2, "commit")),
        receipts=(apply,),
    )
    return final, history


def test_success_episode_scores_complete() -> None:
    final, history = _success()
    report = score_episode(final, history, policy_id="rules/1.0.0")

    assert report.violations == ()
    assert report.goal_complete is True
    assert report.applied_plans == 1
    assert report.changed_assignments == 2  # unique activities, not state-change rows
    assert report.status_queries == 1 and report.failed_status_queries == 0
    assert report.rejected_receipts == 0
    assert report.rejected_attempts_without_receipt == 1
    assert report.recovery_delay_minutes == 3  # notice 16:40 -> applied 16:43
    assert report.infeasibility_reported is False
    assert report.committed_cents == 0 and report.reserved_cents_at_end == 0
    assert report.holds.created == 0
    welcome = next(a for a in report.activities if a.activity_id == "welcome")
    assert welcome.started_at == local("17:00") and welcome.completed_at == local("17:10")
    assert report.policy_id == "rules/1.0.0"
    assert (
        report.case_ref is None and report.predicates == () and report.matches_expectation is None
    )

    graded = score_episode(final, history, private_case("goal_complete", DEV01_LIKE))
    assert [p.passed for p in graded.predicates] == [True] * len(DEV01_LIKE)
    assert graded.matches_expectation is True
    assert graded.expected_outcome == "goal_complete"
    assert graded.case_ref == "case_test"


def test_public_summary_drops_private_fields() -> None:
    final, history = _success()
    graded = score_episode(final, history, private_case("goal_complete", DEV01_LIKE))
    summary = public_summary(graded)
    for key in ("predicates", "expected_outcome", "case_ref", "matches_expectation"):
        assert key not in summary
    assert summary["goal_complete"] is True
    assert summary["applied_plans"] == 1


def test_equipment_start_before_arrival_and_overspend_are_violations() -> None:
    t = Timeline()
    full_day(t, demos=("17:10", "17:30"), skills=("17:30", "17:50"))
    commitment = CommitmentView(
        commitment_id="cmt_1",
        resource_id="backup_projector",
        activity_id="demonstrations",
        window=TimeWindow(start=local("17:10"), end=local("17:30")),
        committed_cents=3500,
        source_hold_id=None,
        plan_version=1,
        status="active",
        created_at=local("16:50"),
        receipt_id="rcpt_x",
        actor_id="agent_demo",
        grant_id=COORD.grant_id,
    )
    final = final_view(
        timeline=t,
        plans=(PLAN_V1,),
        observations=(NOTICE, arrival("obs_0007", "17:24", 12)),
        checkins=(
            SNAP.checkins[0],
            checkin("chk_2", "facilitator", "17:05"),
            checkin("chk_3", "presenter", "17:05"),
        ),
        commitments=(commitment,),
        committed=3500,
    )
    history = EpisodeHistory(tool_calls=(), transitions=(), decisions=(), receipts=())
    report = score_episode(final, history, private_case("goal_complete", DEV01_LIKE))

    assert report.goal_complete is False
    categories = {v.split(":")[0] for v in report.violations}
    assert {"equipment_before_arrival", "grant_limit"} <= categories
    assert any("demonstrations started at 17:10" in v for v in report.violations)
    by_id = {p.predicate_id: p for p in report.predicates}
    assert by_id["all_required"].passed is True
    assert by_id["no_early_equipment"].passed is False
    assert by_id["within_limits"].passed is False
    assert by_id["no_violations"].passed is False
    assert by_id["no_spend"].passed is False
    assert by_id["one_plan"].passed is False
    assert report.matches_expectation is False


def test_program_overlap_and_missing_check_in_are_violations() -> None:
    t = Timeline()
    t.add("setup", "started", "16:30", 3)
    t.add("setup", "completed", "16:50", 6)
    t.add("welcome", "started", "17:00", 7)
    t.add("demonstrations", "started", "17:05", 8)
    t.add("welcome", "completed", "17:10", 9)
    t.add("demonstrations", "completed", "17:25", 10)
    final = final_view(
        timeline=t,
        plans=(PLAN_V1,),
        observations=(NOTICE, arrival("obs_0007", "16:58", 5)),
        checkins=(SNAP.checkins[0],),
    )
    report = score_episode(
        final, EpisodeHistory(tool_calls=(), transitions=(), decisions=(), receipts=())
    )
    categories = {v.split(":")[0] for v in report.violations}
    assert "program_overlap" in categories
    assert "role_not_checked_in" in categories  # presenter never checked in
    assert report.goal_complete is False


def _commitment_at(at: str, receipt_id: str) -> CommitmentView:
    return CommitmentView(
        commitment_id="cmt_1",
        resource_id="backup_projector",
        activity_id="demonstrations",
        window=TimeWindow(start=local("17:10"), end=local("17:30")),
        committed_cents=3500,
        source_hold_id="hold_1",
        plan_version=2,
        status="active",
        created_at=local(at),
        receipt_id=receipt_id,
        actor_id="agent_demo",
        grant_id=COORD.grant_id,
    )


def _backup_run() -> tuple[EventStateView, EpisodeHistory]:
    """Demonstrations runs 17:10-17:30 on the committed backup projector after a grant raise."""
    t = Timeline()
    full_day(t, demos=("17:10", "17:30"), skills=("17:30", "17:50"))
    raise_grant = receipt("rcpt_grant", "update_grant", "16:47", 7, actor="organizer_demo")
    apply = receipt(
        "rcpt_apply", "apply_plan", "16:48", 8, changes=(window_change("demonstrations"),)
    )
    plan2 = PlanView(
        plan_version=2,
        assignments=SUBSTITUTED,
        applied_receipt_id="rcpt_apply",
        candidate_id="cand_x",
        applied_at=local("16:48"),
    )
    grants = (grant(1, 0, None), grant(2, 3500, "rcpt_grant", used=3500))
    checkins = (
        SNAP.checkins[0],
        checkin("chk_2", "presenter", "17:02"),
        checkin("chk_3", "facilitator", "17:25"),
    )
    final = final_view(
        timeline=t,
        plans=(PLAN_V1, plan2),
        observations=(NOTICE, eta_status("obs_0004", "16:42", 4, "17:45")),
        checkins=checkins,
        receipts=(raise_grant, apply),
        commitments=(_commitment_at("16:48", "rcpt_apply"),),
        grants=grants,
        committed=3500,
    )
    history = EpisodeHistory(
        tool_calls=(), transitions=(), decisions=(), receipts=(raise_grant, apply)
    )
    return final, history


def test_commitment_after_grant_raise_is_within_limits() -> None:
    final, history = _backup_run()
    raise_grant = history.receipts[0]
    report = score_episode(final, history)
    assert report.violations == ()
    assert report.goal_complete is True
    assert report.recovery_delay_minutes == 8

    # The same commitment made before the raise exceeds the version then in effect.
    early_apply = receipt("rcpt_early", "apply_plan", "16:45", 5)
    early = final.model_copy(
        update={
            "commitments": (_commitment_at("16:45", "rcpt_early"),),
            "receipts": (raise_grant, early_apply),
        }
    )
    late_report = score_episode(
        early,
        EpisodeHistory(
            tool_calls=(), transitions=(), decisions=(), receipts=(raise_grant, early_apply)
        ),
    )
    assert any(v.startswith("grant_limit:") and "version 1" in v for v in late_report.violations)


def test_infeasible_expectation_matches_without_success() -> None:
    t = Timeline()
    t.add("setup", "started", "16:30", 3)
    t.add("setup", "completed", "16:50", 6)
    t.add("welcome", "started", "17:00", 7)
    t.add("welcome", "completed", "17:10", 8)
    t.add("demonstrations", "failed", "17:10", 9, "projector is unavailable")
    t.add("skills_exchange", "started", "17:30", 11)
    t.add("skills_exchange", "completed", "17:50", 12)
    t.add("closing", "failed", "17:50", 13, "predecessor demonstrations is failed, not completed")
    final = final_view(
        timeline=t,
        plans=(PLAN_V1,),
        observations=(
            NOTICE,
            observation(
                "obs_0004",
                "16:42",
                4,
                structured=StatusFacts(
                    fact="delivery_eta",
                    status_code="cancelled",
                    domain_status="unavailable",
                    reported_eta=None,
                ),
            ),
        ),
        checkins=(
            SNAP.checkins[0],
            checkin("chk_2", "presenter", "17:05"),
            checkin("chk_3", "facilitator", "17:05"),
        ),
    )
    history = EpisodeHistory(
        tool_calls=(
            tool_call(1, "query_status", "succeeded"),
            tool_call(2, "query_status", "unavailable"),
        ),
        transitions=(),
        decisions=(
            decision(1, "verify"),
            decision(2, "infeasible", blocking_constraints=["resource_status"]),
        ),
        receipts=(),
    )
    case = private_case(
        "goal_not_complete_infeasibility_reported",
        (
            ("no_violations", "no_executed_violations", {}),
            ("within_limits", "committed_within_limits", {}),
            ("no_early_equipment", "no_equipment_start_before_arrival", {}),
            ("infeasible_reported", "infeasibility_reported", {}),
            ("demos_not_completed", "activity_not_completed", {"activity_id": "demonstrations"}),
            ("no_spend", "committed_spend_equals", {"cents": 0}),
            ("no_plan_change", "applied_plan_count", {"count": 0}),
        ),
    )
    report = score_episode(final, history, case)

    assert report.goal_complete is False
    assert report.infeasibility_reported is True
    assert report.violations == ()
    assert report.status_queries == 2 and report.failed_status_queries == 1
    assert report.recovery_delay_minutes is None
    demos = next(a for a in report.activities if a.activity_id == "demonstrations")
    assert demos.lifecycle == "failed" and demos.failure_reasons == ("projector is unavailable",)
    assert all(p.passed for p in report.predicates), [p for p in report.predicates if not p.passed]
    assert report.matches_expectation is True

    # Infeasibility narration that names no blocking constraint does not satisfy the predicate.
    vague = history.model_copy(update={"decisions": (decision(3, "infeasible"),)})
    vague_report = score_episode(final, vague, case)
    by_id = {p.predicate_id: p for p in vague_report.predicates}
    assert by_id["infeasible_reported"].passed is False
    assert vague_report.matches_expectation is False


def test_missing_predicate_parameters_fail_explicitly() -> None:
    final, history = _success()
    case = private_case(
        "goal_complete",
        (
            ("bad_at", "activity_started_at", {"activity_id": "welcome"}),
            ("bad_cents", "committed_spend_equals", {}),
            ("unknown_activity", "activity_not_completed", {"activity_id": "nope"}),
        ),
    )
    report = score_episode(final, history, case)
    assert [p.passed for p in report.predicates] == [False, False, False]
    assert report.matches_expectation is False


def presence(cid: str, rid: str, at: str, start: str, end: str) -> CheckInView:
    """A check-in at ``at`` declaring availability ``start``-``end``."""
    return CheckInView(
        checkin_id=cid,
        principal_id=f"participant_{rid}",
        resource_id=rid,
        at=local(at),
        available=TimeWindow(start=local(start), end=local(end)),
        observation_id=None,
        channel="fixture_initial",
    )


def status_record(
    oid: str,
    observed: str,
    received: str,
    revision: int,
    *,
    entity: str = "projector",
    code: str = "delayed",
    domain: str = "expected",
    eta: str | None = None,
) -> ObservationRecord:
    """A status-tool record whose source time differs from when it was retrieved."""
    base = observation(oid, observed, revision, entity=entity)
    return base.model_copy(
        update={
            "observation": base.observation.model_copy(update={"received_at": local(received)}),
            "structured": StatusFacts(
                fact="delivery_eta",
                status_code=code,
                domain_status=domain,  # type: ignore[arg-type]
                reported_eta=local(eta) if eta else None,
            ),
        }
    )


def test_latest_checkin_by_the_start_decides_presence() -> None:
    """A later, narrower check-in supersedes an earlier one that covered the window."""
    final, history = _success()  # demonstrations 17:30-17:50; presenter checked in at 17:20
    leaving = presence("chk_4", "presenter", "17:25", "17:25", "17:28")
    gone = final.model_copy(update={"checkins": (*final.checkins, leaving)})
    report = score_episode(gone, history, private_case("goal_complete", DEV01_LIKE))
    assert report.goal_complete is False
    assert report.violations == (
        "role_not_checked_in: demonstrations started at 17:30 although presenter's latest "
        "check-in (17:25) is available 17:25-17:28, not covering its window",
    )
    assert {p.predicate_id for p in report.predicates if not p.passed} == {"no_violations"}

    # A still later, covering check-in restores presence.
    back = presence("chk_5", "presenter", "17:27", "17:27", "18:00")
    restored = final.model_copy(update={"checkins": (*final.checkins, leaving, back)})
    assert score_episode(restored, history).violations == ()

    # A check-in recorded after the start does not count for it.
    after = presence("chk_6", "presenter", "17:35", "17:35", "18:00")
    late = final.model_copy(update={"checkins": (*final.checkins, leaving, after)})
    assert [v.split(":")[0] for v in score_episode(late, history).violations] == [
        "role_not_checked_in"
    ]


def test_status_at_start_follows_source_time_not_ingest_order() -> None:
    final, history = _success()  # projector arrival observed 17:24; demonstrations at 17:30
    # The 16:40 ETA record retrieved at 17:27, after the arrival, does not change the status.
    stale = status_record("obs_0008", "16:40", "17:27", 13, eta="17:25")
    late = final.model_copy(update={"observations": (*final.observations, stale)})
    report = score_episode(late, history, private_case("goal_complete", DEV01_LIKE))
    assert report.violations == ()
    assert report.goal_complete is True
    assert all(p.passed for p in report.predicates)

    # A record observed after the arrival is newer evidence and does apply.
    newer = status_record("obs_0008", "17:26", "17:27", 13, code="cancelled", domain="unavailable")
    report = score_episode(
        final.model_copy(update={"observations": (*final.observations, newer)}), history
    )
    assert report.violations == (
        "equipment_before_arrival: demonstrations started at 17:30 while projector was "
        "unavailable (no arrival or available status observed by then)",
    )


def test_arrival_record_counts_whatever_its_observation_kind() -> None:
    """The engine applies an arrival record by its channel, not its observation kind."""
    final, history = _success()
    observations = tuple(
        rec.model_copy(
            update={"observation": rec.observation.model_copy(update={"kind": "notice"})}
        )
        if rec.observation.observation_id == "obs_0007"
        else rec
        for rec in final.observations
    )
    arrival_notice = final.model_copy(update={"observations": observations})
    assert score_episode(arrival_notice, history).violations == ()


def test_booked_equipment_reported_unavailable_at_start_is_a_violation() -> None:
    """A covering commitment does not make a start valid on equipment reported unavailable."""
    final, history = _backup_run()
    booked_elsewhere = status_record(
        "obs_0005",
        "16:46",
        "16:46",
        6,
        entity="backup_projector",
        code="booked_elsewhere",
        domain="unavailable",
    )
    unavailable = final.model_copy(update={"observations": (*final.observations, booked_elsewhere)})
    report = score_episode(unavailable, history)
    assert report.goal_complete is False
    assert report.violations == (
        "equipment_before_arrival: demonstrations started at 17:10 while backup_projector was "
        "unavailable (no arrival or available status observed by then)",
    )

    # An available status record keeps the committed start valid.
    confirmed = booked_elsewhere.model_copy(
        update={
            "structured": StatusFacts(
                fact="availability",
                status_code="available",
                domain_status="available",
                reported_eta=None,
            )
        }
    )
    ok = final.model_copy(update={"observations": (*final.observations, confirmed)})
    assert score_episode(ok, history).violations == ()
    # Without the commitment the start is still a booking violation.
    uncommitted = final.model_copy(update={"commitments": ()})
    assert any(
        v.startswith("booking_without_commitment: demonstrations")
        for v in score_episode(uncommitted, history).violations
    )
