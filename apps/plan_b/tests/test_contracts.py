"""Contract traceability: runtime fixtures and conventions versus the planning bundle 0.2.0."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from plan_b.domain.digest import file_sha256, request_digest
from plan_b.domain.fixtures import load_public_scenario, public_scenario_path
from plan_b.domain.timeutil import parse_ts
from plan_b.world.world import available_cases, case_path, load_case
from tests.test_planning_map import FORMATS

REPO = Path(__file__).resolve().parents[3]
PLAN = REPO / "PEEAI_plan"
EXAMPLES = PLAN / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def test_digest_convention_reproduces_planning_example() -> None:
    request = _load("commit_request.json")
    receipt = _load("commit_receipt.json")
    assert request_digest(request) == receipt["request_digest"]


def test_planning_examples_still_validate_unchanged() -> None:
    schema = json.loads((PLAN / "schemas/planning.schema.json").read_text())
    # FORMATS adds a strict RFC 3339 date-time check (the default checker skips date-time).
    validator = Draft202012Validator(schema, format_checker=FORMATS)
    paths = sorted(EXAMPLES.glob("*.json"))
    assert len(paths) == 11
    for path in paths:
        validator.validate(json.loads(path.read_text()))


def test_runtime_public_fixture_traces_to_planning_fixture() -> None:
    planning = _load("campus_showcase.public.json")
    runtime = load_public_scenario()
    assert runtime.derived_from is not None
    assert runtime.derived_from.sha256 == file_sha256(str(EXAMPLES / "campus_showcase.public.json"))
    g, pg = runtime.goal, planning["goal"]
    for field in (
        "goal_id",
        "description",
        "budget_cents",
        "attendance_target",
        "fixed_venue_id",
        "version",
    ):
        assert getattr(g, field) == pg[field]
    assert list(g.required_activity_ids) == pg["required_activity_ids"]
    assert g.public_start == parse_ts(pg["public_start"]) and g.hard_end == parse_ts(pg["hard_end"])
    st, pst = runtime.initial_state, planning["initial_state"]
    assert (st.revision, st.clock) == (pst["revision"], parse_ts(pst["clock"]))
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
        assert a.window.start == parse_ts(pa["window"]["start"])
    for r, pr in zip(runtime.resources, pst["resources"], strict=True):
        assert (
            r.resource_id,
            r.label,
            r.kind,
            r.capacity,
            r.initial_status,
            list(r.capabilities),
            list(r.approved_substitute_ids),
            r.terms.commitment_cost_cents,
        ) == (
            pr["resource_id"],
            pr["label"],
            pr["kind"],
            pr["capacity"],
            pr["status"],
            pr["capabilities"],
            pr["approved_substitute_ids"],
            pr["booking_cost_cents"],
        )
    for a, pa in zip(st.assignments, pst["assignments"], strict=True):
        assert (a.activity_id, a.start, a.end, list(a.resource_ids)) == (
            pa["activity_id"],
            parse_ts(pa["start"]),
            parse_ts(pa["end"]),
            pa["resource_ids"],
        )
    assert [o.model_dump(mode="json")["text"] for o in runtime.visible_observations] == [
        o["text"] for o in planning["visible_observations"]
    ]
    # Planning grants are carried unchanged; extensions are additional grants only.
    by_id = {gr.grant_id: gr for gr in runtime.authority_grants}
    for pg_ in planning["authority_grants"]:
        rg = by_id[pg_["grant_id"]]
        assert rg.max_total_committed_cents == pg_["max_total_committed_cents"]
        assert rg.max_total_reserved_cents == pg_["max_total_reserved_cents"]
        assert list(rg.allowed_tools) == pg_["allowed_tools"]
        assert (
            list(rg.resource_ids) == pg_["resource_ids"] and rg.principal_id == pg_["principal_id"]
        )
    coordinator = by_id["grant_coordinator_demo"]
    assert (
        "check_in" not in coordinator.allowed_tools
        and "submit_observation" not in coordinator.allowed_tools
    )
    assert {x.extension_id for x in runtime.fixture_extensions} >= {
        "x04_presenter_host_grants",
        "x05_organizer_grant",
    }
    backup = next(r for r in runtime.resources if r.resource_id == "backup_projector")
    assert (
        backup.terms.hold_max_minutes,
        backup.terms.reserved_exposure_cents,
        backup.terms.hold_fee_cents,
    ) == (10, 3500, 0)


def test_dev01_private_case_traces_to_planning_evaluator() -> None:
    ev = _load("campus_showcase.evaluator.json")
    case = load_case("dev01")
    assert case.derived_from is not None
    assert case.derived_from.sha256 == file_sha256(str(EXAMPLES / "campus_showcase.evaluator.json"))
    status = next(r for r in case.status_model if r.entity_id == "projector")
    payload = ev["events"][0]["payload"]
    assert status.response is not None
    assert status.response.reported_eta == parse_ts(payload["reported_eta"])
    assert status.response.source_record_id == payload["source_record_id"]
    assert status.available_from == parse_ts(ev["events"][0]["at"])
    arrival = case.world_events[0]
    assert arrival.at == parse_ts(ev["events"][1]["at"])
    assert arrival.source_record_id == ev["events"][1]["payload"]["source_record_id"]


def test_private_cases_are_opaque_and_separate() -> None:
    assert available_cases() == [
        "dev01",
        "dev02",
        "dev04",
        "dev05",
        "dev06",
        "pantry_dev01",
        "pantry_dev02",
        "skills_dev01",
        "skills_dev02",
    ]
    for ref in available_cases():
        assert case_path(ref).name == f"{ref}.json"  # no revealing file names
        assert load_case(ref).never_expose_to_agent is True
    public_text = public_scenario_path("dev_fixture_01").read_text()
    for marker in (
        "never_expose_to_agent",
        "status_model",
        "world_events",
        "outcome_predicates",
        "receipt_P17",
    ):
        assert marker not in public_text
