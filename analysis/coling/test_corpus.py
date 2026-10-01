"""Tests for the OpEst-FDA corpus builder on small synthetic captures.

Each test writes a few fake capture CSVs (FDA header, leading blank line, CRLF endings) to a
temporary directory and builds the corpus from them; one test reads the committed check list of
availability strings instead. Covered: parsing drift (blank lines, BOM,
latin-1, header whitespace, typos in Type of Update, status spellings, a row broken by an
unescaped quote, a file with a header and no rows), re-verification, revision, recovery under
definitions A and B, exit while the generic is resolved, right-censoring, discontinuation as a
competing event, NDC linking across a re-formatted presentation, relisting after resolution, the
train/test split with sealing, and timing-phrase extraction; the availability rule (negated,
future and estimated mentions, the rejection list and the stop on an entry that is in no capture,
the check list of strings, and the committed check list against the rule); the Gate 1 counts
with their gate set and cutoff month; the per-capture count of realigned rows; the guard on
re-confirmation dates; the manifest hook; the build of the open tables alone; and edge cases of
censoring (a train event first seen in the test period, an event first seen at the last capture,
a thread that leaves while its generic is unlisted), of dating and of mixed statement groups.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_corpus.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from analysis.coling import corpus as C

HEADER = (
    "Generic Name,Company Name, Contact Info, Presentation, Type of Update,Date of Update, "
    "Availability Information, Related Information, Resolved Note, Reason for Shortage, "
    "Therapeutic Category, Status, Change Date, Date Discontinued, Initial Posting Date"
)
DRUG = "Alpha Injection"
CO = "Acme Pharma"
P10 = "10 mg vial (NDC 12345-678-90)"
P20 = "20 mg vial (NDC 12345-679-90)"


def row(
    presentation: str,
    update: str,
    date: str,
    avail: str = "",
    related: str = "",
    status: str = "Current",
    disc: str = "",
    generic: str = DRUG,
    company: str = CO,
) -> list[str]:
    return [
        generic,
        company,
        "800-000-0000",
        presentation,
        update,
        date,
        avail,
        related,
        "",
        "Demand increase for the drug",
        "Anesthesia",
        status,
        "",
        disc,
        "01/05/2021",
    ]


def write_capture(
    directory: Path, stamp: str, rows: list[list[str]], raw_lines: tuple[str, ...] = ()
) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    for r in rows:
        writer.writerow(r)
    text = "\r\n" + HEADER + "\r\n" + buf.getvalue() + "".join(raw_lines)
    (directory / f"{stamp}.csv").write_bytes(text.encode("utf-8"))


def build(directory: Path, captures: dict[str, list[list[str]]]) -> C.Corpus:
    for stamp, rows in captures.items():
        write_capture(directory, stamp, rows)
    return C.build_corpus(directory)


def events_of(corpus: C.Corpus, presentation: str) -> pd.DataFrame:
    ev = corpus.events
    return ev[ev["presentation"] == presentation].sort_values("first_seen_date")


def outcome(corpus: C.Corpus, event_id: str) -> pd.Series:
    out = corpus.outcomes.set_index("event_id")
    return out.loc[event_id]


def test_reverification_is_a_reconfirmation_not_a_new_event(tmp_path: Path) -> None:
    text = "Estimated recovery: March 2022"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "Revised", "12/20/2021", "Unavailable", text)],
            "20220201000000": [row(P10, "Reveriifed", "01/25/2022", "Unavailable", text)],
            "20220301000000": [row(P10, "Reverfied", "02/25/2022", "Unavailable", text)],
        },
    )
    ev = events_of(corpus, P10)
    assert len(ev) == 1
    first = ev.iloc[0]
    assert first["event_date"] == "2021-12-20"
    assert first["type_of_update"] == "revised"
    assert first["revision_index"] == 0
    assert outcome(corpus, first["event_id"])["n_reconfirmations"] == 2
    assert outcome(corpus, first["event_id"])["last_reconfirmed_date"] == "2022-02-25"


def test_revision_starts_a_new_event_and_keeps_the_thread(tmp_path: Path) -> None:
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "New", "12/20/2021", "Unavailable", "Recovery March 2022")],
            "20220201000000": [
                row(P10, "Revised", "01/25/2022", "Unavailable", "Recovery May 2022")
            ],
            "20220301000000": [
                row(P10, "Reverified", "02/25/2022", "Unavailable", "Recovery March 2022")
            ],
        },
    )
    ev = events_of(corpus, P10)
    assert list(ev["revision_index"]) == [0, 1, 2]
    assert ev["thread_id"].nunique() == 1
    assert ev.iloc[1]["prev_event_id"] == ev.iloc[0]["event_id"]
    assert ev.iloc[1]["prev_event_date"] == "2021-12-20"
    assert list(ev["text_seen_before_in_thread"]) == [False, False, True]
    assert ev.iloc[2]["date_is_reverification"]
    assert outcome(corpus, ev.iloc[0]["event_id"])["next_event_id"] == ev.iloc[1]["event_id"]


def test_availability_label_change_is_not_a_new_statement(tmp_path: Path) -> None:
    text = "Next delivery: February 2022"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P20, "Revised", "12/20/2021", "Unavailable", text)],
            "20220201000000": [row(P20, "Revised", "01/25/2022", "Limited Availability", text)],
        },
    )
    assert len(events_of(corpus, P20)) == 1


def test_recovery_brackets_under_both_definitions(tmp_path: Path) -> None:
    text = "Next delivery: February 2022"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P20, "Revised", "12/20/2021", "Unavailable", text)],
            "20220201000000": [row(P20, "Revised", "01/25/2022", "Available", text)],
            "20220301000000": [row(P20, "Reverified", "02/25/2022", "Available", text)],
            "20220401000000": [row(P20, "Revised", "03/28/2022", "Available", text, "Resolved")],
        },
    )
    ev = events_of(corpus, P20).iloc[0]
    out = outcome(corpus, ev["event_id"])
    assert out["outcome_B"] == "recovered"
    assert (out["lower_date_B"], out["upper_date_B"]) == ("2022-01-01", "2022-02-01")
    assert out["lower_days_B"] == 12 and out["upper_days_B"] == 43
    assert out["observable31_B"]
    assert out["outcome_A"] == "recovered"
    assert (out["lower_date_A"], out["upper_date_A"]) == ("2022-03-01", "2022-04-01")
    assert out["width_days_A"] == 31 and out["observable31_A"]
    assert out["event_via_A"] == "listed"


def test_not_at_risk_when_available_or_resolved_at_first_sight(tmp_path: Path) -> None:
    corpus = build(
        tmp_path,
        {
            "20220101000000": [
                row(P10, "Revised", "12/20/2021", "Available", "Lots in March 2022")
            ],
            "20220201000000": [row(P10, "Revised", "01/20/2022", "", "", "Resolved")],
        },
    )
    ev = events_of(corpus, P10)
    first, second = (outcome(corpus, e) for e in ev["event_id"])
    assert first["at_risk_A"] and not first["at_risk_B"]
    assert first["outcome_B"] == "not_at_risk" and first["outcome_A"] == "recovered"
    assert second["outcome_A"] == "not_at_risk" and second["outcome_B"] == "not_at_risk"


def test_exit_while_generic_resolved_counts_as_recovery_A(tmp_path: Path) -> None:
    text = "Estimated recovery: TBD"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [
                row(P10, "Revised", "12/20/2021", "Unavailable", text),
                row(P20, "Revised", "12/20/2021", "Unavailable", text),
            ],
            "20220201000000": [row(P20, "Revised", "01/25/2022", "", "", "Resolved")],
        },
    )
    ev = events_of(corpus, P10).iloc[0]
    out = outcome(corpus, ev["event_id"])
    assert out["outcome_A"] == "recovered" and out["event_via_A"] == "exit_generic_resolved"
    assert out["outcome_B"] == "recovered"
    assert ev["has_no_estimate"] and not ev["has_date_like"]


def test_right_censoring_at_the_end_and_after_leaving_the_list(tmp_path: Path) -> None:
    text = "Estimated recovery: June 2022"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [
                row(P10, "Revised", "12/20/2021", "Unavailable", text),
                row(P20, "Revised", "12/20/2021", "Unavailable", text),
            ],
            "20220201000000": [
                row(P10, "Reverified", "01/25/2022", "Unavailable", text),
                row(P20, "Reverified", "01/25/2022", "Unavailable", text),
            ],
            "20220301000000": [row(P10, "Reverified", "02/25/2022", "Unavailable", text)],
        },
    )
    stays = outcome(corpus, events_of(corpus, P10).iloc[0]["event_id"])
    assert stays["outcome_A"] == "censored" and stays["censor_reason_A"] == "end_of_archive"
    assert stays["lower_date_A"] == "2022-03-01" and stays["upper_date_A"] == ""
    assert not stays["observable31_A"]
    leaves = outcome(corpus, events_of(corpus, P20).iloc[0]["event_id"])
    assert leaves["outcome_B"] == "censored"
    assert leaves["censor_reason_B"] == "absent_generic_current"
    assert leaves["lower_date_B"] == "2022-02-01"


def test_discontinuation_is_a_competing_event(tmp_path: Path) -> None:
    text = "Estimated recovery: April 2022"
    moved = "10 mg vial, 25 count (NDC 12345-0678-90)"  # same package NDC, other wording
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "Revised", "12/20/2021", "Unavailable", text)],
            "20220201000000": [row(P10, "Reverified", "01/25/2022", "Unavailable", text)],
            "20220301000000": [
                row(P10, "Reverified", "02/25/2022", "Unavailable", text),
                row(
                    moved,
                    "New",
                    "02/27/2022",
                    "",
                    "Business decision",
                    "To be Discontinued",
                    "02/27/2022",
                ),
            ],
            "20220401000000": [
                row(
                    moved,
                    "New",
                    "02/27/2022",
                    "",
                    "Business decision",
                    "To Be Discontinued",
                    "02/27/2022",
                ),
            ],
        },
    )
    ev = events_of(corpus, P10).iloc[0]
    out = outcome(corpus, ev["event_id"])
    for d in ("A", "B"):
        assert out[f"outcome_{d}"] == "discontinued"
        assert out[f"event_via_{d}"] == "discontinuation_listing"
        assert (out[f"lower_date_{d}"], out[f"upper_date_{d}"]) == ("2022-02-01", "2022-03-01")
        assert out[f"disc_date_field_{d}"] == "02/27/2022"
    disc = corpus.events[corpus.events["listing"] == "discontinuation"]
    assert len(disc) == 1 and disc.iloc[0]["status_at_statement"] == "discontinued"
    assert disc.iloc[0]["event_id"] not in set(corpus.outcomes["event_id"])


def test_already_listed_for_discontinuation_is_flagged_not_counted(tmp_path: Path) -> None:
    text = "Estimated recovery: April 2022"
    both = [
        row(P10, "Revised", "12/20/2021", "Unavailable", text),
        row(P10, "New", "12/20/2021", "", "", "To be Discontinued", "12/20/2021"),
    ]
    corpus = build(tmp_path, {"20220101000000": both, "20220201000000": both})
    ev = corpus.events[
        (corpus.events["presentation"] == P10) & (corpus.events["listing"] == "shortage")
    ]
    assert ev.iloc[0]["discontinuation_listed_at_statement"]
    out = outcome(corpus, ev.iloc[0]["event_id"])
    assert out["outcome_A"] == "censored"


def test_ndc_links_a_reformatted_presentation_and_renamed_generic(tmp_path: Path) -> None:
    text = "Estimated recovery: TBD"
    new_name, new_pres = (
        "Alpha Hydrochloride Injection",
        "Injection, 10 mg/1 mL (NDC 12345-0678-90)",
    )
    corpus = build(
        tmp_path,
        {
            "20230501000000": [row(P10, "Revised", "04/20/2023", "Unavailable", text)],
            "20231101000000": [
                row(new_pres, "Reverified", "10/20/2023", "Unavailable", text, generic=new_name)
            ],
        },
    )
    obs = corpus.captures.obs
    assert obs["thread"].nunique() == 1
    assert obs["generic_id"].nunique() == 1 and obs["generic_id"].iloc[0] == C.norm_text(DRUG)
    ev = corpus.events
    assert len(ev) == 1 and ev.iloc[0]["period"] == "test"


def test_relisting_after_resolution_is_a_new_event(tmp_path: Path) -> None:
    text = "Estimated recovery: TBD"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "Revised", "12/20/2021", "Unavailable", text)],
            "20220201000000": [row(P10, "Revised", "01/20/2022", "Unavailable", text, "Resolved")],
            "20220301000000": [row(P10, "New", "02/20/2022", "Unavailable", text)],
        },
    )
    ev = events_of(corpus, P10)
    assert list(ev["status_at_statement"]) == ["current", "current"]
    assert list(ev["text_seen_before_in_thread"]) == [False, True]
    assert ev.iloc[1]["episode_id"] != ev.iloc[0]["episode_id"]


def test_parsing_drift(tmp_path: Path) -> None:
    good = row(P10, "Revised", "12/20/2021", "Unavailable", "Recovery March 2022")
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerow(
        row("Café 5 mg (NDC 55555-111-22)", "NNew", "12/21/2021", "Unavailable", "Q1 2022")
    )
    broken = (
        '"Alpha Injection","Acme Pharma","800","ALPHA-PF 10%", Sulfite-Free, (Pediatric) 1 L '
        '(NDC 12345-222-33)"","Revisee","12/22/2021","Unavailable","Late January 2022","",'
        '"","Anesthesia","Current","","","01/05/2021"\r\n'
    )
    text = "\r\n\r\n" + HEADER.replace("Status", " Status  ") + "\r\n"
    text += "\r\n".join(",".join(f'"{c}"' for c in r) for r in [good]) + "\r\n"
    raw = ("﻿" + text).encode("utf-8") + buf.getvalue().encode("latin-1") + broken.encode()
    (tmp_path / "20220101000000.csv").write_bytes(raw)
    (tmp_path / "cdx.json").write_text("[]")
    (tmp_path / "20220201000000.csv").write_text("<html>not a csv</html>")
    corpus = C.build_corpus(tmp_path)
    obs = corpus.captures.obs
    assert len(corpus.captures.skipped) == 1
    assert len(obs) == 3
    assert set(obs["update_type"]) == {"revised", "new"}
    fixed = obs[obs["row_repaired"]].iloc[0]
    assert (
        fixed["presentation"].startswith("ALPHA-PF 10%") and "12345-222-33" in fixed["presentation"]
    )
    assert fixed["update_type"] == "revised" and fixed["date_of_update"] == "12/22/2021"
    assert fixed["status_norm"] == "current"
    assert any(p.startswith("Café 5 mg") for p in obs["presentation"])  # latin-1 fallback
    assert C.norm_status("To be Discontinued") == C.norm_status("To Be Discontinued")
    assert C.norm_status("Currently in shortage") == "current"
    assert [C.norm_update_type(x) for x in ("Reveriifed", "Reveified", "Revisee", "NNew")] == [
        "reverified",
        "reverified",
        "revised",
        "new",
    ]


def test_outputs_and_sealing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    caps, out, sealed = tmp_path / "caps", tmp_path / "out", tmp_path / "sealed"
    caps.mkdir()
    old, new = "Estimated recovery: March 2022", "Estimated recovery: March 2023"
    build(
        caps,
        {
            "20221201000000": [row(P10, "Revised", "11/20/2022", "Unavailable", old)],
            "20230115000000": [row(P10, "Revised", "01/10/2023", "Unavailable", new)],
            "20230201000000": [row(P10, "Revised", "01/25/2023", "", "", "Resolved")],
        },
    )
    args = ["--captures", str(caps), "--out", str(out), "--sealed", str(sealed)]
    assert C.main(args, check=None) == 0
    printed = capsys.readouterr().out
    events = pd.read_csv(out / "events.csv.gz", keep_default_na=False)
    train = pd.read_csv(out / "outcomes_train.csv.gz", keep_default_na=False)
    test = pd.read_csv(sealed / "outcomes_test.csv.gz", keep_default_na=False)
    forbidden = {"contact_info", "outcome_A", "lower_date_B", "n_reconfirmations", "next_event_id"}
    assert not forbidden & set(events.columns)
    assert set(train["period"]) == {"train"} and set(test["period"]) == {"test"}
    assert set(events["period"]) == {"train", "test"}
    assert not (out / "outcomes_test.csv.gz").exists()
    assert set(train["censor_reason_A"]) == {"end_of_train"} and set(train["next_event_id"]) == {""}
    full = pd.read_csv(sealed / "outcomes_train_uncensored.csv.gz", keep_default_na=False)
    assert set(full["outcome_A"]) == {"recovered"}
    digest = hashlib.sha256((sealed / "outcomes_test.csv.gz").read_bytes()).hexdigest()
    assert digest in printed
    with gzip.open(sealed / "outcomes_test.csv.gz") as fh:
        assert fh.read(8) == b"event_id"
    # The gzip header carries no write time, so the same rows give the same bytes on any day.
    for path in (*sorted(out.glob("*.gz")), *sorted(sealed.glob("*.gz"))):
        assert path.read_bytes()[4:8] == bytes(4), path.name
    assert "statement events 1;" in printed
    assert "capture manifest: NOT checked" in printed
    assert not (out / "availability_strings.csv").exists()


def test_train_outcomes_stop_before_the_test_period(tmp_path: Path) -> None:
    old, new = "Estimated recovery: March 2022", "Estimated recovery: March 2023"
    corpus = build(
        tmp_path,
        {
            "20221101000000": [row(P10, "Revised", "10/20/2022", "Unavailable", old)],
            "20221201000000": [row(P10, "Reverified", "11/20/2022", "Unavailable", old)],
            "20230115000000": [row(P10, "Revised", "01/10/2023", "Unavailable", new)],
            "20230201000000": [row(P10, "Revised", "01/25/2023", "", "", "Resolved")],
        },
    )
    ev = events_of(corpus, P10)
    first, second = ev.iloc[0], ev.iloc[1]
    assert first["period"] == "train" and second["period"] == "test"
    train = outcome(corpus, first["event_id"])
    for d in C.DEFINITIONS:
        assert train[f"outcome_{d}"] == "censored"
        assert train[f"censor_reason_{d}"] == "end_of_train"
        assert train[f"lower_date_{d}"] == "2022-12-01" and train[f"upper_date_{d}"] == ""
        assert train[f"group_outcome_{d}"] == "censored"
    assert train["next_event_id"] == "" and train["n_followup_listed"] == 1
    assert train["n_followup_captures"] == 1 and train["followup_end_date"] == "2022-12-01"
    assert train["run_last_seen_date"] == "2022-12-01"
    # No train field may name a date in the test period.
    dates = [v for v in train.values if isinstance(v, str) and len(v) == 10 and v[4] == "-"]
    assert dates and all(v < "2023-01-01" for v in dates)
    # The uncensored version, which goes only to the sealed folder, follows the thread on.
    full = corpus.train_uncensored.set_index("event_id").loc[first["event_id"]]
    assert full["outcome_A"] == "recovered" and full["upper_date_A"] == "2023-02-01"
    assert full["next_event_id"] == second["event_id"]
    # The test event is followed to the end of the archive.
    test = outcome(corpus, second["event_id"])
    assert test["outcome_A"] == "recovered" and test["followup_end_date"] == "2023-02-01"


def test_timing_candidates() -> None:
    cases = {
        "Next Delivery: November 2022; Estimated Recovery: May 2023": [
            ("MONTH_YEAR", "November 2022"),
            ("MONTH_YEAR", "May 2023"),
        ],
        "In the November – December 2019 timeframe": [("MONTH_RANGE", "November - December 2019")],
        "Next release Q3-2024.": [("QUARTER", "Q3-2024")],
        "Backorder, Recovery expected Nov-22": [("MONTH_YEAR", "Nov-22")],
        "expected release the week of 10/28": [("WEEK_OF", "the week of 10/28")],
        "Estimated recovery: TBD": [("NO_ESTIMATE", "TBD")],
        "Product may be available in 4-6 weeks": [("RELATIVE", "4-6 weeks")],
        "Estimated recovery: late September 2026": [("MONTH_YEAR", "late September 2026")],
        "Expected to ship in May": [("MONTH", "May")],
        "Supply may fall short": [],
        "Distributed by Mayne Pharma; octreotide": [],
    }
    for text, expected in cases.items():
        assert C.timing_candidates(text) == expected, text


def test_availability_and_ndc_normalisers() -> None:
    assert C.availability_class("Inventory is currently available.") == "available"
    assert C.availability_class("Available; allocating inventory.") == "limited"
    assert C.availability_class("Backordered. Next release not available") == "unavailable"
    assert C.availability_class("Next Delivery and Estimated Recovery: June 2024") == "other"
    assert C.availability_is_bare("Limited Availability")
    assert not C.availability_is_bare("Out of Stock - Resupply TBD")
    assert C.extract_ndcs("(NDC 64679-0961-05)") == C.extract_ndcs("(NDC 64679-961-05)")
    assert "00409798423" in C.extract_ndcs("Legacy Hospira NDC 0409-7984-23")


def test_statement_level_outcome_waits_for_every_presentation(tmp_path: Path) -> None:
    text = "Estimated recovery: March 2022"
    p30 = "30 mg vial (NDC 12345-680-90)"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [
                row(P10, "Revised", "12/20/2021", "Unavailable", text),
                row(P20, "Revised", "12/20/2021", "Unavailable", text),
                row(p30, "Revised", "12/20/2021", "Unavailable", "Estimated recovery: TBD"),
            ],
            "20220201000000": [
                row(P10, "Revised", "12/20/2021", "Available", text),
                row(P20, "Revised", "12/20/2021", "Unavailable", text),
                row(p30, "Revised", "12/20/2021", "Unavailable", "Estimated recovery: TBD"),
            ],
            "20220301000000": [
                row(P10, "Revised", "12/20/2021", "Available", text),
                row(P20, "Revised", "12/20/2021", "Limited Availability", text),
                row(p30, "Revised", "12/20/2021", "Unavailable", "Estimated recovery: TBD"),
            ],
            "20220401000000": [
                row(P10, "Revised", "12/20/2021", "Available", text),
                row(P20, "Revised", "12/20/2021", "Available", text),
            ],
        },
    )
    ev = corpus.events.set_index("presentation")
    assert ev.at[P10, "statement_group_id"] == ev.at[P20, "statement_group_id"]
    assert ev.at[P10, "statement_group_id"] != ev.at[p30, "statement_group_id"]
    out = corpus.outcomes.set_index("event_id")
    group = out.loc[ev.at[P10, "event_id"]]
    assert group["group_n_presentations"] == 2
    assert group["group_outcome_B"] == "recovered"
    assert (group["group_lower_date_B"], group["group_upper_date_B"]) == (
        "2022-03-01",
        "2022-04-01",
    )
    assert group["group_observable31_B"]
    limited = out.loc[ev.at[P20, "event_id"]]
    assert limited["outcome_BL"] == "recovered" and limited["upper_date_BL"] == "2022-03-01"
    assert limited["outcome_B"] == "recovered" and limited["upper_date_B"] == "2022-04-01"
    left = out.loc[ev.at[p30, "event_id"]]
    assert left["outcome_B"] == "censored" and left["censor_reason_B"] == "absent_generic_current"
    assert left["exit_date_B"] == "2022-04-01" and left["group_outcome_B"] == "censored"


# ---------------------------------------------------------------------------
# Availability rule
# ---------------------------------------------------------------------------

ON_HAND = (
    "Available",
    "Inventory is currently available.",
    "Currently available, in stock, production is ongoing",
    "Product available in all wholesalers",
    "Available; additional units expected to release mid-March 2021",
    "Available. Next expected release mid-November",
    "Available; next batch will be available May 2022",
    "Product is currently available with one additional batch to be available late February 2024",
    "Product available until mid-November",
    "Product available as of July 1, 2022",
    "Available, 6 months",
    "Available, Q2 2024",
    "Available (expires 11/30/24)",
    "8 month expiry (4/2022 expiry) dating available by request",
    "Available; shortage anticipated in December 2023",
    "Product continues to be available",
    "Product has become available",
    "In stock; may ship late",
    "Available at this time",
    "Available at all wholesalers",
    "Product available upon request",
    "Available may be delayed",
    "We have product available",
    "Product will continue to have supply available",
    "Available 6 months dating",
    "Available 30 days coverage",
)
NOT_ON_HAND = (
    "Available by 4/5/19",
    "No release date available at this time",
    "Will be available in June",
    "Product will be made available as it is released, TBD",
    "We anticipate product will be available by the end of September or early October 2020",
    "Additional supply to be available in May 2020",
    "Product may be available in 4-6 weeks",
    "Tentatively available by end of October 2023",
    "Estimated date available; TBD",
    "Expected to become available next month",
    "Available in February 2024",
    "Available in January as NDC 25021-687-05",
    "Available March 2019",
    "Available May 2022",
    "Available from April 3rd 2023",
    "Available end of December 2022",
    "New lots available not sooner than January 2021, conditional to manufacturing capacity",
    "Stock sold out. Product has arrived, will be available for sale wk of 12/9/19",
    "Back in stock week 3 of May 2020",
    "Supply available TBD",
    "Not yet available",
    "Availability expected Q3",
    "Estimated availability Dec-2020",
    "Available soon",
    "Product available shortly",
    "Available upon release",
    "Next available date June 2021",
    "Will have product available",
    "Nothing available",
    "Available March",
    "Available early next year",
    "Available mid to late June",
    "Available at the end of March",
    "Available the first week of May",
    "Available within 2 weeks",
    "Available in approximately 2 weeks",
    "Available on or about June 1",
    "Available next week",
    "Available this month",
    "Product will become available",
    "Tentatively available",
    "Available for shipment in June",
    "Available again in June 2021",
    "Available to order 6/1/21",
    "None available",
    "Product isn't available",
)


@pytest.mark.parametrize("text", ON_HAND)
def test_available_when_supply_is_on_hand_now(text: str) -> None:
    assert C.availability_class(text) == "available"
    assert C.availability_class_before_fix(text) == "available"


@pytest.mark.parametrize("text", NOT_ON_HAND)
def test_future_estimated_or_negated_available_is_not_available(text: str) -> None:
    assert C.availability_class(text) == "other"


def test_fix_moves_strings_only_out_of_available() -> None:
    moved = [t for t in NOT_ON_HAND if C.availability_class_before_fix(t) == "available"]
    assert len(moved) == len(NOT_ON_HAND) - 2  # "availability" alone never read as available
    unchanged = {
        "": "blank",
        "Not available": "unavailable",
        "Backordered. Product will be available in June": "unavailable",
        "Limited Availability": "limited",
        "Available on allocation": "limited",
        "Limited supply will be available in June": "limited",
        "Limited supply; on backorder": "unavailable",
        "Next Delivery and Estimated Recovery: June 2024": "other",
    }
    for text, expected in unchanged.items():
        assert C.availability_class(text) == expected, text
        assert C.availability_class_before_fix(text) == expected, text


def test_frozen_rejection_list_is_well_formed() -> None:
    rejected = C.REJECTED_AVAILABLE
    assert isinstance(rejected, tuple) and len(set(rejected)) == len(rejected)
    for text in rejected:
        assert text and C.availability_key(text) == text, text
        assert C.availability_class_before_fix(text) in C.SUPPLY_CLASSES, text
        assert C.availability_class(text) == "other", text


def test_rejected_strings_are_neither_available_nor_limited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rejected = ("available stock pending shipment to private labeler", "limited supply")
    assert C.availability_class("Available stock pending shipment to private labeler.") == (
        "available"
    )
    monkeypatch.setattr(C, "REJECTED_AVAILABLE", rejected)
    assert C.availability_key(" Limited  SUPPLY. ") == "limited supply"
    # Matched on the whole normalised string: case, spacing and edge punctuation do not matter.
    assert C.availability_class("Available stock  pending shipment to private labeler.") == "other"
    assert C.availability_class("Limited Supply") == "other"
    assert C.availability_class("Limited supply available") == "limited"
    assert C.availability_class("Available") == "available"
    assert C.availability_class_before_fix("Limited supply") == "limited"
    text = "Estimated recovery: March 2022"
    held = "Available stock pending shipment to private labeler"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "Revised", "12/20/2021", held, text)],
            "20220201000000": [row(P10, "Revised", "12/20/2021", held, text)],
            "20220301000000": [row(P10, "Revised", "12/20/2021", "Available", text)],
        },
    )
    ev = events_of(corpus, P10).iloc[0]
    out = outcome(corpus, ev["event_id"])
    assert ev["availability_class"] == "other"
    assert out["at_risk_B"] and out["at_risk_BL"] and out["outcome_B"] == "recovered"
    assert (out["lower_date_B"], out["upper_date_B"]) == ("2022-02-01", "2022-03-01")
    table = C.availability_strings(corpus.captures.obs).set_index("string")
    assert table.at[rejected[0], "class_after_fix"] == "other"
    assert table.at[rejected[0], "class_before_fix"] == "available"


def test_check_list_and_rejection_list_hold_no_email_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = "Limited; contact Acme at 1-800-000-0000 or Orders.US@acme-pharma.example.com."
    key = "limited; contact acme at 1-800-000-0000 or [email]"
    assert C.availability_key(raw) == key
    write_capture(tmp_path, "20220101000000", [row(P10, "Revised", "12/20/2021", raw, "TBD")])
    table = C.availability_strings(C.load_captures(tmp_path).obs)
    assert [tuple(r) for r in table.itertuples(index=False)] == [(key, "limited", "limited", 1)]
    assert C.availability_class(raw) == "limited"
    monkeypatch.setattr(C, "REJECTED_AVAILABLE", (key,))
    assert C.availability_class(raw) == "other"
    table = C.availability_strings(C.load_captures(tmp_path).obs)
    assert [tuple(r) for r in table.itertuples(index=False)] == [(key, "other", "limited", 1)]


def test_committed_check_list_is_what_the_rule_gives() -> None:
    """The list the author checked (``out/availability_strings.csv``) against the rule in the
    builder: every listed string gets the classes the list shows, a class changed only by leaving
    available (or by rejection), and no string holds an address. A change of the rule that moves
    a listed string fails here until the list is written again and checked again."""
    path = Path(C.__file__).parent / "out" / C.STRINGS_PATH.name
    if not path.exists():
        pytest.skip(f"{path} is not on disk")
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert tuple(table.columns[: len(C.STRING_COLUMNS)]) == C.STRING_COLUMNS
    assert len(table) and table["string"].is_unique
    assert (table["n_rows"].astype(int) > 0).all()
    assert not table["string"].str.contains("@").any()
    rejected = set(C.REJECTED_AVAILABLE)
    assert rejected <= set(table["string"])
    rows = zip(table["string"], table["class_after_fix"], table["class_before_fix"], strict=True)
    for text, after, before in rows:
        assert C.availability_key(text) == text, text
        assert C.availability_class(text) == after, text
        assert C.availability_class_before_fix(text) == before, text
        assert before in C.SUPPLY_CLASSES, text
        assert after == before or after == "other", text
        if after != before:
            assert before == "available" or text in rejected, text


def test_a_future_available_is_no_recovery_and_leaves_the_event_at_risk(tmp_path: Path) -> None:
    text = "Estimated recovery: June 2022"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "Revised", "12/20/2021", "Unavailable", text)],
            "20220201000000": [row(P10, "Revised", "01/25/2022", "Available in March 2022", text)],
            "20220301000000": [row(P10, "Revised", "02/25/2022", "Available", text)],
        },
    )
    ev = events_of(corpus, P10)
    assert list(ev["availability_class"]) == ["unavailable", "other", "available"]
    first, second, third = (outcome(corpus, e) for e in ev["event_id"])
    assert first["outcome_B"] == "recovered"
    assert (first["lower_date_B"], first["upper_date_B"]) == ("2022-02-01", "2022-03-01")
    assert second["at_risk_B"] and second["at_risk_BL"] and second["outcome_B"] == "recovered"
    assert (second["lower_date_B"], second["upper_date_B"]) == ("2022-02-01", "2022-03-01")
    assert not third["at_risk_B"] and third["outcome_B"] == "not_at_risk"


def test_availability_strings_check_list(tmp_path: Path) -> None:
    caps = tmp_path / "caps"
    caps.mkdir()
    text = "Estimated recovery: March 2022"
    p30 = "30 mg vial (NDC 12345-680-90)"
    for stamp in ("20220101000000", "20230601000000"):
        write_capture(
            caps,
            stamp,
            [
                row(P10, "Revised", "12/20/2021", "Available", text),
                row(P20, "Revised", "12/20/2021", "AVAILABLE.", text),
                row(p30, "Revised", "12/20/2021", "Available by 4/5/22", text),
                row("40 mg (NDC 12345-681-90)", "Revised", "12/20/2021", "Unavailable", text),
                row("50 mg (NDC 12345-682-90)", "Revised", "12/20/2021", "", text),
                row("60 mg (NDC 12345-683-90)", "Revised", "12/20/2021", "Limited Availability"),
                row("70 mg (NDC 12345-684-90)", "Revised", "12/20/2021", "Recovery: June 2022"),
            ],
        )
    expected = [
        ("available", "available", "available", 4),
        ("limited availability", "limited", "limited", 2),
        ("available by 4/5/22", "other", "available", 2),
    ]
    table = C.availability_strings(C.load_captures(caps).obs)
    assert (
        tuple(table.columns)
        == C.STRING_COLUMNS
        == (
            "string",
            "class_after_fix",
            "class_before_fix",
            "n_rows",
        )
    )
    assert [tuple(r) for r in table.itertuples(index=False)] == expected
    path = tmp_path / "out" / "availability_strings.csv"
    assert C.write_availability_strings(caps, path) == 3
    first = path.read_bytes()
    written = pd.read_csv(path, keep_default_na=False)
    assert list(written.columns) == list(C.STRING_COLUMNS)
    assert [tuple(r) for r in written.itertuples(index=False)] == expected
    assert C.write_availability_strings(caps, path) == 3 and path.read_bytes() == first
    assert list(tmp_path.glob("**/*.gz")) == []  # nothing else is written, nothing sealed
    # A copy that carries the author's marks is never overwritten.
    path.write_text(written.assign(ok="yes").to_csv(index=False))
    with pytest.raises(SystemExit):
        C.write_availability_strings(caps, path)
    assert "ok" in path.read_text().splitlines()[0]


# ---------------------------------------------------------------------------
# Gate 1 counts, report and manifest hook
# ---------------------------------------------------------------------------


def gate_captures() -> dict[str, list[list[str]]]:
    """Four dated test-period events: one observable before 2024, one observable after, one
    with a 121-day bracket after, and one first seen at the last capture."""
    p30, p40 = "30 mg vial (NDC 12345-680-90)", "40 mg vial (NDC 12345-681-90)"
    e1, e2 = "Estimated recovery: March 2023", "Estimated recovery: February 2024"
    e3, e4 = "Next delivery: April 2024", "Estimated recovery: July 2024"
    return {
        "20230110000000": [row(P10, "Revised", "01/05/2023", "Unavailable", e1)],
        "20230201000000": [row(P10, "Revised", "01/05/2023", "Available", e1)],
        "20240105000000": [
            row(P20, "Revised", "01/03/2024", "Unavailable", e2),
            row(p30, "Revised", "01/03/2024", "Unavailable", e3),
        ],
        "20240201000000": [
            row(P20, "Revised", "01/03/2024", "Available", e2),
            row(p30, "Revised", "01/03/2024", "Unavailable", e3),
        ],
        "20240601000000": [
            row(P20, "Revised", "01/03/2024", "Available", e2),
            row(p30, "Revised", "01/03/2024", "Available", e3),
            row(p40, "Revised", "05/20/2024", "Unavailable", e4),
        ],
    }


def test_gate_counts_and_the_cutoff_argument(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = build(tmp_path, gate_captures())
    assert pd.Timestamp("2023-12-31") == C.CUTOFF
    counts = C.gate_counts(corpus)
    assert counts == {
        "statement_events": 4,
        "distinct_statements": 4,
        "episodes": 1,
        "observable31_B_events": 2,
        "observable31_B_distinct": 2,
        "after_cutoff_observable31_B_events": 1,
        "after_cutoff_observable31_B_distinct": 1,
        "observable31_A_events": 0,
        "observable31_A_distinct": 0,
        "after_cutoff_observable31_A_events": 0,
        "after_cutoff_observable31_A_distinct": 0,
        "after_cutoff_events": 3,
        "after_cutoff_distinct": 3,
        "after_cutoff_with_followup": 2,
        "after_cutoff_distinct_with_followup": 2,
    }
    assert all(isinstance(v, int) for v in counts.values())
    early = C.gate_counts(corpus, pd.Timestamp("2022-12-31"))
    assert early["after_cutoff_observable31_B_distinct"] == 2 and early["after_cutoff_events"] == 4
    late = C.gate_counts(corpus, "2024-01-31")  # a date string works too
    assert late["after_cutoff_observable31_B_events"] == 0 and late["after_cutoff_events"] == 1
    assert late["after_cutoff_with_followup"] == 0
    # The first three thresholds do not depend on the cutoff.
    fixed = [k for k in counts if not k.startswith("after_cutoff")]
    assert all(counts[k] == early[k] == late[k] for k in fixed)
    # The cutoff is a month: any day of it gives the counts of its last day.
    assert C.cutoff_day("2024-02-10") == pd.Timestamp("2024-02-29") == C.cutoff_day("2024-02-29")
    assert C.gate_counts(corpus, "2024-01-01") == late
    assert C.gate_counts(corpus, pd.Timestamp("2023-12-01")) == counts
    C.print_report(corpus, late, C.gap_summary(corpus.captures.dates), pd.Timestamp("2024-01-31"))
    printed = capsys.readouterr().out
    assert "dated after 2024-01-31, observable outcome, definition B: presentation-level" in printed
    assert "events 0, distinct statements 0 (need >= 150)" in printed
    assert "with follow-up 0, distinct with follow-up 0 (no threshold)" in printed
    # The thresholds on observable outcomes are on definition B; A is printed without one.
    lines = printed.splitlines()
    for need in ("(need >= 250)", "(need >= 150)"):
        assert [line for line in lines if need in line and "definition B" not in line] == []
        assert sum(need in line for line in lines) == 1
    secondary = [line for line in lines if "definition A" in line]
    assert len(secondary) == 2
    assert all(line.endswith("(secondary, no threshold)") for line in secondary)


def test_gate_set_and_the_day_after_the_cutoff(tmp_path: Path) -> None:
    beta = "Beta Tablets"
    p30, p40 = "30 mg vial (NDC 12345-680-90)", "40 mg vial (NDC 12345-681-90)"
    p50, p60 = "50 mg vial (NDC 12345-682-90)", "60 mg vial (NDC 12345-683-90)"
    p70, p80 = "70 mg vial (NDC 12345-684-90)", "80 mg vial (NDC 12345-685-90)"
    p90, p95 = "90 mg vial (NDC 12345-686-90)", "95 mg vial (NDC 12345-687-90)"
    before, on_day, after = "Recovery: March 2024", "Recovery: April 2024", "Recovery: May 2024"
    pair, undated, year26 = "Next delivery: June 2024", "Estimated recovery: TBD", "Mar 2026"
    down, up = "Unavailable", "Available"

    def listing(state: dict[str, str]) -> list[list[str]]:
        """The rows of one 2024 capture; ``state`` gives each presentation's availability."""
        return [
            row(P10, "Revised", "12/15/2023", state["a"], before),
            row(P20, "Revised", "12/31/2023", state["b1"], on_day, generic=beta),
            row(p30, "Revised", "01/01/2024", state["b2"], after, generic=beta),
            row(p40, "Revised", "01/01/2024", state["g1"], pair),
            row(p50, "Revised", "01/01/2024", state["g2"], pair),
            row(p60, "Revised", "01/01/2024", state["x1"], undated),  # no date-like phrase
            row(p70, "Revised", "01/01/2024", "", "Recovered in January 2024", "Resolved"),
            row(p80, "New", "01/01/2024", "", "Stops in March 2024", "To Be Discontinued"),
        ]

    first = dict.fromkeys(("a", "b1", "b2", "g1", "g2", "x1"), down) | {"a": up}
    corpus = build(
        tmp_path,
        {
            "20221201000000": [row(p95, "Revised", "11/20/2022", down, "Recovery: March 2023")],
            "20231220000000": [row(P10, "Revised", "12/15/2023", down, before)],
            "20240102000000": listing(first),
            "20240120000000": listing(dict.fromkeys(first, up) | {"g2": down}),
            "20240601000000": listing(dict.fromkeys(first, up)),
            "20260105000000": [row(p90, "Revised", "01/02/2026", down, year26)],  # after 2025
            "20260120000000": [row(p90, "Revised", "01/02/2026", up, year26)],
        },
    )
    ev = corpus.events.set_index("presentation")
    out = corpus.outcomes.set_index("event_id")
    # Every excluded event has an observable bracket or a date of its own, so only the gate's
    # conditions keep it out: no date-like phrase, not Current, the other listing, 2026, train.
    assert out.loc[ev.at[p60, "event_id"], "observable31_B"] and not ev.at[p60, "has_date_like"]
    assert ev.at[p70, "status_at_statement"] == "resolved" and ev.at[p70, "has_date_like"]
    assert ev.at[p80, "listing"] == "discontinuation" and ev.at[p80, "has_date_like"]
    assert out.loc[ev.at[p90, "event_id"], "observable31_B"] and ev.at[p90, "has_date_like"]
    assert ev.at[p95, "period"] == "train" and ev.at[p95, "has_date_like"]
    # One statement covers two presentations: one recovers within 31 days, the other later, so
    # one event is observable and the statement is not.
    assert ev.at[p40, "statement_group_id"] == ev.at[p50, "statement_group_id"]
    one, other = (out.loc[ev.at[p, "event_id"]] for p in (p40, p50))
    assert one["observable31_B"] and not other["observable31_B"]
    assert not one["group_observable31_B"] and one["group_width_days_B"] == 133
    expected = {
        "statement_events": 5,
        "distinct_statements": 4,
        "episodes": 2,
        "observable31_B_events": 4,
        "observable31_B_distinct": 3,
        "after_cutoff_observable31_B_events": 2,
        "after_cutoff_observable31_B_distinct": 1,
        "observable31_A_events": 0,
        "observable31_A_distinct": 0,
        "after_cutoff_observable31_A_events": 0,
        "after_cutoff_observable31_A_distinct": 0,
        "after_cutoff_events": 3,
        "after_cutoff_distinct": 2,
        "after_cutoff_with_followup": 3,
        "after_cutoff_distinct_with_followup": 2,
    }
    # An event dated on the last day of the cutoff month (2023-12-31) is not after the cutoff.
    assert C.gate_counts(corpus) == expected == C.gate_counts(corpus, "2023-12-05")
    earlier = C.gate_counts(corpus, "2023-11-30")
    assert earlier["after_cutoff_events"] == 5 and earlier["after_cutoff_distinct"] == 4
    assert earlier["after_cutoff_observable31_B_events"] == 4
    assert earlier["after_cutoff_observable31_B_distinct"] == 3
    later = C.gate_counts(corpus, "2024-01-01")  # January 2024: nothing is dated after it
    assert later["after_cutoff_events"] == 0 and later["after_cutoff_observable31_B_events"] == 0


