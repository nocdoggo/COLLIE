"""Build the local reviewable release package from the explicit allowlist in release/manifest.json.

Usage (from apps/plan_b, after `uv sync --all-groups` and `npm ci && npm run build` in web/):

    uv run python scripts/build_release.py --out <new or empty dir> [--skip-serve]

Writes into ``<out>``:

* ``package/``: every allowlisted file, at its repository-relative path, byte for byte, minus
  every file an exclude pattern matches (local secrets, local state, the evaluator-only held-out
  cases, evaluator records, caches, participant data);
* ``package/RELEASE_FILES.json``: each packaged file with its role, size and sha256;
* ``release_report.json``: the checks below, each with its result, and what was excluded.

Checks: every required path is present; no packaged path matches an exclude pattern; no text file
(the gzipped traces decompressed, the Word document's XML parts included) holds credential-shaped
text, a local absolute path, or this machine's user or host name (the manifest's
``public_identifiers`` are blanked first); the browser bundle holds no held-out case ref or
held-out scenario id. Then, unless ``--skip-serve``, the package is started as a reviewer would:
``plan_b`` imported from the package (checked), the freeze verified, the held-out public fixtures
checked against ``heldout.json`` (the private case files are withheld by design), ``demo_prep.py``
run from the package, and ``plan-b serve`` started from the package on 127.0.0.1 with no model
configuration: the board's ``index.html`` and every packaged replay are served byte for byte, and
``verify-trace`` passes on each replay. The server is stopped by its PID.

Nothing here reads a credential, hosts or submits anything, or uses the network beyond the local
server it starts.
"""

from __future__ import annotations

import argparse
import fnmatch
import getpass
import gzip
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
MANIFEST = APP / "release" / "manifest.json"
TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".jsonl", ".txt", ".ts", ".tsx", ".js", ".mjs", ".css", ".html",
    ".svg", ".toml", ".lock", ".sql", ".yaml", ".yml", ".tex", ".sty", ".cfg", ".ini",
    ".xml", ".log", ".csv", ".tsv", ".sh", ".map",
}  # fmt: skip
CREDENTIAL_PATTERNS = (
    ("OpenRouter key prefix", re.compile(r"sk-or-[A-Za-z0-9_-]{8,}")),
    ("API key shape", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "secret assignment",
        re.compile(r"(?i)\b(api[_-]?key|secret|password)[\"']?\s*[:=]\s*[\"'][^\"'\s]{12,}"),
    ),
)
# Absolute paths under a personal or session directory, beyond the repository and home paths.
# (The character class keeps this file from matching its own pattern.)
LOCAL_PATH = re.compile(r"(?<![\w.])/(?:home|Users)/[A-Za-z0-9_.-]+/|/tmp/cl[a]ude")
MIN_NAME = 3


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def excluded(rel: str, groups: list[dict[str, Any]]) -> str | None:
    for group in groups:
        for pattern in group["patterns"]:
            if fnmatch.fnmatchcase(rel, pattern):
                return str(group["why"])
    return None


def select(manifest: dict[str, Any]) -> tuple[list[tuple[str, str]], dict[str, int], list[str]]:
    """(path, role) of every allowlisted file, the excluded counts by reason, unmatched entries."""
    chosen: dict[str, str] = {}
    dropped: dict[str, int] = {}
    unmatched: list[str] = []
    for entry in manifest["include"]:
        for pattern in entry["paths"]:
            # A pattern ending in "**" matches only directories before Python 3.13.
            glob = pattern + "/*" if pattern.endswith("**") else pattern
            matches = sorted(p for p in REPO.glob(glob) if p.is_file() and not p.is_symlink())
            if not matches:
                unmatched.append(pattern)
            for path in matches:
                rel = path.relative_to(REPO).as_posix()
                why = excluded(rel, manifest["exclude"])
                if why is not None:
                    dropped[why] = dropped.get(why, 0) + 1
                    continue
                chosen.setdefault(rel, entry["role"])
    return sorted(chosen.items()), dropped, unmatched


