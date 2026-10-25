"""Recorded live runs: development cases under a model-driven coordinator.

Usage (from apps/plan_b; PAID: every run makes real model calls):

    uv run python scripts/run_live_cases.py --out <dir> [--policy POLICY] CASE [CASE ...]

``--policy`` is one of the model-driven choices of ``run_case``: ``tool-use`` (P1,
``tool-use/1.0.0``), ``live`` or its alias ``selective`` (P2, ``live/1.0.0``, the default) or
``verify-all`` (P3, ``verify-all/1.0.0``). Each case runs once through
``run_case(policy=...)`` under the development episode caps, on a fresh episode in its own
temporary SQLite database. For each run, ``<dir>`` receives:

* ``traces/live_<label>_trace.json``: the exported sanitized trace, verified with the same
  checks as ``plan-b verify-trace`` and never edited afterwards;
* ``reports/live_<label>_outcome.public.json``: the public outcome summary (no predicates);
* ``runner_private/live_<label>_outcome.runner.json``: the evaluator-side report with the case's
  predicates and expectation. Never feed it to a policy or the browser;
* ``reports/live_<label>_run.json``: the run record: the outcome line, the model as requested
  and as returned, every model call's purpose, outcome, latency, tokens and cost, the spend
  ledger before and after, the coordinator's tool calls, every decision, the trace's
  verification, and the checks below.

The label is the case ref when ``--policy`` is not given (the Wave 2 recorded runs), else
``<tag>_<case ref>`` with the policy's tag (``p1-tool-use``, ``p2-live``, ``p3-verify-all``), or
``--label`` for a further run of the same case; a label whose files exist is refused, so a
recorded run is never overwritten. A failed run is recorded like any other.

Checks, computed from the persisted records and the trace (never from model text):

* ``useful_tool_calls``: model-chosen queries, holds (handoff requests included), releases and
  applies, with their outcome and the later model calls that consumed their result (P2 and P3
  choose a menu option; P1 names the tool itself);
* ``validated_actions``: the coordinator's applied ``apply_plan`` receipts, each with its stored
  candidate and report, the evaluation's revision and goal version, and whether the candidate was
  feasible and applicable when evaluated;
* ``fresh_state_agreement``: for each applied plan, the coordinator's next state read, and
  whether the public snapshot at that read's revision (and the final state) holds the plan the
  receipt reported;
* ``notice_responses``: for each notice, offer or policy observation, the decisions that cite
  it, with their kind, failure class and interpretation;
* ``failures``: decisions that carry ``details.failure``.

The spend guard enforces the configured per-run and cumulative caps on every call, and the
ledger records every call. The key is read only by the provider, per call; this script never
reads it and writes no local path: paths are relative to the repository root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plan_b.scenarios.policy_host import PolicyChoice

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
RECORD_VERSION = "plan_b.live_run/1.0.0"
ACTION_PREFIXES = ("query", "hold", "handoff", "release", "apply")
# P1 names tools, not menu options: the same actions by tool.
TOOL_ACTIONS = {
    "query_status": "query",
    "hold_resource": "hold",
    "release_hold": "release",
    "apply_plan": "apply",
}
NOTICE_KINDS = ("notice", "resource_offer", "policy")
POLICY_TAGS = {"tool-use": "p1-tool-use", "live": "p2-live", "verify-all": "p3-verify-all"}


def outcome_line(case_ref: str, report: Any) -> str:
    """The ``plan-b run-case`` result line."""
    return (
        f"{case_ref}: goal_complete={report.goal_complete} "
        f"infeasibility_reported={report.infeasibility_reported} "
        f"applied_plans={report.applied_plans} committed={report.committed_cents} "
        f"violations={len(report.violations)} matches_expectation={report.matches_expectation}"
    )


def _wall() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ledger_state(path: Path) -> dict[str, Any]:
    """The spend ledger's total and call count, read without the key and without a lock (the
    run is over when this is read)."""
    if not path.exists():
        return {"total_cost_usd": 0.0, "calls": 0, "entries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("calls", [])
    return {
        "total_cost_usd": data.get("total_cost_usd", 0.0),
        "calls": len(entries),
        "entries": entries,
    }


def _model_calls(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every model call, from the decision each one is attributed to (once each)."""
    calls: list[dict[str, Any]] = []
    for d in decisions:
        model = d["details"].get("model")
        for call in model.get("calls", []) if isinstance(model, dict) else []:
            calls.append(call | {"decision_id": d["decision_id"]})
    return calls


