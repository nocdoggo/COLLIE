"""The seven-minute demo story, driven in a browser against a real server (Playwright, Chromium).

Not part of the default pytest run. Usage (from apps/plan_b, after `npm run build` in web/):

    uv run python tests/e2e/storyboard.py [--out <dir>] [--port 8791]

The default ``--out`` is var/storyboard/ (the evidence collectors pass their own).
It follows the Wave 2 demo runbook from a clean start: ``scripts/demo_prep.py`` prepares an
empty state directory and the verified recorded traces, then ``plan-b serve`` runs on 127.0.0.1
(stopped afterwards; the state directory is removed). It clicks what the presenter clicks, in
the order of the story, and only on deterministic and replay paths: the deterministic policies
act, people act from their own role tabs, and the live coordinator is shown from its recorded
trace under **Recorded replay**. It never selects or runs a model-driven policy, and a check
confirms that no episode made a model call.

Each step saves one captioned frame ``story_NN_<slug>.png`` (the viewport, with a caption band
above it; re-encoded as a 256-colour PNG; join links masked) and records its checks, which
compare what the page shows with fresh API reads. ``storyboard_report.json`` lists every step
with its segment, caption, checks and wall-clock seconds. Exit code 0 only if every check held.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, ViewportSize, expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from walkthrough import (  # noqa: E402 - the Wave 1 walkthrough's helpers, reused as they are
    APP,
    CODE,
    POLL_S,
    Report,
    api,
    load_case,
    local_time,
    poll,
    quote,
    readiness_of,
    sign_in_moderator,
    stop,
    token_of,
)
from walkthrough_wave2 import (  # noqa: E402
    DEADLINE,
    OFFER_TEXT,
    api_counters,
    api_row,
    board_matches,
    confirm,
    counter,
    join_as,
    minutes_until,
    overflow_of,
)

sys.path.insert(0, str(APP / "scripts"))
from demo_prep import prepare  # noqa: E402

DEFAULT_OUT = APP / "var" / "storyboard"
DEFAULT_PORT = 8791
# 1920x1080 at the 125 % browser zoom the runbook recommends for a projector.
VIEWPORT: ViewportSize = {"width": 1536, "height": 864}
# Recorded paid runs in the Wave 2 packet (scripts/run_live_cases.py), replayed, never re-run.
LIVE_TRACE = "live_p2-live_dev02_trace.json"  # P2 live/1.0.0 on dev02: hold, ask, commit
P3_TRACE = "live_p3-verify-all_dev02_trace.json"  # P3 verify-all/1.0.0: server checks first
# P1's first pantry run failed on a defect in our P1 harness (prompt tool_use.v1, token budget);
# kept on record, superseded by the rerun under tool_use.v2 (evaluation/development/README.md).
LIMIT_TRACE = "live_p1-tool-use_pantry_dev01_trace.json"
RERUN_TRACE = "live_p1-tool-use_pantry_dev01_r2_trace.json"
DETERMINISTIC = ("rules/", "pantry-rules/")

# The runbook's segments (DEMO.md): clock, seconds and title. They sum to 420 seconds.
SEGMENTS: dict[str, tuple[str, int, str]] = {
    "showcase": ("0:00-0:35", 35, "The campus showcase"),
    "commitments": ("0:35-1:10", 35, "What is committed and what the agent may change"),
    "delay": ("1:10-2:25", 75, "The delayed projector: verify, then commit"),
    "stale": ("2:25-3:10", 45, "A stale and a duplicate warning, handled without churn"),
    "backup": ("3:10-4:00", 50, "Prepare, ask, commit: the organizer-approved paid backup"),
    "live": ("4:00-4:55", 55, "The live coordinator's decision card (recorded replay)"),
    "community": ("4:55-5:40", 45, "A participant's own check-in changes the plan"),
    "pantry": ("5:40-6:25", 45, "Pantry Continuity cameo"),
    "close": ("6:25-7:00", 35, "Close: what is delivered, and the fallback"),
}


class StoryReport(Report):
    """Checks grouped by story step; each step saves one captioned frame."""

    def __init__(self, out: Path) -> None:
        super().__init__(out)
        self.steps: list[dict[str, Any]] = []
        self._t0 = time.monotonic()

    def begin(self, slug: str, segment: str, caption: str) -> None:
        if self.steps:
            self._close()
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "slug": slug,
                "segment": segment,
                "clock": SEGMENTS[segment][0],
                "caption": caption,
                "frame": None,
                "checks": [],
                "started_s": round(time.monotonic() - self._t0, 1),
            }
        )

    def _close(self) -> None:
        last = self.steps[-1]
        if "seconds" not in last:
            last["seconds"] = round(time.monotonic() - self._t0 - last["started_s"], 1)

    def check(self, name: str, ok: bool, detail: str = "", *, step: int | None = None) -> None:
        super().check(name, ok, detail, step=step)
        if self.steps:
            self.checks[-1]["story_step"] = self.steps[-1]["step"]
            self.steps[-1]["checks"].append(self.checks[-1])

    def frame(self, page: Page) -> None:
        step = self.steps[-1]
        name = f"story_{step['step']:02d}_{step['slug']}"
        self.shot(page, name)
        title = SEGMENTS[step["segment"]][2]
        caption_png(
            self.out / f"{name}.png",
            f"{step['step']:02d} · {step['clock']} · {title}",
            step["caption"],
        )
        step["frame"] = f"{name}.png"

    def finish(self) -> None:
        if self.steps:
            self._close()


def caption_png(path: Path, title: str, caption: str) -> None:
    """Put a caption band above the screenshot and re-encode it as a 256-colour PNG (median cut,
    no dithering, as scripts/collect_evidence.py does for the walkthrough screenshots)."""
    from PIL import Image, ImageDraw, ImageFont

    with Image.open(path) as image:
        shot = image.convert("RGB")
    band = 78
    canvas = Image.new("RGB", (shot.width, shot.height + band), (22, 30, 46))
    canvas.paste(shot, (0, band))
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 10), title, fill=(255, 255, 255), font=ImageFont.load_default(size=26))
    draw.text((18, 46), caption, fill=(214, 224, 240), font=ImageFont.load_default(size=19))
    palette = canvas.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette.save(path, optimize=True)


# Scroll an element to the top of the viewport, below any sticky banner (the replay label).
TO_TOP = """(e) => {
  e.scrollIntoView({block: 'start'});
  let covered = 0;
  for (const s of document.querySelectorAll('body *')) {
    const p = getComputedStyle(s).position;
    if (p !== 'sticky' && p !== 'fixed') continue;
    const r = s.getBoundingClientRect();
    if (r.top <= 1 && r.height < window.innerHeight / 2) covered = Math.max(covered, r.bottom);
  }
  window.scrollBy(0, e.getBoundingClientRect().top - (covered + 12));
}"""


def show(page: Page, selector: str) -> None:
    """Scroll a board section (the first match) to the top of the viewport."""
    page.locator(selector).first.evaluate(TO_TOP)
    page.wait_for_timeout(250)


def run_policy(page: Page) -> None:
    page.get_by_role("button", name="Run deterministic policy").click()
    expect(page.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=20000)


def run_minutes(page: Page, minutes: int) -> None:
    page.get_by_label("Minutes").fill(str(minutes))
    page.get_by_role("button", name=f"Run {minutes} minutes with policy").click()
    expect(page.get_by_role("button", name="Run deterministic policy")).to_be_enabled(timeout=60000)


def note(episodes: dict[str, set[str]], state: dict[str, Any]) -> None:
    """Remember which policies decided in this episode (for the closing no-model-call check)."""
    episodes.setdefault(state["episode_id"], set()).update(
        d["policy_id"] for d in state["decisions"]
    )


def open_replay(browser: Browser, base: str, name: str) -> tuple[Page, list[str]]:
    posts: list[str] = []
    page = browser.new_context(viewport=VIEWPORT).new_page()
    page.on("request", lambda r: posts.append(r.url) if r.method != "GET" else None)
    page.goto(base + "#/replay")
    page.get_by_role("button", name=name, exact=True).click()
    page.wait_for_function(
        "() => { const b = document.querySelector('.replay-integrity[data-integrity]');"
        " return b !== null && b.getAttribute('data-integrity') !== 'checking'; }",
        timeout=20000,
    )
    return page, posts


def run(out: Path, port: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("story_*.png"):
        old.unlink()
    report = StoryReport(out)
    base = f"http://127.0.0.1:{port}/"
    work = Path(tempfile.mkdtemp(prefix="planb_story_"))
    prepared = prepare(work / "demo")
    env = {**os.environ, "PLAN_B_MODERATOR_CODE": CODE}
    command = [sys.executable, "-m", "plan_b.cli", "serve", "--port", str(port)]
    command += ["--var", str(prepared.state), "--replay-dir", str(prepared.replays)]
    server = subprocess.Popen(
        command, cwd=APP, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    started = time.monotonic()
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
                story(browser, base, report, prepared.copied)
            except Exception as exc:  # recorded as a failed check; the report is still written
                first = (str(exc).splitlines() or [""])[0]
                report.check("storyboard ran to the end", False, f"{type(exc).__name__}: {first}")
            browser.close()
    finally:
        # The state directory holds session and join-code tables: never leave it behind.
        try:
            stop(server)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    report.finish()
    passed = all(c["passed"] for c in report.checks)
    segments = []
    for key, (clock, seconds, title) in SEGMENTS.items():
        mine = [s for s in report.steps if s["segment"] == key]
        segments.append(
            {
                "segment": key,
                "clock": clock,
                "planned_seconds": seconds,
                "title": title,
                "frames": [s["frame"] for s in mine if s["frame"]],
                "automated_seconds": round(sum(s.get("seconds", 0.0) for s in mine), 1),
                "passed": bool(mine) and all(c["passed"] for s in mine for c in s["checks"]),
            }
        )
    (out / "storyboard_report.json").write_text(
        json.dumps(
            {
                "kind": "storyboard of the seven-minute demo (PEEAI_plan/handoffs/wave_2/DEMO.md)",
                "base_url_kind": "local plan-b serve on 127.0.0.1 with a clean demo_prep state",
                "browser": "Chromium (Playwright)",
                "viewport": VIEWPORT,
                "paths": "deterministic policies, role tabs and recorded replays; no model call",
                "passed": passed,
                "planned_seconds": sum(s[1] for s in SEGMENTS.values()),
                "automated_run_seconds": round(time.monotonic() - started, 1),
                "segments": segments,
                "steps": report.steps,
                "checks": [{k: v for k, v in c.items()} for c in report.checks],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"{sum(c['passed'] for c in report.checks)}/{len(report.checks)} checks passed")
    return 0 if passed else 1


def story(browser: Browser, base: str, report: StoryReport, replays: tuple[str, ...]) -> None:
    mod = sign_in_moderator(browser, base, VIEWPORT)
    errors: list[str] = []
    mod.on("pageerror", lambda e: errors.append(str(e)))
    mtoken = token_of(mod)
    report.secret("session token of the moderator", mtoken)
    episodes: dict[str, set[str]] = {}

    campus(browser, base, report, mod, mtoken, episodes)
    live_replay(browser, base, report, mod, replays)
    community(browser, base, report, mod, mtoken, episodes, errors)
    pantry(browser, base, report, mod, mtoken, episodes, errors)
    close(browser, base, report, mod, mtoken, episodes, errors)


def campus(
    browser: Browser,
    base: str,
    report: StoryReport,
    mod: Page,
    mtoken: str,
    episodes: dict[str, set[str]],
) -> None:
    # 1. The campus showcase, from a clean episode.
    report.begin(
        "campus_showcase",
        "showcase",
        "dev01 loaded: goal, 18:00 deadline, budget and the programme, in a fictional sandbox.",
    )
    load_case(mod, "dev01")
    s0 = api(base, "api/state", mtoken)
    head = mod.locator("header").first.inner_text()
    labels = ("Fictional sandbox", "Deterministic policy", "16:40", "18:00")
    report.check(
        "clean dev01 episode: revision 3, no receipt, no hold; header labels visible",
        s0["revision"] == 3
        and s0["receipts"] == []
        and s0["holds"] == []
        and all(s in head for s in labels),
        quote(head, *labels),
    )
    show(mod, "header")
    report.frame(mod)

    # 2. What is committed, and what the coordinator may change.
    report.begin(
        "current_plan",
        "commitments",
        "Plan version 1: five activities; demonstrations need the projector, due 17:00.",
    )
    schedule = mod.locator("#schedule").inner_text()
    activities = [a["definition"]["label"] for a in s0["activities"]]
    report.check(
        "the schedule shows plan version 1 with every activity (fresh API read)",
        "plan version 1" in schedule and all(label in schedule for label in activities),
        f"{len(activities)} activities; " + quote(schedule, "plan version 1"),
    )
    show(mod, "#schedule")
    report.frame(mod)

    report.begin(
        "agent_authority",
        "commitments",
        "The agent's grant: it may hold up to $35.00, but commit $0.00 without the organizer.",
    )
    authority = mod.locator("#authority").inner_text()
    grant = next(
        g["grant"] for g in s0["grants"] if g["grant"]["grant_id"] == "grant_coordinator_demo"
    )
    report.check(
        "the agent's grant is on the board: $0.00 committed limit, $35.00 hold limit",
        "agent_demo" in authority and "$0.00" in authority and "$35.00" in authority,
        f"committed limit {grant['max_total_committed_cents']} cents; "
        + quote(authority, "agent_demo"),
    )
    show(mod, "#authority")
    report.frame(mod)

    # 3. The delayed projector: the notice is a claim, the policy verifies, then commits.
    report.begin(
        "notice_is_a_claim",
        "delay",
        "16:40: a delivery notice says the projector is late. A claim, not yet a fact.",
    )
    notices = [o for o in s0["observations"] if o["observation"]["kind"] == "notice"]
    obs_text = mod.locator("#observations").inner_text()
    words = " ".join(notices[0]["observation"]["text"].split()[:6]) if notices else "?"
    report.check(
        "the projector notice is on the board with its source and times",
        len(notices) == 1
        and words in " ".join(obs_text.split())
        and "from delivery_contact" in obs_text
        and "received 16:40" in obs_text,
        quote(obs_text, "from delivery_contact", "received 16:40"),
    )
    show(mod, "#observations")
    report.frame(mod)

    report.begin(
        "verified_status",
        "delay",
        "Run deterministic policy: one status query answers 'delayed, ETA 17:25'.",
    )
    run_policy(mod)
    expect(mod.get_by_role("heading", name="Applied (1)")).to_be_visible(timeout=15000)
    s1 = api(base, "api/state", mtoken)
    checks = mod.locator("#status-checks").inner_text()
    report.check(
        "the status query's answer is shown with its ETA (fresh API read)",
        any(c["envelope_status"] == "succeeded" for c in s1["status_checks"])
        and "Answered" in checks
        and "17:25" in checks,
        quote(checks, "17:25"),
    )
    show(mod, "#status-checks")
    report.frame(mod)

    report.begin(
        "alternatives",
        "delay",
        "The planner's checked alternatives: the free swap ranks first of 3 feasible; 13 rejected.",
    )
    cands = mod.locator("#candidates").inner_text()
    report.check(
        "alternatives show the feasible swap and the rejected candidates; nothing reserved",
        "Swap demonstrations and skills exchange" in cands
        and "Rejected alternatives (" in cands
        and s1["holds"] == []
        and s1["budget"]["reserved_cents"] == 0,
        quote(cands, "Swap demonstrations and skills exchange", "Rejected alternatives ("),
    )
    show(mod, "#candidates")
    report.frame(mod)

    report.begin(
        "committed_with_receipt",
        "delay",
        "Commit: the swap is applied with a receipt, revision 4 to 5; before and after shown.",
    )
    applied = [r for r in s1["receipts"] if r["status"] == "applied" and r["tool"] == "apply_plan"]
    comparison = mod.locator("#plan-comparison").inner_text()
    body = mod.locator("body").inner_text()
    report.check(
        "one applied plan receipt (4 -> 5), shown on the board; no money committed",
        len(applied) == 1
        and applied[0]["revision_before"] == 4
        and applied[0]["revision_after"] == 5
        and applied[0]["receipt_id"] in body
        and s1["budget"]["committed_cents"] == 0
        and s1["plan"]["plan_version"] == 2
        and "Plan version 1 → 2" in comparison,
        f"{applied[0]['receipt_id'] if applied else 'no receipt'}; "
        + quote(comparison, "Plan version 1 → 2"),
    )
    note(episodes, s1)
    show(mod, "#plan-comparison")
    report.frame(mod)

    # 4. Stale and duplicate warnings (dev04): recorded with reasons, nothing changes.
    report.begin(
        "stale_and_duplicate",
        "stale",
        "dev04: last month's order P09 is 'inapplicable'; its forwarded copy is a 'duplicate'.",
    )
    load_case(mod, "dev04")
    s0 = api(base, "api/state", mtoken)
    run_policy(mod)
    run_minutes(mod, 8)
    s1 = poll(
        lambda: api(base, "api/state", mtoken),
        lambda s: {"inapplicable", "duplicate"} <= {d["kind"] for d in s["decisions"]},
    )
    mod.wait_for_timeout(int(2 * POLL_S * 1000))
    decisions = mod.locator("#decisions").inner_text()
    dup = next((d for d in s1["decisions"] if d["kind"] == "duplicate"), None)
    stale = next((d for d in s1["decisions"] if d["kind"] == "inapplicable"), None)
    report.check(
        "the stale notice is inapplicable with its reasons and the copy is a duplicate",
        dup is not None
        and stale is not None
        and stale["summary"] in decisions
        and dup["summary"] in decisions
        and "P09" in stale["summary"],
        quote(decisions, "P09", dup["summary"][:30] if dup else "duplicate"),
    )
    report.check(
        "no churn: plan v1 kept, no hold, nothing committed or reserved (fresh API read)",
        s1["plan"]["plan_version"] == 1
        and s1["holds"] == []
        and s1["budget"]["committed_cents"] == 0
        and s1["budget"]["reserved_cents"] == 0,
        json.dumps({"plan": s1["plan"]["plan_version"], "budget": s1["budget"]}),
    )
    note(episodes, s1)
    show(mod, "#decisions li.decision[data-decision-kind='duplicate']")
    report.frame(mod)

    # 5. dev02: prepare (a free, expiring hold), ask the organizer, commit once approved.
    report.begin(
        "backup_held_and_asked",
        "backup",
        "dev02: ETA 17:45 is too late. The agent holds the backup (expiry shown) and asks.",
    )
    load_case(mod, "dev02")
    s0 = api(base, "api/state", mtoken)
    run_policy(mod)
    s1 = poll(lambda: api(base, "api/state", mtoken), lambda s: bool(s["holds"]))
    mod.wait_for_timeout(int(2 * POLL_S * 1000))
    holds = mod.locator("#holds").inner_text()
    hold = s1["holds"][0] if s1["holds"] else {}
    expiry = local_time(hold["expires_at"], s1["timezone"]) if hold else "?"
    report.check(
        "a hold on the backup projector with its id and expiry; an authorization request",
        bool(hold)
        and hold["hold_id"] in holds
        and expiry in holds
        and any(d["authorization_request"] for d in s1["decisions"])
        and s1["budget"]["committed_cents"] == 0,
        f"{hold.get('hold_id')} expires {expiry}; " + quote(holds, "Hold expires"),
    )
    show(mod, "#holds")
    report.frame(mod)

    report.begin(
        "organizer_approves",
        "backup",
        "The organizer, in their own session, sees the request and approves $35.00.",
    )
    org = join_as(browser, mod, "organizer_demo", base, report, "Organizer controls")
    org.set_viewport_size(VIEWPORT)
    approve = org.get_by_role("button", name="Approve: raise the limit to $35.00")
    expect(approve).to_be_visible(timeout=3 * POLL_S * 1000)
    approve.evaluate("(e) => e.scrollIntoView({block: 'center'})")
    org.wait_for_timeout(250)
    report.frame(org)
    approve.click()
    confirm_button = org.get_by_role("button", name="Confirm", exact=False)
    if confirm_button.count():
        confirm_button.first.click()
    s2 = poll(
        lambda: api(base, "api/state", mtoken),
        lambda s: any(
            g["grant"]["grant_id"] == "grant_coordinator_demo"
            and g["grant"]["max_total_committed_cents"] == 3500
            for g in s["grants"]
        ),
    )
    report.check(
        "the organizer's approval raised the coordinator's committed limit to $35.00",
        any(
            g["grant"]["grant_id"] == "grant_coordinator_demo"
            and g["grant"]["max_total_committed_cents"] == 3500
            for g in s2["grants"]
        ),
        "grant_coordinator_demo max_total_committed_cents 3500",
    )
    org.context.close()

    report.begin(
        "paid_backup_committed",
        "backup",
        "Run again: the paid backup is booked once, $35.00 committed, the hold converted.",
    )
    run_policy(mod)
    s3 = poll(lambda: api(base, "api/state", mtoken), lambda s: bool(s["commitments"]))
    mod.wait_for_timeout(int(2 * POLL_S * 1000))
    side = mod.locator("#holds").inner_text() + mod.locator("#budget").inner_text()
    report.check(
        "one commitment of $35.00, nothing left reserved (fresh API read and board)",
        s3["budget"]["committed_cents"] == 3500
        and len(s3["commitments"]) == 1
        and s3["budget"]["reserved_cents"] == 0
        and "$35.00" in side,
        json.dumps(s3["budget"]),
    )
    note(episodes, s3)
    show(mod, "#budget")
    report.frame(mod)


def live_replay(
    browser: Browser, base: str, report: StoryReport, mod: Page, replays: tuple[str, ...]
) -> None:
    # 6. The live coordinator (P2, live/1.0.0) from its recorded dev02 run, labeled as replay.
    report.begin(
        "live_decision_card",
        "live",
        "Replay of the live agent's paid dev02 run: a model call chose, the server checked.",
    )
    replay, posts = open_replay(browser, base, LIVE_TRACE)
    text = replay.locator("body").inner_text()
    replay.get_by_role("button", name="Final recorded state").click()
    card = replay.locator("li.decision", has_text="Applied Use backup_projector").first
    expect(card).to_be_visible(timeout=10000)
    card_text = card.inner_text()
    report.check(
        "the replay is labeled, verified, and from the recorded live run",
        LIVE_TRACE in replays
        and "Recorded replay" in text
        and "Integrity check passed" in text
        and "live/1.0.0" in text,
        quote(text, "Recorded replay", "Integrity check", "live/1.0.0"),
    )
    report.check(
        "the decision card names the model call that chose it, the model, latency and cost",
        "chosen by a model call" in card_text
        and "anthropic/claude-sonnet-5.5" in card_text
        and "Model's stated rationale (untrusted" in card_text
        and "apply:" in card_text,
        quote(card_text, "chosen by a model call", "Model (as returned)", "Chose menu option"),
    )
    card.evaluate(TO_TOP)
    replay.wait_for_timeout(250)
    report.frame(replay)
    report.check("the replay issued no POST/PUT/DELETE request", posts == [], json.dumps(posts))
    replay.context.close()

    # The policy choices P0-P3, named but not run: the comparison is not made yet.
    report.begin(
        "policy_choices",
        "live",
        "P0 rules, P1 tool-use, P2 live, P3 verify-all share tools and checks; not yet compared.",
    )
    panel = mod.locator("#moderator-panel")
    radios = panel.get_by_role("radio")
    names = [r.evaluate("(e) => e.closest('label').innerText") for r in radios.all()]
    report.check(
        "the moderator's policy selector offers P0-P3 by name; the deterministic one is selected",
        len(names) == 4
        and any(n.startswith("Deterministic policy") for n in names)
        and any(n.startswith("Tool-use agent") and "P1" in n for n in names)
        and any(n.startswith("Live agent") and "P2" in n for n in names)
        and any(n.startswith("Verify-all agent") and "P3" in n for n in names)
        and panel.locator("[data-policy-selected='rules']").count() == 1,
        " | ".join(" ".join(n.split())[:60] for n in names),
    )
    show(mod, "#moderator-panel fieldset.policy-switch")
    report.frame(mod)

    report.begin(
        "p3_server_checks",
        "live",
        "Backup: in P3's replay its own status checks are server checks; its choices model calls.",
    )
    replay, posts = open_replay(browser, base, P3_TRACE)
    replay.get_by_role("button", name="Final recorded state").click()
    check_card = replay.locator("li.decision", has_text="Verify-all check of projector").first
    expect(check_card).to_be_visible(timeout=10000)
    checked = check_card.inner_text()
    chosen = replay.locator("li.decision", has_text="Held backup_projector").first.inner_text()
    report.check(
        "a P3 server check is labeled with its relevance rule, a P3 hold as a model choice",
        P3_TRACE in replays
        and "verify-all/1.0.0" in checked
        and "server check under verify-all-relevance/1.0.0, no model choice" in checked
        and "chosen by a model call" not in checked
        and "chosen by a model call" in chosen
        and "decision-live" in (check_card.get_attribute("class") or ""),
        quote(checked, "server check under") + " | " + quote(chosen, "chosen by a model call"),
    )
    check_card.evaluate(TO_TOP)
    replay.wait_for_timeout(250)
    report.frame(replay)
    replay.context.close()

    report.begin(
        "harness_bug_on_record",
        "live",
        "On record: a run caught a bug in our P1 prompt; every bad hold was refused."
        " Fixed: 40 of 40.",
    )
    replay, posts = open_replay(browser, base, LIMIT_TRACE)
    replay.get_by_role("button", name="Final recorded state").click()
    final = replay.locator("body").inner_text()
    rejected = replay.locator("li.decision", has_text="hold_resource was rejected")
    first = rejected.first.inner_text() if rejected.count() else ""
    report.check(
        "P1's recorded pantry run replays with 0 of 40 on time, executor rejections and the cap",
        LIMIT_TRACE in replays
        and "Recorded replay" in final
        and "0 of 40 on time" in final
        and rejected.count() == 6
        and "chosen by a model call" in first
        and "model-call cap of 8" in final,
        f"{rejected.count()} rejected holds; " + quote(final, "0 of 40 on time", "model-call cap"),
    )
    show(replay, "#decisions")
    report.frame(replay)
    replay.context.close()
    # The rerun under the fixed prompt (tool_use.v2) completed; it is checked, not shown.
    replay, posts = open_replay(browser, base, RERUN_TRACE)
    replay.get_by_role("button", name="Final recorded state").click()
    final = replay.locator("body").inner_text()
    report.check(
        "the rerun under the fixed prompt replays with 40 of 40 on time and no refused hold",
        RERUN_TRACE in replays
        and "40 of 40 on time" in final
        and "tool-use/1.0.0" in final
        and replay.locator("li.decision", has_text="was rejected").count() == 0,
        quote(final, "40 of 40 on time"),
    )
    replay.context.close()


def community(
    browser: Browser,
    base: str,
    report: StoryReport,
    mod: Page,
    mtoken: str,
    episodes: dict[str, set[str]],
    errors: list[str],
) -> None:
    # 7. The skills exchange: the peer lead's own check-in narrows their window; the plan moves.
    report.begin(
        "participant_check_in",
        "community",
        "Skills exchange: the peer lead checks in from their own tab, available until 11:05.",
    )
    load_case(mod, "skills_dev01")
    s0 = api(base, "api/state", mtoken)
    tz = s0["timezone"]
    peer = join_as(browser, mod, "participant_peer_lead", base, report, "Your role")
    peer.on("pageerror", lambda e: errors.append(str(e)))
    peer.set_viewport_size(VIEWPORT)
    peer.get_by_label("Available until", exact=False).select_option(label="11:05")
    peer.get_by_role("button", name="Check in").click()
    confirm(peer, "Check in as")
    s1 = api(base, "api/state", mtoken)
    latest = [c for c in s1["checkins"] if c["resource_id"] == "peer_lead"][-1]
    report.check(
        "the check-in is recorded from the participant's own session, until 11:05",
        latest["principal_id"] == "participant_peer_lead"
        and local_time(latest["available"]["end"], tz) == "11:05",
        f"{latest['principal_id']} until {local_time(latest['available']['end'], tz)}",
    )
    report.frame(peer)

    report.begin(
        "community_replanned",
        "community",
        "The 11:20 peer exchange no longer fits; the policy swaps it to 10:40 (receipt shown).",
    )
    expect(readiness_of(mod, "peer_lead")).to_contain_text("11:05", timeout=3 * POLL_S * 1000)
    run_policy(mod)
    s2 = poll(lambda: api(base, "api/state", mtoken), lambda s: s["plan"]["plan_version"] >= 2)
    mod.wait_for_timeout(int(2 * POLL_S * 1000))
    plan2 = {a["activity_id"]: a for a in s2["plan"]["assignments"]}
    schedule = mod.locator("#schedule").inner_text()
    report.check(
        "plan v2 moves the peer exchange to 10:40, inside the peer lead's window",
        s2["plan"]["plan_version"] == 2
        and local_time(plan2["peer_exchange"]["start"], tz) == "10:40"
        and "10:40" in schedule,
        quote(schedule, "10:40"),
    )
    show(mod, "#plan-comparison")
    report.frame(mod)

    report.begin(
        "resource_offer",
        "community",
        "A steward offers the registered backup kit: activated after checks; no hold, no spend.",
    )
    steward = join_as(browser, mod, "participant_kit_steward", base, report, "Your role")
    steward.on("pageerror", lambda e: errors.append(str(e)))
    steward.set_viewport_size(VIEWPORT)
    budget, holds = s2["budget"], len(s2["holds"])
    steward.get_by_label("I confirm the registered terms", exact=False).check()
    steward.get_by_label("Your offer").fill(OFFER_TEXT)
    steward.get_by_role("button", name="Send offer").click()
    confirm(steward, "Offer ")
    s3 = api(base, "api/state", mtoken)
    kit = next(
        r for r in s3["resources"] if r["definition"]["resource_id"] == "backup_learning_kit"
    )
    report.check(
        "the offer activates the preconfigured backup kit; no hold, spend or plan change",
        kit["status"] in ("available", "expected")
        and s3["budget"] == budget
        and len(s3["holds"]) == holds
        and s3["plan"]["plan_version"] == 2,
        f"backup kit {kit['status']} ({kit['status_basis']})",
    )
    note(episodes, s3)
    report.frame(steward)
    for page in (peer, steward):
        page.context.close()


def pantry(
    browser: Browser,
    base: str,
    report: StoryReport,
    mod: Page,
    mtoken: str,
    episodes: dict[str, set[str]],
    errors: list[str],
) -> None:
    # 8. Pantry Continuity: 40-kit target, staff-confirmed handoff and distribution.
    report.begin(
        "pantry_loaded",
        "pantry",
        "Target 40 kits. 24 on hand, 20 expected (not stock), 16 at the partner pool.",
    )
    load_case(mod, "pantry_dev01")
    s0 = api(base, "api/state", mtoken)
    ok, detail = board_matches(mod, s0)
    board = mod.locator("#pantry-board").inner_text()
    report.check(
        "fictional pantry board: shortfall 16, deficit 40; pantry 24, expected 20, partner 16",
        ok
        and api_counters(s0) == (16, 40)
        and api_row(s0, "pantry_stock")["on_hand"] == 24
        and api_row(s0, "pantry_stock")["expected"] == 20
        and api_row(s0, "partner_stock")["on_hand"] == 16
        and "Fictional pantry sandbox" in board
        and "Supply shortfall" in board
        and "Service deficit" in board,
        detail + "; " + quote(board, "Fictional pantry sandbox", "Supply shortfall"),
    )
    show(mod, "#pantry-board")
    report.frame(mod)

    report.begin(
        "handoff_requested",
        "pantry",
        "The agent verifies and holds the partner's 16 kits for a staff handoff. Stock stays 24.",
    )
    staff = join_as(browser, mod, "fictional_staff", base, report, "Staff actions")
    staff.on("pageerror", lambda e: errors.append(str(e)))
    staff.set_viewport_size(VIEWPORT)
    run_policy(mod)
    s1 = poll(
        lambda: api(base, "api/state", mtoken),
        lambda s: any(t["status"] == "open" for t in s["stock"]["handoff_tasks"]),
    )
    ok, detail = board_matches(mod, s1)
    task = next(t for t in s1["stock"]["handoff_tasks"] if t["status"] == "open")
    report.check(
        "16 partner kits held for an open staff task; pantry still 24; shortfall 16, deficit 40",
        ok
        and api_counters(s1) == (16, 40)
        and api_row(s1, "partner_stock")["reserved"] == 16
        and api_row(s1, "pantry_stock")["on_hand"] == 24
        and task["requested_quantity"] == 16,
        detail,
    )
    show(mod, "#pantry-board")
    report.frame(mod)

    report.begin(
        "staff_handoff",
        "pantry",
        "Staff (the presenter, in a staff tab) record the handoff: pantry 24 to 40, partner 0.",
    )
    expect(staff.get_by_label("What arrived")).to_have_value(
        f"hold:{task['hold_id']}", timeout=3 * POLL_S * 1000
    )
    receipt_button = staff.get_by_role("button", name="Record stock receipt", exact=True)
    expect(receipt_button).to_be_enabled(timeout=3 * POLL_S * 1000)
    reference = staff.get_by_label("Receipt reference", exact=False).input_value()
    receipt_button.click()
    confirm(staff, f"Receipt {reference}")
    s2 = api(base, "api/state", mtoken)
    report.check(
        "one staff receipt of 16; pantry 40, partner 0; shortfall 0, deficit still 40",
        len(s2["stock"]["receipts"]) == 1
        and s2["stock"]["receipts"][0]["actor_id"] == "fictional_staff"
        and api_counters(s2) == (0, 40)
        and api_row(s2, "pantry_stock")["on_hand"] == 40
        and api_row(s2, "partner_stock")["on_hand"] == 0,
        json.dumps(api_counters(s2)),
    )
    report.frame(staff)

    report.begin(
        "kits_committed",
        "pantry",
        "Run again: the agent reserves 40 and applies the plan. Committed, but nobody served yet.",
    )
    run_policy(mod)
    s3 = poll(lambda: api(base, "api/state", mtoken), lambda s: bool(s["stock"]["allocations"]))
    ok, detail = board_matches(mod, s3)
    service = s3["stock"]["service"][0]
    report.check(
        "40 committed; shortfall 0, deficit still 40, 0 achieved",
        ok
        and api_counters(s3) == (0, 40)
        and service["committed_quantity"] == 40
        and service["on_time_quantity"] == 0,
        detail + f"; achieved {counter(mod, 'achieved')}",
    )
    show(mod, "#pantry-board")
    report.frame(mod)

    report.begin(
        "distributed",
        "pantry",
        "Advance to 13:40 (simulated clock); staff record 40 distributed. Both counters reach 0.",
    )
    minutes = minutes_until(s3["clock"], DEADLINE)
    run_minutes(mod, minutes)
    distribute = staff.get_by_role("button", name="Record distribution", exact=True)
    expect(distribute).to_be_enabled(timeout=3 * POLL_S * 1000)
    expect(staff.get_by_label("Quantity distributed", exact=False)).to_have_value(
        "40", timeout=3 * POLL_S * 1000
    )
    dref = staff.get_by_label("Distribution reference", exact=False).input_value()
    distribute.click()
    confirm(staff, f"Distribution {dref}")
    s4 = poll(lambda: api(base, "api/state", mtoken), lambda s: bool(s["stock"]["distributions"]))
    ok, detail = board_matches(mod, s4)
    expect(mod.locator("#pantry-board [data-counter='achieved'] .counter-value")).to_have_text(
        "40 of 40 on time", timeout=3 * POLL_S * 1000
    )
    report.check(
        "40 of 40 on time at 13:40; shortfall 0, deficit 0; S20 still 20 unreceived",
        ok
        and api_counters(s4) == (0, 0)
        and s4["stock"]["distributions"][0]["on_time"] is True
        and api_row(s4, "pantry_stock")["expected"] == 20
        and all(b["conserved"] for b in s4["stock"]["balances"]),
        f"ran {minutes} minutes from {local_time(s3['clock'], s3['timezone'])}; {detail}",
    )
    note(episodes, s4)
    show(mod, "#pantry-board")
    report.frame(mod)
    staff.context.close()


def close(
    browser: Browser,
    base: str,
    report: StoryReport,
    mod: Page,
    mtoken: str,
    episodes: dict[str, set[str]],
    errors: list[str],
) -> None:
    # 9. The fallback is ready: every recorded trace is listed under Recorded replay.
    report.begin(
        "fallback_ready",
        "close",
        "Offline fallback: recorded traces only, each checked in the browser, labeled replay.",
    )
    page = browser.new_context(viewport=VIEWPORT).new_page()
    page.goto(base + "#/replay")
    expect(page.get_by_role("button", name=LIVE_TRACE)).to_be_visible(timeout=10000)
    listed = [r["name"] for r in api(base, "api/replays")]
    report.check(
        "the replay list holds the recorded traces the runbook opens",
        all(
            n in listed
            for n in (LIVE_TRACE, P3_TRACE, LIMIT_TRACE, RERUN_TRACE, "pantry_dev01_trace.json")
        ),
        f"{len(listed)} traces",
    )
    report.frame(page)
    page.context.close()

    setting = api(base, "api/moderator/policy", mtoken)
    ran = sorted(set().union(*episodes.values())) if episodes else []
    report.check(
        "no model call in the story: every decision of its 5 episodes came from a deterministic "
        "policy, and the selection stayed deterministic",
        len(episodes) == 5
        and bool(ran)
        and all(p.startswith(DETERMINISTIC) for p in ran)
        and setting["caps"]["model_calls"] == 0
        and setting["policy"] == "rules",
        json.dumps({"episodes": len(episodes), "policies": ran, "caps": setting["caps"]}),
    )
    wide, where = overflow_of(mod)
    report.check(f"no horizontal overflow at {VIEWPORT['width']}px", not wide, where)
    report.check(
        "no page errors", errors == [], f"{len(errors)} page errors: {json.dumps(errors[:3])}"
    )
    codes = sum(1 for label, _ in report.secrets if label.startswith("join code"))
    tokens = sum(1 for label, _ in report.secrets if label.startswith("session token"))
    report.check(
        "no join code or session token in the visible text at any frame",
        report.exposed == [] and codes >= 4 and tokens >= 5,
        f"{len(report.shots)} frames; {codes} join codes, {tokens} session tokens and the "
        f"moderator code checked; {report.masked} join links masked; exposed: {report.exposed}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    return run(Path(args.out), args.port)


if __name__ == "__main__":
    sys.exit(main())
