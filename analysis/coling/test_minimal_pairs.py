"""Tests for the minimal-pair generator and the task C audit files (``minimal_pairs.py``).

Two kinds of input:

* **Made-up notices** (an events table written by hand): the worked examples of AUDIT_GUIDE.md
  section 7.3 (the seven ``ok`` rows reproduced, the two ``error`` rows impossible), the time
  conventions and the writings of a time against hand-written tables, the gold of every factor
  against a hand-written table, masks, sentences and phrases, the attested forms, the name
  replacement, the selection, the audit draw, the sheets, the validator, the scorer with its
  pass rule, and the commands end to end.
* **The real captures** (built in memory, events only; skipped when the capture folder is not
  there): determinism, one factor per edit, the gold against the frozen rule reader, no real
  name in any item, every attested form found in a train-period notice outside the labelling
  samples and Appendix A, the strata and caps of the audit sample, planted items that look
  like the others, and that the files under ``analysis/coling/out/e5`` are up to date.

No model is called, no outcome is read and nothing sealed is opened.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_minimal_pairs.py -q -p no:cacheprovider
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import forms as F
from analysis.coling import minimal_pairs as M
from analysis.coling import read
from analysis.coling import rules as R

CAPTURES = Path("external_data/fda_wayback_csv")
REAL_OUT = Path("analysis/coling/out/e5")

# --------------------------------------------------------------------------------------------
# Made-up notices
# --------------------------------------------------------------------------------------------

ATTESTING = (  # availability text, related text: train-period notices that attest forms
    ("Backordered. Next release expected December 2020.", ""),
    ("Unavailable. Next release date not available at this time.", ""),
    ("Backordered. Next release mid-June 2021.", ""),
    ("5 months dating available by request (expiry 6/30/2021). Next release August 2021.", ""),
    ("On backorder. Next release December.", ""),
    ("Allocating inventory. Product will be made available as it is released.", ""),
    ("Unavailable. Estimated recovery TBD.", ""),
    ("Backordered. Estimated availability Aug-2020", ""),
    ("On backorder", "Recovery expected Q3 2021"),
    ("Limited supply, recovery TBD", ""),
    ("Unavailable, recovery in early June 2020", ""),
    ("Remaining inventory estimated to last until April 2020. On backorder.", ""),
    ("Product expected to be available until May 2021. Next release June 2021.", ""),
    ("Additional lots will be available in the June 2021 timeframe.", ""),
    ("Resupply: March/April 2021", ""),
    ("Estimated recovery: 3 weeks", ""),
    ("Currently on backorder - next shipment anticipated end of Nov 20", ""),
    ("Currently on backorder - next shipment TBD", ""),
    ("Backordered. Estimated availability TBD", ""),
)
CEFOXITIN = {  # the seed of the guide's section 7.3
    "generic_name": "Cefoxitin for Injection, USP",
    "company_name": "Fresenius Kabi USA, LLC",
    "presentation": "1 g per vial; SDV; (NDC 63323-341-25)",
    "event_date": "2020-08-13",
    "availability_text": "Backordered. Next release October 2020.",
    "related_text": "Check wholesalers for inventory",
    "reason_for_shortage": "Manufacturing delays",
}


def event(n: int, availability: str, related: str = "", **more: str) -> dict[str, str]:
    """One made-up event with every field the module reads."""
    row = dict.fromkeys(S.EVENT_FIELDS, "")
    row |= {
        "event_id": f"E{n:04d}",
        "statement_group_id": f"S{n:04d}",
        "thread_id": f"T{n:04d}",
        "generic_id": f"G{n:04d}",
        "episode_id": f"P{n:04d}",
        "listing": "shortage",
        "event_date": "2020-06-01",
        "type_of_update": "revised",
        "generic_name": f"Madeupol{n} Injection",
        "company_name": f"Inventa{n} Pharma",
        "presentation": f"10 mg vial (NDC 1{n:04d}-123-45)",
        "status_at_statement": "current",
        "availability_class": "unavailable",
        "availability_text": availability,
        "related_text": related,
        "reason_for_shortage": "Demand increase for the drug",
        "therapeutic_category": "Anti-Infective",
        "initial_posting_date": "05/03/2019",
    }
    row |= more
    row["statement_text"] = C.statement_text(row["availability_text"], row["related_text"])
    return row


def made_up(*seeds: dict[str, str]) -> pd.DataFrame:
    """The attesting notices, then the seeds (events ``E0900`` on)."""
    rows = [event(n, a, r) for n, (a, r) in enumerate(ATTESTING, start=1)]
    rows += [event(900 + n, "", **seed) for n, seed in enumerate(seeds)]
    return pd.DataFrame(rows, columns=list(S.EVENT_FIELDS))


def seed_and_edits(
    *fields: dict[str, str],
) -> tuple[M.Seed, dict[tuple[str, str], M.Edit], list[M.Skip]]:
    """The seed made of the last of ``fields`` and its edits; the others are further notices."""
    events = made_up(*fields)
    row = events.iloc[-1].to_dict()
    lexicon = M.name_lexicon(events)
    inventory = M.build_inventory(events, {row["statement_group_id"]})
    seed, reason, _ = M.make_seed(row, "train", lexicon, set())
    assert seed is not None, reason
    made, skipped = M.edits_of(seed, inventory)
    return seed, {(e.factor, e.level): e for e in made}, skipped


def shown(gold: M.Gold) -> tuple[str, str, str, str, bool, tuple[str, ...]]:
    return (
        gold.statement_type,
        gold.start or gold.abstain_reason,
        gold.end,
        gold.certainty,
        gold.stale,
        gold.distractor_roles,
    )


# --------------------------------------------------------------------------------------------
# The worked examples of AUDIT_GUIDE.md section 7.3
# --------------------------------------------------------------------------------------------

OCTOBER = ("2020-10-01", "2020-10-31")
GUIDE_OK_ROWS = {  # (factor, level): changed fields, gold
    ("certainty", "expected"): (
        {"availability_information": "Backordered. Next release expected October 2020."},
        ("next_delivery", *OCTOBER, "estimated", False, ()),
    ),
    ("certainty", "tbd"): (
        {"availability_information": "Backordered. Next release date not available at this time."},
        ("next_delivery", "tbd", "", "undetermined", False, ()),
    ),
    ("stale", "stale"): (
        {"date_of_update": "2020-11-16", "type_of_update": "Reverified"},
        ("next_delivery", *OCTOBER, "asserted", True, ()),
    ),
    ("distractor", "expiry"): (
        {
            "availability_information": "4 months dating available by request (expiry "
            "12/31/2020). Backordered. Next release October 2020."
        },
        ("next_delivery", *OCTOBER, "asserted", False, ("expiry",)),
    ),
    ("surface_form", "no_year"): (
        {"availability_information": "Backordered. Next release October."},
        ("next_delivery", *OCTOBER, "asserted", False, ()),
    ),
    ("silent", "silent"): (
        {"availability_information": "Backordered."},
        ("none", "no_statement", "", "no_statement", False, ()),
    ),
    ("certainty", "as_released"): (
        {
            "availability_information": "Backordered. Product will be made available as it is "
            "released."
        },
        ("next_delivery", "no_date", "", "undetermined", False, ()),
    ),
}


def test_guide_examples_ok_rows_are_reproduced() -> None:
    seed, edits, _ = seed_and_edits(CEFOXITIN)
    assert shown(seed.gold) == ("next_delivery", *OCTOBER, "asserted", False, ())
    for key, (changed, gold) in GUIDE_OK_ROWS.items():
        edit = edits[key]
        assert {k: v for k, v in edit.fields.items() if v != seed.fields[k]} == changed, key
        assert shown(edit.gold) == gold, key
        if key[0] not in ("stale", "silent"):
            assert edit.attested is not None and edit.attested.text in dict(ATTESTING), key


def test_guide_examples_are_those_the_guide_prints() -> None:
    """The rows above are the guide's: its section 7.3 still quotes every edited entry."""
    section = S.guide_section(M.GUIDE.read_text(encoding="utf-8"), "7")
    text = " ".join(section.split())
    assert '"Backordered. Next release October 2020."' in text
    for changed, _ in GUIDE_OK_ROWS.values():
        entry = changed.get("availability_information")
        assert entry is None or f'"{entry}"' in text, entry
    assert "Type of update Reverified, dated 2020-11-16" in text
    assert "2020-10-11 to 2020-10-20" in text


def test_guide_error_row_mid_gets_the_part_of_the_month() -> None:
    seed, edits, _ = seed_and_edits(CEFOXITIN)
    edit = edits["granularity", "mid"]
    assert edit.fields["availability_information"] == "Backordered. Next release mid-October 2020."
    assert (edit.gold.start, edit.gold.end) == ("2020-10-11", "2020-10-20")
    assert (edit.gold.start, edit.gold.end) != (seed.gold.start, seed.gold.end)
    assert shown(edit.gold)[3:] == ("asserted", False, ())


def test_guide_error_row_whole_statement_swapped_cannot_be_made() -> None:
    """ "Unavailable. Estimated recovery TBD." is attested, and still no edit: every edit but
    the silent one keeps the type, and every edit of the text keeps the status wording."""
    seed, edits, _ = seed_and_edits(CEFOXITIN)
    assert any(a == "Unavailable. Estimated recovery TBD." for a, _ in ATTESTING)
    for (factor, level), edit in edits.items():
        text = edit.fields["availability_information"]
        assert text != "Unavailable. Estimated recovery TBD."
        assert "Backordered." in text, (factor, level)
        assert "Unavailable" not in text and "recovery" not in text.lower()
        if factor != "silent":
            assert edit.gold.statement_type == seed.gold.statement_type == "next_delivery"


def test_guide_examples_agree_with_the_frozen_rule_reader() -> None:
    _, edits, _ = seed_and_edits(CEFOXITIN)
    for key, edit in edits.items():
        rule = M.rule_gold(M.item_text(edit.fields), M.item_anchor(edit.fields))
        assert rule.compared() == edit.gold.compared(), key


# --------------------------------------------------------------------------------------------
# Time conventions and writings, against hand-written tables
# --------------------------------------------------------------------------------------------

ANCHOR = date(2020, 8, 13)
SPANS = (  # a time, and its first and last day (AUDIT_GUIDE.md, C2 to C13)
    (M.Time("month", 2020, 10), "2020-10-01", "2020-10-31"),
    (M.Time("month", 2020, 2), "2020-02-01", "2020-02-29"),
    (M.Time("part_of_month", 2020, 10, part="early"), "2020-10-01", "2020-10-10"),
    (M.Time("part_of_month", 2020, 10, part="mid"), "2020-10-11", "2020-10-20"),
    (M.Time("part_of_month", 2020, 10, part="late"), "2020-10-21", "2020-10-31"),
    (M.Time("part_of_month", 2021, 2, part="late"), "2021-02-21", "2021-02-28"),
    (M.Time("quarter", 2020, quarter=4), "2020-10-01", "2020-12-31"),
    (M.Time("quarter_part", 2021, quarter=3, part="early"), "2021-07-01", "2021-07-31"),
    (M.Time("quarter_part", 2021, quarter=3, part="mid"), "2021-08-01", "2021-08-31"),
    (M.Time("quarter_part", 2021, quarter=3, part="late"), "2021-09-01", "2021-09-30"),
    (M.Time("year_part", 2020, part="early"), "2020-01-01", "2020-04-30"),
    (M.Time("year_part", 2020, part="mid"), "2020-05-01", "2020-08-31"),
    (M.Time("year_part", 2020, part="late"), "2020-09-01", "2020-12-31"),
    (M.Time("month_range", 2021, 3, last_month=4), "2021-03-01", "2021-04-30"),
    (M.Time("day", 2020, 7, day=1), "2020-07-01", "2020-07-01"),
    (M.Time("relative", low=21, high=21), "2020-09-03", "2020-09-03"),
    (M.Time("relative", low=90, high=540), "2020-11-11", "2022-02-04"),
)


@pytest.mark.parametrize(("time", "start", "end"), SPANS)
def test_time_span_follows_the_conventions(time: M.Time, start: str, end: str) -> None:
    low, high = M.time_span(time, ANCHOR)
    assert (low.isoformat(), high.isoformat()) == (start, end)


WRITINGS = (  # text, time, reads as that time on 2020-08-13
    ("October 2020", M.Time("month", 2020, 10), True),
    ("Oct 2020", M.Time("month", 2020, 10), True),
    ("Oct-20", M.Time("month", 2020, 10), True),
    ("10/2020", M.Time("month", 2020, 10), True),
    ("October", M.Time("month", 2020, 10), True),
    ("October", M.Time("month", 2021, 10), False),  # C8: the first October ending after the date
    ("July", M.Time("month", 2020, 7), False),  # July 2020 has ended: "July" is July 2021
    ("July", M.Time("month", 2021, 7), True),
    ("Mar 21", M.Time("month", 2021, 3), True),  # C8: 2021 lies in the window, so a year
    ("Mar 25", M.Time("month", 2025, 3), False),  # 2025 does not: "Mar 25" is a day
    ("mid-October 2020", M.Time("part_of_month", 2020, 10, part="mid"), True),
    ("end of Oct 20", M.Time("part_of_month", 2020, 10, part="late"), True),
    ("mid August", M.Time("part_of_month", 2020, 8, part="mid"), True),  # the year of its month
    ("Q4 2020", M.Time("quarter", 2020, quarter=4), True),
    ("4Q20", M.Time("quarter", 2020, quarter=4), True),
    ("Q2", M.Time("quarter", 2020, quarter=2), False),
    ("Q2", M.Time("quarter", 2021, quarter=2), True),
    ("early Q4 2020", M.Time("quarter_part", 2020, quarter=4, part="early"), True),
    ("late 2020", M.Time("year_part", 2020, part="late"), True),
    ("March/April 2021", M.Time("month_range", 2021, 3, last_month=4), True),
    ("March/April", M.Time("month_range", 2021, 3, last_month=4), False),  # no rule for it
    ("7/1/2021", M.Time("day", 2021, 7, day=1), True),
    ("October 5", M.Time("day", 2020, 10, day=5), True),
    ("October 21", M.Time("day", 2020, 10, day=21), False),  # C8: "October 21" is October 2021
    ("3 weeks", M.Time("relative", low=21, high=21), True),
    ("21 days", M.Time("relative", low=21, high=21), True),
    ("3-18 months", M.Time("relative", low=90, high=540), True),
)


