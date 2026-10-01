"""Build OpEst-FDA: statement events and interval-censored recovery outcomes from the FDA CSV.

Input: Internet Archive captures of the FDA consolidated drug-shortage CSV, one file per capture
in ``external_data/fda_wayback_csv/<timestamp>.csv`` (``fetch_wayback_csv.py``). Each capture is
a full listing, so a presentation's history is the sequence of its rows across captures.

Parsing. Bytes are decoded as utf-8-sig, falling back to latin-1. Leading blank lines are
skipped; headers are stripped and mapped to canonical names through aliases (``HEADER_ALIASES``).
A file with no recognisable header, or with a header and no rows, is not a capture: it is skipped
and named in the report.
Rows with more cells than the header (unescaped quotes inside Presentation or Related
Information) are realigned: cells up to the first cell that reads as a Type of Update followed by
a date are merged into Presentation, and any remaining overflow into Related Information; short
rows are padded. Such rows carry ``row_repaired``. Type of Update is snapped to New, Revised or
Reverified by closest match ("Reveriifed", "Revisee", "NNew"); Status to current ("Current",
"Currently in shortage"), resolved or discontinued ("To be Discontinued" in any case).

Presentation threads. A row's key is (listing, generic, company, presentation), each normalised
(NFKC, lower case, quotes and dashes unified, whitespace collapsed). ``listing`` is ``shortage``
(status Current or Resolved: the FDA's shortage entry, whose status is set per generic) or
``discontinuation`` (To Be Discontinued: a separate entry that can list the same presentation at
the same time). Rows are linked into threads capture by capture: first on the exact key, then,
for rows left over, on the package NDCs in the presentation text (largest Jaccard overlap with a
thread of the same listing not yet matched in that capture, most recently seen first, one to
one). This carries a thread through re-formatting of presentation, generic and company names
(the FDA's system change in November 2023, relabelling after acquisitions). Duplicate keys within
one capture keep the row with the latest Date of Update. Generic names are linked into
``generic_id`` through threads that carry more than one name (union-find); the id is the first
normalised name seen.

Statement text. A row's statement is its Related Information, preceded by its Availability
Information when that is more than a bare availability label (it has a digit or a timing cue:
before 2023 estimates were often written there, "Next Delivery and Estimated Recovery: June
2024"; later the field is a controlled label). Both raw fields are kept.

Statement events. Within a thread, a new statement event starts when the normalised statement
text changes, when the thread returns from Resolved to Current, or when it reappears after at
least one capture's absence with a different Date of Update. Otherwise a later row with the same
text is a re-confirmation (a "Reverified" re-stamp, or a "Revised" stamp with unchanged text),
not a new statement. An event is dated by the Date of Update of the row where it is first seen
(the capture date when that is missing or later than the capture). ``revision_index`` counts the
earlier events of the thread. The events table holds only what is known when the event is first
seen: the number of re-confirmations, the next revision and every other fact from later captures
are outcome information and go to the outcome files.

Timing phrases. ``timing_candidates`` lists, as JSON ``[[tag, text], ...]``, the spans of the
statement text that look like timing phrases (month and year, ranges, numeric dates, quarters,
halves, seasons, "week of", relative durations, bare years, and no-estimate phrases such as
"TBD"). They are candidates only; the rule reader interprets them. ``has_date_like`` is true when
any tag other than NO_ESTIMATE is present.

Outcomes (shortage-listing events only). Using captures after the one where the event is first
seen, each capture gives the thread a state under each recovery definition:

* A (the FDA calls it resolved): recovered when the thread's row has status Resolved, or the row
  is absent while its generic is listed and Resolved (the generic as named in that capture, else
  its linked generic_id);
* B (supply is back): recovered when the row's Availability Information reads as available
  (``availability_class == "available"``: "Available", "Inventory is currently available", not
  "limited", "allocation", "backorder" or "unavailable"), or when A holds. B is never later
  than A. A mention of "available" that is negated, future or estimated does not count ("no
  release date available at this time", "will be available in June", "available by 4/5/19",
  "available soon"), and neither does a string the author rejected (see Availability check
  below).
* BL (sensitivity for B): as B, with limited supply ("Limited Availability", "on allocation")
  counted as available.

A capture is "not recovered" when the row is listed with status Current (A) and, for B and BL,
also not available (not even limited, for BL); an absent row whose generic is Current or unlisted
says nothing. Discontinuation is a competing event and wins ties: the presentation (NDC overlap
or same text key) newly appears in the discontinuation listing, To Be Discontinued, whose Date
Discontinued is kept (``disc_date_field_X``). A Date Discontinued cell on a shortage row is not
used: in the train captures it mostly repeats the Date of Update of a resolution and appears on
products that stayed on the market (Leuprolide while Available, Sterile Water for Injection); the
first capture where one newly appears is kept for sensitivity (``date_discontinued_on_row_date``).

The outcome is a bracket: ``lower`` is the last capture at which the thread was seen not recovered
(at least the capture where the event was first seen), ``upper`` the first capture showing the
event. With neither event by the last capture the outcome is right-censored at ``lower``;
``censor_reason_X`` says whether the thread was still listed at the last capture
(``end_of_archive``; ``end_of_train`` for a train event at its horizon, see Sealing; ``no_followup``
for an event first seen at the archive's last capture) or left the list while its generic was
Current or unlisted (``absent_generic_current``, ``absent_generic_unlisted``), and then
``exit_date_X`` is the first capture where it was missing (for the sensitivity analysis that
counts leaving the list as recovery). An event is at risk under A when its row is Current at
first sight, and under B (BL) when it is also not available (not even limited) then; other
shortage events get ``not_at_risk``. Days are counted from the event date. ``observable31_X``
marks a finite bracket no wider than 31 days.

Statement level. Presentation-level events with the same listing, generic_id, company, statement
text and event date form one distinct statement (``statement_group_id``). Its outcome, in the
``group_*`` columns repeated on each member row, follows the members at risk: it is recovered
when every member that is not discontinued has recovered, with ``lower = max lower`` and ``upper
= max upper``; censored when any such member is censored (``lower = max lower``); discontinued
when every member is.

Availability check. ``write_availability_strings`` lists every distinct normalised Availability
Information string that the rule classes available or limited, and every string that the fix of
1 October 2026 moved out of available (``class_before_fix`` is the class when any mention of
"available" counted), with the number of capture rows that carry it and nothing else. The author
marks each string; the rejected ones are entered in ``REJECTED_AVAILABLE`` and are then classed
other (also a rejected limited string; none is re-classed as limited). An entry that no capture
row carries stops the build. The list is written by its own command (below) and never by
``main``.

Sealing. Events dated 2023-01-01 or later form the test period. Their outcomes are written only
to ``--sealed`` (``outcomes_test.csv.gz``, a gzip with a fixed header time so the sha256 printed
is reproducible for the same inputs); no value from them is printed. Train outcomes go to
``--out`` and are followed only to the last capture before 2023-01-01: a train event still open
there is administratively censored (``censor_reason_X = end_of_train``), and every follow-up field
(``next_event_id``, ``n_followup_listed``, ``followup_end_date``, ...) stops at that capture, so
no train outcome says how a thread stood in the test period. One exception is first-sight
information, not an outcome: a train event whose first capture is itself in the test period (a
Date of Update late in 2022, first archived in 2023) has that capture as its horizon. It has no
follow-up and is censored ``end_of_train`` at its first-seen capture when at risk; the first-seen
capture dates of the event and of the other members of its statement are the only test-period
dates in its row. The same train outcomes followed to the archive's end go to ``--sealed``
(``outcomes_train_uncensored.csv.gz``) for use after the test outcomes are unsealed. Printed are
counts only: rows, realigned rows per capture, threads, events, the capture-gap summary and the
Gate 1 counts (``gate_counts``; the fourth takes the primary model's cutoff month from
``--cutoff``). The events table holds every statement, so the later rows of a thread show that it
was still listed; nothing may be tabulated from that before registration either.

Capture manifest. ``main`` and ``open_build`` first call ``verify_manifest`` on the capture
folder, which runs ``analysis.coling.manifest.verify`` when that module exists and stops the build
on a mismatch; the report says whether the folder was verified.

Usage (from the repository root). The full build writes the sealed files, so it is run only at
the corpus freeze::

    PYTHONPATH=. python -m analysis.coling.corpus [--captures external_data/fda_wayback_csv]
        [--out analysis/coling/out] [--sealed external_data/sealed] [--cutoff 2023-12-31]

The availability check list (``analysis/coling/out/availability_strings.csv``) reads the captures
only and seals nothing::

    PYTHONPATH=. python -c "from analysis.coling import corpus; corpus.write_availability_strings()"

The two open tables alone (``events.csv.gz`` and ``outcomes_train.csv.gz``, the same bytes as the
full build writes) and the report, after the manifest check and with nothing sealed; ``cutoff=``
takes the place of ``--cutoff``::

    PYTHONPATH=. python -c "from analysis.coling import corpus; corpus.open_build()"
"""

from __future__ import annotations

