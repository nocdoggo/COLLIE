"""Hosts one policy instance per episode and runs it through the common executor.

The coordinator session is created here, on the server, and never leaves the process. Policy
decisions are stored as narration (they never change operational state). Reset creates a new
episode, so the next run gets a fresh policy instance and no memory carries over.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from plan_b.domain.models import PolicyDecision, PolicyRunResult
from plan_b.evaluation.policies.base import Policy
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.projection_db import capture_snapshot
from plan_b.store.sessions import AuthError, issue_session
from plan_b.tools.client import InProcessToolClient, LoseResponse

COORDINATOR_ROLE = "coordinator_agent"


def default_policy_factory() -> Policy:
    from plan_b.evaluation.policies.rules import RulePolicy

    return RulePolicy()


class PolicyHost:
    def __init__(
        self,
        db: Database,
        policy_factory: Callable[[], Policy] = default_policy_factory,
    ) -> None:
        self._db = db
        self._factory = policy_factory
        self._policies: dict[str, Policy] = {}
        self._clients: dict[str, InProcessToolClient] = {}
        self._lock = Lock()

    def policy(self, episode_id: str) -> Policy:
        with self._lock:
            if episode_id not in self._policies:
                self._policies[episode_id] = self._factory()
            return self._policies[episode_id]

    def client(
        self, episode_id: str, *, lose_response: LoseResponse | None = None
    ) -> InProcessToolClient:
        # Never hold self._lock while waiting for the SQLite write lock (a reset holds the write
        # lock and then calls forget()): issue the session first, then cache it under the lock.
        if lose_response is None:
            with self._lock:
                cached = self._clients.get(episode_id)
            if cached is not None:
                return cached
        with self._db.write() as conn:
            ep = repo.get_episode(conn, episode_id)
            sc = repo.scenario(conn, episode_id)
            agent = next(p for p in sc.principals if p.role == COORDINATOR_ROLE)
            token, session = issue_session(conn, episode_id, agent.principal_id)
        client = InProcessToolClient(
            self._db,
            token,
            principal_id=session.principal_id,
            event_id=ep.event_id,
            grant_id=session.grant_id,
            lose_response=lose_response,
        )
        if lose_response is None:
            with self._lock:
                client = self._clients.setdefault(episode_id, client)
        return client

    def run(self, episode_id: str, max_tool_calls: int = 16) -> PolicyRunResult:
        policy = self.policy(episode_id)
        try:
            client = self.client(episode_id)
        except AuthError as exc:
            # The episode was reset before the coordinator session could be issued.
            return PolicyRunResult(
                policy_id=getattr(policy, "policy_id", "unknown"),
                status="stopped",
                decisions=(),
                tool_calls=0,
                note=f"not run: {exc.message}",
            )
        result = policy.run(client, max_tool_calls)
        stored = self.record(episode_id, result)
        return result.model_copy(update={"decisions": stored})

    def record(self, episode_id: str, result: PolicyRunResult) -> tuple[PolicyDecision, ...]:
        """Store the run's decisions under store-assigned ids and return the stored copies.
        Nothing is written into an episode that was reset during the run."""
        if not result.decisions:
            return ()
        with self._db.write() as conn:
            if repo.get_episode(conn, episode_id).status != "active":
                return ()
            stored = tuple(repo.insert_decision(conn, episode_id, d) for d in result.decisions)
            # Decisions are narration, not state: no revision change, but the snapshot of the
            # current revision is refreshed so replay frames show them.
            capture_snapshot(conn, episode_id)
        return stored

    def forget(self, episode_id: str) -> None:
        with self._lock:
            self._policies.pop(episode_id, None)
            self._clients.pop(episode_id, None)