def test_fourth_gate_count_is_on_observable_events_not_on_followed_ones(tmp_path: Path) -> None:
    text = "Estimated recovery: March 2024"
    corpus = build(
        tmp_path,
        {
            "20240105000000": [
                row(P10, "Revised", "01/03/2024", "Unavailable", text),
                row(P20, "Revised", "01/03/2024", "Unavailable", text),
            ],
            "20240201000000": [row(P20, "Revised", "01/03/2024", "Unavailable", text, "Resolved")],
        },
    )
    # P10 leaves the list while its generic is Resolved: recovered within 31 days, although no
    # later capture lists its thread. The older check ("with follow-up") does not count it.
    gone = outcome(corpus, events_of(corpus, P10).iloc[0]["event_id"])
    assert gone["observable31_B"] and gone["event_via_B"] == "exit_generic_resolved"
    assert gone["n_followup_listed"] == 0
    counts = C.gate_counts(corpus)
    assert counts["after_cutoff_observable31_B_events"] == 2
    assert counts["after_cutoff_observable31_B_distinct"] == 1
    assert counts["after_cutoff_with_followup"] == 1
    assert counts["after_cutoff_distinct_with_followup"] == 1
    assert counts["after_cutoff_events"] == 2 and counts["after_cutoff_distinct"] == 1


