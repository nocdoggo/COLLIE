"""Hard-constraint checks, assumptions, required holds and authorization for one candidate.

Every check of ``docs/RUNTIME_CONTRACT.md`` section 10 is evaluated for every candidate, in
the table's order. A check is ``not_applicable`` when nothing in the candidate is subject to it
(never a placeholder pass) and ``unsupported`` when the requirement cannot be evaluated in
Wave 1. Only the visible planning snapshot and declared hypotheses are read.

Activity states: ``planned``/``ready`` activities are *not started* and are the subject of
the forward-looking checks (venue, windows, dependencies, status, arrival, availability,
cutoff, holds). ``started`` activities still occupy their resources and the program slot;
``completed``/``failed``/``canceled`` activities occupy nothing any more. Everything that has
started is fixed history (``started_history``).

Time-dependent checks (``no_past_change``, ``commitment_cutoff``, hold liveness and grant
expiry) are judged at ``effective_at``: the time an ``apply_plan`` issued now would take effect
(the snapshot's ``effective_at``, never earlier than its clock). A candidate reported
applicable is then still valid when its apply executes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import combinations

from plan_b.domain.candidates import find_format, readable
from plan_b.domain.models import (
    ActivityDef,
    ActorContext,
    Assignment,
    AuthorizationAssessment,
    BudgetView,
    CandidateAssumption,
    CandidateCheck,
    CheckInView,
    CheckStatus,
    CommitmentView,
    ConstraintResult,
    Edit,
    EventGoal,
    HoldView,
    Hypothesis,
    MissingPermission,
    PlanningConfig,
    PlanningSnapshot,
    RequiredHold,
    ResourceView,
    TimeWindow,
)
from plan_b.domain.projection import effective_hold_status
from plan_b.domain.timeutil import DISPLAY_TIMEZONE, local_label

# The version of the shared checks and planner every policy uses, P0 included. 1.2.0 (Wave 3b): a
# handoff from a pool checked unavailable is infeasible (adapters/pantry.py), and a person whose
# reported or hypothetical ETA is after an activity's start fails participant availability.
# The freeze records it, because P0's own policy ids did not change.
PLANNER_VERSION = "plan_b.planner/1.2.0"

CHECK_IDS = (
    "required_activities",
    "fixed_venue",
    "started_history",
    "no_past_change",
    "activity_windows",
    "event_window",
    "dependencies",
    "program_exclusivity",
    "occupancy_capacity",
    "resource_capacity",
    "resource_status",
    "arrival_assumptions",
    "substitute_compatibility",
    "participant_availability",
    "accessibility",
    "commitment_cutoff",
    "budget",
)

NOT_STARTED = frozenset({"planned", "ready"})
OCCUPYING = frozenset({"planned", "ready", "started"})
FIXED = frozenset({"started", "completed", "failed", "canceled"})
TERMINAL_FAILURE = frozenset({"failed", "canceled"})

REVALIDATE_PRECONDITION = (
    "Revalidate current revision, goal version, grant and resource conflicts at apply_plan."
)
COMMITTED_REVIEW_ITEM = "increase committed spending"
SUPPORTED_ACCESSIBILITY_KINDS = frozenset({"venue_capability"})


def _t(value: datetime) -> str:
    return local_label(value, DISPLAY_TIMEZONE)


def _span(window: TimeWindow | Assignment) -> str:
    return f"{_t(window.start)}-{_t(window.end)}"


@dataclass(frozen=True)
class PlanningContext:
    """Read-only view of one snapshot, with hypotheses applied to resources."""

    clock: datetime
    effective_at: datetime  # when an apply issued now takes effect (>= clock)
    goal: EventGoal
    planning: PlanningConfig
    activities: dict[str, ActivityDef]
    lifecycles: dict[str, str]
    active: dict[str, Assignment]
    resources: dict[str, ResourceView]
    holds: tuple[HoldView, ...]
    commitments: tuple[CommitmentView, ...]
    checkins: tuple[CheckInView, ...]
    budget: BudgetView
    hypothesis_labels: dict[str, str]
    hypothesis_assumptions: tuple[CandidateAssumption, ...]

    def lifecycle(self, activity_id: str) -> str:
        return self.lifecycles.get(activity_id, "planned")

    def live_holds(self) -> tuple[HoldView, ...]:
        """Holds active now that are still active when an apply issued now takes effect."""
        return tuple(
            h
            for h in self.holds
            if h.effective_status == "active"
            and effective_hold_status(h, self.effective_at) == "active"
        )

    def lapsing_holds(self) -> tuple[HoldView, ...]:
        """Holds active now that expire before an apply issued now takes effect."""
        return tuple(
            h
            for h in self.holds
            if h.effective_status == "active"
            and effective_hold_status(h, self.clock) == "active"
            and effective_hold_status(h, self.effective_at) != "active"
        )

    def when(self) -> str:
        """The judgement time in words, naming the apply effect time when it differs."""
        if self.effective_at == self.clock:
            return f"the clock {_t(self.clock)}"
        return f"{_t(self.effective_at)}, when an apply issued at {_t(self.clock)} takes effect"

    def active_commitments(self) -> tuple[CommitmentView, ...]:
        return tuple(c for c in self.commitments if c.status == "active")


def _apply_hypotheses(
    resources: dict[str, ResourceView], hypotheses: tuple[Hypothesis, ...]
) -> tuple[dict[str, ResourceView], dict[str, str], tuple[CandidateAssumption, ...]]:
    adjusted = dict(resources)
    labels: dict[str, str] = {}
    notes: list[CandidateAssumption] = []
    for index, hypothesis in enumerate(hypotheses):
        rid = hypothesis.resource_id
        assumption_id = f"asm_hypothesis_{index + 1:02d}_{rid}"
        resource = adjusted.get(rid)
        if resource is None:
            notes.append(
                CandidateAssumption(
                    assumption_id=assumption_id,
                    kind="hypothesis",
                    entity_id=rid,
                    text=(
                        f"Hypothesis '{hypothesis.label}' names unregistered resource {rid}; "
                        "it changes nothing in this evaluation."
                    ),
                    basis_ref=hypothesis.label,
                )
            )
            continue
        status = resource.status
        eta = resource.reported_eta
        parts: list[str] = []
        if hypothesis.assume_status is not None:
            status = hypothesis.assume_status
            parts.append(f"status {status}")
        if hypothesis.assume_ready_at is not None:
            eta = hypothesis.assume_ready_at
            if hypothesis.assume_status is None and status != "available":
                status = "expected"
            parts.append(f"ready at {_t(eta)} ({DISPLAY_TIMEZONE})")
        adjusted[rid] = resource.model_copy(update={"status": status, "reported_eta": eta})
        labels[rid] = hypothesis.label
        effect = ", ".join(parts) if parts else "no status or ETA override"
        notes.append(
            CandidateAssumption(
                assumption_id=assumption_id,
                kind="hypothesis",
                entity_id=rid,
                text=(
                    f"Hypothesis '{hypothesis.label}': {rid} {effect}, for this evaluation "
                    "only; it is not an observation."
                ),
                basis_ref=hypothesis.label,
            )
        )
    return adjusted, labels, tuple(notes)


def build_context(
    snapshot: PlanningSnapshot, hypotheses: tuple[Hypothesis, ...] = ()
) -> PlanningContext:
    resources = {r.definition.resource_id: r for r in snapshot.resources}
    adjusted, labels, notes = _apply_hypotheses(resources, hypotheses)
    effective_at = snapshot.clock
    if snapshot.effective_at is not None and snapshot.effective_at > snapshot.clock:
        effective_at = snapshot.effective_at
    return PlanningContext(
        clock=snapshot.clock,
        effective_at=effective_at,
        goal=snapshot.goal,
        planning=snapshot.planning,
        activities={v.definition.activity_id: v.definition for v in snapshot.activities},
        lifecycles={v.definition.activity_id: v.lifecycle for v in snapshot.activities},
        active={a.activity_id: a for a in snapshot.plan.assignments},
        resources=adjusted,
        holds=snapshot.holds,
        commitments=snapshot.commitments,
        checkins=snapshot.checkins,
        budget=snapshot.budget,
        hypothesis_labels=labels,
        hypothesis_assumptions=notes,
    )


@dataclass(frozen=True)
class Assessment:
    """Everything the constraint layer establishes about one candidate."""

    changed_activity_ids: tuple[str, ...]
    checks: tuple[CandidateCheck, ...]
    assumptions: tuple[CandidateAssumption, ...]
    required_holds: tuple[RequiredHold, ...]
    authorization: AuthorizationAssessment
    incremental_committed_cents: int
    constraint_status: ConstraintResult
    execution_preconditions: tuple[str, ...]


@dataclass
class _Assumptions:
    items: list[CandidateAssumption] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)

    def add(self, assumption: CandidateAssumption) -> None:
        if assumption.assumption_id not in self.seen:
            self.seen.add(assumption.assumption_id)
            self.items.append(assumption)


def _check(
    constraint_id: str, status: CheckStatus, detail: str, entity_ids: list[str] | None = None
) -> CandidateCheck:
    unique = tuple(dict.fromkeys(entity_ids or ()))
    return CandidateCheck(
        constraint_id=constraint_id, status=status, detail=detail, entity_ids=unique
    )


def _verdict(
    constraint_id: str, problems: list[str], entities: list[str], passed_detail: str
) -> CandidateCheck:
    if problems:
        return _check(constraint_id, "failed", "; ".join(problems), entities)
    return _check(constraint_id, "passed", passed_detail, entities)


def changed_activities(
    active: dict[str, Assignment], assignments: tuple[Assignment, ...]
) -> tuple[str, ...]:
    """Activities whose start, end or resources differ from the active plan."""
    candidate = {a.activity_id: a for a in assignments}
    changed: list[str] = []
    for aid in list(candidate) + [aid for aid in active if aid not in candidate]:
        old, new = active.get(aid), candidate.get(aid)
        if (
            old is None
            or new is None
            or (old.start, old.end, old.resource_ids) != (new.start, new.end, new.resource_ids)
        ):
            changed.append(aid)
    return tuple(changed)


def _not_started(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> list[Assignment]:
    return [a for a in assignments if ctx.lifecycle(a.activity_id) in NOT_STARTED]


def _occupying(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> list[Assignment]:
    return [a for a in assignments if ctx.lifecycle(a.activity_id) in OCCUPYING]


def _peak(window: TimeWindow, intervals: list[tuple[TimeWindow, int]]) -> int:
    """Largest simultaneous quantity of half-open intervals inside ``window``."""
    inside = [(w, q) for w, q in intervals if w.overlaps(window)]
    points = {window.start} | {w.start for w, _ in inside if w.start > window.start}
    best = 0
    for point in points:
        best = max(best, sum(q for w, q in inside if w.start <= point < w.end))
    return best


def _covering_commitment(
    ctx: PlanningContext, resource_id: str, assignment: Assignment
) -> CommitmentView | None:
    for commitment in ctx.active_commitments():
        if (
            commitment.resource_id == resource_id
            and commitment.activity_id == assignment.activity_id
            and commitment.window.contains(assignment.window)
        ):
            return commitment
    return None


def _cutoff(resource: ResourceView, assignment: Assignment) -> datetime | None:
    minutes = resource.definition.terms.commitment_cutoff_minutes_before_use
    if minutes is None:
        return None
    return assignment.start - timedelta(minutes=minutes)


def _latest_checkin(ctx: PlanningContext, resource_id: str) -> CheckInView | None:
    found = [(c.at, i, c) for i, c in enumerate(ctx.checkins) if c.resource_id == resource_id]
    if not found:
        return None
    return max(found, key=lambda item: (item[0], item[1]))[2]


# ---------------------------------------------------------------------------
# Individual checks (contract section 10 table)
# ---------------------------------------------------------------------------


def _required_activities(
    ctx: PlanningContext, assignments: tuple[Assignment, ...]
) -> CandidateCheck:
    required = ctx.goal.required_activity_ids
    if not required:
        return _check(
            "required_activities", "not_applicable", "The goal names no required activity"
        )
    scheduled = {a.activity_id for a in assignments}
    missing = [aid for aid in required if aid not in scheduled]
    if missing:
        return _check(
            "required_activities",
            "failed",
            f"Required activities without an assignment: {', '.join(missing)}",
            missing,
        )
    return _check(
        "required_activities",
        "passed",
        f"All {len(required)} required activities are scheduled",
        list(required),
    )


def _fixed_venue(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    venue = ctx.goal.fixed_venue_id
    subject = _not_started(ctx, assignments)
    if not subject:
        return _check("fixed_venue", "not_applicable", "No not-started activity remains")
    lacking = [a.activity_id for a in subject if venue not in a.resource_ids]
    if lacking:
        return _check(
            "fixed_venue",
            "failed",
            f"{', '.join(lacking)} would not use the fixed venue {venue}",
            lacking + [venue],
        )
    return _check(
        "fixed_venue",
        "passed",
        f"Every not-started activity uses the fixed venue {venue}",
        [venue],
    )


def _started_history(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    fixed = [aid for aid in ctx.activities if ctx.lifecycle(aid) in FIXED]
    if not fixed:
        return _check("started_history", "not_applicable", "No activity has started yet")
    candidate = {a.activity_id: a for a in assignments}
    differs = [aid for aid in fixed if candidate.get(aid) != ctx.active.get(aid)]
    if differs:
        described = ", ".join(f"{aid} ({ctx.lifecycle(aid)})" for aid in differs)
        return _check(
            "started_history",
            "failed",
            f"{described} cannot change: its assignment is recorded history",
            differs,
        )
    described = ", ".join(f"{aid} ({ctx.lifecycle(aid)})" for aid in fixed)
    return _check(
        "started_history",
        "passed",
        f"{described} keeps its active-plan assignment",
        fixed,
    )


def _no_past_change(
    ctx: PlanningContext, assignments: tuple[Assignment, ...], changed: tuple[str, ...]
) -> CandidateCheck:
    subject = [a for a in assignments if a.activity_id in changed]
    if not subject:
        return _check("no_past_change", "not_applicable", "The candidate changes no activity")
    past = [a for a in subject if a.start <= ctx.effective_at]
    if past:
        problems = [
            f"{a.activity_id} would start at {_t(a.start)}, not after {ctx.when()}" for a in past
        ]
        return _check(
            "no_past_change", "failed", "; ".join(problems), [a.activity_id for a in past]
        )
    return _check(
        "no_past_change",
        "passed",
        f"Every changed activity starts after {ctx.when()}",
        [a.activity_id for a in subject],
    )


def _allowed_lengths(
    ctx: PlanningContext, definition: ActivityDef, edits: tuple[Edit, ...]
) -> tuple[list[int], str | None]:
    """Allowed assignment lengths, and a problem when the requested format is unknown."""
    for edit in edits:
        if edit.kind == "alternate_format" and edit.activity_ids[0] == definition.activity_id:
            fmt = find_format(ctx.planning, definition.activity_id, edit.format_id)
            if fmt is None:
                return [], (
                    f"alternate format {edit.format_id} is not configured for "
                    f"{definition.activity_id}"
                )
            return [fmt.duration_minutes], None
    lengths = [definition.duration_minutes]
    for template in ctx.planning.edit_templates:
        if (
            template.template == "alternate_format"
            and template.activity_id == definition.activity_id
            and template.duration_minutes not in lengths
        ):
            lengths.append(template.duration_minutes)
    return lengths, None


def _activity_windows(
    ctx: PlanningContext, assignments: tuple[Assignment, ...], edits: tuple[Edit, ...]
) -> CandidateCheck:
    subject = _not_started(ctx, assignments)
    if not subject:
        return _check("activity_windows", "not_applicable", "No not-started activity remains")
    problems: list[str] = []
    entities: list[str] = []
    for a in subject:
        definition = ctx.activities.get(a.activity_id)
        if definition is None:
            problems.append(f"{a.activity_id} is not a registered activity")
            entities.append(a.activity_id)
            continue
        if not definition.window.contains(a.window):
            problems.append(
                f"{a.activity_id} {_span(a)} is outside its window {_span(definition.window)}"
            )
            entities.append(a.activity_id)
        lengths, format_problem = _allowed_lengths(ctx, definition, edits)
        length = int((a.end - a.start).total_seconds() // 60)
        if format_problem is not None:
            problems.append(format_problem)
            entities.append(a.activity_id)
        elif length not in lengths:
            expected = " or ".join(str(n) for n in lengths)
            problems.append(f"{a.activity_id} lasts {length} min, not {expected} min")
            entities.append(a.activity_id)
    return _verdict(
        "activity_windows",
        problems,
        entities,
        "Every not-started activity fits its window and keeps its (format) duration",
    )


def _event_window(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    if not assignments:
        return _check("event_window", "not_applicable", "The candidate has no assignment")
    end = ctx.goal.hard_end
    late = [a for a in assignments if a.end > end]
    if late:
        problems = [
            f"{a.activity_id} ends at {_t(a.end)}, after the hard end {_t(end)}" for a in late
        ]
        return _check("event_window", "failed", "; ".join(problems), [a.activity_id for a in late])
    return _check("event_window", "passed", f"Every assignment ends by the hard end {_t(end)}")


def _dependencies(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    candidate = {a.activity_id: a for a in assignments}
    subject = [
        a
        for a in _not_started(ctx, assignments)
        if a.activity_id in ctx.activities and ctx.activities[a.activity_id].predecessors
    ]
    if not subject:
        return _check("dependencies", "not_applicable", "No not-started activity has a predecessor")
    problems: list[str] = []
    entities: list[str] = []
    for a in subject:
        for pred in ctx.activities[a.activity_id].predecessors:
            pred_state = ctx.lifecycle(pred)
            pred_assignment = candidate.get(pred)
            if pred_state in TERMINAL_FAILURE:
                problems.append(
                    f"predecessor {pred} of {a.activity_id} is {pred_state} and cannot complete"
                )
            elif pred_assignment is None:
                problems.append(f"predecessor {pred} of {a.activity_id} has no assignment")
            elif a.start < pred_assignment.end:
                problems.append(
                    f"{a.activity_id} starts at {_t(a.start)}, before predecessor {pred} ends "
                    f"at {_t(pred_assignment.end)}"
                )
            else:
                continue
            entities.extend([a.activity_id, pred])
    return _verdict(
        "dependencies",
        problems,
        entities,
        "Every not-started activity starts after its predecessors' assigned ends",
    )


def _program_exclusivity(
    ctx: PlanningContext, assignments: tuple[Assignment, ...]
) -> CandidateCheck:
    program = [
        a
        for a in _occupying(ctx, assignments)
        if a.activity_id in ctx.activities and ctx.activities[a.activity_id].program
    ]
    limit = ctx.goal.program_concurrency
    if not program:
        return _check(
            "program_exclusivity", "not_applicable", "No program activity is still to run"
        )
    intervals = [(a.window, 1) for a in program]
    peak = max(_peak(a.window, intervals) for a in program)
    if peak > limit:
        pairs = [
            f"{x.activity_id} {_span(x)} overlaps {y.activity_id} {_span(y)}"
            for x, y in combinations(program, 2)
            if x.window.overlaps(y.window)
        ]
        entities = [
            aid
            for x, y in combinations(program, 2)
            if x.window.overlaps(y.window)
            for aid in (x.activity_id, y.activity_id)
        ]
        return _check(
            "program_exclusivity",
            "failed",
            f"{'; '.join(pairs)}; at most {limit} program activity may run at once",
            entities,
        )
    return _check(
        "program_exclusivity",
        "passed",
        f"At most {peak} program activity runs at any time (limit {limit})",
    )


def _occupancy_capacity(ctx: PlanningContext) -> CandidateCheck:
    venue_id = ctx.goal.fixed_venue_id
    venue = ctx.resources.get(venue_id)
    target = ctx.goal.attendance_target
    if venue is None:
        return _check(
            "occupancy_capacity", "failed", f"Fixed venue {venue_id} is not registered", [venue_id]
        )
    capacity = venue.definition.capacity
    if target > capacity:
        return _check(
            "occupancy_capacity",
            "failed",
            f"Attendance target {target} exceeds {venue_id} capacity {capacity}",
            [venue_id],
        )
    return _check(
        "occupancy_capacity",
        "passed",
        f"Attendance target {target} fits {venue_id} capacity {capacity}",
        [venue_id],
    )


def _resource_capacity(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    subject = _occupying(ctx, assignments)
    if not subject:
        return _check("resource_capacity", "not_applicable", "No assignment still uses resources")
    by_activity = {a.activity_id: a for a in subject}

    def belongs(resource_id: str, activity_id: str, window: TimeWindow) -> bool:
        own = by_activity.get(activity_id)
        return own is not None and resource_id in own.resource_ids and window.contains(own.window)

    problems: list[str] = []
    entities: list[str] = []
    holds = ctx.live_holds()
    commitments = ctx.active_commitments()
    for a in subject:
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if resource is None:
                problems.append(f"{rid} used by {a.activity_id} is not registered")
                entities.append(rid)
                continue
            if not resource.definition.window.contains(a.window):
                problems.append(
                    f"{a.activity_id} {_span(a)} is outside {rid}'s window "
                    f"{_span(resource.definition.window)}"
                )
                entities.append(rid)
                continue
            usage: list[tuple[TimeWindow, int]] = [
                (other.window, 1) for other in subject if rid in other.resource_ids
            ]
            usage.extend(
                (h.window, h.quantity)
                for h in holds
                if h.resource_id == rid and not belongs(rid, h.activity_id, h.window)
            )
            usage.extend(
                (c.window, 1)
                for c in commitments
                if c.resource_id == rid and not belongs(rid, c.activity_id, c.window)
            )
            peak = _peak(a.window, usage)
            capacity = resource.definition.capacity
            if peak > capacity:
                problems.append(
                    f"{rid} would need {peak} units during {a.activity_id} {_span(a)}, "
                    f"capacity {capacity}"
                )
                entities.append(rid)
    return _verdict(
        "resource_capacity",
        problems,
        entities,
        "Every assigned resource is within its window and capacity, counting active holds "
        "and commitments",
    )


def _resource_status(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    subject = [(a, rid) for a in _not_started(ctx, assignments) for rid in a.resource_ids]
    if not subject:
        return _check(
            "resource_status", "not_applicable", "No not-started activity uses a resource"
        )
    problems: list[str] = []
    entities: list[str] = []
    expected: list[str] = []
    for a, rid in subject:
        resource = ctx.resources.get(rid)
        if resource is None:
            problems.append(f"{rid} used by {a.activity_id} has no registered status")
            entities.append(rid)
            continue
        source = " (hypothesis)" if rid in ctx.hypothesis_labels else ""
        if resource.status in ("unavailable", "unknown"):
            problems.append(f"{rid} for {a.activity_id} is {resource.status}{source}")
            entities.append(rid)
        elif resource.status == "expected" and rid not in expected:
            expected.append(rid)
    note = f"; expected (not yet observed): {', '.join(expected)}" if expected else ""
    return _verdict(
        "resource_status",
        problems,
        entities,
        f"No resource of a not-started activity is unavailable or unknown{note}",
    )


def _arrival_assumptions(
    ctx: PlanningContext, assignments: tuple[Assignment, ...], acc: _Assumptions
) -> CandidateCheck:
    subject: list[tuple[Assignment, ResourceView]] = []
    for a in _not_started(ctx, assignments):
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if (
                resource is not None
                and resource.definition.kind == "equipment"
                and resource.status == "expected"
            ):
                subject.append((a, resource))
    if not subject:
        return _check(
            "arrival_assumptions",
            "not_applicable",
            "No not-started activity relies on expected equipment",
        )
    problems: list[str] = []
    entities: list[str] = []
    passed: list[str] = []
    for a, resource in subject:
        rid = resource.definition.resource_id
        hypothesis = ctx.hypothesis_labels.get(rid)
        eta = resource.reported_eta
        if eta is not None and eta > a.start:
            origin = "hypothetical ETA" if hypothesis else "reported ETA"
            problems.append(
                f"{rid} {origin} {_t(eta)} is after {a.activity_id} starts at {_t(a.start)}"
            )
            entities.extend([rid, a.activity_id])
            continue
        if eta is not None:
            origin = f"hypothesis '{hypothesis}'" if hypothesis else "the reported ETA"
            overdue = (
                ", has already passed without an observed arrival"
                if eta < ctx.clock
                else ", which is not an observed arrival"
            )
            text = (
                f"{rid} is assumed to arrive by {a.activity_id} start at {_t(a.start)} "
                f"({DISPLAY_TIMEZONE}); {origin} is {_t(eta)}{overdue}"
            )
            basis = hypothesis or resource.status_observation_id or resource.definition.source_ref
            passed.append(f"{rid} ETA {_t(eta)} is not after {a.activity_id} {_t(a.start)}")
        else:
            text = (
                f"{rid} is assumed to arrive by {a.activity_id} start at {_t(a.start)} "
                f"({DISPLAY_TIMEZONE}); no ETA has been reported and arrival is not observed"
            )
            basis = resource.status_observation_id or resource.definition.source_ref
            passed.append(f"{rid} has no ETA evidence before {a.activity_id} {_t(a.start)}")
        acc.add(
            CandidateAssumption(
                assumption_id=f"asm_arrival_by_start_{rid}_{a.activity_id}",
                kind="arrival_by_start",
                entity_id=rid,
                text=text,
                basis_ref=basis,
            )
        )
        entities.extend([rid, a.activity_id])
    return _verdict(
        "arrival_assumptions",
        problems,
        entities,
        f"{'; '.join(passed)}; arrival by start is recorded as an assumption",
    )


def _substitute_compatibility(ctx: PlanningContext, edits: tuple[Edit, ...]) -> CandidateCheck:
    subject = [e for e in edits if e.kind == "substitute"]
    if not subject:
        return _check(
            "substitute_compatibility", "not_applicable", "The candidate substitutes no resource"
        )
    problems: list[str] = []
    entities: list[str] = []
    passed: list[str] = []
    for edit in subject:
        activity_id = edit.activity_ids[0]
        rid = edit.resource_id or ""
        sid = edit.substitute_id or ""
        original = ctx.resources.get(rid)
        substitute = ctx.resources.get(sid)
        found: list[str] = []
        if original is None:
            found.append(f"original {rid} is not registered")
        if substitute is None:
            found.append(f"substitute {sid} is not registered")
        if original is not None and sid not in original.definition.approved_substitute_ids:
            found.append(f"{sid} is not an approved substitute for {rid}")
        if original is not None and substitute is not None:
            lacking = [
                cap
                for cap in original.definition.capabilities
                if cap not in substitute.definition.capabilities
            ]
            if lacking:
                found.append(f"{sid} lacks {rid}'s capabilities {', '.join(lacking)}")
        active = ctx.active.get(activity_id)
        if active is None or rid not in active.resource_ids:
            found.append(f"{rid} is not assigned to {activity_id} in the active plan")
        if found:
            problems.extend(found)
            entities.extend([sid, rid, activity_id])
        else:
            passed.append(f"{sid} is an approved, capable substitute for {rid} in {activity_id}")
            entities.extend([sid, rid])
    return _verdict("substitute_compatibility", problems, entities, "; ".join(passed))


def _participant_availability(
    ctx: PlanningContext, assignments: tuple[Assignment, ...], acc: _Assumptions
) -> CandidateCheck:
    subject: list[tuple[Assignment, str]] = []
    for a in _not_started(ctx, assignments):
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if resource is not None and resource.definition.kind == "person":
                subject.append((a, rid))
    if not subject:
        return _check(
            "participant_availability",
            "not_applicable",
            "No not-started activity needs a person",
        )
    problems: list[str] = []
    entities: list[str] = []
    for a, rid in subject:
        eta = ctx.resources[rid].reported_eta
        if eta is not None and eta > a.start:
            # A person's reported or hypothetical arrival after the start (runtime 1.2: a
            # person's delay report reaches the planner as a hypothesis, as equipment's does).
            origin = "hypothetical ETA" if rid in ctx.hypothesis_labels else "reported ETA"
            problems.append(
                f"{rid} {origin} {_t(eta)} is after {a.activity_id} starts at {_t(a.start)}"
            )
            entities.extend([rid, a.activity_id])
            continue
        checkin = _latest_checkin(ctx, rid)
        if checkin is not None:
            if not checkin.available.contains(a.window):
                problems.append(
                    f"{rid}'s latest check-in ({_t(checkin.at)}) is available "
                    f"{_span(checkin.available)}, not covering {a.activity_id} {_span(a)}"
                )
                entities.extend([rid, a.activity_id])
            continue
        declared = ctx.resources[rid].definition.window
        if not declared.contains(a.window):
            problems.append(
                f"{rid}'s declared window {_span(declared)} does not cover "
                f"{a.activity_id} {_span(a)} and {rid} has not checked in"
            )
            entities.extend([rid, a.activity_id])
            continue
        acc.add(
            CandidateAssumption(
                assumption_id=f"asm_declared_availability_{rid}_{a.activity_id}",
                kind="declared_availability",
                entity_id=rid,
                text=(
                    f"{rid} is assumed available for {a.activity_id} {_span(a)} "
                    f"({DISPLAY_TIMEZONE}) from the declared window {_span(declared)}; "
                    f"{rid} has not checked in"
                ),
                basis_ref=ctx.resources[rid].definition.source_ref,
            )
        )
    return _verdict(
        "participant_availability",
        problems,
        entities,
        "Every assigned person is covered by a check-in or, without one, by the declared window",
    )


def _accessibility(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    requirements = ctx.goal.accessibility_requirements
    if not requirements:
        return _check(
            "accessibility", "not_applicable", "The goal declares no accessibility requirement"
        )
    candidate = {a.activity_id: a for a in _occupying(ctx, assignments)}
    failed: list[str] = []
    unsupported: list[str] = []
    passed: list[str] = []
    idle: list[str] = []  # supported requirements that concern no activity still to run
    entities: list[str] = []
    for req in requirements:
        if req.kind not in SUPPORTED_ACCESSIBILITY_KINDS:
            unsupported.append(f"{req.requirement_id} has unsupported kind '{req.kind}'")
            entities.append(req.requirement_id)
            continue
        if req.capability is None:
            unsupported.append(f"{req.requirement_id} names no venue capability to check")
            entities.append(req.requirement_id)
            continue
        subject = [aid for aid in req.activity_ids if aid in candidate]
        if not subject:
            idle.append(f"{req.requirement_id} concerns no activity still to run")
            continue
        for aid in subject:
            spaces = [
                ctx.resources[rid]
                for rid in candidate[aid].resource_ids
                if rid in ctx.resources and ctx.resources[rid].definition.kind == "space"
            ]
            if any(req.capability in s.definition.capabilities for s in spaces):
                passed.append(f"{req.requirement_id}: {aid} venue provides {req.capability}")
            else:
                names = ", ".join(s.definition.resource_id for s in spaces) or "no space"
                failed.append(f"{req.requirement_id}: {aid} venue ({names}) lacks {req.capability}")
                entities.extend([req.requirement_id, aid])
    if failed:
        return _check("accessibility", "failed", "; ".join(failed + unsupported), entities)
    if unsupported:
        return _check(
            "accessibility",
            "unsupported",
            "; ".join(unsupported) + "; Wave 1 checks only venue_capability requirements",
            entities,
        )
    if not passed:
        # Nothing is subject to any requirement: not a vacuous pass.
        return _check("accessibility", "not_applicable", "; ".join(idle))
    return _check("accessibility", "passed", "; ".join(passed + idle), entities)


def _commitment_cutoff(ctx: PlanningContext, assignments: tuple[Assignment, ...]) -> CandidateCheck:
    subject: list[tuple[Assignment, ResourceView]] = []
    for a in _not_started(ctx, assignments):
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if resource is not None and resource.definition.terms.booking_required:
                subject.append((a, resource))
    if not subject:
        return _check(
            "commitment_cutoff",
            "not_applicable",
            "No not-started activity uses a booking-required resource",
        )
    problems: list[str] = []
    passed: list[str] = []
    entities: list[str] = []
    for a, resource in subject:
        rid = resource.definition.resource_id
        entities.append(rid)
        commitment = _covering_commitment(ctx, rid, a)
        if commitment is not None:
            passed.append(f"{rid} for {a.activity_id} is committed ({commitment.commitment_id})")
            continue
        cutoff = _cutoff(resource, a)
        limit = cutoff if cutoff is not None else a.start
        what = "commitment cutoff" if cutoff is not None else "start (no declared cutoff)"
        if ctx.effective_at >= limit:
            problems.append(
                f"{rid} for {a.activity_id} {_span(a)} has no covering commitment and its "
                f"{what} {_t(limit)} is not after {ctx.when()}"
            )
        else:
            passed.append(f"{rid} for {a.activity_id} must be committed before {_t(limit)}")
    return _verdict("commitment_cutoff", problems, entities, "; ".join(passed))


def _budget(
    ctx: PlanningContext, required: tuple[RequiredHold, ...], incremental: int
) -> CandidateCheck:
    holds = {h.hold_id: h for h in ctx.live_holds()}
    converted = sum(
        holds[r.bound_hold_id].reserved_cents
        for r in required
        if r.bound_hold_id is not None and r.bound_hold_id in holds
    )
    # Exposure of holds that expire before the apply takes effect is returned by then.
    lapsed = sum(h.reserved_cents for h in ctx.lapsing_holds())
    committed = ctx.budget.committed_cents
    reserved = ctx.budget.reserved_cents - lapsed
    total = committed + reserved - converted + incremental
    budget = ctx.goal.budget_cents
    arithmetic = (
        f"committed {committed} + reserved {reserved} - converted holds {converted} "
        f"+ incremental {incremental} = {total} cents"
    )
    if lapsed:
        arithmetic += (
            f" (reserved excludes {lapsed} cents of holds that expire by {_t(ctx.effective_at)})"
        )
    if total > budget:
        return _check("budget", "failed", f"{arithmetic} exceeds the budget {budget}")
    return _check("budget", "passed", f"{arithmetic}, within the budget {budget}")


# ---------------------------------------------------------------------------
# Required holds, catalog assumptions, authorization, preconditions
# ---------------------------------------------------------------------------


def required_holds(
    ctx: PlanningContext, actor: ActorContext, assignments: tuple[Assignment, ...]
) -> tuple[RequiredHold, ...]:
    """Booking-required resources of not-started activities that still need a commitment."""
    live = ctx.live_holds()
    needed: list[RequiredHold] = []
    for a in _not_started(ctx, assignments):
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if resource is None or not resource.definition.terms.booking_required:
                continue
            if _covering_commitment(ctx, rid, a) is not None:
                continue
            own = sorted(
                (
                    h
                    for h in live
                    if h.actor_id == actor.principal_id
                    and h.resource_id == rid
                    and h.activity_id == a.activity_id
                    and h.window.contains(a.window)
                ),
                key=lambda h: (-h.expires_at.timestamp(), h.hold_id),
            )
            needed.append(
                RequiredHold(
                    resource_id=rid,
                    activity_id=a.activity_id,
                    window=a.window,
                    bound_hold_id=own[0].hold_id if own else None,
                    commitment_cost_cents=resource.definition.terms.commitment_cost_cents,
                    commitment_cutoff=_cutoff(resource, a),
                )
            )
    return tuple(needed)


def _catalog_assumptions(
    ctx: PlanningContext, assignments: tuple[Assignment, ...], acc: _Assumptions
) -> None:
    for a in _not_started(ctx, assignments):
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if (
                resource is None
                or not resource.definition.terms.booking_required
                or resource.status != "available"
                or resource.status_basis != "catalog"
                or rid in ctx.hypothesis_labels
            ):
                continue
            acc.add(
                CandidateAssumption(
                    assumption_id=f"asm_catalog_availability_{rid}_{a.activity_id}",
                    kind="catalog_availability",
                    entity_id=rid,
                    text=(
                        f"{rid} is assumed available for {a.activity_id} {_span(a)} "
                        f"({DISPLAY_TIMEZONE}) from the authored catalog "
                        f"({resource.definition.source_ref}); no status record confirms it"
                    ),
                    basis_ref=resource.definition.source_ref,
                )
            )


def assess_authorization(
    ctx: PlanningContext,
    actor: ActorContext,
    assignments: tuple[Assignment, ...],
    changed: tuple[str, ...],
    incremental: int,
) -> AuthorizationAssessment:
    """Whether the actor's grant covers applying this candidate (separate from feasibility)."""
    grant = actor.grant
    if grant is None:
        missing = MissingPermission(
            kind="grant_invalid",
            detail=f"{actor.principal_id} has no authority grant",
            grant_id=None,
        )
        return AuthorizationAssessment(sufficient=False, missing=(missing,))
    gid = grant.grant_id
    found: list[MissingPermission] = []
    if not actor.grant_valid:
        found.append(
            MissingPermission(
                kind="grant_invalid",
                detail=f"grant {gid} is not valid now (revoked or expired)",
                grant_id=gid,
            )
        )
    elif ctx.effective_at >= grant.expires_at:
        found.append(
            MissingPermission(
                kind="grant_invalid",
                detail=f"grant {gid} expires at {_t(grant.expires_at)}, not after {ctx.when()}",
                grant_id=gid,
            )
        )
    if "apply_plan" not in grant.allowed_tools:
        found.append(
            MissingPermission(
                kind="tool_not_granted",
                detail=f"grant {gid} does not allow apply_plan",
                grant_id=gid,
                field="allowed_tools",
            )
        )
    for aid in changed:
        if aid not in grant.activity_ids:
            found.append(
                MissingPermission(
                    kind="activity_out_of_scope",
                    detail=f"changed activity {aid} is outside grant {gid}",
                    grant_id=gid,
                    field="activity_ids",
                )
            )
    candidate = {a.activity_id: a for a in assignments}
    resources: list[str] = []
    for aid in changed:
        assignment = candidate.get(aid)
        if assignment is not None:
            resources.extend(r for r in assignment.resource_ids if r not in resources)
    for rid in resources:
        if rid not in grant.resource_ids:
            found.append(
                MissingPermission(
                    kind="resource_out_of_scope",
                    detail=f"resource {rid} of a changed assignment is outside grant {gid}",
                    grant_id=gid,
                    field="resource_ids",
                )
            )
    needed = actor.committed_used_cents + incremental
    limit = grant.max_total_committed_cents
    if needed > limit:
        found.append(
            MissingPermission(
                kind="committed_spend_limit",
                detail=(
                    f"committing {incremental} cents brings committed use to {needed}, above "
                    f"grant {gid} max_total_committed_cents {limit}; review item: "
                    f"{COMMITTED_REVIEW_ITEM}"
                ),
                grant_id=gid,
                field="max_total_committed_cents",
                current_value=limit,
                required_value=needed,
            )
        )
    return AuthorizationAssessment(sufficient=not found, missing=tuple(found))


