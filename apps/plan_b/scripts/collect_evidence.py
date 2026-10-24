"""Regenerate the Wave 1 evidence set from the current checkout.

Usage (from apps/plan_b, after `uv sync --all-groups` and `npm ci` in web/):

    uv run python scripts/collect_evidence.py --out <evidence-dir>

Runs the checks and the development cases, and writes into <evidence-dir>:

* ``reports/checks.json``: every command, working directory, exit code, duration and summary
  (ruff, format, mypy, pytest with a JUnit XML, web typecheck/build/test/lint, CLI runs,
  trace verification, the browser walkthrough, the identifier scan below), plus the pytest and
  web test counts and each development case's result line;
* ``reports/*_outcome.public.json``: public outcome summaries (no predicates);
* ``reports/rejected_actions_steps.json``: expected versus actual code for each rejection step;
* ``reports/fixture_hashes.json``, ``reports/environment.json``;
* ``traces/``: sanitized traces (successful dev01, paid-booking dev02, impossible dev05, and the
  rejected-actions run);
* ``screenshots/``: walkthrough screenshots (re-encoded as 256-colour PNGs to keep the packet
  small; the walkthrough's checks read the live page, not the images) and its JSON report;
* ``runner_private/``: runner-side outcome reports *with* predicates and expectations. These
  are evaluator outputs, kept apart from every public artifact.

Absolute local paths are written as ``<repo>``, ``<evidence>``, ``<work>`` or ``~``, and the
JUnit XML carries ``hostname="<host>"`` and no run timestamp. The last check scans every text file
written for local paths, this host's name, the user name and the git user.email (any case,
wherever no letter is next to it: ``ann_cache`` and ``box2`` count for ``ann`` and ``box``,
``label`` does not count for ``lab``). The host and user names are searched for with those
placeholders blanked out (``~`` only where it stands for the home directory, as ``~`` or ``~/``),
so a host named ``host`` is not found in ``<host>``; the email is searched for as written, so a
``~`` in its local part never hides it. A host or user name
that is an ordinary word can be exempted with ``--allow-identifier WORD`` (repeatable); checks.json
records every exempted word and which names were therefore not scanned. The git email cannot be
exempted. Every command runs with its temp directory inside ``<work>``, which is removed at the
end, so the run leaves no temp directory behind. ``<evidence-dir>`` must be a new or empty
directory, so no stale file is published with the new ones. Nothing here reads credentials or
makes network calls; the git email is read with ``git config user.email``.
`scripts/write_manifest.py` then writes the packet's manifest.json from this evidence.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Collection, Sequence
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
TRACES_KEPT = ("dev01", "dev02", "dev05")
MIN_NAME = 3  # shorter host or user names are not scanned for (they match too much)
# Only these can be exempted by --allow-identifier: they may be ordinary words, an email is not.
EXEMPTABLE = ("host name", "user name")
# The collector's own placeholders: for local paths (placeholders()) and the JUnit host name
# (scrub_junit()). The host and user name scan blanks them out first, so a host named "host" is
# not found in its own placeholder.
HOST_LABEL = "<host>"
HOME_LABEL = "~"
PLACEHOLDER_LABELS = ("<evidence>", "<work>", "<repo>", HOME_LABEL, HOST_LABEL)
_LETTER = r"[^\W\d_]"
# The home label as redact() writes it, in place of the home directory: a path on its own ("~")
# or the start of one ("~/"), so with no name character (letter, digit, "_", ".", "-", "~") on
# either side. Any other "~" ("a~b@example.org", "PROGRA~1") is text, not a placeholder.
_HOME_TOKEN = re.compile(r"(?<![\w.~-])~(?![\w.~-])")
_PLACEHOLDERS: list[tuple[str, str]] = []
# Environment of every command: TMPDIR inside <work>, and no inherited VIRTUAL_ENV (uv ignores a
# foreign one anyway, but warns with its path).
_CHILD_ENV: dict[str, str] = {}


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


def scrub_junit(text: str) -> str:
    """pytest's JUnit XML without local paths, the host name or the run timestamp. The
    placeholders are escaped (``&lt;repo&gt;``), so the file stays well-formed XML."""
    for path, label in _PLACEHOLDERS:
        text = text.replace(path, escape(label))
    text = re.sub(r'\shostname="[^"]*"', f' hostname="{escape(HOST_LABEL)}"', text)
    return re.sub(r'\stimestamp="[^"]*"', "", text)


def tap_counts(text: str) -> dict[str, int]:
    """The node test runner's TAP totals (``# tests N``, ``# pass N``, ...)."""
    pattern = r"^# (tests|suites|pass|fail|cancelled|skipped|todo) (\d+)$"
    return {m.group(1): int(m.group(2)) for m in re.finditer(pattern, text, re.MULTILINE)}


