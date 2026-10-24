"""Consumable stock and service accounting through the real store and executor (W2.3).

Each test names the M2 check of ``PEEAI_plan/waves/02_adaptation.md`` it covers:

* Stock and service accounting: the 24/16 to 40/0 handoff conserves stock; the target stays
  40; receipt and commitment do not reduce the service deficit; only distribution records
  achieved service.
* Quantity failure checks: overlapping and non-overlapping double allocation reject;
  release/expiry create no stock; a duplicate physical record cannot credit twice; a partial
  handoff preserves its residual reservation; early distribution cannot exceed attended
  throughput; late records keep their truthful times and fail on-time attainment.
* Staff boundary: the agent cannot call the staff-only tools; without staff attestation no
  physical success happens.
"""

from __future__ import annotations

import sqlite3

import pytest

from plan_b.domain.models import STAFF_TOOLS, ToolEnvelope
from plan_b.domain.timeutil import fmt_ts
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import baseline_policy_factory, tick_loop
from plan_b.store.database import Database
from tests.test_pantry_fixture import PantrySandbox, error_code, pt


@pytest.fixture
def pantry(db: Database) -> PantrySandbox:
    return PantrySandbox(db)


def _hold_id(env: object) -> str:
    data = getattr(env, "data", None)
    assert data is not None, getattr(env, "error", None)
    return str(data["hold"]["hold_id"])


# ---------------------------------------------------------------------------
# Stock and service accounting
# ---------------------------------------------------------------------------


def test_counters_follow_the_planned_table_exactly(pantry: PantrySandbox) -> None:
    """The five rows of the plan's counter table: supply gap and unfulfilled target stay
    separate, and reservation, receipt and commitment never touch the unfulfilled count."""
    assert pantry.balances() == {"pantry_stock": (24, 0, 24), "partner_stock": (16, 0, 16)}
    assert pantry.counters() == (16, 40)  # initial: max(40 - 24, 0) and 40 - 0
    hold = pantry.hold_partner("k-hold-partner")
    assert hold.status == "succeeded", hold.error
    assert pantry.balances()["partner_stock"] == (16, 16, 0)  # held: moves nothing
    assert pantry.counters() == (16, 40)
    received = pantry.handoff("k-handoff", _hold_id(hold))
    assert received.status == "succeeded", received.error
    assert pantry.balances() == {"pantry_stock": (40, 0, 40), "partner_stock": (0, 0, 0)}
    assert pantry.counters() == (0, 40)  # handoff complete: supply gap closed, nothing served
    assert pantry.hold_pantry("k-hold-pantry", 40).status == "succeeded"
    assert pantry.apply_best("k-apply").status == "succeeded"
    assert pantry.balances()["pantry_stock"] == (40, 40, 0)
    assert pantry.counters() == (0, 40)  # all 40 committed, none distributed
    pantry.advance_to("13:40")
    dist = pantry.distribute("k-dist", 40)
    assert dist.status == "succeeded", dist.error
    assert pantry.counters() == (0, 0)  # staff-confirmed distribution of 40 by the deadline
    assert pantry.balances() == {"pantry_stock": (0, 0, 0), "partner_stock": (0, 0, 0)}
    stock = pantry.view().stock
    assert stock is not None
    service = stock.service[0]
    assert (service.original_quantity, service.target_quantity) == (40, 40)
    assert (service.on_time_quantity, service.attained) == (40, True)
    # The expected 20 never entered the equation and is still unreceived.
    assert [(s.shipment.shipment_id, s.outstanding_quantity) for s in stock.expected_shipments] == [
        ("S20", 20)
    ]
    assert pantry.conserved()


