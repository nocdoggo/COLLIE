"""Tests for the outcome-audit tooling on small synthetic captures and synthetic keys.

A fake archive of seven train-period captures (one after a gap of more than 90 days) and two
later ones is written to a temporary directory; the same archive shifted by two years gives an
all-test-period corpus for the sealed mode. Two smaller archives carry the cases the first one
lacks. Covered:

* the strata, the allocation, the seeded draw with its caps and its shortfall rule, the assignment;
* exclusion by statement and thread, from sample lists and from the guide's Appendix A;
* the trace window and its clipping at the train horizon, class letters against the builder's own
  reading, NDC links, rows of other threads (withheld for a thread of a labelling sample), masked
  e-mail addresses;
* the four planted errors, and how the kinds are shared out;
* the sheets, their key and manifest, and every stop of the sheet command (no sample list, a list
  from another build, a guide row that matches nothing, a final set in the way, a test half
  outside a sealed folder), the draft mode, a second round and a re-audit of listed items;
* the validator; the scorer, its pass rule, its checks of the set before the key is read, the
  minutes per item and the second pass of a re-check;
* the sealed mode: files only under its directory, counts only on the screen, for the sheets and
  for the score.

Nothing here reads real captures or sealed files.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_audit_outcomes.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from analysis.coling import audit_outcomes as AO
from analysis.coling import corpus as C

HEADER = (
    "Generic Name,Company Name, Contact Info, Presentation, Type of Update,Date of Update, "
    "Availability Information, Related Information, Resolved Note, Reason for Shortage, "
    "Therapeutic Category, Status, Change Date, Date Discontinued, Initial Posting Date"
)
MONTHS = ("01", "02", "03", "04", "05", "09", "10")  # captures c0..c6; c4 to c5 is a long gap
P10 = "10 mg vial (NDC 12345-678-90)"
P20 = "20 mg vial (NDC 12345-679-90)"
B1 = "5 mL bottle (NDC 54321-111-11)"
B2 = "10 mL bottle (NDC 54321-222-22)"
G1 = "Kit (NDC 11111-111-11)"
G2 = "Kit with diluent (NDC 11111-111-11) (NDC 22222-222-22)"
D1 = "2 mg tablet, 30 count (NDC 33333-333-33)"
D1_NEW = "2 mg tablets 30ct (NDC 33333-333-33)"
D2 = "4 mg tablet, 30 count (NDC 33333-444-44)"
E1 = "5 mL dropper (NDC 44444-111-11)"
E2 = "10 mL dropper (NDC 44444-222-22)"
D3 = "8 mg tablet, 30 count (NDC 33333-555-55)"
Z1 = "30 g tube (NDC 55555-111-11)"
GUIDE = """# Guide

**Version v9 draft, a test.** See ## Appendix A below.

## Appendix A. Statements excluded from every sample

### A.1 Worked examples

| Generic | Company | Statement date | Outcome example |
|---|---|---|---|
| Alpha Injection, USP | Acme Pharma | 2021-12-20 and 2022-03-05 | 1: `E000000000000` |

### A.2 Sources of phrases

| Generic | Company | Statement date | Phrase |
|---|---|---|---|
| Nothing Tablets | Nobody Inc. | 2020-01-01, 2020-02-02 | "by 2020-03-03" |

## Appendix B. Other

