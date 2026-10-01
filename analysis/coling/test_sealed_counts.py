"""Tests for the counts-only script over the sealed outcomes (``sealed_counts.py``).

No test reads the study's sealed folder. Everything runs on one synthetic corpus: capture files
written to a temporary folder (one on the first day of each month from March 2022 to September
2026, and a last one on 2026-09-26), built by ``corpus.build_corpus``; its test-period outcome
rows are written, as the corpus builder writes them, to a file in that temporary folder, which
stands in for the sealed file.

The statements are laid out so that every expected count follows from the design, without
running the code under test. A statement dated in month M-2 gives month M as its estimate and is
first seen on the first day of M-1. With ``k`` the number of months after M at whose first day
the presentation reads Available:

* ``k = 0``: recovered by the stated end and by the stated end plus 90 days; scoreable;
* ``k = 1``: the bracket straddles the stated end; the first horizon event is undetermined;
* ``k = 2``: not recovered by the stated end, recovered by the stated end plus 90; scoreable;
* ``k = 4``: the bracket straddles the stated end plus 90; undetermined;
* ``k = 5``: recovered after both horizons; scoreable;
* never: censored at the last capture, after both horizons; scoreable, and not observable.

Every recovery lies between two captures a month apart, so it is observable (31 days or less).
(January is never the stated month: in a year that is not a leap year its end plus 90 days is the
first of May, a capture day.)

Covered: each count before masking (the eligible list, the six slices with a statement on each
cutoff day and on the day after, the two observable counts); the record and the printout of a
run; the hashes; the refusals (a wrong, missing or empty hash, with the sealed file left
unparsed; an unknown flag, a cutoff among them; a list or a sealed file from another build; an
open input in a sealed folder; a stop inside the rules, with its message and any warning
withheld); the one output file (required, never overwritten, no folder created, nothing else
written); the mask, its bounds and the nested slices, with an exhaustive check on small tables
that no count below the mask can be worked out from what is printed; the checks before printing,
and that a run goes through them; an output with no date-like string, no decimal number, no
outcome value, no id and no row; the Late split dropped; the same counts as ``dataset.py`` gives
on a train-like file; the cutoff table against MODELS.md; identical bytes on a second run.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_sealed_counts.py -q -p no:cacheprovider
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import re
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from analysis.coling import corpus as C
from analysis.coling import dataset as D
from analysis.coling import sealed_counts as S

HEADER = (
    "Generic Name,Company Name, Contact Info, Presentation, Type of Update,Date of Update, "
    "Availability Information, Related Information, Resolved Note, Reason for Shortage, "
    "Therapeutic Category, Status, Change Date, Date Discontinued, Initial Posting Date"
)
COMPANY = "Acme Pharma"
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
LAST = date(2026, 9, 26)
MODELS_MD = Path(__file__).resolve().parent / "plan" / "MODELS.md"
OBSERVABLE = "--gate-observable"
SEALED_DEFAULT = S.SEALED


@pytest.fixture(autouse=True)
def no_sealed_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No test can reach the study's sealed folder: for the length of a test, the default path
    of the script is a file of the test's own folder that does not exist."""
    monkeypatch.setattr(S, "SEALED", tmp_path / "no_default" / "outcomes_test.csv.gz")


