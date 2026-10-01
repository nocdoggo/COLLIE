"""Outcome audit (AUDIT_GUIDE.md section 6, task B): sample, traces, sheets, validator, scorer.

The audit checks, by hand, whether the recovery bracket that ``corpus.py`` derived for a
presentation-level statement event is what its written rule gives on the raw capture rows. This
module draws the sample, writes one blank sheet per auditor (A1, A2) with a trace file beside
them, checks a returned sheet, and scores the two returned sheets.

Unit. One presentation-level event (one thread), audited under definitions B and A. The bracket
of its statement group (``statement_group_id``) is shown beside it and is not audited: the
builder's tests cover how it is combined.

Sample. Events of one half (``train`` or ``test`` period) on the shortage listing, in strata of
definition-B outcome type (recovered, discontinued, censored, not_at_risk), bracket width (31 days
or less, 32 to 90, more than 90; none for an open bracket) and whether the event was re-confirmed.
Every non-empty stratum gets ``STRATUM_FLOOR`` items and the rest follow the pool in proportion
(largest remainders), so rare cells are oversampled; the key keeps each stratum's pool size for
the reweighted rate. At most one item per thread and per statement group, and ``MAX_PER_GENERIC``
per generic. Draws are deterministic: ids are ordered by the sha256 of seed, purpose and id.

Exclusions (by statement and thread). The pool leaves out every thread that carries a statement
of the pilot, the check sets, the literal-task sample or the guide's Appendix A, every
presentation that shares such a statement, and every other event on those threads. Both auditors
label every literal item, so a thread either of them labelled is skipped for both.

* The samples are read from the lists passed with ``--exclude`` (by default the folder where
  ``audit_sample.py`` writes them): any CSV or JSON-lines file with an ``event_id``,
  ``statement_group_id`` or ``thread_id`` column. A directory is searched. The lists are applied
  to both halves: the literal sample holds test-period statements too.
* Appendix A is read from the guide (generic, company, statement date; the same text at another
  date counts too).
* The command stops when no sample list is found, when the guide has no Appendix A row or one
  that matches no event, and when a listed id names no event of the corpus as built (the lists
  then come from another build): in each case the exclusion would be incomplete.
* ``--draft`` lifts these stops and applies whatever lists there are; the guide file itself is
  always needed. A draft uses its own draw, so it does not show which items the final sheets
  will hold, and it is written to a ``draft`` folder, never beside a final set. A draft drawn
  without the sample lists can show threads whose statements the annotators label: it is for
  checking the tool and the stratum sizes, and is not given to them.
* This module's own ``outcome_*`` files are skipped when a directory is searched, so that a
  second run does not exclude the first run's sample. Named by itself, such a file is the sample
  of an earlier round: its threads are kept out of the pool. Its ids may be missing from a corpus
  rebuilt after a rule fix; that is printed and does not stop the command.

Trace. For each item, the thread's rows capture by capture: up to ``PRE_CAPTURES`` captures before
``c0`` (and the thread's last earlier row), ``c0``, and every later capture to one capture past
the last shown upper bound and through ``RELAPSE_DAYS`` after B's, or to the event's horizon when
a shown outcome is censored. The window never passes the horizon (``corpus.Context.horizon``): a
train event is followed to the last capture before 2023-01-01, so no train trace shows a row
captured in 2023 or later other than the event's own first row; the rows before ``c0`` are cut
at the same capture. Each row gives the capture, the raw cells, whether the row was linked by key
or by NDC, the generic's state, the discontinuation listing, and the class letter the builder
read: ``A`` available, ``L`` limited, ``U`` unavailable, ``O`` other, ``B`` blank, ``R`` row
Resolved, ``r`` row absent while its generic is Resolved, ``D`` newly in the discontinuation
listing, ``.`` absent. A row of another thread that carries the same NDC while this one is absent
is listed too (``present`` reads ``other_thread``). If that thread was left out for a labelling
sample or a guide example, only its generic, company and presentation are given and ``present``
reads ``other_thread_withheld``: its status and text belong to a statement an annotator labels.
The class strip in the sheet is the letters from ``c0`` on, with ``|`` before a capture that
follows a gap of more than ``GAP_DAYS`` days. ``outcome_<auditor>_<half>_items.txt`` shows the
same items as text, each with its trace under it, in the order of the auditor's sheet; verdicts
are entered in the CSV sheet. The cells are the FDA's text as captured, except that an e-mail
address is replaced by ``[email]`` in every file written (as ``corpus.availability_key`` does);
the Contact Info column is never read.

Planted items. Each auditor also gets items, taken from events outside the sample, whose shown
bracket is wrong in a known way: the upper bound moved one capture later, the lower bound moved
one capture earlier, recovery and discontinuation swapped, or the rows of another presentation of
the same generic and company linked after ``c0`` (only where a row of that presentation appears
in the trace, so that the wrong link can be seen). They look like every other item. Which items
are planted, and the true bracket, are written only to the key file, kept apart from the sheets
(``--keys``; the manifest holds its sha256). Nobody opens the key: ``score`` reads it once both
sheets are returned and validate.

Sheets. ``verdict_B`` and ``verdict_A`` take ``ok``, ``error`` or ``cannot_tell``; ``codes_B``
and ``codes_A`` take O1 to O9; ``note_codes`` takes the flags N1 to N6, which are never errors.
Sheets, traces and the adjudication sheet are written for people: every cell is quoted, and a
cell that a spreadsheet would read as a formula starts with an apostrophe. The header lines
``# session_start:`` and ``# session_end:`` are filled by the auditor (``HH:MM``, one time per
sitting, separated by semicolons); ``score`` reports the minutes per item from them.

Scoring. An item marked ``error`` or ``cannot_tell`` under a definition goes to adjudication (one
row per item and definition, ``decision``: confirmed, rejected or unresolved). The half passes
when, for definition B and separately for A, the confirmed errors are at most 5% of the real
items (2 of 50). Unresolved rows do not count against the rule and are reported beside it. The
same code confirmed twice with the same ``cause`` (the same words, whatever their case) asks for
a rule fix even when the count passes; the score file lists every confirmed error with its cause.
An auditor who misses ``PLANTED_MISS_LIMIT`` planted items of a half re-checks their own items;
the second pass is scored with ``--label recheck``, which keeps the first pass's files. Before
the key is read, ``score`` checks that the set has its manifest and that the key and the blank
sheets are the files the manifest lists; then, that the returned sheets hold the key's items. It
also says when ``corpus.py`` is no longer the file whose hash the sheets carry, and when the
sample is smaller than asked.

Sealing. The train half reads train-period outcomes only. The test half (``--half test``) writes
every file, the key included, under the directory given with ``--out`` and prints counts only: no
stratum table, no outcome value. That directory, and the one given to ``score --half test``, must
lie under a folder named ``sealed``. It is run only after every confirmatory run has finished.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.audit_outcomes sheets --half train
        [--captures external_data/fda_wayback_csv] [--out analysis/coling/out/audit_outcomes]
        [--keys external_data/annotation/keys] [--guide analysis/coling/plan/AUDIT_GUIDE.md]
        [--exclude analysis/coling/out/audit/samples ...] [--draft] [--replace]
        [--round N] [--own N] [--shared N] [--planted N] [--items LIST [--changed]]
    PYTHONPATH=. python -m analysis.coling.audit_outcomes sheets --half test
        --out external_data/sealed/audit
    PYTHONPATH=. python -m analysis.coling.audit_outcomes validate SHEET [--blank BLANK]
    PYTHONPATH=. python -m analysis.coling.audit_outcomes score --half train --a1 SHEET --a2 SHEET
        [--dir analysis/coling/out/audit_outcomes] [--key KEYFILE] [--adjudication FILE]
        [--label NAME]

``sheets --half train`` is the one command to run again after the corpus is rebuilt. Run twice on
the same inputs it writes the same bytes. Where a final set already lies in the output folder and
the new one would differ, it stops and writes nothing unless ``--replace`` is given: sheets that
were handed out could not be scored against a new key. With ``--draft`` the defaults of ``--out``
and ``--keys`` are the ``draft`` folders under the two shown above.

Re-audit after a rule fix. Both commands take another ``--out`` and ``--keys`` than the first
round, and each set is scored like any other.

* ``--round 2`` makes a fresh draw; ``--own``, ``--shared`` and ``--planted`` set its size. Name
  the first round's ``outcome_train_sample.csv`` under ``--exclude``, beside the sample lists.
* ``--items LIST`` draws nothing: the real items are the events of the list (a CSV with
  ``event_id`` and, if it has it, ``assigned_to``), shown with the brackets as now derived.
  Rows with a ``planted`` cell are skipped, so the first round's key can be given as it is, once
  that round is scored. Planted items are added only when ``--planted`` is given. With
  ``--changed`` only the listed events are kept whose derived bracket differs from the
  ``true_*`` cells of that key: the items the fix affected.

For the test half ``--keys`` is ignored: the key goes to ``keys/`` under ``--out``, and ``score
--half test --dir external_data/sealed/audit`` reads it there. ``score`` first writes the
adjudication sheet and the planted-item result (exit status 3); run again once ``decision`` is
filled, it prints the confirmed errors and exits 0 on pass, 1 on fail. Sheets that do not
validate, or that do not belong to the key, are not scored (exit status 2).
"""

from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.coling import corpus as C

SEED = 20261001
HALVES = ("train", "test")
AUDITORS = ("A1", "A2")
SHARED = "both"
DEFS = ("B", "A")  # the definitions audited, B first (the main check)
SIZES = {"train": (20, 10, 3), "test": (20, 10, 2)}  # own per auditor, shared, planted per auditor
STRATUM_FLOOR = 2
MAX_PER_GENERIC = 2
PRE_CAPTURES = 2
GAP_DAYS = 90
RELAPSE_DAYS = 90
ALLOWED_ERROR_PERCENT = 5  # pass: confirmed errors <= 5% of the real items (2 of 50)
PLANTED_MISS_LIMIT = 2  # an auditor who misses this many planted items re-checks their own
TRAIN_OUT = Path("analysis/coling/out/audit_outcomes")
TRAIN_KEYS = Path("external_data/annotation/keys")  # git-ignored; AUDIT_GUIDE.md section 10
DRAFT_DIR = "draft"  # a draft goes to this folder under the two above, never beside a final set
DRAFT_NOTE = "a draft is not given to the annotators: it can show threads of statements they label"
SAMPLE_LISTS = Path("analysis/coling/out/audit/samples")  # where audit_sample.py writes its lists
SEALED = "sealed"  # the test half is written and scored only under a folder of this name
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")  # as corpus.availability_key masks them
WITHHELD = "other_thread_withheld"

TYPES = ("recovered", "discontinued", "censored", "not_at_risk")
VERDICTS = ("ok", "error", "cannot_tell")
DECISIONS = ("confirmed", "rejected", "unresolved")
CODES = {
    "O1": "linkage: another presentation's rows are linked, or a re-formatted one is missed",
    "O2": "event start: wrong c0 or wrong statement date",
    "O3": "at risk: marked at risk when not, or the other way round",
    "O4": "class: an availability string or status read into the wrong class, moving a bound",
    "O5": "lower is not the last capture seen not recovered",
    "O6": "upper is not the first capture showing the event",
    "O7": "competing event missed, or wrongly assigned",
    "O8": "censoring: closed when open, open when an event is visible, or the wrong reason",
    "O9": "other; explained in note",
}
NOTE_CODES = {  # flags, never errors (the guide's N1 to N6)
    "N1": "a tighter bound is visible (Date of update of the first recovered row)",
    "N2": "relapse within 90 days after upper",
    "N3": "conflicting fields",
    "N4": "the bracket spans an archive gap of more than 90 days",
    "N5": "a debatable class that does not move a bound of B or A",
    "N6": "the derived value follows the rule, but the text says something the rule cannot record",
}
LETTERS = {"available": "A", "limited": "L", "unavailable": "U", "other": "O", "blank": "B"}
PLANT_KINDS = {
    "upper_later": "O6",
    "lower_earlier": "O5",
    "type_swapped": "O7",
    "wrong_presentation": "O1",
}

