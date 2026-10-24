"""The closed action menu of the live agent.

Built from the visible state and one stored evaluation, before the model is asked. Every option
carries the exact tool, arguments and expectations the server will send; the model only picks an
``option_id``, and any id outside the menu is rejected. Options:

* ``keep``: the keep candidate is applicable now (and robust, when a robustness set applies);
* ``query:<entity>:<fact>``: a registered status source in the grant's scope, offered only for a
  stated verification need (an unanswered notice, a catalog-only substitute, a deadline watch)
  that no successful check requested since has answered, while fewer than
  ``MAX_STATUS_FAILURES`` of this principal's checks since then failed;
* ``hold:<resource>:<activity>:<HHMM>-<HHMM>``: an unbound required hold of a feasible candidate,
  offered when the grant's scope, reserved and committed limits, the budget, the cutoff and the
  per-option hold count allow it, and no better-ranked candidate is applicable;
* ``apply:<candidate_id>``: a stored candidate that is applicable now (its report id is attached
  by the server);
* ``ask:<candidate_id>``: an ``AuthorizationRequest`` for a feasible candidate whose only missing
  permission is committed spending and whose required holds are bound, unless the same request
  is already open;
* ``release:<hold_id>``: an active hold of this principal that the active plan does not use
  (while the plan is in question, also one that no eligible feasible candidate binds);
* ``wait``: no action until the stated time.

Apply, hold and ask are offered only while the plan is in question: the keep candidate is not
applicable (or not robust), or an unanswered material notice threatens it. Otherwise the menu is
keep and wait (plus releases), and a menu without a real choice needs no model call.

Intents (``intent``) name the same choice independently of evaluation-scoped ids, so a menu can
be compared across evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from plan_b.domain.models import (
    ApplyPlanArgs,
    AuthorizationRequest,
    CandidateResult,
    EvaluationResult,
    EventStateView,
    GrantView,
    HoldResourceArgs,
    QueryStatusArgs,
    ReleaseHoldArgs,
)
from plan_b.domain.timeutil import local_label

MAX_STATUS_FAILURES = 2
MAX_HOLDS_PER_OPTION = 2
MAX_APPLY_OPTIONS = 6
MAX_HOLD_OPTIONS = 3
ASK_REASON_LIMIT = 400
NOT_STARTED = ("planned", "ready")

MenuAction = Literal[
    "keep", "wait", "query_status", "hold_resource", "apply_plan", "ask", "release_hold"
]


@dataclass(frozen=True)
class MenuOption:
    option_id: str
    action: MenuAction
    intent: str
    summary: str
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    expected_revision: int | None = None
    expected_goal_version: int | None = None
    candidate_id: str | None = None
    report_id: str | None = None
    signature: str | None = None
    hold_id: str | None = None
    resource_id: str | None = None
    activity_id: str | None = None
    authorization_request: AuthorizationRequest | None = None
    wait_until: datetime | None = None

    def for_model(self) -> dict[str, Any]:
        return {"option_id": self.option_id, "action": self.action, "summary": self.summary}

    def for_record(self) -> dict[str, Any]:
        return {
            "option_id": self.option_id,
            "action": self.action,
            "intent": self.intent,
            "tool": self.tool,
            "candidate_id": self.candidate_id,
            "report_id": self.report_id,
            "hold_id": self.hold_id,
        }


@dataclass(frozen=True)
class Menu:
    options: tuple[MenuOption, ...]

    def get(self, option_id: str) -> MenuOption | None:
        return next((o for o in self.options if o.option_id == option_id), None)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(o.option_id for o in self.options)

    @property
    def intents(self) -> frozenset[str]:
        return frozenset(o.intent for o in self.options)

    @property
    def needs_choice(self) -> bool:
        """Whether any option acts (keep and wait change nothing, so they need no model)."""
        return any(o.action not in ("keep", "wait") for o in self.options)


@dataclass(frozen=True)
class OpenAsk:
    """The policy's own open authorization request (the board derives open/answered)."""

    request: AuthorizationRequest
    signature: str
    grant_version: int
    hold_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerifyNeed:
    """Why a status check of ``entity_id`` is useful now. A successful check requested at or
    after ``since`` answers it (a check answers as of its request time)."""

    entity_id: str
    since: datetime
    reason: str
    refs: tuple[str, ...] = ()  # observation ids that raise the need


@dataclass
class MenuInputs:
    principal: str
    now: datetime
    eligible: frozenset[str] | None = None  # robust candidate signatures; None = no restriction
    verify: dict[str, VerifyNeed] = field(default_factory=dict)
    plan_in_question: bool = True
    open_ask: OpenAsk | None = None
    hold_counts: dict[tuple[str, str, int], int] = field(default_factory=dict)
    rejected_intents: frozenset[str] = frozenset()
    wait_until: datetime | None = None