def month_start(month: str, shift: int = 0) -> date:
    """The first day of ``month`` (YYYY-MM), ``shift`` months later."""
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + number - 1 + shift
    return date(index // 12, index % 12 + 1, 1)


CAPTURE_DAYS = (*(month_start("2022-03", i) for i in range(55)), LAST)


@dataclass(frozen=True)
class Line:
    """One presentation: its statement, and the capture from which it reads Available."""

    label: str
    generic: str
    day: str
    text: str
    back: date | None = None
    available_at_first: bool = False
    k: int | None = None
    listed: bool = False  # on the E3 eligible list, by design


def estimate(label: str, generic: str, day: str, month: str, k: int | None) -> Line:
    """An eligible statement by design: dated ``day``, estimate ``month``, back ``k`` months on."""
    year, number = month.split("-")
    text = f"Estimated recovery: {MONTHS[int(number) - 1]} {year}"
    back = None if k is None else month_start(month, k)
    return Line(label, generic, day, text, back, k=k, listed=True)


ONE, TWO, THREE, FOUR = "Drug One", "Drug Two", "Drug Three", "Drug Four"
FIVE, SIX, SEVEN = "Drug Five", "Drug Six", "Drug Seven"
ELIGIBLE_LINES = (
    # dated up to 2023-10-31: in no slice
    estimate("a1", ONE, "2023-02-15", "2023-04", 0),
    estimate("a2", ONE, "2023-03-15", "2023-05", 1),
    estimate("a3", TWO, "2023-04-15", "2023-06", 2),
    estimate("a4", TWO, "2023-05-15", "2023-07", None),
    estimate("a5", TWO, "2023-06-15", "2023-08", 4),
    estimate("a6", ONE, "2023-10-31", "2023-12", 0),  # on a cutoff day: not after it
    estimate("a7", ONE, "2023-07-15", "2023-09", 1),
    estimate("a8", TWO, "2023-08-15", "2023-10", 4),
    estimate("a9", ONE, "2023-09-15", "2023-11", 1),
    estimate("a10", TWO, "2023-09-20", "2023-11", None),
    # 2023-11-01 to 2023-12-31
    estimate("b0", ONE, "2023-11-01", "2023-12", 0),  # the day after a cutoff day
    estimate("b1", ONE, "2023-11-15", "2024-02", 0),
    estimate("b2", THREE, "2023-12-31", "2024-03", 0),  # on a cutoff day
    # 2024-01-01 to 2024-06-30
    estimate("c1", THREE, "2024-01-01", "2024-03", 2),  # the day after
    estimate("c2", THREE, "2024-02-15", "2024-04", 4),
    estimate("c3", FOUR, "2024-03-15", "2024-05", 5),
    estimate("c4", FOUR, "2024-04-15", "2024-06", None),
    estimate("c5", FOUR, "2024-06-30", "2024-08", 0),  # on a cutoff day
    estimate("c6", FOUR, "2024-05-15", "2024-07", 1),
    estimate("c7", FOUR, "2024-05-20", "2024-07", 4),
    estimate("h1", SEVEN, "2024-03-15", "2024-05", 1),  # the only statement of its episode
    # 2024-07-01 to 2024-08-31
    estimate("d1", FIVE, "2024-07-15", "2024-09", 0),
    estimate("d2", FIVE, "2024-08-15", "2024-10", 1),
    estimate("d3", FIVE, "2024-08-31", "2024-11", 2),  # on a cutoff day
    # 2024-09-01 to 2024-09-30
    estimate("e1", FIVE, "2024-09-15", "2024-11", 0),
    estimate("e2", SIX, "2024-09-30", "2024-12", 0),  # on a cutoff day
    # 2024-10-01 to 2024-12-31
    estimate("f1", SIX, "2024-10-15", "2024-12", 2),
    estimate("f2", SIX, "2024-11-15", "2025-02", 0),
    estimate("f3", SIX, "2024-12-31", "2025-03", 5),  # on a cutoff day
    # one statement, two presentations: one undetermined and observable, one never back
    estimate("pair_a", THREE, "2024-10-20", "2024-12", 1),
    estimate("pair_b", THREE, "2024-10-20", "2024-12", None),
    # 2025
    estimate("g1", ONE, "2025-01-01", "2025-03", 0),  # the day after
    estimate("g2", ONE, "2025-02-15", "2025-04", 1),
    estimate("g3", TWO, "2025-03-15", "2025-05", None),
    estimate("g4", TWO, "2025-04-15", "2025-06", 2),
    estimate("g5", FOUR, "2025-06-15", "2025-08", 0),
    estimate("g6", FOUR, "2025-07-15", "2025-09", 0),
    estimate("g7", ONE, "2025-05-15", "2025-07", 1),
    estimate("g8", TWO, "2025-07-20", "2025-09", 4),
    estimate("g9", FOUR, "2025-08-15", "2025-10", 1),
    estimate("g10", TWO, "2025-09-15", "2025-11", 4),
    estimate("g11", ONE, "2025-10-15", "2025-12", None),
)
OTHER_LINES = (
    # at risk, with a date-like phrase, and not eligible
    Line("n1", TWO, "2025-12-15", "Estimated recovery: August 2026", date(2026, 2, 1)),
    Line("n2", THREE, "2024-02-20", "Estimated recovery: June 2024", available_at_first=True),
    Line("n5", SIX, "2024-05-15", "Estimated recovery: March 2024", date(2024, 7, 1)),  # stale
    Line("n6", ONE, "2023-06-15", "Estimated recovery: March 2023", date(2023, 8, 1)),  # stale
    # no date-like phrase; the Late split
    Line("n3", FOUR, "2024-03-15", "Estimated recovery: TBD", date(2024, 5, 1)),
    Line("n4", FIVE, "2026-01-15", "Estimated recovery: March 2026", date(2026, 3, 1)),
)
TRAIN_A, TRAIN_B = "Drug Eight", "Drug Nine"
TRAIN_LINES = (
    estimate("t1", TRAIN_A, "2022-10-15", "2022-12", 0),
    estimate("t2", TRAIN_A, "2022-10-20", "2022-11", None),  # censored before the second horizon
    Line("t3", TRAIN_A, "2022-10-25", "Estimated recovery: TBD"),
    estimate("t4", TRAIN_B, "2022-02-15", "2022-04", 0),
    estimate("t5", TRAIN_B, "2022-03-15", "2022-05", 1),
    estimate("t6", TRAIN_B, "2022-04-15", "2022-06", 2),
    estimate("t7", TRAIN_B, "2022-05-15", "2022-07", 4),
    estimate("t8", TRAIN_B, "2022-06-15", "2022-08", None),  # censored after both horizons
)
LINES = (*ELIGIBLE_LINES, *OTHER_LINES, *TRAIN_LINES)
SCOREABLE_K = (0, 2, 5, None)
SINGLE = tuple(x for x in ELIGIBLE_LINES if not x.label.startswith("pair"))
PAIR_DAY = "2024-10-20"
SLICE_DAYS = {
    "llama-3.3-70b": "2023-12-31",
    "deepseek-v3": "2024-12-31",
    "qwen-2.5-7b": "2024-09-30",
    "gemma-3-27b": "2024-08-31",
    "gpt-oss-20b": "2024-06-30",
    "gpt-4o-mini": "2023-10-31",
}


def presentation(index: int) -> str:
    return f"{index + 1} mg vial (NDC 12345-{100 + index}-90)"


def capture_rows(day: date) -> list[list[str]]:
    """The listing on one capture day: every presentation whose statement is dated by then."""
    rows = []
    for index, line in enumerate(LINES):
        stated = date.fromisoformat(line.day)
        if stated > day:
            continue
        back = line.available_at_first or (line.back is not None and day >= line.back)
        rows.append(
            [
                line.generic,
                COMPANY,
                "800-000-0000",
                presentation(index),
                "Revised",
                stated.strftime("%m/%d/%Y"),
                "Available" if back else "Unavailable",
                line.text,
                "",
                "Demand increase for the drug",
                "Anesthesia",
                "Current",
                "",
                "",
                "01/05/2021",
            ]
        )
    return rows


def write_captures(directory: Path) -> list[dict[str, str]]:
    """Write the capture files and return the rows of their manifest."""
    manifest = []
    for day in CAPTURE_DAYS:
        buffer = io.StringIO()
        csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerows(
            capture_rows(day)
        )
        data = ("\r\n" + HEADER + "\r\n" + buffer.getvalue()).encode("utf-8")
        stamp = day.strftime("%Y%m%d") + "000000"
        (directory / f"{stamp}.csv").write_bytes(data)
        manifest.append(
            {
                "file": f"{stamp}.csv",
                "timestamp": stamp,
                "bytes": str(len(data)),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return manifest


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """The synthetic corpus and its files: open tables, manifest, eligible list, and the
    test-period outcomes in a temporary folder of their own."""
    root = tmp_path_factory.mktemp("synthetic")
    captures, out, vault = root / "captures", root / "out", root / "sealed"
    for folder in (captures, out, vault):
        folder.mkdir()
    manifest = out / "capture_manifest.csv"
    pd.DataFrame(write_captures(captures)).to_csv(manifest, index=False, lineterminator="\n")
    corpus = C.build_corpus(captures)
    events, sealed, eligible = out / "events.csv.gz", vault / "outcomes_test.csv.gz", out / "e3.csv"
    C.write_gz(corpus.events, events)
    C.write_gz(corpus.outcomes[corpus.outcomes["period"] == "test"], sealed)
    table = D.statement_table(D.read_table(events), LAST)
    eligible.write_text(D.csv_text(D.eligible_frame(table)), encoding="utf-8")
    by_presentation = corpus.events.set_index("presentation")
    event_of = {
        line.label: by_presentation.at[presentation(index), "event_id"]
        for index, line in enumerate(LINES)
    }
    shown = set(table["event_id"])
    return SimpleNamespace(
        root=root,
        corpus=corpus,
        table=table,
        events=events,
        sealed=sealed,
        eligible=eligible,
        manifest=manifest,
        sealed_sha=file_sha(sealed),
        eligible_sha=file_sha(eligible),
        event_of=event_of,
        # 1 when the statement with two presentations shows the one that never comes back
        b=int(event_of["pair_b"] in shown),
    )


def arguments(built: SimpleNamespace, out: Path | None, **replace: Any) -> list[str]:
    values = {
        "--sealed": built.sealed,
        "--events": built.events,
        "--eligible": built.eligible,
        "--manifest": built.manifest,
        "--out": out,
        "--expect-sha256": built.sealed_sha,
        "--expect-eligible-sha256": built.eligible_sha,
    }
    values.update({"--" + key.replace("_", "-"): value for key, value in replace.items()})
    return [
        str(part) for key, value in values.items() if value is not None for part in (key, value)
    ]


def fresh(tmp_path: Path, folder: str = "counts") -> Path:
    """A counts file that does not exist yet, in a folder of this test that does."""
    (tmp_path / folder).mkdir(exist_ok=True)
    taken = len(list((tmp_path / folder).iterdir()))
    return tmp_path / folder / f"sealed_counts_{taken}.json"


def run(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    **replace: Any,
) -> tuple[str, dict[str, Any]]:
    """Run the script on the synthetic files; the printout and the record it wrote."""
    out = fresh(tmp_path)
    assert S.main([*arguments(built, out, **replace), *extra]) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    assert printed.out.splitlines()[-1] == f"wrote {out.as_posix()}"
    return printed.out, json.loads(out.read_text(encoding="utf-8"))


def refused(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    **replace: Any,
) -> str:
    """The reason of a refusal: status 1, nothing on the screen, no file written."""
    out = fresh(tmp_path, "refused")
    with pytest.raises(SystemExit) as stop:
        S.main([*arguments(built, out, **replace), *extra])
    assert isinstance(stop.value.code, str) and stop.value.code.startswith("refused: ")
    # no other error, whose message may quote a cell, travels with the refusal
    assert stop.value.__cause__ is None
    assert stop.value.__context__ is None or stop.value.__suppress_context__
    assert isinstance(stop.value.__context__, argparse.ArgumentError | None)
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == ""
    assert list(out.parent.iterdir()) == []
    return stop.value.code


# --------------------------------------------------------------------------------------------
# The design holds: the expected counts, from the layout alone
# --------------------------------------------------------------------------------------------


def eligible_after(day: str) -> int:
    return sum(x.day > day for x in SINGLE) + (day < PAIR_DAY)


def scoreable_after(day: str, b: int) -> int:
    single = sum(x.k in SCOREABLE_K for x in SINGLE if x.day > day)
    return single + (b if day < PAIR_DAY else 0)


def observable_after(day: str, b: int) -> int:
    single = sum(x.k is not None for x in SINGLE if x.day > day)
    return single + ((1 - b) if day < PAIR_DAY else 0)


def test_the_layout_gives_the_numbers_the_tests_assert(built: SimpleNamespace) -> None:
    assert len(SINGLE) == 40 and sum(x.k in SCOREABLE_K for x in SINGLE) == 25
    assert sum(x.k is not None for x in SINGLE) == 35
    days = list(SLICE_DAYS.values())
    assert [eligible_after(day) for day in days] == [28, 11, 15, 17, 20, 31]
    assert [scoreable_after(day, 0) for day in days] == [17, 6, 9, 11, 13, 20]
    assert observable_after("2023-12-31", 0) == 25
    # the builder agrees on which statements are eligible: the 40 and the pair, in 7 episodes
    listed = built.table[D.true(built.table["e3_eligible"])]
    assert len(listed) == 41 and D.episodes(listed) == 7
    wanted = {built.event_of[x.label] for x in SINGLE}
    assert wanted <= set(listed["event_id"])
    assert set(listed["event_id"]) - wanted <= {built.event_of["pair_a"], built.event_of["pair_b"]}
    assert set(D.read_table(built.eligible)["statement_group_id"]) == set(
        listed["statement_group_id"]
    )
    assert built.b in (0, 1)
    in_table = {m: d.isoformat() for m, d in S.CUTOFF_MONTH_ENDS.items() if S.has_slice(d)}
    assert in_table == SLICE_DAYS


# --------------------------------------------------------------------------------------------
# The counts before masking
# --------------------------------------------------------------------------------------------


def raw_of(built: SimpleNamespace, with_observable: bool = False) -> dict[str, Any]:
    """The counts before masking, through the functions a run calls on the synthetic files."""
    listed = S.listed_statements(built.table, D.read_table(built.eligible))
    rows = S._checked_rows(D.read_table(built.sealed), D.read_table(built.events))
    return S._sealed_counts(listed, rows, S.CUTOFF_MONTH_ENDS, with_observable)


def test_counts_before_masking_follow_the_layout(built: SimpleNamespace) -> None:
    b = built.b
    raw = raw_of(built, with_observable=True)
    assert raw["e3"] == {
        "statements": 41,
        "episodes": 7,
        "scoreable": 25 + b,
        "scoreable_episodes": 6,  # the seventh episode holds one undetermined statement
        "with_a_horizon_event_undetermined": 16 - b,
    }
    # a statement dated on the last day of a cutoff month is in no count of that model: each of
    # a6, b2, c5, d3, e2 and f3 is scoreable and would add one
    assert list(raw["slices"]) == list(SLICE_DAYS)
    for model, day in SLICE_DAYS.items():
        counts = raw["slices"][model]
        assert counts["statements"] == eligible_after(day), model
        assert counts["scoreable"] == scoreable_after(day, b), model
        assert counts["with_a_horizon_event_undetermined"] == (
            eligible_after(day) - scoreable_after(day, b)
        )
    assert raw["slices"]["deepseek-v3"]["scoreable"] == 6
    assert raw["slices"]["gpt-4o-mini"]["scoreable"] == 20 + b
    # the bracket of the displayed presentation: the statement with two presentations is
    # observable when it shows the one that comes back
    assert raw["observable"] == {
        "all": (41, 35 + (1 - b)),
        "after_cutoff": (28, 25 - b),
    }
    assert "observable" not in raw_of(built)


# --------------------------------------------------------------------------------------------
# A run: the record and the printout
# --------------------------------------------------------------------------------------------


def test_counts_on_the_eligible_list(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, record = run(built, tmp_path, capsys)
    b = built.b
    assert record["e3_eligible_test"] == {
        "eligible_statements": 41,
        "eligible_episodes": 7,
        "scoreable_statements": 25 + b,
        # six of seven episodes hold a scoreable statement: a total under ten is not split
        "scoreable_episodes": "withheld",
        "undetermined_statements": 16 - b,
    }
    lines = printed.splitlines()
    assert "  eligible statements: 41" in lines
    assert "  shortage episodes among the eligible: 7" in lines
    assert f"  scoreable statements: {25 + b}" in lines
    assert "  shortage episodes among the scoreable: withheld" in lines
    assert f"  statements with a horizon event undetermined: {16 - b}" in lines
    assert list(record) == list(S.TOP_KEYS)
    assert record["command"] == S.COMMAND and "--out" in S.COMMAND


def test_slices_exact_for_the_primaries_and_bounds_for_the_others(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, record = run(built, tmp_path, capsys)
    b = built.b
    slices = record["post_cutoff_slices"]
    # The primaries: between the list, the two slices and nothing, every difference is five or
    # more on both sides (8 and 5 before 2024; 11 + b and 6 - b in 2024; 6 and 5 from 2025).
    # The secondaries: the three statements between gpt-4o-mini's cutoff and llama-3.3-70b's
    # are fewer than five, so no secondary slice is exact. Each is the bound the exact counts
    # imply: at least the scoreable of the slice inside it, and at least its size less the
    # undetermined of the slice around it.
    assert slices["scoreable_statements"] == {
        "llama-3.3-70b": 17 + b,
        "deepseek-v3": 6,
        "qwen-2.5-7b": ">5",  # holds the deepseek-v3 slice: 6 or more
        "gemma-3-27b": f">{5 + b}",  # 17 statements, 11 - b undetermined after 2023
        "gpt-oss-20b": f">{8 + b}",  # 20 statements, 11 - b undetermined after 2023
        "gpt-4o-mini": f">{16 + b}",  # holds the llama-3.3-70b slice: 17 + b or more
    }
    assert slices["models_without_a_slice"] == ["gemini-3.8-flash", "grok-4.20"]
    lines = printed.splitlines()
    assert f"  llama-3.3-70b: {17 + b}" in lines and "  deepseek-v3: 6" in lines
    assert f"  gpt-4o-mini: >{16 + b}" in lines and "  qwen-2.5-7b: >5" in lines
    assert "without a slice inside the test split: gemini-3.8-flash, grok-4.20" in lines
    # every bound is true of the count behind it, and none is the count itself
    raw = raw_of(built)["slices"]
    for model, value in slices["scoreable_statements"].items():
        if isinstance(value, str):
            assert raw[model]["scoreable"] > int(value[1:]), model
    assert S.OPTIONAL_KEY not in record and "Gate 1" not in printed and "observable" not in printed


def test_observable_counts_only_when_asked(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    b = built.b
    printed, record = run(built, tmp_path, capsys, OBSERVABLE)
    # 5 + b eligible statements are not observable, 3 + b of them after the cutoff: the count
    # on the list is exact, the one after the cutoff is the bound it implies (28 less 5 + b)
    assert record[S.OPTIONAL_KEY] == {
        "model": "llama-3.3-70b",
        "observable_statements": 36 - b,
        "observable_statements_after_cutoff": f">{22 - b}",
    }
    lines = printed.splitlines()
    assert f"  second threshold, all eligible statements: {36 - b}" in lines
    assert f"  fourth threshold, dated after the cutoff month of llama-3.3-70b: >{22 - b}" in lines
    assert record["command"] == f"{S.COMMAND} {OBSERVABLE}"
    plain = run(built, tmp_path, capsys)[1]
    assert {k: v for k, v in record.items() if k not in (S.OPTIONAL_KEY, "command")} == {
        k: v for k, v in plain.items() if k != "command"
    }


def test_observable_counts_are_not_computed_unless_asked(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    computed: list[list[str]] = []
    count = S._sealed_counts

    def watched(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raw = count(*args, **kwargs)
        computed.append(sorted(raw))
        return raw

    monkeypatch.setattr(S, "_sealed_counts", watched)
    run(built, tmp_path, capsys)
    run(built, tmp_path, capsys, OBSERVABLE)
    assert computed == [["e3", "slices"], ["e3", "observable", "slices"]]


def test_hashes_of_the_files_read(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, record = run(built, tmp_path, capsys)
    inputs = record["inputs"]
    assert inputs["sealed_outcomes"] == {"file": "outcomes_test.csv.gz", "sha256": built.sealed_sha}
    assert inputs["eligible_list"] == {"file": "e3.csv", "sha256": built.eligible_sha}
    assert inputs["events"] == {"file": "events.csv.gz", "sha256": file_sha(built.events)}
    assert inputs["capture_manifest"]["sha256"] == file_sha(built.manifest)
    assert inputs["code_sha256"]["sealed_counts.py"] == file_sha(Path(S.__file__))
    assert inputs["code_sha256"]["dataset.py"] == file_sha(Path(D.__file__))
    assert inputs["code_sha256"]["corpus.py"] == file_sha(Path(C.__file__))
    assert list(inputs["code_sha256"]) == [
        "sealed_counts.py",
        "dataset.py",
        "corpus.py",
        "forms.py",
        "rules.py",
    ]
    assert list(inputs) == [*S.FILE_INPUTS, "code_sha256"]
    assert S.FILE_INPUTS == ("sealed_outcomes", "eligible_list", "events", "capture_manifest")
    assert f"sha256 of the sealed outcome file: {built.sealed_sha}" in printed.splitlines()
    assert f"sha256 of the eligible list: {built.eligible_sha}" in printed.splitlines()


# --------------------------------------------------------------------------------------------
# The one output file
# --------------------------------------------------------------------------------------------


def tree(folder: Path) -> set[str]:
    return {path.relative_to(folder).as_posix() for path in folder.rglob("*")}


def test_two_runs_write_the_same_bytes_and_only_the_file_asked_for(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second = fresh(tmp_path), tmp_path / "counts" / "again.json"
    default = D.OUT / "sealed_counts.json"
    there = default.exists()
    before = tree(built.root) | tree(tmp_path)
    assert S.main(arguments(built, first)) == 0
    first_print = capsys.readouterr().out
    assert tree(built.root) | tree(tmp_path) == before | {"counts/sealed_counts_0.json"}
    assert S.main(arguments(built, second)) == 0
    second_print = capsys.readouterr().out
    assert second.read_bytes() == first.read_bytes() and first.read_bytes().endswith(b"\n")
    assert first_print.splitlines()[:-1] == second_print.splitlines()[:-1]
    assert first_print.splitlines()[-1] == f"wrote {first.as_posix()}"
    assert default.exists() == there  # nothing goes to the builders' folder unless asked


def test_the_counts_file_is_required_and_never_overwritten(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nowhere = tmp_path / "no_such_folder" / "outcomes_test.csv.gz"
    # no default: without --out nothing is read (the sealed path here does not exist)
    with pytest.raises(SystemExit) as stop:
        S.main(arguments(built, None, sealed=nowhere))
    assert "--out is required" in str(stop.value.code)
    # an existing file is left as it is, and the sealed file is not opened
    out = fresh(tmp_path)
    out.write_text("kept", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        S.main(arguments(built, out, sealed=nowhere))
    assert "already there" in str(stop.value.code) and out.read_text(encoding="utf-8") == "kept"
    # a second run on the file of the first is refused
    out = fresh(tmp_path)
    assert S.main(arguments(built, out)) == 0
    written = out.read_bytes()
    with pytest.raises(SystemExit) as stop:
        S.main([*arguments(built, out), OBSERVABLE])
    assert "runs once" in str(stop.value.code) and out.read_bytes() == written
    # no folder is created
    deep = tmp_path / "not" / "there" / "counts.json"
    with pytest.raises(SystemExit) as stop:
        S.main(arguments(built, deep, sealed=nowhere))
    assert "does not exist" in str(stop.value.code) and not (tmp_path / "not").exists()
    # and nothing is written into a sealed folder
    inside = built.sealed.parent / "counts.json"
    with pytest.raises(SystemExit) as stop:
        S.main(arguments(built, inside, sealed=nowhere))
    assert "sealed folder" in str(stop.value.code) and not inside.exists()
    assert capsys.readouterr().out.count("wrote ") == 1


def test_a_counts_file_that_appears_during_the_run_is_left_alone(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def appears(path: Path) -> Path:
        path.write_text("kept", encoding="utf-8")  # after the check, before the write
        return path

    monkeypatch.setattr(S, "output_path", appears)
    out = fresh(tmp_path)
    with pytest.raises(SystemExit) as stop:
        S.main(arguments(built, out))
    assert "the counts file cannot be written (FileExistsError)" in str(stop.value.code)
    assert stop.value.__context__ is None
    assert out.read_text(encoding="utf-8") == "kept" and capsys.readouterr().out == ""


# --------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------


def test_a_wrong_or_missing_hash_is_refused_and_the_file_is_not_parsed(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed: list[bytes] = []
    parse = S._table_of

    def watched(data: bytes, gzipped: bool) -> pd.DataFrame:
        parsed.append(data)
        return parse(data, gzipped)

    monkeypatch.setattr(S, "_table_of", watched)
    sealed_bytes = built.sealed.read_bytes()
    reason = refused(built, tmp_path, capsys, expect_sha256="0" * 64)
    assert "the sealed file is not the expected file" in reason
    # a file that is not a table at all gets the same refusal: it is hashed, never parsed
    junk = tmp_path / "outcomes_test.csv.gz"
    junk.write_bytes(b"not a gzip file, 2024-12-25")
    reason = refused(built, tmp_path, capsys, sealed=junk)
    assert "the sealed file is not the expected file" in reason and "2024-12-25" not in reason
    # one byte more than the frozen file
    longer = tmp_path / "longer.csv.gz"
    longer.write_bytes(sealed_bytes + b"\n")
    assert "not the expected file" in refused(built, tmp_path, capsys, sealed=longer)
    # no hash, an empty one, too short a prefix, or something that is not a hash
    assert "--expect-sha256" in refused(built, tmp_path, capsys, expect_sha256=None)
    assert "--expect-sha256" in refused(built, tmp_path, capsys, expect_sha256="")
    assert "--expect-sha256" in refused(built, tmp_path, capsys, "--expect-sha256=")
    assert "--expect-sha256" in refused(built, tmp_path, capsys, expect_sha256="   ")
    assert "--expect-sha256" in refused(
        built, tmp_path, capsys, expect_sha256=built.sealed_sha[:15]
    )
    assert "--expect-sha256" in refused(built, tmp_path, capsys, expect_sha256="z" * 64)
    assert "--expect-sha256" in refused(
        built, tmp_path, capsys, expect_sha256=built.sealed_sha + "0"
    )
    assert "--expect-eligible-sha256" in refused(
        built, tmp_path, capsys, expect_eligible_sha256=None
    )
    assert "--expect-eligible-sha256" in refused(built, tmp_path, capsys, expect_eligible_sha256="")
    # in none of these runs was a sealed file parsed
    assert parsed and sealed_bytes not in parsed and junk.read_bytes() not in parsed
    assert longer.read_bytes() not in parsed
    # the hash check does not rest on the argument check alone
    with pytest.raises(SystemExit):
        S.require_hash(sealed_bytes, "", "the sealed file")
    with pytest.raises(SystemExit):
        S.require_hash(sealed_bytes, built.sealed_sha[:8], "the sealed file")
    assert S.require_hash(sealed_bytes, built.sealed_sha[:16], "the sealed file") == (
        built.sealed_sha
    )
    # the first 16 characters are enough, as the registration records hashes
    _, record = run(
        built,
        tmp_path,
        capsys,
        expect_sha256=built.sealed_sha[:16].upper(),
        expect_eligible_sha256=built.eligible_sha[:16],
    )
    assert record["inputs"]["sealed_outcomes"]["sha256"] == built.sealed_sha
    assert sealed_bytes in parsed


def test_the_sealed_file_is_read_last_and_only_behind_its_hash(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    read = S.file_bytes

    def watched(path: Path, what: str) -> bytes:
        order.append(what)
        return read(path, what)

    monkeypatch.setattr(S, "file_bytes", watched)
    run(built, tmp_path, capsys)
    assert order[-1] == "the sealed file" and order.count("the sealed file") == 1
    assert order[0] == "the eligible list"
    order.clear()
    refused(built, tmp_path, capsys, expect_eligible_sha256="1" * 64)
    assert order == ["the eligible list"]
    # an open input may not come from a sealed folder, nor be the sealed file under another name
    order.clear()
    inside = built.sealed.parent / "events.csv.gz"
    for replace in ({"events": inside}, {"eligible": built.sealed}, {"manifest": inside}):
        reason = refused(built, tmp_path, capsys, **replace)
        assert "only --sealed names a sealed file" in reason
    elsewhere = tmp_path / "elsewhere.csv.gz"
    elsewhere.write_bytes(built.sealed.read_bytes())
    reason = refused(built, tmp_path, capsys, sealed=elsewhere, events=elsewhere)
    assert "only --sealed names a sealed file" in reason
    assert order == []


def test_the_sealed_file_is_not_opened_when_an_open_input_is_wrong(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nowhere = tmp_path / "no_such_folder" / "outcomes_test.csv.gz"
    reason = refused(built, tmp_path, capsys, sealed=nowhere, expect_eligible_sha256="1" * 64)
    assert "the eligible list is not the expected file" in reason
    # a list with a statement taken out, under its own hash: not the builder's list
    shorter = tmp_path / "eligible.csv"
    listed = D.read_table(built.eligible)
    shorter.write_text(D.csv_text(listed.iloc[1:]), encoding="utf-8")
    reason = refused(
        built,
        tmp_path,
        capsys,
        sealed=nowhere,
        eligible=shorter,
        expect_eligible_sha256=file_sha(shorter),
    )
    assert "not the one the dataset builder gives" in reason
    # a file that is not there, and a file name that would put a date into the record
    gone = tmp_path / "eligible_e3.csv"
    assert "cannot be read" in refused(built, tmp_path, capsys, sealed=nowhere, eligible=gone)
    dated = tmp_path / "events_2026-10-02.csv.gz"
    dated.write_bytes(built.events.read_bytes())
    reason = refused(built, tmp_path, capsys, sealed=nowhere, events=dated)
    assert "would hold a date" in reason
    # an open input that is not a table of the builders: the reason names no cell
    broken = tmp_path / "events.csv.gz"
    C.write_gz(D.read_table(built.events).drop(columns=["listing"]), broken)
    reason = refused(built, tmp_path, capsys, sealed=nowhere, events=broken)
    assert "the open inputs are not as the builders write them (ValueError)" in reason
    # with the open inputs in order, the sealed file is the next thing read
    assert "the sealed file cannot be read" in refused(built, tmp_path, capsys, sealed=nowhere)
    # a list with another stated end
    moved = tmp_path / "moved.csv"
    moved.write_text(D.csv_text(listed.assign(stated_end="2024-06-30")), encoding="utf-8")
    reason = refused(
        built,
        tmp_path,
        capsys,
        sealed=nowhere,
        eligible=moved,
        expect_eligible_sha256=file_sha(moved),
    )
    assert "not the one the dataset builder gives" in reason


@pytest.mark.parametrize(
    "extra",
    [
        ("--by-form",),
        ("--by", "year"),
        ("--breakdown", "company"),
        ("--group-by=model",),
        ("--rates",),
        ("form",),
        ("--expect",),  # no abbreviation either
        ("--gate",),
        ("--cutoff", "deepseek-v3=2024-11-15"),  # a cutoff is not an argument
        ("--cutoff=grok-4.20=2022-12-31",),
        ("--mask-below", "1"),
        ("--eligible-observable",),
    ],
)
def test_an_unknown_flag_is_refused(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: tuple
) -> None:
    reason = refused(built, tmp_path, capsys, *extra)
    assert "unknown argument" in reason and "takes no breakdown and no cutoff" in reason


def test_the_only_options_are_the_files_the_hashes_and_one_flag() -> None:
    """A second run can change nothing but the files read and the two observable counts: no
    option moves a cutoff, the mask or the set counted."""
    args = S.arguments(["--out", "x.json"])
    assert sorted(vars(args)) == [
        "eligible",
        "events",
        "expect_eligible_sha256",
        "expect_sha256",
        "gate_observable",
        "manifest",
        "out",
        "sealed",
    ]
    assert args.gate_observable is False and args.expect_sha256 is None
    assert not hasattr(S, "cutoff_table")
    # the defaults are the builders' files and the registered sealed file (compared as text)
    assert SEALED_DEFAULT.as_posix() == "external_data/sealed/outcomes_test.csv.gz"
    assert S.SEALED_FOLDER == "sealed" and args.sealed != SEALED_DEFAULT
    assert (args.events, args.eligible, args.manifest) == (D.EVENTS, D.ELIGIBLE, D.MANIFEST)


def test_a_sealed_file_of_another_build_is_refused(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = D.read_table(built.sealed)

    def other(frame: pd.DataFrame) -> dict[str, Any]:
        path = tmp_path / "outcomes_test.csv.gz"
        return {"sealed": path, "expect_sha256": C.write_gz(frame, path)}

    listed = set(D.read_table(built.eligible)["event_id"])
    without = rows[rows["event_id"] != sorted(listed)[0]]
    assert "not from the same build" in refused(built, tmp_path, capsys, **other(without))
    renamed = rows.assign(event_id=["E" + i[1:][::-1] for i in rows["event_id"]])
    assert "not from the same build" in refused(built, tmp_path, capsys, **other(renamed))
    train = rows.assign(period="train")
    assert "not the table of test-period outcomes" in refused(
        built, tmp_path, capsys, **other(train)
    )
    fewer = rows.drop(columns=["observable31_B"])
    assert "lacks ['observable31_B']" in refused(built, tmp_path, capsys, **other(fewer))
    # the right events under another statement: the display rows are not those of the list
    swapped = rows.assign(statement_group_id=rows["statement_group_id"].iloc[::-1].to_numpy())
    reason = refused(built, tmp_path, capsys, **other(swapped))
    assert "have no outcome row of their display row" in reason


def test_a_stop_inside_the_rules_withholds_its_message(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stop(*args: Any, **kwargs: Any) -> None:
        raise ValueError("S123: recovered by A and not by B, upper bound 2024-12-25")

    with monkeypatch.context() as patch:
        patch.setattr(D, "attach_outcomes", stop)
        reason = refused(built, tmp_path, capsys)
    assert "ValueError" in reason and "withheld" in reason
    assert "S123" not in reason and "2024-12-25" not in reason and "recovered" not in reason
    # a cell that is not a flag stops the run in the same way, and is not quoted
    rows = D.read_table(built.sealed)
    rows.loc[0, "observable31_B"] = "2024-12-25"
    path = tmp_path / "outcomes_test.csv.gz"
    sha = C.write_gz(rows, path)
    reason = refused(built, tmp_path, capsys, OBSERVABLE, sealed=path, expect_sha256=sha)
    assert "withheld" in reason and "2024-12-25" not in reason
    # a file with the expected hash that is not a gzip table
    path.write_bytes(b"recovered,2024-12-25\n")
    reason = refused(built, tmp_path, capsys, sealed=path, expect_sha256=file_sha(path))
    assert "withheld" in reason and "2024-12-25" not in reason and "recovered" not in reason
    # a stop while the record is put together
    with monkeypatch.context() as patch:
        patch.setattr(S, "shown_nested", stop)
        reason = refused(built, tmp_path, capsys)
    assert "ValueError" in reason and "S123" not in reason and "2024-12-25" not in reason


def test_a_warning_over_the_sealed_rows_is_not_shown(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attach = D.attach_outcomes

    def noisy(*args: Any, **kwargs: Any) -> pd.DataFrame:
        warnings.warn("S123 recovered, upper bound 2024-12-25", UserWarning, stacklevel=1)
        return attach(*args, **kwargs)

    monkeypatch.setattr(D, "attach_outcomes", noisy)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        printed, _ = run(built, tmp_path, capsys)
    assert not [w for w in caught if "S123" in str(w.message)]
    assert "S123" not in printed


# --------------------------------------------------------------------------------------------
# Cutoffs
# --------------------------------------------------------------------------------------------


def test_slice_rule_and_cutoff_table() -> None:
    assert S.has_slice(date(2025, 11, 30)) and not S.has_slice(date(2025, 12, 31))
    assert not S.has_slice(date(2026, 3, 31)) and S.has_slice(date(2022, 6, 30))
    assert S.CUTOFF_MONTH_ENDS[S.GATE_MODEL] == C.CUTOFF.date()
    assert D.DEFINITION == "B" == C.GATE_PRIMARY
    assert all(C.cutoff_day(day).date() == day for day in S.CUTOFF_MONTH_ENDS.values())
    assert set(S.PRIMARY) <= set(S.CUTOFF_MONTH_ENDS) and S.GATE_MODEL in S.PRIMARY
    assert all(S.has_slice(S.CUTOFF_MONTH_ENDS[model]) for model in S.PRIMARY)


def test_cutoff_table_mirrors_models_md() -> None:
    text = MODELS_MD.read_text(encoding="utf-8")
    summary = text.split("## 1. Summary", 1)[1].split("\n\n", 2)[1]
    in_note, roles = {}, {}
    for line in summary.splitlines()[2:]:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        in_note[cells[0].split(" ")[0]] = date.fromisoformat(cells[4])
        roles[cells[0].split(" ")[0]] = cells[1]
    assert in_note == S.CUTOFF_MONTH_ENDS
    assert tuple(model for model, role in roles.items() if role == "primary") == S.PRIMARY
    assert set(roles.values()) == {"primary", "secondary"}
    # section 8 names the six slices and the day each starts after
    section = text.split("## 8. Consequences for PLAN.md", 1)[1].split("\n## ", 1)[0]
    named = dict(
        (model, date.fromisoformat(day))
        for day, model in re.findall(r"(\d{4}-\d{2}-\d{2})\s+\(([\w.-]+)\)", section)
    )
    assert named == {m: d for m, d in S.CUTOFF_MONTH_ENDS.items() if S.has_slice(d)}
    assert len(named) == 6


# --------------------------------------------------------------------------------------------
# Masking
# --------------------------------------------------------------------------------------------


def test_small_counts_are_masked() -> None:
    assert [S.shown(n) for n in (0, 1, 4, 5, 6, 250)] == ["<5", "<5", "<5", 5, 6, 250]
    assert S.MASK_BELOW == 5 and S.WITHHELD == "withheld"
    # a count and the rest of its total: a masked one cannot be had by subtraction, because the
    # other is printed as a bound
    assert S.shown_pair(30, 22) == (22, 8)
    assert S.shown_pair(30, 25) == (25, 5)
    assert S.shown_pair(30, 26) == (">25", "<5")
    assert S.shown_pair(30, 30) == (">25", "<5")
    assert S.shown_pair(30, 3) == ("<5", ">25")
    assert S.shown_pair(10, 5) == (5, 5) and S.shown_pair(10, 6) == (">5", "<5")
    # a total of five to nine: two masks would leave one or two values (4 and 4 for a total of
    # 8), and a mask beside a bound would give the side that is not small
    for total in range(5, 10):
        for part in range(total + 1):
            assert S.shown_pair(total, part) == ("withheld", "withheld")
    assert S.shown_pair(3, 2) == ("<5", "<5") and S.shown_pair(0, 0) == ("<5", "<5")
    assert all(S.is_count(v) for v in (5, 250, "<5", ">25", ">0", "withheld"))
    bad = (4, 0, True, 5.0, "5", "0.4", "2024-12-25", None, [5], "<4", "<50", ">", "<5 ", "held")
    assert not any(S.is_count(v) for v in bad)


def test_nested_sets_give_no_small_difference() -> None:
    whole, llama, deepseek = (2585, 2400), (1522, 1410), (591, 550)
    # each count is five or more away from the others on both sides: all exact
    assert S.shown_nested([[whole], [llama, deepseek]]) == [[2400], [1410, 550]]
    assert S.apart(whole, llama) and S.apart(llama, deepseek) and S.apart(deepseek, (0, 0))
    # 84 statements between two cutoffs, 3 of them undetermined: the second step is not exact
    gemma, qwen = (845, 780), (761, 699)
    assert not S.apart(gemma, qwen) and S.apart(gemma, llama) and S.apart(gemma, deepseek)
    printed = S.shown_nested([[whole], [llama, deepseek], [qwen, gemma]])
    assert printed == [[2400], [1410, 550], [">648", ">732"]]
    # qwen: 761 less the 112 undetermined of the llama slice; gemma: 845 less the same 112.
    # The bounds are what a reader of the exact counts could work out, and no more.
    assert S.implied(761, [(0, 0), whole, llama, deepseek], 2400) == ">648"
    # a first step that is not exact closes the later ones, whatever they hold
    near = (1522, 1519)
    assert S.shown_nested([[whole], [near, deepseek], [gemma]]) == [
        [2400],
        [">1336", ">405"],
        [">659"],
    ]
    # the whole list with fewer than five undetermined: a bound, and the slices its bounds
    assert S.shown_nested([[(2585, 2583)], [(1522, 1521)], [(591, 591)]]) == [
        [">2580"],
        [">1517"],
        [">586"],
    ]
    # the whole list with fewer than five scoreable
    assert S.shown_nested([[(40, 3)], [(20, 2)]]) == [["<5"], ["<5"]]
    # a slice of fewer than five statements says nothing that is not open
    assert S.shown_nested([[(40, 20)], [(3, 1)]]) == [[20], ["<5"]]
    assert S.shown_nested([[(40, 20)], [(0, 0)]]) == [[20], ["<5"]]
    # nothing useful implied: withheld
    assert S.shown_nested([[(40, 20)], [(12, 10)]]) == [[20], ["withheld"]]
    assert S.shown_nested([[(8, 4)], [(6, 3)]]) == [["withheld"], ["withheld"]]
    # two models with one cutoff have one slice
    assert S.shown_nested([[whole], [llama, llama]]) == [[2400], [1410, 1410]]


def chains(sizes: Sequence[int], length: int) -> Iterator[tuple[tuple[int, int], ...]]:
    """Every chain of ``length`` nested sets, the widest first, as ``(total, part)``: each set
    adds to the one inside it a band of one of ``sizes`` statements, any number of them in the
    part."""
    bands = [(size, part) for size in sizes for part in range(size + 1)]
    for chosen in itertools.product(bands, repeat=length):
        total = part = 0
        sets = []
        for size, inside in chosen:
            total, part = total + size, part + inside
            sets.append((total, part))
        yield tuple(reversed(sets))


def true_of(value: int | str, part: int) -> bool:
    """Whether a printed count is true of the count behind it."""
    if isinstance(value, int):
        return value == part
    if value.startswith("<"):
        return part < int(value[1:])
    return value == S.WITHHELD or part > int(value[1:])


def recoverable(sizes: Sequence[int], layout: Sequence[Sequence[int]]) -> list[Any]:
    """Counts below the mask that a reader could work out. For every chain of nested sets,
    printed in the steps of ``layout`` (positions in the chain, 0 the widest), the reader has the
    totals (open), what is printed, and this code. A difference between two sets (or between a
    set and nothing), inside the part or outside it, is recovered when it takes one value over
    all the chains that look the same to the reader, is below the mask, and is not fixed by the
    totals alone. The chains of one set of totals are all there, so the check is complete for
    the totals it covers."""
    length = 1 + max(position for step in layout for position in step)
    views: dict[Any, list[tuple[tuple[int, int], ...]]] = {}
    for sets in chains(sizes, length):
        steps = [[sets[position] for position in step] for step in layout]
        printed = S.shown_nested(steps)
        for step, values in zip(steps, printed, strict=True):
            assert all(true_of(v, part) for (_, part), v in zip(step, values, strict=True))
        rest = S.shown_pair(*sets[0])[1]
        assert true_of(rest, sets[0][0] - sets[0][1])
        view = (tuple(total for total, _ in sets), repr(printed), rest)
        views.setdefault(view, []).append(sets)
    found = []
    for view, alike in views.items():
        for i, j in itertools.combinations(range(length + 1), 2):
            total = (*view[0], 0)[i] - (*view[0], 0)[j]
            inside = {(*sets, (0, 0))[i][1] - (*sets, (0, 0))[j][1] for sets in alike}
            if total and len(inside) == 1:
                (part,) = inside
                if min(part, total - part) < S.MASK_BELOW:
                    found.append((view, i, j, part))
    return found


BANDS = {
    # sizes of the bands between two sets: none, too few to split, and just enough to print
    2: (0, 1, 2, 3, 4, 5),
    3: (0, 1, 2, 5, 6, 7),
    5: (0, 1, 4, 9, 10, 11),
}


@pytest.mark.parametrize(
    ("mask", "layout"),
    [
        (5, [[0], [1]]),  # the list and one slice, at the mask of the script
        (5, [[0], [1], [2]]),
        (5, [[0], [2], [1]]),  # the inner slice printed first
        (5, [[0], [1, 2]]),
        (3, [[0], [1], [2]]),  # a smaller mask reaches longer chains
        (3, [[0], [2], [1]]),
        (3, [[0], [1, 2]]),
        (2, [[0], [1, 3], [2]]),  # two primaries around a secondary
        (2, [[0], [2], [1, 3]]),  # a primary between two secondaries
        (2, [[0], [1, 2, 3]]),
        (2, [[0], [3], [2], [1]]),
    ],
)
def test_no_count_below_the_mask_can_be_worked_out(
    monkeypatch: pytest.MonkeyPatch, mask: int, layout: list[list[int]]
) -> None:
    monkeypatch.setattr(S, "MASK_BELOW", mask)
    assert recoverable(BANDS[mask], layout) == []


def test_the_exhaustive_check_sees_a_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check above is not empty: it prints exact counts at every level, and without the rule
    for nested sets, for a pair, or for a later step, it finds counts below the mask."""
    monkeypatch.setattr(S, "MASK_BELOW", 2)
    layout = [[0], [2], [1]]
    exact = set()
    for sets in chains(BANDS[2], 3):
        printed = S.shown_nested([[sets[position] for position in step] for step in layout])
        exact.add(tuple(isinstance(value, int) for (value,) in printed))
    yes, no = True, False
    assert exact >= {(no, no, no), (yes, no, no), (yes, yes, no), (yes, yes, yes)}
    assert recoverable(BANDS[2], layout) == []
    with monkeypatch.context() as patch:
        patch.setattr(S, "apart", lambda one, other: True)
        assert recoverable(BANDS[2], [[0], [1]])
    with monkeypatch.context() as patch:
        patch.setattr(S, "shown_pair", lambda total, part: (S.shown(part), S.shown(total - part)))
        assert recoverable(BANDS[2], [[0], [1]])
    # a mask on each side of a total of twice the mask less two leaves one value for both
    with monkeypatch.context() as patch:
        small = f"<{S.MASK_BELOW}"

        def two_masks(total: int, part: int) -> tuple[int | str, int | str]:
            both = max(part, total - part) < S.MASK_BELOW
            return (small, small) if both else pair(total, part)

        pair = S.shown_pair
        patch.setattr(S, "shown_pair", two_masks)
        assert recoverable(BANDS[2], [[0], [1]])
    # an exact count printed after a withheld one can close in on it
    with monkeypatch.context() as patch:

        def step_by_step(steps: Sequence[Sequence[tuple[int, int]]]) -> list[list[int | str]]:
            kept: list[tuple[int, int]] = [(0, 0)]
            printed: list[list[int | str]] = []
            first = S.shown_pair(*steps[0][0])[0]
            for index, step in enumerate(steps):
                if all(S.apart(one, other) for one in step for other in kept):
                    kept.extend(step)
                    printed.append([S.shown(part) for _, part in step])
                else:
                    printed.append([first if index == 0 else S.WITHHELD for _ in step])
            return printed

        patch.setattr(S, "shown_nested", step_by_step)
        assert recoverable(BANDS[2], layout)


def raw_counts(**replace: Any) -> dict[str, Any]:
    def counts(statements: int, scoreable: int, episodes: int = 9, held: int = 3) -> dict[str, int]:
        return {
            "statements": statements,
            "episodes": episodes,
            "scoreable": scoreable,
            "scoreable_episodes": held,
            "with_a_horizon_event_undetermined": statements - scoreable,
        }

    raw = {
        "e3": counts(40, 38),
        "slices": {"llama-3.3-70b": counts(14, 12), "gpt-4o-mini": counts(1, 0)},
        "observable": {"all": (40, 39), "after_cutoff": (14, 13)},
    }
    raw.update(replace)
    return raw


def record_inputs() -> dict[str, Any]:
    digest = "ab" * 32
    return {
        "sealed_outcomes": {"file": "outcomes_test.csv.gz", "sha256": digest},
        "eligible_list": {"file": "eligible_e3.csv", "sha256": digest},
        "events": {"file": "events.csv.gz", "sha256": digest},
        "capture_manifest": {"file": "capture_manifest.csv", "sha256": digest},
        "code_sha256": dict.fromkeys(S.CODE, digest),
    }


def full_slices(**sizes: tuple[int, int]) -> dict[str, dict[str, int]]:
    """Slice counts for every model with a slice: ``(statements, scoreable)``, by default
    (300, 200) less twenty statements and ten scoreable per model down the table."""
    models = [m for m, day in S.CUTOFF_MONTH_ENDS.items() if S.has_slice(day)]
    slices = {}
    for index, model in enumerate(models):
        default = (300 - 20 * index, 200 - 10 * index)
        statements, scoreable = sizes.get(model.replace("-", "_").replace(".", "_"), default)
        slices[model] = {"statements": statements, "scoreable": scoreable}
    return slices


def test_masks_in_the_record_and_the_printout() -> None:
    record = S.record_of(raw_counts(), record_inputs(), with_observable=True)
    assert record["e3_eligible_test"] == {
        "eligible_statements": 40,
        "eligible_episodes": 9,
        "scoreable_statements": ">35",
        "scoreable_episodes": "withheld",
        "undetermined_statements": "<5",
    }
    assert record["post_cutoff_slices"]["scoreable_statements"] == {
        "llama-3.3-70b": ">9",  # 14 statements, and fewer than 5 undetermined on the list
        "gpt-4o-mini": "<5",
    }
    assert record[S.OPTIONAL_KEY] == {
        "model": "llama-3.3-70b",
        "observable_statements": ">35",
        "observable_statements_after_cutoff": ">9",
    }
    text = "\n".join(S.lines_of(record))
    S.check_text(text)
    assert "  scoreable statements: >35" in text and "undetermined: <5" in text
    assert "  gpt-4o-mini: <5" in text
    # no small integer survives anywhere in the counts
    assert not re.search(r": [0-4]$", text, re.MULTILINE)
    # episodes beside their total; every slice of the table, the primaries exact
    raw = raw_counts(slices=full_slices())
    raw["e3"] = {**raw["e3"], "statements": 400, "scoreable": 250, "episodes": 30}
    raw["e3"]["scoreable_episodes"] = 28
    record = S.record_of(raw, record_inputs())
    S.check_record(record)
    assert record["e3_eligible_test"]["scoreable_episodes"] == ">25"
    assert record["e3_eligible_test"]["scoreable_statements"] == 250
    assert record["e3_eligible_test"]["undetermined_statements"] == 150
    assert record["post_cutoff_slices"]["scoreable_statements"] == {
        "llama-3.3-70b": 200,
        "deepseek-v3": 190,
        "qwen-2.5-7b": 180,
        "gemma-3-27b": 170,
        "gpt-oss-20b": 160,
        "gpt-4o-mini": 150,
    }
    raw["e3"]["scoreable_episodes"] = 25
    assert S.record_of(raw, record_inputs())["e3_eligible_test"]["scoreable_episodes"] == 25
    # a secondary slice four scoreable statements from a primary one: the secondaries close,
    # and each is its size less the 90 undetermined of the deepseek-v3 slice, or more
    raw = {**raw, "slices": full_slices(qwen_2_5_7b=(265, 186))}
    record = S.record_of(raw, record_inputs())
    S.check_record(record)
    assert record["post_cutoff_slices"]["scoreable_statements"] == {
        "llama-3.3-70b": 200,
        "deepseek-v3": 190,
        "qwen-2.5-7b": ">174",
        "gemma-3-27b": ">149",
        "gpt-oss-20b": ">129",
        "gpt-4o-mini": ">109",
    }


def test_the_run_masks_what_the_layout_makes_small(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, record = run(built, tmp_path, capsys, OBSERVABLE)
    assert record["masked_below"] == 5
    lines = printed.splitlines()
    assert lines[1].startswith("reading a count: <5 is fewer than 5; >N is more than N; withheld")
    # by design one episode in seven holds no scoreable statement, 3 + b eligible statements
    # after the cutoff are not observable, and 3 statements lie between two cutoffs: none of
    # the three numbers, nor a count that gives one by subtraction, is in the output
    raw = raw_of(built, with_observable=True)
    assert raw["e3"]["episodes"] - raw["e3"]["scoreable_episodes"] == 1
    after = raw["observable"]["after_cutoff"]
    assert after[0] - after[1] == 3 + built.b
    assert record["e3_eligible_test"]["scoreable_episodes"] == "withheld"
    assert isinstance(record[S.OPTIONAL_KEY]["observable_statements_after_cutoff"], str)
    assert isinstance(record["post_cutoff_slices"]["scoreable_statements"]["gpt-4o-mini"], str)
    assert not re.search(r": [0-4]$", printed, re.MULTILINE)


# --------------------------------------------------------------------------------------------
# Nothing but counts
# --------------------------------------------------------------------------------------------

DATE_LIKE = re.compile(
    r"\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?"  # 2024-12-25, 2024-12, 2024/12/25
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"  # 12/25/2024, 25.12.24
    r"|(?<![0-9a-f])(?:19|20)\d{2}(?![0-9a-f])"  # a year on its own
    r"|(?<![0-9a-f])(?:19|20)\d{6}(?![0-9a-f])"  # 20241225
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d",
    re.IGNORECASE,
)
DECIMAL = re.compile(r"\d\s*[.,]\s*\d|\d\s*%")
OUTCOME_WORDS = re.compile(
    r"recovered|censored|discontinu|not_at_risk|end_of_|no_followup|absent_generic|"
    r"\b(?:yes|no)\b|lower|upper|width|days_|_days|interval|at_cap|rate|share|mean|median|"
    r"percent|proportion",
    re.IGNORECASE,
)


def stripped(text: str, built: SimpleNamespace, tmp_path: Path) -> str:
    """The text without what is not a count: the folder of this test, the model names (their
    version numbers have dots) and the one label that names the width of an observable bracket."""
    text = text.replace(str(tmp_path), "").replace(tmp_path.as_posix(), "")
    for name in sorted(S.CUTOFF_MONTH_ENDS, key=len, reverse=True):
        text = text.replace(name, "MODEL")
    return text.replace("(bracket of 31 days or less)", "")


def leaves(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in leaves(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in leaves(item)]
    return [value]


def walk(value: Any) -> list[Any]:
    """Every container and leaf of a record."""
    if isinstance(value, dict):
        return [value, *(x for item in value.values() for x in walk(item))]
    return [value]


def test_output_has_no_date_no_decimal_no_outcome_value_and_no_row(
    built: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed, record = run(built, tmp_path, capsys, OBSERVABLE)
    written = (tmp_path / "counts" / "sealed_counts_0.json").read_text(encoding="utf-8")
    sealed = D.read_table(built.sealed)
    assert sealed["upper_date_B"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").any()  # dates are there
    for name, text in (("printout", printed), ("file", written)):
        text = stripped(text, built, tmp_path)
        assert not DATE_LIKE.search(text), (name, DATE_LIKE.search(text))
        assert not DECIMAL.search(text), (name, DECIMAL.search(text))
        assert not OUTCOME_WORDS.search(text), (name, OUTCOME_WORDS.search(text))
        # no id of an event, a statement, a thread or an episode, and no cell of a sealed row
        for column in ("event_id", "statement_group_id", "thread_id", "episode_id"):
            assert not any(i and i in text for i in set(built.corpus.events[column])), column
        for column in ("lower_date_B", "upper_date_B", "followup_end_date", "exit_date_B"):
            assert not any(v and v in text for v in set(sealed[column])), column
        assert not any(line.generic in text for line in LINES)
    # the file: every leaf is a count, a mask, a hash, or one of a few fixed texts
    counts = [
        *record["e3_eligible_test"].values(),
        *record["post_cutoff_slices"]["scoreable_statements"].values(),
        record[S.OPTIONAL_KEY]["observable_statements"],
        record[S.OPTIONAL_KEY]["observable_statements_after_cutoff"],
    ]
    assert len(counts) == 5 + 6 + 2
    masked = r"<5|>\d+|withheld"
    assert all((type(v) is int and v >= 5) or re.fullmatch(masked, str(v)) for v in counts)
    texts = {S.ABOUT, f"{S.COMMAND} {OBSERVABLE}"} | set(S.CUTOFF_MONTH_ENDS)
    files = {"outcomes_test.csv.gz", "e3.csv", "events.csv.gz", "capture_manifest.csv"}
    for leaf in leaves(record):
        assert type(leaf) in (int, str), leaf
        if isinstance(leaf, str):
            known = leaf in texts or leaf in files or re.fullmatch(r"[0-9a-f]{64}|" + masked, leaf)
            assert known, leaf
    assert sum(type(leaf) is int for leaf in leaves(record)) <= len(counts) + 1  # and the mask
    # no list but the names of the models without a slice
    lists = [v for v in walk(record) if isinstance(v, list)]
    assert lists == [["gemini-3.8-flash", "grok-4.20"]]
    # the printout: a label and one count (or hash, or names) per line, nothing tabular
    for line in printed.splitlines()[:-1]:
        assert line.count(":") == 1, line
    assert len(printed.splitlines()) == 22
    assert len(run(built, tmp_path, capsys)[0].splitlines()) == 19


def good_record() -> dict[str, Any]:
    return S.record_of(raw_counts(slices=full_slices()), record_inputs())


def test_the_checks_before_printing_stop_anything_else() -> None:
    good = good_record()
    S.check_record(good)
    bad_counts = (4, 0, 0.4, "0.4", "2024-12-25", "recovered", [5, 6], {"recovered": 9}, True, None)
    for value in bad_counts:
        for section, key in (
            ("e3_eligible_test", "scoreable_statements"),
            ("e3_eligible_test", "eligible_episodes"),
        ):
            bad = json.loads(json.dumps(good))
            bad[section][key] = value
            with pytest.raises(SystemExit):
                S.check_record(bad)
        bad = json.loads(json.dumps(good))
        bad["post_cutoff_slices"]["scoreable_statements"]["llama-3.3-70b"] = value
        with pytest.raises(SystemExit):
            S.check_record(bad)
        bad = json.loads(json.dumps(good))
        bad[S.OPTIONAL_KEY] = dict.fromkeys(S.SECTION_KEYS[S.OPTIONAL_KEY], 9)
        bad[S.OPTIONAL_KEY]["model"] = S.GATE_MODEL
        bad["command"] = f"{S.COMMAND} {OBSERVABLE}"
        S.check_record(bad)
        bad[S.OPTIONAL_KEY]["observable_statements"] = value
        with pytest.raises(SystemExit):
            S.check_record(bad)
    for change in (
        {"by_form": {"quarter": 9}},
        {"rows": [["E1", "recovered"]]},
        {"masked_below": 1},
        {"about": "E1 recovered"},
        {"command": S.COMMAND + " --by-form"},
        {"command": f"{S.COMMAND} {OBSERVABLE}"},  # the flag without its section
        {"e3_eligible_test": [9, 9, 9, 9, 9]},
        {S.OPTIONAL_KEY: {"model": S.GATE_MODEL, "observable_statements": 9}},
        {"gate1_second_threshold": {"e3_eligible_statements": 9}},
    ):
        with pytest.raises(SystemExit):
            S.check_record({**good, **change})
    for section, key in (
        ("inputs", "first_rows"),
        ("inputs", "cutoffs"),
        ("post_cutoff_slices", "undetermined_statements"),
        ("e3_eligible_test", "scoreable_2024"),
    ):
        wider = json.loads(json.dumps(good))
        wider[section][key] = 9
        with pytest.raises(SystemExit):
            S.check_record(wider)
    wider = json.loads(json.dumps(good))
    wider["inputs"]["sealed_outcomes"]["rows"] = 9
    with pytest.raises(SystemExit):
        S.check_record(wider)
    del wider["inputs"]["sealed_outcomes"]["rows"]
    S.check_record(wider)
    wider["inputs"]["sealed_outcomes"]["sha256"] = "recovered"
    with pytest.raises(SystemExit):
        S.check_record(wider)
    for change in (
        lambda r: r["inputs"]["code_sha256"].update({"other.py": "ab" * 32}),
        lambda r: r["inputs"]["code_sha256"].pop("rules.py"),
        lambda r: r["inputs"]["events"].update({"file": 9}),
        lambda r: r["post_cutoff_slices"]["scoreable_statements"].update({"quarter": 9}),
        lambda r: r["post_cutoff_slices"]["scoreable_statements"].pop("gpt-4o-mini"),
        lambda r: r["post_cutoff_slices"]["models_without_a_slice"].append("recovered"),
        lambda r: r["post_cutoff_slices"]["models_without_a_slice"].pop(),
    ):
        other = json.loads(json.dumps(good))
        change(other)
        with pytest.raises(SystemExit):
            S.check_record(other)
    for text in ("upper 2024-12-25", "seen 12/25/2024", "rate 0.75", "2023-12", "1,5"):
        with pytest.raises(SystemExit):
            S.check_text(text)
    S.check_text(
        "llama-3.3-70b: 2024\ngrok-4.20: 12\nqwen-2.5-7b: <5\nsha256 of the list: " + "9" * 64
    )


@pytest.mark.parametrize(
    "spoil",
    [
        lambda record: record.update(rows=[["E1", "recovered"]]),
        lambda record: record["e3_eligible_test"].update(scoreable_statements=4),
        lambda record: record["e3_eligible_test"].update(by_outcome={"recovered": 9}),
        lambda record: record["post_cutoff_slices"]["scoreable_statements"].update(quarter=9),
        lambda record: record["inputs"]["events"].update(file="events_2024-12-25.csv.gz"),
    ],
)
def test_a_run_goes_through_the_checks_before_it_prints_or_writes(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    spoil: Any,
) -> None:
    make = S.record_of

    def spoiled(*args: Any, **kwargs: Any) -> dict[str, Any]:
        record = make(*args, **kwargs)
        spoil(record)
        return record

    monkeypatch.setattr(S, "record_of", spoiled)
    reason = refused(built, tmp_path, capsys)
    assert "the output would hold" in reason


def test_a_run_checks_the_printout_too(
    built: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines = S.lines_of
    monkeypatch.setattr(S, "lines_of", lambda record: [*lines(record), "last seen 2024-12-25"])
    assert "would hold a date" in refused(built, tmp_path, capsys)


# --------------------------------------------------------------------------------------------
# The Late split, and the same definitions as the dataset builder
# --------------------------------------------------------------------------------------------


def test_late_rows_are_dropped_before_anything_is_counted(built: SimpleNamespace) -> None:
    rows = D.read_table(built.sealed)
    assert (rows["event_date"] >= "2026-01-01").sum() == 1  # n4
    kept = S._checked_rows(rows, D.read_table(built.events))
    assert len(kept) == len(rows) - 1 and (kept["event_date"] < "2026-01-01").all()
    assert built.event_of["n4"] not in set(kept["event_id"])


def test_same_counts_as_the_dataset_builder_on_a_train_like_file(built: SimpleNamespace) -> None:
    """The open train outcomes have the columns of the sealed file. On them the dataset builder
    counts scoreable statements itself, and the functions this script calls give its numbers."""
    events = D.as_text(built.corpus.events)
    train = D.as_text(built.corpus.outcomes[built.corpus.outcomes["period"] == "train"])
    assert list(train.columns) == list(D.read_table(built.sealed).columns)
    report = D.build(D.Inputs(events, train, CAPTURE_DAYS, (), {"events": "synthetic"})).report
    theirs = report["train"]["dev"]["dated"]
    # by design: t1, t4, t6 and t8 are scoreable, t2, t5 and t7 are not, in two episodes
    assert {k: theirs[k] for k in ("statements", "scoreable", "episodes")} == {
        "statements": 7,
        "scoreable": 4,
        "episodes": 2,
    }
    table = D.statement_table(events, LAST)
    dev = table[(table["split"] == "dev") & (table["analysis_set"] == "dated")]
    dev = dev.sort_values("statement_group_id").reset_index(drop=True)
    cutoffs = {S.GATE_MODEL: date(2022, 4, 30), "gpt-4o-mini": date(2022, 2, 28)}
    raw = S._sealed_counts(dev, train, cutoffs, with_observable=True)
    assert raw["e3"] == {key: theirs[key] for key in raw["e3"]} and len(raw["e3"]) == 5
    # a slice is the same count on the statements dated after the cutoff month: t7, t8, t1 and
    # t2 are dated after April 2022 (two scoreable); t5 and t6 as well after February (three)
    assert {m: c["scoreable"] for m, c in raw["slices"].items()} == {
        S.GATE_MODEL: 2,
        "gpt-4o-mini": 3,
    }
    assert {m: c["statements"] for m, c in raw["slices"].items()} == {
        S.GATE_MODEL: 4,
        "gpt-4o-mini": 6,
    }
    for model, day in cutoffs.items():
        late = dev[dev["event_date"] > day.isoformat()]
        assert raw["slices"][model] == D.scoreable_counts(D.attach_outcomes(late, train))
    # the display row's bracket, as the builder attaches it
    full = D.attach_outcomes(dev, train)
    assert raw["e3"] == D.scoreable_counts(full)
    assert raw["observable"]["all"] == (7, int(D.true(full["observable31"]).sum())) == (7, 5)
    after = D.true(full["observable31"]) & (full["event_date"] > "2022-04-30")
    assert raw["observable"]["after_cutoff"] == (4, int(after.sum()))
    # the test-period rows through the same functions: the counts a run starts from
    listed = S.listed_statements(built.table, D.read_table(built.eligible))
    rows = S._checked_rows(D.read_table(built.sealed), D.read_table(built.events))
    sealed = D.attach_outcomes(listed, rows)
    assert raw_of(built)["e3"] == D.scoreable_counts(sealed)
    assert D.scoreable_counts(sealed)["scoreable"] == 25 + built.b
