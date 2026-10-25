"""P1, the ordinary tool-using model baseline: ``tool-use/1.2.0``.

A serious baseline in the sense of ``PEEAI_plan/08_evaluation.md``: the model reads the visible
state and chooses tools and arguments itself, by strict JSON (``calls``: a tool name from the
coordinator grant's ``allowed_tools`` and its arguments as a JSON object), with no server-built
menu. Its instructions (prompt ``tool_use.v3``) cover the objective, source timestamps, the
budget, the deadline, tool documentation, failure handling and preserving valid commitments,
and it may hold and verify. Every call goes through the same ``ToolClient`` and executor as
every other policy, which validates it; the candidates are the planner's own
(``evaluate_candidates``), so there is no menu advantage and no extra authority.

One ``run`` (one wake):

1. read the state (stop when the event is over, the episode closed or the grant not valid);
2. when nothing new happened since the model last decided (the plan, goal, observations,
   grants, holds, commitments, stock, staff tasks and failed activities are unchanged), no new
   notice arrived and no wake time passed (its own ``wait_minutes``, a retry, or the shared wake
   schedule: a deadline watch, an open request's hold, an awaited staff handoff, the opening of
   the handoff window), wait without a model call;
3. the attention rule shared with P2 and P3 (``agent/attention.py``, 1.1.0): a new notice
   warrants a turn (a repeat of one already shown is recorded as a duplicate by the server);
   otherwise the planner's evaluation is read and a turn is warranted only when the decision
   menu P2 would build from this state offers an action. If not, the server records what the
   state determines (keep, a shortfall, infeasible, or a wait), as for P2, and no model call is
   made. So status answers, arrival records and check-ins that change nothing actionable cost
   no model call;
4. otherwise up to ``MAX_TURNS`` model turns. Each turn's observation is the state and the
   planner's current evaluation (read with ``evaluate_candidates`` whenever the revision moved,
   as the selective policy reads it before each choice). Each turn returns up to
   ``MAX_CALLS_PER_TURN`` tool calls, run in order with the key
   ``tooluse-r<revision>-<tool>-<sha8(arguments)>`` and the latest observed revision and goal
   version; their results reach the next turn. A turn with no calls (or ``done``) ends the run
   with the model's decision (keep, wait, ask, infeasible, unresolved, inapplicable, duplicate
   or none), unless its calls brought news it decided without (a status answer with a new
   observation, or a rejection with a new receipt): then the next turn shows the results. After
   a sent mutation or check, or a lost mutation, the next turn sees a fresh state (the model's
   own state read, when that was its last call).

The same caps as every policy: ``max_model_calls`` model calls and ``max_tool_calls`` tool calls
per episode (repairs, failed calls, retries and receipt lookups count), the per-run budget, and
the provider's spend guard. Failures are decisions, never invented successes, as for P2:
malformed output after one repair, or a tool, decision or request outside what is offered
(``invalid_choice``, refused before any call), is a ``wait``; a cap, the spend cap or missing
configuration is ``stop``; a provider timeout or error is ``wait`` retried 2 minutes later; a
stale or otherwise rejected request is recorded with its error code and returned to the model;
a lost mutation response is reconciled with ``get_action_receipt`` and the original key.

Summaries are composed by the server from receipts and envelopes. The model's rationale is kept
as ``details.choice.rationale_untrusted``; an ``ask`` carries an ``AuthorizationRequest`` that
the server builds and checks against the grant and the evaluation of the state the ask is made
in (1.1.0: when the turn's own calls moved the state, such as a hold in the same turn, the state
is evaluated again and the named candidate is checked as it stands there): a feasible candidate
short only of committed spending, one of its bookings, and a value above the current limit and
at most what the candidate needs. The request's content is part of its id, so a corrected ask is
a new request; an open request is remembered, as P2 remembers its own, so the menu offers no
repeat of it.

Generation settings and the seed are the provider's (``agent/provider.py``): the same output
limit, sampling settings and seed handling as P2 and P3, recorded on every call.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from plan_b.agent.attention import AttentionMixin, _Evaluated, _Watch
from plan_b.agent.config import ModelConfig, load_model_config
from plan_b.agent.interpret import LiveInterpretation
from plan_b.agent.menu import Menu, OpenAsk, ask_reason, own_grant, shortfalls
from plan_b.agent.orchestrator import (
    _candidate_context,
    _status_text,
    _stock_context,
    resume_spend,
)
from plan_b.agent.prompts import Prompt, load_prompt
from plan_b.agent.provider import (
    DEFAULT_TIMEOUT_S,
    MAX_OUTPUT_TOKENS,
    CallRecord,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    OpenAICompatibleProvider,
    ProviderConfigError,
    ProviderError,
    ProviderMalformedJSON,
    ProviderSchemaViolation,
    SpendCapReached,
    SpendGuard,
    SpendLedger,
)
from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import (
    STAFF_TOOLS,
    ActionReceipt,
    AuthorizationRequest,
    CandidateResult,
    DecisionKind,
    EvaluationResult,
    EventStateView,
    ObservationRecord,
    PolicyDecision,
    PolicyRunResult,
    Strict,
    ToolEnvelope,
)
from plan_b.domain.timeutil import local_label
from plan_b.evaluation.policies.base import ToolClient, TransportLost
from plan_b.evaluation.policies.parser import NOTICE_KINDS, normalize_text

POLICY_ID = "tool-use/1.2.0"
PROMPT_ID = "tool_use.v3"  # v3: when the server calls; v1 and v2 kept for the runs citing them
SCHEMA_NAME = "plan_b_tool_turn"
DEFAULT_MAX_MODEL_CALLS = 8
DEFAULT_MAX_TOOL_CALLS = 32
MAX_TURNS = 6  # model turns in one run
MAX_CALLS_PER_TURN = 3
MAX_RESULTS_SHOWN = 12
MAX_OBSERVATIONS_SHOWN = 30
MAX_CANDIDATES_SHOWN = 10
MAX_DECISIONS_SHOWN = 6
MAX_RATIONALE_CHARS = 400
MAX_WAIT_MINUTES = 240
MAX_RECEIPT_LOOKUPS = 2
TURN_MAX_TOKENS = MAX_OUTPUT_TOKENS  # the provider's one limit; reasoning tokens count
PROVIDER_RETRY = timedelta(minutes=2)
STALE = frozenset({"REVISION_CONFLICT", "CANDIDATE_STALE", "GOAL_VERSION_CONFLICT"})
MUTATIONS = frozenset({"hold_resource", "release_hold", "apply_plan"})
BLOCKED = "mutations are blocked in this run"  # after a mutation whose outcome was lost
# Tools that change state or the clock: the next turn sees a fresh state read.
REFRESHING = MUTATIONS | {"query_status"}
DECISIONS = ("none", "keep", "wait", "ask", "infeasible", "unresolved", "inapplicable", "duplicate")
_FINAL_KIND: dict[str, DecisionKind] = {
    "none": "wait",
    "keep": "keep",
    "wait": "wait",
    "ask": "ask",
    "infeasible": "infeasible",
    "unresolved": "unresolved",
    "inapplicable": "inapplicable",
    "duplicate": "duplicate",
}

Failure = Literal[
    "malformed_output",
    "invalid_choice",
    "model_call_cap",
    "tool_call_cap",
    "spend_cap",
    "provider_timeout",
    "provider_error",
    "provider_config",
    "stale_revision",
    "lost_response",
]


def idempotency_key(revision: int, tool: str, arguments: dict[str, Any]) -> str:
    """``tooluse-r<revision>-<tool>-<sha8(arguments)>``: one key per intended request."""
    return f"tooluse-r{revision}-{tool}-{sha256_hex(canonical_json(arguments))[:8]}"


class CallSpec(Strict):
    tool: str
    arguments_json: str


class AskSpec(Strict):
    candidate_id: str
    resource_id: str
    requested_value: int


class TurnOutput(Strict):
    """One model turn (structured output)."""

    calls: tuple[CallSpec, ...]
    done: bool
    decision: str
    ask: AskSpec | None
    wait_minutes: int | None
    rationale: str
    cited_refs: tuple[str, ...]


def turn_schema(tools: tuple[str, ...]) -> dict[str, Any]:
    """Strict JSON schema of ``TurnOutput`` (every property required, no extras)."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(TurnOutput.model_fields),
        "properties": {
            "calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["tool", "arguments_json"],
                    "properties": {
                        "tool": {"type": "string", "enum": list(tools)},
                        "arguments_json": {"type": "string"},
                    },
                },
            },
            "done": {"type": "boolean"},
            "decision": {"type": "string", "enum": list(DECISIONS)},
            "ask": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["candidate_id", "resource_id", "requested_value"],
                        "properties": {
                            "candidate_id": {"type": "string"},
                            "resource_id": {"type": "string"},
                            "requested_value": {"type": "integer"},
                        },
                    },
                ]
            },
            "wait_minutes": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "rationale": {"type": "string"},
            "cited_refs": {"type": "array", "items": {"type": "string"}},
        },
    }