def test_handoff_conserves_stock_in_one_atomic_revision(pantry: PantrySandbox) -> None:
    hold = pantry.hold_partner("k-hold")
    revision = pantry.revision()
    env = pantry.handoff("k-handoff", _hold_id(hold))
    assert env.receipt is not None and env.receipt.status == "applied"
    assert (env.receipt.revision_before, env.receipt.revision_after) == (revision, revision + 1)
    changes = {(c.entity_id, c.field): (c.before, c.after) for c in env.receipt.state_changes}
    assert changes[("partner_stock", "on_hand_quantity")] == (16, 0)
    assert changes[("pantry_stock", "on_hand_quantity")] == (24, 40)
    assert changes[(_hold_id(hold), "status")] == ("active", "fulfilled")
    stock = pantry.view().stock
    assert stock is not None
    total = sum(b.on_hand_quantity for b in stock.balances)
    assert total == 40  # 24 + 16 becomes 40 + 0
    for b in stock.balances:
        assert b.on_hand_quantity == (
            b.opening_quantity
            + b.received_quantity
            - b.transferred_out_quantity
            - b.distributed_quantity
        )
    moves = [(m.resource_id, m.kind, m.delta, m.revision) for m in stock.movements]
    assert moves[-2:] == [
        ("partner_stock", "transfer_out", -16, revision + 1),
        ("pantry_stock", "receipt", 16, revision + 1),
    ]
    # An internal handoff never touches the unrelated expected shipment.
    assert stock.expected_shipments[0].shipment.received_quantity == 0
    assert stock.receipts[0].kind == "internal_handoff"
    assert stock.handoff_tasks[0].status == "fulfilled"


def test_apply_converts_holds_without_double_counting(pantry: PantrySandbox) -> None:
    pantry.handoff("k-handoff", _hold_id(pantry.hold_partner("k-hold")))
    pantry.hold_pantry("k-hold-pantry", 40)
    stock = pantry.view().stock
    assert stock is not None and stock.balances[0].held_quantity == 40
    applied = pantry.apply_best("k-apply")
    assert applied.data is not None and applied.data["allocation_ids"] == ["alloc_0001"]
    stock = pantry.view().stock
    assert stock is not None
    pool = stock.balances[0]
    assert (pool.held_quantity, pool.committed_quantity, pool.reserved_quantity) == (0, 40, 40)
    assert stock.allocations[0].remaining_quantity == 40
    hold = next(h for h in pantry.view().holds if h.resource_id == "pantry_stock")
    assert (hold.effective_status, hold.remaining_quantity) == ("committed", 0)
    # A committed allocation is not released through release_hold.
    released = pantry.agent.call(
        "release_hold",
        arguments={"hold_id": hold.hold_id, "reason": "test"},
        idempotency_key="k-release",
        expected_revision=pantry.revision(),
    )
    assert error_code(released) == "HOLD_CONVERTED"


# ---------------------------------------------------------------------------
# Quantity failure checks
# ---------------------------------------------------------------------------


def test_overlapping_and_non_overlapping_double_allocation_reject(pantry: PantrySandbox) -> None:
    first = pantry.hold_pantry(
        "k-first",
        24,
        window={"start": "2026-11-09T13:00:00-05:00", "end": "2026-11-09T13:20:00-05:00"},
    )
    assert first.status == "succeeded", first.error
    overlapping = pantry.hold_pantry(
        "k-overlap",
        1,
        window={"start": "2026-11-09T13:10:00-05:00", "end": "2026-11-09T13:30:00-05:00"},
    )
    later = pantry.hold_pantry(
        "k-later",
        1,
        window={"start": "2026-11-09T13:20:00-05:00", "end": "2026-11-09T13:40:00-05:00"},
    )
    assert error_code(overlapping) == "INSUFFICIENT_STOCK"
    assert error_code(later) == "INSUFFICIENT_STOCK"  # a later slot does not renew the kits
    assert pantry.balances()["pantry_stock"] == (24, 24, 0)
    # The rejected receipts changed nothing.
    for env in (overlapping, later):
        assert env.receipt is not None and env.receipt.state_changes == ()
        assert env.receipt.revision_before == env.receipt.revision_after


