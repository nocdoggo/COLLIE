"""Deterministic scenario runner (privileged harness).

The runner owns the private case: it loads a clean episode, plays scripted exogenous actors
through their *own* scoped sessions (participant check-ins; a simulated organizer answering an
in-bounds authorization request after a declared latency; in the pantry profile a labeled staff
simulator that answers stock-transfer tasks and records the aggregate distribution), wakes the
policy when public state changed or its requested wake time passed, and advances the clock one
minute at a time to the hard end. It never writes state directly and never tells the policy what
to do. Minute ticks, rather than jumps to private event times, keep wake-up timing from leaking
hidden events.

``run_case`` chooses the coordinator policy by name: ``rules`` is the profile's deterministic
baseline (P0), ``tool-use`` the tool-using model baseline (P1), ``live`` or ``selective`` the live
coordinator (P2) and ``verify-all`` its verify-all ablation (P3). Every policy runs under the same
per-episode caps (``EpisodeCaps``, recorded in the outcome report); once a cap is reached the
policy is not woken again.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from plan_b.domain.fixtures import load_public_scenario
from plan_b.domain.models import (
    ActorScript,
    EpisodeHistory,
    EventStateView,
    OrganizerAuthorizationRule,
    OrganizerGoalUpdateScript,
    OutcomeReport,
    ParticipantCheckInScript,
    ParticipantObservationScript,
    PolicyRunResult,
    PrivateCase,
    StaffDistributionRule,
    StaffHandoffRule,
)
from plan_b.domain.timeutil import fmt_ts
from plan_b.evaluation.policies.base import Policy
from plan_b.scenarios.policy_host import (
    DEVELOPMENT_CAPS,
    EpisodeCaps,
    PolicyChoice,
    PolicyHost,
    policy_factory_for,
)
from plan_b.scenarios.policy_host import (  # re-exported: the baseline used to live here
    baseline_policy_factory as baseline_policy_factory,
)
from plan_b.store import repo
from plan_b.store.database import Database
from plan_b.store.engine import advance_by, run_due_scheduled
from plan_b.store.episodes import create_episode
from plan_b.store.projection_db import TRACE_VIEWER, build_view
from plan_b.store.sessions import issue_session
from plan_b.world.validate import validate_case
from plan_b.world.world import load_case

if TYPE_CHECKING:
    from plan_b.agent.config import ModelConfig


@dataclass
class RunResult:
    episode_id: str
    case_ref: str
    final_view: EventStateView
    history: EpisodeHistory
    report: OutcomeReport
    policy_runs: list[PolicyRunResult] = field(default_factory=list)
    actor_log: list[dict[str, Any]] = field(default_factory=list)


def episode_history(db: Database, episode_id: str) -> EpisodeHistory:
    with db.read() as conn:
        return EpisodeHistory(
            tool_calls=repo.tool_calls(conn, episode_id),
            transitions=repo.transitions(conn, episode_id),
            decisions=repo.decisions(conn, episode_id),
            receipts=repo.receipts(conn, episode_id),
        )


def audit_view(db: Database, episode_id: str) -> EventStateView:
    with db.read() as conn:
        return build_view(conn, episode_id, TRACE_VIEWER, visibility="audit")


def _clock(db: Database, episode_id: str) -> tuple[datetime, int, datetime]:
    with db.read() as conn:
        ep = repo.get_episode(conn, episode_id)
        return ep.clock, ep.revision, repo.goal(conn, episode_id).hard_end


class ScriptedActors:
    """Exogenous actors from the private case. Each action is registered as a scheduled action
    with the actor's own session and executed by the clock engine at its exact scenario
    instant, through the same executor as any call. The harness never writes state itself."""

    def __init__(self, db: Database, episode_id: str, scripts: tuple[ActorScript, ...]) -> None:
        self._db = db
        self._episode_id = episode_id
        self._scripts = scripts
        self._sessions: dict[str, str] = {}
        self._handled: set[str] = set()
        self.declined: list[dict[str, Any]] = []

    def _register(
        self,
        conn: Any,
        *,
        principal_id: str,
        due: datetime,
        tool: str,
        body: dict[str, Any],
        fill_expected_revision: bool = False,
        fill_rule: str | None = None,
        fill: dict[str, Any] | None = None,
    ) -> None:
        sc = repo.scenario(conn, self._episode_id)
        if sc.tool_durations_minutes.get(tool, 0) != 0:
            raise ValueError(f"scheduled actor actions must be instantaneous; {tool} is not")
        if principal_id not in self._sessions:
            _, session = issue_session(conn, self._episode_id, principal_id)
            self._sessions[principal_id] = session.session_id
        n = repo.next_seq(conn, self._episode_id, "scheduled_action")
        conn.execute(
            "INSERT INTO scheduled_actions (episode_id, action_id, due_at, order_index,"
            " principal_id, session_id, tool, body_json, fill_expected_revision, status,"
            " fill_rule, fill_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                self._episode_id,
                f"act_{n:03d}",
                fmt_ts(due),
                n,
                principal_id,
                self._sessions[principal_id],
                tool,
                json.dumps(body, sort_keys=True),
                int(fill_expected_revision),
                fill_rule,
                json.dumps(fill, sort_keys=True) if fill is not None else None,
            ),
        )

    def _body(self, tool: str, key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool": tool,
            "event_id": repo_event_id(self._db, self._episode_id),
            "idempotency_key": key,
            "arguments": arguments,
        }

    def schedule_initial(self) -> None:
        """Register the time-scheduled participant actions of the case. An action due at or
        before the current clock runs immediately, at the current instant."""
        with self._db.write() as conn:
            for index, script in enumerate(self._scripts):
                key = f"script-{index:02d}"
                if isinstance(script, ParticipantCheckInScript):
                    self._register(
                        conn,
                        principal_id=script.principal_id,
                        due=script.at,
                        tool="check_in",
                        body=self._body(
                            "check_in",
                            key,
                            {
                                "resource_id": script.resource_id,
                                "available": {
                                    "start": fmt_ts(script.available_start),
                                    "end": fmt_ts(script.available_end),
                                },
                            },
                        ),
                    )
                elif isinstance(script, ParticipantObservationScript):
                    self._register(
                        conn,
                        principal_id=script.principal_id,
                        due=script.at,
                        tool="submit_observation",
                        body=self._body(
                            "submit_observation",
                            key,
                            {
                                "text": script.text,
                                "entity_id": script.entity_id,
                                "client_record_id": script.client_record_id,
                            },
                        ),
                    )
                elif isinstance(script, OrganizerGoalUpdateScript):
                    self._register(
                        conn,
                        principal_id=script.principal_id,
                        due=script.at,
                        tool="update_goal",
                        body={
                            **self._body(
                                "update_goal",
                                key,
                                {
                                    "preference_preset": script.preference_preset,
                                    "reason": script.reason,
                                },
                            ),
                            "expected_goal_version": script.expected_goal_version,
                        },
                        fill_expected_revision=True,
                    )
                elif isinstance(script, StaffHandoffRule):
                    self._register_handoff_rule(conn, key, script)
                elif isinstance(script, StaffDistributionRule):
                    # The quantity is decided from the visible state at the instant.
                    self._register(
                        conn,
                        principal_id=script.principal_id,
                        due=script.at,
                        tool="record_distribution",
                        body=self._body(
                            "record_distribution",
                            key,
                            {"distribution_reference": script.distribution_reference},
                        ),
                        fill_expected_revision=True,
                        fill_rule="staff_distribution_rule",
                        fill={"service_target_id": script.service_target_id, "label": script.label},
                    )
            run_due_scheduled(
                conn, self._episode_id, repo.get_episode(conn, self._episode_id).clock
            )

    def _register_handoff_rule(self, conn: Any, key: str, script: StaffHandoffRule) -> None:
        """A standing staff rule: the clock engine answers each stock-transfer hold from the
        source into the destination after the declared latency (``engine.run_due_handoffs``)."""
        sc = repo.scenario(conn, self._episode_id)
        destination = next(
            r for r in sc.resources if r.resource_id == script.destination_resource_id
        )
        if sc.pantry_parameters is None or destination.consumable_stock is None:
            raise ValueError("a staff handoff rule needs a pantry scenario and a stock pool")
        self._register(
            conn,
            principal_id=script.principal_id,
            due=sc.pantry_parameters.handoff_window.start,
            tool="record_stock_receipt",
            body=self._body("record_stock_receipt", key, {}),
            fill_expected_revision=True,
            fill_rule="staff_handoff_rule",
            fill={
                "source_resource_id": script.source_resource_id,
                "destination_resource_id": script.destination_resource_id,
                "source_observation_id": script.source_observation_id,
                "receipt_reference_prefix": script.receipt_reference_prefix,
                "max_quantity": script.max_quantity,
                "unit": destination.consumable_stock.unit,
                "label": script.label,
            },
        )

    def answer_requests(self) -> None:
        """The simulated organizer: schedule an answer to each new, in-bounds authorization
        request in the public decision log, ``latency_minutes`` after it was asked."""
        with self._db.write() as conn:
            decisions = repo.decisions(conn, self._episode_id)
            clock = repo.get_episode(conn, self._episode_id).clock
            for index, rule in enumerate(self._scripts):
                if not isinstance(rule, OrganizerAuthorizationRule):
                    continue
                for d in decisions:
                    req = d.authorization_request
                    if d.kind != "ask" or req is None or req.request_id in self._handled:
                        continue
                    self._handled.add(req.request_id)
                    in_bounds = (
                        req.target_grant_id == rule.target_grant_id
                        and req.resource_id in rule.resource_ids
                        and req.requested_value <= rule.max_committed_cents
                    )
                    if not in_bounds:
                        self.declined.append(
                            {
                                "at": fmt_ts(clock),
                                "kind": "organizer_declined",
                                "script_index": index,
                                "request_id": req.request_id,
                                "reason": "outside the organizer's rule",
                            }
                        )
                        continue
                    due = max(d.at + timedelta(minutes=rule.latency_minutes), clock)
                    self._register(
                        conn,
                        principal_id=rule.principal_id,
                        due=due,
                        tool="update_grant",
                        body=self._body(
                            "update_grant",
                            f"script-{index:02d}-{req.request_id}",
                            {
                                "target_grant_id": req.target_grant_id,
                                "max_total_committed_cents": req.requested_value,
                                "reason": f"Organizer approves authorization request"
                                f" {req.request_id} for {req.resource_id}",
                            },
                        ),
                        fill_expected_revision=True,
                    )
                    if due <= clock:
                        run_due_scheduled(conn, self._episode_id, clock)

    @property
    def log(self) -> list[dict[str, Any]]:
        with self._db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_actions WHERE episode_id = ? ORDER BY due_at, order_index",
                (self._episode_id,),
            ).fetchall()
        entries = [
            {
                "action_id": r["action_id"],
                "due_at": r["due_at"],
                "executed_at": r["executed_at"],
                "principal_id": r["principal_id"],
                "tool": r["tool"],
                "status": r["status"],
                "envelope_status": r["envelope_status"],
                "receipt_id": r["receipt_id"],
                "receipt_status": r["receipt_status"],
                "error_code": r["error_code"],
                "fill_rule": r["fill_rule"],
                "note": r["note"],
            }
            for r in rows
        ]
        return entries + self.declined


def repo_event_id(db: Database, episode_id: str) -> str:
    with db.read() as conn:
        return repo.get_episode(conn, episode_id).event_id


def tick_loop(
    db: Database,
    host: PolicyHost,
    episode_id: str,
    *,
    minutes: int | None,
    run_policy: bool,
    actors: ScriptedActors | None,
    max_tool_calls: int = 16,
) -> list[PolicyRunResult]:
    """Advance minute by minute (to the hard end, or ``minutes``), waking the policy when the
    public revision changed or its wake time passed. Scripted actors act inside the clock
    engine at their own instants; after each policy run the simulated organizer may schedule
    an answer. Stops if the episode is reset meanwhile.

    Wake rule: a revision the policy did not produce itself (an actor action, a world event, an
    engine transition, including ones that happened during the policy's own tool durations) is
    news, so the policy runs again on the next tick even if the revision changed mid-run. A run
    that exhausted its tool budget or ended incomplete is also re-woken on the next tick.

    The policy is never woken at or after the event close, or once the coordinator's grant has
    expired: nothing is left to schedule then, and with an expired grant even its first read
    would be rejected (``GRANT_EXPIRED``). Nor is it woken once an episode cap is reached
    (the host recorded a decision saying so)."""
    runs: list[PolicyRunResult] = []
    clock, _, hard_end = _clock(db, episode_id)
    stop_at = hard_end if minutes is None else min(hard_end, clock + timedelta(minutes=minutes))
    last_seen: int | None = None
    wait_until: datetime | None = None
    while _active(db, episode_id):
        clock, revision, _ = _clock(db, episode_id)
        if (
            run_policy
            and (last_seen is None or revision != last_seen or (wait_until and clock >= wait_until))
            and _policy_may_act(db, episode_id)
            and not host.capped(episode_id)
        ):
            start_revision = revision
            result = host.run(episode_id, max_tool_calls)
            runs.append(result)
            _, last_seen, _ = _clock(db, episode_id)
            wait_until = result.wait_until
            if result.status == "budget_exhausted" or result.incomplete:
                wait_until = clock  # unfinished work: run again on the next tick
            elif _exogenous_revisions(db, episode_id, start_revision, host):
                wait_until = clock  # something else changed while it ran
            if actors is not None:
                actors.answer_requests()
        clock, _, _ = _clock(db, episode_id)
        if clock >= stop_at or not _active(db, episode_id):
            break
        with db.write() as conn:
            if repo.get_episode(conn, episode_id).status != "active":
                break
            advance_by(conn, episode_id, 1)
    return runs


def _policy_may_act(db: Database, episode_id: str) -> bool:
    """Whether the event is still open and the coordinator's current grant is unexpired."""
    with db.read() as conn:
        ep = repo.get_episode(conn, episode_id)
        if (
            repo.get_flag(conn, episode_id, "event_closed")
            or ep.clock >= repo.goal(conn, episode_id).hard_end
        ):
            return False
        agent = next(
            p for p in repo.scenario(conn, episode_id).principals if p.role == "coordinator_agent"
        )
        found = repo.current_grant(conn, episode_id, agent.grant_id)
        return found is not None and ep.clock < found[0].expires_at


def _exogenous_revisions(
    db: Database, episode_id: str, after_revision: int, host: PolicyHost
) -> list[int]:
    """Revisions after ``after_revision`` that the hosted policy did not produce itself."""
    with db.read() as conn:
        if repo.get_episode(conn, episode_id).status != "active":
            return []
        # The coordinator's principal comes from the public scenario; asking the host for a
        # client could try to issue a session for an episode that was just reset.
        principal = next(
            p.principal_id
            for p in repo.scenario(conn, episode_id).principals
            if p.role == "coordinator_agent"
        )
        revisions = [
            r["revision"]
            for r in conn.execute(
                "SELECT revision FROM state_transitions WHERE episode_id = ? AND revision > ?",
                (episode_id, after_revision),
            )
        ]
        own = {
            r["revision_after"]
            for r in conn.execute(
                "SELECT revision_after FROM receipts WHERE episode_id = ? AND actor_id = ?"
                " AND status = 'applied' AND revision_after > ?",
                (episode_id, principal, after_revision),
            )
        } | {
            r["revision_after"]
            for r in conn.execute(
                "SELECT revision_after FROM observations WHERE episode_id = ? AND submitted_by = ?"
                " AND revision_after > ?",
                (episode_id, principal, after_revision),
            )
        }
    return [r for r in revisions if r not in own]


def _active(db: Database, episode_id: str) -> bool:
    with db.read() as conn:
        return repo.get_episode(conn, episode_id).status == "active"


def run_case(
    db: Database,
    case_ref: str,
    *,
    scenario_id: str | None = None,
    policy: PolicyChoice = "rules",
    policy_factory: Callable[[], Policy] | None = None,
    caps: EpisodeCaps = DEVELOPMENT_CAPS,
    live_config: ModelConfig | None = None,
    max_tool_calls: int = 16,
    seed: int | None = None,
) -> RunResult:
    """Run one private case to the hard end. The public scenario is the case's own unless
    ``scenario_id`` names it explicitly (a mismatch fails validation). ``policy`` chooses the
    coordinator: ``rules`` (the profile's deterministic baseline) or a model-driven policy,
    ``tool-use``, ``live`` (alias ``selective``) or ``verify-all``, whose endpoint configuration
    is read server-side (these make paid model calls). ``seed`` is the trial's provider seed for
    a model-driven policy: passed as the OpenAI-compatible ``seed`` when the model's endpoints
    accept one, and recorded on every model call either way (``seed``, ``seed_sent``); the
    deterministic baseline ignores it. An explicit ``policy_factory`` (tests) takes precedence.
    Every policy runs under ``caps``."""
    from plan_b.evaluation.scoring import score_episode

    case: PrivateCase = load_case(case_ref)
    scenario_id = scenario_id or case.scenario_id
    public = load_public_scenario(scenario_id)
    if policy_factory is None:
        policy_factory = policy_factory_for(
            policy, public.profile_id, caps=caps, live_config=live_config, seed=seed
        )
    problems = validate_case(public, case)
    if problems:
        raise ValueError(f"private case {case_ref} failed validation: " + "; ".join(problems))
    with db.write() as conn:
        episode_id = create_episode(conn, scenario_id=scenario_id, case_ref=case_ref)
    host = PolicyHost(db, policy_factory, caps=caps)
    actors = ScriptedActors(db, episode_id, case.actor_scripts)
    actors.schedule_initial()
    runs = tick_loop(
        db,
        host,
        episode_id,
        minutes=None,
        run_policy=True,
        actors=actors,
        max_tool_calls=max_tool_calls,
    )
    final = audit_view(db, episode_id)
    history = episode_history(db, episode_id)
    policy_id = runs[0].policy_id if runs else None
    report = score_episode(final, history, case, policy_id=policy_id).model_copy(
        update={
            "mode_label": host.mode_label(episode_id),
            "episode_caps": host.caps_report(episode_id),
        }
    )
    return RunResult(
        episode_id=episode_id,
        case_ref=case_ref,
        final_view=final,
        history=history,
        report=report,
        policy_runs=runs,
        actor_log=actors.log,
    )
