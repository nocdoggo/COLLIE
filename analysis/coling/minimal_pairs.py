"""Minimal pairs for E5 and the sheets of their hand audit (PLAN.md section 5, E5; AUDIT_GUIDE.md
section 7, task C).

The generator turns the seed statements of ``sample_pair_seeds.csv`` into items for the reading
harness: every seed once as it stands, and edited copies of it in which one factor is changed.
No model is called and no outcome is read: the inputs are the events table (first-sight fields
only), the seed list, the sample lists of the labelling tasks, the two lists of prompt items
drawn before the seeds (in-context pool, dev prompt items) and the guide. The seed list is
read by path at every run and no id is written here, so a list drawn again gives its own items.

Items
-----
* The unedited seed item (``factor`` ``seed``, ``level`` ``unedited``): the display row of the
  seed statement, text and dates untouched, names replaced.
* Edited items, one factor each (``FACTORS``). The level says what was put in:

  ``certainty``
      the marker of the target. ``estimated``, ``expected``, ``anticipated``: that hedge, put
      before the time, before the words that lead into it or at the head of its phrase, or in
      the place of the one hedge of the three the sentence has. ``tbd``: an unknown marker in
      the place of the time ("TBD", "to be determined", "unknown", "date not available at this
      time"). ``no_estimated_date`` and ``as_released``: the sentence of a next-delivery target
      replaced by "No estimated release date ..." or by "Product will be made available as it
      is released". The first three give the class ``estimated`` (the guide's section 7.3 calls
      its example with "expected" by that class), the others an abstention.
  ``surface_form``
      the same period written another way, one attribute of the writing changed, named by its
      new value: ``no_year``, ``with_year``, ``two_digit_year``, ``four_digit_year``,
      ``abbreviated_month``, ``full_month``, ``numeric``, ``hyphenated``, ``separator``,
      ``part_word``, ``quarter_first``, ``quarter_last``, ``quarter_words``, ``unit``,
      ``digits``, ``number_word``.
  ``granularity``
      another period at another grain: ``early``, ``mid``, ``late`` (a part of the month, of
      the quarter or of the year), ``range`` (the month and the next), ``quarter`` (the quarter
      of the month); and ``timeframe`` ("the <month> timeframe": the same period, C15).
  ``stale``
      the text unchanged, the entry reverified ``STALE_DAYS`` days after the stated period ended.
  ``distractor``
      a sentence with a date in another role put before the Availability information:
      ``expiry``, ``depletion``, ``available_until``.
  ``silent``
      every statement about timing removed: a sentence from its first phrase that holds one.

Where the gold comes from
-------------------------
* **From the frozen rule reading of the seed** (``rules.read`` on the seed's statement text at
  its Date of update; DECISIONS.md, decision 4): the whole gold of the unedited seed item
  (statement type, interval, certainty, not stale, no distractor). For the edits the same
  reading says where the target's time expression stands, which statements the text makes,
  what period the time is, and whether it is bounded ("by", "until") or written without a year.
* **By construction, from the conventions of AUDIT_GUIDE.md sections 3.6 to 3.10 as this module
  codes them** (:func:`time_span`, :func:`reads_as`, the edit functions): every field an edit
  changes. A new time expression is written from a period and its interval is that period's
  (C2 to C13); a hedge gives ``estimated``; an unknown marker gives an abstention with reason
  ``tbd``; "as it is released" one with reason ``no_date``; a later Date of update gives
  ``stale``; an added sentence gives one distractor of its role ("available until" is a
  ``depletion`` distractor, section 3.10); a silent item is ``none``. The fields an edit does
  not touch are the seed's.
* **The rule reader is run on every item afterwards as a cross-check only**
  (:func:`rule_check`). Every field in which its reading differs from the gold is written, with
  a reason, to ``e5_rule_check.csv`` in the key folder. Nothing of it is copied into the gold,
  and an item on which the two differ stays in the file with its constructed gold.

The gold is written to ``e5_gold.csv`` in the key folder, not beside the items: an auditor who
read it could tell a planted item of task C from a real one. Its columns are those of a
literal gold (section 3.4) with ``stale``, the factor and level, what was inserted and the
attesting notice.

One factor at a time
--------------------
An edit is made only where the guide's conventions leave the other fields alone:

* a new time must read as its period at the seed's Date of update (C8: a missing year, a
  two-digit year) and must not end before it, so that no edit but ``stale`` makes an item stale;
* an unknown marker is put only on a target that is the one statement of its type, so that the
  choice of the target (section 3.6) cannot move; a sentence is replaced only when the seed
  makes one statement, of the next-delivery type, in a sentence that says nothing else (no
  word on the state of supply), so that type and status wording stay (the second error row of
  section 7.3);
* ``stale`` needs a period that does not depend on the Date of update: a written year, no
  relative time, no "by";
* a distractor sentence ends in a full stop before a capital letter, so its hedge is in another
  clause (section 3.8), and carries no shortage word before "until" (section 3.6);
* a seed whose text has no cue, and is read as a recovery only because it holds a date and at
  most four words (section 3.6), gets no edit that can add words (certainty, granularity,
  distractor);
* a seed is left out when it is stale, undated, carries a distractor date already, or when
  replacing its names changes its rule reading;
* no edit turns the text into that of a statement the labellers read, a prompt shows or the
  guide works through (:func:`reserved_texts`): the whole text of a statement of the pilot,
  the check set, its reserve, the literal sample, the in-context pool, the dev prompt items
  or a row of the guide's Appendix A, words in order and punctuation aside, whatever the drug
  or the company. A seed whose own text is such a text stays (the seed list is drawn by the
  rule of AUDIT_GUIDE.md section 10) and is counted in ``e5_counts.json``; its stale item
  carries the same text.

What cannot be applied is skipped and counted, with the reason (``e5_skips.csv``).

Attested forms
--------------
The inventory (:class:`Inventory`) is built from the two text fields of every train-period
statement (dated before 2023-01-01), leaving out the statements of the pilot, the check set,
its reserve and the literal sample, the rows of the guide's Appendix A, the harness's fixed
test item and every statement whose whole text the guide quotes (A.4). Months and numbers are
masked (:func:`mask`): a full month name, an abbreviated one, a four-digit year, any other
number in digits and a number in words are five different marks. It holds three things:

* sentences (a sentence ends at a full stop before a capital letter, or at a semicolon);
* phrases (the parts of a sentence between spaced dashes, commas and spaced slashes);
* time expressions standing alone as the time of a delivery or a recovery
  (:func:`stated_times`): the writings of a time this module knows (:func:`known_forms`) that
  the frozen rule reader finds whole as the time of such a statement. A writing that a notice
  uses only for another date (the numeric month of an expiry date, "(4/2022 expiry)"; the day
  of "effective Dec 1, 2019") is not in it, nor is a month that takes its year from the next
  item of a list ("Aug. and Sept. 2020").

An edit that puts words into the text is kept only when a notice of the inventory attests it,
with only months and numbers changed (``attested_scope``):

* ``sentence``: the sentence the edit changes is a sentence of a notice;
* ``phrase``: failing that, its phrase is a phrase of a notice;
* ``form``: failing that, and only for a new time expression (surface form, granularity), a
  notice gives the time of a delivery or a recovery in that writing. A hedge, an unknown marker
  and a distractor sentence are never taken on this ground: where they stand matters.

``attested_text`` is the field of such a notice, the shortest. ``stale`` and ``silent`` insert
nothing and have no attested text.

Names
-----
Drug and company are replaced by fictitious names (:func:`fictitious_names`: syllables combined
in a seeded order; a name that is a word of any name, Presentation or notice text of the
corpus, or holds a real name word of five letters or more, is not used). The Presentation keeps
only numbers, units and pack words (``PACK_VOCABULARY``), with invented NDC digits. In the
three text fields every word of a real drug or company name of the corpus (``NameLexicon``),
every word marked as a brand, every head of a company name before a corporate word, every
e-mail address, web address, telephone number and NDC is replaced. ``e5_names.csv`` lists what
was replaced in the text fields, for a reader to check. A name that stands only in a notice
text, in no name column and no Presentation of the corpus, is found by the brand-mark and
corporate-word rules alone. ``generate`` stops when an item still holds a real name.

Selection and size
------------------
Every seed gives its unedited item. Of the edits that can be made, a seed keeps at most
``PER_SEED`` levels of a factor (2 for certainty, surface form, granularity and distractor; 1
for stale and silent), taken so that the levels of a factor fill evenly over the seeds (the
level with the fewest items so far first; seeds and ties in seeded order). If more than
``TARGET_ITEMS`` items remain, second levels are dropped, each time from the factor with the
most items and, in it, from the level with the most, in seeded order, until the target is met.

Audit (task C)
--------------
``audit-sample`` draws the real items (45 for each auditor and 10 for both) from the edited
items, in equal shares over the six factors, at most ``MAX_PER_SEED`` per seed, and adds 5
planted items for each auditor: further edited items whose gold is made wrong in one field by
a fixed rule (:func:`corrupt`; statement type, interval, certainty, stale flag, distractors,
one field each). ``--round 2`` draws a fresh sample in another seeded order, for the audit
that follows a failed one. Sample, assignment and planted items are written only to the key
(``e5_pairs_key.csv`` under ``--keys``, git-ignored); nobody opens it. ``sheets`` writes
``pairs_A1.csv`` and ``pairs_A2.csv`` (the columns of AUDIT_GUIDE.md section 9), each with a
text file of the same items in the same order. ``seed_entry`` is the unedited seed item, the
entry every reader gets, so its names are the fictitious ones.

Filling a sheet: copy it to ``external_data/annotation/pairs/`` and leave the blank where it
is. Write the time you start after ``# sitting_start:`` and the time you stop after
``# sitting_end:`` (``HH:MM``; a further pair of lines for a further sitting). For every row
enter 1 or 0 in ``ok_type``, ``ok_interval``, ``ok_certainty``, ``ok_stale``,
``ok_distractors``, ``minimal``, ``attested`` and ``natural``; give ``correct_value`` when a
label check is 0 and a ``note`` when ``minimal`` or ``attested`` is 0. ``attested`` is 1 when
nothing was inserted. Then run ``validate`` on the copy.

``validate`` checks a filled copy against the blank: every item once, no shown cell changed,
1 or 0 in every check column, ``correct_value`` and ``note`` where they are due, the sitting
times. ``score`` validates both sheets against the blanks the manifest records, reads the key,
writes the adjudication sheet (one row for every real item and auditor that marked it an
error) and exits 3. Run again with a filled copy of that sheet (``decision``: confirmed,
rejected or unresolved; ``confirmed_checks`` with a confirmed error) it applies the pass rule
of section 7.4: at least 95% of the real items free of confirmed errors (95 of 100), planted
items left out; exit 0 on pass, 1 on fail, 2 when a sheet cannot be scored. It writes the
statistics of section 8.3 to ``pairs_score.json`` and says when an auditor missed
``PLANTED_MISS_LIMIT`` planted items and re-checks their own. The score of the sheets as they
were before a re-check stays in the file (``earlier_passes``), so both passes are reported.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.minimal_pairs generate
        [--captures external_data/fda_wayback_csv | --events EVENTS.csv.gz]
        [--seeds analysis/coling/out/audit/samples_later/sample_pair_seeds.csv]
        [--guide analysis/coling/plan/AUDIT_GUIDE.md] [--samples analysis/coling/out/audit/samples]
        [--later analysis/coling/out/audit/samples_later]
        [--out analysis/coling/out/e5] [--keys external_data/annotation/keys] [--check]
    PYTHONPATH=. python -m analysis.coling.minimal_pairs audit-sample [--out ...] [--keys ...]
        [--own 45] [--shared 10] [--planted 5] [--round N] [--replace] [--check]
    PYTHONPATH=. python -m analysis.coling.minimal_pairs sheets [--guide ...] [--out ...]
        [--keys ...] [--check]
    PYTHONPATH=. python -m analysis.coling.minimal_pairs validate SHEET [--blank BLANK]
    PYTHONPATH=. python -m analysis.coling.minimal_pairs score --a1 SHEET --a2 SHEET
        [--out ...] [--keys ...] [--adjudication FILE]

``--check`` writes nothing: it builds the files again and exits 1 when one on disk is missing
or differs. ``generate`` builds the events table in memory from the captures (nothing of it is
written) and writes ``e5_pairs.jsonl`` (the items, in the keys ``read.py`` loads, with
``seed_id``, ``factor``, ``level``, ``is_seed``, ``period`` and ``seed_period``),
``e5_counts.json``, ``e5_skips.csv``, ``e5_names.csv`` and ``e5_manifest.json`` (the hashes of
the seed list, the guide, ``rules.py``, this file and the files written) to ``--out``, and
``e5_gold.csv`` and ``e5_rule_check.csv`` to ``--keys``. The launcher reads ``analysis/coling/out/items/e5_pairs.jsonl``; the step that
fills that folder copies the item file there. ``period`` is ``test`` for every item of a seed
dated 2023-01-01 or later and for a stale item whose new date is: the harness reads the period
from the Date of update, and no model reads such an item before amendment F1.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import forms as F
from analysis.coling import rules as R

SEED = 20261001
OUT = Path("analysis/coling/out/e5")
KEYS = Path("external_data/annotation/keys")  # git-ignored; AUDIT_GUIDE.md section 10
GUIDE = S.GUIDE
SEEDS = S.OUT / S.LATER_DIR / "sample_pair_seeds.csv"
SAMPLES = S.OUT / S.SAMPLES_DIR
LATER_LISTS = ("incontext_pool", "dev_prompt")  # drawn before the seeds, beside their list
RULES_SHA256_PREFIX = "6a810bcb1ae277b9"  # DECISIONS.md, process rule 4
TEST_START = date(2023, 1, 1)
ITEMS_FILE = "e5_pairs.jsonl"
GOLD_FILE = "e5_gold.csv"
COUNTS_FILE = "e5_counts.json"
SKIPS_FILE = "e5_skips.csv"
NAMES_FILE = "e5_names.csv"
MANIFEST_FILE = "e5_manifest.json"
RULE_CHECK_FILE = "e5_rule_check.csv"  # under the key folder: it holds rule readings of the items
KEY_FILE = "e5_pairs_key.csv"
AUDIT_MANIFEST_FILE = "pairs_manifest.json"
ADJUDICATION_FILE = "pairs_adjudication.csv"
SCORE_FILE = "pairs_score.json"
AUDITORS = ("A1", "A2")
SHARED = "both"

FACTORS = ("certainty", "surface_form", "granularity", "stale", "distractor", "silent")
SEED_FACTOR = "seed"
SEED_LEVEL = "unedited"
LEVELS: dict[str, tuple[str, ...]] = {
    "certainty": (
        "estimated",
        "expected",
        "anticipated",
        "tbd",
        "no_estimated_date",
        "as_released",
    ),
    "surface_form": (
        "no_year",
        "with_year",
        "two_digit_year",
        "four_digit_year",
        "abbreviated_month",
        "full_month",
        "numeric",
        "hyphenated",
        "separator",
        "part_word",
        "quarter_first",
        "quarter_last",
        "quarter_words",
        "unit",
        "digits",
        "number_word",
    ),
    "granularity": ("early", "mid", "late", "range", "timeframe", "quarter"),
    "stale": ("stale",),
    "distractor": ("expiry", "depletion", "available_until"),
    "silent": ("silent",),
}
PER_SEED = {
    "certainty": 2,
    "surface_form": 2,
    "granularity": 2,
    "stale": 1,
    "distractor": 2,
    "silent": 1,
}
TARGET_ITEMS = 800
STALE_DAYS = 16  # a stale item is reverified this many days after its stated period ended
EXPIRY_MONTHS = 2  # an expiry date is the last day of the month this long after the stated end
ESTIMATE_TYPES = ("recovery", "next_delivery")
DISTRACTOR_ROLE = {"expiry": "expiry", "depletion": "depletion", "available_until": "depletion"}

AUDIT_SIZES = (45, 10, 5)  # own items per auditor, shared items, planted items per auditor
MAX_PER_SEED = 2
PASS_PERCENT = 95  # of the real items, free of confirmed errors (AUDIT_GUIDE.md section 7.4)
PLANTED_MISS_LIMIT = 2  # an auditor who misses this many planted items re-checks their own
SECONDS_PER_ITEM = (40, 20, 60)  # the planning rate of the guide's hours table, low and high
PLANT_FIELDS = ("type", "interval", "certainty", "stale", "distractors")
DECISIONS = ("confirmed", "rejected", "unresolved")

ITEM_KEYS = (
    "item_id",
    "generic_name",
    "company_name",
    "presentation",
    "therapeutic_category",
    "initial_posting_date",
    "date_of_update",
    "type_of_update",
    "availability_information",
    "related_information",
    "reason_for_shortage",
)
"""The keys of an item that the reading harness loads (``read.ReadItem``; the entry block)."""
ITEM_EXTRA = ("seed_id", "factor", "level", "is_seed", "period", "seed_period")
ENTRY_LINES = (
    ("Drug", "generic_name"),
    ("Company", "company_name"),
    ("Presentation", "presentation"),
    ("Therapeutic category", "therapeutic_category"),
    ("Initial posting date", "initial_posting_date"),
    ("Type of update", "type_of_update"),
    ("Date of update", "date_of_update"),
    ("Availability information", "availability_information"),
    ("Related information", "related_information"),
    ("Reason for shortage", "reason_for_shortage"),
)
TEXT_FIELDS = ("availability_information", "related_information")
GOLD_COLUMNS = (
    "item_id",
    "seed_id",
    "factor",
    "level",
    "is_seed",
    "period",
    "statement_type",
    "start",
    "end",
    "abstain",
    "abstain_reason",
    "certainty",
    "stale",
    "quote",
    "distractor_roles",
    "distractor_quotes",
    "gold_source",
    "inserted",
    "form",
    "attested_scope",
    "attested_event_id",
    "attested_text",
)
SKIP_COLUMNS = ("seed_id", "factor", "level", "reason")
NAME_COLUMNS = ("seed_id", "field", "found", "written")
RULE_CHECK_COLUMNS = ("item_id", "seed_id", "factor", "level", "field", "gold", "rule", "reason")

SHOWN = (
    "pair_id",
    "seed_id",
    "factor",
    "level",
    "seed_entry",
    "seed_gold",
    "edited_entry",
    "gold_statement_type",
    "gold_start",
    "gold_end",
    "gold_abstain",
    "gold_certainty",
    "gold_stale",
    "gold_distractor_roles",
    "attested_text",
)
CHECKS = ("ok_type", "ok_interval", "ok_certainty", "ok_stale", "ok_distractors")
ERROR_CHECKS = (*CHECKS, "minimal", "attested")  # a 0 in one of these makes the item an error
ENTERED = (*ERROR_CHECKS, "natural", "correct_value", "note")
SHEET_COLUMNS = (*SHOWN, *ENTERED)
GOLD_SHOWN = SHOWN[7:14]
KEY_COLUMNS = (
    "pair_id",
    "seed_id",
    "factor",
    "level",
    "assigned_to",
    "planted",
    "planted_field",
    *(f"true_{c}" for c in GOLD_SHOWN),
    *(f"shown_{c}" for c in GOLD_SHOWN),
)
ADJUDICATION_SHOWN = (
    "pair_id",
    "seed_id",
    "factor",
    "level",
    "seed_entry",
    "edited_entry",
    *GOLD_SHOWN,
    "attested_text",
    "reported_by",
    "failed_checks",
    "correct_value",
    "note",
)
ADJUDICATION_ENTERED = ("decision", "confirmed_checks", "adj_note")
SCHEME = {
    "ok_type, ok_interval, ok_certainty, ok_stale, ok_distractors": (
        "1 when the edited entry entails the gold field (sections 3.6 to 3.10), else 0"
    ),
    "minimal": "1 when the edit changes only the named factor, else 0",
    "attested": (
        "1 when the inserted marker or form is in attested_text, or nothing was inserted, else 0"
    ),
    "natural": "1 or 0 (secondary; not part of the pass rule)",
    "correct_value": "the right value of every field marked 0",
    "note": "free text; required when minimal or attested is 0",
}
NOTHING_INSERTED = "(nothing inserted)"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def json_text(value: Any) -> str:
    return json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------------------------
# Time conventions (AUDIT_GUIDE.md section 3.7), coded here from the guide
# --------------------------------------------------------------------------------------------

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MONTH_ABBREVIATIONS = tuple(name[:3] for name in MONTHS)
PARTS = ("early", "mid", "late")
PART_DAYS = {"early": (1, 10), "mid": (11, 20), "late": (21, 31)}  # C3; late runs to the last day
YEAR_PART_MONTHS = {"early": (1, 4), "mid": (5, 8), "late": (9, 12)}  # C7
UNIT_DAYS = {"day": 1, "week": 7, "month": 30}  # C12
NUMBER_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
QUARTER_WORDS = ("first", "second", "third", "fourth")
QUARTER_ORDINALS = ("1st", "2nd", "3rd", "4th")
YEAR_WINDOW = (-1, 3)  # C8: a two-digit number after a month is a year inside this window


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


@dataclass(frozen=True)
class Time:
    """A stated time before it is written: a month, a part of one, a quarter, a part of a
    quarter or of a year, a range of months of one year, a day, or days counted from the Date of
    update (``low`` to ``high``)."""

    kind: str
    year: int = 0
    month: int = 0
    day: int = 0
    part: str = ""
    quarter: int = 0
    last_month: int = 0
    low: int = 0
    high: int = 0


def time_span(time: Time, anchor: date) -> tuple[date, date]:
    """First and last day of a time (conventions C2 to C7, C9, C12 and C13)."""
    year, month = time.year, time.month
    if time.kind == "month":
        return date(year, month, 1), month_end(year, month)
    if time.kind == "part_of_month":
        first, last = PART_DAYS[time.part]
        end = month_end(year, month) if time.part == "late" else date(year, month, last)
        return date(year, month, first), end
    if time.kind == "month_range":
        return date(year, month, 1), month_end(year, time.last_month)
    if time.kind == "quarter":
        return date(year, 3 * time.quarter - 2, 1), month_end(year, 3 * time.quarter)
    if time.kind == "quarter_part":
        month = 3 * time.quarter - 2 + PARTS.index(time.part)
        return date(year, month, 1), month_end(year, month)
    if time.kind == "year_part":
        first, last = YEAR_PART_MONTHS[time.part]
        return date(year, first, 1), month_end(year, last)
    if time.kind == "day":
        return date(year, month, time.day), date(year, month, time.day)
    if time.kind == "relative":
        return anchor + timedelta(days=time.low), anchor + timedelta(days=time.high)
    raise ValueError(f"no convention for a time of kind {time.kind!r}")


def first_year(time: Time, anchor: date) -> int:
    """The year a time written without one takes (C8): the first occurrence that ends on or
    after the Date of update. A part of a month takes the year of its month, and a part of a
    quarter that of its quarter."""
    unit = {"part_of_month": "month", "quarter_part": "quarter"}.get(time.kind, time.kind)
    whole = replace(time, kind=unit, part="")
    year = anchor.year
    while time_span(replace(whole, year=year), anchor)[1] < anchor:
        year += 1
    return year


@dataclass(frozen=True)
class Form:
    """One way of writing a time: the words, and what kind of writing it is (``attrs``). A form
    that is not ``offered`` is only recognised in a seed, never written into an item."""

    text: str
    time: Time
    attrs: tuple[tuple[str, str], ...]
    offered: bool = True

    def attr(self, name: str) -> str | None:
        return dict(self.attrs).get(name)


Writing = tuple[str, dict[str, str], bool]


def _month_writings(year: int, month: int) -> Iterator[Writing]:
    full, short = MONTHS[month - 1], MONTH_ABBREVIATIONS[month - 1]
    yy = f"{year % 100:02d}"
    names = [("full_month", full)] + ([("abbreviated_month", short)] if short != full else [])
    for name, word in names:
        common = name == "abbreviated_month" or short == full  # "Jan 21", "May 21"
        yield f"{word} {year}", {"name": name, "sep": "space", "year": "yyyy"}, True
        yield word, {"name": name, "year": ""}, True
        yield f"{word} {yy}", {"name": name, "sep": "space", "year": "yy"}, common
        yield f"{word}-{year}", {"name": name, "sep": "hyphen", "year": "yyyy"}, common
        yield f"{word}-{yy}", {"name": name, "sep": "hyphen", "year": "yy"}, common
        yield f"{word}, {year}", {"name": name, "sep": "comma", "year": "yyyy"}, False
        yield f"{word} of {year}", {"name": name, "sep": "of", "year": "yyyy"}, False
    yield f"{month}/{year}", {"name": "numeric", "year": "yyyy"}, True
    yield f"{month:02d}/{year}", {"name": "numeric", "year": "yyyy"}, False


PART_WORDS = {
    "early": ("early ", "beginning of ", "start of "),
    "mid": ("mid ", "mid-", "middle of ", "mid of "),
    "late": ("late ", "late-", "end of ", "end "),
}
PARTS_NOT_OFFERED = {
    "part_of_month": ("mid of ", "start of "),
    "quarter_part": ("mid of ", "start of ", "middle of "),
    "year_part": ("mid-",),
}
"""Part words that are recognised in a seed and never written into an item: rare ones, and the
two that the frozen rule reader does not read as the guide's conventions do ("middle of Q3 2021"
is the whole quarter to it, where C5 gives the second month; "mid-2020" is no time to it, where
C7 gives May to August)."""


def _part_writings(kind: str, part: str, inner: Iterable[Writing]) -> Iterator[Writing]:
    for word in PART_WORDS[part]:
        for text, attrs, offered in inner:
            if attrs.get("name") != "numeric":
                show = offered and word not in PARTS_NOT_OFFERED[kind]
                yield f"{word}{text}", {**attrs, "word": word.strip()}, show


def _quarter_writings(year: int, quarter: int) -> Iterator[Writing]:
    yy = f"{year % 100:02d}"
    first, last, words = "quarter_first", "quarter_last", "quarter_words"
    yield f"Q{quarter} {year}", {"order": first, "sep": "space", "year": "yyyy"}, True
    yield f"Q{quarter}", {"order": first, "year": ""}, True
    yield f"Q{quarter}-{year}", {"order": first, "sep": "hyphen", "year": "yyyy"}, True
    yield f"Q{quarter}{year}", {"order": first, "sep": "none", "year": "yyyy"}, False
    yield f"Q{quarter}, {year}", {"order": first, "sep": "comma", "year": "yyyy"}, False
    yield f"{quarter}Q {year}", {"order": last, "sep": "space", "year": "yyyy"}, True
    yield f"{quarter}Q{year}", {"order": last, "sep": "none", "year": "yyyy"}, True
    yield f"{quarter}Q{yy}", {"order": last, "sep": "none", "year": "yy"}, True
    yield f"{quarter}Q", {"order": last, "year": ""}, True
    word, ordinal = QUARTER_WORDS[quarter - 1], QUARTER_ORDINALS[quarter - 1]
    yield f"{word} quarter {year}", {"order": words, "sep": "space", "year": "yyyy"}, True
    yield f"{word} quarter of {year}", {"order": words, "sep": "of", "year": "yyyy"}, True
    yield f"{ordinal} quarter {year}", {"order": "ordinal", "sep": "space", "year": "yyyy"}, False


def _day_writings(year: int, month: int, day: int) -> Iterator[Writing]:
    full, short = MONTHS[month - 1], MONTH_ABBREVIATIONS[month - 1]
    yy = f"{year % 100:02d}"
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    yield f"{full} {day}, {year}", {"name": "full_month", "year": "yyyy"}, True
    yield f"{full} {day}", {"name": "full_month", "year": ""}, True
    yield f"{full} {day}{suffix}, {year}", {"name": "ordinal", "year": "yyyy"}, False
    if short != full:
        yield f"{short} {day}, {year}", {"name": "abbreviated_month", "year": "yyyy"}, True
    yield f"{month}/{day}/{year}", {"name": "numeric", "year": "yyyy"}, True
    yield f"{month}/{day}/{yy}", {"name": "numeric", "year": "yy"}, True
    yield f"{month:02d}/{day:02d}/{year}", {"name": "numeric", "year": "yyyy"}, False


RANGE_SEPARATORS = (("/", "slash"), (" - ", "spaced_hyphen"), ("-", "hyphen"), (" to ", "to"))


def _range_writings(year: int, month: int, last_month: int) -> Iterator[Writing]:
    yy = f"{year % 100:02d}"
    for name, words in (("full_month", MONTHS), ("abbreviated_month", MONTH_ABBREVIATIONS)):
        first, last = words[month - 1], words[last_month - 1]
        if name == "abbreviated_month" and (first, last) == (
            MONTHS[month - 1],
            MONTHS[last_month - 1],
        ):
            continue
        for sep, sep_name in RANGE_SEPARATORS:
            attrs = {"name": name, "sep": sep_name}
            usual = sep_name != "slash" or last_month == month + 1  # "March/April", not "/July"
            yield f"{first}{sep}{last} {year}", {**attrs, "year": "yyyy"}, usual
            yield f"{first}{sep}{last}", {**attrs, "year": ""}, usual
            yield f"{first}{sep}{last} {yy}", {**attrs, "year": "yy"}, False


YEAR_PART_WORDS = {
    "early": ("early ", "beginning of "),
    "mid": ("mid ", "mid-", "middle of "),
    "late": ("late ", "end of ", "end "),
}


UNIT_MOST = {"day": 90, "week": 12, "month": 10**6}
"""The largest count offered in a unit: "540 days" is recognised, never written."""


def _relative_writings(low: int, high: int) -> Iterator[Writing]:
    for unit, days in UNIT_DAYS.items():
        if low % days or high % days:
            continue
        first, last = low // days, high // days
        noun = unit if first == last == 1 else f"{unit}s"
        usual = last <= UNIT_MOST[unit]
        if first == last:
            yield f"{first} {noun}", {"unit": unit, "number": "digits"}, usual
            if first <= len(NUMBER_WORDS):
                word = NUMBER_WORDS[first - 1]
                yield f"{word} {noun}", {"unit": unit, "number": "number_word"}, usual
        else:
            for sep, sep_name in RANGE_SEPARATORS[1:]:
                yield f"{first}{sep}{last} {noun}", {"unit": unit, "sep": sep_name}, usual


def forms(time: Time) -> list[Form]:
    """Every writing of a time that this module knows, each text once."""
    if time.kind == "month":
        writings: Iterable[Writing] = _month_writings(time.year, time.month)
    elif time.kind == "part_of_month":
        inner = list(_month_writings(time.year, time.month))
        writings = _part_writings(time.kind, time.part, inner)
    elif time.kind == "quarter":
        writings = _quarter_writings(time.year, time.quarter)
    elif time.kind == "quarter_part":
        inner = list(_quarter_writings(time.year, time.quarter))
        writings = _part_writings(time.kind, time.part, inner)
    elif time.kind == "year_part":
        writings = (
            (f"{word}{time.year}", {"word": word.strip()}, word not in PARTS_NOT_OFFERED[time.kind])
            for word in YEAR_PART_WORDS[time.part]
        )
    elif time.kind == "month_range":
        writings = _range_writings(time.year, time.month, time.last_month)
    elif time.kind == "day":
        writings = _day_writings(time.year, time.month, time.day)
    elif time.kind == "relative":
        writings = _relative_writings(time.low, time.high)
    else:
        raise ValueError(f"no writing for a time of kind {time.kind!r}")
    seen: dict[str, Form] = {}
    for text, attrs, offered in writings:
        seen.setdefault(text, Form(text, time, tuple(sorted(attrs.items())), offered))
    return list(seen.values())


def reads_as(form: Form, anchor: date) -> bool:
    """Whether a writing means its time at this Date of update (C8). A time written without a
    year must be the first occurrence that ends on or after the date; a two-digit year must lie
    in the window of C8; "June 15" must not be a month and a year."""
    time, year = form.time, form.attr("year")
    if year == "":
        if time.kind == "month_range":
            return False  # the guide gives no year to a range written without one
        low, high = anchor.year + YEAR_WINDOW[0], anchor.year + YEAR_WINDOW[1]
        if time.kind == "day" and low <= 2000 + time.day <= high:
            return False
        return first_year(time, anchor) == time.year
    if year == "yy":
        return anchor.year + YEAR_WINDOW[0] <= time.year <= anchor.year + YEAR_WINDOW[1]
    return True


def _squash(text: str) -> str:
    """A time expression for comparison: lower case, no full stop, one kind of dash and space."""
    text = plain(text).lower().replace(".", "")
    return re.sub(r"\bsept\b", "sep", re.sub(r"\s+", " ", text)).strip()


def detect(time: Time, timex: str) -> Form | None:
    """The writing of ``time`` that the seed uses, or None when this module does not know it."""
    wanted = _squash(timex)
    return next((form for form in forms(time) if _squash(form.text) == wanted), None)


def surface_level(old: Form, new: Form) -> str | None:
    """The level of a surface edit: the one attribute of the writing that changes, named by its
    new value. None when nothing or more than one attribute changes."""
    before, after = dict(old.attrs), dict(new.attrs)
    changed = [k for k in sorted(before.keys() & after.keys()) if before[k] != after[k]]
    if len(changed) != 1 or old.time != new.time:
        return None
    key = changed[0]
    value = after[key]
    if key == "year":
        if old.time.kind == "month_range":
            return None
        if value == "yyyy":
            return "with_year" if before[key] == "" else "four_digit_year"
        return "no_year" if value == "" else "two_digit_year"
    if key == "sep":
        return "hyphenated" if value == "hyphen" and old.time.kind != "month_range" else "separator"
    if key == "word":
        return "part_word"
    if key == "unit":
        return "unit"
    return value


def same_writing(old: Form, new: Form, keys: Iterable[str]) -> bool:
    return all(old.attr(k) == new.attr(k) for k in keys)


def seed_time(reading: F.FormReading, anchor: date) -> Time | None:
    """The time of a seed's target, from its rule reading: the class of the form and the
    interval. None for a form this module does not rewrite (a time bounded by "by", a half of a
    month, a week, a range with parts or over two years, a time counted "within")."""
    if reading.start is None or reading.end is None or reading.bound == "by":
        return None
    low, high = date.fromisoformat(reading.start), date.fromisoformat(reading.end)
    year, month = low.year, low.month
    whole_month = low.day == 1 and high == month_end(year, month)
    time: Time | None = None
    if reading.form in ("month_year", "month_no_year") and whole_month:
        time = Time("month", year, month)
    elif reading.form == "part_of_month":
        part = next((p for p in PARTS if PART_DAYS[p][0] == low.day), "")
        time = Time("part_of_month", year, month, part=part) if part else None
    elif reading.form == "quarter" and low.day == 1:
        quarter = (month + 2) // 3
        if whole_month:
            time = Time("quarter_part", year, quarter=quarter, part=PARTS[(month - 1) % 3])
        elif month % 3 == 1:
            time = Time("quarter", year, quarter=quarter)
    elif reading.form == "year":
        part = next((p for p in PARTS if YEAR_PART_MONTHS[p][0] == month), "")
        time = Time("year_part", year, part=part) if part else None
    elif reading.form == "range" and year == high.year and month < high.month:
        time = Time("month_range", year, month, last_month=high.month)
    elif reading.form == "exact_day":
        time = Time("day", year, month, day=low.day)
    elif reading.form == "relative":
        time = Time("relative", low=(low - anchor).days, high=(high - anchor).days)
    if time is None or (time.kind == "relative" and time.low <= 0):
        return None
    return time if time_span(time, anchor) == (low, high) else None


# --------------------------------------------------------------------------------------------
# Text: fields as the rule reader sees them, sentences, phrases, masks
# --------------------------------------------------------------------------------------------

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = dict.fromkeys(map(ord, "‘’´`"), "'")
_MONTH_FULL = "|".join(name.lower() for name in MONTHS)
_MONTH_SHORT = "jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
_MASKS = (
    (re.compile(rf"(?<![a-z])(?:{_MONTH_FULL})(?![a-z])"), "<month>"),
    (re.compile(rf"(?<![a-z])(?:{_MONTH_SHORT})(?![a-z])\.?"), "<mon>"),
    (re.compile(r"(?:(?<!\d)|(?<=q[1-4]))(?:19|20)\d\d(?!\d)"), "<yyyy>"),  # also "Q12020"
    (re.compile(r"\d+"), "<n>"),
    (re.compile(rf"(?<![a-z])(?:{'|'.join(NUMBER_WORDS)})(?![a-z])"), "<number>"),
)
_STOP = re.compile(r"\.(?=\s+[A-Z(])|;")
_ABBREVIATION = re.compile(
    r"\b(?:jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec|exp|est|approx|inc|no)$", re.IGNORECASE
)
_PHRASE_BREAK = re.compile(r"\s+-\s+|\s*[–—]\s*|,\s+|\s+/\s+")
_NO_BREAK_BEFORE = re.compile(
    rf"(?:{_MONTH_FULL}|{_MONTH_SHORT}|early|mid|middle|late|end|beginning|q[1-4]|[1-4]q|and|or"
    r"|respectively)\b|\d",
    re.IGNORECASE,
)


def plain(text: str) -> str:
    """Dashes, quotation marks and spaces written one way."""
    text = text.translate(_DASHES).translate(_QUOTES).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def mask(text: str) -> str:
    """A wording with its months and numbers masked: ``<month>`` for a full month name,
    ``<mon>`` for an abbreviated one, ``<yyyy>`` for a four-digit year (also one written right
    after a quarter, "Q12020"), ``<n>`` for any other number in digits, ``<number>`` for one in
    words; lower case, no punctuation at either end."""
    masked = plain(text).lower()
    for pattern, mark in _MASKS:
        masked = pattern.sub(mark, masked)
    return masked.strip(" .;,")


def sentences(text: str) -> list[tuple[int, int]]:
    """The sentences of a field, as spans with their closing full stop or semicolon. A sentence
    ends at a full stop before a capital letter, or at a semicolon (section 3.8)."""
    cuts, start = [], 0
    for match in _STOP.finditer(text):
        if match.group() == "." and _ABBREVIATION.search(text[: match.start()]):
            continue
        cuts.append((start, match.end()))
        start = match.end()
    cuts.append((start, len(text)))
    spans = []
    for low, high in cuts:
        while low < high and text[low].isspace():
            low += 1
        while high > low and text[high - 1].isspace():
            high -= 1
        if low < high:
            spans.append((low, high))
    return spans


def phrases(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """The phrases of one sentence: its parts between spaced dashes, commas and spaced slashes.
    A break before a month, a number, a part word, "and" or "or" is not one (it is inside a
    date or a list)."""
    spans, low = [], start
    for match in _PHRASE_BREAK.finditer(text, start, end):
        if _NO_BREAK_BEFORE.match(text, match.end(), end) or match.start() == low:
            continue
        spans.append((low, match.start()))
        low = match.end()
    spans.append((low, end))
    return spans


def span_at(spans: Sequence[tuple[int, int]], position: int) -> tuple[int, int] | None:
    return next((span for span in spans if span[0] <= position < span[1]), None)


def units_at(text: str, position: int) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """The sentence and the phrase of ``text`` that hold the character at ``position``."""
    sentence = span_at(sentences(text), position)
    if sentence is None:
        return None
    phrase = span_at(phrases(text, *sentence), position)
    return (sentence, phrase) if phrase is not None else None


@dataclass(frozen=True)
class Piece:
    """One text field as a part of the statement text: its raw text, its text as the rule reader
    normalises it, where each normalised character stands in the raw text, and where the field
    starts in the statement text."""

    name: str
    raw: str
    norm: str
    index: tuple[int, ...]
    offset: int


def _normalised(text: str) -> tuple[str, tuple[int, ...]]:
    """``rules.normalise`` with, for every character kept, its position in ``text``."""
    out: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text.translate(_DASHES).translate(_QUOTES)):
        if char.isspace() or char == "\xa0":
            if out and out[-1] != " ":
                out.append(" ")
                index.append(position)
        else:
            out.append(char)
            index.append(position)
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), tuple(index)


def statement_pieces(availability: str, related: str) -> list[Piece]:
    """The fields that make the statement text, in the order ``corpus.statement_text`` joins
    them. Raises when the pieces do not give the text the rule reader normalises."""
    named = []
    if availability and not C.availability_is_bare(availability):
        named.append(("availability_information", availability))
    if related and not (named and C.norm_text(related) == C.norm_text(availability)):
        named.append(("related_information", related))
    pieces, offset = [], 0
    for name, raw in named:
        norm, index = _normalised(raw)
        pieces.append(Piece(name, raw, norm, index, offset))
        offset += len(norm) + len(S.FIELD_JOIN)
    joined = S.FIELD_JOIN.join(piece.norm for piece in pieces)
    if joined != R.normalise(C.statement_text(availability, related)):
        raise ValueError("the fields do not give the statement text of the corpus builder")
    return pieces


def locate(pieces: Sequence[Piece], start: int, end: int) -> tuple[str, int, int] | None:
    """Field and raw span of the characters ``start`` to ``end`` of the normalised statement
    text; None when they are not inside one field."""
    for piece in pieces:
        low, high = start - piece.offset, end - piece.offset
        if 0 <= low < high <= len(piece.norm):
            return piece.name, piece.index[low], piece.index[high - 1] + 1
    return None


# --------------------------------------------------------------------------------------------
# Attested forms
# --------------------------------------------------------------------------------------------


TIMEFRAMES = ("the {} timeframe", "{} timeframe")
_PREPOSITION = re.compile(
    r"\b(?:in|by|for|on|of|until|till|through|thru|than|to|from|during|before|after)\s+$",
    re.IGNORECASE,
)
SCOPES = ("sentence", "phrase", "form")


@cache
def known_forms() -> frozenset[str]:
    """Every writing of a time this module knows, masked: the forms of ``forms`` for a month
    with an abbreviation and for May, a day, a quarter, a year, relative times, and the
    "timeframe" wordings around a month or a range."""
    times = [Time("day", 2020, 3, day=5), Time("day", 2020, 5, day=5)]
    for month in (3, 5):
        times.append(Time("month", 2020, month))
        times.append(Time("month_range", 2020, month, last_month=month + 1))
        times += [Time("part_of_month", 2020, month, part=part) for part in PARTS]
    times.append(Time("quarter", 2020, quarter=2))
    times += [Time("quarter_part", 2020, quarter=2, part=part) for part in PARTS]
    times += [Time("year_part", 2020, part=part) for part in PARTS]
    for days in UNIT_DAYS.values():
        times += [Time("relative", low=n * days, high=n * days) for n in (1, 2, 13)]
        times.append(Time("relative", low=2 * days, high=13 * days))
    known = set()
    for time in times:
        for form in forms(time):
            known.add(mask(form.text))
            if time.kind in ("month", "month_range"):
                known |= {mask(frame.format(form.text)) for frame in TIMEFRAMES}
    return frozenset(known)


_DAY_OR_YEAR = re.compile(r"<mon(?:th)?> <n>")
"""A month and a number of one or two digits: a month and a year ("Mar 21") or a day ("June
15"), by the Date of update (C8)."""
_LISTED = re.compile(r"[\s,]*(?:and|or|to|&|/|-)?[\s,]*", re.IGNORECASE)
"""What stands between two times of one list ("Aug. and Sept. 2020", "May 2020, July 2020")."""


def stated_times(availability: str, related: str, anchor: date) -> list[tuple[str, str]]:
    """The times that one notice gives for a delivery or a recovery, as the frozen rule reader
    finds them: each as the writing of ``known_forms`` that it is, masked, with the text of the
    field it stands in.

    The reader takes the longest time expression at a place, so a writing found here stands
    alone: a part of a longer date, of a range or of a list of parts is another expression. A
    time that another time follows in a list ("Aug." in "Aug. and Sept. 2020", which takes its
    year from the next) is left out too. A time in any other role (an expiry date, stock that
    lasts until a time, a discontinuation, the onset of a shortage, a past event) is left out:
    it does not attest the writing as the time of a delivery or a recovery, which is what an
    edit makes of it. "The <time> timeframe" and "<time> timeframe" are found around a time,
    and a time that begins with "the" is taken without it. A month and a number that the
    reader takes for a day ("June 15") is not a month and a two-digit year."""
    try:
        pieces = statement_pieces(availability, related)
    except ValueError:
        return []
    raw = {piece.name: piece.raw for piece in pieces}
    known = known_forms()
    joined = S.FIELD_JOIN.join(piece.norm for piece in pieces)
    statements = R.read(C.statement_text(availability, related), anchor).statements
    starts = sorted({st["span"][0] for st in statements if st["interval"] is not None})
    found = []
    for statement in statements:
        interval = statement["interval"]
        if interval is None or statement["statement_type"] not in ESTIMATE_TYPES:
            continue
        last = statement["span"][1]
        if any(_LISTED.fullmatch(joined[last:first]) for first in starts if first >= last):
            continue
        place = locate(pieces, *statement["span"])
        if place is None:
            continue
        name, start, end = place
        text = raw[name]
        wording = re.sub(r"^the\s+", "", text[start:end], flags=re.IGNORECASE)
        if re.match(r"\s+time\s?frame", text[end:], re.IGNORECASE):
            led = re.search(r"\bthe\s+$", text[:start], re.IGNORECASE)
            wording = TIMEFRAMES[0 if led else 1].format(wording)
        form = mask(wording)
        a_day = interval[0] == interval[1] and _DAY_OR_YEAR.fullmatch(form)
        if form in known and not a_day:
            found.append((form, text))
    return found


@dataclass(frozen=True)
class Attested:
    """A real notice that holds a wording: the field's text, its event, and what matched: the
    whole sentence, the phrase, or the time expression alone (``SCOPES``)."""

    text: str
    event_id: str
    scope: str
    statements: int


@dataclass
class Inventory:
    """Masked sentences, phrases and time expressions of the train-period statements, each
    with the number of statements that hold it and the shortest field that does."""

    sentences: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    phrases: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    forms: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    statements: int = 0

    def _count(self, scope: str, wording: str, text: str, event_id: str) -> None:
        table = getattr(self, scope)
        count, best, event = table.get(wording, (0, text, event_id))
        if (len(text), text, event_id) < (len(best), best, event):
            best, event = text, event_id
        table[wording] = (count + 1, best, event)

    def add(self, text: str, event_id: str) -> None:
        """Take in the sentences and the phrases of one field of one statement."""
        found: dict[str, set[str]] = {"sentences": set(), "phrases": set()}
        for low, high in sentences(text):
            found["sentences"].add(mask(text[low:high]))
            found["phrases"].update(mask(text[a:b]) for a, b in phrases(text, low, high))
        for scope, wordings in found.items():
            for wording in sorted(wordings - {""}):
                self._count(scope, wording, text, event_id)

    def add_times(self, times: Iterable[tuple[str, str]], event_id: str) -> None:
        """Take in the times of one statement (:func:`stated_times`): each writing once, with
        the shortest of the statement's fields that hold it."""
        shortest: dict[str, str] = {}
        for form, text in times:
            kept = shortest.get(form, text)
            shortest[form] = min(kept, text, key=lambda t: (len(t), t))
        for form, text in sorted(shortest.items()):
            self._count("forms", form, text, event_id)

    def find(self, text: str, position: int) -> Attested | None:
        """The notice that attests the sentence of ``text`` at ``position``, or else its
        phrase."""
        units = units_at(text, position)
        if units is None:
            return None
        for scope, (low, high) in zip(("sentences", "phrases"), units, strict=True):
            hit = getattr(self, scope).get(mask(text[low:high]))
            if hit is not None:
                return Attested(hit[1], hit[2], scope[:-1], hit[0])
        return None

    def find_form(self, wording: str) -> Attested | None:
        """The notice that gives the time of a delivery or a recovery written like ``wording``,
        standing alone."""
        hit = self.forms.get(mask(wording))
        return Attested(hit[1], hit[2], "form", hit[0]) if hit is not None else None


def train_statements(events: pd.DataFrame, excluded: Iterable[str]) -> pd.DataFrame:
    """One row per train-period statement that is not excluded: its member with the smallest
    event id."""
    ev = S.check_events(events)
    keep = (ev["event_date"] < TEST_START.isoformat()) & ~ev["statement_group_id"].isin(
        set(excluded)
    )
    ev = ev.loc[keep].sort_values(["statement_group_id", "event_id"])
    return ev.groupby("statement_group_id", sort=True).head(1).reset_index(drop=True)


def build_inventory(events: pd.DataFrame, excluded: Iterable[str]) -> Inventory:
    """The attested forms: the two text fields of every train-period statement outside
    ``excluded`` (the labelling samples and the guide's Appendix A), and the times its
    delivery and recovery statements give."""
    inventory = Inventory()
    rows = train_statements(events, excluded)
    columns = ("event_id", "availability_text", "related_text", "event_date")
    for event_id, availability, related, day in zip(*(rows[c] for c in columns), strict=True):
        for text in dict.fromkeys((availability, related)):
            if text:
                inventory.add(text, event_id)
        times = stated_times(availability, related, date.fromisoformat(day))
        inventory.add_times(times, event_id)
    inventory.statements = len(rows)
    return inventory


# --------------------------------------------------------------------------------------------
# Names: the real ones of the corpus, the fictitious ones, and the replacement
# --------------------------------------------------------------------------------------------


def _vocabulary(words: str) -> frozenset[str]:
    return frozenset(words.split())


NAME_VOCABULARY = _vocabulary(
    """
    acetate acetonide acid adult aerosol america american americas besylate bicarbonate
    bitartrate bromide calcium capsule capsules carbonate care center chewable chloride citrate
    coated company concentrate container continuous corp corporation cream delayed delivery
    inc llc ltd plc gmbh
    development devices dextrose diagnostics dipropionate disodium distribution division dose
    drops elixir emulsion equivalent estimated extended film formerly forming free fumarate gel
    generator global gluconate granules health healthcare holder hormone human hyclate
    hydrobromide hydrochloride imaging implant incorporated industries infusion inhalation
    inhalational injectable injection injector institutional international intramuscular
    intravenous iodide kit label laboratories labs lactate limited liquid long lotion
    lyophilized magnesium maleate marketing medical medicine mesylate metered monohydrate
    multi nasal next nitrate north ointment ophthalmic oral owned oxide part partner patch
    pediatric peroxide pharma pharmaceutical pharmaceuticals phosphate plastic plus potassium
    powder preparation preservative private products propionate recombinant recovery release
    replacement research sales sciences sodium solution specialties specialty spray sterile
    strength strips subcutaneous subsidiary succinate sulfate suppositories suppository
    suspension syringe syrup system tablet tablets tartrate technologies technology
    therapeutics topical transdermal usa valerate vial vials water wholly with zinc
    january february march april may june july august september october november december
    """
)
"""Words of drug and company names that name no drug and no company: dosage forms, routes,
salts, corporate words, months. They are never treated as a real name in a notice text."""
PACK_VOCABULARY = _vocabulary(
    """
    a add amber ampoule ampoules ampul ampule ampules ampuls and bag bags base blister blisters
    bottle bottles box boxes bulk by capsule capsules carton cartons cartridge case chewable
    coated concentrate container containing contains count counts cream ct delayed diluent dose
    doses drops each ea eq equivalent extended fill filled film fl flexible fliptop for forming
    free g gel glass gm gram grams granules in individual infusion inj injectable injection
    intravenous iu iv kit l liquid lock luer lyophilized mci mcg mdv meq metered mg ml mmol
    month months multi multidose multiple ndc ndcs of ointment one ophthalmic oral oz pack
    package packages packets patch pen per pharmacy pint pk plastic powder pre prefilled
    preservative release sdv single sol solution spray sterile strength strips supplied
    suppositories suppository suspension syringe syringes syrup tab tablet tablets tabs
    topical tray tube two u ug unit units use usp vial vials with x
    """
)
"""The words a Presentation keeps: units, containers, pack words and dosage forms."""
ORDINARY_GENERICS = 3
"""A word of a name is ordinary, and never taken for a name, when notices of this many other
drugs write it in lower case."""
CORPORATE_WORDS = (
    "Pharmaceuticals|Pharmaceutical|Pharmacal|Pharma|Laboratories|Labs|Inc|LLC|Ltd|Corp"
    "|Corporation|Healthcare|Therapeutics|Biosciences|Biopharma"
)
_CORPORATE_HEAD = re.compile(rf"((?:[A-Z][\w'-]*(?:\s+&)?\s+){{1,4}})(?=(?:{CORPORATE_WORDS})\b)")
_BRAND = re.compile(r"([A-Za-z][\w-]*)\s?(?:[®™]|\((?:R|TM)\))")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_WEB = re.compile(r"(?:https?://|www\.)[^\s,;)]+")
_PHONE = re.compile(r"(?<![\d-])(?:1[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?![\d-])")
_NDC = re.compile(r"(?<![\d-])\d{3,5}-{1,2}\d{2,4}-\d{1,4}(?![\d-])|(?<!\d)\d{10,11}(?!\d)")
NDC_SHAPES = ((4, 4, 2), (5, 3, 2), (5, 4, 1), (5, 4, 2))  # as corpus.extract_ndcs reads them
_WORD = re.compile(r"[A-Za-z]+")
DRUG_SYLLABLES = (
    (
        *("Bre", "Cal", "Dov", "Eln", "Fir", "Gav", "Hul", "Isk", "Jor", "Kel", "Lum", "Mor"),
        *("Nev", "Ost", "Pav", "Quel", "Ruv", "Sab", "Tov", "Ulv", "Vax", "Wen", "Yar", "Zil"),
    ),
    ("a", "e", "i", "o", "u", "ar", "en", "il", "or", "um"),
    ("dran", "vex", "tane", "lox", "brin", "quel", "sant", "tril", "phor", "vane"),
)
COMPANY_SYLLABLES = (
    (
        *("Ald", "Bran", "Corv", "Dun", "Elk", "Fen", "Garr", "Hax", "Ing", "Jes", "Kirk", "Lang"),
        *("Mert", "Nor", "Oak", "Pell", "Quin", "Rad", "Stan", "Thorn", "Ux", "Vey", "Wyn", "Yeld"),
    ),
    ("",),
    ("wick", "mere", "stead", "croft", "holt", "combe", "thorpe", "leigh", "bury", "garth"),
)
COMPANY_ENDINGS = ("Pharma", "Laboratories", "Pharmaceuticals", "Therapeutics")
DOSAGE_FORMS = (
    "Injection",
    "Tablets",
    "Tablet",
    "Capsules",
    "Capsule",
    "Ophthalmic Solution",
    "Ophthalmic Ointment",
    "Ophthalmic Emulsion",
    "Injectable Suspension",
    "Injectable Emulsion",
    "Oral Solution",
    "Oral Suspension",
    "Solution",
    "Suspension",
    "Ointment",
    "Cream",
    "Gel",
    "Strips",
)


def fictitious_names(kind: str) -> tuple[str, ...]:
    """The fixed list of invented names of one kind (``drug`` or ``company``): every
    combination of its syllables, in the seeded order."""
    first, middle, last = DRUG_SYLLABLES if kind == "drug" else COMPANY_SYLLABLES
    names = [a + b + c for a in first for b in middle for c in last]
    return tuple(shuffled(names, f"fictitious/{kind}"))


def words_of(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text)}


