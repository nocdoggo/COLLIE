"""The track record of condition (b): how the stated recovery times of the list held, by form
and revision bucket, and ten resolved examples (PLAN.md sections 3, 5 (E3, condition b), 8 and
11; DECISIONS.md 3, 6 and 12).

The reading harness shows the record in the prompt ``predictive-track-v1`` and reads it from a
file (``read.load_track_record``, schema ``coling-track-record-v1``). This module writes that
file in two versions, with a manifest:

* ``track_fit.json`` (split ``fit``): from the statements of the fit split, dated before
  2021-01-01. For the cost trial and the dev runs of the H3 selection.
* ``track_fit_dev.json`` (split ``fit+dev``): from every train-period statement, dated before
  2023-01-01. For the runs on test-period items.
* ``track_manifest.json``: the hashes of the inputs, of the code and of the two files, the
  statements behind each version, what its follow-up reaches and which statements it is shown
  with have their own thread followed (see "Follow-up" and "Own threads" below).

Inputs. The statement table of ``dataset.py`` (``out/statements.csv.gz``; its outcome columns
are blank on every statement dated 2023-01-01 or later) and the in-context pool of
``audit_sample.py`` (``out/audit/samples_later/sample_incontext_pool.csv``). Both are read where
they stand when the command runs; no count is written into this file. Nothing under
``external_data/sealed/`` is read, listed or written. Every statement goes through
``predictors.fitting_rows``, which refuses a row outside the train period or with no outcome,
and through ``open_statements``, which refuses a statement dated on or after the version's cut
and any bracket date in the test period (but for the one exception of PLAN section 3: a
train-period statement first captured in 2023 is censored at that capture, which is first-sight
information).

The table (``slip_table``). One row for each form class and revision bucket (first, second,
third or later), in the classifier's order of the classes. The form classes are the merged
classes of the statement table and carry its labels (``form_label``), which are the labels the
item files give an entry, so the harness finds the row of every item it reads.

* A dated form. The row is the slip calibrator's (``predictors.fit_calibrator`` on the
  version's statements, so the table and the calibrator of condition (c) rest on the same
  estimates): the cell when it holds at least 100 dated statements, else the form when it does,
  else all dated forms. It gives the number of statements the figures rest on, the Turnbull
  shares recovered by the stated end and by 90 days after it, and the median days from the
  statement to recovery. A dated class with no statement in the version has rows too, on all
  dated forms.
* A form with no stated end (TBD, silent). The shares are null, which the prompt prints as
  "n/a". The median is that of the cell when it holds at least 100 statements of the class,
  else that of the class. A class with fewer than 100 statements stops the build: the plan
  gives such a class no wider pool, and the harness has no basis to name one.
* The median is that of the capped time to recovery (PLAN section 2.5: capped at 365 days,
  where never recovering counts as the cap): the Turnbull median up to 365. Above that it is
  365 when a statement of the row's group was followed to day 365 or beyond (the curve is then
  below one half at day 365), or when more than half of the group was discontinued. It is null
  when the follow-up of the group stops before day 365 and leaves open where one half lies.
* Vague, undated, discontinuation and distractor statements are in no outcome analysis and get
  no row.
* Figures are rounded to six decimals, so that the files do not depend on the last bits of a
  floating-point sum.

The examples. The pool is a ranked list of fit-split statements with a dated form, at risk and
not stale at issue (the guide, section 10). It is walked in ``draw_rank`` order and the first ten
*resolved* statements are kept, in that order, for both versions:

* ``recovered``: the display row's bracket shows recovery, shown as "recovered between the two
  bracket dates";
* ``discontinued``: the display row was discontinued;
* ``not_recovered``: censored with a lower bound 365 days or more after the statement, shown as
  "not recovered within 365 days";
* a statement censored earlier is not resolved and is passed over.

A pool with fewer than ten resolved statements stops the build. The fields of an example are
those of the statement's item (``dataset.item``); drug and company are carried for the name
masker and never shown.

Period. ``since`` and ``through`` are the first and the last statement date behind the table.
The harness's rule that a record "must end before the item's date" compares ``through`` with the
item's date: it is a rule on statement dates.

Follow-up. A train-period outcome is followed to the train horizon (the last capture before
2023-01-01), whatever the statement's split. The fit version therefore rests on recoveries seen
during the dev period, and its examples can show a recovery date or a follow-up date of 2021 or
2022 to a dev item dated earlier. PLAN section 3 registers this ("fit outcomes run past the dev
boundary", so the H3 selection on dev is not a clean forecast evaluation), and the calibrator of
condition (c) is fitted on the same outcomes. The manifest counts, for each version, the
statements whose bracket holds a date on or after the version's cut, and the examples that show
one. The fit+dev version holds no date of a seen recovery after the train horizon.

Own threads. A statement behind the fit record can be an earlier statement of the thread of a
dev-split statement that the record is shown with. When its bracket holds a date on or after
the later statement's date, its follow-up saw what became of the presentation after that
statement was made, which is the later statement's own outcome. ``own_threads`` counts these
later statements, for the table and for the examples, and the manifest holds the counts (all
dev-split statements, and the scoreable ones, which are the items of the H3 selection), so that
the registration can state them for the dev runs. Nothing is left out of the table or of the
examples for it: PLAN section 3 registers that the dev selection is not a clean forecast
evaluation. For the fit+dev record nothing is counted, and the manifest says null: the
statements it is shown with are of the test and late periods, and no row of theirs is joined to
a thread (PLAN.md, standing rules, "Threads in the open events table"). What keeps their future
out of that record is the rule on bracket dates above: no follow-up reaches past the train
horizon, and a statement censored at its first capture in 2023 was not seen again.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.track_record --out FOLDER           # write the files
    PYTHONPATH=. python -m analysis.coling.track_record --out FOLDER --check   # recompute, compare
    PYTHONPATH=. python -m analysis.coling.track_record --out FOLDER \\
        [--statements analysis/coling/out/statements.csv.gz] \\
        [--pool analysis/coling/out/audit/samples_later/sample_incontext_pool.csv]
    PYTHONPATH=. python -m pytest analysis/coling/test_track_record.py -q -p no:cacheprovider

The launcher expects the two files in ``analysis/coling/out/items``. Run the command again
after any change to the statement table, the pool, ``predictors.py`` or this file: ``--check``
reports stale files until then (exit status 1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.coling import dataset, forms
from analysis.coling import predictors as P
from analysis.coling import read as rd

SEED = P.SEED
MIN_CELL = P.MIN_CELL
CAP_DAYS = dataset.CAP_DAYS
HORIZON_DAYS = dataset.HORIZON_DAYS
MAX_EXAMPLES = rd.MAX_EXAMPLES
DIGITS = 6
"""Decimals kept of every share and median."""
POOL = dataset.SAMPLES_LATER / "sample_incontext_pool.csv"
MANIFEST = "track_manifest.json"
COMMAND = "PYTHONPATH=. python -m analysis.coling.track_record"
TABLE_SETS = ("dated", *P.NO_DATE_SETS)
"""The analysis sets whose statements stand behind a row of the table."""
POOL_SET = "dated"
"""The analysis set of every statement of the pool (the guide, section 10)."""
EXAMPLE_KEYS = (
    "item_id",
    "date_of_update",
    "outcome",
    "type_of_update",
    "availability_information",
    "related_information",
    "stated_end",
    "recovered_after",
    "recovered_by",
    "followed_until",
    "generic_name",
    "company_name",
    "form",
    "revision",
)


@dataclass(frozen=True)
class Version:
    """One version of the record: the harness's name for it, the splits whose statements it
    rests on, the day every one of them is dated before (its cut), its file, and the splits of
    the statements it is shown with."""

    split: str
    splits: tuple[str, ...]
    before: date
    file: str
    shown_to: tuple[str, ...]


VERSIONS = (
    Version("fit", ("fit",), forms.DEV_START, "track_fit.json", ("dev",)),
    Version(
        "fit+dev", forms.TRAIN_SPLITS, forms.TEST_START, "track_fit_dev.json", ("test", "late")
    ),
)
"""The fit record for the cost trial and the dev runs, and the fit+dev record for the runs on
test-period items (``launch.py`` names the two files)."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------------------------


