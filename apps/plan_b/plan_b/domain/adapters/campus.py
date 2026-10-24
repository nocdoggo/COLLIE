"""Campus domain adapter (activity/resource core) for the campus and skills-exchange profiles.

``evaluate`` and ``revalidate`` are pure: they read one ``PlanningSnapshot`` and the caller's
``ActorContext``, never the clock, a database, randomness or private runner input.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from plan_b.domain.adapters.base import ReadinessBasis, ReadinessMode
from plan_b.domain.adapters.campus_outcome import score_campus_outcome
from plan_b.domain.adapters.outcome import DomainOutcome
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
    EpisodeHistory,
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
from plan_b.domain.projection import initial_snapshot
from plan_b.domain.readiness import check_readiness
from plan_b.domain.timeutil import DISPLAY_TIMEZONE, minutes_between

ADAPTER_ID = "campus/1.0.0"
PROFILE_IDS = ("campus_showcase", "community_skills_exchange")
# Hard checks the initial plan may fail at load: they depend on status and arrival evidence
# that the episode is designed to change (a resource awaiting delivery, or already reported
# unavailable, is a scenario rather than a configuration error).
EVIDENCE_DEPENDENT_CHECKS = frozenset({"resource_status", "arrival_assumptions"})


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
        """Every reference resolves, and the initial plan passes the planner's hard checks.

        The initial plan is checked last, once everything else is valid (the planner assumes
        resolved references). Its keep candidate may fail only the evidence-dependent checks
        (``EVIDENCE_DEPENDENT_CHECKS``)."""
        problems: list[str] = []
        if scenario.profile_id not in self.profile_ids:
            problems.append(f"profile {scenario.profile_id} is not served by {self.adapter_id}")
        if scenario.timezone != DISPLAY_TIMEZONE:
            problems.append(f"timezone {scenario.timezone} differs from display {DISPLAY_TIMEZONE}")
        activity_ids = [a.activity_id for a in scenario.activities]
        resource_ids = [r.resource_id for r in scenario.resources]
        activities = {a.activity_id: a for a in scenario.activities}
        resources = {r.resource_id: r for r in scenario.resources}
        for kind, ids in (
            ("activity", activity_ids),
            ("resource", resource_ids),
            ("principal", [p.principal_id for p in scenario.principals]),
            ("grant", [g.grant_id for g in scenario.authority_grants]),
            ("status source", [s.source_id for s in scenario.status_sources]),
        ):
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
        problems.extend(self._initial_state_problems(scenario, activities, resources))
        problems.extend(self._status_term_problems(scenario))
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
        principals = {p.principal_id for p in scenario.principals}
        grants = {g.grant_id: g for g in scenario.authority_grants}
        for grant in scenario.authority_grants:
            if grant.event_id != scenario.event_id:
                problems.append(f"grant {grant.grant_id} is for event {grant.event_id}")
            if grant.principal_id not in principals:
                problems.append(f"grant {grant.grant_id}: unknown principal {grant.principal_id}")
            for rid in grant.resource_ids:
                if rid not in resources:
                    problems.append(f"grant {grant.grant_id}: unknown resource {rid}")
            for aid in grant.activity_ids:
                if aid not in activities:
                    problems.append(f"grant {grant.grant_id}: unknown activity {aid}")
        for principal in scenario.principals:
            pid = principal.principal_id
            held = grants.get(principal.grant_id)
            if held is None:
                problems.append(f"principal {pid}: unknown grant")
            elif (held.principal_id, held.principal_role) != (pid, principal.role):
                problems.append(
                    f"principal {pid} ({principal.role}) holds grant {held.grant_id}, issued to "
                    f"{held.principal_id} ({held.principal_role})"
                )
            for rid in principal.speaks_for_resource_ids:
                if rid not in resources:
                    problems.append(f"principal {pid} speaks for unknown resource {rid}")
        coordinators = sum(1 for p in scenario.principals if p.role == "coordinator_agent")
        if coordinators != 1:
            problems.append(f"{coordinators} coordinator_agent principals; exactly one is required")
        if not problems:
            problems.extend(self._initial_plan_problems(scenario))
        return problems

    @staticmethod
    def _initial_state_problems(
        scenario: PublicScenario,
        activities: dict[str, ActivityDef],
        resources: dict[str, ResourceDef],
    ) -> list[str]:
        """Lifecycle, check-in and observation references of the loaded state."""
        problems: list[str] = []
        st = scenario.initial_state
        if st.event_id != scenario.event_id:
            problems.append(f"initial state is for event {st.event_id}, not {scenario.event_id}")
        recorded: set[str] = set()
        for lc in st.lifecycle:
            if lc.activity_id not in activities:
                problems.append(f"initial lifecycle record for unknown activity {lc.activity_id}")
            if lc.activity_id in recorded:
                problems.append(f"activity {lc.activity_id} has more than one lifecycle record")
            recorded.add(lc.activity_id)
        principals = {p.principal_id: p for p in scenario.principals}
        for c in st.checked_in:
            resource = resources.get(c.resource_id)
            if resource is None:
                problems.append(f"initial check-in for unregistered resource {c.resource_id}")
            elif resource.kind != "person":
                problems.append(f"initial check-in for {c.resource_id}, which is not a person")
            if c.principal_id is None:
                continue
            principal = principals.get(c.principal_id)
            if principal is None:
                problems.append(f"initial check-in by unknown principal {c.principal_id}")
            elif c.resource_id not in principal.speaks_for_resource_ids:
                problems.append(
                    f"initial check-in: {c.principal_id} does not speak for {c.resource_id}"
                )
        # The entities an observation may concern, as in submit_observation.
        entities = set(activities) | set(resources) | {scenario.event_id}
        for obs in scenario.visible_observations:
            if obs.event_id != scenario.event_id:
                problems.append(f"observation {obs.observation_id} is for event {obs.event_id}")
            if obs.entity_id not in entities:
                problems.append(f"observation {obs.observation_id}: unknown entity {obs.entity_id}")
        return problems

    @staticmethod
    def _status_term_problems(scenario: PublicScenario) -> list[str]:
        """A resource's status source must be registered and answer its queryable facts for it,
        as ``query_status`` requires."""
        problems: list[str] = []
        sources = {s.source_id: s for s in scenario.status_sources}
        for resource in scenario.resources:
            rid = resource.resource_id
            sid = resource.terms.status_source_id
            if sid is None:
                if resource.terms.queryable_facts:
                    problems.append(f"{rid} lists queryable facts but no status source")
                continue
            source = sources.get(sid)
            if source is None:
                problems.append(f"{rid} status source {sid} is not registered")
                continue
            if rid not in source.entity_ids:
                problems.append(f"status source {sid} does not cover {rid}")
            for fact in resource.terms.queryable_facts:
                if fact not in source.facts:
                    problems.append(f"status source {sid} does not answer {fact} for {rid}")
        return problems

    @staticmethod
    def _initial_plan_problems(scenario: PublicScenario) -> list[str]:
        """The keep candidate at load, assessed by the planner's own hard checks."""
        snapshot = initial_snapshot(scenario)
        agent = next(p for p in scenario.principals if p.role == "coordinator_agent")
        grant = next(g for g in scenario.authority_grants if g.grant_id == agent.grant_id)
        actor = ActorContext(
            principal_id=agent.principal_id,
            role="coordinator_agent",
            grant=grant,
            grant_version=1,
            grant_valid=snapshot.clock < grant.expires_at,
            committed_used_cents=0,
            reserved_used_cents=0,
        )
        assessment = assess_candidate(
            build_context(snapshot), actor, snapshot.plan.assignments, (), hypothetical=False
        )
        return [
            f"initial plan fails {c.constraint_id}: {_sentence_part(c.detail)}"
            for c in assessment.checks
            if c.status == "failed" and c.constraint_id not in EVIDENCE_DEPENDENT_CHECKS
        ]

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
        self,
        snapshot: ReadinessBasis,
        activity_id: str,
        at: datetime,
        *,
        mode: ReadinessMode = "execution",
    ) -> ReadinessReport:
        definitions = {v.definition.activity_id: v.definition for v in snapshot.activities}
        if activity_id not in definitions:
            raise KeyError(f"unknown activity {activity_id!r}")
        assignments = {a.activity_id: a for a in snapshot.plan.assignments}
        return check_readiness(
            activity=definitions[activity_id],
            assignment=assignments.get(activity_id),
            at=at,
            mode=mode,
            lifecycles={v.definition.activity_id: v.lifecycle for v in snapshot.activities},
            assignments=assignments,
            resources={r.definition.resource_id: r for r in snapshot.resources},
            checkins=snapshot.checkins,
            commitments=snapshot.commitments,
            program_activity_ids={aid for aid, d in definitions.items() if d.program},
        )

    def score_outcome(self, final: EventStateView, history: EpisodeHistory) -> DomainOutcome:
        """Required activities completed by the hard end, and the executed-rule violations
        (program overlap, resource capacity, starts without their evidence, late completion)."""
        return score_campus_outcome(final, history)
