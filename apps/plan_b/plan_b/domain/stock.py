"""Consumable stock and service accounting (runtime 1.1.0). Pure functions only.

The store loads the stock ledgers and hands them over as ``StockRecords``; this module derives
every balance, counter and capacity from them. Nothing here reads a database, the clock of a
running episode or private runner input, so the projection, the planner (``PantryAdapter``),
the executor's stock tools, the staff simulator and the scorer all compute the same numbers.

Stock rules (``PEEAI_plan/15_pantry_showcase.md``):

* ``on_hand`` includes reserved, unconsumed units. Reserved = live hold remainders + the
  undistributed remainder of committed allocations (disjoint parts: ``apply_plan`` moves a
  hold's remainder into an allocation and leaves the hold with none). Available = on hand -
  reserved. A reservation applies across the remaining session, so two activities, however far
  apart in time, cannot claim the same units.
* For every pool, ``closing_on_hand = opening + receipts - transfers_out - distributions``.
  Expected units are never part of that equation before a matched receipt.
* Two counters stay separate. Supply gap = ``max(target - distributed - pantry-controlled on
  hand, 0)``: after distribution begins, it is measured against the remaining target, so
  consumed stock does not create a new shortage. Unfulfilled = ``original target - distributed
  on time``: holds, plan commitments and receipts never change it.
* Service capacity accrues one qualified minute at a time: after the service activity actually
  started, while the staff resource's latest check-in covers the minute, while committed
  allocations for the target still hold undistributed units, and before the event's hard end.
  Capacity = rate * qualified minutes - distributed. A late commitment cannot backdate it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from plan_b.domain.models import (
    ActivityDef,
    CheckInView,
    ConsumableStateView,
    ConsumableStock,
    DistributionView,
    EventGoal,
    ExpectedShipment,
    ExpectedShipmentView,
    HandoffTaskStatus,
    HandoffTaskView,
    HoldView,
    ObservationRecord,
    PantryParameters,
    ResourceDef,
    ServiceOutcome,
    ServiceProgressView,
    ServiceTarget,
    StockAllocationView,
    StockBalanceView,
    StockMovementView,
    StockOutcome,
    StockReceiptView,
)

# Constraint ids the consumable planner adds to the activity checks (contract section 10).
PANTRY_CHECK_IDS = (
    "consumable_allocation",
    "stock_on_hand",
    "stock_transfer",
    "service_throughput",
)
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class StockRecords:
    """Everything the consumable projection reads, as the store loaded it."""

    clock: datetime
    hard_end: datetime
    goal: EventGoal
    original_goal: EventGoal  # goal version 1: attainment is scored against its targets
    pantry: PantryParameters | None
    activities: tuple[ActivityDef, ...]
    resources: tuple[ResourceDef, ...]
    holds: tuple[HoldView, ...]  # effective status already evaluated against the clock
    movements: tuple[StockMovementView, ...]
    receipts: tuple[StockReceiptView, ...]
    distributions: tuple[DistributionView, ...]
    allocations: tuple[StockAllocationView, ...]
    shipments: tuple[ExpectedShipment, ...]  # received_quantity as reconciled
    observations: tuple[ObservationRecord, ...]
    activity_starts: dict[str, datetime]  # actual start of each started activity
    checkins: tuple[CheckInView, ...]


def consumable_ids(resources: Iterable[ResourceDef]) -> tuple[str, ...]:
    return tuple(r.resource_id for r in resources if r.consumable_stock is not None)


def live_holds(holds: Iterable[HoldView], resource_id: str | None = None) -> list[HoldView]:
    """Consumable holds whose remainder still reserves stock."""
    return [
        h
        for h in holds
        if h.consumable
        and h.effective_status == "active"
        and (resource_id is None or h.resource_id == resource_id)
    ]


def held_quantity(holds: Iterable[HoldView], resource_id: str) -> int:
    return sum(h.remaining_quantity or 0 for h in live_holds(holds, resource_id))


def committed_quantity(
    allocations: Iterable[StockAllocationView],
    *,
    resource_id: str | None = None,
    target_id: str | None = None,
) -> int:
    return sum(
        a.remaining_quantity
        for a in allocations
        if (resource_id is None or a.resource_id == resource_id)
        and (target_id is None or a.service_target_id == target_id)
    )


def distributed_quantity(
    distributions: Iterable[DistributionView],
    *,
    resource_id: str | None = None,
    target_id: str | None = None,
    on_time_only: bool = False,
) -> int:
    return sum(
        d.quantity
        for d in distributions
        if (resource_id is None or d.resource_id == resource_id)
        and (target_id is None or d.service_target_id == target_id)
        and (d.on_time or not on_time_only)
    )


def own_service_holds(
    holds: Iterable[HoldView], *, actor_id: str, resource_id: str, target_id: str, activity_id: str
) -> list[HoldView]:
    """The actor's live activity holds on a pool for one target and activity: the units
    ``apply_plan`` converts into a committed allocation."""
    return [
        h
        for h in live_holds(holds, resource_id)
        if h.actor_id == actor_id
        and h.purpose == "activity"
        and h.service_target_id == target_id
        and h.activity_id == activity_id
    ]


def own_transfer_holds(
    holds: Iterable[HoldView], *, actor_id: str, source_id: str, destination_id: str
) -> list[HoldView]:
    """The actor's live stock-transfer holds from ``source_id`` into ``destination_id``."""
    return [
        h
        for h in live_holds(holds, source_id)
        if h.actor_id == actor_id
        and h.purpose == "stock_transfer"
        and h.destination_resource_id == destination_id
    ]


