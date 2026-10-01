"""Link each E6 statement to what happened, draw the hand-check sheet, and score it.

The linker reads only later advisories of the same airport or route (``faa.py`` builds the
statements). Draft outcome codebook, to be fixed by the E6 amendment:

- ``gs`` and ``route`` (probability of extension). **Extended** (1): a later advisory of the same
  stop or route, with no cancellation in between and a stated start no later than the stated
  end plus the grace, states an end later than the statement's. A route carried on under the
  same name and a new TMI ID, without a break, is the same route. **Not extended** (0)
  otherwise: ``cancelled`` when a cancellation closed the stop or route, ``lapsed`` when
  nothing followed.
- ``plan`` (planned ground stop or delay programme). **Issued** (1): an actual advisory of a
  named initiative for the airport (never a proposed one) is sent after the statement, no later
  than the window's end, with a stated period (cut at its cancellation, if one came first) that
  overlaps the window. **Not issued** (0) otherwise.
- **Excluded**: ``unresolved_boundary`` when the outcome could still change after the last month
  that was loaded; ``already_active`` when a named initiative was already running for the
  airport when the plan line was first issued, with a stated end at or after the start of the
  line's window.

The text the checkers read is ``CODEBOOK`` below; ``plan/E6_NOTES.md`` section 5 has it in full.

Four commands::

    uv run python -m analysis.coling.faa_links link    # development months -> links_dev.csv
    uv run python -m analysis.coling.faa_links report  # counts and sensitivities -> dev_report.json
    uv run python -m analysis.coling.faa_links sample  # the hand-check sheets for the gate
    uv run python -m analysis.coling.faa_links score SHEET.csv [SHEET.csv ...]

``link`` refuses months after the development months until the amendment flag file exists (see
``faa.check_months``); ``report`` and ``sample`` refuse them always. All three refuse a month
that is not completely on disk (``faa.coverage_gaps``).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from analysis.coling import faa

SEED = 20261001
GATE_MIN_LINKS = 150
GATE_MIN_PER_TERM = 30
GATE_THRESHOLD = 0.90  # draft value, for the owner to confirm
N_EXCLUDED_CHECKED = 10
N_DOUBLE_CHECKED = 30
CHECKERS = ("A1", "A2")
COUNT_MANUAL_STOPS = True  # draft: a hand-written ground stop for the airport counts as issued
COUNT_RENAMED_ROUTES = True  # draft: a route carried on under a new TMI ID is extended
RESTART_MINUTES = 30  # flag only: a new stop that starts this soon after the stated end
# An extension may be sent after the stated end (up to 21 minutes after it for a stop and 49 for
# a route in April and May 2026). The checker's list runs this long past the stated end, and
# "lapsed" is not concluded when the loaded months end sooner than that.
LATE_EXTENSION_MINUTES = 120

VERDICTS = {
    "ok": "ok", "c": "ok", "correct": "ok", "1": "ok", "y": "ok", "yes": "ok",
    "wrong": "wrong", "w": "wrong", "0": "wrong", "n": "wrong", "no": "wrong",
    "unclear": "unclear", "u": "unclear", "?": "unclear",
}  # fmt: skip
ERROR_CODES = {
    "S": "source misread: the term, airport, initiative or window is not what the advisory says",
    "M": "missed advisory: a later advisory that changes the outcome was not used",
    "L": "wrong link: the linked advisory is another stop, route, airport or initiative",
    "R": "rule misapplied: the advisories are right but the outcome contradicts the codebook",
    "X": "exclusion wrong: excluded but should be scored, or scored but should be excluded",
    "D": "codebook gap: the codebook does not decide this case",
}

PROGRAMME_KINDS = (
    "gs", "gs_cnx", "gs_manual", "gs_manual_cnx", "gdp", "gdp_proposed", "gdp_cnx",
)  # fmt: skip


@dataclass(frozen=True)
class Link:
    sid: str
    outcome: int | None  # 1, 0, or None when excluded
    code: (
        str  # extended, cancelled, lapsed, issued, not_issued, unresolved_boundary, already_active
    )
    evidence: tuple[str, ...]  # advisories that decide the outcome
    context: tuple[str, ...]  # every later advisory the linker could have used, in send order
    detail: str
    flags: tuple[str, ...]


# --------------------------------------------------------------------------------------
# The linker
# --------------------------------------------------------------------------------------


def _stamp(moment: dt.datetime | None) -> str:
    return f"{moment:%d/%H%MZ}" if moment else "?"


def index_by_element(advisories: list[faa.Advisory]) -> dict[str, list[faa.Advisory]]:
    """Ground-stop and delay-programme advisories by airport, in send order."""
    index: dict[str, list[faa.Advisory]] = defaultdict(list)
    for a in advisories:
        if a.kind in PROGRAMME_KINDS and a.element and a.sent is not None:
            # a hand-written advisory may name several airports ("LGA AND JFK")
            for airport in dict.fromkeys(re.findall(r"[A-Z0-9]+", a.element)):
                if airport != "AND":
                    index[airport].append(a)
    return index


def link_extension(
    s: faa.Statement,
    by_id: dict[str, faa.Advisory],
    related: list[faa.Advisory],
    data_end: dt.datetime,
    grace: int = faa.GRACE_MINUTES,
    count_renamed: bool = COUNT_RENAMED_ROUTES,
) -> Link:
    """Outcome of a probability-of-extension statement (ground stop or route)."""
    members = [by_id[i] for i in s.episode]
    position = s.episode.index(s.sources[-1])
    later = members[position + 1 :]
    horizon = s.window_end + dt.timedelta(minutes=grace)
    seen_until = context_span(s, grace)[1]
    context = tuple(a.id for a in related if s.issued < a.sent <= seen_until)
    flags = []
    if len(s.terms_seen) > 1:
        flags.append("term_changed")
    if any(a.period[1] and a.period[1] < s.window_end for a in later):
        flags.append("shortened")
    if s.family == "gs" and any(a.kind == "gdp" and s.issued < a.sent <= horizon for a in related):
        flags.append("gdp_followed")
    extending = next((a for a in later if a.period[1] and a.period[1] > s.window_end), None)
    until = extending.sent if extending is not None else horizon
    if any(a.kind == "gs_manual_cnx" and s.issued < a.sent <= until for a in related):
        flags.append("manual_release")  # some or all departure facilities were released by hand
    renamed = None
    if extending is None and s.family == "route":
        cancel = by_id[s.cancel_id] if s.episode_end == "cancelled" else None
        renamed = _continued(s, related, horizon, cancel)
        if renamed is not None:
            flags.append("continued_new_id")
            extending = renamed if count_renamed else None
    if extending is None and s.family == "gs" and _restarted(s, related):
        flags.append("new_stop_30")
    if extending is not None:
        added = faa._minutes(extending.period[1] - s.window_end)
        detail = f"end {_stamp(s.window_end)} -> {_stamp(extending.period[1])} (+{added} min)"
        if extending is renamed:
            detail += f", carried on as {extending.route_name} under TMI ID {extending.tmi_id}"
        return Link(s.sid, 1, "extended", (extending.id,), context, detail, tuple(flags))
    if horizon >= data_end:
        detail = f"end {_stamp(s.window_end)} is at the edge of the loaded months"
        return Link(s.sid, None, "unresolved_boundary", (), context, detail, tuple(flags))
    if s.episode_end == "cancelled":
        cancel = by_id[s.cancel_id]
        detail = f"cancelled at {_stamp(cancel.sent)}; stated end {_stamp(s.window_end)}"
        return Link(s.sid, 0, "cancelled", (cancel.id,), context, detail, tuple(flags))
    if seen_until >= data_end:  # an extension sent after the end would not have been loaded
        detail = f"end {_stamp(s.window_end)} is too near the edge of the loaded months"
        return Link(s.sid, None, "unresolved_boundary", (), context, detail, tuple(flags))
    detail = f"no later advisory moved the end past {_stamp(s.window_end)}"
    return Link(s.sid, 0, "lapsed", (), context, detail, tuple(flags))


def _outside(s: faa.Statement, related: list[faa.Advisory]) -> list[faa.Advisory]:
    """Later advisories outside the statement's own stop or route that state a later end."""
    return [
        a
        for a in related
        if a.id not in s.episode
        and a.sent > s.issued
        and a.period[0]
        and a.period[1]
        and a.period[1] > s.window_end
    ]


