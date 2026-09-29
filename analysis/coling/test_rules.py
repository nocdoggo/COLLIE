"""Tests for the rule-based literal reader (``rules.py``).

The cases are notice texts written the way the FDA shortage CSV writes them (most are verbatim
training-period texts from 2019-2022, a few are composed from attested forms), each with its
Date of Update and the reading the frozen conventions define. Covered: every statement type,
TBD and no-estimate abstentions, vague spans, early/mid/late parts, yearless months, two-digit
years, quarters (Q4 2027, 4Q 2027, 4Q27, late Q3), halves, years, ranges across a year end,
"timeframe" ranges, week forms, day dates, relative durations, "by" bounds, stale estimates,
distractor dates (expiry, depletion, available until), certainty classes, the literal-v1 order
of statement types, the literal-v1 mapping, the modal "may", masking, the capture loader and the
JSONL batch mode.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_rules.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.coling import rules as R

# (text, anchor, statement_type, interval or None, granularity or abstain_reason, certainty)
CASES: list[tuple[str, str, str, tuple[str, str] | None, str, str]] = [
    # the dominant form: next delivery and recovery in one notice; recovery is the reading
    (
        "Next Delivery: December 2019; Estimated Recovery: August 2020",
        "10/07/2019",
        "recovery",
        ("2020-08-01", "2020-08-31"),
        "month",
        "estimated",
    ),
    (
        "Limited Supply Available. Next Delivery and Estimated Recovery: October 2019",
        "10/07/2019",
        "recovery",
        ("2019-10-01", "2019-10-31"),
        "month",
        "estimated",
    ),
    (
        "Next Delivery: September 2020; Estimated Recovery: TBD",
        "09/10/2020",
        "recovery",
        None,
        "tbd",
        "unknown",
    ),
    (
        "Next Delivery: May 2021; Estimated Recovery: 1H 2022",
        "05/10/2021",
        "recovery",
        ("2022-01-01", "2022-06-30"),
        "quarter",
        "estimated",
    ),
    (
        "Next Delivery: October 2019; Estimated Recovery: Late 2020",
        "10/11/2019",
        "recovery",
        ("2020-09-01", "2020-12-31"),
        "year",
        "estimated",
    ),
    # a semicolon typo still carries the recovery cue into the next clause
    (
        "Limited Supply Available. Next Delivery: Septemeber 2021; Estimated Recovery; "
        "November 2021",
        "09/22/2021",
        "recovery",
        ("2021-11-01", "2021-11-30"),
        "month",
        "firm",
    ),
    (
        "Backordered. Next release October 2019.",
        "10/18/2019",
        "next_delivery",
        ("2019-10-01", "2019-10-31"),
        "month",
        "firm",
    ),
    (
        "Backordered. Next release date not available at this time.",
        "10/18/2019",
        "next_delivery",
        None,
        "tbd",
        "unknown",
    ),
    (
        "Long-term backorder for all skus. No estimated release date at this time.",
        "05/28/2019",
        "recovery",
        None,
        "vague",
        "unknown",
    ),
    ("Out of Stock - Resupply TBD", "10/18/2019", "recovery", None, "tbd", "unknown"),
    (
        "On backorder. Shortage duration is unknown at this time.",
        "09/09/2019",
        "recovery",
        None,
        "tbd",
        "unknown",
    ),
    # early / mid / late and "end of"
    (
        "Currently on backorder - next shipment anticipated mid-December 2020",
        "12/01/2020",
        "next_delivery",
        ("2020-12-11", "2020-12-20"),
        "part_of_month",
        "anticipated",
    ),
    (
        "Stocked out; Recovery late January 2021",
        "12/15/2020",
        "recovery",
        ("2021-01-21", "2021-01-31"),
        "part_of_month",
        "firm",
    ),
    (
        "On backorder. Expected release early January 2020",
        "12/10/2019",
        "next_delivery",
        ("2020-01-01", "2020-01-10"),
        "part_of_month",
        "expected",
    ),
    (
        "Unavailable, recovery estimated End of May 2019",
        "04/08/2019",
        "recovery",
        ("2019-05-21", "2019-05-31"),
        "part_of_month",
        "estimated",
    ),
    # two-digit years written after the month
    (
        "Currently on backorder - next shipment anticipated end of Oct 20",
        "10/13/2020",
        "next_delivery",
        ("2020-10-21", "2020-10-31"),
        "part_of_month",
        "anticipated",
    ),
    (
        "Backorder, Recovery expected Nov-22",
        "10/05/2022",
        "recovery",
        ("2022-11-01", "2022-11-30"),
        "month",
        "expected",
    ),
    # a month with no year: the next occurrence on or after the anchor month
    (
        "On backorder. Next release December.",
        "11/04/2019",
        "next_delivery",
        ("2019-12-01", "2019-12-31"),
        "month",
        "firm",
    ),
    (
        "Limited supply; Recovery August",
        "09/15/2022",
        "recovery",
        ("2023-08-01", "2023-08-31"),
        "month",
        "firm",
    ),
    (
        "Partial shipments on allocation through March",
        "02/19/2021",
        "recovery",
        ("2021-03-01", "2021-03-31"),
        "month",
        "firm",
    ),
    # quarters and halves
    (
        "Unavailable. Estimated recovery: Q1 2020",
        "10/18/2019",
        "recovery",
        ("2020-01-01", "2020-03-31"),
        "quarter",
        "estimated",
    ),
    (
        "Estimated recovery 4Q2019",
        "05/21/2019",
        "recovery",
        ("2019-10-01", "2019-12-31"),
        "quarter",
        "estimated",
    ),
    (
        "Next Delivery and Estimated Recovery: Late Q3 2023",
        "11/16/2022",
        "recovery",
        ("2023-09-01", "2023-09-30"),
        "quarter",
        "estimated",
    ),
    (
        "Limited Supply Recovery Q4",
        "10/03/2022",
        "recovery",
        ("2022-10-01", "2022-12-31"),
        "quarter",
        "firm",
    ),
    (
        "Estimated recovery: 4Q 2027",
        "06/01/2026",
        "recovery",
        ("2027-10-01", "2027-12-31"),
        "quarter",
        "estimated",
    ),
    (
        "Estimated recovery: Q4 2027",
        "06/01/2026",
        "recovery",
        ("2027-10-01", "2027-12-31"),
        "quarter",
        "estimated",
    ),
    (
        "Unavailable, resupply Q4 2022/Q1 2023",
        "09/20/2022",
        "recovery",
        ("2022-10-01", "2023-03-31"),
        "range",
        "firm",
    ),
    (
        "This product discontinuation is a business related decision. Anticipated discontinuance "
        "time is first quarter of the year 2020.",
        "06/21/2019",
        "discontinuation",
        ("2020-01-01", "2020-03-31"),
        "quarter",
        "anticipated",
    ),
    # ranges and "timeframe"
    (
        "Additional lots are scheduled for manufacturing in the November - December 2019 "
        "timeframe. Product will be made available as it is released.",
        "09/12/2019",
        "next_delivery",
        ("2019-11-01", "2019-12-31"),
        "range",
        "firm",
    ),
    (
        "Additional lots are scheduled for release in the January/February timeframe.",
        "11/25/2019",
        "next_delivery",
        ("2020-01-01", "2020-02-29"),
        "range",
        "firm",
    ),
    (
        "On backorder - expected release the week of late December/early January",
        "12/10/2019",
        "next_delivery",
        ("2019-12-21", "2020-01-10"),
        "range",
        "expected",
    ),
    (
        "Unavailable, Resupply Anticipated End of October/Early November",
        "10/01/2020",
        "recovery",
        ("2020-10-21", "2020-11-10"),
        "range",
        "anticipated",
    ),
    (
        "Present shipment 2nd week of May 2020, next shipment mid- to late-June 2020",
        "05/05/2020",
        "next_delivery",
        ("2020-06-11", "2020-06-30"),
        "part_of_month",
        "firm",
    ),
    # days and weeks
    (
        "Estimated Availability: October 4, 2022",
        "09/09/2022",
        "recovery",
        ("2022-10-04", "2022-10-04"),
        "day",
        "estimated",
    ),
    (
        "Product availability is planned for 18-Sep-2020.",
        "08/12/2020",
        "recovery",
        ("2020-09-18", "2020-09-18"),
        "day",
        "firm",
    ),
    (
        "On backorder - expected release the week of 12/16/2019",
        "12/10/2019",
        "next_delivery",
        ("2019-12-16", "2019-12-22"),
        "part_of_month",
        "expected",
    ),
    (
        "Back in stock week 3 of May 2020",
        "05/19/2020",
        "recovery",
        ("2020-05-15", "2020-05-21"),
        "part_of_month",
        "firm",
    ),
    # relative durations (a month is 30 days) and "by" bounds
    (
        "Limited supply / out of stock. Cannot support monthly demand. Estimated shortage "
        "duration: 60 days.",
        "05/29/2020",
        "recovery",
        ("2020-07-28", "2020-07-28"),
        "day",
        "estimated",
    ),
    (
        "Availability through wholesalers: not available. Estimated duration of supply shortage: "
        "3-18 months.",
        "10/01/2022",
        "recovery",
        ("2022-12-30", "2024-03-24"),
        "range",
        "estimated",
    ),
    (
        "Estimated recovery by End of June 2020",
        "05/06/2020",
        "recovery",
        ("2020-05-06", "2020-06-30"),
        "part_of_month",
        "estimated",
    ),
    # shortage and availability "until"
    (
        "Not available until April 2021.",
        "01/15/2021",
        "recovery",
        ("2021-04-01", "2021-04-30"),
        "month",
        "firm",
    ),
    (
        "Available, however limited supply until mid December 2019",
        "11/20/2019",
        "recovery",
        ("2019-12-11", "2019-12-20"),
        "part_of_month",
        "firm",
    ),
    (
        "Product is currently on backorder. Estimated shortage duration is until August 2020.",
        "06/10/2020",
        "recovery",
        ("2020-08-01", "2020-08-31"),
        "month",
        "estimated",
    ),
    (
        "Pfizer anticipates stock available through May 1st, 2021.",
        "11/01/2020",
        "availability_until",
        ("2021-05-01", "2021-05-01"),
        "day",
        "anticipated",
    ),
    # end of supply
    (
        "To be discontinued on or near November 2019.",
        "07/17/2019",
        "discontinuation",
        ("2019-11-01", "2019-11-30"),
        "month",
        "estimated",
    ),
    (
        "Discontinued. No longer available for orders starting December 2022.",
        "11/30/2022",
        "discontinuation",
        ("2022-12-01", "2022-12-31"),
        "month",
        "firm",
    ),
    (
        "Discontinuation of the manufacture of the drug.",
        "09/19/2019",
        "discontinuation",
        None,
        "no_date",
        "unknown",
    ),
    (
        "Actively selling; Remaining inventory estimated to last through April 2020",
        "01/15/2020",
        "depletion",
        ("2020-04-01", "2020-04-30"),
        "month",
        "estimated",
    ),
    (
        "Estimated Inventory Depletion: June 2020",
        "03/20/2020",
        "depletion",
        ("2020-06-01", "2020-06-30"),
        "month",
        "estimated",
    ),
    # nothing forward-looking, only a distractor date
    (
        "7 months expiry (expiry 6/30/2021) dating available by request.",
        "11/16/2020",
        "none",
        None,
        "no_statement",
        "unknown",
    ),
    ("Available", "10/07/2019", "none", None, "no_statement", "unknown"),
    # a bare date in the availability field
    (
        "Stocked Out, December 2021",
        "08/25/2021",
        "recovery",
        ("2021-12-01", "2021-12-31"),
        "month",
        "firm",
    ),
]


@pytest.mark.parametrize(("text", "anchor", "kind", "interval", "gran", "certainty"), CASES)
def test_reading(
    text: str,
    anchor: str,
    kind: str,
    interval: tuple[str, str] | None,
    gran: str,
    certainty: str,
) -> None:
    r = R.read(text, anchor)
    assert r.statement_type == kind
    assert r.interval == (list(interval) if interval else None)
    assert r.abstain is (interval is None)
    if interval is None:
        assert r.abstain_reason == gran and r.granularity is None
    else:
        assert r.granularity == gran and r.abstain_reason is None
    assert r.certainty == certainty
    assert r.statement_type in R.STATEMENT_TYPES and r.certainty in R.CERTAINTIES


def test_enough_real_looking_cases() -> None:
    assert len(CASES) >= 30


def test_distractors_for_a_recovery_reading() -> None:
    text = (
        "Currently Lanoxin Adult Ampule is available however current stock short-dates (6 months "
        "remaining shelf-life) at end of June 2021. Covis anticipates availability again by mid "
        "August 2021."
    )
    r = R.read(text, "2021-06-08")
    assert r.statement_type == "recovery"
    assert r.interval == ["2021-06-08", "2021-08-20"]  # "by mid August": anchor to 20 Aug
    assert r.bound == "by"
    assert r.distractor_dates == [
        {"text": "end of June 2021", "role": "expiry", "interval": ["2021-06-21", "2021-06-30"]}
    ]


def test_expiry_and_depletion_dates_are_distractors() -> None:
    r = R.read(
        "6 & 7 month expiry (9/2021 & 10/2021 expiry) dating available by request. "
        "Next release April 2021.",
        "2021-03-15",
    )
    assert r.statement_type == "next_delivery"
    assert [d["role"] for d in r.distractor_dates] == ["expiry", "expiry"]
    assert r.distractor_dates[0]["interval"] == ["2021-09-01", "2021-09-30"]
    r = R.read(
        "Product is available with an expected supply duration until JUL 2022. Recovery "
        "expected Q4 2022.",
        "2022-05-01",
    )
    assert r.statement_type == "recovery"
    assert r.distractor_dates == [
        {"text": "JUL 2022", "role": "availability_until", "interval": ["2022-07-01", "2022-07-31"]}
    ]


def test_literal_v1_type_order_puts_discontinuation_before_depletion() -> None:
    r = R.read(
        "Supply expected to exhaust late September 2022; Discontinuation of the manufacture of "
        "the drug.",
        "2022-09-08",
    )
    assert (r.statement_type, r.abstain_reason) == ("discontinuation", "no_date")
    assert r.distractor_dates[0]["role"] == "depletion"
    assert r.distractor_dates[0]["interval"] == ["2022-09-21", "2022-09-30"]


def test_explicit_recovery_beats_other_recovery_cues() -> None:
    r = R.read(
        "Limited supply available. Presentation will go on backorder by Mid-April, 2021. "
        "Expected resupply by end of July, 2021. Product recovery by end of August 2021",
        "2021-04-02",
    )
    assert r.statement_type == "recovery"
    assert r.interval == ["2021-04-02", "2021-08-31"]
    assert "onset" in [d["role"] for d in r.distractor_dates]
    r = R.read("Backorder. Off Backorder by end of April, recovery in May", "2021-04-01")
    assert r.interval == ["2021-05-01", "2021-05-31"]


def test_stale_estimate() -> None:
    r = R.read("Next Delivery: June 2020; Estimated Recovery: July 2020", "2020-09-15")
    assert r.stale is True and r.interval == ["2020-07-01", "2020-07-31"]
    assert R.read("Recovery: March 2021", "2021-01-10").stale is False


def test_two_digit_number_after_a_month_is_a_day_when_not_a_plausible_year() -> None:
    r = R.read("Next shipment expected June 15", "2020-05-01")
    assert r.interval == ["2020-06-15", "2020-06-15"] and r.granularity == "day"


def test_month_and_month_borrows_the_year() -> None:
    r = R.read("Additional stocks are expected to arrive during May and June 2020", "2020-03-01")
    assert r.interval == ["2020-05-01", "2020-05-31"]
    got = [(s["text"], s["interval"]) for s in r.statements]
    assert got == [
        ("May", ["2020-05-01", "2020-05-31"]),
        ("June 2020", ["2020-06-01", "2020-06-30"]),
    ]


def test_modal_may_is_not_a_month() -> None:
    r = R.read(
        "Shipments of 3mg are continuing to occur however due to high demand there may be "
        "intermittent periods of backorder.",
        "2022-12-15",
    )
    assert r.statement_type == "none" and r.statements == []
    assert R.read("Available. Next release May 2021", "2021-04-01").interval == [
        "2021-05-01",
        "2021-05-31",
    ]


def test_within_and_relative_durations() -> None:
    r = R.read("Next release within 2 weeks", "2021-03-01")
    assert r.interval == ["2021-03-01", "2021-03-15"] and r.granularity == "range"
    r = R.read("Estimated recovery in 4-6 weeks", "2021-03-01")
    assert r.interval == ["2021-03-29", "2021-04-12"]


def test_vague_span_is_an_abstention() -> None:
    r = R.read("Will remain on backorder for few months", "2019-04-02")
    assert (r.statement_type, r.abstain, r.abstain_reason) == ("recovery", True, "vague")


def test_certainty_hedges() -> None:
    assert R.read("Recovery expected July 2020", "2020-05-01").certainty == "expected"
    assert R.read("Next shipment anticipated July 2020", "2020-05-01").certainty == "anticipated"
    assert R.read("Next Delivery ETA Mid August 2021", "2021-07-20").certainty == "estimated"
    assert R.read("Resupply Mid-August 2021", "2021-07-20").certainty == "firm"
    assert R.read("Recovery TBD", "2021-07-20").certainty == "unknown"


def test_joined_fields_split_into_clauses() -> None:
    text = "Unavailable || Next shipment TBD"
    r = R.read(text, "2020-03-01")
    assert (r.statement_type, r.abstain_reason) == ("next_delivery", "tbd")
    item = {"availability_information": "Available", "related_information": "Available"}
    assert R.item_text(item) == "Available"


def test_as_literal_v1() -> None:
    r = R.read("Stock anticipated to be available through October 2022", "2022-08-01")
    out = R.as_literal_v1(r)
    assert out == {
        "statement_type": "depletion",
        "interval": {"start": "2022-10-01", "end": "2022-10-31"},
        "certainty": "estimated",
        "stale": False,
        "quote": "October 2022",
    }
    assert R.as_literal_v1(R.read("Recovery TBD", "2021-01-01"))["interval"] == "ABSTAIN"
    assert R.as_literal_v1(R.read("Recovery TBD", "2021-01-01"))["certainty"] == "undetermined"
    assert R.as_literal_v1(R.read("Available", "2021-01-01"))["certainty"] == "no_statement"
    assert R.as_literal_v1(R.read("Recovery: March 2021", "2021-01-01"))["certainty"] == (
        "asserted"
    )


def test_reading_is_json_serialisable() -> None:
    r = R.read("Next Delivery: May 2021; Estimated Recovery: TBD", "2021-03-05")
    back = json.loads(json.dumps(r.as_dict()))
    assert back["statement_type"] == "recovery" and back["abstain"] is True


def test_mask() -> None:
    assert R.mask("Next Delivery: May 2021; Estimated Recovery: Q3 2022") == (
        "Next Delivery: <MON> <YYYY>; Estimated Recovery: Q<N> <YYYY>"
    )


def test_capture_loader_and_split(tmp_path: Path) -> None:
    header = (
        "Generic Name,Company Name, Contact Info, Presentation, Type of Update,Date of Update, "
        "Availability Information, Related Information"
    )
    rows = [
        'Alpha,Acme,1,10 mg,Revised,03/05/2021,"Next Delivery: May 2021; Estimated Recovery: '
        'TBD",""',
        'Alpha,Acme,1,20 mg,Revised,02/01/2023,"Unavailable","Recovery late March 2023"',
    ]
    body = "\r\n\r\n" + header + "\r\n" + "\r\n".join(rows) + "\r\n"
    (tmp_path / "20230301000000.csv").write_bytes(body.encode("latin-1"))
    train = list(R.iter_texts(tmp_path, "train"))
    assert [t for t, _ in train] == ["Next Delivery: May 2021; Estimated Recovery: TBD"]
    test = R.inventory(tmp_path, "test", 40)
    assert "top" not in test  # the test split is reported in aggregate only
    assert test["distinct_timing_texts"] == 1


def test_items_batch(tmp_path: Path) -> None:
    items = tmp_path / "items.jsonl"
    items.write_text(
        json.dumps(
            {
                "item_id": "x1",
                "date_of_update": "10/13/2020",
                "availability_information": "Available",
                "related_information": "Currently on backorder - next shipment anticipated Oct 20",
            }
        )
        + "\n"
    )
    out = tmp_path / "readings.jsonl"
    assert R.main(["--items", str(items), "--out", str(out)]) == 0
    row = json.loads(out.read_text())
    assert row["item_id"] == "x1"
    assert row["literal_v1"]["interval"] == {"start": "2020-10-01", "end": "2020-10-31"}
