"""Server-validated sessions, one-time join codes and the moderator code.

Tokens are random; only their SHA-256 is stored. A session binds one principal, role, grant
and episode. Nothing in a request body can create or change that binding.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from plan_b.store import repo

SESSION_HOURS = 12
JOIN_CODE_MINUTES = 10


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _wall(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Session:
    session_id: str
    episode_id: str | None
    principal_id: str
    role: str
    grant_id: str | None


class AuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def issue_session(
    conn: sqlite3.Connection, episode_id: str, principal_id: str
) -> tuple[str, Session]:
    if repo.get_episode(conn, episode_id).status != "active":
        raise AuthError("EPISODE_CLOSED", "sessions are issued only for an active episode")
    p = repo.principal(conn, episode_id, principal_id)
    if p is None:
        raise AuthError("SESSION_INVALID", f"unknown principal {principal_id}")
    token = secrets.token_urlsafe(32)
    session = Session(
        session_id=f"ses_{secrets.token_hex(8)}",
        episode_id=episode_id,
        principal_id=p.principal_id,
        role=p.role,
        grant_id=p.grant_id,
    )
    now = _now()
    conn.execute(
        "INSERT INTO sessions (token_sha256, session_id, episode_id, principal_id, role, grant_id,"
        " created_wall, expires_wall) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _sha(token),
            session.session_id,
            episode_id,
            session.principal_id,
            session.role,
            session.grant_id,
            _wall(now),
            _wall(now + timedelta(hours=SESSION_HOURS)),
        ),
    )
    return token, session


def issue_moderator_session(conn: sqlite3.Connection) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    session = Session(
        session_id=f"ses_{secrets.token_hex(8)}",
        episode_id=None,
        principal_id="moderator",
        role="moderator",
        grant_id=None,
    )
    now = _now()
    conn.execute(
        "INSERT INTO sessions (token_sha256, session_id, episode_id, principal_id, role, grant_id,"
        " created_wall, expires_wall) VALUES (?, ?, NULL, 'moderator', 'moderator', NULL, ?, ?)",
        (_sha(token), session.session_id, _wall(now), _wall(now + timedelta(hours=SESSION_HOURS))),
    )
    return token, session


def resolve(conn: sqlite3.Connection, token: str | None) -> Session:
    if not token:
        raise AuthError("AUTH_REQUIRED", "a session token is required")
    return _resolve_row(conn, _sha(token))


def _resolve_row(conn: sqlite3.Connection, token_sha256: str) -> Session:
    row = conn.execute("SELECT * FROM sessions WHERE token_sha256 = ?", (token_sha256,)).fetchone()
    if row is None:
        raise AuthError("SESSION_INVALID", "session is unknown or revoked")
    if row["revoked"]:
        if row["episode_id"] is not None:
            ep = conn.execute(
                "SELECT status FROM episodes WHERE episode_id = ?", (row["episode_id"],)
            ).fetchone()
            if ep is not None and ep["status"] == "closed":
                raise AuthError("EPISODE_CLOSED", "this episode was reset; ask for a new link")
        raise AuthError("SESSION_INVALID", "session is unknown or revoked")
    if row["expires_wall"] <= _wall(_now()):
        raise AuthError("SESSION_INVALID", "session expired")
    return Session(
        session_id=row["session_id"],
        episode_id=row["episode_id"],
        principal_id=row["principal_id"],
        role=row["role"],
        grant_id=row["grant_id"],
    )


def resolve_session_id(conn: sqlite3.Connection, session_id: str) -> Session:
    """Resolve a server-held session by id, with the same validity rules as a token."""
    row = conn.execute(
        "SELECT token_sha256 FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise AuthError("SESSION_INVALID", "session is unknown or revoked")
    return _resolve_row(conn, row["token_sha256"])


def revoke_episode_sessions(conn: sqlite3.Connection, episode_id: str) -> None:
    conn.execute("UPDATE sessions SET revoked = 1 WHERE episode_id = ?", (episode_id,))
    conn.execute("UPDATE join_codes SET used = 1 WHERE episode_id = ?", (episode_id,))


def issue_join_code(conn: sqlite3.Connection, episode_id: str, principal_id: str) -> str:
    p = repo.principal(conn, episode_id, principal_id)
    if p is None:
        raise AuthError("SESSION_INVALID", f"unknown principal {principal_id}")
    if p.role == "coordinator_agent":
        raise AuthError("SESSION_INVALID", "the coordinator agent session stays on the server")
    code = secrets.token_urlsafe(12)
    now = _now()
    conn.execute(
        "INSERT INTO join_codes (code_sha256, episode_id, principal_id, created_wall,"
        " expires_wall) VALUES (?, ?, ?, ?, ?)",
        (
            _sha(code),
            episode_id,
            principal_id,
            _wall(now),
            _wall(now + timedelta(minutes=JOIN_CODE_MINUTES)),
        ),
    )
    return code


def redeem_join_code(conn: sqlite3.Connection, code: str) -> tuple[str, Session]:
    row = conn.execute("SELECT * FROM join_codes WHERE code_sha256 = ?", (_sha(code),)).fetchone()
    if row is not None and repo.get_episode(conn, row["episode_id"]).status != "active":
        raise AuthError("EPISODE_CLOSED", "that episode has been reset; ask for a new link")
    if row is None or row["used"] or row["expires_wall"] <= _wall(_now()):
        raise AuthError("SESSION_INVALID", "join code is unknown, used or expired")
    conn.execute("UPDATE join_codes SET used = 1 WHERE code_sha256 = ?", (_sha(code),))
    return issue_session(conn, row["episode_id"], row["principal_id"])


def check_moderator_code(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