def _restarted(s: faa.Statement, related: list[faa.Advisory]) -> bool:
    """Whether another stop for the airport starts within ``RESTART_MINUTES`` of the stated end.

    Such a stop follows a cancellation or a gap, so it is a new stop and not an extension. The
    flag ``new_stop_30`` is kept for a sensitivity analysis.
    """
    latest = s.window_end + dt.timedelta(minutes=RESTART_MINUTES)
    return any(a.kind == "gs" and a.period[0] <= latest for a in _outside(s, related))


def _continued(s: faa.Statement, related: list[faa.Advisory], horizon, cancel):
    """The advisory that carries a route on under another TMI ID, if there is one.

    It has the same name (the FCA number aside; one name may extend the other), is sent no later
    than the statement's stated end and before any cancellation of the statement's route, and
    states a start no later than that end and an end later than it. The route then never
    stopped applying, although the issuer filed the rest of it as a new route (a new FCA
    number, or the next day's advisory).
    """
    name = _base_name(s.element)
    for a in _outside(s, related):
        other = _base_name(a.route_name)
        named_alike = bool(other) and (other.startswith(name) or name.startswith(other))
        in_time = a.sent <= horizon and a.period[0] <= horizon
        unbroken = cancel is None or faa._order(a) < faa._order(cancel)
        if a.kind == "reroute" and named_alike and in_time and unbroken:
            return a
    return None


def _running_at(history: list[faa.Advisory], base: str, moment: dt.datetime):
    """The advisory that has initiative ``base`` (gs or gdp) running at ``moment``, if any."""
    latest = None
    for a in history:
        if a.sent > moment:
            break
        if a.kind in (base, base + "_cnx"):
            latest = a
    if latest is None or latest.kind != base:
        return None
    return latest if latest.period[1] and latest.period[1] > moment else None


def link_plan(
    s: faa.Statement,
    history: list[faa.Advisory],
    data_end: dt.datetime,
    count_manual: bool = COUNT_MANUAL_STOPS,
) -> Link:
    """Outcome of a planned ground stop or delay programme: was it issued in its window."""
    bases = s.initiative.split("/")
    kinds = set(bases) | ({"gs_manual"} if count_manual and "gs" in bases else set())
    first_shown, last_shown = context_span(s)
    context = tuple(a.id for a in history if first_shown <= a.sent <= last_shown)
    flags = ["term_changed"] if len(s.terms_seen) > 1 else []
    # a hand-written stop that is running counts as a running stop when it counts as an issuance
    running_bases = [*bases, *(["gs_manual"] if count_manual and "gs" in bases else [])]
    for base in running_bases:
        running = _running_at(history, base, s.issued)
        if running is not None and running.period[1] >= s.window_start:
            detail = (
                f"{running.title} already running at {_stamp(s.issued)}, "
                f"until {_stamp(running.period[1])}"
            )
            return Link(s.sid, None, "already_active", (running.id,), context, detail, tuple(flags))
    after = [a for a in history if a.kind in kinds and s.issued < a.sent <= s.window_end]
    for a in after:
        start = a.period[0] or a.sent
        end = a.period[1] or start
        cancel = next(
            (c for c in history if c.kind == a.kind + "_cnx" and a.sent < c.sent < end), None
        )
        if cancel is not None and cancel.sent < start:
            continue  # cancelled before it began: it was never in effect
        if cancel is not None:  # cancelled before its stated end: in effect until then only
            end = cancel.sent
        if start <= s.window_end and end >= s.window_start:
            if a.kind == "gs_manual":
                flags.append("manual_stop")
            detail = f"{a.title} sent {_stamp(a.sent)}, period {_stamp(start)} - {_stamp(end)}"
            return Link(s.sid, 1, "issued", (a.id,), context, detail, tuple(flags))
    if s.window_end >= data_end:
        detail = f"window ends {_stamp(s.window_end)}, after the loaded months"
        return Link(s.sid, None, "unresolved_boundary", (), context, detail, tuple(flags))
    if after:
        flags.append("outside_window")
    if "gdp" in bases and any(
        a.kind == "gdp_proposed" and s.issued < a.sent <= s.window_end for a in history
    ):
        flags.append("proposed_only")
    detail = f"no {' or '.join(bases)} advisory for {s.element} in the window"
    return Link(s.sid, 0, "not_issued", (), context, detail, tuple(flags))


