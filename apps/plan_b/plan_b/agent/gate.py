"""G-LLM gate: a live interpretation, a tool invocation and a continued turn, on dev01.

``uv run python -m plan_b.agent.gate --out <file>`` loads a fresh in-process dev01 episode into
a temporary SQLite database (the construction ``tests/conftest.py`` ``Sandbox`` uses), hosts one
``LivePolicy`` in a ``PolicyHost`` and runs it once through the real executor. The gate passes
only when all three hold:

1. **interpretation**: a model call for the notice returned strict structured output that
   validated as a planning ``change_spec`` and resolved against public state without failure;
2. **tool invocation**: an option the model chose ran as a tool call through the executor
   (query, hold, apply or release) and returned an envelope;
3. **continued turn**: a later model call carried that tool call's result
   (``consumed_tool_call_ids``) and returned a valid choice.

A plain chat reply, a stubbed success or a failed call does not pass. The JSON record holds the
model identity as returned, the configuration without secrets, latencies, usage, cost, every
tool call with its result status, and the verdict with reasons. The key is read only by the
provider, per call; this module never reads it. The spend guard applies the configured per-run
and cumulative caps, and the ledger records every call.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from plan_b.agent.config import ModelConfig, ModelConfigError, load_model_config
from plan_b.agent.orchestrator import POLICY_ID, LivePolicy
from plan_b.agent.prompts import load_prompt
from plan_b.agent.provider import (
    DEFAULT_TIMEOUT_S,
    PROVIDER_VERSION,
    OpenAICompatibleProvider,
    SpendGuard,
    SpendLedger,
)
from plan_b.domain.models import PolicyDecision, ToolCallRecord
from plan_b.scenarios.policy_host import PolicyHost
from plan_b.scenarios.runner import episode_history
from plan_b.store.database import Database
from plan_b.store.episodes import create_episode

GATE_VERSION = "plan_b.gate/1.0.0"
GATE_CASE = "dev01"
NOTICE_ID = "obs_notice_01"
GATE_MAX_MODEL_CALLS = 6
GATE_MAX_TOOL_CALLS = 16
TOOL_ACTIONS = ("query_status", "hold_resource", "apply_plan", "release_hold")


def run_gate(
    config: ModelConfig,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    work_dir: Path | None = None,
    opener: Any = None,
) -> dict[str, Any]:
    """Run the gate once and return its record. ``opener`` replaces the HTTP opener (tests
    only; a gate run without it is live)."""
    started = _wall()
    ledger = SpendLedger(config.ledger_path)
    before = _ledger_total(ledger)
    record: dict[str, Any] = {
        "gate": "G-LLM",
        "gate_version": GATE_VERSION,
        "policy_id": POLICY_ID,
        "provider_version": PROVIDER_VERSION,
        "live": opener is None,
        "started_at": started,
        "configuration": config.public()
        | {
            "timeout_s": timeout_s,
            "max_model_calls": GATE_MAX_MODEL_CALLS,
            "max_tool_calls": GATE_MAX_TOOL_CALLS,
            "prompts": {
                p.prompt_id: p.sha256
                for p in (load_prompt("interpret.v1"), load_prompt("choose_action.v1"))
            },
        },
        "sandbox": {
            "case_ref": GATE_CASE,
            "database": "temporary in-process SQLite, deleted after the run",
        },
    }
    with tempfile.TemporaryDirectory(prefix="plan_b_gate_", dir=work_dir) as tmp:
        db = Database(Path(tmp) / "gate.sqlite3")
        with db.write() as conn:
            episode_id = create_episode(conn, case_ref=GATE_CASE)
        guard = SpendGuard(
            ledger,
            max_run_usd=config.max_run_cost_usd,
            max_total_usd=config.max_total_cost_usd,
            run_id=f"gate-{started}",
        )
        provider = OpenAICompatibleProvider(config, guard, timeout_s=timeout_s)
        if opener is not None:
            provider._opener = opener
        policy = LivePolicy(
            provider, max_model_calls=GATE_MAX_MODEL_CALLS, max_tool_calls=GATE_MAX_TOOL_CALLS
        )
        host = PolicyHost(db, lambda: policy)
        error: dict[str, str] | None = None
        try:
            result = host.run(episode_id, max_tool_calls=GATE_MAX_TOOL_CALLS)
            record["run"] = {
                "status": result.status,
                "tool_calls": result.tool_calls,
                "note": result.note,
            }
        except Exception as exc:  # noqa: BLE001 - recorded as a gate failure, never a pass
            error = {"type": type(exc).__name__, "message": str(exc)[:300]}
        history = episode_history(db, episode_id)
    record["error"] = error
    record.update(_evidence(history.decisions, history.tool_calls, policy))
    record["ledger"] = {
        "path": config.public()["ledger"],
        "total_cost_usd_before": before,
        "total_cost_usd_after": _ledger_total(ledger),
        "gate_run_cost_usd": round(guard.run_spent_usd, 8),
    }
    reasons = list(record.pop("_reasons"))
    if error is not None:
        reasons.insert(0, f"the gate run raised {error['type']}: {error['message']}")
    record["verdict"] = "pass" if not reasons else "fail"
    record["reasons"] = reasons
    record["finished_at"] = _wall()
    return record


def _evidence(
    decisions: tuple[PolicyDecision, ...],
    tool_calls: tuple[ToolCallRecord, ...],
    policy: LivePolicy,
) -> dict[str, Any]:
    calls = [c for d in decisions for c in d.details.get("model", {}).get("calls", [])]
    reasons: list[str] = []
    # 1. interpretation
    interpret_ok = [c for c in calls if c["purpose"] == "interpret" and c["outcome"] == "ok"]
    reading = next(
        (
            i
            for d in decisions
            for i in d.details.get("interpretations", [])
            if NOTICE_ID in i.get("evidence_refs", [])
        ),
        None,
    )
    interp_check = {
        "model_call_ids": [c["call_id"] for c in interpret_ok],
        "change_spec": reading,
        "failure": next(
            (
                d.details.get("failure")
                for d in decisions
                if d.kind == "unresolved" and NOTICE_ID in d.observation_refs
            ),
            None,
        ),
    }
    if not interpret_ok:
        failed = [c for c in calls if c["purpose"] == "interpret"]
        reasons.append(
            "no interpretation call succeeded"
            + (f" ({failed[-1]['outcome']}: {failed[-1]['error']})" if failed else "")
        )
    elif reading is None or interp_check["failure"] is not None:
        reasons.append(f"the interpretation of {NOTICE_ID} did not resolve: {interp_check}")
    else:
        interp_check["expected_reading"] = (
            reading.get("subject_id") == "projector" and reading.get("change_kind") == "delay"
        )
    # 2. tool invocation chosen by the model
    by_id = {t.call_id: t for t in tool_calls}
    chosen = [
        (d, ref)
        for d in decisions
        if d.details.get("chosen_by") == "model"
        and d.details.get("choice", {}).get("option_id", "").split(":")[0]
        in ("query", "hold", "apply", "release")
        for ref in d.tool_call_refs
        if ref in by_id and by_id[ref].tool in TOOL_ACTIONS
    ]
    tool_check = {
        "invocations": [
            {
                "decision_id": d.decision_id,
                "option_id": d.details["choice"]["option_id"],
                "tool_call_id": ref,
                "tool": by_id[ref].tool,
                "envelope_status": by_id[ref].envelope_status,
                "receipt_id": by_id[ref].receipt_id,
            }
            for d, ref in chosen
        ]
    }
    if not chosen:
        reasons.append("no model-chosen option ran as a tool call through the executor")
    # 3. continued turn consuming that result
    invoked = {ref for _, ref in chosen}
    continued = [
        c
        for c in calls
        if c["purpose"] == "choose_action"
        and c["outcome"] == "ok"
        and invoked & set(c["consumed_tool_call_ids"])
    ]
    turn_check = {
        "model_call_ids": [c["call_id"] for c in continued],
        "consumed_tool_call_ids": sorted(
            {t for c in continued for t in c["consumed_tool_call_ids"]}
        ),
    }
    if chosen and not continued:
        reasons.append("no later model call consumed the tool result")
    totals = {
        "model_calls": len(calls),
        "latency_ms": sum(c["latency_ms"] for c in calls),
        "prompt_tokens": sum(c["prompt_tokens"] or 0 for c in calls),
        "completion_tokens": sum(c["completion_tokens"] or 0 for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 8),
    }
    return {
        "_reasons": reasons,
        "model": {
            "requested": policy.requested_model,
            "returned": sorted({c["model_id"] for c in calls if c["model_id"]}),
        },
        "checks": {
            "interpretation": interp_check,
            "tool_invocation": tool_check,
            "continued_turn": turn_check,
        },
        "calls": calls,
        "totals": totals,
        "episode_usage": policy.usage,
        "tool_calls": [
            {
                "call_id": t.call_id,
                "actor_id": t.actor_id,
                "tool": t.tool,
                "envelope_status": t.envelope_status,
                "error_code": t.error_code,
                "receipt_id": t.receipt_id,
                "revision_before": t.revision_before,
                "revision_after": t.revision_after,
            }
            for t in tool_calls
        ],
        "decisions": [
            {
                "decision_id": d.decision_id,
                "kind": d.kind,
                "chosen_by": d.details.get("chosen_by"),
                "option_id": d.details.get("choice", {}).get("option_id"),
                "summary": d.summary,
                "observation_refs": list(d.observation_refs),
                "candidate_refs": list(d.candidate_refs),
                "receipt_refs": list(d.receipt_refs),
                "tool_call_refs": list(d.tool_call_refs),
                "failure": d.details.get("failure"),
            }
            for d in decisions
        ],
    }


def verdict_line(record: dict[str, Any], out: Path) -> str:
    totals = record.get("totals", {})
    if record["verdict"] == "pass":
        tool = record["checks"]["tool_invocation"]["invocations"][0]
        turn = record["checks"]["continued_turn"]["model_call_ids"][0]
        return (
            f"G-LLM PASS: model {', '.join(record['model']['returned']) or 'unknown'}; "
            f"{totals.get('model_calls', 0)} model calls, {totals.get('cost_usd', 0):.4f} USD; "
            f"{tool['tool']} {tool['envelope_status']} ({tool['tool_call_id']}), consumed by "
            f"{turn}; record {out}"
        )
    return f"G-LLM FAIL: {'; '.join(record['reasons'])[:600]}; record {out}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m plan_b.agent.gate", description=__doc__)
    parser.add_argument("--out", required=True, help="where to write the JSON gate record")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="seconds per call")
    args = parser.parse_args(argv)
    out = Path(args.out)
    try:
        config = load_model_config()
    except ModelConfigError as exc:
        record = {"gate": "G-LLM", "verdict": "fail", "reasons": [f"configuration: {exc}"]}
        _write(out, record)
        print(verdict_line(record, out))
        return 2
    record = run_gate(config, timeout_s=args.timeout)
    _write(out, record)
    print(verdict_line(record, out))
    return 0 if record["verdict"] == "pass" else 1


def _write(out: Path, record: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _ledger_total(ledger: SpendLedger) -> float | None:
    try:
        return ledger.total_usd()
    except (OSError, ValueError):
        return None


def _wall() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    sys.exit(main())
