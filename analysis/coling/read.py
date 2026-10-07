"""The language-model reading harness for the COLING 2027 study (E2 to E5): frozen prompts, strict
output schemas, a cached and spend-capped runner, a no-call dry run, and leakage masking.

A reader sees one FDA drug-shortage entry (a *statement event*: generic x company x text, dated by
its Date of Update) and answers one of the frozen prompt templates:

* ``literal-v1``: what the entry asserts. Statement type, the calendar interval its time refers
  to (anchored to the Date of Update, under written conventions) or ``ABSTAIN``, a certainty
  class, a stale flag and the quoted evidence. ``literal-free-v1`` is the convention-free
  secondary variant. Two sentences of these prompts wait for the annotation pilot
  (``PILOT_SENTENCES``); until they are settled the two templates cannot be run live.
* ``predictive-v1`` (condition a): what will happen. P(recovered by horizon A), P(recovered by
  horizon B) and quantiles (q10, q50, q80, q90, q95) of days from the Date of Update to recovery,
  capped at 365. Horizon A is the end of the stated period (``stated_end``, supplied by the
  dataset builder, so the scored events never depend on a model's own reading) and B is 90 days
  later; an entry with no stated period gets Date of Update + 90 and + 180 days, with a different
  frozen sentence.
* ``predictive-track-v1`` (condition b): the same, with the list's track record in context: a
  table of Turnbull shares by form and revision bucket, and up to 10 resolved training-period
  examples, both read from a track-record file (:func:`load_track_record`). Anything dated on or
  after the test start (2023-01-01) is refused, so no sealed outcome can reach a prompt.
* ``predictive-track-p1``, ``-p2`` and ``-p3``: three paraphrases of ``predictive-track-v1``, read
  on the paraphrase subset to measure prompt variance (PLAN section 5, E3). They show the same
  entry and the same track record and ask for the same answer in the same form, so the schema
  and the parser are the same; only the wording, the order, the labels and the place of the
  track record differ (``PARAPHRASE_TEXTS``).
* ``probe-v1``: the E4 no-notice probe. It shows the fields of ``PROBE_FIELDS`` only (drug,
  company, presentation, therapeutic category, initial posting date, date of update) and fixed
  horizons of 90 and 180 days. The stated end, the form, the revision bucket and every text field
  of the item are dropped before anything is rendered (:func:`probe_view`).

Every template is pinned by SHA-256 in ``FROZEN_SHA256`` (text, fixed fragments, output schema,
the repair prompt, and renderings of a canary item plain and masked with a date shift, so the
renderer and the masker are pinned too); the runner refuses to start on a mismatch.
``--print-pins`` lists every template id with its pin.

Answers are parsed strictly (:func:`parse_reading`): one JSON object, validated against the
kind's JSON Schema (``LITERAL_SCHEMA``, ``PREDICTIVE_SCHEMA``) plus semantic checks (real
calendar dates, start <= end, non-decreasing quantiles). Nothing is sorted or clipped. A failure
earns exactly one repair call, a distinct cached request that shows the model its answer and the
errors. A reading that still fails, and a refused request, carry a ``fallback`` flag in the
output row: ``abstain`` for a literal reading, ``base_rate`` for a predictive one (the evaluator
puts the base-rate predictor's output in its place).

Calls use the repository's shared machinery by import, unchanged: the model ladder
(:data:`analysis.commitment.endpoints.LADDER`), the served-model check
(:class:`~analysis.commitment.endpoints.EchoCheckedClient`), key resolution at runtime
(``EndpointConfig.resolve_key``; this module never reads a key), and
:class:`~analysis.real_content_pilot.transport.GuardedTransport` (retries, refusals, a spend
cap, ``spend_log.jsonl`` with token counts and dated dollar cost, thinking billed as output where
the endpoint says so). On top of that this module adds:

* its own table of the eight readers (``ROUTES``): model id, provider endpoint, precision and
  price. For an OpenRouter model the request names one provider endpoint with fallbacks off
  (:func:`provider_object`). A live run is refused while a route is ``UNSET`` and for any model
  outside the table;
* a record of who served each call (:class:`RouteCheckedClient`): the echoed model id and the
  serving provider are stored with every attempt, in the cache and in the output rows. A
  response from another model or another provider stops the run;
* one disk cache for the whole study (``<local-root>/cache``) keyed by model id, full prompt
  hash, template id and SHA, item id, sample index, repair attempt, decoding and route, so a
  rerun, a resumed run and a run under another name or shard are free;
* a *projected* spend check before every paid call: the call is refused if the run's recorded
  spend plus a conservative estimate of this call would pass the run's cap;
* a study ledger (``<out-root>/study_ledger.jsonl``): every live run declares its cap before its
  first call, and is refused when the caps and spend of the model's runs would pass the model's
  cap (``MODEL_CAPS_USD``, or the cap a logged amendment put in its place: it then holds for
  the model's later runs) or those of all runs would pass $200. All runs share one output root
  and one local root (:func:`check_roots`);
* two paid-call guards (:func:`paid_call_refusals`): a live run needs the git tag
  ``coling-registration`` among the ancestors of HEAD, and a live run on items of the test or
  late period also needs the tag ``coling-f1`` and ``--allow-test-items``. Dry runs and scripted
  clients are never blocked. The guards are checked on the command line and again where the
  live client is built (:func:`build_transport`), together with the run's entry in the ledger,
  so no flag and no other caller gets a paying client around them; git is asked with every
  ``GIT_*`` variable removed, so the environment cannot point the check at another repository.
  The tags are local ones: whether the registration was pushed cannot be checked offline.

Leakage controls (E4): :class:`NameMasker` replaces generic, brand and company names and NDC
digits with deterministic fictitious ones, and scales strengths by a per-generic factor (volumes
kept, so concentrations stay coherent), in the fields and in the free text; :func:`shift_dates`
shifts every date by whole years. Both are applied at render time to the
item and to the track record; the stored readings keep the real item id and horizons, and a
literal interval read under a shift is also stored shifted back.

Items are JSON Lines (or CSV), one statement event each, with keys ``item_id``,
``generic_name``, ``company_name``, ``presentation``, ``date_of_update`` (ISO or MM/DD/YYYY) and
optionally ``therapeutic_category``, ``initial_posting_date``, ``type_of_update``,
``availability_information``, ``related_information``, ``reason_for_shortage``, ``stated_end``,
``form``, ``revision`` (one of ``REVISION_BUCKETS``) and ``mask_terms`` (extra strings to mask).
The FDA column headers and the corpus builder's column names (``event_id``, ``event_date``,
``availability_text``, ``related_text``) are accepted as aliases; every other key, outcome fields
and Status included, is ignored and never reaches a prompt.

Outputs of a live run: ``<out-root>/<run>/`` holds ``readings.jsonl`` (parsed readings, one row
per item and sample), ``spend_log.jsonl``, ``invocations.jsonl`` and ``run_manifest.json`` (with
the hashes of the items file, of the track-record file and of this file, the route, and whether
every expected item and sample was read); ``<local-root>/`` (git-ignored) holds the cache and,
per run, ``responses.jsonl`` (raw text). Readings are model outputs, never outcomes, so nothing
here is sealed. :func:`collect_readings` gives an evaluator the set of item ids answered per
model and condition over every run and shard, or over the runs it names.

Usage (from the repository root)::

    # no call: render, count and price
    python -m analysis.coling.read --items items.jsonl --template literal-v1 \\
        --model llama-3.3-70b --model deepseek-v3 --dry-run [--show 2]
    # live (paid): one model per run; a run may be one shard of the items
    python -m analysis.coling.read --items items.jsonl --template predictive-track-v1 \\
        --track-record track.json --model deepseek-v3 --run-name e3-b-deepseek-v3.s0 \\
        --shard 0/4 --spend-cap-usd 2 --allow-live [--allow-test-items] \\
        [--samples 20 --temperature 1.0] [--mask-names] [--shift-years 4]
    # the same command with --declare-only in place of --allow-live writes the run's cap to the
    # ledger and calls nothing
    python -m analysis.coling.read --print-pins        # template ids and pins, for F1
    python -m analysis.coling.read --run-sheet --count e2=120 --count e3=2585 ... \\
        [--sheet-format md] [--price MODEL=IN,OUT] [--per-call-usd MODEL=USD]
    python -m analysis.coling.read --check-runs [--items expected.jsonl --template ID] \\
        [--run NAME ...]                              # only the runs of these names
    python -m analysis.coling.read --print-schemas
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import platform
import re
import string
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cached_property
from itertools import pairwise
from pathlib import Path
from typing import Any

from analysis.commitment.endpoints import LADDER, EchoCheckedClient, ServedModelMismatch
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
DEV_START = date(2021, 1, 1)
"""The fit split ends before this day; the dev split runs from it to the test start."""
TEST_START = date(2023, 1, 1)
"""Statements dated on or after this day are sealed: the test period, then the late period."""
LATE_START = date(2026, 1, 1)
SEALED_PERIODS = ("test", "late")
STUDY_SEED = 20261001
CAP_DAYS = 365
HORIZON_B_OFFSET = timedelta(days=90)
FALLBACK_HORIZONS = (timedelta(days=90), timedelta(days=180))
QUANTILE_KEYS = ("q10", "q50", "q80", "q90", "q95")
QUANTILE_LEVELS = (0.10, 0.50, 0.80, 0.90, 0.95)
MAX_EXAMPLES = 10
REVISION_BUCKETS = ("first", "second", "third or later")
"""Whether a statement is the first, the second, or the third or a later one of its thread
(``revision_index`` 0, 1, and 2 or more in the events table)."""
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
"""The eight readers of PLAN section 4; the first two are the primaries. A dry run may price any
ladder model, a live run only these (see ``ROUTES``)."""
PRIMARIES = STUDY_MODELS[:2]
STUDY_CAP_USD = 200.0
MODEL_CAPS_USD = {
    "gemini-3.8-flash": 110.0,
    "grok-4.20": 30.0,
    "deepseek-v3": 12.0,
    "llama-3.3-70b": 5.0,
    "qwen-2.5-7b": 3.0,
    "gemma-3-27b": 3.0,
    "gpt-oss-20b": 3.0,
    "gpt-4o-mini": 3.0,
}
"""Per-model caps in dollars, as in the budget table of PLAN section 9 (they sum to $169 and
leave a reserve of $31). The table is rebuilt at the real counts before registration
(``--run-sheet``); these figures change with it, in the same edit."""
REGISTRATION_TAG = "coling-registration"
F1_TAG = "coling-f1"
LEDGER_NAME = "study_ledger.jsonl"
ROOTS_ANCHOR_NAME = "coling-read-roots.json"
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
    "Therapeutic Category": "therapeutic_category",
    "Initial Posting Date": "initial_posting_date",
    "event_id": "item_id",  # analysis.coling.corpus statement events
    "event_date": "date_of_update",
    "availability_text": "availability_information",
    "related_text": "related_information",
}
"""Other names accepted for item fields: the FDA headers and the corpus builder's columns. Any
other column (outcome fields and Status included) is ignored and never reaches a prompt."""


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


def _date_text(value: Any) -> str:
    """An ISO date when ``value`` parses as one, the stripped text otherwise ("" when blank)."""
    text = _text(value).strip()
    if not text:
        return ""
    try:
        return parse_date(text).isoformat()
    except ValueError:
        return text


@dataclass(frozen=True)
class ReadItem:
    """One statement event as a reader sees it. Carries no outcome."""

    item_id: str
    generic_name: str
    company_name: str
    presentation: str
    date_of_update: str
    therapeutic_category: str = ""
    initial_posting_date: str = ""
    """When the drug was first posted on the list (ISO when it parses as a date)."""
    type_of_update: str = ""
    availability_information: str = ""
    related_information: str = ""
    reason_for_shortage: str = ""
    stated_end: str | None = None
    """End of the period the entry states (ISO), from the builder; horizon A of the forecasts."""
    form: str | None = None
    """The builder's form label (for example "a month and year"), shown with the track record."""
    revision: str | None = None
    """The builder's revision bucket (``REVISION_BUCKETS``), shown with the track record."""
    mask_terms: tuple[str, ...] = ()
    """Extra strings the name masker must replace (brand names it cannot detect)."""

    @classmethod
    def from_dict(cls, row: dict) -> ReadItem:
        data = {_ALIASES.get(k, k): v for k, v in row.items()}
        if not _text(data.get("item_id")) or not _text(data.get("date_of_update")):
            raise ValueError(f"an item needs item_id and date_of_update: {sorted(data)[:12]}")
        stated = _text(data.get("stated_end")) or None
        revision = _text(data.get("revision")) or None
        if revision is not None and revision not in REVISION_BUCKETS:
            raise ValueError(f"revision must be one of {REVISION_BUCKETS}: {revision!r}")
        return cls(
            item_id=str(data["item_id"]),
            generic_name=_text(data.get("generic_name")),
            company_name=_text(data.get("company_name")),
            presentation=_text(data.get("presentation")),
            date_of_update=parse_date(data["date_of_update"]).isoformat(),
            therapeutic_category=_text(data.get("therapeutic_category")),
            initial_posting_date=_date_text(data.get("initial_posting_date")),
            type_of_update=_text(data.get("type_of_update")),
            availability_information=_text(data.get("availability_information")),
            related_information=_text(data.get("related_information")),
            reason_for_shortage=_text(data.get("reason_for_shortage")),
            stated_end=parse_date(stated).isoformat() if stated else None,
            form=_text(data.get("form")) or None,
            revision=revision,
            mask_terms=_terms_tuple(data.get("mask_terms")),
        )

    @property
    def period(self) -> str:
        """``train`` (fit and dev), ``test`` or ``late``, by the Date of Update."""
        day = parse_date(self.date_of_update)
        return "late" if day >= LATE_START else "test" if day >= TEST_START else "train"


PROBE_FIELDS = (
    "item_id",
    "generic_name",
    "company_name",
    "presentation",
    "therapeutic_category",
    "initial_posting_date",
    "date_of_update",
    "mask_terms",
)
"""What the no-notice probe may use (PLAN section 5, E4): the identity of the presentation, the
two list fields the structured baseline also sees, and the statement date. ``mask_terms`` is never
shown; it only tells the masker which names to replace."""


def probe_view(item: ReadItem) -> ReadItem:
    """The item as the probe may see it: every field outside ``PROBE_FIELDS`` is reset, so no
    notice text, stated end, form or revision bucket can reach a probe prompt or its horizons."""
    return ReadItem(**{name: getattr(item, name) for name in PROBE_FIELDS})


TRACK_SCHEMA = "coling-track-record-v1"
TRACK_SPLITS = ("fit", "fit+dev")
TRACK_BASES = ("cell", "form", "all dated forms")
OUTCOMES = ("recovered", "not_recovered", "discontinued")


@dataclass(frozen=True)
class SlipRow:
    """One row of the track-record table: how the stated times of one form and one revision
    bucket turned out in the training period."""

    form: str
    revision: str
    statements: int
    """How many statements the row's figures rest on (the pooled number when ``basis`` is not
    ``cell``)."""
    basis: str
    """``cell`` (this form and revision bucket), ``form`` (every revision of the form) or ``all
    dated forms``: the smallest of the three with at least ``min_cell`` statements."""
    share_by_stated_end: float | None
    """Turnbull share recovered by the stated end; None (shown "n/a") for a form with no stated
    end."""
    share_by_stated_end_90: float | None
    median_days_to_recovery: float | None


@dataclass(frozen=True)
class ResolvedExample:
    """A resolved training-period entry shown in context. Recovery lies in (after, by]."""

    date_of_update: str
    outcome: str
    item_id: str = ""
    availability_information: str = ""
    related_information: str = ""
    type_of_update: str = ""
    stated_end: str | None = None
    recovered_after: str | None = None
    recovered_by: str | None = None
    followed_until: str | None = None
    """The last capture at which the presentation was still not recovered (the lower bound of
    its recovery date); a ``not_recovered`` example needs it 365 days or more after the update."""
    generic_name: str = ""
    company_name: str = ""
    form: str = ""
    revision: str = ""


