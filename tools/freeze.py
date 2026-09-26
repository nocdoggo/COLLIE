"""Gate 2 method freeze over the registered method files.

This is the wider sibling of :mod:`tools.freeze_contracts`: it hashes every registered method
artefact and refuses confirmatory execution when one has changed without a dated deviation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from collie.eval.prereg import load_preregistration, render_preregistration_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = REPO_ROOT / "prereg" / "freeze_manifest.json"
DEVIATIONS_PATH = REPO_ROOT / "prereg" / "deviations.md"
SCHEMA_VERSION = 1
GATE = "gate2"

REGISTERED_FILES = (
    "collie/contracts.py",
    "collie/spec/registry.py",
    "collie/spec/schema.py",
    "collie/control/mapping.py",
    "collie/control/grid.py",
    "collie/control/forecast.py",
    "collie/verify/registry.py",
    "collie/verify/alpha.py",
    "collie/trigger/detectors.py",
    "collie/arms/oracle.py",
    "collie/eval/pilot.py",
    "collie/eval/truth.py",
    "prereg/prereg_v1.yaml",
    "prereg/threshold_rationale.md",
    "manifests/shockspec_v1.json",
    "tools/run_arms.py",
    "tools/run_pilot.py",
)


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    sha256: str | None
    lines: int
    bytes: int
    missing: bool = False

    @property
    def short(self) -> str:
        return "<missing>" if self.sha256 is None else self.sha256[:12]


def missing_registered_files() -> tuple[str, ...]:
    return tuple(rel for rel in REGISTERED_FILES if not (REPO_ROOT / rel).is_file())


def hash_file(path: Path) -> FileRecord:
    if not path.is_file():
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        return FileRecord(path=rel, sha256=None, lines=0, bytes=0, missing=True)
    raw = path.read_bytes()
    normalised = raw.replace(b"\r\n", b"\n")
    rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    return FileRecord(
        path=rel,
        sha256=hashlib.sha256(normalised).hexdigest(),
        lines=normalised.count(b"\n"),
        bytes=len(normalised),
    )


def current_records() -> tuple[FileRecord, ...]:
    return tuple(hash_file(REPO_ROOT / rel) for rel in REGISTERED_FILES)


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("could not resolve git SHA for the method freeze") from exc


def git_sha_is_ancestor(ancestor: str, descendant: str) -> bool:
    """Return whether a recorded pre-freeze commit remains in the live history."""
    if ancestor == descendant:
        return True
    try:
        completed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return completed.returncode == 0


def preregistration_final_status() -> tuple[bool, str | None]:
    try:
        load_preregistration(require_final=True)
    except (TypeError, ValueError) as exc:
        return False, str(exc)
    return True, None


def load_freeze(path: Path | None = None) -> dict:
    target = path or FREEZE_PATH
    if not target.is_file():
        raise FileNotFoundError(
            f"{target} is missing. Create it with `uv run python -m tools.freeze` "
            "after all registered method files exist."
        )
    return json.loads(target.read_text(encoding="utf-8"))


def render(frozen_at: str) -> str:
    preregistration_final, preregistration_error = preregistration_final_status()
    missing = missing_registered_files()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "gate": GATE,
        "frozen_at": frozen_at,
        "git_sha": git_sha(),
        "registered_files": list(REGISTERED_FILES),
        "complete": not missing and preregistration_final,
        "preregistration_final": preregistration_final,
        "incomplete_reasons": [
            *([f"missing registered files: {', '.join(missing)}"] if missing else []),
            *(
                [f"preregistration is not final: {preregistration_error}"]
                if preregistration_error
                else []
            ),
        ],
        "rule": (
            "A registered method file may change, but not quietly. Log a dated entry in "
            "prereg/deviations.md naming the file and quoting the new sha256, then re-run "
            "tools.freeze."
        ),
        "files": {
            record.path: {
                "sha256": record.sha256,
                "lines": record.lines,
                "bytes": record.bytes,
                "missing": record.missing,
            }
            for record in current_records()
        },
    }
    manifest_hash = hashlib.sha256(
        json.dumps(
            {
                "files": payload["files"],
                "git_sha": payload["git_sha"],
                "registered_files": payload["registered_files"],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    payload["manifest_sha256"] = manifest_hash
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def changed_records(
    frozen_manifest: dict,
    records: tuple[FileRecord, ...],
    current_git_sha: str,
    *,
    recorded_git_is_ancestor: bool | None = None,
) -> list[tuple[str, str, str]]:
    """Compare a frozen manifest to caller-supplied live records."""
    frozen = frozen_manifest["files"]
    changed = []
    if frozen_manifest.get("git_sha") != current_git_sha and recorded_git_is_ancestor is not True:
        changed.append(
            ("<git-sha>", frozen_manifest.get("git_sha", "<not frozen>"), current_git_sha)
        )
    for record in records:
        recorded = frozen.get(record.path)
        live_sha = record.sha256 or "<missing>"
        if recorded is None:
            changed.append((record.path, "<not frozen>", live_sha))
        elif recorded["sha256"] != record.sha256:
            changed.append((record.path, recorded["sha256"] or "<missing>", live_sha))
    return changed


def drift() -> list[tuple[str, str, str]]:
    frozen_manifest = load_freeze()
    current = git_sha()
    recorded = str(frozen_manifest.get("git_sha", ""))
    return changed_records(
        frozen_manifest,
        current_records(),
        current,
        recorded_git_is_ancestor=git_sha_is_ancestor(recorded, current),
    )


def deviation_declared(path: str, new_sha: str) -> bool:
    if not DEVIATIONS_PATH.is_file():
        return False
    text = DEVIATIONS_PATH.read_text(encoding="utf-8")
    return path in text and new_sha[:12] in text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify only; write nothing")
    ap.add_argument("--refreeze", action="store_true", help="stamp today as the freeze date")
    args = ap.parse_args(argv)

    if args.check:
        frozen = load_freeze()
        if not frozen.get("complete", False):
            reasons = frozen.get("incomplete_reasons") or ["unspecified incomplete freeze"]
            raise SystemExit(
                "method freeze is incomplete: " + "; ".join(str(reason) for reason in reasons)
            )
        changed = drift()
        if not changed:
            print(f"method freeze intact ({frozen['frozen_at']}): {len(REGISTERED_FILES)} files")
            return 0
        for path, old, new in changed:
            declared = deviation_declared(path, new)
            status = "declared" if declared else "UNDECLARED"
            print(f"{path}: {old[:12]} -> {new[:12]} [{status}]")
        undeclared = [c for c in changed if not deviation_declared(c[0], c[2])]
        if undeclared:
            raise SystemExit(
                "registered method file changed without a declared deviation. Add a dated entry "
                "to prereg/deviations.md naming the file and its new sha256, then re-run "
                "`uv run python -m tools.freeze`."
            )
        raise SystemExit(
            "deviation is declared but the freeze manifest is stale. Re-run "
            "`uv run python -m tools.freeze`."
        )

    frozen_at = dt.date.today().isoformat()
    if not args.refreeze and FREEZE_PATH.is_file():
        frozen_at = json.loads(FREEZE_PATH.read_text(encoding="utf-8")).get("frozen_at", frozen_at)

    FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FREEZE_PATH.write_text(render(frozen_at), encoding="utf-8")
    print(f"wrote {FREEZE_PATH} (frozen_at {frozen_at})")
    missing = missing_registered_files()
    final, _final_error = preregistration_final_status()
    if missing or not final:
        print("WARNING: method freeze is incomplete:")
        for reason in json.loads(FREEZE_PATH.read_text(encoding="utf-8"))["incomplete_reasons"]:
            print(f"  {reason}")
    for record in current_records():
        print(f"  {record.path}: {record.short} ({record.lines} lines)")
    prereg = load_preregistration(require_final=False)
    print()
    print(render_preregistration_summary(prereg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