def target_pools(
    target: ServiceTarget, activities: Iterable[ActivityDef], consumables: set[str]
) -> tuple[str, ...]:
    """The pantry-controlled pools a target draws from: the consumable required resources of
    its service activity."""
    for activity in activities:
        if activity.activity_id == target.activity_id:
            return tuple(r for r in activity.required_resources if r in consumables)
    return ()


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------


def balance(rec: StockRecords, resource: ResourceDef) -> StockBalanceView:
    rid = resource.resource_id
    assert resource.consumable_stock is not None
    moves = [m for m in rec.movements if m.resource_id == rid]

    def total(kind: str) -> int:
        return sum(m.quantity for m in moves if m.kind == kind)

    opening, received = total("opening"), total("receipt")
    out, distributed = total("transfer_out"), total("distribution")
    on_hand = sum(m.delta for m in moves)
    held = held_quantity(rec.holds, rid)
    committed = committed_quantity(rec.allocations, resource_id=rid)
    reserved = held + committed
    expected = sum(
        s.quantity - s.received_quantity for s in rec.shipments if s.destination_resource_id == rid
    )
    # Cross-record conservation: the ledger's kinds, the physical receipt and distribution
    # records and the reservations must all agree.
    conserved = (
        on_hand == opening + received - out - distributed
        and on_hand >= 0
        and 0 <= reserved <= on_hand
        and received == sum(r.quantity for r in rec.receipts if r.resource_id == rid)
        and out
        == sum(
            r.quantity
            for r in rec.receipts
            if r.kind == "internal_handoff" and r.source_resource_id == rid
        )
        and distributed == distributed_quantity(rec.distributions, resource_id=rid)
    )
    return StockBalanceView(
        resource_id=rid,
        unit=resource.consumable_stock.unit,
        opening_quantity=opening,
        received_quantity=received,
        transferred_out_quantity=out,
        distributed_quantity=distributed,
        on_hand_quantity=on_hand,
        held_quantity=held,
        committed_quantity=committed,
        reserved_quantity=reserved,
        available_quantity=on_hand - reserved,
        expected_quantity=expected,
        conserved=conserved,
    )


def as_consumable_stock(b: StockBalanceView) -> ConsumableStock:
    """The planning-shaped live stock of a pool (``ResourceView.consumable_stock``)."""
    return ConsumableStock(
        unit=b.unit,
        on_hand_quantity=max(b.on_hand_quantity, 0),
        reserved_quantity=max(b.reserved_quantity, 0),
        distributed_quantity=b.distributed_quantity,
        expected_quantity=b.expected_quantity,
    )


# ---------------------------------------------------------------------------
# Service capacity
# ---------------------------------------------------------------------------


def latest_checkin(
    checkins: Iterable[CheckInView], staff_id: str, at: datetime
) -> CheckInView | None:
    """The staff resource's current declaration at ``at``: its latest check-in made by then
    (ties go to the later record, as in readiness)."""
    latest: CheckInView | None = None
    for c in checkins:
        if c.resource_id == staff_id and c.at <= at and (latest is None or c.at >= latest.at):
            latest = c
    return latest


def _covers(declaration: CheckInView | None, minute: datetime) -> bool:
    return (
        declaration is not None
        and declaration.available.start <= minute
        and minute + MINUTE <= declaration.available.end
    )


