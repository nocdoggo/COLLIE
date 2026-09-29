"""Rule-based literal reader for forward-looking estimates in FDA drug-shortage notices.

This is the regex baseline that reviewers expect next to HeidelTime, SUTime and the language
models (E2 of the design memo). It reads one notice text together with its anchor, the row's
"Date of Update", and returns a literal reading. The text may be "Availability Information",
"Related Information" or the corpus's joined statement text (``A || B``); before 2023 most
estimates were written in "Availability Information". The reading::

    {"statement_type": "next_delivery" | "recovery" | "depletion" | "discontinuation"
                       | "availability_until" | "none",
     "interval": [start, end] (inclusive ISO dates) | null,
     "abstain": bool,
     "certainty": "estimated" | "expected" | "anticipated" | "firm" | "unknown",
     "granularity": "day" | "month" | "part_of_month" | "quarter" | "range" | "year" | null,
     "distractor_dates": [{"text", "role", "interval"}, ...],
     "abstain_reason": "tbd" | "no_date" | "vague" | "no_statement" | null,
     "stale": bool, "bound": "by" | "until" | "not_before" | null,
     "cue": str | null, "span": [start, end] | null, "statements": [...]}

:func:`as_literal_v1` maps a reading onto the answer schema of the frozen ``literal-v1`` prompt in
``read.py`` (availability_until -> depletion; firm -> asserted; estimated, expected and
anticipated -> estimated; an interval-less reading -> undetermined or no_statement), so rules
and models are scored by one scorer. The reader is literal: it normalises what the text states,
relative to the anchor, and never applies a slip model or knowledge of what happened. It was
developed on texts dated before 2023-01-01 only (the training period) and is frozen before any
test-period text is scored.

Frozen conventions (the same as ``literal-v1`` wherever that prompt states one)
-------------------------------------------------------------------------------
* ``Month YYYY`` (also ``Mon-YYYY``, ``Mon' YYYY``, ``Month, YYYY``, ``Month of YYYY``,
  ``Mon-YY``, ``Mon 'YY``) is the whole month. A month with no year is the next occurrence on
  or after the anchor month.
* Part of a month: ``early`` / ``beginning of`` / ``start of`` = days 1-10; ``mid`` /
  ``middle of`` = 11-20; ``late`` / ``end of`` / ``Month end`` = 21 to the month's last day;
  ``first half of`` = 1-15, ``second half of`` = 16-end; ``first (1st) week of`` = 1-7, second
  8-14, third 15-21, fourth 22-28, ``last week of`` = the last 7 days; ``week N of Month``
  likewise (week 5 = 29-end); ``week of <date>`` = that date and the 6 days after. Granularity
  ``part_of_month``, also for a span of parts inside one month (``mid- to late-June``).
* Ranges: ``Month-Month YYYY``, ``Month/Month``, ``Month to/through/thru/or Month``, with or
  without parts (``end of June or early July 2021``), run from the start of the first to the
  end of the last; a first month later in the year than the second belongs to the year before
  (``Dec-Jan 2021`` = Dec 2020 to Jan 2021). Granularity ``range``. ``Month and Month`` (or a
  comma list) is several events, not a range: each month is read on its own, and a yearless
  month borrows the year of the next one. ``the Month(-Month) YYYY timeframe`` is the month or
  range.
* Quarters: ``Q4 2027``, ``4Q 2027``, ``4Q27``, ``Q4-2027``, ``Q4/2027``, ``fourth quarter (of)
  2027`` = 1 Oct to 31 Dec; a yearless quarter is the next occurrence on or after the anchor
  quarter. ``early/mid/late/end Qn`` = its first/second/third month (granularity still
  ``quarter``). ``Q3-Q4 2021`` and ``4Q 2021 to 1Q 2022`` are ranges. Halves (``1H 2022``,
  ``H2 2022``, ``second half of 2022``) are Jan-Jun / Jul-Dec, granularity ``quarter``.
* Years: ``2021``, ``in 2021``, ``sometime in 2021`` = the whole year; ``early`` /
  ``beginning of`` = Jan-Apr, ``mid`` / ``middle of`` = May-Aug, ``late`` / ``end (of)`` =
  Sep-Dec (the month convention in thirds). Granularity ``year``.
* Days: ``June 5, 2021``, ``5 June 2021``, ``06/05/2021``, ``6/5/21``, ``18-Sep-2020``,
  ``01Aug2022`` are ``day``; ``June 5-9, 2021`` is a ``range``. In ``Month NN`` (no comma, no
  ordinal) a two-digit ``NN`` whose ``20NN`` lies in [anchor year - 1, anchor year + 3] is a
  year (``anticipated end of Mar 21`` = March 2021, the attested usage), otherwise a day.
  Numeric ``M/YYYY`` (``12/2021 expiry``) is a month.
* Relative durations count from the anchor, a week being 7 days and a month 30 days: ``60
  days`` / ``in 2 weeks`` = the point anchor + N (``day``); ``2-3 months`` = anchor + N to
  anchor + M (``range``); ``within N`` / ``up to N`` / ``over the next N`` = anchor to
  anchor + N (``range``). ``next / this month``, ``end of the month``, ``next year``, ``end of
  the year``, ``next quarter`` are calendar units relative to the anchor. Vague spans (``few
  months``, ``coming weeks``, ``long-term``, ``extended period``, ``soon``) get no interval
  (``abstain_reason = "vague"``).
* Bounds: ``by X``, ``before X``, ``no later than X`` and ``X at the latest`` read as the anchor
  to the end of X (as literal-v1 says), unless X ends before the anchor; ``until`` / ``through``
  and ``not sooner than`` / ``no earlier than`` / ``after`` X read as X. ``bound`` records which.
* ``stale`` is true when the primary interval ends before the anchor.

Statement types and roles. Every date and every abstention marker ("TBD", "to be determined",
"unknown", "no estimated release date", "release date not available at this time", "unable to
provide") gets a role from the nearest cue before it in its clause (clauses end at a full stop
before a capital, ``;`` and ``||``). Specific cues beat the generic ones ("available", "supply");
at equal distance the stronger and then the longer cue wins. A date with no cue after the
previous date of its clause inherits that date's role; a cue right after a date (``12/2021
expiry``, ``March 2020 recovery``) is used when nothing precedes it and no other date follows in
the clause; a short clause with no cue (``Estimated Recovery; November 2021``) takes the
nearest specific cue of the clause before.

* ``recovery``: recover*, resupply / re-supply, restock, back in stock, relaunch, off backorder,
  resum*, return, launch, "(estimated|expected|anticipated|target|initial|product) availability",
  "available for order", shortage duration, "meet / support / fulfil demand", "product
  expected"; and shortage phrases ending in until / through / into right before the date
  (``backorder until``, ``on allocation through``, ``impacted until``, ``not available until``,
  ``limited availability until``): the shortage lasts through X.
* ``next_delivery``: next delivery / release / shipment / batch / lot / supply / replenishment,
  release*, ship*, deliver*, additional lots / units / quantities / stocks, new lots, arriv*,
  replenish*, "scheduled for manufacturing".
* ``depletion``: deplet*, exhaust*, run out, "(expected) to last (through)", unavailability,
  "N months of inventory".
* ``availability_until``: available / availability / supply duration / distribution will
  continue / continue to be sold / stock ... until / through (the gap may not contain a
  shortage word).
* ``discontinuation``: discontinu*, cease*, stop sale / stop shipping, final date / order /
  batch, last order / shipment / batch / distribution, no longer available / supplied, delist*,
  phase out, withdraw*, market exit, distribution to end.
* roles that are never the reading, only distractors: ``expiry`` (expir*, exp., dating, shelf
  life, short-dated), ``onset`` (go on backorder, backorder expected, shortage anticipated
  from), ``past`` (as of, effective, since, initiated, announced, arrived / shipped / received
  in), ``other`` (no cue, or "provide an update in").

"Next Delivery and Estimated Recovery: X" gives both a next_delivery and a recovery statement.
An abstention marker with no cue is a recovery abstention. A clause without a date or marker
gives an undated statement when it states a discontinuation or "product will be made available
as it is released" / "additional lots are scheduled" (``no_date``), or a vague span
(``vague``). A text that is only a date plus at most four words and no cue ("Stocked Out,
December 2021", "Q1 2023") is read as a recovery date.

The primary statement (the top-level fields) follows literal-v1's order: recovery, then
next_delivery, then discontinuation, then depletion (availability_until counts as depletion).
Within recovery an explicit ``recover*`` cue beats resupply-type cues, which beat availability
and shortage-duration cues, which beat until-phrases and generic cues; within every type a dated
statement beats a TBD one, which beats a vague or undated one; next_delivery prefers a ``next
...`` cue; ties go to the first mentioned. ``distractor_dates`` lists every other dated mention
whose role is expiry, depletion, availability_until, discontinuation, onset, past or other and
differs from the primary's type: for a recovery reading these are the depletion, expiry and
"available until" dates of the design.

Certainty is the hedge nearest before the primary date in its segment, else within 25
characters after it: estimat* / est. / ETA / approx* / project* / predict* / target* /
tentativ* / on or near / around / about -> ``estimated``; expect* / likely / should ->
``expected``; anticipat* -> ``anticipated``; none of these (bare labels, "will", "scheduled",
"planned") -> ``firm``; a reading without an interval -> ``unknown``.

Attested forms (training period; both text fields)
--------------------------------------------------
The 40 most frequent masked templates among distinct texts with a timing cue (a month, year,
quarter, relative duration or abstention marker), from ``--inventory`` over the 44 captures on
disk on 2026-09-29 (1,670 distinct texts, 830 templates). Months are masked as <MON>, four-digit
years as <YYYY>, other numbers as <N>; ``n`` counts distinct texts. "ok" means every text of the
template gets the reading the conventions define (checked by hand on the example and by the
outcome counts over the template); pom = part_of_month.

====  ===  ===============================================================  =================
rank    n  template                                                         reading      ok?
====  ===  ===============================================================  =================
   1  182  Next Delivery: <MON> <YYYY>; Estimated Recovery: <MON> <YYYY>    recovery/month ok
   2  154  Limited Supply Available. Next Delivery: <MON> <YYYY>; Estim...  recovery/month ok
   3   45  Next Delivery and Estimated Recovery: <MON> <YYYY>               recovery/month ok
   4   31  Backordered. Next release <MON> <YYYY>.                          next_d./month  ok
   5   31  Limited Supply Available. Next Delivery and Estimated Recov...   recovery/month ok
   6   14  Estimated Availability: <MON> <N>, <YYYY>                        recovery/day   ok
   7   11  <N> month expiry (<N>/<YYYY> expiry) dating available by re...   none+expiry    ok
   8    9  Backorderd. Next release <MON> <YYYY>.                           next_d./month  ok
   9    9  To be discontinued on or near <MON> <YYYY>.                      discont./month ok
  10    8  Additional lots will be scheduled for manufacturing in the ...   next_d./range  ok
  11    8  Backordered. Next release <MON> <YYYY>                           next_d./month  ok
  12    8  Backordered. Next release expected <MON> <YYYY>.                 next_d./month  ok
  13    8  Currently on backorder - next shipment anticipated <MON> <N>     next_d./month  ok
  14    8  Currently on backorder - next shipment anticipated end of <...   next_d./pom    ok
  15    8  Next Delivery: <MON> <YYYY>; Estimated Recovery: TBD             recovery/tbd   ok
  16    8  Next Delivery: <MON> <YYYY>; Estimated recovery: Q<N> <YYYY>     recovery/qtr   ok
  17    8  Recovery <MON> <YYYY>                                            recovery/month ok
  18    7  Currently on backorder - next shipment anticipated in <MON>...   next_d./month  ok
  19    7  Next delivery: <MON> <YYYY>; Estimated recovery: <MON> <YYYY>    recovery/month ok
  20    7  No stock available. Resupply <MON> <YYYY>                        recovery/month ok
  21    7  Unavailable, recovery in <MON> <YYYY>                            recovery/month ok
  22    6  Additional lots are scheduled for manufacturing in the <MON...   next_d./range  ok
  23    6  Additional lots are scheduled to be manufactured in the <MO...   next_d./range  ok
  24    6  Backordered. Estimated availability <MON>-<YYYY>                 recovery/month ok
  25    6  Next Delivery: <MON> <YYYY>; Estimated Recovery: Q<N> <YYYY>     recovery/qtr   ok
  26    6  Next delivery and Estimated recovery: <MON> <YYYY>               recovery/month ok
  27    6  To be discontinued on or near <MON> <YYYY>                       discont./month ok
  28    5  <N> & <N> month expiry (<N>/<YYYY> & <N>/<YYYY> expiry) dat...   next_d.+2 exp. ok
  29    5  <N> months dating available by request. Next release <MON> ...   next_d./month  ok
  30    5  Backordered. Estimated availability <MON> <YYYY>                 recovery/month ok
  31    5  Backordered. Product will be available for order <MON> <N>,...   recovery/day   ok
  32    5  Next Delivery: <MON> <YYYY>; Estimated recovery: TBD             recovery/tbd   ok
  33    5  Partial shipments on allocation through <MON>                    recovery/month ok
  34    5  Supply expected to exhaust late <MON> <YYYY>; Discontinuati...   discont./no_d. ok (1)
  35    4  <N> months expiry (expiry <N>/<N>/<YYYY>) dating available b...  none+expiry    ok
  36    4  <N>, <N>, <N> month expiry available by request. Next relea...   next_d./month  ok
  37    4  A business decision was made to discontinue manufacture of ...   discont./month ok
  38    4  Additional lots will be available in the <MON> <YYYY> timef...   next_d./month  ok
  39    4  Allocating Inventory. Additional lots are scheduled for rel...    next_d./month  ok
  40    4  Available; Additional units expected to release in <MON> <...    next_d./month  ok
====  ===  ===============================================================  =================

(1) literal-v1's order puts discontinuation before depletion, so the reading is an undated
discontinuation and the "exhaust late <MON>" date is listed as a depletion distractor.

Over all 1,670 training texts the reader gives 1,470 dated readings, 110 TBD abstentions, 27
undated statements, 7 vague ones and 56 texts with no statement (mostly expiry-dating notes and
past events). On the corpus builder's statement events (``out/events.csv.gz``, 9,851 training
events), 3,689 of the 3,925 events with a date-like candidate get an interval; the other 236 are
TBD (63), undated (49), vague (28) or no statement (96: expiry dating, "available as of", past
dates), all as the conventions define. Known gaps, left as they are so that the baseline stays a
plain rule reader: narratives with several shortage phases ("limited API supplies till X; new
vendor from Y; better stock situation from Z" is read as the last recovery cue), "Predicted
shortage duration: 2 months, January and February 2021 Resupply: March 2021" (read as the
resupply date), "late this week or early next week" (read as this week), "on allocation for
2020" (no cue), a "TBD" that is a placeholder for a phone number, and lot numbers or strengths
that look like dates.

Usage (from the repository root)::

    python -m analysis.coling.rules --text "Next Delivery: May 2021; Estimated Recovery: TBD" \\
        --anchor 2021-03-05
    python -m analysis.coling.rules --inventory [--split train] [--top 40] [--out inv.json]
    python -m analysis.coling.rules --inventory --split test   # aggregate counts only
    python -m analysis.coling.rules --items items.jsonl --out readings.jsonl

``--items`` takes the JSONL items of ``read.py`` (``item_id``, ``date_of_update``,
``availability_information``, ``related_information``; or ``text`` and ``anchor``) and writes
one line per item with the reading and its ``literal_v1`` form. The two fields are joined as
``availability || related`` (a repeated field once), as the corpus builder joins them.

The test split (Date of Update on or after 2023-01-01) is reported only in aggregate, so that
no test-period template is looked at while the rules could still change.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import io
import json
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

STATEMENT_TYPES = (
    "next_delivery",
    "recovery",
    "depletion",
    "discontinuation",
    "availability_until",
    "none",
)
CERTAINTIES = ("estimated", "expected", "anticipated", "firm", "unknown")
GRANULARITIES = ("day", "month", "part_of_month", "quarter", "range", "year")
DISTRACTOR_ROLES = (
    "expiry",
    "depletion",
    "availability_until",
    "discontinuation",
    "onset",
    "past",
    "other",
)
END_OF_SUPPLY = ("discontinuation", "depletion", "availability_until")
TEST_START = date(2023, 1, 1)
CAPTURES = Path("external_data/fda_wayback_csv")
TEXT_FIELDS = ("Availability Information", "Related Information")
TEXT_KEYS = ("availability_information", "related_information")

# --------------------------------------------------------------------------------------------
# Normalisation and lexical pieces
# --------------------------------------------------------------------------------------------

MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "febuary": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "septemeber": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "novemnber": 11,
    "nov": 11,
    "december": 12,
    "decemer": 12,
    "dec": 12,
}
_MON_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))
# "May" is a month only when capitalised and not a modal verb ("may be", "May experience").
_MAY_VERB = (
    r"be|not|have|also|vary|continue|experience|take|need|result|cause|still|require|occur|"
    r"impact|affect|see|receive|become|change|apply|include|contain|last|run|increase"
)


def _mon(name: str) -> str:
    return (
        rf"(?<![A-Za-z])(?P<{name}>(?:{_MON_ALT})(?![a-z])\.?)"
        rf"(?!(?<=may)\s+(?:{_MAY_VERB})\b)"
    )


_PART_WORDS = {
    "early": "early",
    "beginning of": "early",
    "beginning": "early",
    "start of": "early",
    "the start of": "early",
    "the beginning of": "early",
    "first half of": "h1",
    "mid": "mid",
    "middle of": "mid",
    "the middle of": "mid",
    "middle": "mid",
    "late": "late",
    "end of": "late",
    "the end of": "late",
    "end": "late",
    "latter part of": "late",
    "second half of": "h2",
    "first week of": "w1",
    "1st week of": "w1",
    "second week of": "w2",
    "2nd week of": "w2",
    "third week of": "w3",
    "3rd week of": "w3",
    "fourth week of": "w4",
    "4th week of": "w4",
    "last week of": "wl",
    "the first week of": "w1",
    "the second week of": "w2",
    "the last week of": "wl",
}
_PART_ALT = "|".join(re.escape(p) for p in sorted(_PART_WORDS, key=len, reverse=True))


def _part(name: str) -> str:
    return rf"(?P<{name}>{_PART_ALT})(?![a-z])[\s-]*(?:of\s+)?(?:the\s+)?"


_Y4 = r"20\d\d"
_DAY = r"3[01]|[12]\d|0?[1-9]"
_ORD = r"(?:st|nd|rd|th)?"
_QWORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
_NUMWORD = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}

_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")
_QUOTES = dict.fromkeys(map(ord, "\u2018\u2019\u00b4`"), "'")


def normalise(text: str) -> str:
    """Unify dashes, quotes and whitespace; offsets refer to this normalised text."""
    t = text.translate(_DASHES).translate(_QUOTES).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------------------------------
# Calendar helpers
# --------------------------------------------------------------------------------------------


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def month_span(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), month_end(y, m)


def part_span(y: int, m: int, part: str) -> tuple[date, date]:
    last = calendar.monthrange(y, m)[1]
    lo, hi = {
        "early": (1, 10),
        "mid": (11, 20),
        "late": (21, last),
        "h1": (1, 15),
        "h2": (16, last),
        "w1": (1, 7),
        "w2": (8, 14),
        "w3": (15, 21),
        "w4": (22, 28),
        "w5": (29, last),
        "wl": (last - 6, last),
    }[part]
    return date(y, m, min(lo, last)), date(y, m, min(hi, last))


def infer_year(month: int, anchor: date) -> int:
    """A yearless month is the next occurrence on or after the anchor month."""
    return anchor.year if month >= anchor.month else anchor.year + 1


def two_digit_year(nn: int, anchor: date) -> bool:
    return anchor.year - 1 <= 2000 + nn <= anchor.year + 3


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def quarter_span(y: int, q: int, part: str | None = None) -> tuple[date, date]:
    first = 3 * (q - 1) + 1
    if part in ("early", "mid", "late"):
        m = first + {"early": 0, "mid": 1, "late": 2}[part]
        return month_span(y, m)
    return date(y, first, 1), month_end(y, first + 2)


def year_part_span(y: int, part: str | None) -> tuple[date, date]:
    months = {"early": (1, 4), "mid": (5, 8), "late": (9, 12), "h1": (1, 6), "h2": (7, 12)}
    lo, hi = months.get(part or "", (1, 12))
    return date(y, lo, 1), month_end(y, hi)


# --------------------------------------------------------------------------------------------
# Temporal expressions
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Timex:
    """A normalised temporal expression: inclusive interval, granularity, bound qualifier."""

    start: int
    end: int
    text: str
    lo: date
    hi: date
    granularity: str
    bound: str | None = None

    @property
    def interval(self) -> list[str]:
        return [self.lo.isoformat(), self.hi.isoformat()]


Handler = Callable[[re.Match[str], date], tuple[date, date, str] | None]


def _month_of(m: re.Match[str], name: str) -> int:
    return MONTHS[m.group(name).lower().rstrip(".")]


def _year(m: re.Match[str], name: str, month: int, anchor: date) -> int:
    raw = m.groupdict().get(name)
    if not raw:
        return infer_year(month, anchor)
    return int(raw) if len(raw) == 4 else 2000 + int(raw)


def _numeric_date(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    raw = m.group("y")
    y = int(raw) if len(raw) == 4 else 2000 + int(raw)
    try:
        d = date(y, int(m.group("m")), int(m.group("d")))
    except ValueError:
        return None
    return d, d, "day"


def _numeric_md(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    month = int(m.group("m"))
    try:
        d = date(infer_year(month, anchor), month, int(m.group("d")))
    except ValueError:
        return None
    return d, d, "day"


def _numeric_my(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    return (*month_span(int(m.group("y")), int(m.group("m"))), "month")


def _week_of(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    groups = m.groupdict()
    if groups.get("mn"):
        month = _month_of(m, "mn")
        y = _year(m, "y", month, anchor)
    else:
        month = int(groups["m"])
        raw = groups.get("y")
        y = (int(raw) if len(raw) == 4 else 2000 + int(raw)) if raw else infer_year(month, anchor)
    try:
        d = date(y, month, int(groups["d"]))
    except ValueError:
        return None
    return d, d + timedelta(days=6), "part_of_month"


def _week_n(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    month = _month_of(m, "mon")
    y = _year(m, "y", month, anchor)
    return (*part_span(y, month, f"w{m.group('n')}"), "part_of_month")


def _day_first(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    month = _month_of(m, "mon")
    raw = m.group("y")
    y = int(raw) if len(raw) == 4 else 2000 + int(raw)
    try:
        d = date(y, month, int(m.group("d")))
    except ValueError:
        return None
    return d, d, "day"


def _mon_day(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    month = _month_of(m, "mon")
    day, day2 = int(m.group("d")), m.group("d2")
    bare = not m.group("ord") and not day2 and not m.group("y") and len(m.group("d")) == 2
    if bare and two_digit_year(day, anchor):  # "anticipated Oct 20" = October 2020
        return (*month_span(2000 + day, month), "month")
    y = _year(m, "y", month, anchor)
    try:
        lo = date(y, month, day)
        hi = date(y, month, int(day2)) if day2 else lo
    except ValueError:
        return None
    return lo, hi, ("range" if day2 else "day")


def _part_mon(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    month = _month_of(m, "mon")
    y = _year_or_yy(m, month, anchor)
    part = _PART_WORDS[m.group("p").lower()]
    return (*part_span(y, month, part), "part_of_month")


def _mon_end(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    month = _month_of(m, "mon")
    y = _year_or_yy(m, month, anchor)
    return (*part_span(y, month, "late"), "part_of_month")


def _part_part_mon(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    month = _month_of(m, "mon")
    y = _year_or_yy(m, month, anchor)
    lo = part_span(y, month, _PART_WORDS[m.group("p1").lower()])[0]
    hi = part_span(y, month, _PART_WORDS[m.group("p2").lower()])[1]
    return lo, hi, "part_of_month"


def _year_or_yy(m: re.Match[str], month: int, anchor: date) -> int:
    groups = m.groupdict()
    if groups.get("y"):
        return int(groups["y"])
    if groups.get("yy") and two_digit_year(int(groups["yy"]), anchor):
        return 2000 + int(groups["yy"])
    return infer_year(month, anchor)


def _mon_range(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    m1, m2 = _month_of(m, "mon1"), _month_of(m, "mon2")
    y1raw, y2raw = m.group("y1"), m.group("y2")
    if y2raw:
        y2 = int(y2raw)
        y1 = int(y1raw) if y1raw else (y2 if m1 <= m2 else y2 - 1)
    elif y1raw:
        y1 = int(y1raw)
        y2 = y1 if m2 >= m1 else y1 + 1
    else:
        y1 = infer_year(m1, anchor)
        y2 = y1 if m2 >= m1 else y1 + 1
    p1, p2 = m.group("p1"), m.group("p2")
    lo = part_span(y1, m1, _PART_WORDS[p1.lower()])[0] if p1 else date(y1, m1, 1)
    hi = part_span(y2, m2, _PART_WORDS[p2.lower()])[1] if p2 else month_end(y2, m2)
    if hi < lo:
        return None
    return lo, hi, "range"


def _mon_year(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    month = _month_of(m, "mon")
    return (*month_span(_year_or_yy(m, month, anchor), month), "month")


def _mon_only(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    month = _month_of(m, "mon")
    return (*month_span(infer_year(month, anchor), month), "month")


def _quarter_range(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    q1, q2 = int(m.group("q1") or m.group("q1b")), int(m.group("q2") or m.group("q2b"))
    y2 = int(m.group("y2")) if m.group("y2") else None
    y1 = int(m.group("y1")) if m.group("y1") else None
    if y2 is None and y1 is None:
        y1 = anchor.year if q1 >= (anchor.month - 1) // 3 + 1 else anchor.year + 1
    if y1 is None:
        y1 = y2 if q1 <= q2 else y2 - 1
    if y2 is None:
        y2 = y1 if q2 >= q1 else y1 + 1
    lo, hi = quarter_span(y1, q1)[0], quarter_span(y2, q2)[1]
    return (lo, hi, "range") if lo <= hi else None


def _quarter(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    groups = m.groupdict()
    q = int(groups["q"] or groups["qn"] or _QWORD.get((groups["qw"] or "").lower(), 0))
    if not q:
        return None
    yy = groups.get("yy")
    if groups.get("y"):
        y = int(groups["y"])
    elif yy and (groups["q"] or groups["qn"]) and two_digit_year(int(yy), anchor):
        y = 2000 + int(yy)
    elif yy:
        return None  # "2Q 15 mg" and the like
    else:
        y = anchor.year if q >= (anchor.month - 1) // 3 + 1 else anchor.year + 1
    p = groups.get("p")
    part = _PART_WORDS[re.sub(r"\s+", " ", p.lower())] if p else None
    return (*quarter_span(y, q, part), "quarter")


def _half(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    h = m.group("h") or m.group("h2")
    if not h:
        h = "1" if m.group("hw").lower() in ("first", "1st") else "2"
    return (*year_part_span(int(m.group("y")), f"h{h}"), "quarter")


def _year_only(m: re.Match[str], anchor: date) -> tuple[date, date, str]:
    p = re.sub(r"\s+", " ", (m.group("p") or "").lower())
    part = _PART_WORDS.get(p) if p and p != "sometime in" else None
    return (*year_part_span(int(m.group("y")), part), "year")


def _relative(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    def count(raw: str | None) -> int | None:
        if raw is None:
            return None
        return int(raw) if raw.isdigit() else _NUMWORD.get(raw.lower())

    n, n2 = count(m.group("n")), count(m.group("n2"))
    if n is None:
        return None
    unit = m.group("u").lower()

    def shift(k: int) -> date:
        return anchor + timedelta(days=k * {"d": 1, "w": 7, "m": 30}[unit[0]])

    lo = shift(n)
    hi = shift(n2) if n2 is not None else lo
    if hi < lo:
        return None
    groups = m.groupdict()
    pre = re.sub(r"\s+", " ", (groups.get("pre") or "").lower())
    if pre in ("within", "up to") or (groups.get("next") or "").lower().startswith("the next"):
        return anchor, hi, "range"  # "within 2 weeks", "up to 3 months", "over the next 8 months"
    return lo, hi, ("range" if n2 is not None else "day")


def _calendar_relative(m: re.Match[str], anchor: date) -> tuple[date, date, str] | None:
    which, unit = m.group("which").lower(), m.group("unit").lower()
    late = bool(m.group("late"))
    if which == "the" and not late:
        return None  # "the week of ..." is handled by the week patterns
    step = 0 if which in ("this", "the", "remainder of the") else 1
    if unit == "week":
        monday = anchor - timedelta(days=anchor.weekday()) + timedelta(days=7 * step)
        return monday, monday + timedelta(days=6), "part_of_month"
    if unit == "month":
        first = add_months(anchor.replace(day=1), step)
        if late:
            return (*part_span(first.year, first.month, "late"), "part_of_month")
        return (*month_span(first.year, first.month), "month")
    if unit == "quarter":
        q = (anchor.month - 1) // 3 + step
        y, q = anchor.year + q // 4, q % 4 + 1
        return (*quarter_span(y, q, "late" if late else None), "quarter")
    y = anchor.year + step
    return (*year_part_span(y, "late" if late else None), "year")


_YR_OR_YY = rf"(?:(?:\s+of\s+|[\s,'-]*|/)(?P<y>{_Y4})(?!\d)|\s*[-']\s*(?P<yy>\d\d)(?![\d/]))"
_YR_OR_BARE_YY = rf"(?:(?:[\s,'-]+|/)(?P<y>{_Y4})(?!\d)|\s*[-' ]\s*(?P<yy>\d\d)(?![\d/,:]))"
_BOUND = (
    r"(?P<bound>\bby|\bbefore|no\s+later\s+than|\buntil|\btill|\bthru|\bthrough"
    r"|not\s+sooner\s+than|no\s+earlier\s+than|\bafter)"
)
_BOUND_WORDS = {
    "by": "by",
    "before": "by",
    "no later than": "by",
    "until": "until",
    "till": "until",
    "thru": "until",
    "through": "until",
    "not sooner than": "not_before",
    "no earlier than": "not_before",
    "after": "not_before",
}
_SEP = r"\s*(?:-|/|to|through|thru|or)\s*"


def _pattern(regex: str) -> re.Pattern[str]:
    return re.compile(regex, re.IGNORECASE)


PATTERNS: list[tuple[str, re.Pattern[str], Handler]] = [
    (
        "week_of_numeric",
        _pattern(
            rf"week\s+of\s+(?P<m>1[0-2]|0?[1-9])/(?P<d>{_DAY})(?:/(?P<y>{_Y4}|\d\d))?(?![\d/])"
        ),
        _week_of,
    ),
    (
        "week_of_named",
        _pattern(rf"week\s+of\s+{_mon('mn')}\s+(?P<d>{_DAY}){_ORD}(?:,?\s*(?P<y>{_Y4}))?(?!\d)"),
        _week_of,
    ),
    (
        "week_n_of",
        _pattern(rf"week\s+(?P<n>[1-5])\s+of\s+{_mon('mon')}(?:,?\s+(?P<y>{_Y4}))?"),
        _week_n,
    ),
    (
        "numeric_date",
        _pattern(
            rf"(?<![\d/.-])(?P<m>1[0-2]|0?[1-9])(?P<s>[/-])(?P<d>{_DAY})(?P=s)"
            rf"(?P<y>{_Y4}|\d\d)(?![\d/-])"
        ),
        _numeric_date,
    ),
    (
        "numeric_md",
        _pattern(
            rf"\b(?:on|by|of|until|before|after|around|eta)\s+"
            rf"(?P<core>(?P<m>1[0-2]|0?[1-9])/(?P<d>{_DAY}))(?![\d/%])"
        ),
        _numeric_md,
    ),
    (
        "numeric_month_year",
        _pattern(rf"(?<![\d/.-])(?P<m>1[0-2]|0?[1-9])/(?P<y>{_Y4})(?![\d/])"),
        _numeric_my,
    ),
    (
        "day_first",
        _pattern(
            rf"(?<![\d/.-])(?P<d>{_DAY}){_ORD}(?:\s*-\s*|\s+|)(?:of\s+)?{_mon('mon')}"
            rf"(?:,?\s*-?\s*)(?P<y>{_Y4}|\d\d)(?!\d)"
        ),
        _day_first,
    ),
    (
        "part_part_month",
        _pattern(
            rf"(?P<p1>{_PART_ALT})(?![a-z])[\s-]*(?:to|or|/|-)\s*(?P<p2>{_PART_ALT})(?![a-z])"
            rf"[\s-]*(?:of\s+)?{_mon('mon')}(?:{_YR_OR_YY})?"
        ),
        _part_part_mon,
    ),
    (
        "month_range",
        _pattern(
            rf"(?:{_part('p1')})?{_mon('mon1')}(?:[\s,'-]+(?P<y1>{_Y4})(?!\d))?{_SEP}"
            rf"(?:{_part('p2')})?{_mon('mon2')}(?:[\s,'-]+(?P<y2>{_Y4})(?!\d))?"
        ),
        _mon_range,
    ),
    (
        "month_day",
        _pattern(
            rf"{_mon('mon')}\s*(?P<d>{_DAY})(?P<ord>st|nd|rd|th)?(?!\d)"
            rf"(?:\s*-\s*(?P<d2>{_DAY}){_ORD}(?!\d))?(?:,?\s*(?P<y>{_Y4})(?!\d))?"
            rf"(?!\s*(?:mg|mcg|ml|g|%|count|ct|units?|vials?)\b)"
        ),
        _mon_day,
    ),
    (
        "part_month",
        _pattern(rf"{_part('p')}{_mon('mon')}(?:{_YR_OR_BARE_YY})?"),
        _part_mon,
    ),
    (
        "month_end",
        _pattern(rf"{_mon('mon')}(?:{_YR_OR_YY})?\s+end\b"),
        _mon_end,
    ),
    (
        "quarter_range",
        _pattern(
            rf"(?<![A-Za-z0-9])(?:Q(?P<q1>[1-4])|(?P<q1b>[1-4])Q)(?:[\s,'-]*(?P<y1>{_Y4}))?{_SEP}"
            rf"(?:Q(?P<q2>[1-4])|(?P<q2b>[1-4])Q)(?:[\s,'/-]*(?P<y2>{_Y4}))?(?!\d)"
        ),
        _quarter_range,
    ),
    (
        "quarter",
        _pattern(
            rf"(?:(?P<p>early|mid|late|end\s+of|the\s+end\s+of|end|beginning\s+of)[\s-]*)?"
            rf"(?:(?<![A-Za-z0-9])Q(?P<q>[1-4])|(?<![A-Za-z0-9])(?P<qn>[1-4])Q"
            rf"|(?:the\s+)?(?P<qw>first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter)"
            rf"(?:\s*(?:of\s+)?(?:the\s+year\s+)?(?:[\s,'/-]*)(?:(?P<y>{_Y4})|(?P<yy>\d\d))"
            rf"(?![\d%]))?(?![A-Za-z])"
        ),
        _quarter,
    ),
    (
        "half",
        _pattern(
            rf"(?:(?<![A-Za-z0-9])(?P<h>[12])H|(?<![A-Za-z0-9])H(?P<h2>[12])"
            rf"|(?:the\s+)?(?P<hw>first|second|1st|2nd)\s+half\s+(?:of\s+)?(?:the\s+year\s+)?)"
            rf"[\s,'-]*(?P<y>{_Y4})(?!\d)"
        ),
        _half,
    ),
    (
        "month_year",
        _pattern(rf"{_mon('mon')}{_YR_OR_YY}"),
        _mon_year,
    ),
    (
        "year",
        _pattern(
            rf"(?:(?P<p>early|mid|middle\s+of|the\s+middle\s+of|late|end\s+of|the\s+end\s+of|end"
            rf"|beginning\s+of|the\s+beginning\s+of|start\s+of|sometime\s+in)[\s-]+)?"
            rf"(?<![\d/.,-])(?P<y>{_Y4})(?![\d/-]|\s*(?:mg|mcg|ml|units?)\b)"
        ),
        _year_only,
    ),
    (
        "relative",
        _pattern(
            r"(?:(?P<pre>\bin|\bwithin|\bup\s+to|\bnext|\banother|\bapprox(?:imately|\.)?"
            r"|\babout|\baround|\bof|\bfor|\bover|\bduring|\bduration|\bshortage)\s*:?|:)\s*"
            r"(?P<next>the\s+next\s+|a\s+)?"
            r"(?P<core>(?P<n>\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|twelve)"
            r"(?:\s*(?:-|to)\s*(?P<n2>\d{1,3}|two|three|four|five|six|eight|ten|twelve))?"
            r"\s*(?:business\s+|calendar\s+)?(?P<u>days?|weeks?|months?))\b"
            r"(?!\s*(?:of\s+)?(?:dating|expiry|shelf|supply|stock|inventory|backorder))"
        ),
        _relative,
    ),
    (
        "relative_supply",
        _pattern(
            r"(?P<core>(?P<n>\d{1,3}|one|two|three|four|six|twelve)"
            r"(?:\s*(?:-|to)\s*(?P<n2>\d{1,3}|two|three|four|six|twelve))?"
            r"\s*(?P<u>weeks?|months?))\s+of\s+(?:inventory|supply|stock)\b"
        ),
        _relative,
    ),
    (
        "calendar_relative",
        _pattern(
            r"(?P<late>(?:the\s+)?end\s+of\s+|later\s+|late\s+)?"
            r"(?P<which>next|this|the|remainder\s+of\s+the)\s+(?P<unit>week|month|quarter|year)\b"
        ),
        _calendar_relative,
    ),
    (
        "month_only",
        _pattern(rf"(?<![A-Za-z]){_mon('mon')}"),
        _mon_only,
    ),
]


_BOUND_BEFORE = re.compile(rf"{_BOUND}\s*(?:the\s+)?(?:end\s+of\s+)?$", re.IGNORECASE)


def find_timexes(text: str, anchor: date) -> list[Timex]:
    """All non-overlapping temporal expressions, longest match first."""
    cands: list[tuple[int, int, int, Timex]] = []
    for rank, (_, pattern, handler) in enumerate(PATTERNS):
        for m in pattern.finditer(text):
            if m.end() == m.start():
                continue
            if _modal_may(m):
                continue
            got = handler(m, anchor)
            if got is None:
                continue
            lo, hi, gran = got
            s, e = m.span("core") if "core" in pattern.groupindex else m.span()
            while e > s and text[e - 1] in " ,-'/":
                e -= 1
            cands.append((s, e, rank, Timex(s, e, text[s:e], lo, hi, gran)))
    cands.sort(key=lambda c: (-(c[1] - c[0]), c[2], c[0]))
    taken: list[Timex] = []
    for s, e, _, tx in cands:
        if all(e <= t.start or s >= t.end for t in taken):
            taken.append(tx)
    taken.sort(key=lambda t: t.start)
    return [_with_bound(text, t, anchor) for t in _borrow_years(text, taken)]


def _modal_may(m: re.Match[str]) -> bool:
    """Lower-case 'may' is the modal verb, not the month."""
    names = ("mon", "mon1", "mon2", "mn")
    return any(g in m.re.groupindex and m.group(g) == "may" for g in names)


def _with_bound(text: str, t: Timex, anchor: date) -> Timex:
    """Record a bound word; "by X" / "before X" / "X at the latest" read as anchor to end of X."""
    b = _BOUND_BEFORE.search(text[max(0, t.start - 30) : t.start])
    bound = _BOUND_WORDS[re.sub(r"\s+", " ", b.group("bound").lower())] if b else None
    if re.match(r"\s*,?\s*at\s+the\s+latest", text[t.end :], re.IGNORECASE):
        bound = "by"
    if bound is None:
        return t
    lo = anchor if bound == "by" and anchor <= t.hi else t.lo
    return Timex(t.start, t.end, t.text, lo, t.hi, t.granularity, bound)


def _borrow_years(text: str, timexes: list[Timex]) -> list[Timex]:
    """'Month and Month YYYY': a yearless month joined by and/&/, borrows the next year."""
    out = list(timexes)
    for i in range(len(out) - 1, 0, -1):
        left, right = out[i - 1], out[i]
        joiner = text[left.end : right.start]
        if not re.fullmatch(r"\s*(?:,\s*)?(?:and|&|,)\s*", joiner, re.IGNORECASE):
            continue
        if left.granularity != "month" or re.search(r"\d", left.text):
            continue
        y = right.lo.year if left.lo.month <= right.lo.month else right.lo.year - 1
        lo, hi = month_span(y, left.lo.month)
        out[i - 1] = Timex(left.start, left.end, left.text, lo, hi, left.granularity, left.bound)
    return out


# --------------------------------------------------------------------------------------------
# Abstention and vagueness markers
# --------------------------------------------------------------------------------------------

ABSTAIN = re.compile(
    r"\bTBD\b|\bTBA\b|\bT\.B\.D\b|\bto\s+be\s+(?:determined|announced|confirmed)\b|\bundetermined\b"
    r"|\b(?:date|dates|release|delivery|shipment|eta|estimate|timeline|timeframe|recovery"
    r"|resupply|re-supply|avail\w*|duration)\s+(?:is\s+|are\s+)?(?:currently\s+)?"
    r"(?:not\s+(?:yet\s+)?(?:available|known|determined|confirmed)|unavailable|unknown)\b"
    r"|\bno\s+(?:\w+\s+){0,2}(?:date|eta|estimate|timeline|timeframe)s?\b"
    r"|\b(?:unable|not\s+able)\s+to\s+(?:provide|estimate|determine|give|predict|project)"
    r"|\b(?:cannot|can\s*not)\s+(?:provide|estimate|determine|give|predict)"
    r"|(?<!reason\s)(?<!reason:\s)\bunknown\b",
    re.IGNORECASE,
)
VAGUE = re.compile(
    r"\b(?:a\s+)?(?:few|several|couple\s+of|coming|next\s+few)\s+(?:days|weeks|months)"
    r"|\bextended\s+period|\bforeseeable\s+future|\bnear\s+future|\bshortly\b|\bsoon\b"
    r"|\blong[\s-]term\b|\bweeks/months\b",
    re.IGNORECASE,
)
AS_RELEASED = re.compile(
    r"as\s+(?:it\s+is|they\s+are)\s+released|as\s+the\s+product\s+becomes\s+available"
    r"|additional\s+(?:lots|production|units)\s+(?:are|is|will\s+be)\s+(?:scheduled|underway"
    r"|manufactured)",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------------------------
# Role cues
# --------------------------------------------------------------------------------------------

# Until-phrases take the head nearest to "until": the gap of a shortage-until cue may not cross
# an availability word ("limited short-dated stock available until X" is availability until
# X), and the gap of an availability-until cue may not cross a shortage word ("available,
# however limited supply until X" is a shortage lasting until X).
_UNTIL = (
    r"(?:(?!\bavail\w*|\bin\s+stock)[^.;:]){0,60}?\b(?:until|till|through|thru|into)\b"
    r"(?:\s+(?:the\s+)?end\s+of)?"
)
_SHORTAGE_WORD = (
    r"\b(?:limited|backorder\w*|back[\s-]order\w*|allocat\w*|shortage\w*|out\s+of\s+stock"
    r"|unavail\w*|impacted|disrupt\w*|interrupt\w*|constrain\w*|delay\w*|intermittent)"
)
_AVAIL_UNTIL = (
    rf"(?:(?!{_SHORTAGE_WORD})[^.;:]){{0,60}}?\b(?:until|till|through|thru|into)\b"
    r"(?:\s+(?:the\s+)?end\s+of)?"
)


@dataclass(frozen=True, slots=True)
class Cue:
    """A role cue. Specific cues (strength 2-3) beat generic ones (1); then the nearest wins."""

    role: str
    pattern: re.Pattern[str]
    strength: int
    adjacent: bool = False  # an until-phrase counts only right before the date (<= 16 chars)


def _cue(role: str, strength: int, regex: str) -> Cue:
    adjacent = regex.endswith((_UNTIL, _AVAIL_UNTIL))
    return Cue(role, re.compile(regex, re.IGNORECASE), strength, adjacent)


CUES: tuple[Cue, ...] = (
    _cue(
        "next_delivery+recovery",
        3,
        r"next\s+deliver\w*\s*(?:and|&|/)\s*(?:estimated\s+)?recover\w*",
    ),
    _cue(
        "availability_until",
        3,
        rf"\b(?:avail\w*|supply\s+duration|distribut\w*\s+will\s+continue|continu\w*\s+to\s+"
        rf"(?:be\s+)?(?:avail\w*|distribut\w*|sell\w*|sold|market\w*|ship\w*)|selling|stock)"
        rf"{_AVAIL_UNTIL}",
    ),
    _cue(
        "depletion",
        3,
        r"\b(?:deplet\w*|exhaust\w*|run[\s-]?out|(?:to|will|should|expected\s+to)\s+last"
        r"(?:\s+(?:until|through|thru|into))?|unavailability)\b",
    ),
    _cue(
        "recovery",
        3,
        rf"\b(?:limited\s+avail\w*|not\s+(?:be\s+|currently\s+)?avail\w*|backorder\w*"
        rf"|back[\s-]order\w*|BO|out\s+of\s+stock|stock\s*out|unavail\w*|impacted|disrupt\w*"
        rf"|interrupt\w*|allocat\w*|shortage\w*|constrain\w*|delay\w*|intermittent|limited)"
        rf"{_UNTIL}",
    ),
    _cue(
        "discontinuation",
        3,
        r"\bdiscontinu\w*(?:\s+(?:as\s+of|effective|on|by|in|after)\b)?|\bdiscontinnuation"
        r"|\bcease\w*|\bceasing|\bstop[\s-]+(?:sale|sell\w*|ship\w*|distribut\w*)"
        r"|\bfinal\s+(?:date|order|shipment|availability|lot|batch)\w*"
        r"|\blast\s+(?:order|shipment|batch\w*|lot)\b(?!\s+(?:produced\s+)?expir)"
        r"|\bno\s+longer\s+(?:be\s+)?(?:availab|manufactur|market|distribut|suppl)\w*"
        r"|\bphas\w+\s+out|\bwithdraw\w*|\bmarket\s+exit|\bdelist\w*|\blast\s+distribution"
        r"|\bdistribution\s+(?:to\s+end|will\s+(?:end|cease)|ends?)",
    ),
    _cue("expiry", 3, r"\bexpir\w*|\bexp\b\.?|\bdating\b|\bshelf[\s-]life|\bshort[\s-]dat\w*"),
    _cue(
        "onset",
        3,
        r"\b(?:go|going|will\s+be|be)\s+(?:on\s+)?(?:out\s+of\s+stock|backorder\w*|back[\s-]order"
        r"\w*)(?:\s+by)?|\bshortage\s+(?:is\s+)?(?:anticipated|expected)\s+(?:from|to\s+begin"
        r"|starting)|\bbackorder\w*\s+(?:is\s+)?(?:expected|anticipated|projected)"
        r"|\bprojecting\s+backorder|\b(?:shortage|backorder)\w*\s+starting",
    ),
    _cue(
        "past",
        2,
        r"(?<!be\s)\b(?:arrived|shipped|resolved|launched|posted|updated|received)\s+(?:in|on)\b"
        r"|\bhas\s+been\s+\w+\s+since|\bas\s+of|\beffective|\bsince|\binitiated|\bannounced",
    ),
    _cue(
        "other",
        3,
        r"\b(?:provide|give|issue|next)\s+(?:an\s+)?update\w*|\bre-?evaluat\w*|\breassess\w*",
    ),
    _cue(
        "recovery",
        3,
        r"\brecover\w*|\bre-?suppl\w*|\bre-?stock\w*|\bback\s+in\s+stock|\brelaunch\w*"
        r"|\boff\s+(?:back[\s-]?order|allocation)\w*",
    ),
    _cue(
        "recovery",
        2,
        r"\bresum\w*|\breturn\w*|\blaunch\w*|\b(?:estimated|expected|anticipated|est\.?|target"
        r"|targeted|initial|product|fully|(?<!final\s)date\s+of)\s+"
        r"(?:date\s+of\s+|supply\s+)?avail\w*"
        r"|\bavail\w*\s+(?:is\s+)?(?:anticipated|expected|estimated|planned|targeted)"
        r"|(?<!longer\s)\bavailable\s+(?:for\s+order|to\s+order)|\bshortage\s+duration|\bduration"
        r"|\b(?:meet|support|fulfil\w*)\s+(?:the\s+)?(?:current\s+|full\s+|customer\s+)?demand"
        r"|\bdemand\s+can\s+be\s+fulfil\w*|\bbetter\s+stock|\bnormal\s+(?:supply|inventory)"
        r"|\bfull\s+supply|\bcapacity\s+increase|\bincreased?\s+supply"
        r"|\bdistribut\w*\s+(?:is\s+)?(?:anticipated|expected|planned|will\s+resume)"
        r"|\bproduct\s+(?:is\s+)?(?:expected|anticipated)",
    ),
    _cue(
        "next_delivery",
        3,
        r"\bnext\s+(?:deliver\w*|releas\w*|shipment\w*|ship\w*|batch\w*|lots?|supply|replenish"
        r"\w*|units?|expected|avail\w*)|\breleas\w*|(?<!stop-)(?<!stop\s)\bship(?:ment|ments"
        r"|ping|s)?\b|\bdeliver\w*|\badditional\s+(?:lots?|units?|quantit\w*|stocks?|material"
        r"|releases?|supply|product|replenish\w*|inventory)|\blots?\b|\bbatch\w*|\barriv\w*"
        r"|\breplenish\w*|\bscheduled\s+(?:for|to\s+be)\s+manufactur\w*|\bunits\s+expected"
        r"|\bmore\s+(?:batches|quantities|lots|units)|\bnew\s+(?:lots|batches|material)",
    ),
    _cue(
        "recovery",
        1,
        r"\bavail\w*|\bin\s+stock|\bsupply\b|\bproduct\s+anticipated|\bexpected\s+in",
    ),
)
RIGHT_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("depletion", re.compile(r"^\s*of\s+(?:inventory|supply|stock)\b", re.IGNORECASE)),
    ("expiry", re.compile(r"^[\s)(,]{0,3}(?:expir\w*|exp\b|dating)", re.IGNORECASE)),
    ("recovery", re.compile(r"^[\s,]{0,3}(?:recovery|supply|resupply)\b", re.IGNORECASE)),
    ("next_delivery", re.compile(r"^[\s,]{0,3}(?:release|delivery|shipment)\b", re.IGNORECASE)),
)
HEDGES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "estimated",
        re.compile(
            r"\best[ai]m\w*|\besim\w*|\best\b\.?|\bETA\b|\bapprox\w*|\bproject\w*|\bpredict\w*"
            r"|\btarget\w*|\btentativ\w*|\bon\s+or\s+near\b|\baround\b|\babout\b",
            re.IGNORECASE,
        ),
    ),
    ("expected", re.compile(r"\bexpect\w*|\blikely\b|\bshould\b", re.IGNORECASE)),
    ("anticipated", re.compile(r"\banticipat\w*", re.IGNORECASE)),
)
_CLAUSE = re.compile(r"\.(?=\s+[A-Z(|]|\s*$)|;|\|+")
_ABBREVIATION = re.compile(
    r"\b(?:jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec|exp|est|approx|inc|no)$", re.IGNORECASE
)


def clauses(text: str) -> list[tuple[int, int]]:
    """Clause spans: split at full stops and semicolons, not at decimals or 'Sept.'."""
    out, start = [], 0
    for m in _CLAUSE.finditer(text):
        if m.group() == "." and _ABBREVIATION.search(text[max(0, m.start() - 6) : m.start()]):
            continue
        out.append((start, m.start()))
        start = m.end()
    out.append((start, len(text)))
    return [(s, e) for s, e in out if text[s:e].strip()]


@dataclass(frozen=True, slots=True)
class _CueHit:
    role: str
    strength: int
    start: int
    end: int


def _nearest_cue(segment: str) -> _CueHit | None:
    """The deciding cue: the nearest specific one, else the nearest generic one.

    Nearest means the latest end; ties go to the stronger and then to the longer match.
    """
    best: dict[bool, _CueHit] = {}
    for cue in CUES:
        for m in cue.pattern.finditer(segment):
            if cue.adjacent and len(segment) - m.end() > 16:
                continue
            hit = _CueHit(cue.role, cue.strength, m.start(), m.end())
            tier = cue.strength >= 2
            old = best.get(tier)
            if old is None or (hit.end, hit.strength, -hit.start) > (
                old.end,
                old.strength,
                -old.start,
            ):
                best[tier] = hit
    return best.get(True) or best.get(False)


def _right_cue(text: str, end: int, clause_end: int) -> str | None:
    tail = text[end:clause_end]
    for role, pattern in RIGHT_CUES:
        if pattern.search(tail):
            return role
    return None


def _certainty(segment: str, tail: str) -> str:
    best: tuple[int, str] | None = None
    for label, pattern in HEDGES:
        for m in pattern.finditer(segment):
            if best is None or m.end() > best[0]:
                best = (m.end(), label)
    if best is not None:
        return best[1]
    for label, pattern in HEDGES:
        if pattern.search(tail[:25]):
            return label
    return "firm"


# --------------------------------------------------------------------------------------------
# Statements and the reading
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class Statement:
    """One typed forward-looking statement (or distractor mention) found in the text."""

    statement_type: str
    start: int
    end: int
    text: str
    timex: Timex | None
    abstain_reason: str | None
    certainty: str
    strength: int
    cue: str | None = None

    def as_dict(self) -> dict:
        return {
            "statement_type": self.statement_type,
            "interval": self.timex.interval if self.timex else None,
            "granularity": self.timex.granularity if self.timex else None,
            "bound": self.timex.bound if self.timex else None,
            "abstain_reason": self.abstain_reason,
            "certainty": self.certainty,
            "cue": self.cue,
            "span": [self.start, self.end],
            "text": self.text,
        }


@dataclass(slots=True)
class Reading:
    """The literal reading of one notice text (see the module docstring for each field)."""

    statement_type: str
    interval: list[str] | None
    abstain: bool
    certainty: str
    granularity: str | None
    distractor_dates: list[dict]
    abstain_reason: str | None = None
    stale: bool = False
    bound: str | None = None
    cue: str | None = None
    span: list[int] | None = None
    statements: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "statement_type": self.statement_type,
            "interval": self.interval,
            "abstain": self.abstain,
            "certainty": self.certainty,
            "granularity": self.granularity,
            "distractor_dates": self.distractor_dates,
            "abstain_reason": self.abstain_reason,
            "stale": self.stale,
            "bound": self.bound,
            "cue": self.cue,
            "span": self.span,
            "statements": self.statements,
        }


@dataclass(frozen=True, slots=True)
class _Anchor:
    start: int
    end: int
    timex: Timex | None  # None for an abstention marker


def _anchors(text: str, s: int, e: int, timexes: list[Timex]) -> list[_Anchor]:
    out = [_Anchor(t.start, t.end, t) for t in timexes if s <= t.start < e]
    for m in ABSTAIN.finditer(text, s, e):
        if not any(a.start <= m.start() < a.end for a in out):
            out.append(_Anchor(m.start(), m.end(), None))
    return sorted(out, key=lambda a: a.start)


def _role_for(
    text: str,
    a: _Anchor,
    seg_start: int,
    clause: tuple[int, int],
    inherited: str | None,
    before: int,
    followed: bool,
) -> tuple[str, int, str | None]:
    """(role, strength, cue text) for a date or marker, by the documented precedence.

    ``before`` is the start of the previous clause: a short clause (at most three words besides
    the date) with no cue takes the nearest specific cue of the clause before it ("Estimated
    Recovery; November 2021").
    ``followed`` says another date or marker follows in the clause; a cue after the date then
    belongs to that one ("end of April, recovery in May"), except an expiry cue.
    """
    seg_end = a.start if a.timex else a.end
    hit = _nearest_cue(text[seg_start:seg_end])
    if hit is None and inherited is not None:
        return inherited, 0, None
    right = _right_cue(text, a.end, clause[1]) if a.timex else None
    if right is not None and followed and right != "expiry":
        right = None
    if right is not None and (hit is None or (right == "expiry" and hit.strength < 3)):
        return right, 3, text[a.end : clause[1]].strip()[:20]
    if hit is None:
        seg_start = clause[0]
        hit = _nearest_cue(text[seg_start:seg_end])
    rest = text[clause[0] : a.start] + " " + text[a.end : clause[1]]
    if hit is None and before < clause[0] and len(re.findall(r"[A-Za-z]+", rest)) <= 3:
        seg_start = before
        hit = _nearest_cue(text[before : clause[0]])
        hit = hit if hit is not None and hit.strength >= 2 else None
    if hit is None:
        return ("other" if a.timex else "recovery"), 0, None
    return hit.role, hit.strength, text[seg_start + hit.start : seg_start + hit.end]


def _statements_in_clause(
    text: str, clause: tuple[int, int], timexes: list[Timex], before: int
) -> list[Statement]:
    s, e = clause
    anchors = _anchors(text, s, e, timexes)
    if not anchors:
        return _undated_statements(text, clause)
    out: list[Statement] = []
    prev_end, prev_role = s, None
    for i, a in enumerate(anchors):
        joined = prev_role is not None and re.fullmatch(
            r"[\s,]*(?:and|&|or)?[\s,]*", text[prev_end : a.start], re.IGNORECASE
        )
        inherited = prev_role if joined and prev_role != "other" else None
        followed = i + 1 < len(anchors)
        role, strength, cue = _role_for(text, a, prev_end, clause, inherited, before, followed)
        segment = text[prev_end : a.start if a.timex else a.end]
        certainty = _certainty(segment, text[a.end : e]) if a.timex else "unknown"
        for r in ("next_delivery", "recovery") if role == "next_delivery+recovery" else (role,):
            out.append(
                Statement(
                    statement_type=r,
                    start=a.start,
                    end=a.end,
                    text=text[a.start : a.end],
                    timex=a.timex,
                    abstain_reason=None if a.timex else "tbd",
                    certainty=certainty,
                    strength=strength,
                    cue=cue,
                )
            )
        prev_end, prev_role = a.end, role
    return out


def _undated_statements(text: str, clause: tuple[int, int]) -> list[Statement]:
    """Vague estimates, undated discontinuations and 'as it is released' clauses."""
    s, e = clause
    body = text[s:e]

    def one(kind: str, m: re.Match[str], reason: str, strength: int) -> list[Statement]:
        a, b = s + m.start(), s + m.end()
        cue = text[a:b]
        return [Statement(kind, a, b, cue, None, reason, "unknown", strength, cue)]

    vague = VAGUE.search(body)
    if vague:
        hit = _nearest_cue(body)
        role = hit.role if hit else "recovery"
        if role not in STATEMENT_TYPES:
            role = "recovery"
        return one(role, vague, "vague", hit.strength if hit else 0)
    disc = next(c for c in CUES if c.role == "discontinuation")
    m = disc.pattern.search(body)
    if m:
        return one("discontinuation", m, "no_date", 3)
    m = AS_RELEASED.search(body)
    if m:
        return one("next_delivery", m, "no_date", 1)
    return []


def _score(st: Statement) -> int:
    """Primary-statement precedence (higher wins); see the module docstring."""
    dated, tbd = st.timex is not None, st.abstain_reason == "tbd"
    cue = st.cue or ""
    if st.statement_type == "recovery":
        if not (dated or tbd):
            return 80
        if re.search(r"recover", cue, re.IGNORECASE):
            base = 100
        elif re.search(r"\b(?:until|till|through|thru|into)\b", cue, re.IGNORECASE):
            base = 86
        else:
            base = {3: 94, 2: 90}.get(st.strength, 83)
        return base - (0 if dated else 3)
    if st.statement_type == "next_delivery":
        if dated:
            return 79 if re.match(r"next\b", cue, re.IGNORECASE) else 78
        return 75 if tbd else 73
    if st.statement_type in END_OF_SUPPLY:
        base = 70 if st.statement_type == "discontinuation" else 60
        sub = 5 if dated else 3 if tbd else 0
        return base + sub + (1 if st.statement_type == "depletion" else 0)
    return 0


def _primary(statements: list[Statement]) -> Statement | None:
    typed = [st for st in statements if _score(st) > 0]
    return max(typed, key=lambda st: (_score(st), -st.start)) if typed else None


def _bare_date(text: str, statements: list[Statement]) -> Statement | None:
    """Read a text that is only a date plus at most four words as a recovery date.

    ("Stocked Out, December 2021", "Q1 2023": the field states the product's availability.)
    """
    dated = [st for st in statements if st.timex is not None]
    if len(dated) != 1 or dated[0].statement_type != "other":
        return None
    st = dated[0]
    rest = text[: st.start] + " " + text[st.end :]
    if len(re.findall(r"[A-Za-z]+", rest)) > 4 or _nearest_cue(rest) is not None:
        return None
    st.statement_type, st.strength = "recovery", 1
    return st


def read(text: str, anchor: date | str) -> Reading:
    """Literal reading of one notice text anchored to its Date of Update."""
    if isinstance(anchor, str):
        anchor = parse_anchor(anchor)
    t = normalise(text or "")
    timexes = find_timexes(t, anchor)
    statements: list[Statement] = []
    before = 0
    for clause in clauses(t):
        statements.extend(_statements_in_clause(t, clause, timexes, before))
        before = clause[0]
    primary = _primary(statements) or _bare_date(t, statements)
    distractors = [
        {"text": st.text, "role": st.statement_type, "interval": st.timex.interval}
        for st in statements
        if st.timex is not None
        and st.statement_type in DISTRACTOR_ROLES
        and (primary is None or (st is not primary and st.statement_type != primary.statement_type))
    ]
    listed = [st.as_dict() for st in statements]
    if primary is None:
        return Reading(
            "none", None, True, "unknown", None, distractors, "no_statement", statements=listed
        )
    tx = primary.timex
    return Reading(
        statement_type=primary.statement_type,
        interval=tx.interval if tx else None,
        abstain=tx is None,
        certainty=primary.certainty if tx else "unknown",
        granularity=tx.granularity if tx else None,
        distractor_dates=distractors,
        abstain_reason=None if tx else primary.abstain_reason,
        stale=bool(tx and tx.hi < anchor),
        bound=tx.bound if tx else None,
        cue=primary.cue,
        span=[primary.start, primary.end],
        statements=listed,
    )


LITERAL_V1_CERTAINTY = {
    "firm": "asserted",
    "estimated": "estimated",
    "expected": "estimated",
    "anticipated": "estimated",
}


def as_literal_v1(r: Reading) -> dict:
    """The reading in the answer schema of ``read.py``'s ``literal-v1`` prompt."""
    kind = "depletion" if r.statement_type == "availability_until" else r.statement_type
    if kind == "none":
        certainty = "no_statement"
    elif r.interval is None:
        certainty = "estimated" if r.abstain_reason == "vague" else "undetermined"
    else:
        certainty = LITERAL_V1_CERTAINTY[r.certainty]
    interval = {"start": r.interval[0], "end": r.interval[1]} if r.interval else "ABSTAIN"
    quote = next((st["text"] for st in r.statements if st["span"] == r.span), "")
    return {
        "statement_type": kind,
        "interval": interval,
        "certainty": certainty,
        "stale": r.stale,
        "quote": quote,
    }


def parse_anchor(raw: str) -> date:
    """Accept ISO (2021-03-05) or the CSV's MM/DD/YYYY."""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised anchor date: {raw!r}")


# --------------------------------------------------------------------------------------------
# Inventory of attested forms
# --------------------------------------------------------------------------------------------

_MASK_MON = re.compile(rf"\b(?:{_MON_ALT})\.?(?![a-z])", re.IGNORECASE)
TIMING_SCREEN = re.compile(
    rf"\b(?:{_MON_ALT})(?![a-z])|\b20\d\d\b|\bQ[1-4]\b|\b[1-4]Q|\bquarter\b|\b\d+\s*(?:days|weeks"
    rf"|months)\b|\bTBD\b|to be determined|\bunknown\b|no estimated|not available at this time",
    re.IGNORECASE,
)


def mask(text: str) -> str:
    """Template of a text: months, four-digit years and other numbers masked."""
    t = normalise(text)
    t = _MASK_MON.sub("<MON>", t)
    t = re.sub(r"\b(?:19|20)\d\d\b", "<YYYY>", t)
    return re.sub(r"\d+", "<N>", t)


def read_capture(path: Path) -> list[dict[str, str]]:
    """Rows of one capture: utf-8-sig with latin-1 fallback, blank lead lines, stripped headers."""
    raw = path.read_bytes()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("latin-1")
    rows = list(csv.reader(io.StringIO(txt.lstrip("\r\n \ufeff"))))
    if not rows:
        return []
    head = [c.strip() for c in rows[0]]
    return [dict(zip(head, r, strict=False)) for r in rows[1:] if r]


def iter_texts(captures: Path, split: str) -> Iterator[tuple[str, date]]:
    """Distinct (text, anchor) pairs from both text fields, restricted to a period split."""
    seen: set[tuple[str, date]] = set()
    for path in sorted(captures.glob("*.csv")):
        for row in read_capture(path):
            try:
                anchor = datetime.strptime(row.get("Date of Update", "").strip(), "%m/%d/%Y")
            except ValueError:
                continue
            anchor_d = anchor.date()
            if (split == "train") != (anchor_d < TEST_START):
                continue
            for name in TEXT_FIELDS:
                text = normalise(row.get(name) or "")
                if text and (text, anchor_d) not in seen:
                    seen.add((text, anchor_d))
                    yield text, anchor_d


def outcome_class(r: Reading) -> str:
    return "dated" if r.interval else f"abstain:{r.abstain_reason}"


def inventory(captures: Path, split: str, top: int) -> dict:
    """Template frequencies and the reader's result per template (train: listed; test: counts)."""
    by_text: dict[str, tuple[date, Reading]] = {}
    for text, anchor in iter_texts(captures, split):
        if TIMING_SCREEN.search(text) and text not in by_text:
            by_text[text] = (anchor, read(text, anchor))
    templates: dict[str, list[str]] = {}
    for text in by_text:
        templates.setdefault(mask(text), []).append(text)
    overall = Counter(outcome_class(r) for _, r in by_text.values())
    types = Counter(r.statement_type for _, r in by_text.values())
    report: dict = {
        "split": split,
        "distinct_timing_texts": len(by_text),
        "templates": len(templates),
        "outcomes": dict(overall),
        "statement_types": dict(types),
    }
    if split == "test":
        return report
    rows = []
    for tpl, texts in sorted(templates.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:top]:
        anchor, r = by_text[texts[0]]
        rows.append(
            {
                "n": len(texts),
                "template": tpl,
                "example": texts[0],
                "anchor": anchor.isoformat(),
                "reading": {k: v for k, v in r.as_dict().items() if k != "statements"},
                "outcomes": dict(Counter(outcome_class(by_text[x][1]) for x in texts)),
            }
        )
    report["top"] = rows
    return report


def item_text(item: dict) -> str:
    """The text a batch item is read from: ``text``, else the two CSV fields joined by ``||``."""
    if item.get("text"):
        return str(item["text"])
    parts = [str(item.get(k) or "").strip() for k in TEXT_KEYS]
    parts = [p for i, p in enumerate(parts) if p and p not in parts[:i]]
    return " || ".join(parts)


def read_items(items: Path, out: Path) -> int:
    """Read a JSONL batch ({item_id, date_of_update | anchor, text | the CSV fields}) to JSONL."""
    n = 0
    with items.open() as src, out.open("w") as dst:
        for line in src:
            if not line.strip():
                continue
            item = json.loads(line)
            r = read(item_text(item), str(item.get("anchor") or item["date_of_update"]))
            row = {"item_id": item.get("item_id"), "reading": r.as_dict()}
            row["literal_v1"] = as_literal_v1(r)
            dst.write(json.dumps(row) + "\n")
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.rules", description=__doc__.splitlines()[0]
    )
    ap.add_argument("--text", help="one notice text to read")
    ap.add_argument("--anchor", help="its Date of Update (YYYY-MM-DD or MM/DD/YYYY)")
    ap.add_argument("--inventory", action="store_true", help="template inventory of captures")
    ap.add_argument("--split", choices=("train", "test"), default="train")
    ap.add_argument("--captures", type=Path, default=CAPTURES)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--items", type=Path, help="JSONL batch of items to read (with --out)")
    ap.add_argument("--out", type=Path, help="inventory JSON, or the readings JSONL of --items")
    args = ap.parse_args(argv)
    if args.items:
        if not args.out:
            ap.error("--items needs --out")
        print(f"{read_items(args.items, args.out)} readings -> {args.out}")
        return 0
    if args.inventory:
        report = inventory(args.captures, args.split, args.top)
        if args.out:
            args.out.write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "top"}, indent=1))
        for i, row in enumerate(report.get("top", []), 1):
            r = row["reading"]
            print(
                f"{i:3d} {row['n']:4d}  {row['template'][:70]:70s}  {r['statement_type']:18s}"
                f" {r['granularity'] or r['abstain_reason']}"
            )
        return 0
    if not (args.text and args.anchor):
        ap.error("give --text and --anchor, or --inventory")
    print(json.dumps(read(args.text, args.anchor).as_dict(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