| a | b | 2019-01-01 |
"""


def guide_for(year: int) -> str:
    """The guide above with one Appendix A row, which names a statement of ``world(year)``."""
    text = GUIDE.replace("2021-12-20 and 2022-03-05", f"{year - 1}-12-20")
    nothing = '| Nothing Tablets | Nobody Inc. | 2020-01-01, 2020-02-02 | "by 2020-03-03" |\n'
    assert nothing in text
    return text.replace(nothing, "")


def row(
    generic: str,
    company: str,
    presentation: str,
    date: str,
    avail: str = "",
    related: str = "",
    status: str = "Current",
    disc: str = "",
) -> list[str]:
    cells = [generic, company, "800-000-0000", presentation, "Revised", date, avail, related]
    return [*cells, "", "Demand increase", "Anesthesia", status, "", disc, "01/05/2021"]


def world(year: int) -> dict[str, list[list[str]]]:
    """Captures c0..c6 in ``year`` and c7, c8 in the next (see the tests for each thread)."""
    caps: dict[str, list[list[str]]] = {f"{year}{m}01000000": [] for m in MONTHS}
    caps[f"{year + 1}0201000000"] = []
    caps[f"{year + 1}0301000000"] = []
    stamps = list(caps)

    def put(k: int, *cells: str, date: str = "", **more: str) -> None:
        stamp = stamps[k]
        date = date or (f"12/20/{year - 1}" if k == 0 else f"{stamp[4:6]}/01/{stamp[:4]}")
        caps[stamp].append(row(cells[0], cells[1], cells[2], date, *cells[3:], **more))

    alpha, beta, gamma, delta = "Alpha Injection, USP", "Beta Solution", "Gamma Kit", "Delta Tabs"
    text = "Estimated recovery: March"
    for k, avail in enumerate(["Unavailable", "Unavailable", "Available", "Available"]):
        put(k, alpha, "Acme Pharma", P10, avail, text)
    put(4, alpha, "Acme Pharma", P10, "Limited Availability", text)
    put(5, alpha, "Acme Pharma", P10, "Available", text, status="Resolved")
    put(6, alpha, "Acme Pharma", P10, "Available", text, status="Resolved")
    put(7, alpha, "Acme Pharma", P10, "Unavailable", "Estimated recovery: June")
    for k in range(7):
        put(k, alpha, "Acme Pharma", P20, "Unavailable", "Estimated recovery: TBD")
    put(7, alpha, "Acme Pharma", P20, "Available", "Estimated recovery: TBD")
    put(8, alpha, "Acme Pharma", P20, "Available", "Estimated recovery: TBD", status="Resolved")
    for k in range(2):
        put(k, beta, "Bolt", B1, "Unavailable", "Next delivery: February")
    for k in range(2, 9):
        put(k, beta, "Bolt", B1, "", "", status="To be Discontinued", disc="02/20/2022")
    for k in range(9):
        put(k, beta, "Bolt", B2, "Limited Availability", "On allocation")
        put(k, gamma, "Core", G2, "Unavailable", "Estimated recovery: June")
        put(k, delta, "Dyn", D1 if k < 2 else D1_NEW, "Unavailable" if k < 3 else "Available",
            "Recovery: April")  # fmt: skip
        put(k, delta, "Dyn", D2, "Unavailable" if k < 5 else "Available",
            "Recovery: April" if k < 2 else "Recovery: August")  # fmt: skip
    for k in range(3, 9):  # the same text as D1 and D2 at c0, first stated later
        put(k, delta, "Dyn", D3, "Unavailable", "Recovery: April")
    for k in range(2):
        put(k, gamma, "Core", G1, "Available", "Lots in March")
        put(k, "Epsilon Drops", "Eon", E1, "Unavailable", "Recovery: soon")
    for k in range(9):  # E1 leaves the list at c2, when its generic is Resolved
        status = "Current" if k < 2 else "Resolved"
        put(k, "Epsilon Drops", "Eon", E2, "Unavailable", "Recovery of drops: TBD", status=status)
    # first captured in the next year, but dated in this one
    put(7, "Zeta Cream", "Zed", Z1, "Unavailable", "Recovery: TBD", date=f"12/15/{year}")
    put(8, "Zeta Cream", "Zed", Z1, "Available", "Recovery: TBD", date=f"12/15/{year}")
    for i in range(8):  # eight more generics, two presentations each, four kinds of fate
        name, co = f"Extra {i} Injection", f"Maker {i}"
        pa, pb = f"vial a (NDC 7000{i}-111-11)", f"vial b (NDC 7000{i}-222-22)"
        ta, tb = f"Recovery of lot {i}a expected in May", f"Recovery of lot {i}b expected in May"
        same = f"12/20/{year - 1}" if i >= 4 else ""  # one Date of Update: never re-confirmed
        for k in range(9):
            if i % 4 == 0:
                put(k, name, co, pa, "Unavailable" if k < 2 else "Available", ta, date=same)
                status = "Current" if k < 3 else "Resolved"
                put(k, name, co, pb, "Unavailable", tb, date=same, status=status)
            elif i % 4 == 1:
                put(k, name, co, pa, "Unavailable", ta, date=same)
                status = "Current" if k < 2 else "Resolved"
                put(k, name, co, pb, "Available", tb, date=same, status=status)
            elif i % 4 == 2:
                if k < 4:
                    put(k, name, co, pa, "Unavailable", ta, date=same)
                else:
                    put(k, name, co, pa, status="To be Discontinued", disc="04/20/2022")
                put(k, name, co, pb, "Unavailable" if k < 1 else "Available", tb, date=same)
            else:
                put(k, name, co, pa, "Unavailable" if k < 5 else "Available", ta, date=same)
                put(k, name, co, pb, "Limited Availability", tb, date=same)
    return caps


def write_caps(directory: Path, caps: dict[str, list[list[str]]]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for stamp, rows in caps.items():
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerows(rows)
        text = "\r\n" + HEADER + "\r\n" + buf.getvalue()
        (directory / f"{stamp}.csv").write_bytes(text.encode("utf-8"))
    return directory


def write_world(directory: Path, year: int) -> Path:
    return write_caps(directory, world(year))


def late_world() -> dict[str, list[list[str]]]:
    """One thread whose text changes at the second capture of 2023 under a Date of Update of
    2022: a train event first captured after another test-period capture."""
    eta = ("Eta Gel", "Eon", "tube (NDC 66666-111-11)")
    return {
        "20221001000000": [row(*eta, "09/15/2022", "Unavailable", "Recovery: November")],
        "20230201000000": [row(*eta, "09/15/2022", "Unavailable", "Recovery: November")],
        "20230301000000": [row(*eta, "12/15/2022", "Unavailable", "Recovery: TBD")],
    }


TA = "patch a (NDC 77777-111-11)"
TB = "patch b (NDC 77777-222-22)"
TC = "patch c (NDC 77777-333-33)"
ADDRESS = "supply.desk" + chr(64) + "theta-patch.example"  # built here: no address in this file


def patch_world() -> dict[str, list[list[str]]]:
    """Three presentations of one generic and company: TA short to the end, with a company
    address in its text; TB listed at the first capture only; TC available from the third."""
    caps: dict[str, list[list[str]]] = {f"2022{m}01000000": [] for m in MONTHS[:5]}
    for k, stamp in enumerate(caps):
        date = f"{stamp[4:6]}/01/2022"
        mail = f"Recovery: June. Write to {ADDRESS} for orders"
        caps[stamp].append(row("Theta Patch", "Tho", TA, date, "Unavailable", mail))
        if k == 0:
            caps[stamp].append(row("Theta Patch", "Tho", TB, date, "Unavailable", "Recovery: July"))
        avail = "Unavailable" if k < 2 else "Available"
        caps[stamp].append(row("Theta Patch", "Tho", TC, date, avail, "Recovery: May"))
    return caps


@pytest.fixture(scope="module")
def train(tmp_path_factory: pytest.TempPathFactory) -> AO.Built:
    return AO.load(write_world(tmp_path_factory.mktemp("captures"), 2022), "train")


@pytest.fixture(scope="module")
def patches(tmp_path_factory: pytest.TempPathFactory) -> AO.Built:
    return AO.load(write_caps(tmp_path_factory.mktemp("patches"), patch_world()), "train")


def first_event(b: AO.Built, presentation: str) -> str:
    rows = b.frame[b.frame["presentation"] == presentation].sort_values("first_seen_date")
    return rows["event_id"].iloc[0]


def item_of(b: AO.Built, presentation: str) -> AO.Item:
    item = AO.real_item(b, first_event(b, presentation))
    item.audit_id = "Qtest"
    return item


def dates(rows: list[dict[str, object]], window: str = "") -> list[str]:
    return [str(r["capture_date"]) for r in rows if not window or r["window"] == window]


# ---------------------------------------------------------------------------
# Allocation, draw order, assignment
# ---------------------------------------------------------------------------


def test_allocate_gives_the_floor_then_follows_the_pool() -> None:
    sizes = {"rare": 3, "mid": 100, "big": 897}
    alloc = AO.allocate(sizes, 50, floor=2)
    assert sum(alloc.values()) == 50
    assert alloc == {"rare": 2, "mid": 6, "big": 42}  # 44 left: 0.13, 4.4 and 39.5 -> 0, 4, 40


def test_allocate_never_exceeds_a_stratum_and_reports_a_short_pool() -> None:
    assert AO.allocate({"a": 1, "b": 3}, 10) == {"a": 1, "b": 3}
    assert AO.allocate({"a": 5, "b": 5, "c": 5}, 2) == {"a": 1, "b": 1, "c": 0}
    assert AO.allocate({"a": 0, "b": 4}, 3) == {"b": 3}
    capped = AO.allocate({"a": 3, "b": 1000}, 10, floor=5)
    assert capped == {"a": 3, "b": 7}


def test_strata_are_outcome_type_width_class_and_reconfirmation(train: AO.Built) -> None:
    assert AO.stratum_of("recovered", 31, True) == "recovered/le31/reconfirmed"
    assert AO.stratum_of("recovered", 32, False) == "recovered/32to90/single"
    assert AO.stratum_of("discontinued", 90, False) == "discontinued/32to90/single"
    assert AO.stratum_of("discontinued", 91, True) == "discontinued/gt90/reconfirmed"
    assert AO.stratum_of("censored", None, False) == "censored/none/single"
    assert AO.stratum_of("censored", float("nan"), True) == "censored/none/reconfirmed"
    assert AO.stratum_of("not_at_risk", None, True) == "not_at_risk/none/reconfirmed"
    frame = train.frame
    p10 = frame.loc[first_event(train, P10)]  # B recovered in 28 days, re-confirmed at c1
    assert p10["n_reconfirmations"] > 0 and p10["stratum"] == "recovered/le31/reconfirmed"
    extra = frame.loc[first_event(train, "vial a (NDC 70004-111-11)")]  # one Date of Update
    assert extra["n_reconfirmations"] == 0 and extra["stratum"] == "recovered/le31/single"
    assert list(frame["stratum"]) == list(AO.add_strata(frame))
    assert {s.split("/")[0] for s in frame["stratum"]} == set(AO.TYPES)


def pool_of(rows: list[tuple[str, str, str, str, str]]) -> pd.DataFrame:
    """A pool for the draw: (event, thread, statement, generic, stratum) per row."""
    columns = ["event_id", "thread_id", "statement_group_id", "generic_id", "stratum"]
    return pd.DataFrame(rows, columns=columns).set_index("event_id", drop=False)


def test_draw_takes_one_item_per_thread_and_statement_and_two_per_generic() -> None:
    n = 6
    threads = pool_of([(f"E{i}", "T", f"S{i}", f"g{i}", "a") for i in range(n)])
    assert len(AO.draw(threads, {"a": 4}, "t", AO.Taken())) == 1
    statements = pool_of([(f"E{i}", f"T{i}", "S", f"g{i}", "a") for i in range(n)])
    assert len(AO.draw(statements, {"a": 4}, "t", AO.Taken())) == 1
    generics = pool_of([(f"E{i}", f"T{i}", f"S{i}", "g", "a") for i in range(n)])
    assert len(AO.draw(generics, {"a": 4}, "t", AO.Taken())) == AO.MAX_PER_GENERIC == 2
    free = pool_of([(f"E{i}", f"T{i}", f"S{i}", f"g{i}", "a") for i in range(n)])
    taken = AO.Taken()
    chosen = AO.draw(free, {"a": 4}, "t", taken)
    assert chosen == AO.shuffled(free.index, "t/sample")[:4]  # the top of the seeded order
    assert taken.threads == {f"T{e[1:]}" for e in chosen} and len(taken.groups) == 4
    assert AO.draw(free, {"a": 6}, "t", taken) == AO.shuffled(free.index, "t/sample")[4:]


def test_a_stratum_that_cannot_fill_its_quota_passes_the_rest_to_the_largest() -> None:
    rows = [(f"A{i}", "T", f"SA{i}", f"ga{i}", "a") for i in range(3)]  # one thread: one item
    rows += [(f"B{i}", f"TB{i}", f"SB{i}", f"gb{i}", "b") for i in range(4)]
    rows += [(f"C{i}", f"TC{i}", f"SC{i}", f"gc{i}", "c") for i in range(9)]
    pool = pool_of(rows)
    chosen = AO.draw(pool, {"a": 3, "b": 2, "c": 2}, "t", AO.Taken())
    assert Counter(pool.loc[chosen, "stratum"]) == {"a": 1, "b": 2, "c": 4}
    short = AO.draw(pool, {"a": 3, "b": 4, "c": 9}, "t", AO.Taken())
    assert Counter(pool.loc[short, "stratum"]) == {"a": 1, "b": 4, "c": 9}  # nothing left to give


def test_seeded_order_ignores_input_order_and_depends_on_the_tag() -> None:
    ids = [f"E{i}" for i in range(40)]
    assert AO.shuffled(ids, "x") == AO.shuffled(reversed(ids), "x")
    assert AO.shuffled(ids, "x") != AO.shuffled(ids, "y")
    assert AO.shuffled(ids, "x") != sorted(ids)
    assert AO.shuffled(ids, "x", seed=1) != AO.shuffled(ids, "x")


def test_assignment_is_20_20_10_and_spread() -> None:
    who = AO.assign(50, 20, 10)
    assert Counter(who) == {"A1": 20, "A2": 20, "both": 10}
    assert set(who[:5]) == {"A1", "A2", "both"}
    assert Counter(AO.assign(7, 20, 10))["both"] >= 1


# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------


def test_guide_examples_are_read_from_appendix_a_only() -> None:
    examples = AO.guide_examples(GUIDE)
    assert ("alpha injection, usp", "acme pharma", "2021-12-20") in examples
    assert ("alpha injection, usp", "acme pharma", "2022-03-05") in examples
    assert ("nothing tablets", "nobody inc", "2020-02-02") in examples
    assert len(examples) == 4 and {e[2][:4] for e in examples} == {"2020", "2021", "2022"}
    assert AO.guide_examples("no appendix") == []
    assert AO.guide_version(GUIDE) == "v9 draft"
    assert AO.guide_version("**Version v0, 29 September 2026. Draft.**") == "v0"


def test_exclusion_covers_the_statement_its_presentations_and_their_threads(
    train: AO.Built,
) -> None:
    table = train.table
    d1 = table[table["presentation"] == D1].iloc[0]
    d2 = table[table["presentation"] == D2]
    assert d1["statement_group_id"] in set(d2["statement_group_id"])  # one statement, two threads
    skip, unmatched = AO.excluded_threads(
        table, {"statement_group_id": {d1["statement_group_id"]}}, []
    )
    assert skip == {d1["thread_id"], d2["thread_id"].iloc[0]} and unmatched == []
    # a later event on a skipped thread is skipped with it
    later = d2[d2["statement_text"].str.contains("August")]["thread_id"].iloc[0]
    assert later in skip
    by_event, _ = AO.excluded_threads(table, {"event_id": {d1["event_id"]}}, [])
    assert by_event == skip
    by_guide, unmatched = AO.excluded_threads(table, {}, AO.guide_examples(GUIDE))
    alpha = set(table.loc[table["generic_name"] == "Alpha Injection, USP", "thread_id"])
    assert by_guide == alpha and len(unmatched) == 3
    assert unmatched[0] == ("alpha injection, usp", "acme pharma", "2022-03-05")
    # a guide example also excludes the same generic, company and text stated at another date
    d3 = table[table["presentation"] == D3].iloc[0]
    assert d3["event_date"] == "2022-04-01" and d3["thread_id"] not in skip
    same_text, unmatched = AO.excluded_threads(table, {}, [("delta tabs", "dyn", "2021-12-20")])
    assert same_text == skip | {d3["thread_id"]} and unmatched == []
    # an earlier audit sample keeps out its own threads only: D2 is another audit unit
    ids = {"event_id": {d1["event_id"]}, "statement_group_id": {d1["statement_group_id"]}}
    assert AO.audited_threads(table, ids) == {d1["thread_id"]}
    assert AO.audited_threads(table, {"thread_id": {d3["thread_id"], "Tgone"}}) == {d3["thread_id"]}


def test_sample_lists_are_read_from_csv_and_json_lines(tmp_path: Path) -> None:
    (tmp_path / "pilot.csv").write_text("# task: pilot\nitem_id,statement_group_id\n1,S1\n2,S2\n")
    (tmp_path / "items.jsonl").write_text('{"event_id": "E1", "thread_id": "T1"}\n\n')
    (tmp_path / "blank.csv").write_text("item_id,drug\n1,x\n")
    (tmp_path / "notes.txt").write_text("statement_group_id\nS9\n")
    (tmp_path / "outcome_train_sample.csv").write_text("event_id\nE7\n")  # this module's own
    files = AO.exclusion_files([tmp_path, tmp_path / "missing"])
    assert [p.name for p in files] == ["blank.csv", "items.jsonl", "pilot.csv"]
    ids = [AO.read_ids(p) for p in files]
    assert not any(ids[0].values())
    assert ids[1] == {"event_id": {"E1"}, "statement_group_id": set(), "thread_id": {"T1"}}
    assert ids[2]["statement_group_id"] == {"S1", "S2"}
    named = AO.exclusion_files([tmp_path / "outcome_train_sample.csv"])  # a re-audit round
    assert AO.read_ids(named[0])["event_id"] == {"E7"}


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------


def test_trace_window_strip_and_brackets(train: AO.Built) -> None:
    item = item_of(train, P10)
    rows, strip = AO.trace(item, train)
    sheet = AO.sheet_row(item, train, strip)
    assert strip == "U U A A L | R R"
    assert (sheet["derived_B_type"], sheet["derived_B_lower"], sheet["derived_B_upper"]) == (
        "recovered",
        "2022-02-01",
        "2022-03-01",
    )
    assert sheet["derived_B_width"] == 28 and sheet["derived_A_width"] == 123
    assert (sheet["derived_A_lower"], sheet["derived_A_upper"]) == ("2022-05-01", "2022-09-01")
    assert sheet["c0"] == "2022-01-01" and sheet["statement_date"] == "2021-12-20"
    assert sheet["followed_to"] == "2022-10-01"
    assert dates(rows) == [f"2022-{m}-01" for m in MONTHS]
    assert [r["window"] for r in rows] == ["c0", *["after"] * 6]
    assert rows[5]["gap_before_days"] == 123 and rows[5]["status"] == "Resolved"
    assert rows[0]["same_text"] == 1 and rows[0]["availability_information"] == "Unavailable"


def test_train_trace_stops_at_the_last_capture_before_2023(train: AO.Built) -> None:
    item = item_of(train, P20)  # still unavailable in 2022; "Available" in the 2023 captures
    assert item.horizon == train.ctx.train_last
    rows, strip = AO.trace(item, train)
    sheet = AO.sheet_row(item, train, strip)
    assert max(dates(rows)) == "2022-10-01"
    assert strip == "U U U U U | U U" and "A" not in strip
    assert all(r["availability_information"] == "Unavailable" for r in rows)
    for d in AO.DEFS:
        assert sheet[f"derived_{d}_type"] == "censored"
        assert sheet[f"derived_{d}_censor"] == "end_of_train"
        assert sheet[f"derived_{d}_lower"] == "2022-10-01" and sheet[f"derived_{d}_upper"] == ""


def test_no_train_item_shows_a_capture_from_the_test_period(train: AO.Built) -> None:
    for event_id in train.frame.index:
        item = AO.real_item(train, event_id)
        rows, _ = AO.trace(item, train)
        assert all(r["capture_date"] < "2023-01-01" or r["window"] == "c0" for r in rows)
        assert train.frame.at[event_id, "event_date"] < "2023-01-01"
    late = item_of(train, Z1)  # dated December 2022, first captured in February 2023
    rows, strip = AO.trace(late, train)
    assert [(r["window"], r["present"]) for r in rows] == [
        ("before", "no"),
        ("before", "no"),
        ("c0", "yes"),
    ]
    assert strip == "U" and dates(rows, "c0") == ["2023-02-01"]
    sheet = AO.sheet_row(late, train, strip)
    assert sheet["followed_to"] == "2023-02-01" and sheet["derived_B_censor"] == "end_of_train"


def test_the_sheet_writer_refuses_a_train_trace_that_reaches_the_test_period(
    train: AO.Built, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = item_of(train, P20)
    item.assigned = "A1"
    trace = AO.trace

    def too_far(*args: object) -> tuple[list[dict[str, object]], str]:
        rows, strip = trace(*args)
        return [*rows, {**rows[-1], "capture_date": "2023-02-01", "window": "after"}], strip

    monkeypatch.setattr(AO, "trace", too_far)
    sink = AO.Sink(tmp_path, hold=True)
    with pytest.raises(RuntimeError, match="a train trace reaches the test period"):
        AO.write_sheets(train, AO.Drawn([item], [], {}), sink, sink, {"draw": "t"})
    assert not sink.pending and not list(tmp_path.iterdir())


def test_an_item_that_differs_from_the_outcome_table_is_refused(train: AO.Built) -> None:
    event_id = first_event(train, P10)
    frame = train.frame.copy()
    frame.loc[event_id, "upper_date_B"] = "2022-04-01"  # the table says one capture later
    with pytest.raises(RuntimeError, match="definition B differs from the outcome table"):
        AO.real_item(AO.replace(train, frame=frame), event_id)
    assert AO.real_item(train, event_id).true["B"].upper == 2


def test_rows_before_c0_are_cut_at_the_train_horizon_too(tmp_path: Path) -> None:
    late = AO.load(write_caps(tmp_path, late_world()), "train")
    revised = late.frame[late.frame["first_seen_date"] == "2023-03-01"]
    assert list(revised["event_date"]) == ["2022-12-15"]  # a train event, by its date
    item = AO.real_item(late, revised["event_id"].iloc[0])
    assert item.horizon == 2 and late.ctx.train_last == 0
    rows, strip = AO.trace(item, late)
    # the capture of 2023-02-01 lies between the train horizon and c0: it is not shown
    assert [(r["window"], r["capture_date"]) for r in rows] == [
        ("before", "2022-10-01"),
        ("c0", "2023-03-01"),
    ]
    assert strip == "U"


def test_an_excluded_thread_with_the_same_ndc_is_listed_without_its_text(
    train: AO.Built, tmp_path: Path
) -> None:
    item = item_of(train, G1)  # absent from c2 while its NDC stays listed under G2
    g2 = train.frame.loc[first_event(train, G2), "thread_id"]
    rows, strip = AO.trace(item, train, {g2})
    held = [r for r in rows if r["present"] == AO.WITHHELD]
    assert len(held) == 5 and not [r for r in rows if r["present"] == "other_thread"]
    shown = set(AO.TRACE_COLUMNS) & set(held[0])
    assert {"generic", "company", "presentation"} <= shown and held[0]["presentation"] == G2
    for name in ("status", "availability_information", "related_information", "date_of_update"):
        assert name not in held[0]
    line = AO.trace_line(held[0], AO.sheet_row(item, train, strip))
    assert "withheld" in line and G2 in line and "Estimated recovery" not in line
    # the sheet writer passes the excluded threads on
    item.assigned = "A1"
    drawn = AO.Drawn([item], [], {}, frozenset({g2}))
    sink = AO.Sink(tmp_path)
    AO.write_sheets(train, drawn, sink, sink, {"draw": "t"})
    text = "".join(p.read_text() for p in tmp_path.iterdir())
    assert AO.WITHHELD in text and "Estimated recovery: June" not in text
    drawn = AO.Drawn([item], [], {}, frozenset())
    AO.write_sheets(train, drawn, sink, sink, {"draw": "t"})
    assert "Estimated recovery: June" in (tmp_path / "outcome_train_traces.csv").read_text()


def test_mail_addresses_are_masked_in_every_file_for_people(
    patches: AO.Built, tmp_path: Path
) -> None:
    item = item_of(patches, TA)
    assert ADDRESS in patches.frame.loc[item.event_id, "statement_text"]
    rows, strip = AO.trace(item, patches)
    sheet = AO.sheet_row(item, patches, strip)
    assert "[email] for orders" in sheet["statement_text"]
    assert all("[email] for orders" in r["related_information"] for r in rows)
    assert rows[1]["same_text"] == 1  # compared before masking
    item.assigned = "both"
    sink = AO.Sink(tmp_path)
    AO.write_sheets(patches, AO.Drawn([item], [], {}), sink, sink, {"draw": "t"})
    written = {p.name: p.read_text() for p in tmp_path.iterdir()}
    assert len(written) == 8 and all(chr(64) not in text for text in written.values())
    assert AO.masked(f"a {ADDRESS}, b") == "a [email], b" and AO.masked(3) == 3


def test_class_letters_agree_with_the_builder(train: AO.Built) -> None:
    reading = {"A": "rec", "R": "rec", "r": "rec", "D": "disc", ".": "unknown"}
    seen = set()
    for event_id in train.frame.index:
        item = AO.real_item(train, event_id)
        first = train.ctx.col["cap_idx"][item.ev.rows[0]]
        disc = train.ctx.in_discontinuation(item.ev.rows[0], first)
        for cap in range(first + 1, item.horizon + 1):
            letter = AO.class_letter(item, train, cap, disc)
            state = C.state_at(item.ev, train.ctx, cap, disc)
            assert state.of("B") == reading.get(letter, "not")
            assert (state.of("A") == "rec") == (letter in "Rr")
            seen.add(letter)
    assert {"A", "L", "U", "R", "r", "D", "."} <= seen
    _, strip = AO.trace(item_of(train, E1), train)
    assert strip == "U U r r r"


def test_discontinuation_listing_and_before_rows(train: AO.Built) -> None:
    item = item_of(train, B1)
    rows, strip = AO.trace(item, train)
    assert strip == "U U D D D"  # one capture past upper, then 90 days after it
    assert [r["discontinuation_listing"] for r in rows] == ["", "", *["listed"] * 3]
    assert rows[2]["present"] == "no" and rows[2]["discontinuation_date"] == "02/20/2022"
    assert AO.sheet_row(item, train, strip)["derived_B_type"] == "discontinued"
    revised = train.frame[
        (train.frame["presentation"] == D2) & (train.frame["first_seen_date"] == "2022-03-01")
    ]
    later = AO.real_item(train, revised["event_id"].iloc[0])
    rows, strip = AO.trace(later, train)
    assert [r["window"] for r in rows[:3]] == ["before", "before", "c0"]
    assert [r["same_text"] for r in rows[:3]] == [0, 0, 1]
    assert strip.split()[0] == "U" and dates(rows, "c0") == ["2022-03-01"]


def test_ndc_link_is_marked_and_other_threads_with_the_ndc_are_listed(train: AO.Built) -> None:
    rows, _ = AO.trace(item_of(train, D1), train)
    assert [r["linked_by"] for r in rows[:4]] == ["key", "key", "ndc", "key"]
    assert rows[2]["presentation"] == D1_NEW
    item = item_of(train, G1)  # leaves the list at c2 while its NDC stays listed under G2
    rows, strip = AO.trace(item, train)
    sheet = AO.sheet_row(item, train, strip)
    assert sheet["derived_B_type"] == "not_at_risk"
    assert sheet["derived_A_censor"] == "absent_generic_current"
    assert strip == "A A . . . | . ."
    others = [r for r in rows if r["present"] == "other_thread"]
    assert len(others) == 5 and {r["presentation"] for r in others} == {G2}
    absent = [r for r in rows if r["present"] == "no"]
    assert {r["generic_state"] for r in absent} == {"current"}
    assert sheet["derived_A_exit"] == "2022-03-01" and sheet["derived_B_exit"] == ""
    assert "class_letter" not in others[0]


def test_item_block_shows_the_sheet_cells_and_one_line_per_capture(train: AO.Built) -> None:
    item = item_of(train, G1)
    rows, strip = AO.trace(item, train)
    block = AO.item_block(AO.sheet_row(item, train, strip), rows, 3, 33).splitlines()
    assert block[0] == "=== Qtest (item 3 of 33)"
    assert "derived B: not_at_risk" in block
    assert "derived A: censored at 2022-02-01 (absent_generic_current)" in block
    assert "class strip: A A . . . | . ." in block
    assert block[10].startswith("* 2022-01-01 A | Current | Revised 12/20/2021 | availability: ")
    assert block[10].endswith("| same text")
    assert block[12] == "  2022-03-01 . | absent; generic current"
    assert block[13].startswith("             another thread with this NDC | Current | ")
    assert block[13].endswith(f"| presentation: {G2}")
    assert any(line.endswith("123 days since the capture before") for line in block)
    closed = item_of(train, P10)
    rows, strip = AO.trace(closed, train)
    text = AO.item_block(AO.sheet_row(closed, train, strip), rows, 1, 1)
    assert "derived B: recovered (2022-02-01, 2022-03-01], 28 days\n" in text
    assert "statement group, 1 presentation(s): B recovered (2022-02-01, 2022-03-01]; A " in text
    renamed = item_of(train, D1)
    ndc = AO.trace(renamed, train)[0][2]
    assert (ndc["generic"], ndc["company"]) == ("Delta Tabs", "Dyn")
    line = AO.trace_line(ndc, AO.sheet_row(renamed, train, ""))
    assert line.endswith(f"| presentation: {D1_NEW} | linked by NDC | same text")
    assert "generic:" not in line and "company:" not in line


def test_context_caps_and_window_end() -> None:
    assert AO.context_caps([0, 1, 2, 9], 9) == [2, 7, 8]
    assert AO.context_caps([3, 4], 4) == [2, 3]
    assert AO.context_caps([0], 0) == []
    assert AO.context_caps([0, 1, 2, 9], 9, last=7) == [2, 7]
    assert AO.context_caps([0, 5], 9, last=6) == [5]
    days = list(pd.date_range("2022-01-01", periods=12, freq="30D"))
    closed = {"B": AO.Bracket("recovered", 1, 2), "A": AO.Bracket("recovered", 2, 3)}
    assert AO.window_end(closed, 0, 11, days) == 5  # one past A's upper, 90 days after B's
    assert AO.window_end(closed, 0, 3, days) == 3
    still = {"B": AO.Bracket("recovered", 1, 2), "A": AO.Bracket("censored", 11, None, "x")}
    assert AO.window_end(still, 0, 11, days) == 11
    idle = {d: AO.Bracket("not_at_risk") for d in AO.DEFS}
    assert AO.window_end(idle, 4, 11, days) == 5


# ---------------------------------------------------------------------------
# Planted items
# ---------------------------------------------------------------------------


def test_bound_moves_keep_the_other_definition_possible(train: AO.Built) -> None:
    item = item_of(train, P10)  # B (c1, c2], A (c4, c5]
    later = AO.perturb("upper_later", item, train, set(), "t")
    assert later is not None and later.planted_definitions == ["B"]
    assert (later.shown["B"].upper, later.true["B"].upper) == (3, 2)
    assert AO.sheet_row(later, train, "")["group_B_upper"] == "2022-04-01"
    earlier = AO.perturb("lower_earlier", item, train, set(), "t")
    assert earlier is not None and (earlier.shown["B"].lower, earlier.shown["A"].lower) == (0, 4)
    assert AO.perturb("type_swapped", item, train, set(), "t") is None  # A closes later than B
    open_item = item_of(train, P20)
    for kind in ("upper_later", "lower_earlier", "type_swapped"):
        assert AO.perturb(kind, open_item, train, set(), "t") is None
    both = item_of(train, "vial b (NDC 70000-222-22)")  # Resolved at c3: B and A close together
    moved = AO.perturb("upper_later", both, train, set(), "t")
    assert moved is not None and moved.planted_definitions == ["B", "A"]
    assert moved.shown["A"].upper == moved.shown["B"].upper == 4
    # the window follows the bracket shown, so its length does not give a planted item away
    assert max(dates(AO.trace(both, train)[0])) == "2022-05-01"  # one capture past upper
    assert max(dates(AO.trace(moved, train)[0])) == "2022-09-01"


def test_type_swap_changes_both_definitions(train: AO.Built) -> None:
    both = item_of(train, "vial b (NDC 70000-222-22)")
    swapped = AO.perturb("type_swapped", both, train, set(), "t")
    assert swapped is not None
    assert {swapped.shown[d].kind for d in AO.DEFS} == {"discontinued"}
    assert {swapped.true[d].kind for d in AO.DEFS} == {"recovered"}
    _, strip = AO.trace(swapped, train)
    assert "D" not in strip  # the trace is the true one
    gone = item_of(train, B1)
    back = AO.perturb("type_swapped", gone, train, set(), "t")
    assert back is not None and back.shown["B"].kind == "recovered"
    key = AO.key_row(back, train, {})
    assert (key["true_B_type"], key["shown_B_type"], key["expected_code"]) == (
        "discontinued",
        "recovered",
        "O7",
    )


def test_wrong_presentation_links_a_sibling_thread_after_c0(train: AO.Built) -> None:
    item = item_of(train, D1)  # true B (c2, c3]; its sibling D2 recovers at c5
    planted = AO.perturb("wrong_presentation", item, train, set(), "t")
    assert planted is not None and planted.walker is not planted.ev
    assert (planted.true["B"].lower, planted.true["B"].upper) == (2, 3)
    assert (planted.shown["B"].lower, planted.shown["B"].upper) == (4, 5)
    rows, strip = AO.trace(planted, train)
    assert rows[0]["presentation"] == D1 and rows[1]["presentation"] == D2
    assert [r["linked_by"] for r in rows[:3]] == ["key", "ndc", "key"]
    assert strip.startswith("U U U U U | A")
    sheet = AO.sheet_row(planted, train, strip)
    assert sheet["presentation"] == D1 and sheet["derived_B_upper"] == "2022-09-01"
    assert sheet["group_n_presentations"] == 2 and sheet["group_B_upper"] == "2022-09-01"
    key = AO.key_row(planted, train, {})
    assert key["linked_thread_id"] and key["linked_thread_id"] != key["thread_id"]
    assert key["expected_code"] == "O1" and key["true_B_upper"] == "2022-04-01"
    d2_thread = train.frame.loc[first_event(train, D2), "thread_id"]
    assert AO.perturb("wrong_presentation", item, train, {d2_thread}, "t") is None
    assert AO.perturb("wrong_presentation", item_of(train, G1), train, set(), "t") is None


def test_wrong_presentation_needs_a_row_of_the_other_thread_in_the_trace(
    patches: AO.Built,
) -> None:
    item = item_of(patches, TA)  # censored at the end of train
    tb = patches.frame.loc[first_event(patches, TB), "thread_id"]
    tc = patches.frame.loc[first_event(patches, TC), "thread_id"]
    # TB is listed at c0 only: linked after c0 it would show absences and nothing to catch
    assert AO.perturb("wrong_presentation", item, patches, {tc}, "t") is None
    planted = AO.perturb("wrong_presentation", item, patches, {tb}, "t")
    assert planted is not None and planted.shown["B"].kind == "recovered"
    assert AO.key_row(planted, patches, {})["linked_thread_id"] == tc
    for tag in "abcdefgh":  # whatever the seeded order of the two siblings
        planted = AO.perturb("wrong_presentation", item, patches, set(), tag)
        assert planted is not None
        rows, _ = AO.trace(planted, patches)
        assert any(r["window"] == "after" and r["presentation"] == TC for r in rows)


# ---------------------------------------------------------------------------
# The draw and the sheets
# ---------------------------------------------------------------------------


def test_draw_respects_caps_assignment_and_exclusions(train: AO.Built) -> None:
    skip = set(train.table.loc[train.table["generic_name"] == "Gamma Kit", "thread_id"])
    drawn = AO.draw_items(train, skip, own=3, shared=2, planted=2, tag="t")
    real = [it for it in drawn.items if not it.planted]
    planted = [it for it in drawn.items if it.planted]
    assert len(real) == 8 and len(planted) == 4
    frame = train.frame.loc[[it.event_id for it in drawn.items]]
    assert frame["thread_id"].is_unique and frame["statement_group_id"].is_unique
    assert frame["generic_id"].value_counts().max() <= AO.MAX_PER_GENERIC
    assert not set(frame["thread_id"]) & skip
    assert Counter(it.assigned for it in real) == {"A1": 3, "A2": 3, "both": 2}
    assert Counter(it.assigned for it in planted) == {"A1": 2, "A2": 2}
    assert all(it.shown != it.true and it.planted_definitions for it in planted)
    assert all(it.shown == it.true for it in real)
    for auditor in AO.AUDITORS:
        kinds = [it.planted for it in planted if it.assigned == auditor]
        assert len(set(kinds)) == len(kinds)
    assert len({it.audit_id for it in drawn.items}) == 12
    again = AO.draw_items(train, skip, own=3, shared=2, planted=2, tag="t")
    assert [(it.audit_id, it.assigned, it.planted) for it in again.items] == [
        (it.audit_id, it.assigned, it.planted) for it in drawn.items
    ]
    other = AO.draw_items(train, skip, own=3, shared=2, planted=2, tag="u")
    assert {it.event_id for it in other.items} != {it.event_id for it in drawn.items}
    strata = {s["stratum"]: s for s in drawn.strata}
    assert sum(s["events"] for s in drawn.strata) == len(train.frame)
    assert sum(s["excluded"] for s in drawn.strata) == drawn.counts["excluded_events"] == 2
    assert sum(s["drawn"] for s in drawn.strata) == 8
    assert all(s["pool"] == s["events"] - s["excluded"] for s in strata.values())


def test_a_pool_that_is_too_small_shows_as_a_shortfall(
    train: AO.Built, capsys: pytest.CaptureFixture[str]
) -> None:
    drawn = AO.draw_items(train, set(), own=20, shared=10, planted=3, tag="t")
    assert drawn.counts["real_drawn"] < drawn.counts["real_wanted"] == 50
    manifest = {"status": "draft", "draw": "t", "excluded_threads": 0, "exclusion_lists": []}
    manifest["guide_examples_unmatched"] = 0
    sink = AO.Sink(Path("unused"))
    AO.report_sheets("train", drawn, manifest, sink, sink)
    printed = capsys.readouterr().out
    assert "SHORTFALL" in printed and "<- shortfall" in printed
    assert "recovered/le31/single" in printed  # the train half prints its stratum table


def sample_list(directory: Path, built: AO.Built, presentation: str) -> Path:
    """A sample list as the sampler writes it: the ids of one presentation's first statement."""
    rows = built.table[built.table["presentation"] == presentation]
    first = rows.sort_values("first_seen_date").iloc[0]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "sample_pilot.csv"
    header = ",".join(AO.ID_COLUMNS)
    path.write_text(f"{header}\n{','.join(first[c] for c in AO.ID_COLUMNS)}\n")
    (directory / "strata.csv").write_text("sample,stratum,quota\npilot,month_year,1\n")
    return path


