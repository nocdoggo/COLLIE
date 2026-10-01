"""Tests for the dataset builder (``dataset.py``).

Everything runs on a small synthetic events table, with outcomes written by hand for its
train-period events and passed through ``corpus.add_group_outcomes``. Covered: the seeded draw
and the proportional quotas; the display row (an at-risk member, never an available one, the same
whatever the order of the rows); the four splits; the stated end, the stale flag, the analysis
sets and the horizons; eligibility at the boundary of the last capture, decided without any
outcome; the delayed-entry flag and its boundary; horizon events, the capped time-to-recovery
target and the three statement-level brackets; a train statement at risk with no outcome row is
refused; sealing (an outcome table with test-period rows is refused, a corpus in memory gives its
train rows only, no outcome cell or value of a test-period statement reaches any output, and the
mix of horizon events is tabulated for train rows only); the eligible list, its subsets, the
guide's examples, the harness's fixed test item and the first-draw lists that the reference check
leaves out; the item files (schema of the reading harness, the same fields as the annotation
sheets, probe items without a stated end, form, revision bucket or text); the lists (display-row
outcome, no late statement); the counts report; and the command line (reproducible bytes,
``--check``, refusal of the sealed folder).

The last four tests read the files in the repository and are skipped when they are absent.
``test_outputs_are_up_to_date`` fails until the dataset command is rerun after any change to
``dataset.py``, ``forms.py``, ``rules.py``, the open tables, the guide's Appendix A or the
first-draw lists.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_dataset.py -q -p no:cacheprovider
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from analysis.coling import corpus as C
from analysis.coling import dataset as D
from analysis.coling import forms as F

DAYS = (
    "2019-10-20",
    "2020-03-01",
    "2020-04-15",
    "2020-06-01",
    "2021-02-01",
    "2021-03-15",
    "2022-10-06",
    "2023-01-13",
    "2024-01-10",
    "2025-06-01",
    "2026-09-26",
)
LAST = date(2026, 9, 26)
IDENTITY = {name: name for name in F.FORM_NAMES}
GUIDE = """# Guide

## Appendix A. Statements excluded from every sample

| Generic | Company | Statement date |
|---|---|---|
| Drug S11 | Acme Pharma | 2020-02-12 |

