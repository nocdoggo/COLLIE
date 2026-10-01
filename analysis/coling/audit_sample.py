"""Samples and annotator sheets for the literal-reading task (AUDIT_GUIDE.md sections 1, 3, 4, 9).

This module draws every sample that people label or that prompts are built on, writes the blank
sheets of task A (the pilot, the check set, its reserve and the literal task) with the matching
item file for the reading harness, and checks a filled sheet. Nothing here reads an outcome: the
inputs are the events table (first-sight fields only), the form classifier and the guide.

Unit and frame
--------------
The unit is the distinct statement of ``corpus.py`` (``statement_group_id``). The frame of the
first draw is every statement on the shortage listing whose status is Current when first seen,
from all periods. A statement is *train* when dated before 2023-01-01 and *test* otherwise.

The row shown for a statement (the display row) is one of its presentations at risk under
definition B (shortage listing, status Current, not available), taken by the seeded rule: the
member with the smallest sha256 of ``seed, "display/<statement_group_id>", event_id``. A statement
with no such presentation shows its member with the smallest ``event_id``
(:func:`display_events`).

Strata and quotas
-----------------
They are read from the allocation table of the guide (section 3.2), so the guide is their only
source: one row per stratum with its classifier classes and its quota in the pilot, the check
set, the reserve and the literal sample. In the cell of the classes, a part (up to a semicolon)
that ends with "with a distractor date" names classes the row takes only when the statement
carries a distractor date (the classifier's ``distractor_dates`` is above zero); the other
classes are the row's own. A statement belongs to the row that names its class with a
distractor date when it carries one, else to the row that owns its class. A stratum is called
after the first class it owns; the row that owns none is ``dated_distractor``. The table must
own every class of ``forms.py`` once, must name every class but ``distractor`` and
``discontinuation`` once with a distractor date, and its totals must add up, or the draw stops.

The first draw (:func:`draw_first`; the ``draw`` command)
--------------------------------------------------------
Pilot, check set, reserve and literal sample, in that order, each excluding the earlier ones.

* Order within a sample: strata are served from the one with the fewest statements left to the
  one with the most, so that a rare stratum is not blocked by the caps.
* Seeded order: the candidates of a sample, stratum and period are sorted by the sha256 of
  ``seed, "<sample>/<stratum>/<period>", statement_group_id`` and taken from the top. The result
  does not depend on the order of the input rows, and removing one statement moves no other.
* Periods: pilot, check set and reserve take train statements only. In the literal sample a
  stratum takes one third of its quota (rounded) from the test period, more where the train
  period cannot fill the rest, and more from the train period where the test period cannot.
* Caps, over the four samples together: at most ``MAX_PER_TEMPLATE`` items per masked template
  (the normalised text with months and numbers masked, :func:`masked_template`), at most
  ``MAX_PER_EPISODE`` per shortage episode, and no two items with the same generic, company and
  normalised text.
* Shortfall: a stratum that cannot fill its quota gives all it has. What the vague stratum
  lacks goes to the undated stratum first (``SHORTFALL_FIRST``). The items still missing go, one
  at a time and in turn, to the TBD, distractor-only and silent strata in the literal sample,
  and to the month-and-year stratum in the other three.
* Exclusions: the statements of the guide's Appendix A (generic, company, statement date; the
  same generic, company and normalised text at another date counts too), and the statement the
  harness builds its fixed test item on (``read.CANARY_ITEM``), whether or not the appendix
  lists it. A row of the appendix that matches no event, or a fixed test item that matches no
  statement, would leave a quoted statement in the frame, so ``draw`` and ``draw-later`` stop
  and name the rows; ``--allow-unmatched`` draws anyway.
* Guide phrases: a statement whose whole text is a phrase of ``MIN_PHRASE_WORDS`` words or more
  that the guide quotes in sections 3 and 7 is excluded too, whatever the drug or company
  (:func:`guide_phrases`, :func:`phrase_statements`). A phrase is the text between two double
  quotation marks. The two are compared word for word (:func:`phrase_key`: the normalised
  text without its punctuation), so that a colon or a hyphen inside the text does not tell a
  statement from the phrase. A statement made of both text fields (the builder joins them
  with ``||``) is excluded when each field is such a phrase: the guide quotes the two fields
  of an entry apart. A statement that only contains a quoted phrase, or of which one field is
  none, stays in the frame. ``draw`` prints, by stratum and period, how many frame statements
  the rule removes, and, for each sample, how many of its items contain a quoted phrase
  (``items_containing_a_guide_phrase`` in the manifest).

``draw`` prints, for each sample before it is drawn, what each stratum has left (``pool``) and
how many of those the caps still allow (``available``), then the quota and the number drawn, and
a warning for a sample that does not have the size of the guide's table. It
writes ``samples/sample_<name>.csv`` (``event_id`` of the display row, ``statement_group_id``,
``thread_id``; sorted by statement), ``samples/strata.csv`` and the ``samples`` entry of
``manifest.json`` with the sha256 of every list. ``--fixed pilot`` keeps the pilot list that is
on disk and draws the rest around it (for a guide revision that adds a pilot item to Appendix A).
The stratum table keeps the rows of a kept sample as they were written when it was drawn, so a
draw that keeps all four lists (the freeze run) writes the same lists and the same table.

A list on disk is never replaced by a different one without being named: when the guide or the
events table has changed so that a sample would hold other statements than its list on disk,
``draw`` stops before it writes anything. Name the sample under ``--fixed`` to keep its list (a
sheet of it has been handed out, or a later draw has excluded it) or under ``--replace`` to
take the new one; a replaced list whose sheets are on disk needs ``--sheets`` for it as well,
so that no sheet of the old list stays behind. A repeated draw on unchanged inputs needs
neither and writes the same bytes.

The later draw (:func:`draw_later`; the ``draw-later`` command)
--------------------------------------------------------------
After the train-half outcome-audit sample exists (``audit_outcomes.py``, which is given the
folder ``samples/`` as its exclusion list), three more lists are drawn, in this order, each
excluding the first draw, the outcome-audit sample, Appendix A and the lists before it, by
statement and by text (the same generic, company and normalised text at another date). The
items of the first draw are read by the annotators, so two more kinds of statement are left out
for them (:func:`labelled_twins`): a statement whose whole text is that of an item, word for
word and punctuation aside, whatever the drug or company (a text with no word is not
compared), and a statement
of the same generic and company, dated the same day, whose rule reading has the same statement
type and the same period: the same notice on another presentation, as when two presentations
differ by a typing error. The three lists are:

* ``incontext_pool``: ``LATER["incontext_pool"].size`` fit-split statements at risk under B with
  a dated form and not stale at issue, in turn over the nine dated forms; one per template and
  per episode. The track-record builder walks the list in ``draw_rank`` order and keeps the first
  ten that are resolved, which needs outcomes; this module reads none.
* ``dev_prompt``: dev-split statements at risk under B, in turn over the strata of the guide's
  table. Prompt development and the cost trials use them in ``draw_rank`` order.
* ``pair_seeds``: statements of the seven dated strata, not stale at issue, for the minimal-pair
  generator; one per template; the shortfall goes to month and year. They are train-period
  statements, except those of the relative stratum (``PAIR_SEEDS_LATER``), which are dated
  2023-01-01 or later: the labelling samples use every train-period relative statement. Only
  the text of such a seed is read here.

They are written to ``samples_later/`` (not to ``samples/``, so that a re-run of the outcome
audit draw does not exclude them), with ``draw_rank`` and ``period`` beside the three ids. As
for the first draw, a list on disk is not replaced by a different one without being asked:
``draw-later`` stops before it writes anything, and ``--replace`` takes the new lists. A
seed whose ``period`` is ``test`` is held back from every model call until the test-period
amendment of the plan is tagged.

Sheets (:func:`write_sheets`; the ``sheets`` command)
-----------------------------------------------------
For a task (``pilot``, ``check``, ``reserve`` or ``literal``) the sample list on disk is turned
into ``<task>_A1.csv`` and ``<task>_A2.csv``, ``<task>_items.jsonl`` and ``keys/<task>_key.csv``.

* A sheet starts with ``# key: value`` lines (task, annotator, seed, guide version and hash, the
  label scheme, and an empty ``sitting_start`` and ``sitting_end``), then one CSV table with
  every cell quoted. The shown columns are the fields of the entry block of ``read.py`` (drug,
  company, presentation, therapeutic category, initial posting date, type and date of update,
  availability and related information, reason for shortage), each on one line, an empty field
  as ``(blank)``; no Status, no capture date, no outcome and no reader output. The entered
  columns are empty. A shown cell that a spreadsheet would read as a formula starts with an
  apostrophe. Each annotator gets the items in a different seeded order.
* ``item_id`` is a seeded hash of the statement id; it shows neither stratum nor sample.
* The item file has the same ``item_id`` and the raw fields under the names ``read.py`` loads.
* The key (``item_id``, ids, stratum, form, period) is for the agreement script. The form comes
  from the rule reader, so annotators do not open ``keys/``.
* The sheets are built on the events table of the draw: the ``sheets`` command stops when the
  fields it reads (``events_fields_sha256`` in the manifest) are not those the lists were drawn
  on, since another table can show another presentation of the same statement.
* A sheet under the output folder that holds a label or a sitting time was filled in place. It
  is not overwritten: the command stops until the file has been moved away.
* The ``sheets`` command draws nothing and reads no exclusion (neither Appendix A nor the quoted
  phrases): under a guide revised after the draw it writes the same items with the new guide
  line.

Validator (:func:`validate_sheet`; the ``validate`` command)
------------------------------------------------------------
Checks of the guide's section 3.12 on every row (allowed values, dates that exist, start not
after end, abstention against dates, reason and certainty), a quote for every distractor role, a
note for every ``hard`` row, an interval on a ``none`` row, the sitting times in the header, and,
against the blank sheet, that no item is missing or added and no shown cell was changed. Errors
are listed by row; exit status 1 when there is any. Warnings (a quote that is not in the entry, an
interval more than ``FAR_MONTHS`` months from the Date of update, no blank sheet to compare with)
do not fail a sheet. The blank is the file ``<task>_<annotator>.csv`` under ``--out``, so a sheet
is filled in a copy kept elsewhere, not in place. A file that is not UTF-8 text is reported as
one error, with what to do.

Usage (from the repository root)::

    # the first draw and the pilot and check sheets, in one command
    PYTHONPATH=. python -m analysis.coling.audit_sample draw --sheets pilot check
        [--events analysis/coling/out/events.csv.gz | --captures external_data/fda_wayback_csv]
        [--guide analysis/coling/plan/AUDIT_GUIDE.md] [--out analysis/coling/out/audit]
        [--fixed pilot ...] [--replace literal ...] [--allow-unmatched]
    # sheets of a task from the list on disk (the literal sheets, or a sheet under a new guide)
    PYTHONPATH=. python -m analysis.coling.audit_sample sheets --task literal [--captures ...]
    # the lists drawn after the train-half outcome-audit sample
    PYTHONPATH=. python -m analysis.coling.audit_sample draw-later
        --outcome-sample analysis/coling/out/audit_outcomes/outcome_train_sample.csv [--replace]
    # check a filled sheet (the blank beside it is found by the sheet's own header)
    PYTHONPATH=. python -m analysis.coling.audit_sample validate SHEET [--blank BLANK]

``--captures`` builds the events table in memory (``corpus.build_corpus``; nothing is written and
no outcome leaves it); without it the events table on disk is read. Until the freeze run has
rewritten that table, pass ``--captures external_data/fda_wayback_csv`` to every command.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.coling import corpus as C
from analysis.coling import forms as F

SEED = 20261001
OUT = Path("analysis/coling/out/audit")
GUIDE = Path("analysis/coling/plan/AUDIT_GUIDE.md")
EVENTS = F.EVENTS
SAMPLES_DIR = "samples"
LATER_DIR = "samples_later"
KEYS_DIR = "keys"
MANIFEST = "manifest.json"
ANNOTATORS = ("A1", "A2")
PERIODS = ("train", "test")
FIRST_SAMPLES = ("pilot", "check", "reserve", "literal")
TRAIN_ONLY = ("pilot", "check", "reserve")
MAX_PER_TEMPLATE = 2
MAX_PER_EPISODE = 3
TEST_SHARE = (1, 3)  # of a literal stratum's quota, from statements dated 2023-01-01 or later
SHORTFALL_TO = {
    "pilot": ("month_year",),
    "check": ("month_year",),
    "reserve": ("month_year",),
    "literal": ("tbd", "distractor", "silent"),
}
SHORTFALL_FIRST = {"vague": ("no_date",)}  # what a stratum lacks goes to these before the others
DISTRACTOR_MARK = "with a distractor date"  # ends the part of a table cell that names such classes
OWN_ROW = ("distractor", "discontinuation")  # classes that keep their row whatever dates they carry
DATED_DISTRACTOR = "dated_distractor"  # the stratum of the row that owns no class
PHRASE_SECTIONS = ("3", "7")  # sections of the guide whose quoted phrases are kept out of samples
MIN_PHRASE_WORDS = 3
FIELD_JOIN = " || "  # between the two text fields of a statement (corpus.statement_text)
SAMPLE_HEADERS = {
    "pilot": "pilot",
    "check set": "check",
    "reserve": "reserve",
    "literal sample": "literal",
}
SAMPLE_COLUMNS = ("event_id", "statement_group_id", "thread_id")
LATER_COLUMNS = (*SAMPLE_COLUMNS, "draw_rank", "period")
STRATA_COLUMNS = ("sample", "stratum", "period", "pool", "available", "quota", "drawn")
PHRASE_COLUMNS = ("stratum", "period", "frame", "appendix_a", "equal_to_a_phrase", "removed")
EVENT_FIELDS = (
    "event_id",
    "statement_group_id",
    "thread_id",
    "generic_id",
    "episode_id",
    "listing",
    "event_date",
    "type_of_update",
    "generic_name",
    "company_name",
    "presentation",
    "status_at_statement",
    "availability_class",
    "availability_text",
    "related_text",
    "statement_text",
    "reason_for_shortage",
    "therapeutic_category",
    "initial_posting_date",
)

TASKS = {
    "pilot": "A literal reading, pilot (AUDIT_GUIDE.md sections 3 and 4)",
    "check": "A literal reading, check set (AUDIT_GUIDE.md sections 3 and 4)",
    "reserve": "A literal reading, reserve check set (AUDIT_GUIDE.md sections 3 and 4)",
    "literal": "A literal reading (AUDIT_GUIDE.md section 3)",
}
SHOWN = (
    "item_id",
    "drug",
    "company",
    "presentation",
    "therapeutic_category",
    "initial_posting_date",
    "type_of_update",
    "date_of_update",
    "availability_information",
    "related_information",
    "reason_for_shortage",
)
ENTERED = (
    "statement_type",
    "start",
    "end",
    "abstain",
    "abstain_reason",
    "certainty",
    "quote",
    "distractor_roles",
    "distractor_quotes",
    "hard",
    "note",
)
SHEET_COLUMNS = (*SHOWN, *ENTERED)
ITEM_FIELDS = {  # the harness's item keys, and the shown column each one fills
    "generic_name": "drug",
    "company_name": "company",
    "presentation": "presentation",
    "therapeutic_category": "therapeutic_category",
    "initial_posting_date": "initial_posting_date",
    "type_of_update": "type_of_update",
    "date_of_update": "date_of_update",
    "availability_information": "availability_information",
    "related_information": "related_information",
    "reason_for_shortage": "reason_for_shortage",
}
KEY_COLUMNS = (
    "item_id",
    "statement_group_id",
    "event_id",
    "thread_id",
    "sample",
    "stratum",
    "form",
    "period",
    "split",
    "n_presentations",
)
BLANK = "(blank)"

STATEMENT_TYPES = ("recovery", "next_delivery", "depletion", "discontinuation", "none")
CERTAINTY = ("asserted", "estimated", "undetermined", "no_statement")
ABSTAIN_REASONS = ("tbd", "no_date", "vague", "no_statement")
ROLES = ("expiry", "depletion", "discontinuation", "onset", "past", "other")
REASON_CERTAINTY = {
    "tbd": "undetermined",
    "no_date": "undetermined",
    "vague": "estimated",
    "no_statement": "no_statement",
}
SCHEME = {
    "statement_type": " | ".join(STATEMENT_TYPES),
    "start and end": "YYYY-MM-DD, or YYYY-MM for a whole month; both blank when abstaining",
    "abstain": "1 or 0",
    "abstain_reason": " | ".join(ABSTAIN_REASONS) + " (only when abstain is 1)",
    "certainty": " | ".join(CERTAINTY),
    "distractor_roles": "; ".join(ROLES) + " (one quote per role in distractor_quotes)",
    "hard": "1 or 0 (say why in note)",
}
FAR_MONTHS = 60
SITTING_KEYS = ("sitting_start", "sitting_end")
NOT_UTF8 = (
    "sheet: the file is not UTF-8 text; save it again as CSV UTF-8 (comma-separated), with "
    "every column as text"
)
NO_BLANK = (
    "sheet: no blank sheet to compare with (fill a copy, and keep the blank where it was "
    "written); the list of items and the shown cells were not checked"
)


@dataclass(frozen=True)
class Later:
    """One list of the later draw: how many, from which splits, and its own caps."""

    size: int
    splits: tuple[str, ...]
    per_template: int
    per_episode: int


LATER: dict[str, Later] = {
    "incontext_pool": Later(50, ("fit",), 1, 1),
    "dev_prompt": Later(60, ("dev",), MAX_PER_TEMPLATE, MAX_PER_EPISODE),
    "pair_seeds": Later(100, ("fit", "dev"), 1, MAX_PER_EPISODE),
}
PAIR_SEED_SHARE = {"month_year": 22}  # of 100; every other dated stratum gets PAIR_SEED_REST
PAIR_SEED_REST = 13
PAIR_SEEDS_LATER = ("relative",)  # strata whose seeds are statements dated 2023-01-01 or later


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def draw_key(tag: str, item: str, seed: int = SEED) -> str:
    """Position of ``item`` in the seeded draw named ``tag`` (a sha256, compared as text)."""
    return hashlib.sha256(f"{seed}\x1f{tag}\x1f{item}".encode()).hexdigest()


def shuffled(ids: Iterable[str], tag: str, seed: int = SEED) -> list[str]:
    """The ids in the seeded order of the draw ``tag``; the result ignores the input order."""
    return sorted(sorted(set(ids)), key=lambda i: draw_key(tag, i, seed))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def one_line(value: Any) -> str:
    """The value on one line, as the prompt renderer writes it."""
    return " ".join(str(value or "").split())


def iso_or_text(value: str) -> str:
    """An ISO date when the cell is one (ISO or MM/DD/YYYY), else the cell's text."""
    text = one_line(value)
    for parse in (
        lambda t: date.fromisoformat(t[:10]),
        lambda t: datetime.strptime(t, "%m/%d/%Y").date(),
    ):
        try:
            return parse(text).isoformat()
        except ValueError:
            continue
    return text


