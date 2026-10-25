"""The held-out cases C01-C08 and T01-T04, proven without running any compared policy.

Each case lives in ``plan_b/scenarios/private/eval/`` (``<ref>.json`` and its evaluator data
``<ref>.eval.json``) over a public fixture in ``plan_b/scenarios/public/eval/``. No P0, P1, P2
or P3 runs here. What is shown, through the real runner, store, clock engine and executor:

* every case loads through ``plan-b eval run``'s loader (``run.heldout_specs``) with the
  protocol's ids, outcome classes and negative controls;
* identifiers and agent-visible texts are opaque, and every delivered message is annotated;
* C02-C04: a coordinator that changes nothing completes the original plan (the evaluator's
  replay), and every other case fails without action;
* C01, C05, C06, C07, T01, T02: a scripted oracle action sequence reaches the goal;
* C08: after the authoritative cancellation, the frozen planner's whole enumeration is
  infeasible and the only other projection resource cannot be held under the budget;
* T03, T04: the oracle reaches the achievable limit (24, and 34 with a 6-kit deficit), and the
  tests show why nothing more is reachable;
* no evaluator field (condition, notes, evidence, annotations, case ids) and no private case
  content ahead of its time reaches an observation or a tool response: every response of every
  oracle episode is checked at its own scenario time.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from plan_b.domain.models import (
    AuthorizationRequest,
    PolicyDecision,
    PolicyRunResult,
    PublicScenario,
    ToolEnvelope,
)
from plan_b.domain.timeutil import fmt_ts
from plan_b.evaluation import manifest as mf
from plan_b.evaluation.policies.base import ToolClient
from plan_b.evaluation.run import (
    CASE_CLASSES,
    REVEALING,
    CaseRegistry,
    CaseSpec,
    heldout_specs,
    replay_original_plan,
)
from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store.database import Database
from plan_b.world.leakcheck import find_leaks

APP = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("America/New_York")
K7, R2, N4 = "2026-11-12", "2026-11-19", "2026-11-14"
DISTRIBUTION = {"start": "2026-11-14T16:00:00-05:00", "end": "2026-11-14T16:40:00-05:00"}
TARGET = "kit_target_a"
# Labels that must never appear in agent-visible text (identifiers are held to run.REVEALING).
TEXT_LABELS = (
    "false_alarm",
    "false alarm",
    "infeasib",
    "negative control",
    "held-out",
    "heldout",
    "evaluator",
    "oracle",
    "ground truth",
    "stale",
    "duplicate",
)
# Messages whose text states an earlier time than their delivery (C04's 11:40 update and its
# re-send, T03's forwarded Nov 7 note).
DATED = {"crr_msg_0907", "crr_msg_0913", "vol_fwd_rcpt_1107"}
CASE_ID = re.compile(r"(?<![A-Za-z0-9])[CT]0[1-8](?![0-9])")


def at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=TZ)


@pytest.fixture(scope="module")
def specs() -> dict[str, CaseSpec]:
    return {s.case_id: s for s in heldout_specs()}


# ---------------------------------------------------------------------------------- the oracle


@dataclass
class Turn:
    """What one oracle step may use: the client, the state it read, and a recorder."""

    client: ToolClient
    oracle: Oracle
    state: dict[str, Any]
    decisions: list[PolicyDecision] = field(default_factory=list)

    @property
    def clock(self) -> datetime:
        return datetime.fromisoformat(self.state["clock"])

    def read(self, tool: str, **arguments: Any) -> ToolEnvelope:
        return self.oracle.call(self.client, tool, arguments)

    def mutate(
        self, tool: str, *, goal_version: int | None = None, **arguments: Any
    ) -> ToolEnvelope:
        # A world event can land during the call's modeled duration: re-read and retry, as a
        # policy does after a retryable rejection.
        for _ in range(3):
            state = self.oracle.state(self.client)
            env = self.oracle.call(
                self.client,
                tool,
                arguments,
                idempotency_key=f"oracle-{len(self.oracle.envelopes):03d}",
                expected_revision=state["revision"],
                expected_goal_version=goal_version,
            )
            if env.error is None or env.error.code != "REVISION_CONFLICT":
                break
        return env

    def evaluate(self) -> dict[str, Any]:
        env = self.read("evaluate_candidates")
        assert env.status == "succeeded" and env.data is not None, env.error
        return env.data

    def commit(self, choose: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """Evaluate, choose a candidate and apply it; a revision conflict (an event during the
        call's modeled minute) means evaluating again."""
        for _ in range(3):
            evaluation = self.evaluate()
            chosen = choose(evaluation)
            env = self.oracle.call(
                self.client,
                "apply_plan",
                {
                    "candidate_plan_id": chosen["candidate_id"],
                    "constraint_report_ref": chosen["report_id"],
                },
                idempotency_key=f"oracle-{len(self.oracle.envelopes):03d}",
                expected_revision=evaluation["revision"],
                expected_goal_version=evaluation["goal_version"],
            )
            if env.error is None or env.error.code != "REVISION_CONFLICT":
                break
        assert env.receipt is not None and env.receipt.status == "applied", env.error
        return chosen

    def decide(self, kind: str, summary: str, **extra: Any) -> None:
        state = self.oracle.state(self.client)
        self.decisions.append(
            PolicyDecision(
                decision_id="pending",
                policy_id=Oracle.policy_id,
                at=datetime.fromisoformat(state["clock"]),
                revision=state["revision"],
                kind=kind,  # type: ignore[arg-type]
                summary=summary,
                **extra,
            )
        )


Step = tuple[datetime, Callable[[Turn], None]]


class Oracle:
    """A scripted evaluator coordinator: each step runs once, at the first wake at or after its
    time, through the coordinator's own client. It is a proof device, not a compared policy."""

    policy_id = "evaluator-oracle/scripted"

    def __init__(self, steps: list[Step]) -> None:
        self.steps = sorted(steps, key=lambda s: s[0])
        self.envelopes: list[ToolEnvelope] = []
        self.done: list[datetime] = []

    def call(
        self, client: ToolClient, tool: str, arguments: dict[str, Any], **kw: Any
    ) -> ToolEnvelope:
        env = client.call(tool, arguments=arguments, **kw)
        self.envelopes.append(env)
        return env

    def state(self, client: ToolClient) -> dict[str, Any]:
        env = self.call(client, "get_event_state", {})
        assert env.data is not None
        return env.data

    def run(self, client: ToolClient, max_tool_calls: int = 16) -> PolicyRunResult:
        before = len(self.envelopes)
        turn = Turn(client, self, self.state(client))
        while self.steps and self.steps[0][0] <= turn.clock:
            when, step = self.steps.pop(0)
            step(turn)
            self.done.append(when)
            turn.state = self.state(client)
        return PolicyRunResult(
            policy_id=self.policy_id,
            status="waiting",
            decisions=tuple(turn.decisions),
            tool_calls=len(self.envelopes) - before,
            wait_until=self.steps[0][0] if self.steps else None,
        )


def run_heldout(spec: CaseSpec, steps: list[Step]) -> tuple[RunResult, Oracle]:
    """One episode of a held-out case with the oracle, through the runner's own loader install
    (``CaseRegistry``) in a temporary directory."""
    oracle = Oracle(steps)
    with tempfile.TemporaryDirectory(prefix="plan_b_oracle_") as tmp:
        registry = CaseRegistry.build(Path(tmp), [spec])
        with registry.installed():
            result = run_case(
                Database(Path(tmp) / "oracle.sqlite3"), spec.case_ref, policy_factory=lambda: oracle
            )
            assert_no_leaks(spec, result, oracle.envelopes)
    assert not oracle.steps, f"oracle steps never ran: {[fmt_ts(t) for t, _ in oracle.steps]}"
    return result, oracle


def assert_no_leaks(spec: CaseSpec, result: RunResult, envelopes: list[ToolEnvelope]) -> None:
    """Each response at its own scenario time: no private marker (a record or text not yet
    delivered, a status answer not yet received, the case's description or predicates) and
    neither the case's reference nor its planning label. A marker equal to a text delivered by
    then (a message re-sent word for word) is public."""
    case = _private_case(spec)
    observations = result.final_view.observations
    for env in envelopes:
        text = env.model_dump_json()
        when = env.scenario_time
        delivered = {
            o.observation.text
            for o in observations
            if when is None or o.observation.received_at <= when
        }
        leaks = [m for m in find_leaks(text, case, observations, when) if m not in delivered]
        assert leaks == [], (spec.case_id, env.tool, when, leaks)
        assert spec.case_ref not in text, (spec.case_id, env.tool)
        assert case.planning_label not in text, (spec.case_id, env.tool)


def assert_as_expected(result: RunResult) -> None:
    report = result.report
    failed = [p.predicate_id for p in report.predicates if not p.passed]
    assert not failed and report.matches_expectation is True, (failed, report.violations)
    assert not report.violations


def candidate(evaluation: dict[str, Any], kinds: set[str]) -> dict[str, Any]:
    found = [
        c
        for c in evaluation["candidates"]
        if {e["kind"] for e in c["edits"]} == kinds and c["applicable_now"]
    ]
    assert found, [(c["label"], c["constraint_status"]) for c in evaluation["candidates"]]
    return found[0]


# ---------------------------------------------------------------------------------- loading


def test_every_protocol_case_loads_through_the_runner_loader(specs: dict[str, CaseSpec]) -> None:
    expected = {**CASE_CLASSES["campus"], **CASE_CLASSES["pantry"]}
    assert {i: s.outcome_class for i, s in specs.items()} == expected
    assert {i for i, s in specs.items() if s.negative_control} == {"C02", "C03", "C04"}
    assert all(
        s.heldout and s.negative_control_evidence for i, s in specs.items() if s.negative_control
    )
    for case_id, spec in specs.items():
        assert spec.suite == ("campus" if case_id.startswith("C") else "pantry")
        assert spec.case_file.parent == mf.HELDOUT_PRIVATE_DIR
        assert spec.public_file.parent == mf.HELDOUT_PUBLIC_DIR
        assert load_case_file(spec)["case_ref"] == spec.case_ref
        if spec.suite == "pantry":
            assert spec.target_quantity == 40
    assert specs["T03"].achievable_on_time == 24 and specs["T04"].achievable_on_time == 34
    # Twelve cases, each a private case plus evaluator data; three public fixtures.
    private = sorted(p.name for p in mf.HELDOUT_PRIVATE_DIR.glob("*.json"))
    assert len(private) == 24
    assert sorted(p.name for p in mf.HELDOUT_PUBLIC_DIR.glob("*.json")) == [
        "fixture_k7.json",
        "fixture_n4.json",
        "fixture_r2.json",
    ]


def load_case_file(spec: CaseSpec) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(spec.case_file.read_text(encoding="utf-8"))
    return data


def _visible_strings(spec: CaseSpec) -> tuple[list[str], list[str]]:
    """(identifiers, texts) an agent can come to see: the public fixture, and the private
    case's status answers, delivered events and scripted participants' messages."""
    public = json.loads(spec.public_file.read_text(encoding="utf-8"))
    case = load_case_file(spec)
    ids: list[str] = [public["scenario_id"], public["event_id"], spec.case_ref]
    texts: list[str] = []

    def walk(obj: Any, key: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, k)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)
        elif isinstance(obj, str):
            if key in ("text", "label", "description", "display_name", "reason"):
                texts.append(obj)
            elif (
                key.endswith("_id")
                or key.endswith("_ids")
                or key
                in (
                    "source_record_id",
                    "correlation_group",
                    "booking_ref",
                    "client_record_id",
                    "source_ref",
                    "terms_source_ref",
                    "capabilities",
                )
            ):
                ids.append(obj)

    walk(public)
    for record in case["status_model"]:
        walk(record.get("response") or {})
    for event in case["world_events"]:
        walk(event)
    for script in case["actor_scripts"]:
        if script["kind"] == "participant_observation":
            walk({k: script[k] for k in ("text", "client_record_id", "entity_id")})
        if script["kind"] == "staff_handoff_rule":
            ids.append(script["receipt_reference_prefix"])
        if script["kind"] == "staff_distribution_rule":
            ids.append(script["distribution_reference"])
    return ids, texts


