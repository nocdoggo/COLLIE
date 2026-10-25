"""The live workflow of the model-driven comparison policies (W2.5), with scripted models.

P1 ``tool-use/1.0.0``, P2 ``live/1.0.0`` (``agent/policies/selective.py``) and P3
``verify-all/1.0.0`` run through the real store, executor, runner and staff simulator; the model
is the real provider client with a scripted transport (``tests.test_agent_provider``), so
nothing reaches the network. Covered:

* parity within each suite (campus dev01, community skills_dev01, pantry pantry_dev01): P0-P3
  get the same candidates for the same state, the same grant, session, executor and tool
  registry, and each policy's prompts are recorded by hash;
* the live pantry: P2 completes pantry_dev01 as the baseline does (24/16 to 40/0 by one staff
  handoff, 40 committed, 40 distributed on time through the labeled staff simulator), and so do
  P1 and P3;
* the end-to-end workflow of P1, P2 and P3 on dev01 and skills_dev01;
* every bounded failure class for each of P1, P2 and P3, and P3's relevance rule.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent.interpret import INTERPRET_SCHEMA_NAME
from plan_b.agent.orchestrator import AGENT_TOOLS, LivePolicy
from plan_b.agent.policies import selective
from plan_b.agent.policies.tool_use import SCHEMA_NAME as TURN_SCHEMA
from plan_b.agent.policies.tool_use import ToolUsePolicy
from plan_b.agent.policies.verify_all import RELEVANCE_RULE, VerifyAllPolicy
from plan_b.agent.prompts import load_prompt
from plan_b.cli import main as cli_main
from plan_b.domain.models import STAFF_TOOLS, PolicyDecision
from plan_b.evaluation.policies.base import Policy
from plan_b.scenarios.policy_host import (
    POLICY_CHOICES,
    PolicyHost,
    baseline_policy_factory,
    canonical_choice,
    choice_of,
    mode_label,
    policy_factory_for,
)
from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.episodes import create_episode
from plan_b.world.world import load_case
from tests.conftest import Sandbox, at
from tests.test_agent_provider import (
    RETURNED_MODEL,
    FakeOpener,
    ScriptedModel,
    default_reading,
    make_config,
    make_provider,
    menu_ids,
    observations_of,
    reading,
    schema_name,
    section,
    state_of,
)

KINDS = ("P1", "P2", "P3")
SUITES = (("dev01", "campus"), ("skills_dev01", "community"), ("pantry_dev01", "pantry"))
PROMPTS = Path(__file__).resolve().parents[1] / "plan_b" / "agent" / "prompts"
Reply = Callable[[dict[str, Any]], Any]


# ---------------------------------------------------------------------------------- scripted models


def menu_pick(body: dict[str, Any]) -> dict[str, Any]:
    """A careful menu chooser for P2 and P3: verify, then apply, ask staff for a handoff, hold
    (not while a staff handoff is awaited), ask the organizer, keep, wait."""
    ids = menu_ids(body)
    state = state_of(body)
    cited = [r["tool_call_id"] for r in state["last_tool_results"]]
    awaited = any(
        t["status"] == "open" for t in (state.get("stock") or {}).get("staff_handoff_tasks", [])
    )
    prefer = ["query:", "apply:", "handoff:", *([] if awaited else ["hold:"]), "ask:", "keep"]
    for prefix in prefer:
        for option_id in ids:
            if option_id.startswith(prefix):
                return {
                    "option_id": option_id,
                    "rationale": f"Prefer {prefix}",
                    "cited_refs": cited,
                }
    return {"option_id": "wait", "rationale": "Nothing useful now.", "cited_refs": cited}


def turn(
    calls: Sequence[tuple[str, dict[str, Any]]] = (),
    *,
    done: bool = False,
    decision: str = "none",
    ask: dict[str, Any] | None = None,
    wait_minutes: int | None = None,
    cited: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "calls": [{"tool": t, "arguments_json": json.dumps(a)} for t, a in calls],
        "done": done,
        "decision": decision,
        "ask": ask,
        "wait_minutes": wait_minutes,
        "rationale": "Scripted tool-use turn.",
        "cited_refs": cited or [],
    }


def tool_state(body: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    content = body["messages"][1]["content"]
    return section(content, "plan_b_state"), section(content, "untrusted_observations")


def tool_user(body: dict[str, Any]) -> dict[str, Any]:
    """A competent scripted tool user (P1): check an unanswered notice's subject, check the
    pantry's shipment and alternate pool once, evaluate, then act on the evaluation."""
    if schema_name(body) != TURN_SCHEMA:
        raise AssertionError(f"unexpected schema {schema_name(body)}")
    state, observations = tool_state(body)
    resources = {r["resource_id"]: r for r in state["resources"]}
    checked = {c["entity_id"] for c in state["status_checks"] if c["status"] == "succeeded"}
    ev = state["latest_evaluation"]
    revision = state["event"]["revision"]
    stock = state.get("stock")
    queries: list[tuple[str, dict[str, Any]]] = []
    wanted = [o["entity_id"] for o in observations if o["kind"] == "notice"]
    if stock is not None:
        wanted += sorted({e["destination"] for e in stock["expected_shipments"]})
        wanted += [
            o["source_resource_id"] for o in state["stock_options"] if o["source_resource_id"]
        ]
    for rid in dict.fromkeys(wanted):
        terms = resources.get(rid, {}).get("terms", {})
        tried = any(c["entity_id"] == rid and c["by_you"] for c in state["status_checks"])
        if rid not in checked and not tried and terms.get("queryable_facts"):
            queries.append(
                ("query_status", {"entity_id": rid, "fact": terms["queryable_facts"][0]})
            )
    evaluate: tuple[str, dict[str, Any]] = (
        "evaluate_candidates",
        {"templates": None, "hypotheses": []},
    )
    if queries:
        return turn([*queries[:2], evaluate])
    if ev is None or ev["revision"] != revision:
        return turn([evaluate])
    cands = [c for c in ev["candidates"] if c["constraint_status"] == "feasible_under_assumptions"]
    cands.sort(key=lambda c: c["rank"])
    keep = next((c for c in ev["candidates"] if c["candidate_id"] == ev["keep_candidate_id"]), None)
    if stock is not None:
        return _pantry_turn(state, stock, cands, keep, evaluate)
    best = ev["best_applicable_candidate_id"]
    if best is not None and best != ev["keep_candidate_id"]:
        c = next(c for c in ev["candidates"] if c["candidate_id"] == best)
        apply = {"candidate_plan_id": c["candidate_id"], "constraint_report_ref": c["report_id"]}
        return turn([("apply_plan", apply)], done=True, decision="keep")
    if keep is not None and keep["applicable_now"]:
        return turn(done=True, decision="keep")
    return turn(done=True, decision="wait")


