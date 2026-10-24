"""Consumable stock effects (runtime 1.1.0), called by ``tools.handlers`` inside the executor's
transaction and its handler savepoint.

* ``hold_consumable``: ``hold_resource`` on a pool with ``consumable_stock``. A quantity
  reservation applies across the session, so it is checked against the pool's global available
  quantity (on hand minus every live hold remainder and committed allocation), never against a
  time window. A ``stock_transfer`` hold reserves an alternate pool's units for a staff handoff
  into a registered destination and creates the local staff task.
* ``convert_stock_holds``: ``apply_plan`` turns a candidate's bound activity holds into
  committed allocations. The hold's remainder moves into the allocation (the hold keeps none),
  so the same units are never reserved twice.
* ``record_stock_receipt`` and ``record_distribution``: the staff-only physical attestations.
  Physical identity (``receipt_reference``, ``distribution_reference``) is unique per episode
  whatever the request's idempotency key, so a resubmitted physical record is refused with
  ``DUPLICATE_REFERENCE`` and credits nothing.

Each mutation bumps the revision exactly once. Every refusal raises ``Rejection`` and the
handler savepoint rolls back whatever was written before it.
"""

from __future__ import annotations

from datetime import timedelta

from plan_b.domain.models import (
    ActivityDef,
    CandidateResult,
    ConsumableStateView,
    DistributionView,
    ResourceDef,
    StateChange,
    StockAllocationView,
    StockBalanceView,
    StockReceiptView,
    TimeWindow,
)
from plan_b.domain.stock import (
    balance_of,
    capacity_at,
    distributed_quantity,
    find_target,
)
from plan_b.domain.timeutil import fmt_ts, local_label
from plan_b.store import repo
from plan_b.store.projection_db import build_snapshot, stock_records
from plan_b.tools import handlers
from plan_b.tools.executor import Ctx, Outcome, Rejection
from plan_b.world.world import world_for_episode


def _stock(ctx: Ctx) -> ConsumableStateView:
    stock = build_snapshot(ctx.conn, ctx.episode_id).stock
    if stock is None:
        raise Rejection("HOLD_NOT_SUPPORTED", "this event registers no consumable stock")
    return stock


def _balance(stock: ConsumableStateView, resource_id: str) -> StockBalanceView:
    found = balance_of(stock, resource_id)
    if found is None:
        raise Rejection("INVALID_REQUEST", f"{resource_id} is not a consumable stock pool")
    return found


def _pool(ctx: Ctx, resource_id: str) -> ResourceDef:
    resource = handlers._resource(ctx, resource_id)
    if resource.consumable_stock is None:
        raise Rejection("INVALID_REQUEST", f"{resource_id} is not a consumable stock pool")
    return resource


def _unit(resource: ResourceDef) -> str:
    assert resource.consumable_stock is not None
    return resource.consumable_stock.unit


def _in_scope(ctx: Ctx, resource_id: str) -> None:
    if resource_id not in ctx.grant.resource_ids:
        raise Rejection("SCOPE_VIOLATION", f"{resource_id} is outside this grant")


def _stock_details(b: StockBalanceView) -> dict[str, int]:
    return {
        "on_hand_quantity": b.on_hand_quantity,
        "reserved_quantity": b.reserved_quantity,
        "available_quantity": b.available_quantity,
        "expected_quantity": b.expected_quantity,
    }


# ---------------------------------------------------------------------------
# hold_resource on a consumable pool
# ---------------------------------------------------------------------------


