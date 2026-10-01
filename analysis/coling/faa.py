"""Parse FAA Command Center (ATCSCC) advisories and build the E6 statements.

An advisory page saved by ``faa_fetch.py`` becomes an :class:`Advisory`: number, UTC day, send
time, type, control element, stated period, and the estimative fields exactly as written
(``PROBABILITY OF EXTENSION: MEDIUM``; the ``POSSIBLE`` / ``PROBABLE`` / ``EXPECTED`` lines of the
operations plan). The tag-free text files of the 2024 design pilot parse the same way.

Three families of statements are built from the advisories, each at its first issuance:

- ``gs``: a ground stop's probability of extension. Advisories of one stop that repeat the same
  stated end are one statement.
- ``route``: a reroute's or flow-constrained area's probability of extension, built the same way
  from the valid-until time.
- ``plan``: a planned ground stop or delay programme in the operations plan
  (``AFTER 1900 -EWR GROUND STOP/DELAY PROGRAM POSSIBLE``), one statement per airport,
  initiative and window, at the first plan that carries the line.

Lead time is kept as a covariate: minutes from first issuance to the stated end (``gs``,
``route``) or to the stated start (``plan``).

Development and test months are separated here. Months after the last development month are
refused by every function that opens a saved page (``load_day``, ``load_months``,
``coverage_gaps``, and ``completeness`` for the list pages) unless the flag file written when the
E6 amendment is registered exists. Counting the saved files per day is allowed for every month
and opens no file.

``load_months`` also refuses a month that is not completely on disk (``coverage_gaps``): an
outcome such as "not issued" is read from the later advisories, so it must not rest on a file
that was never saved.

Usage::

    uv run python -m analysis.coling.faa --months 2026-04 2026-05
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import itertools
import re
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path("external_data/faa_atcscc/2026")
OUT = Path("analysis/coling/out/faa")
DEV_MONTHS = ("2026-04", "2026-05")  # provisional until the E6 amendment
TEST_MONTHS = ("2026-06", "2026-07", "2026-08", "2026-09")  # provisional
AMENDMENT_FLAG_NAME = "E6_AMENDMENT_REGISTERED"
AMENDMENT_FLAG = OUT / AMENDMENT_FLAG_NAME  # written by hand when the amendment is pushed

MAX_PERIOD = dt.timedelta(hours=48)  # no stop or programme states a longer period
GRACE_MINUTES = 0  # draft: a later advisory must start no later than the stated end
OPERATING_DAY_END_HOUR = 8  # draft: an "AFTER hhmm" plan window closes at the next 0800Z
LATE_PLAN_MINUTES = 60  # a plan sent this long after its own EVENT TIME is read from that time

# Spellings of one term, as the issuer writes them. The statement keeps the spelling as written.
TERM_FORMS = {"MED": "MEDIUM", "MOD": "MODERATE", "POSS": "POSSIBLE", "PROB": "PROBABLE"}
PLAN_TERMS = ("POSSIBLE", "PROBABLE", "EXPECTED", "LIKELY", "UNLIKELY", "ANTICIPATED")
# Identifiers that name a terminal area or a group of airports, not one airport.
AREA_CODES = frozenset(
    {
        "N90",
        "C90",
        "A80",
        "A90",
        "PCT",
        "SCT",
        "NCT",
        "I90",
        "D10",
        "D01",
        "D21",
        "M98",
        "S46",
        "S56",
        "P50",
        "P80",
        "L30",
        "T75",
        "F11",
        "Y90",
        "R90",
        "U90",
    }
)


def in_scope(element: str) -> bool:
    """False for a Canadian airport (CYYZ, CYVR, ...).

    NAV CANADA's programmes reach the database as hand-written advisories with titles of their
    own ("CYYZ GROUND DELAY PROGRAM", "VANCOUVER GDP CANCELLED"), so their chains cannot be
    linked reliably. Draft rule: they give no statement.
    """
    return not re.fullmatch(r"C[A-Z]{3}", element)


class TestMonthsLocked(RuntimeError):
    """A month after the development months was requested before the amendment flag exists."""

    __test__ = False  # not a pytest class


class IncompleteCoverage(RuntimeError):
    """A requested day is not fully on disk, so an outcome would rest on a missing file."""


# --------------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanLine:
    """One line of a PLANNED section of the operations plan, as written."""

    section: str  # "TERMINAL PLANNED", "EN ROUTE PLANNED", ...
    raw: str
    qualifier: str  # AFTER, UNTIL or RANGE
    time_text: str  # "1100", "16/0400", "1400-2159"
    element_text: str  # "IAD/DCA/BWI"
    airports: tuple[str, ...]  # ("IAD", "DCA", "BWI"); areas and free text are left out
    initiative_text: str  # "GROUND STOP/DELAY PROGRAM"
    initiatives: tuple[str, ...]  # ("gs", "gdp"); empty when not a ground stop or delay programme
    term: str | None  # "POSSIBLE", as written


@dataclass(frozen=True)
class Advisory:
    day: dt.date  # UTC day of the advisory number
    number: int
    facility: str  # "EWR/ZNY", "DCC", "FCAMU1"
    title: str  # "CDM GROUND STOP"
    kind: str  # see classify()
    sent: dt.datetime | None  # signature time, UTC
    element: str | None  # CTL ELEMENT, destination airport, or route key
    element_type: str | None  # APT, FCA, ...
    period: tuple[dt.datetime | None, dt.datetime | None]  # the stated window
    period_label: str  # the field the window came from
    prob_extension: str | None  # as written
    route_name: str | None
    tmi_id: str | None
    plan_lines: tuple[PlanLine, ...]
    text: str  # header and body as written

    @property
    def id(self) -> str:
        return f"{self.day:%Y%m%d}-{self.number:03d}"


@dataclass(frozen=True)
class Statement:
    """One estimate at its first issuance: the unit of E6."""

    sid: str
    family: str  # gs, route or plan
    term: str  # as written at first issuance
    element: str
    initiative: str  # "gs", "gdp", "gs/gdp" or "reroute"
    issued: dt.datetime
    window_start: dt.datetime | None
    window_end: dt.datetime | None
    lead_minutes: int | None
    sources: tuple[str, ...]  # advisory ids that carry the statement, first issuance first
    terms_seen: tuple[str, ...]  # every spelling in the chain, in order of appearance
    line: str  # the estimative line as written at first issuance
    key: str  # what later advisories are matched on (airport, or route key)
    episode: tuple[str, ...] = ()  # gs, route: ids of every advisory of the same stop or route
    episode_end: str = ""  # gs, route: "cancelled" or "lapsed"
    cancel_id: str = ""  # the cancellation that closed the episode, if any

    @property
    def term_norm(self) -> str:
        return TERM_FORMS.get(self.term, self.term)

    @property
    def stratum(self) -> str:
        return f"{self.family}:{self.term_norm}"

    @property
    def day(self) -> dt.date:
        return self.issued.date()


# --------------------------------------------------------------------------------------
# Page to text
# --------------------------------------------------------------------------------------

_HEADER_HTML = re.compile(r"<TH class=header[^>]*>(.*?)</TH>", re.S | re.I)
_PRE = re.compile(r"<PRE>(.*?)</PRE>", re.S | re.I)
_VALUE_AFTER = r"{label}:(?:&nbsp;|\s)*</P>\s*</TD>\s*<TD class=val>(.*?)</TD>"
_HEADER = re.compile(r"^ATCSCC ADVZY (\d+) (.+?) (\d\d)/(\d\d)/(\d{4})(?: (.*))?$")
_SIGNATURE = re.compile(r"^(\d\d)/(\d\d)/(\d\d) (\d\d):(\d\d)")
_EFFECTIVE = re.compile(r"^(\d{6})\s*-\s*(\d{6})$")


def _clean(fragment: str) -> str:
    return html.unescape(fragment).replace("\xa0", " ").replace("\r", "")


def page_to_text(raw: str) -> str:
    """The advisory as plain text, in the layout of the 2024 pilot files.

    The message body sits in a ``<PRE>`` block and may contain ``<`` and ``>`` (route strings),
    so tags are never stripped from it. Text that is not an advisory page is returned unchanged.
    """
    header = _HEADER_HTML.search(raw)
    body = _PRE.search(raw)
    if not header or not body:
        return raw.replace("\r", "")
    parts = [_clean(header.group(1)), "MESSAGE:", _clean(body.group(1))]
    for label in ("EFFECTIVE TIME", "SIGNATURE"):
        value = re.search(_VALUE_AFTER.format(label=label), raw, re.S | re.I)
        if value:
            parts += [label + ":", _clean(value.group(1)).strip()]
    return "\n".join(parts)


# --------------------------------------------------------------------------------------
# Advisory fields
# --------------------------------------------------------------------------------------


def classify(title: str) -> str:
    """Advisory type from the brief title.

    gs, gs_cnx, gdp_proposed, gdp, gdp_cnx, afp_proposed, afp, afp_cnx, ctop (and its variants):
    programmes run through collaborative decision making (CDM). gs_manual, gs_manual_cnx: ground
    stops written by hand, usually for some departure facilities only. A delay programme or its
    cancellation under a hand-written title is gdp or gdp_cnx. ops_plan, reroute, reroute_cnx,
    other.
    """
    t = " ".join(title.upper().split())
    if t == "OPERATIONS PLAN":
        return "ops_plan"
    if t.startswith("CDM "):
        rest = t[4:]
        proposed = rest.startswith("PROPOSED ")
        cancelled = bool(re.search(r"\b(CNX|CANCEL\w*)$", rest))
        if "GROUND STOP" in rest or re.match(r"GS\b", rest):
            base = "gs"
        elif "GROUND DELAY" in rest or re.search(r"\bGDP\b", rest):
            base = "gdp"
        elif "AIRSPACE FLOW" in rest or re.search(r"\bAFP\b", rest):
            base = "afp"
        elif "CTOP" in rest or "TRAJECTORY OPTIONS" in rest:
            base = "ctop"
        else:
            return "other"
        return base + ("_cnx" if cancelled else "_proposed" if proposed else "")
    # Any other title that names a ground stop is written by hand: "LGA GROUND STOP", "DFW GROUND
    # STOP (DVRSN EXEMPT)", "CDW GS EXTENSION", "LGA/JFK GROUND STOP CANCELLATION FOR DAL AND SUBS".
    if re.search(r"\bGROUND STOPS?\b|\bGS\b", t):
        return "gs_manual_cnx" if re.search(r"\b(CNX|CANCEL\w*)\b", t) else "gs_manual"
    # A delay programme or its cancellation under a hand-written title ("JVY GROUND DELAY PROGRAM
    # CANCELLATION", "VANCOUVER GDP CANCELLED"). A title that goes on (CORRECTION) is not one.
    written = re.search(r"\b(?:GROUND DELAY PROGRAMS?|GDPS?)( (?:CNX|CANCEL\w*))?$", t)
    if written:
        return "gdp_cnx" if written.group(1) else "gdp"
    if re.match(r"(ROUTE|FCA) (RQD|RMD|FYI|PLN)\b", t):
        return "reroute"
    if t.startswith("REROUTE CANCEL"):
        return "reroute_cnx"
    return "other"


def _near(reference: dt.datetime, day: int, hhmm: str) -> dt.datetime | None:
    """The time ``day/hhmm`` in the month that puts it closest to ``reference``."""
    hour, minute = int(hhmm[:2]), int(hhmm[2:])
    if hour == 24 and minute == 0:
        hour, extra = 0, dt.timedelta(days=1)
    else:
        extra = dt.timedelta(0)
    best = None
    for shift in (-1, 0, 1):
        month = reference.month - 1 + shift
        year, month = reference.year + month // 12, month % 12 + 1
        try:
            candidate = dt.datetime(year, month, day, hour, minute) + extra
        except ValueError:
            continue
        if best is None or abs(candidate - reference) < abs(best - reference):
            best = candidate
    return best


def _field(body: str, label: str) -> str | None:
    """Value of the first ``LABEL: value`` line; None when the field is absent."""
    found = re.search(rf"(?m)^\s*{label}:[ \t]*(.*)$", body)
    return found.group(1).strip() if found else None


_SLASH_PERIOD = re.compile(r"(\d\d)/(\d{4})Z?\s*-\s*(?:(\d\d)/)?(\d{4})?Z?")
_VALID_PERIOD = re.compile(r"(\d\d)(\d{4})\s+TO\s+(\d\d)(\d{4})")
_PERIOD_FIELDS = {
    "gs": ("GROUND STOP PERIOD",),
    "gs_cnx": ("GS CNX PERIOD",),
    "gdp": ("CUMULATIVE PROGRAM PERIOD",),
    "gdp_proposed": ("ANTICIPATED CUMULATIVE PROGRAM PERIOD",),
    "gdp_cnx": ("GDP CNX PERIOD",),
    "afp": ("CUMULATIVE PROGRAM PERIOD",),
    "afp_proposed": ("ANTICIPATED CUMULATIVE PROGRAM PERIOD",),
    "afp_cnx": ("AFP CNX PERIOD",),
    "gs_manual": ("EVENT TIME",),
    "gs_manual_cnx": ("EVENT TIME",),
    "ops_plan": ("EVENT TIME",),
    "reroute": ("VALID",),
}


def _period(kind: str, body: str, reference: dt.datetime):
    """The stated window of an advisory: (start, end, field name). Unreadable parts are None."""
    for label in _PERIOD_FIELDS.get(kind, ()):
        value = _field(body, label)
        if value is None:
            continue
        if label == "VALID":
            found = _VALID_PERIOD.search(value)
            if not found:
                return None, None, label
            d1, t1, d2, t2 = found.groups()
            start = _near(reference, int(d1), t1)
            return start, _near(start or reference, int(d2), t2), label
        found = _SLASH_PERIOD.search(value)
        if not found:
            return None, None, label
        d1, t1, d2, t2 = found.groups()
        start = _near(reference, int(d1), t1)
        end = None
        if t2 is not None and start is not None:
            end = _near(start, int(d2), t2) if d2 else _near(start, start.day, t2)
            if end is not None and not d2 and end < start:
                end += dt.timedelta(days=1)
            # a mistyped day ("25/0040 - 05/0200") would give a period of days: not readable
            if end is not None and not start <= end <= start + MAX_PERIOD:
                end = None
        return start, end, label
    return None, None, ""


_SECTION = re.compile(r"^([A-Z][A-Za-z0-9 /()&.,\-]*?):\s*$")
_LINE_TIME = re.compile(
    r"^(?:(AFTER|UNTIL)\s+((?:[0-9O]{2}/)?[0-9O]{4})Z?|([0-9O]{4})Z?\s*-\s*([0-9O]{4})Z?)\s*-\s*(.*)$"
)
_INITIATIVE = re.compile(
    r"\b(GROUND STOPS?\s*/\s*(?:GROUND )?DELAY PROGRAMS?|GROUND STOPS?\s*/\s*GDPS?|GS\s*/\s*GDPS?"
    r"|GROUND DELAY PROGRAMS?|DELAY PROGRAMS?|GROUND STOPS?|GDPS?|GS)\b"
)


def _initiatives(text: str) -> tuple[str, ...]:
    kinds = []
    if re.search(r"GROUND STOP|\bGS\b", text):
        kinds.append("gs")
    if re.search(r"DELAY PROGRAM|\bGDP", text):
        kinds.append("gdp")
    return tuple(kinds)


# The two-word names of the initiatives. A slip of one letter in one of the two words is read
# as the name ("GROUND STOO", "DELAY PROGRAOM"); the term itself is never corrected.
_INITIATIVE_PHRASES = (
    ("GROUND", "STOP"),
    ("GROUND", "STOPS"),
    ("GROUND", "DELAY"),
    ("DELAY", "PROGRAM"),
    ("DELAY", "PROGRAMS"),
)
# A word that negates the term it stands before: "NOT EXPECTED", "NO LONGER EXPECTED".
_NEGATIONS = (("NO", "LONGER"), ("NOT",), ("NEVER",))


def _one_slip(word: str, target: str) -> bool:
    """Whether ``word`` is ``target`` with one letter added, dropped, changed or swapped."""
    if word == target or abs(len(word) - len(target)) > 1:
        return False
    start = 0
    while start < min(len(word), len(target)) and word[start] == target[start]:
        start += 1
    a, b = word[start:], target[start:]
    return (
        a[1:] == b[1:]  # one letter changed
        or a[1:] == b  # one letter added
        or a == b[1:]  # one letter dropped
        or (len(a) > 1 and len(b) > 1 and a[0] == b[1] and a[1] == b[0] and a[2:] == b[2:])
    )


def _respell(stem: str) -> str:
    """The stem with a one-letter slip in an initiative's name put right."""
    parts = re.split(r"(\s+|/)", stem)
    words = [i for i, part in enumerate(parts) if part.strip() and part != "/"]
    for i, j in itertools.pairwise(words):
        if (parts[i], parts[j]) in _INITIATIVE_PHRASES:
            continue
        for first, second in _INITIATIVE_PHRASES:
            if (parts[i] == first and _one_slip(parts[j], second)) or (
                parts[j] == second and len(parts[i]) > 4 and _one_slip(parts[i], first)
            ):
                parts[i], parts[j] = first, second
                break
    return "".join(parts)