def link_all(
    statements: list[faa.Statement],
    advisories: list[faa.Advisory],
    data_end: dt.datetime,
    grace: int = faa.GRACE_MINUTES,
    count_manual: bool = COUNT_MANUAL_STOPS,
    count_renamed: bool = COUNT_RENAMED_ROUTES,
) -> list[Link]:
    by_id = {a.id: a for a in advisories}
    by_element = index_by_element(advisories)
    # Routes: what the checker is shown is wider than what the linker uses. It lists every
    # advisory with the same TMI ID or the same name (without the FCA number), so that a
    # route continued under another identifier is visible.
    by_route: dict[str, list[faa.Advisory]] = defaultdict(list)
    for a in advisories:
        if a.sent is not None and a.kind in ("reroute", "reroute_cnx"):
            for key in {faa.route_key(a), _base_name(a.route_name)} - {""}:
                by_route[key].append(a)
    links = []
    for s in statements:
        if s.family == "plan":
            links.append(link_plan(s, by_element.get(s.element, []), data_end, count_manual))
            continue
        if s.family == "gs":
            related = by_element.get(s.key, [])
        else:
            seen = {a.id: a for key in (s.key, _base_name(s.element)) for a in by_route[key]}
            related = sorted(seen.values(), key=lambda a: (a.sent, a.id))
        links.append(link_extension(s, by_id, related, data_end, grace, count_renamed))
    return links


def _base_name(route_name: str | None) -> str:
    """A route name without its FCA number: ``FCA003:IAH_KOBLE_PARTIAL`` -> ``IAH_KOBLE_PARTIAL``."""
    return re.sub(r"^FCA\d+:", "", route_name or "")


LINK_COLUMNS = (*faa.STATEMENT_COLUMNS, "day", "outcome", "code", "evidence", "flags", "detail")


def link_row(s: faa.Statement, link: Link) -> dict:
    row = faa.statement_row(s)
    row.update(
        day=s.day.isoformat(),
        outcome="" if link.outcome is None else link.outcome,
        code=link.code,
        evidence=" ".join(link.evidence),
        flags=" ".join(link.flags),
        detail=link.detail,
    )
    return row


# --------------------------------------------------------------------------------------
# The hand-check sample
# --------------------------------------------------------------------------------------


def _rng(name: str, seed: int = SEED) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{name}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def draw_sample(
    statements: list[faa.Statement],
    links: list[Link],
    per_term: int = GATE_MIN_PER_TERM,
    minimum: int = GATE_MIN_LINKS,
    n_excluded: int = N_EXCLUDED_CHECKED,
    n_double: int = N_DOUBLE_CHECKED,
    seed: int = SEED,
    draw: int = 1,
):
    """Seeded sample for the linker gate.

    From every term (family and term), ``per_term`` scored links, or all of them when the term
    has fewer; more are added across terms until ``minimum`` is reached; ``n_excluded`` excluded
    statements are added as a separate stratum. Items are sorted by id before every draw, and
    each stratum has its own generator, so dropping a family leaves the other draws unchanged.
    ``draw`` numbers a repeat of the gate: draw 2 gives another sample from the same seed.

    Returns (rows, frame): rows are dicts with sid, stratum, checker ("A1", "A2" or "both") in
    the order of the sheet; frame maps stratum to (links available, sampled, required).
    """
    by_sid = {s.sid: s for s in statements}
    suffix = "" if draw == 1 else f":draw{draw}"
    scored: dict[str, list[str]] = defaultdict(list)
    excluded: list[str] = []
    for link in sorted(links, key=lambda x: x.sid):
        if link.outcome is None:
            excluded.append(link.sid)
        else:
            scored[by_sid[link.sid].stratum].append(link.sid)
    chosen: dict[str, str] = {}
    for stratum in sorted(scored):
        ids = scored[stratum]
        for sid in _rng(stratum + suffix, seed).sample(ids, min(per_term, len(ids))):
            chosen[sid] = stratum
    rest = sorted(sid for ids in scored.values() for sid in ids if sid not in chosen)
    if len(chosen) < minimum and rest:
        for sid in _rng("top-up" + suffix, seed).sample(
            rest, min(minimum - len(chosen), len(rest))
        ):
            chosen[sid] = by_sid[sid].stratum
    frame = {
        stratum: (
            len(ids),
            sum(1 for x in chosen.values() if x == stratum),
            min(per_term, len(ids)),
        )
        for stratum, ids in sorted(scored.items())
    }
    picked_excluded = _rng("excluded" + suffix, seed).sample(
        excluded, min(n_excluded, len(excluded))
    )
    frame["excluded"] = (len(excluded), len(picked_excluded), 0)

    order = sorted(chosen) + sorted(picked_excluded)
    _rng("order" + suffix, seed).shuffle(order)
    doubles = set(_rng("double" + suffix, seed).sample(sorted(chosen), min(n_double, len(chosen))))
    rows, turn = [], 0
    for sid in order:
        if sid in doubles:
            checker = "both"
        else:
            checker = CHECKERS[turn % len(CHECKERS)]
            turn += 1
        rows.append({"sid": sid, "stratum": chosen.get(sid, "excluded"), "checker": checker})
    return rows, frame


