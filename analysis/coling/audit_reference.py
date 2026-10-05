"""Reference-reading check (AUDIT_GUIDE.md section 12.2, task E): sheets, validator, scorer.

E3 takes the end of each statement's stated period (``stated_end``), and the list of eligible
statements, from the frozen rule reading. Two annotators (A1, A2) check that reading against the
text on 100 registered statements, and the adjudicator (ADJ) settles what they report. This
module writes one blank sheet per annotator, checks a filled sheet, and scores the two filled
sheets. It draws nothing and changes no item, and it reads no outcome: its inputs are first-sight
fields, the registered lists and the frozen rule reader.

The registered sample (:func:`marked_rows`)
-------------------------------------------
The sample is the statements marked in the column ``reference_check`` of the eligible list
(``eligible_e3.csv``), which ``dataset.py`` drew with seed 20261001. ``sheets`` and ``score``
first read the record of the corpus freeze (``freeze_record.json``) and stop, writing nothing,
when

* the record is not that of a complete freeze run;
* the eligible list or the counts file (``dataset_counts.json``) is not the file whose sha256
  the record names;
* the marked statements are not the subset the counts file records (``ids_sha256``);
* a marked statement is not dated in the test period (2023 to 2025).

Of the counts file only the record of the subset and that of its item file are kept
(:func:`subset_counts`). The ``sheets`` command also stops when the item file of the subset
(``items/subset_reference_check.jsonl``), the events table, a first-draw list (pilot, check,
reserve, literal) or one of the rule reader's files (``rules.py``, ``forms.py``) is not the
registered one.

Blinding (:func:`labelled`)
---------------------------
No statement of the pilot, the check set, its reserve or the literal sample may be on a sheet,
and none that has the generic, company and normalised text of one at another date
(``dataset.labelled_statements``, the rule of the draw). When the counts file calls the subset
final and such a statement is marked, the files contradict each other and the command stops.
When the subset is not final, the command stops too, until ``--leave-off`` is given: the
statements are then left off the sheets, the check has fewer items, and the number left off is
written to the manifest and to the result.

What a sheet shows (:func:`rule_readings`, :func:`build_files`)
---------------------------------------------------------------
* The entry block of the reading harness, one field per column: the registered item of the
  statement, through ``audit_sample.shown_cells`` (the columns of a task A sheet). The items
  text file holds the same entries as the harness renders them (``read.ENTRY_BLOCK``).
* The rule reading: ``rule_statement_type``, ``rule_start``, ``rule_end`` and ``rule_stale``,
  from ``forms.statement_forms`` on the statement's events, which is the call the dataset
  builder makes. ``rule_end`` must be the registered ``stated_end`` and the form the registered
  form, the reading must not be stale (the eligible list holds no stale statement), and the
  text shown must read the same on its own; otherwise the command stops.
* ``item_id`` is ``audit_sample.item_id`` of the statement: it shows neither form nor sample.
* No outcome, no Status, no capture date and no reader output other than the rule reading.

Assignment (:func:`assignment`). The statements are put in the seeded order of the draw
``reference/assign``. A tenth, rounded half up, is checked by both annotators; the others are
split in two halves, the first for A1 and the second for A2: 45, 45 and 10 of 100. Each
annotator's sheet is in a seeded order of its own (``reference/order/<annotator>``). No key
file is written: the item ids and the assignment follow from the registered list and the seed,
and the manifest holds their sha256.

Validator (:func:`validate_sheet`; the ``validate`` command)
------------------------------------------------------------
Errors, by row: a ``verdict`` that is not ``ok``, ``error`` or ``cannot_tell``; ``codes`` other
than K1 to K4 (a list separated by semicolons, commas or spaces), no code with ``error``, a code
without ``error``; a ``true_end`` that is no date (``YYYY-MM-DD``, or ``YYYY-MM`` for the last
day of that month) or that stands beside another verdict than ``error``; ``start_differs``
other than 1, 0 or blank (blank counts as 0); ``cannot_tell`` without a ``note``. For the
sheet: the sitting times (``# sitting_start:`` and ``# sitting_end:``, as in task A), and,
against the blank, an item that is missing, added or repeated and a shown cell that was
changed. Warnings do not fail a sheet: an ``error`` with no ``true_end`` and no K3, K3 beside a
``true_end``, K2 with the ``rule_end`` as ``true_end``, K4 with a ``true_end`` that is not
before the Date of update (and the reverse), ``start_differs`` beside a verdict that is not
``ok``, and no blank to compare with. The blank is ``reference_<annotator>.csv`` under
``--out``, so a sheet is filled in a copy kept elsewhere (``external_data/annotation/reference/``).

Scorer (:func:`agreement`, :func:`adjudication_rows`, :func:`result`; the ``score`` command)
--------------------------------------------------------------------------------------------
1. Both sheets are checked against the blanks the manifest records, copied byte for byte to
   ``submitted/`` with their sha256, and the statistics before adjudication are saved
   (``reference_agreement.json``): each annotator's verdicts and codes, the agreement on the
   shared items (raw, and Cohen's kappa on ``ok`` against ``error`` when both occur), the
   minutes and the seconds per item.
2. ``reference_adjudication.csv`` gets one row for every item that an annotator marked
   ``error`` or ``cannot_tell``, with the entry, the rule reading and the entries of each
   annotator who checked it. ADJ fills, in a copy kept elsewhere, ``decision`` (``confirmed``:
   the rule reading is wrong; ``rejected``: it stands; ``unresolved``: the text does not
   decide), ``confirmed_codes`` (K1 to K4, with ``confirmed`` only), ``confirmed_true_end`` and
   ``adj_note``. The command then stops with exit status 3. When no item was reported there
   is nothing to adjudicate, and the result is written at once; an adjudication sheet that
   was written for other sheets is then removed. A result on disk that was scored on other
   sheets (one of them was replaced since) is removed with its confirmed list, so that
   nothing reads a list that holds for no submitted pair.
3. Run again with ``--adjudication``, it first checks ADJ's sheet against the one it would
   write now: the same items, and every shown cell and annotator's entry as the scorer gave
   it, so that decisions taken on one pair of sheets are not scored on another. ADJ's sheet
   is copied to ``submitted/`` like the annotators'. The command then writes
   ``reference_result.json``: the share of the statements without a confirmed error and the
   share whose rule reading is confirmed (every annotator who checked it said ``ok``, or ADJ
   rejected what was reported; an unresolved item is in the first share and not in the
   second), each with a Wilson 95% interval; the confirmed errors by code, by form class and
   by statement year; the number with ``start_differs``; and the ids of the statements whose
   rule reading is confirmed, which are also written to ``reference_confirmed.csv`` for E7.
   No file of this module has an outcome field.

Exit status of ``score``: 0 the result is written, 2 a sheet or the adjudication sheet does not
validate or the files are not one set, 3 the adjudication is awaited. ``validate`` ends with 0,
or with 1 when the sheet has an error. A command that stops with a message (a file that is not
the registered one, a path in the sealed folder, blank sheets that were filled in place) has
written nothing and ends with status 1.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.audit_reference sheets [--check] [--leave-off]
        [--root analysis/coling/out] [--out analysis/coling/out/audit_reference]
        [--guide analysis/coling/plan/AUDIT_GUIDE.md]
    PYTHONPATH=. python -m analysis.coling.audit_reference validate SHEET [--blank BLANK]
    PYTHONPATH=. python -m analysis.coling.audit_reference score --a1 SHEET --a2 SHEET
        [--adjudication FILLED] [--replace]

``sheets`` writes ``reference_<A1|A2>.csv``, ``reference_<A1|A2>_items.txt`` and
``reference_manifest.json`` under ``--out``. Run twice on the same inputs it writes the same
bytes; ``--check`` writes nothing and exits 1 when a file on disk is not the one it would write.
A sheet under ``--out`` that holds a verdict or a sitting time was filled in place and is never
written over. ``score --replace`` takes a sheet in place of another one of the same annotator
that was submitted before, or another sheet of ADJ; the manifest keeps the hash of the earlier
one.

A sheet may be filled as a workbook (``sheet_xlsx.py``, which runs outside the study's
environment and must name ``verdict`` among the first columns an annotator fills)::

    uv run --no-project --with openpyxl python analysis/coling/sheet_xlsx.py to-xlsx \\
        analysis/coling/out/audit_reference/reference_A1.csv reference_A1.xlsx
    uv run --no-project --with openpyxl python analysis/coling/sheet_xlsx.py to-csv \\
        reference_A1_filled.xlsx --blank analysis/coling/out/audit_reference/reference_A1.csv \\
        --out external_data/annotation/reference/reference_A1.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import dataset as D
from analysis.coling import forms as F

SEED = S.SEED
ROOT = Path("analysis/coling/out")
OUT_NAME = "audit_reference"
GUIDE = S.GUIDE
FREEZE = "freeze_record.json"
COUNTS = "dataset_counts.json"
ELIGIBLE = "eligible_e3.csv"
EVENTS = "events.csv.gz"
ITEMS = "items/subset_reference_check.jsonl"
SAMPLES = "audit/samples"
SUBSET = "reference_check"
FIRST_DRAW = S.FIRST_SAMPLES
ANNOTATORS = S.ANNOTATORS
SHARED = "both"
SHARED_PERCENT = 10  # of the statements on the sheets: 10 of 100, beside 45 for each annotator
SECONDS_PER_ITEM = (30, 20, 45)  # the guide's planning rate, then its low and its high
SHEET = "reference"
MANIFEST = "reference_manifest.json"
AGREEMENT = "reference_agreement.json"
ADJUDICATION = "reference_adjudication.csv"
RESULT = "reference_result.json"
CONFIRMED = "reference_confirmed.csv"
SUBMITTED = "submitted"
TASK = "E reference readings (AUDIT_GUIDE.md section 12.2)"
HAND_OUT = (
    "hand the sheets out only after both task A sheets are submitted; ADJ opens none before "
    "the task A adjudication is finished (AUDIT_GUIDE.md sections 1 and 12.2)"
)

ELIGIBLE_FIELDS = ("statement_group_id", "event_id", "event_date", "form", "stated_end", SUBSET)
EVENT_FIELDS = (*F.EVENT_FIELDS, "generic_name", "company_name")
ITEM_KEYS = ("item_id", *S.ITEM_FIELDS, "stated_end", "display_event_id")
RULE = ("rule_statement_type", "rule_start", "rule_end", "rule_stale")
SHOWN = (*S.SHOWN, *RULE)
ENTERED = ("verdict", "codes", "true_end", "start_differs", "note")
SHEET_COLUMNS = (*SHOWN, *ENTERED)
VERDICTS = ("ok", "error", "cannot_tell")
CODES = {
    "K1": "wrong target: the period read belongs to another statement of the entry",
    "K2": "right target, wrong last day",
    "K3": "the target gives no date or period; the reading should abstain",
    "K4": (
        "the period ends before the Date of update, so the statement is stale and should not "
        "be eligible"
    ),
}
DECISIONS = ("confirmed", "rejected", "unresolved")
SCHEME = {
    "verdict": " | ".join(VERDICTS) + " (cannot_tell: say why in note)",
    "codes": "; ".join(CODES) + " (with error only, and at least one)",
    "true_end": (
        "YYYY-MM-DD, or YYYY-MM for the last day of that month (with error only; blank when "
        "the target gives no date)"
    ),
    "start_differs": "1 or 0 (1: the last day is right but the first day is not; blank is 0)",
}
ADJUDICATION_SHOWN = (*SHOWN, *(f"{a}_{c}" for a in ANNOTATORS for c in ENTERED))
ADJUDICATION_ENTERED = ("decision", "confirmed_codes", "confirmed_true_end", "adj_note")
CONFIRMED_COLUMNS = ("statement_group_id",)


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dig(record: Any, *keys: str) -> Any:
    """The value under a path of keys; None when a key is missing."""
    for key in keys:
        record = record.get(key) if isinstance(record, Mapping) else None
    return record


def json_text(record: Mapping[str, Any]) -> str:
    return json.dumps(record, indent=1, sort_keys=True) + "\n"


def not_sealed(path: Path) -> Path:
    """Refuse a path inside a folder named ``sealed``: this module never reads or writes one."""
    if "sealed" in path.parts or "sealed" in path.resolve().parts:
        raise SystemExit(f"{path}: the reference-reading check never touches the sealed folder")
    return path


def read_columns(path: Path, columns: Sequence[str]) -> pd.DataFrame:
    """The named columns of a CSV table (gzipped or not), every cell as text. No other column
    enters the frame, and a column that holds outcome information is refused."""
    refused = sorted(set(columns) & set(D.OUTCOME_COLUMNS))
    if refused:
        raise ValueError(f"outcome columns are never read: {', '.join(refused)}")
    try:
        return pd.read_csv(path, usecols=list(columns), dtype=str, keep_default_na=False)
    except ValueError as problem:
        raise SystemExit(f"{path}: {problem}") from None


def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    """Wilson 95% interval for k successes in n."""
    if n == 0:
        return None
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denominator = 1 + z * z / n
    low, high = (centre - half) / denominator, (centre + half) / denominator
    return [round(max(0.0, low), 4), round(min(1.0, high), 4)]


def cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters; None when it is undefined (no pairs, or one category)."""
    n = len(pairs)
    if n == 0:
        return None
    agree = sum(a == b for a, b in pairs) / n
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum(first[c] * second[c] for c in first) / (n * n)
    return None if chance >= 1 else round((agree - chance) / (1 - chance), 4)


