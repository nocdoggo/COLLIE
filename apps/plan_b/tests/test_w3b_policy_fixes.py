"""Policy 1.2 fixes of the post-release defects (Wave 3b), on development cases and synthetic
variants written here. No spent held-out case is read or reused.

* An unavailable pool is no handoff option: a status check that reports the alternate pool
  ``unavailable`` removes the handoff from the planner's feasible candidates and from the menu,
  so ``stock_improvable`` no longer keeps the plan in question (a pantry_dev01 variant whose
  partner desk reports the kits booked elsewhere).
* A person's late arrival reaches the planner: a reported or hypothetical ETA after the start
  fails ``participant_availability``, and a person's delay claim is material for P2/P3.
* The shared rule does not call the model again on a menu it already passed on in the same
  state (``AttentionMixin._declined_repeat``).
* The provider waits out HTTP 429 inside one call (no model call of the episode is used),
  bounded by wall time.
* The report lists policy ids in P0 to P3 order.

Each test names the mutation it catches.
"""

from __future__ import annotations

import io
import urllib.error
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent import provider as prov
from plan_b.agent.attention import MATERIAL_KINDS, AttentionMixin
from plan_b.agent.menu import Menu, MenuInputs, MenuOption, handoff_quantity, stock_improvable
from plan_b.agent.orchestrator import POLICY_ID as P2_ID
from plan_b.agent.policies.tool_use import POLICY_ID as P1_ID
from plan_b.agent.policies.verify_all import POLICY_ID as P3_ID
from plan_b.agent.provider import ProviderHTTPError
from plan_b.domain.constraints import _Assumptions, _participant_availability, build_context
from plan_b.domain.fixtures import load_public_scenario
from plan_b.domain.models import Hypothesis
from plan_b.domain.projection import initial_snapshot
from plan_b.evaluation.report import _policy_id_labels
from plan_b.store.database import Database
from tests.test_agent_provider import FakeOpener, echo_request, make_config, make_provider
from tests.test_pantry_fixture import PantrySandbox
from tests.test_pantry_live_menu import (
    AGENT,
    PAIR,
    evaluated,
    handoff_candidate,
    menu,
    scope_of,
)
from tests.test_pantry_live_menu import scratch_case as _scratch_case

scratch_case = _scratch_case  # the fixture, under this module's name


def booked_elsewhere(case: dict[str, Any]) -> None:
    """Synthetic variant: the partner desk answers that the alternate pool is unavailable."""
    record = next(r for r in case["status_model"] if r["entity_id"] == "partner_stock")
    record["response"].update(
        status_code="booked_elsewhere",
        domain_status="unavailable",
        text="Partner steward desk: these kits are committed to another program today.",
    )


def check_partner(sb: PantrySandbox) -> None:
    env = sb.agent.call(
        "query_status",
        arguments={"entity_id": "partner_stock", "fact": "availability"},
        idempotency_key="w3b-check-partner",
        expected_revision=sb.revision(),
    )
    assert env.status == "succeeded", env.error


# ---------------------------------------------------------------- unavailable pool (planner, menu)


def test_a_pool_checked_unavailable_is_no_handoff_option(
    db: Database, scratch_case: Callable[[str, Callable[[dict[str, Any]], None]], str]
) -> None:
    """Catches: dropping the planner's unavailable-source check (the handoff candidate stays
    feasible and ranked) or the menu's (``handoff_quantity`` still counts the pool's units)."""
    sb = PantrySandbox(db, scratch_case("w3b_booked", booked_elsewhere))
    sb.advance_to("12:31")
    before_view, before = evaluated(sb)
    assert handoff_candidate(before).constraint_status == "feasible_under_assumptions"
    assert [i for i in menu(before_view, before) if i.startswith(PAIR)]
    check_partner(sb)
    view, ev = evaluated(sb)
    partner = next(r for r in view.resources if r.definition.resource_id == "partner_stock")
    assert partner.status == "unavailable"
    cand = handoff_candidate(ev)
    assert cand.constraint_status != "feasible_under_assumptions"
    transfer = next(c for c in cand.checks if c.constraint_id == "stock_transfer")
    assert transfer.status == "failed" and "reported unavailable" in transfer.detail
    assert not [i for i in menu(view, ev) if i.startswith(PAIR)]
    # The menu guard holds on its own too, for a stale evaluation that still names the need.
    scope, activities = scope_of(view)
    need = handoff_candidate(before).stock_transfers[0]
    assert handoff_quantity(view, MenuInputs(AGENT, view.clock), scope, activities, need) == 0
    assert handoff_quantity(before_view, MenuInputs(AGENT, view.clock), scope, activities, need)
    # Nothing pursuable covers more, so the shared rule does not keep the plan in question.
    assert not stock_improvable(view, ev, MenuInputs(AGENT, view.clock), lambda c: True)