def form_classes(table: pd.DataFrame) -> list[tuple[str, str, bool]]:
    """The form classes the table has rows for, in the classifier's order: the merged class, its
    label and whether it is dated. They are the classes of the statements in an outcome analysis
    set, of every period (the class and the label are first-sight fields)."""
    listed = table[table["analysis_set"].isin(P.SETS)]
    dated = ~listed["analysis_set"].isin(P.NO_DATE_SETS)
    found: dict[str, tuple[str, bool]] = {}
    for merged, label, flag in set(
        zip(listed["merged_form"], listed["form_label"], dated, strict=True)
    ):
        if found.setdefault(merged, (label, bool(flag))) != (label, bool(flag)):
            raise ValueError(f"form class {merged!r} has two labels, or dated and undated members")
    labels = [label for label, _ in found.values()]
    if len(set(labels)) != len(labels) or not all(label.strip() for label in labels):
        raise ValueError("two form classes share a label, or a class has none")
    order = {name: n for n, name in enumerate(forms.FORM_NAMES)}
    unknown = sorted(set(found) - set(order))
    if unknown:
        raise ValueError(f"form classes the classifier does not have: {unknown}")
    return [(merged, *found[merged]) for merged in sorted(found, key=lambda name: order[name])]


def number(value: float | None) -> float | None:
    """A figure of the table as it is written: rounded to ``DIGITS`` decimals; None stays."""
    return None if value is None else round(float(value), DIGITS)