import argparse
import bisect
import csv
import difflib
import hashlib
import importlib
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TEST_START = pd.Timestamp("2023-01-01")
GATE_END = pd.Timestamp("2025-12-31")
# Last day of the primary model's training-cutoff month (Llama 3.3 70B, per the design memo).
# It is only the default of ``gate_counts`` and ``--cutoff``; pass the documented value there.
CUTOFF = pd.Timestamp("2023-12-31")
OBSERVABLE_WIDTH_DAYS = 31
GATE_THRESHOLDS = {"statements": 600, "observable": 250, "episodes": 100, "post_cutoff": 150}
GZIP = {"method": "gzip", "mtime": 0}
CAPTURES_DIR = Path("external_data/fda_wayback_csv")
OUT_DIR = Path("analysis/coling/out")
STRINGS_PATH = OUT_DIR / "availability_strings.csv"
STRING_COLUMNS = ("string", "class_after_fix", "class_before_fix", "n_rows")
MANIFEST_MODULE = "analysis.coling.manifest"

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "generic_name": ("genericname", "drugname", "generic"),
    "company_name": ("companyname", "company", "manufacturer"),
    "contact_info": ("contactinfo", "contactinformation"),
    "presentation": ("presentation", "presentations"),
    "type_of_update": ("typeofupdate", "updatetype"),
    "date_of_update": ("dateofupdate", "updatedate", "dateupdated", "lastupdated"),
    "availability": ("availabilityinformation", "availability", "availabilityinfo"),
    "related": ("relatedinformation", "relatedinfo"),
    "resolved_note": ("resolvednote",),
    "reason": ("reasonforshortage", "shortagereason", "reason"),
    "therapeutic_category": ("therapeuticcategory", "therapeuticcategories"),
    "status": ("status",),
    "change_date": ("changedate",),
    "date_discontinued": ("datediscontinued", "discontinueddate"),
    "initial_posting_date": ("initialpostingdate", "initialposting", "dateposted"),
}
REQUIRED = ("generic_name", "company_name", "presentation", "date_of_update", "status")
TEXT_COLUMNS = tuple(HEADER_ALIASES)
UPDATE_TYPES = ("new", "revised", "reverified")
_DATE_CELL = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$")
_HEADER_LINE = re.compile(r"^[^\r\n]*generic\s*name[^\r\n]*,", re.IGNORECASE | re.MULTILINE)
_TRANS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


class CaptureFormatError(ValueError):
    """A capture file that is not a shortage CSV (no recognisable header, or no rows)."""


