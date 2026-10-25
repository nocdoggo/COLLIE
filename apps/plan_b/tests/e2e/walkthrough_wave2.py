"""Browser walkthrough of the Wave 2 board against a real server (Playwright, Chromium).

Not part of the default pytest run. Usage (from apps/plan_b, after `npm run build` in web/):

    uv run python tests/e2e/walkthrough_wave2.py --out <dir>

Like tests/e2e/walkthrough.py (whose helpers it reuses), it starts `plan-b serve` on a free port
with a fresh state directory (removed afterwards), drives separate browser contexts for the
moderator, the pantry staff, a participant and the organizer (each a distinct scoped session),
checks what the page shows against fresh API reads, and writes screenshots plus a JSON report of
every assertion to <dir>. Exit code 0 only if every assertion held.

Three flows, each check naming its flow (``flow``):

* pantry: load the pantry case; the deterministic pantry policy holds the partner kits; the staff
  tab records the handoff; the policy commits the kits; the staff tab records the distribution at
  the deadline; the supply gap and the unfulfilled target move as the plan says (16/40, 16/40,
  0/40, 0/40, 0/0); the trace replays with its pantry board.
* community: load the skills case; the peer lead's own check-in narrows their availability, the
  board shows it, and the policy then re-plans; the kit steward's structured offer activates the
  preconfigured backup kit without a hold or spend; the trace replays.
* policy switch: the deterministic label shows; selecting the live agent shows its label (with
  the configured model id) in the moderator panel, the header and a role tab. No live run is
  started, and the check confirms that no model call was made.

Screenshots mask every join link, and a check asserts that no issued join code and no session
token was in the visible page text at any screenshot.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from walkthrough import (  # noqa: E402 - the Wave 1 walkthrough's helpers, reused as they are
    APP,
    CODE,
    POLL_S,
    Report,
    _status,
    api,
    free_port,
    load_case,
    local_time,
    poll,
    quote,
    readiness_of,
    seconds_until,
    sign_in_moderator,
    stop,
    token_of,
)

FLOWS = {
    "pantry": "Pantry: staff record the handoff and the distribution; the counters move as planned",
    "community": "Community: a participant's own check-in changes the board and the plan",
    "policy_switch": "Moderator policy switch: deterministic and live labels (no live model call)",
}
DEADLINE = "2026-11-09T18:40:00Z"  # pantry service deadline, 13:40 America/New_York
OFFER_TEXT = "I can bring the registered backup learning kit; it is complete."


class Wave2Report(Report):
    def check(
        self,
        name: str,
        ok: bool,
        detail: str = "",
        *,
        flow: str | None = None,
        step: int | None = None,
    ) -> None:
        super().check(name, ok, detail, step=step)
        if flow is not None:
            self.checks[-1]["flow"] = flow

    def flows(self) -> list[dict[str, Any]]:
        out = []
        for key, title in FLOWS.items():
            mine = [c for c in self.checks if c.get("flow") == key]
            out.append(
                {
                    "flow": key,
                    "title": title,
                    "checks": [c["check"] for c in mine],
                    "passed": bool(mine) and all(c["passed"] for c in mine),
                }
            )
        return out


def join_as(
    browser: Browser, moderator: Page, principal: str, base: str, report: Report, heading: str
) -> Page:
    """Issue a join code for one principal and open its tab (a distinct scoped session)."""
    row = moderator.locator("li", has_text=principal).first
    row.get_by_role("button", name="Issue join code").click()
    link = moderator.locator(f"a[data-join-link='{principal}']")
    expect(link).to_be_visible()
    href = link.get_attribute("href") or ""
    report.secret(f"join code for {principal}", urllib.parse.unquote(href.split("#/join/", 1)[1]))
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(href if href.startswith("http") else base + href[href.index("#") :])
    expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible(timeout=10000)
    report.secret(f"session token of {principal}", token_of(page))
    return page


def confirm(page: Page, label: str, timeout_s: float = 10.0) -> None:
    """Wait until this tab's submission whose label holds ``label`` is confirmed in a fresh state
    read; on a timeout, fail with what that submission shows (its receipt or its refusal)."""
    item = page.locator("li.submission", has_text=label).first
    try:
        expect(item).to_contain_text("Confirmed in the current state", timeout=timeout_s * 1000)
    except AssertionError as exc:
        shown = item.inner_text() if item.count() else "no such submission"
        raise AssertionError(f"{label}: {' '.join(shown.split())[:600]}") from exc


def counter(page: Page, name: str) -> str:
    """The value of one PantryBoard counter (components/PantryBoard.tsx data-counter)."""
    return (
        page.locator(f"#pantry-board [data-counter='{name}'] .counter-value").inner_text().strip()
    )


def stock_row(page: Page, resource_id: str) -> dict[str, int]:
    """On hand, reserved, available, expected and distributed of one pool, as the board shows."""
    row = page.locator(f"#pantry-board tr[data-stock='{resource_id}']")
    out = {}
    for key in ("on_hand", "reserved", "available", "expected", "distributed"):
        text = row.locator(f"td[data-quantity='{key}']").inner_text()
        out[key] = int(re.match(r"\d+", text.strip()).group(0))  # type: ignore[union-attr]
    return out


def api_row(state: dict[str, Any], resource_id: str) -> dict[str, int]:
    b = next(x for x in state["stock"]["balances"] if x["resource_id"] == resource_id)
    return {
        "on_hand": b["on_hand_quantity"],
        "reserved": b["reserved_quantity"],
        "available": b["available_quantity"],
        "expected": b["expected_quantity"],
        "distributed": b["distributed_quantity"],
    }


def api_counters(state: dict[str, Any]) -> tuple[int, int]:
    service = state["stock"]["service"][0]
    return service["supply_gap_quantity"], service["unfulfilled_quantity"]


def board_matches(
    page: Page, state: dict[str, Any], timeout_s: float = 3 * POLL_S
) -> tuple[bool, str]:
    """Whether the board's counters and pools show the fresh API read (after its next poll)."""
    gap, unfulfilled = api_counters(state)
    unit = "standard kits"
    expect(page.locator("#pantry-board [data-counter='supply_gap'] .counter-value")).to_have_text(
        f"{gap} {unit}", timeout=timeout_s * 1000
    )
    expect(page.locator("#pantry-board [data-counter='unfulfilled'] .counter-value")).to_have_text(
        f"{unfulfilled} {unit}", timeout=timeout_s * 1000
    )
    shown = {rid: stock_row(page, rid) for rid in ("pantry_stock", "partner_stock")}
    wanted = {rid: api_row(state, rid) for rid in ("pantry_stock", "partner_stock")}
    detail = (
        f"board gap {counter(page, 'supply_gap')}, unfulfilled {counter(page, 'unfulfilled')}; "
        f"pools {json.dumps(shown)}"
    )
    return shown == wanted, detail


