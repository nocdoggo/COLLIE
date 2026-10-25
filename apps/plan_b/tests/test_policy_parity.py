"""Parity of P0-P3 at one state, the restart mapping of the model choices, and P1's bounds.

Everything runs through the real store and executor; the models are the real provider client
with a scripted ``FakeOpener`` (``tests.test_agent_provider``), and every spend ledger lives in
``tmp_path``. Each test names, in a comment, the mutation of the code it catches.

* parity: P0 (the profile's baseline), P1 ``tool-use/1.1.0``, P2 ``live/1.1.0`` and P3
  ``verify-all/1.1.0``, each built and run once on a fresh episode of each suite behind a
  recording client, read the same coordinator grant at the same start state, get the same
  candidate set from every plain evaluation, and call only tools of that grant (P1's turn
  schema offers exactly the grant's tools; P2 and P3 stay within ``AGENT_TOOLS``);
* restart (E11): a new ``PolicyHost`` on the same database keeps each model choice;
* lost responses (E6): P1 retries a lost ``apply_plan`` once with its original key after a
  ``not_found`` lookup, makes at most ``MAX_RECEIPT_LOOKUPS`` lookups, and sends no further
  mutation in a run once an outcome could not be established;
* turn bounds (E7): ``MAX_CALLS_PER_TURN``, a rejected mutation ending the turn's sequence,
  ``MAX_WAIT_MINUTES``, the one repair of an invalid tool name, the revision in the
  idempotency key, and ``MAX_TURNS`` per run. Bound tests use ``done=false`` turns, so they hold
  whether or not a ``done`` turn with a rejected mutation ends the run.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent.orchestrator import AGENT_TOOLS
from plan_b.agent.policies.tool_use import (
    MAX_CALLS_PER_TURN,
    MAX_RECEIPT_LOOKUPS,
    MAX_TURNS,
    MAX_WAIT_MINUTES,
    MUTATIONS,
)
from plan_b.agent.policies.tool_use import SCHEMA_NAME as TURN_SCHEMA
from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import STAFF_TOOLS, PolicyRunResult, ToolEnvelope
from plan_b.evaluation.policies.base import Policy, ToolClient, TransportLost
from plan_b.scenarios.policy_host import (
    PolicyChoice,
    PolicyHost,
    baseline_policy_factory,
    policy_factory_for,
)
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.episodes import create_episode
from plan_b.world.world import load_case
from tests.conftest import Sandbox, at
from tests.test_agent_provider import FakeOpener, schema_name
from tests.test_live_workflow import SUITES, ToolScript, build, tool_state, tool_user, turn

POLICY_IDS = {"P1": "tool-use/1.1.0", "P2": "live/1.1.0", "P3": "verify-all/1.1.0"}


# ---------------------------------------------------------------------------------- clients


@dataclass
class Sent:
    """One request a policy sent, and the envelope it received (None: the response was lost)."""

    tool: str
    arguments: dict[str, Any]
    idempotency_key: str | None
    expected_revision: int | None
    expected_goal_version: int | None
    envelope: ToolEnvelope | None = None


class RecordingClient:
    """Delegates every call to the real client (the same executor) and records it. With
    ``lose_applies`` the first that many ``apply_plan`` responses are lost after the server
    processed them; with ``not_found`` every receipt lookup is answered as the handler answers
    an unknown key (``lookup_status: not_found``), the lookup itself still reaching the
    server."""

    def __init__(
        self, inner: ToolClient, *, lose_applies: int = 0, not_found: bool = False
    ) -> None:
        self.inner = inner
        self.principal_id = inner.principal_id
        self.grant_id = getattr(inner, "grant_id", None)
        self.sent: list[Sent] = []
        self._lose_applies = lose_applies
        self._not_found = not_found

    def call(
        self,
        tool: str,
        *,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        expected_goal_version: int | None = None,
    ) -> ToolEnvelope:
        sent = Sent(tool, arguments, idempotency_key, expected_revision, expected_goal_version)
        self.sent.append(sent)
        envelope = self.inner.call(
            tool,
            arguments=arguments,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_goal_version=expected_goal_version,
        )
        if tool == "apply_plan" and self._lose_applies > 0:
            self._lose_applies -= 1
            raise TransportLost(tool, idempotency_key)
        if tool == "get_action_receipt" and self._not_found:
            envelope = envelope.model_copy(
                update={"data": {"lookup_status": "not_found", "receipt": None}}
            )
        sent.envelope = envelope
        return envelope

    def tools(self) -> list[str]:
        return [s.tool for s in self.sent]

    def of(self, tool: str) -> list[Sent]:
        return [s for s in self.sent if s.tool == tool]


def turns_of(opener: FakeOpener) -> list[dict[str, Any]]:
    return [b for b in opener.bodies if schema_name(b) == TURN_SCHEMA]


def last_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    state, _ = tool_state(body)
    results = state["last_tool_results"]
    assert isinstance(results, list)
    return results


def tool_enum(body: dict[str, Any]) -> list[str]:
    schema = body["response_format"]["json_schema"]["schema"]
    return list(schema["properties"]["calls"]["items"]["properties"]["tool"]["enum"])


def serving(policy: Policy) -> Callable[[], Policy]:
    """A host factory that serves one already-built (scripted) policy."""
    return lambda: policy


def new_episode(db: Database, case: str) -> tuple[str, str]:
    with db.write() as conn:
        episode_id = create_episode(conn, scenario_id=load_case(case).scenario_id, case_ref=case)
        profile = repo.get_episode(conn, episode_id).profile_id
    return episode_id, profile


def receipts_of(sb: Sandbox, tool: str) -> list[Any]:
    with sb.db.read() as conn:
        return [r for r in repo.receipts(conn, sb.episode_id) if r.tool == tool]


# ---------------------------------------------------------------------------------- parity


@pytest.mark.parametrize(("case", "suite"), SUITES)
def test_each_policy_reads_the_same_grant_tools_and_candidates(
    db: Database, tmp_path: Path, case: str, suite: str
) -> None:
    """Each of P0-P3 is built by its factory and run once on a fresh episode of the case,
    behind a recording client. Catches: a policy whose factory raises or builds another policy;
    a policy given another principal's session or grant, or a different start state; a policy
    whose evaluation sees a different candidate generation; P1's turn schema offering tools
    outside the grant; P2/P3 calling a tool outside ``AGENT_TOOLS`` or the grant; any policy
    calling a staff tool. No shipped grant lists a staff tool, so P1's staff-tool filter is
    pinned in test_comparison_policy_fixes.py."""
    worlds: dict[str, tuple[Any, ...]] = {}
    candidate_sets: dict[str, set[frozenset[tuple[str, str]]]] = {}
    for name in ("P0", "P1", "P2", "P3"):
        episode_id, profile = new_episode(db, case)
        opener: FakeOpener | None = None
        factory: Callable[[], Policy]
        if name == "P0":
            factory = baseline_policy_factory(profile)
            expected_id = "pantry-rules/1.1.0" if suite == "pantry" else "rules/1.0.0"
        else:
            built, opener = build(name, tmp_path / name)
            factory = serving(built)
            expected_id = POLICY_IDS[name]
        host = PolicyHost(db, factory)
        client = RecordingClient(host.client(episode_id))
        policy = host.policy(episode_id)
        assert policy.policy_id == expected_id, name
        result = policy.run(client)
        assert result.policy_id == expected_id and result.decisions, (name, result.note)

        # The first call reads the state; the grant is the coordinator's own.
        first = client.sent[0]
        assert first.tool == "get_event_state", (name, client.tools())
        assert first.envelope is not None and first.envelope.data is not None
        state = first.envelope.data
        grants = [g for g in state["grants"] if g["grant"]["principal_id"] == client.principal_id]
        assert len(grants) == 1, name
        grant = grants[0]
        assert state["viewer"]["grant_id"] == grant["grant"]["grant_id"] == client.grant_id
        start = {k: v for k, v in state.items() if k != "episode_id"}  # the only per-episode id
        worlds[name] = (
            client.principal_id,
            grant["grant"]["grant_id"],
            json.dumps(grant["grant"], sort_keys=True),
            grant["version"],
            first.envelope.revision,
            sha256_hex(canonical_json(start)),
        )

        # Every plain evaluation the policy made returns the suite's one candidate set.
        sets: set[frozenset[tuple[str, str]]] = set()
        for s in client.of("evaluate_candidates"):
            if s.arguments.get("hypotheses"):
                continue
            assert s.envelope is not None and s.envelope.status == "succeeded", name
            data = s.envelope.data
            assert data is not None and data["hypothetical"] is False
            sets.add(frozenset((c["signature"], c["label"]) for c in data["candidates"]))
        assert sets, f"{name} made no evaluation without hypotheses"
        candidate_sets[name] = sets

        # Tools: only the grant's, never a staff tool; P2/P3 only AGENT_TOOLS.
        allowed = list(grant["grant"]["allowed_tools"])
        called = set(client.tools())
        assert called <= set(allowed), (name, called - set(allowed))
        assert not called & set(STAFF_TOOLS), name
        if name in ("P2", "P3"):
            assert called <= AGENT_TOOLS, (name, called - AGENT_TOOLS)
        if name == "P1":
            assert opener is not None
            bodies = turns_of(opener)
            assert bodies, "P1 made no tool turn"
            offered = [t for t in allowed if t not in STAFF_TOOLS]
            for body in bodies:
                enum = tool_enum(body)
                assert sorted(enum) == sorted(offered) and len(set(enum)) == len(enum)
                shown = tool_state(body)[0]["grant"]
                assert (shown["grant_id"], shown["version"]) == (
                    grant["grant"]["grant_id"],
                    grant["version"],
                )
                assert sorted(shown["allowed_tools"]) == sorted(offered)
            assert called <= set(offered)

    assert len(set(worlds.values())) == 1, f"{suite}: the policies read different grants: {worlds}"
    every = set().union(*candidate_sets.values())
    assert len(every) == 1, f"{suite}: the policies saw different candidate sets"
    assert next(iter(every)), "the evaluation has candidates"


# ---------------------------------------------------------------------------------- restart


@pytest.mark.parametrize(
    ("choice", "policy_id"),
    [("tool-use", "tool-use/1.1.0"), ("live", "live/1.1.0"), ("verify-all", "verify-all/1.1.0")],
)
def test_a_restarted_host_keeps_each_model_policy_choice(
    db: Database, tmp_path: Path, choice: PolicyChoice, policy_id: str
) -> None:
    """E11. Catches: the restart mapping (``PolicyHost._factory_of`` via ``choice_of``) reverted
    to live-only, so a restarted tool-use or verify-all episode silently runs the rules
    baseline (or the live policy); a stored decision losing its policy id."""
    kinds = {"tool-use": "P1", "live": "P2", "verify-all": "P3"}
    asked: list[tuple[str, str]] = []

    def factories(name: PolicyChoice, profile_id: str) -> Callable[[], Policy]:
        asked.append((name, profile_id))
        if name == "rules":
            return policy_factory_for("rules", profile_id)
        return lambda: build(kinds[name], tmp_path / name)[0]

    episode_id, profile = new_episode(db, "dev01")
    host = PolicyHost(db, factory_for=factories)
    host.select(episode_id, choice)
    assert host.choice(episode_id) == choice
    ran = host.run(episode_id)
    assert ran.policy_id == policy_id and ran.decisions, ran.note
    with db.read() as conn:
        stored = repo.decisions(conn, episode_id)
    assert stored and {d.policy_id for d in stored} == {policy_id}

    asked.clear()
    restarted = PolicyHost(db, factory_for=factories)  # a new process on the same database
    assert restarted.choice(episode_id) == choice
    assert restarted.policy(episode_id).policy_id == policy_id
    assert asked == [(choice, profile)]
    described = restarted.describe(episode_id)
    assert (described["policy"], described["policy_id"], described["locked"]) == (
        choice,
        policy_id,
        True,
    )


# ---------------------------------------------------------------------------------- E6: lost


def _apply_then(
    after: Callable[[dict[str, Any], dict[str, Any]], Any] | None,
) -> tuple[ToolScript, dict[str, Any]]:
    """``tool_user``, with its first apply sent in a ``done=false`` turn; once that apply was
    sent, ``after(body, apply_arguments)`` may answer the following turns."""
    seen: dict[str, Any] = {}

    def override(body: dict[str, Any], n: int) -> Any:
        if "apply" in seen:
            return after(body, seen["apply"]) if after is not None else None
        out = tool_user(body)
        applies = [c for c in out["calls"] if c["tool"] == "apply_plan"]
        if applies:
            seen["apply"] = json.loads(applies[0]["arguments_json"])
            out["done"] = False
        return out

    return ToolScript(override), seen


def test_tool_use_retries_a_lost_apply_once_with_its_key_after_not_found(
    db: Database, tmp_path: Path
) -> None:
    """The apply's response is lost and the first lookup says ``not_found``: P1 resends the
    identical request (same key, same expected revision) once, and the server replays the
    original receipt, so the plan is applied exactly once. Catches: no retry after not_found;
    a retry under a fresh key or revision; more than one lookup when the first one answered."""
    sb = Sandbox(db, "dev01")
    model, seen = _apply_then(None)
    policy, _ = build("P1", tmp_path, model)
    client = RecordingClient(sb.agent, lose_applies=1, not_found=True)
    result = policy.run(client)

    applies = client.of("apply_plan")
    assert len(applies) == 2
    first, retry = applies
    assert first.arguments == retry.arguments == seen["apply"]
    assert first.idempotency_key is not None
    assert first.idempotency_key == retry.idempotency_key
    assert (first.expected_revision, first.expected_goal_version) == (
        retry.expected_revision,
        retry.expected_goal_version,
    )
    lookups = client.of("get_action_receipt")
    assert [s.arguments for s in lookups] == [{"idempotency_key": first.idempotency_key}]
    tools = client.tools()
    i = tools.index("apply_plan")
    assert tools[i : i + 3] == ["apply_plan", "get_action_receipt", "apply_plan"]
    assert retry.envelope is not None and retry.envelope.replayed_receipt is True
    assert [r.status for r in receipts_of(sb, "apply_plan")] == ["applied"]
    commit = next(d for d in result.decisions if d.kind == "commit")
    assert commit.details["reconciled"] is True
    assert commit.details["idempotency_key"] == first.idempotency_key
    assert not [d for d in result.decisions if d.details.get("failure") == "lost_response"]


def test_tool_use_bounds_receipt_lookups_and_blocks_mutations_after_a_lost_outcome(
    db: Database, tmp_path: Path
) -> None:
    """The apply's response and its one retry are lost and every lookup says ``not_found``:
    at most ``MAX_RECEIPT_LOOKUPS`` lookups and one retry are made, the outcome is recorded as
    not established, and when the model asks for an apply and a hold in a later turn of the
    same run neither is sent. Catches: an unbounded lookup loop; a second retry; dropping
    ``mutations_blocked`` (or not checking it before a mutation)."""
    sb = Sandbox(db, "dev01")
    asked: list[int] = []

    def after(body: dict[str, Any], apply: dict[str, Any]) -> Any:
        asked.append(1)
        if len(asked) == 1:
            hold = {
                "resource_id": "backup_projector",
                "activity_id": "demonstrations",
                "window": {"start": at("17:10").isoformat(), "end": at("17:30").isoformat()},
            }
            return turn([("apply_plan", apply), ("hold_resource", hold)])
        return turn(done=True, decision="wait")

    model, seen = _apply_then(after)
    policy, opener = build("P1", tmp_path, model)
    client = RecordingClient(sb.agent, lose_applies=2, not_found=True)
    result = policy.run(client)

    applies = client.of("apply_plan")
    assert len(applies) == 2  # the original and exactly one identical retry
    key = applies[0].idempotency_key
    assert key is not None and applies[1].idempotency_key == key
    lookups = client.of("get_action_receipt")
    assert len(lookups) == MAX_RECEIPT_LOOKUPS
    assert all(s.arguments == {"idempotency_key": key} for s in lookups)
    lost = [d for d in result.decisions if d.details.get("failure") == "lost_response"]
    reconcile = [d for d in lost if d.kind == "reconcile"]
    assert len(reconcile) == 1 and reconcile[0].details["idempotency_key"] == key
    # The later, valid requests refused after the lost outcome are not the model's error.
    assert [(d.kind, d.details["tool"]) for d in lost if d.kind != "reconcile"] == [
        ("wait", "apply_plan"),
        ("wait", "hold_resource"),
    ]
    # The model asked again in a later turn: nothing was sent, and it was told so.
    assert len(asked) == 2
    mutations = [s for s in client.sent if s.tool in MUTATIONS]
    assert mutations == applies
    final = turns_of(opener)[-1]
    refused = last_results(final)
    assert [r["tool"] for r in refused] == ["apply_plan", "hold_resource"]
    assert all(r["status"] == "not_sent" and r["refused"] for r in refused)
    assert "commit" not in [d.kind for d in result.decisions]
    # The server applied the first request once (an unestablished outcome, not a failure).
    assert [r.status for r in receipts_of(sb, "apply_plan")] == ["applied"]
    assert seen["apply"] == applies[0].arguments


# ---------------------------------------------------------------------------------- E7: turns


def _run_p1(
    db: Database,
    tmp_path: Path,
    override: Callable[[dict[str, Any], int], Any],
    *,
    max_model_calls: int = 8,
) -> tuple[Sandbox, RecordingClient, FakeOpener, PolicyRunResult]:
    sb = Sandbox(db, "dev01")
    policy, opener = build("P1", tmp_path, ToolScript(override), max_model_calls=max_model_calls)
    client = RecordingClient(sb.agent)
    return sb, client, opener, policy.run(client)


def test_tool_use_runs_at_most_max_calls_per_turn_and_refuses_the_rest(
    db: Database, tmp_path: Path
) -> None:
    """A turn with five calls: the first ``MAX_CALLS_PER_TURN`` are sent, the rest are refused
    before any call and recorded. Catches: removing the per-turn call bound."""
    n_calls = 5
    assert n_calls > MAX_CALLS_PER_TURN
    keys = [f"probe-{i}" for i in range(1, n_calls + 1)]

    def script(body: dict[str, Any], n: int) -> Any:
        if n == 1:
            return turn([("get_action_receipt", {"idempotency_key": k}) for k in keys])
        return turn(done=True, decision="wait")

    _, client, opener, result = _run_p1(db, tmp_path, script)
    sent = [s.arguments["idempotency_key"] for s in client.of("get_action_receipt")]
    assert sent == keys[:MAX_CALLS_PER_TURN]
    results = last_results(turns_of(opener)[1])
    assert [r["tool"] for r in results] == ["get_action_receipt"] * n_calls
    ran, rest = results[:MAX_CALLS_PER_TURN], results[MAX_CALLS_PER_TURN:]
    assert all(r["status"] == "succeeded" and r["refused"] is None for r in ran)
    assert all(r["status"] == "not_sent" and r["refused"] for r in rest)
    refused = [d for d in result.decisions if d.details.get("failure") == "invalid_choice"]
    assert len(refused) == n_calls - MAX_CALLS_PER_TURN
    assert all(d.kind == "wait" and d.details["tool"] == "get_action_receipt" for d in refused)


@pytest.mark.parametrize("why", ["wrong_report", "stale"])
def test_tool_use_a_rejected_mutation_ends_the_turns_sequence(
    db: Database, tmp_path: Path, why: str
) -> None:
    """``apply_plan`` with a report ref of another candidate, or at a revision another
    principal has moved, is rejected; the read after it in the same turn is not sent, and the
    next turn sees only the rejection. Catches: removing the ``break`` after a rejected
    mutation."""
    sb_box: list[Sandbox] = []
    state: dict[str, Any] = {}

    def script(body: dict[str, Any], n: int) -> Any:
        out = tool_user(body)
        applies = [c for c in out["calls"] if c["tool"] == "apply_plan"]
        if not applies or "fired" in state:
            return None
        state["fired"] = n
        args = json.loads(applies[0]["arguments_json"])
        if why == "wrong_report":
            args["constraint_report_ref"] = "rpt_9999_deadbeef"
        else:
            sb = sb_box[0]
            env = sb.client("participant_facilitator").call(
                "check_in",
                arguments={
                    "resource_id": "facilitator",
                    "available": {"start": sb.clock().isoformat(), "end": at("18:00").isoformat()},
                },
                idempotency_key="ci-stale-parity",
            )
            assert env.status == "succeeded"
        return turn(
            [("apply_plan", args), ("get_action_receipt", {"idempotency_key": "after-reject"})]
        )

    sb = Sandbox(db, "dev01")
    sb_box.append(sb)
    policy, opener = build("P1", tmp_path, ToolScript(script))
    client = RecordingClient(sb.agent)
    result = policy.run(client)

    first = client.of("apply_plan")[0]
    assert first.envelope is not None and first.envelope.status == "rejected"
    code = first.envelope.error.code if first.envelope.error is not None else None
    if why == "wrong_report":
        assert code == "CANDIDATE_REPORT_MISMATCH"
    else:
        assert code in ("REVISION_CONFLICT", "CANDIDATE_STALE")
    lookups = [s.arguments.get("idempotency_key") for s in client.of("get_action_receipt")]
    assert "after-reject" not in lookups
    next_turn = turns_of(opener)[state["fired"]]  # the turn right after the rejected one
    results = last_results(next_turn)
    assert [r["tool"] for r in results] == ["apply_plan"]
    assert results[0]["error_code"] == code
    assert receipts_of(sb, "apply_plan")[0].status == "rejected"
    rejected = next(d for d in result.decisions if d.details.get("error_code") == code)
    assert rejected.kind == "wait"


def test_tool_use_caps_the_requested_wait_at_max_wait_minutes(db: Database, tmp_path: Path) -> None:
    """A requested wait is honored up to ``MAX_WAIT_MINUTES``. Catches: removing the cap (a
    100000-minute wait would be recorded as such)."""
    for minutes, expected in ((30, 30), (100000, MAX_WAIT_MINUTES)):

        def script(body: dict[str, Any], n: int, minutes: int = minutes) -> Any:
            return turn(done=True, decision="wait", wait_minutes=minutes)

        _, _, _, result = _run_p1(db, tmp_path / str(minutes), script)
        decision = result.decisions[-1]
        assert decision.kind == "wait" and decision.details["final_decision"] == "wait"
        assert decision.wait_until is not None
        assert decision.wait_until - decision.at == timedelta(minutes=expected), minutes
        # The run wakes at the requested time or earlier, at the shared wake schedule.
        assert result.wait_until is not None and result.wait_until <= decision.wait_until


def test_tool_use_an_invalid_tool_gets_one_repair_then_an_invalid_choice_wait(
    db: Database, tmp_path: Path
) -> None:
    """A tool outside the grant asks for exactly one repair (two turn requests, the second
    carrying the rejected reply and the server's reason), then the run ends with a visible
    ``invalid_choice`` wait and nothing sent. Catches: no repair; repeated repairs; sending the
    unknown tool."""

    def script(body: dict[str, Any], n: int) -> Any:
        return turn([("teleport_kits", {"quantity": 40})])

    _, client, opener, result = _run_p1(db, tmp_path, script)
    bodies = turns_of(opener)
    assert len(bodies) == 2 and len(opener.bodies) == 2
    first, repair = bodies
    assert len(repair["messages"]) == len(first["messages"]) + 2
    assert repair["messages"][-2]["role"] == "assistant"
    assert repair["messages"][-1]["role"] == "user"
    assert "teleport_kits" in repair["messages"][-1]["content"]
    wait = result.decisions[-1]
    assert wait.kind == "wait" and wait.details["failure"] == "invalid_choice"
    assert "teleport_kits" not in client.tools()
    assert set(client.tools()) <= {"get_event_state", "evaluate_candidates"}


def test_tool_use_idempotency_keys_carry_the_revision(db: Database, tmp_path: Path) -> None:
    """Every mutation key is ``tooluse-r<expected revision>-<tool>-<sha8(arguments)>``; an
    apply rejected as stale and the apply after the re-read carry their own revisions. Catches:
    a key without the revision (or not matching the revision sent)."""
    sb_box: list[Sandbox] = []
    fired: list[bool] = []

    def script(body: dict[str, Any], n: int) -> Any:
        out = tool_user(body)
        if not fired and any(c["tool"] == "apply_plan" for c in out["calls"]):
            fired.append(True)
            sb = sb_box[0]
            env = sb.client("participant_facilitator").call(
                "check_in",
                arguments={
                    "resource_id": "facilitator",
                    "available": {"start": sb.clock().isoformat(), "end": at("18:00").isoformat()},
                },
                idempotency_key="ci-stale-key",
            )
            assert env.status == "succeeded"
            out["done"] = False
        return out

    sb = Sandbox(db, "dev01")
    sb_box.append(sb)
    policy, _ = build("P1", tmp_path, ToolScript(script))
    client = RecordingClient(sb.agent)
    policy.run(client)

    mutations = [s for s in client.sent if s.tool in MUTATIONS]
    assert len(mutations) >= 2
    for s in mutations:
        sha8 = sha256_hex(canonical_json(s.arguments))[:8]
        assert s.expected_revision is not None
        assert s.idempotency_key == f"tooluse-r{s.expected_revision}-{s.tool}-{sha8}"
    stale, applied = mutations[0], mutations[-1]
    assert stale.envelope is not None and stale.envelope.status == "rejected"
    assert applied.envelope is not None and applied.envelope.receipt is not None
    assert applied.envelope.receipt.status == "applied"
    assert applied.expected_revision is not None and stale.expected_revision is not None
    assert applied.expected_revision > stale.expected_revision


def test_tool_use_max_turns_bounds_one_run(db: Database, tmp_path: Path) -> None:
    """A model that never ends its turn gets ``MAX_TURNS`` turn requests in one run, then the
    run ends (well inside the model-call cap) and asks to be woken at once. That wake is the
    model's own (the continuation), so it is a model turn whatever the attention rule says
    (the freeze audit), with its own bound. Catches: removing the per-run turn bound (only the
    model-call cap would stop it)."""
    cap = 2 * MAX_TURNS + 3

    def script(body: dict[str, Any], n: int) -> Any:
        return turn([("get_action_receipt", {"idempotency_key": f"never-done-{n}"})])

    sb = Sandbox(db, "dev01")
    policy, opener = build("P1", tmp_path, ToolScript(script), max_model_calls=cap)
    client = RecordingClient(sb.agent)
    first = policy.run(client)
    assert len(turns_of(opener)) == MAX_TURNS
    assert len(client.of("get_action_receipt")) == MAX_TURNS
    assert first.status == "waiting"
    assert not [d for d in first.decisions if d.details.get("failure") == "model_call_cap"]
    assert first.wait_until == sb.view().clock  # the turn bound asks for the next wake now
    second = policy.run(client)
    assert len(turns_of(opener)) == 2 * MAX_TURNS  # the continuation: its own bounded run
    assert second.status == "waiting"
    assert not [d for d in second.decisions if d.details.get("failure") == "model_call_cap"]
