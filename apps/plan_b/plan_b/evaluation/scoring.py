"""State-based outcome scoring for one episode.

The report is computed only from persisted visible records: the final ``EventStateView`` and
the ``EpisodeHistory`` (tool calls, transitions, decisions, receipts). Policy decisions are
narration; they matter only for ``infeasibility_reported``. Execution facts come from
lifecycle records, plan versions, observations, check-ins, commitments, grants and receipts.

Goal attainment and the executed domain-rule violations come from the profile's domain
adapter (``adapter_for(profile_id).score_outcome``). This module adds what is
domain-independent: counters, the event budget and grant limits, and the predicates.

Private ``PrivateCase`` predicates are evaluated only when the runner passes a case. Their
results, the expected outcome and anything derived from them stay in the runner-side report;
``public_summary`` removes them for browser-facing use.

Consumable profiles (runtime 1.1.0) add the service and stock columns of the report: each
target against its original quantity (on time, late, unfulfilled, supply gap), each pool's
conservation terms, staff confirmations, duplicate physical records refused and reservations
that lapsed or were released unused. They come from the final view's ``stock`` projection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from plan_b.domain.adapters.outcome import OutcomeRecords, Violation, required_completed
from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.models import (
    STAFF_TOOLS,
    ActionReceipt,
    ActivityOutcome,
    EpisodeHistory,
    EventStateView,
    GrantView,
    HoldStats,
    OutcomePredicate,
    OutcomeReport,
    PolicyDecision,
    PredicateResult,
    PrivateCase,
)
from plan_b.domain.stock import PANTRY_CHECK_IDS, service_outcomes, stock_outcomes
from plan_b.domain.timeutil import local_label, minutes_between, parse_ts, to_utc

REPORT_VERSION: Literal["1.0.0"] = "1.0.0"
PLAN_CHANGE_FIELDS = frozenset({"scheduled_window", "resource_ids"})
PRIVATE_FIELDS = frozenset({"predicates", "expected_outcome", "case_ref", "matches_expectation"})
# Hard-check identifiers of the planners (contract section 10): the campus checks, then the
# consumable checks the pantry adapter adds.
HARD_CHECK_IDS = (
    "required_activities",
    "fixed_venue",
    "started_history",
    "no_past_change",
    "activity_windows",
    "event_window",
    "dependencies",
    "program_exclusivity",
    "occupancy_capacity",
    "resource_capacity",
    "resource_status",
    "arrival_assumptions",
    "substitute_compatibility",
    "participant_availability",
    "accessibility",
    "commitment_cutoff",
    "budget",
    *PANTRY_CHECK_IDS,
)
BUDGET_CATEGORIES = frozenset({"grant_limit", "budget"})


def score_episode(
    final: EventStateView,
    history: EpisodeHistory,
    case: PrivateCase | None = None,
    policy_id: str | None = None,
) -> OutcomeReport:
    """Outcome of one episode from its persisted records (plus case predicates runner-side).

    The goal is complete when the domain adapter finds it attained and no violation, domain
    or spend limit, was executed."""
    records = OutcomeRecords(final, history)
    domain = adapter_for(final.profile_id).score_outcome(final, history)
    activities = domain.activities
    violations = [*domain.violations, *_limit_violations(records)]
    by_id = {a.activity_id: a for a in activities}
    goal_complete = domain.goal_attained and not violations
    applied = sorted(
        (r for r in records.receipts if r.tool == "apply_plan" and r.status == "applied"),
        key=lambda r: (r.executed_at, r.revision_after),
    )
    changed = sum(
        len({c.entity_id for c in r.state_changes if c.field in PLAN_CHANGE_FIELDS})
        for r in applied
    )
    status_calls = [c for c in history.tool_calls if c.tool == "query_status"]
    failed_status = [c for c in status_calls if c.envelope_status in ("unknown", "unavailable")]
    infeasible = any(d.kind == "infeasible" for d in records.decisions)
    report = OutcomeReport(
        report_version=REPORT_VERSION,
        episode_id=final.episode_id,
        scenario_id=final.scenario_id,
        final_clock=final.clock,
        final_revision=final.revision,
        goal_complete=goal_complete,
        activities=activities,
        committed_cents=final.budget.committed_cents,
        reserved_cents_at_end=final.budget.reserved_cents,
        holds=_hold_stats(final),
        applied_plans=len(applied),
        changed_assignments=changed,
        status_queries=len(status_calls),
        failed_status_queries=len(failed_status),
        rejected_receipts=sum(1 for r in records.receipts if r.status == "rejected"),
        rejected_attempts_without_receipt=sum(
            1
            for c in history.tool_calls
            if c.envelope_status == "rejected" and c.receipt_id is None
        ),
        violations=tuple(v.message for v in violations),
        infeasibility_reported=infeasible,
        recovery_delay_minutes=_recovery_delay(final, applied),
        policy_id=policy_id,
        **_stock_columns(final, records),
    )
    if case is None:
        return report
    results = tuple(
        _predicate(p, report, records, violations, by_id) for p in case.outcome_predicates
    )
    all_pass = all(r.passed for r in results)
    if case.expected_outcome == "goal_complete":
        matches = goal_complete and all_pass
    else:
        matches = (not goal_complete) and infeasible and all_pass
    return report.model_copy(
        update={
            "case_ref": case.case_ref,
            "predicates": results,
            "expected_outcome": case.expected_outcome,
            "matches_expectation": matches,
        }
    )


def public_summary(report: OutcomeReport) -> dict[str, Any]:
    """Browser-facing form: no predicates, expected outcome, case reference, or the match
    verdict derived from them."""
    return report.model_dump(mode="json", exclude=set(PRIVATE_FIELDS))


# ---------------------------------------------------------------------- spend limits


def _limit_violations(records: OutcomeRecords) -> list[Violation]:
    """Event budget and grant limits: domain-independent, after the adapter's violations."""
    final = records.final
    out: list[Violation] = []
    budget = final.budget
    if budget.committed_cents > final.goal.budget_cents:
        out.append(
            Violation(
                "budget",
                f"budget: committed {budget.committed_cents} cents exceeds the event budget "
                f"{final.goal.budget_cents} cents",
            )
        )
    elif budget.committed_cents + budget.reserved_cents > final.goal.budget_cents:
        out.append(
            Violation(
                "budget",
                f"budget: committed plus reserved {budget.committed_cents + budget.reserved_cents}"
                f" cents exceeds the event budget {final.goal.budget_cents} cents",
            )
        )
    if budget.reserved_cents < 0:
        out.append(
            Violation(
                "reserved_negative", f"reserved_negative: reserved is {budget.reserved_cents} cents"
            )
        )
    out.extend(_grant_violations(records))
    return out