def test_identifiers_and_agent_visible_texts_are_opaque(specs: dict[str, CaseSpec]) -> None:
    for case_id, spec in specs.items():
        ids, texts = _visible_strings(spec)
        for name in ids:
            low = name.lower()
            assert not CASE_ID.search(name), (case_id, name)
            assert not any(w in low for w in REVEALING), (case_id, name)
        for text in texts:
            low = text.lower()
            assert not CASE_ID.search(text), (case_id, text)
            assert not any(w in low for w in TEXT_LABELS), (case_id, text)
        # Delivery lag says nothing about the condition: a message is observed when it is
        # delivered unless its own text dates it earlier.
        for event in load_case_file(spec)["world_events"]:
            if event["kind"] == "message_delivery" and event["source_record_id"] not in DATED:
                assert event["observed_at"] == event["at"], (case_id, event["source_record_id"])


def test_every_delivered_message_is_annotated(specs: dict[str, CaseSpec]) -> None:
    for case_id, spec in specs.items():
        case = load_case_file(spec)
        messages = {
            e["source_record_id"] for e in case["world_events"] if e["kind"] == "message_delivery"
        }
        messages |= {
            s["client_record_id"]
            for s in case["actor_scripts"]
            if s["kind"] == "participant_observation"
        }
        annotated = {a["source_record_id"] for a in spec.annotations}
        assert messages and annotated == messages, case_id
        public = PublicScenario.model_validate_json(spec.public_file.read_text())
        for a in spec.annotations:
            assert a["event_id"] == public.event_id
            assert a["resource_id"] in {r.resource_id for r in public.resources}
        assert set(spec.actionable_record_ids) <= messages | {
            o.source_record_id for o in public.visible_observations
        }
        assert spec.requires_recovery == bool(spec.actionable_record_ids)