def _choice(decision: dict[str, Any]) -> dict[str, Any]:
    choice = decision["details"].get("choice")
    return choice if isinstance(choice, dict) else {}


def _action(decision: dict[str, Any]) -> str:
    """The model-chosen action of a decision: the menu option (P2, P3) or, for P1, the tool it
    called; empty for a decision without one."""
    option = str(_choice(decision).get("option_id") or "")
    if option:
        return option
    tool = decision["details"].get("tool")
    return tool if isinstance(tool, str) else ""


def _frame_at(frames: list[dict[str, Any]], revision: int) -> dict[str, Any] | None:
    """The last frame whose revision is at most ``revision``."""
    found = None
    for frame in frames:
        if frame["revision"] <= revision:
            found = frame
    return found


def _plan_key(plan: Any) -> Any:
    if not isinstance(plan, dict):
        return None
    return sorted(
        (a["activity_id"], a["start"], a["end"], tuple(sorted(a["resource_ids"])))
        for a in plan.get("assignments", [])
    )


def analyze(trace: dict[str, Any], agent_id: str | None) -> dict[str, Any]:
    """The run's checks, from the exported trace alone (see the module docstring)."""
    decisions: list[dict[str, Any]] = trace["decisions"]
    calls = _model_calls(decisions)
    tool_calls = [t for t in trace["tool_calls"] if t["actor_id"] == agent_id]
    by_call = {t["call_id"]: t for t in tool_calls}
    receipts = {r["receipt_id"]: r for r in trace["receipts"]}
    evaluations: dict[str, Any] = trace.get("evaluations", {})
    candidates: dict[str, tuple[str | None, dict[str, Any], dict[str, Any]]] = {
        c["candidate_id"]: (ev_id, ev, c)
        for ev_id, ev in evaluations.items()
        for c in ev.get("candidates", [])
    }

    useful = []
    for d in decisions:
        option = _action(d)
        head = option.split(":")[0]
        if d["details"].get("chosen_by") != "model" or (
            head not in ACTION_PREFIXES and head not in TOOL_ACTIONS
        ):
            continue
        for ref in d["tool_call_refs"]:
            t = by_call.get(ref)
            if t is None or t["tool"] in ("get_event_state", "evaluate_candidates"):
                continue
            receipt = receipts.get(t["receipt_id"] or "")
            useful.append(
                {
                    "decision_id": d["decision_id"],
                    "option_id": option,
                    "tool_call_id": ref,
                    "tool": t["tool"],
                    "envelope_status": t["envelope_status"],
                    "error_code": t["error_code"],
                    "receipt_id": t["receipt_id"],
                    "receipt_status": receipt["status"] if receipt else None,
                    "consumed_by_model_calls": [
                        c["call_id"] for c in calls if ref in c.get("consumed_tool_call_ids", [])
                    ],
                }
            )

    validated = []
    agreement = []
    final_plan = trace["final_state"].get("plan")
    applies = [
        t
        for t in tool_calls
        if t["tool"] == "apply_plan"
        and receipts.get(t["receipt_id"] or "", {}).get("status") == "applied"
    ]
    for t in applies:
        receipt = receipts[t["receipt_id"]]
        args = t["request"].get("arguments", {})
        ev_id, ev, cand = candidates.get(args.get("candidate_plan_id", ""), (None, {}, {}))
        validated.append(
            {
                "tool_call_id": t["call_id"],
                "receipt_id": receipt["receipt_id"],
                "candidate_plan_id": args.get("candidate_plan_id"),
                "constraint_report_ref": args.get("constraint_report_ref"),
                "report_matches_candidate": cand.get("report_id")
                == args.get("constraint_report_ref"),
                "evaluation_id": ev_id,
                "evaluation_revision": ev.get("revision"),
                "expected_revision": t["request"].get("expected_revision"),
                "goal_version": ev.get("goal_version"),
                "expected_goal_version": t["request"].get("expected_goal_version"),
                "candidate_label": cand.get("label"),
                "constraint_status": cand.get("constraint_status"),
                "applicable_when_evaluated": cand.get("applicable_now"),
                "revision_before": receipt["revision_before"],
                "revision_after": receipt["revision_after"],
                "committed_delta_cents": receipt["committed_delta_cents"],
            }
        )
        applied_plan = (t["envelope"].get("data") or {}).get("plan")
        read = next(
            (
                r
                for r in tool_calls
                if r["seq"] > t["seq"]
                and r["tool"] == "get_event_state"
                and r["envelope_status"] == "succeeded"
            ),
            None,
        )
        frame = _frame_at(trace["frames"], read["revision_after"]) if read else None
        frame_plan = frame["state"].get("plan") if frame else None
        agreement.append(
            {
                "receipt_id": receipt["receipt_id"],
                "next_state_read": read["call_id"] if read else None,
                "read_revision": read["revision_after"] if read else None,
                "read_after_receipt": bool(
                    read and read["revision_after"] >= receipt["revision_after"]
                ),
                "snapshot_plan_receipt": frame_plan.get("applied_receipt_id")
                if frame_plan
                else None,
                "snapshot_matches_receipt": bool(
                    frame_plan
                    and frame_plan.get("applied_receipt_id") == receipt["receipt_id"]
                    and _plan_key(frame_plan) == _plan_key(applied_plan)
                ),
                "final_state_matches_receipt": bool(
                    final_plan
                    and final_plan.get("applied_receipt_id") == receipt["receipt_id"]
                    and _plan_key(final_plan) == _plan_key(applied_plan)
                ),
            }
        )

    notices = []
    for record in trace["final_state"].get("observations", []):
        obs = record["observation"]
        if obs["kind"] not in NOTICE_KINDS:
            continue
        citing = [d for d in decisions if obs["observation_id"] in d["observation_refs"]]
        responses = []
        for d in citing:
            reading = d["details"].get("interpretation")
            responses.append(
                {
                    "decision_id": d["decision_id"],
                    "at": d["at"],
                    "kind": d["kind"],
                    "chosen_by": d["details"].get("chosen_by"),
                    "failure": d["details"].get("failure"),
                    "summary": d["summary"],
                    "interpretation": {
                        "standing": reading.get("standing"),
                        "change_kind": reading["change_spec"].get("change_kind"),
                        "subject_resource_id": reading.get("subject_resource_id"),
                        "claimed_eta": reading.get("claimed_eta"),
                        "hearsay": reading.get("hearsay"),
                        "duplicate_of": reading.get("duplicate_of"),
                        "retracts": reading.get("retracts"),
                        "contains_instructions": reading.get("contains_instructions"),
                        "failure": reading.get("failure"),
                        "server_notes": reading.get("server_notes"),
                        "model_reading": reading["change_spec"].get("interpretation"),
                    }
                    if isinstance(reading, dict)
                    else None,
                }
            )
        notices.append(
            {
                "observation_id": obs["observation_id"],
                "kind": obs["kind"],
                "channel": record["channel"],
                "source_id": obs["source_id"],
                "received_at": obs["received_at"],
                "entity_id": obs["entity_id"],
                "text": obs["text"],
                "responses": responses,
            }
        )

    failures = [
        {
            "decision_id": d["decision_id"],
            "kind": d["kind"],
            "failure": d["details"]["failure"],
            "recorded_by": d["details"].get("recorded_by", "policy"),
            "summary": d["summary"],
        }
        for d in decisions
        if d["details"].get("failure")
    ]
    return {
        "useful_tool_calls": useful,
        "validated_actions": validated,
        "fresh_state_agreement": agreement,
        "notice_responses": notices,
        "failures": failures,
    }