def _grant_violations(records: OutcomeRecords) -> list[Violation]:
    """Committed spend attributed to each grant never exceeds the version in effect."""
    final = records.final
    versions: dict[str, list[GrantView]] = {}
    for g in final.grant_history or final.grants:
        versions.setdefault(g.grant.grant_id, []).append(g)
    spend: dict[str, list[tuple[datetime, int | None, int, str]]] = {}
    for c in final.commitments:
        receipt = records.receipt_by_id.get(c.receipt_id)
        rev = receipt.revision_after if receipt is not None else None
        spend.setdefault(c.grant_id, []).append(
            (c.created_at, rev, c.committed_cents, c.commitment_id)
        )
    for h in final.holds:
        if h.hold_fee_cents:
            receipt = records.receipt_by_id.get(h.created_receipt_id)
            rev = receipt.revision_after if receipt is not None else None
            spend.setdefault(h.grant_id, []).append(
                (h.created_at, rev, h.hold_fee_cents, h.hold_id)
            )
    out: list[Violation] = []
    for gid in sorted(spend):
        history = sorted(versions.get(gid, []), key=lambda g: g.version)
        if not history:
            out.append(
                Violation(
                    "grant_limit",
                    f"grant_limit: spend is attributed to {gid}, which has no grant record",
                )
            )
            continue
        cumulative = 0
        for at, rev, cents, ref in sorted(spend[gid], key=lambda e: (e[0], e[1] or 0, e[3])):
            cumulative += cents
            version = _version_at(records, history, at, rev)
            if version is None:
                out.append(
                    Violation(
                        "grant_limit",
                        f"grant_limit: the version of {gid} in effect when {ref} was made cannot "
                        "be established from the issuing receipts",
                    )
                )
                continue
            grant = version.grant
            if version.revoked:
                out.append(
                    Violation(
                        "grant_limit",
                        f"grant_limit: {ref} was made under revoked {gid} v{version.version}",
                    )
                )
            if at >= grant.expires_at:
                out.append(
                    Violation("grant_limit", f"grant_limit: {ref} was made after {gid} expired")
                )
            if cumulative > grant.max_total_committed_cents:
                out.append(
                    Violation(
                        "grant_limit",
                        f"grant_limit: {cumulative} cents committed under {gid} by {ref} exceeds "
                        f"the limit {grant.max_total_committed_cents} of version {version.version}",
                    )
                )
    return out