def texts(path: Path) -> list[tuple[str, str]]:
    """(part, text) pairs to scan: the file itself, a gzip's content, a .docx's XML parts."""
    if path.suffix == ".gz":
        return [(path.name, gzip.decompress(path.read_bytes()).decode("utf-8", "replace"))]
    if path.suffix == ".docx":
        with zipfile.ZipFile(path) as z:
            return [
                (f"{path.name}:{n}", z.read(n).decode("utf-8", "replace"))
                for n in z.namelist()
                if n.endswith((".xml", ".rels"))
            ]
    if path.suffix == ".pdf":
        return [(f"{path.name}:{name}", text) for name, text in pdf_texts(path)]
    if path.suffix in TEXT_SUFFIXES or path.name in {"LICENSE"}:
        return [(path.name, path.read_text(encoding="utf-8", errors="replace"))]
    try:
        return [(path.name, path.read_bytes().decode("utf-8"))]
    except UnicodeDecodeError:
        return []


def pdf_texts(path: Path) -> list[tuple[str, str]]:
    """A PDF's visible text (pdftotext), its raw bytes (Info dictionary) and inflated streams."""
    data = path.read_bytes()
    parts = [("raw", data.decode("latin-1"))]
    visible = subprocess.run(  # noqa: S603
        ["pdftotext", "-q", str(path), "-"],  # noqa: S607
        capture_output=True,
        check=False,
    )
    parts.append(("text", visible.stdout.decode("utf-8", "replace")))
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            parts.append(("stream", zlib.decompress(match.group(1)).decode("latin-1")))
        except zlib.error:
            continue
    return parts


def name_pattern(name: str) -> re.Pattern[str]:
    """The name at the start of a word, also inside a longer handle or an e-mail address."""
    letter = r"[^\W\d_]"
    return re.compile(rf"(?<!{letter}){re.escape(name)}", re.IGNORECASE)


def scan(pkg: Path, public: Sequence[str]) -> dict[str, Any]:
    local = sorted({str(REPO), str(Path.home())} - {"/"}, key=len, reverse=True)
    names = {
        n for n in (getpass.getuser(), socket.gethostname().split(".")[0]) if len(n) >= MIN_NAME
    }
    findings: dict[str, list[str]] = {"credential": [], "local path": [], "identifier": []}
    scanned = skipped = 0
    for path in sorted(p for p in pkg.rglob("*") if p.is_file()):
        rel = path.relative_to(pkg).as_posix()
        parts = texts(path)
        if not parts:
            skipped += 1
            continue
        scanned += 1
        for part, text in parts:
            where = rel if part == path.name else f"{rel} ({part.split(':', 1)[1]})"
            for label, pattern in CREDENTIAL_PATTERNS:
                if pattern.search(text):
                    findings["credential"].append(f"{where}: {label}")
            if any(p in text for p in local) or LOCAL_PATH.search(text):
                findings["local path"].append(where)
            if part.endswith(":stream"):
                continue  # kerned text fragments: names are checked on the PDF's visible text
            blanked = text
            for phrase in public:
                blanked = re.sub(re.escape(phrase), " ", blanked, flags=re.IGNORECASE)
            if any(name_pattern(n).search(blanked) for n in names):
                findings["identifier"].append(where)
    return {
        "text_files_scanned": scanned,
        "binary_files_not_text_scanned": skipped,
        "findings": findings,
        "ok": not any(findings.values()),
    }


