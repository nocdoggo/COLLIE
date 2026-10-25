"""Live coordinator policy ``live/1.0.0`` (Wave 2, W2.1): a bounded model-driven loop.

The policy implements ``evaluation/policies/base.py`` ``Policy`` and sees only tool envelopes
through a ``ToolClient``. One ``run`` follows the decision-policy loop:

1. read the state (stop when the event is over, the episode closed or the grant not valid);
2. interpret new notices with the model into planning ``change_spec`` records (``interpret``),
   every entity validated against public state;
3. ``evaluate_candidates``, and when verification of a weighed claim failed, again with the
   claimed outcome as a hypothesis, keeping only candidates feasible under both;
4. build the closed menu (``menu``) from that state and evaluation; the model picks ONE
   ``option_id`` (keep, query, hold, apply, ask, release, wait). An id outside the menu is
   rejected; a menu without a real choice (only keep and wait) needs no model call;
5. execute the option through the ``ToolClient`` with one deterministic idempotency key per
   intended request, and feed the real tool result to the next model call;
6. stop or wait.

Caps (per episode, on the instance; the host keeps one instance per episode): at most
``max_model_calls`` model calls (repairs and failed calls count) and ``max_tool_calls`` tool
calls (failed calls, retries and receipt lookups count). The per-run ``max_tool_calls`` passed
to ``run`` still applies. Within a run at most ``MAX_STEPS`` model-chosen steps run.

Failures are decisions, never invented successes: malformed output after the one repair
(``unresolved`` notice, or ``wait``), an unknown entity (``unresolved``), an exhausted cap, the
spend cap or a configuration failure (``stop``), a provider timeout or error (``wait``, retried
after ``PROVIDER_RETRY``), a stale revision (re-read and re-evaluate, at most
``MAX_STALE_RETRIES`` per run) and a lost mutation response (reconciled with
``get_action_receipt`` and the original key, ``reconcile`` when it cannot be established).

On a consumable (pantry) profile the menu also offers the stock options of ``menu``: a staff
handoff request (a ``stock_transfer`` hold, the local staff task), a quantity hold on a pool and
the apply of a stored stock candidate; the choice prompt is then ``choose_action_pantry.v1``.
The policy never calls a staff-only tool: staff record receipts and distributions. As the
deterministic baseline does, the server releases an own handoff hold once its staff task is no
longer open, and reports a kept plan that covers only part of a target as ``infeasible``
(naming what blocks better coverage) once nothing pursuable covers more.

Subclasses keep this downstream logic and change one step: ``_verify_first`` runs before each
decision step (the verify-all ablation, ``agent/policies/verify_all.py``, requests every relevant
status check there). Decisions and results carry the instance's ``policy_id``.

Every decision cites the observation, candidate, report, receipt and tool-call ids it rests
on. Its ``details.model`` records the requested model and, for each model call attributed to
it, the returned model id, latency, token usage and cost; ``details.chosen_by`` says whether the
model chose or the server recorded the only possible outcome. The model's rationale is kept in
``details.choice`` as untrusted text; summaries are composed by the server from facts.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from plan_b.agent.attention import (
    AttentionMixin,
    _assess,
    _candidate,
    _Evaluated,
    _ids,
    _lifecycles,
    _Watch,
)
from plan_b.agent.config import ModelConfig, load_model_config
from plan_b.agent.interpret import (
    INTERPRET_PROMPT,
    MAX_NOTICES_PER_CALL,
    LiveInterpretation,
    interpret_batch,
    new_notices,
    server_prefilter,
)
from plan_b.agent.menu import (
    Menu,
    MenuOption,
    OpenAsk,
    coverage_text,
    handoff_task,
    own_grant,
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
    ActionReceipt,
    AuthorizationRequest,
    CandidateResult,
    DecisionKind,
    EvaluationResult,
    EventStateView,
    HoldView,
    Hypothesis,
    ObservationRecord,
    PolicyDecision,
    PolicyRunResult,
    ReleaseHoldArgs,
    Strict,
    ToolEnvelope,
)
from plan_b.domain.timeutil import local_label
from plan_b.evaluation.policies.base import ToolClient, TransportLost
from plan_b.evaluation.policies.parser import normalize_text

POLICY_ID = "live/1.1.0"
CHOOSE_PROMPT = "choose_action.v1"
PANTRY_CHOOSE_PROMPT = "choose_action_pantry.v1"  # consumable profiles: the stock options
CHOOSE_SCHEMA_NAME = "plan_b_menu_choice"
DEFAULT_MAX_MODEL_CALLS = 8
DEFAULT_MAX_TOOL_CALLS = 32
MAX_STEPS = 6  # model-chosen steps in one run
MAX_INTERPRET_PASSES = 3  # a repeat in the same batch resolves on the second pass
MAX_STALE_RETRIES = 2
MAX_RECEIPT_LOOKUPS = 2
MAX_CANDIDATES_SHOWN = 8
MAX_RATIONALE_CHARS = 400
CHOOSE_MAX_TOKENS = MAX_OUTPUT_TOKENS  # one output limit for every call of P1-P3 (provider)
INTERPRET_MAX_TOKENS = MAX_OUTPUT_TOKENS
PROVIDER_RETRY = timedelta(minutes=2)
RETRYABLE_REJECTIONS = frozenset(
    {"REVISION_CONFLICT", "CANDIDATE_STALE", "GOAL_VERSION_CONFLICT", "HOLD_EXPIRED"}
)
# The only tools this policy ever sends. Staff attestations, organizer controls, check-ins and
# observation submission are absent: no menu option names them, and ``_Run.call`` refuses any
# other name before it reaches the client.
AGENT_TOOLS = frozenset(
    {
        "get_event_state",
        "get_action_receipt",
        "evaluate_candidates",
        "query_status",
        "hold_resource",
        "release_hold",
        "apply_plan",
    }
)
Failure = Literal[
    "malformed_output",
    "invalid_choice",
    "unknown_entity",
    "model_call_cap",
    "tool_call_cap",
    "spend_cap",
    "provider_timeout",
    "provider_error",
    "provider_config",
    "stale_revision",
    "lost_response",
]
Step = Literal["done", "refresh", "stale"]


def idempotency_key(revision: int, tool: str, arguments: dict[str, Any]) -> str:
    """``live-r<revision>-<tool>-<sha8(arguments)>``: one key per intended request, so a
    repeat of the same intent at the same revision is an idempotent retry."""
    return f"live-r{revision}-{tool}-{sha256_hex(canonical_json(arguments))[:8]}"


class ChooseOutput(Strict):
    """The model's choice (structured output)."""

    option_id: str
    rationale: str
    cited_refs: tuple[str, ...]


