#!/usr/bin/env python3
"""Structural checks for the COLLIE IEEE UV 2026 draft. No TeX toolchain needed.

Run as `make check`, or directly as `python3 check.py`. Four checks:

  inputs   every \\input and \\include target exists on disk
  braces   braces balance in every source file, ignoring comments and escapes
  pending  counts \\pending and \\pcell, and refuses either inside inline math
           (both are text commands and would break a math-only context)
  refs     every \\cite key resolves in refs.bib; entries that are verified but
           not cited in this draft are reported, not treated as failures

Exit status is 0 only if all four pass. The placeholder total printed by the
pending check must equal the inventory table in README.md.
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

SOURCES = ["main.tex"] + sorted(glob.glob("sections/*.tex")) + sorted(glob.glob("figures/*.tex"))


def strip_comments(text: str) -> str:
    """Drop whole-line comments. Enough for these checks and never wrong on
    a commented-out block, which is how the validity table is preserved."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("%"))


def check_inputs() -> int:
    bad = 0
    for path in SOURCES:
        for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", strip_comments(Path(path).read_text())):
            target = m.group(1)
            if not (Path(target).is_file() or Path(target + ".tex").is_file()):
                print(f"MISSING input target: {target} (referenced by {path})")
                bad = 1
    if not bad:
        print("  inputs: every target resolves")
    return bad


def check_braces() -> int:
    bad = 0
    for path in SOURCES:
        depth = 0
        for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
            i = 0
            while i < len(line):
                c = line[i]
                if c == "\\" and i + 1 < len(line):
                    i += 2
                    continue
                if c == "%":
                    break
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth < 0:
                        print(f"UNBALANCED: {path}:{lineno} closes a brace that was never opened")
                        bad = 1
                        depth = 0
                i += 1
        if depth != 0:
            print(f"UNBALANCED: {path} ends at depth {depth}")
            bad = 1
    if not bad:
        print("  braces: balanced in every file")
    return bad


def check_pending() -> int:
    bad = 0
    total_pending = total_pcell = 0
    for path in SOURCES:
        body = strip_comments(Path(path).read_text())
        # Drop the two \newcommand lines in main.tex: they define the markers
        # rather than standing in for a missing number.
        body = "\n".join(l for l in body.splitlines() if not l.startswith("\\newcommand{\\pending}") and not l.startswith("\\newcommand{\\pcell}"))
        n_pending = len(re.findall(r"\\pending\b", body))
        n_pcell = len(re.findall(r"\\pcell\b", body))
        total_pending += n_pending
        total_pcell += n_pcell
        for m in re.finditer(r"\$[^$]*\$", body):
            if "\\pending" in m.group(0) or "\\pcell" in m.group(0):
                print(f"MATH-MODE PLACEHOLDER: {path}: {m.group(0)[:60]}")
                bad = 1
        if n_pending or n_pcell:
            print(f"  {path}: {n_pending} pending, {n_pcell} pcell")
    print(
        f"  TOTAL placeholder markers: {total_pending} pending + {total_pcell} pcell "
        f"= {total_pending + total_pcell}"
    )
    return bad


def check_refs() -> int:
    cited: set[str] = set()
    for path in SOURCES:
        body = strip_comments(Path(path).read_text())
        for m in re.finditer(r"\\cite[a-zA-Z]*\{([^}]*)\}", body):
            cited.update(k.strip() for k in m.group(1).split(",") if k.strip())
    try:
        bib = Path("refs.bib").read_text()
    except FileNotFoundError:
        print("MISSING refs.bib")
        return 1
    defined = set(re.findall(r"@\w+\s*\{\s*([^,\s]+)", bib))
    missing = sorted(cited - defined)
    for key in missing:
        print(f"UNDEFINED CITATION KEY: {key}")
    for key in sorted(defined - cited):
        print(f"  note: verified but not cited in this draft: {key}")
    print(f"  citations: {len(cited)} keys used, {len(defined)} entries defined")
    return 1 if missing else 0


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    checks = {
        "inputs": check_inputs,
        "braces": check_braces,
        "pending": check_pending,
        "refs": check_refs,
    }
    if which != "all":
        return checks[which]()
    status = 0
    for name in ("inputs", "braces", "pending", "refs"):
        status |= checks[name]()
    if status == 0:
        print("structural checks passed")
    return status


if __name__ == "__main__":
    sys.exit(main())
