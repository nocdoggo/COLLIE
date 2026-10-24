"""Deterministic rule policy P0 (``rules/1.0.0``), contract section 11.

The policy sees only tool envelopes through a ``ToolClient``. One ``run`` is a bounded loop:
read state, interpret new observations, verify material claims with ``query_status`` (at
most two attempts per claim), evaluate the declared candidate menu (and, when verification
failed, the claimed outcome as a hypothesis, keeping only candidates feasible under both),
then keep, apply, prepare (verify a catalog substitute, hold it, ask for the missing committed
limit), report infeasibility, release holds the plan no longer needs, and wait.

Source standing. A claim is weighed by what its source can report. A delay or cancellation
claim delivered by the scenario (channel ``scenario_delivery`` or ``fixture_initial``: the
supplier's external contact) follows the robustness rule above when verification fails. A
claim submitted through an event session (``participant_session``, ``organizer_session``)
about equipment is hearsay: event principals speak for their own roles, not for a supplier's
delivery. Hearsay may trigger verification, and a typed answer settles it like any claim, but
while unverified it builds no hypothesis, so on its own it never causes a hold, an ask or a
robustness-driven plan change. A later notice whose ``supersedes`` names an earlier notice of
the same source retracts that notice's claim.

Verification only. A notice outside the supported message forms is never a claim. When the
parser still finds exactly one registered equipment resource in it (``verify_subject_id``),
that resource's registered status source may be queried under the same bounds as a claim
(material resources only, at most two attempts), and the typed status it returns drives
planning as usual; the notice itself builds no hypothesis and causes no hold, ask or plan
change.

The loop remembers the revision of the last state view it decided on. A wake whose state
differs from it (including a change that landed during the previous run's last tool call)
runs a new cycle; recorded decisions are de-duplicated, so a repeated cycle adds none.

When nothing is feasible but some candidates are ``unknown`` (an unsupported requirement), the
decision is ``unresolved``: it names the unsupported requirement and the undecided candidates
instead of reporting infeasibility. An ``AuthorizationRequest.reason`` is one sentence naming
the exact missing permission, bounded by the model's 400-character limit for any candidate.

Per-episode memory lives on the instance (the host keeps one instance per episode; reset
creates a new one). Every choice comes from visible state, tool results and declared
configuration; nothing here knows a case, a label or a scripted time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import (
    ActionReceipt,
    ApplyPlanArgs,
    Assignment,
    AuthorizationRequest,
    CandidateResult,
    DecisionKind,
    EvaluationResult,
    EventStateView,
    GrantView,
    HoldResourceArgs,
    HoldView,
    Hypothesis,
    ObservationRecord,
    PolicyDecision,
    PolicyRunResult,
    QueryStatusArgs,
    ReleaseHoldArgs,
    ResourceStatus,
    ResourceView,
    ToolEnvelope,
)
from plan_b.domain.timeutil import local_label
from plan_b.evaluation.policies.base import ToolClient, TransportLost
from plan_b.evaluation.policies.parser import (
    NOTICE_KINDS,
    EvidenceStatus,
    Interpretation,
    assess_claim,
    event_local_date,
    interpret_observation,
)

POLICY_ID = "rules/1.0.0"
MAX_STATUS_ATTEMPTS = 2
MAX_RECEIPT_LOOKUPS = 2
MAX_CYCLES = 6
MAX_STALE_RETRIES = 2
MAX_HOLDS_PER_OPTION = 2  # one hold and at most one re-hold per grant version
DEADLINE_LEAD = timedelta(minutes=5)
ETA_GRACE = timedelta(minutes=1)
ASK_LEAD = timedelta(minutes=1)
ASK_REASON_LIMIT = 400  # AuthorizationRequest.reason max_length
RETRYABLE_REJECTIONS = frozenset(
    {"REVISION_CONFLICT", "CANDIDATE_STALE", "GOAL_VERSION_CONFLICT", "HOLD_EXPIRED"}
)
NOT_STARTED = ("planned", "ready")

Step = Literal["done", "again", "refresh"]


def idempotency_key(revision: int, tool: str, arguments: dict[str, Any]) -> str:
    """``rules-r<revision>-<tool>-<sha8(arguments)>``: the same intent at the same revision
    always maps to the same key, so a repeat is an idempotent retry, never a fresh request."""
    return f"rules-r{revision}-{tool}-{sha256_hex(canonical_json(arguments))[:8]}"


class _BudgetExhausted(Exception):
    """The run's tool-call budget is spent."""


class _ReadLost(Exception):
    """A read response was lost twice in a row."""


class _Stop(Exception):
    """A stop condition holds (event over, episode closed, grant not valid)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Claim:
    interpretation: Interpretation
    attempts: int = 0
    verification_unavailable: bool = False
    answered_by: str | None = None
    evidence_status: EvidenceStatus = "unresolved"

    @property
    def observation_id(self) -> str:
        return self.interpretation.observation_id

    @property
    def subject_id(self) -> str:
        interp = self.interpretation
        return interp.subject_id or interp.verify_subject_id or ""

    @property
    def hearsay(self) -> bool:
        return self.interpretation.hearsay

    @property
    def verify_only(self) -> bool:
        """An unsupported notice whose resource may be checked; never weighed as a claim."""
        return self.interpretation.verify_subject_id is not None

    def assess(
        self, domain_status: ResourceStatus, reported_eta: datetime | None
    ) -> EvidenceStatus:
        """The claim's standing under a typed status; a verify-only notice stays unresolved."""
        if self.verify_only:
            return "unresolved"
        return assess_claim(
            self.interpretation, domain_status=domain_status, reported_eta=reported_eta
        )


@dataclass
class _OpenRequest:
    request: AuthorizationRequest
    grant_version: int
    signature: str
    hold_ids: tuple[str, ...]


@dataclass
class _Watch:
    at: datetime
    activity_id: str
    resource_id: str
    plan_version: int


@dataclass
class _Mutation:
    envelope: ToolEnvelope | None
    receipt: ActionReceipt | None
    call_ids: tuple[str, ...]
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
class _Cycle:
    stale_retries: int = 0
    blocked: list[str] = field(default_factory=list)


class _Run:
    """Call accounting and the latest envelope position for one ``run``."""

    def __init__(self, client: ToolClient, max_calls: int) -> None:
        self.client = client
        self.max_calls = max_calls
        self.calls = 0
        self.decisions: list[PolicyDecision] = []
        self.at: datetime | None = None
        self.revision: int | None = None
        self.goal_version: int | None = None
        self.mutations_blocked = False
        self.notes: list[str] = []

    def call(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        expected_goal_version: int | None = None,
    ) -> ToolEnvelope:
        if self.calls >= self.max_calls:
            raise _BudgetExhausted
        self.calls += 1
        envelope = self.client.call(
            tool,
            arguments=arguments,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            expected_goal_version=expected_goal_version,
        )
        if envelope.scenario_time is not None:
            self.at = envelope.scenario_time
        if envelope.revision is not None:
            self.revision = envelope.revision
        if envelope.goal_version is not None:
            self.goal_version = envelope.goal_version
        return envelope

    def read(self, tool: str, arguments: dict[str, Any]) -> ToolEnvelope:
        """Reads have no side effects, so one lost response is retried once."""
        try:
            return self.call(tool, arguments)
        except TransportLost:
            try:
                return self.call(tool, arguments)
            except TransportLost as exc:
                raise _ReadLost from exc


