"""The language-model reading harness for the COLING 2027 study (E2 to E5): frozen prompts, strict
output schemas, a cached and spend-capped runner, a no-call dry run, and leakage masking.

A reader sees one FDA drug-shortage entry (a *statement event*: generic x company x text, dated by
its Date of Update) and answers one of the frozen prompt templates:

* ``literal-v1``: what the entry asserts. Statement type, the calendar interval its time refers
  to (anchored to the Date of Update, under written conventions) or ``ABSTAIN``, a certainty
  class, a stale flag and the quoted evidence. ``literal-free-v1`` is the convention-free
  secondary variant.
* ``predictive-v1``: what will happen. P(recovered by horizon A), P(recovered by horizon B) and
  quantiles (q10, q50, q80, q90, q95) of days from the Date of Update to recovery, capped at 365.
  Horizon A is the end of the stated period (``stated_end``, supplied by the dataset builder, so
  the scored events never depend on a model's own reading) and B is 90 days later; an entry with
  no stated period gets Date of Update + 90 and + 180 days, with a different frozen sentence.
* ``predictive-track-v1``: the same, with the issuer's track record in context: a slip table by
  form and up to 10 resolved training-period examples (:class:`TrackRecord`). Examples dated on
  or after the test start (2023-01-01) are refused, so no sealed outcome can reach a prompt.
* ``probe-v1``: the E4 no-notice probe. Name, company, presentation and date only.

Every template is pinned by SHA-256 in ``FROZEN_SHA256`` (text, fixed fragments, output schema,
the repair prompt, and renderings of a canary item plain and masked with a date shift, so the
renderer and the masker are pinned too); the runner refuses to start on a mismatch.

Answers are parsed strictly (:func:`parse_reading`): one JSON object, validated against the
kind's JSON Schema (``LITERAL_SCHEMA``, ``PREDICTIVE_SCHEMA``) plus semantic checks (real
calendar dates, start <= end, non-decreasing quantiles). A failure earns exactly one repair
call, a distinct cached request that shows the model its answer and the errors.

Calls reuse the commitment study's machinery by import, unchanged: the model ladder and its dated
prices (:data:`analysis.commitment.endpoints.LADDER`), the served-model check
(:class:`~analysis.commitment.endpoints.EchoCheckedClient`), key resolution at runtime
(``EndpointConfig.resolve_key``; this module never reads a key), and
:class:`~analysis.real_content_pilot.transport.GuardedTransport` (retries, refusals, a spend
cap, ``spend_log.jsonl`` with token counts and dated dollar cost, thinking billed as output where
the endpoint says so). On top of that this module adds:

* a disk cache (:class:`collie.llm.DiskCache`) keyed by model, full prompt hash, template id and
  SHA, item id, sample index, repair attempt and decoding, so a rerun is free;
* a *projected* spend check before every paid call: the call is refused if the run's recorded
  spend plus a conservative estimate of this call would pass the run's cap;
* a study-level check at start: recorded spend of every run under the output root plus this
  run's cap must fit in ``--study-cap-usd`` (default 200). Runs launched in parallel must split
  what remains between their caps;
* live reading of test-period items (Date of Update on or after 2023-01-01) only with
  ``--allow-test-items``, to be passed once the study is registered.

Leakage controls (E4): :class:`NameMasker` replaces generic, brand and company names and NDC
digits with deterministic fictitious ones, and scales strengths by a per-generic factor (volumes
kept, so concentrations stay coherent), in the fields and in the free text; :func:`shift_dates`
shifts every date by whole years. Both are applied at render time to the
item and to the track record; the stored readings keep the real item id and horizons, and a
literal interval read under a shift is also stored shifted back.

Items are JSON Lines (or CSV), one statement event each, with keys ``item_id``,
``generic_name``, ``company_name``, ``presentation``, ``date_of_update`` (ISO or MM/DD/YYYY) and
optionally ``type_of_update``, ``availability_information``, ``related_information``,
``reason_for_shortage``, ``stated_end``, ``form`` and ``mask_terms`` (extra strings to mask). The
FDA column headers and the corpus builder's column names (``event_id``, ``event_date``,
``availability_text``, ``related_text``) are accepted as aliases; every other key, outcome fields
included, is ignored and never reaches a prompt. The track record is one
JSON object, see :func:`load_track_record`.

Outputs of a live run: ``<out-root>/<run>/`` holds ``readings.jsonl`` (parsed readings, one row
per item and sample), ``spend_log.jsonl``, ``invocations.jsonl`` and ``run_manifest.json``;
``<local-root>/<run>/`` (git-ignored ``results/``) holds the cache and ``responses.jsonl`` (raw
text). Readings are model outputs, never outcomes, so nothing here is sealed.

Usage (from the repository root)::

    # no call: render, count and price
    python -m analysis.coling.read --items items.jsonl --template literal-v1 \\
        --model llama-3.3-70b --model deepseek-v3 --dry-run [--show 2]
    # live (paid): one model per run
    python -m analysis.coling.read --items items.jsonl --template predictive-track-v1 \\
        --track-record track.json --model deepseek-v3 --run-name e3-track-deepseek-v3 \\
        --spend-cap-usd 10 --allow-live [--allow-test-items] [--samples 20 --temperature 1.0] \\
        [--mask-names] [--shift-years 3]
    python -m analysis.coling.read --print-schemas
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import string
import subprocess
import time
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cached_property, lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Any

from analysis.commitment.endpoints import LADDER, EchoCheckedClient
from analysis.real_content_pilot.transport import (
    CallCapReached,
    GuardedTransport,
    SpendCapReached,
    prompt_digest,
)
from collie.llm import DiskCache, cache_key
from collie.llm.client import DecodingConfig, EndpointConfig, RawResponse, Transport

REPO = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO / "analysis" / "coling" / "out" / "read"
LOCAL_ROOT = REPO / "results" / "coling" / "read"
LIVE_TIMEOUT_S = 180.0
TEST_START = date(2023, 1, 1)
"""Statements dated on or after this day form the sealed test period."""
CAP_DAYS = 365
HORIZON_B_OFFSET = timedelta(days=90)
FALLBACK_HORIZONS = (timedelta(days=90), timedelta(days=180))
QUANTILE_KEYS = ("q10", "q50", "q80", "q90", "q95")
MAX_EXAMPLES = 10
STUDY_MODELS = (
    "llama-3.3-70b",
    "deepseek-v3",
    "qwen-2.5-7b",
    "gemma-3-27b",
    "gpt-oss-20b",
    "gpt-4o-mini",
    "gemini-3.8-flash",
    "grok-4.20",
)
"""The design memo's eight readers; the first two are the primaries. Any ladder rung is allowed."""
STUDY_CAP_USD = 200.0
_RUN_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

# ---------------------------------------------------------------------------------------------
# Items and the track record
# ---------------------------------------------------------------------------------------------

_ALIASES = {
    "Generic Name": "generic_name",
    "Company Name": "company_name",
    "Presentation": "presentation",
    "Type of Update": "type_of_update",
    "Date of Update": "date_of_update",
    "Availability Information": "availability_information",
    "Related Information": "related_information",
    "Reason for Shortage": "reason_for_shortage",
    "event_id": "item_id",  # analysis.coling.corpus statement events
    "event_date": "date_of_update",
    "availability_text": "availability_information",
    "related_text": "related_information",
}
"""Other names accepted for item fields: the FDA headers and the corpus builder's columns. Any
other column (outcome fields included) is ignored and never reaches a prompt."""


def parse_date(value: str | date) -> date:
    """An ISO (YYYY-MM-DD) or FDA-style (MM/DD/YYYY) date."""
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return datetime.strptime(text, "%m/%d/%Y").date()


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def _terms_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return (str(value),) if isinstance(value, str) else tuple(str(t) for t in value)


@dataclass(frozen=True)
class ReadItem:
    """One statement event as a reader sees it. Carries no outcome."""

    item_id: str
    generic_name: str
    company_name: str
    presentation: str
    date_of_update: str
    type_of_update: str = ""
    availability_information: str = ""
    related_information: str = ""
    reason_for_shortage: str = ""
    stated_end: str | None = None
    """End of the period the entry states (ISO), from the builder; horizon A of the forecasts."""
    form: str | None = None
    """The builder's form label (for example "a month and year"), shown with the track record."""
    mask_terms: tuple[str, ...] = ()
    """Extra strings the name masker must replace (brand names it cannot detect)."""

    @classmethod
    def from_dict(cls, row: dict) -> ReadItem:
        data = {_ALIASES.get(k, k): v for k, v in row.items()}
        if not _text(data.get("item_id")) or not _text(data.get("date_of_update")):
            raise ValueError(f"an item needs item_id and date_of_update: {sorted(data)[:12]}")
        stated = _text(data.get("stated_end")) or None
        return cls(
            item_id=str(data["item_id"]),
            generic_name=_text(data.get("generic_name")),
            company_name=_text(data.get("company_name")),
            presentation=_text(data.get("presentation")),
            date_of_update=parse_date(data["date_of_update"]).isoformat(),
            type_of_update=_text(data.get("type_of_update")),
            availability_information=_text(data.get("availability_information")),
            related_information=_text(data.get("related_information")),
            reason_for_shortage=_text(data.get("reason_for_shortage")),
            stated_end=parse_date(stated).isoformat() if stated else None,
            form=_text(data.get("form")) or None,
            mask_terms=_terms_tuple(data.get("mask_terms")),
        )

    @property
    def period(self) -> str:
        return "test" if parse_date(self.date_of_update) >= TEST_START else "train"