def _window(cand: dict[str, Any], activity: str) -> dict[str, str]:
    a = next(a for a in cand["assignments"] if a["activity_id"] == activity)
    return {"start": a["window"]["start"], "end": a["window"]["end"]}


def _pantry_turn(
    state: dict[str, Any],
    stock: dict[str, Any],
    cands: list[dict[str, Any]],
    keep: dict[str, Any] | None,
    evaluate: tuple[str, dict[str, Any]],
) -> dict[str, Any]:
    tasks = stock["staff_handoff_tasks"]
    if any(t["status"] == "open" for t in tasks):
        return turn(done=True, decision="wait")
    best = cands[0]
    if best["stock_transfers"]:
        need = best["stock_transfers"][0]
        if not tasks and need["held"] < need["quantity"]:
            hold = {
                "resource_id": need["source"],
                "activity_id": need["activity_id"],
                "window": _window(best, need["activity_id"]),
                "quantity": need["quantity"] - need["held"],
                "purpose": "stock_transfer",
                "destination_resource_id": need["destination"],
            }
            return turn([("hold_resource", hold)], done=True, decision="wait")
        best = next(c for c in cands if not c["stock_transfers"])
    if best["applicable_now"]:
        if keep is not None and keep["applicable_now"] and not best["required_stock_holds"]:
            return turn(done=True, decision="keep")
        apply = {
            "candidate_plan_id": best["candidate_id"],
            "constraint_report_ref": best["report_id"],
        }
        return turn([("apply_plan", apply)], done=True, decision="keep")
    holds = [
        (
            "hold_resource",
            {
                "resource_id": h["resource_id"],
                "activity_id": h["activity_id"],
                "window": _window(best, h["activity_id"]),
                "quantity": h["quantity"] - h["held"],
                "service_target_id": h["service_target_id"],
            },
        )
        for h in best["required_stock_holds"]
        if h["held"] < h["quantity"]
    ]
    return turn([*holds, evaluate]) if holds else turn(done=True, decision="wait")


class ToolScript:
    """``tool_user`` with per-turn overrides: ``override(body, n)`` returns a reply or None."""

    def __init__(self, override: Callable[[dict[str, Any], int], Any] | None = None) -> None:
        self.override = override
        self.n = 0

    def __call__(self, body: dict[str, Any]) -> Any:
        self.n += 1
        if self.override is not None:
            out = self.override(body, self.n)
            if out is not None:
                return out
        return tool_user(body)


# ---------------------------------------------------------------------------------- builders


def build(
    kind: str,
    tmp_path: Path,
    model: Reply | None = None,
    *,
    max_model_calls: int = 8,
    max_tool_calls: int = 48,
    run_cap: float = 1.0,
) -> tuple[Policy, FakeOpener]:
    cfg = make_config(tmp_path, run_cap=run_cap)
    if kind == "P1":
        opener = FakeOpener(model or ToolScript())
        return ToolUsePolicy(
            make_provider(cfg, opener),
            max_model_calls=max_model_calls,
            max_tool_calls=max_tool_calls,
        ), opener
    opener = FakeOpener(model or ScriptedModel(choose=menu_pick))
    cls = selective.SelectivePolicy if kind == "P2" else VerifyAllPolicy
    return cls(
        make_provider(cfg, opener), max_model_calls=max_model_calls, max_tool_calls=max_tool_calls
    ), opener


def run_with(db: Database, case: str, policy: Policy) -> RunResult:
    return run_case(db, case, policy_factory=lambda: policy)


def agent_tools(result: RunResult) -> list[str]:
    return [t.tool for t in result.history.tool_calls if t.actor_id == "agent_demo"]


def sandbox_calls(sb: Sandbox) -> list[str]:
    with sb.db.read() as conn:
        return [t.tool for t in repo.tool_calls(conn, sb.episode_id) if t.actor_id == "agent_demo"]


def plan_of(sb: Sandbox) -> tuple[Any, ...]:
    view = sb.view()
    return (
        view.plan.plan_version,
        tuple((a.activity_id, a.start, a.resource_ids) for a in view.plan.assignments),
        sb.ledger(),
        tuple((h.hold_id, h.effective_status) for h in view.holds),
    )


def failure_of(decisions: tuple[PolicyDecision, ...] | list[PolicyDecision]) -> list[Any]:
    return [d.details.get("failure") for d in decisions]


