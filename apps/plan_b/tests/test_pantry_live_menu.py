"""The live (P2) policy's pantry stock options, against the real store and executor.

Menu guards (``plan_b/agent/menu.py``: ``handoff_quantity``, ``stock_hold_quantity``,
``own_transfer_holds``, ``_stock_options``, ``_release_options``, ``stock_improvable``) are
checked on pantry_dev01 states built through ``PantrySandbox`` and a real ``EvaluationResult``;
where the fixture cannot reach a boundary through tools, one field of the real view or
candidate is changed with ``model_copy``. The ``LivePolicy`` paths built on them (the plan
reopened by ``stock_improvable``, the server-chosen wait for an awaited staff handoff, the wake
at the staff response or cutoff, a rejected handoff kept out of the run's later menus) run P2
with a scripted provider (``tests.test_live_workflow.build``): nothing reaches the network and
spend goes to a tmp ledger. Two hidden-world variants of pantry_dev01 (a status desk that cannot
be reached) live in a scratch copy of the private cases.

Each test names the mutation it catches.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import plan_b.world.world as world
from plan_b.agent.interpret import INTERPRET_SCHEMA_NAME
from plan_b.agent.menu import (
    MenuInputs,
    awaited_handoffs,
    build_menu,
    handoff_quantity,
    own_grant,
    own_transfer_holds,
    stock_hold_quantity,
    stock_improvable,
    unfulfilled,
)
from plan_b.domain.models import (
    CandidateResult,
    EvaluationResult,
    EventStateView,
    PolicyDecision,
    PolicyRunResult,
)
from plan_b.store.database import Database
from tests.test_agent_provider import FakeOpener, ScriptedModel, menu_ids, schema_name, state_of
from tests.test_live_workflow import build
from tests.test_pantry_fixture import PantrySandbox, pt

AGENT = "agent_demo"
PAIR = "handoff:partner_stock:pantry_stock:"
HANDOFF_16 = f"{PAIR}16"
POOL_24 = "hold:pantry_stock:kits_40:24"
SHORT_WINDOW = {"start": "2026-11-09T13:00:00-05:00", "end": "2026-11-09T13:30:00-05:00"}


# ---------------------------------------------------------------------------------- helpers


def evaluated(sb: PantrySandbox) -> tuple[EventStateView, EvaluationResult]:
    env = sb.evaluate()
    assert env.status == "succeeded" and env.data is not None, env.error
    return sb.view(), EvaluationResult.model_validate(env.data)


def by_label(ev: EvaluationResult, prefix: str) -> CandidateResult:
    return next(c for c in ev.candidates if c.label.startswith(prefix))


def handoff_candidate(ev: EvaluationResult) -> CandidateResult:
    return by_label(ev, "Hand off partner_stock into pantry_stock")


def allocate_candidate(ev: EvaluationResult) -> CandidateResult:
    return by_label(ev, "Allocate pantry_stock")


def keep_candidate(ev: EvaluationResult) -> CandidateResult:
    return next(c for c in ev.candidates if c.candidate_id == ev.keep_candidate_id)


def scope_of(view: EventStateView) -> tuple[set[str], set[str]]:
    grant = own_grant(view, AGENT)
    assert grant is not None
    return set(grant.grant.resource_ids), set(grant.grant.activity_ids)


def inputs(now: datetime) -> MenuInputs:
    return MenuInputs(principal=AGENT, now=now)


def menu(
    view: EventStateView, ev: EvaluationResult, now: datetime | None = None, **kw: Any
) -> tuple[str, ...]:
    return build_menu(view, ev, MenuInputs(principal=AGENT, now=now or view.clock, **kw)).ids


def with_available(view: EventStateView, pool: str, available: int) -> EventStateView:
    stock = view.stock
    assert stock is not None
    balances = tuple(
        b.model_copy(update={"available_quantity": available}) if b.resource_id == pool else b
        for b in stock.balances
    )
    return view.model_copy(update={"stock": stock.model_copy(update={"balances": balances})})


def with_grant(view: EventStateView, **update: Any) -> EventStateView:
    grants = tuple(
        g.model_copy(update={"grant": g.grant.model_copy(update=update)})
        if g.grant.principal_id == AGENT
        else g
        for g in view.grants
    )
    return view.model_copy(update={"grants": grants})


def with_candidate(ev: EvaluationResult, cand: CandidateResult) -> EvaluationResult:
    candidates = tuple(cand if c.candidate_id == cand.candidate_id else c for c in ev.candidates)
    return ev.model_copy(update={"candidates": candidates})


def everyone(c: CandidateResult) -> bool:
    return True


def chooser(*prefixes: str) -> ScriptedModel:
    """A scripted P2 chooser: the first option whose id starts with the earliest listed prefix,
    else ``wait``."""

    def choose(body: dict[str, Any]) -> dict[str, Any]:
        ids = menu_ids(body)
        cited = [r["tool_call_id"] for r in state_of(body)["last_tool_results"]]
        for prefix in prefixes:
            for option_id in ids:
                if option_id.startswith(prefix):
                    return {
                        "option_id": option_id,
                        "rationale": f"Scripted preference {prefix!r}.",
                        "cited_refs": cited,
                    }
        return {"option_id": "wait", "rationale": "Nothing scripted applies.", "cited_refs": cited}

    return ScriptedModel(choose=choose)


def run_p2(
    sb: PantrySandbox, tmp_path: Path, model: ScriptedModel
) -> tuple[Any, PolicyRunResult, FakeOpener]:
    policy, opener = build("P2", tmp_path, model, max_model_calls=12)
    return policy, policy.run(sb.agent, max_tool_calls=40), opener


def choice_menus(opener: FakeOpener) -> list[list[str]]:
    return [menu_ids(b) for b in opener.bodies if schema_name(b) != INTERPRET_SCHEMA_NAME]


def rejected(decisions: tuple[PolicyDecision, ...]) -> list[PolicyDecision]:
    return [d for d in decisions if d.details.get("outcome") == "rejected"]


@pytest.fixture
def scratch_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[str, Callable[[dict[str, Any]], None]], str]]:
    """A scratch copy of the private cases; ``make(name, mutate)`` writes a pantry_dev01 variant
    named ``name`` and returns its case ref."""
    private = tmp_path / "private"
    shutil.copytree(world.PRIVATE_DIR, private)
    monkeypatch.setattr(world, "PRIVATE_DIR", private)
    world.load_case.cache_clear()

    def make(name: str, mutate: Callable[[dict[str, Any]], None]) -> str:
        case = json.loads((private / "pantry_dev01.json").read_text())
        case["case_ref"] = name
        mutate(case)
        (private / f"{name}.json").write_text(json.dumps(case))
        return name

    yield make
    world.load_case.cache_clear()


def partner_desk_unreachable(case: dict[str, Any]) -> None:
    """The partner steward desk cannot be reached: a stock-transfer hold on partner_stock is
    refused at execution (``STATUS_UNAVAILABLE``), which the visible state does not show."""
    record = next(r for r in case["status_model"] if r["entity_id"] == "partner_stock")
    record.update(outcome="unavailable", response=None)


def supplier_desk_down_from_1233(case: dict[str, Any]) -> None:
    """From 12:33 the pantry supplier desk cannot be reached: the S20 status read at 12:32 still
    succeeds, a later pantry_stock hold is refused at execution (``STATUS_UNAVAILABLE``)."""
    case["status_model"].append(
        {
            "entity_id": "pantry_stock",
            "fact": "shipment_eta",
            "available_from": "2026-11-09T12:33:00-05:00",
            "outcome": "unavailable",
            "response": None,
        }
    )


# ---------------------------------------------------------------------------------- E2


def test_a_partial_handoff_request_is_the_one_request_for_its_pool_pair(db: Database) -> None:
    """Catches: dropping the ``own_transfer_holds`` rule from ``handoff_quantity`` (a second
    request for the 8 outstanding units would be offered beside the first), or counting only
    live holds in it (the pair would be offered again once the request is released)."""
    sb = PantrySandbox(db, "pantry_dev01")
    held = sb.hold_partner("partial-8", quantity=8)
    assert held.status == "succeeded" and held.data is not None, held.error
    hold_id = held.data["hold"]["hold_id"]
    view, ev = evaluated(sb)
    need = handoff_candidate(ev).stock_transfers[0]
    scope, activities = scope_of(view)
    now = inputs(view.clock)
    # Units remain to hand off and the source has them; only the earlier request blocks.
    assert (need.quantity, need.held_quantity, need.bound_hold_ids) == (16, 8, ())
    assert sb.balances()["partner_stock"] == (16, 8, 8)
    assert [h.hold_id for h in own_transfer_holds(view, AGENT, need)] == [hold_id]
    assert handoff_quantity(view.model_copy(update={"holds": ()}), now, scope, activities, need)
    assert handoff_quantity(view, now, scope, activities, need) == 0
    assert not [i for i in menu(view, ev) if i.startswith(PAIR)]
    # Released, the request still counts: one request per pair, whatever became of it.
    released = sb.agent.call(
        "release_hold",
        arguments={"hold_id": hold_id, "reason": "test: the partial request is withdrawn"},
        idempotency_key="release-partial-8",
        expected_revision=sb.revision(),
    )
    assert released.status == "succeeded", released.error
    view, ev = evaluated(sb)
    need = handoff_candidate(ev).stock_transfers[0]
    assert (need.held_quantity, sb.balances()["partner_stock"]) == (0, (16, 0, 16))
    assert not [i for i in menu(view, ev) if i.startswith(PAIR)]


# ---------------------------------------------------------------------------------- E3


def test_a_handoff_is_offered_only_while_a_staff_answer_lands_inside_the_window(
    db: Database,
) -> None:
    """hold_resource takes 1 min and staff answer 2 min later; the window is 12:30-12:50 with an
    exclusive end. Catches: dropping or loosening (``>`` for ``>=``) the window-end check, or
    dropping the window-start check."""
    sb = PantrySandbox(db, "pantry_dev01")
    view, ev = evaluated(sb)
    # The fixture's need cutoff equals the window end; without it only the window decides.
    need = handoff_candidate(ev).stock_transfers[0].model_copy(update={"handoff_cutoff": None})
    scope, activities = scope_of(view)

    def quantity(hhmm: str) -> int:
        return handoff_quantity(view, inputs(pt(hhmm)), scope, activities, need)

    assert quantity("12:46") == 16  # the answer lands at 12:49
    assert quantity("12:47") == 0  # the answer would land at 12:50, when the window has closed
    assert quantity("12:29") == 16  # the request lands at 12:30, as the window opens
    assert quantity("12:28") == 0  # the request would land before the window opens
    assert HANDOFF_16 in menu(view, ev, pt("12:46"))
    assert not [i for i in menu(view, ev, pt("12:47")) if i.startswith(PAIR)]


def test_a_handoff_is_not_offered_when_the_answer_would_land_at_the_need_cutoff(
    db: Database,
) -> None:
    """Catches: dropping or loosening the ``need.handoff_cutoff`` check (here earlier than the
    window end, so only the cutoff decides)."""
    sb = PantrySandbox(db, "pantry_dev01")
    view, ev = evaluated(sb)
    scope, activities = scope_of(view)
    cand = handoff_candidate(ev)
    need = cand.stock_transfers[0]
    now = inputs(pt("12:30"))  # the request lands at 12:31, the answer at 12:33
    at_answer = need.model_copy(update={"handoff_cutoff": pt("12:33")})
    after_answer = need.model_copy(update={"handoff_cutoff": pt("12:34")})
    assert handoff_quantity(view, now, scope, activities, after_answer) == 16
    assert handoff_quantity(view, now, scope, activities, at_answer) == 0
    cut = with_candidate(ev, cand.model_copy(update={"stock_transfers": (at_answer,)}))
    assert HANDOFF_16 in menu(view, ev, pt("12:30"))
    assert not [i for i in menu(view, cut, pt("12:30")) if i.startswith(PAIR)]


def test_a_handoff_is_not_offered_when_the_source_has_fewer_units_than_the_need(
    db: Database,
) -> None:
    """Catches: dropping the source-availability check, or loosening it to a strict ``<``."""
    sb = PantrySandbox(db, "pantry_dev01")
    view, ev = evaluated(sb)
    scope, activities = scope_of(view)
    need = handoff_candidate(ev).stock_transfers[0]
    now = inputs(view.clock)
    exact, short = (
        with_available(view, "partner_stock", 16),
        with_available(view, "partner_stock", 15),
    )
    assert handoff_quantity(exact, now, scope, activities, need) == 16
    assert handoff_quantity(short, now, scope, activities, need) == 0
    assert HANDOFF_16 in menu(exact, ev)
    assert not [i for i in menu(short, ev) if i.startswith(PAIR)]
    # The pool hold of the allocation does not depend on the alternate pool.
    assert POOL_24 in menu(short, ev)


def test_a_handoff_needs_both_pools_and_the_activity_in_the_grant(db: Database) -> None:
    """Catches: dropping the source or destination scope check, or the activity check, of
    ``handoff_quantity``."""
    sb = PantrySandbox(db, "pantry_dev01")
    view, ev = evaluated(sb)
    scope, activities = scope_of(view)
    need = handoff_candidate(ev).stock_transfers[0]
    now = inputs(view.clock)
    assert {"pantry_stock", "partner_stock"} <= scope and "distribution" in activities
    assert handoff_quantity(view, now, scope, activities, need) == 16
    assert handoff_quantity(view, now, scope - {"partner_stock"}, activities, need) == 0
    assert handoff_quantity(view, now, scope - {"pantry_stock"}, activities, need) == 0
    assert handoff_quantity(view, now, scope, activities - {"distribution"}, need) == 0
    # Through the grant the menu reads: without the source in scope the handoff goes, the
    # pool hold stays; without the activity neither stock option is offered.
    no_source = with_grant(view, resource_ids=tuple(sorted(scope - {"partner_stock"})))
    no_activity = with_grant(view, activity_ids=tuple(sorted(activities - {"distribution"})))
    ids = menu(no_source, ev)
    assert not [i for i in ids if i.startswith(PAIR)] and POOL_24 in ids
    assert not [i for i in menu(no_activity, ev) if i.startswith((PAIR, "hold:"))]


def test_a_pool_hold_is_offered_only_for_available_units_of_an_unbound_requirement(
    db: Database,
) -> None:
    """Catches: dropping the availability check of ``stock_hold_quantity`` (or loosening it to
    ``<``), its bound-hold check, or its scope and activity checks."""
    sb = PantrySandbox(db, "pantry_dev01")
    view, ev = evaluated(sb)
    scope, activities = scope_of(view)
    rh = allocate_candidate(ev).required_stock_holds[0]
    assert (rh.resource_id, rh.quantity, rh.held_quantity, rh.bound_hold_ids) == (
        "pantry_stock",
        24,
        0,
        (),
    )
    exact, short = (
        with_available(view, "pantry_stock", 24),
        with_available(view, "pantry_stock", 23),
    )
    assert stock_hold_quantity(exact, scope, activities, rh) == 24
    assert stock_hold_quantity(short, scope, activities, rh) == 0
    assert POOL_24 in menu(exact, ev)
    assert not [i for i in menu(short, ev) if i.startswith("hold:")]
    bound = rh.model_copy(update={"bound_hold_ids": ("hold_9999",)})
    assert stock_hold_quantity(view, scope, activities, bound) == 0
    assert stock_hold_quantity(view, scope - {"pantry_stock"}, activities, rh) == 0
    assert stock_hold_quantity(view, scope, activities - {"distribution"}, rh) == 0
    # Once the agent holds the 24 units, the requirement is bound and no pool hold is offered.
    held = sb.hold_pantry("pool-24", 24)
    assert held.status == "succeeded" and held.data is not None, held.error
    view, ev = evaluated(sb)
    assert allocate_candidate(ev).required_stock_holds[0].bound_hold_ids == (
        held.data["hold"]["hold_id"],
    )
    assert not [i for i in menu(view, ev) if i.startswith("hold:")]


def test_a_candidate_with_pending_transfers_gets_no_pool_hold_option(db: Database) -> None:
    """The handoff candidate needs 40 pool units; with 40 available (one field of the real view
    changed) its pool hold could be placed. Catches: dropping the ``if c.stock_transfers:
    continue`` of ``_stock_options`` (``hold:pantry_stock:kits_40:40`` would be offered before
    the handoff is answered)."""
    sb = PantrySandbox(db, "pantry_dev01")
    view, ev = evaluated(sb)
    scope, activities = scope_of(view)
    cand = handoff_candidate(ev)
    assert cand.stock_transfers
    rh = cand.required_stock_holds[0]
    plenty = with_available(view, "pantry_stock", 40)
    assert rh.quantity == 40 and stock_hold_quantity(plenty, scope, activities, rh) == 40
    ids = menu(plenty, ev)
    assert HANDOFF_16 in ids and POOL_24 in ids
    assert "hold:pantry_stock:kits_40:40" not in ids


def test_a_stock_hold_bound_by_a_feasible_candidate_gets_no_release_option(
    db: Database,
) -> None:
    """While the plan is in question, a hold the active plan does not use but a feasible
    candidate binds is not offered for release (once the plan is settled it is). Catches:
    dropping the ``stock_transfers`` or the ``required_stock_holds`` binding from
    ``_release_options``."""
    # A full handoff request binds the handoff candidate's transfer need.
    sb = PantrySandbox(db, "pantry_dev01")
    held = sb.hold_partner("full-16")
    assert held.status == "succeeded" and held.data is not None, held.error
    transfer = held.data["hold"]["hold_id"]
    view, ev = evaluated(sb)
    assert handoff_candidate(ev).stock_transfers[0].bound_hold_ids == (transfer,)
    assert f"release:{transfer}" not in menu(view, ev)
    assert f"release:{transfer}" in menu(view, ev, plan_in_question=False)
    # A pool hold whose window does not cover the planned distribution is not used by the
    # plan, yet it binds the allocation's (and the kept plan's) pool requirement.
    sb = PantrySandbox(db, "pantry_dev01")
    held = sb.hold_pantry("pool-short", 24, window=SHORT_WINDOW)
    assert held.status == "succeeded" and held.data is not None, held.error
    pool = held.data["hold"]["hold_id"]
    view, ev = evaluated(sb)
    assert allocate_candidate(ev).constraint_status == "feasible_under_assumptions"
    assert allocate_candidate(ev).required_stock_holds[0].bound_hold_ids == (pool,)
    assert f"release:{pool}" not in menu(view, ev)
    assert f"release:{pool}" in menu(view, ev, plan_in_question=False)


# ---------------------------------------------------------------------------------- E4


def test_stock_improvable_names_a_pursuable_candidate_that_covers_more(db: Database) -> None:
    """The agent holds the 24 pantry kits: the kept plan is applicable and covers 24 of 40, the
    handoff candidate would cover 40. Catches: treating every candidate as pursuable, dropping
    the ``unfulfilled(c) < unfulfilled(keep)`` comparison (or making it ``<=``), ignoring the
    eligibility filter, or dropping the awaited-handoff clause of ``pursuable``."""
    sb = PantrySandbox(db, "pantry_dev01")
    held = sb.hold_pantry("pool-24", 24)
    assert held.status == "succeeded", held.error
    view, ev = evaluated(sb)
    keep, cand = keep_candidate(ev), handoff_candidate(ev)
    assert keep.applicable_now and unfulfilled(keep) == 16
    assert not cand.applicable_now and unfulfilled(cand) == 0
    assert stock_improvable(view, ev, inputs(view.clock), everyone) is True
    # In question, the stock options reopen; settled, the menu is keep and wait.
    assert HANDOFF_16 in menu(view, ev)
    assert menu(view, ev, plan_in_question=False) == ("keep", "wait")
    # Nothing pursuable covers more: at 12:47 the handoff can no longer be requested.
    assert stock_improvable(view, ev, inputs(pt("12:47")), everyone) is False
    # The applicable allocation covers what the kept plan covers, which is not more.
    rest = ev.model_copy(
        update={
            "candidates": tuple(c for c in ev.candidates if c.candidate_id != cand.candidate_id)
        }
    )
    assert stock_improvable(view, rest, inputs(view.clock), everyone) is False
    assert (
        stock_improvable(view, ev, inputs(view.clock), lambda c: c.signature != cand.signature)
        is False
    )
    # Requested, the awaited handoff keeps the candidate pursuable after requests close, until
    # the staff task's cutoff.
    asked = sb.hold_partner("full-16")
    assert asked.status == "succeeded", asked.error
    view, ev = evaluated(sb)
    assert awaited_handoffs(view, AGENT, pt("12:47"))
    assert stock_improvable(view, ev, inputs(pt("12:47")), everyone) is True
    assert not awaited_handoffs(view, AGENT, pt("12:50"))
    assert stock_improvable(view, ev, inputs(pt("12:50")), everyone) is False


def test_the_live_policy_reopens_an_applicable_plan_when_a_handoff_would_cover_more(
    db: Database, tmp_path: Path
) -> None:
    """Catches: dropping the ``stock_improvable`` reopening from ``LivePolicy._step`` (the
    applicable plan would be kept by the server with no model call and no handoff request)."""
    sb = PantrySandbox(db, "pantry_dev01")
    held = sb.hold_pantry("pool-24", 24)
    assert held.status == "succeeded", held.error
    _, result, opener = run_p2(sb, tmp_path, chooser("handoff:", "keep"))
    menus = choice_menus(opener)
    assert menus and "keep" in menus[0] and HANDOFF_16 in menus[0]
    asks = [d for d in result.decisions if d.kind == "ask"]
    assert len(asks) == 1
    assert asks[0].details["ask"] == "stock_handoff"
    assert asks[0].details["choice"]["option_id"] == HANDOFF_16
    stock = sb.view().stock
    assert stock is not None and [t.status for t in stock.handoff_tasks] == ["open"]


def test_with_every_other_option_spent_the_policy_waits_for_the_staff_handoff(
    db: Database,
    tmp_path: Path,
    scratch_case: Callable[[str, Callable[[dict[str, Any]], None]], str],
) -> None:
    """After both status reads, the handoff request and a refused pool hold (the supplier desk
    is unreachable from 12:33), the menu holds nothing but wait while staff owe the handoff.
    Catches: dropping the awaited-handoff branch of ``_record_default`` (a generic blocked wait
    would be recorded), dropping the rejected pool hold from the run's later menus, or dropping
    the staff task from the wake computation (the run would wake at nothing)."""
    case = scratch_case("pantry_t1_supplier_desk_down", supplier_desk_down_from_1233)
    sb = PantrySandbox(db, case)
    _, result, opener = run_p2(sb, tmp_path, chooser("query:", "handoff:", "hold:"))
    refused = rejected(result.decisions)
    assert len(refused) == 1
    assert refused[0].details["choice"]["option_id"] == POOL_24
    assert refused[0].details["error_code"] == "STATUS_UNAVAILABLE"
    # The refused hold was the last model choice: what followed needed none.
    assert POOL_24 in choice_menus(opener)[-1]
    stock = sb.view().stock
    assert stock is not None and len(stock.handoff_tasks) == 1
    task = stock.handoff_tasks[0]
    assert task.status == "open" and sb.clock() < task.respond_after
    waits = [
        d
        for d in result.decisions
        if d.kind == "wait" and d.summary.startswith("Waiting for staff to record the handoff")
    ]
    assert len(waits) == 1
    assert waits[0].details["chosen_by"] == "server" and task.hold_id in waits[0].summary
    assert waits[0].wait_until == task.respond_after
    assert result.status == "waiting" and result.wait_until == task.respond_after


def test_the_wake_moves_from_the_staff_response_to_the_task_cutoff(
    db: Database, tmp_path: Path
) -> None:
    """Without a case no staff simulator answers. Catches: dropping the awaited staff task from
    ``_compute_wait``, waking only at ``respond_after`` (nothing once it passed) or only at the
    cutoff."""
    sb = PantrySandbox(db)
    policy, first, _ = run_p2(sb, tmp_path, chooser("handoff:"))
    stock = sb.view().stock
    assert stock is not None and len(stock.handoff_tasks) == 1
    task = stock.handoff_tasks[0]
    assert task.status == "open" and task.respond_after < task.cutoff
    ask = next(d for d in first.decisions if d.kind == "ask")
    assert ask.wait_until == task.respond_after
    assert first.status == "waiting" and first.wait_until == task.respond_after
    sb.advance_to("12:35")
    assert task.respond_after < sb.clock() < task.cutoff
    second = policy.run(sb.agent, max_tool_calls=40)
    stock = sb.view().stock
    assert stock is not None and [t.status for t in stock.handoff_tasks] == ["open"]
    assert second.status == "waiting" and second.wait_until == task.cutoff


def test_a_rejected_handoff_is_not_offered_again_in_the_same_run(
    db: Database,
    tmp_path: Path,
    scratch_case: Callable[[str, Callable[[dict[str, Any]], None]], str],
) -> None:
    """The partner steward desk cannot be reached, so the handoff hold is refused at execution
    while the visible state still supports it. Catches: dropping
    ``run.rejected_intents.add(option.intent)`` from ``_after_handoff`` (the same request would
    be offered, and chosen, again in the run)."""
    case = scratch_case("pantry_t1_partner_desk_down", partner_desk_unreachable)
    sb = PantrySandbox(db, case)
    _, result, opener = run_p2(sb, tmp_path, chooser("handoff:"))
    refused = rejected(result.decisions)
    assert len(refused) == 1
    assert refused[0].details["choice"]["option_id"] == HANDOFF_16
    assert refused[0].details["error_code"] == "STATUS_UNAVAILABLE"
    menus = choice_menus(opener)
    assert len(menus) >= 2 and HANDOFF_16 in menus[0]
    assert all(HANDOFF_16 not in m for m in menus[1:])
    # The state alone would still offer it: no hold or staff task exists, the window is open.
    view, ev = evaluated(sb)
    stock = view.stock
    assert stock is not None and stock.handoff_tasks == () and not view.holds
    assert HANDOFF_16 in menu(view, ev)
