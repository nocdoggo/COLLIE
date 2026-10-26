"""Pantry Continuity fixtures and runtime 1.1.0 contract: the public fixture traces field by field
to the planning example, the private cases to the planning evaluator, and 1.0.0 data still
parses. ``PantrySandbox`` is the shared helper of the pantry tests: a loaded pantry episode with
a client per principal, all through the real store, sessions and executor."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.digest import file_sha256
from plan_b.domain.fixtures import load_public_scenario, public_scenario_path
from plan_b.domain.models import (
    RUNTIME_VERSION,
    ActionReceipt,
    EventStateView,
    PublicScenario,
    StaffDistributionRule,
    StaffHandoffRule,
    ToolEnvelope,
)
from plan_b.domain.timeutil import parse_ts
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.engine import advance_to
from plan_b.store.episodes import create_episode
from plan_b.store.projection_db import TRACE_VIEWER, build_view
from plan_b.store.sessions import issue_session
from plan_b.tools.client import InProcessToolClient
from plan_b.world.validate import validate_case
from plan_b.world.world import NO_CASE, load_case

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "apps" / "plan_b" / "data" / "planning" / "examples"
SCENARIO = "dev_fixture_03"
EVENT = "e_pantry_01"
DAY = "2026-11-09"
DISTRIBUTION_WINDOW = {"start": f"{DAY}T13:00:00-05:00", "end": f"{DAY}T13:40:00-05:00"}


def pt(hhmm: str) -> datetime:
    """Pantry event-local wall time (America/New_York, -05:00)."""
    return parse_ts(f"{DAY}T{hhmm}:00-05:00")


class PantrySandbox:
    """One loaded pantry episode with a client per principal (real executor). Without a case
    there is no staff simulator: staff act only through ``staff`` calls."""

    def __init__(self, db: Database, case_ref: str = NO_CASE) -> None:
        self.db = db
        with db.write() as conn:
            self.episode_id = create_episode(conn, scenario_id=SCENARIO, case_ref=case_ref)
        self._clients: dict[str, InProcessToolClient] = {}

    def client(self, principal_id: str) -> InProcessToolClient:
        if principal_id not in self._clients:
            with self.db.write() as conn:
                token, session = issue_session(conn, self.episode_id, principal_id)
            self._clients[principal_id] = InProcessToolClient(
                self.db, token, principal_id=principal_id, event_id=EVENT, grant_id=session.grant_id
            )
        return self._clients[principal_id]

    @property
    def agent(self) -> InProcessToolClient:
        return self.client("agent_demo")

    @property
    def staff(self) -> InProcessToolClient:
        return self.client("fictional_staff")

    @property
    def steward(self) -> InProcessToolClient:
        return self.client("fictional_partner_steward")

    def view(self) -> EventStateView:
        with self.db.read() as conn:
            return build_view(conn, self.episode_id, TRACE_VIEWER, visibility="audit")

    def revision(self) -> int:
        with self.db.read() as conn:
            return repo.get_episode(conn, self.episode_id).revision

    def clock(self) -> datetime:
        with self.db.read() as conn:
            return repo.get_episode(conn, self.episode_id).clock

    def advance_to(self, hhmm: str) -> None:
        with self.db.write() as conn:
            advance_to(conn, self.episode_id, pt(hhmm))

    def count(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
        with self.db.read() as conn:
            sql = f"SELECT COUNT(*) AS n FROM {table} WHERE episode_id = ?"
            if where:
                sql += f" AND {where}"
            return int(conn.execute(sql, (self.episode_id, *params)).fetchone()["n"])

    # --- stock read-outs ---------------------------------------------------------------

    def balances(self) -> dict[str, tuple[int, int, int]]:
        """pool -> (on hand, reserved, available)."""
        stock = self.view().stock
        assert stock is not None
        return {
            b.resource_id: (b.on_hand_quantity, b.reserved_quantity, b.available_quantity)
            for b in stock.balances
        }

    def counters(self) -> tuple[int, int]:
        """(supply gap, unfulfilled) of kits_40."""
        stock = self.view().stock
        assert stock is not None
        s = stock.service[0]
        return s.supply_gap_quantity, s.unfulfilled_quantity

    def conserved(self) -> bool:
        stock = self.view().stock
        assert stock is not None
        return all(b.conserved for b in stock.balances)

    # --- common flows ------------------------------------------------------------------

    def hold_partner(self, key: str, quantity: int = 16, **extra: Any) -> ToolEnvelope:
        return self.agent.call(
            "hold_resource",
            arguments={
                "resource_id": "partner_stock",
                "activity_id": "distribution",
                "window": DISTRIBUTION_WINDOW,
                "quantity": quantity,
                "purpose": "stock_transfer",
                "destination_resource_id": "pantry_stock",
                **extra,
            },
            idempotency_key=key,
            expected_revision=self.revision(),
        )

    def hold_pantry(
        self, key: str, quantity: int, client: InProcessToolClient | None = None, **extra: Any
    ) -> ToolEnvelope:
        arguments = {
            "resource_id": "pantry_stock",
            "activity_id": "distribution",
            "window": DISTRIBUTION_WINDOW,
            "quantity": quantity,
            "service_target_id": "kits_40",
        }
        arguments.update(extra)
        return (client or self.agent).call(
            "hold_resource",
            arguments=arguments,
            idempotency_key=key,
            expected_revision=self.revision(),
        )

    def handoff(
        self,
        key: str,
        hold_id: str,
        quantity: int = 16,
        *,
        reference: str = "handoff_test_001",
        client: InProcessToolClient | None = None,
        **extra: Any,
    ) -> ToolEnvelope:
        arguments = {
            "resource_id": "pantry_stock",
            "quantity": quantity,
            "unit": "standard_kit",
            "source_observation_id": "obs_partner_stock",
            "receipt_reference": reference,
            "source_resource_id": "partner_stock",
            "source_hold_id": hold_id,
        }
        arguments.update(extra)
        return (client or self.staff).call(
            "record_stock_receipt",
            arguments=arguments,
            idempotency_key=key,
            expected_revision=self.revision(),
        )

    def evaluate(self) -> ToolEnvelope:
        return self.agent.call("evaluate_candidates", arguments={})

    def apply_best(self, key: str) -> ToolEnvelope:
        env = self.evaluate()
        assert env.data is not None and env.data["best_applicable_candidate_id"] is not None
        best = next(
            c
            for c in env.data["candidates"]
            if c["candidate_id"] == env.data["best_applicable_candidate_id"]
        )
        return self.agent.call(
            "apply_plan",
            arguments={
                "candidate_plan_id": best["candidate_id"],
                "constraint_report_ref": best["report_id"],
            },
            idempotency_key=key,
            expected_revision=env.data["revision"],
            expected_goal_version=env.data["goal_version"],
        )

    def allocations(self) -> list[str]:
        stock = self.view().stock
        assert stock is not None
        return [a.allocation_id for a in stock.allocations]

    def distribute(
        self,
        key: str,
        quantity: int,
        *,
        reference: str = "distribution_test_001",
        client: InProcessToolClient | None = None,
        **extra: Any,
    ) -> ToolEnvelope:
        arguments: dict[str, Any] = {
            "resource_id": "pantry_stock",
            "quantity": quantity,
            "unit": "standard_kit",
            "service_target_id": "kits_40",
            "activity_id": "distribution",
            "distribution_reference": reference,
            "allocation_ids": self.allocations() or ["alloc_none"],
        }
        arguments.update(extra)
        return (client or self.staff).call(
            "record_distribution",
            arguments=arguments,
            idempotency_key=key,
            expected_revision=self.revision(),
            expected_goal_version=1,
        )

    def committed_40(self) -> None:
        """The canonical preparation: hold 16 partner kits, staff hand them off, hold and
        commit the 40 session kits."""
        hold = self.hold_partner("prep-hold-partner")
        assert hold.data is not None, hold.error
        received = self.handoff("prep-handoff", hold.data["hold"]["hold_id"])
        assert received.status == "succeeded", received.error
        held = self.hold_pantry("prep-hold-pantry", 40)
        assert held.status == "succeeded", held.error
        applied = self.apply_best("prep-apply")
        assert applied.status == "succeeded", applied.error


@pytest.fixture
def pantry(db: Database) -> PantrySandbox:
    return PantrySandbox(db)


def error_code(env: ToolEnvelope) -> str | None:
    return env.error.code if env.error else None


# ---------------------------------------------------------------------------
# The public fixture traces to the planning example
# ---------------------------------------------------------------------------


def _planning() -> dict[str, Any]:
    return json.loads((EXAMPLES / "pantry_continuity.public.json").read_text())


def test_public_fixture_traces_to_planning_example() -> None:
    plan = _planning()
    runtime = load_public_scenario(SCENARIO)
    assert runtime.runtime_version == RUNTIME_VERSION == "1.1.0"
    assert runtime.derived_from is not None
    assert runtime.derived_from.sha256 == file_sha256(
        str(EXAMPLES / "pantry_continuity.public.json")
    )
    assert (runtime.scenario_id, runtime.profile_id) == (plan["scenario_id"], plan["profile_id"])
    g, pg = runtime.goal, plan["goal"]
    for name in (
        "goal_id",
        "description",
        "budget_cents",
        "attendance_target",
        "fixed_venue_id",
        "version",
    ):
        assert getattr(g, name) == pg[name]
    assert list(g.required_activity_ids) == pg["required_activity_ids"]
    assert list(g.priorities) == pg["priorities"]
    assert (g.public_start, g.hard_end) == (parse_ts(pg["public_start"]), parse_ts(pg["hard_end"]))
    assert [t.model_dump(mode="json") for t in g.service_targets] == [
        {**t, "deadline": "2026-11-09T18:40:00Z"} for t in pg["service_targets"]
    ]
    st, pst = runtime.initial_state, plan["initial_state"]
    assert (st.event_id, st.revision, st.clock) == (
        pst["event_id"],
        pst["revision"],
        parse_ts(pst["clock"]),
    )
    assert (st.committed_cents, st.reserved_cents) == (
        pst["committed_cents"],
        pst["reserved_cents"],
    )
    for a, pa in zip(runtime.activities, pst["activities"], strict=True):
        assert (
            a.activity_id,
            a.label,
            a.duration_minutes,
            list(a.predecessors),
            list(a.required_resources),
            a.required,
        ) == (
            pa["activity_id"],
            pa["label"],
            pa["duration_minutes"],
            pa["predecessors"],
            pa["required_resources"],
            pa["required"],
        )
        assert (a.window.start, a.window.end) == (
            parse_ts(pa["window"]["start"]),
            parse_ts(pa["window"]["end"]),
        )
    assert st.lifecycle == () and not any(pa["started"] for pa in pst["activities"])
    for r, pr in zip(runtime.resources, pst["resources"], strict=True):
        assert (
            r.resource_id,
            r.label,
            r.kind,
            r.capacity,
            r.initial_status,
            r.source_ref,
            list(r.capabilities),
            list(r.approved_substitute_ids),
            r.terms.commitment_cost_cents,
        ) == (
            pr["resource_id"],
            pr["label"],
            pr["kind"],
            pr["capacity"],
            pr["status"],
            pr["source_ref"],
            pr["capabilities"],
            pr["approved_substitute_ids"],
            pr["booking_cost_cents"],
        )
        stock = r.consumable_stock.model_dump() if r.consumable_stock else None
        assert stock == pr.get("consumable_stock")
    for asg, pa in zip(st.assignments, pst["assignments"], strict=True):
        assert (asg.activity_id, asg.start, asg.end, list(asg.resource_ids)) == (
            pa["activity_id"],
            parse_ts(pa["start"]),
            parse_ts(pa["end"]),
            pa["resource_ids"],
        )
        assert [c.model_dump() for c in asg.consumable_allocations] == pa.get(
            "consumable_allocations", []
        )
    assert [p.model_dump() for p in st.service_progress] == pst["service_progress"]
    assert [s.model_dump(mode="json") for s in st.expected_shipments] == [
        {**s, "expected_at": "2026-11-09T17:55:00Z"} for s in pst["expected_shipments"]
    ]
    assert [c.resource_id for c in st.checked_in] == pst["checked_in_roles"]
    assert [o.model_dump(mode="json")["text"] for o in runtime.visible_observations] == [
        o["text"] for o in plan["visible_observations"]
    ]
    assert [a.model_dump() for a in runtime.declared_assumptions] == plan["declared_assumptions"]
    assert runtime.pantry_parameters is not None
    assert runtime.pantry_parameters.model_dump(mode="json") == {
        **plan["pantry_parameters"],
        "handoff_window": {"start": "2026-11-09T17:30:00Z", "end": "2026-11-09T17:50:00Z"},
    }
    # Planning grants are carried unchanged; the staff grant's role is the one recorded departure.
    by_id = {gr.grant_id: gr for gr in runtime.authority_grants}
    assert set(by_id) == {gr["grant_id"] for gr in plan["authority_grants"]}
    for pg_ in plan["authority_grants"]:
        rg = by_id[pg_["grant_id"]].model_dump(mode="json")
        expected = {**pg_, "expires_at": "2026-11-09T19:00:00Z"}
        if pg_["grant_id"] == "grant_pantry_staff":
            assert (pg_["principal_role"], rg["principal_role"]) == ("organizer", "participant")
            expected["principal_role"] = "participant"
        assert rg == expected
    agent = by_id["grant_pantry_agent"]
    assert not {"record_stock_receipt", "record_distribution"} & set(agent.allowed_tools)


def test_every_fixture_addition_is_recorded() -> None:
    runtime = load_public_scenario(SCENARIO)
    paths = " ".join(x.field_path for x in runtime.fixture_extensions)
    for added in (
        "terms",
        "checked_in",
        "principal_role",
        "principals",
        "objective_weights",
        "planning",
        "stock_options",
        "status_sources",
        "tool_durations_minutes",
    ):
        assert added in paths, added
    text = public_scenario_path(SCENARIO).read_text()
    for marker in ("never_expose_to_agent", "status_model", "S20_supplier_v2", "handoff_DEV03"):
        assert marker not in text


def test_pantry_fixture_loads_through_its_adapter_and_campus_is_unchanged() -> None:
    pantry = load_public_scenario(SCENARIO)
    assert adapter_for(pantry.profile_id).adapter_id == "pantry/1.0.0"
    assert adapter_for(pantry.profile_id).validate_config(pantry) == []
    campus = load_public_scenario("dev_fixture_01")
    # Campus fixtures stay 1.0.0 documents with none of the optional pantry fields.
    assert campus.runtime_version == "1.0.0"
    assert campus.pantry_parameters is None and campus.stock_options == ()
    assert campus.goal.service_targets == () and campus.initial_state.expected_shipments == ()
    assert all(r.consumable_stock is None for r in campus.resources)
    assert adapter_for(campus.profile_id).validate_config(campus) == []


def test_stock_contract_problems_refuse_the_load() -> None:
    raw = json.loads(public_scenario_path(SCENARIO).read_text())
    # An initial plan that allocates the same 24 kits to two activities, however far apart in
    # time, over-allocates the pool: consumable reservations do not renew with the window.
    raw["goal"]["service_targets"].append(
        {
            "target_id": "kits_late",
            "unit": "standard_kit",
            "quantity": 10,
            "deadline": "2026-11-09T14:00:00-05:00",
            "activity_id": "reconciliation",
        }
    )
    raw["initial_state"]["service_progress"].append(
        {"target_id": "kits_late", "distributed_quantity": 0}
    )
    raw["activities"][3]["required_resources"].append("pantry_stock")
    raw["initial_state"]["assignments"][3]["resource_ids"].append("pantry_stock")
    raw["initial_state"]["assignments"][3]["consumable_allocations"] = [
        {"resource_id": "pantry_stock", "quantity": 10, "service_target_id": "kits_late"}
    ]
    sc = PublicScenario.model_validate(raw)
    problems = adapter_for(sc.profile_id).validate_config(sc)
    assert any("stock_on_hand" in p and "34" in p for p in problems), problems
    bad = json.loads(public_scenario_path(SCENARIO).read_text())
    bad["resources"][2]["consumable_stock"]["expected_quantity"] = 0
    bad["goal"]["service_targets"][0]["unit"] = "family_box"
    bad["stock_options"][1]["source_resource_id"] = "pantry_stock"
    sc = PublicScenario.model_validate(bad)
    problems = adapter_for(sc.profile_id).validate_config(sc)
    assert any("outstanding shipments" in p for p in problems)
    assert any("counts family_box" in p for p in problems)
    assert any("different source" in p for p in problems)


def test_runtime_1_0_0_records_still_parse() -> None:
    trace_dir = REPO / "apps" / "plan_b" / "data" / "recorded" / "wave_1"
    trace = json.loads(next(iter(sorted(trace_dir.glob("*.json")))).read_text())
    assert trace["runtime_version"] == "1.0.0"
    final = EventStateView.model_validate(trace["final_state"])
    assert final.runtime_version == "1.0.0" and final.stock is None
    for receipt in trace["receipts"]:
        assert ActionReceipt.model_validate(receipt).runtime_version == "1.0.0"
    for call in trace["tool_calls"][:5]:
        assert ToolEnvelope.model_validate(call["envelope"]).runtime_version == "1.0.0"


def test_private_cases_trace_to_the_planning_evaluator() -> None:
    ev = json.loads((EXAMPLES / "pantry_continuity.evaluator.json").read_text())
    public = load_public_scenario(SCENARIO)
    for ref in ("pantry_dev01", "pantry_dev02"):
        case = load_case(ref)
        assert validate_case(public, case) == []
        assert case.derived_from is not None
        assert case.derived_from.sha256 == file_sha256(
            str(EXAMPLES / "pantry_continuity.evaluator.json")
        )
        eta = next(r for r in case.status_model if r.entity_id == "pantry_stock")
        payload = ev["events"][0]["payload"]
        assert eta.response is not None and eta.available_from == parse_ts(ev["events"][0]["at"])
        assert (eta.fact, eta.response.source_record_id, eta.response.shipment_id) == (
            payload["requested_fact"],
            payload["source_record_id"],
            payload["shipment_id"],
        )
        assert eta.response.reported_eta == parse_ts(payload["reported_eta"])
        kinds = [s.kind for s in case.actor_scripts]
        assert kinds == ["staff_handoff_rule", "staff_distribution_rule"]
        handoff, dist = case.actor_scripts
        assert isinstance(handoff, StaffHandoffRule) and isinstance(dist, StaffDistributionRule)
        assert handoff.label.startswith("Labeled staff simulator")
        assert dist.label.startswith("Labeled staff simulator")
        assert dist.at == parse_ts(ev["events"][2]["at"])
        # Opaque physical references: a public trace carries no case label (the evaluator's
        # references embed DEV03).
        assert ev["events"][2]["payload"]["distribution_reference"].startswith("distribution_")
        assert dist.distribution_reference == "distribution_001"
        assert handoff.receipt_reference_prefix == "handoff"
    partial, canonical = (load_case(r).actor_scripts[0] for r in ("pantry_dev02", "pantry_dev01"))
    assert isinstance(partial, StaffHandoffRule) and isinstance(canonical, StaffHandoffRule)
    assert (partial.max_quantity, canonical.max_quantity) == (10, None)


def test_case_validation_rejects_a_staff_rule_outside_its_grant() -> None:
    public = load_public_scenario(SCENARIO)
    case = load_case("pantry_dev01")
    scripts = list(case.actor_scripts)
    scripts[0] = scripts[0].model_copy(update={"principal_id": "fictional_partner_steward"})
    scripts[1] = scripts[1].model_copy(update={"principal_id": "agent_demo"})
    problems = validate_case(public, case.model_copy(update={"actor_scripts": tuple(scripts)}))
    assert any("may not record stock receipts" in p for p in problems)
    assert any("may not record distributions" in p for p in problems)