def _version_at(
    records: OutcomeRecords, history: list[GrantView], at: datetime, revision: int | None
) -> GrantView | None:
    chosen: GrantView | None = None
    for version in history:
        if version.issued_receipt_id is None:
            chosen = version
            continue
        receipt = records.receipt_by_id.get(version.issued_receipt_id)
        if receipt is None:
            return None
        if records.before(at, revision, receipt.executed_at, receipt.revision_after):
            chosen = version
    return chosen


# ---------------------------------------------------------------------- counters


def _hold_stats(final: EventStateView) -> HoldStats:
    statuses = [h.effective_status for h in final.holds]
    return HoldStats(
        created=len(statuses),
        released=statuses.count("released"),
        expired=statuses.count("expired"),
        committed=statuses.count("committed"),
        active_at_end=statuses.count("active"),
        fulfilled=statuses.count("fulfilled"),
    )


def _stock_columns(final: EventStateView, records: OutcomeRecords) -> dict[str, Any]:
    """The consumable report columns; empty for a profile without stock."""
    stock = final.stock
    if stock is None:
        return {}
    handed = {r.source_hold_id for r in stock.receipts if r.source_hold_id}
    unused = sum(
        1
        for h in final.holds
        if h.consumable
        and h.effective_status in ("released", "expired")
        and h.hold_id not in handed
    )
    return {
        "service": service_outcomes(stock),
        "stock": stock_outcomes(stock),
        "staff_confirmations": sum(
            1 for r in records.receipts if r.tool in STAFF_TOOLS and r.status == "applied"
        ),
        "duplicate_records_rejected": sum(
            1
            for r in records.receipts
            if r.status == "rejected" and r.error_code == "DUPLICATE_REFERENCE"
        ),
        "unnecessary_reservations": unused,
    }


def _recovery_delay(final: EventStateView, applied: list[ActionReceipt]) -> int | None:
    notices = [
        rec.observation.received_at
        for rec in final.observations
        if rec.observation.kind == "notice"
    ]
    if not notices or not applied:
        return None
    first_notice = min(notices)
    after = [r.executed_at for r in applied if r.executed_at >= first_notice]
    if not after:
        return None
    return minutes_between(first_notice, min(after))


# ---------------------------------------------------------------------- predicates


def _predicate(
    predicate: OutcomePredicate,
    report: OutcomeReport,
    records: OutcomeRecords,
    violations: list[Violation],
    activities: dict[str, ActivityOutcome],
) -> PredicateResult:
    def result(passed: bool, detail: str) -> PredicateResult:
        return PredicateResult(
            predicate_id=predicate.predicate_id, kind=predicate.kind, passed=passed, detail=detail
        )

    params = predicate.params
    tz = records.final.timezone
    kind = predicate.kind
    if kind == "all_required_completed_by_deadline":
        deadline = _param_time(params.get("deadline")) or records.final.goal.hard_end
        ok, missing = required_completed(records.final, activities, deadline)
        return result(
            ok, "all required activities completed by the deadline" if ok else "; ".join(missing)
        )
    if kind in ("activity_started_at", "activity_not_completed"):
        aid = params.get("activity_id")
        outcome = activities.get(aid) if isinstance(aid, str) else None
        if outcome is None:
            return result(False, f"activity {aid!r} is not a recorded activity")
        if kind == "activity_not_completed":
            ok = outcome.lifecycle != "completed"
            return result(ok, f"{aid} is {outcome.lifecycle}")
        expected = _param_time(params.get("at"))
        if expected is None:
            return result(False, "parameter 'at' is missing or not a timestamp")
        if outcome.started_at is None:
            return result(False, f"{aid} never started ({outcome.lifecycle})")
        ok = outcome.started_at == expected
        return result(
            ok,
            f"{aid} started at {local_label(outcome.started_at, tz)}; expected "
            f"{local_label(expected, tz)}",
        )
    if kind == "no_equipment_start_before_arrival":
        found = [v.message for v in violations if v.category == "equipment_before_arrival"]
        return result(not found, "; ".join(found) or "no equipment-dependent start before arrival")
    if kind == "no_executed_violations":
        return result(not violations, "; ".join(v.message for v in violations) or "no violations")
    if kind == "committed_within_limits":
        found = [v.message for v in violations if v.category in BUDGET_CATEGORIES]
        return result(not found, "; ".join(found) or "committed spend within grant and budget")
    if kind == "committed_spend_equals":
        cents = params.get("cents")
        if not isinstance(cents, int):
            return result(False, "parameter 'cents' is missing or not an integer")
        ok = report.committed_cents == cents
        return result(ok, f"committed {report.committed_cents} cents; expected {cents}")
    if kind == "applied_plan_count":
        count = params.get("count")
        if not isinstance(count, int):
            return result(False, "parameter 'count' is missing or not an integer")
        ok = report.applied_plans == count
        return result(ok, f"{report.applied_plans} applied plan changes; expected {count}")
    if kind == "infeasibility_reported":
        named = [d for d in records.decisions if d.kind == "infeasible" and _names_blocking(d)]
        if named:
            return result(True, f"infeasibility recorded in {named[0].decision_id}")
        if report.infeasibility_reported:
            return result(False, "an infeasible decision exists but names no blocking constraint")
        return result(False, "no infeasible decision was recorded")
    if kind in STOCK_PREDICATES:
        return _stock_predicate(predicate, records, violations)
    return result(False, f"predicate kind {kind!r} is not supported")


