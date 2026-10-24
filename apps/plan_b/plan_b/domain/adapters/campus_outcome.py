"""Outcome scoring for the campus profiles: goal attainment and executed-rule violations.

Everything is rebuilt from persisted visible records (``OutcomeRecords``): lifecycle history,
plan versions, observations, check-ins, commitments and receipts. Policy narration is never
read. Spend limits (event budget and grants) are domain-independent and are scored by the core
(``evaluation/scoring.py``), after these violations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from plan_b.domain.adapters.outcome import (
    DomainOutcome,
    OutcomeRecords,
    Violation,
    activity_outcome,
    required_completed,
)
from plan_b.domain.models import (
    Assignment,
    CheckInView,
    EpisodeHistory,
    EventStateView,
    ResourceDef,
    ResourceStatus,
)
from plan_b.domain.timeutil import local_label

# Channels whose records carry typed status facts that move a resource's status.
STATUS_CHANNELS = frozenset({"status_tool", "arrival_record"})


@dataclass(frozen=True)
class _Interval:
    activity_id: str
    start: datetime
    end: datetime
    revision: int | None
    assignment: Assignment | None


def score_campus_outcome(final: EventStateView, history: EpisodeHistory) -> DomainOutcome:
    """Required activities completed by the hard end, and the executed-rule violations."""
    records = OutcomeRecords(final, history)
    activities = tuple(activity_outcome(a) for a in final.activities)
    attained, unmet = required_completed(
        final, {a.activity_id: a for a in activities}, final.goal.hard_end
    )
    return DomainOutcome(
        activities=activities,
        goal_attained=attained,
        unmet=tuple(unmet),
        violations=tuple(_violations(records)),
    )


def _intervals(records: OutcomeRecords) -> list[_Interval]:
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


def _violations(records: OutcomeRecords) -> list[Violation]:
    final = records.final
    out: list[Violation] = []
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
                Violation(
                    "completed_after_deadline",
                    f"completed_after_deadline: {view.definition.activity_id} completed at "
                    f"{local_label(done.at, final.timezone)}, after the "
                    f"{local_label(final.goal.hard_end, final.timezone)} deadline",
                )
            )
    return out


def _concurrency(
    intervals: list[_Interval], limit: int, category: str, subject: str, tz: str
) -> list[Violation]:
    out: list[Violation] = []
    seen: set[frozenset[str]] = set()
    for point in sorted({i.start for i in intervals}):
        active = [i for i in intervals if i.start <= point < i.end]
        ids = frozenset(i.activity_id for i in active)
        if len(active) > limit and ids not in seen:
            seen.add(ids)
            out.append(
                Violation(
                    category,
                    f"{category}: {', '.join(sorted(ids))} ran at the same time at "
                    f"{local_label(point, tz)} ({subject} limit {limit})",
                )
            )
    return out


def _start_violations(records: OutcomeRecords, interval: _Interval) -> list[Violation]:
    final = records.final
    out: list[Violation] = []
    assignment = interval.assignment
    aid = interval.activity_id
    at = interval.start
    label = local_label(at, final.timezone)
    if assignment is None:
        return [
            Violation(
                "unscheduled_start",
                f"unscheduled_start: {aid} started at {label} without an assignment in the plan "
                "in effect",
            )
        ]
    for rid in assignment.resource_ids:
        definition = records.resources.get(rid)
        if definition is None:
            out.append(
                Violation("unregistered_resource", f"unregistered_resource: {aid} used {rid}")
            )
            continue
        if definition.kind == "equipment":
            # Booked equipment needs both: a covering commitment and an available status.
            status = _status_at(records, definition, at, interval.revision)
            if status != "available":
                out.append(
                    Violation(
                        "equipment_before_arrival",
                        f"equipment_before_arrival: {aid} started at {label} while {rid} was "
                        f"{status} (no arrival or available status observed by then)",
                    )
                )
            if definition.terms.booking_required and not _committed(
                records, rid, assignment, at, interval.revision
            ):
                out.append(
                    Violation(
                        "booking_without_commitment",
                        f"booking_without_commitment: {aid} started at {label} using {rid} "
                        "without a committed booking",
                    )
                )
        elif definition.kind == "person":
            latest = _latest_checkin(records, rid, at, interval.revision)
            if latest is None:
                out.append(
                    Violation(
                        "role_not_checked_in",
                        f"role_not_checked_in: {aid} started at {label} without a check-in by "
                        f"{rid} covering its window",
                    )
                )
            elif not latest.available.contains(assignment.window):
                out.append(
                    Violation(
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
    records: OutcomeRecords, definition: ResourceDef, at: datetime, revision: int | None
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
    records: OutcomeRecords, rid: str, assignment: Assignment, at: datetime, revision: int | None
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
    records: OutcomeRecords, rid: str, at: datetime, revision: int | None
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
