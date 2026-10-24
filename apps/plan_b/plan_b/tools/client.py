"""In-process ToolClient: the same executor path as HTTP, without a network hop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plan_b.domain.models import ToolEnvelope
from plan_b.evaluation.policies.base import TransportLost
from plan_b.store.database import Database
from plan_b.tools.executor import execute

# Fault injection: given (tool, idempotency_key), return True to drop the response *after*
# the server processed the request (a lost response, not a failed request).
LoseResponse = Callable[[str, str | None], bool]


class InProcessToolClient:
    def __init__(
        self,
        db: Database,
        token: str,
        *,
        principal_id: str,
        event_id: str,
        grant_id: str | None,
        lose_response: LoseResponse | None = None,
    ) -> None:
        self._db = db
        self._token = token
        self.principal_id = principal_id
        self.event_id = event_id
        self.grant_id = grant_id
        self._lose = lose_response
        self.calls: list[ToolEnvelope] = []  # everything this client's caller received

    def call(
        self,
        tool: str,
        *,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        expected_goal_version: int | None = None,
    ) -> ToolEnvelope:
        body: dict[str, Any] = {
            "tool": tool,
            "event_id": self.event_id,
            "grant_id": self.grant_id,
            "arguments": arguments,
        }
        if idempotency_key is not None:
            body["idempotency_key"] = idempotency_key
        if expected_revision is not None:
            body["expected_revision"] = expected_revision
        if expected_goal_version is not None:
            body["expected_goal_version"] = expected_goal_version
        _, env = execute(self._db, self._token, tool, body)
        if self._lose is not None and self._lose(tool, idempotency_key):
            raise TransportLost(tool, idempotency_key)
        self.calls.append(env)
        return env