def test_an_auditor_gets_a_kind_twice_only_when_no_other_can_be_made(
    train: AO.Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    kinds = AO.shuffled(AO.PLANT_KINDS, "t/kinds")
    perturb = AO.perturb

    def without_the_first(kind: str, *rest: object) -> AO.Item | None:
        return None if kind == kinds[0] else perturb(kind, *rest)

    monkeypatch.setattr(AO, "perturb", without_the_first)
    items = AO.plant(train, train.frame, AO.Taken(), set(), 2, "t")
    for auditor in AO.AUDITORS:
        mine = [it.planted for it in items if it.assigned == auditor]
        assert len(mine) == 2 and len(set(mine)) == 2 and kinds[0] not in mine
    # the first auditor's second slot starts its rotation at the kind the first slot fell back on
    assert [it.planted for it in items][:2] == [kinds[1], kinds[2]]


def run_sheets(tmp_path: Path, year: int, *more: str) -> tuple[Path, Path, int]:
    captures = write_world(tmp_path / "captures", year)
    guide = tmp_path / "guide.md"
    guide.write_text(guide_for(year))
    out = tmp_path / "out"
    args = ["sheets", "--captures", str(captures), "--guide", str(guide), "--out", str(out)]
    args += ["--keys", str(out / "keys"), "--own", "2", "--shared", "1", "--planted", "1"]
    code = AO.main([*args, *more])
    return captures, out, code


def test_sheets_command_writes_blank_sheets_traces_key_and_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lists = tmp_path / "lists"
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    listed = sample_list(lists, built, G2)
    _, out, code = run_sheets(tmp_path, 2022, "--half", "train", "--exclude", str(lists))
    assert code == 0
    printed = capsys.readouterr().out
    assert "real items 5 of 5; planted 2 of 2" in printed and "stratum" in printed
    names = AO.file_names("train")
    key = AO.read_sheet(out / "keys" / names["key"])[1]
    assert not (out / names["key"]).exists()
    sheets = {a: AO.read_sheet(out / names[a]) for a in AO.AUDITORS}
    for auditor, (meta, rows) in sheets.items():
        assert meta["auditor"] == auditor and meta["half"] == "train" and meta["status"] == "final"
        assert "note" not in meta
        assert meta["followed_to"] == "2022-10-01" and meta["guide"].startswith("v9 draft sha256 ")
        assert meta["items"] == "4" and len(rows) == 4
        assert list(rows[0]) == list(AO.SHEET_COLUMNS)
        assert all(r[c] == "" for r in rows for c in AO.ENTERED)
        mine = {k["audit_id"] for k in key if k["assigned_to"] in (auditor, "both")}
        assert {r["audit_id"] for r in rows} == mine
        assert sum(bool(k["planted"]) for k in key if k["audit_id"] in mine) == 1
    ids = [[r["audit_id"] for r in rows] for _, rows in sheets.values()]
    assert len(set(ids[0]) & set(ids[1])) == 1
    for auditor, order in zip(AO.AUDITORS, ids, strict=True):  # each sheet in its own seeded order
        assert order == AO.shuffled(order, f"train/order/{auditor}") != sorted(order)
    text = "".join((out / names[a]).read_text() for a in AO.AUDITORS)
    for auditor, order in zip(AO.AUDITORS, ids, strict=True):
        blocks = (out / names[f"{auditor}_items"]).read_text()
        assert blocks.startswith("# task: B outcome audit") and f"# auditor: {auditor}" in blocks
        assert re.findall(r"^=== (Q\w+) \(item \d of 4\)$", blocks, flags=re.M) == order
        assert blocks.count("\nclass strip: ") == 4 and blocks.count("\n* 2022-") == 4
        text += blocks
    assert not re.search(r"\bE[0-9a-f]{12}\b|\bT[0-9a-f]{12}\b|planted", text)
    # the Alpha threads are guide examples: no item, no trace row
    assert "Alpha Injection" not in text
    # the thread of the listed statement is no item, and its text is in no file for people
    rows = [r for _, sheet in sheets.values() for r in sheet]
    assert G2 not in {r["presentation"] for r in rows}
    assert "Estimated recovery: June" not in text + (out / names["traces"]).read_text()
    traces = AO.read_sheet(out / names["traces"])[1]
    assert {t["audit_id"] for t in traces} == {k["audit_id"] for k in key}
    assert all(t["capture_date"] < "2023-01-01" or t["window"] == "c0" for t in traces)
    sample = AO.read_sheet(out / names["sample"])[1]
    assert sorted(s["event_id"] for s in sample) == sorted(k["event_id"] for k in key)
    assert list(sample[0]) == list(AO.SAMPLE_COLUMNS)
    manifest = json.loads((out / names["manifest"]).read_text())
    assert manifest["counts"]["real_drawn"] == 5 and manifest["guide_examples_unmatched"] == 0
    assert manifest["guide_examples"] == 1
    assert manifest["exclusion_lists"] == [
        {
            "file": "sample_pilot.csv",
            "ids": 3,
            "kind": "labelling",
            "sha256": AO.sha256_file(listed),
        }
    ]  # the list is named without its folder; the strata table beside it holds no id
    assert manifest["excluded_threads"] == 3 and manifest["sample_list_ids_unknown"] == 0
    assert (
        manifest["counts"]["excluded_events"]
        == manifest["counts"]["events"] - (manifest["counts"]["pool"])
    )
    assert manifest["files"][names["A1"]] == AO.sha256_file(out / names["A1"])
    assert manifest["files"][names["key"]] == AO.sha256_file(out / "keys" / names["key"])
    before = {p.name: p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}
    assert run_sheets(tmp_path, 2022, "--half", "train", "--exclude", str(lists))[2] == 0
    assert before == {p.name: p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}


def test_train_half_needs_a_sample_list_unless_it_is_a_draft(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no sample list"):
        run_sheets(tmp_path, 2022, "--half", "train", "--exclude", str(tmp_path / "none"))
    (tmp_path / "none").mkdir()
    (tmp_path / "none" / "strata.csv").write_text("sample,stratum,quota\npilot,month_year,1\n")
    with pytest.raises(SystemExit, match="no sample list"):  # a file with no id column is no list
        run_sheets(tmp_path, 2022, "--half", "train", "--exclude", str(tmp_path / "none"))
    assert not (tmp_path / "out").exists()
    _, out, code = run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude")
    assert code == 0
    meta, _ = AO.read_sheet(out / "outcome_A1_train.csv")
    assert meta["status"] == "draft" and meta["draw"] == "train/draft"
    assert meta["note"] == AO.DRAFT_NOTE and "not given to the annotators" in meta["note"]
    assert f"# note: {AO.DRAFT_NOTE}\n" in (out / "outcome_A1_train_items.txt").read_text()


def test_a_draft_uses_whatever_lists_exist_and_its_own_draw(tmp_path: Path) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    lists = sample_list(tmp_path / "lists", built, G2).parent
    _, out, _ = run_sheets(tmp_path, 2022, "--half", "train", "--exclude", str(lists))
    names = AO.file_names("train")
    final = {r["event_id"] for r in AO.read_sheet(out / names["sample"])[1]}
    draft_out = tmp_path / "draft"
    args = ["--half", "train", "--draft", "--exclude", str(lists), "--out", str(draft_out)]
    assert run_sheets(tmp_path, 2022, *args, "--keys", str(draft_out / "keys"))[2] == 0
    manifest = json.loads((draft_out / names["manifest"]).read_text())
    assert manifest["status"] == "draft" and manifest["draw"] == "train/draft"
    assert manifest["exclusion_lists"][0]["file"] == "sample_pilot.csv"
    assert manifest["excluded_threads"] == 3  # the listed thread and the two guide examples
    draft = AO.read_sheet(draft_out / names["sample"])[1]
    g2 = built.frame.loc[first_event(built, G2), "thread_id"]
    assert g2 not in {r["thread_id"] for r in draft}
    assert {r["event_id"] for r in draft} != final  # another draw: it does not show the final one


def test_a_listed_id_that_names_no_event_stops_the_final_draw(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    lists = sample_list(tmp_path / "lists", built, G2).parent
    (lists / "sample_check.csv").write_text("statement_group_id\nSnone\n")
    assert AO.unknown_ids(built.table, {"statement_group_id": {"Snone"}, "event_id": set()}) == 1
    with pytest.raises(SystemExit, match="1 ids in the sample lists name no event"):
        run_sheets(tmp_path, 2022, "--half", "train", "--exclude", str(lists))
    assert not (tmp_path / "out").exists()
    _, out, code = run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude", str(lists))
    assert code == 0 and "WARNING: 1 listed ids name no event" in capsys.readouterr().out
    manifest = json.loads((out / "outcome_train_manifest.json").read_text())
    assert manifest["sample_list_ids_unknown"] == 1 and len(manifest["exclusion_lists"]) == 2


def test_the_guide_and_its_appendix_a_are_needed(tmp_path: Path) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    lists = str(sample_list(tmp_path / "lists", built, G2).parent)
    captures, out = str(tmp_path / "captures"), str(tmp_path / "out")
    args = ["sheets", "--half", "train", "--captures", captures, "--out", out, "--exclude", lists]
    args += ["--keys", str(tmp_path / "keys"), "--own", "2", "--shared", "1", "--planted", "1"]
    with pytest.raises(SystemExit, match="guide not found"):
        AO.main([*args, "--guide", str(tmp_path / "no_guide.md"), "--draft"])
    bare = tmp_path / "bare.md"
    bare.write_text("# Guide\n\n**Version v9.**\n\n## Appendix A. Statements\n\nNone yet.\n")
    with pytest.raises(SystemExit, match="no excluded statement found in its Appendix A"):
        AO.main([*args, "--guide", str(bare)])
    typo = tmp_path / "typo.md"
    typo.write_text(GUIDE)  # three of its four rows name no statement of these captures
    with pytest.raises(SystemExit, match="3 rows of the guide's Appendix A match no event") as stop:
        AO.main([*args, "--guide", str(typo)])
    assert "alpha injection, usp, acme pharma, 2022-03-05; nothing tablets" in str(stop.value)
    assert not (tmp_path / "out").exists()
    assert AO.main([*args, "--guide", str(typo), "--draft"]) == 0
    manifest = json.loads((tmp_path / "out" / "outcome_train_manifest.json").read_text())
    assert manifest["guide_examples"] == 4 and manifest["guide_examples_unmatched"] == 3
    assert AO.main([*args, "--guide", str(bare), "--draft"]) == 0
    manifest = json.loads((tmp_path / "out" / "outcome_train_manifest.json").read_text())
    assert manifest["guide_examples"] == 0 and manifest["excluded_threads"] == 1


def test_a_final_set_is_replaced_only_on_request(tmp_path: Path) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    lists = str(sample_list(tmp_path / "lists", built, G2).parent)
    args = ["--half", "train", "--exclude", lists]
    _, out, _ = run_sheets(tmp_path, 2022, *args)
    before = {p: p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}
    for more in (["--own", "1"], ["--draft"]):  # another final set, or a draft, in its place
        with pytest.raises(SystemExit, match="holds a final set that this run would change"):
            run_sheets(tmp_path, 2022, *args, *more)
        assert before == {p: p.read_bytes() for p in sorted(out.rglob("*")) if p.is_file()}
    assert run_sheets(tmp_path, 2022, *args, "--own", "1", "--replace")[2] == 0
    after = json.loads((out / "outcome_train_manifest.json").read_text())
    assert after["sizes"]["own"] == 1 and after["counts"]["real_drawn"] == 3
    assert (out / "outcome_A1_train.csv").read_bytes() != before[out / "outcome_A1_train.csv"]


def test_a_second_round_skips_the_first_sample_and_a_list_is_audited_as_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    lists = str(sample_list(tmp_path / "lists", built, G2).parent)
    _, out, _ = run_sheets(tmp_path, 2022, "--half", "train", "--exclude", lists)
    names = AO.file_names("train")
    first = AO.read_sheet(out / names["sample"])[1]
    key = AO.read_sheet(out / "keys" / names["key"])[1]
    # a fresh draw: the first round's sample, named by itself, is kept out of the pool
    fresh = tmp_path / "round2"
    more = ["--round", "2", "--out", str(fresh), "--keys", str(fresh / "keys")]
    more += ["--exclude", lists, str(out / names["sample"])]
    assert run_sheets(tmp_path, 2022, "--half", "train", *more)[2] == 0
    second = AO.read_sheet(fresh / names["sample"])[1]
    assert not {r["thread_id"] for r in second} & {r["thread_id"] for r in first}
    manifest = json.loads((fresh / names["manifest"]).read_text())
    assert manifest["draw"] == "train/round2"
    assert [u["kind"] for u in manifest["exclusion_lists"]] == [
        "labelling",
        "earlier outcome audit",
    ]
    assert manifest["excluded_threads"] == 3 + len(first)
    # the first sample alone is no labelling list
    alone = ["--round", "2", "--out", str(fresh), "--exclude", str(out / names["sample"])]
    with pytest.raises(SystemExit, match="no sample list"):
        run_sheets(tmp_path, 2022, "--half", "train", *alone)
    # an id of the first sample that the rebuilt corpus lacks is reported, not a stop
    stale = tmp_path / "outcome_train_sample.csv"
    stale.write_text((out / names["sample"]).read_text() + "Egone,Sgone,Tgone\n")
    more[-1] = str(stale)
    capsys.readouterr()
    assert run_sheets(tmp_path, 2022, "--half", "train", *more, "--replace")[2] == 0
    assert "WARNING: 2 ids of an earlier outcome-audit sample name no event" in (
        capsys.readouterr().out
    )
    # the first round's key as a list: its real items again, to the same auditors, none planted
    again = tmp_path / "again"
    listed = ["--round", "2", "--out", str(again), "--keys", str(again / "keys")]
    listed += ["--exclude", lists, "--planted", "0", "--items", str(out / "keys" / names["key"])]
    assert run_sheets(tmp_path, 2022, "--half", "train", *listed)[2] == 0
    printed = capsys.readouterr().out
    assert "real items 5 of 5; planted 0 of 0" in printed
    assert "listed for re-audit 5; not events of this half in this build: 0" in printed
    new_key = AO.read_sheet(again / "keys" / names["key"])[1]
    real = {k["event_id"]: k for k in key if not k["planted"]}
    assert {k["event_id"]: k["assigned_to"] for k in new_key} == {
        e: k["assigned_to"] for e, k in real.items()
    }
    assert not {k["audit_id"] for k in new_key} & {k["audit_id"] for k in key}
    assert all(k[f"true_{d}_upper"] == real[k["event_id"]][f"true_{d}_upper"] for k in new_key
               for d in AO.DEFS)  # fmt: skip
    manifest = json.loads((again / names["manifest"]).read_text())
    assert manifest["draw"] == "train/round2/items" and manifest["items_list"] == {
        "changed_only": False,
        "sha256": AO.sha256_file(out / "keys" / names["key"]),
    }
    assert manifest["counts"]["listed"] == 5 and manifest["sizes"]["own"] == 0
    # no planted item unless it is asked for
    plain = ["sheets", "--half", "train", "--captures", str(tmp_path / "captures"), "--round", "2"]
    plain += ["--guide", str(tmp_path / "guide.md"), "--exclude", lists, "--out", str(again)]
    plain += ["--keys", str(again / "keys"), "--items", str(out / "keys" / names["key"])]
    assert AO.main(plain) == 0
    assert json.loads((again / names["manifest"]).read_text())["sizes"] == {
        "own": 0,
        "planted_per_auditor": 0,
        "shared": 0,
    }


def test_rows_of_an_earlier_audit_sample_are_shown_and_rows_of_a_labelling_sample_are_not(
    tmp_path: Path,
) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    lists = sample_list(tmp_path / "lists", built, B2).parent
    g1, g2 = (built.table.loc[built.table["presentation"] == p].iloc[0] for p in (G1, G2))
    items = tmp_path / "items.csv"
    items.write_text(f"event_id,assigned_to\n{g1['event_id']},A1\n")
    d1 = built.table.loc[built.table["presentation"] == D1].iloc[0]
    earlier = tmp_path / "outcome_train_sample.csv"  # G2 and D1 were audited in an earlier round
    rows = [",".join(r[c] for c in AO.ID_COLUMNS) for r in (g2, d1)]
    earlier.write_text(",".join(AO.ID_COLUMNS) + "\n" + "\n".join(rows) + "\n")
    args = ["--half", "train", "--planted", "0", "--items", str(items)]
    _, out, code = run_sheets(tmp_path, 2022, *args, "--exclude", str(lists), str(earlier))
    manifest = json.loads((out / "outcome_train_manifest.json").read_text())
    # B2, the two Alpha threads of the guide, G2 and D1; not D2, which shares D1's statement
    assert manifest["excluded_threads"] == 5 and manifest["earlier_sample_ids_unknown"] == 0
    traces = AO.read_sheet(out / "outcome_train_traces.csv")[1]
    shown = [t for t in traces if t["present"] == "other_thread"]
    assert code == 0 and len(shown) == 5 and {t["presentation"] for t in shown} == {G2}
    assert {t["related_information"] for t in shown} == {"Estimated recovery: June"}
    # the same thread in a labelling list: names only
    (lists / "sample_check.csv").write_text(f"event_id\n{g2['event_id']}\n")
    args += ["--exclude", str(lists), "--replace"]
    assert run_sheets(tmp_path, 2022, *args)[2] == 0
    traces = AO.read_sheet(out / "outcome_train_traces.csv")[1]
    held = [t for t in traces if t["present"] == AO.WITHHELD]
    assert len(held) == 5 and {t["related_information"] for t in held} == {""}
    assert not [t for t in traces if t["present"] == "other_thread"]


def test_listed_items_keep_their_threads_from_the_planted_ones(train: AO.Built) -> None:
    everything = [{"event_id": e} for e in train.frame.index]
    drawn = AO.draw_items(train, set(), 0, 0, 1, "t", everything)
    assert drawn.counts["real_drawn"] == len(train.frame) == drawn.counts["listed"]
    assert drawn.counts["planted_drawn"] == 0 and drawn.counts["planted_wanted"] == 2
    assert {it.assigned for it in drawn.items} == {"both"}
    some = [{"event_id": first_event(train, P10), "assigned_to": "A2"}, {"event_id": "Egone"}]
    drawn = AO.draw_items(train, set(), 0, 0, 1, "t", some)
    assert drawn.counts["listed_not_in_build"] == 1 and drawn.counts["real_wanted"] == 2
    planted = [it for it in drawn.items if it.planted]
    assert len(planted) == 2 and [it.assigned for it in drawn.items if not it.planted] == ["A2"]
    threads = train.frame.loc[[it.event_id for it in drawn.items], "thread_id"]
    assert threads.is_unique


def test_a_list_for_one_auditor_leaves_the_other_sheet_empty_and_is_scored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built = AO.load(write_world(tmp_path / "captures", 2022), "train")
    items = tmp_path / "items.csv"
    items.write_text(f"event_id,assigned_to\n{first_event(built, P10)},A1\n")
    args = ["--half", "train", "--draft", "--exclude", "--planted", "0", "--items", str(items)]
    _, out, code = run_sheets(tmp_path, 2022, *args)
    names = AO.file_names("train")
    blank = AO.read_sheet(out / names["A2"])[1]
    assert code == 0 and blank == [] and len(AO.read_sheet(out / names["A1"])[1]) == 1
    assert AO.validate([], blank) == ([], []) and AO.validate([], None)[0] == [
        "the sheet has no rows"
    ]
    assert AO.validate([], [filled("Q1")])[0] == ["the sheet has no rows"]
    key = {k["audit_id"]: k for k in AO.read_sheet(out / "keys" / names["key"])[1]}
    back = {a: tmp_path / "returned" / names[a] for a in AO.AUDITORS}
    for auditor, path in back.items():
        fill(out / names[auditor], path, key, set())
    score = ["score", "--half", "train", "--dir", str(out), "--a1", str(back["A1"])]
    score += ["--a2", str(back["A2"]), "--key", str(out / "keys" / names["key"])]
    assert AO.main(score) == 0
    assert "1 real items" in capsys.readouterr().out
    result = json.loads((out / names["score"]).read_text())
    assert result["allowed_errors"] == 0 and result["auditor_flagged"]["A2"]["real_items"] == 0


def test_only_the_listed_items_whose_bracket_changed_are_kept(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude")
    names = AO.file_names("train")
    meta, key = AO.read_sheet(out / "keys" / names["key"])
    real = [k for k in key if not k["planted"]]
    target = next(k for k in real if k["true_B_upper"])
    old = tmp_path / "old_key.csv"
    target["true_B_upper"] = "2000-01-01"  # as if the rule had since moved this bound
    key.append({**real[0], "event_id": "Egone", "audit_id": "Qgone"})
    old.write_text(AO.csv_text(AO.KEY_COLUMNS, key, meta, sheet=False))
    again = tmp_path / "changed"
    args = ["--half", "train", "--draft", "--exclude", "--round", "2", "--out", str(again)]
    args += ["--keys", str(again / "keys"), "--planted", "0", "--items", str(old)]
    assert run_sheets(tmp_path, 2022, *args, "--changed")[2] == 0
    printed = capsys.readouterr().out
    assert "real items 1 of 2" in printed and "not events of this half in this build: 1" in printed
    new_key = AO.read_sheet(again / "keys" / names["key"])[1]
    assert [k["event_id"] for k in new_key] == [target["event_id"]]
    assert (
        new_key[0]["assigned_to"] == target["assigned_to"] and new_key[0]["true_B_upper"] > "2022"
    )
    # nothing changed: nothing to audit, nothing written
    unchanged = tmp_path / "unchanged"
    same = ["--half", "train", "--draft", "--exclude", "--round", "2", "--out", str(unchanged)]
    same += ["--keys", str(unchanged / "keys"), "--planted", "0"]
    same += ["--items", str(out / "keys" / names["key"])]
    assert run_sheets(tmp_path, 2022, *same, "--changed")[2] == 0
    assert "no item to audit; nothing was written" in capsys.readouterr().out
    assert not unchanged.exists()
    # the list must be usable
    with pytest.raises(SystemExit, match="--changed goes with --items"):
        run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude", "--changed")
    bare = tmp_path / "bare.csv"
    bare.write_text(f"event_id,assigned_to\n{target['event_id']},A1\n")
    with pytest.raises(SystemExit, match="needs the true_"):
        run_sheets(tmp_path, 2022, *same[:-1], str(bare), "--changed")
    bare.write_text(f"event_id,assigned_to\n{target['event_id']},A3\n")
    with pytest.raises(SystemExit, match="assigned_to must be A1, A2, both"):
        run_sheets(tmp_path, 2022, *same[:-1], str(bare))
    bare.write_text(f"event_id\n{target['event_id']}\n{target['event_id']}\n")
    with pytest.raises(SystemExit, match="listed more than once"):
        run_sheets(tmp_path, 2022, *same[:-1], str(bare))
    bare.write_text(f"event_id\n{target['event_id']}\n")  # no auditor named: both check it
    assert run_sheets(tmp_path, 2022, *same[:-1], str(bare), "--planted", "1")[2] == 0
    both = AO.read_sheet(unchanged / "keys" / names["key"])[1]
    assert Counter(k["assigned_to"] for k in both if not k["planted"]) == {"both": 1}
    assert Counter(k["assigned_to"] for k in both if k["planted"]) == {"A1": 1, "A2": 1}
    assert target["event_id"] not in {k["event_id"] for k in both if k["planted"]}


def test_draft_and_test_half_folders() -> None:
    assert AO.output_dirs("train", False, None, None) == (AO.TRAIN_OUT, AO.TRAIN_KEYS, "")
    draft = AO.output_dirs("train", True, None, None)
    assert draft == (AO.TRAIN_OUT / "draft", AO.TRAIN_KEYS / "draft", "")
    assert AO.output_dirs("train", True, Path("x"), Path("y")) == (Path("x"), Path("y"), "")
    with pytest.raises(SystemExit, match="needs --out"):
        AO.output_dirs("test", False, None, None)
    with pytest.raises(SystemExit, match="only under a folder named sealed"):
        AO.output_dirs("test", False, Path("open/audit"), None)
    with pytest.raises(SystemExit, match="only under a folder named sealed"):
        AO.output_dirs("test", True, Path("unsealed/audit"), None)
    sealed = Path("data/sealed/audit")
    assert AO.output_dirs("test", False, sealed, Path("else")) == (sealed, sealed, "keys/")


def test_sealed_mode_writes_only_under_its_directory_and_prints_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match="needs --out"):
        AO.main(["sheets", "--half", "test"])
    captures = write_world(tmp_path / "captures", 2024)  # every statement is in the test period
    (tmp_path / "guide.md").write_text(guide_for(2024))
    lists = sample_list(tmp_path / "lists", AO.load(captures, "test"), G2).parent
    known = {p for p in tmp_path.rglob("*") if p.is_file()}
    sealed = tmp_path / "sealed" / "audit"
    args = ["sheets", "--half", "test", "--captures", str(captures), "--exclude", str(lists)]
    args += ["--guide", "guide.md", "--keys", str(tmp_path / "elsewhere")]
    args += ["--own", "2", "--shared", "1", "--planted", "1"]
    with pytest.raises(SystemExit, match="only under a folder named sealed"):
        AO.main([*args, "--out", str(tmp_path / "open" / "audit")])
    with pytest.raises(SystemExit, match="no sample list"):  # the test half needs the lists too
        AO.main([*args[:5], "--exclude", "--out", str(sealed), "--guide", "guide.md"])
    assert {p for p in tmp_path.rglob("*") if p.is_file()} == known
    assert AO.main([*args, "--out", str(sealed)]) == 0
    new = {p for p in tmp_path.rglob("*") if p.is_file()} - known
    assert new and all(p.is_relative_to(sealed) for p in new)
    names = AO.file_names("test")
    assert (sealed / "keys" / names["key"]).is_file() and (sealed / names["strata"]).is_file()
    assert len(AO.read_sheet(sealed / names["A1"])[1]) == 4
    printed = capsys.readouterr().out
    assert "real items 5 of 5; planted 2 of 2" in printed
    for word in (*AO.TYPES, "le31", "32to90", "gt90", "reconfirmed", "stratum", "end_of_archive"):
        assert word not in printed
    lines = [line for line in printed.splitlines() if "wrote" not in line]
    assert not re.search(r"20\d\d-\d\d-\d\d", "\n".join(lines))
    key = AO.read_sheet(sealed / "keys" / names["key"])[1]
    assert all(k["true_B_lower"] >= "2024" for k in key if k["true_B_lower"])
    assert G2 not in {r["presentation"] for r in AO.read_sheet(sealed / names["A1"])[1]}
    # scoring: files only under the sealed directory, counts only on the screen
    by_id = {k["audit_id"]: k for k in key}
    wrong = {next(i for i, k in by_id.items() if k["assigned_to"] == "both")}
    back = {a: sealed / "returned" / names[a] for a in AO.AUDITORS}
    for auditor, path in back.items():
        fill(sealed / names[auditor], path, by_id, wrong)
    score = ["score", "--half", "test", "--a1", str(back["A1"]), "--a2", str(back["A2"])]
    with pytest.raises(SystemExit, match="needs --dir"):
        AO.main(score)
    with pytest.raises(SystemExit, match="only under a folder named sealed"):
        AO.main([*score, "--dir", str(tmp_path / "open")])
    score += ["--dir", str(sealed)]
    with pytest.raises(SystemExit, match="stays in the sealed directory"):
        AO.main([*score, "--adjudication", str(tmp_path / "adjudication.csv")])
    assert AO.main(score) == 3
    meta, rows = AO.read_sheet(sealed / names["adjudication"])
    assert len(rows) == 1 and rows[0]["definition"] == "B"  # the shared item, marked by both
    for r in rows:
        r.update(decision="confirmed", confirmed_codes="O6", cause="capture skipped")
    columns = (*AO.ADJUDICATION_SHOWN, *AO.ADJUDICATION_ENTERED)
    (sealed / names["adjudication"]).write_text(AO.csv_text(columns, rows, meta))
    assert AO.main(score) == 1
    result = json.loads((sealed / names["score"]).read_text())
    assert result["B"]["confirmed_errors"] == 1 and result["B"]["codes"] == {"O6": 1}
    for d in AO.DEFS:  # no breakdown by stratum until the registered evaluator has run
        assert "errors_by_stratum" not in result[d]
        assert "agreement_rate_reweighted" not in result[d]
    printed = capsys.readouterr().out
    assert "confirmed errors 1 of 5" in printed
    for word in (*AO.TYPES, "le31", "32to90", "gt90", "reconfirmed", "stratum", "end_of_archive"):
        assert word not in printed
    lines = [line for line in printed.splitlines() if "wrote" not in line]
    assert not re.search(r"20\d\d-\d\d-\d\d", "\n".join(lines))
    new = {p for p in tmp_path.rglob("*") if p.is_file()} - known
    assert all(p.is_relative_to(sealed) for p in new)


def test_header_hashes_name_the_builder_that_was_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    hashes = AO.builder_hashes()
    assert hashes["corpus_py"] == f"sha256 {AO.sha256_file(Path(C.__file__))[:16]}"
    doc = AO.hashlib.sha256(C.__doc__.encode()).hexdigest()[:16]
    assert hashes["corpus_docstring"] == f"sha256 {doc}"
    monkeypatch.setattr(C, "__doc__", C.__doc__ + " (edited after loading)")
    with pytest.raises(SystemExit, match="changed on disk"):
        AO.builder_hashes()


def test_a_sink_refuses_a_path_outside_its_root(tmp_path: Path) -> None:
    sink = AO.Sink(tmp_path / "sealed")
    with pytest.raises(ValueError, match="outside"):
        sink.write("../leak.csv", "x")
    assert not (tmp_path / "leak.csv").exists()
    sink.write("keys/a.csv", "x")
    assert sink.written == {"keys/a.csv": AO.hashlib.sha256(b"x").hexdigest()}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def filled(audit_id: str = "Q1", **cells: str) -> dict[str, str]:
    base = dict.fromkeys(AO.SHEET_COLUMNS, "")
    return {**base, "audit_id": audit_id, "verdict_B": "ok", "verdict_A": "ok", **cells}


def test_validator_accepts_well_formed_rows() -> None:
    rows = [
        filled("Q1"),
        filled(
            "Q2",
            verdict_B="error",
            codes_B="O5; O6",
            true_B_type="recovered",
            true_B_lower="2020-04-02",
            true_B_upper="2020-06-12",
        ),
        filled("Q3", note_codes="N1;N4", dou_first_recovered="2020-05-12"),
        filled("Q6", note_codes="N6"),
        filled("Q4", verdict_A="cannot_tell", note="the row is missing for three captures"),
        filled("Q5", verdict_B="error", codes_B="O1", note="NDC of another strength"),
    ]
    assert AO.validate(rows) == ([], [])


@pytest.mark.parametrize(
    ("cells", "message"),
    [
        ({"verdict_B": ""}, "verdict_B must be one of"),
        ({"verdict_A": "wrong"}, "verdict_A must be one of"),
        ({"verdict_B": "error"}, "codes_B is empty"),
        ({"verdict_B": "error", "codes_B": "O6"}, "give true_B_type"),
        ({"verdict_B": "error", "codes_B": "O12", "note": "x"}, "unknown O12"),
        ({"codes_A": "O5"}, "codes_A given but verdict_A is ok"),
        ({"true_B_upper": "2020-01-01"}, "true_B_* given but verdict_B is ok"),
        ({"verdict_B": "error", "codes_B": "O8", "true_B_type": "open"}, "true_B_type must be"),
        ({"verdict_A": "error", "codes_A": "O6", "true_A_upper": "6/12/2020"}, "not a YYYY-MM-DD"),
        (
            {
                "verdict_B": "error",
                "codes_B": "O5",
                "true_B_lower": "2020-06-12",
                "true_B_upper": "2020-04-02",
            },
            "true_B_lower is after",
        ),
        ({"verdict_B": "cannot_tell"}, "say why in note"),
        ({"note_codes": "N1"}, "dou_first_recovered is given exactly when"),
        ({"dou_first_recovered": "2020-05-12"}, "dou_first_recovered is given exactly when"),
        ({"note_codes": "N7"}, "unknown N7"),
        ({"note_codes": "F1"}, "unknown F1"),
        ({"verdict_B": "error", "codes_B": "O9", "true_B_type": "censored"}, "O9 needs a note"),
    ],
)
def test_validator_reports_each_malformed_cell(cells: dict[str, str], message: str) -> None:
    problems, _ = AO.validate([filled("Q1", **cells)])
    assert any(message in p and p.startswith("Q1: ") for p in problems), problems


def test_validator_compares_ids_and_shown_cells_with_the_blank() -> None:
    blank = [filled(i, generic="Alpha", verdict_B="", verdict_A="") for i in ("Q1", "Q2", "Q3")]
    back = [filled(i, generic=g) for i, g in (("Q1", "Alpha"), ("Q2", "Beta"), ("Q1", "Alpha"))]
    back.append(filled("Q9"))
    problems, warnings = AO.validate(back, blank)
    assert "Q1: listed more than once" in problems and "Q3: row missing" in problems
    assert "Q9: not an item of this sheet" in problems
    assert warnings == ["Q2: shown cells changed: generic"]
    assert AO.validate([{"audit_id": "Q1"}])[0][0].startswith("missing columns")


def test_sheet_parser_survives_a_spreadsheet_round_trip() -> None:
    text = AO.csv_text(
        ("audit_id", "note"), [{"audit_id": "Q1", "note": "a, b"}], {"auditor": "A1"}
    )
    assert text == '# auditor: A1\n"audit_id","note"\n"Q1","a, b"\n'
    plain = AO.csv_text(("event_id", "n"), [{"event_id": "E1", "n": 2}], {}, sheet=False)
    assert plain == "event_id,n\nE1,2\n"
    risky = [{"audit_id": "Q1", "note": "=1+1"}, {"audit_id": "Q2", "note": "-5 days"}]
    guarded = AO.csv_text(("audit_id", "note", "n"), [{**r, "n": -3} for r in risky], {})
    assert '"\'=1+1"' in guarded and '"\'-5 days"' in guarded and '"-3"' in guarded
    mangled = (
        chr(0xFEFF)
        + '"# auditor: A1",\r\n"# session_start: 2 Oct, 14:05",\r\n,\r\naudit_id,note\r\n'
    )
    meta, rows = AO.parse_sheet(mangled + ' Q1 ,"a, b"\r\n,\r\n')
    assert meta == {"auditor": "A1", "session_start": "2 Oct, 14:05"}
    assert rows == [{"audit_id": "Q1", "note": "a, b"}] == AO.parse_sheet(text)[1]


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def synthetic_key(n_strata: int = 5) -> list[dict[str, str]]:
    """50 real items (20 for each auditor, 10 shared) in five strata, and 3 planted for each."""
    key = []
    who = AO.assign(50, 20, 10)
    for i in range(50):
        stratum = f"s{i % n_strata}"
        base = dict.fromkeys(AO.KEY_COLUMNS, "")
        pool = "1000" if stratum == "s0" else "10"
        base.update(audit_id=f"Q{i:02d}", assigned_to=who[i], stratum=stratum, stratum_pool=pool)
        base.update(shown_B_type="recovered", shown_A_type="censored")
        key.append(base)
    for j, auditor in enumerate(("A1", "A1", "A1", "A2", "A2", "A2")):
        base = dict.fromkeys(AO.KEY_COLUMNS, "")
        base.update(audit_id=f"P{j}", assigned_to=auditor, planted="upper_later")
        base.update(planted_definitions="B", expected_code="O6", stratum="s0", stratum_pool="1000")
        key.append(base)
    return key


def all_ok(key: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    sheets: dict[str, dict[str, dict[str, str]]] = {a: {} for a in AO.AUDITORS}
    for k in key:
        for auditor in AO.auditors_of(k):
            sheets[auditor][k["audit_id"]] = filled(k["audit_id"])
    return sheets


def mark_error(
    sheet: dict[str, dict[str, str]], audit_id: str, d: str = "B", code: str = "O6"
) -> None:
    sheet[audit_id].update({f"verdict_{d}": "error", f"codes_{d}": code, "note": "see trace"})


def decide(
    wanted: list[dict[str, str]], decision: str = "confirmed", cause: str = "c"
) -> list[dict[str, str]]:
    return [
        {**w, "decision": decision, "confirmed_codes": "O6", "cause": f"{cause}{i}"}
        for i, w in enumerate(wanted)
    ]


def own_items(key: list[dict[str, str]], auditor: str) -> list[str]:
    return [k["audit_id"] for k in key if k["assigned_to"] == auditor and not k["planted"]]


def test_two_confirmed_errors_pass_and_three_fail() -> None:
    key = synthetic_key()
    for n_errors, passes in ((0, True), (2, True), (3, False)):
        sheets = all_ok(key)
        for audit_id in own_items(key, "A1")[:n_errors]:
            mark_error(sheets["A1"], audit_id)
        wanted = AO.adjudication_rows(key, sheets)
        assert len(wanted) == n_errors
        decisions, problems = AO.check_adjudication(wanted, decide(wanted))
        assert problems == []
        result = AO.score(key, sheets, decisions)
        assert result["real_items"] == 50 and result["allowed_errors"] == 2
        assert result["B"]["confirmed_errors"] == n_errors and result["B"]["pass"] is passes
        assert result["A"]["confirmed_errors"] == 0 and result["A"]["pass"] is True
        assert result["pass"] is passes and result["rule_fix_required"] is (not passes)
        assert result["B"]["agreement_rate"] == (50 - n_errors) / 50
        assert result["B"]["codes"] == ({"O6": n_errors} if n_errors else {})


def test_each_definition_is_judged_on_its_own() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    for audit_id in own_items(key, "A2")[:3]:
        mark_error(sheets["A2"], audit_id, "A", "O8")
    mark_error(sheets["A2"], own_items(key, "A2")[0], "B", "O5")
    wanted = AO.adjudication_rows(key, sheets)
    assert Counter(w["definition"] for w in wanted) == {"A": 3, "B": 1}
    decisions, _ = AO.check_adjudication(wanted, decide(wanted))
    result = AO.score(key, sheets, decisions)
    assert result["B"]["pass"] is True and result["A"]["pass"] is False and result["pass"] is False
    assert result["auditor_flagged"]["A2"]["error_A"] == 3
    assert result["auditor_flagged"]["A1"] == {
        "real_items": 30, "error_B": 0, "cannot_tell_B": 0, "error_A": 0, "cannot_tell_A": 0,
    }  # fmt: skip


def test_rejected_and_unresolved_rows_do_not_count_as_confirmed() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    ids = own_items(key, "A1")[:4]
    for audit_id in ids[:3]:
        mark_error(sheets["A1"], audit_id)
    sheets["A1"][ids[3]].update(verdict_B="cannot_tell", note="row missing")
    wanted = AO.adjudication_rows(key, sheets)
    filled_in = decide(wanted)
    filled_in[0]["decision"] = "rejected"
    filled_in[3]["decision"] = "unresolved"
    decisions, problems = AO.check_adjudication(wanted, filled_in)
    assert problems == []
    result = AO.score(key, sheets, decisions)
    assert result["B"]["confirmed_errors"] == 2 and result["B"]["unresolved"] == 1
    assert result["B"]["pass"] is True and result["B"]["pass_if_unresolved_count"] is False
    assert result["auditor_flagged"]["A1"]["error_B"] == 3
    assert result["auditor_flagged"]["A1"]["cannot_tell_B"] == 1


def test_the_same_code_and_cause_twice_asks_for_a_rule_fix() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    for audit_id in own_items(key, "A1")[:2]:
        mark_error(sheets["A1"], audit_id)
    wanted = AO.adjudication_rows(key, sheets)
    rows = decide(wanted)
    for r in rows:
        r["cause"] = "Allocation read as available."
    result = AO.score(key, sheets, AO.check_adjudication(wanted, rows)[0])
    assert result["pass"] is True and result["rule_fix_required"] is True
    assert result["repeated_causes"] == ["O6: allocation read as available"]


def test_reweighted_rate_and_wilson_interval() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    rare = next(k for k in key if k["stratum"] == "s1")
    mark_error(sheets[AO.auditors_of(rare)[0]], rare["audit_id"])
    wanted = AO.adjudication_rows(key, sheets)
    result = AO.score(key, sheets, AO.check_adjudication(wanted, decide(wanted))[0])
    assert result["B"]["agreement_rate"] == 0.98
    assert result["B"]["errors_by_stratum"] == {"s1": 1}
    # s1 holds 10 of the 1,040 pool events and one of its ten items is wrong
    assert result["B"]["agreement_rate_reweighted"] == pytest.approx(1 - (10 / 1040) * 0.1)
    low, high = result["B"]["agreement_wilson95"]
    assert low == pytest.approx(0.8950, abs=5e-4) and high == pytest.approx(0.9965, abs=5e-4)
    assert AO.wilson(0, 0) is None and AO.wilson(50, 50)[1] == pytest.approx(1.0)


def test_planted_items_are_scored_by_the_key_and_kept_out_of_the_pass_rule() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    for audit_id in ("P0", "P1", "P2", "P3"):
        auditor = "A1" if audit_id < "P3" else "A2"
        mark_error(sheets[auditor], audit_id, "B", "O6" if audit_id != "P1" else "O4")
    sheets["A2"]["P4"].update(verdict_A="error", codes_A="O6", note="x")  # not the planted side
    assert AO.adjudication_rows(key, sheets) == []
    result = AO.score(key, sheets, {})
    assert result["planted"]["A1"] == {
        "planted": 3, "caught": 3, "caught_with_expected_code": 2, "recheck_own_items": False,
    }  # fmt: skip
    assert result["planted"]["A2"]["caught"] == 1 and result["planted"]["A2"]["recheck_own_items"]
    assert result["pass"] is True and result["B"]["confirmed_errors"] == 0
    sheets["A2"]["P5"].update(verdict_B="cannot_tell", note="?")  # not an error verdict: a miss
    assert AO.score(key, sheets, {})["planted"]["A2"]["caught"] == 1
    mark_error(sheets["A2"], "P5")
    again = AO.score(key, sheets, {})["planted"]["A2"]
    assert again["caught"] == 2 and again["recheck_own_items"] is False  # one miss is allowed


def test_shared_items_agreement_and_kappa() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    shared = [k["audit_id"] for k in key if k["assigned_to"] == "both"]
    for audit_id in shared[:2]:
        mark_error(sheets["A1"], audit_id)
    mark_error(sheets["A2"], shared[0])
    sheets["A2"][shared[9]].update(verdict_B="cannot_tell", note="?")
    result = AO.score(key, sheets, None)
    assert result["adjudicated"] is False and "pass" not in result and "B" not in result
    b = result["shared_items"]["B"]
    assert (b["items"], b["same_verdict"], b["with_cannot_tell"]) == (10, 8, 1)
    # nine clear pairs: 1 error/error, 1 error/ok, 7 ok/ok
    assert b["kappa_ok_error"] == pytest.approx((8 / 9 - 58 / 81) / (1 - 58 / 81))
    assert result["shared_items"]["A"]["kappa_ok_error"] is None
    wanted = AO.adjudication_rows(key, sheets)
    assert [w["audit_id"] for w in wanted] == sorted([shared[0], shared[1], shared[9]])
    assert wanted[0]["A1_verdict"] == "error" and wanted[0]["A2_verdict"] == "error"
    assert AO.cohen_kappa([]) is None
    assert AO.cohen_kappa([("ok", "error"), ("error", "ok")]) == pytest.approx(-1.0)


def test_adjudication_sheet_must_be_complete() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    ids = own_items(key, "A1")[:3]
    for audit_id in ids:
        mark_error(sheets["A1"], audit_id)
    wanted = AO.adjudication_rows(key, sheets)
    rows = decide(wanted)
    rows[0]["decision"] = ""
    rows[1]["confirmed_codes"] = ""
    rows[2]["cause"] = ""
    rows.append({"audit_id": "Q49", "definition": "A", "decision": "rejected"})
    _, problems = AO.check_adjudication(wanted, rows)
    assert len(problems) == 4
    assert any("no decision" in p for p in problems)
    assert any("confirmed_codes" in p for p in problems)
    assert any("needs a cause" in p for p in problems)
    assert any("not sent to adjudication" in p for p in problems)


def fill(path: Path, target: Path, key: dict[str, dict[str, str]], errors: set[str]) -> None:
    """Return a sheet: planted items and ``errors`` marked as errors under B, the rest ok."""
    meta, rows = AO.read_sheet(path)
    for r in rows:
        wrong = bool(key[r["audit_id"]]["planted"]) or r["audit_id"] in errors
        r.update(verdict_B="error" if wrong else "ok", verdict_A="ok")
        r.update(codes_B="O6" if wrong else "", note="upper is late" if wrong else "")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(AO.csv_text(AO.SHEET_COLUMNS, rows, meta))


def test_score_command_from_returned_sheets_to_pass_or_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude")
    names = AO.file_names("train")
    key = {k["audit_id"]: k for k in AO.read_sheet(out / "keys" / names["key"])[1]}
    wrong = {next(i for i, k in key.items() if k["assigned_to"] == "both")}
    back = {a: tmp_path / "returned" / names[a] for a in AO.AUDITORS}
    for auditor, path in back.items():
        fill(out / names[auditor], path, key, wrong if auditor == "A1" else set())
    args = ["score", "--half", "train", "--dir", str(out)]
    args += ["--key", str(out / "keys" / names["key"])]
    args += ["--a1", str(back["A1"]), "--a2", str(back["A2"])]
    assert AO.main(args) == 3  # one shared item to adjudicate
    printed = capsys.readouterr().out
    assert "A1: planted caught 1 of 1" in printed and "awaiting adjudication" in printed
    pending = json.loads((out / names["score"]).read_text())
    assert pending["counts"]["real_drawn"] == 5 and pending["counts"]["pool"] > 5
    assert pending["adjudicated"] is False and pending["sha256"]["A1"] == AO.sha256_file(back["A1"])
    meta, rows = AO.read_sheet(out / names["adjudication"])
    assert len(rows) == 1 and rows[0]["A1_verdict"] == "error" and rows[0]["A2_verdict"] == "ok"
    assert AO.main(args) == 3  # the adjudication sheet exists but has no decision yet
    rows[0].update(decision="confirmed", confirmed_codes="O6", cause="capture skipped")
    columns = (*AO.ADJUDICATION_SHOWN, *AO.ADJUDICATION_ENTERED)
    (out / names["adjudication"]).write_text(AO.csv_text(columns, rows, meta))
    assert AO.main(args) == 1  # 5 real items allow no error
    result = json.loads((out / names["score"]).read_text())
    assert result["B"]["confirmed_errors"] == 1 and result["allowed_errors"] == 0
    assert result["pass"] is False and result["A"]["pass"] is True
    assert result["shared_items"]["B"]["same_verdict"] == 0
    assert "FAIL" in capsys.readouterr().out
    rows[0].update(decision="rejected", confirmed_codes="", cause="")
    (out / names["adjudication"]).write_text(AO.csv_text(columns, rows, meta))
    assert AO.main(args) == 0
    assert json.loads((out / names["score"]).read_text())["pass"] is True
    # a sheet that does not validate is not scored
    text = back["A2"].read_text().replace('"ok","ok",', '"fine","ok",', 1)
    back["A2"].write_text(text)
    assert AO.main(args) == 2
    assert "nothing was scored" in capsys.readouterr().out


def test_score_checks_the_set_before_it_reads_the_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude")
    names = AO.file_names("train")
    key_path = out / "keys" / names["key"]
    key = {k["audit_id"]: k for k in AO.read_sheet(key_path)[1]}
    back = {a: tmp_path / "returned" / names[a] for a in AO.AUDITORS}
    for auditor, path in back.items():
        fill(out / names[auditor], path, key, set())
    args = ["score", "--half", "train", "--dir", str(out), "--key", str(key_path)]
    args += ["--a1", str(back["A1"]), "--a2", str(back["A2"])]
    assert AO.main(args) == 0
    capsys.readouterr()
    kept = {p: p.read_bytes() for p in (key_path, out / names["A2"], out / names["manifest"])}
    score = out / names["score"]

    def refused(message: str) -> None:
        score.unlink(missing_ok=True)
        assert AO.main(args) == 2 and not score.exists()
        printed = capsys.readouterr().out
        assert message in printed and "nothing scored" in printed

    key_path.write_bytes(kept[key_path] + b"\n")  # another key, or one that was edited
    refused(f"is not the {names['key']} that the manifest lists")
    key_path.unlink()
    refused(f"{key_path} not found")
    key_path.write_bytes(kept[key_path])
    blank = out / names["A2"]
    blank.write_bytes(kept[blank].replace(b"# seed: 20261001", b"# seed: 1"))
    refused(f"is not the {names['A2']} that the manifest lists")
    blank.write_bytes(kept[blank])
    manifest = out / names["manifest"]
    manifest.write_text(json.dumps({"status": "draft", "files": {}}))
    refused(f"the manifest does not list {names['key']}")
    manifest.unlink()
    refused("the set cannot be checked")
    manifest.write_bytes(kept[manifest])
    assert AO.main(args) == 0 and score.is_file()
    blank.unlink()
    with pytest.raises(SystemExit, match=r"not found: .*outcome_A2_train\.csv"):
        AO.main(args)


def test_key_and_sheets_must_hold_the_same_items() -> None:
    key = synthetic_key()
    sheets = all_ok(key)
    assert AO.key_problems(key, sheets) == []
    moved = sheets["A1"].pop("P0")
    assert AO.key_problems(key, sheets) == [
        "the key and the sheet of A1 do not hold the same items"
    ]
    sheets["A1"]["P0"] = moved
    sheets["A2"]["Q99"] = filled("Q99")
    assert AO.key_problems(key, sheets) == [
        "the key and the sheet of A2 do not hold the same items"
    ]


def test_session_lines_give_the_minutes_per_item() -> None:
    assert AO.clock("9:05") == 545 and AO.clock(" 14:05:30 ") == 845
    assert AO.clock("24:00") is None and AO.clock("12:60") is None and AO.clock("2 Oct") is None
    two = {"session_start": "09:00; 14:00", "session_end": "09:40;14:25"}
    assert AO.session_minutes(two) == 65
    assert AO.session_minutes({"session_start": "23:50", "session_end": "00:20"}) == 30
    assert AO.session_minutes({"session_start": "09:00", "session_end": ""}) is None
    assert AO.session_minutes({"session_start": "09:00; 10:00", "session_end": "09:30"}) is None
    assert AO.session_minutes({"session_start": "nine", "session_end": "ten"}) is None
    assert AO.session_minutes({}) is None
    worked = AO.timing({"session_start": "09:00", "session_end": "10:06"}, 33)
    assert worked == {"minutes": 66, "items": 33, "minutes_per_item": 2.0}
    assert AO.timing({}, 33) is None and AO.timing(two, 0) is None


def test_a_recheck_is_scored_beside_the_first_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run_sheets(tmp_path, 2022, "--half", "train", "--draft", "--exclude")
    names = AO.file_names("train")
    key_path = out / "keys" / names["key"]
    key = {k["audit_id"]: k for k in AO.read_sheet(key_path)[1]}
    own = next(i for i, k in key.items() if k["assigned_to"] == "A1" and not k["planted"])
    back = {a: tmp_path / "returned" / names[a] for a in AO.AUDITORS}
    for auditor, path in back.items():
        fill(out / names[auditor], path, key, set())
    text = back["A1"].read_text().replace("# session_start: ", "# session_start: 09:00")
    back["A1"].write_text(text.replace("# session_end: ", "# session_end: 09:08"))
    args = ["score", "--half", "train", "--dir", str(out), "--key", str(key_path)]
    assert AO.main([*args, "--a1", str(back["A1"]), "--a2", str(back["A2"])]) == 0
    printed = capsys.readouterr().out
    assert (
        "A1: minutes worked 8 (2.0 per item)" in printed
        and "A2: minutes worked not given" in printed
    )
    first = (out / names["score"]).read_bytes()
    assert json.loads(first)["minutes"]["A1"] == {"minutes": 8, "items": 4, "minutes_per_item": 2.0}
    again = tmp_path / "returned" / "recheck_A1.csv"
    fill(out / names["A1"], again, key, {own})
    args += ["--a1", str(again), "--a2", str(back["A2"]), "--label", "recheck"]
    assert AO.main(args) == 3
    assert (out / "outcome_train_adjudication_recheck.csv").is_file()
    assert not (out / names["adjudication"]).exists()
    second = json.loads((out / "outcome_train_score_recheck.json").read_text())
    assert second["auditor_flagged"]["A1"]["error_B"] == 1 and second["adjudicated"] is False
    assert (out / names["score"]).read_bytes() == first
    assert AO.labelled("a.b.csv", "x") == "a.b_x.csv" and AO.labelled("a.csv", "") == "a.csv"