def parse_plan_line(section: str, line: str, element: str = "") -> PlanLine | None:
    """One timed line of a PLANNED section; None for NONE, free text or untimed lines.

    ``element`` is the element the line is about when the line itself names none (the second
    half of "DEN GROUND DELAY PROGRAM EXPECTED, GROUND STOP POSSIBLE").
    """
    found = _LINE_TIME.match(" ".join(line.split()))
    if not found:
        return None
    word, when, range_start, range_end, rest = found.groups()
    if word:
        qualifier, time_text = word, when.replace("O", "0")
    else:
        qualifier, time_text = "RANGE", f"{range_start}-{range_end}".replace("O", "0")
    rest = rest.strip()
    words = rest.rstrip(" .,").split()
    term = words[-1] if words and words[-1] in PLAN_TERMS + tuple(TERM_FORMS) else None
    if term:
        words = words[:-1]
        # A negated term is a term of its own, as written: never the term it negates.
        for negation in _NEGATIONS:
            if tuple(words[-len(negation) :]) == negation:
                words = words[: -len(negation)]
                term = " ".join((*negation, term))
                break
    stem = _respell(" ".join(words)) if term else rest
    initiative = _INITIATIVE.search(stem)
    if initiative and element and not stem[: initiative.start()].strip():
        stem = f"{element} {stem}"
        initiative = _INITIATIVE.search(stem)
    if initiative:
        element_text = stem[: initiative.start()].strip()
        initiative_text = stem[initiative.start() :].strip()
        initiatives = _initiatives(initiative_text)
    else:
        element_text, initiative_text, initiatives = stem, "", ()
    # Areas and free text ("N90", "NY METS", "EWR SATS") name no single airport and are left out.
    airports = tuple(
        code
        for code in (part.strip() for part in element_text.split("/"))
        if re.fullmatch(r"[A-Z]{3,4}", code)
        and code not in AREA_CODES
        and not re.fullmatch(r"Z[A-Z]{2}", code)  # an en-route centre
    )
    return PlanLine(
        section, line.strip(), qualifier, time_text, element_text, airports, initiative_text,
        initiatives, term,
    )  # fmt: skip