def choice_model(kind: str, choose: Reply) -> Reply:
    """``choose`` answers the choice (P2/P3) or tool turn (P1); interpretations stay careful."""
    if kind == "P1":
        return choose
    return ScriptedModel(choose=choose)


# ---------------------------------------------------------------------------------- selection


def test_policy_choices_name_p0_to_p3_and_their_labels() -> None:
    assert POLICY_CHOICES == ("rules", "tool-use", "live", "selective", "verify-all")
    assert canonical_choice("selective") == "live" and canonical_choice("tool-use") == "tool-use"
    with pytest.raises(ValueError):
        canonical_choice("oracle")
    assert selective.SelectivePolicy is LivePolicy and selective.POLICY_ID == "live/1.0.0"
    for policy_id, choice, label in (
        ("tool-use/1.0.0", "tool-use", "Tool-use agent · m/x"),
        ("live/1.0.0", "live", "Live agent · m/x"),
        ("verify-all/1.0.0", "verify-all", "Verify-all agent · m/x"),
        ("rules/1.0.0", "rules", "Deterministic policy"),
        ("pantry-rules/1.0.0", "rules", "Deterministic policy"),
    ):
        assert choice_of(policy_id) == choice
        assert mode_label(policy_id, "m/x") == label
    assert mode_label("verify-all/1.0.0", None, "m/req") == (
        "Verify-all agent · m/req (requested; no reply yet)"
    )


def test_every_model_choice_builds_its_policy_from_the_endpoint_config(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    built = {
        choice: policy_factory_for(choice, "campus_showcase", live_config=cfg)().policy_id
        for choice in POLICY_CHOICES
    }
    assert built == {
        "rules": "rules/1.0.0",
        "tool-use": "tool-use/1.0.0",
        "live": "live/1.0.0",
        "selective": "live/1.0.0",
        "verify-all": "verify-all/1.0.0",
    }
    assert policy_factory_for("rules", "pantry_continuity")().policy_id == "pantry-rules/1.0.0"


@pytest.mark.parametrize("choice", ["tool-use", "selective", "verify-all"])
def test_cli_refuses_an_unconfigured_model_policy_before_any_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    choice: str,
) -> None:
    import plan_b.agent.config as config

    def missing(*_: Any, **__: Any) -> Any:
        raise config.ModelConfigError("PLAN_B_MODEL_BASE_URL is not set")

    monkeypatch.setattr(config, "load_model_config", missing)
    db = tmp_path / "never.sqlite3"
    assert cli_main(["run-case", "dev01", "--policy", choice, "--db", str(db)]) == 2
    assert "is not configured" in capsys.readouterr().out
    assert not db.exists()


# ---------------------------------------------------------------------------------- parity


@pytest.mark.parametrize(("case", "suite"), SUITES)
def test_p0_to_p3_get_the_same_candidates_grant_and_tools_for_the_same_state(
    db: Database, tmp_path: Path, case: str, suite: str
) -> None:
    """One episode, one state: a host serving any of the policies issues the same coordinator
    session, and the shared executor returns the same evaluation through it. (What each policy
    itself reads and offers is compared in ``tests/test_policy_parity.py``.)"""
    with db.write() as conn:
        episode_id = create_episode(conn, scenario_id=load_case(case).scenario_id, case_ref=case)
        profile = repo.get_episode(conn, episode_id).profile_id

    def model_factory(kind: str) -> Callable[[], Policy]:
        return lambda: build(kind, tmp_path / kind)[0]

    factories: dict[str, Callable[[], Policy]] = {
        "P0": baseline_policy_factory(profile),
        **{k: model_factory(k) for k in KINDS},
    }
    seen: dict[str, tuple[Any, ...]] = {}
    for name, factory in factories.items():
        host = PolicyHost(db, factory)
        client = host.client(episode_id)
        state = client.call("get_event_state", arguments={})
        assert state.data is not None
        grant = next(g for g in state.data["grants"] if g["grant"]["principal_id"] == "agent_demo")
        ev = client.call("evaluate_candidates", arguments={})
        assert ev.status == "succeeded" and ev.data is not None
        candidates = tuple(
            (
                c["signature"],
                c["label"],
                c["constraint_status"],
                c["rank"],
                c["applicable_now"],
                json.dumps([c["checks"], c["required_holds"], c["authorization"]], sort_keys=True),
                json.dumps(
                    [c["required_stock_holds"], c["stock_transfers"], c["service_coverage"]],
                    sort_keys=True,
                ),
            )
            for c in ev.data["candidates"]
        )
        seen[name] = (
            client.principal_id,
            state.data["viewer"]["grant_id"],
            json.dumps(grant["grant"], sort_keys=True),
            grant["version"],
            ev.data["revision"],
            candidates,
        )
        assert set(grant["grant"]["allowed_tools"]) & set(STAFF_TOOLS) == set()
    assert len({v for v in seen.values()}) == 1, f"{suite}: the policies saw different worlds"
    assert seen["P0"][5], "the evaluation has candidates"


