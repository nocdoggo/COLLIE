"""Form classes for statements in FDA drug-shortage notices (PLAN.md section 2.6).

Every statement text gets exactly one *form class*: how the notice writes the time of the next
delivery or of recovery, or why it gives none. The classifier adds no reading rule of its own. It
runs the frozen rule reader (``rules.read``, pinned by ``RULES_SHA256``) and names the result, so
the form, the stated period and the eligibility of a statement all come from one reading.

Inventory and precedence
------------------------
The classes are tested in this order and the first that fits is the form (``FORMS``):

==  ===============  ========================================================================
 #  form             fits when
==  ===============  ========================================================================
 1  relative         the target's time is counted from the Date of Update: "60 days", "3-18
                     months", "within 4 weeks", "this week", "next month", "end of the year"
 2  range            the time runs over several units: "March/April timeframe", "4Q 2021 to
                     1Q 2022", "November 4-6, 2020"
 3  exact_day        one calendar day: "June 5, 2021", "06/05/2021", "by 3/5"
 4  part_of_month    early, mid, late, a half or a week of a month: "late August", "mid- to
                     late-June", "week of 10/28"
 5  half_year        a half of a year: "1H 2022", "the second half of 2020"
 6  quarter          a quarter, or its early, mid or late month: "Q4 2021", "early Q3"
 7  year             a year or a part of one: "2023", "late 2020", "the end of 2022"
 8  month_no_year    a month whose year is not written: "Next release December."
 9  month_year       a month with its year: "December 2022", "Dec-22", "Oct 20" (October 2020)
10  tbd              the target is governed by an unknown marker: "Estimated Recovery: TBD",
                     "Shortage duration is unknown", "No estimated release date"
11  vague            the target's time has no number and no calendar name: "for few months",
                     "long-term backorder", "an extended period"
12  no_date          a delivery is stated with no time at all: "Product will be made
                     available as it is released"
13  discontinuation  the target is a discontinuation, dated or not: "To be discontinued on or
                     near March 2021", "Discontinuation of the manufacture of the drug"
14  distractor       no delivery, recovery or discontinuation target, but a statement or a
                     date in another role: a depletion or "available until" statement (dated
                     or not), expiry dating, a past event
15  silent           the rule reader finds no statement about timing and no date: "On
                     backorder", "Check wholesalers for inventory"
==  ===============  ========================================================================

Classes 1 to 12 need a *target* that is a recovery or a next-delivery statement; the rule reader
chooses the target in the order of the literal prompt (recovery, next delivery, discontinuation,
depletion), and within a type a dated statement beats an unknown marker, which beats a vague or
undated one (three corners differ; see the known limits). So "Next Delivery: May 2021; Estimated
Recovery: TBD" is ``tbd``, and an undated discontinuation beside a dated depletion is
``discontinuation``.

Classes 1 to 9 are the *dated* forms: the target has a period, whose last day is the stated end
(``FormReading.end``). Among them a time counted from the Date of Update is ``relative``
whatever its length, a half-year is not a quarter (the rule reader gives both the granularity
"quarter"), and a part of a month, a quarter, a range or a day written without a year keeps its
own class.

``silent`` is exactly the texts whose rule reading has the statement type "none" and lists no
dated mention. A depletion or "available until" target is ``distractor`` whether it has a date
or not ("Estimated Run Out TBD"), because the text does speak of timing.

Flags and other fields (``FormReading``)
----------------------------------------
* ``no_year``: the target has a period whose year is not written and was taken from the Date of
  Update ("mid-October", "early Q3", "March/April timeframe", "by 3/5"). A month in a list that
  takes the year of a later item ("May and June 2020") has its year written. Always false for
  ``relative``. ``month_no_year`` is the month granularity with this flag set.
* ``distractor_dates``: the number of dated mentions the rule reader lists beside the target
  (expiry, depletion, "available until", discontinuation, onset, past, other). A text can carry
  one whatever its form; ``distractor`` is the class of texts whose only timing is of that kind.
* ``statement_type`` and ``certainty``: the five types and four classes of the literal prompt and
  of ``AUDIT_GUIDE.md`` (availability-until counts as depletion; asserted, estimated,
  undetermined, no_statement), as ``rules.as_literal_v1`` maps them (``STATEMENT_TYPES`` and
  ``CERTAINTIES``). ``rule_statement_type`` and ``rule_certainty`` are the rule reader's own six
  and five.
* ``start``, ``end``, ``granularity``, ``bound``, ``stale``, ``abstain_reason``: the target's
  period as the rule reader read it. ``pattern`` is the entry of ``rules.PATTERNS`` that matched
  the target's time.

Merging small classes
---------------------
A class with fewer than ``MIN_TRAIN`` (15) train-period statements is merged into its neighbour
in ``MERGE_INTO`` for per-form tests and for every table or cell fitted by form::

    relative -> range            half_year -> quarter      vague -> no_date
    range -> month_year          quarter -> month_year     no_date -> tbd
    exact_day -> part_of_month   year -> quarter           tbd -> silent
    part_of_month -> month_year  month_no_year -> month_year
    discontinuation -> distractor                          distractor -> silent

``month_year`` and ``silent`` are never merged away. Classes are examined in inventory order; a
class that is still too small after receiving another is merged on in turn (``merge_map``). The
counts are those of distinct train-period statements (dated before 2023-01-01) on the shortage
listing that are at risk under definition B when first seen, the analysis set of the outcome
experiments. The merged class keeps the name of the class that receives. Samples for the literal
task are stratified on the unmerged classes.

Units and splits
----------------
The unit is the distinct statement of ``corpus.py`` (``statement_group_id``). Its form is read
from the ``statement_text`` of its member with the smallest ``event_id``, anchored at
``event_date``. Splits are by statement date: fit before 2021-01-01, dev to 2022-12-31, test to
2025-12-31, late from 2026-01-01. Populations: every statement, the shortage listing, at risk
under A (status Current when first seen) and at risk under B (also not available); a statement
is at risk when any of its members is.

Known limits (left as they are, because the rule reader is frozen)
-------------------------------------------------------------------
* The statement text leaves out an Availability Information cell that is only a label. A label
  that states a discontinuation or a vague time by itself ("Discontinued", "Long-term
  backorder") is therefore not read, and such a statement is ``silent`` unless its Related
  Information says more.
* A half-year or a season written without a year is not read ("Estimated recovery: 1H" is
  ``silent``); a season with a year is read as the year.
* In "April/May 21" the rule reader takes the year of the range from the Date of Update, not
  from the two digits, so ``no_year`` is set.
* "late this week or early next week" is read as this week (``relative``).
* The rule reader's ranking of targets (``rules._score``) departs from the order above in three
  corners. A dated discontinuation outranks a delivery stated with no time ("as it is
  released") and ties with a delivery under an unknown marker. A discontinuation under an
  unknown marker ties with a delivery stated with no time. A recovery under an unknown marker
  that has no specific cue (a bare "TBD") ties with a vague recovery. In a tie the first
  mentioned wins.

Use from other modules
----------------------
``classify(text, anchor)`` gives the ``FormReading`` of one text; ``statement_forms(events)``
gives one row per statement of an events table; ``load_merge()`` gives the merged class of each
form as written in ``form_counts.json``; ``LABELS`` and ``merged_label`` give the wording for
tables and prompts.

Outputs
-------
* ``out/form_counts.json``: the inventory, the merge table as applied, and counts of statements
  by form, split and population. Counts of texts only; no outcome is read. Its ``no_year`` table
  counts the flag on the dated forms only.
* ``out/rule_readings_train_golden.csv.gz``: the reading of every distinct train-period
  (statement text, statement date) pair, keyed by the first 16 hex characters of the sha256 of
  the text. It pins the behaviour of ``rules.py`` and of this file; ``--check`` and the tests
  recompute it. Texts dated 2023-01-01 or later never enter it. After a rebuild of the events
  table, run ``--check`` before writing: it prints how many readings changed on the pairs that
  the old file and the new table share, which must be none while ``rules.py`` is frozen.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.forms                  # write both outputs
    PYTHONPATH=. python -m analysis.coling.forms --check          # recompute and compare
    PYTHONPATH=. python -m analysis.coling.forms --captures external_data/fda_wayback_csv
    PYTHONPATH=. python -m analysis.coling.forms --text "Next release early Q3." \\
        --anchor 2021-05-19

The default input is ``analysis/coling/out/events.csv.gz``. ``--captures`` builds the events
table in memory from the capture files instead and writes nothing but the two outputs. The
counts file records which of the two it was built from and the command that wrote it, so
``--check`` takes the same flags as the run that wrote it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.coling import rules

RULES_SHA256 = "6a810bcb1ae277b9"
"""First 16 hex characters of the sha256 of the frozen ``rules.py`` this file was built on."""

DEV_START = date(2021, 1, 1)
TEST_START = rules.TEST_START
LATE_START = date(2026, 1, 1)
SPLITS = ("fit", "dev", "test", "late")
TRAIN_SPLITS = ("fit", "dev")
MIN_TRAIN = 15
MERGE_POPULATION = "at_risk_B"
GZIP = {"method": "gzip", "mtime": 0}
OUT = Path("analysis/coling/out")
EVENTS = OUT / "events.csv.gz"
COUNTS = OUT / "form_counts.json"
GOLDEN = OUT / "rule_readings_train_golden.csv.gz"
EVENT_FIELDS = (
    "event_id",
    "statement_group_id",
    "listing",
    "event_date",
    "status_at_statement",
    "availability_class",
    "statement_text",
)
COMMAND = "PYTHONPATH=. python -m analysis.coling.forms"
ESTIMATE_TYPES = ("recovery", "next_delivery")
RELATIVE_PATTERNS = ("relative", "relative_supply", "calendar_relative")
STATEMENT_TYPES = ("recovery", "next_delivery", "depletion", "discontinuation", "none")
"""The five statement types of the literal answer schema, in the schema's order."""
CERTAINTIES = ("asserted", "estimated", "undetermined", "no_statement")
"""The four certainty classes of the literal answer schema, in the schema's order."""


