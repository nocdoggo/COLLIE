"""Gate 1 — freeze the core contracts and guard them against silent change.

``collie/contracts.py`` is the shared vocabulary of all eight branches. Once Gate 1 passes, every
branch builds against it, so an unannounced edit would silently invalidate work already done
elsewhere. This tool records a hash; ``tests/test_contract_freeze.py`` is the tripwire.

The rule the guard enforces: **a frozen file may change, but not quietly.** To change it you log a
dated entry in ``prereg/deviations.md`` that names the file and quotes the new hash, then re-run
this tool. The guard fails until both are done, and the diff of both files is the audit trail.

This is the narrow Gate 1 freeze. The wider Gate 2 freeze over every registered method file
(``prereg/freeze_manifest.json``) belongs to Task 19 and is a separate artefact.

Usage::

    uv run python -m tools.freeze_contracts            # create or update, preserving frozen_at
    uv run python -m tools.freeze_contracts --check     # verify only, write nothing
    uv run python -m tools.freeze_contracts --refreeze  # accept current contents, stamp today
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = REPO_ROOT / "prereg" / "contract_freeze.json"
DEVIATIONS_PATH = REPO_ROOT / "prereg" / "deviations.md"
SCHEMA_VERSION = 1
GATE = "gate1"

FROZEN_FILES = ("collie/contracts.py",)
"""Gate 1 freezes the shared vocabulary and nothing else. Branch-owned modules are still moving."""


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    sha256: str
    lines: int
    bytes: int

    @property
    def short(self) -> str:
        return self.sha256[:12]


def hash_file(path: Path) -> FileRecord:
    """Hash on normalised content so a line-ending change is not mistaken for an edit."""
    raw = path.read_bytes()
    normalised = raw.replace(b"\r\n", b"\n")
    resolved = path.resolve()
    rel = (
        resolved.relative_to(REPO_ROOT).as_posix()
        if resolved.is_relative_to(REPO_ROOT)
        else resolved.name
    )
    return FileRecord(
        path=rel,
        sha256=hashlib.sha256(normalised).hexdigest(),
        lines=normalised.count(b"\n"),
        bytes=len(normalised),
    )


def current_records() -> tuple[FileRecord, ...]:
    return tuple(hash_file(REPO_ROOT / rel) for rel in FROZEN_FILES)


def load_freeze(path: Path | None = None) -> dict:
    target = path or FREEZE_PATH
    if not target.is_file():
        raise FileNotFoundError(
            f"{target} is missing. Gate 1 requires the contract freeze; create it with "
            "uv run python -m tools.freeze_contracts"
        )
    return json.loads(target.read_text(encoding="utf-8"))


def render(frozen_at: str) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "gate": GATE,
        "frozen_at": frozen_at,
        "rule": (
            "A frozen file may change, but not quietly. Log a dated entry in "
            "prereg/deviations.md naming the file and quoting the new sha256, then re-run "
            "tools.freeze_contracts."
        ),
        "files": {
            record.path: {"sha256": record.sha256, "lines": record.lines, "bytes": record.bytes}
            for record in current_records()
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def drift() -> list[tuple[str, str, str]]:
    """Return ``(path, frozen_sha, live_sha)`` for every frozen file that has changed."""
    frozen = load_freeze()["files"]
    changed = []
    for record in current_records():
        recorded = frozen.get(record.path)
        if recorded is None:
            changed.append((record.path, "<not frozen>", record.sha256))
        elif recorded["sha256"] != record.sha256:
            changed.append((record.path, recorded["sha256"], record.sha256))
    return changed


def deviation_declared(path: str, new_sha: str) -> bool:
    """True when ``deviations.md`` names the file and quotes the new hash.

    Requiring the hash, not just the filename, is what stops a single stale entry from
    authorising every future edit to that file.
    """
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
        changed = drift()
        if not changed:
            frozen = load_freeze()
            print(f"contract freeze intact ({frozen['frozen_at']}): {', '.join(FROZEN_FILES)}")
            return 0
        for path, old, new in changed:
            declared = deviation_declared(path, new)
            status = "declared" if declared else "UNDECLARED"
            print(f"{path}: {old[:12]} -> {new[:12]} [{status}]")
        undeclared = [c for c in changed if not deviation_declared(c[0], c[2])]
        if undeclared:
            raise SystemExit(
                "frozen contract changed without a declared deviation. Add a dated entry to "
                "prereg/deviations.md naming the file and its new sha256, then re-run "
                "uv run python -m tools.freeze_contracts"
            )
        raise SystemExit(
            "deviation is declared but the freeze record is stale. Re-run "
            "uv run python -m tools.freeze_contracts"
        )

    frozen_at = dt.date.today().isoformat()
    if not args.refreeze and FREEZE_PATH.is_file():
        # Preserve the original date so a re-run is byte-stable.
        frozen_at = json.loads(FREEZE_PATH.read_text(encoding="utf-8")).get("frozen_at", frozen_at)

    FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FREEZE_PATH.write_text(render(frozen_at), encoding="utf-8")
    print(f"wrote {FREEZE_PATH} (frozen_at {frozen_at})")
    for record in current_records():
        print(f"  {record.path}: {record.short} ({record.lines} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