def hold_consumable(ctx: Ctx, resource: ResourceDef, activity: ActivityDef) -> Outcome:
    """Checks in order: purpose and target bindings, unit, window, visible status, handoff
    window (transfer holds), available quantity, money limits, then the steward."""
    args = ctx.args
    rid = resource.resource_id
    unit = _unit(resource)
    pantry = ctx.scenario.pantry_parameters
    goal = repo.goal(ctx.conn, ctx.episode_id)
    if args.purpose == "stock_transfer":
        destination = _pool(ctx, args.destination_resource_id)
        did = destination.resource_id
        if did == rid:
            raise Rejection("INVALID_REQUEST", "a stock transfer needs a different destination")
        _in_scope(ctx, did)
        if _unit(destination) != unit:
            raise Rejection(
                "UNIT_MISMATCH",
                f"{rid} counts {unit} but {did} counts {_unit(destination)}; no unit conversion"
                " is registered",
            )
        registered = any(
            o.option == "transfer_stock" and o.source_resource_id == rid and o.resource_id == did
            for o in ctx.scenario.stock_options
        )
        if not registered:
            raise Rejection(
                "CONSTRAINT_VIOLATION", f"{rid} is not a registered transfer source for {did}"
            )
        if did not in activity.required_resources:
            raise Rejection(
                "CONSTRAINT_VIOLATION", f"{did} is not a stock pool of {activity.activity_id}"
            )
        if args.service_target_id is not None:
            raise Rejection(
                "INVALID_REQUEST",
                "a transfer hold reserves source units for a handoff; it serves no target",
            )
    else:
        if rid not in activity.required_resources:
            raise Rejection(
                "CONSTRAINT_VIOLATION", f"{rid} is not a stock pool of {activity.activity_id}"
            )
        if args.service_target_id is None:
            raise Rejection("INVALID_REQUEST", "a stock hold names the service target it serves")
        target = find_target(goal, args.service_target_id)
        if target is None:
            raise Rejection(
                "UNKNOWN_ENTITY", f"service target {args.service_target_id!r} is not registered"
            )
        if target.activity_id != activity.activity_id:
            raise Rejection(
                "CONSTRAINT_VIOLATION",
                f"target {target.target_id} is served by {target.activity_id}, not"
                f" {activity.activity_id}",
            )
        if target.unit != unit:
            raise Rejection(
                "UNIT_MISMATCH", f"target {target.target_id} counts {target.unit}, {rid} {unit}"
            )
    window: TimeWindow = args.window
    if not resource.window.contains(window) or not activity.window.contains(window):
        raise Rejection(
            "CONSTRAINT_VIOLATION", "hold window must lie within the resource and activity windows"
        )
    # A quantity reservation applies across the remaining session, so it may cover a session
    # already under way; it must not have ended.
    if window.end <= ctx.now:
        raise Rejection("CONSTRAINT_VIOLATION", "a stock hold must cover a window not yet ended")
    snap = build_snapshot(ctx.conn, ctx.episode_id)
    view = next(r for r in snap.resources if r.definition.resource_id == rid)
    if view.status == "unavailable":
        raise Rejection(
            "RESOURCE_UNAVAILABLE",
            f"{rid} is reported unavailable",
            {"status_observation_id": view.status_observation_id},
        )
    terms = resource.terms
    max_minutes = terms.hold_max_minutes or 10
    expires = ctx.now + timedelta(minutes=min(args.hold_minutes or max_minutes, max_minutes))
    if args.purpose == "stock_transfer":
        if pantry is None:
            raise Rejection("HOLD_NOT_SUPPORTED", "this event declares no staff handoff timing")
        cutoff = pantry.handoff_window.end
        respond = ctx.now + timedelta(minutes=pantry.handoff_duration_minutes)
        if not pantry.handoff_window.start <= ctx.now or respond >= cutoff:
            raise Rejection(
                "HANDOFF_WINDOW_CLOSED",
                f"staff need {pantry.handoff_duration_minutes} min to respond and handoffs are"
                f" accepted only before {local_label(cutoff)}",
                {"handoff_cutoff": fmt_ts(cutoff), "respond_after": fmt_ts(respond)},
            )
        expires = min(expires, cutoff)
    assert snap.stock is not None
    before = _balance(snap.stock, rid)
    if args.quantity > before.available_quantity:
        raise Rejection(
            "INSUFFICIENT_STOCK",
            f"{rid} has {before.available_quantity} {unit} available ({before.on_hand_quantity}"
            f" on hand, {before.reserved_quantity} reserved); expected units are not stock",
            _stock_details(before),
        )
    exposure = terms.reserved_exposure_cents * args.quantity
    fee = terms.hold_fee_cents * args.quantity
    c_used, r_used = repo.grant_usage(ctx.conn, ctx.episode_id, ctx.grant.grant_id)
    total_c, total_r = repo.ledger_totals(ctx.conn, ctx.episode_id)
    if (
        r_used + exposure > ctx.grant.max_total_reserved_cents
        or c_used + fee > ctx.grant.max_total_committed_cents
        or total_c + total_r + exposure + fee > goal.budget_cents
    ):
        raise Rejection(
            "BUDGET_EXCEEDED",
            f"holding {args.quantity} {unit} needs {exposure} reserved and {fee} committed cents,"
            " beyond the grant or the event budget",
        )
    _confirm_with_steward(ctx, resource)
    hold_id = f"hold_{repo.next_seq(ctx.conn, ctx.episode_id, 'hold'):04d}"
    ctx.conn.execute(
        "INSERT INTO holds (episode_id, hold_id, resource_id, activity_id, quantity, window_start,"
        " window_end, created_at, expires_at, commitment_cutoff, reserved_cents, hold_fee_cents,"
        " status, actor_id, grant_id, created_receipt_id, consumable, remaining_quantity,"
        " purpose, destination_resource_id, service_target_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'active', ?, ?, ?, 1, ?, ?, ?, ?)",
        (
            ctx.episode_id,
            hold_id,
            rid,
            activity.activity_id,
            args.quantity,
            fmt_ts(window.start),
            fmt_ts(window.end),
            fmt_ts(ctx.now),
            fmt_ts(expires),
            exposure,
            fee,
            ctx.actor_id,
            ctx.grant.grant_id,
            ctx.receipt_id,
            args.quantity,
            args.purpose,
            args.destination_resource_id,
            args.service_target_id,
        ),
    )
    repo.append_ledger(
        ctx.conn,
        ctx.episode_id,
        at=ctx.now,
        kind="reserve",
        committed_delta=0,
        reserved_delta=exposure,
        grant_id=ctx.grant.grant_id,
        hold_id=hold_id,
        receipt_id=ctx.receipt_id,
    )
    if fee:
        repo.append_ledger(
            ctx.conn,
            ctx.episode_id,
            at=ctx.now,
            kind="hold_fee",
            committed_delta=fee,
            reserved_delta=0,
            grant_id=ctx.grant.grant_id,
            hold_id=hold_id,
            receipt_id=ctx.receipt_id,
        )
    purpose = (
        f"a staff handoff into {args.destination_resource_id}"
        if args.purpose == "stock_transfer"
        else f"target {args.service_target_id}"
    )
    handlers._bump(
        ctx,
        "hold_created",
        hold_id,
        f"Hold {hold_id}: {args.quantity} {unit} of {rid} for {purpose} until"
        f" {local_label(expires)}; nothing moves until staff record it",
    )
    hold = handlers._hold_view(ctx, hold_id)
    return Outcome(
        data={"hold": hold.model_dump(mode="json")},
        summary=(
            f"Held {args.quantity} {unit} of {rid} for {purpose} until {local_label(expires)};"
            f" available {before.available_quantity} -> {before.available_quantity - args.quantity}"
        ),
        state_changes=[
            StateChange(entity_id=hold_id, field="status", before=None, after="active"),
            StateChange(
                entity_id=rid,
                field="reserved_quantity",
                before=before.reserved_quantity,
                after=before.reserved_quantity + args.quantity,
            ),
        ],
        committed_delta=fee,
        reserved_delta=exposure,
    )