@dataclass(frozen=True, slots=True)
class Form:
    """One class of the inventory: its id, the label shown in tables and prompts, whether it has
    a stated period, and the class it is merged into when it is too small."""

    name: str
    label: str
    dated: bool
    merge_into: str | None


FORMS: tuple[Form, ...] = (
    Form("relative", "a relative time", True, "range"),
    Form("range", "a range", True, "month_year"),
    Form("exact_day", "an exact day", True, "part_of_month"),
    Form("part_of_month", "part of a month", True, "month_year"),
    Form("half_year", "a half-year", True, "quarter"),
    Form("quarter", "a quarter", True, "month_year"),
    Form("year", "a year", True, "quarter"),
    Form("month_no_year", "a month with no year", True, "month_year"),
    Form("month_year", "a month and year", True, None),
    Form("tbd", "TBD or unknown", False, "silent"),
    Form("vague", "a vague time", False, "no_date"),
    Form("no_date", "no time given", False, "tbd"),
    Form("discontinuation", "a discontinuation", False, "distractor"),
    Form("distractor", "a time in another role", False, "silent"),
    Form("silent", "no timing", False, None),
)
FORM_NAMES: tuple[str, ...] = tuple(f.name for f in FORMS)
DATED_FORMS: tuple[str, ...] = tuple(f.name for f in FORMS if f.dated)
LABELS: dict[str, str] = {f.name: f.label for f in FORMS}
MERGE_INTO: dict[str, str] = {f.name: f.merge_into for f in FORMS if f.merge_into}

