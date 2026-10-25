"""The fresh held-out set C09-C12 and T05-T06 (Wave 3b), proven without running any policy.

The twelve Wave 3 cases are spent. These six were authored against the frozen v1.1 code by a
worker that never saw a v1.2 policy change, to give version 1.2 a small new held-out check.
They live in ``plan_b/scenarios/private/eval/set2/`` (``<ref>.json`` and ``<ref>.eval.json``)
over the public fixtures in ``plan_b/scenarios/public/eval/set2/``, or in the parent
directories once the lock step moves them there. The frozen loader's protocol table
(``run.CASE_CLASSES``, ``run.NEGATIVE_CONTROLS``) names only C01-C08 and T01-T04, so these tests
extend it inside the test process when the code does not yet. No P0, P1, P2 or P3 runs here.
What is shown, through the real runner, store, clock engine and executor:

* every case loads through ``plan-b eval run``'s loader (``run.heldout_specs``) with its
  protocol condition, outcome class and C10 as the negative control;
* identifiers and agent-visible texts are opaque, every delivered message is annotated, and no
  text, record id, resource id or world is shared with a development or a spent held-out case;
* C10: a coordinator that changes nothing completes the original plan (the evaluator's replay),
  every other case fails without action, and a check prompted by its warning is fresh;
* C09 (a shift, or the spare booked with approval), C11 (a swap) and T05 (one handoff): a
  scripted oracle action sequence reaches the goal;
* C12: after the withdrawn order, the frozen planner's whole enumeration is infeasible, the
  spare failing on its commitment cutoff while money would allow it;
* T06: the oracle reaches the achievable limit of 24 and the tests show why nothing more is
  reachable;
* no evaluator field (condition, notes, evidence, annotations, case ids) and no private case
  content ahead of its time reaches an observation or a tool response.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from plan_b.domain.models import AuthorizationRequest, PublicScenario, ToolEnvelope
from plan_b.domain.timeutil import fmt_ts
from plan_b.evaluation import manifest as mf
from plan_b.evaluation import run as eval_run
from plan_b.evaluation.run import REVEALING, CaseRegistry, CaseSpec, replay_original_plan
from plan_b.scenarios.runner import RunResult
from plan_b.world.leakcheck import find_leaks
from plan_b.world.world import available_cases
from tests.test_heldout_cases import (
    TEXT_LABELS,
    Step,
    Turn,
    _code,
    _evaluator_strings,
    _private_case,
    _stock,
    _visible_strings,
    assert_as_expected,
    at,
    candidate,
    load_case_file,
    run_heldout,
)

W5, H3, P6 = "2026-12-03", "2026-12-10", "2026-12-05"
DISTRIBUTION = {"start": "2026-12-05T10:10:00-05:00", "end": "2026-12-05T10:50:00-05:00"}
TARGET = "kits_morning"
FRESH = {
    "campus": {"C09": "goal", "C10": "goal", "C11": "goal", "C12": "infeasible"},
    "pantry": {"T05": "target", "T06": "partial"},
}
FRESH_NEGATIVE_CONTROLS = frozenset({"C10"})
CONDITIONS = {
    "C09": "C01",
    "C10": "C03",
    "C11": "C06",
    "C12": "C08",
    "T05": "T01",
    "T06": "T03",
}
# T06's portal auto-forward dates itself 8:05 a.m.; every other message is observed on delivery.
DATED = {"portal_pod_0805"}
CASE_ID = re.compile(r"(?<![A-Za-z0-9])[CT](0[1-9]|1[0-2])(?![0-9])")


def _dirs() -> tuple[Path, Path]:
    """The staged ``set2`` directories, or the held-out directories once the cases move there."""
    private, public = mf.HELDOUT_PRIVATE_DIR / "set2", mf.HELDOUT_PUBLIC_DIR / "set2"
    if private.is_dir():
        return private, public
    return mf.HELDOUT_PRIVATE_DIR, mf.HELDOUT_PUBLIC_DIR


def _load(private: Path, public: Path) -> list[CaseSpec]:
    """``run.heldout_specs`` with the fresh ids in the protocol table (unchanged if the code
    already names them, and then with the same classes)."""
    classes = {suite: dict(ids) for suite, ids in eval_run.CASE_CLASSES.items()}
    for suite, ids in FRESH.items():
        for case_id, outcome_class in ids.items():
            assert classes[suite].setdefault(case_id, outcome_class) == outcome_class
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(eval_run, "CASE_CLASSES", classes)
        mp.setattr(
            eval_run, "NEGATIVE_CONTROLS", eval_run.NEGATIVE_CONTROLS | FRESH_NEGATIVE_CONTROLS
        )
        return eval_run.heldout_specs(private, public)


@pytest.fixture(scope="module")
def specs() -> dict[str, CaseSpec]:
    found = {s.case_id: s for s in _load(*_dirs())}
    fresh = {i for ids in FRESH.values() for i in ids}
    return {i: found[i] for i in sorted(fresh)}


SPENT = frozenset({f"C0{i}" for i in range(1, 9)} | {f"T0{i}" for i in range(1, 5)})


@pytest.fixture(scope="module")
def spent() -> list[CaseSpec]:
    """The twelve Wave 3 cases (a loader that also finds ``set2/`` returns more)."""
    found = [s for s in eval_run.heldout_specs() if s.case_id in SPENT]
    assert len(found) == 12
    return found


# ---------------------------------------------------------------------------------- loading


def test_every_fresh_case_loads_through_the_runner_loader(specs: dict[str, CaseSpec]) -> None:
    private, public = _dirs()
    assert {i: s.outcome_class for i, s in specs.items()} == {**FRESH["campus"], **FRESH["pantry"]}
    assert {i for i, s in specs.items() if s.negative_control} == {"C10"}
    assert (specs["C10"].negative_control_evidence or "").strip()
    for case_id, spec in specs.items():
        assert spec.heldout
        assert spec.suite == ("campus" if case_id.startswith("C") else "pantry")
        assert spec.case_file.parent == private and spec.public_file.parent == public
        assert load_case_file(spec)["case_ref"] == spec.case_ref
        if spec.suite == "pantry":
            assert spec.target_quantity == 40
    assert specs["T05"].achievable_on_time == 40 and specs["T06"].achievable_on_time == 24
    assert {i for i, s in specs.items() if s.requires_recovery} == {"C09", "C11", "T05"}
    if private.name == "set2":
        # Six cases with their evaluator data and three public fixtures, staged beside (not in)
        # the v1.1 held-out directories, whose non-recursive v1.1 loader never sees them.
        assert len(list(private.glob("*.json"))) == 12
        assert sorted(p.name for p in public.glob("*.json")) == [
            "fixture_h3.json",
            "fixture_p6.json",
            "fixture_w5.json",
        ]


def test_each_fresh_case_keeps_its_protocol_condition(
    specs: dict[str, CaseSpec], spent: list[CaseSpec]
) -> None:
    by_id = {s.case_id: s for s in spent}
    for case_id, protocol_id in CONDITIONS.items():
        if protocol_id in by_id:
            assert specs[case_id].condition == by_id[protocol_id].condition, case_id
            assert specs[case_id].outcome_class == by_id[protocol_id].outcome_class


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


def _strings(spec: CaseSpec) -> tuple[set[str], set[str], set[str], str]:
    """(message and status texts, record ids, public names, world digest) of one case. The
    event model's labels (activities, roles) are shared by design and not compared."""
    case = _private_case(spec)
    public = PublicScenario.model_validate_json(spec.public_file.read_text())
    texts = {r.response.text for r in case.status_model if r.response is not None}
    texts |= {e.text for e in case.world_events}
    texts |= {a.text for a in case.actor_scripts if a.kind == "participant_observation"}
    texts |= {o.text for o in public.visible_observations} | {public.goal.description}
    records = {r.response.source_record_id for r in case.status_model if r.response is not None}
    records |= {e.source_record_id for e in case.world_events}
    records |= {o.source_record_id for o in public.visible_observations}
    named = {r.resource_id for r in public.resources} | {public.event_id, public.scenario_id}
    named |= {p.principal_id for p in public.principals}
    named |= {g.grant_id for g in public.authority_grants}
    return set(texts), records, named, eval_run._world_digest(case)