# ---------------------------------------------------------------------------------- campus


def test_negative_controls_keep_a_feasible_original_plan(specs: dict[str, CaseSpec]) -> None:
    for case_id, spec in specs.items():
        replay = replay_original_plan(spec)
        assert replay["original_plan_completes"] is spec.negative_control, (case_id, replay)
        assert replay["violations"] == 0 and replay["applied_plans"] == 0
    for case_id in ("C02", "C03", "C04"):
        result, oracle = run_heldout(specs[case_id], [])
        assert_as_expected(result)
        assert result.report.applied_plans == 0 and result.report.committed_cents == 0


def test_a_check_prompted_by_a_negative_control_message_gets_a_fresh_answer(
    specs: dict[str, CaseSpec],
) -> None:
    answers: dict[str, list[Any]] = {}
    for case_id in ("C02", "C03", "C04"):
        case = load_case_file(specs[case_id])
        times = sorted(
            {e["at"] for e in case["world_events"] if e["entity_id"] == "loan_projector"}
            - {e["at"] for e in case["world_events"] if e["kind"] == "resource_arrival"}
        )

        def check(turn: Turn, case_id: str = case_id) -> None:
            env = turn.read("query_status", entity_id="loan_projector", fact="delivery_eta")
            assert env.status == "succeeded" and env.data is not None, env.error
            answers.setdefault(case_id, []).append(env.data["freshness"]["stale"])

        steps: list[Step] = [(datetime.fromisoformat(t), check) for t in times]
        result, _ = run_heldout(specs[case_id], steps)
        assert_as_expected(result)
    assert answers == {"C02": [False], "C03": [False], "C04": [False, False]}, answers