def median_days(curve: P.Turnbull, group: pd.DataFrame) -> float | None:
    """The median of the capped days from the statement to recovery (see the module docstring),
    from the curve of a group of statements and the group itself: the Turnbull median up to the
    cap. Above it: the cap when a statement of the group was followed to the cap or beyond (the
    curve is then below one half at the cap) or when more than half of the group was
    discontinued, and None when the follow-up stops before the cap and so leaves that open.

    The curve alone does not say how far the group was followed: with a discontinuation in the
    group, its mass with no finite end starts at ``predictors.NEVER`` and also holds the
    statements censored before the cap."""
    median = float(curve.quantile(0.5))
    if median <= CAP_DAYS:
        return median
    left, right = P.ttr_brackets(group)
    live = left < P.NEVER
    bounds = np.concatenate([left[live], right[live & np.isfinite(right)]])
    followed = bounds.max(initial=-np.inf) >= CAP_DAYS
    return float(CAP_DAYS) if followed or 2 * int((~live).sum()) > len(left) else None


def table_row(
    label: str,
    revision: str,
    basis: str,
    group: pd.DataFrame,
    slip: P.Turnbull | None,
    days: P.Turnbull,
) -> dict[str, Any]:
    """One row of the table, with the keys of ``read.SlipRow``. ``group`` holds the statements
    the figures rest on; ``slip`` is None for a form with no stated end, whose shares are null."""
    return {
        "form": label,
        "revision": revision,
        "statements": len(group),
        "basis": basis,
        "share_by_stated_end": None if slip is None else number(slip.cdf(0.0)),
        "share_by_stated_end_90": None if slip is None else number(slip.cdf(float(HORIZON_DAYS))),
        "median_days_to_recovery": number(median_days(days, group)),
    }


def basis_group(dated: pd.DataFrame, merged: str, revision: str, basis: str) -> pd.DataFrame:
    """The dated fitting statements that a row with this basis rests on: those of the cell, of
    the form class, or all of them."""
    if basis == "all dated forms":
        return dated
    of_form = dated[dated["form"] == merged]
    return of_form[of_form["revision"] == revision] if basis == "cell" else of_form


def dated_rows(
    calibrator: P.SlipCalibrator, dated: pd.DataFrame, merged: str, label: str
) -> list[dict[str, Any]]:
    """The three rows of a dated form class, from the calibrator's estimate for each cell.
    ``dated`` holds the statements the calibrator was fitted on."""
    rows = []
    for revision in P.REVISIONS:
        basis, estimate = calibrator.basis(merged, revision)
        group = basis_group(dated, merged, revision, basis)
        if len(group) != estimate.statements:
            raise ValueError(
                f"{merged!r}, {revision!r}: the calibrator's estimate rests on "
                f"{estimate.statements} statements and its {basis} holds {len(group)}"
            )
        rows.append(table_row(label, revision, basis, group, estimate.slip, estimate.ttr))
    return rows


