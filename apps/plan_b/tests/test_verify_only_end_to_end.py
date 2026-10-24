"""Verify-only notices end to end: scratch variants of the private cases run through the real
runner, executor and store (the shipped cases are copied, never edited)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import plan_b.world.world as world
from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store.database import Database

GENUINE = "Order P17 was cancelled by the carrier this afternoon; sorry for the trouble."
CHATTER = ("Running a bit late, sorry.", "The projector delivery is delayed, more soon.")


def _t(hm: str) -> str:
    return f"2026-11-05T{hm}:00-05:00"


def _notice(text: str, hm: str, rec: str) -> dict[str, Any]:
    return {
        "at": _t(hm),
        "kind": "message_delivery",
        "entity_id": "projector",
        "observation_kind": "notice",
        "source_id": "delivery_contact",
        "source_record_id": rec,
        "correlation_group": f"grp_{rec}",
        "observed_at": _t(hm),
        "authority_scope": "self_report",
        "text": text,
        "supersedes": [],
    }


def _status(start: str, code: str, domain: str, eta: str | None, rec: str) -> dict[str, Any]:
    return {
        "entity_id": "projector",
        "fact": "delivery_eta",
        "available_from": _t(start),
        "outcome": "ok",
        "response": {
            "status_code": code,
            "domain_status": domain,
            "reported_eta": _t(eta) if eta else None,
            "source_record_id": rec,
            "observed_at": _t(start),
            "text": f"Order P17: {code}.",
        },
    }


# The supplier's source reports the 17:25 delay, then the cancellation from 16:44.
CANCELLED_FROM_1644 = [
    _status("16:30", "delayed", "expected", "17:25", "order_P17_rev_a"),
    _status("16:44", "cancelled", "unavailable", None, "order_P17_rev_b"),
]


@pytest.fixture
def variant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., RunResult]]:
    private = tmp_path / "private"
    shutil.copytree(world.PRIVATE_DIR, private)
    monkeypatch.setattr(world, "PRIVATE_DIR", private)
    world.load_case.cache_clear()

    def make(
        base: str,
        name: str,
        notices: list[dict[str, Any]],
        status: list[dict[str, Any]] | None = None,
    ) -> RunResult:
        case = json.loads((private / f"{base}.json").read_text())
        case["case_ref"] = name
        case["world_events"] = list(case["world_events"]) + notices
        if status is not None:
            # The projector never arrives; only the supplier's status source tells the truth.
            case["world_events"] = [
                e for e in case["world_events"] if e["kind"] != "resource_arrival"
            ]
            case["status_model"] = [
                s for s in case["status_model"] if s["entity_id"] != "projector"
            ] + status
        (private / f"{name}.json").write_text(json.dumps(case))
        return run_case(Database(tmp_path / f"{name}.sqlite3"), name)

    yield make
    world.load_case.cache_clear()


def _projector_queries(r: RunResult) -> list[str]:
    return [
        c.requested_at.strftime("%H:%M")
        for c in r.history.tool_calls
        if c.tool == "query_status"
        and c.actor_id == "agent_demo"
        and c.request["arguments"]["entity_id"] == "projector"
    ]


def test_unsupported_supplier_cancellation_after_the_initial_check_is_verified(
    variant: Callable[..., RunResult],
) -> None:
    r = variant("dev06", "vo_genuine", [_notice(GENUINE, "16:45", "g0")], CANCELLED_FROM_1644)
    # The 16:40 check predates the notice, so it does not answer it: the notice is checked
    # (21:45Z), the typed cancellation drives the backup booking, and the event completes.
    assert "21:45" in _projector_queries(r)
    assert r.report.goal_complete and r.final_view.budget.committed_cents == 3500
    assert any("verified only" in d.summary for d in r.history.decisions if d.kind == "verify")


def test_status_worded_supplier_chatter_does_not_delay_the_backup(
    variant: Callable[..., RunResult],
) -> None:
    chatter = [_notice(CHATTER[0], "16:44", "c0"), _notice(CHATTER[1], "16:47", "c1")]
    r = variant("dev02", "vo_chatter", chatter)
    # The 16:40 check says the projector is expected only at 17:45, after every start that uses
    # it, so no check of the chatter could change the plan: none is spent, and the hold, the ask
    # and the authorized booking keep their timing.
    assert r.report.goal_complete and r.final_view.budget.committed_cents == 3500
    assert _projector_queries(r) == ["21:40"]
    skipped = [d for d in r.history.decisions if d.details.get("outcome") == "not_checked"]
    # The 16:44 notice is narrated as not checked; by 16:47 the backup is committed and the
    # projector no longer matters to the plan.
    assert [d.observation_refs for d in skipped] == [("obs_0002",)]
    assert skipped[0].kind == "verify" and "expected only at 17:45" in skipped[0].summary


def test_a_notice_arriving_while_a_check_is_in_flight_is_checked_again(
    variant: Callable[..., RunResult],
) -> None:
    notices = [_notice(CHATTER[0], "16:43", "c0"), _notice(GENUINE, "16:44", "g0")]
    r = variant("dev06", "vo_inflight", notices, CANCELLED_FROM_1644)
    # The chatter's check was requested at 21:43Z, before the cancellation notice arrived, so
    # it cannot answer it; a later check does, and recovery follows.
    queries = _projector_queries(r)
    assert any(q > "21:44" for q in queries), queries
    assert r.report.goal_complete and r.final_view.budget.committed_cents == 3500
