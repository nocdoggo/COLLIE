"""Hosts one policy instance per episode and runs it through the common executor.

The coordinator session is created here, on the server, and never leaves the process. Policy
decisions are stored as narration (they never change operational state). Reset creates a new
episode, so the next run gets a fresh policy instance and no memory carries over.

Every coordinator policy, the rule baselines included, runs under the same per-episode caps
(``EpisodeCaps``). Tool calls are counted from the episode's tool-call log for the coordinator
principal, so failed calls, retries and receipt lookups count; model calls are counted from the
decisions that carry them (the live policy attributes every provider call to a decision). A run
gets at most the remaining tool budget. Once a cap is reached the policy is not woken again and
the host records one ``stop`` decision that says so.

The host also knows which policy an episode runs, by the evaluation plan's names: ``rules``
(P0, the profile's deterministic baseline), ``tool-use`` (P1, ``tool-use/1.0.0``), ``live`` or
its alias ``selective`` (P2, ``live/1.0.0``) and ``verify-all`` (P3, ``verify-all/1.0.0``). Every
stored decision is stamped with ``details.policy_mode``: the mode label ("Deterministic policy",
or "<policy label> · <returned model id>", e.g. "Live agent · …") and the caps it ran under.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal

from plan_b.domain.models import EpisodeCapsReport, PolicyDecision, PolicyRunResult
from plan_b.evaluation.policies.base import Policy
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.projection_db import capture_snapshot
from plan_b.store.sessions import AuthError, issue_session
from plan_b.tools.client import InProcessToolClient, LoseResponse

if TYPE_CHECKING:
    from plan_b.agent.config import ModelConfig

COORDINATOR_ROLE = "coordinator_agent"
PolicyChoice = Literal["rules", "tool-use", "live", "selective", "verify-all"]
POLICY_CHOICES: tuple[PolicyChoice, ...] = ("rules", "tool-use", "live", "selective", "verify-all")
# ``selective`` names P2 as the evaluation plan does; the host stores it as ``live``.
POLICY_ALIASES: dict[str, PolicyChoice] = {"selective": "live"}
DETERMINISTIC_LABEL = "Deterministic policy"
LIVE_LABEL = "Live agent"
TOOL_USE_LABEL = "Tool-use agent"
VERIFY_ALL_LABEL = "Verify-all agent"
# Model-driven policies: (policy id prefix, the choice that selects it, its mode label).
MODEL_POLICIES: tuple[tuple[str, PolicyChoice, str], ...] = (
    ("tool-use/", "tool-use", TOOL_USE_LABEL),
    ("live/", "live", LIVE_LABEL),
    ("verify-all/", "verify-all", VERIFY_ALL_LABEL),
)
CAP_FAILURES = {"tool_calls": "tool_call_cap", "model_calls": "model_call_cap"}


@dataclass(frozen=True)
class EpisodeCaps:
    """Per-episode caps for every coordinator policy. The defaults are the Wave 2
    development-phase values that Wave 3 freezes: 48 tool calls (the rule baselines use 19-30
    in the development cases) and 8 model calls (only the model-driven policies, P1-P3, call
    a model). A rebuilt policy (a restarted server) continues the episode's recorded counters
    and model spend (``resume_usage``)."""

    max_tool_calls: int = 48
    max_model_calls: int = 8
    phase: Literal["development", "frozen"] = "development"

    def __post_init__(self) -> None:
        if self.max_tool_calls < 1 or self.max_model_calls < 1:
            raise ValueError("episode caps must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "max_tool_calls": self.max_tool_calls,
            "max_model_calls": self.max_model_calls,
        }


DEVELOPMENT_CAPS = EpisodeCaps()


@dataclass(frozen=True)
class EpisodeUsage:
    tool_calls: int
    model_calls: int


class PolicyLockedError(ValueError):
    """The episode's coordinator already acted under another policy."""


def default_policy_factory() -> Policy:
    from plan_b.evaluation.policies.rules import RulePolicy

    return RulePolicy()