def no_date_rows(
    statements: pd.DataFrame, merged: str, label: str, min_cell: int = MIN_CELL
) -> list[dict[str, Any]]:
    """The three rows of a form class with no stated end, from its fitting statements: the cell
    when it holds at least ``min_cell`` of them, else the class."""
    group = statements[statements["form"] == merged]
    if len(group) < min_cell:
        raise ValueError(
            f"the form class {merged!r} has {len(group)} fitting statements, fewer than "
            f"{min_cell}: the plan gives a form with no stated end no wider pool, and the "
            "harness has no basis to name one"
        )
    whole = P.turnbull(*P.ttr_brackets(group))
    rows = []
    for revision in P.REVISIONS:
        cell = group[group["revision"] == revision]
        if len(cell) >= min_cell:
            days = P.turnbull(*P.ttr_brackets(cell))
            rows.append(table_row(label, revision, "cell", cell, None, days))
        else:
            rows.append(table_row(label, revision, "form", group, None, whole))
    return rows


def slip_table(
    statements: pd.DataFrame, classes: Sequence[tuple[str, str, bool]], min_cell: int = MIN_CELL
) -> list[dict[str, Any]]:
    """The table of one version from its statements (rows of the typed frame of
    ``predictors.prepare``): three rows per form class, in the order of ``classes``."""
    calibrator = P.fit_calibrator(statements, min_cell)
    with_end = P.fitting_rows(statements, ("dated",))
    undated = P.fitting_rows(statements, P.NO_DATE_SETS)
    rows: list[dict[str, Any]] = []
    for merged, label, dated in classes:
        if dated:
            rows += dated_rows(calibrator, with_end, merged, label)
        else:
            rows += no_date_rows(undated, merged, label, min_cell)
    return rows


# --------------------------------------------------------------------------------------------
# The statements of a version, and what must not enter it
# --------------------------------------------------------------------------------------------


def version_statements(frame: pd.DataFrame, version: Version) -> pd.DataFrame:
    """The rows of the typed frame that a version rests on: the statements of its splits in the
    sets of ``TABLE_SETS``. Stops unless every one is a train-period statement with an outcome."""
    rows = frame[frame["split"].isin(version.splits)]
    return P.fitting_rows(rows, TABLE_SETS)


def bracket_dates_from(rows: pd.DataFrame, day: date) -> pd.Series:
    """Whether a statement's bracket holds a date on or after ``day``."""
    iso = day.isoformat()
    return (rows["lower_date"] >= iso) | (rows["upper_date"] >= iso)


def first_sight_only(rows: pd.DataFrame) -> pd.Series:
    """Whether a statement is censored at the capture where it was first seen: it has no
    follow-up, and its one bracket date is first-sight information (PLAN section 3)."""
    return (
        (rows["outcome"] == "censored")
        & (rows["upper_date"] == "")
        & (rows["lower_date"] == rows["first_seen_date"])
    )


def open_statements(table: pd.DataFrame, ids: Sequence[str], version: Version) -> pd.DataFrame:
    """The rows of the statement table for the statements of a version, by id. Stops when one is
    not of the train period or is dated on or after the version's cut, and when a bracket holds
    a test-period date that is not the first capture of a statement censored there."""
    rows = table.set_index("statement_group_id").loc[list(ids)]
    late = (rows["period"] != "train") | (rows["event_date"] >= version.before.isoformat())
    if late.any():
        raise ValueError(
            f"{int(late.sum())} statements of the {version.split} record are dated on or after "
            f"{version.before}: {list(rows.index[late][:3])}"
        )
    sealed = bracket_dates_from(rows, forms.TEST_START) & ~first_sight_only(rows)
    if sealed.any():
        raise ValueError(
            f"{int(sealed.sum())} statements carry a follow-up date in the test period: "
            f"{list(rows.index[sealed][:3])}"
        )
    return rows


def follow_up_record(rows: pd.DataFrame, version: Version) -> dict[str, Any]:
    """What the follow-up of a version's statements reaches: the latest bracket date, and how
    many statements hold a bracket date on or after the version's cut (for the fit record: an
    outcome seen during the dev period)."""
    after = bracket_dates_from(rows, version.before)
    return {
        "last_bracket_date": max(rows["lower_date"].max(), rows["upper_date"].max()),
        "cut": version.before.isoformat(),
        "statements_with_a_bracket_date_on_or_after_the_cut": int(after.sum()),
        "of_them_censored_at_first_sight": int((after & first_sight_only(rows)).sum()),
    }