@pytest.mark.parametrize(("text", "time", "reads"), WRITINGS)
def test_writings_and_their_reading(text: str, time: M.Time, reads: bool) -> None:
    form = next((f for f in M.forms(time) if f.text == text), None)
    assert form is not None, f"{text!r} is not a writing of {time}"
    assert M.reads_as(form, ANCHOR) is reads
    assert M.detect(time, text) == form


def test_every_offered_writing_is_read_by_the_rule_reader_as_its_time() -> None:
    """The writers against the frozen reader: a writing that reads as its time on a date is
    read as that period by ``rules.py`` too, behind a plain recovery cue."""
    times = [t for t, _, _ in SPANS if t.kind != "relative"]
    times += [M.Time("month", 2021, 5), M.Time("quarter", 2021, quarter=1)]
    differ = []
    for time in times:
        for form in M.forms(time):
            if not form.offered or not M.reads_as(form, ANCHOR):
                continue
            low, high = M.time_span(time, ANCHOR)
            rule = M.rule_gold(f"Estimated recovery: {form.text}", ANCHOR)
            if (rule.start, rule.end) != (low.isoformat(), high.isoformat()):
                differ.append((form.text, rule.start, rule.end))
    assert not differ, differ


def test_surface_level_names_the_one_attribute_that_changes() -> None:
    month = M.Time("month", 2020, 10)
    seed = M.detect(month, "October 2020")
    assert seed is not None
    levels = {f.text: M.surface_level(seed, f) for f in M.forms(month)}
    assert levels["October"] == "no_year"
    assert levels["Oct 2020"] == "abbreviated_month"
    assert levels["10/2020"] == "numeric"
    assert levels["October-2020"] == "hyphenated"
    assert levels["October 2020"] is None  # nothing changes
    assert levels["Oct-20"] is None  # three attributes change
    short = M.detect(month, "Oct. 20")
    assert short is not None
    assert M.surface_level(short, M.detect(month, "Oct 2020")) == "four_digit_year"
    assert M.surface_level(M.detect(month, "October"), seed) == "with_year"
    part = M.Time("part_of_month", 2020, 10, part="late")
    assert M.surface_level(M.detect(part, "end of Oct 20"), M.detect(part, "late Oct 20")) == (
        "part_word"
    )
    span = M.Time("month_range", 2021, 3, last_month=4)
    assert M.surface_level(
        M.detect(span, "March/April 2021"), M.detect(span, "March - April 2021")
    ) == ("separator")
    assert (
        M.surface_level(M.detect(span, "March/April 2021"), M.detect(span, "March/April")) is None
    )
    weeks = M.Time("relative", low=21, high=21)
    assert M.surface_level(M.detect(weeks, "3 weeks"), M.detect(weeks, "21 days")) == "unit"
    assert M.surface_level(M.detect(weeks, "three weeks"), M.detect(weeks, "3 weeks")) == "digits"


def test_every_level_a_surface_edit_can_take_is_listed() -> None:
    found = set()
    for time, _, _ in SPANS:
        writings = M.forms(time)
        found |= {M.surface_level(a, b) for a in writings for b in writings if b.offered}
    assert found - {None} <= set(M.LEVELS["surface_form"])


SEED_TIMES = (  # text, date, the time of the target (None: not rewritten)
    ("Next release October 2020.", "2020-08-13", M.Time("month", 2020, 10)),
    ("Next release December.", "2019-11-04", M.Time("month", 2019, 12)),
    ("Recovery mid July 2020", "2020-07-06", M.Time("part_of_month", 2020, 7, part="mid")),
    ("Estimated recovery 1Q2023", "2022-08-01", M.Time("quarter", 2023, quarter=1)),
    (
        "Estimated recovery: Late Q3 2023",
        "2022-09-21",
        M.Time("quarter_part", 2023, quarter=3, part="late"),
    ),
    ("Estimated recovery: Late 2020", "2019-10-11", M.Time("year_part", 2020, part="late")),
    ("Relaunch Mar-Apr 2022", "2021-11-08", M.Time("month_range", 2022, 3, last_month=4)),
    ("Expected release - 12/11/2020", "2020-12-08", M.Time("day", 2020, 12, day=11)),
    ("Estimated recovery: 2 weeks", "2020-01-24", M.Time("relative", low=14, high=14)),
    ("Inventory will be available by end of Q1 2021", "2021-01-07", None),  # "by"
    ("Resupply end of Sep/early Oct 2020", "2020-09-04", None),  # a range with parts
    ("Estimated recovery: first half of June 2021", "2021-05-01", None),
)


@pytest.mark.parametrize(("text", "day", "time"), SEED_TIMES)
def test_seed_time_from_the_rule_reading(text: str, day: str, time: M.Time | None) -> None:
    assert M.seed_time(F.classify(text, day), date.fromisoformat(day)) == time


# --------------------------------------------------------------------------------------------
# Text: masks, sentences, phrases, the fields as the rule reader sees them
# --------------------------------------------------------------------------------------------


def test_mask_keeps_four_kinds_of_month_and_number_apart() -> None:
    assert M.mask("Next release October 2020.") == "next release <month> <yyyy>"
    assert M.mask("Next release Oct. 2020") == "next release <mon> <yyyy>"
    assert M.mask("next shipment anticipated Jan 21") == "next shipment anticipated <mon> <n>"
    assert M.mask("Estimated recovery 3Q2020") == "estimated recovery <n>q<yyyy>"
    assert M.mask("Availability Q12020") == "availability q<n><yyyy>"  # a quarter and a year,
    assert M.mask("Availability Q12020") != M.mask("Availability Q4")  # not a quarter alone
    assert M.mask("lot 12020") == "lot <n>"
    assert M.mask("Approximately four months") == "approximately <number> months"
    assert M.mask("On backorder – resupply TBD;") == "on backorder - resupply tbd"
    assert M.mask("May 2020") == "<month> <yyyy>"  # May has no abbreviation
    assert M.mask("Limited supply, June") != M.mask("Limited supply, Jun")


def test_sentences_and_phrases() -> None:
    text = "Backordered. Next release Dec. 2020; Estimated recovery: Q1, 2021. est. 5 units"
    assert [text[a:b] for a, b in M.sentences(text)] == [
        "Backordered.",
        "Next release Dec. 2020;",
        "Estimated recovery: Q1, 2021. est. 5 units",
    ]
    one = "Currently on backorder - next shipment anticipated May - June 2021, on allocation"
    assert [one[a:b] for a, b in M.phrases(one, 0, len(one))] == [
        "Currently on backorder",
        "next shipment anticipated May - June 2021",
        "on allocation",
    ]
    listed = "Limited inventory in June, July and August 2021 / Recovery TBD"
    assert [listed[a:b] for a, b in M.phrases(listed, 0, len(listed))] == [
        "Limited inventory in June, July and August 2021",
        "Recovery TBD",
    ]


def test_statement_pieces_locate_a_span_in_the_raw_field() -> None:
    availability = "On backorder –  increase demand; resupply date end of November 2020"
    related = "Check wholesalers"
    pieces = M.statement_pieces(availability, related)
    joined = R.normalise(C.statement_text(availability, related))
    start = joined.index("end of November 2020")
    name, low, high = M.locate(pieces, start, start + len("end of November 2020"))
    assert (name, availability[low:high]) == ("availability_information", "end of November 2020")
    start = joined.index("Check")
    assert M.locate(pieces, start, start + 5) == ("related_information", 0, 5)
    assert M.locate(pieces, start - 6, start + 5) is None  # across the two fields
    bare = M.statement_pieces("On backorder", "Recovery Dec 2021")
    assert [p.name for p in bare] == ["related_information"]


# --------------------------------------------------------------------------------------------
# Attested forms
# --------------------------------------------------------------------------------------------


def test_inventory_holds_sentences_phrases_and_times_of_train_notices_only() -> None:
    late = {"availability_text": "Backordered. Next release in the fourth quarter of 2024."}
    events = made_up({**late, "event_date": "2023-01-01"})
    inventory = M.build_inventory(events, {"S0001"})
    assert inventory.statements == len(ATTESTING) - 1
    assert "next release mid-<month> <yyyy>" in inventory.sentences
    assert "next release expected <month> <yyyy>" not in inventory.sentences  # S0001 is excluded
    assert "next release in the <number> quarter of <yyyy>" not in inventory.sentences  # 2023
    assert "recovery tbd" in inventory.phrases and "recovery tbd" not in inventory.sentences
    assert {"mid-<month> <yyyy>", "<mon>-<yyyy>", "q<n> <yyyy>", "<n> weeks"} <= set(
        inventory.forms
    )
    assert "the <month> <yyyy> timeframe" in inventory.forms
    hit = inventory.find("Unavailable. Next release mid-May 2022.", 15)
    assert hit is not None and (hit.scope, hit.event_id) == ("sentence", "E0003")
    hit = inventory.find("Low stock, recovery TBD", 12)
    assert hit is not None and hit.scope == "phrase"
    assert inventory.find("Unavailable. Next release late May 2022.", 15) is None


TIMES_ALONE = (  # a notice, its date, and the time expressions it attests on their own
    ("Next release October 2020.", "2020-06-01", {"<month> <yyyy>"}),
    ("Next release October.", "2020-06-01", {"<month>"}),
    ("Next release mid-October 2020.", "2020-06-01", {"mid-<month> <yyyy>"}),
    ("Next release June 15, 2021.", "2020-06-01", {"<month> <n>, <yyyy>"}),
    # "June" is part of a list and takes its year from the next item
    ("Next shipments June and July 2021.", "2020-06-01", {"<month> <yyyy>"}),
    ("Next shipments anticipated Aug. and Sept. 2020", "2020-06-01", {"<mon> <yyyy>"}),
    ("Next Delivery: May 2021, July 2021.", "2020-06-01", {"<month> <yyyy>"}),
    ("Next release June 5-9, 2021.", "2020-06-01", set()),  # a range of days: no known writing
    ("Resupply end of Sep/early Oct 2020", "2020-09-04", set()),  # a range with parts
    (
        "Additional lots are scheduled for release in the March/April 2021 timeframe.",
        "2020-06-01",
        {"the <month>/<month> <yyyy> timeframe"},
    ),
    ("Resupply by the end of March 2021", "2020-06-01", {"end of <month> <yyyy>"}),
    ("Recovery Q4 2020; next delivery 4Q20", "2020-06-01", {"q<n> <yyyy>", "<n>q<n>"}),
    ("Availability Q12021", "2020-06-01", {"q<n><yyyy>"}),  # not the writing of "Q4"
    ("Stocked Out, Recovery Q4", "2020-06-01", {"q<n>"}),
    # C8: a year inside the window, a day outside it
    ("Next shipment anticipated Jun 21", "2020-05-04", {"<mon> <n>"}),
    ("Next shipment anticipated Jun 15", "2020-05-04", set()),
    # a writing used for another date than a delivery or a recovery attests nothing
    ("9 month dating available by request. Next release date not available.", "2020-06-01", set()),
    (
        "5 month expiry (4/2022 expiry) dating available by request. Next release TBD.",
        "2021-11-04",
        set(),
    ),
    (
        "5 month expiry (4/2022 expiry) dating available by request. Next release 6/2022.",
        "2021-11-04",
        {"<n>/<yyyy>"},
    ),
    ("Product is available with an expected supply duration until AUG' 2022.", "2022-03-01", set()),
    ("Product not on allocation effective Dec 1, 2019", "2019-12-10", set()),
    ("Discontinued: May 30, 2019", "2019-03-01", set()),
    ("Approximately 2 months of inventory on hand", "2020-06-01", set()),
    ("Estimated shortage duration: 90 days.", "2020-06-01", {"<n> days"}),
)


@pytest.mark.parametrize(("text", "day", "wanted"), TIMES_ALONE)
def test_a_time_is_attested_alone_as_the_time_of_a_delivery_or_recovery(
    text: str, day: str, wanted: set[str]
) -> None:
    times = M.stated_times(text, "", date.fromisoformat(day))
    assert {form for form, _ in times} == wanted
    assert all(field == text for _, field in times)
    inventory = M.Inventory()
    inventory.add(text, "E1")
    assert not inventory.forms  # the fields give sentences and phrases; the times come apart
    inventory.add_times(times, "E1")
    inventory.add_times(times, "E2")
    assert {form: hit[0] for form, hit in inventory.forms.items()} == dict.fromkeys(wanted, 2)


def test_a_time_in_the_related_information_is_found_in_its_field() -> None:
    related = "Recovery expected Q3 2021. Additional lots in the June timeframe."
    times = M.stated_times("On backorder", related, date(2021, 5, 20))
    assert times == [("q<n> <yyyy>", related), ("the <month> timeframe", related)]
    both = M.stated_times("Next release Oct. 2021", "Recovery October 2021", date(2021, 5, 20))
    assert both == [
        ("<mon> <yyyy>", "Next release Oct. 2021"),
        ("<month> <yyyy>", "Recovery October 2021"),
    ]
    inventory = M.Inventory()
    twice = [("<month>", "On backorder. Next release in June"), ("<month>", "Recovery June")]
    inventory.add_times(twice, "E1")  # one statement, the writing in both fields: counted once
    assert inventory.forms == {"<month>": (1, "Recovery June", "E1")}
    assert inventory.find_form("October") == M.Attested("Recovery June", "E1", "form", 1)
    assert inventory.find_form("Oct") is None