def _query_and_swap(day: str, hhmm: str, *, query: bool = True) -> list[Step]:
    def step(turn: Turn) -> None:
        if query:
            env = turn.read("query_status", entity_id="loan_projector", fact="delivery_eta")
            assert env.status == "succeeded", env.error
        evaluation = turn.evaluate()
        keep = next(
            c
            for c in evaluation["candidates"]
            if c["candidate_id"] == evaluation["keep_candidate_id"]
        )
        if query:
            assert keep["constraint_status"] == "infeasible"
        turn.commit(lambda ev: candidate(ev, {"swap"}))

    return [(at(day, hhmm), step)]


@pytest.mark.parametrize(
    ("case_id", "hhmm", "query"),
    [("C01", "18:13", True), ("C05", "18:12", True), ("C06", "18:14", False)],
)
def test_a_permitted_swap_recovers_the_disrupted_cases(
    specs: dict[str, CaseSpec], case_id: str, hhmm: str, query: bool
) -> None:
    result, _ = run_heldout(specs[case_id], _query_and_swap(K7, hhmm, query=query))
    assert_as_expected(result)
    assert result.report.goal_complete and result.report.applied_plans == 1
    demos = next(a for a in result.final_view.plan.assignments if a.activity_id == "demonstrations")
    assert demos.start == at(K7, "19:00")