@dataclass(frozen=True)
class SlipRow:
    """One row of the training-split slip table: how estimates of one form turned out."""

    form: str
    statements: int
    share_by_stated_end: float | None
    """Share recovered by the stated end; None (shown "n/a") for forms with no stated end."""
    share_by_stated_end_90: float | None
    median_days_to_recovery: float | None


OUTCOMES = ("recovered", "not_recovered", "discontinued")


@dataclass(frozen=True)
class ResolvedExample:
    """A resolved training-period entry shown in context. Recovery lies in (after, by]."""

    date_of_update: str
    outcome: str
    availability_information: str = ""
    related_information: str = ""
    type_of_update: str = ""
    stated_end: str | None = None
    recovered_after: str | None = None
    recovered_by: str | None = None
    generic_name: str = ""
    company_name: str = ""


@dataclass(frozen=True)
class TrackRecord:
    """The in-context track record: a slip table by form plus at most 10 resolved examples."""

    through: str
    slip_table: tuple[SlipRow, ...]
    examples: tuple[ResolvedExample, ...]
    since: str = "2019-10-01"

    def check(self) -> None:
        """Refuse anything that could carry a test-period (sealed) outcome into a prompt."""
        if parse_date(self.through) >= TEST_START:
            raise ValueError(f"the track record must end before {TEST_START}: {self.through}")
        if len(self.examples) > MAX_EXAMPLES:
            raise ValueError(f"at most {MAX_EXAMPLES} examples, got {len(self.examples)}")
        for ex in self.examples:
            if parse_date(ex.date_of_update) >= TEST_START:
                raise ValueError(f"example dated {ex.date_of_update} is in the test period")
            if ex.outcome not in OUTCOMES:
                raise ValueError(f"example outcome must be one of {OUTCOMES}: {ex.outcome!r}")
            if ex.outcome == "recovered" and not ex.recovered_by:
                raise ValueError("a recovered example needs recovered_by")
        for row in self.slip_table:
            for share in (row.share_by_stated_end, row.share_by_stated_end_90):
                if share is not None and not 0.0 <= share <= 1.0:
                    raise ValueError(f"slip-table share outside [0, 1] for {row.form!r}")


def track_precedes(track: TrackRecord, item: ReadItem) -> bool:
    """Whether the track record ends before the item's date, so it holds nothing from its
    future (always true for test-period items)."""
    return parse_date(track.through) < parse_date(item.date_of_update)


def load_items(path: Path) -> list[ReadItem]:
    """Items from JSON Lines, or from a CSV (optionally gzipped) such as the corpus events."""
    if path.name.endswith((".csv", ".csv.gz")):
        import pandas as pd

        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        rows = frame.to_dict(orient="records")
    else:
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
    items = [ReadItem.from_dict(row) for row in rows]
    ids = [i.item_id for i in items]
    if len(set(ids)) != len(ids):
        raise ValueError("item ids must be unique")
    return items


def load_track_record(path: Path) -> TrackRecord:
    """Read ``{"through", "since"?, "slip_table": [SlipRow fields], "examples": [ResolvedExample
    fields]}`` (dates ISO). Unknown keys raise, so no stray column slips in unnoticed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    unknown = set(data) - {"through", "since", "slip_table", "examples"}
    if unknown:
        raise ValueError(f"unknown track-record keys: {sorted(unknown)}")
    track = TrackRecord(
        through=parse_date(data["through"]).isoformat(),
        since=parse_date(data.get("since", "2019-10-01")).isoformat(),
        slip_table=tuple(SlipRow(**row) for row in data["slip_table"]),
        examples=tuple(ResolvedExample(**row) for row in data.get("examples", ())),
    )
    track.check()
    return track


# ---------------------------------------------------------------------------------------------
# Frozen prompt templates
# ---------------------------------------------------------------------------------------------

ENTRY_BLOCK = """Entry
- Drug: $generic_name
- Company: $company_name
- Presentation: $presentation
- Type of update: $type_of_update
- Date of update: $date_of_update
- Availability information: $availability_information
- Related information: $related_information
- Reason for shortage: $reason_for_shortage"""

LITERAL_HEAD = (
    """You will read one entry from the US FDA drug-shortage list. Report only what the \
entry itself says about timing. Do not forecast, and do not use anything you may know about this \
drug or company.

"""
    + ENTRY_BLOCK
    + """

Answer these five questions about the entry.

1. statement_type: the kind of forward-looking statement the entry makes about supply of this \
presentation.
   - "recovery": when supply is expected to return to normal, or the shortage to end.
   - "next_delivery": when the next shipment, release or delivery is expected.
   - "depletion": when current stock is expected to run out, or until when product remains \
available.
   - "discontinuation": when the product will be, or has been, discontinued.
   - "none": the entry makes no forward-looking statement about timing.
   If the entry makes more than one, choose the first that applies in this order: recovery, \
next_delivery, discontinuation, depletion. A statement whose timing is unknown (for example \
"Next shipment TBD") still has a type. Expiry dates, lot numbers and past events are not \
statements about timing.

2. interval: the calendar dates that the chosen statement's time refers to, as {"start": \
"YYYY-MM-DD", "end": "YYYY-MM-DD"}, or the string "ABSTAIN" if the entry gives no date or period \
for it (for example TBD, unknown or no estimate). Read times relative to the date of update.
"""
)

LITERAL_TAIL = """
3. certainty: how the entry presents the timing of the chosen statement.
   - "asserted": stated plainly, for example "Next release April 2020".
   - "estimated": hedged, for example estimated, expected, anticipated, projected, approximately \
or tentative.
   - "undetermined": the entry says the timing is not known, for example TBD, unknown or no \
estimated date.
   - "no_statement": use this exactly when statement_type is "none".

4. stale: true if the interval ends before the date of update, meaning the entry repeats an \
estimate that had already passed when it was updated; otherwise false, including when interval \
is "ABSTAIN".

5. quote: the shortest exact words from the entry that your answer rests on, or "" if there are \
none.

Reply with one JSON object and nothing else, in this form (interval may instead be "ABSTAIN"):
{"statement_type": "...", "interval": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}, \
"certainty": "...", "stale": true or false, "quote": "..."}"""

CONVENTIONS = """   Conventions:
   - A month, such as "April 2020" or "Apr-20": the whole month.
   - "Early", "mid" or "late" in a month: days 1 to 10, 11 to 20, or 21 to the month's last day. \
"Beginning of" a month is early; "end of" a month is late.
   - A quarter, such as "Q2 2020" or "2Q20": the whole quarter. The "first half" or "second \
half" of a year: January to June, or July to December.
   - A year alone: the whole year.
   - A range, such as "May-June 2020": from the start of its first part to the end of its last.
   - A month, quarter or half without a year: its first occurrence that ends on or after the \
date of update.
   - "By" or "before" a time: from the date of update to the end of that time.
   - A relative time, counted from the date of update: "within N" or "up to N" is from the date \
of update to N later; "N to M", such as "4-6 weeks", is from N later to M later; a single "N" is \
N later, as both start and end. A week is 7 days and a month 30 days.
   - An exact date: that day, as both start and end.
   - A vague time with no number and no calendar name, such as "a few months", "soon" or "the \
near future": "ABSTAIN"."""

NO_CONVENTIONS = (
    "   Use your own judgement of what the words mean; there are no further conventions."
)

LITERAL_TEXT = LITERAL_HEAD + CONVENTIONS + "\n" + LITERAL_TAIL
LITERAL_FREE_TEXT = LITERAL_HEAD + NO_CONVENTIONS + "\n" + LITERAL_TAIL

PREDICTIVE_INTRO = (
    """You will read one entry from the US FDA drug-shortage list and forecast \
when this presentation will recover. Recovered means that the list shows the presentation as \
available again, or the shortage as resolved for it. If it is discontinued instead, it has not \
recovered.

Forecast as if today were the date of update: use only what could have been known on that day. \
The entry's own estimate may be optimistic, pessimistic or out of date, so give your own forecast \
rather than repeating it.

"""
    + ENTRY_BLOCK
    + "\n"
)

TRACK_BLOCK = """
Track record: how the estimates in earlier entries of this list turned out (entries updated \
from $track_since to $track_through), by the form of the stated time. Shares are of the \
statements whose outcome is known.

$slip_table

This entry's form: $form

Resolved earlier entries (their outcomes are known; none of them is this entry):
$examples
"""

QUESTIONS = """
Answer these three questions. All times are counted from the date of update, $date_of_update. \
$horizon_note

