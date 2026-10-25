"""Three consecutive automated rehearsals of the showcase story (Playwright, Chromium).

Not part of the default pytest run. Usage (from apps/plan_b, after `npm run build` in web/):

    uv run python tests/e2e/rehearsal.py --out <dir>

These are AUTOMATED internal rehearsals, not human ones: no speaking, no projector. Each
rehearsal starts from a clean reset (``scripts/demo_prep.py``: an empty state directory and the
verified recorded traces), starts its own ``plan-b serve`` on 127.0.0.1, signs in, and clicks
through the live-board story of PEEAI_plan/handoffs/wave_3/SHOWCASE.md. That story is the
storyboard's (``tests/e2e/storyboard.py``, reused as it is, with its checks of the page against
fresh API reads), plus the results segment: the committed held-out figure is opened and its
title checked. Before every reset and at the end, the episode's receipts and final state are
read from the API. All three rehearsals must give the same receipts and final states.

Rehearsal 2 forces a provider failure first. Its server is configured with an invalid base URL
(``http://127.0.0.1:<a closed port>/api/v1``), a placeholder key file in the work directory and a
spend ledger in the work directory: no request leaves this machine, no real key is read and the
real ledger is not touched. On ``dev01`` it selects **Live agent**, presses **Run live agent**,
and checks that the failure is visible (a ``provider_error`` card), that nothing changed (plan,
holds, commitments, budget, receipts), and that the ledger holds no successful call and no cost.
It then switches to the labeled offline replay of the same scenario
(``live_p2-live_dev01_trace.json``): the "Recorded replay" banner, "Integrity check passed", no
request other than GET, and the recorded receipts on its final state. Then it resets and runs the
story like the others.

Writes ``rehearsal_report.json`` (checks, timings, signatures) into ``--out``. The frames the
reused story takes go to a temporary directory and are removed. Exit code 0 only if every check
of every rehearsal held.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storyboard  # noqa: E402 - the storyboard's story, reused as it is
from walkthrough import APP, CODE, api, sign_in_moderator, stop, token_of  # noqa: E402
from walkthrough import load_case as clean_load  # noqa: E402

sys.path.insert(0, str(APP / "scripts"))
from demo_prep import prepare  # noqa: E402

REHEARSALS = 3
FORCED = 2  # the rehearsal that forces a provider failure first
FALLBACK_TRACE = "live_p2-live_dev01_trace.json"  # P2 live/1.0.0 on dev01, recorded in Wave 2
SWITCH_AFTER_S = 20  # SHOWCASE.md: switch to the replay after 20 s without a visible change
RESULTS = APP / "evaluation/results/wave3_heldout_20261025T1625Z"
RESULTS_COMMIT = "c052338"  # the commit that recorded the held-out results
FIGURE = RESULTS / "campus/report/figure.svg"
LEDGER = APP / "var/model_spend.json"  # the repository's spend ledger, never written here
FIGURE_TITLE = "Outcome met and status checks, per case and policy"
# The server runs the CLI with the spend ledger moved into the work directory.
SERVE = (
    "import pathlib, sys; import plan_b.agent.config as c; "
    "c.DEFAULT_LEDGER = pathlib.Path(sys.argv[1]); from plan_b.cli import main; "
    "sys.exit(main(sys.argv[2:]))"
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def snapshot(base: str, token: str) -> dict[str, Any]:
    """The current episode's receipts and final state, without per-run ids or wall times."""
    s = api(base, "api/state", token)
    stock = s.get("stock") or {}
    return {
        "scenario_id": s["scenario_id"],
        "clock": s["clock"],
        "revision": s["revision"],
        "plan_version": s["plan"]["plan_version"],
        "assignments": [[a["activity_id"], a["start"], a["end"]] for a in s["plan"]["assignments"]],
        "receipts": [[r.get("receipt_id"), r.get("tool"), r.get("status")] for r in s["receipts"]],
        "holds": [[h.get("hold_id"), h.get("status")] for h in s["holds"]],
        "commitments": len(s["commitments"]),
        "budget": {k: s["budget"][k] for k in ("committed_cents", "reserved_cents")},
        "decisions": [[d.get("policy_id"), d.get("kind")] for d in s["decisions"]],
        "stock": stock_summary(stock),
    }


def stock_summary(stock: dict[str, Any]) -> Any:
    """The pantry's counters, pool balances, allocations, distributions and handoff tasks."""
    if not stock:
        return None
    keep = ("service", "balances", "allocations", "distributions", "handoff_tasks")
    return {k: without_wall_times(stock[k]) for k in keep if k in stock} or sorted(stock)