def _ends_with_term(text: str) -> bool:
    words = text.rstrip(" .,").split()
    return bool(words) and words[-1] in PLAN_TERMS + tuple(TERM_FORMS)


def parse_plan_entry(section: str, entry: str) -> list[PlanLine]:
    """The plan lines one timed entry holds: one, or one per estimate when it states several.

    "AFTER 2200 -DEN GROUND DELAY PROGRAM EXPECTED, GROUND STOP POSSIBLE" is two estimates
    with one time; the second is about the element of the first unless it names its own. Each
    keeps the whole entry as ``raw``.
    """
    found = _LINE_TIME.match(" ".join(entry.split()))
    if not found:
        return []
    rest = found.group(5)
    clauses = [clause.strip() for clause in rest.split(",")]
    if len(clauses) < 2 or not all(_ends_with_term(clause) for clause in clauses):
        line = parse_plan_line(section, entry)
        return [line] if line else []
    prefix = " ".join(entry.split())[: found.start(5)]
    lines: list[PlanLine] = []
    for clause in clauses:
        element = lines[-1].element_text if lines else ""
        line = parse_plan_line(section, prefix + clause, element)
        if line:
            lines.append(replace(line, raw=entry))
    return lines


def parse_plan_lines(body: str) -> tuple[PlanLine, ...]:
    """Every timed line under a section whose name contains PLANNED (launches excepted).

    A line that is not timed and follows a timed one is the rest of a line the issuer wrapped
    ("... ORD/MDW GROUND" / "STOPS POSSIBLE"); the two are read as one.
    """
    entries: list[tuple[str, str]] = []
    section = None
    open_entry = False
    for raw in body.splitlines():
        text = raw.strip()
        if not text:
            section, open_entry = None, False
            continue
        header = _SECTION.match(text)
        if header and not _LINE_TIME.match(text):
            name = header.group(1)
            section = name if "PLANNED" in name and "LAUNCH" not in name else None
            open_entry = False
            continue
        if not section:
            continue
        if _LINE_TIME.match(" ".join(text.split())):
            entries.append((section, text))
            open_entry = True
        elif open_entry and text != "NONE":
            entries[-1] = (section, f"{entries[-1][1]} {text}")
    return tuple(line for section, entry in entries for line in parse_plan_entry(section, entry))