_MONTH = re.compile(
    r"(?<![a-z])(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])\.?"
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def masked_template(text: str) -> str:
    """The normalised text with month names and numbers masked."""
    return _NUMBER.sub("<n>", _MONTH.sub("<mon>", C.norm_text(text)))


def round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


# --------------------------------------------------------------------------------------------
# The guide: allocation table, Appendix A, version
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Stratum:
    """One row of the guide's table: the classes it owns, and those it takes only when the
    statement carries a distractor date."""

    name: str
    label: str
    classes: tuple[str, ...]
    with_distractor: tuple[str, ...] = ()


@dataclass(frozen=True)
class Allocation:
    """The strata of the guide's table and the quota of each stratum in each sample."""

    strata: tuple[Stratum, ...]
    quotas: dict[str, dict[str, int]]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.strata)

    @cached_property
    def by_class(self) -> dict[str, str]:
        return {c: s.name for s in self.strata for c in s.classes}

    @cached_property
    def by_class_with_distractor(self) -> dict[str, str]:
        return {c: s.name for s in self.strata for c in s.with_distractor}

    def stratum_of(self, form: str, distractor_dates: int) -> str:
        """The stratum of a statement: the row that names its class with a distractor date when
        it carries one, else the row that owns its class (so a class no row names that way, as
        a discontinuation, stays where it is)."""
        if distractor_dates > 0 and form in self.by_class_with_distractor:
            return self.by_class_with_distractor[form]
        return self.by_class[form]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def row_classes(cell: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The classes named in a cell of the allocation table: those the row owns, and those it
    takes only with a distractor date (the parts, up to a semicolon, that end with
    ``DISTRACTOR_MARK``)."""
    own: list[str] = []
    beside: list[str] = []
    for part in cell.split(";"):
        named = re.findall(r"`([a-z_]+)`", part)
        (beside if DISTRACTOR_MARK in " ".join(part.lower().split()) else own).extend(named)
    return tuple(own), tuple(beside)


def guide_allocation(text: str) -> Allocation:
    """The allocation table of the guide's section 3.2."""
    lines = text.splitlines()
    start = next(
        (
            n
            for n, line in enumerate(lines)
            if line.lstrip().startswith("|")
            and _cells(line)[:2] == ["Stratum", "Classifier classes"]
        ),
        None,
    )
    if start is None:
        raise ValueError("the guide has no allocation table (| Stratum | Classifier classes | ...)")
    header = [h.lower() for h in _cells(lines[start])[2:]]
    unknown = [h for h in header if h not in SAMPLE_HEADERS]
    if unknown or sorted(SAMPLE_HEADERS[h] for h in header) != sorted(FIRST_SAMPLES):
        raise ValueError(f"allocation table: the sample columns are {header}")
    samples = [SAMPLE_HEADERS[h] for h in header]
    strata: list[Stratum] = []
    quotas: dict[str, dict[str, int]] = {s: {} for s in samples}
    totals: dict[str, int] | None = None
    for line in lines[start + 2 :]:
        if not line.lstrip().startswith("|"):
            break
        cells = _cells(line)
        numbers = [int(re.sub(r"\D", "", c) or 0) for c in cells[2 : 2 + len(samples)]]
        if "total" in cells[0].lower():
            totals = dict(zip(samples, numbers, strict=True))
            continue
        classes, beside = row_classes(cells[1])
        if not classes and not beside:
            raise ValueError(f"allocation table: no classifier class in the row {cells[0]!r}")
        name = classes[0] if classes else DATED_DISTRACTOR
        if name in quotas[samples[0]]:
            raise ValueError(f"allocation table: two rows give the stratum {name!r}")
        strata.append(Stratum(name, cells[0], classes, beside))
        for sample, number in zip(samples, numbers, strict=True):
            quotas[sample][name] = number
    for what, named, wanted in (
        ("named", [c for s in strata for c in s.classes], F.FORM_NAMES),
        (
            f"named {DISTRACTOR_MARK}",
            [c for s in strata for c in s.with_distractor],
            [c for c in F.FORM_NAMES if c not in OWN_ROW],
        ),
    ):
        if sorted(named) != sorted(wanted):
            odd = sorted({c for c in named if named.count(c) > 1 or c not in wanted})
            raise ValueError(
                f"allocation table: the classes {what} are not the classifier's inventory "
                f"(missing {sorted(set(wanted) - set(named))}, unknown or repeated {odd})"
            )
    sums = {s: sum(quotas[s].values()) for s in samples}
    if totals is not None and totals != sums:
        raise ValueError(f"allocation table: the totals row says {totals}, the rows add to {sums}")
    return Allocation(tuple(strata), quotas)


def guide_exclusions(text: str) -> list[tuple[str, str, str]]:
    """(generic, company, statement date), normalised, of every statement the guide's Appendix A
    lists: the rows of its three-column tables; a date cell may hold several dates."""
    parts = text.split("\n## Appendix A", 1)
    if len(parts) < 2:
        return []
    out = []
    for line in parts[1].split("\n## ", 1)[0].splitlines():
        cells = _cells(line)
        if line.lstrip().startswith("|") and len(cells) == 3:
            for day in re.findall(r"\d{4}-\d{2}-\d{2}", cells[2]):
                out.append((C.norm_text(cells[0]), C.norm_text(cells[1]), day))
    return out


def guide_section(text: str, number: str) -> str:
    """The guide's section ``## <number>. ...``, up to the next heading of that level."""
    match = re.search(rf"^## {re.escape(number)}\. .*?(?=^## |\Z)", text, flags=re.M | re.S)
    return match.group(0) if match else ""


def _blocks(section: str) -> Iterable[str]:
    """The paragraphs of a section, each on one line, and its table rows one by one."""
    lines: list[str] = []
    for line in [*section.splitlines(), ""]:
        row = line.lstrip().startswith("|")
        if lines and (row or not line.strip()):
            yield " ".join(lines)
            lines = []
        if row:
            yield line.strip()
        elif line.strip():
            lines.append(line.strip())


def phrase_words(phrase: str) -> int:
    """The words of a phrase: its parts between spaces that hold a letter or a digit."""
    return sum(1 for part in phrase.split() if re.search(r"[^\W_]", part))


def guide_phrases(text: str) -> set[str]:
    """The phrases of ``MIN_PHRASE_WORDS`` words or more that the guide quotes in the sections
    ``PHRASE_SECTIONS``, normalised as the corpus builder normalises a statement text.

    A phrase is the text between two double quotation marks of one paragraph or table row. A
    paragraph or row with an odd number of quotation marks cannot be read and stops the draw.
    """
    found: set[str] = set()
    for number in PHRASE_SECTIONS:
        for block in _blocks(guide_section(text, number)):
            block = block.translate({0x201C: '"', 0x201D: '"'})
            if block.count('"') % 2:
                raise ValueError(
                    f"guide, section {number}: an odd number of quotation marks in {block[:80]!r}"
                )
            found.update(re.findall(r'"([^"]*)"', block))
    phrases = {C.norm_text(phrase) for phrase in found}
    return {phrase for phrase in phrases if phrase_words(phrase) >= MIN_PHRASE_WORDS}


def guide_version(text: str) -> str:
    """The version named in the guide's ``**Version ...`` line: ``v1 draft``, ``v1``, ``v1.1``."""
    match = re.search(r"\*\*Version (v\d+(?:\.\d+)*(?: [^,.*]+)?)", text)
    return match.group(1).strip() if match else "unknown"


def guide_stamp(text: str) -> str:
    return f"{guide_version(text)} sha256 {sha256_text(text)[:16]}"


# --------------------------------------------------------------------------------------------
# Events, display rows, the statement table
# --------------------------------------------------------------------------------------------


def load_events(path: Path = EVENTS) -> pd.DataFrame:
    """The corpus builder's events table, every cell as text."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def check_events(events: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in EVENT_FIELDS if c not in events.columns]
    if missing:
        raise ValueError(f"events table lacks {missing}")
    return events.loc[:, list(EVENT_FIELDS)].fillna("").astype(str)


def events_fields_sha256(events: pd.DataFrame) -> str:
    """sha256 of the fields this module reads (``EVENT_FIELDS``), rows sorted by event: the same
    for the table on disk and for one built in memory, whatever the order of rows and columns."""
    used = check_events(events).sort_values("event_id", ignore_index=True)
    return sha256_text(used.to_csv(index=False, lineterminator="\n"))


def at_risk_b(events: pd.DataFrame) -> pd.Series:
    """Presentations at risk under definition B when first seen (first-sight fields only)."""
    return (
        (events["listing"] == "shortage")
        & (events["status_at_statement"] == "current")
        & (events["availability_class"] != "available")
    )


def display_events(events: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """One row per statement: the event shown for it, with ``n_presentations``.

    Among the members at risk under B the one with the smallest draw key is shown; a statement
    with none shows its member with the smallest ``event_id``.
    """
    ev = check_events(events)
    pairs = zip(ev["statement_group_id"], ev["event_id"], at_risk_b(ev), strict=True)
    ev["_order"] = [
        "0" + draw_key(f"display/{group}", event, seed) if risk else "1" + event
        for group, event, risk in pairs
    ]
    ev = ev.sort_values(["statement_group_id", "_order"], ignore_index=True)
    groups = ev.groupby("statement_group_id", sort=True)
    shown = groups.head(1).drop(columns="_order").reset_index(drop=True)
    shown["n_presentations"] = groups.size().to_numpy()
    return shown


def statement_table(events: pd.DataFrame, alloc: Allocation) -> list[dict[str, Any]]:
    """One record per statement: ids of the display row, period, form, stratum, frame flags and
    the keys of the caps. ``wording`` is the normalised text alone, and ``notice`` joins generic,
    company, statement date and what the rule reader finds stated (statement type, start and
    end of the period), for :func:`labelled_twins`. No outcome field is read."""
    shown = display_events(events).set_index("statement_group_id")
    forms = F.statement_forms(events).set_index("statement_group_id")
    records = []
    for group, row in shown.iterrows():
        form = forms.loc[group]
        distractors = int(form["distractor_dates"])
        text = C.norm_text(row["statement_text"])
        company = C.norm_text(row["company_name"])
        said = (form["statement_type"], str(form["start"]), str(form["end"]))
        records.append(
            {
                "id": str(group),
                "event_id": row["event_id"],
                "thread_id": row["thread_id"],
                "event_date": row["event_date"],
                "split": form["split"],
                "period": "train" if form["split"] in F.TRAIN_SPLITS else "test",
                "form": form["form"],
                "stratum": alloc.stratum_of(form["form"], distractors),
                "stale": str(form["stale"]) == "True",
                "in_frame": bool(form["at_risk_A"]),
                "at_risk_B": bool(form["at_risk_B"]),
                "text": "\x1f".join((row["generic_id"], company, text)),
                "wording": text,
                "notice": "\x1f".join((row["generic_id"], company, row["event_date"], *said)),
                "template": masked_template(row["statement_text"]),
                "episode": row["episode_id"] or f"generic:{row['generic_id']}",
                "n_presentations": int(row["n_presentations"]),
            }
        )
    return records


def canary_keys(events: pd.DataFrame) -> set[tuple[str, str, str]]:
    """(generic, company, date) of the statement the harness's fixed test item is built on: the
    events of its generic and date whose statement text stands in the item's text fields."""
    from analysis.coling import read

    item = read.CANARY_ITEM
    inside = C.norm_text(f"{item.availability_information} || {item.related_information}")
    ev = check_events(events)
    generic = ev["generic_name"].map(C.norm_text)
    text = ev["statement_text"].map(C.norm_text)
    company = ev["company_name"].map(C.norm_text)
    return {
        (g, c, d)
        for g, c, d, t in zip(generic, company, ev["event_date"], text, strict=True)
        if g == C.norm_text(item.generic_name) and d == item.date_of_update and t and t in inside
    }


def excluded_statements(
    events: pd.DataFrame, keys: Iterable[tuple[str, str, str]]
) -> tuple[set[str], int]:
    """Statements named by (generic, company, date) keys, with every statement of the same
    generic, company and normalised text at another date; and how many keys match no event."""
    wanted = set(keys)
    ev = check_events(events)
    generic = ev["generic_name"].map(C.norm_text)
    company = ev["company_name"].map(C.norm_text)
    dated = list(zip(generic, company, ev["event_date"], strict=True))
    texts = list(zip(generic, company, ev["statement_text"].map(C.norm_text), strict=True))
    quoted = {t for k, t in zip(dated, texts, strict=True) if k in wanted}
    hit = [t in quoted for t in texts]
    return set(ev.loc[hit, "statement_group_id"]), len(wanted - set(dated))


def unmatched_keys(
    events: pd.DataFrame, keys: Iterable[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """The (generic, company, date) keys that name no event, sorted."""
    ev = check_events(events)
    generic = ev["generic_name"].map(C.norm_text)
    company = ev["company_name"].map(C.norm_text)
    return sorted(set(keys) - set(zip(generic, company, ev["event_date"], strict=True)))


def phrase_key(text: str) -> str:
    """The words of a text, in order: its normalised form without punctuation (the runs of
    letters and digits, single spaces between them). A statement and a quoted phrase are
    compared on this key, so "Estimated recovery: TBD" is the phrase "Estimated recovery TBD"."""
    return " ".join(re.findall(r"[^\W_]+", C.norm_text(text)))


def is_quoted(text: str, keys: set[str]) -> bool:
    """Whether a statement text is wholly quoted: its words are those of a quoted phrase
    (``keys`` holds the :func:`phrase_key` of every phrase), or it is made of both text fields
    (joined with ``FIELD_JOIN`` by ``corpus.statement_text``) and each field is one."""
    whole = C.norm_text(text)
    if phrase_key(whole) in keys:
        return True
    fields = [phrase_key(part) for part in whole.split(FIELD_JOIN)]
    return len(fields) > 1 and all(part in keys for part in fields)


def phrase_statements(events: pd.DataFrame, phrases: Iterable[str]) -> set[str]:
    """Statements whose whole text the guide quotes (:func:`is_quoted`), whatever the drug or
    the company. A statement that only contains a phrase is not among them."""
    ev = check_events(events)
    keys = {phrase_key(phrase) for phrase in phrases}
    quoted = ev["statement_text"].map(lambda text: is_quoted(text, keys))
    return set(ev.loc[quoted, "statement_group_id"])


def containing_a_phrase(
    table: Sequence[Mapping[str, Any]], ids: Iterable[str], phrases: Iterable[str]
) -> int:
    """How many of the statements ``ids`` contain a quoted phrase: the words of the phrase stand
    somewhere in their text, in the same order (:func:`phrase_key`). Such a statement shares a
    wording with the guide and may be drawn; the number is reported for every sample."""
    wanted = set(ids)
    quoted = sorted({f" {phrase_key(phrase)} " for phrase in phrases})
    texts = (f" {phrase_key(s['wording'])} " for s in table if s["id"] in wanted)
    return sum(any(phrase in text for phrase in quoted) for text in texts)


def phrase_counts(
    table: Sequence[Mapping[str, Any]], listed: Iterable[str], worded: Iterable[str]
) -> list[dict[str, Any]]:
    """What the rule on guide phrases does to the frame, by stratum and period: the frame
    statements, those Appendix A excludes (``listed``), those whose text equals a quoted phrase
    (``worded``), and those of them that Appendix A leaves in, which the rule removes."""
    listed, worded = set(listed), set(worded)
    counts: dict[tuple[str, str], Counter[str]] = {}
    for s in table:
        if s["in_frame"]:
            cell = counts.setdefault((s["stratum"], s["period"]), Counter())
            cell["frame"] += 1
            cell["appendix_a"] += s["id"] in listed
            cell["equal_to_a_phrase"] += s["id"] in worded
            cell["removed"] += s["id"] in worded - listed
    return [
        {"stratum": st, "period": p, **{c: counts[st, p][c] for c in PHRASE_COLUMNS[2:]}}
        for st, p in sorted(counts)
    ]


# --------------------------------------------------------------------------------------------
# Drawing under caps
# --------------------------------------------------------------------------------------------


@dataclass
class Used:
    """What every draw so far has taken: statements, and texts (generic, company, text)."""

    statements: set[str] = field(default_factory=set)
    texts: set[str] = field(default_factory=set)

    def copy(self) -> Used:
        return Used(set(self.statements), set(self.texts))


@dataclass
class Caps:
    """Items so far per masked template and per episode, with their limits."""

    per_template: int = MAX_PER_TEMPLATE
    per_episode: int = MAX_PER_EPISODE
    templates: Counter[str] = field(default_factory=Counter)
    episodes: Counter[str] = field(default_factory=Counter)

    def copy(self) -> Caps:
        return Caps(
            self.per_template, self.per_episode, self.templates.copy(), self.episodes.copy()
        )


def is_free(s: Mapping[str, Any], used: Used, caps: Caps) -> bool:
    return (
        s["id"] not in used.statements
        and s["text"] not in used.texts
        and caps.templates[s["template"]] < caps.per_template
        and caps.episodes[s["episode"]] < caps.per_episode
    )


def claim(s: Mapping[str, Any], used: Used, caps: Caps) -> None:
    used.statements.add(s["id"])
    used.texts.add(s["text"])
    caps.templates[s["template"]] += 1
    caps.episodes[s["episode"]] += 1


def take(candidates: Sequence[Mapping[str, Any]], k: int, used: Used, caps: Caps) -> list[str]:
    """Up to ``k`` statements from the top of ``candidates`` that the caps allow."""
    got: list[str] = []
    for s in candidates:
        if len(got) >= k:
            break
        if is_free(s, used, caps):
            claim(s, used, caps)
            got.append(s["id"])
    return got


def capacity(candidates: Sequence[Mapping[str, Any]], used: Used, caps: Caps) -> int:
    """How many of ``candidates`` a draw could take now, alone, under the caps."""
    return len(take(candidates, len(candidates), used.copy(), caps.copy()))


def ordered(pool: Iterable[Mapping[str, Any]], tag: str) -> list[Mapping[str, Any]]:
    return sorted(pool, key=lambda s: draw_key(tag, s["id"]))


@dataclass
class Drawn:
    """The lists of one draw (statement ids, sorted) and its stratum table."""

    lists: dict[str, list[str]]
    strata: list[dict[str, Any]]
    ranks: dict[str, dict[str, int]] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)


def from_test_period(quota: int) -> int:
    """How much of a literal stratum's quota comes from the test period: one third, rounded."""
    return round_half_up(quota * TEST_SHARE[0], TEST_SHARE[1])


def top_up(
    got: dict[str, list[str]],
    cands: Mapping[str, Sequence[Mapping[str, Any]]],
    target: int,
    used: Used,
    caps: Caps,
) -> int:
    """Bring one stratum to ``target`` items and return how many it has.

    ``got`` and ``cands`` are keyed by period. With one period the stratum takes what it can.
    With two, the train period gives the target less its test part, the test period the rest
    (so more when the train period falls short), and the train period makes up what the test
    period cannot give.
    """

    def have() -> int:
        return sum(len(ids) for ids in got.values())

    def more(period: str, k: int) -> None:
        if k > 0:
            got[period] += take(cands[period], k, used, caps)

    if set(got) == {"train"}:
        more("train", target - have())
        return have()
    more("train", target - from_test_period(target) - len(got["train"]))
    more("test", target - have())
    more("train", target - have())
    return have()


def draw_first(
    table: Sequence[Mapping[str, Any]],
    alloc: Allocation,
    excluded: Iterable[str] = (),
    fixed: Mapping[str, Sequence[str]] | None = None,
) -> Drawn:
    """Pilot, check set, reserve and literal sample, in that order (see the module docstring).

    ``fixed`` gives the statement ids of samples that are kept as they are: they count against
    the caps and are not drawn again.
    """
    fixed = fixed or {}
    by_id = {s["id"]: s for s in table}
    barred = set(excluded)
    frame = [s for s in table if s["in_frame"] and s["id"] not in barred]
    used, caps = Used(), Caps()
    lists: dict[str, list[str]] = {}
    strata: list[dict[str, Any]] = []
    for sample in FIRST_SAMPLES:
        if sample in fixed:
            unknown = sorted(set(fixed[sample]) - set(by_id))
            if unknown:
                raise ValueError(f"fixed sample {sample}: not in the events table: {unknown[:5]}")
            for i in fixed[sample]:
                claim(by_id[i], used, caps)
            lists[sample] = sorted(fixed[sample])
            continue
        periods = ("train",) if sample in TRAIN_ONLY else PERIODS
        quotas = alloc.quotas[sample]
        cands = {
            st: {
                p: ordered(
                    (s for s in frame if s["stratum"] == st and s["period"] == p),
                    f"{sample}/{st}/{p}",
                )
                for p in periods
            }
            for st in alloc.names
        }
        left = {
            st: {
                p: sum(s["id"] not in used.statements and s["text"] not in used.texts for s in pool)
                for p, pool in cands[st].items()
            }
            for st in alloc.names
        }
        free = {
            st: {p: capacity(pool, used, caps) for p, pool in cands[st].items()}
            for st in alloc.names
        }
        got: dict[str, dict[str, list[str]]] = {st: {p: [] for p in periods} for st in alloc.names}
        rarest_first = sorted(
            alloc.names, key=lambda st: (sum(left[st].values()), alloc.names.index(st))
        )
        lacking = {
            st: quotas[st] - top_up(got[st], cands[st], quotas[st], used, caps)
            for st in rarest_first
            if quotas[st] > 0
        }
        short = 0
        for st, missing in lacking.items():
            for first in SHORTFALL_FIRST.get(st, ()):  # the stratum's own recipients come first
                if missing > 0 and first in got:
                    before = sum(len(ids) for ids in got[first].values())
                    after = top_up(got[first], cands[first], before + missing, used, caps)
                    missing -= after - before
            short += missing
        turn, misses = 0, 0
        recipients = SHORTFALL_TO[sample]
        while short > 0 and misses < len(recipients):
            st = recipients[turn % len(recipients)]
            turn += 1
            before = sum(len(ids) for ids in got[st].values())
            if top_up(got[st], cands[st], before + 1, used, caps) > before:
                short, misses = short - 1, 0
            else:
                misses += 1
        lists[sample] = sorted(i for st in alloc.names for ids in got[st].values() for i in ids)
        for st in alloc.names:
            for p in periods:
                quota = quotas[st]
                if len(periods) > 1:
                    quota = (
                        from_test_period(quota) if p == "test" else quota - from_test_period(quota)
                    )
                strata.append(
                    {
                        "sample": sample,
                        "stratum": st,
                        "period": p,
                        "pool": left[st][p],
                        "available": free[st][p],
                        "quota": quota,
                        "drawn": len(got[st][p]),
                    }
                )
    return Drawn(lists, strata)


def in_turn(
    cands: Mapping[str, Sequence[Mapping[str, Any]]], size: int, used: Used, caps: Caps
) -> list[str]:
    """Up to ``size`` statements, one from each stratum in turn, the smallest stratum first."""
    order = sorted(cands, key=lambda st: (len(cands[st]), st))
    got: list[str] = []
    progress = True
    while len(got) < size and progress:
        progress = False
        for st in order:
            if len(got) < size:
                one = take(cands[st], 1, used, caps)
                got += one
                progress = progress or bool(one)
    return got


def labelled_twins(
    table: Sequence[Mapping[str, Any]], labelled: Iterable[str]
) -> dict[str, set[str]]:
    """Statements that are not items of the labelling samples but read like one, by reason.

    ``same_wording``: the whole text is that of an item, word for word and punctuation aside
    (:func:`phrase_key`), whatever the drug or the company (a text with no word is no wording
    and is not compared). ``same_notice``: the same
    generic, company and statement date as an item, with the same statement type and the same
    period in the rule reading, whatever the spelling: the item's notice on another
    presentation. A statement of both kinds is counted under the first.
    """
    by_id = {s["id"]: s for s in table}
    read = [by_id[i] for i in set(labelled) if i in by_id]
    items = {s["id"] for s in read}
    wordings = {phrase_key(s["wording"]) for s in read} - {""}
    notices = {s["notice"] for s in read}
    rest = [s for s in table if s["id"] not in items]
    worded = {s["id"] for s in rest if phrase_key(s["wording"]) in wordings}
    return {
        "same_wording": worded,
        "same_notice": {s["id"] for s in rest if s["notice"] in notices} - worded,
    }


def draw_later(
    table: Sequence[Mapping[str, Any]],
    alloc: Allocation,
    excluded: Iterable[str],
    earlier: Iterable[str],
    labelled: Iterable[str] = (),
) -> Drawn:
    """The in-context pool, the dev prompt items and the minimal-pair seeds, in that order.

    ``excluded`` are the statements of the guide's Appendix A and those whose text equals a
    phrase the guide quotes; ``earlier`` are the statements of the first draw and of the
    train-half outcome-audit sample. Both are left out, with every statement of the same
    generic, company and normalised text, and each list leaves out the ones before it.
    ``labelled`` are the statements of the first draw, which the annotators read: the
    statements that read like one of them (:func:`labelled_twins`) are left out in the same way.

    The lists hold train-period statements of the splits of ``LATER``, except the pair seeds of
    the strata ``PAIR_SEEDS_LATER``, which are statements dated 2023-01-01 or later (text only).
    """
    by_id = {s["id"]: s for s in table}
    twins = labelled_twins(table, labelled)
    barred = set(excluded) | set(earlier) | twins["same_wording"] | twins["same_notice"]
    used = Used(set(barred), {by_id[i]["text"] for i in barred if i in by_id})
    dated = [s.name for s in alloc.strata if set(s.classes) & set(F.DATED_FORMS)]
    lists: dict[str, list[str]] = {}
    ranks: dict[str, dict[str, int]] = {}
    strata: list[dict[str, Any]] = []

    def later_seed(s: Mapping[str, Any]) -> bool:
        return s["stratum"] in PAIR_SEEDS_LATER

    def in_period(name: str, s: Mapping[str, Any]) -> bool:
        """Whether the statement is of the period the list takes its stratum from."""
        if name == "pair_seeds" and later_seed(s):
            return s["period"] == "test"
        return s["split"] in LATER[name].splits

    def pool_of(name: str, keep: Any, key: str) -> dict[str, list[Mapping[str, Any]]]:
        """The candidates of a list by stratum, in seeded order, without what is already used."""
        rows = [
            s
            for s in table
            if s["in_frame"]
            and in_period(name, s)
            and keep(s)
            and s["id"] not in used.statements
            and s["text"] not in used.texts
        ]
        return {
            st: ordered((s for s in rows if s[key] == st), f"{name}/{st}")
            for st in sorted({s[key] for s in rows})
        }

    def record(name: str, cands: Mapping[str, Sequence], got: list[str], quota: Any) -> None:
        lists[name] = sorted(got)
        ranks[name] = {i: n for n, i in enumerate(got, start=1)}
        count = Counter(by_id[i]["form" if name == "incontext_pool" else "stratum"] for i in got)
        for st, pool in cands.items():
            later = name == "pair_seeds" and st in PAIR_SEEDS_LATER
            strata.append(
                {
                    "sample": name,
                    "stratum": st,
                    "period": "test" if later else "+".join(LATER[name].splits),
                    "pool": len(pool),
                    "available": "",
                    "quota": quota(st),
                    "drawn": count[st],
                }
            )

    spec = LATER["incontext_pool"]
    cands = pool_of(
        "incontext_pool",
        lambda s: s["at_risk_B"] and s["form"] in F.DATED_FORMS and not s["stale"],
        "form",
    )
    got = in_turn(cands, spec.size, used, Caps(spec.per_template, spec.per_episode))
    record("incontext_pool", cands, got, lambda st: "")

    spec = LATER["dev_prompt"]
    cands = pool_of("dev_prompt", lambda s: s["at_risk_B"], "stratum")
    got = in_turn(cands, spec.size, used, Caps(spec.per_template, spec.per_episode))
    record("dev_prompt", cands, got, lambda st: "")

    spec = LATER["pair_seeds"]
    cands = pool_of("pair_seeds", lambda s: s["stratum"] in dated and not s["stale"], "stratum")
    caps = Caps(spec.per_template, spec.per_episode)
    quota = {st: PAIR_SEED_SHARE.get(st, PAIR_SEED_REST) for st in dated}
    taken = {
        st: take(cands.get(st, []), quota[st], used, caps) for st in sorted(quota, key=dated.index)
    }
    short = spec.size - sum(len(v) for v in taken.values())
    taken["month_year"] = taken.get("month_year", []) + take(
        cands.get("month_year", []), max(short, 0), used, caps
    )
    got = [i for st in dated for i in taken.get(st, [])]
    record("pair_seeds", cands, got, lambda st: quota.get(st, 0))
    notes = {
        f"frame_statements_left_out_{k}": sum(by_id[i]["in_frame"] for i in v)
        for k, v in twins.items()
    }
    return Drawn(lists, strata, ranks, notes)


# --------------------------------------------------------------------------------------------
# Files: lists, the manifest, CSV sheets
# --------------------------------------------------------------------------------------------


def write_bytes(root: Path, name: str, data: bytes) -> str:
    """Write ``data`` under ``root`` only, and return its sha256."""
    base = root.resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"{name} is outside {root}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def write_text(root: Path, name: str, text: str) -> str:
    return write_bytes(root, name, text.encode("utf-8"))


def plain_csv(columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> str:
    """A CSV read by code: a header row, minimal quoting, ``\\n`` line ends."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def list_rows(
    ids: Iterable[str],
    by_id: Mapping[str, Mapping[str, Any]],
    ranks: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": by_id[i]["event_id"],
            "statement_group_id": i,
            "thread_id": by_id[i]["thread_id"],
            "draw_rank": (ranks or {}).get(i, ""),
            "period": by_id[i]["period"],
        }
        for i in sorted(ids)
    ]


def ids_sha256(ids: Iterable[str]) -> str:
    """sha256 of the sorted statement ids, one per line: the sample whatever row is shown."""
    return sha256_text("".join(f"{i}\n" for i in sorted(ids)))


def update_manifest(root: Path, section: str, entry: Mapping[str, Any]) -> None:
    """Replace one section of ``manifest.json`` and leave the others as they are."""
    path = root / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    manifest["about"] = "Samples, blank sheets, submitted sheets and gold of the literal task."
    manifest["seed"] = SEED
    manifest[section] = entry
    write_text(root, MANIFEST, json.dumps(manifest, indent=1, sort_keys=True) + "\n")


def guarded(value: str) -> str:
    """A cell that a spreadsheet would take for a formula gets a leading apostrophe."""
    return "'" + value if value[:1] in tuple("=+-@") else value


def unguarded(value: str) -> str:
    return value[1:] if value[:1] == "'" and value[1:2] in tuple("=+-@") else value


def sheet_text(
    columns: Sequence[str], rows: Iterable[Mapping[str, Any]], meta: Iterable[tuple[str, Any]]
) -> str:
    """A sheet for people: ``# key: value`` lines, then a table with every cell quoted and
    formula-like cells guarded."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_ALL)
    for key, value in meta:
        writer.writerow([f"# {key}: {value}".rstrip()])
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow([guarded(str(row.get(c, ""))) for c in columns])
    return buf.getvalue()


def parse_sheet(text: str) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    """Split a sheet into its ``# key: value`` lines, in order, and its rows (cells stripped).

    The comment lines are the rows above the header row; a spreadsheet may have spread one over
    several cells. A ``#`` further down is part of an entry.
    """
    table = list(csv.reader(io.StringIO(text.removeprefix(chr(0xFEFF)), newline="")))
    meta: list[tuple[str, str]] = []
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for line in table:
        if not any(c.strip() for c in line):
            continue
        first = next(c.strip() for c in line if c.strip())
        if not header and first.startswith("#"):
            joined = " ".join(c.strip() for c in line if c.strip()).lstrip("# ")
            key, _, value = joined.partition(":")
            meta.append((key.strip(), value.strip()))
        elif not header:
            header = [c.strip() for c in line]
        else:
            padded = [*line, *([""] * len(header))]
            rows.append({h: padded[n].strip() for n, h in enumerate(header) if h})
    return meta, rows


def read_sheet(path: Path) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    return parse_sheet(path.read_text(encoding="utf-8-sig"))


def meta_value(meta: Iterable[tuple[str, str]], key: str) -> str:
    return next((v for k, v in meta if k == key), "")


# --------------------------------------------------------------------------------------------
# Sheets, item files and keys
# --------------------------------------------------------------------------------------------


def item_id(statement: str, seed: int = SEED) -> str:
    """The id shown for a statement: a seeded hash, so it shows neither stratum nor sample."""
    return "I" + draw_key("item", statement, seed)[:10]


def harness_item(row: Mapping[str, str], shown_id: str) -> dict[str, str]:
    """The display row as an item of the reading harness (raw fields; no outcome, no Status)."""
    return {
        "item_id": shown_id,
        "generic_name": row["generic_name"],
        "company_name": row["company_name"],
        "presentation": row["presentation"],
        "date_of_update": row["event_date"],
        "therapeutic_category": row["therapeutic_category"],
        "initial_posting_date": iso_or_text(row["initial_posting_date"]),
        "type_of_update": row["type_of_update"].capitalize(),
        "availability_information": row["availability_text"],
        "related_information": row["related_text"],
        "reason_for_shortage": row["reason_for_shortage"],
    }


def shown_cells(item: Mapping[str, str]) -> dict[str, str]:
    """The shown columns of a sheet row: the harness item on one line per field, an empty field
    as ``(blank)``; the anchor is always an ISO date."""
    cells = {"item_id": item["item_id"]}
    for key, column in ITEM_FIELDS.items():
        cells[column] = one_line(item[key]) or BLANK
    return cells


@dataclass
class SheetSet:
    """The files of one task, by name, ready to be written."""

    files: dict[str, str]
    key: str
    n_items: int


def build_sheets(
    task: str,
    statements: Sequence[str],
    events: pd.DataFrame,
    table: Sequence[Mapping[str, Any]],
    guide: str,
) -> SheetSet:
    """Blank sheets for A1 and A2, the harness item file and the key of one task."""
    by_id = {s["id"]: s for s in table}
    missing = sorted(set(statements) - set(by_id))
    if missing:
        raise ValueError(f"{task}: statements not in the events table: {missing[:5]}")
    rows = check_events(events).set_index("event_id")
    items: dict[str, dict[str, str]] = {}
    keys: list[dict[str, Any]] = []
    for statement in sorted(statements):
        s = by_id[statement]
        shown_id = item_id(statement)
        if shown_id in items:
            raise ValueError(f"{task}: two statements share the item id {shown_id}")
        items[shown_id] = harness_item(rows.loc[s["event_id"]], shown_id)
        keys.append(
            {
                "item_id": shown_id,
                "statement_group_id": statement,
                "event_id": s["event_id"],
                "thread_id": s["thread_id"],
                "sample": task,
                "stratum": s["stratum"],
                "form": s["form"],
                "period": s["period"],
                "split": s["split"],
                "n_presentations": s["n_presentations"],
            }
        )
    if task in TRAIN_ONLY and any(k["period"] != "train" for k in keys):
        raise ValueError(f"{task}: a statement dated 2023-01-01 or later is in a train-only sample")
    files: dict[str, str] = {}
    for annotator in ANNOTATORS:
        order = shuffled(items, f"{task}/order/{annotator}")
        meta = [
            ("task", TASKS[task]),
            ("sheet", task),
            ("annotator", annotator),
            ("seed", SEED),
            ("guide", guide_stamp(guide)),
            ("items", len(order)),
            *((f"values of {column}", values) for column, values in SCHEME.items()),
            ("sitting_start", ""),
            ("sitting_end", ""),
        ]
        files[f"{task}_{annotator}.csv"] = sheet_text(
            SHEET_COLUMNS, (shown_cells(items[i]) for i in order), meta
        )
    ordered_items = [items[i] for i in sorted(items)]
    files[f"{task}_items.jsonl"] = "".join(
        json.dumps(item, ensure_ascii=False) + "\n" for item in ordered_items
    )
    key = plain_csv(KEY_COLUMNS, sorted(keys, key=lambda k: k["item_id"]))
    return SheetSet(files, key, len(items))


# --------------------------------------------------------------------------------------------
# Labels: parsing and the checks of the guide's section 3.12
# --------------------------------------------------------------------------------------------

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_ONLY = re.compile(r"^\d{4}-\d{2}$")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap])?\.?m?\.?$", re.IGNORECASE)


def month_end(year: int, month: int) -> date:
    first_of_next = date(year + month // 12, month % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def parse_day(text: str, *, end: bool) -> date:
    """A ``start`` or ``end`` cell: ``YYYY-MM-DD``, or ``YYYY-MM`` for the first day (start) or
    the last day (end) of that month. Raises ValueError with the reason."""
    if _DAY.match(text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ValueError(f"{text} is not a calendar date") from None
    if _MONTH_ONLY.match(text):
        year, month = int(text[:4]), int(text[5:])
        if not 1 <= month <= 12 or year < 1:
            raise ValueError(f"{text} is not a calendar month")
        return month_end(year, month) if end else date(year, month, 1)
    raise ValueError(f"{text!r} is not YYYY-MM-DD or YYYY-MM")


def split_list(cell: str) -> list[str]:
    """A semicolon list; a quote list may use ``|`` instead, for a quote that holds a semicolon.
    A bar typed with the backslash that the guide's table source shows before it counts the same.
    """
    separator = "|" if "|" in cell else ";"
    parts = (p.strip().removesuffix("\\").strip() for p in cell.split(separator))
    return [p for p in parts if p]


def month_offset(day: date, anchor: date) -> int:
    """``12 x (year(d) - year(a)) + (month(d) - month(a))`` (the guide's section 8.1)."""
    return 12 * (day.year - anchor.year) + (day.month - anchor.month)


@dataclass(frozen=True)
class Label:
    """One row of labels, as entered, with the dates read and the derived columns."""

    item_id: str
    statement_type: str
    abstain: bool
    start: date | None
    end: date | None
    abstain_reason: str
    certainty: str
    quote: str
    distractor_roles: tuple[str, ...]
    distractor_quotes: tuple[str, ...]
    hard: bool
    note: str
    anchor: date | None = None

    @property
    def interval(self) -> tuple[date, date] | None:
        return (self.start, self.end) if self.start and self.end else None

    @property
    def stale(self) -> bool:
        """The interval ends before the Date of update (false when the row abstains)."""
        return bool(self.end and self.anchor and self.end < self.anchor)

    def offsets(self) -> dict[str, int | None]:
        """Month and day offsets of start and end from the anchor (None when abstaining)."""
        out: dict[str, int | None] = {}
        for name, day in (("start", self.start), ("end", self.end)):
            known = day is not None and self.anchor is not None
            out[f"{name}_offset_m"] = month_offset(day, self.anchor) if known else None
            out[f"{name}_offset_d"] = (day - self.anchor).days if known else None
        return out

    def entered(self) -> dict[str, str]:
        """The entered columns, with dates written in full."""
        return {
            "statement_type": self.statement_type,
            "start": self.start.isoformat() if self.start else "",
            "end": self.end.isoformat() if self.end else "",
            "abstain": "1" if self.abstain else "0",
            "abstain_reason": self.abstain_reason,
            "certainty": self.certainty,
            "quote": self.quote,
            "distractor_roles": "; ".join(self.distractor_roles),
            "distractor_quotes": " | ".join(self.distractor_quotes),
            "hard": "1" if self.hard else "0",
            "note": self.note,
        }


def read_label(row: Mapping[str, str]) -> tuple[Label | None, list[str], list[str]]:
    """The label of one sheet row, with what is wrong with it and what only looks odd.

    The label is None when a coded cell or a date cannot be read.
    """
    get = {c: unguarded((row.get(c) or "").strip()) for c in SHEET_COLUMNS}
    if not any(get[c] for c in ENTERED):
        return None, ["the row is not filled"], []
    errors: list[str] = []
    warnings: list[str] = []
    coded = (
        ("statement_type", STATEMENT_TYPES, True),
        ("abstain", ("0", "1"), True),
        ("certainty", CERTAINTY, True),
        ("abstain_reason", ABSTAIN_REASONS, False),
        ("hard", ("0", "1"), False),
    )
    for column, allowed, required in coded:
        if not get[column]:
            if required:
                errors.append(f"{column} is missing")
        elif get[column] not in allowed:
            errors.append(f"{column} {get[column]!r} is not one of {', '.join(allowed)}")
    roles = [r.lower() for r in split_list(get["distractor_roles"])]
    errors += [
        f"distractor role {r!r} is not one of {', '.join(ROLES)}" for r in roles if r not in ROLES
    ]
    days: dict[str, date | None] = {"start": None, "end": None}
    for name in days:
        if get[name]:
            try:
                days[name] = parse_day(get[name], end=name == "end")
            except ValueError as problem:
                errors.append(f"{name}: {problem}")
    if errors:
        return None, errors, warnings
    start, end = days["start"], days["end"]
    statement, certainty, reason = get["statement_type"], get["certainty"], get["abstain_reason"]
    abstain = get["abstain"] == "1"
    if abstain and (get["start"] or get["end"]):
        errors.append("abstain is 1 but a date is given")
    if not abstain and not (start and end):
        errors.append("abstain is 0 but start or end is missing")
    if start and end and start > end:
        errors.append("start is after end")
    if (statement == "none") != (certainty == "no_statement"):
        errors.append("statement_type none and certainty no_statement go together")
    if statement == "none" and not abstain:
        errors.append("statement_type is none but the row does not abstain")
    if certainty == "undetermined" and (start or end):
        errors.append("certainty is undetermined but an interval is given")
    if abstain and not reason:
        errors.append("abstain_reason is missing")
    if not abstain and reason:
        errors.append("abstain_reason is given but the row does not abstain")
    if abstain and reason and REASON_CERTAINTY[reason] != certainty:
        errors.append(f"abstain_reason {reason} needs certainty {REASON_CERTAINTY[reason]}")
    quotes = split_list(get["distractor_quotes"])
    if len(quotes) != len(roles):
        errors.append(f"{len(roles)} distractor roles but {len(quotes)} distractor quotes")
    if get["hard"] == "1" and not get["note"]:
        errors.append("hard is 1 but note is empty")
    anchor = None
    try:
        anchor = date.fromisoformat(get["date_of_update"])
    except ValueError:
        errors.append(f"date_of_update {get['date_of_update']!r} is not an ISO date")
    entry = C.norm_text(f"{get['availability_information']} || {get['related_information']}")
    for name, words in (
        ("quote", [get["quote"]] if get["quote"] else []),
        ("distractor quote", quotes),
    ):
        warnings += [
            f"{name} {w!r} is not in the entry" for w in words if C.norm_text(w) not in entry
        ]
    if anchor:
        far = [n for n, d in days.items() if d and abs(month_offset(d, anchor)) > FAR_MONTHS]
        warnings += [f"{n} is more than {FAR_MONTHS} months from the Date of update" for n in far]
    label = Label(
        item_id=get["item_id"],
        statement_type=statement,
        abstain=abstain,
        start=start,
        end=end,
        abstain_reason=reason,
        certainty=certainty,
        quote=get["quote"],
        distractor_roles=tuple(roles),
        distractor_quotes=tuple(quotes),
        hard=get["hard"] == "1",
        note=get["note"],
        anchor=anchor,
    )
    return (None if errors else label), errors, warnings


def clock(text: str) -> int | None:
    """Minutes after midnight of an ``HH:MM`` cell (seconds and am or pm tolerated)."""
    match = _TIME.match(text.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    half = (match.group(3) or "").lower()
    if half:
        hour = hour % 12 + (12 if half == "p" else 0)
    return hour * 60 + minute if hour < 24 and minute < 60 else None


def sittings(meta: Iterable[tuple[str, str]]) -> tuple[int | None, list[str]]:
    """Minutes of labelling from the ``sitting_start`` and ``sitting_end`` lines, in order."""
    marks = [(k, clock(v), v) for k, v in meta if k in SITTING_KEYS and v]
    errors = [f"header: {k} {v!r} is not a time (HH:MM)" for k, t, v in marks if t is None]
    starts = [t for k, t, _ in marks if k == "sitting_start" and t is not None]
    ends = [t for k, t, _ in marks if k == "sitting_end" and t is not None]
    if errors:
        return None, errors
    if not starts or len(starts) != len(ends):
        return None, ["header: give one sitting_start and one sitting_end (HH:MM) for each sitting"]
    if any(e <= s for s, e in zip(starts, ends, strict=True)):
        return None, ["header: a sitting_end is not after its sitting_start"]
    return sum(e - s for s, e in zip(starts, ends, strict=True)), []


@dataclass
class Checked:
    """A sheet after validation: labels by item id, errors and warnings by row, minutes."""

    labels: dict[str, Label]
    errors: list[str]
    warnings: list[str]
    minutes: int | None
    meta: list[tuple[str, str]]
    rows: list[dict[str, str]]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_sheet(
    meta: list[tuple[str, str]],
    rows: list[dict[str, str]],
    blank: Sequence[Mapping[str, str]] | None = None,
) -> Checked:
    """Check a filled sheet; ``blank`` is the rows of the sheet as it was handed out."""
    errors: list[str] = []
    warnings: list[str] = []
    labels: dict[str, Label] = {}
    missing = [c for c in SHEET_COLUMNS if rows and c not in rows[0]]
    if missing or not rows:
        problem = f"columns missing: {', '.join(missing)}" if missing else "the sheet has no rows"
        if rows and any(";" in name for name in rows[0]):
            problem += " (the file looks semicolon-separated; save it comma-separated)"
        return Checked({}, [f"sheet: {problem}"], [], None, meta, rows)
    minutes, problems = sittings(meta)
    errors += problems
    seen: Counter[str] = Counter(r["item_id"] for r in rows)
    handed = {unguarded(b["item_id"]): b for b in blank} if blank is not None else None
    for n, row in enumerate(rows, start=1):
        where = f"row {n} ({row['item_id'] or 'no item_id'})"
        if not row["item_id"] or seen[row["item_id"]] > 1:
            errors.append(f"{where}: item_id is missing or repeated")
            continue
        if handed is not None:
            if row["item_id"] not in handed:
                errors.append(f"{where}: this item is not in the blank sheet")
                continue
            changed = [
                c
                for c in SHOWN
                if unguarded(row[c]) != unguarded((handed[row["item_id"]].get(c) or "").strip())
            ]
            if changed:
                errors.append(
                    f"{where}: shown cells changed ({', '.join(changed)}); "
                    "import every column as text and do not edit shown cells"
                )
        label, wrong, odd = read_label(row)
        errors += [f"{where}: {e}" for e in wrong]
        warnings += [f"{where}: {w}" for w in odd]
        if label is not None:
            labels[row["item_id"]] = label
    if handed is not None:
        absent = sorted(set(handed) - set(seen))
        errors += [f"sheet: item {i} of the blank sheet is missing" for i in absent]
    return Checked(labels, errors, warnings, minutes, meta, rows)


def blank_beside(sheet: Path, meta: Iterable[tuple[str, str]], root: Path = OUT) -> Path | None:
    """The blank sheet a filled one came from, by the sheet's own header lines."""
    meta = list(meta)
    task, annotator = meta_value(meta, "sheet"), meta_value(meta, "annotator")
    path = root / f"{task}_{annotator}.csv"
    if task in TASKS and annotator in ANNOTATORS and path.is_file():
        return None if path.resolve() == sheet.resolve() else path
    return None


def holds_labels(path: Path) -> bool:
    """Whether the sheet at ``path`` was filled in: a sitting time or any entered cell (a file
    that cannot be read as a sheet counts as filled)."""
    if not path.is_file():
        return False
    try:
        meta, rows = read_sheet(path)
    except UnicodeDecodeError:
        return True
    timed = any(value for key, value in meta if key in SITTING_KEYS)
    return timed or any(row.get(c) for row in rows for c in ENTERED)


def check_file(sheet: Path, blank: Path | None = None, root: Path = OUT) -> Checked:
    """Validate the sheet at ``sheet`` against its blank (given, or found under ``root``)."""
    try:
        meta, rows = read_sheet(sheet)
    except UnicodeDecodeError:
        return Checked({}, [NOT_UTF8], [], None, [], [])
    blank = blank or blank_beside(sheet, meta, root)
    checked = validate_sheet(meta, rows, read_sheet(blank)[1] if blank else None)
    if blank is None:
        checked.warnings.append(NO_BLANK)
    return checked


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


@dataclass
class Inputs:
    """What every command reads: events, the guide, and what the two give."""

    events: pd.DataFrame
    source: dict[str, str]
    guide: str
    alloc: Allocation
    table: list[dict[str, Any]]
    excluded: set[str]
    notes: dict[str, Any]
    unmatched: list[tuple[str, str, str]] = field(default_factory=list)
    phrase_rule: list[dict[str, Any]] = field(default_factory=list)
    phrases: set[str] = field(default_factory=set)


def load_inputs(args: argparse.Namespace, exclusions: bool = True) -> Inputs:
    """Events, guide, allocation and statement table; and, for a draw, the exclusions. A command
    that draws nothing (``sheets``) passes ``exclusions=False`` and reads none of them, so that
    it does not depend on Appendix A or on the phrases of a guide revised after the draw."""
    if args.captures:
        events = F.events_from_captures(args.captures)
        source = {"events": f"built in memory from {args.captures.as_posix()}"}
    else:
        events = load_events(args.events)
        source = {
            "events": args.events.as_posix(),
            "events_sha256": F.sha16(args.events.read_bytes()),
        }
    guide = args.guide.read_text(encoding="utf-8")
    alloc = guide_allocation(guide)
    source |= {
        "events_fields_sha256": events_fields_sha256(events),
        "guide": guide_stamp(guide),
        "forms_sha256": F.sha16(Path(F.__file__).read_bytes()),
        "rules_sha256": F.sha16(Path(F.rules.__file__).read_bytes()),
        "audit_sample_sha256": F.sha16(Path(__file__).read_bytes()),
    }
    table = statement_table(events, alloc)
    if not exclusions:
        return Inputs(events, source, guide, alloc, table, set(), {})
    listed = set(guide_exclusions(guide))
    canary = canary_keys(events)
    excluded, unmatched = excluded_statements(events, listed | canary)
    phrases = guide_phrases(guide)
    worded = phrase_statements(events, phrases)
    notes = {
        "appendix_a_rows": len(listed),
        "appendix_a_rows_matching_no_event": unmatched,
        "fixed_test_item_statements": len(canary),
        "fixed_test_item_in_appendix_a": bool(canary) and canary <= listed,
        "excluded_statements": len(excluded),
        "guide_phrases": len(phrases),
        "statements_equal_to_a_guide_phrase": len(worded),
        "excluded_statements_with_guide_phrases": len(excluded | worded),
    }
    return Inputs(
        events,
        source,
        guide,
        alloc,
        table,
        excluded | worded,
        notes,
        unmatched_keys(events, listed),
        phrase_counts(table, excluded, worded),
        phrases,
    )


def require_exclusions(inputs: Inputs, allow: bool) -> None:
    """Stop a draw whose exclusions are incomplete: a row of Appendix A that names no event, or
    a fixed test item of the harness that is on no statement."""
    problems = [f"Appendix A row matches no event: {', '.join(key)}" for key in inputs.unmatched]
    if not inputs.notes["fixed_test_item_statements"]:
        problems.append("the fixed test item of the harness (read.CANARY_ITEM) is on no statement")
    for line in problems:
        print(f"{'warning' if allow else 'error'}: {line}")
    if problems and not allow:
        raise SystemExit(
            "the exclusions are incomplete, so a statement the guide quotes could be drawn: "
            "correct Appendix A, or pass --allow-unmatched to draw anyway"
        )


def require_same_lists(
    root: Path, drawn: Drawn, replace: Iterable[str], sheets: Iterable[str]
) -> None:
    """Stop a draw that would put other statements in a list that is on disk, unless the sample
    is named under ``--replace`` (a list kept with ``--fixed`` is the one on disk, so it never
    differs). A replaced list whose sheets are on disk needs them written again in the same
    command."""
    moved = [
        name
        for name, ids in drawn.lists.items()
        if (path := root / SAMPLES_DIR / f"sample_{name}.csv").is_file()
        and read_list(path) != sorted(ids)
    ]
    unasked = " ".join(name for name in moved if name not in set(replace))
    if unasked:
        raise SystemExit(
            f"the draw would change the list on disk of: {unasked} (the guide or the events "
            f"table is not the one of the last draw). Nothing was written. Keep a list that a "
            f"sheet or a later draw rests on with --fixed {unasked}; take the new one with "
            f"--replace {unasked}"
        )
    stale = " ".join(
        name
        for name in moved
        if name not in set(sheets) and (root / f"{name}_{ANNOTATORS[0]}.csv").is_file()
    )
    if stale:
        raise SystemExit(
            f"the sheets on disk of: {stale} are those of the list that is replaced. Nothing "
            f"was written. Add --sheets {stale} to write them again with the new list"
        )


def print_phrase_rule(rows: Sequence[Mapping[str, Any]]) -> None:
    """Counts of frame statements, for the strata that hold a statement equal to a guide phrase:
    ``removed`` are those the rule takes out beyond Appendix A."""
    hit = [row for row in rows if row["equal_to_a_phrase"]]
    print(f"guide phrases: frame statements whose whole text equals one ({len(hit)} cells)")
    print(f"  {'stratum':16s} {'period':8s} " + " ".join(f"{c:>17s}" for c in PHRASE_COLUMNS[2:]))
    for row in hit:
        cells = " ".join(f"{row[c]!s:>17s}" for c in PHRASE_COLUMNS[2:])
        print(f"  {row['stratum']:16s} {row['period']:8s} {cells}")


def print_strata(strata: Sequence[Mapping[str, Any]]) -> None:
    """Counts of statements only: what is left, what the caps allow, the quota and the draw."""
    print(
        f"  {'sample':15s} {'stratum':16s} {'period':8s} "
        + " ".join(f"{c:>9s}" for c in STRATA_COLUMNS[3:])
    )
    for row in strata:
        cells = " ".join(f"{row[c]!s:>9s}" for c in STRATA_COLUMNS[3:])
        print(f"  {row['sample']:15s} {row['stratum']:16s} {row['period']:8s} {cells}")


def write_lists(
    root: Path,
    folder: str,
    drawn: Drawn,
    table: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
) -> dict[str, Any]:
    by_id = {s["id"]: s for s in table}
    entry: dict[str, Any] = {}
    for name, ids in drawn.lists.items():
        file = f"{folder}/sample_{name}.csv"
        text = plain_csv(columns, list_rows(ids, by_id, drawn.ranks.get(name)))
        entry[name] = {
            "file": file,
            "n": len(ids),
            "sha256": write_text(root, file, text),
            "statements_sha256": ids_sha256(ids),
        }
    file = f"{folder}/strata.csv"
    entry["strata"] = {
        "file": file,
        "sha256": write_text(root, file, plain_csv(STRATA_COLUMNS, drawn.strata)),
    }
    return entry


def read_list(path: Path) -> list[str]:
    return [r["statement_group_id"] for r in read_csv(path)]


def with_kept_strata(
    root: Path, strata: Sequence[Mapping[str, Any]], kept: Iterable[str]
) -> list[Mapping[str, Any]]:
    """The stratum table of a draw, with the rows of the samples it kept taken from the table
    on disk: they say what each stratum had when the kept list was drawn, and a draw that
    keeps a list must not lose them."""
    path = root / SAMPLES_DIR / "strata.csv"
    on_disk = read_csv(path) if path.is_file() else []
    kept = set(kept)
    rows: list[Mapping[str, Any]] = []
    for sample in FIRST_SAMPLES:
        source = on_disk if sample in kept else strata
        rows += [row for row in source if row["sample"] == sample]
    return rows


def require_unfilled(root: Path, tasks: Iterable[str]) -> None:
    """Stop before a sheet that was filled in place is written over."""
    filled = [
        path
        for task in tasks
        for annotator in ANNOTATORS
        if holds_labels(path := root / f"{task}_{annotator}.csv")
    ]
    if filled:
        raise SystemExit(
            f"{', '.join(p.as_posix() for p in filled)}: the sheet holds labels or a sitting "
            "time (it was filled in place). Nothing was written. Move it out of the folder "
            "(external_data/annotation/<task>/) and run the command again"
        )


def run_sheets_for(tasks: Sequence[str], inputs: Inputs, root: Path, keys: Path) -> None:
    manifest_path = root / MANIFEST
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    entry = dict(manifest.get("sheets", {}))
    drawn_on = manifest.get("samples", {}).get("inputs", {}).get("events_fields_sha256")
    if drawn_on and drawn_on != inputs.source["events_fields_sha256"]:
        raise SystemExit(
            "the events table is not the one the samples were drawn on (its fields differ): "
            "name the same table with --events or --captures, or draw again on this one and "
            "keep the lists already handed out with --fixed"
        )
    require_unfilled(root, tasks)
    for task in tasks:
        path = root / SAMPLES_DIR / f"sample_{task}.csv"
        if not path.is_file():
            raise SystemExit(f"{path} does not exist: run the draw command first")
        recorded = manifest.get("samples", {}).get(task, {}).get("sha256")
        if recorded and recorded != hashlib.sha256(path.read_bytes()).hexdigest():
            raise SystemExit(f"{path} is not the list the manifest records")
        built = build_sheets(task, read_list(path), inputs.events, inputs.table, inputs.guide)
        files = {name: write_text(root, name, text) for name, text in built.files.items()}
        key_sha = write_text(keys, f"{task}_key.csv", built.key)
        entry[task] = {
            "guide": guide_stamp(inputs.guide),
            "events": inputs.source["events"],
            "items": built.n_items,
            "files": files,
            "key_sha256": key_sha,
        }
        print(f"{task}: {built.n_items} items; wrote {', '.join(sorted(files))} and the key")
    update_manifest(root, "sheets", entry)


def run_draw(args: argparse.Namespace) -> int:
    inputs = load_inputs(args)
    require_exclusions(inputs, args.allow_unmatched)
    root: Path = args.out
    fixed = {name: read_list(root / SAMPLES_DIR / f"sample_{name}.csv") for name in args.fixed}
    drawn = draw_first(inputs.table, inputs.alloc, inputs.excluded, fixed)
    drawn.strata = with_kept_strata(root, drawn.strata, fixed)
    require_same_lists(root, drawn, args.replace, args.sheets)
    require_unfilled(root, args.sheets)
    entry = write_lists(root, SAMPLES_DIR, drawn, inputs.table, SAMPLE_COLUMNS)
    entry["inputs"] = inputs.source
    entry["exclusions"] = inputs.notes
    entry["phrase_rule"] = inputs.phrase_rule
    entry["items_containing_a_guide_phrase"] = {
        name: containing_a_phrase(inputs.table, ids, inputs.phrases)
        for name, ids in drawn.lists.items()
    }
    entry["fixed"] = sorted(fixed)
    entry["caps"] = {"per_template": MAX_PER_TEMPLATE, "per_episode": MAX_PER_EPISODE}
    update_manifest(root, "samples", entry)
    for key, value in inputs.notes.items():
        print(f"{key}: {value}")
    print_phrase_rule(inputs.phrase_rule)
    print_strata(drawn.strata)
    for name in FIRST_SAMPLES:
        kept = " (kept from disk)" if name in fixed else ""
        print(f"{name}: {entry[name]['n']} statements, sha256 {entry[name]['sha256']}{kept}")
        size = sum(inputs.alloc.quotas[name].values())
        if entry[name]["n"] != size:
            print(f"warning: {name} has {entry[name]['n']} statements, the guide's table {size}")
        shared = entry["items_containing_a_guide_phrase"][name]
        print(f"{name}: {shared} of its items contain a phrase the guide quotes")
    if args.sheets:
        run_sheets_for(args.sheets, inputs, root, args.keys or root / KEYS_DIR)
    return 0


def run_sheets(args: argparse.Namespace) -> int:
    inputs = load_inputs(args, exclusions=False)
    run_sheets_for(args.task, inputs, args.out, args.keys or args.out / KEYS_DIR)
    return 0


def require_same_later_lists(root: Path, drawn: Drawn, replace: bool) -> None:
    """Stop a later draw that would put other statements, or another order, in a list that is on
    disk, unless ``--replace`` is given: a list that prompts or pairs were built on is not
    changed without being asked."""
    moved = []
    for name, ids in drawn.lists.items():
        path = root / LATER_DIR / f"sample_{name}.csv"
        if path.is_file():
            ranks = drawn.ranks.get(name, {})
            on_disk = [(r["statement_group_id"], r["draw_rank"]) for r in read_csv(path)]
            if on_disk != [(i, str(ranks.get(i, ""))) for i in sorted(ids)]:
                moved.append(name)
    if moved and not replace:
        raise SystemExit(
            f"the draw would change the list on disk of: {' '.join(moved)} (the guide, the events "
            "table, the first draw or the outcome-audit sample is not the one of the last "
            "draw). Nothing was written. Take the new lists with --replace"
        )


def run_draw_later(args: argparse.Namespace) -> int:
    root: Path = args.out
    sample: Path = args.outcome_sample
    beside = sample.with_name(sample.name.replace("_sample.csv", "_manifest.json"))
    if beside.is_file() and beside != sample:
        status = json.loads(beside.read_text(encoding="utf-8")).get("status")
        if status != "final" and not args.draft:
            raise SystemExit(f"{sample} is a {status} draw; pass --draft to try the command on it")
    first: dict[str, list[str]] = {}
    for name in FIRST_SAMPLES:
        path = root / SAMPLES_DIR / f"sample_{name}.csv"
        if not path.is_file():
            raise SystemExit(f"{path} does not exist: run the draw command first")
        first[name] = read_list(path)
    audited = read_list(sample)
    earlier = {i for ids in first.values() for i in ids}
    if earlier & set(audited):
        raise SystemExit("the outcome-audit sample holds statements of the first draw")
    inputs = load_inputs(args)
    require_exclusions(inputs, args.allow_unmatched)
    drawn = draw_later(
        inputs.table, inputs.alloc, inputs.excluded, earlier | set(audited), labelled=earlier
    )
    require_same_later_lists(root, drawn, args.replace)
    entry = write_lists(root, LATER_DIR, drawn, inputs.table, LATER_COLUMNS)
    entry["inputs"] = inputs.source | {
        "outcome_sample": sample.as_posix(),
        "outcome_sample_sha256": hashlib.sha256(sample.read_bytes()).hexdigest(),
    }
    entry["exclusions"] = inputs.notes | drawn.notes
    entry["status"] = "draft" if args.draft else "final"
    update_manifest(root, "samples_later", entry)
    for key, value in drawn.notes.items():
        print(f"{key}: {value}")
    print_strata(drawn.strata)
    for name in LATER:
        print(f"{name}: {entry[name]['n']} statements, sha256 {entry[name]['sha256']}")
    return 0


def report_check(sheet: Path, checked: Checked) -> int:
    for line in checked.errors:
        print(f"error: {line}")
    for line in checked.warnings:
        print(f"warning: {line}")
    minutes = "not given" if checked.minutes is None else f"{checked.minutes} minutes"
    print(
        f"{sheet}: {len(checked.rows)} rows, {len(checked.labels)} valid, "
        f"{len(checked.errors)} errors, {len(checked.warnings)} warnings; sittings: {minutes}"
    )
    return 0 if checked.ok else 1


def run_validate(args: argparse.Namespace) -> int:
    return report_check(args.sheet, check_file(args.sheet, args.blank, args.out))


def add_inputs(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--events", type=Path, default=EVENTS, help="the events table (csv.gz)")
    sub.add_argument("--captures", type=Path, help="build the events in memory from this folder")
    sub.add_argument("--guide", type=Path, default=GUIDE)
    sub.add_argument("--out", type=Path, default=OUT)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.audit_sample", description=(__doc__ or "").splitlines()[0]
    )
    sub = ap.add_subparsers(dest="command", required=True)
    draw = sub.add_parser("draw", help="draw the pilot, check, reserve and literal samples")
    add_inputs(draw)
    draw.add_argument("--fixed", nargs="*", default=[], choices=FIRST_SAMPLES)
    draw.add_argument("--replace", nargs="*", default=[], choices=FIRST_SAMPLES)
    draw.add_argument("--allow-unmatched", action="store_true")
    draw.add_argument("--sheets", nargs="*", default=[], choices=FIRST_SAMPLES)
    draw.add_argument("--keys", type=Path, default=None)
    draw.set_defaults(run=run_draw)
    sheets = sub.add_parser("sheets", help="write the blank sheets of a task from its list")
    add_inputs(sheets)
    sheets.add_argument("--task", nargs="+", required=True, choices=FIRST_SAMPLES)
    sheets.add_argument("--keys", type=Path, default=None)
    sheets.set_defaults(run=run_sheets)
    later = sub.add_parser("draw-later", help="draw the lists that follow the outcome-audit sample")
    add_inputs(later)
    later.add_argument("--outcome-sample", type=Path, required=True)
    later.add_argument("--draft", action="store_true")
    later.add_argument("--replace", action="store_true")
    later.add_argument("--allow-unmatched", action="store_true")
    later.set_defaults(run=run_draw_later)
    check = sub.add_parser("validate", help="check a filled sheet")
    check.add_argument("sheet", type=Path)
    check.add_argument("--blank", type=Path, default=None)
    check.add_argument("--out", type=Path, default=OUT)
    check.set_defaults(run=run_validate)
    return ap


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(None if argv is None else list(argv))
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