@pytest.mark.parametrize(("case", "suite"), SUITES)
def test_p1_to_p3_complete_each_suite_end_to_end_with_recorded_prompts(
    db: Database, tmp_path: Path, case: str, suite: str
) -> None:
    baseline = run_case(db, case)
    assert baseline.report.matches_expectation is True
    for kind in KINDS:
        policy, opener = build(kind, tmp_path / kind)
        result = run_with(db, case, policy)
        report = result.report
        assert report.matches_expectation is True, (suite, kind, report.predicates)
        assert report.goal_complete is True and report.violations == ()
        decisions = result.history.decisions
        assert {d.policy_id for d in decisions} == {policy.policy_id}
        assert (report.mode_label or "").endswith(f"· {RETURNED_MODEL}")
        # The same grant and tools as P0: only granted, never staff, control or participant.
        tools = set(agent_tools(result))
        assert tools <= set(AGENT_TOOLS) | {"list_resources"}
        assert not tools & {*STAFF_TOOLS, "update_grant", "update_goal", "check_in"}
        # Each policy's prompts are recorded by hash on every decision it made.
        expected = _prompts_for(kind, suite)
        for d in decisions:
            if d.details.get("recorded_by") == "host":
                continue
            assert d.details["prompts"] == expected, (kind, d.kind)
        calls = [c for d in decisions for c in d.details["model"]["calls"]]
        assert len(calls) == len(opener.requests) <= 8
        assert report.episode_caps is not None and report.episode_caps.max_model_calls == 8


def _prompts_for(kind: str, suite: str) -> dict[str, str]:
    def sha(name: str) -> str:
        return load_prompt(name).sha256

    if kind == "P1":
        names = ["tool_use.v2"]
    else:
        names = [
            "interpret.v1",
            "choose_action_pantry.v1" if suite == "pantry" else "choose_action.v1",
        ]
    out = {n: sha(n) for n in names}
    for n in names:
        assert (PROMPTS / f"{n}.txt").is_file()
    return out


# ---------------------------------------------------------------------------------- pantry


def _pantry_record(result: RunResult) -> dict[str, Any]:
    final = result.final_view
    stock = final.stock
    assert stock is not None
    staff = [
        (t.tool, t.envelope_status)
        for t in result.history.tool_calls
        if t.actor_id == "fictional_staff"
    ]
    return {
        "balances": {
            b.resource_id: (b.on_hand_quantity, b.reserved_quantity) for b in stock.balances
        },
        "receipts": [
            (r.kind, r.source_resource_id, r.resource_id, r.quantity) for r in stock.receipts
        ],
        "distributions": [(d.quantity, d.on_time) for d in stock.distributions],
        "service": [
            (s.target_quantity, s.on_time_quantity, s.unfulfilled_quantity) for s in stock.service
        ],
        "expected": [e.outstanding_quantity for e in stock.expected_shipments],
        "staff": staff,
        "applied_plans": result.report.applied_plans,
        "predicates": {p.predicate_id: p.passed for p in result.report.predicates},
    }


def test_the_live_policy_completes_pantry_dev01_as_the_baseline_does(
    db: Database, tmp_path: Path
) -> None:
    baseline = run_case(db, "pantry_dev01")
    policy, opener = build("P2", tmp_path)
    live = run_with(db, "pantry_dev01", policy)
    expected = _pantry_record(baseline)
    assert _pantry_record(live) == expected
    assert expected["balances"] == {"pantry_stock": (0, 0), "partner_stock": (0, 0)}
    assert expected["receipts"] == [("internal_handoff", "partner_stock", "pantry_stock", 16)]
    assert expected["distributions"] == [(40, True)] and expected["expected"] == [20]
    assert expected["staff"] == [
        ("record_stock_receipt", "succeeded"),
        ("record_distribution", "succeeded"),
    ]
    decisions = live.history.decisions
    by_kind = {d.kind: d for d in decisions}
    # The handoff request, the 40-unit hold and the apply were model choices from the menu.
    ask = by_kind["ask"]
    assert ask.details["chosen_by"] == "model" and ask.details["ask"] == "stock_handoff"
    assert ask.details["choice"]["option_id"] == "handoff:partner_stock:pantry_stock:16"
    assert "only a staff-recorded receipt moves stock" in ask.summary
    hold = by_kind["prepare"]
    assert hold.details["choice"]["option_id"] == "hold:pantry_stock:kits_40:40"
    commit = by_kind["commit"]
    assert "covers 40 of 40 kits_40 on time" in commit.summary
    assert commit.details["choice"]["option_id"].startswith("apply:")
    verified = [d.details["entity_id"] for d in decisions if d.kind == "verify"]
    assert sorted(verified) == ["pantry_stock", "partner_stock"]
    # The agent never called a staff tool; the staff simulator acted in its own session.
    assert not set(agent_tools(live)) & set(STAFF_TOOLS)
    menus = [menu_ids(b) for b in opener.bodies if schema_name(b) != INTERPRET_SCHEMA_NAME]
    assert all(not any(i.startswith(("record_", "distribute")) for i in m) for m in menus)
    assert any("handoff:partner_stock:pantry_stock:16" in m for m in menus)
    assert all(d.details["prompts"] == _prompts_for("P2", "pantry") for d in decisions)


def test_the_live_pantry_menu_offers_stock_options_from_the_adapters_candidates(
    db: Database, tmp_path: Path
) -> None:
    from plan_b.agent.menu import MenuInputs, build_menu
    from plan_b.domain.models import EvaluationResult
    from tests.test_pantry_fixture import PantrySandbox

    sb = PantrySandbox(db, "pantry_dev01")
    ev = EvaluationResult.model_validate(sb.evaluate().data)
    view = sb.view()
    menu = build_menu(view, ev, MenuInputs(principal="agent_demo", now=view.clock))
    assert menu.ids == (
        "handoff:partner_stock:pantry_stock:16",
        "hold:pantry_stock:kits_40:24",
        "wait",
    )
    handoff = menu.get("handoff:partner_stock:pantry_stock:16")
    assert handoff is not None and handoff.tool == "hold_resource"
    assert handoff.arguments["purpose"] == "stock_transfer"
    assert handoff.arguments["destination_resource_id"] == "pantry_stock"
    assert handoff.arguments["quantity"] == 16
    # Once requested, the pair is never offered again (one request per pool, as P0).
    hold = sb.hold_partner("menu-hold-partner")
    assert hold.status == "succeeded"
    ev2 = EvaluationResult.model_validate(sb.evaluate().data)
    view2 = sb.view()
    menu2 = build_menu(view2, ev2, MenuInputs(principal="agent_demo", now=view2.clock))
    assert not any(i.startswith("handoff:") for i in menu2.ids)


