"""Registration check: is PLAN.md ready to be registered, and if not, what is left to do.

PLAN.md becomes the registration when no marker and no owner tag is left, its opening draft
paragraph is replaced, and section 17 holds the record of the corpus freeze (the plan's opening
and section 17, "Identity"). This script checks exactly that, against the freeze record
(``analysis/coling/out/freeze_record.json``, written by ``freeze.py``) and against the files on
disk, and exits with status 1 while anything is missing, naming each thing.

Checks.

1. Markers. No ``TBD-at-gate`` or ``TBD-at-registration`` marker and no ``[owner to confirm]``
   tag is left anywhere in the file, in any letter case; a ``TBD-at-`` marker with another
   word after it counts too. ``TBD-at-F1`` may stay. One thing is not counted: the list item
   before section 1 that starts with a marker in bold and a colon and so defines it
   ("- **TBD-at-gate**: depends on ..."), once for each of the four markers. A second such
   item for the same marker counts, and so does a marker further on in a defining item.
2. The draft paragraph. The opening ("**DRAFT (...). Not registered.**") is gone.
3. The freeze record. It is there, it is the record of a complete freeze run (not of a
   rehearsal), both sealed hashes are in it, and the one rerun that checks them has been run
   and agreed (``freeze --verify-rerun``).
4. The record against section 17 and the disk. Every hash of the record that section 17 must
   hold (lock file, capture manifest, the code that section lists, tables, lists, guide,
   availability-string list, MODELS.md) and every template pin appears in section 17 (as its
   first 16 hex characters) and is the hash of the file on disk now; the Python version of the
   record is in section 17 too. A file that is on disk and has no hash in the record fails as
   well (a list drawn after the freeze, a code file the record does not know). The files that
   the steps of the freeze wrote must also still have the recorded bytes; they need not be in
   section 17.
5. The sealed hashes. Both appear in section 17. They are compared as text from the record:
   nothing under the sealed folder is opened, listed or hashed. The file of the counts-only
   code names the record's sealed test file, and the eligible list, the events table, the
   capture manifest and the code it ran on are still the files on disk.
6. The hashes the plan states. ``rules.py``, the capture manifest, the availability-string
   list and the lock file have the hash that section 17 states, and the opening states the
   same hash for ``rules.py``.
7. The guide. Its version line says ``v1``, with no "draft".
8. The prompts. Every template matches its pin and waits for no pilot sentence.

When the record and the disk differ because a file changed after the freeze (the guide, a
prompt, MODELS.md), ``freeze --continue-after-sealed`` writes the record again without
building the corpus.

After the checks the script names, as a note that fails nothing, every hash written in
section 17 that the record, the template pins and check 6 do not hold (the hash of a submitted
sheet, say, or one left over from an earlier state of a file): those are checked by hand.

Nothing in a sealed folder is opened: the sealed hashes are compared as text, and a path in
such a folder, given on the command line or named by a record, stops the script.

``--list`` prints the worklist instead: every marker and tag left, grouped by kind, each with
its line number, its section (and the bold lead-in it stands under) and the rule written next
to it (the sentence that holds it), then the counts by kind and by section. It always exits
with status 0.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.plan_check            # exit status 1 while not ready
    PYTHONPATH=. python -m analysis.coling.plan_check --list     # what is left to fill
    PYTHONPATH=. python -m analysis.coling.plan_check --plan FILE --record FILE
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from analysis.coling import freeze

GATE = "TBD-at-gate"
REGISTRATION = "TBD-at-registration"
OWNER = "[owner to confirm]"
F1 = "TBD-at-F1"
KINDS = {
    GATE: "to fill before registration, by the rule next to it",
    REGISTRATION: "to confirm at its source before registration",
    OWNER: "to be confirmed or changed by the owner, and the tag removed",
    F1: "may stay: fixed by amendment F1",
}
MAY_STAY = (F1,)
"""Every other marker or tag must be gone, a ``TBD-at-`` marker of no known kind included."""
BY_WORD = {"gate": GATE, "registration": REGISTRATION, "f1": F1}
OPENING = "(opening)"
GUIDE_VERSION = "v1"

_MARKER = re.compile(r"TBD-\s*at-\s*(\w+)|\[owner\s+to\s+confirm\]", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6}) +(.*?)\s*$")
_LEAD = re.compile(r"^\s*(?:[-*] |\d+\. )?\*\*([^*]+)\*\*")
_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.) ")
_DEFINITION = re.compile(r"^- \*\*(?:TBD-at-\w+|\[owner to confirm\])\*\*:")
_LEAD_IN = "- **"
_BOUNDARY = re.compile(r"(?<=[.!?])[*_)\]]*\s+(?=[A-Z\[(*`_|])")
_DRAFT = re.compile(r"\*\*DRAFT\b|Not registered")
_WORD = re.compile(r"[A-Za-z0-9]{2,}")
_SHA = re.compile(r"[0-9a-f]{64}")
_WRITTEN = re.compile(rf"(?<![0-9a-f])[0-9a-f]{{{freeze.SHORT}}}(?:[0-9a-f]{{48}})?(?![0-9a-f])")


@dataclass(frozen=True)
class Found:
    """One marker or tag in the plan."""

    kind: str
    line: int
    section: str
    place: str
    rule: str
    definition: bool


# --------------------------------------------------------------------------------------------
# Markers and tags
# --------------------------------------------------------------------------------------------


def kind_of(match: re.Match[str]) -> str:
    """The kind of a marker as the plan names it; a ``TBD-at-`` marker with a word the plan
    does not use keeps that word, and is one more kind to resolve."""
    word = match.group(1)
    if not word:
        return OWNER
    return BY_WORD.get(word.lower(), f"TBD-at-{word}")


def places(lines: Sequence[str]) -> list[tuple[str, str]]:
    """For each line, its section (the ``## `` heading above it, or the opening) and its place:
    the nearest heading, with the bold lead-in the line stands under, if any."""
    out = []
    section, heading, lead = OPENING, OPENING, ""
    for line in lines:
        head = _HEADING.match(line)
        if head:
            if len(head.group(1)) == 2:
                section = head.group(2)
            if len(head.group(1)) >= 2:
                heading, lead = head.group(2), ""
        named = _LEAD.match(line)
        if named and not _MARKER.search(named.group(1)):
            lead = named.group(1).strip().rstrip(".:")
        out.append((section, f"{heading} / {lead}" if lead else heading))
    return out


def block_span(lines: Sequence[str], index: int) -> tuple[int, int]:
    """The lines of the paragraph, list item or table row that holds line ``index``."""
    if lines[index].lstrip().startswith("|"):
        return index, index + 1
    start = index
    while start > 0 and not _ITEM.match(lines[start]) and in_block(lines[start - 1]):
        start -= 1
    end = index + 1
    while end < len(lines) and not _ITEM.match(lines[end]) and in_block(lines[end]):
        end += 1
    return start, end


def in_block(line: str) -> bool:
    """Whether a line can belong to a paragraph or list item: not blank, no table row, no heading."""
    return bool(line.strip()) and not line.lstrip().startswith(("|", "#"))


def sentence_at(block: str, position: int) -> str:
    """The sentence of ``block`` that holds ``position``. A sentence that is little more than
    the marker ("**TBD-at-gate.**", "[owner to confirm]") is given with the one before it."""
    cuts = [0, *(m.end() for m in _BOUNDARY.finditer(block)), len(block)]
    spans = list(pairwise(cuts))
    at = next((k for k, (lo, hi) in enumerate(spans) if lo <= position < hi), len(spans) - 1)
    lo, hi = spans[at]
    if at > 0 and len(_WORD.findall(_MARKER.sub("", block[lo:hi]))) < 3:
        lo = spans[at - 1][0]
    return block[lo:hi].strip()


def find_markers(text: str) -> list[Found]:
    """Every marker and tag of the plan, in file order. A tag broken over two lines is found."""
    lines = text.splitlines()
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)
    where = places(lines)
    found = []
    defined: set[str] = set()
    for match in _MARKER.finditer(text):
        index = text.count("\n", 0, match.start())
        first, last = block_span(lines, index)
        block = _ITEM.sub("", " ".join(line.strip() for line in lines[first:last]))
        earlier = len(_MARKER.findall(text[starts[first] : match.start()]))
        same = list(_MARKER.finditer(block))
        position = same[earlier].start() if earlier < len(same) else 0
        section, place = where[index]
        kind = kind_of(match)
        definition = (
            section == OPENING
            and kind in KINDS
            and kind not in defined
            and lines[index][: match.start() - starts[index]] == _LEAD_IN
            and bool(_DEFINITION.match(lines[index]))
        )
        if definition:
            defined.add(kind)
        found.append(
            Found(
                kind=kind,
                line=index + 1,
                section=section,
                place=place,
                rule=sentence_at(block, position),
                definition=definition,
            )
        )
    return found


def left(found: Sequence[Found]) -> list[Found]:
    """The markers and tags that must be gone before registration."""
    return [f for f in found if f.kind not in MAY_STAY and not f.definition]


def kinds_of(found: Sequence[Found]) -> list[str]:
    """The four kinds of the plan, then any other ``TBD-at-`` kind that was found."""
    return [*KINDS, *dict.fromkeys(f.kind for f in found if f.kind not in KINDS)]


def worklist(found: Sequence[Found]) -> list[str]:
    """The lines of ``--list``: the markers by kind, then the counts by kind and by section."""
    counted = [f for f in found if not f.definition]
    kinds = kinds_of(counted)
    lines = [f"{len(counted)} markers and tags, {len(left(found))} of them to resolve"]
    for kind in kinds:
        rows = [f for f in counted if f.kind == kind]
        what = KINDS.get(kind, "not a marker of this plan: to resolve as one of the four")
        lines += ["", f"{kind}: {len(rows)} ({what})"]
        lines += [f"  line {f.line:4d}  [{f.place}]  {f.rule}" for f in rows]
    defined = [f for f in found if f.definition]
    lines += ["", f"definitions of a marker in the opening, not counted: {len(defined)}"]
    lines += [f"  line {f.line:4d}  {f.kind}" for f in defined]
    lines += ["", "by section:"]
    lines.append("  " + "".join(f"{kind:>21s}" for kind in kinds) + "  section")
    tally = Counter((f.section, f.kind) for f in counted)
    for section in dict.fromkeys(f.section for f in counted):
        cells = "".join(f"{tally[section, kind]:21d}" for kind in kinds)
        lines.append(f"  {cells}  {section}")
    totals = "".join(f"{sum(f.kind == kind for f in counted):21d}" for kind in kinds)
    lines.append(f"  {totals}  all")
    return lines


# --------------------------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------------------------


def check_markers(text: str) -> list[str]:
    rows = left(find_markers(text))
    tally = Counter(f.kind for f in rows)
    head = [f"{tally[kind]} {kind}" for kind in kinds_of(rows) if tally[kind]]
    return [*head, *(f"line {f.line} ({f.place}): {f.kind}" for f in rows)]


def check_draft(text: str) -> list[str]:
    opening = text.split("\n## ", 1)[0]
    if _DRAFT.search(opening):
        return ["the opening still holds the draft paragraph (DRAFT ... Not registered)"]
    return []


def check_record(record: Any) -> list[str]:
    """The record is that of a complete freeze run whose one rerun agreed."""
    if not isinstance(record, Mapping):
        return ["there is no freeze record: run the freeze (python -m analysis.coling.freeze)"]
    problems = []
    if record.get("mode") != freeze.FREEZE:
        problems.append(f"the record is of a run in mode {record.get('mode')}, not of the freeze")
    if record.get("status") != "complete":
        problems.append(f"the record's status is {record.get('status')}, not complete")
    for name, value in (freeze.dig(record, "tables", "sealed") or {}).items():
        if not (isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)):
            problems.append(f"sealed {name}: the record has {value!r}, not a sha256")
    if freeze.dig(record, "verify_rerun", "matches") is not True:
        problems.append("the one rerun has not confirmed the sealed hashes (freeze --verify-rerun)")
    return problems


def check_registered(record: Mapping[str, Any], disk: Mapping[str, Any], section: str) -> list[str]:
    """Every hash of the record is in section 17 and is the hash of the file on disk now; a
    file on disk has its hash in the record; section 17 names the Python of the record."""
    problems = []
    python = freeze.dig(record, "environment", "python")
    if not python or f"Python {python}" not in section:
        problems.append(f"Python {python} (the record's) is not in section 17")
    recorded = freeze.registered_hashes(record)
    for label, value in recorded.items():
        now = disk.get(label)
        if not isinstance(value, str):
            problems.append(f"{label}: the record has no hash")
        elif freeze.short(value) not in section:
            problems.append(f"{label}: {freeze.short(value)} is not in section 17")
        if isinstance(value, str) and now != value:
            problems.append(
                f"{label}: the record has {freeze.short(value)}, the disk {freeze.short(now)}"
            )
    for label, now in disk.items():
        if now is not None and label not in recorded:
            problems.append(f"{label}: on disk ({freeze.short(now)}) and not in the record")
    return problems


def unchecked_hashes(
    record: Any, pins: Any, section: str, stated: Sequence[str | None] = ()
) -> list[str]:
    """The hashes written in section 17 (16 or 64 hex characters) that neither the record nor
    the template pins hold and that are not among ``stated`` (the hashes the plan states for
    its pinned files, which have a check of their own). Nothing here can say what file they
    belong to."""
    known = {value[: freeze.SHORT] for value in _SHA.findall(json.dumps([record, pins]))}
    known |= {value for value in stated if value}
    written = dict.fromkeys(match.group(0) for match in _WRITTEN.finditer(section))
    return [value for value in written if value[: freeze.SHORT] not in known]


def check_outputs(record: Mapping[str, Any]) -> list[str]:
    """The files the steps of the freeze wrote still have the recorded bytes."""
    problems = []
    for name, value in (record.get("outputs") or {}).items():
        now = freeze.sha256_file(Path(name))
        if now != value:
            problems.append(
                f"{name}: written by the freeze as {freeze.short(value)}, now {freeze.short(now)}"
            )
    return problems


def check_sealed(record: Mapping[str, Any], section: str) -> list[str]:
    """Both sealed hashes of the record are in section 17, and the counts file names the sealed
    test file of the record (text against text) and the open files and code now on disk."""
    sealed = freeze.dig(record, "tables", "sealed") or {}
    problems = [
        f"sealed {name}: {freeze.short(value)} is not in section 17"
        for name, value in sealed.items()
        if freeze.short(value) not in section
    ]
    counts = freeze.read_json(freeze.SEALED_COUNTS)
    counted = freeze.dig(counts, "inputs", "sealed_outcomes", "sha256")
    if counted != sealed.get(freeze.SEALED_TEST):
        problems.append(
            f"{freeze.SEALED_COUNTS.name}: counts of the sealed file {freeze.short(counted)}, "
            f"not of the record's {freeze.short(sealed.get(freeze.SEALED_TEST))}"
        )
    moved = freeze.counts_drift(counts)
    if moved:
        problems.append(f"changed since the sealed counts were taken: {', '.join(moved)}")
    return problems


def check_stated(text: str) -> list[str]:
    """The hashes the plan states are those of the files, and the opening agrees on rules.py."""
    problems = freeze.check_pins(freeze.stated_pins(text))
    opening = text.split("\n## ", 1)[0]
    frozen = freeze.hash_after(opening, r"`rules\.py` is frozen")
    in_record = freeze.stated_pins(text)["rules.py"]
    if frozen and in_record and frozen != in_record:
        problems.append(f"rules.py: the opening states {frozen}, section 17 states {in_record}")
    return problems


def check_guide(guide: Path) -> list[str]:
    if not guide.is_file():
        return [f"{guide.as_posix()} is not there"]
    version = freeze.guide_version(guide.read_text(encoding="utf-8"))
    if version != GUIDE_VERSION:
        return [f"the guide's version line says {version!r}, not {GUIDE_VERSION!r}"]
    return []


def check_prompts(pins: Any) -> list[str]:
    templates = freeze.dig(pins, "templates")
    if not isinstance(templates, Mapping) or not templates:
        return ["the template pins could not be read (python -m analysis.coling.read --print-pins)"]
    problems = []
    for name, pin in templates.items():
        if not pin.get("matches_pin"):
            problems.append(f"{name}: the template does not match its pin")
        if pin.get("pending"):
            problems.append(f"{name}: waits for the pilot sentences {', '.join(pin['pending'])}")
    return problems


def live_pins() -> Any:
    """The template pins as ``read.py`` computes them now (None when the command fails)."""
    command = (freeze.PYTHON, "-m", "analysis.coling.read", "--print-pins")
    done = freeze.run_command(command, freeze.Runtime().environ)
    try:
        return json.loads(done.stdout)
    except ValueError:
        return None


def checks(text: str, record: Any, pins: Any, guide: Path = freeze.GUIDE) -> dict[str, list[str]]:
    """Every check by name, each with the problems found (empty when it holds)."""
    section = freeze.plan_section(text, 17)
    now = {**freeze.snapshot(), "environment": freeze.environment(), "prompts": pins}
    disk = freeze.registered_hashes(now)
    has_record = isinstance(record, Mapping)
    waits = ["waits for the freeze record"]
    return {
        "no marker and no owner tag is left": check_markers(text),
        "the draft paragraph is replaced": check_draft(text),
        "the freeze record is complete and its rerun agreed": check_record(record),
        "the record's hashes are in section 17 and on disk": (
            [*check_registered(record, disk, section), *check_outputs(record)]
            if has_record
            else waits
        ),
        "the sealed hashes are in section 17, and the counts are theirs": (
            check_sealed(record, section) if has_record else waits
        ),
        "the hashes the plan states are those of the files": check_stated(text),
        "the guide is v1": check_guide(guide),
        "the prompts match their pins and wait for nothing": check_prompts(pins),
    }


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def report(found: Mapping[str, list[str]], unchecked: Sequence[str] = ()) -> list[str]:
    lines = []
    for name, problems in found.items():
        lines.append(f"{'NOT READY' if problems else 'ok       '}  {name}")
        lines += [f"    {line}" for line in problems]
    if unchecked:
        lines.append(
            f"note: {len(unchecked)} hashes in section 17 are not in the freeze record or the "
            f"template pins; check them by hand: {', '.join(unchecked)}"
        )
    failing = sum(bool(problems) for problems in found.values())
    lines.append(
        f"not ready to register: {failing} of {len(found)} checks fail"
        if failing
        else "ready to register: every check holds"
    )
    return lines


def main(argv: Sequence[str] | None = None, pins_of: Callable[[], Any] = live_pins) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.plan_check", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("--plan", type=Path, default=freeze.PLAN, help="the plan to check")
    ap.add_argument("--record", type=Path, default=freeze.RECORD, help="the freeze record")
    ap.add_argument("--guide", type=Path, default=freeze.GUIDE, help="the audit guide")
    ap.add_argument("--list", action="store_true", help="print every marker and tag left")
    args = ap.parse_args(None if argv is None else list(argv))
    for path in (args.plan, args.record, args.guide):
        freeze.readable(path)
    if not args.plan.is_file():
        ap.error(f"no plan at {args.plan.as_posix()}")
    text = args.plan.read_text(encoding="utf-8")
    if args.list:
        print(f"{args.plan.as_posix()}: " + "\n".join(worklist(find_markers(text))))
        return 0
    record, pins = freeze.read_json(args.record), pins_of()
    found = checks(text, record, pins, args.guide)
    stated = list(freeze.stated_pins(text).values())
    unchecked = unchecked_hashes(record, pins, freeze.plan_section(text, 17), stated)
    print("\n".join(report(found, unchecked)))
    return 1 if any(found.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