def followed_on_thread(rows: pd.DataFrame, later: pd.DataFrame) -> pd.Series:
    """Whether a statement of ``later`` lies on the thread of a statement of ``rows`` whose
    bracket holds a date on or after its own date: the follow-up of that statement saw what
    became of the presentation after the later statement was made."""
    last = rows[["lower_date", "upper_date"]].max(axis=1).groupby(rows["thread_id"]).max()
    seen_to = later["thread_id"].map(last).fillna("")
    return (later["thread_id"] != "") & (seen_to >= later["event_date"])


def own_threads(
    rows: pd.DataFrame, shown: pd.DataFrame, table: pd.DataFrame, version: Version
) -> dict[str, Any] | None:
    """How many statements a version is shown with have their thread followed past their own
    date, by a statement behind the table (``rows``) and by an example (``shown``); see "Own
    threads" in the module docstring. None for a version shown with test- or late-period
    statements: their rows are not joined to a thread."""
    if not set(version.shown_to) <= set(forms.TRAIN_SPLITS):
        return None
    later = table[(table["period"] == "train") & table["split"].isin(version.shown_to)]
    behind = followed_on_thread(rows, later)
    beside = followed_on_thread(shown, later)
    scoreable = dataset.true(later["scoreable"])
    key = "followed_past_their_date_"
    return {
        "shown_to": list(version.shown_to),
        "statements": len(later),
        key + "behind_the_table": int(behind.sum()),
        key + "by_an_example": int(beside.sum()),
        "examples_that_follow_them": [
            i for i in shown.index if followed_on_thread(shown.loc[[i]], later).any()
        ],
        "scoreable": {
            "statements": int(scoreable.sum()),
            key + "behind_the_table": int((behind & scoreable).sum()),
            key + "by_an_example": int((beside & scoreable).sum()),
        },
    }


# --------------------------------------------------------------------------------------------
# The examples
# --------------------------------------------------------------------------------------------


def read_pool(path: Path) -> list[str]:
    """The statement ids of the in-context pool, in ``draw_rank`` order. A rank that is not a
    whole number, a repeated rank and a repeated statement are errors."""
    frame = dataset.read_table(path)
    for column in ("statement_group_id", "draw_rank"):
        if column not in frame.columns:
            raise ValueError(f"{path} has no {column} column")
    ids = list(frame["statement_group_id"])
    try:
        ranks = [int(rank) for rank in frame["draw_rank"]]
    except ValueError:
        raise ValueError(f"{path}: every draw_rank must be a whole number") from None
    if len(set(ranks)) != len(ranks) or len(set(ids)) != len(ids):
        raise ValueError(f"{path} repeats a draw_rank or a statement")
    return [i for _, i in sorted(zip(ranks, ids, strict=True))]


def resolved_example(row: Mapping[str, str]) -> dict[str, str | None] | None:
    """The example a statement gives (the keys of ``read.ResolvedExample``), or None when its
    outcome is not resolved: censored with a lower bound under 365 days after the statement."""
    kind, lower, upper = row["outcome"], row["lower_date"], row["upper_date"]
    dates: dict[str, str | None] = dict.fromkeys(
        ("recovered_after", "recovered_by", "followed_until")
    )
    if kind == "recovered":
        outcome = "recovered"
        dates |= {"recovered_after": lower, "recovered_by": upper}
    elif kind == "discontinued":
        outcome = "discontinued"
    elif kind == "censored" and int(dataset.days_between(row["event_date"], lower)) >= CAP_DAYS:
        outcome = "not_recovered"
        dates["followed_until"] = lower
    else:
        return None
    shown = dataset.item(row)
    example = {**shown, "outcome": outcome, **dates}
    return {key: example[key] for key in EXAMPLE_KEYS}


def pool_rows(table: pd.DataFrame, pool: Sequence[str]) -> pd.DataFrame:
    """The rows of the statement table for the pool, in its order. Stops when a statement of the
    pool is not in the table, or is not a fit-split statement of the set ``POOL_SET``: the pool
    and the table would not be from the same build."""
    rows = table.set_index("statement_group_id", drop=False)
    unknown = [i for i in pool if i not in rows.index]
    if unknown:
        raise ValueError(f"the pool names statements the table does not hold: {unknown[:5]}")
    listed = rows.loc[list(pool)]
    other = (listed["split"] != "fit") | (listed["analysis_set"] != POOL_SET)
    if other.any():
        raise ValueError(
            "the pool holds fit-split statements with a dated form, at risk and not stale; "
            f"not so: {list(listed.index[other][:5])}"
        )
    return listed