def share(k: int, n: int) -> dict[str, Any]:
    """A count of ``n`` with its share and Wilson 95% interval."""
    return {"n": k, "share": round(k / n, 4) if n else None, "wilson95": wilson(k, n)}


# --------------------------------------------------------------------------------------------
# The registered files
# --------------------------------------------------------------------------------------------


def frozen_record(root: Path) -> dict[str, Any]:
    """The record of the corpus freeze. Anything but a complete freeze run registers nothing."""
    path = not_sealed(root) / FREEZE
    if not path.is_file():
        raise SystemExit(f"{path} not found: the sample is checked against the freeze record")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (dig(record, "mode"), dig(record, "status")) != ("freeze", "complete"):
        raise SystemExit(f"{path} is not the record of a complete freeze run; nothing was written")
    return record


def output_hash(record: Mapping[str, Any], name: str) -> str | None:
    """The sha256 the freeze record gives, among its outputs, for the file called ``name``."""
    found = [v for k, v in (dig(record, "outputs") or {}).items() if Path(k).name == name]
    return found[0] if len(found) == 1 else None


def require_registered(path: Path, registered: Any, what: str) -> str:
    """The sha256 of the file at ``path``; stops when it is not the registered one (a
    registered hash of 16 characters or more is compared over its own length)."""
    if not isinstance(registered, str) or len(registered) < 16:
        raise SystemExit(f"no registered sha256 for {what}; nothing was written")
    if not path.is_file():
        raise SystemExit(f"{path} not found ({what}); nothing was written")
    found = sha256_file(path)
    if not found.startswith(registered):
        raise SystemExit(
            f"{path} is not the registered file ({what}): sha256 {found[:16]}, registered "
            f"{registered[:16]}; nothing was written"
        )
    return found