def test_overdraw_unit_and_quantity_shape_are_refused(pantry: PantrySandbox) -> None:
    assert error_code(pantry.hold_pantry("k-over", 25)) == "INSUFFICIENT_STOCK"
    assert error_code(pantry.hold_partner("k-over-p", 17)) == "INSUFFICIENT_STOCK"
    for bad in (0, -3, 2.5, "16"):
        env = pantry.hold_pantry(f"k-bad-{bad}", bad)  # type: ignore[arg-type]
        assert error_code(env) == "INVALID_REQUEST"
    hold = pantry.hold_partner("k-hold")
    for bad in (16.0, "16", -1):
        env = pantry.handoff(f"k-r-{bad}", _hold_id(hold), quantity=bad)  # type: ignore[arg-type]
        assert error_code(env) == "INVALID_REQUEST"
    wrong_unit = pantry.handoff("k-unit", _hold_id(hold), unit="family_box")
    assert error_code(wrong_unit) == "UNIT_MISMATCH"
    too_many = pantry.handoff("k-many", _hold_id(hold), quantity=17)
    assert error_code(too_many) == "INSUFFICIENT_STOCK"
    assert pantry.balances() == {"pantry_stock": (24, 0, 24), "partner_stock": (16, 16, 0)}
    assert pantry.count("stock_receipts") == 0


def test_release_and_expiry_create_no_stock(pantry: PantrySandbox) -> None:
    held = pantry.hold_pantry("k-hold", 24, hold_minutes=5)
    assert pantry.balances()["pantry_stock"] == (24, 24, 0)
    released = pantry.agent.call(
        "release_hold",
        arguments={"hold_id": _hold_id(held), "reason": "test release"},
        idempotency_key="k-release",
        expected_revision=pantry.revision(),
    )
    assert released.status == "succeeded", released.error
    assert pantry.balances()["pantry_stock"] == (24, 0, 24)  # the claim ends; nothing is added
    again = pantry.agent.call(
        "release_hold",
        arguments={"hold_id": _hold_id(held), "reason": "again"},
        idempotency_key="k-release-2",
        expected_revision=pantry.revision(),
    )
    assert error_code(again) == "HOLD_NOT_ACTIVE"
    partner = pantry.hold_partner("k-hold-partner")
    assert pantry.balances()["partner_stock"] == (16, 16, 0)
    pantry.advance_to("12:50")  # the transfer hold never outlives the 12:50 handoff cutoff
    hold = next(h for h in pantry.view().holds if h.hold_id == _hold_id(partner))
    assert hold.effective_status == "expired" and hold.remaining_quantity == 16
    assert pantry.balances() == {"pantry_stock": (24, 0, 24), "partner_stock": (16, 0, 16)}
    late = pantry.handoff("k-late", hold.hold_id)
    assert error_code(late) == "HOLD_EXPIRED"
    stock = pantry.view().stock
    assert stock is not None and stock.handoff_tasks[0].status == "lapsed"
    assert [m.kind for m in stock.movements] == ["opening", "opening"]
    assert pantry.conserved()


