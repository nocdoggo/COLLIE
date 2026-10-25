"""Pantry Continuity end to end on the shared core (W2.3): the planned four-step sequence
through the executor with real staff sessions, the runner cases with the labeled staff
simulator, a sanitized trace that verifies intact, and the HTTP staff path.

The shared pantry core is the same executor, grants, receipts, clock, snapshots and trace
format as the campus event: nothing here forks them."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plan_b.api.app import create_app
from plan_b.cli import main as cli_main
from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.models import STAFF_TOOLS, TRACE_VERSION
from plan_b.evaluation.export_trace import build_trace, verify_trace, write_trace
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import (
    ScriptedActors,
    audit_view,
    baseline_policy_factory,
    run_case,
    tick_loop,
)
from plan_b.store.database import Database
from plan_b.store.projection_db import build_snapshot
from plan_b.world.leakcheck import find_leaks
from plan_b.world.world import load_case
from tests.test_pantry_fixture import DISTRIBUTION_WINDOW, EVENT, SCENARIO, PantrySandbox, pt

PKG = Path(__file__).resolve().parents[1] / "plan_b"
FORBIDDEN = (
    "plan_b.world",
    "plan_b.store",
    "plan_b.scenarios",
    "plan_b.tools",
    "plan_b.api",
    "plan_b.evaluation.scoring",
    "plan_b.evaluation.export_trace",
)


@pytest.fixture
def pantry(db: Database) -> PantrySandbox:
    # The case answers status queries; without the runner no staff simulator is scheduled, so
    # every staff action below is an explicit call through the staff's own session.
    return PantrySandbox(db, "pantry_dev01")


# ---------------------------------------------------------------------------
# The four-step sequence
# ---------------------------------------------------------------------------


def test_four_step_sequence_with_staff_sessions(pantry: PantrySandbox) -> None:
    agent = pantry.agent
    # 1. The agent queries current alternate availability and holds the 16 partner kits.
    eta = agent.call(
        "query_status", arguments={"entity_id": "pantry_stock", "fact": "shipment_eta"}
    )
    assert eta.status == "succeeded" and eta.data is not None
    assert eta.data["observation"]["structured"]["shipment_id"] == "S20"
    assert pantry.view().resources[2].status == "available"  # an ETA never moves the pool
    alternate = agent.call(
        "query_status", arguments={"entity_id": "partner_stock", "fact": "availability"}
    )
    assert alternate.status == "succeeded"
    stock = pantry.view().stock
    assert stock is not None
    assert stock.expected_shipments[0].reported_eta == pt("14:10")
    revision = pantry.revision()
    hold = pantry.hold_partner("step1-hold")
    assert hold.receipt is not None and hold.receipt.status == "applied"
    assert (hold.receipt.revision_before, hold.receipt.revision_after) == (revision, revision + 1)
    hold_id = hold.data["hold"]["hold_id"] if hold.data else ""
    assert pantry.balances()["partner_stock"] == (16, 16, 0)
    assert pantry.counters() == (16, 40)  # nothing moved, nobody served
    # 2. Staff record the receipt: one transaction debits, closes the hold, credits.
    revision = pantry.revision()
    receipt = pantry.handoff("step2-handoff", hold_id, reference="handoff_001")
    assert receipt.receipt is not None and receipt.receipt.actor_id == "fictional_staff"
    assert receipt.receipt.revision_after == revision + 1
    assert pantry.balances() == {"pantry_stock": (40, 0, 40), "partner_stock": (0, 0, 0)}
    assert pantry.counters() == (0, 40)
    stock = pantry.view().stock
    assert stock is not None and stock.expected_shipments[0].outstanding_quantity == 20
    # 3. The agent reserves the 40 session kits, refreshes, and applies under its grant.
    assert pantry.hold_pantry("step3-hold", 40).status == "succeeded"
    applied = pantry.apply_best("step3-apply")
    assert applied.receipt is not None and applied.receipt.actor_id == "agent_demo"
    assert applied.data is not None and len(applied.data["allocation_ids"]) == 1
    assert pantry.balances()["pantry_stock"] == (40, 40, 0)
    assert pantry.counters() == (0, 40)  # committed, not achieved
    # 4. Staff record the on-time distribution at the deadline.
    pantry.advance_to("13:40")
    dist = pantry.distribute("step4-dist", 40, reference="distribution_001")
    assert dist.receipt is not None and dist.receipt.executed_at == pt("13:40")
    assert pantry.balances() == {"pantry_stock": (0, 0, 0), "partner_stock": (0, 0, 0)}
    assert pantry.counters() == (0, 0)
    stock = pantry.view().stock
    assert stock is not None
    assert stock.service[0].on_time_quantity == 40 and stock.service[0].attained
    assert stock.expected_shipments[0].outstanding_quantity == 20  # S20 still unreceived
    assert pantry.conserved()
    # The staff tools left one applied receipt each, by staff, each moving the revision by one.
    staff_receipts = [r for r in pantry.view().receipts if r.tool in STAFF_TOOLS]
    assert [(r.tool, r.actor_id, r.revision_after - r.revision_before) for r in staff_receipts] == [
        ("record_stock_receipt", "fictional_staff", 1),
        ("record_distribution", "fictional_staff", 1),
    ]
    causes = {t.revision: (t.cause_kind, t.cause_ref) for t in pantry.view().transitions}
    assert causes[staff_receipts[0].revision_after] == ("stock_received", "srec_0001")
    assert causes[staff_receipts[1].revision_after] == ("stock_distributed", "dist_0001")


# ---------------------------------------------------------------------------
# The runner cases
# ---------------------------------------------------------------------------


def test_runner_case_dev01_reaches_the_target_through_staff(db: Database) -> None:
    result = run_case(db, "pantry_dev01")
    report = result.report
    assert report.policy_id == "pantry-rules/1.1.0"
    assert report.matches_expectation and report.goal_complete
    assert all(p.passed for p in report.predicates), [p for p in report.predicates if not p.passed]
    assert [(s.target_id, s.on_time_quantity, s.unfulfilled_quantity) for s in report.service] == [
        ("kits_40", 40, 0)
    ]
    assert {s.resource_id: s.closing_on_hand_quantity for s in report.stock} == {
        "pantry_stock": 0,
        "partner_stock": 0,
    }
    assert report.staff_confirmations == 2 and report.unnecessary_reservations == 0
    final = result.final_view
    assert final.stock is not None
    assert [r.receipt_reference for r in final.stock.receipts] == ["handoff_001"]
    assert [d.distribution_reference for d in final.stock.distributions] == ["distribution_001"]
    # The coordinator never called a staff-only tool; the staff simulator acted in its session.
    calls = result.history.tool_calls
    assert not [c for c in calls if c.actor_id == "agent_demo" and c.tool in STAFF_TOOLS]
    assert {c.actor_id for c in calls if c.tool in STAFF_TOOLS} == {"fictional_staff"}
    logged = [a for a in result.actor_log if a["receipt_status"] == "applied"]
    assert [a["tool"] for a in logged] == ["record_stock_receipt", "record_distribution"]
    assert [a["executed_at"] for a in logged] == ["2026-11-09T17:37:00Z", "2026-11-09T18:40:00Z"]


def test_runner_case_dev02_reports_the_partial_handoff_shortfall(db: Database) -> None:
    result = run_case(db, "pantry_dev02")
    report = result.report
    assert report.matches_expectation and not report.goal_complete
    assert report.infeasibility_reported and report.violations == ()
    assert [
        (s.on_time_quantity, s.unfulfilled_quantity, s.supply_gap_quantity) for s in report.service
    ] == [(34, 6, 6)]
    assert {s.resource_id: s.closing_on_hand_quantity for s in report.stock} == {
        "pantry_stock": 0,
        "partner_stock": 6,
    }
    shortfall = next(d for d in report_decisions(result) if d.kind == "infeasible")
    assert shortfall.details["shortfall_quantity"] == 6
    assert result.final_view.goal.service_targets[0].quantity == 40  # the target is unchanged
    assert all(s.conserved for s in report.stock)


def report_decisions(result: Any) -> list[Any]:
    return list(result.final_view.decisions)


def test_runner_is_deterministic(tmp_path: Path) -> None:
    first = run_case(Database(tmp_path / "a.sqlite3"), "pantry_dev01").report
    second = run_case(Database(tmp_path / "b.sqlite3"), "pantry_dev01").report
    drop = {"episode_id"}
    assert first.model_dump(exclude=drop) == second.model_dump(exclude=drop)


def test_completion_distribution_and_next_start_order_at_the_inclusive_deadline(
    db: Database,
) -> None:
    result = run_case(db, "pantry_dev01")
    at_deadline = [
        (t.cause_kind, t.cause_ref) for t in result.final_view.transitions if t.at == pt("13:40")
    ]
    assert (
        at_deadline.index(("activity_completed", "distribution"))
        < at_deadline.index(("stock_distributed", "dist_0001"))
        < at_deadline.index(("activity_started", "reconciliation"))
    )
    stock = result.final_view.stock
    assert stock is not None and stock.distributions[0].on_time


# ---------------------------------------------------------------------------
# Trace export, verification and the public/private boundary
# ---------------------------------------------------------------------------


def test_trace_export_verifies_intact_and_carries_no_private_input(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run_case(db, "pantry_dev01")
    trace = build_trace(db, result.episode_id, policy_id=result.report.policy_id)
    assert trace["trace_version"] == TRACE_VERSION and verify_trace(trace) == []
    assert trace["source"]["profile_id"] == "pantry_continuity"
    assert trace["source"]["policy_id"] == "pantry-rules/1.1.0"
    assert trace["final_state"]["stock"]["service"][0]["on_time_quantity"] == 40
    path = write_trace(trace, tmp_path / "traces" / "pantry_trace.json")
    capsys.readouterr()
    assert cli_main(["verify-trace", str(path)]) == 0
    assert capsys.readouterr().out.strip() == "intact"
    text = path.read_text()
    case = load_case("pantry_dev01")
    assert find_leaks(text, case, audit_view(db, result.episode_id).observations, None) == []
    for marker in ("pantry_dev01", "DEV03", "token", "join_code", "max_quantity"):
        assert marker not in text, marker
    tampered = json.loads(text)
    tampered["final_state"]["stock"]["balances"][0]["on_hand_quantity"] = 99
    assert verify_trace(tampered)


def test_policy_and_planner_inputs_exclude_private_data(db: Database) -> None:
    sb = PantrySandbox(db, "pantry_dev02")
    host = PolicyHost(db, baseline_policy_factory("pantry_continuity"))
    actors = ScriptedActors(db, sb.episode_id, load_case("pantry_dev02").actor_scripts)
    actors.schedule_initial()
    tick_loop(db, host, sb.episode_id, minutes=None, run_policy=True, actors=actors)
    client = host.client(sb.episode_id)
    assert client.calls
    final = audit_view(db, sb.episode_id)
    case = load_case("pantry_dev02")
    for env in client.calls:
        leaks = find_leaks(env.model_dump_json(), case, final.observations, env.scenario_time)
        assert leaks == [], (env.tool, env.scenario_time, leaks)
        assert env.tool not in STAFF_TOOLS
    with db.read() as conn:
        snap = build_snapshot(conn, sb.episode_id)
    assert find_leaks(snap.model_dump_json(), case, final.observations, snap.clock) == []


@pytest.mark.parametrize(
    "module",
    ["evaluation/policies/pantry_rules.py", "domain/adapters/pantry.py", "domain/stock.py"],
)
def test_pantry_policy_and_planner_cannot_reach_private_input(module: str) -> None:
    path = PKG / module
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    bad = [m for m in imports if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)]
    assert bad == [], f"{module} imports {bad}"
    text = path.read_text()
    assert "PrivateCase" not in text and "scenarios/private" not in text and "open(" not in text


# ---------------------------------------------------------------------------
# HTTP: a staff tab acts through its own session
# ---------------------------------------------------------------------------


def test_staff_actions_over_http(tmp_path: Path) -> None:
    code = "pantry-moderator-code"
    app = create_app(
        tmp_path / "api.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code=code,
        web_dist=tmp_path / "none",
    )
    c = TestClient(app)
    mod = c.post("/api/auth/moderator", json={"code": code}).json()["token"]
    auth = {"Authorization": f"Bearer {mod}"}
    loaded = c.post(
        "/api/moderator/episodes",
        json={"scenario_id": SCENARIO, "case_ref": "pantry_dev01"},
        headers=auth,
    )
    assert loaded.status_code == 200, loaded.text

    def join(principal: str) -> str:
        r = c.post("/api/moderator/sessions", json={"principal_id": principal}, headers=auth)
        assert r.status_code == 200, r.text
        return str(c.post("/api/auth/join", json={"code": r.json()["join_code"]}).json()["token"])

    staff, steward = join("fictional_staff"), join("fictional_partner_steward")
    state = c.get("/api/state", headers={"Authorization": f"Bearer {staff}"}).json()
    assert state["stock"]["service"][0]["supply_gap_quantity"] == 16
    assert state["pantry_parameters"]["handoff_duration_minutes"] == 2

    def tool(token: str, name: str, arguments: dict[str, Any], **extra: Any) -> Any:
        body = {"tool": name, "event_id": EVENT, "arguments": arguments, **extra}
        return c.post(f"/api/tools/{name}", json=body, headers={"Authorization": f"Bearer {token}"})

    hold = tool(
        staff,
        "hold_resource",
        {
            "resource_id": "partner_stock",
            "activity_id": "distribution",
            "window": DISTRIBUTION_WINDOW,
            "quantity": 16,
            "purpose": "stock_transfer",
            "destination_resource_id": "pantry_stock",
        },
        idempotency_key="http-hold",
        expected_revision=state["revision"],
    )
    assert hold.status_code == 200 and hold.json()["status"] == "succeeded", hold.text
    hold_id = hold.json()["data"]["hold"]["hold_id"]
    receipt_args = {
        "resource_id": "pantry_stock",
        "quantity": 16,
        "unit": "standard_kit",
        "source_observation_id": "obs_partner_stock",
        "receipt_reference": "handoff_http_001",
        "source_resource_id": "partner_stock",
        "source_hold_id": hold_id,
    }
    revision = hold.json()["revision"]
    denied = tool(
        steward,
        "record_stock_receipt",
        receipt_args,
        idempotency_key="http-steward",
        expected_revision=revision,
    )
    assert denied.status_code == 200 and denied.json()["error"]["code"] == "GRANT_REQUIRED"
    bad = tool(
        staff,
        "record_stock_receipt",
        {**receipt_args, "quantity": 2.5},
        idempotency_key="http-bad",
        expected_revision=revision,
    )
    assert bad.status_code == 400
    ok = tool(
        staff,
        "record_stock_receipt",
        receipt_args,
        idempotency_key="http-receipt",
        expected_revision=revision,
    )
    assert ok.status_code == 200 and ok.json()["status"] == "succeeded", ok.text
    after = c.get("/api/state", headers=auth).json()
    balances = {b["resource_id"]: b["on_hand_quantity"] for b in after["stock"]["balances"]}
    assert balances == {"pantry_stock": 40, "partner_stock": 0}


# ---------------------------------------------------------------------------
# Readiness and outcome scoring through the adapter
# ---------------------------------------------------------------------------


def test_readiness_reports_stock_in_both_modes_but_does_not_gate_the_start(db: Database) -> None:
    sb = PantrySandbox(db, "pantry_dev01")
    view = sb.view()
    preview = next(a for a in view.activities if a.definition.activity_id == "distribution")
    assert preview.readiness is not None and preview.readiness.mode == "preview"
    assert any("pantry_stock: 24 standard_kit on hand" in m for m in preview.readiness.met)
    adapter = adapter_for("pantry_continuity")
    with db.read() as conn:
        snap = build_snapshot(conn, sb.episode_id)
    execution = adapter.check_readiness(snap, "distribution", pt("13:00"), mode="execution")
    # Predecessors have not completed at load, so execution readiness is not met; the pool is
    # reported, never an unmet start condition.
    assert not execution.ready and all("pantry_stock" not in u for u in execution.unmet)
    # Without any commitment the session still starts at 13:00 and serves nobody.
    sb.advance_to("13:05")
    lifecycles = {a.definition.activity_id: a.lifecycle for a in sb.view().activities}
    assert lifecycles["distribution"] == "started"
    stock = sb.view().stock
    assert stock is not None and stock.service[0].qualified_minutes == 0


def test_outcome_scoring_flags_unattested_and_agent_records(db: Database) -> None:
    result = run_case(db, "pantry_dev01")
    adapter = adapter_for("pantry_continuity")
    clean = adapter.score_outcome(result.final_view, result.history)
    assert clean.goal_attained and clean.violations == ()
    final = result.final_view
    assert final.stock is not None
    receipts = tuple(
        r.model_copy(update={"actor_role": "coordinator_agent"})
        if r.tool == "record_distribution"
        else r
        for r in final.receipts
    )
    forged = final.model_copy(update={"receipts": receipts})
    history = result.history.model_copy(update={"receipts": receipts})
    flagged = adapter.score_outcome(forged, history)
    assert [v.category for v in flagged.violations] == ["attestation_by_agent"]
    orphan = final.stock.distributions[0].model_copy(update={"receipt_id": "rcpt_missing"})
    broken = final.model_copy(
        update={
            "stock": final.stock.model_copy(
                update={
                    "distributions": (orphan,),
                    "balances": tuple(
                        b.model_copy(update={"conserved": False}) for b in final.stock.balances
                    ),
                }
            )
        }
    )
    categories = [v.category for v in adapter.score_outcome(broken, result.history).violations]
    assert categories.count("stock_not_conserved") == 2
    assert "unattested_stock_record" in categories