POPULATIONS: dict[str, str] = {
    "all": "every distinct statement, shortage and discontinuation listings",
    "shortage": "statements on the shortage listing",
    "at_risk_A": "shortage listing, status Current when first seen",
    "at_risk_B": "shortage listing, status Current and not available when first seen (primary)",
}


@dataclass(frozen=True, slots=True)
class FormReading:
    """The form of one statement text with the fields of the rule reading behind it."""

    form: str
    no_year: bool
    distractor_dates: int
    statement_type: str
    certainty: str
    rule_statement_type: str
    rule_certainty: str
    start: str | None
    end: str | None
    granularity: str | None
    bound: str | None
    abstain_reason: str | None
    stale: bool
    pattern: str | None

    @property
    def dated(self) -> bool:
        """True when the statement has a stated period (``end`` is its stated end)."""
        return self.form in DATED_FORMS

    def as_row(self) -> dict[str, Any]:
        """The fields as CSV cells: a missing value is the empty string."""
        return {k: "" if v is None else v for k, v in asdict(self).items()}


GOLDEN_COLUMNS: tuple[str, ...] = ("text_sha256", "anchor", *FormReading.__dataclass_fields__)


# --------------------------------------------------------------------------------------------
# From a rule reading to a form
# --------------------------------------------------------------------------------------------