def _preconditions(
    ctx: PlanningContext,
    assignments: tuple[Assignment, ...],
    holds: tuple[RequiredHold, ...],
    authorization: AuthorizationAssessment,
    hypothetical: bool,
) -> tuple[str, ...]:
    tz = DISPLAY_TIMEZONE
    lines: list[str] = []
    if hypothetical:
        lines.append(
            "This evaluation rests on hypotheses; re-evaluate without hypotheses before applying."
        )
    for a in _not_started(ctx, assignments):
        name = readable(a.activity_id)
        start = _t(a.start)
        for rid in a.resource_ids:
            resource = ctx.resources.get(rid)
            if resource is None:
                continue
            kind = resource.definition.kind
            if kind == "equipment" and resource.status == "expected":
                lines.append(f"Observe {rid} arrival before {name} start at {start} ({tz}).")
            elif kind == "person":
                checkin = _latest_checkin(ctx, rid)
                if checkin is None or not checkin.available.contains(a.window):
                    lines.append(
                        f"Confirm {rid} checked in before {start} ({tz}) with availability "
                        f"covering {_span(a)} for {name}."
                    )
    live = {h.hold_id: h for h in ctx.live_holds()}
    for req in holds:
        if req.commitment_cutoff is not None:
            cutoff = f"commitment cutoff {_t(req.commitment_cutoff)} ({tz})"
        else:
            cutoff = (
                f"no declared commitment cutoff, so commit before {_t(req.window.start)} ({tz})"
            )
        if req.bound_hold_id is None:
            lines.append(
                f"Acquire a live hold on {req.resource_id} covering {_span(req.window)} "
                f"before applying; {cutoff}."
            )
        else:
            hold = live.get(req.bound_hold_id)
            expiry = f" (expires {_t(hold.expires_at)})" if hold is not None else ""
            lines.append(
                f"Apply while hold {req.bound_hold_id} on {req.resource_id} is live{expiry}; "
                f"{cutoff}."
            )
    for missing in authorization.missing:
        if missing.kind == "committed_spend_limit":
            lines.append(
                f"Obtain organizer approval to raise {missing.grant_id} "
                f"max_total_committed_cents from {missing.current_value} to "
                f"{missing.required_value} (review item: {COMMITTED_REVIEW_ITEM})."
            )
        else:
            lines.append(f"Resolve authorization: {missing.detail}.")
    lines.append(REVALIDATE_PRECONDITION)
    return tuple(dict.fromkeys(lines))


