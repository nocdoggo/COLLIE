"""Policy fixes of the Wave 3 freeze audit (development-only variants built in a scratch dir).

* P1: a wake the model asked for (its ``wait_minutes``) is its own model turn, as P2's open
  claim keeps P2 called; before, the attention rule recorded a server ``keep`` instead and the
  model was next called at the 17:05 deadline watch (audit A1).
* P1: a timed wake reads the evaluation again when it was made at an earlier scenario time at
  the same revision; before, the handoff window's opening reused a "too early" evaluation and
  P1 never requested the handoff (audit B1).
* P2/P3: a status check answers a notice as of its request time, so a check still in flight when
  a notice arrives does not answer it; P3 checks that notice's subject again (audit A2).
* P0: a transfer hold rejected for a retryable reason (a revision conflict at the window's
  opening) is retried, as an apply is; before, P0 gave the handoff up (audit B2).
* P0-P3: a shortfall only a handoff could close is held back until the window opens only while
  that handoff could still serve the target; a window opening after the deadline no longer
  delays the report past the service (audit B3).

The real store, executor, runner and labeled staff simulator; the models are scripted.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

import plan_b.domain.fixtures as fixtures
import plan_b.world.world as world
from plan_b.domain.stock import handoff_still_possible
from plan_b.domain.timeutil import parse_ts
from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store.database import Database
from tests.test_agent_provider import (
    ScriptedModel,
    default_reading,
    observations_of,
    reading,
)
from tests.test_live_workflow import ToolScript, build, menu_pick, run_with, tool_user, turn

PANTRY_DAY = "2026-11-09"
CAMPUS_DAY = "2026-11-05"


def _pantry(hhmm: str) -> datetime:
    return parse_ts(f"{PANTRY_DAY}T{hhmm}:00-05:00")


def _campus(hhmm: str) -> datetime:
    return parse_ts(f"{CAMPUS_DAY}T{hhmm}:00-05:00")


@pytest.fixture
def private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A scratch private directory holding the development cases; variants are added to it."""
    target = tmp_path / "private"
    target.mkdir()
    for path in world.PRIVATE_DIR.glob("*.json"):
        (target / path.name).write_text(path.read_text())
    monkeypatch.setattr(world, "PRIVATE_DIR", target)
    world.load_case.cache_clear()
    yield target
    world.load_case.cache_clear()


def _window_variant(
    private: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, start: str, end: str
) -> str:
    """pantry_dev01 with another handoff window (its predicates as they are)."""
    original = fixtures.public_scenario_path
    scenario = json.loads(original("dev_fixture_03").read_text())
    scenario["pantry_parameters"]["handoff_window"] = {
        "start": f"{PANTRY_DAY}T{start}:00-05:00",
        "end": f"{PANTRY_DAY}T{end}:00-05:00",
    }
    variant = tmp_path / f"window_{start.replace(':', '')}.public.json"
    variant.write_text(json.dumps(scenario))
    monkeypatch.setattr(
        fixtures,
        "public_scenario_path",
        lambda sid: variant if sid == "dev_fixture_03" else original(sid),
    )
    ref = f"pantry_dev_window_{start.replace(':', '')}"
    case = json.loads((private / "pantry_dev01.json").read_text())
    case |= {
        "case_ref": ref,
        "planning_label": "DEV03-WINDOW",
        "description": f"Development only: pantry_dev01 with the handoff window {start}-{end}.",
        "derived_from": None,
    }
    (private / f"{ref}.json").write_text(json.dumps(case))
    world.load_case.cache_clear()
    return ref


def _served(result: RunResult) -> int:
    view = result.final_view
    assert view.stock is not None
    return sum(s.on_time_quantity for s in view.stock.service)


def _handoffs(result: RunResult) -> list[Any]:
    return [
        t
        for t in result.history.tool_calls
        if t.actor_id == "agent_demo"
        and t.tool == "hold_resource"
        and t.request.get("arguments", {}).get("purpose") == "stock_transfer"
    ]


# ---------------------------------------------------------------------------------- P1 wakes