def test_report_counts_realigned_rows_per_capture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "Estimated recovery: March 2022"
    broken = (
        '"Alpha Injection","Acme Pharma","800","ALPHA-PF 10%", Sulfite-Free, (Pediatric) 1 L '
        '(NDC 12345-222-33)"","Revisee","12/22/2021","Unavailable","Late January 2022","",'
        '"","Anesthesia","Current","","","01/05/2021"\r\n'
    )
    short = '"Alpha Injection","Acme Pharma","800","5 mg (NDC 12345-555-11)","New"\r\n'
    good = [row(P10, "Revised", "12/20/2021", "Unavailable", text)]
    write_capture(tmp_path, "20220101000000", good, raw_lines=(broken, short))
    write_capture(tmp_path, "20220201000000", good)
    write_capture(tmp_path, "20220301000000", good, raw_lines=(broken,))
    corpus = C.build_corpus(tmp_path)
    # Counted as read: the padded short row has no status and is dropped afterwards.
    assert corpus.captures.realigned == {
        "20220101000000": 2,
        "20220201000000": 0,
        "20220301000000": 1,
    }
    assert int(corpus.captures.obs["row_repaired"].sum()) == 2
    C.print_report(corpus, C.gate_counts(corpus), C.gap_summary(corpus.captures.dates))
    lines = capsys.readouterr().out.splitlines()
    assert "realigned rows as read, per capture: 3 in 2 of 3 captures (none in the others)" in lines
    assert "  20220101000000: 2" in lines and "  20220301000000: 1" in lines
    assert not any(line.startswith("  20220201000000") for line in lines)
    assert any("realigned among those kept: 2" in line for line in lines)