def _confirm_with_steward(ctx: Ctx, resource: ResourceDef) -> None:
    """As for a booking: the pool's registered steward is asked last. A record about an
    expected shipment speaks for that shipment, not for the pool, and is not an answer."""
    terms = resource.terms
    if terms.status_source_id is None or not terms.queryable_facts:
        return
    world = world_for_episode(ctx.conn, ctx.episode_id)
    for fact in terms.queryable_facts:
        answer = world.status_answer(resource.resource_id, fact, ctx.now)
        if answer is None or (answer.response is not None and answer.response.shipment_id):
            continue
        if answer.outcome == "unavailable":
            raise Rejection(
                "STATUS_UNAVAILABLE",
                f"the steward of {resource.resource_id} could not be reached to confirm a hold",
            )
        if (
            answer.outcome == "ok"
            and answer.response is not None
            and answer.response.domain_status == "unavailable"
        ):
            raise Rejection(
                "RESOURCE_UNAVAILABLE",
                f"the steward of {resource.resource_id} declined the hold: its units are not"
                " available",
            )
        return


# ---------------------------------------------------------------------------
# apply_plan: holds -> committed allocations
# ---------------------------------------------------------------------------


def convert_stock_holds(
    ctx: Ctx, candidate: CandidateResult, plan_version: int
) -> tuple[list[StateChange], list[str], list[str]]:
    """Commit every bound stock hold of a revalidated candidate. Returns the state changes, the
    converted hold ids and the new allocation ids."""
    changes: list[StateChange] = []
    converted: list[str] = []
    allocation_ids: list[str] = []
    for need in candidate.required_stock_holds:
        for hold_id in need.bound_hold_ids:
            hold = handlers._hold_view(ctx, hold_id)
            quantity = hold.remaining_quantity or 0
            allocation_id = f"alloc_{repo.next_seq(ctx.conn, ctx.episode_id, 'allocation'):04d}"
            repo.insert_stock_allocation(
                ctx.conn,
                ctx.episode_id,
                StockAllocationView(
                    allocation_id=allocation_id,
                    resource_id=need.resource_id,
                    service_target_id=need.service_target_id,
                    activity_id=need.activity_id,
                    quantity=quantity,
                    remaining_quantity=quantity,
                    source_hold_id=hold.hold_id,
                    plan_version=plan_version,
                    created_at=ctx.now,
                    receipt_id=ctx.receipt_id or "",
                    actor_id=ctx.actor_id,
                    grant_id=ctx.grant.grant_id,
                ),
            )
            # The remainder moves into the allocation in the same statement that ends the hold.
            ctx.conn.execute(
                "UPDATE holds SET status = 'committed', remaining_quantity = 0, terminal_at = ?,"
                " terminal_receipt_id = ? WHERE episode_id = ? AND hold_id = ?",
                (fmt_ts(ctx.now), ctx.receipt_id, ctx.episode_id, hold.hold_id),
            )
            repo.append_ledger(
                ctx.conn,
                ctx.episode_id,
                at=ctx.now,
                kind="convert_reserve",
                committed_delta=0,
                reserved_delta=-hold.reserved_cents,
                grant_id=hold.grant_id,
                hold_id=hold.hold_id,
                receipt_id=ctx.receipt_id,
            )
            converted.append(hold.hold_id)
            allocation_ids.append(allocation_id)
            changes.append(
                StateChange(
                    entity_id=hold.hold_id, field="status", before="active", after="committed"
                )
            )
            changes.append(
                StateChange(
                    entity_id=allocation_id,
                    field="committed_quantity",
                    before=None,
                    after={
                        "resource_id": need.resource_id,
                        "service_target_id": need.service_target_id,
                        "quantity": quantity,
                    },
                )
            )
    return changes, converted, allocation_ids


