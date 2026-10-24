"""The evidence tooling: scripts/write_manifest.py, the collector's scrubbing and identifier scan
(audit C1-C5), and the walkthrough's check details.

The manifest is built from a temporary evidence directory of synthetic files and a fake git that
answers only read-only commands, so every field can be traced to its source. One test reads the
real repository's history, read-only. The identifier scan is given synthetic host names, user
names and git emails, so no test depends on this machine's names or reads its git email.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

APP = Path(__file__).resolve().parents[1]
BASE = "a" * 40
MIDDLE = "b" * 40
HEAD = "c" * 40
AUTHOR = "Ann Example <ann@example.org>"
READ_ONLY = {
    "rev-parse",
    "rev-list",
    "show",
    "diff-tree",
    "branch",
    "merge-base",
    "cat-file",
    "diff",
}


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script(name: str) -> ModuleType:
    return _load(name, APP / "scripts" / f"{name}.py")


wm = _script("write_manifest")
ce = _script("collect_evidence")
HOST = "ci-runner-7f3a"  # a synthetic host name, never this machine's


class FakeGit:
    """Canned answers to the git calls the manifest makes; every call is recorded."""

    def __init__(
        self,
        upstream: str | None = None,
        upstream_has_head: bool = False,
        app_changed: bool = False,
    ) -> None:
        self.upstream = upstream
        self.upstream_has_head = upstream_has_head
        self.app_changed = app_changed
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> tuple[int, str]:
        self.calls.append(args)
        if args[:2] == ("rev-parse", "--verify"):
            return 0, BASE
        if args == ("rev-parse", "HEAD"):
            return 0, HEAD
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return (0, self.upstream) if self.upstream else (128, "")
        if args[0] == "rev-list":
            assert args[-1] == f"{BASE}..{HEAD}"
            return 0, f"{MIDDLE}\n{HEAD}"
        if args[0] == "show":
            commit = args[-1]
            return 0, "\x00".join(
                [commit, AUTHOR, AUTHOR, "2026-10-24T10:00:00+00:00", f"subject {commit[0]}", ""]
            )
        if args[0] == "diff-tree":
            return 0, "apps/plan_b/scripts/x.py\napps/plan_b/README.md\n.gitignore"
        if args[0] == "merge-base":
            return (0 if self.upstream_has_head else 1), ""
        if args[:2] == ("branch", "-r"):
            return 0, ""
        if args == ("branch", "--show-current"):
            return 0, "hackathon/branch"
        if args[0] == "cat-file":
            return 0, ""
        if args[0] == "diff":
            return (1 if self.app_changed else 0), ""
        raise AssertionError(f"unexpected git call {args}")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def _evidence(
    root: Path,
    *,
    exit_code: int = 0,
    walk_ok: bool = True,
    walk: bool = True,
    clean: bool = True,
) -> tuple[Path, Path]:
    """A packet directory and its evidence directory of synthetic files."""
    packet = root / "packet"
    evidence = root / "evidence"
    packet.mkdir()
    (packet / "VERIFICATION.md").write_text("# Verification\n")
    line = "goal_complete={} infeasibility_reported={} violations=0 matches_expectation=True"
    checks = [
        {"name": "ruff check", "summary": ["All checks passed!"], "exit_code": 0},
        {"name": "pytest", "summary": ["3 passed in 1.0s"], "exit_code": exit_code},
        {"name": "web tests", "summary": ["# pass 9", "# fail 0"], "exit_code": 0},
        {
            "name": "plan-b run-case all",
            "summary": [f"dev01: {line.format(True, False)}", f"dev05: {line.format(False, True)}"],
            "exit_code": 0,
        },
    ]
    if walk:
        checks.append(
            {
                "name": "browser walkthrough (Playwright, Chromium)",
                "command": "uv run python tests/e2e/walkthrough.py --out <work>/shots",
                "summary": ["2/2 checks passed"],
                "exit_code": 0,
            }
        )
    for check in checks:
        check.setdefault("command", f"uv run {check['name']}")
        check.update(cwd="apps/plan_b", seconds=1.0)
    _write(
        evidence / "reports" / "checks.json",
        {
            "pytest_counts": {"tests": 3, "failures": 0, "errors": 0, "skipped": 0},
            "identifier_scan": {
                "allowed_identifiers": ["lab"],
                "not_scanned": ["host name: allowed by --allow-identifier"],
            },
            "checks": checks,
        },
    )
    _write(evidence / "reports" / "environment.json", {"git_head": HEAD, "app_tree_clean": clean})
    _write(
        evidence / "reports" / "fixture_hashes.json",
        {"lockfiles": {"apps/plan_b/uv.lock": "f" * 64}, "migrations": {"0001.sql": "e" * 64}},
    )
    report = {
        "applied_plans": 0,
        "committed_cents": 0,
        "violations": [],
        "policy_id": "rules/1.0.0",
    }
    _write(
        evidence / "reports" / "dev01_outcome.public.json",
        {**report, "goal_complete": True, "infeasibility_reported": False, "applied_plans": 1},
    )
    _write(
        evidence / "reports" / "dev05_outcome.public.json",
        {**report, "goal_complete": False, "infeasibility_reported": True},
    )
    _write(evidence / "reports" / "rejected_actions_steps.json", {"steps": [{"step": "a"}] * 4})
    trace = {
        "kind": "plan_b_sanitized_trace",
        "trace_version": "1.0.0",
        "runtime_version": "1.0.0",
        "source": {"policy_id": "rules/1.0.0"},
        "receipts": [{"status": "applied"}],
    }
    _write(evidence / "traces" / "dev01_trace.json", trace)
    _write(evidence / "traces" / "dev05_trace.json", {**trace, "receipts": []})
    _write(
        evidence / "traces" / "rejected_actions_trace.json",
        {**trace, "receipts": [{"status": "applied"}, {"status": "rejected"}]},
    )
    if walk:
        _write(
            evidence / "screenshots" / "walkthrough_report.json",
            {
                "browser": "Chromium (Playwright)",
                "passed": walk_ok,
                "checks": [
                    {"check": "loaded", "passed": True, "detail": "", "workflow_step": 1},
                    {"check": "no page errors", "passed": walk_ok, "detail": ""},
                ],
                "minimum_visible_workflow": [
                    {"step": 1, "title": "Load", "checks": ["loaded"], "passed": True}
                ],
                "screenshots": ["01_loaded.png"],
            },
        )
        (evidence / "screenshots" / "01_loaded.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(64))
    _write(evidence / "runner_private" / "dev01_outcome.runner.json", {"matches_expectation": True})
    return packet, evidence


def _manifest(tmp_path: Path, git: FakeGit, **kwargs: Any) -> dict[str, Any]:
    packet, evidence = _evidence(tmp_path, **kwargs)
    out = tmp_path / "scratch" / "manifest.json"
    out.parent.mkdir()
    argv = ["--packet", str(packet), "--evidence", str(evidence), "--out", str(out)]
    assert wm.main(argv, git=git) == 0
    assert not (packet / "manifest.json").exists()
    manifest: dict[str, Any] = json.loads(out.read_text())
    return manifest


def test_manifest_is_derived_from_the_evidence_and_git(tmp_path: Path) -> None:
    git = FakeGit()
    m = _manifest(tmp_path, git)
    repo = m["repository"]
    assert [c["id"] for c in repo["commits"]] == [MIDDLE, HEAD]
    assert {(c["author"], c["committer"]) for c in repo["commits"]} == {(AUTHOR, AUTHOR)}
    assert [c["subject"] for c in repo["commits"]] == ["subject b", "subject c"]
    assert repo["commits"][0]["areas"] == [".gitignore", "apps/plan_b"]
    assert repo["commits_with_trailers"] == []
    assert repo["planning_baseline_commit"] == BASE and repo["head"] == HEAD
    assert repo["evidence_generated_at_commit"] == HEAD
    assert repo["app_changed_since_evidence"] is False
    assert repo["upstream"] is None and repo["pushed"] is False
    # Every git call is a read.
    assert {call[0] for call in git.calls} <= READ_ONLY
    assert all(call[1] in ("--show-current", "-r") for call in git.calls if call[0] == "branch")
    assert all("--quiet" in call for call in git.calls if call[0] == "diff")

    assert [(c["name"], c["exit_code"]) for c in m["checks"]][:2] == [
        ("ruff check", 0),
        ("pytest", 0),
    ]
    assert m["identifier_scan"] == {
        "allowed_identifiers": ["lab"],
        "not_scanned": ["host name: allowed by --allow-identifier"],
    }
    assert m["pytest_counts"]["passed"] == 3
    assert m["web_test_counts"] == {"pass": 9, "fail": 0}
    walk = m["browser_walkthrough"]
    assert (walk["checks_total"], walk["checks_passed"], walk["failed_checks"]) == (2, 2, [])
    assert walk["minimum_visible_workflow"] == [
        {"step": 1, "title": "Load", "checks": 1, "passed": True}
    ]
    cases = {c["case_ref"]: c for c in m["development_cases"]}
    assert set(cases) == {"dev01", "dev05"}
    assert cases["dev01"]["goal_complete"] is True and cases["dev01"]["matches_expectation"] is True
    assert cases["dev05"]["infeasibility_reported"] is True
    assert cases["dev01"]["trace"] == "evidence/traces/dev01_trace.json"
    assert m["rejection_steps"]["steps"] == 4
    assert m["fixtures_and_locks"]["lockfiles"] == {"apps/plan_b/uv.lock": "f" * 64}
    assert m["versions"]["recorded"]["policies"] == ["rules/1.0.0"]

    evidence = tmp_path / "evidence"
    on_disk = sorted(p for p in evidence.rglob("*") if p.is_file())
    assert sorted(m["evidence_files"]) == [f"evidence/{p.relative_to(evidence)}" for p in on_disk]
    for p in on_disk:
        entry = m["evidence_files"][f"evidence/{p.relative_to(evidence)}"]
        assert entry["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
        assert entry["bytes"] == p.stat().st_size
        private = p.relative_to(evidence).parts[0] == "runner_private"
        assert entry["visibility"] == ("evaluator_private" if private else "public")

    assert m["m1"]["status"] == "passed_on_recorded_automated_checks"
    assert m["m1"]["self_assessed"] is True and m["m1"]["independent_audit"] == "pending"
    assert m["m1"]["reasons"] == []
    assert all(r["present"] for r in m["m1"]["required_evidence"])


@pytest.mark.parametrize(
    ("change", "git", "reason"),
    [
        ({"exit_code": 1}, FakeGit(), "checks exited non-zero: ['pytest']"),
        ({"walk_ok": False}, FakeGit(), "walkthrough checks failed: ['no page errors']"),
        ({"walk": False}, FakeGit(), "no walkthrough check recorded"),
        ({"clean": False}, FakeGit(), "uncommitted app changes"),
        ({}, FakeGit(app_changed=True), "the app changed after the evidence commit"),
    ],
)
def test_m1_fails_unless_every_recorded_check_passed(
    tmp_path: Path, change: dict[str, Any], git: FakeGit, reason: str
) -> None:
    m1 = _manifest(tmp_path, git, **change)["m1"]
    assert m1["status"] == "failed"
    assert any(reason in r for r in m1["reasons"]), m1["reasons"]
    assert m1["self_assessed"] is True and m1["independent_audit"] == "pending"


@pytest.mark.parametrize(("has_head", "pushed"), [(False, False), (True, True)])
def test_pushed_is_read_from_the_upstream(tmp_path: Path, has_head: bool, pushed: bool) -> None:
    repo = _manifest(tmp_path, FakeGit(upstream="origin/b", upstream_has_head=has_head))[
        "repository"
    ]
    assert repo["upstream"] == "origin/b"
    assert repo["upstream_contains_head"] is has_head
    assert repo["pushed"] is pushed


def test_manifest_reads_the_real_history(tmp_path: Path) -> None:
    git = wm.git_in(wm.REPO)
    if git("cat-file", "-e", f"{wm.BASELINE}^{{commit}}")[0] != 0:
        pytest.skip("not a git checkout with the planning baseline")
    repo = wm.repository(git, wm.BASELINE, None)
    assert repo["planning_baseline_commit"].startswith(wm.BASELINE)
    assert repo["commits"], "the implementation commits follow the baseline"
    for commit in repo["commits"]:
        assert re.fullmatch(r"[0-9a-f]{40}", commit["id"])
        assert commit["author"] and commit["committer"] and commit["subject"]
    assert repo["commits"][-1]["id"] == repo["head"]
    assert isinstance(repo["pushed"], bool)


def test_junit_keeps_no_host_name_timestamp_or_local_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ce, "_PLACEHOLDERS", [(str(tmp_path), "<evidence>")])
    raw = (
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="1.5" '
        f'timestamp="2026-10-24T10:00:00.000001+00:00" hostname="{HOST}">'
        f'<testcase classname="t" name="a" time="0.1"/><testcase classname="t" name="b" '
        f'time="0.1"><failure message="see {tmp_path}/x.py">trace</failure></testcase>'
        "</testsuite></testsuites>"
    )
    text = ce.scrub_junit(raw)
    suite = ET.fromstring(text).find("testsuite")
    assert suite is not None
    assert suite.get("hostname") == "<host>"
    assert re.findall(r'hostname="[^"]*"', text) == ['hostname="&lt;host&gt;"']
    assert "timestamp" not in suite.attrib and "timestamp=" not in text
    assert str(tmp_path) not in text
    failure = suite.find(".//failure")
    assert failure is not None and "<evidence>/x.py" in failure.get("message", "")
    assert suite.get("tests") == "2" and suite.get("name") == "pytest"


NAMES = {"host name": {f"{HOST}.example.org", HOST}, "user name": {"ann"}}


def test_identifier_scan_names_files_not_values(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "host.json").write_text(json.dumps({"machine": HOST}))
    (tmp_path / "reports" / "user.json").write_text(json.dumps({"by": "Ann"}))
    (tmp_path / "reports" / "path.json").write_text(json.dumps({"db": f"{tmp_path}/db.sqlite3"}))
    (tmp_path / "reports" / "clean.json").write_text(json.dumps({"ok": True}))
    (tmp_path / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe" + HOST.encode())
    found, scanned = ce.identifier_scan(
        tmp_path, {"reports/checks.json": "nothing local"}, [str(tmp_path)], NAMES
    )
    assert scanned == 5  # four reports and the in-memory checks.json; the PNG is skipped
    assert sorted(found) == [
        "reports/host.json: host name",
        "reports/path.json: local path",
        "reports/user.json: user name",
    ]
    assert not any(HOST in f or "ann" in f.lower() or str(tmp_path) in f for f in found)


def test_identifier_scan_finds_a_name_unless_a_letter_is_next_to_it(tmp_path: Path) -> None:
    """Only letters hide a name: a cache directory named after the user (``ann_cache``) and a
    numbered host (``boxen2``) are found, an ordinary word inside a longer word ("lab" in
    "label") is not."""
    names = {"host name": {"lab", "boxen"}, "user name": {"ann"}}
    (tmp_path / "inside.txt").write_text(
        "label collaborate Laboratory boxenx unboxen joann annual Anna banner\n"
    )
    (tmp_path / "underscore.txt").write_text("cache: ~/.cache/Ann_Cache\n")
    (tmp_path / "digit.txt").write_text("node boxen2 is up\n")
    (tmp_path / "joined.txt").write_text("lab_notes lab42\n")
    (tmp_path / "word.txt").write_text("results from the LAB.\n")
    (tmp_path / "dashed.txt").write_text("lab-1\n")
    found, scanned = ce.identifier_scan(tmp_path, {}, [], names)
    assert scanned == 6
    assert sorted(found) == [
        "dashed.txt: host name",
        "digit.txt: host name",
        "joined.txt: host name",
        "underscore.txt: user name",
        "word.txt: host name",
    ]
    # The same text with each name joined to a letter instead is clean.
    (tmp_path / "underscore.txt").write_text("cache: ~/.cache/AnnaCache\n")
    (tmp_path / "digit.txt").write_text("node boxeny2 is up\n")
    found, _ = ce.identifier_scan(tmp_path, {}, [], names)
    assert "underscore.txt: user name" not in found and "digit.txt: host name" not in found


def test_the_collectors_own_placeholders_never_count_as_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A host named "host" is not found in the JUnit's ``hostname="&lt;host&gt;"``, nor a user
    named "work" or "repo" in ``<work>``/``<repo>``; anywhere else they are still found."""
    out = tmp_path / "evidence"
    (out / "reports").mkdir(parents=True)
    monkeypatch.setattr(ce, "_PLACEHOLDERS", ce.placeholders(out, tmp_path / "work", tmp_path))
    labels = {label for _, label in ce._PLACEHOLDERS} | {ce.HOST_LABEL}
    assert labels == set(ce.PLACEHOLDER_LABELS)  # every label the collector writes is blanked
    raw = (
        '<testsuites><testsuite name="pytest" tests="1" hostname="host">'
        f'<testcase classname="t" name="a"><failure message="see {tmp_path / "work"}/x.py '
        f'and {ce.REPO}/y.py">trace</failure></testcase></testsuite></testsuites>'
    )
    junit = ce.scrub_junit(raw)
    assert 'hostname="&lt;host&gt;"' in junit and "&lt;work&gt;/x.py" in junit
    (out / "reports" / "pytest_junit.xml").write_text(junit)
    checks = {"command": ce.redact(f"uv run x --out {out} --db {tmp_path}/r.sqlite3")}
    assert checks["command"] == "uv run x --out <evidence> --db ~/r.sqlite3"
    (out / "reports" / "checks.json").write_text(json.dumps(checks))
    for names in (
        {"host name": {"host"}, "user name": {"work"}},
        {"host name": {"evidence"}, "user name": {"repo"}},
    ):
        assert ce.identifier_scan(out, {}, [str(tmp_path)], names) == ([], 2)

    (out / "reports" / "env.json").write_text('{"machine": "host", "dir": "work/"}')
    found, _ = ce.identifier_scan(out, {}, [], {"host name": {"host"}, "user name": {"work"}})
    assert found == ["reports/env.json: host name", "reports/env.json: user name"]
    # A placeholder becomes a space, so the text on either side stays apart.
    assert ce.without_placeholders("ann<work>x &lt;host&gt;y") == "ann x  y"