def baseline_policy_factory(profile_id: str) -> Callable[[], Policy]:
    """The deterministic baseline for a profile: the documented rule policy for the event
    profiles, the pantry rule policy for the consumable profile. The profile selects a policy
    and its declared rules; it never selects a scripted outcome."""
    if profile_id == "pantry_continuity":

        def pantry() -> Policy:
            from plan_b.evaluation.policies.pantry_rules import PantryRulePolicy

            return PantryRulePolicy()

        return pantry
    return default_policy_factory


def canonical_choice(choice: str) -> PolicyChoice:
    """The stored name of a choice (``selective`` is ``live``); raises on an unknown one."""
    if choice not in POLICY_CHOICES:
        raise ValueError(f"unknown policy {choice!r}; choose one of {', '.join(POLICY_CHOICES)}")
    return POLICY_ALIASES.get(choice, choice)


def live_factory(
    caps: EpisodeCaps = DEVELOPMENT_CAPS, config: ModelConfig | None = None
) -> Callable[[], Policy]:
    """The live coordinator (``live/1.0.0``) under the episode caps. Its endpoint configuration
    is read now, server-side (environment, else ``.local/keys/model_endpoint.env``); the key is
    read only by the provider, per call. Raises ``ModelConfigError`` when the endpoint is not
    configured."""
    from plan_b.agent.orchestrator import live_policy_factory

    return live_policy_factory(
        config, max_model_calls=caps.max_model_calls, max_tool_calls=caps.max_tool_calls
    )


def tool_use_factory(
    caps: EpisodeCaps = DEVELOPMENT_CAPS, config: ModelConfig | None = None
) -> Callable[[], Policy]:
    """P1, the tool-using model baseline (``tool-use/1.0.0``), under the same caps and the same
    server-side endpoint configuration as the live coordinator."""
    from plan_b.agent.policies.tool_use import tool_use_policy_factory

    return tool_use_policy_factory(
        config, max_model_calls=caps.max_model_calls, max_tool_calls=caps.max_tool_calls
    )


def verify_all_factory(
    caps: EpisodeCaps = DEVELOPMENT_CAPS, config: ModelConfig | None = None
) -> Callable[[], Policy]:
    """P3, the verify-all ablation (``verify-all/1.0.0``), under the same caps and endpoint."""
    from plan_b.agent.policies.verify_all import verify_all_policy_factory

    return verify_all_policy_factory(
        config, max_model_calls=caps.max_model_calls, max_tool_calls=caps.max_tool_calls
    )


def policy_factory_for(
    choice: PolicyChoice,
    profile_id: str,
    *,
    caps: EpisodeCaps = DEVELOPMENT_CAPS,
    live_config: ModelConfig | None = None,
) -> Callable[[], Policy]:
    """``rules`` is the profile's deterministic baseline (P0); the model-driven choices share
    the endpoint configuration, read server-side (``ModelConfigError`` when it is missing)."""
    choice = canonical_choice(choice)
    if choice == "rules":
        return baseline_policy_factory(profile_id)
    if choice == "tool-use":
        return tool_use_factory(caps, live_config)
    if choice == "verify-all":
        return verify_all_factory(caps, live_config)
    return live_factory(caps, live_config)


def is_live(policy_id: str) -> bool:
    """The live coordinator (P2) itself."""
    return policy_id.startswith("live/")


def is_model_driven(policy_id: str) -> bool:
    """P1, P2 or P3: a policy whose decisions carry model calls."""
    return any(policy_id.startswith(prefix) for prefix, _, _ in MODEL_POLICIES)


def choice_of(policy_id: str) -> PolicyChoice:
    """The selection that runs ``policy_id`` (``rules`` for the deterministic baselines)."""
    return next((c for prefix, c, _ in MODEL_POLICIES if policy_id.startswith(prefix)), "rules")