1. p_by_horizon_a: the probability that the presentation has recovered on or before $horizon_a.
2. p_by_horizon_b: the probability that the presentation has recovered on or before $horizon_b.
3. days_to_recovery: quantiles of the number of days from the date of update to recovery. Each \
is a whole number from 0 to 365, where 365 means 365 days or more, including never. q10 is the \
number of days within which you give recovery a 10% chance, q50 is the median, and q80, q90 and \
q95 follow the same rule. They must not decrease from q10 to q95.

Reply with one JSON object and nothing else, in this form, where each P is a probability between \
0 and 1 and each D a whole number of days:
{"p_by_horizon_a": P, "p_by_horizon_b": P, "days_to_recovery": {"q10": D, "q50": D, "q80": D, \
"q90": D, "q95": D}}"""

PREDICTIVE_TEXT = PREDICTIVE_INTRO + QUESTIONS
PREDICTIVE_TRACK_TEXT = PREDICTIVE_INTRO + TRACK_BLOCK + QUESTIONS

PROBE_TEXT = (
    """A drug presentation was on the US FDA drug-shortage list on $date_of_update. You \
are not shown the list entry. Estimate when this presentation recovered, meaning when the list \
next showed it as available or the shortage as resolved for it; if it was discontinued instead, \
it did not recover. Give your best estimate, using anything you know.

- Drug: $generic_name
- Company: $company_name
- Presentation: $presentation
- Date of update: $date_of_update
"""
    + QUESTIONS
)

HORIZON_NOTES = {
    "stated_end": (
        "Horizon A, $horizon_a, is the end of the period the entry states; horizon B, "
        "$horizon_b, is 90 days after it."
    ),
    "fallback": (
        "The entry states no period, so horizon A, $horizon_a, is 90 days after the date of "
        "update, and horizon B, $horizon_b, is 180 days after it."
    ),
    "probe": "Horizon A is $horizon_a and horizon B is $horizon_b.",
}

REPAIR_TEXT = """$prompt

Your previous reply was:
<<<
$previous
>>>

It could not be used: $errors

Reply again with one JSON object in the form asked for above, and nothing else."""
REPAIR_PREVIOUS_CHARS = 2000

# ---------------------------------------------------------------------------------------------
# Output schemas (JSON Schema 2020-12 subset, validated by :func:`validate`)
# ---------------------------------------------------------------------------------------------

STATEMENT_TYPES = ("recovery", "next_delivery", "depletion", "discontinuation", "none")
CERTAINTY_CLASSES = ("asserted", "estimated", "undetermined", "no_statement")
_ISO_DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}

LITERAL_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "literal reading",
    "type": "object",
    "additionalProperties": False,
    "required": ["statement_type", "interval", "certainty", "stale", "quote"],
    "properties": {
        "statement_type": {"enum": list(STATEMENT_TYPES)},
        "interval": {
            "anyOf": [
                {"const": "ABSTAIN"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["start", "end"],
                    "properties": {"start": _ISO_DATE, "end": _ISO_DATE},
                },
            ]
        },
        "certainty": {"enum": list(CERTAINTY_CLASSES)},
        "stale": {"type": "boolean"},
        "quote": {"type": "string", "maxLength": 400},
    },
}

_PROBABILITY = {"type": "number", "minimum": 0, "maximum": 1}
_DAYS = {"type": "integer", "minimum": 0, "maximum": CAP_DAYS}

PREDICTIVE_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "predictive reading",
    "type": "object",
    "additionalProperties": False,
    "required": ["p_by_horizon_a", "p_by_horizon_b", "days_to_recovery"],
    "properties": {
        "p_by_horizon_a": _PROBABILITY,
        "p_by_horizon_b": _PROBABILITY,
        "days_to_recovery": {
            "type": "object",
            "additionalProperties": False,
            "required": list(QUANTILE_KEYS),
            "properties": dict.fromkeys(QUANTILE_KEYS, _DAYS),
        },
    },
}

SCHEMAS = {"literal": LITERAL_SCHEMA, "predictive": PREDICTIVE_SCHEMA}


@dataclass(frozen=True)
class PromptTemplate:
    """One frozen prompt. The SHA covers everything that shapes a call to it: the text, its fixed
    fragments, the output schema, the repair prompt, and canary renderings (plain, and masked
    with a date shift), so a change to the renderer or the masker also moves the pin."""

    id: str
    kind: str
    """``literal`` or ``predictive`` (selects the schema and the semantic checks)."""
    text: str
    horizon_notes: tuple[str, ...] = ()
    needs_track: bool = False

    @cached_property
    def sha256(self) -> str:
        masker = NameMasker()
        material = {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "horizon_notes": {k: HORIZON_NOTES[k] for k in self.horizon_notes},
            "schema": SCHEMAS[self.kind],
            "repair": REPAIR_TEXT,
            "canary": render_prompt(self, CANARY_ITEM, CANARY_TRACK),
            "canary_masked": render_prompt(
                self, prepare(CANARY_ITEM, masker, 2), transform_track(CANARY_TRACK, masker, 2)
            ),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


CANARY_ITEM = ReadItem(
    item_id="canary",
    generic_name="Anagrelide Hydrochloride Capsules",
    company_name="Teva Pharmaceuticals USA, Inc.",
    presentation="0.5 MG 100 Capsules (NDC 0172-5241-60)",
    date_of_update="2020-03-17",
    type_of_update="Reverified",
    availability_information="Backordered. Next release Dec-20; 2Q21 at the latest.",
    related_information="Expected recovery April 2020 (lot 2000 mg; FY21). Teva is working on it.",
    reason_for_shortage="Demand increase for the drug",
    stated_end="2020-04-30",
    form="a month and year",
)
"""A fixed item (a real 2020 text with extra date forms) whose renderings are part of each pin."""
CANARY_TRACK = TrackRecord(
    through="2022-12-31",
    slip_table=(
        SlipRow("a month and year", 120, 0.31, 0.62, 140),
        SlipRow("TBD or unknown", 80, None, None, None),
    ),
    examples=(
        ResolvedExample(
            date_of_update="2021-03-04",
            outcome="recovered",
            availability_information="Backordered. Next release April 2021.",
            type_of_update="Revised",
            stated_end="2021-04-30",
            recovered_after="2021-06-10",
            recovered_by="2021-06-18",
        ),
        ResolvedExample(
            date_of_update="2020-05-01",
            outcome="not_recovered",
            related_information="Next shipment TBD",
        ),
        ResolvedExample(
            date_of_update="2020-06-01", outcome="recovered", recovered_by="2020-08-01"
        ),
        ResolvedExample(date_of_update="2020-07-01", outcome="discontinued"),
    ),
)


TEMPLATES: dict[str, PromptTemplate] = {
    t.id: t
    for t in (
        PromptTemplate("literal-v1", "literal", LITERAL_TEXT),
        PromptTemplate("literal-free-v1", "literal", LITERAL_FREE_TEXT),
        PromptTemplate("predictive-v1", "predictive", PREDICTIVE_TEXT, ("stated_end", "fallback")),
        PromptTemplate(
            "predictive-track-v1",
            "predictive",
            PREDICTIVE_TRACK_TEXT,
            ("stated_end", "fallback"),
            needs_track=True,
        ),
        PromptTemplate("probe-v1", "predictive", PROBE_TEXT, ("probe",)),
    )
}

FROZEN_SHA256 = {
    "literal-v1": "a24ca65e42b092efdb77ab1973c30dce404a3c0dc096ede958ce2a8934c7b9de",
    "literal-free-v1": "429d13aaba645e6dd6c9b5b9846a41f733edf10f36afce46864e2daab384b9c8",
    "predictive-v1": "12ab562f353ff5d6296dfaaeae3ce89972447bf5c3d538ef0244e19cf6e546cc",
    "predictive-track-v1": "ee0d22ca9783f3dc755d5b7749203643eb14edecafb4236aea04b183921e02d6",
    "probe-v1": "2d16caf9a18c1fd35ad37a9f37ac51298e1d77b6d98d48019657e101ddcbdcca",
}
"""Pinned template digests. Changing a prompt means a new template id, not an edit."""


def check_frozen() -> None:
    changed = [t.id for t in TEMPLATES.values() if FROZEN_SHA256.get(t.id) != t.sha256]
    if changed:
        raise RuntimeError(f"templates changed without a new pin: {changed}")


# ---------------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------------


def _one_line(value: str) -> str:
    return " ".join(str(value or "").split())


def _quoted(value: str) -> str:
    text = _one_line(value)
    return f'"{text}"' if text else "(blank)"


def _plain(value: str) -> str:
    return _one_line(value) or "(blank)"


def horizons(item: ReadItem) -> tuple[date, date, str]:
    """Horizons A and B of the forecast questions, and the rule that set them."""
    if item.stated_end:
        end = parse_date(item.stated_end)
        return end, end + HORIZON_B_OFFSET, "stated_end"
    dou = parse_date(item.date_of_update)
    return dou + FALLBACK_HORIZONS[0], dou + FALLBACK_HORIZONS[1], "fallback"


def _entry_fields(item: ReadItem) -> dict[str, str]:
    return {
        "generic_name": _plain(item.generic_name),
        "company_name": _plain(item.company_name),
        "presentation": _plain(item.presentation),
        "type_of_update": _plain(item.type_of_update),
        "date_of_update": parse_date(item.date_of_update).isoformat(),
        "availability_information": _quoted(item.availability_information),
        "related_information": _quoted(item.related_information),
        "reason_for_shortage": _quoted(item.reason_for_shortage),
    }


def _share(value: float | None) -> str:
    return "n/a" if value is None else f"{round(100 * value)}%"


def render_slip_table(rows: Sequence[SlipRow]) -> str:
    lines = [
        "| form | statements | recovered by the stated end | recovered by 90 days after the "
        "stated end | median days from update to recovery |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        median = (
            "n/a" if r.median_days_to_recovery is None else str(round(r.median_days_to_recovery))
        )
        lines.append(
            f"| {_one_line(r.form)} | {r.statements} | {_share(r.share_by_stated_end)} | "
            f"{_share(r.share_by_stated_end_90)} | {median} |"
        )
    return "\n".join(lines)


def _outcome_text(ex: ResolvedExample) -> str:
    dou = parse_date(ex.date_of_update)
    if ex.outcome == "discontinued":
        return "discontinued without recovering."
    if ex.outcome == "not_recovered":
        return f"not recovered within {CAP_DAYS} days of the update."
    by = parse_date(ex.recovered_by or "")
    if ex.recovered_after:
        after = parse_date(ex.recovered_after)
        return (
            f"recovered between {after.isoformat()} and {by.isoformat()}, "
            f"{(after - dou).days} to {(by - dou).days} days after the update."
        )
    return f"recovered by {by.isoformat()}, within {(by - dou).days} days of the update."


def render_examples(examples: Sequence[ResolvedExample]) -> str:
    lines = []
    for n, ex in enumerate(examples, start=1):
        stated = parse_date(ex.stated_end).isoformat() if ex.stated_end else "none stated"
        lines += [
            f"{n}. Date of update: {parse_date(ex.date_of_update).isoformat()}",
            f"   Type of update: {_plain(ex.type_of_update)}",
            f"   Availability information: {_quoted(ex.availability_information)}",
            f"   Related information: {_quoted(ex.related_information)}",
            f"   Stated end: {stated}",
            f"   Outcome: {_outcome_text(ex)}",
        ]
    return "\n".join(lines) if lines else "(none)"


def render_prompt(
    template: PromptTemplate, item: ReadItem, track: TrackRecord | None = None
) -> str:
    """The exact text sent for one item (already masked or shifted, if at all)."""
    fields = _entry_fields(item)
    if template.kind == "literal":
        return string.Template(template.text).substitute(fields)
    a, b, rule = horizons(item)
    note_key = "probe" if "probe" in template.horizon_notes else rule
    marks = {"horizon_a": a.isoformat(), "horizon_b": b.isoformat()}
    fields |= marks | {"horizon_note": string.Template(HORIZON_NOTES[note_key]).substitute(marks)}
    if template.needs_track:
        if track is None:
            raise ValueError(f"{template.id} needs a track record")
        if len(track.examples) > MAX_EXAMPLES:
            raise ValueError(f"at most {MAX_EXAMPLES} examples, got {len(track.examples)}")
        fields |= {
            "track_since": parse_date(track.since).isoformat(),
            "track_through": parse_date(track.through).isoformat(),
            "slip_table": render_slip_table(track.slip_table),
            "form": _plain(item.form or "unclassified"),
            "examples": render_examples(track.examples),
        }
    return string.Template(template.text).substitute(fields)


def render_repair(prompt: str, previous: str, errors: Sequence[str]) -> str:
    shown = previous if len(previous) <= REPAIR_PREVIOUS_CHARS else previous[:REPAIR_PREVIOUS_CHARS]
    return string.Template(REPAIR_TEXT).substitute(
        prompt=prompt, previous=shown or "(empty)", errors="; ".join(errors[:6])
    )


# ---------------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------------


def _is_type(value: Any, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if not math.isfinite(value):
        return False
    return kind == "number" or (kind == "integer" and float(value).is_integer())


def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Errors of ``value`` against the schema subset used here (empty when valid)."""
    if "anyOf" in schema:
        branches = [validate(value, s, path) for s in schema["anyOf"]]
        if all(branches):
            return [f"{path}: matches no allowed form ({' / '.join(b[0] for b in branches)})"]
        return []
    if "const" in schema and value != schema["const"]:
        return [f"{path}: must be {schema['const']!r}"]
    if "enum" in schema and (not isinstance(value, str) or value not in schema["enum"]):
        return [f"{path}: must be one of {schema['enum']}"]
    kind = schema.get("type")
    if kind is not None and not _is_type(value, kind):
        return [f"{path}: must be of type {kind}"]
    errors: list[str] = []
    if isinstance(value, dict):
        props = schema.get("properties", {})
        errors += [
            f"{path}: missing {key!r}" for key in schema.get("required", ()) if key not in value
        ]
        if schema.get("additionalProperties") is False:
            errors += [f"{path}: unexpected key {key!r}" for key in value if key not in props]
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, f"{path}.{key}")
    elif isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if len(value) > schema.get("maxLength", math.inf):
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
    elif _is_type(value, "number"):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            errors.append(
                f"{path}: {value} outside [{schema.get('minimum')}, {schema.get('maximum')}]"
            )
    return errors


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"```(?:json)?", re.I)


