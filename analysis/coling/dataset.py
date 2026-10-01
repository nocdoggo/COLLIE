"""Dataset builder: one row per distinct statement, with its display row, split, frozen rule
reading, eligibility and, for the train period only, its outcomes (PLAN.md sections 2.3, 2.5, 3).

Inputs. The open events table of ``corpus.py`` (every period, first-sight fields only), the open
train outcomes (``outcomes_train.csv.gz``: train-period events followed to the train horizon),
the capture manifest (the capture days) and the form classifier (``forms.py`` on the frozen
``rules.py``). Nothing under ``external_data/sealed/`` is read, listed or written, and an outcome
table that holds anything but train-period rows is refused (``require_train``).

Unit. One row per ``statement_group_id``. The *display row* is the presentation that readers and
annotators see and whose bracket is the primary outcome: among the members at risk under
definition B, the one with the smallest ``draw_key("display/<statement_group_id>", event_id)``; a
statement with no member at risk shows the member with the smallest ``event_id``. No outcome
field enters the draw. ``audit_sample.py`` applies the same rule to the annotation sheets.
``event_id`` and every first-sight field of the table (thread, episode, presentation, texts,
revision index, first-seen capture) are those of the display row.

Seeded draws. Every draw orders ids by ``sha256("<seed>\\x1f<tag>\\x1f<id>")`` with seed 20261001
and takes the first n (``seeded_order``). The order does not depend on the order of the input and
an id keeps its place when other ids come or go.

Splits (by statement date). fit before 2021-01-01; dev 2021-01-01 to 2022-12-31; test 2023-01-01
to 2025-12-31; late from 2026-01-01. ``period`` keeps the corpus builder's two values (train,
test), where test includes late.

Reading. ``form``, ``stated_end`` and ``stale_at_issue`` come from the frozen rule reading through
``forms.statement_forms``; ``stated_end`` (the plan's ``t_end``) is set only for the nine dated
forms, and a statement is stale at issue when ``stated_end`` is before its date. ``merged_form``
and ``form_label`` apply the merge of small classes. ``revision`` is the bucket of the display
row's revision index (first, second, third or later).

Analysis sets (``analysis_set``, statements at risk under B only): ``dated`` (a dated form, not
stale), ``stale`` (a dated form, stale at issue), ``tbd``, ``silent``, or ``none`` (vague, no
date, discontinuation or distractor: in no outcome analysis). Blank when not at risk under B.

Horizons. ``horizon_a`` and ``horizon_b`` are the two dates the forecast questions ask about, as
``read.horizons`` sets them: ``stated_end`` and 90 days later for a dated form; 90 and 180 days
after the statement date for ``tbd`` and ``silent``. ``horizon_reached`` says whether
``horizon_b`` is on or before the last capture.

Eligibility uses the statement date, first-sight fields and the stated period, never an outcome.
``eligible`` is true for a ``dated``, ``tbd`` or ``silent`` statement of the test or late split
whose ``horizon_b`` is reached, for every such statement of the train period (there the captures
decide what can be scored), and for every ``stale`` statement. ``e3_eligible`` is the E3 list:
test split, ``dated``, ``eligible``. ``delayed_entry`` marks a ``dated`` statement first captured
after its stated period ended.

Outcomes (train period only; every outcome column is blank on a test or late row).

* Primary: the display row's bracket under B (``outcome``, ``censor_reason``, ``lower_date``,
  ``upper_date``, days from the statement date).
* Secondary, all covered presentations (``*_all``): the statement-level bracket of ``corpus.py``
  (maximum over the at-risk members).
* Sensitivity, any covered presentation (``*_any``): the minimum in place of the maximum. The
  statement recovers when the first at-risk member that is not discontinued recovers, with
  ``lower = min lower`` over those members and ``upper = min upper`` over the recovered ones; it
  is censored when none of them has recovered; it is discontinued when every member is.
* Horizon events: yes when the bracket shows recovery with ``upper <= horizon``; no when ``lower
  >= horizon`` or the outcome is a discontinuation; undetermined otherwise. ``E_end`` and
  ``E_end90`` are set for ``dated`` statements and ``scoreable`` says that both are determined.
  ``E_90`` and ``E_180`` with ``scoreable_fallback`` are the same for ``tbd`` and ``silent``.
* Time to recovery in days from the statement date, capped at 365 (``ttr_*``): ``interval``
  when recovery lies in ``(ttr_lower_days, ttr_upper_days]`` (``ttr_mid_days`` is the midpoint);
  ``at_cap`` when it is known to be the cap (a discontinuation, or a lower bound at or past 365
  days); ``right_censored`` when the outcome is censored before the cap (only the lower bound).

``attach_outcomes`` holds these rules and takes any outcome table of ``corpus.py``; the builder
gives it train rows only and stops when a train statement at risk has no outcome row. The counts
of scoreable test statements come from a separate counts-only script over the sealed file, which
can call the same function and ``scoreable_counts`` (scoreable and undetermined, with no
breakdown by outcome). ``train_outcome_counts`` adds the mix of the two horizon events and
refuses any row that is not of the train period.

Outputs (all three are rewritten by the one command below).

* ``out/statements.csv.gz``: the table, sorted by ``statement_group_id``.
* ``out/eligible_e3.csv``: the E3 eligible list, sorted by ``statement_group_id``, with the
  display ``event_id``, ``thread_id``, ``episode_id``, the statement date, the form, ``stated_end``
  and one 0/1 column per seeded subset (``SUBSETS``: probe, samples20, paraphrase, twobytwo,
  each stratified by statement year in proportion, and reference_check, a simple draw). Each
  subset is a draw of its own, so they may overlap. Every subset leaves out the statements of the
  guide's Appendix A and the statement the harness builds its fixed test item on
  (``read.CANARY_ITEM``), with the same generic, company and normalised text at another date.
  ``reference_check`` also leaves out the statements of the first draw (the pilot, the check
  set, its reserve and the literal sample: ``sample_<name>.csv`` under ``--samples``, written by
  ``audit_sample.py``), again with the same text at another date, so that no annotator is shown
  the rule reading of a statement they labelled. A list that is not on disk leaves nothing out;
  the counts file names the lists that were read and those that were missing, and
  ``reference_check`` is final only when all four were read and every id on them is in the
  statement table.
* ``out/dataset_counts.json``: every count PLAN.md sections 2 and 3 take from this builder, the
  seeds and hashes of the lists (the eligible list, the three secondary lists, the subsets, the
  late list and the scoreable dev statements), and the hashes of the inputs and outputs. For the
  test and late splits it holds counts of statements only; train-period outcomes are counted by
  fit and dev.

Item files for the reading harness are written only when ``--items`` names a folder
(``write_items``): JSON Lines in the schema of ``read.ReadItem``, with ``item_id`` the
``statement_group_id``. Probe items carry the fields of ``PROBE_KEYS`` and nothing else: no
stated end, form, revision bucket or notice text.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.dataset              # write the three outputs
    PYTHONPATH=. python -m analysis.coling.dataset --check      # recompute and compare
    PYTHONPATH=. python -m analysis.coling.dataset --items analysis/coling/out/items
    PYTHONPATH=. python -m analysis.coling.dataset --captures external_data/fda_wayback_csv

The default inputs are ``analysis/coling/out/events.csv.gz``, ``outcomes_train.csv.gz`` and
``capture_manifest.csv``, the guide (its Appendix A) and the first-draw lists under
``analysis/coling/out/audit/samples`` when they exist. ``--captures`` builds the corpus in memory
from the capture files instead (after the manifest check), keeps the events and the train-period
outcome rows, and writes nothing but this module's outputs. The counts file records which of the
two it was built from, so ``--check`` takes the same flags as the run that wrote it. After the
first draw is written (``audit_sample draw``), or after any change to ``forms.py``, ``rules.py``
or this file, run the command again: ``--check`` and the tests report stale outputs until then.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.coling import forms, rules
from analysis.coling.corpus import norm_text

SEED = 20261001
DEFINITION = "B"
HORIZON_DAYS = 90
FALLBACK_DAYS = (90, 180)
CAP_DAYS = 365
TEST_START = forms.TEST_START
SPLITS = forms.SPLITS
TRAIN_SPLITS = forms.TRAIN_SPLITS
REVISION_BUCKETS = ("first", "second", "third or later")
FALLBACK_FORMS = ("tbd", "silent")
ANALYSIS_SETS = ("dated", "stale", "tbd", "silent", "none")
DISPLAY_TAG = "display/"  # followed by the statement_group_id
OUT = Path("analysis/coling/out")
EVENTS = OUT / "events.csv.gz"
OUTCOMES = OUT / "outcomes_train.csv.gz"
MANIFEST = OUT / "capture_manifest.csv"
GUIDE = Path("analysis/coling/plan/AUDIT_GUIDE.md")
SAMPLES = OUT / "audit" / "samples"
FIRST_DRAW = ("pilot", "check", "reserve", "literal")
"""The samples people label, drawn before every other (``<SAMPLES>/sample_<name>.csv``)."""
STATEMENTS = OUT / "statements.csv.gz"
ELIGIBLE = OUT / "eligible_e3.csv"
COUNTS = OUT / "dataset_counts.json"
COMMAND = "PYTHONPATH=. python -m analysis.coling.dataset"

EVENT_FIELDS = (
    "event_id",
    "statement_group_id",
    "thread_id",
    "generic_id",
    "episode_id",
    "listing",
    "period",
    "event_date",
    "first_seen_date",
    "days_capture_after_event",
    "left_truncated",
    "type_of_update",
    "revision_index",
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
OUTCOME_FIELDS = (
    "event_id",
    "event_date",
    "period",
    "statement_group_id",
    "followup_end_date",
    *(
        f"{name}_{DEFINITION}"
        for name in (
            "outcome",
            "censor_reason",
            "lower_date",
            "upper_date",
            "observable31",
            "group_outcome",
            "group_lower_date",
            "group_upper_date",
        )
    ),
)

FIRST_SIGHT_COLUMNS = (
    "statement_group_id",
    "event_id",
    "thread_id",
    "generic_id",
    "episode_id",
    "listing",
    "period",
    "split",
    "event_date",
    "n_presentations",
    "n_at_risk_A",
    "n_at_risk_B",
    "at_risk_A",
    "at_risk_B",
    "first_seen_date",
    "days_capture_after_event",
    "left_truncated",
    "first_seen_in_test_period",
    "revision_index",
    "revision",
    "type_of_update",
    "generic_name",
    "company_name",
    "presentation",
    "therapeutic_category",
    "initial_posting_date",
    "listing_age_days",
    "reason_for_shortage",
    "availability_class",
    "availability_text",
    "related_text",
    "statement_text",
    "form",
    "merged_form",
    "form_label",
    "dated",
    "no_year",
    "distractor_dates",
    "statement_type",
    "certainty",
    "granularity",
    "bound",
    "stated_start",
    "stated_end",
    "stale_at_issue",
    "silent",
    "analysis_set",
    "horizon_a",
    "horizon_b",
    "horizon_rule",
    "horizon_reached",
    "eligible",
    "e3_eligible",
    "delayed_entry",
)
VARIANTS = ("", "_all", "_any")
OUTCOME_COLUMNS = (
    "outcome",
    "censor_reason",
    "lower_date",
    "upper_date",
    "lower_days",
    "upper_days",
    "observable31",
    "followup_end_date",
    "E_end",
    "E_end90",
    "scoreable",
    "E_90",
    "E_180",
    "scoreable_fallback",
    "ttr_kind",
    "ttr_lower_days",
    "ttr_upper_days",
    "ttr_mid_days",
    *(
        f"{name}{variant}"
        for variant in VARIANTS[1:]
        for name in ("outcome", "lower_date", "upper_date", "E_end", "E_end90", "scoreable")
    ),
)
"""Columns that hold outcome information. They are blank on every test and late row."""
COLUMNS = (*FIRST_SIGHT_COLUMNS, *OUTCOME_COLUMNS)

PROBE_KEYS = (
    "item_id",
    "generic_name",
    "company_name",
    "presentation",
    "therapeutic_category",
    "initial_posting_date",
    "date_of_update",
)
"""The keys of a probe item: the identity of the presentation, the two list fields the structured
baseline also uses, and the statement date. No notice text and no stated end."""
ENTRY_KEYS = (
    *PROBE_KEYS,
    "type_of_update",
    "availability_information",
    "related_information",
    "reason_for_shortage",
    "stated_end",
    "form",
    "revision",
    "display_event_id",
    "split",
)


@dataclass(frozen=True, slots=True)
class Subset:
    """A seeded subset of the E3 eligible list: its column, size, draw tag and use, and whether
    it leaves out the statements of the first draw."""

    name: str
    size: int
    tag: str
    by_year: bool
    use: str
    skip_first_draw: bool = False


SUBSETS: tuple[Subset, ...] = (
    Subset("probe", 300, "e4-probe", True, "E4 no-notice probe"),
    Subset("samples20", 300, "e3-samples20", True, "E3: 20 samples of condition (a), primaries"),
    Subset("paraphrase", 200, "e3-paraphrase", True, "E3: 3 paraphrases of condition (b)"),
    Subset("twobytwo", 300, "e4-name-date-2x2", True, "E4 name and date 2x2, condition (b)"),
    Subset("reference_check", 100, "e3-reference-check", False, "task E: reference readings", True),
)
ELIGIBLE_BASE = (
    "statement_group_id",
    "event_id",
    "thread_id",
    "episode_id",
    "event_date",
    "form",
    "stated_end",
)
ELIGIBLE_COLUMNS = (*ELIGIBLE_BASE, *(s.name for s in SUBSETS))


# --------------------------------------------------------------------------------------------
# Seeded draws
# --------------------------------------------------------------------------------------------


def draw_key(tag: str, item: str, seed: int = SEED) -> str:
    """Position of ``item`` in the seeded draw named ``tag`` (a sha256, compared as text)."""
    return hashlib.sha256(f"{seed}\x1f{tag}\x1f{item}".encode()).hexdigest()


def seeded_order(ids: Iterable[str], tag: str, seed: int = SEED) -> list[str]:
    """The distinct ids in the seeded order of the draw ``tag``, whatever the input order."""
    return sorted(sorted(set(ids)), key=lambda i: draw_key(tag, i, seed))


def allocate(sizes: Mapping[str, int], n: int) -> dict[str, int]:
    """Quotas summing to ``n`` in proportion to the stratum sizes (largest remainders; a tie goes
    to the stratum that sorts first). Every stratum is taken whole when ``n`` covers them all."""
    total = sum(sizes.values())
    if n >= total:
        return dict(sizes)
    quotas = {k: n * v // total for k, v in sizes.items()}
    order = sorted(sizes, key=lambda k: (-(n * sizes[k] % total), k))
    for k in order[: n - sum(quotas.values())]:
        quotas[k] += 1
    return quotas


def draw_subset(pool: Mapping[str, str], subset: Subset, seed: int = SEED) -> list[str]:
    """The ids of one subset, sorted. ``pool`` maps each candidate id to its stratum (the
    statement year); a subset that is not stratified ignores the strata."""
    if not subset.by_year:
        return sorted(seeded_order(pool, subset.tag, seed)[: subset.size])
    strata: dict[str, list[str]] = {}
    for item, stratum in pool.items():
        strata.setdefault(stratum, []).append(item)
    quotas = allocate({k: len(v) for k, v in strata.items()}, subset.size)
    drawn = [i for k, v in strata.items() for i in seeded_order(v, subset.tag, seed)[: quotas[k]]]
    return sorted(drawn)


def ids_sha256(ids: Iterable[str]) -> str:
    """One digest for a set of ids: the sha256 of the sorted ids, one per line (as ``read.py``
    records the items of a run)."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def sha16(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


