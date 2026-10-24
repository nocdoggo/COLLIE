"""Browser walkthrough of the Wave 1 board against a real server (Playwright, Chromium).

Not part of the default pytest run. Usage (from apps/plan_b, after `npm run build` in web/):

    uv run python tests/e2e/walkthrough.py --out <dir>

It starts `plan-b serve` on a free port with a fresh state directory (removed afterwards), drives
separate browser contexts for the moderator, participants and organizer (each a distinct scoped
session), checks what the page shows against fresh API reads, and writes screenshots plus a JSON
report of every assertion to <dir>. Exit code 0 only if every assertion held.

The run covers every step of the minimum visible workflow in PEEAI_plan/waves/01_foundation.md:
each check that evidences a step names it (``workflow_step``), and the report lists the steps
with their checks. Screenshots mask every join link (``[data-join-link]``, and any other link
into ``#/join/``), and a check asserts that no issued join code and no session token was in the
visible page text at any screenshot. A check's detail quotes the lines of page text it relied on,
whole, rather than a cut-off prefix.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.sync_api import Browser, Locator, Page, ViewportSize, expect, sync_playwright

APP = Path(__file__).resolve().parents[2]
CODE = "walkthrough-moderator-code"
# Masked in every screenshot: web/src/panels/ModeratorPanel.tsx JoinLink, and any link into a
# join route even without that attribute.
JOIN_LINK = "[data-join-link], a[href*='#/join/']"
POLL_S = 1.5  # web/src/views/EventBoard.tsx POLL_MS
PLAY_S = 1.5  # web/src/replay/ReplayView.tsx PLAY_MS
UNAVAILABLE = "Unavailable — service did not respond"  # components/Observations.tsx
UPDATE_TEXT = "Name badges and markers are on the skills exchange tables."
UPDATE_ENTITY = "skills_exchange"
# The minimum visible workflow, PEEAI_plan/waves/01_foundation.md.
WORKFLOW = {
    1: "Load the fixture into a clean sandbox; show goal, schedule, budget and authority",
    2: "Submit an update through submit_observation; show source, time and affected entity",
    3: "Scoped status query; show the actual result, including unknown/unavailable outcomes",
    4: "Show alternatives and assumptions from evaluate_candidates; a preview reserves nothing",
    5: "Place a hold or apply a checked plan; show the receipt and the next state read",
    6: "Advance the clock: readiness and actual completion or supported failure",
    7: "Reset to a new episode, then play the visible trace under Recorded replay",
}


class Report:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.checks: list[dict[str, Any]] = []
        self.shots: list[str] = []
        # Credentials the run handles, by label. Only labels are ever written to the report.
        self.secrets: list[tuple[str, str]] = [("moderator code", CODE)]
        self.exposed: list[str] = []
        self.masked = 0

    def check(self, name: str, ok: bool, detail: str = "", *, step: int | None = None) -> None:
        entry: dict[str, Any] = {"check": name, "passed": bool(ok), "detail": detail}
        if step is not None:
            entry["workflow_step"] = step
        self.checks.append(entry)
        print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail else ""))

    def secret(self, label: str, value: str) -> None:
        self.secrets.append((label, value))

    def shot(self, page: Page, name: str, *, full: bool = False) -> None:
        # What a viewer could read at this moment must hold no code or token; the image itself
        # masks the join links, whose text shows only a short prefix of the code.
        text = page.locator("body").inner_text()
        self.exposed += [f"{name}: {label}" for label, value in self.secrets if value in text]
        links = page.locator(JOIN_LINK)
        self.masked += links.count()
        path = self.out / f"{name}.png"
        page.screenshot(path=str(path), full_page=full, mask=[links])
        self.shots.append(path.name)

    def workflow(self) -> list[dict[str, Any]]:
        steps = []
        for step, title in WORKFLOW.items():
            mine = [c for c in self.checks if c.get("workflow_step") == step]
            steps.append(
                {
                    "step": step,
                    "title": title,
                    "checks": [c["check"] for c in mine],
                    "passed": bool(mine) and all(c["passed"] for c in mine),
                }
            )
        return steps


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def api(base: str, path: str, token: str | None = None) -> Any:
    req = urllib.request.Request(base + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - local test server
        return json.loads(resp.read())


def poll(read: Callable[[], Any], until: Callable[[Any], bool], timeout_s: float = 20.0) -> Any:
    """Read until the condition holds or the time is up; returns the last read."""
    deadline = time.time() + timeout_s
    while True:
        value = read()
        if until(value) or time.time() > deadline:
            return value
        time.sleep(0.5)


def token_of(page: Page) -> str:
    raw = page.evaluate("() => sessionStorage.getItem('planb.session')")
    data = json.loads(raw)
    return str(data["token"] if isinstance(data, dict) else data)


def local_time(iso: str, tz: str) -> str:
    """HH:MM in the event timezone, as the board's fmtTime shows it."""
    return (
        datetime.fromisoformat(iso.replace("Z", "+00:00"))
        .astimezone(ZoneInfo(tz))
        .strftime("%H:%M")
    )