def ndc_matches(text: str) -> list[re.Match[str]]:
    """The NDCs in a text: three groups of digits in a shape the codes have, or any such group
    or run of ten or eleven digits right after "NDC"."""
    found = []
    for match in _NDC.finditer(text):
        shape = tuple(len(part) for part in re.split(r"-+", match.group()))
        after_label = re.search(r"NDCs?[\s#:(]*$", text[: match.start()]) is not None
        if shape in NDC_SHAPES or after_label:
            found.append(match)
    return found


@dataclass(frozen=True)
class NameLexicon:
    """The real names of the corpus: every drug and company name in full, the words that can
    stand for one in a notice text, the NDCs, and the invented names that touch none of it."""

    names: frozenset[str]
    words: frozenset[str]
    brands: frozenset[str]
    ndcs: frozenset[str]
    drugs: tuple[str, ...]
    companies: tuple[str, ...]

    def hits(self, text: str) -> list[re.Match[str]]:
        """The words of ``text`` that are words of a real name. A word of three letters, and a
        word known only from the Presentations, counts only when it is written with a
        capital."""
        found = []
        for m in _WORD.finditer(text):
            word = m.group()
            named = word.lower() in self.words and (len(word) > 3 or word[0].isupper())
            if named or (word.lower() in self.brands and word[0].isupper()):
                found.append(m)
        return found