class RulePolicy:
    """P0: the documented deterministic coordinator policy."""

    policy_id = POLICY_ID

    def __init__(self) -> None:
        self._seq = 0
        self._handled: dict[str, Interpretation] = {}
        self._claims: dict[str, _Claim] = {}
        self._recorded: set[tuple[Any, ...]] = set()
        self._open_request: _OpenRequest | None = None
        self._hold_wake: datetime | None = None
        self._watch: _Watch | None = None
        self._deadline_rechecked: set[tuple[str, str, int]] = set()
        self._substitute_attempts: dict[str, int] = {}
        self._hold_counts: dict[tuple[str, str, int], int] = {}
        self._own_keys: dict[str, str] = {}
        self._settled: tuple[int, int] | None = None
        self._stopped = False
        self._principal = ""

    # ------------------------------------------------------------------ entry point

    def run(self, client: ToolClient, max_tool_calls: int = 16) -> PolicyRunResult:
        self._principal = client.principal_id
        run = _Run(client, max_tool_calls)
        try:
            status, wait_until = self._run(run)
        except _BudgetExhausted:
            run.notes.append(f"tool-call budget of {max_tool_calls} spent")
            return self._result(run, "budget_exhausted", None)
        except _ReadLost:
            run.notes.append("a state read response was lost twice; nothing was decided")
            return self._result(run, "waiting", None, incomplete=True)
        return self._result(run, status, wait_until)

    def _result(
        self,
        run: _Run,
        status: Literal["waiting", "stopped", "budget_exhausted"],
        wait_until: datetime | None,
        *,
        incomplete: bool = False,
    ) -> PolicyRunResult:
        return PolicyRunResult(
            policy_id=POLICY_ID,
            status=status,
            decisions=tuple(run.decisions),
            tool_calls=run.calls,
            wait_until=wait_until,
            note="; ".join(run.notes),
            incomplete=incomplete,
        )

    def _run(self, run: _Run) -> tuple[Literal["waiting", "stopped"], datetime | None]:
        try:
            view = self._refresh(run)
        except _Stop as stop:
            self._record_stop(run, stop.reason)
            return "stopped", None
        now = run.at or view.clock
        woke_deadline = self._watch is not None and now >= self._watch.at
        woke_hold = self._hold_wake is not None and now >= self._hold_wake
        force = self._settled is None or woke_deadline or woke_hold
        dirty = False
        if woke_deadline and self._deadline_recheck(view, run):
            dirty = True
        cycle = _Cycle()
        # The state the loop last decided on. Not the last envelope's revision: a change that
        # lands during this run's last tool call has not been considered yet, so the next wake
        # must run a cycle for it.
        decided: tuple[int, int] | None = None
        try:
            for index in range(MAX_CYCLES):
                if dirty:
                    view = self._refresh(run)
                    dirty = False
                attempted, changed = self._verify_claims(view, run)
                if changed:
                    dirty = True
                    continue
                current = (view.revision, view.goal.version)
                decided = current
                if index == 0 and not (force or attempted) and current == self._settled:
                    break
                step = self._decide(view, run, cycle, woke_hold)
                if step == "again":
                    dirty = True
                    continue
                if step == "refresh":
                    view = self._refresh(run)
                    self._release_unneeded(view, run, keep=set())
                break
        except _Stop as stop:
            self._record_stop(run, stop.reason)
            return "stopped", None
        now = run.at or view.clock
        wait_until = self._compute_wait(view, now)
        if decided is not None:
            self._settled = decided
        return "waiting", wait_until

    # ------------------------------------------------------------------ state and evidence

    def _refresh(self, run: _Run) -> EventStateView:
        envelope = run.read("get_event_state", {})
        if envelope.status != "succeeded" or envelope.data is None:
            code = envelope.error.code if envelope.error is not None else envelope.status
            raise _Stop(f"the state read was {envelope.status} ({code})")
        view = EventStateView.model_validate(envelope.data)
        grant = self._own_grant(view)
        if view.episode_status == "closed":
            raise _Stop("the episode is closed")
        if view.clock >= view.goal.hard_end:
            raise _Stop(f"the event window ended at {self._t(view.goal.hard_end, view)}")
        if grant is None:
            raise _Stop(f"no grant is visible for {self._principal}")
        if not grant.valid_now:
            raise _Stop(f"grant {grant.grant.grant_id} is not valid now")
        self._interpret_new(view, run)
        self._refresh_answers(view)
        return view

    def _own_grant(self, view: EventStateView) -> GrantView | None:
        own = [g for g in view.grants if g.grant.principal_id == self._principal]
        return max(own, key=lambda g: g.version) if own else None

    def _interpret_new(self, view: EventStateView, run: _Run) -> None:
        day = event_local_date(view.goal, view.timezone)
        for record in view.observations:
            oid = record.observation.observation_id
            if oid in self._handled:
                continue
            interp = interpret_observation(
                record,
                resources=view.resources,
                event_date=day,
                timezone=view.timezone,
                goal=view.goal,
                event_id=view.event_id,
                handled=tuple(self._handled.values()),
            )
            self._handled[oid] = interp
            if record.observation.kind not in NOTICE_KINDS:
                continue
            self._record_notice(run, interp)
            self._retract(run, interp)
            if interp.applicable and interp.change_kind in ("delay", "unavailability"):
                self._claims[oid] = _Claim(interpretation=interp)
            elif interp.verify_subject_id is not None:
                self._claims[oid] = _Claim(interpretation=interp)  # verification only

    def _retract(self, run: _Run, interp: Interpretation) -> None:
        """A notice superseding an earlier notice of the same source withdraws its claim."""
        for ref in interp.retracts:
            claim = self._claims.get(ref)
            if claim is None or claim.answered_by is not None:
                continue
            claim.answered_by = interp.observation_id
            claim.evidence_status = "superseded"
            effect = (
                "it is no longer verified"
                if claim.verify_only
                else "its claim is no longer weighed"
            )
            self._record(
                run,
                "inapplicable",
                f"Notice {ref} is retracted by later notice {interp.observation_id} from the "
                f"same source ({interp.source_id}); {effect}.",
                observation_refs=(ref, interp.observation_id),
                details={"retracted": ref, "retracted_by": interp.observation_id},
            )

    def _record_notice(self, run: _Run, interp: Interpretation) -> None:
        oid = interp.observation_id
        tail = ""
        if interp.contains_instructions:
            tail = (
                f" Embedded instruction words ({', '.join(interp.instruction_words)}) are data"
                " and have no effect."
            )
        details: dict[str, Any] = {"interpretation": interp.model_dump(mode="json")}
        if interp.evidence_status == "duplicate":
            copy = "a forwarded copy of" if interp.claims.forwarded else "a repeat of"
            summary = (
                f"Notice {oid} is {copy} handled notice {interp.duplicate_of} (same correlation"
                " group and text): one evidence lineage, not corroboration. No plan change."
            )
            kind: DecisionKind = "duplicate"
        elif interp.evidence_status == "inapplicable":
            summary = (
                f"Notice {oid} does not apply to this event: "
                f"{'; '.join(interp.identity_failures)}. No plan change."
            )
            kind = "inapplicable"
        elif not interp.applicable:
            fields = interp.unresolved_fields
            candidates = interp.claims.subject_candidates
            if "wording" in fields:
                why = "is outside the supported message forms, so it is not read as a claim"
            elif "subject" in fields and candidates:
                why = (
                    f"names its resource ambiguously ('{interp.claims.entity_text}' matches "
                    f"{', '.join(candidates)})"
                )
            elif "subject" in fields:
                why = "names no registered resource that can be resolved"
            else:
                why = f"leaves {', '.join(fields) or 'its claim'} unresolved"
            summary = f"Notice {oid} {why}; left unresolved. No plan change."
            rid = interp.verify_subject_id
            if rid is not None:
                summary = (
                    f"Notice {oid} {why}; left unresolved and never weighed as a claim. It "
                    f"identifies {rid}, so the only step it can prompt is verification of {rid} "
                    "with its registered status source; no hypothesis, hold, ask or plan change "
                    "comes from the notice."
                )
                details["verify_only"] = rid
            kind = "unresolved"
        else:
            if interp.contains_instructions:
                run.notes.append(f"instruction words in {oid} ignored")
            return
        self._record(run, kind, summary + tail, observation_refs=(oid,), details=details)

    def _refresh_answers(self, view: EventStateView) -> None:
        """A typed status for the subject received after the notice answers its claim."""
        resources = _resources(view)
        for claim in self._claims.values():
            if claim.answered_by is not None:
                continue
            latest: tuple[str, ObservationRecord] | None = None
            for record in view.observations:
                obs = record.observation
                if obs.entity_id != claim.subject_id or obs.kind != "status":
                    continue
                if not _received_after(record, claim.interpretation):
                    continue
                latest = (obs.observation_id, record)
            if latest is None:
                continue
            oid, record = latest
            if record.structured is not None:
                status, eta = record.structured.domain_status, record.structured.reported_eta
            else:
                res = resources.get(claim.subject_id)
                if res is None or res.status_observation_id != oid:
                    continue
                status, eta = res.status, res.reported_eta
            claim.answered_by = oid
            claim.evidence_status = claim.assess(status, eta)

    def _material(self, view: EventStateView, claim: _Claim) -> list[Assignment]:
        """Not-started activities of the active plan that the claim would affect (for a
        verify-only notice: every not-started activity using its resource)."""
        res = _resources(view).get(claim.subject_id)
        if res is None or res.definition.kind != "equipment":
            return []
        if claim.verify_only and _recently_checked(view, claim.subject_id):
            # Typed status for this resource was fetched within its source's freshness window:
            # an unsupported notice does not justify spending another check.
            return []
        lifecycles = _lifecycles(view)
        interp = claim.interpretation
        eta = interp.claims.claimed_eta
        out: list[Assignment] = []
        for a in view.plan.assignments:
            if claim.subject_id not in a.resource_ids:
                continue
            if lifecycles.get(a.activity_id) not in NOT_STARTED:
                continue
            if (
                claim.verify_only
                or interp.change_kind == "unavailability"
                or (eta is not None and a.start < eta)
            ):
                out.append(a)
        return out

    # ------------------------------------------------------------------ verification

    def _verify_claims(self, view: EventStateView, run: _Run) -> tuple[bool, bool]:
        """Query the registered source for every material unanswered claim.

        Returns (attempted, state_changed)."""
        groups: dict[str, list[_Claim]] = {}
        for claim in self._claims.values():
            if claim.answered_by is not None or claim.verification_unavailable:
                continue
            if not self._material(view, claim):
                continue
            groups.setdefault(claim.subject_id, []).append(claim)
        attempted = changed = False
        resources = _resources(view)
        for rid, claims in sorted(groups.items()):
            res = resources[rid]
            fact = _status_fact(res)
            refs = tuple(c.observation_id for c in claims)
            if fact is None:
                attempted = True
                for c in claims:
                    c.verification_unavailable = True
                self._record(
                    run,
                    "verify",
                    f"{rid} has no registered status source; notice {', '.join(refs)} stays"
                    f" unverified.{_weight_note(claims)}",
                    observation_refs=refs,
                    details={
                        "entity_id": rid,
                        "outcome": "no_status_source",
                        "hearsay": [c.observation_id for c in claims if c.hearsay],
                        "verify_only": [c.observation_id for c in claims if c.verify_only],
                    },
                )
                continue
            while min(c.attempts for c in claims) < MAX_STATUS_ATTEMPTS:
                attempted = True
                envelope, record = self._query(run, rid, fact)
                for c in claims:
                    c.attempts += 1
                attempt = max(c.attempts for c in claims)
                if envelope.status == "succeeded":
                    changed = True
                    answer = record.observation.observation_id if record is not None else None
                    for c in claims:
                        c.answered_by = answer or envelope.call_id
                        if record is not None and record.structured is not None:
                            c.evidence_status = c.assess(
                                record.structured.domain_status, record.structured.reported_eta
                            )
                        elif not c.verify_only:
                            c.evidence_status = "superseded"
                    self._record(
                        run,
                        "verify",
                        f"Checked {rid} {fact} for notice {', '.join(refs)}: "
                        f"{_status_text(envelope, record, view)}; notice {_verdicts(claims)}.",
                        observation_refs=refs + ((answer,) if answer else ()),
                        tool_call_refs=(envelope.call_id,),
                        details=_verify_details(envelope, rid, fact, attempt)
                        | {"verify_only": [c.observation_id for c in claims if c.verify_only]},
                    )
                    break
                code = envelope.error.code if envelope.error is not None else None
                exhausted = attempt >= MAX_STATUS_ATTEMPTS or code == "STATUS_SOURCE_NOT_REGISTERED"
                if exhausted:
                    for c in claims:
                        c.verification_unavailable = True
                what = "the claim" if any(not c.verify_only for c in claims) else rid
                self._record(
                    run,
                    "verify",
                    f"Verification attempt {attempt} of {MAX_STATUS_ATTEMPTS} for {rid} {fact}"
                    f" (notice {', '.join(refs)}) returned {envelope.status}"
                    f"{f' ({code})' if code else ''}; {what} stays unverified"
                    f"{' and verification is now unavailable' if exhausted else ''}."
                    f"{_weight_note(claims) if exhausted else ''}",
                    observation_refs=refs,
                    tool_call_refs=(envelope.call_id,),
                    details=_verify_details(envelope, rid, fact, attempt)
                    | {
                        "hearsay": [c.observation_id for c in claims if c.hearsay],
                        "verify_only": [c.observation_id for c in claims if c.verify_only],
                    },
                )
                if exhausted:
                    break
        return attempted, changed

    def _deadline_recheck(self, view: EventStateView, run: _Run) -> bool:
        """On a deadline wake with the resource still not available, one fresh query."""
        watch = self._watch
        if watch is None:
            return False
        res = _resources(view).get(watch.resource_id)
        key = (watch.activity_id, watch.resource_id, watch.plan_version)
        if (
            res is None
            or res.status == "available"
            or view.plan.plan_version != watch.plan_version
            or _lifecycles(view).get(watch.activity_id) not in NOT_STARTED
            or key in self._deadline_rechecked
        ):
            return False
        self._deadline_rechecked.add(key)
        fact = _status_fact(res)
        if fact is None:
            return False
        envelope, record = self._query(run, watch.resource_id, fact)
        pending = [
            c
            for c in self._claims.values()
            if c.subject_id == watch.resource_id and c.answered_by is None
        ]
        if envelope.status == "succeeded":
            answer = record.observation.observation_id if record is not None else None
            for c in pending:
                c.answered_by = answer or envelope.call_id
                if record is not None and record.structured is not None:
                    c.evidence_status = c.assess(
                        record.structured.domain_status, record.structured.reported_eta
                    )
                elif not c.verify_only:
                    c.evidence_status = "superseded"
        self._record(
            run,
            "verify",
            f"{watch.resource_id} is still not available ahead of {watch.activity_id} at "
            f"{self._t(_start_of(view, watch.activity_id), view)}; fresh check of {fact}: "
            f"{_status_text(envelope, record, view)}.",
            observation_refs=tuple(c.observation_id for c in pending)
            + ((record.observation.observation_id,) if record is not None else ()),
            tool_call_refs=(envelope.call_id,),
            details=_verify_details(envelope, watch.resource_id, fact, 1)
            | {"purpose": "deadline_watch"},
        )
        return envelope.status == "succeeded"

    def _query(
        self, run: _Run, rid: str, fact: str
    ) -> tuple[ToolEnvelope, ObservationRecord | None]:
        args = QueryStatusArgs(entity_id=rid, fact=fact).model_dump(mode="json")
        envelope = run.read("query_status", args)
        record = None
        if envelope.status == "succeeded" and envelope.data and envelope.data.get("observation"):
            record = ObservationRecord.model_validate(envelope.data["observation"])
        return envelope, record

    # ------------------------------------------------------------------ decision

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
            )
            return None
        return EvaluationResult.model_validate(envelope.data)

    def _unweighed_hearsay(self, view: EventStateView) -> list[_Claim]:
        """Material hearsay claims whose verification is unavailable (never hypotheses)."""
        return [
            c
            for c in self._claims.values()
            if c.hearsay
            and c.answered_by is None
            and c.verification_unavailable
            and self._material(view, c)
        ]

    def _hypotheses(self, view: EventStateView) -> tuple[Hypothesis, ...]:
        """The claimed outcome of every material claim whose verification is unavailable and
        whose source can report it (hearsay is never a declared outcome)."""
        chosen: dict[str, _Claim] = {}
        for claim in self._claims.values():
            if claim.answered_by is not None or not claim.verification_unavailable:
                continue
            if claim.hearsay or claim.verify_only:
                continue
            interp = claim.interpretation
            if interp.change_kind == "delay" and interp.claims.claimed_eta is None:
                continue
            if not self._material(view, claim):
                continue
            current = chosen.get(claim.subject_id)
            if current is None or _stronger(claim, current):
                chosen[claim.subject_id] = claim
        hypotheses: list[Hypothesis] = []
        for rid, claim in sorted(chosen.items()):
            interp = claim.interpretation
            if interp.change_kind == "unavailability":
                hypotheses.append(
                    Hypothesis(
                        resource_id=rid,
                        assume_status="unavailable",
                        label=f"claimed cancellation from {claim.observation_id}",
                    )
                )
            else:
                hypotheses.append(
                    Hypothesis(
                        resource_id=rid,
                        assume_ready_at=interp.claims.claimed_eta,
                        label=f"claimed ETA from {claim.observation_id}",
                    )
                )
        return tuple(hypotheses)

    def _decide(self, view: EventStateView, run: _Run, cycle: _Cycle, woke_hold: bool) -> Step:
        cycle.blocked.clear()
        ev = self._evaluate(run, ())
        if ev is None:
            return "done"
        hypotheses = self._hypotheses(view)
        robust: set[str] | None = None
        robust_note = ""
        if hypotheses:
            labels = ", ".join(h.label for h in hypotheses)
            ev_h = self._evaluate(run, hypotheses)
            if ev_h is None:
                robust_note = f"robustness check under {labels} was not available"
            else:
                both = _feasible(ev) & _feasible(ev_h)
                if both:
                    robust = both
                    robust_note = (
                        f"restricted to candidates feasible both on current evidence and under "
                        f"{labels} (hypothetical evaluation {ev_h.evaluation_id})"
                    )
                else:
                    robust_note = (
                        f"no candidate is feasible both on current evidence and under {labels} "
                        f"(hypothetical evaluation {ev_h.evaluation_id}); deciding on current "
                        "evidence only"
                    )
        hearsay = self._unweighed_hearsay(view)
        apply_note = robust_note
        if hearsay:
            note = (
                f"unverified hearsay notice {', '.join(c.observation_id for c in hearsay)} is "
                "not weighed as a declared outcome"
            )
            apply_note = f"{robust_note}; {note}" if robust_note else note

        def eligible(c: CandidateResult) -> bool:
            return robust is None or c.signature in robust

        keep = _candidate(ev, ev.keep_candidate_id)
        if keep is not None and keep.applicable_now and eligible(keep):
            # The keep narration lists every claim, hearsay included.
            self._record_keep(view, run, ev, keep, robust_note)
            self._release_unneeded(view, run, keep=set())
            return "done"
        target = next(
            (
                c
                for c in ev.candidates
                if c.applicable_now and eligible(c) and c.candidate_id != ev.keep_candidate_id
            ),
            None,
        )
        if target is not None:
            return self._apply(view, run, ev, target, keep, cycle, apply_note)
        feasible = [
            c
            for c in ev.candidates
            if c.constraint_status == "feasible_under_assumptions" and eligible(c)
        ]
        if not feasible:
            unknown = [c for c in ev.candidates if c.constraint_status == "unknown"]
            if unknown:
                self._record_undecided(view, run, ev, unknown)
            else:
                self._record_infeasible(view, run, ev)
            self._release_unneeded(view, run, keep=set())
            return "done"
        for cand in feasible:
            step = self._prepare(view, run, ev, cand, cycle, woke_hold)
            if step is not None:
                return step
        best = feasible[0]
        blockers = list(dict.fromkeys(cycle.blocked)) or ["no applicable preparation step"]
        self._record_once(
            run,
            ("wait", "blocked", ev.goal_version, view.plan.plan_version, tuple(blockers)),
            "wait",
            f"No candidate can be applied now; the best feasible option is {best.label}. "
            f"Not prepared because: {'; '.join(blockers)}. Plan v{view.plan.plan_version} is "
            "kept unchanged.",
            candidate_refs=(best.candidate_id,),
            details={"evaluation_id": ev.evaluation_id, "blockers": blockers},
        )
        keep_ids = {
            rh.bound_hold_id for c in feasible for rh in c.required_holds if rh.bound_hold_id
        }
        self._release_unneeded(view, run, keep=keep_ids)
        return "done"

    def _apply(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        target: CandidateResult,
        keep: CandidateResult | None,
        cycle: _Cycle,
        robust_note: str,
    ) -> Step:
        if run.mutations_blocked:
            return "done"
        args = ApplyPlanArgs(
            candidate_plan_id=target.candidate_id, constraint_report_ref=target.report_id
        ).model_dump(mode="json")
        result = self._mutate(
            run,
            "apply_plan",
            args,
            expected_revision=ev.revision,
            expected_goal_version=ev.goal_version,
        )
        if result is None:
            return "done"
        if result.applied and result.receipt is not None:
            receipt = result.receipt
            failed = (
                [ch.constraint_id for ch in keep.checks if ch.status == "failed"] if keep else []
            )
            why = f"; the current plan fails {', '.join(failed)}" if failed else ""
            robust = f"; {robust_note}" if robust_note else ""
            self._record(
                run,
                "commit",
                f"Applied {target.label} ({target.candidate_id}): changed "
                f"{', '.join(target.changed_activity_ids) or 'no activity'}, additional committed "
                f"{target.incremental_committed_cents} cents, revision {receipt.revision_before}"
                f" -> {receipt.revision_after}{why}{robust}.",
                candidate_refs=(target.candidate_id,),
                receipt_refs=(receipt.receipt_id,),
                tool_call_refs=result.call_ids,
                details={
                    "evaluation_id": ev.evaluation_id,
                    "report_id": target.report_id,
                    "reconciled": result.reconciled,
                    "assumptions": [a.text for a in target.assumptions],
                },
            )
            if self._open_request is not None and self._open_request.signature == target.signature:
                self._open_request = None
                self._hold_wake = None
            return "refresh"
        code = result.error_code
        if code in RETRYABLE_REJECTIONS and cycle.stale_retries < MAX_STALE_RETRIES:
            cycle.stale_retries += 1
            run.notes.append(f"apply_plan rejected with {code}; re-read and re-evaluated")
            return "again"
        self._record(
            run,
            "wait",
            f"apply_plan for {target.label} was rejected ({code}); plan "
            f"v{view.plan.plan_version} is unchanged.",
            candidate_refs=(target.candidate_id,),
            receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
            tool_call_refs=result.call_ids,
            details={"error_code": code},
        )
        return "done"

    def _prepare(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        cand: CandidateResult,
        cycle: _Cycle,
        woke_hold: bool,
    ) -> Step | None:
        """Make a feasible booking candidate applicable: verify, hold, ask. None = not
        actionable within the grant."""
        missing = cand.authorization.missing
        other = [m for m in missing if m.kind != "committed_spend_limit"]
        if other:
            cycle.blocked.extend(f"{cand.label}: {m.kind} ({m.detail})" for m in other)
            return None
        resources = _resources(view)
        unbound = [rh for rh in cand.required_holds if rh.bound_hold_id is None]
        for rh in cand.required_holds:
            res = resources.get(rh.resource_id)
            fact = _status_fact(res) if res is not None else None
            if res is None or fact is None or res.status_basis != "catalog":
                continue
            attempts = self._substitute_attempts.get(rh.resource_id, 0)
            if attempts >= MAX_STATUS_ATTEMPTS:
                continue
            self._substitute_attempts[rh.resource_id] = attempts + 1
            envelope, record = self._query(run, rh.resource_id, fact)
            self._record(
                run,
                "verify",
                f"Checked {rh.resource_id} {fact} before preparing {cand.label}, whose "
                f"availability rests on the catalog: {_status_text(envelope, record, view)}.",
                observation_refs=(record.observation.observation_id,) if record else (),
                tool_call_refs=(envelope.call_id,),
                candidate_refs=(cand.candidate_id,),
                details=_verify_details(envelope, rh.resource_id, fact, attempts + 1)
                | {"purpose": "substitute"},
            )
            if envelope.status == "succeeded":
                return "again"
        grant = self._own_grant(view)
        if grant is None:
            cycle.blocked.append("no own grant is visible")
            return None
        if unbound:
            if run.mutations_blocked:
                return "done"
            exposure = sum(
                resources[rh.resource_id].definition.terms.reserved_exposure_cents
                for rh in unbound
                if rh.resource_id in resources
            )
            fees = sum(
                resources[rh.resource_id].definition.terms.hold_fee_cents
                for rh in unbound
                if rh.resource_id in resources
            )
            headroom = grant.grant.max_total_reserved_cents - grant.reserved_used_cents
            fee_room = grant.grant.max_total_committed_cents - grant.committed_used_cents
            effective = (run.at or view.clock) + timedelta(
                minutes=view.tool_durations_minutes.get("hold_resource", 0)
            )
            late = [
                rh.resource_id
                for rh in unbound
                if rh.commitment_cutoff is not None and effective >= rh.commitment_cutoff
            ]
            if exposure > headroom:
                cycle.blocked.append(
                    f"{cand.label}: reserved exposure {exposure} cents exceeds the remaining "
                    f"reserved limit {headroom} cents"
                )
                return None
            if exposure + fees > view.budget.remaining_cents:
                cycle.blocked.append(
                    f"{cand.label}: exposure {exposure + fees} cents exceeds the remaining "
                    f"budget {view.budget.remaining_cents} cents"
                )
                return None
            if fees > fee_room:
                cycle.blocked.append(
                    f"{cand.label}: hold fee {fees} cents exceeds the committed limit"
                )
                return None
            if late:
                cycle.blocked.append(
                    f"{cand.label}: commitment cutoff passed for {', '.join(late)}"
                )
                return None
            rh = unbound[0]
            count_key = (rh.resource_id, rh.activity_id, grant.version)
            if self._hold_counts.get(count_key, 0) >= MAX_HOLDS_PER_OPTION:
                cycle.blocked.append(
                    f"{cand.label}: {rh.resource_id} was already held {MAX_HOLDS_PER_OPTION} "
                    "times without an authorization answer"
                )
                return None
            args = HoldResourceArgs(
                resource_id=rh.resource_id,
                activity_id=rh.activity_id,
                window=rh.window,
                hold_minutes=None,
            ).model_dump(mode="json")
            result = self._mutate(run, "hold_resource", args, expected_revision=ev.revision)
            if result is None:
                return "done"
            if result.applied and result.receipt is not None:
                self._hold_counts[count_key] = self._hold_counts.get(count_key, 0) + 1
                hold = _hold_from(result)
                expiry = f", expires {self._t(hold.expires_at, view)}" if hold else ""
                self._record(
                    run,
                    "prepare",
                    f"Held {rh.resource_id} for {rh.activity_id} "
                    f"{self._t(rh.window.start, view)}-{self._t(rh.window.end, view)}"
                    f"{f' (hold {hold.hold_id}{expiry})' if hold else ''} to keep {cand.label} "
                    f"open; reserved exposure {exposure} cents within the reserved limit "
                    f"{grant.grant.max_total_reserved_cents}.",
                    candidate_refs=(cand.candidate_id,),
                    receipt_refs=(result.receipt.receipt_id,),
                    tool_call_refs=result.call_ids,
                    details={"evaluation_id": ev.evaluation_id, "reconciled": result.reconciled},
                )
                return "again"
            code = result.error_code
            if code in RETRYABLE_REJECTIONS and cycle.stale_retries < MAX_STALE_RETRIES:
                cycle.stale_retries += 1
                return "again"
            self._record(
                run,
                "prepare",
                f"Hold of {rh.resource_id} for {rh.activity_id} was rejected ({code}); no "
                "reservation was made.",
                candidate_refs=(cand.candidate_id,),
                receipt_refs=(result.receipt.receipt_id,) if result.receipt is not None else (),
                tool_call_refs=result.call_ids,
                details={"error_code": code, "outcome": "rejected"},
            )
            return "done"
        if not missing:
            cycle.blocked.append(f"{cand.label}: not applicable although no permission is missing")
            return None
        return self._ask(view, run, ev, cand, grant, woke_hold)

    def _ask(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        cand: CandidateResult,
        grant: GrantView,
        woke_hold: bool,
    ) -> Step:
        holds = {h.hold_id: h for h in view.holds}
        bound = tuple(rh.bound_hold_id for rh in cand.required_holds if rh.bound_hold_id)
        expiries = [holds[h].expires_at for h in bound if h in holds]
        # Wake early enough that an apply issued then still takes effect while the hold is live:
        # the planner judges hold liveness when the apply takes effect (clock + its duration).
        apply_lead = timedelta(minutes=view.tool_durations_minutes.get("apply_plan", 0))
        self._hold_wake = min(expiries) - ASK_LEAD - apply_lead if expiries else None
        booking = cand.required_holds[0].resource_id if cand.required_holds else ""
        current = grant.grant.max_total_committed_cents
        requested = grant.committed_used_cents + cand.incremental_committed_cents
        open_req = self._open_request
        same = (
            open_req is not None
            and open_req.grant_version == grant.version
            and open_req.signature == cand.signature
            and open_req.request.requested_value == requested
            and open_req.request.resource_id == booking
        )
        if same and open_req is not None:
            open_req.hold_ids = bound
            if woke_hold:
                self._record_once(
                    run,
                    ("wait", "ask", open_req.request.request_id, bound),
                    "wait",
                    f"Authorization request {open_req.request.request_id} is still unanswered; "
                    f"hold {', '.join(bound) or 'none'} keeps {cand.label} open until "
                    f"{', '.join(self._t(t, view) for t in expiries) or 'its expiry'}.",
                    candidate_refs=(cand.candidate_id,),
                )
            self._release_unneeded(view, run, keep=set(bound))
            return "done"
        request = AuthorizationRequest(
            request_id=f"authreq_r{ev.revision}_{cand.signature[:8]}",
            target_grant_id=grant.grant.grant_id,
            field="max_total_committed_cents",
            current_value=current,
            requested_value=requested,
            resource_id=booking,
            candidate_id=cand.candidate_id,
            reason=_ask_reason(grant.grant.grant_id, current, requested, cand, booking),
        )
        self._open_request = _OpenRequest(
            request=request, grant_version=grant.version, signature=cand.signature, hold_ids=bound
        )
        until = f" until {self._t(min(expiries), view)}" if expiries else ""
        self._record(
            run,
            "ask",
            f"Asked the organizer to raise max_total_committed_cents of {grant.grant.grant_id} "
            f"from {current} to {requested} cents so {cand.label} can be applied; "
            f"hold {', '.join(bound) or 'none'} keeps the option open{until}.",
            candidate_refs=(cand.candidate_id,),
            authorization_request=request,
            wait_until=self._hold_wake,
            details={
                "evaluation_id": ev.evaluation_id,
                "missing": [m.model_dump(mode="json") for m in cand.authorization.missing],
            },
        )
        self._release_unneeded(view, run, keep=set(bound))
        return "done"

    def _record_keep(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        keep: CandidateResult,
        robust_note: str,
    ) -> None:
        resources = _resources(view)
        lifecycles = _lifecycles(view)
        if not any(state in NOT_STARTED for state in lifecycles.values()):
            # Nothing is left to plan; "passes every hard check" would read as success.
            failed = sorted(a for a, s in lifecycles.items() if s in ("failed", "canceled"))
            done = sorted(a for a, s in lifecycles.items() if s == "completed")
            running = sorted(a for a, s in lifecycles.items() if s == "started")
            parts = [
                f"No activity remains to re-plan in plan v{view.plan.plan_version}: completed "
                f"{', '.join(done) or 'none'}; in progress {', '.join(running) or 'none'}; "
                f"failed {', '.join(failed) or 'none'}. No action can change these records"
            ]
        else:
            parts = [
                f"Keep plan v{view.plan.plan_version}: it passes every hard check under its "
                "stated assumptions"
            ]
        used: list[str] = []
        for a in sorted(view.plan.assignments, key=lambda x: x.start):
            if lifecycles.get(a.activity_id) not in NOT_STARTED:
                continue
            for rid in a.resource_ids:
                res = resources.get(rid)
                if res is not None and res.definition.kind == "equipment" and rid not in used:
                    used.append(rid)
                    eta = (
                        f", reported ETA {self._t(res.reported_eta, view)}"
                        if res.reported_eta is not None
                        else ""
                    )
                    parts.append(
                        f"{rid} is {res.status} ({res.status_basis.replace('_', ' ')}{eta}) for "
                        f"{a.activity_id} at {self._t(a.start, view)}"
                    )
        for claim in self._claims.values():
            if claim.verify_only and claim.answered_by is not None:
                how = (
                    "retracted by"
                    if claim.evidence_status == "superseded"
                    else "verified only, answered by"
                )
                parts.append(
                    f"notice {claim.observation_id} (not a supported message form) {how} "
                    f"{claim.answered_by}"
                )
            elif claim.verify_only and claim.verification_unavailable:
                parts.append(
                    f"notice {claim.observation_id} (not a supported message form) unverified, "
                    "never weighed as a claim"
                )
            elif claim.answered_by is not None:
                parts.append(
                    f"notice {claim.observation_id} {claim.evidence_status} by {claim.answered_by}"
                )
            elif claim.verification_unavailable and claim.hearsay:
                parts.append(
                    f"notice {claim.observation_id} unverified hearsay from "
                    f"{claim.interpretation.submitted_by or claim.interpretation.source_id}, "
                    "not weighed as a declared outcome"
                )
            elif claim.verification_unavailable:
                parts.append(f"notice {claim.observation_id} unverified")
            elif not self._material(view, claim):
                parts.append(f"notice {claim.observation_id} not material for the current plan")
        if robust_note:
            parts.append(robust_note)
        summary = "; ".join(parts) + "."
        self._record_once(
            run,
            ("keep", view.plan.plan_version, ev.goal_version, summary),
            "keep",
            summary,
            observation_refs=tuple(self._claims),
            candidate_refs=(keep.candidate_id,),
            details={
                "evaluation_id": ev.evaluation_id,
                "assumptions": [a.text for a in keep.assumptions],
            },
        )

    def _record_undecided(
        self,
        view: EventStateView,
        run: _Run,
        ev: EvaluationResult,
        unknown: list[CandidateResult],
    ) -> None:
        """Nothing is feasible, but some candidates rest on an unsupported requirement: they
        are undecided, not infeasible, so the decision is ``unresolved``."""
        unsupported: dict[str, str] = {}
        for c in unknown:
            for check in c.checks:
                if check.status == "unsupported":
                    unsupported.setdefault(check.constraint_id, check.detail)
        infeasible = [c for c in ev.candidates if c.constraint_status == "infeasible"]
        blocking = sorted(
            {ch.constraint_id for c in infeasible for ch in c.checks if ch.status == "failed"}
        )
        requirement = "; ".join(
            f"{cid}: {detail.rstrip('. ')}" for cid, detail in sorted(unsupported.items())
        )
        shown = ", ".join(c.label for c in unknown[:3])
        more = f" and {len(unknown) - 3} more" if len(unknown) > 3 else ""
        others = (
            f" The other {len(infeasible)} fail {', '.join(blocking) or 'a hard check'}."
            if infeasible
            else ""
        )
        inf = ev.infeasibility
        self._record_once(
            run,
            (
                "unresolved",
                "undecided",
                ev.goal_version,
                view.plan.plan_version,
                tuple(sorted(unsupported)),
                tuple(sorted(c.signature for c in unknown)),
            ),
            "unresolved",
            f"No candidate is established feasible at revision {ev.revision}: {len(unknown)} "
            f"could not be decided because a requirement is unsupported "
            f"({requirement or 'unsupported check'}): {shown}{more}.{others} Plan "
            f"v{view.plan.plan_version} is kept unchanged and no booking or spend is made.",
            observation_refs=tuple(self._claims),
            candidate_refs=tuple(c.candidate_id for c in unknown[:8]),
            details={
                "evaluation_id": ev.evaluation_id,
                "revision": ev.revision,
                "goal_version": ev.goal_version,
                "unsupported_requirements": [
                    {"constraint_id": cid, "detail": detail}
                    for cid, detail in sorted(unsupported.items())
                ],
                "undecided_candidate_ids": [c.candidate_id for c in unknown],
                "blocking_constraints": blocking,
                "declared_action_space": inf.declared_action_space if inf else None,
                "detail": inf.detail if inf else None,
            },
        )

    def _record_infeasible(self, view: EventStateView, run: _Run, ev: EvaluationResult) -> None:
        inf = ev.infeasibility
        if inf is None:
            return
        blocking = tuple(inf.blocking_constraints)
        self._record_once(
            run,
            ("infeasible", ev.goal_version, view.plan.plan_version, blocking),
            "infeasible",
            f"No candidate in the declared action space ({inf.declared_action_space}) is "
            f"feasible at revision {ev.revision}: blocking constraints "
            f"{', '.join(blocking) or 'none named'}. Plan v{view.plan.plan_version} is preserved "
            "and no booking or spend is made.",
            observation_refs=tuple(self._claims),
            details={
                "evaluation_id": ev.evaluation_id,
                "revision": ev.revision,
                "goal_version": ev.goal_version,
                "blocking_constraints": list(blocking),
                "declared_action_space": inf.declared_action_space,
                "detail": inf.detail,
            },
        )

    # ------------------------------------------------------------------ holds and mutations

    def _release_unneeded(self, view: EventStateView, run: _Run, keep: set[str]) -> None:
        """Release own active holds the active plan does not use and the chosen option
        does not need."""
        for hold in view.holds:
            if hold.actor_id != self._principal or hold.effective_status != "active":
                continue
            if hold.hold_id in keep or _plan_uses(view, hold):
                continue
            if run.mutations_blocked or run.revision is None:
                return
            args = ReleaseHoldArgs(
                hold_id=hold.hold_id,
                reason=f"not needed by active plan v{view.plan.plan_version}",
            ).model_dump(mode="json")
            result = self._mutate(run, "release_hold", args, expected_revision=run.revision)
            if result is None:
                return
            if result.applied and result.receipt is not None:
                self._record(
                    run,
                    "release",
                    f"Released hold {hold.hold_id} on {hold.resource_id} for "
                    f"{hold.activity_id}: active plan v{view.plan.plan_version} does not use it; "
                    f"{hold.reserved_cents} reserved cents returned.",
                    receipt_refs=(result.receipt.receipt_id,),
                    tool_call_refs=result.call_ids,
                )
                if self._open_request is not None and hold.hold_id in self._open_request.hold_ids:
                    self._open_request = None
                    self._hold_wake = None
            else:
                run.notes.append(f"release of {hold.hold_id} not applied ({result.error_code})")

    def _mutate(
        self,
        run: _Run,
        tool: str,
        arguments: dict[str, Any],
        *,
        expected_revision: int,
        expected_goal_version: int | None = None,
    ) -> _Mutation | None:
        """One mutation with lost-response reconciliation under the original key.

        Returns None when the outcome could not be established (mutations then stop for
        this run)."""
        key = idempotency_key(expected_revision, tool, arguments)
        request = sha256_hex(
            canonical_json([tool, arguments, expected_revision, expected_goal_version])
        )
        if self._own_keys.setdefault(key, request) != request:
            # Two different intents would share one key; the executor would reject the second
            # as an idempotency conflict, so it is not sent.
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
            return _Mutation(envelope, envelope.receipt, (envelope.call_id,))
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
                return _Mutation(lookup, receipt, tuple(calls), reconciled=True)
            if retried:
                continue
            retried = True
            try:
                envelope = send()
                calls.append(envelope.call_id)
                return _Mutation(envelope, envelope.receipt, tuple(calls), reconciled=True)
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
            details={"idempotency_key": key, "tool": tool},
        )
        return None

    # ------------------------------------------------------------------ waiting

    def _compute_wait(self, view: EventStateView, now: datetime) -> datetime | None:
        self._watch = self._deadline_watch(view, now)
        times: list[datetime] = []
        if self._watch is not None:
            times.append(self._watch.at)
        if self._open_request is None or (self._hold_wake is not None and self._hold_wake <= now):
            self._hold_wake = None
        if self._hold_wake is not None:
            times.append(self._hold_wake)
        return min(times) if times else None

    def _deadline_watch(self, view: EventStateView, now: datetime) -> _Watch | None:
        """Earliest not-started activity relying on expected equipment: wake at
        min(start - 5 min, reported ETA + 1 min)."""
        resources = _resources(view)
        lifecycles = _lifecycles(view)
        for a in sorted(view.plan.assignments, key=lambda x: (x.start, x.activity_id)):
            if lifecycles.get(a.activity_id) not in NOT_STARTED:
                continue
            for rid in a.resource_ids:
                res = resources.get(rid)
                if res is None or res.definition.kind != "equipment" or res.status != "expected":
                    continue
                options = [a.start - DEADLINE_LEAD]
                if res.reported_eta is not None:
                    options.append(res.reported_eta + ETA_GRACE)
                future = [t for t in options if t > now]
                if future:
                    return _Watch(min(future), a.activity_id, rid, view.plan.plan_version)
        return None

    # ------------------------------------------------------------------ narration

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
        if run.at is None or run.revision is None:
            run.notes.append(f"{kind} not recorded: no scenario time or revision observed")
            return
        self._seq += 1
        run.decisions.append(
            PolicyDecision(
                decision_id=f"dec_{self._seq:04d}",
                policy_id=POLICY_ID,
                at=run.at,
                revision=run.revision,
                kind=kind,
                summary=summary,
                observation_refs=observation_refs,
                tool_call_refs=tool_call_refs,
                candidate_refs=candidate_refs,
                receipt_refs=receipt_refs,
                authorization_request=authorization_request,
                wait_until=wait_until,
                details=details or {},
            )
        )

    def _record_once(
        self, run: _Run, signature: tuple[Any, ...], kind: DecisionKind, summary: str, **kw: Any
    ) -> None:
        """Record a state-level decision unless an identical one was already recorded."""
        if signature in self._recorded:
            return
        self._recorded.add(signature)
        self._record(run, kind, summary, **kw)

    def _record_stop(self, run: _Run, reason: str) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._record(run, "stop", f"Stopped: {reason}. No further action.")

    def _t(self, value: datetime, view: EventStateView) -> str:
        return local_label(value, view.timezone)