def test_duplicate_physical_records_cannot_credit_twice(pantry: PantrySandbox) -> None:
    hold = pantry.hold_partner("k-hold", 16)
    first = pantry.handoff("k-handoff", _hold_id(hold), 8, reference="handoff_A")
    assert first.status == "succeeded"
    # The same request again is an idempotent replay of the original receipt.
    replay = pantry.staff.call(
        "record_stock_receipt",
        arguments={
            "resource_id": "pantry_stock",
            "quantity": 8,
            "unit": "standard_kit",
            "source_observation_id": "obs_partner_stock",
            "receipt_reference": "handoff_A",
            "source_resource_id": "partner_stock",
            "source_hold_id": _hold_id(hold),
        },
        idempotency_key="k-handoff",
        expected_revision=first.receipt.revision_before if first.receipt else 0,
    )
    assert replay.replayed_receipt and replay.receipt == first.receipt
    # The same physical receipt under a fresh request key is refused and credits nothing.
    fresh = pantry.handoff("k-handoff-fresh", _hold_id(hold), 8, reference="handoff_A")
    assert error_code(fresh) == "DUPLICATE_REFERENCE"
    assert pantry.balances() == {"pantry_stock": (32, 0, 32), "partner_stock": (8, 8, 0)}
    # A distinct physical record of the rest is accepted once.
    assert (
        pantry.handoff("k-handoff-b", _hold_id(hold), 8, reference="handoff_B").status
        == "succeeded"
    )
    assert pantry.balances() == {"pantry_stock": (40, 0, 40), "partner_stock": (0, 0, 0)}
    pantry.hold_pantry("k-hold-pantry", 40)
    pantry.apply_best("k-apply")
    pantry.advance_to("13:40")
    assert pantry.distribute("k-dist", 30, reference="dist_A").status == "succeeded"
    dup = pantry.distribute("k-dist-fresh", 10, reference="dist_A")
    assert error_code(dup) == "DUPLICATE_REFERENCE"
    stock = pantry.view().stock
    assert stock is not None
    assert (stock.service[0].distributed_quantity, len(stock.distributions)) == (30, 1)
    # The database refuses a second physical record with the same reference by itself.
    with pantry.db.write() as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO stock_receipts SELECT episode_id, 'srec_9999', receipt_reference, kind,"
            " resource_id, source_resource_id, source_hold_id, shipment_id, quantity, unit,"
            " source_observation_id, at, actor_id, receipt_id, revision FROM stock_receipts"
            " WHERE episode_id = ? LIMIT 1",
            (pantry.episode_id,),
        )


def test_partial_handoff_preserves_the_residual_reservation(pantry: PantrySandbox) -> None:
    hold = pantry.hold_partner("k-hold", 16)
    env = pantry.handoff("k-partial", _hold_id(hold), 10)
    assert env.data is not None and env.data["hold_status"] == "active"
    assert pantry.balances() == {"pantry_stock": (34, 0, 34), "partner_stock": (6, 6, 0)}
    view = pantry.view()
    residual = next(h for h in view.holds if h.hold_id == _hold_id(hold))
    assert (residual.effective_status, residual.quantity, residual.remaining_quantity) == (
        "active",
        16,
        6,
    )
    assert view.stock is not None and view.stock.handoff_tasks[0].status == "partially_fulfilled"
    # The six are still reserved: not available twice and not counted as received.
    assert error_code(pantry.hold_partner("k-again", 1)) == "INSUFFICIENT_STOCK"
    assert view.stock.service[0].supply_gap_quantity == 6
    # Distributing the available 34 leaves a six-kit deficit against the unchanged target.
    assert pantry.hold_pantry("k-hold-34", 34).status == "succeeded"
    assert pantry.apply_best("k-apply").status == "succeeded"
    released = pantry.agent.call(
        "release_hold",
        arguments={"hold_id": _hold_id(hold), "reason": "the plan no longer needs it"},
        idempotency_key="k-release",
        expected_revision=pantry.revision(),
    )
    assert released.status == "succeeded"
    assert pantry.balances()["partner_stock"] == (6, 0, 6)  # release creates no stock
    pantry.advance_to("13:40")
    assert pantry.distribute("k-dist", 34).status == "succeeded"
    stock = pantry.view().stock
    assert stock is not None
    s = stock.service[0]
    assert (s.original_quantity, s.on_time_quantity, s.unfulfilled_quantity, s.attained) == (
        40,
        34,
        6,
        False,
    )
    assert pantry.conserved()


def test_early_distribution_cannot_exceed_attended_throughput(pantry: PantrySandbox) -> None:
    pantry.committed_40()
    pantry.advance_to("13:10")  # ten staffed minutes with committed stock since 13:00
    stock = pantry.view().stock
    assert stock is not None and stock.service[0].capacity_quantity == 10
    too_many = pantry.distribute("k-11", 11, reference="dist_early_11")
    assert error_code(too_many) == "THROUGHPUT_EXCEEDED"
    assert pantry.distribute("k-10", 10, reference="dist_early_10").status == "succeeded"
    assert (
        error_code(pantry.distribute("k-1", 1, reference="dist_early_1")) == "THROUGHPUT_EXCEEDED"
    )
    pantry.advance_to("13:40")
    assert pantry.distribute("k-30", 30, reference="dist_rest").status == "succeeded"
    stock = pantry.view().stock
    assert stock is not None and stock.service[0].on_time_quantity == 40


