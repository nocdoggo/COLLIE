"""Evaluation metrics (``08_evaluation.md``, "Outcomes and definitions" and the pantry metrics
table), per episode and per policy, from a results directory of ``plan-b eval run``.

Every quantity comes from the episode's persisted records: the final state of its sanitized
trace (holds, commitments, plan, observations, stock balances, movements, receipts and
distributions), its action receipts and its tool-call log, and the public outcome report the
scorer computed from the same records. Two definitions need the policy's own records and say
so: *appropriate infeasibility* and *supported partial fulfillment* need an ``infeasible``
decision that names its blocking constraints (the explanation is part of the outcome), and the
extraction labels compare a policy's recorded structured reading of a message with the
evaluator's annotation of that message. Model narration (rationales, summaries) is never
scored.

Evaluator data (outcome class, negative-control designation, recovery data, achievable
quantities, message annotations) comes from ``runner_private/cases.json``; the metrics are
therefore evaluator output.

Rules, as the protocol states them:

* the outcome classes are scored separately: goal completion on campus ``goal`` cases
  (C01-C07), appropriate infeasibility on ``infeasible`` cases (C08), original-target attainment
  on pantry ``target`` cases (T01-T02) and supported partial fulfillment on ``partial`` cases
  (T03-T04); a timed-out or crashed episode is a failure in its class, never dropped; a planned
  episode without any record is *missing*, listed and counted apart from the denominators;
* unnecessary committed changes are counted only on designated negative controls: each applied
  ``apply_plan`` receipt of the coordinator is one committed change;
* plan churn is the coordinator's applied plan changes plus the assignments they altered;
* verification effort counts status checks, distinct sources (entity, fact), repeated checks
  (a retry is never a new source), failed checks and their modeled minutes;
* recovery delay runs from the first actionable public update to the first applied plan change
  after it, only on cases that require a recovery and only when the episode's outcome succeeded;
  otherwise the episode is unrecovered and carries the horizon (update to hard end);
* preparation cost is hold minutes, hold fees, expired holds and holds still active at the end;
* computation cost is model calls, retries, tokens, provider latency, provider-reported cost
  and tool calls, kept apart from modeled event money.

No composite score is computed and no significance is claimed.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from plan_b.domain.timeutil import parse_ts
from plan_b.evaluation.scoring import PLAN_CHANGE_FIELDS

METRICS_VERSION = "plan_b.eval_metrics/1.0.0"
COORDINATOR = "coordinator_agent"
# Failures in their outcome class (never dropped): a timeout, a crash, a trace that no longer
# matches its record. ``aborted`` (the harness stopped the model calls) and ``missing`` are
# listed apart from the denominators.
FAILED_STATUSES = ("timeout", "crashed", "integrity_failed")
UNSCORED_STATUSES = ("missing", "aborted")
FAILED_CHECKS = ("unknown", "unavailable", "rejected")
CLASS_METRIC = {
    "goal": "goal_completion",
    "infeasible": "appropriate_infeasibility",
    "target": "target_attainment",
    "partial": "supported_partial",
}
POLICY_ORDER = ("P0", "P1", "P2", "P3")


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_ts(value)
    except ValueError:
        return None


def _minutes(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return int((end - start).total_seconds() // 60)


# ---------------------------------------------------------------------------------- pieces


def names_blocking(decision: dict[str, Any]) -> bool:
    """An ``infeasible`` decision that names at least one blocking constraint in its
    structured details (never from its text)."""
    blocking = decision.get("details", {}).get("blocking_constraints")
    return isinstance(blocking, list) and any(isinstance(b, str) and b for b in blocking)


def reported_shortfalls(decision: dict[str, Any]) -> dict[str | None, int]:
    """``{target_id: quantity}`` an ``infeasible`` decision reports as unfulfilled, from its
    structured details only: ``shortfall_quantity`` (with ``target_id``) or each item of
    ``shortfalls``. A target id of None stands for a decision that names none."""
    details = decision.get("details", {})
    out: dict[str | None, int] = {}
    if isinstance(details.get("shortfall_quantity"), int):
        out[details.get("target_id")] = details["shortfall_quantity"]
    for item in details.get("shortfalls") or []:
        if isinstance(item, dict) and isinstance(item.get("shortfall_quantity"), int):
            out[item.get("target_id")] = item["shortfall_quantity"]
    return out


def _coordinator_calls(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in trace["tool_calls"] if t.get("actor_role") == COORDINATOR]


def _coordinator_ids(trace: dict[str, Any]) -> set[str]:
    ids = {t["actor_id"] for t in _coordinator_calls(trace) if t.get("actor_id")}
    ids |= {r["actor_id"] for r in trace["receipts"] if r.get("actor_role") == COORDINATOR}
    return ids


def _applied_plans(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            r
            for r in trace["receipts"]
            if r["tool"] == "apply_plan"
            and r["status"] == "applied"
            and r.get("actor_role") == COORDINATOR
        ),
        key=lambda r: (r["executed_at"], r["revision_after"]),
    )


def invalid_attempts(trace: dict[str, Any]) -> dict[str, Any]:
    rejected = [t for t in _coordinator_calls(trace) if t["envelope_status"] == "rejected"]
    return {
        "count": len(rejected),
        "by_code": dict(sorted(Counter(str(t.get("error_code")) for t in rejected).items())),
        "by_tool": dict(sorted(Counter(t["tool"] for t in rejected).items())),
    }


def verification_effort(trace: dict[str, Any]) -> dict[str, Any]:
    checks = [t for t in _coordinator_calls(trace) if t["tool"] == "query_status"]
    sources = [
        (
            (t.get("request") or {}).get("arguments", {}).get("entity_id"),
            (t.get("request") or {}).get("arguments", {}).get("fact"),
        )
        for t in checks
    ]
    minutes = [_minutes(_ts(t.get("requested_at")), _ts(t.get("completed_at"))) for t in checks]
    return {
        "status_checks": len(checks),
        "distinct_sources": len(set(sources)),
        "repeated_checks": len(checks) - len(set(sources)),
        "failed_checks": sum(1 for t in checks if t["envelope_status"] in FAILED_CHECKS),
        "simulated_minutes": sum(m for m in minutes if m is not None),
    }


def _failing_before(trace: dict[str, Any], revision: int) -> set[str] | None:
    """The activities the kept plan already failed a hard check on in the latest evaluation
    made at or before ``revision`` (None when there is none): an activity a failed check names,
    or one whose kept assignment uses a resource a failed check names (a resource-level check,
    an unavailable resource for example, names only the resource)."""
    evaluations = [
        e
        for e in (trace.get("evaluations") or {}).values()
        if not e.get("hypothetical") and int(e.get("revision", -1)) <= revision
    ]
    if not evaluations:
        return None
    latest = max(evaluations, key=lambda e: (int(e["revision"]), str(e.get("evaluated_at"))))
    keep = next(
        (
            c
            for c in latest.get("candidates", [])
            if c["candidate_id"] == latest.get("keep_candidate_id")
        ),
        None,
    )
    if keep is None:
        return None
    named = {
        x
        for c in keep.get("checks", [])
        if c.get("status") == "failed"
        for x in c.get("entity_ids", [])
    }
    return named | {
        a["activity_id"]
        for a in keep.get("assignments", [])
        if named & {a["activity_id"], *a.get("resource_ids", [])}
    }


def plan_churn(trace: dict[str, Any]) -> dict[str, int]:
    """Committed revisions plus the previously valid assignments they altered
    (``08_evaluation.md``): per applied coordinator plan change, the activities whose window or
    resources changed, minus those the kept plan already failed a hard check on in the
    planner's latest evaluation before the change (an assignment the disruption had already
    invalidated is repaired, not churned)."""
    applied = _applied_plans(trace)
    altered = valid = 0
    for r in applied:
        changed = {
            c["entity_id"]
            for c in r.get("state_changes", [])
            if c.get("field") in PLAN_CHANGE_FIELDS
        }
        failing = _failing_before(trace, int(r.get("revision_before") or 0)) or set()
        altered += len(changed)
        valid += len(changed - failing)
    return {
        "committed_revisions": len(applied),
        "altered_assignments": altered,
        "previously_valid_altered": valid,
        "total": len(applied) + valid,
    }


def preparation_cost(trace: dict[str, Any]) -> dict[str, Any]:
    final = trace["final_state"]
    clock = _ts(final.get("clock"))
    ids = _coordinator_ids(trace)
    holds = [h for h in final.get("holds", []) if h.get("actor_id") in ids]
    minutes = 0
    for h in holds:
        end = _ts(h.get("terminal_at")) or clock
        minutes += max(0, _minutes(_ts(h.get("created_at")), end) or 0)
    statuses = Counter(h.get("effective_status") for h in holds)
    return {
        "holds": len(holds),
        "hold_minutes": minutes,
        "hold_fee_cents": sum(int(h.get("hold_fee_cents") or 0) for h in holds),
        "reserved_cents_at_end": int((final.get("budget") or {}).get("reserved_cents") or 0),
        "expired_holds": statuses.get("expired", 0),
        "unreleased_holds": statuses.get("active", 0),
        "released_holds": statuses.get("released", 0),
        "committed_holds": statuses.get("committed", 0),
        "fulfilled_holds": statuses.get("fulfilled", 0),
    }


def recovery(
    trace: dict[str, Any], case: dict[str, Any], succeeded: bool | None
) -> dict[str, Any] | None:
    """Recovery delay on a case that requires a recovery; ``None`` on other cases."""
    if not case.get("requires_recovery"):
        return None
    final = trace["final_state"]
    observations = [o["observation"] for o in final.get("observations", [])]
    wanted = set(case.get("actionable_record_ids") or [])
    updates = [
        t
        for o in observations
        if (o.get("source_record_id") in wanted if wanted else o.get("kind") == "notice")
        and (t := _ts(o.get("received_at"))) is not None
    ]
    hard_end = _ts((final.get("goal") or {}).get("hard_end"))
    if not updates:
        return {
            "required": True,
            "update_at": None,
            "recovered": False,
            "delay_minutes": None,
            "horizon_minutes": None,
            "note": "the actionable update never arrived",
        }
    update = min(updates)
    horizon = _minutes(update, hard_end)
    after = [
        t for r in _applied_plans(trace) if (t := _ts(r["executed_at"])) is not None and t >= update
    ]
    first = min(after, default=None)
    recovered = bool(succeeded) and first is not None
    return {
        "required": True,
        "update_at": update.isoformat(),
        "recovered": recovered,
        "delay_minutes": _minutes(update, first) if recovered else horizon,
        "horizon_minutes": horizon,
        "note": None if recovered else "unrecovered: a failure, recorded with the horizon",
    }


def _receipt_by_id(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["receipt_id"]: r for r in trace["receipts"]}


def _grant_tools(final: dict[str, Any]) -> dict[str, set[str]]:
    tools: dict[str, set[str]] = {}
    for g in [*(final.get("grant_history") or []), *(final.get("grants") or [])]:
        grant = g.get("grant") or {}
        tools.setdefault(grant.get("grant_id", ""), set()).update(grant.get("allowed_tools") or [])
    return tools


def pantry_metrics(trace: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any] | None:
    """Quantities, conservation, duplicate or unauthorized credit and receipt integrity."""
    final = trace["final_state"]
    stock = final.get("stock")
    if not stock:
        return None
    receipts = _receipt_by_id(trace)
    grants = _grant_tools(final)
    holds = {h["hold_id"]: h for h in final.get("holds", [])}
    movements = stock.get("movements", [])
    window = (final.get("pantry_parameters") or {}).get("handoff_window") or {}
    tasks = {t["hold_id"]: t for t in stock.get("handoff_tasks", [])}
    shipments = {s["shipment"]["shipment_id"]: s for s in stock.get("expected_shipments", [])}
    problems: list[str] = []
    credits: list[str] = []

    def attested(action_id: str, tool: str, what: str) -> None:
        receipt = receipts.get(action_id)
        if receipt is None or receipt["status"] != "applied" or receipt["tool"] != tool:
            problems.append(f"{what}: no applied {tool} receipt {action_id}")
            return
        if receipt.get("actor_role") == COORDINATOR:
            credits.append(f"{what}: attested by the coordinator")
        if tool not in grants.get(receipt.get("grant_id", ""), set()):
            credits.append(f"{what}: grant {receipt.get('grant_id')} does not allow {tool}")

    def moved(action_id: str, resource: str, kind: str, delta: int, what: str) -> None:
        found = [
            m
            for m in movements
            if m.get("receipt_id") == action_id
            and m["resource_id"] == resource
            and m["kind"] == kind
        ]
        if [m["delta"] for m in found] != [delta]:
            problems.append(f"{what}: {kind} movement of {resource} is not exactly {delta}")

    references = Counter(r["receipt_reference"] for r in stock.get("receipts", []))
    credits += [
        f"receipt reference {ref} credited {n} times" for ref, n in references.items() if n > 1
    ]
    per_hold: Counter[str] = Counter()
    per_shipment: Counter[str] = Counter()
    for r in stock.get("receipts", []):
        what = f"stock receipt {r['stock_receipt_id']}"
        attested(r["receipt_id"], "record_stock_receipt", what)
        if not r.get("source_observation_id"):
            problems.append(f"{what}: no source observation")
        moved(r["receipt_id"], r["resource_id"], "receipt", int(r["quantity"]), what)
        at = _ts(r.get("at"))
        if r["kind"] == "internal_handoff":
            hold = holds.get(r.get("source_hold_id") or "")
            if (
                hold is None
                or hold["resource_id"] != r.get("source_resource_id")
                or hold.get("destination_resource_id") != r["resource_id"]
            ):
                problems.append(f"{what}: does not match a stock-transfer hold of its source")
            else:
                per_hold[hold["hold_id"]] += int(r["quantity"])
            moved(
                r["receipt_id"],
                r.get("source_resource_id") or "",
                "transfer_out",
                -int(r["quantity"]),
                what,
            )
            start, end = _ts(window.get("start")), _ts(window.get("end"))
            if at is None or (start and at < start) or (end and at > end):
                problems.append(f"{what}: outside the handoff window")
            task = tasks.get(r.get("source_hold_id") or "")
            if task is not None and at is not None and at >= (_ts(task["cutoff"]) or at):
                problems.append(f"{what}: at or after its task's cutoff")
        else:
            shipment = shipments.get(r.get("shipment_id") or "")
            if shipment is None or shipment["shipment"].get("destination") not in (
                None,
                r["resource_id"],
            ):
                problems.append(
                    f"{what}: does not match an expected shipment to {r['resource_id']}"
                )
            else:
                per_shipment[shipment["shipment"]["shipment_id"]] += int(r["quantity"])
    for hold_id, quantity in per_hold.items():
        if quantity > int(holds[hold_id]["quantity"]):
            credits.append(
                f"hold {hold_id}: {quantity} received for a {holds[hold_id]['quantity']}-unit hold"
            )
    for shipment_id, quantity in per_shipment.items():
        expected = int(shipments[shipment_id]["shipment"].get("quantity") or 0)
        if quantity > expected:
            credits.append(f"shipment {shipment_id}: {quantity} received of {expected}")
    service = {s["target_id"]: s for s in stock.get("service", [])}
    dist_refs = Counter(d["distribution_reference"] for d in stock.get("distributions", []))
    credits += [
        f"distribution reference {ref} credited {n} times" for ref, n in dist_refs.items() if n > 1
    ]
    for d in stock.get("distributions", []):
        what = f"distribution {d['distribution_id']}"
        attested(d["receipt_id"], "record_distribution", what)
        moved(d["receipt_id"], d["resource_id"], "distribution", -int(d["quantity"]), what)
        target = service.get(d["service_target_id"])
        deadline = _ts(target["deadline"]) if target else None
        at = _ts(d.get("at"))
        if target is None or (
            deadline is not None and at is not None and d["on_time"] != (at <= deadline)
        ):
            problems.append(f"{what}: on-time flag disagrees with its target's deadline")
    # Provenance of verification: every status-tool observation links to a successful check
    # (whoever made it), and every verify decision that reports a success cites one.
    checks = [
        t
        for t in trace["tool_calls"]
        if t["tool"] == "query_status" and t["envelope_status"] == "succeeded"
    ]
    calls = {t["call_id"]: t for t in trace["tool_calls"]}
    for d in trace["decisions"]:
        if d["kind"] != "verify" or (d.get("details") or {}).get("outcome") != "succeeded":
            continue
        cited = [calls[r] for r in d.get("tool_call_refs") or [] if r in calls]
        if not any(
            c["tool"] == "query_status" and c["envelope_status"] == "succeeded" for c in cited
        ):
            problems.append(f"verify decision {d['decision_id']}: cites no successful status check")
    for record in final.get("observations", []):
        obs = record["observation"]
        if record.get("channel") != "status_tool":
            continue
        linked = any(
            (t.get("request") or {}).get("arguments", {}).get("entity_id") == obs.get("entity_id")
            and t.get("completed_at") == obs.get("received_at")
            for t in checks
        )
        if not linked:
            problems.append(
                f"status observation {obs['observation_id']}: no successful check links to it"
            )
    targets = []
    for s in outcome.get("service") or []:
        view = service.get(s["target_id"], {})
        targets.append(
            {
                "target_id": s["target_id"],
                "original_target": s["original_quantity"],
                "current_target": view.get("target_quantity"),
                "on_time": s["on_time_quantity"],
                "late": s["late_quantity"],
                "distributed": s["distributed_quantity"],
                "service_deficit": max(0, s["original_quantity"] - s["on_time_quantity"]),
                "supply_shortfall": s["supply_gap_quantity"],
                "attained": s["attained"],
            }
        )
    pools = [
        {
            "resource_id": b["resource_id"],
            "opening": b["opening_quantity"],
            "expected": b["expected_quantity"],
            "reserved_at_end": b["reserved_quantity"],
            "received": b["received_quantity"],
            "transferred_out": b["transferred_out_quantity"],
            "distributed": b["distributed_quantity"],
            "on_hand_at_end": b["on_hand_quantity"],
            "conserved": b["conserved"]
            and b["on_hand_quantity"]
            == b["opening_quantity"]
            + b["received_quantity"]
            - b["transferred_out_quantity"]
            - b["distributed_quantity"],
        }
        for b in stock.get("balances", [])
    ]
    return {
        "targets": targets,
        "pools": pools,
        "conservation_failures": sum(1 for p in pools if not p["conserved"]),
        "duplicate_or_unauthorized_credits": len(credits),
        "credit_findings": credits,
        "duplicate_attempts_blocked": int(outcome.get("duplicate_records_rejected") or 0),
        "unnecessary_reservations": int(outcome.get("unnecessary_reservations") or 0),
        "receipt_integrity_ok": not problems,
        "receipt_integrity_problems": problems,
        "staff_confirmations": int(outcome.get("staff_confirmations") or 0),
    }


# ---------------------------------------------------------------------------------- extraction


def _readings(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The first structured reading each observation received, as recorded: a rule parser's
    ``interpretation`` or a live reading in ``interpretations`` (P2, P3: a full reading names
    its ``observation_id``; the change spec of a weighed claim names it in ``evidence_refs``).
    P1 records none."""
    out: dict[str, dict[str, Any]] = {}
    for d in trace["decisions"]:
        details = d.get("details") or {}
        items = list(details.get("interpretations") or [])
        if isinstance(details.get("interpretation"), dict):
            items.append(details["interpretation"])
        for item in items:
            if not isinstance(item, dict):
                continue
            refs = [item["observation_id"]] if item.get("observation_id") else []
            refs += [r for r in item.get("evidence_refs") or [] if isinstance(r, str)]
            for ref in refs[:1]:
                out.setdefault(ref, item)
    return out