SHOWN = (
    "audit_id",
    "generic",
    "company",
    "presentation",
    "statement_text",
    "statement_date",
    "c0",
    "followed_to",
    "class_strip",
    "derived_B_type",
    "derived_B_lower",
    "derived_B_upper",
    "derived_B_width",
    "derived_B_censor",
    "derived_B_exit",
    "derived_A_type",
    "derived_A_lower",
    "derived_A_upper",
    "derived_A_width",
    "derived_A_censor",
    "derived_A_exit",
    "group_n_presentations",
    "group_B_type",
    "group_B_lower",
    "group_B_upper",
    "group_A_type",
    "group_A_lower",
    "group_A_upper",
)
ENTERED = (
    "verdict_B",
    "verdict_A",
    "codes_B",
    "codes_A",
    "true_B_type",
    "true_B_lower",
    "true_B_upper",
    "true_A_type",
    "true_A_lower",
    "true_A_upper",
    "note_codes",
    "dou_first_recovered",
    "note",
)
SHEET_COLUMNS = (*SHOWN, *ENTERED)
TRACE_COLUMNS = (
    "audit_id",
    "capture_date",
    "capture",
    "window",
    "present",
    "linked_by",
    "generic",
    "company",
    "presentation",
    "status",
    "type_of_update",
    "date_of_update",
    "availability_information",
    "related_information",
    "resolved_note",
    "change_date",
    "date_discontinued",
    "same_text",
    "generic_state",
    "discontinuation_listing",
    "discontinuation_date",
    "class_letter",
    "gap_before_days",
)
RAW_CELLS = {
    "generic": "generic_name",
    "company": "company_name",
    "presentation": "presentation",
    "status": "status",
    "type_of_update": "type_of_update",
    "date_of_update": "date_of_update",
    "availability_information": "availability",
    "related_information": "related",
    "resolved_note": "resolved_note",
    "change_date": "change_date",
    "date_discontinued": "date_discontinued",
}
KEY_COLUMNS = (
    "audit_id",
    "event_id",
    "thread_id",
    "statement_group_id",
    "assigned_to",
    "planted",
    "planted_definitions",
    "expected_code",
    "linked_thread_id",
    "stratum",
    "stratum_pool",
    "stratum_drawn",
    *(
        f"{side}_{d}_{part}"
        for d in DEFS
        for side in ("true", "shown")
        for part in ("type", "lower", "upper", "censor")
    ),
)
SAMPLE_COLUMNS = ("event_id", "statement_group_id", "thread_id")
STRATA_COLUMNS = ("stratum", "events", "excluded", "pool", "quota", "drawn")
ADJUDICATION_SHOWN = (
    "audit_id",
    "definition",
    "shown_type",
    "shown_lower",
    "shown_upper",
    "shown_censor",
    *(
        f"{a}_{part}"
        for a in AUDITORS
        for part in ("verdict", "codes", "true", "note_codes", "note")
    ),
)
ADJUDICATION_ENTERED = ("decision", "confirmed_codes", "cause", "adj_note")
ID_COLUMNS = ("event_id", "statement_group_id", "thread_id")
EVENT_FIELDS = (
    "thread_id",
    "generic_id",
    "generic_name",
    "company_name",
    "presentation",
    "statement_text",
    "first_seen_date",
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def draw_key(tag: str, item: str, seed: int = SEED) -> str:
    """Position of ``item`` in the seeded draw named ``tag`` (a sha256, compared as text)."""
    return hashlib.sha256(f"{seed}\x1f{tag}\x1f{item}".encode()).hexdigest()


def shuffled(ids: Iterable[str], tag: str, seed: int = SEED) -> list[str]:
    """The ids in the seeded order of the draw ``tag``; the result ignores the input order."""
    return sorted(sorted(set(ids)), key=lambda i: draw_key(tag, i, seed))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def masked(text: Any) -> Any:
    """Text with every e-mail address replaced by ``[email]``; other values pass unchanged."""
    return EMAIL.sub("[email]", text) if isinstance(text, str) else text


def labelled(name: str, label: str) -> str:
    """A file name with ``_label`` before its suffix (the name itself when there is no label)."""
    stem, dot, suffix = name.rpartition(".")
    return f"{stem}_{label}{dot}{suffix}" if label else name


def clock(text: str) -> int | None:
    """Minutes after midnight of an ``HH:MM`` time (seconds, if a spreadsheet added them, drop)."""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", text.strip())
    if match is None or int(match[1]) > 23 or int(match[2]) > 59:
        return None
    return int(match[1]) * 60 + int(match[2])


def session_minutes(meta: dict[str, str]) -> int | None:
    """Minutes an auditor worked, from the ``session_start`` and ``session_end`` header lines
    (one ``HH:MM`` per sitting, separated by semicolons). None when a time is missing or
    unreadable, or when the two lines do not pair up. A sitting may run past midnight."""
    starts = [clock(t) for t in meta.get("session_start", "").split(";") if t.strip()]
    ends = [clock(t) for t in meta.get("session_end", "").split(";") if t.strip()]
    if not starts or len(starts) != len(ends) or None in starts or None in ends:
        return None
    return sum((end - start) % (24 * 60) for start, end in zip(starts, ends, strict=True))


def split_list(cell: str) -> list[str]:
    """Codes in a cell written as a list separated by semicolons, commas or spaces."""
    return [p for p in re.split(r"[;,\s]+", (cell or "").strip()) if p]


def is_iso(text: str) -> bool:
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        return False
    return len(text) == 10


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    """Wilson 95% interval for k successes in n."""
    if n == 0:
        return None
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denominator = 1 + z * z / n
    return (max(0.0, (centre - half) / denominator), min(1.0, (centre + half) / denominator))


def cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters; None when it is undefined (no pairs, or one category)."""
    n = len(pairs)
    if n == 0:
        return None
    agree = sum(a == b for a, b in pairs) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(first[c] * second[c] for c in first) / (n * n)
    return None if chance >= 1 else (agree - chance) / (1 - chance)


# ---------------------------------------------------------------------------
# Sheets as files: '# key: value' lines, then one CSV table
# ---------------------------------------------------------------------------


def guarded(value: Any) -> Any:
    """A text cell that a spreadsheet would take for a formula gets a leading apostrophe."""
    return "'" + value if isinstance(value, str) and value[:1] in tuple("=+-@") else value


def csv_text(
    columns: Sequence[str], rows: Iterable[dict[str, Any]], meta: dict[str, Any], sheet: bool = True
) -> str:
    """CSV text under ``# key: value`` lines. A ``sheet`` is opened by people: every cell is
    quoted and formula-like cells are guarded. Lists read by code are written plainly."""
    buf = io.StringIO()
    for key, value in meta.items():
        buf.write(f"# {key}: {value}\n")
    quoting = csv.QUOTE_ALL if sheet else csv.QUOTE_MINIMAL
    writer = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n", quoting=quoting)
    writer.writeheader()
    for row in rows:
        cells = {c: row.get(c, "") for c in columns}
        writer.writerow({c: guarded(v) for c, v in cells.items()} if sheet else cells)
    return buf.getvalue()


def parse_sheet(text: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Split a sheet into its ``# key: value`` lines and its rows (cells stripped).

    The comment lines are read by hand, since a spreadsheet may have quoted and padded them.
    """
    cells = list(csv.reader(io.StringIO(text.removeprefix(chr(0xFEFF)), newline="")))
    meta: dict[str, str] = {}
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for line in cells:
        if not any(c.strip() for c in line):
            continue
        if not header and line[0].strip().startswith("#"):
            key, _, value = ",".join(c for c in line if c).lstrip("# ").partition(":")
            meta[key.strip()] = value.strip()
        elif not header:
            header = [c.strip() for c in line]
        else:
            padded = [*line, *([""] * len(header))]
            rows.append({h: padded[i].strip() for i, h in enumerate(header) if h})
    return meta, rows


def read_sheet(path: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        return parse_sheet(handle.read())


@dataclass
class Sink:
    """Writes files under one root only, and remembers their sha256.

    With ``hold`` nothing reaches the disk before ``commit``, so that a whole set can be compared
    with the one already there before any file of it is replaced.
    """

    root: Path
    hold: bool = False
    written: dict[str, str] = field(default_factory=dict)
    pending: dict[str, bytes] = field(default_factory=dict)

    def write(self, name: str, text: str) -> Path:
        root = self.root.resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"{name} is outside {self.root}")
        data = text.encode("utf-8")
        self.pending[name] = data
        self.written[name] = hashlib.sha256(data).hexdigest()
        if not self.hold:
            self.commit()
        return path

    def commit(self) -> None:
        for name, data in self.pending.items():
            path = self.root.resolve() / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.pending.clear()


# ---------------------------------------------------------------------------
# The built corpus, one half
# ---------------------------------------------------------------------------


@dataclass
class Built:
    """Events and outcomes of one half, with the per-capture lookups the traces need."""

    half: str
    ctx: C.Context
    events: dict[str, C.Event]
    table: pd.DataFrame  # every event's statement-time fields (all periods; no outcome)
    frame: pd.DataFrame  # outcomes of this half, indexed by event_id, with EVENT_FIELDS
    raw: dict[str, list[Any]]
    thread_ids: dict[int, str]
    members: dict[str, list[str]]
    by_ndc: dict[int, dict[str, list[int]]]
    siblings: dict[tuple[int, str, str], list[int]]


def assemble(corpus: C.Corpus, half: str) -> Built:
    """Keep one half of a built corpus. The other half's outcomes are dropped here."""
    obs = corpus.captures.obs
    ctx = C.Context(corpus.captures)
    events = C.split_events(obs)
    C.date_events(events, obs)
    C.assign_ids(events, obs)
    out = corpus.outcomes
    out = out[out["period"] == half] if len(out) else out
    if not len(out):
        raise ValueError(f"no {half}-period shortage events in the captures")
    extra = [c for c in EVENT_FIELDS if c not in out.columns]
    frame = out.merge(corpus.events[["event_id", *extra]], on="event_id", how="left")
    frame = frame.set_index("event_id", drop=False).sort_index()
    frame.index.name = None
    frame["stratum"] = add_strata(frame)
    columns = ("key", "stmt_key", "ndcs", "thread", "listing", *RAW_CELLS.values())
    raw = {name: obs[name].tolist() for name in dict.fromkeys(columns)}
    by_ndc: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    siblings: dict[tuple[int, str, str], list[int]] = defaultdict(list)
    col = ctx.col
    for i, listing in enumerate(raw["listing"]):
        if listing == "shortage":
            siblings[(col["cap_idx"][i], col["generic_id"][i], col["c_norm"][i])].append(i)
            for ndc in raw["ndcs"][i]:
                by_ndc[col["cap_idx"][i]][ndc].append(i)
    members: dict[str, list[str]] = defaultdict(list)
    for event_id, group in zip(frame["event_id"], frame["statement_group_id"], strict=True):
        members[group].append(event_id)
    return Built(
        half=half,
        ctx=ctx,
        events={ev.event_id: ev for ev in events},
        table=corpus.events,
        frame=frame,
        raw=raw,
        thread_ids={ev.thread: ev.thread_id for ev in events},
        members=dict(members),
        by_ndc=by_ndc,
        siblings=siblings,
    )


def load(captures: Path, half: str) -> Built:
    """Build the corpus in memory (nothing is written) and keep one half."""
    return assemble(C.build_corpus(captures), half)


# ---------------------------------------------------------------------------
# Exclusions: by statement and thread
# ---------------------------------------------------------------------------


def exclusion_files(paths: Iterable[Path]) -> list[Path]:
    """The sample lists under ``paths``: files as given, directories searched for CSV and JSONL.

    A search skips this module's own files (``outcome_*``), so that a second run does not exclude
    the first run's sample; name such a file itself to exclude it (a re-audit round).
    """
    suffixes = (".csv", ".csv.gz", ".jsonl", ".jsonl.gz")
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            inside = (p for p in path.rglob("*") if p.is_file() and p.name.endswith(suffixes))
            found += sorted(p for p in inside if not p.name.startswith("outcome_"))
        elif path.is_file():
            found.append(path)
    return found


def read_ids(path: Path) -> dict[str, set[str]]:
    """The event, statement-group and thread ids named in one sample list."""
    if path.name.removesuffix(".gz").endswith(".jsonl"):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
    else:
        _, records = read_sheet(path)
    return {c: {str(r[c]) for r in records if isinstance(r, dict) and r.get(c)} for c in ID_COLUMNS}


def guide_examples(text: str) -> list[tuple[str, str, str]]:
    """(generic, company, statement date) of the statements the guide excludes from every sample:
    the rows of the tables of its Appendix A (first three cells; a cell may hold several dates)."""
    parts = text.split("\n## Appendix A", 1)
    if len(parts) < 2:
        return []
    out = []
    for line in parts[1].split("\n## ", 1)[0].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) >= 3:
            for date in re.findall(r"\d{4}-\d{2}-\d{2}", cells[2]):
                out.append((C.norm_text(cells[0]), C.norm_text(cells[1]), date))
    return out


