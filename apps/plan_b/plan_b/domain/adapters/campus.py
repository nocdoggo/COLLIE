"""Campus domain adapter (activity/resource core) for the campus and skills-exchange profiles.

``evaluate`` and ``revalidate`` are pure: they read one ``PlanningSnapshot`` and the caller's
``ActorContext``, never the clock, a database, randomness or private runner input.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from plan_b.domain.candidates import (
    apply_edits,
    candidate_ids,
    candidate_label,
    describe_action_space,
    edits_signature,
    enabled_templates,
    generate_edit_lists,
)
from plan_b.domain.constraints import (
    SUPPORTED_ACCESSIBILITY_KINDS,
    PlanningContext,
    assess_candidate,
    build_context,
)
from plan_b.domain.models import (
    ActivityDef,
    ActorContext,
    AlternateFormatTemplate,
    Assignment,
    CandidateResult,
    Edit,
    EvaluationRequest,
    EvaluationResult,
    EventStateView,
    InfeasibilitySummary,
    PlanningSnapshot,
    PublicScenario,
    ReadinessReport,
    ResourceDef,
    ShiftTemplate,
    SubstituteTemplate,
    SwapTemplate,
)
from plan_b.domain.objective import (
    is_feasible,
    objective_components,
    rank_candidates,
    unsupported_tie_breaks,
)
from plan_b.domain.readiness import check_readiness
from plan_b.domain.timeutil import DISPLAY_TIMEZONE, fmt_ts, minutes_between

ADAPTER_ID = "campus/1.0.0"
PROFILE_IDS = ("campus_showcase", "community_skills_exchange")


def _sentence_part(detail: str) -> str:
    return detail.rstrip(". ")


def _rationale(candidate: CandidateResult) -> str:
    """One factual sentence about the candidate's feasibility and cost."""
    failed = [c for c in candidate.checks if c.status == "failed"]
    unsupported = [c for c in candidate.checks if c.status == "unsupported"]
    if failed:
        ids = ", ".join(c.constraint_id for c in failed)
        return f"Fails {ids}: {_sentence_part(failed[0].detail)}."
    if unsupported:
        ids = ", ".join(c.constraint_id for c in unsupported)
        return (
            f"No hard check fails, but {ids} could not be evaluated: "
            f"{_sentence_part(unsupported[0].detail)}."
        )
    count = len(candidate.assumptions)
    noun = "assumption" if count == 1 else "assumptions"
    obj = candidate.objective
    if not candidate.changed_activity_ids:
        return f"Leaves the active plan unchanged and passes every hard check under {count} {noun}."
    changed = ", ".join(candidate.changed_activity_ids)
    n = len(candidate.changed_activity_ids)
    return (
        f"Changes {n} {'activity' if n == 1 else 'activities'} ({changed}) "
        f"with {obj.start_shift_minutes} min of total start shift and "
        f"{candidate.incremental_committed_cents} cents of new committed spending, and passes "
        f"every hard check under {count} {noun}."
    )


def _infeasibility(
    snapshot: PlanningSnapshot,
    enabled: tuple[str, ...],
    candidates: tuple[CandidateResult, ...],
    *,
    generated: int,
    truncated: bool,
) -> InfeasibilitySummary:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        for check in candidate.checks:
            if check.status == "failed":
                counts[check.constraint_id] += 1
    blocking = tuple(sorted(counts))
    space = describe_action_space(
        snapshot.planning,
        enabled,
        generated=generated,
        evaluated=len(candidates),
        truncated=truncated,
    )
    undecided = sum(1 for c in candidates if c.constraint_status == "unknown")
    if counts:
        top = max(counts.values())
        common = sorted(cid for cid, n in counts.items() if n == top)[0]
        detail = (
            f"No evaluated candidate is feasible within the declared action space; the most "
            f"common blocker is {common} (failed in {top} of {len(candidates)} candidates)."
        )
    else:
        detail = "No evaluated candidate is feasible within the declared action space."
    if undecided:
        detail += f" {undecided} candidates could not be decided (unsupported checks)."
    if truncated:
        detail += " The candidate cap truncated the search, so later candidates were not checked."
    return InfeasibilitySummary(
        declared_action_space=space, blocking_constraints=blocking, detail=detail
    )


