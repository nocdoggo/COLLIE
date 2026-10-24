"""The single tool executor used by HTTP callers and in-process policies alike.

Order inside one ``BEGIN IMMEDIATE`` transaction (docs/RUNTIME_CONTRACT.md section 5):
session -> episode/event -> grant and tool authorization -> request validation ->
idempotency (identical: original receipt; different body: conflict) -> static prechecks ->
modeled tool duration (clock advance with event processing) -> grant validity at the new
time -> handler validation and effects -> receipt + idempotency record -> snapshot -> call log.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from plan_b.domain.digest import request_digest
from plan_b.domain.models import (
    CONTROL_TOOLS,
    MUTATION_TOOLS,
    RUNTIME_VERSION,
    TOOL_ARGUMENT_MODELS,
    TOOL_REQUIREMENTS,
    ActionReceipt,
    AuthorityGrant,
    EnvelopeStatus,
    PublicScenario,
    StateChange,
    Strict,
    ToolEnvelope,
    ToolError,
    ToolRequest,
)
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.engine import advance_by, refresh_ready
from plan_b.store.projection_db import capture_snapshot
from plan_b.store.sessions import AuthError, Session, resolve, resolve_session_id

log = logging.getLogger("plan_b.executor")

RECEIPT_TOOLS = set(MUTATION_TOOLS) | set(CONTROL_TOOLS)
QUIET_READS = {"get_event_state", "get_action_receipt", "list_resources"}


class Rejection(Exception):  # noqa: N818 - a domain outcome, not a crash
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        envelope_status: EnvelopeStatus = "rejected",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.envelope_status = envelope_status
        self.data = data


@dataclass
class Outcome:
    data: dict[str, Any] | None
    summary: str = ""
    state_changes: list[StateChange] = field(default_factory=list)
    committed_delta: int = 0
    reserved_delta: int = 0
    related_plan_id: str | None = None
    constraint_report_ref: str | None = None


@dataclass
class Ctx:
    conn: sqlite3.Connection
    episode_id: str
    event_id: str
    scenario: PublicScenario
    session: Session
    grant: AuthorityGrant
    grant_version: int
    request: ToolRequest
    args: Any
    requested_at: datetime
    now: datetime
    receipt_id: str | None
    call_id: str

    @property
    def actor_id(self) -> str:
        return self.session.principal_id


def _envelope(
    *,
    call_id: str,
    tool: str,
    status: EnvelopeStatus,
    conn: sqlite3.Connection | None = None,
    episode_id: str | None = None,
    data: dict[str, Any] | None = None,
    error: ToolError | None = None,
    receipt: ActionReceipt | None = None,
    replayed: bool = False,
) -> ToolEnvelope:
    revision = goal_version = None
    clock = None
    event_id = None
    if conn is not None and episode_id is not None:
        ep = repo.get_episode(conn, episode_id)
        revision, goal_version, clock, event_id = (
            ep.revision,
            ep.goal_version,
            ep.clock,
            ep.event_id,
        )
    return ToolEnvelope(
        runtime_version=RUNTIME_VERSION,
        call_id=call_id,
        tool=tool,
        status=status,
        episode_id=episode_id,
        event_id=event_id,
        revision=revision,
        goal_version=goal_version,
        scenario_time=clock,
        data=data,
        error=error,
        receipt=receipt,
        replayed_receipt=replayed,
    )


def _log_call(
    conn: sqlite3.Connection,
    episode_id: str,
    seq: int,
    call_id: str,
    session: Session,
    tool: str,
    body: Any,
    requested_at: datetime | None,
    revision_before: int | None,
    env: ToolEnvelope,
) -> None:
    conn.execute(
        "INSERT INTO tool_calls (episode_id, seq, call_id, actor_id, actor_role, tool,"
        " requested_at, completed_at, revision_before, revision_after, envelope_status,"
        " error_code, receipt_id, request_json, envelope_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            episode_id,
            seq,
            call_id,
            session.principal_id,
            session.role,
            tool,
            requested_at.strftime("%Y-%m-%dT%H:%M:%SZ") if requested_at else None,
            env.scenario_time.strftime("%Y-%m-%dT%H:%M:%SZ") if env.scenario_time else None,
            revision_before,
            env.revision,
            env.status,
            env.error.code if env.error else None,
            env.receipt.receipt_id if env.receipt else None,
            repo.dumps(body),
            env.model_dump_json(),
        ),
    )


def _body_summary(body: Any) -> dict[str, Any]:
    """What is logged for a body that has not passed validation: field names only, never values
    (a client could put a secret in an unknown field)."""
    if isinstance(body, dict):
        return {"unvalidated": True, "fields": sorted(str(k)[:64] for k in body)[:32]}
    return {"unvalidated": True, "fields": []}


def execute(db: Database, token: str | None, tool: str, body: Any) -> tuple[int, ToolEnvelope]:
    """Run one tool call in its own BEGIN IMMEDIATE transaction. Returns (http_status, envelope)."""
    with db.write() as conn:
        return execute_in(conn, tool, body, token=token)


def execute_in(
    conn: sqlite3.Connection,
    tool: str,
    body: Any,
    *,
    token: str | None = None,
    session_id: str | None = None,
    fill_expected_revision: bool = False,
) -> tuple[int, ToolEnvelope]:
    """The executor body for an already-open write transaction.

    HTTP and in-process callers come through ``execute`` with their bearer token. The engine
    uses ``session_id`` to run a scheduled exogenous actor action at its exact scenario instant
    (the actor's own server-held session; raw tokens are never stored). With
    ``fill_expected_revision`` the action is validated against the state at that instant, as if
    the actor had read it immediately before acting."""
    try:
        session = (
            resolve(conn, token) if session_id is None else resolve_session_id(conn, session_id)
        )
    except AuthError as exc:
        return 401, _envelope(
            call_id="call_unauthenticated",
            tool=tool,
            status="rejected",
            error=ToolError(code=exc.code, message=exc.message),  # type: ignore[arg-type]
        )
    if session.role == "moderator" or session.episode_id is None:
        return 403, _envelope(
            call_id="call_moderator",
            tool=tool,
            status="rejected",
            error=ToolError(
                code="GRANT_REQUIRED",
                message="moderator sessions control the sandbox and cannot call event tools",
            ),
        )
    episode_id = session.episode_id
    if fill_expected_revision and isinstance(body, dict):
        body = {**body, "expected_revision": repo.get_episode(conn, episode_id).revision}
    seq = repo.next_seq(conn, episode_id, "tool_call")
    call_id = f"call_{seq:05d}"
    savepoint = f"tool_call_{seq}"
    logged: dict[str, Any] = {"body": _body_summary(body)}

    def finish(
        env: ToolEnvelope,
        http: int = 200,
        requested_at: datetime | None = None,
        revision_before: int | None = None,
        *,
        snapshot: bool = True,
    ) -> tuple[int, ToolEnvelope]:
        _log_call(
            conn,
            episode_id,
            seq,
            call_id,
            session,
            tool,
            logged["body"],
            requested_at,
            revision_before,
            env,
        )
        if snapshot and (tool not in QUIET_READS or env.status != "succeeded"):
            # Status checks, evaluations, receipts and attempts are visible facts even when
            # the revision did not change: refresh this revision's replay snapshot.
            capture_snapshot(conn, episode_id)
        return http, env

    def reject_early(
        code: str,
        message: str,
        http: int = 200,
        details: dict[str, Any] | None = None,
        *,
        snapshot: bool = True,
    ) -> tuple[int, ToolEnvelope]:
        env = _envelope(
            call_id=call_id,
            tool=tool,
            status="rejected",
            conn=conn,
            episode_id=episode_id,
            error=ToolError(code=code, message=message, details=details or {}),  # type: ignore[arg-type]
        )
        return finish(env, http, snapshot=snapshot)

    # Everything after the call id is allocated runs inside a savepoint: an unexpected
    # error rolls back whatever the call did and is recorded as an INTERNAL_ERROR attempt,
    # so the caller gets an envelope and the evidence survives.
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        result = _run_call(conn, session, tool, body, call_id, logged, finish, reject_early)
    except Exception as exc:  # noqa: BLE001 - converted into an explicit envelope
        conn.execute(f"ROLLBACK TO {savepoint}")
        conn.execute(f"RELEASE {savepoint}")
        log.exception("tool call %s (%s) failed", call_id, tool)
        return reject_early(
            "INTERNAL_ERROR",
            "the request failed inside the server; none of its effects were kept",
            500,
            {"exception": type(exc).__name__},
            snapshot=False,
        )
    conn.execute(f"RELEASE {savepoint}")
    return result


@contextmanager
def _savepoint(conn: sqlite3.Connection, name: str) -> Iterator[None]:
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        conn.execute(f"ROLLBACK TO {name}")
        conn.execute(f"RELEASE {name}")
        raise
    conn.execute(f"RELEASE {name}")


Finish = Callable[..., tuple[int, ToolEnvelope]]


def _run_call(
    conn: sqlite3.Connection,
    session: Session,
    tool: str,
    body: Any,
    call_id: str,
    logged: dict[str, Any],
    finish: Finish,
    reject_early: Finish,
) -> tuple[int, ToolEnvelope]:
    assert session.episode_id is not None
    episode_id = session.episode_id
    ep = repo.get_episode(conn, episode_id)
    if ep.status != "active":
        return reject_early("EPISODE_CLOSED", "this episode has been reset", 401)
    try:
        request = ToolRequest.model_validate(body)
    except ValidationError as exc:
        return reject_early(
            "INVALID_REQUEST",
            "request body failed validation",
            400,
            {"errors": _validation_errors(exc)},
        )
    logged["body"] = {
        **request.model_dump(mode="json"),
        "arguments": _body_summary(request.arguments),
    }
    if request.tool != tool:
        return reject_early("INVALID_REQUEST", "body tool does not match the endpoint", 400)
    if tool not in TOOL_ARGUMENT_MODELS:
        return reject_early("UNKNOWN_TOOL", f"unknown tool {tool!r}")
    if request.event_id != ep.event_id:
        return reject_early(
            "EVENT_MISMATCH",
            "this session is scoped to a different event",
            details={"session_event_id": ep.event_id},
        )
    if session.grant_id is None:
        return reject_early("GRANT_REQUIRED", "this session has no grant")
    if request.grant_id is not None and request.grant_id != session.grant_id:
        return reject_early(
            "GRANT_MISMATCH",
            "grant_id does not belong to this session; a grant id is not authentication",
        )
    found = repo.current_grant(conn, episode_id, session.grant_id)
    if found is None:
        return reject_early("GRANT_REQUIRED", "the session's grant does not exist")
    grant, grant_version, _ = found
    if tool not in grant.allowed_tools:
        return reject_early(
            "GRANT_REQUIRED",
            f"grant {grant.grant_id} does not allow {tool}",
            details={"allowed_tools": list(grant.allowed_tools)},
        )
    try:
        args = TOOL_ARGUMENT_MODELS[tool].model_validate(request.arguments)
    except ValidationError as exc:
        return reject_early(
            "INVALID_REQUEST",
            "arguments failed validation",
            400,
            {"errors": _validation_errors(exc)},
        )
    logged["body"] = {**request.model_dump(mode="json"), "arguments": args.model_dump(mode="json")}
    for name, need in TOOL_REQUIREMENTS[tool].items():
        if need == "required" and getattr(request, name) is None:
            return reject_early("INVALID_REQUEST", f"{tool} requires {name}", 400)

    is_receipt_tool = tool in RECEIPT_TOOLS
    digest = request_digest(request.model_dump(mode="json")) if is_receipt_tool else None
    if is_receipt_tool:
        assert request.idempotency_key is not None
        prior = conn.execute(
            "SELECT request_digest, receipt_id FROM idempotency WHERE episode_id = ?"
            " AND actor_id = ? AND idempotency_key = ?",
            (episode_id, session.principal_id, request.idempotency_key),
        ).fetchone()
        if prior is not None:
            if prior["request_digest"] == digest:
                original = repo.receipt(conn, episode_id, prior["receipt_id"])
                assert original is not None
                env = _envelope(
                    call_id=call_id,
                    tool=tool,
                    status="succeeded" if original.status == "applied" else "rejected",
                    conn=conn,
                    episode_id=episode_id,
                    data={"replayed": True},
                    error=None
                    if original.status == "applied"
                    else ToolError(
                        code=original.error_code or "INVALID_REQUEST",
                        message=original.error_message or "original request was rejected",
                    ),
                    receipt=original,
                    replayed=True,
                )
                return finish(env)
            return reject_early(
                "IDEMPOTENCY_CONFLICT",
                "this idempotency key was already used for a different request",
                details={"original_receipt_id": prior["receipt_id"]},
            )

    from plan_b.tools import handlers

    requested_at = ep.clock
    ctx = Ctx(
        conn=conn,
        episode_id=episode_id,
        event_id=ep.event_id,
        scenario=repo.scenario(conn, episode_id),
        session=session,
        grant=grant,
        grant_version=grant_version,
        request=request,
        args=args,
        requested_at=requested_at,
        now=requested_at,
        receipt_id=None,
        call_id=call_id,
    )
    try:
        handlers.precheck(ctx, tool)
    except Rejection as rej:
        # Static prechecks are about the request itself; nothing executes, no time passes.
        return reject_early(rej.code, rej.message, details=rej.details)

    # Looking up one's own receipts stays possible after revocation or expiry, so a caller can
    # always reconcile a lost response. Reading another actor's receipts needs a valid grant.
    own_lookup = tool == "get_action_receipt" and getattr(args, "actor_id", None) in (
        None,
        session.principal_id,
    )

    def reject(rej: Rejection, revision_before: int) -> tuple[int, ToolEnvelope]:
        if not is_receipt_tool:
            env = _envelope(
                call_id=call_id,
                tool=tool,
                status=rej.envelope_status,
                conn=conn,
                episode_id=episode_id,
                data=rej.data,
                error=ToolError(code=rej.code, message=rej.message, details=rej.details),  # type: ignore[arg-type]
            )
            return finish(env, 200, requested_at, revision_before)
        if ctx.receipt_id is None:
            ctx.receipt_id = f"rcpt_{repo.next_seq(conn, episode_id, 'receipt'):04d}"
        receipt = _store_receipt(
            ctx,
            tool=tool,
            digest=digest,
            status="rejected",
            revision_before=revision_before,
            outcome=Outcome(data=None, summary=f"Rejected: {rej.message}"),
            error_code=rej.code,
            error_message=rej.message,
        )
        env = _envelope(
            call_id=call_id,
            tool=tool,
            status="rejected",
            conn=conn,
            episode_id=episode_id,
            error=ToolError(code=rej.code, message=rej.message, details=rej.details),  # type: ignore[arg-type]
            receipt=receipt,
        )
        return finish(env, 200, requested_at, revision_before)

    def grant_problem(at: datetime) -> Rejection | None:
        current = repo.current_grant(conn, episode_id, grant.grant_id)
        if current is None:
            return Rejection("GRANT_REQUIRED", f"grant {grant.grant_id} no longer exists")
        g, version, is_revoked = current
        ctx.grant, ctx.grant_version = g, version
        if own_lookup:
            return None
        if is_revoked:
            return Rejection("GRANT_REVOKED", f"grant {g.grant_id} was revoked")
        if not at < g.expires_at:
            return Rejection(
                "GRANT_EXPIRED",
                f"grant {g.grant_id} expired",
                {"expires_at": g.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")},
            )
        return None

    # Authority known at arrival is checked before any modeled time passes: a revoked or
    # expired grant cannot move the shared scenario clock.
    problem = grant_problem(requested_at)
    if problem is not None:
        return reject(problem, ep.revision)

    minutes = ctx.scenario.tool_durations_minutes.get(tool, 0)
    if minutes:
        advance_by(conn, episode_id, minutes)
    ep_now = repo.get_episode(conn, episode_id)
    ctx.now = ep_now.clock
    revision_before = ep_now.revision
    if is_receipt_tool:
        ctx.receipt_id = f"rcpt_{repo.next_seq(conn, episode_id, 'receipt'):04d}"

    try:
        # The grant can expire, or a scheduled organizer action can revoke it, during the
        # modeled duration: check again at execution time.
        problem = grant_problem(ctx.now)
        if problem is not None:
            raise problem
        outcome = handlers.handle(ctx, tool)
    except Rejection as rej:
        return reject(rej, revision_before)

    changed = repo.get_episode(conn, episode_id).revision != revision_before
    applied: ActionReceipt | None = None
    if is_receipt_tool:
        applied = _store_receipt(
            ctx,
            tool=tool,
            digest=digest,
            status="applied",
            revision_before=revision_before,
            outcome=outcome,
            error_code=None,
            error_message=None,
        )
    if changed:
        refresh_ready(conn, episode_id)
        capture_snapshot(conn, episode_id)
    env = _envelope(
        call_id=call_id,
        tool=tool,
        status="succeeded",
        conn=conn,
        episode_id=episode_id,
        data=outcome.data,
        receipt=applied,
    )
    return finish(env, 200, requested_at, revision_before)


def _store_receipt(
    ctx: Ctx,
    *,
    tool: str,
    digest: str | None,
    status: str,
    revision_before: int,
    outcome: Outcome,
    error_code: str | None,
    error_message: str | None,
) -> ActionReceipt:
    assert ctx.receipt_id is not None and digest is not None
    assert ctx.request.idempotency_key is not None
    ep = repo.get_episode(ctx.conn, ctx.episode_id)
    receipt = ActionReceipt(
        runtime_version=RUNTIME_VERSION,
        receipt_id=ctx.receipt_id,
        episode_id=ctx.episode_id,
        event_id=ctx.event_id,
        tool=tool,
        request_idempotency_key=ctx.request.idempotency_key,
        request_digest=digest,
        grant_id=ctx.grant.grant_id,
        grant_version=ctx.grant_version,
        actor_id=ctx.actor_id,
        actor_role=ctx.session.role,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        revision_before=revision_before,
        revision_after=ep.revision if status == "applied" else revision_before,
        requested_at=ctx.requested_at,
        executed_at=ctx.now,
        simulation=True,
        state_changes=tuple(outcome.state_changes) if status == "applied" else (),
        committed_delta_cents=outcome.committed_delta if status == "applied" else 0,
        reserved_delta_cents=outcome.reserved_delta if status == "applied" else 0,
        related_plan_id=outcome.related_plan_id,
        constraint_report_ref=outcome.constraint_report_ref,
        error_code=error_code,  # type: ignore[arg-type]
        error_message=error_message,
        summary=outcome.summary,
    )
    ctx.conn.execute(
        "INSERT INTO receipts (episode_id, receipt_id, actor_id, tool, idempotency_key, status,"
        " revision_before, revision_after, executed_at, body_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ctx.episode_id,
            receipt.receipt_id,
            receipt.actor_id,
            tool,
            receipt.request_idempotency_key,
            receipt.status,
            receipt.revision_before,
            receipt.revision_after,
            receipt.executed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            receipt.model_dump_json(),
        ),
    )
    ctx.conn.execute(
        "INSERT INTO idempotency (episode_id, actor_id, idempotency_key, tool, request_digest,"
        " receipt_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ctx.episode_id,
            ctx.actor_id,
            receipt.request_idempotency_key,
            tool,
            digest,
            receipt.receipt_id,
            receipt.executed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )
    return receipt


def _validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", ""), "type": e.get("type")}
        for e in exc.errors()
    ]


__all__ = ["Ctx", "Outcome", "Rejection", "Strict", "execute"]
