"""When a model call is warranted: the server-side attention rule of the model-driven policies.

One rule, shared code: the live coordinator (P2, ``live``), its verify-all ablation (P3) and the
tool-using baseline (P1, ``tool-use``) all decide here whether the state needs the model at
all. A model call is warranted when

* a new notice arrives that the server cannot resolve itself (a repeat with the same
  correlation group and text is a ``duplicate`` without a model call). P2 and P3 interpret it
  (``interpret``); P1 reads it in its next turn; or
* the decision menu built from the visible state and the latest evaluation (``menu``) offers
  an option that acts: a status check for a stated verification need, an apply, hold, handoff
  request or ask while the plan is in question, or the release of an own hold the plan does
  not use.

The plan is in question when the keep candidate is not applicable (or not robust), when an
unanswered material notice threatens it, or, on a consumable profile, when a pursuable stock
candidate leaves less of a service target unfulfilled. A notice is material when it concerns
equipment a not-started activity of the active plan uses before its claimed ETA (any use, for
a cancellation, no ETA, or a verify-only notice). Status answers, arrival records and check-ins
are typed evidence: they warrant a model call only through the evaluation (a plan that stops
working, a candidate that becomes applicable). Otherwise the server records what the state
determines (keep, a shortfall, infeasible, undecided, or a wait for staff or the organizer)
with ``chosen_by = "server"``, once per state.

Every policy wakes at its deadline watch (expected equipment ahead of a not-started activity:
the earlier of start - 5 min and reported ETA + 1 min; a status check is offered once per
watch), when an open authorization request's hold is about to lapse, when an awaited staff
handoff is due, and when the pantry handoff window opens (no state change marks that moment;
``domain.stock.handoff_window_opening``, the same wake as the deterministic baseline's).

P1 has no separate interpretation step, so the notices this rule weighs for it are only new
ones (each warrants its next turn); P2 and P3 also weigh their stored readings (claims and
verify-only notices). Within a call P1 still sees every visible observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from plan_b.agent.interpret import LiveInterpretation
from plan_b.agent.menu import (
    MAX_STATUS_FAILURES,
    Menu,
    MenuInputs,
    MenuOption,
    OpenAsk,
    VerifyNeed,
    awaited_handoffs,
    build_menu,
    coverage_text,
    hold_candidates,
    shortfalls,
    stock_improvable,
)
from plan_b.agent.provider import CallRecord
from plan_b.domain.models import (
    AuthorizationRequest,
    CandidateResult,
    DecisionKind,
    EvaluationResult,
    EventStateView,
    Hypothesis,
    ObservationRecord,
    ResourceView,
)
from plan_b.domain.stock import handoff_still_possible, handoff_window_opening
from plan_b.domain.timeutil import local_label

NOT_STARTED = ("planned", "ready")
DEADLINE_LEAD = timedelta(minutes=5)
ETA_GRACE = timedelta(minutes=1)
ASK_LEAD = timedelta(minutes=1)
_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass
class _Evaluated:
    ev: EvaluationResult
    hypothetical: EvaluationResult | None = None
    hypotheses: tuple[Hypothesis, ...] = ()
    eligible: frozenset[str] | None = None
    robust_note: str = ""


@dataclass
class _Watch:
    at: datetime
    activity_id: str
    resource_id: str
    plan_version: int


class AttentionMixin:
    """The shared attention rule, wake schedule and server-side narration (module docstring).

    The host policy supplies the state below and ``_record``; P1 keeps no interpretations
    (``_interps`` stays empty), so only the parts that do not rest on a model reading apply to
    it."""

    _principal: str
    _interps: dict[str, LiveInterpretation]
    _open_ask: OpenAsk | None
    _hold_counts: dict[tuple[str, str, int], int]
    _wake: datetime | None
    _watch: _Watch | None
    _watch_offered: set[tuple[str, str, int]]
    _window: datetime | None
    _recorded: set[tuple[Any, ...]]
    _pending_calls: list[CallRecord]
    _at: datetime | None

    def _record(
        self,
        run: Any,
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
        raise NotImplementedError

    # ------------------------------------------------------------------ the attention rule

    def _open_material(
        self, view: EventStateView, claims: list[LiveInterpretation]
    ) -> list[LiveInterpretation]:
        """Weighed notices that no check has answered yet and that are material for the active
        plan."""
        open_claims = [c for c in claims if self._answer(view, c) is None]
        return [c for c in open_claims if self._material(view, c)]

    def _attend(
        self,
        view: EventStateView,
        run: Any,
        evaluated: _Evaluated,
        material: list[LiveInterpretation],
        woke: bool,
        rejected_intents: frozenset[str] = frozenset(),
    ) -> Menu:
        """The decision menu for this state and evaluation; its ``needs_choice`` is whether a
        model call is warranted. On a consumable profile a kept plan short of a target is
        reported here (``_record_shortfall``) once the plan is not in question."""
        ev = evaluated.ev
        keep = _candidate(ev, ev.keep_candidate_id)
        keep_ok = (
            keep is not None
            and keep.applicable_now
            and (evaluated.eligible is None or keep.signature in evaluated.eligible)
        )
        # A weighed claim that can still be verified puts the plan in question; once its
        # verification failed, the robustness restriction (``eligible``) already accounts for it.
        threatening = [
            c
            for c in material
            if c.is_claim and not c.hearsay and not self._verification_failed(view, c)
        ]
        in_question = not keep_ok or bool(threatening)
        eligible = evaluated.eligible
        if not in_question and stock_improvable(
            view,
            ev,
            MenuInputs(principal=self._principal, now=self._now(view)),
            lambda c: eligible is None or c.signature in eligible,
        ):
            in_question = True  # a pursuable stock candidate leaves less unfulfilled
        if view.stock is not None and not in_question:
            self._record_shortfall(view, run, evaluated)
        verify = self._verify_needs(view, evaluated, material, woke, keep_ok, in_question)
        inputs = MenuInputs(
            principal=self._principal,
            now=self._now(view),
            eligible=evaluated.eligible,
            verify=verify,
            plan_in_question=in_question,
            open_ask=self._open_ask,
            hold_counts=dict(self._hold_counts),
            rejected_intents=rejected_intents,
            wait_until=self._compute_wait(view, self._now(view), dry=True),
        )
        return build_menu(view, ev, inputs)

    # ------------------------------------------------------------------ notices

    @staticmethod
    def _verify_only(interp: LiveInterpretation) -> bool:
        return (
            interp.standing in ("unresolved", "no_claim")
            and interp.subject_resource_id is not None
            and "query_status" in interp.change_spec.proposed_checks
        )

    def _claims(self, view: EventStateView) -> list[LiveInterpretation]:
        """Weighed claims and verify-only notices not retracted by a later notice."""
        retracted = {r for i in self._interps.values() for r in i.retracts}
        return [
            i
            for i in self._interps.values()
            if i.observation_id not in retracted and (i.is_claim or self._verify_only(i))
        ]

    def _answer(self, view: EventStateView, interp: LiveInterpretation) -> tuple[str, str] | None:
        """(observation id, evidence status) of the first typed status of the subject received
        after the notice (the check that answered it), or None while unanswered. A check
        answers as of its request time (``menu.VerifyNeed``), so a status whose checks were all
        requested before the notice arrived (one still in flight when it came) does not answer
        it; a status no check produced (an arrival record) answers as of its observation."""
        asked: dict[str, datetime] = {}
        for c in view.status_checks:
            if c.observation_id is not None and c.requested_at is not None:
                prior = asked.get(c.observation_id, c.requested_at)
                asked[c.observation_id] = max(prior, c.requested_at)
        latest: ObservationRecord | None = None
        for record in view.observations:
            obs = record.observation
            if obs.entity_id != interp.subject_resource_id or obs.kind != "status":
                continue
            asked_at = asked.get(obs.observation_id)
            if asked_at is not None:
                # A check's answer: its latest request at or after the notice answers it, a
                # deduplicated one (the source still reports the earlier observation) included.
                if asked_at < interp.received_at:
                    continue
            elif (obs.received_at, record.revision_after) <= (
                interp.received_at,
                interp.revision_after,
            ) or obs.observed_at < interp.received_at:
                continue
            latest = record
            break
        if latest is None:
            return None
        facts = latest.structured
        res = _resources(view).get(interp.subject_resource_id or "")
        status = facts.domain_status if facts is not None else (res.status if res else "unknown")
        eta = facts.reported_eta if facts is not None else (res.reported_eta if res else None)
        return latest.observation.observation_id, _assess(interp, status, eta)

    def _verification_failed(self, view: EventStateView, interp: LiveInterpretation) -> bool:
        """No registered source, or ``MAX_STATUS_FAILURES`` own checks since the notice failed
        and none succeeded."""
        res = _resources(view).get(interp.subject_resource_id or "")
        if res is None or not _has_source(view, res):
            return True
        since = [
            c
            for c in view.status_checks
            if c.entity_id == interp.subject_resource_id
            and c.requested_at is not None
            and c.requested_at >= interp.received_at
        ]
        if any(c.envelope_status == "succeeded" for c in since):
            return False
        return sum(1 for c in since if c.actor_id == self._principal) >= MAX_STATUS_FAILURES

    def _material(self, view: EventStateView, interp: LiveInterpretation) -> bool:
        """Whether the notice concerns equipment a not-started activity of the active plan
        uses before its claimed ETA (any use, for a cancellation, no ETA, or verify-only)."""
        res = _resources(view).get(interp.subject_resource_id or "")
        if res is None or res.definition.kind != "equipment":
            return False
        lifecycles = _lifecycles(view)
        eta = interp.claimed_eta if interp.is_claim else None
        for a in view.plan.assignments:
            if res.definition.resource_id not in a.resource_ids:
                continue
            if lifecycles.get(a.activity_id) not in NOT_STARTED:
                continue
            if eta is None or a.start < eta:
                return True
        return False

    # ------------------------------------------------------------------ verification needs

    def _verify_needs(
        self,
        view: EventStateView,
        evaluated: _Evaluated,
        material: list[LiveInterpretation],
        woke: bool,
        keep_ok: bool,
        in_question: bool,
    ) -> dict[str, VerifyNeed]:
        """Status checks worth offering: unanswered material notices; while the plan is in
        question, the catalog-only availability of a resource a hold would be offered for; and
        once per watch, equipment still not available on a deadline wake."""
        needs: dict[str, VerifyNeed] = {}
        by_entity: dict[str, list[LiveInterpretation]] = {}
        for claim in material:
            if claim.subject_resource_id is not None:
                by_entity.setdefault(claim.subject_resource_id, []).append(claim)
        for rid, claims in by_entity.items():
            refs = tuple(c.observation_id for c in claims)
            since = max(c.received_at for c in claims)
            what = (
                "a claim"
                if any(c.is_claim and not c.hearsay for c in claims)
                else "an unverified report"
            )
            needs[rid] = VerifyNeed(
                entity_id=rid,
                since=since,
                reason=f"notice {', '.join(refs)} makes {what} about {rid} that no check since "
                "has answered",
                refs=refs,
            )
        resources = _resources(view)
        eligible = evaluated.eligible
        targets = (
            hold_candidates(
                evaluated.ev, lambda c: eligible is None or c.signature in eligible, keep_ok
            )
            if in_question
            else []
        )
        for c in targets:
            for rh in c.required_holds:
                res = resources.get(rh.resource_id)
                if (
                    rh.bound_hold_id is None
                    and res is not None
                    and res.status_basis == "catalog"
                    and rh.resource_id not in needs
                    and _has_source(view, res)
                ):
                    needs[rh.resource_id] = VerifyNeed(
                        entity_id=rh.resource_id,
                        since=_EPOCH,
                        reason=f"{c.label} needs {rh.resource_id}, whose availability rests "
                        "only on the catalog",
                    )
        if view.stock is not None and in_question:
            self._stock_verify_needs(view, needs)
        watch = self._watch
        if woke and watch is not None:
            res = resources.get(watch.resource_id)
            key = (watch.activity_id, watch.resource_id, watch.plan_version)
            if (
                res is not None
                and res.status != "available"
                and view.plan.plan_version == watch.plan_version
                and _lifecycles(view).get(watch.activity_id) in NOT_STARTED
                and key not in self._watch_offered
                and watch.resource_id not in needs
                and _has_source(view, res)
            ):
                self._watch_offered.add(key)
                needs[watch.resource_id] = VerifyNeed(
                    entity_id=watch.resource_id,
                    since=watch.at,
                    reason=f"{watch.resource_id} is still {res.status} ahead of "
                    f"{watch.activity_id} at {self._t(_start_of(view, watch.activity_id), view)}",
                )
        return needs

    def _stock_verify_needs(self, view: EventStateView, needs: dict[str, VerifyNeed]) -> None:
        """Consumable profiles: an outstanding expected shipment whose status was never
        answered, and, while a supply gap exists, a declared transfer source (a handoff request
        would rest on its availability). A successful check at any time answers either."""
        stock = view.stock
        assert stock is not None
        resources = _resources(view)
        for shipment in stock.expected_shipments:
            rid = shipment.shipment.destination_resource_id
            res = resources.get(rid)
            if (
                shipment.outstanding_quantity
                and shipment.status_observation_id is None
                and res is not None
                and rid not in needs
                and _has_source(view, res)
            ):
                needs[rid] = VerifyNeed(
                    entity_id=rid,
                    since=_EPOCH,
                    reason=f"expected shipment {shipment.shipment.shipment_id} "
                    f"({shipment.outstanding_quantity} units) has no status answer; expected "
                    "units count only after a staff-recorded receipt",
                )
        gap = sum(s.supply_gap_quantity for s in stock.service)
        if not gap:
            return
        for option in view.stock_options:
            source = option.source_resource_id
            res = resources.get(source or "")
            if (
                option.option != "transfer_stock"
                or source is None
                or res is None
                or source in needs
                or not _has_source(view, res)
            ):
                continue
            needs[source] = VerifyNeed(
                entity_id=source,
                since=_EPOCH,
                reason=f"a staff handoff from {source} into {option.resource_id} would close the "
                f"supply gap of {gap} units; its availability has no status answer",
            )

    # ------------------------------------------------------------------ server narration

    def _record_shortfall(self, view: EventStateView, run: Any, evaluated: _Evaluated) -> None:
        """Consumable profiles, once the plan is not in question: a kept plan that covers less
        than a service target, with nothing pursuable that covers more (``stock_improvable``),
        no handoff awaited and none that could still open, is reported as the deterministic
        baseline reports it (``infeasible``, naming what blocks better coverage). The target is
        unchanged."""
        ev = evaluated.ev
        keep = _candidate(ev, ev.keep_candidate_id)
        now = self._now(view)
        params = view.pantry_parameters
        if keep is None or awaited_handoffs(view, self._principal, now):
            return
        deadlines = {t.target_id: t.deadline for t in view.goal.service_targets}
        for short in shortfalls(ev):
            if "stock_transfer" in short.blocking_constraints and handoff_still_possible(
                params, now, deadlines.get(short.target_id)
            ):
                continue  # a handoff can still be requested once the window opens
            names = ", ".join(short.blocking_constraints)
            self._record_once(
                run,
                ("shortfall", short.target_id, short.covered_quantity),
                "infeasible",
                f"No declared option covers the {short.target_quantity}-unit target "
                f"{short.target_id} with confirmed stock: plan v{view.plan.plan_version} "
                f"covers {short.covered_quantity}, leaving {short.shortfall_quantity} "
                f"unfulfilled. Blocking: {names}. The target is unchanged.",
                candidate_refs=(keep.candidate_id,),
                details={"chosen_by": "server", "evaluation_id": ev.evaluation_id}
                | short.details(),
            )

    def _record_default(
        self,
        view: EventStateView,
        run: Any,
        evaluated: _Evaluated,
        menu: Menu,
        claims: list[LiveInterpretation],
    ) -> None:
        """The menu offered no real choice: record what the state determines."""
        ev = evaluated.ev
        keep = menu.get("keep")
        if keep is not None:
            self._record_keep(view, run, evaluated, keep, None, chosen_by="server")
            return
        feasible = [
            c
            for c in ev.candidates
            if c.constraint_status == "feasible_under_assumptions"
            and (evaluated.eligible is None or c.signature in evaluated.eligible)
        ]
        refs = tuple(c.observation_id for c in claims)
        if not feasible:
            unknown = [c for c in ev.candidates if c.constraint_status == "unknown"]
            if unknown:
                self._record_undecided(view, run, ev, unknown, refs)
            else:
                self._record_infeasible(view, run, ev, refs)
            return
        best = feasible[0]
        awaited = awaited_handoffs(view, self._principal, self._now(view))
        if awaited:
            tasks = sorted(awaited, key=lambda ht: ht[1].respond_after)
            self._record_once(
                run,
                ("wait", "handoff", tuple(h.hold_id for h, _ in tasks), view.plan.plan_version),
                "wait",
                "Waiting for staff to record the handoff for "
                + ", ".join(
                    f"{h.hold_id} ({t.remaining_quantity} units of {t.source_resource_id}; due "
                    f"{self._t(t.respond_after, view)}, cutoff {self._t(t.cutoff, view)})"
                    for h, t in tasks
                )
                + f"; only a staff-recorded receipt moves stock. Plan v{view.plan.plan_version} "
                "is unchanged.",
                candidate_refs=(best.candidate_id,),
                wait_until=self._handoff_wake(view, self._now(view)),
                details={"evaluation_id": ev.evaluation_id, "chosen_by": "server"},
            )
            return
        ask = self._open_ask
        if ask is not None and ask.signature == best.signature:
            holds = {h.hold_id: h for h in view.holds}
            expiries = [holds[h].expires_at for h in ask.hold_ids if h in holds]
            self._record_once(
                run,
                ("wait", "ask", ask.request.request_id, ask.hold_ids, view.plan.plan_version),
                "wait",
                f"Authorization request {ask.request.request_id} is still unanswered; hold "
                f"{', '.join(ask.hold_ids) or 'none'} keeps {best.label} open until "
                f"{', '.join(self._t(t, view) for t in expiries) or 'its expiry'}.",
                candidate_refs=(best.candidate_id,),
                details={"evaluation_id": ev.evaluation_id, "chosen_by": "server"},
            )
            return
        missing = "; ".join(f"{m.kind} ({m.detail})" for m in best.authorization.missing)
        unbound = [rh.resource_id for rh in best.required_holds if rh.bound_hold_id is None]
        blockers = [
            *([f"missing permission: {missing}"] if missing else []),
            *([f"unbound hold on {', '.join(unbound)} cannot be placed now"] if unbound else []),
        ] or ["no applicable preparation step"]
        self._record_once(
            run,
            ("wait", "blocked", ev.goal_version, view.plan.plan_version, tuple(blockers)),
            "wait",
            f"No candidate can be applied now; the best feasible option is {best.label} "
            f"({best.candidate_id}). Not prepared because: {'; '.join(blockers)}. Plan "
            f"v{view.plan.plan_version} is kept unchanged.",
            candidate_refs=(best.candidate_id,),
            observation_refs=refs,
            details={"evaluation_id": ev.evaluation_id, "blockers": blockers},
        )

    def _record_keep(
        self,
        view: EventStateView,
        run: Any,
        evaluated: _Evaluated,
        option: MenuOption,
        choice: dict[str, Any] | None,
        *,
        chosen_by: Literal["model", "server"],
    ) -> None:
        ev = evaluated.ev
        lifecycles = _lifecycles(view)
        resources = _resources(view)
        if not any(state in NOT_STARTED for state in lifecycles.values()):
            done = sorted(a for a, s in lifecycles.items() if s == "completed")
            running = sorted(a for a, s in lifecycles.items() if s == "started")
            failed = sorted(a for a, s in lifecycles.items() if s in ("failed", "canceled"))
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
        kept_c = _candidate(ev, option.candidate_id)
        if kept_c is not None and kept_c.service_coverage:
            parts.append(f"it {coverage_text(kept_c)}")
        claims = self._claims(view)
        for claim in claims:
            answer = self._answer(view, claim)
            if answer is not None:
                parts.append(f"notice {claim.observation_id} {answer[1]} by {answer[0]}")
            elif claim.hearsay:
                parts.append(f"notice {claim.observation_id} unverified hearsay, not weighed")
            elif self._verify_only(claim):
                parts.append(f"notice {claim.observation_id} not a claim; verification only")
            elif not self._material(view, claim):
                parts.append(f"notice {claim.observation_id} not material for the current plan")
            else:
                parts.append(f"notice {claim.observation_id} unverified")
        if evaluated.robust_note:
            parts.append(evaluated.robust_note)
        summary = "; ".join(parts) + "."
        kept = _candidate(ev, option.candidate_id)
        details: dict[str, Any] = {
            "evaluation_id": ev.evaluation_id,
            "report_id": option.report_id,
            "assumptions": [a.text for a in kept.assumptions] if kept is not None else [],
        }
        kw: dict[str, Any] = {
            "observation_refs": tuple(c.observation_id for c in claims),
            "candidate_refs": _ids([option.candidate_id]),
        }
        if chosen_by == "model":
            details["choice"] = choice
            self._record(run, "keep", summary, details=details, **kw)
        else:
            self._record_once(
                run,
                ("keep", view.plan.plan_version, ev.goal_version, summary),
                "keep",
                summary,
                details=details,
                **kw,
            )

    def _record_undecided(
        self,
        view: EventStateView,
        run: Any,
        ev: EvaluationResult,
        unknown: list[CandidateResult],
        refs: tuple[str, ...],
    ) -> None:
        unsupported: dict[str, str] = {}
        for c in unknown:
            for check in c.checks:
                if check.status == "unsupported":
                    unsupported.setdefault(check.constraint_id, check.detail)
        infeasible = [c for c in ev.candidates if c.constraint_status == "infeasible"]
        blocking = sorted(
            {ch.constraint_id for c in infeasible for ch in c.checks if ch.status == "failed"}
        )
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
            f"({', '.join(sorted(unsupported)) or 'unsupported check'}). Plan "
            f"v{view.plan.plan_version} is kept unchanged and no booking or spend is made.",
            observation_refs=refs,
            candidate_refs=tuple(c.candidate_id for c in unknown[:8]),
            details={
                "evaluation_id": ev.evaluation_id,
                "unsupported_requirements": [
                    {"constraint_id": cid, "detail": detail}
                    for cid, detail in sorted(unsupported.items())
                ],
                "undecided_candidate_ids": [c.candidate_id for c in unknown],
                "blocking_constraints": blocking,
            },
        )

    def _record_infeasible(
        self, view: EventStateView, run: Any, ev: EvaluationResult, refs: tuple[str, ...]
    ) -> None:
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
            observation_refs=refs,
            details={
                "evaluation_id": ev.evaluation_id,
                "revision": ev.revision,
                "goal_version": ev.goal_version,
                "blocking_constraints": list(blocking),
                "declared_action_space": inf.declared_action_space,
                "detail": inf.detail,
            },
        )

    def _record_once(
        self, run: Any, signature: tuple[Any, ...], kind: DecisionKind, summary: str, **kw: Any
    ) -> None:
        """A state-level decision without model calls is recorded once; with model calls to
        account for it is always recorded."""
        if signature in self._recorded and not self._pending_calls:
            return
        self._recorded.add(signature)
        self._record(run, kind, summary, **kw)

    # ------------------------------------------------------------------ waking

    def _ask_wake(self, view: EventStateView, expiries: list[datetime]) -> datetime | None:
        """Early enough that an apply issued then still takes effect while the hold is live."""
        if not expiries:
            return None
        apply_lead = timedelta(minutes=view.tool_durations_minutes.get("apply_plan", 0))
        return min(expiries) - ASK_LEAD - apply_lead

    def _compute_wait(
        self, view: EventStateView, now: datetime, *, dry: bool = False
    ) -> datetime | None:
        watch = self._deadline_watch(view, now)
        if not dry:
            self._watch = watch
        times: list[datetime] = [watch.at] if watch is not None else []
        wake = self._wake
        if self._open_ask is None or (wake is not None and wake <= now):
            wake = None
        if not dry:
            self._wake = wake
        if wake is not None:
            times.append(wake)
        handoff = self._handoff_wake(view, now)
        if handoff is not None:
            times.append(handoff)
        opening = handoff_window_opening(view.pantry_parameters, now)
        if not dry:
            self._window = opening
        if opening is not None:
            times.append(opening)
        return min(times) if times else None

    def _handoff_wake(self, view: EventStateView, now: datetime) -> datetime | None:
        """The earliest wake an awaited staff handoff owes: its ``respond_after``, then its
        cutoff."""
        dues = [
            task.respond_after if task.respond_after > now else task.cutoff
            for _, task in awaited_handoffs(view, self._principal, now)
        ]
        return min((due for due in dues if due > now), default=None)

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

    def _now(self, view: EventStateView) -> datetime:
        return self._at if self._at is not None and self._at >= view.clock else view.clock

    def _t(self, value: datetime, view: EventStateView) -> str:
        return local_label(value, view.timezone)


# ---------------------------------------------------------------------------------- helpers


def _ids(values: Any) -> tuple[str, ...]:
    return tuple(v for v in values if v)


def _resources(view: EventStateView) -> dict[str, ResourceView]:
    return {r.definition.resource_id: r for r in view.resources}


def _lifecycles(view: EventStateView) -> dict[str, str]:
    return {a.definition.activity_id: a.lifecycle for a in view.activities}


def _has_source(view: EventStateView, res: ResourceView) -> bool:
    terms = res.definition.terms
    return terms.status_source_id is not None and any(
        s.source_id == terms.status_source_id and res.definition.resource_id in s.entity_ids
        for s in view.status_sources
    )


def _start_of(view: EventStateView, activity_id: str) -> datetime:
    for a in view.plan.assignments:
        if a.activity_id == activity_id:
            return a.start
    return view.clock


def _candidate(ev: EvaluationResult, candidate_id: str | None) -> CandidateResult | None:
    if candidate_id is None:
        return None
    return next((c for c in ev.candidates if c.candidate_id == candidate_id), None)


def _assess(interp: LiveInterpretation, status: str, eta: datetime | None) -> str:
    """A claim's standing under typed status received after it (as ``parser.assess_claim``)."""
    kind = interp.change_spec.change_kind
    if not interp.is_claim:
        return "verified_only"
    if kind == "delay":
        if status != "expected" or eta is None:
            return "superseded"
        if interp.promised_at is not None and eta <= interp.promised_at:
            return "contradicted"
        return "corroborated"
    if kind == "unavailability":
        if status == "unavailable":
            return "corroborated"
        if status in ("available", "expected"):
            return "contradicted"
    return "superseded"
