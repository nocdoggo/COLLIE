"""Keyboard navigation and comprehension (W3.3), in a browser against a real server
(Playwright, Chromium).

Not part of the default pytest run. Usage (from apps/plan_b, after `npm run build` in web/):

    uv run python tests/e2e/keyboard.py --out <dir>

It starts ``plan-b serve`` on 127.0.0.1 with a fresh state directory (stopped and removed
afterwards) and uses only the deterministic policies: no model is called. Pointer clicks are
used for setup only (loading a case, issuing a join code); every check below is reached with the
keyboard (Tab, Shift+Tab, Enter) and compares what the focused page shows with fresh API reads:

* sign-in (the code field is reached by Tab) and the skip link work from the keyboard;
* on the campus board, the current plan, the evidence, the latest decision with its next wake
  and the action status are each reached by Tab, show a visible focus outline and say what the
  API says. The section links work with Enter and with Space, and the section they land on
  shows the outline too;
* a receipt's evidence button, reached by Tab, moves focus to a receipt the API reports;
* Shift+Tab visits the same stops in exactly the reverse order;
* the pantry board's quantities are reached by Tab and keep expected, held, received, committed
  and distributed apart, with the values the API reports for every stock row;
* a second signed-in view of the same episode agrees on the revision and the receipts.

The board has no modal or menu (only native ``<details>``), so there is no Escape check. The
deterministic policy sets no next wake, so the wake text is checked in
``web/tests/keyboard.test.ts`` and here only when the API reports one.

``keyboard_report.json`` lists every check. Exit code 0 only if every check held.
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
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from walkthrough import (  # noqa: E402 - the Wave 1 walkthrough's helpers, reused as they are
    APP,
    CODE,
    POLL_S,
    Report,
    api,
    free_port,
    join,
    load_case,
    local_time,
    poll,
    quote,
    stop,
    token_of,
)

VIEWPORT = {"width": 1440, "height": 900}
MAX_TABS = 400

# What one Tab press reached: the element, its board section and whether a focus ring shows.
# ``order`` numbers each element the first time it is focused, so a cycle is detected even
# among buttons with the same name.
FOCUSED = """() => {
  const el = document.activeElement;
  if (el === null || el === document.body) return null;
  window.__kbdOrder = window.__kbdOrder || new WeakMap();
  window.__kbdNext = window.__kbdNext || 0;
  const again = window.__kbdOrder.has(el);
  if (!again) window.__kbdOrder.set(el, window.__kbdNext++);
  const section = el.closest("section[id]");
  const style = getComputedStyle(el);
  // The board's focus style is a 3px outline (styles.css). A box shadow is not a focus ring:
  // selected tabs carry one at rest.
  const ring = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2;
  const label = el.getAttribute("aria-label") || el.textContent || el.getAttribute("value") || "";
  return {
    tag: el.tagName.toLowerCase(),
    id: el.id || null,
    text: label.replace(/\\s+/g, " ").trim().slice(0, 80),
    section: section ? section.id : null,
    ring,
    again,
  };
}"""

# Start each walk at the skip link, the first focusable element of the page.
FROM_THE_TOP = """() => {
  window.__kbdOrder = new WeakMap();
  window.__kbdNext = 0;
  window.scrollTo(0, 0);
  document.querySelector(".skip-link")?.focus();
}"""


def tab_walk(page: Page, *, backwards: bool = False) -> list[dict[str, Any]]:
    """Tab from the skip link until focus cycles; returns each focus stop once, in order."""
    page.evaluate(FROM_THE_TOP)
    first = page.evaluate(FOCUSED)
    seen: list[dict[str, Any]] = [first] if first is not None else []
    for _ in range(MAX_TABS):
        page.keyboard.press("Shift+Tab" if backwards else "Tab")
        stop_at = page.evaluate(FOCUSED)
        if stop_at is None:
            continue  # focus left the document (browser chrome); the next Tab re-enters it
        if stop_at.pop("again"):
            break
        seen.append(stop_at)
    for s in seen:
        s.pop("again", None)
    return seen


def tab_to(page: Page, label: str, section: str | None) -> bool:
    """Tab from the skip link until the element named ``label`` in ``section`` has focus."""
    page.evaluate(FROM_THE_TOP)
    for _ in range(MAX_TABS):
        page.keyboard.press("Tab")
        here = page.evaluate(FOCUSED)
        if here is None:
            continue
        if here["again"]:
            return False
        if here["text"] == label and here["section"] == section:
            return True
    return False


def jump_by_keyboard(page: Page, label: str, key: str = "Enter") -> str | None:
    """Tab from the skip link to the board's section link ``label``, press ``key`` and return
    the id of the element that then has focus (None if the link was not reached)."""
    if not tab_to(page, label, None):
        return None
    page.keyboard.press(key)
    page.wait_for_timeout(200)
    return str(page.evaluate("() => document.activeElement?.id || ''")) or None


# Whether the element that has focus shows the board's focus outline.
LANDING_RING = """() => {
  const el = document.activeElement;
  if (el === null || el === document.body) return false;
  const style = getComputedStyle(el);
  return style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2;
}"""


def latest_decision(state: dict[str, Any]) -> dict[str, Any]:
    """The decision the board shows as latest: later time, then higher revision, then later."""
    best: dict[str, Any] | None = None
    for d in state["decisions"]:
        if best is None or (d["at"], d["revision"]) >= (best["at"], best["revision"]):
            best = d
    assert best is not None
    return best


def in_section(stops: list[dict[str, Any]], *sections: str) -> list[dict[str, Any]]:
    return [s for s in stops if s["section"] in sections]


def section_text(page: Page, section_id: str) -> str:
    return page.locator(f"section#{section_id}").inner_text()


def sign_in_by_keyboard(browser: Browser, base: str, report: Report) -> Page:
    page = browser.new_context(viewport=VIEWPORT).new_page()  # type: ignore[arg-type]
    page.goto(base)
    page.keyboard.press("Tab")
    first = page.evaluate(FOCUSED)
    report.check(
        "the first Tab stop is the skip link",
        first is not None and "Skip to content" in first["text"],
        json.dumps(first),
    )
    reached = False
    for _ in range(20):
        if (
            page.evaluate(
                "() => document.activeElement?.getAttribute('aria-label') "
                "|| document.activeElement?.labels?.[0]?.textContent || ''"
            ).find("Moderator code")
            >= 0
        ):
            reached = True
            break
        page.keyboard.press("Tab")
    page.keyboard.type(CODE)
    page.keyboard.press("Enter")
    ok = reached
    try:
        expect(page.get_by_role("heading", name="Moderator controls")).to_be_visible(timeout=10000)
    except AssertionError:
        ok = False
    report.check(
        "the moderator signs in with the keyboard only (Tab to the code field, type, Enter)",
        ok,
        f"code field reached by Tab: {reached}",
    )
    return page


def skip_link_moves_focus(page: Page, report: Report) -> None:
    page.evaluate(FROM_THE_TOP)
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    after = page.evaluate(
        "() => ({id: document.activeElement?.id || null, "
        "tag: document.activeElement?.tagName.toLowerCase() || null})"
    )
    report.check(
        "Enter on the skip link moves focus past the header into the content",
        after["id"] == "main",
        json.dumps(after),
    )


def campus(browser: Browser, base: str, report: Report) -> None:
    mod = sign_in_by_keyboard(browser, base, report)
    load_case(mod, "dev01")
    token = token_of(mod)
    skip_link_moves_focus(mod, report)
    # The deterministic policy runs ten scenario minutes: a verified swap, receipts, evidence.
    run = _post(base, "api/moderator/run", token, {"minutes": 10})
    state = poll(
        lambda: api(base, "api/state", token),
        lambda s: s["revision"] == run["revision"],
    )
    mod.wait_for_timeout(int(POLL_S * 2000))
    stops = tab_walk(mod)
    (Path(report.out) / "keyboard_campus_tab_order.json").write_text(
        json.dumps(stops, indent=2) + "\n"
    )
    report.check(
        "Tab reaches the board and every stop shows a visible focus ring",
        len(stops) > 10 and all(s["ring"] for s in stops),
        f"{len(stops)} stops; without a ring: {[s['text'] for s in stops if not s['ring']][:5]}",
    )
    tz = state["timezone"]

    # The current plan.
    plan = in_section(stops, "schedule")
    landed = jump_by_keyboard(mod, "Current plan")
    rings = {"schedule": mod.evaluate(LANDING_RING)}
    schedule = section_text(mod, "schedule")
    starts = [(a["activity_id"], local_time(a["start"], tz)) for a in state["plan"]["assignments"]]
    report.check(
        "the current plan is reached by keyboard (Tab to 'Current plan', Enter)",
        landed == "schedule",
        f"focus on {landed!r}; {len(plan)} Tab stops inside the schedule",
    )
    report.check(
        "the schedule names the plan version and every start time the API reports",
        f"plan version {state['plan']['plan_version']}" in schedule
        and all(t in schedule for _, t in starts),
        f"plan version {state['plan']['plan_version']}; starts {starts}",
    )

    # The evidence.
    evidence = in_section(stops, "status-checks", "observations", "evidence")
    landed = jump_by_keyboard(mod, "Evidence")
    rings["status-checks"] = mod.evaluate(LANDING_RING)
    report.check(
        "the evidence (status checks, incoming updates, raw evidence) is reached by keyboard",
        landed == "status-checks" and bool(evidence),
        f"'Evidence' moves focus to {landed!r}; {len(evidence)} Tab stops in "
        f"{sorted({s['section'] for s in evidence})}",
    )
    spaced = jump_by_keyboard(mod, "Evidence", key="Space")
    report.check(
        "a section link also works with Space",
        spaced == "status-checks",
        f"Space on 'Evidence' moves focus to {spaced!r}",
    )
    checks_text = section_text(mod, "status-checks")
    entities = sorted({c["entity_id"] for c in state["status_checks"] if c["entity_id"]})
    report.check(
        "the status checks show every entity the API reports as checked",
        bool(entities) and all(e.lower() in checks_text.lower() for e in entities),
        f"checked {entities}; " + (checks_text.splitlines()[0] if checks_text else ""),
    )

    # The latest decision and its next wake.
    decision_stops = in_section(stops, "what-changed", "decisions")
    latest = latest_decision(state)
    summary = section_text(mod, "what-changed")
    landed = jump_by_keyboard(mod, "Latest decision")
    rings["what-changed"] = mod.evaluate(LANDING_RING)
    report.check(
        "the latest decision and the decision list are reached by keyboard",
        landed == "what-changed" and bool(in_section(stops, "decisions")),
        f"'Latest decision' moves focus to {landed!r}; {len(decision_stops)} Tab stops",
    )
    wake = latest.get("wait_until")
    report.check(
        "the latest policy decision says what the API says, with its next wake",
        "latest policy decision" in summary.lower()  # the eyebrow is shown in capitals
        and latest["summary"][:40] in summary
        and (wake is None or f"waiting until {local_time(wake, tz)}" in summary),
        f"{latest['kind']}: {latest['summary'][:60]!r}; wait_until {wake}; board: "
        + quote(summary, latest["summary"][:40]),
    )

    # The action status.
    actions = in_section(stops, "action-history")
    history = section_text(mod, "action-history")
    receipts = state["receipts"]
    landed = jump_by_keyboard(mod, "Action status")
    rings["action-history"] = mod.evaluate(LANDING_RING)
    report.check(
        "the action status (Action history) is reached by keyboard",
        landed == "action-history" and bool(actions),
        f"'Action status' moves focus to {landed!r}; {len(actions)} Tab stops",
    )
    report.check(
        "every receipt the API reports is listed with its tool",
        bool(receipts) and all(r["tool"] in history for r in receipts),
        f"{len(receipts)} receipts: {[(r['tool'], r['status']) for r in receipts]}",
    )

    report.check(
        "every section a link lands on shows the focus outline",
        all(rings.values()),
        json.dumps(rings),
    )

    # A receipt's evidence button, reached by Tab, moves focus to a receipt the API reports.
    reached = tab_to(mod, "evidence", "what-changed")
    jumped = None
    if reached:
        mod.keyboard.press("Enter")
        mod.wait_for_timeout(200)
        jumped = mod.evaluate("() => document.activeElement?.id || null")
    receipt_ids = {f"rcpt-{r['receipt_id']}" for r in receipts}
    report.check(
        "Enter on a receipt's evidence button (reached by Tab) moves focus to that receipt",
        reached and jumped in receipt_ids,
        f"reached by Tab: {reached}; focus moved to {jumped}; receipts {sorted(receipt_ids)}",
    )

    # Shift+Tab walks the same stops backwards, in exactly the reverse order. Both walks start
    # at the skip link, so the backward walk is compared from its second stop.
    back = tab_walk(mod, backwards=True)

    def key(s: dict[str, Any]) -> tuple[Any, ...]:
        return (s["tag"], s["id"], s["text"], s["section"])

    report.check(
        "Shift+Tab reaches the same stops in exactly the reverse order",
        [key(s) for s in back[1:]] == [key(s) for s in reversed(stops[1:])],
        f"{len(back)} backwards, {len(stops)} forwards",
    )

    # A second view of the same episode agrees on the revision and the receipts.
    org = join(browser, mod, "organizer_demo", base, report)
    org_token = token_of(org)
    a = api(base, "api/state", token)
    b = api(base, "api/state", org_token)
    org.wait_for_timeout(int(POLL_S * 2000))
    org_header = org.locator("text=STATE REVISION").first.locator("xpath=..").inner_text()
    mod_header = mod.locator("text=STATE REVISION").first.locator("xpath=..").inner_text()
    report.check(
        "two signed-in views agree on the revision and the receipts",
        a["revision"] == b["revision"]
        and sorted(r["receipt_id"] for r in a["receipts"])
        == sorted(r["receipt_id"] for r in b["receipts"])
        and re.search(rf"STATE REVISION\s*{a['revision']}\b", org_header, re.I) is not None
        and re.search(rf"STATE REVISION\s*{a['revision']}\b", mod_header, re.I) is not None,
        f"revision {a['revision']} / {b['revision']}; headers {mod_header!r} / {org_header!r}",
    )
    org.context.close()
    mod.context.close()


def pantry(browser: Browser, base: str, report: Report) -> None:
    mod = browser.new_context(viewport=VIEWPORT).new_page()  # type: ignore[arg-type]
    mod.goto(base)
    mod.get_by_label("Moderator code").fill(CODE)
    mod.keyboard.press("Enter")
    expect(mod.get_by_role("heading", name="Moderator controls")).to_be_visible()
    load_case(mod, "pantry_dev01")
    token = token_of(mod)
    # Deterministic pantry policy and the labeled staff simulator, twelve scenario minutes in:
    # the partner hold is placed, and nothing is received, committed or distributed yet.
    run = _post(base, "api/moderator/run", token, {"minutes": 12})
    poll(lambda: api(base, "api/state", token), lambda s: s["revision"] == run["revision"])
    mod.wait_for_timeout(int(POLL_S * 2000))
    state = api(base, "api/state", token)
    stops = tab_walk(mod)
    (Path(report.out) / "keyboard_pantry_tab_order.json").write_text(
        json.dumps(stops, indent=2) + "\n"
    )
    board = in_section(stops, "pantry-board")
    landed = jump_by_keyboard(mod, "Stock and service")
    ring = mod.evaluate(LANDING_RING)
    report.check(
        "the pantry stock and service board is reached by keyboard and shows the focus outline",
        landed == "pantry-board" and ring,
        f"'Stock and service' moves focus to {landed!r} (outline {ring}); "
        f"{len(board)} Tab stops inside",
    )
    text = section_text(mod, "pantry-board")
    labels = (
        "Expected (not stock)",
        "held,",
        "received",
        "committed",
        "Distributed",
        "Service deficit",
        "Achieved service (staff-recorded)",
    )
    report.check(
        "the pantry board keeps expected, held, received, committed and distributed apart",
        all(label in text for label in labels),
        "; ".join(f"{label}: {label in text}" for label in labels),
    )
    stock = state["stock"]
    service = stock["service"][0]
    shown: dict[str, dict[str, str]] = {}
    api_values: dict[str, dict[str, str]] = {}
    split_ok = True
    for pool in stock["balances"]:
        rid = pool["resource_id"]
        row = mod.locator(f"tr[data-stock='{rid}']")
        cells = {
            q: row.locator(f"td[data-quantity='{q}']").inner_text()
            for q in ("on_hand", "reserved", "available", "expected", "distributed")
        }
        shown[rid] = {q: text.split("\n")[0].strip() for q, text in cells.items()}
        api_values[rid] = {
            "on_hand": str(pool["on_hand_quantity"]),
            "reserved": str(pool["reserved_quantity"]),
            "available": str(pool["available_quantity"]),
            "expected": str(pool["expected_quantity"]),
            "distributed": str(pool["distributed_quantity"]),
        }
        split = f"{pool['held_quantity']} held, {pool['committed_quantity']} committed"
        split_ok = split_ok and split in cells["reserved"]
    report.check(
        "every stock row shows the quantities the API reports, with held and committed apart",
        bool(shown) and shown == api_values and split_ok,
        f"shown {shown}; api {api_values}; held and committed split shown: {split_ok}",
    )
    report.check(
        "the target stays 40 and the deficit is visible before any distribution",
        service["original_quantity"] == 40
        and f"{service['on_time_quantity']} of 40 on time" in text
        and service["unfulfilled_quantity"] > 0,
        f"on time {service['on_time_quantity']}, deficit {service['unfulfilled_quantity']}, "
        f"committed {service['committed_quantity']}",
    )
    mod.context.close()


def _post(base: str, path: str, token: str, body: dict[str, Any]) -> Any:
    import urllib.request

    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - local test server
        return json.loads(resp.read())


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report = Report(out)
    port = free_port()
    base = f"http://127.0.0.1:{port}/"
    var = Path(tempfile.mkdtemp(prefix="planb_kbd_"))
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
            for part in (campus, pantry):
                try:
                    part(browser, base, report)
                except Exception as exc:  # recorded as a failed check; the report is written
                    first = (str(exc).splitlines() or [""])[0]
                    report.check(
                        f"{part.__name__} ran to the end", False, f"{type(exc).__name__}: {first}"
                    )
            browser.close()
    finally:
        try:
            stop(server)
        finally:
            shutil.rmtree(var, ignore_errors=True)
    passed = all(c["passed"] for c in report.checks)
    (out / "keyboard_report.json").write_text(
        json.dumps(
            {
                "base_url_kind": "local plan-b serve on a free port with a fresh state directory",
                "browser": "Chromium (Playwright)",
                "passed": passed,
                "checks": report.checks,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"{sum(c['passed'] for c in report.checks)}/{len(report.checks)} checks passed")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    return run(Path(parser.parse_args().out))


if __name__ == "__main__":
    raise SystemExit(main())