# ---------------------------------------------------------------------------------- control


class _RunBudget(Exception):
    """The run's tool-call budget is spent."""


class _ReadLost(Exception):
    """A read response was lost twice in a row."""


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Halt(Exception):
    def __init__(self, failure: Failure, reason: str) -> None:
        super().__init__(reason)
        self.failure = failure
        self.reason = reason


class _ModelFailed(Exception):
    def __init__(self, failure: Failure, error: ProviderError) -> None:
        super().__init__(error.message)
        self.failure = failure
        self.error = error


@dataclass
class _Run:
    client: ToolClient
    max_calls: int
    calls: int = 0
    decisions: list[PolicyDecision] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    read_refs: list[str] = field(default_factory=list)
    mutations_blocked: bool = False


@dataclass
class _Outcome:
    """What one requested call did, as the next turn sees it."""

    tool: str
    arguments: dict[str, Any] | str
    envelope: ToolEnvelope | None = None
    receipt: ActionReceipt | None = None
    call_ids: tuple[str, ...] = ()
    key: str | None = None
    reconciled: bool = False
    refused: str | None = None  # refused before any tool call (with the reason)

    @property
    def applied(self) -> bool:
        return self.receipt is not None and self.receipt.status == "applied"

    @property
    def error_code(self) -> str | None:
        if self.receipt is not None and self.receipt.error_code is not None:
            return self.receipt.error_code
        if self.envelope is not None and self.envelope.error is not None:
            return self.envelope.error.code
        return None


# ---------------------------------------------------------------------------------- policy


