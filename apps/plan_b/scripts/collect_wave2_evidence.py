"""Regenerate the Wave 2 evidence set from the current checkout.

Usage (from apps/plan_b, after `uv sync --all-groups` and `npm ci` in web/):

    uv run python scripts/collect_wave2_evidence.py --out <evidence-dir> \
        [--live <dir written by scripts/run_live_cases.py>] [--gate <G-LLM gate record>]

Runs the checks and the development cases with the deterministic baselines, and writes into
<evidence-dir>:

* ``reports/checks.json``: every command, working directory, exit code, duration and summary
  (ruff, format, mypy, pytest with a JUnit XML, web typecheck/build/test/lint, CLI runs, trace
  verification, both browser walkthroughs, the scans below), plus the pytest and web test
  counts, each development case's result line and the recorded live runs;
* ``reports/m2_focused_tests.json``: each mandatory M2 check of ``waves/02_adaptation.md`` with
  the focused tests that cover it and each test's JUnit outcome from the same pytest run;
* ``reports/pantry_accounting.json``: the stock and service counters of every frame of the
  pantry traces, with the conservation, target and handoff checks;
* ``reports/wave1_parity.json``: the dev01-dev06 result lines against the Wave 1 evidence;
* ``reports/model_spend_summary.json``: the spend ledger's totals per run (with ``--live``):
  calls, outcomes, models and cost of each run id, labelled with the recorded run or the gate it
  belongs to. The ledger holds no secret; its per-call generation ids are not copied;
* ``reports/*_outcome.public.json``, ``reports/rejected_actions_steps.json``,
  ``reports/fixture_hashes.json``, ``reports/environment.json``;
* ``traces/``: sanitized deterministic traces (``TRACES_KEPT``); every exported trace, the
  rejected-actions run included, is verified, and the rejection steps are in
  ``reports/rejected_actions_steps.json``;
* ``screenshots/``: the Wave 2 walkthrough's screenshots (256-colour PNGs, join links masked)
  and both walkthroughs' JSON reports;
* ``runner_private/``: runner-side outcome reports *with* predicates and expectations.

``--live`` copies previously recorded live runs (``live_*`` files of its ``reports``,
``traces`` and ``runner_private``) and verifies each live trace again; ``--gate`` copies the G-LLM
gate record as ``reports/g_llm_gate.json``. Paid model calls are never made here: the live runs
are recorded once by ``scripts/run_live_cases.py`` and kept as they are.

Local paths are written as placeholders and the scans of ``scripts/collect_evidence.py`` apply to
every text file written, the copied live runs included. A further scan refuses credential-shaped
text (an OpenRouter key prefix or a bearer token) without reading any key. Nothing here reads
credentials or makes network calls; the walkthroughs use a local server on 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET  # noqa: S405 - parses the JUnit report pytest wrote here
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import collect_evidence as ce

APP = ce.APP
REPO = ce.REPO
WAVE1_CHECKS = REPO / "PEEAI_plan/handoffs/wave_1/evidence/reports/checks.json"
TRACES_KEPT = ("pantry_dev01", "pantry_dev02", "skills_dev01")
WAVE1_CASES = ("dev01", "dev02", "dev04", "dev05", "dev06")
LEDGER = APP / "var" / "model_spend.json"
# Credential shapes, searched for without reading any key: an OpenRouter key and a bearer token.
CREDENTIAL_PATTERNS = (
    ("OpenRouter key prefix", re.compile(r"sk-or-[A-Za-z0-9_-]{8,}")),
    ("bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}")),
)

# The mandatory M2 checks of PEEAI_plan/waves/02_adaptation.md and the focused tests that
# cover them, as (test file, test-name regex) pairs. Parametrized cases are included.
M2_CHECKS: dict[str, list[tuple[str, str]]] = {
    "Live campus behavior": [
        ("test_agent_boundary", r"test_dev01_scripted_model_reaches_the_verified_swap"),
        ("test_agent_boundary", r"test_dev02_style_ask_holds_asks_and_commits"),
        ("test_agent_boundary", r"test_interpretation_checks_identity_and_drops_unknown"),
        ("test_agent_boundary", r"test_duplicates_and_retractions_are_resolved_by_the_server"),
        ("test_agent_boundary", r"test_gate_"),
        ("test_integration_policy", r"test_live_policy_selected_by_name_runs_under_the_same_caps"),
    ],
    "Bounded failure behavior": [
        ("test_agent_boundary", r"test_malformed_"),
        ("test_agent_boundary", r"test_an_option_outside_the_menu_is_rejected_server_side"),
        ("test_agent_boundary", r"test_unknown_entity_is_unresolved_and_never_invented"),
        ("test_agent_boundary", r"test_model_call_cap_stops_the_episode"),
        ("test_agent_boundary", r"test_tool_call_cap_stops_the_episode"),
        ("test_agent_boundary", r"test_the_per_run_tool_budget_still_applies"),
        ("test_agent_boundary", r"test_provider_timeout_is_a_visible_wait_and_retried_later"),
        ("test_agent_boundary", r"test_provider_http_error_is_a_visible_wait"),
        ("test_agent_boundary", r"test_spend_cap_stops_without_sending"),
        ("test_agent_boundary", r"test_stale_revision_"),
        ("test_agent_boundary", r"test_lost_response_"),
        ("test_agent_boundary", r"test_prompt_injection_in_observation_text_changes_nothing"),
        ("test_agent_boundary", r"test_the_key_never_appears_in_"),
        ("test_agent_provider", r"test_malformed_and_invalid_replies_are_typed"),
        ("test_agent_provider", r"test_http_status_errors_are_typed_and_scrubbed"),
        ("test_agent_provider", r"test_transport_timeout_is_typed_and_charged_at_the_bound"),
        ("test_agent_provider", r"test_bounded_timeout_against_a_local_server"),
        ("test_agent_provider", r"test_spend_guard_"),
        ("test_integration_policy", r"test_a_reached_tool_cap_stops_the_rule_policy_and_says_so"),
        ("test_integration_policy", r"test_failed_calls_count_and_a_run_never_exceeds"),
        ("test_integration_policy", r"test_a_reached_model_cap_stops_waking_the_live_policy"),
        ("test_integration_api", r"test_board_runs_stop_at_the_episode_cap"),
    ],
    "Community workflow": [
        ("test_community_skills_exchange", r"test_fixture_loads_through_the_campus_adapter"),
        ("test_community_skills_exchange", r"test_the_changed_constraint_blocks_the_campus_style"),
        ("test_community_skills_exchange", r"test_own_check_in_removes_a_role_assumption"),
        ("test_community_skills_exchange", r"test_skills_dev01_check_in_drives_one_correct_replan"),
        ("test_community_skills_exchange", r"test_participant_cannot_change_the_goal"),
        ("test_community_skills_exchange", r"test_claiming_organizer_authority_in_a_message"),
        ("test_community_skills_exchange", r"test_a_resource_offer_alone_reserves_and_spends"),
        ("test_community_skills_exchange", r"test_goal_"),
        ("test_community_skills_exchange", r"test_skills_dev02_goal_version_change"),
        ("test_resource_offer", r"test_"),
        ("test_integration_api", r"test_participation_tells_each_role_what_it_can_contribute"),
        ("test_integration_api", r"test_offer_and_goal_change_over_http"),
        ("test_stock_conservation", r"test_agent_cannot_call_staff_only_tools"),
    ],
    "Shared pantry core": [
        ("test_pantry_workflow", r"test_four_step_sequence_with_staff_sessions"),
        ("test_pantry_workflow", r"test_runner_case_dev0[12]_"),
        ("test_pantry_workflow", r"test_runner_is_deterministic"),
        ("test_pantry_workflow", r"test_trace_export_verifies_intact_and_carries_no_private"),
        ("test_pantry_workflow", r"test_pantry_policy_and_planner_cannot_reach_private_input"),
        ("test_pantry_workflow", r"test_staff_actions_over_http"),
        ("test_pantry_fixture", r"test_pantry_fixture_loads_through_its_adapter_and_campus"),
        ("test_pantry_fixture", r"test_runtime_1_0_0_records_still_parse"),
        ("test_integration_policy", r"test_rule_baselines_run_under_the_development_caps"),
    ],
    "Stock and service accounting": [
        ("test_stock_conservation", r"test_counters_follow_the_planned_table_exactly"),
        ("test_stock_conservation", r"test_handoff_conserves_stock_in_one_atomic_revision"),
        ("test_stock_conservation", r"test_apply_converts_holds_without_double_counting"),
        ("test_stock_conservation", r"test_external_receipt_reconciles_its_shipment_once"),
        ("test_stock_conservation", r"test_an_eta_or_message_never_adds_stock"),
        ("test_stock_conservation", r"test_stock_ledgers_are_append_only"),
        ("test_pantry_workflow", r"test_completion_distribution_and_next_start_order"),
    ],
    "Quantity failure checks": [
        ("test_stock_conservation", r"test_overlapping_and_non_overlapping_double_allocation"),
        ("test_stock_conservation", r"test_overdraw_unit_and_quantity_shape_are_refused"),
        ("test_stock_conservation", r"test_release_and_expiry_create_no_stock"),
        ("test_stock_conservation", r"test_duplicate_physical_records_cannot_credit_twice"),
        ("test_stock_conservation", r"test_partial_handoff_preserves_the_residual_reservation"),
        ("test_stock_conservation", r"test_early_distribution_cannot_exceed_attended_throughput"),
        ("test_stock_conservation", r"test_a_late_commitment_cannot_backdate_throughput"),
        ("test_stock_conservation", r"test_late_records_keep_their_times_and_fail_on_time"),
        ("test_stock_conservation", r"test_await_shipment_candidate_counting_expected_units"),
        ("test_stock_conservation", r"test_a_transfer_hold_too_late_for_the_staff_response"),
    ],
    "Staff boundary": [
        ("test_stock_conservation", r"test_agent_cannot_call_staff_only_tools"),
        ("test_stock_conservation", r"test_without_staff_attestation_nothing_physical_succeeds"),
        ("test_stock_conservation", r"test_distribution_needs_a_started_service_and_committed"),
        ("test_agent_boundary", r"test_agent_tools_exclude_staff_control_and_participant_tools"),
        ("test_agent_boundary", r"test_the_executor_rejects_staff_unknown_and_ungranted_tools"),
        ("test_pantry_workflow", r"test_outcome_scoring_flags_unattested_and_agent_records"),
        ("test_pantry_fixture", r"test_case_validation_rejects_a_staff_rule_outside_its_grant"),
    ],
    "Future comparison parity": [
        ("test_agent_boundary", r"test_policy_side_modules_cannot_reach_private_input"),
        ("test_agent_boundary", r"test_model_inputs_and_policy_envelopes_exclude_private_data"),
        ("test_agent_boundary", r"test_the_policy_never_sends_a_tool_outside_its_set"),
        ("test_agent_boundary", r"test_the_menu_offers_only_granted_tools"),
        ("test_integration_policy", r"test_live_policy_selected_by_name_runs_under_the_same_caps"),
        ("test_integration_policy", r"test_mode_labels_name_the_policy_that_ran"),
        ("test_integration_policy", r"test_selection_locks_once_the_coordinator_acted"),
        ("test_runner_isolation", r"test_"),
    ],
}


def junit_cases(path: Path) -> list[dict[str, str]]:
    """Every testcase of a pytest JUnit report: its file stem, name and outcome."""
    root = ET.parse(path).getroot()  # noqa: S314 - our own pytest output
    cases = []
    for case in root.iter("testcase"):
        outcome = "passed"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[child.tag]
        cases.append(
            {
                "file": case.get("classname", "").split(".")[-1],
                "name": case.get("name", ""),
                "outcome": outcome,
            }
        )
    return cases


def m2_focused(junit: Path) -> dict[str, Any]:
    """Each M2 check with its focused tests' outcomes from the JUnit report. A pattern that
    matches no test is a problem, so a renamed test cannot drop out silently."""
    cases = junit_cases(junit) if junit.exists() else []
    report: dict[str, Any] = {}
    problems: list[str] = []
    for check, patterns in M2_CHECKS.items():
        tests: dict[str, str] = {}
        for stem, pattern in patterns:
            matched = [
                c for c in cases if c["file"] == stem and re.match(pattern, c["name"]) is not None
            ]
            if not matched:
                problems.append(f"{check}: no test matches {stem}::{pattern}")
            for c in matched:
                tests[f"tests/{c['file']}.py::{c['name']}"] = c["outcome"]
        counts = {
            k: list(tests.values()).count(k) for k in ("passed", "failed", "error", "skipped")
        }
        report[check] = {"counts": counts, "tests": tests}
        if counts["failed"] or counts["error"]:
            problems.append(f"{check}: {counts['failed']} failed, {counts['error']} errors")
    return {"checks": report, "problems": problems}


def pantry_accounting(trace_path: Path) -> dict[str, Any]:
    """The stock and service counters of every frame of a pantry trace, and the problems found
    over all of them: each pool's ledger identity (on hand = opening + received - transferred
    out - distributed), and the units on hand or distributed across the pools staying at the
    opening total (an internal handoff moves units and creates none; the expected shipment is
    never received in these cases, so it never enters stock)."""
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    frames = []
    problems: list[str] = []
    opening_total: int | None = None
    for frame in trace["frames"]:
        stock = frame["state"].get("stock") or {}
        pools = {}
        for b in stock.get("balances", []):
            identity = (
                b["opening_quantity"]
                + b["received_quantity"]
                - b["transferred_out_quantity"]
                - b["distributed_quantity"]
            )
            pools[b["resource_id"]] = {
                k: b[k]
                for k in (
                    "on_hand_quantity",
                    "reserved_quantity",
                    "available_quantity",
                    "held_quantity",
                    "committed_quantity",
                    "distributed_quantity",
                    "expected_quantity",
                )
            }
            if identity != b["on_hand_quantity"] or not b["conserved"]:
                problems.append(f"frame {frame['seq']}: {b['resource_id']} is not conserved")
        total = sum(p["on_hand_quantity"] + p["distributed_quantity"] for p in pools.values())
        if opening_total is None:
            opening_total = sum(b["opening_quantity"] for b in stock.get("balances", []))
        if total != opening_total:
            problems.append(f"frame {frame['seq']}: {total} units, not the opening {opening_total}")
        service = [
            {
                k: s[k]
                for k in (
                    "target_id",
                    "original_quantity",
                    "target_quantity",
                    "supply_gap_quantity",
                    "unfulfilled_quantity",
                    "distributed_quantity",
                    "on_time_quantity",
                    "late_quantity",
                    "committed_quantity",
                )
            }
            for s in stock.get("service", [])
        ]
        frames.append(
            {
                "seq": frame["seq"],
                "revision": frame["revision"],
                "scenario_time": frame["scenario_time"],
                "cause": f"{frame['cause_kind']} {frame['cause_ref'] or ''}".strip(),
                "pools": pools,
                "pool_total_plus_distributed": total,
                "service": service,
                "handoff_tasks": [
                    {
                        k: h[k]
                        for k in ("hold_id", "requested_quantity", "remaining_quantity", "status")
                    }
                    for h in stock.get("handoff_tasks", [])
                ],
                "expected_unreceived": sum(
                    e["outstanding_quantity"] for e in stock.get("expected_shipments", [])
                ),
            }
        )
    targets = {(s["target_id"], s["original_quantity"]) for f in frames for s in f["service"]}
    expected = {f["expected_unreceived"] for f in frames}
    # The counter pairs (supply gap, unfulfilled) in the order they appear, each once.
    sequence: list[tuple[int, int]] = []
    for f in frames:
        for s in f["service"]:
            pair = (s["supply_gap_quantity"], s["unfulfilled_quantity"])
            if not sequence or sequence[-1] != pair:
                sequence.append(pair)
    return {
        "trace": trace_path.name,
        "frames": frames,
        "original_targets": sorted(targets),
        "expected_unreceived_values": sorted(expected),
        "counter_sequence": sequence,
        "problems": problems,
    }


def pantry_checks(dev01: dict[str, Any], dev02: dict[str, Any]) -> list[str]:
    """The canonical handoff (24/16 to 40/0, target 40, achieved service only at the
    staff-recorded distribution) and the partial handoff (10 of 16, residual 6 reserved, a
    6-kit deficit), from the frames. Returns the problems found."""
    problems = list(dev01["problems"]) + list(dev02["problems"])

    def pools(frame: dict[str, Any]) -> tuple[int, int]:
        p = frame["pools"]
        return p["pantry_stock"]["on_hand_quantity"], p["partner_stock"]["on_hand_quantity"]

    frames = dev01["frames"]
    if pools(frames[0]) != (24, 16):
        problems.append(f"dev01 opens at {pools(frames[0])}, not 24/16")
    moves = [
        b["cause"]
        for a, b in zip(frames, frames[1:], strict=False)
        if pools(a) == (24, 16) and pools(b) == (40, 0)
    ]
    if len(moves) != 1 or not moves[0].startswith("stock_received"):
        problems.append(f"dev01 does not move 24/16 to 40/0 in one staff receipt: {moves}")
    if dev01["original_targets"] != [("kits_40", 40)]:
        problems.append(f"dev01 targets {dev01['original_targets']}, not kits_40 = 40 throughout")
    if dev01["expected_unreceived_values"] != [20]:
        problems.append(f"dev01 expected shipment {dev01['expected_unreceived_values']}, not 20")
    if dev01["counter_sequence"] != [(16, 40), (0, 40), (0, 0)]:
        problems.append(f"dev01 counters {dev01['counter_sequence']}, not 16/40, 0/40, 0/0")
    # Holds, the receipt and the commitment leave the deficit at 40; only the staff-recorded
    # distribution records achieved service.
    served = [f for f in frames if f["service"][0]["on_time_quantity"] > 0]
    if not served or not served[0]["cause"].startswith("stock_distributed"):
        problems.append("dev01 achieved service does not first appear at a staff distribution")
    early = [f for f in frames if served and f["seq"] < served[0]["seq"]]
    if any(f["service"][0]["unfulfilled_quantity"] != 40 for f in early):
        problems.append("dev01 unfulfilled target moved before the distribution")
    last = frames[-1]["service"][0]
    if (last["on_time_quantity"], last["unfulfilled_quantity"]) != (40, 0):
        problems.append(f"dev01 ends with on time {last['on_time_quantity']}, not 40")
    tail = dev02["frames"][-1]
    s2 = tail["service"][0]
    if (s2["distributed_quantity"], s2["unfulfilled_quantity"], s2["original_quantity"]) != (
        34,
        6,
        40,
    ):
        problems.append(
            f"dev02 ends with {s2['distributed_quantity']} distributed and "
            f"{s2['unfulfilled_quantity']} unfulfilled, not 34 and 6 of 40"
        )
    partial = [
        h
        for f in dev02["frames"]
        for h in f["handoff_tasks"]
        if h["requested_quantity"] == 16 and h["remaining_quantity"] == 6
    ]
    if not partial:
        problems.append("dev02 never shows the 16-kit hold with 6 remaining after the handoff")
    return problems


def credential_scan(out: Path) -> dict[str, Any]:
    """The 'credential pattern scan' check: no text file under ``out`` holds a credential-shaped
    string. The patterns are shapes, so no key is read; matches are reported by file only."""
    t0 = time.monotonic()
    found: list[str] = []
    scanned = 0
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # screenshots
        scanned += 1
        found += [
            f"{p.relative_to(out)}: {what}" for what, rx in CREDENTIAL_PATTERNS if rx.search(text)
        ]
    clean = f"{scanned} text files: no OpenRouter key prefix and no bearer token"
    return {
        "name": "evidence credential pattern scan",
        "command": "every text file written to <evidence>: "
        + ", ".join(what for what, _ in CREDENTIAL_PATTERNS),
        "cwd": str(APP.relative_to(REPO)),
        "exit_code": 1 if found else 0,
        "seconds": round(time.monotonic() - t0, 1),
        "summary": found or [clean],
    }


def json_check(name: str, problems: list[str], ok_line: str) -> dict[str, Any]:
    return {
        "name": name,
        "command": "computed by the collector from the files it wrote",
        "cwd": str(APP.relative_to(REPO)),
        "exit_code": 1 if problems else 0,
        "seconds": 0.0,
        "summary": problems or [ok_line],
    }


def copy_live(src: Path, out: Path) -> list[dict[str, Any]]:
    """Copy the recorded live runs and return their run records."""
    records = []
    for sub in ("reports", "traces", "runner_private"):
        for p in sorted((src / sub).glob("live_*")):
            shutil.copy2(p, out / sub / p.name)
    for p in sorted((out / "reports").glob("live_*_run.json")):
        records.append(json.loads(p.read_text(encoding="utf-8")))
    return records


def spend_summary(
    ledger: Path, records: list[dict[str, Any]], gate: dict[str, Any] | None
) -> dict[str, Any]:
    """The ledger's totals per run id, each labelled with the recorded live run (or the gate
    record) whose ``ledger.run_ids`` names it; a run id no record names is labelled as such."""
    data = json.loads(ledger.read_text(encoding="utf-8"))
    entries = data.get("calls", [])
    labels = {rid: f"live run {r['label']}" for r in records for rid in r["ledger"]["run_ids"]}
    runs: dict[str, dict[str, Any]] = {}
    for e in entries:
        rid = e.get("run_id") or "(none)"
        if gate is not None and rid.startswith("gate-") and gate.get("live"):
            labels.setdefault(rid, "G-LLM gate")
        run = runs.setdefault(
            rid,
            {
                "label": labels.get(rid, "not a recorded run"),
                "calls": 0,
                "cost_usd": 0.0,
                "outcomes": {},
                "models_returned": [],
            },
        )
        run["calls"] += 1
        run["cost_usd"] = round(run["cost_usd"] + (e.get("cost_usd") or 0.0), 8)
        outcome = str(e.get("outcome"))
        run["outcomes"][outcome] = run["outcomes"].get(outcome, 0) + 1
        model = e.get("model_returned")
        if model and model not in run["models_returned"]:
            run["models_returned"].append(model)
    return {
        "ledger": str(ledger.relative_to(REPO)),
        "total_cost_usd": data.get("total_cost_usd"),
        "calls": len(entries),
        "sum_of_runs_usd": round(sum(r["cost_usd"] for r in runs.values()), 8),
        "runs": runs,
    }


def live_summary(record: dict[str, Any]) -> dict[str, Any]:
    model = record.get("model", {})
    return {
        "label": record["label"],
        "outcome_line": record.get("outcome_line"),
        "error": record.get("error"),
        "model_requested": model.get("requested"),
        "model_returned": model.get("returned"),
        "model_calls": model.get("calls"),
        "tool_calls": record.get("tool_calls", {}).get("total"),
        "run_cost_usd": record["ledger"]["run_cost_usd"],
        "trace": record.get("trace", {}).get("verify"),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="a new or empty evidence directory")
    parser.add_argument("--live", default=None, help="a run_live_cases.py output directory")
    parser.add_argument("--gate", default=None, help="the G-LLM gate record (JSON)")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--allow-identifier", action="append", default=[], metavar="WORD")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists() and (not out.is_dir() or any(p.is_file() for p in out.rglob("*"))):
        print(f"{out}: give a new or empty directory", file=sys.stderr)
        return 2
    allowed = list(dict.fromkeys(w.strip() for w in args.allow_identifier if w.strip()))
    email = ce.git_email()
    if email and email.casefold() in {word.casefold() for word in allowed}:
        print("--allow-identifier cannot exempt the git user.email", file=sys.stderr)
        return 2
    for sub in ("reports", "traces", "screenshots", "runner_private"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="planb_w2_evidence_"))
    try:
        return collect(
            out,
            work,
            live=Path(args.live).resolve() if args.live else None,
            gate=Path(args.gate).resolve() if args.gate else None,
            skip_browser=args.skip_browser,
            allowed=allowed,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def collect(
    out: Path,
    work: Path,
    *,
    live: Path | None,
    gate: Path | None,
    skip_browser: bool,
    allowed: Sequence[str] = (),
) -> int:
    checks: list[dict[str, Any]] = []
    uv = ["uv", "run"]
    web = APP / "web"
    (work / "tmp").mkdir()
    ce._CHILD_ENV.clear()
    ce._CHILD_ENV.update({k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
    ce._CHILD_ENV["TMPDIR"] = str(work / "tmp")
    ce._PLACEHOLDERS[:] = ce.placeholders(out, work, Path.home())
    extra = [p for p in (live, gate) if p is not None]
    for p in extra:  # the copied live runs' source paths are local paths too
        ce._PLACEHOLDERS.append((str(p.parent if p.is_file() else p), "<work>"))
    ce._PLACEHOLDERS.sort(key=lambda pair: -len(pair[0]))

    ce.run(uv + ["ruff", "check", "."], APP, checks, "ruff check")
    ce.run(uv + ["ruff", "format", "--check", "."], APP, checks, "ruff format --check")
    ce.run(uv + ["mypy"], APP, checks, "mypy (strict defs)")
    ce.run(["npm", "run", "typecheck"], web, checks, "web typecheck")
    ce.run(["npm", "run", "build"], web, checks, "web build")
    junit = out / "reports" / "pytest_junit.xml"
    ce.run(
        uv + ["pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
        APP,
        checks,
        "pytest",
    )
    if junit.exists():
        junit.write_text(ce.scrub_junit(junit.read_text()))
    web_tests = ce.run(["npm", "test"], web, checks, "web tests")
    ce.run(["npm", "run", "lint"], web, checks, "web boundary lint")

    runs_out = work / "out"
    cases = ce.run(
        uv
        + ["plan-b", "run-case", "all", "--db", str(work / "runs.sqlite3"), "--out", str(runs_out)],
        APP,
        checks,
        "plan-b run-case all",
    )
    ce.run(
        uv
        + ["plan-b", "demo-rejections", "--db", str(work / "demo.sqlite3"), "--out", str(runs_out)],
        APP,
        checks,
        "plan-b demo-rejections",
    )
    for trace in sorted((runs_out / "traces").glob("*.json")):
        ce.run(
            uv + ["plan-b", "verify-trace", str(trace)], APP, checks, f"verify-trace {trace.name}"
        )
    for ref in TRACES_KEPT:
        shutil.copy2(runs_out / "traces" / f"{ref}_trace.json", out / "traces")
    for report in sorted((runs_out / "reports").glob("*.json")):
        shutil.copy2(report, out / "reports" / report.name)
    for report in sorted((runs_out / "private").glob("*.json")):
        shutil.copy2(report, out / "runner_private" / report.name)

    # Wave 1 behavior: the dev01-dev06 result lines are those of the Wave 1 evidence.
    outcomes = ce.case_lines(cases.stdout)
    wave1 = json.loads(WAVE1_CHECKS.read_text(encoding="utf-8"))["case_outcomes"]
    parity = {
        ref: {
            "wave_1": wave1.get(ref),
            "now": outcomes.get(ref),
            "same": wave1.get(ref) == outcomes.get(ref),
        }
        for ref in WAVE1_CASES
    }
    (out / "reports" / "wave1_parity.json").write_text(json.dumps(parity, indent=2) + "\n")
    checks.append(
        json_check(
            "Wave 1 case lines unchanged",
            [f"{ref} differs from Wave 1" for ref, p in parity.items() if not p["same"]],
            "dev01, dev02, dev04, dev05 and dev06 print the Wave 1 evidence lines",
        )
    )

    # Pantry accounting, from the deterministic baseline's traces.
    try:
        p1 = pantry_accounting(runs_out / "traces" / "pantry_dev01_trace.json")
        p2 = pantry_accounting(runs_out / "traces" / "pantry_dev02_trace.json")
        problems = pantry_checks(p1, p2)
        accounting: dict[str, Any] = {"pantry_dev01": p1, "pantry_dev02": p2, "problems": problems}
    except (OSError, KeyError, IndexError, ValueError) as exc:
        problems = [f"pantry traces could not be read: {type(exc).__name__}: {exc}"]
        accounting = {"problems": problems}
    (out / "reports" / "pantry_accounting.json").write_text(json.dumps(accounting, indent=1) + "\n")
    checks.append(
        json_check(
            "pantry stock and service accounting",
            problems,
            "pantry_dev01: 24/16 -> 40/0 in one revision, conserved every frame, target 40, "
            "counters 16/40 -> 0/40 -> 0/0, S20 20 unreceived; pantry_dev02: 34 of 40, 6 reserved "
            "after a 10-of-16 handoff",
        )
    )

    # Focused M2 tests, from the same pytest run.
    focused = m2_focused(junit)
    (out / "reports" / "m2_focused_tests.json").write_text(json.dumps(focused, indent=2) + "\n")
    checks.append(
        json_check(
            "M2 focused tests",
            focused["problems"],
            "; ".join(
                f"{name}: {c['counts']['passed']} passed" for name, c in focused["checks"].items()
            ),
        )
    )

    if not skip_browser:
        shots1, shots2 = work / "shots1", work / "shots2"
        ce.run(
            uv + ["python", "tests/e2e/walkthrough.py", "--out", str(shots1)],
            APP,
            checks,
            "browser walkthrough, Wave 1 (Playwright, Chromium)",
        )
        ce.run(
            uv + ["python", "tests/e2e/walkthrough_wave2.py", "--out", str(shots2)],
            APP,
            checks,
            "browser walkthrough, Wave 2 (Playwright, Chromium)",
        )
        for shot in sorted(shots1.glob("*.json")):
            shutil.copy2(shot, out / "screenshots" / shot.name)
        for shot in sorted(shots2.glob("*")):
            if shot.suffix == ".png":
                ce.quantize_png(shot, out / "screenshots" / shot.name)
            elif shot.is_file():
                shutil.copy2(shot, out / "screenshots" / shot.name)

    live_runs: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    if live is not None:
        records = copy_live(live, out)
        live_runs = [live_summary(r) for r in records]
        for trace in sorted((out / "traces").glob("live_*_trace.json")):
            ce.run(
                uv + ["plan-b", "verify-trace", str(trace)],
                APP,
                checks,
                f"verify-trace {trace.name} (recorded live run)",
            )
    gate_record = None
    if gate is not None:
        shutil.copy2(gate, out / "reports" / "g_llm_gate.json")
        gate_record = json.loads(gate.read_text(encoding="utf-8"))
    if live is not None and LEDGER.exists():
        spend = spend_summary(LEDGER, records, gate_record)
        (out / "reports" / "model_spend_summary.json").write_text(
            json.dumps(spend, indent=2) + "\n"
        )

    hashes = {
        "public_fixtures": {
            p.name: ce.sha256(p) for p in sorted((APP / "plan_b/scenarios/public").glob("*.json"))
        },
        "private_cases": {
            p.name: ce.sha256(p) for p in sorted((APP / "plan_b/scenarios/private").glob("*.json"))
        },
        "planning_examples": {
            p.name: ce.sha256(p) for p in sorted((REPO / "PEEAI_plan/examples").glob("*.json"))
        },
        "planning_schema": ce.sha256(REPO / "PEEAI_plan/schemas/planning.schema.json"),
        "prompts": {
            p.name: ce.sha256(p) for p in sorted((APP / "plan_b/agent/prompts").glob("*.txt"))
        },
        "lockfiles": {
            "apps/plan_b/uv.lock": ce.sha256(APP / "uv.lock"),
            "apps/plan_b/web/package-lock.json": ce.sha256(web / "package-lock.json"),
        },
        "migrations": {
            p.name: ce.sha256(p) for p in sorted((APP / "plan_b/store/migrations").glob("*.sql"))
        },
    }
    (out / "reports" / "fixture_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")

    def version(cmd: list[str], cwd: Path = APP) -> str:
        try:
            return subprocess.run(  # noqa: S603
                cmd, cwd=cwd, capture_output=True, text=True, env=ce._CHILD_ENV
            ).stdout.strip()
        except OSError:
            return "unavailable"

    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uv": version(["uv", "--version"]),
        "node": version(["node", "--version"]),
        "npm": version(["npm", "--version"]),
        "playwright": version(uv + ["playwright", "--version"]),
        "sqlite": version(uv + ["python", "-c", "import sqlite3; print(sqlite3.sqlite_version)"]),
        "git_head": version(["git", "rev-parse", "HEAD"], REPO),
        "git_branch": version(["git", "branch", "--show-current"], REPO) or "(detached HEAD)",
        "app_tree_clean": not version(["git", "status", "--porcelain", "--", "apps/plan_b"], REPO),
    }
    (out / "reports" / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    record = {
        "pytest_counts": junit_counts(junit),
        "web_test_counts": ce.tap_counts(web_tests.stdout),
        "case_outcomes": outcomes,
        "live_runs": live_runs,
        "checks": checks,
    }

    checks.append(credential_scan(out))
    print(f"[{'ok' if checks[-1]['exit_code'] == 0 else 'FAIL'}] evidence credential pattern scan")
    local = [path for path, _ in ce._PLACEHOLDERS] + [os.path.join(tempfile.gettempdir(), "")]
    scan = ce.scan_check(out, record, local, ce.local_names(), allowed)
    checks.append(scan)
    print(f"[{'ok' if scan['exit_code'] == 0 else 'FAIL'}] evidence identifier scan")
    (out / "reports" / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
    failed = [c["name"] for c in checks if c["exit_code"] != 0]
    print("all checks passed" if not failed else f"FAILED: {failed}")
    return 0 if not failed else 1


def junit_counts(junit: Path) -> dict[str, int]:
    text = junit.read_text() if junit.exists() else ""
    counts = {}
    for key in ("tests", "failures", "errors", "skipped"):
        found = re.search(rf'{key}="(\d+)"', text)
        if found:
            counts[key] = int(found.group(1))
    return counts


if __name__ == "__main__":
    sys.exit(main())
