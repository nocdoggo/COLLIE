"""Development cases end to end: deterministic policy, scripted exogenous actors, real executor,
state-based scoring. These are development checks, not held-out evaluation results."""

from __future__ import annotations

import pytest

from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store.database import Database
from tests.conftest import at


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, RunResult]:
    db = Database(tmp_path_factory.mktemp("cases") / "cases.sqlite3")
    return {ref: run_case(db, ref) for ref in ("dev01", "dev02", "dev04", "dev05", "dev06")}


def _life(r: RunResult) -> dict[str, str]:
    return {a.definition.activity_id: a.lifecycle for a in r.final_view.activities}


def _started(r: RunResult, activity: str):  # noqa: ANN202
    a = next(a for a in r.final_view.activities if a.definition.activity_id == activity)
    return next((e for e in a.history if e.state == "started"), None)


@pytest.mark.parametrize("ref", ["dev01", "dev02", "dev04", "dev05", "dev06"])
def test_case_matches_its_honest_expectation(results: dict[str, RunResult], ref: str) -> None:
    report = results[ref].report
    failed = [p for p in report.predicates if not p.passed]
    assert report.matches_expectation, (report.goal_complete, report.violations, failed)
    assert report.violations == ()


@pytest.mark.parametrize("ref", ["dev01", "dev02", "dev04", "dev05", "dev06"])
def test_runs_end_without_a_wake_after_the_close(results: dict[str, RunResult], ref: str) -> None:
    # At the 18:00 hard end the grants expire and the event closes; the policy is not woken
    # then, so no clean run ends with a rejected GRANT_EXPIRED read.
    r = results[ref]
    hard_end = r.final_view.goal.hard_end
    assert r.report.rejected_attempts_without_receipt == 0
    assert [c.call_id for c in r.history.tool_calls if c.error_code == "GRANT_EXPIRED"] == []
    assert all(c.requested_at is None or c.requested_at < hard_end for c in r.history.tool_calls)
    assert all(d.at < hard_end for d in r.history.decisions)


def test_dev01_genuine_disruption_swap(results: dict[str, RunResult]) -> None:
    r = results["dev01"]
    assert r.report.goal_complete and r.report.applied_plans == 1 and r.report.committed_cents == 0
    applied = [x for x in r.history.receipts if x.tool == "apply_plan" and x.status == "applied"]
    assert {c.entity_id for c in applied[0].state_changes} == {"demonstrations", "skills_exchange"}
    assert _started(r, "demonstrations").at == at("17:30")  # after the 17:24 arrival
    assert r.report.status_queries >= 1
    assert all(v == "completed" for v in _life(r).values())


def test_dev02_prepare_ask_commit(results: dict[str, RunResult]) -> None:
    r = results["dev02"]
    kinds = [d.kind for d in r.history.decisions]
    assert "prepare" in kinds and "ask" in kinds and "commit" in kinds
    assert r.report.committed_cents == 3500 and r.report.applied_plans == 1
    grant_changes = [
        x for x in r.history.receipts if x.tool == "update_grant" and x.status == "applied"
    ]
    assert len(grant_changes) == 1 and grant_changes[0].actor_id == "organizer_demo"
    assert _started(r, "demonstrations").at == at("17:10")
    holds = r.final_view.holds
    assert len(holds) == 1 and holds[0].status == "committed"


def test_dev04_stale_and_duplicate_notices_change_nothing(results: dict[str, RunResult]) -> None:
    r = results["dev04"]
    kinds = [d.kind for d in r.history.decisions]
    assert "inapplicable" in kinds and "duplicate" in kinds
    assert (
        r.report.applied_plans == 0 and r.report.committed_cents == 0 and r.final_view.holds == ()
    )
    # The re-delivered record never became a second observation.
    ids = [o.observation.source_record_id for o in r.final_view.observations]
    assert ids.count("delivery_message_09") == 1


def test_dev05_impossible_recovery_is_visibly_unsuccessful(results: dict[str, RunResult]) -> None:
    r = results["dev05"]
    assert not r.report.goal_complete and r.report.infeasibility_reported
    life = _life(r)
    assert life["demonstrations"] == "failed" and life["closing"] == "failed"
    assert r.report.committed_cents == 0 and r.report.applied_plans == 0
    infeasible = [d for d in r.history.decisions if d.kind == "infeasible"]
    assert infeasible and infeasible[0].details  # names the blocking constraints
    grants = {g.grant.grant_id: g for g in r.final_view.grants}
    assert grants["grant_coordinator_demo"].grant.max_total_committed_cents == 0


def test_dev06_unavailable_verification_is_bounded(results: dict[str, RunResult]) -> None:
    r = results["dev06"]
    assert r.report.failed_status_queries >= 2 and r.report.goal_complete
    first_two = [t for t in r.history.tool_calls if t.tool == "query_status"][:2]
    assert [t.envelope_status for t in first_two] == ["unavailable", "unavailable"]


def test_dev06_failed_status_checks_are_visible_in_state(results: dict[str, RunResult]) -> None:
    checks = results["dev06"].final_view.status_checks
    assert [c.envelope_status for c in checks[:2]] == ["unavailable", "unavailable"]
    assert all(
        c.error_code == "STATUS_UNAVAILABLE" and c.observation_id is None for c in checks[:2]
    )
    assert checks[0].requested_at == at("16:40") and checks[0].completed_at == at("16:42")


def test_dev05_narration_does_not_claim_success_after_failures(
    results: dict[str, RunResult],
) -> None:
    late = [d for d in results["dev05"].history.decisions if d.kind == "keep"]
    assert all("passes every hard check" not in d.summary for d in late)


def test_rejected_actions_run_rejects_without_state_change(tmp_path) -> None:  # noqa: ANN001
    from plan_b.scenarios.demos import rejected_actions_run
    from plan_b.scenarios.runner import audit_view

    db = Database(tmp_path / "demo.sqlite3")
    episode_id, log = rejected_actions_run(db)
    for row in log:
        actual = row["receipt_status"] or row["envelope_status"]
        if row["code"]:
            actual += f" {row['code']}"
        assert row["expected"].split(" (")[0] == actual, row
    retry = next(r for r in log if r["step"].startswith("identical retry"))
    first = next(r for r in log if r["step"] == "authorized backup booking")
    assert retry["replayed_receipt"] and retry["receipt_id"] == first["receipt_id"]
    view = audit_view(db, episode_id)
    assert view.budget.committed_cents == 3500 and len(view.commitments) == 1
    assert {g.grant.grant_id: g.grant.max_total_committed_cents for g in view.grants}[
        "grant_coordinator_demo"
    ] == 3500