class CampusAdapter:
    """Finite-menu planner and readiness/outcome rules for the activity/resource core."""

    adapter_id: str = ADAPTER_ID
    profile_ids: tuple[str, ...] = PROFILE_IDS

    # -- configuration -----------------------------------------------------

    def validate_config(self, scenario: PublicScenario) -> list[str]:
        problems: list[str] = []
        if scenario.profile_id not in self.profile_ids:
            problems.append(f"profile {scenario.profile_id} is not served by {self.adapter_id}")
        if scenario.timezone != DISPLAY_TIMEZONE:
            problems.append(f"timezone {scenario.timezone} differs from display {DISPLAY_TIMEZONE}")
        activity_ids = [a.activity_id for a in scenario.activities]
        resource_ids = [r.resource_id for r in scenario.resources]
        activities = {a.activity_id: a for a in scenario.activities}
        resources = {r.resource_id: r for r in scenario.resources}
        for kind, ids in (("activity", activity_ids), ("resource", resource_ids)):
            for dup in sorted({i for i in ids if ids.count(i) > 1}):
                problems.append(f"duplicate {kind} id {dup}")
        goal = scenario.goal
        for aid in goal.required_activity_ids:
            if aid not in activities:
                problems.append(f"required activity {aid} is not defined")
            elif not activities[aid].required:
                problems.append(f"required activity {aid} is not marked required")
        venue = resources.get(goal.fixed_venue_id)
        if venue is None:
            problems.append(f"fixed venue {goal.fixed_venue_id} is not a registered resource")
        elif venue.kind != "space":
            problems.append(f"fixed venue {goal.fixed_venue_id} is not a space")
        if goal.hard_end <= goal.public_start:
            problems.append("goal hard_end is not after public_start")
        for activity in scenario.activities:
            for pred in activity.predecessors:
                if pred not in activities:
                    problems.append(f"{activity.activity_id} predecessor {pred} is not defined")
            for rid in activity.required_resources:
                if rid not in resources:
                    problems.append(f"{activity.activity_id} resource {rid} is not registered")
            length = minutes_between(activity.window.start, activity.window.end)
            if activity.duration_minutes > length:
                problems.append(f"{activity.activity_id} duration exceeds its window")
        for resource in scenario.resources:
            for sid in resource.approved_substitute_ids:
                if sid not in resources:
                    problems.append(f"{resource.resource_id} substitute {sid} is not registered")
        seen_assignments: set[str] = set()
        for assignment in scenario.initial_state.assignments:
            aid = assignment.activity_id
            if aid not in activities:
                problems.append(f"initial assignment for unknown activity {aid}")
            if aid in seen_assignments:
                problems.append(f"activity {aid} has more than one initial assignment")
            seen_assignments.add(aid)
            for rid in assignment.resource_ids:
                if rid not in resources:
                    problems.append(f"initial assignment {aid} uses unregistered resource {rid}")
        problems.extend(self._template_problems(scenario, activities, resources))
        for name in unsupported_tie_breaks(scenario.planning.tie_breaks):
            problems.append(f"tie-break {name} is not supported")
        for req in goal.accessibility_requirements:
            if req.kind in SUPPORTED_ACCESSIBILITY_KINDS and req.capability is None:
                problems.append(
                    f"accessibility requirement {req.requirement_id} names no capability"
                )
            if not req.activity_ids:
                # An empty list has no defined meaning (venue-wide or none), so it is refused.
                problems.append(f"accessibility requirement {req.requirement_id} lists no activity")
            for aid in req.activity_ids:
                if aid not in activities:
                    problems.append(
                        f"accessibility requirement {req.requirement_id}: unknown {aid}"
                    )
        for source in scenario.status_sources:
            for eid in source.entity_ids:
                if eid not in resources:
                    problems.append(f"status source {source.source_id}: unknown entity {eid}")
        grant_ids = {g.grant_id for g in scenario.authority_grants}
        for grant in scenario.authority_grants:
            for rid in grant.resource_ids:
                if rid not in resources:
                    problems.append(f"grant {grant.grant_id}: unknown resource {rid}")
            for aid in grant.activity_ids:
                if aid not in activities:
                    problems.append(f"grant {grant.grant_id}: unknown activity {aid}")
        for principal in scenario.principals:
            if principal.grant_id not in grant_ids:
                problems.append(f"principal {principal.principal_id}: unknown grant")
        return problems

    @staticmethod
    def _template_problems(
        scenario: PublicScenario,
        activities: dict[str, ActivityDef],
        resources: dict[str, ResourceDef],
    ) -> list[str]:
        problems: list[str] = []
        formats: set[tuple[str, str]] = set()
        for index, template in enumerate(scenario.planning.edit_templates):
            where = f"edit template {index} ({template.template})"
            if isinstance(template, SwapTemplate):
                first, second = template.activity_ids
                if first == second:
                    problems.append(f"{where} swaps an activity with itself")
                for aid in (first, second):
                    if aid not in activities:
                        problems.append(f"{where}: unknown activity {aid}")
            elif isinstance(template, ShiftTemplate):
                if template.activity_id not in activities:
                    problems.append(f"{where}: unknown activity {template.activity_id}")
                offsets = template.offsets_minutes
                if not offsets:
                    problems.append(f"{where} lists no offsets")
                if 0 in offsets:
                    problems.append(f"{where} includes a zero offset")
                if len(set(offsets)) != len(offsets):
                    problems.append(f"{where} repeats an offset")
            elif isinstance(template, SubstituteTemplate):
                activity = activities.get(template.activity_id)
                if activity is None:
                    problems.append(f"{where}: unknown activity {template.activity_id}")
                elif template.resource_id not in activity.required_resources:
                    problems.append(
                        f"{where}: {template.resource_id} is not required by {template.activity_id}"
                    )
                if template.resource_id not in resources:
                    problems.append(f"{where}: unknown resource {template.resource_id}")
                if not template.substitute_ids:
                    problems.append(f"{where} lists no substitutes")
            elif isinstance(template, AlternateFormatTemplate):
                if template.activity_id not in activities:
                    problems.append(f"{where}: unknown activity {template.activity_id}")
                for rid in template.required_resources:
                    if rid not in resources:
                        problems.append(f"{where}: unknown resource {rid}")
                key = (template.activity_id, template.format_id)
                if key in formats:
                    problems.append(f"{where} repeats format {template.format_id}")
                formats.add(key)
        return problems

    # -- planning ----------------------------------------------------------

    def _result(
        self,
        ctx: PlanningContext,
        actor: ActorContext,
        *,
        candidate_id: str,
        report_id: str,
        signature: str,
        label: str,
        edits: tuple[Edit, ...],
        assignments: tuple[Assignment, ...],
        hypothetical: bool,
    ) -> CandidateResult:
        assessment = assess_candidate(ctx, actor, assignments, edits, hypothetical=hypothetical)
        objective = objective_components(
            active=ctx.active,
            assignments=assignments,
            changed=assessment.changed_activity_ids,
            additional_committed_cents=assessment.incremental_committed_cents,
            activities=ctx.activities,
            resources=ctx.resources,
            weights=ctx.goal.objective_weights,
        )
        applicable = (
            assessment.constraint_status == "feasible_under_assumptions"
            and assessment.authorization.sufficient
            and all(h.bound_hold_id is not None for h in assessment.required_holds)
            and not hypothetical
        )
        draft = CandidateResult(
            candidate_id=candidate_id,
            report_id=report_id,
            signature=signature,
            label=label,
            edits=edits,
            assignments=assignments,
            changed_activity_ids=assessment.changed_activity_ids,
            incremental_committed_cents=assessment.incremental_committed_cents,
            constraint_status=assessment.constraint_status,
            checks=assessment.checks,
            assumptions=assessment.assumptions,
            execution_preconditions=assessment.execution_preconditions,
            required_holds=assessment.required_holds,
            authorization=assessment.authorization,
            objective=objective,
            rank=None,
            applicable_now=applicable,
            rationale="",
        )
        return draft.model_copy(update={"rationale": _rationale(draft)})

    def evaluate(
        self,
        snapshot: PlanningSnapshot,
        actor: ActorContext,
        request: EvaluationRequest,
        evaluation_id: str,
    ) -> EvaluationResult:
        hypothetical = bool(request.hypotheses)
        ctx = build_context(snapshot, request.hypotheses)
        planning = snapshot.planning
        enabled = enabled_templates(planning, request.templates)
        menu = generate_edit_lists(planning, enabled)
        chosen = menu[: planning.candidate_cap]
        truncated = len(menu) > planning.candidate_cap
        results: list[CandidateResult] = []
        keep_id: str | None = None
        for edits in chosen:
            signature = edits_signature(edits)
            candidate_id, report_id = candidate_ids(evaluation_id, signature)
            if not edits:
                keep_id = candidate_id
            results.append(
                self._result(
                    ctx,
                    actor,
                    candidate_id=candidate_id,
                    report_id=report_id,
                    signature=signature,
                    label=candidate_label(edits, planning),
                    edits=edits,
                    assignments=apply_edits(snapshot.plan.assignments, edits, planning),
                    hypothetical=hypothetical,
                )
            )
        ordered = rank_candidates(results, planning.tie_breaks)
        feasible = [c for c in ordered if is_feasible(c)]
        applicable = [c for c in feasible if c.applicable_now]
        infeasibility = None
        if not feasible:
            infeasibility = _infeasibility(
                snapshot, enabled, ordered, generated=len(menu), truncated=truncated
            )
        return EvaluationResult(
            evaluation_id=evaluation_id,
            event_id=snapshot.event_id,
            revision=snapshot.revision,
            goal_version=snapshot.goal.version,
            evaluated_at=snapshot.clock,
            actor_id=actor.principal_id,
            hypothetical=hypothetical,
            hypotheses=request.hypotheses,
            templates=enabled,
            max_combined_edits=planning.max_combined_edits,
            candidate_cap=planning.candidate_cap,
            generated_count=len(menu),
            evaluated_count=len(chosen),
            truncated=truncated,
            candidates=ordered,
            best_candidate_id=feasible[0].candidate_id if feasible else None,
            best_applicable_candidate_id=applicable[0].candidate_id if applicable else None,
            keep_candidate_id=keep_id,
            infeasibility=infeasibility,
        )

    def revalidate(
        self, snapshot: PlanningSnapshot, actor: ActorContext, candidate: CandidateResult
    ) -> CandidateResult:
        ctx = build_context(snapshot)
        return self._result(
            ctx,
            actor,
            candidate_id=candidate.candidate_id,
            report_id=candidate.report_id,
            signature=candidate.signature,
            label=candidate.label,
            edits=candidate.edits,
            assignments=candidate.assignments,
            hypothetical=False,
        )

    # -- execution and outcome --------------------------------------------

    def check_readiness(
        self, snapshot: PlanningSnapshot, activity_id: str, at: datetime
    ) -> ReadinessReport:
        definitions = {v.definition.activity_id: v.definition for v in snapshot.activities}
        if activity_id not in definitions:
            raise KeyError(f"unknown activity {activity_id!r}")
        assignments = {a.activity_id: a for a in snapshot.plan.assignments}
        return check_readiness(
            activity=definitions[activity_id],
            assignment=assignments.get(activity_id),
            at=at,
            mode="execution",
            lifecycles={v.definition.activity_id: v.lifecycle for v in snapshot.activities},
            assignments=assignments,
            resources={r.definition.resource_id: r for r in snapshot.resources},
            checkins=snapshot.checkins,
            commitments=snapshot.commitments,
            program_activity_ids={aid for aid, d in definitions.items() if d.program},
        )

    def score_outcome(self, view: EventStateView) -> dict[str, Any]:
        """Goal attainment computed only from the visible state."""
        goal = view.goal
        rows: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        started_at: dict[str, datetime] = {}
        for activity in view.activities:
            history = sorted(activity.history, key=lambda e: e.seq)
            started = next((e for e in history if e.state == "started"), None)
            completed = next((e for e in history if e.state == "completed"), None)
            failed = next((e for e in history if e.state == "failed"), None)
            aid = activity.definition.activity_id
            if started is not None:
                started_at[aid] = started.at
            assignment = activity.assignment
            row: dict[str, Any] = {
                "activity_id": aid,
                "required": aid in goal.required_activity_ids,
                "lifecycle": activity.lifecycle,
                "assigned_start": fmt_ts(assignment.start) if assignment else None,
                "assigned_end": fmt_ts(assignment.end) if assignment else None,
                "started_at": fmt_ts(started.at) if started else None,
                "completed_at": fmt_ts(completed.at) if completed else None,
                "completed_by_deadline": (
                    activity.lifecycle == "completed"
                    and completed is not None
                    and completed.at <= goal.hard_end
                ),
                "failure_reasons": list(failed.reasons) if failed else [],
            }
            rows.append(row)
            by_id[aid] = row
        required = list(goal.required_activity_ids)
        on_time = [aid for aid in required if aid in by_id and by_id[aid]["completed_by_deadline"]]
        opening = self._opening_activity(view)
        opening_started = started_at.get(opening) if opening else None
        delay = (
            minutes_between(goal.public_start, opening_started)
            if opening_started is not None
            else None
        )
        budget = view.budget
        return {
            "adapter_id": self.adapter_id,
            "event_id": view.event_id,
            "evaluated_at": fmt_ts(view.clock),
            "goal_version": goal.version,
            "hard_end": fmt_ts(goal.hard_end),
            "activities": rows,
            "required_total": len(required),
            "required_completed_by_deadline": len(on_time),
            "missing_required_activity_ids": [aid for aid in required if aid not in on_time],
            "all_required_completed_by_deadline": len(on_time) == len(required),
            "public_start": fmt_ts(goal.public_start),
            "opening_activity_id": opening,
            "opening_started_at": fmt_ts(opening_started) if opening_started else None,
            "opening_start_delay_minutes": delay,
            "opened_on_time": delay is not None and delay <= 0,
            "budget_cents": budget.budget_cents,
            "committed_cents": budget.committed_cents,
            "reserved_cents": budget.reserved_cents,
            "within_budget": budget.committed_cents + budget.reserved_cents <= budget.budget_cents,
        }

    @staticmethod
    def _opening_activity(view: EventStateView) -> str | None:
        """The required activity whose assignment starts first at or after the public start."""
        public_start = view.goal.public_start
        assigned = [
            (a.assignment.start, a.definition.activity_id)
            for a in view.activities
            if a.assignment is not None
            and a.definition.activity_id in view.goal.required_activity_ids
            and a.assignment.start >= public_start
        ]
        return min(assigned)[1] if assigned else None