# ---------------------------------------------------------------------- helpers


def _resources(view: EventStateView) -> dict[str, ResourceView]:
    return {r.definition.resource_id: r for r in view.resources}


def _lifecycles(view: EventStateView) -> dict[str, str]:
    return {a.definition.activity_id: a.lifecycle for a in view.activities}


def _start_of(view: EventStateView, activity_id: str) -> datetime:
    for a in view.plan.assignments:
        if a.activity_id == activity_id:
            return a.start
    return view.clock


def _status_fact(res: ResourceView) -> str | None:
    terms = res.definition.terms
    if terms.status_source_id is None or not terms.queryable_facts:
        return None
    return terms.queryable_facts[0]


def _received_after(record: ObservationRecord, interp: Interpretation) -> bool:
    return (record.observation.received_at, record.revision_after) > (
        interp.received_at,
        interp.revision_after,
    )


def _stronger(a: _Claim, b: _Claim) -> bool:
    """Cancellation over delay; between delays the later claimed ETA, then the later notice."""
    ia, ib = a.interpretation, b.interpretation
    if (ia.change_kind == "unavailability") != (ib.change_kind == "unavailability"):
        return ia.change_kind == "unavailability"
    ea, eb = ia.claims.claimed_eta, ib.claims.claimed_eta
    if ea is not None and eb is not None and ea != eb:
        return ea > eb
    return (ia.received_at, ia.revision_after) > (ib.received_at, ib.revision_after)