def subset_counts(counts: Mapping[str, Any]) -> dict[str, Any]:
    """The two entries of the counts file that this module uses, and nothing else of it: the
    record of the subset and the record of its item file."""
    name = Path(ITEMS).name
    return {
        "subsets": {SUBSET: dig(counts, "subsets", SUBSET) or {}},
        "outputs": {"items": {name: dig(counts, "outputs", "items", name) or {}}},
    }


def marked_rows(
    root: Path, record: Mapping[str, Any]
) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, str]]:
    """The statements marked for the check in the registered eligible list, sorted by id, with
    the two entries of the counts file that are used and the sha256 of the two files. Stops
    when either file is not the one the freeze record names, when the marked statements are
    not the subset the counts file records, or when one of them is not dated in the test
    period."""
    source = {
        "eligible_sha256": require_registered(
            root / ELIGIBLE, dig(record, "tables", "eligible_list", "sha256"), "the eligible list"
        ),
        "counts_sha256": require_registered(
            root / COUNTS, output_hash(record, COUNTS), "the counts file of the dataset builder"
        ),
    }
    counts = subset_counts(json.loads((root / COUNTS).read_text(encoding="utf-8")))
    listed = read_columns(root / ELIGIBLE, ELIGIBLE_FIELDS)
    marked = listed[listed[SUBSET] == "1"].drop(columns=SUBSET)
    rows = marked.sort_values("statement_group_id").to_dict("records")
    ids = [row["statement_group_id"] for row in rows]
    subset = dig(counts, "subsets", SUBSET) or {}
    if len(set(ids)) != len(ids) or (D.ids_sha256(ids), len(ids)) != (
        subset.get("ids_sha256"),
        subset.get("statements"),
    ):
        raise SystemExit(
            f"the statements marked {SUBSET} in {root / ELIGIBLE} are not the subset that "
            f"{root / COUNTS} records; nothing was written"
        )
    other = [row["statement_group_id"] for row in rows if F.split_of(row["event_date"]) != "test"]
    if other:
        raise SystemExit(f"marked statements are not dated in the test period: {other[:5]}")
    return rows, counts, source


def harness_items(
    root: Path, counts: Mapping[str, Any], rows: Sequence[Mapping[str, str]]
) -> tuple[dict[str, dict[str, str]], str]:
    """The registered items of the subset by statement id, with the keys this module uses and
    no other, and the sha256 of their file. Stops when the file is not the one the counts file
    records, or when its items are not those of the marked statements."""
    path = root / ITEMS
    registered = dig(counts, "outputs", "items", path.name, "sha256")
    digest = require_registered(path, registered, "the item file of the subset")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    wanted = set(ITEM_KEYS)
    items = [
        json.loads(line, object_pairs_hook=lambda pairs: {k: v for k, v in pairs if k in wanted})
        for line in lines
    ]
    if any(set(item) != wanted for item in items):
        raise SystemExit(f"{path}: an item lacks one of {', '.join(ITEM_KEYS)}")
    by_id = {item["item_id"]: item for item in items}
    if len(by_id) != len(items) or set(by_id) != {row["statement_group_id"] for row in rows}:
        raise SystemExit(f"{path} does not hold the items of the marked statements")
    for row in rows:
        item = by_id[row["statement_group_id"]]
        shown = (item["date_of_update"], item["stated_end"], item["display_event_id"])
        if shown != (row["event_date"], row["stated_end"], row["event_id"]):
            raise SystemExit(
                f"{path}: the item of {row['statement_group_id']} is not the display row, the "
                "date or the stated end of the eligible list"
            )
    return by_id, digest


def first_draw(root: Path, record: Mapping[str, Any]) -> tuple[set[str], dict[str, str]]:
    """The statements of the pilot, the check set, its reserve and the literal sample, with the
    sha256 of each list. All four lists must be on disk and be the registered ones: without
    them nothing shows that a sheet holds no statement an annotator labelled."""
    ids: set[str] = set()
    hashes = {}
    for name in FIRST_DRAW:
        path = root / SAMPLES / f"sample_{name}.csv"
        registered = dig(record, "sample_lists", name, "sha256")
        hashes[name] = require_registered(path, registered, f"the {name} list")
        ids |= set(read_columns(path, ("statement_group_id",))["statement_group_id"])
    return ids, hashes


def load_events(root: Path, record: Mapping[str, Any]) -> tuple[pd.DataFrame, str]:
    """The first-sight fields of the registered events table that the rule reader and the
    blinding check need (``EVENT_FIELDS``), and the sha256 of the file."""
    path = root / EVENTS
    registered = dig(record, "tables", "open", EVENTS, "gzip_sha256")
    digest = require_registered(path, registered, "the events table")
    return read_columns(path, EVENT_FIELDS), digest


def frozen_reader(record: Mapping[str, Any]) -> dict[str, str]:
    """The sha256 of the rule reader's two files; stops when one is not the frozen file."""
    found = {}
    for name, module in (("rules.py", F.rules), ("forms.py", F)):
        registered = dig(record, "code", name)
        found[name] = require_registered(Path(module.__file__), registered, f"the frozen {name}")
    if not found["rules.py"].startswith(F.RULES_SHA256):
        raise SystemExit(f"rules.py is not the frozen file ({F.RULES_SHA256})")
    return found


def labelled(events: pd.DataFrame, first: Iterable[str]) -> set[str]:
    """The statements no sheet may show: those of the first draw, and every statement with the
    generic, company and normalised text of one of them at another date."""
    first = set(first)
    return first | D.labelled_statements(events, first)


def rule_readings(
    events: pd.DataFrame,
    rows: Sequence[Mapping[str, str]],
    items: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, str]]:
    """The frozen rule reading of each statement in the cells a sheet shows, by statement id.

    The reading is that of ``forms.statement_forms`` on the statement's events, as the dataset
    builder takes it. Stops when it is not the registered reading (form and ``stated_end``, and
    not stale), when the display row is not an event of the statement, or when the text shown,
    read on its own, gives another type, period or stale flag.
    """
    ids = {row["statement_group_id"] for row in rows}
    members = events[events["statement_group_id"].isin(ids)]
    read = F.statement_forms(members).set_index("statement_group_id").to_dict("index")
    of_statement = dict(zip(members["event_id"], members["statement_group_id"], strict=True))
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        gid = row["statement_group_id"]
        if gid not in read or of_statement.get(row["event_id"]) != gid:
            raise SystemExit(
                f"{gid}: its display row {row['event_id']} is not an event of this statement in "
                "the events table"
            )
        r = read[gid]
        end = r["end"] if r["form"] in F.DATED_FORMS else ""
        stale = bool(r["stale"])
        if (r["form"], end) != (row["form"], row["stated_end"]) or stale or not end:
            raise SystemExit(
                f"{gid}: the rule reader and the registered list disagree: the reader gives "
                f"{r['form']} ending {end or 'nowhere'}{', stale' if stale else ''}; the list, "
                f"{row['form']} ending {row['stated_end']}. Nothing was written"
            )
        item = items[gid]
        text = C.statement_text(item["availability_information"], item["related_information"])
        own = F.classify(text, item["date_of_update"])
        if (own.statement_type, own.start, own.end, own.stale) != (
            r["statement_type"],
            r["start"],
            r["end"],
            stale,
        ):
            raise SystemExit(
                f"{gid}: the text shown, read on its own, does not give the statement's rule "
                "reading. Nothing was written"
            )
        out[gid] = {
            "rule_statement_type": r["statement_type"],
            "rule_start": r["start"],
            "rule_end": end,
            "rule_stale": str(int(stale)),
        }
    return out