def plan_excerpt(text: str) -> str:
    """Header, event time and the TERMINAL ACTIVE / TERMINAL PLANNED sections of a plan."""
    kept, keep = [], False
    for index, line in enumerate(text.splitlines()):
        if index == 0 or line.startswith("EVENT TIME"):
            kept.append(line)
            continue
        if re.match(r"TERMINAL (ACTIVE|PLANNED)", line):
            keep = True
        elif re.match(r"[A-Z][A-Za-z /()&.,\-]*:\s*$", line):
            keep = False
        if keep and line.strip():
            kept.append(line)
    return "\n".join(kept)


def route_excerpt(text: str) -> str:
    """A reroute advisory without its route table (the lines from ROUTES: to TMI ID)."""
    kept, skipping = [], False
    for line in text.splitlines():
        if line.startswith("ROUTES:"):
            skipping = True
            kept.append("ROUTES: [route table not shown]")
        elif line.startswith("TMI ID"):
            skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def shown_text(a: faa.Advisory) -> str:
    """The advisory text as the checker sees it: whole, or the relevant excerpt."""
    if a.kind == "ops_plan":
        return plan_excerpt(a.text)
    return route_excerpt(a.text) if a.kind == "reroute" else a.text


def _timeline_line(a: faa.Advisory) -> str:
    period = f"{_stamp(a.period[0])} - {_stamp(a.period[1])}" if a.period_label else ""
    term = f"  [PROBABILITY OF EXTENSION: {a.prob_extension}]" if a.prob_extension else ""
    name = f"  {a.route_name}" if a.route_name else f"  {a.element or ''}"
    label = f"{a.period_label} {period}" if period else ""
    return f"{a.id}  sent {a.sent:%m/%d %H:%MZ}  {a.title}{name}  {label}{term}".rstrip()


def outcome_text(link: Link) -> str:
    if link.outcome is None:
        return f"EXCLUDED ({link.code})"
    word = {
        "extended": "EXTENDED",
        "cancelled": "NOT EXTENDED (cancelled)",
        "lapsed": "NOT EXTENDED (lapsed)",
        "issued": "ISSUED",
        "not_issued": "NOT ISSUED",
    }[link.code]
    return f"{word} = {link.outcome}"


def context_span(s: faa.Statement, grace: int = faa.GRACE_MINUTES):
    """The hours whose advisories the checker is shown for a statement: (first, last)."""
    if s.family == "plan":
        return s.issued - dt.timedelta(hours=6), s.window_end + dt.timedelta(hours=1)
    return s.issued, s.window_end + dt.timedelta(minutes=grace + LATE_EXTENSION_MINUTES)


def others_naming(s: faa.Statement, advisories: list[faa.Advisory]) -> list[str]:
    """Advisories the linker does not read that name the statement's airport, in the same hours.

    They are of types the linker never uses (arrival delays, corrections, hotlines). The
    checker sees their titles, so that an advisory left out because of its title can be found.
    Routes have none: their list already holds every advisory of the same name or TMI ID.
    """
    if s.family == "route":
        return []
    first, last = context_span(s)
    lines = []
    for a in advisories:
        if a.kind != "other" or a.sent is None or not first <= a.sent <= last:
            continue
        named = re.findall(r"[A-Z0-9]+", f"{a.facility} {a.title}")
        if s.element in named:
            lines.append(f"{a.id}  sent {a.sent:%m/%d %H:%MZ}  {a.title}")
    return lines


def item_text(
    number: int,
    s: faa.Statement,
    link: Link,
    by_id: dict[str, faa.Advisory],
    others: list[str] | None = None,
) -> str:
    """One link as the checker reads it.

    The statement, the source text and the later advisories come first; the outcome the linker
    derived and the advisory it rests on come last, so that they are read after the evidence.
    """
    first = by_id[s.sources[0]]
    source = shown_text(first)
    window = f"{_stamp(s.window_start)} - {_stamp(s.window_end)}"
    parts = [
        f"## {number}. {s.sid}",
        "",
        f"- Term: **{s.term}** ({s.stratum}); written as: `{s.line}`",
        f"- Element: {s.element}; initiative: {s.initiative}; first issued {s.issued:%m/%d %H:%MZ}"
        f" in {first.id}; window read as {window}",
        f"- Repeated in: {' '.join(s.sources[1:]) or 'no later advisory'}",
        "",
        "Source advisory:",
        "",
        "```",
        source,
        "```",
        "",
        "Every advisory the linker could see for this element in the horizon:",
        "",
        "```",
    ]
    parts += [_timeline_line(by_id[i]) for i in link.context] or ["(none)"]
    parts += ["```", ""]
    if others:
        parts += ["Other advisories that name the element (not read by the linker):", "", "```"]
        parts += [*others, "```", ""]
    parts += [
        f"**Derived outcome: {outcome_text(link)}**. {link.detail}."
        + (f" Flags: {' '.join(link.flags)}." if link.flags else ""),
        "",
    ]
    if link.evidence:
        parts += ["Advisory that decides the outcome:", ""]
        for evidence in link.evidence:
            parts += ["```", shown_text(by_id[evidence]), "```", ""]
    else:
        parts += ["No advisory decides the outcome (nothing qualifying was found).", ""]
    return "\n".join(parts)