def _target_match(text: str, anchor: date, span: tuple[int, int]) -> tuple[str, re.Match[str]]:
    """The ``rules.PATTERNS`` entry and match behind the time expression at ``span``.

    ``rules.find_timexes`` keeps, for a span, the first pattern in list order that yields it;
    this walks the list the same way (same skips, same trimming of the span).
    """
    for name, pattern, handler in rules.PATTERNS:
        for m in pattern.finditer(text):
            if m.end() == m.start() or rules._modal_may(m) or handler(m, anchor) is None:
                continue
            s, e = m.span("core") if "core" in pattern.groupindex else m.span()
            while e > s and text[e - 1] in " ,-'/":
                e -= 1
            if (s, e) == span:
                return name, m
    raise ValueError(f"no pattern of rules.PATTERNS yields the span {span} of {text!r}")


def _year_written(name: str, m: re.Match[str], anchor: date, granularity: str) -> bool:
    """True when the matched expression writes its year (four digits, or two read as 20NN)."""
    groups = m.groupdict()
    if any(groups.get(k) for k in ("y", "y1", "y2")):
        return True
    yy = groups.get("yy")
    if yy and rules.two_digit_year(int(yy), anchor):
        return True
    return name == "month_day" and granularity == "month"  # "Oct 20" read as October 2020


_LIST_JOIN = re.compile(r"\s*(?:,\s*)?(?:and|&|,)\s*", re.IGNORECASE)


def _year_from_list(text: str, anchor: date, span: tuple[int, int]) -> bool:
    """True when the yearless month at ``span`` takes its year from a later item of its list.

    Mirrors ``rules._borrow_years``: "May and June 2020", "November, December 2019 and January
    2020". A list that never writes a year ("May and June") lends none.
    """
    timexes = rules.find_timexes(text, anchor)
    i = next((k for k, t in enumerate(timexes) if (t.start, t.end) == span), None)
    while i is not None and i + 1 < len(timexes):
        left, right = timexes[i], timexes[i + 1]
        joined = _LIST_JOIN.fullmatch(text[left.end : right.start])
        if not joined or left.granularity != "month" or re.search(r"\d", left.text):
            return False
        name, m = _target_match(text, anchor, (right.start, right.end))
        if _year_written(name, m, anchor, right.granularity):
            return True
        i += 1
    return False


def _form(r: rules.Reading, pattern: str | None, no_year: bool) -> str:
    """The first class of ``FORMS`` that fits the reading (see the module docstring)."""
    if r.statement_type in ESTIMATE_TYPES:
        if r.interval is None:
            return {"tbd": "tbd", "vague": "vague"}.get(r.abstain_reason or "", "no_date")
        if pattern in RELATIVE_PATTERNS:
            return "relative"
        if r.granularity == "range":
            return "range"
        if r.granularity == "day":
            return "exact_day"
        if r.granularity == "part_of_month":
            return "part_of_month"
        if pattern == "half":
            return "half_year"
        if r.granularity == "quarter":
            return "quarter"
        if r.granularity == "year":
            return "year"
        return "month_no_year" if no_year else "month_year"
    if r.statement_type == "discontinuation":
        return "discontinuation"
    if r.statement_type != "none" or r.distractor_dates:
        return "distractor"  # a depletion or "available until" target, or a date in another role
    return "silent"