class ToolUsePolicy(AttentionMixin):
    """``tool-use/1.2.0``: the model picks tools and arguments; the executor validates. When a
    model turn is warranted is the server-side attention rule shared with P2 and P3
    (``agent/attention.py``)."""

    policy_id = POLICY_ID

    def __init__(
        self,
        provider: ModelProvider,
        *,
        max_model_calls: int = DEFAULT_MAX_MODEL_CALLS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> None:
        if max_model_calls < 1 or max_tool_calls < 1:
            raise ValueError("caps must be positive")
        self._provider = provider
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self._prompt: Prompt = load_prompt(PROMPT_ID)
        self._seq = 0
        self._model_calls = 0
        self._tool_calls = 0
        self._call_seq = 0
        self._cost_usd = 0.0
        self._pending_calls: list[CallRecord] = []
        self._results: list[dict[str, Any]] = []  # tool results since the last model call
        self._history: list[dict[str, Any]] = []  # recent results, for continuity
        self._evaluation: EvaluationResult | None = None
        self._settled: str | None = None
        self._model_wake: datetime | None = None  # the model's wait_minutes, a retry, a bound
        # Policy 1.2: whether _model_wake is the model's wait_minutes asked again on a state
        # unchanged since its last wait (then the wake goes through the shared attention rule;
        # a first wait, a retry and the turn bound's continuation are their own turn), the state
        # digest of its last wait, and the menu the shared rule last offered.
        self._wake_repeat = False
        self._wait_digest: str | None = None
        self._offered: Menu | None = None
        self._ended_with: str | None = None
        self._halted: str | None = None
        # The shared attention rule's state (``AttentionMixin``). P1 keeps no interpretations.
        self._interps: dict[str, LiveInterpretation] = {}
        self._open_ask: OpenAsk | None = None
        self._hold_counts: dict[tuple[str, str, int], int] = {}
        self._wake: datetime | None = None  # an open authorization request's hold lapses
        self._watch: _Watch | None = None
        self._watch_offered: set[tuple[str, str, int]] = set()
        self._window: datetime | None = None
        self._recorded: set[tuple[Any, ...]] = set()
        self._seen_notices: set[str] = set()  # notices a model turn has shown
        self._lineages: dict[tuple[str, str], str] = {}  # (group, text) -> first notice shown
        self._principal = ""
        self._at: datetime | None = None
        self._revision: int | None = None
        self._goal_version: int | None = None

    @property
    def requested_model(self) -> str:
        return self._provider.requested_model

    @property
    def usage(self) -> dict[str, Any]:
        return {
            "model_calls": self._model_calls,
            "max_model_calls": self.max_model_calls,
            "tool_calls": self._tool_calls,
            "max_tool_calls": self.max_tool_calls,
            "cost_usd": round(self._cost_usd, 8),
        }

    def resume_usage(self, model_calls: int, tool_calls: int, spent_usd: float = 0.0) -> None:
        """A rebuilt instance (a restarted server) continues the episode's recorded counters
        and model spend, so the per-episode caps, the USD one included, hold across the
        restart."""
        self._model_calls = max(self._model_calls, model_calls)
        self._tool_calls = max(self._tool_calls, tool_calls)
        resume_spend(self._provider, spent_usd)

    # ------------------------------------------------------------------ entry point

    def run(self, client: ToolClient, max_tool_calls: int = 16) -> PolicyRunResult:
        self._principal = client.principal_id
        run = _Run(client, max_tool_calls)
        if self._halted is not None:
            return self._result(run, "stopped", None, note=f"halted: {self._halted}")
        try:
            status, wait_until = self._run(run)
        except _RunBudget:
            run.notes.append(f"tool-call budget of {max_tool_calls} for this run spent")
            self._flush(run)
            return self._result(run, "budget_exhausted", None)
        except _ReadLost:
            run.notes.append("a state read response was lost twice; nothing was decided")
            self._flush(run)
            return self._result(run, "waiting", None, incomplete=True)
        except _Halt as halt:
            self._halted = halt.reason
            self._record(
                run,
                "stop",
                f"Stopped for this episode: {halt.reason}. No further action is taken; the "
                "accepted plan and every commitment stay as they are.",
                details={"failure": halt.failure},
            )
            return self._result(run, "stopped", None)
        self._flush(run)
        return self._result(run, status, wait_until)

    def _result(
        self,
        run: _Run,
        status: Literal["waiting", "stopped", "budget_exhausted"],
        wait_until: datetime | None,
        *,
        incomplete: bool = False,
        note: str = "",
    ) -> PolicyRunResult:
        notes = [*run.notes, note] if note else run.notes
        return PolicyRunResult(
            policy_id=self.policy_id,
            status=status,
            decisions=tuple(run.decisions),
            tool_calls=run.calls,
            wait_until=wait_until,
            note="; ".join(notes),
            incomplete=incomplete,
        )

    def _run(self, run: _Run) -> tuple[Literal["waiting", "stopped"], datetime | None]:
        try:
            view = self._refresh(run)
        except _Stop as stop:
            self._record(run, "stop", f"Stopped: {stop.reason}. No further action.")
            return "stopped", None
        now = self._now(view)
        woke = self._model_wake is not None and now >= self._model_wake
        woke_ask = self._wake is not None and now >= self._wake
        woke_watch = self._watch is not None and now >= self._watch.at
        woke_window = self._window is not None and now >= self._window
        fresh = self._fresh_notices(view, run)
        if self._settled == _digest(view) and not (
            fresh or woke or woke_ask or woke_watch or woke_window
        ):
            return "waiting", self._next_wake(view, now)
        if woke:
            self._model_wake = None
        # A timed wake can change what the clock-dependent checks say (the handoff window, a
        # deadline watch) with no new revision: the evaluation is read again.
        timed = woke or woke_ask or woke_watch or woke_window
        own_turn = woke and not self._wake_repeat
        self._offered = None
        self._ended_with = None
        try:
            # The shared attention rule: a new notice warrants a turn; otherwise only a state
            # whose decision menu offers an action does (P2's rule, ``agent/attention.py``). A
            # retry after a failed call, the turn bound's continuation and a wake the model asked
            # for (its wait_minutes) are their own turn. Policy 1.2: a wait asked again on a
            # state unchanged since the model's last wait is not: it goes through the shared
            # rule, so repeated waits on an unchanged state do not each cost a model call.
            if not fresh and not own_turn and not self._warranted(view, run, woke_watch, timed):
                self._settled = _digest(view)
                return "waiting", self._next_wake(view, self._now(view))
            self._model_wake = None
            for _ in range(MAX_TURNS):
                self._observe(view, run, refresh=timed)
                turn = self._turn(view, run)
                if turn is None:
                    break
                output, response = turn
                seen = _visible_ids(view)
                outcomes = self._execute_calls(view, run, output, response)
                if any(_moved(o) for o in outcomes):
                    view = self._next_view(run, outcomes)
                # A new status answer or a new rejection is news the model decided without: its
                # results reach the next turn instead of ending the run. A repeated answer or a
                # replayed rejection it has already seen is not.
                news = any(_news(o, seen) for o in outcomes)
                if (output.done or not output.calls) and not news:
                    self._finish(view, run, output, response)
                    break
            else:
                run.notes.append(f"turn bound of {MAX_TURNS} reached; the next wake continues")
                self._model_wake = self._now(view)
                self._wake_repeat = False
            if self._offered is not None and self._ended_with not in (None, "ask"):
                self._note_declined(view, self._offered)
        except _Stop as stop:
            self._record(run, "stop", f"Stopped: {stop.reason}. No further action.")
            return "stopped", None
        except _ModelFailed as failed:
            what = "timed out" if failed.failure == "provider_timeout" else "failed"
            retry = self._now(view) + PROVIDER_RETRY
            self._model_wake = retry
            self._wake_repeat = False
            self._record(
                run,
                "wait",
                f"The model call {what} ({failed.error.kind}: {failed.error.message[:160]}); no "
                "action is taken and the plan is unchanged. The next wake tries again within "
                "the caps.",
                details={"failure": failed.failure, "error_kind": failed.error.kind},
                wait_until=retry,
            )
            return "waiting", retry
        self._settled = _digest(view)
        return "waiting", self._next_wake(view, self._now(view))

    # ------------------------------------------------------------------ attention

    def _fresh_notices(self, view: EventStateView, run: _Run) -> list[ObservationRecord]:
        """Notices no model turn has shown yet. A repeat of a shown notice (same correlation
        group and text) is one evidence lineage: the server records it as a duplicate without
        a model call, as P2's server does."""
        fresh: list[ObservationRecord] = []
        for record in view.observations:
            obs = record.observation
            if obs.kind not in NOTICE_KINDS or obs.observation_id in self._seen_notices:
                continue
            original = self._lineages.get((obs.correlation_group, normalize_text(obs.text)))
            if original is None:
                fresh.append(record)
                continue
            self._seen_notices.add(obs.observation_id)
            self._record(
                run,
                "duplicate",
                f"Notice {obs.observation_id} repeats notice {original} (same correlation group "
                "and text): one evidence lineage, not corroboration. No plan change.",
                observation_refs=(obs.observation_id, original),
                details={"duplicate_of": original},
            )
        return fresh

    def _mark_shown(self, view: EventStateView) -> None:
        """Every visible notice reached the model in this turn (``_observations``)."""
        for record in view.observations:
            obs = record.observation
            if obs.kind in NOTICE_KINDS and obs.observation_id not in self._seen_notices:
                self._seen_notices.add(obs.observation_id)
                self._lineages.setdefault(
                    (obs.correlation_group, normalize_text(obs.text)), obs.observation_id
                )

    def _warranted(
        self, view: EventStateView, run: _Run, woke_watch: bool, timed: bool = False
    ) -> bool:
        """Whether the decision menu of this state offers an action (``AttentionMixin``). When
        it does not, the server records what the state determines, as for P2."""
        envelope = self._observe(view, run, refresh=timed)
        ev = self._evaluation
        if ev is None or (ev.revision, ev.goal_version) != (view.revision, view.goal.version):
            code = (
                envelope.error.code
                if envelope is not None and envelope.error is not None
                else envelope.status
                if envelope is not None
                else "not available"
            )
            self._record_once(
                run,
                ("wait", "evaluation", code, view.revision),
                "wait",
                f"evaluate_candidates was {code}; no model turn is warranted without an "
                f"evaluation and plan v{view.plan.plan_version} is unchanged.",
                tool_call_refs=tuple(run.read_refs),
                details={"error_code": code},
            )
            run.read_refs = []
            return False
        evaluated = _Evaluated(ev=ev)
        menu = self._attend(view, run, evaluated, [], woke_watch)
        if menu.needs_choice and not self._declined_repeat(view, menu):
            self._offered = menu
            return True
        self._record_default(view, run, evaluated, menu, [])
        run.read_refs = []
        return False

    def _next_wake(self, view: EventStateView, now: datetime) -> datetime | None:
        """The shared wake schedule (deadline watch, an open request's hold, an awaited staff
        handoff, the handoff window's opening) and the model's own requested wake."""
        times = [t for t in (self._compute_wait(view, now), self._model_wake) if t is not None]
        return min(times) if times else None

    # ------------------------------------------------------------------ tools

    def _call(
        self,
        run: _Run,
        tool: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        expected_goal_version: int | None = None,
    ) -> ToolEnvelope:
        if tool in STAFF_TOOLS:
            raise ValueError(f"the tool-use policy never calls {tool}")
        if self._tool_calls >= self.max_tool_calls:
            raise _Halt(
                "tool_call_cap",
                f"the tool-call cap of {self.max_tool_calls} for this episode is spent",
            )
        if run.calls >= run.max_calls:
            raise _RunBudget
        run.calls += 1
        self._tool_calls += 1
        envelope = run.client.call(
            tool,
            arguments=arguments,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_goal_version=expected_goal_version,
        )
        if envelope.scenario_time is not None:
            self._at = envelope.scenario_time
        if envelope.revision is not None:
            self._revision = envelope.revision
        if envelope.goal_version is not None:
            self._goal_version = envelope.goal_version
        return envelope

    def _read(self, run: _Run, tool: str, arguments: dict[str, Any]) -> ToolEnvelope:
        """Reads have no side effect, so one lost response is retried once."""
        try:
            return self._call(run, tool, arguments)
        except TransportLost:
            try:
                return self._call(run, tool, arguments)
            except TransportLost as exc:
                raise _ReadLost from exc

    def _refresh(self, run: _Run) -> EventStateView:
        envelope = self._read(run, "get_event_state", {})
        if envelope.status != "succeeded" or envelope.data is None:
            code = envelope.error.code if envelope.error is not None else envelope.status
            raise _Stop(f"the state read was {envelope.status} ({code})")
        return self._checked(EventStateView.model_validate(envelope.data))

    def _checked(self, view: EventStateView) -> EventStateView:
        """A state read, with the stop conditions checked."""
        grant = own_grant(view, self._principal)
        if view.episode_status == "closed":
            raise _Stop("the episode is closed")
        if view.clock >= view.goal.hard_end:
            raise _Stop(f"the event window ended at {self._t(view.goal.hard_end, view)}")
        if grant is None:
            raise _Stop(f"no grant is visible for {self._principal}")
        if not grant.valid_now:
            raise _Stop(f"grant {grant.grant.grant_id} is not valid now")
        self._goal_version = view.goal.version
        return view

    def _next_view(self, run: _Run, outcomes: list[_Outcome]) -> EventStateView:
        """The state after a turn's calls: the model's own state read when it was the turn's
        last sent call (no second read), else a fresh one."""
        last = next((o for o in reversed(outcomes) if o.refused is None), None)
        env = last.envelope if last is not None and last.tool == "get_event_state" else None
        if env is not None and env.status == "succeeded" and env.data is not None:
            return self._checked(EventStateView.model_validate(env.data))
        return self._refresh(run)

    def _observe(
        self, view: EventStateView, run: _Run, *, refresh: bool = False
    ) -> ToolEnvelope | None:
        """The turn's observation: the state and the planner's current evaluation, read with
        the same ``evaluate_candidates`` the selective policy reads before each choice (the
        read's envelope, or None when the evaluation is current). ``refresh`` (a timed wake)
        also reads it again when it was made at an earlier scenario time at the same revision.
        The model can still call it itself (with hypotheses, for example)."""
        ev = self._evaluation
        if (
            ev is not None
            and (ev.revision, ev.goal_version) == (view.revision, view.goal.version)
            and not (refresh and ev.evaluated_at < view.clock)
        ):
            return None
        if "evaluate_candidates" not in self._tools(view):
            return None
        envelope = self._read(run, "evaluate_candidates", {})
        run.read_refs.append(envelope.call_id)
        if envelope.status == "succeeded" and envelope.data is not None:
            self._evaluation = EvaluationResult.model_validate(envelope.data)
        return envelope

    def _tools(self, view: EventStateView) -> tuple[str, ...]:
        """The coordinator grant's tools, the staff attestations excepted (no grant of this
        principal lists them; the executor would refuse them anyway)."""
        grant = own_grant(view, self._principal)
        allowed = grant.grant.allowed_tools if grant is not None else ()
        return tuple(t for t in allowed if t not in STAFF_TOOLS)

    def _execute_calls(
        self, view: EventStateView, run: _Run, output: TurnOutput, response: ModelResponse
    ) -> list[_Outcome]:
        self._history.extend(self._results)
        self._history = self._history[-MAX_RESULTS_SHOWN:]
        self._results = []
        choice = self._choice(view, output, response)
        tools = self._tools(view)
        outcomes: list[_Outcome] = []
        for index, spec in enumerate(output.calls):
            if index >= MAX_CALLS_PER_TURN:
                outcome = _Outcome(
                    spec.tool,
                    spec.arguments_json[:300],
                    refused=f"at most {MAX_CALLS_PER_TURN} calls run per turn",
                )
            else:
                outcome = self._one_call(view, run, spec, tools)
            outcomes.append(outcome)
            self._results.append(self._summary(outcome, view))
            self._narrate(view, run, outcome, choice)
            if outcome.refused is None and outcome.tool in MUTATIONS and not outcome.applied:
                break  # a rejected mutation ends the turn's sequence
        return outcomes

    def _one_call(
        self, view: EventStateView, run: _Run, spec: CallSpec, tools: tuple[str, ...]
    ) -> _Outcome:
        tool = spec.tool.strip()
        if tool not in tools:
            return _Outcome(
                tool[:64],
                spec.arguments_json[:300],
                refused=f"{tool[:64]!r} is not a tool of this grant ({', '.join(tools)})",
            )
        try:
            arguments = json.loads(spec.arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return _Outcome(tool, spec.arguments_json[:300], refused=f"arguments_json: {exc.msg}")
        except (ValueError, RecursionError):
            return _Outcome(tool, spec.arguments_json[:300], refused="arguments_json: not parsable")
        if not isinstance(arguments, dict):
            return _Outcome(
                tool, spec.arguments_json[:300], refused="arguments_json: not an object"
            )
        if tool not in MUTATIONS:
            envelope = self._read(run, tool, arguments)
            run.read_refs.append(envelope.call_id)
            if tool == "evaluate_candidates" and envelope.status == "succeeded" and envelope.data:
                ev = EvaluationResult.model_validate(envelope.data)
                if not ev.hypothetical:
                    self._evaluation = ev
            return _Outcome(tool, arguments, envelope, envelope.receipt, (envelope.call_id,))
        if run.mutations_blocked:
            return _Outcome(tool, arguments, refused=BLOCKED)
        return self._mutate(view, run, tool, arguments)

    def _mutate(
        self, view: EventStateView, run: _Run, tool: str, arguments: dict[str, Any]
    ) -> _Outcome:
        """One mutation at the latest observed revision; a lost response is reconciled with
        ``get_action_receipt`` and the original key (at most ``MAX_RECEIPT_LOOKUPS`` lookups
        and one identical retry)."""
        revision = self._revision if self._revision is not None else view.revision
        goal_version = self._goal_version if tool == "apply_plan" else None
        key = idempotency_key(revision, tool, arguments)

        def send() -> ToolEnvelope:
            return self._call(
                run,
                tool,
                arguments,
                idempotency_key=key,
                expected_revision=revision,
                expected_goal_version=goal_version,
            )

        try:
            envelope = send()
            return _Outcome(tool, arguments, envelope, envelope.receipt, (envelope.call_id,), key)
        except TransportLost:
            pass
        calls: list[str] = []
        retried = False
        lookups = 0
        for _ in range(MAX_RECEIPT_LOOKUPS):
            lookups += 1
            try:
                lookup = self._call(run, "get_action_receipt", {"idempotency_key": key})
            except TransportLost:
                continue
            calls.append(lookup.call_id)
            data = lookup.data or {}
            if lookup.status == "succeeded" and data.get("lookup_status") == "found":
                receipt = ActionReceipt.model_validate(data["receipt"])
                return _Outcome(
                    tool, arguments, lookup, receipt, tuple(calls), key, reconciled=True
                )
            if retried:
                continue
            retried = True
            try:
                envelope = send()
                calls.append(envelope.call_id)
                return _Outcome(
                    tool, arguments, envelope, envelope.receipt, tuple(calls), key, reconciled=True
                )
            except TransportLost:
                continue
        run.mutations_blocked = True
        retry = "one identical retry" if retried else "no retry"
        self._record(
            run,
            "reconcile",
            f"The response to {tool} (key {key}) was lost and its outcome could not be "
            f"established after {lookups} receipt lookup(s) and {retry}; no further mutation "
            "is made in this run.",
            tool_call_refs=tuple(calls),
            details={"failure": "lost_response", "idempotency_key": key, "tool": tool},
        )
        return _Outcome(tool, arguments, None, None, tuple(calls), key, refused="lost response")

    # ------------------------------------------------------------------ narration

    def _narrate(
        self, view: EventStateView, run: _Run, o: _Outcome, choice: dict[str, Any]
    ) -> None:
        """Record what a state-changing or verifying call did, from its envelope or receipt.
        Reads are cited by the next decision."""
        if o.tool not in REFRESHING and o.refused is None:
            return
        if o.refused == "lost response":
            return  # the reconcile decision says it
        base: dict[str, Any] = {"choice": choice, "tool": o.tool}
        refs = (*run.read_refs, *o.call_ids)
        run.read_refs = []
        if o.refused is not None:
            # After a lost outcome a valid request is refused too: that is not the model's error.
            failure = "lost_response" if o.refused == BLOCKED else "invalid_choice"
            self._record(
                run,
                "wait",
                f"The model's {o.tool} request was refused before any call ({o.refused}); "
                f"nothing was sent and plan v{view.plan.plan_version} is unchanged.",
                tool_call_refs=refs,
                details=base | {"failure": failure, "problem": o.refused[:300]},
            )
            return
        args = o.arguments if isinstance(o.arguments, dict) else {}
        if o.tool == "query_status":
            record = None
            data = o.envelope.data if o.envelope is not None else None
            if o.envelope is not None and o.envelope.status == "succeeded" and data:
                observation = data.get("observation")
                record = ObservationRecord.model_validate(observation) if observation else None
            text = _status_text(o.envelope, record, view) if o.envelope else "no response"
            self._record(
                run,
                "verify",
                f"Checked {args.get('entity_id')} {args.get('fact')}: {text}.",
                observation_refs=(record.observation.observation_id,) if record else (),
                tool_call_refs=refs,
                details=base
                | {
                    "entity_id": args.get("entity_id"),
                    "fact": args.get("fact"),
                    "outcome": o.envelope.status if o.envelope else None,
                    "error_code": o.error_code,
                },
            )
            return
        receipt_refs = (o.receipt.receipt_id,) if o.receipt is not None else ()
        base |= {"idempotency_key": o.key, "reconciled": o.reconciled}
        if not o.applied:
            stale = o.error_code in STALE
            self._record(
                run,
                "wait",
                f"{o.tool} was rejected ({o.error_code}); "
                + (
                    "the state changed since it was read, so the model re-evaluates. "
                    if stale
                    else ""
                )
                + f"Plan v{view.plan.plan_version} is unchanged.",
                receipt_refs=receipt_refs,
                tool_call_refs=refs,
                details=base
                | {"error_code": o.error_code}
                | ({"failure": "stale_revision"} if stale else {}),
            )
            return
        assert o.receipt is not None
        self._note_applied(view, o, args)
        summary = o.receipt.summary[:300]
        data = o.envelope.data if o.envelope is not None else None
        hold = data.get("hold") if isinstance(data, dict) else None
        hold_id = hold.get("hold_id") if isinstance(hold, dict) else None
        if o.tool == "apply_plan":
            kind: DecisionKind = "commit"
            text = (
                f"Applied candidate {args.get('candidate_plan_id')} (report "
                f"{args.get('constraint_report_ref')}), revision {o.receipt.revision_before} -> "
                f"{o.receipt.revision_after}: {summary}"
            )
            extra: dict[str, Any] = {"report_id": args.get("constraint_report_ref")}
        elif o.tool == "release_hold":
            kind, text = "release", f"Released hold {args.get('hold_id')}: {summary}"
            extra = {"hold_id": args.get("hold_id")}
        elif args.get("purpose") == "stock_transfer":
            kind = "ask"
            text = (
                f"Asked staff for a handoff from {args.get('resource_id')} into "
                f"{args.get('destination_resource_id')}: hold {hold_id} (the local staff task) "
                f"reserves {args.get('quantity')} units and moves nothing; only a staff-recorded "
                "receipt moves stock."
            )
            extra = {"ask": "stock_handoff", "hold_id": hold_id}
        else:
            kind = "prepare"
            text = f"Held {args.get('resource_id')} for {args.get('activity_id')}: {summary}"
            extra = {"hold_id": hold_id}
        self._record(
            run,
            kind,
            text,
            candidate_refs=tuple(
                c for c in (args.get("candidate_plan_id"),) if isinstance(c, str) and c
            ),
            receipt_refs=receipt_refs,
            tool_call_refs=refs,
            details=base | extra,
        )

    def _note_applied(self, view: EventStateView, o: _Outcome, args: dict[str, Any]) -> None:
        """The attention rule's memory of applied requests, kept as P2 keeps it: holds per
        (resource, activity, grant version), and the open request an apply or release closes."""
        ask = self._open_ask
        if o.tool == "apply_plan":
            ev = self._evaluation
            cand = next(
                (
                    c
                    for c in (ev.candidates if ev is not None else ())
                    if c.candidate_id == args.get("candidate_plan_id")
                ),
                None,
            )
            if ask is not None and cand is not None and cand.signature == ask.signature:
                self._open_ask, self._wake = None, None
        elif o.tool == "release_hold":
            if ask is not None and args.get("hold_id") in ask.hold_ids:
                self._open_ask, self._wake = None, None
        elif o.tool == "hold_resource" and args.get("purpose") != "stock_transfer":
            grant = own_grant(view, self._principal)
            rid, aid = args.get("resource_id"), args.get("activity_id")
            if grant is not None and isinstance(rid, str) and isinstance(aid, str):
                key = (rid, aid, grant.version)
                self._hold_counts[key] = self._hold_counts.get(key, 0) + 1

    def _finish(
        self, view: EventStateView, run: _Run, output: TurnOutput, response: ModelResponse
    ) -> None:
        """Record the decision the model ended its turn with (server-composed summary)."""
        choice = self._choice(view, output, response)
        refs = tuple(run.read_refs)
        run.read_refs = []
        now = self._now(view)
        wait_until = None
        if output.wait_minutes is not None and output.wait_minutes >= 1:
            wait_until = now + timedelta(minutes=min(output.wait_minutes, MAX_WAIT_MINUTES))
            self._model_wake = wait_until
            digest = _digest(view)
            self._wake_repeat = digest == self._wait_digest
            self._wait_digest = digest
        decision = output.decision
        self._ended_with = decision
        if decision == "infeasible":
            self._observe(view, run)  # its shortfall names the state it ends on
            refs = (*refs, *run.read_refs)
            run.read_refs = []
        asked: tuple[AuthorizationRequest | None, CandidateResult | None, str] = (None, None, "")
        if decision == "ask":
            # Checked against the state the ask is made in: the turn's own calls (a hold made
            # in the same turn) may have moved it since the turn's evaluation.
            asked = self._ask_request(view, run, output)
            refs = (*refs, *run.read_refs)
            run.read_refs = []
        ev = self._evaluation
        observed = _visible_ids(view)
        obs_refs = tuple(r for r in choice["cited_refs"] if r in observed)
        kind = _FINAL_KIND[decision]
        details: dict[str, Any] = {"choice": choice, "final_decision": decision}
        if ev is not None:
            details["evaluation_id"] = ev.evaluation_id
        if decision == "ask":
            request, cand, problem = asked
            if request is None or cand is None:
                self._record(
                    run,
                    "wait",
                    f"The model's authorization request was not usable ({problem}); nothing was "
                    f"asked and plan v{view.plan.plan_version} is unchanged.",
                    tool_call_refs=refs,
                    details=details | {"failure": "invalid_choice", "problem": problem},
                )
                return
            self._record(
                run,
                "ask",
                f"Asked the organizer to raise {request.field} of {request.target_grant_id} from "
                f"{request.current_value} to {request.requested_value} cents so candidate "
                f"{request.candidate_id} can commit {request.resource_id}.",
                candidate_refs=(request.candidate_id,),
                observation_refs=obs_refs,
                tool_call_refs=refs,
                authorization_request=request,
                wait_until=wait_until,
                details=details,
            )
            self._remember_ask(view, request, cand)
            return
        if decision == "infeasible" and ev is not None and ev.infeasibility is not None:
            details["blocking_constraints"] = list(ev.infeasibility.blocking_constraints)
        elif decision == "infeasible" and ev is not None and (short := shortfalls(ev)):
            # A stock plan that covers only part of a target: named as P0 and P2 name it.
            details["blocking_constraints"] = sorted(
                {n for s in short for n in s.blocking_constraints}
            )
            details["shortfalls"] = [s.details() for s in short]
        latest = (
            f"; latest evaluation {ev.evaluation_id} at revision {ev.revision}: "
            f"{sum(1 for c in ev.candidates if c.rank is not None)} feasible, "
            f"{sum(1 for c in ev.candidates if c.applicable_now)} applicable now"
            if ev is not None
            else "; no evaluation was made"
        )
        until = f"; it looks again at {self._t(wait_until, view)}" if wait_until else ""
        self._record(
            run,
            kind,
            f"The tool-use agent ended its turn with '{decision}' at revision {view.revision}: "
            f"plan v{view.plan.plan_version} stands{latest}{until}.",
            observation_refs=obs_refs,
            tool_call_refs=refs,
            wait_until=wait_until,
            details=details,
        )

    def _ask_request(
        self, view: EventStateView, run: _Run, output: TurnOutput
    ) -> tuple[AuthorizationRequest | None, CandidateResult | None, str]:
        """The organizer request the model asked for, checked against the grant and the
        evaluation of the state it is made in: only committed spending of this grant, for a
        stored candidate. When the turn's own calls moved the state since the evaluation the
        model read (a hold in the same turn), the state is evaluated again and the named
        candidate is checked as it stands there (the same signature)."""
        spec = output.ask
        grant = own_grant(view, self._principal)
        read = self._evaluation
        if spec is None:
            return None, None, "decision 'ask' without an ask"
        if grant is None or read is None:
            return None, None, "no grant or evaluation to ask against"
        named: CandidateResult | None = next(
            (c for c in read.candidates if c.candidate_id == spec.candidate_id), None
        )
        if named is None:
            return (
                None,
                None,
                f"candidate {spec.candidate_id[:64]!r} is not in the latest evaluation",
            )
        self._observe(view, run)
        ev = self._evaluation
        if ev is None or (ev.revision, ev.goal_version) != (view.revision, view.goal.version):
            return None, None, f"no evaluation of revision {view.revision} to ask against"
        cand = next((c for c in ev.candidates if c.signature == named.signature), None)
        if cand is None:
            return (
                None,
                None,
                (
                    f"candidate {named.candidate_id} ({named.label}) is not in the evaluation of "
                    f"revision {ev.revision}"
                ),
            )
        if spec.resource_id not in {r.definition.resource_id for r in view.resources}:
            return None, None, f"resource {spec.resource_id[:64]!r} is not registered"
        missing = cand.authorization.missing
        if cand.constraint_status != "feasible_under_assumptions" or not missing:
            return (
                None,
                None,
                f"candidate {cand.candidate_id} is not feasible and short of authority",
            )
        if any(m.kind != "committed_spend_limit" for m in missing):
            return None, None, f"candidate {cand.candidate_id} lacks more than committed spending"
        if spec.resource_id not in {rh.resource_id for rh in cand.required_holds}:
            return None, None, f"{spec.resource_id[:64]!r} is not a booking of {cand.candidate_id}"
        current = grant.grant.max_total_committed_cents
        need = grant.committed_used_cents + cand.incremental_committed_cents
        if not current < spec.requested_value <= need:
            return (
                None,
                None,
                (
                    f"requested {spec.requested_value} is not above the current {current} and "
                    f"at most the {need} the candidate needs"
                ),
            )
        content = sha256_hex(
            canonical_json([grant.version, spec.resource_id, spec.requested_value])
        )[:8]
        request = AuthorizationRequest(
            # The request's content is part of its id: a corrected ask is a new request.
            request_id=f"authreq_r{ev.revision}_{cand.signature[:8]}_{content}",
            target_grant_id=grant.grant.grant_id,
            field="max_total_committed_cents",
            current_value=current,
            requested_value=spec.requested_value,
            resource_id=spec.resource_id,
            candidate_id=cand.candidate_id,
            reason=ask_reason(
                grant.grant.grant_id, current, spec.requested_value, cand, spec.resource_id
            ),
        )
        return request, cand, ""

    def _remember_ask(
        self, view: EventStateView, request: AuthorizationRequest, cand: CandidateResult
    ) -> None:
        """The open request, as P2 keeps its own: the menu offers no repeat of it, and the
        wake schedule looks again before the holds that keep its candidate open lapse."""
        grant = own_grant(view, self._principal)
        if grant is None:
            return
        bound = tuple(rh.bound_hold_id for rh in cand.required_holds if rh.bound_hold_id)
        self._open_ask = OpenAsk(
            request=request, signature=cand.signature, grant_version=grant.version, hold_ids=bound
        )
        holds = {h.hold_id: h for h in view.holds}
        self._wake = self._ask_wake(view, [holds[h].expires_at for h in bound if h in holds])

    def _flush(self, run: _Run) -> None:
        if self._pending_calls and self._at is not None and self._revision is not None:
            self._record(
                run,
                "wait",
                "Model calls of this run are recorded here; no further decision was made.",
                details={"accounting_only": True},
            )

    def _record(
        self,
        run: _Run,
        kind: DecisionKind,
        summary: str,
        *,
        observation_refs: tuple[str, ...] = (),
        tool_call_refs: tuple[str, ...] = (),
        candidate_refs: tuple[str, ...] = (),
        receipt_refs: tuple[str, ...] = (),
        authorization_request: AuthorizationRequest | None = None,
        wait_until: datetime | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._at is None or self._revision is None:
            run.notes.append(f"{kind} not recorded: no scenario time or revision observed")
            return
        calls, self._pending_calls = self._pending_calls, []
        out = dict(details or {})
        out.setdefault("chosen_by", "model" if "choice" in out else "server")
        out["model"] = self._model_details(calls)
        out["prompts"] = {self._prompt.prompt_id: self._prompt.sha256}
        self._seq += 1
        run.decisions.append(
            PolicyDecision(
                decision_id=f"dec_{self._seq:04d}",
                policy_id=self.policy_id,
                at=self._at,
                revision=self._revision,
                kind=kind,
                summary=summary,
                observation_refs=tuple(dict.fromkeys(observation_refs)),
                tool_call_refs=tuple(dict.fromkeys(tool_call_refs)),
                candidate_refs=tuple(dict.fromkeys(candidate_refs)),
                receipt_refs=tuple(dict.fromkeys(receipt_refs)),
                authorization_request=authorization_request,
                wait_until=wait_until,
                details=out,
            )
        )

    def _model_details(self, calls: list[CallRecord]) -> dict[str, Any]:
        def total(name: str) -> int | None:
            values = [getattr(c, name) for c in calls if getattr(c, name) is not None]
            return sum(values) if values else None

        returned = sorted({c.model_id for c in calls if c.model_id})
        return {
            "requested_model": self.requested_model,
            "model_id": returned[-1] if len(returned) == 1 else (returned or None),
            "calls": [c.as_dict() for c in calls],
            "latency_ms": sum(c.latency_ms for c in calls),
            "prompt_tokens": total("prompt_tokens"),
            "completion_tokens": total("completion_tokens"),
            "total_tokens": total("total_tokens"),
            "cost_usd": round(sum(c.cost_usd for c in calls), 8),
            "episode": self.usage,
        }

    def _choice(
        self, view: EventStateView, output: TurnOutput, response: ModelResponse
    ) -> dict[str, Any]:
        known = _visible_ids(view) | set(response.record.consumed_tool_call_ids)
        ev = self._evaluation
        if ev is not None:
            known |= {ev.evaluation_id} | {c.candidate_id for c in ev.candidates}
            known |= {c.report_id for c in ev.candidates}
        return {
            "model_call_id": response.record.call_id,
            "decision": output.decision,
            "calls": [
                {"tool": c.tool[:64], "arguments_json": c.arguments_json[:300]}
                for c in output.calls[: MAX_CALLS_PER_TURN + 1]
            ],
            "rationale_untrusted": " ".join(output.rationale.split())[:MAX_RATIONALE_CHARS],
            "cited_refs": [r for r in dict.fromkeys(output.cited_refs) if r in known],
            "dropped_refs": [r[:64] for r in output.cited_refs if r not in known][:8],
            "consumed_tool_call_ids": list(response.record.consumed_tool_call_ids),
        }

    # ------------------------------------------------------------------ model

    def _turn(self, view: EventStateView, run: _Run) -> tuple[TurnOutput, ModelResponse] | None:
        """One model turn with one repair. None when the output stayed unusable (recorded)."""
        tools = self._tools(view)
        context = self._context(view, tools)
        consumed = tuple(r["tool_call_id"] for r in self._results if r.get("tool_call_id"))
        request = ModelRequest(
            purpose="tool_turn",
            system=self._prompt.system,
            user=self._prompt.render(
                state=context, observations=_observations(view, self._seen_notices)
            ),
            schema_name=SCHEMA_NAME,
            schema=turn_schema(tools),
            output_model=TurnOutput,
            max_tokens=TURN_MAX_TOKENS,
            context=context,
            call_id=self._next_call_id(),
            consumed_tool_call_ids=consumed,
            prompt_id=self._prompt.prompt_id,
        )
        problem, failure = "", "malformed_output"
        for attempt in (1, 2):
            try:
                response = self._call_model(request)
            except (ProviderMalformedJSON, ProviderSchemaViolation) as exc:
                problem, failure = exc.message, "malformed_output"
                if attempt == 1:
                    request = request.with_repair(
                        exc.raw_text, problem, call_id=self._next_call_id()
                    )
                continue
            assert isinstance(response.parsed, TurnOutput)
            output = response.parsed
            bad = _invalid(output, tools)
            if bad is None:
                self._mark_shown(view)
                return output, response
            problem, failure = bad, "invalid_choice"
            if attempt == 1:
                request = request.with_repair(
                    response.raw_text, problem, call_id=self._next_call_id()
                )
        self._results = []
        self._mark_shown(view)  # read, though its reply was unusable (P2: ``malformed_output``)
        self._record(
            run,
            "wait",
            f"The model's turn was not usable after the one repair attempt ({problem[:200]}); "
            f"no action is taken and plan v{view.plan.plan_version} is unchanged.",
            tool_call_refs=tuple(run.read_refs),
            details={"failure": failure, "problem": problem[:400]},
        )
        run.read_refs = []
        return None

    def _call_model(self, request: ModelRequest) -> ModelResponse:
        if self._model_calls >= self.max_model_calls:
            raise _Halt(
                "model_call_cap",
                f"the model-call cap of {self.max_model_calls} for this episode is spent",
            )
        self._model_calls += 1
        try:
            response = self._provider.complete(request)
        except (ProviderMalformedJSON, ProviderSchemaViolation) as exc:
            self._note_call(exc.record)
            raise
        except SpendCapReached as exc:
            self._model_calls -= 1  # refused before sending: no model call happened
            self._note_call(exc.record)
            raise _Halt("spend_cap", exc.message) from None
        except ProviderConfigError as exc:
            self._model_calls -= 1
            self._note_call(exc.record)
            raise _Halt("provider_config", exc.message) from None
        except ProviderError as exc:
            self._note_call(exc.record)
            failure: Failure = "provider_timeout" if exc.kind == "timeout" else "provider_error"
            raise _ModelFailed(failure, exc) from None
        self._note_call(response.record)
        return response

    def _note_call(self, record: CallRecord | None) -> None:
        if record is None:
            return
        self._pending_calls.append(record)
        self._cost_usd += record.cost_usd

    def _next_call_id(self) -> str:
        self._call_seq += 1
        return f"mc_{self._call_seq:04d}"

    # ------------------------------------------------------------------ prompt context

    def _context(self, view: EventStateView, tools: tuple[str, ...]) -> dict[str, Any]:
        """The visible state as the model reads it (everything is data)."""
        grant = own_grant(view, self._principal)
        lifecycles = {a.definition.activity_id: a.lifecycle for a in view.activities}

        def t(value: datetime | None) -> str | None:
            return self._t(value, view) if value is not None else None

        def window(w: Any) -> dict[str, Any]:
            return {
                "local": f"{t(w.start)}-{t(w.end)}",
                "start": _iso(w.start),
                "end": _iso(w.end),
            }

        ev = self._evaluation
        evaluation = None
        if ev is not None:
            shown = list(ev.candidates[:MAX_CANDIDATES_SHOWN])
            evaluation = {
                "evaluation_id": ev.evaluation_id,
                "revision": ev.revision,
                "goal_version": ev.goal_version,
                "keep_candidate_id": ev.keep_candidate_id,
                "best_candidate_id": ev.best_candidate_id,
                "best_applicable_candidate_id": ev.best_applicable_candidate_id,
                "candidates": [
                    _candidate_context(c)
                    | {
                        "required_holds": [
                            {
                                "resource_id": rh.resource_id,
                                "activity_id": rh.activity_id,
                                "window": window(rh.window),
                                "bound_hold_id": rh.bound_hold_id,
                                "commitment_cost_cents": rh.commitment_cost_cents,
                            }
                            for rh in c.required_holds
                        ],
                        "assignments": [
                            {
                                "activity_id": a.activity_id,
                                "window": window(a),
                                "resource_ids": list(a.resource_ids),
                            }
                            for a in c.assignments
                            if a.activity_id in c.changed_activity_ids
                            or c.required_stock_holds
                            or c.stock_transfers
                        ],
                        "service_target_ids": sorted(
                            {h.service_target_id for h in c.required_stock_holds}
                        ),
                    }
                    for c in shown
                ],
                "not_shown": max(len(ev.candidates) - len(shown), 0),
                "infeasibility": (
                    ev.infeasibility.model_dump(mode="json") if ev.infeasibility else None
                ),
            }
        out: dict[str, Any] = {
            "event": {
                "event_id": view.event_id,
                "profile_id": view.profile_id,
                "timezone": view.timezone,
                "now_local": t(self._now(view)),
                "now_utc": _iso(self._now(view)),
                "hard_end_local": t(view.goal.hard_end),
                "revision": view.revision,
                "goal_version": view.goal.version,
                "goal": view.goal.description,
                "required_activity_ids": list(view.goal.required_activity_ids),
            },
            "activities": [
                {
                    "activity_id": a.definition.activity_id,
                    "lifecycle": lifecycles.get(a.definition.activity_id),
                    "window": window(a.definition.window),
                    "duration_minutes": a.definition.duration_minutes,
                    "predecessors": list(a.definition.predecessors),
                    "required_resources": list(a.definition.required_resources),
                    "required": a.definition.required,
                }
                for a in view.activities
            ],
            "plan": {
                "plan_version": view.plan.plan_version,
                "assignments": [
                    {
                        "activity_id": a.activity_id,
                        "window": window(a),
                        "resource_ids": list(a.resource_ids),
                        "consumable_allocations": [
                            c.model_dump(mode="json") for c in a.consumable_allocations
                        ],
                    }
                    for a in sorted(view.plan.assignments, key=lambda x: x.start)
                ],
            },
            "resources": [
                {
                    "resource_id": r.definition.resource_id,
                    "kind": r.definition.kind,
                    "status": r.status,
                    "status_basis": r.status_basis,
                    "status_observed_local": t(r.status_observed_at),
                    "reported_eta_local": t(r.reported_eta),
                    "window": window(r.definition.window),
                    "capabilities": list(r.definition.capabilities),
                    "approved_substitute_ids": list(r.definition.approved_substitute_ids),
                    "terms": r.definition.terms.model_dump(
                        mode="json", exclude={"terms_source_ref"}
                    ),
                }
                for r in view.resources
            ],
            "status_sources": [s.model_dump(mode="json") for s in view.status_sources],
            "status_checks": [
                {
                    "call_id": c.call_id,
                    "entity_id": c.entity_id,
                    "fact": c.fact,
                    "requested_local": t(c.requested_at),
                    "status": c.envelope_status,
                    "observation_id": c.observation_id,
                    "stale": c.stale,
                    "by_you": c.actor_id == self._principal,
                }
                for c in view.status_checks[-10:]
            ],
            "your_holds": [
                {
                    "hold_id": h.hold_id,
                    "resource_id": h.resource_id,
                    "activity_id": h.activity_id,
                    "window": window(h.window),
                    "status": h.effective_status,
                    "expires_local": t(h.expires_at),
                    "reserved_cents": h.reserved_cents,
                    "quantity": h.remaining_quantity if h.consumable else h.quantity,
                    "purpose": h.purpose,
                }
                for h in view.holds
                if h.actor_id == self._principal
            ],
            "commitments": [
                {
                    "commitment_id": c.commitment_id,
                    "resource_id": c.resource_id,
                    "activity_id": c.activity_id,
                    "committed_cents": c.committed_cents,
                }
                for c in view.commitments
            ],
            "checkins": [
                {
                    "resource_id": c.resource_id,
                    "at_local": t(c.at),
                    "available_local": f"{t(c.available.start)}-{t(c.available.end)}",
                }
                for c in view.checkins
            ],
            "grant": (
                {
                    "grant_id": grant.grant.grant_id,
                    "version": grant.version,
                    "allowed_tools": list(tools),
                    "resource_ids": list(grant.grant.resource_ids),
                    "activity_ids": list(grant.grant.activity_ids),
                    "max_total_committed_cents": grant.grant.max_total_committed_cents,
                    "committed_used_cents": grant.committed_used_cents,
                    "max_total_reserved_cents": grant.grant.max_total_reserved_cents,
                    "reserved_used_cents": grant.reserved_used_cents,
                    "expires_local": t(grant.grant.expires_at),
                }
                if grant is not None
                else None
            ),
            "budget": view.budget.model_dump(mode="json"),
            "tool_durations_minutes": dict(view.tool_durations_minutes),
            "latest_evaluation": evaluation,
            "your_recent_decisions": [
                {"kind": d.kind, "at_local": t(d.at), "summary": d.summary[:240]}
                for d in view.decisions
                if d.policy_id == self.policy_id
            ][-MAX_DECISIONS_SHOWN:],
            "earlier_tool_results": list(self._history),
            "last_tool_results": list(self._results),
            "caps_left": {
                "model_calls": self.max_model_calls - self._model_calls,
                "tool_calls": self.max_tool_calls - self._tool_calls,
            },
        }
        if view.stock is not None:
            out["stock"] = _stock_context(view, self._principal)
            out["stock_options"] = [o.model_dump(mode="json") for o in view.stock_options]
        return out

    def _summary(self, o: _Outcome, view: EventStateView) -> dict[str, Any]:
        """A tool result as the next turn sees it."""
        env = o.envelope
        out: dict[str, Any] = {
            "tool_call_id": env.call_id if env is not None else None,
            "tool": o.tool,
            "arguments": o.arguments,
            "status": env.status if env is not None else "not_sent",
            "error_code": o.error_code,
            "refused": o.refused,
        }
        if env is not None and env.error is not None:
            out["error_message"] = env.error.message[:300]
        if o.receipt is not None:
            out |= {
                "receipt_id": o.receipt.receipt_id,
                "receipt_status": o.receipt.status,
                "revision_after": o.receipt.revision_after,
                "summary": o.receipt.summary[:300],
                "reconciled": o.reconciled,
            }
        data = env.data if env is not None else None
        if o.tool == "query_status" and env is not None:
            record = None
            if env.status == "succeeded" and data and data.get("observation"):
                record = ObservationRecord.model_validate(data["observation"])
            out["summary"] = _status_text(env, record, view)
        elif o.tool == "evaluate_candidates" and data:
            out["summary"] = (
                f"evaluation {data.get('evaluation_id')} at revision {data.get('revision')}"
                " (see latest_evaluation)"
                if not data.get("hypothetical")
                else f"hypothetical evaluation {data.get('evaluation_id')} (what-if only, never "
                "applicable; apply the candidate with the same label from latest_evaluation): "
                + "; ".join(
                    _what_if(c) for c in (data.get("candidates") or [])[:MAX_CANDIDATES_SHOWN]
                )
            )
        elif o.tool == "hold_resource" and data and isinstance(data.get("hold"), dict):
            hold = data["hold"]
            out["hold"] = {
                k: hold.get(k)
                for k in ("hold_id", "resource_id", "activity_id", "expires_at", "quantity")
            }
        elif o.tool == "list_resources" and data:
            out["summary"] = json.dumps(data, sort_keys=True, default=str)[:1500]
        elif o.tool == "get_event_state" and env is not None:
            out["summary"] = f"state at revision {env.revision} (shown in this prompt)"
        return out


# ---------------------------------------------------------------------------------- factory


def tool_use_policy_factory(
    config: ModelConfig | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_model_calls: int = DEFAULT_MAX_MODEL_CALLS,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ledger_path: Path | None = None,
    seed: int | None = None,
) -> Callable[[], ToolUsePolicy]:
    """One provider and spend guard per instance (episode), and the run's ``seed``, as for
    the live policy."""
    cfg = config or load_model_config()
    ledger = SpendLedger(ledger_path or cfg.ledger_path)

    def make() -> ToolUsePolicy:
        guard = SpendGuard(
            ledger,
            max_run_usd=cfg.max_run_cost_usd,
            max_total_usd=cfg.max_total_cost_usd,
            run_id=f"tool-use-{uuid.uuid4().hex[:12]}",
        )
        provider = OpenAICompatibleProvider(cfg, guard, timeout_s=timeout_s, seed=seed)
        return ToolUsePolicy(
            provider, max_model_calls=max_model_calls, max_tool_calls=max_tool_calls
        )

    return make


# ---------------------------------------------------------------------------------- helpers


def _invalid(output: TurnOutput, tools: tuple[str, ...]) -> str | None:
    """Server-side validation of a turn: a decision outside the list, or a tool outside the
    grant (refused before any call), asks for the one repair."""
    if output.decision not in DECISIONS:
        return f"decision {output.decision[:40]!r} is not one of {', '.join(DECISIONS)}"
    for spec in output.calls:
        if spec.tool.strip() not in tools:
            return f"tool {spec.tool[:64]!r} is not available; the grant allows {', '.join(tools)}"
    return None


def _what_if(c: dict[str, Any]) -> str:
    """One hypothetical candidate as a turn reads it: id, label, status and failed checks."""
    failed = [k.get("constraint_id") for k in c.get("checks") or [] if k.get("status") == "failed"]
    status = f"{c.get('candidate_id')} {c.get('label')!r} {c.get('constraint_status')}"
    return status + (f" failing {', '.join(map(str, failed))}" if failed else "")


def _news(o: _Outcome, seen: set[str]) -> bool:
    """A sent call whose result the model has not seen: a status answer with a new observation,
    or a rejection with a new receipt."""
    if o.refused is not None or o.envelope is None:
        return False
    data = o.envelope.data or {}
    if o.tool == "query_status":
        record = data.get("observation") if o.envelope.status == "succeeded" else None
        observation = record.get("observation") if isinstance(record, dict) else None
        oid = observation.get("observation_id") if isinstance(observation, dict) else None
        return isinstance(oid, str) and oid not in seen
    if o.tool in MUTATIONS and not o.applied:
        return o.receipt is not None and o.receipt.receipt_id not in seen
    return False


def _moved(o: _Outcome) -> bool:
    """Whether the server state may have changed (or been read anew) through this call: a sent
    mutation or status check, a state read, or a mutation whose outcome was lost."""
    if o.refused == "lost response":
        return True
    return o.refused is None and (o.tool in REFRESHING or o.tool == "get_event_state")


def _digest(view: EventStateView) -> str:
    """What a new model turn depends on. Clock ticks, activity starts and completions alone
    leave it unchanged; a failed activity, a new observation, a grant or goal version, a hold
    or commitment, stock or a staff task does not."""
    stock = view.stock
    return sha256_hex(
        canonical_json(
            [
                view.plan.plan_version,
                view.goal.version,
                [r.observation.observation_id for r in view.observations],
                [(g.grant.grant_id, g.version, g.valid_now) for g in view.grants],
                [(h.hold_id, h.effective_status, h.remaining_quantity) for h in view.holds],
                [c.commitment_id for c in view.commitments],
                sorted(
                    a.definition.activity_id
                    for a in view.activities
                    if a.lifecycle in ("failed", "canceled")
                ),
                (
                    [
                        [
                            (b.resource_id, b.on_hand_quantity, b.reserved_quantity)
                            for b in stock.balances
                        ],
                        [(t.hold_id, t.status) for t in stock.handoff_tasks],
                        [d.distribution_id for d in stock.distributions],
                    ]
                    if stock is not None
                    else None
                ),
            ]
        )
    )


def _observations(view: EventStateView, shown: set[str] | None = None) -> list[dict[str, Any]]:
    """Visible observations, newest last, as quoted data with their source timestamps: the
    latest ``MAX_OBSERVATIONS_SHOWN``, and every older notice not in ``shown`` (no notice
    reaches a decision unread)."""
    latest = view.observations[-MAX_OBSERVATIONS_SHOWN:]
    older = [
        r
        for r in view.observations[: -MAX_OBSERVATIONS_SHOWN or None]
        if shown is not None
        and r.observation.kind in NOTICE_KINDS
        and r.observation.observation_id not in shown
    ]
    out: list[dict[str, Any]] = []
    for record in [*older, *latest]:
        obs = record.observation
        facts = record.structured
        out.append(
            {
                "observation_id": obs.observation_id,
                "kind": obs.kind,
                "entity_id": obs.entity_id,
                "source_id": obs.source_id,
                "channel": record.channel,
                "observed_local": local_label(obs.observed_at, view.timezone),
                "received_local": local_label(obs.received_at, view.timezone),
                "correlation_group": obs.correlation_group,
                "supersedes": list(obs.supersedes),
                "authority_scope": obs.authority_scope,
                "text": obs.text,
                "structured": facts.model_dump(mode="json") if facts is not None else None,
            }
        )
    return out


def _visible_ids(view: EventStateView) -> set[str]:
    known = {r.observation.observation_id for r in view.observations}
    known |= {r.receipt_id for r in view.receipts}
    known |= {c.call_id for c in view.status_checks}
    known |= {h.hold_id for h in view.holds}
    return known


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