@dataclass(frozen=True)
class TrackRecord:
    """The in-context track record of the list: a table of Turnbull shares by form and revision
    bucket, plus at most 10 resolved examples."""

    through: str
    slip_table: tuple[SlipRow, ...]
    examples: tuple[ResolvedExample, ...]
    since: str = "2019-10-01"
    split: str = "fit+dev"
    min_cell: int = 100
    sha256: str = ""
    """The sha256 of the file the record was read from ("" for a record built in memory)."""

    def errors(self) -> list[str]:
        """Everything wrong with the record, above all anything that could carry a test-period
        (sealed) outcome into a prompt."""
        found: list[str] = []
        if self.split not in TRACK_SPLITS:
            found.append(f"split must be one of {TRACK_SPLITS}: {self.split!r}")
        through, since = parse_date(self.through), parse_date(self.since)
        if through >= TEST_START:
            found.append(f"the track record must end before {TEST_START}: {self.through}")
        if self.split == "fit" and through >= DEV_START:
            found.append(f"a fit-split record must end before {DEV_START}: {self.through}")
        if since > through:
            found.append("since is after through")
        if len(self.examples) > MAX_EXAMPLES:
            found.append(f"at most {MAX_EXAMPLES} examples, got {len(self.examples)}")
        ids = [ex.item_id for ex in self.examples if ex.item_id]
        if len(set(ids)) != len(ids):
            found.append("example item ids must be unique")
        for n, ex in enumerate(self.examples, start=1):
            found += [f"example {n}: {e}" for e in _example_errors(ex, through)]
        cells = [(row.form, row.revision) for row in self.slip_table]
        if len(set(cells)) != len(cells):
            found.append("the table has two rows for one form and revision bucket")
        for row in self.slip_table:
            found += [f"row {row.form!r}, {row.revision!r}: {e}" for e in _row_errors(row, self)]
        return found

    def check(self) -> None:
        found = self.errors()
        if found:
            raise ValueError("track record refused: " + "; ".join(found))


def _example_errors(ex: ResolvedExample, through: date) -> list[str]:
    found: list[str] = []
    dou = parse_date(ex.date_of_update)
    if dou >= TEST_START:
        found.append(f"dated {ex.date_of_update}, in the test period")
    elif dou >= DEV_START:
        found.append(f"dated {ex.date_of_update}, outside the fit split (before {DEV_START})")
    elif dou > through:
        found.append(f"dated {ex.date_of_update}, after the record's last day")
    if ex.outcome not in OUTCOMES:
        found.append(f"outcome must be one of {OUTCOMES}: {ex.outcome!r}")
    if ex.outcome == "recovered" and not ex.recovered_by:
        found.append("a recovered example needs recovered_by")
    if ex.outcome != "recovered" and (ex.recovered_by or ex.recovered_after):
        found.append("only a recovered example has recovery dates")
    for name in ("recovered_after", "recovered_by", "followed_until"):
        value = getattr(ex, name)
        if value and parse_date(value) >= TEST_START:
            found.append(f"{name} {value} is in the test period")
    both = ex.recovered_after and ex.recovered_by
    if both and parse_date(ex.recovered_after) > parse_date(ex.recovered_by):
        found.append("recovered_after is later than recovered_by")
    if ex.recovered_by and parse_date(ex.recovered_by) < dou:
        found.append("recovered_by is before the update")
    if ex.outcome == "not_recovered":
        followed = parse_date(ex.followed_until).toordinal() if ex.followed_until else 0
        if followed - dou.toordinal() < CAP_DAYS:
            found.append(f"a not_recovered example needs {CAP_DAYS} days of follow-up")
    if ex.revision and ex.revision not in REVISION_BUCKETS:
        found.append(f"revision must be one of {REVISION_BUCKETS}: {ex.revision!r}")
    return found


def _row_errors(row: SlipRow, track: TrackRecord) -> list[str]:
    found: list[str] = []
    if row.revision not in REVISION_BUCKETS:
        found.append(f"revision must be one of {REVISION_BUCKETS}")
    if row.basis not in TRACK_BASES:
        found.append(f"basis must be one of {TRACK_BASES}")
    if isinstance(row.statements, bool) or not isinstance(row.statements, int):
        found.append("statements must be a whole number")
    elif row.statements < 1 or (row.basis == "cell" and row.statements < track.min_cell):
        found.append(f"a cell needs at least {track.min_cell} statements, a pooled row at least 1")
    shares = (row.share_by_stated_end, row.share_by_stated_end_90)
    if any(s is not None and not 0.0 <= s <= 1.0 for s in shares):
        found.append("share outside [0, 1]")
    elif None not in shares and shares[1] < shares[0]:
        found.append("the share by 90 days after the stated end is below the share by it")
    median = row.median_days_to_recovery
    if median is not None and not 0 <= median <= CAP_DAYS:
        found.append(f"median outside [0, {CAP_DAYS}]")
    return found


def track_precedes(track: TrackRecord, item: ReadItem) -> bool:
    """Whether the last statement behind the track record is dated before the item (always true
    for test-period items). A rule on statement dates: the outcomes of the fit record are
    followed to the train horizon, through the dev period (PLAN section 3)."""
    return parse_date(track.through) < parse_date(item.date_of_update)


def track_refusals(track: TrackRecord, items: Sequence[ReadItem]) -> list[str]:
    """Why a live run may not show this track record with these items (empty when it may).

    * The record must end before every item: a table that covers an item's own period would
      put statements of that period into its prompt. So a dev run needs the ``fit`` record
      (whose outcomes still run through the dev period: PLAN section 3).
    * Items of the test or late period are read with the record of the whole train period
      (``fit+dev``), as registered.

    A dry run is not refused; it counts the items the first rule would stop
    (``items_not_after_track_record``).
    """
    found = []
    early = sorted(i.item_id for i in items if not track_precedes(track, i))
    if early:
        found.append(
            f"{len(early)} items are dated on or before the track record's last day "
            f"({track.through}); the record must end before every item it is shown with: "
            f"{early[:5]}"
        )
    if track.split != "fit+dev" and any(i.period in SEALED_PERIODS for i in items):
        found.append(
            f"test- or late-period items are read with the fit+dev track record, not with the "
            f"{track.split!r} one"
        )
    return found


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


_TRACK_KEYS = {
    "schema": str,
    "split": str,
    "since": str,
    "through": str,
    "seed": int,
    "min_cell": int,
    "source": dict,
    "slip_table": list,
    "examples": list,
}
_ROW_KEYS = {f.name for f in fields(SlipRow)}
_ROW_SHARES = ("share_by_stated_end", "share_by_stated_end_90", "median_days_to_recovery")
_EXAMPLE_KEYS = {f.name for f in fields(ResolvedExample)}
_EXAMPLE_NEEDS = ("item_id", "date_of_update", "outcome")


def track_file_errors(data: Any) -> list[str]:
    """Schema errors of a parsed track-record file (see :func:`load_track_record`): a missing or
    unknown key, or a value of the wrong type, at the top level, in a table row or in an example.
    Unknown keys are errors, so no stray column (an outcome field, say) slips in unnoticed."""
    if not isinstance(data, dict):
        return ["the file must hold one JSON object"]
    found = [f"missing key {key!r}" for key in _TRACK_KEYS if key not in data]
    found += [f"unknown key {key!r}" for key in data if key not in _TRACK_KEYS]
    for key, kind in _TRACK_KEYS.items():
        value = data.get(key)
        if key in data and (not isinstance(value, kind) or isinstance(value, bool)):
            found.append(f"{key!r} must be of type {kind.__name__}")
    if found:
        return found
    if data["schema"] != TRACK_SCHEMA:
        found.append(f"schema must be {TRACK_SCHEMA!r}: {data['schema']!r}")
    if data["seed"] != STUDY_SEED:
        found.append(f"seed must be the study seed {STUDY_SEED}: {data['seed']}")
    if data["min_cell"] < 1:
        found.append("min_cell must be at least 1")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in data["source"].items()):
        found.append("source must map names to strings (file hashes and the like)")
    if not data["slip_table"]:
        found.append("slip_table is empty")
    for n, row in enumerate(data["slip_table"], start=1):
        found += [f"slip_table row {n}: {e}" for e in _record_errors(row, _ROW_KEYS, _ROW_KEYS)]
        if isinstance(row, dict):
            for key in _ROW_SHARES:
                value = row.get(key)
                if value is not None and (isinstance(value, bool) or not _is_type(value, "number")):
                    found.append(f"slip_table row {n}: {key!r} must be a number or null")
            if not isinstance(row.get("form"), str) or not row.get("form", "").strip():
                found.append(f"slip_table row {n}: 'form' must be a non-empty string")
    for n, ex in enumerate(data["examples"], start=1):
        found += [f"example {n}: {e}" for e in _record_errors(ex, _EXAMPLE_KEYS, _EXAMPLE_NEEDS)]
        if isinstance(ex, dict) and not all(v is None or isinstance(v, str) for v in ex.values()):
            found.append(f"example {n}: every value must be a string or null")
    return found


def _record_errors(record: Any, allowed: Iterable[str], needed: Iterable[str]) -> list[str]:
    if not isinstance(record, dict):
        return ["must be an object"]
    found = [f"missing key {key!r}" for key in needed if key not in record]
    return found + [f"unknown key {key!r}" for key in record if key not in set(allowed)]


def load_track_record(path: Path) -> TrackRecord:
    """Read and check a track-record file: the table and the seeded examples of condition (b).

    The file is one JSON object. Every key below is required unless marked optional; any other
    key is refused. Dates are ISO (YYYY-MM-DD)::

        {
          "schema": "coling-track-record-v1",
          "split": "fit" | "fit+dev",      # fit for the dev runs, fit+dev for the test runs
          "since": "2019-10-01",           # first and last statement date the record covers;
          "through": "2022-12-31",         #   before 2021-01-01 for "fit", before 2023-01-01 always
          "seed": 20261001,                # the seed of the example draw (the study seed)
          "min_cell": 100,                 # the smallest cell estimated on its own
          "source": {"outcomes_sha256": "...", "events_sha256": "...", "builder_sha256": "..."},
          "slip_table": [                  # one row per form and revision bucket, in print order
            {"form": "a month and year",
             "revision": "first" | "second" | "third or later",
             "statements": 412,            # statements behind the figures (pooled if not "cell")
             "basis": "cell" | "form" | "all dated forms",
             "share_by_stated_end": 0.31,      # Turnbull share recovered by the stated end,
             "share_by_stated_end_90": 0.62,   #   and by 90 days after it; null if no stated end
             "median_days_to_recovery": 140}   # Turnbull median, days from update; null if none
          ],
          "examples": [                    # at most 10, dated before 2021-01-01 (the fit
                                           #   split, for either record), drawn with the seed
            {"item_id": "S...", "date_of_update": "2020-03-04",
             "outcome": "recovered" | "not_recovered" | "discontinued",
             # optional:
             "type_of_update": "Revised", "availability_information": "...",
             "related_information": "...", "stated_end": "2020-04-30",
             "recovered_after": "2020-06-10", "recovered_by": "2020-06-18",  # recovered only
             "followed_until": "2022-10-06",  # not_recovered only: the last capture at which
                                              #   it was still not recovered, 365 days or more
                                              #   after the update
             "generic_name": "...", "company_name": "...",  # never shown; used by the name masker
             "form": "a month and year", "revision": "first"}  # never shown; the draw's strata
          ]
        }

    Beyond the schema (:func:`track_file_errors`), :meth:`TrackRecord.errors` refuses a record
    that ends in the test period, an example dated outside the fit split or after the record's
    last day, any recovery or follow-up date in the test period, a ``not_recovered`` example
    followed for less than 365 days, two rows for one cell, a ``cell`` row under ``min_cell``
    statements, and shares that are out of range or decrease. The sha256 of the file is kept on
    the record and written to the run manifest and to every reading row.
    """
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    found = track_file_errors(data)
    if found:
        raise ValueError(f"{path.name} is not a track-record file: " + "; ".join(found))
    track = TrackRecord(
        through=parse_date(data["through"]).isoformat(),
        since=parse_date(data["since"]).isoformat(),
        split=data["split"],
        min_cell=data["min_cell"],
        slip_table=tuple(SlipRow(**row) for row in data["slip_table"]),
        examples=tuple(ResolvedExample(**row) for row in data["examples"]),
        sha256=hashlib.sha256(raw).hexdigest(),
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
- Therapeutic category: $therapeutic_category
- Initial posting date: $initial_posting_date
- Type of update: $type_of_update
- Date of update: $date_of_update
- Availability information: $availability_information
- Related information: $related_information
- Reason for shortage: $reason_for_shortage"""
"""The entry as models and annotators see it. Status is not shown: it is the same on every
at-risk entry. Therapeutic category and Initial posting date are shown because the structured
baseline uses them."""

# PILOT PLACEHOLDERS ---------------------------------------------------------------------------
# Two sentences of the literal prompts were settled by the annotation pilot on 5 October 2026
# (AUDIT_GUIDE.md, appendix B, decisions D1 and D3). To fill one, replace its ``None`` below with the sentence
# (one line, no "$"), or with "" if the pilot decides that the prompt says nothing; then run
# ``python -m analysis.coling.read --print-pins`` and copy the new pins of ``literal-v1`` and
# ``literal-free-v1`` into ``FROZEN_SHA256``. Nothing else needs to change. While a sentence is
# ``None`` the templates that carry it are refused for live runs.
PILOT_SENTENCES: dict[str, str | None] = {
    # D1: the certainty class of a statement that gives no date and has no unknown marker.
    # Added as the last line of question 3 (certainty), in both literal templates.
    "D1": (
        "When the entry gives no date for the statement and does not say that the timing is "
        'unknown: answer "estimated" if it gives a vague time, such as "a few months", and '
        '"undetermined" if it gives no time at all, such as "as it is released".'
    ),
    # D3: how "until X" and "through X" are read. Added as a convention after the one on "by"
    # and "before", in literal-v1 only (literal-free-v1 states no conventions).
    "D3": (
        '"Until" or "through" a time: that time itself, read as above, for example "through '
        'February 2021" is the whole of February 2021.'
    ),
}
# ----------------------------------------------------------------------------------------------


def _pilot_line(decision: str, prefix: str) -> str:
    """The prompt line of a pilot sentence ("" while it is pending or settled as nothing)."""
    sentence = PILOT_SENTENCES[decision]
    if not sentence:
        return ""
    if "$" in sentence or "\n" in sentence:
        raise ValueError(f"pilot sentence {decision} must be one line with no '$'")
    return f"{prefix}{sentence.strip()}\n"


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

LITERAL_CERTAINTY = """
3. certainty: how the entry presents the timing of the chosen statement.
   - "asserted": stated plainly, for example "Next release April 2020".
   - "estimated": hedged, for example estimated, expected, anticipated, projected, approximately \
or tentative.
   - "undetermined": the entry says the timing is not known, for example TBD, unknown or no \
estimated date.
   - "no_statement": use this exactly when statement_type is "none".
"""

LITERAL_REST = """
4. stale: true if the interval ends before the date of update, meaning the entry repeats an \
estimate that had already passed when it was updated; otherwise false, including when interval \
is "ABSTAIN".

5. quote: the shortest exact words from the entry that your answer rests on, or "" if there are \
none.

Reply with one JSON object and nothing else, in this form (interval may instead be "ABSTAIN"):
{"statement_type": "...", "interval": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}, \
"certainty": "...", "stale": true or false, "quote": "..."}"""

LITERAL_TAIL = LITERAL_CERTAINTY + _pilot_line("D1", "   ") + LITERAL_REST

CONVENTIONS_FIRST = """   Conventions:
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
"""

CONVENTIONS_REST = """\
   - A relative time, counted from the date of update: "within N" or "up to N" is from the date \
