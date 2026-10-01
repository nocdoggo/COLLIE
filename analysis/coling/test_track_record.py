"""Tests for the track record of condition (b) (``track_record.py``).

The synthetic statement tables below are in the schema of ``dataset.py``, with outcomes that are
worked out by hand in the comments. Covered: the constants shared with the harness and the
launcher; the form classes and their order; the backoff of dated forms (cell, form, all dated
forms) and its agreement with the calibrator's own table; the rows of forms with no stated end
and the class that is too small; the capped median, with and without a discontinuation in the
group; the examples (the walk in ``draw_rank``
order, what counts as resolved, the fields, the refusals of a pool that does not fit the table);
the two versions (which statements enter each, ``since`` and ``through``, what must not enter,
the follow-up record of the manifest, the dev statements whose own thread the fit record
follows past their date, and that no test-period statement is joined to a thread); the files
(the harness's own loader and refusals,
determinism, ``--check``); a dry run of the harness on dev items with the fit file; and the
build from the open tables on disk, when they are there.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_track_record.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from analysis.coling import dataset, forms, launch
from analysis.coling import predictors as P
from analysis.coling import read as rd
from analysis.coling import track_record as T

FIT, FIT_DEV = T.VERSIONS
SOURCE = {"statements_sha256": "0" * 64, "incontext_pool_sha256": "1" * 64}
CODE = {"builder_sha256": "2" * 64, "predictors_sha256": "3" * 64}
TRACK_TEMPLATE = rd.TEMPLATES["predictive-track-v1"]
RECORD_KEYS = [
    "schema",
    "split",
    "since",
    "through",
    "seed",
    "min_cell",
    "source",
    "slip_table",
    "examples",
]
"""The keys of a track-record file, in the order of the harness's description of it."""


# --------------------------------------------------------------------------------------------
# Synthetic statement tables
# --------------------------------------------------------------------------------------------