def own_grant(view: EventStateView, principal: str) -> GrantView | None:
    own = [g for g in view.grants if g.grant.principal_id == principal]
    return max(own, key=lambda g: g.version) if own else None


def build_menu(view: EventStateView, ev: EvaluationResult, inputs: MenuInputs) -> Menu:
    grant = own_grant(view, inputs.principal)
    allowed = set(grant.grant.allowed_tools) if grant is not None else set()
    scope = set(grant.grant.resource_ids) if grant is not None else set()

    def eligible(c: CandidateResult) -> bool:
        return inputs.eligible is None or c.signature in inputs.eligible

    options: list[MenuOption] = []
    keep = next((c for c in ev.candidates if c.candidate_id == ev.keep_candidate_id), None)
    keep_ok = keep is not None and keep.applicable_now and eligible(keep)
    if keep is not None and keep_ok:
        options.append(
            MenuOption(
                option_id="keep",
                action="keep",
                intent="keep",
                summary=f"Keep plan v{view.plan.plan_version} ({keep.candidate_id}); it passes "
                "every hard check under its stated assumptions.",
                candidate_id=keep.candidate_id,
                report_id=keep.report_id,
                signature=keep.signature,
            )
        )
    if "query_status" in allowed:
        options.extend(_query_options(view, inputs, scope))
    if grant is not None and grant.valid_now:
        if inputs.plan_in_question:
            if "apply_plan" in allowed:
                options.extend(_apply_options(view, ev, eligible))
            if "hold_resource" in allowed:
                options.extend(_hold_options(view, ev, grant, inputs, scope, eligible, keep_ok))
            options.extend(_ask_options(view, ev, grant, inputs, eligible))
        if "release_hold" in allowed:
            options.extend(_release_options(view, ev, inputs, eligible))
    options = [o for o in options if o.intent not in inputs.rejected_intents]
    until = (
        f" until {local_label(inputs.wait_until, view.timezone)}"
        if inputs.wait_until is not None
        else " until the state changes"
    )
    options.append(
        MenuOption(
            option_id="wait",
            action="wait",
            intent="wait",
            summary=f"Change nothing now; look again{until}.",
            wait_until=inputs.wait_until,
        )
    )
    return Menu(options=tuple(options))


def _query_options(view: EventStateView, inputs: MenuInputs, scope: set[str]) -> list[MenuOption]:
    out: list[MenuOption] = []
    resources = {r.definition.resource_id: r for r in view.resources}
    for source in view.status_sources:
        for entity in source.entity_ids:
            need = inputs.verify.get(entity)
            res = resources.get(entity)
            if need is None or res is None or entity not in scope:
                continue
            terms = res.definition.terms
            if terms.status_source_id != source.source_id:
                continue
            for fact in source.facts:
                if fact not in terms.queryable_facts:
                    continue
                since = [
                    c
                    for c in view.status_checks
                    if c.entity_id == entity
                    and c.fact == fact
                    and c.requested_at is not None
                    and c.requested_at >= need.since
                ]
                if any(c.envelope_status == "succeeded" for c in since):
                    continue  # answered
                failures = [c for c in since if c.actor_id == inputs.principal]
                if len(failures) >= MAX_STATUS_FAILURES:
                    continue
                ok = [
                    c.requested_at
                    for c in view.status_checks
                    if c.entity_id == entity
                    and c.fact == fact
                    and c.envelope_status == "succeeded"
                    and c.requested_at is not None
                ]
                last = (
                    f"last successful check {local_label(max(ok), view.timezone)}"
                    if ok
                    else "never checked successfully"
                )
                failed = f", {len(failures)} failed check(s) since" if failures else ""
                out.append(
                    MenuOption(
                        option_id=f"query:{entity}:{fact}",
                        action="query_status",
                        intent=f"query:{entity}:{fact}",
                        summary=f"Query {source.label} for {entity} {fact}: {need.reason} "
                        f"({last}{failed}; takes "
                        f"{view.tool_durations_minutes.get('query_status', 0)} min).",
                        tool="query_status",
                        arguments=QueryStatusArgs(entity_id=entity, fact=fact).model_dump(
                            mode="json"
                        ),
                        resource_id=entity,
                    )
                )
    return out