def test_the_standby_fallback_recovers_when_verification_is_unavailable(
    specs: dict[str, CaseSpec],
) -> None:
    def prepare(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="loan_projector", fact="delivery_eta")
        assert env.status != "succeeded"  # the order desk cannot answer all evening
        held = turn.mutate(
            "hold_resource",
            resource_id="standby_projector",
            activity_id="demonstrations",
            window={"start": fmt_ts(at(K7, "19:00")), "end": fmt_ts(at(K7, "19:20"))},
        )
        assert held.receipt is not None and held.receipt.status == "applied", held.error
        evaluation = turn.evaluate()
        chosen = next(
            c
            for c in evaluation["candidates"]
            if {e["kind"] for e in c["edits"]} == {"swap", "substitute"}
            and c["constraint_status"] != "infeasible"
        )
        turn.decide(
            "ask",
            "Ask the organizer to allow booking the standby projector (2800 cents).",
            authorization_request=AuthorizationRequest(
                request_id="oracle_req_1",
                target_grant_id="grant_coordinator_k7",
                field="max_total_committed_cents",
                current_value=0,
                requested_value=2800,
                resource_id="standby_projector",
                candidate_id=chosen["candidate_id"],
                reason="The loaned projector cannot be verified; book the standby.",
            ),
        )

    def commit(turn: Turn) -> None:
        turn.commit(lambda ev: candidate(ev, {"swap", "substitute"}))

    result, _ = run_heldout(specs["C07"], [(at(K7, "18:13"), prepare), (at(K7, "18:22"), commit)])
    assert_as_expected(result)
    assert result.report.committed_cents == 2800 and result.report.applied_plans == 1


def test_no_permitted_recovery_exists_once_the_order_is_cancelled(
    specs: dict[str, CaseSpec],
) -> None:
    evaluations: list[dict[str, Any]] = []
    holds: list[ToolEnvelope] = []

    def prove(turn: Turn) -> None:
        for entity, fact in (
            ("loan_projector", "delivery_eta"),
            ("standby_projector", "availability"),
        ):
            env = turn.read("query_status", entity_id=entity, fact=fact)
            assert env.status == "succeeded", env.error
        evaluations.append(turn.evaluate())
        for start, end in (("18:40", "19:00"), ("19:00", "19:20")):
            holds.append(
                turn.mutate(
                    "hold_resource",
                    resource_id="standby_projector",
                    activity_id="demonstrations",
                    window={"start": fmt_ts(at(R2, start)), "end": fmt_ts(at(R2, end))},
                )
            )
        turn.decide(
            "infeasible",
            "No permitted recovery: the order is cancelled and the"
            " standby booking exceeds the event budget.",
            details={"blocking_constraints": ["resource_status", "budget"]},
        )

    def again(turn: Turn) -> None:
        evaluations.append(turn.evaluate())

    result, _ = run_heldout(specs["C08"], [(at(R2, "18:12"), prove), (at(R2, "18:30"), again)])
    assert_as_expected(result)
    assert not result.report.goal_complete and result.report.infeasibility_reported
    for evaluation in evaluations:
        # The whole declared action space was enumerated: every template, no truncation.
        assert not evaluation["truncated"]
        assert evaluation["generated_count"] == evaluation["evaluated_count"] > 1
        assert set(evaluation["templates"]) == {"keep", "swap", "shift", "substitute"}
        assert evaluation["best_candidate_id"] is None
        assert evaluation["best_applicable_candidate_id"] is None
        assert {c["constraint_status"] for c in evaluation["candidates"]} == {"infeasible"}
        for c in evaluation["candidates"]:
            failed = {k["constraint_id"] for k in c["checks"] if k["status"] == "failed"}
            uses_standby = any(e["kind"] == "substitute" for e in c["edits"])
            assert ("budget" in failed) if uses_standby else ("resource_status" in failed), (
                c["label"],
                failed,
            )
    # The only other projection resource cannot be reserved at all: its 4600-cent exposure is
    # beyond the 4000-cent event budget, which no grant can raise.
    assert [h.error.code if h.error else None for h in holds] == ["BUDGET_EXCEEDED"] * 2
    public = PublicScenario.model_validate_json(specs["C08"].public_file.read_text())
    standby = next(r for r in public.resources if r.resource_id == "standby_projector")
    assert standby.terms.reserved_exposure_cents > public.goal.budget_cents
    assert [r.resource_id for r in public.resources if "projection" in r.capabilities] == [
        "loan_projector",
        "standby_projector",
    ]