of update to N later; "N to M", such as "4-6 weeks", is from N later to M later; a single "N" is \
N later, as both start and end. A week is 7 days and a month 30 days.
   - An exact date: that day, as both start and end.
   - A vague time with no number and no calendar name, such as "a few months", "soon" or "the \
near future": "ABSTAIN"."""

CONVENTIONS = CONVENTIONS_FIRST + _pilot_line("D3", "   - ") + CONVENTIONS_REST

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
Track record: how the times stated in earlier entries of this list turned out. It is the record \
of the whole list, all companies together, not of this entry's company. It covers entries \
updated from $track_since to $track_through.

The table has one row for each form of stated time and each revision bucket: whether the \
statement was the first one made for its presentation, the second, or the third or a later one. \
The two shares are Turnbull estimates of the share of statements whose presentation had \
recovered by the end of the stated time, and by 90 days after it. A Turnbull estimate allows for \
recovery dates that are known only to lie between two captures of the list. Basis says which \
statements a row's figures rest on: "cell" is the row's own form and revision bucket; where that \
had fewer than $min_cell statements, the figures are those of every revision of the form \
("form") or of every form with a stated time ("all dated forms"). In the last column, a median \
of 365 means 365 days or more, including never.

$slip_table

This entry's form: $form
This entry's revision bucket: $revision

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

# PARAPHRASES OF THE TRACK-RECORD PROMPT ---------------------------------------------------------
# Three paraphrases of ``predictive-track-v1`` (PLAN section 5, E3: prompt variance on the
# paraphrase subset). They vary the prompt and nothing else: each shows the same entry fields,
# the same track record and the same horizon sentence, asks for the same three quantities under
# the same names, and ends with the reply instruction of the original, so the schema, the parser
# and the repair prompt are those of ``predictive-track-v1``. What a paraphrase varies is the
# wording and the order of the instructions, the framing sentence, the section labels and where
# the track record stands (before or after the entry). None adds a fact, an example or a
# definition, and none drops one; the entry's form and revision bucket stay under the table.
# The field lines and the reply instruction are cut from the original's own constants, so they
# cannot drift apart from it.
_ENTRY_LABEL, _, ENTRY_FIELD_LINES = ENTRY_BLOCK.partition("\n")
"""The ten field lines of the entry, without the label line above them."""
REPLY_BLOCK = QUESTIONS[QUESTIONS.index("Reply with one JSON object") :]
"""The reply instruction and the JSON form: the output contract every predictive prompt ends
with, and what the repair prompt means by "the form asked for above"."""
if _ENTRY_LABEL != "Entry" or not ENTRY_FIELD_LINES.startswith("- Drug: $generic_name\n"):
    raise RuntimeError("ENTRY_BLOCK no longer starts with its label line and the Drug field")

PARAPHRASE_1_TEXT = (
    """Below is one entry from the US FDA drug-shortage list. Your task is to forecast when the \
presentation in this entry will recover. A presentation has recovered when the list shows it as \
available again, or shows the shortage as resolved for it. A presentation that is discontinued \
instead has not recovered.

Give your own forecast rather than repeating the entry's own estimate, which may be optimistic, \
pessimistic or out of date. Make the forecast as if the date of update were today, using only \
what could have been known on that day.

The entry:
"""
    + ENTRY_FIELD_LINES
    + """

Past record of the list: how the times stated in this list's earlier entries turned out. This \
is the record of the whole list, with all companies taken together; it is not the record of \
this entry's company. The entries it covers were updated from $track_since to $track_through.

The table has a row for every form of stated time in every revision bucket. The revision bucket \
says whether the statement was the first one made for its presentation, the second, or the third \
or a later one. The two shares are both Turnbull estimates: one is the share of statements whose \
presentation had recovered by the end of the stated time, the other the share whose presentation \
had recovered by 90 days after it. A Turnbull estimate allows for recovery dates that are known \
only to lie between two captures of the list. The basis column says which statements the figures \
of a row rest on: "cell" is the row's own form and revision bucket; where that had fewer than \
$min_cell statements, the figures are those of every revision of the form ("form") or of every \
form with a stated time ("all dated forms"). A median of 365 in the last column means 365 days \
or more, including never.

$slip_table

Form of this entry: $form
Revision bucket of this entry: $revision

Earlier entries that have been resolved (their outcomes are known, and none of them is this \
entry):
$examples

Now answer the three questions that follow. All times are counted from the date of update, \
$date_of_update. $horizon_note

1. p_by_horizon_a: the probability that the presentation has recovered on or before $horizon_a.
2. p_by_horizon_b: the probability that the presentation has recovered on or before $horizon_b.
3. days_to_recovery: quantiles of how many days pass from the date of update until recovery. \
Every quantile is a whole number from 0 to 365, and 365 stands for 365 days or more, including \
never. q10 is the number of days within which you put the chance of recovery at 10%, q50 is the \
median, and q80, q90 and q95 are set by the same rule. From q10 to q95 they must not decrease.

"""
    + REPLY_BLOCK
)
"""Paraphrase 1: the layout of the original (instructions, entry, track record, questions) in
other words. The framing sentence names a task, the two instruction sentences of the second
paragraph change places, and the labels are reworded. The two probability questions are those
of the original word for word."""

PARAPHRASE_2_TEXT = (
    """Act as a forecaster. You are shown the track record of the US FDA drug-shortage list and \
then one entry from that list, and you forecast when the presentation in that entry will recover.

Treat the entry's date of update as today: use only what could have been known on that day. The \
estimate that the entry itself gives may be optimistic, pessimistic or out of date, so make your \
own forecast instead of repeating it. "Recovered" means that the list shows the presentation as \
available again, or the shortage as resolved for it; a presentation that is discontinued instead \
has not recovered.

### Track record of the list

This section shows how the times stated in earlier entries of this list turned out. The record \
is of the whole list, all companies together, and not of the company in the entry to forecast. \
It covers entries updated from $track_since to $track_through.

How to read the table:
- Rows: one for each form of stated time and each revision bucket, that is, whether the \
statement was the first one made for its presentation, the second, or the third or a later one.
- The two shares: Turnbull estimates of the share of statements whose presentation had recovered \
by the end of the stated time, and by 90 days after it. A Turnbull estimate allows for recovery \
dates that are known only to lie between two captures of the list.
- Basis: which statements a row's figures rest on. "cell" is the row's own form and revision \
bucket; where that had fewer than $min_cell statements, the figures are those of every revision \
of the form ("form") or of every form with a stated time ("all dated forms").
- Last column: a median of 365 means 365 days or more, including never.

$slip_table

Form of the entry to forecast: $form
Revision bucket of the entry to forecast: $revision

Earlier entries with known outcomes (they are resolved; none of them is the entry to forecast):
$examples

### Entry to forecast

"""
    + ENTRY_FIELD_LINES
    + """

### Questions

Answer the three questions below. All times are counted from the date of update, \
$date_of_update. $horizon_note

1. p_by_horizon_a: the probability that, on or before $horizon_a, the presentation has recovered.
2. p_by_horizon_b: the probability that, on or before $horizon_b, the presentation has recovered.
3. days_to_recovery: quantiles of the time, in days, from the date of update to recovery. q10 is \
the number of days within which you give recovery a 10% chance, q50 is the median, and the same \
rule holds for q80, q90 and q95; from q10 to q95 they must not decrease. Give each as a whole \
number from 0 to 365, where 365 means 365 days or more, including never.

"""
    + REPLY_BLOCK
)
"""Paraphrase 2: the track record stands before the entry. The framing sentence names a role,
the rule on the date of update comes before the definition of recovery, the sections have
headings, and the notes on the table are a list."""

PARAPHRASE_3_TEXT = (
    """Here is a forecasting problem about one entry from the US FDA drug-shortage list: when \
will the presentation in this entry recover?

[Entry]
"""
    + ENTRY_FIELD_LINES
    + """

[Track record]
The record below covers earlier entries of this list, updated from $track_since to \
$track_through, and shows how the times stated in them turned out. It is the record of the whole \
list, all companies together, not of this entry's company.

In the table there is one row for each form of stated time and each revision bucket (whether \
the statement was the first one made for its presentation, the second, or the third or a later \
one). The column "basis" shows which statements a row's figures rest on: "cell" is the row's own \
form and revision bucket; where that had fewer than $min_cell statements, the figures are those \
of every revision of the form ("form") or of every form with a stated time ("all dated forms"). \
The two shares are the shares of statements whose presentation had recovered by the end of the \
stated time and by 90 days after it. They are Turnbull estimates; such an estimate allows for \
recovery dates that are known only to lie between two captures of the list. Where the last \
column shows a median of 365, that value means 365 days or more, including never.

$slip_table

This entry has the form: $form
This entry is in the revision bucket: $revision

Earlier entries that are resolved (their outcomes are known; this entry is not among them):
$examples

[Rules and definition]
This entry's own estimate may be optimistic, pessimistic or out of date; rather than repeating \
it, give your own forecast. Take this entry's date of update as today and use only what could \
have been known on that day. Recovered means that the list shows the presentation as available \
again, or the shortage as resolved for it; if the presentation is discontinued instead, it has \
not recovered.

[Questions]
Please answer the following three questions. All times are counted from the date of update, \
$date_of_update. $horizon_note

1. p_by_horizon_a: the probability of the presentation having recovered on or before $horizon_a.
2. p_by_horizon_b: the probability of the presentation having recovered on or before $horizon_b.
3. days_to_recovery: quantiles of the number of days between the date of update and recovery. \
q10 is the number of days within which, in your forecast, recovery has a 10% chance; q50 is the \
median; q80, q90 and q95 follow the same rule. They must not decrease from q10 to q95, and each \
is a whole number from 0 to 365, where 365 means 365 days or more, including never.

"""
    + REPLY_BLOCK
)
"""Paraphrase 3: the entry and the track record come first, and the rules and the definition of
recovery after them, just before the questions (in the order: own forecast, date of update,
definition). The framing sentence is a question, the sections carry bracketed labels, and the
notes on the table are in another order (the basis before the shares)."""

PARAPHRASE_OF = "predictive-track-v1"
PARAPHRASE_TEXTS = {
    "predictive-track-p1": PARAPHRASE_1_TEXT,
    "predictive-track-p2": PARAPHRASE_2_TEXT,
    "predictive-track-p3": PARAPHRASE_3_TEXT,
}
"""The paraphrases by template id. The launcher finds them by the start of their ids
(``launch.PARAPHRASE_PREFIX``) and makes one run of each for a model."""
# ------------------------------------------------------------------------------------------------

PROBE_TEXT = (
    """A drug presentation was on the US FDA drug-shortage list on $date_of_update. You \
are shown how the list identifies it, but not what its entry said. Estimate when this \
presentation recovered, meaning when the list next showed it as available or the shortage as \
resolved for it; if it was discontinued instead, it did not recover. Give your best estimate, \
using anything you know.

- Drug: $generic_name
- Company: $company_name
- Presentation: $presentation
- Therapeutic category: $therapeutic_category
- Initial posting date: $initial_posting_date
- Date of update: $date_of_update
"""
    + QUESTIONS
)
"""The no-notice probe. Its placeholders are those of ``PROBE_FIELDS`` and the two horizons,
which are fixed offsets from the date of update; :func:`probe_view` drops everything else."""

HORIZON_NOTES = {
    "stated_end": (
        "Horizon A, $horizon_a, is the end of the period the entry states; horizon B, "
        "$horizon_b, is 90 days after it."
    ),
    "fallback": (
        "The entry states no period, so horizon A, $horizon_a, is 90 days after the date of "
        "update, and horizon B, $horizon_b, is 180 days after it."
    ),
    "probe": (
        "Horizon A, $horizon_a, is 90 days after the date of update, and horizon B, "
        "$horizon_b, is 180 days after it."
    ),
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
    probe: bool = False
    """The no-notice probe: rendered from :func:`probe_view` of the item, with fixed horizons."""
    pilot: tuple[str, ...] = ()
    """The pilot sentences (keys of ``PILOT_SENTENCES``) that this template carries."""

    @property
    def pending(self) -> tuple[str, ...]:
        """The pilot sentences this template still waits for; a live run needs none."""
        return tuple(d for d in self.pilot if PILOT_SENTENCES[d] is None)

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
            "canary": render_for(self, CANARY_ITEM, track=CANARY_TRACK),
            "canary_masked": render_for(
                self, CANARY_ITEM, track=CANARY_TRACK, masker=masker, shift_years=2
            ),
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


CANARY_ITEM = ReadItem(
    item_id="canary",
    generic_name="Anagrelide Hydrochloride Capsules",
    company_name="Teva Pharmaceuticals USA, Inc.",
    presentation="0.5 MG 100 Capsules (NDC 0172-5241-60)",
    date_of_update="2020-03-17",
    therapeutic_category="Hematology",
    initial_posting_date="2019-11-22",
    type_of_update="Reverified",
    availability_information="Backordered. Next release Dec-20; 2Q21 at the latest.",
    related_information="Expected recovery April 2020 (lot 2000 mg; FY21). Teva is working on it.",
    reason_for_shortage="Demand increase for the drug",
    stated_end="2020-04-30",
    form="a month and year",
    revision="second",
)
"""A fixed item (a real 2020 text with extra date forms; its category, posting date, form and
revision bucket are set for the rendering only) whose renderings are part of each pin."""
CANARY_TRACK = TrackRecord(
    through="2022-12-31",
    slip_table=(
        SlipRow("a month and year", "first", 240, "cell", 0.31, 0.62, 140),
        SlipRow("a month and year", "second", 120, "cell", 0.24, 0.55, 171),
        SlipRow("a quarter", "third or later", 310, "form", 0.2, 0.41, None),
        SlipRow("TBD or unknown", "first", 180, "cell", None, None, None),
    ),
    examples=(
        ResolvedExample(
            item_id="canary-1",
            date_of_update="2020-03-04",
            outcome="recovered",
            availability_information="Backordered. Next release April 2020.",
            type_of_update="Revised",
            stated_end="2020-04-30",
            recovered_after="2020-06-10",
            recovered_by="2020-06-18",
        ),
        ResolvedExample(
            item_id="canary-2",
            date_of_update="2020-05-01",
            outcome="not_recovered",
            related_information="Next shipment TBD",
            followed_until="2021-11-30",
        ),
        ResolvedExample(
            item_id="canary-3",
            date_of_update="2020-06-01",
            outcome="recovered",
            recovered_by="2020-08-01",
        ),
        ResolvedExample(item_id="canary-4", date_of_update="2020-07-01", outcome="discontinued"),
    ),
)


TEMPLATES: dict[str, PromptTemplate] = {
    t.id: t
    for t in (
        PromptTemplate("literal-v1", "literal", LITERAL_TEXT, pilot=("D1", "D3")),
        PromptTemplate("literal-free-v1", "literal", LITERAL_FREE_TEXT, pilot=("D1",)),
        PromptTemplate("predictive-v1", "predictive", PREDICTIVE_TEXT, ("stated_end", "fallback")),
        PromptTemplate(
            "predictive-track-v1",
            "predictive",
            PREDICTIVE_TRACK_TEXT,
            ("stated_end", "fallback"),
            needs_track=True,
        ),
        PromptTemplate("probe-v1", "predictive", PROBE_TEXT, ("probe",), probe=True),
        *(
            PromptTemplate(
                template_id, "predictive", text, ("stated_end", "fallback"), needs_track=True
            )
            for template_id, text in PARAPHRASE_TEXTS.items()
        ),
    )
}

FROZEN_SHA256 = {
    "literal-v1": "855244013a7614501ebdd6fbb45c8998f102a877e1299a6d86f81e1359934b27",
    "literal-free-v1": "ab87cd7525a49965763f78f55d6f8c47f4ca1476f49216a525635f97d6ef2555",
    "predictive-v1": "c0732a5b2d109c60a94e56cd0820a4aa5851786bd01fd31acd3b12c9d47534ed",
    "predictive-track-v1": "d0384c1f860d734bd26fa197de0a99e1bcdf520392941b399ef9d0f7b3213483",
    "probe-v1": "02e8d4338c3532a22615a43c47c54423250bf13474ef3f556925f5c878e8d08e",
    "predictive-track-p1": "5b985d6ba619431394ea9521a06e91cfef2cbb73916793b66252cb8cd49a6b67",
    "predictive-track-p2": "1644f2428c5bd73c2490e4934f2b8197191d78fe838b09b24dff85ee2e1e8e08",
    "predictive-track-p3": "018f57e81ae8f299418b06c7767fa40dcd690dfe8f53b41575f1ac6e7fec19f9",
}
"""Pinned template digests, as ``--print-pins`` lists them. Until the freeze amendment F1 a
prompt edit moves its pin here (no call has been made under any of these ids). The edit of
1 October 2026 changed the entry fields, the probe fields and the track-record sentence. The edit
of 5 October 2026, after the pilot, filled the two pilot sentences of the literal prompts (D1 and
D3) and added to the track-record prompt that a median of 365 means 365 days or more. From F1
on, changing a prompt means a new template id, not an edit. The three paraphrases of
``predictive-track-v1`` are not among the five templates of the registration record (PLAN
section 17, "Prompts"): their ids and pins are among what F1 records ("At F1"). An edit of the
original before F1 moves their pins too where it touches the entry fields, the horizon
sentences or the reply instruction, which they share with it."""


def check_frozen() -> None:
    changed = [t.id for t in TEMPLATES.values() if FROZEN_SHA256.get(t.id) != t.sha256]
    if changed:
        raise RuntimeError(f"templates changed without a new pin: {changed}")


def template_pins() -> dict:
    """Every template id with its pin, for the registration record and for F1.

    ``sha256`` is the digest computed now and ``pinned`` the one in ``FROZEN_SHA256``; they
    differ only between a prompt edit and the update of its pin. ``pending`` lists the pilot
    sentences a template still waits for. ``schemas_sha256`` covers the two output schemas and
    ``read_py_sha256`` this file, which holds the parser and the runner.
    """
    schemas = json.dumps(SCHEMAS, sort_keys=True).encode("utf-8")
    return {
        "templates": {
            t.id: {
                "kind": t.kind,
                "sha256": t.sha256,
                "pinned": FROZEN_SHA256.get(t.id),
                "matches_pin": FROZEN_SHA256.get(t.id) == t.sha256,
                "pending": list(t.pending),
            }
            for t in TEMPLATES.values()
        },
        "schemas_sha256": hashlib.sha256(schemas).hexdigest(),
        "read_py_sha256": _sha256_file(Path(__file__)),
    }


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


def horizons(item: ReadItem, *, probe: bool = False) -> tuple[date, date, str]:
    """Horizons A and B of the forecast questions, and the rule that set them. The probe always
    gets the fixed offsets from the Date of Update, whatever the item carries."""
    if item.stated_end and not probe:
        end = parse_date(item.stated_end)
        return end, end + HORIZON_B_OFFSET, "stated_end"
    dou = parse_date(item.date_of_update)
    return dou + FALLBACK_HORIZONS[0], dou + FALLBACK_HORIZONS[1], "probe" if probe else "fallback"


def _entry_fields(item: ReadItem) -> dict[str, str]:
    return {
        "generic_name": _plain(item.generic_name),
        "company_name": _plain(item.company_name),
        "presentation": _plain(item.presentation),
        "therapeutic_category": _plain(item.therapeutic_category),
        "initial_posting_date": _plain(item.initial_posting_date),
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
        "| form | revision | statements | basis | recovered by the stated end | recovered by 90 "
        "days after the stated end | median days from update to recovery |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        median = (
            "n/a" if r.median_days_to_recovery is None else str(round(r.median_days_to_recovery))
        )
        lines.append(
            f"| {_one_line(r.form)} | {r.revision} | {r.statements} | {r.basis} | "
            f"{_share(r.share_by_stated_end)} | {_share(r.share_by_stated_end_90)} | {median} |"
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
    """The exact text sent for one item (already masked or shifted, if at all). A probe template
    is rendered from :func:`probe_view` of the item, whatever the caller passed."""
    if template.probe:
        item = probe_view(item)
    fields_ = _entry_fields(item)
    if template.kind == "literal":
        return string.Template(template.text).substitute(fields_)
    a, b, rule = horizons(item, probe=template.probe)
    marks = {"horizon_a": a.isoformat(), "horizon_b": b.isoformat()}
    fields_ |= marks | {"horizon_note": string.Template(HORIZON_NOTES[rule]).substitute(marks)}
    if template.needs_track:
        if track is None:
            raise ValueError(f"{template.id} needs a track record")
        if len(track.examples) > MAX_EXAMPLES:
            raise ValueError(f"at most {MAX_EXAMPLES} examples, got {len(track.examples)}")
        fields_ |= {
            "track_since": parse_date(track.since).isoformat(),
            "track_through": parse_date(track.through).isoformat(),
            "min_cell": str(track.min_cell),
            "slip_table": render_slip_table(track.slip_table),
            "form": _plain(item.form or "unclassified"),
            "revision": _plain(item.revision or "not given"),
            "examples": render_examples(track.examples),
        }
    return string.Template(template.text).substitute(fields_)


def render_for(
    template: PromptTemplate,
    item: ReadItem,
    *,
    track: TrackRecord | None = None,
    masker: NameMasker | None = None,
    shift_years: int = 0,
) -> str:
    """The prompt for a real item under a condition: the probe view first (so nothing the probe
    may not see can steer the masker either), then masking and the date shift, then the text.
    ``track`` is the record as shown, already transformed by :func:`transform_track`."""
    if template.probe:
        item = probe_view(item)
    return render_prompt(template, prepare(item, masker, shift_years), track)


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
                "initial_posting_date",
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
                followed_until=_shift_optional(ex.followed_until, years),
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


def estimate_tokens(text: str) -> int:
    """A token count from the length of the text: four characters to a token, rounded up.

    No tokenizer is loaded. The usual one fetches its vocabulary from the network the first
    time it is used, and a dry run, the run sheet and the tests must not touch the network; and
    a count that depended on what is installed would move the projected costs from one
    environment to the next. The check before a paid call adds a margin to this count
    (:func:`projected_call_usd`), and the cost trial replaces the projection by measured costs.
    """
    return max(1, math.ceil(len(text) / 4))


def token_method() -> str:
    return "characters / 4"


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
# Routes: the model id, the provider endpoint and the price of each reader
# ---------------------------------------------------------------------------------------------

UNSET = "UNSET"
"""A provider pin that has not been chosen yet. A live run is refused while its route has it."""
DIRECT = "direct"
"""The model's maker is called on its own API, so there is no provider to pin."""