# --------------------------------------------------------------------------------------------
# First-sight fields: display row, split, reading, eligibility
# --------------------------------------------------------------------------------------------


def revision_bucket(index: int | str) -> str:
    """first, second, or third or later statement of its thread (revision index 0, 1, 2 or more)."""
    return REVISION_BUCKETS[min(int(index), 2)]


def iso_or_raw(cell: str) -> str:
    """An FDA date cell (MM/DD/YYYY or ISO) as ISO; any other text unchanged."""
    text = cell.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def days_between(start: str, end: str) -> int | str:
    """Whole days from one ISO date to another; blank when either is not an ISO date."""
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return ""


def listing_age(posted: str, day: str) -> int | str:
    """Days from the Initial Posting Date to the statement date; blank when the posting date is
    missing, unreadable or later than the statement (a typing error in the source)."""
    age = days_between(posted, day)
    return age if age != "" and age >= 0 else ""


def analysis_set(form: str, stale: bool, at_risk_b: bool) -> str:
    """The outcome analysis set of a statement (see the module docstring); blank when it is not
    at risk under B."""
    if not at_risk_b:
        return ""
    if form in forms.DATED_FORMS:
        return "stale" if stale else "dated"
    return form if form in FALLBACK_FORMS else "none"


def horizons(form: str, stated_end: str, day: str) -> tuple[str, str, str]:
    """Horizon A, horizon B and the rule that set them, as ``read.horizons`` gives them."""
    if stated_end:
        end = date.fromisoformat(stated_end)
        return stated_end, (end + timedelta(days=HORIZON_DAYS)).isoformat(), "stated_end"
    if form in FALLBACK_FORMS:
        a, b = (date.fromisoformat(day) + timedelta(days=n) for n in FALLBACK_DAYS)
        return a.isoformat(), b.isoformat(), "fallback"
    return "", "", ""


