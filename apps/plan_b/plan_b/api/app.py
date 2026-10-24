"""FastAPI application: sessions, event tools, moderator controls, sanitized replays.

Endpoints are synchronous (FastAPI runs them in a thread pool); every write uses its own
``BEGIN IMMEDIATE`` transaction, so concurrent requests serialize at SQLite.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from plan_b.domain.models import RUNTIME_VERSION, ViewerInfo
from plan_b.evaluation.export_trace import build_trace, write_trace
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import tick_loop
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.engine import advance_by
from plan_b.store.episodes import create_episode
from plan_b.store.projection_db import build_view
from plan_b.store.sessions import (
    AuthError,
    Session,
    check_moderator_code,
    issue_join_code,
    issue_moderator_session,
    redeem_join_code,
    resolve,
)
from plan_b.tools.executor import execute
from plan_b.world.world import available_cases

APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_VAR = APP_DIR / "var"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+\.json$")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodeBody(_Body):
    code: str = Field(min_length=1, max_length=200)


class EpisodeBody(_Body):
    scenario_id: str = "dev_fixture_01"
    case_ref: str


class SessionBody(_Body):
    principal_id: str


class ClockBody(_Body):
    advance_minutes: int = Field(ge=1, le=240)


class PolicyBody(_Body):
    max_tool_calls: int = Field(default=16, ge=1, le=64)


class RunBody(_Body):
    minutes: int = Field(ge=1, le=240)
    policy: bool = True


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def load_moderator_code(var_dir: Path) -> str:
    code = os.environ.get("PLAN_B_MODERATOR_CODE")
    if code:
        return code
    path = var_dir / "moderator_code.txt"
    if path.exists():
        if path.stat().st_mode & 0o077:
            path.chmod(0o600)  # tighten a file left readable by others
        return path.read_text().strip()
    var_dir.mkdir(parents=True, exist_ok=True)
    code = secrets.token_urlsafe(9)
    # Create the file owner-only from the first byte (no window with default permissions).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(code + "\n")
    return code


def create_app(
    db_path: str | Path | None = None,
    *,
    var_dir: str | Path | None = None,
    web_dist: str | Path | None = None,
    moderator_code: str | None = None,
    replay_dirs: list[str | Path] | None = None,
) -> FastAPI:
    var = Path(var_dir) if var_dir else DEFAULT_VAR
    db = Database(db_path or var / "plan_b.sqlite3")
    host = PolicyHost(db)
    code = moderator_code or load_moderator_code(var)
    traces_dir = var / "traces"
    replay_roots = [traces_dir] + [Path(p) for p in (replay_dirs or [])]

    app = FastAPI(title="Plan B: The Show Must Go On (Wave 1 sandbox)", version=RUNTIME_VERSION)
    app.state.db = db
    app.state.host = host

    def session_of(authorization: str | None) -> Session:
        with db.read() as conn:
            try:
                return resolve(conn, _bearer(authorization))
            except AuthError as exc:
                raise HTTPException(
                    status_code=401, detail={"code": exc.code, "message": exc.message}
                ) from exc

    def moderator(authorization: str | None) -> Session:
        s = session_of(authorization)
        if s.role != "moderator":
            raise HTTPException(
                status_code=403, detail={"code": "GRANT_REQUIRED", "message": "moderator only"}
            )
        return s

    def current_episode() -> str:
        with db.read() as conn:
            ep = repo.current_episode_id(conn)
        if ep is None:
            raise HTTPException(
                status_code=409, detail={"code": "NO_EPISODE", "message": "load an episode first"}
            )
        return ep

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "runtime_version": RUNTIME_VERSION, "mode": "deterministic_policy"}

    @app.post("/api/auth/moderator")
    def auth_moderator(body: CodeBody) -> dict[str, Any]:
        if not check_moderator_code(body.code, code):
            raise HTTPException(
                status_code=401,
                detail={"code": "SESSION_INVALID", "message": "wrong moderator code"},
            )
        with db.write() as conn:
            token, s = issue_moderator_session(conn)
        return {
            "token": token,
            "role": s.role,
            "principal_id": s.principal_id,
            "display_name": "Moderator",
        }

    @app.post("/api/auth/join")
    def auth_join(body: CodeBody) -> dict[str, Any]:
        with db.write() as conn:
            try:
                token, s = redeem_join_code(conn, body.code)
            except AuthError as exc:
                raise HTTPException(
                    status_code=401, detail={"code": exc.code, "message": exc.message}
                ) from exc
            assert s.episode_id is not None
            ep = repo.get_episode(conn, s.episode_id)
            p = repo.principal(conn, s.episode_id, s.principal_id)
        return {
            "token": token,
            "role": s.role,
            "principal_id": s.principal_id,
            "display_name": p.display_name,
            "episode_id": s.episode_id,
            "event_id": ep.event_id,
            "grant_id": s.grant_id,
        }

    @app.get("/api/auth/whoami")
    def whoami(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        s = session_of(authorization)
        out: dict[str, Any] = {
            "role": s.role,
            "principal_id": s.principal_id,
            "episode_id": s.episode_id,
            "grant_id": s.grant_id,
        }
        if s.episode_id:
            with db.read() as conn:
                ep = repo.get_episode(conn, s.episode_id)
                p = repo.principal(conn, s.episode_id, s.principal_id)
            out.update(
                {
                    "event_id": ep.event_id,
                    "display_name": p.display_name,
                    "episode_status": ep.status,
                }
            )
        else:
            out["display_name"] = "Moderator"
        return out

    @app.get("/api/state")
    def state(authorization: str | None = Header(default=None)) -> Any:
        s = session_of(authorization)
        if s.role == "moderator":
            episode_id = current_episode()
            viewer = ViewerInfo(
                principal_id="moderator", role="moderator", display_name="Moderator", grant_id=None
            )
            visibility = "audit"
        else:
            assert s.episode_id is not None
            episode_id = s.episode_id
            with db.read() as conn:
                p = repo.principal(conn, episode_id, s.principal_id)
            viewer = ViewerInfo(
                principal_id=s.principal_id,
                role=s.role,  # type: ignore[arg-type]
                display_name=p.display_name,
                grant_id=s.grant_id,
            )
            visibility = "audit" if s.role == "organizer" else "principal"
        with db.read() as conn:
            view = build_view(conn, episode_id, viewer, visibility=visibility)  # type: ignore[arg-type]
        return JSONResponse(view.model_dump(mode="json"))

    @app.post("/api/tools/{tool}")
    async def tool_call(
        tool: str, request: Request, authorization: str | None = Header(default=None)
    ) -> Any:
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"unparsed": True}
        from starlette.concurrency import run_in_threadpool

        status, env = await run_in_threadpool(execute, db, _bearer(authorization), tool, body)
        return JSONResponse(env.model_dump(mode="json"), status_code=status)

    # ------------------------------------------------------------------ moderator

    @app.get("/api/moderator/cases")
    def cases(authorization: str | None = Header(default=None)) -> list[dict[str, str]]:
        moderator(authorization)
        return [{"case_ref": c} for c in available_cases()]

    @app.post("/api/moderator/episodes")
    def load_episode(
        body: EpisodeBody, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        moderator(authorization)
        if body.case_ref not in available_cases():
            raise HTTPException(
                status_code=400, detail={"code": "UNKNOWN_ENTITY", "message": "unknown case"}
            )
        with db.write() as conn:
            closing = [
                row["episode_id"]
                for row in conn.execute("SELECT episode_id FROM episodes WHERE status = 'active'")
            ]
            episode_id = create_episode(conn, scenario_id=body.scenario_id, case_ref=body.case_ref)
            ep = repo.get_episode(conn, episode_id)
        # Drop policy memory only after the reset committed (never while holding the write lock).
        for old in closing:
            host.forget(old)
        return {
            "episode_id": episode_id,
            "event_id": ep.event_id,
            "clock": ep.clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "revision": ep.revision,
        }

    @app.get("/api/moderator/current")
    def current(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        moderator(authorization)
        with db.read() as conn:
            return {"episode_id": repo.current_episode_id(conn)}

    @app.post("/api/moderator/sessions")
    def new_session(
        body: SessionBody, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        moderator(authorization)
        episode_id = current_episode()
        with db.write() as conn:
            try:
                join = issue_join_code(conn, episode_id, body.principal_id)
            except AuthError as exc:
                raise HTTPException(
                    status_code=400, detail={"code": exc.code, "message": exc.message}
                ) from exc
            p = repo.principal(conn, episode_id, body.principal_id)
        return {
            "join_code": join,
            "join_path": f"/#/join/{join}",
            "principal_id": p.principal_id,
            "role": p.role,
            "display_name": p.display_name,
        }

    @app.post("/api/moderator/clock")
    def clock(body: ClockBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        moderator(authorization)
        episode_id = current_episode()
        with db.write() as conn:
            if repo.get_episode(conn, episode_id).status != "active":
                raise HTTPException(
                    status_code=409,
                    detail={"code": "EPISODE_CLOSED", "message": "the episode was just reset"},
                )
            transitions = advance_by(conn, episode_id, body.advance_minutes)
            ep = repo.get_episode(conn, episode_id)
        return {
            "episode_id": episode_id,
            "clock": ep.clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "revision": ep.revision,
            "transitions": [t.model_dump(mode="json") for t in transitions],
        }

    @app.post("/api/moderator/policy/run")
    def policy_run(body: PolicyBody, authorization: str | None = Header(default=None)) -> Any:
        moderator(authorization)
        episode_id = current_episode()
        result = host.run(episode_id, body.max_tool_calls)
        with db.read() as conn:
            status = repo.get_episode(conn, episode_id).status
        # episode_status is "closed" when a reset interrupted the run.
        return JSONResponse(
            {**result.model_dump(mode="json"), "episode_id": episode_id, "episode_status": status}
        )

    @app.post("/api/moderator/run")
    def run(body: RunBody, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        moderator(authorization)
        episode_id = current_episode()
        runs = tick_loop(
            db, host, episode_id, minutes=body.minutes, run_policy=body.policy, actors=None
        )
        with db.read() as conn:
            ep = repo.get_episode(conn, episode_id)
        return {
            "episode_id": episode_id,
            "episode_status": ep.status,  # "closed" when a reset interrupted the run
            "clock": ep.clock.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "revision": ep.revision,
            "policy_runs": [r.model_dump(mode="json") for r in runs],
        }

    @app.post("/api/moderator/export")
    def export(authorization: str | None = Header(default=None)) -> Any:
        moderator(authorization)
        episode_id = current_episode()
        trace = build_trace(db, episode_id, policy_id="rules/1.0.0")
        name = f"{episode_id}_rev{trace['final_state']['revision']}.json"
        write_trace(trace, traces_dir / name)
        return JSONResponse({"name": name, "trace": trace})

    # ------------------------------------------------------------------ replays (public, read-only)

    @app.get("/api/replays")
    def replays() -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for root in replay_roots:
            if root.is_dir():
                out.extend({"name": p.name} for p in sorted(root.glob("*.json")))
        return out

    @app.get("/api/replays/{name}")
    def replay(name: str) -> Any:
        if not SAFE_NAME.match(name):
            raise HTTPException(
                status_code=400, detail={"code": "INVALID_REQUEST", "message": "bad name"}
            )
        for root in replay_roots:
            path = root / name
            if path.is_file():
                return FileResponse(path, media_type="application/json")
        raise HTTPException(
            status_code=404, detail={"code": "UNKNOWN_ENTITY", "message": "no such replay"}
        )

    # ------------------------------------------------------------------ static browser app

    dist = Path(web_dist) if web_dist else APP_DIR / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app