@dataclass(frozen=True)
class Route:
    """How one of the eight readers is reached (see ``ROUTES``; recorded at F1)."""

    model_id: str
    """The id requested. Every response must echo it (or one of ``also_served_as``)."""
    provider: str
    """An OpenRouter endpoint slug such as ``deepinfra/turbo``, ``DIRECT``, or ``UNSET``."""
    quantization: str | None = None
    """The precision the endpoint states, sent as a filter; None when it states none."""
    price: tuple[float, float, str] | None = None
    """($ per 1M input tokens, $ per 1M output tokens, the day the price was read) of the pinned
    endpoint, or of the maker's own route; a pinned route must carry it. A direct route without
    one (None) keeps the ladder's price and date."""
    also_served_as: tuple[str, ...] = ()
    """Further model ids accepted in the echo (for a dated id that the route echoes otherwise)."""
    also_served_by: tuple[str, ...] = ()
    """Further provider names accepted in the echo, if a provider reports itself under a name
    that is neither the slug nor its part before the slash."""


# F1 TABLE -------------------------------------------------------------------------------------
# One row per reader. The six OpenRouter routes were entered on 2026-10-01, once the owner had
# confirmed the endpoints (analysis/coling/plan/DECISIONS.md; decision 17 for deepseek-v3). The
# values are those of analysis/coling/plan/MODELS.md, section 9, read at source on 2026-10-01:
# the model id sent, the endpoint slug, the precision the endpoint states, and the endpoint's
# price with the day it was read. F1 records the table as it then stands, with this file's hash.
# - The price is entered for every pinned endpoint: on OpenRouter a price belongs to an
#   endpoint, the ladder's belongs to the model id, and a live run is refused for a pinned
#   route without one (the spend log would misstate the spend). The two direct routes carry
#   the makers' own prices, read again on 2026-10-01 and equal to the ladder's, so that one
#   price date serves all eight rows, as PLAN section 4 registers it.
# - ``phala`` and ``openai`` state no precision: their third value is ``None`` and no precision
#   filter is sent.
# - gpt-4o-mini keeps the alias id, pinned to ``openai``. If its dated id
#   (openai/gpt-4o-mini-2024-07-18) is taken, change the model id here and, if the echo
#   differs, ``also_served_as``.
# - A row whose provider is ``UNSET`` (none today: a route taken back, or a reader added later)
#   is refused for a live run until its endpoint is entered, for example
#       Route("qwen/qwen-2.5-7b-instruct", "phala", None, (0.10, 0.20, "2026-10-01"))
# - Still open until the cost trial: the name under which a provider reports itself in a
#   response is not documented (the endpoint listing prints "DeepInfra", "Phala" and "OpenAI",
#   not the slug that is sent). ``also_served_by`` is therefore left empty in every row and
#   ``PROVIDER_ECHO_REQUIRED`` stays off; both are set from what the trial's responses show.
# Entering a route clears nothing else: a live run still needs the registration tag
# (:func:`paid_call_refusals`), the pilot sentences of its template and its entry in the ledger.
ROUTES: dict[str, Route] = {
    "llama-3.3-70b": Route(
        "meta-llama/llama-3.3-70b-instruct", "deepinfra/turbo", "fp8", (0.10, 0.32, "2026-10-01")
    ),
    "deepseek-v3": Route(
        "deepseek/deepseek-chat", "deepinfra/fp4", "fp4", (0.32, 0.89, "2026-10-01")
    ),
    "qwen-2.5-7b": Route("qwen/qwen-2.5-7b-instruct", "phala", None, (0.10, 0.20, "2026-10-01")),
    "gemma-3-27b": Route(
        "google/gemma-3-27b-it", "deepinfra/fp8", "fp8", (0.08, 0.16, "2026-10-01")
    ),
    "gpt-oss-20b": Route(
        "openai/gpt-oss-20b", "deepinfra/bf16", "bf16", (0.03, 0.14, "2026-10-01")
    ),
    "gpt-4o-mini": Route("openai/gpt-4o-mini", "openai", None, (0.15, 0.60, "2026-10-01")),
    "gemini-3.8-flash": Route("gemini-3.8-flash", DIRECT, None, (0.75, 3.75, "2026-10-01")),
    "grok-4.20": Route("grok-4.20-0309-non-reasoning", DIRECT, None, (1.25, 2.50, "2026-10-01")),
}
PROVIDER_ECHO_REQUIRED = False
"""Whether a response on a pinned route must name its provider. OpenRouter documents the name
under a routing-metadata object that it returns on request; the cost trial shows its exact shape
(:func:`served_of` keeps what it finds). Set to True at F1 once that is confirmed: a response
that names no provider is then refused. A response that names another provider is refused now."""
# ----------------------------------------------------------------------------------------------


def provider_object(route: Route | None) -> dict | None:
    """The OpenRouter ``provider`` request object that pins a route: one endpoint, fallbacks
    off, and the precision as a filter when the endpoint states one. None for a route that is
    direct, unset or absent."""
    if route is None or route.provider in (UNSET, DIRECT):
        return None
    pin: dict = {"order": [route.provider], "allow_fallbacks": False}
    if route.quantization:
        pin["quantizations"] = [route.quantization]
    return pin


def route_tag(route: Route | None) -> str:
    """A short digest of the provider pin ("" without one). It is part of every cache key, so an
    answer served under one pin is never reused under another."""
    pin = provider_object(route)
    if pin is None:
        return ""
    return hashlib.sha256(json.dumps(pin, sort_keys=True).encode("utf-8")).hexdigest()[:8]


def route_errors(model: str) -> list[str]:
    """Why a model cannot be called live yet (empty when it can)."""
    route = ROUTES.get(model)
    if route is None:
        return [f"{model!r} is not one of the eight readers in ROUTES"]
    on_openrouter = LADDER[model].provider == "openrouter"
    if route.provider == UNSET:
        return [
            f"ROUTES[{model!r}] has no provider yet (UNSET); the endpoint of PLAN section 4 is "
            "entered there before the first paid run"
        ]
    if on_openrouter == (route.provider == DIRECT):
        return [f"ROUTES[{model!r}]: an OpenRouter model needs an endpoint slug, others DIRECT"]
    if on_openrouter and route.price is None:
        return [
            f"ROUTES[{model!r}] pins {route.provider!r} and gives no price; the price of the "
            "pinned endpoint (in, out, the day it was read) is entered with the route"
        ]
    return []


def served_as(model: str) -> tuple[str, ...]:
    """The model ids a response may echo for this model."""
    rung, route = LADDER[model], ROUTES.get(model)
    if route is None:
        return rung.served_as
    base = rung.served_as if route.model_id == rung.model_id else (route.model_id,)
    return (*base, *route.also_served_as)


def route_endpoint(model: str) -> EndpointConfig:
    """The endpoint of a model: the ladder's, with the route's model id, price and provider pin
    when the model is one of the eight readers."""
    rung = LADDER[model]
    endpoint = rung.endpoint()
    route = ROUTES.get(model)
    if route is None:
        return endpoint
    changes: dict[str, Any] = {}
    if route.model_id != endpoint.model_id:
        changes |= {"model_id": route.model_id, "name": f"{rung.provider}:{route.model_id}"}
    if route.price is not None:
        price_in, price_out, price_date = route.price
        changes |= {
            "price_input_per_mtok": price_in,
            "price_output_per_mtok": price_out,
            "price_date": price_date,
        }
    pin = provider_object(route)
    if pin is not None:
        changes["extra_body"] = {**(endpoint.extra_body or {}), "provider": pin}
    return replace(endpoint, **changes) if changes else endpoint


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def provider_problem(route: Route | None, names: Sequence[str]) -> str | None:
    """What is wrong with the provider names of a response on a pinned route (None if nothing).
    A name is accepted when it is the pinned slug, the slug's part before the slash (the
    provider's own name), or one of ``also_served_by``, compared on letters and digits only."""
    if provider_object(route) is None:
        return None
    assert route is not None
    if not names:
        return "the response names no provider" if PROVIDER_ECHO_REQUIRED else None
    accepted = {_slug(n) for n in (route.provider, route.provider.split("/")[0])}
    accepted |= {_slug(n) for n in route.also_served_by}
    wrong = [n for n in names if _slug(n) not in accepted]
    if wrong:
        return f"pinned to {route.provider!r} but the response names {wrong}"
    return None


class ServedProviderMismatch(ServedModelMismatch):
    """The call was served by another provider than the pinned one."""


_PROVIDER_KEYS = ("provider_name", "provider", "tag", "provider_slug")
SERVED_METADATA_CHARS = 4000


def _get(node: Any, name: str) -> Any:
    return node.get(name) if isinstance(node, dict) else getattr(node, name, None)


def _provider_names(node: Any, depth: int = 0) -> list[str]:
    """Every provider name in a piece of routing metadata, outermost first.

    OpenRouter documents the metadata as a list of the endpoints it considered, each with a
    ``selected`` flag. An entry whose flag is exactly false was considered and not used: it
    names nobody, and nothing under it is read. An entry with no flag, or with any other value
    there, counts as naming its provider, so an unknown shape errs towards refusing the
    response.
    """
    found: list[str] = []
    if isinstance(node, dict):
        if node.get("selected") is False:
            return found
        for key in _PROVIDER_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                found.append(value.strip())
        children: Iterable[Any] = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return found
    if depth < 4:
        for child in children:
            found += _provider_names(child, depth + 1)
    return found


def served_of(response: Any) -> dict:
    """What a response says about who served it: the echoed model id, and on OpenRouter the
    provider. The provider is looked for in a top-level ``provider`` string and in the
    ``openrouter_metadata`` object (returned when the request carries the header
    ``X-OpenRouter-Metadata: enabled``); every distinct name found is kept, except those of
    endpoints the metadata marks as not selected, and the metadata itself is kept (shortened)
    for the local response file."""
    model = str(_get(response, "model") or "").removeprefix("models/")
    meta = _get(response, "openrouter_metadata")
    if meta is not None and not isinstance(meta, dict | list):
        dump = getattr(meta, "model_dump", None)
        meta = dump() if callable(dump) else None
    top = _get(response, "provider")
    names: list[str] = []
    for name in ([top.strip()] if isinstance(top, str) and top.strip() else []) + (
        _provider_names(meta)
    ):
        if name not in names:
            names.append(name)
    text = json.dumps(meta, sort_keys=True, default=str) if meta is not None else None
    return {
        "model": model,
        "provider": " | ".join(names) if names else None,
        "provider_names": names,
        "metadata": text[:SERVED_METADATA_CHARS] if text else None,
    }


class _Tap:
    """Stands where the SDK client stands inside :class:`EchoCheckedClient`: passes every
    request on unchanged (plus the given headers) and keeps the responses it returns."""

    def __init__(self, sdk: Any, headers: dict[str, str]) -> None:
        self._sdk = sdk
        self._headers = dict(headers)
        self.seen: list[Any] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> Any:
        if self._headers:
            kwargs["extra_headers"] = {**kwargs.get("extra_headers", {}), **self._headers}
        response = self._sdk.chat.completions.create(**kwargs)
        self.seen.append(response)
        return response