def test_a_late_commitment_cannot_backdate_throughput(pantry: PantrySandbox) -> None:
    """Distribution starts at 13:00 without committed stock; the commitment lands at 13:11.
    Staff throughput accrues only from then, so by 13:40 at most 29 of the 40 committed kits can
    be distributed on time; the rest can only be served late."""
    pantry.handoff("k-handoff", _hold_id(pantry.hold_partner("k-hold")))
    pantry.advance_to("13:09")
    view = pantry.view()
    assert {a.definition.activity_id: a.lifecycle for a in view.activities}["distribution"] == (
        "started"
    )
    assert pantry.hold_pantry("k-hold-late", 40).status == "succeeded"  # executes at 13:10
    env = pantry.evaluate()
    assert env.data is not None
    best = next(
        c for c in env.data["candidates"] if c["candidate_id"] == env.data["best_candidate_id"]
    )
    coverage = best["service_coverage"][0]
    assert (coverage["allocated_quantity"], coverage["on_time_quantity"]) == (40, 29)
    assert coverage["unfulfilled_quantity"] == 11
    assert pantry.apply_best("k-apply").status == "succeeded"  # executes at 13:11
    pantry.advance_to("13:40")
    stock = pantry.view().stock
    assert stock is not None and stock.service[0].capacity_quantity == 29
    assert error_code(pantry.distribute("k-40", 40, reference="d40")) == "THROUGHPUT_EXCEEDED"
    assert pantry.distribute("k-29", 29, reference="d29").status == "succeeded"
    pantry.advance_to("13:51")
    assert pantry.distribute("k-11", 11, reference="d11").status == "succeeded"  # served late
    stock = pantry.view().stock
    assert stock is not None
    s = stock.service[0]
    assert (s.on_time_quantity, s.late_quantity, s.unfulfilled_quantity) == (29, 11, 11)


def test_late_records_keep_their_times_and_fail_on_time_attainment(pantry: PantrySandbox) -> None:
    pantry.committed_40()
    pantry.advance_to("13:45")  # after the 13:40 deadline, inside the event and staff grant
    late = pantry.distribute("k-late", 40, reference="dist_late")
    assert late.status == "succeeded", late.error
    stock = pantry.view().stock
    assert stock is not None
    record = stock.distributions[0]
    assert (record.at, record.on_time) == (pt("13:45"), False)
    s = stock.service[0]
    assert (s.distributed_quantity, s.on_time_quantity, s.late_quantity) == (40, 0, 40)
    assert (s.unfulfilled_quantity, s.attained) == (40, False)
    assert stock.balances[0].on_hand_quantity == 0  # physical stock still moved truthfully
    assert late.receipt is not None and late.receipt.executed_at == pt("13:45")


def test_external_receipt_reconciles_its_shipment_once(pantry: PantrySandbox) -> None:
    def receive(key: str, quantity: int, reference: str) -> ToolEnvelope:
        return pantry.staff.call(
            "record_stock_receipt",
            arguments={
                "resource_id": "pantry_stock",
                "quantity": quantity,
                "unit": "standard_kit",
                "source_observation_id": "obs_pantry_stock",
                "receipt_reference": reference,
                "shipment_id": "S20",
            },
            idempotency_key=key,
            expected_revision=pantry.revision(),
        )

    first = receive("k-s20-a", 12, "S20_box_1")
    assert first.status == "succeeded"
    stock = pantry.view().stock
    assert stock is not None
    assert stock.expected_shipments[0].shipment.received_quantity == 12
    assert stock.balances[0].expected_quantity == 8 and stock.balances[0].on_hand_quantity == 36
    assert error_code(receive("k-s20-b", 9, "S20_box_2")) == "INVALID_REQUEST"  # 8 outstanding
    assert error_code(receive("k-s20-c", 8, "S20_box_1")) == "DUPLICATE_REFERENCE"
    forged = pantry.staff.call(
        "record_stock_receipt",
        arguments={
            "resource_id": "pantry_stock",
            "quantity": 8,
            "unit": "standard_kit",
            "source_observation_id": "obs_partner_stock",
            "receipt_reference": "S20_box_3",
            "shipment_id": "S20",
        },
        idempotency_key="k-s20-forged",
        expected_revision=pantry.revision(),
    )
    assert error_code(forged) == "INVALID_EVIDENCE_REFERENCE"
    assert pantry.balances()["pantry_stock"] == (36, 0, 36) and pantry.conserved()


