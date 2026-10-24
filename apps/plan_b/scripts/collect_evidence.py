"""Regenerate the Wave 1 evidence set from the current checkout.

Usage (from apps/plan_b, after `uv sync --all-groups` and `npm ci` in web/):

    uv run python scripts/collect_evidence.py --out <evidence-dir>

Runs the checks and the development cases, and writes into <evidence-dir>:

* ``reports/checks.json``: every command, working directory, exit code, duration and summary
  (ruff, format, mypy, pytest with a JUnit XML, web typecheck/build/test/lint, CLI runs,
  trace verification, the browser walkthrough);
* ``reports/*_outcome.public.json``: public outcome summaries (no predicates);
* ``reports/rejected_actions_steps.json``: expected versus actual code for each rejection step;
* ``reports/fixture_hashes.json``, ``reports/environment.json``;
* ``traces/``: sanitized traces (successful dev01, paid-booking dev02, impossible dev05, and the
  rejected-actions run);
* ``screenshots/``: walkthrough screenshots (re-encoded as 256-colour PNGs to keep the packet
  small; the walkthrough's checks read the live page, not the images) and its JSON report;
* ``runner_private/``: runner-side outcome reports *with* predicates and expectations. These
  are evaluator outputs, kept apart from every public artifact.

Absolute local paths are written as ``<repo>``, ``<evidence>``, ``<work>`` or ``~``. Nothing here
reads credentials or makes network calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
TRACES_KEPT = ("dev01", "dev02", "dev05")
_PLACEHOLDERS: list[tuple[str, str]] = []


def redact(text: str) -> str:
    for path, label in _PLACEHOLDERS:
        text = text.replace(path, label)
    return text


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantize_png(src: Path, dst: Path) -> None:
    """Re-encode a screenshot as a 256-colour PNG (median cut, no dithering)."""
    from PIL import Image

    with Image.open(src) as image:
        palette = image.convert("RGB").quantize(
            colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )
        palette.save(dst, optimize=True)


def run(
    cmd: list[str], cwd: Path, checks: list[dict[str, Any]], name: str
) -> subprocess.CompletedProcess[str]:
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)  # noqa: S603
    out = (proc.stdout + proc.stderr).strip().splitlines()
    checks.append(
        {
            "name": name,
            "command": redact(" ".join(cmd)),
            "cwd": str(cwd.relative_to(REPO)) if cwd.is_relative_to(REPO) else str(cwd),
            "exit_code": proc.returncode,
            "seconds": round(time.monotonic() - t0, 1),
            "summary": [redact(line) for line in out if line.strip()][-6:],
        }
    )
    print(f"[{'ok' if proc.returncode == 0 else 'FAIL'}] {name}")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    for sub in ("reports", "traces", "screenshots", "runner_private"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    uv = ["uv", "run"]
    web = APP / "web"
    work = Path(tempfile.mkdtemp(prefix="planb_evidence_"))
    # Longest first, so a path inside another is replaced by its own label.
    _PLACEHOLDERS[:] = sorted(
        [(str(out), "<evidence>"), (str(work), "<work>"), (str(REPO), "<repo>")]
        + [(str(Path.home()), "~")],
        key=lambda pair: -len(pair[0]),
    )

    run(uv + ["ruff", "check", "."], APP, checks, "ruff check")
    run(uv + ["ruff", "format", "--check", "."], APP, checks, "ruff format --check")
    run(uv + ["mypy"], APP, checks, "mypy (strict defs)")
    run(["npm", "run", "typecheck"], web, checks, "web typecheck")
    run(["npm", "run", "build"], web, checks, "web build")
    # pytest runs after the build so the bundle-privacy test has a bundle to scan.
    junit = out / "reports" / "pytest_junit.xml"
    run(
        uv + ["pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
        APP,
        checks,
        "pytest",
    )
    if junit.exists():
        junit.write_text(redact(junit.read_text()))
    run(["npm", "test"], web, checks, "web tests")
    run(["npm", "run", "lint"], web, checks, "web boundary lint")

    runs_out = work / "out"
    run(
        uv
        + ["plan-b", "run-case", "all", "--db", str(work / "runs.sqlite3"), "--out", str(runs_out)],
        APP,
        checks,
        "plan-b run-case all",
    )
    run(
        uv
        + ["plan-b", "demo-rejections", "--db", str(work / "demo.sqlite3"), "--out", str(runs_out)],
        APP,
        checks,
        "plan-b demo-rejections",
    )
    for trace in sorted((runs_out / "traces").glob("*.json")):
        run(uv + ["plan-b", "verify-trace", str(trace)], APP, checks, f"verify-trace {trace.name}")
    for ref in TRACES_KEPT:
        shutil.copy2(
            runs_out / "traces" / f"{ref}_trace.json", out / "traces" / f"{ref}_trace.json"
        )
    shutil.copy2(runs_out / "traces" / "rejected_actions_trace.json", out / "traces")
    for report in sorted((runs_out / "reports").glob("*.json")):
        shutil.copy2(report, out / "reports" / report.name)
    for report in sorted((runs_out / "private").glob("*.json")):
        shutil.copy2(report, out / "runner_private" / report.name)

    if not args.skip_browser:
        shots = work / "shots"
        run(
            uv + ["python", "tests/e2e/walkthrough.py", "--out", str(shots)],
            APP,
            checks,
            "browser walkthrough (Playwright, Chromium)",
        )
        for shot in sorted(shots.glob("*")):
            if shot.suffix == ".png":
                quantize_png(shot, out / "screenshots" / shot.name)
            else:
                shutil.copy2(shot, out / "screenshots" / shot.name)

    junit_text = junit.read_text() if junit.exists() else ""
    counts = {}
    for key in ("tests", "failures", "errors", "skipped"):
        mm = re.search(rf'{key}="(\d+)"', junit_text)
        if mm:
            counts[key] = int(mm.group(1))

    hashes = {
        "public_fixture": {
            "path": "apps/plan_b/plan_b/scenarios/public/campus_showcase.json",
            "sha256": sha256(APP / "plan_b/scenarios/public/campus_showcase.json"),
        },
        "private_cases": {
            p.name: sha256(p) for p in sorted((APP / "plan_b/scenarios/private").glob("*.json"))
        },
        "planning_examples": {
            p.name: sha256(p) for p in sorted((REPO / "PEEAI_plan/examples").glob("*.json"))
        },
        "planning_schema": sha256(REPO / "PEEAI_plan/schemas/planning.schema.json"),
        "lockfiles": {
            "apps/plan_b/uv.lock": sha256(APP / "uv.lock"),
            "apps/plan_b/web/package-lock.json": sha256(web / "package-lock.json"),
        },
        "migrations": {
            p.name: sha256(p) for p in sorted((APP / "plan_b/store/migrations").glob("*.sql"))
        },
    }
    (out / "reports" / "fixture_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")

    def version(cmd: list[str], cwd: Path = APP) -> str:
        try:
            return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout.strip()  # noqa: S603
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
    (out / "reports" / "checks.json").write_text(
        json.dumps({"pytest_counts": counts, "checks": checks}, indent=2) + "\n"
    )
    shutil.rmtree(work, ignore_errors=True)
    failed = [c["name"] for c in checks if c["exit_code"] != 0]
    print("all checks passed" if not failed else f"FAILED: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