# ---------------------------------------------------------------------------
# Staff attestations
# ---------------------------------------------------------------------------


def _observation_about(ctx: Ctx, observation_id: str, entity_ids: set[str]) -> None:
    """The cited source observation exists and concerns one of the attested entities."""
    for rec in repo.observations(ctx.conn, ctx.episode_id):
        obs = rec.observation
        if obs.observation_id != observation_id:
            continue
        if obs.entity_id not in entity_ids:
            raise Rejection(
                "INVALID_EVIDENCE_REFERENCE",
                f"observation {observation_id} concerns {obs.entity_id}, not"
                f" {', '.join(sorted(entity_ids))}",
            )
        return
    raise Rejection("INVALID_EVIDENCE_REFERENCE", f"observation {observation_id!r} does not exist")


def record_stock_receipt(ctx: Ctx) -> Outcome:
    """A staff-attested physical receipt: a registered internal handoff (source pool and its
    stock-transfer hold) or a matched external shipment."""
    handlers._check_revision(ctx)
    args = ctx.args
    destination = _pool(ctx, args.resource_id)
    did = destination.resource_id
    _in_scope(ctx, did)
    source = _pool(ctx, args.source_resource_id) if args.source_resource_id else None
    if source is not None:
        _in_scope(ctx, source.resource_id)
    prior = repo.stock_receipt_by_reference(ctx.conn, ctx.episode_id, args.receipt_reference)
    if prior is not None:
        raise Rejection(
            "DUPLICATE_REFERENCE",
            f"physical receipt {args.receipt_reference} was already recorded"
            f" ({prior.stock_receipt_id}); a new request key cannot credit it again",
            {"stock_receipt_id": prior.stock_receipt_id, "receipt_id": prior.receipt_id},
        )
    unit = _unit(destination)
    if args.unit != unit or (source is not None and _unit(source) != unit):
        raise Rejection("UNIT_MISMATCH", f"{did} counts {unit}; the receipt states {args.unit}")
    stock = _stock(ctx)
    into = _balance(stock, did)
    if source is not None:
        _observation_about(ctx, args.source_observation_id, {source.resource_id, did})
        return _internal_handoff(ctx, source, destination, stock, into)
    _observation_about(ctx, args.source_observation_id, {did})
    return _external_receipt(ctx, destination, into)