def decode(raw: bytes) -> str:
    """Decode a capture: utf-8 (with or without BOM), else latin-1."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def header_key(cell: str) -> str:
    return re.sub(r"[^a-z]", "", cell.lower())


def canonical_header(cells: Sequence[str]) -> list[str]:
    """Map raw header cells to canonical names; unknown columns keep their squashed name."""
    lookup = {alias: name for name, aliases in HEADER_ALIASES.items() for alias in aliases}
    out = []
    for cell in cells:
        key = header_key(cell)
        out.append(lookup.get(key, key or "unnamed"))
    return out


def clean_cell(cell: str) -> str:
    """Collapse whitespace and drop stray quote characters left by broken quoting."""
    return re.sub(r"\s+", " ", cell).strip().strip('"').strip()


def norm_text(text: str) -> str:
    """Normalised form for keys: NFKC, unified quotes and dashes, lower case, no edge punctuation."""
    text = unicodedata.normalize("NFKC", text or "").translate(_TRANS)
    return re.sub(r"\s+", " ", text).strip().lower().strip(" .;,\"'")


def norm_update_type(cell: str) -> str:
    """Snap a Type of Update cell to new/revised/reverified ('' when it is not one)."""
    letters = re.sub(r"[^a-z]", "", (cell or "").lower())
    if not letters or len(letters) > 14:
        return ""
    if letters in UPDATE_TYPES:
        return letters
    match = difflib.get_close_matches(letters, UPDATE_TYPES, n=1, cutoff=0.6)
    return match[0] if match else ""


def norm_status(cell: str) -> str:
    text = norm_text(cell)
    if "discontinu" in text:
        return "discontinued"
    if text.startswith("resolv"):
        return "resolved"
    if text.startswith("current"):
        return "current"
    return ""


def realign(cells: list[str], header: list[str]) -> tuple[list[str], bool]:
    """Fit a row with the wrong number of cells to the header (see the module docstring)."""
    n = len(header)
    if len(cells) == n:
        return cells, False
    if len(cells) < n:
        return cells + [""] * (n - len(cells)), True
    cells = list(cells)
    if "type_of_update" in header:
        u = header.index("type_of_update")
        for j in range(u, len(cells) - 1):
            if norm_update_type(cells[j]) and _DATE_CELL.match(cells[j + 1]):
                if j > u:
                    cells = [*cells[: u - 1], ",".join(cells[u - 1 : j]), *cells[j:]]
                break
    extra = len(cells) - n
    if extra > 0:
        r = header.index("related") if "related" in header else n - 1
        cells = [*cells[:r], ",".join(cells[r : r + extra + 1]), *cells[r + extra + 1 :]]
    return cells, True


def read_capture(path: Path) -> pd.DataFrame:
    """One capture as a frame of canonical text columns plus ``row_repaired`` and ``row_in_file``."""
    text = decode(path.read_bytes())
    header_line = _HEADER_LINE.search(text[:20_000])
    if header_line is None:
        raise CaptureFormatError(f"{path.name}: no header line")
    reader = csv.reader(io.StringIO(text[header_line.start() :], newline=""))
    header = canonical_header(next(reader))
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise CaptureFormatError(f"{path.name}: missing columns {missing}")
    records = []
    for i, cells in enumerate(reader):
        if not any(c.strip() for c in cells):
            continue
        fitted, repaired = realign(cells, header)
        rec = {name: clean_cell(value) for name, value in zip(header, fitted, strict=True)}
        rec["row_repaired"] = repaired
        rec["row_in_file"] = i
        records.append(rec)
    if not records:
        raise CaptureFormatError(f"{path.name}: a header and no rows")
    frame = pd.DataFrame.from_records(records)
    for col in TEXT_COLUMNS:
        if col not in frame:
            frame[col] = ""
    return frame[[*TEXT_COLUMNS, "row_repaired", "row_in_file"]]


def capture_files(directory: Path) -> list[Path]:
    """Capture CSVs named by a 14-digit Wayback timestamp, in time order."""
    return sorted(p for p in directory.glob("*.csv") if re.fullmatch(r"\d{14}", p.stem))


def parse_dates(values: pd.Series) -> pd.Series:
    """Parse FDA date cells (mm/dd/yyyy, with fallbacks) to Timestamps; NaT when unparseable."""
    text = values.fillna("").astype(str).str.strip()
    out = pd.to_datetime(text, format="%m/%d/%Y", errors="coerce")
    for fmt in ("%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        miss = out.isna() & (text != "")
        if not miss.any():
            break
        out[miss] = pd.to_datetime(text[miss], format=fmt, errors="coerce")
    return out


# ---------------------------------------------------------------------------
# Field normalisers
# ---------------------------------------------------------------------------

_NDC_HYPHEN = re.compile(r"(?<![\d-])(\d{3,5})-{1,2}(\d{2,4})-(\d{1,4})(?![\d-])")
_NDC_DIGITS = re.compile(r"ndc[\s#:]*(\d{10,11})(?!\d)", re.IGNORECASE)
_NDC_SHAPES = {(4, 4, 2), (5, 3, 2), (5, 4, 1), (5, 4, 2)}


def extract_ndcs(text: str) -> frozenset[str]:
    """Package NDCs in a presentation, as 11-digit 5-4-2 strings where the shape allows.

    An unhyphenated 10-digit NDC is ambiguous and yields its three 11-digit readings; a
    non-standard hyphenation keeps its digits behind an ``x``.
    """
    out: set[str] = set()
    for a, b, c in _NDC_HYPHEN.findall(text or ""):
        if (len(a), len(b), len(c)) in _NDC_SHAPES:
            out.add(a.zfill(5) + b.zfill(4) + c.zfill(2))
        else:
            out.add("x" + a + b + c)
    for d in _NDC_DIGITS.findall(text or ""):
        if len(d) == 11:
            out.add(d)
        else:
            out.update({"0" + d, d[:5] + "0" + d[5:], d[:9] + "0" + d[9:]})
    return frozenset(out)


_UNAVAILABLE = re.compile(
    r"unavailab|not (?:currently )?available|no (?:product|inventory|supply|stock)|back ?-?order"
    r"|out of stock|depleted|stock ?out|temporarily|on hold|not shipping|no longer|discontinu"
)
_LIMITED = re.compile(r"limited|allocat|intermittent|constrain|reduced|short supply|contract")
_AVAILABLE = re.compile(r"\bavailable\b|in stock")
SUPPLY_CLASSES = ("available", "limited")

# Strings the author rejected in the check of ``availability_strings.csv``, as that file prints
# them (``availability_key``): text that the rule below would class available or limited and
# that reports neither. A string listed here is classed other. The tuple is frozen with this file.
REJECTED_AVAILABLE: tuple[str, ...] = ()
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# A mention of "available" or "in stock" reports supply on hand unless it is negated, future or
# estimated. The cue stands before the mention in the same clause (at most a few words between,
# no punctuation), or a time or a word of waiting follows the mention directly.
_WORDS = r"(?:[\w/'-]+\s+)"
_NEGATED_BEFORE = re.compile(
    rf"\b(?:no|not|never|none|nothing|cannot|unable|\w+n't)\s+{_WORDS}{{0,4}}$"
)
_FUTURE_BEFORE = re.compile(
    rf"\b(?:be|become|becomes|(?:will|shall|should|would)\s+have)\s+{_WORDS}{{0,2}}$"
)
_STILL_BEFORE = re.compile(
    rf"\b(?:continu\w*\s+to\s+be|(?:has|have)\s+(?:\w+\s+)?become)\s+{_WORDS}{{0,2}}$"
)
_ESTIMATED_BEFORE = re.compile(
    r"\b(?:estimat(?:e|es|ed)|expect(?:s|ed)?|anticipat(?:e|es|ed)|projected|tentative(?:ly)?"
    rf"|scheduled|planned|targeted)\s+{_WORDS}{{0,3}}$"
)
_LEAD_IN_AFTER = re.compile(
    r"\s*(?:(?:again|for (?:sale|order|ordering|shipment|shipping|purchase)|to (?:order|ship))\s+)?"
)
_WAITING_AFTER = re.compile(
    r"(?:soon|shortly|later|tomorrow|date|pending|(?:up)?on (?:release|approval|arrival)"
    r"|(?:when|once) released)\b"
)
_ABOUT = r"(?:about|around|approximately|approx\.?|roughly)"
_FUTURE_PREP_AFTER = re.compile(
    r"(?:(?:(?:starting|beginning|sometime)\s+)?(?:on or (?:about|after|before)|by|in|on|at|from"
    rf"|within|after|eta|est\.?|{_ABOUT}|as early as|(?:not|no) (?:sooner|earlier) than"
    rf"|not before)(?:\s+{_ABOUT})?|starting|beginning)\s+(?:the\s+)?"
)
_PART_AFTER = re.compile(r"(?:early|mid|late)(?:\s+to\s+(?:early|mid|late))?[\s-]+")
_WEEK_AFTER = re.compile(
    r"(?:the\s+)?(?:(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+)?(?:week|wk)\b"
)
_NAMED_PERIOD = re.compile(r"(?:next|coming|following|this|(?:the\s+)?end)\b")
_AMBIGUOUS_AFTER = {"may", "fall"}


def availability_key(text: str) -> str:
    """An Availability Information string as the check list prints it and as the rejection list
    matches it: normalised (``norm_text``), with any e-mail address replaced by ``[email]`` so
    that none is copied into the check list or into this file."""
    return _EMAIL.sub("[email]", norm_text(text))


def _starts_with_time(text: str, after_preposition: bool) -> bool:
    """Whether ``text`` opens with a timing phrase (the candidates' patterns, matched at 0, also
    behind "early", "mid" or "late": "early next year", "mid to late June").

    Without a preposition before it, a bare "may" or "fall" (which need not be a time) and a bare
    duration ("6 months dating", "30 days coverage") do not count.
    """
    if _WEEK_AFTER.match(text):
        return True
    part = _PART_AFTER.match(text)
    for start in (0, part.end()) if part else (0,):
        for tag, pattern in _COMPILED:
            hit = pattern.match(text, start)
            if hit is None:
                continue
            span = hit.group(0)
            if after_preposition:
                return True
            if tag == "RELATIVE" and not _NAMED_PERIOD.match(span):
                continue
            bare = re.sub(r"[^a-z]", "", span) in _AMBIGUOUS_AFTER and not re.search(r"\d", span)
            if tag in {"MONTH", "SEASON"} and bare and start == 0:
                continue
            return True
    return False


def _timed_after(after: str) -> bool:
    """Whether a time follows a mention directly: "available by 4/5/19", "available in February
    2024", "available for sale wk of 12/9", "back in stock week 3 of May", "available TBD"; or a
    word of waiting: "available soon", "available upon release", "available date".

    "until", "through" and "as of" are not future ("available until mid-November" is on hand
    now), and punctuation after the mention ends the reach ("Available, Q2 2024" is a label)."""
    rest = after[_LEAD_IN_AFTER.match(after).end() :]
    if _WAITING_AFTER.match(rest):
        return True
    prep = _FUTURE_PREP_AFTER.match(rest)
    if prep is not None and _starts_with_time(rest[prep.end() :], True):
        return True
    return _starts_with_time(rest, False)


def _on_hand(text: str, mention: re.Match[str]) -> bool:
    """Whether one mention of "available" or "in stock" reports supply on hand now."""
    before = text[: mention.start()]
    if _NEGATED_BEFORE.search(before) or _ESTIMATED_BEFORE.search(before):
        return False
    if _FUTURE_BEFORE.search(before) and not _STILL_BEFORE.search(before):
        return False
    return not _timed_after(text[mention.end() :])


def _availability_class(t: str, any_mention: bool) -> str:
    if not t:
        return "blank"
    if _UNAVAILABLE.search(t):
        return "unavailable"
    if _LIMITED.search(t):
        return "limited"
    mentions = list(_AVAILABLE.finditer(t))
    if mentions and (any_mention or any(_on_hand(t, m) for m in mentions)):
        return "available"
    return "other"


def availability_class(text: str) -> str:
    """blank, unavailable, limited, available or other (checked in that order).

    A string is available only when some mention of "available" or "in stock" reports supply on
    hand now. A mention does not count when it is negated ("no release date available at this
    time", "not yet available"), future or estimated ("will be available in June", "to be
    available", "tentatively available", "estimated date available") or directly followed by a
    time ("available by 4/5/19", "available in February 2024", "available March 2019") or by a
    word of waiting ("available soon", "available upon release"). A string with no mention that
    counts is other. A string in ``REJECTED_AVAILABLE`` is other as well.
    """
    t = norm_text(text)
    found = _availability_class(t, any_mention=False)
    rejected = found in SUPPLY_CLASSES and availability_key(t) in REJECTED_AVAILABLE
    return "other" if rejected else found


def availability_class_before_fix(text: str) -> str:
    """The rule as it stood before 1 October 2026: any mention of "available" or "in stock"
    counted, and no string was rejected. Kept only so that the check list can show what the
    present rule moved out of available; no outcome uses it."""
    return _availability_class(norm_text(text), any_mention=True)


_MONTH_WORDS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_TIMING_CUE = re.compile(
    r"\d|tbd|determin|unknown|until|expect|estimat|anticipat|\bnext\b|recover|releas|resuppl"
    r"|deliver|restock|resum|return|week|month|quarter|\bq[1-4]\b|spring|summer|autumn|winter"
    r"|\beta\b|soon|\blate\b|early|\bmid\b|end of|pending|time ?frame|\b(?:" + _MONTH_WORDS + r")\b"
)


def availability_is_bare(text: str) -> bool:
    """True when an Availability Information cell is only a label (no digit, no timing cue)."""
    return not _TIMING_CUE.search(norm_text(text))


def statement_text(availability: str, related: str) -> str:
    """The statement a row makes: Related Information, after availability text that is not bare."""
    parts = []
    if availability and not availability_is_bare(availability):
        parts.append(availability)
    if related and not (parts and norm_text(related) == norm_text(availability)):
        parts.append(related)
    return " || ".join(parts)


# ---------------------------------------------------------------------------
# Timing-phrase candidates (extraction only; interpretation is the rule reader's job)
# ---------------------------------------------------------------------------

_MON = r"(?:" + _MONTH_WORDS + r")(?![a-z])\.?"
_YR = r"(?:19|20)\d{2}(?!\d)"
_MOD = (
    r"(?:(?:early|mid|middle(?:\s+of)?|late|(?:the\s+)?end(?:\s+of)?|beginning(?:\s+of)?"
    r"|start(?:\s+of)?|(?:first|second)\s+half\s+of)[\s-]+)?"
)
_SEP = r"\s*(?:-|to|through|thru|until|/|or|and)\s*"
_NUM_WORD = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_TIMING_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "MONTH_RANGE",
        rf"\b{_MOD}{_MON}(?:\s*,?\s*{_YR})?{_SEP}{_MOD}{_MON}(?:\s*,?\s*{_YR}|-\d{{2}}(?!\d))?",
    ),
    (
        "WEEK_OF",
        rf"\b(?:the\s+)?week\s+of\s+(?:{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*,?\s*{_YR})?"
        rf"|\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?)",
    ),
    ("MONTH_DAY_YEAR", rf"\b{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s*{_YR}"),
    ("DAY_MONTH_YEAR", rf"\b\d{{1,2}}\s+{_MON}\s*,?\s*{_YR}"),
    ("MONTH_YEAR", rf"\b{_MOD}{_MON}(?:\s*,?\s*(?:of\s+)?{_YR}|\s*-\s*\d{{2}}(?!\d)|\s*'\d{{2}})"),
    ("MONTH_DAY", rf"\b{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?(?!\d)"),
    (
        "QUARTER",
        rf"\b{_MOD}(?:q[1-4]|[1-4]q|(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter)"
        rf"(?:\s*(?:of\s+)?[-/,]?\s*(?:{_YR}|'?\d{{2}}(?!\d)))?",
    ),
    (
        "HALF",
        rf"\b(?:(?:first|second|1st|2nd)\s+half(?:\s+of)?\s*|h[12]\s*|[12]h\s*)"
        rf"(?:{_YR}|'?\d{{2}}(?!\d))",
    ),
    ("SEASON", rf"\b{_MOD}(?:spring|summer|fall|autumn|winter)(?![a-z])(?:\s+(?:of\s+)?{_YR})?"),
    ("NUMERIC_MONTH_YEAR", rf"\b(?:0?[1-9]|1[0-2])/{_YR}"),
    (
        "NUMERIC_DATE",
        r"\b(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?:/(?:\d{4}|\d{2}))?(?![\d/])",
    ),
    ("ISO_DATE", r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"),
    (
        "RELATIVE",
        rf"\b(?:(?:{_NUM_WORD}|a|a\s+few|few|several|couple\s+of)"
        rf"(?:\s*(?:-|to)\s*{_NUM_WORD})?\s*\+?\s*(?:business\s+|calendar\s+)?"
        r"(?:days?|weeks?|wks?|months?|mos?|years?)(?![a-z])"
        r"|(?:next|coming|following|this)\s+(?:few\s+)?(?:days?|weeks?|months?|quarter|year)"
        r"|(?:the\s+)?end\s+of\s+(?:the\s+)?(?:week|month|quarter|year))",
    ),
    ("MONTH", rf"\b{_MOD}{_MON}"),
    ("YEAR", rf"\b{_MOD}{_YR}(?!\s*(?:mg|mcg|ml|g|units?|iu|%|count|ct|tablets?|vials?)\b)"),
    (
        "NO_ESTIMATE",
        r"\btbd\b|\bt\.b\.d\b|to be (?:determined|confirmed)|\btbc\b|\bunknown\b"
        r"|not (?:yet )?(?:known|determined)|undetermined|\bno eta\b|\bpending\b"
        r"|no (?:estimated |anticipated |expected )?(?:release |recovery |resupply |return "
        r"|availability |ship |shipping |delivery )?(?:date|timeframe|time frame|eta)\b"
        r"|(?:cannot|unable to) (?:estimate|provide|determine)",
    ),
)
_COMPILED = tuple((tag, re.compile(p, re.IGNORECASE)) for tag, p in _TIMING_PATTERNS)
_TEMPORAL_PREP = {"in", "by", "until", "till", "through", "thru", "from", "of", "before", "after"}
_AMBIGUOUS_BARE = {"may", "mar", "fall", "spring", "winter", "summer", "march"}
DATE_TAGS = frozenset(tag for tag, _ in _TIMING_PATTERNS) - {"NO_ESTIMATE"}


def _keep_bare(text: str, start: int, span: str) -> bool:
    """A bare month or season ("may", "fall") counts only after a temporal preposition."""
    word = re.sub(r"[^a-z]", "", span.lower())
    if word not in _AMBIGUOUS_BARE:
        return True
    before = re.findall(r"[a-z]+", text[:start].lower())
    return bool(before) and before[-1] in _TEMPORAL_PREP


def timing_candidates(text: str) -> list[tuple[str, str]]:
    """Non-overlapping timing-phrase spans in text order, as (tag, text); first pattern wins.

    Matching runs on the text with quotes and dashes unified (NFKC), in its original case.
    """
    text = unicodedata.normalize("NFKC", text or "").translate(_TRANS)
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, str, str]] = []
    for tag, pattern in _COMPILED:
        for m in pattern.finditer(text):
            a, b = m.span()
            span = m.group(0).strip()
            if not span or any(a < y and x < b for x, y in taken):
                continue
            if tag in {"MONTH", "SEASON"} and not _keep_bare(text, a, span):
                continue
            taken.append((a, b))
            found.append((a, tag, span))
    return [(tag, span) for _, tag, span in sorted(found)]


# ---------------------------------------------------------------------------
# Observations and threads
# ---------------------------------------------------------------------------


@dataclass
class Captures:
    """All captures as one long observation frame, plus per-capture metadata."""

    obs: pd.DataFrame
    stamps: list[str]
    dates: list[pd.Timestamp]
    skipped: list[str] = field(default_factory=list)
    n_dropped: int = 0
    realigned: dict[str, int] = field(default_factory=dict)  # stamp -> realigned rows as read


def load_captures(directory: Path) -> Captures:
    """Read every capture, normalise fields, drop statusless rows and duplicate keys."""
    frames, stamps, skipped = [], [], []
    realigned: dict[str, int] = {}
    for path in capture_files(directory):
        try:
            frame = read_capture(path)
        except CaptureFormatError as exc:
            skipped.append(str(exc))
            continue
        frame["cap_idx"] = len(stamps)
        frame["cap_stamp"] = path.stem
        realigned[path.stem] = int(frame["row_repaired"].sum())
        stamps.append(path.stem)
        frames.append(frame)
    if not frames:
        raise SystemExit(f"no readable captures in {directory}")
    dates = [pd.Timestamp(s[:8]) for s in stamps]
    obs = add_normalised_fields(pd.concat(frames, ignore_index=True))
    obs["cap_date"] = obs["cap_idx"].map(dict(enumerate(dates)))
    n_rows = len(obs)
    obs = obs[obs["listing"] != ""]
    obs = obs.sort_values(["cap_idx", "key", "dou", "row_in_file"], ascending=[1, 1, 0, 1])
    obs = obs.drop_duplicates(["cap_idx", "key"], keep="first")
    obs = obs.sort_values(["cap_idx", "row_in_file"]).reset_index(drop=True)
    return Captures(obs, stamps, dates, skipped, n_rows - len(obs), realigned)


def add_normalised_fields(obs: pd.DataFrame) -> pd.DataFrame:
    obs = obs.copy()
    obs["status_norm"] = obs["status"].map(norm_status)
    listing = {"current": "shortage", "resolved": "shortage", "discontinued": "discontinuation"}
    obs["listing"] = obs["status_norm"].map(listing).fillna("")
    obs["update_type"] = obs["type_of_update"].map(norm_update_type)
    obs["dou"] = parse_dates(obs["date_of_update"])
    obs["dd"] = parse_dates(obs["date_discontinued"])
    for raw, normed in (("generic_name", "g_norm"), ("company_name", "c_norm")):
        obs[normed] = obs[raw].map(norm_text)
    obs["p_norm"] = obs["presentation"].map(norm_text)
    parts = zip(obs["listing"], obs["g_norm"], obs["c_norm"], obs["p_norm"], strict=True)
    obs["key"] = ["\x1f".join(p) for p in parts]
    obs["ndcs"] = obs["presentation"].map(extract_ndcs)
    obs["avail_key"] = obs["availability"].map(availability_key)
    obs["avail_class"] = obs["availability"].map(availability_class)
    pairs = zip(obs["availability"], obs["related"], strict=True)
    obs["statement"] = [statement_text(a, r) for a, r in pairs]
    obs["stmt_key"] = obs["statement"].map(norm_text)
    return obs


def link_threads(obs: pd.DataFrame) -> np.ndarray:
    """Thread number per observation (see the module docstring for the matching rules)."""
    thread = np.full(len(obs), -1, dtype=np.int64)
    keys, ndcs, listing = obs["key"].tolist(), obs["ndcs"].tolist(), obs["listing"].tolist()
    by_key: dict[str, int] = {}
    by_ndc: dict[tuple[str, str], set[int]] = defaultdict(set)
    ndcs_of: dict[int, frozenset[str]] = {}
    last_seen: dict[int, int] = {}
    n_threads = 0
    for cap, idx in sorted(obs.groupby("cap_idx").indices.items()):
        taken: set[int] = set()
        pending = []
        for i in idx:
            tid = by_key.get(keys[i])
            if tid is not None and tid not in taken:
                thread[i] = tid
                taken.add(tid)
            else:
                pending.append(i)
        candidates = []
        for i in pending:
            pool = set().union(*(by_ndc.get((listing[i], n), set()) for n in ndcs[i])) - taken
            for tid in pool:
                jaccard = len(ndcs[i] & ndcs_of[tid]) / len(ndcs[i] | ndcs_of[tid])
                if jaccard > 0:
                    candidates.append((-jaccard, -last_seen[tid], tid, i))
        done: set[int] = set()
        for _, _, tid, i in sorted(candidates):
            if i not in done and tid not in taken:
                thread[i] = tid
                taken.add(tid)
                done.add(i)
        for i in pending:
            if thread[i] < 0:
                thread[i] = n_threads
                n_threads += 1
        for i in idx:
            tid = int(thread[i])
            by_key[keys[i]] = tid
            for n in ndcs[i]:
                by_ndc[(listing[i], n)].add(tid)
            ndcs_of[tid] = ndcs[i]
            last_seen[tid] = cap
    return thread


def link_generics(obs: pd.DataFrame) -> pd.Series:
    """generic_id per observation: generic names joined through shared threads (union-find).

    The id of a group is its name seen first, so it is readable and independent of thread ids.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first_seen = {name: i for i, name in reversed(list(enumerate(obs["g_norm"])))}
    for names in obs.groupby("thread")["g_norm"].unique():
        roots = sorted({find(n) for n in names}, key=first_seen.__getitem__)
        for other in roots[1:]:
            parent[other] = roots[0]
    return obs["g_norm"].map(find)


def generic_states(obs: pd.DataFrame, by: str = "generic_id") -> dict[tuple[str, int], str]:
    """Per (generic, capture): 'current' if any shortage row is Current, else 'resolved'.

    ``by`` is ``generic_id`` (linked names) or ``g_norm`` (the name as listed in that capture).
    """
    shortage = obs[obs["listing"] == "shortage"]
    states: dict[tuple[str, int], str] = {}
    for (gid, cap), statuses in shortage.groupby([by, "cap_idx"])["status_norm"]:
        states[(gid, int(cap))] = "current" if (statuses == "current").any() else "resolved"
    return states


def episode_starts(states: dict[tuple[str, int], str], n_caps: int) -> dict[tuple[str, int], int]:
    """Start capture of the generic-level shortage episode that contains each Current capture.

    An episode is a run of consecutive captures in which the generic is Current; a capture where
    it is Resolved or unlisted ends it. The start uses only the past.
    """
    starts: dict[tuple[str, int], int] = {}
    for gid in sorted({g for g, _ in states}):
        start = None
        for cap in range(n_caps):
            if states.get((gid, cap)) == "current":
                start = cap if start is None else start
                starts[(gid, cap)] = start
            else:
                start = None
    return starts


def short_hash(*parts: Any) -> str:
    return hashlib.sha1("\x1f".join(map(str, parts)).encode()).hexdigest()[:12]


def iso(value: Any) -> str:
    return "" if value is None or pd.isna(value) else pd.Timestamp(value).date().isoformat()


def same_date(a: Any, b: Any) -> bool:
    """Equality that treats two missing dates as equal."""
    return (pd.isna(a) and pd.isna(b)) or (not pd.isna(a) and not pd.isna(b) and a == b)


# ---------------------------------------------------------------------------
# Statement events
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """One statement event: the row where it is first seen and the rows that re-confirm it."""

    thread: int
    revision_index: int
    rows: list[int]
    prev: Event | None = None
    event_id: str = ""
    thread_id: str = ""
    date: pd.Timestamp = pd.NaT
    date_source: str = ""
    next_id: str = ""
    next_cap: int | None = None


def split_events(obs: pd.DataFrame) -> list[Event]:
    """Cut every thread into statement events (text change, relisting, or Resolved to Current)."""
    events: list[Event] = []
    caps, stmt = obs["cap_idx"].to_numpy(), obs["stmt_key"].to_numpy()
    status, dou = obs["status_norm"].to_numpy(), obs["dou"].tolist()
    for _, idx in sorted(obs.groupby("thread").indices.items()):
        current: Event | None = None
        for i in sorted(idx, key=lambda i: caps[i]):
            if current is not None:
                last = current.rows[-1]
                relisted = caps[i] - caps[last] > 1 and not same_date(dou[i], dou[last])
                reopened = status[last] == "resolved" and status[i] == "current"
                if stmt[i] == stmt[current.rows[0]] and not relisted and not reopened:
                    current.rows.append(i)
                    continue
            rev = 0 if current is None else current.revision_index + 1
            current = Event(int(obs.at[i, "thread"]), rev, [i], current)
            events.append(current)
    return events


def plausible_stamp(dou: pd.Timestamp, cap_date: pd.Timestamp) -> bool:
    """A Date of Update cannot be later than the capture that shows it (one day of slack)."""
    return dou <= cap_date + np.timedelta64(1, "D")


def date_events(events: list[Event], obs: pd.DataFrame) -> None:
    """Event date: the first row's Date of Update, or its capture date if missing or later."""
    for ev in events:
        i = ev.rows[0]
        dou, cap = obs.at[i, "dou"], obs.at[i, "cap_date"]
        if pd.isna(dou):
            ev.date, ev.date_source = cap, "capture:missing"
        elif not plausible_stamp(dou, cap):
            ev.date, ev.date_source = cap, "capture:future"
        else:
            ev.date, ev.date_source = dou, "dou"


def assign_ids(events: list[Event], obs: pd.DataFrame) -> None:
    """Stable ids from content (first capture stamp and keys), not from processing order."""
    thread_ids: dict[int, str] = {}
    for ev in events:
        i = ev.rows[0]
        if ev.thread not in thread_ids:
            thread_ids[ev.thread] = "T" + short_hash(obs.at[i, "cap_stamp"], obs.at[i, "key"])
        ev.thread_id = thread_ids[ev.thread]
        ev.event_id = "E" + short_hash(ev.thread_id, obs.at[i, "cap_stamp"], obs.at[i, "stmt_key"])
        if ev.prev is not None:
            ev.prev.next_id = ev.event_id
            ev.prev.next_cap = int(obs.at[i, "cap_idx"])


class Context:
    """Column lists and per-capture lookups shared by event and outcome derivation."""

    COLUMNS = (
        "cap_idx",
        "ndcs",
        "g_norm",
        "c_norm",
        "p_norm",
        "status_norm",
        "avail_class",
        "dd",
        "date_discontinued",
        "generic_id",
        "listing",
        "dou",
    )

    def __init__(self, caps: Captures) -> None:
        obs = caps.obs
        self.obs = obs
        self.dates = caps.dates
        self.stamps = caps.stamps
        self.col = {name: obs[name].tolist() for name in self.COLUMNS}
        rows: dict[int, dict[int, int]] = defaultdict(dict)
        for i, (tid, cap) in enumerate(zip(obs["thread"], obs["cap_idx"], strict=True)):
            rows[int(tid)][int(cap)] = i
        self.thread_rows = dict(rows)
        self.thread_caps = {tid: sorted(r) for tid, r in self.thread_rows.items()}
        # Discontinuation listing per capture: NDC or text key -> its Date Discontinued cell.
        self.d_ndcs: dict[int, dict[str, str]] = defaultdict(dict)
        self.d_keys: dict[int, dict[tuple[str, str, str], str]] = defaultdict(dict)
        disc = obs[obs["listing"] == "discontinuation"]
        cols = ["cap_idx", "g_norm", "c_norm", "p_norm", "ndcs", "date_discontinued"]
        for cap, g, c, p, nd, dd in disc[cols].itertuples(index=False):
            for n in nd:
                self.d_ndcs[int(cap)].setdefault(n, dd)
            self.d_keys[int(cap)].setdefault((g, c, p), dd)
        self.train_last = max((k for k, d in enumerate(self.dates) if d < TEST_START), default=-1)
        self.gstate = generic_states(obs)
        self.gstate_name = generic_states(obs, by="g_norm")
        self.episodes = episode_starts(self.gstate, len(caps.dates))

    def horizon(self, ev: Event, full: bool = False) -> int:
        """The last capture an event's outcome may use: the archive's last for a test event (and
        for ``full``), else the last capture before TEST_START (or the event's first capture, if
        that is later), so that no train outcome carries information from the test period."""
        if full or ev.date >= TEST_START:
            return len(self.dates) - 1
        return max(self.col["cap_idx"][ev.rows[0]], self.train_last)

    def discontinuation(self, row: int, cap: int) -> str | None:
        """The Date Discontinued cell ('' if blank) of the discontinuation-listing row for the
        presentation of observation ``row`` at ``cap``; None when it is not listed there."""
        c = self.col
        by_ndc = self.d_ndcs.get(cap, {})
        for n in sorted(c["ndcs"][row] & by_ndc.keys()):
            return by_ndc[n]
        return self.d_keys.get(cap, {}).get((c["g_norm"][row], c["c_norm"][row], c["p_norm"][row]))

    def in_discontinuation(self, row: int, cap: int) -> bool:
        """Whether the presentation of observation ``row`` is in the discontinuation listing."""
        return self.discontinuation(row, cap) is not None

    def generic_state(self, row: int, cap: int) -> str | None:
        """Shortage status of the generic of ``row`` at ``cap``: by the name as listed there if it
        is, else by the linked generic_id; None when the generic is unlisted."""
        c = self.col
        by_name = self.gstate_name.get((c["g_norm"][row], cap))
        return by_name if by_name is not None else self.gstate.get((c["generic_id"][row], cap))

    def row_at_or_before(self, thread: int, cap: int) -> int:
        """The thread's row at ``cap`` or, if it is unlisted there, its last row before."""
        caps = self.thread_caps[thread]
        k = bisect.bisect_right(caps, cap) - 1
        return self.thread_rows[thread][caps[k]]


EVENT_COLUMNS = (
    "event_id",
    "statement_group_id",
    "thread_id",
    "generic_id",
    "episode_id",
    "listing",
    "period",
    "event_date",
    "event_date_source",
    "first_seen_capture",
    "first_seen_date",
    "days_capture_after_event",
    "prev_capture_date",
    "left_truncated",
    "type_of_update",
    "date_is_reverification",
    "revision_index",
    "prev_event_id",
    "prev_event_date",
    "text_seen_before_in_thread",
    "generic_name",
    "company_name",
    "presentation",
    "ndcs",
    "status_at_statement",
    "availability_class",
    "availability_text",
    "related_text",
    "statement_text",
    "timing_candidates",
    "has_date_like",
    "has_no_estimate",
    "reason_for_shortage",
    "therapeutic_category",
    "initial_posting_date",
    "change_date",
    "date_discontinued",
    "resolved_note",
    "discontinuation_listed_at_statement",
    "row_repaired",
)


def earlier_texts(ev: Event, obs: pd.DataFrame) -> set[str]:
    texts = set()
    prev = ev.prev
    while prev is not None:
        texts.add(obs.at[prev.rows[0], "stmt_key"])
        prev = prev.prev
    return texts


def event_record(ev: Event, ctx: Context) -> dict[str, Any]:
    """Statement-time fields of one event (nothing from later captures)."""
    o = ctx.obs
    i = ev.rows[0]
    cap = int(o.at[i, "cap_idx"])
    listing, gid = o.at[i, "listing"], o.at[i, "generic_id"]
    start = ctx.episodes.get((gid, cap)) if listing == "shortage" else None
    cands = timing_candidates(o.at[i, "statement"])
    tags = {t for t, _ in cands}
    return {
        "event_id": ev.event_id,
        "statement_group_id": "S"
        + short_hash(listing, gid, o.at[i, "c_norm"], o.at[i, "stmt_key"], iso(ev.date)),
        "thread_id": ev.thread_id,
        "generic_id": gid,
        "episode_id": "" if start is None else f"{gid}@{iso(ctx.dates[start])}",
        "listing": listing,
        "period": "test" if ev.date >= TEST_START else "train",
        "event_date": iso(ev.date),
        "event_date_source": ev.date_source,
        "first_seen_capture": ctx.stamps[cap],
        "first_seen_date": iso(ctx.dates[cap]),
        "days_capture_after_event": (ctx.dates[cap] - ev.date).days,
        "prev_capture_date": iso(ctx.dates[cap - 1]) if cap > 0 else "",
        "left_truncated": cap == 0,
        "type_of_update": o.at[i, "update_type"],
        "date_is_reverification": o.at[i, "update_type"] == "reverified",
        "revision_index": ev.revision_index,
        "prev_event_id": "" if ev.prev is None else ev.prev.event_id,
        "prev_event_date": "" if ev.prev is None else iso(ev.prev.date),
        "text_seen_before_in_thread": o.at[i, "stmt_key"] in earlier_texts(ev, o),
        "generic_name": o.at[i, "generic_name"],
        "company_name": o.at[i, "company_name"],
        "presentation": o.at[i, "presentation"],
        "ndcs": " ".join(sorted(o.at[i, "ndcs"])),
        "status_at_statement": o.at[i, "status_norm"],
        "availability_class": o.at[i, "avail_class"],
        "availability_text": o.at[i, "availability"],
        "related_text": o.at[i, "related"],
        "statement_text": o.at[i, "statement"],
        "timing_candidates": json.dumps(cands),
        "has_date_like": bool(tags & DATE_TAGS),
        "has_no_estimate": "NO_ESTIMATE" in tags,
        "reason_for_shortage": o.at[i, "reason"],
        "therapeutic_category": o.at[i, "therapeutic_category"],
        "initial_posting_date": o.at[i, "initial_posting_date"],
        "change_date": o.at[i, "change_date"],
        "date_discontinued": o.at[i, "date_discontinued"],
        "resolved_note": o.at[i, "resolved_note"],
        "discontinuation_listed_at_statement": listing == "shortage"
        and ctx.in_discontinuation(i, cap),
        "row_repaired": bool(o.at[i, "row_repaired"]),
    }


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

DEFINITIONS = ("A", "B", "BL")
GATE_DEFINITIONS = ("B", "A")


@dataclass(frozen=True)
class State:
    """A later capture's reading of the event's presentation per definition: 'not', 'rec',
    'disc' or 'unknown'."""

    values: dict[str, str]
    how: str
    disc_date: str = ""

    def of(self, definition: str) -> str:
        return self.values[definition]


def state_at(ev: Event, ctx: Context, cap: int, disc_at_start: bool) -> State:
    """State of the event's presentation at a capture after the one where it was first seen."""
    c = ctx.col
    row = ctx.thread_rows[ev.thread].get(cap)
    probe = ctx.row_at_or_before(ev.thread, cap)
    disc = None if disc_at_start else ctx.discontinuation(probe, cap)
    if disc is not None:
        return State(dict.fromkeys(DEFINITIONS, "disc"), "discontinuation_listing", disc)
    if row is not None:
        rec_a = c["status_norm"][row] == "resolved"
        rec_b = rec_a or c["avail_class"][row] == "available"
        rec_bl = rec_b or c["avail_class"][row] == "limited"
        flags = {"A": rec_a, "B": rec_b, "BL": rec_bl}
        return State({d: "rec" if flags[d] else "not" for d in DEFINITIONS}, "listed")
    generic = ctx.generic_state(probe, cap)
    if generic == "resolved":
        return State(dict.fromkeys(DEFINITIONS, "rec"), "exit_generic_resolved")
    how = "absent_generic_current" if generic == "current" else "absent_generic_unlisted"
    return State(dict.fromkeys(DEFINITIONS, "unknown"), how)


def at_risk(ev: Event, ctx: Context) -> dict[str, bool]:
    """At risk: Current at first sight (A), and not yet available (B) or not even limited (BL)."""
    c = ctx.col
    i = ev.rows[0]
    current = c["listing"][i] == "shortage" and c["status_norm"][i] == "current"
    avail = c["avail_class"][i]
    return {
        "A": current,
        "B": current and avail != "available",
        "BL": current and avail not in {"available", "limited"},
    }


def walk(ev: Event, ctx: Context, risk: dict[str, bool], horizon: int) -> dict[str, dict[str, Any]]:
    """Scan later captures up to ``horizon`` until each at-risk definition sees its event.

    ``exit`` is the first capture after the last not-recovered one at which the thread is absent
    (reset if it is seen not recovered again), for the exit-as-recovery sensitivity.
    """
    first_cap = ctx.col["cap_idx"][ev.rows[0]]
    disc_at_start = ctx.in_discontinuation(ev.rows[0], first_cap)
    track = {
        d: {"lower": first_cap, "upper": None, "exit": None, "kind": "", "how": "", "disc": ""}
        for d in DEFINITIONS
    }
    open_defs = [d for d in DEFINITIONS if risk[d]]
    for cap in range(first_cap + 1, horizon + 1):
        if not open_defs:
            break
        state = state_at(ev, ctx, cap, disc_at_start)
        for d in list(open_defs):
            t = track[d]
            t["how"] = state.how
            value = state.of(d)
            if value == "not":
                t["lower"], t["exit"] = cap, None
            elif value == "unknown":
                t["exit"] = cap if t["exit"] is None else t["exit"]
            else:
                t["upper"] = cap
                t["kind"] = "recovered" if value == "rec" else "discontinued"
                t["disc"] = state.disc_date
                open_defs.remove(d)
    return track


def bracket(
    d: str, risk: bool, t: dict[str, Any], ev: Event, ctx: Context, horizon: int
) -> dict[str, Any]:
    """Outcome columns for one definition, using captures up to ``horizon`` only."""
    administrative = horizon < len(ctx.dates) - 1
    first_cap = ctx.col["cap_idx"][ev.rows[0]]
    lo = ctx.dates[t["lower"]] if risk else None
    up = ctx.dates[t["upper"]] if risk and t["upper"] is not None else None
    exit_date = None
    if not risk:
        kind, censor = "not_at_risk", ""
    elif up is not None:
        kind, censor = t["kind"], ""
    else:
        kind = "censored"
        if administrative and t["lower"] == horizon:
            censor = "end_of_train"
        elif first_cap == horizon:
            censor = "no_followup"
        elif t["lower"] == horizon:
            censor = "end_of_archive"
        else:
            censor = t["how"]
            exit_date = ctx.dates[t["exit"]] if t["exit"] is not None else None
    width = (up - lo).days if up is not None and lo is not None else None
    return {
        f"at_risk_{d}": risk,
        f"outcome_{d}": kind,
        f"event_via_{d}": t["how"] if up is not None else "",
        f"censor_reason_{d}": censor,
        f"lower_date_{d}": iso(lo),
        f"upper_date_{d}": iso(up),
        f"lower_days_{d}": (lo - ev.date).days if lo is not None else None,
        f"upper_days_{d}": (up - ev.date).days if up is not None else None,
        f"width_days_{d}": width,
        f"observable31_{d}": width is not None and width <= OBSERVABLE_WIDTH_DAYS,
        f"disc_date_field_{d}": t["disc"] if kind == "discontinued" else "",
        f"exit_date_{d}": iso(exit_date),
    }


def date_discontinued_appears(ev: Event, ctx: Context, horizon: int) -> str:
    """First later capture at which the thread's shortage row carries a new Date Discontinued.

    Recorded for sensitivity only: on shortage rows the cell mostly repeats the Date of Update of a
    resolution and appears on products that stayed on the market, so it is not the competing event.
    """
    c = ctx.col
    first = ev.rows[0]
    first_cap = c["cap_idx"][first]
    for cap in ctx.thread_caps[ev.thread]:
        row = ctx.thread_rows[ev.thread][cap]
        new = c["date_discontinued"][row] != c["date_discontinued"][first]
        if first_cap < cap <= horizon and new and not pd.isna(c["dd"][row]):
            return iso(ctx.dates[cap])
    return ""


def followup_fields(ev: Event, ctx: Context, horizon: int) -> dict[str, Any]:
    """Facts about the event from later captures up to ``horizon`` (outcome information, so never
    in events). ``followup_end_date`` is the date of the horizon capture.

    A re-confirmation is a later row of the event whose Date of Update differs from the first
    row's. ``n_reconfirmations`` counts the distinct such dates. ``last_reconfirmed_date`` is the
    latest of them that is plausible (``plausible_stamp``); a date later than its own capture (a
    typing error in the source, such as the year 2201) still counts as a re-confirmation but is
    never used as a date, and ``n_reconfirm_dates_implausible`` says how many were set aside.
    """
    c = ctx.col
    first_cap = c["cap_idx"][ev.rows[0]]
    first_dou = c["dou"][ev.rows[0]]
    seen = [r for r in ev.rows if c["cap_idx"][r] <= horizon]
    stamps, implausible = set(), set()
    for r in seen[1:]:
        dou = c["dou"][r]
        if pd.isna(dou) or same_date(dou, first_dou):
            continue
        (stamps if plausible_stamp(dou, ctx.dates[c["cap_idx"][r]]) else implausible).add(dou)
    next_seen = ev.next_cap is not None and ev.next_cap <= horizon
    return {
        "n_reconfirmations": len(stamps) + len(implausible),
        "n_reconfirm_dates_implausible": len(implausible),
        "last_reconfirmed_date": iso(max(stamps)) if stamps else "",
        "run_last_seen_date": iso(ctx.dates[c["cap_idx"][seen[-1]]]),
        "next_event_id": ev.next_id if next_seen else "",
        "n_followup_captures": horizon - first_cap,
        "n_followup_listed": sum(
            1 for cap in ctx.thread_caps[ev.thread] if first_cap < cap <= horizon
        ),
        "date_discontinued_on_row_date": date_discontinued_appears(ev, ctx, horizon),
        "followup_end_date": iso(ctx.dates[horizon]),
    }


def outcome_record(ev: Event, ctx: Context, full: bool = False) -> dict[str, Any]:
    """Interval-censored outcome of one shortage-listing event under every definition. A train
    event is followed only to the last capture before TEST_START unless ``full``."""
    horizon = ctx.horizon(ev, full)
    risk = at_risk(ev, ctx)
    track = walk(ev, ctx, risk, horizon)
    rec: dict[str, Any] = {"event_id": ev.event_id, "event_date": iso(ev.date)}
    for d in DEFINITIONS:
        rec.update(bracket(d, risk[d], track[d], ev, ctx, horizon))
    rec.update(followup_fields(ev, ctx, horizon))
    return rec


def group_bracket(members: pd.DataFrame, d: str) -> dict[str, Any]:
    """Statement-level outcome from its presentation-level rows (see the module docstring)."""
    risk = members[members[f"at_risk_{d}"].astype(bool)]
    if risk.empty:
        kind, lo, up = "not_at_risk", "", ""
    else:
        live = risk[risk[f"outcome_{d}"] != "discontinued"]
        pool = risk if live.empty else live
        lo = pool[f"lower_date_{d}"].max()
        if live.empty:
            kind, up = "discontinued", pool[f"upper_date_{d}"].max()
        elif (live[f"outcome_{d}"] == "censored").any():
            kind, up = "censored", ""
        else:
            kind, up = "recovered", pool[f"upper_date_{d}"].max()
    date = pd.Timestamp(members["event_date"].iloc[0])
    lo_ts = pd.Timestamp(lo) if lo else None
    up_ts = pd.Timestamp(up) if up else None
    width = (up_ts - lo_ts).days if up_ts is not None and lo_ts is not None else None
    return {
        f"group_outcome_{d}": kind,
        f"group_lower_date_{d}": lo,
        f"group_upper_date_{d}": up,
        f"group_lower_days_{d}": (lo_ts - date).days if lo_ts is not None else None,
        f"group_upper_days_{d}": (up_ts - date).days if up_ts is not None else None,
        f"group_width_days_{d}": width,
        f"group_observable31_{d}": width is not None and width <= OBSERVABLE_WIDTH_DAYS,
    }


def add_group_outcomes(out: pd.DataFrame) -> pd.DataFrame:
    """Attach statement-level (statement_group_id) outcomes to every presentation-level row."""
    rows = []
    for gid, members in out.groupby("statement_group_id", sort=True):
        rec: dict[str, Any] = {"statement_group_id": gid, "group_n_presentations": len(members)}
        for d in DEFINITIONS:
            rec.update(group_bracket(members, d))
        rows.append(rec)
    return out.merge(pd.DataFrame(rows), on="statement_group_id", how="left", validate="m:1")


# ---------------------------------------------------------------------------
# Corpus assembly
# ---------------------------------------------------------------------------


@dataclass
class Corpus:
    events: pd.DataFrame
    outcomes: pd.DataFrame  # train censored at TEST_START; test followed to the archive's end
    captures: Captures
    train_uncensored: pd.DataFrame  # train followed to the archive's end: sealed, never read


def build_corpus(directory: Path) -> Corpus:
    """Parse every capture in ``directory`` and derive events and outcomes (all periods)."""
    caps = load_captures(directory)
    caps.obs["thread"] = link_threads(caps.obs)
    caps.obs["generic_id"] = link_generics(caps.obs)
    ctx = Context(caps)
    events = split_events(caps.obs)
    date_events(events, caps.obs)
    assign_ids(events, caps.obs)
    ev_rows, out_rows, full_rows = [], [], []
    for ev in events:
        record = event_record(ev, ctx)
        ev_rows.append(record)
        if record["listing"] == "shortage":
            extra = {k: record[k] for k in ("period", "statement_group_id")}
            out_rows.append({**outcome_record(ev, ctx), **extra})
            if record["period"] == "train":
                full_rows.append({**outcome_record(ev, ctx, full=True), **extra})
    ev_frame = pd.DataFrame(ev_rows, columns=list(EVENT_COLUMNS))
    ev_frame = ev_frame.sort_values(["event_date", "event_id"], ignore_index=True)
    return Corpus(ev_frame, outcome_frame(out_rows), caps, outcome_frame(full_rows))


def outcome_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if len(frame):
        frame = add_group_outcomes(frame)
        frame = frame.sort_values(["event_date", "event_id"], ignore_index=True)
    return frame


# ---------------------------------------------------------------------------
# Reporting (counts only) and writing
# ---------------------------------------------------------------------------


def cutoff_day(cutoff: Any) -> pd.Timestamp:
    """The last day of the month that holds ``cutoff``: a model's cutoff is a month, and an event
    is after it when it is dated after that month's last day."""
    return pd.Timestamp(cutoff).normalize() + pd.offsets.MonthEnd(0)


def gate_counts(corpus: Corpus, cutoff: Any = CUTOFF) -> dict[str, int]:
    """Gate 1 counts. Test outcomes enter only as counts of events with an observable outcome.

    The gate set is the shortage events dated TEST_START to GATE_END that are Current at
    statement and carry a date-like phrase. ``after_cutoff_observable31_X_*`` is the fourth
    threshold as the plan words it: the observable events (bracket of 31 days or less) of the gate
    set dated after the last day of the primary model's documented cutoff month (``cutoff`` is
    any day of that month, see ``cutoff_day``). ``_events`` counts presentation-level events
    with an observable bracket of their own; ``_distinct`` counts distinct statements whose
    statement-level bracket is observable. The ``after_cutoff_*with_followup`` counts are the
    weaker check used before it (events with any later capture that lists the thread), kept
    under their own names.
    """
    cutoff = cutoff_day(cutoff)
    ev = corpus.events
    date = pd.to_datetime(ev["event_date"])
    in_gate = (
        (ev["listing"] == "shortage")
        & (ev["status_at_statement"] == "current")
        & ev["has_date_like"].astype(bool)
        & (date >= TEST_START)
        & (date <= GATE_END)
    )
    gate, late = ev[in_gate], ev[in_gate & (date > cutoff)]
    out = corpus.outcomes.set_index("event_id")
    counts = {
        "statement_events": len(gate),
        "distinct_statements": gate["statement_group_id"].nunique(),
        "episodes": gate.loc[gate["episode_id"] != "", "episode_id"].nunique(),
    }
    for d in GATE_DEFINITIONS:
        observable = out.index[out[f"observable31_{d}"].astype(bool)]
        grouped = set(out.loc[out[f"group_observable31_{d}"].astype(bool), "statement_group_id"])
        for prefix, frame in (("", gate), ("after_cutoff_", late)):
            name = f"{prefix}observable31_{d}"
            counts[f"{name}_events"] = int(frame["event_id"].isin(observable).sum())
            in_frame = frame.loc[frame["statement_group_id"].isin(grouped), "statement_group_id"]
            counts[f"{name}_distinct"] = in_frame.nunique()
    followed = late[late["event_id"].isin(out.index[out["n_followup_listed"] > 0])]
    counts["after_cutoff_events"] = len(late)
    counts["after_cutoff_distinct"] = late["statement_group_id"].nunique()
    counts["after_cutoff_with_followup"] = len(followed)
    counts["after_cutoff_distinct_with_followup"] = followed["statement_group_id"].nunique()
    return counts


def gap_summary(dates: Sequence[pd.Timestamp]) -> dict[str, Any]:
    """Capture coverage: counts per year, gap distribution in days, and gaps over 60 days."""
    days = pd.Series(sorted(set(dates)))
    gaps = days.diff().dt.days.dropna()
    long = [f"{iso(days[i - 1])}..{iso(days[i])} ({int(g)} d)" for i, g in gaps.items() if g > 60]
    return {
        "captures": len(dates),
        "capture_days": len(days),
        "first": iso(days.iloc[0]),
        "last": iso(days.iloc[-1]),
        "per_year": {int(k): int(v) for k, v in days.dt.year.value_counts().sort_index().items()},
        "median_gap_days": float(gaps.median()) if len(gaps) else None,
        "share_gaps_le_31": round(float((gaps <= 31).mean()), 3) if len(gaps) else None,
        "gaps_over_60_days": long,
    }


def availability_strings(obs: pd.DataFrame) -> pd.DataFrame:
    """The author's check list: every distinct normalised Availability Information string that
    the rule classes available or limited, or classed so before the fix of 1 October 2026.

    Strings are printed as ``availability_key`` gives them. ``n_rows`` counts the capture rows
    that carry the string (rows kept by ``load_captures``, all captures, both listings). No
    other column is shown, no drug, company, date or outcome, so the check reveals no
    statement's outcome. Rows are sorted by class after the fix (available, limited, then
    other: what the fix or the rejection list moved out), by ``n_rows`` descending, then by
    string.
    """
    groups = obs.groupby("avail_key", sort=False)
    frame = pd.DataFrame(
        {
            "class_after_fix": groups["avail_class"].first(),
            "class_before_fix": groups["availability"].first().map(availability_class_before_fix),
            "n_rows": groups.size(),
        }
    )
    frame = frame.rename_axis("string").reset_index()[list(STRING_COLUMNS)]
    supply = frame[["class_after_fix", "class_before_fix"]].isin(SUPPLY_CLASSES).any(axis=1)
    frame = frame[supply]
    rank = {name: k for k, name in enumerate(SUPPLY_CLASSES)}
    keys = frame.assign(
        rank=frame["class_after_fix"].map(rank).fillna(len(rank)), fewer=-frame["n_rows"]
    )
    order = keys.sort_values(["rank", "fewer", "string"]).index
    return frame.loc[order].reset_index(drop=True)


def write_availability_strings(captures: Path = CAPTURES_DIR, path: Path = STRINGS_PATH) -> int:
    """Write the check list (``availability_strings``) as a plain CSV; returns its row count.

    Only the captures are read: no thread, event or outcome is derived and nothing is sealed. A
    file at ``path`` whose header is not exactly the four columns (the author's marks added in a
    further column, say) is not overwritten.
    """
    header = ",".join(STRING_COLUMNS)
    if path.exists() and path.read_text(encoding="utf-8").split("\n", 1)[0].strip() != header:
        raise SystemExit(f"{path} has other columns than {header}; move it away first")
    frame = availability_strings(load_captures(captures).obs)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
    return len(frame)


def verify_manifest(directory: Path, module: str = MANIFEST_MODULE) -> bool:
    """Check the capture folder against the frozen manifest, when the manifest module exists.

    Calls ``verify(directory)`` of ``module`` (``analysis/coling/manifest.py``), which is imported
    by name here so that this file runs without it. An error raised by ``verify`` stops the
    build, and so does a result of False or a non-empty list of differences. Returns True when
    the check ran and passed, and False when there is no such module (nothing was checked).
    """
    try:
        manifest = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name is not None and (module == exc.name or module.startswith(exc.name + ".")):
            return False
        raise
    found = manifest.verify(directory)
    if found is False or (isinstance(found, list | tuple) and len(found) > 0):
        raise SystemExit(f"{directory} does not match the capture manifest: {found}")
    return True


def unseen_rejections(obs: pd.DataFrame) -> list[str]:
    """Entries of ``REJECTED_AVAILABLE`` that no capture row carries. Such an entry rejects
    nothing (a mistyped copy of a check-list string, say), so ``main`` refuses to build with one.
    """
    seen = set(obs["avail_key"])
    return [text for text in REJECTED_AVAILABLE if text not in seen]


def write_gz(frame: pd.DataFrame, path: Path) -> str:
    """Write a gzip CSV with a fixed header time and return its sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression=GZIP, lineterminator="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_open_tables(corpus: Corpus, out: Path = OUT_DIR) -> dict[str, str]:
    """Write the two open tables, the events of every period (first-sight fields only) and the
    train outcomes followed to the train horizon, and return the sha256 of each file by name.

    Nothing sealed is written and no test-period outcome leaves memory.
    """
    train = corpus.outcomes[corpus.outcomes["period"] == "train"]
    return {
        "events.csv.gz": write_gz(corpus.events, out / "events.csv.gz"),
        "outcomes_train.csv.gz": write_gz(train, out / "outcomes_train.csv.gz"),
    }


def print_report(
    corpus: Corpus, gate: dict[str, int], gaps: dict[str, Any], cutoff: Any = CUTOFF
) -> None:
    """Counts only: captures, rows, threads, events, capture gaps and Gate 1. ``cutoff`` is the
    one given to ``gate_counts`` for ``gate``."""
    caps, ev = corpus.captures, corpus.events
    cutoff = cutoff_day(cutoff)
    print(f"captures read: {len(caps.stamps)}; skipped: {len(caps.skipped)}")
    for msg in caps.skipped:
        print(f"  skipped {msg}")
    repaired = int(caps.obs["row_repaired"].sum())
    print(
        f"rows kept: {len(caps.obs)}; dropped (duplicate or no status): {caps.n_dropped}; "
        f"realigned among those kept: {repaired}"
    )
    realigned = {stamp: n for stamp, n in caps.realigned.items() if n}
    print(
        f"realigned rows as read, per capture: {sum(realigned.values())} in {len(realigned)} of "
        f"{len(caps.realigned)} captures (none in the others)"
    )
    for stamp, n in realigned.items():
        print(f"  {stamp}: {n}")
    print(
        f"availability strings rejected by the author: {len(REJECTED_AVAILABLE)} "
        f"({len(unseen_rejections(caps.obs))} of them in no capture)"
    )
    print(
        f"threads: {caps.obs['thread'].nunique()}; generics: {caps.obs['generic_id'].nunique()}; "
        f"events: {len(ev)} (train {int((ev['period'] == 'train').sum())}, "
        f"test {int((ev['period'] == 'test').sum())})"
    )
    print("capture gaps:")
    for key, value in gaps.items():
        print(f"  {key}: {value}")
    t = GATE_THRESHOLDS
    print(
        f"Gate 1: shortage events dated {iso(TEST_START)}..{iso(GATE_END)}, Current at statement, "
        "with a date-like phrase"
    )
    print(
        f"  statement events {gate['statement_events']}; distinct statements "
        f"{gate['distinct_statements']} (need >= {t['statements']})"
    )
    for d in GATE_DEFINITIONS:
        print(
            f"  observable outcome (bracket <= {OBSERVABLE_WIDTH_DAYS} d), definition {d}: "
            f"presentation-level events {gate[f'observable31_{d}_events']}, distinct statements "
            f"{gate[f'observable31_{d}_distinct']} (need >= {t['observable']})"
        )
    print(f"  shortage episodes {gate['episodes']} (need >= {t['episodes']})")
    for d in GATE_DEFINITIONS:
        print(
            f"  dated after {iso(cutoff)}, observable outcome, definition {d}: presentation-level "
            f"events {gate[f'after_cutoff_observable31_{d}_events']}, distinct statements "
            f"{gate[f'after_cutoff_observable31_{d}_distinct']} (need >= {t['post_cutoff']})"
        )
    print(
        f"  dated after {iso(cutoff)}: events {gate['after_cutoff_events']}, distinct statements "
        f"{gate['after_cutoff_distinct']}; with follow-up {gate['after_cutoff_with_followup']}, "
        f"distinct with follow-up {gate['after_cutoff_distinct_with_followup']} (no threshold)"
    )


def open_build(
    captures: Path = CAPTURES_DIR,
    out: Path = OUT_DIR,
    cutoff: Any = CUTOFF,
    check: Callable[[Path], object] | None = verify_manifest,
) -> Corpus:
    """Build the corpus, write the two open tables and print the report; nothing is sealed.

    ``check`` is called on the capture folder before anything is read or written; it raises to
    stop the build and returns False when it could not check. The default verifies the capture
    manifest; ``None`` skips the check (synthetic captures in tests). The build also stops,
    before anything is written, when an entry of ``REJECTED_AVAILABLE`` is in no capture.
    """
    checked = check is not None and check(captures) is not False
    print(f"capture manifest: {'verified' if checked else 'NOT checked'}")
    corpus = build_corpus(captures)
    unseen = unseen_rejections(corpus.captures.obs)
    if unseen:
        raise SystemExit(f"REJECTED_AVAILABLE holds strings that are in no capture: {unseen}")
    open_sha = write_open_tables(corpus, out)
    print_report(corpus, gate_counts(corpus, cutoff), gap_summary(corpus.captures.dates), cutoff)
    for name, sha in open_sha.items():
        print(f"wrote {out / name} sha256 {sha}")
    return corpus


def main(
    argv: Iterable[str] | None = None,
    check: Callable[[Path], object] | None = verify_manifest,
) -> int:
    """Build the corpus and write every table, the sealed ones included: ``open_build``, then the
    test outcomes and the train outcomes with full follow-up under ``--sealed``."""
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.corpus")
    ap.add_argument("--captures", type=Path, default=CAPTURES_DIR)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--sealed", type=Path, default=Path("external_data/sealed"))
    ap.add_argument(
        "--cutoff",
        type=pd.Timestamp,
        default=CUTOFF,
        help="a day of the primary model's documented training-cutoff month (Gate 1)",
    )
    args = ap.parse_args(None if argv is None else list(argv))
    corpus = open_build(args.captures, args.out, args.cutoff, check)
    test = corpus.outcomes[corpus.outcomes["period"] == "test"]
    sealed_sha = write_gz(test, args.sealed / "outcomes_test.csv.gz")
    full_sha = write_gz(corpus.train_uncensored, args.sealed / "outcomes_train_uncensored.csv.gz")
    print(f"sealed {args.sealed / 'outcomes_test.csv.gz'} sha256 {sealed_sha}")
    print(f"sealed {args.sealed / 'outcomes_train_uncensored.csv.gz'} sha256 {full_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