def test_manifest_hook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert C.MANIFEST_MODULE == "analysis.coling.manifest"
    # No such module: nothing is checked, and nothing is imported.
    assert C.verify_manifest(tmp_path, module="analysis.coling.no_such_manifest") is False
    assert C.verify_manifest(tmp_path, module="no_such_package.manifest") is False
    seen: list[Path] = []
    monkeypatch.setitem(sys.modules, "fake_manifest", types.SimpleNamespace(verify=seen.append))
    assert C.verify_manifest(tmp_path, module="fake_manifest") is True and seen == [tmp_path]
    monkeypatch.setitem(
        sys.modules, "fake_manifest", types.SimpleNamespace(verify=lambda directory: False)
    )
    with pytest.raises(SystemExit):
        C.verify_manifest(tmp_path, module="fake_manifest")
    listing = types.SimpleNamespace(verify=lambda directory: ["x.csv: not in the manifest"])
    monkeypatch.setitem(sys.modules, "fake_manifest", listing)
    with pytest.raises(SystemExit, match="not in the manifest"):
        C.verify_manifest(tmp_path, module="fake_manifest")
    monkeypatch.setitem(sys.modules, "fake_manifest", types.SimpleNamespace(verify=lambda d: []))
    assert C.verify_manifest(tmp_path, module="fake_manifest") is True

    def mismatch(directory: Path) -> None:
        raise ValueError(f"{directory}: 1 file not in the manifest")

    monkeypatch.setitem(sys.modules, "fake_manifest", types.SimpleNamespace(verify=mismatch))
    with pytest.raises(ValueError, match="not in the manifest"):
        C.verify_manifest(tmp_path, module="fake_manifest")
    # A manifest module that exists but cannot be imported is an error, not a skipped check.
    (tmp_path / "broken_manifest.py").write_text("import surely_not_an_installed_module\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError):
        C.verify_manifest(tmp_path, module="broken_manifest")


def test_manifest_module_refuses_another_capture_set(tmp_path: Path) -> None:
    pytest.importorskip(C.MANIFEST_MODULE)  # written separately; skipped while it is absent
    write_capture(tmp_path, "20220101000000", [row(P10, "Revised", "12/20/2021", "Unavailable")])
    with pytest.raises(SystemExit):
        C.verify_manifest(tmp_path)
    out, sealed = tmp_path / "out", tmp_path / "sealed"
    with pytest.raises(SystemExit):
        C.main(["--captures", str(tmp_path), "--out", str(out), "--sealed", str(sealed)])
    assert not out.exists() and not sealed.exists()


def test_main_checks_the_manifest_before_anything_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    caps, out, sealed = tmp_path / "caps", tmp_path / "out", tmp_path / "sealed"
    caps.mkdir()
    for stamp, rows in gate_captures().items():
        write_capture(caps, stamp, rows)
    args = ["--captures", str(caps), "--out", str(out), "--sealed", str(sealed)]

    def refuse(directory: Path) -> None:
        raise ValueError(f"{directory} does not match the manifest")

    with pytest.raises(ValueError, match="does not match"):
        C.main(args, check=refuse)
    assert not out.exists() and not sealed.exists()
    seen: list[Path] = []
    assert C.main([*args, "--cutoff", "2024-01-31"], check=seen.append) == 0
    printed = capsys.readouterr().out
    assert seen == [caps] and "capture manifest: verified" in printed
    assert "dated after 2024-01-31, observable outcome, definition B" in printed
    assert sorted(p.name for p in out.iterdir()) == ["events.csv.gz", "outcomes_train.csv.gz"]
    assert sorted(p.name for p in sealed.iterdir()) == [
        "outcomes_test.csv.gz",
        "outcomes_train_uncensored.csv.gz",
    ]
    # With no manifest module the default check reports that it checked nothing.
    assert C.main(args, check=lambda directory: False) == 0
    assert "capture manifest: NOT checked" in capsys.readouterr().out


def test_check_runs_before_the_captures_are_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caps = tmp_path / "caps"
    caps.mkdir()
    write_capture(caps, "20220101000000", [row(P10, "Revised", "12/20/2021", "Unavailable")])
    order: list[str] = []
    real = C.build_corpus

    def building(directory: Path) -> C.Corpus:
        order.append("build")
        return real(directory)

    monkeypatch.setattr(C, "build_corpus", building)
    args = ["--captures", str(caps), "--out", str(tmp_path / "o"), "--sealed", str(tmp_path / "s")]
    assert C.main(args, check=lambda directory: order.append("check")) == 0
    assert order == ["check", "build"]


def test_open_build_writes_the_open_tables_and_seals_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    caps, out, full = tmp_path / "caps", tmp_path / "out", tmp_path / "full"
    caps.mkdir()
    for stamp, rows in gate_captures().items():
        write_capture(caps, stamp, rows)
    write_capture(caps, "20221201000000", [row(P10, "Revised", "11/20/2022", "Unavailable", "TBD")])
    seen: list[Path] = []
    corpus = C.open_build(caps, out, cutoff="2024-01-15", check=seen.append)
    printed = capsys.readouterr().out
    assert seen == [caps] and "capture manifest: verified" in printed
    assert "dated after 2024-01-31, observable outcome, definition B" in printed
    assert "sealed" not in printed
    assert sorted(p.name for p in tmp_path.rglob("*.gz")) == [
        "events.csv.gz",
        "outcomes_train.csv.gz",
    ]
    train = pd.read_csv(out / "outcomes_train.csv.gz", keep_default_na=False)
    assert len(train) == 1 and set(train["period"]) == {"train"}
    assert len(pd.read_csv(out / "events.csv.gz")) == len(corpus.events) == 5
    for name in ("events.csv.gz", "outcomes_train.csv.gz"):
        digest = hashlib.sha256((out / name).read_bytes()).hexdigest()
        assert f"wrote {out / name} sha256 {digest}" in printed
    # The freeze run writes the same two files, byte for byte, beside the sealed ones.
    args = ["--captures", str(caps), "--out", str(full), "--sealed", str(tmp_path / "sealed")]
    assert C.main(args, check=None) == 0
    for name in ("events.csv.gz", "outcomes_train.csv.gz"):
        assert (full / name).read_bytes() == (out / name).read_bytes()


def test_rejected_string_in_no_capture_stops_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    caps, out, sealed = tmp_path / "caps", tmp_path / "out", tmp_path / "sealed"
    caps.mkdir()
    for stamp, rows in gate_captures().items():
        write_capture(caps, stamp, rows)
    args = ["--captures", str(caps), "--out", str(out), "--sealed", str(sealed)]
    assert C.unseen_rejections(C.load_captures(caps).obs) == []
    monkeypatch.setattr(C, "REJECTED_AVAILABLE", ("available", "availabel"))
    assert C.unseen_rejections(C.load_captures(caps).obs) == ["availabel"]
    with pytest.raises(SystemExit, match="availabel"):
        C.main(args, check=None)
    with pytest.raises(SystemExit, match="in no capture"):
        C.open_build(caps, out, check=None)
    assert not out.exists() and not sealed.exists()
    # Every entry is carried by a capture row: the build runs and reports the list.
    monkeypatch.setattr(C, "REJECTED_AVAILABLE", ("available",))
    capsys.readouterr()
    assert C.main(args, check=None) == 0
    assert "rejected by the author: 1 (0 of them in no capture)" in capsys.readouterr().out
    events = pd.read_csv(out / "events.csv.gz", keep_default_na=False)
    assert set(events["availability_class"]) == {"unavailable"}  # first sight; later rows other


def test_capture_with_a_header_and_no_rows_is_skipped(tmp_path: Path) -> None:
    text = "Estimated recovery: March 2022"
    write_capture(
        tmp_path, "20220101000000", [row(P10, "Revised", "12/20/2021", "Unavailable", text)]
    )
    write_capture(tmp_path, "20220201000000", [])
    write_capture(
        tmp_path, "20220301000000", [row(P10, "Revised", "12/20/2021", "Available", text)]
    )
    with pytest.raises(C.CaptureFormatError, match="no rows"):
        C.read_capture(tmp_path / "20220201000000.csv")
    corpus = C.build_corpus(tmp_path)
    assert corpus.captures.stamps == ["20220101000000", "20220301000000"]
    assert corpus.captures.skipped == ["20220201000000.csv: a header and no rows"]
    assert sorted(corpus.captures.realigned) == corpus.captures.stamps
    # The empty file is no capture, so it is no absence either: one event, recovered.
    assert len(corpus.events) == 1
    out = outcome(corpus, corpus.events.iloc[0]["event_id"])
    assert (out["lower_date_B"], out["upper_date_B"]) == ("2022-01-01", "2022-03-01")


# ---------------------------------------------------------------------------
# Edge cases of follow-up, censoring, dating and statement groups
# ---------------------------------------------------------------------------


def date_values(record: pd.Series) -> list[str]:
    """Every ISO date held in an outcome row."""
    return [v for v in record.to_numpy() if isinstance(v, str) and len(v) == 10 and v[4] == "-"]


def test_implausible_reconfirmation_date_is_never_the_last_reconfirmed_date(
    tmp_path: Path,
) -> None:
    text = "Estimated recovery: March 2022"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [
                row(P10, "Revised", "12/20/2021", "Unavailable", text),
                row(P20, "Revised", "12/20/2021", "Unavailable", text),
            ],
            "20220201000000": [
                row(P10, "Reverified", "01/25/2022", "Unavailable", text),
                row(P20, "Reverified", "01/25/2201", "Unavailable", text),
            ],
            "20220301000000": [
                row(P10, "Reverified", "02/25/2202", "Unavailable", text),
                row(P20, "Reverified", "01/25/2201", "Unavailable", text),
            ],
        },
    )
    assert len(corpus.events) == 2  # the mistyped stamps start no new event
    typo_last = outcome(corpus, events_of(corpus, P10).iloc[0]["event_id"])
    assert typo_last["n_reconfirmations"] == 2 and typo_last["n_reconfirm_dates_implausible"] == 1
    assert typo_last["last_reconfirmed_date"] == "2022-01-25"
    typo_only = outcome(corpus, events_of(corpus, P20).iloc[0]["event_id"])
    assert typo_only["n_reconfirmations"] == 1 and typo_only["n_reconfirm_dates_implausible"] == 1
    assert typo_only["last_reconfirmed_date"] == ""
    last_capture = "2022-03-01"
    for frame in (corpus.outcomes, corpus.train_uncensored):
        for _, record in frame.iterrows():
            assert all(v <= last_capture for v in date_values(record))


