"""Policy selection, per-episode caps and mode labels (Wave 2 integration).

Every coordinator policy runs under one set of per-episode caps (development values: 48 tool
calls, 8 model calls). The caps and the mode label are recorded in the outcome report and on
every stored decision; a reached cap stops the policy for the episode with a decision saying so.
``run_case(policy="live")`` builds the Build 1 live policy from its server-side configuration;
here the provider's HTTP opener is a scripted fake, so nothing reaches the network.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent import provider as provider_module
from plan_b.agent.orchestrator import POLICY_ID as LIVE_POLICY_ID
from plan_b.cli import main
from plan_b.domain.models import PolicyDecision, PolicyRunResult, ToolEnvelope
from plan_b.evaluation.export_trace import build_trace, verify_trace
from plan_b.evaluation.policies.base import ToolClient
from plan_b.scenarios.policy_host import (
    DETERMINISTIC_LABEL,
    DEVELOPMENT_CAPS,
    EpisodeCaps,
    PolicyHost,
    PolicyLockedError,
    mode_label,
    policy_factory_for,
)
from plan_b.scenarios.runner import RunResult, run_case
from plan_b.store import repo
from plan_b.store.database import Database
from tests.conftest import Sandbox
from tests.test_agent_provider import (
    REQUESTED_MODEL,
    RETURNED_MODEL,
    FakeOpener,
    ScriptedModel,
    make_config,
)

LIVE_LABEL = f"Live agent · {RETURNED_MODEL}"


def coordinator_calls(db: Database, episode_id: str) -> int:
    with db.read() as conn:
        return sum(1 for t in repo.tool_calls(conn, episode_id) if t.actor_id == "agent_demo")


def host_decisions(result: RunResult) -> list[PolicyDecision]:
    return [d for d in result.history.decisions if d.details.get("recorded_by") == "host"]


@pytest.fixture
def scripted_opener(monkeypatch: pytest.MonkeyPatch) -> FakeOpener:
    """Every provider built from here on talks to a scripted model, not the network."""
    opener = FakeOpener(ScriptedModel())
    monkeypatch.setattr(provider_module.urllib.request, "build_opener", lambda *_: opener)
    assert provider_module.urllib.request is urllib.request
    return opener


def run_live(
    db: Database, tmp_path: Path, case: str = "dev01", caps: EpisodeCaps = DEVELOPMENT_CAPS
) -> RunResult:
    return run_case(db, case, policy="live", caps=caps, live_config=make_config(tmp_path))


# ---------------------------------------------------------------------- caps for every policy


@pytest.mark.parametrize("case", ["dev01", "dev02", "pantry_dev01", "skills_dev02"])
def test_rule_baselines_run_under_the_development_caps(db: Database, case: str) -> None:
    result = run_case(db, case)
    report = result.report
    caps = report.episode_caps
    assert caps is not None and report.matches_expectation is True
    assert (caps.phase, caps.max_tool_calls, caps.max_model_calls) == ("development", 48, 8)
    assert caps.tool_calls == coordinator_calls(db, result.episode_id)
    assert 19 <= caps.tool_calls <= 30 and caps.model_calls == 0 and caps.reached == ()
    assert report.mode_label == DETERMINISTIC_LABEL
    assert result.history.decisions and all(
        d.details["policy_mode"]
        == {"policy": "rules", "label": DETERMINISTIC_LABEL, "caps": DEVELOPMENT_CAPS.as_dict()}
        for d in result.history.decisions
    )
    assert host_decisions(result) == []


def test_a_reached_tool_cap_stops_the_rule_policy_and_says_so(db: Database) -> None:
    result = run_case(db, "dev02", caps=EpisodeCaps(max_tool_calls=10))
    caps = result.report.episode_caps
    assert caps is not None and caps.reached == ("tool_calls",)
    assert caps.tool_calls == coordinator_calls(db, result.episode_id) == 10
    [stop] = host_decisions(result)
    assert stop.kind == "stop" and stop.details["failure"] == "tool_call_cap"
    assert stop.details["usage"] == {"tool_calls": 10, "model_calls": 0}
    assert "not woken again" in stop.summary
    # It is the last thing the policy side did: no run happened after it.
    assert result.policy_runs[-1].decisions[-1].decision_id == stop.decision_id
    assert result.report.matches_expectation is False  # the cap cut the recovery short


class _FailingCalls:
    """Each run sends up to five malformed requests: failed calls count toward the cap."""

    policy_id = "test-failing/1.0.0"

    def run(self, client: ToolClient, max_tool_calls: int = 16) -> PolicyRunResult:
        calls = 0
        for _ in range(min(5, max_tool_calls)):
            env: ToolEnvelope = client.call("hold_resource", arguments={"bad": True})
            assert env.status == "rejected"
            calls += 1
        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(), tool_calls=calls
        )


def test_failed_calls_count_and_a_run_never_exceeds_the_remaining_budget(
    sandbox: Sandbox,
) -> None:
    host = PolicyHost(sandbox.db, _FailingCalls, caps=EpisodeCaps(max_tool_calls=12))
    runs = [host.run(sandbox.episode_id) for _ in range(4)]
    assert [r.tool_calls for r in runs] == [5, 5, 2, 0]
    assert runs[3].status == "stopped" and "tool calls cap is reached" in runs[3].note
    assert coordinator_calls(sandbox.db, sandbox.episode_id) == 12
    with sandbox.db.read() as conn:
        stops = [d for d in repo.decisions(conn, sandbox.episode_id) if d.kind == "stop"]
    assert len(stops) == 1 and stops[0].details["failure"] == "tool_call_cap"
    assert host.capped(sandbox.episode_id)


def test_caps_are_validated() -> None:
    with pytest.raises(ValueError):
        EpisodeCaps(max_tool_calls=0)
    with pytest.raises(ValueError):
        EpisodeCaps(max_model_calls=0)


# ---------------------------------------------------------------------- the live policy


def test_live_policy_selected_by_name_runs_under_the_same_caps(
    db: Database, tmp_path: Path, scripted_opener: FakeOpener
) -> None:
    result = run_live(db, tmp_path)
    report = result.report
    assert report.policy_id == LIVE_POLICY_ID and report.goal_complete
    caps = report.episode_caps
    assert caps is not None and (caps.max_tool_calls, caps.max_model_calls) == (48, 8)
    assert caps.model_calls == len(scripted_opener.requests) > 0
    assert caps.tool_calls == coordinator_calls(db, result.episode_id) and caps.reached == ()
    assert report.mode_label == LIVE_LABEL
    live = [d for d in result.history.decisions if d.policy_id == LIVE_POLICY_ID]
    assert live and all(d.details["policy_mode"]["label"] == LIVE_LABEL for d in live)
    # The live policy itself holds the same caps (one cap for every policy).
    episode = live[-1].details["model"]["episode"]
    assert (episode["max_tool_calls"], episode["max_model_calls"]) == (48, 8)
    trace = build_trace(db, result.episode_id, policy_id=report.policy_id)
    assert verify_trace(trace) == []
    assert trace["source"]["policy_id"] == LIVE_POLICY_ID
    assert {d["details"]["policy_mode"]["label"] for d in trace["decisions"]} == {LIVE_LABEL}
    assert LIVE_LABEL in str(trace["final_state"]["decisions"])


def test_a_reached_model_cap_stops_waking_the_live_policy(
    db: Database, tmp_path: Path, scripted_opener: FakeOpener
) -> None:
    result = run_live(db, tmp_path, caps=EpisodeCaps(max_model_calls=2))
    caps = result.report.episode_caps
    assert caps is not None and "model_calls" in caps.reached
    assert caps.model_calls == len(scripted_opener.requests) == 2
    [stop] = host_decisions(result)
    assert stop.details["failure"] == "model_call_cap" and stop.policy_id == LIVE_POLICY_ID
    assert result.policy_runs[-1].decisions[-1].decision_id == stop.decision_id


def test_mode_labels_name_the_policy_that_ran() -> None:
    assert mode_label("rules/1.0.0", None) == DETERMINISTIC_LABEL
    assert mode_label("pantry-rules/1.0.0", None) == DETERMINISTIC_LABEL
    assert mode_label(LIVE_POLICY_ID, "vendor/model-x") == "Live agent · vendor/model-x"
    assert (
        mode_label(LIVE_POLICY_ID, None, REQUESTED_MODEL)
        == f"Live agent · {REQUESTED_MODEL} (requested; no reply yet)"
    )


def test_selection_locks_once_the_coordinator_acted_and_survives_a_restart(
    db: Database, tmp_path: Path, scripted_opener: FakeOpener
) -> None:
    config = make_config(tmp_path)

    def factories(choice: Any, profile_id: str) -> Any:
        return policy_factory_for(choice, profile_id, live_config=config)

    sb = Sandbox(db, "dev01")
    host = PolicyHost(db, factory_for=factories)
    assert host.choice(sb.episode_id) == "rules"
    host.select(sb.episode_id, "live")
    assert host.describe(sb.episode_id)["label"].endswith("(requested; no reply yet)")
    run = host.run(sb.episode_id)
    assert run.policy_id == LIVE_POLICY_ID and run.decisions
    with pytest.raises(PolicyLockedError):
        host.select(sb.episode_id, "rules")
    restarted = PolicyHost(db, factory_for=factories)
    assert restarted.choice(sb.episode_id) == "live"
    assert restarted.mode_label(sb.episode_id) == LIVE_LABEL


# ---------------------------------------------------------------------- command line


def test_cli_runs_every_case_on_its_own_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["run-case", "skills_dev02", "--db", str(tmp_path / "cli.sqlite3")]) == 0
    assert capsys.readouterr().out == (
        "skills_dev02: goal_complete=True infeasibility_reported=False applied_plans=1"
        " committed=0 violations=0 matches_expectation=True\n"
    )


def test_cli_refuses_an_unconfigured_live_policy_and_bad_caps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "cli.sqlite3"
    monkeypatch.setenv("PLAN_B_MODEL_BASE_URL", "ftp://models.invalid/v1")
    assert main(["run-case", "dev01", "--policy", "live", "--db", str(db)]) == 2
    assert "the live policy is not configured" in capsys.readouterr().out
    assert main(["run-case", "dev01", "--max-episode-tool-calls", "0", "--db", str(db)]) == 2
    assert "invalid caps" in capsys.readouterr().out
    assert not db.exists()