def extract_json(text: str) -> tuple[list[dict], list[str]]:
    """Every top-level JSON object in a reply, and warnings about what surrounded them."""
    cleaned = _FENCE.sub("", _THINK.sub("", text)).strip()
    decoder = json.JSONDecoder()
    found: list[tuple[int, int, dict]] = []
    pos = cleaned.find("{")
    while pos != -1:
        try:
            obj, end = decoder.raw_decode(cleaned, pos)
        except json.JSONDecodeError:
            pos = cleaned.find("{", pos + 1)
            continue
        if isinstance(obj, dict):
            found.append((pos, end, obj))
            pos = cleaned.find("{", end)
        else:
            pos = cleaned.find("{", pos + 1)
    if not found:
        return [], []
    warnings = []
    if cleaned[: found[0][0]].strip() or cleaned[found[-1][1] :].strip():
        warnings.append("text_outside_json")
    if len(found) > 1:
        warnings.append("several_json_objects")
    return [obj for _, _, obj in found], warnings


@dataclass
class ParseResult:
    reading: dict | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.reading is not None and not self.errors


def _literal_checks(reading: dict, date_of_update: date | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    interval = reading["interval"]
    if isinstance(interval, dict):
        try:
            start, end = date.fromisoformat(interval["start"]), date.fromisoformat(interval["end"])
        except ValueError as exc:
            return [f"$.interval: not a calendar date ({exc})"], warnings
        if start > end:
            errors.append("$.interval: start is after end")
        if reading["statement_type"] == "none":
            warnings.append("interval_without_statement")
        if reading["certainty"] == "undetermined":
            warnings.append("interval_for_undetermined")
        if date_of_update is not None and reading["stale"] != (end < date_of_update):
            warnings.append("stale_flag_disagrees_with_interval")
    elif reading["stale"]:
        warnings.append("stale_without_interval")
    if (reading["statement_type"] == "none") != (reading["certainty"] == "no_statement"):
        warnings.append("no_statement_mismatch")
    return errors, warnings


def _predictive_checks(reading: dict) -> tuple[list[str], list[str]]:
    q = reading["days_to_recovery"]
    values = [int(q[k]) for k in QUANTILE_KEYS]
    reading["days_to_recovery"] = dict(zip(QUANTILE_KEYS, values, strict=True))
    errors = []
    if any(b < a for a, b in pairwise(values)):
        errors.append("$.days_to_recovery: quantiles decrease")
    warnings = []
    if reading["p_by_horizon_b"] < reading["p_by_horizon_a"]:
        warnings.append("p_by_horizon_b_below_a")
    return errors, warnings


def parse_reading(text: str, kind: str, *, date_of_update: date | None = None) -> ParseResult:
    """Strict parse: one JSON object that passes the kind's schema and semantic checks."""
    objects, warnings = extract_json(text)
    if not objects:
        return ParseResult(None, ["no JSON object found"], warnings)
    obj = objects[0]
    if any(other != obj for other in objects[1:]):
        return ParseResult(None, ["several different JSON objects"], warnings)
    errors = validate(obj, SCHEMAS[kind])
    if errors:
        return ParseResult(None, errors, warnings)
    checks = _literal_checks(obj, date_of_update) if kind == "literal" else _predictive_checks(obj)
    errors, more = checks
    return ParseResult(None if errors else obj, errors, warnings + more)


# ---------------------------------------------------------------------------------------------
# Leakage controls: fictitious names and whole-year date shifts
# ---------------------------------------------------------------------------------------------


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


FORM_WORDS = _words(
    """injection injectable injections tablet tablets tab tabs capsule capsules cap caps oral
    solution solutions suspension suspensions for and with without in of extended release
    released delayed immediate modified er xr sr xl dr cr la usp nf powder cream ointment gel
    topical ophthalmic otic nasal spray inhalation inhaler aerosol emulsion liquid syrup elixir
    drops patch transdermal vial vials kit premix premixed bag bags vaginal rectal suppository
    suppositories lotion chewable disintegrating orally film coated concentrate infusion
    intravenous subcutaneous intramuscular single dose multiple preservative free plus sterile
    lyophilized pen prefilled syringe syringes cartridge auto injector system granules packet
    packets foam shampoo implant insert ring gum lozenge troche buffered dental water sodium
    potassium calcium magnesium hydrochloride hcl sulfate sulphate phosphate acetate citrate
    chloride bromide tartrate maleate mesylate succinate fumarate besylate lactate gluconate
    bicarbonate carbonate oxide hydroxide nitrate dihydrate monohydrate trihydrate anhydrous
    dextrose saline mg ml mcg type adult adults pediatric human combination strength regular
    concentrated only"""
)
SALT_WORDS = _words(
    """sodium potassium calcium magnesium hydrochloride hcl sulfate sulphate phosphate acetate
    citrate chloride bromide tartrate maleate mesylate succinate fumarate besylate lactate
    gluconate bicarbonate carbonate oxide hydroxide nitrate dextrose saline water"""
)
CORP_WORDS = _words(
    """pharma pharmaceutical pharmaceuticals pharmaceutica inc incorporated llc ltd limited corp
    corporation co company usa us laboratories laboratory labs lab holdings healthcare health
    medical products group gmbh ag sa plc lp llp the of and by mfd manufactured for distributed
    international global north america americas american biologics biosciences bio sciences
    therapeutics generics generic specialty division a an institutional pharmacy supply"""
)
_ONSETS = ("b", "d", "f", "k", "l", "m", "n", "p", "r", "s", "t", "v", "z", "br", "dr", "tr")
_VOWELS = ("a", "e", "i", "o", "u")
_CODAS = {
    "ingredient": ("zine", "dolex", "nide", "zol", "done", "trel"),
    "brand": ("ra", "xa", "vo", "lis"),
    "company": ("tex", "rora", "vanta", "niva", "dell"),
}
_WORD = re.compile(r"[A-Za-z]+")
_BRAND_MARK = re.compile(r"([A-Za-z][A-Za-z-]*)\s*[®™]")
_NDC_DASHED = re.compile(r"(?<![\d-])\d{4,5}-\d{3,4}-\d{1,2}(?![\d-])")
_NDC_PLAIN = re.compile(r"(\bNDC[#:\s]*)(\d{10,11})\b")
_NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)"
_UNITS = r"mcg|mg|µg|kg|g|meq|mmol|ml|cc|l|units?|iu"
_STRENGTH = re.compile(rf"(?<![\w.])((?:{_NUMBER}/)*{_NUMBER})(\s*)({_UNITS})(?![A-Za-z])", re.I)
"""An amount with a unit, or a slash chain of amounts ending in one ("1.25/1.25mg")."""
_PERCENT = re.compile(rf"(?<![\w.])((?:{_NUMBER}/)*{_NUMBER})(\s*)(%)")
_NUMBER_RE = re.compile(_NUMBER)
_CAPITALISED = re.compile(r"\b[A-Z][A-Za-z]{3,}\b")
PACKAGING_WORDS = _words(
    """bottle bottles count carton cartons box boxes pack packs blister blisters tray trays unit
    units ampul ampule ampules ampoule ampoules fliptop flip top luer lock needle needles pouch
    pouches amber clear white blue green yellow orange pink round oval scored strip strips glass
    plastic container containers package packages case cases each tube tubes jar jars canister
    dispenser applicator applicators device devices bulk hospital retail unit-dose unitdose
    sample samples label labeled vials syringes kits bags premixed pharmacy
    per total with without approximately january february march april may june july august
    september october november december discontinued available unavailable only new old
    formulation size sizes strengths presentation presentations product including contains
    containing note lot lots expiry expiration date dated short long latex natural rubber dye
    sugar alcohol color flavor flavored unflavored cherry grape strawberry mint vanilla lemon
    diluent reconstitution reconstituted nonsterile professional institutional"""
)
"""Common capitalised presentation words that are not brands (kept by the brand heuristic)."""
VOLUME_UNITS = frozenset({"ml", "l", "cc"})
STRENGTH_FACTORS = ("0.5", "2", "2.5", "4", "5")
"""Amounts (not volumes) of one generic are scaled by one of these, so "1 mg/4 mL (0.25 mg/mL)"
stays coherent and the relative strengths of a product family survive."""