def qualified_minutes(
    target: ServiceTarget,
    *,
    until: datetime,
    started_at: datetime | None,
    pantry: PantryParameters | None,
    allocations: Iterable[StockAllocationView],
    distributions: Iterable[DistributionView],
    checkins: Iterable[CheckInView],
    hard_end: datetime,
) -> int:
    """Whole minutes in ``[started_at, until)`` of staffed service with committed, undistributed
    stock for the target. A distribution recorded at an instant consumes its units from then on,
    so the minute that ends at that instant still counts."""
    if started_at is None or pantry is None:
        return 0
    allocs = [a for a in allocations if a.service_target_id == target.target_id]
    dists = [d for d in distributions if d.service_target_id == target.target_id]
    people = tuple(checkins)
    count = 0
    minute = started_at
    end = min(until, hard_end)
    while minute < end:
        committed = sum(a.quantity for a in allocs if a.created_at <= minute) - sum(
            d.quantity for d in dists if d.at <= minute
        )
        declaration = latest_checkin(people, pantry.staff_resource_id, minute)
        if committed > 0 and _covers(declaration, minute):
            count += 1
        minute += MINUTE
    return count


def capacity_at(rec: StockRecords, target: ServiceTarget, at: datetime) -> int:
    """Units the staff could still distribute for the target at ``at``: the rate times the
    qualified minutes accrued by then, minus everything already distributed for it."""
    if rec.pantry is None:
        return 0
    minutes = qualified_minutes(
        target,
        until=at,
        started_at=rec.activity_starts.get(target.activity_id),
        pantry=rec.pantry,
        allocations=rec.allocations,
        distributions=rec.distributions,
        checkins=rec.checkins,
        hard_end=rec.hard_end,
    )
    done = distributed_quantity(rec.distributions, target_id=target.target_id)
    return max(rec.pantry.service_rate_units_per_minute * minutes - done, 0)


def service_capacity(
    target: ServiceTarget,
    *,
    by: datetime,
    pantry: PantryParameters | None,
    effective_at: datetime,
    service_start: datetime | None,
    started_at: datetime | None,
    allocations: Iterable[StockAllocationView],
    distributions: Iterable[DistributionView],
    checkins: Iterable[CheckInView],
    clock: datetime,
    hard_end: datetime,
) -> int:
    """The cumulative units of ``target`` staff could distribute by ``by`` (its deadline for
    on-time service, the event end for any service) if committed stock were in place from
    ``effective_at``: the qualified minutes accrued before then, plus every minute from
    ``max(service_start, effective_at)`` to ``by`` that the staff's current declaration covers,
    times the rate.

    ``started_at`` is the service activity's actual start (None before it starts);
    ``service_start`` is that start, or the planned start of an activity still to run, and None
    when it can no longer run (no future minutes)."""
    if pantry is None:
        return 0
    people = tuple(checkins)
    deadline = min(by, hard_end)
    past = qualified_minutes(
        target,
        until=min(effective_at, deadline),
        started_at=started_at,
        pantry=pantry,
        allocations=allocations,
        distributions=distributions,
        checkins=people,
        hard_end=hard_end,
    )
    future = 0
    if service_start is not None:
        # Future minutes are judged on the staff's declaration as it stands now.
        declaration = latest_checkin(people, pantry.staff_resource_id, clock)
        minute = max(service_start, effective_at)
        while minute < deadline:
            if _covers(declaration, minute):
                future += 1
            minute += MINUTE
    return pantry.service_rate_units_per_minute * (past + future)


# ---------------------------------------------------------------------------
# The consumable state projection
# ---------------------------------------------------------------------------


def _shipment_status(
    observations: Iterable[ObservationRecord], shipment_id: str
) -> tuple[datetime | None, str | None]:
    """The latest typed status of a shipment (newest source time wins, as for resources)."""
    best: ObservationRecord | None = None
    for rec in observations:
        facts = rec.structured
        if facts is None or facts.shipment_id != shipment_id:
            continue
        if best is None or best.observation.observed_at <= rec.observation.observed_at:
            best = rec
    if best is None or best.structured is None:
        return None, None
    return best.structured.reported_eta, best.observation.observation_id


