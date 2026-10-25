"""The moderator API's model-driven policies without a usable endpoint configuration.

A selection is refused with ``MODEL_NOT_CONFIGURED`` when the configured key file is not present
(as ``live_availability`` reports it; the key is never read), and a restarted server that cannot
rebuild an episode's model-driven policy answers the same described 400, never a 500. Nothing
here calls a model: the model is a scripted transport.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plan_b.agent.config import ModelConfig, ModelConfigError
from plan_b.api.app import create_app
from plan_b.evaluation.policies.base import Policy
from plan_b.scenarios.policy_host import policy_factory_for
from plan_b.store import repo
from plan_b.store.database import Database
from tests.test_agent_provider import make_config
from tests.test_live_workflow import build

CODE = "test-moderator-code"
KINDS = {"tool-use": "P1", "live": "P2", "verify-all": "P3"}


def _client(tmp_path: Path, **kwargs: Any) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        tmp_path / "api.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code=CODE,
        web_dist=tmp_path / "no_dist",
        **kwargs,
    )
    c = TestClient(app, raise_server_exceptions=False)
    token = c.post("/api/auth/moderator", json={"code": CODE}).json()["token"]
    return c, {"Authorization": f"Bearer {token}"}


def _unconfigured() -> ModelConfig:
    raise ModelConfigError("not configured: PLAN_B_MODEL_BASE_URL")


@pytest.mark.parametrize("choice", ["tool-use", "selective", "verify-all"])
def test_a_model_policy_is_not_selectable_without_its_key_file(tmp_path: Path, choice: str) -> None:
    cfg = make_config(tmp_path)
    cfg.key_file.unlink()
    c, auth = _client(tmp_path, live_config_loader=lambda: cfg)
    assert c.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=auth).is_success
    assert c.get("/api/moderator/policy", headers=auth).json()["live_available"] is False
    refused = c.post("/api/moderator/policy", json={"policy": choice}, headers=auth)
    assert refused.status_code == 400
    assert refused.json()["detail"] == {
        "code": "MODEL_NOT_CONFIGURED",
        "message": "the configured key file is not present",
    }
    assert str(tmp_path) not in refused.text
    loaded = c.post(
        "/api/moderator/episodes", json={"case_ref": "dev01", "policy": choice}, headers=auth
    )
    assert loaded.status_code == 400
    # Nothing was locked: the deterministic baseline is still selectable.
    assert c.post("/api/moderator/policy", json={"policy": "rules"}, headers=auth).is_success


@pytest.mark.parametrize("choice", ["tool-use", "live", "verify-all"])
def test_a_restart_without_the_endpoint_configuration_is_a_described_400(
    tmp_path: Path, choice: str
) -> None:
    def factories(name: Any, profile_id: str) -> Callable[[], Policy]:
        if name == "rules":
            return policy_factory_for("rules", profile_id)
        return lambda: build(KINDS[name], tmp_path / "model")[0]

    c, auth = _client(tmp_path, policy_factories=factories)
    assert c.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=auth).is_success
    assert c.post("/api/moderator/policy", json={"policy": choice}, headers=auth).is_success
    assert c.post("/api/moderator/policy/run", json={}, headers=auth).is_success
    # The server restarts on the same database without the endpoint configuration.
    c2, auth2 = _client(tmp_path, live_config_loader=_unconfigured)
    for response in (
        c2.get("/api/policy", headers=auth2),
        c2.get("/api/moderator/policy", headers=auth2),
        c2.post("/api/moderator/policy/run", json={}, headers=auth2),
    ):
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == {
            "code": "MODEL_NOT_CONFIGURED",
            "message": "not configured: PLAN_B_MODEL_BASE_URL",
        }
        assert str(tmp_path) not in response.text
    # Nothing moves before the policy is resolved: the clock stays where it was.
    before = c2.get("/api/moderator/policy", headers=auth2)
    clock = _clock(tmp_path)
    moved = c2.post("/api/moderator/run", json={"minutes": 5, "policy": False}, headers=auth2)
    assert (before.status_code, moved.status_code) == (400, 400)
    assert _clock(tmp_path) == clock


def _clock(tmp_path: Path) -> Any:
    db = Database(tmp_path / "api.sqlite3")
    with db.read() as conn:
        episode_id = repo.current_episode_id(conn)
        assert episode_id is not None
        return repo.get_episode(conn, episode_id).clock