def _digest(*parts: str) -> int:
    return int(hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest(), 16)


def _match_case(fake: str, original: str) -> str:
    if len(original) > 1 and original.isupper():
        return fake.upper()
    if original[:1].isupper():
        return fake.capitalize()
    return fake.lower()


class NameMasker:
    """Deterministic fictitious names. A fake depends only on the salt, the kind and the real
    word (never on which items came first), so masked prompts are reproducible and cacheable and
    masked revision threads stay linkable. Three syllables and a suffix give about three million
    words per kind, so two real words share a fake with odds of about one in three million."""

    def __init__(self, salt: str = "coling-mask-v1") -> None:
        self.salt = salt
        self._fake: dict[tuple[str, str], str] = {}

    def fake_word(self, real: str, kind: str) -> str:
        key = (kind, real.lower())
        if key not in self._fake:
            h = _digest(self.salt, kind, real.lower())
            syllables = "".join(
                _ONSETS[(h >> (16 * i)) % len(_ONSETS)]
                + _VOWELS[(h >> (16 * i + 8)) % len(_VOWELS)]
                for i in range(3)
            )
            coda = _CODAS[kind][(h >> 64) % len(_CODAS[kind])]
            self._fake[key] = (syllables + coda).capitalize()
        return self._fake[key]

    def _terms(self, item: ReadItem) -> dict[str, str]:
        """Every real token to replace, mapped to its fake."""
        terms: dict[str, str] = {}
        generic = [w for w in _WORD.findall(item.generic_name) if len(w) >= 3]
        ingredients = [w for w in generic if w.lower() not in FORM_WORDS]
        if not ingredients:  # e.g. "Sodium Chloride Injection": the salt is the identity
            ingredients = [w for w in generic if w.lower() in SALT_WORDS]
        for w in ingredients:
            terms[w.lower()] = self.fake_word(w, "ingredient")
        for w in _WORD.findall(item.company_name):
            if len(w) >= 3 and w.lower() not in CORP_WORDS:
                terms[w.lower()] = self.fake_word(w, "company")
        texts = (item.presentation, item.availability_information, item.related_information)
        for text in (item.generic_name, *texts):
            for w in _BRAND_MARK.findall(text):
                for part in _WORD.findall(w):
                    if len(part) >= 3 and part.lower() not in FORM_WORDS:
                        terms.setdefault(part.lower(), self.fake_word(part, "brand"))
        for w in _CAPITALISED.findall(item.presentation):  # heuristic: capitalised non-form words
            if w.lower() not in FORM_WORDS | CORP_WORDS | PACKAGING_WORDS:
                terms.setdefault(w.lower(), self.fake_word(w, "brand"))
        for extra in item.mask_terms:
            for part in _WORD.findall(extra):
                if len(part) >= 3:
                    terms.setdefault(part.lower(), self.fake_word(part, "brand"))
        company = [w for w in _WORD.findall(item.company_name) if w.lower() in terms]
        if len(company) >= 3:  # "BMS" for Bristol Myers Squibb
            initials = "".join(w[0] for w in company).lower()
            terms.setdefault(initials, "".join(terms[w.lower()][0] for w in company))
        return terms

    def _replace_terms(self, text: str, terms: dict[str, str]) -> str:
        if not text or not terms:
            return text
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r")\b",
            re.I,
        )
        return pattern.sub(lambda m: _match_case(terms[m.group(1).lower()], m.group(1)), text)

    def _fake_digits(self, code: str) -> str:
        """Same layout, new digits. Each hyphen segment is keyed by the segments before it, so
        one labeller code maps to one fake labeller code across items."""
        out = []
        for n, segment in enumerate(code.split("-")):
            h = _digest(self.salt, "ndc", *code.split("-")[: n + 1])
            out.append("".join(str((h >> (4 * i)) % 10) for i in range(len(segment))))
        return "-".join(out)

    def mask_ndc(self, text: str) -> str:
        text = _NDC_DASHED.sub(lambda m: self._fake_digits(m.group(0)), text)
        return _NDC_PLAIN.sub(lambda m: m.group(1) + self._fake_digits(m.group(2)), text)

    def strength_factor(self, generic_name: str) -> Decimal:
        h = _digest(self.salt, "strength", " ".join(generic_name.lower().split()))
        return Decimal(STRENGTH_FACTORS[h % len(STRENGTH_FACTORS)])

    @staticmethod
    def mask_strength(text: str, factor: Decimal, *, percent: bool) -> str:
        """Amounts with a mass or unit measure (and percentages, if ``percent``) times
        ``factor``; volumes are kept."""

        def scale(number: re.Match) -> str:
            return format((Decimal(number.group(0)) * factor).normalize(), "f")

        def one(m: re.Match) -> str:
            if m.group(3).lower() in VOLUME_UNITS:
                return m.group(0)
            return _NUMBER_RE.sub(scale, m.group(1)) + m.group(2) + m.group(3)

        text = _STRENGTH.sub(one, text)
        return _PERCENT.sub(one, text) if percent else text

    def mask_text(self, text: str, terms: dict[str, str], factor: Decimal, *, percent: bool) -> str:
        text = self._replace_terms(text, terms)
        return self.mask_strength(self.mask_ndc(text), factor, percent=percent)

    def mask_item(self, item: ReadItem) -> ReadItem:
        terms = self._terms(item)
        k = self.strength_factor(item.generic_name)
        return replace(
            item,
            generic_name=self.mask_text(item.generic_name, terms, k, percent=True),
            company_name=self._replace_terms(item.company_name, terms),
            presentation=self.mask_text(item.presentation, terms, k, percent=True),
            availability_information=self.mask_text(
                item.availability_information, terms, k, percent=False
            ),
            related_information=self.mask_text(item.related_information, terms, k, percent=False),
            reason_for_shortage=self._replace_terms(item.reason_for_shortage, terms),
            mask_terms=(),
        )

    def mask_example(self, ex: ResolvedExample) -> ResolvedExample:
        stub = ReadItem(
            item_id="example",
            generic_name=ex.generic_name,
            company_name=ex.company_name,
            presentation="",
            date_of_update=ex.date_of_update,
            availability_information=ex.availability_information,
            related_information=ex.related_information,
        )
        masked = self.mask_item(stub)
        return replace(
            ex,
            availability_information=masked.availability_information,
            related_information=masked.related_information,
            generic_name=masked.generic_name,
            company_name=masked.company_name,
        )