def after(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def statement(
    sid: str,
    day: str,
    form: str = "month_year",
    revision: str = "first",
    outcome: tuple[str, int, int | None] | None = ("recovered", 20, 40),
    *,
    end: int = 30,
    seen: int = 0,
    **more: str,
) -> dict[str, str]:
    """One row of the statement table. ``outcome`` is the kind and the bracket in days from the
    statement date (None for a test-period statement); ``end`` the stated end in days from it
    (dated forms); ``seen`` the days to the first capture. Every statement has an event and a
    thread of its own unless ``more`` names another."""
    dated = form in forms.DATED_FORMS
    which = "dated" if dated else form if form in dataset.FALLBACK_FORMS else "none"
    stated_end = after(day, end) if dated else ""
    a, b, rule = dataset.horizons(form, stated_end, day)
    split = forms.split_of(day)
    row = {
        **dict.fromkeys(dataset.COLUMNS, ""),
        "statement_group_id": sid,
        "event_id": "E" + sid,
        "thread_id": "T" + sid,
        "episode_id": "ep-" + sid,
        "period": "train" if split in forms.TRAIN_SPLITS else "test",
        "split": split,
        "event_date": day,
        "at_risk_B": "True",
        "first_seen_date": after(day, seen),
        "revision": revision,
        "type_of_update": "revised",
        "generic_name": f"Drug {sid} Injection",
        "company_name": "Acme Pharma",
        "presentation": "1 mL vial",
        "listing_age_days": "10",
        "availability_text": f"Next release in about {end} days ({sid})",
        "related_text": "Check wholesalers",
        "form": form,
        "merged_form": form,
        "form_label": forms.merged_label([form]),
        "stated_end": stated_end,
        "analysis_set": which,
        "horizon_a": a,
        "horizon_b": b,
        "horizon_rule": rule,
    }
    if outcome is not None:
        kind, lower, upper = outcome
        bracket = (kind, after(day, lower), "" if upper is None else after(day, upper))
        row |= {"outcome": kind, "lower_date": bracket[1], "upper_date": bracket[2]}
        row |= dataset.outcome_cells(row, dict.fromkeys(dataset.VARIANTS, bracket))
    return {**row, **more}


def as_table(rows: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(dataset.COLUMNS)).astype(str)


def small_rows() -> list[dict[str, str]]:
    """A table for a minimum cell of 3.

    Fit, dated (8): month_year/first F01, F02 recover in (20, 40] and F03 is discontinued;
    month_year/second F04 recovers in (50, 70]; quarter/first F05, F06 recover in (30, 50];
    year/first F14 is censored at 364 days and year/second F15 at 365. Fit, TBD (4): first
    F07, F08 recover in (0, 100] and F09 is censored at 400; second F10 recovers in (10, 20].
    Fit, silent (3): one per revision bucket, each censored at 500. F16 is vague, in no analysis
    set; F17, dated 2019-06-01, is stale at issue, so behind no row of the table.
    Dev, dated (5): month_year/second D01, D02; quarter/first D03; year/first D04 censored at
    100; month_year/third D05, dated 2022-12-20 and first seen on 2023-01-13, censored there.
    Test: a range X01 and a TBD X02, with no outcome.
    """
    never = ("discontinued", 5, 9)
    return [
        statement("F01", "2020-01-10"),
        statement("F02", "2020-02-10"),
        statement("F03", "2020-03-10", outcome=never),
        statement("F04", "2020-04-10", revision="second", outcome=("recovered", 50, 70)),
        statement("F05", "2019-11-05", "quarter", outcome=("recovered", 30, 50)),
        statement("F06", "2020-05-10", "quarter", outcome=("recovered", 30, 50)),
        statement("F07", "2020-06-10", "tbd", outcome=("recovered", 0, 100)),
        statement("F08", "2020-07-10", "tbd", outcome=("recovered", 0, 100)),
        statement("F09", "2020-08-10", "tbd", outcome=("censored", 400, None)),
        statement("F10", "2020-09-10", "tbd", "second", ("recovered", 10, 20)),
        statement("F11", "2020-10-10", "silent", "first", ("censored", 500, None)),
        statement("F12", "2020-10-11", "silent", "second", ("censored", 500, None)),
        statement("F13", "2020-12-30", "silent", "third or later", ("censored", 500, None)),
        statement("F14", "2020-03-01", "year", "first", ("censored", 364, None)),
        statement("F15", "2020-03-02", "year", "second", ("censored", 365, None)),
        statement("F16", "2020-03-03", "vague", "first", ("recovered", 1, 2)),
        statement("F17", "2019-06-01", end=-5, analysis_set="stale"),
        statement("D01", "2021-02-01", revision="second", outcome=("recovered", 10, 30)),
        statement("D02", "2021-03-01", revision="second", outcome=("recovered", 10, 30)),
        statement("D03", "2021-04-01", "quarter", outcome=("recovered", 30, 50)),
        statement("D04", "2021-05-01", "year", outcome=("censored", 100, None)),
        statement("D05", "2022-12-20", "month_year", "third or later", ("censored", 24, None), seen=24),
        statement("X01", "2024-03-10", "range", outcome=None),
        statement("X02", "2024-04-10", "tbd", "second", outcome=None),
    ]  # fmt: skip


SMALL_POOL = ["F14", "F15", "F01", "F03", "F04", "F05"]
"""F14 is not resolved (censored at 364 days); the next three are, in this order."""


def small_build(rows: list[dict[str, str]] | None = None, **more: Any) -> dict[str, Any]:
    """The three files of the small table as parsed JSON, by the harness's name of the version
    (and ``manifest``), for a minimum cell of 3 and three examples."""
    table = as_table(small_rows() if rows is None else rows)
    options = {"min_cell": 3, "limit": 3} | more
    files = T.build(table, SMALL_POOL, SOURCE, CODE, **options)
    out = {version.split: json.loads(files[version.file]) for version in T.VERSIONS}
    return out | {"manifest": json.loads(files[T.MANIFEST])}


def cell(record: dict[str, Any], label: str, revision: str) -> dict[str, Any]:
    found = [r for r in record["slip_table"] if (r["form"], r["revision"]) == (label, revision)]
    assert len(found) == 1
    return found[0]


def big_rows() -> list[dict[str, str]]:
    """A table for the registered minimum of 100: in the fit split 100 month_year/first (A),
    100 TBD/first (B) and 100 silent/second (C) statements; three scoreable dev statements;
    two test statements. The statements of rank k are dated k days after 2020-01-01. A000 is
    censored at 100 days (not resolved), A001 at 400 days, and A002 is discontinued; of the other
    A, the 49 of odd rank recover in (20, 30] days and the 48 of even rank in (40, 60]."""
    special = {0: ("censored", 100, None), 1: ("censored", 400, None), 2: ("discontinued", 5, 9)}
    rows = []
    for k in range(100):
        day = after("2020-01-01", k)
        usual = ("recovered", 20, 30) if k % 2 else ("recovered", 40, 60)
        rows.append(statement(f"A{k:03d}", day, outcome=special.get(k, usual)))
        rows.append(statement(f"B{k:03d}", day, "tbd", outcome=("censored", 400, None)))
        rows.append(statement(f"C{k:03d}", day, "silent", "second", ("recovered", 0, 50)))
    rows += [
        statement("D001", "2021-02-01", outcome=("recovered", 5, 20)),
        statement("D002", "2021-03-01", revision="second", outcome=("recovered", 40, 100)),
        statement("D003", "2021-04-01", "tbd", "third or later", ("censored", 300, None)),
        statement("X001", "2024-03-10", outcome=None),
        statement("X002", "2024-04-10", "silent", outcome=None),
    ]
    return rows


BIG_POOL = [f"A{k:03d}" for k in range(14)]


def write_inputs(folder: Path, rows: list[dict[str, str]] | None = None) -> list[str]:
    """The big table and its pool as files (the pool's lines in reverse order of rank), and the
    command-line arguments that name them and the output folder."""
    folder.mkdir(parents=True, exist_ok=True)
    table = as_table(big_rows() if rows is None else rows)
    # a fixed time in the gzip header: the same table gives the same bytes, and so the same hash
    # in the records, whenever it is written
    gz = {"method": "gzip", "mtime": 0}
    table.to_csv(folder / "statements.csv.gz", index=False, compression=gz)
    pool = pd.DataFrame(
        {
            "event_id": ["E" + sid for sid in BIG_POOL],
            "statement_group_id": BIG_POOL,
            "thread_id": ["T" + sid for sid in BIG_POOL],
            "draw_rank": [str(n) for n in range(1, len(BIG_POOL) + 1)],
            "period": "train",
        }
    )
    pool.iloc[::-1].to_csv(folder / "pool.csv", index=False)
    return [
        "--statements",
        str(folder / "statements.csv.gz"),
        "--pool",
        str(folder / "pool.csv"),
        "--out",
        str(folder / "out"),
    ]


@pytest.fixture(scope="module")
def written(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[str]]:
    """The files of the big table, written once by the command."""
    folder = tmp_path_factory.mktemp("track")
    args = write_inputs(folder)
    assert T.main(args) == 0
    return folder, args


def dev_items(rows: list[dict[str, str]]) -> list[rd.ReadItem]:
    """The scoreable dev statements of a table as items of the harness."""
    table = as_table(rows)
    dev = table[(table["split"] == "dev") & dataset.true(table["scoreable"])]
    return [rd.ReadItem.from_dict(i) for i in dataset.items(table, dev["statement_group_id"])]


# --------------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------------


def test_constants_agree_with_the_harness_and_the_launcher() -> None:
    assert (T.SEED, T.MIN_CELL, T.MAX_EXAMPLES, T.CAP_DAYS) == (20261001, 100, 10, 365)
    assert T.SEED == rd.STUDY_SEED and T.CAP_DAYS == rd.CAP_DAYS and T.HORIZON_DAYS == 90
    assert tuple(v.split for v in T.VERSIONS) == rd.TRACK_SPLITS == ("fit", "fit+dev")
    assert (FIT.splits, FIT_DEV.splits) == (("fit",), ("fit", "dev"))
    assert (FIT.shown_to, FIT_DEV.shown_to) == (("dev",), ("test", "late"))
    assert set(FIT_DEV.splits + FIT_DEV.shown_to) == set(forms.SPLITS)
    assert (FIT.before, FIT_DEV.before) == (rd.DEV_START, rd.TEST_START)
    assert (FIT.before, FIT_DEV.before) == (date(2021, 1, 1), date(2023, 1, 1))
    expected = launch.default_options(Path("items"))["tracks"]
    assert {v.split: f"items/{v.file}" for v in T.VERSIONS} == expected
    assert P.REVISIONS == rd.REVISION_BUCKETS and P.BASES == rd.TRACK_BASES
    assert set(T.EXAMPLE_KEYS) == {f.name for f in fields(rd.ResolvedExample)}
    assert T.POOL.name == "sample_incontext_pool.csv" and T.POOL.parent == dataset.SAMPLES_LATER


# --------------------------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------------------------


def test_form_classes_are_those_of_the_analysis_sets_in_the_classifiers_order() -> None:
    classes = T.form_classes(as_table(small_rows()))
    assert classes == [
        ("range", "a range", True),  # a test-period statement only: first-sight fields
        ("quarter", "a quarter", True),
        ("year", "a year", True),
        ("month_year", "a month and year", True),
        ("tbd", "TBD or unknown", False),
        ("silent", "no timing", False),
    ]  # the vague statement is in no analysis set: no class


def test_form_classes_refuse_a_table_whose_labels_do_not_identify_a_class() -> None:
    rows = small_rows()
    with pytest.raises(ValueError, match="two labels"):
        T.form_classes(as_table([*rows, statement("F20", "2020-01-01", form_label="a month")]))
    with pytest.raises(ValueError, match="share a label"):
        T.form_classes(as_table([{**r, "form_label": "a time"} for r in rows]))
    unknown = statement("F20", "2020-01-01", merged_form="decade", form_label="a decade")
    with pytest.raises(ValueError, match="does not have"):
        T.form_classes(as_table([*rows, unknown]))
    mixed = statement("F20", "2020-01-01", "tbd", merged_form="quarter", form_label="a quarter")
    with pytest.raises(ValueError, match="dated and undated"):
        T.form_classes(as_table([*rows, mixed]))


def test_the_fit_table_backs_off_from_cell_to_form_to_all_dated_forms() -> None:
    fit = small_build()["fit"]
    rows = [(r["form"], r["revision"], r["basis"], r["statements"]) for r in fit["slip_table"]]
    every, form = "all dated forms", "form"
    assert rows == [
        ("a range", "first", every, 8),  # no fit statement of the class: all 8 dated ones
        ("a range", "second", every, 8),
        ("a range", "third or later", every, 8),
        ("a quarter", "first", every, 8),  # 2 in the cell and in the form, under 3
        ("a quarter", "second", every, 8),
        ("a quarter", "third or later", every, 8),
        ("a year", "first", every, 8),
        ("a year", "second", every, 8),
        ("a year", "third or later", every, 8),
        ("a month and year", "first", "cell", 3),
        ("a month and year", "second", form, 4),  # 1 in the cell, 4 in the form
        ("a month and year", "third or later", form, 4),
        ("TBD or unknown", "first", "cell", 3),
        ("TBD or unknown", "second", form, 4),
        ("TBD or unknown", "third or later", form, 4),
        ("no timing", "first", form, 3),
        ("no timing", "second", form, 3),
        ("no timing", "third or later", form, 3),
    ]


def test_the_fit_and_dev_table_adds_the_dev_statements() -> None:
    both = small_build()["fit+dev"]
    found = {(r["form"], r["revision"]): (r["basis"], r["statements"]) for r in both["slip_table"]}
    assert found[("a month and year", "first")] == ("cell", 3)
    assert found[("a month and year", "second")] == ("cell", 3)  # F04 with D01 and D02
    assert found[("a month and year", "third or later")] == ("form", 7)  # D05 alone in the cell
    assert found[("a quarter", "first")] == ("cell", 3)  # F05, F06 and D03
    assert found[("a quarter", "second")] == ("form", 3)
    assert found[("a year", "first")] == ("form", 3)  # F14, F15 and D04
    assert found[("a range", "first")] == ("all dated forms", 13)
    assert found[("TBD or unknown", "first")] == ("cell", 3)  # no dev statement without a date
    assert len(both["slip_table"]) == 18


def test_shares_and_medians_of_a_hand_computed_table() -> None:
    fit = small_build()["fit"]
    # month_year/first: stated end at 30 days. Two recover in (20, 40], slip in (-10, 10]; one is
    # discontinued. Mass 2/3 spread over (-10, 10]: 1/3 by the stated end, 2/3 by 90 days later.
    # Days to recovery: 2/3 on (20, 40], so one half is reached at 20 + 20 * 0.75.
    first = cell(fit, "a month and year", "first")
    assert first["share_by_stated_end"] == pytest.approx(1 / 3, abs=1e-6)
    assert first["share_by_stated_end_90"] == pytest.approx(2 / 3, abs=1e-6)
    assert first["median_days_to_recovery"] == pytest.approx(35.0, abs=1e-4)
    # The form adds F04, slip in (20, 40]: masses 1/2 on (-10, 10], 1/4 on (20, 40], 1/4 never.
    second = cell(fit, "a month and year", "second")
    assert second["share_by_stated_end"] == pytest.approx(0.25, abs=1e-6)
    assert second["share_by_stated_end_90"] == pytest.approx(0.75, abs=1e-6)
    assert second["median_days_to_recovery"] == pytest.approx(40.0, abs=1e-4)
    # TBD/first: two in (0, 100] and one censored at 400: one half is reached at 100 * 0.75.
    tbd = cell(fit, "TBD or unknown", "first")
    assert (tbd["share_by_stated_end"], tbd["share_by_stated_end_90"]) == (None, None)
    assert tbd["median_days_to_recovery"] == pytest.approx(75.0, abs=1e-4)
    # The TBD form adds (10, 20], which lies inside (0, 100]: mass 3/4 on (10, 20].
    pooled = cell(fit, "TBD or unknown", "second")
    assert pooled["median_days_to_recovery"] == pytest.approx(10 + 10 * (0.5 / 0.75), abs=1e-4)
    # Silent: every statement censored at 500 days, past the cap.
    silent = cell(fit, "no timing", "third or later")
    assert (silent["share_by_stated_end"], silent["median_days_to_recovery"]) == (None, 365.0)


def test_dated_rows_are_the_calibrators_own() -> None:
    table = as_table(small_rows())
    frame = P.prepare(table)
    labels = {merged: label for merged, label, _ in T.form_classes(table)}
    for version in T.VERSIONS:
        statements = T.version_statements(frame, version)
        mine = {(r["form"], r["revision"]): r for r in small_build()[version.split]["slip_table"]}
        listed = P.fit_calibrator(statements, 3).table()
        assert listed, version.split
        for theirs in listed:
            row = mine[(labels[theirs["form"]], theirs["revision"])]
            for key in ("basis", "statements"):
                assert row[key] == theirs[key]
            for key in ("share_by_stated_end", "share_by_stated_end_90"):
                assert row[key] == pytest.approx(theirs[key], abs=1e-6)
            median = theirs["median_days_to_recovery"]
            if median is not None and median <= T.CAP_DAYS:
                assert row["median_days_to_recovery"] == pytest.approx(median, abs=1e-6)


def test_the_minimum_is_met_at_the_boundary_and_missed_one_below() -> None:
    # month_year/first has 3 statements and TBD/first has 3: cells at a minimum of 3; at a
    # minimum of 4 both back off to their forms, which hold exactly 4.
    # (The silent class holds 3 statements; it is left out here and comes back below.)
    rows = [r for r in small_rows() if r["form"] != "silent"]
    at_three, at_four = (small_build(rows, min_cell=n)["fit"] for n in (3, 4))
    for label in ("a month and year", "TBD or unknown"):
        row = cell(at_three, label, "first")
        assert (row["basis"], row["statements"]) == ("cell", 3)
        row = cell(at_four, label, "first")
        assert (row["basis"], row["statements"]) == ("form", 4)
    assert (at_three["min_cell"], at_four["min_cell"]) == (3, 4)
    # A class with no stated end and fewer statements than the minimum has no wider pool.
    with pytest.raises(ValueError, match="'silent' has 3 fitting statements, fewer than 4"):
        small_build(min_cell=4)
    # At a minimum of 5 the TBD class (4 statements) is too small as well.
    with pytest.raises(ValueError, match="'tbd' has 4 fitting statements, fewer than 5"):
        small_build(rows, min_cell=5)


def test_figures_are_rounded_to_six_decimals() -> None:
    assert T.number(None) is None and T.number(np.float64(1 / 3)) == 0.333333
    fit = small_build()["fit"]
    assert cell(fit, "a month and year", "first")["share_by_stated_end"] == 0.333333
    for row in fit["slip_table"]:
        for key in ("share_by_stated_end", "share_by_stated_end_90", "median_days_to_recovery"):
            assert row[key] is None or row[key] == round(row[key], 6)


def group_of(left: list[float], right: list[float]) -> pd.DataFrame:
    """A group of statements with these brackets of the days to recovery, as the typed frame
    holds them: ``P.NEVER`` on the left is a discontinuation, an infinite right end a censored
    statement."""
    kinds = [
        "discontinued" if lo == P.NEVER else "censored" if hi == np.inf else "recovered"
        for lo, hi in zip(left, right, strict=True)
    ]
    group = pd.DataFrame(
        {
            "outcome": kinds,
            "lower_days": [5.0 if lo == P.NEVER else float(lo) for lo in left],
            "upper_days": [float(hi) if np.isfinite(hi) else np.nan for hi in right],
        }
    )
    found = P.ttr_brackets(group)
    assert list(found[0]) == list(left) and list(found[1]) == list(right)
    return group


def median_of(left: list[float], right: list[float]) -> float | None:
    """The builder's median for a group with these brackets."""
    return T.median_days(P.turnbull(left, right), group_of(left, right))


def test_the_median_is_that_of_the_capped_days_to_recovery() -> None:
    inf = np.inf
    # reached before the cap: the median itself (mass spread over (100, 300])
    assert median_of([100], [300]) == pytest.approx(200.0)
    assert median_of([365, 365], [365.5, 365.5]) == 365.0  # just past the cap
    # above the cap: the cap ((300, 500] holds everything; one half is reached at 400)
    assert median_of([300], [500]) == 365.0
    # never reached, and known to be past the cap: discontinuations, or censored after it
    assert median_of([0, P.NEVER, P.NEVER], [10, inf, inf]) == 365.0
    assert median_of([0, 400, 400], [10, inf, inf]) == 365.0
    # exactly at the cap
    assert median_of([365], [inf]) == 365.0
    # left open: every statement censored before the cap, so nothing says where one half lies
    assert median_of([50, 60], [inf, inf]) is None
    assert median_of([0, 364, 364], [10, inf, inf]) is None
    # open mass too small to matter: 2/3 recover in (0, 10], so the median is known
    assert median_of([0, 0, 50], [10, 10, inf]) == pytest.approx(7.5)


def test_a_discontinuation_does_not_hide_statements_censored_before_the_cap() -> None:
    inf = np.inf
    # Two statements censored at 50 and 60 days: open. One discontinuation beside them must not
    # turn that into a known 365: the curve then has all its mass on (NEVER, inf), which says
    # nothing of how far the censored statements were followed.
    curve = P.turnbull([50, 60, P.NEVER], [inf, inf, inf])
    assert list(curve.left) == [P.NEVER] and list(curve.mass) == [1.0]
    assert median_of([50, 60, P.NEVER], [inf, inf, inf]) is None
    # 40 recover by day 10, 100 are censored at day 50, one is discontinued: still open
    left = [0.0] * 40 + [50.0] * 100 + [P.NEVER]
    assert median_of(left, [10.0] * 40 + [inf] * 101) is None
    # exactly half discontinued: the other half could all recover before the cap
    assert median_of([50, P.NEVER], [inf, inf]) is None
    # more than half discontinued: at least half the group is at the cap, whatever the others do
    assert median_of([50, P.NEVER, P.NEVER], [inf, inf, inf]) == 365.0
    # one statement followed to the cap: the curve is known there, and it is below one half
    assert median_of([50, 365, P.NEVER], [inf, inf, inf]) == 365.0
    # the same through a recovery bracket that ends past the cap: a third of the mass lies on
    # (60, 400] and the rest never recovers; with the bracket ending at 364 days nothing was
    # followed to the cap, and two of four discontinued are not more than half
    assert median_of([50, 60, P.NEVER, P.NEVER], [inf, 400, inf, inf]) == 365.0
    assert median_of([50, 60, P.NEVER, P.NEVER], [inf, 364, inf, inf]) is None
    # a median reached before the cap is the median, whatever was discontinued
    assert median_of([50, 60, P.NEVER], [inf, 364, inf]) == pytest.approx(364.0)
    # through the table: a class with no stated end, censored early, with one discontinuation
    rows = [
        statement("F31", "2020-06-01", "tbd", outcome=("censored", 50, None)),
        statement("F32", "2020-06-02", "tbd", outcome=("censored", 60, None)),
        statement("F33", "2020-06-03", "tbd", outcome=("discontinued", 5, 9)),
    ]
    frame = P.prepare(as_table(rows))
    listed = T.no_date_rows(frame, "tbd", "TBD or unknown", min_cell=3)
    assert [r["median_days_to_recovery"] for r in listed] == [None, None, None]
    assert [(r["basis"], r["statements"]) for r in listed] == [
        ("cell", 3),
        ("form", 3),
        ("form", 3),
    ]
    shown = rd.render_slip_table([rd.SlipRow(**r) for r in listed])
    assert shown.count("| TBD or unknown | first | 3 | cell | n/a | n/a | n/a |") == 1


def test_a_dated_row_rests_on_the_statements_of_its_basis() -> None:
    table = as_table(small_rows())
    frame = P.prepare(table)
    fit = T.version_statements(frame, FIT)
    dated = P.fitting_rows(fit, ("dated",))
    assert sorted(T.basis_group(dated, "month_year", "first", "cell").index) == [
        "F01",
        "F02",
        "F03",
    ]
    assert len(T.basis_group(dated, "month_year", "second", "form")) == 4
    assert len(T.basis_group(dated, "range", "first", "all dated forms")) == len(dated) == 8
    # the group and the calibrator's estimate must be of the same statements
    calibrator = P.fit_calibrator(fit, 3)
    assert len(T.dated_rows(calibrator, dated, "month_year", "a month and year")) == 3
    with pytest.raises(ValueError, match="rests on 3 statements and its cell holds 2"):
        T.dated_rows(calibrator, dated.drop(index="F01"), "month_year", "a month and year")
    # year/first and year/second are censored at 364 and at 365 days: with the six others the
    # pooled group is followed past the cap, and its median (one half reached at 40 days) is
    # below it; the group of the two alone has a statement followed to the cap
    pooled = T.dated_rows(calibrator, dated, "year", "a year")[0]
    assert (pooled["basis"], pooled["statements"]) == ("all dated forms", 8)
    assert pooled["median_days_to_recovery"] == pytest.approx(40.0, abs=1e-4)
    year = dated[dated["form"] == "year"]
    assert T.median_days(P.turnbull(*P.ttr_brackets(year)), year) == 365.0
    assert T.median_days(P.turnbull(*P.ttr_brackets(year.loc[["F14"]])), year.loc[["F14"]]) is None


# --------------------------------------------------------------------------------------------
# The examples
# --------------------------------------------------------------------------------------------


def test_the_pool_is_read_in_draw_rank_order(tmp_path: Path) -> None:
    path = tmp_path / "pool.csv"
    path.write_text("statement_group_id,draw_rank\nS3,10\nS1,2\nS2,1\n", encoding="utf-8")
    assert T.read_pool(path) == ["S2", "S1", "S3"]  # by number, not by text: 10 after 2
    for text, message in (
        ("statement_group_id,rank\nS1,1\n", "no draw_rank column"),
        ("statement_group_id,draw_rank\nS1,1\nS2,1\n", "repeats a draw_rank or a statement"),
        ("statement_group_id,draw_rank\nS1,1\nS1,2\n", "repeats a draw_rank or a statement"),
        ("statement_group_id,draw_rank\nS1,first\n", "must be a whole number"),
    ):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            T.read_pool(path)


def test_the_first_resolved_statements_of_the_pool_are_the_examples_in_its_order() -> None:
    built = small_build()
    for split in ("fit", "fit+dev"):  # the same examples in both versions
        assert [ex["item_id"] for ex in built[split]["examples"]] == ["F15", "F01", "F03"]
    assert built["fit"]["examples"] == built["fit+dev"]["examples"]
    shown = built["manifest"]["examples"]
    assert shown == {"pool": 6, "shown": ["F15", "F01", "F03"], "passed_over_unresolved": ["F14"]}
    table = as_table(small_rows())
    examples, passed = T.draw_examples(table, list(reversed(SMALL_POOL)), limit=2)
    assert [ex["item_id"] for ex in examples] == ["F05", "F04"] and passed == []
    with pytest.raises(ValueError, match="holds 5 resolved statements; the record shows 6"):
        T.draw_examples(table, SMALL_POOL, limit=6)


def test_what_an_example_shows() -> None:
    not_recovered, recovered, discontinued = small_build()["fit"]["examples"]
    assert not_recovered == {
        "item_id": "F15",
        "date_of_update": "2020-03-02",
        "outcome": "not_recovered",
        "type_of_update": "Revised",
        "availability_information": "Next release in about 30 days (F15)",
        "related_information": "Check wholesalers",
        "stated_end": "2020-04-01",
        "recovered_after": None,
        "recovered_by": None,
        "followed_until": "2021-03-02",  # 365 days after the statement: the lower bound
        "generic_name": "Drug F15 Injection",
        "company_name": "Acme Pharma",
        "form": "a year",
        "revision": "second",
    }
    assert list(not_recovered) == list(T.EXAMPLE_KEYS)
    assert (recovered["outcome"], recovered["recovered_after"], recovered["recovered_by"]) == (
        "recovered",
        "2020-01-30",
        "2020-02-19",
    )  # F01, dated 2020-01-10, recovered in (20, 40] days
    assert recovered["followed_until"] is None and recovered["form"] == "a month and year"
    assert discontinued["outcome"] == "discontinued"
    assert {discontinued[k] for k in ("recovered_after", "recovered_by", "followed_until")} == {
        None
    }
    text = rd.render_examples([rd.ResolvedExample(**ex) for ex in (not_recovered, recovered)])
    assert "Outcome: not recovered within 365 days of the update." in text
    assert "recovered between 2020-01-30 and 2020-02-19, 20 to 40 days after the update." in text
    assert "Drug F15" not in text and "Acme" not in text


def test_a_statement_censored_before_365_days_is_not_resolved() -> None:
    rows = {r["statement_group_id"]: r for r in small_rows()}
    assert T.resolved_example(rows["F14"]) is None  # censored at 364 days
    assert T.resolved_example(rows["F15"])["outcome"] == "not_recovered"  # at 365 days
    assert T.resolved_example(rows["D04"]) is None  # censored at 100 days
    assert T.resolved_example({**rows["F01"], "outcome": "not_at_risk"}) is None


def test_a_pool_that_does_not_fit_the_table_is_refused() -> None:
    table = as_table(small_rows())
    with pytest.raises(ValueError, match=r"does not hold: \['S404'\]"):
        T.draw_examples(table, ["F01", "S404"], limit=1)
    for sid in ("D01", "F07", "F16", "X01"):  # a dev, a TBD, a vague and a test statement
        with pytest.raises(ValueError, match=f"not so: \\['{sid}'\\]"):
            T.draw_examples(table, ["F01", sid], limit=1)
    stale = [
        {**r, "analysis_set": "stale"} if r["statement_group_id"] == "F01" else r
        for r in small_rows()
    ]
    with pytest.raises(ValueError, match=r"not so: \['F01'\]"):
        T.draw_examples(as_table(stale), ["F01"], limit=1)


# --------------------------------------------------------------------------------------------
# The two versions: what enters each
# --------------------------------------------------------------------------------------------


def test_each_version_rests_on_statements_dated_before_its_cut() -> None:
    table = as_table(small_rows())
    frame = P.prepare(table)
    dates = table.set_index("statement_group_id")["event_date"]
    fit = T.version_statements(frame, FIT)
    both = T.version_statements(frame, FIT_DEV)
    assert sorted(fit.index) == [f"F{k:02d}" for k in range(1, 16)]  # not F16, not F17
    assert sorted(set(both.index) - set(fit.index)) == ["D01", "D02", "D03", "D04", "D05"]
    assert dates[fit.index].max() < "2021-01-01" and dates[both.index].max() < "2023-01-01"
    built = small_build()
    assert (built["fit"]["since"], built["fit"]["through"]) == ("2019-11-05", "2020-12-30")
    assert (built["fit+dev"]["since"], built["fit+dev"]["through"]) == ("2019-11-05", "2022-12-20")
    for split, cut in (("fit", "2021-01-01"), ("fit+dev", "2023-01-01")):
        assert built[split]["through"] < cut
        assert all(ex["date_of_update"] < "2021-01-01" for ex in built[split]["examples"])
        about = built["manifest"]["versions"][split]
        assert (about["since"], about["through"]) == (
            built[split]["since"],
            built[split]["through"],
        )
    assert built["manifest"]["versions"]["fit"]["statements"] == {"dated": 8, "tbd": 4, "silent": 3}
    assert built["manifest"]["versions"]["fit+dev"]["statements"] == {
        "dated": 13,
        "tbd": 4,
        "silent": 3,
    }


def test_a_dev_outcome_moves_the_fit_and_dev_record_only() -> None:
    base = small_build()
    rows = small_rows()
    k = next(n for n, r in enumerate(rows) if r["statement_group_id"] == "D01")
    rows[k] = statement("D01", "2021-02-01", revision="second", outcome=("censored", 400, None))
    moved = small_build(rows)
    assert moved["fit"] == base["fit"]
    assert moved["fit+dev"]["slip_table"] != base["fit+dev"]["slip_table"]
    # a test-period statement gives rows for its class and nothing else: without the two test
    # statements the other rows are the same
    train = [r for r in small_rows() if r["period"] == "train"]
    without = small_build(train)
    for split in ("fit", "fit+dev"):
        assert without[split]["slip_table"] == [
            r for r in base[split]["slip_table"] if r["form"] != "a range"
        ]


def test_a_test_period_outcome_cannot_enter() -> None:
    rows = small_rows()
    sealed = statement("X03", "2024-05-10", outcome=("recovered", 20, 40))
    with pytest.raises(ValueError, match="outcome columns filled on test-period statements"):
        small_build([*rows, sealed])
    table = as_table(rows)
    frame = P.prepare(table)
    with pytest.raises(ValueError, match="fitted on train-period statements only"):
        T.version_statements(frame.assign(split="fit"), FIT)
    # a statement dated on or after the cut of the version
    ids = list(T.version_statements(frame, FIT_DEV).index)
    with pytest.raises(ValueError, match="5 statements of the fit record are dated on or after"):
        T.open_statements(table, ids, FIT)
    assert len(T.open_statements(table, ids, FIT_DEV)) == len(ids)
    # the cut itself is outside: a statement dated on the first day of the dev split, or of the
    # test period, whatever its row says of its split and period
    edge = [
        statement("F20", "2020-12-31"),
        statement("D20", "2021-01-01"),
        statement("D21", "2022-12-31", outcome=("censored", 0, None)),
        {**statement("X20", "2023-01-01", outcome=None), "period": "train"},
    ]
    edges = as_table([*rows, *edge])
    assert len(T.open_statements(edges, ["F01", "F20"], FIT)) == 2
    with pytest.raises(ValueError, match=r"1 statements of the fit record are dated .*\['D20'\]"):
        T.open_statements(edges, ["F01", "F20", "D20"], FIT)
    assert len(T.open_statements(edges, ["F20", "D20", "D21"], FIT_DEV)) == 3
    with pytest.raises(ValueError, match=r"1 statements of the fit\+dev record .*\['X20'\]"):
        T.open_statements(edges, ["D21", "X20"], FIT_DEV)
    # and a row of the test period is refused whatever its date says
    wrong = as_table([*rows, {**statement("F21", "2020-05-01"), "period": "test"}])
    with pytest.raises(ValueError, match=r"1 statements of the fit record .*\['F21'\]"):
        T.open_statements(wrong, ["F01", "F21"], FIT)


def test_a_follow_up_date_in_the_test_period_is_refused_but_for_first_sight() -> None:
    rows = small_rows()
    built = small_build(rows)
    # D05 is censored at its first capture, 2023-01-13: first-sight information, and counted
    reach = built["manifest"]["versions"]["fit+dev"]["follow_up"]
    assert reach == {
        "last_bracket_date": "2023-01-13",
        "cut": "2023-01-01",
        "statements_with_a_bracket_date_on_or_after_the_cut": 1,
        "of_them_censored_at_first_sight": 1,
    }
    # the same lower bound after an earlier first capture is follow-up into the test period
    followed = [
        {**r, "first_seen_date": "2022-12-21"} if r["statement_group_id"] == "D05" else r
        for r in rows
    ]
    with pytest.raises(ValueError, match=r"follow-up date in the test period: \['D05'\]"):
        small_build(followed)
    # and so is a recovery seen in 2023
    late = statement("D06", "2022-12-01", outcome=("recovered", 10, 43))
    with pytest.raises(ValueError, match=r"follow-up date in the test period: \['D06'\]"):
        small_build([*rows, late])
    # also when its lower bound is the first capture: the exception is for a statement censored
    # there, with no upper bound, and for nothing else
    for outcome in (("recovered", 10, 43), ("discontinued", 43, 43), ("discontinued", 43, None)):
        seen = statement("D06", "2022-12-01", outcome=outcome, seen=outcome[1])
        assert seen["first_seen_date"] == seen["lower_date"]
        with pytest.raises(ValueError, match=r"follow-up date in the test period: \['D06'\]"):
            small_build([*rows, seen])
    # the first day of the test period is in it; the last day of the train period is not
    first_day = statement("D06", "2022-12-01", outcome=("recovered", 10, 31))
    assert first_day["upper_date"] == "2023-01-01"
    with pytest.raises(ValueError, match=r"follow-up date in the test period: \['D06'\]"):
        small_build([*rows, first_day])
    last_day = statement("D06", "2022-12-01", outcome=("recovered", 10, 30))
    assert last_day["upper_date"] == "2022-12-31"
    reach = small_build([*rows, last_day])["manifest"]["versions"]["fit+dev"]["follow_up"]
    assert reach["statements_with_a_bracket_date_on_or_after_the_cut"] == 1  # D05 alone
    dates = pd.DataFrame(
        {
            "lower_date": ["2020-12-31", "2021-01-01", "2020-05-01"],
            "upper_date": ["", "", "2021-01-01"],
        }
    )
    assert list(T.bracket_dates_from(dates, date(2021, 1, 1))) == [False, True, True]


def test_the_manifest_counts_the_fit_outcomes_seen_after_the_dev_boundary() -> None:
    # PLAN section 3: a fit statement is followed to the train horizon, through the dev period.
    # F09 (censored at 400 days), F11 to F13 (at 500), F14 (at 364 days after 2020-03-01, which
    # is 2021-02-28) and F15 (at 365) have a lower bound in 2021 or 2022. The other nine fit
    # statements recover or are discontinued in 2020.
    built = small_build()
    reach = built["manifest"]["versions"]["fit"]["follow_up"]
    table = as_table(small_rows())
    fit = table[(table["split"] == "fit") & table["analysis_set"].isin(T.TABLE_SETS)]
    late = (fit["lower_date"] >= "2021-01-01") | (fit["upper_date"] >= "2021-01-01")
    assert sorted(fit.loc[late, "statement_group_id"]) == ["F09", "F11", "F12", "F13", "F14", "F15"]
    assert reach == {
        "last_bracket_date": "2022-05-14",  # F13: 500 days after 2020-12-30
        "cut": "2021-01-01",
        "statements_with_a_bracket_date_on_or_after_the_cut": 6,
        "of_them_censored_at_first_sight": 0,
    }
    # of the three examples, F15 shows a follow-up date of 2021
    assert built["manifest"]["versions"]["fit"]["examples_with_a_date_on_or_after_the_cut"] == 1
    assert built["manifest"]["versions"]["fit+dev"]["examples_with_a_date_on_or_after_the_cut"] == 0
    assert T.example_dates_from(built["fit"]["examples"], date(2020, 2, 19)) == 2
    assert T.example_dates_from(built["fit"]["examples"], date(2020, 2, 20)) == 1
    # the last bracket date can be an upper bound: F04 seen to recover only 900 days after it
    rows = small_rows()
    k = next(n for n, r in enumerate(rows) if r["statement_group_id"] == "F04")
    rows[k] = statement("F04", "2020-04-10", revision="second", outcome=("recovered", 50, 900))
    reach = small_build(rows)["manifest"]["versions"]["fit"]["follow_up"]
    assert reach["last_bracket_date"] == after("2020-04-10", 900) == "2022-09-27"
    assert reach["statements_with_a_bracket_date_on_or_after_the_cut"] == 7


def on_threads(rows: list[dict[str, str]], threads: dict[str, str]) -> list[dict[str, str]]:
    """The rows with the statements named in ``threads`` put on the thread of another one."""
    return [
        {**r, "thread_id": "T" + threads[r["statement_group_id"]]}
        if r["statement_group_id"] in threads
        else r
        for r in rows
    ]


def test_a_thread_is_followed_from_the_last_bracket_date_of_its_statements() -> None:
    rows = pd.DataFrame(
        {
            "thread_id": ["T1", "T1", "T2", ""],
            "lower_date": ["2021-03-01", "2020-05-01", "2020-06-01", "2022-10-06"],
            "upper_date": ["", "2021-04-10", "2020-07-01", ""],
        }
    )
    later = pd.DataFrame(
        {
            "thread_id": ["T1", "T1", "T2", "T2", "T3", ""],
            "event_date": [
                "2021-04-10",  # the day of the last bracket date of T1: followed to that day
                "2021-04-11",  # the day after it
                "2020-07-01",
                "2021-01-05",  # T2 was last seen in 2020
                "2021-01-05",  # a thread with no statement behind the record
                "2021-01-05",  # no thread at all: never matched with the blank thread of ``rows``
            ],
        }
    )
    assert list(T.followed_on_thread(rows, later)) == [True, False, True, False, False, False]
    assert not T.followed_on_thread(rows.iloc[:0], later).any()


def test_the_manifest_counts_the_dev_statements_whose_own_thread_the_fit_record_follows() -> None:
    # every statement on a thread of its own: nothing to count. Three of the five dev statements
    # are scoreable (D01, D02, D03); D04 and D05 are censored before their second horizon.
    key = "followed_past_their_date_"
    nothing = {key + "behind_the_table": 0, key + "by_an_example": 0}
    plain = small_build()
    assert plain["manifest"]["versions"]["fit"]["own_threads"] == {
        "shown_to": ["dev"],
        "statements": 5,
        **nothing,
        "examples_that_follow_them": [],
        "scoreable": {"statements": 3, **nothing},
    }
    # D01 (2021-02-01) on the thread of F09, a TBD statement censored on 2021-09-14;
    # D02 (2021-03-01) on that of F15, the first example, censored on 2021-03-02;
    # D04 (2021-05-01, not scoreable) on that of F13, a silent statement censored in 2022;
    # D03 (2021-04-01) on that of F01, which recovered by 2020-02-19: not followed that far.
    threads = {"D01": "F09", "D02": "F15", "D04": "F13", "D03": "F01"}
    built = small_build(on_threads(small_rows(), threads))
    assert built["fit"] == plain["fit"]  # the record itself does not change
    assert built["fit+dev"] == plain["fit+dev"]
    assert built["manifest"]["versions"]["fit"]["own_threads"] == {
        "shown_to": ["dev"],
        "statements": 5,
        key + "behind_the_table": 3,
        key + "by_an_example": 1,
        "examples_that_follow_them": ["F15"],
        "scoreable": {"statements": 3, key + "behind_the_table": 2, key + "by_an_example": 1},
    }


def test_no_test_period_statement_is_joined_to_a_thread() -> None:
    # The fit+dev record is shown with test- and late-period statements. The later rows of a
    # thread are not joined to its train statements (PLAN.md, standing rules): nothing is
    # counted for that record, whatever threads the test statements are on.
    plain = small_build()
    assert plain["manifest"]["versions"]["fit+dev"]["own_threads"] is None
    assert json.dumps(plain["manifest"]).count("own_threads") == 2
    rows = on_threads(small_rows(), {"X01": "D05", "X02": "F13"})
    early = statement("X03", "2023-01-05", outcome=None, thread_id="TD05")
    assert early["period"] == "test"
    late = statement("X04", "2026-02-01", outcome=None, thread_id="TF15")
    assert forms.split_of("2026-02-01") == "late"
    built = small_build([*rows, early, late])
    assert built == plain  # the three files are the same, the manifest included
    # the function reads train-period rows only, whatever a row says of its split
    table = as_table([*on_threads(small_rows(), {"D01": "F09"}), early, late])
    behind = T.open_statements(table, T.version_statements(P.prepare(table), FIT).index, FIT)
    both = T.open_statements(table, T.version_statements(P.prepare(table), FIT_DEV).index, FIT_DEV)
    assert T.own_threads(both, both.loc[["F15"]], table, FIT_DEV) is None
    found = T.own_threads(behind, behind.loc[["F15"]], table, FIT)
    assert (found["statements"], found["followed_past_their_date_behind_the_table"]) == (5, 1)
    mislabelled = table.assign(split="dev")  # every row called a dev row: 22 train-period rows
    found = T.own_threads(both, both.loc[["F15"]], mislabelled, FIT)
    assert found["statements"] == int((table["period"] == "train").sum()) == 22


# --------------------------------------------------------------------------------------------
# The files
# --------------------------------------------------------------------------------------------


def test_the_record_has_the_keys_of_the_harness_schema_in_order() -> None:
    built = small_build()
    for split in ("fit", "fit+dev"):
        record = built[split]
        assert list(record) == RECORD_KEYS
        assert rd.track_file_errors(record) == [] and T.harness_errors(record) == []
        assert (record["schema"], record["split"], record["seed"]) == (
            rd.TRACK_SCHEMA,
            split,
            20261001,
        )
        assert record["source"] == SOURCE | CODE
        assert all(
            list(row) == [f.name for f in fields(rd.SlipRow)] for row in record["slip_table"]
        )
    assert built["manifest"]["inputs"] == SOURCE and built["manifest"]["seed"] == 20261001
    assert built["manifest"]["code"] == CODE | {"numpy": np.__version__, "pandas": pd.__version__}


def test_a_record_the_harness_would_refuse_is_not_built(monkeypatch: pytest.MonkeyPatch) -> None:
    record = small_build()["fit"]
    assert "median outside" in " ".join(
        T.harness_errors(
            record | {"slip_table": [record["slip_table"][0] | {"median_days_to_recovery": 400}]}
        )
    )
    assert T.harness_errors(record | {"through": "2021-01-01"}) == [
        "a fit-split record must end before 2021-01-01: 2021-01-01"
    ]
    assert T.harness_errors({k: v for k, v in record.items() if k != "seed"}) == [
        "missing key 'seed'"
    ]
    monkeypatch.setattr(T, "median_days", lambda curve, group: 400.0)
    with pytest.raises(ValueError, match="the harness would refuse the fit record") as caught:
        small_build()
    assert "median outside [0, 365]" in str(caught.value)


def test_the_build_is_deterministic_and_ignores_the_order_of_the_rows() -> None:
    rows = small_rows()
    first = T.build(as_table(rows), SMALL_POOL, SOURCE, CODE, min_cell=3, limit=3)
    again = T.build(as_table(rows), SMALL_POOL, SOURCE, CODE, min_cell=3, limit=3)
    turned = T.build(as_table(rows[::-1]), SMALL_POOL, SOURCE, CODE, min_cell=3, limit=3)
    assert first == again == turned
    assert list(first) == ["track_fit.json", "track_fit_dev.json", "track_manifest.json"]
    assert all(text.endswith("}\n") and "NaN" not in text for text in first.values())
    manifest = json.loads(first[T.MANIFEST])
    for version in T.VERSIONS:
        digest = T.sha256(first[version.file].encode("utf-8"))
        assert manifest["versions"][version.split]["sha256"] == digest
        assert manifest["versions"][version.split]["file"] == version.file


def test_the_command_writes_files_the_harness_loads(written: tuple[Path, list[str]]) -> None:
    folder, _ = written
    out = folder / "out"
    assert sorted(p.name for p in out.iterdir()) == [
        "track_fit.json",
        "track_fit_dev.json",
        "track_manifest.json",
    ]
    manifest = json.loads((out / T.MANIFEST).read_text(encoding="utf-8"))
    fit, both = (rd.load_track_record(out / version.file) for version in T.VERSIONS)
    assert (fit.split, both.split) == ("fit", "fit+dev") and fit.min_cell == both.min_cell == 100
    assert fit.sha256 == manifest["versions"]["fit"]["sha256"]
    assert both.sha256 == manifest["versions"]["fit+dev"]["sha256"]
    assert (fit.since, fit.through) == ("2020-01-01", "2020-04-09")
    assert (both.since, both.through) == ("2020-01-01", "2021-04-01")
    source = json.loads((out / "track_fit.json").read_text(encoding="utf-8"))["source"]
    assert source == {
        "statements_sha256": T.sha256((folder / "statements.csv.gz").read_bytes()),
        "incontext_pool_sha256": T.sha256((folder / "pool.csv").read_bytes()),
        "builder_sha256": T.sha256(Path(T.__file__).read_bytes()),
        "predictors_sha256": T.sha256(Path(P.__file__).read_bytes()),
    }
    assert manifest["inputs"]["statements"] == (folder / "statements.csv.gz").as_posix()
    # the registered minimum: a cell of 100, a form of 100 and a class of 100
    cells = {(r.form, r.revision): (r.basis, r.statements) for r in fit.slip_table}
    assert cells[("a month and year", "first")] == ("cell", 100)
    assert cells[("a month and year", "second")] == ("form", 100)
    assert cells[("TBD or unknown", "first")] == ("cell", 100)
    assert cells[("no timing", "first")] == ("form", 100)
    assert {(r.form, r.revision): r.statements for r in both.slip_table}[
        ("TBD or unknown", "third or later")
    ] == 101
    # ten examples, the first ten resolved of the pool by rank: A000 is passed over
    assert [ex.item_id for ex in fit.examples] == [f"A{k:03d}" for k in range(1, 11)]
    assert fit.examples == both.examples and manifest["examples"]["passed_over_unresolved"] == [
        "A000"
    ]
    assert [ex.outcome for ex in fit.examples[:3]] == ["not_recovered", "discontinued", "recovered"]


def test_no_statement_or_seen_outcome_of_a_record_is_dated_on_or_after_its_cut(
    written: tuple[Path, list[str]],
) -> None:
    folder, _ = written
    manifest = json.loads((folder / "out" / T.MANIFEST).read_text(encoding="utf-8"))
    table = dataset.load_statements(folder / "statements.csv.gz")
    frame = P.prepare(table)
    for version in T.VERSIONS:
        track = rd.load_track_record(folder / "out" / version.file)
        cut = version.before.isoformat()
        rows = table.set_index("statement_group_id").loc[T.version_statements(frame, version).index]
        assert (rows["event_date"] < cut).all() and (rows["period"] == "train").all()
        assert (track.since, track.through) == (rows["event_date"].min(), rows["event_date"].max())
        assert track.through < cut
        # no bracket date of any statement behind the record is in the test period
        assert (rows["lower_date"] < "2023-01-01").all() and (
            rows["upper_date"] < "2023-01-01"
        ).all()
        for ex in track.examples:
            assert ex.date_of_update < "2021-01-01" and ex.date_of_update <= track.through
            shown = [d for d in (ex.recovered_after, ex.recovered_by, ex.followed_until) if d]
            assert all(d < "2023-01-01" for d in shown)
        reach = manifest["versions"][version.split]["follow_up"]
        assert reach["last_bracket_date"] < "2023-01-01" and reach["cut"] == cut
    # fit+dev: nothing at all on or after its cut. fit: the follow-up runs into the dev period
    # (PLAN section 3), which the manifest counts: the 100 TBD statements and A001, censored
    # at 400 days.
    both, fit = manifest["versions"]["fit+dev"], manifest["versions"]["fit"]
    assert both["follow_up"]["statements_with_a_bracket_date_on_or_after_the_cut"] == 0
    assert both["examples_with_a_date_on_or_after_the_cut"] == 0
    assert fit["follow_up"]["statements_with_a_bracket_date_on_or_after_the_cut"] == 101
    assert fit["examples_with_a_date_on_or_after_the_cut"] == 1
    # no statement shares a thread with another one: the fit record follows no dev statement
    own = fit["own_threads"]
    assert (own["shown_to"], own["statements"]) == (["dev"], 3)
    assert own["followed_past_their_date_behind_the_table"] == 0
    assert own["followed_past_their_date_by_an_example"] == 0
    assert both["own_threads"] is None  # test-period rows are not joined to a thread


def test_check_reports_files_that_are_stale(
    written: tuple[Path, list[str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, args = written
    out = folder / "out"
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    assert T.main([*args, "--check"]) == 0
    assert capsys.readouterr().out.strip() == "up to date"
    assert {p.name: p.read_bytes() for p in out.iterdir()} == before  # a check writes nothing
    # the same inputs elsewhere give the same records; the manifest names the input paths
    other = write_inputs(tmp_path / "copy")
    assert T.main(other) == 0
    for version in T.VERSIONS:
        assert (tmp_path / "copy" / "out" / version.file).read_bytes() == before[version.file]
    # a changed file, a missing file and a changed input are each reported
    copy = tmp_path / "copy" / "out"
    (copy / "track_fit.json").write_bytes(before["track_fit.json"].replace(b'"fit"', b'"fit" ', 1))
    assert T.main([*other, "--check"]) == 1
    assert capsys.readouterr().out.strip().endswith("out/track_fit.json")
    (copy / "track_fit.json").unlink()
    assert T.main([*other, "--check"]) == 1 and not (copy / "track_fit.json").exists()
    assert T.main(other) == 0 and T.main([*other, "--check"]) == 0
    rows = big_rows()
    k = next(n for n, r in enumerate(rows) if r["statement_group_id"] == "A001")
    rows[k] = statement("A001", "2020-01-02", outcome=("recovered", 20, 40))
    write_inputs(tmp_path / "copy", rows)
    capsys.readouterr()
    assert T.main([*other, "--check"]) == 1
    stale = capsys.readouterr().out.strip().removeprefix("differs from a fresh run: ").split(", ")
    assert [Path(p).name for p in stale] == ["track_fit.json", "track_fit_dev.json", T.MANIFEST]
    empty = tmp_path / "nothing"
    assert T.main([*other[:-1], str(empty), "--check"]) == 1 and not empty.exists()


def test_the_command_never_reads_or_writes_the_sealed_folder(tmp_path: Path) -> None:
    args = write_inputs(tmp_path / "in")
    for k in (1, 3, 5):
        sealed = list(args)
        sealed[k] = str(tmp_path / "sealed" / Path(args[k]).name)
        with pytest.raises(SystemExit, match="never reads the sealed folder"):
            T.main(sealed)
    assert not (tmp_path / "sealed").exists() and not (tmp_path / "in" / "out").exists()
    with pytest.raises(SystemExit):
        T.main(args[:4])  # no --out: there is no default folder


# --------------------------------------------------------------------------------------------
# The harness on the files
# --------------------------------------------------------------------------------------------


def test_the_harness_takes_each_record_for_its_items_only(written: tuple[Path, list[str]]) -> None:
    folder, _ = written
    fit, both = (rd.load_track_record(folder / "out" / version.file) for version in T.VERSIONS)
    rows = big_rows()
    dev = dev_items(rows)
    table = as_table(rows)
    test = [
        rd.ReadItem.from_dict(i)
        for i in dataset.items(table, table.loc[table["split"] == "test", "statement_group_id"])
    ]
    assert [i.item_id for i in dev] == ["D001", "D002"] and len(test) == 2
    assert rd.track_refusals(fit, dev) == []
    assert all(rd.track_precedes(fit, i) and rd.track_precedes(both, i) for i in test)
    assert rd.track_refusals(both, test) == []
    assert "fit+dev track record" in " ".join(rd.track_refusals(fit, test))
    assert "must end before every item" in " ".join(rd.track_refusals(both, dev))
    # every item finds the row of its form and revision bucket
    for track in (fit, both):
        cells = {(r.form, r.revision) for r in track.slip_table}
        assert all((i.form, i.revision) in cells for i in [*dev, *test])


def test_the_harness_renders_condition_b_on_dev_items_in_a_dry_run(
    written: tuple[Path, list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder, _ = written
    path = folder / "out" / "track_fit.json"
    track = rd.load_track_record(path)
    items = dev_items(big_rows())
    summary = rd.dry_run(
        items,
        models=["llama-3.3-70b"],
        template=TRACK_TEMPLATE,
        track=track,
        samples=1,
        temperature=0.0,
        mask_names=False,
        shift_years=0,
    )
    assert summary["items"] == 2 and summary["items_not_after_track_record"] == 0
    assert summary["condition"].endswith(f"|track={track.sha256[:16]}")
    prompt = rd.render_for(TRACK_TEMPLATE, items[1], track=rd.transform_track(track, None, 0))
    assert "It covers entries updated from 2020-01-01 to 2020-04-09." in prompt
    assert "had fewer than 100 statements" in prompt
    # 49 of 100 recover in (20, 30] days, by the stated end at 30 days; 48 more in (40, 60],
    # by 90 days after it; one half is reached at 40 + 20 * (1 / 48) days.
    assert "| a month and year | first | 100 | cell | 49% | 97% | 40 |" in prompt
    assert "| a month and year | second | 100 | form | 49% | 97% | 40 |" in prompt
    assert "| TBD or unknown | first | 100 | cell | n/a | n/a | 365 |" in prompt
    assert "| no timing | second | 100 | cell | n/a | n/a | 25 |" in prompt
    assert "This entry's form: a month and year\nThis entry's revision bucket: second" in prompt
    assert "1. Date of update: 2020-01-02" in prompt and "10. Date of update: 2020-01-11" in prompt
    assert "11. Date of update" not in prompt
    assert "Outcome: not recovered within 365 days of the update." in prompt
    assert "Outcome: discontinued without recovering." in prompt
    assert "Outcome: recovered between 2020-01-24 and 2020-02-03, 20 to 30 days after" in prompt
    assert "Drug A001" not in prompt  # the names of an example are never shown
    # masked and shifted, as in the 2x2: the record moves with the items
    masked = rd.dry_run(
        items,
        models=["llama-3.3-70b"],
        template=TRACK_TEMPLATE,
        track=track,
        samples=1,
        temperature=0.0,
        mask_names=True,
        shift_years=4,
    )
    assert masked["items_not_after_track_record"] == 0
    moved = rd.transform_track(track, rd.NameMasker(), 4)
    assert (moved.since, moved.through) == ("2024-01-01", "2024-04-09")
    # and through the harness's own command line
    monkeypatch.setattr(rd, "REPO", tmp_path)  # a dry run asks for no repository and no tag
    listed = tmp_path / "dev.jsonl"
    listed.write_text(dataset.jsonl(dataset.items(as_table(big_rows()), ["D001", "D002"])), "utf-8")
    code = rd.main(
        ["--items", str(listed), "--template", "predictive-track-v1", "--track-record", str(path),
         "--model", "llama-3.3-70b", "--dry-run", "--show", "1", "--out-root",
         str(tmp_path / "out"), "--local-root", str(tmp_path / "local")]
    )  # fmt: skip
    shown = capsys.readouterr().out
    assert code == 0 and "===== D001 (train)" in shown and "Track record: how the times" in shown
    assert json.loads(shown[shown.rindex("\n{\n") + 1 :])["items_not_after_track_record"] == 0
    assert not (tmp_path / "out").exists() and not (tmp_path / "local").exists()


# --------------------------------------------------------------------------------------------
# The open tables on disk
# --------------------------------------------------------------------------------------------

ON_DISK = dataset.STATEMENTS.is_file() and T.POOL.is_file()


@pytest.mark.skipif(not ON_DISK, reason="the statement table or the pool is not on disk")
def test_the_open_tables_give_two_records_the_harness_takes(tmp_path: Path) -> None:
    assert T.main(["--out", str(tmp_path)]) == 0
    fit, both = (rd.load_track_record(tmp_path / version.file) for version in T.VERSIONS)
    manifest = json.loads((tmp_path / T.MANIFEST).read_text(encoding="utf-8"))
    table = dataset.load_statements()
    by_id = table.set_index("statement_group_id")
    assert fit.through < "2021-01-01" <= both.through < "2023-01-01"
    assert fit.since == both.since and fit.examples == both.examples
    # every statement of an outcome analysis set, of any period, finds its row in both records
    read = table[table["analysis_set"].isin(P.SETS)]
    wanted = set(zip(read["form_label"], read["revision"], strict=True))
    for track in (fit, both):
        cells = {(r.form, r.revision) for r in track.slip_table}
        assert wanted <= cells and len(track.slip_table) == 3 * len(T.form_classes(table))
        assert all(r.basis != "cell" or r.statements >= 100 for r in track.slip_table)
    # the ten examples are the first ten resolved statements of the pool, by rank
    pool = T.read_pool(T.POOL)
    resolved = [
        sid
        for sid in pool
        if by_id.at[sid, "outcome"] in ("recovered", "discontinued")
        or (by_id.at[sid, "outcome"] == "censored" and int(by_id.at[sid, "lower_days"]) >= 365)
    ]
    assert [ex.item_id for ex in fit.examples] == resolved[:10] and len(fit.examples) == 10
    assert all(by_id.at[ex.item_id, "split"] == "fit" for ex in fit.examples)
    drawn = {sid for ids in dataset.first_draw_lists(dataset.SAMPLES).values() for sid in ids}
    assert not drawn & {ex.item_id for ex in fit.examples}
    # nor is one of them on a list drawn with the pool or before it (PLAN section 3, steps 2, 3)
    for path in (
        dataset.SAMPLES_LATER / "sample_dev_prompt.csv",
        dataset.SAMPLES_LATER / "sample_pair_seeds.csv",
        dataset.OUT / "audit_outcomes" / "outcome_train_sample.csv",
    ):
        if path.is_file():
            listed = set(dataset.read_table(path)["statement_group_id"])
            assert not listed & set(pool), path.name
    # the fit record is shown to dev items, the fit+dev record to test items
    dev = by_id[(by_id["split"] == "dev") & dataset.true(by_id["scoreable"])].index[:5]
    items = [rd.ReadItem.from_dict(i) for i in dataset.items(table, dev)]
    assert len(items) == 5 and rd.track_refusals(fit, items) == []
    summary = rd.dry_run(
        items,
        models=list(rd.PRIMARIES),
        template=TRACK_TEMPLATE,
        track=fit,
        samples=1,
        temperature=0.0,
        mask_names=False,
        shift_years=0,
    )
    assert summary["items_not_after_track_record"] == 0
    prompt = rd.render_for(TRACK_TEMPLATE, items[0], track=rd.transform_track(fit, None, 0))
    assert f"updated from {fit.since} to {fit.through}." in prompt
    assert prompt.count("\n   Outcome: ") == 10
    # the follow-up record: nothing of the test period but first-sight captures
    reach = manifest["versions"]["fit+dev"]["follow_up"]
    assert (
        reach["statements_with_a_bracket_date_on_or_after_the_cut"]
        == reach["of_them_censored_at_first_sight"]
    )
    assert manifest["versions"]["fit"]["follow_up"]["last_bracket_date"] < "2023-01-01"
    # own threads: counted for the dev statements only, and recomputed here from the table
    key = "followed_past_their_date_"
    assert manifest["versions"]["fit+dev"]["own_threads"] is None

    def last_seen(rows: pd.DataFrame) -> dict[str, str]:
        """The last bracket date of each thread among the rows."""
        last: dict[str, str] = {}
        for thread, lower, upper in zip(
            rows["thread_id"], rows["lower_date"], rows["upper_date"], strict=True
        ):
            last[thread] = max(last.get(thread, ""), lower, upper)
        return last

    def followed(last: dict[str, str], rows: pd.DataFrame) -> int:
        days = zip(rows["thread_id"], rows["event_date"], strict=True)
        return sum(1 for thread, day in days if last.get(thread, "") >= day)

    behind = table[
        (table["split"] == "fit")
        & dataset.true(table["at_risk_B"])
        & table["analysis_set"].isin(T.TABLE_SETS)
    ]
    dev = table[table["split"] == "dev"]
    scored = dev[dataset.true(dev["scoreable"])]
    by_table = last_seen(behind)
    by_example = last_seen(by_id.loc[[ex.item_id for ex in fit.examples]])
    own = manifest["versions"]["fit"]["own_threads"]
    assert (own["statements"], own["scoreable"]["statements"]) == (len(dev), len(scored))
    assert own[key + "behind_the_table"] == followed(by_table, dev)
    assert own[key + "by_an_example"] == followed(by_example, dev)
    assert own["scoreable"][key + "behind_the_table"] == followed(by_table, scored)
    assert own["scoreable"][key + "by_an_example"] == followed(by_example, scored)
    assert set(own["examples_that_follow_them"]) <= {ex.item_id for ex in fit.examples}
    assert bool(own["examples_that_follow_them"]) == bool(own[key + "by_an_example"])