def mode_label(policy_id: str, model_id: str | None, requested_model: str | None = None) -> str:
    """ "Deterministic policy", or "<policy label> · <model id as returned by the provider>"
    ("Live agent", "Tool-use agent" or "Verify-all agent"); before the first reply the
    configured model is named and marked as requested."""
    label = next((lbl for prefix, _, lbl in MODEL_POLICIES if policy_id.startswith(prefix)), None)
    if label is None:
        return DETERMINISTIC_LABEL
    if model_id:
        return f"{label} · {model_id}"
    if requested_model:
        return f"{label} · {requested_model} (requested; no reply yet)"
    return label


def returned_model_id(decision: PolicyDecision) -> str | None:
    """The model id a decision's provider calls returned (the last one if they differ)."""
    model = decision.details.get("model")
    found = model.get("model_id") if isinstance(model, dict) else None
    if isinstance(found, list):
        found = found[-1] if found else None
    return found if isinstance(found, str) and found else None


def _model_calls(decision: PolicyDecision) -> int:
    model = decision.details.get("model")
    calls = model.get("calls") if isinstance(model, dict) else None
    return len(calls) if isinstance(calls, list) else 0


def _model_spend(decision: PolicyDecision) -> float:
    model = decision.details.get("model")
    calls = model.get("calls") if isinstance(model, dict) else None
    if not isinstance(calls, list):
        return 0.0
    return sum(
        float(c["cost_usd"])
        for c in calls
        if isinstance(c, dict) and isinstance(c.get("cost_usd"), int | float)
    )


