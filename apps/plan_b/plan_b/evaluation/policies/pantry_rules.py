"""Deterministic pantry baseline policy (``pantry-rules/1.0.0``).

Like the event rule policy, it sees only tool envelopes through a ``ToolClient`` bound to the
coordinator session, and every effect goes through the shared executor. It never calls the
staff-only ``record_stock_receipt`` or ``record_distribution``: physical receipt and service are
staff attestations. One ``run`` is a bounded loop:

1. Read state; stop when the event is over or the grant is not valid.
2. Verify: query each outstanding expected shipment's registered status once (its ETA) and,
   while a supply gap exists, each declared alternate pool's registered status once (at most two
   attempts each).
3. Evaluate the declared candidate menu (keep and the stock options).
4. Take the best feasible candidate. If it counts alternate units still to be handed off and no
   handoff was requested from that pool yet, hold the shortfall on the alternate pool
   (``purpose: stock_transfer``; the hold is the staff task), record the request, and wait for
   the declared staff response. While the request is open, wait. Once staff answered it, fully
   or partly, or it lapsed, plan without pending handoffs: one request per pool, so a partial
   answer is not topped up by asking again.
5. Commit: hold exactly the units the chosen candidate still needs on the session pool,
   re-evaluate, and apply the stored candidate under the standing grant.
6. When the best plan covers less than the target, record an ``infeasible`` decision with the
   shortfall and the blocking checks; the target itself is never changed.
7. Release own stock-transfer holds no pending handoff needs, and wait.

Memory lives on the instance (one per episode): the requests made, the status checks made and
the state signature last decided on. Every choice comes from visible state and declared
configuration; nothing here knows a case, a label or a scripted time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import (
    ActionReceipt,
    Assignment,
    CandidateResult,
    DecisionKind,
    EvaluationResult,
    EventStateView,
    GrantView,
    HandoffTaskView,
    HoldView,
    PolicyDecision,
    PolicyRunResult,
    ToolEnvelope,
)
from plan_b.domain.timeutil import local_label
from plan_b.evaluation.policies.base import ToolClient, TransportLost

POLICY_ID = "pantry-rules/1.0.0"
MAX_STATUS_ATTEMPTS = 2
MAX_RECEIPT_LOOKUPS = 2
MAX_CYCLES = 5
RETRYABLE = frozenset({"REVISION_CONFLICT", "CANDIDATE_STALE", "GOAL_VERSION_CONFLICT"})


def idempotency_key(revision: int, tool: str, arguments: dict[str, Any]) -> str:
    """``pantry-r<revision>-<tool>-<sha8(arguments)>``: the same intent at the same revision is
    an idempotent retry, never a fresh request."""
    return f"pantry-r{revision}-{tool}-{sha256_hex(canonical_json(arguments))[:8]}"


class _BudgetExhausted(Exception):
    """The run's tool-call budget is spent."""


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Mutation:
    envelope: ToolEnvelope
    receipt: ActionReceipt | None
    calls: tuple[str, ...]

    @property
    def applied(self) -> bool:
        return self.receipt is not None and self.receipt.status == "applied"

    @property
    def error_code(self) -> str | None:
        if self.receipt is not None and self.receipt.error_code:
            return self.receipt.error_code
        return self.envelope.error.code if self.envelope.error else None


class _Run:
    def __init__(self, client: ToolClient, max_calls: int) -> None:
        self.client = client
        self.max_calls = max_calls
        self.calls = 0
        self.decisions: list[PolicyDecision] = []
        self.at: datetime | None = None
        self.revision: int | None = None
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
        return envelope

    def read(self, tool: str, arguments: dict[str, Any]) -> ToolEnvelope:
        """Reads have no side effects, so one lost response is retried once."""
        try:
            return self.call(tool, arguments)
        except TransportLost:
            return self.call(tool, arguments)


