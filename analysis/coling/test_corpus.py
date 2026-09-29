"""Tests for the OpEst-FDA corpus builder on small synthetic captures.

Each test writes two to four fake capture CSVs (FDA header, leading blank line, CRLF endings) to
a temporary directory and builds the corpus from them. Covered: parsing drift (blank lines, BOM,
latin-1, header whitespace, typos in Type of Update, status spellings, a row broken by an
unescaped quote), re-verification, revision, recovery under definitions A and B, exit while the
generic is resolved, right-censoring, discontinuation as a competing event, NDC linking across a
re-formatted presentation, relisting after resolution, the train/test split with sealing, and
timing-phrase extraction.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_corpus.py -q
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
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
    assert C.main(["--captures", str(caps), "--out", str(out), "--sealed", str(sealed)]) == 0
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
    assert "statement events 1;" in printed


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