# The derived outcome is not a column: the checker meets it at the end of the item, after the
# advisories, and not on the sheet before the item is read.
SHEET_COLUMNS = (
    "row", "link_id", "term", "element", "statement", "issued", "window", "checker", "verdict",
    "error_code", "note",
)  # fmt: skip

CODEBOOK = """## Draft codebook

The full text is section 5 of `analysis/coling/plan/E6_NOTES.md`. All times are UTC.

**Ground stops and routes (probability of extension).** The statement is the first advisory
that states an end time for a stop or a route. It is EXTENDED when a later advisory of the same
stop or route states a later end, by any amount.

- The same stop: `CDM GROUND STOP` advisories for the airport, each sent with no `CDM GS CNX`
  between it and the one before, and each with a stated start no later than the stated end of
  the one before.
- The same route: advisories with the same TMI ID and the same name (one name may extend the
  other), with no `REROUTE CANCELLATION` of that name between them. A route is also carried
  on, and so EXTENDED, by an advisory of the same name under another TMI ID (a new FCA number,
  or the next day's advisory) when that advisory is sent no later than the stated end and
  before any cancellation of the route, and states a start no later than the stated end and
  an end later than it (flag `continued_new_id`).
- Otherwise NOT EXTENDED: "cancelled" when a cancellation followed no later than the stated
  end, "lapsed" when nothing followed. A wrong reason with the right outcome is still `ok`;
  say so in the note.
- Not extensions: the same end sent again; a shorter end; a new stop or route that starts
  after the stated end or after a cancellation, even minutes later (flag `new_stop_30` on
  stops); a delay programme that follows the stop (flag `gdp_followed`). A hand-written
  `GROUND STOP CANCELLATION` does not close a CDM stop (flag `manual_release`).

**Planned ground stops and delay programmes (operations plan).** The statement is the first
plan that carries the line for that airport with that window. A line that names several
airports gives one statement for each. A line with two estimates (`DEN GROUND DELAY PROGRAM
EXPECTED, GROUND STOP POSSIBLE`) gives one statement for each estimate.

- Window: `UNTIL hhmm` runs from the plan's send time to hhmm; `AFTER hhmm` runs from the
  first hhmm after the plan was sent to the next 0800Z (a plan sent at 2327Z that says `AFTER
  2300` means 2300Z of the next day); a range is used as written.
- ISSUED when an actual advisory of a named initiative for the airport is sent after the plan
  and no later than the window's end, and its stated period, cut at its own cancellation if
  that came first, overlaps the window. Actual advisories are `CDM GROUND STOP`,
  `CDM GROUND DELAY PROGRAM` and a hand-written `<airport> GROUND STOP` (flag `manual_stop`);
  a `PROPOSED` programme is not one. A line that names both initiatives is met by either. An
  advisory sent before the window opens counts when its period reaches into the window; one
  cancelled before its stated start does not count.
- Otherwise NOT ISSUED.

**Excluded.** `already_active`: a named initiative was running for the airport when the plan
was sent, with a stated end at or after the window's start; "running" is read from the send
times of the advisories, not from the plan's `TERMINAL ACTIVE` lines. `unresolved_boundary`:
the outcome could still change after the last development month (a window or a stated end
that reaches past the month's last day, or a stated end in the last two hours of that day
with nothing after it). Canadian airports give no statement.
"""

SHEET_INTRO = """# E6 linker gate: hand check of links ({checker})

Development months only. For each link, read the source advisory and the later advisories, and
decide whether the derived outcome follows the draft codebook below. Judge against the codebook
as written, also where you would have chosen another rule: a rule you disagree with is a note,
not an error. Write the verdict in `{sheet}`, column `verdict`: `ok`, `wrong` or `unclear`. For
`wrong` or `unclear`, add one error code and a short note.

Error codes:

{codes}

Each item gives the statement, the source advisory and the later advisories first, and the
derived outcome last. Work out the outcome from the advisories before you read the derived
one.

Times are written day/hhmm. The first list under each item shows every ground-stop,
delay-programme or route advisory the linker could see for the airport or route, up to two
hours after the stated end (one hour after a plan line's window, and from six hours before the
plan); check that none of them was missed. A second list, when there is one, gives the titles
of the other advisories that name the airport in the same hours; the linker does not read
them, and one that is a ground stop or a delay programme under another title is an `M`.

Some rows are also on the other checker's sheet. They are not marked; do not confer on any
row before both sheets are returned.

{codebook}
"""


def filled_sheets(out: Path) -> list[Path]:
    """Sheets under ``out`` that already hold a verdict: a new draw must not write over them."""
    filled = []
    for checker in CHECKERS:
        sheet = out / f"linker_gate_sheet_{checker}.csv"
        if sheet.exists():
            with sheet.open(newline="") as f:
                if any((row.get("verdict") or "").strip() for row in csv.DictReader(f)):
                    filled.append(sheet)
    return filled