def _rule_readings(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """P0's readings, by replaying its frozen deterministic parser over the episode's
    observations in order (P0 records a reading only for the notices it does not weigh; the
    parser is deterministic, so the replay is what it read). Event profiles only: the pantry
    baseline reads no notices."""
    from plan_b.domain.models import EventStateView
    from plan_b.evaluation.policies.parser import event_local_date, interpret_observation

    try:
        view = EventStateView.model_validate(trace["final_state"])
    except ValueError:
        return {}
    if view.stock is not None:
        return {}
    day = event_local_date(view.goal, view.timezone)
    handled: list[Any] = []
    out: dict[str, dict[str, Any]] = {}
    for record in view.observations:
        interp = interpret_observation(
            record,
            resources=view.resources,
            event_date=day,
            timezone=view.timezone,
            goal=view.goal,
            event_id=view.event_id,
            handled=tuple(handled),
        )
        handled.append(interp)
        out[interp.observation_id] = interp.model_dump(mode="json")
    return out


def _normalized(reading: dict[str, Any]) -> dict[str, Any]:
    spec: dict[str, Any] = reading.get("change_spec") or {}
    claims: dict[str, Any] = reading.get("claims") or {}
    spec = spec if isinstance(spec, dict) else {}
    claims = claims if isinstance(claims, dict) else {}
    return {
        "change": spec.get("change_kind") or reading.get("change_kind"),
        "subject": reading.get("subject_resource_id")
        or reading.get("subject_id")
        or spec.get("subject_id"),
        "event": reading.get("event_id") or spec.get("event_id"),
        "time": reading.get("claimed_eta") or claims.get("claimed_eta"),
        "booking": claims.get("order_ref") or reading.get("order_ref"),
        # a live reading's standing (P0's evidence_status is the claim's verification, not
        # its reading; P0 abstains with change_kind "unresolved")
        "standing": reading.get("standing"),
        "failure": reading.get("failure"),
    }


def extraction_labels(
    trace: dict[str, Any], case: dict[str, Any], policy: str | None = None
) -> list[dict[str, Any]] | None:
    """One label per annotated message: ``correct``, ``incorrect``, ``abstained``,
    ``malformed`` (the model's reading did not validate), ``rejected`` (the server refused the
    reading's entity), or ``not_recorded`` (no structured reading of that message exists, as
    for P1, a provider error, or a message never read). A reading is compared on the claimed
    change, resource, event, effective time and booking it states; a field it leaves out is not
    a mismatch (the free-text unknown fields are not compared)."""
    annotations = case.get("annotations") or []
    if not annotations:
        return None
    by_record = {
        o["observation"].get("source_record_id"): o["observation"]["observation_id"]
        for o in trace["final_state"].get("observations", [])
    }
    readings = _readings(trace)
    if policy == "P0":
        readings = _rule_readings(trace) | readings
    labels = []
    for a in annotations:
        oid = by_record.get(a["source_record_id"])
        reading = readings.get(oid or "")
        entry: dict[str, Any] = {"source_record_id": a["source_record_id"], "observation_id": oid}
        if reading is None:
            labels.append(entry | {"label": "not_recorded", "mismatched": []})
            continue
        r = _normalized(reading)
        mismatched: list[str] = []
        if r["failure"] in ("provider_error", "missing"):
            labels.append(entry | {"label": "not_recorded", "mismatched": []})
            continue
        if r["failure"] == "malformed_output":
            label = "malformed"
        elif r["failure"] == "unknown_entity":
            label = "rejected"
        elif r["change"] in (None, "unresolved") or r["standing"] == "unresolved":
            label = "correct" if a["claimed_change"] == "no_change" else "abstained"
        else:
            if r["change"] != a["claimed_change"]:
                mismatched.append("claimed_change")
            if a.get("resource_id") and r["subject"] != a["resource_id"]:
                mismatched.append("resource_id")
            if a.get("event_id") and r["event"] and r["event"] != a["event_id"]:
                mismatched.append("event_id")
            if (
                a.get("effective_time")
                and r["time"] is not None
                and _ts(r["time"]) != _ts(a["effective_time"])
            ):
                mismatched.append("effective_time")
            if (
                a.get("booking_ref")
                and r["booking"]
                and str(r["booking"]).upper() != str(a["booking_ref"]).upper()
            ):
                mismatched.append("booking_ref")
            label = "incorrect" if mismatched else "correct"
        labels.append(entry | {"label": label, "mismatched": mismatched})
    return labels


# ---------------------------------------------------------------------------------- one episode


def _decided_by(decision: dict[str, Any]) -> str:
    """Who chose a decision: the model, the server (the shared attention rule's narration) or
    the deterministic policy itself."""
    return str(decision["details"].get("chosen_by") or "policy")


def class_success(
    case: dict[str, Any],
    outcome: dict[str, Any],
    trace: dict[str, Any],
    pantry: dict[str, Any] | None,
) -> tuple[bool, list[str], str | None]:
    """Whether the episode met its outcome class, the reasons it did not, and on the
    infeasible and partial classes who chose the decision that reports it (``_decided_by``)."""
    klass = case["outcome_class"]
    goal = bool(outcome.get("goal_complete"))
    violations = len(outcome.get("violations") or [])
    explained = [d for d in trace["decisions"] if d["kind"] == "infeasible" and names_blocking(d)]
    why: list[str] = []
    if klass == "goal":
        if not goal:
            why.append("goal not complete")
        return goal, why, None
    if violations:
        why.append(f"{violations} executed violation(s)")
    if klass == "infeasible":
        if goal:
            why.append("reported the goal complete")
        if not explained:
            why.append("no infeasibility decision names a blocking constraint")
        return not why, why, _decided_by(explained[0]) if explained else None
    targets = (pantry or {}).get("targets", [])
    if (pantry or {}).get("conservation_failures"):
        why.append("stock not conserved")
    wanted = case.get("target_quantity")
    for t in targets:
        if t["current_target"] is not None and t["current_target"] != t["original_target"]:
            why.append(f"{t['target_id']}: target changed from {t['original_target']}")
        if wanted is not None and t["original_target"] != wanted:
            why.append(f"{t['target_id']}: original target is not {wanted}")
    if klass == "target":
        if not goal or not targets or not all(t["attained"] for t in targets):
            why.append("original target not met by the deadline")
        return not why, why, None
    achievable = case.get("achievable_on_time")
    on_time = sum(t["on_time"] for t in targets)
    if achievable is None:
        why.append("the evaluator data states no achievable quantity")
    elif on_time != achievable:
        why.append("on-time fulfillment differs from the achievable quantity")
    # The accurate deficit: an infeasible decision with blocking constraints whose structured
    # shortfall for each short target equals that target's final deficit.
    short = [t for t in targets if t["service_deficit"] > 0]
    reported = [
        d
        for d in explained
        if short
        and all(
            reported_shortfalls(d).get(t["target_id"], reported_shortfalls(d).get(None))
            == t["service_deficit"]
            for t in short
        )
    ]
    if not reported:
        why.append(
            "no infeasibility decision reports the final deficit with its blocking constraints"
        )
    if goal:
        why.append("reported the goal complete")
    return not why, why, _decided_by(reported[0]) if reported else None


def episode_metrics(entry: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    plan, record, trace = entry["plan"], entry["record"], entry["trace"]
    klass = case.get("outcome_class")
    base: dict[str, Any] = {
        "key": plan["key"],
        "case_ref": plan["case_ref"],
        "case_id": case.get("case_id", plan["case_ref"]),
        "policy": plan["policy"],
        "seed": plan["seed"],
        "trial": plan["trial"],
        "position": plan["position"],
        "outcome_class": klass,
        "negative_control": bool(case.get("negative_control")),
        "status": "missing" if record is None else record["status"],
        "success": None,
        "failure_reasons": [],
    }
    if record is None:
        return base
    if record["status"] == "aborted":
        # The harness stopped its model calls (the cumulative spend cap or the endpoint
        # configuration): not a policy outcome, listed apart and rerun by a resume.
        return base | {"policy_id": record.get("policy_id")}
    problems = list(entry.get("integrity") or [])
    if problems:
        base["status"] = "integrity_failed"
    base |= {
        "policy_id": record.get("policy_id"),
        "wall_seconds": record.get("wall_seconds"),
        "computation": {
            "model_calls": (record.get("model") or {}).get("calls", 0),
            "model_retries": (record.get("model") or {}).get("retries", 0),
            "model_failed_calls": (record.get("model") or {}).get("failed", 0),
            "prompt_tokens": (record.get("model") or {}).get("prompt_tokens", 0),
            "completion_tokens": (record.get("model") or {}).get("completion_tokens", 0),
            "reasoning_tokens": (record.get("model") or {}).get("reasoning_tokens", 0),
            "latency_ms": (record.get("model") or {}).get("latency_ms", 0),
            "cost_usd": (record.get("model") or {}).get("cost_usd", 0.0),
            "tool_calls": (record.get("tool_calls") or {}).get("total"),
            "wall_seconds": record.get("wall_seconds"),
        },
        "trace_verify": (record.get("trace") or {}).get("verify"),
        "caps_reached": (record.get("episode_caps") or {}).get("reached", []),
    }
    if problems:
        return base | {"success": False, "failure_reasons": ["integrity_failed", *problems]}
    if record["status"] in FAILED_STATUSES or trace is None or record.get("outcome") is None:
        # Nothing was measured: the episode's model calls before a timeout are in the spend
        # ledger only, and its partial state in runner_private/failed/.
        reasons = [e.get("message", e.get("kind", "")) for e in record.get("errors") or []]
        return base | {
            "success": False,
            "failure_reasons": [record["status"], *reasons],
            "computation": None,
        }
    outcome = record["outcome"]
    pantry = pantry_metrics(trace, outcome) if case.get("suite") == "pantry" else None
    success, why, decided_by = class_success(case, outcome, trace, pantry)
    churn = plan_churn(trace)
    applied = _applied_plans(trace)
    unnecessary = None
    if case.get("negative_control"):
        unnecessary = {
            "committed_changes": len(applied),
            "altered_assignments": churn["altered_assignments"],
            "committed_cents": sum(int(r.get("committed_delta_cents") or 0) for r in applied),
        }
    prep = preparation_cost(trace)
    return base | {
        "success": success,
        "failure_reasons": why,
        "decided_by": decided_by,
        "goal_complete": bool(outcome.get("goal_complete")),
        "infeasibility_reported": bool(outcome.get("infeasibility_reported")),
        "invalid_attempts": invalid_attempts(trace),
        "executed_violations": len(outcome.get("violations") or []),
        "violations": list(outcome.get("violations") or []),
        "unnecessary_committed_changes": unnecessary,
        "plan_churn": churn,
        "verification": verification_effort(trace),
        "recovery": recovery(trace, case, success),
        "preparation": prep,
        # Committed event money already includes every hold fee (``budget_view``); the fees
        # are reported as its component in preparation cost, never added again.
        "modeled_cost_cents": int(outcome.get("committed_cents") or 0),
        "committed_cents": int(outcome.get("committed_cents") or 0),
        "pantry": pantry,
        "extraction": extraction_labels(trace, case, plan["policy"]),
    }


# ---------------------------------------------------------------------------------- aggregates


def _share(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "k": sum(1 for r in rows if r["success"]),
        "n": len(rows),
        "cases": sorted({r["case_id"] for r in rows}),
    }


def _sum(rows: Iterable[dict[str, Any]], *path: str) -> int | float:
    total: int | float = 0
    for r in rows:
        value: Any = r
        for p in path:
            value = value.get(p) if isinstance(value, dict) else None
        if isinstance(value, int | float) and not isinstance(value, bool):
            total += value
    return total


def policy_aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One policy's aggregates. The outcome-class shares count every recorded episode (a
    timeout, crash or failed trace is a failure); the other aggregates are over the scored
    episodes (``scored``; ``incomplete`` says how many were not), and computation over the
    episodes it was measured on."""
    recorded = [r for r in rows if r["status"] not in UNSCORED_STATUSES]
    scored = [r for r in recorded if r["status"] not in FAILED_STATUSES and "plan_churn" in r]
    by_class = {k: [r for r in recorded if r["outcome_class"] == k] for k in CLASS_METRIC}
    negatives = [r for r in scored if r["negative_control"]]
    recoveries = [r["recovery"] for r in scored if r.get("recovery")]
    recoveries += [
        {"recovered": False, "delay_minutes": None, "horizon_minutes": None}
        for r in recorded
        if r["status"] in FAILED_STATUSES and r.get("requires_recovery")
    ]
    delays = [
        x["delay_minutes"] for x in recoveries if x["recovered"] and x["delay_minutes"] is not None
    ]
    # An unrecovered episode enters at its horizon (a lower bound: right-censored), so a
    # policy that rarely recovers cannot look as fast as one that always does; one that was not
    # measured (timed out, crashed, its trace failed) enters as unbounded.
    censored = delays + [
        math.inf if x.get("horizon_minutes") is None else x["horizon_minutes"]
        for x in recoveries
        if not x["recovered"]
    ]
    median = statistics.median(censored) if censored else None
    extraction = Counter(label["label"] for r in scored for label in (r.get("extraction") or []))
    pantry_rows = [r["pantry"] for r in scored if r.get("pantry")]
    measured = [r for r in recorded if r.get("computation") is not None]
    return {
        "planned": len(rows),
        "recorded": len(recorded),
        "missing": sum(1 for r in rows if r["status"] == "missing"),
        "aborted": sum(1 for r in rows if r["status"] == "aborted"),
        "scored": len(scored),
        "statuses": dict(sorted(Counter(r["status"] for r in rows).items())),
        "incomplete": sum(1 for r in recorded if r["status"] in FAILED_STATUSES),
        "capped": sum(1 for r in recorded if r["status"] == "capped"),
        **{CLASS_METRIC[k]: _share(v) for k, v in by_class.items() if v},
        "decided_by": dict(
            sorted(
                Counter(
                    str(r["decided_by"]) for r in scored if r["success"] and r.get("decided_by")
                ).items()
            )
        ),
        "invalid_attempts": _sum(scored, "invalid_attempts", "count"),
        "executed_violations": _sum(scored, "executed_violations"),
        "unnecessary_changes": {
            "committed_changes": _sum(
                negatives, "unnecessary_committed_changes", "committed_changes"
            ),
            "episodes_with_change": sum(
                1 for r in negatives if r["unnecessary_committed_changes"]["committed_changes"]
            ),
            "n": len(negatives),
            "cases": sorted({r["case_id"] for r in negatives}),
        },
        "plan_churn": _sum(scored, "plan_churn", "total"),
        "verification": {
            k: _sum(scored, "verification", k)
            for k in (
                "status_checks",
                "distinct_sources",
                "repeated_checks",
                "failed_checks",
                "simulated_minutes",
            )
        },
        "recovery": {
            "required": len(recoveries),
            "recovered": sum(1 for x in recoveries if x["recovered"]),
            "unrecovered": sum(1 for x in recoveries if not x["recovered"]),
            # None when unbounded: more than half (or the middle) were not measured
            "median_minutes": None if median is None or math.isinf(median) else median,
            "median_unbounded": median is not None and math.isinf(median),
            "median_is_lower_bound": any(not x["recovered"] for x in recoveries),
            "unrecovered_unmeasured": sum(
                1 for x in recoveries if not x["recovered"] and x.get("horizon_minutes") is None
            ),
            "median_recovered_minutes": statistics.median(delays) if delays else None,
            "min_minutes": min(delays) if delays else None,
            "max_minutes": max(delays) if delays else None,
            "unrecovered_horizons": sorted(
                x["horizon_minutes"]
                for x in recoveries
                if not x["recovered"] and x.get("horizon_minutes") is not None
            ),
        },
        "preparation": {
            k: _sum(scored, "preparation", k)
            for k in (
                "holds",
                "hold_minutes",
                "hold_fee_cents",
                "expired_holds",
                "unreleased_holds",
            )
        },
        "modeled_cost_cents": _sum(scored, "modeled_cost_cents"),
        "committed_cents": _sum(scored, "committed_cents"),
        "computation_measured": len(measured),
        "computation": {
            k: _sum(measured, "computation", k)
            for k in (
                "model_calls",
                "model_retries",
                "model_failed_calls",
                "prompt_tokens",
                "completion_tokens",
                "reasoning_tokens",
                "latency_ms",
                "cost_usd",
                "tool_calls",
                "wall_seconds",
            )
        },
        "extraction": dict(sorted(extraction.items())),
        "pantry": {
            "kits_on_time": sum(t["on_time"] for p in pantry_rows for t in p["targets"]),
            "original_target": sum(t["original_target"] for p in pantry_rows for t in p["targets"]),
            "service_deficit": sum(t["service_deficit"] for p in pantry_rows for t in p["targets"]),
            "conservation_failures": sum(p["conservation_failures"] for p in pantry_rows),
            "duplicate_or_unauthorized_credits": sum(
                p["duplicate_or_unauthorized_credits"] for p in pantry_rows
            ),
            "duplicate_attempts_blocked": sum(p["duplicate_attempts_blocked"] for p in pantry_rows),
            "receipt_integrity_failures": sum(
                1 for p in pantry_rows if not p["receipt_integrity_ok"]
            ),
            "staff_confirmations": sum(p["staff_confirmations"] for p in pantry_rows),
            "unnecessary_reservations": sum(p["unnecessary_reservations"] for p in pantry_rows),
            "episodes": len(pantry_rows),
        }
        if pantry_rows
        else None,
    }


def suite_metrics(results: dict[str, Any]) -> dict[str, Any]:
    """Per-episode metrics, per-policy aggregates, per-case cells and the missing episodes."""
    plan = results["plan"]
    cases = results["cases"]
    rows = []
    for entry in results["episodes"]:
        ref = entry["plan"]["case_ref"]
        case = cases.get(ref) or {
            "case_ref": ref,
            "case_id": ref,
            "outcome_class": None,
            "suite": plan["suite"],
        }
        row = episode_metrics(entry, case)
        row["requires_recovery"] = bool(case.get("requires_recovery"))
        rows.append(row)
    policies = [p for p in POLICY_ORDER if p in plan["policies"]]
    by_case: dict[str, dict[str, Any]] = {}
    for ref in plan["case_refs"]:
        case = cases.get(ref) or {"case_id": ref}
        cell = {}
        for p in policies:
            sub = [r for r in rows if r["case_ref"] == ref and r["policy"] == p]
            scored = [r for r in sub if "verification" in r]
            negatives = [r for r in scored if r.get("unnecessary_committed_changes")]
            cell[p] = {
                "success": sum(1 for r in sub if r["success"]),
                "n": sum(1 for r in sub if r["status"] not in UNSCORED_STATUSES),
                "planned": len(sub),
                "status_checks_mean": statistics.fmean(
                    r["verification"]["status_checks"] for r in scored
                )
                if scored
                else None,
                "unnecessary_changes": sum(
                    r["unnecessary_committed_changes"]["committed_changes"] for r in negatives
                )
                if case.get("negative_control")
                else None,
            }
        by_case[ref] = {
            "case_id": case.get("case_id", ref),
            "outcome_class": case.get("outcome_class"),
            "negative_control": bool(case.get("negative_control")),
            "policies": cell,
        }
    return {
        "version": METRICS_VERSION,
        "suite": plan["suite"],
        "heldout": plan["heldout"],
        "policies": policies,
        "seeds": plan["seeds"],
        "episodes": rows,
        "by_policy": {p: policy_aggregate([r for r in rows if r["policy"] == p]) for p in policies},
        "by_case": by_case,
        "missing": [r["key"] for r in rows if r["status"] == "missing"],
        "aborted": [r["key"] for r in rows if r["status"] == "aborted"],
    }