def test_only_the_home_label_is_blanked_and_a_tilde_email_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``~`` that redact() writes for the home directory (a path on its own, or ``~/``) is
    blanked, never every ``~``; a git email with a ``~`` in its local part (RFC 5322 allows it)
    is still found, wherever the ``~`` is."""
    home = tmp_path / "home"
    monkeypatch.setattr(ce, "_PLACEHOLDERS", ce.placeholders(tmp_path / "e", tmp_path / "w", home))
    written = ce.redact(f'--db {home}/r.sqlite3 --home {home} "cwd": "{home}" PATH={home}:/bin')
    assert written == '--db ~/r.sqlite3 --home ~ "cwd": "~" PATH=~:/bin'
    assert "~" not in ce.without_placeholders(written)
    for text in ("a~b@example.org", "PROGRA~1", "x~", "~x", "~~", "a.~.b", "a-~_b"):
        assert ce.without_placeholders(text) == text

    scan = tmp_path / "scan"
    scan.mkdir()
    (scan / "checks.json").write_text(json.dumps({"command": written}))
    no_names = {"host name": {""}, "user name": {""}}
    (scan / "author.txt").write_text("a~b@example.org\n")
    found = ce.identifier_scan(scan, {}, [], {**no_names, "git email": {"a~b@example.org"}})
    assert found == (["author.txt: git email"], 2)
    for email in ("a~b@example.org", "~@example.org", "~/x@example.org", "x=~/y@example.org"):
        names = {"host name": {HOST}, "user name": {"ann"}, "git email": {email}}
        (scan / "author.txt").write_text("Signed-off-by: Bob <bob@example.org>\n")
        assert ce.identifier_scan(scan, {}, [], names) == ([], 2)
        (scan / "author.txt").write_text(f"Signed-off-by: Bob <{email.upper()}>\n")
        assert ce.identifier_scan(scan, {}, [], names) == (["author.txt: git email"], 2)


def test_the_git_email_is_scanned_for_and_cannot_be_exempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    email = "Ann.Example@Example.org"
    names = {"host name": {HOST}, "user name": {"ann"}, "git email": {email}}
    (tmp_path / "author.txt").write_text("Signed-off-by: Ann <ann.example@example.org>\n")
    (tmp_path / "other.txt").write_text("joann.example@example.org bob@example.org\n")
    found, _ = ce.identifier_scan(tmp_path, {}, [], names)
    assert found == ["author.txt: git email", "author.txt: user name"]

    # --allow-identifier exempts the user name, never the email.
    record: dict[str, Any] = {"checks": []}
    check = ce.scan_check(tmp_path, record, [], names, ["ann", email.upper()])
    assert check["exit_code"] == 1
    assert sorted(check["summary"]) == ["author.txt: git email", "reports/checks.json: git email"]
    assert record["identifier_scan"]["not_scanned"] == ["user name: allowed by --allow-identifier"]
    assert "git email" in check["command"]

    # An unset email is recorded as not scanned.
    assert ce.name_patterns({"git email": {""}}) == ([], ["git email: not known"])

    # The collector refuses to start with the email as an exempted word, and writes nothing.
    monkeypatch.setattr(ce, "git_email", lambda: email)
    monkeypatch.setattr(ce, "collect", lambda *_, **__: pytest.fail("must not collect"))
    target = tmp_path / "fresh"
    assert ce.main(["--out", str(target), "--allow-identifier", email.lower()]) == 2
    err = capsys.readouterr().err
    assert "cannot exempt the git user.email" in err and email.casefold() not in err.casefold()
    assert not target.exists()


def test_git_email_is_read_with_git_config_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\temail = ann@example.org\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))  # instead of ~/.gitconfig and XDG
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    for var in ("GIT_DIR", "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"):
        monkeypatch.delenv(var, raising=False)
    calls: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(ce.subprocess, "run", spy)
    cwd = tmp_path / "not_a_repo"
    cwd.mkdir()
    assert ce.git_email(cwd) == "ann@example.org"
    config.write_text("[user]\n\tname = Ann\n")
    assert ce.git_email(cwd) == ""
    assert calls == [["git", "config", "user.email"]] * 2  # a read, never a write

    def no_git(*_: Any, **__: Any) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(ce.subprocess, "run", no_git)
    assert ce.git_email(cwd) == ""


def test_out_must_be_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--out naming a regular file, or a path under one, is refused with exit 2 and a message."""
    file = tmp_path / "evidence"
    file.write_text("x")
    # The real command line: a message, not a traceback.
    script = APP / "scripts" / "collect_evidence.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--out", str(file)], capture_output=True, text=True
    )
    assert proc.returncode == 2, proc.stderr
    assert proc.stderr.strip() == (
        f"{file.resolve()} is not a directory: give a new or empty directory"
    )
    assert proc.stdout == ""

    monkeypatch.setattr(ce, "git_email", lambda: "")
    monkeypatch.setattr(ce, "collect", lambda *_, **__: pytest.fail("must not collect"))
    assert ce.main(["--out", str(file)]) == 2
    assert "is not a directory" in capsys.readouterr().err
    assert ce.main(["--out", str(file / "sub")]) == 2
    assert "cannot create the evidence directory" in capsys.readouterr().err
    assert file.read_text() == "x" and sorted(tmp_path.iterdir()) == [file]