# --------------------------------------------------------------------------------------------
# Gold by construction, against a hand-written table for each factor
# --------------------------------------------------------------------------------------------

RECOVERY = {
    "event_date": "2020-03-10",
    "availability_text": "Unavailable, recovery in May 2020",
    "related_text": "Check wholesalers",
}
TABLE = (  # seed fields, (factor, level), changed fields, gold
    (
        RECOVERY,
        ("certainty", "tbd"),
        {"availability_information": "Unavailable, recovery TBD"},
        ("recovery", "tbd", "", "undetermined", False, ()),
    ),
    (
        RECOVERY,
        ("granularity", "early"),
        {"availability_information": "Unavailable, recovery in early May 2020"},
        ("recovery", "2020-05-01", "2020-05-10", "asserted", False, ()),
    ),
    (
        RECOVERY,
        ("granularity", "mid"),
        {"availability_information": "Unavailable, recovery in mid-May 2020"},
        ("recovery", "2020-05-11", "2020-05-20", "asserted", False, ()),
    ),
    (
        RECOVERY,
        ("granularity", "quarter"),
        {"availability_information": "Unavailable, recovery in Q2 2020"},
        ("recovery", "2020-04-01", "2020-06-30", "asserted", False, ()),
    ),
    (
        {"event_date": "2020-01-10", "availability_text": "Unavailable, recovery in March 2020"},
        ("granularity", "quarter"),
        {"availability_information": "Unavailable, recovery in Q1 2020"},
        ("recovery", "2020-01-01", "2020-03-31", "asserted", False, ()),
    ),
    (
        RECOVERY,
        ("granularity", "range"),
        {"availability_information": "Unavailable, recovery in May/June 2020"},
        ("recovery", "2020-05-01", "2020-06-30", "asserted", False, ()),
    ),
    (
        RECOVERY,
        ("granularity", "timeframe"),
        {"availability_information": "Unavailable, recovery in the May 2020 timeframe"},
        ("recovery", "2020-05-01", "2020-05-31", "asserted", False, ()),
    ),
    (
        {"event_date": "2020-03-10", "availability_text": "Unavailable, recovery in Sep 2020"},
        ("surface_form", "hyphenated"),
        {"availability_information": "Unavailable, recovery in Sep-2020"},
        ("recovery", "2020-09-01", "2020-09-30", "asserted", False, ()),
    ),
    (
        RECOVERY,
        ("stale", "stale"),
        {"date_of_update": "2020-06-16", "type_of_update": "Reverified"},
        ("recovery", "2020-05-01", "2020-05-31", "asserted", True, ()),
    ),
    (
        RECOVERY,
        ("distractor", "depletion"),
        {
            "availability_information": "Remaining inventory estimated to last until April "
            "2020. Unavailable, recovery in May 2020"
        },
        ("recovery", "2020-05-01", "2020-05-31", "asserted", False, ("depletion",)),
    ),
    (
        RECOVERY,
        ("distractor", "available_until"),
        {
            "availability_information": "Product expected to be available until April 2020. "
            "Unavailable, recovery in May 2020"
        },
        ("recovery", "2020-05-01", "2020-05-31", "asserted", False, ("depletion",)),
    ),
    (
        RECOVERY,
        ("silent", "silent"),
        {"availability_information": "Unavailable"},
        ("none", "no_statement", "", "no_statement", False, ()),
    ),
    (
        {
            "event_date": "2020-11-06",
            "availability_text": "Backordered. Estimated availability Nov-2020",
        },
        ("certainty", "tbd"),
        {"availability_information": "Backordered. Estimated availability TBD"},
        ("recovery", "tbd", "", "undetermined", False, ()),
    ),
    (
        {
            "event_date": "2020-11-02",
            "availability_text": "Currently on backorder - next shipment anticipated mid Nov 20",
        },
        ("certainty", "tbd"),
        {"availability_information": "Currently on backorder - next shipment TBD"},
        ("next_delivery", "tbd", "", "undetermined", False, ()),
    ),
    (
        {
            "event_date": "2020-11-02",
            "availability_text": "Currently on backorder - next shipment anticipated mid Nov 20",
        },
        ("granularity", "late"),
        {
            "availability_information": "Currently on backorder - next shipment anticipated end of Nov 20"
        },
        ("next_delivery", "2020-11-21", "2020-11-30", "estimated", False, ()),
    ),
    (
        {
            "event_date": "2021-05-20",
            "availability_text": "On backorder",
            "related_text": "Recovery Q3 2021",
        },
        ("certainty", "expected"),
        {"related_information": "Recovery expected Q3 2021"},
        ("recovery", "2021-07-01", "2021-09-30", "estimated", False, ()),
    ),
    (
        {
            "event_date": "2021-05-20",
            "availability_text": "On backorder",
            "related_text": "Recovery Q3 2021",
        },
        ("distractor", "available_until"),
        {
            "availability_information": "Product expected to be available until June 2021. On backorder"
        },
        ("recovery", "2021-07-01", "2021-09-30", "asserted", False, ("depletion",)),
    ),
    (
        {
            "event_date": "2023-02-01",
            "availability_text": "Unavailable",
            "related_text": "Estimated recovery: 21 days",
        },
        ("surface_form", "unit"),
        {"related_information": "Estimated recovery: 3 weeks"},
        ("recovery", "2023-02-22", "2023-02-22", "estimated", False, ()),
    ),
)


@pytest.mark.parametrize(("seed_fields", "key", "changed", "gold"), TABLE)
def test_gold_by_construction(
    seed_fields: dict[str, str],
    key: tuple[str, str],
    changed: dict[str, str],
    gold: tuple[Any, ...],
) -> None:
    seed, edits, skipped = seed_and_edits(seed_fields)
    assert key in edits, [s for s in skipped if s.factor == key[0]]
    edit = edits[key]
    assert {k: v for k, v in edit.fields.items() if v != seed.fields[k]} == changed
    assert shown(edit.gold) == gold
    rule = M.rule_gold(M.item_text(edit.fields), M.item_anchor(edit.fields))
    assert rule.compared() == edit.gold.compared()  # the frozen reader agrees on these


def reasons(skipped: list[M.Skip], factor: str, level: str = "") -> list[str]:
    return [s.reason for s in skipped if s.factor == factor and level in ("", s.level)]


def test_what_cannot_be_applied_is_skipped_with_its_reason() -> None:
    _, edits, skipped = seed_and_edits(
        {
            "event_date": "2020-12-08",
            "availability_text": "On backorder. Expected release - 12/11/2020",
        }
    )
    assert not any(f == "granularity" for f, _ in edits)  # an exact day has no other grain
    assert "no finer or coarser grain" in reasons(skipped, "granularity")[0]
    _, edits, skipped = seed_and_edits(
        {"event_date": "2019-11-04", "availability_text": "On backorder. Next release December."}
    )
    assert ("stale", "stale") not in edits  # the year comes from the Date of update
    assert "read from the Date of update" in reasons(skipped, "stale")[0]
    _, edits, skipped = seed_and_edits(
        {
            "event_date": "2023-02-01",
            "availability_text": "Unavailable",
            "related_text": "Estimated recovery: 3 weeks",
        }
    )
    assert ("stale", "stale") not in edits and "counted from" in reasons(skipped, "stale")[0]
    _, edits, skipped = seed_and_edits(
        {
            "event_date": "2021-01-07",
            "availability_text": "Inventory will be available by end of Q1 2021",
        }
    )
    assert not {f for f, _ in edits} & {"stale", "surface_form", "granularity"}
    assert '"by"' in reasons(skipped, "stale")[0]
    _, edits, skipped = seed_and_edits(
        {
            "event_date": "2020-10-23",
            "availability_text": "9 mos expiry available. Next release December 2020.",
        }
    )
    assert not any(f == "distractor" for f, _ in edits)
    assert "capital letter" in reasons(skipped, "distractor")[0]
    _, edits, skipped = seed_and_edits(
        {"event_date": "2020-03-10", "availability_text": "Recovery May 2020"}
    )
    assert ("silent", "silent") not in edits and "nothing would be left" in reasons(
        skipped, "silent"
    )[0]


def test_a_sentence_is_replaced_only_when_it_says_nothing_else() -> None:
    """The second error row of section 7.3: the status wording must stay. "Next release ..." in
    a sentence of its own can give way to "Product will be made available as it is released";
    a delivery stated with a word on the state of supply, or in a phrase of a longer sentence,
    cannot."""
    _, edits, _ = seed_and_edits(CEFOXITIN)
    assert ("certainty", "as_released") in edits
    for text in (
        "Partial shipments on allocation October 2020",
        "Backordered, next release October 2020.",
    ):
        seed, edits, skipped = seed_and_edits(
            {
                "event_date": "2020-08-13",
                "availability_text": "No current supply",
                "related_text": text,
            }
        )
        assert seed.gold.statement_type == "next_delivery" and len(seed.mentions) == 1
        assert ("certainty", "as_released") not in edits, text
        assert "in a sentence of its own" in reasons(skipped, "certainty", "as_released")[0]


def test_an_unknown_marker_needs_a_target_that_is_alone_in_its_type() -> None:
    """With a second recovery statement the choice of the target could move (section 3.6), so
    no unknown marker is put in; with a next delivery beside the recovery it can be."""
    two = {
        "event_date": "2020-09-16",
        "availability_text": "On backorder, shortage until November 2020.",
        "related_text": "Estimated recovery Q4 2020",
    }
    seed, edits, skipped = seed_and_edits(two)
    assert sum(m.statement_type == "recovery" for m in seed.mentions) == 2
    assert not {("certainty", "tbd"), ("certainty", "as_released")} & set(edits)
    assert "another statement of the target's type" in reasons(skipped, "certainty", "tbd")[0]
    assert shown(edits["silent", "silent"].gold)[0] == "none"
    assert edits["silent", "silent"].fields["related_information"] == ""
    assert edits["silent", "silent"].fields["availability_information"] == "On backorder."
    both = {
        "event_date": "2020-09-16",
        "availability_text": "Next Delivery: October 2020; Estimated Recovery: Nov-2020",
    }
    seed, edits, _ = seed_and_edits(both)
    assert [m.statement_type for m in seed.mentions] == ["next_delivery", "recovery"]
    assert ("certainty", "as_released") not in edits  # the target is a recovery


def test_a_seed_read_only_as_a_bare_date_gets_no_added_words() -> None:
    seed, edits, skipped = seed_and_edits(
        {"event_date": "2021-08-25", "availability_text": "Stocked Out, December 2021"}
    )
    assert seed.bare and seed.gold.statement_type == "recovery"
    assert not {f for f, _ in edits} & set(M.ADD_WORDS)
    assert all("no cue" in r for f in M.ADD_WORDS for r in reasons(skipped, f))
    assert ("stale", "stale") in edits


def test_no_edit_but_stale_makes_an_item_stale() -> None:
    """A part of the month that has passed is not offered: "early" on the 15th is skipped."""
    _, edits, _ = seed_and_edits(
        {"event_date": "2020-05-15", "availability_text": "Unavailable, recovery in May 2020"}
    )
    assert ("granularity", "early") not in edits and ("granularity", "mid") in edits
    for (factor, _), edit in edits.items():
        assert edit.gold.stale is (factor == "stale")
        if edit.gold.end:
            assert (edit.gold.end < edit.fields["date_of_update"]) is (factor == "stale")


def test_a_day_without_a_year_is_not_attested_by_a_month_and_a_two_digit_year() -> None:
    """ "June 15" and "May 21" have one mask, and a notice writes "May 21" for May 2021: that
    attests no day. The day without its year is offered, and not made."""
    month_and_year = {
        "event_date": "2020-06-01",
        "availability_text": "Currently on backorder - next shipment anticipated May 21",
    }
    day = {
        "event_date": "2020-03-31",
        "availability_text": "Unavailable. Expecting new shipment June 15, 2020",
    }
    events = made_up(month_and_year, day)
    inventory = M.build_inventory(events, {"S0901"})
    assert inventory.find_form("June 15") is not None  # the mask alone would let it through
    seed, edits, skipped = seed_and_edits(month_and_year, day)
    assert seed.time == M.Time("day", 2020, 6, day=15)
    no_year = next(f for f in M.forms(seed.time) if f.text == "June 15")
    assert no_year.offered and M.reads_as(no_year, seed.anchor)
    assert ("surface_form", "no_year") not in edits
    assert reasons(skipped, "surface_form", "no_year") == ["no notice attests the wording"]


def test_a_distractor_sentence_needs_a_notice_with_that_sentence() -> None:
    """A notice that has the wording only as a part of a longer sentence does not attest the
    sentence that a distractor edit puts in."""
    part = {
        "event_date": "2020-01-10",
        "availability_text": "Low stock, Remaining inventory estimated to last until April 2020",
    }
    events = made_up(part, RECOVERY)
    lexicon = M.name_lexicon(events)
    seed, _, _ = M.make_seed(events.iloc[-1].to_dict(), "train", lexicon, set())
    assert seed is not None
    whole = M.build_inventory(events, {"S0901"})
    assert ("distractor", "depletion") in {(e.factor, e.level) for e in M.edits_of(seed, whole)[0]}
    partly = M.build_inventory(events, {"S0901", "S0012"})  # without the notice of ATTESTING
    wording = "remaining inventory estimated to last until <month> <yyyy>"
    assert wording in partly.phrases and wording not in partly.sentences
    made, skipped = M.edits_of(seed, partly)
    assert ("distractor", "depletion") not in {(e.factor, e.level) for e in made}
    assert reasons(skipped, "distractor", "depletion") == [
        "no notice attests a sentence of this role"
    ]