def name_lexicon(events: pd.DataFrame) -> NameLexicon:
    """The real names of the corpus, from the name columns and the Presentations of every event
    (names only: no outcome is read).

    A word of a name can stand for it when it has three letters or more, is not in
    ``NAME_VOCABULARY`` and is not ordinary: written in lower case in the train-period notices
    of ``ORDINARY_GENERICS`` drugs whose own names do not hold it. A capitalised word of a
    Presentation that the Presentation of an item would not keep is taken for a brand name
    under the same conditions, where a notice writes it with a capital. An invented name is
    free when it is no word of any name, Presentation or notice text of the corpus and holds no
    real name word of five letters or more.
    """
    ev = S.check_events(events)
    named: set[str] = set()
    for column in ("generic_name", "company_name"):
        for name in ev[column].unique():
            named |= {w for w in words_of(name) if len(w) >= 3}
    branded: set[str] = set()
    for text in ev["presentation"].unique():
        branded |= {
            w.lower()
            for w in re.findall(r"(?<![A-Za-z])[A-Z][A-Za-z]{3,}", text)
            if w.lower() not in PACK_VOCABULARY
        }
    lower: dict[str, set[str]] = {}
    train = ev.loc[ev["event_date"] < TEST_START.isoformat()]
    columns = ("generic_id", "generic_name", "availability_text", "related_text")
    for generic, name, *texts in zip(*(train[c] for c in columns), strict=True):
        own = words_of(name)
        for text in texts:
            for word in re.findall(r"(?<![A-Za-z])[a-z]{3,}(?![A-Za-z])", text):
                if word not in own:
                    lower.setdefault(word, set()).add(generic)
    ordinary = {word for word, generics in lower.items() if len(generics) >= ORDINARY_GENERICS}
    words = named - NAME_VOCABULARY - ordinary
    brands = branded - named - NAME_VOCABULARY - ordinary
    seen: set[str] = set()
    text_columns = ("availability_text", "related_text", "reason_for_shortage")
    for column in ("generic_name", "company_name", "presentation", *text_columns):
        for text in ev[column].unique():
            seen |= words_of(text)
    long_words = [w for w in words | brands if len(w) > 4]

    def free(kind: str) -> tuple[str, ...]:
        return tuple(
            name
            for name in fictitious_names(kind)
            if name.lower() not in seen and not any(w in name.lower() for w in long_words)
        )

    return NameLexicon(
        names=frozenset(
            C.norm_text(n) for c in ("generic_name", "company_name") for n in ev[c].unique() if n
        ),
        words=frozenset(words),
        brands=frozenset(brands),
        ndcs=frozenset(
            m.group() for text in ev["presentation"].unique() for m in ndc_matches(text)
        ),
        drugs=free("drug"),
        companies=free("company"),
    )