def test_no_text_identifier_or_world_is_shared_with_a_development_or_spent_case(
    specs: dict[str, CaseSpec], spent: list[CaseSpec]
) -> None:
    others = list(spent) + [eval_run.development_spec(ref) for ref in available_cases()]
    seen_texts: set[str] = set()
    seen_records: set[str] = set()
    seen_named: set[str] = set()
    worlds: set[str] = set()
    for spec in others:
        texts, records, named, world = _strings(spec)
        seen_texts |= texts
        seen_records |= records
        seen_named |= named
        worlds.add(world)
    shared_actor_ids = {"p_front_host", "p_demo_presenter", "p_swap_facilitator"}
    for case_id, spec in specs.items():
        texts, records, named, world = _strings(spec)
        assert not texts & seen_texts, (case_id, texts & seen_texts)
        assert not records & seen_records, (case_id, records & seen_records)
        assert not (named - shared_actor_ids) & seen_named, (case_id, named & seen_named)
        assert world not in worlds, case_id


def test_recovery_terms_differ_from_the_spent_fixtures(specs: dict[str, CaseSpec]) -> None:
    def load(name: str) -> PublicScenario:
        path = mf.HELDOUT_PUBLIC_DIR / f"{name}.json"
        return PublicScenario.model_validate_json(path.read_text())

    k7, n4 = load("fixture_k7"), load("fixture_n4")
    w5 = PublicScenario.model_validate_json(specs["C09"].public_file.read_text())
    h3 = PublicScenario.model_validate_json(specs["C12"].public_file.read_text())
    p6 = PublicScenario.model_validate_json(specs["T05"].public_file.read_text())

    def spare(s: PublicScenario) -> Any:
        return next(r for r in s.resources if r.terms.booking_required).terms

    old = spare(k7)
    for s, cutoff in ((w5, 25), (h3, 75)):
        terms = spare(s)
        assert terms.commitment_cost_cents == 3500 != old.commitment_cost_cents
        assert terms.hold_max_minutes == 15 != old.hold_max_minutes
        assert terms.commitment_cutoff_minutes_before_use == cutoff
        assert cutoff != old.commitment_cutoff_minutes_before_use
        assert s.goal.budget_cents == 9000 != k7.goal.budget_cents
        # The skills exchange comes first, with a 10-minute slack before the fixed closing.
        order = [a.activity_id for a in sorted(s.initial_state.assignments, key=lambda a: a.start)]
        assert order == ["setup", "welcome", "skills_exchange", "demonstrations", "closing"]
    assert p6.pantry_parameters is not None and n4.pantry_parameters is not None
    assert p6.pantry_parameters.handoff_duration_minutes == 4
    assert n4.pantry_parameters.handoff_duration_minutes == 3
    window = p6.pantry_parameters.handoff_window
    assert (window.end - window.start).total_seconds() == 24 * 60