def _apply_options(view: EventStateView, ev: EvaluationResult, eligible: Any) -> list[MenuOption]:
    out: list[MenuOption] = []
    for c in ev.candidates:
        if len(out) >= MAX_APPLY_OPTIONS:
            break
        if not c.applicable_now or c.candidate_id == ev.keep_candidate_id or not eligible(c):
            continue
        out.append(
            MenuOption(
                option_id=f"apply:{c.candidate_id}",
                action="apply_plan",
                intent=f"apply:{c.signature}",
                summary=f"Apply {c.label} ({c.candidate_id}, report {c.report_id}, rank {c.rank}):"
                f" changes {', '.join(c.changed_activity_ids) or 'nothing'}, additional committed "
                f"{c.incremental_committed_cents} cents.",
                tool="apply_plan",
                arguments=ApplyPlanArgs(
                    candidate_plan_id=c.candidate_id, constraint_report_ref=c.report_id
                ).model_dump(mode="json"),
                expected_revision=ev.revision,
                expected_goal_version=ev.goal_version,
                candidate_id=c.candidate_id,
                report_id=c.report_id,
                signature=c.signature,
            )
        )
    return out


def _hold_options(
    view: EventStateView,
    ev: EvaluationResult,
    grant: GrantView,
    inputs: MenuInputs,
    scope: set[str],
    eligible: Any,
    keep_ok: bool,
) -> list[MenuOption]:
    """Holds that keep a feasible candidate open. While the keep candidate still works (an
    unanswered notice puts it in question) a hold is a contingency for any feasible candidate;
    otherwise only for candidates ranked better than the best applicable change."""
    resources = {r.definition.resource_id: r for r in view.resources}
    activities = set(grant.grant.activity_ids)
    effective = inputs.now + timedelta(minutes=view.tool_durations_minutes.get("hold_resource", 0))
    out: list[MenuOption] = []
    seen: set[str] = set()
    for c in hold_candidates(ev, eligible, keep_ok):
        if len(out) >= MAX_HOLD_OPTIONS:
            break
        for rh in c.required_holds:
            res = resources.get(rh.resource_id)
            if rh.bound_hold_id is not None or res is None:
                continue
            span = (
                f"{local_label(rh.window.start, view.timezone).replace(':', '')}-"
                f"{local_label(rh.window.end, view.timezone).replace(':', '')}"
            )
            intent = f"hold:{rh.resource_id}:{rh.activity_id}:{span}"
            if intent in seen:
                continue
            terms = res.definition.terms
            exposure, fee = terms.reserved_exposure_cents, terms.hold_fee_cents
            count = inputs.hold_counts.get((rh.resource_id, rh.activity_id, grant.version), 0)
            if (
                rh.resource_id not in scope
                or rh.activity_id not in activities
                or (rh.commitment_cutoff is not None and effective >= rh.commitment_cutoff)
                or grant.reserved_used_cents + exposure > grant.grant.max_total_reserved_cents
                or grant.committed_used_cents + fee > grant.grant.max_total_committed_cents
                or exposure + fee > view.budget.remaining_cents
                or count >= MAX_HOLDS_PER_OPTION
            ):
                continue
            seen.add(intent)
            cutoff = (
                f", commitment cutoff {local_label(rh.commitment_cutoff, view.timezone)}"
                if rh.commitment_cutoff is not None
                else ""
            )
            lasts = f"{terms.hold_max_minutes or 10} min"
            out.append(
                MenuOption(
                    option_id=intent,
                    action="hold_resource",
                    intent=intent,
                    summary=f"Hold {rh.resource_id} for {rh.activity_id} "
                    f"{local_label(rh.window.start, view.timezone)}-"
                    f"{local_label(rh.window.end, view.timezone)} to keep {c.label} "
                    f"({c.candidate_id}) open: reserved exposure {exposure} cents (limit "
                    f"{grant.grant.max_total_reserved_cents}, used {grant.reserved_used_cents}), "
                    f"hold fee {fee} cents, lasts at most {lasts}{cutoff}; booking it later costs "
                    f"{rh.commitment_cost_cents} cents.",
                    tool="hold_resource",
                    arguments=HoldResourceArgs(
                        resource_id=rh.resource_id,
                        activity_id=rh.activity_id,
                        window=rh.window,
                        hold_minutes=None,
                    ).model_dump(mode="json"),
                    expected_revision=ev.revision,
                    candidate_id=c.candidate_id,
                    signature=c.signature,
                    resource_id=rh.resource_id,
                    activity_id=rh.activity_id,
                )
            )
    return out