def without_wall_times(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: without_wall_times(v)
            for k, v in value.items()
            if not re.search(r"(^|_)(wall|created|updated|recorded)(_|$)", k)
        }
    if isinstance(value, list):
        return [without_wall_times(v) for v in value]
    return value


def file_digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def rehearse(
    browser: Browser, number: int, work: Path, base: str, forced: bool, replays: Path
) -> dict[str, Any]:
    frames = work / "frames"
    frames.mkdir()
    report = storyboard.StoryReport(frames)
    signatures: list[dict[str, Any]] = []
    original = storyboard.load_case
    token: dict[str, str] = {}

    def load_case(page: Page, case_ref: str) -> None:
        # The episode about to be closed: its receipts and final state.
        if "mod" in token:
            current = api(base, "api/moderator/current", token["mod"])
            if current.get("episode_id"):
                signatures.append({"case_ref": token["case"], **snapshot(base, token["mod"])})
        token.setdefault("mod", token_of(page))
        token["case"] = case_ref
        original(page, case_ref)

    forced_record: dict[str, Any] | None = None
    forced_checks = 0
    t0 = time.monotonic()
    storyboard.load_case = load_case
    try:
        if forced:
            forced_record = forced_failure(browser, base, report, work, replays)
            forced_checks = len(report.checks)
        storyboard.story(browser, base, report, tuple(sorted(p.name for p in replays.iterdir())))
        if "mod" in token:
            signatures.append({"case_ref": token["case"], **snapshot(base, token["mod"])})
        results_segment(browser, report)
    except Exception as exc:  # recorded as a failed check; the report is still written
        first = (str(exc).splitlines() or [""])[0]
        report.check("rehearsal ran to the end", False, f"{type(exc).__name__}: {first}")
    finally:
        storyboard.load_case = original
        report.finish()
    seconds = round(time.monotonic() - t0, 1)
    segments: dict[str, float] = {}
    for step in report.steps:
        segments[step["segment"]] = round(
            segments.get(step["segment"], 0.0) + step.get("seconds", 0.0), 1
        )
    return {
        "rehearsal": number,
        "forced_provider_failure": forced,
        "seconds": seconds,
        "segments_seconds": segments,
        "forced_failure_checks": forced_checks,
        "story_checks": len(report.checks) - forced_checks,
        "checks": report.checks,
        "passed": all(c["passed"] for c in report.checks),
        "signatures": signatures,
        "forced": forced_record,
    }


def forced_failure(
    browser: Browser, base: str, report: storyboard.StoryReport, work: Path, replays: Path
) -> dict[str, Any]:
    """Live agent against an unreachable endpoint, then the switch to the recorded replay."""
    report.begin("forced_failure", "live", "Forced provider failure, then the recorded replay.")
    mod = sign_in_moderator(browser, base, storyboard.VIEWPORT)
    mtoken = token_of(mod)
    report.secret("session token of the moderator (forced failure)", mtoken)
    clean_load(mod, "dev01")
    before = snapshot(base, mtoken)
    mod.get_by_role("radio", name=re.compile(r"^Live agent")).click()
    expect(mod.get_by_role("button", name="Run live agent")).to_be_visible(timeout=10000)
    head = mod.locator("header").first.inner_text()
    report.check("the board shows the live label before the press", "Live agent" in head)
    pressed = time.monotonic()
    mod.get_by_role("button", name="Run live agent").click()
    card = mod.get_by_text("provider_error", exact=False).first
    expect(card).to_be_visible(timeout=SWITCH_AFTER_S * 1000)
    visible_s = round(time.monotonic() - pressed, 1)
    after = snapshot(base, mtoken)
    report.check(
        f"the failure is visible as a provider_error card within {SWITCH_AFTER_S} s",
        visible_s <= SWITCH_AFTER_S,
        f"{visible_s} s after the press",
    )
    unchanged = {k: before[k] == after[k] for k in ("plan_version", "holds", "commitments")}
    unchanged["budget"] = before["budget"] == after["budget"]
    unchanged["receipts"] = before["receipts"] == after["receipts"]
    report.check(
        "nothing changed: plan, holds, commitments, budget and receipts as before the press",
        all(unchanged.values()),
        json.dumps(unchanged),
    )
    kinds = [d for d in after["decisions"] if str(d[0]).startswith("live/")]
    report.check("the failed run is recorded under the live policy id", bool(kinds), str(kinds))
    path = work / "ledger.json"
    ledger = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    calls = ledger.get("calls", [])
    outcomes = sorted({str(c.get("outcome")) for c in calls})
    report.check(
        "the work ledger recorded the failed call, as a transport failure with no cost",
        path.is_file()
        and bool(calls)
        and outcomes == ["transport"]
        and not ledger.get("total_cost_usd"),
        f"{len(calls)} calls, outcomes {outcomes}, total {ledger.get('total_cost_usd')}",
    )
    report.frame(mod)
    mod.context.close()

    # The switch: the recorded run of the same scenario, labeled as a replay.
    switched = time.monotonic()
    page, posts = storyboard.open_replay(browser, base, FALLBACK_TRACE)
    integrity = page.locator(".replay-integrity").first.get_attribute("data-integrity")
    banner = page.locator(".replay-banner").first.inner_text()
    page.get_by_role("button", name="Final recorded state").click()
    page.wait_for_timeout(500)
    text = page.locator("body").inner_text()
    trace = json.loads((replays / FALLBACK_TRACE).read_text(encoding="utf-8"))
    receipt_ids = [str(r.get("receipt_id")) for r in trace.get("receipts", [])]
    ready_s = round(time.monotonic() - switched, 1)
    report.check(
        "the replay is labeled and its integrity check passed",
        "Recorded replay" in banner and integrity == "passed",
        f"integrity {integrity}; ready {ready_s} s after the switch",
    )
    report.check(
        "the replay's final state shows the recorded receipts",
        bool(receipt_ids) and all(rid in text for rid in receipt_ids),
        f"receipts {receipt_ids}",
    )
    report.check("the replay sent no request other than GET", posts == [], f"{len(posts)} sent")
    report.frame(page)
    page.context.close()
    return {
        "endpoint": "http://127.0.0.1:<closed port>/api/v1 (nothing listening)",
        "failure_visible_seconds": visible_s,
        "replay": FALLBACK_TRACE,
        "replay_ready_seconds": ready_s,
        "ledger_calls": len(calls),
        "ledger_outcomes": outcomes,
        "ledger_total_usd": ledger.get("total_cost_usd"),
        "unchanged": unchanged,
    }