def excluded_threads(
    table: pd.DataFrame, ids: dict[str, set[str]], examples: Iterable[tuple[str, str, str]]
) -> tuple[set[str], list[tuple[str, str, str]]]:
    """Threads the audit must skip, and the guide examples that matched no event.

    A thread is skipped when it carries a named event or statement, a guide example (or the
    same generic, company and normalised text at another date, as the guide's Appendix A says),
    or any presentation of such a statement.
    """
    wanted = set(examples)
    generic = table["generic_name"].map(C.norm_text)
    company = table["company_name"].map(C.norm_text)
    keys = list(zip(generic, company, table["event_date"], strict=True))
    texts = list(zip(generic, company, table["statement_text"].map(C.norm_text), strict=True))
    quoted = {t for k, t in zip(keys, texts, strict=True) if k in wanted}
    seed = (
        table["event_id"].isin(ids.get("event_id", set()))
        | table["statement_group_id"].isin(ids.get("statement_group_id", set()))
        | table["thread_id"].isin(ids.get("thread_id", set()))
        | pd.Series([t in quoted for t in texts], index=table.index)
    )
    groups = set(table.loc[seed, "statement_group_id"])
    threads = set(table.loc[seed | table["statement_group_id"].isin(groups), "thread_id"])
    return threads | set(ids.get("thread_id", set())), sorted(wanted - set(keys))


def audited_threads(table: pd.DataFrame, ids: dict[str, set[str]]) -> set[str]:
    """Threads of an earlier outcome-audit sample: those it names and those of its events. The
    other presentations of an audited statement are other audit units, and stay in the pool."""
    named = table["thread_id"].isin(ids.get("thread_id", set()))
    return set(table.loc[named | table["event_id"].isin(ids.get("event_id", set())), "thread_id"])


def unknown_ids(table: pd.DataFrame, ids: dict[str, set[str]]) -> int:
    """How many listed ids name no event of the built corpus. Any at all means that the lists
    were drawn from another build, so the exclusion would be incomplete."""
    return sum(len(ids.get(c, set()) - set(table[c])) for c in ID_COLUMNS)


# ---------------------------------------------------------------------------
# Strata, allocation and the draw
# ---------------------------------------------------------------------------


def stratum_of(kind: str, width: Any, reconfirmed: bool) -> str:
    """Stratum name: definition-B outcome type / bracket width class / re-confirmed or single."""
    wide = "none"
    if kind in ("recovered", "discontinued") and width is not None and not pd.isna(width):
        wide = "le31" if width <= 31 else "32to90" if width <= 90 else "gt90"
    return f"{kind}/{wide}/{'reconfirmed' if reconfirmed else 'single'}"


def add_strata(frame: pd.DataFrame) -> pd.Series:
    cells = zip(frame["outcome_B"], frame["width_days_B"], frame["n_reconfirmations"], strict=True)
    return pd.Series([stratum_of(k, w, n > 0) for k, w, n in cells], index=frame.index, dtype=str)


def allocate(sizes: dict[str, int], n: int, floor: int = STRATUM_FLOOR) -> dict[str, int]:
    """Items per stratum: ``floor`` each (or all it has), the rest in proportion to the pool.

    The proportional part uses largest remainders (ties by name). A stratum never gets more than
    it holds; what it cannot take goes round again. If the floors alone exceed ``n`` they are
    cut back, largest stratum first.
    """
    alloc = {s: min(size, floor) for s, size in sizes.items() if size > 0}
    while sum(alloc.values()) > n:
        top = max(alloc, key=lambda s: (alloc[s], sizes[s], s))
        alloc[top] -= 1
    left = n - sum(alloc.values())
    while left > 0:
        room = {s: sizes[s] - alloc[s] for s in alloc if sizes[s] > alloc[s]}
        if not room:
            break
        total = sum(sizes[s] for s in room)
        share = {s: left * sizes[s] / total for s in room}
        give = {s: min(int(share[s]), room[s]) for s in room}
        spare = left - sum(give.values())
        for s in sorted(room, key=lambda s: (int(share[s]) - share[s], s)):
            if spare > 0 and give[s] < room[s]:
                give[s] += 1
                spare -= 1
        for s, k in give.items():
            alloc[s] += k
        left = n - sum(alloc.values())
    return alloc


@dataclass
class Taken:
    """Threads, statement groups and generics already used by drawn items."""

    threads: set[str] = field(default_factory=set)
    groups: set[str] = field(default_factory=set)
    generics: Counter[str] = field(default_factory=Counter)

    def free(self, row: pd.Series) -> bool:
        return (
            row["thread_id"] not in self.threads
            and row["statement_group_id"] not in self.groups
            and self.generics[row["generic_id"]] < MAX_PER_GENERIC
        )

    def add(self, row: pd.Series) -> None:
        self.threads.add(row["thread_id"])
        self.groups.add(row["statement_group_id"])
        self.generics[row["generic_id"]] += 1


def draw(pool: pd.DataFrame, quota: dict[str, int], tag: str, taken: Taken) -> list[str]:
    """Event ids drawn stratum by stratum (smallest pool first) under the caps of ``Taken``.

    A stratum that cannot fill its quota passes the shortfall to the others, largest pool first.
    """
    by_stratum = {s: shuffled(g.index, f"{tag}/sample") for s, g in pool.groupby("stratum")}
    position = dict.fromkeys(by_stratum, 0)
    chosen: list[str] = []

    def take(stratum: str, wanted: int) -> int:
        got = 0
        ids = by_stratum[stratum]
        while got < wanted and position[stratum] < len(ids):
            event_id = ids[position[stratum]]
            position[stratum] += 1
            if taken.free(pool.loc[event_id]):
                taken.add(pool.loc[event_id])
                chosen.append(event_id)
                got += 1
        return got

    short = 0
    for stratum in sorted(quota, key=lambda s: (len(by_stratum[s]), s)):
        short += quota[stratum] - take(stratum, quota[stratum])
    for stratum in sorted(by_stratum, key=lambda s: (-len(by_stratum[s]), s)):
        if short <= 0:
            break
        short -= take(stratum, short)
    return chosen


def assign(n_items: int, own: int, shared: int) -> list[str]:
    """Who audits each of ``n_items`` taken in order: A1, A2 and both, spread evenly."""
    target = {AUDITORS[0]: own, AUDITORS[1]: own, SHARED: shared}
    total = sum(target.values()) or 1
    given: Counter[str] = Counter()
    out = []
    for i in range(n_items):
        who = max(
            target, key=lambda k: (target[k] * (i + 1) / total - given[k], -list(target).index(k))
        )
        given[who] += 1
        out.append(who)
    return out


# ---------------------------------------------------------------------------
# Brackets, as capture indexes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bracket:
    """An outcome under one definition; ``lower`` and ``upper`` are capture indexes, ``exit`` is
    the date of the first capture where a censored thread was missing."""

    kind: str
    lower: int | None = None
    upper: int | None = None
    censor: str = ""
    exit: str = ""

    @property
    def closed(self) -> bool:
        return self.kind in ("recovered", "discontinued") and self.upper is not None


def derive(
    ev: C.Event, ctx: C.Context, risk: dict[str, bool] | None = None
) -> tuple[int, dict[str, Bracket]]:
    """The event's horizon and its bracket under each audited definition, by the builder's code."""
    horizon = ctx.horizon(ev)
    risk = C.at_risk(ev, ctx) if risk is None else risk
    track = C.walk(ev, ctx, risk, horizon)
    out = {}
    for d in DEFS:
        rec = C.bracket(d, risk[d], track[d], ev, ctx, horizon)
        lower = track[d]["lower"] if risk[d] else None
        upper = track[d]["upper"] if risk[d] else None
        reason, left = rec[f"censor_reason_{d}"], rec[f"exit_date_{d}"]
        out[d] = Bracket(rec[f"outcome_{d}"], lower, upper, reason, left)
    return horizon, out


def cap_date(ctx: C.Context, cap: int | None) -> str:
    return "" if cap is None else C.iso(ctx.dates[cap])


def width_days(ctx: C.Context, b: Bracket) -> int | str:
    if b.lower is None or b.upper is None:
        return ""
    return (ctx.dates[b.upper] - ctx.dates[b.lower]).days


def bracket_cells(ctx: C.Context, b: Bracket) -> dict[str, Any]:
    return {
        "type": b.kind,
        "lower": cap_date(ctx, b.lower),
        "upper": cap_date(ctx, b.upper),
        "width": width_days(ctx, b),
        "censor": b.censor,
        "exit": b.exit,
    }


@dataclass
class Item:
    """One audit item: an event, what the sheet shows for it and what is true."""

    event_id: str
    ev: C.Event
    walker: C.Event  # the event, or for a wrong-presentation plant a stand-in on another thread
    horizon: int
    true: dict[str, Bracket]
    shown: dict[str, Bracket]
    stratum: str = ""
    assigned: str = ""
    planted: str = ""
    audit_id: str = ""

    @property
    def planted_definitions(self) -> list[str]:
        return [d for d in DEFS if self.shown[d] != self.true[d]]


def real_item(b: Built, event_id: str) -> Item:
    """An item that shows the derived bracket; fails if it differs from the outcome table."""
    ev = b.events[event_id]
    horizon, true = derive(ev, b.ctx)
    row = b.frame.loc[event_id]
    for d in DEFS:
        cells = bracket_cells(b.ctx, true[d])
        table = (row[f"outcome_{d}"], row[f"lower_date_{d}"], row[f"upper_date_{d}"])
        if (cells["type"], cells["lower"], cells["upper"]) != tuple(
            "" if pd.isna(v) else v for v in table
        ):
            raise RuntimeError(f"{event_id}: definition {d} differs from the outcome table")
    return Item(event_id, ev, ev, horizon, true, dict(true), stratum=row["stratum"])