@cache
def _classify(text: str, anchor: date) -> FormReading:
    r = rules.read(text, anchor)
    pattern, no_year = None, False
    if r.interval is not None and r.span is not None:
        t = rules.normalise(text)
        span = (r.span[0], r.span[1])
        pattern, m = _target_match(t, anchor, span)
        written = _year_written(pattern, m, anchor, r.granularity or "")
        if not written and pattern == "month_only":
            written = _year_from_list(t, anchor, span)
        no_year = not written and pattern not in RELATIVE_PATTERNS
    v1 = rules.as_literal_v1(r)
    return FormReading(
        form=_form(r, pattern, no_year),
        no_year=no_year,
        distractor_dates=len(r.distractor_dates),
        statement_type=v1["statement_type"],
        certainty=v1["certainty"],
        rule_statement_type=r.statement_type,
        rule_certainty=r.certainty,
        start=r.interval[0] if r.interval else None,
        end=r.interval[1] if r.interval else None,
        granularity=r.granularity,
        bound=r.bound,
        abstain_reason=r.abstain_reason,
        stale=r.stale,
        pattern=pattern,
    )


def classify(text: str | None, anchor: date | str) -> FormReading:
    """The form of one statement text, read at its Date of Update (ISO or MM/DD/YYYY)."""
    if isinstance(anchor, str):
        anchor = rules.parse_anchor(anchor)
    return _classify(text or "", anchor)


def form_class(text: str | None, anchor: date | str) -> str:
    """The form class alone."""
    return classify(text, anchor).form


# --------------------------------------------------------------------------------------------
# Merging small classes
# --------------------------------------------------------------------------------------------


def merge_map(train_counts: Mapping[str, int], minimum: int = MIN_TRAIN) -> dict[str, str]:
    """The merged class of every form, given the train-period count of each form.

    Forms are examined in inventory order. One with fewer than ``minimum`` statements, counting
    what it has received, moves with all it holds into the class its ``MERGE_INTO`` neighbour
    now belongs to; the scan then starts again. ``month_year`` and ``silent`` have no neighbour.
    """
    unknown = sorted(set(train_counts) - set(FORM_NAMES))
    if unknown:
        raise ValueError(f"not in the inventory: {unknown}")
    merged = {name: name for name in FORM_NAMES}
    total = {name: int(train_counts.get(name, 0)) for name in FORM_NAMES}
    while True:
        small = next(
            (n for n in FORM_NAMES if merged[n] == n and total[n] < minimum and n in MERGE_INTO),
            None,
        )
        if small is None:
            return merged
        target = merged[MERGE_INTO[small]]
        total[target] += total[small]
        merged = {n: target if c == small else c for n, c in merged.items()}


def load_merge(path: Path | None = None) -> dict[str, str]:
    """The merged class of every form, as applied in ``form_counts.json``."""
    merged = json.loads((path or COUNTS).read_text())["merge"]["merged_form"]
    if tuple(merged) != FORM_NAMES or not set(merged.values()) <= set(FORM_NAMES):
        raise ValueError(f"{path or COUNTS} does not hold this inventory")
    return merged


def merged_label(members: Iterable[str]) -> str:
    """The label of a merged class: its members' labels in inventory order, joined by "or"."""
    labels = [LABELS[n] for n in FORM_NAMES if n in set(members)]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " or " + labels[-1]


# --------------------------------------------------------------------------------------------
# Statements, splits and counts
# --------------------------------------------------------------------------------------------


def split_of(day: date | str) -> str:
    """fit, dev, test or late, by the statement date."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    if day < DEV_START:
        return "fit"
    if day < TEST_START:
        return "dev"
    return "test" if day < LATE_START else "late"


def text_key(text: str) -> str:
    """First 16 hex characters of the sha256 of a statement text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _fields(events: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in EVENT_FIELDS if c not in events.columns]
    if missing:
        raise ValueError(f"events table lacks {missing}")
    fields = events.loc[:, list(EVENT_FIELDS)].fillna("").astype(str)
    for column in ("event_id", "statement_group_id", "event_date"):
        if (fields[column] == "").any():
            raise ValueError(f"events table has rows with no {column}")
    return fields