class RouteCheckedClient(EchoCheckedClient):
    """The live client of this study. :class:`EchoCheckedClient` does the call and the
    served-model check, unchanged; this class adds three things around it.

    * The request: the provider pin travels in the endpoint's ``extra_body`` (see
      :func:`route_endpoint`), and a pinned request asks OpenRouter for its routing metadata.
    * The record: after every call ``last_served`` holds what the response said (see
      :func:`served_of`) and ``last_billed`` the tokens of every response of the call, also when
      the call ends in a refusal for a wrong model or provider, so that spend can be logged.
    * The provider check: a response that names another provider than the pinned one raises
      :class:`ServedProviderMismatch`.

    ``sdk`` replaces the SDK client with a scripted one (tests); no key is resolved then.
    """

    def __init__(
        self,
        endpoint: EndpointConfig,
        served_as: tuple[str, ...],
        *,
        route: Route | None = None,
        sdk: Any = None,
        **kwargs: Any,
    ) -> None:
        if sdk is None:
            super().__init__(endpoint, served_as, **kwargs)
            sdk = self._client
        else:
            self._endpoint, self._served_as = endpoint, tuple(served_as)
        self._route = route
        pinned = provider_object(route) is not None
        self._client = _Tap(sdk, {"X-OpenRouter-Metadata": "enabled"} if pinned else {})
        self.last_served: dict | None = None
        self.last_billed: tuple[int, int, int] | None = None

    def complete_metered(
        self, prompt: str, *, decoding: DecodingConfig, system: str | None = None
    ) -> RawResponse:
        tap = self._client
        tap.seen.clear()
        self.last_served = self.last_billed = None
        try:
            raw = super().complete_metered(prompt, decoding=decoding, system=system)
        finally:
            usages = [u for u in (_get(r, "usage") for r in tap.seen) if u is not None]
            if usages:
                self.last_billed = (
                    sum(u.prompt_tokens for u in usages),
                    sum(u.completion_tokens for u in usages),
                    sum(u.total_tokens for u in usages),
                )
            if tap.seen:
                self.last_served = served_of(tap.seen[-1])
        assert self.last_served is not None
        problem = provider_problem(self._route, self.last_served["provider_names"])
        if problem:
            raise ServedProviderMismatch(problem)
        return raw


class ReadCache(DiskCache):
    """The study's disk cache. Beside the answer and its token counts, an entry keeps who served
    it, so a run resumed from the cache still knows. The entry is written once, whole: a run
    killed while it stores an answer leaves either the full entry or none, never an answer
    without its echo."""

    def put(self, key: str, raw: RawResponse, served: dict | None = None) -> None:
        if not served:
            super().put(key, raw)
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "completion_tokens": raw.completion_tokens,
            "prompt_tokens": raw.prompt_tokens,
            "text": raw.text,
            "total_tokens": raw.total_tokens,
            "served": served,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(tmp, path)


# ---------------------------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------------------------


def decoding_for(temperature: float) -> DecodingConfig:
    """``det-v1`` at temperature 0 (the commitment study's label); ``temp<T>-v1`` otherwise."""
    if temperature < 0:
        raise ValueError("temperature must be non-negative")
    label = "det-v1" if temperature == 0 else f"temp{temperature:g}-v1"
    return DecodingConfig(label, float(temperature), None)


def call_state(
    template: PromptTemplate, item_id: str, sample: int, attempt: int, route: str = ""
) -> str:
    """The part of a cache key that names the call: template and pin, item, sample, repair
    attempt, and the route tag (see :func:`route_tag`)."""
    state = f"{template.id}@{template.sha256[:16]}#{item_id}#s{sample}"
    state = f"{state}#a{attempt}" if attempt else state
    return f"{state}#r{route}" if route else state


def condition_id(
    template: PromptTemplate,
    decoding: DecodingConfig,
    *,
    mask_names: bool,
    shift_years: int,
    track: TrackRecord | None,
) -> str:
    """One label for everything that defines a condition besides the model: the template, the
    decoding, masking, the date shift and the track-record file. Runs and shards with the same
    model and the same label answer the same question and may be pooled."""
    record = track.sha256[:16] if track is not None and track.sha256 else "-"
    return (
        f"{template.id}|{decoding.decoding_hash}|mask={int(mask_names)}|shift={shift_years}"
        f"|track={record}"
    )


def fallback_for(kind: str, status: str) -> str | None:
    """What stands in for a reading that failed after its repair call or was refused: a literal
    reading counts as ABSTAIN (``abstain``), a predictive one is replaced by the base-rate
    predictor's output for the event (``base_rate``; the evaluator does the replacing and
    reports it). None for a parsed reading."""
    if status in ("ok", "repaired"):
        return None
    return "abstain" if kind == "literal" else "base_rate"


def build_transport(
    model: str,
    *,
    spend_log: Path,
    spend_cap_usd: float,
    max_physical_calls: int,
    inner: Transport | None = None,
    template: PromptTemplate | None = None,
    periods: Iterable[str] = SEALED_PERIODS,
) -> tuple[EndpointConfig, GuardedTransport]:
    """The model's route behind the served-model check and the guard. ``inner`` replaces the
    live client (tests); otherwise the key is resolved here, at setup, by the endpoint config.

    Without ``inner`` this is the one place where a client that can spend money is built, so
    what the command line checks is checked here again, for any other caller: the route, the
    pilot sentences of ``template``, the registration tag and, for ``periods`` that are sealed
    (the default, when the caller does not say), the F1 tag (:func:`live_refusals`); and that
    the run which owns ``spend_log`` stands in the study ledger with this cap, under the shared
    output root (:func:`ledger_refusals`). :class:`LiveRunRefused` is raised before any key is
    read.
    """
    endpoint = route_endpoint(model)
    if inner is None:
        if template is None:
            raise LiveRunRefused("a live client needs the template it will be used with")
        refusals = live_refusals(model, template, periods)
        refusals += ledger_refusals(spend_log, model, spend_cap_usd)
        if refusals:
            raise LiveRunRefused("; ".join(refusals))
        inner = RouteCheckedClient(
            endpoint,
            served_as(model),
            route=ROUTES.get(model),
            timeout=LIVE_TIMEOUT_S,
            max_retries=0,
        )
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
    route: Route | None = None
    """The registered route. With it, the echo of every attempt is checked again when a row is
    written, also for answers that come from the cache."""
    responses: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if FROZEN_SHA256.get(self.template.id) != self.template.sha256:
            raise RuntimeError(f"template {self.template.id!r} does not match its pin")
        if self.template.needs_track and self.track is None:
            raise ValueError(f"{self.template.id} needs a track record")
        if not isinstance(self.cache, ReadCache):
            self.cache = ReadCache(self.cache.root)
        self._track = (
            transform_track(self.track, self.masker, self.shift_years) if self.track else None
        )
        self._example_ids = {ex.item_id for ex in self.track.examples} if self.track else set()
        self._cells = {(r.form, r.revision) for r in self.track.slip_table} if self.track else set()
        self._route_tag = route_tag(self.route)
        self._served_as = tuple(dict.fromkeys((self.endpoint.model_id, *served_as(self.model))))
        self.condition = condition_id(
            self.template,
            self.decoding,
            mask_names=self.masker is not None,
            shift_years=self.shift_years,
            track=self.track,
        )

    def prompt_for(self, item: ReadItem) -> str:
        return render_for(
            self.template,
            item,
            track=self._track,
            masker=self.masker,
            shift_years=self.shift_years,
        )

    def _log_unusable_call(self, prompt: str) -> None:
        """A response refused for a wrong model or provider was still billed: put its tokens in
        the spend log, so that the caps count it."""
        billed = getattr(self.transport.inner, "last_billed", None)
        if not billed:
            return
        raw = RawResponse("", *billed)
        cost = usd(raw.prompt_tokens, raw.billable_output(self.endpoint), self.endpoint)
        self.transport.spent_usd += cost
        self.transport.physical_calls += 1
        row = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "event": "call",
            "status": "served_mismatch",
            "prompt_sha256": prompt_digest(prompt),
            "prompt_tokens": raw.prompt_tokens,
            "completion_tokens": raw.completion_tokens,
            "total_tokens": raw.total_tokens,
            "billable_output_tokens": raw.billable_output(self.endpoint),
            "usd": cost,
            "cumulative_usd": self.transport.spent_usd,
        }
        self.transport.spend_log.parent.mkdir(parents=True, exist_ok=True)
        with self.transport.spend_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _call(self, prompt: str, state: str) -> tuple[RawResponse, bool, dict | None]:
        key = cache_key(
            model_id=self.endpoint.model_id,
            prompt=prompt,
            state=state,
            decoding_hash=self.decoding.decoding_hash,
        )
        payload = self.cache.get(key)
        if payload is not None:
            raw = RawResponse(
                text=payload["text"],
                prompt_tokens=payload["prompt_tokens"],
                completion_tokens=payload["completion_tokens"],
                total_tokens=payload["total_tokens"],
            )
            return raw, True, payload.get("served")
        projected = projected_call_usd(prompt, self.model, self.template.kind, self.endpoint)
        cap = self.transport.spend_cap_usd
        if self.transport.spent_usd + projected > cap:
            raise SpendCapReached(
                f"recorded spend ${self.transport.spent_usd:.4f} plus this call's projected "
                f"${projected:.4f} would pass the ${cap:.2f} cap"
            )
        try:
            raw = self.transport.complete_metered(prompt, decoding=self.decoding)
        except ServedModelMismatch:
            self._log_unusable_call(prompt)
            raise
        refused = raw.text == "" and raw.total_tokens == 0
        served = None if refused else getattr(self.transport.inner, "last_served", None)
        self.cache.put(key, raw, served)
        return raw, False, served

    def _attempt(self, item: ReadItem, sample: int, attempt: int, prompt: str) -> dict:
        state = call_state(self.template, item.item_id, sample, attempt, self._route_tag)
        raw, hit, served = self._call(prompt, state)
        refused = raw.text == "" and raw.total_tokens == 0
        served = served or {}
        self.responses.append(
            {
                "item_id": item.item_id,
                "sample": sample,
                "attempt": attempt,
                "prompt_sha256": prompt_digest(prompt),
                "text": raw.text,
                "served": served or None,
            }
        )
        return {
            "attempt": attempt,
            "prompt_sha256": prompt_digest(prompt),
            "cache_hit": hit,
            "refused": refused,
            "served_model": served.get("model") or None,
            "served_provider": served.get("provider"),
            "prompt_tokens": raw.prompt_tokens,
            "completion_tokens": raw.completion_tokens,
            "total_tokens": raw.total_tokens,
            "billable_output_tokens": raw.billable_output(self.endpoint),
            "usd": usd(raw.prompt_tokens, raw.billable_output(self.endpoint), self.endpoint),
            "_text": raw.text,
            "_provider_names": served.get("provider_names") or [],
        }

    def _echo(self, attempts: Sequence[dict]) -> str:
        """``ok`` when every answered attempt echoes the registered model id and, on a pinned
        route, names the pinned provider; ``mismatch`` when one echoes something else;
        ``provider_not_reported`` when the model is right and no provider is named;
        ``not_recorded`` when an attempt carries no echo at all (a scripted client);
        ``refused`` when every attempt was refused, so nothing answered."""
        answered = [a for a in attempts if not a["refused"]]
        if not answered:
            return "refused"
        if any(a["served_model"] is None for a in answered):
            return "not_recorded"
        for a in answered:
            if a["served_model"] not in self._served_as:
                return "mismatch"
            if provider_problem(self.route, a["_provider_names"]):
                return "mismatch"
        pinned = provider_object(self.route) is not None
        if pinned and any(a["served_provider"] is None for a in answered):
            return "provider_not_reported"
        return "ok"

    def _context_warnings(self, item: ReadItem) -> list[str]:
        found = []
        if self.track is not None and not track_precedes(self.track, item):
            found.append("track_record_not_before_item")
        if self.template.needs_track and (item.form, item.revision) not in self._cells:
            found.append("no_track_row_for_item")
        return found

    def read(self, item: ReadItem, sample: int = 0) -> dict:
        """One reading row: the parsed answer, its status, and what each attempt cost."""
        if item.item_id in self._example_ids:
            raise ValueError(f"item {item.item_id!r} is one of the track record's examples")
        prompt = self.prompt_for(item)
        view = probe_view(item) if self.template.probe else item
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
            "provider_pin": self.route.provider if self.route else None,
            "template": self.template.id,
            "template_sha256": self.template.sha256,
            "decoding": self.decoding.decoding_hash,
            "temperature": self.decoding.temperature,
            "mask_names": self.masker is not None,
            "shift_years": self.shift_years,
            "track_record_sha256": (self.track.sha256 or None) if self.track else None,
            "condition": self.condition,
            "status": status,
            "fallback": fallback_for(self.template.kind, status),
            "echo": self._echo(attempts),
            "reading": parsed.reading if parsed.ok else None,
            "errors": errors,
            "warnings": parsed.warnings + self._context_warnings(view),
            "attempts": [{k: v for k, v in a.items() if not k.startswith("_")} for a in attempts],
        }
        if self.template.kind == "predictive":
            a, b, rule = horizons(view, probe=self.template.probe)
            row["horizons"] = {"a": a.isoformat(), "b": b.isoformat(), "rule": rule}
        elif parsed.ok and self.shift_years and isinstance(parsed.reading["interval"], dict):
            iv = parsed.reading["interval"]
            row["interval_unshifted"] = {
                k: shift_day(date.fromisoformat(iv[k]), -self.shift_years).isoformat()
                for k in ("start", "end")
            }
        return row


def echo_acceptable(echo: str) -> bool:
    """Whether a row's echo lets it be scored: the registered model and provider answered
    (``ok``), or nothing answered (``refused``). While ``PROVIDER_ECHO_REQUIRED`` is off, a
    response that names no provider is accepted too. ``mismatch`` and ``not_recorded`` never
    are."""
    allowed = {"ok", "refused"} | (set() if PROVIDER_ECHO_REQUIRED else {"provider_not_reported"})
    return echo in allowed


def read_items(
    reader: Reader,
    items: Sequence[ReadItem],
    *,
    samples: int = 1,
    rows: list[dict] | None = None,
) -> tuple[list[dict], str]:
    """Every item and sample, in order. Returns the rows and ``complete`` or ``aborted: ...``.
    A run is aborted, not failed, when a cap is reached or a response comes from another model
    or provider than the registered one; rows read before that are kept, and their answers stay
    cached. ``rows`` is filled in place, so a caller keeps what was read if anything else is
    raised."""
    rows = [] if rows is None else rows
    try:
        for item in items:
            for sample in range(samples):
                rows.append(reader.read(item, sample))
    except (SpendCapReached, CallCapReached) as exc:
        return rows, f"aborted: {exc}"
    except ServedModelMismatch as exc:
        return rows, f"aborted: served by another model or provider: {exc}"
    return rows, "complete"


SAMPLED_PERCENTS = tuple(round(100 * level) for level in QUANTILE_LEVELS)