def test_an_available_pool_keeps_its_handoff(db: Database) -> None:
    """Control on the unchanged development case: the check reports the pool available and the
    handoff stays offered. Catches: a check that drops handoffs whatever the status."""
    sb = PantrySandbox(db, "pantry_dev01")
    sb.advance_to("12:31")
    check_partner(sb)
    view, ev = evaluated(sb)
    assert handoff_candidate(ev).constraint_status == "feasible_under_assumptions"
    assert [i for i in menu(view, ev) if i.startswith(PAIR)]


# ---------------------------------------------------------------- a person's delay (C06 class)


def _snapshot_with_person() -> tuple[Any, str, Any]:
    """The development fixture's initial snapshot and its first person on a planned activity."""
    snapshot = initial_snapshot(load_public_scenario())
    resources = {r.definition.resource_id: r for r in snapshot.resources}
    for a in snapshot.plan.assignments:
        for rid in a.resource_ids:
            if resources[rid].definition.kind == "person":
                return snapshot, rid, a
    pytest.skip("the development fixture assigns no person")


def test_a_person_eta_after_the_start_fails_participant_availability() -> None:
    """Catches: a planner that ignores a person's reported or hypothetical arrival time (1.1
    checked only check-ins and the declared window, so a person's delay never failed a plan)."""
    snapshot, rid, a = _snapshot_with_person()
    plan = snapshot.plan.assignments
    base = _participant_availability(build_context(snapshot), plan, _Assumptions())
    assert base.status != "failed"
    late = Hypothesis(resource_id=rid, assume_ready_at=a.start + timedelta(minutes=15), label="x")
    check = _participant_availability(build_context(snapshot, (late,)), plan, _Assumptions())
    assert check.status == "failed" and "hypothetical ETA" in check.detail
    early = Hypothesis(resource_id=rid, assume_ready_at=a.start - timedelta(minutes=5), label="y")
    fine = _participant_availability(build_context(snapshot, (early,)), plan, _Assumptions())
    assert fine.status != "failed"


def test_person_notices_are_material() -> None:
    """Catches: reverting the materiality rule to equipment only."""
    assert "person" in MATERIAL_KINDS and "equipment" in MATERIAL_KINDS


# ---------------------------------------------------------------- the declined-menu rule


class _Host(AttentionMixin):
    pass


class _View:
    def __init__(self, revision: int, goal_version: int = 1) -> None:
        self.revision = revision
        self.goal = type("G", (), {"version": goal_version})()


def _menu(*intents: str) -> Menu:
    acting = tuple(
        MenuOption(option_id=i, action="hold_resource", intent=i, summary=i) for i in intents
    )
    wait = MenuOption(option_id="wait", action="wait", intent="wait", summary="wait")
    return Menu(options=(*acting, wait))