# ---------------------------------------------------------------------------------- campus


def test_only_the_negative_control_keeps_a_feasible_original_plan(
    specs: dict[str, CaseSpec],
) -> None:
    for case_id, spec in specs.items():
        replay = replay_original_plan(spec)
        assert replay["original_plan_completes"] is spec.negative_control, (case_id, replay)
        assert replay["violations"] == 0 and replay["applied_plans"] == 0
    result, _ = run_heldout(specs["C10"], [])
    assert_as_expected(result)
    assert result.report.applied_plans == 0 and result.report.committed_cents == 0


def test_a_check_prompted_by_the_warning_gets_a_fresh_answer(specs: dict[str, CaseSpec]) -> None:
    answers: list[Any] = []

    def check(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="lent_projector", fact="delivery_eta")
        assert env.status == "succeeded" and env.data is not None, env.error
        answers.append(env.data["freshness"]["stale"])

    # At the warning and after the order desk's second record: both answers are fresh.
    steps: list[Step] = [(at(W5, "17:21"), check), (at(W5, "17:31"), check)]
    result, _ = run_heldout(specs["C10"], steps)
    assert_as_expected(result)
    assert answers == [False, False], answers


def _shift(evaluation: dict[str, Any], activity: str, offset: int) -> dict[str, Any]:
    found = [
        c
        for c in evaluation["candidates"]
        if c["applicable_now"]
        and [(e["kind"], e["activity_ids"], e["offset_minutes"]) for e in c["edits"]]
        == [("shift", [activity], offset)]
    ]
    assert found, [(c["label"], c["constraint_status"]) for c in evaluation["candidates"]]
    return found[0]


def _assignment(result: RunResult, activity: str) -> Any:
    return next(a for a in result.final_view.plan.assignments if a.activity_id == activity)


def test_a_permitted_shift_recovers_the_delayed_delivery(specs: dict[str, CaseSpec]) -> None:
    seen: dict[str, Any] = {}

    def step(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="lent_projector", fact="delivery_eta")
        assert env.status == "succeeded", env.error
        evaluation = turn.evaluate()
        for c in evaluation["candidates"]:
            if c["candidate_id"] == evaluation["keep_candidate_id"]:
                seen["keep"] = c["constraint_status"]
            elif [e["kind"] for e in c["edits"]] == ["swap"]:
                seen["swap"] = c["constraint_status"]
        turn.commit(lambda ev: _shift(ev, "demonstrations", 10))

    result, _ = run_heldout(specs["C09"], [(at(W5, "17:16"), step)])
    assert_as_expected(result)
    # Keeping the plan or swapping the slots needs the projector before it can arrive.
    assert seen == {"keep": "infeasible", "swap": "infeasible"}
    assert result.report.goal_complete and result.report.applied_plans == 1
    assert result.report.committed_cents == 0
    assert _assignment(result, "demonstrations").start == at(W5, "18:10")
    assert _assignment(result, "closing").start == at(W5, "18:30")