def _check_storage(destination: ResourceDef, into: StockBalanceView, quantity: int) -> None:
    if into.on_hand_quantity + quantity > destination.capacity:
        raise Rejection(
            "RESOURCE_CONFLICT",
            f"{destination.resource_id} stores at most {destination.capacity}; it holds"
            f" {into.on_hand_quantity}",
        )


def _internal_handoff(
    ctx: Ctx,
    source: ResourceDef,
    destination: ResourceDef,
    stock: ConsumableStateView,
    into: StockBalanceView,
) -> Outcome:
    args = ctx.args
    sid, did = source.resource_id, destination.resource_id
    unit = _unit(destination)
    hold = handlers._hold_view(ctx, args.source_hold_id)
    if (
        hold.resource_id != sid
        or not hold.consumable
        or hold.purpose != "stock_transfer"
        or hold.destination_resource_id != did
    ):
        raise Rejection(
            "INVALID_REQUEST",
            f"hold {hold.hold_id} is not a stock-transfer hold from {sid} into {did}",
        )
    if hold.effective_status != "active":
        code = "HOLD_EXPIRED" if hold.effective_status == "expired" else "HOLD_NOT_ACTIVE"
        raise Rejection(
            code,
            f"hold {hold.hold_id} is {hold.effective_status}; it reserves nothing to hand off",
            {"state": hold.effective_status},
        )
    pantry = ctx.scenario.pantry_parameters
    if pantry is None or not pantry.handoff_window.start <= ctx.now < pantry.handoff_window.end:
        raise Rejection(
            "HANDOFF_WINDOW_CLOSED",
            "handoffs are accepted only inside the declared handoff window",
        )
    remaining = hold.remaining_quantity or 0
    out_of = _balance(stock, sid)
    if args.quantity > remaining or args.quantity > out_of.on_hand_quantity:
        raise Rejection(
            "INSUFFICIENT_STOCK",
            f"hold {hold.hold_id} reserves {remaining} {unit} of {sid}"
            f" ({out_of.on_hand_quantity} on hand); {args.quantity} cannot be handed off",
            {"remaining_quantity": remaining, **_stock_details(out_of)},
        )
    _check_storage(destination, into, args.quantity)
    receipt_seq = repo.next_seq(ctx.conn, ctx.episode_id, "stock_receipt")
    stock_receipt_id = f"srec_{receipt_seq:04d}"
    left = remaining - args.quantity
    status = "fulfilled" if left == 0 else "active"
    rev = handlers._bump(
        ctx,
        "stock_received",
        stock_receipt_id,
        f"Staff recorded handoff {args.receipt_reference}: {args.quantity} {unit} from {sid} to"
        f" {did} ({out_of.on_hand_quantity}/{into.on_hand_quantity} ->"
        f" {out_of.on_hand_quantity - args.quantity}/{into.on_hand_quantity + args.quantity})",
    )
    if left == 0:
        ctx.conn.execute(
            "UPDATE holds SET status = 'fulfilled', remaining_quantity = 0, terminal_at = ?,"
            " terminal_receipt_id = ? WHERE episode_id = ? AND hold_id = ?",
            (fmt_ts(ctx.now), ctx.receipt_id, ctx.episode_id, hold.hold_id),
        )
    else:
        ctx.conn.execute(
            "UPDATE holds SET remaining_quantity = ? WHERE episode_id = ? AND hold_id = ?",
            (left, ctx.episode_id, hold.hold_id),
        )
    for pool, kind, other in ((sid, "transfer_out", did), (did, "receipt", sid)):
        repo.append_stock_movement(
            ctx.conn,
            ctx.episode_id,
            at=ctx.now,
            resource_id=pool,
            kind=kind,
            quantity=args.quantity,
            revision=rev,
            counterpart_resource_id=other,
            reference=args.receipt_reference,
            hold_id=hold.hold_id,
            receipt_id=ctx.receipt_id,
        )
    record = StockReceiptView(
        stock_receipt_id=stock_receipt_id,
        receipt_reference=args.receipt_reference,
        kind="internal_handoff",
        resource_id=did,
        source_resource_id=sid,
        source_hold_id=hold.hold_id,
        shipment_id=None,
        quantity=args.quantity,
        unit=unit,
        source_observation_id=args.source_observation_id,
        at=ctx.now,
        actor_id=ctx.actor_id,
        receipt_id=ctx.receipt_id or "",
        revision=rev,
    )
    repo.insert_stock_receipt(ctx.conn, ctx.episode_id, record)
    changes = [
        StateChange(
            entity_id=sid,
            field="on_hand_quantity",
            before=out_of.on_hand_quantity,
            after=out_of.on_hand_quantity - args.quantity,
        ),
        StateChange(
            entity_id=did,
            field="on_hand_quantity",
            before=into.on_hand_quantity,
            after=into.on_hand_quantity + args.quantity,
        ),
        StateChange(
            entity_id=hold.hold_id, field="remaining_quantity", before=remaining, after=left
        ),
        StateChange(entity_id=stock_receipt_id, field="stock_receipt", before=None, after=did),
    ]
    if status == "fulfilled":
        changes.append(
            StateChange(entity_id=hold.hold_id, field="status", before="active", after="fulfilled")
        )
    return Outcome(
        data={"stock_receipt": record.model_dump(mode="json"), "hold_status": status},
        summary=(
            f"Recorded handoff {args.receipt_reference}: {args.quantity} {unit} moved from {sid}"
            f" to {did}; hold {hold.hold_id} has {left} left"
        ),
        state_changes=changes,
    )


