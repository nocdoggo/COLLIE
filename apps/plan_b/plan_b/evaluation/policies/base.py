"""Policy/tool boundary shared by the deterministic policy now and live policies later.

A policy receives only a ``ToolClient``. It cannot reach the store, the private world, the
runner or another actor's session. Every effect it has goes through the same executor as an
HTTP caller.
"""

from __future__ import annotations

from typing import Any, Protocol

from plan_b.domain.models import PolicyRunResult, ToolEnvelope


class TransportLost(Exception):  # noqa: N818 - the name states the event, not an error class
    """The response to a call was lost; the request may or may not have executed.

    Raised by a ``ToolClient`` after the server processed the request but before the caller
    saw the envelope (tests inject this). The caller must reconcile with
    ``get_action_receipt`` and the original idempotency key, never with a fresh key."""

    def __init__(self, tool: str, idempotency_key: str | None) -> None:
        super().__init__(f"response lost for {tool} (key {idempotency_key})")
        self.tool = tool
        self.idempotency_key = idempotency_key


class ToolClient(Protocol):
    principal_id: str

    def call(
        self,
        tool: str,
        *,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        expected_goal_version: int | None = None,
    ) -> ToolEnvelope:
        """Call one tool as this client's principal. ``event_id`` and ``grant_id`` are
        filled from the client's session binding."""
        ...


class Policy(Protocol):
    policy_id: str

    def run(self, client: ToolClient, max_tool_calls: int = 16) -> PolicyRunResult:
        """One bounded decision loop. Must stop or wait; never loops unboundedly."""
        ...
