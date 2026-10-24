"""Regression tests for the third round of verified findings (backend core)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from plan_b.api.app import create_app
from plan_b.domain.models import PolicyDecision, PolicyRunResult
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import tick_loop
from plan_b.store.database import Database
from plan_b.store.episodes import create_episode
from plan_b.tools.executor import execute
from tests.conftest import Sandbox


class _ResetMidRun:
    policy_id = "test/reset-mid-run"

    def __init__(self, db: Database) -> None:
        self.db = db

    def run(self, client, max_tool_calls: int = 16) -> PolicyRunResult:  # noqa: ANN001
        env = client.call("get_event_state", arguments={})
        with self.db.write() as conn:
            create_episode(conn, case_ref="dev01")
        d = PolicyDecision(
            decision_id="x",
            policy_id=self.policy_id,
            at=env.scenario_time,
            revision=env.revision,
            kind="keep",
            summary="kept",
        )
        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(d,), tool_calls=1
        )


def test_tick_loop_survives_a_reset_during_a_policy_run(db: Database) -> None:
    sb = Sandbox(db, "dev01")
    runs = tick_loop(
        db,
        PolicyHost(db, lambda: _ResetMidRun(db)),
        sb.episode_id,
        minutes=5,
        run_policy=True,
        actors=None,
    )
    assert len(runs) == 1  # stopped cleanly; no AuthError from issuing a closed-episode session
    assert sb.view().episode_status == "closed" and sb.view().decisions == ()


def test_moderator_run_endpoint_reports_the_episode(tmp_path: Path) -> None:
    app = create_app(
        tmp_path / "a.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code="c",
        web_dist=tmp_path / "none",
    )
    c = TestClient(app)
    token = c.post("/api/auth/moderator", json={"code": "c"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    c.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=h)
    run = c.post("/api/moderator/run", json={"minutes": 2, "policy": True}, headers=h).json()
    assert run["episode_status"] == "active" and run["episode_id"].startswith("ep_")
    pol = c.post("/api/moderator/policy/run", json={}, headers=h).json()
    assert pol["episode_status"] == "active" and pol["episode_id"] == run["episode_id"]


def test_extreme_hypothesis_time_is_a_400(sandbox: Sandbox) -> None:
    body = {
        "tool": "evaluate_candidates",
        "event_id": "e_showcase_01",
        "arguments": {
            "hypotheses": [
                {
                    "resource_id": "projector",
                    "assume_ready_at": "0001-01-01T00:00:00Z",
                    "label": "far past",
                }
            ]
        },
    }
    status, env = execute(sandbox.db, sandbox.agent._token, "evaluate_candidates", body)  # noqa: SLF001
    assert status == 400 and env.error.code == "INVALID_REQUEST"


def _interp(text: str, entity: str):  # noqa: ANN202
    from datetime import date

    from plan_b.domain.fixtures import load_public_scenario
    from plan_b.domain.models import Observation, ObservationRecord, TimeWindow
    from plan_b.domain.projection import initial_snapshot
    from plan_b.evaluation.policies.parser import interpret_observation
    from tests.conftest import at

    snap = initial_snapshot(load_public_scenario())
    t = at("16:44")
    obs = Observation(
        observation_id="o9",
        event_id="e_showcase_01",
        entity_id=entity,
        kind="notice",
        source_id="delivery_contact",
        source_record_id="r9",
        correlation_group="g9",
        observed_at=t,
        received_at=t,
        valid_window=TimeWindow(start=t, end=at("18:00")),
        authority_scope="self_report",
        text=text,
        supersedes=(),
    )
    rec = ObservationRecord(
        observation=obs, channel="scenario_delivery", submitted_by=None, revision_after=4
    )
    return interpret_observation(
        rec,
        resources=snap.resources,
        event_date=date(2026, 11, 5),
        timezone="America/New_York",
        goal=snap.goal,
        event_id="e_showcase_01",
    )


def test_content_free_notice_triggers_no_verification() -> None:
    for text in ("Thanks for your patience.", "The driver is on his way, see you soon.", "Hi."):
        interp = _interp(text, "projector")
        assert interp.applicable is False and interp.verify_subject_id is None, text


def test_event_scoped_projector_wording_is_verified_on_the_projector() -> None:
    text = (
        "Our projector delivery may be about 40 minutes later than the promised 5 p.m. "
        "arrival because of traffic."
    )
    interp = _interp(text, "e_showcase_01")
    assert interp.applicable is False and interp.verify_subject_id == "projector"
    spare = _interp("The spare projector delivery is running late.", "e_showcase_01")
    assert spare.verify_subject_id is None


def test_fresh_status_is_not_rechecked_for_an_unsupported_notice(db: Database) -> None:
    sb = Sandbox(db, "dev02")
    host = PolicyHost(db)
    host.run(sb.episode_id)  # verifies the fixture notice (16:40 -> 16:42) and acts on it
    queries_before = sb.count(
        "tool_calls",
        "tool = 'query_status' AND actor_id = 'agent_demo' AND envelope_status = 'succeeded'",
    )
    sb.client("participant_host").call(
        "submit_observation",
        arguments={
            "text": "The projector delivery is running late again, sorry.",
            "entity_id": "projector",
        },
        idempotency_key="late-again",
    )
    host.run(sb.episode_id)
    projector_queries = [c for c in sb.view().status_checks if c.entity_id == "projector"]
    # One successful projector check from the first run; the unsupported notice (and its
    # hearsay channel) does not justify another within the 30-minute freshness window.
    assert len(projector_queries) == 1, projector_queries
    assert queries_before >= 1


def test_a_check_answers_a_verify_only_notice_as_of_its_request_time(db: Database) -> None:
    from plan_b.domain.models import StatusCheckView
    from plan_b.evaluation.policies.rules import _check_answer, _session_check_fresh
    from tests.conftest import at

    interp = _interp("Order P17 was cancelled by the carrier this afternoon; sorry.", "projector")
    assert interp.verify_subject_id == "projector" and interp.received_at == at("16:44")
    view = Sandbox(db, "dev01").view()

    def check(requested: str, completed: str, status: str = "succeeded") -> StatusCheckView:
        return StatusCheckView(
            call_id=f"c{requested}",
            actor_id="agent_demo",
            entity_id="projector",
            fact="delivery_eta",
            requested_at=at(requested),
            completed_at=at(completed),
            envelope_status=status,  # type: ignore[arg-type]
            error_code=None,
            observation_id=f"obs_{requested}",
            deduplicated=False,
            stale=False,
            reason=None,
        )

    def answer(*checks: StatusCheckView) -> str | None:
        return _check_answer(view.model_copy(update={"status_checks": checks}), interp)

    # Neither a check made before the notice nor one in flight when it arrived answers it.
    assert answer(check("16:40", "16:42")) is None
    assert answer(check("16:43", "16:45")) is None
    assert answer(check("16:44", "16:46", status="unavailable")) is None
    # A successful check requested at or after the notice's arrival does.
    assert answer(check("16:43", "16:45"), check("16:44", "16:46")) == "obs_16:44"
    # A supplier notice is never skipped for freshness; a session submission is.
    fresh = view.model_copy(
        update={"clock": at("16:45"), "status_checks": (check("16:40", "16:42"),)}
    )
    assert not _session_check_fresh(fresh, interp)
    session = interp.model_copy(update={"channel": "participant_session"})
    assert _session_check_fresh(fresh, session)
    assert not _session_check_fresh(fresh.model_copy(update={"clock": at("17:11")}), session)