def choose_schema(option_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["option_id", "rationale", "cited_refs"],
        "properties": {
            "option_id": {"type": "string", "enum": list(option_ids)},
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
    """A stop condition of the event holds (event over, episode closed, grant not valid)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Halt(Exception):
    """A per-episode limit ends the policy for this episode (caps, spend, configuration)."""

    def __init__(self, failure: Failure, reason: str) -> None:
        super().__init__(reason)
        self.failure = failure
        self.reason = reason


class _ModelFailed(Exception):
    """A model call failed in a way the next wake may retry (timeout, HTTP, transport)."""

    def __init__(self, failure: Failure, error: ProviderError, stage: str) -> None:
        super().__init__(error.message)
        self.failure = failure
        self.error = error
        self.stage = stage


@dataclass
class _Mutation:
    envelope: ToolEnvelope | None
    receipt: ActionReceipt | None
    call_ids: tuple[str, ...]
    key: str
    reconciled: bool = False

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


@dataclass
class _Run:
    """Call accounting for one ``run``; the episode counters live on the policy."""

    policy: LivePolicy
    client: ToolClient
    max_calls: int
    calls: int = 0
    decisions: list[PolicyDecision] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mutations_blocked: bool = False
    rejected_intents: set[str] = field(default_factory=set)
    retry_at: datetime | None = None

    def call(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        expected_goal_version: int | None = None,
    ) -> ToolEnvelope:
        if tool not in AGENT_TOOLS:
            raise ValueError(f"the live policy never calls {tool}")
        policy = self.policy
        if policy._tool_calls >= policy.max_tool_calls:
            raise _Halt(
                "tool_call_cap",
                f"the tool-call cap of {policy.max_tool_calls} for this episode is spent",
            )
        if self.calls >= self.max_calls:
            raise _RunBudget
        self.calls += 1
        policy._tool_calls += 1
        envelope = self.client.call(
            tool,
            arguments=arguments,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_goal_version=expected_goal_version,
        )
        if envelope.scenario_time is not None:
            policy._at = envelope.scenario_time
        if envelope.revision is not None:
            policy._revision = envelope.revision
        return envelope

    def read(self, tool: str, arguments: dict[str, Any]) -> ToolEnvelope:
        """Reads have no side effect, so one lost response is retried once."""
        try:
            return self.call(tool, arguments)
        except TransportLost:
            try:
                return self.call(tool, arguments)
            except TransportLost as exc:
                raise _ReadLost from exc


# ---------------------------------------------------------------------------------- policy


def resume_spend(provider: ModelProvider, spent_usd: float) -> None:
    """Seed a rebuilt instance's spend guard with the episode's recorded model spend."""
    guard = getattr(provider, "guard", None)
    if isinstance(guard, SpendGuard):
        guard.run_spent_usd = max(guard.run_spent_usd, spent_usd)


class LivePolicy(AttentionMixin):
    """``live/1.0.0``: the model chooses among server-built options; the server executes."""

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
        self._choose_prompt: Prompt = load_prompt(CHOOSE_PROMPT)
        self._profile_checked = False
        self._interpret_prompt: Prompt = load_prompt(INTERPRET_PROMPT)
        self._seq = 0
        self._model_calls = 0
        self._tool_calls = 0
        self._call_seq = 0
        self._cost_usd = 0.0
        self._interps: dict[str, LiveInterpretation] = {}
        self._pending_calls: list[CallRecord] = []
        self._pending_interps: list[LiveInterpretation] = []
        self._pending_results: list[dict[str, Any]] = []
        self._recorded: set[tuple[Any, ...]] = set()
        self._release_failed: set[str] = set()  # stock-transfer holds whose release was rejected
        self._open_ask: OpenAsk | None = None
        self._hold_counts: dict[tuple[str, str, int], int] = {}
        self._own_keys: dict[str, str] = {}
        self._settled: tuple[int, int] | None = None
        self._wake: datetime | None = None
        self._watch: _Watch | None = None
        self._watch_offered: set[tuple[str, str, int]] = set()
        self._window: datetime | None = None
        self._halted: str | None = None
        self._principal = ""
        self._at: datetime | None = None
        self._revision: int | None = None

    @property
    def requested_model(self) -> str:
        return self._provider.requested_model

    @property
    def usage(self) -> dict[str, Any]:
        """Episode counters (model calls, tool calls, cost) for harnesses and records."""
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
        run = _Run(self, client, max_tool_calls)
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
            self._halt(run, halt)
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
            fresh = self._interpret_new(view, run)
        except _Stop as stop:
            self._record_stop(run, stop.reason)
            return "stopped", None
        except _ModelFailed as failed:
            self._record_model_failure(run, failed)
            return "waiting", run.retry_at
        now = self._now(view)
        woke_ask = self._wake is not None and now >= self._wake
        woke_watch = self._watch is not None and now >= self._watch.at
        woke_window = self._window is not None and now >= self._window
        force = self._settled is None or woke_ask or woke_watch or woke_window or fresh
        if not force and (view.revision, view.goal.version) == self._settled:
            return "waiting", self._compute_wait(view, now)
        stale = 0
        try:
            for _ in range(MAX_STEPS):
                view = self._verify_first(view, run)
                decided = (view.revision, view.goal.version)
                step = self._step(view, run, woke_watch)
                woke_watch = False
                self._settled = decided
                if step == "done":
                    break
                if step == "stale":
                    stale += 1
                    if stale > MAX_STALE_RETRIES:
                        self._record(
                            run,
                            "wait",
                            f"Stale-state rejections persisted after {MAX_STALE_RETRIES} "
                            f"re-reads in this run; plan v{view.plan.plan_version} is unchanged.",
                            details={"failure": "stale_revision", "retries": MAX_STALE_RETRIES},
                        )
                        break
                view = self._refresh(run)
                self._interpret_new(view, run)
            else:
                run.notes.append(f"step bound of {MAX_STEPS} reached; the next wake continues")
                run.retry_at = self._now(view)
        except _Stop as stop:
            self._record_stop(run, stop.reason)
            return "stopped", None
        except _ModelFailed as failed:
            self._record_model_failure(run, failed)
            self._settled = None
            return "waiting", run.retry_at
        now = self._now(view)
        wait_until = self._compute_wait(view, now)
        if run.retry_at is not None:
            wait_until = min(wait_until, run.retry_at) if wait_until else run.retry_at
        return "waiting", wait_until

    # ------------------------------------------------------------------ state and evidence

    def _refresh(self, run: _Run) -> EventStateView:
        envelope = run.read("get_event_state", {})
        if envelope.status != "succeeded" or envelope.data is None:
            code = envelope.error.code if envelope.error is not None else envelope.status
            raise _Stop(f"the state read was {envelope.status} ({code})")
        view = EventStateView.model_validate(envelope.data)
        if not self._profile_checked:
            self._profile_checked = True
            if view.stock is not None:
                self._choose_prompt = load_prompt(PANTRY_CHOOSE_PROMPT)
        grant = own_grant(view, self._principal)
        if view.episode_status == "closed":
            raise _Stop("the episode is closed")
        if view.clock >= view.goal.hard_end:
            raise _Stop(f"the event window ended at {self._t(view.goal.hard_end, view)}")
        if grant is None:
            raise _Stop(f"no grant is visible for {self._principal}")
        if not grant.valid_now:
            raise _Stop(f"grant {grant.grant.grant_id} is not valid now")
        return view

    def _interpret_new(self, view: EventStateView, run: _Run) -> bool:
        """Interpret every new notice; True when any was handled. Provider failures other
        than malformed output leave the notices for the next wake."""
        records = new_notices(view, list(self._interps))
        if not records:
            return False
        for _ in range(MAX_INTERPRET_PASSES):
            if not records:
                break
            done, to_model = server_prefilter(view, records, list(self._interps.values()))
            for interp in done:
                self._handle_interpretation(run, interp, view)
            # A repeat of a notice in the same batch waits for the original's reading, so the
            # next pass resolves it as a duplicate without a model call.
            firsts: list[ObservationRecord] = []
            records = []
            for record in to_model:
                lineage = _lineage(record)
                if any(_lineage(f) == lineage for f in firsts):
                    records.append(record)
                else:
                    firsts.append(record)
            while firsts:
                batch, firsts = firsts[:MAX_NOTICES_PER_CALL], firsts[MAX_NOTICES_PER_CALL:]
                results, _ = interpret_batch(
                    lambda r: self._call_model(replace(r, max_tokens=INTERPRET_MAX_TOKENS)),
                    view,
                    batch,
                    list(self._interps.values()),
                    call_ids=self._next_call_id,
                    prompt=self._interpret_prompt,
                )
                for interp in results:
                    self._handle_interpretation(run, interp, view)
        return True

    def _handle_interpretation(
        self, run: _Run, interp: LiveInterpretation, view: EventStateView
    ) -> None:
        oid = interp.observation_id
        self._interps[oid] = interp
        self._pending_interps.append(interp)
        spec = interp.change_spec.model_dump(mode="json")
        details: dict[str, Any] = {"interpretation": interp.model_dump(mode="json")}
        tail = (
            " Its text tries to instruct the coordinator; that text is data and has no effect."
            if interp.contains_instructions
            else ""
        )
        for ref in interp.retracts:
            self._record(
                run,
                "inapplicable",
                f"Notice {ref} is retracted by later notice {oid} from the same source "
                f"({interp.source_id}); its claim is no longer weighed.",
                observation_refs=(ref, oid),
                details={"retracted": ref, "retracted_by": oid, "change_spec": spec},
            )
        if interp.standing == "duplicate":
            self._record(
                run,
                "duplicate",
                f"Notice {oid} repeats handled notice {interp.duplicate_of} (same correlation "
                "group and text): one evidence lineage, not corroboration. No plan change." + tail,
                observation_refs=(oid, interp.duplicate_of or oid),
                details=details,
            )
        elif interp.standing == "inapplicable":
            why = "; ".join(
                n.removeprefix("inapplicable: ")
                for n in interp.server_notes
                if n.startswith("inapplicable: ")
            )
            self._record(
                run,
                "inapplicable",
                f"Notice {oid} does not apply to this event: {why or 'another event or booking'}"
                f". No plan change.{tail}",
                observation_refs=(oid,),
                details=details,
            )
        elif interp.standing == "unresolved":
            if interp.failure == "unknown_entity":
                why = (
                    "names an entity that is not registered in this event; the reading is left "
                    "unresolved and no entity is invented"
                )
            elif interp.failure == "malformed_output":
                why = (
                    "could not be interpreted: the model's structured output was malformed or "
                    "invalid after the one repair attempt, so it stays unresolved"
                )
            elif interp.failure == "missing":
                why = "received no reading from the model, so it stays unresolved"
            else:
                fields = ", ".join(interp.change_spec.unresolved_fields) or "its claim"
                why = f"leaves {fields} unresolved"
            verify = self._verify_only(interp)
            more = (
                f" It names {interp.subject_resource_id}, so the only step it can prompt is a "
                "status check; no hypothesis, hold, ask or plan change comes from it."
                if verify
                else ""
            )
            self._record(
                run,
                "unresolved",
                f"Notice {oid} {why}. No plan change.{more}{tail}",
                observation_refs=(oid,),
                details=details | {"failure": interp.failure},
            )
        elif interp.contains_instructions:
            run.notes.append(f"instruction text in {oid} ignored")

    # ------------------------------------------------------------------ one step

    def _verify_first(self, view: EventStateView, run: _Run) -> EventStateView:
        """Runs before each decision step, ahead of the point the step settles on; returns the
        state to decide on. The selective policy verifies only through the menu, so it changes
        nothing here."""
        return view

    def _release_closed_handoffs(self, view: EventStateView, run: _Run) -> bool:
        """Consumable profiles: release own live stock-transfer holds whose staff task is no
        longer open (staff answered it, or its cutoff passed), as the deterministic baseline
        does; such a hold reserves units no staff handoff will move. Chosen by the server, with
        no model call. True when a release changed the state."""
        now = self._now(view)
        released = False
        for hold in view.holds:
            if (
                not hold.consumable
                or hold.actor_id != self._principal
                or hold.purpose != "stock_transfer"
                or hold.effective_status != "active"
                or hold.hold_id in self._release_failed
                or run.mutations_blocked
            ):
                continue
            task = handoff_task(view, hold.hold_id)
            if task is not None and task.status == "open" and now < task.cutoff:
                continue
            why = f"its staff task is {task.status}" if task is not None else "it has no staff task"
            arguments = ReleaseHoldArgs(
                hold_id=hold.hold_id,
                reason=f"Released: {why}; no staff handoff will move these units.",
            ).model_dump(mode="json")
            result = self._mutate(
                run, "release_hold", arguments, expected_revision=self._revision or view.revision
            )
            if result is None:
                return released
            details = {"chosen_by": "server", "hold_id": hold.hold_id}
            if result.applied and result.receipt is not None:
                released = True
                self._record(
                    run,
                    "release",
                    f"Released hold {hold.hold_id} ({hold.remaining_quantity} units of "
                    f"{hold.resource_id}): {why}, so no staff handoff will move these units. "
                    "Releasing creates no stock.",
                    receipt_refs=(result.receipt.receipt_id,),
                    tool_call_refs=result.call_ids,
                    details=details,
                )
                continue
            if result.error_code not in RETRYABLE_REJECTIONS:
                self._release_failed.add(hold.hold_id)  # a stale one is retried next step
            self._record(
                run,
                "wait",
                f"release_hold of {hold.hold_id} was rejected ({result.error_code}); the hold is "
                "unchanged.",
                receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
                tool_call_refs=result.call_ids,
                details=details | {"error_code": result.error_code},
            )
        return released

    def _step(self, view: EventStateView, run: _Run, woke: bool) -> Step:
        if view.stock is not None and self._release_closed_handoffs(view, run):
            return "refresh"
        claims = self._claims(view)
        material = self._open_material(view, claims)
        evaluated = self._evaluate_all(view, run, material)
        if evaluated is None:
            return "done"
        menu = self._attend(view, run, evaluated, material, woke, frozenset(run.rejected_intents))
        if not menu.needs_choice:
            self._record_default(view, run, evaluated, menu, claims)
            return "done"
        choice = self._choose(
            view, run, evaluated, menu, self._context(view, evaluated, menu, claims)
        )
        if choice is None:
            return "done"
        option, output, response = choice
        return self._execute(view, run, evaluated, menu, option, output, response)

    def _evaluate_all(
        self, view: EventStateView, run: _Run, material: list[LiveInterpretation]
    ) -> _Evaluated | None:
        ev = self._evaluate(run, ())
        if ev is None:
            return None
        hypotheses = self._hypotheses(view, material)
        if not hypotheses:
            return _Evaluated(ev=ev)
        labels = ", ".join(h.label for h in hypotheses)
        ev_h = self._evaluate(run, hypotheses)
        if ev_h is None:
            return _Evaluated(
                ev=ev,
                hypotheses=hypotheses,
                robust_note=f"robustness check under {labels} was not available",
            )
        both = _feasible(ev) & _feasible(ev_h)
        if not both:
            return _Evaluated(
                ev=ev,
                hypothetical=ev_h,
                hypotheses=hypotheses,
                robust_note=f"no candidate is feasible both on current evidence and under "
                f"{labels} (hypothetical evaluation {ev_h.evaluation_id}); deciding on current "
                "evidence only",
            )
        return _Evaluated(
            ev=ev,
            hypothetical=ev_h,
            hypotheses=hypotheses,
            eligible=frozenset(both),
            robust_note=f"restricted to candidates feasible both on current evidence and under "
            f"{labels} (hypothetical evaluation {ev_h.evaluation_id})",
        )

    def _evaluate(self, run: _Run, hypotheses: tuple[Hypothesis, ...]) -> EvaluationResult | None:
        args: dict[str, Any] = {}
        if hypotheses:
            args["hypotheses"] = [h.model_dump(mode="json") for h in hypotheses]
        envelope = run.read("evaluate_candidates", args)
        if envelope.status != "succeeded" or envelope.data is None:
            code = envelope.error.code if envelope.error is not None else envelope.status
            self._record_once(
                run,
                ("wait", "evaluation", code, bool(hypotheses)),
                "wait",
                f"evaluate_candidates was {envelope.status} ({code}); the plan is unchanged.",
                tool_call_refs=(envelope.call_id,),
                details={"error_code": code},
            )
            return None
        return EvaluationResult.model_validate(envelope.data)

    def _hypotheses(
        self, view: EventStateView, material: list[LiveInterpretation]
    ) -> tuple[Hypothesis, ...]:
        """The claimed outcome of each material weighed claim whose verification failed
        (hearsay and verify-only notices are never declared outcomes)."""
        chosen: dict[str, LiveInterpretation] = {}
        for claim in material:
            if not claim.is_claim or claim.hearsay or claim.subject_resource_id is None:
                continue
            kind = claim.change_spec.change_kind
            if kind == "delay" and claim.claimed_eta is None:
                continue
            if not self._verification_failed(view, claim):
                continue
            current = chosen.get(claim.subject_resource_id)
            if current is None or _stronger(claim, current):
                chosen[claim.subject_resource_id] = claim
        out: list[Hypothesis] = []
        for rid, claim in sorted(chosen.items()):
            if claim.change_spec.change_kind == "unavailability":
                out.append(
                    Hypothesis(
                        resource_id=rid,
                        assume_status="unavailable",
                        label=f"claimed cancellation from {claim.observation_id}",
                    )
                )
            else:
                out.append(
                    Hypothesis(
                        resource_id=rid,
                        assume_ready_at=claim.claimed_eta,
                        label=f"claimed ETA from {claim.observation_id}",
                    )
                )
        return tuple(out)

    # ------------------------------------------------------------------ model choice

    def _choose(
        self,
        view: EventStateView,
        run: _Run,
        evaluated: _Evaluated,
        menu: Menu,
        context: dict[str, Any],
    ) -> tuple[MenuOption, ChooseOutput, ModelResponse] | None:
        consumed = tuple(r["tool_call_id"] for r in self._pending_results)
        request = ModelRequest(
            purpose="choose_action",
            system=self._choose_prompt.system,
            user=self._choose_prompt.render(state=context),
            schema_name=CHOOSE_SCHEMA_NAME,
            schema=choose_schema(menu.ids),
            output_model=ChooseOutput,
            max_tokens=CHOOSE_MAX_TOKENS,
            context=context,
            call_id=self._next_call_id(),
            consumed_tool_call_ids=consumed,
            prompt_id=self._choose_prompt.prompt_id,
        )
        problem = ""
        failure: Failure = "malformed_output"
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
            assert isinstance(response.parsed, ChooseOutput)
            output = response.parsed
            option = menu.get(output.option_id.strip())
            if option is not None:
                return option, output, response
            # Server-side validation: an id outside the menu is never executed.
            problem, failure = (
                f"option_id {output.option_id[:80]!r} is not in the menu; the menu offers "
                f"{', '.join(menu.ids)}",
                "invalid_choice",
            )
            if attempt == 1:
                request = request.with_repair(
                    response.raw_text, problem, call_id=self._next_call_id()
                )
        self._record(
            run,
            "wait",
            f"The model's choice was not usable after the one repair attempt ({problem[:200]}); "
            f"no action is taken and plan v{view.plan.plan_version} is unchanged.",
            candidate_refs=_ids([evaluated.ev.keep_candidate_id]),
            details={
                "failure": failure,
                "problem": problem[:400],
                "evaluation_id": evaluated.ev.evaluation_id,
                "menu": [o.for_record() for o in menu.options],
            },
        )
        return None

    def _call_model(self, request: ModelRequest) -> ModelResponse:
        """One model call under the episode cap. Malformed or invalid output propagates for
        the caller's repair; other provider failures become control exceptions."""
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
            stage = "interpretation" if request.purpose == "interpret" else "choice"
            raise _ModelFailed(failure, exc, stage) from None
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

    # ------------------------------------------------------------------ execution

    def _execute(
        self,
        view: EventStateView,
        run: _Run,
        evaluated: _Evaluated,
        menu: Menu,
        option: MenuOption,
        output: ChooseOutput,
        response: ModelResponse,
    ) -> Step:
        ev = evaluated.ev
        choice = self._choice_details(view, evaluated, menu, option, output, response)
        self._pending_results.clear()  # consumed by this call
        cited = tuple(choice["cited_refs"])
        if option.action == "keep":
            self._record_keep(view, run, evaluated, option, choice, chosen_by="model")
            return "done"
        if option.action == "wait":
            self._record(
                run,
                "wait",
                f"Chose to wait: {option.summary} Plan v{view.plan.plan_version} is unchanged.",
                observation_refs=_obs_refs(cited, view),
                candidate_refs=_ids([ev.keep_candidate_id]),
                wait_until=option.wait_until,
                details={"choice": choice, "evaluation_id": ev.evaluation_id},
            )
            return "done"
        if option.action == "ask":
            return self._ask(view, run, ev, option, choice)
        if option.action == "query_status":
            return self._query(view, run, ev, option, choice)
        if run.mutations_blocked:
            run.notes.append(f"{option.option_id} not sent: mutations are blocked in this run")
            return "done"
        assert option.tool is not None and option.expected_revision is not None
        result = self._mutate(
            run,
            option.tool,
            option.arguments,
            expected_revision=option.expected_revision,
            expected_goal_version=option.expected_goal_version,
        )
        if result is None:
            return "done"
        self._pending_results.extend(_result_summary(result, view))
        receipt_refs = (result.receipt.receipt_id,) if result.receipt is not None else ()
        base = {
            "choice": choice,
            "evaluation_id": ev.evaluation_id,
            "idempotency_key": result.key,
            "reconciled": result.reconciled,
        }
        code = result.error_code
        if not result.applied and code in RETRYABLE_REJECTIONS:
            self._record(
                run,
                "wait",
                f"{option.tool} for {option.option_id} was rejected as stale ({code}) at "
                f"revision {ev.revision}; the state is re-read and the candidates re-evaluated.",
                candidate_refs=_ids([option.candidate_id]),
                receipt_refs=receipt_refs,
                tool_call_refs=result.call_ids,
                details=base | {"failure": "stale_revision", "error_code": code},
            )
            return "stale"
        if option.action == "apply_plan":
            return self._after_apply(view, run, evaluated, option, result, base)
        if option.action == "hold_resource":
            return self._after_hold(view, run, ev, option, result, base)
        if option.action == "request_handoff":
            return self._after_handoff(view, run, ev, option, result, base)
        return self._after_release(view, run, option, result, base)

    def _query(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        option: MenuOption,
        choice: dict[str, Any],
    ) -> Step:
        envelope = run.read("query_status", option.arguments)
        record = None
        if envelope.status == "succeeded" and envelope.data and envelope.data.get("observation"):
            record = ObservationRecord.model_validate(envelope.data["observation"])
        self._pending_results.append(_envelope_summary(envelope, view, record))
        rid = option.resource_id or ""
        fact = str(option.arguments.get("fact", ""))
        notices = tuple(
            c.observation_id
            for c in self._claims(view)
            if c.subject_resource_id == rid and self._answer(view, c) is None
        )
        answer = (record.observation.observation_id,) if record is not None else ()
        verdicts = ""
        if record is not None and notices:
            verdicts = "; notice " + ", ".join(
                f"{n} {_assess(self._interps[n], *_facts(record))}" for n in notices
            )
        code = envelope.error.code if envelope.error is not None else None
        self._record(
            run,
            "verify",
            f"Checked {rid} {fact}: {_status_text(envelope, record, view)}{verdicts}.",
            observation_refs=notices + answer,
            tool_call_refs=(envelope.call_id,),
            candidate_refs=_ids([option.candidate_id]),
            details={
                "choice": choice,
                "evaluation_id": ev.evaluation_id,
                "entity_id": rid,
                "fact": fact,
                "outcome": envelope.status,
                "error_code": code,
            },
        )
        return "refresh"

    def _ask(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        option: MenuOption,
        choice: dict[str, Any],
    ) -> Step:
        request = option.authorization_request
        grant = own_grant(view, self._principal)
        cand = _candidate(ev, option.candidate_id)
        if request is None or grant is None or cand is None:
            return "done"
        bound = tuple(rh.bound_hold_id for rh in cand.required_holds if rh.bound_hold_id)
        self._open_ask = OpenAsk(
            request=request, signature=cand.signature, grant_version=grant.version, hold_ids=bound
        )
        holds = {h.hold_id: h for h in view.holds}
        expiries = [holds[h].expires_at for h in bound if h in holds]
        self._wake = self._ask_wake(view, expiries)
        until = f" until {self._t(min(expiries), view)}" if expiries else ""
        self._record(
            run,
            "ask",
            f"Asked the organizer to raise {request.field} of {request.target_grant_id} from "
            f"{request.current_value} to {request.requested_value} cents so {cand.label} can be "
            f"applied; hold {', '.join(bound) or 'none'} keeps the option open{until}.",
            candidate_refs=(cand.candidate_id,),
            observation_refs=_obs_refs(tuple(choice["cited_refs"]), view),
            authorization_request=request,
            wait_until=self._wake,
            details={
                "choice": choice,
                "evaluation_id": ev.evaluation_id,
                "report_id": cand.report_id,
                "missing": [m.model_dump(mode="json") for m in cand.authorization.missing],
            },
        )
        return "done"

    def _after_apply(
        self,
        view: EventStateView,
        run: _Run,
        evaluated: _Evaluated,
        option: MenuOption,
        result: _Mutation,
        base: dict[str, Any],
    ) -> Step:
        ev = evaluated.ev
        target = _candidate(ev, option.candidate_id)
        label = target.label if target is not None else option.option_id
        if result.applied and result.receipt is not None and target is not None:
            receipt = result.receipt
            keep = _candidate(ev, ev.keep_candidate_id)
            failed = (
                [ch.constraint_id for ch in keep.checks if ch.status == "failed"] if keep else []
            )
            why = f"; the current plan fails {', '.join(failed)}" if failed else ""
            if target.service_coverage:
                why += (
                    f"; it {coverage_text(target)}, its stock holds are now committed "
                    "allocations, and only a staff-recorded distribution serves anyone"
                )
            robust = f"; {evaluated.robust_note}" if evaluated.robust_note else ""
            self._record(
                run,
                "commit",
                f"Applied {label} ({target.candidate_id}, report {target.report_id}): changed "
                f"{', '.join(target.changed_activity_ids) or 'no activity'}, additional "
                f"committed {target.incremental_committed_cents} cents, revision "
                f"{receipt.revision_before} -> {receipt.revision_after}{why}{robust}.",
                observation_refs=_obs_refs(tuple(base["choice"]["cited_refs"]), view),
                candidate_refs=(target.candidate_id,),
                receipt_refs=(receipt.receipt_id,),
                tool_call_refs=result.call_ids,
                details=base
                | {
                    "report_id": target.report_id,
                    "assumptions": [a.text for a in target.assumptions],
                },
            )
            if self._open_ask is not None and self._open_ask.signature == target.signature:
                self._open_ask = None
                self._wake = None
            return "refresh"
        run.rejected_intents.add(option.intent)
        self._record(
            run,
            "wait",
            f"apply_plan for {label} was rejected ({result.error_code}); plan "
            f"v{view.plan.plan_version} is unchanged.",
            candidate_refs=_ids([option.candidate_id]),
            receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
            tool_call_refs=result.call_ids,
            details=base | {"error_code": result.error_code, "report_id": option.report_id},
        )
        return "refresh"

    def _after_hold(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        option: MenuOption,
        result: _Mutation,
        base: dict[str, Any],
    ) -> Step:
        rid, aid = option.resource_id or "", option.activity_id or ""
        cand = _candidate(ev, option.candidate_id)
        label = cand.label if cand is not None else option.candidate_id
        if result.applied and result.receipt is not None:
            grant = own_grant(view, self._principal)
            if grant is not None:
                count_key = (rid, aid, grant.version)
                self._hold_counts[count_key] = self._hold_counts.get(count_key, 0) + 1
            hold = _hold_from(result)
            expiry = f", expires {self._t(hold.expires_at, view)}" if hold else ""
            if option.quantity is not None:
                self._record(
                    run,
                    "prepare",
                    f"Held {option.quantity} units of {rid} for {option.service_target_id} "
                    f"({aid}){f' (hold {hold.hold_id}{expiry})' if hold else ''} so {label} can "
                    "be applied; a hold reserves units and serves nobody.",
                    candidate_refs=_ids([option.candidate_id]),
                    receipt_refs=(result.receipt.receipt_id,),
                    tool_call_refs=result.call_ids,
                    details=base
                    | {"hold_id": hold.hold_id if hold else None, "quantity": option.quantity},
                )
                return "refresh"
            self._record(
                run,
                "prepare",
                f"Held {rid} for {aid}{f' (hold {hold.hold_id}{expiry})' if hold else ''} to keep "
                f"{label} open; reserved {hold.reserved_cents if hold else 0} cents, refundable "
                "on release or expiry.",
                candidate_refs=_ids([option.candidate_id]),
                receipt_refs=(result.receipt.receipt_id,),
                tool_call_refs=result.call_ids,
                details=base | {"hold_id": hold.hold_id if hold else None},
            )
            return "refresh"
        run.rejected_intents.add(option.intent)
        self._record(
            run,
            "prepare",
            f"Hold of {rid} for {aid} was rejected ({result.error_code}); no reservation was made.",
            candidate_refs=_ids([option.candidate_id]),
            receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
            tool_call_refs=result.call_ids,
            details=base | {"error_code": result.error_code, "outcome": "rejected"},
        )
        return "refresh"

    def _after_handoff(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        option: MenuOption,
        result: _Mutation,
        base: dict[str, Any],
    ) -> Step:
        """A staff handoff request: the stock-transfer hold is the local staff task. Only a
        staff-recorded receipt moves stock; the agent never records one."""
        source, destination = option.resource_id or "", option.destination_resource_id or ""
        hold = _hold_from(result)
        if result.applied and result.receipt is not None and hold is None:
            # A reconciled response carries the receipt, not the hold: find it by its receipt.
            receipt_id = result.receipt.receipt_id
            view = self._refresh(run)
            hold = next((h for h in view.holds if h.created_receipt_id == receipt_id), None)
        if result.applied and result.receipt is not None and hold is not None:
            task = handoff_task(view, hold.hold_id)
            params = view.pantry_parameters
            due = (
                task.respond_after
                if task is not None
                else hold.created_at + timedelta(minutes=params.handoff_duration_minutes)
                if params is not None
                else None
            )
            self._record(
                run,
                "ask",
                f"Asked staff to hand off {option.quantity} units from {source} into "
                f"{destination}: hold {hold.hold_id} on {source} (the local staff task, expires "
                f"{self._t(hold.expires_at, view)}) reserves them and moves nothing; only a "
                "staff-recorded receipt moves stock"
                + (f"; their response is due at {self._t(due, view)}" if due else "")
                + ".",
                candidate_refs=_ids([option.candidate_id]),
                receipt_refs=(result.receipt.receipt_id,),
                tool_call_refs=result.call_ids,
                wait_until=due,
                details=base
                | {
                    "ask": "stock_handoff",
                    "hold_id": hold.hold_id,
                    "quantity": option.quantity,
                    "source_resource_id": source,
                    "destination_resource_id": destination,
                },
            )
            return "refresh"
        run.rejected_intents.add(option.intent)
        self._record(
            run,
            "prepare",
            f"The handoff request for {option.quantity} units of {source} was rejected "
            f"({result.error_code}); no reservation was made and no staff task exists.",
            candidate_refs=_ids([option.candidate_id]),
            receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
            tool_call_refs=result.call_ids,
            details=base | {"error_code": result.error_code, "outcome": "rejected"},
        )
        return "refresh"

    def _after_release(
        self,
        view: EventStateView,
        run: _Run,
        option: MenuOption,
        result: _Mutation,
        base: dict[str, Any],
    ) -> Step:
        hid = option.hold_id or ""
        if result.applied and result.receipt is not None:
            self._record(
                run,
                "release",
                f"Released hold {hid} on {option.resource_id} for {option.activity_id}: active "
                f"plan v{view.plan.plan_version} does not use it.",
                receipt_refs=(result.receipt.receipt_id,),
                tool_call_refs=result.call_ids,
                details=base | {"hold_id": hid},
            )
            if self._open_ask is not None and hid in self._open_ask.hold_ids:
                self._open_ask = None
                self._wake = None
            return "refresh"
        run.rejected_intents.add(option.intent)
        self._record(
            run,
            "wait",
            f"release_hold of {hid} was rejected ({result.error_code}); the hold is unchanged.",
            receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
            tool_call_refs=result.call_ids,
            details=base | {"error_code": result.error_code, "hold_id": hid},
        )
        return "refresh"

    def _mutate(
        self,
        run: _Run,
        tool: str,
        arguments: dict[str, Any],
        *,
        expected_revision: int,
        expected_goal_version: int | None = None,
    ) -> _Mutation | None:
        """One mutation; a lost response is reconciled with ``get_action_receipt`` and the
        original key (at most ``MAX_RECEIPT_LOOKUPS`` lookups and one identical retry).
        Returns None when the outcome could not be established (mutations then stop)."""
        key = idempotency_key(expected_revision, tool, arguments)
        request = sha256_hex(
            canonical_json([tool, arguments, expected_revision, expected_goal_version])
        )
        if self._own_keys.setdefault(key, request) != request:
            run.notes.append(f"{tool} not sent: key {key} already names a different request")
            return None

        def send() -> ToolEnvelope:
            return run.call(
                tool,
                arguments,
                idempotency_key=key,
                expected_revision=expected_revision,
                expected_goal_version=expected_goal_version,
            )

        try:
            envelope = send()
            return _Mutation(envelope, envelope.receipt, (envelope.call_id,), key)
        except TransportLost:
            pass
        calls: list[str] = []
        retried = False
        for _ in range(MAX_RECEIPT_LOOKUPS):
            try:
                lookup = run.call("get_action_receipt", {"idempotency_key": key})
            except TransportLost:
                continue
            calls.append(lookup.call_id)
            data = lookup.data or {}
            if lookup.status == "succeeded" and data.get("lookup_status") == "found":
                receipt = ActionReceipt.model_validate(data["receipt"])
                return _Mutation(lookup, receipt, tuple(calls), key, reconciled=True)
            if retried:
                continue
            retried = True
            try:
                envelope = send()
                calls.append(envelope.call_id)
                return _Mutation(envelope, envelope.receipt, tuple(calls), key, reconciled=True)
            except TransportLost:
                continue
        run.mutations_blocked = True
        self._record(
            run,
            "reconcile",
            f"The response to {tool} (key {key}) was lost and its outcome could not be "
            f"established after {MAX_RECEIPT_LOOKUPS} receipt lookups and one identical retry; "
            "no further mutation is made in this run.",
            tool_call_refs=tuple(calls),
            details={"failure": "lost_response", "idempotency_key": key, "tool": tool},
        )
        return None

    # ------------------------------------------------------------------ narration

    def _record_model_failure(self, run: _Run, failed: _ModelFailed) -> None:
        error, stage = failed.error, failed.stage
        what = "timed out" if failed.failure == "provider_timeout" else "failed"
        now = self._at
        run.retry_at = now + PROVIDER_RETRY if now is not None else None
        self._record(
            run,
            "wait",
            f"The model call for {stage} {what} ({error.kind}: {error.message[:160]}); no action "
            "is taken and the plan is unchanged. The next wake tries again within the caps.",
            details={"failure": failed.failure, "stage": stage, "error_kind": error.kind},
            wait_until=run.retry_at,
        )

    def _record_stop(self, run: _Run, reason: str) -> None:
        self._record_once(run, ("stop", reason), "stop", f"Stopped: {reason}. No further action.")

    def _halt(self, run: _Run, halt: _Halt) -> None:
        self._halted = halt.reason
        self._record(
            run,
            "stop",
            f"Stopped for this episode: {halt.reason}. No further model-chosen action is taken; "
            "the accepted plan and every commitment stay as they are.",
            details={"failure": halt.failure},
        )

    def _flush(self, run: _Run) -> None:
        """Attach model calls not yet carried by a decision (for example the interpretation
        before a stop) to one last decision, so every call's cost appears in a decision."""
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
        interps, self._pending_interps = self._pending_interps, []
        out = dict(details or {})
        out.setdefault("chosen_by", "model" if "choice" in out else "server")
        out["model"] = self._model_details(calls)
        out["prompts"] = {
            p.prompt_id: p.sha256 for p in (self._interpret_prompt, self._choose_prompt)
        }
        if interps:
            out["interpretations"] = [i.change_spec.model_dump(mode="json") for i in interps]
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

    def _choice_details(
        self,
        view: EventStateView,
        evaluated: _Evaluated,
        menu: Menu,
        option: MenuOption,
        output: ChooseOutput,
        response: ModelResponse,
    ) -> dict[str, Any]:
        """The validated choice. Cited ids that name nothing visible are dropped."""
        consumed = response.record.consumed_tool_call_ids
        known = _known_ids(view, evaluated, menu) | set(consumed)
        cited = [r for r in dict.fromkeys(output.cited_refs) if r in known]
        dropped = [r[:64] for r in output.cited_refs if r not in known]
        return {
            "option_id": option.option_id,
            "intent": option.intent,
            "model_call_id": response.record.call_id,
            "rationale_untrusted": " ".join(output.rationale.split())[:MAX_RATIONALE_CHARS],
            "cited_refs": cited,
            "dropped_refs": dropped[:8],
            "menu": [o.for_record() for o in menu.options],
            "consumed_tool_call_ids": list(consumed),
        }

    # ------------------------------------------------------------------ prompt context

    def _context(
        self,
        view: EventStateView,
        evaluated: _Evaluated,
        menu: Menu,
        claims: list[LiveInterpretation],
    ) -> dict[str, Any]:
        """The server data the model chooses from (everything is data; text is quoted)."""
        ev = evaluated.ev
        lifecycles = _lifecycles(view)
        grant = own_grant(view, self._principal)
        shown = list(ev.candidates[:MAX_CANDIDATES_SHOWN])
        for cid in (ev.keep_candidate_id, ev.best_applicable_candidate_id):
            c = _candidate(ev, cid)
            if c is not None and c not in shown:
                shown.append(c)
        robust = None
        if evaluated.hypotheses:
            robust = {
                "hypotheses": [h.label for h in evaluated.hypotheses],
                "hypothetical_evaluation_id": (
                    evaluated.hypothetical.evaluation_id if evaluated.hypothetical else None
                ),
                "robust_candidate_ids": [
                    c.candidate_id
                    for c in ev.candidates
                    if evaluated.eligible is not None and c.signature in evaluated.eligible
                ],
                "note": evaluated.robust_note,
            }
        return {
            "event": {
                "event_id": view.event_id,
                "now_local": self._t(self._now(view), view),
                "hard_end_local": self._t(view.goal.hard_end, view),
                "revision": view.revision,
                "goal_version": view.goal.version,
            },
            "plan": {
                "plan_version": view.plan.plan_version,
                "assignments": [
                    {
                        "activity_id": a.activity_id,
                        "start_local": self._t(a.start, view),
                        "end_local": self._t(a.end, view),
                        "resource_ids": list(a.resource_ids),
                        "lifecycle": lifecycles.get(a.activity_id),
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
                    "reported_eta_local": (
                        self._t(r.reported_eta, view) if r.reported_eta is not None else None
                    ),
                    "booking_required": r.definition.terms.booking_required,
                }
                for r in view.resources
            ],
            "own_active_holds": [
                {
                    "hold_id": h.hold_id,
                    "resource_id": h.resource_id,
                    "activity_id": h.activity_id,
                    "expires_local": self._t(h.expires_at, view),
                }
                for h in view.holds
                if h.actor_id == self._principal and h.effective_status == "active"
            ],
            "grant": (
                {
                    "grant_id": grant.grant.grant_id,
                    "version": grant.version,
                    "max_total_committed_cents": grant.grant.max_total_committed_cents,
                    "committed_used_cents": grant.committed_used_cents,
                    "max_total_reserved_cents": grant.grant.max_total_reserved_cents,
                    "reserved_used_cents": grant.reserved_used_cents,
                }
                if grant is not None
                else None
            ),
            "budget_remaining_cents": view.budget.remaining_cents,
            "notices": [self._notice_context(view, c) for c in claims],
            "evaluation": {
                "evaluation_id": ev.evaluation_id,
                "revision": ev.revision,
                "keep_candidate_id": ev.keep_candidate_id,
                "best_candidate_id": ev.best_candidate_id,
                "best_applicable_candidate_id": ev.best_applicable_candidate_id,
                "candidates": [_candidate_context(c) for c in shown],
                "not_shown": max(len(ev.candidates) - len(shown), 0),
                "infeasibility": (
                    ev.infeasibility.model_dump(mode="json") if ev.infeasibility else None
                ),
            },
            **({"stock": _stock_context(view, self._principal)} if view.stock else {}),
            "robustness": robust,
            "open_authorization_request": (
                self._open_ask.request.model_dump(mode="json") if self._open_ask else None
            ),
            "last_tool_results": list(self._pending_results),
            "menu": [o.for_model() for o in menu.options],
            "caps_left": {
                "model_calls": self.max_model_calls - self._model_calls,
                "tool_calls": self.max_tool_calls - self._tool_calls,
            },
        }

    def _notice_context(self, view: EventStateView, interp: LiveInterpretation) -> dict[str, Any]:
        answer = self._answer(view, interp)
        return {
            "observation_id": interp.observation_id,
            "standing": "verification_only" if self._verify_only(interp) else interp.standing,
            "change_kind": interp.change_spec.change_kind,
            "subject_id": interp.subject_resource_id,
            "claimed_eta_local": (
                self._t(interp.claimed_eta, view) if interp.claimed_eta is not None else None
            ),
            "hearsay": interp.hearsay,
            "material": self._material(view, interp),
            "answered_by": answer[0] if answer else None,
            "evidence_status": answer[1] if answer else "unresolved",
            "verification_failed": answer is None and self._verification_failed(view, interp),
        }

    # ------------------------------------------------------------------ waiting


# ---------------------------------------------------------------------------------- factory


def live_policy_factory(
    config: ModelConfig | None = None,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_model_calls: int = DEFAULT_MAX_MODEL_CALLS,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ledger_path: Path | None = None,
    seed: int | None = None,
) -> Callable[[], LivePolicy]:
    """A ``policy_factory`` for ``PolicyHost`` / ``run_case``: each instance (one episode) gets
    its own provider and spend guard, so the per-run cap is a per-episode cap (a rebuilt instance
    resumes the episode's recorded spend through ``resume_usage``). ``seed`` goes to the
    provider (the OpenAI-compatible ``seed``; recorded per call). Raises ``ModelConfigError``
    now when the endpoint is not configured."""
    cfg = config or load_model_config()
    ledger = SpendLedger(ledger_path or cfg.ledger_path)

    def make() -> LivePolicy:
        guard = SpendGuard(
            ledger,
            max_run_usd=cfg.max_run_cost_usd,
            max_total_usd=cfg.max_total_cost_usd,
            run_id=f"live-{uuid.uuid4().hex[:12]}",
        )
        provider = OpenAICompatibleProvider(cfg, guard, timeout_s=timeout_s, seed=seed)
        return LivePolicy(provider, max_model_calls=max_model_calls, max_tool_calls=max_tool_calls)

    return make


# ---------------------------------------------------------------------------------- helpers


def _lineage(record: ObservationRecord) -> tuple[str, str]:
    return record.observation.correlation_group, normalize_text(record.observation.text)


def _feasible(ev: EvaluationResult) -> set[str]:
    return {
        c.signature for c in ev.candidates if c.constraint_status == "feasible_under_assumptions"
    }


def _stronger(a: LiveInterpretation, b: LiveInterpretation) -> bool:
    """Cancellation over delay; between delays the later claimed ETA, then the later notice."""
    ka, kb = a.change_spec.change_kind, b.change_spec.change_kind
    if (ka == "unavailability") != (kb == "unavailability"):
        return ka == "unavailability"
    if a.claimed_eta is not None and b.claimed_eta is not None and a.claimed_eta != b.claimed_eta:
        return a.claimed_eta > b.claimed_eta
    return (a.received_at, a.revision_after) > (b.received_at, b.revision_after)


def _facts(record: ObservationRecord) -> tuple[str, datetime | None]:
    if record.structured is None:
        return "unknown", None
    return record.structured.domain_status, record.structured.reported_eta


def _obs_refs(refs: tuple[str, ...], view: EventStateView) -> tuple[str, ...]:
    visible = {r.observation.observation_id for r in view.observations}
    return tuple(r for r in refs if r in visible)


def _known_ids(view: EventStateView, evaluated: _Evaluated, menu: Menu) -> set[str]:
    known = {r.observation.observation_id for r in view.observations}
    known |= {r.receipt_id for r in view.receipts}
    known |= {c.call_id for c in view.status_checks}
    known |= {h.hold_id for h in view.holds}
    known.add(evaluated.ev.evaluation_id)
    for ev in (evaluated.ev, evaluated.hypothetical):
        if ev is None:
            continue
        known |= {c.candidate_id for c in ev.candidates} | {c.report_id for c in ev.candidates}
    known |= set(menu.ids)
    return known


def _stock_context(view: EventStateView, principal: str) -> dict[str, Any]:
    """Consumable stock as the model sees it: balances, service counters, staff tasks."""
    stock = view.stock
    assert stock is not None
    params = view.pantry_parameters

    def t(value: datetime) -> str:
        return local_label(value, view.timezone)

    return {
        "balances": [
            {
                "resource_id": b.resource_id,
                "unit": b.unit,
                "on_hand": b.on_hand_quantity,
                "reserved": b.reserved_quantity,
                "available": b.available_quantity,
                "expected_not_stock": b.expected_quantity,
            }
            for b in stock.balances
        ],
        "service": [
            {
                "target_id": s.target_id,
                "target": s.target_quantity,
                "original_target": s.original_quantity,
                "deadline_local": t(s.deadline),
                "distributed_on_time": s.on_time_quantity,
                "committed_undistributed": s.committed_quantity,
                "supply_gap": s.supply_gap_quantity,
                "unfulfilled": s.unfulfilled_quantity,
            }
            for s in stock.service
        ],
        "expected_shipments": [
            {
                "shipment_id": e.shipment.shipment_id,
                "destination": e.shipment.destination_resource_id,
                "outstanding": e.outstanding_quantity,
                "reported_eta_local": t(e.reported_eta) if e.reported_eta else None,
            }
            for e in stock.expected_shipments
        ],
        "staff_handoff_tasks": [
            {
                "hold_id": h.hold_id,
                "source": h.source_resource_id,
                "destination": h.destination_resource_id,
                "requested": h.requested_quantity,
                "remaining": h.remaining_quantity,
                "respond_after_local": t(h.respond_after),
                "cutoff_local": t(h.cutoff),
                "status": h.status,
            }
            for h in stock.handoff_tasks
        ],
        "own_stock_holds": [
            {
                "hold_id": h.hold_id,
                "resource_id": h.resource_id,
                "purpose": h.purpose,
                "remaining": h.remaining_quantity,
                "status": h.effective_status,
                "expires_local": t(h.expires_at),
            }
            for h in view.holds
            if h.consumable and h.actor_id == principal
        ],
        "handoff": (
            {
                "window_local": f"{t(params.handoff_window.start)}-{t(params.handoff_window.end)}",
                "staff_response_minutes": params.handoff_duration_minutes,
                "service_rate_units_per_minute": params.service_rate_units_per_minute,
            }
            if params is not None
            else None
        ),
    }


def _candidate_context(c: CandidateResult) -> dict[str, Any]:
    stock: dict[str, Any] = {}
    if c.service_coverage:
        stock = {
            "required_stock_holds": [
                {
                    "resource_id": h.resource_id,
                    "activity_id": h.activity_id,
                    "service_target_id": h.service_target_id,
                    "quantity": h.quantity,
                    "held": h.held_quantity,
                }
                for h in c.required_stock_holds
            ],
            "stock_transfers": [
                {
                    "source": n.source_resource_id,
                    "destination": n.destination_resource_id,
                    "activity_id": n.activity_id,
                    "quantity": n.quantity,
                    "held": n.held_quantity,
                }
                for n in c.stock_transfers
            ],
            "service_coverage": [
                {
                    "target_id": s.target_id,
                    "on_time": s.on_time_quantity,
                    "unfulfilled": s.unfulfilled_quantity,
                }
                for s in c.service_coverage
            ],
        }
    return stock | {
        "candidate_id": c.candidate_id,
        "report_id": c.report_id,
        "label": c.label,
        "constraint_status": c.constraint_status,
        "rank": c.rank,
        "applicable_now": c.applicable_now,
        "failed_checks": [ch.constraint_id for ch in c.checks if ch.status == "failed"],
        "assumptions": [a.text[:200] for a in c.assumptions[:4]],
        "missing_permissions": [m.kind for m in c.authorization.missing],
        "required_holds": [
            {"resource_id": rh.resource_id, "bound_hold_id": rh.bound_hold_id}
            for rh in c.required_holds
        ],
        "incremental_committed_cents": c.incremental_committed_cents,
        "objective_total": c.objective.total,
    }


def _status_text(
    envelope: ToolEnvelope, record: ObservationRecord | None, view: EventStateView
) -> str:
    if envelope.status != "succeeded":
        code = envelope.error.code if envelope.error is not None else None
        return f"{envelope.status}{f' ({code})' if code else ''}; the status stays unverified"
    if record is None or record.structured is None:
        return "succeeded without typed facts"
    facts = record.structured
    eta = (
        f", reported ETA {local_label(facts.reported_eta, view.timezone)}"
        if facts.reported_eta is not None
        else ""
    )
    freshness = envelope.data.get("freshness") if envelope.data else None
    stale = ", stale record" if isinstance(freshness, dict) and freshness.get("stale") else ""
    return (
        f"{facts.status_code}, {facts.domain_status}{eta} "
        f"({record.observation.observation_id}{stale})"
    )


def _envelope_summary(
    envelope: ToolEnvelope, view: EventStateView, record: ObservationRecord | None = None
) -> dict[str, Any]:
    receipt = envelope.receipt
    return {
        "tool_call_id": envelope.call_id,
        "tool": envelope.tool,
        "status": envelope.status,
        "error_code": envelope.error.code if envelope.error is not None else None,
        "receipt_id": receipt.receipt_id if receipt is not None else None,
        "receipt_status": receipt.status if receipt is not None else None,
        "revision": envelope.revision,
        "summary": (
            _status_text(envelope, record, view)
            if envelope.tool == "query_status"
            else (receipt.summary[:300] if receipt is not None else envelope.status)
        ),
    }


def _result_summary(result: _Mutation, view: EventStateView) -> list[dict[str, Any]]:
    if result.envelope is None:
        return []
    out = _envelope_summary(result.envelope, view)
    if result.reconciled and result.receipt is not None:
        out |= {
            "reconciled": True,
            "receipt_id": result.receipt.receipt_id,
            "receipt_status": result.receipt.status,
            "summary": result.receipt.summary[:300],
        }
    return [out]


def _hold_from(result: _Mutation) -> HoldView | None:
    data = result.envelope.data if result.envelope is not None else None
    if data and isinstance(data.get("hold"), dict):
        return HoldView.model_validate(data["hold"])
    return None