def test_a_menu_passed_on_is_not_offered_again_in_the_same_state() -> None:
    """Catches: dropping ``_declined_repeat`` (a repeated wait costs a model call each wake) or
    keying it too loosely (a changed state or a new option must reach the model again)."""
    host = _Host()
    offered = _menu("hold:a:1", "handoff:b:c:4")
    assert not host._declined_repeat(_View(7), offered)  # type: ignore[arg-type]
    host._note_declined(_View(7), offered)  # type: ignore[arg-type]
    assert host._declined_repeat(_View(7), _menu("handoff:b:c:4", "hold:a:1"))  # type: ignore[arg-type]
    assert not host._declined_repeat(_View(8), offered)  # type: ignore[arg-type]
    assert not host._declined_repeat(_View(7, 2), offered)  # type: ignore[arg-type]
    assert not host._declined_repeat(_View(7), _menu("hold:a:1"))  # type: ignore[arg-type]


# ---------------------------------------------------------------- 429 backoff


class _RateLimited(FakeOpener):
    """Answers HTTP 429 ``n`` times, then the scripted reply."""

    def __init__(self, n: int, retry_after: str | None = None) -> None:
        super().__init__(lambda body: {"word": "hello"})
        self.limited = n
        self.retry_after = retry_after

    def open(self, request: Any, timeout: float | None = None) -> Any:
        if self.limited > 0:
            self.limited -= 1
            self.requests.append(request)
            headers = {"Retry-After": self.retry_after} if self.retry_after else {}
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                headers,  # type: ignore[arg-type]
                io.BytesIO(b'{"error":{"message":"rate limited"}}'),
            )
        return super().open(request, timeout)


def _limited_provider(tmp_path: Path, opener: _RateLimited) -> tuple[Any, list[float]]:
    provider = make_provider(make_config(tmp_path), opener)
    slept: list[float] = []
    provider._sleep = slept.append
    return provider, slept


def test_a_429_is_waited_out_inside_one_model_call(tmp_path: Path) -> None:
    """Catches: a 429 that reaches the caller (it would use one of the episode's model calls),
    a retry without a wait, or a wait that does not back off."""
    opener = _RateLimited(2)
    provider, slept = _limited_provider(tmp_path, opener)
    response = provider.complete(echo_request(call_id="mc_0001"))
    assert response.parsed.word == "hello"  # type: ignore[attr-defined]
    assert len(opener.requests) == 3 and slept == [prov.RETRY_429_BASE_S, 2 * prov.RETRY_429_BASE_S]
    assert response.record.rate_limit_retries == 2
    assert response.record.rate_limit_wait_ms == round(3 * prov.RETRY_429_BASE_S * 1000)
    entries = provider.guard.ledger.read()["calls"]
    statuses = [e.get("http_status") for e in entries]
    assert statuses.count(429) == 2  # every 429 is its own ledger entry
    assert all(e["cost_usd"] == 0 for e in entries if e.get("http_status") == 429)


def test_a_retry_after_header_is_honoured_up_to_the_delay_bound(tmp_path: Path) -> None:
    opener = _RateLimited(1, retry_after="7")
    provider, slept = _limited_provider(tmp_path, opener)
    provider.complete(echo_request(call_id="mc_0001"))
    assert slept == [7.0]


def test_the_429_wait_is_bounded_by_wall_time(tmp_path: Path) -> None:
    """Catches: an unbounded retry loop. After the bound the 429 reaches the caller, as in 1.1,
    with the waits it already made recorded."""
    opener = _RateLimited(100)
    provider, slept = _limited_provider(tmp_path, opener)
    with pytest.raises(ProviderHTTPError) as caught:
        provider.complete(echo_request(call_id="mc_0001"))
    assert caught.value.status == 429
    assert sum(slept) <= prov.RETRY_429_MAX_WAIT_S
    assert caught.value.record is not None
    assert caught.value.record.rate_limit_retries == len(slept) > 0


def test_other_http_errors_are_not_retried(tmp_path: Path) -> None:
    opener = _RateLimited(0)
    opener.reply = lambda body: urllib.error.HTTPError(
        "https://openrouter.test",
        500,
        "boom",
        {},
        io.BytesIO(b"{}"),  # type: ignore[arg-type]
    )
    provider, slept = _limited_provider(tmp_path, opener)
    with pytest.raises(ProviderHTTPError):
        provider.complete(echo_request(call_id="mc_0001"))
    assert slept == [] and len(opener.requests) == 1


