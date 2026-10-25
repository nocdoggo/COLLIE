"""Pantry Continuity domain adapter (``pantry/1.0.0``): the activity/resource core plus
consumable stock and a service target.

The event core (references, windows, dependencies, the staff roster, venue, budget, the keep
plan's hard checks) is the campus adapter's, unchanged: this adapter extends it and owns only
the added semantics.

* **Candidate menu.** Keep, the configured event edits, and one candidate per declared stock
  option (``PublicScenario.stock_options``): ``allocate_stock`` allocates the pool's usable
  units to the target, ``transfer_stock`` also counts an alternate pool's units after a staff
  handoff, ``await_shipment`` counts the pool's outstanding expected shipments. Each allocation
  is capped by the target and by the service throughput still achievable before its deadline.
  Stock edits are not combined with each other.
* **Stock checks** (after the activity checks): ``consumable_allocation`` (registered pool,
  target, activity and unit; never below what is committed or distributed),
  ``stock_on_hand`` (the candidate's demand on each pool, summed across all its activities
  whatever their windows, fits the units usable by this actor; expected units never count),
  ``stock_transfer`` (an alternate pool can still hand off the shortfall before the exclusive
  handoff cutoff, given the staff response latency) and ``service_throughput`` (the allocation
  can be distributed before the deadline at the declared rate while staff are declared).
* **Coverage.** A partial allocation is feasible; its unfulfilled units are reported per target
  and cost ``UNFULFILLED_UNIT_WEIGHT`` objective points each. Feasibility of a candidate is
  never feasibility of the full target.
* **Applicability.** On top of the core rules: every allocation not yet committed is matched
  exactly by the actor's live activity holds (``required_stock_holds``), and no alternate
  units are still awaiting a handoff (``stock_transfers``).

Pure like the campus adapter: one snapshot and an actor context in, no database, clock or
private input.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from plan_b.domain.adapters.base import ReadinessBasis, ReadinessMode
from plan_b.domain.adapters.campus import CampusAdapter
from plan_b.domain.adapters.campus_outcome import score_campus_outcome
from plan_b.domain.adapters.outcome import DomainOutcome, Violation
from plan_b.domain.candidates import (
    apply_edits,
    candidate_ids,
    candidate_label,
    describe_action_space,
    edits_signature,
    enabled_templates,
    generate_edit_lists,
    readable,
)
from plan_b.domain.constraints import (
    PlanningContext,
    assess_authorization,
    assess_candidate,
    build_context,
    constraint_status,
)
from plan_b.domain.models import (
    STAFF_TOOLS,
    ActorContext,
    Assignment,
    CandidateAssumption,
    CandidateCheck,
    CandidateResult,
    CheckStatus,
    ConsumableAllocation,
    ConsumableStateView,
    Edit,
    EpisodeHistory,
    EvaluationRequest,
    EvaluationResult,
    EventStateView,
    HoldView,
    Hypothesis,
    InfeasibilitySummary,
    ObjectiveComponents,
    PlanningSnapshot,
    PublicScenario,
    ReadinessReport,
    RequiredStockHold,
    ResourceDef,
    ServiceCoverage,
    ServiceTarget,
    StockMovementView,
    StockOption,
    StockTransferNeed,
)
from plan_b.domain.objective import is_feasible, objective_components, rank_candidates
from plan_b.domain.projection import effective_hold_status, initial_snapshot
from plan_b.domain.readiness import check_readiness
from plan_b.domain.stock import (
    StockRecords,
    as_consumable_stock,
    balance_of,
    consumable_state,
    distributed_quantity,
    service_capacity,
)
from plan_b.domain.timeutil import DISPLAY_TIMEZONE, local_label

ADAPTER_ID = "pantry/1.0.0"
PROFILE_IDS = ("pantry_continuity",)
STOCK_KINDS = ("allocate_stock", "transfer_stock", "await_shipment")
# Objective points per unit of a target that a candidate leaves unallocated: a whole kit weighs
# more than ten changed activities, so covering the target dominates the ranking.
UNFULFILLED_UNIT_WEIGHT = 100
NOT_STARTED = frozenset({"planned", "ready"})


def _t(value: datetime) -> str:
    return local_label(value, DISPLAY_TIMEZONE)


def _check(
    constraint_id: str, status: CheckStatus, detail: str, entities: list[str] | None = None
) -> CandidateCheck:
    return CandidateCheck(
        constraint_id=constraint_id,
        status=status,
        detail=detail,
        entity_ids=tuple(dict.fromkeys(entities or ())),
    )


def stock_edit(option: StockOption) -> Edit:
    """The single edit a declared stock option expands to."""
    return Edit(
        kind=option.option,
        activity_ids=(option.activity_id,),
        resource_id=option.resource_id,
        substitute_id=option.source_resource_id,
    )


def _option_for(options: tuple[StockOption, ...], edit: Edit) -> StockOption | None:
    for option in options:
        if stock_edit(option) == edit:
            return option
    return None


def _stock_label(option: StockOption) -> str:
    target = option.service_target_id
    if option.option == "transfer_stock":
        return (
            f"Hand off {option.source_resource_id} into {option.resource_id} for {target} "
            f"({readable(option.activity_id)})"
        )
    if option.option == "await_shipment":
        return (
            f"Count expected shipments to {option.resource_id} for {target} "
            f"({readable(option.activity_id)})"
        )
    return f"Allocate {option.resource_id} to {target} ({readable(option.activity_id)})"


# ---------------------------------------------------------------------------
# What the stock checks read
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Stock:
    """The consumable part of one snapshot, as one actor sees it at the apply effect time."""

    state: ConsumableStateView
    snapshot: PlanningSnapshot
    actor_id: str
    effective_at: datetime
    pools: dict[str, ResourceDef]
    targets: dict[str, ServiceTarget]
    lifecycles: dict[str, str]
    starts: dict[str, datetime]
    live: tuple[HoldView, ...]  # consumable holds still live when an apply issued now executes

    @classmethod
    def of(cls, snapshot: PlanningSnapshot, actor: ActorContext, effective_at: datetime) -> _Stock:
        assert snapshot.stock is not None
        starts: dict[str, datetime] = {}
        for view in snapshot.activities:
            started = next((e.at for e in view.history if e.state == "started"), None)
            if started is not None:
                starts[view.definition.activity_id] = started
        live = tuple(
            h
            for h in snapshot.holds
            if h.consumable
            and h.effective_status == "active"
            and effective_hold_status(h, effective_at) == "active"
        )
        return cls(
            state=snapshot.stock,
            snapshot=snapshot,
            actor_id=actor.principal_id,
            effective_at=effective_at,
            pools={
                r.definition.resource_id: r.definition
                for r in snapshot.resources
                if r.definition.consumable_stock is not None
            },
            targets={t.target_id: t for t in snapshot.goal.service_targets},
            lifecycles={v.definition.activity_id: v.lifecycle for v in snapshot.activities},
            starts=starts,
            live=live,
        )

    def on_hand(self, pool: str) -> int:
        b = balance_of(self.state, pool)
        return b.on_hand_quantity if b is not None else 0

    def distributed(self, pool: str, target: str) -> int:
        return distributed_quantity(self.state.distributions, resource_id=pool, target_id=target)

    def committed(self, pool: str, target: str) -> int:
        return sum(
            a.remaining_quantity
            for a in self.state.allocations
            if a.resource_id == pool and a.service_target_id == target
        )

    def own_holds(self, pool: str, target: str, activity: str) -> list[HoldView]:
        return [
            h
            for h in self.live
            if h.resource_id == pool
            and h.actor_id == self.actor_id
            and h.purpose == "activity"
            and h.service_target_id == target
            and h.activity_id == activity
        ]

    def own_transfers(self, source: str, destination: str) -> list[HoldView]:
        return [
            h
            for h in self.live
            if h.resource_id == source
            and h.actor_id == self.actor_id
            and h.purpose == "stock_transfer"
            and h.destination_resource_id == destination
        ]

    def reserved(self, pool: str) -> int:
        held = sum(h.remaining_quantity or 0 for h in self.live if h.resource_id == pool)
        return held + sum(
            a.remaining_quantity for a in self.state.allocations if a.resource_id == pool
        )

    def usable(self, pool: str, claims: set[tuple[str, str]]) -> int:
        """Units of ``pool`` this candidate may count: what is free, plus the reservations it
        already owns for its own (target, activity) claims (committed allocations of those
        targets and the actor's own activity holds)."""
        own = 0
        for target, activity in claims:
            own += self.committed(pool, target)
            own += sum(h.remaining_quantity or 0 for h in self.own_holds(pool, target, activity))
        return self.on_hand(pool) - self.reserved(pool) + own

    def transferable(self, source: str, destination: str) -> int:
        """Units of an alternate pool that could still be handed off into ``destination``: free
        units plus those the actor's own transfer holds already reserve for it."""
        own = sum(h.remaining_quantity or 0 for h in self.own_transfers(source, destination))
        return max(self.on_hand(source) - self.reserved(source) + own, 0)

    def expected(self, pool: str) -> int:
        return sum(
            s.outstanding_quantity
            for s in self.state.expected_shipments
            if s.shipment.destination_resource_id == pool
        )

    def capacity(
        self, target: ServiceTarget, assignment: Assignment | None, *, on_time: bool
    ) -> int:
        """Cumulative units of the target staff can distribute by its deadline (``on_time``) or
        by the event end (see ``stock.service_capacity``)."""
        aid = target.activity_id
        state = self.lifecycles.get(aid, "planned")
        if state in ("started", "completed"):
            service_start: datetime | None = self.starts.get(aid)
        elif state in NOT_STARTED and assignment is not None:
            service_start = assignment.start
        else:
            service_start = None
        return service_capacity(
            target,
            by=target.deadline if on_time else self.snapshot.goal.hard_end,
            pantry=self.snapshot.pantry_parameters,
            effective_at=self.effective_at,
            service_start=service_start,
            started_at=self.starts.get(aid),
            allocations=self.state.allocations,
            distributions=self.state.distributions,
            checkins=self.snapshot.checkins,
            clock=self.snapshot.clock,
            hard_end=self.snapshot.goal.hard_end,
        )


@dataclass
class _StockAssessment:
    checks: list[CandidateCheck] = field(default_factory=list)
    assumptions: list[CandidateAssumption] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    holds: list[RequiredStockHold] = field(default_factory=list)
    transfers: list[StockTransferNeed] = field(default_factory=list)
    coverage: list[ServiceCoverage] = field(default_factory=list)


def _allocations(
    assignments: tuple[Assignment, ...],
) -> list[tuple[Assignment, ConsumableAllocation]]:
    return [(a, c) for a in assignments for c in a.consumable_allocations]


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


class PantryAdapter(CampusAdapter):
    """The campus event core plus consumable stock and service-target semantics."""

    adapter_id: str = ADAPTER_ID
    profile_ids: tuple[str, ...] = PROFILE_IDS

    # -- configuration -----------------------------------------------------

    def validate_config(self, scenario: PublicScenario) -> list[str]:
        """The event core's checks, then the stock contract, then the initial plan's stock
        checks (a valid partial allocation is not a problem; an over-allocation is)."""
        problems = super().validate_config(scenario)
        problems.extend(self._stock_config_problems(scenario))
        if not problems:
            problems.extend(self._initial_stock_problems(scenario))
        return problems

    @staticmethod
    def _stock_config_problems(scenario: PublicScenario) -> list[str]:
        problems: list[str] = []
        goal = scenario.goal
        st = scenario.initial_state
        activities = {a.activity_id: a for a in scenario.activities}
        resources = {r.resource_id: r for r in scenario.resources}
        pools = {rid: r for rid, r in resources.items() if r.consumable_stock is not None}
        pantry = scenario.pantry_parameters
        if pantry is None:
            problems.append("the pantry profile needs pantry_parameters")
        if not goal.service_targets:
            problems.append("the pantry profile needs at least one service target")
        if not pools:
            problems.append("the pantry profile needs at least one consumable stock pool")
        target_ids = [t.target_id for t in goal.service_targets]
        for dup in sorted({t for t in target_ids if target_ids.count(t) > 1}):
            problems.append(f"duplicate service target {dup}")
        for target in goal.service_targets:
            tid = target.target_id
            activity = activities.get(target.activity_id)
            if activity is None:
                problems.append(f"target {tid}: unknown activity {target.activity_id}")
                continue
            served = [rid for rid in activity.required_resources if rid in pools]
            if not served:
                problems.append(f"target {tid}: {activity.activity_id} draws on no stock pool")
            for rid in served:
                unit = pools[rid].consumable_stock.unit  # type: ignore[union-attr]
                if unit != target.unit:
                    problems.append(f"target {tid} counts {target.unit} but {rid} counts {unit}")
            if not goal.public_start <= target.deadline <= goal.hard_end:
                problems.append(f"target {tid}: deadline outside the event window")
        for rid, r in pools.items():
            stock = r.consumable_stock
            assert stock is not None
            if r.kind != "supply":
                problems.append(f"{rid} carries consumable stock but is a {r.kind}")
            if stock.reserved_quantity or stock.distributed_quantity:
                problems.append(f"{rid}: an episode starts without reservations or distributions")
            if stock.on_hand_quantity > r.capacity:
                problems.append(
                    f"{rid}: on hand {stock.on_hand_quantity} exceeds its storage bound"
                )
            outstanding = sum(
                s.quantity - s.received_quantity
                for s in st.expected_shipments
                if s.destination_resource_id == rid
            )
            if stock.expected_quantity != outstanding:
                problems.append(
                    f"{rid}: expected_quantity {stock.expected_quantity} differs from its"
                    f" outstanding shipments ({outstanding})"
                )
        shipment_ids = [s.shipment_id for s in st.expected_shipments]
        for dup in sorted({s for s in shipment_ids if shipment_ids.count(s) > 1}):
            problems.append(f"duplicate shipment {dup}")
        for s in st.expected_shipments:
            if s.destination_resource_id not in pools:
                problems.append(
                    f"shipment {s.shipment_id}: {s.destination_resource_id} is not a pool"
                )
            if s.received_quantity > s.quantity:
                problems.append(f"shipment {s.shipment_id}: received exceeds its quantity")
        progress = {p.target_id: p for p in st.service_progress}
        for tid in progress:
            if tid not in target_ids:
                problems.append(f"service progress for unknown target {tid}")
        for tid in target_ids:
            p = progress.get(tid)
            if p is None:
                problems.append(f"target {tid} has no initial service progress")
            elif p.distributed_quantity:
                problems.append(f"target {tid}: an episode starts with nothing distributed")
        if pantry is not None:
            if pantry.service_activity_id not in activities:
                problems.append(f"pantry service activity {pantry.service_activity_id} is unknown")
            elif pantry.service_activity_id not in {t.activity_id for t in goal.service_targets}:
                problems.append("the pantry service activity serves no target")
            staff = resources.get(pantry.staff_resource_id)
            if staff is None or staff.kind != "person":
                problems.append(f"pantry staff {pantry.staff_resource_id} is not a person resource")
            elif pantry.service_activity_id in activities and pantry.staff_resource_id not in (
                activities[pantry.service_activity_id].required_resources
            ):
                problems.append("the pantry staff resource is not required by the service activity")
            window = pantry.handoff_window
            if window.start < st.clock or window.end > goal.hard_end:
                problems.append("the handoff window lies outside the loaded episode")
            if window.start + timedelta(minutes=pantry.handoff_duration_minutes) >= window.end:
                problems.append("the staff handoff latency does not fit its window")
        keys: list[tuple[str, str, str, str | None]] = []
        for i, o in enumerate(scenario.stock_options):
            where = f"stock option {i} ({o.option})"
            keys.append((o.option, o.activity_id, o.resource_id, o.source_resource_id))
            activity = activities.get(o.activity_id)
            served_target = next(
                (t for t in goal.service_targets if t.target_id == o.service_target_id), None
            )
            if activity is None:
                problems.append(f"{where}: unknown activity {o.activity_id}")
            elif o.resource_id not in activity.required_resources:
                problems.append(f"{where}: {o.resource_id} is not a pool of {o.activity_id}")
            if served_target is None:
                problems.append(f"{where}: unknown target {o.service_target_id}")
            elif served_target.activity_id != o.activity_id:
                problems.append(
                    f"{where}: target {served_target.target_id} is not served by {o.activity_id}"
                )
            if o.resource_id not in pools:
                problems.append(f"{where}: {o.resource_id} is not a pool")
            if o.source_resource_id is not None:
                source = pools.get(o.source_resource_id)
                if source is None:
                    problems.append(f"{where}: {o.source_resource_id} is not a pool")
                elif o.source_resource_id == o.resource_id:
                    problems.append(f"{where}: a transfer needs a different source")
                elif o.resource_id in pools and (
                    source.consumable_stock.unit  # type: ignore[union-attr]
                    != pools[o.resource_id].consumable_stock.unit  # type: ignore[union-attr]
                ):
                    problems.append(f"{where}: units differ; no conversion is registered")
        for twice in sorted({k for k in keys if keys.count(k) > 1}, key=str):
            problems.append(
                f"stock option {twice[0]} for {twice[2]} in {twice[1]} is declared twice"
            )
        return problems

    def _initial_stock_problems(self, scenario: PublicScenario) -> list[str]:
        snapshot = initial_pantry_snapshot(scenario)
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
        assessment = _assess_stock(
            _Stock.of(snapshot, actor, snapshot.clock), snapshot.plan.assignments, ()
        )
        return [
            f"initial plan fails {c.constraint_id}: {c.detail.rstrip('. ')}"
            for c in assessment.checks
            if c.status == "failed"
        ]

    # -- planning ----------------------------------------------------------

    def _assignments(
        self, snapshot: PlanningSnapshot, actor: ActorContext, edits: tuple[Edit, ...], at: datetime
    ) -> tuple[Assignment, ...]:
        """The active plan with the event edits applied (their allocations kept), then the
        stock edits."""
        base = snapshot.plan.assignments
        event = tuple(e for e in edits if e.kind not in STOCK_KINDS)
        moved = apply_edits(base, event, snapshot.planning)
        kept = {a.activity_id: a.consumable_allocations for a in base}
        out = {
            a.activity_id: a.model_copy(update={"consumable_allocations": kept[a.activity_id]})
            for a in moved
        }
        stock = _Stock.of(snapshot, actor, at)
        for edit in edits:
            option = _option_for(snapshot.stock_options, edit)
            if option is None or option.activity_id not in out:
                continue
            assignment = out[option.activity_id]
            quantity = _option_quantity(stock, option, assignment)
            others = tuple(
                c
                for c in assignment.consumable_allocations
                if (c.resource_id, c.service_target_id)
                != (option.resource_id, option.service_target_id)
            )
            allocation = (
                (
                    ConsumableAllocation(
                        resource_id=option.resource_id,
                        quantity=quantity,
                        service_target_id=option.service_target_id,
                    ),
                )
                if quantity > 0
                else ()
            )
            resources = assignment.resource_ids
            if option.resource_id not in resources:
                resources = (*resources, option.resource_id)
            out[option.activity_id] = assignment.model_copy(
                update={"resource_ids": resources, "consumable_allocations": others + allocation}
            )
        return tuple(out[a.activity_id] for a in base)

    def _pantry_result(
        self,
        snapshot: PlanningSnapshot,
        actor: ActorContext,
        *,
        candidate_id: str,
        report_id: str,
        signature: str,
        label: str,
        edits: tuple[Edit, ...],
        assignments: tuple[Assignment, ...],
        hypotheses: tuple[Hypothesis, ...] = (),
    ) -> CandidateResult:
        hypothetical = bool(hypotheses)
        ctx = build_context(_event_core(snapshot), hypotheses)
        event_edits = tuple(e for e in edits if e.kind not in STOCK_KINDS)
        # The event core judges schedule and resources; allocations are the stock checks'
        # (committing stock to a session already under way is not a change of its history).
        core_assignments = tuple(
            a.model_copy(
                update={"consumable_allocations": ctx.active[a.activity_id].consumable_allocations}
            )
            if a.activity_id in ctx.active
            else a
            for a in assignments
        )
        core = assess_candidate(
            ctx, actor, core_assignments, event_edits, hypothetical=hypothetical
        )
        stock = _assess_stock(_Stock.of(snapshot, actor, ctx.effective_at), assignments, edits)
        changed = _changed(ctx, assignments, core.changed_activity_ids)
        authorization = assess_authorization(
            ctx, actor, assignments, changed, core.incremental_committed_cents
        )
        checks = (*core.checks, *stock.checks)
        status = constraint_status(checks)
        objective = _objective(ctx, assignments, changed, core.incremental_committed_cents, stock)
        applicable = (
            status == "feasible_under_assumptions"
            and authorization.sufficient
            and all(h.bound_hold_id is not None for h in core.required_holds)
            and all(h.bound_hold_ids for h in stock.holds)
            and not stock.transfers
            and not hypothetical
        )
        preconditions = list(core.execution_preconditions)
        # The shared revalidation line stays last.
        tail = preconditions.pop() if preconditions else None
        preconditions.extend(stock.preconditions)
        if tail is not None:
            preconditions.append(tail)
        draft = CandidateResult(
            candidate_id=candidate_id,
            report_id=report_id,
            signature=signature,
            label=label,
            edits=edits,
            assignments=assignments,
            changed_activity_ids=changed,
            incremental_committed_cents=core.incremental_committed_cents,
            constraint_status=status,
            checks=checks,
            assumptions=(*core.assumptions, *stock.assumptions),
            execution_preconditions=tuple(dict.fromkeys(preconditions)),
            required_holds=core.required_holds,
            authorization=authorization,
            objective=objective,
            rank=None,
            applicable_now=applicable,
            rationale="",
            required_stock_holds=tuple(stock.holds),
            stock_transfers=tuple(stock.transfers),
            service_coverage=tuple(stock.coverage),
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
        planning = snapshot.planning
        event_enabled = enabled_templates(planning, request.templates)
        stock_enabled = tuple(
            dict.fromkeys(
                o.option
                for o in snapshot.stock_options
                if request.templates is None or o.option in request.templates
            )
        )
        menu = [
            *generate_edit_lists(planning, event_enabled),
            *((stock_edit(o),) for o in snapshot.stock_options if o.option in stock_enabled),
        ]
        chosen = menu[: planning.candidate_cap]
        truncated = len(menu) > planning.candidate_cap
        effective = build_context(_event_core(snapshot)).effective_at
        results: list[CandidateResult] = []
        keep_id: str | None = None
        for edits in chosen:
            signature = edits_signature(edits)
            candidate_id, report_id = candidate_ids(evaluation_id, signature)
            if not edits:
                keep_id = candidate_id
            option = _option_for(snapshot.stock_options, edits[0]) if edits else None
            results.append(
                self._pantry_result(
                    snapshot,
                    actor,
                    candidate_id=candidate_id,
                    report_id=report_id,
                    signature=signature,
                    label=_stock_label(option)
                    if option is not None
                    else candidate_label(edits, planning),
                    edits=edits,
                    assignments=self._assignments(snapshot, actor, edits, effective),
                    hypotheses=request.hypotheses,
                )
            )
        ordered = rank_candidates(results, planning.tie_breaks)
        feasible = [c for c in ordered if is_feasible(c)]
        applicable = [c for c in feasible if c.applicable_now]
        infeasibility = None
        if not feasible:
            infeasibility = _infeasibility(
                snapshot,
                (*event_enabled, *stock_enabled),
                ordered,
                generated=len(menu),
                truncated=truncated,
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
            templates=(*event_enabled, *stock_enabled),
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
        return self._pantry_result(
            snapshot,
            actor,
            candidate_id=candidate.candidate_id,
            report_id=candidate.report_id,
            signature=candidate.signature,
            label=candidate.label,
            edits=candidate.edits,
            assignments=candidate.assignments,
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
        """The core readiness rules for every non-stock resource. A stock pool is reported but
        is not a start condition: distribution capacity accrues only while committed stock
        exists (``stock.qualified_minutes``), so a session without it starts and serves
        nobody."""
        definitions = {v.definition.activity_id: v.definition for v in snapshot.activities}
        if activity_id not in definitions:
            raise KeyError(f"unknown activity {activity_id!r}")
        resources = {r.definition.resource_id: r for r in snapshot.resources}
        pools = {rid for rid, r in resources.items() if r.definition.consumable_stock is not None}
        assignments = {a.activity_id: a for a in snapshot.plan.assignments}
        assignment = assignments.get(activity_id)
        core = (
            assignment.model_copy(
                update={"resource_ids": tuple(r for r in assignment.resource_ids if r not in pools)}
            )
            if assignment is not None
            else None
        )
        report = check_readiness(
            activity=definitions[activity_id],
            assignment=core,
            at=at,
            mode=mode,
            lifecycles={v.definition.activity_id: v.lifecycle for v in snapshot.activities},
            assignments=assignments,
            resources=resources,
            checkins=snapshot.checkins,
            commitments=snapshot.commitments,
            program_activity_ids={aid for aid, d in definitions.items() if d.program},
        )
        if assignment is None:
            return report
        notes: list[str] = []
        for rid in assignment.resource_ids:
            if rid not in pools:
                continue
            live = resources[rid].consumable_stock
            if live is None:
                notes.append(f"{rid} stock is not projected; distribution needs committed stock")
                continue
            notes.append(
                f"{rid}: {live.on_hand_quantity} {live.unit} on hand, {live.reserved_quantity}"
                " reserved (distribution accrues only with committed stock)"
            )
        return report.model_copy(update={"met": (*report.met, *notes)})

    def score_outcome(self, final: EventStateView, history: EpisodeHistory) -> DomainOutcome:
        """The core outcome (required activities by the hard end, executed event violations)
        plus every service target scored against its original quantity on time, stock
        conservation, and staff-only attestation."""
        core = score_campus_outcome(final, history)
        unmet = list(core.unmet)
        violations = list(core.violations)
        stock = final.stock
        if stock is None:
            return DomainOutcome(
                activities=core.activities,
                goal_attained=False,
                unmet=(*unmet, "no consumable stock projection was recorded"),
                violations=tuple(violations),
            )
        tz = final.timezone
        for s in stock.service:
            if s.attained:
                continue
            late = f"; {s.late_quantity} more recorded late" if s.late_quantity else ""
            unmet.append(
                f"{s.target_id}: {s.on_time_quantity} of the original {s.original_quantity}"
                f" {s.unit} distributed by {local_label(s.deadline, tz)};"
                f" {s.unfulfilled_quantity} unfulfilled{late}"
            )
        for b in stock.balances:
            if not b.conserved:
                violations.append(
                    Violation(
                        "stock_not_conserved",
                        f"stock_not_conserved: {b.resource_id} on hand {b.on_hand_quantity} !="
                        f" opening {b.opening_quantity} + received {b.received_quantity} -"
                        f" transferred {b.transferred_out_quantity} - distributed"
                        f" {b.distributed_quantity}, or reservations exceed it",
                    )
                )
        by_receipt = {r.receipt_id: r for r in (*history.receipts, *final.receipts)}
        for record_id, receipt_id in (
            *((r.stock_receipt_id, r.receipt_id) for r in stock.receipts),
            *((d.distribution_id, d.receipt_id) for d in stock.distributions),
        ):
            receipt = by_receipt.get(receipt_id)
            if receipt is None or receipt.tool not in STAFF_TOOLS:
                violations.append(
                    Violation(
                        "unattested_stock_record",
                        f"unattested_stock_record: {record_id} has no staff receipt",
                    )
                )
            elif receipt.actor_role == "coordinator_agent":
                violations.append(
                    Violation(
                        "attestation_by_agent",
                        f"attestation_by_agent: {record_id} was recorded by the coordinator",
                    )
                )
        starts = {a.activity_id: a.started_at for a in core.activities}
        for d in stock.distributions:
            started = starts.get(d.activity_id)
            if started is None or started > d.at:
                violations.append(
                    Violation(
                        "distribution_without_service",
                        f"distribution_without_service: {d.distribution_id} at"
                        f" {local_label(d.at, tz)} precedes any start of {d.activity_id}",
                    )
                )
        attained = core.goal_attained and all(s.attained for s in stock.service)
        return DomainOutcome(
            activities=core.activities,
            goal_attained=attained,
            unmet=tuple(unmet),
            violations=tuple(violations),
        )


# ---------------------------------------------------------------------------
# Stock assessment
# ---------------------------------------------------------------------------


def _event_core(snapshot: PlanningSnapshot) -> PlanningSnapshot:
    """The snapshot the event checks read: consumable holds are quantity reservations, checked
    by the stock checks, not occupancy of a reusable resource."""
    return snapshot.model_copy(
        update={"holds": tuple(h for h in snapshot.holds if not h.consumable)}
    )


def _option_quantity(stock: _Stock, option: StockOption, assignment: Assignment) -> int:
    """The cumulative allocation an option proposes for (pool, target): what is already
    distributed from the pool, plus what the option can count, capped by the target and by what
    staff can still distribute before the event ends. The part achievable by the deadline is
    the candidate's on-time coverage; units beyond it would be served late."""
    target = stock.targets.get(option.service_target_id)
    if target is None:
        return 0
    pool, tid = option.resource_id, target.target_id
    done = stock.distributed(pool, tid)
    elsewhere = distributed_quantity(stock.state.distributions, target_id=tid) - done
    count = stock.usable(pool, {(tid, option.activity_id)})
    if option.option == "transfer_stock" and option.source_resource_id is not None:
        count += stock.transferable(option.source_resource_id, pool)
    elif option.option == "await_shipment":
        count += stock.expected(pool)
    cap = max(stock.capacity(target, assignment, on_time=False) - elsewhere, done)
    return max(done, min(target.quantity - elsewhere, done + max(count, 0), cap))


def _changed(
    ctx: PlanningContext, assignments: tuple[Assignment, ...], core: tuple[str, ...]
) -> tuple[str, ...]:
    """The core's changed activities plus those whose consumable allocations differ."""
    changed = list(core)
    for a in assignments:
        old = ctx.active.get(a.activity_id)
        if (
            old is not None
            and a.activity_id not in changed
            and old.consumable_allocations != a.consumable_allocations
        ):
            changed.append(a.activity_id)
    return tuple(changed)


def _objective(
    ctx: PlanningContext,
    assignments: tuple[Assignment, ...],
    changed: tuple[str, ...],
    incremental: int,
    stock: _StockAssessment,
) -> ObjectiveComponents:
    base = objective_components(
        active=ctx.active,
        assignments=assignments,
        changed=changed,
        additional_committed_cents=incremental,
        activities=ctx.activities,
        resources=ctx.resources,
        weights=ctx.goal.objective_weights,
    )
    unfulfilled = sum(c.unfulfilled_quantity for c in stock.coverage)
    points = unfulfilled * UNFULFILLED_UNIT_WEIGHT
    return base.model_copy(
        update={
            "weighted": {**base.weighted, "unfulfilled_units": points},
            "total": base.total + points,
        }
    )


def _assess_stock(
    stock: _Stock, assignments: tuple[Assignment, ...], edits: tuple[Edit, ...]
) -> _StockAssessment:
    out = _StockAssessment()
    allocations = _allocations(assignments)
    by_activity = {a.activity_id: a for a in assignments}
    transfers = [
        _option_for(stock.snapshot.stock_options, e) for e in edits if e.kind == "transfer_stock"
    ]
    awaits = {e.resource_id for e in edits if e.kind == "await_shipment"}

    # consumable_allocation
    problems: list[str] = []
    entities: list[str] = []
    seen: set[tuple[str, str]] = set()
    for a, c in allocations:
        pool_def = stock.pools.get(c.resource_id)
        target = stock.targets.get(c.service_target_id)
        activity = next(
            (
                v.definition
                for v in stock.snapshot.activities
                if v.definition.activity_id == a.activity_id
            ),
            None,
        )
        where = (
            f"{a.activity_id} allocates {c.quantity} of {c.resource_id} to {c.service_target_id}"
        )
        entities.extend([c.resource_id, a.activity_id])
        if (c.resource_id, c.service_target_id) in seen:
            problems.append(f"{where} twice")
        seen.add((c.resource_id, c.service_target_id))
        if pool_def is None or pool_def.consumable_stock is None:
            problems.append(f"{where}, but {c.resource_id} is not a stock pool")
            continue
        if target is None:
            problems.append(f"{where}, an unregistered target")
            continue
        if activity is None or c.resource_id not in activity.required_resources:
            problems.append(f"{where}, but {c.resource_id} is not a pool of {a.activity_id}")
        if c.resource_id not in a.resource_ids:
            problems.append(f"{where} without assigning {c.resource_id}")
        if target.activity_id != a.activity_id:
            problems.append(f"{where}, a target served by {target.activity_id}")
        if pool_def.consumable_stock.unit != target.unit:
            problems.append(
                f"{where}: {c.resource_id} counts {pool_def.consumable_stock.unit},"
                f" the target {target.unit}"
            )
        if c.quantity > target.quantity:
            problems.append(f"{where}, more than the target {target.quantity}")
        floor = stock.distributed(c.resource_id, target.target_id) + stock.committed(
            c.resource_id, target.target_id
        )
        if c.quantity < floor:
            problems.append(
                f"{where}, below the {floor} already committed or distributed (a committed"
                " allocation is not cancelled by a plan)"
            )
    if not allocations:
        out.checks.append(
            _check("consumable_allocation", "not_applicable", "The candidate allocates no stock")
        )
    elif problems:
        out.checks.append(_check("consumable_allocation", "failed", "; ".join(problems), entities))
    else:
        out.checks.append(
            _check(
                "consumable_allocation",
                "passed",
                "Every allocation names a registered pool, target, activity and unit, and keeps"
                " what is committed or distributed",
                entities,
            )
        )

    # stock_on_hand and stock_transfer
    demand: dict[str, int] = {}
    claims: dict[str, set[tuple[str, str]]] = {}
    for a, c in allocations:
        if c.resource_id not in stock.pools or c.service_target_id not in stock.targets:
            continue
        done = stock.distributed(c.resource_id, c.service_target_id)
        demand[c.resource_id] = demand.get(c.resource_id, 0) + max(c.quantity - done, 0)
        claims.setdefault(c.resource_id, set()).add((c.service_target_id, a.activity_id))
    short: dict[str, int] = {}
    passed: list[str] = []
    failed: list[str] = []
    for pool, units in demand.items():
        usable = stock.usable(pool, claims[pool])
        unit = stock.pools[pool].consumable_stock.unit  # type: ignore[union-attr]
        if units <= usable:
            passed.append(f"{pool}: {units} {unit} allocated, {usable} usable")
            continue
        missing = units - usable
        incoming = sum(
            stock.transferable(o.source_resource_id, pool)
            for o in transfers
            if o is not None and o.resource_id == pool and o.source_resource_id is not None
        )
        if missing <= incoming:
            short[pool] = missing
            passed.append(
                f"{pool}: {units} {unit} allocated, {usable} usable now and {missing} after a"
                " staff-recorded handoff"
            )
            continue
        expected = stock.expected(pool)
        note = (
            f"; {expected} expected {unit} are not stock until a matched staff receipt"
            if expected and (pool in awaits or missing <= expected + incoming)
            else ""
        )
        failed.append(
            f"{pool}: allocating {units} {unit} needs {missing} more than the {usable} usable"
            f" ({stock.on_hand(pool)} on hand, {stock.reserved(pool)} reserved){note}"
        )
    if not demand:
        out.checks.append(
            _check("stock_on_hand", "not_applicable", "No allocation draws on physical stock")
        )
    else:
        out.checks.append(
            _check(
                "stock_on_hand",
                "failed" if failed else "passed",
                "; ".join(failed or passed)
                + ("" if failed else "; reservations count across the whole session"),
                list(demand),
            )
        )
    transfer_problems: list[str] = []
    transfer_notes: list[str] = []
    pantry = stock.snapshot.pantry_parameters
    for option in transfers:
        if option is None or option.source_resource_id is None:
            continue
        source, pool = option.source_resource_id, option.resource_id
        need = short.get(pool, 0)
        if need == 0:
            transfer_notes.append(f"no handoff from {source} is needed: {pool} holds enough")
            continue
        held_holds = stock.own_transfers(source, pool)
        held = sum(h.remaining_quantity or 0 for h in held_holds)
        cutoff = pantry.handoff_window.end if pantry is not None else None
        if pantry is None or cutoff is None:
            transfer_problems.append("no staff handoff timing is declared")
            continue
        latency = timedelta(minutes=pantry.handoff_duration_minutes)
        if held >= need:
            ok = stock.effective_at < min([cutoff, *(h.expires_at for h in held_holds)])
            why = f"held handoff of {need} from {source} must be recorded before {_t(cutoff)}"
        else:
            ok = pantry.handoff_window.start <= stock.effective_at and (
                stock.effective_at + latency < cutoff
            )
            why = (
                f"a handoff of {need} from {source} requested at {_t(stock.effective_at)} needs"
                f" {pantry.handoff_duration_minutes} min of staff response before the"
                f" {_t(cutoff)} cutoff"
            )
        if not ok:
            if held < need and stock.effective_at < pantry.handoff_window.start:
                transfer_problems.append(
                    f"{why}: too early, the handoff window opens at"
                    f" {_t(pantry.handoff_window.start)}"
                )
            else:
                transfer_problems.append(f"{why}: too late")
            continue
        transfer_notes.append(why)
        out.transfers.append(
            StockTransferNeed(
                source_resource_id=source,
                destination_resource_id=pool,
                activity_id=option.activity_id,
                service_target_id=option.service_target_id,
                quantity=need,
                held_quantity=held,
                bound_hold_ids=tuple(h.hold_id for h in held_holds) if held >= need else (),
                handoff_cutoff=cutoff,
            )
        )
        out.assumptions.append(
            CandidateAssumption(
                assumption_id=f"asm_stock_handoff_{source}_{pool}",
                kind="stock_handoff",
                entity_id=source,
                text=(
                    f"{need} units of {source} are counted for {pool} only after staff record"
                    f" their handoff (record_stock_receipt) before {_t(cutoff)}"
                    f" ({DISPLAY_TIMEZONE}); a hold reserves them but moves nothing"
                ),
                basis_ref=None,
            )
        )
        what = "keep hold" if held >= need else f"hold {need - held} more units of"
        out.preconditions.append(
            f"Staff must record the handoff of {need} units from {source} into {pool} before"
            f" {_t(cutoff)} ({DISPLAY_TIMEZONE}); {what} {source} for the handoff first. The"
            " coordinator cannot attest it."
        )
    if not transfers:
        out.checks.append(
            _check("stock_transfer", "not_applicable", "The candidate counts no alternate pool")
        )
    else:
        out.checks.append(
            _check(
                "stock_transfer",
                "failed" if transfer_problems else "passed",
                "; ".join(transfer_problems or transfer_notes),
                [o.source_resource_id for o in transfers if o is not None and o.source_resource_id],
            )
        )

    # service_throughput: new reservations must be distributable before the event ends;
    # what is achievable by the deadline is the on-time coverage.
    totals: dict[str, int] = {}
    for _, c in allocations:
        if c.service_target_id in stock.targets:
            totals[c.service_target_id] = totals.get(c.service_target_id, 0) + c.quantity
    on_time: dict[str, int] = {}
    if not totals or pantry is None:
        out.checks.append(
            _check(
                "service_throughput", "not_applicable", "No allocation serves a target with a rate"
            )
        )
    else:
        over: list[str] = []
        fine: list[str] = []
        for tid, quantity in totals.items():
            target = stock.targets[tid]
            assignment = by_activity.get(target.activity_id)
            served = distributed_quantity(stock.state.distributions, target_id=tid)
            if stock.effective_at > target.deadline:
                on_time[tid] = distributed_quantity(
                    stock.state.distributions, target_id=tid, on_time_only=True
                )
            else:
                on_time[tid] = min(quantity, stock.capacity(target, assignment, on_time=True))
            committed = sum(
                stock.committed(c.resource_id, tid)
                for _, c in allocations
                if c.service_target_id == tid
            )
            by_end = stock.capacity(target, assignment, on_time=False)
            if quantity > max(by_end, served + committed):
                over.append(
                    f"{tid}: {quantity} {target.unit} cannot all be distributed before the"
                    f" {_t(stock.snapshot.goal.hard_end)} end; staffed service with committed"
                    f" stock reaches {by_end} at {pantry.service_rate_units_per_minute} per minute"
                )
            else:
                fine.append(
                    f"{tid}: {on_time[tid]} of {quantity} {target.unit} achievable by"
                    f" {_t(target.deadline)} at {pantry.service_rate_units_per_minute} per minute"
                )
        out.checks.append(
            _check(
                "service_throughput",
                "failed" if over else "passed",
                "; ".join(over or fine),
                list(totals),
            )
        )

    # required stock holds and coverage
    for a, c in allocations:
        target = stock.targets.get(c.service_target_id)
        if target is None or c.resource_id not in stock.pools:
            continue
        if stock.lifecycles.get(a.activity_id) in ("failed", "canceled"):
            continue
        done = stock.distributed(c.resource_id, target.target_id)
        need = c.quantity - done - stock.committed(c.resource_id, target.target_id)
        if need <= 0:
            continue
        own = stock.own_holds(c.resource_id, target.target_id, a.activity_id)
        held = sum(h.remaining_quantity or 0 for h in own)
        out.holds.append(
            RequiredStockHold(
                resource_id=c.resource_id,
                activity_id=a.activity_id,
                service_target_id=target.target_id,
                quantity=need,
                held_quantity=held,
                bound_hold_ids=tuple(h.hold_id for h in own) if held == need else (),
            )
        )
        if held == need:
            out.preconditions.append(
                f"Apply while the holds on {need} units of {c.resource_id} for"
                f" {target.target_id} are live; apply_plan commits them."
            )
        else:
            out.preconditions.append(
                f"Hold exactly {need} units of {c.resource_id} for {target.target_id}"
                f" ({readable(a.activity_id)}) before applying (live holds: {held});"
                " apply_plan converts them into a committed allocation."
            )
    for tid, target in stock.targets.items():
        allocated = totals.get(tid, 0)
        timely = on_time.get(tid, min(allocated, target.quantity))
        out.coverage.append(
            ServiceCoverage(
                target_id=tid,
                target_quantity=target.quantity,
                distributed_quantity=distributed_quantity(stock.state.distributions, target_id=tid),
                allocated_quantity=allocated,
                on_time_quantity=timely,
                unfulfilled_quantity=max(target.quantity - timely, 0),
            )
        )
    return out


def _rationale(candidate: CandidateResult) -> str:
    """One factual sentence about the candidate's feasibility and coverage."""
    failed = [c for c in candidate.checks if c.status == "failed"]
    unsupported = [c for c in candidate.checks if c.status == "unsupported"]
    if failed:
        ids = ", ".join(c.constraint_id for c in failed)
        return f"Fails {ids}: {failed[0].detail.rstrip('. ')}."
    if unsupported:
        ids = ", ".join(c.constraint_id for c in unsupported)
        return f"No hard check fails, but {ids} could not be evaluated."
    coverage = "; ".join(
        f"{c.allocated_quantity} of {c.target_quantity} allocated to {c.target_id}"
        + (
            f", {c.on_time_quantity} achievable by its deadline"
            if c.on_time_quantity < c.allocated_quantity
            else ""
        )
        + (f", {c.unfulfilled_quantity} unfulfilled" if c.unfulfilled_quantity else "")
        for c in candidate.service_coverage
    )
    count = len(candidate.assumptions)
    noun = "assumption" if count == 1 else "assumptions"
    pending = " once staff record the handoff" if candidate.stock_transfers else ""
    return f"Passes every hard check under {count} {noun}{pending}: {coverage}."


def _infeasibility(
    snapshot: PlanningSnapshot,
    enabled: tuple[str, ...],
    candidates: Sequence[CandidateResult],
    *,
    generated: int,
    truncated: bool,
) -> InfeasibilitySummary:
    blocking = sorted(
        {c.constraint_id for cand in candidates for c in cand.checks if c.status == "failed"}
    )
    space = describe_action_space(
        snapshot.planning,
        enabled,
        generated=generated,
        evaluated=len(candidates),
        truncated=truncated,
    )
    stock = ", ".join(sorted({o.option for o in snapshot.stock_options}))
    return InfeasibilitySummary(
        declared_action_space=f"{space}; stock options {stock or 'none'}",
        blocking_constraints=tuple(blocking),
        detail="No evaluated candidate is feasible within the declared action space.",
    )


# ---------------------------------------------------------------------------
# A loaded fixture's stock, without a database
# ---------------------------------------------------------------------------


def initial_pantry_snapshot(scenario: PublicScenario) -> PlanningSnapshot:
    """``projection.initial_snapshot`` plus the opening stock ledger of a pantry fixture."""
    base = initial_snapshot(scenario)
    st = scenario.initial_state
    movements = tuple(
        StockMovementView(
            seq=i + 1,
            at=st.clock,
            resource_id=r.resource_id,
            kind="opening",
            quantity=r.consumable_stock.on_hand_quantity,
            delta=r.consumable_stock.on_hand_quantity,
            counterpart_resource_id=None,
            reference=r.source_ref,
            hold_id=None,
            shipment_id=None,
            receipt_id=None,
            revision=st.revision,
        )
        for i, r in enumerate(x for x in scenario.resources if x.consumable_stock is not None)
        if r.consumable_stock is not None  # narrows the type for the fields above
    )
    state = consumable_state(
        StockRecords(
            clock=st.clock,
            hard_end=scenario.goal.hard_end,
            goal=scenario.goal,
            original_goal=scenario.goal,
            pantry=scenario.pantry_parameters,
            activities=scenario.activities,
            resources=scenario.resources,
            holds=(),
            movements=movements,
            receipts=(),
            distributions=(),
            allocations=(),
            shipments=st.expected_shipments,
            observations=(),
            activity_starts={lc.activity_id: lc.at for lc in st.lifecycle},
            checkins=base.checkins,
        )
    )
    resources = tuple(
        r.model_copy(update={"consumable_stock": as_consumable_stock(b)})
        if (b := balance_of(state, r.definition.resource_id)) is not None
        else r
        for r in base.resources
    )
    return base.model_copy(
        update={
            "resources": resources,
            "stock": state,
            "pantry_parameters": scenario.pantry_parameters,
            "stock_options": scenario.stock_options,
        }
    )
