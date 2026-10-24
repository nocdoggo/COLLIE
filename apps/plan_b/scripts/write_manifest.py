"""Write the Wave 1 packet's manifest.json from the evidence directory and read-only git.

Usage (from apps/plan_b, after scripts/collect_evidence.py has written the evidence):

    uv run python scripts/write_manifest.py [--packet DIR] [--evidence DIR] [--out FILE]
                                            [--baseline REV]

Defaults: ``--packet`` is PEEAI_plan/handoffs/wave_1, ``--evidence`` is <packet>/evidence,
``--out`` is <packet>/manifest.json and ``--baseline`` is 65997ac (the planning package). Evidence
paths in the manifest are written as ``evidence/<path>``, where the packet publishes them.

Nothing in the manifest is typed in. It is read from the evidence and from git:

* the commits ``baseline..HEAD`` with author, committer, subject, trailers and the areas they
  touch; whether HEAD is pushed (its upstream or another remote-tracking branch contains it, as of
  the last fetch: local refs only, no network call); whether the app changed after the evidence;
* every recorded check with its exit code, the identifier scan's exempted words
  (``--allow-identifier``) and the names it did not scan for, the pytest and web test counts, the
  walkthrough totals and its minimum-visible-workflow steps, and each development case's public
  outcome and result line;
* the fixture, lockfile and migration hashes, and the versions the traces and the code name;
* the sha256, size and visibility of every evidence file (``runner_private/`` is
  ``evaluator_private``, everything else ``public``);
* M1. Its status is ``passed_on_recorded_automated_checks`` only when every recorded check
  exited 0, the browser walkthrough is among them and every one of its checks passed, the evidence
  the wave plan requires is present, the evidence came from a clean app tree, and the app is
  unchanged between the evidence commit and HEAD. Otherwise it is ``failed``, with the reasons.
  It is always self-assessed; the independent audit is ``pending``.

Git is only read (rev-parse, rev-list, show, diff-tree, diff --quiet, cat-file -e, branch
--show-current, branch -r --contains, merge-base --is-ancestor).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
PACKET = REPO / "PEEAI_plan" / "handoffs" / "wave_1"
BASELINE = "65997ac"
COMPLETION_RECORD = "VERIFICATION.md"
WALKTHROUGH_SCRIPT = "tests/e2e/walkthrough.py"
PASSED = "passed_on_recorded_automated_checks"
# A git runner: arguments after "git" -> (exit code, stripped stdout).
Git = Callable[..., tuple[int, str]]


def git_in(repo: Path) -> Git:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}

    def git(*args: str) -> tuple[int, str]:
        proc = subprocess.run(  # noqa: S603
            ["git", *args], cwd=repo, capture_output=True, text=True, env=env
        )
        return proc.returncode, proc.stdout.strip()

    return git


def must(git: Git, *args: str) -> str:
    code, out = git(*args)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} exited {code}")
    return out


def load(path: Path) -> Any:
    return json.loads(path.read_text()) if path.is_file() else None


def area(path: str) -> str:
    """The first two components of a path with three or more ("apps/plan_b"), else the path."""
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else path


def commits(git: Git, base: str, head: str) -> list[dict[str, Any]]:
    # NUL-separated: str.strip() would eat a trailing \x1f before an empty trailers field.
    fmt = "%H%x00%an <%ae>%x00%cn <%ce>%x00%cI%x00%s%x00%(trailers:only,unfold)"
    out = []
    for commit in must(git, "rev-list", "--reverse", f"{base}..{head}").split():
        cid, author, committer, when, subject, trailers = must(
            git, "show", "-s", f"--format={fmt}", commit
        ).split("\x00")
        paths = must(git, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit)
        out.append(
            {
                "id": cid,
                "author": author,
                "committer": committer,
                "committed_at": when,
                "subject": subject,
                "trailers": [line for line in trailers.splitlines() if line.strip()],
                "areas": sorted({area(p) for p in paths.splitlines() if p}),
            }
        )
    return out


def repository(git: Git, baseline: str, evidence_head: str | None) -> dict[str, Any]:
    base = must(git, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    head = must(git, "rev-parse", "HEAD")
    history = commits(git, base, head)
    code, upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    tracking = upstream if code == 0 and upstream else None
    upstream_has_head = (
        git("merge-base", "--is-ancestor", head, tracking)[0] == 0 if tracking else None
    )
    code, remote = git("branch", "-r", "--contains", head, "--format=%(refname:short)")
    remotes = [line for line in remote.splitlines() if line] if code == 0 else []
    app_changed: bool | None = None
    if evidence_head and git("cat-file", "-e", f"{evidence_head}^{{commit}}")[0] == 0:
        code, _ = git("diff", "--quiet", evidence_head, head, "--", str(APP.relative_to(REPO)))
        app_changed = {0: False, 1: True}.get(code)
    return {
        "branch": git("branch", "--show-current")[1] or "(detached HEAD)",
        "head": head,
        "planning_baseline_commit": base,
        "commits": history,
        "authors": sorted({c["author"] for c in history}),
        "committers": sorted({c["committer"] for c in history}),
        "commits_with_trailers": [c["id"] for c in history if c["trailers"]],
        "evidence_generated_at_commit": evidence_head,
        "app_changed_since_evidence": app_changed,
        "packet_commit": "the commit that adds this manifest (a file cannot name its own commit)",
        "upstream": tracking,
        "upstream_contains_head": upstream_has_head,
        "remote_branches_containing_head": remotes,
        "pushed": bool(upstream_has_head) or bool(remotes),
    }


def evidence_files(evidence: Path) -> dict[str, dict[str, Any]]:
    files = {}
    for p in sorted(evidence.rglob("*")):
        if p.is_file():
            rel = p.relative_to(evidence)
            files[f"evidence/{rel.as_posix()}"] = {
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
                "visibility": "evaluator_private" if rel.parts[0] == "runner_private" else "public",
            }
    return files


def result_lines(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each case's `plan-b run-case` result line, from checks.json (recorded or in the summary)."""
    if record.get("case_outcomes"):
        return dict(record["case_outcomes"])
    cases: dict[str, dict[str, Any]] = {}
    for check in record.get("checks", []):
        if check["name"] == "plan-b run-case all":
            for line in check["summary"]:
                ref, sep, rest = line.partition(": ")
                if sep and "=" in rest:
                    pairs = (pair.split("=", 1) for pair in rest.split() if "=" in pair)
                    cases[ref] = {k: {"True": True, "False": False}.get(v, v) for k, v in pairs}
    return cases