def bundle_scan(pkg: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    heldout = json.loads((pkg / "apps/plan_b/plan_b/evaluation/manifests/heldout.json").read_text())
    tokens = sorted(
        {
            c[k]
            for cases in heldout["suites"].values()
            for c in cases
            for k in ("case_ref", "scenario_id")
        }
    )
    bundle = pkg / manifest["browser_bundle"]["path"]
    hits = []
    files = sorted(p for p in bundle.rglob("*") if p.is_file())
    for path in files:
        text = path.read_bytes().decode("utf-8", "replace")
        hits += [f"{path.relative_to(pkg).as_posix()}: {t}" for t in tokens if t in text]
    return {
        "files": len(files),
        "tokens_searched": len(tokens),
        "hits": hits,
        "ok": not hits and bool(files),
    }


def check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any = "") -> None:
    checks.append({"check": name, "passed": bool(ok), "detail": detail})
    print(f"[{'ok' if ok else 'FAIL'}] {name}")


def py(pkg_app: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, *args], cwd=pkg_app, env=env, capture_output=True, text=True, timeout=300
    )


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - the local server
        return bytes(resp.read())


def verify_package(pkg: Path, work: Path, checks: list[dict[str, Any]]) -> None:
    pkg_app = pkg / "apps/plan_b"
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("PLAN_B_") and k != "VIRTUAL_ENV"
    }
    env.update({"PYTHONPATH": str(pkg_app), "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(work)})
    where = py(pkg_app, ["-c", "import plan_b; print(plan_b.__file__)"], env)
    check(
        checks,
        "plan_b is imported from the package, not the repository",
        where.returncode == 0 and Path(where.stdout.strip()).is_relative_to(pkg_app),
        "<package>/" + Path(where.stdout.strip()).relative_to(pkg).as_posix()
        if where.returncode == 0 and Path(where.stdout.strip()).is_relative_to(pkg)
        else where.stderr[-300:],
    )
    freeze = py(
        pkg_app,
        [
            "-c",
            "from pathlib import Path; from plan_b.evaluation import manifest; "
            "c = manifest.verify_freeze(Path('plan_b/evaluation/manifests/freeze_v1_2.json')); "
            "print(c.ok, c.detail, list(c.drift)[:5]); raise SystemExit(0 if c.ok else 1)",
        ],
        env,
    )
    # freeze.json (1.1) verifies only at its own commit since the 1.2 code, so the package checks
    # the current freeze.
    check(
        checks,
        "freeze_v1_2.json verifies in the package",
        freeze.returncode == 0,
        freeze.stdout.strip(),
    )
    heldout = json.loads((pkg_app / "plan_b/evaluation/manifests/heldout.json").read_text())
    public = [
        (c["public_file"], c["public_sha256"])
        for cases in heldout["suites"].values()
        for c in cases
    ]
    bad = [f for f, h in public if sha256((pkg_app / f).read_bytes()) != h]
    withheld = [
        c["private_file"]
        for cases in heldout["suites"].values()
        for c in cases
        if (pkg_app / c["private_file"]).exists()
    ]
    check(
        checks,
        "held-out public fixtures match heldout.json; the private case files are withheld",
        not bad and not withheld,
        f"{len(public)} public fixture entries checked; mismatched {bad}; "
        f"private present {withheld}",
    )
    prep = py(pkg_app, ["scripts/demo_prep.py", "--dest", str(work / "demo")], env)
    replays = sorted((work / "demo" / "replays").glob("*.json"))
    check(
        checks,
        "demo_prep.py from the package prepares a clean state and verifies the packaged traces",
        prep.returncode == 0 and bool(replays),
        f"exit {prep.returncode}; {len(replays)} traces verified intact",
    )
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    base = f"http://127.0.0.1:{port}/"
    serve_env = {**env, "PLAN_B_MODERATOR_CODE": secrets.token_urlsafe(18)}
    command = [sys.executable, "-m", "plan_b.cli", "serve", "--port", str(port)]
    command += [
        "--var",
        str(work / "demo" / "state"),
        "--replay-dir",
        str(work / "demo" / "replays"),
    ]
    server = subprocess.Popen(  # noqa: S603
        command, cwd=pkg_app, env=serve_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        health: Any = None
        for _ in range(80):
            try:
                health = json.loads(get(base + "api/health"))
                break
            except OSError:
                time.sleep(0.25)
        check(
            checks, "plan-b serve starts from the package on 127.0.0.1", health is not None, health
        )
        index = get(base)
        check(
            checks,
            "the board's index.html is served from the packaged bundle",
            index == (pkg_app / "web/dist/index.html").read_bytes(),
            f"{len(index)} bytes",
        )
        listed = sorted(r["name"] for r in json.loads(get(base + "api/replays")))
        check(
            checks,
            "the server lists every packaged replay",
            listed == [p.name for p in replays],
            f"{len(listed)} listed",
        )
        same = [
            n
            for n in listed
            if get(base + f"api/replays/{n}") == (work / "demo/replays" / n).read_bytes()
        ]
        check(
            checks,
            "each replay is served byte for byte",
            same == listed,
            f"{len(same)}/{len(listed)}",
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
    verified = [
        p.name
        for p in replays
        if py(pkg_app, ["-m", "plan_b.cli", "verify-trace", str(p)], env).returncode == 0
    ]
    check(
        checks,
        "verify-trace passes on every packaged replay (run from the package)",
        len(verified) == len(replays),
        f"{len(verified)}/{len(replays)}",
    )


def build(out: Path, skip_serve: bool) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []
    chosen, dropped, unmatched = select(manifest)
    check(checks, "every allowlist entry matches a file", not unmatched, unmatched)
    rels = {rel for rel, _ in chosen}
    missing = [r for r in manifest["required"] if r not in rels]
    check(checks, "every required path is in the package", not missing, missing)
    pkg = out / "package"
    files = []
    for rel, role in chosen:
        src, dst = REPO / rel, pkg / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dst.write_bytes(data)
        files.append({"path": rel, "role": role, "bytes": len(data), "sha256": sha256(data)})
    written = sorted(p.relative_to(pkg).as_posix() for p in pkg.rglob("*") if p.is_file())
    leaked = [r for r in written if excluded(r, manifest["exclude"]) or r not in rels]
    check(
        checks,
        "every written file is allowlisted and none matches an exclude pattern",
        not leaked,
        leaked,
    )
    (pkg / "RELEASE_FILES.json").write_text(
        json.dumps({"manifest": manifest["kind"], "files": files}, indent=1) + "\n"
    )
    found = scan(pkg, manifest["public_identifiers"]["strings"])
    check(
        checks,
        "no credential, local path or local user/host name in any text file",
        found["ok"],
        found,
    )
    bundle = bundle_scan(pkg, manifest)
    check(
        checks, "the browser bundle holds no held-out case ref or scenario id", bundle["ok"], bundle
    )
    if not skip_serve:
        work = Path(tempfile.mkdtemp(prefix="planb_release_"))
        try:
            verify_package(pkg, work, checks)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    head = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,  # noqa: S607
    ).stdout.strip()
    report = {
        "kind": "plan_b local release package build (not hosted, not submitted)",
        "manifest": "apps/plan_b/release/manifest.json",
        "manifest_sha256": sha256(MANIFEST.read_bytes()),
        "git_head": head,
        "tree_clean": not subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=REPO,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "files": len(files),
        "bytes": sum(f["bytes"] for f in files),
        "excluded_by_reason": dropped,
        "served_and_replayed": not skip_serve,
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
    (out / "release_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(files)} files, {report['bytes']} bytes; excluded {dropped}")
    print("release package built" if report["passed"] else "RELEASE CHECKS FAILED")
    return 0 if report["passed"] else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", required=True, help="a new or empty directory")
    parser.add_argument(
        "--skip-serve", action="store_true", help="skip the startup and replay check"
    )
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        print(f"{out}: give a new or empty directory", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    return build(out, args.skip_serve)


if __name__ == "__main__":
    sys.exit(main())