def results_segment(browser: Browser, report: storyboard.StoryReport) -> None:
    """The results slides: the committed held-out figure opens and reads as committed."""
    # Filed under the storyboard's "close" segment, the last of its runbook segments.
    report.begin("results_figure", "close", "Results: the committed held-out figure.")
    page = browser.new_context(viewport=storyboard.VIEWPORT).new_page()
    page.goto(FIGURE.as_uri())
    title = page.locator("title").first.text_content() or ""
    report.check("the results figure opens with its title", title == FIGURE_TITLE, title)
    digest = hashlib.sha256(FIGURE.read_bytes()).hexdigest()
    relative = FIGURE.resolve().relative_to(APP.parent.parent).as_posix()
    shown = subprocess.run(
        ["git", "show", f"{RESULTS_COMMIT}:{relative}"], cwd=APP, capture_output=True, check=False
    )
    committed = hashlib.sha256(shown.stdout).hexdigest() if shown.returncode == 0 else None
    report.check(
        f"the figure is the committed report's (commit {RESULTS_COMMIT})",
        digest == committed,
        f"{digest[:16]} against {str(committed)[:16]}",
    )
    page.context.close()


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    rehearsals: list[dict[str, Any]] = []
    started = time.monotonic()
    ledger_before = file_digest(LEDGER)
    for number in range(1, REHEARSALS + 1):
        forced = number == FORCED
        work = Path(tempfile.mkdtemp(prefix="planb_rehearsal_"))
        port = free_port()
        base = f"http://127.0.0.1:{port}/"
        # No rehearsal can reach the real provider: the others get a key path that does not exist.
        env = {**os.environ, "PLAN_B_MODERATOR_CODE": CODE}
        env["PLAN_B_MODEL_KEY_FILE"] = str(work / "no-key-here")
        if forced:
            (work / "placeholder.key").write_text("placeholder-not-a-key\n", encoding="utf-8")
            env.update(
                {
                    "PLAN_B_MODEL_PROVIDER": "openrouter",
                    "PLAN_B_MODEL_BASE_URL": f"http://127.0.0.1:{free_port()}/api/v1",
                    "PLAN_B_MODEL_KEY_FILE": str(work / "placeholder.key"),
                    "PLAN_B_MODEL_ID": "anthropic/claude-sonnet-5.5",
                    "PLAN_B_MODEL_MAX_RUN_COST_USD": "0.10",
                    "PLAN_B_MODEL_MAX_TOTAL_COST_USD": "0.10",
                }
            )
        server: subprocess.Popen[bytes] | None = None
        try:
            prepared = prepare(work / "demo")
            command = [sys.executable, "-c", SERVE, str(work / "ledger.json"), "serve"]
            command += ["--port", str(port), "--var", str(prepared.state)]
            command += ["--replay-dir", str(prepared.replays)]
            log = (work / "serve.log").open("wb")
            server = subprocess.Popen(command, cwd=APP, env=env, stdout=log, stderr=log)
            for _ in range(80):
                try:
                    api(base, "api/health")
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                tail = (work / "serve.log").read_text(encoding="utf-8", errors="replace")[-2000:]
                raise RuntimeError(f"plan-b serve did not answer on {base}: {tail}")
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    record = rehearse(browser, number, work, base, forced, prepared.replays)
                finally:
                    browser.close()
        finally:
            try:
                if server is not None:
                    stop(server)
            finally:
                shutil.rmtree(work, ignore_errors=True)
        rehearsals.append(record)
        print(
            f"rehearsal {number}: {'passed' if record['passed'] else 'FAILED'} in "
            f"{record['seconds']} s ({sum(c['passed'] for c in record['checks'])}/"
            f"{len(record['checks'])} checks)"
        )
    first = rehearsals[0]["signatures"]
    same = [r["signatures"] == first and bool(first) for r in rehearsals]
    expected = expected_signatures(first)
    ledger_unchanged = ledger_before == file_digest(LEDGER)
    passed = (
        all(r["passed"] for r in rehearsals)
        and all(same)
        and expected["passed"]
        and ledger_unchanged
    )
    (out / "rehearsal_report.json").write_text(
        json.dumps(
            {
                "kind": "automated internal rehearsals of the showcase story "
                "(PEEAI_plan/handoffs/wave_3/SHOWCASE.md); not human rehearsals",
                "base_url_kind": "local plan-b serve on 127.0.0.1, a clean demo_prep state each",
                "browser": "Chromium (Playwright), headless",
                "viewport": storyboard.VIEWPORT,
                "rehearsals_run": len(rehearsals),
                "consecutive": True,
                "passed": passed,
                "same_receipts_and_final_states": all(same),
                "repository_ledger_unchanged": ledger_unchanged,
                "expected_outcomes": expected,
                "total_seconds": round(time.monotonic() - started, 1),
                "rehearsals": rehearsals,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"{sum(r['passed'] for r in rehearsals)}/{len(rehearsals)} rehearsals passed; "
        f"same receipts and final states: {all(same)}; expected outcomes: {expected['passed']}; "
        f"repository ledger unchanged: {ledger_unchanged}"
    )
    return 0 if passed else 1


def expected_signatures(signatures: list[dict[str, Any]]) -> dict[str, Any]:
    """The story's known outcomes (DEMO.md and SHOWCASE.md), read from the signatures."""
    case = {s["case_ref"]: s for s in signatures}
    empty: dict[str, Any] = {}

    def tools(ref: str) -> list[Any]:
        return [r[1] for r in case.get(ref, empty).get("receipts", [])]

    dev01, dev04, dev02 = (
        case.get("dev01", empty),
        case.get("dev04", empty),
        case.get("dev02", empty),
    )
    pantry = case.get("pantry_dev01", empty)
    service = ((pantry.get("stock") or {}).get("service") or [{}])[0]
    checks = {
        "dev01: plan version 2 by one apply_plan receipt (rcpt_0001)": dev01.get("plan_version")
        == 2
        and tools("dev01") == ["apply_plan"],
        "dev04: plan version 1 kept, no receipt, no hold, no spend": dev04.get("plan_version") == 1
        and tools("dev04") == []
        and dev04.get("holds") == []
        and dev04.get("budget", {}).get("committed_cents") == 0,
        "dev02: hold, organizer approval, one commitment of $35.00": tools("dev02")
        == ["hold_resource", "update_grant", "apply_plan"]
        and dev02.get("budget", {}).get("committed_cents") == 3500
        and dev02.get("commitments") == 1,
        "skills_dev01: the check-in then the swap (plan version 2)": case.get(
            "skills_dev01", empty
        ).get("plan_version")
        == 2
        and tools("skills_dev01")[:2] == ["check_in", "apply_plan"],
        "pantry_dev01: target 40, 40 distributed on time": service.get("original_quantity") == 40
        and service.get("distributed_quantity") == 40
        and service.get("on_time_quantity") == 40,
        "five episodes recorded": [s["case_ref"] for s in signatures]
        == ["dev01", "dev04", "dev02", "skills_dev01", "pantry_dev01"],
    }
    return {"checks": checks, "passed": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="where rehearsal_report.json is written")
    args = parser.parse_args()
    return run(Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