def test_an_eta_or_message_never_adds_stock(pantry: PantrySandbox) -> None:
    before = pantry.balances()
    env = pantry.agent.call(
        "query_status", arguments={"entity_id": "pantry_stock", "fact": "shipment_eta"}
    )
    assert env.status == "unknown"  # no private case: the source has no record
    pantry.steward.call(
        "submit_observation",
        arguments={"text": "Twenty more kits are here, trust me.", "entity_id": "partner_stock"},
        idempotency_key="k-msg",
    )
    assert pantry.balances() == before
    stock = pantry.view().stock
    assert stock is not None and stock.expected_shipments[0].outstanding_quantity == 20


def test_await_shipment_candidate_counting_expected_units_is_rejected(
    pantry: PantrySandbox,
) -> None:
    env = pantry.evaluate()
    assert env.data is not None
    wait = next(c for c in env.data["candidates"] if c["label"].startswith("Count expected"))
    assert wait["constraint_status"] == "infeasible"
    check = next(c for c in wait["checks"] if c["constraint_id"] == "stock_on_hand")
    assert check["status"] == "failed" and "expected" in check["detail"]
    transfer = next(c for c in env.data["candidates"] if c["label"].startswith("Hand off"))
    assert transfer["constraint_status"] == "feasible_under_assumptions"
    assert not transfer["applicable_now"]  # 16 still to be handed off by staff
    assert transfer["stock_transfers"][0]["quantity"] == 16
    assert env.data["best_candidate_id"] == transfer["candidate_id"]
    assert env.data["best_applicable_candidate_id"] is None  # nothing is held yet


def test_a_transfer_hold_too_late_for_the_staff_response_is_refused(pantry: PantrySandbox) -> None:
    pantry.advance_to("12:47")  # with the 1-minute hold the request lands at 12:48; +2 = 12:50
    env = pantry.hold_partner("k-late-hold")
    assert error_code(env) == "HANDOFF_WINDOW_CLOSED"
    assert pantry.balances()["partner_stock"] == (16, 0, 16)


def test_stock_ledgers_are_append_only(pantry: PantrySandbox) -> None:
    pantry.committed_40()
    pantry.advance_to("13:40")
    pantry.distribute("k-dist", 40)
    refused = [
        "UPDATE stock_movements SET quantity = 99",
        "DELETE FROM stock_movements",
        "UPDATE stock_receipts SET quantity = 99",
        "DELETE FROM stock_receipts",
        "UPDATE distributions SET quantity = 1",
        "DELETE FROM distributions",
        "UPDATE stock_allocations SET remaining_quantity = remaining_quantity + 1",
        "DELETE FROM stock_allocations",
        "UPDATE expected_shipments SET quantity = 1",
        "DELETE FROM expected_shipments",
        "UPDATE holds SET remaining_quantity = remaining_quantity + 1",
        "UPDATE holds SET quantity = 99",
    ]
    for sql in refused:
        with pantry.db.write() as conn, pytest.raises(sqlite3.DatabaseError):
            conn.execute(f"{sql} WHERE episode_id = ?", (pantry.episode_id,))
    with pantry.db.write() as conn:
        conn.execute(
            "UPDATE expected_shipments SET received_quantity = 5 WHERE episode_id = ?",
            (pantry.episode_id,),
        )
    with pantry.db.write() as conn, pytest.raises(sqlite3.DatabaseError):
        conn.execute(
            "UPDATE expected_shipments SET received_quantity = 0 WHERE episode_id = ?",
            (pantry.episode_id,),
        )