def member_flags(events: pd.DataFrame) -> pd.DataFrame:
    """The events as text cells, with the at-risk flags of each presentation (PLAN 2.3)."""
    missing = [c for c in EVENT_FIELDS if c not in events.columns]
    if missing:
        raise ValueError(f"events table lacks {missing}")
    ev = events.loc[:, list(EVENT_FIELDS)].fillna("").astype(str)
    if ev["event_id"].duplicated().any():
        raise ValueError("events table repeats an event_id")
    current = (ev["listing"] == "shortage") & (ev["status_at_statement"] == "current")
    ev["at_risk_A"] = current
    ev["at_risk_B"] = current & (ev["availability_class"] != "available")
    return ev


def display_rows(ev: pd.DataFrame) -> pd.DataFrame:
    """One member per statement: the at-risk-B member first in the seeded draw, or the member
    with the smallest event id when none is at risk. Indexed by ``statement_group_id``."""
    members = zip(ev["statement_group_id"], ev["event_id"], ev["at_risk_B"], strict=True)
    rank = ["0" + draw_key(DISPLAY_TAG + g, i) if risk else "1" + i for g, i, risk in members]
    ordered = ev.assign(rank=rank).sort_values(["statement_group_id", "rank"])
    first = ordered.groupby("statement_group_id", sort=True).head(1)
    return first.drop(columns="rank").set_index("statement_group_id")


def merge_of(statement_forms: pd.DataFrame) -> dict[str, str]:
    """The merged class of every form, as ``forms.tabulate`` applies it to these statements."""
    return forms.tabulate(statement_forms)["merge"]["merged_form"]


def form_labels(merged: Mapping[str, str]) -> dict[str, str]:
    """The label of each form's merged class, as tables and prompts name it."""
    members: dict[str, list[str]] = {}
    for name, target in merged.items():
        members.setdefault(target, []).append(name)
    return {name: forms.merged_label(members[target]) for name, target in merged.items()}


def statement_table(
    events: pd.DataFrame, last_capture: date, merged: Mapping[str, str] | None = None
) -> pd.DataFrame:
    """One row per statement with its first-sight columns (``FIRST_SIGHT_COLUMNS``), every cell
    as text. ``last_capture`` is the last capture day of the archive; ``merged`` replaces the
    merge of small form classes computed from these events."""
    ev = member_flags(events)
    statement_forms = forms.statement_forms(ev)
    merged = dict(merged) if merged is not None else merge_of(statement_forms)
    reading = statement_forms.set_index("statement_group_id").to_dict("index")
    labels = form_labels(merged)
    shown = display_rows(ev)
    groups = ev.groupby("statement_group_id", sort=True)
    size, n_a, n_b = groups.size(), groups["at_risk_A"].sum(), groups["at_risk_B"].sum()
    rows = []
    for gid, row in shown.iterrows():
        r = reading[gid]
        day, form = row["event_date"], r["form"]
        dated = form in forms.DATED_FORMS
        end = r["end"] if dated else ""
        stale = dated and end < day
        if dated and stale != (str(r["stale"]) == "True"):
            raise ValueError(f"{gid}: the stale flag of the rule reading contradicts its period")
        at_risk_b = bool(n_b[gid])
        which = analysis_set(form, stale, at_risk_b)
        a, b, rule = horizons(form, end, day) if which else ("", "", "")
        reached = bool(b) and b <= last_capture.isoformat()
        train = row["period"] == "train"
        eligible = which == "stale" or (which in ("dated", *FALLBACK_FORMS) and (train or reached))
        posted = iso_or_raw(row["initial_posting_date"])
        rows.append(
            {
                "statement_group_id": gid,
                **{k: row[k] for k in ("event_id", "thread_id", "generic_id", "episode_id")},
                "listing": row["listing"],
                "period": row["period"],
                "split": forms.split_of(day),
                "event_date": day,
                "n_presentations": int(size[gid]),
                "n_at_risk_A": int(n_a[gid]),
                "n_at_risk_B": int(n_b[gid]),
                "at_risk_A": bool(n_a[gid]),
                "at_risk_B": at_risk_b,
                "first_seen_date": row["first_seen_date"],
                "days_capture_after_event": row["days_capture_after_event"],
                "left_truncated": row["left_truncated"],
                "first_seen_in_test_period": train
                and row["first_seen_date"] >= TEST_START.isoformat(),
                "revision_index": row["revision_index"],
                "revision": revision_bucket(row["revision_index"]),
                "type_of_update": row["type_of_update"],
                "generic_name": row["generic_name"],
                "company_name": row["company_name"],
                "presentation": row["presentation"],
                "therapeutic_category": row["therapeutic_category"],
                "initial_posting_date": posted,
                "listing_age_days": listing_age(posted, day),
                "reason_for_shortage": row["reason_for_shortage"],
                "availability_class": row["availability_class"],
                "availability_text": row["availability_text"],
                "related_text": row["related_text"],
                "statement_text": row["statement_text"],
                "form": form,
                "merged_form": merged[form],
                "form_label": labels[form],
                "dated": dated,
                "no_year": r["no_year"],
                "distractor_dates": r["distractor_dates"],
                "statement_type": r["statement_type"],
                "certainty": r["certainty"],
                "granularity": r["granularity"] if dated else "",
                "bound": r["bound"] if dated else "",
                "stated_start": r["start"] if dated else "",
                "stated_end": end,
                "stale_at_issue": stale,
                "silent": form == "silent",
                "analysis_set": which,
                "horizon_a": a,
                "horizon_b": b,
                "horizon_rule": rule,
                "horizon_reached": reached,
                "eligible": eligible,
                "e3_eligible": eligible and which == "dated" and forms.split_of(day) == "test",
                "delayed_entry": which == "dated" and row["first_seen_date"] > end,
            }
        )
    table = pd.DataFrame(rows, columns=list(FIRST_SIGHT_COLUMNS))
    return table.astype(str).reset_index(drop=True)


def display_reading_differs(table: pd.DataFrame) -> int:
    """Statements whose display row, read on its own text, gets another form or stated end than
    the statement (members share the normalised text, so this should be none)."""
    n = 0
    for text, day, form, end in zip(
        table["statement_text"],
        table["event_date"],
        table["form"],
        table["stated_end"],
        strict=True,
    ):
        own = forms.classify(text, day)
        n += own.form != form or ((own.end or "") if own.dated else "") != end
    return n


# --------------------------------------------------------------------------------------------
# Outcomes: horizon events, the time-to-recovery target, the three statement-level brackets
# --------------------------------------------------------------------------------------------

AT_RISK_KINDS = ("recovered", "censored", "discontinued")


def horizon_event(kind: str, lower: str, upper: str, horizon: str) -> str:
    """Whether recovery had occurred by ``horizon`` (ISO dates): ``yes`` when the bracket shows
    recovery with ``upper <= horizon``; ``no`` when ``lower >= horizon`` or the outcome is a
    discontinuation; ``undetermined`` otherwise. Blank for an event that was not at risk."""
    if kind not in AT_RISK_KINDS or not horizon:
        return ""
    if kind == "discontinued":
        return "no"
    if kind == "recovered" and upper <= horizon:
        return "yes"
    return "no" if lower >= horizon else "undetermined"


def determined(*events: str) -> bool:
    """True when every horizon event is yes or no."""
    return all(e in ("yes", "no") for e in events)