def test_allowed_identifier_is_not_scanned_and_is_recorded(tmp_path: Path) -> None:
    """--allow-identifier exempts a name that is an ordinary word, in any case; checks.json says
    which words were exempted and which names were therefore not scanned."""
    names = {"host name": {"pytest.example.org", "pytest"}, "user name": {"ann"}}
    (tmp_path / "reports").mkdir()
    junit = '<testsuite name="pytest" hostname="&lt;host&gt;"/>\n'
    (tmp_path / "reports" / "pytest_junit.xml").write_text(junit)
    record: dict[str, Any] = {"checks": []}

    blocked = ce.scan_check(tmp_path, dict(record), [], names, [])
    assert blocked["exit_code"] == 1
    assert blocked["summary"] == ["reports/pytest_junit.xml: host name"]

    check = ce.scan_check(tmp_path, record, [], names, ["PyTest"])
    assert check["exit_code"] == 0, check["summary"]
    assert check["name"] == "evidence identifier scan"
    assert check["command"].endswith("; --allow-identifier PyTest")
    assert record["identifier_scan"] == {
        "allowed_identifiers": ["PyTest"],
        "not_scanned": ["host name: allowed by --allow-identifier"],
    }
    assert check["summary"] == [
        "2 text files: no host name, user name, git email or local path",
        "not scanned: host name: allowed by --allow-identifier",
    ]

    # Only the exempted name: the full host name and the user name are still scanned for.
    (tmp_path / "reports" / "env.json").write_text('{"host": "PYTEST.example.org", "u": "ann"}')
    still = ce.scan_check(tmp_path, record, [], names, ["pytest"])
    assert still["exit_code"] == 1
    assert still["summary"] == ["reports/env.json: host name", "reports/env.json: user name"]