def hold_candidates(ev: EvaluationResult, eligible: Any, keep_ok: bool) -> list[CandidateResult]:
    """Feasible eligible candidates worth holding for: any of them while the keep candidate
    still works (a contingency), else only those ranked better than the best applicable
    change."""
    best_applicable = next(
        (
            c
            for c in ev.candidates
            if c.applicable_now and eligible(c) and c.candidate_id != ev.keep_candidate_id
        ),
        None,
    )
    out: list[CandidateResult] = []
    for c in ev.candidates:
        if c.constraint_status != "feasible_under_assumptions" or not eligible(c):
            continue
        if (
            not keep_ok
            and best_applicable is not None
            and (c.rank is None or best_applicable.rank is None or c.rank >= best_applicable.rank)
        ):
            continue
        out.append(c)
    return out


def _ask_options(
    view: EventStateView,
    ev: EvaluationResult,
    grant: GrantView,
    inputs: MenuInputs,
    eligible: Any,
) -> list[MenuOption]:
    out: list[MenuOption] = []
    for c in ev.candidates:
        if c.constraint_status != "feasible_under_assumptions" or not eligible(c):
            continue
        missing = c.authorization.missing
        if not missing or any(m.kind != "committed_spend_limit" for m in missing):
            continue
        if not c.required_holds or any(rh.bound_hold_id is None for rh in c.required_holds):
            continue
        booking = c.required_holds[0].resource_id
        current = grant.grant.max_total_committed_cents
        requested = grant.committed_used_cents + c.incremental_committed_cents
        open_ask = inputs.open_ask
        if (
            open_ask is not None
            and open_ask.signature == c.signature
            and open_ask.grant_version == grant.version
            and open_ask.request.requested_value == requested
        ):
            continue
        request = AuthorizationRequest(
            request_id=f"authreq_r{ev.revision}_{c.signature[:8]}",
            target_grant_id=grant.grant.grant_id,
            field="max_total_committed_cents",
            current_value=current,
            requested_value=requested,
            resource_id=booking,
            candidate_id=c.candidate_id,
            reason=ask_reason(grant.grant.grant_id, current, requested, c, booking),
        )
        out.append(
            MenuOption(
                option_id=f"ask:{c.candidate_id}",
                action="ask",
                intent=f"ask:{c.signature}:{requested}:{grant.version}",
                summary=f"Ask the organizer to raise max_total_committed_cents of "
                f"{grant.grant.grant_id} from {current} to {requested} cents so {c.label} "
                f"({c.candidate_id}) can be applied; its holds "
                f"{', '.join(rh.bound_hold_id or '' for rh in c.required_holds)} keep it open.",
                candidate_id=c.candidate_id,
                report_id=c.report_id,
                signature=c.signature,
                resource_id=booking,
                authorization_request=request,
            )
        )
        break  # one request at a time: the best feasible candidate that needs it
    return out


def _release_options(
    view: EventStateView, ev: EvaluationResult, inputs: MenuInputs, eligible: Any
) -> list[MenuOption]:
    bound = {
        rh.bound_hold_id
        for c in ev.candidates
        if c.constraint_status == "feasible_under_assumptions" and eligible(c)
        for rh in c.required_holds
        if rh.bound_hold_id
    }
    out: list[MenuOption] = []
    for hold in view.holds:
        if hold.actor_id != inputs.principal or hold.effective_status != "active":
            continue
        used = any(
            a.activity_id == hold.activity_id
            and hold.resource_id in a.resource_ids
            and hold.window.contains(a.window)
            for a in view.plan.assignments
        )
        if used or (inputs.plan_in_question and hold.hold_id in bound):
            continue
        note = (
            "only a candidate the active plan does not need binds it"
            if hold.hold_id in bound
            else "neither the plan nor a feasible candidate needs it"
        )
        out.append(
            MenuOption(
                option_id=f"release:{hold.hold_id}",
                action="release_hold",
                intent=f"release:{hold.hold_id}",
                summary=f"Release your hold {hold.hold_id} on {hold.resource_id} for "
                f"{hold.activity_id} (expires {local_label(hold.expires_at, view.timezone)}; "
                f"{hold.reserved_cents} reserved cents return); {note}.",
                tool="release_hold",
                arguments=ReleaseHoldArgs(
                    hold_id=hold.hold_id,
                    reason=f"released by the live coordinator: {note}",
                ).model_dump(mode="json"),
                expected_revision=ev.revision,
                hold_id=hold.hold_id,
                resource_id=hold.resource_id,
                activity_id=hold.activity_id,
            )
        )
    return out


def ask_reason(
    grant_id: str, current: int, requested: int, cand: CandidateResult, booking: str
) -> str:
    """One sentence with the exact missing permission, within ``ASK_REASON_LIMIT``."""
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
