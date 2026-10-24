"""HTTP integration of Wave 2: cases on their own scenarios, the moderator's policy choice,
the per-episode caps on board runs, and the participation surface.

The live policy is never called over the network: the app gets a configuration loader and a
factory whose provider talks to a scripted model (``tests.test_agent_provider``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plan_b.agent.config import ModelConfig, ModelConfigError
from plan_b.agent.orchestrator import LivePolicy
from plan_b.api.app import create_app
from plan_b.api.config import factory_for, live_availability, load_episode_caps
from plan_b.evaluation.policies.base import Policy
from plan_b.scenarios.policy_host import EpisodeCaps, PolicyChoice, policy_factory_for
from tests.test_agent_provider import (
    FAKE_KEY,
    REQUESTED_MODEL,
    RETURNED_MODEL,
    FakeOpener,
    ScriptedModel,
    make_config,
    make_provider,
)

CODE = "test-moderator-code"
SKILLS_EVENT = "e_skills_01"
TERMS = "community_fixture_catalog_v1"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _app(
    tmp_path: Path,
    *,
    config: ModelConfig | None = None,
    caps: EpisodeCaps | None = None,
) -> TestClient:
    def loader() -> ModelConfig:
        if config is None:
            raise ModelConfigError("PLAN_B_MODEL_BASE_URL is not configured")
        return config

    def factories(choice: PolicyChoice, profile_id: str) -> Callable[[], Policy]:
        if choice == "rules":
            return policy_factory_for("rules", profile_id)
        cfg = loader()
        return lambda: LivePolicy(make_provider(cfg, FakeOpener(ScriptedModel())))

    app = create_app(
        tmp_path / "api.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code=CODE,
        web_dist=tmp_path / "no_dist",
        caps=caps,
        live_config_loader=loader,
        policy_factories=factories,
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return _app(tmp_path)


@pytest.fixture
def live_client(tmp_path: Path) -> TestClient:
    return _app(tmp_path, config=make_config(tmp_path))


def _moderator(c: TestClient) -> str:
    r = c.post("/api/auth/moderator", json={"code": CODE})
    assert r.status_code == 200
    return str(r.json()["token"])


def _join(c: TestClient, mod: str, principal: str) -> str:
    r = c.post("/api/moderator/sessions", json={"principal_id": principal}, headers=_auth(mod))
    assert r.status_code == 200, r.text
    j = c.post("/api/auth/join", json={"code": r.json()["join_code"]})
    assert j.status_code == 200, j.text
    return str(j.json()["token"])


def _load(c: TestClient, mod: str, case_ref: str, **body: Any) -> Any:
    return c.post(
        "/api/moderator/episodes", json={"case_ref": case_ref, **body}, headers=_auth(mod)
    )


# ---------------------------------------------------------------------- cases and policies


def test_cases_name_their_scenario_and_load_without_one(client: TestClient) -> None:
    mod = _moderator(client)
    cases = {
        c["case_ref"]: c for c in client.get("/api/moderator/cases", headers=_auth(mod)).json()
    }
    assert cases["dev01"] == {
        "case_ref": "dev01",
        "scenario_id": "dev_fixture_01",
        "profile_id": "campus_showcase",
    }
    assert cases["skills_dev02"]["scenario_id"] == "dev_fixture_02"
    assert cases["pantry_dev01"]["profile_id"] == "pantry_continuity"
    loaded = _load(client, mod, "pantry_dev01")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["scenario_id"] == "dev_fixture_03"
    assert loaded.json()["mode_label"] == "Deterministic policy"
    # The board's "rules" choice is the profile's baseline.
    run = client.post("/api/moderator/policy/run", json={}, headers=_auth(mod))
    assert run.status_code == 200 and run.json()["policy_id"] == "pantry-rules/1.0.0"
    wrong = _load(client, mod, "skills_dev01", scenario_id="dev_fixture_01")
    assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "SCENARIO_MISMATCH"
    assert "dev_fixture_02" not in wrong.text


def test_live_choice_needs_its_configuration_and_resets_nothing(client: TestClient) -> None:
    mod = _moderator(client)
    first = _load(client, mod, "dev01").json()["episode_id"]
    refused = _load(client, mod, "dev02", policy="live")
    assert refused.status_code == 400
    assert refused.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"
    current = client.get("/api/moderator/current", headers=_auth(mod)).json()
    assert current["episode_id"] == first  # the refused load closed nothing
    view = client.get("/api/moderator/policy", headers=_auth(mod)).json()
    assert view["policy"] == "rules" and view["live_available"] is False
    assert "not configured" in view["reason"]
    switch = client.post("/api/moderator/policy", json={"policy": "live"}, headers=_auth(mod))
    assert switch.status_code == 400


def test_moderator_switches_to_live_before_the_coordinator_acts(
    live_client: TestClient, tmp_path: Path
) -> None:
    c = live_client
    mod = _moderator(c)
    _load(c, mod, "dev01")
    view = c.get("/api/moderator/policy", headers=_auth(mod)).json()
    assert view["policy"] == "rules" and view["live_available"] is True
    assert view["model_id"] == REQUESTED_MODEL and view["locked"] is False
    chosen = c.post("/api/moderator/policy", json={"policy": "live"}, headers=_auth(mod)).json()
    assert chosen["policy"] == "live" and chosen["policy_id"] == "live/1.0.0"
    assert chosen["label"] == f"Live agent · {REQUESTED_MODEL} (requested; no reply yet)"
    assert chosen["caps"]["max_tool_calls"] == 48 and chosen["caps"]["model_calls"] == 0
    run = c.post("/api/moderator/policy/run", json={}, headers=_auth(mod)).json()
    assert run["policy_id"] == "live/1.0.0"
    assert run["mode_label"] == f"Live agent · {RETURNED_MODEL}"
    assert all(
        d["details"]["policy_mode"]["label"] == f"Live agent · {RETURNED_MODEL}"
        for d in run["decisions"]
    )
    locked = c.post("/api/moderator/policy", json={"policy": "rules"}, headers=_auth(mod))
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "POLICY_LOCKED"
    organizer = _join(c, mod, "organizer_demo")
    public = c.get("/api/policy", headers=_auth(organizer)).json()
    assert public["policy"] == "live" and public["label"] == f"Live agent · {RETURNED_MODEL}"
    state = c.get("/api/state", headers=_auth(organizer)).text
    for text in (c.get("/api/moderator/policy", headers=_auth(mod)).text, state, str(run)):
        assert FAKE_KEY not in text and str(tmp_path) not in text


def test_board_runs_stop_at_the_episode_cap(tmp_path: Path) -> None:
    c = _app(tmp_path, caps=EpisodeCaps(max_tool_calls=5))
    mod = _moderator(c)
    _load(c, mod, "dev01")
    r = c.post("/api/moderator/run", json={"minutes": 30}, headers=_auth(mod))
    assert r.status_code == 200
    view = c.get("/api/moderator/policy", headers=_auth(mod)).json()
    assert view["caps"]["tool_calls"] == 5 and view["caps"]["reached"] == ["tool_calls"]
    state = c.get("/api/state", headers=_auth(mod)).json()
    agent_calls = [a for a in state["receipts"] if a["actor_id"] == "agent_demo"]
    assert len(agent_calls) <= 5
    stops = [d for d in state["decisions"] if d["details"].get("recorded_by") == "host"]
    assert len(stops) == 1 and stops[0]["details"]["failure"] == "tool_call_cap"
    again = c.post("/api/moderator/policy/run", json={}, headers=_auth(mod)).json()
    assert again["status"] == "stopped" and again["tool_calls"] == 0


# ---------------------------------------------------------------------- participation


def test_participation_tells_each_role_what_it_can_contribute(client: TestClient) -> None:
    mod = _moderator(client)
    _load(client, mod, "skills_dev01")
    steward = client.get(
        "/api/participation/me", headers=_auth(_join(client, mod, "participant_kit_steward"))
    ).json()
    [kit] = steward["speaks_for"]
    assert kit["resource_id"] == "backup_learning_kit" and kit["check_in"] is False
    assert kit["offer"]["approved_for"] == ["learning_kit"]
    assert kit["offer"]["needed_capabilities"] == {"learning_kit": ["guided_learning"]}
    assert kit["offer"]["terms_ref"] == TERMS
    assert kit["offer"]["registered_window"]["end"] == "2026-11-07T17:00:00Z"
    peer = client.get(
        "/api/participation/me", headers=_auth(_join(client, mod, "participant_peer_lead"))
    ).json()
    assert peer["speaks_for"][0]["check_in"] is True and peer["speaks_for"][0]["offer"] is None
    assert peer["organizer"] is None and peer["staff_tools"] == []
    org = client.get(
        "/api/participation/me", headers=_auth(_join(client, mod, "organizer_demo"))
    ).json()
    assert org["organizer"] == {
        "goal_version": 1,
        "preference_preset": "balanced",
        "presets": ["balanced", "preserve_order", "minimize_spend"],
    }
    assert client.get("/api/participation/me", headers=_auth(mod)).status_code == 403
    _load(client, mod, "pantry_dev01")
    staff = client.get(
        "/api/participation/me", headers=_auth(_join(client, mod, "fictional_staff"))
    ).json()
    assert staff["staff_tools"] == ["record_stock_receipt", "record_distribution"]


def test_offer_and_goal_change_over_http(client: TestClient) -> None:
    mod = _moderator(client)
    _load(client, mod, "skills_dev01")
    client.post("/api/moderator/clock", json={"advance_minutes": 20}, headers=_auth(mod))
    steward = _join(client, mod, "participant_kit_steward")
    body = {
        "tool": "submit_observation",
        "event_id": SKILLS_EVENT,
        "idempotency_key": "web-offer-1",
        "arguments": {
            "text": "The backup kit is here and complete.",
            "entity_id": "backup_learning_kit",
            "kind": "resource_offer",
            "offer": {
                "available": {"start": "2026-11-07T14:40:00Z", "end": "2026-11-07T17:00:00Z"},
                "capabilities": ["guided_learning"],
                "terms_ref": TERMS,
            },
        },
    }
    r = client.post("/api/tools/submit_observation", json=body, headers=_auth(steward))
    assert r.status_code == 200 and r.json()["status"] == "succeeded", r.text
    assert r.json()["data"]["activation"]["status"] == "available"
    state = client.get("/api/state", headers=_auth(steward)).json()
    kit = next(
        x for x in state["resources"] if x["definition"]["resource_id"] == "backup_learning_kit"
    )
    assert kit["status"] == "available" and state["holds"] == []
    assert state["budget"]["reserved_cents"] == 0 and state["budget"]["committed_cents"] == 0
    organizer = _join(client, mod, "organizer_demo")
    goal = client.post(
        "/api/tools/update_goal",
        json={
            "tool": "update_goal",
            "event_id": SKILLS_EVENT,
            "idempotency_key": "web-goal-1",
            "expected_revision": state["revision"],
            "expected_goal_version": 1,
            "arguments": {"preference_preset": "preserve_order", "reason": "keep the order"},
        },
        headers=_auth(organizer),
    )
    assert goal.status_code == 200 and goal.json()["status"] == "succeeded", goal.text
    me = client.get("/api/participation/me", headers=_auth(organizer)).json()
    assert me["organizer"]["goal_version"] == 2


# ---------------------------------------------------------------------- server-side config


def test_api_config_reads_caps_and_builds_policies_without_calling_a_model(
    tmp_path: Path,
) -> None:
    assert load_episode_caps({}) == EpisodeCaps()
    caps = load_episode_caps(
        {"PLAN_B_EPISODE_MAX_TOOL_CALLS": "60", "PLAN_B_EPISODE_MAX_MODEL_CALLS": "4"}
    )
    assert (caps.max_tool_calls, caps.max_model_calls, caps.phase) == (60, 4, "development")
    with pytest.raises(ValueError):
        load_episode_caps({"PLAN_B_EPISODE_MAX_TOOL_CALLS": "many"})
    config = make_config(tmp_path)
    make = factory_for(caps, lambda: config)
    assert make("rules", "pantry_continuity")().policy_id == "pantry-rules/1.0.0"
    assert make("rules", "community_skills_exchange")().policy_id == "rules/1.0.0"
    live = make("live", "campus_showcase")()
    assert isinstance(live, LivePolicy) and live.usage["model_calls"] == 0
    assert (live.max_tool_calls, live.max_model_calls) == (60, 4)
    available = live_availability(lambda: config)
    assert available.available and available.model_id == REQUESTED_MODEL
    assert FAKE_KEY not in str(available.as_dict())

    def missing() -> ModelConfig:
        raise ModelConfigError("PLAN_B_MODEL_KEY_FILE is not configured")

    assert live_availability(missing).as_dict()["live_available"] is False
    with pytest.raises(ModelConfigError):
        factory_for(caps, missing)("live", "campus_showcase")
