"""The evaluation report: ``plan-b eval report --results <dir>``.

From one results directory of ``plan-b eval run`` it writes, under ``<dir>/report/``:

* ``metrics.json``: ``metrics.suite_metrics`` (every episode, every policy, every case);
* ``evaluation_results.md``: the tables of ``PEEAI_plan/templates/evaluation_results.md``
  filled from the run (run manifest, the suite's aggregate display, exact counts and
  denominators per policy, the per-case table, the pantry quantity ledger, extraction labels,
  and the missing episodes);
* ``figure.svg``: one figure, per case, of the episodes that met their outcome class next to
  the status checks per episode, for each policy. Plain SVG written here, readable in light
  and dark.

This module only formats what ``metrics.py`` computed: it adds no metric, no composite score
and no significance test. The report is evaluator output, like ``runner_private/``: it names the
evaluator case ids, their outcome classes and negative-control designations and the reasons an
episode missed its class (which can name the evaluator's quantities), never a case's contents,
predicates or messages. Keep it with the evaluator side until the comparison is reported; the
public part of a results directory is ``plan.json``, ``invocations.jsonl`` and ``episodes/``.
"""

from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path
from typing import Any

from plan_b.evaluation.metrics import CLASS_METRIC, suite_metrics
from plan_b.evaluation.run import load_results

REPORT_DIR = "report"
CLASS_LABELS = {
    "goal": "Goal completion",
    "infeasible": "Appropriate infeasibility",
    "target": "Original target met",
    "partial": "Supported partial fulfillment",
}
# Categorical slots 1-4 of the reference palette (validated in this order), light and dark.
SERIES = {
    "P0": ("#2a78d6", "#3987e5"),
    "P1": ("#eb6834", "#d95926"),
    "P2": ("#1baf7a", "#199e70"),
    "P3": ("#eda100", "#c98500"),
}
POLICY_NAMES = {
    "P0": "P0 rules",
    "P1": "P1 tool use",
    "P2": "P2 selective",
    "P3": "P3 verify-all",
}


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value).replace("|", "\\|")


def _share(entry: dict[str, Any] | None) -> str:
    if not entry:
        return "—"
    return f"{entry['k']}/{entry['n']}"