# ---------------------------------------------------------------------------------- pantry


def _transfer(turn: Turn, quantity: int = 16) -> ToolEnvelope:
    return turn.mutate(
        "hold_resource",
        resource_id="neighbor_stock",
        activity_id="distribution",
        window=DISTRIBUTION,
        quantity=quantity,
        purpose="stock_transfer",
        destination_resource_id="shelf_stock",
    )


def _commit(turn: Turn, quantity: int) -> dict[str, Any]:
    held = turn.mutate(
        "hold_resource",
        resource_id="shelf_stock",
        activity_id="distribution",
        window=DISTRIBUTION,
        quantity=quantity,
        service_target_id=TARGET,
    )
    assert held.receipt is not None and held.receipt.status == "applied", held.error
    return turn.commit(
        lambda ev: next(
            c for c in ev["candidates"] if c["candidate_id"] == ev["best_applicable_candidate_id"]
        )
    )


def _code(env: ToolEnvelope) -> str | None:
    return env.error.code if env.error else None


def _stock(result: RunResult) -> dict[str, Any]:
    stock = result.final_view.stock
    assert stock is not None
    return stock.model_dump(mode="json")


def test_the_alternate_supply_meets_the_target(specs: dict[str, CaseSpec]) -> None:
    def reserve(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="neighbor_stock", fact="availability")
        assert env.status == "succeeded"
        held = _transfer(turn)
        assert held.receipt is not None and held.receipt.status == "applied", held.error

    def commit(turn: Turn) -> None:
        _commit(turn, 40)

    result, _ = run_heldout(specs["T01"], [(at(N4, "15:30"), reserve), (at(N4, "15:36"), commit)])
    assert_as_expected(result)
    stock = _stock(result)
    assert [r["quantity"] for r in stock["receipts"]] == [16]
    assert [d["quantity"] for d in stock["distributions"]] == [40]


def test_duplicate_and_adversarial_requests_add_no_second_effect(
    specs: dict[str, CaseSpec],
) -> None:
    refused: dict[str, str | None] = {}

    def reserve(turn: Turn) -> None:
        held = _transfer(turn)
        assert held.receipt is not None and held.receipt.status == "applied", held.error
        # The same logical request again, the same kits for a later slot, and the message's
        # quantities: none can reserve, credit or distribute anything more.
        refused["second_transfer"] = _code(_transfer(turn))
        refused["later_slot"] = _code(
            turn.mutate(
                "hold_resource",
                resource_id="neighbor_stock",
                activity_id="distribution",
                window={
                    "start": DISTRIBUTION["start"].replace("16:00", "16:30"),
                    "end": DISTRIBUTION["end"],
                },
                quantity=16,
                purpose="stock_transfer",
                destination_resource_id="shelf_stock",
            )
        )
        for name, quantity in (("negative", -6), ("fractional", 2.5), ("overdraw", 64)):
            refused[name] = _code(
                turn.mutate(
                    "hold_resource",
                    resource_id="shelf_stock",
                    activity_id="distribution",
                    window=DISTRIBUTION,
                    quantity=quantity,
                    service_target_id=TARGET,
                )
            )
        refused["agent_receipt"] = _code(
            turn.mutate(
                "record_stock_receipt",
                resource_id="shelf_stock",
                quantity=16,
                unit="standard_kit",
                source_observation_id="obs_neighbor_stock",
                receipt_reference="claimed_208",
                source_resource_id="neighbor_stock",
            )
        )

    def commit(turn: Turn) -> None:
        _commit(turn, 40)

    result, _ = run_heldout(specs["T02"], [(at(N4, "15:30"), reserve), (at(N4, "15:37"), commit)])
    assert_as_expected(result)
    assert all(code is not None for code in refused.values()), refused
    stock = _stock(result)
    assert [r["quantity"] for r in stock["receipts"]] == [16]
    assert [d["quantity"] for d in stock["distributions"]] == [40]
    assert len([h for h in result.final_view.holds if h.purpose == "stock_transfer"]) == 1


