"""Execution readiness for the activity/resource core (campus and skills-exchange profiles).

Readiness uses only visible evidence at the given scenario time:

* every predecessor has a ``completed`` lifecycle record;
* each scheduled resource is ready by kind:
  - space: status ``available``;
  - equipment: status ``available`` (for an ``expected`` delivery this requires an observed
    arrival; a reported ETA is never readiness), and, if the resource requires booking, an
    active commitment covering the scheduled window;
  - person: a check-in whose declared availability covers the scheduled window.
    Declared future availability in the catalog is not presence;
* no other main-program activity is in progress (program exclusivity).

``mode="execution"`` applies all of these strictly at the scheduled start. ``mode="preview"``
reports the same evidence ahead of time: a predecessor that is not yet completed but is
scheduled to end by this activity's start is *pending*, and exclusivity is left to execution.
A plan accepted under an ETA assumption does not change any of these facts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from plan_b.domain.models import (
    ActivityDef,
    Assignment,
    CheckInView,
    CommitmentView,
    ReadinessReport,
    ResourceView,
    TimeWindow,
)
from plan_b.domain.timeutil import local_label


def check_readiness(
    *,
    activity: ActivityDef,
    assignment: Assignment | None,
    at: datetime,
    mode: Literal["preview", "execution"],
    lifecycles: dict[str, str],
    assignments: dict[str, Assignment],
    resources: dict[str, ResourceView],
    checkins: tuple[CheckInView, ...],
    commitments: tuple[CommitmentView, ...],
    program_activity_ids: set[str],
) -> ReadinessReport:
    met: list[str] = []
    unmet: list[str] = []
    pending: list[str] = []
    evidence: list[str] = []

    if assignment is None:
        return ReadinessReport(
            activity_id=activity.activity_id,
            at=at,
            mode=mode,
            ready=False,
            met=(),
            unmet=("not scheduled in the active plan",),
            pending=(),
            evidence_refs=(),
        )

    for pred in activity.predecessors:
        state = lifecycles.get(pred, "unknown")
        pred_assignment = assignments.get(pred)
        if state == "completed":
            met.append(f"predecessor {pred} completed")
        elif (
            mode == "preview"
            and state in ("planned", "ready", "started")
            and pred_assignment is not None
            and pred_assignment.end <= assignment.start
        ):
            pending.append(
                f"predecessor {pred} scheduled to complete by {local_label(pred_assignment.end)}"
            )
        else:
            unmet.append(f"predecessor {pred} is {state}, not completed")

    window = TimeWindow(start=assignment.start, end=assignment.end)
    for rid in assignment.resource_ids:
        res = resources.get(rid)
        if res is None:
            unmet.append(f"resource {rid} is not registered")
            continue
        kind = res.definition.kind
        if kind == "space":
            if res.status == "available":
                met.append(f"{rid} available")
            else:
                unmet.append(f"{rid} is {res.status}")
        elif kind == "equipment":
            if res.status == "available":
                met.append(f"{rid} available ({res.status_basis.replace('_', ' ')})")
                if res.status_observation_id:
                    evidence.append(res.status_observation_id)
            elif res.status == "expected":
                eta = (
                    f"; reported ETA {local_label(res.reported_eta)}"
                    if res.reported_eta is not None
                    else ""
                )
                unmet.append(f"{rid} not yet observed at the venue (expected{eta})")
            else:
                unmet.append(f"{rid} is {res.status}")
            if res.definition.terms.booking_required:
                covering = [
                    c
                    for c in commitments
                    if c.resource_id == rid
                    and c.activity_id == activity.activity_id
                    and c.window.contains(window)
                ]
                if covering:
                    met.append(f"{rid} booking committed ({covering[0].commitment_id})")
                    evidence.append(covering[0].commitment_id)
                else:
                    unmet.append(f"{rid} requires a committed booking for this window")
        elif kind == "person":
            # The latest check-in for the role is the person's current declaration: a later,
            # narrower availability supersedes an earlier, wider one.
            role_checkins = [c for c in checkins if c.resource_id == rid]
            if not role_checkins:
                unmet.append(f"{rid} has not checked in for {local_label(window.start)}")
            else:
                # Ties within one minute go to the later record (insertion order).
                latest = max(enumerate(role_checkins), key=lambda ic: (ic[1].at, ic[0]))[1]
                if latest.available.contains(window):
                    met.append(f"{rid} checked in at {local_label(latest.at)}")
                    evidence.append(latest.checkin_id)
                else:
                    span = (
                        f"{local_label(latest.available.start)}-{local_label(latest.available.end)}"
                    )
                    unmet.append(
                        f"{rid}'s latest check-in ({local_label(latest.at)}) is available {span},"
                        f" not covering {local_label(window.start)}-{local_label(window.end)}"
                    )
                    evidence.append(latest.checkin_id)
        else:
            unmet.append(f"readiness for resource kind '{kind}' is not supported in Wave 1")

    if activity.program and mode == "execution":
        busy = [
            aid
            for aid, state in lifecycles.items()
            if state == "started" and aid != activity.activity_id and aid in program_activity_ids
        ]
        if busy:
            unmet.append(f"program exclusivity: {', '.join(sorted(busy))} still in progress")
        else:
            met.append("no other program activity in progress")

    return ReadinessReport(
        activity_id=activity.activity_id,
        at=at,
        mode=mode,
        ready=not unmet,
        met=tuple(met),
        unmet=tuple(unmet),
        pending=tuple(pending),
        evidence_refs=tuple(evidence),
    )