def test_short_or_unknown_names_are_recorded_as_not_scanned() -> None:
    patterns, skipped = ce.name_patterns({"host name": {"pc"}, "user name": {""}})
    assert patterns == []
    assert skipped == [
        f"host name: shorter than {ce.MIN_NAME} characters",
        "user name: not known",
    ]


def test_local_names_cover_the_full_and_short_host_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ce.socket, "gethostname", lambda: "Box.example.org")
    monkeypatch.setattr(ce.getpass, "getuser", lambda: "ann")
    monkeypatch.setattr(ce, "git_email", lambda: "ann@example.org")
    assert ce.local_names() == {
        "host name": {"Box.example.org", "Box"},
        "user name": {"ann"},
        "git email": {"ann@example.org"},
    }


def test_allow_identifier_is_repeatable_and_out_must_be_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = ce.parse_args(["--out", "x", "--allow-identifier", "lab", "--allow-identifier", "ann"])
    assert args.allow_identifier == ["lab", "ann"] and args.skip_browser is False
    assert ce.parse_args(["--out", "x"]).allow_identifier == []

    def no_collect(*_: Any, **__: Any) -> int:
        raise AssertionError("the collector must not run into a directory with stale files")

    monkeypatch.setattr(ce, "git_email", lambda: "ann@example.org")
    monkeypatch.setattr(ce, "collect", no_collect)
    stale = tmp_path / "evidence"
    (stale / "screenshots").mkdir(parents=True)
    (stale / "screenshots" / "old.png").write_bytes(b"")
    assert ce.main(["--out", str(stale)]) == 2
    assert sorted(p.name for p in stale.rglob("*")) == ["old.png", "screenshots"]

    seen: dict[str, Any] = {}

    def record_collect(out: Path, work: Path, *, skip_browser: bool, allowed: list[str]) -> int:
        seen.update(out=out, work=work, allowed=allowed, skip_browser=skip_browser)
        return 0

    monkeypatch.setattr(ce, "collect", record_collect)
    fresh = tmp_path / "fresh"
    argv = [
        "--out",
        str(fresh),
        "--skip-browser",
        "--allow-identifier",
        " lab ",
        "--allow-identifier",
        "lab",
    ]
    assert ce.main(argv) == 0
    assert seen["allowed"] == ["lab"] and seen["skip_browser"] is True
    assert seen["out"] == fresh.resolve()
    assert not seen["work"].exists()  # the work directory is removed afterwards