def sampled_quantiles(rows: Iterable[dict]) -> dict[str, dict]:
    """The sampled quantiles of each item of a run with several samples per item (the 20 samples
    at temperature 1 under condition (a)): the empirical quantiles, at the levels of the
    verbalised ones, of the medians (q50) that the samples gave.

    The quantile at level t of n sampled medians is the k-th smallest, with k the smallest whole
    number at least t times n: the inverse of the empirical distribution function, with no
    interpolation. With 20 samples these are the 2nd, 10th, 16th, 18th and 19th smallest. A
    sample with no parsed reading is left out and counted (``parsed`` against ``samples``); an
    item with no parsed sample has ``quantiles`` None and takes the predictive fallback.
    """
    medians: dict[str, list[int]] = {}
    drawn: dict[str, int] = {}
    for row in rows:
        item_id = row["item_id"]
        drawn[item_id] = drawn.get(item_id, 0) + 1
        values = medians.setdefault(item_id, [])
        if row.get("reading") is not None:
            values.append(int(row["reading"]["days_to_recovery"]["q50"]))
    out: dict[str, dict] = {}
    for item_id, n in drawn.items():
        values = sorted(medians[item_id])
        quantiles = None
        if values:
            ranks = [max(1, -(-pct * len(values) // 100)) for pct in SAMPLED_PERCENTS]
            quantiles = {key: values[k - 1] for key, k in zip(QUANTILE_KEYS, ranks, strict=True)}
        out[item_id] = {"samples": n, "parsed": len(values), "quantiles": quantiles}
    return out


def shard_of(item_id: str, shards: int) -> int:
    """The shard an item belongs to: fixed by its id alone, so shards are disjoint, cover every
    item and do not depend on the order of the items file."""
    return int(hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:12], 16) % shards


def parse_shard(text: str | None) -> tuple[int, int] | None:
    """``K/N`` as (K, N), with 0 <= K < N."""
    if text is None:
        return None
    match = re.fullmatch(r"(\d+)/(\d+)", text)
    if not match or not int(match.group(1)) < int(match.group(2)):
        raise SystemExit("--shard takes K/N with 0 <= K < N, for example 0/4")
    return int(match.group(1)), int(match.group(2))


# ---------------------------------------------------------------------------------------------
# Dry run and outputs
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
    cache_dir: Path | None = None,
) -> dict:
    """Render every prompt and price it from token counts. Sends nothing."""
    masker = NameMasker() if mask_names else None
    moved = transform_track(track, masker, shift_years) if track else None
    prompts = [
        render_for(template, i, track=moved, masker=masker, shift_years=shift_years) for i in items
    ]
    prompt_tokens = [estimate_tokens(p) for p in prompts]
    decoding = decoding_for(temperature)
    cache = DiskCache(cache_dir) if cache_dir is not None else None
    per_model = {}
    for model in models:
        endpoint = route_endpoint(model)
        tag = route_tag(ROUTES.get(model))
        cached = 0
        typical = upper = 0.0
        for item, prompt, tokens in zip(items, prompts, prompt_tokens, strict=True):
            for sample in range(samples):
                if cache is not None:
                    key = cache_key(
                        model_id=endpoint.model_id,
                        prompt=prompt,
                        state=call_state(template, item.item_id, sample, 0, tag),
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
            "route_ready": not route_errors(model),
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
        "template_pending": list(template.pending),
        "condition": condition_id(
            template, decoding, mask_names=mask_names, shift_years=shift_years, track=track
        ),
        "items": len(items),
        "items_by_period": {p: periods.count(p) for p in ("train", "test", "late")},
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


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids_sha256(ids: Iterable[str]) -> str:
    """One digest for a set of item ids: the sha256 of the sorted ids, one per line."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def _git(*args: str) -> str | None:
    """The output of a git command run in the checkout that holds this file (None if it fails).

    Every ``GIT_*`` variable is dropped from the environment first. With ``GIT_DIR`` or
    ``GIT_WORK_TREE`` set, git would answer for another repository, and the paid-call guards and
    the shared-roots file would then be read from there.
    """
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    try:
        proc = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30, env=env
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _modified(path: Path) -> bool | None:
    """Whether the file differs from HEAD (None when git cannot say)."""
    state = _git("status", "--porcelain", "--", str(path))
    return None if state is None else bool(state)


def write_run(
    rows: Sequence[dict],
    reader: Reader,
    *,
    out_dir: Path,
    local_dir: Path,
    meta: dict,
    items: Sequence[ReadItem],
    samples: int,
) -> dict:
    """Write the readings, the raw responses and the manifest of a run. The manifest says what
    the run was expected to answer (``item_ids_sha256``, ``expected_rows``) and whether it did
    (``complete``), so an evaluator can refuse a partial run without reading the rows."""
    _write_jsonl(out_dir / "readings.jsonl", rows)
    _write_jsonl(local_dir / "responses.jsonl", reader.responses)

    def count(key: str) -> dict[str, int]:
        values = [r[key] for r in rows]
        return {v: values.count(v) for v in sorted(set(values))}

    done = {(r["item_id"], r["sample"]) for r in rows}
    expected = len(items) * samples
    manifest = {
        **meta,
        "template": reader.template.id,
        "template_sha256": reader.template.sha256,
        "condition": reader.condition,
        "model": reader.model,
        "model_id": reader.endpoint.model_id,
        "served_as": list(reader._served_as),
        "route": asdict(reader.route) if reader.route else None,
        "provider_object": provider_object(reader.route),
        "ladder_rung": asdict(LADDER[reader.model]),
        "usd_per_mtok": [
            reader.endpoint.price_input_per_mtok,
            reader.endpoint.price_output_per_mtok,
        ],
        "price_date": reader.endpoint.price_date,
        "track_record_sha256": (reader.track.sha256 or None) if reader.track else None,
        "track_record_split": reader.track.split if reader.track else None,
        "read_py_sha256": _sha256_file(Path(__file__)),
        "items": len(items),
        "item_ids_sha256": _ids_sha256(i.item_id for i in items),
        "expected_rows": expected,
        "readings": len(rows),
        "complete": meta.get("status") == "complete" and len(done) == expected == len(rows),
        "by_status": count("status"),
        "by_echo": count("echo"),
        "fallbacks": sum(1 for r in rows if r["fallback"]),
        "guard": reader.transport.stats(),
        "readings_sha256": _sha256_file(out_dir / "readings.jsonl"),
    }
    (out_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def runs_with_readings(out_root: Path) -> list[str]:
    """The names of the runs under ``out_root`` that wrote a readings file, in name order."""
    return [path.parent.name for path in sorted(out_root.glob("*/readings.jsonl"))]


def collect_readings(
    out_root: Path, runs: Iterable[str] | None = None
) -> dict[tuple[str, str], dict]:
    """What the runs under ``out_root`` answered, pooled over run names and shards.

    Every paid run shares one output root, so a cost trial, a dev run or a secondary list can
    stand under the same model and condition as a confirmatory run. ``runs`` limits the pooling
    to the runs of those names (the shards of one line of the run sheet, say); a run of any
    other name is skipped as if it were not there. Without ``runs`` every run is pooled.

    The key is (model, condition), with the condition label of :func:`condition_id`. Each value
    holds ``runs`` (their names), ``incomplete_runs`` (those whose manifest is missing or does
    not say ``complete``), ``rows`` (one reading row per (item id, sample); the first run in
    name order wins), ``item_ids`` (the items with every sample of the group's largest sample
    count present), ``duplicates`` ((item id, sample) pairs found in more than one run), and
    counts ``by_status`` and ``by_echo``. An evaluator compares ``item_ids`` with the eligible
    set, and refuses a group with incomplete runs, duplicates or an echo that
    :func:`echo_acceptable` rejects.
    """
    groups: dict[tuple[str, str], dict] = {}
    wanted = None if runs is None else {runs} if isinstance(runs, str) else set(runs)

    def enter(run: str, model: str, condition: str, complete: bool) -> dict:
        group = groups.setdefault(
            (model, condition), {"runs": [], "incomplete_runs": [], "rows": {}, "duplicates": []}
        )
        if run not in group["runs"]:
            group["runs"].append(run)
            if not complete:
                group["incomplete_runs"].append(run)
        return group

    for run in runs_with_readings(out_root):
        if wanted is not None and run not in wanted:
            continue
        path = out_root / run / "readings.jsonl"
        manifest_path = path.parent / "run_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        )
        complete = bool(manifest.get("complete"))
        if manifest:  # a run that stopped before its first row still counts as a run
            enter(run, manifest["model"], manifest["condition"], complete)
        for row in _read_jsonl(path):
            group = enter(run, row["model"], row["condition"], complete)
            key = (row["item_id"], row["sample"])
            if key in group["rows"]:
                group["duplicates"].append(key)
            else:
                group["rows"][key] = row
    for group in groups.values():
        rows = list(group["rows"].values())
        samples = 1 + max((s for _, s in group["rows"]), default=0)
        seen: dict[str, int] = {}
        for item_id, _ in group["rows"]:
            seen[item_id] = seen.get(item_id, 0) + 1
        group["samples"] = samples
        group["item_ids"] = {item_id for item_id, n in seen.items() if n == samples}
        for name in ("status", "echo"):
            values = [r[name] for r in rows]
            group[f"by_{name}"] = {v: values.count(v) for v in sorted(set(values))}
    return groups


def check_runs(
    out_root: Path,
    *,
    expected: Iterable[str] | None = None,
    template: str | None = None,
    runs: Iterable[str] | None = None,
) -> list[dict]:
    """A completeness report, one entry per model and condition (limited to one template if
    given, and to the runs named in ``runs`` if given: see :func:`collect_readings`). With
    ``expected`` (item ids), each entry also says which of them are missing and which answered
    ids were not expected. ``ready`` is true when nothing stands in the way of scoring the
    group: complete runs only, no duplicate, every echo acceptable (see
    :func:`echo_acceptable`), and, if ``expected`` was given, exactly the expected ids."""
    wanted = set(expected) if expected is not None else None
    report = []
    for (model, condition), group in sorted(collect_readings(out_root, runs).items()):
        if template is not None and condition.split("|")[0] != template:
            continue
        entry = {
            "model": model,
            "condition": condition,
            "runs": group["runs"],
            "incomplete_runs": group["incomplete_runs"],
            "samples": group["samples"],
            "items_answered": len(group["item_ids"]),
            "item_ids_sha256": _ids_sha256(group["item_ids"]),
            "rows": len(group["rows"]),
            "duplicates": len(group["duplicates"]),
            "by_status": group["by_status"],
            "by_echo": group["by_echo"],
        }
        ready = not group["incomplete_runs"] and not group["duplicates"]
        ready = ready and all(echo_acceptable(echo) for echo in group["by_echo"])
        if wanted is not None:
            missing, extra = sorted(wanted - group["item_ids"]), sorted(group["item_ids"] - wanted)
            entry |= {
                "expected": len(wanted),
                "missing": len(missing),
                "missing_first": missing[:10],
                "unexpected": len(extra),
                "unexpected_first": extra[:10],
            }
            ready = ready and not missing and not extra
        report.append(entry | {"ready": ready})
    return report


# ---------------------------------------------------------------------------------------------
# Paid-call guards, the shared roots and the study ledger
# ---------------------------------------------------------------------------------------------


def tag_is_ancestor(tag: str) -> bool:
    """Whether the git tag exists and its commit is HEAD or one of HEAD's ancestors."""
    commit = _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    return bool(commit) and _git("merge-base", "--is-ancestor", commit, "HEAD") is not None


def paid_call_refusals(periods: Iterable[str]) -> list[str]:
    """Why a live run may not start (empty when it may).

    * No paid call before the registration: the tag ``coling-registration`` must exist and be
      an ancestor of HEAD.
    * No call on an item of the test or late period before the freeze amendment F1: the tag
      ``coling-f1`` must exist and be an ancestor of HEAD.

    Dry runs and runs with a scripted client never come here.
    """
    found = []
    if not tag_is_ancestor(REGISTRATION_TAG):
        found.append(
            f"no paid call before the registration: the git tag {REGISTRATION_TAG!r} does not "
            "exist or is not an ancestor of HEAD"
        )
    sealed = sorted(set(periods) & set(SEALED_PERIODS))
    if sealed and not tag_is_ancestor(F1_TAG):
        found.append(
            f"no call on {' or '.join(sealed)}-period items before F1: the git tag {F1_TAG!r} "
            "does not exist or is not an ancestor of HEAD"
        )
    return found


class LiveRunRefused(RuntimeError):
    """A client that can spend money was asked for, and the run is not cleared for one."""


def live_refusals(model: str, template: PromptTemplate, periods: Iterable[str]) -> list[str]:
    """Everything, apart from the budget, that stands between a run and its first paid call
    (empty when nothing does): a route that is not filled in, pilot sentences the template
    still waits for, and the two tags of :func:`paid_call_refusals`."""
    found = route_errors(model)
    if template.pending:
        found.append(
            f"{template.id} waits for the pilot sentences {list(template.pending)} "
            "(PILOT_SENTENCES); it cannot be run live before they are settled"
        )
    return found + paid_call_refusals(periods)


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on ``path`` (created if missing), so that runs launched together
    check and write one after another."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def roots_anchor() -> Path | None:
    """Where the study's two roots are written down: a file in the git directory that every
    worktree of the repository shares, so a run launched from another checkout finds it. None
    outside a git repository."""
    common = _git("rev-parse", "--git-common-dir")
    return (REPO / common).resolve() / ROOTS_ANCHOR_NAME if common else None


def check_roots(out_root: Path, local_root: Path) -> dict:
    """All paid runs share one output root and one local root, so that one ledger, one set of
    spend logs and one cache see every run. The first live run writes its two roots (resolved)
    to :func:`roots_anchor`; a later run with other roots is refused."""
    anchor = roots_anchor()
    if anchor is None:
        raise SystemExit("a live run needs the git repository (to find the shared roots file)")
    mine = {"out_root": str(out_root.resolve()), "local_root": str(local_root.resolve())}
    with _locked(anchor.with_suffix(".lock")):
        if not anchor.is_file():
            anchor.write_text(json.dumps(mine, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return mine
        registered = json.loads(anchor.read_text(encoding="utf-8"))
    if registered != mine:
        raise SystemExit(
            f"every paid run shares one output root and one local root, {registered} (written "
            f"down in {anchor}); this run was given {mine}"
        )
    return mine


def registered_roots() -> dict | None:
    """The two roots the first live run wrote down (None before it, or outside git)."""
    anchor = roots_anchor()
    if anchor is None or not anchor.is_file():
        return None
    return json.loads(anchor.read_text(encoding="utf-8"))


def ledger_refusals(spend_log: Path, model: str, cap_usd: float) -> list[str]:
    """Why the run that owns ``spend_log`` (``<out-root>/<run>/spend_log.jsonl``) may not make a
    paid call yet under the budget rules (empty when it may): its output root must be the
    study's shared one (:func:`check_roots`), and the run must stand in the study ledger, open,
    for this model and with this cap (:func:`declare_run`)."""
    out_root, run = spend_log.parent.parent, spend_log.parent.name
    roots = registered_roots()
    if roots is None or roots.get("out_root") != str(out_root.resolve()):
        return [
            f"the output root {out_root} is not the one every paid run shares "
            f"({roots['out_root'] if roots else 'none is written down yet'})"
        ]
    entry = held_by_run(out_root).get(run)
    declared = entry is not None and entry["open"] and entry["model"] == model
    if not declared or entry["cap_usd"] != cap_usd:
        return [
            f"run {run!r} is not declared in the study ledger for {model} with a cap of "
            f"${cap_usd}; a run declares its cap before its first call"
        ]
    return []


def run_spend(out_root: Path) -> dict[str, float]:
    """Dollars recorded in each run's spend log under ``out_root``, by run name."""
    spent: dict[str, float] = {}
    for log in sorted(out_root.glob("*/spend_log.jsonl")):
        rows = _read_jsonl(log)
        spent[log.parent.name] = sum(float(r["usd"]) for r in rows if r.get("event") == "call")
    return spent


def recorded_spend(out_root: Path, *, exclude: str | None = None) -> float:
    """Dollars recorded in every run's spend log under ``out_root`` (optionally but one run)."""
    return sum(usd_ for run, usd_ in run_spend(out_root).items() if run != exclude)


def held_by_run(out_root: Path) -> dict[str, dict]:
    """The study ledger, run by run: the model, the dollars spent, the declared cap, and the
    dollars the run *holds* against the caps. A declared run holds its cap (or its spend, if
    that is larger) until it finishes; a finished run holds what it spent, and so does a run
    that has a spend log but was never declared.

    The dollars spent are those of the run's spend log, and never less than the largest figure
    the ledger recorded when the run finished: a finished run whose folder was moved or deleted
    afterwards still counts for what it cost."""
    spent = run_spend(out_root)
    state: dict[str, dict] = {}
    closed_at: dict[str, float] = {}
    for row in _read_jsonl(out_root / LEDGER_NAME):
        if row["event"] == "declare":
            state[row["run"]] = {"model": row["model"], "cap_usd": row["cap_usd"], "open": True}
        elif row["event"] == "close" and row["run"] in state:
            state[row["run"]]["open"] = False
            closed_at[row["run"]] = max(closed_at.get(row["run"], 0.0), float(row["usd"]))
    held = {}
    for run in sorted(set(state) | set(spent)):
        entry = state.get(run, {"model": None, "cap_usd": 0.0, "open": False})
        used = max(spent.get(run, 0.0), closed_at.get(run, 0.0))
        held[run] = entry | {
            "spent_usd": used,
            "held_usd": max(used, entry["cap_usd"]) if entry["open"] else used,
        }
    return held


def amendment_log(out_root: Path) -> dict[str, list[tuple[float, str]]]:
    """Every amendment of a model cap in the ledger, by model and in the order they were
    written: the cap each amended declaration set and its note. A cap there that is not a
    finite amount, zero or more, stops everything that reads the caps: it would compare as
    false with every sum, and so switch the checks off."""
    log: dict[str, list[tuple[float, str]]] = {}
    for row in _read_jsonl(out_root / LEDGER_NAME):
        if row["event"] == "declare" and row.get("amendment"):
            cap = float(row["model_cap_usd"])
            if not (math.isfinite(cap) and cap >= 0):
                raise SystemExit(
                    f"the ledger holds an amended cap for {row['model']} that is not a finite "
                    f"amount, zero or more ({cap}); no cap is read from it until it is repaired"
                )
            log.setdefault(row["model"], []).append((cap, str(row["amendment"])))
    return log


def cap_amendments(out_root: Path) -> dict[str, tuple[float, str]]:
    """The model caps that declarations in the ledger replaced with an amendment note: for each
    such model, the cap of its latest amended declaration and that declaration's note."""
    return {model: entries[-1] for model, entries in amendment_log(out_root).items()}


def amended_caps(out_root: Path) -> dict[str, float]:
    """For each model whose cap an amendment in the ledger replaced, the cap now in its place."""
    return {model: cap for model, (cap, _) in cap_amendments(out_root).items()}


def model_caps(out_root: Path) -> dict[str, float]:
    """The cap of every model as it stands under ``out_root``: the registered one
    (``MODEL_CAPS_USD``), or the one that the latest amendment in the ledger put in its place.
    An amended cap holds for every later run of the model until another amendment changes it."""
    return MODEL_CAPS_USD | amended_caps(out_root)


def _append_ledger(out_root: Path, row: dict) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    stamped = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), **row}
    with (out_root / LEDGER_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stamped, sort_keys=True) + "\n")


def declare_run(
    out_root: Path,
    *,
    run: str,
    model: str,
    cap_usd: float,
    study_cap_usd: float = STUDY_CAP_USD,
    model_cap_usd: float | None = None,
    amendment: str | None = None,
) -> dict:
    """Write a run's planned cap into the study ledger, or refuse the run.

    The run is refused when its cap, added to what the other runs of the model hold, would pass
    the model's cap, or, added to what all other runs hold, would pass the study's cap. A run
    declared again (a resumed run, a raised cap) replaces its earlier declaration. The check and
    the write happen under one lock, so two runs launched together cannot both take the same
    dollars.

    The model's cap is the registered one (``MODEL_CAPS_USD``) until an amendment replaces it.
    ``model_cap_usd`` is such an amendment: it needs an ``amendment`` note, which is kept in the
    ledger with the new cap, and from then on that cap is the model's, for this run and for
    every later run of the model, until another amendment changes it (:func:`model_caps`,
    read from the ledger under the same lock). A cap therefore never falls back to the
    registered one without a note. Nor does it fall back to an earlier amendment: a declaration
    that repeats an amendment already in the ledger (the same cap under the same note, as when
    the command line of an amended run is used again to resume it) is accepted while that
    amendment is the one in force, and refused once a later one has replaced it. The caps in
    force must stay within the reserve: those of the eight models, with the amended ones, may
    not sum to more than the study's cap, whether this declaration changes one or only relies
    on one. The study's cap binds beside them as before.
    """
    for what, dollars in (("run", cap_usd), ("model", model_cap_usd), ("study", study_cap_usd)):
        if dollars is not None and not (math.isfinite(dollars) and dollars >= 0):
            raise SystemExit(f"the {what} cap must be a finite amount, zero or more: {dollars}")
    if study_cap_usd > STUDY_CAP_USD:
        raise SystemExit(f"the study cap is ${STUDY_CAP_USD:.2f}; it cannot be raised")
    amendment = (amendment or "").strip() or None  # a blank note is no note
    if model_cap_usd is not None and not amendment:
        raise SystemExit("--model-cap-usd changes a registered cap and needs an --amendment note")
    if amendment and model_cap_usd is None:
        raise SystemExit("--amendment is the note of a changed model cap; give --model-cap-usd")
    with _locked(out_root / f"{LEDGER_NAME}.lock"):
        logged = amendment_log(out_root)
        amended = {name: entries[-1] for name, entries in logged.items()}
        caps = MODEL_CAPS_USD | {name: cap for name, (cap, _) in amended.items()}
        if model_cap_usd is not None:
            given, earlier = (model_cap_usd, amendment), logged.get(model, [])
            if given in earlier[:-1] and given != earlier[-1]:
                raise SystemExit(
                    f"the amendment {amendment!r} (${model_cap_usd:.2f} for {model}) is in the "
                    f"ledger already, and a later one ({earlier[-1][1]!r}) put "
                    f"${earlier[-1][0]:.2f} in its place; an amendment is not applied a second "
                    "time. To resume under the cap in force, leave out --model-cap-usd and "
                    "--amendment; to change the cap again, give a new note"
                )
            caps[model] = model_cap_usd
        model_cap = caps[model]
        if sum(caps.values()) > STUDY_CAP_USD + 1e-9:
            if model_cap_usd is not None:
                raise SystemExit(
                    f"a model cap is raised within the reserve: with ${model_cap:.2f} for "
                    f"{model} the caps of the models would sum to ${sum(caps.values()):.2f}, "
                    f"past the study's ${STUDY_CAP_USD:.2f}"
                )
            raise SystemExit(
                f"the model caps in force (registered, or amended in the ledger) sum to "
                f"${sum(caps.values()):.2f}, past the study's ${STUDY_CAP_USD:.2f}; no run is "
                "declared until an amendment brings them back within it"
            )
        others = {name: h for name, h in held_by_run(out_root).items() if name != run}
        same = sum(h["held_usd"] for h in others.values() if h["model"] == model)
        total = sum(h["held_usd"] for h in others.values())
        if same + cap_usd > model_cap + 1e-9:
            raise SystemExit(
                f"the other runs of {model} hold ${same:.2f}; with this run's ${cap_usd:.2f} cap "
                f"the model would pass its ${model_cap:.2f} cap"
            )
        if total + cap_usd > study_cap_usd + 1e-9:
            raise SystemExit(
                f"the other runs hold ${total:.2f}; with this run's ${cap_usd:.2f} cap the "
                f"study would pass its ${study_cap_usd:.2f} cap"
            )
        row = {
            "event": "declare",
            "run": run,
            "model": model,
            "cap_usd": cap_usd,
            "model_cap_usd": model_cap,
            "model_held_other_runs_usd": round(same, 6),
            "study_held_other_runs_usd": round(total, 6),
        }
        if amendment:
            row["amendment"] = amendment
        elif model in amended:  # the cap is not the registered one: say which note set it
            row["model_cap_amended_by"] = amended[model][1]
        _append_ledger(out_root, row)
    return row


def close_run(out_root: Path, *, run: str, model: str, spent_usd: float) -> None:
    """Mark a run as finished in the ledger: from now on it holds what it spent, not its cap."""
    with _locked(out_root / f"{LEDGER_NAME}.lock"):
        _append_ledger(out_root, {"event": "close", "run": run, "model": model, "usd": spent_usd})


def ledger_summary(out_root: Path) -> dict:
    """Dollars spent and held, by model and in all, against the caps in force (the registered
    ones, or those an amendment in the ledger put in their place)."""
    held = held_by_run(out_root)
    caps = model_caps(out_root)
    models: dict[str, dict] = {}
    for entry in held.values():
        name = entry["model"] or "undeclared"
        slot = models.setdefault(name, {"runs": 0, "spent_usd": 0.0, "held_usd": 0.0})
        slot["runs"] += 1
        slot["spent_usd"] += entry["spent_usd"]
        slot["held_usd"] += entry["held_usd"]
    for name, slot in models.items():
        slot["cap_usd"] = caps.get(name)
    return {
        "models": models,
        "spent_usd": round(sum(e["spent_usd"] for e in held.values()), 6),
        "held_usd": round(sum(e["held_usd"] for e in held.values()), 6),
        "study_cap_usd": STUDY_CAP_USD,
    }


# ---------------------------------------------------------------------------------------------
# The run sheet: projected calls and cost per model at given item counts
# ---------------------------------------------------------------------------------------------

NOT_GEMINI = tuple(m for m in STUDY_MODELS if m != "gemini-3.8-flash")
TRIAL_NOTE = "cost trial: dev items, once per template a model uses"
E6_NOTE = "counted in calls and priced as literal-v1; E6's own prompt comes with its amendment"
SEC_NOTE = "the three secondary lists together: TBD, silent, stale at issue"
TWO_BY_TWO_NOTE = "the three masked or shifted cells; the fourth cell is e3-b"
PARA_NOTE = (
    f"the three paraphrases of (b), one run each ({', '.join(PARAPHRASE_TEXTS)}); priced as "
    f"{PARAPHRASE_OF}"
)
SAMPLES_NOTE = "20 samples at temperature 1 under condition (a)"


@dataclass(frozen=True)
class SheetLine:
    """One line of the run sheet: a template read by some models on one set of items."""

    name: str
    experiment: str
    template: str
    count: str
    """The name of the item count the line multiplies (given with ``--count``)."""
    models: tuple[str, ...]
    per_item: int = 1
    """Calls per item and model: samples, cells or paraphrases."""
    note: str = ""


RUN_SHEET: tuple[SheetLine, ...] = (
    SheetLine("e2-literal", "E2", "literal-v1", "e2", STUDY_MODELS),
    SheetLine("e2-literal-free", "E2", "literal-free-v1", "e2", STUDY_MODELS),
    SheetLine("e3-a", "E3", "predictive-v1", "e3", STUDY_MODELS),
    SheetLine("e3-b", "E3", "predictive-track-v1", "e3", STUDY_MODELS),
    SheetLine("e3-c", "E3", "literal-v1", "e3", STUDY_MODELS),
    SheetLine("e4-probe", "E4", "probe-v1", "probe", NOT_GEMINI),
    SheetLine("e5", "E5", "literal-v1", "e5", NOT_GEMINI),
    SheetLine("trial-literal", "trial", "literal-v1", "trial", STUDY_MODELS, note=TRIAL_NOTE),
    SheetLine("trial-literal-free", "trial", "literal-free-v1", "trial", STUDY_MODELS),
    SheetLine("trial-a", "trial", "predictive-v1", "trial", STUDY_MODELS),
    SheetLine("trial-b", "trial", "predictive-track-v1", "trial", STUDY_MODELS),
    SheetLine("trial-probe", "trial", "probe-v1", "trial", NOT_GEMINI),
    SheetLine("e6", "E6", "literal-v1", "e6", NOT_GEMINI, note=E6_NOTE),
    SheetLine("e3-secondary-a", "E3", "predictive-v1", "e3_secondary", PRIMARIES, note=SEC_NOTE),
    SheetLine("e3-secondary-b", "E3", "predictive-track-v1", "e3_secondary", PRIMARIES),
    SheetLine("e3-secondary-c", "E3", "literal-v1", "e3_secondary", PRIMARIES),
    SheetLine("dev-a", "dev", "predictive-v1", "dev", PRIMARIES),
    SheetLine("dev-b", "dev", "predictive-track-v1", "dev", PRIMARIES),
    SheetLine("dev-c", "dev", "literal-v1", "dev", PRIMARIES),
    SheetLine("e4-2x2", "E4", "predictive-track-v1", "twobytwo", PRIMARIES, 3, TWO_BY_TWO_NOTE),
    SheetLine("e3-paraphrases", "E3", "predictive-track-v1", "paraphrase", PRIMARIES, 3, PARA_NOTE),
    SheetLine("e3-samples", "E3", "predictive-v1", "samples", PRIMARIES, 20, SAMPLES_NOTE),
)
"""The study's runs, in the order of the calls table of PLAN section 9: which template each item
set is read with, by which models, and with how many calls per item. ``gemini-3.8-flash`` reads
E2, the three E3 conditions and its cost trial only. The item counts are not here: they are
given on the command line (``--count``), so the budget table can be printed again whenever a
count changes. With the plan's fixed counts (e2 120, probe 300, e5 800, trial 20, twobytwo 300,
paraphrase 200, samples 300) the calls per model are those of the plan's formulas: 320 + 3 e3
for gemini-3.8-flash, 1,440 + 3 e3 for the other secondaries, and 8,940 + 3 (e3 + e3_secondary +
dev) for the primaries."""
SHEET_COUNTS = tuple(dict.fromkeys(line.count for line in RUN_SHEET))
SHEET_TRACK_ROWS = 33


def _sheet_track() -> TrackRecord:
    """A stand-in track record of full size (33 table rows, 10 examples), for pricing the
    track-record prompt before the real file exists."""
    rows = tuple(
        replace(
            CANARY_TRACK.slip_table[n % 2],
            form=f"form {n // 3 + 1}",
            revision=REVISION_BUCKETS[n % 3],
        )
        for n in range(SHEET_TRACK_ROWS)
    )
    examples = tuple(CANARY_TRACK.examples[n % 2] for n in range(MAX_EXAMPLES))
    return replace(CANARY_TRACK, slip_table=rows, examples=examples)


def sheet_prompt_tokens(
    items: Sequence[ReadItem] | None = None, track: TrackRecord | None = None
) -> dict[str, float]:
    """Mean prompt tokens per template: over ``items`` if given, else for the canary item; with
    ``track`` if given, else with the full-size stand-in."""
    items = list(items) if items else [CANARY_ITEM]
    track = track if track is not None else _sheet_track()
    means = {}
    for template in TEMPLATES.values():
        tokens = [estimate_tokens(render_for(template, item, track=track)) for item in items]
        means[template.id] = sum(tokens) / len(tokens)
    return means


def run_sheet(
    counts: dict[str, int],
    *,
    items: Sequence[ReadItem] | None = None,
    track: TrackRecord | None = None,
    prices: dict[str, tuple[float, float]] | None = None,
    per_call_usd: dict[str, float] | None = None,
    repair_rate: float = 0.0,
) -> dict:
    """Projected calls and cost per model for the runs of ``RUN_SHEET`` at the given item counts.

    A call is priced from the price table (``ROUTES``, else the ladder): prompt tokens times the
    input price plus output tokens times the output price. ``usd_typical`` uses the estimated
    prompt length and the typical output length (for a reasoning model, the median hidden
    reasoning); ``usd_upper`` uses the generous figures of the per-call cap check. ``prices``
    replaces a model's prices (to see what another endpoint than the one in ``ROUTES`` costs),
    ``per_call_usd`` replaces a model's typical cost per call by a measured mean (the cost
    trial's), and ``repair_rate`` adds that share of calls for repairs.

    Each run (a line read by one model) also gets a suggested cap: the model's cap split over
    its runs in proportion to their upper estimates, rounded down, so the caps of a model's runs
    never sum to more than the model's cap. A run split into shards splits its cap. Sends
    nothing.
    """
    unknown = sorted(set(counts) - set(SHEET_COUNTS))
    if unknown:
        raise SystemExit(f"unknown counts {unknown}; the sheet knows {list(SHEET_COUNTS)}")
    prices, per_call_usd = prices or {}, per_call_usd or {}
    tokens = sheet_prompt_tokens(items, track)
    endpoints = {}
    for model in STUDY_MODELS:
        endpoint = route_endpoint(model)
        if model in prices:
            endpoint = replace(
                endpoint,
                price_input_per_mtok=prices[model][0],
                price_output_per_mtok=prices[model][1],
                price_date="given on the command line",
            )
        endpoints[model] = endpoint
    models = {
        m: {"calls": 0, "usd_typical": 0.0, "usd_upper": 0.0, "lines": {}} for m in STUDY_MODELS
    }
    lines = []
    for line in RUN_SHEET:
        n_items = counts.get(line.count, 0)
        first = n_items * line.per_item
        calls = first + math.ceil(first * repair_rate - 1e-9)
        kind = TEMPLATES[line.template].kind
        prompt = tokens[line.template]
        lines.append(
            asdict(line) | {"items": n_items, "calls_per_model": calls, "prompt_tokens": prompt}
        )
        if not calls:
            continue
        for model in line.models:
            endpoint = endpoints[model]
            typical = per_call_usd.get(
                model, usd(round(prompt), output_tokens(model, kind, upper=False), endpoint)
            )
            upper = usd(
                math.ceil(1.25 * prompt) + 16, output_tokens(model, kind, upper=True), endpoint
            )
            slot = models[model]
            slot["calls"] += calls
            slot["usd_typical"] += calls * typical
            slot["usd_upper"] += calls * max(upper, typical)
            slot["lines"][line.name] = {
                "calls": calls,
                "usd_typical": round(calls * typical, 4),
                "usd_upper": round(calls * max(upper, typical), 4),
                "share": calls * max(upper, typical),
            }
    for model, slot in models.items():
        endpoint = endpoints[model]
        for entry in slot["lines"].values():  # the model's cap, split in proportion to the uppers
            share = entry.pop("share") / slot["usd_upper"]
            entry["cap_usd"] = math.floor(1e4 * MODEL_CAPS_USD[model] * share) / 1e4
        slot |= {
            "usd_typical": round(slot["usd_typical"], 4),
            "usd_upper": round(slot["usd_upper"], 4),
            "usd_per_call_typical": round(slot["usd_typical"] / max(1, slot["calls"]), 6),
            "cap_usd": MODEL_CAPS_USD[model],
            "typical_within_cap": slot["usd_typical"] <= MODEL_CAPS_USD[model],
            "upper_within_cap": slot["usd_upper"] <= MODEL_CAPS_USD[model],
            "usd_per_mtok": [endpoint.price_input_per_mtok, endpoint.price_output_per_mtok],
            "price_date": endpoint.price_date,
            "per_call_usd_given": model in per_call_usd,
        }
    caps = sum(MODEL_CAPS_USD.values())
    return {
        "counts": {name: counts.get(name, 0) for name in SHEET_COUNTS},
        "counts_not_given": [name for name in SHEET_COUNTS if name not in counts],
        "lines": lines,
        "models": models,
        "total": {
            "calls": sum(m["calls"] for m in models.values()),
            "usd_typical": round(sum(m["usd_typical"] for m in models.values()), 4),
            "usd_upper": round(sum(m["usd_upper"] for m in models.values()), 4),
            "caps_usd": caps,
            "study_cap_usd": STUDY_CAP_USD,
            "reserve_usd": STUDY_CAP_USD - caps,
        },
        "repair_rate": repair_rate,
        "token_method": token_method(),
        "prompt_tokens_from": "the items given" if items else "the canary item",
        "track_record_from": "the file given" if track is not None else "a full-size stand-in",
        "note": (
            "typical uses the median hidden reasoning, which understates the mean of a reasoning "
            "model; give the cost trial's mean with --per-call-usd"
        ),
    }


def run_sheet_markdown(sheet: dict) -> str:
    """The run sheet as three tables: the budget table of PLAN section 9 (per model), the runs
    with their templates, items and calls, and a suggested cap for every run."""
    out = [
        "| Model | Calls | Cost per call | Estimate | Upper estimate | Cap |",
        "|---|---|---|---|---|---|",
    ]
    for model, slot in sheet["models"].items():
        out.append(
            f"| {model} | {slot['calls']:,} | ${slot['usd_per_call_typical']:.5f} | "
            f"${slot['usd_typical']:.2f} | ${slot['usd_upper']:.2f} | ${slot['cap_usd']:.0f} |"
        )
    total = sheet["total"]
    out.append(
        f"| **All** | **{total['calls']:,}** | | **${total['usd_typical']:.2f}** | "
        f"${total['usd_upper']:.2f} | caps ${total['caps_usd']:.0f}; reserve "
        f"${total['reserve_usd']:.0f} |"
    )
    out += [
        "",
        "| Run | Template | Items | Calls per model | Models | Note |",
        "|---|---|---|---|---|---|",
    ]
    for line in sheet["lines"]:
        out.append(
            f"| {line['name']} | {line['template']} | {line['items']:,} | "
            f"{line['calls_per_model']:,} | {len(line['models'])} | {line['note']} |"
        )
    names = list(sheet["models"])
    out += ["", "Suggested cap per run, in dollars (each column sums to at most the model's cap):"]
    out += ["", "| Run | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for line in sheet["lines"]:
        caps = [sheet["models"][m]["lines"].get(line["name"], {}).get("cap_usd") for m in names]
        if any(cap is not None for cap in caps):
            cells = ["" if cap is None else f"{cap:.4f}" for cap in caps]
            out.append(f"| {line['name']} | " + " | ".join(cells) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m analysis.coling.read", description=__doc__)
    ap.add_argument("--items", type=Path, help="JSON Lines, one statement event per line")
    ap.add_argument("--template", choices=sorted(TEMPLATES), default="literal-v1")
    ap.add_argument("--model", action="append", choices=sorted(LADDER), help="repeatable (dry run)")
    ap.add_argument(
        "--track-record", type=Path, help="needed by predictive-track-v1 and its paraphrases"
    )
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--mask-names", action="store_true")
    ap.add_argument("--shift-years", type=int, default=0)
    ap.add_argument("--shard", help="K/N: read only the items of shard K of N (by item id)")
    ap.add_argument("--limit", type=int, help="read only the first N items (of the shard)")
    ap.add_argument("--dry-run", action="store_true", help="render and price; no call")
    ap.add_argument("--show", type=int, default=0, help="dry run: print the first N prompts")
    ap.add_argument("--print-schemas", action="store_true")
    ap.add_argument("--print-pins", action="store_true", help="every template id with its pin")
    ap.add_argument("--run-sheet", action="store_true", help="projected calls and cost per model")
    ap.add_argument("--count", action="append", default=[], metavar="NAME=N", help="run sheet")
    ap.add_argument(
        "--price", action="append", default=[], metavar="MODEL=IN,OUT", help="run sheet: $/1M"
    )
    ap.add_argument(
        "--per-call-usd", action="append", default=[], metavar="MODEL=USD", help="run sheet"
    )
    ap.add_argument("--repair-rate", type=float, default=0.0, help="run sheet: share of repairs")
    ap.add_argument("--sheet-format", choices=("json", "md"), default="json")
    ap.add_argument(
        "--check-runs",
        action="store_true",
        help="item ids answered per model and condition under --out-root; with --items and "
        "--template, compared with the expected ids",
    )
    ap.add_argument(
        "--run",
        action="append",
        metavar="NAME",
        help="check runs: only the runs of these names (repeatable); every run without it",
    )
    ap.add_argument(
        "--run-name", help="one model, template, condition, shard and item set per run name"
    )
    ap.add_argument(
        "--spend-cap-usd", type=float, help="cumulative for the run: earlier invocations count"
    )
    ap.add_argument(
        "--study-cap-usd",
        type=float,
        default=STUDY_CAP_USD,
        help="what all runs hold plus this run's cap must fit in it; it can only be lowered",
    )
    ap.add_argument(
        "--model-cap-usd",
        type=float,
        help="replaces the model's cap, for this run and the model's later runs; needs a note",
    )
    ap.add_argument("--amendment", help="the note kept in the ledger with --model-cap-usd")
    ap.add_argument(
        "--declare-only", action="store_true", help="write the run's cap to the ledger; no call"
    )
    ap.add_argument("--max-physical-calls", type=int, default=20000)
    ap.add_argument("--allow-live", action="store_true")
    ap.add_argument(
        "--allow-test-items", action="store_true", help="test or late items: only after F1"
    )
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--local-root", type=Path, default=LOCAL_ROOT)
    return ap


def _pairs(values: Sequence[str], option: str) -> dict[str, str]:
    pairs = {}
    for value in values:
        name, sep, rest = value.partition("=")
        if not sep or not name or not rest:
            raise SystemExit(f"{option} takes NAME=VALUE: {value!r}")
        pairs[name] = rest
    return pairs


def _check_args(args: argparse.Namespace, items: Sequence[ReadItem]) -> None:
    if args.samples < 1:
        raise SystemExit("--samples must be at least 1")
    if args.samples > 1 and args.temperature == 0:
        raise SystemExit("several samples need --temperature above 0")
    if args.dry_run:
        return
    if len(args.model) != 1:
        raise SystemExit("a live run reads with exactly one --model")
    if not args.allow_live and not args.declare_only:
        raise SystemExit("this makes paid calls; pass --allow-live (or use --dry-run)")
    if not args.run_name or not _RUN_NAME.match(args.run_name):
        raise SystemExit("--run-name: lowercase letters, digits, '.', '-' or '_'")
    cap = args.spend_cap_usd
    if cap is None or not (math.isfinite(cap) and cap > 0):
        raise SystemExit("a live run needs a positive --spend-cap-usd")
    if args.model[0] not in ROUTES:
        raise SystemExit("; ".join(route_errors(args.model[0])))
    if args.declare_only:
        return
    sealed = sum(1 for i in items if i.period in SEALED_PERIODS)
    if sealed and not args.allow_test_items:
        raise SystemExit(
            f"{sealed} items are in the test or late period; read them only after the freeze "
            "amendment F1 is registered (--allow-test-items)"
        )
    problems = live_refusals(args.model[0], TEMPLATES[args.template], (i.period for i in items))
    if problems:
        raise SystemExit("; ".join(problems))


IDENTITY_KEYS = (
    "model",
    "model_id",
    "provider_object",
    "template",
    "temperature",
    "mask_names",
    "shift_years",
    "track_record_sha256",
    "shard",
    "limit",
    "samples",
    "items_sha256",
)
"""What a run name stands for. An invocation under a name that already has one must give the
same value for every key (:func:`_check_run_identity`). The items file is identified by the hash
of the whole file, which every shard and every resumption of a run shares; with the shard and
the limit it fixes the item set, and with the sample count the rows the run is to write."""


def _check_run_identity(out_dir: Path, invocation: dict) -> None:
    """A run name keeps one model, route, template, condition, shard and item set, so its cap,
    its spend log and its readings stay meaningful: the readings file is written whole by every
    invocation, and one under another item set would replace the rows of the first. The same
    settings resume the run from the cache."""
    lines = _read_jsonl(out_dir / "invocations.jsonl")
    first = lines[0] if lines else {}
    clash = {
        k: (first.get(k), invocation[k])
        for k in IDENTITY_KEYS
        if lines and first.get(k) != invocation[k]
    }
    if clash:
        raise SystemExit(
            f"run {out_dir.name!r} was started with other settings (then, now): {clash}; its "
            "readings would be overwritten, so this invocation needs another --run-name"
        )


def _live(
    args: argparse.Namespace,
    items: Sequence[ReadItem],
    track: TrackRecord | None,
    items_in_file: int,
) -> int:
    model = args.model[0]
    route = ROUTES[model]
    out_dir, local_dir = args.out_root / args.run_name, args.local_root / args.run_name
    identity = {
        "model": model,
        "model_id": route.model_id,
        "provider_object": provider_object(route),
        "template": args.template,
        "temperature": args.temperature,
        "mask_names": args.mask_names,
        "shift_years": args.shift_years,
        "track_record_sha256": track.sha256 if track else None,
        "shard": args.shard,
        "limit": args.limit,
        "samples": args.samples,
        "items_sha256": _sha256_file(args.items),
    }
    _check_run_identity(out_dir, identity)
    roots = check_roots(args.out_root, args.local_root)
    declared = declare_run(
        args.out_root,
        run=args.run_name,
        model=model,
        cap_usd=args.spend_cap_usd,
        study_cap_usd=args.study_cap_usd,
        model_cap_usd=args.model_cap_usd,
        amendment=args.amendment,
    )
    if args.declare_only:
        print(json.dumps(declared, indent=2, sort_keys=True))
        return 0
    endpoint, guard = build_transport(
        model,
        spend_log=out_dir / "spend_log.jsonl",
        spend_cap_usd=args.spend_cap_usd,
        max_physical_calls=args.max_physical_calls,
        template=TEMPLATES[args.template],
        periods={i.period for i in items},
    )
    reader = Reader(
        model=model,
        template=TEMPLATES[args.template],
        endpoint=endpoint,
        transport=guard,
        cache=ReadCache(args.local_root / "cache"),
        decoding=decoding_for(args.temperature),
        track=track,
        masker=NameMasker() if args.mask_names else None,
        shift_years=args.shift_years,
        route=route,
    )
    invocation = {
        **identity,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "items_file": str(args.items),
        "items_in_file": items_in_file,
        "items": len(items),
        "spend_cap_usd": args.spend_cap_usd,
        "ledger": declared,
        "git_sha": _git("rev-parse", "HEAD"),
    }
    rows: list[dict] = []
    t0 = time.perf_counter()
    status = "error"
    try:
        try:
            rows, status = read_items(reader, items, samples=args.samples, rows=rows)
        except Exception as exc:
            status = f"error: {type(exc).__name__}: {exc}"[:400]
            raise
        finally:
            meta = {
                "run_name": args.run_name,
                "status": status,
                "track_record": str(args.track_record) if args.track_record else None,
                "git": {
                    "sha": _git("rev-parse", "HEAD"),
                    "branch": _git("branch", "--show-current"),
                    "registration": _git("rev-parse", "--verify", "--quiet", REGISTRATION_TAG),
                    "f1": _git("rev-parse", "--verify", "--quiet", F1_TAG),
                    "read_py_modified": _modified(Path(__file__)),
                },
                "python": platform.python_version(),
                "roots": roots,
                **{k: invocation[k] for k in ("items_sha256", "items_in_file", "limit")},
                **{k: invocation[k] for k in ("samples", "spend_cap_usd", "shard")},
                **{k: invocation[k] for k in ("temperature", "mask_names", "shift_years")},
            }
            manifest = write_run(
                rows,
                reader,
                out_dir=out_dir,
                local_dir=local_dir,
                meta=meta,
                items=items,
                samples=args.samples,
            )
            if manifest["complete"]:
                close_run(args.out_root, run=args.run_name, model=model, spent_usd=guard.spent_usd)
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


def _run_sheet_command(
    args: argparse.Namespace, items: Sequence[ReadItem] | None, track: TrackRecord | None
) -> int:
    counts = {name: int(n) for name, n in _pairs(args.count, "--count").items()}
    prices = {}
    for model, pair in _pairs(args.price, "--price").items():
        low, _, high = pair.partition(",")
        prices[model] = (float(low), float(high))
    per_call = {m: float(v) for m, v in _pairs(args.per_call_usd, "--per-call-usd").items()}
    stray = sorted((set(prices) | set(per_call)) - set(STUDY_MODELS))
    if stray:
        raise SystemExit(f"not among the eight readers: {stray}")
    sheet = run_sheet(
        counts,
        items=items,
        track=track,
        prices=prices,
        per_call_usd=per_call,
        repair_rate=args.repair_rate,
    )
    if args.sheet_format == "md":
        print(run_sheet_markdown(sheet))
    else:
        print(json.dumps(sheet, indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.run and not args.check_runs:
        raise SystemExit("--run goes with --check-runs; a live run is named with --run-name")
    if args.print_schemas:
        print(json.dumps(SCHEMAS, indent=2))
        return 0
    if args.print_pins:
        pins = template_pins()
        print(json.dumps(pins, indent=2, sort_keys=True))
        return 0 if all(t["matches_pin"] for t in pins["templates"].values()) else 1
    check_frozen()
    all_items = load_items(args.items) if args.items is not None else None
    track = load_track_record(args.track_record) if args.track_record else None
    if args.run_sheet:
        return _run_sheet_command(args, all_items, track)
    if args.check_runs:
        expected = [i.item_id for i in all_items] if all_items is not None else None
        template_id = args.template if expected is not None else None
        report = check_runs(args.out_root, expected=expected, template=template_id, runs=args.run)
        print(json.dumps(report, indent=2, sort_keys=True))
        named = set(args.run or ())
        absent = sorted(named - set(runs_with_readings(args.out_root)))
        if absent:  # a name that matches no run must not pass for a run that is ready
            print(f"--run: no readings under {args.out_root} for {absent}", file=sys.stderr)
        # nor may a named run that counts for nothing: one of another template than the one
        # asked for, or one that holds no row and no manifest, is in no entry of the report
        idle = sorted(named - set(absent) - {run for entry in report for run in entry["runs"]})
        if idle:
            print(f"--run: the report holds nothing of {idle}", file=sys.stderr)
        found = (bool(report) or expected is None) and not absent and not idle
        return 0 if found and all(entry["ready"] for entry in report) else 3
    if all_items is None or not args.model:
        raise SystemExit("--items and --model are required")
    shard = parse_shard(args.shard)
    items = [i for i in all_items if shard is None or shard_of(i.item_id, shard[1]) == shard[0]]
    items = items[: args.limit]
    _check_args(args, items)
    template = TEMPLATES[args.template]
    if template.needs_track and track is None:
        raise SystemExit(f"{template.id} needs --track-record")
    if not template.needs_track:
        track = None  # a record given to a template that does not show it plays no part
    if track is not None:
        shown = sorted({ex.item_id for ex in track.examples} & {i.item_id for i in items})
        if shown:
            raise SystemExit(f"{len(shown)} items are examples of the track record: {shown[:5]}")
    if track is not None and not args.dry_run:
        problems = track_refusals(track, items)
        if problems:
            raise SystemExit("; ".join(problems))
    if not args.dry_run:
        return _live(args, items, track, len(all_items))
    masker = NameMasker() if args.mask_names else None
    moved = transform_track(track, masker, args.shift_years) if track else None
    for item in items[: args.show]:
        print(f"===== {item.item_id} ({item.period})")
        print(render_for(template, item, track=moved, masker=masker, shift_years=args.shift_years))
    summary = dry_run(
        items,
        models=args.model,
        template=template,
        track=track,
        samples=args.samples,
        temperature=args.temperature,
        mask_names=args.mask_names,
        shift_years=args.shift_years,
        cache_dir=args.local_root / "cache",
    )
    summary["shard"] = args.shard
    summary["study_spend_recorded_usd"] = round(recorded_spend(args.out_root), 4)
    summary["ledger"] = ledger_summary(args.out_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
