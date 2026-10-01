"""Tests for the form classifier (``forms.py``).

The cases are statement texts written the way the FDA shortage CSV writes them, each with its Date
of Update, the form class and the no-year flag. Most are verbatim or lightly shortened
training-period texts from 2018-2022; the others change the date of such a text or are
constructed for a corner, and none is taken from a text dated 2023 or later. Covered: every class
of the inventory, the precedence conflicts (relative against range, day and part of a month;
half-year against quarter; part of a month against a month with no year; a two-digit year
against a day, and two digits that cannot be a year; a recovery "TBD" beside a dated delivery;
an undated discontinuation beside a dated depletion; a dated target beside expiry dating; the
three corners of the rule reader's ranking), what ``silent`` and the dated forms mean in terms
of the rule reading (an undated depletion is not silent), the year a list lends to a yearless
month, the fields passed on from the rule reading, the merge rule, the tables of the module
docstring against the code, the splits, the statement table and its counts on a small synthetic
events table (also with no train statement and with no row; at risk through a later member),
the golden file (built, tampered with, compared after a change of the events table, and
recomputed on a sample of the real one), and determinism of both outputs.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_forms.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pandas as pd
import pytest

from analysis.coling import forms as F
from analysis.coling import rules as R

SEED = 20261001

# (text, anchor, form, no_year)
CASES: list[tuple[str, str, str, bool]] = [
    # relative: counted from the Date of Update, whatever the length of the result
    (
        "Limited supply / out of stock. Cannot support monthly demand. "
        "Estimated shortage duration: 60 days.",
        "2020-05-29",
        "relative",
        False,
    ),
    (
        "Availability through wholesalers: not available. "
        "Estimated duration of supply shortage: 3-18 months.",
        "2022-09-30",
        "relative",
        False,
    ),
    (
        "On backorder. Product expected to be released late this week or early next week",
        "2019-09-23",
        "relative",
        False,
    ),
    # range
    (
        "Additional lots are scheduled for release in the January/February timeframe.",
        "2019-11-25",
        "range",
        True,
    ),
    ("Estimated availability in 4Q 2021 to 1Q 2022", "2021-11-17", "range", False),
    ("Estimated Recovery: February 2021 - April 2021", "2020-12-10", "range", False),
    (
        "Out of stock. The earliest we expect having product available for ordering in the US "
        "market is November 4-6, 2020.",
        "2020-10-30",
        "range",
        False,
    ),
    (
        "On backorder - expected release the week of late December/early January",
        "2019-12-10",
        "range",
        True,
    ),
    # exact day
    ("Estimated release September 7, 2018", "2018-08-16", "exact_day", False),
    ("Estimated Availability: June 5, 2021", "2021-05-20", "exact_day", False),
    ("Not Available. Estimated recovery by April 1, 2019.", "2019-01-09", "exact_day", False),
    (
        "Backordered. Product will be available for order 06/05/2021",
        "2021-05-20",
        "exact_day",
        False,
    ),
    ("Next shipment expected June 15", "2020-06-01", "exact_day", True),
    ("Available by 3/5", "2021-02-20", "exact_day", True),
    # part of a month
    ("Backorder - Product availabilty ETA Late August", "2020-08-20", "part_of_month", True),
    ("Backordered. Next release mid-October", "2020-09-01", "part_of_month", True),
    (
        "Backordered.  Next delivery anticipated in late-May 2020",
        "2020-06-02",
        "part_of_month",
        False,
    ),
    ("On backorder - expected release the week of 10/28", "2019-10-09", "part_of_month", True),
    (
        "Currently on backorder - next shipment anticipated end of Mar 21",
        "2021-02-10",
        "part_of_month",
        False,
    ),
    # half-year
    ("Next Delivery: June 2021; Estimated Recovery: 1H 2022", "2021-05-21", "half_year", False),
    (
        "Availability limited to product already in pharmacies until resumption of "
        "manufacturing in the second half of 2020",
        "2020-07-22",
        "half_year",
        False,
    ),
    # quarter
    ("Next Delivery: May 2021; Estimated Recovery: Q4 2021", "2021-03-05", "quarter", False),
    ("Backordered. Next release early Q3.", "2021-05-19", "quarter", True),
    ("Limited Supply on Allocation, Recovery Q4", "2021-11-23", "quarter", True),
    ("Expected to be on allocation until sometime in 1Q20.", "2019-12-13", "quarter", False),
    # year
    ("Out of Stock, no plans to manufacture until sometime in 2023", "2022-08-24", "year", False),
    ("Not Available; Target availability in 2020", "2019-10-17", "year", False),
    (
        "Backordered. Product availability is likely to be impacted until the end of 2022.",
        "2022-09-02",
        "year",
        False,
    ),
    # a month with no year
    ("On backorder. Next release December.", "2019-11-04", "month_no_year", True),
    ("Partial shipments on allocation through April", "2021-03-29", "month_no_year", True),
    ("Limited Supply; Recovery November", "2022-09-28", "month_no_year", True),
    (
        "On backorder. Next expected releases in November and December",
        "2020-10-07",
        "month_no_year",
        True,
    ),
    # month and year
    (
        "Next Delivery: December 2019; Estimated Recovery: August 2020",
        "2019-10-07",
        "month_year",
        False,
    ),
    ("Next Delivery and Estimated Recovery: June 2021", "2019-10-07", "month_year", False),
    ("Backordered. Next release October 2020.", "2020-08-13", "month_year", False),
    ("Backordered. Estimated availability Dec-2020", "2020-10-01", "month_year", False),
    (
        "Currently on backorder - next shipment anticipated Oct 20",
        "2020-09-25",
        "month_year",
        False,
    ),
    ("Partial shipments on allocation through February 2021", "2021-01-12", "month_year", False),
    (
        "Additional stocks are expected to arrive during May and June 2020",
        "2020-04-30",
        "month_year",
        False,
    ),
    # TBD or unknown
    ("Unavailable. Estimated recovery TBD.", "2020-03-20", "tbd", False),
    ("On backorder. Shortage duration is unknown at this time.", "2019-09-09", "tbd", False),
    (
        "Availability and estimated duration of supply interruption is unknown",
        "2019-10-16",
        "tbd",
        False,
    ),
    # vague
    ("Will remain on backorder for few months", "2019-04-02", "vague", False),
    ("On long term backorder", "2020-09-25", "vague", False),
    (
        "Product is temporarily unavailable and no future production expected for an extended "
        "period.",
        "2022-07-20",
        "vague",
        False,
    ),
    # a delivery stated with no time
    ("Product will be made available as it is released.", "2019-10-04", "no_date", False),
    (
        "Additional lots are scheduled to be manufactured. Product will be made available as it "
        "is released.",
        "2019-05-08",
        "no_date",
        False,
    ),
    # discontinuation, dated or not
    ("To be discontinued on or near March 2021", "2020-12-01", "discontinuation", False),
    ("To be discontinued in 2022", "2019-09-12", "discontinuation", False),
    ("Discontinuation of the manufacture of the drug.", "2020-03-25", "discontinuation", False),
    # a date in another role only
    (
        "5 month expiry (4/2022 expiry) dating available by request. || Check wholesalers for "
        "inventory",
        "2021-11-23",
        "distractor",
        False,
    ),
    (
        "Actively selling; Remaining inventory estimated to last through March 2020",
        "2020-01-16",
        "distractor",
        False,
    ),
    ("Product expected to be available until August 2021", "2021-01-28", "distractor", False),
    ("Market Exit - Estimated Run Out TBD", "2022-09-21", "distractor", False),
    # silent
    ("On backorder", "2019-05-03", "silent", False),
    ("Please check wholesalers for available inventory.", "2019-05-03", "silent", False),
    (
        "8 months expiry dating available by request. || Check wholesalers for inventory",
        "2020-10-08",
        "silent",
        False,
    ),
    ("", "2021-01-01", "silent", False),
]


@pytest.mark.parametrize(("text", "anchor", "form", "no_year"), CASES)
def test_form_of_attested_texts(text: str, anchor: str, form: str, no_year: bool) -> None:
    got = F.classify(text, anchor)
    assert (got.form, got.no_year) == (form, no_year)
    assert F.form_class(text, anchor) == form
    assert got.dated == (form in F.DATED_FORMS)
    assert (got.end is not None) or not got.dated


def test_every_form_has_a_case() -> None:
    assert {form for _, _, form, _ in CASES} == set(F.FORM_NAMES)


# --------------------------------------------------------------------------------------------
# Precedence
# --------------------------------------------------------------------------------------------


def test_relative_beats_the_granularity_of_its_result() -> None:
    day = F.classify("Estimated shortage duration: 60 days.", "2020-05-29")
    span = F.classify("Estimated duration of supply shortage: 3-18 months.", "2022-09-30")
    week = F.classify("Product expected to be released late this week", "2019-09-23")
    assert [r.granularity for r in (day, span, week)] == ["day", "range", "part_of_month"]
    assert {r.form for r in (day, span, week)} == {"relative"}
    assert (day.start, day.end) == ("2020-07-28", "2020-07-28")
    assert not any(r.no_year for r in (day, span, week))


def test_half_year_is_not_a_quarter() -> None:
    half = F.classify("Estimated Recovery: 1H 2022", "2021-05-21")
    quarter = F.classify("Estimated Recovery: Q1 2022", "2021-05-21")
    assert half.granularity == quarter.granularity == "quarter"
    assert (half.form, quarter.form) == ("half_year", "quarter")
    assert (half.start, half.end) == ("2022-01-01", "2022-06-30")


def test_part_of_month_without_year_keeps_its_class_and_sets_the_flag() -> None:
    got = F.classify("Backordered. Next release mid-October", "2020-09-01")
    assert (got.form, got.no_year) == ("part_of_month", True)
    assert (got.start, got.end) == ("2020-10-11", "2020-10-20")


def test_two_digit_year_or_day() -> None:
    text = "Currently on backorder - next shipment anticipated in May 21"
    as_year = F.classify(text, "2021-01-08")
    assert (as_year.form, as_year.no_year, as_year.end) == ("month_year", False, "2021-05-31")
    as_day = F.classify(text, "2015-03-02")  # 2021 is too far from 2015 to be a year
    assert (as_day.form, as_day.no_year, as_day.end) == ("exact_day", True, "2015-05-21")


def test_two_digits_that_cannot_be_a_year_leave_the_year_unwritten() -> None:
    # "15" is neither a year near 2021 nor, after a hyphen or a part word, a day
    month = F.classify("Backordered. Estimated availability Dec-15", "2021-01-10")
    assert (month.form, month.no_year, month.end) == ("month_no_year", True, "2021-12-31")
    part = F.classify("Currently on backorder - next shipment anticipated mid Feb 15", "2021-01-10")
    assert (part.form, part.no_year, part.end) == ("part_of_month", True, "2021-02-20")
    near = F.classify("Backordered. Estimated availability Dec-21", "2021-01-10")
    assert (near.form, near.no_year, near.end) == ("month_year", False, "2021-12-31")


def test_recovery_tbd_beats_a_dated_delivery() -> None:
    got = F.classify("Next Delivery: May 2021; Estimated Recovery: TBD", "2021-03-05")
    assert (got.form, got.statement_type, got.end) == ("tbd", "recovery", None)
    assert (got.certainty, got.rule_certainty, got.abstain_reason) == (
        "undetermined",
        "unknown",
        "tbd",
    )


def test_recovery_form_beats_the_delivery_form() -> None:
    got = F.classify("Next Delivery: Q2 2020; Estimated Recovery: Late 2020", "2019-10-11")
    assert (got.form, got.start, got.end) == ("year", "2020-09-01", "2020-12-31")


def test_vague_recovery_beats_an_unknown_delivery() -> None:
    text = "Long-term backorder for all skus. No estimated release date at this time."
    got = F.classify(text, "2019-04-02")
    assert (got.form, got.certainty, got.abstain_reason) == ("vague", "estimated", "vague")


def test_undated_discontinuation_beats_a_dated_depletion() -> None:
    text = (
        "Discontinuation of the manufacture of the drug. Current supply expected to deplete by "
        "May/June 2020 timeframe."
    )
    got = F.classify(text, "2020-03-25")
    assert (got.form, got.end, got.distractor_dates) == ("discontinuation", None, 1)
    assert (got.certainty, got.abstain_reason) == ("undetermined", "no_date")


def test_a_target_beside_expiry_dating_keeps_its_form() -> None:
    dated = F.classify(
        "6 month expiry (4/2022 expiry) dating available by request. Next release December 2021.",
        "2021-10-08",
    )
    assert (dated.form, dated.end, dated.distractor_dates) == ("month_year", "2021-12-31", 1)
    unknown = F.classify(
        "5 month expiry (1/2022 expiry) dating available by request. Next release date not "
        "available at this time.",
        "2021-08-25",
    )
    assert (unknown.form, unknown.distractor_dates) == ("tbd", 1)
    alone = F.classify("5 month expiry (1/2022 expiry) dating available by request.", "2021-08-25")
    assert (alone.form, alone.distractor_dates, alone.end) == ("distractor", 1, None)


def test_distractor_dates_are_counted() -> None:
    got = F.classify(
        "6 & 9 month expiry (4/2022 & 7/2022 expiry) dating available by request. Next release "
        "December 2021.",
        "2021-10-08",
    )
    assert (got.form, got.end, got.distractor_dates) == ("month_year", "2021-12-31", 2)


def test_ranking_corners_of_the_rule_reader() -> None:
    """The three corners named in the module docstring, as the frozen rule reader ranks them."""
    anchor = "2021-01-10"
    dated = "To be discontinued in March 2021."
    undated = "Product will be made available as it is released."
    # a dated discontinuation outranks a delivery with no time, in either order
    assert F.form_class(f"{dated} {undated}", anchor) == "discontinuation"
    assert F.form_class(f"{undated} {dated}", anchor) == "discontinuation"
    # and ties with a delivery under an unknown marker: the first mentioned wins
    unknown = "Next release date TBD."
    assert F.form_class(f"{dated} {unknown}", anchor) == "discontinuation"
    assert F.form_class(f"{unknown} {dated}", anchor) == "tbd"
    # a discontinuation under an unknown marker ties with a delivery with no time
    assert F.form_class(f"Discontinuation date TBD. {undated}", anchor) == "discontinuation"
    assert F.form_class(f"{undated} Discontinuation date TBD.", anchor) == "no_date"
    # a bare "TBD" ties with a vague recovery; one with a recovery cue beats it
    assert F.form_class("Long-term backorder. TBD", anchor) == "vague"
    assert F.form_class("TBD. Long-term backorder", anchor) == "tbd"
    assert F.form_class("Long-term backorder. Estimated recovery TBD.", anchor) == "tbd"
    # across types the order holds: a vague recovery beats a dated delivery
    assert F.form_class("Long-term backorder. Next release June 2021.", anchor) == "vague"


def test_end_of_supply_dates_are_distractors_with_their_period() -> None:
    until = F.classify("Product expected to be available until August 2021", "2021-01-28")
    assert (until.form, until.dated, until.end) == ("distractor", False, "2021-08-31")
    assert (until.statement_type, until.rule_statement_type) == ("depletion", "availability_until")
    stock = F.classify("Approximately 2 months of inventory on hand", "2022-03-04")
    assert (stock.form, stock.pattern, stock.no_year) == ("distractor", "relative_supply", False)


def test_undated_depletion_is_a_distractor_not_silent() -> None:
    unknown = F.classify("Market Exit - Estimated Run Out TBD", "2022-09-21")
    assert (unknown.form, unknown.statement_type, unknown.abstain_reason, unknown.end) == (
        "distractor",
        "depletion",
        "tbd",
        None,
    )
    assert (unknown.certainty, unknown.distractor_dates) == ("undetermined", 0)
    vague = F.classify("Inventory expected to deplete soon", "2022-09-21")
    assert (vague.form, vague.statement_type, vague.abstain_reason) == (
        "distractor",
        "depletion",
        "vague",
    )


# further texts for the class definitions; the second and third are constructed, not attested
PROBES: list[tuple[str, str]] = [
    ("Market Exit - Estimated Run Out TBD", "2022-09-21"),
    ("Inventory expected to deplete soon", "2022-09-21"),
    ("Product expected to be available until further notice", "2022-09-21"),
    ("Discontinuation of the manufacture of the drug.", "2020-03-25"),
    ("The last batches will expire September 30, 2019.", "2018-12-19"),
    ("Product available as of July 1, 2022.", "2022-09-02"),
    ("Product will be made available as it is released.", "2019-10-04"),
]


def test_silent_means_no_statement_and_no_date() -> None:
    """``silent`` is the rule reading "none" with no dated mention, and nothing else is; a
    dated form is a recovery or next-delivery target with a period, and nothing else is."""
    for text, anchor in [(t, a) for t, a, _, _ in CASES] + PROBES:
        got = F.classify(text, anchor)
        none = got.rule_statement_type == "none"
        assert (got.form == "silent") == (none and got.distractor_dates == 0), text
        assert (got.certainty == "no_statement") == none, text
        estimate = got.rule_statement_type in F.ESTIMATE_TYPES
        assert got.dated == (estimate and got.end is not None), text
        if got.form in ("tbd", "vague", "no_date"):
            assert estimate and got.end is None and got.abstain_reason == got.form, text


def test_year_lent_by_a_list() -> None:
    # read after May 2020, a yearless May would be May 2021; the list says 2020
    lent = F.classify(
        "Additional stocks are expected to arrive during May and June 2020", "2020-06-15"
    )
    assert (lent.form, lent.no_year, lent.end, lent.stale) == (
        "month_year",
        False,
        "2020-05-31",
        True,
    )
    chain = F.classify(
        "Limited Inventory to be released during November, December 2019 and January 2020",
        "2019-09-11",
    )
    assert (chain.form, chain.no_year, chain.end) == ("month_year", False, "2019-11-30")
    # the year passes through a month that does not write one: May takes 2020 by way of June
    through = F.classify(
        "Backordered. Next deliveries expected in May, June and July 2020", "2020-06-15"
    )
    assert (through.form, through.no_year, through.end) == ("month_year", False, "2020-05-31")
    unwritten = F.classify(
        "Backordered. Next deliveries expected in May, June and July", "2020-06-15"
    )
    assert (unwritten.form, unwritten.no_year) == ("month_no_year", True)
    none = F.classify("On backorder. Next expected releases in November and December", "2020-10-07")
    assert (none.form, none.no_year, none.end) == ("month_no_year", True, "2020-11-30")
    apart = F.classify(
        "Lots are anticipated in April; additional inventory in May 2022.", "2022-04-11"
    )
    assert (apart.form, apart.no_year) == ("month_no_year", True)
    # a day, a part of a month or a month followed by two digits that cannot be a year takes its
    # year from the Date of Update and passes that on, so the written year at the end of the
    # list does not reach the first month
    for middle in ("June 5", "late June", "Dec-15"):
        cut = F.classify(f"Next deliveries expected in May, {middle} and July 2022", "2021-01-10")
        assert (cut.form, cut.no_year, cut.end) == ("month_no_year", True, "2021-05-31"), middle
    whole = F.classify("Next deliveries expected in May, June and July 2022", "2021-01-10")
    assert (whole.form, whole.no_year, whole.end) == ("month_year", False, "2022-05-31")


# --------------------------------------------------------------------------------------------
# Fields passed on from the rule reading
# --------------------------------------------------------------------------------------------


def test_fields_of_a_bounded_day() -> None:
    got = F.classify("Not Available. Estimated recovery by April 1, 2019.", "01/09/2019")
    assert got == F.FormReading(
        form="exact_day",
        no_year=False,
        distractor_dates=0,
        statement_type="recovery",
        certainty="estimated",
        rule_statement_type="recovery",
        rule_certainty="estimated",
        start="2019-01-09",
        end="2019-04-01",
        granularity="day",
        bound="by",
        abstain_reason=None,
        stale=False,
        pattern="month_day",
    )
    row = got.as_row()
    assert tuple(row) == F.GOLDEN_COLUMNS[2:]
    assert (row["abstain_reason"], row["bound"], row["stale"]) == ("", "by", False)


def test_stale_and_certainty_classes() -> None:
    stale = F.classify("Unavailable, recovery in May 2020", "2020-06-02")
    assert (stale.form, stale.stale, stale.certainty, stale.rule_certainty) == (
        "month_year",
        True,
        "asserted",
        "firm",
    )
    hedged = F.classify("Backordered. Next release expected October 2020.", "2020-08-13")
    assert (hedged.certainty, hedged.rule_certainty) == ("estimated", "expected")
    silent = F.classify("On backorder", "2019-05-03")
    assert (silent.statement_type, silent.certainty, silent.abstain_reason) == (
        "none",
        "no_statement",
        "no_statement",
    )
    assert silent.as_row()["end"] == ""


def test_agrees_with_the_rule_reader() -> None:
    for text, anchor, _, _ in CASES:
        got, r = F.classify(text, anchor), R.read(text, anchor)
        assert [got.start, got.end] == (r.interval or [None, None])
        assert (got.rule_statement_type, got.granularity, got.stale) == (
            r.statement_type,
            r.granularity,
            r.stale,
        )
        assert got.statement_type == R.as_literal_v1(r)["statement_type"]
        assert got.certainty == R.as_literal_v1(r)["certainty"]


def test_classify_accepts_none_and_both_date_formats() -> None:
    assert F.classify(None, "2021-01-01").form == "silent"
    text = "Backordered. Next release October 2020."
    assert F.classify(text, "08/13/2020") == F.classify(text, "2020-08-13")


# --------------------------------------------------------------------------------------------
# Inventory and merging
# --------------------------------------------------------------------------------------------

LARGE = dict.fromkeys(F.FORM_NAMES, 100)


def test_inventory() -> None:
    assert len(F.FORM_NAMES) == len(set(F.FORM_NAMES)) == 15
    assert F.FORM_NAMES[:9] == F.DATED_FORMS
    assert len(set(F.LABELS.values())) == 15
    assert F.LABELS["month_year"] == "a month and year"
    dated = set(F.DATED_FORMS)
    for name in F.FORM_NAMES:
        seen, at = [name], name
        while at in F.MERGE_INTO:
            at = F.MERGE_INTO[at]
            assert at in F.FORM_NAMES and at not in seen
            seen.append(at)
        assert at == ("month_year" if name in dated else "silent")
        assert all((n in dated) == (name in dated) for n in seen)


def test_statement_types_and_certainty_classes_are_those_of_the_literal_schema() -> None:
    assert len(F.STATEMENT_TYPES) == 5 and len(F.CERTAINTIES) == 4
    assert set(F.STATEMENT_TYPES) == set(R.STATEMENT_TYPES) - {"availability_until"}
    assert set(F.CERTAINTIES) == set(R.LITERAL_V1_CERTAINTY.values()) | {
        "undetermined",
        "no_statement",
    }
    assert set(R.LITERAL_V1_CERTAINTY) == set(R.CERTAINTIES) - {"unknown"}
    for text, anchor in [(t, a) for t, a, _, _ in CASES] + PROBES:
        got = F.classify(text, anchor)
        assert got.statement_type in F.STATEMENT_TYPES and got.certainty in F.CERTAINTIES
        assert got.rule_statement_type in R.STATEMENT_TYPES and got.rule_certainty in R.CERTAINTIES


def test_module_docstring_tables_match_the_code() -> None:
    doc = F.__doc__ or ""
    numbered = re.findall(r"^\s*(\d+)  (\w+) ", doc, flags=re.MULTILINE)
    assert [int(n) for n, _ in numbered] == list(range(1, 16))
    assert tuple(name for _, name in numbered) == F.FORM_NAMES
    arrows = re.findall(r"(\w+) -> (\w+)", doc)
    assert len(arrows) == len(F.MERGE_INTO) and dict(arrows) == F.MERGE_INTO
    assert f"``MIN_TRAIN`` ({F.MIN_TRAIN})" in doc


def test_merge_map_keeps_large_classes() -> None:
    assert F.merge_map(LARGE) == {n: n for n in F.FORM_NAMES}
    assert F.merge_map(dict.fromkeys(F.FORM_NAMES, 15)) == {n: n for n in F.FORM_NAMES}


def test_merge_map_small_classes_go_to_their_neighbour() -> None:
    counts = {**LARGE, "relative": 5, "half_year": 3, "year": 14, "vague": 6, "no_date": 19}
    merged = F.merge_map(counts)
    assert merged["relative"] == "range"
    assert merged["half_year"] == merged["year"] == merged["quarter"] == "quarter"
    assert merged["vague"] == merged["no_date"] == "no_date"
    assert merged["tbd"] == "tbd"
    changed = {n for n, c in merged.items() if n != c}
    assert changed == {"relative", "half_year", "year", "vague"}


def test_merge_map_chains_until_large_enough() -> None:
    merged = F.merge_map({**LARGE, "vague": 3, "no_date": 5})
    assert merged["vague"] == merged["no_date"] == "tbd"
    merged = F.merge_map({**LARGE, "relative": 2, "range": 4})
    assert merged["relative"] == merged["range"] == "month_year"
    merged = F.merge_map({**LARGE, "exact_day": 0})
    assert merged["exact_day"] == "part_of_month"


def test_merge_map_examines_forms_in_inventory_order() -> None:
    both = F.merge_map({**LARGE, "discontinuation": 10, "distractor": 10})
    assert both["discontinuation"] == both["distractor"] == "distractor"
    tiny = F.merge_map({**LARGE, "discontinuation": 3, "distractor": 4})
    assert tiny["discontinuation"] == tiny["distractor"] == "silent"


def test_merge_map_never_merges_the_two_ends_and_rejects_unknown_forms() -> None:
    merged = F.merge_map({})
    assert {merged[n] for n in F.DATED_FORMS} == {"month_year"}
    assert {merged[n] for n in F.FORM_NAMES if n not in F.DATED_FORMS} == {"silent"}
    assert F.merge_map(LARGE, minimum=101)["tbd"] == "silent"
    with pytest.raises(ValueError, match="not in the inventory"):
        F.merge_map({"other": 3})


def test_merged_label() -> None:
    assert F.merged_label(["quarter"]) == "a quarter"
    assert F.merged_label(["quarter", "half_year"]) == "a half-year or a quarter"
    assert F.merged_label(["year", "quarter", "half_year"]) == "a half-year, a quarter or a year"


# --------------------------------------------------------------------------------------------
# Splits, statements and counts on a synthetic events table
# --------------------------------------------------------------------------------------------


def test_split_of() -> None:
    days = ["2014-02-18", "2020-12-31", "2021-01-01", "2022-12-31", "2023-01-01", "2025-12-31"]
    assert [F.split_of(d) for d in days] == ["fit", "fit", "dev", "dev", "test", "test"]
    assert [F.split_of(d) for d in ("2026-01-01", "2026-09-26")] == ["late", "late"]
    assert F.TEST_START == R.TEST_START


def event(
    event_id: str,
    group: str,
    day: str,
    text: str,
    listing: str = "shortage",
    status: str = "current",
    availability: str = "unavailable",
) -> dict[str, str]:
    return {
        "event_id": event_id,
        "statement_group_id": group,
        "listing": listing,
        "event_date": day,
        "status_at_statement": status,
        "availability_class": availability,
        "statement_text": text,
        "company_name": "Acme Pharma",
    }


def synthetic_events() -> pd.DataFrame:
    month = "Next Delivery: May {y}; Estimated Recovery: July {y}"
    rows = [
        # S1: two presentations of one fit statement; only the second is at risk under B
        event("E02", "S1", "2020-03-01", month.format(y=2020), availability="available"),
        event("E01", "S1", "2020-03-01", month.format(y=2020)),
        # S2: fit, TBD, resolved at first sight: on the shortage listing but not at risk
        event("E03", "S2", "2020-06-01", "Estimated recovery TBD.", status="resolved"),
        # S3: dev, quarter with no year, available: at risk under A only
        event("E04", "S3", "2021-11-23", "Recovery Q4", availability="available"),
        # S4: dev, a discontinuation-listing statement
        event(
            "E05",
            "S4",
            "2022-02-01",
            "To be discontinued on or near March 2022",
            listing="discontinuation",
            status="discontinued",
        ),
        # S5: test, silent
        event("E06", "S5", "2023-01-01", "On backorder"),
        # S6: test, month and year beside expiry dating
        event(
            "E07",
            "S6",
            "2024-05-01",
            "6 month expiry (4/2025 expiry) dating available by request. Next release June 2024.",
        ),
        # S7: late, two members whose texts differ in case; "may" in lower case is the verb
        event("E08", "S7", "2026-02-01", "Next release May 2026"),
        event("E09", "S7", "2026-02-01", "Next release may 2026"),
        # S8: fit, the same text as S1 on another date
        event("E10", "S8", "2020-04-01", month.format(y=2020)),
    ]
    return pd.DataFrame(rows)


def test_statement_forms() -> None:
    st = F.statement_forms(synthetic_events()).set_index("statement_group_id")
    assert list(st.index) == [f"S{i}" for i in range(1, 9)]
    assert st.loc["S1", ["event_id", "split", "form"]].tolist() == ["E01", "fit", "month_year"]
    assert st.loc["S1", ["at_risk_A", "at_risk_B"]].tolist() == [True, True]
    assert st.loc["S2", ["form", "at_risk_A", "at_risk_B"]].tolist() == ["tbd", False, False]
    assert st.loc["S3", ["split", "form", "no_year"]].tolist() == ["dev", "quarter", True]
    assert st.loc["S3", ["at_risk_A", "at_risk_B"]].tolist() == [True, False]
    # the yearless quarter is read at the statement's own date
    assert st.loc["S3", ["start", "end"]].tolist() == ["2021-10-01", "2021-12-31"]
    assert st.loc["S4", ["listing", "form", "at_risk_A"]].tolist() == [
        "discontinuation",
        "discontinuation",
        False,
    ]
    assert st.loc["S5", ["split", "form"]].tolist() == ["test", "silent"]
    assert st.loc["S6", ["form", "distractor_dates", "end"]].tolist() == [
        "month_year",
        1,
        "2024-06-30",
    ]
    assert st.loc["S7", ["event_id", "split", "form", "member_forms"]].tolist() == [
        "E08",
        "late",
        "month_year",
        2,
    ]
    assert (st["member_forms"].drop("S7") == 1).all()


def test_at_risk_needs_the_shortage_listing_and_any_member() -> None:
    text = "Backordered. Next release October 2020."
    rows = [
        # T1: the member with the smallest id is Resolved; the second is Current and available;
        # the third is Current and unavailable
        event("E01", "T1", "2020-08-13", text, status="resolved"),
        event("E02", "T1", "2020-08-13", text, availability="available"),
        event("E03", "T1", "2020-08-13", text),
        # T2: only Current and available members: at risk under A, not under B
        event("E04", "T2", "2020-08-14", text, availability="available"),
        event("E05", "T2", "2020-08-14", text, availability="available"),
        # T3: a discontinuation-listing row is never at risk, whatever its status says
        event("E06", "T3", "2020-08-15", text, listing="discontinuation"),
        # T4 to T6: a limited, blank or other availability class is not "available"
        event("E07", "T4", "2020-08-16", text, availability="limited"),
        event("E08", "T5", "2020-08-17", text, availability="blank"),
        event("E09", "T6", "2020-08-18", text, availability="other"),
    ]
    st = F.statement_forms(pd.DataFrame(rows)).set_index("statement_group_id")
    assert st["event_id"].tolist() == ["E01", "E04", "E06", "E07", "E08", "E09"]
    assert st["at_risk_A"].tolist() == [True, True, False, True, True, True]
    assert st["at_risk_B"].tolist() == [True, False, False, True, True, True]
    report = F.tabulate(st.reset_index())
    assert report["statements"]["shortage"]["all"] == 5
    assert report["statements"]["at_risk_A"]["all"] == 5
    assert report["statements"]["at_risk_B"]["all"] == 4


def test_statement_forms_needs_its_columns() -> None:
    with pytest.raises(ValueError, match="statement_text"):
        F.statement_forms(synthetic_events().drop(columns="statement_text"))
    undated = synthetic_events()
    undated.loc[3, "event_date"] = None
    with pytest.raises(ValueError, match="no event_date"):
        F.statement_forms(undated)
    with pytest.raises(ValueError, match="no event_date"):
        F.golden_frame(undated)


def test_an_events_table_with_no_train_statement() -> None:
    events = synthetic_events()
    late = events[events["event_date"] >= "2023-01-01"]
    assert len(F.golden_frame(late)) == 0
    report = F.tabulate(F.statement_forms(late))
    assert report["statements"]["all"] == {
        "fit": 0,
        "dev": 0,
        "test": 2,
        "late": 1,
        "train": 0,
        "all": 3,
    }
    assert set(report["merge"]["train_counts"].values()) == {0}
    assert set(report["merge"]["merged_form"].values()) == {"month_year", "silent"}
    empty = F.tabulate(F.statement_forms(events.iloc[:0]))
    assert empty["statements"]["all"]["all"] == 0 and empty["form"]["all"]["silent"]["all"] == 0
    # a class with no statement still has its row of zeros, in every table and population
    zero = {"fit": 0, "dev": 0, "test": 0, "late": 0, "train": 0, "all": 0}
    for made in (report, empty):
        for population in F.POPULATIONS:
            assert tuple(made["form"][population]) == F.FORM_NAMES
            assert tuple(made["no_year"][population]) == F.DATED_FORMS
            assert tuple(made["statement_type"][population]) == F.STATEMENT_TYPES
            assert tuple(made["certainty"][population]) == F.CERTAINTIES
        assert made["statement_type"]["all"]["depletion"] == zero


def test_tabulate_rejects_a_value_outside_its_list() -> None:
    statements = F.statement_forms(synthetic_events())
    for column in ("form", "statement_type", "certainty"):
        wrong = statements.copy()
        wrong.loc[0, column] = "other"
        with pytest.raises(ValueError, match=column):
            F.tabulate(wrong)


def test_tabulate_counts_statements_by_form_split_and_population() -> None:
    report = F.tabulate(F.statement_forms(synthetic_events()))
    form = report["form"]
    assert list(form) == list(F.POPULATIONS)
    assert list(form["all"]) == list(F.FORM_NAMES)
    zero = {"fit": 0, "dev": 0, "test": 0, "late": 0, "train": 0, "all": 0}
    assert form["all"]["month_year"] == {
        **zero,
        "fit": 2,
        "test": 1,
        "late": 1,
        "train": 2,
        "all": 4,
    }
    assert form["all"]["discontinuation"] == {**zero, "dev": 1, "train": 1, "all": 1}
    assert form["shortage"]["discontinuation"] == zero
    assert form["shortage"]["tbd"] == {**zero, "fit": 1, "train": 1, "all": 1}
    assert form["at_risk_A"]["tbd"] == zero
    assert form["at_risk_A"]["quarter"] == {**zero, "dev": 1, "train": 1, "all": 1}
    assert form["at_risk_B"]["quarter"] == zero
    assert report["statements"] == {
        "all": {"fit": 3, "dev": 2, "test": 2, "late": 1, "train": 5, "all": 8},
        "shortage": {"fit": 3, "dev": 1, "test": 2, "late": 1, "train": 4, "all": 7},
        "at_risk_A": {"fit": 2, "dev": 1, "test": 2, "late": 1, "train": 3, "all": 6},
        "at_risk_B": {"fit": 2, "dev": 0, "test": 2, "late": 1, "train": 2, "all": 5},
    }
    for population in F.POPULATIONS:
        total = report["statements"][population]["all"]
        assert sum(row["all"] for row in form[population].values()) == total
        assert sum(row["all"] for row in report["merged_form"][population].values()) == total
        assert sum(row["all"] for row in report["statement_type"][population].values()) == total
        assert sum(row["all"] for row in report["certainty"][population].values()) == total
    assert report["no_year"]["all"]["quarter"]["dev"] == 1
    assert sum(row["all"] for row in report["no_year"]["all"].values()) == 1
    assert report["with_distractor_date"]["all"] == {**zero, "test": 1, "all": 1}
    assert report["statements_with_mixed_member_forms"] == 1


def test_tabulate_applies_the_merge_rule_on_train_counts_of_the_primary_population() -> None:
    report = F.tabulate(F.statement_forms(synthetic_events()))
    merge = report["merge"]
    assert (merge["minimum"], merge["population"]) == (15, "at_risk_B")
    assert merge["train_counts"]["month_year"] == 2  # S1 and S8; S6 and S7 are not train
    assert sum(merge["train_counts"].values()) == 2
    assert set(merge["merged_form"].values()) == {"month_year", "silent"}
    assert [c["form"] for c in merge["classes"]] == ["month_year", "silent"]
    assert merge["classes"][0]["members"] == list(F.DATED_FORMS)
    assert list(report["merged_form"]["all"]) == ["month_year", "silent"]
    assert report["merged_form"]["all"]["month_year"]["all"] == 5
    assert report["merged_form"]["all"]["silent"]["all"] == 3
    assert [f["name"] for f in report["inventory"]] == list(F.FORM_NAMES)
    assert report["inventory"][0] == {
        "name": "relative",
        "label": "a relative time",
        "dated": True,
        "merge_into": "range",
    }


# --------------------------------------------------------------------------------------------
# The golden file
# --------------------------------------------------------------------------------------------


def test_golden_frame_holds_train_pairs_only_and_no_text() -> None:
    events = synthetic_events()
    frame = F.golden_frame(events)
    assert tuple(frame.columns) == F.GOLDEN_COLUMNS
    # S1 (two members) and S8 share a text on two dates; S2, S3 and S4 are the other train pairs
    assert len(frame) == 5
    assert frame["anchor"].max() < "2023-01-01"
    assert list(frame[["text_sha256", "anchor"]].itertuples(index=False)) == sorted(
        frame[["text_sha256", "anchor"]].itertuples(index=False)
    )
    month = F.text_key("Next Delivery: May 2020; Estimated Recovery: July 2020")
    assert len(month) == 16
    assert frame.loc[frame["text_sha256"] == month, "anchor"].tolist() == [
        "2020-03-01",
        "2020-04-01",
    ]
    assert set(frame.loc[frame["text_sha256"] == month, "end"]) == {"2020-07-31"}
    cells = frame.astype(str).to_numpy().ravel().tolist()
    assert not any(text and text in cell for text in events["statement_text"] for cell in cells)


def test_golden_bytes_are_reproducible(tmp_path: Path) -> None:
    events = synthetic_events()
    first = F.gz_bytes(F.golden_frame(events))
    again = F.gz_bytes(F.golden_frame(events.sample(frac=1.0, random_state=SEED)))
    assert first == again
    assert first[4:8] == b"\x00\x00\x00\x00"  # the gzip header carries no time
    path = tmp_path / "golden.csv.gz"
    path.write_bytes(first)
    back = F.read_golden(path)
    assert back.equals(F.golden_frame(events).astype(str))
    assert F.golden_mismatches(back, events) == []


def test_golden_mismatches_reports_changed_missing_and_extra_rows() -> None:
    events = synthetic_events()
    golden = F.golden_frame(events).astype(str)
    changed = golden.copy()
    was = changed.loc[0, "form"]
    changed.loc[0, "form"] = "relative"
    found = F.golden_mismatches(changed, events)
    assert len(found) == 1 and found[0].endswith(f"form 'relative' -> {was!r}")
    found = F.golden_mismatches(golden.iloc[1:], events)
    assert len(found) == 1 and found[0].endswith("only in the events table")
    found = F.golden_mismatches(golden, events[events["statement_group_id"] != "S2"])
    assert len(found) == 1 and found[0].endswith("only in the golden file")
    assert F.golden_mismatches(golden.drop(columns="pattern"), events)[0].startswith("columns")


def test_golden_diff_separates_changed_readings_from_changed_events() -> None:
    events = synthetic_events()
    golden = F.golden_frame(events).astype(str)
    assert F.golden_diff(golden, events) == ([], [])
    # a new events table (S2 gone, so the first golden row may be missing) and a changed reading
    last = len(golden) - 1
    was = golden.loc[last, "end"]
    golden.loc[last, "end"] = "2099-12-31"
    kept = golden.loc[last, "text_sha256"]
    fewer = events[events["statement_text"].map(F.text_key) == kept]
    changed, one_sided = F.golden_diff(golden, fewer)
    assert len(changed) == 1 and changed[0].endswith(f"end '2099-12-31' -> {was!r}")
    assert len(changed) + len(one_sided) == len(golden) - len(F.golden_frame(fewer)) + 1
    assert all(line.endswith("only in the golden file") for line in one_sided)
    assert F.golden_mismatches(golden, fewer) == changed + one_sided


def test_rules_file_is_the_frozen_one() -> None:
    assert F.sha16(Path(R.__file__).read_bytes()) == F.RULES_SHA256


@pytest.fixture(scope="module")
def real_files() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not (F.EVENTS.exists() and F.GOLDEN.exists()):
        pytest.skip("run from the repository root after building events.csv.gz and the golden file")
    return F.load_events(), F.read_golden()


def test_golden_file_sample_is_reproduced(real_files: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    """A seeded sample of the golden file, with every form in it, recomputed from the texts of
    the events table."""
    events, golden = real_files
    train = events[events["event_date"] < F.TEST_START.isoformat()]
    texts = {
        (F.text_key(t), d): t
        for t, d in zip(train["statement_text"], train["event_date"], strict=True)
    }
    keys = sorted(zip(golden["text_sha256"], golden["anchor"], strict=True))
    assert max(anchor for _, anchor in keys) < F.TEST_START.isoformat()
    # after a rebuild of the events table the pairs both hold still pin the rule reader;
    # test_outputs_are_up_to_date says whether the file must be rewritten
    shared = [key for key in keys if key in texts]
    assert shared, "no pair of the golden file is in the events table"
    rows = golden.set_index(["text_sha256", "anchor"])
    # 400 pairs over all forms, and up to 25 more of each form so that no class goes unchecked
    rng = random.Random(SEED)
    sample = set(rng.sample(shared, min(400, len(shared))))
    for form in F.FORM_NAMES:
        of_form = [key for key in shared if rows.at[key, "form"] == form]
        sample.update(rng.sample(of_form, min(25, len(of_form))))
    for key in sorted(sample):
        now = {k: str(v) for k, v in F.classify(texts[key], key[1]).as_row().items()}
        assert now == rows.loc[key].to_dict(), key
    assert set(golden["form"]) <= set(F.FORM_NAMES)
    dated = golden["form"].isin(F.DATED_FORMS)
    assert (golden.loc[dated, "end"] != "").all() and (golden.loc[dated, "pattern"] != "").all()
    assert golden.loc[dated, "rule_statement_type"].isin(F.ESTIMATE_TYPES).all()
    none = (golden["rule_statement_type"] == "none") & (golden["distractor_dates"] == "0")
    assert ((golden["form"] == "silent") == none).all()


def test_outputs_are_up_to_date(real_files: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    if not F.COUNTS.exists():
        pytest.skip("form_counts.json has not been written")
    assert F.main(["--check"]) == 0, "stale outputs: python -m analysis.coling.forms"
    report = json.loads(F.COUNTS.read_text())
    assert report["inputs"]["rules_sha256"] == F.RULES_SHA256
    assert report["command"] == F.COMMAND
    assert report["golden"]["rows"] == len(real_files[1])
    for population, totals in report["statements"].items():
        for table in ("form", "merged_form", "statement_type", "certainty"):
            rows = report[table][population].values()
            assert {s: sum(row[s] for row in rows) for s in totals} == totals, (table, population)
    merged = F.load_merge()
    assert merged == F.merge_map(report["merge"]["train_counts"])
    assert report["merge"]["train_counts"] == {
        name: row["train"] for name, row in report["form"][F.MERGE_POPULATION].items()
    }


# --------------------------------------------------------------------------------------------
# Command line and determinism
# --------------------------------------------------------------------------------------------


def write_events(folder: Path) -> Path:
    path = folder / "events.csv.gz"
    synthetic_events().to_csv(path, index=False, compression=F.GZIP)
    return path


def test_main_writes_both_outputs_reproducibly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    events = write_events(tmp_path)
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    assert F.main(["--events", str(events), "--out", str(out_a)]) == 0
    assert F.main(["--events", str(events), "--out", str(out_b)]) == 0
    printed = capsys.readouterr().out
    assert "month_year" in printed and "golden rows: 5" in printed
    for name in (F.COUNTS.name, F.GOLDEN.name):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()
    report = json.loads((out_a / F.COUNTS.name).read_text())
    assert F.load_merge(out_a / F.COUNTS.name) == report["merge"]["merged_form"]
    assert report["inputs"]["events"] == events.as_posix()
    assert report["inputs"]["events_sha256"] == F.sha16(events.read_bytes())
    assert report["command"] == f"{F.COMMAND} --events {events.as_posix()}"
    assert report["inputs"]["forms_sha256"] == F.sha16(Path(F.__file__).read_bytes())
    assert report["golden"] == {
        "file": F.GOLDEN.name,
        "rows": 5,
        "sha256": F.sha16((out_a / F.GOLDEN.name).read_bytes()),
    }
    assert report["form"]["all"]["month_year"]["all"] == 4


def test_check_detects_a_stale_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    events = write_events(tmp_path)
    args = ["--events", str(events), "--out", str(tmp_path)]
    assert F.main([*args, "--check"]) == 1  # nothing written yet
    assert F.main(args) == 0
    assert F.main([*args, "--check"]) == 0
    assert "up to date" in capsys.readouterr().out
    golden = F.read_golden(tmp_path / F.GOLDEN.name)
    golden.loc[0, "end"] = "2099-12-31"
    (tmp_path / F.GOLDEN.name).write_bytes(F.gz_bytes(golden))
    assert F.main([*args, "--check"]) == 1
    printed = capsys.readouterr().out
    assert "differs from a fresh run" in printed and "'2099-12-31' ->" in printed
    assert "readings changed on shared pairs: 1; pairs on one side only: 0" in printed
    assert F.GOLDEN.name in printed and F.COUNTS.name not in printed
    # a counts file that no longer matches is reported as well, on its own
    assert F.main(args) == 0
    counts = tmp_path / F.COUNTS.name
    report = json.loads(counts.read_text())
    report["form"]["all"]["month_year"]["fit"] += 1
    counts.write_text(F.report_text(report))
    capsys.readouterr()
    assert F.main([*args, "--check"]) == 1
    printed = capsys.readouterr().out
    assert F.COUNTS.name in printed and F.GOLDEN.name not in printed


def test_load_merge_rejects_another_inventory(tmp_path: Path) -> None:
    path = tmp_path / "form_counts.json"
    path.write_text(json.dumps({"merge": {"merged_form": {"month_year": "month_year"}}}))
    with pytest.raises(ValueError, match="inventory"):
        F.load_merge(path)


def test_main_classifies_one_text(capsys: pytest.CaptureFixture[str]) -> None:
    assert F.main(["--text", "Backordered. Next release early Q3.", "--anchor", "2021-05-19"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert (got["form"], got["no_year"], got["end"]) == ("quarter", True, "2021-07-31")
    with pytest.raises(SystemExit):
        F.main(["--text", "On backorder"])