def test_home_at_the_filesystem_root_is_not_a_placeholder(tmp_path: Path) -> None:
    at_root = ce.placeholders(tmp_path / "evidence", tmp_path / "work", Path("/"))
    assert sorted(label for _, label in at_root) == ["<evidence>", "<repo>", "<work>"]
    home = ce.placeholders(tmp_path / "evidence", tmp_path / "work", tmp_path)
    assert (str(tmp_path), "~") in home
    lengths = [len(path) for path, _ in home]
    assert lengths == sorted(lengths, reverse=True)  # a path inside another gets its own label


def test_walkthrough_details_quote_the_whole_lines_relied_on() -> None:
    """Check 15's detail keeps the principal id however long the item's label is."""
    pytest.importorskip("playwright.sync_api")
    wt = _load("walkthrough", APP / "tests" / "e2e" / "walkthrough.py")
    label = "Skills facilitator with a much longer display name " * 3
    after = (
        f"{label}(facilitator) ✓Checked in\n\n"
        "At 16:44, available 16:44–18:00 (participant session) by participant_facilitator\n\n"
        "Needed for Skills exchange 17:10–17:30"
    )
    assert after.index("participant_facilitator") > 160
    detail = wt.quote(after, "Checked in", "(participant session)", "participant_facilitator")
    assert detail == (
        f"{label.strip()} (facilitator) ✓Checked in"
        " | At 16:44, available 16:44–18:00 (participant session) by participant_facilitator"
    )
    before = "Skills facilitator (facilitator) ⧗No check-in yet\n\nNeeded for Skills exchange"
    assert wt.quote(before, "(facilitator)", "No check-in yet", "Checked in") == (
        "Skills facilitator (facilitator) ⧗No check-in yet | lacks 'Checked in'"
    )
    assert "a[href*='#/join/']" in wt.JOIN_LINK and "[data-join-link]" in wt.JOIN_LINK


def test_counts_and_case_lines_are_parsed_from_command_output() -> None:
    tap = "# tests 7\n# suites 2\n# pass 6\n# fail 1\n# duration_ms 12.5\n"
    assert ce.tap_counts(tap) == {"tests": 7, "suites": 2, "pass": 6, "fail": 1}
    out = (
        "warning: unrelated\n"
        "dev01: goal_complete=True infeasibility_reported=False applied_plans=1 committed=0 "
        "violations=0 matches_expectation=True\n"
    )
    assert ce.case_lines(out) == {
        "dev01": {
            "goal_complete": True,
            "infeasibility_reported": False,
            "applied_plans": 1,
            "committed": 0,
            "violations": 0,
            "matches_expectation": True,
        }
    }