def _external_receipt(ctx: Ctx, destination: ResourceDef, into: StockBalanceView) -> Outcome:
    args = ctx.args
    did = destination.resource_id
    unit = _unit(destination)
    shipment = next(
        (
            s
            for s in repo.expected_shipments(ctx.conn, ctx.episode_id)
            if s.shipment_id == args.shipment_id
        ),
        None,
    )
    if shipment is None:
        raise Rejection("UNKNOWN_ENTITY", f"shipment {args.shipment_id!r} is not registered")
    if shipment.destination_resource_id != did:
        raise Rejection(
            "INVALID_REQUEST",
            f"shipment {shipment.shipment_id} is expected at {shipment.destination_resource_id}",
        )
    outstanding = shipment.quantity - shipment.received_quantity
    if args.quantity > outstanding:
        raise Rejection(
            "INVALID_REQUEST",
            f"shipment {shipment.shipment_id} has {outstanding} {unit} outstanding; a receipt"
            " cannot exceed it",
            {"outstanding_quantity": outstanding},
        )
    _check_storage(destination, into, args.quantity)
    stock_receipt_id = f"srec_{repo.next_seq(ctx.conn, ctx.episode_id, 'stock_receipt'):04d}"
    rev = handlers._bump(
        ctx,
        "stock_received",
        stock_receipt_id,
        f"Staff recorded receipt {args.receipt_reference}: {args.quantity} {unit} of shipment"
        f" {shipment.shipment_id} into {did}",
    )
    ctx.conn.execute(
        "UPDATE expected_shipments SET received_quantity = received_quantity + ?"
        " WHERE episode_id = ? AND shipment_id = ?",
        (args.quantity, ctx.episode_id, shipment.shipment_id),
    )
    repo.append_stock_movement(
        ctx.conn,
        ctx.episode_id,
        at=ctx.now,
        resource_id=did,
        kind="receipt",
        quantity=args.quantity,
        revision=rev,
        reference=args.receipt_reference,
        shipment_id=shipment.shipment_id,
        receipt_id=ctx.receipt_id,
    )
    record = StockReceiptView(
        stock_receipt_id=stock_receipt_id,
        receipt_reference=args.receipt_reference,
        kind="external_shipment",
        resource_id=did,
        source_resource_id=None,
        source_hold_id=None,
        shipment_id=shipment.shipment_id,
        quantity=args.quantity,
        unit=unit,
        source_observation_id=args.source_observation_id,
        at=ctx.now,
        actor_id=ctx.actor_id,
        receipt_id=ctx.receipt_id or "",
        revision=rev,
    )
    repo.insert_stock_receipt(ctx.conn, ctx.episode_id, record)
    return Outcome(
        data={"stock_receipt": record.model_dump(mode="json")},
        summary=(
            f"Recorded receipt {args.receipt_reference}: {args.quantity} {unit} of shipment"
            f" {shipment.shipment_id} into {did}"
        ),
        state_changes=[
            StateChange(
                entity_id=did,
                field="on_hand_quantity",
                before=into.on_hand_quantity,
                after=into.on_hand_quantity + args.quantity,
            ),
            StateChange(
                entity_id=shipment.shipment_id,
                field="received_quantity",
                before=shipment.received_quantity,
                after=shipment.received_quantity + args.quantity,
            ),
            StateChange(entity_id=stock_receipt_id, field="stock_receipt", before=None, after=did),
        ],
    )


