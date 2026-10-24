"""Finite candidate planner and campus adapter (contract section 10)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from plan_b.domain.adapters.base import DomainAdapter
from plan_b.domain.adapters.campus import CampusAdapter
from plan_b.domain.constraints import CHECK_IDS, REVALIDATE_PRECONDITION
from plan_b.domain.fixtures import load_public_scenario
from plan_b.domain.models import (
    AccessibilityRequirement,
    ActivityLifecycleEvent,
    ActorContext,
    CandidateCheck,
    CandidateResult,
    CheckInView,
    CommitmentView,
    EpisodeHistory,
    EvaluationRequest,
    EvaluationResult,
    EventStateView,
    HoldView,
    Hypothesis,
    PlanningSnapshot,
    ShiftTemplate,
    SubstituteTemplate,
    TimeWindow,
    ViewerInfo,
)
from plan_b.domain.projection import budget_view, initial_snapshot, with_effective_status

SCENARIO = load_public_scenario()
TZ = ZoneInfo("America/New_York")
ADAPTER = CampusAdapter()

KEEP = "Keep the current plan"
SWAP = "Swap demonstrations and skills exchange"
SUBSTITUTE = "Use backup_projector instead of projector for demonstrations"
SWAP_AND_SUBSTITUTE = f"{SWAP} + {SUBSTITUTE}"
SHIFT_DEMOS_LATER = "Shift demonstrations by +10 min"
SHIFT_DEMOS_EARLIER = "Shift demonstrations by -10 min"


def at(hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(2026, 11, 5, hour, minute, tzinfo=TZ).astimezone(UTC)


def window(start: str, end: str) -> TimeWindow:
    return TimeWindow(start=at(start), end=at(end))


def coordinator(**grant_update: Any) -> ActorContext:
    grant = next(g for g in SCENARIO.authority_grants if g.grant_id == "grant_coordinator_demo")
    if grant_update:
        grant = grant.model_copy(update=grant_update)
    return ActorContext(
        principal_id="agent_demo",
        role="coordinator_agent",
        grant=grant,
        grant_version=1,
        grant_valid=True,
        committed_used_cents=0,
        reserved_used_cents=0,
    )


def base() -> PlanningSnapshot:
    return initial_snapshot(SCENARIO)


def with_resource(snap: PlanningSnapshot, resource_id: str, **update: Any) -> PlanningSnapshot:
    resources = tuple(
        r.model_copy(update=update) if r.definition.resource_id == resource_id else r
        for r in snap.resources
    )
    return snap.model_copy(update={"resources": resources})


def with_eta(snap: PlanningSnapshot, hhmm: str) -> PlanningSnapshot:
    return with_resource(
        snap,
        "projector",
        status="expected",
        status_basis="status_observation",
        status_observation_id="obs_status_02",
        status_observed_at=at("16:40"),
        reported_eta=at(hhmm),
    )


def backup_hold(
    start: str = "17:10",
    end: str = "17:30",
    *,
    created: str = "16:44",
    expires: str = "16:54",
    actor_id: str = "agent_demo",
    hold_id: str = "hold_0001",
) -> HoldView:
    return HoldView(
        hold_id=hold_id,
        resource_id="backup_projector",
        activity_id="demonstrations",
        quantity=1,
        window=window(start, end),
        created_at=at(created),
        expires_at=at(expires),
        commitment_cutoff=at(start) - (at("17:10") - at("16:55")),
        reserved_cents=3500,
        hold_fee_cents=0,
        status="active",
        effective_status="active",
        actor_id=actor_id,
        grant_id="grant_coordinator_demo",
        commitment_id=None,
        terminal_at=None,
        created_receipt_id="rcpt_hold_0001",
        terminal_receipt_id=None,
    )


def with_holds(snap: PlanningSnapshot, holds: tuple[HoldView, ...]) -> PlanningSnapshot:
    effective = with_effective_status(holds, snap.clock)
    return snap.model_copy(
        update={
            "holds": effective,
            "budget": budget_view(snap.goal, effective, snap.commitments),
        }
    )


def with_checkin(
    snap: PlanningSnapshot, resource_id: str, start: str, end: str
) -> PlanningSnapshot:
    checkin = CheckInView(
        checkin_id=f"chk_{resource_id}",
        principal_id=f"participant_{resource_id}",
        resource_id=resource_id,
        at=snap.clock,
        available=window(start, end),
        observation_id=None,
        channel="participant_session",
    )
    return snap.model_copy(update={"checkins": (*snap.checkins, checkin)})


def with_templates(snap: PlanningSnapshot, *templates: Any) -> PlanningSnapshot:
    planning = snap.planning.model_copy(update={"edit_templates": templates})
    return snap.model_copy(update={"planning": planning})


def evaluate(
    snap: PlanningSnapshot,
    actor: ActorContext | None = None,
    request: EvaluationRequest | None = None,
    evaluation_id: str = "eval_0001",
) -> EvaluationResult:
    return ADAPTER.evaluate(
        snap, actor or coordinator(), request or EvaluationRequest(), evaluation_id
    )


def by_label(result: EvaluationResult, label: str) -> CandidateResult:
    matches = [c for c in result.candidates if c.label == label]
    assert len(matches) == 1, f"{label!r} not found once in {[c.label for c in result.candidates]}"
    return matches[0]


def check(candidate: CandidateResult, constraint_id: str) -> CandidateCheck:
    return next(c for c in candidate.checks if c.constraint_id == constraint_id)


def failed_ids(candidate: CandidateResult) -> set[str]:
    return {c.constraint_id for c in candidate.checks if c.status == "failed"}


# ---------------------------------------------------------------------------


def test_adapter_identity_and_config() -> None:
    adapter: DomainAdapter = ADAPTER
    assert adapter.adapter_id == "campus/1.0.0"
    assert adapter.profile_ids == ("campus_showcase", "community_skills_exchange")
    assert ADAPTER.validate_config(SCENARIO) == []
    bad_planning = SCENARIO.planning.model_copy(
        update={
            "edit_templates": (
                *SCENARIO.planning.edit_templates,
                ShiftTemplate(template="shift", activity_id="nope", offsets_minutes=(0,)),
            ),
            "tie_breaks": ("objective_total", "vibes"),
        }
    )
    problems = ADAPTER.validate_config(SCENARIO.model_copy(update={"planning": bad_planning}))
    assert any("unknown activity nope" in p for p in problems)
    assert any("zero offset" in p for p in problems)
    assert any("tie-break vibes" in p for p in problems)


def test_initial_state_keeps_plan_under_arrival_assumption() -> None:
    result = evaluate(base())
    keep = by_label(result, KEEP)
    assert result.keep_candidate_id == keep.candidate_id
    assert keep.edits == ()
    assert keep.constraint_status == "feasible_under_assumptions"
    assert keep.applicable_now
    assert keep.rank == 1
    assert result.best_candidate_id == keep.candidate_id
    assert result.best_applicable_candidate_id == keep.candidate_id
    arrival = [a for a in keep.assumptions if a.kind == "arrival_by_start"]
    assert [a.entity_id for a in arrival] == ["projector"]
    declared = {a.entity_id for a in keep.assumptions if a.kind == "declared_availability"}
    assert declared == {"presenter", "facilitator"}
    assert keep.objective.total == 0
    assert keep.changed_activity_ids == ()
    assert keep.required_holds == ()
    assert keep.authorization.sufficient
    # Every documented check is present, in table order, and none is a placeholder pass.
    assert tuple(c.constraint_id for c in keep.checks) == CHECK_IDS
    assert check(keep, "accessibility").status == "not_applicable"
    assert check(keep, "substitute_compatibility").status == "not_applicable"
    assert check(keep, "no_past_change").status == "not_applicable"
    assert check(keep, "started_history").status == "passed"
    assert check(keep, "arrival_assumptions").status == "passed"
    assert keep.execution_preconditions[-1] == REVALIDATE_PRECONDITION
    assert (
        "Observe projector arrival before demonstrations start at 17:10 (America/New_York)."
        in keep.execution_preconditions
    )
    assert result.generated_count == 16
    assert result.evaluated_count == 16
    assert not result.truncated
    assert not result.hypothetical
    assert result.infeasibility is None
    # A candidate always lists every activity of the active plan.
    for candidate in result.candidates:
        assert [a.activity_id for a in candidate.assignments] == [
            a.activity_id for a in SCENARIO.initial_state.assignments
        ]


def test_reported_eta_1725_prefers_swap() -> None:
    result = evaluate(with_eta(base(), "17:25"))
    keep = by_label(result, KEEP)
    assert keep.constraint_status == "infeasible"
    assert failed_ids(keep) == {"arrival_assumptions"}
    assert keep.rank is None and not keep.applicable_now

    swap = by_label(result, SWAP)
    assert swap.constraint_status == "feasible_under_assumptions"
    assert swap.applicable_now
    assert swap.rank == 1
    assert result.best_candidate_id == swap.candidate_id
    assert result.best_applicable_candidate_id == swap.candidate_id
    assert swap.changed_activity_ids == ("demonstrations", "skills_exchange")
    demos = next(a for a in swap.assignments if a.activity_id == "demonstrations")
    skills = next(a for a in swap.assignments if a.activity_id == "skills_exchange")
    assert (demos.start, demos.end) == (at("17:30"), at("17:50"))
    assert (skills.start, skills.end) == (at("17:10"), at("17:30"))
    arrival = next(a for a in swap.assumptions if a.kind == "arrival_by_start")
    assert arrival.basis_ref == "obs_status_02"
    assert swap.objective.total == 70
    assert swap.objective.weighted == {
        "start_shift_minutes": 40,
        "changed_activities": 20,
        "additional_committed_cents": 0,
        "optional_activities_removed": 0,
        "participant_notifications": 10,
    }

    substitute = by_label(result, SUBSTITUTE)
    assert substitute.constraint_status == "feasible_under_assumptions"
    assert not substitute.applicable_now
    assert substitute.rank == 2
    assert substitute.objective.total == 150
    assert substitute.incremental_committed_cents == 3500
    assert [m.kind for m in substitute.authorization.missing] == ["committed_spend_limit"]
    missing = substitute.authorization.missing[0]
    assert (missing.field, missing.current_value, missing.required_value) == (
        "max_total_committed_cents",
        0,
        3500,
    )
    assert "increase committed spending" in missing.detail
    (hold,) = substitute.required_holds
    assert hold.resource_id == "backup_projector" and hold.bound_hold_id is None
    assert hold.window == window("17:10", "17:30")
    assert hold.commitment_cutoff == at("16:55")
    assert any(a.kind == "catalog_availability" for a in substitute.assumptions)
    assert (
        "Acquire a live hold on backup_projector covering 17:10-17:30 before applying; "
        "commitment cutoff 16:55 (America/New_York)." in substitute.execution_preconditions
    )
    # Ranked feasible candidates come first in rank order, the rest by signature.
    ranks = [c.rank for c in result.candidates]
    feasible = [r for r in ranks if r is not None]
    assert feasible == list(range(1, len(feasible) + 1))
    rest = [c.signature for c in result.candidates if c.rank is None]
    assert rest == sorted(rest)
    assert ranks[: len(feasible)] == feasible


def test_reported_eta_1745_needs_bound_backup_hold() -> None:
    snap = with_eta(base(), "17:45")
    result = evaluate(snap)
    assert failed_ids(by_label(result, SWAP)) == {"arrival_assumptions"}
    substitute = by_label(result, SUBSTITUTE)
    assert result.best_candidate_id == substitute.candidate_id
    assert result.best_applicable_candidate_id is None
    assert {c.label for c in result.candidates if c.rank is not None} == {
        SUBSTITUTE,
        SWAP_AND_SUBSTITUTE,
    }

    held = with_holds(snap.model_copy(update={"clock": at("16:45")}), (backup_hold(),))
    raised = coordinator(max_total_committed_cents=3500)
    result = evaluate(held, raised)
    substitute = by_label(result, SUBSTITUTE)
    assert substitute.applicable_now
    assert result.best_applicable_candidate_id == substitute.candidate_id
    (required,) = substitute.required_holds
    assert required.bound_hold_id == "hold_0001"
    assert substitute.incremental_committed_cents == 3500
    budget = check(substitute, "budget")
    assert budget.status == "passed"
    assert "reserved 3500 - converted holds 3500 + incremental 3500 = 3500" in budget.detail
    assert check(substitute, "resource_capacity").status == "passed"
    assert any("hold_0001" in line for line in substitute.execution_preconditions)

    # A hold by another actor, or one that does not cover the window, is not bound.
    other = with_holds(held, (backup_hold(actor_id="organizer_demo"),))
    assert by_label(evaluate(other, raised), SUBSTITUTE).required_holds[0].bound_hold_id is None
    short = with_holds(held, (backup_hold("17:10", "17:20"),))
    short_sub = by_label(evaluate(short, raised), SUBSTITUTE)
    assert short_sub.required_holds[0].bound_hold_id is None
    assert not short_sub.applicable_now
    # The uncovered hold still occupies the single backup projector.
    assert check(short_sub, "resource_capacity").status == "failed"


def test_commitment_cutoff_passed() -> None:
    snap = with_eta(base(), "17:45").model_copy(update={"clock": at("16:56")})
    substitute = by_label(evaluate(snap), SUBSTITUTE)
    cutoff = check(substitute, "commitment_cutoff")
    assert cutoff.status == "failed"
    assert "16:55" in cutoff.detail
    assert substitute.constraint_status == "infeasible"
    # At 16:54 the same candidate is still feasible.
    early = with_eta(base(), "17:45").model_copy(update={"clock": at("16:54")})
    assert by_label(evaluate(early), SUBSTITUTE).constraint_status == "feasible_under_assumptions"


def test_nothing_feasible_reports_infeasibility() -> None:
    snap = with_resource(
        base(), "projector", status="unavailable", status_basis="status_observation"
    )
    snap = with_resource(
        snap, "backup_projector", status="unavailable", status_basis="status_observation"
    )
    result = evaluate(snap)
    assert all(c.constraint_status == "infeasible" for c in result.candidates)
    assert all(c.rank is None for c in result.candidates)
    assert result.best_candidate_id is None
    assert result.best_applicable_candidate_id is None
    summary = result.infeasibility
    assert summary is not None
    assert "resource_status" in summary.blocking_constraints
    assert list(summary.blocking_constraints) == sorted(set(summary.blocking_constraints))
    assert "most common blocker is resource_status" in summary.detail
    assert "16 candidates generated" in summary.declared_action_space
    assert "at most 2 combined edits" in summary.declared_action_space
    assert "substitute(demonstrations: projector -> backup_projector)" in (
        summary.declared_action_space
    )


def test_invalid_substitute_fails_compatibility() -> None:
    snap = with_templates(
        base(),
        SubstituteTemplate(
            template="substitute",
            activity_id="demonstrations",
            resource_id="projector",
            substitute_ids=("host", "ghost_projector"),
        ),
    )
    result = evaluate(snap)
    host = by_label(result, "Use host instead of projector for demonstrations")
    compat = check(host, "substitute_compatibility")
    assert compat.status == "failed"
    assert "not an approved substitute" in compat.detail
    assert "lacks projector's capabilities projection" in compat.detail
    ghost = by_label(result, "Use ghost_projector instead of projector for demonstrations")
    assert "ghost_projector is not registered" in check(ghost, "substitute_compatibility").detail
    assert ghost.constraint_status == "infeasible"
    # Two substitutions of the same (activity, resource) are never combined.
    assert result.generated_count == 3


def test_overlapping_shift_and_dependency() -> None:
    result = evaluate(base())
    later = by_label(result, SHIFT_DEMOS_LATER)
    assert check(later, "program_exclusivity").status == "failed"
    assert (
        "demonstrations 17:20-17:40 overlaps skills_exchange 17:30-17:50"
        in check(later, "program_exclusivity").detail
    )
    earlier = by_label(result, SHIFT_DEMOS_EARLIER)
    assert check(earlier, "dependencies").status == "failed"
    assert "before predecessor welcome ends at 17:10" in check(earlier, "dependencies").detail
    assert check(earlier, "activity_windows").status == "failed"


def test_started_setup_cannot_move() -> None:
    snap = with_templates(
        base(), ShiftTemplate(template="shift", activity_id="setup", offsets_minutes=(10,))
    )
    result = evaluate(snap)
    moved = by_label(result, "Shift setup by +10 min")
    assert check(moved, "started_history").status == "failed"
    assert check(moved, "no_past_change").status == "failed"
    assert moved.constraint_status == "infeasible"


def test_participant_availability_from_checkin() -> None:
    snap = with_checkin(base(), "facilitator", "17:00", "17:40")
    result = evaluate(snap)
    keep = by_label(result, KEEP)
    availability = check(keep, "participant_availability")
    assert availability.status == "failed"
    assert "facilitator" in availability.entity_ids
    assert "not covering skills_exchange 17:30-17:50" in availability.detail
    assert by_label(result, SUBSTITUTE).constraint_status == "infeasible"
    swap = by_label(result, SWAP)
    assert check(swap, "participant_availability").status == "passed"
    assert swap.constraint_status == "feasible_under_assumptions"
    assert result.best_applicable_candidate_id == swap.candidate_id
    # The checked-in person needs no declared-availability assumption.
    assert all(a.entity_id != "facilitator" for a in swap.assumptions)


def test_accessibility_requirements() -> None:
    def with_requirements(*requirements: AccessibilityRequirement) -> PlanningSnapshot:
        snap = base()
        goal = snap.goal.model_copy(update={"accessibility_requirements": requirements})
        return snap.model_copy(update={"goal": goal})

    unsupported = AccessibilityRequirement(
        requirement_id="acc_captions",
        kind="live_captioning",
        activity_ids=("demonstrations",),
        detail="Live captions during demonstrations",
    )
    keep = by_label(evaluate(with_requirements(unsupported)), KEEP)
    assert check(keep, "accessibility").status == "unsupported"
    assert keep.constraint_status == "unknown"
    assert keep.rank is None and not keep.applicable_now
    assert keep.rationale.startswith("No hard check fails")

    missing = AccessibilityRequirement(
        requirement_id="acc_loop",
        kind="venue_capability",
        activity_ids=("welcome",),
        capability="hearing_loop",
        detail="Hearing loop in the venue",
    )
    keep = by_label(evaluate(with_requirements(missing)), KEEP)
    assert check(keep, "accessibility").status == "failed"
    assert keep.constraint_status == "infeasible"

    met = missing.model_copy(update={"capability": "main_room"})
    keep = by_label(evaluate(with_requirements(met)), KEEP)
    assert check(keep, "accessibility").status == "passed"

    keep = by_label(evaluate(base()), KEEP)
    assert check(keep, "accessibility").status == "not_applicable"


def test_candidate_cap_ids_and_determinism() -> None:
    snap = with_eta(base(), "17:25")
    first = evaluate(snap, evaluation_id="eval_0007")
    second = evaluate(snap, evaluation_id="eval_0007")
    assert first == second
    for candidate in first.candidates:
        sig8 = candidate.signature[:8]
        assert re.fullmatch(r"[0-9a-f]{64}", candidate.signature)
        assert candidate.candidate_id == f"cand_0007_{sig8}"
        assert candidate.report_id == f"rpt_0007_{sig8}"
    assert len({c.candidate_id for c in first.candidates}) == len(first.candidates)

    planning = snap.planning.model_copy(update={"candidate_cap": 5})
    capped = evaluate(snap.model_copy(update={"planning": planning}))
    assert capped.truncated
    assert capped.generated_count == 16
    assert capped.evaluated_count == 5
    assert len(capped.candidates) == 5
    labels = {c.label for c in capped.candidates}
    assert labels == {
        KEEP,
        SWAP,
        SHIFT_DEMOS_EARLIER,
        SHIFT_DEMOS_LATER,
        "Shift skills exchange by -10 min",
    }

    # Template restriction: keep is always generated first.
    only_swap = evaluate(snap, request=EvaluationRequest(templates=("swap",)))
    assert only_swap.templates == ("keep", "swap")
    assert [c.label for c in only_swap.candidates] == [SWAP, KEEP]

    with pytest.raises(ValueError):
        evaluate(snap, evaluation_id="evaluation-7")


def test_revalidate_matches_and_detects_hold_expiry() -> None:
    snap = with_holds(
        with_eta(base(), "17:45").model_copy(update={"clock": at("16:45")}), (backup_hold(),)
    )
    raised = coordinator(max_total_committed_cents=3500)
    result = evaluate(snap, raised)
    for candidate in result.candidates:
        assert ADAPTER.revalidate(snap, raised, candidate) == candidate.model_copy(
            update={"rank": None}
        )

    substitute = by_label(result, SUBSTITUTE)
    assert substitute.applicable_now
    expired_hold = backup_hold().model_copy(update={"effective_status": "expired"})
    later = snap.model_copy(update={"holds": (expired_hold,)})
    fresh = ADAPTER.revalidate(later, raised, substitute)
    assert fresh.candidate_id == substitute.candidate_id
    assert fresh.signature == substitute.signature
    assert fresh.edits == substitute.edits
    assert fresh.assignments == substitute.assignments
    assert fresh.label == substitute.label
    assert fresh.rank is None
    assert fresh.required_holds[0].bound_hold_id is None
    assert not fresh.applicable_now

    # The clock passing expires_at also unbinds the hold, even before expiry processing.
    at_expiry = snap.model_copy(update={"clock": at("16:54")})
    assert not ADAPTER.revalidate(at_expiry, raised, substitute).applicable_now


def test_hypotheses_are_never_applicable() -> None:
    request = EvaluationRequest(
        hypotheses=(
            Hypothesis(
                resource_id="projector",
                assume_ready_at=at("17:25"),
                label="claimed ETA 17:25",
            ),
        )
    )
    result = evaluate(base(), request=request)
    assert result.hypothetical
    assert result.hypotheses == request.hypotheses
    assert not any(c.applicable_now for c in result.candidates)
    assert result.best_applicable_candidate_id is None
    keep = by_label(result, KEEP)
    assert failed_ids(keep) == {"arrival_assumptions"}
    assert "hypothetical ETA 17:25" in check(keep, "arrival_assumptions").detail
    swap = by_label(result, SWAP)
    assert swap.constraint_status == "feasible_under_assumptions"
    assert result.best_candidate_id == swap.candidate_id
    assert any(a.kind == "hypothesis" for a in swap.assumptions)
    arrival = next(a for a in swap.assumptions if a.kind == "arrival_by_start")
    assert arrival.basis_ref == "claimed ETA 17:25"
    assert any("re-evaluate without hypotheses" in p for p in swap.execution_preconditions)

    status_request = EvaluationRequest(
        hypotheses=(
            Hypothesis(resource_id="projector", assume_status="unavailable", label="cancelled"),
        )
    )
    keep = by_label(evaluate(base(), request=status_request), KEEP)
    assert "resource_status" in failed_ids(keep)


def test_authorization_scope_and_grant_validity() -> None:
    snap = with_eta(base(), "17:25")
    narrow = coordinator(activity_ids=("setup", "welcome", "closing"))
    swap = by_label(evaluate(snap, narrow), SWAP)
    assert swap.constraint_status == "feasible_under_assumptions"
    assert not swap.applicable_now
    assert {m.kind for m in swap.authorization.missing} == {"activity_out_of_scope"}

    invalid = coordinator().model_copy(update={"grant_valid": False})
    swap = by_label(evaluate(snap, invalid), SWAP)
    assert "grant_invalid" in {m.kind for m in swap.authorization.missing}

    organizer_grant = next(
        g for g in SCENARIO.authority_grants if g.grant_id == "grant_organizer_demo"
    )
    organizer = ActorContext(
        principal_id="organizer_demo",
        role="organizer",
        grant=organizer_grant,
        grant_version=1,
        grant_valid=True,
        committed_used_cents=0,
        reserved_used_cents=0,
    )
    swap = by_label(evaluate(snap, organizer), SWAP)
    assert {m.kind for m in swap.authorization.missing} == {"tool_not_granted"}


def test_evaluation_has_no_side_effects() -> None:
    snap = with_holds(with_eta(base(), "17:45"), (backup_hold(),))
    before = snap.model_dump(mode="json")
    evaluate(snap)
    assert snap.model_dump(mode="json") == before


def test_check_readiness_delegates_in_execution_mode() -> None:
    snap = base()
    report = ADAPTER.check_readiness(snap, "demonstrations", at("17:10"))
    assert report.mode == "execution"
    assert not report.ready
    assert any("projector not yet observed" in u for u in report.unmet)
    with pytest.raises(KeyError):
        ADAPTER.check_readiness(snap, "unknown_activity", at("17:10"))


def _final_view(*, closing_completed: bool) -> EventStateView:
    snap = base()
    seq = 0
    activities = []
    for view in snap.activities:
        assignment = view.assignment
        assert assignment is not None
        aid = view.definition.activity_id
        start, end = assignment.start, assignment.end
        events = []
        seq += 1
        events.append(
            ActivityLifecycleEvent(
                seq=seq, activity_id=aid, state="started", at=start, revision=seq
            )
        )
        lifecycle = "completed"
        if aid == "closing" and not closing_completed:
            lifecycle = "failed"
            seq += 1
            events[0] = ActivityLifecycleEvent(
                seq=seq,
                activity_id=aid,
                state="failed",
                at=start,
                revision=seq,
                reasons=("host has not checked in for 17:50",),
            )
        else:
            seq += 1
            events.append(
                ActivityLifecycleEvent(
                    seq=seq, activity_id=aid, state="completed", at=end, revision=seq
                )
            )
        activities.append(
            view.model_copy(
                update={"lifecycle": lifecycle, "history": tuple(events), "readiness": None}
            )
        )
    return EventStateView(
        runtime_version="1.0.0",
        episode_id="ep_test",
        event_id=snap.event_id,
        scenario_id=SCENARIO.scenario_id,
        profile_id=SCENARIO.profile_id,
        fictional=True,
        sandbox_label="Sandbox",
        timezone=SCENARIO.timezone,
        episode_status="closed",
        clock=at("18:00"),
        revision=20,
        goal=snap.goal,
        goal_history=(snap.goal,),
        activities=tuple(activities),
        plan=snap.plan,
        plan_history=(snap.plan,),
        resources=snap.resources,
        holds=(),
        commitments=(),
        checkins=snap.checkins,
        budget=snap.budget.model_copy(update={"committed_cents": 3500, "remaining_cents": 11500}),
        grants=(),
        grant_history=(),
        observations=(),
        receipts=(),
        attempts=(),
        decisions=(),
        latest_evaluation=None,
        transitions=(),
        declared_assumptions=SCENARIO.declared_assumptions,
        tool_durations_minutes=SCENARIO.tool_durations_minutes,
        viewer=ViewerInfo(
            principal_id="moderator", role="moderator", display_name="Moderator", grant_id=None
        ),
    )


def test_score_outcome_from_visible_state() -> None:
    history = EpisodeHistory(tool_calls=(), transitions=(), decisions=(), receipts=())
    complete = ADAPTER.score_outcome(_final_view(closing_completed=True), history)
    assert complete.goal_attained is True and complete.unmet == ()
    assert tuple(a.activity_id for a in complete.activities) == SCENARIO.goal.required_activity_ids
    closing = next(a for a in complete.activities if a.activity_id == "closing")
    assert closing.lifecycle == "completed" and closing.completed_at == at("18:00")
    # Attainment is not success: starts made without their evidence are executed violations.
    assert sorted({v.category for v in complete.violations}) == [
        "equipment_before_arrival",
        "role_not_checked_in",
    ]

    incomplete = ADAPTER.score_outcome(_final_view(closing_completed=False), history)
    assert incomplete.goal_attained is False
    assert incomplete.unmet == ("closing is failed",)
    closing = next(a for a in incomplete.activities if a.activity_id == "closing")
    assert closing.lifecycle == "failed"
    assert closing.failure_reasons == ("host has not checked in for 17:50",)


def test_failed_predecessor_blocks_dependents() -> None:
    snap = with_eta(base(), "17:45").model_copy(update={"clock": at("17:11")})
    activities = tuple(
        v.model_copy(update={"lifecycle": "failed", "readiness": None})
        if v.definition.activity_id == "demonstrations"
        else v.model_copy(update={"lifecycle": "completed", "readiness": None})
        if v.definition.activity_id in ("setup", "welcome")
        else v
        for v in snap.activities
    )
    result = evaluate(snap.model_copy(update={"activities": activities}))
    assert result.best_candidate_id is None
    for candidate in result.candidates:
        assert "dependencies" in failed_ids(candidate)
    keep = by_label(result, KEEP)
    assert "predecessor demonstrations of closing is failed" in check(keep, "dependencies").detail
    assert result.infeasibility is not None
    assert "dependencies" in result.infeasibility.blocking_constraints


def test_committed_substitute_in_active_plan() -> None:
    snap = with_eta(base(), "17:45").model_copy(update={"clock": at("16:50")})
    assignments = tuple(
        a.model_copy(update={"resource_ids": ("main_room", "backup_projector", "presenter")})
        if a.activity_id == "demonstrations"
        else a
        for a in snap.plan.assignments
    )
    plan = snap.plan.model_copy(update={"plan_version": 2, "assignments": assignments})
    commitment = CommitmentView(
        commitment_id="cmt_0001",
        resource_id="backup_projector",
        activity_id="demonstrations",
        window=window("17:10", "17:30"),
        committed_cents=3500,
        source_hold_id="hold_0001",
        plan_version=2,
        status="active",
        created_at=at("16:49"),
        receipt_id="rcpt_0006",
        actor_id="agent_demo",
        grant_id="grant_coordinator_demo",
    )
    snap = snap.model_copy(
        update={
            "plan": plan,
            "commitments": (commitment,),
            "budget": budget_view(snap.goal, (), (commitment,)),
        }
    )
    result = evaluate(snap)
    keep = by_label(result, KEEP)
    assert keep.constraint_status == "feasible_under_assumptions"
    assert keep.applicable_now and keep.rank == 1
    assert keep.required_holds == () and keep.incremental_committed_cents == 0
    assert "committed (cmt_0001)" in check(keep, "commitment_cutoff").detail
    # The commitment belongs to this assignment, so it is not counted twice.
    assert check(keep, "resource_capacity").status == "passed"
    substitute = by_label(result, SUBSTITUTE)
    assert (
        "projector is not assigned to demonstrations in the active plan"
        in check(substitute, "substitute_compatibility").detail
    )
    assert by_label(result, SWAP_AND_SUBSTITUTE).constraint_status == "infeasible"
    # Moving demonstrations off the committed window needs a fresh booking ...
    swap = by_label(result, SWAP)
    assert swap.incremental_committed_cents == 3500
    assert swap.required_holds[0].window == window("17:30", "17:50")
    # ... and an overlapping move conflicts with the commitment on the single backup.
    later = by_label(result, SHIFT_DEMOS_LATER)
    assert check(later, "resource_capacity").status == "failed"
    assert "backup_projector would need 2 units" in check(later, "resource_capacity").detail


def test_overdue_eta_is_disclosed() -> None:
    snap = with_eta(base(), "16:45").model_copy(update={"clock": at("16:50")})
    keep = by_label(evaluate(snap), KEEP)
    assert keep.constraint_status == "feasible_under_assumptions"
    arrival = next(a for a in keep.assumptions if a.kind == "arrival_by_start")
    assert "has already passed without an observed arrival" in arrival.text


def test_cutoff_is_judged_when_the_apply_takes_effect() -> None:
    """At cutoff - 1 minute an apply (1-minute duration) would execute at the cutoff."""
    raised = coordinator(max_total_committed_cents=3500)
    hold = backup_hold(created="16:50", expires="17:00")
    snap = with_holds(with_eta(base(), "17:45").model_copy(update={"clock": at("16:54")}), (hold,))
    # Judged at the clock (no effect time given) the substitution is applicable ...
    assert by_label(evaluate(snap, raised), SUBSTITUTE).applicable_now
    # ... but an apply issued at 16:54 takes effect at 16:55, the cutoff.
    later = evaluate(snap.model_copy(update={"effective_at": at("16:55")}), raised)
    substitute = by_label(later, SUBSTITUTE)
    cutoff = check(substitute, "commitment_cutoff")
    assert cutoff.status == "failed"
    assert "16:55 is not after 16:55, when an apply issued at 16:54 takes effect" in cutoff.detail
    assert substitute.constraint_status == "infeasible" and not substitute.applicable_now
    assert later.best_applicable_candidate_id != substitute.candidate_id
    # apply_plan revalidates at its execution time (effective_at = clock) with the same verdict.
    executed = snap.model_copy(update={"clock": at("16:55")})
    assert not ADAPTER.revalidate(executed, raised, substitute).applicable_now


def test_hold_must_be_live_when_the_apply_takes_effect() -> None:
    raised = coordinator(max_total_committed_cents=3500)
    short = backup_hold(created="16:41", expires="16:51")
    snap = with_holds(with_eta(base(), "17:45").model_copy(update={"clock": at("16:50")}), (short,))
    assert by_label(evaluate(snap, raised), SUBSTITUTE).required_holds[0].bound_hold_id
    # The hold expires at 16:51, exactly when an apply issued at 16:50 would execute.
    lapsing = evaluate(snap.model_copy(update={"effective_at": at("16:51")}), raised)
    substitute = by_label(lapsing, SUBSTITUTE)
    assert substitute.required_holds[0].bound_hold_id is None
    assert not substitute.applicable_now
    # Its exposure is returned by then, so the budget does not count it ...
    budget = check(substitute, "budget")
    assert "reserved 0 - converted holds 0 + incremental 3500 = 3500" in budget.detail
    assert "excludes 3500 cents of holds that expire by 16:51" in budget.detail
    # ... and it no longer occupies the backup projector.
    assert check(substitute, "resource_capacity").status == "passed"


def test_no_past_change_uses_the_apply_effect_time() -> None:
    snap = with_eta(base(), "17:25").model_copy(update={"clock": at("17:09")})
    # The swap moves skills_exchange to 17:10: valid at 17:09, past once the apply executes.
    assert check(by_label(evaluate(snap), SWAP), "no_past_change").status == "passed"
    swap = by_label(evaluate(snap.model_copy(update={"effective_at": at("17:10")})), SWAP)
    past = check(swap, "no_past_change")
    assert past.status == "failed"
    assert past.entity_ids == ("skills_exchange",)
    assert "skills_exchange would start at 17:10, not after 17:10, when an apply" in past.detail
    assert not swap.applicable_now
    # An effect time before the clock is never used: checks are never weaker than at the clock.
    backwards = snap.model_copy(update={"effective_at": at("17:00")})
    assert evaluate(backwards) == evaluate(snap)


def test_grant_must_be_valid_when_the_apply_takes_effect() -> None:
    snap = with_eta(base(), "17:25").model_copy(update={"clock": at("17:09")})
    expiring = coordinator(expires_at=at("17:10"))
    assert by_label(evaluate(snap, expiring), KEEP).authorization.sufficient
    effective = snap.model_copy(update={"effective_at": at("17:10")})
    keep = by_label(evaluate(effective, expiring), KEEP)
    assert [m.kind for m in keep.authorization.missing] == ["grant_invalid"]
    (missing,) = keep.authorization.missing
    assert "expires at 17:10, not after 17:10, when an apply" in missing.detail
    assert not keep.applicable_now


def test_participant_availability_uses_the_latest_checkin() -> None:
    """A later, narrower check-in supersedes an earlier, wider one (as in readiness)."""
    wide = with_checkin(base(), "presenter", "16:50", "18:00")
    assert check(by_label(evaluate(wide), KEEP), "participant_availability").status == "passed"
    narrow = CheckInView(
        checkin_id="chk_presenter_2",
        principal_id="participant_presenter",
        resource_id="presenter",
        at=at("16:50"),  # same minute: the later record wins
        available=window("16:50", "17:15"),
        observation_id=None,
        channel="participant_session",
    )
    superseded = wide.model_copy(update={"checkins": (*wide.checkins, narrow)})
    availability = check(by_label(evaluate(superseded), KEEP), "participant_availability")
    assert availability.status == "failed"
    assert "presenter's latest check-in (16:50) is available 16:50-17:15" in availability.detail


def _with_requirements(
    snap: PlanningSnapshot, *requirements: AccessibilityRequirement
) -> PlanningSnapshot:
    goal = snap.goal.model_copy(update={"accessibility_requirements": requirements})
    return snap.model_copy(update={"goal": goal})


def test_accessibility_without_a_subject_is_not_applicable() -> None:
    step_free = AccessibilityRequirement(
        requirement_id="acc_step_free",
        kind="venue_capability",
        activity_ids=(),
        capability="step_free_access",
        detail="Step-free access",
    )
    # main_room lacks step_free_access, but no activity is subject: never a vacuous pass.
    keep = by_label(evaluate(_with_requirements(base(), step_free)), KEEP)
    accessibility = check(keep, "accessibility")
    assert accessibility.status == "not_applicable"
    assert accessibility.detail == "acc_step_free concerns no activity still to run"

    # The same holds for a requirement scoped only to activities that have finished.
    snap = base()
    activities = tuple(
        v.model_copy(update={"lifecycle": "completed", "readiness": None})
        if v.definition.activity_id == "setup"
        else v
        for v in snap.activities
    )
    finished = step_free.model_copy(update={"activity_ids": ("setup",)})
    snap = _with_requirements(snap.model_copy(update={"activities": activities}), finished)
    assert check(by_label(evaluate(snap), KEEP), "accessibility").status == "not_applicable"

    # Beside a requirement that is checked and met, the check passes and names both.
    met = AccessibilityRequirement(
        requirement_id="acc_room",
        kind="venue_capability",
        activity_ids=("welcome",),
        capability="main_room",
        detail="Main room",
    )
    keep = by_label(evaluate(_with_requirements(base(), met, step_free)), KEEP)
    accessibility = check(keep, "accessibility")
    assert accessibility.status == "passed"
    assert accessibility.detail == (
        "acc_room: welcome venue provides main_room; "
        "acc_step_free concerns no activity still to run"
    )


def test_validate_config_rejects_requirement_without_activities() -> None:
    requirement = AccessibilityRequirement(
        requirement_id="acc_step_free",
        kind="venue_capability",
        activity_ids=(),
        capability="step_free_access",
        detail="Step-free access",
    )
    goal = SCENARIO.goal.model_copy(update={"accessibility_requirements": (requirement,)})
    problems = ADAPTER.validate_config(SCENARIO.model_copy(update={"goal": goal}))
    assert problems == ["accessibility requirement acc_step_free lists no activity"]