def development_cases(evidence: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    lines = result_lines(record)
    reports = {
        p.name.split("_outcome")[0]: p
        for p in sorted((evidence / "reports").glob("*_outcome.public.json"))
    }
    cases = []
    for ref in sorted(set(reports) | set(lines)):
        report = load(reports[ref]) if ref in reports else {}
        trace = evidence / "traces" / f"{ref}_trace.json"
        cases.append(
            {
                "case_ref": ref,
                "goal_complete": report.get("goal_complete"),
                "infeasibility_reported": report.get("infeasibility_reported"),
                "applied_plans": report.get("applied_plans"),
                "committed_cents": report.get("committed_cents"),
                "reserved_cents_at_end": report.get("reserved_cents_at_end"),
                "violations": len(report["violations"]) if "violations" in report else None,
                "rejected_receipts": report.get("rejected_receipts"),
                "rejected_attempts_without_receipt": report.get(
                    "rejected_attempts_without_receipt"
                ),
                "matches_expectation": lines.get(ref, {}).get("matches_expectation"),
                "public_report": f"evidence/reports/{reports[ref].name}"
                if ref in reports
                else None,
                "trace": f"evidence/traces/{trace.name}" if trace.is_file() else None,
            }
        )
    return cases


def web_test_counts(record: dict[str, Any]) -> dict[str, int]:
    if record.get("web_test_counts"):
        return dict(record["web_test_counts"])
    counts = {}
    for check in record.get("checks", []):
        if check["name"] == "web tests":
            for line in check["summary"]:
                parts = line.split()
                if len(parts) == 3 and parts[0] == "#" and parts[2].isdigit():
                    counts[parts[1]] = int(parts[2])
    return counts


def walkthrough_summary(walk: dict[str, Any] | None) -> dict[str, Any] | None:
    if walk is None:
        return None
    checks = walk.get("checks", [])
    return {
        "browser": walk.get("browser"),
        "checks_total": len(checks),
        "checks_passed": sum(1 for c in checks if c["passed"]),
        "failed_checks": [c["check"] for c in checks if not c["passed"]],
        "minimum_visible_workflow": [
            {
                "step": s["step"],
                "title": s["title"],
                "checks": len(s["checks"]),
                "passed": s["passed"],
            }
            for s in walk.get("minimum_visible_workflow", [])
        ],
        "screenshots": len(walk.get("screenshots", [])),
        "report": "evidence/screenshots/walkthrough_report.json",
    }


def required_evidence(
    evidence: Path, packet: Path, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The evidence the wave plan's M1 paragraph asks to retain, found in the evidence itself."""

    def traced(pred: Callable[[dict[str, Any]], bool]) -> list[str]:
        return [c["trace"] for c in cases if c["trace"] and pred(c)]

    rejected = [
        f"evidence/traces/{p.name}"
        for p in sorted((evidence / "traces").glob("*.json"))
        if any(r.get("status") == "rejected" for r in (load(p) or {}).get("receipts", []))
    ]
    hashes = evidence / "reports" / "fixture_hashes.json"
    items = [
        ("fixture hashes", ["evidence/reports/fixture_hashes.json"] if hashes.is_file() else []),
        (
            "a successful trace",
            traced(lambda c: c["goal_complete"] is True and c["violations"] == 0),
        ),
        ("a rejected-action trace", rejected),
        ("an impossible-case trace", traced(lambda c: c["infeasibility_reported"] is True)),
        (
            "an M1 completion record",
            [COMPLETION_RECORD] if (packet / COMPLETION_RECORD).is_file() else [],
        ),
    ]
    return [{"item": item, "evidence": paths, "present": bool(paths)} for item, paths in items]


def m1(
    record: dict[str, Any],
    walk: dict[str, Any] | None,
    required: list[dict[str, Any]],
    env: dict[str, Any],
    repo: dict[str, Any],
) -> dict[str, Any]:
    checks = record.get("checks", [])
    failed = [c["name"] for c in checks if c.get("exit_code") != 0]
    walked = any(WALKTHROUGH_SCRIPT in c.get("command", "") for c in checks)
    walk_checks = (walk or {}).get("checks", [])
    walk_failed = [c["check"] for c in walk_checks if not c["passed"]]
    missing = [r["item"] for r in required if not r["present"]]
    conditions = [
        ("checks were recorded", bool(checks), "no checks were recorded"),
        ("every recorded check exited 0", not failed, f"checks exited non-zero: {failed}"),
        ("the browser walkthrough is a recorded check", walked, "no walkthrough check recorded"),
        (
            "every walkthrough check passed",
            bool(walk_checks) and not walk_failed,
            f"walkthrough checks failed: {walk_failed}" if walk_checks else "no walkthrough checks",
        ),
        ("the required evidence is present", not missing, f"required evidence missing: {missing}"),
        (
            "the evidence came from a clean app tree",
            env.get("app_tree_clean") is True,
            "the evidence run had uncommitted app changes (environment.app_tree_clean is not true)",
        ),
        (
            "the app is unchanged between the evidence commit and HEAD",
            repo["app_changed_since_evidence"] is False,
            "the app changed after the evidence commit, or that commit is not in this repository",
        ),
    ]
    reasons = [reason for _, met, reason in conditions if not met]
    return {
        "status": "failed" if reasons else PASSED,
        "self_assessed": True,
        "independent_audit": "pending",
        "conditions": [{"condition": name, "met": bool(met)} for name, met, _ in conditions],
        "reasons": reasons,
        "required_evidence": required,
        "record": COMPLETION_RECORD,
    }


def versions(evidence: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    from plan_b.domain.models import RUNTIME_VERSION
    from plan_b.evaluation.policies.parser import PARSER_VERSION

    traces = [load(p) or {} for p in sorted((evidence / "traces").glob("*.json"))]
    reports = [
        load(evidence / c["public_report"].removeprefix("evidence/")) or {}
        for c in cases
        if c["public_report"]
    ]
    policies = {t.get("source", {}).get("policy_id") for t in traces} | {
        r.get("policy_id") for r in reports
    }
    schema = load(REPO / "PEEAI_plan" / "schemas" / "planning.schema.json") or {}
    project = tomllib.loads((APP / "pyproject.toml").read_text())["project"]

    def named(key: str) -> list[str]:
        return sorted({str(t[key]) for t in traces if t.get(key) is not None})

    return {
        "recorded": {
            "runtime": named("runtime_version"),
            "trace": named("trace_version"),
            "trace_kind": named("kind"),
            "policies": sorted(p for p in policies if p),
        },
        "code": {
            "app_package": f"{project['name']} {project['version']}",
            "runtime": RUNTIME_VERSION,
            "parser": PARSER_VERSION,
            "planning_schema": schema.get("$id"),
        },
    }


def build_manifest(evidence: Path, packet: Path, baseline: str, git: Git) -> dict[str, Any]:
    reports = evidence / "reports"
    record = load(reports / "checks.json") or {}
    env = load(reports / "environment.json") or {}
    walk = load(evidence / "screenshots" / "walkthrough_report.json")
    steps = load(reports / "rejected_actions_steps.json") or {}
    cases = development_cases(evidence, record)
    repo = repository(git, baseline, env.get("git_head"))
    counts = dict(record.get("pytest_counts", {}))
    if "tests" in counts:
        counts["passed"] = counts["tests"] - sum(
            counts.get(k, 0) for k in ("failures", "errors", "skipped")
        )
    return {
        "manifest_version": "1.0.0",
        "packet": "plan_b_wave_1_handoff",
        "project": "Plan B: The Show Must Go On (fictional local sandbox)",
        "repository": repo,
        "versions": versions(evidence, cases),
        "environment": env,
        "fixtures_and_locks": load(reports / "fixture_hashes.json"),
        "checks": [
            {
                "name": c["name"],
                "cwd": c["cwd"],
                "command": c["command"],
                "exit_code": c["exit_code"],
                "seconds": c.get("seconds"),
                "last_line": c["summary"][-1] if c["summary"] else "",
            }
            for c in record.get("checks", [])
        ],
        "identifier_scan": record.get("identifier_scan"),
        "pytest_counts": counts,
        "web_test_counts": web_test_counts(record),
        "browser_walkthrough": walkthrough_summary(walk),
        "development_cases": cases,
        "rejection_steps": {
            "steps": len(steps.get("steps", [])),
            "report": "evidence/reports/rejected_actions_steps.json" if steps else None,
        },
        "m1": m1(record, walk, required_evidence(evidence, packet, cases), env, repo),
        "evidence_files": evidence_files(evidence),
    }


def main(argv: list[str] | None = None, git: Git | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--evidence", type=Path, default=None, help="default: <packet>/evidence")
    parser.add_argument("--out", type=Path, default=None, help="default: <packet>/manifest.json")
    parser.add_argument("--baseline", default=BASELINE)
    args = parser.parse_args(argv)
    packet = args.packet.resolve()
    evidence = (args.evidence or packet / "evidence").resolve()
    out = (args.out or packet / "manifest.json").resolve()
    if not (evidence / "reports" / "checks.json").is_file():
        print(f"no reports/checks.json under {evidence}", file=sys.stderr)
        return 2
    manifest = build_manifest(evidence, packet, args.baseline, git or git_in(REPO))
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    status = manifest["m1"]["status"]
    print(f"wrote {out.name}: {len(manifest['evidence_files'])} evidence files, M1 {status}")
    for reason in manifest["m1"]["reasons"]:
        print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