# --------------------------------------------------------------------------------------------
# Item ids and the assignment
# --------------------------------------------------------------------------------------------


def split_sizes(n: int) -> dict[str, int]:
    """How many of ``n`` statements go to A1 alone, to A2 alone and to both: a tenth to both
    (rounded half up), the others in two halves, A1 taking the odd one."""
    shared = S.round_half_up(n * SHARED_PERCENT, 100)
    own = n - shared
    return {ANNOTATORS[0]: own - own // 2, ANNOTATORS[1]: own // 2, SHARED: shared}


def assignment(ids: Iterable[str]) -> dict[str, str]:
    """Who checks each statement: the ids in the seeded order of the draw ``reference/assign``,
    the first block for A1, the next for A2, the last for both. The input order is ignored."""
    order = S.shuffled(ids, f"{SHEET}/assign")
    who = [name for name, size in split_sizes(len(order)).items() for _ in range(size)]
    return dict(zip(order, who, strict=True))


@dataclass(frozen=True)
class Sample:
    """The statements on the sheets, sorted by statement id, each with its ``item_id`` and
    ``assigned_to``; how many the registration marked, whether the subset is final, and the
    marked statements that were left off the sheets."""

    rows: tuple[dict[str, str], ...]
    registered: int
    final: bool
    left_off: tuple[str, ...]

    def of(self, annotator: str) -> dict[str, dict[str, str]]:
        """The rows of one annotator's sheet by item id: their own and the shared ones."""
        return {r["item_id"]: r for r in self.rows if r["assigned_to"] in (annotator, SHARED)}


def checkers(row: Mapping[str, str]) -> tuple[str, ...]:
    return ANNOTATORS if row["assigned_to"] == SHARED else (row["assigned_to"],)


def on_sheets(
    rows: Sequence[Mapping[str, str]], counts: Mapping[str, Any], left_off: Iterable[str] = ()
) -> Sample:
    """The sample as the sheets hold it: the marked statements without those left off."""
    skip = set(left_off)
    kept = [dict(row) for row in rows if row["statement_group_id"] not in skip]
    who = assignment(row["statement_group_id"] for row in kept)
    for row in kept:
        row["item_id"] = S.item_id(row["statement_group_id"])
        row["assigned_to"] = who[row["statement_group_id"]]
    if len({row["item_id"] for row in kept}) != len(kept):
        raise SystemExit("two statements share an item id")
    final = dig(counts, "subsets", SUBSET, "final") is True
    return Sample(tuple(kept), len(rows), final, tuple(sorted(skip)))


def sample_record(sample: Sample) -> dict[str, Any]:
    """The sample for the manifest: sizes, hashes of the ids and of the assignment, and counts
    of statements by year and by form class. Nothing here names who checks which item."""
    rows = sample.rows
    pairs = sorted((row["item_id"], row["assigned_to"]) for row in rows)
    given = Counter(row["assigned_to"] for row in rows)
    return {
        "registered": sample.registered,
        "final": sample.final,
        "left_off": list(sample.left_off),
        "statements": len(rows),
        "ids_sha256": D.ids_sha256(row["statement_group_id"] for row in rows),
        "assigned": {name: given[name] for name in (*ANNOTATORS, SHARED)},
        "assignment_sha256": S.sha256_text("".join(f"{i},{who}\n" for i, who in pairs)),
        "by_year": dict(sorted(Counter(row["event_date"][:4] for row in rows).items())),
        "by_form": {f: n for f in F.FORM_NAMES if (n := sum(r["form"] == f for r in rows))},
    }


# --------------------------------------------------------------------------------------------
# Sheets and the items text
# --------------------------------------------------------------------------------------------


def entry_block(item: Mapping[str, str]) -> str:
    """The entry of an item exactly as the reading harness renders it (``read.ENTRY_BLOCK``)."""
    from analysis.coling import read

    template = read.PromptTemplate("entry-block", "literal", read.ENTRY_BLOCK)
    return read.render_prompt(template, read.ReadItem.from_dict(dict(item)))


def rule_line(cells: Mapping[str, str]) -> str:
    """The rule reading on one line, as the guide's example writes it."""
    stale = "stale" if cells["rule_stale"] == "1" else "not stale"
    return (
        f"Rule reading: {cells['rule_statement_type']}, {cells['rule_start']} to "
        f"{cells['rule_end']}, {stale}"
    )


def sheet_meta(annotator: str, n_items: int, guide: str) -> list[tuple[str, Any]]:
    return [
        ("task", TASK),
        ("sheet", SHEET),
        ("annotator", annotator),
        ("seed", SEED),
        ("guide", S.guide_stamp(guide)),
        ("rule reader", f"rules.py sha256 {F.RULES_SHA256}"),
        ("items", n_items),
        *((f"values of {column}", values) for column, values in SCHEME.items()),
        *((f"code {code}", meaning) for code, meaning in CODES.items()),
        ("sitting_start", ""),
        ("sitting_end", ""),
    ]


def build_files(
    sample: Sample,
    items: Mapping[str, Mapping[str, str]],
    readings: Mapping[str, Mapping[str, str]],
    guide: str,
) -> dict[str, str]:
    """The blank sheet and the items text of each annotator, by file name. The rows of a sheet
    are in that annotator's seeded order, and the text follows the order of the sheet."""
    files = {}
    for annotator in ANNOTATORS:
        mine = sample.of(annotator)
        order = S.shuffled(mine, f"{SHEET}/order/{annotator}")
        rows = []
        text = [
            f"Task E, reference readings: the items of {SHEET}_{annotator}.csv, in the order of "
            "the sheet.",
            "Verdicts go into the sheet; this file is for reading.",
            "",
        ]
        for n, shown_id in enumerate(order, start=1):
            gid = mine[shown_id]["statement_group_id"]
            item = {**items[gid], "item_id": shown_id}
            rows.append(S.shown_cells(item) | dict(readings[gid]))
            text += [
                f"=== {n} of {len(order)}: {shown_id} ===",
                entry_block(item),
                rule_line(readings[gid]),
                "",
            ]
        meta = sheet_meta(annotator, len(order), guide)
        files[f"{SHEET}_{annotator}.csv"] = S.sheet_text(SHEET_COLUMNS, rows, meta)
        files[f"{SHEET}_{annotator}_items.txt"] = "\n".join(text)
    return files


def holds_marks(path: Path) -> bool:
    """Whether the sheet at ``path`` was filled in: a sitting time or any entered cell (a file
    that cannot be read as a sheet counts as filled)."""
    if not path.is_file():
        return False
    try:
        meta, rows = S.read_sheet(path)
    except (UnicodeDecodeError, csv.Error):
        return True
    timed = any(value for key, value in meta if key in S.SITTING_KEYS)
    return timed or any(row.get(c) for row in rows for c in ENTERED)


def read_manifest(out: Path) -> dict[str, Any]:
    path = out / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def update_manifest(out: Path, entries: Mapping[str, Any], drop: Iterable[str] = ()) -> None:
    """Replace the named sections of the manifest, remove those of ``drop`` and leave the
    others as they are."""
    manifest = read_manifest(out) | {
        "about": "Task E, the reference-reading check: blank sheets, submitted sheets, result.",
        "seed": SEED,
        **entries,
    }
    for section in drop:
        manifest.pop(section, None)
    S.write_text(out, MANIFEST, json_text(manifest))


# --------------------------------------------------------------------------------------------
# Validator
# --------------------------------------------------------------------------------------------


@dataclass
class Checked:
    """A sheet after validation: the marks by item id, errors and warnings, minutes."""

    marks: dict[str, dict[str, str]]
    errors: list[str]
    warnings: list[str]
    minutes: int | None
    meta: list[tuple[str, str]]
    rows: list[dict[str, str]]

    @property
    def ok(self) -> bool:
        return not self.errors


def code_list(cell: str) -> list[str]:
    """The codes of a cell: a list separated by semicolons, commas or spaces."""
    return [part for part in re.split(r"[;,\s]+", cell.strip()) if part]


def oddities(row: Mapping[str, str], mark: Mapping[str, str]) -> list[str]:
    """What looks inconsistent in a row that has no error: the warnings of the validator."""
    odd = []
    codes, true_end = mark["codes"].split(";"), mark["true_end"]
    if mark["verdict"] == "error" and not true_end and "K3" not in codes:
        odd.append("error with no true_end: give the right last day, or K3 if there is no date")
    if "K3" in codes and true_end:
        odd.append("K3 says that the target gives no date, but true_end gives one")
    if "K2" in codes and true_end and true_end == row["rule_end"]:
        odd.append("K2 says that the last day is wrong, but true_end is the rule_end")
    try:
        anchor = date.fromisoformat(row["date_of_update"]).isoformat()
    except ValueError:
        anchor = ""
    if true_end and anchor and (true_end < anchor) != ("K4" in codes):
        odd.append(
            "K4 is the code of a period that ends before the Date of update: true_end is "
            + ("before it without K4" if true_end < anchor else "not before it")
        )
    if mark["start_differs"] == "1" and mark["verdict"] != "ok":
        odd.append("start_differs is 1 but the verdict is not ok (it is for a right last day)")
    return odd


def read_mark(row: Mapping[str, str]) -> tuple[dict[str, str] | None, list[str], list[str]]:
    """The entered cells of one row, with what is wrong with them and what only looks odd.

    In a mark the codes are sorted and joined by semicolons, ``true_end`` is written in full
    and ``start_differs`` is 1 or 0. The mark is None when the row has an error.
    """
    verdict = row["verdict"]
    if verdict not in VERDICTS:
        said = f"verdict {verdict!r} is" if verdict else "verdict is missing: it is"
        return None, [f"{said} not one of {', '.join(VERDICTS)}"], []
    errors = []
    codes = code_list(row["codes"])
    unknown = [code for code in codes if code not in CODES]
    if unknown:
        errors.append(f"codes: unknown {' '.join(unknown)} (the codes are {', '.join(CODES)})")
    if verdict == "error" and not codes:
        errors.append("verdict is error but codes is empty")
    if verdict != "error" and codes:
        errors.append(f"codes is given but verdict is {verdict}")
    true_end = ""
    if row["true_end"]:
        try:
            true_end = S.parse_day(row["true_end"], end=True).isoformat()
        except ValueError as problem:
            errors.append(f"true_end: {problem}")
        if verdict != "error":
            errors.append(f"true_end is given but verdict is {verdict}")
    if row["start_differs"] not in ("", "0", "1"):
        errors.append("start_differs must be 1 or 0")
    if verdict == "cannot_tell" and not row["note"]:
        errors.append("verdict is cannot_tell but note is empty: say why")
    if errors:
        return None, errors, []
    mark = {
        "verdict": verdict,
        "codes": ";".join(sorted(set(codes))),
        "true_end": true_end,
        "start_differs": "1" if row["start_differs"] == "1" else "0",
        "note": row["note"],
    }
    return mark, [], oddities(row, mark)


def validate_sheet(
    meta: list[tuple[str, str]],
    rows: list[dict[str, str]],
    blank: Sequence[Mapping[str, str]] | None = None,
) -> Checked:
    """Check a filled sheet; ``blank`` is the rows of the sheet as it was handed out."""
    errors: list[str] = []
    warnings: list[str] = []
    marks: dict[str, dict[str, str]] = {}
    missing = [c for c in SHEET_COLUMNS if rows and c not in rows[0]]
    if missing or not rows:
        problem = f"columns missing: {', '.join(missing)}" if missing else "the sheet has no rows"
        if rows and any(";" in name for name in rows[0]):
            problem += " (the file looks semicolon-separated; save it comma-separated)"
        return Checked({}, [f"sheet: {problem}"], [], None, meta, rows)
    minutes, problems = S.sittings(meta)
    errors += problems
    seen = Counter(row["item_id"] for row in rows)
    handed = {S.unguarded(b["item_id"]): b for b in blank} if blank is not None else None
    for n, row in enumerate(rows, start=1):
        where = f"row {n} ({row['item_id'] or 'no item_id'})"
        if not row["item_id"] or seen[row["item_id"]] > 1:
            errors.append(f"{where}: item_id is missing or repeated")
            continue
        if handed is not None:
            if row["item_id"] not in handed:
                errors.append(f"{where}: this item is not in the blank sheet")
                continue
            was = handed[row["item_id"]]
            changed = [
                c for c in SHOWN if S.unguarded(row[c]) != S.unguarded((was.get(c) or "").strip())
            ]
            if changed:
                errors.append(
                    f"{where}: shown cells changed ({', '.join(changed)}); "
                    "import every column as text and do not edit shown cells"
                )
        mark, wrong, odd = read_mark(row)
        errors += [f"{where}: {e}" for e in wrong]
        warnings += [f"{where}: {w}" for w in odd]
        if mark is not None:
            marks[row["item_id"]] = mark
    if handed is not None:
        absent = sorted(set(handed) - set(seen))
        errors += [f"sheet: item {i} of the blank sheet is missing" for i in absent]
    return Checked(marks, errors, warnings, minutes, meta, rows)


def check_file(sheet: Path, blank: Path | None, out: Path) -> Checked:
    """Validate the sheet at ``sheet`` against its blank: the one given, or the file
    ``reference_<annotator>.csv`` under ``out`` that the sheet's header names. A sheet that is
    the blank's own file was filled in place and is refused."""
    for path in (sheet, blank):
        if path is not None and not path.is_file():
            return Checked({}, [f"sheet: {path} not found"], [], None, [], [])
    try:
        meta, rows = S.read_sheet(sheet)
    except (UnicodeDecodeError, csv.Error):
        return Checked({}, [S.NOT_UTF8], [], None, [], [])
    if blank is None:
        annotator = S.meta_value(meta, "annotator")
        beside = out / f"{SHEET}_{annotator}.csv"
        named = S.meta_value(meta, "sheet") == SHEET and annotator in ANNOTATORS
        blank = beside if named and beside.is_file() else None
    if blank is not None and blank.resolve() == sheet.resolve():
        message = "sheet: this is the blank sheet itself; fill a copy kept elsewhere"
        return Checked({}, [message], [], None, meta, rows)
    checked = validate_sheet(meta, rows, S.read_sheet(blank)[1] if blank is not None else None)
    if blank is None:
        checked.warnings.append(S.NO_BLANK)
    return checked


def report_check(sheet: Path, checked: Checked) -> int:
    for line in checked.errors:
        print(f"error: {line}")
    for line in checked.warnings:
        print(f"warning: {line}")
    minutes = "not given" if checked.minutes is None else f"{checked.minutes} minutes"
    print(
        f"{sheet}: {len(checked.rows)} rows, {len(checked.marks)} valid, "
        f"{len(checked.errors)} errors, {len(checked.warnings)} warnings; sittings: {minutes}"
    )
    return 0 if checked.ok else 1


# --------------------------------------------------------------------------------------------
# Scorer: agreement, adjudication, result
# --------------------------------------------------------------------------------------------


def agreement(sample: Sample, sheets: Mapping[str, Checked]) -> dict[str, Any]:
    """The statistics before adjudication: what each annotator reported, the agreement on the
    shared items, and the time taken."""
    reported = {}
    for annotator in ANNOTATORS:
        mine = [sheets[annotator].marks[i] for i in sample.of(annotator)]
        reported[annotator] = {
            "items": len(mine),
            **{verdict: sum(m["verdict"] == verdict for m in mine) for verdict in VERDICTS},
            "codes": {code: sum(code in m["codes"].split(";") for m in mine) for code in CODES},
            "start_differs": sum(m["start_differs"] == "1" for m in mine),
        }
    both = sorted(row["item_id"] for row in sample.rows if row["assigned_to"] == SHARED)
    pairs = [tuple(sheets[a].marks[i]["verdict"] for a in ANNOTATORS) for i in both]
    clear = [pair for pair in pairs if "cannot_tell" not in pair]
    same = sum(a == b for a, b in pairs)
    minutes = {a: sheets[a].minutes for a in ANNOTATORS}
    return {
        "statements": len(sample.rows),
        "reported": reported,
        "shared": {
            "items": len(pairs),
            "same_verdict": same,
            "raw_agreement": round(same / len(pairs), 4) if pairs else None,
            "with_cannot_tell": len(pairs) - len(clear),
            "kappa_ok_error": cohen_kappa(clear)
            if len({v for p in clear for v in p}) > 1
            else None,
            "items_that_differ": [i for i, (a, b) in zip(both, pairs, strict=True) if a != b],
        },
        "minutes": minutes,
        "seconds_per_item": {
            a: round(60 * minutes[a] / len(sheets[a].marks), 1)
            if minutes[a] and sheets[a].marks
            else None
            for a in ANNOTATORS
        },
    }


def adjudication_rows(
    sample: Sample, sheets: Mapping[str, Checked], shown: Mapping[str, Mapping[str, str]]
) -> list[dict[str, str]]:
    """One row for every item that an annotator marked ``error`` or ``cannot_tell``, sorted by
    item id: the shown cells and the entries of each annotator who checked the item (the cells
    of an annotator who did not are empty)."""
    rows = []
    for entry in sorted(sample.rows, key=lambda r: r["item_id"]):
        item = entry["item_id"]
        marks = {a: sheets[a].marks[item] for a in checkers(entry)}
        if all(mark["verdict"] == "ok" for mark in marks.values()):
            continue
        row = {c: shown[item][c] for c in SHOWN}
        for annotator, mark in marks.items():
            row |= {f"{annotator}_{c}": mark[c] for c in ENTERED}
        rows.append(row)
    return rows


def as_shown(cell: str | None) -> str:
    """A cell of ADJ's sheet for comparison: without the guard of a formula-like cell, and on
    one line (a workbook may store the line breaks of a note otherwise)."""
    return S.one_line(S.unguarded((cell or "").strip()))


def check_adjudication(
    wanted: Sequence[Mapping[str, str]], filled: Sequence[Mapping[str, str]]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """The decisions by item id, and what is missing or malformed in the filled sheet. In a
    decision the codes are sorted and joined by semicolons and the date is written in full.
    ``wanted`` is the rows of the sheet as the scorer writes it for these sheets: a filled row
    whose shown cells or annotators' entries are not those was decided on other entries."""
    by_item = {S.unguarded(row.get("item_id", "")): row for row in filled}
    problems = []
    if len(by_item) != len(filled):
        problems.append("an item is listed more than once")
    decisions: dict[str, dict[str, str]] = {}
    for sent in sorted(wanted, key=lambda w: w["item_id"]):
        item = sent["item_id"]
        row = by_item.get(item)
        decision = (row or {}).get("decision", "")
        if row is None or not decision:
            problems.append(f"{item}: no decision")
            continue
        changed = [c for c in ADJUDICATION_SHOWN if as_shown(row.get(c)) != as_shown(sent.get(c))]
        if changed:
            problems.append(
                f"{item}: the cells shown to ADJ are not those of these sheets "
                f"({', '.join(changed)}); fill a copy of the sheet as it was written, with "
                "every column as text"
            )
        if decision not in DECISIONS:
            problems.append(f"{item}: decision must be one of {', '.join(DECISIONS)}")
            continue
        codes = code_list(row.get("confirmed_codes", ""))
        day = row.get("confirmed_true_end", "")
        if decision == "confirmed" and (not codes or any(c not in CODES for c in codes)):
            problems.append(f"{item}: a confirmed error needs confirmed_codes from K1 to K4")
        if decision != "confirmed" and (codes or day):
            problems.append(f"{item}: confirmed_codes or confirmed_true_end without confirmed")
        try:
            day = S.parse_day(day, end=True).isoformat() if day else ""
        except ValueError as problem:
            problems.append(f"{item}: confirmed_true_end: {problem}")
        decisions[item] = {
            "decision": decision,
            "confirmed_codes": ";".join(sorted(set(codes))),
            "confirmed_true_end": day,
            "adj_note": row.get("adj_note", ""),
        }
    extra = sorted(set(by_item) - {w["item_id"] for w in wanted})
    problems += [f"{item or 'a row with no item_id'}: not sent to adjudication" for item in extra]
    return decisions, problems


def breakdown(
    rows: Sequence[Mapping[str, str]], state: Mapping[str, str], key: str, order: Iterable[str]
) -> dict[str, dict[str, int]]:
    """Statements, confirmed errors, unresolved items and confirmed readings by a row field."""
    out = {}
    for value in order:
        mine = [state[row["item_id"]] for row in rows if row[key] == value]
        if mine:
            out[value] = {
                "statements": len(mine),
                "confirmed_errors": mine.count("confirmed"),
                "unresolved": mine.count("unresolved"),
                "reading_confirmed": mine.count("ok") + mine.count("rejected"),
            }
    return out


def result(
    sample: Sample, sheets: Mapping[str, Checked], decisions: Mapping[str, Mapping[str, str]]
) -> dict[str, Any]:
    """The statistics of the guide's section 8.4 after adjudication.

    The state of an item is ``ok`` (no annotator reported anything), or ADJ's decision. A rule
    reading is confirmed when the state is ``ok`` or ``rejected``; an ``unresolved`` item has no
    confirmed error and no confirmed reading.
    """
    rows = [dict(row) | {"year": row["event_date"][:4]} for row in sample.rows]
    n = len(rows)
    state = {r["item_id"]: dig(decisions, r["item_id"], "decision") or "ok" for r in rows}
    held = Counter(state.values())
    wrong = [row for row in rows if state[row["item_id"]] == "confirmed"]
    right = [row for row in rows if state[row["item_id"]] in ("ok", "rejected")]
    codes = Counter(
        c for row in wrong for c in decisions[row["item_id"]]["confirmed_codes"].split(";")
    )
    flagged = {
        row["item_id"]
        for row in rows
        if any(sheets[a].marks[row["item_id"]]["start_differs"] == "1" for a in checkers(row))
    }
    return {
        "statements": n,
        "registered": sample.registered,
        "left_off": len(sample.left_off),
        "subset_final": sample.final,
        "sent_to_adjudication": len(decisions),
        "confirmed_errors": held["confirmed"],
        "rejected": held["rejected"],
        "unresolved": held["unresolved"],
        "without_confirmed_error": share(n - held["confirmed"], n),
        "reading_confirmed": share(len(right), n),
        "codes": {code: codes[code] for code in CODES},
        "by_form": breakdown(rows, state, "form", F.FORM_NAMES),
        "by_year": breakdown(rows, state, "year", sorted({row["year"] for row in rows})),
        "start_differs": len(flagged),
        "errors": [
            {
                "item_id": row["item_id"],
                "statement_group_id": row["statement_group_id"],
                "form": row["form"],
                "codes": decisions[row["item_id"]]["confirmed_codes"].split(";"),
                "true_end": decisions[row["item_id"]]["confirmed_true_end"],
            }
            for row in sorted(wrong, key=lambda r: r["item_id"])
        ],
        "unresolved_items": sorted(i for i, s in state.items() if s == "unresolved"),
        "confirmed_statement_ids": sorted(row["statement_group_id"] for row in right),
    }


def decisions_entered(path: Path) -> bool:
    """Whether the adjudication sheet at ``path`` holds an entry of ADJ (a file that cannot be
    read as a sheet counts as filled)."""
    if not path.is_file():
        return False
    try:
        _, rows = S.read_sheet(path)
    except (UnicodeDecodeError, csv.Error):
        return True
    return any(row.get(c) for row in rows for c in ADJUDICATION_ENTERED)


def submit(out: Path, files: Mapping[str, Path], replace: bool) -> dict[str, Any] | None:
    """Copy the validated sheets byte for byte under ``submitted/`` and return the manifest's
    entry with their sha256. ``files`` gives each sheet by its name there: the two annotators'
    and, once it is filled, ADJ's. A sheet that would take the place of another one of the
    same name is refused (None) unless ``replace`` is set; the entry then keeps the hash of the
    earlier one."""
    before = read_manifest(out).get("submitted", {})
    entry = {"files": dict(before.get("files", {})), "replaced": list(before.get("replaced", []))}
    data = {f"{SUBMITTED}/{name}": path.read_bytes() for name, path in files.items()}
    for name, new in data.items():
        old = out / name
        if old.is_file() and old.read_bytes() != new:
            if not replace:
                print(f"error: {old} holds another submitted sheet; --replace takes this one")
                return None
            entry["replaced"].append({"file": name, "sha256": sha256_file(old)})
    for name, new in data.items():
        entry["files"][name] = S.write_bytes(out, name, new)
    return entry


def filled_adjudication(path: Path) -> list[dict[str, str]] | None:
    """The rows of ADJ's filled sheet; None, with one error line, when it cannot be read."""
    if not not_sealed(path).is_file():
        print(f"error: adjudication: {path} not found")
        return None
    try:
        return S.read_sheet(path)[1]
    except (UnicodeDecodeError, csv.Error):
        print(f"error: adjudication: {S.NOT_UTF8}")
        return None


def withdraw_result(out: Path, sheets_sha256: Mapping[str, str]) -> list[str]:
    """Remove a result that was scored on other sheets than these, with its confirmed list:
    once a sheet is replaced they hold for no submitted pair. Returns the names removed."""
    path = out / RESULT
    try:
        scored = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except ValueError:
        scored = {}
    if scored is None or dig(scored, "sheets_sha256") == dict(sheets_sha256):
        return []
    removed = [name for name in (RESULT, CONFIRMED) if (out / name).is_file()]
    for name in removed:
        (out / name).unlink()
    return removed


def withdraw_adjudication(out: Path) -> bool:
    """Remove the adjudication sheet on disk when the sheets that are scored report no item:
    it was written for other sheets and would ask ADJ for decisions that no result uses. The
    caller has checked that it holds no entry of ADJ. Returns whether one was there."""
    path = out / ADJUDICATION
    if not path.is_file():
        return False
    path.unlink()
    return True


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


def out_folder(args: argparse.Namespace) -> Path:
    return not_sealed(args.out if args.out is not None else args.root / OUT_NAME)


def minutes_for(n_items: int) -> list[int]:
    """Minutes for a sheet at the guide's planning rate, then at its low and its high rate."""
    return [S.round_half_up(n_items * seconds, 60) for seconds in SECONDS_PER_ITEM]


def run_sheets(args: argparse.Namespace) -> int:
    root, out = args.root, out_folder(args)
    record = frozen_record(root)
    rows, counts, source = marked_rows(root, record)
    first, lists = first_draw(root, record)
    events, source["events_sha256"] = load_events(root, record)
    source |= {f"{name}_sha256": digest for name, digest in frozen_reader(record).items()}
    source["first_draw_lists_sha256"] = lists
    seen = sorted(labelled(events, first) & {row["statement_group_id"] for row in rows})
    final = dig(counts, "subsets", SUBSET, "final") is True
    if seen and (final or not args.leave_off):
        why = (
            "the counts file calls the subset final, so the files contradict each other"
            if final
            else "the subset is not final: --leave-off leaves them off the sheets"
        )
        raise SystemExit(
            f"{len(seen)} marked statements are statements of the pilot, the check sets or the "
            f"literal sample, or have the text of one ({', '.join(seen[:5])}); {why}. Nothing "
            "was written"
        )
    sample = on_sheets(rows, counts, seen)
    items, source["items_sha256"] = harness_items(root, counts, rows)
    readings = rule_readings(events, sample.rows, items)
    guide = not_sealed(args.guide).read_text(encoding="utf-8")
    files = build_files(sample, items, readings, guide)
    per_sheet = {a: len(sample.of(a)) for a in ANNOTATORS}
    entries = {
        "inputs": source,
        "sample": sample_record(sample),
        "sheets": {
            "guide": S.guide_stamp(guide),
            "items_per_sheet": per_sheet,
            "minutes_per_sheet": {a: minutes_for(n) for a, n in per_sheet.items()},
            "files": {name: S.sha256_text(text) for name, text in sorted(files.items())},
        },
    }
    record_ = entries["sample"]
    print(
        f"task E: {record_['statements']} of {record_['registered']} registered statements "
        f"({len(seen)} left off); by year {record_['by_year']}; by form {record_['by_form']}"
    )
    for annotator, n in per_sheet.items():
        plan, low, high = minutes_for(n)
        print(f"{SHEET}_{annotator}.csv: {n} items, about {plan} minutes ({low} to {high})")
    if args.check:
        manifest = read_manifest(out)
        stale = [n for n, text in files.items() if not same_text(out / n, text)]
        stale += [MANIFEST] if any(manifest.get(k) != v for k, v in entries.items()) else []
        for name in stale:
            print(f"not up to date: {out / name}")
        print("up to date" if not stale else f"{len(stale)} files are not up to date")
        return 1 if stale else 0
    filled = [p for a in ANNOTATORS if holds_marks(p := out / f"{SHEET}_{a}.csv")]
    if filled:
        raise SystemExit(
            f"{', '.join(p.as_posix() for p in filled)}: the sheet holds a verdict or a sitting "
            "time (it was filled in place). Nothing was written. Move it out of the folder "
            f"(external_data/annotation/{SHEET}/) and run the command again"
        )
    for name, text in files.items():
        S.write_text(out, name, text)
    update_manifest(out, entries)
    print(f"wrote {', '.join(sorted(files))} and {MANIFEST} to {out.as_posix()}")
    print(f"note: {HAND_OUT}")
    return 0


def same_text(path: Path, text: str) -> bool:
    return path.is_file() and path.read_bytes() == text.encode("utf-8")


def run_validate(args: argparse.Namespace) -> int:
    blank = not_sealed(args.blank) if args.blank is not None else None
    return report_check(args.sheet, check_file(not_sealed(args.sheet), blank, out_folder(args)))


def registered_sample(root: Path, manifest: Mapping[str, Any]) -> Sample:
    """The sample of the sheets under the manifest, derived again from the registered list.
    Stops when it is not the sample the sheets were written on."""
    rows, counts, _ = marked_rows(root, frozen_record(root))
    sample = on_sheets(rows, counts, dig(manifest, "sample", "left_off") or ())
    if sample_record(sample) != manifest.get("sample"):
        raise SystemExit(
            "the registered sample is not the one the sheets were written on; nothing was scored"
        )
    return sample


def returned_sheets(
    args: argparse.Namespace, out: Path, sample: Sample, manifest: Mapping[str, Any]
) -> tuple[dict[str, Checked], dict[str, dict[str, str]]] | None:
    """Both filled sheets, checked against the blanks the manifest records, and the shown cells
    of every item. None when a blank is not the recorded file or a sheet does not validate."""
    listed = dig(manifest, "sheets", "files") or {}
    sheets: dict[str, Checked] = {}
    shown: dict[str, dict[str, str]] = {}
    failed = False
    for annotator, path in zip(ANNOTATORS, (args.a1, args.a2), strict=True):
        blank = out / f"{SHEET}_{annotator}.csv"
        if not blank.is_file() or sha256_file(blank) != listed.get(blank.name):
            print(f"error: {blank} is missing or is not the sheet the manifest records")
            return None
        checked = check_file(not_sealed(path), blank, out)
        named = S.meta_value(checked.meta, "sheet"), S.meta_value(checked.meta, "annotator")
        if checked.ok and named != (SHEET, annotator):
            checked.errors.append(f"sheet: this is not the {SHEET} sheet of {annotator}")
        if checked.ok and set(checked.marks) != set(sample.of(annotator)):
            checked.errors.append("sheet: its items are not those of this annotator")
        failed = bool(report_check(path, checked)) or failed
        sheets[annotator] = checked
        for row in S.read_sheet(blank)[1]:
            shown[S.unguarded(row["item_id"])] = {c: S.unguarded(row[c]) for c in SHOWN}
    return None if failed else (sheets, shown)


def print_agreement(stats: Mapping[str, Any]) -> None:
    for annotator, said in stats["reported"].items():
        took = stats["seconds_per_item"][annotator]
        print(
            f"{annotator}: {said['items']} items; ok {said['ok']}, error {said['error']}, "
            f"cannot_tell {said['cannot_tell']}; seconds per item: {took or 'not given'}"
        )
    both = stats["shared"]
    print(f"shared items: the same verdict on {both['same_verdict']} of {both['items']}")


def print_result(scored: Mapping[str, Any]) -> None:
    n = scored["statements"]
    for name in ("without_confirmed_error", "reading_confirmed"):
        part = scored[name]
        low, high = part["wilson95"] or (None, None)
        print(f"{name}: {part['n']} of {n} ({part['share']}; Wilson 95% {low} to {high})")
    print(
        f"confirmed errors {scored['confirmed_errors']}, rejected {scored['rejected']}, "
        f"unresolved {scored['unresolved']}; by code {scored['codes']}; "
        f"start_differs {scored['start_differs']}"
    )


def run_score(args: argparse.Namespace) -> int:
    root, out = args.root, out_folder(args)
    manifest = read_manifest(out)
    if "sheets" not in manifest:
        raise SystemExit(f"no sheets under {out}: run the sheets command first")
    sample = registered_sample(root, manifest)
    checked = returned_sheets(args, out, sample, manifest)
    if checked is None:
        print("the sheets were not scored")
        return 2
    sheets, shown = checked
    returned = dict(zip(ANNOTATORS, (args.a1, args.a2), strict=True))
    if args.adjudication is None and decisions_entered(out / ADJUDICATION):
        print(
            f"error: {out / ADJUDICATION} holds decisions (it was filled in place) and would be "
            "written over; move it away and pass it with --adjudication"
        )
        return 2
    wanted = adjudication_rows(sample, sheets, shown)
    decisions: dict[str, dict[str, str]] | None = {} if not wanted else None
    files = {f"{SHEET}_{a}.csv": path for a, path in returned.items()}
    if args.adjudication is not None:
        filled = filled_adjudication(args.adjudication)
        if filled is None:
            return 2
        files[ADJUDICATION] = args.adjudication
        decisions, problems = check_adjudication(wanted, filled)
        for line in problems:
            print(f"error: adjudication: {line}")
        if problems:
            print("the adjudication sheet does not validate; no result was written")
            return 2
    submitted = submit(out, files, args.replace)
    if submitted is None:
        return 2
    stats = agreement(sample, sheets) | {
        "task": TASK,
        "sheets_sha256": {a: sha256_file(path) for a, path in returned.items()},
    }
    entries: dict[str, Any] = {"submitted": submitted}
    entries["agreement"] = {AGREEMENT: S.write_text(out, AGREEMENT, json_text(stats))}
    print_agreement(stats)
    if decisions is None:
        meta = [
            ("task", f"{TASK}, adjudication (section 5)"),
            ("sheet", f"{SHEET} adjudication"),
            ("seed", SEED),
            ("items", len(wanted)),
            ("values of decision", " | ".join(DECISIONS)),
            ("values of confirmed_codes", "; ".join(CODES) + " (with confirmed only)"),
            ("values of confirmed_true_end", "YYYY-MM-DD or YYYY-MM (with confirmed only)"),
        ]
        columns = (*ADJUDICATION_SHOWN, *ADJUDICATION_ENTERED)
        text = S.sheet_text(columns, wanted, meta)
        entries["adjudication"] = {ADJUDICATION: S.write_text(out, ADJUDICATION, text)}
        removed = withdraw_result(out, stats["sheets_sha256"])
        update_manifest(out, entries, drop=("result",) if removed else ())
        if removed:
            print(f"removed {', '.join(removed)}: they were scored on other sheets than these")
        print(f"{len(wanted)} items to adjudicate: fill a copy of {out / ADJUDICATION}")
        print("and run score again with --adjudication")
        return 3
    scored = result(sample, sheets, decisions) | {
        "task": TASK,
        "status": "scored",
        "sheets_sha256": stats["sheets_sha256"],
    }
    if args.adjudication is not None:
        scored["adjudication_sha256"] = submitted["files"][f"{SUBMITTED}/{ADJUDICATION}"]
    listed = [{"statement_group_id": i} for i in scored["confirmed_statement_ids"]]
    entries["result"] = {
        CONFIRMED: S.write_text(out, CONFIRMED, S.plain_csv(CONFIRMED_COLUMNS, listed)),
        RESULT: S.write_text(out, RESULT, json_text(scored)),
    }
    stale = args.adjudication is None and withdraw_adjudication(out)
    update_manifest(out, entries, drop=("adjudication",) if stale else ())
    if stale:
        print(f"removed {ADJUDICATION}: it was written for other sheets; these report no item")
    print_result(scored)
    print(f"wrote {RESULT} and {CONFIRMED} to {out.as_posix()}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.audit_reference",
        description=(__doc__ or "").splitlines()[0],
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def folders(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--root", type=Path, default=ROOT, help="the folder of the registered files"
        )
        sp.add_argument(
            "--out", type=Path, default=None, help="default: audit_reference under --root"
        )

    sheets = sub.add_parser("sheets", help="write the two blank sheets of task E")
    folders(sheets)
    sheets.add_argument("--guide", type=Path, default=GUIDE)
    sheets.add_argument("--check", action="store_true", help="write nothing; exit 1 when stale")
    sheets.add_argument("--leave-off", action="store_true", help="for a subset that is not final")
    sheets.set_defaults(run=run_sheets)
    check = sub.add_parser("validate", help="check a filled sheet")
    check.add_argument("sheet", type=Path)
    check.add_argument("--blank", type=Path, default=None)
    folders(check)
    check.set_defaults(run=run_validate)
    score = sub.add_parser("score", help="score the two filled sheets")
    score.add_argument("--a1", type=Path, required=True)
    score.add_argument("--a2", type=Path, required=True)
    score.add_argument("--adjudication", type=Path, default=None, help="the filled sheet of ADJ")
    score.add_argument("--replace", action="store_true", help="take a second submitted sheet")
    folders(score)
    score.set_defaults(run=run_score)
    return ap


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(None if argv is None else list(argv))
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