def parse_advisory(text: str, day: dt.date | None = None, number: int | None = None) -> Advisory:
    """Typed record from an advisory page (HTML as served) or a tag-free pilot text file.

    ``day`` and ``number`` are the day and number the database lists the advisory under. They
    replace the header's when given: an advisory sent at 0000Z can carry the previous day's date
    in its header, which would give two advisories one id.
    """
    lines = [line.strip() for line in page_to_text(text).splitlines()]
    start = next((i for i, line in enumerate(lines) if _HEADER.match(line)), None)
    if start is None:
        raise ValueError("no 'ATCSCC ADVZY' header line")
    header_number, facility, month, header_day, year, title = _HEADER.match(lines[start]).groups()
    title = (title or "").strip()
    kind = classify(title)
    date = day or dt.date(int(year), int(month), int(header_day))

    body_lines: list[str] = []
    sent = None
    rest = lines[start + 1 :]
    index = 0
    while index < len(rest):
        line = rest[index]
        if line.startswith("<input") or "Back to Results" in line:
            break
        if line in ("EFFECTIVE TIME:", "SIGNATURE:"):
            index += 1
            while index < len(rest) and not rest[index]:
                index += 1
            value = rest[index] if index < len(rest) else ""
            if line == "SIGNATURE:" and _SIGNATURE.match(value):
                sent = _signature(value)
            if _SIGNATURE.match(value) or _EFFECTIVE.match(value):
                index += 1
            continue
        if line in ("MESSAGE:", "RAW TEXT:") and not body_lines:
            index += 1
            continue
        body_lines.append(line)
        index += 1
    while body_lines and not body_lines[-1]:
        body_lines.pop()
    # Operations plans carry the effective time and the signature as their last two lines.
    if sent is None and body_lines and _SIGNATURE.match(body_lines[-1]):
        sent = _signature(body_lines.pop())
        if body_lines and _EFFECTIVE.match(body_lines[-1]):
            body_lines.pop()
    body = "\n".join(body_lines).strip("\n")
    reference = sent or dt.datetime.combine(date, dt.time(12, 0))
    # A cancellation relayed under the programme's own title: no programme period, only the
    # cancellation's.
    if (
        kind in ("gs", "gdp", "afp")
        and _field(body, _PERIOD_FIELDS[kind][0]) is None
        and _field(body, _PERIOD_FIELDS[kind + "_cnx"][0]) is not None
    ):
        kind += "_cnx"

    period_start, period_end, label = _period(kind, body, reference)
    element = _field(body, "CTL ELEMENT") or _field(body, "DESTINATION AIRPORTS?")
    route_name = _field(body, "NAME") if kind == "reroute" else None
    tmi_id = _field(body, "TMI ID") if kind == "reroute" else None
    if kind == "reroute":
        element = route_name
    elif kind == "reroute_cnx":
        cancelled = re.search(r"(?m)^(\S+) HAS BEEN CANCELL?ED", body)
        route_name = element = cancelled.group(1) if cancelled else None
    elif element is None and "/" in facility:
        element = facility.split("/")[0]
    return Advisory(
        day=date,
        number=int(header_number) if number is None else number,
        facility=facility,
        title=title,
        kind=kind,
        sent=sent,
        element=element,
        element_type=_field(body, "ELEMENT TYPE"),
        period=(period_start, period_end),
        period_label=label,
        prob_extension=_field(body, "PROBABILITY OF EXTENSION") or None,
        route_name=route_name,
        tmi_id=tmi_id,
        plan_lines=parse_plan_lines(body) if kind == "ops_plan" else (),
        text=lines[start] + "\n" + body,
    )