def test_a_partial_staff_handoff_leaves_an_honest_shortfall_for_the_live_policy(
    db: Database, tmp_path: Path
) -> None:
    baseline = run_case(db, "pantry_dev02")
    policy, _ = build("P2", tmp_path)
    live = run_with(db, "pantry_dev02", policy)
    record, expected = _pantry_record(live), _pantry_record(baseline)
    for key in ("receipts", "distributions", "service", "expected", "staff", "applied_plans"):
        assert record[key] == expected[key], key
    assert record["distributions"] == [(34, True)]
    assert record["service"] == [(40, 34, 6)]
    keep = [d for d in live.history.decisions if d.kind == "keep"]
    assert any("covers 34 of 40 kits_40 on time" in d.summary for d in keep)


# ---------------------------------------------------------------------------------- P3 relevance


def test_verify_all_checks_every_relevant_source_once_before_choosing(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    policy, opener = build("P3", tmp_path)
    assert isinstance(policy, VerifyAllPolicy)
    result = policy.run(sandbox.agent)
    checks = [d for d in result.decisions if d.details.get("verify_all")]
    assert [(d.details["entity_id"], d.details["fact"]) for d in checks] == [
        ("projector", "delivery_eta"),
        ("backup_projector", "availability"),
    ]
    assert all(d.details["verify_all"]["rule"] == RELEVANCE_RULE for d in checks)
    assert all(d.details["chosen_by"] == "server" for d in checks)
    assert "subject of unanswered notice obs_notice_01" in checks[0].summary
    assert "approved substitute of projector" in checks[1].summary
    # Both checks ran before the first choice, and that choice consumed their results.
    choices = [b for b in opener.bodies if schema_name(b) == "plan_b_menu_choice"]
    first = state_of(choices[0])
    assert {r["tool"] for r in first["last_tool_results"]} == {"query_status"}
    assert not any(i.startswith("query:") for i in menu_ids(choices[0]))
    commit = next(d for d in result.decisions if d.kind == "commit")
    assert commit.policy_id == "verify-all/1.0.0"
    # Checked once each: nothing is asked again in later runs.
    again = policy.run(sandbox.agent)
    assert not [d for d in again.decisions if d.details.get("verify_all")]


def test_verify_all_retries_a_failed_source_once_and_never_waits_for_it(
    db: Database, tmp_path: Path
) -> None:
    sb = Sandbox(db, "dev06")
    policy, _ = build("P3", tmp_path)
    result = policy.run(sb.agent)
    checks = [d for d in result.decisions if d.details.get("verify_all")]
    projector = [d for d in checks if d.details["entity_id"] == "projector"]
    assert [d.details["outcome"] for d in projector] == ["unavailable", "unavailable"]
    assert [d.details["verify_all"]["attempt"] for d in projector] == [1, 2]
    assert result.status == "waiting"
    # It decides without the source: the plan works under the claim, so it commits.
    assert "commit" in [d.kind for d in result.decisions]
    later = policy.run(sb.agent)
    assert not [d for d in later.decisions if d.details.get("entity_id") == "projector"]


def test_verify_all_on_the_pantry_checks_the_pools_of_the_gap(db: Database, tmp_path: Path) -> None:
    policy, _ = build("P3", tmp_path)
    result = run_with(db, "pantry_dev01", policy)
    checks = [d for d in result.history.decisions if d.details.get("verify_all")]
    assert sorted(d.details["entity_id"] for d in checks) == ["pantry_stock", "partner_stock"]
    assert all("supply gap" in d.summary for d in checks)
    assert result.report.matches_expectation is True


# ---------------------------------------------------------------------------------- failures


def _bad_output(kind: str) -> Reply:
    return choice_model(kind, lambda body: "not a json object")


def test_unusable_output_after_one_repair_is_a_visible_wait_for_each_policy(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    for i, kind in enumerate(KINDS):
        sb = sandbox if i == 0 else Sandbox(sandbox.db, "dev01")
        policy, opener = build(kind, tmp_path / kind, _bad_output(kind))
        before = plan_of(sb)
        result = policy.run(sb.agent)
        wait = next(d for d in result.decisions if d.details.get("failure") == "malformed_output")
        assert wait.kind == "wait" and "after the one repair attempt" in wait.summary
        schema = TURN_SCHEMA if kind == "P1" else "plan_b_menu_choice"
        assert [schema_name(b) for b in opener.bodies].count(schema) == 2, kind
        assert plan_of(sb) == before
        assert not {"hold_resource", "apply_plan", "release_hold"} & set(sandbox_calls(sb))


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("bad", ["record_distribution", "update_grant"])
def test_a_tool_or_option_outside_what_is_offered_is_refused_before_any_call(
    db: Database, tmp_path: Path, kind: str, bad: str
) -> None:
    sb = Sandbox(db, "dev01")

    def choose(body: dict[str, Any]) -> Any:
        if kind == "P1":
            return turn([(bad, {"quantity": 40})])
        return {"option_id": bad, "rationale": "Do it.", "cited_refs": []}

    policy, _ = build(kind, tmp_path, choice_model(kind, choose))
    before = plan_of(sb)
    result = policy.run(sb.agent)
    wait = next(d for d in result.decisions if d.details.get("failure") == "invalid_choice")
    assert wait.kind == "wait" and bad in wait.details["problem"]
    assert plan_of(sb) == before
    assert bad not in sandbox_calls(sb)


@pytest.mark.parametrize("kind", KINDS)
def test_an_unknown_entity_stays_unresolved_or_rejected_and_is_never_invented(
    db: Database, tmp_path: Path, kind: str
) -> None:
    sb = Sandbox(db, "dev01")
    sb.organizer.call(
        "submit_observation",
        arguments={"text": "The laser cutter for the demos will be 20 minutes late."},
        idempotency_key="org-laser",
    )
    if kind == "P1":

        def first(body: dict[str, Any], n: int) -> Any:
            if n == 1:
                return turn(
                    [("query_status", {"entity_id": "laser_cutter", "fact": "delivery_eta"})]
                )
            return turn(done=True, decision="unresolved") if n == 2 else None

        model: Reply = ToolScript(first)
    else:

        def interpret(body: dict[str, Any]) -> dict[str, Any]:
            out = []
            for obs in observations_of(body):
                if "laser" in obs["text"]:
                    out.append(
                        reading(
                            obs["observation_id"],
                            subject_id="laser_cutter",
                            change_kind="delay",
                            applicability="applies",
                            claimed_eta_local="17:20",
                        )
                    )
                else:
                    out.append(default_reading(obs))
            return {"interpretations": out}

        model = ScriptedModel(interpret=interpret, choose=menu_pick)
    policy, _ = build(kind, tmp_path, model)
    result = policy.run(sb.agent)
    if kind == "P1":
        verify = next(d for d in result.decisions if d.kind == "verify")
        assert verify.details["entity_id"] == "laser_cutter"
        assert verify.details["outcome"] != "succeeded" and verify.details["error_code"]
        assert verify.observation_refs == ()
        assert result.decisions[-1].kind == "unresolved"
    else:
        unresolved = next(d for d in result.decisions if d.kind == "unresolved")
        assert unresolved.details["failure"] == "unknown_entity"
        with sb.db.read() as conn:
            requests = json.dumps([t.request for t in repo.tool_calls(conn, sb.episode_id)])
        assert "laser_cutter" not in requests
    assert "laser_cutter" not in {r.definition.resource_id for r in sb.view().resources}


@pytest.mark.parametrize("kind", KINDS)
def test_caps_and_the_spend_guard_stop_each_policy(db: Database, tmp_path: Path, kind: str) -> None:
    sb = Sandbox(db, "dev01")
    policy, opener = build(kind, tmp_path / "m", max_model_calls=1)
    result = policy.run(sb.agent)
    assert result.status == "stopped"
    assert result.decisions[-1].details["failure"] == "model_call_cap"
    assert len(opener.requests) == 1
    assert policy.run(sb.agent).tool_calls == 0

    sb2 = Sandbox(db, "dev01")
    policy, _ = build(kind, tmp_path / "t", max_tool_calls=2)
    result = policy.run(sb2.agent)
    assert result.status == "stopped"
    assert result.decisions[-1].details["failure"] == "tool_call_cap"
    assert len(sandbox_calls(sb2)) == 2

    sb3 = Sandbox(db, "dev01")
    policy, opener = build(kind, tmp_path / "s", run_cap=0.0001)
    result = policy.run(sb3.agent)
    assert result.status == "stopped" and opener.requests == []
    assert result.decisions[-1].details["failure"] == "spend_cap"
    ledger = json.loads((tmp_path / "s" / "var" / "model_spend.json").read_text())
    assert [c["outcome"] for c in ledger["calls"]] == ["spend_cap"]


@pytest.mark.parametrize("kind", KINDS)
def test_provider_timeouts_and_errors_are_visible_waits_retried_later(
    db: Database, tmp_path: Path, kind: str
) -> None:
    sb = Sandbox(db, "dev01")
    base = ToolScript() if kind == "P1" else ScriptedModel(choose=menu_pick)
    state = {"n": 0}

    def flaky(body: dict[str, Any]) -> Any:
        state["n"] += 1
        return TimeoutError("read timed out") if state["n"] == 1 else base(body)

    policy, _ = build(kind, tmp_path / "timeout", flaky)
    before = plan_of(sb)
    first = policy.run(sb.agent)
    wait = next(d for d in first.decisions if d.details.get("failure") == "provider_timeout")
    assert wait.kind == "wait" and first.wait_until == at("16:42")
    assert plan_of(sb) == before
    second = policy.run(sb.agent)
    assert "commit" in [d.kind for d in second.decisions]

    sb2 = Sandbox(db, "dev01")

    def error(body: dict[str, Any]) -> Exception:
        return urllib.error.HTTPError(
            "https://openrouter.test",
            503,
            "Unavailable",
            None,  # type: ignore[arg-type]
            io.BytesIO(b"upstream down"),
        )

    policy, _ = build(kind, tmp_path / "http", error)
    before = plan_of(sb2)
    result = policy.run(sb2.agent)
    wait = next(d for d in result.decisions if d.details.get("failure") == "provider_error")
    assert wait.kind == "wait" and "503" in wait.summary
    assert plan_of(sb2) == before


@pytest.mark.parametrize("kind", KINDS)
def test_a_stale_revision_is_rejected_then_re_evaluated(
    db: Database, tmp_path: Path, kind: str
) -> None:
    """Before the first apply leaves the model, the facilitator checks in again (a new
    revision): the apply is rejected as stale, and a fresh evaluation leads to the commit."""
    sb = Sandbox(db, "dev01")
    fired: list[bool] = []

    def check_in() -> None:
        fired.append(True)
        env = sb.client("participant_facilitator").call(
            "check_in",
            arguments={
                "resource_id": "facilitator",
                "available": {"start": sb.clock().isoformat(), "end": at("18:00").isoformat()},
            },
            idempotency_key="ci-stale",
        )
        assert env.status == "succeeded"

    if kind == "P1":

        def stale(body: dict[str, Any], n: int) -> Any:
            out = tool_user(body)
            if not fired and any(c["tool"] == "apply_plan" for c in out["calls"]):
                check_in()
                out["done"] = False  # look at the result before ending the turn
            return out

        model: Reply = ToolScript(stale)
    else:

        def pick(body: dict[str, Any]) -> dict[str, Any]:
            out = menu_pick(body)
            if not fired and out["option_id"].startswith("apply:"):
                check_in()
            return out

        model = ScriptedModel(choose=pick)
    policy, _ = build(kind, tmp_path, model)
    result = policy.run(sb.agent)
    stale_d = next(d for d in result.decisions if d.details.get("failure") == "stale_revision")
    assert stale_d.kind == "wait" and stale_d.receipt_refs
    kinds = [d.kind for d in result.decisions]
    assert kinds.index("commit") > result.decisions.index(stale_d)
    with sb.db.read() as conn:
        applies = [r for r in repo.receipts(conn, sb.episode_id) if r.tool == "apply_plan"]
    assert [r.status for r in applies] == ["rejected", "applied"]
    assert applies[0].error_code in ("REVISION_CONFLICT", "CANDIDATE_STALE")


@pytest.mark.parametrize("kind", KINDS)
def test_a_lost_mutation_response_is_reconciled_with_its_original_key(
    db: Database, tmp_path: Path, kind: str
) -> None:
    sb = Sandbox(db, "dev01")
    lost: list[str | None] = []

    def lose(tool: str, key: str | None) -> bool:
        if tool == "apply_plan" and not lost:
            lost.append(key)
            return True
        return False

    policy, _ = build(kind, tmp_path)
    result = policy.run(sb.client("agent_demo", lose=lose))
    commit = next(d for d in result.decisions if d.kind == "commit")
    assert commit.details["reconciled"] is True and commit.details["idempotency_key"] == lost[0]
    with sb.db.read() as conn:
        applies = [r for r in repo.receipts(conn, sb.episode_id) if r.tool == "apply_plan"]
        lookups = [
            t for t in repo.tool_calls(conn, sb.episode_id) if t.tool == "get_action_receipt"
        ]
    assert [r.status for r in applies] == ["applied"]
    assert lookups and lookups[0].request["arguments"]["idempotency_key"] == lost[0]

    sb2 = Sandbox(db, "dev01")
    policy, _ = build(kind, tmp_path / "never")
    result = policy.run(
        sb2.client(
            "agent_demo", lose=lambda tool, key: tool in ("apply_plan", "get_action_receipt")
        )
    )
    reconcile = next(d for d in result.decisions if d.kind == "reconcile")
    assert reconcile.details["failure"] == "lost_response"
    assert "commit" not in [d.kind for d in result.decisions]


# ---------------------------------------------------------------------------------- P1 specifics


def test_tool_use_turns_see_real_results_and_record_server_summaries(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    policy, opener = build("P1", tmp_path)
    result = policy.run(sandbox.agent)
    turns = [b for b in opener.bodies if schema_name(b) == TURN_SCHEMA]
    assert len(turns) == 2
    schema = turns[0]["response_format"]["json_schema"]
    assert schema["strict"] is True
    tools = schema["schema"]["properties"]["calls"]["items"]["properties"]["tool"]["enum"]
    assert set(tools) == {
        "get_event_state",
        "list_resources",
        "query_status",
        "evaluate_candidates",
        "hold_resource",
        "release_hold",
        "apply_plan",
        "get_action_receipt",
    }
    second, _ = tool_state(turns[1])
    results = second["last_tool_results"]
    assert [r["tool"] for r in results] == ["query_status", "evaluate_candidates"]
    assert "17:25" in results[0]["summary"]
    verify, commit = (
        next(d for d in result.decisions if d.kind == k) for k in ("verify", "commit")
    )
    assert verify.details["choice"]["calls"][0]["tool"] == "query_status"
    assert commit.summary.startswith("Applied candidate") and commit.receipt_refs
    assert results[0]["tool_call_id"] in commit.details["choice"]["consumed_tool_call_ids"]
    assert commit.details["choice"]["rationale_untrusted"] == "Scripted tool-use turn."
    # Observation text reaches the model only inside the untrusted block.
    _, observations = tool_state(turns[0])
    assert observations[0]["observation_id"] == "obs_notice_01"
    assert re.search(r"<untrusted_observations>\n\[", turns[0]["messages"][1]["content"])


def test_tool_use_waits_without_a_model_call_when_nothing_changed(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    policy, opener = build("P1", tmp_path)
    policy.run(sandbox.agent)
    n = len(opener.requests)
    sandbox.advance(1)  # a clock tick alone is not news
    again = policy.run(sandbox.agent)
    assert len(opener.requests) == n and again.decisions == ()


def _short_of_spending(ev: dict[str, Any]) -> dict[str, Any]:
    return next(
        c
        for c in ev["candidates"]
        if c["constraint_status"] == "feasible_under_assumptions"
        and c["missing_permissions"] == ["committed_spend_limit"]
    )


def _ask_turn(pick: Callable[[dict[str, Any]], dict[str, Any]]) -> ToolScript:
    def asker(body: dict[str, Any], n: int) -> Any:
        state, _ = tool_state(body)
        ev = state["latest_evaluation"]
        if ev is None:
            return turn([("evaluate_candidates", {"templates": None, "hypotheses": []})])
        return turn(done=True, decision="ask", ask=pick(ev))

    return ToolScript(asker)


def test_tool_use_ask_is_built_and_checked_by_the_server(db: Database, tmp_path: Path) -> None:
    def good(ev: dict[str, Any]) -> dict[str, Any]:
        cand = _short_of_spending(ev)
        booking = cand["required_holds"][0]["resource_id"]
        return {
            "candidate_id": cand["candidate_id"],
            "resource_id": booking,
            "requested_value": 3500,
        }

    policy, _ = build("P1", tmp_path, _ask_turn(good))
    result = policy.run(Sandbox(db, "dev02").agent)
    ask = next(d for d in result.decisions if d.kind == "ask")
    req = ask.authorization_request
    assert req is not None and req.target_grant_id == "grant_coordinator_demo"
    assert (req.current_value, req.requested_value) == (0, 3500)
    assert req.reason.startswith("Missing permission:") and len(req.reason) <= 400

    # A corrected ask (another value) at the same revision is a new request, never a repeat.
    def lower(ev: dict[str, Any]) -> dict[str, Any]:
        return good(ev) | {"requested_value": 3400}

    policy, _ = build("P1", tmp_path / "lower", _ask_turn(lower))
    lowered = next(d for d in policy.run(Sandbox(db, "dev02").agent).decisions if d.kind == "ask")
    assert lowered.authorization_request is not None
    assert lowered.authorization_request.request_id != req.request_id

    # Refused before anything is asked: an unknown candidate, the keep candidate (it needs no
    # authority), a resource that is not the candidate's booking, and more than it needs.
    def keep(ev: dict[str, Any]) -> dict[str, Any]:
        return good(ev) | {"candidate_id": ev["keep_candidate_id"]}

    bad: list[Callable[[dict[str, Any]], dict[str, Any]]] = [
        lambda ev: good(ev) | {"candidate_id": "cand_9999"},
        keep,
        lambda ev: good(ev) | {"resource_id": "projector"},
        lambda ev: good(ev) | {"resource_id": "nowhere"},
        lambda ev: good(ev) | {"requested_value": 99999},
        lambda ev: good(ev) | {"requested_value": 0},
    ]
    for i, pick in enumerate(bad):
        policy, _ = build("P1", tmp_path / f"bad{i}", _ask_turn(pick))
        result = policy.run(Sandbox(db, "dev02").agent)
        wait = result.decisions[-1]
        assert wait.kind == "wait" and wait.details["failure"] == "invalid_choice", i
        assert all(d.authorization_request is None for d in result.decisions), i


# ---------------------------------------------------------------------------------- moderator API


@pytest.mark.parametrize(
    ("choice", "stored", "policy_id", "label"),
    [
        ("tool-use", "tool-use", "tool-use/1.0.0", "Tool-use agent"),
        ("selective", "live", "live/1.0.0", "Live agent"),
        ("live", "live", "live/1.0.0", "Live agent"),
        ("verify-all", "verify-all", "verify-all/1.0.0", "Verify-all agent"),
    ],
)
def test_the_moderator_selects_each_model_policy_by_name(
    tmp_path: Path, choice: str, stored: str, policy_id: str, label: str
) -> None:
    from fastapi.testclient import TestClient

    from plan_b.api.app import create_app

    code = "test-moderator-code"
    kinds = {"tool-use": "P1", "live": "P2", "verify-all": "P3"}

    def factories(name: Any, profile_id: str) -> Callable[[], Policy]:
        if name == "rules":
            return policy_factory_for("rules", profile_id)
        return lambda: build(kinds[name], tmp_path / "model")[0]

    app = create_app(
        tmp_path / "api.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code=code,
        web_dist=tmp_path / "no_dist",
        live_config_loader=lambda: make_config(tmp_path),
        policy_factories=factories,
    )
    c = TestClient(app)
    token = c.post("/api/auth/moderator", json={"code": code}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    loaded = c.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=auth)
    assert loaded.status_code == 200 and loaded.json()["policy"] == "rules"
    chosen = c.post("/api/moderator/policy", json={"policy": choice}, headers=auth)
    assert chosen.status_code == 200, chosen.text
    body = chosen.json()
    assert (body["policy"], body["policy_id"]) == (stored, policy_id)
    assert body["label"].startswith(f"{label} · ") and "(requested; no reply yet)" in body["label"]
    run = c.post("/api/moderator/policy/run", json={}, headers=auth).json()
    assert run["policy_id"] == policy_id
    assert run["mode_label"] == f"{label} · {RETURNED_MODEL}"
    public = c.get("/api/policy", headers=auth).json()
    assert (public["policy"], public["policy_id"]) == (stored, policy_id)
    locked = c.post("/api/moderator/policy", json={"policy": "rules"}, headers=auth)
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "POLICY_LOCKED"
    fresh = c.post(
        "/api/moderator/episodes", json={"case_ref": "dev01", "policy": choice}, headers=auth
    )
    assert fresh.status_code == 200 and fresh.json()["policy"] == stored
    refused = c.post("/api/moderator/policy", json={"policy": "oracle"}, headers=auth)
    assert refused.status_code == 422
