"""Pure assembly of visible state from primitive records.

The DB-backed projection (``store/projection_db.py``) loads rows and calls these functions;
``initial_snapshot`` builds the same structures straight from a public fixture so the
planner can be tested without a database. Nothing here can see private runner input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.models import (
    ActivityDef,
    ActivityLifecycleEvent,
    ActivityView,
    Assignment,
    BudgetView,
    CheckInView,
    CommitmentView,
    EventGoal,
    HoldStatus,
    HoldView,
    OccupancyEntry,
    PlanningSnapshot,
    PlanView,
    PublicScenario,
    ResourceDef,
    ResourceStatus,
    ResourceView,
    StatusBasis,
)


@dataclass(frozen=True)
class _ReadinessBasis:
    """The parts of a snapshot that readiness reads, before the snapshot exists."""

    activities: tuple[ActivityView, ...]
    plan: PlanView
    resources: tuple[ResourceView, ...]
    checkins: tuple[CheckInView, ...]
    commitments: tuple[CommitmentView, ...]


def effective_hold_status(hold: HoldView, clock: datetime) -> HoldStatus:
    """A hold is unusable at its expiry boundary: active only while ``clock < expires_at``.

    The engine persists expiry when the clock reaches ``expires_at``; this function makes reads
    correct even if that processing had not happened."""
    if hold.status == "active" and clock >= hold.expires_at:
        return "expired"
    return hold.status


def with_effective_status(holds: tuple[HoldView, ...], clock: datetime) -> tuple[HoldView, ...]:
    return tuple(
        h.model_copy(update={"effective_status": effective_hold_status(h, clock)}) for h in holds
    )


def budget_view(
    goal: EventGoal, holds: tuple[HoldView, ...], commitments: tuple[CommitmentView, ...]
) -> BudgetView:
    committed = sum(c.committed_cents for c in commitments) + sum(h.hold_fee_cents for h in holds)
    reserved = sum(h.reserved_cents for h in holds if h.effective_status == "active")
    return BudgetView(
        budget_cents=goal.budget_cents,
        committed_cents=committed,
        reserved_cents=reserved,
        remaining_cents=goal.budget_cents - committed - reserved,
    )


def occupancy_for(
    resource_id: str,
    plan: PlanView,
    holds: tuple[HoldView, ...],
    commitments: tuple[CommitmentView, ...],
) -> tuple[OccupancyEntry, ...]:
    entries: list[OccupancyEntry] = []
    for a in plan.assignments:
        if resource_id in a.resource_ids:
            entries.append(
                OccupancyEntry(
                    kind="plan",
                    ref=f"plan_v{plan.plan_version}",
                    activity_id=a.activity_id,
                    window=a.window,
                    quantity=1,
                )
            )
    for h in holds:
        if h.resource_id == resource_id and h.effective_status == "active":
            entries.append(
                OccupancyEntry(
                    kind="hold",
                    ref=h.hold_id,
                    activity_id=h.activity_id,
                    window=h.window,
                    quantity=h.quantity,
                )
            )
    for c in commitments:
        if c.resource_id == resource_id and c.status == "active":
            entries.append(
                OccupancyEntry(
                    kind="commitment",
                    ref=c.commitment_id,
                    activity_id=c.activity_id,
                    window=c.window,
                    quantity=1,
                )
            )
    return tuple(entries)


def resource_view(
    definition: ResourceDef,
    *,
    status: ResourceStatus,
    status_basis: StatusBasis,
    status_observation_id: str | None,
    status_observed_at: datetime | None,
    reported_eta: datetime | None,
    plan: PlanView,
    holds: tuple[HoldView, ...],
    commitments: tuple[CommitmentView, ...],
) -> ResourceView:
    return ResourceView(
        definition=definition,
        status=status,
        status_basis=status_basis,
        status_observation_id=status_observation_id,
        status_observed_at=status_observed_at,
        reported_eta=reported_eta,
        occupancy=occupancy_for(definition.resource_id, plan, holds, commitments),
    )


def activity_views(
    *,
    definitions: tuple[ActivityDef, ...],
    lifecycles: dict[str, str],
    history: tuple[ActivityLifecycleEvent, ...],
    plan: PlanView,
    resources: tuple[ResourceView, ...],
    checkins: tuple[CheckInView, ...],
    commitments: tuple[CommitmentView, ...],
    clock: datetime,
    profile_id: str,
) -> tuple[ActivityView, ...]:
    """Activity views; a not-started activity carries the preview readiness that the domain
    adapter of ``profile_id`` (the episode's or fixture's own profile; there is no default)
    reports for it at ``clock``."""
    by_activity = {a.activity_id: a for a in plan.assignments}
    bare = tuple(
        ActivityView(
            definition=d,
            lifecycle=lifecycles[d.activity_id],  # type: ignore[arg-type]
            history=tuple(e for e in history if e.activity_id == d.activity_id),
            assignment=by_activity.get(d.activity_id),
            readiness=None,
        )
        for d in definitions
    )
    adapter = adapter_for(profile_id)
    basis = _ReadinessBasis(
        activities=bare, plan=plan, resources=resources, checkins=checkins, commitments=commitments
    )
    return tuple(
        v.model_copy(
            update={
                "readiness": adapter.check_readiness(
                    basis, v.definition.activity_id, clock, mode="preview"
                )
            }
        )
        if v.lifecycle in ("planned", "ready")
        else v
        for v in bare
    )


def initial_snapshot(scenario: PublicScenario) -> PlanningSnapshot:
    """PlanningSnapshot of a freshly loaded fixture, without a database."""
    st = scenario.initial_state
    plan = PlanView(
        plan_version=1,
        assignments=st.assignments,
        applied_receipt_id=None,
        candidate_id=None,
        applied_at=None,
    )
    holds: tuple[HoldView, ...] = ()
    commitments: tuple[CommitmentView, ...] = ()
    checkins = tuple(
        CheckInView(
            checkin_id=f"chk_fixture_{i + 1:02d}",
            principal_id=c.principal_id,
            resource_id=c.resource_id,
            at=c.at,
            available=c.available,
            observation_id=None,
            channel="fixture_initial",
        )
        for i, c in enumerate(st.checked_in)
    )
    resources = tuple(
        resource_view(
            r,
            status=r.initial_status,
            status_basis="catalog",
            status_observation_id=None,
            status_observed_at=None,
            reported_eta=None,
            plan=plan,
            holds=holds,
            commitments=commitments,
        )
        for r in scenario.resources
    )
    lifecycles = {a.activity_id: "planned" for a in scenario.activities}
    history: list[ActivityLifecycleEvent] = []
    for i, lc in enumerate(st.lifecycle):
        lifecycles[lc.activity_id] = lc.state
        history.append(
            ActivityLifecycleEvent(
                seq=i + 1,
                activity_id=lc.activity_id,
                state=lc.state,
                at=lc.at,
                revision=st.revision,
                reasons=(f"recorded in {lc.source_ref}",),
            )
        )
    activities = activity_views(
        definitions=scenario.activities,
        lifecycles=lifecycles,
        history=tuple(history),
        plan=plan,
        resources=resources,
        checkins=checkins,
        commitments=commitments,
        clock=st.clock,
        profile_id=scenario.profile_id,
    )
    return PlanningSnapshot(
        event_id=scenario.event_id,
        revision=st.revision,
        clock=st.clock,
        goal=scenario.goal,
        planning=scenario.planning,
        activities=activities,
        resources=resources,
        plan=plan,
        holds=holds,
        commitments=commitments,
        checkins=checkins,
        budget=budget_view(scenario.goal, holds, commitments),
    )


def assignments_by_activity(assignments: tuple[Assignment, ...]) -> dict[str, Assignment]:
    return {a.activity_id: a for a in assignments}