def write_sheets(out: Path, rows, statements, links, advisories) -> list[Path]:
    """Write one sheet (CSV) and one reading file (Markdown) per checker; return the paths.

    Refuses when a sheet on disk holds verdicts: a checked sheet is moved away by hand first.
    """
    filled = filled_sheets(out)
    if filled:
        names = ", ".join(str(path) for path in filled)
        raise FileExistsError(f"{names}: verdicts are written there; move the sheet first")
    by_sid = {s.sid: s for s in statements}
    link_of = {link.sid: link for link in links}
    by_id = {a.id: a for a in advisories}
    in_order = sorted(advisories, key=lambda a: (a.sent is None, a.sent, a.id))
    paths = []
    for checker in CHECKERS:
        mine = [r for r in rows if r["checker"] in (checker, "both")]
        sheet = out / f"linker_gate_sheet_{checker}.csv"
        items = out / f"linker_gate_items_{checker}.md"
        codes = "\n".join(f"- `{code}`: {meaning}" for code, meaning in ERROR_CODES.items())
        text = [
            SHEET_INTRO.format(checker=checker, sheet=sheet.name, codes=codes, codebook=CODEBOOK)
        ]
        table = []
        for number, row in enumerate(mine, start=1):
            s, link = by_sid[row["sid"]], link_of[row["sid"]]
            text.append(item_text(number, s, link, by_id, others_naming(s, in_order)))
            table.append(
                {
                    "row": number,
                    "link_id": s.sid,
                    "term": row["stratum"],
                    "element": s.element,
                    "statement": s.line,
                    "issued": f"{s.issued:%Y-%m-%dT%H:%MZ}",
                    "window": f"{_stamp(s.window_start)} - {_stamp(s.window_end)}",
                    "checker": checker,  # rows shared with the other checker are not marked
                    "verdict": "",
                    "error_code": "",
                    "note": "",
                }
            )
        faa.write_csv(sheet, SHEET_COLUMNS, table)
        items.write_text("\n".join(text))
        paths += [sheet, items]
    return paths


# --------------------------------------------------------------------------------------
# Scoring the returned sheets
# --------------------------------------------------------------------------------------


def read_verdicts(paths) -> dict[str, dict]:
    """Verdicts per link from the returned sheets.

    Returns {link_id: {"term": ..., "verdicts": [...], "codes": [...]}}; the codes are the error
    codes written beside verdicts other than ``ok``.
    """
    checked: dict[str, dict] = {}
    for path in paths:
        with Path(path).open(newline="") as f:
            for row in csv.DictReader(f):
                raw = (row.get("verdict") or "").strip().lower()
                if not raw:
                    continue
                if raw not in VERDICTS:
                    raise ValueError(f"{path}: verdict {raw!r} for {row['link_id']} is not known")
                entry = checked.setdefault(
                    row["link_id"], {"term": row["term"], "verdicts": [], "codes": []}
                )
                entry["verdicts"].append(VERDICTS[raw])
                code = (row.get("error_code") or "").strip().upper()
                if VERDICTS[raw] != "ok" and code:
                    entry["codes"].append(code)
    return checked


def score(
    checked: dict[str, dict],
    required: dict[str, int],
    threshold: float = GATE_THRESHOLD,
    minimum: int = GATE_MIN_LINKS,
) -> dict:
    """Share of checked links that are correct, overall and per term, against the gate.

    A link checked twice is correct only when both checkers said ``ok``. The ``excluded``
    stratum is reported but does not count towards the gate. The gate passes when at least
    ``minimum`` links are checked, every term has its required number, and the overall share
    correct is at least ``threshold``.
    """
    per_term: dict[str, Counter] = defaultdict(Counter)
    double = Counter()
    codes = Counter()
    for entry in checked.values():
        verdicts = entry["verdicts"]
        codes.update(entry.get("codes", ()))
        per_term[entry["term"]]["checked"] += 1
        per_term[entry["term"]]["ok"] += all(v == "ok" for v in verdicts)
        per_term[entry["term"]]["unclear"] += any(v == "unclear" for v in verdicts)
        if len(verdicts) > 1:
            double["links"] += 1
            double["agree"] += len(set(verdicts)) == 1
    terms = {}
    for term in sorted(set(per_term) | set(required)):
        n, ok = per_term[term]["checked"], per_term[term]["ok"]
        terms[term] = {
            "checked": n,
            "required": required.get(term, 0),
            "correct": ok,
            "share_correct": round(ok / n, 4) if n else None,
            "unclear": per_term[term]["unclear"],
        }
    gate_terms = {t: v for t, v in terms.items() if t != "excluded"}
    n = sum(v["checked"] for v in gate_terms.values())
    ok = sum(v["correct"] for v in gate_terms.values())
    short = sorted(t for t, v in gate_terms.items() if v["checked"] < v["required"])
    share = ok / n if n else None
    return {
        "threshold": threshold,
        "checked": n,
        "correct": ok,
        "share_correct": round(share, 4) if share is not None else None,
        "terms": terms,
        "terms_below_threshold": sorted(
            t
            for t, v in gate_terms.items()
            if v["checked"] and v["correct"] / v["checked"] < threshold
        ),
        "terms_short_of_required": short,
        "error_codes": dict(sorted(codes.items())),
        "double_checked": double["links"],
        "double_agree": double["agree"],
        "enough_links": n >= minimum,
        "passed": bool(n >= minimum and not short and share is not None and share >= threshold),
    }


def code_hashes() -> dict[str, str]:
    """sha256 of the parser and the linker, so a sheet can be tied to the code that drew it."""
    here = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((here / name).read_bytes()).hexdigest()
        for name in ("faa.py", "faa_links.py")
    }


def read_frame(path: Path) -> dict[str, int]:
    with path.open(newline="") as f:
        return {row["term"]: int(row["required"]) for row in csv.DictReader(f)}


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------


def _load(args):
    advisories, data_end = faa.load_months(args.root, args.months)
    statements = faa.build_statements(advisories, args.months, args.grace)
    links = link_all(statements, advisories, data_end, args.grace)
    return advisories, statements, links


def count_table(statements, links, with_outcomes: bool) -> list[dict]:
    """Statements, exclusions and days per term; outcome counts only when ``with_outcomes``."""
    by_sid = {s.sid: s for s in statements}
    table: dict[str, Counter] = defaultdict(Counter)
    days: dict[str, set] = defaultdict(set)
    for link in links:
        s = by_sid[link.sid]
        table[s.stratum]["statements"] += 1
        table[s.stratum]["excluded"] += link.outcome is None
        table[s.stratum]["scored"] += link.outcome is not None
        table[s.stratum]["yes"] += link.outcome == 1
        days[s.stratum].add(s.day)
    rows = []
    for stratum in sorted(table):
        row = {"term": stratum, **table[stratum], "days": len(days[stratum])}
        row = {
            k: row.get(k, 0) for k in ("term", "statements", "excluded", "scored", "yes", "days")
        }
        if not with_outcomes:
            del row["yes"]
        rows.append(row)
    return rows