def summarize_model(decisions: list[dict[str, Any]], requested: str) -> dict[str, Any]:
    calls = _model_calls(decisions)

    def total(name: str) -> int:
        return sum(c.get(name) or 0 for c in calls)

    return {
        "requested": requested,
        "returned": sorted({c["model_id"] for c in calls if c.get("model_id")}),
        "calls": len(calls),
        "by_purpose": dict(Counter(c["purpose"] for c in calls)),
        "outcomes": dict(Counter(c["outcome"] for c in calls)),
        "cost_basis": sorted({c["cost_basis"] for c in calls if c.get("cost_basis")}),
        "latency_ms": total("latency_ms"),
        "prompt_tokens": total("prompt_tokens"),
        "completion_tokens": total("completion_tokens"),
        "reasoning_tokens": total("reasoning_tokens"),
        "cost_usd": round(sum(c.get("cost_usd") or 0.0 for c in calls), 8),
        "call_log": [
            {
                k: c.get(k)
                for k in (
                    "call_id",
                    "decision_id",
                    "purpose",
                    "prompt_id",
                    "attempt",
                    "outcome",
                    "error",
                    "http_status",
                    "model_id",
                    "latency_ms",
                    "prompt_tokens",
                    "completion_tokens",
                    "reasoning_tokens",
                    "cost_usd",
                    "cost_basis",
                    "consumed_tool_call_ids",
                )
            }
            for c in calls
        ],
    }


