"""Per-tool validation and effects. Called only by ``tools.executor`` inside its transaction."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from plan_b.domain.adapters.registry import adapter_for
from plan_b.domain.models import (
    ActivityDef,
    CandidateResult,
    EvaluationRequest,
    EventGoal,
    GrantView,
    HoldView,
    ObjectiveWeights,
    Observation,
    ObservationChannel,
    ObservationRecord,
    ResourceDef,
    StateChange,
    StatusFacts,
    TimeWindow,
    ViewerInfo,
)
from plan_b.domain.projection import with_effective_status
from plan_b.domain.timeutil import fmt_ts, local_label, minutes_between
from plan_b.store import repo
from plan_b.store.engine import validity_window
from plan_b.store.projection_db import Visibility, actor_context, build_snapshot, build_view
from plan_b.tools.executor import Ctx, Outcome, Rejection
from plan_b.world.world import world_for_episode

PRESET_WEIGHTS: dict[str, ObjectiveWeights] = {
    "balanced": ObjectiveWeights(
        start_shift_per_minute=1,
        changed_activity=10,
        spend_per_100_cents=4,
        optional_activity_removed=1000,
        participant_notification=5,
    ),
    "preserve_order": ObjectiveWeights(
        start_shift_per_minute=5,
        changed_activity=25,
        spend_per_100_cents=4,
        optional_activity_removed=1000,
        participant_notification=10,
    ),
    "minimize_spend": ObjectiveWeights(
        start_shift_per_minute=1,
        changed_activity=10,
        spend_per_100_cents=12,
        optional_activity_removed=1000,
        participant_notification=5,
    ),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _resource(ctx: Ctx, resource_id: str) -> ResourceDef:
    for r in ctx.scenario.resources:
        if r.resource_id == resource_id:
            return r
    raise Rejection("UNKNOWN_ENTITY", f"resource {resource_id!r} is not registered")


def _activity(ctx: Ctx, activity_id: str) -> ActivityDef:
    for a in ctx.scenario.activities:
        if a.activity_id == activity_id:
            return a
    raise Rejection("UNKNOWN_ENTITY", f"activity {activity_id!r} is not registered")


def _check_revision(ctx: Ctx) -> None:
    expected = ctx.request.expected_revision
    if expected is None:
        return
    current = repo.get_episode(ctx.conn, ctx.episode_id).revision
    if expected != current:
        raise Rejection(
            "REVISION_CONFLICT",
            f"expected revision {expected} but the event is at revision {current}",
            {"expected_revision": expected, "current_revision": current},
        )


def _check_goal_version(ctx: Ctx) -> None:
    expected = ctx.request.expected_goal_version
    if expected is None:
        return
    current = repo.get_episode(ctx.conn, ctx.episode_id).goal_version
    if expected != current:
        raise Rejection(
            "GOAL_VERSION_CONFLICT",
            f"expected goal version {expected} but the goal is at version {current}",
            {"expected_goal_version": expected, "current_goal_version": current},
        )


def _bump(ctx: Ctx, cause_kind: str, cause_ref: str | None, summary: str) -> int:
    return repo.bump_revision(
        ctx.conn,
        ctx.episode_id,
        at=ctx.now,
        cause_kind=cause_kind,
        cause_ref=cause_ref,
        summary=summary,
    )


def _hold_view(ctx: Ctx, hold_id: str) -> HoldView:
    for h in with_effective_status(repo.holds(ctx.conn, ctx.episode_id), ctx.now):
        if h.hold_id == hold_id:
            return h
    raise Rejection("UNKNOWN_ENTITY", f"hold {hold_id!r} does not exist in this episode")


def _viewer(ctx: Ctx) -> ViewerInfo:
    p = repo.principal(ctx.conn, ctx.episode_id, ctx.actor_id)
    return ViewerInfo(
        principal_id=ctx.actor_id,
        role=ctx.session.role,  # type: ignore[arg-type]
        display_name=p.display_name if p else ctx.actor_id,
        grant_id=ctx.session.grant_id,
    )


def _status_source(ctx: Ctx, resource: ResourceDef, fact: str) -> Any:
    sid = resource.terms.status_source_id
    if sid is None or fact not in resource.terms.queryable_facts:
        raise Rejection(
            "STATUS_SOURCE_NOT_REGISTERED",
            f"no registered status source answers {fact!r} for {resource.resource_id}",
            {"queryable_facts": list(resource.terms.queryable_facts)},
        )
    for s in ctx.scenario.status_sources:
        if s.source_id == sid and resource.resource_id in s.entity_ids and fact in s.facts:
            return s
    raise Rejection(
        "STATUS_SOURCE_NOT_REGISTERED", f"status source {sid} is not registered for {fact!r}"
    )


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def precheck(ctx: Ctx, tool: str) -> None:
    """Static request checks that need no scenario time (nothing executes if they fail)."""
    if tool == "query_status":
        resource = _resource(ctx, ctx.args.entity_id)
        if resource.resource_id not in ctx.grant.resource_ids:
            raise Rejection("SCOPE_VIOLATION", f"{resource.resource_id} is outside this grant")
        _status_source(ctx, resource, ctx.args.fact)


def handle(ctx: Ctx, tool: str) -> Outcome:
    return HANDLERS[tool](ctx)


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------


def get_event_state(ctx: Ctx) -> Outcome:
    visibility: Visibility = "audit" if ctx.session.role == "organizer" else "principal"
    view = build_view(ctx.conn, ctx.episode_id, _viewer(ctx), visibility=visibility)
    return Outcome(data=view.model_dump(mode="json"))


def get_action_receipt(ctx: Ctx) -> Outcome:
    target = ctx.args.actor_id or ctx.actor_id
    if target != ctx.actor_id and ctx.session.role != "organizer":
        raise Rejection(
            "SCOPE_VIOLATION",
            "only an organizer with review authority can read another actor's receipts",
        )
    row = ctx.conn.execute(
        "SELECT receipt_id FROM idempotency WHERE episode_id = ? AND actor_id = ?"
        " AND idempotency_key = ?",
        (ctx.episode_id, target, ctx.args.idempotency_key),
    ).fetchone()
    if row is None:
        return Outcome(data={"lookup_status": "not_found", "receipt": None})
    rec = repo.receipt(ctx.conn, ctx.episode_id, row["receipt_id"])
    return Outcome(
        data={"lookup_status": "found", "receipt": rec.model_dump(mode="json") if rec else None}
    )


def list_resources(ctx: Ctx) -> Outcome:
    snap = build_snapshot(ctx.conn, ctx.episode_id)
    out = []
    for r in snap.resources:
        if ctx.args.capability and ctx.args.capability not in r.definition.capabilities:
            continue
        if ctx.args.window is not None and not r.definition.window.overlaps(ctx.args.window):
            continue
        out.append(r.model_dump(mode="json"))
    return Outcome(data={"resources": out})


def query_status(ctx: Ctx) -> Outcome:
    resource = _resource(ctx, ctx.args.entity_id)
    source = _status_source(ctx, resource, ctx.args.fact)
    world = world_for_episode(ctx.conn, ctx.episode_id)
    # The source answers as of the moment it was asked; the answer arrives after the duration.
    record = world.status_answer(resource.resource_id, ctx.args.fact, ctx.requested_at)
    base = {"entity_id": resource.resource_id, "fact": ctx.args.fact}
    if record is None or record.outcome == "unknown":
        raise Rejection(
            "STATUS_UNKNOWN",
            f"{source.label} could not establish {ctx.args.fact} for {resource.resource_id}",
            envelope_status="unknown",
            data={**base, "reason": "the source had no record for this request"},
        )
    if record.outcome == "unavailable" or record.response is None:
        raise Rejection(
            "STATUS_UNAVAILABLE",
            f"{source.label} did not respond; the status remains unknown",
            envelope_status="unavailable",
            data={**base, "reason": "status service unavailable"},
        )
    resp = record.response
    existing = repo.observation_by_source(
        ctx.conn, ctx.episode_id, source.source_id, resp.source_record_id
    )
    deduplicated = existing is not None
    if existing is None:
        obs_id = f"obs_{repo.next_seq(ctx.conn, ctx.episode_id, 'observation'):04d}"
        goal = repo.goal(ctx.conn, ctx.episode_id)
        observation = Observation(
            observation_id=obs_id,
            event_id=ctx.event_id,
            entity_id=resource.resource_id,
            kind="status",
            source_id=source.source_id,
            source_record_id=resp.source_record_id,
            # The source names the lineage its record belongs to (the order's delivery, the
            # same group as its notices and arrival); a record that names none is its own.
            correlation_group=resp.correlation_group or f"{resource.resource_id}_status",
            observed_at=resp.observed_at,
            received_at=ctx.now,
            valid_window=validity_window(resp.observed_at, goal.hard_end),
            authority_scope="resource_status",
            text=resp.text,
            supersedes=(),
        )
        rev = _bump(
            ctx,
            "observation",
            obs_id,
            f"Status from {source.source_id} for {resource.resource_id}: {resp.status_code}",
        )
        record_obj = ObservationRecord(
            observation=observation,
            channel="status_tool",
            submitted_by=ctx.actor_id,
            revision_after=rev,
            structured=StatusFacts(
                fact=ctx.args.fact,
                status_code=resp.status_code,
                domain_status=resp.domain_status,
                reported_eta=resp.reported_eta,
            ),
        )
        repo.insert_observation(ctx.conn, ctx.episode_id, record_obj)
        row = ctx.conn.execute(
            "SELECT status_basis, status_observed_at FROM resources WHERE episode_id = ?"
            " AND resource_id = ?",
            (ctx.episode_id, resource.resource_id),
        ).fetchone()
        newer = (
            row["status_basis"] == "catalog"
            or row["status_observed_at"] is None
            or row["status_observed_at"] <= fmt_ts(resp.observed_at)
        )
        if newer:
            ctx.conn.execute(
                "UPDATE resources SET status = ?, status_basis = 'status_observation',"
                " status_observation_id = ?, status_observed_at = ?, reported_eta = ?"
                " WHERE episode_id = ? AND resource_id = ?",
                (
                    resp.domain_status,
                    obs_id,
                    fmt_ts(resp.observed_at),
                    fmt_ts(resp.reported_eta)
                    if resp.reported_eta and resp.domain_status == "expected"
                    else None,
                    ctx.episode_id,
                    resource.resource_id,
                ),
            )
        existing = record_obj
    age = minutes_between(resp.observed_at, ctx.now)
    return Outcome(
        data={
            **base,
            "observation": existing.model_dump(mode="json"),
            "deduplicated": deduplicated,
            "freshness": {
                "observed_at": fmt_ts(resp.observed_at),
                "retrieved_at": fmt_ts(ctx.now),
                "age_minutes": age,
                "stale": age > source.freshness_minutes,
            },
        }
    )


def evaluate_candidates(ctx: Ctx) -> Outcome:
    _check_goal_version(ctx)
    ep = repo.get_episode(ctx.conn, ctx.episode_id)
    evaluation_id = f"eval_{repo.next_seq(ctx.conn, ctx.episode_id, 'evaluation'):04d}"
    # Judge time-dependent checks at the moment an apply issued now would take effect.
    lead = ctx.scenario.tool_durations_minutes.get("apply_plan", 0)
    snap = build_snapshot(ctx.conn, ctx.episode_id, apply_lead_minutes=lead)
    actor = actor_context(
        ctx.conn, ctx.episode_id, ctx.actor_id, ctx.session.grant_id, ctx.session.role
    )
    result = adapter_for(ep.profile_id).evaluate(
        snap,
        actor,
        EvaluationRequest(templates=ctx.args.templates, hypotheses=ctx.args.hypotheses),
        evaluation_id,
    )
    ctx.conn.execute(
        "INSERT INTO evaluations (episode_id, evaluation_id, revision, goal_version, evaluated_at,"
        " actor_id, hypothetical, body_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ctx.episode_id,
            evaluation_id,
            result.revision,
            result.goal_version,
            fmt_ts(result.evaluated_at),
            ctx.actor_id,
            int(result.hypothetical),
            result.model_dump_json(),
        ),
    )
    for c in result.candidates:
        ctx.conn.execute(
            "INSERT INTO candidates (episode_id, candidate_id, report_id, evaluation_id, signature,"
            " based_on_revision, goal_version, hypothetical, constraint_status, body_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.episode_id,
                c.candidate_id,
                c.report_id,
                evaluation_id,
                c.signature,
                result.revision,
                result.goal_version,
                int(result.hypothetical),
                c.constraint_status,
                c.model_dump_json(),
            ),
        )
    return Outcome(data=result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# mutations
# ---------------------------------------------------------------------------


def hold_resource(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    args = ctx.args
    resource = _resource(ctx, args.resource_id)
    activity = _activity(ctx, args.activity_id)
    if resource.resource_id not in ctx.grant.resource_ids:
        raise Rejection("SCOPE_VIOLATION", f"{resource.resource_id} is outside this grant")
    if activity.activity_id not in ctx.grant.activity_ids:
        raise Rejection("SCOPE_VIOLATION", f"{activity.activity_id} is outside this grant")
    terms = resource.terms
    if not terms.booking_required:
        raise Rejection(
            "HOLD_NOT_SUPPORTED", f"{resource.resource_id} has no booking terms to hold"
        )
    compatible = resource.resource_id in activity.required_resources or any(
        resource.resource_id in _resource(ctx, rid).approved_substitute_ids
        for rid in activity.required_resources
    )
    if not compatible:
        raise Rejection(
            "CONSTRAINT_VIOLATION",
            f"{resource.resource_id} is not a required or approved substitute resource for"
            f" {activity.activity_id}",
        )
    window: TimeWindow = args.window
    if args.quantity > resource.capacity:
        raise Rejection("RESOURCE_CONFLICT", "quantity exceeds the resource capacity")
    if not resource.window.contains(window) or not activity.window.contains(window):
        raise Rejection(
            "CONSTRAINT_VIOLATION", "hold window must lie within the resource and activity windows"
        )
    if window.start <= ctx.now:
        raise Rejection("CONSTRAINT_VIOLATION", "a hold must cover a future window")
    snap = build_snapshot(ctx.conn, ctx.episode_id)
    res_view = next(r for r in snap.resources if r.definition.resource_id == resource.resource_id)
    if res_view.status == "unavailable":
        raise Rejection(
            "RESOURCE_UNAVAILABLE",
            f"{resource.resource_id} is reported unavailable",
            {"status_observation_id": res_view.status_observation_id},
        )
    cutoff = None
    if terms.commitment_cutoff_minutes_before_use is not None:
        cutoff = window.start - timedelta(minutes=terms.commitment_cutoff_minutes_before_use)
        if ctx.now >= cutoff:
            raise Rejection(
                "COMMITMENT_CUTOFF_PASSED",
                f"bookings for {local_label(window.start)} had to be confirmed by"
                f" {local_label(cutoff)}",
                {"commitment_cutoff": fmt_ts(cutoff)},
            )
    conflicts = [o.ref for o in res_view.occupancy if o.window.overlaps(window)]
    used = sum(o.quantity for o in res_view.occupancy if o.window.overlaps(window))
    if used + args.quantity > resource.capacity:
        raise Rejection(
            "RESOURCE_CONFLICT",
            f"{resource.resource_id} capacity {resource.capacity} is already used in that window",
            {"conflicting_refs": conflicts},
        )
    exposure = terms.reserved_exposure_cents * args.quantity
    fee = terms.hold_fee_cents * args.quantity
    c_used, r_used = repo.grant_usage(ctx.conn, ctx.episode_id, ctx.grant.grant_id)
    if r_used + exposure > ctx.grant.max_total_reserved_cents:
        raise Rejection(
            "BUDGET_EXCEEDED",
            f"holding needs {exposure} reserved cents; grant {ctx.grant.grant_id} allows"
            f" {ctx.grant.max_total_reserved_cents - r_used} more",
            {"limit": ctx.grant.max_total_reserved_cents, "used": r_used, "requested": exposure},
        )
    if c_used + fee > ctx.grant.max_total_committed_cents:
        raise Rejection(
            "BUDGET_EXCEEDED",
            f"the hold fee of {fee} cents exceeds the committed limit of grant"
            f" {ctx.grant.grant_id}",
            {"limit": ctx.grant.max_total_committed_cents, "used": c_used, "requested": fee},
        )
    goal = repo.goal(ctx.conn, ctx.episode_id)
    total_c, total_r = repo.ledger_totals(ctx.conn, ctx.episode_id)
    if total_c + total_r + exposure + fee > goal.budget_cents:
        raise Rejection(
            "BUDGET_EXCEEDED",
            "the event contingency budget cannot cover this hold",
            {"budget": goal.budget_cents, "committed": total_c, "reserved": total_r},
        )
    max_minutes = terms.hold_max_minutes or 10
    minutes = min(args.hold_minutes or max_minutes, max_minutes)
    expires = ctx.now + timedelta(minutes=minutes)
    # A hold is a request to the resource's steward, who knows whether the resource is really
    # free. The steward is asked last, so a hold that fails for a public reason (cutoff,
    # capacity, authority, budget) is refused for that reason without consulting it. The answer
    # is what a real booking refusal would say; the private record itself (its id and text) is
    # not disclosed.
    if terms.status_source_id is not None and terms.queryable_facts:
        steward = world_for_episode(ctx.conn, ctx.episode_id).status_answer(
            resource.resource_id, terms.queryable_facts[0], ctx.now
        )
        if steward is not None and steward.outcome == "unavailable":
            raise Rejection(
                "STATUS_UNAVAILABLE",
                f"the steward of {resource.resource_id} could not be reached to confirm a hold",
            )
        if (
            steward is not None
            and steward.outcome == "ok"
            and steward.response is not None
            and steward.response.domain_status == "unavailable"
        ):
            raise Rejection(
                "RESOURCE_UNAVAILABLE",
                f"the steward of {resource.resource_id} declined the hold: it is not available"
                " for that window",
            )
    hold_id = f"hold_{repo.next_seq(ctx.conn, ctx.episode_id, 'hold'):04d}"
    ctx.conn.execute(
        "INSERT INTO holds (episode_id, hold_id, resource_id, activity_id, quantity, window_start,"
        " window_end, created_at, expires_at, commitment_cutoff, reserved_cents, hold_fee_cents,"
        " status, actor_id, grant_id, created_receipt_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
        (
            ctx.episode_id,
            hold_id,
            resource.resource_id,
            activity.activity_id,
            args.quantity,
            fmt_ts(window.start),
            fmt_ts(window.end),
            fmt_ts(ctx.now),
            fmt_ts(expires),
            fmt_ts(cutoff) if cutoff else None,
            exposure,
            fee,
            ctx.actor_id,
            ctx.grant.grant_id,
            ctx.receipt_id,
        ),
    )
    repo.append_ledger(
        ctx.conn,
        ctx.episode_id,
        at=ctx.now,
        kind="reserve",
        committed_delta=0,
        reserved_delta=exposure,
        grant_id=ctx.grant.grant_id,
        hold_id=hold_id,
        receipt_id=ctx.receipt_id,
    )
    if fee:
        repo.append_ledger(
            ctx.conn,
            ctx.episode_id,
            at=ctx.now,
            kind="hold_fee",
            committed_delta=fee,
            reserved_delta=0,
            grant_id=ctx.grant.grant_id,
            hold_id=hold_id,
            receipt_id=ctx.receipt_id,
        )
    _bump(
        ctx,
        "hold_created",
        hold_id,
        f"Hold {hold_id} on {resource.resource_id} for {activity.activity_id}"
        f" {local_label(window.start)}-{local_label(window.end)} until {local_label(expires)}",
    )
    hold = _hold_view(ctx, hold_id)
    return Outcome(
        data={"hold": hold.model_dump(mode="json")},
        summary=(
            f"Held {resource.resource_id} for {activity.activity_id} until {local_label(expires)}"
            f" ({exposure} cents reserved, {fee} cents fee)"
        ),
        state_changes=[
            StateChange(entity_id=hold_id, field="status", before=None, after="active"),
            StateChange(
                entity_id="budget", field="reserved_cents", before=total_r, after=total_r + exposure
            ),
        ],
        committed_delta=fee,
        reserved_delta=exposure,
    )


def release_hold(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    hold = _hold_view(ctx, ctx.args.hold_id)
    if hold.actor_id != ctx.actor_id and ctx.session.role != "organizer":
        raise Rejection("SCOPE_VIOLATION", "only the holder or an organizer can release this hold")
    if hold.effective_status == "committed":
        raise Rejection(
            "HOLD_CONVERTED",
            f"hold {hold.hold_id} became commitment {hold.commitment_id}; a committed booking is"
            " not released through release_hold",
            {"commitment_id": hold.commitment_id},
        )
    if hold.effective_status != "active":
        raise Rejection(
            "HOLD_NOT_ACTIVE",
            f"hold {hold.hold_id} is already {hold.effective_status}; nothing is refunded again",
            {"state": hold.effective_status},
        )
    resource = _resource(ctx, hold.resource_id)
    if not resource.terms.refundable_on_release:
        raise Rejection(
            "UNSUPPORTED_ACTION", "non-refundable hold terms are not supported in Wave 1"
        )
    ctx.conn.execute(
        "UPDATE holds SET status = 'released', terminal_at = ?, terminal_receipt_id = ?"
        " WHERE episode_id = ? AND hold_id = ?",
        (fmt_ts(ctx.now), ctx.receipt_id, ctx.episode_id, hold.hold_id),
    )
    repo.append_ledger(
        ctx.conn,
        ctx.episode_id,
        at=ctx.now,
        kind="release_reserve",
        committed_delta=0,
        reserved_delta=-hold.reserved_cents,
        grant_id=hold.grant_id,
        hold_id=hold.hold_id,
        receipt_id=ctx.receipt_id,
    )
    _bump(ctx, "hold_released", hold.hold_id, f"Hold {hold.hold_id} released: {ctx.args.reason}")
    return Outcome(
        data={"hold": _hold_view(ctx, hold.hold_id).model_dump(mode="json")},
        summary=f"Released hold {hold.hold_id}; {hold.reserved_cents} reserved cents returned",
        state_changes=[
            StateChange(entity_id=hold.hold_id, field="status", before="active", after="released")
        ],
        reserved_delta=-hold.reserved_cents,
    )


def apply_plan(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    _check_goal_version(ctx)
    ep = repo.get_episode(ctx.conn, ctx.episode_id)
    row = ctx.conn.execute(
        "SELECT * FROM candidates WHERE episode_id = ? AND candidate_id = ?",
        (ctx.episode_id, ctx.args.candidate_plan_id),
    ).fetchone()
    if row is None:
        raise Rejection("CANDIDATE_NOT_FOUND", "no stored candidate has that id in this episode")
    if row["report_id"] != ctx.args.constraint_report_ref:
        raise Rejection(
            "CANDIDATE_REPORT_MISMATCH",
            "the constraint report reference does not belong to this candidate",
            {"candidate_report_id": row["report_id"]},
        )
    if row["hypothetical"]:
        raise Rejection(
            "CANDIDATE_HYPOTHETICAL", "candidates evaluated under hypotheses cannot be applied"
        )
    if row["based_on_revision"] != ep.revision or row["goal_version"] != ep.goal_version:
        raise Rejection(
            "CANDIDATE_STALE",
            f"candidate was evaluated at revision {row['based_on_revision']} / goal version"
            f" {row['goal_version']}; the event is at {ep.revision} / {ep.goal_version}",
            {"based_on_revision": row["based_on_revision"], "current_revision": ep.revision},
        )
    stored = CandidateResult.model_validate_json(row["body_json"])
    if stored.constraint_status != "feasible_under_assumptions":
        raise Rejection(
            "CANDIDATE_NOT_APPLICABLE",
            f"the stored report for {stored.candidate_id} is {stored.constraint_status}",
        )
    snap = build_snapshot(ctx.conn, ctx.episode_id)
    actor = actor_context(
        ctx.conn, ctx.episode_id, ctx.actor_id, ctx.session.grant_id, ctx.session.role
    )
    fresh = adapter_for(ep.profile_id).revalidate(snap, actor, stored)
    if fresh.constraint_status != "feasible_under_assumptions":
        failed = [
            c.model_dump(mode="json")
            for c in fresh.checks
            if c.status != "passed" and c.status != "not_applicable"
        ]
        raise Rejection(
            "CONSTRAINT_VIOLATION",
            "the candidate no longer satisfies the hard constraints",
            {"checks": failed},
        )
    if not fresh.authorization.sufficient:
        missing = [m.model_dump(mode="json") for m in fresh.authorization.missing]
        kinds = {m.kind for m in fresh.authorization.missing}
        code = "BUDGET_EXCEEDED"
        if kinds & {"tool_not_granted", "resource_out_of_scope", "activity_out_of_scope"}:
            code = "SCOPE_VIOLATION"
        elif "grant_invalid" in kinds:
            code = "GRANT_EXPIRED"
        elif "review_required" in kinds and not kinds & {
            "committed_spend_limit",
            "reserved_spend_limit",
        }:
            code = "REVIEW_REQUIRED"
        raise Rejection(code, "the candidate exceeds this actor's authority", {"missing": missing})
    unbound = [h for h in fresh.required_holds if h.bound_hold_id is None]
    if unbound:
        previously_bound = {h.resource_id for h in stored.required_holds if h.bound_hold_id}
        if any(h.resource_id in previously_bound for h in unbound):
            raise Rejection(
                "HOLD_EXPIRED",
                "a hold this candidate relied on is no longer live; reacquire and revalidate",
                {"resources": [h.resource_id for h in unbound]},
            )
        raise Rejection(
            "CANDIDATE_NOT_APPLICABLE",
            "the candidate needs a live hold before it can be applied",
            {"resources": [h.resource_id for h in unbound]},
        )
    if not fresh.applicable_now:
        raise Rejection("CANDIDATE_NOT_APPLICABLE", "the candidate is not applicable now")
    if not fresh.changed_activity_ids and not fresh.required_holds:
        raise Rejection(
            "UNSUPPORTED_ACTION",
            "this candidate keeps the current plan; keeping a plan needs no mutation",
        )

    old_plan = repo.plan(ctx.conn, ctx.episode_id)
    old = {a.activity_id: a for a in old_plan.assignments}
    new_version = old_plan.plan_version + 1
    ctx.conn.execute(
        "INSERT INTO plans (episode_id, plan_version, assignments_json, candidate_id, receipt_id,"
        " applied_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            ctx.episode_id,
            new_version,
            repo.dumps([a.model_dump(mode="json") for a in fresh.assignments]),
            fresh.candidate_id,
            ctx.receipt_id,
            fmt_ts(ctx.now),
        ),
    )
    ctx.conn.execute(
        "UPDATE episodes SET plan_version = ? WHERE episode_id = ?", (new_version, ctx.episode_id)
    )
    changes: list[StateChange] = []
    for a in fresh.assignments:
        before = old.get(a.activity_id)
        if before is None:
            continue
        if (before.start, before.end) != (a.start, a.end):
            changes.append(
                StateChange(
                    entity_id=a.activity_id,
                    field="scheduled_window",
                    before={"start": fmt_ts(before.start), "end": fmt_ts(before.end)},
                    after={"start": fmt_ts(a.start), "end": fmt_ts(a.end)},
                )
            )
        if tuple(before.resource_ids) != tuple(a.resource_ids):
            changes.append(
                StateChange(
                    entity_id=a.activity_id,
                    field="resource_ids",
                    before=list(before.resource_ids),
                    after=list(a.resource_ids),
                )
            )
    committed_delta = 0
    reserved_delta = 0
    converted: list[str] = []
    commitment_ids: list[str] = []
    for req in fresh.required_holds:
        assert req.bound_hold_id is not None
        hold = _hold_view(ctx, req.bound_hold_id)
        commitment_id = f"commit_{repo.next_seq(ctx.conn, ctx.episode_id, 'commitment'):04d}"
        cost = _resource(ctx, req.resource_id).terms.commitment_cost_cents
        ctx.conn.execute(
            "UPDATE holds SET status = 'committed', commitment_id = ?, terminal_at = ?,"
            " terminal_receipt_id = ? WHERE episode_id = ? AND hold_id = ?",
            (commitment_id, fmt_ts(ctx.now), ctx.receipt_id, ctx.episode_id, hold.hold_id),
        )
        ctx.conn.execute(
            "INSERT INTO commitments (episode_id, commitment_id, resource_id, activity_id,"
            " window_start, window_end, committed_cents, source_hold_id, plan_version, status,"
            " created_at, receipt_id, actor_id, grant_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)",
            (
                ctx.episode_id,
                commitment_id,
                req.resource_id,
                req.activity_id,
                fmt_ts(req.window.start),
                fmt_ts(req.window.end),
                cost,
                hold.hold_id,
                new_version,
                fmt_ts(ctx.now),
                ctx.receipt_id,
                ctx.actor_id,
                ctx.grant.grant_id,
            ),
        )
        repo.append_ledger(
            ctx.conn,
            ctx.episode_id,
            at=ctx.now,
            kind="convert_reserve",
            committed_delta=0,
            reserved_delta=-hold.reserved_cents,
            grant_id=hold.grant_id,
            hold_id=hold.hold_id,
            receipt_id=ctx.receipt_id,
        )
        repo.append_ledger(
            ctx.conn,
            ctx.episode_id,
            at=ctx.now,
            kind="commit_charge",
            committed_delta=cost,
            reserved_delta=0,
            grant_id=ctx.grant.grant_id,
            hold_id=hold.hold_id,
            commitment_id=commitment_id,
            receipt_id=ctx.receipt_id,
        )
        committed_delta += cost
        reserved_delta -= hold.reserved_cents
        converted.append(hold.hold_id)
        commitment_ids.append(commitment_id)
        changes.append(
            StateChange(entity_id=hold.hold_id, field="status", before="active", after="committed")
        )
    _bump(ctx, "plan_applied", fresh.candidate_id, f"Applied plan v{new_version}: {fresh.label}")
    new_plan = repo.plan(ctx.conn, ctx.episode_id)
    return Outcome(
        data={
            "plan": new_plan.model_dump(mode="json"),
            "converted_hold_ids": converted,
            "commitment_ids": commitment_ids,
        },
        summary=f"Applied {fresh.label} as plan v{new_version}",
        state_changes=changes,
        committed_delta=committed_delta,
        reserved_delta=reserved_delta,
        related_plan_id=fresh.candidate_id,
        constraint_report_ref=fresh.report_id,
    )


def check_in(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    resource = _resource(ctx, ctx.args.resource_id)
    p = repo.principal(ctx.conn, ctx.episode_id, ctx.actor_id)
    if (
        p is None
        or resource.resource_id not in p.speaks_for_resource_ids
        or resource.resource_id not in ctx.grant.resource_ids
    ):
        raise Rejection(
            "SCOPE_VIOLATION",
            f"{ctx.actor_id} may check in only for their own role, not {resource.resource_id}",
        )
    if resource.kind != "person":
        raise Rejection("INVALID_REQUEST", "check-in applies to a person role")
    end = resource.window.end
    if ctx.args.available is not None:
        if ctx.args.available.start > ctx.now:
            raise Rejection(
                "INVALID_REQUEST",
                "a check-in records presence now; future availability is not presence",
            )
        end = ctx.args.available.end
    if end <= ctx.now:
        raise Rejection("INVALID_REQUEST", "availability must extend past the check-in time")
    available = TimeWindow(start=ctx.now, end=end)
    prior = [
        c
        for c in repo.checkins(ctx.conn, ctx.episode_id)
        if c.resource_id == resource.resource_id and c.principal_id == ctx.actor_id
    ]
    if prior and prior[-1].available.end == end:
        raise Rejection(
            "DUPLICATE_CHECK_IN",
            f"{resource.resource_id} is already checked in at {local_label(prior[-1].at)} with"
            " the same availability",
            {"checkin_id": prior[-1].checkin_id},
        )
    n = repo.next_seq(ctx.conn, ctx.episode_id, "checkin")
    checkin_id = f"chk_{n:04d}"
    obs_id = f"obs_{repo.next_seq(ctx.conn, ctx.episode_id, 'observation'):04d}"
    observation = Observation(
        observation_id=obs_id,
        event_id=ctx.event_id,
        entity_id=resource.resource_id,
        kind="check_in",
        source_id=ctx.actor_id,
        source_record_id=f"checkin_{n:04d}",
        correlation_group=f"checkin_{resource.resource_id}",
        observed_at=ctx.now,
        received_at=ctx.now,
        valid_window=available,
        authority_scope="self_report",
        text=(
            f"{p.display_name} checked in for {resource.resource_id} at {local_label(ctx.now)},"
            f" available until {local_label(end)}."
        ),
        supersedes=tuple(c.observation_id for c in prior[-1:] if c.observation_id),
    )
    rev = _bump(
        ctx, "check_in", checkin_id, f"{p.display_name} checked in ({resource.resource_id})"
    )
    rec = ObservationRecord(
        observation=observation,
        channel="participant_session",
        submitted_by=ctx.actor_id,
        revision_after=rev,
    )
    repo.insert_observation(ctx.conn, ctx.episode_id, rec)
    ctx.conn.execute(
        "INSERT INTO checkins (episode_id, checkin_id, principal_id, resource_id, at,"
        " available_start, available_end, observation_id, channel)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'participant_session')",
        (
            ctx.episode_id,
            checkin_id,
            ctx.actor_id,
            resource.resource_id,
            fmt_ts(ctx.now),
            fmt_ts(available.start),
            fmt_ts(available.end),
            obs_id,
        ),
    )
    checkin = next(c for c in repo.checkins(ctx.conn, ctx.episode_id) if c.checkin_id == checkin_id)
    return Outcome(
        data={
            "checkin": checkin.model_dump(mode="json"),
            "observation": rec.model_dump(mode="json"),
        },
        summary=f"{p.display_name} checked in for {resource.resource_id} until {local_label(end)}",
        state_changes=[
            StateChange(
                entity_id=resource.resource_id,
                field="checked_in",
                before=bool(prior),
                after={"checkin_id": checkin_id, "available_until": fmt_ts(end)},
            )
        ],
    )


def submit_observation(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    args = ctx.args
    entity = args.entity_id or ctx.event_id
    known = (
        {r.resource_id for r in ctx.scenario.resources}
        | {a.activity_id for a in ctx.scenario.activities}
        | {ctx.event_id}
    )
    if entity not in known:
        raise Rejection("UNKNOWN_ENTITY", f"{entity!r} is not a registered entity of this event")
    observed_at = args.observed_at or ctx.now
    if observed_at > ctx.now:
        raise Rejection("INVALID_REQUEST", "an observation cannot be observed in the future")
    for ref in args.supersedes:
        if not repo.observation_exists(ctx.conn, ctx.episode_id, ref):
            raise Rejection("INVALID_EVIDENCE_REFERENCE", f"observation {ref!r} does not exist")
    record_id = (
        args.client_record_id
        or f"{ctx.actor_id}_msg_{repo.next_seq(ctx.conn, ctx.episode_id, 'message'):04d}"
    )
    existing = repo.observation_by_source(ctx.conn, ctx.episode_id, ctx.actor_id, record_id)
    if existing is not None:
        if existing.observation.text != args.text:
            raise Rejection(
                "INVALID_EVIDENCE_REFERENCE",
                "that source record id was already used for different content",
                {"observation_id": existing.observation.observation_id},
            )
        return Outcome(
            data={"observation": existing.model_dump(mode="json"), "deduplicated": True},
            summary=(
                f"Duplicate of {existing.observation.observation_id}; the existing record was"
                " returned and nothing changed"
            ),
        )
    goal = repo.goal(ctx.conn, ctx.episode_id)
    obs_id = f"obs_{repo.next_seq(ctx.conn, ctx.episode_id, 'observation'):04d}"
    scope = "organizer_instruction" if ctx.session.role == "organizer" else "self_report"
    channel: ObservationChannel = (
        "organizer_session" if ctx.session.role == "organizer" else "participant_session"
    )
    observation = Observation(
        observation_id=obs_id,
        event_id=ctx.event_id,
        entity_id=entity,
        kind=args.kind,
        source_id=ctx.actor_id,
        source_record_id=record_id,
        correlation_group=args.correlation_group or f"{ctx.actor_id}_{record_id}",
        observed_at=observed_at,
        received_at=ctx.now,
        valid_window=validity_window(observed_at, goal.hard_end),
        authority_scope=scope,  # type: ignore[arg-type]
        text=args.text,
        supersedes=tuple(args.supersedes),
    )
    rev = _bump(ctx, "observation", obs_id, f"Update from {ctx.actor_id} about {entity}")
    rec = ObservationRecord(
        observation=observation,
        channel=channel,
        submitted_by=ctx.actor_id,
        revision_after=rev,
    )
    repo.insert_observation(ctx.conn, ctx.episode_id, rec)
    return Outcome(
        data={"observation": rec.model_dump(mode="json"), "deduplicated": False},
        summary=(
            f"Recorded observation {obs_id} from {ctx.actor_id} (content is data, not a command)"
        ),
        state_changes=[
            StateChange(entity_id=obs_id, field="observation", before=None, after=entity)
        ],
    )


def update_goal(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    _check_goal_version(ctx)
    current: EventGoal = repo.goal(ctx.conn, ctx.episode_id)
    preset = ctx.args.preference_preset
    if preset == current.preference_preset:
        raise Rejection("INVALID_REQUEST", f"the goal already uses the {preset!r} preset")
    new_goal = current.model_copy(
        update={
            "version": current.version + 1,
            "preference_preset": preset,
            "objective_weights": PRESET_WEIGHTS[preset],
        }
    )
    EventGoal.model_validate(new_goal.model_dump())
    ctx.conn.execute(
        "INSERT INTO goals (episode_id, version, body_json, created_at, created_by, receipt_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            ctx.episode_id,
            new_goal.version,
            new_goal.model_dump_json(),
            fmt_ts(ctx.now),
            ctx.actor_id,
            ctx.receipt_id,
        ),
    )
    ctx.conn.execute(
        "UPDATE episodes SET goal_version = ? WHERE episode_id = ?",
        (new_goal.version, ctx.episode_id),
    )
    _bump(
        ctx,
        "goal_updated",
        f"goal_v{new_goal.version}",
        f"Organizer set preferences to {preset!r} (goal v{new_goal.version}); hard constraints"
        " unchanged; older candidates are stale",
    )
    return Outcome(
        data={"goal": new_goal.model_dump(mode="json")},
        summary=f"Goal v{new_goal.version}: preference preset {preset!r} ({ctx.args.reason})",
        state_changes=[
            StateChange(
                entity_id=current.goal_id,
                field="version",
                before=current.version,
                after=new_goal.version,
            ),
            StateChange(
                entity_id=current.goal_id,
                field="preference_preset",
                before=current.preference_preset,
                after=preset,
            ),
        ],
    )


def update_grant(ctx: Ctx) -> Outcome:
    _check_revision(ctx)
    args = ctx.args
    if args.target_grant_id == ctx.grant.grant_id:
        raise Rejection("SCOPE_VIOLATION", "an organizer cannot change its own grant")
    found = repo.current_grant(ctx.conn, ctx.episode_id, args.target_grant_id)
    if found is None:
        raise Rejection("UNKNOWN_ENTITY", f"grant {args.target_grant_id!r} does not exist")
    target, version, revoked = found
    if target.principal_role == "organizer":
        raise Rejection("SCOPE_VIOLATION", "organizer grants are outside this control")
    if revoked:
        raise Rejection("GRANT_REVOKED", f"grant {target.grant_id} is already revoked")
    goal = repo.goal(ctx.conn, ctx.episode_id)
    committed = (
        args.max_total_committed_cents
        if args.max_total_committed_cents is not None
        else target.max_total_committed_cents
    )
    reserved = (
        args.max_total_reserved_cents
        if args.max_total_reserved_cents is not None
        else target.max_total_reserved_cents
    )
    if committed > min(ctx.grant.max_total_committed_cents, goal.budget_cents):
        raise Rejection(
            "BUDGET_EXCEEDED",
            "the organizer can delegate at most its own committed limit and the event budget",
            {"limit": min(ctx.grant.max_total_committed_cents, goal.budget_cents)},
        )
    if reserved > min(ctx.grant.max_total_reserved_cents, goal.budget_cents):
        raise Rejection(
            "BUDGET_EXCEEDED",
            "the organizer can delegate at most its own reserved limit and the event budget",
            {"limit": min(ctx.grant.max_total_reserved_cents, goal.budget_cents)},
        )
    if (
        not args.revoke
        and committed == target.max_total_committed_cents
        and reserved == target.max_total_reserved_cents
    ):
        raise Rejection("INVALID_REQUEST", "the requested grant change changes nothing")
    new = target.model_copy(
        update={"max_total_committed_cents": committed, "max_total_reserved_cents": reserved}
    )
    ctx.conn.execute(
        "UPDATE grants SET is_current = 0 WHERE episode_id = ? AND grant_id = ? AND is_current = 1",
        (ctx.episode_id, target.grant_id),
    )
    ctx.conn.execute(
        "INSERT INTO grants (episode_id, grant_id, version, body_json, principal_id, revoked,"
        " is_current, issued_at, issued_receipt_id) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (
            ctx.episode_id,
            target.grant_id,
            version + 1,
            new.model_dump_json(),
            target.principal_id,
            int(args.revoke),
            fmt_ts(ctx.now),
            ctx.receipt_id,
        ),
    )
    what = (
        "revoked"
        if args.revoke
        else f"committed limit {target.max_total_committed_cents}->{committed},"
        f" reserved limit {target.max_total_reserved_cents}->{reserved}"
    )
    _bump(
        ctx,
        "grant_updated",
        target.grant_id,
        f"Organizer changed {target.grant_id} v{version + 1}: {what}",
    )
    c_used, r_used = repo.grant_usage(ctx.conn, ctx.episode_id, target.grant_id)
    view = GrantView(
        grant=new,
        version=version + 1,
        revoked=bool(args.revoke),
        valid_now=not args.revoke and ctx.now < new.expires_at,
        committed_used_cents=c_used,
        reserved_used_cents=r_used,
        issued_receipt_id=ctx.receipt_id,
    )
    changes = [
        StateChange(entity_id=target.grant_id, field="version", before=version, after=version + 1)
    ]
    if committed != target.max_total_committed_cents:
        changes.append(
            StateChange(
                entity_id=target.grant_id,
                field="max_total_committed_cents",
                before=target.max_total_committed_cents,
                after=committed,
            )
        )
    if reserved != target.max_total_reserved_cents:
        changes.append(
            StateChange(
                entity_id=target.grant_id,
                field="max_total_reserved_cents",
                before=target.max_total_reserved_cents,
                after=reserved,
            )
        )
    if args.revoke:
        changes.append(
            StateChange(entity_id=target.grant_id, field="revoked", before=False, after=True)
        )
    return Outcome(
        data={"grant": view.model_dump(mode="json")},
        summary=f"Organizer updated {target.grant_id}: {what} ({args.reason})",
        state_changes=changes,
    )


HANDLERS = {
    "get_event_state": get_event_state,
    "get_action_receipt": get_action_receipt,
    "list_resources": list_resources,
    "query_status": query_status,
    "evaluate_candidates": evaluate_candidates,
    "hold_resource": hold_resource,
    "release_hold": release_hold,
    "apply_plan": apply_plan,
    "check_in": check_in,
    "submit_observation": submit_observation,
    "update_goal": update_goal,
    "update_grant": update_grant,
}