def test_train_event_first_seen_in_the_test_period_has_no_followup(tmp_path: Path) -> None:
    old, late = "Estimated recovery: March 2023", "Estimated recovery: February 2023"
    corpus = build(
        tmp_path,
        {
            "20221006000000": [row(P10, "Revised", "09/20/2022", "Unavailable", old)],
            "20230113000000": [
                row(P10, "Revised", "09/20/2022", "Unavailable", old),
                row(P20, "Revised", "12/28/2022", "Unavailable", late),
            ],
            "20230201000000": [
                row(P10, "Revised", "09/20/2022", "Unavailable", old),
                row(P20, "Reverified", "01/30/2023", "Available", late),
            ],
            "20230301000000": [row(P20, "Revised", "02/20/2023", "", "", "Resolved")],
        },
    )
    ev = events_of(corpus, P20).iloc[0]
    assert ev["period"] == "train" and ev["event_date"] == "2022-12-28"
    assert ev["first_seen_date"] == "2023-01-13" and ev["days_capture_after_event"] == 16
    out = outcome(corpus, ev["event_id"])
    for d in C.DEFINITIONS:
        assert out[f"at_risk_{d}"] and out[f"outcome_{d}"] == "censored"
        assert out[f"censor_reason_{d}"] == "end_of_train"
        assert out[f"lower_date_{d}"] == "2023-01-13" and out[f"upper_date_{d}"] == ""
        assert out[f"exit_date_{d}"] == "" and not out[f"observable31_{d}"]
        assert out[f"group_outcome_{d}"] == "censored" and out[f"group_upper_date_{d}"] == ""
    assert out["n_followup_captures"] == 0 and out["n_followup_listed"] == 0
    assert out["n_reconfirmations"] == 0 and out["last_reconfirmed_date"] == ""
    assert out["next_event_id"] == "" and out["date_discontinued_on_row_date"] == ""
    assert out["followup_end_date"] == "2023-01-13" == out["run_last_seen_date"]
    # Its own first-seen capture is the only test-period date in the open row.
    dates = date_values(out)
    assert "2023-01-13" in dates
    assert all(v < "2023-01-01" or v == ev["first_seen_date"] for v in dates)
    # An earlier train event on the same listing stops at the last train capture as before.
    earlier = outcome(corpus, events_of(corpus, P10).iloc[0]["event_id"])
    assert earlier["censor_reason_B"] == "end_of_train" and earlier["n_followup_captures"] == 0
    assert all(v < "2023-01-01" for v in date_values(earlier))
    # The sealed, uncensored version follows the thread to its recovery.
    full = corpus.train_uncensored.set_index("event_id").loc[ev["event_id"]]
    assert full["outcome_B"] == "recovered" and full["upper_date_B"] == "2023-02-01"
    assert full["outcome_A"] == "recovered" and full["upper_date_A"] == "2023-03-01"
    assert full["last_reconfirmed_date"] == "2023-01-30"