def test_late_supply_limits_service_to_the_kits_on_the_shelf(
    specs: dict[str, CaseSpec],
) -> None:
    refused: list[str | None] = []

    def commit(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="shelf_stock", fact="shipment_eta")
        assert env.status == "succeeded"
        refused.append(_code(_transfer(turn)))
        _commit(turn, 24)
        turn.decide(
            "infeasible",
            "Only the 24 shelf kits can be served by 16:40.",
            details={
                "blocking_constraints": ["stock_available"],
                "shortfall_quantity": 16,
                "target_id": TARGET,
            },
        )

    def retry(turn: Turn) -> None:
        refused.append(_code(_transfer(turn)))

    result, oracle = run_heldout(
        specs["T03"],
        [(at(N4, "15:30"), commit), (at(N4, "15:45"), retry), (at(N4, "15:51"), retry)],
    )
    assert_as_expected(result)
    # The limit: the neighbor desk refuses a hold for the whole handoff window, no receipt of
    # the shipment is recorded (the coordinator may not record one and no crew rule does), so
    # nothing beyond the 24 shelf kits is ever stock before 16:40.
    assert refused == ["RESOURCE_UNAVAILABLE", "RESOURCE_UNAVAILABLE", "HANDOFF_WINDOW_CLOSED"]
    stock = _stock(result)
    assert stock["receipts"] == []
    assert [d["quantity"] for d in stock["distributions"]] == [24]
    case = _private_case(specs["T03"])
    assert {s.kind for s in case.actor_scripts} == {"staff_handoff_rule", "staff_distribution_rule"}
    public = PublicScenario.model_validate_json(specs["T03"].public_file.read_text())
    agent = next(g for g in public.authority_grants if g.principal_role == "coordinator_agent")
    assert "record_stock_receipt" not in agent.allowed_tools
    eta = next(r for r in case.status_model if r.fact == "shipment_eta")
    assert eta.response is not None and eta.response.reported_eta is not None
    assert eta.response.reported_eta > public.goal.service_targets[0].deadline


def test_a_partial_handoff_leaves_a_six_kit_deficit_and_its_residual_hold(
    specs: dict[str, CaseSpec],
) -> None:
    seen: dict[str, Any] = {}

    def reserve(turn: Turn) -> None:
        held = _transfer(turn)
        assert held.receipt is not None and held.receipt.status == "applied", held.error

    def commit(turn: Turn) -> None:
        transfer = next(h for h in turn.state["holds"] if h["purpose"] == "stock_transfer")
        seen["after_handoff"] = (transfer["effective_status"], transfer["remaining_quantity"])
        _commit(turn, 34)
        turn.decide(
            "infeasible",
            "34 of 40 kits can be served; 6 are not available in time.",
            details={
                "blocking_constraints": ["stock_available"],
                "shortfall_quantity": 6,
                "target_id": TARGET,
            },
        )

    def top_up(turn: Turn) -> None:
        seen["second_transfer"] = _code(_transfer(turn, 6))

    result, _ = run_heldout(
        specs["T04"],
        [(at(N4, "15:30"), reserve), (at(N4, "15:36"), commit), (at(N4, "15:50"), top_up)],
    )
    assert_as_expected(result)
    # The crew confirmed 10 of the 16 held kits; the residual 6 stayed reserved on the transfer
    # hold until it lapsed, with no second credit.
    assert seen["after_handoff"] == ("active", 6)
    stock = _stock(result)
    assert [r["quantity"] for r in stock["receipts"]] == [10]
    assert [d["quantity"] for d in stock["distributions"]] == [34]
    transfer = [h for h in result.final_view.holds if h.purpose == "stock_transfer"]
    assert [(h.effective_status, h.remaining_quantity) for h in transfer][0] == ("expired", 6)