# The deepest elements reaching past the viewport's right edge (for a failed overflow check).
OVERFLOWING = """() => [...document.querySelectorAll('body *')]
  .filter((e) => e.getBoundingClientRect().right > window.innerWidth + 1)
  .filter((e) => e.tagName === 'SELECT' || ![...e.children].some(
    (c) => c.getBoundingClientRect().right > window.innerWidth + 1))
  .slice(0, 5)
  .map((e) => `${e.tagName.toLowerCase()}${e.id ? '#' + e.id : ''}.${e.className}`
    + ` (${Math.round(e.getBoundingClientRect().right)}px)`)"""


def overflow_of(page: Page) -> tuple[bool, str]:
    wide = bool(page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1"))
    return wide, json.dumps(page.evaluate(OVERFLOWING)) if wide else ""


def minutes_until(clock: str, target: str) -> int:
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return int((parse(target) - parse(clock)).total_seconds() // 60)


def replay_trace(browser: Browser, base: str, name: str) -> tuple[Page, list[str], str]:
    """Open one exported trace in a fresh replay tab; returns the page, its non-GET requests and
    its text once the browser's integrity check settled."""
    posts: list[str] = []
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.on("request", lambda r: posts.append(r.url) if r.method != "GET" else None)
    page.goto(base + "#/replay")
    page.get_by_role("button", name=name).click()
    page.wait_for_function(
        "() => { const b = document.querySelector('.replay-integrity[data-integrity]');"
        " return b !== null && b.getAttribute('data-integrity') !== 'checking'; }",
        timeout=20000,
    )
    return page, posts, page.locator("body").inner_text()


def export(mod: Page, base: str, token: str) -> str:
    executed = api(base, "api/state", token)
    name = f"{executed['episode_id']}_rev{executed['revision']}.json"
    mod.get_by_role("button", name="Export trace").click()
    poll(lambda: [r["name"] for r in api(base, "api/replays")], lambda names: name in names)
    return name


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report = Wave2Report(out)
    port = free_port()
    base = f"http://127.0.0.1:{port}/"
    var = Path(tempfile.mkdtemp(prefix="planb_e2e2_"))
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
    (out / "walkthrough_wave2_report.json").write_text(
        json.dumps(
            {
                "base_url_kind": "local plan-b serve on a free port with a fresh state directory",
                "browser": "Chromium (Playwright)",
                "passed": passed,
                "checks": report.checks,
                "flows": report.flows(),
                "screenshots": report.shots,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"{sum(c['passed'] for c in report.checks)}/{len(report.checks)} checks passed")
    return 0 if passed else 1


def walkthrough(browser: Browser, base: str, report: Wave2Report) -> None:
    mod = sign_in_moderator(browser, base, {"width": 1440, "height": 900})
    errors: list[str] = []
    mod.on("pageerror", lambda e: errors.append(str(e)))
    mtoken = token_of(mod)
    report.secret("session token of the moderator", mtoken)

    pantry_flow(browser, base, report, mod, mtoken, errors)
    community_flow(browser, base, report, mod, mtoken, errors)
    policy_switch_flow(browser, base, report, mod, mtoken)

    for w, h in ((1920, 1080), (1280, 800)):
        mod.set_viewport_size({"width": w, "height": h})
        mod.wait_for_timeout(500)
        wide, where = overflow_of(mod)
        report.check(f"no horizontal overflow at {w}px", not wide, where)
    report.check(
        "no page errors", errors == [], f"{len(errors)} page errors: {json.dumps(errors[:3])}"
    )
    codes = sum(1 for label, _ in report.secrets if label.startswith("join code"))
    tokens = sum(1 for label, _ in report.secrets if label.startswith("session token"))
    report.check(
        "no join code or session token in the visible text at any screenshot",
        report.exposed == [] and codes >= 4 and tokens >= 5,
        f"{len(report.shots)} screenshots; {codes} join codes, {tokens} session tokens and the "
        f"moderator code checked; {report.masked} join links masked; exposed: {report.exposed}",
    )
    missing = [f["flow"] for f in report.flows() if not f["passed"]]
    report.check(
        "every Wave 2 flow ran with passing checks",
        missing == [],
        f"flows without a passing record: {missing}" if missing else ", ".join(FLOWS),
    )


def pantry_flow(
    browser: Browser, base: str, report: Wave2Report, mod: Page, mtoken: str, errors: list[str]
) -> None:
    flow = "pantry"
    load_case(mod, "pantry_dev01")
    s0 = api(base, "api/state", mtoken)
    head = mod.locator("header").first.inner_text()
    report.check(
        "pantry case loaded on its own scenario under the deterministic policy",
        s0["profile_id"] == "pantry_continuity"
        and s0["scenario_id"] == "dev_fixture_03"
        and "Deterministic policy" in head,
        quote(head, "Deterministic policy") + f" · {s0['scenario_id']} ({s0['profile_id']})",
        flow=flow,
    )
    ok, detail = board_matches(mod, s0)
    report.check(
        "initial counters and pools: gap 16, unfulfilled 40; pantry 24, partner 16, expected 20",
        ok
        and api_counters(s0) == (16, 40)
        and api_row(s0, "pantry_stock")["on_hand"] == 24
        and api_row(s0, "pantry_stock")["expected"] == 20
        and api_row(s0, "partner_stock")["on_hand"] == 16,
        detail,
        flow=flow,
    )
    mod.locator("#pantry-board").scroll_into_view_if_needed()
    report.shot(mod, "w2_01_pantry_loaded")

    staff = join_as(browser, mod, "fictional_staff", base, report, "Staff actions")
    staff.on("pageerror", lambda e: errors.append(str(e)))
    staff_token = token_of(staff)
    staff_head = staff.locator("header").first.inner_text()
    report.check(
        "staff tab is its own scoped session with the staff-only tools",
        "fictional_staff" in staff_head
        and staff.get_by_role("tab", name="Staff actions").get_attribute("aria-selected") == "true"
        and set(api(base, "api/participation/me", staff_token)["staff_tools"])
        == {"record_stock_receipt", "record_distribution"},
        quote(staff_head, "fictional_staff"),
        flow=flow,
    )

    # 1. The pantry policy verifies, holds the 16 partner kits for a staff handoff and asks.
    mod.get_by_role("button", name="Run deterministic policy").click()
    s1 = poll(
        lambda: api(base, "api/state", mtoken),
        lambda s: any(t["status"] == "open" for t in s["stock"]["handoff_tasks"]),
    )
    expect(mod.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=20000)
    ok, detail = board_matches(mod, s1)
    task = next(t for t in s1["stock"]["handoff_tasks"] if t["status"] == "open")
    report.check(
        "policy holds 16 partner kits: partner reserved 16, available 0; gap 16, unfulfilled 40",
        ok
        and api_counters(s1) == (16, 40)
        and api_row(s1, "partner_stock")
        == {**api_row(s1, "partner_stock"), "reserved": 16, "available": 0}
        and api_row(s1, "partner_stock")["on_hand"] == 16
        and task["requested_quantity"] == 16,
        detail,
        flow=flow,
    )
    decisions = mod.locator("#decisions").inner_text()
    report.check(
        "decision cards narrate the hold and the ask with the policy that ran",
        "Asked staff to hand off 16 units" in decisions
        and "pantry-rules/1.1.0" in decisions
        and "Prepare" in decisions,
        quote(decisions, "pantry-rules/1.1.0", "partner_stock"),
        flow=flow,
    )
    report.shot(mod, "w2_02_pantry_handoff_requested_full", full=True)

    # 2. Staff record the handoff (record_stock_receipt with the held source).
    # The staff tab offers the task once its next state read shows the hold.
    expect(staff.get_by_label("What arrived")).to_have_value(
        f"hold:{task['hold_id']}", timeout=3 * POLL_S * 1000
    )
    receipt_button = staff.get_by_role("button", name="Record stock receipt", exact=True)
    expect(receipt_button).to_be_enabled(timeout=3 * POLL_S * 1000)
    chosen = staff.get_by_label("What arrived").input_value()
    receipt_reference = staff.get_by_label("Receipt reference", exact=False).input_value()
    receipt_button.click()
    confirm(staff, f"Receipt {receipt_reference}")
    s2 = api(base, "api/state", mtoken)
    rec = s2["stock"]["receipts"]
    report.check(
        "staff tab recorded the handoff: one receipt of 16 from the held partner pool",
        chosen == f"hold:{task['hold_id']}"
        and len(rec) == 1
        and rec[0]["quantity"] == 16
        and rec[0]["source_hold_id"] == task["hold_id"]
        and rec[0]["actor_id"] == "fictional_staff",
        f"{chosen}; "
        + json.dumps([(r["receipt_reference"], r["quantity"], r["actor_id"]) for r in rec]),
        flow=flow,
    )
    ok, detail = board_matches(mod, s2)
    report.check(
        "after the handoff: pantry 40, partner 0, expected 20 unreceived; gap 0, unfulfilled 40",
        ok
        and api_counters(s2) == (0, 40)
        and api_row(s2, "pantry_stock")["on_hand"] == 40
        and api_row(s2, "pantry_stock")["expected"] == 20
        and api_row(s2, "partner_stock")["on_hand"] == 0,
        detail,
        flow=flow,
    )
    report.shot(staff, "w2_03_staff_recorded_handoff")

    # 3. The policy reserves the 40 local kits and applies the plan: committed, not served.
    mod.get_by_role("button", name="Run deterministic policy").click()
    s3 = poll(lambda: api(base, "api/state", mtoken), lambda s: bool(s["stock"]["allocations"]))
    expect(mod.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=20000)
    ok, detail = board_matches(mod, s3)
    service = s3["stock"]["service"][0]
    report.check(
        "plan applied: 40 committed and reserved; gap 0, unfulfilled still 40, 0 achieved",
        ok
        and api_counters(s3) == (0, 40)
        and service["committed_quantity"] == 40
        and service["on_time_quantity"] == 0
        and api_row(s3, "pantry_stock")["reserved"] == 40,
        detail + f"; achieved {counter(mod, 'achieved')}",
        flow=flow,
    )

    # 4. Advance to the 13:40 deadline (inclusive); staff record the distribution.
    minutes = minutes_until(s3["clock"], DEADLINE)
    mod.get_by_label("Minutes").fill(str(minutes))
    mod.get_by_role("button", name=f"Run {minutes} minutes with policy").click()
    poll(lambda: api(base, "api/state", mtoken), lambda s: s["clock"] >= DEADLINE, 90)
    expect(mod.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=30000)
    distribute = staff.get_by_role("button", name="Record distribution", exact=True)
    expect(distribute).to_be_enabled(timeout=3 * POLL_S * 1000)
    # Only once the staff tab has read the 13:40 state does it offer all 40 (staffed capacity).
    expect(staff.get_by_text("Recorded now at 13:40", exact=False)).to_be_visible(
        timeout=3 * POLL_S * 1000
    )
    expect(staff.get_by_label("Quantity distributed", exact=False)).to_have_value(
        "40", timeout=3 * POLL_S * 1000
    )
    expect(
        staff.get_by_text("counts on time (deadline 13:40, inclusive)", exact=False)
    ).to_be_visible(timeout=3 * POLL_S * 1000)
    quantity = staff.get_by_label("Quantity distributed", exact=False).input_value()
    reference = staff.get_by_label("Distribution reference", exact=False).input_value()
    distribute.click()
    confirm(staff, f"Distribution {reference}")
    s4 = poll(lambda: api(base, "api/state", mtoken), lambda s: bool(s["stock"]["distributions"]))
    dist = s4["stock"]["distributions"]
    report.check(
        "staff tab recorded the distribution of 40 at 13:40, on time",
        quantity == "40"
        and len(dist) == 1
        and dist[0]["quantity"] == 40
        and dist[0]["on_time"] is True
        and local_time(dist[0]["at"], s4["timezone"]) == "13:40",
        json.dumps(
            [(d["distribution_reference"], d["quantity"], d["on_time"], d["at"]) for d in dist]
        ),
        flow=flow,
    )
    ok, detail = board_matches(mod, s4)
    expect(mod.locator("#pantry-board [data-counter='achieved'] .counter-value")).to_have_text(
        "40 of 40 on time", timeout=3 * POLL_S * 1000
    )
    report.check(
        "after distribution: gap 0, unfulfilled 0, 40 of 40 on time; both pools 0, expected 20",
        ok
        and api_counters(s4) == (0, 0)
        and api_row(s4, "pantry_stock")["on_hand"] == 0
        and api_row(s4, "partner_stock")["on_hand"] == 0
        and api_row(s4, "pantry_stock")["expected"] == 20
        and all(b["conserved"] for b in s4["stock"]["balances"]),
        detail + f"; achieved {counter(mod, 'achieved')}",
        flow=flow,
    )
    report.shot(staff, "w2_04_staff_recorded_distribution")
    mod.locator("#pantry-board").scroll_into_view_if_needed()
    report.shot(mod, "w2_05_pantry_distributed")
    staff.set_viewport_size({"width": 1280, "height": 800})
    staff.wait_for_timeout(300)
    wide, where = overflow_of(staff)
    report.check("staff tab has no horizontal overflow at 1280px", not wide, where, flow=flow)

    # 5. Replay the pantry trace read-only.
    name = export(mod, base, mtoken)
    replay, posts, text = replay_trace(browser, base, name)
    replay.get_by_role("button", name="Final recorded state").click()
    final_text = replay.locator("body").inner_text()
    report.check(
        "pantry trace replays: integrity passed, pantry board and policy label shown",
        "Recorded replay" in text
        and "Integrity check passed" in text
        and replay.locator(".replay-integrity").get_attribute("data-integrity") == "passed"
        and "Stock and service" in final_text
        and "40 of 40 on time" in final_text
        and "Deterministic policy" in final_text,
        name,
        flow=flow,
    )
    report.check(
        "pantry replay issued no POST/PUT/DELETE requests",
        posts == [],
        json.dumps(posts),
        flow=flow,
    )
    replay.locator("#pantry-board").scroll_into_view_if_needed()
    report.shot(replay, "w2_06_pantry_replay")
    replay.context.close()
    staff.context.close()


def community_flow(
    browser: Browser, base: str, report: Wave2Report, mod: Page, mtoken: str, errors: list[str]
) -> None:
    flow = "community"
    load_case(mod, "skills_dev01")
    s0 = api(base, "api/state", mtoken)
    tz = s0["timezone"]
    plan0 = {a["activity_id"]: a for a in s0["plan"]["assignments"]}
    report.check(
        "skills case loaded on its own scenario through the event adapter, without a pantry board",
        s0["scenario_id"] == "dev_fixture_02"
        and s0["profile_id"] == "community_skills_exchange"
        and s0.get("stock") is None
        and mod.locator("#pantry-board").count() == 0,
        f"{s0['scenario_id']} ({s0['profile_id']}); peer exchange at "
        f"{local_time(plan0['peer_exchange']['start'], tz)}",
        flow=flow,
    )
    peer = join_as(browser, mod, "participant_peer_lead", base, report, "Your role")
    peer.on("pageerror", lambda e: errors.append(str(e)))
    alias = peer.locator("[data-alias]").inner_text()
    report.check(
        "participation view shows the volunteer's alias and the role's declared window",
        "Peer exchange facilitator" in alias
        and "participant_peer_lead" in alias
        and "09:30–12:00" in alias,
        quote(alias, "Peer exchange facilitator", "09:30–12:00"),
        flow=flow,
    )
    before = readiness_of(mod, "peer_lead").inner_text()
    peer.get_by_label("Available until", exact=False).select_option(label="11:05")
    peer.get_by_role("button", name="Check in").click()
    confirm(peer, "Check in as")
    s1 = api(base, "api/state", mtoken)
    latest = [c for c in s1["checkins"] if c["resource_id"] == "peer_lead"][-1]
    seen = seconds_until(readiness_of(mod, "peer_lead"), "(participant session)", 2 * POLL_S)
    after = readiness_of(mod, "peer_lead").inner_text()
    report.check(
        "the peer lead's own check-in until 11:05 changes the moderator's board",
        "No check-in yet" in before
        and seen is not None
        and local_time(latest["available"]["end"], tz) == "11:05"
        and latest["principal_id"] == "participant_peer_lead"
        and "11:05" in after
        and "(participant session)" in after,
        f"before: {quote(before, '(peer_lead)')}; after: {quote(after, '(peer_lead)', '11:05')}",
        flow=flow,
    )
    report.shot(peer, "w2_07_participant_checked_in")
    mod.get_by_role("button", name="Run deterministic policy").click()
    s2 = poll(lambda: api(base, "api/state", mtoken), lambda s: s["plan"]["plan_version"] >= 2)
    expect(mod.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=20000)
    mod.wait_for_timeout(int(2 * POLL_S * 1000))
    plan2 = {a["activity_id"]: a for a in s2["plan"]["assignments"]}
    schedule = mod.locator("#schedule").inner_text()
    report.check(
        "the check-in made keep infeasible; the policy applied the peer exchange swap",
        s2["plan"]["plan_version"] == 2
        and local_time(plan2["peer_exchange"]["start"], tz) == "10:40"
        and plan2["peer_exchange"]["end"] <= latest["available"]["end"]
        and "Swap practice and peer exchange" in mod.locator("body").inner_text()
        and "10:40" in schedule,
        f"plan v{s2['plan']['plan_version']}: peer exchange "
        f"{local_time(plan2['peer_exchange']['start'], tz)}-"
        f"{local_time(plan2['peer_exchange']['end'], tz)} (fresh API read)",
        flow=flow,
    )
    report.shot(mod, "w2_08_community_replanned_full", full=True)

    # The kit steward's structured offer activates the preconfigured backup kit, nothing else.
    steward = join_as(browser, mod, "participant_kit_steward", base, report, "Your role")
    steward.on("pageerror", lambda e: errors.append(str(e)))
    expect(steward.get_by_role("heading", name="Offer a resource")).to_be_visible(timeout=10000)
    budget = s2["budget"]
    holds = len(s2["holds"])
    steward.get_by_label("I confirm the registered terms", exact=False).check()
    steward.get_by_label("Your offer").fill(OFFER_TEXT)
    steward.get_by_role("button", name="Send offer").click()
    confirm(steward, "Offer ")
    s3 = api(base, "api/state", mtoken)
    kit = next(
        r for r in s3["resources"] if r["definition"]["resource_id"] == "backup_learning_kit"
    )
    offer = next(o for o in s3["observations"] if o["observation"]["text"] == OFFER_TEXT)
    report.check(
        "the steward's offer activates the preconfigured backup kit; no hold, spend or plan change",
        offer["observation"]["kind"] == "resource_offer"
        and kit["status"] in ("available", "expected")
        and kit["status_observation_id"] == offer["observation"]["observation_id"]
        and s3["budget"] == budget
        and len(s3["holds"]) == holds
        and s3["plan"]["plan_version"] == 2,
        f"backup kit {kit['status']} ({kit['status_basis']}, {kit['status_observation_id']}); "
        f"budget {json.dumps(s3['budget'])}",
        flow=flow,
    )
    report.shot(steward, "w2_09_resource_offer_sent")

    name = export(mod, base, mtoken)
    replay, posts, text = replay_trace(browser, base, name)
    replay.get_by_role("button", name="Final recorded state").click()
    final_text = replay.locator("body").inner_text()
    report.check(
        "community trace replays: integrity passed, the check-in and the re-plan shown",
        "Recorded replay" in text
        and "Integrity check passed" in text
        and "Swap practice and peer exchange" in final_text
        and "(participant session)" in final_text
        and "Stock and service" not in final_text,
        name,
        flow=flow,
    )
    report.check(
        "community replay issued no POST/PUT/DELETE requests",
        posts == [],
        json.dumps(posts),
        flow=flow,
    )
    report.shot(replay, "w2_10_community_replay")
    replay.context.close()
    for page in (peer, steward):
        page.context.close()


def policy_switch_flow(
    browser: Browser, base: str, report: Wave2Report, mod: Page, mtoken: str
) -> None:
    flow = "policy_switch"
    load_case(mod, "dev01")
    head = mod.locator("header").first.inner_text()
    panel = mod.locator("#moderator-panel")
    expect(panel.locator("[data-policy-selected='rules']")).to_contain_text(
        "Deterministic policy", timeout=10000
    )
    report.check(
        "deterministic label in the header and the moderator panel; run button names it",
        "Deterministic policy" in head
        and mod.get_by_role("button", name="Run deterministic policy").count() == 1,
        quote(head, "Deterministic policy"),
        flow=flow,
    )
    setting = api(base, "api/moderator/policy", mtoken)
    model_id = setting.get("model_id") or ""
    live_radio = mod.get_by_role("radio", name=re.compile(r"^Live agent"))
    if not setting.get("live_available"):
        report.check(
            "live policy can be selected on this machine",
            False,
            f"live not available: {setting.get('reason')}",
            flow=flow,
        )
        return
    live_radio.click()  # controlled radio: it shows checked once the server confirms
    expect(panel.locator("[data-policy-selected='live']")).to_contain_text(
        f"Live agent · {model_id}", timeout=10000
    )
    expect(mod.locator("header").first).to_contain_text(f"Live agent · {model_id}", timeout=5000)
    head = mod.locator("header").first.inner_text()
    report.check(
        "selecting the live agent shows its label with the configured model id",
        f"Live agent · {model_id}" in head
        and mod.get_by_role("button", name="Run live agent").count() == 1
        and mod.get_by_role("button", name="Run deterministic policy").count() == 0,
        quote(head, "Live agent"),
        flow=flow,
    )
    report.shot(mod, "w2_11_live_policy_selected")
    org = join_as(browser, mod, "organizer_demo", base, report, "Organizer controls")
    expect(org.locator("header").first).to_contain_text("Live agent ·", timeout=3 * POLL_S * 1000)
    org_head = org.locator("header").first.inner_text()
    report.check(
        "a role tab shows the same live label from the server (GET /api/policy)",
        f"Live agent · {model_id}" in org_head,
        quote(org_head, "Live agent"),
        flow=flow,
    )
    report.shot(org, "w2_12_role_tab_live_label")
    org.context.close()
    after = api(base, "api/moderator/policy", mtoken)
    state = api(base, "api/state", mtoken)
    report.check(
        "no live model call was made: no decision, no tool call, zero model calls",
        after["policy"] == "live"
        and after["caps"]["model_calls"] == 0
        and after["caps"]["tool_calls"] == 0
        and after["returned_model_id"] is None
        and state["decisions"] == []
        and after["locked"] is False,
        json.dumps(
            {k: after[k] for k in ("policy", "policy_id", "caps", "locked", "returned_model_id")}
        ),
        flow=flow,
    )
    mod.get_by_role("radio", name=re.compile(r"^Deterministic policy")).click()
    expect(panel.locator("[data-policy-selected='rules']")).to_contain_text(
        "Deterministic policy", timeout=10000
    )
    expect(mod.locator("header").first).to_contain_text("Deterministic policy", timeout=5000)
    report.check(
        "switching back restores the deterministic policy before anything ran",
        api(base, "api/moderator/policy", mtoken)["policy"] == "rules"
        and _status(base, "api/policy", mtoken) == 200,
        flow=flow,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return run(Path(parser.parse_args().out))


if __name__ == "__main__":
    sys.exit(main())