@pytest.mark.parametrize("year", [2022, 2023])
def test_event_first_seen_at_the_last_capture_has_no_followup(tmp_path: Path, year: int) -> None:
    old, new = f"Estimated recovery: March {year}", f"Estimated recovery: June {year}"
    corpus = build(
        tmp_path,
        {
            f"{year}0201000000": [row(P10, "Revised", f"01/20/{year}", "Unavailable", old)],
            f"{year}0301000000": [
                row(P10, "Revised", f"02/20/{year}", "Unavailable", new),
                row(P20, "New", f"02/25/{year}", "Available", new),
            ],
        },
    )
    first, second = (outcome(corpus, e) for e in events_of(corpus, P10)["event_id"])
    assert first["censor_reason_B"] == "end_of_archive" and first["n_followup_captures"] == 1
    for d in C.DEFINITIONS:
        assert (
            second[f"outcome_{d}"] == "censored" and second[f"censor_reason_{d}"] == "no_followup"
        )
        assert second[f"lower_date_{d}"] == f"{year}-03-01" and second[f"upper_date_{d}"] == ""
        assert second[f"lower_days_{d}"] == 9
    assert second["n_followup_captures"] == 0 and second["n_followup_listed"] == 0
    assert second["followup_end_date"] == f"{year}-03-01"
    # Available at first sight: at risk under A only, and censored there for the same reason.
    listed = outcome(corpus, events_of(corpus, P20).iloc[0]["event_id"])
    assert listed["outcome_A"] == "censored" and listed["censor_reason_A"] == "no_followup"
    assert listed["outcome_B"] == "not_at_risk" and listed["censor_reason_B"] == ""


