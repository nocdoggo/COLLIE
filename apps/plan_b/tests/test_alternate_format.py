"""Approved alternate formats (contract section 10): candidate generation, the combination rule,
duration and resource effects, revalidation and apply through the real executor, execution
readiness and the scored final state.

The shipped fixture configures no alternate format, so these tests add templates to a copy of
it: a scratch ``PlanningConfig`` for the planner, and a scratch public fixture file for the
store and executor (the repository fixture is never edited).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from itertools import combinations
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import plan_b.domain.fixtures as fixtures
from plan_b.domain.adapters.campus import CampusAdapter
from plan_b.domain.candidates import enabled_templates, generate_edit_lists, single_edits
from plan_b.domain.models import (
    ActorContext,
    AlternateFormatTemplate,
    CandidateCheck,
    CandidateResult,
    Edit,
    EvaluationRequest,
    EvaluationResult,
    PlanningSnapshot,
    PublicScenario,
)
from plan_b.domain.projection import initial_snapshot
from plan_b.evaluation.scoring import score_episode
from plan_b.scenarios.runner import audit_view, episode_history
from plan_b.store.database import Database
from tests.conftest import Sandbox, at

SCENARIO = fixtures.load_public_scenario()
TZ = ZoneInfo("America/New_York")
ADAPTER = CampusAdapter()


def _format(
    activity_id: str, format_id: str, label: str, minutes: int, resources: tuple[str, ...]
) -> AlternateFormatTemplate:
    return AlternateFormatTemplate(
        template="alternate_format",
        activity_id=activity_id,
        format_id=format_id,
        label=label,
        duration_minutes=minutes,
        required_resources=resources,
    )


# Demonstrations without projection: shorter, and only the room and the presenter.
POSTER = _format("demonstrations", "poster_walk", "poster walk", 15, ("main_room", "presenter"))
# A shorter format that still needs the delayed projector.
SHORT_DEMO = _format(
    "demonstrations", "short_demo", "short demo", 15, ("main_room", "projector", "presenter")
)
# A format on the booking-required backup projector.
BACKUP_DEMO = _format(
    "demonstrations",
    "backup_demo",
    "backup demo",
    20,
    ("main_room", "backup_projector", "presenter"),
)
# A format too long for the demonstrations window (17:10-17:50).
LONG_DEMO = _format("demonstrations", "long_demo", "long demo", 45, ("main_room", "presenter"))
# A format on another activity.
CIRCLE = _format(
    "skills_exchange", "skills_circle", "skills circle", 15, ("main_room", "facilitator", "host")
)

POSTER_LABEL = "Use the poster walk format for demonstrations"
SHORT_LABEL = "Use the short demo format for demonstrations"
BACKUP_LABEL = "Use the backup demo format for demonstrations"
LONG_LABEL = "Use the long demo format for demonstrations"
CIRCLE_LABEL = "Use the skills circle format for skills exchange"
SWAP_LABEL = "Swap demonstrations and skills exchange"
SUBSTITUTE_LABEL = "Use backup_projector instead of projector for demonstrations"


def with_formats(*templates: AlternateFormatTemplate, **planning: Any) -> PublicScenario:
    """The public fixture with alternate-format templates appended to its edit templates."""
    config = SCENARIO.planning.model_copy(
        update={"edit_templates": (*SCENARIO.planning.edit_templates, *templates), **planning}
    )
    return SCENARIO.model_copy(update={"planning": config})


def with_formats_first(*templates: AlternateFormatTemplate, **planning: Any) -> PublicScenario:
    """The public fixture with alternate-format templates configured right after ``keep``, so
    every format is generated before the swap, the shifts and the substitution."""
    keep, *rest = SCENARIO.planning.edit_templates
    assert keep.template == "keep"
    config = SCENARIO.planning.model_copy(
        update={"edit_templates": (keep, *templates, *rest), **planning}
    )
    return SCENARIO.model_copy(update={"planning": config})


def delayed(scenario: PublicScenario, eta: str = "17:25") -> PlanningSnapshot:
    """Initial snapshot with the projector reported late (dev01's 17:25 ETA)."""
    snap = initial_snapshot(scenario)
    resources = tuple(
        r.model_copy(
            update={
                "status": "expected",
                "status_basis": "status_observation",
                "status_observation_id": "obs_status_02",
                "status_observed_at": at("16:40"),
                "reported_eta": at(eta),
            }
        )
        if r.definition.resource_id == "projector"
        else r
        for r in snap.resources
    )
    return snap.model_copy(update={"resources": resources})


def coordinator() -> ActorContext:
    grant = next(g for g in SCENARIO.authority_grants if g.grant_id == "grant_coordinator_demo")
    return ActorContext(
        principal_id="agent_demo",
        role="coordinator_agent",
        grant=grant,
        grant_version=1,
        grant_valid=True,
        committed_used_cents=0,
        reserved_used_cents=0,
    )


def evaluate(snap: PlanningSnapshot, request: EvaluationRequest | None = None) -> EvaluationResult:
    return ADAPTER.evaluate(snap, coordinator(), request or EvaluationRequest(), "eval_0001")


def by_label(result: EvaluationResult, label: str) -> CandidateResult:
    matches = [c for c in result.candidates if c.label == label]
    assert len(matches) == 1, f"{label!r} not found once in {[c.label for c in result.candidates]}"
    return matches[0]


def check(candidate: CandidateResult, constraint_id: str) -> CandidateCheck:
    return next(c for c in candidate.checks if c.constraint_id == constraint_id)


def failed_ids(candidate: CandidateResult) -> set[str]:
    return {c.constraint_id for c in candidate.checks if c.status == "failed"}


def span(candidate: CandidateResult, activity_id: str) -> tuple[str, str, tuple[str, ...]]:
    a = next(a for a in candidate.assignments if a.activity_id == activity_id)
    return (
        a.start.astimezone(TZ).strftime("%H:%M"),
        a.end.astimezone(TZ).strftime("%H:%M"),
        a.resource_ids,
    )


def format_activities(edits: tuple[Edit, ...] | list[dict[str, Any]]) -> list[str]:
    """Activity of each alternate-format edit, for stored (dict) or typed edits."""
    out: list[str] = []
    for e in edits:
        kind, ids = (
            (e["kind"], e["activity_ids"]) if isinstance(e, dict) else (e.kind, e.activity_ids)
        )
        if kind == "alternate_format":
            out.append(ids[0])
    return out


def documented_combination(edits: tuple[Edit, ...]) -> bool:
    """The combination rule as candidates.py documents it, restated independently."""
    timed = [aid for e in edits if e.kind in ("swap", "shift") for aid in e.activity_ids]
    substituted = [(e.activity_ids[0], e.resource_id) for e in edits if e.kind == "substitute"]
    formatted = format_activities(edits)
    return (
        len(timed) == len(set(timed))
        and len(substituted) == len(set(substituted))
        and len(formatted) == len(set(formatted))
        and not set(formatted) & {aid for aid, _ in substituted}
    )


# --------------------------------------------------------------------------- generation


def test_formats_are_valid_configuration() -> None:
    scenario = with_formats(POSTER, SHORT_DEMO, BACKUP_DEMO, LONG_DEMO, CIRCLE)
    assert ADAPTER.validate_config(scenario) == []
    # The same (activity, format) twice is a configuration error.
    problems = ADAPTER.validate_config(with_formats(POSTER, POSTER))
    assert any("repeats format poster_walk" in p for p in problems)


def test_generation_combines_formats_only_under_the_documented_rule() -> None:
    planning = with_formats(POSTER, SHORT_DEMO, CIRCLE, max_combined_edits=3).planning
    enabled = enabled_templates(planning, None)
    assert "alternate_format" in enabled
    singles = single_edits(planning, enabled)
    formats = [e for e in singles if e.kind == "alternate_format"]
    # Each configured format is one single edit, in configuration order.
    assert [(e.activity_ids, e.format_id) for e in formats] == [
        (("demonstrations",), "poster_walk"),
        (("demonstrations",), "short_demo"),
        (("skills_exchange",), "skills_circle"),
    ]
    menu = generate_edit_lists(planning, enabled)
    expected = [(), *((e,) for e in singles)]
    for size in (2, 3):
        expected.extend(c for c in combinations(singles, size) if documented_combination(c))
    assert list(menu) == expected

    # Two alternate formats of one activity are never combined, nor a format with a
    # substitution on the same activity; formats of different activities, and a format after
    # a timing edit of its activity, are.
    for edits in menu:
        per_activity = Counter(format_activities(edits))
        assert all(n == 1 for n in per_activity.values()), edits
    kinds_by_combo = {
        tuple(sorted((e.kind, e.format_id or e.resource_id or "") for e in edits)) for edits in menu
    }
    assert (("alternate_format", "poster_walk"), ("alternate_format", "short_demo")) not in (
        kinds_by_combo
    )
    assert not any(
        {e.kind for e in edits} >= {"substitute", "alternate_format"}
        and "demonstrations" in format_activities(edits)
        for edits in menu
    )
    assert (("alternate_format", "poster_walk"), ("alternate_format", "skills_circle")) in (
        kinds_by_combo
    )
    assert any(
        [e.kind for e in edits] == ["swap", "alternate_format"]
        and format_activities(edits) == ["demonstrations"]
        for edits in menu
    )
    assert any(
        [e.kind for e in edits] == ["substitute", "alternate_format"]
        and format_activities(edits) == ["skills_exchange"]
        for edits in menu
    )


def test_a_format_generated_before_a_substitution_of_its_activity_is_not_combined() -> None:
    # With the formats configured first, generation reaches (format, substitute) on
    # demonstrations with the format first: the rule refuses that direction too.
    scenario = with_formats_first(POSTER, CIRCLE, max_combined_edits=3)
    planning = scenario.planning
    enabled = enabled_templates(planning, None)
    singles = single_edits(planning, enabled)
    assert [(e.kind, e.activity_ids) for e in singles[:2]] == [
        ("alternate_format", ("demonstrations",)),
        ("alternate_format", ("skills_exchange",)),
    ]
    format_then_substitute = [
        pair
        for pair in combinations(singles, 2)
        if [e.kind for e in pair] == ["alternate_format", "substitute"]
        and pair[0].activity_ids == pair[1].activity_ids
    ]
    assert [p[0].format_id for p in format_then_substitute] == ["poster_walk"]
    menu = generate_edit_lists(planning, enabled)
    assert not any(
        all(e in edits for e in pair) for pair in format_then_substitute for edits in menu
    )
    assert not any(
        {e.kind for e in edits} >= {"substitute", "alternate_format"}
        and "demonstrations" in format_activities(edits)
        for edits in menu
    )
    expected = [(), *((e,) for e in singles)]
    for size in (2, 3):
        expected.extend(c for c in combinations(singles, size) if documented_combination(c))
    assert list(menu) == expected
    # A format of another activity still combines with the substitution, format first.
    assert any(
        [e.kind for e in edits] == ["alternate_format", "substitute"]
        and format_activities(edits) == ["skills_exchange"]
        for edits in menu
    )

    labels = {c.label for c in evaluate(delayed(with_formats_first(POSTER))).candidates}
    assert {POSTER_LABEL, SUBSTITUTE_LABEL} <= labels
    assert f"{POSTER_LABEL} + {SUBSTITUTE_LABEL}" not in labels


def test_evaluation_lists_each_format_and_never_two_on_one_activity() -> None:
    result = evaluate(delayed(with_formats(POSTER, SHORT_DEMO, CIRCLE)))
    assert not result.truncated
    for label in (POSTER_LABEL, SHORT_LABEL, CIRCLE_LABEL):
        assert by_label(result, label).edits[0].kind == "alternate_format"
    for c in result.candidates:
        per_activity = Counter(format_activities(c.edits))
        assert all(n == 1 for n in per_activity.values()), c.label
        assert c.label.count("format for demonstrations") <= 1
    assert f"{POSTER_LABEL} + {CIRCLE_LABEL}" in {c.label for c in result.candidates}
    assert f"{SUBSTITUTE_LABEL} + {POSTER_LABEL}" not in {c.label for c in result.candidates}
    # Requesting only the alternate_format template searches keep and the formats alone.
    request = EvaluationRequest(templates=("alternate_format",))
    only = evaluate(delayed(with_formats(POSTER, SHORT_DEMO, CIRCLE)), request)
    assert {c.label for c in only.candidates} == {
        "Keep the current plan",
        POSTER_LABEL,
        SHORT_LABEL,
        CIRCLE_LABEL,
        f"{POSTER_LABEL} + {CIRCLE_LABEL}",
        f"{SHORT_LABEL} + {CIRCLE_LABEL}",
    }
    # With the projector gone, the short demo (which needs it) leaves nothing feasible, and the
    # infeasibility report states the format in the searched action space.
    snap = initial_snapshot(with_formats(SHORT_DEMO))
    gone = tuple(
        r.model_copy(update={"status": "unavailable", "status_basis": "status_observation"})
        if r.definition.resource_id == "projector"
        else r
        for r in snap.resources
    )
    infeasible = evaluate(snap.model_copy(update={"resources": gone}), request)
    assert infeasible.infeasibility is not None
    assert "resource_status" in infeasible.infeasibility.blocking_constraints
    assert "alternate_format(demonstrations: short_demo)" in (
        infeasible.infeasibility.declared_action_space
    )


# --------------------------------------------------------------------- duration, resources


def test_format_sets_duration_and_resources_of_its_activity() -> None:
    result = evaluate(delayed(with_formats(POSTER, SHORT_DEMO, BACKUP_DEMO, LONG_DEMO)))
    keep = by_label(result, "Keep the current plan")
    assert "arrival_assumptions" in failed_ids(keep)

    poster = by_label(result, POSTER_LABEL)
    # Same start, the format's duration, exactly the format's resources; nothing else moves.
    assert span(poster, "demonstrations") == ("17:10", "17:25", ("main_room", "presenter"))
    assert poster.changed_activity_ids == ("demonstrations",)
    for other in poster.assignments:
        if other.activity_id != "demonstrations":
            assert other in SCENARIO.initial_state.assignments
    assert poster.constraint_status == "feasible_under_assumptions" and poster.applicable_now
    assert check(poster, "activity_windows").status == "passed"
    # Without the projector, the delayed delivery is no longer an assumption of the plan.
    assert check(poster, "arrival_assumptions").status == "not_applicable"
    assert not any(a.entity_id == "projector" for a in poster.assumptions)
    # It changes one activity and moves no start, so it outranks the swap (objective 70).
    assert poster.objective.start_shift_minutes == 0
    assert poster.objective.changed_activities == 1
    assert result.best_applicable_candidate_id == poster.candidate_id

    # A format is checked with its own resources: the short demo still needs the projector.
    short = by_label(result, SHORT_LABEL)
    assert span(short, "demonstrations") == (
        "17:10",
        "17:25",
        ("main_room", "projector", "presenter"),
    )
    assert "arrival_assumptions" in failed_ids(short)
    assert short.constraint_status == "infeasible"

    # A booking-required resource of a format needs a hold, a commitment and authority.
    backup = by_label(result, BACKUP_LABEL)
    assert [h.resource_id for h in backup.required_holds] == ["backup_projector"]
    assert backup.incremental_committed_cents == 3500
    assert [m.kind for m in backup.authorization.missing] == ["committed_spend_limit"]
    assert not backup.applicable_now

    # A format longer than the activity's window is reported, not stretched or clipped.
    long = by_label(result, LONG_LABEL)
    assert span(long, "demonstrations")[:2] == ("17:10", "17:55")
    assert "demonstrations 17:10-17:55 is outside its window 17:10-17:50" in (
        check(long, "activity_windows").detail
    )
    assert long.constraint_status == "infeasible"


def test_format_applies_after_a_timing_edit_of_its_activity() -> None:
    result = evaluate(delayed(with_formats(POSTER, SHORT_DEMO)))
    swapped = by_label(result, f"{SWAP_LABEL} + {POSTER_LABEL}")
    # Timing edits first (the swap moves demonstrations to 17:30), then the format's duration.
    assert span(swapped, "demonstrations") == ("17:30", "17:45", ("main_room", "presenter"))
    assert span(swapped, "skills_exchange")[:2] == ("17:10", "17:30")
    assert swapped.constraint_status == "feasible_under_assumptions"
    # The swap alone gives the late projector time; with the projector-free format, too.
    swapped_short = by_label(result, f"{SWAP_LABEL} + {SHORT_LABEL}")
    assert swapped_short.constraint_status == "feasible_under_assumptions"


@pytest.mark.parametrize("formats_first", [False, True], ids=["swap_listed_first", "format_first"])
def test_timing_edits_apply_before_a_format_of_the_later_swapped_activity(
    formats_first: bool,
) -> None:
    # Here the order matters. The swap moves the later activity (skills exchange, 17:30-17:50)
    # to 17:10 and starts the earlier one where the later one's current length ends. Timing
    # first: skills exchange 17:10-17:30, demonstrations 17:30-17:50, then the circle format
    # shortens skills exchange to 17:10-17:25. Formatting first would make the swap read a
    # 15-minute skills exchange and pull demonstrations to 17:25. The documented order holds
    # whichever edit the candidate lists first.
    scenario = with_formats_first(CIRCLE) if formats_first else with_formats(CIRCLE)
    label = f"{CIRCLE_LABEL} + {SWAP_LABEL}" if formats_first else f"{SWAP_LABEL} + {CIRCLE_LABEL}"
    combined = by_label(evaluate(delayed(scenario)), label)
    assert [e.kind for e in combined.edits] == (
        ["alternate_format", "swap"] if formats_first else ["swap", "alternate_format"]
    )
    assert span(combined, "skills_exchange") == (
        "17:10",
        "17:25",
        ("main_room", "facilitator", "host"),
    )
    assert span(combined, "demonstrations") == (
        "17:30",
        "17:50",
        ("main_room", "projector", "presenter"),
    )
    assert set(combined.changed_activity_ids) == {"demonstrations", "skills_exchange"}


# ------------------------------------------------------------------ executor, readiness, score


@pytest.fixture
def format_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A scratch copy of the public fixture with POSTER and SHORT_DEMO configured."""
    public = tmp_path / "public"
    public.mkdir()
    name = fixtures.PUBLIC_SCENARIOS["dev_fixture_01"]
    data = json.loads((fixtures.PUBLIC_DIR / name).read_text())
    data["planning"]["edit_templates"].extend(
        t.model_dump(mode="json") for t in (POSTER, SHORT_DEMO)
    )
    (public / name).write_text(json.dumps(data))
    monkeypatch.setattr(fixtures, "PUBLIC_DIR", public)
    yield


def _stored_edits(env_data: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [c["edits"] for c in env_data["candidates"]]


def test_format_is_revalidated_applied_executed_and_scored(
    db: Database, format_fixture: None
) -> None:
    sb = Sandbox(db, "dev01")  # the projector reports 17:25 and arrives at 17:24
    assert sb.query().status == "succeeded"
    first = sb.evaluate()
    assert first.data is not None
    for edits in _stored_edits(first.data):
        assert all(n == 1 for n in Counter(format_activities(edits)).values())
    poster = sb.candidate(first, POSTER_LABEL)
    assert poster["applicable_now"]
    assert first.data["best_applicable_candidate_id"] == poster["candidate_id"]

    # Revalidation: a candidate evaluated before a state change is not applied.
    assert sb.check_in("participant_presenter", "presenter", "pres-1").status == "succeeded"
    stale = sb.apply(poster, first, "apply-stale")
    assert stale.receipt is not None and stale.receipt.error_code == "REVISION_CONFLICT"
    old_report = sb.agent.call(
        "apply_plan",
        arguments={
            "candidate_plan_id": poster["candidate_id"],
            "constraint_report_ref": poster["report_id"],
        },
        idempotency_key="apply-old-candidate",
        expected_revision=sb.revision(),
        expected_goal_version=first.data["goal_version"],
    )
    assert old_report.receipt is not None and old_report.receipt.error_code == "CANDIDATE_STALE"
    assert sb.view().plan.plan_version == 1

    second = sb.evaluate()
    assert second.data is not None
    poster = sb.candidate(second, POSTER_LABEL)
    applied = sb.apply(poster, second, "apply-poster")
    assert applied.receipt is not None and applied.receipt.status == "applied", applied.error
    receipt = applied.receipt
    assert receipt.related_plan_id == poster["candidate_id"]
    assert receipt.constraint_report_ref == poster["report_id"]
    changes = {(c.entity_id, c.field): c for c in receipt.state_changes}
    assert set(changes) == {
        ("demonstrations", "scheduled_window"),
        ("demonstrations", "resource_ids"),
    }
    assert changes[("demonstrations", "resource_ids")].after == ["main_room", "presenter"]
    assert receipt.committed_delta_cents == 0 and receipt.reserved_delta_cents == 0

    # The applied plan is the revalidated candidate, exactly.
    view = sb.view()
    assert view.plan.plan_version == 2 and view.plan.candidate_id == poster["candidate_id"]
    assert [a.model_dump(mode="json") for a in view.plan.assignments] == poster["assignments"]
    demos = next(a for a in view.activities if a.definition.activity_id == "demonstrations")
    assert demos.assignment is not None
    assert (demos.assignment.start, demos.assignment.end) == (at("17:10"), at("17:25"))

    # The active plan keeps the format's duration: keeping it is feasible, and the format
    # is not offered again as a change.
    third = sb.evaluate()
    assert third.data is not None
    keep = next(
        c for c in third.data["candidates"] if c["candidate_id"] == third.data["keep_candidate_id"]
    )
    assert keep["constraint_status"] == "feasible_under_assumptions"
    assert keep["assignments"] == poster["assignments"]
    again = sb.candidate(third, POSTER_LABEL)
    assert again["changed_activity_ids"] == []

    # Readiness reads the format's resources: no projector is awaited.
    assert demos.readiness is not None
    assert not any("projector" in line for line in (*demos.readiness.met, *demos.readiness.unmet))
    assert sb.check_in("participant_facilitator", "facilitator", "fac-1").status == "succeeded"

    sb.advance_to("17:11")
    view = sb.view()
    projector = next(r for r in view.resources if r.definition.resource_id == "projector")
    assert projector.status == "expected"  # still not arrived
    demos = next(a for a in view.activities if a.definition.activity_id == "demonstrations")
    started = next(e for e in demos.history if e.state == "started")
    assert started.at == at("17:10")
    assert not any("projector" in reason for reason in started.reasons)

    sb.advance_to("18:00")
    final = audit_view(db, sb.episode_id)
    report = score_episode(final, episode_history(db, sb.episode_id))
    # Starting without the projector is no violation: the plan in effect did not use it.
    assert report.violations == ()
    assert report.goal_complete
    assert report.applied_plans == 1 and report.changed_assignments == 1
    assert report.committed_cents == 0
    outcome = next(a for a in report.activities if a.activity_id == "demonstrations")
    assert (outcome.started_at, outcome.completed_at) == (at("17:10"), at("17:25"))
