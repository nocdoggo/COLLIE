"""Regressions of the model-driven comparison policies (P1-P3), with scripted models.

Each test pins one behavior the Wave 2 close-out audit found missing: P1 sees the news its own
calls bring before it decides, reads its own state reads and parses arguments safely; a lost
mutation is never narrated from a stale state; the live pantry policy reports a shortfall as
the baseline does, records a reconciled handoff as the ask it was and releases a handoff hold
staff are done with; P3 checks every update (including one that arrives during its checks)
under P2's retry bound and settles after its checks; and a restarted host keeps the episode's
model-call cap. The final audit added two: a handoff requested before its window opens is
checked as too early, not too late, and P1's turn tools drop a staff tool even when a grant
lists one. Everything runs through the real store, executor and runner; nothing reaches the
network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import plan_b.domain.fixtures as fixtures
from plan_b.agent.menu import own_grant
from plan_b.agent.policies.tool_use import ToolUsePolicy
from plan_b.agent.policies.verify_all import VerifyAllPolicy
from plan_b.domain.models import EventStateView
from plan_b.evaluation.policies.base import Policy
from plan_b.scenarios.policy_host import EpisodeCaps, PolicyHost
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.sessions import issue_session
from plan_b.tools.client import InProcessToolClient
from tests.conftest import Sandbox, at
from tests.test_agent_provider import (
    FakeOpener,
    ScriptedModel,
    make_config,
    make_provider,
    menu_ids,
    state_of,
)
from tests.test_live_workflow import (
    ToolScript,
    build,
    run_with,
    sandbox_calls,
    schema_name,
    tool_state,
    tool_user,
    turn,
)
from tests.test_pantry_fixture import EVENT, PantrySandbox


def _receipts(sb: Sandbox, tool: str) -> list[str]:
    with sb.db.read() as conn:
        return [r.status for r in repo.receipts(conn, sb.episode_id) if r.tool == tool]


def _choose(prefixes: tuple[str, ...]) -> ScriptedModel:
    def choose(body: dict[str, Any]) -> dict[str, Any]:
        ids = menu_ids(body)
        cited = [r["tool_call_id"] for r in state_of(body)["last_tool_results"]]
        for prefix in prefixes:
            for option_id in ids:
                if option_id.startswith(prefix):
                    return {"option_id": option_id, "rationale": prefix, "cited_refs": cited}
        return {"option_id": "wait", "rationale": "wait", "cited_refs": cited}

    return ScriptedModel(choose=choose)


class _Exogenous:
    """A coordinator client that lets ``act`` change the world once, right after the first
    call of ``tool`` (as a participant or organizer acting during that call would)."""

    def __init__(self, inner: InProcessToolClient, tool: str, act: Any) -> None:
        self.inner, self.tool, self.act, self.done = inner, tool, act, False
        self.principal_id = inner.principal_id

    def call(self, tool: str, **kwargs: Any) -> Any:
        envelope = self.inner.call(tool, **kwargs)
        if tool == self.tool and not self.done:
            self.done = True
            self.act()
        return envelope


# ---------------------------------------------------------------------------------- P1


def test_tool_use_sees_a_rejected_apply_before_it_decides(db: Database, tmp_path: Path) -> None:
    sb = Sandbox(db, "dev01")
    fired: list[bool] = []

    def check_in() -> None:
        env = sb.client("participant_facilitator").call(
            "check_in",
            arguments={
                "resource_id": "facilitator",
                "available": {"start": sb.clock().isoformat(), "end": at("18:00").isoformat()},
            },
            idempotency_key="ci-stale",
        )
        assert env.status == "succeeded", env

    def stale(body: dict[str, Any], n: int) -> Any:
        out = tool_user(body)  # applies and ends its turn (done=true) in one reply
        if not fired and any(c["tool"] == "apply_plan" for c in out["calls"]):
            fired.append(True)
            check_in()
        return out

    policy, _ = build("P1", tmp_path, ToolScript(stale))
    result = policy.run(sb.agent)
    # Before: the run ended with the model's 'keep', written before it saw the rejection, and
    # the attention rule then never woke it again. Now the rejection reaches the next turn.
    assert _receipts(sb, "apply_plan") == ["rejected", "applied"]
    kinds = [d.kind for d in result.decisions]
    assert "commit" in kinds and kinds[-1] == "keep"


def test_tool_use_sees_a_status_answer_before_it_decides(sandbox: Sandbox, tmp_path: Path) -> None:
    def query_and_end(body: dict[str, Any], n: int) -> Any:
        if n == 1:
            check = ("query_status", {"entity_id": "projector", "fact": "delivery_eta"})
            return turn([check], done=True, decision="keep")
        return turn(done=True, decision="wait")

    policy, opener = build("P1", tmp_path, ToolScript(query_and_end))
    policy.run(sandbox.agent)
    turns = [b for b in opener.bodies if schema_name(b) == "plan_b_tool_turn"]
    assert len(turns) == 2
    state, _ = tool_state(turns[1])
    assert [r["tool"] for r in state["last_tool_results"]] == ["query_status"]


def test_tool_use_reads_the_state_it_asked_for(sandbox: Sandbox, tmp_path: Path) -> None:
    seen: list[tuple[int, list[str]]] = []

    def model(body: dict[str, Any], n: int) -> Any:
        state, observations = tool_state(body)
        seen.append((state["event"]["revision"], [o["observation_id"] for o in observations]))
        if n == 1:
            sandbox.organizer.call(
                "submit_observation",
                arguments={"text": "The facilitator says she will be 30 minutes late."},
                idempotency_key="org-late",
            )
            return turn([("get_event_state", {})])
        return turn(done=True, decision="wait")

    policy, _ = build("P1", tmp_path, ToolScript(model))
    result = policy.run(sandbox.agent)
    assert seen[1][0] == sandbox.revision() > seen[0][0]
    assert len(seen[1][1]) == len(seen[0][1]) + 1
    # The model's own read is the next turn's state: it is not read a second time.
    reads = [t for t in sandbox_calls(sandbox) if t == "get_event_state"]
    assert len(reads) == 2 and result.tool_calls == len(sandbox_calls(sandbox))


def test_tool_use_reads_a_what_if_by_label(sandbox: Sandbox, tmp_path: Path) -> None:
    what_if = {"resource_id": "projector", "assume_ready_at": None, "assume_status": "unavailable"}
    what_if |= {"label": "projector unavailable"}

    def model(body: dict[str, Any], n: int) -> Any:
        if n == 1:
            return turn([("evaluate_candidates", {"templates": None, "hypotheses": [what_if]})])
        return turn(done=True, decision="wait")

    policy, opener = build("P1", tmp_path, ToolScript(model))
    policy.run(sandbox.agent)
    state, _ = tool_state([b for b in opener.bodies if schema_name(b) == "plan_b_tool_turn"][1])
    result = state["last_tool_results"][0]
    assert result["status"] == "succeeded", result
    assert "what-if only" in result["summary"] and "'Keep the current plan'" in result["summary"]


@pytest.mark.parametrize("mode", ["query", "reject"])
def test_tool_use_ends_its_turn_on_news_it_has_already_seen(
    sandbox: Sandbox, tmp_path: Path, mode: str
) -> None:
    """A model that ends every turn with the same check, or the same rejected request, gets one
    look at the result; then its decision and wait stand (no loop to the model-call cap)."""

    def model(body: dict[str, Any], n: int) -> Any:
        call: tuple[str, dict[str, Any]] = (
            ("query_status", {"entity_id": "projector", "fact": "delivery_eta"})
            if mode == "query"
            else ("release_hold", {"hold_id": "hold_9999", "reason": "tidy up"})
        )
        return turn([call], done=True, decision="wait", wait_minutes=30)

    policy, opener = build("P1", tmp_path, ToolScript(model))
    result = policy.run(sandbox.agent)
    assert len(opener.bodies) <= 2
    final = result.decisions[-1]
    assert final.kind == "wait" and final.details.get("final_decision") == "wait"
    # The model's wake stands; the run wakes at it or earlier, at the shared wake schedule
    # (here dev01's deadline watch on the projector, 17:05).
    assert final.wait_until is not None and policy._model_wake == final.wait_until
    assert result.wait_until is not None and result.wait_until <= final.wait_until


def test_a_tool_use_shortfall_is_read_after_its_own_apply(db: Database, tmp_path: Path) -> None:
    def apply_and_report(body: dict[str, Any], n: int) -> Any:
        out = tool_user(body)
        applies = [c for c in out["calls"] if c["tool"] == "apply_plan"]
        if out["done"] and applies:
            state, _ = tool_state(body)
            cid = json.loads(applies[0]["arguments_json"])["candidate_plan_id"]
            cand = next(
                c for c in state["latest_evaluation"]["candidates"] if c["candidate_id"] == cid
            )
            if any(s["unfulfilled"] for s in cand.get("service_coverage", [])):
                return out | {"decision": "infeasible"}
        return out

    policy, _ = build("P1", tmp_path, ToolScript(apply_and_report))
    result = run_with(db, "pantry_dev02", policy)
    infeasible = next(d for d in result.history.decisions if d.kind == "infeasible")
    assert infeasible.details["shortfalls"][0]["covered_quantity"] == 34
    assert infeasible.details["shortfalls"][0]["shortfall_quantity"] == 6


def test_tool_use_refuses_arguments_it_cannot_parse(sandbox: Sandbox, tmp_path: Path) -> None:
    huge = '{"capability": ' + "9" * 4301 + "}"  # json.loads raises a plain ValueError

    def model(body: dict[str, Any], n: int) -> Any:
        if n == 1:
            return turn() | {"calls": [{"tool": "list_resources", "arguments_json": huge}]}
        return turn(done=True, decision="wait")

    policy, _ = build("P1", tmp_path, ToolScript(model))
    result = policy.run(sandbox.agent)
    refused = [d for d in result.decisions if d.details.get("failure") == "invalid_choice"]
    assert refused and "not parsable" in refused[0].details["problem"]
    assert result.decisions[-1].kind == "wait"


def test_a_lost_apply_is_never_narrated_from_a_stale_state(db: Database, tmp_path: Path) -> None:
    sb = Sandbox(db, "dev01")
    policy, _ = build("P1", tmp_path)
    lost = sb.client("agent_demo", lose=lambda t, k: t in ("apply_plan", "get_action_receipt"))
    result = policy.run(lost)
    kinds = [d.kind for d in result.decisions]
    reconcile = result.decisions[kinds.index("reconcile")]
    assert "2 receipt lookup(s) and no retry" in reconcile.summary
    version = sb.view().plan.plan_version
    assert version == 2  # the apply ran on the server; only its responses were lost
    later = result.decisions[kinds.index("reconcile") + 1 :]
    assert later and all("plan v1 " not in d.summary for d in later)


def test_each_model_call_records_its_generation_settings(db: Database, tmp_path: Path) -> None:
    expected = {"tool_turn": 4096, "choose_action": 4096, "interpret": 4096}  # one limit (W3)
    for kind in ("P1", "P2"):
        sb = Sandbox(db, "dev01")
        policy, _ = build(kind, tmp_path / kind)
        calls = [c for d in policy.run(sb.agent).decisions for c in d.details["model"]["calls"]]
        assert calls, kind
        for call in calls:
            assert call["provider"] == "openrouter"
            assert call["max_tokens"] == expected[call["purpose"]], (kind, call["purpose"])


# ---------------------------------------------------------------------------------- P2 pantry


def test_the_live_pantry_policy_reports_a_shortfall_as_the_baseline_does(
    db: Database, tmp_path: Path
) -> None:
    for kind in ("P2", "P3"):
        policy, _ = build(kind, tmp_path / kind)
        result = run_with(db, "pantry_dev02", policy)
        assert result.report.matches_expectation is True, (kind, result.report.predicates)
        shortfall = [d for d in result.history.decisions if d.kind == "infeasible"]
        assert len(shortfall) == 1, kind
        details = shortfall[0].details
        assert (details["shortfall_quantity"], details["chosen_by"]) == (6, "server")
        assert details["blocking_constraints"]
        # Staff answered the handoff; the server releases its residual hold, so the model is
        # not asked again and again about it.
        releases = [d for d in result.history.decisions if d.kind == "release"]
        assert releases and all(d.details.get("chosen_by") == "server" for d in releases)
        caps = result.report.episode_caps
        assert caps is not None and caps.model_calls < caps.max_model_calls, kind


def test_a_tool_use_shortfall_report_names_what_blocks_coverage(
    db: Database, tmp_path: Path
) -> None:
    def honest(body: dict[str, Any], n: int) -> Any:
        out = tool_user(body)
        state, _ = tool_state(body)
        ev = state["latest_evaluation"]
        keep = next(
            (
                c
                for c in (ev or {}).get("candidates", [])
                if c["candidate_id"] == ev["keep_candidate_id"]
            ),
            None,
        )
        short = keep is not None and any(s["unfulfilled"] for s in keep.get("service_coverage", []))
        if out["done"] and out["decision"] == "keep" and not out["calls"] and short:
            return out | {"decision": "infeasible"}  # it reports the shortfall it keeps
        return out

    policy, _ = build("P1", tmp_path, ToolScript(honest))
    result = run_with(db, "pantry_dev02", policy)
    infeasible = [d for d in result.history.decisions if d.kind == "infeasible"]
    assert infeasible and all(d.details["blocking_constraints"] for d in infeasible)
    # Reported by the model (``details.shortfalls``) or, when no model call is warranted, by the
    # server's narration shared with P2 (1.1.0; the shortfall's own fields).
    quantities = {
        d.details["shortfalls"][0]["shortfall_quantity"]
        if "shortfalls" in d.details
        else d.details["shortfall_quantity"]
        for d in infeasible
    }
    assert quantities == {6}
    assert result.report.matches_expectation is True, result.report.predicates


def _pantry_variant(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **params: Any) -> None:
    """The pantry scenario with some pantry parameters changed (a scratch copy)."""
    original = fixtures.public_scenario_path
    scenario = json.loads(original("dev_fixture_03").read_text())
    for key, value in params.items():
        if key == "window_start":
            scenario["pantry_parameters"]["handoff_window"]["start"] = value
        else:
            scenario["pantry_parameters"][key] = value
    variant = tmp_path / "pantry_continuity.json"
    variant.write_text(json.dumps(scenario))
    monkeypatch.setattr(
        fixtures,
        "public_scenario_path",
        lambda sid: variant if sid == "dev_fixture_03" else original(sid),
    )


def test_no_shortfall_is_reported_before_the_handoff_window_opens(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pantry_variant(monkeypatch, tmp_path, window_start="2026-11-09T12:40:00-05:00")
    for kind in ("P2", "P3"):
        policy, _ = build(kind, tmp_path / kind)
        result = run_with(db, "pantry_dev01", policy)
        assert result.report.goal_complete is True, kind
        assert not [d for d in result.history.decisions if d.kind == "infeasible"], kind


def test_a_handoff_before_its_window_opens_is_checked_as_too_early(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every policy reads this check; P1 reads its text directly.
    _pantry_variant(monkeypatch, tmp_path, window_start="2026-11-09T12:40:00-05:00")
    env = PantrySandbox(db).evaluate()
    assert env.data is not None
    details = [
        check["detail"]
        for c in env.data["candidates"]
        if c["label"].startswith("Hand off partner_stock")
        for check in c["checks"]
        if check["constraint_id"] == "stock_transfer" and check["status"] == "failed"
    ]
    assert details
    assert all("too early, the handoff window opens at 12:40" in d for d in details)
    assert not any("too late" in d for d in details)


def test_tool_use_never_offers_a_staff_tool_its_grant_lists(db: Database, tmp_path: Path) -> None:
    # No shipped coordinator grant lists a staff tool, so the parity tests cannot reach this.
    view = PantrySandbox(db).view()
    own = own_grant(view, "agent_demo")
    assert own is not None
    staff = ("record_stock_receipt", "record_distribution")
    widened = own.model_copy(
        update={
            "grant": own.grant.model_copy(
                update={"allowed_tools": (*own.grant.allowed_tools, *staff)}
            )
        }
    )
    grants = tuple(widened if g is own else g for g in view.grants)
    policy, _ = build("P1", tmp_path)
    assert isinstance(policy, ToolUsePolicy)
    policy._principal = "agent_demo"
    tools = policy._tools(view.model_copy(update={"grants": grants}))
    assert tools == tuple(own.grant.allowed_tools)
    assert not set(staff) & set(tools)


def test_a_stale_release_of_a_closed_handoff_is_retried(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Staff answer after 4 minutes, so the release spans the 12:40 setup start and goes stale.
    _pantry_variant(monkeypatch, tmp_path, handoff_duration_minutes=4)
    policy, _ = build("P2", tmp_path)
    result = run_with(db, "pantry_dev02", policy)
    stale = [
        d for d in result.history.decisions if d.details.get("error_code") == "REVISION_CONFLICT"
    ]
    released = [d for d in result.history.decisions if d.kind == "release"]
    assert stale and released and released[0].at > stale[0].at


def test_the_live_menu_never_offers_an_apply_that_keeps_the_plan(
    db: Database, tmp_path: Path
) -> None:
    policy, _ = build("P2", tmp_path, _choose(("query:", "hold:", "apply:", "handoff:", "keep")))
    result = run_with(db, "pantry_dev01", policy)
    codes = {d.details.get("error_code") for d in result.history.decisions}
    assert "UNSUPPORTED_ACTION" not in codes
    assert result.report.goal_complete is True


def test_a_reconciled_handoff_request_is_recorded_as_the_ask(db: Database, tmp_path: Path) -> None:
    sb = PantrySandbox(db, "pantry_dev01")
    lost: list[str] = []

    def lose(tool: str, key: str | None) -> bool:
        if tool == "hold_resource" and not lost:
            lost.append(tool)
            return True
        return False

    with db.write() as conn:
        token, session = issue_session(conn, sb.episode_id, "agent_demo")
    client = InProcessToolClient(
        db,
        token,
        principal_id="agent_demo",
        event_id=EVENT,
        grant_id=session.grant_id,
        lose_response=lose,
    )
    policy, _ = build("P2", tmp_path)
    result = policy.run(client)
    hold = next(h for h in sb.view().holds if h.purpose == "stock_transfer")
    ask = next(d for d in result.decisions if d.details.get("ask") == "stock_handoff")
    assert ask.kind == "ask" and ask.details["reconciled"] is True
    assert ask.details["hold_id"] == hold.hold_id
    assert not any("was rejected" in d.summary for d in result.decisions)


# ---------------------------------------------------------------------------------- P3


def _verify_all(decisions: Any, entity: str) -> list[Any]:
    return [
        d for d in decisions if d.details.get("verify_all") and d.details["entity_id"] == entity
    ]


def test_verify_all_checks_a_newer_notice_about_a_checked_subject(
    db: Database, tmp_path: Path
) -> None:
    sb = Sandbox(db, "dev06")
    policy, _ = build("P3", tmp_path, _choose(()))
    first = policy.run(sb.agent)
    assert len(_verify_all(first.decisions, "projector")) == 2  # both attempts failed
    sb.advance(3)
    env = sb.organizer.call(
        "submit_observation",
        arguments={
            "entity_id": "projector",
            "text": "Our projector delivery may be about 40 minutes later than the promised 5 "
            "p.m. arrival.",
        },
        idempotency_key="org-newer",
    )
    newer = env.data["observation"]["observation"]["observation_id"] if env.data else None
    sb.advance(1)
    second = policy.run(sb.agent)
    checks = _verify_all(second.decisions, "projector")
    assert checks and all(newer in d.observation_refs for d in checks)


def test_verify_all_checks_a_notice_that_arrives_during_its_checks(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    def notice() -> None:
        sandbox.organizer.call(
            "submit_observation",
            arguments={
                "entity_id": "projector",
                "text": "Our projector delivery may be about 50 minutes later than the "
                "promised 5 p.m. arrival.",
            },
            idempotency_key="org-mid",
        )

    policy, _ = build("P3", tmp_path, _choose(("apply:", "keep")))
    result = policy.run(_Exogenous(sandbox.agent, "query_status", notice))
    kinds = [d.kind for d in result.decisions]
    assert "commit" in kinds
    checks = [i for i, d in enumerate(result.decisions) if d.details.get("verify_all")]
    mid = [i for i in checks if "obs_0002" in result.decisions[i].summary]
    assert mid and max(mid) < kinds.index("commit")


def test_verify_all_relevance_follows_the_grant_and_the_answers(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    policy, _ = build("P3", tmp_path)
    assert isinstance(policy, VerifyAllPolicy)
    policy.run(sandbox.agent, max_tool_calls=1)  # reads and interprets; no check fits the budget

    def view() -> EventStateView:
        return EventStateView.model_validate(
            sandbox.agent.call("get_event_state", arguments={}).data
        )

    def regrant(v: EventStateView, **update: Any) -> EventStateView:
        grants = tuple(
            g.model_copy(update={"grant": g.grant.model_copy(update=update)})
            if g.grant.principal_id == "agent_demo"
            else g
            for g in v.grants
        )
        return v.model_copy(update={"grants": grants})

    def relevant(v: EventStateView) -> list[tuple[str, str]]:
        return [(c.entity_id, c.fact) for c in policy.relevant_checks(v)]

    v = view()
    assert relevant(v) == [("projector", "delivery_eta"), ("backup_projector", "availability")]
    grant = own_grant(v, "agent_demo")
    assert grant is not None
    tools = tuple(t for t in grant.grant.allowed_tools if t != "query_status")
    assert relevant(regrant(v, allowed_tools=tools)) == []  # query_status not granted
    scope = tuple(r for r in grant.grant.resource_ids if r != "backup_projector")
    assert relevant(regrant(v, resource_ids=scope)) == [("projector", "delivery_eta")]
    # A typed status received after the notice answers it: nothing about it is relevant then.
    check = sandbox.agent.call(
        "query_status", arguments={"entity_id": "projector", "fact": "delivery_eta"}
    )
    assert check.status == "succeeded"
    assert relevant(view()) == []


def test_verify_all_keeps_the_retry_bound_across_runs(db: Database, tmp_path: Path) -> None:
    sb = Sandbox(db, "dev06")
    policy, _ = build("P3", tmp_path)
    first = policy.run(sb.agent, max_tool_calls=2)  # one failed check, then the run budget
    second = policy.run(sb.agent)
    attempts = [
        d.details["verify_all"]["attempt"]
        for d in _verify_all([*first.decisions, *second.decisions], "projector")
    ]
    assert attempts == [1, 2]
    own = [
        c
        for c in sb.view().status_checks
        if c.entity_id == "projector" and c.actor_id == "agent_demo"
    ]
    assert len(own) == 2


def test_verify_all_settles_after_its_own_checks(sandbox: Sandbox, tmp_path: Path) -> None:
    policy, opener = build("P3", tmp_path, _choose(()))
    assert isinstance(policy, VerifyAllPolicy)
    policy.run(sandbox.agent)
    before = (len(opener.bodies), policy.usage["tool_calls"])
    again = policy.run(sandbox.agent)  # nothing changed outside
    assert again.decisions == ()
    assert len(opener.bodies) == before[0]
    assert policy.usage["tool_calls"] == before[1] + 1  # one state read


# ---------------------------------------------------------------------------------- host


def test_a_restarted_host_keeps_the_episode_model_call_cap(db: Database, tmp_path: Path) -> None:
    sb = Sandbox(db, "dev01")
    openers: list[FakeOpener] = []

    def factory() -> Policy:
        never_done = ToolScript(lambda body, n: turn([("list_resources", {"capability": None})]))
        policy, opener = build("P1", tmp_path / f"p{len(openers)}", never_done)
        openers.append(opener)
        return policy

    caps = EpisodeCaps(max_tool_calls=48, max_model_calls=8)
    PolicyHost(db, factory, caps=caps).run(sb.episode_id, 16)
    assert len(openers[0].requests) == 6  # the turn bound of one run
    restarted = PolicyHost(db, factory, caps=caps)  # a new server on the same database
    restarted.run(sb.episode_id, 16)
    assert sum(len(o.requests) for o in openers) == caps.max_model_calls


def test_a_restarted_host_keeps_the_episode_spend(db: Database, tmp_path: Path) -> None:
    sb = Sandbox(db, "dev01")
    openers: list[FakeOpener] = []

    def factory() -> Policy:
        never_done = ToolScript(lambda body, n: turn([("list_resources", {"capability": None})]))
        opener = FakeOpener(never_done, cost=0.3)  # each call spends 0.3 of a 1.00 USD run cap
        openers.append(opener)
        cfg = make_config(tmp_path / f"p{len(openers)}", run_cap=1.0)  # its own ledger
        return ToolUsePolicy(make_provider(cfg, opener))

    caps = EpisodeCaps(max_tool_calls=48, max_model_calls=8)
    PolicyHost(db, factory, caps=caps).run(sb.episode_id, 16)
    assert len(openers[0].requests) == 3  # the per-run USD cap, not the call cap, stopped it
    restarted = PolicyHost(db, factory, caps=caps)  # a new server on the same database
    restarted.run(sb.episode_id, 16)
    assert openers[1].requests == []  # 0.90 of 1.00 USD was already spent in this episode
    last = sb.view().decisions[-1]
    assert last.details.get("failure") == "spend_cap"


@pytest.mark.parametrize("kind", ["P1", "P2", "P3"])
def test_resume_usage_seeds_the_spend_guard(kind: str, tmp_path: Path) -> None:
    policy, _ = build(kind, tmp_path)
    policy.resume_usage(2, 9, 0.42)  # type: ignore[attr-defined]
    assert policy._provider.guard.run_spent_usd == pytest.approx(0.42)  # type: ignore[attr-defined]