def case_lines(text: str) -> dict[str, dict[str, Any]]:
    """`plan-b run-case` result lines (``dev01: goal_complete=True ... violations=0 ...``)."""

    def value(raw: str) -> Any:
        if raw in ("True", "False"):
            return raw == "True"
        return int(raw) if raw.isdigit() else raw

    cases: dict[str, dict[str, Any]] = {}
    for m in re.finditer(r"^(\w+): ((?:\w+=\S+ ?)+)$", text, re.MULTILINE):
        cases[m.group(1)] = {
            key: value(raw) for key, raw in (pair.split("=", 1) for pair in m.group(2).split())
        }
    return cases


def git_email(cwd: Path = REPO) -> str:
    """The git user.email that applies in ``cwd``, read with the read-only ``git config
    user.email``, or "" when it is not set or git is missing."""
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "config", "user.email"], cwd=cwd, capture_output=True, text=True
        )
    except OSError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def local_names() -> dict[str, set[str]]:
    """This machine's host name (in full and its first label), the user name and the git
    user.email, by category."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = ""
    host = socket.gethostname()
    return {
        "host name": {host, host.split(".")[0]},
        "user name": {user},
        "git email": {git_email()},
    }


def name_patterns(
    names: dict[str, set[str]], allowed: Collection[str] = ()
) -> tuple[list[tuple[str, re.Pattern[str]]], list[str]]:
    """A case-insensitive pattern for each name, by category, that finds it wherever no letter is
    next to it (digits, ``_``, ``-`` and ``.`` do not hide a name), and the names left out
    (exempted by ``--allow-identifier``, too short or unknown), by category and reason only. Only
    the categories in ``EXEMPTABLE`` can be exempted."""
    allow = {word.casefold() for word in allowed}
    patterns: list[tuple[str, re.Pattern[str]]] = []
    skipped: set[str] = set()
    for what, values in names.items():
        for name in sorted(values):
            if not name:
                skipped.add(f"{what}: not known")
            elif what in EXEMPTABLE and name.casefold() in allow:
                skipped.add(f"{what}: allowed by --allow-identifier")
            elif len(name) < MIN_NAME:
                skipped.add(f"{what}: shorter than {MIN_NAME} characters")
            else:
                word = re.compile(rf"(?<!{_LETTER}){re.escape(name)}(?!{_LETTER})", re.IGNORECASE)
                patterns.append((what, word))
    return patterns, sorted(skipped)


def without_placeholders(text: str) -> str:
    """``text`` with the collector's own placeholders, plain or XML-escaped, replaced by a space:
    the ``<...>`` labels wherever they are, the home label ``~`` only where it is a path or starts
    one (``_HOME_TOKEN``). A space is no letter, so the blanking neither hides a name next to a
    placeholder nor joins two pieces of text into one."""
    for label in PLACEHOLDER_LABELS:
        if label != HOME_LABEL:
            text = text.replace(escape(label), " ").replace(label, " ")
    return _HOME_TOKEN.sub(" ", text)


def identifier_scan(
    out: Path,
    texts: dict[str, str],
    paths: list[str],
    names: dict[str, set[str]],
    allowed: Collection[str] = (),
) -> tuple[list[str], int]:
    """Text files under ``out`` (and ``texts``, by relative name) that hold a name in ``names``
    (see name_patterns()) or a local path, as ``<file>: <what>``, and the number of text files
    scanned. Host and user names are searched for with the collector's placeholders blanked out;
    the git email and local paths in the text as written. An address cannot hold the ``<...>``
    labels, and blanking the home ``~`` could hide one whose local part holds a ``~`` (RFC 5322
    allows it: ``~@example.org``). The values found are never reported."""
    words, _ = name_patterns(names, allowed)
    files = dict(texts)
    for p in sorted(out.rglob("*")):
        rel = str(p.relative_to(out))
        if p.is_file() and rel not in files:
            try:
                files[rel] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue  # screenshots
    found: list[str] = []
    for rel, text in files.items():
        bare = without_placeholders(text)
        hits = {
            what for what, pattern in words if pattern.search(text if what == "git email" else bare)
        }
        if any(path in text for path in paths):
            hits.add("local path")
        found += [f"{rel}: {what}" for what in sorted(hits)]
    return found, len(files)


def scan_check(
    out: Path,
    record: dict[str, Any],
    paths: list[str],
    names: dict[str, set[str]],
    allowed: Sequence[str],
) -> dict[str, Any]:
    """The 'evidence identifier scan' check. It first records the exempted words and the names
    not scanned in ``record["identifier_scan"]``, so checks.json says what the scan left out."""
    t0 = time.monotonic()
    _, skipped = name_patterns(names, allowed)
    record["identifier_scan"] = {"allowed_identifiers": list(allowed), "not_scanned": skipped}
    found, scanned = identifier_scan(
        out, {"reports/checks.json": json.dumps(record, indent=2)}, paths, names, allowed
    )
    command = "every text file written to <evidence>: host name, user name, git email, local paths"
    if allowed:
        command += "; " + " ".join(f"--allow-identifier {word}" for word in allowed)
    clean = f"{scanned} text files: no host name, user name, git email or local path"
    return {
        "name": "evidence identifier scan",
        "command": command,
        "cwd": str(APP.relative_to(REPO)),
        "exit_code": 1 if found else 0,
        "seconds": round(time.monotonic() - t0, 1),
        "summary": found or [clean] + [f"not scanned: {s}" for s in skipped],
    }


def placeholders(out: Path, work: Path, home: Path) -> list[tuple[str, str]]:
    """Local paths and their labels (from ``PLACEHOLDER_LABELS``), longest first, so a path inside
    another is replaced by its own label. The home directory is left out when it is the
    filesystem root."""
    pairs = [(str(out), "<evidence>"), (str(work), "<work>"), (str(REPO), "<repo>")]
    if len(home.parts) > 1:
        pairs.append((str(home), "~"))
    return sorted(pairs, key=lambda pair: -len(pair[0]))


def run(
    cmd: list[str], cwd: Path, checks: list[dict[str, Any]], name: str
) -> subprocess.CompletedProcess[str]:
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=_CHILD_ENV)  # noqa: S603
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="a new or empty evidence directory")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument(
        "--allow-identifier",
        action="append",
        default=[],
        metavar="WORD",
        help="a host or user name that is an ordinary word, not scanned for (recorded in "
        "checks.json; repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists() and not out.is_dir():
        print(f"{out} is not a directory: give a new or empty directory", file=sys.stderr)
        return 2
    stale = [p for p in out.rglob("*") if p.is_file()] if out.is_dir() else []
    if stale:
        print(
            f"{out} already holds {len(stale)} files: give a new or empty directory, so no stale "
            "file is published or hashed into the manifest with the new evidence",
            file=sys.stderr,
        )
        return 2
    allowed = list(dict.fromkeys(w.strip() for w in args.allow_identifier if w.strip()))
    email = git_email()
    if email and email.casefold() in {word.casefold() for word in allowed}:
        # Refused before anything is written: checks.json would record the exempted word.
        print("--allow-identifier cannot exempt the git user.email", file=sys.stderr)
        return 2
    try:
        for sub in ("reports", "traces", "screenshots", "runner_private"):
            (out / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"cannot create the evidence directory: {exc}", file=sys.stderr)
        return 2
    work = Path(tempfile.mkdtemp(prefix="planb_evidence_"))
    try:
        return collect(out, work, skip_browser=args.skip_browser, allowed=allowed)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def collect(out: Path, work: Path, *, skip_browser: bool, allowed: Sequence[str] = ()) -> int:
    checks: list[dict[str, Any]] = []
    uv = ["uv", "run"]
    web = APP / "web"
    (work / "tmp").mkdir()
    _CHILD_ENV.clear()
    _CHILD_ENV.update({k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
    _CHILD_ENV["TMPDIR"] = str(work / "tmp")
    _PLACEHOLDERS[:] = placeholders(out, work, Path.home())

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
        junit.write_text(scrub_junit(junit.read_text()))
    web_tests = run(["npm", "test"], web, checks, "web tests")
    run(["npm", "run", "lint"], web, checks, "web boundary lint")

    runs_out = work / "out"
    cases = run(
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

    if not skip_browser:
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
            return subprocess.run(  # noqa: S603
                cmd, cwd=cwd, capture_output=True, text=True, env=_CHILD_ENV
            ).stdout.strip()
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
    record = {
        "pytest_counts": counts,
        "web_test_counts": tap_counts(web_tests.stdout),
        "case_outcomes": case_lines(cases.stdout),
        "checks": checks,
    }

    # Last check: nothing written names this host, the user, the git email or a local path.
    local = [path for path, _ in _PLACEHOLDERS] + [os.path.join(tempfile.gettempdir(), "")]
    scan = scan_check(out, record, local, local_names(), allowed)
    checks.append(scan)
    print(f"[{'ok' if scan['exit_code'] == 0 else 'FAIL'}] evidence identifier scan")
    (out / "reports" / "checks.json").write_text(json.dumps(record, indent=2) + "\n")
    failed = [c["name"] for c in checks if c["exit_code"] != 0]
    print("all checks passed" if not failed else f"FAILED: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
