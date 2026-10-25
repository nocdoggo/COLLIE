"""P1 decides when a model call is warranted by P2's own rule (Wave 3 pre-freeze item 2).

Before 1.1.0, P1 (``tool-use/1.0.0``) called the model after every new observation: in its
development runs it confirmed ``keep`` after each check-in and arrival record and reached the
8-call cap with its plan already in place. Now P1, P2 and P3 share one attention rule
(``agent/attention.py``): a new notice warrants a model call; otherwise only a state whose
decision menu offers an action does, and the server records what the state determines. Checked
here: the code is shared (the same functions, not a copy); P1 makes no model call for a check-in
or arrival that changes nothing actionable; it still answers a check-in that breaks its plan and
every new notice, while a repeated notice is a server-recorded duplicate; and when it is called
it sees every observation that arrived meanwhile. Real store, executor and runner; scripted
models.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from plan_b.agent.attention import AttentionMixin
from plan_b.agent.orchestrator import LivePolicy
from plan_b.agent.policies.tool_use import MAX_OBSERVATIONS_SHOWN, ToolUsePolicy, _observations
from plan_b.agent.policies.verify_all import VerifyAllPolicy
from plan_b.domain.models import EventStateView, PolicyDecision
from plan_b.domain.timeutil import parse_ts
from plan_b.scenarios.runner import RunResult
from plan_b.store.database import Database
from tests.conftest import Sandbox
from tests.test_live_workflow import build, run_with, tool_state

SHARED = (
    "_attend",
    "_open_material",
    "_material",
    "_verify_needs",
    "_stock_verify_needs",
    "_record_default",
    "_record_shortfall",
    "_record_keep",
    "_compute_wait",
    "_deadline_watch",
    "_handoff_wake",
    "_ask_wake",
)


def _local(day: str, hhmm: str) -> datetime:
    return parse_ts(f"{day}T{hhmm}:00-05:00")


def _calls(d: PolicyDecision) -> int:
    return len(d.details["model"]["calls"])


def _run(db: Database, case: str, kind: str, tmp_path: Path) -> tuple[RunResult, Any]:
    policy, opener = build(kind, tmp_path / kind)
    return run_with(db, case, policy), opener


def test_p1_p2_and_p3_share_one_attention_rule() -> None:
    for name in SHARED:
        rule = getattr(AttentionMixin, name)
        for cls in (ToolUsePolicy, LivePolicy, VerifyAllPolicy):
            assert getattr(cls, name) is rule, (cls.__name__, name)


def test_p1_spends_no_model_call_on_check_ins_and_arrivals_that_change_nothing(
    db: Database, tmp_path: Path
) -> None:
    # dev01: after the swap, two check-ins (17:05, 17:20) and the projector's arrival (17:24).
    result, opener = _run(db, "dev01", "P1", tmp_path)
    assert result.report.matches_expectation is True, result.report.predicates
    commit = next(d for d in result.history.decisions if d.kind == "commit")
    later = [d for d in result.history.decisions if d.at > commit.at]
    assert later and all(_calls(d) == 0 for d in later)
    assert all(d.details["chosen_by"] == "server" for d in later)
    caps = result.report.episode_caps
    assert caps is not None and caps.model_calls == len(opener.requests) <= 3
    # The observations did arrive and were weighed, each by one evaluation, not a model call.
    kinds = {r.observation.kind for r in result.final_view.observations if r.revision_after > 0}
    assert {"check_in", "status"} <= kinds


def test_p1_is_called_when_a_check_in_breaks_its_plan(db: Database, tmp_path: Path) -> None:
    # skills_dev01: the peer lead's own check-in (10:05, available until 11:05) breaks the
    # planned 11:20 peer exchange: the keep candidate fails, so a model turn is warranted.
    result, _ = _run(db, "skills_dev01", "P1", tmp_path)
    assert result.report.matches_expectation is True, result.report.predicates
    day = "2026-11-07"
    turns = [d for d in result.history.decisions if _calls(d) and d.at >= _local(day, "10:05")]
    assert turns and turns[0].at < _local(day, "10:10")
    commit = next(d for d in result.history.decisions if d.kind == "commit")
    assert commit.details["chosen_by"] == "model" and commit.at >= _local(day, "10:05")


def test_p1_reads_every_new_notice_and_the_server_records_a_repeat(
    db: Database, tmp_path: Path
) -> None:
    # dev04: notices at 16:44 (a stale reminder), 16:46 and 16:47 (a forwarded copy).
    result, opener = _run(db, "dev04", "P1", tmp_path)
    assert result.report.matches_expectation is True, result.report.predicates
    shown: set[str] = set()
    for body in opener.bodies:
        _, observations = tool_state(body)
        shown |= {o["observation_id"] for o in observations if o["kind"] == "notice"}
    duplicates = [d for d in result.history.decisions if d.kind == "duplicate"]
    assert len(duplicates) == 1 and duplicates[0].details["chosen_by"] == "server"
    repeat, original = duplicates[0].observation_refs
    assert _calls(duplicates[0]) == 0 and original in shown
    notices = {
        r.observation.observation_id
        for r in result.final_view.observations
        if r.observation.kind == "notice"
    }
    assert notices - {repeat} <= shown  # every other notice reached a model turn


def test_a_called_p1_sees_the_observations_that_arrived_while_it_was_not_called(
    db: Database, tmp_path: Path
) -> None:
    result, opener = _run(db, "skills_dev01", "P1", tmp_path)
    last = opener.bodies[-1]
    _, observations = tool_state(last)
    ids = {o["observation_id"] for o in observations}
    arrived = {
        r.observation.observation_id
        for r in result.final_view.observations
        if r.revision_after <= tool_state(last)[0]["event"]["revision"]
    }
    assert arrived <= ids


def test_older_unshown_notices_are_never_cut_from_a_turn(db: Database) -> None:
    sb = Sandbox(db, "dev04")
    view = sb.view()
    notice = next(r for r in view.observations if r.observation.kind == "notice")
    filler = [
        r.model_copy(
            update={
                "observation": r.observation.model_copy(
                    update={"observation_id": f"obs_fill_{i:03d}", "kind": "status"}
                )
            }
        )
        for i, r in enumerate([notice] * (MAX_OBSERVATIONS_SHOWN + 5))
    ]
    crowded = view.model_copy(update={"observations": (notice, *filler)})
    assert isinstance(crowded, EventStateView)
    shown = [o["observation_id"] for o in _observations(crowded, set())]
    assert shown[0] == notice.observation.observation_id
    assert len(shown) == MAX_OBSERVATIONS_SHOWN + 1
    seen = {notice.observation.observation_id}
    assert notice.observation.observation_id not in {
        o["observation_id"] for o in _observations(crowded, seen)
    }