def _digits(tag: str, like: str) -> str:
    """Seeded digits in the place of the digits of ``like``."""
    stream = iter(str(int(draw_key(tag, like), 16)))
    return "".join(next(stream) if char.isdigit() else char for char in like)


def fictitious_ndc(code: str, tag: str, lexicon: NameLexicon) -> str:
    """An invented NDC of the same shape: a labeler code of zeros, which no labeler has, and
    seeded digits after it."""
    labeler, dash, rest = code.partition("-")
    made = (
        "0" * 5 + _digits(tag, code[5:])
        if not dash
        else "0" * len(labeler) + dash + _digits(tag, rest)
    )
    if made in lexicon.ndcs:
        raise ValueError(f"the invented NDC {made} is one of the corpus")
    return made


def fictitious_drug(real: str, stem: str) -> str:
    """The invented drug name: the stem, with the first dosage form the real name gives, when
    this module knows it."""
    found = [(real.lower().find(f.lower()), -len(f), f) for f in DOSAGE_FORMS]
    form = min((hit for hit in found if hit[0] >= 0), default=(0, 0, ""))[2]
    return f"{stem} {form}".strip()


def _balanced(text: str) -> str:
    """The text without the brackets that lost their partner."""
    for opening, closing in (("([", ")]"), (")]", "([")):
        depth, kept = 0, []
        for char in text:
            if char in opening:
                depth += 1
            elif char in closing:
                if depth == 0:
                    continue
                depth -= 1
            kept.append(char)
        text = "".join(kept)[::-1]
    return text


def neutral_presentation(text: str, tag: str, lexicon: NameLexicon) -> str:
    """A Presentation without names: invented NDC digits, and of the other chunks only those
    whose words are all in ``PACK_VOCABULARY`` (numbers, units, containers)."""
    spans = [
        (m.start(), m.end(), fictitious_ndc(m.group(), tag, lexicon)) for m in ndc_matches(text)
    ]
    for start, end, new in sorted(spans, reverse=True):
        text = text[:start] + new + text[end:]
    kept = [
        chunk
        for chunk in text.split()
        if all(word.lower() in PACK_VOCABULARY for word in _WORD.findall(chunk))
    ]
    out = re.sub(r"\(\s*\)|\[\s*\]", "", _balanced(" ".join(kept)))
    out = re.sub(r"\s+([,;)\]])", r"\1", re.sub(r"\s+", " ", out))
    return re.sub(
        r"^(?:(?:and|of|in|with|for|per|by)\s+)+", "", out.strip(" ,;/"), flags=re.IGNORECASE
    )


@dataclass
class Renamer:
    """The fictitious names of one seed: its drug, its company, and a further invented name for
    every other real name its texts mention. ``log`` lists what was replaced."""

    seed_id: str
    lexicon: NameLexicon
    drug: str
    company: str
    own_drug: frozenset[str]
    own_company: frozenset[str]
    spare: list[str]
    given: dict[str, str] = field(default_factory=dict)
    log: list[tuple[str, str, str]] = field(default_factory=list)

    def name_for(self, word: str) -> str:
        key = word.lower()
        if key in self.own_company:
            made = self.company
        elif key in self.own_drug:
            made = self.drug
        else:
            if key not in self.given:
                self.given[key] = self.spare.pop(0)
            made = self.given[key]
        if word.isupper() and len(word) > 1:
            return made.upper()
        return made.lower() if word.islower() else made

    def text(self, field_name: str, text: str) -> str:
        """A notice text with every real name, address and number replaced."""
        tag = f"names/{self.seed_id}"
        site = self.company.lower()
        swaps: list[tuple[int, int, str]] = []

        def add(start: int, end: int, new: str) -> None:
            if not any(a < end and start < b for a, b, _ in swaps):
                swaps.append((start, end, new))

        for m in _EMAIL.finditer(text):
            add(m.start(), m.end(), f"info@{site}.example")
        for m in _WEB.finditer(text):
            add(m.start(), m.end(), f"www.{site}.example")
        for m in _PHONE.finditer(text):
            add(m.start(), m.end(), "1-800-555-01" + _digits(tag, m.group())[-2:])
        for m in ndc_matches(text):
            add(m.start(), m.end(), fictitious_ndc(m.group(), tag, self.lexicon))
        for m in _BRAND.finditer(text):
            add(m.start(1), m.end(1), self.name_for(m.group(1)))
        hits = self.lexicon.hits(text)
        for m in _CORPORATE_HEAD.finditer(text):
            head = m.group(1).rstrip()
            end = m.start(1) + len(head)
            known = any(m.start(1) <= h.start() < end for h in hits)
            if not known and not words_of(head) & NAME_VOCABULARY:
                add(m.start(1), end, self.name_for(head))
        for m in hits:
            add(m.start(), m.end(), self.name_for(m.group()))
        out = text
        for start, end, new in sorted(swaps, reverse=True):
            self.log.append((field_name, text[start:end], new))
            out = out[:start] + new + out[end:]
        for name in {self.drug, self.company, *self.given.values()}:
            out = re.sub(rf"\b({name})(?:\s+\1\b)+", r"\1", out, flags=re.IGNORECASE)
        return out


def renamed_fields(
    row: Mapping[str, str], seed_id: str, lexicon: NameLexicon, taken: set[str]
) -> tuple[dict[str, str], Renamer]:
    """The entry of a seed with fictitious names, in the keys of the reading harness.

    The names of a seed are the first free ones in a seeded order of its own, so a seed keeps
    its names when other seeds join or leave the list, unless an earlier seed takes them."""

    def in_order(kind: str, names: Sequence[str]) -> list[str]:
        order = sorted(names, key=lambda n: draw_key(f"name/{kind}/{seed_id}", n))
        return [name for name in order if name not in taken]

    drugs, companies = in_order("drug", lexicon.drugs), in_order("company", lexicon.companies)
    stem, company = drugs[0], companies[0]
    ending = COMPANY_ENDINGS[int(draw_key("ending", seed_id), 16) % len(COMPANY_ENDINGS)]
    renamer = Renamer(
        seed_id=seed_id,
        lexicon=lexicon,
        drug=stem,
        company=company,
        own_drug=frozenset(words_of(row["generic_name"]) & lexicon.words),
        own_company=frozenset(words_of(row["company_name"]) & lexicon.words),
        spare=companies[1:],
    )
    item = S.harness_item(row, "")
    del item["item_id"]
    item["generic_name"] = fictitious_drug(row["generic_name"], stem)
    item["company_name"] = f"{company} {ending}"
    item["presentation"] = neutral_presentation(row["presentation"], f"names/{seed_id}", lexicon)
    for name in (*TEXT_FIELDS, "reason_for_shortage"):
        item[name] = renamer.text(name, item[name])
    taken |= {stem, company, *renamer.given.values()}
    return item, renamer


def real_name_hits(item: Mapping[str, str], lexicon: NameLexicon) -> list[str]:
    """Every trace of a real name in an item (empty when it is clean): a full drug or company
    name of the corpus, a word of one in a name or text field, a Presentation word outside
    ``PACK_VOCABULARY``, or an NDC of the corpus."""
    found = []
    for key in ("generic_name", "company_name", *TEXT_FIELDS, "reason_for_shortage"):
        text = f" {C.norm_text(item[key])} "
        found += [f"{key}: {n}" for n in sorted(lexicon.names) if len(n) > 8 and f" {n} " in text]
        found += [f"{key}: {m.group()}" for m in lexicon.hits(item[key])]
        found += [
            f"{key}: {m.group()}" for m in _EMAIL.finditer(item[key]) if ".example" not in m.group()
        ]
    odd = [w for w in _WORD.findall(item["presentation"]) if w.lower() not in PACK_VOCABULARY]
    found += [f"presentation: {w}" for w in odd]
    for key in ("presentation", *TEXT_FIELDS):
        found += [
            f"{key}: {m.group()}" for m in ndc_matches(item[key]) if m.group() in lexicon.ndcs
        ]
    return found


# --------------------------------------------------------------------------------------------
# Gold, seeds and edits
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Gold:
    """A literal reading in the fields of AUDIT_GUIDE.md section 3.4, with the stale flag."""

    statement_type: str
    start: str = ""
    end: str = ""
    abstain_reason: str = ""
    certainty: str = ""
    stale: bool = False
    quote: str = ""
    distractor_roles: tuple[str, ...] = ()
    distractor_quotes: tuple[str, ...] = ()

    @property
    def abstain(self) -> bool:
        return not self.start

    def compared(self) -> dict[str, str]:
        """The fields the cross-check compares, as text."""
        return {
            "statement_type": self.statement_type,
            "interval": f"{self.start} to {self.end}" if self.start else "abstain",
            "abstain_reason": self.abstain_reason,
            "certainty": self.certainty,
            "stale": "1" if self.stale else "0",
            "distractor_roles": "; ".join(sorted(self.distractor_roles)),
        }


def rule_gold(text: str, anchor: date) -> Gold:
    """The frozen rule reading of a statement text, in the gold's fields: the reference reading
    of a seed, and the cross-check of an item. "Available until" counts as depletion, as type
    and as distractor role (AUDIT_GUIDE.md, appendix B, D9 and D17)."""
    reading = R.read(text, anchor)
    literal = R.as_literal_v1(reading)
    interval = literal["interval"]
    dated = isinstance(interval, dict)
    return Gold(
        statement_type=literal["statement_type"],
        start=interval["start"] if dated else "",
        end=interval["end"] if dated else "",
        abstain_reason="" if dated else (reading.abstain_reason or ""),
        certainty=literal["certainty"],
        stale=bool(literal["stale"]),
        quote=literal["quote"],
        distractor_roles=tuple(
            "depletion" if d["role"] == "availability_until" else d["role"]
            for d in reading.distractor_dates
        ),
        distractor_quotes=tuple(d["text"] for d in reading.distractor_dates),
    )


def item_text(fields: Mapping[str, str]) -> str:
    """The statement text of an item, joined as the corpus builder joins the two fields."""
    return C.statement_text(fields["availability_information"], fields["related_information"])


def item_anchor(fields: Mapping[str, str]) -> date:
    return date.fromisoformat(fields["date_of_update"])


@dataclass(frozen=True)
class Mention:
    """One statement the rule reader finds in a seed, and where its time or marker stands."""

    name: str
    start: int
    end: int
    statement_type: str


@dataclass(frozen=True)
class Seed:
    """A seed statement ready to be edited: its entry with fictitious names, its reference
    reading, where the target's time stands, and what that time is."""

    seed_id: str
    event_id: str
    period: str
    form: str
    fields: dict[str, str]
    gold: Gold
    name: str
    span: tuple[int, int]
    bound: str
    no_year: bool
    time: Time | None
    written: Form | None
    mentions: tuple[Mention, ...]
    bare: bool = False
    """The text has no cue: it is read as a recovery only because it holds a date and at most
    four words (section 3.6), so nothing may be added to it."""

    @property
    def anchor(self) -> date:
        return item_anchor(self.fields)

    @property
    def text(self) -> str:
        return self.fields[self.name]

    @property
    def timex(self) -> str:
        return self.text[self.span[0] : self.span[1]]


def make_seed(
    row: Mapping[str, str], period: str, lexicon: NameLexicon, taken: set[str]
) -> tuple[Seed | None, str, Renamer | None]:
    """The seed of one statement, or the reason it cannot be one."""
    seed_id, anchor = row["statement_group_id"], date.fromisoformat(row["event_date"])
    if C.statement_text(row["availability_text"], row["related_text"]) != row["statement_text"]:
        return None, "the statement text is not the join of the two fields", None
    reference = rule_gold(row["statement_text"], anchor)
    if reference.abstain or reference.statement_type not in ESTIMATE_TYPES:
        return None, "the rule reading has no dated delivery or recovery target", None
    if reference.stale:
        return None, "the seed is stale at issue", None
    if reference.distractor_roles:
        return None, "the seed carries a distractor date", None
    fields, renamer = renamed_fields(row, seed_id, lexicon, taken)
    text = item_text(fields)
    if rule_gold(text, anchor) != reference:
        return None, "replacing the names changes the rule reading", renamer
    reading, form = R.read(text, anchor), F.classify(text, anchor)
    pieces = statement_pieces(fields["availability_information"], fields["related_information"])
    target = locate(pieces, *reading.span) if reading.span else None
    mentions = []
    for st in reading.statements:
        place = locate(pieces, *st["span"])
        if place is None:
            return None, "a statement of the seed is not inside one field", renamer
        mentions.append(Mention(*place, st["statement_type"]))
    if target is None:
        return None, "the target's time is not inside one field", renamer
    name, start, end = target
    if fields[name][start:end].endswith("."):
        end -= 1  # a closing full stop is the sentence's, not the time's
    time = seed_time(form, anchor)
    seed = Seed(
        seed_id=seed_id,
        event_id=row["event_id"],
        period=period,
        form=form.form,
        fields=fields,
        gold=reference,
        name=name,
        span=(start, end),
        bound=form.bound or "",
        no_year=form.no_year,
        time=time,
        written=detect(time, fields[name][start:end]) if time else None,
        mentions=tuple(mentions),
        bare=reading.cue is None,
    )
    return seed, "", renamer


@dataclass(frozen=True)
class Edit:
    """One edited copy of a seed: the factor and level, the entry, its gold by construction,
    what was put into the text, and the notice that attests it."""

    factor: str
    level: str
    fields: dict[str, str]
    gold: Gold
    inserted: str = ""
    form: str = ""
    attested: Attested | None = None


@dataclass(frozen=True)
class Skip:
    """An edit that cannot be made, and why."""

    factor: str
    level: str
    reason: str


def attest(
    inventory: Inventory, fields: Mapping[str, str], name: str, position: int
) -> tuple[Attested, str] | None:
    """The notice that attests the wording of ``fields[name]`` around ``position``, with the
    masked wording that matched; None when no train-period notice has it."""
    hit = inventory.find(fields[name], position)
    units = units_at(fields[name], position)
    if hit is None or units is None:
        return None
    low, high = units[0] if hit.scope == "sentence" else units[1]
    return hit, mask(fields[name][low:high])


def _rank(edit: Edit) -> tuple[int, int]:
    assert edit.attested is not None
    return SCOPES.index(edit.attested.scope), -edit.attested.statements


def _best(edits: Iterable[Edit]) -> list[Edit]:
    """One edit per level: an attested sentence before an attested phrase before a time
    expression attested alone, then the wording more statements hold; the first made wins a
    tie."""
    best: dict[str, Edit] = {}
    for edit in edits:
        old = best.get(edit.level)
        if old is None or _rank(edit) < _rank(old):
            best[edit.level] = edit
    return list(best.values())


def _splice(seed: Seed, start: int, end: int, new: str) -> dict[str, str]:
    return {**seed.fields, seed.name: seed.text[:start] + new + seed.text[end:]}


def _like(seed: Seed, text: str) -> str:
    """A new time expression in the case of the seed's: a capital first when the seed's time
    begins with a part word written so; a capital unit after a capital unit."""
    old = seed.timex
    led = seed.time is not None and seed.time.kind in ("part_of_month", "quarter_part", "year_part")
    if led and old[:1].isupper() and text[:1].islower():
        text = text[:1].upper() + text[1:]
    head, _, last = text.rpartition(" ")
    if head and old.rpartition(" ")[2][:1].isupper() and last[:1].islower() and last.isalpha():
        text = f"{head} {last.capitalize()}"
    return text


def _fresh(seed: Seed, form: Form) -> tuple[date, date] | None:
    """The period of a new writing, when it reads as that period at the seed's date and does
    not end before it; else None."""
    if not reads_as(form, seed.anchor):
        return None
    low, high = time_span(form.time, seed.anchor)
    return (low, high) if high >= seed.anchor else None