def record_distribution(ctx: Ctx) -> Outcome:
    """A staff-attested aggregate distribution that consumes committed, reserved stock.

    The record keeps its actual time: one at or before the target's original deadline counts
    on time; a later one is recorded truthfully and counts only as late."""
    handlers._check_revision(ctx)
    handlers._check_goal_version(ctx)
    args = ctx.args
    pool = _pool(ctx, args.resource_id)
    rid = pool.resource_id
    activity = handlers._activity(ctx, args.activity_id)
    _in_scope(ctx, rid)
    if activity.activity_id not in ctx.grant.activity_ids:
        raise Rejection("SCOPE_VIOLATION", f"{activity.activity_id} is outside this grant")
    prior = repo.distribution_by_reference(ctx.conn, ctx.episode_id, args.distribution_reference)
    if prior is not None:
        raise Rejection(
            "DUPLICATE_REFERENCE",
            f"distribution {args.distribution_reference} was already recorded"
            f" ({prior.distribution_id}); a new request key cannot count it again",
            {"distribution_id": prior.distribution_id, "receipt_id": prior.receipt_id},
        )
    goal = repo.goal(ctx.conn, ctx.episode_id)
    target = find_target(goal, args.service_target_id)
    if target is None:
        raise Rejection(
            "UNKNOWN_ENTITY", f"service target {args.service_target_id!r} is not registered"
        )
    if target.activity_id != activity.activity_id:
        raise Rejection(
            "INVALID_REQUEST",
            f"target {target.target_id} is served by {target.activity_id}, not"
            f" {activity.activity_id}",
        )
    unit = _unit(pool)
    if args.unit != target.unit or unit != target.unit:
        raise Rejection(
            "UNIT_MISMATCH",
            f"target {target.target_id} counts {target.unit}; {rid} counts {unit}; the record"
            f" states {args.unit}",
        )
    _, lifecycles = repo.activity_rows(ctx.conn, ctx.episode_id)
    if lifecycles.get(activity.activity_id) not in ("started", "completed"):
        raise Rejection(
            "CONSTRAINT_VIOLATION",
            f"{activity.activity_id} is {lifecycles.get(activity.activity_id)}; distribution is"
            " recorded only once it has actually started",
        )
    allocations = {a.allocation_id: a for a in repo.stock_allocations(ctx.conn, ctx.episode_id)}
    chosen: list[StockAllocationView] = []
    for allocation_id in args.allocation_ids:
        found = allocations.get(allocation_id)
        if found is None:
            raise Rejection("UNKNOWN_ENTITY", f"allocation {allocation_id!r} does not exist")
        if found.resource_id != rid or found.service_target_id != target.target_id:
            raise Rejection(
                "INVALID_REQUEST",
                f"allocation {allocation_id} commits {found.resource_id} to"
                f" {found.service_target_id}, not {rid} to {target.target_id}",
            )
        if found in chosen:
            raise Rejection("INVALID_REQUEST", f"allocation {allocation_id} is listed twice")
        chosen.append(found)
    committed = sum(a.remaining_quantity for a in chosen)
    if args.quantity > committed:
        raise Rejection(
            "INSUFFICIENT_STOCK",
            f"the named allocations commit {committed} undistributed {unit}; only committed,"
            " reserved stock is distributed",
            {"committed_quantity": committed},
        )
    original = find_target(repo.goal(ctx.conn, ctx.episode_id, 1), target.target_id) or target
    rec = stock_records(ctx.conn, ctx.episode_id)
    assert rec is not None
    done = distributed_quantity(rec.distributions, target_id=target.target_id)
    if args.quantity > original.quantity - done:
        raise Rejection(
            "CONSTRAINT_VIOLATION",
            f"{done} of the original {original.quantity} {unit} are already distributed;"
            f" {args.quantity} more exceed the target",
        )
    capacity = capacity_at(rec, target, ctx.now)
    if args.quantity > capacity:
        raise Rejection(
            "THROUGHPUT_EXCEEDED",
            f"staffed service with committed stock supports {capacity} more {unit} by"
            f" {local_label(ctx.now)}; {args.quantity} were stated",
            {"capacity_quantity": capacity},
        )
    stock = _stock(ctx)
    before = _balance(stock, rid)
    on_time = ctx.now <= original.deadline
    distribution_id = f"dist_{repo.next_seq(ctx.conn, ctx.episode_id, 'distribution'):04d}"
    timing = "on time" if on_time else f"after the {local_label(original.deadline)} deadline"
    rev = handlers._bump(
        ctx,
        "stock_distributed",
        distribution_id,
        f"Staff recorded distribution {args.distribution_reference}: {args.quantity} {unit} of"
        f" {rid} for {target.target_id} at {local_label(ctx.now)} ({timing})",
    )
    left = args.quantity
    changes: list[StateChange] = []
    for allocation in chosen:
        used = min(left, allocation.remaining_quantity)
        if used == 0:
            continue
        ctx.conn.execute(
            "UPDATE stock_allocations SET remaining_quantity = remaining_quantity - ?"
            " WHERE episode_id = ? AND allocation_id = ?",
            (used, ctx.episode_id, allocation.allocation_id),
        )
        changes.append(
            StateChange(
                entity_id=allocation.allocation_id,
                field="remaining_quantity",
                before=allocation.remaining_quantity,
                after=allocation.remaining_quantity - used,
            )
        )
        left -= used
    repo.append_stock_movement(
        ctx.conn,
        ctx.episode_id,
        at=ctx.now,
        resource_id=rid,
        kind="distribution",
        quantity=args.quantity,
        revision=rev,
        reference=args.distribution_reference,
        receipt_id=ctx.receipt_id,
    )
    record = DistributionView(
        distribution_id=distribution_id,
        distribution_reference=args.distribution_reference,
        resource_id=rid,
        service_target_id=target.target_id,
        activity_id=activity.activity_id,
        quantity=args.quantity,
        unit=unit,
        goal_version=goal.version,
        allocation_ids=tuple(a.allocation_id for a in chosen),
        at=ctx.now,
        on_time=on_time,
        actor_id=ctx.actor_id,
        receipt_id=ctx.receipt_id or "",
        revision=rev,
    )
    repo.insert_distribution(ctx.conn, ctx.episode_id, record)
    changes[:0] = [
        StateChange(
            entity_id=rid,
            field="on_hand_quantity",
            before=before.on_hand_quantity,
            after=before.on_hand_quantity - args.quantity,
        ),
        StateChange(
            entity_id=target.target_id,
            field="distributed_quantity",
            before=done,
            after=done + args.quantity,
        ),
    ]
    changes.append(
        StateChange(entity_id=distribution_id, field="distribution", before=None, after=rid)
    )
    return Outcome(
        data={"distribution": record.model_dump(mode="json")},
        summary=(
            f"Recorded {args.quantity} {unit} distributed for {target.target_id} at"
            f" {local_label(ctx.now)} ({timing})"
        ),
        state_changes=changes,
    )