_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_DATES = re.compile(
    r"(?P<ndc>(?<![\d-])\d{4,5}-\d{3,4}-\d{1,2}(?![\d-])|\b\d{10,11}\b)"
    r"|(?P<iso>\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})\b)"
    r"|(?P<mdy>\b(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4}|\d{2})\b)"
    r"|(?P<year>(?<!\d)(?:19[89]\d|20[0-4]\d)(?!\d)(?!\s?(?:mg|mcg|ml|units?|iu|meq|g\b|%)))"
    r"|(?P<q2>\b(?:[1-4]Q|Q[1-4])\s?'?(?P<qy>\d{2})\b)"
    rf"|(?P<mon2>\b(?:{_MONTHS})\.?(?:-'?|\s?')(?P<my>\d{{2}})(?!\d))"
    r"|(?P<fy2>\bFY\s?'?(?P<fy>\d{2})\b)",
    re.I,
)


def shift_day(day: date, years: int) -> date:
    """``day`` moved by whole years; 29 February becomes 28 February in a common year."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _shift_iso(m: re.Match, years: int) -> str:
    try:
        day = date(int(m.group("iy")), int(m.group("im")), int(m.group("id")))
    except ValueError:
        return m.group(0)
    return shift_day(day, years).isoformat()


def _shift_mdy(m: re.Match, years: int) -> str:
    month, day, year = m.group("m"), m.group("d"), m.group("y")
    try:
        real = date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
    except ValueError:
        return m.group(0)
    moved = shift_day(real, years)
    year_text = str(moved.year) if len(year) == 4 else f"{moved.year % 100:02d}"
    return f"{month}/{moved.day:0{len(day)}d}/{year_text}"


def _shift_two_digit(m: re.Match, inner: str, years: int) -> str:
    whole, start = m.group(0), m.start()
    a, b = m.start(inner) - start, m.end(inner) - start
    return whole[:a] + f"{(int(whole[a:b]) + years) % 100:02d}" + whole[b:]


def shift_dates(text: str, years: int) -> str:
    """Every date and year in ``text`` moved by ``years`` whole years. NDC codes are left alone.

    Handles ISO and MM/DD/YY(YY) dates, four-digit years 1980 to 2049 (not when a unit such as
    "mg" follows), and two-digit years in "2Q20", "Q2 '20", "Dec-20", "Dec '20" and "FY20".
    "Aug 20" is read as a day and left alone. Weekday names are not adjusted.
    """
    if not years or not text:
        return text

    def sub(m: re.Match) -> str:
        if m.group("ndc"):
            return m.group(0)
        if m.group("iso"):
            return _shift_iso(m, years)
        if m.group("mdy"):
            return _shift_mdy(m, years)
        if m.group("year"):
            return str(int(m.group(0)) + years)
        for outer, inner in (("q2", "qy"), ("mon2", "my"), ("fy2", "fy")):
            if m.group(outer):
                return _shift_two_digit(m, inner, years)
        return m.group(0)

    return _DATES.sub(sub, text)


def shift_item(item: ReadItem, years: int) -> ReadItem:
    if not years:
        return item
    return replace(
        item,
        date_of_update=shift_day(parse_date(item.date_of_update), years).isoformat(),
        stated_end=(
            shift_day(parse_date(item.stated_end), years).isoformat() if item.stated_end else None
        ),
        **{
            name: shift_dates(getattr(item, name), years)
            for name in (
                "generic_name",
                "presentation",
                "availability_information",
                "related_information",
                "reason_for_shortage",
            )
        },
    )


def _shift_optional(value: str | None, years: int) -> str | None:
    return shift_day(parse_date(value), years).isoformat() if value else None


def transform_track(track: TrackRecord, masker: NameMasker | None, years: int) -> TrackRecord:
    """The track record under the same masking and shift as the items. The sealing check runs
    here, on the real dates, before anything is moved."""
    track.check()
    examples = []
    for ex in track.examples:
        ex = masker.mask_example(ex) if masker else ex
        if years:
            ex = replace(
                ex,
                date_of_update=shift_day(parse_date(ex.date_of_update), years).isoformat(),
                stated_end=_shift_optional(ex.stated_end, years),
                recovered_after=_shift_optional(ex.recovered_after, years),
                recovered_by=_shift_optional(ex.recovered_by, years),
                availability_information=shift_dates(ex.availability_information, years),
                related_information=shift_dates(ex.related_information, years),
            )
        examples.append(ex)
    moved = replace(track, examples=tuple(examples))
    if years:  # the period labels move too; ``check`` ran on the real dates already
        moved = replace(
            moved,
            since=shift_day(parse_date(track.since), years).isoformat(),
            through=shift_day(parse_date(track.through), years).isoformat(),
        )
    return moved


def prepare(item: ReadItem, masker: NameMasker | None, years: int) -> ReadItem:
    """Masking first (it may rewrite NDC digits), then the date shift."""
    return shift_item(masker.mask_item(item) if masker else item, years)


# ---------------------------------------------------------------------------------------------
# Cost estimation (no call)
# ---------------------------------------------------------------------------------------------

VISIBLE_OUTPUT_TOKENS = {"literal": (90, 180), "predictive": (70, 140)}
"""(typical, generous) visible answer length in tokens; a JSON answer in stages C and D ran at
60 to 90 tokens on every non-reasoning rung."""
REASONING_TOKENS = {"gemini-3.8-flash": (1700, 4700), "gpt-oss-20b": (1200, 2800)}
"""(median, 90th percentile) hidden reasoning billed as output, from the commitment study's
spend logs (billable output minus the visible answer, stages A to D, 2026-09-28)."""
REASONING_FALLBACK = {"gemini": (2000, 5000), "stepfun": (2000, 5000)}


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        return None
    return tiktoken.get_encoding("o200k_base")


def estimate_tokens(text: str) -> int:
    enc = _encoder()
    return len(enc.encode(text)) if enc is not None else max(1, math.ceil(len(text) / 4))


def token_method() -> str:
    return "tiktoken o200k_base" if _encoder() is not None else "characters / 4"


def output_tokens(model: str, kind: str, *, upper: bool) -> int:
    visible = VISIBLE_OUTPUT_TOKENS[kind][1 if upper else 0]
    provider = LADDER[model].provider
    reasoning = REASONING_TOKENS.get(model, REASONING_FALLBACK.get(provider, (0, 0)))
    return visible + reasoning[1 if upper else 0]


def usd(prompt_tokens: int, output: int, endpoint: EndpointConfig) -> float:
    return (
        prompt_tokens * endpoint.price_input_per_mtok + output * endpoint.price_output_per_mtok
    ) / 1_000_000.0


def projected_call_usd(prompt: str, model: str, kind: str, endpoint: EndpointConfig) -> float:
    """A deliberately generous price for one call, checked against the cap before sending it."""
    prompt_tokens = math.ceil(1.25 * estimate_tokens(prompt)) + 16
    return usd(prompt_tokens, output_tokens(model, kind, upper=True), endpoint)


# ---------------------------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------------------------


def decoding_for(temperature: float) -> DecodingConfig:
    """``det-v1`` at temperature 0 (the commitment study's label); ``temp<T>-v1`` otherwise."""
    if temperature < 0:
        raise ValueError("temperature must be non-negative")
    label = "det-v1" if temperature == 0 else f"temp{temperature:g}-v1"
    return DecodingConfig(label, float(temperature), None)


def call_state(template: PromptTemplate, item_id: str, sample: int, attempt: int) -> str:
    state = f"{template.id}@{template.sha256[:16]}#{item_id}#s{sample}"
    return f"{state}#a{attempt}" if attempt else state


def build_transport(
    model: str,
    *,
    spend_log: Path,
    spend_cap_usd: float,
    max_physical_calls: int,
    inner: Transport | None = None,
) -> tuple[EndpointConfig, GuardedTransport]:
    """The ladder rung behind the served-model check and the guard. ``inner`` replaces the live
    client (tests); otherwise the key is resolved here, at setup, by the endpoint config."""
    rung = LADDER[model]
    endpoint = rung.endpoint()
    if inner is None:
        inner = EchoCheckedClient(endpoint, rung.served_as, timeout=LIVE_TIMEOUT_S, max_retries=0)
    guard = GuardedTransport(
        inner=inner,
        endpoint=endpoint,
        spend_log=spend_log,
        spend_cap_usd=spend_cap_usd,
        max_physical_calls=max_physical_calls,
    )
    return endpoint, guard


@dataclass
class Reader:
    """Reads items with one model and one template: cache, projected cap check, one repair."""

    model: str
    template: PromptTemplate
    endpoint: EndpointConfig
    transport: GuardedTransport
    cache: DiskCache
    decoding: DecodingConfig
    track: TrackRecord | None = None
    masker: NameMasker | None = None
    shift_years: int = 0
    responses: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if FROZEN_SHA256.get(self.template.id) != self.template.sha256:
            raise RuntimeError(f"template {self.template.id!r} does not match its pin")
        if self.template.needs_track and self.track is None:
            raise ValueError(f"{self.template.id} needs a track record")
        self._track = (
            transform_track(self.track, self.masker, self.shift_years) if self.track else None
        )

    def prompt_for(self, item: ReadItem) -> str:
        return render_prompt(
            self.template, prepare(item, self.masker, self.shift_years), self._track
        )

    def _call(self, prompt: str, state: str) -> tuple[RawResponse, bool]:
        key = cache_key(
            model_id=self.endpoint.model_id,
            prompt=prompt,
            state=state,
            decoding_hash=self.decoding.decoding_hash,
        )
        payload = self.cache.get(key)
        if payload is not None:
            return RawResponse(
                text=payload["text"],
                prompt_tokens=payload["prompt_tokens"],
                completion_tokens=payload["completion_tokens"],
                total_tokens=payload["total_tokens"],
            ), True
        projected = projected_call_usd(prompt, self.model, self.template.kind, self.endpoint)
        cap = self.transport.spend_cap_usd
        if self.transport.spent_usd + projected > cap:
            raise SpendCapReached(
                f"recorded spend ${self.transport.spent_usd:.4f} plus this call's projected "
                f"${projected:.4f} would pass the ${cap:.2f} cap"
            )
        raw = self.transport.complete_metered(prompt, decoding=self.decoding)
        self.cache.put(key, raw)
        return raw, False

    def _attempt(self, item: ReadItem, sample: int, attempt: int, prompt: str) -> dict:
        raw, hit = self._call(prompt, call_state(self.template, item.item_id, sample, attempt))
        refused = raw.text == "" and raw.total_tokens == 0
        self.responses.append(
            {
                "item_id": item.item_id,
                "sample": sample,
                "attempt": attempt,
                "prompt_sha256": prompt_digest(prompt),
                "text": raw.text,
            }
        )
        return {
            "attempt": attempt,
            "prompt_sha256": prompt_digest(prompt),
            "cache_hit": hit,
            "refused": refused,
            "prompt_tokens": raw.prompt_tokens,
            "completion_tokens": raw.completion_tokens,
            "total_tokens": raw.total_tokens,
            "billable_output_tokens": raw.billable_output(self.endpoint),
            "usd": usd(raw.prompt_tokens, raw.billable_output(self.endpoint), self.endpoint),
            "_text": raw.text,
        }

    def _context_warnings(self, item: ReadItem) -> list[str]:
        if self.track is not None and not track_precedes(self.track, item):
            return ["track_record_not_before_item"]
        return []

    def read(self, item: ReadItem, sample: int = 0) -> dict:
        """One reading row: the parsed answer, its status, and what each attempt cost."""
        prompt = self.prompt_for(item)
        shown_dou = parse_date(prepare(item, None, self.shift_years).date_of_update)
        first = self._attempt(item, sample, 0, prompt)
        attempts = [first]
        parsed = parse_reading(first["_text"], self.template.kind, date_of_update=shown_dou)
        status = "ok" if parsed.ok else "refused" if first["refused"] else "failed"
        errors = list(parsed.errors)
        if status == "failed":
            repair_prompt = render_repair(prompt, first["_text"], parsed.errors)
            second = self._attempt(item, sample, 1, repair_prompt)
            attempts.append(second)
            parsed = parse_reading(second["_text"], self.template.kind, date_of_update=shown_dou)
            status = "repaired" if parsed.ok else "failed"
            errors += [f"repair: {e}" for e in parsed.errors]
        row = {
            "item_id": item.item_id,
            "period": item.period,
            "sample": sample,
            "model": self.model,
            "model_id": self.endpoint.model_id,
            "template": self.template.id,
            "template_sha256": self.template.sha256,
            "decoding": self.decoding.decoding_hash,
            "temperature": self.decoding.temperature,
            "mask_names": self.masker is not None,
            "shift_years": self.shift_years,
            "status": status,
            "reading": parsed.reading if parsed.ok else None,
            "errors": errors,
            "warnings": parsed.warnings + self._context_warnings(item),
            "attempts": [{k: v for k, v in a.items() if k != "_text"} for a in attempts],
        }
        if self.template.kind == "predictive":
            a, b, rule = horizons(item)
            row["horizons"] = {"a": a.isoformat(), "b": b.isoformat(), "rule": rule}
        elif parsed.ok and self.shift_years and isinstance(parsed.reading["interval"], dict):
            iv = parsed.reading["interval"]
            row["interval_unshifted"] = {
                k: shift_day(date.fromisoformat(iv[k]), -self.shift_years).isoformat()
                for k in ("start", "end")
            }
        return row


def read_items(
    reader: Reader, items: Sequence[ReadItem], *, samples: int = 1
) -> tuple[list[dict], str]:
    """Every item and sample, in order. Returns the rows and ``complete`` or ``aborted: ...``;
    rows read before a cap was reached are kept, and their answers stay cached."""
    rows: list[dict] = []
    try:
        for item in items:
            for sample in range(samples):
                rows.append(reader.read(item, sample))
    except (SpendCapReached, CallCapReached) as exc:
        return rows, f"aborted: {exc}"
    return rows, "complete"


# ---------------------------------------------------------------------------------------------
# Dry run, study spend and outputs
# ---------------------------------------------------------------------------------------------


def dry_run(
    items: Sequence[ReadItem],
    *,
    models: Sequence[str],
    template: PromptTemplate,
    track: TrackRecord | None,
    samples: int,
    temperature: float,
    mask_names: bool,
    shift_years: int,
    cache_dirs: dict[str, Path] | None = None,
) -> dict:
    """Render every prompt and price it from token counts. Sends nothing."""
    masker = NameMasker() if mask_names else None
    moved = transform_track(track, masker, shift_years) if track else None
    prompts = [render_prompt(template, prepare(i, masker, shift_years), moved) for i in items]
    prompt_tokens = [estimate_tokens(p) for p in prompts]
    decoding = decoding_for(temperature)
    per_model = {}
    for model in models:
        endpoint = LADDER[model].endpoint()
        cache = DiskCache(cache_dirs[model]) if cache_dirs and model in cache_dirs else None
        cached = 0
        typical = upper = 0.0
        for item, prompt, tokens in zip(items, prompts, prompt_tokens, strict=True):
            for sample in range(samples):
                if cache is not None:
                    state = call_state(template, item.item_id, sample, 0)
                    key = cache_key(
                        model_id=endpoint.model_id,
                        prompt=prompt,
                        state=state,
                        decoding_hash=decoding.decoding_hash,
                    )
                    if cache.get(key) is not None:
                        cached += 1
                        continue
                typical += usd(tokens, output_tokens(model, template.kind, upper=False), endpoint)
                upper += projected_call_usd(prompt, model, template.kind, endpoint)
        per_model[model] = {
            "price_date": endpoint.price_date,
            "usd_per_mtok": [endpoint.price_input_per_mtok, endpoint.price_output_per_mtok],
            "calls": len(items) * samples,
            "cached_calls": cached,
            "output_tokens_per_call": [
                output_tokens(model, template.kind, upper=False),
                output_tokens(model, template.kind, upper=True),
            ],
            "usd_typical": round(typical, 4),
            "usd_upper": round(upper, 4),
        }
    periods = [i.period for i in items]
    overlap = sum(1 for i in items if track is not None and not track_precedes(track, i))
    return {
        "items_not_after_track_record": overlap,
        "template": template.id,
        "template_sha256": template.sha256,
        "items": len(items),
        "items_by_period": {p: periods.count(p) for p in ("train", "test")},
        "samples": samples,
        "decoding": decoding.decoding_hash,
        "mask_names": mask_names,
        "shift_years": shift_years,
        "token_method": token_method(),
        "prompt_tokens": {
            "total": sum(prompt_tokens),
            "mean": round(sum(prompt_tokens) / max(1, len(prompt_tokens)), 1),
            "max": max(prompt_tokens, default=0),
        },
        "models": per_model,
        "usd_typical": round(sum(m["usd_typical"] for m in per_model.values()), 4),
        "usd_upper": round(sum(m["usd_upper"] for m in per_model.values()), 4),
        "note": "repair calls are not included; the upper figure prices every call generously",
    }


def recorded_spend(out_root: Path, *, exclude: str | None = None) -> float:
    """Dollars recorded in every run's spend log under ``out_root`` (optionally but one run)."""
    total = 0.0
    for log in sorted(out_root.glob("*/spend_log.jsonl")):
        if log.parent.name == exclude:
            continue
        for line in log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("event") == "call":
                total += float(row["usd"])
    return total


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def write_run(
    rows: Sequence[dict], reader: Reader, *, out_dir: Path, local_dir: Path, meta: dict
) -> dict:
    _write_jsonl(out_dir / "readings.jsonl", rows)
    _write_jsonl(local_dir / "responses.jsonl", reader.responses)
    statuses = [r["status"] for r in rows]
    manifest = {
        **meta,
        "template": reader.template.id,
        "template_sha256": reader.template.sha256,
        "ladder_rung": asdict(LADDER[reader.model]),
        "price_date": reader.endpoint.price_date,
        "readings": len(rows),
        "by_status": {s: statuses.count(s) for s in sorted(set(statuses))},
        "guard": reader.transport.stats(),
        "readings_sha256": _sha256_file(out_dir / "readings.jsonl"),
    }
    (out_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


# ---------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.read", description=__doc__)
    ap.add_argument("--items", type=Path, help="JSON Lines, one statement event per line")
    ap.add_argument("--template", choices=sorted(TEMPLATES), default="literal-v1")
    ap.add_argument("--model", action="append", choices=sorted(LADDER), help="repeatable (dry run)")
    ap.add_argument("--track-record", type=Path, help="needed by predictive-track-v1")
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--mask-names", action="store_true")
    ap.add_argument("--shift-years", type=int, default=0)
    ap.add_argument("--limit", type=int, help="read only the first N items")
    ap.add_argument("--dry-run", action="store_true", help="render and price; no call")
    ap.add_argument("--show", type=int, default=0, help="dry run: print the first N prompts")
    ap.add_argument("--print-schemas", action="store_true")
    ap.add_argument("--run-name", help="one model, template and condition per run name")
    ap.add_argument(
        "--spend-cap-usd", type=float, help="cumulative for the run: earlier invocations count"
    )
    ap.add_argument(
        "--study-cap-usd",
        type=float,
        default=STUDY_CAP_USD,
        help="other runs' recorded spend plus this run's cap must fit in it",
    )
    ap.add_argument("--max-physical-calls", type=int, default=20000)
    ap.add_argument("--allow-live", action="store_true")
    ap.add_argument("--allow-test-items", action="store_true", help="only after registration")
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--local-root", type=Path, default=LOCAL_ROOT)
    return ap


def _check_args(args: argparse.Namespace, items: Sequence[ReadItem]) -> None:
    if args.samples < 1:
        raise SystemExit("--samples must be at least 1")
    if args.samples > 1 and args.temperature == 0:
        raise SystemExit("several samples need --temperature above 0")
    if args.dry_run:
        return
    if len(args.model) != 1:
        raise SystemExit("a live run reads with exactly one --model")
    if not args.allow_live:
        raise SystemExit("this makes paid calls; pass --allow-live (or use --dry-run)")
    if not args.run_name or not _RUN_NAME.match(args.run_name):
        raise SystemExit("--run-name: lowercase letters, digits, '.', '-' or '_'")
    if args.spend_cap_usd is None or args.spend_cap_usd <= 0:
        raise SystemExit("a live run needs a positive --spend-cap-usd")
    tests = sum(1 for i in items if i.period == "test")
    if tests and not args.allow_test_items:
        raise SystemExit(
            f"{tests} items are in the test period; read them only after the study is registered "
            "(--allow-test-items)"
        )


IDENTITY_KEYS = ("model", "template", "temperature", "mask_names", "shift_years")


def _check_run_identity(out_dir: Path, invocation: dict) -> None:
    """A run name keeps one model, template and condition, so its cap and cache stay meaningful."""
    log = out_dir / "invocations.jsonl"
    if not log.is_file():
        return
    lines = log.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0]) if lines else {}
    clash = {
        k: (first.get(k), invocation[k]) for k in IDENTITY_KEYS if first.get(k) != invocation[k]
    }
    if clash:
        raise SystemExit(f"run {out_dir.name!r} was started with other settings: {clash}")


