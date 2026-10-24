"""HTTP surface: sessions, role scoping, moderator controls, replay endpoints, payload leaks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plan_b.api.app import create_app
from plan_b.domain.models import ObservationRecord
from plan_b.domain.timeutil import parse_ts
from plan_b.world.leakcheck import find_leaks
from plan_b.world.world import load_case

CODE = "test-moderator-code"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        tmp_path / "api.sqlite3",
        var_dir=tmp_path / "var",
        moderator_code=CODE,
        web_dist=tmp_path / "no_dist",
    )
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _moderator(c: TestClient) -> str:
    r = c.post("/api/auth/moderator", json={"code": CODE})
    assert r.status_code == 200
    return str(r.json()["token"])


def _join(c: TestClient, mod: str, principal: str) -> dict[str, Any]:
    r = c.post("/api/moderator/sessions", json={"principal_id": principal}, headers=_auth(mod))
    assert r.status_code == 200, r.text
    code = r.json()["join_code"]
    j = c.post("/api/auth/join", json={"code": code})
    assert j.status_code == 200, j.text
    return {**j.json(), "code": code}


def _tool(c: TestClient, token: str, tool: str, **body: Any) -> Any:
    payload = {"tool": tool, "event_id": "e_showcase_01", "arguments": {}, **body}
    return c.post(f"/api/tools/{tool}", json=payload, headers=_auth(token))


def test_health_and_moderator_auth(client: TestClient) -> None:
    assert client.get("/api/health").json()["runtime_version"] == "1.1.0"
    assert client.post("/api/auth/moderator", json={"code": "wrong"}).status_code == 401
    mod = _moderator(client)
    assert client.get("/api/auth/whoami", headers=_auth(mod)).json()["role"] == "moderator"


def test_moderator_cannot_call_event_tools(client: TestClient) -> None:
    mod = _moderator(client)
    client.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    r = _tool(client, mod, "get_event_state")
    assert r.status_code == 403 and r.json()["error"]["code"] == "GRANT_REQUIRED"


def test_tools_require_a_session_and_valid_body(client: TestClient) -> None:
    r = client.post(
        "/api/tools/get_event_state", json={"tool": "get_event_state", "event_id": "e_showcase_01"}
    )
    assert r.status_code == 401 and r.json()["status"] == "rejected"
    mod = _moderator(client)
    client.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    fac = _join(client, mod, "participant_facilitator")
    r = client.post("/api/tools/check_in", json={"tool": "check_in"}, headers=_auth(fac["token"]))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_join_codes_are_one_time_and_coordinator_stays_on_server(client: TestClient) -> None:
    mod = _moderator(client)
    client.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    fac = _join(client, mod, "participant_facilitator")
    assert fac["role"] == "participant" and fac["grant_id"] == "grant_facilitator_self"
    assert client.post("/api/auth/join", json={"code": fac["code"]}).status_code == 401
    r = client.post(
        "/api/moderator/sessions", json={"principal_id": "agent_demo"}, headers=_auth(mod)
    )
    assert r.status_code == 400
    assert (
        client.post("/api/moderator/sessions", json={"principal_id": "agent_demo"}).status_code
        == 401
    )


def test_participant_flow_and_role_scoped_state(client: TestClient) -> None:
    mod = _moderator(client)
    client.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    fac = _join(client, mod, "participant_facilitator")
    pres = _join(client, mod, "participant_presenter")
    r = _tool(
        client,
        fac["token"],
        "check_in",
        idempotency_key="ui-1",
        arguments={"resource_id": "facilitator"},
    )
    assert r.status_code == 200 and r.json()["receipt"]["status"] == "applied"
    # A second session sees the persisted change through a fresh read.
    state = client.get("/api/state", headers=_auth(pres["token"])).json()
    assert any(
        c["resource_id"] == "facilitator" and c["channel"] == "participant_session"
        for c in state["checkins"]
    )
    assert state["receipts"] == []  # the presenter sees only its own receipts
    assert [g["grant"]["grant_id"] for g in state["grants"]] == ["grant_presenter_self"]
    audit = client.get("/api/state", headers=_auth(mod)).json()
    assert len(audit["receipts"]) == 1 and len(audit["grants"]) == 5
    forged = _tool(
        client,
        pres["token"],
        "check_in",
        idempotency_key="ui-2",
        arguments={"resource_id": "facilitator"},
    )
    assert forged.json()["receipt"]["error_code"] == "SCOPE_VIOLATION"


def test_clock_and_reset_isolate_episodes(client: TestClient) -> None:
    mod = _moderator(client)
    first = client.post(
        "/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod)
    ).json()
    fac = _join(client, mod, "participant_facilitator")
    _tool(
        client,
        fac["token"],
        "check_in",
        idempotency_key="same-key",
        arguments={"resource_id": "facilitator"},
    )
    adv = client.post(
        "/api/moderator/clock", json={"advance_minutes": 15}, headers=_auth(mod)
    ).json()
    assert adv["clock"] == "2026-11-05T21:55:00Z"
    assert any(t["cause_kind"] == "activity_completed" for t in adv["transitions"])
    second = client.post(
        "/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod)
    ).json()
    assert second["episode_id"] != first["episode_id"]
    assert second["revision"] == 3 and second["clock"] == "2026-11-05T21:40:00Z"
    stale = client.get("/api/state", headers=_auth(fac["token"]))
    assert stale.status_code == 401  # the old episode's session is revoked
    fac2 = _join(client, mod, "participant_facilitator")
    again = _tool(
        client,
        fac2["token"],
        "check_in",
        idempotency_key="same-key",
        arguments={"resource_id": "facilitator"},
    )
    body = again.json()
    assert body["receipt"]["status"] == "applied" and not body["replayed_receipt"]
    state = client.get("/api/state", headers=_auth(mod)).json()
    assert state["episode_id"] == second["episode_id"] and len(state["receipts"]) == 1
    assert state["holds"] == [] and state["decisions"] == [] and state["latest_evaluation"] is None


def test_replay_endpoints_are_read_only_and_path_safe(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/replays").json() == []
    assert client.get("/api/replays/..%2Fapi.sqlite3").status_code in (400, 404)
    assert client.get("/api/replays/missing.json").status_code == 404
    assert client.post("/api/replays/x.json").status_code == 405


def test_http_payloads_carry_no_private_case_data(client: TestClient) -> None:
    mod = _moderator(client)
    client.post("/api/moderator/episodes", json={"case_ref": "dev01"}, headers=_auth(mod))
    org = _join(client, mod, "organizer_demo")
    cases = client.get("/api/moderator/cases", headers=_auth(mod)).json()
    assert all(set(c) == {"case_ref", "scenario_id", "profile_id"} for c in cases)
    texts: list[tuple[str, str]] = []
    for minutes in (0, 10, 20, 30, 40):
        if minutes:
            client.post("/api/moderator/clock", json={"advance_minutes": 10}, headers=_auth(mod))
        for token in (mod, org["token"]):
            r = client.get("/api/state", headers=_auth(token))
            texts.append((r.json()["clock"], r.text))
        r = _tool(client, org["token"], "evaluate_candidates")
        texts.append((r.json()["scenario_time"], r.text))
    case = load_case("dev01")
    final = client.get("/api/state", headers=_auth(mod)).json()
    observations = [ObservationRecord.model_validate(o) for o in final["observations"]]
    for clock, text in texts:
        assert find_leaks(text, case, observations, parse_ts(clock)) == [], clock