## Appendix B. Other
"""


def event(
    event_id: str,
    group: str,
    day: str,
    text: str,
    seen: str,
    *,
    listing: str = "shortage",
    status: str = "current",
    availability: str = "unavailable",
    revision: int = 0,
    generic: str | None = None,
    posted: str = "01/15/2019",
) -> dict[str, str]:
    return {
        "event_id": event_id,
        "statement_group_id": group,
        "thread_id": "T" + event_id[1:],
        "generic_id": (generic or f"drug {group.lower()}").lower(),
        "episode_id": "" if status != "current" else f"{group[0].lower()}@2019-10-20",
        "listing": listing,
        "period": "train" if day < "2023-01-01" else "test",
        "event_date": day,
        "first_seen_date": seen,
        "days_capture_after_event": str((date.fromisoformat(seen) - date.fromisoformat(day)).days),
        "left_truncated": "False",
        "type_of_update": "revised",
        "revision_index": str(revision),
        "generic_name": generic or f"Drug {group}",
        "company_name": "Acme Pharma",
        "presentation": f"10 mL vial ({event_id})",
        "status_at_statement": status,
        "availability_class": availability,
        "availability_text": "Backordered" if availability == "unavailable" else "Available",
        "related_text": text,
        "statement_text": text,
        "reason_for_shortage": "Demand increase for the drug",
        "therapeutic_category": "Anesthesia",
        "initial_posting_date": posted,
    }


def synthetic_events() -> pd.DataFrame:
    may = "Estimated Recovery: May 2020"
    rows = [
        # S01 fit, month and year: three presentations, the third is available
        event("E011", "S01", "2020-02-10", may, "2020-03-01", revision=2),
        event("E012", "S01", "2020-02-10", may, "2020-03-01", revision=1),
        event("E013", "S01", "2020-02-10", may, "2020-03-01", availability="available"),
        # S02 fit, TBD; S03 fit, silent; S04 fit, stale at issue; S05 fit, no time given
        event("E021", "S02", "2020-02-20", "Estimated Recovery: TBD", "2020-03-01"),
        event("E031", "S03", "2020-05-20", "On backorder", "2020-06-01"),
        event(
            "E041", "S04", "2020-05-25", "Backordered. Next release February 2020.", "2020-06-01"
        ),
        event(
            "E051",
            "S05",
            "2020-05-28",
            "Product will be made available as it is released",
            "2020-06-01",
        ),
        # S06 fit, dated but Resolved at first sight; S09 fit, the discontinuation listing
        event(
            "E061",
            "S06",
            "2019-10-01",
            "Estimated Recovery: December 2019",
            "2019-10-20",
            status="resolved",
        ),
        event(
            "E091",
            "S09",
            "2020-02-01",
            "To be discontinued on or near March 2020",
            "2020-03-01",
            listing="discontinuation",
            status="discontinued",
        ),
        # S07 dev, first captured after its stated period; S08 dev, first captured in 2023
        event("E071", "S07", "2021-01-05", "Estimated Recovery: January 2021", "2021-02-01"),
        event("E081", "S08", "2022-12-20", "Estimated Recovery: March 2023", "2023-01-13"),
        # S10 dev, quarter; S11 and S12 fit
        event("E101", "S10", "2021-01-10", "Estimated Recovery: Q1 2021", "2021-02-01"),
        event("E111", "S11", "2020-02-12", "Estimated Recovery: March", "2020-03-01"),
        event("E121", "S12", "2020-02-14", "Estimated Recovery: February 2020", "2020-03-01"),
        # test split
        event("E201", "T01", "2023-05-01", "Estimated Recovery: July 2023", "2024-01-10"),
        event("E202", "T01", "2023-05-01", "Estimated Recovery: July 2023", "2024-01-10"),
        event("E211", "T02", "2025-05-20", "Estimated Recovery: June 2026", "2025-06-01"),
        event("E221", "T03", "2025-05-20", "Estimated Recovery: June 28, 2026", "2025-06-01"),
        event("E231", "T04", "2024-01-05", "Estimated Recovery: TBD", "2024-01-10"),
        event("E241", "T05", "2024-01-06", "On backorder", "2024-01-10"),
        event("E251", "T06", "2025-05-25", "Next release April 2025.", "2025-06-01"),
        event(
            "E261",
            "T07",
            "2024-01-07",
            "Estimated Recovery: March 2024",
            "2024-01-10",
            availability="available",
        ),
        # the text of S11 again, on a test date (same generic and company)
        event(
            "E271",
            "T08",
            "2023-02-14",
            "Estimated Recovery: March",
            "2024-01-10",
            generic="Drug S11",
        ),
        event(
            "E272",
            "T09",
            "2024-01-02",
            "Estimated Recovery: February 2024",
            "2024-01-10",
            posted="12/03/2108",
        ),
        # late split
        event("E301", "L01", "2026-02-01", "Estimated Recovery: March 2026", "2026-09-26"),
        event("E311", "L02", "2026-08-01", "Estimated Recovery: TBD", "2026-09-26"),
    ]
    return pd.DataFrame(rows)


def outcome_of(row: dict, kind: str, lower: str = "", upper: str = "", reason: str = "") -> dict:
    """An outcome row, as ``corpus.py`` derives one, for the event ``row``."""
    rec = {
        "event_id": row["event_id"],
        "event_date": row["event_date"],
        "period": row["period"],
        "statement_group_id": row["statement_group_id"],
        "followup_end_date": "2022-10-06" if row["period"] == "train" else "2026-09-26",
    }
    for d in C.DEFINITIONS:
        rec.update(
            {
                f"at_risk_{d}": kind != "not_at_risk",
                f"outcome_{d}": kind,
                f"censor_reason_{d}": reason,
                f"lower_date_{d}": lower,
                f"upper_date_{d}": upper,
                f"observable31_{d}": False,
            }
        )
    return rec


def outcome(event_id: str, kind: str, lower: str = "", upper: str = "", reason: str = "") -> dict:
    events = synthetic_events().set_index("event_id", drop=False)
    return outcome_of(events.loc[event_id].to_dict(), kind, lower, upper, reason)


TRAIN_OUTCOMES = [
    outcome("E011", "recovered", "2020-03-01", "2020-06-01"),
    outcome("E012", "censored", "2022-10-06", reason="end_of_train"),
    outcome("E013", "not_at_risk"),
    outcome("E021", "recovered", "2020-03-01", "2020-06-01"),
    outcome("E031", "discontinued", "2020-06-01", "2021-02-01"),
    outcome("E041", "censored", "2022-10-06", reason="end_of_train"),
    outcome("E051", "recovered", "2020-06-01", "2021-02-01"),
    outcome("E061", "not_at_risk"),
    outcome("E071", "censored", "2022-10-06", reason="end_of_train"),
    outcome("E081", "censored", "2023-01-13", reason="end_of_train"),
    outcome("E101", "recovered", "2021-02-01", "2021-03-15"),
    outcome("E111", "recovered", "2020-03-01", "2020-06-01"),
    outcome("E121", "recovered", "2020-03-01", "2020-04-15"),
]
MARKER = "2024-12-25"  # an upper bound that only the test-period outcome rows below carry
TEST_OUTCOMES = [
    outcome("E201", "recovered", "2024-01-10", MARKER),
    outcome("E202", "recovered", "2024-01-10", MARKER),
    outcome("E211", "recovered", "2025-06-01", MARKER),
    outcome("E301", "censored", "2026-09-26", reason="no_followup"),
]


def outcome_table(rows: list[dict]) -> pd.DataFrame:
    """The rows as ``corpus.py`` writes them and a CSV reads them back."""
    return D.as_text(C.add_group_outcomes(pd.DataFrame(rows)))


def first_sight() -> pd.DataFrame:
    return D.statement_table(synthetic_events(), LAST, IDENTITY).set_index(
        "statement_group_id", drop=False
    )


def full_table() -> pd.DataFrame:
    table = D.attach_outcomes(first_sight().reset_index(drop=True), outcome_table(TRAIN_OUTCOMES))
    return table.set_index("statement_group_id", drop=False)


def inputs(
    outcomes: list[dict] | None = None,
    guide: str = GUIDE,
    first_draw: dict[str, tuple[str, ...]] | None = None,
) -> D.Inputs:
    return D.Inputs(
        events=synthetic_events(),
        outcomes=outcome_table(TRAIN_OUTCOMES if outcomes is None else outcomes),
        days=tuple(date.fromisoformat(d) for d in DAYS),
        examples=tuple(D.guide_examples(guide)),
        source={"events": "synthetic"},
        first_draw=first_draw or {},
    )


# --------------------------------------------------------------------------------------------
# Seeded draws
# --------------------------------------------------------------------------------------------


def test_seeded_order_ignores_the_input_order_and_keeps_places() -> None:
    ids = [f"S{i:03d}" for i in range(40)]
    order = D.seeded_order(ids, "tag")
    assert order == D.seeded_order(reversed(ids), "tag") == D.seeded_order(ids + ids, "tag")
    assert sorted(order) == ids and order != ids
    assert order != D.seeded_order(ids, "another tag")
    assert order != D.seeded_order(ids, "tag", seed=1)
    fewer = [i for i in ids if i != order[3]]
    assert D.seeded_order(fewer, "tag") == [i for i in order if i != order[3]]
    assert D.SEED == 20261001


def test_allocate_is_proportional_with_largest_remainders() -> None:
    assert D.allocate({"2023": 1063, "2024": 931, "2025": 591}, 300) == {
        "2023": 123,
        "2024": 108,
        "2025": 69,
    }
    assert D.allocate({"a": 1, "b": 1, "c": 1}, 2) == {"a": 1, "b": 1, "c": 0}
    assert D.allocate({"a": 5, "b": 5}, 3) == {"a": 2, "b": 1}
    assert D.allocate({"a": 2, "b": 3}, 10) == {"a": 2, "b": 3}
    assert D.allocate({}, 5) == {}


def test_draw_subset_is_stratified_seeded_and_nested_in_the_pool() -> None:
    pool = {f"S{i:04d}": str(2023 + i % 3) for i in range(900)}
    probe = D.SUBSETS[0]
    drawn = D.draw_subset(pool, probe)
    assert drawn == sorted(drawn) == D.draw_subset(dict(reversed(pool.items())), probe)
    assert len(drawn) == len(set(drawn)) == 300 and set(drawn) <= set(pool)
    assert {y: sum(pool[i] == y for i in drawn) for y in ("2023", "2024", "2025")} == {
        "2023": 100,
        "2024": 100,
        "2025": 100,
    }
    flat = D.Subset("check", 100, "tag", False, "")
    assert len(D.draw_subset(pool, flat)) == 100 and not flat.skip_first_draw
    assert D.draw_subset({"S1": "2023", "S2": "2024"}, probe) == ["S1", "S2"]
    names = [s.name for s in D.SUBSETS]
    assert names == ["probe", "samples20", "paraphrase", "twobytwo", "reference_check"]
    assert [s.size for s in D.SUBSETS] == [300, 300, 200, 300, 100]
    assert len({s.tag for s in D.SUBSETS}) == len(D.SUBSETS)
    assert not any(s.tag.startswith(D.DISPLAY_TAG) for s in D.SUBSETS)
    assert [s.name for s in D.SUBSETS if s.skip_first_draw] == ["reference_check"]


# --------------------------------------------------------------------------------------------
# Display row, splits, reading, eligibility
# --------------------------------------------------------------------------------------------


def test_display_row_is_a_seeded_at_risk_member() -> None:
    ev = D.member_flags(synthetic_events())
    shown = D.display_rows(ev)
    # in the seeded order E013 comes first, but it is available: the draw is among E011 and E012
    assert D.seeded_order(["E011", "E012", "E013"], D.DISPLAY_TAG + "S01")[0] == "E013"
    assert shown.loc["S01", "event_id"] == "E011"
    assert (
        shown.loc["T01", "event_id"] == D.seeded_order(["E201", "E202"], D.DISPLAY_TAG + "T01")[0]
    )
    # no member at risk: the smallest event id
    assert shown.loc["S06", "event_id"] == "E061" and shown.loc["S09", "event_id"] == "E091"
    shuffled = ev.sample(frac=1, random_state=3)
    assert D.display_rows(shuffled)["event_id"].to_dict() == shown["event_id"].to_dict()
    without = ev[ev["statement_group_id"] != "T01"]
    assert D.display_rows(without).loc["S01", "event_id"] == "E011"


def test_display_row_is_the_one_on_the_annotation_sheets() -> None:
    sample = pytest.importorskip("analysis.coling.audit_sample")
    events = synthetic_events()
    sheets = sample.display_events(events).set_index("statement_group_id")["event_id"]
    shown = D.display_rows(D.member_flags(events))["event_id"]
    assert sheets.to_dict() == shown.to_dict(), "dataset.py and audit_sample.py show other rows"


def test_display_row_fields_are_those_of_the_shown_presentation() -> None:
    st = first_sight()
    row = st.loc["S01"]
    assert row[["event_id", "thread_id", "presentation"]].tolist() == [
        "E011",
        "T011",
        "10 mL vial (E011)",
    ]
    assert row[["n_presentations", "n_at_risk_A", "n_at_risk_B"]].tolist() == ["3", "3", "2"]
    assert row[["revision_index", "revision"]].tolist() == ["2", "third or later"]
    assert row[["initial_posting_date", "listing_age_days"]].tolist() == ["2019-01-15", "391"]
    assert st.loc["S02", "revision"] == "first"
    assert [D.revision_bucket(i) for i in (0, "1", 2, 7)] == [
        "first",
        "second",
        "third or later",
        "third or later",
    ]
    # a posting date after the statement is kept as written and gives no age
    assert st.loc["T09", ["initial_posting_date", "listing_age_days"]].tolist() == [
        "2108-12-03",
        "",
    ]
    assert list(st.columns) == list(D.FIRST_SIGHT_COLUMNS)
    assert list(st.index) == sorted(st.index)


def test_splits_and_periods() -> None:
    st = first_sight()
    assert st.loc[["S01", "S07", "S08", "T01", "T02", "L01"], "split"].tolist() == [
        "fit",
        "dev",
        "dev",
        "test",
        "test",
        "late",
    ]
    assert st.loc[["S08", "T01", "L01"], "period"].tolist() == ["train", "test", "test"]
    assert st.loc["S08", "first_seen_in_test_period"] == "True"
    assert (st.loc[st["period"] == "test", "first_seen_in_test_period"] == "False").all()


def test_reading_stated_end_stale_and_analysis_sets() -> None:
    st = first_sight()
    assert st.loc[
        "S01", ["form", "dated", "stated_start", "stated_end", "stale_at_issue"]
    ].tolist() == [
        "month_year",
        "True",
        "2020-05-01",
        "2020-05-31",
        "False",
    ]
    assert st.loc["S04", ["stated_end", "stale_at_issue", "analysis_set"]].tolist() == [
        "2020-02-29",
        "True",
        "stale",
    ]
    assert st.loc["S02", ["form", "stated_end", "analysis_set", "silent"]].tolist() == [
        "tbd",
        "",
        "tbd",
        "False",
    ]
    assert st.loc["S03", ["form", "analysis_set", "silent"]].tolist() == [
        "silent",
        "silent",
        "True",
    ]
    assert st.loc["S05", ["form", "analysis_set"]].tolist() == ["no_date", "none"]
    # a discontinuation statement has a period in the rule reading, but no stated end here
    assert st.loc["S09", ["form", "stated_end", "analysis_set"]].tolist() == [
        "discontinuation",
        "",
        "",
    ]
    # dated, on the shortage listing, but not at risk under B: in no analysis set
    assert st.loc["S06", ["dated", "at_risk_A", "at_risk_B", "analysis_set"]].tolist() == [
        "True",
        "False",
        "False",
        "",
    ]
    assert st.loc["T07", ["at_risk_A", "at_risk_B", "analysis_set", "eligible"]].tolist() == [
        "True",
        "False",
        "",
        "False",
    ]
    assert set(st["analysis_set"]) == {"", *D.ANALYSIS_SETS}
    assert D.analysis_set("quarter", False, True) == "dated"
    assert D.analysis_set("vague", False, True) == "none"
    assert D.analysis_set("month_year", False, False) == ""


def test_horizons_follow_the_reading_harness() -> None:
    from analysis.coling import read as R

    st = first_sight()
    assert st.loc["S01", ["horizon_a", "horizon_b", "horizon_rule"]].tolist() == [
        "2020-05-31",
        "2020-08-29",
        "stated_end",
    ]
    assert st.loc["S02", ["horizon_a", "horizon_b", "horizon_rule"]].tolist() == [
        "2020-05-20",
        "2020-08-18",
        "fallback",
    ]
    assert st.loc["S05", ["horizon_a", "horizon_b", "horizon_rule"]].tolist() == ["", "", ""]
    for gid in ("S01", "S02", "S03", "S04", "T03", "T04"):
        item = R.ReadItem.from_dict(D.item(st.loc[gid].to_dict()))
        a, b, rule = R.horizons(item)
        assert [a.isoformat(), b.isoformat(), rule] == st.loc[
            gid, ["horizon_a", "horizon_b", "horizon_rule"]
        ].tolist()
    assert R.HORIZON_B_OFFSET.days == D.HORIZON_DAYS and R.CAP_DAYS == D.CAP_DAYS
    assert tuple(d.days for d in R.FALLBACK_HORIZONS) == D.FALLBACK_DAYS
    assert D.REVISION_BUCKETS == R.REVISION_BUCKETS


def test_eligibility_stops_at_the_last_capture() -> None:
    st = first_sight()
    # stated end 2026-06-30: 90 days later is 2026-09-28, two days after the last capture
    assert st.loc["T02", ["horizon_b", "horizon_reached", "eligible", "e3_eligible"]].tolist() == [
        "2026-09-28",
        "False",
        "False",
        "False",
    ]
    # stated end 2026-06-28: 90 days later is the last capture day itself
    assert st.loc["T03", ["horizon_b", "horizon_reached", "eligible", "e3_eligible"]].tolist() == [
        "2026-09-26",
        "True",
        "True",
        "True",
    ]
    a_day_earlier = D.statement_table(synthetic_events(), date(2026, 9, 25), IDENTITY)
    a_day_earlier = a_day_earlier.set_index("statement_group_id")
    assert a_day_earlier.loc["T03", "e3_eligible"] == "False"
    assert sorted(st.index[st["e3_eligible"] == "True"]) == ["T01", "T03", "T08", "T09"]
    # TBD, silent and stale test statements are listed, but are not E3 items
    assert st.loc[["T04", "T05", "T06"], "eligible"].tolist() == ["True"] * 3
    assert st.loc[["T04", "T05", "T06"], "e3_eligible"].tolist() == ["False"] * 3
    # late: the same condition, never an E3 item
    assert st.loc["L01", ["eligible", "e3_eligible"]].tolist() == ["True", "False"]
    assert st.loc["L02", ["horizon_b", "eligible"]].tolist() == ["2027-01-28", "False"]
    # train: the captures decide, not the last capture of the archive
    assert st.loc[["S01", "S02", "S03", "S04", "S08"], "eligible"].tolist() == ["True"] * 5
    assert st.loc[["S05", "S06", "S09"], "eligible"].tolist() == ["False"] * 3
    early = D.statement_table(synthetic_events(), date(2019, 1, 1), IDENTITY)
    early = early.set_index("statement_group_id")
    assert early.loc[["S01", "S02", "S03", "S08"], "horizon_reached"].tolist() == ["False"] * 4
    assert early.loc[["S01", "S02", "S03", "S04", "S08"], "eligible"].tolist() == ["True"] * 5
    assert not D.true(early.loc[early["period"] == "test", "e3_eligible"]).any()
    assert early.loc[["T01", "T04", "T05"], "eligible"].tolist() == ["False"] * 3
    assert early.loc["T06", ["analysis_set", "eligible"]].tolist() == ["stale", "True"]


def test_delayed_entry_marks_dated_statements_first_captured_after_the_stated_end() -> None:
    st = first_sight()
    assert st.loc[["S07", "S12", "T01"], "delayed_entry"].tolist() == ["True"] * 3
    assert st.loc[["S01", "S10", "T03"], "delayed_entry"].tolist() == ["False"] * 3
    # stale, TBD and silent statements have no flag
    assert st.loc[["S04", "S02", "S03", "T06"], "delayed_entry"].tolist() == ["False"] * 4
    # first captured on the last day of the stated period: not delayed; a day later: delayed
    rows = [
        event("E501", "S50", "2020-03-20", "Estimated Recovery: April 15, 2020", "2020-04-15"),
        event("E511", "S51", "2020-03-20", "Estimated Recovery: April 14, 2020", "2020-04-15"),
    ]
    edge = D.statement_table(pd.DataFrame(rows), LAST, IDENTITY).set_index("statement_group_id")
    assert edge["stated_end"].to_dict() == {"S50": "2020-04-15", "S51": "2020-04-14"}
    assert edge["delayed_entry"].to_dict() == {"S50": "False", "S51": "True"}


def test_merged_forms_and_labels() -> None:
    merged = {**IDENTITY, "relative": "range", "half_year": "quarter"}
    labels = D.form_labels(merged)
    assert labels["relative"] == labels["range"] == "a relative time or a range"
    assert labels["month_year"] == "a month and year"
    st = D.statement_table(synthetic_events(), LAST)  # the merge computed from these events
    assert set(st["merged_form"]) <= {"month_year", "silent"}
    assert st.set_index("statement_group_id").loc["S10", ["form", "merged_form"]].tolist() == [
        "quarter",
        "month_year",
    ]
    assert D.display_reading_differs(st) == 0


def test_statement_table_needs_its_columns_and_distinct_events() -> None:
    with pytest.raises(ValueError, match="first_seen_date"):
        D.statement_table(synthetic_events().drop(columns="first_seen_date"), LAST)
    twice = pd.concat([synthetic_events(), synthetic_events().head(1)])
    with pytest.raises(ValueError, match="repeats an event_id"):
        D.statement_table(twice, LAST)


# --------------------------------------------------------------------------------------------
# Outcomes on the train period
# --------------------------------------------------------------------------------------------


def test_horizon_event() -> None:
    assert D.horizon_event("recovered", "2020-03-01", "2020-05-31", "2020-05-31") == "yes"
    assert D.horizon_event("recovered", "2020-03-01", "2020-06-01", "2020-05-31") == "undetermined"
    assert D.horizon_event("recovered", "2020-05-31", "2020-06-01", "2020-05-31") == "no"
    assert D.horizon_event("censored", "2020-05-31", "", "2020-05-31") == "no"
    assert D.horizon_event("censored", "2020-05-30", "", "2020-05-31") == "undetermined"
    assert D.horizon_event("discontinued", "2020-03-01", "2020-04-01", "2020-05-31") == "no"
    assert D.horizon_event("discontinued", "2020-03-01", "2021-04-01", "2020-05-31") == "no"
    assert D.horizon_event("not_at_risk", "", "", "2020-05-31") == ""
    assert D.horizon_event("recovered", "2020-03-01", "2020-04-01", "") == ""
    assert D.determined("yes", "no") and not D.determined("no", "undetermined")
    assert not D.determined("", "")


def test_time_target() -> None:
    assert D.time_target("recovered", 20, 112) == {
        "kind": "interval",
        "lower": 20,
        "upper": 112,
        "mid": 66.0,
    }
    assert D.time_target("recovered", 300, 500)["upper"] == 365
    assert D.time_target("recovered", 300, 500)["mid"] == 332.5
    assert D.time_target("recovered", 365, 400)["kind"] == "at_cap"
    assert D.time_target("recovered", -1, 9)["lower"] == 0
    assert D.time_target("discontinued", 12, 40) == {
        "kind": "at_cap",
        "lower": 365,
        "upper": 365,
        "mid": 365,
    }
    assert D.time_target("censored", 500, None)["kind"] == "at_cap"
    assert D.time_target("censored", 120, None) == {
        "kind": "right_censored",
        "lower": 120,
        "upper": "",
        "mid": "",
    }
    assert [D.number(v) for v in ("", 66.0, 332.5, 365)] == ["", "66", "332.5", "365"]


def test_any_bracket_takes_the_minimum() -> None:
    rec, cen = ("recovered", "2020-03-01", "2020-06-01"), ("censored", "2022-10-06", "")
    late = ("recovered", "2020-04-15", "2021-02-01")
    disc = ("discontinued", "2020-03-01", "2020-04-15")
    assert D.any_bracket([rec, cen]) == rec
    assert D.any_bracket([late, rec]) == ("recovered", "2020-03-01", "2020-06-01")
    assert D.any_bracket([cen, ("censored", "2020-06-01", "")]) == ("censored", "2020-06-01", "")
    assert D.any_bracket([disc, cen]) == cen
    assert D.any_bracket([disc, ("discontinued", "2020-06-01", "2021-02-01")]) == (
        "discontinued",
        "2020-06-01",
        "2021-02-01",
    )
    assert D.any_bracket([("not_at_risk", "", ""), rec]) == rec
    assert D.any_bracket([("not_at_risk", "", "")]) == ("not_at_risk", "", "")


def test_outcomes_of_a_statement_with_several_presentations() -> None:
    row = full_table().loc["S01"]
    # primary: the display row E011, recovered between 2020-03-01 and 2020-06-01
    assert row[["outcome", "lower_date", "upper_date", "lower_days", "upper_days"]].tolist() == [
        "recovered",
        "2020-03-01",
        "2020-06-01",
        "20",
        "112",
    ]
    assert row[["E_end", "E_end90", "scoreable"]].tolist() == ["undetermined", "yes", "False"]
    # all covered presentations: E012 is still open at the train horizon
    assert row[["outcome_all", "lower_date_all", "upper_date_all"]].tolist() == [
        "censored",
        "2022-10-06",
        "",
    ]
    assert row[["E_end_all", "E_end90_all", "scoreable_all"]].tolist() == ["no", "no", "True"]
    # any covered presentation: the first recovery
    assert row[["outcome_any", "lower_date_any", "upper_date_any"]].tolist() == [
        "recovered",
        "2020-03-01",
        "2020-06-01",
    ]
    assert row[["E_end_any", "E_end90_any", "scoreable_any"]].tolist() == [
        "undetermined",
        "yes",
        "False",
    ]
    assert row[["ttr_kind", "ttr_lower_days", "ttr_upper_days", "ttr_mid_days"]].tolist() == [
        "interval",
        "20",
        "112",
        "66",
    ]
    assert row[["E_90", "E_180", "scoreable_fallback"]].tolist() == ["", "", ""]


def test_horizon_events_scoreable_and_targets_by_analysis_set() -> None:
    table = full_table()
    events = table[["E_end", "E_end90", "scoreable"]]
    assert events.loc["S07"].tolist() == ["no", "no", "True"]
    assert events.loc["S12"].tolist() == ["no", "yes", "True"]
    assert events.loc["S10"].tolist() == ["yes", "yes", "True"]
    assert events.loc["S11"].tolist() == ["undetermined", "yes", "False"]
    # first captured in 2023: censored there, nothing determined for a period ending later
    assert table.loc["S08", ["outcome", "censor_reason", "lower_date"]].tolist() == [
        "censored",
        "end_of_train",
        "2023-01-13",
    ]
    assert events.loc["S08"].tolist() == ["undetermined", "undetermined", "False"]
    # stale, no-date and not-at-risk statements have no horizon event
    for gid in ("S04", "S05", "S06", "S09"):
        assert events.loc[gid].tolist() == ["", "", ""]
    # TBD and silent: 90 and 180 days after the statement date
    fallback = table[["E_90", "E_180", "scoreable_fallback"]]
    assert fallback.loc["S02"].tolist() == ["undetermined", "yes", "False"]
    assert fallback.loc["S03"].tolist() == ["no", "no", "True"]
    assert events.loc["S02"].tolist() == ["", "", ""]
    # the target is defined for every at-risk statement, whatever its form
    target = table[["ttr_kind", "ttr_lower_days", "ttr_upper_days", "ttr_mid_days"]]
    assert target.loc["S03"].tolist() == ["at_cap", "365", "365", "365"]
    assert target.loc["S04"].tolist() == ["at_cap", "365", "365", "365"]
    assert target.loc["S05"].tolist() == ["interval", "4", "249", "126.5"]
    assert target.loc["S08"].tolist() == ["right_censored", "24", "", ""]
    assert target.loc["S06"].tolist() == ["", "", "", ""]
    assert table.loc["S06", "outcome"] == "not_at_risk"
    assert table.loc["S09", list(D.OUTCOME_COLUMNS)].tolist() == [""] * len(D.OUTCOME_COLUMNS)
    assert list(table.columns) == list(D.COLUMNS)


def test_attach_outcomes_refuses_tables_from_different_builds() -> None:
    rows = [
        r if r["event_id"] != "E011" else outcome("E011", "not_at_risk") for r in TRAIN_OUTCOMES
    ]
    with pytest.raises(ValueError, match="not from the same build"):
        D.attach_outcomes(first_sight().reset_index(drop=True), outcome_table(rows))


def test_build_refuses_a_train_statement_at_risk_with_no_outcome_row() -> None:
    fewer = [r for r in TRAIN_OUTCOMES if r["event_id"] != "E071"]
    with pytest.raises(ValueError, match=r"1 train statements at risk have no outcome row.*S07"):
        D.build(inputs(fewer))
    # a statement that is not at risk needs none (S09 is on the discontinuation listing)
    assert "E091" not in {r["event_id"] for r in TRAIN_OUTCOMES}
    D.require_train_outcomes(full_table())


# --------------------------------------------------------------------------------------------
# Sealing
# --------------------------------------------------------------------------------------------


def test_scoreable_counts_break_nothing_down_by_outcome() -> None:
    table = full_table()
    dated = table[(table["split"] == "dev") & (table["analysis_set"] == "dated")]
    assert D.scoreable_counts(dated) == {
        "statements": 3,
        "episodes": 1,
        "scoreable": 2,
        "scoreable_episodes": 1,
        "with_a_horizon_event_undetermined": 1,
    }
    assert all(isinstance(v, int) for v in D.scoreable_counts(dated).values())
    with_mix = D.train_outcome_counts(dated)
    assert set(with_mix) - set(D.scoreable_counts(dated)) == {"scoreable_by_E_end_and_E_end90"}
    # the mix is never tabulated for rows of the test period
    later = table[table["analysis_set"] == "dated"]
    assert (later["period"] == "test").any()
    with pytest.raises(ValueError, match="train-period statements only"):
        D.train_outcome_counts(later)


def test_require_train_refuses_test_period_rows() -> None:
    assert len(D.require_train(outcome_table(TRAIN_OUTCOMES))) == len(TRAIN_OUTCOMES)
    with pytest.raises(ValueError, match="train rows only"):
        D.require_train(outcome_table(TRAIN_OUTCOMES + TEST_OUTCOMES))
    relabelled = outcome_table(TRAIN_OUTCOMES + TEST_OUTCOMES).assign(period="train")
    with pytest.raises(ValueError, match="train rows only"):
        D.require_train(relabelled)
    with pytest.raises(ValueError, match="lacks"):
        D.require_train(outcome_table(TRAIN_OUTCOMES).drop(columns="followup_end_date"))
    with pytest.raises(ValueError, match="train rows only"):
        D.build(inputs(TRAIN_OUTCOMES + TEST_OUTCOMES))


def test_assert_sealed_stops_a_filled_test_row() -> None:
    table = full_table().reset_index(drop=True)
    D.assert_sealed(table)
    table.loc[table["statement_group_id"] == "T01", "outcome"] = "recovered"
    with pytest.raises(ValueError, match="outcome"):
        D.assert_sealed(table)


def test_no_test_period_outcome_reaches_any_output(tmp_path: Path) -> None:
    corpus = SimpleNamespace(
        events=synthetic_events(),
        outcomes=C.add_group_outcomes(pd.DataFrame(TRAIN_OUTCOMES + TEST_OUTCOMES)),
        captures=SimpleNamespace(dates=[pd.Timestamp(d) for d in DAYS]),
        train_uncensored=None,
    )
    guide = tmp_path / "guide.md"
    guide.write_text("# a guide with no Appendix A\n", encoding="utf-8")
    built = D.build(D.corpus_input(corpus, {"events": "in memory"}, guide))
    table = built.table
    sealed = table[table["period"] != "train"]
    assert len(sealed) == 11 and set(sealed["split"]) == {"test", "late"}
    assert (sealed[list(D.OUTCOME_COLUMNS)] == "").all().all()
    train = table[(table["period"] == "train") & (table["listing"] == "shortage")]
    assert (train["outcome"] != "").all()
    written = [gzip.decompress(built.statements_gz).decode(), built.eligible_csv, built.report_text]
    assert all(MARKER not in text for text in written)
    assert "no_followup" not in written[0]
    # the same outputs as a build that was never given the test-period rows
    same = D.build(D.Inputs(**{**inputs(guide="").__dict__, "source": {"events": "in memory"}}))
    assert built.statements_gz == same.statements_gz and built.eligible_csv == same.eligible_csv
    assert built.report_text == same.report_text
    # outcomes are counted for fit and dev only
    assert list(built.report["train"]) == list(D.TRAIN_SPLITS)
    assert set(D.OUTCOME_COLUMNS).isdisjoint(D.FIRST_SIGHT_COLUMNS)
    assert set(D.OUTCOME_COLUMNS).isdisjoint(D.ELIGIBLE_COLUMNS)


def test_eligibility_and_display_rows_do_not_depend_on_outcomes() -> None:
    flipped = [
        outcome(r["event_id"], "not_at_risk")
        if r["outcome_B"] == "not_at_risk"
        else outcome(r["event_id"], "censored", "2022-10-06", reason="end_of_train")
        for r in TRAIN_OUTCOMES
    ]
    a, b = D.build(inputs()), D.build(inputs(flipped))
    assert a.eligible_csv == b.eligible_csv
    first = list(D.FIRST_SIGHT_COLUMNS)
    assert a.table[first].equals(b.table[first])
    assert not a.table["outcome"].equals(b.table["outcome"])
    for key in ("e3", "eligible", "secondary_lists_test", "subsets", "statements", "events"):
        assert a.report[key] == b.report[key]


def test_the_sealed_folder_is_refused(tmp_path: Path) -> None:
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    with pytest.raises(SystemExit, match="sealed"):
        D.not_sealed(sealed / "outcomes_test.csv.gz")
    with pytest.raises(SystemExit, match="sealed"):
        D.main(["--outcomes", str(sealed / "outcomes_test.csv.gz"), "--out", str(tmp_path)])
    with pytest.raises(SystemExit, match="sealed"):
        D.main(["--out", str(sealed)])
    with pytest.raises(SystemExit, match="sealed"):
        D.main(["--samples", str(sealed), "--out", str(tmp_path)])
    assert D.not_sealed(tmp_path / "out") == tmp_path / "out"


# --------------------------------------------------------------------------------------------
# The eligible list, its subsets and the guide's examples
# --------------------------------------------------------------------------------------------


def test_guide_examples_and_the_statements_they_exclude() -> None:
    examples = D.guide_examples(GUIDE)
    assert examples == [("drug s11", "acme pharma", "2020-02-12")]
    assert D.guide_examples("# no appendix") == []
    two = GUIDE.replace("2020-02-12 |", "2020-02-12 and 2021-01-05 |")
    assert [e[2] for e in D.guide_examples(two)] == ["2020-02-12", "2021-01-05"]
    # S11 itself, and T08: the same generic, company and text on another date
    assert D.example_statements(synthetic_events(), examples) == {"S11", "T08"}
    assert D.example_statements(synthetic_events(), []) == set()
    assert D.unmatched_examples(synthetic_events(), examples) == 0
    mistyped = [*examples, ("drug s11", "acme pharma", "2020-02-13")]
    assert D.unmatched_examples(synthetic_events(), mistyped) == 1
    assert D.build(inputs()).report["inputs"]["guide_examples_matching_no_event"] == 0


def test_eligible_list_is_sorted_and_its_subsets_skip_guide_examples() -> None:
    built = D.build(inputs())
    listed = built.eligible
    assert list(listed.columns) == list(D.ELIGIBLE_COLUMNS)
    assert listed["statement_group_id"].tolist() == ["T01", "T03", "T08", "T09"]
    assert listed.set_index("statement_group_id").loc["T03", ["form", "stated_end"]].tolist() == [
        "exact_day",
        "2026-06-28",
    ]
    # the pool is smaller than every subset: all of it is taken, except the guide's example
    for subset in D.SUBSETS:
        assert listed[subset.name].tolist() == [1, 1, 0, 1]
    assert built.report["subsets"]["pool"] == 3
    assert built.report["subsets"]["left_out_as_guide_examples"] == 1
    assert built.report["subsets"]["probe"]["seed"] == D.SEED
    assert built.report["subsets"]["probe"]["by_year"] == {"2023": 1, "2024": 1, "2025": 1}
    no_guide = D.build(inputs(guide=""))
    assert no_guide.eligible["probe"].tolist() == [1, 1, 1, 1]
    assert built.eligible_csv.splitlines()[0] == ",".join(D.ELIGIBLE_COLUMNS)


def test_fixed_test_item_of_the_harness_is_left_out_of_every_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from analysis.coling import read as R

    fixed = R.CANARY_ITEM
    assert D.fixed_item_examples(synthetic_events()) == set()
    assert D.build(inputs()).report["inputs"]["fixed_test_item_statements"] == 0
    events = synthetic_events()
    # the statement the fixed item is built on, its text again on a later date, and the same
    # text from another company on another date
    base = event("E401", "S40", fixed.date_of_update, "Expected recovery April 2020", "2020-04-15")
    base |= {"generic_name": fixed.generic_name, "company_name": "Teva Pharmaceuticals"}
    again = event("E402", "T40", "2023-03-01", "Expected recovery April 2020", "2024-01-10")
    again |= {"generic_name": fixed.generic_name, "company_name": "Teva Pharmaceuticals"}
    other = event("E403", "S41", "2020-03-18", "Expected recovery April 2020", "2020-04-15")
    other |= {"generic_name": fixed.generic_name, "company_name": "Another Company"}
    events = pd.concat([events, pd.DataFrame([base, again, other])], ignore_index=True)
    key = (C.norm_text(fixed.generic_name), "teva pharmaceuticals", fixed.date_of_update)
    assert D.fixed_item_examples(events) == {key}
    assert D.example_statements(events, {key}) == {"S40", "T40"}
    added = [outcome_of(r, "censored", "2022-10-06", reason="end_of_train") for r in (base, other)]
    given = inputs(TRAIN_OUTCOMES + added, guide="")
    built = D.build(D.Inputs(**{**given.__dict__, "events": events}))
    assert built.report["inputs"]["fixed_test_item_statements"] == 1
    assert built.report["inputs"]["guide_examples"] == 0
    # a fixed item built on S11: its text on a test date (T08) is in the list and in no subset
    on_s11 = replace(
        fixed,
        generic_name="Drug S11",
        date_of_update="2020-02-12",
        availability_information="Backordered",
        related_information="Estimated Recovery: March (lot 12)",
    )
    monkeypatch.setattr(R, "CANARY_ITEM", on_s11)
    assert D.fixed_item_examples(synthetic_events()) == {("drug s11", "acme pharma", "2020-02-12")}
    listed = D.build(inputs(guide="")).eligible.set_index("statement_group_id")
    assert listed.loc["T08", [s.name for s in D.SUBSETS]].tolist() == [0] * len(D.SUBSETS)
    assert listed.loc["T09", [s.name for s in D.SUBSETS]].tolist() == [1] * len(D.SUBSETS)


def test_reference_check_leaves_out_the_first_draw() -> None:
    plain = D.build(inputs())
    assert plain.report["subsets"]["first_draw"] == {
        "lists_read": {},
        "lists_missing": list(D.FIRST_DRAW),
        "ids_not_in_the_statement_table": 0,
        "eligible_statements_left_out": 0,
    }
    assert not plain.report["subsets"]["reference_check"]["final"]
    assert plain.report["subsets"]["probe"]["final"]
    # a literal item on the eligible list is kept in the list and out of the reference check only
    drawn = {"pilot": ("S01",), "check": ("S10",), "reserve": (), "literal": ("T09", "S02")}
    built = D.build(inputs(first_draw=drawn))
    listed = built.eligible.set_index("statement_group_id")
    assert listed.index.tolist() == ["T01", "T03", "T08", "T09"]
    assert listed["reference_check"].tolist() == [1, 1, 0, 0]
    for name in ("probe", "samples20", "paraphrase", "twobytwo"):
        assert listed[name].tolist() == plain.eligible[name].tolist() == [1, 1, 0, 1]
    subsets = built.report["subsets"]
    assert subsets["first_draw"] == {
        "lists_read": {"pilot": 1, "check": 1, "reserve": 0, "literal": 2},
        "lists_missing": [],
        "ids_not_in_the_statement_table": 0,
        "eligible_statements_left_out": 1,
    }
    assert subsets["pool"] == 3 and subsets["left_out_as_guide_examples"] == 1
    assert subsets["reference_check"]["pool"] == 2 and subsets["probe"]["pool"] == 3
    assert subsets["reference_check"]["final"] and subsets["reference_check"]["statements"] == 2
    assert subsets["reference_check"]["leaves_out_the_first_draw"]
    assert not subsets["probe"]["leaves_out_the_first_draw"]
    assert (
        built.report["inputs"]["first_draw_lists_sha256"]["literal"]
        == D.ids_sha256(["S02", "T09"])[:16]
    )
    assert built.statements_gz == plain.statements_gz
    assert built.report["e3"] == plain.report["e3"]
    # the same text on another date is left out with the labelled statement (S11 and T08)
    assert D.labelled_statements(synthetic_events(), ["S11", "nowhere"]) == {"S11", "T08"}
    assert D.labelled_statements(synthetic_events(), []) == set()
    by_text = D.build(inputs(guide="", first_draw={"pilot": ("S11", "nowhere")}))
    assert by_text.report["subsets"]["first_draw"]["ids_not_in_the_statement_table"] == 1
    assert by_text.eligible["reference_check"].tolist() == [1, 1, 0, 1]
    assert by_text.eligible["probe"].tolist() == [1, 1, 1, 1]
    assert by_text.report["subsets"]["first_draw"]["lists_missing"] == [
        "check",
        "reserve",
        "literal",
    ]
    assert not by_text.report["subsets"]["reference_check"]["final"]
    # all four lists read, but one id is of another build: the draw is not final
    strange = D.build(inputs(first_draw={**drawn, "pilot": ("S01", "nowhere")}))
    assert strange.report["subsets"]["first_draw"]["lists_missing"] == []
    assert strange.report["subsets"]["first_draw"]["ids_not_in_the_statement_table"] == 1
    assert not strange.report["subsets"]["reference_check"]["final"]
    assert strange.report["subsets"]["probe"]["final"]


def test_first_draw_lists_are_read_from_their_folder(tmp_path: Path) -> None:
    assert D.first_draw_lists(None) == {} and D.first_draw_lists(tmp_path / "nowhere") == {}
    columns = ["event_id", "statement_group_id", "thread_id"]
    pd.DataFrame([["E272", "T09", "T272"], ["E021", "S02", "T021"]], columns=columns).to_csv(
        tmp_path / "sample_literal.csv", index=False
    )
    pd.DataFrame([], columns=columns).to_csv(tmp_path / "sample_reserve.csv", index=False)
    (tmp_path / "strata.csv").write_text("sample,stratum\n", encoding="utf-8")
    assert D.first_draw_lists(tmp_path) == {"reserve": (), "literal": ("S02", "T09")}
    (tmp_path / "sample_pilot.csv").write_text("event_id\nE011\n", encoding="utf-8")
    with pytest.raises(ValueError, match="statement_group_id"):
        D.first_draw_lists(tmp_path)


def test_subsets_of_a_larger_list_have_their_sizes() -> None:
    n = 900
    table = pd.DataFrame(
        {
            "statement_group_id": [f"S{i:04d}" for i in range(n)],
            "event_id": [f"E{i:04d}" for i in range(n)],
            "thread_id": "T",
            "episode_id": "g@2019-10-20",
            "event_date": [f"{2023 + i % 3}-03-01" for i in range(n)],
            "form": "month_year",
            "stated_end": "2025-12-31",
            "e3_eligible": "True",
        }
    )
    listed = D.eligible_frame(table, excluded={"S0000", "S0001"})
    sizes = {
        "probe": 300,
        "samples20": 300,
        "paraphrase": 200,
        "twobytwo": 300,
        "reference_check": 100,
    }
    assert {s.name: int(listed[s.name].sum()) for s in D.SUBSETS} == sizes
    # labelled statements leave the reference check alone; the next in the seeded order come in
    checked = listed.loc[listed["reference_check"] == 1, "statement_group_id"].tolist()
    without = D.eligible_frame(table, {"S0000", "S0001"}, labelled=checked[:10])
    assert {s.name: int(without[s.name].sum()) for s in D.SUBSETS} == sizes
    again = without.loc[without["reference_check"] == 1, "statement_group_id"].tolist()
    assert not set(again) & set(checked[:10]) and set(checked[10:]) <= set(again)
    assert without.drop(columns="reference_check").equals(listed.drop(columns="reference_check"))
    assert listed.loc[listed["statement_group_id"].isin(["S0000", "S0001"]), "probe"].sum() == 0
    assert not listed["probe"].equals(listed["samples20"])
    assert listed.equals(D.eligible_frame(table.sample(frac=1, random_state=5), {"S0001", "S0000"}))


# --------------------------------------------------------------------------------------------
# Items for the reading harness
# --------------------------------------------------------------------------------------------


def test_items_are_read_by_the_harness() -> None:
    from analysis.coling import read as R

    table = full_table()
    rows = D.items(table, ["T03", "S01", "S02"])
    assert [r["item_id"] for r in rows] == ["S01", "S02", "T03"]
    assert all(tuple(r) == D.ENTRY_KEYS for r in rows)
    # no key that the harness would take for another field (event_id is an alias of item_id)
    assert not set(D.ENTRY_KEYS) & set(R._ALIASES)
    item = R.ReadItem.from_dict(rows[0])
    assert item.item_id == "S01" and item.presentation == "10 mL vial (E011)"
    assert item.date_of_update == "2020-02-10" and item.stated_end == "2020-05-31"
    assert item.type_of_update == "Revised" and item.revision == "third or later"
    assert item.form == "a month and year" and item.initial_posting_date == "2019-01-15"
    assert item.availability_information == "Backordered"
    assert item.related_information == "Estimated Recovery: May 2020"
    assert rows[0]["display_event_id"] == "E011" and rows[0]["split"] == "fit"
    tbd = R.ReadItem.from_dict(rows[1])
    assert rows[1]["stated_end"] is None and tbd.stated_end is None
    assert R.ReadItem.from_dict(rows[2]).period == "test"
    with pytest.raises(ValueError, match="not in the statement table"):
        D.items(table, ["S01", "nowhere"])


def test_items_show_what_the_annotation_sheets_show() -> None:
    sample = pytest.importorskip("analysis.coling.audit_sample")
    table = full_table()
    shown = synthetic_events().set_index("event_id")
    for gid in ("S01", "T01", "T09"):
        row = D.item(table.loc[gid].to_dict())
        sheet = sample.harness_item(shown.loc[row["display_event_id"]], row["item_id"])
        assert {key: row[key] for key in sheet} == sheet


def test_probe_items_carry_no_stated_end_and_no_text() -> None:
    from analysis.coling import read as R

    table = full_table()
    rows = D.items(table, ["T01", "T03"], probe=True)
    assert set(D.PROBE_KEYS) <= set(R.PROBE_FIELDS)
    for row in rows:
        assert tuple(row) == D.PROBE_KEYS
        assert not {"stated_end", "form", "revision", "type_of_update"} & set(row)
        assert not any("information" in key or "reason" in key for key in row)
        assert "Estimated Recovery" not in json.dumps(row)
        item = R.ReadItem.from_dict(row)
        assert item.stated_end is None and item.form is None and item.revision is None
        assert not item.availability_information and not item.related_information
        assert not item.reason_for_shortage and not item.type_of_update
        assert item == R.probe_view(item)
        # even read as an ordinary item it has no stated end to print
        assert R.horizons(item)[2] == "fallback"
    assert table.loc["T03", "stated_end"] == "2026-06-28"
    assert "2026-06-28" not in D.jsonl(rows)


def test_write_items_writes_every_list(tmp_path: Path) -> None:
    from analysis.coling import read as R

    built = D.build(inputs())
    written = D.write_items(built.table, built.eligible, tmp_path)
    assert sorted(written) == sorted(p.name for p in tmp_path.iterdir())
    assert {name: rec["rows"] for name, rec in written.items()} == {
        "e3_eligible.jsonl": 4,
        "e3_tbd.jsonl": 1,
        "e3_silent.jsonl": 1,
        "e3_stale.jsonl": 1,
        "subset_probe.jsonl": 3,
        "subset_samples20.jsonl": 3,
        "subset_paraphrase.jsonl": 3,
        "subset_twobytwo.jsonl": 3,
        "subset_reference_check.jsonl": 3,
        "dev_scoreable.jsonl": 2,
    }
    assert [rec["probe"] for rec in written.values()].count(True) == 1
    probe = (tmp_path / "subset_probe.jsonl").read_text()
    assert "stated_end" not in probe and "Estimated Recovery" not in probe
    assert all(i.stated_end is None for i in R.load_items(tmp_path / "subset_probe.jsonl"))
    eligible = R.load_items(tmp_path / "e3_eligible.jsonl")
    assert [i.item_id for i in eligible] == ["T01", "T03", "T08", "T09"]
    assert all(i.stated_end and i.period == "test" for i in eligible)
    assert [i.item_id for i in R.load_items(tmp_path / "dev_scoreable.jsonl")] == ["S07", "S10"]
    assert [i.item_id for i in R.load_items(tmp_path / "e3_stale.jsonl")] == ["T06"]
    again = D.write_items(built.table, built.eligible, tmp_path / "again")
    assert again == written
    assert written["e3_eligible.jsonl"]["item_ids_sha256"] == R._ids_sha256(
        i.item_id for i in eligible
    )


# --------------------------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------------------------


def test_counts_report() -> None:
    report = D.build(inputs()).report
    assert report["parameters"]["last_capture"] == "2026-09-26"
    assert report["parameters"]["train_horizon"] == "2022-10-06"
    assert report["parameters"]["capture_days"] == len(DAYS)
    assert report["events"]["all"] == {
        "fit": 11,
        "dev": 3,
        "test": 10,
        "late": 2,
        "train": 14,
        "all": 26,
    }
    assert report["events"]["train_first_seen_in_test_period"] == {
        "shortage_listing": 1,
        "at_risk_B": 1,
    }
    statements = report["statements"]
    assert statements["all"] == {"fit": 9, "dev": 3, "test": 9, "late": 2, "train": 12, "all": 23}
    assert statements["shortage_listing"]["fit"] == 8 and statements["at_risk_A"]["fit"] == 7
    assert statements["at_risk_B"] == {
        "fit": 7,
        "dev": 3,
        "test": 8,
        "late": 2,
        "train": 10,
        "all": 20,
    }
    assert statements["with_several_presentations"]["all"] == 2
    assert statements["with_several_presentations_at_risk_B"]["all"] == 2
    assert statements["most_presentations_in_one_statement"] == 3
    sets = report["at_risk_B_by_analysis_set"]
    assert {k: v["test"] for k, v in sets.items()} == {
        "dated": 5,
        "stale": 1,
        "tbd": 1,
        "silent": 1,
        "none": 0,
    }
    assert sets["none"]["fit"] == 1 and sets["stale"]["fit"] == 1
    assert report["eligible"]["dated"]["test"] == 4 and report["eligible"]["dated"]["late"] == 1
    assert report["eligible"]["tbd"]["late"] == 0
    assert report["dated_with_horizon_b_after_the_last_capture"]["test"] == 1
    e3 = report["e3"]
    assert e3["statements"] == 4 and e3["covered_presentation_events"] == 5
    assert e3["by_year"] == {"2023": 2, "2024": 1, "2025": 1}
    assert e3["by_form"]["month_year"] == 2 and e3["by_form"]["exact_day"] == 1
    assert e3["by_form"]["month_no_year"] == 1 and e3["episodes"] == 1
    assert e3["episodes_that_also_hold_train_statements"] == 0
    assert e3["first_captured_after_stated_end"] == 2
    assert e3["dated_after"]["2022-12-31"] == 4 and e3["dated_after"]["2023-12-31"] == 2
    assert list(e3["dated_after"])[-1] == "2025-12-31" and len(e3["dated_after"]) == 37
    assert e3["dated_after"]["2025-12-31"] == 0
    assert e3["ids_sha256"] == D.ids_sha256(["T01", "T03", "T08", "T09"])
    assert report["budget"] == {"N_E": 4, "N_S": 3, "N_D": 2}
    assert report["dev_scoreable"] == {
        "statements": 2,
        "episodes": 1,
        "ids_sha256": D.ids_sha256(["S07", "S10"]),
    }
    assert report["secondary_lists_test"]["tbd"] == {
        "statements": 1,
        "episodes": 1,
        "ids_sha256": D.ids_sha256(["T04"]),
        "episodes_that_also_hold_train_statements": 0,
    }
    assert report["late"]["statements"] == 1
    fit, dev = report["train"]["fit"], report["train"]["dev"]
    assert fit["dated"] == {
        "statements": 3,
        "episodes": 1,
        "scoreable": 1,
        "scoreable_episodes": 1,
        "with_a_horizon_event_undetermined": 2,
        "scoreable_by_E_end_and_E_end90": {"no/no": 0, "no/yes": 1, "yes/yes": 0},
    }
    assert fit["dated_all_covered_presentations"]["scoreable"] == 2
    assert dev["dated"]["scoreable"] == 2
    assert dev["dated"]["scoreable_by_E_end_and_E_end90"] == {"no/no": 1, "no/yes": 0, "yes/yes": 1}
    assert dev["dated_first_captured_by_stated_end"]["scoreable"] == 1
    assert dev["dated_first_captured_by_stated_end"]["statements"] == 2
    assert fit["dated_first_captured_by_stated_end"]["statements"] == 2
    assert fit["outcome_of_the_display_row"] == {"recovered": 5, "censored": 1, "discontinued": 1}
    assert dev["censor_reason"] == {"end_of_train": 2}
    assert fit["tbd_and_silent"] == {"statements": 2, "scoreable_at_90_and_180_days": 1}
    assert fit["time_to_recovery_target"] == {"at_cap": 2, "interval": 5}
    assert D.month_ends(date(2022, 12, 31), date(2023, 3, 1)) == [
        date(2022, 12, 31),
        date(2023, 1, 31),
        date(2023, 2, 28),
    ]


def test_lists_use_the_display_row_and_leave_out_the_late_split() -> None:
    given = inputs()
    days = tuple(given.days)
    # with a later last capture the late TBD statement L02 becomes eligible: still on no list
    later = D.statement_table(synthetic_events(), date(2027, 6, 1), IDENTITY)
    table = D.attach_outcomes(later, given.outcomes)
    rows = table.set_index("statement_group_id")
    assert rows.loc["L02", ["split", "analysis_set", "eligible"]].tolist() == [
        "late",
        "tbd",
        "True",
    ]
    # S08 is scoreable over all covered presentations only: not a dev item, not in N_D
    table.loc[table["statement_group_id"] == "S08", "scoreable_all"] = "True"
    eligible = D.eligible_frame(table)
    lists = D.item_lists(table, eligible)
    assert lists["e3_tbd"] == (["T04"], False)
    assert lists["dev_scoreable"] == (["S07", "S10"], False)
    assert "L01" not in lists["e3_eligible"][0] and "T02" in lists["e3_eligible"][0]
    report = D.counts(given.events, table, eligible, days, ())
    assert report["secondary_lists_test"]["tbd"]["statements"] == 1
    assert report["eligible"]["tbd"]["late"] == 1
    assert report["budget"] == {"N_E": 5, "N_S": 3, "N_D": 2}
    assert report["dev_scoreable"]["ids_sha256"] == D.ids_sha256(["S07", "S10"])


def test_episodes_that_cross_the_split_and_post_cutoff_slices() -> None:
    frame = pd.DataFrame({"episode_id": ["a@1", "a@1", "b@2", "", "c@3"]})
    assert D.crossing(frame, {"a@1", "c@3", "z@9", ""}) == 2
    assert D.crossing(frame, set()) == 0
    table = full_table()
    assert D.train_episodes(table) == {"s@2019-10-20"}
    # a statement dated on the last day of a month is not after that month
    days = pd.Series(["2023-01-31", "2023-02-01", "2023-02-28"])
    assert D.dated_after(days, [date(2022, 12, 31), date(2023, 1, 31), date(2023, 2, 28)]) == {
        "2022-12-31": 3,
        "2023-01-31": 2,
        "2023-02-28": 0,
    }


def test_build_checks_the_capture_days() -> None:
    given = inputs()
    fewer = D.Inputs(**{**given.__dict__, "days": given.days[:-1]})
    with pytest.raises(ValueError, match="not capture days"):
        D.build(fewer)


# --------------------------------------------------------------------------------------------
# Command line and determinism
# --------------------------------------------------------------------------------------------


def write_inputs(folder: Path) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    synthetic_events().to_csv(folder / "events.csv.gz", index=False, compression=F.GZIP)
    outcome_table(TRAIN_OUTCOMES).to_csv(
        folder / "outcomes_train.csv.gz", index=False, compression=F.GZIP
    )
    stamps = [d.replace("-", "") + "120000" for d in DAYS]
    manifest = pd.DataFrame({"file": [s + ".csv" for s in stamps], "timestamp": stamps})
    manifest.assign(bytes=1, sha256="0").to_csv(folder / "capture_manifest.csv", index=False)
    (folder / "guide.md").write_text(GUIDE, encoding="utf-8")
    (folder / "samples").mkdir(exist_ok=True)
    return [
        "--samples",
        str(folder / "samples"),
        "--events",
        str(folder / "events.csv.gz"),
        "--outcomes",
        str(folder / "outcomes_train.csv.gz"),
        "--manifest",
        str(folder / "capture_manifest.csv"),
        "--guide",
        str(folder / "guide.md"),
    ]


def test_main_writes_the_outputs_reproducibly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = write_inputs(tmp_path / "in")
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    assert D.main([*args, "--out", str(out_a)]) == 0
    assert D.main([*args, "--out", str(out_b), "--items", str(tmp_path / "items")]) == 0
    printed = capsys.readouterr().out
    assert "E3 eligible: 4 statements" in printed and "subset probe: 3" in printed
    names = (D.STATEMENTS.name, D.ELIGIBLE.name, D.COUNTS.name)
    for name in names:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()
    assert sorted(p.name for p in out_a.iterdir()) == sorted(names)
    assert (tmp_path / "items" / "subset_probe.jsonl").exists()
    report = json.loads((out_a / D.COUNTS.name).read_text())
    table = D.load_statements(out_a / D.STATEMENTS.name)
    assert list(table.columns) == list(D.COLUMNS) and len(table) == 23
    assert table["statement_group_id"].tolist() == sorted(table["statement_group_id"])
    assert report["outputs"][D.STATEMENTS.name] == {
        "rows": 23,
        "columns": len(D.COLUMNS),
        "sha256": D.sha16((out_a / D.STATEMENTS.name).read_bytes()),
        "content_sha256": D.sha16(gzip.decompress((out_a / D.STATEMENTS.name).read_bytes())),
    }
    assert report["outputs"][D.ELIGIBLE.name]["sha256"] == D.sha16(
        (out_a / D.ELIGIBLE.name).read_bytes()
    )
    assert report["inputs"]["events_sha256"] == D.sha16(
        (tmp_path / "in" / "events.csv.gz").read_bytes()
    )
    assert report["inputs"]["dataset_sha256"] == D.sha16(Path(D.__file__).read_bytes())
    assert report["inputs"]["guide_examples"] == 1
    assert report["command"] == D.COMMAND
    assert "first-draw lists not on disk: pilot, check, reserve, literal" in printed
    assert "subset reference_check: 3 (not final" in printed
    sealed = table[table["period"] != "train"]
    assert (sealed[list(D.OUTCOME_COLUMNS)] == "").all().all()
    assert D.true(table["e3_eligible"]).sum() == report["e3"]["statements"] == 4


def test_check_detects_a_stale_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = [*write_inputs(tmp_path / "in"), "--out", str(tmp_path / "out")]
    assert D.main([*args, "--check"]) == 1  # nothing written yet
    assert D.main(args) == 0
    assert D.main([*args, "--check"]) == 0
    assert "up to date" in capsys.readouterr().out
    path = tmp_path / "out" / D.ELIGIBLE.name
    path.write_text(path.read_text().replace("T03", "T99"))
    assert D.main([*args, "--check"]) == 1
    assert "differs from a fresh run" in capsys.readouterr().out
    # a first-draw list that appears after the run makes the outputs stale, until they are rebuilt
    assert D.main(args) == 0
    lists = tmp_path / "in" / "samples"
    for name in D.FIRST_DRAW:
        ids = "T09\n" if name == "literal" else ""
        (lists / f"sample_{name}.csv").write_text("statement_group_id\n" + ids, encoding="utf-8")
    assert D.main([*args, "--check"]) == 1
    capsys.readouterr()
    assert D.main(args) == 0
    printed = capsys.readouterr().out
    assert "subset reference_check: 2\n" in printed and "not on disk" not in printed
    assert D.main([*args, "--check"]) == 0
    listed = D.read_table(path).set_index("statement_group_id")
    assert listed.loc["T09", ["probe", "reference_check"]].tolist() == ["1", "0"]


# --------------------------------------------------------------------------------------------
# The files in the repository
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_outputs() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    paths = (D.EVENTS, D.OUTCOMES, D.MANIFEST, D.STATEMENTS, D.ELIGIBLE, D.COUNTS)
    if not all(p.exists() for p in paths):
        pytest.skip("run from the repository root after python -m analysis.coling.dataset")
    return D.load_statements(), D.read_table(D.ELIGIBLE), json.loads(D.COUNTS.read_text())


def test_written_table_holds_no_test_period_outcome(
    real_outputs: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    table, listed, report = real_outputs
    assert list(table.columns) == list(D.COLUMNS)
    sealed = table[table["event_date"] >= D.TEST_START.isoformat()]
    assert len(sealed) and (sealed["period"] == "test").all()
    assert (sealed[list(D.OUTCOME_COLUMNS)] == "").all().all()
    assert list(report["train"]) == list(D.TRAIN_SPLITS)
    assert not set(D.OUTCOME_COLUMNS) & set(listed.columns)
    assert table["statement_group_id"].is_unique


def test_written_display_rows_are_those_of_the_annotation_sheets(
    real_outputs: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    sample = pytest.importorskip("analysis.coling.audit_sample")
    table, _, report = real_outputs
    if report["inputs"].get("events_sha256") != D.sha16(D.EVENTS.read_bytes()):
        pytest.skip("the outputs were not built from the events table on disk")
    sheets = sample.display_events(D.read_table(D.EVENTS)).set_index("statement_group_id")
    shown = table.set_index("statement_group_id")["event_id"]
    assert sheets["event_id"].to_dict() == shown.to_dict()


def test_written_eligible_list_matches_the_table(
    real_outputs: tuple[pd.DataFrame, pd.DataFrame, dict],
) -> None:
    table, listed, report = real_outputs
    ids = listed["statement_group_id"].tolist()
    assert (
        ids == sorted(ids) == sorted(table.loc[D.true(table["e3_eligible"]), "statement_group_id"])
    )
    rows = table.set_index("statement_group_id").loc[ids]
    assert (rows["split"] == "test").all() and (rows["analysis_set"] == "dated").all()
    assert D.true(rows["at_risk_B"]).all() and not D.true(rows["stale_at_issue"]).any()
    assert (rows["horizon_b"] <= report["parameters"]["last_capture"]).all()
    assert (rows["stated_end"] >= rows["event_date"]).all()
    assert (rows["stated_end"].to_numpy() == listed["stated_end"].to_numpy()).all()
    assert report["e3"]["ids_sha256"] == D.ids_sha256(ids)
    assert report["outputs"][D.ELIGIBLE.name]["sha256"] == D.sha16(D.ELIGIBLE.read_bytes())
    assert report["outputs"][D.STATEMENTS.name]["sha256"] == D.sha16(D.STATEMENTS.read_bytes())
    for subset in D.SUBSETS:
        assert int(listed[subset.name].astype(int).sum()) == min(subset.size, len(ids))


def test_outputs_are_up_to_date(real_outputs: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    report = real_outputs[2]
    if "events_sha256" not in report["inputs"]:
        pytest.skip("the outputs were built with --captures")
    assert D.main(["--check"]) == 0, "stale outputs: python -m analysis.coling.dataset"
    if F.COUNTS.exists():
        merged = F.load_merge()
        in_use = report["inputs"]["merged_forms_in_use"]
        assert in_use == {name: merged[name] for name in in_use}