def _fits(seed: Seed, form: Form) -> bool:
    """Whether a part word of several words can stand where the seed's time stands: not after
    "in" ("in end of June") and not before "timeframe" ("the end of April timeframe")."""
    if " of" not in (form.attr("word") or ""):
        return True
    start, end = seed.span
    after_in = re.search(r"\bin\s+$", seed.text[:start], re.IGNORECASE)
    framed = re.match(r"\s+time\s?frame", seed.text[end:], re.IGNORECASE)
    return not after_in and not framed


def _time_edit(
    seed: Seed, inventory: Inventory, factor: str, level: str, form: Form, text: str, lead: str = ""
) -> Edit | None:
    """The seed with ``lead`` and ``text`` in the place of its time, when a notice attests the
    result: the sentence, else the phrase, else the time expression ``text`` standing alone. A
    day written without a four-digit year is not looked up alone (its mask is also that of a
    month and a two-digit year)."""
    span = _fresh(seed, form)
    if span is None or not _fits(seed, form):
        return None
    fields = _splice(seed, *seed.span, lead + text)
    found = attest(inventory, fields, seed.name, seed.span[0])
    if found is None:
        unclear = form.time.kind == "day" and form.attr("year") != "yyyy"
        alone = None if unclear else inventory.find_form(text)
        if alone is None:
            return None
        found = (alone, mask(text))
    text = lead + text
    gold = replace(seed.gold, start=span[0].isoformat(), end=span[1].isoformat(), quote=text)
    return Edit(factor, level, fields, gold, text, found[1], found[0])


def surface_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """The same period written another way: one attribute of the writing changes."""
    if seed.time is None or seed.written is None:
        return [Skip("surface_form", "", "the seed's time is not a form this module rewrites")]
    made, tried = [], set()
    for form in forms(seed.time):
        level = surface_level(seed.written, form)
        if level is None or not form.offered or _fresh(seed, form) is None:
            continue
        if not _fits(seed, form):
            continue
        tried.add(level)
        edit = _time_edit(seed, inventory, "surface_form", level, form, _like(seed, form.text))
        if edit is not None:
            assert (edit.gold.start, edit.gold.end) == (seed.gold.start, seed.gold.end)
            made.append(edit)
    best: list[Edit | Skip] = list(_best(made))
    done = {edit.level for edit in made}
    best += [
        Skip("surface_form", level, "no notice attests the wording")
        for level in sorted(tried - done)
    ]
    return best or [Skip("surface_form", "", "no other writing reads as the same period")]