STOCK_PREDICATES = frozenset(
    {
        "service_on_time_equals",
        "service_unfulfilled_equals",
        "stock_on_hand_equals",
        "expected_unreceived_equals",
        "stock_conserved",
        "no_staff_attestation_by_agent",
    }
)


def _stock_predicate(
    predicate: OutcomePredicate, records: OutcomeRecords, violations: list[Violation]
) -> PredicateResult:
    def result(passed: bool, detail: str) -> PredicateResult:
        return PredicateResult(
            predicate_id=predicate.predicate_id, kind=predicate.kind, passed=passed, detail=detail
        )

    params = predicate.params
    kind = predicate.kind
    stock = records.final.stock
    if kind == "no_staff_attestation_by_agent":
        by_agent = [
            r.receipt_id
            for r in records.receipts
            if r.tool in STAFF_TOOLS
            and r.actor_role == "coordinator_agent"
            and r.status == "applied"
        ]
        found = [v.message for v in violations if v.category == "attestation_by_agent"]
        ok = not by_agent and not found
        return result(ok, "; ".join(found + by_agent) or "every stock attestation is staff's")
    if stock is None:
        return result(False, "the episode has no consumable stock projection")
    if kind == "stock_conserved":
        bad = [b.resource_id for b in stock.balances if not b.conserved]
        return result(
            not bad, f"not conserved: {', '.join(bad)}" if bad else "every pool conserved"
        )
    quantity = params.get("quantity")
    if not isinstance(quantity, int):
        return result(False, "parameter 'quantity' is missing or not an integer")
    if kind in ("service_on_time_equals", "service_unfulfilled_equals"):
        target = next((s for s in stock.service if s.target_id == params.get("target_id")), None)
        if target is None:
            return result(False, f"target {params.get('target_id')!r} is not registered")
        actual = (
            target.on_time_quantity
            if kind == "service_on_time_equals"
            else target.unfulfilled_quantity
        )
        what = "on time" if kind == "service_on_time_equals" else "unfulfilled"
        return result(
            actual == quantity, f"{target.target_id}: {actual} {what}; expected {quantity}"
        )
    if kind == "stock_on_hand_equals":
        pool = next((b for b in stock.balances if b.resource_id == params.get("resource_id")), None)
        if pool is None:
            return result(False, f"pool {params.get('resource_id')!r} is not registered")
        return result(
            pool.on_hand_quantity == quantity,
            f"{pool.resource_id}: {pool.on_hand_quantity} on hand; expected {quantity}",
        )
    shipment = next(
        (
            s
            for s in stock.expected_shipments
            if s.shipment.shipment_id == params.get("shipment_id")
        ),
        None,
    )
    if shipment is None:
        return result(False, f"shipment {params.get('shipment_id')!r} is not registered")
    return result(
        shipment.outstanding_quantity == quantity,
        f"{shipment.shipment.shipment_id}: {shipment.outstanding_quantity} unreceived;"
        f" expected {quantity}",
    )


def _names_blocking(decision: PolicyDecision) -> bool:
    blocking = decision.details.get("blocking_constraints")
    if isinstance(blocking, list) and any(isinstance(b, str) and b for b in blocking):
        return True
    return any(check in decision.summary for check in HARD_CHECK_IDS)


def _param_time(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            return to_utc(value)
        if isinstance(value, str):
            return parse_ts(value)
    except ValueError:
        return None
    return None
