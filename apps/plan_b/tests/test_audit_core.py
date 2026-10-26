"""Regressions for the Wave 1 audit findings on the executor, the tools and the export endpoint.

* M1-INV-01: a hold asks the private steward only after every public refusal check.
* M1-INV-02: a Rejection raised by a handler rolls back that handler's writes, but not the
  modeled duration, the rejected receipt, the idempotency record or the call log.
* REQ-11: the status observation joins the lineage its private record names, reproducing the
  planning example ``observation_after_query.json``; the leak checker treats a lineage that is
  not yet public as a private marker.
* WEB-5: ``POST /api/moderator/export`` records the policy that actually ran.

Every test runs against the real executor and SQLite store (``tests/conftest.py`` Sandbox) or
the FastAPI app in-process.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plan_b.api.app import create_app, policies_that_ran
from plan_b.domain.models import ObservationRecord, PolicyDecision, PrivateCase
from plan_b.domain.planning_map import to_planning_observation_record
from plan_b.domain.timeutil import parse_ts
from plan_b.store import repo
from plan_b.tools import handlers
from plan_b.tools.executor import Ctx, Rejection
from plan_b.world.leakcheck import find_leaks, private_markers
from plan_b.world.world import load_case
from tests.conftest import Sandbox, at
from tests.test_api import CODE, _auth, _moderator
from tests.test_planning_map import validate

EXAMPLES = Path(__file__).resolve().parents[1] / "data" / "planning" / "examples"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")


# ---------------------------------------------------------------------------
# M1-INV-01: public refusals come before the steward's answer
# ---------------------------------------------------------------------------


def _hold_backup_in_dev05(make_sandbox: Any) -> Sandbox:
    sb: Sandbox = make_sandbox("dev05")  # the steward reports the backup booked elsewhere
    backup = next(r for r in sb.view().resources if r.definition.resource_id == "backup_projector")
    assert backup.status == "available"  # publicly, nothing says otherwise
    return sb


def test_dev05_hold_after_cutoff_reports_the_cutoff(make_sandbox: Any) -> None:
    sb = _hold_backup_in_dev05(make_sandbox)
    sb.advance_to("16:55")  # the hold executes at 16:56; the 17:10 window's cutoff was 16:55
    res = sb.hold_backup("k-cut")
    assert res.receipt is not None and res.receipt.status == "rejected"
    assert res.receipt.error_code == "COMMITMENT_CUTOFF_PASSED"
    assert "steward" not in (res.receipt.error_message or "")
    assert sb.count("holds") == 0 and sb.ledger() == (0, 0)


def test_dev05_hold_beyond_reserved_authority_reports_the_budget(make_sandbox: Any) -> None:
    sb = _hold_backup_in_dev05(make_sandbox)
    lowered = sb.organizer.call(
        "update_grant",
        arguments={
            "target_grant_id": "grant_coordinator_demo",
            "max_total_reserved_cents": 0,
            "reason": "test: no reserved authority",
        },
        idempotency_key="org-zero",
        expected_revision=sb.revision(),
    )
    assert lowered.receipt is not None and lowered.receipt.status == "applied"
    res = sb.hold_backup("k-zero")
    assert res.receipt is not None and res.receipt.status == "rejected"
    assert res.receipt.error_code == "BUDGET_EXCEEDED"
    assert res.error is not None and res.error.details["limit"] == 0
    assert sb.count("holds") == 0 and sb.ledger() == (0, 0)


def test_dev05_hold_passing_every_public_check_gets_the_steward_answer(
    make_sandbox: Any,
) -> None:
    sb = _hold_backup_in_dev05(make_sandbox)
    revision = sb.revision()
    res = sb.hold_backup("k-steward")
    assert res.receipt is not None and res.receipt.status == "rejected"
    assert res.receipt.error_code == "RESOURCE_UNAVAILABLE"
    assert "the steward of backup_projector declined the hold" in (res.receipt.error_message or "")
    # The refusal discloses no private record, and nothing is ingested or held.
    assert "backup_desk_record_8" not in res.model_dump_json()
    assert sb.count("holds") == 0 and sb.count("observations") == 1
    assert sb.ledger() == (0, 0) and sb.revision() == revision


def test_dev01_hold_still_succeeds_after_the_steward_confirms(sandbox: Sandbox) -> None:
    res = sandbox.hold_backup("k-ok")
    assert res.receipt is not None and res.receipt.status == "applied"
    assert res.data is not None and res.data["hold"]["hold_id"] == "hold_0001"


# ---------------------------------------------------------------------------
# M1-INV-02: a late Rejection rolls back the handler's writes
# ---------------------------------------------------------------------------


def _plan_rows(sb: Sandbox) -> list[tuple[int, str | None]]:
    with sb.db.read() as conn:
        rows = conn.execute(
            "SELECT plan_version, receipt_id FROM plans WHERE episode_id = ? ORDER BY plan_version",
            (sb.episode_id,),
        ).fetchall()
    return [(r["plan_version"], r["receipt_id"]) for r in rows]


def _plan_version(sb: Sandbox) -> int:
    with sb.db.read() as conn:
        return repo.get_episode(conn, sb.episode_id).plan_version


def test_late_rejection_in_apply_plan_leaves_no_partial_plan(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox.hold_backup("k-hold")  # hold_0001, 3500 reserved
    sandbox.raise_committed_limit()
    env = sandbox.evaluate()
    sub = sandbox.candidate(env, "Use backup_projector")
    assert sub["applicable_now"]
    before = {
        "plans": _plan_rows(sandbox),
        "plan_version": _plan_version(sandbox),
        "revision": sandbox.revision(),
        "ledger": sandbox.ledger(),
        "holds": [h.status for h in sandbox.view().holds],
    }
    assert before["plans"] == [(1, None)] and before["plan_version"] == 1
    clock = sandbox.clock()
    original_bump = handlers._bump

    def late(ctx: Ctx, cause_kind: str, cause_ref: str | None, summary: str) -> int:
        # Fault injection: by now apply_plan has inserted plan v2, moved plan_version, converted
        # the hold, inserted the commitment and written both ledger rows.
        if cause_kind == "plan_applied":
            raise Rejection("UNKNOWN_ENTITY", "injected late rejection")
        return original_bump(ctx, cause_kind, cause_ref, summary)

    monkeypatch.setattr(handlers, "_bump", late)
    res = sandbox.apply(sub, env, "k-late")
    assert res.status == "rejected" and res.receipt is not None
    assert res.receipt.status == "rejected" and res.receipt.error_code == "UNKNOWN_ENTITY"
    assert res.receipt.revision_before == res.receipt.revision_after == before["revision"]
    assert res.receipt.state_changes == () and res.receipt.committed_delta_cents == 0
    # The handler's writes are gone ...
    assert _plan_rows(sandbox) == before["plans"]
    assert _plan_version(sandbox) == before["plan_version"]
    assert sandbox.revision() == before["revision"] and sandbox.ledger() == before["ledger"]
    assert [h.status for h in sandbox.view().holds] == before["holds"] == ["active"]
    assert sandbox.count("commitments") == 0
    assert sandbox.count("ledger", "kind IN ('convert_reserve', 'commit_charge')") == 0
    # ... but the modeled duration, the rejected receipt, the idempotency record and the call
    # log are kept.
    assert sandbox.clock() == clock + timedelta(minutes=1)  # apply_plan's modeled duration
    assert res.receipt.executed_at == sandbox.clock()
    assert sandbox.count("receipts", "receipt_id = ?", (res.receipt.receipt_id,)) == 1
    assert sandbox.count("idempotency", "idempotency_key = 'k-late'") == 1
    assert sandbox.count("tool_calls", "receipt_id = ?", (res.receipt.receipt_id,)) == 1
    retry = sandbox.apply(sub, env, "k-late")
    assert retry.replayed_receipt and retry.receipt == res.receipt

    # Without the fault, the same candidate (the revision did not move) applies cleanly and
    # reuses the plan version and commitment id the rolled-back attempt had taken.
    monkeypatch.setattr(handlers, "_bump", original_bump)
    ok = sandbox.apply(sub, env, "k-clean")
    assert ok.receipt is not None and ok.receipt.status == "applied"
    assert ok.data is not None and ok.data["commitment_ids"] == ["commit_0001"]
    assert _plan_rows(sandbox) == [(1, None), (2, ok.receipt.receipt_id)]
    assert _plan_version(sandbox) == 2 and sandbox.ledger() == (3500, 0)


def test_late_rejection_in_hold_resource_leaves_no_hold(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_view = handlers._hold_view

    def missing(ctx: Ctx, hold_id: str) -> Any:
        raise Rejection("UNKNOWN_ENTITY", f"injected: {hold_id} not found after insert")

    monkeypatch.setattr(handlers, "_hold_view", missing)
    res = sandbox.hold_backup("k-late-hold")
    assert res.receipt is not None and res.receipt.error_code == "UNKNOWN_ENTITY"
    assert sandbox.count("holds") == 0 and sandbox.ledger() == (0, 0)
    assert sandbox.count("ledger") == 0 and sandbox.revision() == 3
    assert sandbox.clock() == at("16:41")  # the hold's one-minute duration still passed
    monkeypatch.setattr(handlers, "_hold_view", original_view)
    ok = sandbox.hold_backup("k-hold")
    assert ok.data is not None and ok.data["hold"]["hold_id"] == "hold_0001"


# ---------------------------------------------------------------------------
# REQ-11: the status observation reproduces the planning example
# ---------------------------------------------------------------------------


def _normalized(value: Any) -> Any:
    """Timestamps compared as instants (the example writes -05:00, the runtime writes Z)."""
    if isinstance(value, dict):
        return {k: _normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalized(v) for v in value]
    if isinstance(value, str) and TIMESTAMP.match(value):
        return parse_ts(value)
    return value


def test_dev01_status_observation_matches_planning_example(sandbox: Sandbox) -> None:
    example = json.loads((EXAMPLES / "observation_after_query.json").read_text())
    revision_before = sandbox.revision()
    env = sandbox.query()
    assert env.status == "succeeded" and env.data is not None
    record = ObservationRecord.model_validate(env.data["observation"])
    projected = to_planning_observation_record(
        record, revision_before=revision_before, ingested_at=record.observation.received_at
    )
    validate(projected, "ObservationRecord")
    actual, expected = _normalized(projected), _normalized(example)
    assert set(actual) == set(expected)
    for key in expected:
        if key != "observation":
            assert actual[key] == expected[key], key
    assert set(actual["observation"]) == set(expected["observation"])
    for key, value in expected["observation"].items():
        if key == "observation_id":
            continue  # store-assigned at runtime (obs_0001); the example names it obs_status_02
        assert actual["observation"][key] == value, key
    assert actual["observation"]["observation_id"] == "obs_0001"
    # One lineage with the visible notice and, later, the arrival.
    assert record.observation.correlation_group == "projector_delivery_01"
    notice = sandbox.view().observations[0].observation
    assert notice.observation_id == "obs_notice_01"
    assert notice.correlation_group == record.observation.correlation_group
    sandbox.advance_to("17:24")
    arrival = next(
        o.observation
        for o in sandbox.view().observations
        if o.observation.source_record_id == "receipt_P17"
    )
    assert arrival.correlation_group == "projector_delivery_01"


def test_status_record_without_a_lineage_keeps_its_own_group(sandbox: Sandbox) -> None:
    env = sandbox.query("backup_projector", "availability")
    assert env.status == "succeeded" and env.data is not None
    assert env.data["observation"]["observation"]["correlation_group"] == "backup_projector_status"


def _with_projector_lineage(group: str) -> PrivateCase:
    """dev01 whose projector status record names ``group`` as its lineage."""
    case = load_case("dev01")
    records = list(case.status_model)
    i = next(i for i, r in enumerate(records) if r.entity_id == "projector" and r.response)
    response = records[i].response
    assert response is not None
    records[i] = records[i].model_copy(
        update={"response": response.model_copy(update={"correlation_group": group})}
    )
    return case.model_copy(update={"status_model": tuple(records)})


def test_leakcheck_flags_a_status_lineage_until_it_is_public(sandbox: Sandbox) -> None:
    # A planted lineage nothing public carries yet is a private marker, like the record's id and
    # text: a payload naming it at 16:41 leaks what the status source would answer.
    planted = _with_projector_lineage("projector_delivery_77")
    payload = '{"correlation_group":"projector_delivery_77"}'
    start = sandbox.view().observations  # only the fixture notice
    assert "projector_delivery_77" in private_markers(planted, start, at("16:41"))
    assert find_leaks(payload, planted, start, at("16:41")) == ["projector_delivery_77"]
    assert find_leaks(payload, planted, [], None) == ["projector_delivery_77"]
    # Once a public observation carries the lineage it is public, even though the status record
    # itself has not been read: an organizer notice in that lineage arrives at 16:41.
    notice = sandbox.organizer.call(
        "submit_observation",
        arguments={
            "text": "Order P17 has a new tracking number.",
            "entity_id": "projector",
            "correlation_group": "projector_delivery_77",
        },
        idempotency_key="n-77",
    )
    assert notice.receipt is not None and notice.receipt.status == "applied", notice
    assert notice.data is not None
    received = parse_ts(notice.data["observation"]["observation"]["received_at"])
    seen = sandbox.view().observations
    assert find_leaks(payload, planted, seen, received - timedelta(minutes=1)) == [
        "projector_delivery_77"
    ]
    assert find_leaks(payload, planted, seen, received) == []
    # Reading the record makes all of it public, lineage included.
    planted_late = _with_projector_lineage("projector_delivery_78")
    late = '{"correlation_group":"projector_delivery_78"}'
    assert find_leaks(late, planted_late, seen, sandbox.clock()) == ["projector_delivery_78"]
    assert sandbox.query().status == "succeeded"
    after = sandbox.view()
    assert find_leaks(late, planted_late, after.observations, after.clock) == []


@pytest.mark.parametrize("case_ref", ["dev01", "dev02", "dev04", "dev05", "dev06"])
def test_shipped_status_lineages_are_public_from_the_start(
    make_sandbox: Any, case_ref: str
) -> None:
    # The shipped records name the fixture notice's lineage, public from 16:40: no false positive,
    # although every view names it (the notice) from the first frame on.
    case = load_case(case_ref)
    lineages = {r.response.correlation_group for r in case.status_model if r.response}
    assert lineages - {None} == {"projector_delivery_01"}
    sb: Sandbox = make_sandbox(case_ref)
    start = sb.view()
    assert "projector_delivery_01" in start.model_dump_json()
    for observations in (start.observations, []):  # with or without the episode's records
        assert "projector_delivery_01" not in private_markers(case, observations, start.clock)
        assert find_leaks(start.model_dump_json(), case, observations, start.clock) == []
    # Before the fixture notice is received, the lineage would still be private.
    assert "projector_delivery_01" in private_markers(case, [], at("16:39"))


# ---------------------------------------------------------------------------
# WEB-5: the export names the policy that ran
# ---------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path: Path) -> TestClient:
    app = create_app(
        tmp_path / "api.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code=CODE,
        web_dist=tmp_path / "no_dist",
    )
    return TestClient(app)


def _export(c: TestClient, mod: str) -> dict[str, Any]:
    r = c.post("/api/moderator/export", headers=_auth(mod))
    assert r.status_code == 200, r.text
    trace: dict[str, Any] = r.json()["trace"]
    return trace


def test_export_without_a_policy_run_records_no_policy(api: TestClient, tmp_path: Path) -> None:
    mod = _moderator(api)
    api.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    r = api.post("/api/moderator/clock", json={"advance_minutes": 5}, headers=_auth(mod))
    assert r.status_code == 200
    trace = _export(api, mod)
    assert trace["decisions"] == [] and trace["source"]["policy_id"] is None
    written = sorted((tmp_path / "var" / "traces").glob("*.json"))
    assert len(written) == 1
    assert json.loads(written[0].read_text())["source"]["policy_id"] is None


def test_export_after_a_policy_run_records_that_policy(api: TestClient) -> None:
    mod = _moderator(api)
    api.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    run = api.post("/api/moderator/policy/run", json={}, headers=_auth(mod))
    assert run.status_code == 200 and run.json()["decisions"]
    trace = _export(api, mod)
    assert {d["policy_id"] for d in trace["decisions"]} == {"rules/1.0.0"}
    assert trace["source"]["policy_id"] == "rules/1.0.0"


def test_export_names_every_policy_that_decided(api: TestClient) -> None:
    mod = _moderator(api)
    api.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    api.post("/api/moderator/policy/run", json={}, headers=_auth(mod))
    db = api.app.state.db
    with db.write() as conn:
        episode_id = repo.current_episode_id(conn)
        ep = repo.get_episode(conn, episode_id)
        repo.insert_decision(
            conn,
            episode_id,
            PolicyDecision(
                decision_id="dec_x",
                policy_id="alt/0.1.0",
                at=ep.clock,
                revision=ep.revision,
                kind="stop",
                summary="a second policy decided too",
            ),
        )
    assert _export(api, mod)["source"]["policy_id"] == "alt/0.1.0,rules/1.0.0"


def test_policies_that_ran_is_null_single_or_sorted_and_joined() -> None:
    assert policies_that_ran([]) is None
    assert policies_that_ran(["rules/1.0.0", "rules/1.0.0"]) == "rules/1.0.0"
    assert policies_that_ran(["rules/1.0.0", "alt/0.1.0", "rules/1.0.0"]) == (
        "alt/0.1.0,rules/1.0.0"
    )