def _signature(value: str) -> dt.datetime:
    yy, mm, dd, hour, minute = (int(x) for x in _SIGNATURE.match(value).groups())
    return dt.datetime(2000 + yy, mm, dd, hour, minute)


# --------------------------------------------------------------------------------------
# Loading, with the development / test separation
# --------------------------------------------------------------------------------------


_MONTH = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])")


def is_locked(month: str) -> bool:
    """Whether a month (``YYYY-MM``, exactly) lies after the last development month.

    Any other spelling is refused: ``2026-006`` or `` 2026-06`` would sort before ``2026-05``
    as text and still be read as June.
    """
    if not isinstance(month, str) or not _MONTH.fullmatch(month):
        raise ValueError(f"month {month!r} is not written YYYY-MM")
    return month > max(DEV_MONTHS)


def amendment_registered(flag: Path | None = None) -> bool:
    """Whether the flag file written when the E6 amendment is pushed exists.

    The file is ``AMENDMENT_FLAG``. Another folder may hold it (the tests use a temporary one),
    but it must be a regular file of that name: no other existing path opens the test months.
    """
    flag = AMENDMENT_FLAG if flag is None else Path(flag)
    return flag.name == AMENDMENT_FLAG_NAME and flag.is_file()


def check_months(months, flag: Path | None = None) -> None:
    """Refuse any month after the development months unless the amendment flag file exists."""
    if isinstance(months, str):
        raise ValueError("months must be a list of YYYY-MM strings, not one string")
    locked = sorted(m for m in months if is_locked(m))
    if locked and not amendment_registered(flag):
        raise TestMonthsLocked(
            f"{', '.join(locked)}: months after {max(DEV_MONTHS)} may not be parsed or linked "
            f"before the E6 amendment is registered "
            f"({AMENDMENT_FLAG if flag is None else flag} is not there)"
        )


def _month(day: dt.date) -> str:
    return f"{day:%Y-%m}"