def decision_log(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "decision_id": d["decision_id"],
            "at": d["at"],
            "revision": d["revision"],
            "kind": d["kind"],
            "chosen_by": d["details"].get("chosen_by"),
            "option_id": _choice(d).get("option_id"),
            "tool": d["details"].get("tool"),
            "final_decision": d["details"].get("final_decision"),
            "verify_all": d["details"].get("verify_all"),
            "rationale_untrusted": _choice(d).get("rationale_untrusted"),
            "failure": d["details"].get("failure"),
            "mode_label": (d["details"].get("policy_mode") or {}).get("label"),
            "summary": d["summary"],
            "observation_refs": d["observation_refs"],
            "candidate_refs": d["candidate_refs"],
            "receipt_refs": d["receipt_refs"],
            "tool_call_refs": d["tool_call_refs"],
        }
        for d in decisions
    ]


def public_message(exc: BaseException, tmp: str) -> str:
    """An exception's text for the run record, with local paths as placeholders: an error
    from the ledger or the database names its file."""
    text = str(exc)
    for local, placeholder in ((tmp, "<tmp>"), (str(REPO), "<repo>"), (str(Path.home()), "~")):
        text = text.replace(local, placeholder)
    return text[:300]


def run_one(case_ref: str, label: str, out: Path, policy: PolicyChoice = "live") -> dict[str, Any]:
    from plan_b.agent.config import load_model_config
    from plan_b.evaluation.export_trace import build_trace, verify_trace_bytes, write_trace
    from plan_b.evaluation.scoring import public_summary
    from plan_b.scenarios.policy_host import DEVELOPMENT_CAPS
    from plan_b.scenarios.runner import run_case
    from plan_b.store.database import Database

    config = load_model_config()  # server-side; the key itself is not read here
    caps = DEVELOPMENT_CAPS
    before = _ledger_state(config.ledger_path)
    started, t0 = _wall(), time.monotonic()
    error = None
    with tempfile.TemporaryDirectory(prefix="plan_b_live_") as tmp:
        db = Database(Path(tmp) / "live.sqlite3")
        try:
            result = run_case(db, case_ref, policy=policy, caps=caps, live_config=config)
        except Exception as exc:  # noqa: BLE001 - recorded, never hidden
            error = {"type": type(exc).__name__, "message": public_message(exc, tmp)}
            result = None
        trace = None
        if result is not None:
            trace = build_trace(db, result.episode_id, policy_id=result.report.policy_id)
    after = _ledger_state(config.ledger_path)
    record: dict[str, Any] = {
        "record": RECORD_VERSION,
        "label": label,
        "case_ref": case_ref,
        "policy": policy,
        "started_at": started,
        "finished_at": _wall(),
        "wall_seconds": round(time.monotonic() - t0, 1),
        "configuration": config.public() | {"episode_caps": caps.as_dict()},
        "error": error,
    }
    new_entries = after["entries"][before["calls"] :]
    record["ledger"] = {
        "path": config.public()["ledger"],
        "total_cost_usd_before": before["total_cost_usd"],
        "total_cost_usd_after": after["total_cost_usd"],
        "run_cost_usd": round(after["total_cost_usd"] - before["total_cost_usd"], 8),
        "calls_added": len(new_entries),
        "run_ids": sorted({e.get("run_id") for e in new_entries if e.get("run_id")}),
        "outcomes": dict(Counter(e.get("outcome") for e in new_entries)),
    }
    if result is None or trace is None:
        return record
    report = result.report
    trace_path = write_trace(trace, out / "traces" / f"live_{label}_trace.json")
    data = trace_path.read_bytes()
    problems = verify_trace_bytes(data)
    (out / "reports" / f"live_{label}_outcome.public.json").write_text(
        json.dumps(public_summary(report), indent=2, sort_keys=True) + "\n"
    )
    (out / "runner_private" / f"live_{label}_outcome.runner.json").write_text(
        report.model_dump_json(indent=2) + "\n"
    )
    agent_id = next(
        (t["actor_id"] for t in trace["tool_calls"] if t["actor_role"] == "coordinator_agent"),
        None,
    )
    decisions = trace["decisions"]
    tool_calls = [t for t in trace["tool_calls"] if t["actor_id"] == agent_id]
    record |= {
        "policy_id": report.policy_id,
        "mode_label": report.mode_label,
        "outcome_line": outcome_line(case_ref, report),
        "matches_expectation": report.matches_expectation,
        "outcome": public_summary(report),
        "episode_caps": report.episode_caps.model_dump(mode="json")
        if report.episode_caps
        else None,
        "model": summarize_model(decisions, config.model_id),
        "tool_calls": {
            "total": len(tool_calls),
            "by_tool": dict(Counter(t["tool"] for t in tool_calls)),
            "by_status": dict(Counter(t["envelope_status"] for t in tool_calls)),
            "rejected": [
                {"call_id": t["call_id"], "tool": t["tool"], "error_code": t["error_code"]}
                for t in tool_calls
                if t["envelope_status"] != "succeeded"
            ],
        },
        "decisions": decision_log(decisions),
        "trace": {
            "file": f"traces/{trace_path.name}",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "verify": problems or "intact",
        },
        "checks": analyze(trace, agent_id),
    }
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/run_live_cases.py", description=__doc__)
    parser.add_argument("cases", nargs="+", help="case refs (dev01, dev04, skills_dev01, ...)")
    parser.add_argument("--out", required=True, help="evidence directory (created if missing)")
    parser.add_argument(
        "--policy",
        default=None,
        choices=("tool-use", "live", "selective", "verify-all"),
        help="the model-driven policy (default live; see above)",
    )
    parser.add_argument("--label", default=None, help="file label for a single case's run")
    args = parser.parse_args(argv)
    if args.label and len(args.cases) != 1:
        parser.error("--label names one case's run")
    from plan_b.scenarios.policy_host import canonical_choice

    policy = canonical_choice(args.policy or "live")
    out = Path(args.out).resolve()
    for sub in ("reports", "traces", "runner_private"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    ok = True
    for case_ref in args.cases:
        label = args.label or (
            case_ref if args.policy is None else f"{POLICY_TAGS[policy]}_{case_ref}"
        )
        taken = [
            p
            for p in (
                out / "traces" / f"live_{label}_trace.json",
                out / "reports" / f"live_{label}_run.json",
            )
            if p.exists()
        ]
        if taken:
            print(f"{label}: already recorded ({taken[0].name}); choose another --label")
            ok = False
            continue
        record = run_one(case_ref, label, out, policy)
        (out / "reports" / f"live_{label}_run.json").write_text(
            json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        if record.get("error"):
            print(f"{label}: run raised {record['error']['type']}: {record['error']['message']}")
            ok = False
            continue
        model = record["model"]
        print(record["outcome_line"])
        returned = ", ".join(model["returned"]) or "none returned"
        print(
            f"  model {returned}; {model['calls']} model calls ({model['outcomes']});"
            f" {record['tool_calls']['total']} tool calls;"
            f" {record['ledger']['run_cost_usd']:.4f} USD (ledger);"
            f" trace {record['trace']['verify']}"
        )
        ok = ok and record["trace"]["verify"] == "intact"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