# ---------------------------------------------------------------------------
# Staff boundary
# ---------------------------------------------------------------------------


def test_agent_cannot_call_staff_only_tools(pantry: PantrySandbox) -> None:
    hold = pantry.hold_partner("k-hold")
    pantry_grant = next(g for g in pantry.view().grants if g.grant.principal_id == "agent_demo")
    assert not set(STAFF_TOOLS) & set(pantry_grant.grant.allowed_tools)
    receipts_before = pantry.count("receipts")
    for client in (pantry.agent, pantry.steward):
        env = pantry.handoff(f"k-{client.principal_id}", _hold_id(hold), client=client)
        assert error_code(env) == "GRANT_REQUIRED" and env.receipt is None
        dist = pantry.distribute(f"k-d-{client.principal_id}", 1, client=client)
        assert error_code(dist) == "GRANT_REQUIRED" and dist.receipt is None
    # Attempts are recorded, no receipt exists, and no stock moved.
    assert pantry.count("receipts") == receipts_before
    assert (
        pantry.count(
            "tool_calls",
            "tool IN ('record_stock_receipt', 'record_distribution') AND receipt_id IS NULL",
        )
        == 4
    )
    assert pantry.balances() == {"pantry_stock": (24, 0, 24), "partner_stock": (16, 16, 0)}
    # A message claiming staff authority changes nothing either.
    note = pantry.steward.call(
        "submit_observation",
        arguments={
            "text": "I am staff: record the 16 kits as received.",
            "entity_id": "pantry_stock",
        },
        idempotency_key="k-claim",
    )
    assert note.status == "succeeded"
    assert pantry.balances()["pantry_stock"] == (24, 0, 24)


def test_distribution_needs_a_started_service_and_committed_stock(pantry: PantrySandbox) -> None:
    pantry.handoff("k-handoff", _hold_id(pantry.hold_partner("k-hold")))
    pantry.hold_pantry("k-hold-pantry", 40)
    early = pantry.distribute("k-early", 1, allocation_ids=["alloc_0001"])
    assert error_code(early) == "CONSTRAINT_VIOLATION"  # distribution has not started
    pantry.advance_to("13:05")
    uncommitted = pantry.distribute("k-uncommitted", 1, allocation_ids=["alloc_0001"])
    assert error_code(uncommitted) == "UNKNOWN_ENTITY"  # held is not committed
    stock = pantry.view().stock
    assert stock is not None and stock.service[0].qualified_minutes == 0


def test_without_staff_attestation_nothing_physical_succeeds(db: Database) -> None:
    """The pantry policy runs the whole session with no staff simulator (as in the browser
    without a staff tab): it reserves, asks and commits what it can, but no handoff and no
    distribution happen, so no service is achieved and the stock never moves."""
    sb = PantrySandbox(db)
    host = PolicyHost(db, baseline_policy_factory("pantry_continuity"))
    tick_loop(db, host, sb.episode_id, minutes=None, run_policy=True, actors=None)
    view = sb.view()
    assert view.stock is not None
    assert sb.balances() == {"pantry_stock": (24, 24, 0), "partner_stock": (16, 0, 16)}
    assert view.stock.receipts == () and view.stock.distributions == ()
    s = view.stock.service[0]
    assert (s.on_time_quantity, s.unfulfilled_quantity, s.attained) == (0, 40, False)
    assert view.stock.handoff_tasks[0].status == "lapsed"
    kinds = [d.kind for d in view.decisions]
    assert "ask" in kinds and "infeasible" in kinds and "commit" in kinds
    assert all(r.tool not in STAFF_TOOLS for r in view.receipts)
    assert sb.conserved()
    assert fmt_ts(view.clock) == "2026-11-09T19:00:00Z"