def test_p1_is_called_when_the_time_it_asked_for_comes(
    db: Database, tmp_path: Path, private: Path
) -> None:
    """dev01: the model's first turn waits three minutes; it is called again then (not first at
    the 17:05 deadline watch) and repairs the plan long before the demonstrations."""

    def defer(body: dict[str, Any], n: int) -> Any:
        return turn(done=True, decision="wait", wait_minutes=3) if n == 1 else None

    policy, opener = build("P1", tmp_path / "p1", ToolScript(defer))
    result = run_with(db, "dev01", policy)
    assert result.report.matches_expectation is True
    second = [d for d in result.history.decisions if d.details.get("model", {}).get("calls")][1]
    assert second.details["chosen_by"] == "model"
    assert second.at < _campus("16:50"), second
    commit = next(d for d in result.history.decisions if d.kind == "commit")
    assert commit.at < _campus("16:50")
    assert len(opener.requests) >= 3


def test_p1_reads_the_evaluation_again_when_the_handoff_window_opens(
    db: Database, tmp_path: Path, private: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Window 12:39-12:47 and no state change between P1's last evaluation (12:36, after its
    commit) and the opening: the opening's wake evaluates again, finds the handoff, calls the
    model, and all 40 kits are served."""
    ref = _window_variant(private, tmp_path, monkeypatch, "12:39", "12:47")

    def reread(body: dict[str, Any], n: int) -> Any:
        reply = tool_user(body)
        if reply["done"] and reply["decision"] == "keep" and reply["calls"]:
            reply["calls"].append(
                {
                    "tool": "evaluate_candidates",
                    "arguments_json": json.dumps({"templates": None, "hypotheses": []}),
                }
            )
        return reply

    policy, _ = build("P1", tmp_path / "p1", ToolScript(reread))
    result = run_with(db, ref, policy)
    requests = _handoffs(result)
    assert requests and all(t.requested_at >= _pantry("12:39") for t in requests)
    assert _served(result) == 40
    assert not [d for d in result.history.decisions if d.kind == "infeasible"]


# ---------------------------------------------------------------------------------- P2/P3 answers


def test_a_check_in_flight_when_a_notice_arrives_does_not_answer_it(
    db: Database, tmp_path: Path, private: Path
) -> None:
    """dev01 with a cancellation notice at 16:41, while P3's 16:40 projector check is in
    flight: that check answers as of 16:40, so P3's relevance rule checks the projector again
    (requested at or after 16:41)."""
    case = json.loads((private / "dev01.json").read_text())
    case["case_ref"] = "dev01_inflight"
    case["world_events"].insert(
        0,
        {
            "at": f"{CAMPUS_DAY}T16:41:00-05:00",
            "kind": "message_delivery",
            "entity_id": "projector",
            "observation_kind": "notice",
            "source_id": "delivery_contact",
            "source_record_id": "delivery_message_17b",
            "correlation_group": "projector_delivery_01",
            "observed_at": f"{CAMPUS_DAY}T16:41:00-05:00",
            "authority_scope": "self_report",
            "text": "Update on order P17: today's projector delivery has been cancelled.",
        },
    )
    (private / "dev01_inflight.json").write_text(json.dumps(case))
    world.load_case.cache_clear()

    def interpret(body: dict[str, Any]) -> dict[str, Any]:
        out = []
        for o in observations_of(body):
            if "cancelled" in o["text"]:
                out.append(
                    reading(
                        o["observation_id"],
                        subject_id="projector",
                        change_kind="unavailability",
                        applicability="applies",
                        order_ref="P17",
                        interpretation="Cancellation claim.",
                        unresolved_fields=["current delivery status"],
                        proposed_checks=["query_status"],
                    )
                )
            else:
                out.append(default_reading(o))
        return {"interpretations": out}

    policy, _ = build("P3", tmp_path / "p3", ScriptedModel(interpret=interpret, choose=menu_pick))
    result = run_with(db, "dev01_inflight", policy)
    checks = [
        t
        for t in result.history.tool_calls
        if t.actor_id == "agent_demo"
        and t.tool == "query_status"
        and t.request.get("arguments", {}).get("entity_id") == "projector"
    ]
    assert checks[0].requested_at < _campus("16:41")
    assert any(t.requested_at >= _campus("16:41") for t in checks), [t.requested_at for t in checks]


# ---------------------------------------------------------------------------------- P0 handoff


def test_p0_retries_a_transfer_hold_rejected_by_a_revision_conflict(
    db: Database, tmp_path: Path, private: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Window 12:39-12:47: P0 asks at the opening, setup starts at 12:40 during the hold's
    one-minute duration (REVISION_CONFLICT); P0 re-reads, holds again and serves 40."""
    ref = _window_variant(private, tmp_path, monkeypatch, "12:39", "12:47")
    result = run_case(db, ref)
    requests = _handoffs(result)
    assert [t.envelope_status for t in requests][:1] == ["rejected"]
    assert any(t.envelope_status == "succeeded" for t in requests)
    assert _served(result) == 40