class PantryRulePolicy:
    """The documented deterministic coordinator policy for the consumable profile."""

    policy_id = POLICY_ID

    def __init__(self) -> None:
        self._seq = 0
        self._recorded: set[tuple[Any, ...]] = set()
        self._attempts: dict[tuple[str, str], int] = {}
        self._verified: set[tuple[str, str]] = set()
        self._asked: dict[tuple[str, str], str | None] = {}  # (source, destination) -> hold id
        self._settled: tuple[Any, ...] | None = None
        self._wait: datetime | None = None
        self._stopped = False

    # ------------------------------------------------------------------ entry point

    def run(self, client: ToolClient, max_tool_calls: int = 16) -> PolicyRunResult:
        run = _Run(client, max_tool_calls)
        try:
            status, wait_until = self._run(run)
        except _BudgetExhausted:
            run.notes.append(f"tool-call budget of {max_tool_calls} spent")
            return self._result(run, "budget_exhausted", None)
        except TransportLost:
            run.notes.append("a read response was lost twice; nothing was decided")
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
            if view.stock is None:
                self._record_once(
                    run,
                    ("no_stock",),
                    "unresolved",
                    "This event projects no consumable stock; the pantry policy does nothing.",
                )
                return "waiting", None
            if self._verify(view, run):
                view = self._refresh(run)
            now = run.at or view.clock
            woke = self._wait is not None and now >= self._wait
            if self._signature(view) == self._settled and not woke:
                return "waiting", self._wait
            self._wait = None
            for _ in range(MAX_CYCLES):
                step = self._decide(view, run)
                if step != "again":
                    break
                view = self._refresh(run)
            view = self._refresh(run)
            self._release_unneeded(view, run)
            self._settled = self._signature(view)
        except _Stop as stop:
            if not self._stopped:
                self._stopped = True
                self._record(run, "stop", f"Stopped: {stop.reason}. No further action.")
            return "stopped", None
        return "waiting", self._wait

    # ------------------------------------------------------------------ state

    def _refresh(self, run: _Run) -> EventStateView:
        env = run.read("get_event_state", {})
        if env.status != "succeeded" or env.data is None:
            code = env.error.code if env.error else env.status
            raise _Stop(f"the state could not be read ({code})")
        view = EventStateView.model_validate(env.data)
        if view.episode_status != "active":
            raise _Stop("the episode is closed")
        if view.clock >= view.goal.hard_end or any(
            t.cause_kind == "event_closed" for t in view.transitions
        ):
            raise _Stop("the event window has closed")
        grant = self._own_grant(view)
        if grant is None or not grant.valid_now:
            raise _Stop("the coordinator grant is not valid")
        return view

    @staticmethod
    def _own_grant(view: EventStateView) -> GrantView | None:
        return next((g for g in view.grants if g.grant.grant_id == view.viewer.grant_id), None)

    @staticmethod
    def _signature(view: EventStateView) -> tuple[Any, ...]:
        """What the decision depends on: plan, goal, stock, reservations and staff tasks.
        Activity starts and completions alone leave it unchanged."""
        stock = view.stock
        assert stock is not None
        return (
            view.plan.plan_version,
            view.goal.version,
            tuple((b.resource_id, b.on_hand_quantity, b.reserved_quantity) for b in stock.balances),
            tuple((a.allocation_id, a.remaining_quantity) for a in stock.allocations),
            tuple(
                (h.hold_id, h.effective_status, h.remaining_quantity)
                for h in view.holds
                if h.consumable
            ),
            tuple((t.hold_id, t.status) for t in stock.handoff_tasks),
            tuple(
                (s.shipment.shipment_id, s.status_observation_id) for s in stock.expected_shipments
            ),
        )

    # ------------------------------------------------------------------ verification

    def _verify(self, view: EventStateView, run: _Run) -> bool:
        """Query registered sources for unverified expected shipments and, while there is a
        supply gap, for the declared alternate pools. True when anything new was ingested."""
        stock = view.stock
        assert stock is not None
        resources = {r.definition.resource_id: r for r in view.resources}
        wanted: list[tuple[str, str]] = []
        for shipment in stock.expected_shipments:
            pool = resources.get(shipment.shipment.destination_resource_id)
            if pool is None or not shipment.outstanding_quantity:
                continue
            if shipment.status_observation_id is None:
                facts = pool.definition.terms.queryable_facts
                if facts:
                    wanted.append((pool.definition.resource_id, facts[0]))
        gap = any(s.supply_gap_quantity > 0 for s in stock.service)
        if gap:
            sources = {
                o.source_resource_id
                for o in view.stock_options
                if o.option == "transfer_stock" and o.source_resource_id is not None
            }
            for rid in sorted(sources):
                source = resources.get(rid)
                facts = source.definition.terms.queryable_facts if source else ()
                if facts:
                    wanted.append((rid, facts[0]))
        changed = False
        for rid, fact in dict.fromkeys(wanted):
            if (rid, fact) in self._verified:
                continue
            if self._attempts.get((rid, fact), 0) >= MAX_STATUS_ATTEMPTS:
                continue
            self._attempts[(rid, fact)] = self._attempts.get((rid, fact), 0) + 1
            env = run.read("query_status", {"entity_id": rid, "fact": fact})
            data = env.data or {}
            if env.status == "succeeded":
                self._verified.add((rid, fact))
                changed = changed or not data.get("deduplicated", False)
                record = data.get("observation") or {}
                facts_seen = record.get("structured") or {}
                eta = facts_seen.get("reported_eta")
                self._record(
                    run,
                    "verify",
                    f"Checked {fact} of {rid} with its registered source: "
                    f"{facts_seen.get('status_code', 'answered')}"
                    + (f", ETA {self._t(eta, view)}" if isinstance(eta, str) else "")
                    + ". A status answer is evidence, not stock.",
                    tool_call_refs=(env.call_id,),
                    observation_refs=tuple(
                        o for o in [(record.get("observation") or {}).get("observation_id")] if o
                    ),
                    details={"entity_id": rid, "fact": fact, "outcome": env.status},
                )
            else:
                self._record(
                    run,
                    "verify",
                    f"The source for {rid} {fact} answered {env.status}; it stays unverified.",
                    tool_call_refs=(env.call_id,),
                    details={"entity_id": rid, "fact": fact, "outcome": env.status},
                )
        return changed

    # ------------------------------------------------------------------ deciding

    def _evaluate(self, run: _Run) -> EvaluationResult | None:
        env = run.read("evaluate_candidates", {})
        if env.status != "succeeded" or env.data is None:
            run.notes.append(f"evaluation {env.status}")
            return None
        return EvaluationResult.model_validate(env.data)

    def _decide(self, view: EventStateView, run: _Run) -> Literal["done", "again"]:
        ev = self._evaluate(run)
        if ev is None:
            return "done"
        stock = view.stock
        assert stock is not None
        feasible = [c for c in ev.candidates if c.rank is not None]
        if not feasible:
            blocking = ev.infeasibility.blocking_constraints if ev.infeasibility else ()
            self._record_once(
                run,
                ("infeasible", tuple(blocking)),
                "infeasible",
                "No declared option is feasible; the plan is kept and the target is unchanged."
                f" Blocking: {', '.join(blocking) or 'none named'}.",
                candidate_refs=(),
                details={"blocking_constraints": list(blocking), "evaluation_id": ev.evaluation_id},
            )
            return "done"
        best = feasible[0]
        if best.stock_transfers:
            step = self._pursue_handoff(view, run, ev, best)
            if step is not None:
                return step
            fallback = next((c for c in feasible if not c.stock_transfers), None)
            if fallback is None:
                self._record_shortfall(run, ev, best, blocking=("stock_transfer",))
                return "done"
            best = fallback
        if best.applicable_now:
            if not best.changed_activity_ids and not best.required_stock_holds:
                self._record_shortfall(run, ev, best)
                self._record_once(
                    run,
                    ("keep", view.plan.plan_version),
                    "keep",
                    f"The active plan is the best applicable candidate ({_coverage(best)});"
                    " nothing to change.",
                    candidate_refs=(best.candidate_id,),
                )
                return "done"
            return self._apply(view, run, ev, best)
        needs = [h for h in best.required_stock_holds if not h.bound_hold_ids]
        if not needs:
            self._record_once(
                run,
                ("unresolved", best.signature, ev.revision),
                "unresolved",
                f"The best feasible candidate ({best.label}) is not applicable now and needs no"
                " hold this policy can make; it waits.",
                candidate_refs=(best.candidate_id,),
                details={"evaluation_id": ev.evaluation_id},
            )
            return "done"
        for need in needs:
            held = self._hold_for(
                view,
                run,
                best,
                need.resource_id,
                need.service_target_id,
                need.activity_id,
                need.quantity - need.held_quantity,
            )
            if not held:
                return "done"
        return "again"

    def _pursue_handoff(
        self, view: EventStateView, run: _Run, ev: EvaluationResult, best: CandidateResult
    ) -> Literal["done", "again"] | None:
        """Request, or wait for, the staff handoff the best candidate counts on. None when this
        policy will not wait for it (answered, lapsed, refused, or never possible)."""
        stock = view.stock
        assert stock is not None
        now = run.at or view.clock
        for need in best.stock_transfers:
            key = (need.source_resource_id, need.destination_resource_id)
            if key not in self._asked:
                if need.held_quantity >= need.quantity:
                    self._asked[key] = need.bound_hold_ids[0] if need.bound_hold_ids else None
                else:
                    hold = self._hold_transfer(
                        view,
                        run,
                        best,
                        need.source_resource_id,
                        need.destination_resource_id,
                        need.activity_id,
                        need.quantity - need.held_quantity,
                    )
                    self._asked[key] = hold.hold_id if hold is not None else None
                    if hold is None:
                        return None
                    task = _task(view, hold.hold_id)
                    respond = task.respond_after if task is not None else None
                    self._wait = respond
                    self._record(
                        run,
                        "ask",
                        f"Asked staff to hand off {need.quantity} units from"
                        f" {need.source_resource_id} into {need.destination_resource_id} (hold"
                        f" {hold.hold_id}, the local staff task); only a staff-recorded receipt"
                        " moves stock"
                        + (
                            f"; their response is due at {self._t(respond, view)}"
                            if respond
                            else ""
                        )
                        + ".",
                        candidate_refs=(best.candidate_id,),
                        details={
                            "ask": "stock_handoff",
                            "hold_id": hold.hold_id,
                            "quantity": need.quantity,
                            "source_resource_id": need.source_resource_id,
                            "destination_resource_id": need.destination_resource_id,
                        },
                        wait_until=respond,
                    )
                    return "done"
            hold_id = self._asked[key]
            task = _task(view, hold_id) if hold_id else None
            if task is not None and task.status == "open" and now < task.cutoff:
                self._wait = task.respond_after if task.respond_after > now else task.cutoff
                self._record_once(
                    run,
                    ("wait", hold_id),
                    "wait",
                    f"Waiting for staff to record the handoff for {hold_id} (due"
                    f" {self._t(task.respond_after, view)}, cutoff {self._t(task.cutoff, view)}).",
                    wait_until=self._wait,
                )
                return "done"
        return None

    def _apply(
        self, view: EventStateView, run: _Run, ev: EvaluationResult, best: CandidateResult
    ) -> Literal["done", "again"]:
        arguments = {
            "candidate_plan_id": best.candidate_id,
            "constraint_report_ref": best.report_id,
        }
        result = self._mutate(
            run,
            "apply_plan",
            arguments,
            expected_revision=ev.revision,
            expected_goal_version=ev.goal_version,
        )
        if result is None:
            return "done"
        if result.applied:
            self._record(
                run,
                "commit",
                f"Applied {best.label} ({_coverage(best)}); its stock holds are now committed"
                " allocations. Distribution itself is recorded by staff.",
                candidate_refs=(best.candidate_id,),
                receipt_refs=(result.receipt.receipt_id,) if result.receipt else (),
                tool_call_refs=result.calls,
            )
            return "again"
        if result.error_code in RETRYABLE:
            return "again"
        self._record_once(
            run,
            ("apply_rejected", best.signature, result.error_code),
            "unresolved",
            f"apply_plan for {best.label} was rejected ({result.error_code}); the plan is kept.",
            candidate_refs=(best.candidate_id,),
            receipt_refs=(result.receipt.receipt_id,) if result.receipt else (),
        )
        return "done"

    def _hold_for(
        self,
        view: EventStateView,
        run: _Run,
        best: CandidateResult,
        pool: str,
        target: str,
        activity: str,
        quantity: int,
    ) -> bool:
        """Hold ``quantity`` units of the session pool for the candidate's allocation. A
        negative difference (more held than needed) releases those holds first."""
        if quantity < 0:
            for hold in _own_live(view, purpose="activity", resource_id=pool):
                if hold.service_target_id == target and hold.activity_id == activity:
                    self._release(view, run, hold, "it no longer matches the planned allocation")
            return True
        window = _window(best, activity)
        if window is None:
            return False
        arguments = {
            "resource_id": pool,
            "activity_id": activity,
            "window": window,
            "quantity": quantity,
            "service_target_id": target,
        }
        result = self._mutate(run, "hold_resource", arguments, expected_revision=run.revision or 0)
        if result is None:
            return False
        if not result.applied:
            if result.error_code in RETRYABLE:
                return True
            self._record_once(
                run,
                ("hold_rejected", pool, target, result.error_code),
                "unresolved",
                f"Holding {quantity} units of {pool} for {target} was rejected"
                f" ({result.error_code}); the plan stays as it is.",
                receipt_refs=(result.receipt.receipt_id,) if result.receipt else (),
            )
            return False
        self._record(
            run,
            "prepare",
            f"Held {quantity} units of {pool} for {target} so {best.label} can be applied; a"
            " hold reserves units and serves nobody.",
            candidate_refs=(best.candidate_id,),
            receipt_refs=(result.receipt.receipt_id,) if result.receipt else (),
        )
        return True

    def _hold_transfer(
        self,
        view: EventStateView,
        run: _Run,
        best: CandidateResult,
        source: str,
        destination: str,
        activity: str,
        quantity: int,
    ) -> HoldView | None:
        window = _window(best, activity)
        if window is None:
            return None
        arguments = {
            "resource_id": source,
            "activity_id": activity,
            "window": window,
            "quantity": quantity,
            "purpose": "stock_transfer",
            "destination_resource_id": destination,
        }
        result = self._mutate(run, "hold_resource", arguments, expected_revision=run.revision or 0)
        if result is None or not result.applied:
            code = result.error_code if result is not None else "unknown"
            self._record_once(
                run,
                ("transfer_rejected", source, destination),
                "unresolved",
                f"Reserving {quantity} units of {source} for a handoff was rejected ({code});"
                " the plan goes ahead without them.",
                receipt_refs=(result.receipt.receipt_id,)
                if result is not None and result.receipt
                else (),
            )
            return None
        data = (result.envelope.data or {}).get("hold")
        hold = HoldView.model_validate(data) if isinstance(data, dict) else None
        if hold is not None:
            self._record(
                run,
                "prepare",
                f"Held {quantity} units of {source} for a staff handoff into {destination}; the"
                " hold moves nothing and serves nobody.",
                candidate_refs=(best.candidate_id,),
                receipt_refs=(result.receipt.receipt_id,) if result.receipt else (),
            )
        return hold

    def _record_shortfall(
        self,
        run: _Run,
        ev: EvaluationResult,
        chosen: CandidateResult,
        *,
        blocking: tuple[str, ...] = (),
    ) -> None:
        """Report a plan that covers less than the target, naming what blocks better
        coverage. The target is unchanged."""
        for coverage in chosen.service_coverage:
            if not coverage.unfulfilled_quantity:
                continue
            better = [
                c
                for c in ev.candidates
                if any(
                    x.target_id == coverage.target_id
                    and x.allocated_quantity > coverage.allocated_quantity
                    for x in c.service_coverage
                )
            ]
            named = set(blocking)
            for c in better:
                failed = [k.constraint_id for k in c.checks if k.status == "failed"]
                named.update(failed or (["stock_transfer"] if c.stock_transfers else []))
            names = sorted(named) or ["stock_on_hand"]
            self._record_once(
                run,
                ("shortfall", coverage.target_id, coverage.allocated_quantity),
                "infeasible",
                f"No declared option covers the {coverage.target_quantity}-unit target"
                f" {coverage.target_id} with confirmed stock: the plan covers"
                f" {coverage.allocated_quantity}, leaving {coverage.unfulfilled_quantity}"
                f" unfulfilled. Blocking: {', '.join(names)}. The target is unchanged.",
                candidate_refs=(chosen.candidate_id,),
                details={
                    "blocking_constraints": names,
                    "evaluation_id": ev.evaluation_id,
                    "target_id": coverage.target_id,
                    "covered_quantity": coverage.allocated_quantity,
                    "shortfall_quantity": coverage.unfulfilled_quantity,
                },
            )

    # ------------------------------------------------------------------ holds

    def _release_unneeded(self, view: EventStateView, run: _Run) -> None:
        """Release own stock-transfer holds whose handoff this policy no longer waits for."""
        stock = view.stock
        if stock is None:
            return
        now = run.at or view.clock
        for hold in _own_live(view, purpose="stock_transfer"):
            task = _task(view, hold.hold_id)
            waiting = task is not None and task.status == "open" and now < task.cutoff
            if waiting:
                continue
            self._release(view, run, hold, "staff answered its handoff; the plan does not need it")

    def _release(self, view: EventStateView, run: _Run, hold: HoldView, why: str) -> None:
        """Release one own hold. A release can go stale when its modeled duration spans another
        change; it is then retried once at the refreshed revision."""
        arguments = {"hold_id": hold.hold_id, "reason": f"Released: {why}."}
        revision = run.revision or view.revision
        for attempt in range(2):
            result = self._mutate(run, "release_hold", arguments, expected_revision=revision)
            if result is None:
                return
            if result.applied:
                self._record(
                    run,
                    "release",
                    f"Released hold {hold.hold_id} ({hold.remaining_quantity} units of"
                    f" {hold.resource_id}): {why}. Releasing creates no stock.",
                    receipt_refs=(result.receipt.receipt_id,) if result.receipt else (),
                )
                return
            if result.error_code != "REVISION_CONFLICT" or attempt:
                return
            revision = self._refresh(run).revision

    # ------------------------------------------------------------------ mutations

    def _mutate(
        self,
        run: _Run,
        tool: str,
        arguments: dict[str, Any],
        *,
        expected_revision: int,
        expected_goal_version: int | None = None,
    ) -> _Mutation | None:
        """One mutation; a lost response is reconciled with its original key."""
        key = idempotency_key(expected_revision, tool, arguments)

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
                return _Mutation(
                    lookup, ActionReceipt.model_validate(data["receipt"]), tuple(calls)
                )
            if retried:
                continue
            retried = True
            try:
                envelope = send()
                calls.append(envelope.call_id)
                return _Mutation(envelope, envelope.receipt, tuple(calls))
            except TransportLost:
                continue
        self._record(
            run,
            "reconcile",
            f"The response to {tool} (key {key}) was lost and its outcome could not be"
            " established; no further mutation is made in this run.",
            tool_call_refs=tuple(calls),
            details={"idempotency_key": key, "tool": tool},
        )
        raise _Stop("a mutation outcome could not be established")

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
                wait_until=wait_until,
                details=details or {},
            )
        )

    def _record_once(
        self, run: _Run, signature: tuple[Any, ...], kind: DecisionKind, summary: str, **kw: Any
    ) -> None:
        if signature in self._recorded:
            return
        self._recorded.add(signature)
        self._record(run, kind, summary, **kw)

    @staticmethod
    def _t(value: datetime | str, view: EventStateView) -> str:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return local_label(value, view.timezone)


# ---------------------------------------------------------------------- helpers


def _own_live(
    view: EventStateView, *, purpose: str, resource_id: str | None = None
) -> list[HoldView]:
    return [
        h
        for h in view.holds
        if h.consumable
        and h.actor_id == view.viewer.principal_id
        and h.effective_status == "active"
        and h.purpose == purpose
        and (resource_id is None or h.resource_id == resource_id)
    ]


def _task(view: EventStateView, hold_id: str | None) -> HandoffTaskView | None:
    if view.stock is None or hold_id is None:
        return None
    return next((t for t in view.stock.handoff_tasks if t.hold_id == hold_id), None)


def _window(candidate: CandidateResult, activity_id: str) -> dict[str, str] | None:
    assignment: Assignment | None = next(
        (a for a in candidate.assignments if a.activity_id == activity_id), None
    )
    if assignment is None:
        return None
    return {
        "start": assignment.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": assignment.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _coverage(candidate: CandidateResult) -> str:
    return "; ".join(
        f"{c.allocated_quantity} of {c.target_quantity} {c.target_id}"
        for c in candidate.service_coverage
    )