def _feasible(ev: EvaluationResult) -> set[str]:
    return {
        c.signature for c in ev.candidates if c.constraint_status == "feasible_under_assumptions"
    }


def _candidate(ev: EvaluationResult, candidate_id: str | None) -> CandidateResult | None:
    if candidate_id is None:
        return None
    return next((c for c in ev.candidates if c.candidate_id == candidate_id), None)


def _plan_uses(view: EventStateView, hold: HoldView) -> bool:
    for a in view.plan.assignments:
        if (
            a.activity_id == hold.activity_id
            and hold.resource_id in a.resource_ids
            and hold.window.contains(a.window)
        ):
            return True
    return False


def _hold_from(result: _Mutation) -> HoldView | None:
    data = result.envelope.data if result.envelope is not None else None
    if data and isinstance(data.get("hold"), dict):
        return HoldView.model_validate(data["hold"])
    return None


def _status_text(
    envelope: ToolEnvelope, record: ObservationRecord | None, view: EventStateView
) -> str:
    if envelope.status != "succeeded":
        code = envelope.error.code if envelope.error is not None else None
        return f"{envelope.status}{f' ({code})' if code else ''}"
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


def _verdicts(claims: list[_Claim]) -> str:
    """Each notice's standing after a typed answer; a verify-only notice is not a claim."""
    return ", ".join(
        f"{c.observation_id} verified only (not a supported message form, not weighed as a claim)"
        if c.verify_only
        else f"{c.observation_id} {c.evidence_status}"
        for c in claims
    )