class PolicyHost:
    """``policy_factory`` serves every episode without a selection. With ``factory_for`` the
    host can select a policy per episode (``select``), and an episode whose stored decisions
    came from a model-driven policy keeps it after a restart."""

    def __init__(
        self,
        db: Database,
        policy_factory: Callable[[], Policy] = default_policy_factory,
        *,
        caps: EpisodeCaps = DEVELOPMENT_CAPS,
        factory_for: Callable[[PolicyChoice, str], Callable[[], Policy]] | None = None,
    ) -> None:
        self._db = db
        self._factory = policy_factory
        self._factory_for = factory_for
        self.caps = caps
        self._policies: dict[str, Policy] = {}
        self._clients: dict[str, InProcessToolClient] = {}
        self._selected: dict[str, tuple[PolicyChoice, Callable[[], Policy]]] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------ selection

    def select(
        self,
        episode_id: str,
        choice: PolicyChoice,
        factory: Callable[[], Policy] | None = None,
    ) -> None:
        """Choose the episode's policy. Allowed only before its coordinator has acted, so one
        episode never mixes two policies' memory or caps. Building a model-driven factory reads
        the endpoint configuration and raises ``ModelConfigError`` when it is missing."""
        choice = canonical_choice(choice)
        if factory is None:
            if self._factory_for is None:
                raise ValueError("this host has no per-episode policy factories")
            factory = self._factory_for(choice, self._profile(episode_id))
        if self.acted(episode_id):
            raise PolicyLockedError(
                "the coordinator already acted in this episode; load a clean episode to change"
                " the policy"
            )
        with self._lock:
            self._selected[episode_id] = (choice, factory)
            self._policies.pop(episode_id, None)

    def acted(self, episode_id: str) -> bool:
        with self._db.read() as conn:
            return self._tool_calls(conn, episode_id) > 0 or bool(repo.decisions(conn, episode_id))

    def choice(self, episode_id: str) -> PolicyChoice:
        return choice_of(self.policy(episode_id).policy_id)

    def _profile(self, episode_id: str) -> str:
        with self._db.read() as conn:
            return repo.get_episode(conn, episode_id).profile_id

    def _factory_of(self, episode_id: str) -> Callable[[], Policy]:
        with self._lock:
            selected = self._selected.get(episode_id)
        if selected is not None:
            return selected[1]
        if self._factory_for is None:
            return self._factory
        # No selection in this process: a restarted server keeps the policy the episode's
        # decisions came from; an episode without decisions runs its deterministic baseline.
        with self._db.read() as conn:
            decisions = repo.decisions(conn, episode_id)
        choice = choice_of(decisions[-1].policy_id) if decisions else "rules"
        return self._factory_for(choice, self._profile(episode_id))

    def policy(self, episode_id: str) -> Policy:
        with self._lock:
            found = self._policies.get(episode_id)
        if found is not None:
            return found
        made = self._factory_of(episode_id)()
        used = self.usage(episode_id)
        resume = getattr(made, "resume_usage", None)
        if callable(resume) and (used.model_calls or used.tool_calls):
            with self._db.read() as conn:
                spent = sum(_model_spend(d) for d in repo.decisions(conn, episode_id))
            # A restart continues the episode's caps: its calls and its model spend.
            resume(used.model_calls, used.tool_calls, spent)
        with self._lock:
            return self._policies.setdefault(episode_id, made)

    # ------------------------------------------------------------------ caps and labels

    def _tool_calls(self, conn: Any, episode_id: str) -> int:
        principal = next(
            p.principal_id
            for p in repo.scenario(conn, episode_id).principals
            if p.role == COORDINATOR_ROLE
        )
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM tool_calls WHERE episode_id = ? AND actor_id = ?",
            (episode_id, principal),
        ).fetchone()
        return int(row["n"])

    def usage(self, episode_id: str) -> EpisodeUsage:
        with self._db.read() as conn:
            tool_calls = self._tool_calls(conn, episode_id)
            model_calls = sum(_model_calls(d) for d in repo.decisions(conn, episode_id))
        with self._lock:
            policy = self._policies.get(episode_id)
        live = getattr(policy, "usage", None)
        if isinstance(live, dict) and isinstance(live.get("model_calls"), int):
            model_calls = max(model_calls, live["model_calls"])
        return EpisodeUsage(tool_calls=tool_calls, model_calls=model_calls)

    def _reached(self, used: EpisodeUsage) -> tuple[Literal["tool_calls", "model_calls"], ...]:
        reached: list[Literal["tool_calls", "model_calls"]] = []
        if used.tool_calls >= self.caps.max_tool_calls:
            reached.append("tool_calls")
        if used.model_calls >= self.caps.max_model_calls:
            reached.append("model_calls")
        return tuple(reached)

    def capped(self, episode_id: str) -> bool:
        return bool(self._reached(self.usage(episode_id)))

    def caps_report(self, episode_id: str) -> EpisodeCapsReport:
        used = self.usage(episode_id)
        return EpisodeCapsReport(
            phase=self.caps.phase,
            max_tool_calls=self.caps.max_tool_calls,
            max_model_calls=self.caps.max_model_calls,
            tool_calls=used.tool_calls,
            model_calls=used.model_calls,
            reached=self._reached(used),
        )

    def latest_model_id(self, episode_id: str) -> str | None:
        with self._db.read() as conn:
            decisions = repo.decisions(conn, episode_id)
        return next((m for d in reversed(decisions) if (m := returned_model_id(d))), None)

    def mode_label(self, episode_id: str) -> str:
        policy = self.policy(episode_id)
        return mode_label(
            policy.policy_id,
            self.latest_model_id(episode_id),
            getattr(policy, "requested_model", None),
        )

    def describe(self, episode_id: str) -> dict[str, Any]:
        """The episode's policy as the board shows it (no secrets, no private records):
        ``requested_model`` is the configured model of a live policy, ``returned_model_id`` the
        model id its latest provider reply named."""
        policy = self.policy(episode_id)
        return {
            "episode_id": episode_id,
            "policy": self.choice(episode_id),
            "policy_id": policy.policy_id,
            "label": self.mode_label(episode_id),
            "requested_model": getattr(policy, "requested_model", None),
            "returned_model_id": self.latest_model_id(episode_id),
            "caps": self.caps_report(episode_id).model_dump(mode="json"),
            "locked": self.acted(episode_id),
        }

    # ------------------------------------------------------------------ runs

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
        """One bounded run with at most ``max_tool_calls`` calls and never more than the
        episode's remaining tool budget. Not run once a cap is reached."""
        policy = self.policy(episode_id)
        policy_id = getattr(policy, "policy_id", "unknown")
        reached = self._reached(self.usage(episode_id))
        if reached:
            return PolicyRunResult(
                policy_id=policy_id,
                status="stopped",
                decisions=self._record_cap(episode_id, policy_id),
                tool_calls=0,
                note="not run: the episode's "
                + " and ".join(r.replace("_", " ") for r in reached)
                + " cap is reached",
            )
        try:
            client = self.client(episode_id)
        except AuthError as exc:
            # The episode was reset before the coordinator session could be issued.
            return PolicyRunResult(
                policy_id=policy_id,
                status="stopped",
                decisions=(),
                tool_calls=0,
                note=f"not run: {exc.message}",
            )
        budget = min(max_tool_calls, self.caps.max_tool_calls - self.usage(episode_id).tool_calls)
        result = policy.run(client, budget)
        stored = self.record(episode_id, result)
        if self._reached(self.usage(episode_id)):
            stored += self._record_cap(episode_id, policy_id)
        return result.model_copy(update={"decisions": stored})

    def _record_cap(self, episode_id: str, policy_id: str) -> tuple[PolicyDecision, ...]:
        """One ``stop`` decision per episode stating which cap was reached."""
        used = self.usage(episode_id)
        reached = self._reached(used)
        with self._db.read() as conn:
            ep = repo.get_episode(conn, episode_id)
            if ep.status != "active" or any(
                d.details.get("recorded_by") == "host" for d in repo.decisions(conn, episode_id)
            ):
                return ()
        spent: list[str] = []
        if "tool_calls" in reached:
            spent.append(f"{used.tool_calls} of {self.caps.max_tool_calls} tool calls")
        if "model_calls" in reached:
            spent.append(f"{used.model_calls} of {self.caps.max_model_calls} model calls")
        decision = PolicyDecision(
            decision_id="dec_host",
            policy_id=policy_id,
            at=ep.clock,
            revision=ep.revision,
            kind="stop",
            summary=(
                f"Episode cap reached: {' and '.join(spent)} used ({self.caps.phase}-phase caps)."
                " The coordinator policy is not woken again in this episode; the accepted plan"
                " and every commitment stay as they are."
            ),
            details={
                "recorded_by": "host",
                "failure": CAP_FAILURES[reached[0]],
                "reached": list(reached),
                "caps": self.caps.as_dict(),
                "usage": {"tool_calls": used.tool_calls, "model_calls": used.model_calls},
            },
        )
        return self.record(
            episode_id,
            PolicyRunResult(
                policy_id=policy_id, status="stopped", decisions=(decision,), tool_calls=0
            ),
        )

    def record(self, episode_id: str, result: PolicyRunResult) -> tuple[PolicyDecision, ...]:
        """Store the run's decisions under store-assigned ids and return the stored copies, each
        stamped with the episode's mode label and caps. Nothing is written into an episode that
        was reset during the run."""
        if not result.decisions:
            return ()
        with self._lock:
            policy = self._policies.get(episode_id)
        requested = getattr(policy, "requested_model", None)
        latest = self.latest_model_id(episode_id)
        stamped: list[PolicyDecision] = []
        for d in result.decisions:
            latest = returned_model_id(d) or latest
            mode = {
                "policy": choice_of(d.policy_id),
                "label": mode_label(d.policy_id, latest, requested),
                "caps": self.caps.as_dict(),
            }
            stamped.append(d.model_copy(update={"details": {**d.details, "policy_mode": mode}}))
        with self._db.write() as conn:
            if repo.get_episode(conn, episode_id).status != "active":
                return ()
            stored = tuple(repo.insert_decision(conn, episode_id, d) for d in stamped)
            # Decisions are narration, not state: no revision change, but the snapshot of the
            # current revision is refreshed so replay frames show them.
            capture_snapshot(conn, episode_id)
        return stored

    def forget(self, episode_id: str) -> None:
        with self._lock:
            self._policies.pop(episode_id, None)
            self._clients.pop(episode_id, None)
            self._selected.pop(episode_id, None)
