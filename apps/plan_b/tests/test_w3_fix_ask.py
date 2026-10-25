"""P1's organizer ask is checked against the state it is made in (Wave 3 pre-freeze item 6).

The Wave 2 note: an ask made in the same turn as a hold was checked against that turn's
pre-mutation evaluation. Reproduced: the hold moved the revision, but the recorded request named
a candidate of the evaluation from before the hold (its required hold unbound), with that
evaluation's revision in its id. Now the server re-evaluates the state the ask is made in and
checks the ask against the same candidate there (matched by signature), so the request names the
candidate whose hold is bound. Real store, executor and runner; the model is scripted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plan_b.domain.models import EvaluationResult
from plan_b.store.database import Database
from tests.conftest import Sandbox
from tests.test_live_workflow import ToolScript, build, tool_state, turn

EVALUATE = ("evaluate_candidates", {"templates": None, "hypotheses": []})


def _short_of_spending(ev: dict[str, Any]) -> dict[str, Any]:
    return next(
        c
        for c in ev["candidates"]
        if c["constraint_status"] == "feasible_under_assumptions"
        and c["missing_permissions"] == ["committed_spend_limit"]
    )


def _hold_and_ask(body: dict[str, Any], n: int) -> Any:
    """Turn 1 evaluates; turn 2 holds the booking the candidate needs and asks in one reply."""
    state, _ = tool_state(body)
    ev = state["latest_evaluation"]
    if ev is None:
        return turn([EVALUATE])
    if n > 2:
        return turn(done=True, decision="wait")
    cand = _short_of_spending(ev)
    rh = cand["required_holds"][0]
    hold = {
        "resource_id": rh["resource_id"],
        "activity_id": rh["activity_id"],
        "window": {"start": rh["window"]["start"], "end": rh["window"]["end"]},
    }
    ask = {
        "candidate_id": cand["candidate_id"],
        "resource_id": rh["resource_id"],
        "requested_value": 3500,
    }
    return turn([("hold_resource", hold)], done=True, decision="ask", ask=ask)


def _evaluation(db: Database, episode_id: str, evaluation_id: str) -> EvaluationResult:
    with db.read() as conn:
        row = conn.execute(
            "SELECT body_json FROM evaluations WHERE episode_id = ? AND evaluation_id = ?",
            (episode_id, evaluation_id),
        ).fetchone()
    assert row is not None, evaluation_id
    return EvaluationResult.model_validate_json(row["body_json"])


def _candidate_evaluation(db: Database, episode_id: str, candidate_id: str) -> str:
    with db.read() as conn:
        row = conn.execute(
            "SELECT evaluation_id FROM candidates WHERE episode_id = ? AND candidate_id = ?",
            (episode_id, candidate_id),
        ).fetchone()
    assert row is not None, candidate_id
    return str(row["evaluation_id"])


def test_an_ask_in_the_same_turn_as_its_hold_is_checked_against_the_held_state(
    db: Database, tmp_path: Path
) -> None:
    sb = Sandbox(db, "dev02")
    policy, _ = build("P1", tmp_path, ToolScript(_hold_and_ask))
    result = policy.run(sb.agent)
    kinds = [d.kind for d in result.decisions]
    assert "prepare" in kinds and "ask" in kinds, kinds
    hold = result.decisions[kinds.index("prepare")]
    ask = result.decisions[kinds.index("ask")]
    request = ask.authorization_request
    assert request is not None and request.requested_value == 3500
    # The ask is made after the hold moved the revision ...
    assert hold.receipt_refs and ask.revision == sb.revision()
    # ... and is checked against the evaluation of that state, where the hold is bound.
    evaluation_id = ask.details["evaluation_id"]
    ev = _evaluation(db, sb.episode_id, evaluation_id)
    assert ev.revision == ask.revision
    assert _candidate_evaluation(db, sb.episode_id, request.candidate_id) == evaluation_id
    cand = next(c for c in ev.candidates if c.candidate_id == request.candidate_id)
    assert [rh.bound_hold_id for rh in cand.required_holds] == [hold.details["hold_id"]]
    assert request.request_id.startswith(f"authreq_r{ask.revision}_")
    assert request.candidate_id in ask.candidate_refs


def test_an_ask_whose_candidate_is_gone_after_the_turn_is_refused(
    db: Database, tmp_path: Path
) -> None:
    # The model asks for a candidate id the latest evaluation never had: refused before
    # anything is asked, as before.
    def bogus(body: dict[str, Any], n: int) -> Any:
        out = _hold_and_ask(body, n)
        if out["decision"] == "ask":
            out = out | {"ask": out["ask"] | {"candidate_id": "cand_9999_00000000"}}
        return out

    sb = Sandbox(db, "dev02")
    policy, _ = build("P1", tmp_path, ToolScript(bogus))
    result = policy.run(sb.agent)
    assert all(d.authorization_request is None for d in result.decisions)
    refused = [d for d in result.decisions if d.details.get("failure") == "invalid_choice"]
    assert refused and "not in the latest evaluation" in refused[0].details["problem"]