def time_target(kind: str, lower_days: int, upper_days: int | None) -> dict[str, Any]:
    """The capped, interval-censored time to recovery (PLAN 2.5), in days from the statement.

    ``interval``: recovery in ``(ttr_lower_days, ttr_upper_days]``, with the midpoint.
    ``at_cap``: the target is the cap (a discontinuation, or a lower bound at or past the cap).
    ``right_censored``: censored before the cap; only the lower bound is known.
    """
    lower = min(max(lower_days, 0), CAP_DAYS)
    if kind == "discontinued" or lower >= CAP_DAYS:
        return {"kind": "at_cap", "lower": CAP_DAYS, "upper": CAP_DAYS, "mid": CAP_DAYS}
    if kind == "recovered" and upper_days is not None:
        upper = min(max(upper_days, lower), CAP_DAYS)
        return {"kind": "interval", "lower": lower, "upper": upper, "mid": (lower + upper) / 2}
    return {"kind": "right_censored", "lower": lower, "upper": "", "mid": ""}


def any_bracket(members: Sequence[tuple[str, str, str]]) -> tuple[str, str, str]:
    """The bracket of the first recovery among a statement's presentations, from their
    ``(outcome, lower_date, upper_date)``: the minimum in place of the maximum of ``corpus.py``.

    Members not at risk are left out. With every member discontinued the statement is
    discontinued (bounds as the maximum rule gives them). Otherwise, over the members that are
    not discontinued: ``lower`` is their smallest lower bound; the statement has recovered when
    any of them has, with the smallest upper bound; else it is censored.
    """
    risk = [m for m in members if m[0] in AT_RISK_KINDS]
    if not risk:
        return "not_at_risk", "", ""
    live = [m for m in risk if m[0] != "discontinued"]
    if not live:
        return "discontinued", max(m[1] for m in risk), max(m[2] for m in risk)
    lower = min(m[1] for m in live)
    uppers = [m[2] for m in live if m[0] == "recovered"]
    return ("recovered", lower, min(uppers)) if uppers else ("censored", lower, "")


def number(value: float | int | str) -> str:
    """A day count as a CSV cell: an integer when whole, one decimal otherwise, blank if none."""
    if value == "":
        return ""
    return str(int(value)) if float(value).is_integer() else f"{float(value):.1f}"


def outcome_cells(row: Mapping[str, str], brackets: Mapping[str, tuple[str, str, str]]) -> dict:
    """The horizon-event and time-target cells of one statement, from its first-sight row and
    its three brackets (keys of ``VARIANTS``: display row, all covered, any covered)."""
    which, a, b = row["analysis_set"], row["horizon_a"], row["horizon_b"]
    cells: dict[str, str] = {}
    for variant, (kind, lower, upper) in brackets.items():
        if variant:
            cells.update({f"outcome{variant}": kind, f"lower_date{variant}": lower})
            cells[f"upper_date{variant}"] = upper
        if which == "dated":
            first, second = (
                horizon_event(kind, lower, upper, a),
                horizon_event(kind, lower, upper, b),
            )
            if (first, second) == ("yes", "no"):
                raise ValueError(f"{row['statement_group_id']}: recovered by A and not by B")
            cells[f"E_end{variant}"], cells[f"E_end90{variant}"] = first, second
            cells[f"scoreable{variant}"] = str(determined(first, second)) if first else ""
    kind, lower, upper = brackets[""]
    if which in FALLBACK_FORMS:
        cells["E_90"] = horizon_event(kind, lower, upper, a)
        cells["E_180"] = horizon_event(kind, lower, upper, b)
        cells["scoreable_fallback"] = str(determined(cells["E_90"], cells["E_180"]))
    if kind in AT_RISK_KINDS:
        lower_days = int(days_between(row["event_date"], lower))
        upper_days = int(days_between(row["event_date"], upper)) if upper else None
        target = time_target(kind, lower_days, upper_days)
        cells["lower_days"] = number(lower_days)
        cells["upper_days"] = number("" if upper_days is None else upper_days)
        cells["ttr_kind"] = target["kind"]
        for key in ("lower", "upper", "mid"):
            cells[f"ttr_{key}_days"] = number(target[key])
    return cells


def attach_outcomes(
    table: pd.DataFrame, outcomes: pd.DataFrame, definition: str = DEFINITION
) -> pd.DataFrame:
    """The statement table with ``OUTCOME_COLUMNS`` filled for every statement whose display row
    is in ``outcomes`` (an outcome table of ``corpus.py``) and blank for the others.

    The builder passes train-period rows only (``require_train``). A counts-only script over
    the sealed file can pass that file's rows, under the plan's rules for it: it prints the
    numbers of ``scoreable_counts`` and nothing broken down by an outcome value, and it writes
    no table.
    """
    d = definition
    risk_column = f"at_risk_{d}" if f"at_risk_{d}" in table.columns else None
    out = outcomes.fillna("").astype(str)
    by_event = out.set_index("event_id").to_dict("index")
    members: dict[str, list[tuple[str, str, str]]] = {}
    triple = zip(out[f"outcome_{d}"], out[f"lower_date_{d}"], out[f"upper_date_{d}"], strict=True)
    for gid, bracket in zip(out["statement_group_id"], triple, strict=True):
        members.setdefault(gid, []).append(bracket)
    filled = []
    for row in table.to_dict("records"):
        cells = dict.fromkeys(OUTCOME_COLUMNS, "")
        rec = by_event.get(row["event_id"])
        if rec is not None:
            shown = (rec[f"outcome_{d}"], rec[f"lower_date_{d}"], rec[f"upper_date_{d}"])
            if risk_column and (row[risk_column] == "True") != (shown[0] in AT_RISK_KINDS):
                raise ValueError(
                    f"{row['event_id']}: at risk in one table and not in the other; the events "
                    "and the outcomes are not from the same build"
                )
            every = (
                rec[f"group_outcome_{d}"],
                rec[f"group_lower_date_{d}"],
                rec[f"group_upper_date_{d}"],
            )
            brackets = {
                "": shown,
                "_all": every,
                "_any": any_bracket(members[row["statement_group_id"]]),
            }
            cells.update(
                {
                    "outcome": shown[0],
                    "censor_reason": rec[f"censor_reason_{d}"],
                    "lower_date": shown[1],
                    "upper_date": shown[2],
                    "observable31": rec[f"observable31_{d}"],
                    "followup_end_date": rec["followup_end_date"],
                }
            )
            cells.update(outcome_cells(row, brackets))
        filled.append({**row, **cells})
    return pd.DataFrame(filled, columns=list(COLUMNS)).astype(str)


def require_train(outcomes: pd.DataFrame) -> pd.DataFrame:
    """The outcome table, refused unless every row is a train-period row."""
    missing = [c for c in OUTCOME_FIELDS if c not in outcomes.columns]
    if missing:
        raise ValueError(f"outcome table lacks {missing}")
    period = outcomes["period"].astype(str)
    day = outcomes["event_date"].astype(str)
    if (period != "train").any() or (day >= TEST_START.isoformat()).any():
        raise ValueError("the outcome table holds rows of the test period; train rows only")
    return outcomes


def assert_sealed(table: pd.DataFrame) -> None:
    """Stop if any outcome column is filled on a statement dated in the test period or later."""
    sealed = table[table["period"] != "train"]
    filled = [c for c in OUTCOME_COLUMNS if (sealed[c] != "").any()]
    if filled:
        raise ValueError(f"outcome columns filled on test-period statements: {filled}")


def require_train_outcomes(table: pd.DataFrame) -> None:
    """Stop if a train-period statement at risk under B has no outcome: its display row is not
    in the outcome table, so the events and the outcomes are not from the same build."""
    train = (table["period"] == "train") & true(table["at_risk_B"])
    bare = table.loc[train & (table["outcome"] == ""), "statement_group_id"]
    if len(bare):
        raise ValueError(
            f"{len(bare)} train statements at risk have no outcome row ({list(bare[:3])}); the "
            "events and the outcomes are not from the same build"
        )


# --------------------------------------------------------------------------------------------
# The eligible list, its subsets, and the guide's examples
# --------------------------------------------------------------------------------------------


def guide_examples(text: str) -> list[tuple[str, str, str]]:
    """(generic, company, statement date), normalised, of the statements the guide excludes from
    every sample: the rows of the tables of its Appendix A (a date cell may hold several)."""
    parts = text.split("\n## Appendix A", 1)
    if len(parts) < 2:
        return []
    found = []
    for line in parts[1].split("\n## ", 1)[0].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|") or len(cells) < 3:
            continue
        for day in re.findall(r"\d{4}-\d{2}-\d{2}", cells[2]):
            found.append((norm_text(cells[0]), norm_text(cells[1]), day))
    return found


