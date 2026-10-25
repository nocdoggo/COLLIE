"""P1's hold documentation and turn budget, after the live P1 pantry_dev01 development run.

That run (``live_p1-tool-use_pantry_dev01``, prompt ``tool_use.v1``) sent six transfer holds the
executor refused: ``tool_use.v1`` never said which window a hold covers, so the model used the
staff handoff window, and a stock_transfer hold with a service target. Two of its turns were
also cut off at 1536 tokens, which the model's reasoning tokens count against. ``tool_use.v2``
documents the window and the transfer hold (``tool_use.v3`` keeps that text and adds when the
server calls the model); a turn may use 4096 tokens. These tests run the real store and
executor, with a scripted provider for the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plan_b.agent.policies.tool_use import PROMPT_ID, TURN_MAX_TOKENS
from plan_b.agent.prompts import load_prompt
from plan_b.store.database import Database
from tests.test_live_workflow import build, run_with
from tests.test_pantry_fixture import PantrySandbox

V1_SHA256 = "189709ae324fe24feed61fe6d38434925f85431179dbe3795e7b48a8567a1d34"


@pytest.fixture
def pantry(db: Database) -> PantrySandbox:
    return PantrySandbox(db)


def _transfer(pantry: PantrySandbox, window: dict[str, str], **extra: Any) -> tuple[str, str]:
    env = pantry.agent.call(
        "hold_resource",
        arguments={
            "resource_id": "partner_stock",
            "activity_id": "distribution",
            "window": window,
            "quantity": 16,
            "purpose": "stock_transfer",
            "destination_resource_id": "pantry_stock",
            **extra,
        },
        idempotency_key=f"transfer-{window['start']}-{len(extra)}",
        expected_revision=pantry.revision(),
    )
    return env.status, env.error.code if env.error else ""


def test_the_prompt_documents_the_hold_window_the_executor_accepts(
    pantry: PantrySandbox,
) -> None:
    assert PROMPT_ID == "tool_use.v3"
    text = " ".join(load_prompt(PROMPT_ID).system.split())
    assert "the activity's window in the candidate you hold for" in text
    assert "never the handoff window or the hold's lifetime" in text
    assert (
        "the window of the candidate's assignment of that activity, and no service_target_id"
        in (text)
    )
    assert load_prompt("tool_use.v1").sha256 == V1_SHA256  # the recorded v1 runs cite it

    env = pantry.agent.call("evaluate_candidates", arguments={})
    assert env.data is not None
    transfer = next(c for c in env.data["candidates"] if c["stock_transfers"])
    need = transfer["stock_transfers"][0]
    assert (need["source_resource_id"], need["destination_resource_id"]) == (
        "partner_stock",
        "pantry_stock",
    )
    assignment = next(a for a in transfer["assignments"] if a["activity_id"] == need["activity_id"])
    documented = {"start": assignment["start"], "end": assignment["end"]}
    handoff = {"start": "2026-11-09T17:30:00Z", "end": "2026-11-09T17:50:00Z"}

    # What the v1 run sent is refused, and nothing is held.
    assert _transfer(pantry, documented, service_target_id="kits_40") == (
        "rejected",
        "INVALID_REQUEST",
    )
    assert _transfer(pantry, handoff) == ("rejected", "CONSTRAINT_VIOLATION")
    assert not pantry.view().holds
    # What v2 documents is held: 16 partner kits reserved for the staff handoff.
    assert _transfer(pantry, documented) == ("succeeded", "")
    (hold,) = pantry.view().holds
    assert (hold.purpose, hold.remaining_quantity, hold.service_target_id) == (
        "stock_transfer",
        16,
        None,
    )


def test_each_p1_turn_sends_the_current_prompt_with_room_to_reason(
    db: Database, tmp_path: Path
) -> None:
    policy, opener = build("P1", tmp_path)
    result = run_with(db, "pantry_dev01", policy)
    assert result.report.matches_expectation is True
    system = load_prompt(PROMPT_ID).system
    assert TURN_MAX_TOKENS >= 4096
    assert opener.bodies and all(b["max_tokens"] == TURN_MAX_TOKENS for b in opener.bodies)
    assert all(b["messages"][0]["content"] == system for b in opener.bodies)
    holds = [
        t
        for t in result.history.tool_calls
        if t.actor_id == "agent_demo" and t.tool == "hold_resource"
    ]
    assert holds and all(t.envelope_status == "succeeded" for t in holds)
    prompts = {p for d in result.history.decisions for p in d.details.get("prompts", {}) if p}
    assert prompts == {"tool_use.v3"}