def cents(value: int) -> str:
    return f"${value / 100:,.2f}"


def quote(text: str, *needles: str) -> str:
    """The lines of ``text`` that hold any of the needles a check relies on, each whole and once
    (whitespace collapsed), then each needle the text lacks: a detail that shows what was read."""
    lines = [line for line in text.splitlines() if line.strip()]
    held = [" ".join(line.split()) for line in lines if any(n in line for n in needles)]
    lacking = [f"lacks {n!r}" for n in needles if n not in text]
    return " | ".join(list(dict.fromkeys(held)) + lacking)


def seconds_until(locator: Locator, text: str, timeout_s: float) -> float | None:
    """Seconds until the locator contains the text, or None if it did not within the time."""
    t0 = time.monotonic()
    try:
        expect(locator).to_contain_text(text, timeout=timeout_s * 1000)
    except AssertionError:
        return None
    return time.monotonic() - t0


def sign_in_moderator(browser: Browser, base: str, size: ViewportSize) -> Page:
    page = browser.new_context(viewport=size).new_page()
    page.goto(base)
    page.get_by_label("Moderator code").fill(CODE)
    page.get_by_role("button", name="Sign in as moderator").click()
    expect(page.get_by_role("heading", name="Moderator controls")).to_be_visible()
    return page


def load_case(page: Page, case_ref: str) -> None:
    page.locator("select").first.select_option(case_ref)
    load = page.get_by_role("button", name="Load episode")
    if load.count():
        load.click()
    else:
        page.get_by_role("button", name="Reset: load a clean episode…").click()
        page.get_by_role("button", name=f"Close it and load case {case_ref}").click()
    expect(page.get_by_text("STATE REVISION", exact=False).first).to_be_visible()
    page.wait_for_timeout(1200)


def join(browser: Browser, moderator: Page, principal: str, base: str, report: Report) -> Page:
    row = moderator.locator("li", has_text=principal).first
    row.get_by_role("button", name="Issue join code").click()
    link = moderator.locator(f"a[data-join-link='{principal}']")
    expect(link).to_be_visible()
    # The link text shows only a prefix of the code; the href carries all of it.
    href = link.get_attribute("href") or ""
    report.secret(f"join code for {principal}", urllib.parse.unquote(href.split("#/join/", 1)[1]))
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(href if href.startswith("http") else base + href[href.index("#") :])
    expect(
        page.get_by_role("heading", name="Your role").or_(
            page.get_by_role("heading", name="Organizer controls")
        )
    ).to_be_visible(timeout=10000)
    report.secret(f"session token of {principal}", token_of(page))
    return page


def wait_for_clock(base: str, token: str, iso: str, timeout_s: float = 90.0) -> dict[str, Any]:
    state = poll(lambda: api(base, "api/state", token), lambda s: s["clock"] >= iso, timeout_s)
    return dict(state)


def header_revision(page: Page) -> str:
    return page.locator("text=STATE REVISION").first.locator("xpath=..").inner_text()


def readiness_of(page: Page, resource_id: str) -> Locator:
    """The Role readiness list item of one person resource ("<label> (<resource_id>)")."""
    return page.locator("#role-readiness li", has_text=f"({resource_id})")