def fixed_item_examples(events: pd.DataFrame) -> set[tuple[str, str, str]]:
    """(generic, company, statement date), normalised, of the statement the reading harness
    builds its fixed test item on: the events of its generic and date whose statement text
    stands in the item's text fields (as ``audit_sample.canary_keys`` finds it)."""
    from analysis.coling.read import CANARY_ITEM as fixed

    inside = norm_text(f"{fixed.availability_information} || {fixed.related_information}")
    generic = events["generic_name"].astype(str).map(norm_text)
    company = events["company_name"].astype(str).map(norm_text)
    text = events["statement_text"].astype(str).map(norm_text)
    rows = zip(generic, company, events["event_date"].astype(str), text, strict=True)
    return {
        (g, c, d)
        for g, c, d, t in rows
        if g == norm_text(fixed.generic_name) and d == fixed.date_of_update and t and t in inside
    }


def same_text_statements(events: pd.DataFrame, chosen: pd.Series) -> set[str]:
    """Statements of the rows flagged in ``chosen``, with every statement that has the generic,
    company and normalised text of one of them (the same notice text at another date)."""
    if not chosen.any():
        return set()
    generic = events["generic_name"].astype(str).map(norm_text)
    company = events["company_name"].astype(str).map(norm_text)
    text = events["statement_text"].astype(str).map(norm_text)
    texts = list(zip(generic, company, text, strict=True))
    quoted = {t for t, hit in zip(texts, chosen, strict=True) if hit}
    return set(events.loc[[t in quoted for t in texts], "statement_group_id"])


def example_statements(events: pd.DataFrame, examples: Iterable[tuple[str, str, str]]) -> set[str]:
    """Statements that are a guide example, or that have the generic, company and normalised
    text of one at another date."""
    wanted = set(examples)
    generic = events["generic_name"].astype(str).map(norm_text)
    company = events["company_name"].astype(str).map(norm_text)
    keys = zip(generic, company, events["event_date"].astype(str), strict=True)
    return same_text_statements(events, pd.Series([k in wanted for k in keys], index=events.index))


def unmatched_examples(events: pd.DataFrame, examples: Iterable[tuple[str, str, str]]) -> int:
    """How many (generic, company, statement date) keys name no event of the table: a mistyped
    row of Appendix A excludes nothing."""
    generic = events["generic_name"].astype(str).map(norm_text)
    company = events["company_name"].astype(str).map(norm_text)
    keys = set(zip(generic, company, events["event_date"].astype(str), strict=True))
    return len(set(examples) - keys)


def labelled_statements(events: pd.DataFrame, ids: Iterable[str]) -> set[str]:
    """The statements named in ``ids`` (the first draw) that the events table holds, with every
    statement of the same generic, company and normalised text at another date."""
    return same_text_statements(events, events["statement_group_id"].astype(str).isin(set(ids)))


def first_draw_lists(folder: Path | None) -> dict[str, tuple[str, ...]]:
    """The statement ids of each first-draw list found under ``folder`` (``sample_<name>.csv``
    for the names of ``FIRST_DRAW``), sorted. A list that is not there is left out."""
    found: dict[str, tuple[str, ...]] = {}
    if folder is None:
        return found
    for name in FIRST_DRAW:
        path = folder / f"sample_{name}.csv"
        if not path.is_file():
            continue
        frame = read_table(path)
        if "statement_group_id" not in frame.columns:
            raise ValueError(f"{path} has no statement_group_id column")
        found[name] = tuple(sorted(set(frame["statement_group_id"])))
    return found


def true(column: pd.Series) -> pd.Series:
    """A text column of True and False as booleans."""
    return column == "True"


def eligible_frame(
    table: pd.DataFrame, excluded: Iterable[str] = (), labelled: Iterable[str] = ()
) -> pd.DataFrame:
    """The E3 eligible list with one 0/1 column per subset. ``excluded`` are statements kept in
    the list but out of every subset; ``labelled`` are kept in the list but out of the subsets
    that leave out the first draw (``Subset.skip_first_draw``)."""
    listed = table[true(table["e3_eligible"])].sort_values("statement_group_id")
    skip, seen = set(excluded), set(labelled)
    pool = {
        gid: day[:4]
        for gid, day in zip(listed["statement_group_id"], listed["event_date"], strict=True)
        if gid not in skip
    }
    unseen = {gid: year for gid, year in pool.items() if gid not in seen}
    frame = listed.loc[:, list(ELIGIBLE_BASE)].reset_index(drop=True)
    for subset in SUBSETS:
        drawn = set(draw_subset(unseen if subset.skip_first_draw else pool, subset))
        frame[subset.name] = [int(g in drawn) for g in frame["statement_group_id"]]
    return frame