def service_progress(
    rec: StockRecords, target: ServiceTarget, balances: dict[str, StockBalanceView]
) -> ServiceProgressView:
    tid = target.target_id
    consumables = set(balances)
    pools = target_pools(target, rec.activities, consumables)
    distributed = distributed_quantity(rec.distributions, target_id=tid)
    on_time = distributed_quantity(rec.distributions, target_id=tid, on_time_only=True)
    original = next(
        (t.quantity for t in rec.original_goal.service_targets if t.target_id == tid),
        target.quantity,
    )
    # Pantry-controlled supply for this target: its pools' on-hand stock, minus units that
    # leave a pool on a transfer hold or that the pools hold or commit for other targets.
    other = sum(
        h.remaining_quantity or 0
        for h in live_holds(rec.holds)
        if h.resource_id in pools
        and (h.purpose == "stock_transfer" or h.service_target_id not in (None, tid))
    ) + sum(
        a.remaining_quantity
        for a in rec.allocations
        if a.resource_id in pools and a.service_target_id != tid
    )
    supply = sum(balances[p].on_hand_quantity for p in pools) - other
    remaining = max(target.quantity - distributed, 0)
    minutes = qualified_minutes(
        target,
        until=rec.clock,
        started_at=rec.activity_starts.get(target.activity_id),
        pantry=rec.pantry,
        allocations=rec.allocations,
        distributions=rec.distributions,
        checkins=rec.checkins,
        hard_end=rec.hard_end,
    )
    rate = rec.pantry.service_rate_units_per_minute if rec.pantry is not None else 0
    return ServiceProgressView(
        target_id=tid,
        unit=target.unit,
        activity_id=target.activity_id,
        deadline=target.deadline,
        target_quantity=target.quantity,
        original_quantity=original,
        distributed_quantity=distributed,
        on_time_quantity=on_time,
        late_quantity=distributed - on_time,
        committed_quantity=committed_quantity(rec.allocations, target_id=tid),
        supply_gap_quantity=max(remaining - supply, 0),
        unfulfilled_quantity=max(original - on_time, 0),
        qualified_minutes=minutes,
        capacity_quantity=max(rate * minutes - distributed, 0),
        attained=on_time >= original,
    )


def handoff_tasks(rec: StockRecords) -> tuple[HandoffTaskView, ...]:
    if rec.pantry is None:
        return ()
    out: list[HandoffTaskView] = []
    for h in rec.holds:
        if not h.consumable or h.purpose != "stock_transfer" or h.destination_resource_id is None:
            continue
        mine = tuple(r.stock_receipt_id for r in rec.receipts if r.source_hold_id == h.hold_id)
        status: HandoffTaskStatus
        if h.effective_status == "fulfilled":
            status = "fulfilled"
        elif h.effective_status == "active":
            status = "partially_fulfilled" if mine else "open"
        else:
            status = "lapsed"
        out.append(
            HandoffTaskView(
                hold_id=h.hold_id,
                source_resource_id=h.resource_id,
                destination_resource_id=h.destination_resource_id,
                requested_quantity=h.quantity,
                remaining_quantity=h.remaining_quantity or 0,
                requested_at=h.created_at,
                respond_after=h.created_at + timedelta(minutes=rec.pantry.handoff_duration_minutes),
                cutoff=min(h.expires_at, rec.pantry.handoff_window.end),
                status=status,
                stock_receipt_ids=mine,
            )
        )
    return tuple(out)


def consumable_state(rec: StockRecords) -> ConsumableStateView:
    consumable = [r for r in rec.resources if r.consumable_stock is not None]
    balances = {r.resource_id: balance(rec, r) for r in consumable}
    shipments: list[ExpectedShipmentView] = []
    for s in rec.shipments:
        eta, obs_id = _shipment_status(rec.observations, s.shipment_id)
        shipments.append(
            ExpectedShipmentView(
                shipment=s,
                outstanding_quantity=s.quantity - s.received_quantity,
                reported_eta=eta,
                status_observation_id=obs_id,
            )
        )
    return ConsumableStateView(
        balances=tuple(balances.values()),
        expected_shipments=tuple(shipments),
        service=tuple(service_progress(rec, t, balances) for t in rec.goal.service_targets),
        allocations=rec.allocations,
        movements=rec.movements,
        receipts=rec.receipts,
        distributions=rec.distributions,
        handoff_tasks=handoff_tasks(rec),
    )


# ---------------------------------------------------------------------------
# Lookups over a projected state
# ---------------------------------------------------------------------------


def balance_of(state: ConsumableStateView, resource_id: str) -> StockBalanceView | None:
    return next((b for b in state.balances if b.resource_id == resource_id), None)


def service_of(state: ConsumableStateView, target_id: str) -> ServiceProgressView | None:
    return next((s for s in state.service if s.target_id == target_id), None)