def draw_examples(
    table: pd.DataFrame, pool: Sequence[str], limit: int = MAX_EXAMPLES
) -> tuple[list[dict[str, str | None]], list[str]]:
    """The first ``limit`` resolved statements of the pool as examples, in its order, and the
    ids of the unresolved statements passed over on the way. Stops when the pool holds fewer."""
    chosen: list[dict[str, str | None]] = []
    passed: list[str] = []
    for row in pool_rows(table, pool).to_dict("records"):
        if len(chosen) == limit:
            break
        example = resolved_example(row)
        if example is None:
            passed.append(row["statement_group_id"])
        else:
            chosen.append(example)
    if len(chosen) < limit:
        raise ValueError(
            f"the pool holds {len(chosen)} resolved statements; the record shows {limit}"
        )
    return chosen, passed


def example_dates_from(examples: Sequence[Mapping[str, str | None]], day: date) -> int:
    """How many examples show a recovery or follow-up date on or after ``day``."""
    keys = ("recovered_after", "recovered_by", "followed_until")
    return sum(1 for ex in examples if any((ex[key] or "") >= day.isoformat() for key in keys))


# --------------------------------------------------------------------------------------------
# The files
# --------------------------------------------------------------------------------------------


def harness_errors(record: Mapping[str, Any]) -> list[str]:
    """What the harness would refuse the record for: the errors of the file schema, then those
    of the record itself (``read.track_file_errors``, ``read.TrackRecord.errors``)."""
    found = rd.track_file_errors(record)
    if found:
        return found
    track = rd.TrackRecord(
        through=record["through"],
        since=record["since"],
        split=record["split"],
        min_cell=record["min_cell"],
        slip_table=tuple(rd.SlipRow(**row) for row in record["slip_table"]),
        examples=tuple(rd.ResolvedExample(**row) for row in record["examples"]),
    )
    return track.errors()