def test_a_seed_that_is_stale_undated_or_carries_a_distractor_is_refused() -> None:
    cases = {
        "the seed is stale at issue": {
            "event_date": "2020-06-02",
            "availability_text": "Unavailable, recovery in May 2020",
        },
        "no dated delivery or recovery target": {
            "event_date": "2020-06-02",
            "availability_text": "Unavailable. Estimated recovery TBD.",
        },
        "carries a distractor date": {
            "event_date": "2020-06-02",
            "availability_text": "5 month expiry (1/2021 expiry) dating available by request. Next release July 2020.",
        },
    }
    for reason, fields in cases.items():
        events = made_up(fields)
        seed, why, _ = M.make_seed(
            events.iloc[-1].to_dict(), "train", M.name_lexicon(events), set()
        )
        assert seed is None and reason in why


# --------------------------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------------------------

NAMED = {
    "generic_name": "Iomeprol injection",
    "company_name": "Bracco",
    "presentation": "Iomeprol injection (IOMERON) 350, 6 X 500 ML (NDC 0270-9350-06)",
    "event_date": "2022-09-09",
    "availability_text": "Estimated Availability: October 4, 2022",
    "related_text": (
        "Bracco has initiated importation of Iomeron® (iomeprol injection). Contact Bracco "
        "Customer Service at 1-877-272-2269 or Bracco.otc@diag.bracco.com, see "
        "https://imaging.bracco.com/us-en/iomeron. Labeled for Blue Point Laboratories "
        "(NDC 0270-9350-06)."
    ),
}


def test_names_are_replaced_in_every_field() -> None:
    events = made_up(NAMED)
    lexicon = M.name_lexicon(events)
    row = events.iloc[-1].to_dict()
    item, renamer = M.renamed_fields(row, row["statement_group_id"], lexicon, set())
    assert not M.real_name_hits(item, lexicon)
    whole = " ".join(item.values()).lower()
    for real in ("iomeprol", "bracco", "iomeron", "blue point", "0270-9350-06", "877-272-2269"):
        assert real not in whole, real
    drug, company = renamer.drug, renamer.company
    assert item["generic_name"] == f"{drug} Injection" and item["company_name"].startswith(company)
    assert (
        item["presentation"] == "injection 350, 6 X 500 ML (NDC 0000-" + item["presentation"][-8:]
    )
    related = item["related_information"]
    assert related.startswith(f"{company} has initiated importation of ")
    assert f"({drug.lower()} injection)" in related and "®" in related
    assert (
        f"info@{company.lower()}.example" in related and f"www.{company.lower()}.example" in related
    )
    assert "1-800-555-01" in related and "Laboratories" in related
    assert item["availability_information"] == NAMED["availability_text"]  # no name, no change
    assert M.real_name_hits({**item, "related_information": "ask Bracco"}, lexicon)
    assert M.real_name_hits({**item, "presentation": "Iomeron 350"}, lexicon)


def test_build_stops_when_a_name_of_the_corpus_is_left_in_an_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the replacement in the text fields failed, nothing would be written."""
    events = made_up(NAMED)
    sources = sources_of(events, listed(events, ["S0900"]))
    assert M.build(sources).seeds_used == 1
    monkeypatch.setattr(M.Renamer, "text", lambda self, field_name, text: text)
    with pytest.raises(ValueError, match="holds a real name"):
        M.build(sources)


def test_fictitious_names_are_fixed_seeded_and_free_of_the_corpus() -> None:
    drugs, companies = M.fictitious_names("drug"), M.fictitious_names("company")
    assert (len(drugs), len(set(drugs)), len(companies), len(set(companies))) == (
        2400,
        2400,
        240,
        240,
    )
    digest = hashlib.sha256("\n".join((*drugs, *companies)).encode()).hexdigest()
    assert digest[:16] == "a1db1548759ff1d1"
    collide = {
        "generic_name": f"{drugs[0]} Tablets",
        "company_name": f"{companies[0]} Inc.",
        "event_date": "2020-01-01",
    }
    lexicon = M.name_lexicon(made_up(collide))
    assert drugs[0] not in lexicon.drugs and companies[0] not in lexicon.companies
    assert drugs[1] in lexicon.drugs and companies[1] in lexicon.companies


def test_a_seed_keeps_its_names_when_the_list_changes() -> None:
    events = made_up(CEFOXITIN, NAMED)
    lexicon = M.name_lexicon(events)
    rows = [events.iloc[-2].to_dict(), events.iloc[-1].to_dict()]
    alone = M.renamed_fields(rows[1], rows[1]["statement_group_id"], lexicon, set())[0]
    taken: set[str] = set()
    M.renamed_fields(rows[0], rows[0]["statement_group_id"], lexicon, taken)
    after = M.renamed_fields(rows[1], rows[1]["statement_group_id"], lexicon, taken)[0]
    assert alone == after


def test_a_word_of_a_name_that_notices_use_as_a_word_is_not_a_name() -> None:
    extra = [
        {
            "company_name": "Supply Pharma",
            "event_date": "2020-01-01",
            "availability_text": "On backorder",
        },
        *(
            {"availability_text": f"Limited supply until week {n}", "event_date": "2020-01-01"}
            for n in range(3)
        ),
    ]
    lexicon = M.name_lexicon(made_up(*extra))
    assert "supply" not in lexicon.words and "madeupol" in lexicon.words
    assert "inventa" in lexicon.words and "pharma" not in lexicon.words


# --------------------------------------------------------------------------------------------
# The whole build on made-up notices: selection, items, files, commands
# --------------------------------------------------------------------------------------------

MANY = tuple(
    {
        "event_date": f"2020-{month:02d}-05",
        "availability_text": text.format(M.MONTHS[month + 1]),
        "generic_name": f"Seedol{n} Injection",
        "company_name": f"Seedco{n} Pharma",
    }
    for n, (month, text) in enumerate(
        (month, text)
        for month in range(1, 10)
        for text in ("Unavailable, recovery in {} 2020", "Backordered. Next release {} 2020.")
    )
)


def sources_of(events: pd.DataFrame, seeds: list[dict[str, str]]) -> M.Sources:
    return M.Sources(events, seeds, "guide", set(), {"note": "made up"})


def listed(events: pd.DataFrame, ids: list[str]) -> list[dict[str, str]]:
    rows = events.set_index("statement_group_id")
    return [
        {
            "event_id": rows.loc[i, "event_id"],
            "statement_group_id": i,
            "thread_id": "",
            "period": "",
        }
        for i in ids
    ]


@pytest.fixture(scope="module")
def small() -> tuple[M.Built, M.Sources]:
    events = made_up(CEFOXITIN, RECOVERY, *MANY)
    seeds = listed(events, [f"S{900 + n:04d}" for n in range(2 + len(MANY))])
    sources = sources_of(events, seeds)
    return M.build(sources), sources


def test_build_is_deterministic_and_ignores_the_order_of_the_list(
    small: tuple[M.Built, M.Sources],
) -> None:
    built, sources = small
    files = M.generate_files(built, sources)
    again = M.generate_files(M.build(sources), sources)
    assert files == again
    shuffled = list(sources.seeds)
    random.Random(3).shuffle(shuffled)
    mixed = sources_of(sources.events.sample(frac=1, random_state=3), shuffled)
    assert M.generate_files(M.build(mixed), sources) == files


def test_items_are_what_the_harness_loads(small: tuple[M.Built, M.Sources], tmp_path: Path) -> None:
    built, sources = small
    files, keys = M.generate_files(built, sources)
    path = tmp_path / M.ITEMS_FILE
    path.write_text(files[M.ITEMS_FILE], encoding="utf-8")
    loaded = read.load_items(path)
    records = [json.loads(line) for line in files[M.ITEMS_FILE].splitlines()]
    assert (
        [i.item_id for i in loaded]
        == [r["item_id"] for r in records]
        == sorted(r["item_id"] for r in records)
    )
    for item, record in zip(loaded, records, strict=True):
        assert tuple(record) == (*M.ITEM_KEYS, *M.ITEM_EXTRA)
        assert set(M.ITEM_KEYS) <= set(read.ReadItem.__dataclass_fields__)
        for key in M.ITEM_KEYS:
            assert getattr(item, key) == record[key], key
        assert item.period == record["period"]  # the harness holds what the file marks
    seeds = [r for r in records if r["is_seed"]]
    assert len(seeds) == built.seeds_used == 20
    assert all((r["factor"], r["level"]) == (M.SEED_FACTOR, M.SEED_LEVEL) for r in seeds)
    assert {r["factor"] for r in records if not r["is_seed"]} == set(M.FACTORS)
    assert set(keys) == {M.GOLD_FILE, M.RULE_CHECK_FILE}  # the gold is kept with the keys
    assert M.GOLD_FILE not in files and "gold" not in files[M.ITEMS_FILE]
    manifest = json.loads(files[M.MANIFEST_FILE])
    assert (
        manifest["files"][M.ITEMS_FILE] == hashlib.sha256(files[M.ITEMS_FILE].encode()).hexdigest()
    )
    assert manifest["items"] == len(records) and manifest["seed"] == 20261001


def test_entry_block_is_the_one_the_models_see(small: tuple[M.Built, M.Sources]) -> None:
    import string

    built, _ = small
    for item in built.items[:25]:
        record = item.record()
        seen = string.Template(read.ENTRY_BLOCK).substitute(
            read._entry_fields(read.ReadItem.from_dict(record))
        )
        assert M.entry_block(record) == seen
    blank = M.entry_block({**built.items[0].record(), "related_information": ""})
    assert "- Related information: (blank)" in blank


def test_gold_file_has_the_columns_of_a_literal_gold(small: tuple[M.Built, M.Sources]) -> None:
    built, sources = small
    _, keys = M.generate_files(built, sources)
    rows = list(csv.DictReader(io.StringIO(keys[M.GOLD_FILE])))
    assert tuple(rows[0]) == M.GOLD_COLUMNS
    assert set(S.ENTERED) - {"hard", "note"} <= set(M.GOLD_COLUMNS)
    for row in rows:
        assert row["statement_type"] in S.STATEMENT_TYPES and row["certainty"] in S.CERTAINTY
        assert (row["abstain"] == "1") == (row["start"] == "") == (row["end"] == "")
        assert (row["abstain_reason"] in S.ABSTAIN_REASONS) == (row["abstain"] == "1")
        if row["abstain"] == "1":
            assert S.REASON_CERTAINTY[row["abstain_reason"]] == row["certainty"]
        assert set(row["distractor_roles"].split("; ")) - {""} <= set(S.ROLES)
        source = "rule reading of the seed" if row["is_seed"] == "1" else "construction"
        assert row["gold_source"] == source


def test_selection_caps_fills_levels_evenly_and_meets_the_target() -> None:
    def edit(factor: str, level: str) -> M.Edit:
        return M.Edit(factor, level, {}, M.Gold("recovery"))

    one = [edit("certainty", level) for level in ("expected", "tbd", "as_released")]
    one += [edit("distractor", level) for level in M.LEVELS["distractor"]]
    one += [edit("stale", "stale"), edit("silent", "silent")]
    edits = {f"S{n}": list(one) for n in range(30)}
    kept = M.select(edits, target=10_000)
    for chosen in kept.values():
        per = Counter(e.factor for e in chosen)
        assert per == {"certainty": 2, "distractor": 2, "stale": 1, "silent": 1}
        assert len({(e.factor, e.level) for e in chosen}) == len(chosen)
    levels = Counter((e.factor, e.level) for chosen in kept.values() for e in chosen)
    assert all(n == 20 for (f, _), n in levels.items() if f in ("certainty", "distractor"))
    trimmed = M.select(edits, target=30 + 150)
    sizes = Counter(e.factor for chosen in trimmed.values() for e in chosen)
    assert sum(sizes.values()) == 150
    assert sizes["stale"] == sizes["silent"] == 30  # only second levels are dropped
    assert sizes["certainty"] == sizes["distractor"] == 45
    floor = M.select(edits, target=0)
    assert Counter(e.factor for c in floor.values() for e in c) == dict.fromkeys(
        ("certainty", "distractor", "stale", "silent"), 30
    )
    assert M.select(edits, target=10_000) == kept


def test_rule_check_reports_a_difference_with_its_reason(small: tuple[M.Built, M.Sources]) -> None:
    built, _ = small
    assert built.check == []
    item = next(i for i in built.items if i.factor == "stale")
    assert item.edit is not None
    wrong = M.Item(item.item_id, item.seed, M.Edit("stale", "stale", item.fields, item.seed.gold))
    rows = M.rule_check([wrong])
    assert [(r["field"], r["gold"], r["rule"], r["reason"]) for r in rows] == [
        ("stale", "0", "1", "unexplained")
    ]
    assert M.difference_reason("Estimated recovery 4-6 weeks").startswith("D18")
    assert M.difference_reason("Will remain on backorder for 3 months").startswith("D18")
    assert M.difference_reason("Estimated recovery: 4-6 weeks") == "unexplained"


def test_build_refuses_a_list_that_does_not_fit_the_events(
    small: tuple[M.Built, M.Sources],
) -> None:
    _, sources = small
    twice = [*sources.seeds, sources.seeds[0]]
    with pytest.raises(ValueError, match="twice"):
        M.build(sources_of(sources.events, twice))
    lost = [{**sources.seeds[0], "event_id": "E9999"}]
    with pytest.raises(ValueError, match="not in the events table"):
        M.build(sources_of(sources.events, lost))
    other = [{**sources.seeds[0], "event_id": "E0001"}]
    with pytest.raises(ValueError, match="another statement"):
        M.build(sources_of(sources.events, other))
    marked = [{**sources.seeds[0], "period": "test"}]
    with pytest.raises(ValueError, match="listed as test"):
        M.build(sources_of(sources.events, marked))


def test_period_marks_later_seeds_and_later_dates() -> None:
    late = {"event_date": "2023-03-01", "availability_text": "Unavailable, recovery in May 2023"}
    edge = {
        "event_date": "2022-12-01",
        "availability_text": "Unavailable, recovery in December 2022",
    }
    events = made_up(late, edge, RECOVERY)
    built = M.build(sources_of(events, listed(events, ["S0900", "S0901", "S0902"])))
    periods = {(i.seed.seed_id, i.factor): i.period for i in built.items}
    assert {p for (s, _), p in periods.items() if s == "S0900"} == {"test"}
    assert periods["S0901", "seed"] == "train" and periods["S0901", "stale"] == "test"
    assert {p for (s, _), p in periods.items() if s == "S0902"} == {"train"}
    for item in built.items:
        assert read.ReadItem.from_dict(item.record()).period == item.period


def write_inputs(
    root: Path,
    events: pd.DataFrame,
    seeds: list[dict[str, str]],
    in_context: tuple[int, ...] = (),
) -> argparse.Namespace:
    """The files ``generate`` reads, made up, with the arguments that name them: statement 2
    is in the pilot, and the statements ``in_context`` are in the in-context pool."""

    def rows_of(numbers: tuple[int, ...]) -> list[dict[str, str]]:
        return [
            {"event_id": f"E{n:04d}", "statement_group_id": f"S{n:04d}", "thread_id": f"T{n:04d}"}
            for n in numbers
        ]

    (root / "samples").mkdir(parents=True)
    (root / "later").mkdir()
    events.to_csv(root / "events.csv.gz", index=False)
    for name in S.FIRST_SAMPLES:
        text = S.plain_csv(S.SAMPLE_COLUMNS, rows_of((2,)) if name == "pilot" else [])
        (root / "samples" / f"sample_{name}.csv").write_text(text)
    for name in M.LATER_LISTS:
        text = S.plain_csv(
            S.SAMPLE_COLUMNS, rows_of(in_context) if name == M.LATER_LISTS[0] else []
        )
        (root / "later" / f"sample_{name}.csv").write_text(text)
    (root / "seeds.csv").write_text(
        M.plain_csv(("event_id", "statement_group_id", "thread_id", "period"), seeds)
    )
    return argparse.Namespace(
        events=root / "events.csv.gz",
        captures=None,
        seeds=root / "seeds.csv",
        guide=M.GUIDE,
        samples=root / "samples",
        later=root / "later",
        out=root / "out",
        keys=root / "keys",
    )


def cli(args: argparse.Namespace, command: str, *more: str) -> list[str]:
    paths = {
        "generate": ("events", "seeds", "guide", "samples", "later", "out", "keys"),
        "audit-sample": ("out", "keys"),
        "sheets": ("guide", "out", "keys"),
    }[command]
    flags = [part for name in paths for part in (f"--{name}", str(getattr(args, name)))]
    return [command, *flags, *more]


def test_generate_writes_checks_and_goes_stale(
    small: tuple[M.Built, M.Sources], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, sources = small
    args = write_inputs(tmp_path, sources.events, sources.seeds)
    assert M.main(cli(args, "generate", "--check")) == 1  # nothing on disk yet
    assert not args.out.exists()
    assert M.main(cli(args, "generate")) == 0
    out = capsys.readouterr().out
    assert "seeds: 20 used, 0 dropped" in out and "differs from the gold: 0" in out
    names = {M.ITEMS_FILE, M.COUNTS_FILE, M.SKIPS_FILE, M.NAMES_FILE, M.MANIFEST_FILE}
    assert {p.name for p in args.out.iterdir()} == names
    assert {p.name for p in args.keys.iterdir()} == {M.GOLD_FILE, M.RULE_CHECK_FILE}
    for name in names - {M.MANIFEST_FILE}:  # nothing beside the items gives a gold away
        assert "undetermined" not in (args.out / name).read_text(), name
    manifest = json.loads((args.out / M.MANIFEST_FILE).read_text())
    inputs = manifest["inputs"]
    assert inputs["seed_list_sha256"] == M.sha256_file(args.seeds)
    assert inputs["guide_sha256"] == M.sha256_file(M.GUIDE)
    assert (
        inputs["rules_sha256"].startswith(M.RULES_SHA256_PREFIX)
        and inputs["rules_is_the_frozen_file"]
    )
    assert inputs["minimal_pairs_sha256"] == M.sha256_file(Path(M.__file__))
    assert inputs["left_out_of_the_attested_forms"]["labelling_samples"] == 1
    assert inputs["prompt_item_lists"] == {
        f"sample_{name}.csv": M.sha256_file(args.later / f"sample_{name}.csv")
        for name in M.LATER_LISTS
    }
    # the pilot's statement, and the seed of the guide's section 7.3, a row of its Appendix A
    assert inputs["texts_no_edit_may_produce"] == {"statements": 2, "texts": 2}
    assert M.main(cli(args, "generate", "--check")) == 0
    assert "up to date" in capsys.readouterr().out
    before = {p.name: p.read_bytes() for p in (*args.out.iterdir(), *args.keys.iterdir())}
    assert M.main(cli(args, "generate")) == 0
    assert {p.name: p.read_bytes() for p in (*args.out.iterdir(), *args.keys.iterdir())} == before
    assert manifest["key_files"][M.GOLD_FILE] == M.sha256_file(args.keys / M.GOLD_FILE)
    gold = args.keys / M.GOLD_FILE
    gold.write_text(gold.read_text().replace("estimated", "asserted", 1))
    assert M.main(cli(args, "generate", "--check")) == 1
    assert f"not up to date: {gold.as_posix()}" in capsys.readouterr().out
    assert gold.read_bytes() != before[M.GOLD_FILE]  # --check wrote nothing


def test_generate_leaves_the_labelling_samples_out_of_the_attested_forms(
    small: tuple[M.Built, M.Sources], tmp_path: Path
) -> None:
    """``S0002`` is in the made-up pilot list: its wording attests nothing."""
    _, sources = small
    args = write_inputs(tmp_path, sources.events, sources.seeds)
    loaded = M.load_sources(args)
    assert "S0002" in loaded.excluded
    built = M.build(loaded)
    assert "next release date not available at this time" not in built.inventory.sentences
    assert not [i for i in built.items if i.edit and "date not available" in i.edit.inserted]


def test_no_edit_gives_the_text_of_a_statement_that_is_read_elsewhere() -> None:
    """An edit that would read, word for word, like a statement of a labelling sample, of a
    prompt list or of Appendix A is not made; the others of the seed are."""
    shown = {
        "event_date": "2020-10-08",
        "availability_text": "Backordered. Next release expected October 2020.",
        "related_text": "Check wholesalers for inventory.",  # punctuation is not compared
    }
    events = made_up(CEFOXITIN, shown)
    lexicon = M.name_lexicon(events)
    inventory = M.build_inventory(events, {"S0900", "S0901"})
    seed, _, _ = M.make_seed(events.iloc[-2].to_dict(), "train", lexicon, set())
    assert seed is not None
    free, _ = M.edits_of(seed, inventory)
    reserved = M.reserved_texts(events, {"S0901"})
    assert reserved == {
        "backordered next release expected october 2020 check wholesalers for inventory"
    }
    made, skipped = M.edits_of(seed, inventory, reserved)
    gone = {(e.factor, e.level) for e in free} - {(e.factor, e.level) for e in made}
    assert gone == {("certainty", "expected")}
    assert reasons(skipped, "certainty", "expected") == [M.RESERVED]
    assert M.reserved_texts(events, {"S0003"}) == {"backordered next release mid june 2021"}
    assert M.reserved_texts(made_up({"event_date": "2020-01-01"}), {"S0900"}) == set()  # no word
    own = M.reserved_texts(events, {"S0900"})  # the seed's own text: its stale item keeps it
    assert M.is_reserved(seed.fields, own)
    kept = {(e.factor, e.level) for e in M.edits_of(seed, inventory, own)[0]}
    assert ("stale", "stale") in kept and ("certainty", "expected") in kept


def test_generate_reads_the_prompt_lists_and_counts_the_seeds_they_hold(
    small: tuple[M.Built, M.Sources], tmp_path: Path
) -> None:
    """Statement 800 is in the made-up in-context pool: the edit that would read like it is
    not made, and a seed that reads like statement 801 stays and is counted, as does the seed
    of the guide's section 7.3, which is a row of its Appendix A."""
    _, sources = small
    more = pd.DataFrame(
        [
            event(800, "Backordered. Next release October."),
            event(801, "Unavailable, recovery in May 2020", "Check wholesalers"),
        ],
        columns=list(S.EVENT_FIELDS),
    )
    events = pd.concat([sources.events, more], ignore_index=True)
    args = write_inputs(tmp_path, events, sources.seeds, in_context=(800, 801))
    loaded = M.load_sources(args)
    assert loaded.reserved == {
        "unavailable next release date not available at this time",  # statement 2, the pilot
        "backordered next release october 2020 check wholesalers for inventory",  # Appendix A
        "backordered next release october",
        "unavailable recovery in may 2020 check wholesalers",
    }
    assert loaded.record["texts_no_edit_may_produce"] == {"statements": 4, "texts": 4}
    built = M.build(loaded)
    texts = {M.item_text(i.fields): i for i in built.items}
    assert "Backordered. Next release October." not in texts
    assert "Backordered. Next release October. || Check wholesalers for inventory" in texts
    skipped = [r for r in built.skips if r["reason"] == M.RESERVED]
    assert [(r["factor"], r["level"]) for r in skipped] == [("surface_form", "no_year")]
    recovery = next(i.seed for i in built.items if i.seed.seed_id == "S0901")
    own = ("S0900", "S0901")
    assert built.reserved_seeds == own and M.is_reserved(recovery.fields, loaded.reserved)
    assert M.counts_of(built)["seeds_whose_own_text_is_reserved"] == list(own)
    for seed_id in own:  # the seed stays, with the edit that keeps its text
        assert {"seed", "stale"} <= {i.factor for i in built.items if i.seed.seed_id == seed_id}
    for item in built.items:  # no other item reads like a reserved statement
        if item.seed.seed_id not in own or item.factor not in ("seed", "stale"):
            assert not M.is_reserved(item.fields, loaded.reserved), item.item_id
    (args.later / f"sample_{M.LATER_LISTS[1]}.csv").unlink()
    with pytest.raises(SystemExit, match="lists of prompt items are drawn first"):
        M.load_sources(args)


