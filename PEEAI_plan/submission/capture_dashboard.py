"""Capture sharp screenshots of the running Plan B board for the deck and the documentation.

Starts ``plan-b serve`` on 127.0.0.1 with a clean demo_prep state (no model call), signs in as
the moderator, runs the deterministic policy on the practice cases for a few scenario minutes
(right after its decision), saves 2x screenshots and crops the panels into ``screenshots/``.
The crop needs Pillow, for example ``uv run --with pillow python ...``. Run from ``apps/plan_b``:

    uv run python ../../PEEAI_plan/submission/capture_dashboard.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parents[1] / "apps" / "plan_b"
sys.path.insert(0, str(APP / "tests" / "e2e"))
sys.path.insert(0, str(APP / "scripts"))

from demo_prep import prepare  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from walkthrough import CODE, api, load_case, stop  # noqa: E402

OUT = HERE / "screenshots"
PORT = 8796
SIZE = {"width": 1600, "height": 1000}


def run_minutes(page, minutes: int) -> None:
    page.get_by_label("Minutes").fill(str(minutes))
    page.get_by_role("button", name=f"Run {minutes} minutes with policy").click()
    expect(page.get_by_role("button", name="Run deterministic policy")).to_be_enabled(
        timeout=90000
    )
    page.wait_for_timeout(1500)


def view_at(page, heading: str, path: Path, offset: int = 12) -> None:
    """Scroll so a board section's heading sits at the top, then save the viewport."""
    target = page.get_by_role("heading", name=heading, exact=False).first
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    if box is not None:
        page.evaluate(f"window.scrollBy(0, {box['y'] - offset})")
    page.wait_for_timeout(500)
    page.screenshot(path=str(path))


CROPS = {
    "shot_campus_trail.png": ("board_campus_changes.png", (0.0, 0.0, 0.615, 0.70)),
    "shot_pantry_trail.png": ("board_pantry_changes.png", (0.0, 0.0, 0.615, 0.78)),
    "shot_pantry_stock.png": ("board_pantry_stock.png", (0.0, 0.0, 0.615, 0.70)),
}


def crop_panels() -> None:
    """Crop the panels the deck, the poster and the docx use, then drop the raw captures."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    for name, (source, (x0, y0, x1, y1)) in CROPS.items():
        with Image.open(OUT / source) as im:
            w, h = im.size
            im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))).save(OUT / name, optimize=True)
    for raw in OUT.glob("board_*.png"):
        raw.unlink()


def main() -> int:
    OUT.mkdir(exist_ok=True)
    base = f"http://127.0.0.1:{PORT}/"
    work = Path(tempfile.mkdtemp(prefix="planb_shots_"))
    prepared = prepare(work / "demo")
    env = {**os.environ, "PLAN_B_MODERATOR_CODE": CODE}
    cmd = [sys.executable, "-m", "plan_b.cli", "serve", "--port", str(PORT)]
    cmd += ["--var", str(prepared.state), "--replay-dir", str(prepared.replays)]
    server = subprocess.Popen(cmd, cwd=APP, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(80):
            try:
                api(base, "api/health")
                break
            except OSError:
                time.sleep(0.25)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(viewport=SIZE, device_scale_factor=2)
            page = ctx.new_page()
            page.goto(base)
            page.get_by_label("Moderator code").fill(CODE)
            page.get_by_role("button", name="Sign in as moderator").click()
            expect(page.get_by_role("heading", name="Moderator controls")).to_be_visible()

            load_case(page, "dev01")
            page.screenshot(path=str(OUT / "board_campus_start.png"))
            run_minutes(page, 5)
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(OUT / "board_campus_after.png"))
            page.screenshot(path=str(OUT / "board_campus_full.png"), full_page=True)
            view_at(page, "What changed and what the app did", OUT / "board_campus_changes.png")
            view_at(page, "Current schedule", OUT / "board_campus_schedule.png")

            load_case(page, "pantry_dev01")
            run_minutes(page, 10)
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(OUT / "board_pantry.png"))
            page.screenshot(path=str(OUT / "board_pantry_full.png"), full_page=True)
            view_at(page, "What changed and what the app did", OUT / "board_pantry_changes.png")
            view_at(page, "Stock and service", OUT / "board_pantry_stock.png")

            replay = ctx.new_page()
            replay.goto(base + "#/replay")
            replay.get_by_role("button", name="live_p2-live_dev02_trace.json", exact=True).click()
            replay.wait_for_timeout(1500)
            final = replay.get_by_role("button", name="Final recorded state")
            if final.count():
                final.click()
                replay.wait_for_timeout(1200)
            replay.screenshot(path=str(OUT / "board_replay_live.png"))
            view_at(replay, "What changed and what the app did", OUT / "board_replay_decisions.png")
            browser.close()
    finally:
        try:
            stop(server)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    crop_panels()
    print("saved:", ", ".join(sorted(p.name for p in OUT.glob("shot_*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