def build_record(
    table: pd.DataFrame,
    frame: pd.DataFrame,
    examples: Sequence[Mapping[str, str | None]],
    version: Version,
    source: Mapping[str, str],
    min_cell: int = MIN_CELL,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The record of one version as the file holds it, and what the manifest says about it.
    ``frame`` is the typed frame of ``table``. Stops when the harness would refuse the record."""
    statements = version_statements(frame, version)
    rows = open_statements(table, statements.index, version)
    record = {
        "schema": rd.TRACK_SCHEMA,
        "split": version.split,
        "since": rows["event_date"].min(),
        "through": rows["event_date"].max(),
        "seed": SEED,
        "min_cell": min_cell,
        "source": dict(source),
        "slip_table": slip_table(statements, form_classes(table), min_cell),
        "examples": [dict(example) for example in examples],
    }
    found = harness_errors(record)
    if found:
        raise ValueError(
            f"the harness would refuse the {version.split} record: " + "; ".join(found)
        )
    by_set = statements["analysis_set"].value_counts()
    bases = [row["basis"] for row in record["slip_table"]]
    shown = table.set_index("statement_group_id").loc[[ex["item_id"] for ex in examples]]
    about = {
        "file": version.file,
        "splits": list(version.splits),
        "since": record["since"],
        "through": record["through"],
        "statements": {name: int(by_set.get(name, 0)) for name in TABLE_SETS},
        "table_rows": len(bases),
        "rows_by_basis": {basis: bases.count(basis) for basis in rd.TRACK_BASES},
        "follow_up": follow_up_record(rows, version),
        "examples_with_a_date_on_or_after_the_cut": example_dates_from(examples, version.before),
        "own_threads": own_threads(rows, shown, table, version),
    }
    return record, about


def record_text(record: Mapping[str, Any]) -> str:
    return json.dumps(record, indent=1, ensure_ascii=False) + "\n"


def build(
    table: pd.DataFrame,
    pool: Sequence[str],
    inputs: Mapping[str, str],
    code: Mapping[str, str],
    min_cell: int = MIN_CELL,
    limit: int = MAX_EXAMPLES,
) -> dict[str, str]:
    """The text of the three files by name: the two versions of the record and the manifest.
    ``inputs`` and ``code`` are the hashes the manifest records; every key that ends in
    ``_sha256`` also goes into the ``source`` of both records."""
    frame = P.prepare(table)
    examples, passed = draw_examples(table, pool, limit)
    source = {k: v for k, v in {**inputs, **code}.items() if k.endswith("_sha256")}
    files: dict[str, str] = {}
    versions: dict[str, Any] = {}
    for version in VERSIONS:
        record, about = build_record(table, frame, examples, version, source, min_cell)
        files[version.file] = record_text(record)
        digest = sha256(files[version.file].encode("utf-8"))
        versions[version.split] = {**about, "sha256": digest}
    manifest = {
        "about": (
            "The track record of condition (b) (PLAN.md section 5, E3): the table of Turnbull "
            "shares by form and revision bucket and the resolved examples, from train-period "
            "statements only. Outcomes are followed to the train horizon, also for the fit "
            "record (PLAN.md section 3)."
        ),
        "command": COMMAND,
        "schema": rd.TRACK_SCHEMA,
        "seed": SEED,
        "min_cell": min_cell,
        "inputs": dict(inputs),
        "code": {**code, "numpy": np.__version__, "pandas": pd.__version__},
        "examples": {
            "pool": len(pool),
            "shown": [example["item_id"] for example in examples],
            "passed_over_unresolved": passed,
        },
        "versions": versions,
    }
    files[MANIFEST] = record_text(manifest)
    return files


def code_record() -> dict[str, str]:
    """The hashes of the code a record depends on: this file and the predictors."""
    files = {"builder": Path(__file__), "predictors": Path(P.__file__)}
    return {f"{name}_sha256": sha256(path.read_bytes()) for name, path in files.items()}


def stale_files(content: Mapping[str, str], folder: Path) -> list[str]:
    """The files under ``folder`` that are missing or differ from ``content``."""
    return [
        (folder / name).as_posix()
        for name, text in content.items()
        if not (folder / name).is_file() or (folder / name).read_text(encoding="utf-8") != text
    ]


def print_summary(content: Mapping[str, str]) -> None:
    manifest = json.loads(content[MANIFEST])
    for split, about in manifest["versions"].items():
        reach = about["follow_up"]
        print(
            f"{split}: statements dated {about['since']} to {about['through']} "
            f"{about['statements']}; {about['table_rows']} rows {about['rows_by_basis']}; "
            f"{reach['statements_with_a_bracket_date_on_or_after_the_cut']} statements with a "
            f"bracket date on or after {reach['cut']}"
        )
        own, key = about["own_threads"], "followed_past_their_date_"
        if own is not None:
            print(
                f"  shown with {' and '.join(own['shown_to'])} statements: the table follows the "
                f"thread of {own[key + 'behind_the_table']} of them past their date, an example "
                f"that of {own[key + 'by_an_example']}"
            )
    shown = manifest["examples"]
    print(
        f"examples: {len(shown['shown'])} of a pool of {shown['pool']}, "
        f"{len(shown['passed_over_unresolved'])} unresolved passed over"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.track_record", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("--statements", type=Path, default=dataset.STATEMENTS, help="statement table")
    ap.add_argument("--pool", type=Path, default=POOL, help="the in-context pool")
    ap.add_argument("--out", type=Path, required=True, help="folder of the three files")
    ap.add_argument("--check", action="store_true", help="recompute and compare; write nothing")
    args = ap.parse_args(argv)
    for path in (args.statements, args.pool, args.out):
        dataset.not_sealed(path)
    inputs = {
        "statements": args.statements.as_posix(),
        "statements_sha256": sha256(args.statements.read_bytes()),
        "incontext_pool": args.pool.as_posix(),
        "incontext_pool_sha256": sha256(args.pool.read_bytes()),
    }
    content = build(
        dataset.load_statements(args.statements), read_pool(args.pool), inputs, code_record()
    )
    if args.check:
        stale = stale_files(content, args.out)
        print("up to date" if not stale else "differs from a fresh run: " + ", ".join(stale))
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in content.items():
        (args.out / name).write_text(text, encoding="utf-8")
    print_summary(content)
    print("wrote " + ", ".join((args.out / name).as_posix() for name in content))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