def _other_grains(seed: Seed) -> Iterator[tuple[str, Form]]:
    """The periods at another grain, each in the writing of the seed: the three parts of the
    seed's month, quarter or year, the range of its month and the next, and its quarter."""
    time, written = seed.time, seed.written
    assert time is not None and written is not None
    keep = [k for k in ("name", "sep", "year", "order") if written.attr(k) is not None]
    if time.kind in ("month", "quarter"):
        inner = "part_of_month" if time.kind == "month" else "quarter_part"
        for part in PARTS:
            for form in forms(replace(time, kind=inner, part=part)):
                if same_writing(written, form, keep):
                    yield part, form
    if time.kind in ("part_of_month", "quarter_part", "year_part"):
        for part in PARTS:
            for form in forms(replace(time, part=part)):
                if part != time.part and same_writing(written, form, keep):
                    yield part, form
    if time.kind == "month":
        if time.month < 12:
            wider = Time("month_range", time.year, time.month, last_month=time.month + 1)
            for form in forms(wider):
                if same_writing(written, form, ("name", "year")):
                    yield "range", form
        quarter = Time("quarter", time.year, quarter=(time.month + 2) // 3)
        for form in forms(quarter):
            if form.attr("year") == written.attr("year"):
                yield "quarter", form


def granularity_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """Another period at another grain, and "the <month> timeframe" (the same period, C15),
    led in by "in" where no preposition stands before the time."""
    kinds = ("month", "part_of_month", "quarter", "quarter_part", "year_part")
    if seed.time is None or seed.written is None or seed.time.kind not in kinds:
        return [Skip("granularity", "", "the seed's time has no finer or coarser grain here")]
    made, tried = [], set()
    start, end = seed.span
    framed = re.match(r"\s+time\s?frame", seed.text[end:], re.IGNORECASE)
    for level, form in _other_grains(seed):
        if form.offered and _fresh(seed, form) is not None and _fits(seed, form):
            tried.add(level)
            text = _like(seed, form.text)
            edit = _time_edit(seed, inventory, "granularity", level, form, text)
            made += [edit] if edit is not None else []
    if seed.time.kind == "month" and not framed:
        tried.add("timeframe")
        before = seed.text[:start]
        frame = TIMEFRAMES[1] if re.search(r"\bthe\s+$", before, re.IGNORECASE) else TIMEFRAMES[0]
        lead = "" if frame == TIMEFRAMES[1] or _PREPOSITION.search(before) else "in "
        text = frame.format(seed.timex)
        edit = _time_edit(seed, inventory, "granularity", "timeframe", seed.written, text, lead)
        made += [edit] if edit is not None else []
    best: list[Edit | Skip] = list(_best(made))
    done = {edit.level for edit in made}
    best += [
        Skip("granularity", level, "no notice attests the wording")
        for level in sorted(tried - done)
    ]
    return best or [Skip("granularity", "", "every other grain would end before the date")]


HEDGE_WORDS = ("estimated", "expected", "anticipated")
_HEDGE = re.compile(  # the closed list of section 3.8
    r"\b(?:estimat\w*|est\b\.?|expect\w*|anticipat\w*|project\w*|predict\w*|target\w*"
    r"|tentativ\w*|approx\w*|eta\b|on or near\b|around\b|about\b|likely\b|should\b)",
    re.IGNORECASE,
)
_LEAD_IN = re.compile(r"(?:\b(?:in|by|for|on|of|until|through|is|the)\s+)+$", re.IGNORECASE)
_HEDGED_LEAD_IN = re.compile(
    r"\b(?:estimated|expected|anticipated)\s+(?:(?:in|by|for|on|of|until|through|is|the)\s+)*$",
    re.IGNORECASE,
)
UNKNOWN_FILLS = (
    "TBD",
    "to be determined",
    "unknown",
    "unknown at this time",
    "date not available at this time",
    "not available at this time",
    "date unknown",
)
SENTENCES = {
    "as_released": ("Product will be made available as it is released",),
    "no_estimated_date": (
        "No estimated release date at this time",
        "No estimated release date available",
        "No release date available at this time",
    ),
}
SENTENCE_REASON = {"as_released": "no_date", "no_estimated_date": "tbd"}
_STATUS = re.compile(
    r"\b(?:allocat\w*|back[\s-]?order\w*|unavailable|limited|out of stock|stock\s?out|shortage"
    r"|intermittent|interrupt\w*|constrain\w*|in stock|available)\b",
    re.IGNORECASE,
)
"""Words that say how supply stands. A sentence that holds one is not replaced as a whole: its
status wording would go with it (the second error row of section 7.3)."""


def _in_case(word: str, like: str) -> str:
    if len(like) > 1 and like.isupper():
        return word.upper()
    return word.capitalize() if like[:1].isupper() else word


def hedge_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """A hedge on the target: put before the time, before the words that lead into it, or at
    the head of its phrase when the sentence has no hedge; in the place of the one hedge of the
    three when it has that one."""
    text, (start, _) = seed.text, seed.span
    units = units_at(text, start)
    assert units is not None
    sentence, phrase = units
    hedges = list(_HEDGE.finditer(text, sentence[0], start))
    options: list[tuple[str, str, int]] = []
    if not hedges and seed.gold.certainty != "asserted":
        return [Skip("certainty", "", "the target's hedge does not stand before its time")]
    if not hedges:
        lead_in = _LEAD_IN.search(text, phrase[0], start)
        head = text[phrase[0] : phrase[0] + 2]
        for word in HEDGE_WORDS:
            options.append((word, f"{text[:start]}{word} {text[start:]}", start))
            if lead_in:
                cut = lead_in.start()
                options.append((word, f"{text[:cut]}{word} {text[cut:]}", cut))
            lowered = (
                head[:1].lower() + head[1:] if head[:1].isupper() and not head.isupper() else head
            )
            first = _in_case(word, head[:1])
            new = f"{text[: phrase[0]]}{first} {lowered}{text[phrase[0] + 2 :]}"
            options.append((word, new, phrase[0]))
    elif len(hedges) == 1 and hedges[0].group().lower() in HEDGE_WORDS:
        old = hedges[0]
        for word in HEDGE_WORDS:
            if word != old.group().lower():
                new = text[: old.start()] + _in_case(word, old.group()) + text[old.end() :]
                options.append((word, new, old.start()))
    else:
        return [Skip("certainty", "", "the target carries a hedge that is none of the three")]
    made = []
    for word, new, position in options:
        fields = {**seed.fields, seed.name: new}
        found = attest(inventory, fields, seed.name, position)
        if found is not None:
            gold = replace(seed.gold, certainty="estimated")
            made.append(Edit("certainty", word, fields, gold, word, found[1], found[0]))
    best: list[Edit | Skip] = list(_best(made))
    done = {edit.level for edit in made}
    best += [
        Skip("certainty", word, "no notice attests the wording")
        for word in HEDGE_WORDS
        if word not in done and any(word == option[0] for option in options)
    ]
    return best


def unknown_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """An unknown marker in the place of the target's time, or a sentence that gives no time in
    the place of the target's sentence."""
    kind = seed.gold.statement_type
    if sum(m.statement_type == kind for m in seed.mentions) != 1:
        reason = "the seed makes another statement of the target's type"
        return [
            Skip("certainty", level, reason)
            for level in ("tbd", "no_estimated_date", "as_released")
        ]
    text, (start, end) = seed.text, seed.span
    units = units_at(text, start)
    assert units is not None
    sentence, phrase = units
    out: list[Edit | Skip] = []
    cuts = {start}
    for pattern in (_LEAD_IN, _HEDGED_LEAD_IN):
        match = pattern.search(text, phrase[0], start)
        cuts |= {match.start()} if match else set()
    made = []
    for cut in sorted(cuts, reverse=True):
        for fill in UNKNOWN_FILLS:
            fields = {**seed.fields, seed.name: text[:cut] + fill + text[end:]}
            found = attest(inventory, fields, seed.name, cut)
            if found is not None:
                gold = Gold(kind, abstain_reason="tbd", certainty="undetermined", quote=fill)
                made.append(Edit("certainty", "tbd", fields, gold, fill, found[1], found[0]))
    out += _best(made) or [Skip("certainty", "tbd", "no notice attests the wording")]
    alone = len(seed.mentions) == 1 and phrases(text, *sentence) == [phrase]
    alone = alone and not _STATUS.search(text, sentence[0], sentence[1])
    for level, wordings in SENTENCES.items():
        if kind != "next_delivery" or not alone:
            reason = "the target is not a next delivery stated alone in a sentence of its own"
            out.append(Skip("certainty", level, reason))
            continue
        made = []
        close = text[sentence[1] - 1] if text[sentence[1] - 1] in ".;" else ""
        for wording in wordings:
            new = text[: sentence[0]] + wording + close + text[sentence[1] :]
            fields = {**seed.fields, seed.name: new}
            found = attest(inventory, fields, seed.name, sentence[0])
            if found is not None:
                gold = Gold(
                    kind,
                    abstain_reason=SENTENCE_REASON[level],
                    certainty="undetermined",
                    quote=wording,
                )
                made.append(Edit("certainty", level, fields, gold, wording, found[1], found[0]))
        out += _best(made) or [Skip("certainty", level, "no notice attests the wording")]
    return out


def stale_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """The same text, reverified ``STALE_DAYS`` days after the stated period ended."""
    del inventory  # nothing is inserted
    reason = ""
    if seed.form == "relative":
        reason = "the period is counted from the Date of update"
    elif seed.no_year:
        reason = "the year of the period is read from the Date of update"
    elif seed.bound == "by":
        reason = 'the period starts at the Date of update ("by")'
    later = date.fromisoformat(seed.gold.end) + timedelta(days=STALE_DAYS)
    two_digit = seed.written is not None and seed.written.attr("year") == "yy"
    if seed.written is None and not re.search(r"(?<!\d)(?:19|20)\d\d(?!\d)", seed.timex):
        reason = reason or "the year of the period is not written in four digits"
    if two_digit and not reads_as(seed.written, later):
        reason = reason or "the two-digit year would be read otherwise at the later date"
    if reason:
        return [Skip("stale", "stale", reason)]
    fields = {**seed.fields, "date_of_update": later.isoformat(), "type_of_update": "Reverified"}
    return [Edit("stale", "stale", fields, replace(seed.gold, stale=True))]


DISTRACTOR_SENTENCES = {
    "expiry": (
        "{n} months dating available by request (expiry {m}/{d}/{y})",
        "{n} month expiry ({m}/{y} expiry) dating available by request",
        "{n} month dating (expiry {m}/{d}/{y}) available by request",
        "{n} month dating available by request (expiry {m}/{d}/{y})",
    ),
    "depletion": (
        "Remaining inventory estimated to last until {month} {y}",
        "Remaining inventory estimated to last through {month} {y}",
        "Supply expected to exhaust {month} {y}",
        "Current supply expected to exhaust {month} {y}",
        "Estimated inventory depletion: {month} {y}",
    ),
    "available_until": (
        "Product expected to be available until {month} {y}",
        "Stock anticipated to be available through {month} {y}",
        "Product is available with an expected supply duration until {mon} {y}",
    ),
}
"""Sentences with a date in another role. One is used only when a train-period notice has it."""


def distractor_date(seed: Seed, level: str) -> date | None:
    """The date a distractor sentence gives: for an expiry, the last day of the month
    ``EXPIRY_MONTHS`` after the stated end; for the others, the month before the stated period
    when it has not ended at the Date of update, else the month after the period."""
    low, high = date.fromisoformat(seed.gold.start), date.fromisoformat(seed.gold.end)
    if level == "expiry":
        index = high.year * 12 + high.month - 1 + EXPIRY_MONTHS
        return month_end(index // 12, index % 12 + 1)
    index = low.year * 12 + low.month - 2
    before = month_end(index // 12, index % 12 + 1)
    if before >= seed.anchor:
        return before
    index = high.year * 12 + high.month
    return month_end(index // 12, index % 12 + 1)


def distractor_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """A sentence with a date in another role, put before the Availability information."""
    old = seed.fields["availability_information"]
    if old and not old[0].isupper():
        reason = "the Availability information does not begin with a capital letter"
        return [Skip("distractor", level, reason) for level in DISTRACTOR_SENTENCES]
    out: list[Edit | Skip] = []
    for level, templates in DISTRACTOR_SENTENCES.items():
        day = distractor_date(seed, level)
        assert day is not None
        months = (day.year - seed.anchor.year) * 12 + day.month - seed.anchor.month
        made = []
        for template in shuffled(templates, f"distractor/{seed.seed_id}/{level}"):
            sentence = template.format(
                n=months,
                m=day.month,
                d=day.day,
                y=day.year,
                month=MONTHS[day.month - 1],
                mon=MONTH_ABBREVIATIONS[day.month - 1],
            )
            fields = {**seed.fields, "availability_information": f"{sentence}. {old}".strip()}
            found = attest(inventory, fields, "availability_information", 0)
            dated = months >= 1 or level != "expiry"
            if found is not None and found[0].scope == "sentence" and dated:
                gold = replace(
                    seed.gold,
                    distractor_roles=(DISTRACTOR_ROLE[level],),
                    distractor_quotes=(sentence,),
                )
                made.append(Edit("distractor", level, fields, gold, sentence, found[1], found[0]))
                break
        out += made or [Skip("distractor", level, "no notice attests a sentence of this role")]
    return out


def _cut(text: str, spans: Iterable[tuple[int, int]]) -> str:
    """The text without the spans, tidied: no dangling separator, a capital first."""
    for low, high in sorted(spans, reverse=True):
        text = text[:low] + text[high:]
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\s,;/–—-]+|[\s,;/–—-]+$", "", text)
    return text[:1].upper() + text[1:] if re.search(r"[A-Za-z0-9]", text) else ""


def silent_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    """Every statement about timing removed: a sentence from its first phrase that holds one to
    its end, so that the phrases before it (the status wording) stay."""
    del inventory  # nothing is inserted
    fields = dict(seed.fields)
    for name in TEXT_FIELDS:
        text = fields[name]
        marks = [m.start for m in seed.mentions if m.name == name]
        cuts = []
        spans = sentences(text)
        for n, (low, high) in enumerate(spans):
            inside = [mark for mark in marks if low <= mark < high]
            if not inside:
                continue
            parts = phrases(text, low, high)
            first = next((k for k, (_, b) in enumerate(parts) if min(inside) < b), 0)
            if first == 0:
                cuts.append((low, spans[n + 1][0] if n + 1 < len(spans) else high))
            else:
                closing = text[high - 1] if text[high - 1] in ".;" else ""
                cuts.append((parts[first - 1][1], high - len(closing)))
        fields[name] = _cut(text, cuts) if cuts else text
    if not any(fields[name] for name in TEXT_FIELDS):
        return [Skip("silent", "silent", "nothing would be left in the two text fields")]
    gold = Gold("none", abstain_reason="no_statement", certainty="no_statement")
    return [Edit("silent", "silent", fields, gold)]


def certainty_edits(seed: Seed, inventory: Inventory) -> list[Edit | Skip]:
    return [*hedge_edits(seed, inventory), *unknown_edits(seed, inventory)]


ADD_WORDS = ("certainty", "granularity", "distractor")  # factors whose edits can add words
EDITORS = {
    "certainty": certainty_edits,
    "surface_form": surface_edits,
    "granularity": granularity_edits,
    "stale": stale_edits,
    "distractor": distractor_edits,
    "silent": silent_edits,
}


RESERVED = (
    "the edited text is that of a statement the labellers read, a prompt shows or the guide "
    "works through"
)


def reserved_texts(events: pd.DataFrame, statements: Iterable[str]) -> frozenset[str]:
    """The whole texts of the named statements, as the sampler compares wordings
    (``audit_sample.phrase_key``: the words in order, punctuation aside). A text with no word
    is not among them."""
    ev = S.check_events(events)
    texts = ev.loc[ev["statement_group_id"].isin(set(statements)), "statement_text"].unique()
    return frozenset(S.phrase_key(text) for text in texts) - {""}


def is_reserved(fields: Mapping[str, str], reserved: frozenset[str]) -> bool:
    return S.phrase_key(item_text(fields)) in reserved


def edits_of(
    seed: Seed, inventory: Inventory, reserved: frozenset[str] = frozenset()
) -> tuple[list[Edit], list[Skip]]:
    """Every edit that can be made of a seed, one per factor and level, and what cannot be.
    An edit that leaves the entry as it was is not one, and an edit that turns the text into a
    ``reserved`` one (:func:`reserved_texts`) is not made."""
    made: list[Edit] = []
    skipped: list[Skip] = []
    own = item_text(seed.fields)
    for factor in FACTORS:
        if seed.bare and factor in ADD_WORDS:
            reason = "the seed is read as a recovery only while its text holds a date and no cue"
            skipped.append(Skip(factor, "", reason))
            continue
        for result in EDITORS[factor](seed, inventory):
            if isinstance(result, Skip):
                skipped.append(result)
            elif result.fields == seed.fields:
                skipped.append(Skip(factor, result.level, "the edit changes nothing"))
            elif item_text(result.fields) != own and is_reserved(result.fields, reserved):
                skipped.append(Skip(factor, result.level, RESERVED))
            else:
                made.append(result)
    return made, skipped


# --------------------------------------------------------------------------------------------
# Selection, items, the cross-check and the files of ``generate``
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    """One item of the file: an unedited seed (``edit`` is None) or an edit of one."""

    item_id: str
    seed: Seed
    edit: Edit | None

    @property
    def factor(self) -> str:
        return self.edit.factor if self.edit else SEED_FACTOR

    @property
    def level(self) -> str:
        return self.edit.level if self.edit else SEED_LEVEL

    @property
    def fields(self) -> dict[str, str]:
        return self.edit.fields if self.edit else self.seed.fields

    @property
    def gold(self) -> Gold:
        return self.edit.gold if self.edit else self.seed.gold

    @property
    def period(self) -> str:
        """``test`` when the item is dated 2023-01-01 or later, as the harness reads it: every
        item of a later seed, and a stale item of a train seed whose new date is later."""
        return "test" if item_anchor(self.fields) >= TEST_START else "train"

    def record(self) -> dict[str, Any]:
        """The item as a line of the item file."""
        extra = {
            "seed_id": self.seed.seed_id,
            "factor": self.factor,
            "level": self.level,
            "is_seed": self.edit is None,
            "period": self.period,
            "seed_period": self.seed.period,
        }
        return {
            "item_id": self.item_id,
            **{key: self.fields[key] for key in ITEM_KEYS[1:]},
            **{key: extra[key] for key in ITEM_EXTRA},
        }

    def gold_row(self) -> dict[str, Any]:
        gold, edit = self.gold, self.edit
        attested = edit.attested if edit else None
        return {
            "item_id": self.item_id,
            "seed_id": self.seed.seed_id,
            "factor": self.factor,
            "level": self.level,
            "is_seed": int(edit is None),
            "period": self.period,
            "statement_type": gold.statement_type,
            "start": gold.start,
            "end": gold.end,
            "abstain": int(gold.abstain),
            "abstain_reason": gold.abstain_reason,
            "certainty": gold.certainty,
            "stale": int(gold.stale),
            "quote": gold.quote,
            "distractor_roles": "; ".join(gold.distractor_roles),
            "distractor_quotes": " | ".join(gold.distractor_quotes),
            "gold_source": "construction" if edit else "rule reading of the seed",
            "inserted": edit.inserted if edit else "",
            "form": edit.form if edit else "",
            "attested_scope": attested.scope if attested else "",
            "attested_event_id": attested.event_id if attested else "",
            "attested_text": attested.text if attested else "",
        }


def item_id(seed_id: str, factor: str, level: str) -> str:
    """The id of an item: a seeded hash of its seed, factor and level."""
    return "P" + draw_key("pair", f"{seed_id}/{factor}/{level}")[:10]


def select(
    edits: Mapping[str, Sequence[Edit]], target: int = TARGET_ITEMS
) -> dict[str, list[Edit]]:
    """The edits kept for each seed (see the module docstring, "Selection and size")."""
    counts: Counter[tuple[str, str]] = Counter()
    kept: list[tuple[str, Edit, int]] = []
    for seed_id in shuffled(edits, "select"):
        for factor in FACTORS:
            options = [e for e in edits[seed_id] if e.factor == factor]
            for turn in range(PER_SEED[factor]):
                if not options:
                    break
                tag = f"select/{seed_id}/{factor}"
                options.sort(key=lambda e: (counts[factor, e.level], draw_key(tag, e.level)))
                pick = options.pop(0)
                counts[factor, pick.level] += 1
                kept.append((seed_id, pick, turn))
    while len(edits) + len(kept) > target:
        sizes = Counter(edit.factor for _, edit, _ in kept)
        spare = [row for row in kept if row[2] > 0]
        if not spare:
            break
        largest = max(
            FACTORS,
            key=lambda f: (
                sizes[f] if any(r[1].factor == f for r in spare) else -1,
                -FACTORS.index(f),
            ),
        )
        drop = max(
            (row for row in spare if row[1].factor == largest),
            key=lambda r: (counts[largest, r[1].level], draw_key("trim", f"{r[0]}/{r[1].level}")),
        )
        counts[largest, drop[1].level] -= 1
        kept.remove(drop)
    out: dict[str, list[Edit]] = {seed_id: [] for seed_id in edits}
    for seed_id, edit, _ in kept:
        out[seed_id].append(edit)
    return out


NOT_KEPT = "made but not kept: the seed's share of the factor, or the size of the file"
KNOWN_MISMATCHES = (
    (
        r"\b(?:recovery|release|delivery|availability|resupply|re-supply)\s+\d+"
        r"(?:\s*(?:-|to)\s*\d+)?\s+(?:days?|weeks?|months?)",
        "D18: the rule reader does not read a relative time that follows its cue with no "
        '"in" and no colon',
    ),
    (
        r"\bbackorder\s+for\s+\d+\s+(?:days?|weeks?|months?)",
        'D18: the rule reader does not read "on backorder for N months"',
    ),
)
"""Wordings the guide lists as known mismatches of the frozen rule reader (appendix B, D18)."""


def difference_reason(text: str) -> str:
    """Why the rule reader may differ from the constructed gold on a statement text: a mismatch
    the guide knows (appendix B), or "unexplained", which asks for a look at the item."""
    for pattern, reason in KNOWN_MISMATCHES:
        if re.search(pattern, text, re.IGNORECASE):
            return reason
    return "unexplained"


def rule_check(items: Iterable[Item]) -> list[dict[str, str]]:
    """The cross-check: every field in which the frozen rule reading of an item differs from
    its gold. The unedited seeds are compared too (their gold is the rule reading of the real
    statement; the item is read with its fictitious names)."""
    rows = []
    for item in items:
        gold = item.gold.compared()
        rule = rule_gold(item_text(item.fields), item_anchor(item.fields)).compared()
        for name in gold:
            if gold[name] != rule[name]:
                rows.append(
                    {
                        "item_id": item.item_id,
                        "seed_id": item.seed.seed_id,
                        "factor": item.factor,
                        "level": item.level,
                        "field": name,
                        "gold": gold[name],
                        "rule": rule[name],
                        "reason": difference_reason(item_text(item.fields)),
                    }
                )
    return rows


@dataclass
class Sources:
    """What ``generate`` reads: the events table, the seed list, the guide and the statements
    left out of the attested forms, each with its hash or path."""

    events: pd.DataFrame
    seeds: list[dict[str, str]]
    guide: str
    excluded: set[str]
    record: dict[str, Any]
    reserved: frozenset[str] = frozenset()
    """Whole texts that no edit may produce (:func:`reserved_texts`): those of the labelling
    samples, the in-context pool, the dev prompt items and the rows of the guide's Appendix A."""


@dataclass
class Built:
    """What ``generate`` makes, before it is written."""

    items: list[Item]
    skips: list[dict[str, str]]
    names: list[dict[str, str]]
    check: list[dict[str, str]]
    seeds_used: int
    seeds_dropped: int
    candidates: Counter[tuple[str, str]]
    inventory: Inventory
    lexicon: NameLexicon
    reserved_seeds: tuple[str, ...] = ()
    """Seeds whose own text is a reserved one. They stay: the seed list is drawn by the rule
    of AUDIT_GUIDE.md section 10, which leaves out such a wording only for the labelling
    samples. They are counted, and their stale items carry the same text."""


def build(sources: Sources, target: int = TARGET_ITEMS) -> Built:
    """Seeds, edits, selection and cross-check, from the sources alone. The result does not
    depend on the order of the seed list."""
    events = S.check_events(sources.events).set_index("event_id", drop=False)
    inventory = build_inventory(sources.events, sources.excluded)
    lexicon = name_lexicon(sources.events)
    seeds: dict[str, Seed] = {}
    edits: dict[str, list[Edit]] = {}
    skips: list[dict[str, str]] = []
    names: list[dict[str, str]] = []
    candidates: Counter[tuple[str, str]] = Counter()
    taken: set[str] = set()
    listed = sorted(sources.seeds, key=lambda r: r["statement_group_id"])
    if len({r["statement_group_id"] for r in listed}) != len(listed):
        raise ValueError("the seed list names a statement twice")
    for row in listed:
        seed_id = row["statement_group_id"]
        if row["event_id"] not in events.index:
            raise ValueError(f"the seed {seed_id} names an event that is not in the events table")
        event = events.loc[row["event_id"]]
        if event["statement_group_id"] != seed_id:
            raise ValueError(f"the event of the seed {seed_id} belongs to another statement")
        period = "test" if event["event_date"] >= TEST_START.isoformat() else "train"
        if row.get("period") and row["period"] != period:
            raise ValueError(f"the seed {seed_id} is listed as {row['period']} but dated {period}")
        seed, reason, renamer = make_seed(event, period, lexicon, taken)
        if seed is None:
            skips.append({"seed_id": seed_id, "factor": SEED_FACTOR, "level": "", "reason": reason})
            continue
        assert renamer is not None
        names += [
            {"seed_id": seed_id, "field": name, "found": found, "written": written}
            for name, found, written in renamer.log
        ]
        made, skipped = edits_of(seed, inventory, sources.reserved)
        seeds[seed_id], edits[seed_id] = seed, made
        candidates.update((edit.factor, edit.level) for edit in made)
        skips += [
            {"seed_id": seed_id, "factor": s.factor, "level": s.level, "reason": s.reason}
            for s in skipped
        ]
    kept = select(edits, target)
    items = []
    for seed_id, seed in seeds.items():
        items.append(Item(item_id(seed_id, SEED_FACTOR, SEED_LEVEL), seed, None))
        items += [Item(item_id(seed_id, e.factor, e.level), seed, e) for e in kept[seed_id]]
        dropped = [e for e in edits[seed_id] if e not in kept[seed_id]]
        skips += [
            {
                "seed_id": seed_id,
                "factor": e.factor,
                "level": e.level,
                "reason": NOT_KEPT,
            }
            for e in dropped
        ]
    items.sort(key=lambda item: item.item_id)
    if len({item.item_id for item in items}) != len(items):
        raise ValueError("two items share an id")
    for item in items:
        hits = real_name_hits(item.fields, lexicon)
        if hits:
            raise ValueError(f"item {item.item_id} holds a real name: {hits[:3]}")
    skips.sort(key=lambda r: (r["seed_id"], r["factor"], r["level"], r["reason"]))
    return Built(
        items=items,
        skips=skips,
        names=names,
        check=rule_check(items),
        seeds_used=len(seeds),
        seeds_dropped=len(listed) - len(seeds),
        candidates=candidates,
        inventory=inventory,
        lexicon=lexicon,
        reserved_seeds=tuple(
            seed_id
            for seed_id, seed in sorted(seeds.items())
            if is_reserved(seed.fields, sources.reserved)
        ),
    )


def counts_of(built: Built) -> dict[str, Any]:
    """Counts of the item file: per factor and level, per form and period of the seed, per
    scope of attestation, items per seed, and what was skipped."""
    items = built.items
    edited = [item for item in items if item.edit is not None]
    per_seed = Counter(item.seed.seed_id for item in edited)
    by_level: dict[str, dict[str, int]] = {}
    for factor in (SEED_FACTOR, *FACTORS):
        levels = (SEED_LEVEL,) if factor == SEED_FACTOR else LEVELS[factor]
        tally = Counter(item.level for item in items if item.factor == factor)
        by_level[factor] = {level: tally[level] for level in levels if tally[level]}
    reasons = Counter((r["factor"], r["reason"]) for r in built.skips)
    return {
        "items": len(items),
        "target": TARGET_ITEMS,
        "seeds_listed": built.seeds_used + built.seeds_dropped,
        "seeds_used": built.seeds_used,
        "seeds_dropped": built.seeds_dropped,
        "per_factor": {f: sum(levels.values()) for f, levels in by_level.items()},
        "per_factor_and_level": by_level,
        "levels_with_no_item": {
            f: [level for level in LEVELS[f] if level not in by_level[f]] for f in FACTORS
        },
        "edits_that_could_be_made": {
            f: {
                level: built.candidates[f, level]
                for level in LEVELS[f]
                if built.candidates[f, level]
            }
            for f in FACTORS
        },
        "per_seed_form": dict(sorted(Counter(item.seed.form for item in items).items())),
        "seeds_per_form": dict(
            sorted(Counter(item.seed.form for item in items if item.edit is None).items())
        ),
        "per_period": dict(sorted(Counter(item.period for item in items).items())),
        "per_seed_period": dict(sorted(Counter(item.seed.period for item in items).items())),
        "per_attested_scope": dict(
            sorted(Counter(i.edit.attested.scope for i in edited if i.edit.attested).items())
        ),
        "per_factor_and_scope": {
            f: dict(
                sorted(
                    Counter(
                        i.edit.attested.scope if i.edit.attested else "nothing inserted"
                        for i in edited
                        if i.factor == f
                    ).items()
                )
            )
            for f in FACTORS
        },
        "edited_items_per_seed": {
            "min": min(per_seed.values(), default=0),
            "max": max(per_seed.values(), default=0),
            "mean": round(sum(per_seed.values()) / max(len(per_seed), 1), 2),
        },
        "per_seed_cap": PER_SEED,
        "skipped": [
            {"factor": factor, "reason": reason, "n": n}
            for (factor, reason), n in sorted(reasons.items())
        ],
        "attested_forms": {
            "statements": built.inventory.statements,
            "sentences": len(built.inventory.sentences),
            "phrases": len(built.inventory.phrases),
            "time_expressions": len(built.inventory.forms),
        },
        "text_fields_with_a_name_replaced": len({(r["seed_id"], r["field"]) for r in built.names}),
        "seeds_whose_own_text_is_reserved": list(built.reserved_seeds),
    }


def generate_files(built: Built, sources: Sources) -> tuple[dict[str, str], dict[str, str]]:
    """The files of ``generate`` by name: those of the output folder, and those of the key
    folder (the gold, which would tell a planted item of the audit from a real one, and the
    cross-check, which holds rule readings of the items)."""
    files = {
        ITEMS_FILE: "".join(
            json.dumps(item.record(), ensure_ascii=False) + "\n" for item in built.items
        ),
        COUNTS_FILE: json_text(counts_of(built)),
        SKIPS_FILE: plain_csv(SKIP_COLUMNS, built.skips),
        NAMES_FILE: plain_csv(NAME_COLUMNS, built.names),
    }
    keys = {
        GOLD_FILE: plain_csv(GOLD_COLUMNS, (item.gold_row() for item in built.items)),
        RULE_CHECK_FILE: plain_csv(RULE_CHECK_COLUMNS, built.check),
    }
    manifest = {
        "about": "Minimal pairs for E5; made by analysis.coling.minimal_pairs generate.",
        "seed": SEED,
        "inputs": sources.record,
        "items": len(built.items),
        "item_ids_sha256": sha256_text("".join(f"{item.item_id}\n" for item in built.items)),
        "files": {name: sha256_text(text) for name, text in sorted(files.items())},
        "key_files": {name: sha256_text(text) for name, text in sorted(keys.items())},
        "note": (
            f"{GOLD_FILE} and {RULE_CHECK_FILE} are written to the key folder. The gold of an "
            "item on an audit sheet would show whether the item is planted, and the cross-check "
            "holds rule readings of the items (AUDIT_GUIDE.md, section 2, rule 1). The "
            "annotators open neither; the keys are committed with the scores of task C."
        ),
    }
    files[MANIFEST_FILE] = json_text(manifest)
    return files, keys


def load_sources(args: argparse.Namespace) -> Sources:
    """Events (built in memory from the captures unless ``--events`` names a table), the seed
    list, the guide, the statements left out of the attested forms, and the texts no edit may
    produce."""
    if args.events:
        events = S.load_events(args.events)
        source = {"events": args.events.as_posix(), "events_sha256": sha256_file(args.events)}
    else:
        events = F.events_from_captures(args.captures)
        source = {"events": f"built in memory from {args.captures.as_posix()}"}
    guide = args.guide.read_text(encoding="utf-8")
    listed = set(S.guide_exclusions(guide)) | S.canary_keys(events)
    excluded, unmatched = S.excluded_statements(events, listed)
    worded = S.phrase_statements(events, S.guide_phrases(guide))
    samples: dict[str, str] = {}
    labelled: set[str] = set()
    for name in S.FIRST_SAMPLES:
        path = args.samples / f"sample_{name}.csv"
        if not path.is_file():
            raise SystemExit(f"{path} does not exist: the labelling samples are drawn first")
        labelled |= {row["statement_group_id"] for row in read_csv(path)}
        samples[path.name] = sha256_file(path)
    later = args.later or args.seeds.parent
    prompts: dict[str, str] = {}
    prompted: set[str] = set()
    for name in LATER_LISTS:
        path = later / f"sample_{name}.csv"
        if not path.is_file():
            raise SystemExit(f"{path} does not exist: the lists of prompt items are drawn first")
        prompted |= {row["statement_group_id"] for row in read_csv(path)}
        prompts[path.name] = sha256_file(path)
    reserved = reserved_texts(events, excluded | labelled | prompted)
    rules_sha = sha256_file(Path(R.__file__))
    record = source | {
        "events_fields_sha256": S.events_fields_sha256(events),
        "seed_list": args.seeds.as_posix(),
        "seed_list_sha256": sha256_file(args.seeds),
        "guide": S.guide_stamp(guide),
        "guide_sha256": sha256_text(guide),
        "rules_sha256": rules_sha,
        "rules_is_the_frozen_file": rules_sha.startswith(RULES_SHA256_PREFIX),
        "minimal_pairs_sha256": sha256_file(Path(__file__)),
        "forms_sha256": sha256_file(Path(F.__file__)),
        "corpus_sha256": sha256_file(Path(C.__file__)),
        "audit_sample_sha256": sha256_file(Path(S.__file__)),
        "labelling_samples": samples,
        "prompt_item_lists": prompts,
        "texts_no_edit_may_produce": {
            "statements": len(excluded | labelled | prompted),
            "texts": len(reserved),
        },
        "left_out_of_the_attested_forms": {
            "appendix_a_and_fixed_test_item": len(excluded),
            "appendix_a_rows_matching_no_event": unmatched,
            "whole_text_quoted_in_the_guide": len(worded),
            "labelling_samples": len(labelled),
            "all": len(excluded | worded | labelled),
        },
    }
    left_out = excluded | worded | labelled
    return Sources(events, read_csv(args.seeds), guide, left_out, record, reserved)


def stale_files(root: Path, files: Mapping[str, str]) -> list[str]:
    """The files of ``files`` that are missing under ``root`` or differ from what is there."""
    stale = []
    for name, text in sorted(files.items()):
        path = root / name
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            stale.append(path.as_posix())
    return stale


def write_files(root: Path, files: Mapping[str, str]) -> None:
    for name, text in files.items():
        S.write_text(root, name, text)


def settle(written: Sequence[tuple[Path, Mapping[str, str]]], check: bool) -> int:
    """Write the files, or, for ``--check``, say which of them are not up to date (exit 1)."""
    if not check:
        for root, files in written:
            write_files(root, files)
        return 0
    stale = [name for root, files in written for name in stale_files(root, files)]
    for name in stale:
        print(f"not up to date: {name}")
    print("up to date" if not stale else f"{len(stale)} files are not up to date")
    return 1 if stale else 0


def run_generate(args: argparse.Namespace) -> int:
    sources = load_sources(args)
    if not sources.record["rules_is_the_frozen_file"]:
        raise SystemExit(
            f"rules.py is not the frozen file (sha256 {RULES_SHA256_PREFIX}...): the seeds' "
            "reference readings would not be the registered ones"
        )
    built = build(sources)
    files, keys = generate_files(built, sources)
    status = settle([(args.out, files), (args.keys, keys)], args.check)
    counts = counts_of(built)
    print(f"seeds: {counts['seeds_used']} used, {counts['seeds_dropped']} dropped")
    print(f"items: {counts['items']} (target {TARGET_ITEMS})")
    for factor, levels in counts["per_factor_and_level"].items():
        cells = ", ".join(f"{level} {n}" for level, n in levels.items())
        print(f"  {factor:13s} {counts['per_factor'][factor]:4d}  {cells}")
    for factor, levels in counts["levels_with_no_item"].items():
        if levels:
            print(f"  no item at {factor}: {', '.join(levels)}")
    differ = len({row["item_id"] for row in built.check})
    print(f"items whose rule reading differs from the gold: {differ} (listed in the key folder)")
    if not args.check:
        print(f"wrote {', '.join(sorted(files))} to {args.out.as_posix()}")
    return status


# --------------------------------------------------------------------------------------------
# The audit sample (AUDIT_GUIDE.md section 7.1): draw, assignment, planted items, key
# --------------------------------------------------------------------------------------------


def shown_gold(row: Mapping[str, str]) -> dict[str, str]:
    """The gold columns of the audit sheet from a row of the gold file."""
    return {
        "gold_statement_type": row["statement_type"],
        "gold_start": row["start"],
        "gold_end": row["end"],
        "gold_abstain": str(row["abstain"]),
        "gold_certainty": row["certainty"],
        "gold_stale": str(row["stale"]),
        "gold_distractor_roles": row["distractor_roles"],
    }


def _next_month_end(day: date) -> date:
    index = day.year * 12 + day.month
    return month_end(index // 12, index % 12 + 1)


def corrupt(shown: Mapping[str, str], field_name: str) -> dict[str, str] | None:
    """The gold with one field made wrong, by a fixed rule for each field; None when the rule
    does not apply to this gold.

    * ``type``: recovery and next delivery change places.
    * ``interval``: a part of a month becomes the whole month; any other interval ends on the
      last day of the month after its own.
    * ``certainty``: asserted and estimated change places; undetermined becomes estimated.
    * ``stale``: the flag of a dated item is turned over.
    * ``distractors``: expiry and depletion change places.
    """
    wrong = dict(shown)
    dated = shown["gold_abstain"] == "0"
    if field_name == "type":
        swap = {"recovery": "next_delivery", "next_delivery": "recovery"}
        wrong["gold_statement_type"] = swap.get(shown["gold_statement_type"], "")
        return wrong if wrong["gold_statement_type"] else None
    if field_name == "interval" and dated:
        low, high = date.fromisoformat(shown["gold_start"]), date.fromisoformat(shown["gold_end"])
        whole = (date(low.year, low.month, 1), month_end(low.year, low.month))
        inside = (low.year, low.month) == (high.year, high.month) and (low, high) != whole
        low, high = whole if inside else (low, _next_month_end(high))
        wrong["gold_start"], wrong["gold_end"] = low.isoformat(), high.isoformat()
        return wrong
    if field_name == "certainty":
        swap = {"asserted": "estimated", "estimated": "asserted", "undetermined": "estimated"}
        wrong["gold_certainty"] = swap.get(shown["gold_certainty"], "")
        return wrong if wrong["gold_certainty"] else None
    if field_name == "stale" and dated:
        wrong["gold_stale"] = "0" if shown["gold_stale"] == "1" else "1"
        return wrong
    if field_name == "distractors":
        swap = {"expiry": "depletion", "depletion": "expiry"}
        wrong["gold_distractor_roles"] = swap.get(shown["gold_distractor_roles"], "")
        return wrong if wrong["gold_distractor_roles"] else None
    return None


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


def draw_audit(
    gold: Sequence[Mapping[str, str]], sizes: tuple[int, int, int] = AUDIT_SIZES, round_: int = 1
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """The key of the audit and its stratum table.

    The real items are edited items in equal shares over the six factors (what a factor
    cannot give goes to the factors with the most items left), at most ``MAX_PER_SEED`` per
    seed, each factor in its own seeded order. They are assigned in the order of factor and
    draw, so that each auditor gets every factor. Each auditor then gets planted items from
    the edited items left over, one corrupted field each (``PLANT_FIELDS`` in turn), the first
    in a seeded order to which the corruption applies and whose seed the auditor has not twice
    already. A later ``round_`` (a fresh audit after a failed one, section 7.4) draws in
    another seeded order."""
    own, shared, planted = sizes
    draw = "audit" if round_ == 1 else f"audit{round_}"
    pool = {row["item_id"]: row for row in gold if str(row["is_seed"]) == "0"}
    by_factor = {
        f: shuffled((i for i, r in pool.items() if r["factor"] == f), f"{draw}/{f}")
        for f in FACTORS
    }
    n_real = 2 * own + shared
    base, extra = divmod(n_real, len(FACTORS))
    richest = sorted(FACTORS, key=lambda f: (-len(by_factor[f]), FACTORS.index(f)))
    quota = {f: base + (1 if f in richest[:extra] else 0) for f in FACTORS}
    per_seed: Counter[str] = Counter()
    drawn: dict[str, list[str]] = {f: [] for f in FACTORS}

    def take(factor: str, k: int) -> int:
        got = 0
        for candidate in by_factor[factor]:
            seed_id = pool[candidate]["seed_id"]
            if got >= k:
                break
            if candidate not in drawn[factor] and per_seed[seed_id] < MAX_PER_SEED:
                drawn[factor].append(candidate)
                per_seed[seed_id] += 1
                got += 1
        return got

    short = 0
    for factor in sorted(FACTORS, key=lambda f: (len(by_factor[f]), FACTORS.index(f))):
        short += quota[factor] - take(factor, quota[factor])
    for factor in richest:
        if short <= 0:
            break
        short -= take(factor, short)
    real = [i for f in FACTORS for i in drawn[f]]
    who = dict(zip(real, assign(len(real), own, shared), strict=True))
    rows = []
    for pair_id in real:
        row, shown = pool[pair_id], shown_gold(pool[pair_id])
        rows.append(
            {
                **{k: row[k] for k in ("seed_id", "factor", "level")},
                "pair_id": pair_id,
                "assigned_to": who[pair_id],
                "planted": 0,
                "planted_field": "",
                **{f"true_{k}": v for k, v in shown.items()},
                **{f"shown_{k}": v for k, v in shown.items()},
            }
        )
    used = set(real)
    for auditor in AUDITORS:
        seen = Counter(pool[i]["seed_id"] for i in real if who[i] in (auditor, SHARED))
        for n in range(planted):
            field_name = PLANT_FIELDS[n % len(PLANT_FIELDS)]
            tag = f"{draw}/planted/{auditor}/{field_name}/{n}"
            for candidate in shuffled(set(pool) - used, tag):
                row, shown = pool[candidate], shown_gold(pool[candidate])
                wrong = corrupt(shown, field_name)
                if wrong is None or seen[row["seed_id"]] >= MAX_PER_SEED:
                    continue
                used.add(candidate)
                seen[row["seed_id"]] += 1
                rows.append(
                    {
                        **{k: row[k] for k in ("seed_id", "factor", "level")},
                        "pair_id": candidate,
                        "assigned_to": auditor,
                        "planted": 1,
                        "planted_field": field_name,
                        **{f"true_{k}": v for k, v in shown.items()},
                        **{f"shown_{k}": v for k, v in wrong.items()},
                    }
                )
                break
    strata = [
        {
            "factor": f,
            "pool": len(by_factor[f]),
            "quota": quota[f],
            "drawn": len(drawn[f]),
        }
        for f in FACTORS
    ]
    rows.sort(key=lambda r: r["pair_id"])
    return rows, strata


def read_items(path: Path) -> dict[str, dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {row["item_id"]: row for row in map(json.loads, lines)}


@dataclass
class OnDisk:
    """The item file under the output folder and the gold file under the key folder, checked
    against the manifest of ``generate``."""

    items: dict[str, dict[str, Any]]
    gold: list[dict[str, str]]
    hashes: dict[str, str]


def load_on_disk(root: Path, keys: Path) -> OnDisk:
    """Items and gold as ``generate`` wrote them; stops when they are not the files its
    manifest lists."""
    manifest_path = root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise SystemExit(f"{manifest_path} does not exist: run generate first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {}
    for folder, name, listed in (
        (root, ITEMS_FILE, manifest["files"]),
        (keys, GOLD_FILE, manifest["key_files"]),
    ):
        path = folder / name
        if not path.is_file() or sha256_file(path) != listed[name]:
            raise SystemExit(f"{path} is not the file the manifest of generate records")
        hashes[name] = listed[name]
    return OnDisk(read_items(root / ITEMS_FILE), read_csv(keys / GOLD_FILE), hashes)


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def run_audit_sample(args: argparse.Namespace) -> int:
    disk = load_on_disk(args.out, args.keys)
    sizes = (args.own, args.shared, args.planted)
    rows, strata = draw_audit(disk.gold, sizes, args.round)
    key = plain_csv(KEY_COLUMNS, rows)
    real = [r for r in rows if not r["planted"]]
    manifest = read_manifest(args.out / AUDIT_MANIFEST_FILE)
    entry = {
        "sizes": {"own": args.own, "shared": args.shared, "planted_per_auditor": args.planted},
        "round": args.round,
        "real_items": len(real),
        "planted_items": len(rows) - len(real),
        "strata": strata,
        "max_per_seed": MAX_PER_SEED,
        "items_sha256": disk.hashes[ITEMS_FILE],
        "gold_sha256": disk.hashes[GOLD_FILE],
        "key": (args.keys / KEY_FILE).as_posix(),
        "key_sha256": sha256_text(key),
    }
    manifest = {
        "about": "Task C, the minimal-pair audit; made by analysis.coling.minimal_pairs.",
        "seed": SEED,
        **{k: v for k, v in manifest.items() if k == "sheets"},
        "sample": entry,
    }
    print(f"{'factor':13s} {'pool':>5s} {'quota':>5s} {'drawn':>5s}")
    for row in strata:
        print(f"{row['factor']:13s} {row['pool']:5d} {row['quota']:5d} {row['drawn']:5d}")
    print(f"real items: {len(real)}; planted items: {len(rows) - len(real)}")
    wanted = (2 * args.own + args.shared, len(AUDITORS) * args.planted)
    if (len(real), len(rows) - len(real)) != wanted:
        print(f"warning: the sample is smaller than asked ({wanted[0]} real, {wanted[1]} planted)")
    if args.check:
        on_disk = read_manifest(args.out / AUDIT_MANIFEST_FILE).get("sample")
        stale = stale_files(args.keys, {KEY_FILE: key})
        stale += [] if on_disk == entry else [(args.out / AUDIT_MANIFEST_FILE).as_posix()]
        for name in stale:
            print(f"not up to date: {name}")
        print("up to date" if not stale else f"{len(stale)} files are not up to date")
        return 1 if stale else 0
    handed = manifest.get("sheets", {}).get("key_sha256")
    if handed and handed != entry["key_sha256"] and not args.replace:
        raise SystemExit(
            "sheets were written for another sample; a new key cannot score them. "
            "Nothing was written. Pass --replace to draw again, then write the sheets again"
        )
    if handed and handed != entry["key_sha256"]:
        manifest.pop("sheets")
    write_files(args.keys, {KEY_FILE: key})
    write_files(args.out, {AUDIT_MANIFEST_FILE: json_text(manifest)})
    print(f"wrote the key to {args.keys.as_posix()} and {AUDIT_MANIFEST_FILE}")
    return 0


# --------------------------------------------------------------------------------------------
# Sheets (AUDIT_GUIDE.md section 9, task C)
# --------------------------------------------------------------------------------------------

QUOTED_LINES = ("availability_information", "related_information", "reason_for_shortage")


def entry_block(item: Mapping[str, Any]) -> str:
    """The entry as the models see it (``ENTRY_BLOCK`` of ``read.py``): one line per field, the
    three text fields in quotation marks, an empty field as ``(blank)``."""
    lines = ["Entry"]
    for label, key in ENTRY_LINES:
        text = S.one_line(item[key])
        if key == "date_of_update":
            text = date.fromisoformat(text).isoformat()
        elif key in QUOTED_LINES and text:
            text = f'"{text}"'
        lines.append(f"- {label}: {text or S.BLANK}")
    return "\n".join(lines)


def gold_line(shown: Mapping[str, str]) -> str:
    """A gold on one line, as the sheet shows the seed's."""
    interval = (
        "abstain"
        if shown["gold_abstain"] == "1"
        else f"{shown['gold_start']} to {shown['gold_end']}"
    )
    parts = [
        shown["gold_statement_type"],
        interval,
        shown["gold_certainty"],
        "stale" if shown["gold_stale"] == "1" else "not stale",
        f"distractors: {shown['gold_distractor_roles'] or 'none'}",
    ]
    return "; ".join(parts)


def sheet_rows(
    key: Sequence[Mapping[str, str]], disk: OnDisk, auditor: str
) -> list[dict[str, str]]:
    """The rows of one auditor's sheet, in that auditor's seeded order. A planted item shows
    its corrupted gold and is otherwise a row like any other."""
    gold = {row["item_id"]: row for row in disk.gold}
    seeds = {r["seed_id"]: r["item_id"] for r in disk.gold if str(r["is_seed"]) == "1"}
    mine = {r["pair_id"]: r for r in key if r["assigned_to"] in (auditor, SHARED)}
    rows = []
    for pair_id in shuffled(mine, f"audit/order/{auditor}"):
        entry, truth = mine[pair_id], gold[pair_id]
        seed_item = seeds[entry["seed_id"]]
        rows.append(
            {
                "pair_id": pair_id,
                "seed_id": entry["seed_id"],
                "factor": entry["factor"],
                "level": entry["level"],
                "seed_entry": entry_block(disk.items[seed_item]),
                "seed_gold": gold_line(shown_gold(gold[seed_item])),
                "edited_entry": entry_block(disk.items[pair_id]),
                **{k: entry[f"shown_{k}"] for k in GOLD_SHOWN},
                "attested_text": truth["attested_text"] or NOTHING_INSERTED,
            }
        )
    return rows


def items_text(rows: Sequence[Mapping[str, str]], auditor: str) -> str:
    """The items of a sheet as text, in the order of the sheet; marks go into the CSV sheet."""
    out = [
        f"Task C, minimal pairs: the items of pairs_{auditor}.csv, in the order of the sheet.",
        "",
    ]
    for n, row in enumerate(rows, start=1):
        out += [
            f"=== {n} of {len(rows)}: {row['pair_id']} (seed {row['seed_id']}) ===",
            f"factor: {row['factor']}; level: {row['level']}",
            "",
            "Seed entry",
            *row["seed_entry"].splitlines()[1:],
            f"Seed gold: {row['seed_gold']}",
            "",
            "Edited entry",
            *row["edited_entry"].splitlines()[1:],
            f"Gold of the edited entry: {gold_line(row)}",
            f"Attested text: {row['attested_text']}",
            "",
        ]
    return "\n".join(out)


def build_sheets(key: Sequence[Mapping[str, str]], disk: OnDisk, guide: str) -> dict[str, str]:
    """The blank sheet and the items text of each auditor, by file name."""
    files = {}
    for auditor in AUDITORS:
        rows = sheet_rows(key, disk, auditor)
        meta = [
            ("task", "C minimal-pair audit (AUDIT_GUIDE.md section 7)"),
            ("sheet", "pairs"),
            ("annotator", auditor),
            ("seed", SEED),
            ("guide", S.guide_stamp(guide)),
            ("items", len(rows)),
            ("item file sha256", disk.hashes[ITEMS_FILE][:16]),
            *((f"values of {column}", values) for column, values in SCHEME.items()),
            ("sitting_start", ""),
            ("sitting_end", ""),
        ]
        files[f"pairs_{auditor}.csv"] = S.sheet_text(SHEET_COLUMNS, rows, meta)
        files[f"pairs_{auditor}_items.txt"] = items_text(rows, auditor)
    return files


def holds_marks(path: Path) -> bool:
    """True when a sheet on disk holds a mark or a sitting time: it was filled in place."""
    if not path.is_file():
        return False
    try:
        meta, rows = S.read_sheet(path)
    except (UnicodeDecodeError, csv.Error):
        return True
    timed = any(k in S.SITTING_KEYS and v for k, v in meta)
    return timed or any(row.get(c) for row in rows for c in ENTERED)


def read_key(args: argparse.Namespace) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """The key and the manifest of the audit; stops when the key is not the one the manifest
    records, or was drawn on other item and gold files than those on disk."""
    manifest = read_manifest(args.out / AUDIT_MANIFEST_FILE)
    sample = manifest.get("sample")
    path = args.keys / KEY_FILE
    if not sample or not path.is_file():
        raise SystemExit(f"no audit sample in {args.out} or no key at {path}: run audit-sample")
    if sha256_file(path) != sample["key_sha256"]:
        raise SystemExit(f"{path} is not the key the manifest records")
    return read_csv(path), manifest


def run_sheets(args: argparse.Namespace) -> int:
    disk = load_on_disk(args.out, args.keys)
    key, manifest = read_key(args)
    sample = manifest["sample"]
    if (sample["items_sha256"], sample["gold_sha256"]) != (
        disk.hashes[ITEMS_FILE],
        disk.hashes[GOLD_FILE],
    ):
        raise SystemExit("the sample was drawn on other item and gold files: run audit-sample")
    guide = args.guide.read_text(encoding="utf-8")
    files = build_sheets(key, disk, guide)
    entry = {
        "guide": S.guide_stamp(guide),
        "key_sha256": sample["key_sha256"],
        "items_per_sheet": {a: sum(r["assigned_to"] in (a, SHARED) for r in key) for a in AUDITORS},
        "minutes_per_sheet": {
            a: [
                round(sum(r["assigned_to"] in (a, SHARED) for r in key) * s / 60)
                for s in SECONDS_PER_ITEM
            ]
            for a in AUDITORS
        },
        "files": {name: sha256_text(text) for name, text in sorted(files.items())},
    }
    for auditor in AUDITORS:
        n = entry["items_per_sheet"][auditor]
        plan, low, high = entry["minutes_per_sheet"][auditor]
        print(f"pairs_{auditor}.csv: {n} items, about {plan} minutes ({low} to {high})")
    if args.check:
        stale = stale_files(args.out, files)
        stale += (
            [] if manifest.get("sheets") == entry else [(args.out / AUDIT_MANIFEST_FILE).as_posix()]
        )
        for name in stale:
            print(f"not up to date: {name}")
        print("up to date" if not stale else f"{len(stale)} files are not up to date")
        return 1 if stale else 0
    filled = [p for a in AUDITORS if holds_marks(p := args.out / f"pairs_{a}.csv")]
    if filled:
        raise SystemExit(
            f"{', '.join(p.as_posix() for p in filled)}: the sheet holds marks or a sitting "
            "time (it was filled in place). Nothing was written. Move it out of the folder "
            "(external_data/annotation/pairs/) and run the command again"
        )
    write_files(args.out, files)
    write_files(args.out, {AUDIT_MANIFEST_FILE: json_text({**manifest, "sheets": entry})})
    print(f"wrote {', '.join(sorted(files))} to {args.out.as_posix()}")
    return 0


# --------------------------------------------------------------------------------------------
# Validator and scorer (AUDIT_GUIDE.md sections 7.2, 7.4 and 8.3)
# --------------------------------------------------------------------------------------------


@dataclass
class Checked:
    """A sheet after validation: the marks by item, errors and warnings, minutes."""

    marks: dict[str, dict[str, str]]
    errors: list[str]
    warnings: list[str]
    minutes: int | None
    meta: list[tuple[str, str]]

    @property
    def ok(self) -> bool:
        return not self.errors


def _same(a: str, b: str) -> bool:
    """Two shown cells are the same text, whatever the line ends and spaces."""
    return " ".join(S.unguarded(a).split()) == " ".join(S.unguarded(b).split())


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
        return Checked({}, [f"sheet: {problem}"], [], None, meta)
    minutes, problems = S.sittings(meta)
    errors += problems
    seen = Counter(row["pair_id"] for row in rows)
    handed = {S.unguarded(b["pair_id"]): b for b in blank} if blank is not None else None
    for n, row in enumerate(rows, start=1):
        where = f"row {n} ({row['pair_id'] or 'no pair_id'})"
        if not row["pair_id"] or seen[row["pair_id"]] > 1:
            errors.append(f"{where}: pair_id is missing or repeated")
            continue
        if handed is not None:
            if row["pair_id"] not in handed:
                errors.append(f"{where}: this item is not in the blank sheet")
                continue
            changed = [c for c in SHOWN if not _same(row[c], handed[row["pair_id"]].get(c) or "")]
            if changed:
                errors.append(
                    f"{where}: shown cells changed ({', '.join(changed)}); "
                    "import every column as text and leave the shown columns as they are"
                )
        bad = [c for c in (*ERROR_CHECKS, "natural") if row[c] not in ("0", "1")]
        if bad:
            errors.append(f"{where}: {', '.join(bad)} must be 1 or 0")
            continue
        if any(row[c] == "0" for c in CHECKS) and not row["correct_value"]:
            errors.append(f"{where}: a label check is 0 but correct_value is empty")
        if (row["minimal"] == "0" or row["attested"] == "0") and not row["note"]:
            errors.append(f"{where}: minimal or attested is 0 but note is empty")
        if row["correct_value"] and all(row[c] == "1" for c in CHECKS):
            warnings.append(f"{where}: correct_value is given but every label check is 1")
        marks[row["pair_id"]] = {c: row[c] for c in ENTERED}
    if handed is not None:
        lost = sorted(set(handed) - set(seen))
        errors += (
            [f"sheet: {len(lost)} items of the blank sheet are missing: {lost[:5]}"] if lost else []
        )
    else:
        warnings.append(S.NO_BLANK)
    return Checked(marks, errors, warnings, minutes, meta)


def check_file(sheet: Path, blank: Path | None, root: Path = OUT) -> Checked:
    """Validate the sheet at ``sheet`` against its blank: the one given, or the file
    ``pairs_<annotator>.csv`` under ``root`` that the sheet's header names. A sheet that is the
    blank's own file was filled in place and is refused."""
    try:
        meta, rows = S.read_sheet(sheet)
    except UnicodeDecodeError:
        return Checked({}, [S.NOT_UTF8], [], None, [])
    if blank is None:
        annotator = S.meta_value(meta, "annotator")
        beside = root / f"pairs_{annotator}.csv"
        blank = beside if annotator in AUDITORS and beside.is_file() else None
    if blank is not None and blank.resolve() == sheet.resolve():
        message = "sheet: this is the blank sheet itself; fill a copy kept elsewhere"
        return Checked({}, [message], [], None, meta)
    handed = S.read_sheet(blank)[1] if blank is not None else None
    return validate_sheet(meta, rows, handed)


def report_check(sheet: Path, checked: Checked) -> int:
    for line in checked.errors:
        print(f"error: {line}")
    for line in checked.warnings:
        print(f"warning: {line}")
    state = "ok" if checked.ok else f"{len(checked.errors)} errors"
    minutes = "" if checked.minutes is None else f", {checked.minutes} minutes"
    print(f"{sheet}: {len(checked.marks)} rows read, {state}{minutes}")
    return 0 if checked.ok else 1


def run_validate(args: argparse.Namespace) -> int:
    return report_check(args.sheet, check_file(args.sheet, args.blank, args.out))


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


def verdict(marks: Mapping[str, str]) -> str:
    """``error`` when a label check, ``minimal`` or ``attested`` is 0 (section 7.2)."""
    return "error" if any(marks[c] == "0" for c in ERROR_CHECKS) else "ok"


def failed(marks: Mapping[str, str]) -> list[str]:
    return [c for c in ERROR_CHECKS if marks[c] == "0"]


PLANT_CHECK = dict(zip(PLANT_FIELDS, CHECKS, strict=True))


def adjudication_rows(
    key: Sequence[Mapping[str, str]],
    sheets: Mapping[str, Checked],
    shown: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    """One row for every real item and auditor that marked it an error."""
    rows = []
    for entry in sorted(key, key=lambda r: r["pair_id"]):
        if str(entry["planted"]) == "1":
            continue
        for auditor in AUDITORS:
            marks = sheets[auditor].marks.get(entry["pair_id"])
            if marks is None or verdict(marks) == "ok":
                continue
            cells = shown[entry["pair_id"]]
            rows.append(
                {
                    **{c: cells.get(c, "") for c in ADJUDICATION_SHOWN},
                    "reported_by": auditor,
                    "failed_checks": "; ".join(failed(marks)),
                    "correct_value": marks["correct_value"],
                    "note": marks["note"],
                }
            )
    return rows


def check_adjudication(
    filled: Sequence[Mapping[str, str]], wanted: Sequence[Mapping[str, str]]
) -> list[str]:
    """What is wrong with a filled adjudication sheet (empty when it can be scored)."""
    errors = []
    ids = lambda rows: sorted((r["pair_id"], r["reported_by"]) for r in rows)  # noqa: E731
    if ids(filled) != ids(wanted):
        errors.append("the adjudication sheet does not hold the rows that were reported")
    for row in filled:
        where = f"{row['pair_id']} ({row['reported_by']})"
        if row.get("decision") not in DECISIONS:
            errors.append(f"{where}: decision must be one of {', '.join(DECISIONS)}")
            continue
        checks = S.split_list(row.get("confirmed_checks", ""))
        if any(c not in ERROR_CHECKS for c in checks):
            errors.append(f"{where}: confirmed_checks takes {', '.join(ERROR_CHECKS)}")
        if row["decision"] == "confirmed" and not checks:
            errors.append(f"{where}: a confirmed error needs its confirmed_checks")
        if row["decision"] != "confirmed" and checks:
            errors.append(f"{where}: confirmed_checks is given but the error is not confirmed")
    return errors


def pass_count(n_real: int) -> int:
    """How many real items must be free of confirmed errors: 95% of them, rounded up."""
    return -(-PASS_PERCENT * n_real // 100)


def score(
    key: Sequence[Mapping[str, str]],
    sheets: Mapping[str, Checked],
    adjudicated: Sequence[Mapping[str, str]] | None,
) -> dict[str, Any]:
    """The statistics of section 8.3 and, once the adjudication is in, the pass rule of 7.4."""
    real = [r for r in key if str(r["planted"]) == "0"]
    planted = [r for r in key if str(r["planted"]) == "1"]
    result: dict[str, Any] = {"real_items": len(real), "planted_items": len(planted)}
    reported: dict[str, Counter[str]] = {a: Counter() for a in AUDITORS}
    unnatural: Counter[str] = Counter()
    verdicts: dict[str, dict[str, str]] = {}
    for entry in real:
        for auditor in AUDITORS:
            marks = sheets[auditor].marks.get(entry["pair_id"])
            if marks is not None:
                verdicts.setdefault(entry["pair_id"], {})[auditor] = verdict(marks)
                reported[auditor].update(failed(marks))
                unnatural[auditor] += marks["natural"] == "0"
    result["reported"] = {
        auditor: {
            "items_marked_error": sum(v.get(auditor) == "error" for v in verdicts.values()),
            "failed_checks": {c: reported[auditor][c] for c in ERROR_CHECKS},
            "natural_0": unnatural[auditor],
        }
        for auditor in AUDITORS
    }
    both = [(v[AUDITORS[0]], v[AUDITORS[1]]) for v in verdicts.values() if len(v) == 2]
    result["double_audited"] = {
        "n": len(both),
        "raw_agreement": round(sum(a == b for a, b in both) / len(both), 4) if both else None,
        "kappa": cohen_kappa(both) if len({v for pair in both for v in pair}) > 1 else None,
    }
    result["planted"] = {}
    for auditor in AUDITORS:
        mine = [r for r in planted if r["assigned_to"] == auditor]
        caught = [r for r in mine if verdict(sheets[auditor].marks[r["pair_id"]]) == "error"]
        on_field = [
            r
            for r in caught
            if sheets[auditor].marks[r["pair_id"]][PLANT_CHECK[r["planted_field"]]] == "0"
        ]
        result["planted"][auditor] = {
            "n": len(mine),
            "caught": len(caught),
            "caught_on_the_corrupted_field": len(on_field),
            "missed": sorted(r["pair_id"] for r in mine if r not in caught),
            "recheck_own_items": len(mine) - len(caught) >= PLANTED_MISS_LIMIT,
        }
    result["minutes"] = {a: sheets[a].minutes for a in AUDITORS}
    result["seconds_per_item"] = {
        a: round(60 * sheets[a].minutes / len(sheets[a].marks), 1)
        if sheets[a].minutes and sheets[a].marks
        else None
        for a in AUDITORS
    }
    if adjudicated is None:
        result["status"] = "adjudication pending"
        return result
    confirmed: dict[str, set[str]] = {}
    unresolved = set()
    for row in adjudicated:
        if row["decision"] == "confirmed":
            confirmed.setdefault(row["pair_id"], set()).update(
                S.split_list(row["confirmed_checks"])
            )
        elif row["decision"] == "unresolved":
            unresolved.add(row["pair_id"])
    free = len(real) - len(confirmed)
    by_factor = {}
    for factor in FACTORS:
        ids = [r["pair_id"] for r in real if r["factor"] == factor]
        clean = sum(i not in confirmed for i in ids)
        by_factor[factor] = {
            "n": len(ids),
            "free_of_confirmed_errors": clean,
            "wilson95": wilson(clean, len(ids)),
        }
    result |= {
        "status": "scored",
        "free_of_confirmed_errors": free,
        "share": round(free / len(real), 4) if real else None,
        "wilson95": wilson(free, len(real)),
        "needed": pass_count(len(real)),
        "passed": free >= pass_count(len(real)),
        "confirmed_errors": {i: sorted(checks) for i, checks in sorted(confirmed.items())},
        "confirmed_checks": dict(
            sorted(Counter(c for checks in confirmed.values() for c in checks).items())
        ),
        "unresolved": sorted(unresolved - set(confirmed)),
        "by_factor": by_factor,
    }
    return result


def earlier_passes(path: Path, sheets_sha256: Mapping[str, str]) -> list[dict[str, Any]]:
    """The scores of earlier passes, from the score file on disk: every score it holds of
    other filled sheets than these. An auditor who missed planted items re-checks their own
    items and submits again, and both passes are reported (section 8.3)."""
    if not path.is_file():
        return []
    old = json.loads(path.read_text(encoding="utf-8"))
    kept = list(old.get("earlier_passes", []))
    if old.get("sheets_sha256") != dict(sheets_sha256):
        kept.append({k: v for k, v in old.items() if k != "earlier_passes"})
    return kept


def run_score(args: argparse.Namespace) -> int:
    key, manifest = read_key(args)
    listed = manifest.get("sheets", {}).get("files", {})
    sheets: dict[str, Checked] = {}
    shown: dict[str, dict[str, str]] = {}
    for auditor, path in zip(AUDITORS, (args.a1, args.a2), strict=True):
        blank = args.out / f"pairs_{auditor}.csv"
        if not blank.is_file() or sha256_file(blank) != listed.get(blank.name):
            print(f"error: {blank} is missing or is not the sheet the manifest records")
            return 2
        checked = check_file(path, blank, args.out)
        if S.meta_value(checked.meta, "annotator") != auditor and checked.ok:
            checked.errors.append(f"sheet: this is not the sheet of {auditor}")
        mine = {r["pair_id"] for r in key if r["assigned_to"] in (auditor, SHARED)}
        if checked.ok and set(checked.marks) != mine:
            checked.errors.append("sheet: its items are not those the key gives this auditor")
        if report_check(path, checked):
            return 2
        sheets[auditor] = checked
        shown |= {S.unguarded(r["pair_id"]): r for r in S.read_sheet(blank)[1]}
    wanted = adjudication_rows(key, sheets, shown)
    adjudicated = None
    if args.adjudication is not None:
        _, adjudicated = S.read_sheet(args.adjudication)
        problems = check_adjudication(adjudicated, wanted)
        for line in problems:
            print(f"error: {line}")
        if problems:
            return 2
    elif not wanted:
        adjudicated = []
    result = score(key, sheets, adjudicated)
    result["sheets_sha256"] = {
        a: sha256_file(p) for a, p in zip(AUDITORS, (args.a1, args.a2), strict=True)
    }
    result["earlier_passes"] = earlier_passes(args.out / SCORE_FILE, result["sheets_sha256"])
    write_files(args.out, {SCORE_FILE: json_text(result)})
    for auditor in AUDITORS:
        planted = result["planted"][auditor]
        print(f"{auditor}: caught {planted['caught']} of {planted['n']} planted items")
        if planted["recheck_own_items"]:
            print(
                f"{auditor}: missed {PLANTED_MISS_LIMIT} or more; re-check your own real items once"
            )
    if adjudicated is None:
        sheet = args.out / ADJUDICATION_FILE
        if sheet.is_file() and any(r.get("decision") for r in S.read_sheet(sheet)[1]):
            print(f"error: {sheet} holds decisions (it was filled in place); it is not written")
            print("over: move it away and pass it with --adjudication")
            return 2
        meta = [
            ("task", "C minimal-pair audit, adjudication (AUDIT_GUIDE.md sections 5 and 7.4)"),
            ("values of decision", " | ".join(DECISIONS)),
            ("values of confirmed_checks", "; ".join(ERROR_CHECKS) + " (only with confirmed)"),
        ]
        columns = (*ADJUDICATION_SHOWN, *ADJUDICATION_ENTERED)
        write_files(args.out, {ADJUDICATION_FILE: S.sheet_text(columns, wanted, meta)})
        print(f"{len(wanted)} reported errors: fill a copy of {args.out / ADJUDICATION_FILE}")
        print("and run score again with --adjudication")
        return 3
    print(
        f"{result['free_of_confirmed_errors']} of {result['real_items']} real items free of "
        f"confirmed errors (needed {result['needed']}): {'pass' if result['passed'] else 'fail'}"
    )
    return 0 if result["passed"] else 1


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)

    def folders(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--out", type=Path, default=OUT)
        sp.add_argument("--keys", type=Path, default=KEYS, help="where the keys are kept")

    def checkable(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--check", action="store_true", help="write nothing; exit 1 when stale")

    sp = sub.add_parser("generate", help="the item file, the gold and the counts")
    sp.add_argument("--captures", type=Path, default=C.CAPTURES_DIR, help="build events in memory")
    sp.add_argument("--events", type=Path, help="read this events table instead")
    sp.add_argument("--seeds", type=Path, default=SEEDS)
    sp.add_argument("--guide", type=Path, default=GUIDE)
    sp.add_argument("--samples", type=Path, default=SAMPLES, help="lists of the labelling samples")
    sp.add_argument(
        "--later", type=Path, help="lists of the prompt items (default: beside --seeds)"
    )
    folders(sp)
    checkable(sp)
    sp.set_defaults(run=run_generate)

    sp = sub.add_parser("audit-sample", help="draw the task C sample and write its key")
    sp.add_argument("--own", type=int, default=AUDIT_SIZES[0])
    sp.add_argument("--shared", type=int, default=AUDIT_SIZES[1])
    sp.add_argument("--planted", type=int, default=AUDIT_SIZES[2])
    sp.add_argument("--round", type=int, default=1, help="2 for a fresh audit after a failed one")
    sp.add_argument("--replace", action="store_true", help="draw again after sheets were written")
    folders(sp)
    checkable(sp)
    sp.set_defaults(run=run_audit_sample)

    sp = sub.add_parser("sheets", help="write the two blank sheets of task C")
    sp.add_argument("--guide", type=Path, default=GUIDE)
    folders(sp)
    checkable(sp)
    sp.set_defaults(run=run_sheets)

    sp = sub.add_parser("validate", help="check a filled sheet")
    sp.add_argument("sheet", type=Path)
    sp.add_argument("--blank", type=Path, help="the blank sheet (default: found under --out)")
    sp.add_argument("--out", type=Path, default=OUT)
    sp.set_defaults(run=run_validate)

    sp = sub.add_parser("score", help="score the two filled sheets")
    sp.add_argument("--a1", type=Path, required=True)
    sp.add_argument("--a2", type=Path, required=True)
    sp.add_argument("--adjudication", type=Path, help="the filled adjudication sheet")
    folders(sp)
    sp.set_defaults(run=run_score)
    return ap


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(list(argv) if argv is not None else None)
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