def test_generate_stops_when_rules_is_not_the_frozen_file(
    small: tuple[M.Built, M.Sources], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sources = small
    args = write_inputs(tmp_path, sources.events, sources.seeds)
    monkeypatch.setattr(M, "RULES_SHA256_PREFIX", "0" * 16)
    with pytest.raises(SystemExit, match="not the frozen file"):
        M.main(cli(args, "generate"))
    assert not args.out.exists()


def test_rules_file_is_the_frozen_one() -> None:
    assert M.sha256_file(Path(R.__file__)).startswith(M.RULES_SHA256_PREFIX)


# --------------------------------------------------------------------------------------------
# The audit: draw, key, sheets, validator, scorer
# --------------------------------------------------------------------------------------------


def gold_rows(n_seeds: int = 60) -> list[dict[str, str]]:
    """A made-up gold file: every seed with one edit of each factor and a second distractor."""
    rows = []
    base = {
        "statement_type": "recovery",
        "start": "2020-05-01",
        "end": "2020-05-31",
        "abstain": "0",
        "certainty": "asserted",
        "stale": "0",
        "distractor_roles": "",
        "attested_text": "a notice",
    }
    edits = (
        ("certainty", "expected", {"certainty": "estimated"}),
        ("surface_form", "no_year", {}),
        ("granularity", "mid", {"start": "2020-05-11", "end": "2020-05-20"}),
        ("stale", "stale", {"stale": "1", "attested_text": ""}),
        ("distractor", "expiry", {"distractor_roles": "expiry"}),
        ("distractor", "depletion", {"distractor_roles": "depletion"}),
        (
            "silent",
            "silent",
            {
                "statement_type": "none",
                "start": "",
                "end": "",
                "abstain": "1",
                "certainty": "no_statement",
                "attested_text": "",
            },
        ),
    )
    for n in range(n_seeds):
        seed_id = f"S{n:03d}"
        rows.append(
            {
                **base,
                "item_id": M.item_id(seed_id, "seed", "unedited"),
                "seed_id": seed_id,
                "factor": "seed",
                "level": "unedited",
                "is_seed": "1",
            }
        )
        for factor, level, change in edits:
            rows.append(
                {
                    **base,
                    **change,
                    "item_id": M.item_id(seed_id, factor, level),
                    "seed_id": seed_id,
                    "factor": factor,
                    "level": level,
                    "is_seed": "0",
                }
            )
    return rows


def check_draw(
    key: list[dict[str, Any]],
    strata: list[dict[str, Any]],
    gold: list[dict[str, str]],
    sizes: tuple[int, int, int] = M.AUDIT_SIZES,
) -> None:
    """Everything section 7.1 asks of the sample."""
    own, shared, planted = sizes
    by_id = {row["item_id"]: row for row in gold}
    real = [r for r in key if not int(r["planted"])]
    fake = [r for r in key if int(r["planted"])]
    assert len(real) == 2 * own + shared and len(fake) == 2 * planted
    assert len({r["pair_id"] for r in key}) == len(key)
    assert all(by_id[r["pair_id"]]["is_seed"] == "0" for r in key)  # edited items only
    per_factor = Counter(r["factor"] for r in real)
    assert set(per_factor) == set(M.FACTORS)
    assert max(per_factor.values()) - min(per_factor.values()) <= 1  # equal shares
    assert {s["factor"]: s["drawn"] for s in strata} == dict(per_factor)
    assert max(Counter(r["seed_id"] for r in real).values()) <= M.MAX_PER_SEED
    assert Counter(r["assigned_to"] for r in real) == {"A1": own, "A2": own, "both": shared}
    for auditor in M.AUDITORS:
        mine = [r for r in key if r["assigned_to"] in (auditor, M.SHARED)]
        assert len(mine) == own + shared + planted
        assert max(Counter(r["seed_id"] for r in mine).values()) <= M.MAX_PER_SEED
        assert {r["factor"] for r in mine if not int(r["planted"])} == set(M.FACTORS)
        plants = [r for r in fake if r["assigned_to"] == auditor]
        fields = [r["planted_field"] for r in plants]
        assert sorted(fields) == sorted(M.PLANT_FIELDS[n % 5] for n in range(planted))
    for row in key:
        true = {c: row[f"true_{c}"] for c in M.GOLD_SHOWN}
        seen = {c: row[f"shown_{c}"] for c in M.GOLD_SHOWN}
        assert true == M.shown_gold(by_id[row["pair_id"]])
        changed = {c for c in M.GOLD_SHOWN if true[c] != seen[c]}
        if not int(row["planted"]):
            assert not changed and row["planted_field"] == ""
            continue
        allowed = {
            "type": {"gold_statement_type"},
            "interval": {"gold_start", "gold_end"},
            "certainty": {"gold_certainty"},
            "stale": {"gold_stale"},
            "distractors": {"gold_distractor_roles"},
        }[row["planted_field"]]
        assert changed and changed <= allowed, row


def test_audit_draw_strata_caps_assignment_and_planted_items() -> None:
    gold = gold_rows()
    key, strata = M.draw_audit(gold)
    check_draw(key, strata, gold)
    assert M.draw_audit(list(reversed(gold))) == (key, strata)  # the order of the file is nothing
    assert [s["quota"] for s in strata] == [
        17,
        17,
        17,
        16,
        17,
        16,
    ]  # the largest pools get the extra
    small_key, small_strata = M.draw_audit(gold, (27, 6, 3))
    check_draw(small_key, small_strata, gold, (27, 6, 3))
    fresh, fresh_strata = M.draw_audit(gold, round_=2)  # a second audit is another draw
    check_draw(fresh, fresh_strata, gold)
    assert {r["pair_id"] for r in fresh} != {r["pair_id"] for r in key}


def test_audit_draw_gives_what_a_thin_factor_lacks_to_the_others() -> None:
    gold = [r for r in gold_rows() if r["factor"] != "stale" or int(r["seed_id"][1:]) < 5]
    key, strata = M.draw_audit(gold)
    drawn = {s["factor"]: s["drawn"] for s in strata}
    assert drawn["stale"] == 5 and sum(drawn.values()) == 100
    assert max(Counter(r["seed_id"] for r in key if not int(r["planted"])).values()) <= 2


CORRUPT = (  # the shown gold, the field, what changes
    ({"gold_statement_type": "recovery"}, "type", {"gold_statement_type": "next_delivery"}),
    ({"gold_statement_type": "none", "gold_abstain": "1"}, "type", None),
    (
        {"gold_start": "2020-05-11", "gold_end": "2020-05-20"},
        "interval",
        {"gold_start": "2020-05-01", "gold_end": "2020-05-31"},
    ),
    ({}, "interval", {"gold_end": "2020-06-30"}),
    (
        {"gold_start": "2020-10-01", "gold_end": "2020-12-31"},
        "interval",
        {"gold_end": "2021-01-31"},
    ),
    ({"gold_abstain": "1", "gold_start": "", "gold_end": ""}, "interval", None),
    ({}, "certainty", {"gold_certainty": "estimated"}),
    ({"gold_certainty": "undetermined"}, "certainty", {"gold_certainty": "estimated"}),
    ({"gold_certainty": "no_statement"}, "certainty", None),
    ({}, "stale", {"gold_stale": "1"}),
    ({"gold_stale": "1"}, "stale", {"gold_stale": "0"}),
    ({"gold_abstain": "1"}, "stale", None),
    ({"gold_distractor_roles": "expiry"}, "distractors", {"gold_distractor_roles": "depletion"}),
    ({}, "distractors", None),
)


@pytest.mark.parametrize(("change", "field", "wanted"), CORRUPT)
def test_corrupt_changes_one_field_by_its_rule(
    change: dict[str, str], field: str, wanted: dict[str, str] | None
) -> None:
    base = {
        "gold_statement_type": "recovery",
        "gold_start": "2020-05-01",
        "gold_end": "2020-05-31",
        "gold_abstain": "0",
        "gold_certainty": "asserted",
        "gold_stale": "0",
        "gold_distractor_roles": "",
    }
    gold = {**base, **change}
    wrong = M.corrupt(gold, field)
    assert wrong == (None if wanted is None else {**gold, **wanted})
    assert wrong is None or wrong != gold


@pytest.fixture()
def audit(small: tuple[M.Built, M.Sources], tmp_path: Path) -> argparse.Namespace:
    """The files of ``generate`` on made-up notices, a sample of 12 and 6 with 2 planted items
    each, and the two blank sheets."""
    built, sources = small
    files, keys = M.generate_files(built, sources)
    args = argparse.Namespace(
        out=tmp_path / "out", keys=tmp_path / "keys", guide=M.GUIDE, work=tmp_path / "work"
    )
    M.write_files(args.out, files)
    M.write_files(args.keys, keys)
    assert M.main(cli(args, "audit-sample", "--own", "12", "--shared", "6", "--planted", "2")) == 0
    assert M.main(cli(args, "sheets")) == 0
    args.work.mkdir()
    return args


def fill(
    args: argparse.Namespace,
    auditor: str,
    marks: dict[str, dict[str, str]] | None = None,
    times: tuple[str, str] = ("09:00", "09:40"),
) -> Path:
    """A copy of a blank sheet filled as a careful auditor would: 1 everywhere, then ``marks``
    by pair id."""
    meta, rows = S.read_sheet(args.out / f"pairs_{auditor}.csv")
    meta = [(k, times[S.SITTING_KEYS.index(k)] if k in S.SITTING_KEYS else v) for k, v in meta]
    for row in rows:
        row |= dict.fromkeys((*M.ERROR_CHECKS, "natural"), "1")
        row |= (marks or {}).get(row["pair_id"], {})
    path = args.work / f"pairs_{auditor}.csv"
    path.write_text(S.sheet_text(M.SHEET_COLUMNS, rows, meta), encoding="utf-8")
    return path


def read_key(args: argparse.Namespace) -> list[dict[str, str]]:
    return M.read_csv(args.keys / M.KEY_FILE)


def catching(args: argparse.Namespace, auditor: str) -> dict[str, dict[str, str]]:
    """Marks that catch every planted item of an auditor on its corrupted field."""
    return {
        r["pair_id"]: {M.PLANT_CHECK[r["planted_field"]]: "0", "correct_value": "the true value"}
        for r in read_key(args)
        if r["planted"] == "1" and r["assigned_to"] == auditor
    }


def test_sheets_have_the_guide_layout_and_keep_the_key_apart(audit: argparse.Namespace) -> None:
    key = read_key(audit)
    assert {p.name for p in audit.out.iterdir()} >= {
        "pairs_A1.csv",
        "pairs_A2.csv",
        "pairs_A1_items.txt",
        "pairs_A2_items.txt",
        M.AUDIT_MANIFEST_FILE,
    }
    assert not (audit.out / M.KEY_FILE).exists() and (audit.keys / M.KEY_FILE).is_file()
    guide = " ".join(S.guide_section(M.GUIDE.read_text(encoding="utf-8"), "9").split())
    for column in M.SHEET_COLUMNS:
        assert f"`{column}`" in guide, column  # the columns are those of the guide's section 9
    for auditor in M.AUDITORS:
        meta, rows = S.read_sheet(audit.out / f"pairs_{auditor}.csv")
        assert tuple(rows[0]) == M.SHEET_COLUMNS and len(rows) == 12 + 6 + 2
        assert (
            S.meta_value(meta, "annotator") == auditor and S.meta_value(meta, "seed") == "20261001"
        )
        assert S.meta_value(meta, "guide") == S.guide_stamp(M.GUIDE.read_text(encoding="utf-8"))
        assert [k for k, _ in meta][-2:] == list(S.SITTING_KEYS)
        mine = {r["pair_id"]: r for r in key if r["assigned_to"] in (auditor, "both")}
        assert {r["pair_id"] for r in rows} == set(mine)
        for row in rows:
            assert all(row[c] == "" for c in M.ENTERED)
            assert {c: row[c] for c in M.GOLD_SHOWN} == {
                c: mine[row["pair_id"]][f"shown_{c}"] for c in M.GOLD_SHOWN
            }
            assert (
                row["seed_entry"].startswith("Entry\n- Drug: ")
                and row["edited_entry"] != row["seed_entry"]
            )
            assert row["attested_text"]
        text = (audit.out / f"pairs_{auditor}_items.txt").read_text()
        assert [m for m in re.findall(r"=== \d+ of 20: (P\w+)", text)] == [
            r["pair_id"] for r in rows
        ]
    orders = [
        [r["pair_id"] for r in S.read_sheet(audit.out / f"pairs_{a}.csv")[1]] for a in M.AUDITORS
    ]
    shared = [r["pair_id"] for r in key if r["assigned_to"] == "both"]
    assert [i for i in orders[0] if i in shared] != [i for i in orders[1] if i in shared]


def test_planted_items_look_like_the_others(audit: argparse.Namespace) -> None:
    """Nothing an auditor is given tells a planted item from a real one."""
    key = {r["pair_id"]: r for r in read_key(audit)}
    planted = {i for i, r in key.items() if r["planted"] == "1"}
    assert len(planted) == 4
    for path in audit.out.iterdir():
        text = path.read_text(encoding="utf-8")
        if path.name.startswith("pairs_A"):  # what an auditor is given
            assert "planted" not in text.lower(), path.name
        if path.name == M.AUDIT_MANIFEST_FILE:
            assert not re.search(r"\bP[0-9a-f]{10}\b", text)  # the manifest names no item
    for auditor in M.AUDITORS:
        _, rows = S.read_sheet(audit.out / f"pairs_{auditor}.csv")
        fake = [r for r in rows if r["pair_id"] in planted]
        real = [r for r in rows if r["pair_id"] not in planted]
        assert len(fake) == 2
        positions = [n for n, r in enumerate(rows) if r["pair_id"] in planted]
        assert positions != list(range(len(rows) - 2, len(rows)))  # not at the end of the sheet
        for row in fake:
            assert re.fullmatch(r"P[0-9a-f]{10}", row["pair_id"])
            assert {c for c in M.SHEET_COLUMNS if row[c]} <= {
                c for r in real for c in M.SHEET_COLUMNS if r[c]
            }
            assert row["factor"] in M.FACTORS and row["level"] in M.LEVELS[row["factor"]]
            same_kind = [r for r in real if r["factor"] == row["factor"]]
            shapes = {tuple(bool(r[c]) for c in M.SHOWN) for r in same_kind} | {
                tuple(bool(r[c]) for c in M.SHOWN) for r in real
            }
            assert tuple(bool(row[c]) for c in M.SHOWN) in shapes
            assert row["edited_entry"] != row["seed_entry"]


def test_validator_accepts_a_filled_copy_and_names_every_fault(
    audit: argparse.Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    good = fill(audit, "A1")
    checked = M.check_file(good, None, audit.out)
    assert (
        checked.ok and checked.minutes == 40 and len(checked.marks) == 20 and not checked.warnings
    )
    assert M.main(["validate", str(good), "--out", str(audit.out)]) == 0
    assert "20 rows read, ok, 40 minutes" in capsys.readouterr().out
    meta, rows = S.read_sheet(good)
    ids = [r["pair_id"] for r in rows]

    def errors(
        change: dict[int, dict[str, str]],
        keep: slice = slice(None),
        header: list[tuple[str, str]] | None = None,
    ) -> list[str]:
        edited = [{**r, **change.get(n, {})} for n, r in enumerate(rows)][keep]
        path = audit.work / "edited.csv"
        path.write_text(S.sheet_text(M.SHEET_COLUMNS, edited, header or meta), encoding="utf-8")
        return M.check_file(path, audit.out / "pairs_A1.csv", audit.out).errors

    assert errors({}) == []
    assert "ok_type must be 1 or 0" in errors({0: {"ok_type": "yes"}})[0]
    assert "natural must be 1 or 0" in errors({0: {"natural": ""}})[0]
    assert "correct_value is empty" in errors({1: {"ok_interval": "0"}})[0]
    assert errors({1: {"ok_interval": "0", "correct_value": "2020-05-11 to 2020-05-20"}}) == []
    assert "note is empty" in errors({2: {"minimal": "0"}})[0]
    assert "note is empty" in errors({2: {"attested": "0"}})[0]
    assert errors({2: {"attested": "0", "note": "the form is not in the notice"}}) == []
    assert errors({3: {"natural": "0"}}) == []  # natural needs no note
    assert (
        "shown cells changed (gold_certainty)"
        in errors(
            {
                4: {
                    "gold_certainty": "asserted"
                    if rows[4]["gold_certainty"] != "asserted"
                    else "estimated"
                }
            }
        )[0]
    )
    assert (
        "shown cells changed (edited_entry)"
        in errors({4: {"edited_entry": rows[4]["edited_entry"] + " x"}})[0]
    )
    assert "1 items of the blank sheet are missing" in errors({}, slice(1, None))[0]
    assert "not in the blank sheet" in errors({5: {"pair_id": "P0000000000"}})[0]
    assert "missing or repeated" in errors({5: {"pair_id": ids[6]}})[0]
    assert (
        "sitting_start"
        in errors({}, header=[(k, "" if k == "sitting_end" else v) for k, v in meta])[0]
    )
    spreadsheet = [{**r, "seed_entry": r["seed_entry"].replace("\n", "\r\n")} for r in rows]
    path = audit.work / "saved.csv"
    path.write_text(S.sheet_text(M.SHEET_COLUMNS, spreadsheet, meta), encoding="utf-8")
    assert M.check_file(path, None, audit.out).ok  # line ends inside a cell are not a change
    assert (
        "blank sheet itself" in M.check_file(audit.out / "pairs_A1.csv", None, audit.out).errors[0]
    )
    other = audit.work / "elsewhere"
    other.mkdir()
    alone = M.check_file(good, None, other)
    assert alone.ok and alone.warnings == [S.NO_BLANK]
    path.write_bytes("pair_id;factor\nP1;stale\n".encode("utf-16"))
    assert M.check_file(path, None, audit.out).errors == [S.NOT_UTF8]
    assert M.main(["validate", str(path), "--out", str(audit.out)]) == 1


def test_score_all_clear_passes_without_adjudication(
    audit: argparse.Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    a1, a2 = (
        fill(audit, "A1", catching(audit, "A1")),
        fill(audit, "A2", catching(audit, "A2"), ("10:00", "10:30")),
    )
    assert (
        M.main(
            [
                "score",
                "--a1",
                str(a1),
                "--a2",
                str(a2),
                "--out",
                str(audit.out),
                "--keys",
                str(audit.keys),
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert (
        "A1: caught 2 of 2 planted items" in out
        and "30 of 30 real items free" in out
        and "pass" in out
    )
    result = json.loads((audit.out / M.SCORE_FILE).read_text())
    assert result["passed"] and result["needed"] == 29 and result["wilson95"][1] == 1.0
    assert result["planted"]["A2"] == {
        "n": 2,
        "caught": 2,
        "caught_on_the_corrupted_field": 2,
        "missed": [],
        "recheck_own_items": False,
    }
    assert result["double_audited"] == {"n": 6, "raw_agreement": 1.0, "kappa": None}
    assert result["seconds_per_item"] == {"A1": 120.0, "A2": 90.0}
    assert sum(f["n"] for f in result["by_factor"].values()) == 30
    assert not (audit.out / M.ADJUDICATION_FILE).exists()


def reported(
    args: argparse.Namespace, n_a1: int, n_shared_a2: int = 0
) -> tuple[Path, Path, list[str]]:
    """Sheets on which A1 reports ``n_a1`` real items of its own and A2 some shared ones."""
    key = read_key(args)
    own = sorted(r["pair_id"] for r in key if r["planted"] == "0" and r["assigned_to"] == "A1")[
        :n_a1
    ]
    shared = sorted(r["pair_id"] for r in key if r["assigned_to"] == "both")[:n_shared_a2]
    wrong = {"ok_interval": "0", "correct_value": "another interval"}
    a1 = fill(args, "A1", catching(args, "A1") | dict.fromkeys(own, wrong))
    a2 = fill(
        args,
        "A2",
        {i: {"minimal": "0", "note": "two things change", "natural": "0"} for i in shared},
    )
    return a1, a2, [*own, *shared]


def decide(args: argparse.Namespace, decisions: dict[str, tuple[str, str]]) -> Path:
    meta, rows = S.read_sheet(args.out / M.ADJUDICATION_FILE)
    for row in rows:
        row["decision"], row["confirmed_checks"] = decisions[row["pair_id"]]
    path = args.work / M.ADJUDICATION_FILE
    path.write_text(S.sheet_text(tuple(rows[0]), rows, meta), encoding="utf-8")
    return path


def test_score_adjudication_and_the_pass_rule(
    audit: argparse.Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """30 real items: 29 must be free of confirmed errors (95%, rounded up)."""
    a1, a2, ids = reported(audit, 2, 1)
    command = [
        "score",
        "--a1",
        str(a1),
        "--a2",
        str(a2),
        "--out",
        str(audit.out),
        "--keys",
        str(audit.keys),
    ]
    assert M.main(command) == 3
    out = capsys.readouterr().out
    assert "3 reported errors" in out and "A2: caught 0 of 2 planted items" in out
    assert "A2: missed 2 or more; re-check your own real items once" in out
    pending = json.loads((audit.out / M.SCORE_FILE).read_text())
    assert pending["status"] == "adjudication pending" and "passed" not in pending
    assert pending["reported"]["A1"]["failed_checks"]["ok_interval"] == 2
    assert pending["reported"]["A2"] == {
        "items_marked_error": 1,
        "failed_checks": {**dict.fromkeys(M.ERROR_CHECKS, 0), "minimal": 1},
        "natural_0": 1,
    }
    assert (
        pending["double_audited"]["raw_agreement"] == round(5 / 6, 4)
        and pending["double_audited"]["kappa"] == 0.0
    )
    _, rows = S.read_sheet(audit.out / M.ADJUDICATION_FILE)
    assert [(r["pair_id"], r["reported_by"]) for r in rows] == sorted(
        zip(ids, ("A1", "A1", "A2"), strict=True)
    )
    assert all(r["decision"] == "" and r["edited_entry"] for r in rows)
    one = decide(
        audit,
        {
            ids[0]: ("confirmed", "ok_interval"),
            ids[1]: ("rejected", ""),
            ids[2]: ("unresolved", ""),
        },
    )
    assert M.main([*command, "--adjudication", str(one)]) == 0
    result = json.loads((audit.out / M.SCORE_FILE).read_text())
    assert (result["free_of_confirmed_errors"], result["needed"], result["passed"]) == (
        29,
        29,
        True,
    )
    assert result["confirmed_errors"] == {ids[0]: ["ok_interval"]} and result["unresolved"] == [
        ids[2]
    ]
    assert result["confirmed_checks"] == {"ok_interval": 1}
    two = decide(
        audit,
        {
            ids[0]: ("confirmed", "ok_interval"),
            ids[1]: ("rejected", ""),
            ids[2]: ("confirmed", "minimal"),
        },
    )
    assert M.main([*command, "--adjudication", str(two)]) == 1
    result = json.loads((audit.out / M.SCORE_FILE).read_text())
    assert (result["free_of_confirmed_errors"], result["passed"]) == (28, False)
    assert (
        "28 of 30 real items free of confirmed errors (needed 29): fail" in capsys.readouterr().out
    )
    in_place = audit.out / M.ADJUDICATION_FILE
    blank_sheet = in_place.read_bytes()
    shutil.copy(two, in_place)  # decisions written into the sheet under the output folder
    assert M.main(command) == 2 and in_place.read_bytes() == two.read_bytes()
    assert "filled in place" in capsys.readouterr().out
    in_place.write_bytes(blank_sheet)
    bad = decide(
        audit, {ids[0]: ("confirmed", ""), ids[1]: ("maybe", ""), ids[2]: ("rejected", "minimal")}
    )
    assert M.main([*command, "--adjudication", str(bad)]) == 2
    out = capsys.readouterr().out
    assert (
        "needs its confirmed_checks" in out
        and "decision must be one of" in out
        and "not confirmed" in out
    )


def test_score_keeps_the_pass_before_a_recheck(
    audit: argparse.Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    """Section 8.3: an auditor who missed planted items re-checks, and both passes are
    reported. The score of other filled sheets stays in the score file; scoring the same
    sheets again adds nothing."""
    a1 = fill(audit, "A1", catching(audit, "A1"))
    a2 = fill(audit, "A2")  # misses both planted items
    command = ["score", "--out", str(audit.out), "--keys", str(audit.keys), "--a1", str(a1)]
    assert M.main([*command, "--a2", str(a2)]) == 0
    assert "A2: missed 2 or more" in capsys.readouterr().out
    first = json.loads((audit.out / M.SCORE_FILE).read_text())
    assert first["earlier_passes"] == [] and first["planted"]["A2"]["recheck_own_items"]
    assert M.main([*command, "--a2", str(a2)]) == 0  # the same sheets: one pass
    assert json.loads((audit.out / M.SCORE_FILE).read_text()) == first
    again = audit.work / "recheck"
    again.mkdir()
    shutil.copy(fill(audit, "A2", catching(audit, "A2")), again / "pairs_A2.csv")
    assert M.main([*command, "--a2", str(again / "pairs_A2.csv")]) == 0
    second = json.loads((audit.out / M.SCORE_FILE).read_text())
    assert second["planted"]["A2"]["caught"] == 2 and len(second["earlier_passes"]) == 1
    kept = second["earlier_passes"][0]
    assert kept == {k: v for k, v in first.items() if k != "earlier_passes"}
    assert kept["planted"]["A2"]["caught"] == 0 and kept["sheets_sha256"] != second["sheets_sha256"]
    capsys.readouterr()


def test_pass_rule_is_95_of_100() -> None:
    assert [M.pass_count(n) for n in (100, 60, 30, 20)] == [95, 57, 29, 19]
    key = [
        {"pair_id": f"P{n}", "factor": M.FACTORS[n % 6], "planted": "0", "assigned_to": "A1"}
        for n in range(100)
    ]
    clear = dict.fromkeys((*M.ERROR_CHECKS, "natural"), "1") | {"correct_value": "", "note": ""}
    sheets = {
        a: M.Checked({r["pair_id"]: clear for r in key} if a == "A1" else {}, [], [], 40, [])
        for a in M.AUDITORS
    }
    for confirmed, passed in ((5, True), (6, False)):
        rows = [
            {"pair_id": f"P{n}", "decision": "confirmed", "confirmed_checks": "ok_type"}
            for n in range(confirmed)
        ]
        result = M.score(key, sheets, rows)
        assert (result["free_of_confirmed_errors"], result["passed"]) == (100 - confirmed, passed)
        assert result["share"] == (100 - confirmed) / 100
    two_rows = [
        {"pair_id": "P1", "decision": "confirmed", "confirmed_checks": c}
        for c in ("ok_type", "minimal")
    ]
    assert M.score(key, sheets, two_rows)["free_of_confirmed_errors"] == 99  # one item, two rows


def test_score_refuses_sheets_it_cannot_trust(
    audit: argparse.Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    a1, a2 = fill(audit, "A1"), fill(audit, "A2")
    command = ["score", "--out", str(audit.out), "--keys", str(audit.keys)]
    assert M.main([*command, "--a1", str(a2), "--a2", str(a1)]) == 2  # the two sheets swapped
    assert M.main([*command, "--a1", str(audit.out / "pairs_A1.csv"), "--a2", str(a2)]) == 2
    assert "blank sheet itself" in capsys.readouterr().out
    blank = audit.out / "pairs_A2.csv"
    kept = blank.read_bytes()
    blank.write_bytes(kept.replace(b"recovery", b"next_delivery", 1))
    assert M.main([*command, "--a1", str(a1), "--a2", str(a2)]) == 2
    assert "not the sheet the manifest records" in capsys.readouterr().out
    blank.write_bytes(kept)
    key = audit.keys / M.KEY_FILE
    key.write_text(key.read_text().replace(",A1,", ",A2,", 1))
    with pytest.raises(SystemExit, match="not the key the manifest records"):
        M.main([*command, "--a1", str(a1), "--a2", str(a2)])


def test_audit_commands_check_and_guard_what_is_on_disk(
    audit: argparse.Namespace, capsys: pytest.CaptureFixture[str]
) -> None:
    sizes = ("--own", "12", "--shared", "6", "--planted", "2")
    assert M.main(cli(audit, "audit-sample", *sizes, "--check")) == 0
    assert M.main(cli(audit, "sheets", "--check")) == 0
    before = {p.name: p.read_bytes() for p in (*audit.out.iterdir(), *audit.keys.iterdir())}
    assert M.main(cli(audit, "audit-sample", *sizes)) == 0 and M.main(cli(audit, "sheets")) == 0
    assert {p.name: p.read_bytes() for p in (*audit.out.iterdir(), *audit.keys.iterdir())} == before
    assert (
        M.main(
            cli(audit, "audit-sample", "--own", "10", "--shared", "6", "--planted", "2", "--check")
        )
        == 1
    )
    with pytest.raises(SystemExit, match="another sample"):
        M.main(cli(audit, "audit-sample", "--own", "10", "--shared", "6", "--planted", "2"))
    assert {p.name: p.read_bytes() for p in (*audit.out.iterdir(), *audit.keys.iterdir())} == before
    sheet = audit.out / "pairs_A1.csv"
    shutil.copy(fill(audit, "A1"), sheet)  # filled in place
    with pytest.raises(SystemExit, match="filled in place"):
        M.main(cli(audit, "sheets"))
    assert M.main(cli(audit, "sheets", "--check")) == 1
    sheet.write_bytes(before["pairs_A1.csv"])
    gold = audit.keys / M.GOLD_FILE
    gold.write_text(gold.read_text() + "\n")
    with pytest.raises(SystemExit, match="not the file the manifest of generate records"):
        M.main(cli(audit, "sheets"))
    capsys.readouterr()


def test_wilson_and_kappa() -> None:
    assert M.wilson(95, 100) == [0.8882, 0.9785]
    assert M.wilson(0, 0) is None and M.wilson(10, 10)[1] == 1.0
    assert (
        M.cohen_kappa([("ok", "ok"), ("error", "error"), ("ok", "error"), ("error", "ok")]) == 0.0
    )
    assert M.cohen_kappa([("ok", "ok")] * 4) is None and M.cohen_kappa([]) is None
    assert M.assign(100, 45, 10).count("both") == 10 and M.assign(60, 27, 6).count("A2") == 27


# --------------------------------------------------------------------------------------------
# The real captures: the whole build, in memory
# --------------------------------------------------------------------------------------------

needs_captures = pytest.mark.skipif(
    not CAPTURES.is_dir() or not M.SEEDS.is_file(), reason="no captures or no seed list"
)


@pytest.fixture(scope="module")
def real() -> tuple[M.Built, M.Sources]:
    args = argparse.Namespace(
        events=None, captures=CAPTURES, seeds=M.SEEDS, guide=M.GUIDE, samples=M.SAMPLES, later=None
    )
    sources = M.load_sources(args)
    return M.build(sources), sources


@needs_captures
def test_real_counts_factors_levels_and_seeds(real: tuple[M.Built, M.Sources]) -> None:
    built, sources = real
    counts = M.counts_of(built)
    assert counts["seeds_listed"] == len(sources.seeds) and counts["seeds_dropped"] <= 5
    assert 700 <= counts["items"] <= M.TARGET_ITEMS
    assert counts["per_factor"]["seed"] == counts["seeds_used"]
    assert all(counts["per_factor"][f] >= 70 for f in M.FACTORS)  # every factor is there
    for factor in ("certainty", "granularity", "stale", "distractor", "silent"):
        assert counts["levels_with_no_item"][factor] == [], factor  # every level the plan names
    assert counts["edited_items_per_seed"]["max"] <= sum(M.PER_SEED.values())
    assert counts["edited_items_per_seed"]["max"] / counts["items"] < 0.02  # no seed dominates
    per_seed = Counter((i.seed.seed_id, i.factor) for i in built.items if i.edit)
    assert all(n <= M.PER_SEED[f] for (_, f), n in per_seed.items())
    assert len({(i.seed.seed_id, i.factor, i.level) for i in built.items}) == len(built.items)
    listed_periods = {r["statement_group_id"]: r["period"] for r in sources.seeds}
    for item in built.items:
        assert item.seed.period == listed_periods[item.seed.seed_id]
        assert item.period == "test" or item.fields["date_of_update"] < "2023-01-01"
        assert item.seed.period == "train" or item.period == "test"
        # what the file marks as test is what the harness holds until F1 (its test and late)
        held = read.ReadItem.from_dict(item.record()).period in read.SEALED_PERIODS
        assert held == (item.period == "test"), item.item_id


@needs_captures
def test_real_build_is_deterministic(real: tuple[M.Built, M.Sources]) -> None:
    built, sources = real
    again = M.build(
        M.Sources(
            sources.events.sample(frac=1, random_state=7),
            list(reversed(sources.seeds)),
            sources.guide,
            sources.excluded,
            sources.record,
            sources.reserved,
        )
    )
    assert M.generate_files(again, sources) == M.generate_files(built, sources)


def changed_region(old: str, new: str) -> tuple[int, int]:
    """Where ``old`` differs from ``new``: what lies between their common head and tail."""
    head = next(
        (n for n, (a, b) in enumerate(zip(old, new, strict=False)) if a != b),
        min(len(old), len(new)),
    )
    tail = 0
    while tail < min(len(old), len(new)) - head and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    return head, len(old) - tail


@needs_captures
def test_real_every_edit_changes_only_its_factor(real: tuple[M.Built, M.Sources]) -> None:
    built, _ = real
    hedges, unknown = M.HEDGE_WORDS, ("tbd", "no_estimated_date", "as_released")
    for item in built.items:
        seed, edit = item.seed, item.edit
        if edit is None:
            assert item.fields == seed.fields and item.gold == seed.gold
            continue
        where = (seed.seed_id, edit.factor, edit.level)
        changed = {k for k in M.ITEM_KEYS[1:] if edit.fields[k] != seed.fields[k]}
        old, new = seed.gold.compared(), edit.gold.compared()
        differs = {k for k in old if old[k] != new[k]}
        if edit.factor == "stale":
            assert {"date_of_update"} <= changed <= {"date_of_update", "type_of_update"}, where
            assert edit.fields["type_of_update"] == "Reverified" and differs == {"stale"}, where
            assert edit.gold.end < edit.fields["date_of_update"], where
            continue
        assert (
            not edit.gold.stale and edit.fields["date_of_update"] == seed.fields["date_of_update"]
        ), where
        if edit.factor == "distractor":
            assert changed == {"availability_information"} and differs == {"distractor_roles"}, (
                where
            )
            added = edit.fields["availability_information"]
            assert added == f"{edit.inserted}. {seed.fields['availability_information']}".strip(), (
                where
            )
            assert edit.gold.distractor_roles == (M.DISTRACTOR_ROLE[edit.level],), where
            continue
        if edit.factor == "silent":
            assert changed and changed <= set(M.TEXT_FIELDS), where
            assert (
                new
                == M.Gold(
                    "none", abstain_reason="no_statement", certainty="no_statement"
                ).compared()
            )
            for name in changed:  # words are only taken away
                left = Counter(re.findall(r"\w+", edit.fields[name].lower()))
                assert not left - Counter(re.findall(r"\w+", seed.fields[name].lower())), where
            continue
        assert changed == {seed.name}, where  # one text field, and only around the target
        low, high = changed_region(seed.text, edit.fields[seed.name])
        sentence, _ = M.units_at(seed.text, seed.span[0])
        if edit.factor in ("surface_form", "granularity"):
            # inside the time expression (a space next to it may be shared by both texts)
            assert seed.span[0] <= low <= high <= seed.span[1] + 1, where
            assert differs <= ({"interval"} if edit.factor == "granularity" else set()), where
            assert (edit.level == "timeframe") == (edit.factor == "granularity" and not differs), (
                where
            )
        elif edit.level in hedges:
            assert sentence[0] <= low and high <= seed.span[0], where  # before the time
            assert differs <= {"certainty"} and edit.gold.certainty == "estimated", where
            assert edit.level in edit.fields[seed.name].lower(), where
        else:
            assert edit.level in unknown and sentence[0] <= low and high <= sentence[1], where
            assert high <= seed.span[1] or edit.level != "tbd", where
            assert edit.gold.statement_type == seed.gold.statement_type, where
            assert (edit.gold.abstain, edit.gold.certainty) == (True, "undetermined"), where
            assert edit.gold.abstain_reason == ("no_date" if edit.level == "as_released" else "tbd")
            assert (
                differs == {"interval", "abstain_reason", "certainty"}
                and not edit.gold.distractor_roles
            )


@needs_captures
def test_real_gold_against_the_frozen_rule_reader(real: tuple[M.Built, M.Sources]) -> None:
    """The cross-check: where the two differ, the reason is a mismatch the guide lists."""
    built, _ = real
    assert built.check == M.rule_check(built.items)
    assert all(row["reason"] != "unexplained" for row in built.check), built.check[:5]
    assert len({row["item_id"] for row in built.check}) <= 0.02 * len(built.items)
    for item in built.items:
        if item.edit is None:  # the seed's gold is the rule reading of the real statement
            row = S.check_events(real[1].events).set_index("event_id").loc[item.seed.event_id]
            assert item.gold == M.rule_gold(
                row["statement_text"], date.fromisoformat(row["event_date"])
            )


@needs_captures
def test_real_no_real_name_in_any_item(real: tuple[M.Built, M.Sources]) -> None:
    built, sources = real
    events = S.check_events(sources.events).set_index("event_id")
    lexicon = built.lexicon
    stems = {name.lower() for name in (*M.fictitious_names("drug"), *M.fictitious_names("company"))}
    corpus_words: set[str] = set()
    for column in (
        "generic_name",
        "company_name",
        "presentation",
        "availability_text",
        "related_text",
    ):
        for text in events[column].unique():
            corpus_words |= M.words_of(text)
    used = set()
    for item in built.items:
        record = item.record()
        assert M.real_name_hits(record, lexicon) == [], item.item_id
        row = events.loc[item.seed.event_id]
        whole = " ".join(str(record[k]) for k in M.ITEM_KEYS[1:]).lower()
        own = {w for name in (row["generic_name"], row["company_name"]) for w in M.words_of(name)}
        own = {w for w in own if len(w) > 3 and w not in M.NAME_VOCABULARY and w in lexicon.words}
        assert not {w for w in own if re.search(rf"(?<![a-z]){w}(?![a-z])", whole)}, item.item_id
        assert (
            C.norm_text(row["generic_name"]) not in whole
            and C.norm_text(row["company_name"]) not in whole
        )
        assert not [m.group() for m in M.ndc_matches(whole) if m.group() in lexicon.ndcs]
        assert not re.search(r"@(?!\w+\.example)", whole) and "http" not in whole
        drug, company = record["generic_name"].split()[0], record["company_name"].split()[0]
        assert drug in M.fictitious_names("drug") and company in M.fictitious_names("company")
        used |= {drug.lower(), company.lower()}
    assert used <= stems and not used & corpus_words  # no invented name is a word of the corpus
    by_seed = {
        i.seed.seed_id: (i.fields["generic_name"], i.fields["company_name"]) for i in built.items
    }
    assert len(set(by_seed.values())) == len({d for d, _ in by_seed.values()}) == len(by_seed)


@needs_captures
def test_real_no_edit_reads_like_a_statement_read_elsewhere(
    real: tuple[M.Built, M.Sources],
) -> None:
    """No edit has the whole text of a statement of the labelling samples, the in-context pool,
    the dev prompt items or Appendix A. A seed may (the seed list is drawn by the guide's own
    rule), and then its stale item does; those seeds are few and are counted."""
    built, sources = real
    assert len(sources.reserved) > 100
    own = set(built.reserved_seeds)
    assert len(own) <= 5 and own <= {i.seed.seed_id for i in built.items}
    events = S.check_events(sources.events)
    labelled: set[str] = set()
    for name in S.FIRST_SAMPLES:
        labelled |= {r["statement_group_id"] for r in M.read_csv(M.SAMPLES / f"sample_{name}.csv")}
    read_by_people = M.reserved_texts(events, labelled)
    assert read_by_people and read_by_people <= sources.reserved
    for item in built.items:
        assert not M.is_reserved(item.fields, read_by_people), item.item_id  # seeds included
        if M.is_reserved(item.fields, sources.reserved):
            assert item.seed.seed_id in own and item.factor in ("seed", "stale"), item.item_id


@needs_captures
def test_real_attested_forms_occur_in_train_period_notices(real: tuple[M.Built, M.Sources]) -> None:
    built, sources = real
    events = S.check_events(sources.events).set_index("event_id")
    for item in built.items:
        edit = item.edit
        if edit is None or edit.factor in ("stale", "silent"):
            assert edit is None or (edit.attested is None and edit.inserted == "")
            continue
        attested, where = edit.attested, (item.item_id, edit.factor, edit.level)
        assert attested is not None and edit.inserted and edit.form, where
        notice = events.loc[attested.event_id]
        assert notice["event_date"] < "2023-01-01", where  # a train-period notice
        assert notice["statement_group_id"] not in sources.excluded, where  # not a labelled one
        assert attested.text in (notice["availability_text"], notice["related_text"]), where
        spans = M.sentences(attested.text)
        if attested.scope == "sentence":
            found = {M.mask(attested.text[a:b]) for a, b in spans}
        elif attested.scope == "phrase":
            found = {
                M.mask(attested.text[a:b]) for s in spans for a, b in M.phrases(attested.text, *s)
            }
        else:  # the writing is the time of a delivery or a recovery in that notice
            times = M.stated_times(
                notice["availability_text"],
                notice["related_text"],
                date.fromisoformat(notice["event_date"]),
            )
            found = {form for form, text in times if text == attested.text}
        assert edit.form in found, where  # the wording is there, months and numbers apart
        assert attested.event_id != item.seed.event_id, where  # never the seed's own notice
        name = "availability_information" if edit.factor == "distractor" else item.seed.name
        assert edit.inserted.lower() in edit.fields[name].lower(), where
        if attested.scope == "form":
            assert edit.factor in ("surface_form", "granularity"), where
            assert edit.form in M.mask(edit.inserted), where
        else:
            assert M.mask(edit.inserted) in edit.form, where
    scopes = Counter(i.edit.attested.scope for i in built.items if i.edit and i.edit.attested)
    assert set(scopes) == set(M.SCOPES)
    assert all(i.edit.attested.scope == "sentence" for i in built.items if i.factor == "distractor")
    assert all(i.edit.attested.scope != "form" for i in built.items if i.factor == "certainty")


@needs_captures
def test_real_audit_sample_strata_caps_and_planted_items(real: tuple[M.Built, M.Sources]) -> None:
    built, _ = real
    gold = [{k: str(v) for k, v in item.gold_row().items()} for item in built.items]
    key, strata = M.draw_audit(gold)
    check_draw(key, strata, gold)
    assert sorted(s["quota"] for s in strata) == [16, 16, 17, 17, 17, 17]
    assert all(s["drawn"] == s["quota"] for s in strata)
    disk = M.OnDisk({i.item_id: i.record() for i in built.items}, gold, {M.ITEMS_FILE: "0" * 64})
    sheets = M.build_sheets(key, disk, M.GUIDE.read_text(encoding="utf-8"))
    planted = {r["pair_id"] for r in key if r["planted"]}
    for auditor in M.AUDITORS:
        _, rows = S.parse_sheet(sheets[f"pairs_{auditor}.csv"])
        assert len(rows) == 60 and sum(r["pair_id"] in planted for r in rows) == 5
        assert max(Counter(r["seed_id"] for r in rows).values()) <= M.MAX_PER_SEED
        assert "planted" not in sheets[f"pairs_{auditor}.csv"].lower()
        assert "planted" not in sheets[f"pairs_{auditor}_items.txt"].lower()
        shapes = Counter(
            tuple(bool(r[c]) for c in M.SHEET_COLUMNS) for r in rows if r["pair_id"] not in planted
        )
        assert all(
            tuple(bool(r[c]) for c in M.SHEET_COLUMNS) in shapes
            for r in rows
            if r["pair_id"] in planted
        )


@needs_captures
def test_real_files_on_disk_are_up_to_date(real: tuple[M.Built, M.Sources]) -> None:
    """The files under ``analysis/coling/out/e5`` are what the sources give now."""
    if not (REAL_OUT / M.MANIFEST_FILE).is_file():
        pytest.skip("generate has not been run")
    built, sources = real
    files, _ = M.generate_files(built, sources)
    assert M.stale_files(REAL_OUT, files) == []
    counts = json.loads((REAL_OUT / M.COUNTS_FILE).read_text())
    assert counts["items"] == len(read.load_items(REAL_OUT / M.ITEMS_FILE))