def stop(server: subprocess.Popen[bytes]) -> None:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=10)


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report = Report(out)
    port = free_port()
    base = f"http://127.0.0.1:{port}/"
    var = Path(tempfile.mkdtemp(prefix="planb_e2e_"))
    env = {**os.environ, "PLAN_B_MODERATOR_CODE": CODE}
    server = subprocess.Popen(
        [sys.executable, "-m", "plan_b.cli", "serve", "--port", str(port), "--var", str(var)],
        cwd=APP,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            try:
                api(base, "api/health")
                break
            except OSError:
                time.sleep(0.25)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                walkthrough(browser, base, report)
            except Exception as exc:  # recorded as a failed check; the report is still written
                first = (str(exc).splitlines() or [""])[0]
                report.check("walkthrough ran to the end", False, f"{type(exc).__name__}: {first}")
            browser.close()
    finally:
        # The state directory holds session and join-code tables: never leave it behind.
        try:
            stop(server)
        finally:
            shutil.rmtree(var, ignore_errors=True)
    passed = all(c["passed"] for c in report.checks)
    (out / "walkthrough_report.json").write_text(
        json.dumps(
            {
                "base_url_kind": "local plan-b serve on a free port with a fresh state directory",
                "browser": "Chromium (Playwright)",
                "passed": passed,
                "checks": report.checks,
                "minimum_visible_workflow": report.workflow(),
                "screenshots": report.shots,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"{sum(c['passed'] for c in report.checks)}/{len(report.checks)} checks passed")
    return 0 if passed else 1


def walkthrough(browser: Browser, base: str, report: Report) -> None:
    mod = sign_in_moderator(browser, base, {"width": 1440, "height": 900})
    errors: list[str] = []
    mod.on("pageerror", lambda e: errors.append(str(e)))

    # 1. Load dev01: goal, schedule, budget, authority, mode label, clock in the event timezone.
    load_case(mod, "dev01")
    mtoken = token_of(mod)
    report.secret("session token of the moderator", mtoken)
    head = mod.locator("header").first.inner_text()
    labels_shown = ("Plan B: The Show Must Go On", "Fictional sandbox", "Deterministic policy")
    report.check(
        "header shows product, sandbox and mode labels",
        all(s in head for s in labels_shown),
        quote(head, *labels_shown),
        step=1,
    )
    report.check(
        "scenario clock 16:40 in America/New_York",
        "16:40" in head and "America/New_York" in head,
        step=1,
    )
    report.check(
        "goal and public deadline visible",
        "Public deadline" in head and "18:00" in head,
        step=1,
    )
    loaded = api(base, "api/state", mtoken)
    schedule = mod.locator("#schedule").inner_text()
    budget = mod.locator("#budget").inner_text()
    authority = mod.locator("#authority").inner_text()
    labels = [a["definition"]["label"] for a in loaded["activities"]]
    grants = [g["grant"] for g in loaded["grants"]]
    report.check(
        "schedule, modeled budget and authority envelope visible (fresh API read)",
        all(label in schedule for label in labels)
        and cents(loaded["budget"]["budget_cents"]) in budget
        and bool(grants)
        and all(
            g["principal_id"] in authority
            and cents(g["max_total_committed_cents"]) in authority
            and cents(g["max_total_reserved_cents"]) in authority
            for g in grants
        ),
        f"{len(labels)} activities, budget {cents(loaded['budget']['budget_cents'])}, "
        f"{len(grants)} grants",
        step=1,
    )
    report.shot(mod, "01_loaded_dev01")
    report.shot(mod, "01_loaded_dev01_full", full=True)

    # Keyboard: reach a control by Tab from the top and activate it with Enter (+1 min).
    mod.evaluate(
        "() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); }"
    )
    clock_before = api(base, "api/state", mtoken)["clock"]
    reached = False
    for _ in range(120):
        mod.keyboard.press("Tab")
        label = mod.evaluate("() => document.activeElement && document.activeElement.textContent")
        if label and label.strip() == "+1 min":
            outline = mod.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
            report.check(
                "focused control has a visible focus outline", outline not in ("none", ""), outline
            )
            report.shot(mod, "01b_keyboard_focus")
            mod.keyboard.press("Enter")
            reached = True
            break
    mod.wait_for_timeout(1500)
    clock_after = api(base, "api/state", mtoken)["clock"]
    report.check(
        "keyboard Tab + Enter operated a control",
        reached and clock_after != clock_before,
        f"{clock_before} -> {clock_after}",
    )

    # 2. Run the deterministic policy: verify, evaluate, commit the swap.
    mod.get_by_role("button", name="Run deterministic policy").click()
    expect(mod.get_by_role("heading", name="Applied (1)")).to_be_visible(timeout=15000)
    state = api(base, "api/state", mtoken)
    applied = [r for r in state["receipts"] if r["status"] == "applied"]
    plan = {a["activity_id"]: a for a in state["plan"]["assignments"]}
    report.check(
        "fresh API read: swap applied at revision 4->5",
        len(applied) == 1
        and applied[0]["revision_before"] == 4
        and applied[0]["revision_after"] == 5
        and plan["demonstrations"]["start"] == "2026-11-05T22:30:00Z",
        json.dumps([(r["receipt_id"], r["tool"], r["status"]) for r in state["receipts"]]),
        step=5,
    )
    page_text = mod.locator("body").inner_text()
    report.check(
        "receipt shown on the board matches the API receipt",
        applied[0]["receipt_id"] in page_text,
        step=5,
    )
    report.check(
        "status query result shown with its reported ETA",
        "Answered" in page_text and "17:25" in page_text,
        step=3,
    )
    report.check(
        "alternatives show feasible and rejected candidates",
        "Swap demonstrations and skills exchange" in page_text
        and "Rejected alternatives (" in page_text,
        step=4,
    )
    report.check(
        "evaluating alternatives reserved nothing (fresh API read)",
        state["holds"] == [] and state["budget"]["reserved_cents"] == 0,
        json.dumps(state["budget"]),
        step=4,
    )
    report.shot(mod, "02_policy_verified_and_swapped_full", full=True)
    mod.get_by_role("heading", name="Before and after", exact=True).scroll_into_view_if_needed()
    report.shot(mod, "02b_before_after")
    mod.get_by_text("Rejected alternatives (", exact=False).first.click()  # expand the details
    mod.get_by_role("heading", name="Alternatives", exact=True).scroll_into_view_if_needed()
    report.shot(mod, "02c_alternatives")

    # 3. Facilitator checks in from a separate scoped session; the moderator tab sees it.
    facilitator = "participant_facilitator"
    fac = join(browser, mod, facilitator, base, report)
    fac_token = token_of(fac)
    fac_head = fac.locator("header").first.inner_text()
    report.check(
        "participant tab is a distinct scoped session",
        facilitator in fac_head or "Skills facilitator" in fac_head,
        quote(fac_head, facilitator, "Skills facilitator"),
    )
    report.check("no token rendered in the page", fac_token not in fac.locator("body").inner_text())
    fac_ready = readiness_of(mod, "facilitator")
    before = fac_ready.inner_text()
    report.check(
        "moderator tab shows the facilitator without a check-in before it",
        "No check-in yet" in before and "Checked in" not in before,
        quote(before, "(facilitator)", "No check-in yet", "Checked in"),
        step=6,
    )
    fac.get_by_role("button", name="Check in").click()
    expect(fac.get_by_text("Confirmed in the current state", exact=False).first).to_be_visible(
        timeout=10000
    )
    seen = seconds_until(fac_ready, "Checked in", 2 * POLL_S)
    after = fac_ready.inner_text()
    report.check(
        "moderator tab observes the persisted check-in by polling",
        seen is not None
        and "Checked in" in after
        and "(participant session)" in after
        and facilitator in after,
        f"{'not seen' if seen is None else f'{seen:.1f} s'} after the receipt "
        f"(poll interval {POLL_S} s): "
        + quote(after, "Checked in", "(participant session)", facilitator),
        step=6,
    )
    report.shot(fac, "03_participant_checked_in")
    fac.get_by_role("button", name="Check in").click()
    expect(fac.get_by_text("DUPLICATE_CHECK_IN", exact=False).first).to_be_visible(timeout=10000)
    report.check("duplicate check-in shown as rejected", True)
    report.shot(fac, "04_duplicate_check_in_rejected")

    # 3b. The facilitator sends an update through submit_observation; the moderator's board
    # shows its source, its times and the entity it concerns.
    fac_principal = api(base, "api/state", fac_token)["viewer"]["principal_id"]
    fac.get_by_label("What did you observe?").fill(UPDATE_TEXT)
    fac.get_by_label("About (optional)").select_option(UPDATE_ENTITY)
    fac.get_by_role("button", name="Send update").click()
    sent = poll(
        lambda: api(base, "api/state", mtoken),
        lambda s: any(o["observation"]["text"] == UPDATE_TEXT for o in s["observations"]),
    )
    record = next(o for o in sent["observations"] if o["observation"]["text"] == UPDATE_TEXT)
    obs = record["observation"]
    receipt = next(
        r
        for r in sent["receipts"]
        if r["tool"] == "submit_observation"
        and any(c["entity_id"] == obs["observation_id"] for c in r["state_changes"])
    )
    report.check(
        "participant update recorded through submit_observation (fresh API read)",
        receipt["status"] == "applied"
        and receipt["revision_after"] == record["revision_after"]
        and record["channel"] == "participant_session"
        and obs["source_id"] == fac_principal
        and obs["entity_id"] == UPDATE_ENTITY
        and obs["authority_scope"] == "self_report",
        f"{receipt['receipt_id']} {receipt['status']}: {obs['observation_id']} from "
        f"{obs['source_id']} about {obs['entity_id']} ({obs['authority_scope']})",
        step=2,
    )
    expect(
        fac.get_by_text(f"Confirmed in the current state: receipt {receipt['receipt_id']}")
    ).to_be_visible(timeout=10000)
    report.check(
        "participant tab confirms its update with the API receipt",
        True,
        receipt["receipt_id"],
        step=2,
    )
    report.shot(fac, "03b_participant_update_sent")
    item = mod.locator("#observations li.observation", has_text=UPDATE_TEXT)
    seen_update = seconds_until(item, "Participant session", 2 * POLL_S)
    item_text = item.inner_text() if seen_update is not None else ""
    tz = sent["timezone"]
    entity_label = next(
        a["definition"]["label"]
        for a in sent["activities"]
        if a["definition"]["activity_id"] == obs["entity_id"]
    )
    expected = [
        "Participant session",
        f"from {obs['source_id']}",
        f"Affects {entity_label} ({obs['entity_id']})",
        f"Observed {local_time(obs['observed_at'], tz)}",
        f"received {local_time(obs['received_at'], tz)}",
    ]
    report.check(
        "board shows the update's source, times and affected entity",
        seen_update is not None and all(s in item_text for s in expected),
        " | ".join(s for s in expected if s not in item_text) or " | ".join(expected),
        step=2,
    )
    item.scroll_into_view_if_needed()
    report.shot(mod, "03c_board_shows_participant_update")

    # 4. Presenter checks in; run to the end with the policy.
    pres = join(browser, mod, "participant_presenter", base, report)
    pres.get_by_role("button", name="Check in").click()
    expect(pres.get_by_text("Confirmed in the current state", exact=False).first).to_be_visible(
        timeout=10000
    )
    mod.get_by_label("Minutes").fill("80")
    mod.get_by_role("button", name="Run 80 minutes with policy").click()
    final = wait_for_clock(base, mtoken, "2026-11-05T23:00:00Z")
    mod.wait_for_timeout(2500)  # let the board poll the final state
    lifecycles = {a["definition"]["activity_id"]: a["lifecycle"] for a in final["activities"]}
    report.check(
        "all required activities completed (fresh API read)",
        set(lifecycles.values()) == {"completed"},
        json.dumps(lifecycles),
        step=6,
    )
    report.check(
        "arrival observed before demonstrations started",
        any(o["channel"] == "arrival_record" for o in final["observations"]),
        step=6,
    )
    report.shot(mod, "05_dev01_completed_full", full=True)
    report.shot(mod, "05_dev01_completed")

    # 5. Export the executed run.
    executed = api(base, "api/state", mtoken)
    trace_name = f"{executed['episode_id']}_rev{executed['revision']}.json"
    mod.get_by_role("button", name="Export trace").click()
    listed = poll(
        lambda: [r["name"] for r in api(base, "api/replays")], lambda names: trace_name in names
    )
    report.check(
        "the executed run is exported as a trace on the server",
        trace_name in listed,
        trace_name,
        step=7,
    )

    # 6. Reset: the impossible case dev05 in a new episode.
    load_case(mod, "dev05")
    reset_state = api(base, "api/state", mtoken)
    report.check(
        "reset created a clean episode",
        reset_state["revision"] == 3
        and reset_state["receipts"] == []
        and reset_state["holds"] == []
        and reset_state["episode_id"] != final["episode_id"],
        step=7,
    )
    report.check(
        "old participant session rejected after reset",
        _status(base, "api/state", fac_token) == 401,
        step=7,
    )

    # 7. After the reset, replay the exported dev01 trace read-only and play it through.
    posts: list[str] = []
    replay = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    replay.on("request", lambda r: posts.append(r.url) if r.method != "GET" else None)
    replay.goto(base + "#/replay")
    replay.get_by_role("button", name=trace_name).click()
    replay.wait_for_function(
        "() => { const b = document.querySelector('.replay-integrity[data-integrity]');"
        " return b !== null && b.getAttribute('data-integrity') !== 'checking'; }",
        timeout=15000,
    )
    text = replay.locator("body").inner_text()
    report.check(
        "replay shows the persistent Recorded replay label", "Recorded replay" in text, step=7
    )
    report.check(
        "replay integrity verified in the browser",
        "Integrity check passed" in text
        and replay.locator(".replay-integrity").get_attribute("data-integrity") == "passed",
        step=7,
    )
    report.check(
        "replay opened after the reset shows the pre-reset episode",
        f"episode {executed['episode_id']}" in text
        and api(base, "api/state", mtoken)["episode_id"] == reset_state["episode_id"],
        f"replayed {executed['episode_id']}; live {reset_state['episode_id']}",
        step=7,
    )
    for _ in range(6):
        replay.keyboard.press("ArrowRight")
    replay.wait_for_timeout(500)
    report.check(
        "replay labels recorded results as not re-queried",
        "not re-queried" in replay.locator("body").inner_text(),
        step=7,
    )
    report.shot(replay, "07_recorded_replay")
    frames_match = re.search(r"(\d+) frames", text)
    frames = int(frames_match.group(1)) if frames_match else 0
    replay.keyboard.press("Home")
    replay.get_by_role("button", name="Play").click()
    played = seconds_until(
        replay.locator("#replay-controls"), f"Frame {frames} of {frames}", frames * PLAY_S + 15
    )
    play_button = replay.locator("#replay-controls").get_by_role("button", name="Play")
    report.check(
        "replay plays the visible trace through to its last frame",
        frames > 1
        and played is not None
        and play_button.get_attribute("aria-pressed") == "false"
        and "Recorded replay" in replay.locator("body").inner_text(),
        f"{frames} frames" + (f" played in {played:.0f} s" if played is not None else ""),
        step=7,
    )
    replay.get_by_role("button", name="Final recorded state").click()
    final_text = replay.locator("body").inner_text()
    report.check(
        "replayed final state shows every receipt of the executed run",
        bool(executed["receipts"])
        and all(r["receipt_id"] in final_text for r in executed["receipts"]),
        ", ".join(r["receipt_id"] for r in executed["receipts"]),
        step=7,
    )
    replay.keyboard.press("End")
    replay.wait_for_timeout(500)
    report.shot(replay, "07b_recorded_replay_final_full", full=True)
    report.check(
        "replay issued no POST/PUT/DELETE requests", posts == [], json.dumps(posts), step=7
    )
    live = api(base, "api/state", mtoken)
    report.check(
        "replay created no action in the live episode",
        live["episode_id"] == reset_state["episode_id"]
        and live["revision"] == reset_state["revision"]
        and live["receipts"] == reset_state["receipts"]
        and live["clock"] == reset_state["clock"],
        f"live revision {reset_state['revision']} -> {live['revision']}",
        step=7,
    )

    # 8. Impossible case (dev05, loaded by the reset above).
    mod.get_by_role("button", name="Run deterministic policy").click()
    expect(
        mod.get_by_text("No candidate in the declared action space", exact=False).first
    ).to_be_visible(timeout=15000)
    report.shot(mod, "08_dev05_infeasible_full", full=True)
    mod.get_by_label("Minutes").fill("80")
    mod.get_by_role("button", name="Run 80 minutes with policy").click()
    end5 = wait_for_clock(base, mtoken, "2026-11-05T23:00:00Z")
    mod.wait_for_timeout(2500)
    life5 = {a["definition"]["activity_id"]: a["lifecycle"] for a in end5["activities"]}
    report.check(
        "impossible case stays visibly unsuccessful",
        life5["demonstrations"] == "failed"
        and life5["closing"] == "failed"
        and end5["budget"]["committed_cents"] == 0,
        json.dumps(life5),
        step=6,
    )
    report.shot(mod, "09_dev05_end_full", full=True)

    # 9. dev06: the status service does not answer; the board shows that outcome as it is.
    load_case(mod, "dev06")
    mod.get_by_role("button", name="Run deterministic policy").click()
    poll(
        lambda: api(base, "api/state", mtoken),
        lambda s: any(c["envelope_status"] == "unavailable" for c in s["status_checks"]),
    )
    # The button reads "Running policy…" until the run returns; then one board poll.
    expect(mod.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=20000)
    mod.wait_for_timeout(int(2 * POLL_S * 1000))
    s6 = api(base, "api/state", mtoken)
    unavailable = [c for c in s6["status_checks"] if c["envelope_status"] == "unavailable"]
    checks6 = mod.locator("#status-checks")
    shown = checks6.get_by_text(UNAVAILABLE, exact=False).count()
    checks_text = checks6.inner_text()
    report.check(
        "status query shows the unavailable outcome as it is (dev06)",
        bool(unavailable)
        and shown == len(unavailable)
        and all(c["observation_id"] is None for c in unavailable)
        and all(c["error_code"] is None or c["error_code"] in checks_text for c in unavailable),
        f"API: {len(unavailable)} unavailable of {len(s6['status_checks'])} status queries "
        f"({', '.join(sorted({str(c['error_code']) for c in unavailable}))}); board: {shown}",
        step=3,
    )
    checks6.scroll_into_view_if_needed()
    report.shot(mod, "09b_dev06_status_unavailable")

    # 10. dev02: prepare, ask, organizer authorizes from its own session, commit.
    load_case(mod, "dev02")
    mod.get_by_role("button", name="Run deterministic policy").click()
    expect(mod.get_by_role("heading", name="Applied (1)")).to_be_visible(timeout=15000)  # the hold
    org = join(browser, mod, "organizer_demo", base, report)
    org.wait_for_timeout(2000)
    report.shot(org, "10_organizer_sees_request_full", full=True)
    approve = org.get_by_role("button", name="Approve: raise the limit to $35.00")
    report.check("organizer sees the authorization request", approve.count() > 0)
    approve.click()
    confirm = org.get_by_role("button", name="Confirm", exact=False)
    if confirm.count():
        confirm.first.click()
    org.wait_for_timeout(2000)
    mod.get_by_role("button", name="Run deterministic policy").click()
    mod.wait_for_timeout(3000)
    s2 = api(base, "api/state", mtoken)
    report.check(
        "authorized paid backup booking committed once",
        s2["budget"]["committed_cents"] == 3500
        and len(s2["commitments"]) == 1
        and s2["budget"]["reserved_cents"] == 0,
        json.dumps(s2["budget"]),
        step=5,
    )
    report.shot(mod, "11_dev02_committed_full", full=True)

    # 11. Presentation and laptop sizes.
    for w, h in ((1920, 1080), (1280, 800)):
        mod.set_viewport_size({"width": w, "height": h})
        mod.wait_for_timeout(500)
        report.shot(mod, f"12_board_{w}x{h}")
        overflow = mod.evaluate(
            "() => document.documentElement.scrollWidth > window.innerWidth + 1"
        )
        report.check(f"no horizontal overflow at {w}px", not overflow)
    report.check(
        "no page errors", errors == [], f"{len(errors)} page errors: {json.dumps(errors[:3])}"
    )

    codes = sum(1 for label, _ in report.secrets if label.startswith("join code"))
    tokens = sum(1 for label, _ in report.secrets if label.startswith("session token"))
    report.check(
        "no join code or session token in the visible text at any screenshot",
        report.exposed == [] and codes >= 3 and tokens >= 4,
        f"{len(report.shots)} screenshots; {codes} join codes, {tokens} session tokens and the "
        f"moderator code checked; {report.masked} join links masked; exposed: {report.exposed}",
    )
    missing = [s["step"] for s in report.workflow() if not s["passed"]]
    report.check(
        "every step of the minimum visible workflow ran with passing checks",
        missing == [],
        f"steps without a passing record: {missing}" if missing else f"steps 1-{len(WORKFLOW)}",
    )


def _status(base: str, path: str, token: str) -> int:
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return run(Path(parser.parse_args().out))


if __name__ == "__main__":
    sys.exit(main())