def _live(args: argparse.Namespace, items: Sequence[ReadItem], track: TrackRecord | None) -> int:
    model = args.model[0]
    out_dir, local_dir = args.out_root / args.run_name, args.local_root / args.run_name
    _check_run_identity(
        out_dir,
        {
            "model": model,
            "template": args.template,
            "temperature": args.temperature,
            "mask_names": args.mask_names,
            "shift_years": args.shift_years,
        },
    )
    others = recorded_spend(args.out_root, exclude=args.run_name)
    if others + args.spend_cap_usd > args.study_cap_usd:
        raise SystemExit(
            f"other runs recorded ${others:.2f}; with this run's ${args.spend_cap_usd:.2f} cap the "
            f"study would pass its ${args.study_cap_usd:.2f} cap"
        )
    endpoint, guard = build_transport(
        model,
        spend_log=out_dir / "spend_log.jsonl",
        spend_cap_usd=args.spend_cap_usd,
        max_physical_calls=args.max_physical_calls,
    )
    reader = Reader(
        model=model,
        template=TEMPLATES[args.template],
        endpoint=endpoint,
        transport=guard,
        cache=DiskCache(local_dir / "cache"),
        decoding=decoding_for(args.temperature),
        track=track,
        masker=NameMasker() if args.mask_names else None,
        shift_years=args.shift_years,
    )
    invocation = {
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "template": args.template,
        "items_file": str(args.items),
        "items_sha256": _sha256_file(args.items),
        "items": len(items),
        "samples": args.samples,
        "temperature": args.temperature,
        "mask_names": args.mask_names,
        "shift_years": args.shift_years,
        "spend_cap_usd": args.spend_cap_usd,
        "study_spend_other_runs_usd": round(others, 6),
        "git_sha": _git("rev-parse", "HEAD"),
    }
    t0 = time.perf_counter()
    status = "error"
    try:
        rows, status = read_items(reader, items, samples=args.samples)
        meta = {
            "run_name": args.run_name,
            "status": status,
            "track_record": str(args.track_record) if args.track_record else None,
            "git": {"sha": _git("rev-parse", "HEAD"), "branch": _git("branch", "--show-current")},
            "python": platform.python_version(),
            **{k: invocation[k] for k in ("items_sha256", "samples", "temperature")},
            **{k: invocation[k] for k in ("mask_names", "shift_years", "spend_cap_usd")},
        }
        write_run(rows, reader, out_dir=out_dir, local_dir=local_dir, meta=meta)
    finally:
        invocation |= {
            "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "wall_seconds": round(time.perf_counter() - t0, 1),
            "status": status,
            "guard": guard.stats(),
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "invocations.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(invocation, sort_keys=True) + "\n")
    print(json.dumps(invocation, indent=2, sort_keys=True))
    return 0 if status == "complete" else 3


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.print_schemas:
        print(json.dumps(SCHEMAS, indent=2))
        return 0
    check_frozen()
    if args.items is None or not args.model:
        raise SystemExit("--items and --model are required")
    items = load_items(args.items)[: args.limit]
    _check_args(args, items)
    template = TEMPLATES[args.template]
    track = load_track_record(args.track_record) if args.track_record else None
    if template.needs_track and track is None:
        raise SystemExit(f"{template.id} needs --track-record")
    if not args.dry_run:
        return _live(args, items, track)
    masker = NameMasker() if args.mask_names else None
    moved = transform_track(track, masker, args.shift_years) if track else None
    for item in items[: args.show]:
        print(f"===== {item.item_id} ({item.period})")
        print(render_prompt(template, prepare(item, masker, args.shift_years), moved))
    cache_dirs = (
        {m: args.local_root / args.run_name / "cache" for m in args.model}
        if args.run_name
        else None
    )
    summary = dry_run(
        items,
        models=args.model,
        template=template,
        track=track,
        samples=args.samples,
        temperature=args.temperature,
        mask_names=args.mask_names,
        shift_years=args.shift_years,
        cache_dirs=cache_dirs,
    )
    summary["study_spend_recorded_usd"] = round(recorded_spend(args.out_root), 4)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
