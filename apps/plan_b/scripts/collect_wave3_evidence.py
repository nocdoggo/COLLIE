"""Regenerate the Wave 3 packet evidence from the current checkout, with no paid call.

Usage (from apps/plan_b, after `uv sync --all-groups` and `npm ci` in web/):

    uv run python scripts/collect_wave3_evidence.py --out <evidence-dir> [--skip-browser]

Runs the full battery and the Wave 3 checks, and writes into <evidence-dir>:

* ``reports/checks.json``: every command, working directory, exit code, duration and summary
  (ruff, format, mypy, pytest with a JUnit XML, web typecheck/build/test/lint, ``run-case all``,
  ``verify-freeze --require-heldout``, the held-out reports recomputed from the committed raw
  records, the release build, both walkthroughs, the storyboard, the keyboard check, the three
  rehearsals, and the scans below), plus the pytest and web test counts and the case lines;
* ``reports/wave1_parity.json``: the dev01-dev06 result lines against the Wave 1 evidence;
* ``reports/results_recomputed.json``: for each suite, whether ``plan-b eval report`` run on the
  committed raw records reproduces the committed ``report/`` byte for byte;
* ``reports/results_summary.json``: the counts the packet cites, read from the committed
  ``metrics.json`` (met over recorded per policy and class, by-case all-trials-met, statuses,
  violations, unnecessary changes, provider-reported USD), so every number is traceable;
* ``reports/environment.json``: tool versions, git head and branch, whether the app tree is clean;
* ``rehearsal/rehearsal_report.json`` (``tests/e2e/rehearsal.py``);
* ``browser/``: the JSON reports of both walkthroughs, the storyboard and the keyboard check
  (their frames are not kept: the Wave 2 packet holds the storyboard frames);
* ``release/release_report.json``: the release build's checks (``scripts/build_release.py``);
  the package itself is built in a temporary directory and removed.

The held-out reports are recomputed into a temporary directory; nothing under the results
directory is written. No model is called: the rehearsals' forced failure points the provider at a
closed port on 127.0.0.1 with a placeholder key and a temporary ledger. Local paths are written as
placeholders, and the credential and identifier scans of ``collect_wave2_evidence.py`` and
``collect_evidence.py`` apply to every text file written. Nothing here reads credentials.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import collect_evidence as ce
import collect_wave2_evidence as w2

APP = ce.APP
REPO = ce.REPO
RESULTS = APP / "evaluation/results/wave3_heldout_20261025T1625Z"
SUITES = ("campus", "pantry")
CLASSES = {
    "campus": ("goal_completion", "appropriate_infeasibility"),
    "pantry": ("target_attainment", "supported_partial"),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="a new or empty evidence directory")
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
    for sub in ("reports", "rehearsal", "browser", "release"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="planb_w3_evidence_"))
    try:
        return collect(out, work, skip_browser=args.skip_browser, allowed=allowed)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def same_tree(a: Path, b: Path) -> list[str]:
    """Files that differ between two directories (missing on either side included)."""
    names = sorted({p.name for p in a.iterdir()} | {p.name for p in b.iterdir()})
    return [
        n
        for n in names
        if not ((a / n).is_file() and (b / n).is_file() and filecmp.cmp(a / n, b / n, False))
    ]


def results_summary() -> dict[str, Any]:
    summary: dict[str, Any] = {"results": str(RESULTS.relative_to(REPO)), "suites": {}}
    for suite in SUITES:
        m = json.loads((RESULTS / suite / "report/metrics.json").read_text(encoding="utf-8"))
        policies: dict[str, Any] = {}
        for policy, p in m["by_policy"].items():
            met = sum(p[c]["k"] for c in CLASSES[suite])
            policies[policy] = {
                "met": met,
                "recorded": p["recorded"],
                "planned": p["planned"],
                "classes": {c: f"{p[c]['k']}/{p[c]['n']}" for c in CLASSES[suite]},
                "statuses": p["statuses"],
                "executed_violations": p["executed_violations"],
                "invalid_attempts": p["invalid_attempts"],
                "unnecessary_changes": p.get("unnecessary_changes"),
                "cost_usd": round(p["computation"]["cost_usd"], 6),
                "model_calls": p["computation"]["model_calls"],
            }
        cases: dict[str, dict[str, list[bool]]] = {}
        for e in m["episodes"]:
            cases.setdefault(e["case_id"], {}).setdefault(e["policy"], []).append(e["success"])
        by_case = {
            policy: sum(1 for c in cases.values() if all(c.get(policy, [False])))
            for policy in m["by_policy"]
        }
        summary["suites"][suite] = {
            "episodes_recorded": len(m["episodes"]),
            "missing": m["missing"],
            "aborted": m["aborted"],
            "cases": len(cases),
            "by_policy": policies,
            "cases_with_all_trials_met": by_case,
            "per_case_met": {
                case: {pol: f"{sum(v)}/{len(v)}" for pol, v in sorted(row.items())}
                for case, row in sorted(cases.items())
            },
        }
    return summary


def collect(out: Path, work: Path, *, skip_browser: bool, allowed: Sequence[str] = ()) -> int:
    checks: list[dict[str, Any]] = []
    uv = ["uv", "run"]
    web = APP / "web"
    (work / "tmp").mkdir()
    ce._CHILD_ENV.clear()
    ce._CHILD_ENV.update({k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
    ce._CHILD_ENV["TMPDIR"] = str(work / "tmp")
    ce._PLACEHOLDERS[:] = ce.placeholders(out, work, Path.home())

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

    cases = ce.run(
        uv
        + ["plan-b", "run-case", "all", "--db", str(work / "runs.sqlite3")]
        + ["--out", str(work / "out")],
        APP,
        checks,
        "plan-b run-case all",
    )
    outcomes = ce.case_lines(cases.stdout)
    wave1 = json.loads(w2.WAVE1_CHECKS.read_text(encoding="utf-8"))["case_outcomes"]
    parity = {
        ref: {
            "wave_1": wave1.get(ref),
            "now": outcomes.get(ref),
            "same": wave1.get(ref) == outcomes.get(ref),
        }
        for ref in w2.WAVE1_CASES
    }
    (out / "reports" / "wave1_parity.json").write_text(json.dumps(parity, indent=2) + "\n")
    checks.append(
        w2.json_check(
            "Wave 1 case lines unchanged",
            [f"{ref} differs from Wave 1" for ref, p in parity.items() if not p["same"]]
            + ([] if len(outcomes) == 9 else [f"{len(outcomes)} case lines, expected 9"]),
            "9 case lines; dev01, dev02, dev04, dev05 and dev06 print the Wave 1 evidence lines",
        )
    )

    ce.run(
        uv + ["plan-b", "eval", "verify-freeze", "--require-heldout"],
        APP,
        checks,
        "plan-b eval verify-freeze --require-heldout",
    )
    recomputed: dict[str, Any] = {}
    for suite in SUITES:
        dest = work / "report" / suite
        ce.run(
            uv
            + ["plan-b", "eval", "report", "--results", str(RESULTS / suite), "--out", str(dest)],
            APP,
            checks,
            f"plan-b eval report ({suite}, from the committed raw records)",
        )
        differ = same_tree(dest, RESULTS / suite / "report") if dest.is_dir() else ["(not written)"]
        recomputed[suite] = {"identical": not differ, "differing_files": differ}
    (out / "reports" / "results_recomputed.json").write_text(
        json.dumps(recomputed, indent=2) + "\n"
    )
    checks.append(
        w2.json_check(
            "held-out reports recomputed byte for byte",
            [f"{s}: {r['differing_files']}" for s, r in recomputed.items() if not r["identical"]],
            "campus and pantry report/ (metrics.json, evaluation_results.md, figure.svg) reproduce",
        )
    )
    summary = results_summary()
    (out / "reports" / "results_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    release = work / "release"
    ce.run(
        uv + ["python", "scripts/build_release.py", "--out", str(release)],
        APP,
        checks,
        "release package build, startup and replay (scripts/build_release.py)",
    )
    if (release / "release_report.json").exists():
        text = ce.redact((release / "release_report.json").read_text(encoding="utf-8"))
        (out / "release" / "release_report.json").write_text(text)

    if not skip_browser:
        browser = work / "browser"
        runs = (
            ("walkthrough.py", "w1", "browser walkthrough, Wave 1 (Playwright, Chromium)"),
            ("walkthrough_wave2.py", "w2", "browser walkthrough, Wave 2 (Playwright, Chromium)"),
            ("storyboard.py", "story", "demo storyboard (Playwright, Chromium)"),
            ("keyboard.py", "keyboard", "keyboard and comprehension (Playwright, Chromium)"),
        )
        for script, sub, name in runs:
            extra = ["--port", str(w2.free_port())] if script == "storyboard.py" else []
            ce.run(
                uv + ["python", f"tests/e2e/{script}", "--out", str(browser / sub)] + extra,
                APP,
                checks,
                name,
            )
            for report in sorted((browser / sub).glob("*.json")):
                shutil.copy2(report, out / "browser" / f"{sub}_{report.name}")
        ce.run(
            uv + ["python", "tests/e2e/rehearsal.py", "--out", str(out / "rehearsal")],
            APP,
            checks,
            "three automated rehearsals, one with a forced provider failure (Playwright)",
        )

    def version(cmd: list[str], cwd: Path = APP) -> str:
        try:
            return ce.subprocess.run(  # noqa: S603
                cmd, cwd=cwd, capture_output=True, text=True, env=ce._CHILD_ENV
            ).stdout.strip()
        except OSError:
            return "unavailable"

    env = {
        "python": sys.version.split()[0],
        "platform": ce.platform.platform(),
        "uv": version(["uv", "--version"]),
        "node": version(["node", "--version"]),
        "npm": version(["npm", "--version"]),
        "playwright": version(uv + ["playwright", "--version"]),
        "git_head": version(["git", "rev-parse", "HEAD"], REPO),
        "git_branch": version(["git", "branch", "--show-current"], REPO) or "(detached HEAD)",
        "app_tree_clean": not version(["git", "status", "--porcelain", "--", "apps/plan_b"], REPO),
    }
    (out / "reports" / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    record = {
        "pytest_counts": w2.junit_counts(junit),
        "web_test_counts": ce.tap_counts(web_tests.stdout),
        "case_outcomes": outcomes,
        "paid_calls": 0,
        "checks": checks,
    }
    checks.append(w2.credential_scan(out))
    print(f"[{'ok' if checks[-1]['exit_code'] == 0 else 'FAIL'}] evidence credential pattern scan")
    local = [path for path, _ in ce._PLACEHOLDERS] + [os.path.join(tempfile.gettempdir(), "")]
    scan = ce.scan_check(out, record, local, ce.local_names(), allowed)
    checks.append(scan)
    print(f"[{'ok' if scan['exit_code'] == 0 else 'FAIL'}] evidence identifier scan")
    (out / "reports" / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
    failed = [c["name"] for c in checks if c["exit_code"] != 0]
    print("all checks passed" if not failed else f"FAILED: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