def test_the_spare_booked_with_approval_is_a_second_permitted_path(
    specs: dict[str, CaseSpec],
) -> None:
    def prepare(turn: Turn) -> None:
        held = turn.mutate(
            "hold_resource",
            resource_id="spare_projector",
            activity_id="demonstrations",
            window={"start": fmt_ts(at(W5, "18:00")), "end": fmt_ts(at(W5, "18:20"))},
        )
        assert held.receipt is not None and held.receipt.status == "applied", held.error
        evaluation = turn.evaluate()
        chosen = next(
            c
            for c in evaluation["candidates"]
            if [e["kind"] for e in c["edits"]] == ["substitute"]
            and c["constraint_status"] != "infeasible"
        )
        turn.decide(
            "ask",
            "Ask the organizer to allow booking the spare projector (3500 cents).",
            authorization_request=AuthorizationRequest(
                request_id="oracle_req_1",
                target_grant_id="grant_coordinator_w5",
                field="max_total_committed_cents",
                current_value=0,
                requested_value=3500,
                resource_id="spare_projector",
                candidate_id=chosen["candidate_id"],
                reason="The lent projector reaches the room after its 6:00 slot.",
            ),
        )

    def commit(turn: Turn) -> None:
        turn.commit(lambda ev: candidate(ev, {"substitute"}))

    result, _ = run_heldout(specs["C09"], [(at(W5, "17:17"), prepare), (at(W5, "17:26"), commit)])
    assert_as_expected(result)
    assert result.report.committed_cents == 3500 and result.report.applied_plans == 1
    assert _assignment(result, "demonstrations").start == at(W5, "18:00")


def test_a_permitted_swap_recovers_the_late_facilitator(specs: dict[str, CaseSpec]) -> None:
    def step(turn: Turn) -> None:
        turn.commit(lambda ev: candidate(ev, {"swap"}))

    result, _ = run_heldout(specs["C11"], [(at(W5, "17:24"), step)])
    assert_as_expected(result)
    assert result.report.goal_complete and result.report.applied_plans == 1
    assert _assignment(result, "demonstrations").start == at(W5, "17:40")
    assert _assignment(result, "skills_exchange").start == at(W5, "18:00")


def test_no_permitted_recovery_exists_once_the_order_is_withdrawn(
    specs: dict[str, CaseSpec],
) -> None:
    evaluations: list[dict[str, Any]] = []

    def prove(turn: Turn) -> None:
        for entity, fact in (
            ("lent_projector", "delivery_eta"),
            ("spare_projector", "availability"),
        ):
            env = turn.read("query_status", entity_id=entity, fact=fact)
            assert env.status == "succeeded", env.error
        evaluations.append(turn.evaluate())
        turn.decide(
            "infeasible",
            "No permitted recovery: the lent projector is withdrawn and the spare cannot be"
            " confirmed 75 minutes before any demonstrations start.",
            details={"blocking_constraints": ["resource_status", "commitment_cutoff"]},
        )

    def again(turn: Turn) -> None:
        evaluations.append(turn.evaluate())

    result, _ = run_heldout(specs["C12"], [(at(H3, "17:12"), prove), (at(H3, "17:30"), again)])
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
            uses_spare = any(e["kind"] == "substitute" for e in c["edits"])
            assert ("commitment_cutoff" in failed) if uses_spare else ("resource_status" in failed)
            # Money is not the blocker: the event budget and the organizer's rule cover it.
            assert "budget" not in failed, (c["label"], failed)
    public = PublicScenario.model_validate_json(specs["C12"].public_file.read_text())
    spare = next(r for r in public.resources if r.resource_id == "spare_projector")
    assert spare.terms.reserved_exposure_cents <= public.goal.budget_cents
    scripts = _private_case(specs["C12"]).actor_scripts
    rule = next(s for s in scripts if s.kind == "organizer_authorization_rule")
    assert rule.max_committed_cents >= spare.terms.commitment_cost_cents
    # The latest demonstrations start (18:10) needs confirmation by 16:55, before the opening.
    demos = next(a for a in public.activities if a.activity_id == "demonstrations")
    latest = demos.window.end.timestamp() - demos.duration_minutes * 60
    assert spare.terms.commitment_cutoff_minutes_before_use == 75
    cutoff = latest - 75 * 60
    assert cutoff < public.initial_state.clock.timestamp()
    assert [r.resource_id for r in public.resources if "projection" in r.capabilities] == [
        "lent_projector",
        "spare_projector",
    ]