def test_the_crew_cap_also_holds_for_a_top_up_inside_the_window(
    specs: dict[str, CaseSpec],
) -> None:
    seen: dict[str, Any] = {}

    def reserve(turn: Turn) -> None:
        held = _transfer(turn)
        assert held.receipt is not None and held.receipt.status == "applied", held.error

    def release(turn: Turn) -> None:
        transfer = next(h for h in turn.state["holds"] if h["purpose"] == "stock_transfer")
        seen["after_handoff"] = (transfer["effective_status"], transfer["remaining_quantity"])
        env = turn.mutate(
            "release_hold", hold_id=transfer["hold_id"], reason="Hold the residual kits again."
        )
        assert env.receipt is not None and env.receipt.status == "applied", env.error

    def top_up(turn: Turn) -> None:
        held = _transfer(turn, 6)
        assert held.receipt is not None and held.receipt.status == "applied", held.error

    def commit(turn: Turn) -> None:
        _commit(turn, 34)
        turn.decide(
            "infeasible",
            "34 of 40 kits can be served; 6 are not available in time.",
            details={
                "blocking_constraints": ["stock_available"],
                "shortfall_quantity": 6,
                "target_id": TARGET,
            },
        )

    result, _ = run_heldout(
        specs["T04"],
        [
            (at(N4, "15:30"), reserve),
            (at(N4, "15:35"), release),
            (at(N4, "15:36"), top_up),
            (at(N4, "15:44"), commit),
        ],
    )
    assert_as_expected(result)
    # The second hold is accepted inside the window, but the crew confirms nothing beyond the 10
    # it already handed off: still one 10-kit receipt and 34 served.
    assert seen["after_handoff"] == ("active", 6)
    stock = _stock(result)
    assert [r["quantity"] for r in stock["receipts"]] == [10]
    assert [d["quantity"] for d in stock["distributions"]] == [34]


# ---------------------------------------------------------------------------------- isolation


def _evaluator_strings(spec: CaseSpec) -> list[str]:
    data = json.loads(spec.eval_file.read_text(encoding="utf-8")) if spec.eval_file else {}
    out = [data.get("condition"), data.get("note"), data.get("negative_control_evidence")]
    out += [a.get("note") for a in data.get("annotations", [])]
    return [s for s in out if isinstance(s, str) and len(s) >= 12]


@pytest.fixture(scope="module")
def visible_payloads(specs: dict[str, CaseSpec]) -> Iterator[dict[str, tuple[str, RunResult]]]:
    """Every tool response the coordinator received in a keep-and-read episode of each case
    (resources, every status fact the case models, the evaluation), as JSON, with the run."""
    out: dict[str, tuple[str, RunResult]] = {}
    for case_id, spec in specs.items():
        facts = sorted({(r.entity_id, r.fact) for r in _private_case(spec).status_model})

        def look(turn: Turn, facts: list[tuple[str, str]] = facts) -> None:
            turn.read("list_resources")
            for entity, fact in facts:
                turn.read("query_status", entity_id=entity, fact=fact)
            turn.evaluate()

        day = {"C08": R2}.get(case_id, N4 if case_id.startswith("T") else K7)
        times = ("15:30", "15:45", "16:41") if day == N4 else ("18:10", "18:31", "19:21")
        result, oracle = run_heldout(spec, [(at(day, t), look) for t in times])
        out[case_id] = ("\n".join(e.model_dump_json() for e in oracle.envelopes), result)
    yield out


def test_no_evaluator_field_reaches_an_observation_or_tool_response(
    specs: dict[str, CaseSpec], visible_payloads: dict[str, tuple[str, RunResult]]
) -> None:
    for case_id, spec in specs.items():
        payload, result = visible_payloads[case_id]
        assert '"observations"' in payload
        assert not CASE_ID.search(payload), case_id
        for text in _evaluator_strings(spec):
            assert text not in payload, (case_id, text[:40])
        for key in (
            '"outcome_class"',
            '"negative_control"',
            '"annotations"',
            '"case_id"',
            '"achievable_on_time"',
            '"actionable_record_ids"',
            "plan_b.eval_case",
        ):
            assert key not in payload, (case_id, key)
        # The frozen leak check over the private case: nothing that was not public by the end
        # of the episode (its description, predicates, undelivered records) is in any response.
        with (
            tempfile.TemporaryDirectory(prefix="plan_b_leaks_") as tmp,
            CaseRegistry.build(Path(tmp), [spec]).installed(),
        ):
            leaks = find_leaks(payload, _private_case(spec), result.final_view.observations, None)
        assert leaks == [], (case_id, leaks)


def _private_case(spec: CaseSpec) -> Any:
    from plan_b.domain.models import PrivateCase

    return PrivateCase.model_validate_json(spec.case_file.read_text(encoding="utf-8"))
