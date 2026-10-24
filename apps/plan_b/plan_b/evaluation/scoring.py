"""State-based outcome scoring for one episode.

The report is computed only from persisted visible records: the final ``EventStateView`` and
the ``EpisodeHistory`` (tool calls, transitions, decisions, receipts). Policy decisions are
narration; they matter only for ``infeasibility_reported``. Execution facts come from
lifecycle records, plan versions, observations, check-ins, commitments, grants and receipts.

Private ``PrivateCase`` predicates are evaluated only when the runner passes a case. Their
results, the expected outcome and anything derived from them stay in the runner-side report;
``public_summary`` removes them for browser-facing use.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeVar

from plan_b.domain.models import (
    ActionReceipt,
    ActivityOutcome,
    ActivityView,
    Assignment,
    CheckInView,
    EpisodeHistory,
    EventStateView,
    GrantView,
    HoldStats,
    OutcomePredicate,
    OutcomeReport,
    PlanView,
    PolicyDecision,
    PredicateResult,
    PrivateCase,
    ResourceDef,
    ResourceStatus,
)
from plan_b.domain.timeutil import local_label, minutes_between, parse_ts, to_utc

REPORT_VERSION: Literal["1.0.0"] = "1.0.0"
PLAN_CHANGE_FIELDS = frozenset({"scheduled_window", "resource_ids"})
PRIVATE_FIELDS = frozenset({"predicates", "expected_outcome", "case_ref", "matches_expectation"})
# Hard-check identifiers of the campus planner (contract section 10).
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
)
BUDGET_CATEGORIES = frozenset({"grant_limit", "budget"})
# Channels whose records carry typed status facts that move a resource's status.
STATUS_CHANNELS = frozenset({"status_tool", "arrival_record"})

T = TypeVar("T")


@dataclass(frozen=True)
class _Violation:
    category: str
    message: str


@dataclass(frozen=True)
class _Interval:
    activity_id: str
    start: datetime
    end: datetime
    revision: int | None
    assignment: Assignment | None


class _Records:
    """Indexes over the persisted records of one episode."""

    def __init__(self, final: EventStateView, history: EpisodeHistory) -> None:
        self.final = final
        self.history = history
        self.receipts = _merge(history.receipts, final.receipts, lambda r: r.receipt_id)
        self.receipt_by_id = {r.receipt_id: r for r in self.receipts}
        self.decisions = _merge(history.decisions, final.decisions, lambda d: d.decision_id)
        self.resources = {r.definition.resource_id: r.definition for r in final.resources}
        self.observation_revision = {
            rec.observation.observation_id: rec.revision_after for rec in final.observations
        }
        plans = _merge(final.plan_history, (final.plan,), lambda p: str(p.plan_version))
        self.plans = sorted(plans, key=lambda p: p.plan_version)

    def plan_at(self, at: datetime, revision: int | None) -> PlanView:
        """The plan in effect at a start: the latest plan applied before it, else the first."""
        chosen = self.plans[0]
        for plan in self.plans[1:]:
            if plan.applied_at is None:
                continue
            receipt = self.receipt_by_id.get(plan.applied_receipt_id or "")
            if receipt is not None and revision is not None:
                in_effect = receipt.revision_after <= revision
            else:
                in_effect = plan.applied_at <= at
            if in_effect:
                chosen = plan
        return chosen

    def before(
        self, at: datetime, revision: int | None, record_at: datetime, record_rev: int | None
    ) -> bool:
        """Whether a record was persisted no later than (at, revision)."""
        if revision is not None and record_rev is not None:
            return record_rev <= revision and record_at <= at
        return record_at <= at


def score_episode(
    final: EventStateView,
    history: EpisodeHistory,
    case: PrivateCase | None = None,
    policy_id: str | None = None,
) -> OutcomeReport:
    """Outcome of one episode from its persisted records (plus case predicates runner-side)."""
    records = _Records(final, history)
    activities = tuple(_activity_outcome(a) for a in final.activities)
    violations = _violations(records)
    by_id = {a.activity_id: a for a in activities}
    required_done, _ = _required_completed(final, by_id, final.goal.hard_end)
    goal_complete = required_done and not violations
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


# ---------------------------------------------------------------------- activities


def _activity_outcome(view: ActivityView) -> ActivityOutcome:
    started = next((e.at for e in view.history if e.state == "started"), None)
    completed = next((e.at for e in view.history if e.state == "completed"), None)
    reasons: list[str] = []
    for e in view.history:
        if e.state == "failed":
            reasons.extend(e.reasons)
    return ActivityOutcome(
        activity_id=view.definition.activity_id,
        required=view.definition.required,
        lifecycle=view.lifecycle,
        started_at=started,
        completed_at=completed,
        failure_reasons=tuple(reasons),
    )


def _required_completed(
    final: EventStateView, by_id: dict[str, ActivityOutcome], deadline: datetime
) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for aid in final.goal.required_activity_ids:
        outcome = by_id.get(aid)
        if outcome is None:
            missing.append(f"{aid} is not a recorded activity")
        elif outcome.lifecycle != "completed" or outcome.completed_at is None:
            missing.append(f"{aid} is {outcome.lifecycle}")
        elif outcome.completed_at > deadline:
            missing.append(
                f"{aid} completed at {local_label(outcome.completed_at, final.timezone)}, after "
                "the deadline"
            )
    return not missing, missing


def _intervals(records: _Records) -> list[_Interval]:
    """Actual execution intervals: [started, completed | failed | final clock)."""
    out: list[_Interval] = []
    for view in records.final.activities:
        start_event = next((e for e in view.history if e.state == "started"), None)
        if start_event is None:
            continue
        end_event = next(
            (
                e
                for e in view.history
                if e.state in ("completed", "failed") and e.seq > start_event.seq
            ),
            None,
        )
        end = end_event.at if end_event is not None else records.final.clock
        plan = records.plan_at(start_event.at, start_event.revision)
        assignment = next(
            (a for a in plan.assignments if a.activity_id == view.definition.activity_id), None
        )
        out.append(
            _Interval(
                activity_id=view.definition.activity_id,
                start=start_event.at,
                end=max(end, start_event.at),
                revision=start_event.revision,
                assignment=assignment,
            )
        )
    return out


# ---------------------------------------------------------------------- violations


def _violations(records: _Records) -> list[_Violation]:
    final = records.final
    out: list[_Violation] = []
    intervals = _intervals(records)
    program = {a.definition.activity_id for a in final.activities if a.definition.program}
    out.extend(
        _concurrency(
            [i for i in intervals if i.activity_id in program],
            final.goal.program_concurrency,
            "program_overlap",
            "program activities",
            final.timezone,
        )
    )
    for rid, definition in records.resources.items():
        using = [
            i for i in intervals if i.assignment is not None and rid in i.assignment.resource_ids
        ]
        out.extend(
            _concurrency(using, definition.capacity, "resource_capacity", rid, final.timezone)
        )
    for interval in intervals:
        out.extend(_start_violations(records, interval))
    for view in final.activities:
        done = next((e for e in view.history if e.state == "completed"), None)
        if done is not None and done.at > final.goal.hard_end:
            out.append(
                _Violation(
                    "completed_after_deadline",
                    f"completed_after_deadline: {view.definition.activity_id} completed at "
                    f"{local_label(done.at, final.timezone)}, after the "
                    f"{local_label(final.goal.hard_end, final.timezone)} deadline",
                )
            )
    budget = final.budget
    if budget.committed_cents > final.goal.budget_cents:
        out.append(
            _Violation(
                "budget",
                f"budget: committed {budget.committed_cents} cents exceeds the event budget "
                f"{final.goal.budget_cents} cents",
            )
        )
    elif budget.committed_cents + budget.reserved_cents > final.goal.budget_cents:
        out.append(
            _Violation(
                "budget",
                f"budget: committed plus reserved {budget.committed_cents + budget.reserved_cents}"
                f" cents exceeds the event budget {final.goal.budget_cents} cents",
            )
        )
    if budget.reserved_cents < 0:
        out.append(
            _Violation(
                "reserved_negative", f"reserved_negative: reserved is {budget.reserved_cents} cents"
            )
        )
    out.extend(_grant_violations(records))
    return out


def _concurrency(
    intervals: list[_Interval], limit: int, category: str, subject: str, tz: str
) -> list[_Violation]:
    out: list[_Violation] = []
    seen: set[frozenset[str]] = set()
    for point in sorted({i.start for i in intervals}):
        active = [i for i in intervals if i.start <= point < i.end]
        ids = frozenset(i.activity_id for i in active)
        if len(active) > limit and ids not in seen:
            seen.add(ids)
            out.append(
                _Violation(
                    category,
                    f"{category}: {', '.join(sorted(ids))} ran at the same time at "
                    f"{local_label(point, tz)} ({subject} limit {limit})",
                )
            )
    return out


def _start_violations(records: _Records, interval: _Interval) -> list[_Violation]:
    final = records.final
    out: list[_Violation] = []
    assignment = interval.assignment
    aid = interval.activity_id
    at = interval.start
    label = local_label(at, final.timezone)
    if assignment is None:
        return [
            _Violation(
                "unscheduled_start",
                f"unscheduled_start: {aid} started at {label} without an assignment in the plan "
                "in effect",
            )
        ]
    for rid in assignment.resource_ids:
        definition = records.resources.get(rid)
        if definition is None:
            out.append(
                _Violation("unregistered_resource", f"unregistered_resource: {aid} used {rid}")
            )
            continue
        if definition.kind == "equipment":
            # Booked equipment needs both: a covering commitment and an available status.
            status = _status_at(records, definition, at, interval.revision)
            if status != "available":
                out.append(
                    _Violation(
                        "equipment_before_arrival",
                        f"equipment_before_arrival: {aid} started at {label} while {rid} was "
                        f"{status} (no arrival or available status observed by then)",
                    )
                )
            if definition.terms.booking_required and not _committed(
                records, rid, assignment, at, interval.revision
            ):
                out.append(
                    _Violation(
                        "booking_without_commitment",
                        f"booking_without_commitment: {aid} started at {label} using {rid} "
                        "without a committed booking",
                    )
                )
        elif definition.kind == "person":
            latest = _latest_checkin(records, rid, at, interval.revision)
            if latest is None:
                out.append(
                    _Violation(
                        "role_not_checked_in",
                        f"role_not_checked_in: {aid} started at {label} without a check-in by "
                        f"{rid} covering its window",
                    )
                )
            elif not latest.available.contains(assignment.window):
                out.append(
                    _Violation(
                        "role_not_checked_in",
                        f"role_not_checked_in: {aid} started at {label} although {rid}'s latest "
                        f"check-in ({local_label(latest.at, final.timezone)}) is available "
                        f"{local_label(latest.available.start, final.timezone)}-"
                        f"{local_label(latest.available.end, final.timezone)}, not covering its "
                        "window",
                    )
                )
    return out


def _status_at(
    records: _Records, definition: ResourceDef, at: datetime, revision: int | None
) -> ResourceStatus:
    """A resource's status at a start, rebuilt with the engine's rule.

    Status and arrival records recorded by then apply in recording order, and each changes
    the status only when its source time (``observed_at``) is not older than the record the
    status already rests on. The catalog status is older than any record. An old record
    ingested late (an ETA retrieved after the arrival) therefore changes nothing."""
    status: ResourceStatus = definition.initial_status
    basis: datetime | None = None  # observed_at of the record in effect; None = catalog
    for rec in sorted(records.final.observations, key=lambda r: r.revision_after):
        obs = rec.observation
        if obs.entity_id != definition.resource_id or rec.channel not in STATUS_CHANNELS:
            continue
        if rec.structured is None:
            continue
        if not records.before(at, revision, obs.received_at, rec.revision_after):
            continue
        if basis is None or basis <= obs.observed_at:
            status = rec.structured.domain_status
            basis = obs.observed_at
    return status


def _committed(
    records: _Records, rid: str, assignment: Assignment, at: datetime, revision: int | None
) -> bool:
    for c in records.final.commitments:
        if c.resource_id != rid or c.activity_id != assignment.activity_id:
            continue
        if not c.window.contains(assignment.window):
            continue
        receipt = records.receipt_by_id.get(c.receipt_id)
        rev = receipt.revision_after if receipt is not None else None
        if records.before(at, revision, c.created_at, rev):
            return True
    return False


def _latest_checkin(
    records: _Records, rid: str, at: datetime, revision: int | None
) -> CheckInView | None:
    """The role's latest check-in recorded by a start. A later check-in supersedes an earlier
    one, even a wider one; ties within a minute go to the later record (as in readiness)."""
    latest: CheckInView | None = None
    for c in records.final.checkins:
        if c.resource_id != rid:
            continue
        rev = records.observation_revision.get(c.observation_id or "")
        if not records.before(at, revision, c.at, rev):
            continue
        if latest is None or c.at >= latest.at:
            latest = c
    return latest


def _grant_violations(records: _Records) -> list[_Violation]:
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
    out: list[_Violation] = []
    for gid in sorted(spend):
        history = sorted(versions.get(gid, []), key=lambda g: g.version)
        if not history:
            out.append(
                _Violation(
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
                    _Violation(
                        "grant_limit",
                        f"grant_limit: the version of {gid} in effect when {ref} was made cannot "
                        "be established from the issuing receipts",
                    )
                )
                continue
            grant = version.grant
            if version.revoked:
                out.append(
                    _Violation(
                        "grant_limit",
                        f"grant_limit: {ref} was made under revoked {gid} v{version.version}",
                    )
                )
            if at >= grant.expires_at:
                out.append(
                    _Violation("grant_limit", f"grant_limit: {ref} was made after {gid} expired")
                )
            if cumulative > grant.max_total_committed_cents:
                out.append(
                    _Violation(
                        "grant_limit",
                        f"grant_limit: {cumulative} cents committed under {gid} by {ref} exceeds "
                        f"the limit {grant.max_total_committed_cents} of version {version.version}",
                    )
                )
    return out


def _version_at(
    records: _Records, history: list[GrantView], at: datetime, revision: int | None
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
    )


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
    records: _Records,
    violations: list[_Violation],
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
        ok, missing = _required_completed(records.final, activities, deadline)
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
    return result(False, f"predicate kind {kind!r} is not supported")


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


def _merge(first: Iterable[T], second: Iterable[T], key: Callable[[T], str]) -> list[T]:
    seen: dict[str, T] = {}
    for item in (*first, *second):
        seen.setdefault(key(item), item)
    return list(seen.values())