# ---------------------------------------------------------------------------
# Planted items
# ---------------------------------------------------------------------------


def step(ctx: C.Context, cap: int, direction: int, stop: int) -> int | None:
    """The nearest capture after (or before) ``cap`` with another date, not past ``stop``."""
    k = cap + direction
    while 0 <= k < len(ctx.dates) and (stop - k) * direction >= 0:
        if ctx.dates[k] != ctx.dates[cap]:
            return k
        k += direction
    return None


def perturb(kind: str, item: Item, b: Built, skip: set[str], tag: str) -> Item | None:
    """A copy of ``item`` with one planted error of ``kind``, or None when it cannot carry one.

    A move or a swap is made under B, and under A as well where A's value is the same, so that
    the shown pair stays possible under the rule (B is never later than A).
    """
    ctx, true = b.ctx, item.true
    base = true["B"]
    first = ctx.col["cap_idx"][item.ev.rows[0]]
    shown = dict(true)
    if kind == "wrong_presentation":
        return wrong_presentation(item, b, skip, tag)
    if not base.closed:
        return None
    if kind == "upper_later":
        later = step(ctx, base.upper, 1, item.horizon)
        if later is None:
            return None
        for d in DEFS:
            if true[d].closed and true[d].upper == base.upper:
                shown[d] = replace(true[d], upper=later)
    elif kind == "lower_earlier":
        earlier = step(ctx, base.lower, -1, first)
        if earlier is None:
            return None
        for d in DEFS:
            if true[d].closed and true[d].lower == base.lower:
                shown[d] = replace(true[d], lower=earlier)
    elif kind == "type_swapped":
        if (true["A"].kind, true["A"].upper) != (base.kind, base.upper):
            return None
        other = "discontinued" if base.kind == "recovered" else "recovered"
        shown = {d: replace(true[d], kind=other) for d in DEFS}
    else:
        raise ValueError(kind)
    return replace(item, shown=shown, planted=kind)


def wrong_presentation(item: Item, b: Built, skip: set[str], tag: str) -> Item | None:
    """Link another presentation of the same generic and company after ``c0``.

    The shown bracket is what the rule gives on that other thread from ``c0``, under the event's
    own at-risk status; it must differ from the true one under B. The other thread must have a
    row in the trace window after ``c0``: without one the trace would show only absences, and
    nothing in it could tell the auditor that the link is wrong.
    """
    ctx, raw = b.ctx, b.raw
    i = item.ev.rows[0]
    cap = ctx.col["cap_idx"][i]
    pool = b.siblings.get((cap, ctx.col["generic_id"][i], ctx.col["c_norm"][i]), [])
    others = {
        raw["key"][j]: j
        for j in pool
        if raw["thread"][j] != item.ev.thread
        and not (raw["ndcs"][j] & raw["ndcs"][i])
        and ctx.col["p_norm"][j] != ctx.col["p_norm"][i]
        and b.thread_ids.get(int(raw["thread"][j])) not in skip
    }
    risk = C.at_risk(item.ev, ctx)
    for key in shuffled(others, f"{tag}/sibling/{item.event_id}"):
        j = others[key]
        walker = C.Event(int(raw["thread"][j]), 0, [j], date=item.ev.date)
        horizon, shown = derive(walker, ctx, risk)
        end = window_end(shown, cap, horizon, ctx.dates)
        visible = any(cap < c <= end for c in ctx.thread_caps[walker.thread])
        if shown["B"] != item.true["B"] and visible:
            return replace(item, walker=walker, shown=shown, planted="wrong_presentation")
    return None