def find_target(goal: EventGoal, target_id: str) -> ServiceTarget | None:
    return next((t for t in goal.service_targets if t.target_id == target_id), None)


def service_outcomes(state: ConsumableStateView) -> tuple[ServiceOutcome, ...]:
    """Each target scored against its original quantity (``OutcomeReport.service``)."""
    return tuple(
        ServiceOutcome(
            target_id=s.target_id,
            unit=s.unit,
            original_quantity=s.original_quantity,
            distributed_quantity=s.distributed_quantity,
            on_time_quantity=s.on_time_quantity,
            late_quantity=s.late_quantity,
            unfulfilled_quantity=s.unfulfilled_quantity,
            supply_gap_quantity=s.supply_gap_quantity,
            attained=s.attained,
        )
        for s in state.service
    )


def stock_outcomes(state: ConsumableStateView) -> tuple[StockOutcome, ...]:
    """Each pool's conservation terms at the end (``OutcomeReport.stock``)."""
    return tuple(
        StockOutcome(
            resource_id=b.resource_id,
            opening_quantity=b.opening_quantity,
            received_quantity=b.received_quantity,
            transferred_out_quantity=b.transferred_out_quantity,
            distributed_quantity=b.distributed_quantity,
            closing_on_hand_quantity=b.on_hand_quantity,
            expected_unreceived_quantity=b.expected_quantity,
            conserved=b.conserved,
        )
        for b in state.balances
    )


# ---------------------------------------------------------------------------
# The labeled staff simulator's quantity rules (decided from visible state at the instant)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StaffFill:
    """What a scheduled staff action records, or why it records nothing."""

    arguments: dict[str, object] | None
    note: str


def handoff_fill(
    holds: Iterable[HoldView],
    *,
    hold_id: str,
    already_confirmed: int,
    max_quantity: int | None,
    now: datetime,
    pantry: PantryParameters | None,
) -> StaffFill:
    """The staff response to a stock-transfer task: confirm the hold's live remainder while the
    hold and the handoff window are valid. ``max_quantity`` caps what this staff confirms from
    the source over the whole episode (``already_confirmed`` counts earlier responses), so a
    partial answer is not topped up by asking again."""
    hold = next((h for h in holds if h.hold_id == hold_id), None)
    if hold is None or hold.effective_status != "active" or not hold.remaining_quantity:
        return StaffFill(None, f"hold {hold_id} is no longer live; staff recorded no handoff")
    if pantry is None or not (pantry.handoff_window.start <= now < pantry.handoff_window.end):
        return StaffFill(None, "the handoff window is closed; staff recorded no handoff")
    quantity = hold.remaining_quantity
    if max_quantity is not None:
        quantity = min(quantity, max_quantity - already_confirmed)
    if quantity <= 0:
        return StaffFill(None, f"staff confirm no more units for {hold_id}; nothing recorded")
    return StaffFill({"quantity": quantity}, f"staff confirmed {quantity} units for {hold_id}")


def distribution_fill(
    state: ConsumableStateView, goal: EventGoal, *, target_id: str, at: datetime
) -> StaffFill:
    """The staff's aggregate distribution record: min(committed undistributed stock, original
    target - distributed, accrued capacity), from one pool's committed allocations."""
    progress = service_of(state, target_id)
    target = find_target(goal, target_id)
    if progress is None or target is None:
        return StaffFill(None, f"target {target_id} is not registered; nothing recorded")
    allocations = [
        a for a in state.allocations if a.service_target_id == target_id and a.remaining_quantity
    ]
    if not allocations:
        return StaffFill(None, f"no committed stock for {target_id}; nothing recorded")
    pool = allocations[0].resource_id
    pool_allocations = [a for a in allocations if a.resource_id == pool]
    committed = sum(a.remaining_quantity for a in pool_allocations)
    quantity = min(
        committed,
        max(progress.original_quantity - progress.distributed_quantity, 0),
        progress.capacity_quantity,
    )
    if quantity <= 0:
        return StaffFill(
            None, f"no service capacity left for {target_id} at {at}; nothing recorded"
        )
    return StaffFill(
        {
            "resource_id": pool,
            "quantity": quantity,
            "unit": target.unit,
            "service_target_id": target_id,
            "activity_id": target.activity_id,
            "allocation_ids": [a.allocation_id for a in pool_allocations],
        },
        f"staff recorded {quantity} units distributed for {target_id}",
    )