def _table(head: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    if not rows:
        out.append("| " + " | ".join("—" for _ in head) + " |")
    return out


def _last_invocation(results: dict[str, Any]) -> dict[str, Any]:
    return results["invocations"][-1] if results["invocations"] else {}


def _distinct(results: dict[str, Any], *path: str) -> list[Any]:
    """The distinct values of one field over every invocation of the run, in order."""
    seen: list[Any] = []
    for inv in results["invocations"]:
        value: Any = inv
        for p in path:
            value = value.get(p) if isinstance(value, dict) else None
        if value not in seen:
            seen.append(value)
    return seen


def _manifest(results: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    plan = results["plan"]
    inv = _last_invocation(results)
    records = [e["record"] for e in results["episodes"] if e["record"]]
    policy_ids = sorted({r.get("policy_id") for r in records if r.get("policy_id")})
    models = sorted({m for r in records for m in (r.get("model") or {}).get("returned", [])})
    seed_passed = sorted({bool(r.get("seed_passed")) for r in records if r.get("seed") is not None})
    seed_fields = [f for r in records for f in (r.get("model") or {}).get("seed_fields", [])]
    freeze = inv.get("freeze") or {}
    lock = inv.get("heldout_lock") or {}
    cases = results["cases"]
    ids = [cases.get(ref, {}).get("case_id", ref) for ref in plan["case_refs"]]
    statuses = metrics["by_policy"]
    incomplete = sum(p["incomplete"] for p in statuses.values())
    missing = len(metrics["missing"])
    aborted = len(metrics.get("aborted", []))
    seed_sent = sorted(
        {bool(f.get("seed_sent")) for f in seed_fields if isinstance(f, dict) and "seed_sent" in f}
    )
    # Every invocation of a resumed run must have run under one freeze, lock and commit.
    mixed = [
        f"{what} differs between invocations ({', '.join(str(v) for v in values)})"
        for what, values in (
            ("the freeze files_sha256", _distinct(results, "freeze", "files_sha256")),
            ("the held-out lock files_sha256", _distinct(results, "heldout_lock", "files_sha256")),
            ("the code commit", _distinct(results, "git_head")),
        )
        if len(values) > 1
    ]
    caps = plan["episode_caps"]
    model_line = (
        f"scripted provider (dry run: {plan['policy_factory']})"
        if plan["dry_run"]
        else (
            f"requested {(inv.get('model') or {}).get('model_id')} via"
            f" {(inv.get('model') or {}).get('provider')}; returned {', '.join(models) or 'none'}"
            if inv.get("model")
            else "no model-driven policy in this run"
        )
    )
    return [
        "## Run manifest",
        "",
        *(f"- **MIXED RUN: {m}.**" for m in mixed),
        f"- Code commit: {inv.get('git_head') or 'unknown'}"
        f" (apps/plan_b tree clean: {_cell(inv.get('app_tree_clean'))}; measured files"
        f" {plan.get('measured_files_sha256') or '—'})",
        f"- Suite: {'primary campus' if plan['suite'] == 'campus' else 'secondary pantry transfer'}"
        f" ({plan['suite']})",
        "- Scenario-set version and hash: "
        + (
            f"held-out lock files_sha256 {lock.get('files_sha256')}"
            if plan["heldout"]
            else "development cases (not held-out; not a reported result)"
        ),
        f"- Case IDs: {', '.join(ids)}" + ("" if plan["heldout"] else " (development fixtures)"),
        f"- Protocol version: {plan['protocol_version']}",
        f"- Policy identifiers: {', '.join(policy_ids) or '—'} ({', '.join(plan['policies'])})",
        f"- Model identifier and serving configuration: {model_line}",
        f"- Measured code (prompts, parser, planner, adapters, tool registry):"
        f" freeze {('verified' if freeze.get('ok') else 'NOT verified')},"
        f" files_sha256 {freeze.get('files_sha256') or '—'}",
        "- Candidate generation, registry, grants and tools: the same frozen code and fixture for"
        " every policy within a case",
        f"- Tool limits, retries, timeouts: {caps['max_tool_calls']} tool calls and"
        f" {caps['max_model_calls']} model calls per episode ({caps['phase']} caps); episode"
        f" timeout {plan['episode_timeout_s']:.0f} s of wall time; retry rules as frozen",
        f"- Scenario clock and random seeds: seeds {plan['seeds']}; policy-order seed"
        f" {plan['order_seed']}",
        "- Provider seed support: "
        + (
            "seed passed to run_case"
            if seed_passed == [True]
            else "seed NOT passed (run_case took no seed); trials are independent run ids"
            if seed_passed == [False]
            else "mixed or not applicable"
        )
        + (
            "; the provider received it (seed_sent)"
            if seed_sent == [True]
            else "; NOT sent to the provider (the model's endpoints refuse a seed): the trials"
            " are independent runs, not reproducible ones"
            if seed_sent == [False]
            else ""
        ),
        "- Shared exogenous observations and staff responses: each case's frozen private case,"
        " identical for every policy",
        f"- Number of independent cases: {len(plan['case_refs'])}",
        f"- Repeated model runs per case: {len(plan['seeds'])} per model policy; P0 once",
        f"- Failed or incomplete runs and treatment: {incomplete} timed out, crashed or with a"
        " trace that no longer matches its record (failures in the outcome-class shares; the"
        " other aggregates are over scored episodes, whose number each table names);"
        f" {aborted} aborted by the harness (the cumulative spend cap or the endpoint"
        f" configuration: not scored, rerun by a resume); {missing} planned episodes missing"
        " (listed below)",
        "- Run order: shuffled within each case over all four policies from the order seed"
        " (plan.json)"
        + (
            f"; this run covers only {', '.join(plan['policies'])}, so a comparison assembled from"
            " several runs is NOT order-randomized"
            if plan.get("policy_subset")
            else ""
        )
        + f"; run created {plan.get('created_at', '—')}",
        "- Analysis changes after inspecting outcomes: none made by this tool; record any here",
        "",
    ]


def _campus_aggregate(metrics: dict[str, Any]) -> list[str]:
    rows = []
    for p in metrics["policies"]:
        a = metrics["by_policy"][p]
        un = a["unnecessary_changes"]
        rows.append(
            [
                POLICY_NAMES[p],
                _share(a.get("goal_completion")),
                _share(a.get("appropriate_infeasibility")) + _by(a),
                f"{a['invalid_attempts']} / {a['executed_violations']} ({a['scored']} scored)",
                f"{un['committed_changes']} in {un['episodes_with_change']}/{un['n']} episodes"
                if un["n"]
                else "—",
                _recovery(a["recovery"]),
                a["computation"]["tool_calls"],
                f"{a['modeled_cost_cents']} cents",
                _incomplete(a),
            ]
        )
    return [
        "## Primary campus aggregate display",
        "",
        *_table(
            [
                "Policy",
                "Goal completion C01–C07",
                "Appropriate infeasibility C08",
                "Invalid attempts / executed violations",
                "Unnecessary changes C02–C04",
                "Recovery time",
                "Tool calls",
                "Modeled cost",
                "Incomplete runs",
            ],
            rows,
        ),
        "",
        "Completion columns are episodes meeting the case's outcome class over recorded episodes"
        " of that class (a timed-out or crashed episode counts as not met); for infeasibility,"
        " who chose the reporting decision (the model, the server's shared narration, or the"
        " deterministic policy). Unnecessary changes are applied plan changes on the designated"
        " negative controls, whose original plan the evaluator's replay confirmed feasible."
        " Recovery time is simulated minutes from the first actionable update to the first"
        " applied plan change; the median counts an unrecovered episode at its horizon (≥: a"
        " lower bound), and the median among recovered episodes is shown beside it. Modeled cost"
        " is committed event money, hold fees included, separate from computation cost.",
        "",
    ]


def _by(a: dict[str, Any]) -> str:
    by = a.get("decided_by") or {}
    return f" ({', '.join(f'{k} {v}' for k, v in by.items())})" if by else ""


def _recovery(rec: dict[str, Any]) -> str:
    if not rec["required"]:
        return "—"
    bound = "≥" if rec.get("median_is_lower_bound") else ""
    median = (
        "unbounded (the middle episodes were not measured)"
        if rec.get("median_unbounded")
        else f"{bound}{_cell(rec['median_minutes'])} min"
    )
    return (
        f"{rec['recovered']}/{rec['required']} recovered; median {median} (recovered only: median"
        f" {_cell(rec.get('median_recovered_minutes'))}, range {_cell(rec['min_minutes'])}–"
        f"{_cell(rec['max_minutes'])})"
    )


def _incomplete(a: dict[str, Any]) -> str:
    return f"{a['incomplete']} (+{a.get('aborted', 0)} aborted, +{a['missing']} missing)"


def _pantry_aggregate(metrics: dict[str, Any]) -> list[str]:
    rows = []
    for p in metrics["policies"]:
        a = metrics["by_policy"][p]
        pa = a["pantry"] or {}
        v = a["verification"]
        rows.append(
            [
                POLICY_NAMES[p],
                _share(a.get("target_attainment")),
                _share(a.get("supported_partial")) + _by(a),
                f"{pa.get('kits_on_time', '—')} / {pa.get('original_target', '—')}"
                f" ({pa.get('episodes', 0)} scored)",
                pa.get("service_deficit"),
                pa.get("conservation_failures"),
                pa.get("unnecessary_reservations"),
                f"{a['invalid_attempts']} / {a['executed_violations']}",
                f"{v['status_checks']} checks; {a['computation']['tool_calls']} tool calls;"
                f" {a['computation']['cost_usd']:.4f} USD",
                _incomplete(a),
            ]
        )
    return [
        "## Pantry transfer aggregate display",
        "",
        *_table(
            [
                "Policy",
                "Target met T01–T02",
                "Supported partial fulfillment T03–T04",
                "Kits fulfilled by deadline / original target",
                "Residual deficit",
                "Conservation failures",
                "Unnecessary reservations",
                "Invalid attempts / executed violations",
                "Checks and tool cost",
                "Incomplete runs",
            ],
            rows,
        ),
        "",
        "Kits are staff-confirmed distributions by the deadline, summed over the scored episodes"
        " (a timed-out or crashed episode is not in these sums: see Incomplete runs), against the"
        " original target of each; reservations and receipts are not fulfillment. Supported"
        " partial fulfillment names who chose the decision reporting the deficit.",
        "",
    ]


def _denominators(metrics: dict[str, Any]) -> list[str]:
    rows = []
    for p in metrics["policies"]:
        a = metrics["by_policy"][p]
        classes = "; ".join(
            f"{CLASS_LABELS[k]} {_share(a.get(CLASS_METRIC[k]))}"
            for k in CLASS_METRIC
            if a.get(CLASS_METRIC[k])
        )
        rows.append(
            [
                POLICY_NAMES[p],
                a["planned"],
                a["recorded"],
                a["scored"],
                a["capped"],
                a["statuses"].get("timeout", 0),
                a["statuses"].get("crashed", 0),
                a["statuses"].get("integrity_failed", 0),
                a.get("aborted", 0),
                a["missing"],
                classes or "—",
            ]
        )
    return [
        "## Counts and denominators",
        "",
        *_table(
            [
                "Policy",
                "Planned",
                "Recorded",
                "Scored from state",
                "Capped",
                "Timed out",
                "Crashed",
                "Trace failed",
                "Aborted (harness)",
                "Missing",
                "Outcome classes (met / recorded)",
            ],
            rows,
        ),
        "",
    ]


def _verification(metrics: dict[str, Any]) -> list[str]:
    rows = []
    for p in metrics["policies"]:
        a = metrics["by_policy"][p]
        v, prep, comp = a["verification"], a["preparation"], a["computation"]
        rows.append(
            [
                POLICY_NAMES[p],
                v["status_checks"],
                v["distinct_sources"],
                v["repeated_checks"],
                v["failed_checks"],
                v["simulated_minutes"],
                a["plan_churn"],
                f"{prep['holds']} holds, {prep['hold_minutes']} min,"
                f" {prep['hold_fee_cents']} cents in fees (part of committed money),"
                f" {prep['expired_holds']} expired, {prep['unreleased_holds']} unreleased",
                f"{a.get('computation_measured', '—')} episodes measured:"
                f" {comp['model_calls']} calls ({comp['model_retries']} retries,"
                f" {comp['model_failed_calls']} failed); {comp['prompt_tokens']}+"
                f"{comp['completion_tokens']} tokens; {comp['latency_ms']} ms;"
                f" {comp['cost_usd']:.4f} USD",
            ]
        )
    return [
        "## Verification, churn, preparation and computation",
        "",
        "Over the scored episodes. Plan churn is committed revisions plus the previously valid"
        " assignments they altered (an assignment the kept plan already failed a hard check on"
        " in the planner's evaluation before the change is a repair, not churn).",
        "",
        *_table(
            [
                "Policy",
                "Status checks",
                "Distinct sources",
                "Repeated",
                "Failed",
                "Simulated minutes",
                "Plan churn",
                "Preparation cost",
                "Computation",
            ],
            rows,
        ),
        "",
    ]


def _per_case(metrics: dict[str, Any]) -> list[str]:
    rows = []
    for r in sorted(metrics["episodes"], key=lambda r: (r["case_id"], r["policy"], r["trial"])):
        if r["status"] in ("missing", "aborted"):
            rows.append(
                [
                    r["case_id"],
                    r["policy"],
                    r["seed"] or "once",
                    r["status"],
                    "",
                    "",
                    "",
                    "",
                    "not run" if r["status"] == "missing" else "stopped by the harness; rerun",
                    "",
                ]
            )
            continue
        comp = r.get("computation") or {}
        status = f"{CLASS_LABELS.get(r['outcome_class'] or '', 'outcome')}: {_cell(r['success'])}"
        if r["status"] != "completed":
            status += f" ({r['status']})"
        note = "; ".join(r["failure_reasons"]) or "met"
        rows.append(
            [
                r["case_id"],
                r["policy"],
                r["seed"] if r["seed"] is not None else "once",
                status,
                f"{(r.get('invalid_attempts') or {}).get('count', '—')} /"
                f" {r.get('executed_violations', '—')}",
                (r.get("plan_churn") or {}).get("committed_revisions", "—"),
                (r.get("verification") or {}).get("status_checks", "—"),
                f"{comp.get('model_calls', 0)} model / {comp.get('tool_calls', '—')} tool calls;"
                f" {float(comp.get('cost_usd') or 0):.4f} USD",
                note,
                f"episodes/{r['key']}/trace.json.gz",
            ]
        )
    return [
        "## Per-case display",
        "",
        *_table(
            [
                "Case",
                "Policy",
                "Seed/run ID",
                "Final original-goal status",
                "Invalid attempts / violations",
                "Plan edits",
                "Verification calls",
                "Actual model/tool cost",
                "Outcome note",
                "Trace",
            ],
            rows,
        ),
        "",
        "The case is the comparison unit; the three model runs within a case show variability and"
        " are not three independent worlds.",
        "",
    ]


def _pantry_ledger(metrics: dict[str, Any]) -> list[str]:
    episodes = sorted(metrics["episodes"], key=lambda r: (r["case_id"], r["policy"], r["trial"]))
    targets, pools = [], []
    for r in episodes:
        pantry = r.get("pantry")
        if not pantry:
            continue
        run = f"{r['case_id']} {r['policy']} {r['seed'] or 'once'}"
        targets += [
            [
                run,
                t["target_id"],
                t["original_target"],
                t["current_target"],
                t["on_time"],
                t["late"],
                t["supply_shortfall"],
                t["service_deficit"],
            ]
            for t in pantry["targets"]
        ]
        pools += [
            [
                run,
                p["resource_id"],
                p["opening"],
                p["expected"],
                p["reserved_at_end"],
                p["received"],
                p["transferred_out"],
                p["distributed"],
                p["on_hand_at_end"],
                "yes" if p["conserved"] else "NO",
            ]
            for p in pantry["pools"]
        ]
    if not targets and not pools:
        return []
    integrity = [
        [
            f"{r['case_id']} {r['policy']} {r['seed'] or 'once'}",
            r["pantry"]["staff_confirmations"],
            r["pantry"]["duplicate_attempts_blocked"],
            r["pantry"]["duplicate_or_unauthorized_credits"],
            "ok"
            if r["pantry"]["receipt_integrity_ok"]
            else "; ".join(r["pantry"]["receipt_integrity_problems"]),
        ]
        for r in sorted(metrics["episodes"], key=lambda r: (r["case_id"], r["policy"], r["trial"]))
        if r.get("pantry")
    ]
    return [
        "## Pantry quantity and receipt ledger",
        "",
        "Per target (the original target stays visible; fulfillment is staff-confirmed"
        " distribution, by the deadline and after it):",
        "",
        *_table(
            [
                "Case/run",
                "Target",
                "Original target",
                "Current target",
                "Fulfilled by deadline",
                "Fulfilled late",
                "Supply shortfall",
                "Service deficit",
            ],
            targets,
        ),
        "",
        "Per stock pool (at the episode's end; expected stock is not stock until received):",
        "",
        *_table(
            [
                "Case/run",
                "Pool",
                "Initial physical stock",
                "Expected",
                "Reserved at end",
                "Received",
                "Transferred out",
                "Distributed",
                "Final on-hand",
                "Conserved",
            ],
            pools,
        ),
        "",
        *_table(
            [
                "Case/run",
                "Staff confirmations",
                "Duplicate attempts blocked",
                "Duplicate or unauthorized credits",
                "Receipt and evidence integrity",
            ],
            integrity,
        ),
        "",
    ]


def _extraction(metrics: dict[str, Any]) -> list[str]:
    labels = ("correct", "incorrect", "abstained", "malformed", "rejected", "not_recorded")
    rows = [
        [POLICY_NAMES[p], *(metrics["by_policy"][p]["extraction"].get(k, 0) for k in labels)]
        for p in metrics["policies"]
        if metrics["by_policy"][p]["extraction"]
    ]
    if not rows:
        return [
            "## Interpretation display",
            "",
            "No message annotations exist for these cases, so no extraction label was computed.",
            "",
        ]
    return [
        "## Interpretation display",
        "",
        *_table(["Policy", *labels], rows),
        "",
        "Each annotated message gets one label per episode from the policy's first structured"
        " reading of it: P2 and P3's recorded readings, P0's frozen parser replayed over the"
        " episode's observations (the pantry baseline reads no notices). P1 records no"
        " structured reading (`not_recorded`), nor does a reading lost to a provider error.",
        "",
    ]


def _missing(metrics: dict[str, Any]) -> list[str]:
    missing = metrics["missing"]
    aborted = metrics.get("aborted", [])
    return [
        "## Missing and aborted episodes",
        "",
        *(
            [f"- `{k}` (missing)" for k in missing] + [f"- `{k}` (aborted)" for k in aborted]
            if missing or aborted
            else ["None: every planned episode has a scored record."]
        ),
        "",
    ]


def render_markdown(results: dict[str, Any], metrics: dict[str, Any]) -> str:
    plan = results["plan"]
    planned = len(plan["episodes"])
    recorded = planned - len(metrics["missing"]) - len(metrics.get("aborted", []))
    kind = "held-out" if plan["heldout"] else "development (not a reported result)"
    lines = [
        "# Evaluation results",
        "",
        f"Generated by `plan-b eval report` from one results directory: suite **{plan['suite']}**,"
        f" {kind}, {recorded} of {planned} planned episodes recorded"
        f" ({len(plan['case_refs'])} cases × policies {', '.join(plan['policies'])}). Descriptive"
        " counts only: no composite score and no significance test. A blank cell (—) means not"
        " measured, not zero.",
        "",
        *_manifest(results, metrics),
        *(_campus_aggregate(metrics) if plan["suite"] == "campus" else _pantry_aggregate(metrics)),
        *_denominators(metrics),
        *_verification(metrics),
        *_per_case(metrics),
        *_pantry_ledger(metrics),
        *_extraction(metrics),
        *_missing(metrics),
        "## Figure",
        "",
        "![Outcome met and status checks per case and policy](figure.svg)",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------- figure


def render_svg(metrics: dict[str, Any]) -> str:
    """Per case (rows) and policy (bars): left, the share of recorded episodes that met the
    case's outcome class, labelled k/n; right, the mean status checks per scored episode.
    Two panels with their own axes, no shared scale between them."""
    policies = metrics["policies"]
    cases = list(metrics["by_case"].values())
    bar, gap, group_pad = 10, 2, 14
    group = len(policies) * (bar + gap) - gap
    left, label_w, panel_w, mid = 16, 190, 260, 70
    top = 78
    height = top + len(cases) * (group + group_pad) + 40
    width = left + label_w + panel_w + mid + panel_w + 24
    x1 = left + label_w
    x2 = x1 + panel_w + mid
    checks = [
        c["policies"][p]["status_checks_mean"]
        for c in cases
        for p in policies
        if c["policies"][p]["status_checks_mean"] is not None
    ]
    max_checks = float(math.ceil(max([1.0, *checks])))
    css = ["svg{font-family:system-ui,-apple-system,'Segoe UI',sans-serif}"]
    light = [":root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e4e3df"]
    dark = [":root{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#383835"]
    for p in policies:
        light.append(f";--{p}:{SERIES[p][0]}")
        dark.append(f";--{p}:{SERIES[p][1]}")
    css += ["".join(light) + "}", "@media (prefers-color-scheme: dark){" + "".join(dark) + "}}"]
    css += [
        ".bg{fill:var(--bg)}.t{fill:var(--ink);font-size:12px}.s{fill:var(--ink2);font-size:11px}",
        ".h{fill:var(--ink);font-size:14px;font-weight:600}.g{stroke:var(--grid);stroke-width:1}",
    ]
    css += [f".{p}{{fill:var(--{p})}}" for p in policies]
    # Presentation attributes carry the light colours for renderers without CSS variables;
    # the stylesheet's rules override them where it applies (light and dark).
    fill = {"t": 'fill="#0b0b0b"', "s": 'fill="#52514e"', "h": 'fill="#0b0b0b"'}
    grid = 'stroke="#e4e3df"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}" role="img" aria-labelledby="ttl dsc">',
        '<title id="ttl">Outcome met and status checks, per case and policy</title>',
        '<desc id="dsc">For each case, one bar per policy: on the left the share of recorded'
        " episodes that met the case's outcome class (labelled met/recorded), on the right the"
        " mean number of status checks per scored episode.</desc>",
        "<style>" + "".join(css) + "</style>",
        f'<rect class="bg" fill="#fcfcfb" x="0" y="0" width="{width}" height="{height}"/>',
        f'<text class="h" {fill["h"]} x="{x1}" y="22">Episodes meeting the case outcome</text>',
        f'<text class="h" {fill["h"]} x="{x2}" y="22">Status checks per episode (mean)</text>',
    ]
    lx = x1
    for p in policies:
        out.append(
            f'<rect class="{p}" fill="{SERIES[p][0]}" x="{lx}" y="34" width="10" height="10"'
            ' rx="2"/>'
        )
        out.append(
            f'<text class="s" {fill["s"]} x="{lx + 14}" y="43">{escape(POLICY_NAMES[p])}</text>'
        )
        lx += 14 + 7 * len(POLICY_NAMES[p]) + 18
    for frac in (0, 0.5, 1):
        x = x1 + frac * panel_w
        out.append(
            f'<line class="g" {grid} x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 30}"/>'
        )
        out.append(
            f'<text class="s" {fill["s"]} x="{x:.1f}" y="{height - 14}"'
            f' text-anchor="middle">{frac:.0%}</text>'
        )
    for tick in sorted({0.0, max_checks / 2, max_checks}):
        x = x2 + tick / max_checks * panel_w
        out.append(
            f'<line class="g" {grid} x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{height - 30}"/>'
        )
        out.append(
            f'<text class="s" {fill["s"]} x="{x:.1f}" y="{height - 14}"'
            f' text-anchor="middle">{tick:.3g}</text>'
        )
    y = top
    for c in cases:
        name = c["case_id"] + (" (neg. control)" if c["negative_control"] else "")
        out.append(
            f'<text class="t" {fill["t"]} x="{left}" y="{y + group / 2 + 4:.1f}">'
            f"{escape(name)}</text>"
        )
        out.append(
            f'<text class="s" {fill["s"]} x="{left}" y="{y + group / 2 + 17:.1f}">'
            f"{escape(CLASS_LABELS.get(c['outcome_class'] or '', ''))}</text>"
        )
        for i, p in enumerate(policies):
            cell = c["policies"][p]
            by = y + i * (bar + gap)
            share = cell["success"] / cell["n"] if cell["n"] else 0.0
            w = max(share * panel_w, 0.0)
            tip = f"{c['case_id']} {POLICY_NAMES[p]}: {cell['success']}/{cell['n']} met"
            if w > 0:
                out.append(
                    f'<rect class="{p}" fill="{SERIES[p][0]}" x="{x1}" y="{by}" width="{w:.1f}"'
                    f' height="{bar}" rx="2">'
                    f"<title>{escape(tip)}</title></rect>"
                )
            label = f"{cell['success']}/{cell['n']}" if cell["n"] else "not run"
            out.append(
                f'<text class="s" {fill["s"]} x="{x1 + w + 4:.1f}" y="{by + 9}">{label}</text>'
            )
            mean = cell["status_checks_mean"]
            if mean is not None:
                w2 = mean / max_checks * panel_w
                tip2 = f"{c['case_id']} {POLICY_NAMES[p]}: {mean:.2f} status checks per episode"
                if w2 > 0:
                    out.append(
                        f'<rect class="{p}" fill="{SERIES[p][0]}" x="{x2}" y="{by}"'
                        f' width="{w2:.1f}" height="{bar}"'
                        f' rx="2"><title>{escape(tip2)}</title></rect>'
                    )
                out.append(
                    f'<text class="s" {fill["s"]} x="{x2 + w2 + 4:.1f}" y="{by + 9}">'
                    f"{mean:.2g}</text>"
                )
        y += group + group_pad
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write_report(results_dir: Path, out_dir: Path | None = None) -> dict[str, Path]:
    results = load_results(results_dir)
    metrics = suite_metrics(results)
    target = out_dir or results_dir / REPORT_DIR
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "metrics": target / "metrics.json",
        "markdown": target / "evaluation_results.md",
        "figure": target / "figure.svg",
    }
    paths["metrics"].write_text(
        json.dumps(metrics, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["markdown"].write_text(render_markdown(results, metrics), encoding="utf-8")
    paths["figure"].write_text(render_svg(metrics), encoding="utf-8")
    return paths