# ---------------------------------------------------------------------------------- shortfalls


def test_handoff_still_possible_needs_the_window_to_open_before_the_deadline() -> None:
    scenario = fixtures.load_public_scenario("dev_fixture_03")
    params = scenario.pantry_parameters
    assert params is not None
    opening = params.handoff_window.start
    before = opening.replace(minute=opening.minute - 10)
    assert handoff_still_possible(params, before, None)
    assert handoff_still_possible(params, before, _pantry("13:40"))
    assert not handoff_still_possible(params, before, opening)  # opens at the deadline
    assert not handoff_still_possible(params, opening, _pantry("13:40"))  # already open


@pytest.mark.parametrize("kind", ["P0", "P2", "P3"])
def test_a_window_opening_after_the_deadline_does_not_hold_back_the_shortfall(
    db: Database, tmp_path: Path, private: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """Window 13:45-13:55, after the 13:40 deadline: the 16-kit shortfall is reported when the
    24 kits are committed, before distribution starts at 13:00, not at 13:45."""
    ref = _window_variant(private, tmp_path, monkeypatch, "13:45", "13:55")
    if kind == "P0":
        result = run_case(db, ref)
    else:
        policy, _ = build(kind, tmp_path / kind)
        result = run_with(db, ref, policy)
    shortfalls = [d for d in result.history.decisions if d.kind == "infeasible"]
    assert shortfalls and shortfalls[0].at < _pantry("13:00"), kind
    assert shortfalls[0].details.get("shortfall_quantity") == 16


@pytest.mark.parametrize("kind", ["P2", "P3"])
def test_a_deduplicated_check_after_a_notice_answers_it(
    db: Database, tmp_path: Path, private: Path, kind: str
) -> None:
    """dev04 with a false delay notice at 16:50, after the 16:40 check, while the source still
    holds the same answer: the check at 16:50 is deduplicated to the 16:42 observation and
    answers the notice as of 16:50 (as P0 and the menu read it), so P2 and P3 keep the valid
    plan instead of churning it (re-audit R1)."""
    case = json.loads((private / "dev04.json").read_text())
    case["case_ref"] = "dev04_late_claim"
    case["world_events"].append(
        {
            "at": f"{CAMPUS_DAY}T16:50:00-05:00",
            "kind": "message_delivery",
            "entity_id": "projector",
            "observation_kind": "notice",
            "source_id": "delivery_contact",
            "source_record_id": "delivery_message_17x",
            "correlation_group": "projector_delivery_01",
            "observed_at": f"{CAMPUS_DAY}T16:50:00-05:00",
            "authority_scope": "self_report",
            "text": "Update on order P17: the projector will arrive 45 minutes later than the"
            " promised 5 p.m.",
        }
    )
    case["world_events"].sort(key=lambda e: e["at"])
    (private / "dev04_late_claim.json").write_text(json.dumps(case))
    world.load_case.cache_clear()
    policy, _ = build(kind, tmp_path / kind, ScriptedModel(choose=menu_pick))
    result = run_with(db, "dev04_late_claim", policy)
    assert result.report.goal_complete is True
    assert result.report.applied_plans == 0
