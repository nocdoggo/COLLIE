"""Every policy wakes when the pantry handoff window opens (Wave 3 pre-freeze item 1).

Two development-only cases, built here from the canonical pantry fixture (``dev_fixture_03``,
``pantry_dev01``) in a scratch directory; neither is a committed fixture, so ``plan-b run-case
all`` and the held-out bank are untouched:

* ``pantry_dev_late_window``: the handoff window opens at 12:42, after load (the development
  cases open it at load, 12:30), and closes at 12:49. No state change marks 12:42, so before
  1.1.0 no policy looked again then and each reported the shortfall: the probe of the Wave 2
  final audit. Now P0-P3 wake at the opening, request the handoff and serve all 40 kits.
* ``pantry_dev_closed_window``: the window closes at 12:33, before any handoff can be
  answered, so only the 24 kits on hand can be served. P2 and P3 used to hold them and then keep
  the plan without committing them (the kept plan looked as if it covered 24, though its
  allocation rested only on holds and uncommitted stock serves nobody); now they commit and
  report the 16-kit shortfall, as P0 does.

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
from plan_b.domain.stock import handoff_window_opening
from plan_b.domain.timeutil import parse_ts
from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store.database import Database
from tests.test_live_workflow import build, run_with

DAY = "2026-11-09"
LATE = "pantry_dev_late_window"
CLOSED = "pantry_dev_closed_window"


def _at(hhmm: str) -> datetime:
    return parse_ts(f"{DAY}T{hhmm}:00-05:00")


def _predicate(pid: str, kind: str, **params: Any) -> dict[str, Any]:
    return {"predicate_id": pid, "kind": kind, "params": params, "description": pid}


COMMON = [
    _predicate("p_conserved", "stock_conserved"),
    _predicate("p_expected", "expected_unreceived_equals", shipment_id="S20", quantity=20),
    _predicate("p_staff_only", "no_staff_attestation_by_agent"),
    _predicate("p_no_violations", "no_executed_violations"),
    _predicate("p_spend", "committed_spend_equals", cents=0),
    _predicate("p_pantry_end", "stock_on_hand_equals", resource_id="pantry_stock", quantity=0),
]
CASES: dict[str, tuple[str, str, list[dict[str, Any]], str]] = {
    LATE: (
        "12:42",
        "12:49",
        [
            _predicate("p_required", "all_required_completed_by_deadline"),
            *COMMON,
            _predicate("p_on_time", "service_on_time_equals", target_id="kits_40", quantity=40),
            _predicate(
                "p_unfulfilled", "service_unfulfilled_equals", target_id="kits_40", quantity=0
            ),
            _predicate(
                "p_partner_end", "stock_on_hand_equals", resource_id="partner_stock", quantity=0
            ),
        ],
        "goal_complete",
    ),
    CLOSED: (
        "12:30",
        "12:33",
        [
            *COMMON,
            _predicate("p_on_time", "service_on_time_equals", target_id="kits_40", quantity=24),
            _predicate(
                "p_unfulfilled", "service_unfulfilled_equals", target_id="kits_40", quantity=16
            ),
            _predicate(
                "p_partner_end", "stock_on_hand_equals", resource_id="partner_stock", quantity=16
            ),
            _predicate("p_reported", "infeasibility_reported"),
        ],
        "goal_not_complete_infeasibility_reported",
    ),
}


@pytest.fixture
def window_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """``window_case(ref)``: the pantry scenario with that case's handoff window, and the case
    itself in a scratch private directory (the development cases stay visible next to it)."""
    original = fixtures.public_scenario_path
    private = tmp_path / "private"
    private.mkdir()
    for path in world.PRIVATE_DIR.glob("*.json"):
        (private / path.name).write_text(path.read_text())
    monkeypatch.setattr(world, "PRIVATE_DIR", private)

    def make(ref: str) -> str:
        start, end, predicates, expected = CASES[ref]
        scenario = json.loads(original("dev_fixture_03").read_text())
        scenario["pantry_parameters"]["handoff_window"] = {
            "start": f"{DAY}T{start}:00-05:00",
            "end": f"{DAY}T{end}:00-05:00",
        }
        variant = tmp_path / f"{ref}.public.json"
        variant.write_text(json.dumps(scenario))
        monkeypatch.setattr(
            fixtures,
            "public_scenario_path",
            lambda sid: variant if sid == "dev_fixture_03" else original(sid),
        )
        case = json.loads((private / "pantry_dev01.json").read_text())
        case |= {
            "case_ref": ref,
            "planning_label": "DEV03-WINDOW",
            "description": f"Development only: pantry_dev01 with the handoff window {start}-{end}.",
            "derived_from": None,
            "outcome_predicates": predicates,
            "expected_outcome": expected,
        }
        (private / f"{ref}.json").write_text(json.dumps(case))
        return ref

    yield make
    world.load_case.cache_clear()


def _run(db: Database, ref: str, kind: str, tmp_path: Path) -> RunResult:
    if kind == "P0":
        return run_case(db, ref)
    policy, _ = build(kind, tmp_path / kind)
    return run_with(db, ref, policy)


def _handoff_requests(result: RunResult) -> list[Any]:
    return [
        t
        for t in result.history.tool_calls
        if t.actor_id == "agent_demo"
        and t.tool == "hold_resource"
        and t.request.get("arguments", {}).get("purpose") == "stock_transfer"
    ]


def test_the_window_opening_is_a_wake_only_while_it_is_ahead() -> None:
    scenario = fixtures.load_public_scenario("dev_fixture_03")
    params = scenario.pantry_parameters
    assert params is not None
    start = params.handoff_window.start
    assert handoff_window_opening(params, _at("12:20")) == start
    assert handoff_window_opening(params, start) is None  # the development cases: open at load
    assert handoff_window_opening(None, _at("12:20")) is None


@pytest.mark.parametrize("kind", ["P0", "P1", "P2", "P3"])
def test_every_policy_answers_a_handoff_window_that_opens_after_load(
    db: Database, tmp_path: Path, window_case: Any, kind: str
) -> None:
    ref = window_case(LATE)
    result = _run(db, ref, kind, tmp_path)
    assert result.report.matches_expectation is True, (kind, result.report.predicates)
    # Woken at the opening: the first run that ends before it asks to be woken then.
    early = [r for r in result.policy_runs if r.wait_until is not None]
    assert any(r.wait_until == _at("12:42") for r in early), kind
    requests = _handoff_requests(result)
    assert requests and all(t.envelope_status == "succeeded" for t in requests), kind
    assert all(t.requested_at is not None and t.requested_at >= _at("12:42") for t in requests)
    # No shortfall is reported while the handoff can still be requested.
    early_shortfalls = [
        d for d in result.history.decisions if d.kind == "infeasible" and d.at < _at("12:42")
    ]
    assert not early_shortfalls, kind


@pytest.mark.parametrize("kind", ["P0", "P1", "P2", "P3"])
def test_with_no_handoff_possible_the_kits_on_hand_are_committed_and_served(
    db: Database, tmp_path: Path, window_case: Any, kind: str
) -> None:
    ref = window_case(CLOSED)
    result = _run(db, ref, kind, tmp_path)
    assert result.report.matches_expectation is True, (kind, result.report.predicates)
    assert not _handoff_requests(result), kind
    commits = [d for d in result.history.decisions if d.kind == "commit"]
    assert commits and commits[0].at < _at("13:00"), kind  # before distribution starts