def _changed(base: dict[str, int | None], statements, links) -> int:
    """Statements whose outcome differs from ``base`` (missing ones count as different)."""
    other = {link.sid: link.outcome for link in links}
    return sum(1 for sid in set(base) | set(other) if base.get(sid, "-") != other.get(sid, "-"))


def dev_report(advisories, months, data_end) -> dict:
    """Counts for the development months: advisories, statements, outcomes and sensitivities."""
    wanted = set(months)
    in_months = [a for a in advisories if f"{a.day:%Y-%m}" in wanted]
    per_day = Counter(a.day for a in in_months)
    statements = faa.build_statements(advisories, months)
    links = link_all(statements, advisories, data_end)
    base = {link.sid: link.outcome for link in links}
    by_sid = {s.sid: s for s in statements}

    plan_lines = Counter()
    plan_terms = Counter()
    not_used = Counter()
    for a in in_months:
        for line in a.plan_lines:
            if line.section == "TERMINAL PLANNED" and line.initiatives and line.airports:
                plan_terms[line.term or "(no known term)"] += 1
            if line.section == "TERMINAL PLANNED" and not (
                line.term and line.initiatives and line.airports
            ):
                not_used[" ".join(line.raw.split())] += 1
            if line.section != "TERMINAL PLANNED":
                plan_lines[f"other section: {line.section}"] += 1
            elif not line.term:
                plan_lines["terminal, no known term"] += 1
            elif not line.initiatives:
                plan_lines["terminal, no ground stop or delay programme"] += 1
            elif not line.airports:
                plan_lines["terminal, no airport (area or free text)"] += 1
            else:
                plan_lines["terminal, used"] += 1

    def variant(**options):
        build = {k: v for k, v in options.items() if k in ("grace", "day_end_hour")}
        names = ("grace", "count_manual", "count_renamed")
        link = {k: v for k, v in options.items() if k in names}
        alt = faa.build_statements(advisories, months, **build)
        return _changed(base, alt, link_all(alt, advisories, data_end, **link))

    flags = Counter(flag for link in links for flag in link.flags)
    codes = Counter(f"{by_sid[link.sid].family}:{link.code}" for link in links)

    lead_quartiles = {}
    for family in ("gs", "route", "plan"):
        leads = sorted(s.lead_minutes for s in statements if s.family == family)
        if leads:
            lead_quartiles[family] = [leads[int(q * (len(leads) - 1))] for q in (0.25, 0.5, 0.75)]

    by_id = {a.id: a for a in advisories}

    def short_extension(link: Link, minutes: int = 15) -> bool:
        """Extended, but no later advisory of the episode moves the end by ``minutes`` or more."""
        if link.code != "extended":
            return False
        s = by_sid[link.sid]
        later = s.episode[s.episode.index(s.sources[-1]) + 1 :]
        ends = [by_id[i].period[1] for i in (*later, *link.evidence) if by_id[i].period[1]]
        return max(ends) < s.window_end + dt.timedelta(minutes=minutes)

    def flagged_zero(flag: str) -> int:
        return sum(1 for link in links if link.outcome == 0 and flag in link.flags)

    programme_words = re.compile(r"GROUND STOP|\bGS\b|GDP|DELAY PROGRAM|\bAFP\b|AIRSPACE FLOW")
    unclassified = Counter(
        a.title for a in in_months if a.kind == "other" and programme_words.search(a.title)
    )
    canadian = Counter(
        a.kind
        for a in in_months
        if a.kind in PROGRAMME_KINDS and a.element and not faa.in_scope(a.element)
    )
    return {
        "months": sorted(wanted),
        "days_with_advisories": len(per_day),
        "advisories": len(in_months),
        "advisories_per_day": {
            "min": min(per_day.values(), default=0),
            "median": sorted(per_day.values())[len(per_day) // 2] if per_day else 0,
            "max": max(per_day.values(), default=0),
        },
        "advisories_by_kind": dict(Counter(a.kind for a in in_months).most_common()),
        "probability_of_extension_as_written": dict(
            sorted(
                Counter(
                    f"{a.kind}:{a.prob_extension}" for a in in_months if a.prob_extension
                ).items()
            )
        ),
        "plan_lines": dict(sorted(plan_lines.items())),
        "plan_line_terms_as_written": dict(plan_terms.most_common()),
        "terminal_planned_lines_not_used": dict(not_used.most_common()),
        "lead_minutes_quartiles": lead_quartiles,
        "days_by_family": {
            family: len({s.day for s in statements if s.family == family})
            for family in ("gs", "route", "plan")
        },
        "statements": len(statements),
        "terms": count_table(statements, links, with_outcomes=True),
        "codes": dict(sorted(codes.items())),
        "flags": dict(sorted(flags.items())),
        "statements_repeated_in_later_advisories": sum(len(s.sources) > 1 for s in statements),
        "airport_days_plan": len({(s.element, s.day) for s in statements if s.family == "plan"}),
        "titles_naming_a_programme_but_not_classified": dict(unclassified.most_common()),
        "advisories_for_canadian_airports_by_kind": dict(canadian.most_common()),
        "outcomes_changed_by": {
            "a new stop within 30 minutes of the stated end counted as an extension": (
                flagged_zero("new_stop_30")
            ),
            "a route carried on under a new TMI ID not counted as an extension": variant(
                count_renamed=False
            ),
            "an extension of under 15 minutes not counted": sum(
                short_extension(link) for link in links
            ),
            "grace 15 minutes instead of 0": variant(grace=15),
            "grace 30 minutes instead of 0": variant(grace=30),
            "hand-written stops not counted as issued": variant(count_manual=False),
            "operating day ends 0600Z instead of 0800Z": variant(day_end_hour=6),
            "operating day ends 1000Z instead of 0800Z": variant(day_end_hour=10),
        },
    }


def _print_counts(statements, links, with_outcomes: bool) -> None:
    rows = count_table(statements, links, with_outcomes)
    if not rows:
        print("no statements")
        return
    columns = list(rows[0])
    print(" ".join(f"{c:>18s}" if c == "term" else f"{c:>10s}" for c in columns))
    for row in rows:
        print(" ".join(f"{row[c]:>18s}" if c == "term" else f"{row[c]:>10d}" for c in columns))
    if with_outcomes:
        print("codes:", dict(sorted(Counter(link.code for link in links).items())))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.faa_links")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("link", "sample", "report"):
        p = sub.add_parser(name)
        p.add_argument("--root", type=Path, default=faa.ROOT)
        p.add_argument("--out", type=Path, default=faa.OUT)
        p.add_argument("--months", nargs="+", default=list(faa.DEV_MONTHS))
        p.add_argument("--grace", type=int, default=faa.GRACE_MINUTES)
        if name == "link":
            p.add_argument("--name", help="suffix of the links table (default: dev)")
        if name == "sample":
            p.add_argument("--families", nargs="+", default=["gs", "route", "plan"])
            p.add_argument("--per-term", type=int, default=GATE_MIN_PER_TERM)
            p.add_argument("--minimum", type=int, default=GATE_MIN_LINKS)
            p.add_argument("--draw", type=int, default=1, help="2 for a repeat of the gate")
    p = sub.add_parser("score")
    p.add_argument("sheets", nargs="+", type=Path)
    p.add_argument("--frame", type=Path, default=faa.OUT / "linker_gate_frame.csv")
    p.add_argument("--threshold", type=float, default=GATE_THRESHOLD)
    p.add_argument("--out", type=Path, default=faa.OUT / "linker_gate_score.json")
    args = ap.parse_args(argv)

    if args.command == "score":
        result = score(read_verdicts(args.sheets), read_frame(args.frame), args.threshold)
        args.out.write_text(json.dumps(result, indent=1) + "\n")
        print(f"{'term':18s} {'checked':>7s} {'required':>8s} {'correct':>7s} {'share':>6s}")
        for term, v in result["terms"].items():
            share = "-" if v["share_correct"] is None else f"{v['share_correct']:.3f}"
            print(f"{term:18s} {v['checked']:7d} {v['required']:8d} {v['correct']:7d} {share:>6s}")
        print(
            f"overall: {result['correct']} of {result['checked']} correct "
            f"({result['share_correct']}); threshold {result['threshold']}; "
            f"double-checked {result['double_checked']}, agree {result['double_agree']}"
        )
        if result["error_codes"]:
            print("error codes on links not marked ok:", result["error_codes"])
        print("GATE PASSED" if result["passed"] else "GATE NOT PASSED")
        return 0 if result["passed"] else 1

    faa.check_months(args.months)  # before anything is read or written
    name = faa.table_name(args.months, args.name) if args.command == "link" else ""
    if args.command in ("sample", "report"):  # development months only, whatever the flag says
        locked = sorted(m for m in args.months if faa.is_locked(m))
        if locked:
            raise faa.TestMonthsLocked(
                f"{', '.join(locked)}: '{args.command}' is for the development months only"
            )
    if args.command == "report":
        advisories, data_end = faa.load_months(args.root, args.months)
        report = dev_report(advisories, args.months, data_end)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "dev_report.json").write_text(json.dumps(report, indent=1) + "\n")
        print(json.dumps(report, indent=1))
        return 0
    advisories, statements, links = _load(args)
    by_sid = {s.sid: s for s in statements}
    if args.command == "link":
        faa.write_csv(
            args.out / f"links_{name}.csv",
            LINK_COLUMNS,
            (link_row(by_sid[link.sid], link) for link in links),
        )
        # outcome counts are printed for development months only
        _print_counts(statements, links, all(m in faa.DEV_MONTHS for m in args.months))
        return 0

    if filled_sheets(args.out):  # before the frame is rewritten; write_sheets says which
        write_sheets(args.out, [], [], [], [])
    kept = [s for s in statements if s.family in set(args.families)]
    kept_ids = {s.sid for s in kept}
    kept_links = [link for link in links if link.sid in kept_ids]
    rows, frame = draw_sample(kept, kept_links, args.per_term, args.minimum, draw=args.draw)
    faa.write_csv(
        args.out / "linker_gate_frame.csv",
        ("term", "available", "sampled", "required"),
        (
            {"term": term, "available": a, "sampled": n, "required": r}
            for term, (a, n, r) in frame.items()
        ),
    )
    paths = write_sheets(args.out, rows, kept, kept_links, advisories)
    meta = {
        "seed": SEED,
        "draw": args.draw,
        "months": sorted(args.months),
        "families": sorted(args.families),
        "per_term": args.per_term,
        "minimum": args.minimum,
        "grace_minutes": args.grace,
        "scored_links_in_frame": sum(a for term, (a, _, _) in frame.items() if term != "excluded"),
        "rows": len(rows),
        "double_checked": sum(row["checker"] == "both" for row in rows),
        "rows_per_checker": {
            checker: sum(row["checker"] in (checker, "both") for row in rows)
            for checker in CHECKERS
        },
        "sha256": code_hashes(),
    }
    (args.out / "linker_gate_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    for term, (available, sampled, required) in frame.items():
        print(f"{term:18s} available {available:5d}  sampled {sampled:3d}  required {required:3d}")
    print(f"rows: {len(rows)} links; per checker {meta['rows_per_checker']}")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
