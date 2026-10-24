"""Browser walkthrough of the Wave 1 board against a real server (Playwright, Chromium).

Not part of the default pytest run. Usage (from apps/plan_b, after `npm run build` in web/):

    uv run python tests/e2e/walkthrough.py --out <dir>

It starts `plan-b serve` on a free port with a fresh state directory, drives separate browser
contexts for the moderator, participants and organizer (each a distinct scoped session), checks
what the page shows against fresh API reads, and writes screenshots plus a JSON report of every
assertion to <dir>. Exit code 0 only if every assertion held.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect, sync_playwright

APP = Path(__file__).resolve().parents[2]
CODE = "walkthrough-moderator-code"


class Report:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.checks: list[dict[str, Any]] = []
        self.shots: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"check": name, "passed": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail else ""))

    def shot(self, page: Page, name: str, *, full: bool = False) -> None:
        path = self.out / f"{name}.png"
        page.screenshot(path=str(path), full_page=full)
        self.shots.append(path.name)


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


def token_of(page: Page) -> str:
    raw = page.evaluate("() => sessionStorage.getItem('planb.session')")
    data = json.loads(raw)
    return str(data["token"] if isinstance(data, dict) else data)


def sign_in_moderator(browser: Browser, base: str, size: dict[str, int]) -> Page:
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


def join(browser: Browser, moderator: Page, principal: str, base: str) -> Page:
    row = moderator.locator("li", has_text=principal).first
    row.get_by_role("button", name="Issue join code").click()
    link = row.locator("a[href*='#/join/']").first
    expect(link).to_be_visible()
    href = link.get_attribute("href") or ""
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(href if href.startswith("http") else base + href[href.index("#") :])
    expect(
        page.get_by_role("heading", name="Your role").or_(
            page.get_by_role("heading", name="Organizer controls")
        )
    ).to_be_visible(timeout=10000)
    return page


def wait_for_clock(base: str, token: str, iso: str, timeout_s: float = 90.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while True:
        state = api(base, "api/state", token)
        if state["clock"] >= iso or time.time() > deadline:
            return dict(state)
        time.sleep(0.5)


def header_revision(page: Page) -> str:
    return page.locator("text=STATE REVISION").first.locator("xpath=..").inner_text()


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
            walkthrough(browser, base, report)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    passed = all(c["passed"] for c in report.checks)
    (out / "walkthrough_report.json").write_text(
        json.dumps(
            {
                "base_url_kind": "local plan-b serve on a free port with a fresh state directory",
                "browser": "Chromium (Playwright)",
                "passed": passed,
                "checks": report.checks,
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

    # 1. Load dev01: goal, schedule, mode label, clock in the event timezone.
    load_case(mod, "dev01")
    head = mod.locator("header").first.inner_text()
    report.check(
        "header shows product, sandbox and mode labels",
        all(
            s in head
            for s in ("Plan B: The Show Must Go On", "Fictional sandbox", "Deterministic policy")
        ),
        head[:120],
    )
    report.check(
        "scenario clock 16:40 in America/New_York", "16:40" in head and "America/New_York" in head
    )
    report.check("goal and public deadline visible", "Public deadline" in head and "18:00" in head)
    report.shot(mod, "01_loaded_dev01")
    report.shot(mod, "01_loaded_dev01_full", full=True)
    mtoken = token_of(mod)

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
    )
    page_text = mod.locator("body").inner_text()
    report.check(
        "receipt shown on the board matches the API receipt", applied[0]["receipt_id"] in page_text
    )
    report.check(
        "status query result shown with its reported ETA",
        "Answered" in page_text and "17:25" in page_text,
    )
    report.check(
        "alternatives show feasible and rejected candidates",
        "Swap demonstrations and skills exchange" in page_text
        and "Rejected alternatives (" in page_text,
    )
    report.shot(mod, "02_policy_verified_and_swapped_full", full=True)
    mod.get_by_role("heading", name="Before and after", exact=True).scroll_into_view_if_needed()
    report.shot(mod, "02b_before_after")
    mod.get_by_text("Rejected alternatives (", exact=False).first.click()  # expand the details
    mod.get_by_role("heading", name="Alternatives", exact=True).scroll_into_view_if_needed()
    report.shot(mod, "02c_alternatives")

    # 3. Facilitator checks in from a separate scoped session; the moderator tab sees it.
    fac = join(browser, mod, "participant_facilitator", base)
    fac_token = token_of(fac)
    fac_head = fac.locator("header").first.inner_text()
    report.check(
        "participant tab is a distinct scoped session",
        "participant_facilitator" in fac_head or "Skills facilitator" in fac_head,
        fac_head[:120],
    )
    report.check(
        "no token rendered in the page", token_of(fac) not in fac.locator("body").inner_text()
    )
    fac.get_by_role("button", name="Check in").click()
    expect(fac.get_by_text("Confirmed", exact=False).first).to_be_visible(timeout=10000)
    report.shot(fac, "03_participant_checked_in")
    fac.get_by_role("button", name="Check in").click()
    expect(fac.get_by_text("DUPLICATE_CHECK_IN", exact=False).first).to_be_visible(timeout=10000)
    report.check("duplicate check-in shown as rejected", True)
    report.shot(fac, "04_duplicate_check_in_rejected")
    mod.wait_for_timeout(2500)  # one polling interval
    rr = (
        mod.get_by_role("heading", name="Role readiness", exact=True)
        .locator("xpath=..")
        .inner_text()
    )
    report.check(
        "moderator tab observes the persisted check-in by polling",
        "Checked in" in rr and "facilitator" in rr.lower(),
        rr[:200],
    )

    # 4. Presenter checks in; run to the end with the policy.
    pres = join(browser, mod, "participant_presenter", base)
    pres.get_by_role("button", name="Check in").click()
    expect(pres.get_by_text("Confirmed", exact=False).first).to_be_visible(timeout=10000)
    mod.get_by_label("Minutes").fill("80")
    mod.get_by_role("button", name="Run 80 minutes with policy").click()
    final = wait_for_clock(base, mtoken, "2026-11-05T23:00:00Z")
    mod.wait_for_timeout(2500)  # let the board poll the final state
    lifecycles = {a["definition"]["activity_id"]: a["lifecycle"] for a in final["activities"]}
    report.check(
        "all required activities completed (fresh API read)",
        set(lifecycles.values()) == {"completed"},
        json.dumps(lifecycles),
    )
    report.check(
        "arrival observed before demonstrations started",
        any(o["channel"] == "arrival_record" for o in final["observations"]),
    )
    report.shot(mod, "05_dev01_completed_full", full=True)
    report.shot(mod, "05_dev01_completed")

    # 6. Export the executed run and replay it read-only.
    mod.get_by_role("button", name="Export trace").click()
    mod.wait_for_timeout(1500)
    posts: list[str] = []
    replay = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    replay.on("request", lambda r: posts.append(r.url) if r.method != "GET" else None)
    replay.goto(base + "#/replay")
    replay.wait_for_timeout(1000)
    replay.get_by_role("button", name=".json").first.click()
    replay.wait_for_timeout(1500)
    text = replay.locator("body").inner_text()
    report.check("replay shows the persistent Recorded replay label", "Recorded replay" in text)
    report.check("replay integrity verified in the browser", "Integrity check passed" in text)
    for _ in range(6):
        replay.keyboard.press("ArrowRight")
    replay.wait_for_timeout(500)
    report.check(
        "replay labels recorded results as not re-queried",
        "not re-queried" in replay.locator("body").inner_text(),
    )
    report.shot(replay, "07_recorded_replay")
    replay.keyboard.press("End")
    replay.wait_for_timeout(500)
    report.shot(replay, "07b_recorded_replay_final_full", full=True)
    report.check("replay issued no POST/PUT/DELETE requests", posts == [], json.dumps(posts))

    # 7. Impossible case: reset to dev05.
    load_case(mod, "dev05")
    reset_state = api(base, "api/state", mtoken)
    report.check(
        "reset created a clean episode",
        reset_state["revision"] == 3
        and reset_state["receipts"] == []
        and reset_state["holds"] == []
        and reset_state["episode_id"] != final["episode_id"],
    )
    report.check(
        "old participant session rejected after reset", _status(base, "api/state", fac_token) == 401
    )
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
    )
    report.shot(mod, "09_dev05_end_full", full=True)

    # 8. dev02: prepare, ask, organizer authorizes from its own session, commit.
    load_case(mod, "dev02")
    mod.get_by_role("button", name="Run deterministic policy").click()
    expect(mod.get_by_role("heading", name="Applied (1)")).to_be_visible(timeout=15000)  # the hold
    org = join(browser, mod, "organizer_demo", base)
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
    )
    report.shot(mod, "11_dev02_committed_full", full=True)

    # 9. Presentation and laptop sizes.
    for w, h in ((1920, 1080), (1280, 800)):
        mod.set_viewport_size({"width": w, "height": h})
        mod.wait_for_timeout(500)
        report.shot(mod, f"12_board_{w}x{h}")
        overflow = mod.evaluate(
            "() => document.documentElement.scrollWidth > window.innerWidth + 1"
        )
        report.check(f"no horizontal overflow at {w}px", not overflow)
    report.check("no page errors", errors == [], json.dumps(errors[:3]))


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