# ---------------------------------------------------------------------------------- pantry


def _transfer(turn: Turn, quantity: int = 16) -> ToolEnvelope:
    return turn.mutate(
        "hold_resource",
        resource_id="loft_rack",
        activity_id="distribution",
        window=DISTRIBUTION,
        quantity=quantity,
        purpose="stock_transfer",
        destination_resource_id="main_rack",
    )


def _commit(turn: Turn, quantity: int) -> dict[str, Any]:
    held = turn.mutate(
        "hold_resource",
        resource_id="main_rack",
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


def test_the_loft_stock_meets_the_target(specs: dict[str, CaseSpec]) -> None:
    def reserve(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="loft_rack", fact="availability")
        assert env.status == "succeeded"
        held = _transfer(turn)
        assert held.receipt is not None and held.receipt.status == "applied", held.error

    def commit(turn: Turn) -> None:
        _commit(turn, 40)

    result, _ = run_heldout(specs["T05"], [(at(P6, "09:40"), reserve), (at(P6, "09:48"), commit)])
    assert_as_expected(result)
    stock = _stock(result)
    assert [r["quantity"] for r in stock["receipts"]] == [16]
    assert [d["quantity"] for d in stock["distributions"]] == [40]


def test_late_supply_limits_service_to_the_kits_on_the_main_rack(
    specs: dict[str, CaseSpec],
) -> None:
    refused: list[str | None] = []

    def commit(turn: Turn) -> None:
        env = turn.read("query_status", entity_id="main_rack", fact="shipment_eta")
        assert env.status == "succeeded"
        refused.append(_code(_transfer(turn)))
        _commit(turn, 24)
        turn.decide(
            "infeasible",
            "Only the 24 kits on the main rack can be served by 10:50.",
            details={
                "blocking_constraints": ["stock_available"],
                "shortfall_quantity": 16,
                "target_id": TARGET,
            },
        )

    def retry(turn: Turn) -> None:
        refused.append(_code(_transfer(turn)))

    result, _ = run_heldout(
        specs["T06"],
        [(at(P6, "09:40"), commit), (at(P6, "09:55"), retry), (at(P6, "10:02"), retry)],
    )
    assert_as_expected(result)
    # The limit: the loft desk refuses a hold for the whole handoff window, no receipt of the
    # delivery is recorded (the coordinator may not record one and no crew rule does), so
    # nothing beyond the 24 rack kits is ever stock before 10:50.
    assert refused == ["RESOURCE_UNAVAILABLE", "RESOURCE_UNAVAILABLE", "HANDOFF_WINDOW_CLOSED"]
    stock = _stock(result)
    assert stock["receipts"] == []
    assert [d["quantity"] for d in stock["distributions"]] == [24]
    case = _private_case(specs["T06"])
    assert {s.kind for s in case.actor_scripts} == {"staff_handoff_rule", "staff_distribution_rule"}
    public = PublicScenario.model_validate_json(specs["T06"].public_file.read_text())
    agent = next(g for g in public.authority_grants if g.principal_role == "coordinator_agent")
    assert "record_stock_receipt" not in agent.allowed_tools
    eta = next(r for r in case.status_model if r.fact == "shipment_eta")
    assert eta.response is not None and eta.response.reported_eta is not None
    assert eta.response.reported_eta > public.goal.service_targets[0].deadline


# ---------------------------------------------------------------------------------- isolation


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

        day = {"C12": H3}.get(case_id, P6 if case_id.startswith("T") else W5)
        times = ("09:40", "09:58", "10:51") if day == P6 else ("17:10", "17:31", "18:31")
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
        with (
            tempfile.TemporaryDirectory(prefix="plan_b_leaks_") as tmp,
            CaseRegistry.build(Path(tmp), [spec]).installed(),
        ):
            leaks = find_leaks(payload, _private_case(spec), result.final_view.observations, None)
        assert leaks == [], (case_id, leaks)


def test_the_evaluator_note_stays_out_of_the_agent_visible_tree(specs: dict[str, CaseSpec]) -> None:
    note = mf.HELDOUT_PRIVATE_DIR / "README_set2.md"
    assert note.is_file()
    text = note.read_text(encoding="utf-8")
    for case_id, spec in specs.items():
        assert case_id in text and spec.case_ref in text
    for spec in specs.values():
        public = json.loads(spec.public_file.read_text(encoding="utf-8"))
        assert "README_set2" not in json.dumps(public)