def test_thread_leaves_while_its_generic_is_unlisted(tmp_path: Path) -> None:
    text = "Estimated recovery: June 2022"
    other = row("5 mg (NDC 55555-111-22)", "Revised", "12/20/2021", "Unavailable", text)
    other[0] = "Beta Tablets"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [row(P10, "Revised", "12/20/2021", "Unavailable", text), other],
            "20220201000000": [row(P10, "Revised", "12/20/2021", "Unavailable", text), other],
            "20220301000000": [other],
            "20220401000000": [other],
        },
    )
    out = outcome(corpus, events_of(corpus, P10).iloc[0]["event_id"])
    for d in C.DEFINITIONS:
        assert out[f"outcome_{d}"] == "censored"
        assert out[f"censor_reason_{d}"] == "absent_generic_unlisted"
        assert out[f"lower_date_{d}"] == "2022-02-01" and out[f"exit_date_{d}"] == "2022-03-01"
    assert out["n_followup_captures"] == 3 and out["n_followup_listed"] == 1
    assert out["run_last_seen_date"] == "2022-02-01"


def test_event_dating_and_duplicate_rows(tmp_path: Path) -> None:
    text = "Estimated recovery: June 2022"
    p30 = "30 mg vial (NDC 12345-680-90)"
    corpus = build(
        tmp_path,
        {
            "20220101000000": [
                row(P10, "Revised", "03/01/2022", "Unavailable", text),  # later than the capture
                row(P20, "Revised", "", "Unavailable", text),  # missing
                row(p30, "Revised", "12/01/2021", "Unavailable", text),
                row(p30, "Revised", "12/20/2021", "Unavailable", text),  # same key, later stamp
                row("40 mg (NDC 12345-681-90)", "Revised", "01/02/2022", "Unavailable", text),
            ],
            "20220201000000": [row(P10, "Revised", "03/01/2022", "Unavailable", text)],
        },
    )
    ev = corpus.events.set_index("presentation")
    assert (ev.at[P10, "event_date"], ev.at[P10, "event_date_source"]) == (
        "2022-01-01",
        "capture:future",
    )
    assert (ev.at[P20, "event_date"], ev.at[P20, "event_date_source"]) == (
        "2022-01-01",
        "capture:missing",
    )
    assert ev.at[p30, "event_date"] == "2021-12-20" and corpus.captures.n_dropped == 1
    # One day of slack: a stamp dated the day after the capture is kept.
    late = ev.loc["40 mg (NDC 12345-681-90)"]
    assert (late["event_date"], late["event_date_source"]) == ("2022-01-02", "dou")
    assert late["days_capture_after_event"] == -1
    assert set(ev["left_truncated"]) == {True}
    assert len(events_of(corpus, P10)) == 1  # the same future stamp is no re-confirmation
    assert outcome(corpus, ev.at[P10, "event_id"])["n_reconfirmations"] == 0