def statement_forms(events: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct statement: its date, split, populations and form reading.

    ``member_forms`` counts the distinct forms among the statement's members; it is 1 unless
    members with the same normalised text differ in case or spacing in a way that changes the
    reading.
    """
    ev = _fields(events).sort_values(["statement_group_id", "event_id"], ignore_index=True)
    shortage = ev["listing"] == "shortage"
    current = shortage & (ev["status_at_statement"] == "current")
    ev["at_risk_A"] = current
    ev["at_risk_B"] = current & (ev["availability_class"] != "available")
    ev["form"] = [
        form_class(t, d) for t, d in zip(ev["statement_text"], ev["event_date"], strict=True)
    ]
    groups = ev.groupby("statement_group_id", sort=True)
    first = groups.head(1).set_index("statement_group_id")
    readings = [
        classify(t, d) for t, d in zip(first["statement_text"], first["event_date"], strict=True)
    ]
    out = pd.DataFrame(
        {
            "statement_group_id": first.index,
            "event_id": first["event_id"].to_numpy(),
            "event_date": first["event_date"].to_numpy(),
            "split": [split_of(d) for d in first["event_date"]],
            "listing": first["listing"].to_numpy(),
            "at_risk_A": groups["at_risk_A"].any().to_numpy(),
            "at_risk_B": groups["at_risk_B"].any().to_numpy(),
            "member_forms": groups["form"].nunique().to_numpy(),
        }
    )
    fields = pd.DataFrame([r.as_row() for r in readings], columns=GOLDEN_COLUMNS[2:])
    return pd.concat([out, fields], axis=1)


def _in_population(statements: pd.DataFrame, population: str) -> pd.Series:
    if population == "all":
        return pd.Series(True, index=statements.index)
    if population == "shortage":
        return statements["listing"] == "shortage"
    return statements[population].astype(bool)


def _by_split(values: pd.Series, splits: pd.Series, order: Iterable[str]) -> dict[str, dict]:
    """Counts of ``values`` per split, with train (fit and dev) and all, in the given order."""
    table = pd.crosstab(values, splits)
    out: dict[str, dict] = {}
    for key in order:
        row = {s: int(table.at[key, s]) if key in table.index and s in table else 0 for s in SPLITS}
        row["train"] = sum(row[s] for s in TRAIN_SPLITS)
        row["all"] = sum(row[s] for s in SPLITS)
        out[str(key)] = row
    return out


def _split_totals(splits: pd.Series) -> dict[str, int]:
    row = {s: int((splits == s).sum()) for s in SPLITS}
    row["train"] = sum(row[s] for s in TRAIN_SPLITS)
    row["all"] = sum(row[s] for s in SPLITS)
    return row


def tabulate(statements: pd.DataFrame) -> dict[str, Any]:
    """Counts of statements by form, split and population, with the merge table as applied.

    Every table has one row per class of its fixed list, with zeros where a class is absent, so
    the rows of a table add up to the number of statements whatever the events table holds.
    """
    listed = (("form", FORM_NAMES), ("statement_type", STATEMENT_TYPES), ("certainty", CERTAINTIES))
    for column, allowed in listed:
        unknown = sorted(set(statements[column]) - set(allowed))
        if unknown:
            raise ValueError(f"{column} has values outside its list: {unknown}")
    train = statements["split"].isin(TRAIN_SPLITS)
    base = statements[_in_population(statements, MERGE_POPULATION) & train]
    train_counts = {n: int((base["form"] == n).sum()) for n in FORM_NAMES}
    merged = merge_map(train_counts)
    classes = [n for n in FORM_NAMES if merged[n] == n]
    members = {c: [n for n in FORM_NAMES if merged[n] == c] for c in classes}
    report: dict[str, Any] = {
        "splits": {
            "fit": f"before {DEV_START.isoformat()}",
            "dev": f"{DEV_START.isoformat()} to before {TEST_START.isoformat()}",
            "test": f"{TEST_START.isoformat()} to before {LATE_START.isoformat()}",
            "late": f"{LATE_START.isoformat()} onward",
            "train": "fit and dev",
        },
        "populations": POPULATIONS,
        "inventory": [asdict(f) for f in FORMS],
        "merge": {
            "rule": (
                f"a form with fewer than {MIN_TRAIN} train-period statements in the population "
                f"{MERGE_POPULATION} is merged into its merge_into neighbour, in inventory order"
            ),
            "minimum": MIN_TRAIN,
            "population": MERGE_POPULATION,
            "train_counts": train_counts,
            "merged_form": merged,
            "classes": [
                {"form": c, "members": members[c], "label": merged_label(members[c])}
                for c in classes
            ],
        },
        "statements": {},
        "form": {},
        "merged_form": {},
        "no_year": {},
        "with_distractor_date": {},
        "statement_type": {},
        "certainty": {},
        "statements_with_mixed_member_forms": int((statements["member_forms"] > 1).sum()),
    }
    merged_form = statements["form"].map(merged)
    for population in POPULATIONS:
        keep = _in_population(statements, population)
        sub, splits = statements[keep], statements.loc[keep, "split"]
        report["statements"][population] = _split_totals(splits)
        report["form"][population] = _by_split(sub["form"], splits, FORM_NAMES)
        report["merged_form"][population] = _by_split(merged_form[keep], splits, classes)
        flagged = sub["no_year"].astype(bool)
        report["no_year"][population] = _by_split(
            sub.loc[flagged, "form"], splits[flagged], DATED_FORMS
        )
        report["with_distractor_date"][population] = _split_totals(
            splits[sub["distractor_dates"].astype(int) > 0]
        )
        report["statement_type"][population] = _by_split(
            sub["statement_type"], splits, STATEMENT_TYPES
        )
        report["certainty"][population] = _by_split(sub["certainty"], splits, CERTAINTIES)
    return report


# --------------------------------------------------------------------------------------------
# The golden file of train-period readings
# --------------------------------------------------------------------------------------------


def golden_frame(events: pd.DataFrame) -> pd.DataFrame:
    """The reading of every distinct train-period (statement text, statement date) pair."""
    ev = _fields(events)
    ev = ev[[date.fromisoformat(d) < TEST_START for d in ev["event_date"]]]
    pairs = sorted(set(zip(ev["statement_text"], ev["event_date"], strict=True)))
    rows = [{"text_sha256": text_key(t), "anchor": d, **classify(t, d).as_row()} for t, d in pairs]
    frame = pd.DataFrame(rows, columns=list(GOLDEN_COLUMNS))
    frame = frame.sort_values(["text_sha256", "anchor"], ignore_index=True)
    if frame.duplicated(["text_sha256", "anchor"]).any():
        raise ValueError("two train-period texts share a 16-character sha256 prefix")
    return frame


def gz_bytes(frame: pd.DataFrame) -> bytes:
    """The frame as a gzip CSV with a fixed header time, so equal frames give equal bytes."""
    buffer = io.BytesIO()
    frame.to_csv(buffer, index=False, compression=GZIP, lineterminator="\n")
    return buffer.getvalue()


def read_golden(path: Path = GOLDEN) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def golden_diff(golden: pd.DataFrame, events: pd.DataFrame) -> tuple[list[str], list[str]]:
    """How a golden file differs from a fresh run on the events table.

    The first list holds the pairs both have whose reading changed, which is a change of
    ``rules.py`` or of this file. The second holds the pairs only one of them has, which is a
    change of the events table.
    """
    fresh = golden_frame(events).astype(str)
    old = golden.astype(str)
    if list(old.columns) != list(fresh.columns):
        return [f"columns differ: {list(old.columns)} != {list(fresh.columns)}"], []
    key = ["text_sha256", "anchor"]
    was = {(r["text_sha256"], r["anchor"]): r for r in old.to_dict("records")}
    now = {(r["text_sha256"], r["anchor"]): r for r in fresh.to_dict("records")}
    changed, one_sided = [], []
    for pair in sorted(set(was) | set(now)):
        tag = " ".join(pair)
        if pair not in was or pair not in now:
            side = "golden file" if pair in was else "events table"
            one_sided.append(f"{tag}: only in the {side}")
            continue
        diff = [
            f"{c} {was[pair][c]!r} -> {now[pair][c]!r}"
            for c in GOLDEN_COLUMNS
            if c not in key and was[pair][c] != now[pair][c]
        ]
        if diff:
            changed.append(f"{tag}: " + "; ".join(diff))
    return changed, one_sided


def golden_mismatches(golden: pd.DataFrame, events: pd.DataFrame) -> list[str]:
    """Rows of a golden file that the current code does not reproduce on the events table:
    the changed readings first, then the rows that only one side has."""
    changed, one_sided = golden_diff(golden, events)
    return changed + one_sided


# --------------------------------------------------------------------------------------------
# Inputs, outputs and the command line
# --------------------------------------------------------------------------------------------


def sha16(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def load_events(path: Path = EVENTS) -> pd.DataFrame:
    """The corpus builder's events table, every cell as text."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, usecols=list(EVENT_FIELDS))


def events_from_captures(captures: Path) -> pd.DataFrame:
    """The events table built in memory from the capture files; nothing is written."""
    from analysis.coling.corpus import build_corpus

    text = build_corpus(captures).events.to_csv(index=False)
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def build(
    events: pd.DataFrame, source: Mapping[str, str], command: str = COMMAND
) -> tuple[dict[str, Any], bytes]:
    """The counts report and the golden file's bytes for one events table."""
    frame = golden_frame(events)
    golden = gz_bytes(frame)
    report = {
        "about": "Counts of distinct statements by form class (PLAN.md section 2.6). No outcome.",
        "command": command,
        "inputs": {
            **source,
            "rules_sha256": sha16(Path(rules.__file__).read_bytes()),
            "forms_sha256": sha16(Path(__file__).read_bytes()),
        },
        **tabulate(statement_forms(events)),
        "golden": {"file": GOLDEN.name, "rows": len(frame), "sha256": sha16(golden)},
    }
    return report, golden


def report_text(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=1) + "\n"


def print_summary(report: Mapping[str, Any]) -> None:
    """Counts only: statements by form and split in the primary population, and the merges."""
    population = MERGE_POPULATION
    print(f"statements by form and split, population {population}:")
    print(f"  {'form':16s} " + " ".join(f"{s:>6s}" for s in (*SPLITS, "train", "all")))
    for name, row in report["form"][population].items():
        print(f"  {name:16s} " + " ".join(f"{row[s]:6d}" for s in (*SPLITS, "train", "all")))
    for cls in report["merge"]["classes"]:
        if len(cls["members"]) > 1:
            print(f"merged class {cls['form']}: {', '.join(cls['members'])}")
    print(f"statements with mixed member forms: {report['statements_with_mixed_member_forms']}")
    print(f"golden rows: {report['golden']['rows']} sha256 {report['golden']['sha256']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.forms", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("--events", type=Path, default=EVENTS, help="the events table (csv.gz)")
    ap.add_argument("--captures", type=Path, help="build the events in memory from this folder")
    ap.add_argument("--out", type=Path, default=OUT, help="folder of the two outputs")
    ap.add_argument("--check", action="store_true", help="recompute and compare; write nothing")
    ap.add_argument("--text", help="one statement text to classify (with --anchor)")
    ap.add_argument("--anchor", help="its Date of Update (YYYY-MM-DD or MM/DD/YYYY)")
    args = ap.parse_args(argv)
    if args.text is not None:
        if not args.anchor:
            ap.error("--text needs --anchor")
        print(json.dumps(asdict(classify(args.text, args.anchor)), indent=1))
        return 0
    if sha16(Path(rules.__file__).read_bytes()) != RULES_SHA256:
        print(f"warning: rules.py is not the frozen file ({RULES_SHA256})")
    command = COMMAND
    if args.captures:
        events = events_from_captures(args.captures)
        source = {"events": f"built in memory from {args.captures.as_posix()}"}
        command += f" --captures {args.captures.as_posix()}"
    else:
        events = load_events(args.events)
        source = {
            "events": args.events.as_posix(),
            "events_sha256": sha16(args.events.read_bytes()),
        }
        if args.events != EVENTS:
            command += f" --events {args.events.as_posix()}"
    report, golden = build(events, source, command)
    counts_path, golden_path = args.out / COUNTS.name, args.out / GOLDEN.name
    if args.check:
        stale = []
        if not counts_path.exists() or counts_path.read_text() != report_text(report):
            stale.append(counts_path.as_posix())
        if not golden_path.exists() or golden_path.read_bytes() != golden:
            stale.append(golden_path.as_posix())
            if golden_path.exists():
                changed, one_sided = golden_diff(read_golden(golden_path), events)
                print(
                    f"golden file: readings changed on shared pairs: {len(changed)}; "
                    f"pairs on one side only: {len(one_sided)}"
                )
                for line in (changed + one_sided)[:20]:
                    print(f"  {line}")
        print("up to date" if not stale else "differs from a fresh run: " + ", ".join(stale))
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    counts_path.write_text(report_text(report))
    golden_path.write_bytes(golden)
    print_summary(report)
    print(f"wrote {counts_path} and {golden_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