# ---------------------------------------------------------------- ids and the report


def test_model_policies_carry_the_1_2_ids() -> None:
    assert (P1_ID, P2_ID, P3_ID) == ("tool-use/1.2.0", "live/1.2.0", "verify-all/1.2.0")


def test_the_report_lists_policy_ids_in_p0_to_p3_order() -> None:
    """Catches: the Wave 3 alphabetical order (live, rules, tool-use, verify-all)."""
    records = [
        {"policy": "P3", "policy_id": "verify-all/1.2.0"},
        {"policy": "P2", "policy_id": "live/1.2.0"},
        {"policy": "P0", "policy_id": "rules/1.0.0"},
        {"policy": "P1", "policy_id": "tool-use/1.2.0"},
        {"policy": "P0", "policy_id": "pantry-rules/1.1.0"},
        {"policy": "P2", "policy_id": "live/1.2.0"},
    ]
    assert _policy_id_labels(records, ["P0", "P1", "P2", "P3"]) == [
        "P0 pantry-rules/1.1.0",
        "P0 rules/1.0.0",
        "P1 tool-use/1.2.0",
        "P2 live/1.2.0",
        "P3 verify-all/1.2.0",
    ]


# ---------------------------------------------------------------- a stale choice is re-issued


def test_a_stale_choice_is_re_issued_without_a_model_call(sandbox: Any, tmp_path: Path) -> None:
    """dev01 sandbox: the apply the model chose arrives stale (a check-in lands first). Policy
    1.2 re-issues the same option on the re-read state; 1.1 asked the model again. Catches:
    dropping the re-issue (two choose_action calls) or re-issuing a different option."""
    from plan_b.agent.orchestrator import CHOOSE_SCHEMA_NAME
    from plan_b.store import repo
    from tests.test_agent_boundary import _stale_once, live
    from tests.test_agent_provider import schema_name

    policy, opener, _ = live(tmp_path, _stale_once(sandbox, 1))
    result = policy.run(sandbox.agent)
    with sandbox.db.read() as conn:
        applies = [r for r in repo.receipts(conn, sandbox.episode_id) if r.tool == "apply_plan"]
    assert [r.status for r in applies] == ["rejected", "applied"]
    stale = next(d for d in result.decisions if d.details.get("failure") == "stale_revision")
    after = [
        d for d in result.decisions[result.decisions.index(stale) + 1 :] if "choice" in d.details
    ]
    # The next model-chosen decision is the re-issued apply, with the stale choice's model call.
    assert (
        after
        and after[0].details["choice"]["model_call_id"]
        == (stale.details["choice"]["model_call_id"])
    )
    assert after[0].details["choice"]["intent"] == stale.details["choice"]["intent"]
    assert "re-issued apply:" in (result.note or "")
    # One choice before the stale apply and none for its retry (dev01's later commit stage
    # may add its own choice, after the applied plan).
    chooses = [b for b in opener.bodies if schema_name(b) == CHOOSE_SCHEMA_NAME]
    assert len(chooses) <= 2


# ---------------------------------------------------------------- P1's repeated waits


def test_p1_repeated_waits_on_an_unchanged_state_do_not_each_cost_a_call(
    db: Database, tmp_path: Path
) -> None:
    """dev01, a scripted P1 model that only ever waits three minutes. 1.1 honoured every wait
    it asked for and spent the episode's 8 model calls on waits. 1.2 honours a first wait, sends
    a wait asked again on an unchanged state through the shared rule, and does not call again
    on a menu the model passed on. Catches: dropping either rule."""
    from tests.test_live_workflow import ToolScript, build, run_with, turn

    def always_wait(body: dict[str, Any], n: int) -> Any:
        return turn(done=True, decision="wait", wait_minutes=3)

    policy, opener = build("P1", tmp_path / "p1", ToolScript(always_wait))
    run_with(db, "dev01", policy)
    assert 2 <= len(opener.requests) < 8