def test_statement_groups_with_mixed_members(tmp_path: Path) -> None:
    mixed, waits, gone = "Recovery: March 2022", "Recovery: April 2022", "Recovery: May 2022"
    p30, p40 = "30 mg vial (NDC 12345-680-90)", "40 mg vial (NDC 12345-681-90)"
    p50, p60 = "50 mg vial (NDC 12345-682-90)", "60 mg vial (NDC 12345-683-90)"

    def shortage(avail: dict[str, str]) -> list[list[str]]:
        texts = {P10: mixed, P20: mixed, p30: mixed, p40: waits, p50: waits, p60: gone}
        return [row(p, "Revised", "12/20/2021", a, texts[p]) for p, a in avail.items()]

    def discontinued(presentation: str) -> list[str]:
        return row(presentation, "New", "02/20/2022", "", "", "To Be Discontinued", "02/20/2022")

    down = "Unavailable"
    corpus = build(
        tmp_path,
        {
            "20220101000000": shortage(
                {P10: down, P20: down, p30: "Available", p40: down, p50: down, p60: down}
            ),
            "20220201000000": shortage(
                {P10: "Available", P20: down, p30: "Available", p40: "Available", p50: down}
                | {p60: down}
            ),
            "20220301000000": [
                *shortage({P10: "Available", p30: "Available", p40: "Available", p50: down}),
                discontinued(P20),
                discontinued(p60),
            ],
        },
    )
    ev = corpus.events[corpus.events["listing"] == "shortage"].set_index("presentation")
    out = corpus.outcomes.set_index("event_id")
    member = {p: out.loc[ev.at[p, "event_id"]] for p in ev.index}
    assert ev.loc[[P10, P20, p30], "statement_group_id"].nunique() == 1
    assert ev.loc[[p40, p50], "statement_group_id"].nunique() == 1
    assert ev["statement_group_id"].nunique() == 3
    # One recovered, one discontinued, one never at risk under B: the group recovers with the
    # member that is left, and the discontinued member does not move its bracket.
    assert [member[p]["outcome_B"] for p in (P10, P20, p30)] == [
        "recovered",
        "discontinued",
        "not_at_risk",
    ]
    for p in (P10, P20, p30):
        group = member[p]
        assert group["group_n_presentations"] == 3 and group["group_outcome_B"] == "recovered"
        assert (group["group_lower_date_B"], group["group_upper_date_B"]) == (
            "2022-01-01",
            "2022-02-01",
        )
        assert group["group_width_days_B"] == 31 and group["group_observable31_B"]
        # Under A all three are at risk and two stay listed as Current: censored at the last
        # capture, whatever the discontinued member did.
        assert group["group_outcome_A"] == "censored" and group["group_upper_date_A"] == ""
        assert group["group_lower_date_A"] == "2022-03-01" and not group["group_observable31_A"]
    assert member[P20]["upper_date_B"] == "2022-03-01"
    # One recovered and one still open: the group waits, censored at the open member's bound.
    for p in (p40, p50):
        group = member[p]
        assert group["group_outcome_B"] == "censored" and group["group_upper_date_B"] == ""
        assert group["group_lower_date_B"] == "2022-03-01" and not group["group_observable31_B"]
    assert member[p40]["outcome_B"] == "recovered" and member[p40]["upper_date_B"] == "2022-02-01"
    # Every member discontinued: the group is discontinued, with the members' bracket.
    alone = member[p60]
    for d in C.DEFINITIONS:
        assert alone[f"group_outcome_{d}"] == "discontinued"
        assert (alone[f"group_lower_date_{d}"], alone[f"group_upper_date_{d}"]) == (
            "2022-02-01",
            "2022-03-01",
        )
        assert alone[f"disc_date_field_{d}"] == "02/20/2022"