def plant(
    b: Built, pool: pd.DataFrame, taken: Taken, skip: set[str], per_auditor: int, tag: str
) -> list[Item]:
    """Planted items for both auditors, kinds in a seeded rotation, from events not yet taken.

    An auditor gets a kind a second time only when no event can carry any kind they lack.
    """
    kinds = shuffled(PLANT_KINDS, f"{tag}/kinds")
    at_risk = pool[pool["outcome_B"] != "not_at_risk"]
    items: list[Item] = []
    for slot in range(len(AUDITORS) * per_auditor):
        auditor = AUDITORS[slot // per_auditor]
        given = {it.planted for it in items if it.assigned == auditor}
        rotation = [kinds[(slot + k) % len(kinds)] for k in range(len(kinds))]
        wanted = sorted(rotation, key=lambda kind: kind in given)  # stable: new kinds first
        made = None
        for kind in wanted:
            for event_id in shuffled(at_risk.index, f"{tag}/plant/{kind}"):
                row = at_risk.loc[event_id]
                if not taken.free(row):
                    continue
                made = perturb(kind, real_item(b, event_id), b, skip | taken.threads, tag)
                if made is not None:
                    taken.add(row)
                    if made.walker is not made.ev:
                        taken.threads.add(b.thread_ids[made.walker.thread])
                    break
            if made is not None:
                break
        if made is not None:
            made.assigned = auditor
            items.append(made)
    return items


# ---------------------------------------------------------------------------
# Traces and sheet rows
# ---------------------------------------------------------------------------


def window_end(shown: dict[str, Bracket], first: int, horizon: int, dates: Sequence[Any]) -> int:
    """Last capture shown: the horizon for an open outcome, else past the last upper bound."""
    at_risk = [s for s in shown.values() if s.kind != "not_at_risk"]
    if any(s.kind == "censored" for s in at_risk):
        return horizon
    uppers = [s.upper for s in at_risk if s.upper is not None]
    last = max(uppers, default=first)
    end = min(last + 1, horizon)
    if uppers:
        anchor = shown["B"].upper if shown["B"].upper is not None else last
        while end < horizon and (dates[end + 1] - dates[anchor]).days <= RELAPSE_DAYS:
            end += 1
    return end


def context_caps(thread_caps: Sequence[int], first: int, last: int | None = None) -> list[int]:
    """Captures shown before ``c0``: the last PRE_CAPTURES, and the thread's last earlier row.

    With ``last``, none after that capture: a train event first captured in the test period
    shows nothing between the train horizon and its own first row.
    """
    caps = list(range(max(0, first - PRE_CAPTURES), first))
    earlier = [c for c in thread_caps if c < first]
    if earlier and earlier[-1] not in caps:
        caps.insert(0, earlier[-1])
    return [c for c in caps if last is None or c <= last]


def letter_of_row(ctx: C.Context, row: int) -> str:
    if ctx.col["status_norm"][row] == "resolved":
        return "R"
    return LETTERS.get(ctx.col["avail_class"][row], "O")


def class_letter(item: Item, b: Built, cap: int, disc_at_start: bool) -> str:
    """The builder's reading of one capture as a letter (see the module docstring)."""
    ctx = b.ctx
    first = ctx.col["cap_idx"][item.ev.rows[0]]
    thread = item.walker.thread if cap > first else item.ev.thread
    row = ctx.thread_rows[thread].get(cap)
    if cap <= first:
        if row is not None:
            return letter_of_row(ctx, row)
        return "r" if generic_status(item, b, cap) == "resolved" else "."
    state = C.state_at(item.walker, ctx, cap, disc_at_start)
    if state.how == "discontinuation_listing":
        return "D"
    if row is not None:
        return letter_of_row(ctx, row)
    return "r" if state.how == "exit_generic_resolved" else "."


def probe_row(item: Item, b: Built, cap: int) -> int:
    """The item's row at ``cap``, else its last row before, else the event's first row."""
    first = b.ctx.col["cap_idx"][item.ev.rows[0]]
    thread = item.walker.thread if cap > first else item.ev.thread
    if b.ctx.thread_caps[thread][0] <= cap:
        return b.ctx.row_at_or_before(thread, cap)
    return item.ev.rows[0]


def generic_status(item: Item, b: Built, cap: int) -> str:
    return b.ctx.generic_state(probe_row(item, b, cap), cap) or "unlisted"


def raw_cells(b: Built, row: int | None, names: Iterable[str] = tuple(RAW_CELLS)) -> dict[str, str]:
    """The cells of one capture row as the FDA wrote them, e-mail addresses masked."""
    return {n: "" if row is None else masked(b.raw[RAW_CELLS[n]][row]) for n in names}


def trace(
    item: Item, b: Built, withheld: frozenset[str] | set[str] = frozenset()
) -> tuple[list[dict[str, Any]], str]:
    """Trace rows of one item and its class strip.

    ``withheld`` holds the ids of the threads left out because of a labelling sample or a guide
    example. Where such a thread carries the item's NDC while the item is absent, its row is
    listed with its names only: its status and text belong to a statement an annotator labels.
    """
    ctx, raw = b.ctx, b.raw
    first = ctx.col["cap_idx"][item.ev.rows[0]]
    end = window_end(item.shown, first, item.horizon, ctx.dates)
    clip = ctx.train_last if item.ev.date < C.TEST_START else None
    disc_at_start = ctx.in_discontinuation(item.walker.rows[0], first)
    own = ctx.thread_rows[item.ev.thread]
    after = ctx.thread_rows[item.walker.thread]
    linked, seen = {}, set()
    path = [own[c] for c in sorted(own) if c <= first] + [
        after[c] for c in sorted(after) if c > first
    ]
    for n, i in enumerate(path):
        linked[i] = "key" if n == 0 or raw["key"][i] in seen else "ndc"
        seen.add(raw["key"][i])
    text = raw["stmt_key"][item.ev.rows[0]]
    rows, strip = [], []
    before = context_caps(ctx.thread_caps[item.ev.thread], first, clip)
    for cap in [*before, *range(first, end + 1)]:
        source = after if cap > first else own
        row = source.get(cap)
        probe = probe_row(item, b, cap)
        listed = ctx.discontinuation(probe, cap)
        letter = class_letter(item, b, cap, disc_at_start)
        gap = (ctx.dates[cap] - ctx.dates[cap - 1]).days if cap > 0 else ""
        shared = {
            "audit_id": item.audit_id,
            "capture_date": cap_date(ctx, cap),
            "capture": ctx.stamps[cap],
            "window": "before" if cap < first else "c0" if cap == first else "after",
            "generic_state": generic_status(item, b, cap),
            "discontinuation_listing": "" if listed is None else "listed",
            "discontinuation_date": listed or "",
            "gap_before_days": gap,
        }
        rows.append(
            {
                **shared,
                **raw_cells(b, row),
                "present": "no" if row is None else "yes",
                "linked_by": "" if row is None else linked[row],
                "same_text": "" if row is None else int(raw["stmt_key"][row] == text),
                "class_letter": letter,
            }
        )
        if row is None and cap > first:
            hits = {j for n in raw["ndcs"][probe] for j in b.by_ndc.get(cap, {}).get(n, [])}
            for j in sorted(hits):
                if raw["thread"][j] in (item.ev.thread, item.walker.thread):
                    continue
                if b.thread_ids.get(int(raw["thread"][j])) in withheld:
                    names = raw_cells(b, j, ("generic", "company", "presentation"))
                    rows.append({**shared, **names, "present": WITHHELD})
                else:
                    rows.append({**shared, **raw_cells(b, j), "present": "other_thread"})
        if cap >= first:
            if cap > first and gap != "" and gap > GAP_DAYS:
                strip.append("|")
            strip.append(letter)
    return rows, " ".join(strip)


def group_cells(item: Item, b: Built) -> dict[str, Any]:
    """The statement group's bracket, recomputed with what the sheet shows for this member."""
    row = b.frame.loc[item.event_id]
    members = b.frame.loc[b.members[row["statement_group_id"]]].copy()
    out: dict[str, Any] = {"group_n_presentations": len(members)}
    for d in DEFS:
        cells = bracket_cells(b.ctx, item.shown[d])
        members.loc[item.event_id, f"outcome_{d}"] = cells["type"]
        members.loc[item.event_id, f"lower_date_{d}"] = cells["lower"]
        members.loc[item.event_id, f"upper_date_{d}"] = cells["upper"]
        group = C.group_bracket(members, d)
        out[f"group_{d}_type"] = group[f"group_outcome_{d}"]
        out[f"group_{d}_lower"] = group[f"group_lower_date_{d}"]
        out[f"group_{d}_upper"] = group[f"group_upper_date_{d}"]
    return out


def sheet_row(item: Item, b: Built, strip: str) -> dict[str, Any]:
    row = b.frame.loc[item.event_id]
    out: dict[str, Any] = {
        "audit_id": item.audit_id,
        "generic": masked(row["generic_name"]),
        "company": masked(row["company_name"]),
        "presentation": masked(row["presentation"]),
        "statement_text": masked(row["statement_text"]),
        "statement_date": row["event_date"],
        "c0": row["first_seen_date"],
        "followed_to": cap_date(b.ctx, item.horizon),
        "class_strip": strip,
        **group_cells(item, b),
    }
    for d in DEFS:
        for part, value in bracket_cells(b.ctx, item.shown[d]).items():
            out[f"derived_{d}_{part}"] = value
    return out


def bracket_text(cells: dict[str, Any], prefix: str) -> str:
    kind, lower, upper = (cells[f"{prefix}_{part}"] for part in ("type", "lower", "upper"))
    if upper:
        width = cells.get(f"{prefix}_width", "")
        return f"{kind} ({lower}, {upper}]" + ("" if width == "" else f", {width} days")
    if lower:
        reason = cells.get(f"{prefix}_censor", "")
        return f"{kind} at {lower}" + (f" ({reason})" if reason else "")
    return kind


def trace_line(r: dict[str, Any], sheet: dict[str, Any]) -> str:
    """One trace row as text: ``<`` before c0, ``*`` at c0; class letter; then the cells. The
    names are given only where they differ from the item's own."""
    mark = {"before": "<", "c0": "*"}.get(r["window"], " ")
    if r["present"] == WITHHELD:
        names = " | ".join(f"{name}: {r[name]}" for name in ("generic", "company", "presentation"))
        return (
            "             another thread with this NDC | status and text withheld: "
            f"a thread of a labelling sample | {names}"
        )
    if r["present"] == "no":
        cells = [f"absent; generic {r['generic_state']}"]
    else:
        cells = [
            r["status"],
            f"{r['type_of_update']} {r['date_of_update']}".strip(),
            f"availability: {r['availability_information']}",
            f"related: {r['related_information']}",
        ]
        labels = (("resolved_note", "resolved note"), ("change_date", "change date"))
        cells += [f"{label}: {r[name]}" for name, label in labels if r[name]]
        if r["date_discontinued"]:
            cells.append(f"date discontinued: {r['date_discontinued']}")
        names = ("generic", "company", "presentation")
        cells += [f"{name}: {r[name]}" for name in names if r[name] != sheet[name]]
        if r.get("linked_by") == "ndc":
            cells.append("linked by NDC")
        if r.get("same_text") == 1:
            cells.append("same text")
    if r["discontinuation_listing"]:
        cells.append(f"in the discontinuation listing ({r['discontinuation_date']})")
    if r["gap_before_days"] != "" and r["gap_before_days"] > GAP_DAYS:
        cells.append(f"{r['gap_before_days']} days since the capture before")
    if r["present"] == "other_thread":
        return f"             another thread with this NDC | {' | '.join(cells)}"
    return f"{mark} {r['capture_date']} {r['class_letter']} | {' | '.join(cells)}"


def item_block(sheet: dict[str, Any], rows: list[dict[str, Any]], number: int, total: int) -> str:
    """One item as text: what the sheet shows, then its trace, one line per capture."""
    group = f"B {bracket_text(sheet, 'group_B')}; A {bracket_text(sheet, 'group_A')}"
    lines = [
        f"=== {sheet['audit_id']} (item {number} of {total})",
        f"generic: {sheet['generic']}",
        f"company: {sheet['company']}",
        f"presentation: {sheet['presentation']}",
        f"statement: {sheet['statement_text']}",
        f"statement date {sheet['statement_date']}; c0 {sheet['c0']}; "
        f"followed to {sheet['followed_to']}",
        f"derived B: {bracket_text(sheet, 'derived_B')}",
        f"derived A: {bracket_text(sheet, 'derived_A')}",
        f"statement group, {sheet['group_n_presentations']} presentation(s): {group}",
        f"class strip: {sheet['class_strip']}",
        *(trace_line(r, sheet) for r in rows),
    ]
    return "\n".join(lines) + "\n"


def key_row(item: Item, b: Built, strata: dict[str, dict[str, int]]) -> dict[str, Any]:
    row = b.frame.loc[item.event_id]
    cell = strata.get(item.stratum, {})
    out: dict[str, Any] = {
        "audit_id": item.audit_id,
        "event_id": item.event_id,
        "thread_id": row["thread_id"],
        "statement_group_id": row["statement_group_id"],
        "assigned_to": item.assigned,
        "planted": item.planted,
        "planted_definitions": ";".join(item.planted_definitions),
        "expected_code": PLANT_KINDS.get(item.planted, ""),
        "linked_thread_id": b.thread_ids[item.walker.thread] if item.walker is not item.ev else "",
        "stratum": item.stratum,
        "stratum_pool": cell.get("pool", ""),
        "stratum_drawn": cell.get("drawn", ""),
    }
    for d in DEFS:
        for side, bracket in (("true", item.true[d]), ("shown", item.shown[d])):
            cells = bracket_cells(b.ctx, bracket)
            for part in ("type", "lower", "upper", "censor"):
                out[f"{side}_{d}_{part}"] = cells[part]
    return out


# ---------------------------------------------------------------------------
# The sheet generator
# ---------------------------------------------------------------------------


@dataclass
class Drawn:
    items: list[Item]
    strata: list[dict[str, Any]]
    counts: dict[str, int]
    # threads of the labelling samples and of the guide's examples: their text is never shown
    withheld: frozenset[str] = frozenset()


def listed_rows(path: Path) -> list[dict[str, str]]:
    """The real items named in a list for a re-audit: a CSV with ``event_id`` and, if it has
    them, ``assigned_to`` and the ``true_*`` cells of an earlier key. Rows with a ``planted``
    cell are left out, so that the key of an earlier round can be given as it is."""
    rows = [r for r in read_sheet(path)[1] if r.get("event_id") and not r.get("planted")]
    if not rows:
        raise SystemExit(f"{path}: no row with an event_id")
    if len({r["event_id"] for r in rows}) != len(rows):
        raise SystemExit(f"{path}: an event_id is listed more than once")
    wrong = sorted({r.get("assigned_to") or SHARED for r in rows} - {*AUDITORS, SHARED})
    if wrong:
        raise SystemExit(f"{path}: assigned_to must be {', '.join((*AUDITORS, SHARED))}")
    return rows


def same_bracket(b: Built, item: Item, row: dict[str, str]) -> bool:
    """Whether the bracket now derived is the one an earlier key recorded as true, under both
    definitions (type, bounds and censoring reason)."""
    for d in DEFS:
        cells = bracket_cells(b.ctx, item.true[d])
        for part in ("type", "lower", "upper", "censor"):
            if f"true_{d}_{part}" not in row:
                raise SystemExit("--changed needs the true_* columns of an earlier key")
            if cells[part] != row[f"true_{d}_{part}"]:
                return False
    return True


def named_items(b: Built, listed: list[dict[str, str]], changed: bool) -> tuple[list[Item], int]:
    """The listed events as items, assigned as the list says (to both auditors when it does not
    say), and the number of rows that name no event of this half in the corpus as built. With
    ``changed``, only the events whose derived bracket differs from the one the list records."""
    items, missing = [], 0
    for row in sorted(listed, key=lambda r: r["event_id"]):
        if row["event_id"] not in b.frame.index:
            missing += 1
            continue
        item = real_item(b, row["event_id"])
        item.assigned = row.get("assigned_to") or SHARED
        if not (changed and same_bracket(b, item, row)):
            items.append(item)
    return items, missing


def draw_items(
    b: Built,
    skip: set[str],
    own: int,
    shared: int,
    planted: int,
    tag: str,
    listed: list[dict[str, str]] | None = None,
    changed: bool = False,
) -> Drawn:
    """Draw the real items and the planted ones, assign them and give every item its id.

    With ``listed`` nothing is drawn: the real items are the listed events, whatever the
    exclusions say (they were drawn under them before), and ``own`` and ``shared`` are unused.
    """
    frame = b.frame
    pool = frame[~frame["thread_id"].isin(skip)]
    sizes = pool["stratum"].value_counts().to_dict()
    taken = Taken()
    items: list[Item] = []
    missing = 0
    if listed is None:
        n_real = len(AUDITORS) * own + shared
        quota = allocate(sizes, n_real)
        chosen = draw(pool, quota, tag, taken)
        ordered = sorted(
            chosen, key=lambda e: (pool.at[e, "stratum"], draw_key(f"{tag}/assign", e))
        )
        for event_id, who in zip(ordered, assign(len(ordered), own, shared), strict=True):
            item = real_item(b, event_id)
            item.assigned = who
            items.append(item)
    else:
        quota = {}
        items, missing = named_items(b, listed, changed)
        chosen = [item.event_id for item in items]
        n_real = len(chosen) + missing
        for event_id in chosen:
            taken.add(frame.loc[event_id])
    drawn = Counter(frame.loc[chosen, "stratum"]) if chosen else Counter()
    items += plant(b, pool, taken, skip, planted, tag)
    for item in items:
        item.audit_id = "Q" + draw_key(f"{tag}/id", item.event_id)[:8]
    if len({item.audit_id for item in items}) != len(items):
        raise RuntimeError("audit ids collide; change the tag")
    population = frame["stratum"].value_counts().to_dict()
    strata = [
        {
            "stratum": s,
            "events": population[s],
            "excluded": population[s] - sizes.get(s, 0),
            "pool": sizes.get(s, 0),
            "quota": quota.get(s, 0),
            "drawn": drawn.get(s, 0),
        }
        for s in sorted(population)
    ]
    counts = {
        "events": len(frame),
        "excluded_events": len(frame) - len(pool),
        "pool": len(pool),
        "real_wanted": n_real,
        "real_drawn": len(chosen),
        "planted_wanted": len(AUDITORS) * planted,
        "planted_drawn": len(items) - len(chosen),
    }
    if listed is not None:
        counts["listed"] = len(listed)
        counts["listed_not_in_build"] = missing
    return Drawn(items, strata, counts, frozenset(skip))  # every excluded thread, by default


def file_names(half: str) -> dict[str, str]:
    return {
        **{a: f"outcome_{a}_{half}.csv" for a in AUDITORS},
        **{f"{a}_items": f"outcome_{a}_{half}_items.txt" for a in AUDITORS},
        "traces": f"outcome_{half}_traces.csv",
        "sample": f"outcome_{half}_sample.csv",
        "strata": f"outcome_{half}_strata.csv",
        "manifest": f"outcome_{half}_manifest.json",
        "key": f"outcome_{half}_key.csv",
        "adjudication": f"outcome_{half}_adjudication.csv",
        "score": f"outcome_{half}_score.json",
    }


def builder_hashes() -> dict[str, str]:
    """Hashes of ``corpus.py`` and of its docstring for the sheet header.

    Stops when the file on disk is no longer the code that was loaded: the header must name the
    builder that derived the brackets shown.
    """
    source = Path(C.__file__).read_bytes()
    doc = ast.get_docstring(ast.parse(source), clean=False) or ""
    if doc != (C.__doc__ or ""):
        raise SystemExit("corpus.py changed on disk after it was loaded: run again")
    return {
        "corpus_py": f"sha256 {hashlib.sha256(source).hexdigest()[:16]}",
        "corpus_docstring": f"sha256 {hashlib.sha256(doc.encode()).hexdigest()[:16]}",
    }


def guide_version(text: str) -> str:
    match = re.search(r"\*\*Version (v[^,.*]+)", text)
    return match.group(1).strip() if match else "unknown"


def write_sheets(
    b: Built, drawn: Drawn, out: Sink, keys: Sink, meta: dict[str, Any], key_prefix: str = ""
) -> None:
    """Write the two sheets (as CSV and as text blocks), the traces, the sample list, the strata
    table and the key."""
    names = file_names(b.half)
    sheet_rows: dict[str, dict[str, Any]] = {}
    trace_rows: list[dict[str, Any]] = []
    traces: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(drawn.items, key=lambda it: it.audit_id):
        rows, strip = trace(item, b, drawn.withheld)
        if b.half == "train" and any(
            r["capture_date"] >= C.iso(C.TEST_START) and r["window"] != "c0" for r in rows
        ):
            raise RuntimeError(f"{item.audit_id}: a train trace reaches the test period")
        trace_rows += rows
        traces[item.audit_id] = rows
        sheet_rows[item.audit_id] = sheet_row(item, b, strip)
    for auditor in AUDITORS:
        mine = [it.audit_id for it in drawn.items if it.assigned in (auditor, SHARED)]
        order = shuffled(mine, f"{meta['draw']}/order/{auditor}")
        head = {"task": "B outcome audit (AUDIT_GUIDE.md section 6)", "auditor": auditor, **meta}
        head = {**head, "items": len(order), "session_start": "", "session_end": ""}
        out.write(names[auditor], csv_text(SHEET_COLUMNS, (sheet_rows[i] for i in order), head))
        blocks = [
            item_block(sheet_rows[i], traces[i], n, len(order)) for n, i in enumerate(order, 1)
        ]
        intro = "".join(f"# {key}: {value}\n" for key, value in head.items() if value != "")
        out.write(names[f"{auditor}_items"], intro + "\n" + "\n".join(blocks))
    out.write(names["traces"], csv_text(TRACE_COLUMNS, trace_rows, {}))
    listed = sorted(drawn.items, key=lambda it: it.event_id)
    strata = {s["stratum"]: s for s in drawn.strata}
    all_keys = [key_row(it, b, strata) for it in listed]
    out.write(names["sample"], csv_text(SAMPLE_COLUMNS, all_keys, {}, sheet=False))
    out.write(names["strata"], csv_text(STRATA_COLUMNS, drawn.strata, {}, sheet=False))
    by_id = sorted(all_keys, key=lambda k: k["audit_id"])
    keys.write(key_prefix + names["key"], csv_text(KEY_COLUMNS, by_id, {}, sheet=False))


def check_sealed(directory: Path) -> None:
    """Stop unless ``directory`` lies under a folder named ``sealed``: test-period outcomes are
    written and scored nowhere else."""
    if SEALED not in directory.resolve().parts:
        raise SystemExit(
            f"{directory}: the test half is written and scored only under a folder named {SEALED}"
        )


def output_dirs(
    half: str, draft: bool, out: Path | None, keys: Path | None
) -> tuple[Path, Path, str]:
    """Where the sheets and the key go, and the prefix of the key's name.

    Train half: ``out`` and ``keys`` as given, else ``TRAIN_OUT`` and ``TRAIN_KEYS``, and for a
    draft their ``draft`` folders, so that a draft never lies beside a final set. Test half:
    ``out`` is required and must be under a folder named ``sealed``; the key goes to ``keys/``
    inside it, whatever ``keys`` says.
    """
    if half == "test":
        if out is None:
            raise SystemExit("--half test needs --out (the sealed audit directory)")
        check_sealed(out)
        return out, out, "keys/"
    sub = DRAFT_DIR if draft else ""
    return out or TRAIN_OUT / sub, keys or TRAIN_KEYS / sub, ""


def read_lists(
    paths: Iterable[Path],
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[dict[str, Any]]]:
    """The ids of the labelling samples under ``paths``, the ids of this module's own earlier
    samples (files named ``outcome_*``, given by name for a re-audit round), and the lists that
    held any id (name, sha256, number of ids, which of the two kinds).

    A path is named without its directory when it is absolute, so that no home directory reaches
    the manifest.
    """
    ids: dict[str, set[str]] = {c: set() for c in ID_COLUMNS}
    earlier: dict[str, set[str]] = {c: set() for c in ID_COLUMNS}
    used = []
    for path in exclusion_files(paths):
        found = read_ids(path)
        if any(found.values()):
            own = path.name.startswith("outcome_")
            shown = path.name if path.is_absolute() else path.as_posix()
            n_ids = sum(len(v) for v in found.values())
            entry = {"file": shown, "sha256": sha256_file(path), "ids": n_ids}
            used.append({**entry, "kind": "earlier outcome audit" if own else "labelling"})
            for c in ID_COLUMNS:
                (earlier if own else ids)[c] |= found[c]
    return ids, earlier, used


def read_manifest(path: Path) -> dict[str, Any]:
    """The manifest of a written set; empty when there is none."""
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def run_sheets(args: argparse.Namespace) -> int:
    half = args.half
    names = file_names(half)
    out_dir, keys_dir, key_prefix = output_dirs(half, args.draft, args.out, args.keys)
    out = Sink(out_dir, hold=True)
    keys = out if half == "test" else Sink(keys_dir, hold=True)
    if not args.guide.is_file():
        raise SystemExit(f"guide not found: {args.guide}")
    guide = args.guide.read_text(encoding="utf-8")
    examples = guide_examples(guide)
    ids, earlier, used = read_lists(args.exclude)
    listed = listed_rows(args.items) if args.items else None
    if args.changed and listed is None:
        raise SystemExit("--changed goes with --items")
    if not examples and not args.draft:
        raise SystemExit(f"{args.guide}: no excluded statement found in its Appendix A")
    if not any(u["kind"] == "labelling" for u in used) and not args.draft:
        raise SystemExit(
            "no sample list with event_id, statement_group_id or thread_id under --exclude: "
            "the audit must skip the pilot, check and literal-task samples "
            "(pass --draft to draw a draft without them)"
        )
    builder = builder_hashes()
    b = load(args.captures, half)
    unknown = unknown_ids(b.table, ids)
    if unknown and not args.draft:
        raise SystemExit(
            f"{unknown} ids in the sample lists name no event of this build: the lists come "
            "from other captures or another corpus.py, so the exclusion would be incomplete"
        )
    labelled_threads, unmatched = excluded_threads(b.table, ids, examples)
    if unmatched and not args.draft:
        rows = "; ".join(", ".join(example) for example in unmatched)
        raise SystemExit(
            f"{len(unmatched)} rows of the guide's Appendix A match no event, so their "
            f"statements would not be excluded: {rows}"
        )
    skip = labelled_threads | audited_threads(b.table, earlier)
    own, shared, planted = (
        default if given is None else given
        for default, given in zip(SIZES[half], (args.own, args.shared, args.planted), strict=True)
    )
    if listed is not None:  # a list is audited as it is, with planted items only on request
        own, shared, planted = 0, 0, args.planted or 0
    tag = "/".join(
        [
            half,
            *(["draft"] if args.draft else []),
            *([f"round{args.round}"] if args.round > 1 else []),
            *(["items"] if listed is not None else []),
        ]
    )
    drawn = draw_items(b, skip, own, shared, planted, tag, listed, args.changed)
    drawn.withheld = frozenset(labelled_threads)
    if not drawn.items:
        print(f"outcome audit, {half} half: no item to audit; nothing was written")
        return 0
    horizon = b.ctx.train_last if half == "train" else len(b.ctx.dates) - 1
    if builder_hashes() != builder:
        raise SystemExit("corpus.py changed on disk during the run: run again")
    meta = {
        "half": half,
        "status": "draft" if args.draft else "final",
        **({"note": DRAFT_NOTE} if args.draft else {}),
        "draw": tag,
        "seed": SEED,
        "guide": f"{guide_version(guide)} sha256 {hashlib.sha256(guide.encode()).hexdigest()[:16]}",
        **builder,
        "followed_to": cap_date(b.ctx, horizon) if horizon >= 0 else "",
    }
    write_sheets(b, drawn, out, keys, meta, key_prefix)
    captures = [(p.name, sha256_file(p)) for p in C.capture_files(args.captures)]
    manifest = {
        **meta,
        "captures": len(captures),
        "captures_sha256": hashlib.sha256(json.dumps(captures).encode()).hexdigest(),
        "sizes": {"own": own, "shared": shared, "planted_per_auditor": planted},
        **(
            {"items_list": {"sha256": sha256_file(args.items), "changed_only": args.changed}}
            if listed is not None
            else {}
        ),
        "exclusion_lists": used,
        "sample_list_ids_unknown": unknown,
        "earlier_sample_ids_unknown": unknown_ids(
            b.table, {**earlier, "statement_group_id": set()}
        ),
        "guide_examples": len(examples),
        "guide_examples_unmatched": len(unmatched),
        "excluded_threads": len(skip),
        "counts": drawn.counts,
        "files": {**out.written, **keys.written},
    }
    before = read_manifest(out_dir / names["manifest"])
    changed = before.get("status") == "final" and before.get("files") != manifest["files"]
    if changed and not args.replace:
        raise SystemExit(
            f"{out_dir} holds a final set that this run would change; sheets already handed "
            "out could then no longer be scored. Nothing was written. Pass --replace to "
            "overwrite the set, or --out and --keys to write elsewhere"
        )
    out.write(names["manifest"], json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    out.commit()
    keys.commit()
    report_sheets(half, drawn, manifest, out, keys)
    return 0


def report_sheets(half: str, drawn: Drawn, manifest: dict[str, Any], out: Sink, keys: Sink) -> None:
    """Counts. The stratum table is printed for the train half only: for the test half it would
    be a cross-tabulation of sealed outcomes, so it stays in the sealed directory."""
    c = drawn.counts
    print(f"outcome audit, {half} half ({manifest['status']}; draw {manifest['draw']})")
    print(
        f"  shortage events {c['events']}; excluded with their threads {c['excluded_events']} "
        f"({manifest['excluded_threads']} threads over all periods); pool {c['pool']}"
    )
    print(f"  sample lists read: {len(manifest['exclusion_lists'])}")
    for used in manifest["exclusion_lists"]:
        kind = "" if used.get("kind", "labelling") == "labelling" else f" ({used['kind']})"
        print(f"    {used['file']}: {used['ids']} ids, sha256 {used['sha256'][:16]}{kind}")
    if manifest.get("sample_list_ids_unknown"):
        print(f"  WARNING: {manifest['sample_list_ids_unknown']} listed ids name no event")
    if manifest.get("earlier_sample_ids_unknown"):
        print(
            f"  WARNING: {manifest['earlier_sample_ids_unknown']} ids of an earlier outcome-audit "
            "sample name no event of this build, so those items are not kept out of this draw"
        )
    print(
        f"  guide examples read: {manifest.get('guide_examples', 0)}; "
        f"matching no event: {manifest['guide_examples_unmatched']}"
    )
    if manifest["guide_examples_unmatched"]:
        print("  WARNING: a guide example that matches no event is not excluded: check Appendix A")
    if half == "train":
        print(f"  {STRATA_COLUMNS[0]:<34}" + "".join(f"{name:>10}" for name in STRATA_COLUMNS[1:]))
        for s in drawn.strata:
            mark = "  <- shortfall" if s["drawn"] < s["quota"] else ""
            cells = "".join(f"{s[k]:>10}" for k in STRATA_COLUMNS[1:])
            print(f"  {s['stratum']:<34}{cells}{mark}")
    print(
        f"  real items {c['real_drawn']} of {c['real_wanted']}; "
        f"planted {c['planted_drawn']} of {c['planted_wanted']}"
    )
    if "listed" in c:
        print(
            f"  listed for re-audit {c['listed']}; "
            f"not events of this half in this build: {c['listed_not_in_build']}"
        )
    short = "listed" not in c and c["real_drawn"] < c["real_wanted"]
    if short or c["planted_drawn"] < c["planted_wanted"]:
        print("  SHORTFALL: the pool could not fill the sample")
    for sink in [out] if keys is out else [out, keys]:
        for name, digest in sorted(sink.written.items()):
            print(f"  wrote {sink.root / name} sha256 {digest[:16]}")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_row(row: dict[str, str]) -> list[str]:
    """Problems in the entered cells of one sheet row."""
    problems = []
    codes = {d: split_list(row.get(f"codes_{d}", "")) for d in DEFS}
    for d in DEFS:
        verdict = row.get(f"verdict_{d}", "")
        if verdict not in VERDICTS:
            problems.append(f"verdict_{d} must be one of {', '.join(VERDICTS)}")
            continue
        bad = [c for c in codes[d] if c not in CODES]
        if bad:
            problems.append(f"codes_{d}: unknown {' '.join(bad)}")
        true = {part: row.get(f"true_{d}_{part}", "") for part in ("type", "lower", "upper")}
        if verdict == "error":
            if not codes[d]:
                problems.append(f"verdict_{d} is error but codes_{d} is empty")
            if not any(true.values()) and not row.get("note", ""):
                problems.append(f"verdict_{d} is error: give true_{d}_type, bounds, or a note")
        else:
            if codes[d]:
                problems.append(f"codes_{d} given but verdict_{d} is {verdict}")
            if any(true.values()):
                problems.append(f"true_{d}_* given but verdict_{d} is {verdict}")
        if true["type"] and true["type"] not in TYPES:
            problems.append(f"true_{d}_type must be one of {', '.join(TYPES)}")
        for part in ("lower", "upper"):
            if true[part] and not is_iso(true[part]):
                problems.append(f"true_{d}_{part} is not a YYYY-MM-DD date")
        if is_iso(true["lower"]) and is_iso(true["upper"]) and true["lower"] > true["upper"]:
            problems.append(f"true_{d}_lower is after true_{d}_upper")
        if verdict == "cannot_tell" and not row.get("note", ""):
            problems.append(f"verdict_{d} is cannot_tell: say why in note")
    flags = split_list(row.get("note_codes", ""))
    bad = [f for f in flags if f not in NOTE_CODES]
    if bad:
        problems.append(f"note_codes: unknown {' '.join(bad)}")
    first = row.get("dou_first_recovered", "")
    if ("N1" in flags) != bool(first):
        problems.append("dou_first_recovered is given exactly when note_codes has N1")
    if first and not is_iso(first):
        problems.append("dou_first_recovered is not a YYYY-MM-DD date")
    if any("O9" in c for c in codes.values()) and not row.get("note", ""):
        problems.append("O9 needs a note")
    return problems


def validate(
    rows: list[dict[str, str]], blank: list[dict[str, str]] | None = None
) -> tuple[list[str], list[str]]:
    """Problems (which block scoring) and warnings for a returned sheet.

    With the blank sheet, the item ids must be the same set; a shown cell that differs from the
    blank is a warning, since scoring takes the shown values from the key. A sheet without rows
    is in order only when its blank has none (a re-audit list that names one auditor only).
    """
    problems: list[str] = []
    warnings: list[str] = []
    if not rows:
        return ([] if blank == [] else ["the sheet has no rows"]), warnings
    missing = [c for c in SHEET_COLUMNS if c not in rows[0]]
    if missing:
        return [f"missing columns: {', '.join(missing)}"], warnings
    ids = [r.get("audit_id", "") for r in rows]
    problems += [f"{i}: listed more than once" for i, n in Counter(ids).items() if n > 1]
    if blank is not None:
        wanted = {r["audit_id"]: r for r in blank}
        problems += [f"{i}: not an item of this sheet" for i in sorted(set(ids) - set(wanted))]
        problems += [f"{i}: row missing" for i in sorted(set(wanted) - set(ids))]
        for row in rows:
            ref = wanted.get(row.get("audit_id", ""), {})
            changed = [c for c in SHOWN if c in ref and row.get(c, "") != ref[c]]
            if changed:
                warnings.append(f"{row['audit_id']}: shown cells changed: {', '.join(changed)}")
    for row in rows:
        problems += [f"{row.get('audit_id', '?')}: {p}" for p in validate_row(row)]
    return problems, warnings


def run_validate(args: argparse.Namespace) -> int:
    meta, rows = read_sheet(args.sheet)
    blank = read_sheet(args.blank)[1] if args.blank else None
    problems, warnings = validate(rows, blank)
    if session_minutes(meta) is None:
        warnings.append("session_start and session_end give no usable times (HH:MM; HH:MM)")
    for line in warnings:
        print(f"warning: {line}")
    for line in problems:
        print(f"problem: {line}")
    print(f"{args.sheet}: {len(rows)} rows, {len(problems)} problems, {len(warnings)} warnings")
    return 1 if problems else 0


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def auditors_of(key: dict[str, str]) -> tuple[str, ...]:
    return AUDITORS if key["assigned_to"] == SHARED else (key["assigned_to"],)


def adjudication_rows(
    key: list[dict[str, str]], sheets: dict[str, dict[str, dict[str, str]]]
) -> list[dict[str, str]]:
    """One row per real item and definition that an auditor did not mark ``ok``."""
    rows = []
    for k in sorted(key, key=lambda k: k["audit_id"]):
        if k["planted"]:
            continue
        for d in DEFS:
            marks = {a: sheets[a][k["audit_id"]] for a in auditors_of(k)}
            if all(m[f"verdict_{d}"] == "ok" for m in marks.values()):
                continue
            row = {"audit_id": k["audit_id"], "definition": d}
            row.update(
                {f"shown_{p}": k[f"shown_{d}_{p}"] for p in ("type", "lower", "upper", "censor")}
            )
            for a, m in marks.items():
                true = "|".join(m[f"true_{d}_{p}"] for p in ("type", "lower", "upper"))
                row.update(
                    {
                        f"{a}_verdict": m[f"verdict_{d}"],
                        f"{a}_codes": ";".join(split_list(m[f"codes_{d}"])),
                        f"{a}_true": true if true != "||" else "",
                        f"{a}_note_codes": ";".join(split_list(m["note_codes"])),
                        f"{a}_note": m["note"],
                    }
                )
            rows.append(row)
    return rows


def check_adjudication(
    wanted: list[dict[str, str]], filled: list[dict[str, str]]
) -> tuple[dict[tuple[str, str], dict[str, str]], list[str]]:
    """Decisions by (item, definition), and what is missing or malformed in the filled sheet."""
    by_key = {(r.get("audit_id", ""), r.get("definition", "")): r for r in filled}
    problems = []
    for w in wanted:
        k = (w["audit_id"], w["definition"])
        row = by_key.get(k)
        if row is None or not row.get("decision"):
            problems.append(f"{k[0]} {k[1]}: no decision")
        elif row["decision"] not in DECISIONS:
            problems.append(f"{k[0]} {k[1]}: decision must be one of {', '.join(DECISIONS)}")
        elif row["decision"] == "confirmed":
            codes = split_list(row.get("confirmed_codes", ""))
            if not codes or any(c not in CODES for c in codes):
                problems.append(f"{k[0]} {k[1]}: confirmed_codes must list codes O1 to O9")
            if not row.get("cause"):
                problems.append(f"{k[0]} {k[1]}: a confirmed error needs a cause")
    extra = set(by_key) - {(w["audit_id"], w["definition"]) for w in wanted}
    problems += [f"{a} {d}: not sent to adjudication" for a, d in sorted(extra)]
    return by_key, problems


def score_planted(
    key: list[dict[str, str]], sheets: dict[str, dict[str, dict[str, str]]]
) -> dict[str, dict[str, Any]]:
    """Planted items each auditor caught: an ``error`` verdict under a planted definition."""
    out = {}
    for a in AUDITORS:
        mine = [k for k in key if k["planted"] and k["assigned_to"] == a]
        caught, coded = 0, 0
        for k in mine:
            mark = sheets[a][k["audit_id"]]
            hit = [
                d for d in split_list(k["planted_definitions"]) if mark[f"verdict_{d}"] == "error"
            ]
            caught += bool(hit)
            coded += any(k["expected_code"] in split_list(mark[f"codes_{d}"]) for d in hit)
        missed = len(mine) - caught
        out[a] = {
            "planted": len(mine),
            "caught": caught,
            "caught_with_expected_code": coded,
            "recheck_own_items": missed >= PLANTED_MISS_LIMIT,
        }
    return out


def score_shared(
    key: list[dict[str, str]], sheets: dict[str, dict[str, dict[str, str]]]
) -> dict[str, dict[str, Any]]:
    """Agreement of the two auditors on the items both audited, before adjudication."""
    out = {}
    both = [k["audit_id"] for k in key if not k["planted"] and k["assigned_to"] == SHARED]
    for d in DEFS:
        pairs = [tuple(sheets[a][i][f"verdict_{d}"] for a in AUDITORS) for i in both]
        clear = [p for p in pairs if "cannot_tell" not in p]
        out[d] = {
            "items": len(pairs),
            "same_verdict": sum(a == b for a, b in pairs),
            "with_cannot_tell": len(pairs) - len(clear),
            "kappa_ok_error": cohen_kappa(clear),
        }
    return out


def score(
    key: list[dict[str, str]],
    sheets: dict[str, dict[str, dict[str, str]]],
    decisions: dict[tuple[str, str], dict[str, str]] | None,
) -> dict[str, Any]:
    """Audit statistics. ``decisions`` is None until adjudication is complete; the confirmed
    errors and the pass rule are then left out."""
    real = [k for k in key if not k["planted"]]
    n = len(real)
    flagged: dict[str, Any] = {}
    for a in AUDITORS:
        mine = [sheets[a][k["audit_id"]] for k in real if a in auditors_of(k)]
        flagged[a] = {
            "real_items": len(mine),
            **{
                f"{verdict}_{d}": sum(m[f"verdict_{d}"] == verdict for m in mine)
                for d in DEFS
                for verdict in ("error", "cannot_tell")
            },
        }
    flags: Counter[str] = Counter()
    for k in real:
        seen = {
            f for a in auditors_of(k) for f in split_list(sheets[a][k["audit_id"]]["note_codes"])
        }
        flags.update(seen)
    result: dict[str, Any] = {
        "real_items": n,
        "allowed_errors": n * ALLOWED_ERROR_PERCENT // 100,
        "auditor_flagged": flagged,
        "note_codes": dict(sorted(flags.items())),
        "shared_items": score_shared(key, sheets),
        "planted": score_planted(key, sheets),
        "adjudicated": decisions is not None,
    }
    if decisions is None:
        return result
    pool = {k["stratum"]: int(k["stratum_pool"] or 0) for k in real}
    total = sum(pool.values())
    causes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for d in DEFS:
        state = {
            k["audit_id"]: decisions.get((k["audit_id"], d), {}).get("decision", "") for k in real
        }
        confirmed = [i for i, s in state.items() if s == "confirmed"]
        unresolved = sum(s == "unresolved" for s in state.values())
        codes: Counter[str] = Counter()
        for i in confirmed:
            row = decisions[(i, d)]
            codes.update(set(split_list(row.get("confirmed_codes", ""))))
            for code in set(split_list(row.get("confirmed_codes", ""))):
                causes[(code, C.norm_text(row.get("cause", "")))].add(i)
        by_stratum = Counter(k["stratum"] for k in real)
        wrong = Counter(k["stratum"] for k in real if k["audit_id"] in confirmed)
        weighted = (
            sum(pool[s] / total * (1 - wrong[s] / by_stratum[s]) for s in by_stratum)
            if total
            else None
        )
        result[d] = {
            "confirmed_errors": len(confirmed),
            "unresolved": unresolved,
            "agreement_rate": (n - len(confirmed)) / n if n else None,
            "agreement_wilson95": wilson(n - len(confirmed), n),
            "agreement_rate_reweighted": weighted,
            "codes": dict(sorted(codes.items())),
            "errors_by_stratum": dict(sorted(wrong.items())),
            "confirmed": [
                {
                    "audit_id": i,
                    "codes": sorted(set(split_list(decisions[(i, d)].get("confirmed_codes", "")))),
                    "cause": decisions[(i, d)].get("cause", ""),
                }
                for i in sorted(confirmed)
            ],
            "pass": n > 0 and len(confirmed) <= result["allowed_errors"],
            "pass_if_unresolved_count": len(confirmed) + unresolved <= result["allowed_errors"],
        }
    repeated = sorted(f"{code}: {cause}" for (code, cause), ids in causes.items() if len(ids) > 1)
    result["repeated_causes"] = repeated
    result["pass"] = all(result[d]["pass"] for d in DEFS)
    result["rule_fix_required"] = not result["pass"] or bool(repeated)
    return result


def set_problems(manifest: dict[str, Any], directory: Path, key_path: Path, half: str) -> list[str]:
    """What stops scoring before the key is read: the set has no manifest, or the key or a blank
    sheet in ``directory`` is missing or is not the file that the manifest lists."""
    names = file_names(half)
    if not manifest:
        return [f"{directory / names['manifest']} not found: the set cannot be checked"]
    files = manifest.get("files", {})
    listed = {("keys/" if half == "test" else "") + names["key"]: key_path}
    listed.update({names[a]: directory / names[a] for a in AUDITORS})
    problems = []
    for name, path in listed.items():
        if name not in files:
            problems.append(f"the manifest does not list {name}")
        elif not path.is_file():
            problems.append(f"{path} not found")
        elif sha256_file(path) != files[name]:
            problems.append(f"{path} is not the {name} that the manifest lists")
    return problems


def key_problems(
    key: list[dict[str, str]], sheets: dict[str, dict[str, dict[str, str]]]
) -> list[str]:
    """Items of the key that a sheet lacks, and items of a sheet that the key lacks."""
    problems = []
    for a in AUDITORS:
        wanted = {k["audit_id"] for k in key if a in auditors_of(k)}
        if wanted != set(sheets[a]):
            problems.append(f"the key and the sheet of {a} do not hold the same items")
    return problems


def timing(meta: dict[str, str], n_items: int) -> dict[str, Any] | None:
    """Minutes worked and minutes per item, from the session lines of a returned sheet."""
    minutes = session_minutes(meta)
    if minutes is None or not n_items:
        return None
    return {"minutes": minutes, "items": n_items, "minutes_per_item": round(minutes / n_items, 2)}


def run_score(args: argparse.Namespace) -> int:
    half = args.half
    names = file_names(half)
    if half == "test" and args.dir is None:
        raise SystemExit("--half test needs --dir (the sealed audit directory)")
    directory: Path = args.dir or TRAIN_OUT
    key_path = args.key or (directory / "keys" if half == "test" else TRAIN_KEYS) / names["key"]
    adjudication_path = args.adjudication or directory / labelled(names["adjudication"], args.label)
    if half == "test":
        check_sealed(directory)
        if not adjudication_path.resolve().is_relative_to(directory.resolve()):
            raise SystemExit("--half test: the adjudication sheet stays in the sealed directory")
    manifest = read_manifest(directory / names["manifest"])
    returned = {AUDITORS[0]: args.a1, AUDITORS[1]: args.a2}
    needed = [*returned.values(), *(directory / names[a] for a in AUDITORS)]
    missing = [str(path) for path in needed if not path.is_file()]
    if missing:
        raise SystemExit(f"not found: {', '.join(missing)}")
    sheets: dict[str, dict[str, dict[str, str]]] = {}
    minutes: dict[str, Any] = {}
    failed = False
    for auditor, path in returned.items():
        meta, rows = read_sheet(path)
        problems, warnings = validate(rows, read_sheet(directory / names[auditor])[1])
        for line in warnings:
            print(f"warning ({auditor}): {line}")
        for line in problems:
            print(f"problem ({auditor}): {line}")
        failed = failed or bool(problems)
        sheets[auditor] = {r["audit_id"]: r for r in rows}
        minutes[auditor] = timing(meta, len(rows))
    if failed:
        print("the sheets do not validate; nothing was scored and the key was not read")
        return 2
    problems = set_problems(manifest, directory, key_path, half)
    key = [] if problems else read_sheet(key_path)[1]
    problems = problems or key_problems(key, sheets)
    if problems:
        for line in problems:
            print(f"problem: {line}")
        print("the key, the blank sheets and the returned sheets are not one set; nothing scored")
        return 2
    wanted = adjudication_rows(key, sheets)
    decisions = None
    if not wanted:
        decisions = {}
    elif adjudication_path.is_file():
        decisions, problems = check_adjudication(wanted, read_sheet(adjudication_path)[1])
        for line in problems:
            print(f"adjudication: {line}")
        decisions = None if problems else decisions
    else:
        columns = (*ADJUDICATION_SHOWN, *ADJUDICATION_ENTERED)
        Sink(adjudication_path.parent).write(adjudication_path.name, csv_text(columns, wanted, {}))
        print(f"wrote {adjudication_path}: {len(wanted)} rows to adjudicate")
    result = score(key, sheets, decisions)
    result["half"] = half
    result["status"] = manifest.get("status", "unknown")
    result["minutes"] = minutes
    # sizes of the frame, the excluded part and the pool; the builder that was audited
    result["counts"] = manifest.get("counts", {})
    result["corpus_py"] = manifest.get("corpus_py", "")
    now = f"sha256 {sha256_file(Path(C.__file__))[:16]}"
    result["corpus_py_unchanged"] = result["corpus_py"] == now
    result["sha256"] = {
        **{a: sha256_file(p) for a, p in returned.items()},
        "key": sha256_file(key_path),
        **({"adjudication": sha256_file(adjudication_path)} if decisions else {}),
    }
    if half == "test":  # counts only until the registered evaluator has run
        for d in DEFS:
            for name in ("errors_by_stratum", "agreement_rate_reweighted"):
                result.get(d, {}).pop(name, None)
    score_name = labelled(names["score"], args.label)
    Sink(directory).write(score_name, json.dumps(result, indent=2, sort_keys=True) + "\n")
    report_score(result)
    print(f"wrote {directory / score_name}")
    if not result["adjudicated"]:
        return 3
    return 0 if result["pass"] else 1


def report_score(result: dict[str, Any]) -> None:
    n = result["real_items"]
    print(f"outcome audit, {result['half']} half ({result['status']}): {n} real items")
    wanted = result.get("counts", {}).get("real_wanted", n)
    if n < wanted:
        print(f"  NOTE: the sample holds {n} of the {wanted} real items the rule is stated for")
    if result.get("corpus_py_unchanged") is False:
        print(f"  NOTE: corpus.py is no longer the file audited ({result['corpus_py']})")
    for a, p in result["planted"].items():
        recheck = "; re-check own items" if p["recheck_own_items"] else ""
        print(f"  {a}: planted caught {p['caught']} of {p['planted']}{recheck}")
    for a, t in result["minutes"].items():
        took = "not given" if t is None else f"{t['minutes']} ({t['minutes_per_item']} per item)"
        print(f"  {a}: minutes worked {took}")
    for d, s in result["shared_items"].items():
        print(
            f"  shared items, definition {d}: same verdict on {s['same_verdict']} of {s['items']}"
        )
    if not result["adjudicated"]:
        print("  awaiting adjudication: fill the decision column and run score again")
        return
    for d in DEFS:
        r = result[d]
        verdict = "pass" if r["pass"] else "FAIL"
        print(
            f"  definition {d}: confirmed errors {r['confirmed_errors']} of {n} "
            f"(allowed {result['allowed_errors']}); unresolved {r['unresolved']}; "
            f"codes {r['codes'] or 'none'}: {verdict}"
        )
        if r["pass"] and not r["pass_if_unresolved_count"]:
            print(f"    definition {d} would fail if the unresolved items were errors")
    print(f"  note codes (items): {result['note_codes'] or 'none'}")
    if result["repeated_causes"]:
        print(f"  the same code and cause twice or more: {'; '.join(result['repeated_causes'])}")
    verdict = "PASS" if result["pass"] else "FAIL"
    print(f"  {verdict}; rule fix required: {result['rule_fix_required']}")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.audit_outcomes")
    sub = ap.add_subparsers(dest="command", required=True)
    sheets = sub.add_parser("sheets", help="draw the sample and write sheets, traces and key")
    sheets.add_argument("--half", choices=HALVES, required=True)
    sheets.add_argument("--captures", type=Path, default=Path("external_data/fda_wayback_csv"))
    sheets.add_argument("--out", type=Path, default=None)
    sheets.add_argument("--keys", type=Path, default=None)
    sheets.add_argument("--guide", type=Path, default=Path("analysis/coling/plan/AUDIT_GUIDE.md"))
    sheets.add_argument("--exclude", type=Path, nargs="*", default=[SAMPLE_LISTS])
    sheets.add_argument("--draft", action="store_true")
    sheets.add_argument("--replace", action="store_true")
    sheets.add_argument("--round", type=int, default=1)
    sheets.add_argument("--items", type=Path, default=None)
    sheets.add_argument("--changed", action="store_true")
    for name in ("own", "shared", "planted"):
        sheets.add_argument(f"--{name}", type=int, default=None)
    sheets.set_defaults(run=run_sheets)
    check = sub.add_parser("validate", help="check a returned sheet")
    check.add_argument("sheet", type=Path)
    check.add_argument("--blank", type=Path, default=None)
    check.set_defaults(run=run_validate)
    scorer = sub.add_parser("score", help="score two returned sheets")
    scorer.add_argument("--half", choices=HALVES, required=True)
    scorer.add_argument("--a1", type=Path, required=True)
    scorer.add_argument("--a2", type=Path, required=True)
    scorer.add_argument("--dir", type=Path, default=None)
    scorer.add_argument("--key", type=Path, default=None)
    scorer.add_argument("--adjudication", type=Path, default=None)
    scorer.add_argument("--label", default="")
    scorer.set_defaults(run=run_score)
    return ap


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(None if argv is None else list(argv))
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