def constraint_status(checks: tuple[CandidateCheck, ...]) -> ConstraintResult:
    if any(c.status == "failed" for c in checks):
        return "infeasible"
    if any(c.status == "unsupported" for c in checks):
        return "unknown"
    return "feasible_under_assumptions"


def assess_candidate(
    ctx: PlanningContext,
    actor: ActorContext,
    assignments: tuple[Assignment, ...],
    edits: tuple[Edit, ...],
    *,
    hypothetical: bool,
) -> Assessment:
    """Run every hard check and derive assumptions, holds, authorization and preconditions."""
    changed = changed_activities(ctx.active, assignments)
    holds = required_holds(ctx, actor, assignments)
    incremental = sum(h.commitment_cost_cents for h in holds)
    acc = _Assumptions()
    for note in ctx.hypothesis_assumptions:
        acc.add(note)
    checks = (
        _required_activities(ctx, assignments),
        _fixed_venue(ctx, assignments),
        _started_history(ctx, assignments),
        _no_past_change(ctx, assignments, changed),
        _activity_windows(ctx, assignments, edits),
        _event_window(ctx, assignments),
        _dependencies(ctx, assignments),
        _program_exclusivity(ctx, assignments),
        _occupancy_capacity(ctx),
        _resource_capacity(ctx, assignments),
        _resource_status(ctx, assignments),
        _arrival_assumptions(ctx, assignments, acc),
        _substitute_compatibility(ctx, edits),
        _participant_availability(ctx, assignments, acc),
        _accessibility(ctx, assignments),
        _commitment_cutoff(ctx, assignments),
        _budget(ctx, holds, incremental),
    )
    _catalog_assumptions(ctx, assignments, acc)
    authorization = assess_authorization(ctx, actor, assignments, changed, incremental)
    return Assessment(
        changed_activity_ids=changed,
        checks=checks,
        assumptions=tuple(acc.items),
        required_holds=holds,
        authorization=authorization,
        incremental_committed_cents=incremental,
        constraint_status=constraint_status(checks),
        execution_preconditions=_preconditions(
            ctx, assignments, holds, authorization, hypothetical
        ),
    )