def _weight_note(claims: list[_Claim]) -> str:
    """How unverified claims are weighed: as declared outcomes, or not at all as hearsay or a
    verify-only notice."""
    hearsay = [c for c in claims if c.hearsay]
    unweighed = [c for c in claims if c.verify_only]
    weighed = [c for c in claims if not c.hearsay and not c.verify_only]
    parts: list[str] = []
    if weighed:
        parts.append(
            f" Notice {', '.join(c.observation_id for c in weighed)} is weighed only as a "
            "declared outcome."
        )
    if unweighed:
        parts.append(
            f" Notice {', '.join(c.observation_id for c in unweighed)} is not a supported "
            "message form: it can only prompt verification and is never weighed as a claim."
        )
    for c in hearsay:
        who = c.interpretation.submitted_by or c.interpretation.source_id
        parts.append(
            f" Notice {c.observation_id} is hearsay ({who} via {c.interpretation.channel} does "
            f"not speak for {c.subject_id}), so it is not weighed as a declared outcome."
        )
    return "".join(parts)


def _ask_reason(
    grant_id: str, current: int, requested: int, cand: CandidateResult, booking: str
) -> str:
    """One sentence with the exact missing permission, within ``ASK_REASON_LIMIT``. The
    candidate label is dropped, then the candidate, when the sentence would not fit."""
    permission = (
        "Missing permission: increase committed spending (max_total_committed_cents) of "
        f"{grant_id} from {current} to {requested} cents"
    )
    commits = f"can commit {cand.incremental_committed_cents} cents for {booking}"
    options = (
        f"{permission} so {cand.label} ({cand.candidate_id}) {commits}.",
        f"{permission} so candidate {cand.candidate_id} {commits}.",
        f"{permission}.",
    )
    return next((o for o in options if len(o) <= ASK_REASON_LIMIT), options[-1])


def _verify_details(envelope: ToolEnvelope, rid: str, fact: str, attempt: int) -> dict[str, Any]:
    return {
        "entity_id": rid,
        "fact": fact,
        "attempt": attempt,
        "outcome": envelope.status,
        "error_code": envelope.error.code if envelope.error is not None else None,
    }


def _recently_checked(view: EventStateView, resource_id: str) -> bool:
    """A successful status check of the resource completed within its source's freshness
    window (contract section 9)."""
    window = {e: src.freshness_minutes for src in view.status_sources for e in src.entity_ids}.get(
        resource_id
    )
    if window is None:
        return False
    return any(
        c.entity_id == resource_id
        and c.envelope_status == "succeeded"
        and c.completed_at is not None
        and view.clock - c.completed_at <= timedelta(minutes=window)
        for c in view.status_checks
    )