def csv_text(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n")


# --------------------------------------------------------------------------------------------
# Items for the reading harness
# --------------------------------------------------------------------------------------------


def item(row: Mapping[str, str], probe: bool = False) -> dict[str, Any]:
    """One statement as an item of ``read.py``. A probe item holds ``PROBE_KEYS`` only."""
    full = {
        "item_id": row["statement_group_id"],
        "generic_name": row["generic_name"],
        "company_name": row["company_name"],
        "presentation": row["presentation"],
        "therapeutic_category": row["therapeutic_category"],
        "initial_posting_date": row["initial_posting_date"],
        "date_of_update": row["event_date"],
        "type_of_update": row["type_of_update"].capitalize(),
        "availability_information": row["availability_text"],
        "related_information": row["related_text"],
        "reason_for_shortage": row["reason_for_shortage"],
        "stated_end": row["stated_end"] or None,
        "form": row["form_label"],
        "revision": row["revision"],
        "display_event_id": row["event_id"],
        "split": row["split"],
    }
    return {k: full[k] for k in (PROBE_KEYS if probe else ENTRY_KEYS)}


def items(table: pd.DataFrame, ids: Iterable[str], probe: bool = False) -> list[dict[str, Any]]:
    """The items of the named statements, sorted by id. An unknown id is an error."""
    rows = table.set_index("statement_group_id", drop=False)
    wanted = sorted(set(ids))
    unknown = [i for i in wanted if i not in rows.index]
    if unknown:
        raise ValueError(f"not in the statement table: {unknown[:5]}")
    return [item(rows.loc[i].to_dict(), probe) for i in wanted]


def jsonl(rows: Iterable[Mapping[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def item_lists(table: pd.DataFrame, eligible: pd.DataFrame) -> dict[str, tuple[list[str], bool]]:
    """The item lists of the study by file stem: statement ids, and whether it is a probe list."""
    test = (table["split"] == "test") & true(table["eligible"])
    lists: dict[str, tuple[list[str], bool]] = {
        "e3_eligible": (list(eligible["statement_group_id"]), False),
    }
    for name in ("tbd", "silent", "stale"):
        keep = test & (table["analysis_set"] == name)
        lists[f"e3_{name}"] = (sorted(table.loc[keep, "statement_group_id"]), False)
    for subset in SUBSETS:
        chosen = list(eligible.loc[eligible[subset.name] == 1, "statement_group_id"])
        lists[f"subset_{subset.name}"] = (chosen, subset.name == "probe")
    dev = (table["split"] == "dev") & true(table["scoreable"])
    lists["dev_scoreable"] = (sorted(table.loc[dev, "statement_group_id"]), False)
    return lists


def write_items(table: pd.DataFrame, eligible: pd.DataFrame, folder: Path) -> dict[str, dict]:
    """Write every item list as ``<folder>/<stem>.jsonl``; returns rows and hashes by file."""
    folder.mkdir(parents=True, exist_ok=True)
    written = {}
    for stem, (ids, probe) in item_lists(table, eligible).items():
        text = jsonl(items(table, ids, probe))
        (folder / f"{stem}.jsonl").write_text(text, encoding="utf-8")
        written[f"{stem}.jsonl"] = {
            "rows": len(ids),
            "probe": probe,
            "sha256": sha16(text.encode("utf-8")),
            "item_ids_sha256": ids_sha256(ids),
        }
    return written


# --------------------------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------------------------


def by_split(splits: pd.Series) -> dict[str, int]:
    """Counts per split, with train (fit and dev) and all."""
    row = {s: int((splits == s).sum()) for s in SPLITS}
    row["train"] = sum(row[s] for s in TRAIN_SPLITS)
    row["all"] = sum(row[s] for s in SPLITS)
    return row


def episodes(frame: pd.DataFrame) -> int:
    """Distinct shortage episodes among the statements of ``frame``."""
    return int(frame.loc[frame["episode_id"] != "", "episode_id"].nunique())


def list_record(frame: pd.DataFrame) -> dict[str, Any]:
    """Size, episodes and id digest of an item list."""
    return {
        "statements": len(frame),
        "episodes": episodes(frame),
        "ids_sha256": ids_sha256(frame["statement_group_id"]),
    }


def month_ends(first: date, before: date) -> list[date]:
    """The last day of every month from the month of ``first`` on that falls before ``before``."""
    days, year, month = [], first.year, first.month
    while True:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        end = date(year, month, 1) - timedelta(days=1)
        if end >= before:
            return days
        days.append(end)


def dated_after(days: pd.Series, month_end: Iterable[date]) -> dict[str, int]:
    """Statements dated after each month end (strictly: a statement dated on the last day of a
    cutoff month is not in that month's post-cutoff slice)."""
    return {d.isoformat(): int((days > d.isoformat()).sum()) for d in month_end}


def crossing(frame: pd.DataFrame, train_episodes: set[str]) -> int:
    """Episodes of the statements of ``frame`` that also hold a train-period statement."""
    return len((set(frame["episode_id"]) - {""}) & train_episodes)


def mix(frame: pd.DataFrame, variant: str = "") -> dict[str, int]:
    """Scoreable statements by their two horizon events (``E_end/E_end90``)."""
    pair = frame[f"E_end{variant}"] + "/" + frame[f"E_end90{variant}"]
    return {key: int((pair == key).sum()) for key in ("no/no", "no/yes", "yes/yes")}


def scoreable_counts(dated: pd.DataFrame, variant: str = "") -> dict[str, int]:
    """Counts on dated statements with outcomes attached: how many are scoreable, in how many
    episodes, and how many have a horizon event left undetermined. Nothing is broken down by an
    outcome value, so these are the counts the plan allows for the test period too."""
    scoreable = dated[true(dated[f"scoreable{variant}"])]
    return {
        "statements": len(dated),
        "episodes": episodes(dated),
        "scoreable": len(scoreable),
        "scoreable_episodes": episodes(scoreable),
        "with_a_horizon_event_undetermined": len(dated) - len(scoreable),
    }


def train_outcome_counts(dated: pd.DataFrame, variant: str = "") -> dict[str, Any]:
    """``scoreable_counts`` with the mix of the two horizon events among the scoreable. The mix
    is a breakdown by outcome value: for train-period statements only, never for sealed rows."""
    if (dated["period"] != "train").any():
        raise ValueError("the outcome mix is tabulated for train-period statements only")
    scoreable = dated[true(dated[f"scoreable{variant}"])]
    return {
        **scoreable_counts(dated, variant),
        "scoreable_by_E_end_and_E_end90": mix(scoreable, variant),
    }


def train_counts(table: pd.DataFrame) -> dict[str, Any]:
    """Counts that use train-period outcomes, by fit and dev. No test or late row enters."""
    out: dict[str, Any] = {}
    for split in TRAIN_SPLITS:
        rows = table[(table["split"] == split) & true(table["at_risk_B"])]
        dated = rows[rows["analysis_set"] == "dated"]
        fallback = rows[rows["analysis_set"].isin(FALLBACK_FORMS)]
        censored = rows[rows["outcome"] == "censored"]
        early = dated[~true(dated["delayed_entry"])]
        out[split] = {
            "at_risk_B": len(rows),
            "outcome_of_the_display_row": {
                kind: int((rows["outcome"] == kind).sum()) for kind in AT_RISK_KINDS
            },
            "censor_reason": {
                str(k): int(v)
                for k, v in censored["censor_reason"].value_counts().sort_index().items()
            },
            "dated": train_outcome_counts(dated),
            "dated_all_covered_presentations": train_outcome_counts(dated, "_all"),
            "dated_any_covered_presentation": train_outcome_counts(dated, "_any"),
            "dated_first_captured_by_stated_end": train_outcome_counts(early),
            "tbd_and_silent": {
                "statements": len(fallback),
                "scoreable_at_90_and_180_days": int(true(fallback["scoreable_fallback"]).sum()),
            },
            "time_to_recovery_target": {
                str(k): int(v) for k, v in rows["ttr_kind"].value_counts().sort_index().items()
            },
        }
    return out


def parameter_record(days: Sequence[date]) -> dict[str, Any]:
    """The constants and capture days a build used."""
    return {
        "seed": SEED,
        "draw": "ids ordered by sha256('<seed>\\x1f<tag>\\x1f<id>'); the first n are taken",
        "display_row_tag": DISPLAY_TAG + "<statement_group_id>",
        "definition": DEFINITION,
        "splits": {
            "fit": f"before {forms.DEV_START.isoformat()}",
            "dev": f"{forms.DEV_START.isoformat()} to before {TEST_START.isoformat()}",
            "test": f"{TEST_START.isoformat()} to before {forms.LATE_START.isoformat()}",
            "late": f"{forms.LATE_START.isoformat()} onward",
            "train": "fit and dev",
        },
        "capture_days": len(days),
        "last_capture": days[-1].isoformat(),
        "train_horizon": max(d for d in days if d < TEST_START).isoformat(),
        "horizon_b_days_after_stated_end": HORIZON_DAYS,
        "fallback_horizon_days": list(FALLBACK_DAYS),
        "cap_days": CAP_DAYS,
    }


def event_counts(ev: pd.DataFrame) -> dict[str, Any]:
    """Presentation-level events by split, listing and at-risk definition."""
    split = ev["event_date"].map(forms.split_of)
    late_seen = (ev["period"] == "train") & (ev["first_seen_date"] >= TEST_START.isoformat())
    return {
        "all": by_split(split),
        "shortage_listing": by_split(split[ev["listing"] == "shortage"]),
        "discontinuation_listing": by_split(split[ev["listing"] == "discontinuation"]),
        "at_risk_A": by_split(split[ev["at_risk_A"]]),
        "at_risk_B": by_split(split[ev["at_risk_B"]]),
        "train_first_seen_in_test_period": {
            "shortage_listing": int((late_seen & (ev["listing"] == "shortage")).sum()),
            "at_risk_B": int((late_seen & ev["at_risk_B"]).sum()),
        },
    }


def statement_counts(table: pd.DataFrame) -> dict[str, Any]:
    """Distinct statements by split and population."""
    shortage = table["listing"] == "shortage"
    late_seen = true(table["first_seen_in_test_period"])
    n_members, n_risk = table["n_presentations"].astype(int), table["n_at_risk_B"].astype(int)
    return {
        "all": by_split(table["split"]),
        "shortage_listing": by_split(table.loc[shortage, "split"]),
        "at_risk_A": by_split(table.loc[true(table["at_risk_A"]), "split"]),
        "at_risk_B": by_split(table.loc[true(table["at_risk_B"]), "split"]),
        "with_several_presentations": by_split(table.loc[n_members > 1, "split"]),
        "with_several_presentations_at_risk_B": by_split(table.loc[n_risk > 1, "split"]),
        "most_presentations_in_one_statement": int(n_members.max()) if len(table) else 0,
        "display_reading_differs": display_reading_differs(table),
        "train_first_seen_in_test_period": {
            "shortage_listing": int((late_seen & shortage).sum()),
            "at_risk_B": int((late_seen & true(table["at_risk_B"])).sum()),
        },
    }


def year_counts(days: pd.Series) -> dict[str, int]:
    """Statements per calendar year of their date."""
    return {str(k): int(v) for k, v in days.str[:4].value_counts().sort_index().items()}


def train_episodes(table: pd.DataFrame) -> set[str]:
    """The episodes that hold a train-period statement of the shortage listing."""
    train = (table["period"] == "train") & (table["listing"] == "shortage")
    return set(table.loc[train, "episode_id"]) - {""}


def e3_counts(table: pd.DataFrame, ev: pd.DataFrame) -> dict[str, Any]:
    """Counts on the E3 eligible list. Statement-time fields only."""
    e3 = table[true(table["e3_eligible"])]
    members = ev[ev["statement_group_id"].isin(set(e3["statement_group_id"]))]
    month_end = month_ends(TEST_START - timedelta(days=1), forms.LATE_START)
    return {
        **list_record(e3),
        "episodes_that_also_hold_train_statements": crossing(e3, train_episodes(table)),
        "covered_presentation_events": len(members),
        "covered_presentation_events_at_risk_B": int(members["at_risk_B"].sum()),
        "with_several_presentations_at_risk_B": int((e3["n_at_risk_B"].astype(int) > 1).sum()),
        "by_year": year_counts(e3["event_date"]),
        "by_form": {n: int((e3["form"] == n).sum()) for n in forms.DATED_FORMS},
        "by_revision": {b: int((e3["revision"] == b).sum()) for b in REVISION_BUCKETS},
        "first_captured_after_stated_end": int(true(e3["delayed_entry"]).sum()),
        "dated_after": dated_after(e3["event_date"], month_end),
    }


def subset_counts(
    eligible: pd.DataFrame,
    excluded: Iterable[str],
    labelled: Iterable[str],
    first_draw: Mapping[str, Sequence[str]],
    unmatched: int = 0,
) -> dict[str, Any]:
    """The seeded subsets of the eligible list: seed, tag, size, year allocation and digest,
    with what each draw left out and the first-draw lists that were read. ``unmatched`` is the
    number of ids on those lists that the statement table does not hold."""
    listed = set(eligible["statement_group_id"])
    skip = set(excluded) & listed
    seen = (set(labelled) & listed) - skip
    record: dict[str, Any] = {
        "pool": len(listed) - len(skip),
        "left_out_as_guide_examples": len(skip),
        "first_draw": {
            "lists_read": {
                name: len(first_draw[name]) for name in FIRST_DRAW if name in first_draw
            },
            "lists_missing": [name for name in FIRST_DRAW if name not in first_draw],
            "ids_not_in_the_statement_table": unmatched,
            "eligible_statements_left_out": len(seen),
        },
    }
    for s in SUBSETS:
        chosen = eligible[eligible[s.name] == 1]
        record[s.name] = {
            "use": s.use,
            "seed": SEED,
            "tag": s.tag,
            "requested": s.size,
            "stratified_by": "statement year" if s.by_year else "",
            "leaves_out_the_first_draw": s.skip_first_draw,
            "final": not s.skip_first_draw
            or (all(name in first_draw for name in FIRST_DRAW) and not unmatched),
            "pool": len(listed) - len(skip) - (len(seen) if s.skip_first_draw else 0),
            "statements": len(chosen),
            "by_year": year_counts(chosen["event_date"]),
            "ids_sha256": ids_sha256(chosen["statement_group_id"]),
        }
    return record


def counts(
    events: pd.DataFrame,
    table: pd.DataFrame,
    eligible: pd.DataFrame,
    days: Sequence[date],
    excluded: Iterable[str],
    labelled: Iterable[str] = (),
    first_draw: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Every count of the report except inputs and outputs. Outcome values enter only through
    ``train_counts`` and the number of scoreable dev statements (``N_D``)."""
    ev = member_flags(events)
    train = table["period"] == "train"
    dated = table["analysis_set"] == "dated"
    listed = true(table["eligible"])
    test = table["split"] == "test"
    drawn = first_draw or {}
    strangers = {i for ids in drawn.values() for i in ids} - set(table["statement_group_id"])
    in_train = set(table.loc[train, "episode_id"]) - {""}
    in_test = set(table.loc[~train, "episode_id"]) - {""}
    crossed = train_episodes(table)
    secondary = {}
    for name in ("tbd", "silent", "stale"):
        rows = table[test & listed & (table["analysis_set"] == name)]
        secondary[name] = {
            **list_record(rows),
            "episodes_that_also_hold_train_statements": crossing(rows, crossed),
        }
    dev_list = table[true(table["scoreable"]) & (table["split"] == "dev")]
    return {
        "parameters": parameter_record(days),
        "events": event_counts(ev),
        "statements": statement_counts(table),
        "at_risk_B_by_analysis_set": {
            name: by_split(table.loc[table["analysis_set"] == name, "split"])
            for name in ANALYSIS_SETS
        },
        "episodes": {
            "all": episodes(table),
            "with_a_train_statement": len(in_train),
            "with_a_test_or_late_statement": len(in_test),
            "with_both": len(in_train & in_test),
            "at_risk_B_dated_by_split": {
                s: episodes(table[dated & (table["split"] == s)]) for s in SPLITS
            },
        },
        "eligible": {
            name: by_split(table.loc[listed & (table["analysis_set"] == name), "split"])
            for name in ("dated", "tbd", "silent", "stale")
        },
        "dated_with_horizon_b_after_the_last_capture": by_split(
            table.loc[dated & ~true(table["horizon_reached"]), "split"]
        ),
        "e3": e3_counts(table, ev),
        "secondary_lists_test": secondary,
        "budget": {
            "N_E": int(true(table["e3_eligible"]).sum()),
            "N_S": sum(rec["statements"] for rec in secondary.values()),
            "N_D": len(dev_list),
        },
        "dev_scoreable": list_record(dev_list),
        "late": list_record(table[listed & dated & (table["split"] == "late")]),
        "train": train_counts(table),
        "subsets": subset_counts(eligible, excluded, labelled, drawn, len(strangers)),
    }


# --------------------------------------------------------------------------------------------
# Inputs, outputs and the command line
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Inputs:
    """What one build reads: the events of every period, train-period outcomes, the capture
    days, the guide's excluded examples, a record of where they came from, and the first-draw
    lists that were on disk (statement ids by list name)."""

    events: pd.DataFrame
    outcomes: pd.DataFrame
    days: tuple[date, ...]
    examples: tuple[tuple[str, str, str], ...]
    source: dict[str, str]
    first_draw: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Built:
    """The three outputs as bytes or text, with the tables behind them."""

    table: pd.DataFrame
    eligible: pd.DataFrame
    report: dict[str, Any]
    statements_gz: bytes
    eligible_csv: str

    @property
    def report_text(self) -> str:
        return json.dumps(self.report, indent=1) + "\n"


def capture_days(manifest: Path = MANIFEST) -> tuple[date, ...]:
    """The capture days of the frozen capture set, from the manifest's timestamps."""
    stamps = pd.read_csv(manifest, dtype=str, keep_default_na=False)["timestamp"]
    return tuple(sorted({datetime.strptime(s[:8], "%Y%m%d").date() for s in stamps}))


def read_table(path: Path) -> pd.DataFrame:
    """A CSV (optionally gzipped) with every cell as text."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_statements(path: Path = STATEMENTS) -> pd.DataFrame:
    """The statement table as written, every cell as text (``true`` reads a flag column)."""
    return read_table(path)


def not_sealed(path: Path) -> Path:
    """Refuse a path inside a folder named ``sealed``."""
    if "sealed" in path.resolve().parts or "sealed" in path.parts:
        raise SystemExit(f"{path}: this builder never reads the sealed folder")
    return path


def files_input(
    events: Path, outcomes: Path, manifest: Path, guide: Path, samples: Path | None = None
) -> Inputs:
    """The inputs as the files on disk give them."""
    for path in (events, outcomes, manifest, guide, *([samples] if samples else [])):
        not_sealed(path)
    return Inputs(
        events=read_table(events),
        outcomes=require_train(read_table(outcomes)),
        days=capture_days(manifest),
        examples=tuple(guide_examples(guide.read_text(encoding="utf-8"))),
        source={
            "events": events.as_posix(),
            "events_sha256": sha16(events.read_bytes()),
            "outcomes_train": outcomes.as_posix(),
            "outcomes_train_sha256": sha16(outcomes.read_bytes()),
            "capture_manifest": manifest.as_posix(),
            "capture_manifest_sha256": sha16(manifest.read_bytes()),
        },
        first_draw=first_draw_lists(samples),
    )


def as_text(frame: pd.DataFrame) -> pd.DataFrame:
    """A frame as it reads back from CSV, every cell as text."""
    return pd.read_csv(io.StringIO(frame.to_csv(index=False)), dtype=str, keep_default_na=False)


def corpus_input(
    corpus: Any, source: Mapping[str, str], guide: Path, samples: Path | None = None
) -> Inputs:
    """The inputs from a corpus built in memory. Only its events, its capture days and the
    train-period rows of its outcome table are taken; no other outcome row is touched."""
    outcomes = corpus.outcomes
    train = outcomes[outcomes["period"] == "train"]
    return Inputs(
        events=as_text(corpus.events),
        outcomes=require_train(as_text(train)),
        days=tuple(sorted({d.date() for d in corpus.captures.dates})),
        examples=tuple(guide_examples(guide.read_text(encoding="utf-8"))),
        source=dict(source),
        first_draw=first_draw_lists(samples),
    )


def build(inputs: Inputs) -> Built:
    """The statement table, the eligible list and the counts report for one set of inputs."""
    days = inputs.days
    first_seen = set(inputs.events["first_seen_date"].astype(str))
    unknown = sorted(first_seen - {d.isoformat() for d in days})
    if unknown:
        raise ValueError(f"events first seen on days that are not capture days: {unknown[:5]}")
    first_sight = statement_table(inputs.events, days[-1])
    table = attach_outcomes(first_sight, require_train(inputs.outcomes))
    table = table.sort_values("statement_group_id", ignore_index=True)
    assert_sealed(table)
    require_train_outcomes(table)
    fixed = fixed_item_examples(inputs.events)
    excluded = example_statements(inputs.events, set(inputs.examples) | fixed)
    first_draw = inputs.first_draw
    labelled = labelled_statements(inputs.events, (i for ids in first_draw.values() for i in ids))
    eligible = eligible_frame(table, excluded, labelled)
    statements_gz = forms.gz_bytes(table)
    eligible_csv = csv_text(eligible)
    merged = dict(zip(table["form"], table["merged_form"], strict=True))
    report = {
        "about": (
            "Counts from the dataset builder (PLAN.md sections 2 and 3). Outcomes are counted for "
            "the train period only; for the test and late splits there are counts of statements."
        ),
        "command": COMMAND,
        "inputs": {
            **inputs.source,
            "rules_sha256": sha16(Path(rules.__file__).read_bytes()),
            "forms_sha256": sha16(Path(forms.__file__).read_bytes()),
            "dataset_sha256": sha16(Path(__file__).read_bytes()),
            "guide_examples": len(inputs.examples),
            "guide_examples_sha256": ids_sha256("\x1f".join(e) for e in inputs.examples)[:16],
            "guide_examples_matching_no_event": unmatched_examples(inputs.events, inputs.examples),
            "fixed_test_item_statements": len(fixed),
            "first_draw_lists_sha256": {k: ids_sha256(v)[:16] for k, v in first_draw.items()},
            "merged_forms_in_use": {k: merged[k] for k in forms.FORM_NAMES if k in merged},
        },
        **counts(inputs.events, table, eligible, days, excluded, labelled, first_draw),
        "outputs": {
            STATEMENTS.name: {
                "rows": len(table),
                "columns": len(table.columns),
                "sha256": sha16(statements_gz),
                "content_sha256": sha16(csv_text(table).encode("utf-8")),
            },
            ELIGIBLE.name: {
                "rows": len(eligible),
                "sha256": sha16(eligible_csv.encode("utf-8")),
                "ids_sha256": ids_sha256(eligible["statement_group_id"]),
            },
        },
    }
    return Built(table, eligible, report, statements_gz, eligible_csv)


def print_summary(report: Mapping[str, Any]) -> None:
    """Counts only. Outcomes appear for fit and dev alone."""
    p, e3 = report["parameters"], report["e3"]
    print(
        f"capture days {p['capture_days']}; last {p['last_capture']}; train horizon {p['train_horizon']}"
    )
    header = "  {:34s} " + " ".join("{:>6s}" for _ in (*SPLITS, "train", "all"))
    line = "  {:34s} " + " ".join("{:6d}" for _ in (*SPLITS, "train", "all"))
    print(header.format("statements", *SPLITS, "train", "all"))
    for name in ("all", "shortage_listing", "at_risk_A", "at_risk_B"):
        row = report["statements"][name]
        print(line.format(name, *(row[s] for s in (*SPLITS, "train", "all"))))
    for name, row in report["at_risk_B_by_analysis_set"].items():
        print(line.format(f"at risk B, {name}", *(row[s] for s in (*SPLITS, "train", "all"))))
    print(
        f"E3 eligible: {e3['statements']} statements in {e3['episodes']} episodes "
        f"({e3['episodes_that_also_hold_train_statements']} also hold train statements); "
        f"first captured after the stated end: {e3['first_captured_after_stated_end']}"
    )
    lists = report["secondary_lists_test"]
    print(
        "secondary lists (test): " + ", ".join(f"{k} {v['statements']}" for k, v in lists.items())
    )
    for split in TRAIN_SPLITS:
        d = report["train"][split]["dated"]
        print(
            f"{split}: dated {d['statements']}, scoreable {d['scoreable']} in "
            f"{d['scoreable_episodes']} episodes, E_end/E_end90 {d['scoreable_by_E_end_and_E_end90']}"
        )
    for subset in SUBSETS:
        record = report["subsets"][subset.name]
        note = (
            "" if record["final"] else " (not final: first-draw lists missing or not of this build)"
        )
        print(f"subset {subset.name}: {record['statements']}{note}")
    if report["inputs"]["guide_examples_matching_no_event"]:
        print(
            f"warning: {report['inputs']['guide_examples_matching_no_event']} rows of the guide's "
            "Appendix A match no event and exclude nothing"
        )
    if report["statements"]["display_reading_differs"]:
        print(
            f"warning: {report['statements']['display_reading_differs']} display rows read "
            "differently from their statement; stated_end is then not that of the text shown"
        )
    first = report["subsets"]["first_draw"]
    if first["lists_missing"]:
        print("first-draw lists not on disk: " + ", ".join(first["lists_missing"]))
    if first["ids_not_in_the_statement_table"]:
        print(
            f"warning: {first['ids_not_in_the_statement_table']} ids of the first-draw lists are "
            "not in the statement table; the lists were drawn from another build"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.dataset", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("--events", type=Path, default=EVENTS, help="the events table (csv.gz)")
    ap.add_argument("--outcomes", type=Path, default=OUTCOMES, help="train outcomes (csv.gz)")
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help="the capture manifest")
    ap.add_argument("--captures", type=Path, help="build the corpus in memory from this folder")
    ap.add_argument("--guide", type=Path, default=GUIDE, help="the guide (its Appendix A)")
    ap.add_argument("--samples", type=Path, default=SAMPLES, help="folder of the first-draw lists")
    ap.add_argument("--out", type=Path, default=OUT, help="folder of the three outputs")
    ap.add_argument("--items", type=Path, help="also write the item files to this folder")
    ap.add_argument("--check", action="store_true", help="recompute and compare; write nothing")
    args = ap.parse_args(argv)
    for path in (args.out, args.items, args.samples):
        if path is not None:
            not_sealed(path)
    if sha16(Path(rules.__file__).read_bytes()) != forms.RULES_SHA256:
        print(f"warning: rules.py is not the frozen file ({forms.RULES_SHA256})")
    if args.captures:
        from analysis.coling import corpus

        checked = corpus.verify_manifest(not_sealed(args.captures))
        source = {
            "events": f"built in memory from {args.captures.as_posix()}",
            "corpus_sha256": sha16(Path(corpus.__file__).read_bytes()),
            "capture_manifest": "verified" if checked else "not checked",
        }
        built_corpus = corpus.build_corpus(args.captures)
        inputs = corpus_input(built_corpus, source, not_sealed(args.guide), args.samples)
    else:
        inputs = files_input(args.events, args.outcomes, args.manifest, args.guide, args.samples)
    built = build(inputs)
    paths = {name: args.out / name for name in (STATEMENTS.name, ELIGIBLE.name, COUNTS.name)}
    content = {
        STATEMENTS.name: built.statements_gz,
        ELIGIBLE.name: built.eligible_csv.encode("utf-8"),
        COUNTS.name: built.report_text.encode("utf-8"),
    }
    if args.check:
        stale = [
            paths[name].as_posix()
            for name in content
            if not paths[name].exists() or paths[name].read_bytes() != content[name]
        ]
        print("up to date" if not stale else "differs from a fresh run: " + ", ".join(stale))
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        paths[name].write_bytes(data)
    print_summary(built.report)
    print("wrote " + ", ".join(p.as_posix() for p in paths.values()))
    if args.items:
        for name, record in write_items(built.table, built.eligible, args.items).items():
            print(f"wrote {args.items / name}: {record['rows']} items, sha256 {record['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