def month_days(month: str) -> list[dt.date]:
    is_locked(month)  # refuses any spelling but YYYY-MM
    year, number = (int(x) for x in month.split("-"))
    first = dt.date(year, number, 1)
    following = dt.date(year + number // 12, number % 12 + 1, 1)
    return [first + dt.timedelta(days=i) for i in range((following - first).days)]


def _saved_numbers(folder: Path) -> set[int]:
    return {int(path.stem.split("_")[1]) for path in folder.glob("adv_*.html")}


def load_day(root: Path, day: dt.date, flag: Path | None = None) -> list[Advisory]:
    """Every advisory saved for one day. A page that is not an advisory is skipped with a warning.

    A day after the development months is refused like its month (``check_months``).
    """
    check_months([_month(day)], flag)
    advisories = []
    for path in sorted((root / f"{day:%Y%m%d}").glob("adv_*.html")):
        number = int(path.stem.split("_")[1])
        try:
            advisories.append(parse_advisory(path.read_text(encoding="latin-1"), day, number))
        except ValueError as error:
            warnings.warn(f"{path}: not parsed ({error})", stacklevel=2)
    return advisories


def coverage_gaps(root: Path, days, flag: Path | None = None) -> list[str]:
    """What is missing on disk for the given days, one line per day; empty when nothing is.

    A day is covered when its list page is saved and every advisory the page names is saved
    too. "Not extended" and "not issued" are read from what the later advisories say, so a
    day that is not covered would turn a missing file into an outcome.
    """
    from analysis.coling.faa_fetch import advisory_numbers

    days = list(days)
    check_months({_month(day) for day in days}, flag)
    gaps = []
    for day in days:
        folder = root / f"{day:%Y%m%d}"
        list_page = folder / "list.html"
        if not list_page.is_file():
            gaps.append(f"{day:%Y-%m-%d}: no list page")
            continue
        missing = set(advisory_numbers(list_page.read_bytes(), day)) - _saved_numbers(folder)
        if missing:
            gaps.append(f"{day:%Y-%m-%d}: {len(missing)} listed advisories not saved")
    return gaps


def load_months(
    root: Path,
    months,
    flag: Path | None = None,
    lead_in: bool = True,
    complete: bool = True,
):
    """Advisories of the requested months, in send order, and the first instant after them.

    The day before the first month is loaded as context when it is on disk (it lets a plan line
    see a programme that was already running), but no statement is built from it.

    With ``complete`` (the default) every day of the requested months must be covered
    (``coverage_gaps``) and every saved page must parse; otherwise ``IncompleteCoverage`` is
    raised and nothing is returned. The lead-in day is not held to that.
    """
    if isinstance(months, str):
        raise ValueError("months must be a list of YYYY-MM strings, not one string")
    months = sorted(set(months))
    check_months(months, flag)
    days = [day for month in months for day in month_days(month)]
    gaps = coverage_gaps(root, days, flag) if complete else []
    advisories = []
    for day in days:
        loaded = load_day(root, day, flag)
        unread = len(_saved_numbers(root / f"{day:%Y%m%d}")) - len(loaded)
        if complete and unread:
            gaps.append(f"{day:%Y-%m-%d}: {unread} saved pages not parsed")
        advisories += loaded
    if gaps:
        raise IncompleteCoverage(
            f"{len(gaps)} gaps in {' '.join(months)} under {root}: " + "; ".join(sorted(gaps)[:10])
        )
    if lead_in:
        advisories += load_day(root, days[0] - dt.timedelta(days=1), flag)
    advisories.sort(
        key=lambda a: (a.sent or dt.datetime.combine(a.day, dt.time()), a.day, a.number)
    )
    last = days[-1] + dt.timedelta(days=1)
    return advisories, dt.datetime.combine(last, dt.time())


def completeness(root: Path, flag: Path | None = None) -> list[dict]:
    """Per day folder: advisories saved, advisories the day's list page names, and those missing.

    Reads advisory numbers from the list page and opens no advisory. The list page of a day
    after the development months is not opened before the amendment flag exists: such a day
    gets its count of saved files only, which reads no file. ``listed`` and ``missing`` are
    also empty when the list page is not on disk.
    """
    from analysis.coling.faa_fetch import advisory_numbers

    unlocked = amendment_registered(flag)
    rows = []
    for folder in sorted(root.iterdir()):
        if not (folder.is_dir() and re.fullmatch(r"[0-9]{8}", folder.name)):
            continue
        saved = _saved_numbers(folder)
        row = {"day": folder.name, "advisories": len(saved), "listed": "", "missing": ""}
        list_page = folder / "list.html"
        try:
            day = dt.datetime.strptime(folder.name, "%Y%m%d").date()
        except ValueError:
            day = None  # eight digits that are not a date: counted, never opened
        if day is not None and (unlocked or not is_locked(_month(day))) and list_page.exists():
            numbers = advisory_numbers(list_page.read_bytes(), day)
            row.update(listed=len(numbers), missing=len(set(numbers) - saved))
        rows.append(row)
    return rows


def raw_counts(root: Path) -> dict[str, int]:
    """Saved advisory files per day folder. Reads no file, so every month is allowed."""
    return {
        folder.name: sum(1 for _ in folder.glob("adv_*.html"))
        for folder in sorted(root.iterdir())
        if folder.is_dir() and re.fullmatch(r"\d{8}", folder.name)
    }


# --------------------------------------------------------------------------------------
# Statements
# --------------------------------------------------------------------------------------


def _minutes(delta: dt.timedelta) -> int:
    return round(delta.total_seconds() / 60)


def _order(advisory: Advisory):
    """Send order; advisories sent in the same minute are ordered by day and number."""
    return (advisory.sent, advisory.day, advisory.number)


def episodes(items: list[Advisory], cancels: list[Advisory], grace: int = GRACE_MINUTES, same=None):
    """Split one element's advisories (send order) into stops or routes that ran without a break.

    An advisory continues the one before it unless a cancellation was sent between the two, its
    stated start is more than ``grace`` minutes after the earlier stated end, or ``same`` (a
    test on the two advisories, used for routes) says they are different things. Returns a list
    of (advisories, how the episode ended, cancellation or None). The ending is "cancelled" when
    a cancellation followed the last advisory no later than ``grace`` minutes after its stated
    end, and "lapsed" otherwise (a cancellation sent after the stated end closes nothing: the
    stop had already run out).
    """
    out: list[tuple[list[Advisory], str, Advisory | None]] = []
    current: list[Advisory] = []
    pending = sorted(cancels, key=_order)

    def limit(advisory: Advisory) -> dt.datetime:
        return (advisory.period[1] or advisory.sent) + dt.timedelta(minutes=grace)

    def cancelled(previous: Advisory, following: Advisory | None) -> Advisory | None:
        """The first cancellation sent after ``previous`` and before ``following``."""
        for cancel in pending:
            if _order(cancel) > _order(previous) and (
                following is None or _order(cancel) < _order(following)
            ):
                return cancel
        return None

    def close(cancel: Advisory | None) -> None:
        if cancel is not None and cancel.sent <= limit(current[-1]):
            out.append((list(current), "cancelled", cancel))
        else:
            out.append((list(current), "lapsed", None))
        current.clear()

    for item in items:
        if current:
            previous = current[-1]
            cancel = cancelled(previous, item)
            late = (item.period[0] or item.sent) > limit(previous)
            if cancel is not None or late or (same and not same(previous, item)):
                close(cancel)
        current.append(item)
    if current:
        close(cancelled(current[-1], None))
    return out


def _extension_statements(family, key, items, cancels, grace, same=None) -> list[Statement]:
    statements = []
    for members, ending, cancel in episodes(items, cancels, grace, same):
        ids = tuple(a.id for a in members)
        index = 0
        while index < len(members):
            chain = [members[index]]
            while (
                index + len(chain) < len(members)
                and members[index + len(chain)].period[1] == chain[0].period[1]
            ):
                chain.append(members[index + len(chain)])
            index += len(chain)
            stated = [a for a in chain if a.prob_extension]
            if not stated or chain[0].period[1] is None:
                continue
            first = stated[0]
            terms = tuple(dict.fromkeys(a.prob_extension for a in stated))
            statements.append(
                Statement(
                    sid=f"{family}-{first.id}",
                    family=family,
                    term=first.prob_extension,
                    element=first.element or key,
                    initiative="gs" if family == "gs" else "reroute",
                    issued=first.sent,
                    window_start=first.period[0],
                    window_end=first.period[1],
                    lead_minutes=_minutes(first.period[1] - first.sent),
                    sources=tuple(a.id for a in chain),
                    terms_seen=terms,
                    line=f"PROBABILITY OF EXTENSION: {first.prob_extension}",
                    key=key,
                    episode=ids,
                    episode_end=ending,
                    cancel_id=cancel.id if cancel else "",
                )
            )
    return statements


def gs_statements(advisories: list[Advisory], grace: int = GRACE_MINUTES) -> list[Statement]:
    """Ground-stop extension statements: one per stop and stated end, at first issuance."""
    stops, cancels = defaultdict(list), defaultdict(list)
    for a in advisories:
        if a.sent is None or not a.element or not in_scope(a.element):
            continue
        if a.kind == "gs":
            stops[a.element].append(a)
        elif a.kind == "gs_cnx":
            cancels[a.element].append(a)
    out = []
    for element in sorted(stops):
        out += _extension_statements("gs", element, stops[element], cancels[element], grace)
    return out


def route_key(advisory: Advisory) -> str:
    """What ties the advisories of one reroute together: the TMI ID, else the route name.

    A replacement keeps the TMI ID even when the name changes (WATRS, then WATRS_PARTIAL).
    """
    return advisory.tmi_id or advisory.route_name or ""


def same_route(earlier: Advisory, later: Advisory) -> bool:
    """Whether two advisories with one TMI ID are the same reroute.

    TMI IDs are reused from day to day, so the name must also match (one name may extend the
    other: WATRS, WATRS_PARTIAL), or the later advisory must say that it replaces the earlier.
    """
    a, b = earlier.route_name or "", later.route_name or ""
    if a and b and (a.startswith(b) or b.startswith(a)):
        return True
    return bool(re.search(rf"REPLACES ADVZY\s*0*{earlier.number}\b", later.text))


def route_statements(advisories: list[Advisory], grace: int = GRACE_MINUTES) -> list[Statement]:
    """Reroute and flow-constrained-area extension statements, built like the ground-stop ones.

    A cancellation names the route; it is attached to the latest earlier advisory of that name.
    """
    routes, cancels = defaultdict(list), defaultdict(list)
    latest_by_name: dict[str, Advisory] = {}
    for a in advisories:
        if a.sent is None:
            continue
        if a.kind == "reroute" and route_key(a):
            routes[route_key(a)].append(a)
            if a.route_name:
                latest_by_name[a.route_name] = a
        elif a.kind == "reroute_cnx" and a.route_name in latest_by_name:
            cancels[route_key(latest_by_name[a.route_name])].append(a)
    out = []
    for key in sorted(routes):
        out += _extension_statements("route", key, routes[key], cancels[key], grace, same_route)
    return out


def _clock(reference: dt.datetime, hhmm: str) -> dt.datetime:
    """First time the clock reads ``hhmm`` at or after ``reference``."""
    candidate = reference.replace(hour=int(hhmm[:2]) % 24, minute=int(hhmm[2:]), second=0)
    return candidate if candidate >= reference else candidate + dt.timedelta(days=1)


def plan_window(
    line: PlanLine,
    issued: dt.datetime,
    day_end_hour: int = OPERATING_DAY_END_HOUR,
    event_start: dt.datetime | None = None,
):
    """The window a plan line states, read at its first issuance: (start, end).

    - ``UNTIL hhmm``: from the issuance to the next time the clock reads hhmm.
    - ``AFTER hhmm``: from the next hhmm to the end of the operating day, the next
      ``day_end_hour``:00Z after the start. "Next" counts from the issuance, or from the start of
      the plan's own period (``event_start``, its EVENT TIME) when the plan was sent up to
      ``LATE_PLAN_MINUTES`` after it: a plan for 1600Z sent at 1620Z means today's 1600Z by
      "AFTER 1600". A plan sent at 2327Z for the next day means the next day's 2300Z by
      "AFTER 2300".
    - ``hhmm-hhmm``: that range. A day written with the time (``16/0400``) is used as written.
    """
    text = line.time_text
    if line.qualifier == "RANGE":
        first, second = text.split("-")
        start = _clock(issued, first)
        running = start - dt.timedelta(days=1)  # the same range, if it is already under way
        if _clock(running, second) > issued:
            start = running
        return start, _clock(start, second)
    if "/" in text:
        day, hhmm = text.split("/")
        moment = _near(issued, int(day), hhmm)
    elif line.qualifier == "UNTIL":
        moment = _clock(issued, text)
    else:
        late = dt.timedelta(minutes=LATE_PLAN_MINUTES)
        on_time = event_start is None or not issued - late <= event_start < issued
        moment = _clock(issued if on_time else event_start, text)
    if line.qualifier == "UNTIL":
        return issued, moment
    end = _clock(moment + dt.timedelta(minutes=1), f"{day_end_hour:02d}00")
    return moment, end


def plan_statements(
    advisories: list[Advisory], day_end_hour: int = OPERATING_DAY_END_HOUR
) -> list[Statement]:
    """Planned ground stops and delay programmes, one statement per (airport, initiative, window).

    A line repeated in the next operations plan with the same airport, initiative and window text
    belongs to the same chain; the statement is the chain's first issuance. A line that drops out
    of one plan and returns later starts a new chain.
    """
    plans = [a for a in advisories if a.kind == "ops_plan" and a.sent is not None]
    open_chains: dict[tuple, dict] = {}
    chains: list[dict] = []
    for plan in plans:
        seen: dict[tuple, dict] = {}
        for line in plan.plan_lines:
            if line.section != "TERMINAL PLANNED" or not line.initiatives or not line.term:
                continue
            for airport in line.airports:
                key = (airport, line.initiatives, line.qualifier, line.time_text)
                if key in seen or not in_scope(airport):
                    continue
                chain = open_chains.get(key)
                if chain is None:
                    chain = {"key": key, "line": line, "first": plan, "plans": [], "terms": []}
                    chains.append(chain)
                chain["plans"].append(plan.id)
                chain["terms"].append(line.term)
                seen[key] = chain
        open_chains = seen
    statements = []
    for chain in chains:
        airport, initiatives, qualifier, time_text = chain["key"]
        line, first = chain["line"], chain["first"]
        start, end = plan_window(line, first.sent, day_end_hour, first.period[0])
        initiative = "/".join(initiatives)
        statements.append(
            Statement(
                sid=f"plan-{first.id}-{airport}-{initiative.replace('/', '+')}-{qualifier}"
                f"{time_text.replace('/', '.')}",
                family="plan",
                term=line.term,
                element=airport,
                initiative=initiative,
                issued=first.sent,
                window_start=start,
                window_end=end,
                lead_minutes=_minutes(start - first.sent),
                sources=tuple(chain["plans"]),
                terms_seen=tuple(dict.fromkeys(chain["terms"])),
                line=line.raw,
                key=airport,
            )
        )
    return statements


def build_statements(
    advisories: list[Advisory],
    months,
    grace: int = GRACE_MINUTES,
    day_end_hour: int = OPERATING_DAY_END_HOUR,
):
    """All three families, restricted to statements first issued in the requested months."""
    wanted = set(months)
    statements = (
        gs_statements(advisories, grace)
        + route_statements(advisories, grace)
        + plan_statements(advisories, day_end_hour)
    )
    statements = [s for s in statements if _month(s.issued.date()) in wanted]
    return sorted(statements, key=lambda s: s.sid)


# --------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------

STATEMENT_COLUMNS = (
    "sid", "family", "term", "term_norm", "element", "initiative", "issued", "window_start",
    "window_end", "lead_minutes", "n_sources", "sources", "terms_seen", "line",
)  # fmt: skip


def statement_row(s: Statement) -> dict:
    return {
        "sid": s.sid,
        "family": s.family,
        "term": s.term,
        "term_norm": s.term_norm,
        "element": s.element,
        "initiative": s.initiative,
        "issued": f"{s.issued:%Y-%m-%dT%H:%MZ}",
        "window_start": f"{s.window_start:%Y-%m-%dT%H:%MZ}" if s.window_start else "",
        "window_end": f"{s.window_end:%Y-%m-%dT%H:%MZ}" if s.window_end else "",
        "lead_minutes": "" if s.lead_minutes is None else s.lead_minutes,
        "n_sources": len(s.sources),
        "sources": " ".join(s.sources),
        "terms_seen": " ".join(s.terms_seen),
        "line": s.line,
    }


def write_csv(path: Path, columns, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def table_name(months, name: str | None) -> str:
    """Suffix of the output tables: ``dev`` for development months only, and for nothing else."""
    development = set(months) <= set(DEV_MONTHS)
    if name is None and not development:
        raise ValueError("--name is needed for months other than the development months")
    if name == "dev" and not development:
        raise ValueError("the tables named 'dev' hold development months only")
    return name or "dev"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.faa")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--months", nargs="+", default=list(DEV_MONTHS))
    ap.add_argument("--name", help="suffix of the output tables (default: dev)")
    args = ap.parse_args(argv)
    check_months(args.months)  # before anything is read or written
    name = table_name(args.months, args.name)

    days = completeness(args.root)
    write_csv(args.out / "raw_counts_per_day.csv", ("day", "advisories", "listed", "missing"), days)
    checked = [row for row in days if row["listed"] != ""]
    incomplete = [row["day"] for row in checked if row["missing"] != 0]
    print(
        f"raw files: {sum(row['advisories'] for row in days)} advisories in {len(days)} day "
        f"folders; {len(checked)} folders compared with their list page, {len(incomplete)} of "
        f"them incomplete"
        + (
            f" ({', '.join(incomplete[:5])}{', ...' if len(incomplete) > 5 else ''})"
            if incomplete
            else ""
        )
    )

    advisories, _ = load_months(args.root, args.months)
    statements = build_statements(advisories, args.months)
    write_csv(
        args.out / f"statements_{name}.csv",
        STATEMENT_COLUMNS,
        (statement_row(s) for s in statements),
    )
    in_months = [a for a in advisories if _month(a.day) in set(args.months)]
    print(f"months {' '.join(sorted(args.months))}: {len(in_months)} advisories parsed")
    for kind, n in sorted(Counter(a.kind for a in in_months).items(), key=lambda kv: -kv[1]):
        print(f"  {kind:14s} {n}")
    print(f"statements: {len(statements)}")
    for stratum, n in sorted(Counter(s.stratum for s in statements).items()):
        print(f"  {stratum:18s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
