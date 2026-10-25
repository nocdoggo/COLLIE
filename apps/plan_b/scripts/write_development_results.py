"""Development results: the recorded development runs of P1-P3, with P0's deterministic lines.

Usage (from apps/plan_b; no model call, no network):

    uv run python scripts/write_development_results.py \
        --evidence ../../PEEAI_plan/handoffs/wave_2/evidence [--dir plan_b/evaluation/development]

Reads the run records ``reports/live_p<N>-<policy>_<case>_run.json`` that
``scripts/run_live_cases.py --policy`` wrote and that were copied into the evidence directory,
P0's case lines from ``reports/checks.json`` and its tool-call usage from the public outcome
summaries. ``<dir>/run_notes.json`` holds, for each run label, one hand-written sentence of what
happened, read from that run's trace, and optionally ``superseded_by`` and ``reason`` for a run
replaced after a defect in our code was fixed. Writes into ``<dir>``:

* ``development_runs.json``: one entry per run, with its policy, case, outcome fields, model and
  tool calls, cost, models as requested and returned, trace file, sha256 and verification, the
  model-, server- and host-recorded steps from the run record, and the sentence;
* ``README.md``: one table row per run, in the same order.

These are development runs: one trial each, on development cases, never the held-out
evaluation, and no comparison between policies is drawn from them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from plan_b.domain.timeutil import local_label, parse_ts

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
RESULTS_VERSION = "plan_b.development_results/1.0.0"
CASES = ("dev01", "dev02", "dev04", "pantry_dev01", "skills_dev01")
POLICIES = (
    ("P1", "p1-tool-use", "tool-use/1.0.0"),
    ("P2", "p2-live", "live/1.0.0"),
    ("P3", "p3-verify-all", "verify-all/1.0.0"),
)
LABEL = re.compile(r"^live_(p[123]-[a-z-]+)_\w+_run\.json$")
STEP_KINDS = frozenset(
    {"verify", "prepare", "commit", "ask", "release", "infeasible", "stop", "reconcile"}
)


def _steps(record: dict[str, Any]) -> list[str]:
    """The run's model-chosen decisions and its non-routine server and host decisions, in
    local event time, with their server-composed summaries."""
    out = []
    for d in record.get("decisions", []):
        by = d.get("chosen_by") or ("host" if d.get("kind") == "stop" else "server")
        if by != "model" and d.get("kind") not in STEP_KINDS:
            continue
        at = local_label(parse_ts(d["at"]))
        out.append(f"{at} {d['kind']} ({by}): {d['summary']}")
    return out


def _run_entry(path: Path, notes: dict[str, Any]) -> dict[str, Any]:
    record = json.loads(path.read_text(encoding="utf-8"))
    label = record["label"]
    outcome = record.get("outcome") or {}
    model = record.get("model") or {}
    note = notes.get(label) or {}
    caps = record.get("episode_caps") or {}
    return {
        "label": label,
        "policy": record.get("policy"),
        "policy_id": record.get("policy_id"),
        "case_ref": record["case_ref"],
        "status": "superseded" if note.get("superseded_by") else "recorded",
        "superseded_by": note.get("superseded_by"),
        "superseded_reason": note.get("reason"),
        "goal_complete": outcome.get("goal_complete"),
        "infeasibility_reported": outcome.get("infeasibility_reported"),
        "matches_expectation": record.get("matches_expectation"),
        "outcome_line": record.get("outcome_line"),
        "error": record.get("error"),
        "model_calls": model.get("calls"),
        "model_calls_by_purpose": model.get("by_purpose"),
        "tool_calls": (record.get("tool_calls") or {}).get("total"),
        "caps_reached": caps.get("reached"),
        "cost_usd": record["ledger"]["run_cost_usd"],
        "prompts": sorted(
            {c["prompt_id"] for c in model.get("call_log", []) if c.get("prompt_id")}
        ),
        "model_requested": model.get("requested"),
        "model_returned": model.get("returned"),
        "started_at": record.get("started_at"),
        "run_record": f"reports/{path.name}",
        "trace_file": (record.get("trace") or {}).get("file"),
        "trace_sha256": (record.get("trace") or {}).get("sha256"),
        "trace_verify": (record.get("trace") or {}).get("verify"),
        "steps": _steps(record),
        "what_happened": note.get("what_happened"),
    }


def _p0_entry(evidence: Path, case_ref: str, lines: dict[str, Any]) -> dict[str, Any]:
    public = json.loads(
        (evidence / "reports" / f"{case_ref}_outcome.public.json").read_text(encoding="utf-8")
    )
    line = lines[case_ref]
    caps = public.get("episode_caps") or {}
    return {
        "label": f"p0_{case_ref}",
        "policy": "rules",
        "policy_id": public.get("policy_id"),
        "case_ref": case_ref,
        "status": "deterministic baseline (reports/checks.json)",
        "goal_complete": line["goal_complete"],
        "infeasibility_reported": line["infeasibility_reported"],
        "matches_expectation": line["matches_expectation"],
        "model_calls": 0,
        "tool_calls": caps.get("tool_calls"),
        "cost_usd": 0.0,
        "trace_file": f"traces/{case_ref}_trace.json"
        if (evidence / "traces" / f"{case_ref}_trace.json").exists()
        else None,
    }


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    return str(value).replace("|", "\\|")


def markdown(runs: list[dict[str, Any]], p0: list[dict[str, Any]]) -> str:
    head = [
        "# Development runs (Wave 2)",
        "",
        "Generated by `scripts/write_development_results.py` from the run records in",
        "`PEEAI_plan/handoffs/wave_2/evidence/` (paths below are relative to that directory).",
        "",
        "These are **development runs** on development cases: one live trial each, under the",
        "development caps (48 tool calls, 8 model calls per episode). They are not the held-out",
        "evaluation, they measure no variance, and **no comparison between policies is drawn",
        "from them**. The model was `anthropic/claude-sonnet-5.5` through OpenRouter. Each",
        "\"What happened\" sentence is read from that run's trace; the model's rationale is not",
        "used as evidence. The prompts each run's model calls used are named after its policy.",
        "",
        "| Policy | Case | goal_complete | matches_expectation | Model calls | Tool calls"
        " | Cost (USD) | Returned model | Trace | What happened |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows = []
    names = {policy_id: name for name, _, policy_id in POLICIES}
    for r in runs:
        policy = f"{names.get(r['policy_id'], '')} `{r['policy_id'] or r['policy']}`".strip()
        policy += f" ({', '.join(r['prompts'])})" if r["prompts"] else ""
        if r["status"] == "superseded":
            policy += f" (superseded by `{r['superseded_by']}`)"
        rows.append(
            f"| {policy} | {r['case_ref']} | {_cell(r['goal_complete'])}"
            f" | {_cell(r['matches_expectation'])} | {_cell(r['model_calls'])}"
            f" | {_cell(r['tool_calls'])} | {r['cost_usd']:.4f} | {_cell(r['model_returned'])}"
            f" | `{_cell(r['trace_file'])}` | {_cell(r['what_happened'])} |"
        )
    superseded = [r for r in runs if r["status"] == "superseded"]
    tail = [""]
    if superseded:
        tail += ["**Superseded runs** are kept as recorded:", ""]
        tail += [
            f"* `{r['label']}` → `{r['superseded_by']}`: {r['superseded_reason']}"
            for r in superseded
        ]
        tail.append("")
    tail += [
        "**P0, for reference** (`rules/1.0.0`, `pantry-rules/1.0.0`): deterministic, recorded",
        "once in `reports/checks.json`; no model call.",
        "",
        "| Case | Policy | goal_complete | matches_expectation | Tool calls |",
        "| --- | --- | --- | --- | --- |",
    ]
    tail += [
        f"| {e['case_ref']} | {e['policy_id']} | {_cell(e['goal_complete'])}"
        f" | {_cell(e['matches_expectation'])} | {_cell(e['tool_calls'])} |"
        for e in p0
    ]
    total = sum(r["cost_usd"] for r in runs)
    tail += [
        "",
        f"Spend over these {len(runs)} runs: {total:.4f} USD (the ledger difference of each run).",
        "",
    ]
    return "\n".join(head + rows + tail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/write_development_results.py")
    parser.add_argument("--evidence", required=True, help="the Wave 2 evidence directory")
    parser.add_argument(
        "--dir", default=str(APP / "plan_b/evaluation/development"), help="results directory"
    )
    args = parser.parse_args(argv)
    evidence = Path(args.evidence).resolve()
    out = Path(args.dir).resolve()
    notes_path = out / "run_notes.json"
    notes = json.loads(notes_path.read_text(encoding="utf-8")) if notes_path.exists() else {}
    order = {tag: i for i, (_, tag, _) in enumerate(POLICIES)}
    found = []
    for path in sorted((evidence / "reports").glob("live_p*_run.json")):
        m = LABEL.match(path.name)
        if m and m.group(1) in order:
            record = json.loads(path.read_text(encoding="utf-8"))
            found.append((order[m.group(1)], record["case_ref"], record["started_at"], path))
    case_order = {c: i for i, c in enumerate(CASES)}
    found.sort(key=lambda f: (f[0], case_order.get(f[1], len(CASES)), f[2]))
    runs = [_run_entry(path, notes) for *_, path in found]
    missing = [label for label in notes if label not in {r["label"] for r in runs}]
    lines = json.loads((evidence / "reports" / "checks.json").read_text(encoding="utf-8"))[
        "case_outcomes"
    ]
    p0 = [_p0_entry(evidence, c, lines) for c in CASES]
    out.mkdir(parents=True, exist_ok=True)
    data = {
        "results": RESULTS_VERSION,
        "kind": "development runs (one trial each; not the held-out evaluation; no comparison)",
        "evidence": str(evidence.relative_to(REPO)) if evidence.is_relative_to(REPO) else None,
        "runs": runs,
        "p0_reference": p0,
        "spend_usd": round(sum(r["cost_usd"] for r in runs), 8),
    }
    (out / "development_runs.json").write_text(
        json.dumps(data, indent=1, sort_keys=False) + "\n", encoding="utf-8"
    )
    (out / "README.md").write_text(markdown(runs, p0), encoding="utf-8")
    without = [r["label"] for r in runs if not r["what_happened"]]
    print(f"{len(runs)} runs written; spend {data['spend_usd']:.4f} USD")
    if without or missing:
        print(f"runs without a note: {without}; notes without a run: {missing}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
