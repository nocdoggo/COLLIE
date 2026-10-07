"""Tests for the scorer of E2 and E5 and of the registered pattern (``literal_scores.py``).

No test reads an outcome, a sealed folder, a key folder of the study, a network connection or
an API key. One test reads the committed plan, to hold the constants of the pattern and the
words of its sentence to the plan's own. Everything else runs on made-up files in temporary
folders:

* E2: a made-up events table (one statement per row, wordings chosen so that the frozen form
  classifier puts them in known strata) and a short guide; the blank sheets, the item file and
  the key written by the sampler (``audit_sample.build_sheets``); two scripted annotators; the
  agreement script's ``agree`` and ``gold`` commands, which write the submitted sheets, the
  adjudication sheet and the gold file;
* E5: seeds and edits built as the generator's own objects (``minimal_pairs.Item``), whose
  ``record`` and ``gold_row`` write the item file and the gold file;
* a plan made by ``launch.make_plan`` and every run read by the harness's own reader
  (``read.Reader``, ``read.write_run``) around a scripted client, so that rows and manifests
  are in the harness's format. The scripted answers are a fixed function of the model, the
  template and the item;
* the pattern: the two result files of the made-up study, and result files written out by
  hand that hold what the pattern reads of a result and nothing else;
* a cut of E5: a made-up seed list, the cut item file, and a second plan with its own runs.

Covered: every metric on cases worked by hand, letter accuracy among them; the letter reading
with its two intervals; the exact intervals of the rates; the ceiling on every labelled item;
the weights by event and by template; the
intervals against a loop over the same draws; the exact McNemar test; Holm; the GEE against a
logistic fit and a cluster sandwich written here from the cell means, and against statsmodels
when it is installed; the two p-values of the bootstrap fallback against a loop in exact
fractions; the error definition of E5, with the unedited item held to the criterion of the
factor it is compared with; the seeds of a contrast counted on each of its sides; what the
standing part of the registered pattern reads beside a test; a fit that does not converge;
both commands end to end against values worked out here; every
refusal; a run stored in several parts; and that no text of an item reaches a result or the
printout. Also: that the cells of the models outside the registered family never decide its
procedure; the margins over the rule reader and over the annotators against a loop over the
same draws; the pins of the rule reader and of the item file; plans, manifests and stored rows
that are not as they are written; what a declaration of runs not run is held to; and that a
refused input in a sealed folder is neither opened nor listed (an audit hook of the
interpreter records both). For the registered pattern of PLAN section 13: the floors at
exactly 0.10 and just below, on counts and through the scorer of E5 on readings worked by
hand, with the own error of each standing factor; the margin of the letter part at exactly
-0.10, read on the lower end as an exact fraction, with ends that are -1/10 by interpolation
and a model above the rule reader whose interval starts below; the letter reading of each
primary; every outcome that the
bullet "The sentence" tells apart, on result files written by hand (both primaries; one by
name; the letter part withheld by its margin or by a test on a letter factor; a standing test
that a floor or the own error withholds; a secondary model alone; a primary declared not run;
E5 not scored); the pattern end to end on the made-up study; E5 cut to the first seeds of
the seed list, with the rows of the cut item file held to the registered ones byte for byte,
and the pattern on it; and every refusal of the cut and of ``pattern``, a result that cannot
be read whole among them.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_literal_scores.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, redirect_stdout
from datetime import date
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from scipy import optimize, stats

from analysis.coling import audit_agreement as A
from analysis.coling import audit_sample as S
from analysis.coling import corpus as C
from analysis.coling import evaluate as ev
from analysis.coling import forms as F
from analysis.coling import launch as lp
from analysis.coling import literal_scores as LS
from analysis.coling import minimal_pairs as MP
from analysis.coling import predictors as P
from analysis.coling import read as rd
from analysis.coling import rules as R
from collie.llm.client import EndpointConfig

LLAMA, DEEPSEEK = rd.PRIMARIES
QWEN, GEMMA, OSS, MINI, GEMINI, GROK = rd.STUDY_MODELS[2:]
V1, FREE = "literal-v1", "literal-free-v1"
DAY = "2020-03-02"
APRIL = ("2020-04-01", "2020-04-30")
GARBAGE = "I cannot answer in that form."
NDC = re.compile(r"NDC (\d{4})-(\d{4})-01")


# --------------------------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------------------------


def guard(monkeypatch: pytest.MonkeyPatch, nowhere: Path) -> None:
    """What no test may do, made impossible: open a network connection, read a key, or use
    the real repository as the harness's checkout."""

    def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a test tried to open a network connection")

    def no_key(self: Any) -> None:
        raise AssertionError("a test tried to read an API key")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(EndpointConfig, "resolve_key", no_key)
    for name in list(os.environ):
        if name.endswith("_API_KEY") or name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(rd, "REPO", nowhere)


@pytest.fixture(autouse=True)
def guarded(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    guard(monkeypatch, tmp_path_factory.mktemp("nowhere"))


# --------------------------------------------------------------------------------------------
# Small cases worked by hand
# --------------------------------------------------------------------------------------------


def near(value: Any, rel: float | None = None, abs: float = 1e-6) -> Any:
    """Equal to a number of a result file, which holds six decimals."""
    return pytest.approx(value, rel=rel, abs=abs)


def d(text: str) -> date:
    return date.fromisoformat(text)


def span(start: str, end: str) -> tuple[date, date]:
    return d(start), d(end)


def reading(
    kind: str | None,
    start: str = "",
    end: str = "",
    certainty: str | None = "asserted",
    stale: bool = False,
    parsed: bool = True,
) -> LS.Reading:
    return LS.Reading(kind, span(start, end) if start else None, certainty, stale, parsed)


def gold(
    kind: str,
    start: str = "",
    end: str = "",
    certainty: str = "asserted",
    stale: bool = False,
    distractors: Sequence[tuple[str, str]] = (),
) -> LS.Gold:
    return LS.Gold(
        "I",
        reading(kind, start, end, certainty, stale),
        distractors=tuple(span(a, b) for a, b in distractors),
        roles=len(distractors),
    )


def days_of(interval: tuple[date, date]) -> set[int]:
    return set(range(interval[0].toordinal(), interval[1].toordinal() + 1))


def iou_by_sets(first: tuple[date, date], second: tuple[date, date]) -> Fraction:
    """IoU from the two sets of days themselves."""
    a, b = days_of(first), days_of(second)
    return Fraction(len(a & b), len(a | b))


def test_iou_counts_days_with_both_end_days() -> None:
    april = span("2020-04-01", "2020-04-30")
    assert LS.span_days(april) == 30 and LS.span_days(span("2020-06-05", "2020-06-05")) == 1
    # half of April against the fifteen days around the end of April: 15 shared of 45
    assert LS.iou(april, span("2020-04-16", "2020-05-15")) == pytest.approx(1 / 3)
    assert LS.iou(april, april) == 1.0
    assert LS.iou(span("2020-06-05", "2020-06-05"), span("2020-06-05", "2020-06-05")) == 1.0
    assert LS.iou(april, span("2020-05-01", "2020-05-31")) == 0.0  # adjacent months share no day
    assert LS.iou(april, span("2020-05-02", "2020-05-31")) == 0.0  # one day between them
    assert LS.iou(span("2019-01-01", "2019-12-31"), april) == 0.0
    assert LS.iou(april, span("2020-04-30", "2020-05-29")) == pytest.approx(1 / 59)
    assert LS.iou(span("2020-04-01", "2020-04-10"), april) == pytest.approx(10 / 30)
    assert LS.iou(april, span("2020-04-01", "2020-04-15")) == 0.5  # the threshold itself
    pairs = [
        (span("2020-01-01", "2020-12-31"), span("2020-06-01", "2021-03-31")),
        (span("2020-10-11", "2020-10-20"), span("2020-10-01", "2020-10-31")),
        (span("2021-01-01", "2021-03-31"), span("2020-10-01", "2021-03-31")),
        (span("2020-02-01", "2020-02-29"), span("2020-03-01", "2020-03-01")),
        (span("2020-01-01", "2020-01-10"), span("2021-03-01", "2021-03-31")),
    ]
    for a, b in pairs:
        assert LS.iou(a, b) == pytest.approx(float(iou_by_sets(a, b)))
        assert LS.iou(b, a) == LS.iou(a, b)


def test_a_distractors_interval_is_its_quote_read_by_the_frozen_conventions() -> None:
    anchor = d(DAY)
    assert LS.distractor_intervals(["(1/2022 expiry)"], anchor) == (
        span("2022-01-01", "2022-01-31"),
    )
    # "until X" is the period X; "by X" runs from the Date of update to the end of X
    assert LS.distractor_intervals(
        [
            "Remaining inventory estimated to last until April 2020",
            "Current supply expected to deplete by May/June 2020 timeframe",
        ],
        anchor,
    ) == (span("2020-04-01", "2020-04-30"), span(DAY, "2020-06-30"))
    # a month with no year is its first occurrence that ends on or after the anchor
    assert LS.distractor_intervals(["Projecting backorder in May"], d("2020-08-13")) == (
        span("2021-05-01", "2021-05-31"),
    )
    assert LS.distractor_intervals(["available until", "Check wholesalers"], anchor) == ()
    assert LS.distractor_intervals([], anchor) == ()


def test_a_stored_row_becomes_a_reading_and_a_failed_one_abstains() -> None:
    row = {
        "reading": {
            "statement_type": "recovery",
            "interval": {"start": "2020-05-01", "end": "2020-05-31"},
            "certainty": "estimated",
            "stale": True,
            "quote": "Estimated recovery",
        }
    }
    assert LS.stored_reading(row) == reading(
        "recovery", "2020-05-01", "2020-05-31", "estimated", stale=True
    )
    row["reading"]["interval"] = "ABSTAIN"
    row["reading"]["stale"] = False
    assert LS.stored_reading(row) == reading("recovery", certainty="estimated")
    failed = LS.stored_reading({"reading": None, "status": "failed", "fallback": "abstain"})
    assert failed == LS.NO_ANSWER
    assert failed.interval is None and failed.stale is False and failed.parsed is False
    assert failed.statement_type is None and failed.certainty is None


OUTSIDE_THE_SCHEMA = {
    "a certainty class that is a free text": {"certainty": "back in stock soon"},
    "a statement type that is a free text": {"statement_type": "back in stock soon"},
    "a stale flag that is a text": {"stale": "no"},
    "a stale flag that is a number": {"stale": 0},
    "an interval that is a free text": {"interval": "back in stock soon"},
    "an interval that is nothing": {"interval": None},
    "an interval that ends before it starts": {
        "interval": {"start": "2020-05-31", "end": "2020-05-01"}
    },
}


@pytest.mark.parametrize("case", list(OUTSIDE_THE_SCHEMA))
def test_a_stored_answer_outside_the_answer_schema_is_no_reading(case: str) -> None:
    """The scorer's own reading of a stored row holds the four scored fields to the answer
    schema, whatever was checked before it: a free text is no certainty class and no
    abstention, a text is no stale flag, and an interval does not end before it starts. The
    error names the fault and quotes no cell."""
    answer = {
        "statement_type": "recovery",
        "interval": {"start": "2020-05-01", "end": "2020-05-31"},
        "certainty": "estimated",
        "stale": False,
        "quote": "Estimated recovery",
    }
    assert LS.stored_reading({"reading": answer}) == reading(
        "recovery", "2020-05-01", "2020-05-31", "estimated"
    )
    with pytest.raises(ValueError) as stop:
        LS.stored_reading({"reading": answer | OUTSIDE_THE_SCHEMA[case]})
    assert "soon" not in str(stop.value) and "2020" not in str(stop.value)
    # one day is a period, and so is the same day twice
    day = {"interval": {"start": "2020-05-01", "end": "2020-05-01"}}
    assert LS.stored_reading({"reading": answer | day}).interval == span("2020-05-01", "2020-05-01")


def test_the_rule_reader_reads_the_statement_text_of_an_item() -> None:
    """The guide's worked examples 2, 18 and 12 (the last with its timing in the Related
    information): the frozen reading of the two text fields, in the answer schema."""
    item = {
        "item_id": "I1",
        "date_of_update": "2020-08-13",
        "availability_information": "Backordered. Next release October 2020.",
        "related_information": "Check wholesalers for inventory",
    }
    assert LS.rule_reading(item) == reading("next_delivery", "2020-10-01", "2020-10-31")
    stale = {
        "date_of_update": "06/02/2020",
        "availability_information": "Unavailable, recovery in May 2020",
    }
    assert LS.rule_reading(stale) == reading("recovery", "2020-05-01", "2020-05-31", stale=True)
    related = {
        "date_of_update": "2019-09-09",
        "availability_information": "Currently unavailable",
        "related_information": "On backorder. Shortage duration is unknown at this time.",
    }
    assert LS.rule_reading(related) == reading("recovery", certainty="undetermined")
    silent = {"date_of_update": DAY, "availability_information": "On backorder"}
    assert LS.rule_reading(silent) == reading("none", certainty="no_statement")


GOLD_ROW = {
    "item_id": "I1",
    "statement_type": "next_delivery",
    "start": "2020-01-01",
    "end": "2020-01-31",
    "abstain": "0",
    "abstain_reason": "",
    "certainty": "asserted",
    "quote": "",
    "distractor_roles": "expiry; depletion",
    "distractor_quotes": "(1/2022 expiry) | available until further notice",
    "hard": "1",
    "note": "a note",
    "adj_decision": "gap",
    "adj_note": "",
}


def test_a_gold_row_gives_the_reading_the_stale_flag_and_the_distractor_dates() -> None:
    found = LS.gold_of("I1", GOLD_ROW, d(DAY))
    assert found.reading == reading("next_delivery", "2020-01-01", "2020-01-31", stale=True)
    assert found.distractors == (span("2022-01-01", "2022-01-31"),) and found.roles == 2
    assert found.decision == "gap" and found.hard is True
    # the flag is derived from the interval and the anchor: the day itself is not stale
    assert LS.gold_of("I1", GOLD_ROW, d("2020-01-31")).reading.stale is False
    assert LS.gold_of("I1", GOLD_ROW, d("2020-02-01")).reading.stale is True
    # a gold file with its own stale column is taken at its word
    assert LS.gold_of("I1", GOLD_ROW, d(DAY), "0").reading.stale is False
    assert LS.gold_of("I1", GOLD_ROW, d("2019-01-01"), "1").reading.stale is True
    abstains = GOLD_ROW | {"start": "", "end": "", "abstain": "1", "abstain_reason": "tbd"}
    found = LS.gold_of("I1", abstains | {"certainty": "undetermined"}, d(DAY))
    assert found.reading == reading("next_delivery", certainty="undetermined")
    assert found.abstain_reason == "tbd"


@pytest.mark.parametrize(
    "change",
    [
        {"statement_type": "availability_until"},
        {"certainty": "firm"},
        {"abstain": "yes"},
        {"abstain": "1"},
        {"end": ""},
        {"start": "", "end": ""},
        {"start": "2020-02-01"},
        {"start": "2020-02-30"},
    ],
)
def test_a_row_that_cannot_be_a_gold_row_is_named_without_its_cells(change: dict) -> None:
    with pytest.raises(ValueError) as stop:
        LS.gold_of("I1", GOLD_ROW | change, d(DAY))
    assert not any(str(value) in str(stop.value) for value in change.values() if value)
    with pytest.raises(ValueError):
        LS.gold_of("I1", GOLD_ROW, d(DAY), "maybe")


# eight items, each a case of its own; the reader's answers beside the gold
CASES: tuple[tuple[LS.Reading, LS.Gold], ...] = (
    # 1: everything right
    (
        reading("recovery", "2020-04-01", "2020-04-30", "estimated"),
        gold("recovery", "2020-04-01", "2020-04-30", "estimated"),
    ),
    # 2: the type wrong, the interval half of the gold one (IoU 15/30), the certainty wrong
    (
        reading("next_delivery", "2020-04-01", "2020-04-15", "estimated"),
        gold("recovery", "2020-04-01", "2020-04-30", "asserted"),
    ),
    # 3: the interval ten days of thirty (IoU 1/3), starts 20 days late, a stale flag invented
    (
        reading("recovery", "2020-04-21", "2020-04-30", "asserted", stale=True),
        gold("recovery", "2020-04-01", "2020-04-30", "asserted"),
    ),
    # 4: both abstain, the certainty wrong
    (reading("recovery", certainty="estimated"), gold("recovery", certainty="undetermined")),
    # 5: a date where the gold abstains (false commitment), on the gold's distractor date
    (
        reading("next_delivery", "2022-01-01", "2022-01-31", "asserted"),
        gold(
            "next_delivery",
            certainty="undetermined",
            distractors=[("2022-01-01", "2022-01-31")],
        ),
    ),
    # 6: an abstention where the gold gives a stale interval
    (
        reading("recovery", certainty="undetermined"),
        gold("recovery", "2020-01-01", "2020-01-31", "asserted", stale=True),
    ),
    # 7: no parsed answer: ABSTAIN, on a silent item
    (LS.NO_ANSWER, gold("none", certainty="no_statement")),
    # 8: the distractor's interval instead of the gold one; stale flags agree on stale
    (
        reading("recovery", "2020-01-01", "2020-01-31", "estimated", stale=True),
        gold(
            "recovery",
            "2020-02-01",
            "2020-02-29",
            "estimated",
            stale=True,
            distractors=[("2019-06-01", "2019-06-30"), ("2020-01-01", "2020-01-20")],
        ),
    ),
)
BY_HAND = {
    "correct": Fraction(2, 8),  # items 1 and 4; item 2 has the type wrong, item 7 no type
    "statement_type_accuracy": Fraction(6, 8),  # all but items 2 and 7
    "interval_iou": (1 + Fraction(1, 2) + Fraction(1, 3) + 0 + 0) / 5,  # items 1, 2, 3, 6, 8
    "interval_coverage": Fraction(4, 5),  # of those five, the reader abstains on item 6
    "identical_interval": Fraction(3, 8),  # items 1, 4 and 7
    "start_error_days": Fraction(0 + 0 + 20 + 31, 4),  # items 1, 2, 3, 8
    "end_error_days": Fraction(0 + 15 + 0 + 29, 4),
    "start_error_signed_days": Fraction(0 + 0 + 20 - 31, 4),
    "end_error_signed_days": Fraction(0 - 15 + 0 - 29, 4),
    "abstention_precision": Fraction(2, 3),  # the reader abstains on 4, 6, 7; gold on 4, 5, 7
    "abstention_recall": Fraction(2, 3),
    "abstention_f1": Fraction(2, 3),
    "false_commitment": Fraction(1, 3),  # item 5 of the gold-ABSTAIN items 4, 5, 7
    # items 3, 5 and 7 are marked; the gold of item 3 gives a date, so it does not count
    "false_commitment_tbd_or_silent": Fraction(1, 2),
    "stale_accuracy": Fraction(6, 8),  # wrong on items 3 and 6
    "stale_precision": Fraction(1, 2),  # the reader says stale on 3 and 8; the gold on 6 and 8
    "stale_recall": Fraction(1, 2),
    "stale_f1": Fraction(1, 2),
    "distractor_uptake": Fraction(2, 2),  # items 5 and 8 carry a distractor date
    "certainty_accuracy": Fraction(3, 8),  # items 1, 3 and 8
    # over the seven parsed readings: 3 agree; the reader says asserted 2, estimated 4,
    # undetermined 1; the gold asserted 3, estimated 2, undetermined 2
    "certainty_kappa": (Fraction(3, 7) - Fraction(2 * 3 + 4 * 2 + 1 * 2, 49))
    / (1 - Fraction(2 * 3 + 4 * 2 + 1 * 2, 49)),
    # the letter items are 1, 2, 3 and 6: the gold of 4, 5 and 7 gives no interval, and that of
    # item 8 carries a distractor date; of the four, item 1 alone is correct
    "letter_accuracy": Fraction(1, 4),
}
MARKED = (False, False, True, False, True, False, True, False)


def case_columns() -> dict[str, np.ndarray]:
    return LS.columns([r for r, _ in CASES], [g for _, g in CASES], MARKED)


def test_every_metric_on_eight_items_worked_by_hand() -> None:
    cols = case_columns()
    found = LS.values(cols, np.ones(8))
    assert set(found) == set(LS.METRICS) == set(BY_HAND)
    for name, expected in BY_HAND.items():
        assert found[name] == pytest.approx(float(expected)), name
    assert LS.counts(cols) == {
        "items": 8,
        "parsed": 7,
        "gold_interval": 5,
        "gold_abstain": 3,
        "reader_abstain": 3,
        "both_interval": 4,
        "gold_stale": 2,
        "reader_stale": 2,
        "gold_with_distractor_date": 2,
        "gold_abstain_tbd_or_silent": 2,
        "letter_items": 4,
    }
    assert LS.counts(cols, [True] * 4 + [False] * 4)["gold_abstain"] == 1
    # the flags of the E2 rule, item by item
    assert cols["correct"].tolist() == [1, 0, 0, 1, 0, 0, 0, 0]
    assert cols["uptake"].tolist() == [0, 0, 0, 0, 1, 0, 0, 1]
    assert cols["letter"].tolist() == [1, 1, 1, 0, 0, 1, 0, 0]
    assert cols["letter_correct"].tolist() == [1, 0, 0, 0, 0, 0, 0, 0]


def test_letter_accuracy_is_the_e2_rule_on_the_dated_items_without_a_distractor_date() -> None:
    """PLAN section 7.1: among the gold items that give an interval and carry no distractor
    date, the share of readings correct by the E2 rule. An item whose gold abstains is no
    letter item, even when the reader abstains too and is correct; neither is a dated item
    beside a distractor date."""
    right, off = reading("recovery", *APRIL), reading("recovery", "2020-06-01", "2020-06-30")
    carried = [("2022-01-01", "2022-01-31")]
    pairs = [
        (right, gold("recovery", *APRIL)),  # a letter item, correct
        (off, gold("recovery", *APRIL)),  # a letter item, the interval elsewhere
        (reading("depletion", *APRIL), gold("recovery", *APRIL)),  # a letter item, the type wrong
        (reading("recovery"), gold("recovery", *APRIL)),  # a letter item, the reader abstains
        (reading("recovery"), gold("recovery")),  # correct, and no letter item
        (right, gold("recovery", *APRIL, distractors=carried)),  # correct, and no letter item
        (off, gold("recovery", *APRIL, distractors=carried)),
    ]
    readings, golds = zip(*pairs, strict=True)
    assert [LS.letter_item(g) for g in golds] == [True] * 4 + [False] * 3
    # a distractor role whose quote gives no date is no distractor date: a letter item
    assert LS.letter_item(LS.Gold("I", right, roles=1)) is True
    assert LS.letter_item(LS.Gold("I", right, distractors=(span(*APRIL),))) is False
    cols = LS.columns(readings, golds)
    assert cols["correct"].tolist() == [1, 0, 0, 0, 1, 1, 0]
    assert cols["letter"].tolist() == [1, 1, 1, 1, 0, 0, 0]
    assert cols["letter_correct"].tolist() == [1, 0, 0, 0, 0, 0, 0]
    found = LS.values(cols, np.ones(7))
    assert found["letter_accuracy"] == 0.25 and found["correct"] == pytest.approx(3 / 7)
    # weights count a letter item as often as they say
    assert LS.values(cols, [3, 1, 1, 1, 9, 9, 9])["letter_accuracy"] == 0.5
    # no letter item, no letter accuracy
    assert LS.values(LS.columns(readings[4:], golds[4:]), np.ones(3))["letter_accuracy"] is None
    # the letter items can be named from outside, where the labels scored against are not the
    # gold: the E2 rule is then read against those labels, on the items named
    named = LS.columns(readings, golds, None, [False, True, False, False, True, True, True])
    assert named["letter"].tolist() == [0, 1, 0, 0, 1, 1, 1]
    assert named["letter_correct"].tolist() == [0, 0, 0, 0, 1, 1, 0]
    assert LS.values(named, np.ones(7))["letter_accuracy"] == 0.5


def test_the_correct_rule_needs_the_type_and_half_the_days() -> None:
    april = ("2020-04-01", "2020-04-30")

    def correct(mine: LS.Reading, theirs: LS.Gold) -> bool:
        return bool(LS.columns([mine], [theirs])["correct"][0])

    assert correct(reading("recovery", "2020-04-01", "2020-04-15"), gold("recovery", *april))
    assert not correct(reading("recovery", "2020-04-01", "2020-04-14"), gold("recovery", *april))
    assert not correct(reading("depletion", *april), gold("recovery", *april))
    assert correct(reading("none", certainty="no_statement"), gold("none"))
    assert not correct(reading("recovery"), gold("none"))
    assert not correct(reading("recovery"), gold("recovery", *april))
    assert not correct(reading("recovery", *april), gold("recovery"))
    assert not correct(LS.NO_ANSWER, gold("none"))
    # the certainty class and the stale flag are no part of it
    assert correct(reading("recovery", *april, "estimated", stale=True), gold("recovery", *april))


def test_distractor_uptake_needs_the_distractor_and_not_the_gold() -> None:
    carried = [("2020-01-01", "2020-01-31")]

    def uptake(mine: LS.Reading, theirs: LS.Gold) -> tuple[float, float]:
        cols = LS.columns([mine], [theirs])
        return cols["has_distractor"][0], cols["uptake"][0]

    theirs = gold("recovery", "2020-04-01", "2020-04-30", distractors=carried)
    assert uptake(reading("recovery", "2020-01-01", "2020-01-31"), theirs) == (1, 1)
    assert uptake(reading("recovery", "2020-01-01", "2020-01-16"), theirs) == (1, 1)  # 16/31
    assert uptake(reading("recovery", "2020-01-01", "2020-01-15"), theirs) == (1, 0)  # 15/31
    assert uptake(reading("recovery", "2020-04-01", "2020-04-30"), theirs) == (1, 0)
    assert uptake(reading("recovery"), theirs) == (1, 0)
    # an interval that reaches both the distractor and the gold is not an uptake
    both = gold("recovery", "2020-01-01", "2020-01-31", distractors=carried)
    assert uptake(reading("recovery", "2020-01-01", "2020-01-31"), both) == (1, 0)
    # no distractor date, no uptake to count
    assert uptake(reading("recovery", "2020-01-01", "2020-01-31"), gold("recovery")) == (0, 0)
    # the gold abstains: the distractor alone decides
    silent = gold("none", certainty="no_statement", distractors=carried)
    assert uptake(reading("recovery", "2020-01-01", "2020-01-31"), silent) == (1, 1)


def test_a_metric_without_its_denominator_is_undefined() -> None:
    april = ("2020-04-01", "2020-04-30")
    pairs = [(reading("recovery", *april), gold("recovery", *april))]
    found = LS.values(LS.columns(*zip(*pairs, strict=True)), np.ones(1))
    for name in (
        "abstention_precision",
        "abstention_recall",
        "abstention_f1",
        "false_commitment",
        "false_commitment_tbd_or_silent",
        "stale_precision",
        "stale_recall",
        "stale_f1",
        "distractor_uptake",
        "certainty_kappa",  # one class on both sides: chance agreement is complete
    ):
        assert found[name] is None, name
    assert found["correct"] == 1.0 and found["interval_iou"] == 1.0
    assert found["start_error_days"] == 0.0 and found["stale_accuracy"] == 1.0
    assert found["interval_coverage"] == 1.0
    # nothing parsed: no kappa, and every accuracy is zero
    nothing = LS.values(LS.columns([LS.NO_ANSWER], [gold("none")]), np.ones(1))
    assert nothing["certainty_kappa"] is None and nothing["certainty_accuracy"] == 0.0
    assert nothing["interval_coverage"] is None and nothing["interval_iou"] is None
    # an abstention where the gold gives an interval: covered by nothing, and an IoU of zero
    missed = LS.values(LS.columns([reading("recovery")], [gold("recovery", *april)]), np.ones(1))
    assert missed["interval_coverage"] == 0.0 == missed["interval_iou"]
    assert nothing["abstention_recall"] == 1.0 and nothing["statement_type_accuracy"] == 0.0


def test_kappa_is_the_agreement_scripts_on_the_parsed_readings() -> None:
    cols = case_columns()
    parsed = [(r.certainty, g.reading.certainty) for r, g in CASES if r.parsed]
    assert LS.values(cols, np.ones(8))["certainty_kappa"] == pytest.approx(A.cohen_kappa(parsed))


def test_weights_move_every_metric_as_repeated_items_would() -> None:
    """An item with weight 3 counts as three items: the weighted metrics are those of the list
    with the item written three times."""
    weights = np.array([1, 3, 1, 2, 1, 1, 2, 3], dtype=float)
    cols = case_columns()
    repeated = [pair for pair, k in zip(CASES, weights, strict=True) for _ in range(int(k))]
    marks = [m for m, k in zip(MARKED, weights, strict=True) for _ in range(int(k))]
    longer = LS.columns([r for r, _ in repeated], [g for _, g in repeated], marks)
    found, expected = LS.values(cols, weights), LS.values(longer, np.ones(len(repeated)))
    for name in LS.METRICS:
        assert found[name] == pytest.approx(expected[name]), name
    # a weight of 3 on the one wrong item of the first four: correct falls from 2/8 to 2/10
    assert found["correct"] == pytest.approx(3 / 14)
    assert LS.values(cols, [1, 1, 1, 1, 0, 0, 0, 0])["correct"] == pytest.approx(2 / 4)
    # several rows of weights give several estimates at once
    many = LS.metrics(cols, np.stack([np.ones(8), weights]))
    assert many["correct"].tolist() == pytest.approx([2 / 8, 3 / 14])


def test_stratum_weights_are_frame_sizes_over_scored_items() -> None:
    strata = ["a", "a", "b", "a", "c"]
    weights, scored = LS.stratum_weights(strata, {"a": 12, "b": 5, "c": 1, "d": 9}, "statement")
    assert weights.tolist() == [4, 4, 5, 4, 1] and scored == ["a", "b", "c"]
    assert weights.sum() == 12 + 5 + 1  # the frame of the scored strata, and no other
    with pytest.raises(SystemExit, match=r"refused: the frame holds no template for .*'b'"):
        LS.stratum_weights(strata, {"a": 12, "c": 1}, "template")
    with pytest.raises(SystemExit, match="refused"):
        LS.stratum_weights(strata, {"a": 12, "b": 0, "c": 1}, "template")


def test_item_draws_are_the_registered_cluster_draws() -> None:
    clusters = ["e2", "e1", "e2", "e3", "e1", "e2"]
    taken = LS.item_draws(clusters, draws=50)
    drawn = P.cluster_draws(3, 50, LS.SEED)  # the clusters in sorted order: e1, e2, e3
    assert taken.shape == (50, 6) and LS.SEED == 20261001 and LS.DRAWS == 10_000
    assert (taken[:, 1] == drawn[:, 0]).all() and (taken[:, 4] == drawn[:, 0]).all()
    assert (taken[:, 0] == drawn[:, 1]).all() and (taken[:, 3] == drawn[:, 2]).all()
    assert (drawn.sum(axis=1) == 3).all()  # three clusters are drawn each time
    assert LS.item_draws(clusters).shape == (10_000, 6)
    with pytest.raises(ValueError, match="no cluster"):
        LS.item_draws(["e1", ""])


def test_intervals_are_percentiles_over_draws_of_whole_clusters() -> None:
    cols = case_columns()
    clusters = ["a", "a", "b", "c", "c", "d", "e", "e"]
    base = np.array([2.0, 2, 1, 3, 3, 1, 1, 1])
    taken = LS.item_draws(clusters, draws=400)
    found = LS.estimates(cols, base, taken)
    assert set(found) == set(LS.METRICS)
    assert found["correct"]["value"] == pytest.approx((2 + 3) / 14)
    # the same draws, one at a time: the clusters drawn are written out as a list of items
    drawn = P.cluster_draws(5, 400, LS.SEED)
    members = {
        k: [i for i, c in enumerate(clusters) if c == name] for k, name in enumerate("abcde")
    }
    correct, iou, fc = [], [], []
    for row in drawn:
        picked = [i for k, times in enumerate(row) for _ in range(times) for i in members[k]]
        weight = sum(base[i] for i in picked)
        correct.append(sum(base[i] * cols["correct"][i] for i in picked) / weight)
        dated = sum(base[i] * cols["gold_dated"][i] for i in picked)
        iou.append(sum(base[i] * cols["iou"][i] for i in picked) / dated if dated else np.nan)
        silent = sum(base[i] * cols["gold_abstains"][i] for i in picked)
        fc.append(
            sum(base[i] * cols["false_commitment"][i] for i in picked) / silent
            if silent
            else np.nan
        )
    for name, values in (("correct", correct), ("interval_iou", iou), ("false_commitment", fc)):
        kept = np.array([v for v in values if not np.isnan(v)])
        low, high = np.quantile(kept, [0.025, 0.975])
        assert found[name]["ci95"] == {
            "low": pytest.approx(low),
            "high": pytest.approx(high),
            "draws": len(kept),
        }, name
    # a statistic that some draws leave undefined is taken over the others, and says how many
    assert found["false_commitment"]["ci95"]["draws"] < 400 == found["correct"]["ci95"]["draws"]
    assert LS.interval95(np.array([np.nan, np.nan])) is None
    assert LS.interval95(np.arange(101.0)) == {"low": 2.5, "high": 97.5, "draws": 101}


def test_exact_mcnemar_on_cases_worked_by_hand() -> None:
    def test(only_first: int, only_second: int, both: int = 3, neither: int = 2) -> dict:
        first = [1] * only_first + [0] * only_second + [1] * both + [0] * neither
        second = [0] * only_first + [1] * only_second + [1] * both + [0] * neither
        return LS.mcnemar(first, second)

    found = test(5, 1)
    assert found == {
        "items": 11,
        "first_correct": 8,
        "second_correct": 4,
        "both_correct": 3,
        "neither_correct": 2,
        "only_first_correct": 5,
        "only_second_correct": 1,
        "p": pytest.approx(2 * (1 + 6) / 64),  # twice P(X <= 1) for X of 6 fair coins
    }
    assert test(1, 5)["p"] == found["p"]
    assert test(7, 0)["p"] == pytest.approx(2 / 128)
    assert test(6, 0)["p"] == pytest.approx(2 / 64)
    assert test(7, 3)["p"] == pytest.approx(2 * (1 + 10 + 45 + 120) / 1024)
    assert test(3, 3)["p"] == 1.0 and test(2, 3)["p"] == 1.0  # twice the tail passes 1
    assert test(0, 0)["p"] == 1.0  # no discordant pair
    assert LS.mcnemar([], [])["p"] == 1.0 and LS.mcnemar([], [])["items"] == 0
    for b, c in ((5, 1), (9, 2), (4, 4), (12, 3), (0, 6)):
        assert test(b, c)["p"] == pytest.approx(stats.binomtest(b, b + c, 0.5).pvalue)


def test_holm_over_a_family_and_the_level() -> None:
    tests = [{"p": 0.02}, {"p": 0.04}, {"p": 0.013}]
    found = LS.family(tests)
    # sorted 0.013, 0.02, 0.04: times 3, 2, 1, never below an earlier one
    assert [t["p_holm"] for t in found] == pytest.approx([0.04, 0.04, 0.039])
    assert [t["holds"] for t in found] == [True, True, True]
    found = LS.family([{"p": 0.03}, {"p": 0.025}])
    assert [t["p_holm"] for t in found] == pytest.approx([0.05, 0.05])
    assert [t["holds"] for t in found] == [False, False]  # 0.05 itself does not hold
    assert LS.family([{"p": 0.0249}, {"p": 1.0}])[0]["holds"] is True
    assert LS.ALPHA == 0.05


def test_the_registered_lines_models_and_templates_are_the_run_sheets() -> None:
    sheet = {line.name: line for line in rd.RUN_SHEET}
    for template, line in LS.E2_LINES.items():
        assert sheet[line].template == template and sheet[line].models == LS.E2_MODELS
        assert lp.PARTS[line][0].items == LS.LISTS["e2"]
    assert tuple(LS.E2_LINES) == (V1, FREE) and LS.E2_TEMPLATE == V1 and len(LS.E2_MODELS) == 8
    assert sheet[LS.E5_LINE].template == LS.E5_TEMPLATE == V1
    assert sheet[LS.E5_LINE].models == LS.E5_MODELS and len(LS.E5_MODELS) == 7
    assert "gemini-3.8-flash" not in LS.E5_MODELS and LS.PRIMARIES == (LLAMA, DEEPSEEK)
    assert lp.PARTS[LS.E5_LINE][0].items == LS.LISTS["e5"]
    assert lp.phase_of(sheet["e2-literal"], LLAMA) == lp.phase_of(sheet["e5"], QWEN) == LS.PHASE
    assert LS.FACTORS == MP.FACTORS and len(LS.FACTORS) == 6 and LS.IOU_CORRECT == 0.5
    assert set(LS.NORMALISERS_NOT_RUN) == {"HeidelTime", "SUTime"}


# --------------------------------------------------------------------------------------------
# The GEE and its fallback, on small data
# --------------------------------------------------------------------------------------------


def gee_data(seeds: int = 30) -> SimpleNamespace:
    """Errors of three models on four factor levels (the unedited seed and three factors),
    one item for each seed, level and model, with a seed effect so that clusters matter."""
    rng = np.random.default_rng(7)
    levels, models = ["seed", "certainty", "stale", "silent"], ["m1", "m2", "m3"]
    base = {"seed": 0.25, "certainty": 0.5, "stale": 0.7, "silent": 0.35}
    lift = {"m1": 0.0, "m2": 0.1, "m3": -0.1}
    rows = []
    for s in range(seeds):
        own = rng.normal(0, 0.15)
        for m in models:
            for f in levels:
                p = min(0.95, max(0.05, base[f] + lift[m] + own))
                rows.append((f"s{s:02d}", f, m, float(rng.random() < p)))
    frame = pd.DataFrame(rows, columns=["seed", "factor", "model", "error"])
    return SimpleNamespace(frame=frame, levels=levels, models=models)


def by_cell_means(
    frame: pd.DataFrame, factor: str, model: str, against: str = "seed"
) -> tuple[float, float]:
    """The contrast of a factor against a seed cell in one model, and its cluster-robust
    standard error, from the cell means alone: with a cell for every factor and model the
    logistic fit gives each cell its own mean, the log odds of a cell with mean ``p`` over
    ``n`` items has the influence ``(y - p) / (n p (1 - p))`` on each of its items, and the
    robust variance of a difference of two cells is the sum over seeds of the squared
    difference of their summed influences."""
    mine = frame[frame["model"] == model]
    parts = {}
    for name in (factor, against):
        cell = mine[mine["factor"] == name]
        p, n = cell["error"].mean(), len(cell)
        influence = (cell["error"] - p) / (n * p * (1 - p))
        parts[name] = (np.log(p / (1 - p)), influence.groupby(cell["seed"]).sum())
    seeds = sorted(set(frame["seed"]))
    gap = parts[factor][1].reindex(seeds, fill_value=0) - parts[against][1].reindex(
        seeds, fill_value=0
    )
    return parts[factor][0] - parts[against][0], float(np.sqrt((gap**2).sum()))


def fit_separately(y: np.ndarray, x: np.ndarray, clusters: Sequence[str]) -> tuple[Any, Any]:
    """A logistic fit and its cluster-robust sandwich, written apart from the scorer: the
    coefficients minimise the negative log likelihood (a quasi-Newton search from zero, then
    polished), and the covariance is built one observation and one cluster at a time."""

    def loss(beta: np.ndarray) -> float:
        eta = x @ beta
        return float(np.sum(np.logaddexp(0.0, eta) - y * eta))

    def slope(beta: np.ndarray) -> np.ndarray:
        return x.T @ (1.0 / (1.0 + np.exp(-(x @ beta))) - y)

    start = optimize.minimize(loss, np.zeros(x.shape[1]), jac=slope, method="BFGS")
    beta = optimize.root(slope, start.x, tol=1e-13).x
    width = x.shape[1]
    bread = np.zeros((width, width))
    sums: dict[str, np.ndarray] = {}
    for row, outcome, cluster in zip(x, y, clusters, strict=True):
        p = 1.0 / (1.0 + np.exp(-float(row @ beta)))
        bread += p * (1 - p) * np.outer(row, row)
        sums[cluster] = sums.get(cluster, np.zeros(width)) + row * (outcome - p)
    meat = sum(np.outer(score, score) for score in sums.values())
    inverse = np.linalg.inv(bread)
    return beta, inverse @ meat @ inverse


def fitted(data: SimpleNamespace) -> tuple[dict, list[str]]:
    frame = data.frame
    x, names = LS.design(list(frame["factor"]), list(frame["model"]), data.levels, data.models)
    return LS.gee(frame["error"].to_numpy(), x, list(frame["seed"])), names


def contrast_of(
    names: list[str], factor: str, model: str, first: str, against: str = "seed"
) -> np.ndarray:
    """The weights of the contrast of a factor against a seed cell in one model of the joint
    design, whose reference levels are the cell ``seed`` and the model ``first``."""
    weights = np.zeros(len(names))
    for cell, sign in ((factor, 1.0), (against, -1.0)):
        if cell == "seed":
            continue
        weights[names.index(f"factor[{cell}]")] = sign
        if model != first:
            weights[names.index(f"factor[{cell}]:model[{model}]")] = sign
    return weights


def test_the_design_is_factor_and_model_with_their_interaction() -> None:
    factors = ["seed", "stale", "seed", "silent", "stale"]
    models = ["m1", "m1", "m2", "m2", "m2"]
    x, names = LS.design(factors, models, ["seed", "stale", "silent"], ["m1", "m2"])
    assert names == [
        "intercept",
        "factor[stale]",
        "factor[silent]",
        "model[m2]",
        "factor[stale]:model[m2]",
        "factor[silent]:model[m2]",
    ]
    assert x.tolist() == [
        [1, 0, 0, 0, 0, 0],
        [1, 1, 0, 0, 0, 0],
        [1, 0, 0, 1, 0, 0],
        [1, 0, 1, 1, 0, 1],
        [1, 1, 0, 1, 1, 0],
    ]


def test_the_gee_is_the_logistic_fit_with_the_cluster_sandwich() -> None:
    data = gee_data()
    fit, names = fitted(data)
    assert fit["converged"] and fit["clusters"] == 30 and len(names) == 12
    cells = data.frame.groupby(["factor", "model"])["error"].mean()
    assert cells.between(0.01, 0.99).all()  # no cell without a finite estimate
    # the fitted log odds of every cell are those of its mean
    for (factor, model), p in cells.items():
        weights = contrast_of(names, factor, model, "m1") if factor != "seed" else np.zeros(12)
        weights[0] = 1
        if model != "m1":
            weights[names.index(f"model[{model}]")] = 1
        assert weights @ fit["beta"] == pytest.approx(np.log(p / (1 - p)), abs=1e-8)
    for model in data.models:
        for factor in data.levels[1:]:
            found = LS.wald(fit, contrast_of(names, factor, model, "m1"))
            estimate, se = by_cell_means(data.frame, factor, model)
            assert found["log_odds_difference"] == pytest.approx(estimate, abs=1e-8)
            assert found["se"] == pytest.approx(se, rel=1e-8)
            assert found["z"] == pytest.approx(estimate / se, rel=1e-8)
            assert found["p"] == pytest.approx(2 * stats.norm.sf(abs(estimate / se)), rel=1e-8)
    # a logistic fit and a sandwich written apart from the scorer give the same numbers
    x, _ = LS.design(
        list(data.frame["factor"]), list(data.frame["model"]), data.levels, data.models
    )
    beta, covariance = fit_separately(data.frame["error"].to_numpy(), x, list(data.frame["seed"]))
    assert np.allclose(beta, fit["beta"], atol=1e-7)
    assert np.allclose(covariance, fit["covariance"], rtol=1e-6, atol=1e-9)
    # the covariance is symmetric and the clusters matter: the naive one differs
    assert np.allclose(fit["covariance"], fit["covariance"].T)
    x, _ = LS.design(
        list(data.frame["factor"]), list(data.frame["model"]), data.levels, data.models
    )
    p = 1 / (1 + np.exp(-(x @ fit["beta"])))
    naive = np.linalg.inv(x.T @ (x * (p * (1 - p))[:, None]))
    assert not np.allclose(naive, fit["covariance"], rtol=0.05)
    # every item its own cluster: the sandwich of independent observations
    alone, _ = (
        LS.gee(data.frame["error"].to_numpy(), x, [str(k) for k in range(len(x))]),
        None,
    )
    scores = x * (data.frame["error"].to_numpy() - p)[:, None]
    assert np.allclose(alone["covariance"], naive @ (scores.T @ scores) @ naive)


def test_the_gee_against_statsmodels_when_it_is_installed() -> None:
    sm = pytest.importorskip("statsmodels.api")
    data = gee_data()
    fit, names = fitted(data)
    frame = data.frame
    x, _ = LS.design(list(frame["factor"]), list(frame["model"]), data.levels, data.models)
    order = np.argsort(frame["seed"].to_numpy(), kind="stable")
    model = sm.GEE(
        frame["error"].to_numpy()[order],
        x[order],
        groups=frame["seed"].to_numpy()[order],
        family=sm.families.Binomial(),
        cov_struct=sm.cov_struct.Independence(),
    )
    result = model.fit(maxiter=200, ctol=1e-12, cov_type="robust")
    assert np.allclose(result.params, fit["beta"], atol=1e-6)
    assert np.allclose(result.cov_robust, fit["covariance"], rtol=1e-5, atol=1e-8)
    weights = contrast_of(names, "stale", "m2", "m1")
    test = result.t_test(weights)
    found = LS.wald(fit, weights)
    assert found["z"] == pytest.approx(float(np.squeeze(test.tvalue)), rel=1e-5)
    assert found["p"] == pytest.approx(float(np.squeeze(test.pvalue)), rel=1e-4)


def test_the_gee_says_when_it_cannot_be_computed() -> None:
    data = gee_data()
    frame = data.frame.copy()
    # a cell with no error at all: the fit has no finite coefficients
    frame.loc[(frame["factor"] == "silent") & (frame["model"] == "m3"), "error"] = 0.0
    x, names = LS.design(list(frame["factor"]), list(frame["model"]), data.levels, data.models)
    fit = LS.gee(frame["error"].to_numpy(), x, list(frame["seed"]))
    assert fit["converged"] is False and fit["beta"] is None
    assert LS.wald(fit, contrast_of(names, "stale", "m1", "m1")) is None
    # a column that repeats another: the first step cannot be taken
    twice = np.concatenate([x, x[:, :1]], axis=1)
    fit = LS.gee(data.frame["error"].to_numpy(), twice, list(data.frame["seed"]))
    assert fit["converged"] is False
    # a contrast that weighs nothing has no positive variance
    good, _ = fitted(data)
    assert LS.wald(good, np.zeros(12)) is None


def drawn_gaps(
    error: np.ndarray, edited: np.ndarray, plain: np.ndarray, picked: np.ndarray
) -> tuple[Fraction, list[Fraction]]:
    """The difference of the two error rates (edited minus unedited) on the items as they are,
    and in each draw that holds an item on both sides, one draw at a time and in exact
    fractions. ``picked`` holds how often each item is taken in each draw."""

    def gap(times: np.ndarray) -> Fraction | None:
        n_f, n_s = int(times @ edited), int(times @ plain)
        if not n_f or not n_s:
            return None
        return Fraction(int(times @ (error * edited)), n_f) - Fraction(
            int(times @ (error * plain)), n_s
        )

    whole = gap(np.ones(len(error)))
    assert whole is not None
    return whole, [g for g in map(gap, picked) if g is not None]


def centred(d: Fraction, gaps: Sequence[Fraction]) -> float:
    """The p-value of the fallback as the plan writes it: ``(1 + #{|d* - d| >= |d|}) / (B + 1)``."""
    return (1 + sum(abs(g - d) >= abs(d) for g in gaps)) / (len(gaps) + 1)


def percentile(gaps: Sequence[Fraction]) -> float:
    """The two-sided percentile p-value on the sign of the drawn difference."""
    below = (1 + sum(g <= 0 for g in gaps)) / (len(gaps) + 1)
    above = (1 + sum(g >= 0 for g in gaps)) / (len(gaps) + 1)
    return min(1.0, 2 * min(below, above))


def test_the_bootstrap_contrast_gives_the_centred_p_value_and_the_percentile_one() -> None:
    data = gee_data(9)
    mine = data.frame[data.frame["model"] == "m2"].reset_index(drop=True)
    error = mine["error"].to_numpy()
    edited = (mine["factor"] == "stale").to_numpy().astype(float)
    plain = (mine["factor"] == "seed").to_numpy().astype(float)
    taken = LS.item_draws(list(mine["seed"]), draws=300)
    found = LS.drawn_contrast(error, edited, plain, taken)
    assert set(found) == {"draws", "p", "p_percentile", "ci95"}
    # the same draws, one at a time: each seed as often as it was drawn
    drawn = P.cluster_draws(9, 300, LS.SEED)
    seeds = sorted(set(mine["seed"]))
    gaps = []
    for row in drawn:
        picked = pd.concat(
            [mine[mine["seed"] == seeds[k]] for k, t in enumerate(row) for _ in range(t)]
        )
        rates = picked.groupby("factor")["error"].mean()
        gaps.append(
            Fraction(rates["stale"]).limit_denominator(1000)
            - Fraction(rates["seed"]).limit_denominator(1000)
        )
    d, again = drawn_gaps(error, edited, plain, taken)
    assert again == gaps and d == Fraction(int(error @ edited) - int(error @ plain), 9)
    assert found["draws"] == 300
    assert found["p"] == pytest.approx(centred(d, gaps))
    assert found["p_percentile"] == pytest.approx(percentile(gaps))
    assert found["p"] != pytest.approx(found["p_percentile"])  # two numbers, each under its name
    low, high = np.quantile([float(g) for g in gaps], [0.025, 0.975])
    assert found["ci95"] == {"low": pytest.approx(low), "high": pytest.approx(high), "draws": 300}
    assert any(g == 0 for g in gaps)  # draws of equal rates exist, and count on both sides
    # the edited items never err and the seed items always do: every draw gives the difference
    # itself, so none is as far from it as it is from zero, and every one is below zero
    sure = LS.drawn_contrast(plain, edited, plain, taken)
    assert sure["p"] == pytest.approx(1 / 301) and sure["p_percentile"] == pytest.approx(2 / 301)
    assert sure["ci95"]["high"] == -1.0
    # no difference between the two rates: every draw is at least as far, and p = 1
    same = LS.drawn_contrast(np.ones(len(error)), edited, plain, taken)
    assert same["p"] == 1.0 and same["p_percentile"] == 1.0
    # a side with no item in a draw leaves the draw out, and B is the number of draws left
    one = np.zeros(len(error))
    one[0] = 1.0
    part = LS.drawn_contrast(error, one, plain, taken)
    assert part["draws"] == int((drawn[:, 0] > 0).sum()) < 300
    d, gaps = drawn_gaps(error, one, plain, taken)
    assert len(gaps) == part["draws"] and part["p"] == pytest.approx(centred(d, gaps))
    assert part["p_percentile"] == pytest.approx(percentile(gaps))
    assert LS.drawn_contrast(error, np.zeros(len(error)), plain, taken) == {
        "draws": 0,
        "p": 1.0,
        "p_percentile": 1.0,
        "ci95": None,
    }


def test_the_centred_p_value_counts_a_draw_exactly_as_far_as_the_difference() -> None:
    """``|d* - d| >= |d|`` holds with equality when a draw gives no difference at all, or twice
    the difference seen. Such draws are common, and they count: the comparison is made on
    whole numbers, where a division would put some of them on the wrong side."""
    # one seed errs on its edited item and no unedited item errs: d = 1/8, and a draw gives
    # d* = k/8 when it takes that seed k times
    seeds = [f"S{s}" for s in range(8) for _ in range(2)]
    edited = np.array([1.0, 0.0] * 8)
    plain = 1 - edited
    error = np.zeros(16)
    error[6] = 1.0
    taken = LS.item_draws(seeds, draws=400)
    times = P.cluster_draws(8, 400, LS.SEED)[:, 3]
    found = LS.drawn_contrast(error, edited, plain, taken)
    assert int((times == 2).sum()) > 30 and int((times == 0).sum()) > 100
    assert found["p"] == pytest.approx((1 + int(((times == 0) | (times >= 2)).sum())) / 401)
    assert found["p_percentile"] == pytest.approx(min(1.0, 2 * (1 + int((times == 0).sum())) / 401))
    # the sign of the difference does not matter: the two sides the other way round
    turned = LS.drawn_contrast(error, plain, edited, taken)
    assert turned["p"] == found["p"] and turned["p_percentile"] == found["p_percentile"]
    assert turned["ci95"]["low"] == -found["ci95"]["high"] < 0 == turned["ci95"]["high"]
    # rates over other numbers of items in every draw: ten seeds, each with one edited and one
    # unedited item, and errors on both sides
    seeds = [f"S{s}" for s in range(10) for _ in range(2)]
    edited = np.array([1.0, 0.0] * 10)
    plain = 1 - edited
    taken = LS.item_draws(seeds, draws=300)
    rng = np.random.default_rng(11)
    ties = 0
    for _ in range(40):
        error = (rng.random(20) < 0.3).astype(float)
        d, gaps = drawn_gaps(error, edited, plain, taken)
        found = LS.drawn_contrast(error, edited, plain, taken)
        assert found["p"] == pytest.approx(centred(d, gaps), abs=1e-12)
        assert found["p_percentile"] == pytest.approx(percentile(gaps), abs=1e-12)
        ties += sum(abs(g - d) == abs(d) for g in gaps if d)
    assert ties > 1000


def test_an_error_is_the_e2_rule_plus_the_factors_own_field() -> None:
    april = ("2020-04-01", "2020-04-30")
    theirs = gold("recovery", *april, "estimated")
    answers = [
        reading("recovery", *april, "estimated"),  # right
        reading("recovery", *april, "asserted"),  # the certainty wrong
        reading("recovery", *april, "estimated", stale=True),  # the stale flag wrong
        reading("recovery", "2021-04-01", "2021-04-30", "estimated"),  # not correct
    ]
    cols = LS.columns(answers, [theirs] * 4)
    expected = {
        "seed": [0, 0, 0, 1],
        "certainty": [0, 1, 0, 1],
        "stale": [0, 0, 1, 1],
        "surface_form": [0, 0, 0, 1],
        "granularity": [0, 0, 0, 1],
        "distractor": [0, 0, 0, 1],
        "silent": [0, 0, 0, 1],
    }
    for factor, errors in expected.items():
        flags = LS.error_flags(cols, [factor] * 4)
        assert flags["error"].astype(int).tolist() == errors, factor
        assert flags["not_correct"].astype(int).tolist() == [0, 0, 0, 1]
        assert flags["certainty_wrong"].astype(int).tolist() == [0, 1, 0, 0]
        assert flags["stale_wrong"].astype(int).tolist() == [0, 0, 1, 0]
        # what an unedited seed item is held to in the contrast of the certainty factor, and of
        # the stale factor: the same readings, whatever the factor of the item
        assert set(flags) == {
            "error",
            "not_correct",
            "certainty_wrong",
            "stale_wrong",
            "seed|certainty",
            "seed|stale",
        }
        assert flags["seed|certainty"].astype(int).tolist() == expected["certainty"]
        assert flags["seed|stale"].astype(int).tolist() == expected["stale"]
        # the criterion of the seed cell a factor is compared with is that factor's own
        cell = LS.seed_cell(factor)
        assert LS.held_to(flags, cell).astype(int).tolist() == errors, factor
    assert LS.OWN_FIELD == {"certainty": "certainty_wrong", "stale": "stale_wrong"}
    assert LS.SEED_ROWS == {"certainty": "seed|certainty", "stale": "seed|stale"}
    assert LS.SEED_CELLS == ("seed", "seed|certainty", "seed|stale")
    assert [LS.seed_cell(f) for f in PAIR_FACTORS] == [
        "seed",
        "seed|certainty",
        "seed",
        "seed",
        "seed|stale",
        "seed",
        "seed",
    ]
    # a reading that was not parsed is an error on every factor
    lost = LS.columns([LS.NO_ANSWER], [gold("none", certainty="no_statement")])
    assert LS.error_flags(lost, ["silent"])["error"].tolist() == [True]


def test_an_unedited_item_enters_once_under_each_of_the_three_criteria() -> None:
    """The rows of one reader: every item under its factor, then each unedited seed item again
    under the criterion of the certainty factor, and again under that of the stale factor."""
    factors = ["seed", "certainty", "stale", "seed", "silent"]
    item, level = LS.long_table(factors)
    assert item.tolist() == [0, 1, 2, 3, 4, 0, 3, 0, 3]
    assert level.tolist() == [
        *factors,
        "seed|certainty",
        "seed|certainty",
        "seed|stale",
        "seed|stale",
    ]
    april = ("2020-04-01", "2020-04-30")
    theirs = gold("recovery", *april, "estimated")
    answers = [
        reading("recovery", *april, "asserted"),  # an unedited item with the certainty wrong
        reading("recovery", *april, "asserted"),  # the same on the certainty item
        reading("recovery", *april, "asserted"),  # and on the stale item, where it is no error
        reading("recovery", *april, "estimated", stale=True),  # unedited, the stale flag wrong
        reading("depletion", *april, "estimated"),  # not correct
    ]
    flags = LS.error_flags(LS.columns(answers, [theirs] * 5), factors)
    assert flags["error"].astype(int).tolist() == [0, 1, 0, 0, 1]
    assert LS.long_outcome(flags, item, level).tolist() == [0, 1, 0, 0, 1, 1, 0, 0, 1]
    # no unedited item: nothing is added
    item, level = LS.long_table(["stale", "silent"])
    assert item.tolist() == [0, 1] and level.tolist() == ["stale", "silent"]


# --------------------------------------------------------------------------------------------
# The made-up study: events, guide, sheets, gold, minimal pairs, plan and runs
# --------------------------------------------------------------------------------------------

ROWS = (
    ("month and year", "`month_year`"),
    ("month with no year", "`month_no_year`"),
    ("part of a month", "`part_of_month`"),
    ("quarter, half or year", "`quarter`, `half_year`, `year`"),
    ("range", "`range`"),
    ("relative", "`relative`"),
    ("exact day", "`exact_day`"),
    ("TBD or unknown", "`tbd`"),
    ("vague", "`vague`"),
    ("undated", "`no_date`"),
    ("silent", "`silent`"),
    ("distractor only", "`distractor`; `tbd`, `vague`, `no_date`, `silent` with a distractor date"),
    (
        "dated target beside a distractor date",
        "`month_year`, `month_no_year`, `part_of_month`, `quarter`, `half_year`, `year`, "
        "`range`, `relative`, `exact_day` with a distractor date",
    ),
    ("discontinuation", "`discontinuation`"),
)
GUIDE = "\n".join(
    [
        "# Guide",
        "",
        "**Version v9 test, 1 January 2000.** A made-up guide.",
        "",
        "| Stratum | Classifier classes | Pilot | Check set | Reserve | Literal sample |",
        "|---|---|---|---|---|---|",
        *(f"| {label} | {classes} | | | | 2 |" for label, classes in ROWS),
        "",
        "## Appendix A. Statements excluded from every sample",
        "",
        "| Generic | Company | Statement date |",
        "|---|---|---|",
        f"| Examplamine 31 Injection | Acme Pharma, Inc. | {DAY} |",
        "",
    ]
)
EXPIRY = "5 month expiry (1/2022 expiry) dating available by request."
UNTIL_APRIL = "Remaining inventory estimated to last until April 2020"
TEXTS = {
    # the sample: items 1 to 24
    1: "Backordered. Next release April 2020.",
    2: "Unavailable, recovery in May 2020",
    3: "Estimated Recovery: December 2020",
    4: "Backordered. Next release January 2020.",
    5: "Backorder - product availability ETA late August 2020",
    6: "Next release mid-October 2020.",
    7: "Next shipment anticipated end of June 2020",
    8: "Backordered, next shipment in November.",
    9: "Next release December.",
    10: "Additional lots are scheduled for release in the March/April 2020 timeframe.",
    11: "Estimated availability in 4Q 2020 to 1Q 2021",
    12: "Unavailable. Estimated recovery TBD.",
    13: "Next release date not available at this time.",
    14: "Shortage duration is unknown at this time.",
    15: "On backorder.",
    16: "Check wholesalers for inventory.",
    17: "Currently unavailable.",
    18: f"{EXPIRY} Next release June 2020.",
    19: f"{UNTIL_APRIL}. Estimated recovery: July 2020.",
    20: "Remaining inventory estimated to last until May 2020.",
    21: f"{EXPIRY} Next release date not available at this time.",
    22: "Will remain on backorder for few months.",
    23: "Estimated Availability: June 5, 2020",
    24: "To be discontinued on or near March 2021.",
    # the rest of the frame
    25: "Recovery June 2020",
    26: "Backordered. Next release May 2020.",
    27: "Backordered. Next release July 2020.",
    28: "Backordered. Next release August 2020.",
    29: "Unavailable. Estimated recovery TBD.",
    30: "Unavailable. Estimated recovery TBD.",
    31: "On backorder.",  # excluded by the guide's Appendix A
    32: "On backorder.",  # Resolved when first seen: not in the frame
    33: "Recovery: to be determined.",
}
SAMPLE = tuple(range(1, 25))
STRATA = {
    **dict.fromkeys((1, 2, 3, 4), "month_year"),
    **dict.fromkeys((5, 6, 7), "part_of_month"),
    **dict.fromkeys((8, 9), "month_no_year"),
    **dict.fromkeys((10, 11), "range"),
    **dict.fromkeys((12, 13, 14), "tbd"),
    **dict.fromkeys((15, 16, 17), "silent"),
    **dict.fromkeys((18, 19), "dated_distractor"),
    **dict.fromkeys((20, 21), "distractor"),
    22: "vague",
    23: "exact_day",
    24: "discontinuation",
}
# the frame without the excluded statement: statements and distinct masked templates
FRAME = {
    "month_year": (8, 4),  # 1 to 4 and 25 to 28; 1, 4, 26, 27 and 28 share a template
    "part_of_month": (3, 3),
    "month_no_year": (2, 2),
    "range": (2, 2),
    "tbd": (6, 4),  # 12 to 14, 29, 30 and 33; 12, 29 and 30 share a template
    "silent": (3, 3),  # 31 is excluded, 32 is not in the frame
    "dated_distractor": (2, 2),
    "distractor": (2, 2),
    "vague": (1, 1),
    "exact_day": (1, 1),
    "discontinuation": (1, 1),
}
EPISODES = {2: 1, 13: 12}  # items 1 and 2 share an episode, and items 12 and 13


def event(n: int) -> dict[str, str]:
    return {
        "event_id": f"E{n:05d}",
        "statement_group_id": f"S{n:05d}",
        "thread_id": f"T{n:05d}",
        "generic_id": f"g{n:05d}",
        "episode_id": f"P{EPISODES.get(n, n):05d}",
        "listing": "shortage",
        "event_date": DAY,
        "type_of_update": "revised",
        "generic_name": f"Examplamine {n} Injection",
        "company_name": "Acme Pharma, Inc.",
        "presentation": f"10 mg vial (NDC 0000-{n:04d}-01)",
        "status_at_statement": "resolved" if n == 32 else "current",
        "availability_class": "limited",
        "availability_text": TEXTS[n],
        "related_text": "",
        "statement_text": TEXTS[n],
        "reason_for_shortage": "Other",
        "therapeutic_category": "Oncology",
        "initial_posting_date": "01/15/2019",
    }


def lab(
    kind: str,
    start: str = "",
    end: str = "",
    certainty: str = "asserted",
    reason: str = "",
    roles: str = "",
    quotes: str = "",
) -> dict[str, str]:
    return {
        "statement_type": kind,
        "start": start,
        "end": end,
        "abstain": "0" if start else "1",
        "abstain_reason": reason,
        "certainty": certainty,
        "quote": "",
        "distractor_roles": roles,
        "distractor_quotes": quotes,
        "hard": "0",
        "note": "",
    }


TBD = {"certainty": "undetermined", "reason": "tbd"}
NONE = lab("none", certainty="no_statement", reason="no_statement")
# what A1 enters. Seven labels leave the rule reading on purpose (7, 8, 10, 11, 13, 23, 24), so
# that the rule reader is wrong on seven items outside the month-and-year stratum
TRUTH = {
    1: lab("next_delivery", "2020-04-01", "2020-04-30"),
    2: lab("recovery", "2020-05-01", "2020-05-31"),
    3: lab("recovery", "2020-12-01", "2020-12-31", "estimated"),
    4: lab("next_delivery", "2020-01-01", "2020-01-31"),  # stale
    5: lab("recovery", "2020-08-21", "2020-08-31", "estimated"),
    6: lab("next_delivery", "2020-10-11", "2020-10-20"),
    7: lab("next_delivery", "2020-06-01", "2020-06-30", "estimated"),  # rules: 21 to 30
    8: lab("next_delivery", "2021-11-01", "2021-11-30"),  # rules: November 2020
    9: lab("next_delivery", "2020-12-01", "2020-12-31"),
    10: lab("next_delivery", "2020-04-01", "2020-04-30"),  # rules: March and April
    11: lab("recovery", "2021-01-01", "2021-03-31", "estimated"),  # rules: from October 2020
    12: lab("recovery", **TBD),
    13: lab("recovery", **TBD),  # rules: next_delivery
    14: lab("recovery", **TBD),
    15: NONE,
    16: NONE,
    17: NONE,
    18: lab("next_delivery", "2020-06-01", "2020-06-30", roles="expiry", quotes="(1/2022 expiry)"),
    19: lab(
        "recovery", "2020-07-01", "2020-07-31", "estimated", roles="depletion", quotes=UNTIL_APRIL
    ),
    20: lab("depletion", "2020-05-01", "2020-05-31", "estimated"),
    21: lab("next_delivery", **TBD, roles="expiry", quotes="(1/2022 expiry)"),
    22: lab("recovery", certainty="estimated", reason="vague"),
    23: lab("recovery", "2020-06-01", "2020-06-30", "estimated"),  # rules: 5 June
    24: lab("discontinuation", "2022-03-01", "2022-03-31", "estimated"),  # rules: March 2021
}
RULES_WRONG = (7, 8, 10, 11, 13, 23, 24)
# where A2 differs from A1, and what the adjudicator does about it
SECOND = {
    3: TRUTH[3] | {"certainty": "asserted"},  # slip: A1's label
    6: TRUTH[6] | {"start": "2020-10-01", "end": "2020-10-31"},  # slip: A1's label
    10: TRUTH[10] | {"start": "2020-03-01"},  # gap, decided as A1 has it
    22: TRUTH[22] | {"abstain_reason": "no_date", "certainty": "undetermined"},  # gap, unsettled
    11: TRUTH[11] | {"hard": "1", "note": "the range crosses the year"},  # no difference
}
GAP_ITEM, LEFT_OUT, CONVENTION_ITEMS = 10, 22, (8, 9)
GOLD = tuple(n for n in SAMPLE if n != LEFT_OUT)


def number_of(row: Mapping[str, str]) -> int:
    return int(NDC.search(row["presentation"]).group(2))  # type: ignore[union-attr]


def fill(blank: str, labels: Mapping[int, dict[str, str]]) -> str:
    meta, rows = S.parse_sheet(blank)
    times = {"sitting_start": "09:00", "sitting_end": "09:40"}
    meta = [(key, times.get(key, value)) for key, value in meta]
    return S.sheet_text(S.SHEET_COLUMNS, [row | labels[number_of(row)] for row in rows], meta)


def answer(model: str, template: str, n: int) -> dict[str, Any] | None:
    """The scripted reading of sample item ``n`` (None: no answer that parses)."""
    label = dict(TRUTH[n])
    stale = bool(label["end"]) and label["end"] < DAY

    def dated(start: str, end: str) -> None:
        label.update(start=start, end=end)

    if template == FREE and n in (5, 6):  # the convention-free prompt reads the whole month
        dated(label["start"][:8] + "01", label["start"][:8] + "31")
    elif template == FREE:
        pass
    elif model == LLAMA:
        if n == 12:  # a date where the entry says TBD
            dated("2020-06-01", "2020-06-30")
        if n == 18:  # the expiry date in place of the release
            dated("2022-01-01", "2022-01-31")
        if n == 5:
            label["statement_type"] = "next_delivery"
    elif model == DEEPSEEK:
        if n == 4:
            stale = False
        if n == 2:
            label["certainty"] = "estimated"
    elif model == QWEN:
        if n == 16:
            return None
    elif model == GEMMA:
        if n in (12, 13, 14, 15):
            dated("2020-06-01", "2020-06-30")
            label["statement_type"] = "recovery"
            label["certainty"] = "estimated"
    elif model == OSS:
        if n in (18, 21):
            dated("2022-01-01", "2022-01-31")
        if n == 19:
            dated("2020-04-01", "2020-04-30")
    elif model == MINI:
        stale = n in (1, 2)
    elif model == GEMINI and label["start"]:
        label["certainty"] = "estimated"
    interval: Any = {"start": label["start"], "end": label["end"]} if label["start"] else "ABSTAIN"
    return {
        "statement_type": label["statement_type"],
        "interval": interval,
        "certainty": label["certainty"],
        "stale": stale,
        "quote": "",
    }


def fails(model: str, template: str, n: int) -> int:
    """How many attempts come back unparsable: 2 (failed), 1 (repaired), 0."""
    if model == QWEN and template == V1:
        return {2: 2, 3: 1}.get(n, 0)
    return 0


# ---- the minimal pairs -----------------------------------------------------------------------

PAIR_SEEDS = 12
PAIR_FACTORS = ("seed", *MP.FACTORS)
PAIR_LEVELS = {
    "seed": "unedited",
    "certainty": "expected",
    "surface_form": "no_year",
    "granularity": "mid",
    "stale": "stale",
    "distractor": "expiry",
    "silent": "silent",
}
# for each model and factor, how many of the twelve seeds it errs on (the seeds are taken in
# turn, from another start for each model and factor)
ERRS = {
    LLAMA: (2, 6, 3, 4, 9, 5, 1),
    DEEPSEEK: (1, 4, 3, 2, 5, 11, 2),
    QWEN: (5, 7, 6, 6, 8, 9, 4),
    GEMMA: (4, 5, 5, 3, 7, 6, 3),
    OSS: (3, 6, 4, 5, 6, 7, 5),
    MINI: (2, 3, 2, 4, 4, 5, 2),
    GROK: (1, 2, 3, 2, 3, 4, 1),
}


def pair_number(seed: int, factor: str) -> int:
    return 10 * seed + PAIR_FACTORS.index(factor)


def pair_gold(factor: str) -> MP.Gold:
    """The gold of an item by construction: the seed reads next delivery, October 2020."""
    whole = MP.Gold("next_delivery", "2020-10-01", "2020-10-31", "", "asserted")
    if factor == "certainty":
        return MP.Gold("next_delivery", "2020-10-01", "2020-10-31", "", "estimated")
    if factor == "granularity":
        return MP.Gold("next_delivery", "2020-10-11", "2020-10-20", "", "asserted")
    if factor == "stale":
        return MP.Gold("next_delivery", "2020-10-01", "2020-10-31", "", "asserted", stale=True)
    if factor == "distractor":
        return MP.Gold(
            "next_delivery",
            "2020-10-01",
            "2020-10-31",
            "",
            "asserted",
            distractor_roles=("expiry",),
            distractor_quotes=("(expiry 12/31/2020)",),
        )
    if factor == "silent":
        return MP.Gold("none", abstain_reason="no_statement", certainty="no_statement")
    return whole


PAIR_TEXT = {
    "seed": "Backordered. Next release October 2020.",
    "certainty": "Backordered. Next release expected October 2020.",
    "surface_form": "Backordered. Next release October.",
    "granularity": "Backordered. Next release mid-October 2020.",
    "stale": "Backordered. Next release October 2020.",
    "distractor": "4 months dating available by request (expiry 12/31/2020). Backordered. "
    "Next release October 2020.",
    "silent": "Backordered.",
}


def pair_items() -> list[MP.Item]:
    items = []
    for s in range(PAIR_SEEDS):
        period = "test" if s >= 10 else "train"

        def fields(factor: str, s: int = s) -> dict[str, str]:
            return {
                "generic_name": f"Zorvamine {s}",
                "company_name": "Belcor Pharma",
                "presentation": f"10 mg vial (NDC 1111-{pair_number(s, factor):04d}-01)",
                "therapeutic_category": "Oncology",
                "initial_posting_date": "2019-05-03",
                "date_of_update": "2020-11-16" if factor == "stale" else "2020-08-13",
                "type_of_update": "Reverified" if factor == "stale" else "Revised",
                "availability_information": PAIR_TEXT[factor],
                "related_information": "",
                "reason_for_shortage": "Other",
            }

        seed = MP.Seed(
            seed_id=f"S{s:02d}",
            event_id=f"E{s:02d}",
            period=period,
            form="month_year",
            fields=fields("seed"),
            gold=pair_gold("seed"),
            name="availability_information",
            span=(0, 0),
            bound="",
            no_year=False,
            time=None,
            written=None,
            mentions=(),
        )
        items.append(MP.Item(MP.item_id(seed.seed_id, "seed", "unedited"), seed, None))
        for factor in MP.FACTORS:
            edit = MP.Edit(factor, PAIR_LEVELS[factor], fields(factor), pair_gold(factor))
            items.append(MP.Item(MP.item_id(seed.seed_id, factor, edit.level), seed, edit))
    return items


def pair_errs(model: str, seed: int, factor: str) -> bool:
    k = PAIR_FACTORS.index(factor)
    return (seed + 5 * k + 3 * list(ERRS).index(model)) % PAIR_SEEDS < ERRS[model][k]


def seed_errs(model: str, seed: int, factor: str = "seed") -> bool:
    """Whether the scripted reading of the unedited item of a seed is an error when it is
    compared with the items of a factor: not correct by the E2 rule, or wrong in the field that
    the criterion of the certainty factor, or of the stale factor, adds."""
    own = {"certainty": seed % 4 == 1, "stale": seed % 6 == 2}
    return pair_errs(model, seed, "seed") or own.get(factor, False)


def pair_answer(model: str, seed: int, factor: str) -> dict[str, Any]:
    """The scripted reading of a minimal pair: the gold, made wrong in the factor's own way
    when the model errs on it. Some answers are wrong in a field that is no error there, and
    some unedited items in a field that is an error in one contrast alone."""
    theirs = pair_gold(factor)
    kind, certainty, stale = theirs.statement_type, theirs.certainty, theirs.stale
    start, end = theirs.start, theirs.end
    if pair_errs(model, seed, factor):
        if factor == "certainty":
            certainty = "asserted"
        elif factor == "stale":
            stale = False
        elif factor == "silent":
            kind, certainty = "recovery", "undetermined"
        elif factor == "distractor":
            start, end = "2020-12-31", "2020-12-31"
        else:
            start, end = "2021-10-01", "2021-10-31"
    elif factor == "surface_form" and seed % 2:
        certainty = "estimated"  # wrong, and no error outside the certainty factor
    elif factor == "granularity" and seed % 3 == 0:
        stale = True  # wrong, and no error outside the stale factor
    elif factor == "seed" and seed % 4 == 1:
        certainty = "estimated"  # wrong: an error of the unedited item in the certainty contrast
    elif factor == "seed" and seed % 6 == 2:
        stale = True  # wrong: an error of the unedited item in the stale contrast
    interval: Any = {"start": start, "end": end} if start else "ABSTAIN"
    return {
        "statement_type": kind,
        "interval": interval,
        "certainty": certainty,
        "stale": stale,
        "quote": "",
    }


# ---- runs ------------------------------------------------------------------------------------


class ScriptedSDK:
    """Stands in for the SDK client inside the harness's own client: it echoes the model it was
    asked for, names the provider it is given, and answers with ``reply(prompt)``; an empty
    answer uses no token (a refusal)."""

    def __init__(self, reply: Callable[[str], str], provider: str) -> None:
        self.reply = reply
        self.provider = provider
        self.chat = self.completions = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        text = self.reply(kwargs["messages"][-1]["content"])
        used = (500, 60, 560) if text else (0, 0, 0)
        return SimpleNamespace(
            model=kwargs["model"],
            provider=self.provider,
            openrouter_metadata=None,
            usage=SimpleNamespace(
                prompt_tokens=used[0], completion_tokens=used[1], total_tokens=used[2]
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        )


def make_run(plan: dict, run: dict, reply: Callable[[str], str], local: Path) -> None:
    """One run of the plan, read by the harness's reader around the scripted client and written
    by ``read.write_run`` with the fields the harness's command line adds to the manifest."""
    model, out_dir = run["model"], Path(plan["options"]["out_root"]) / run["run"]
    every = rd.load_items(Path(run["items"]))
    route = rd.ROUTES[model]
    sdk = ScriptedSDK(reply, route.provider.split("/")[0])
    client = rd.RouteCheckedClient(
        rd.route_endpoint(model), rd.served_as(model), route=route, sdk=sdk
    )
    endpoint, transport = rd.build_transport(
        model,
        spend_log=out_dir / "spend_log.jsonl",
        spend_cap_usd=1000.0,
        max_physical_calls=10**6,
        inner=client,
    )
    reader = rd.Reader(
        model=model,
        template=rd.TEMPLATES[run["template"]],
        endpoint=endpoint,
        transport=transport,
        cache=rd.ReadCache(local / "cache"),
        decoding=rd.decoding_for(run["temperature"]),
        track=None,
        route=route,
    )
    rows, status = rd.read_items(reader, every, samples=run["samples"])
    meta = {
        "run_name": run["run"],
        "status": status,
        "items_sha256": hashlib.sha256(Path(run["items"]).read_bytes()).hexdigest(),
        "items_in_file": len(every),
        "limit": run["limit"],
        "samples": run["samples"],
        "spend_cap_usd": run["cap_usd"],
        "shard": run["shard"],
        "temperature": run["temperature"],
        "mask_names": run["mask_names"],
        "shift_years": run["shift_years"],
    }
    rd.write_run(
        rows,
        reader,
        out_dir=out_dir,
        local_dir=local / run["run"],
        meta=meta,
        items=every,
        samples=1,
    )


def reply_for(model: str, template: str) -> Callable[[str], str]:
    def reply(prompt: str) -> str:
        kind, digits = NDC.search(prompt).groups()  # type: ignore[union-attr]
        attempt = int("Your previous reply was:" in prompt)
        if kind == "1111":
            seed, k = divmod(int(digits), 10)
            return json.dumps(pair_answer(model, seed, PAIR_FACTORS[k]))
        n = int(digits)
        found = answer(model, template, n)
        if found is None:
            return ""
        return GARBAGE if attempt < fails(model, template, n) else json.dumps(found)

    return reply


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_study(root: Path, template_of: Mapping[str, str] | None = None) -> SimpleNamespace:
    """The made-up study on disk. ``template_of`` plans a line under another template than the
    run sheet's (for the refusal of such a plan)."""
    audit, work, keys = root / "audit", root / "work", root / "keys"
    items_dir, runs, local, pairs = root / "items", root / "read", root / "local", root / "e5"
    for folder in (audit / S.KEYS_DIR, work, keys, items_dir, runs, local, pairs):
        folder.mkdir(parents=True)
    events = pd.DataFrame([event(n) for n in TEXTS], dtype=str)
    events_path, guide_path = root / "events.csv", root / "guide.md"
    events.to_csv(events_path, index=False)
    guide_path.write_text(GUIDE, encoding="utf-8")

    # E2: sheets, items and key by the sampler; labels; agreement; adjudication; gold
    table = S.statement_table(events, S.guide_allocation(GUIDE))
    sheets = S.build_sheets("literal", [f"S{n:05d}" for n in SAMPLE], events, table, GUIDE)
    for name, text in sheets.files.items():
        (audit / name).write_text(text, encoding="utf-8")
    (audit / S.KEYS_DIR / "literal_key.csv").write_text(sheets.key, encoding="utf-8")
    filled = {}
    for annotator, labels in (("A1", TRUTH), ("A2", TRUTH | SECOND)):
        filled[annotator] = work / f"literal_{annotator}.csv"
        blank = (audit / f"literal_{annotator}.csv").read_text(encoding="utf-8")
        filled[annotator].write_text(fill(blank, labels), encoding="utf-8")
    agree = ["agree", "--task", "literal", "--dir", str(audit), "--keys", str(audit / S.KEYS_DIR)]
    assert A.main([*agree, "--a1", str(filled["A1"]), "--a2", str(filled["A2"])]) == 0
    meta, rows = S.read_sheet(audit / A.ADJUDICATION)
    assert sorted(number_of(row) for row in rows) == [3, 6, 10, 22]
    decided = []
    for row in rows:
        n = number_of(row)
        entered = {} if n == LEFT_OUT else {c: row[f"A1_{c}"] for c in S.ENTERED}
        decision = "gap" if n in (GAP_ITEM, LEFT_OUT) else "slip"
        decided.append(row | entered | {"adj_decision": decision, "adj_note": f"note {n}"})
    adjudicated = work / "adjudicated.csv"
    adjudicated.write_text(S.sheet_text(A.ADJUDICATION_COLUMNS, decided, meta), encoding="utf-8")
    assert A.main(["gold", "--dir", str(audit), "--adjudication", str(adjudicated)]) == 0
    literal = [
        json.loads(line) for line in (audit / "literal_items.jsonl").read_text().splitlines()
    ]
    ids = {number_of(item): item["item_id"] for item in literal}
    shutil.copy(audit / "literal_items.jsonl", items_dir / "literal_items.jsonl")
    marks = audit / LS.E2_CONVENTION_ITEMS
    marks.write_text("item_id\n" + "".join(f"{ids[n]}\n" for n in CONVENTION_ITEMS))

    # E5: items and gold by the generator's own row writers
    made = pair_items()
    (pairs / MP.ITEMS_FILE).write_text(
        "".join(json.dumps(item.record(), ensure_ascii=False) + "\n" for item in made)
    )
    (keys / MP.GOLD_FILE).write_text(
        MP.plain_csv(MP.GOLD_COLUMNS, (item.gold_row() for item in made))
    )
    shutil.copy(pairs / MP.ITEMS_FILE, items_dir / MP.ITEMS_FILE)
    pair_ids = {(int(item.seed.seed_id[1:]), item.factor): item.item_id for item in made}

    # the plan and the runs
    options = lp.default_options(items_dir)
    options |= {"out_root": str(runs), "local_root": str(local)}
    options["counts"] = dict.fromkeys(("e3", "tbd", "silent", "stale", "dev"), 50)
    plan = lp.make_plan(options)
    for run in plan["runs"]:
        if template_of and run["line"] in template_of:
            run["template"] = template_of[run["line"]]
    lp.plan_path(runs).parent.mkdir(parents=True)
    lp.plan_path(runs).write_text(lp.plan_text(plan), encoding="utf-8")
    for run in plan["runs"]:
        if run["list"] in ("e2", "e5"):
            make_run(plan, run, reply_for(run["model"], run["template"]), local)
    return SimpleNamespace(
        root=root,
        audit=audit,
        runs=runs,
        local=local,
        plan=plan,
        events=events_path,
        guide=guide_path,
        gold=audit / A.GOLD,
        marks=marks,
        ids=ids,
        items={item["item_id"]: item for item in literal},
        e5_items=pairs / MP.ITEMS_FILE,
        e5_gold=keys / MP.GOLD_FILE,
        pair_ids=pair_ids,
        pairs=made,
    )


@pytest.fixture(scope="module")
def study(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    patch = pytest.MonkeyPatch()
    guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        yield build_study(tmp_path_factory.mktemp("study"))
    finally:
        patch.undo()


def listed(command: str, options: dict[str, Any], gold: Path, replace: Mapping[str, Any]) -> list:
    """The arguments of a command; the hash of the gold file is its own unless one is given."""
    options |= {f"--{name.replace('_', '-')}": value for name, value in replace.items()}
    if "--expect-gold-sha256" not in options:
        named = Path(options.get("--gold", gold))
        options["--expect-gold-sha256"] = sha(named) if named.is_file() else "0" * 64
    parts = [(name, value) for name, value in options.items() if value is not None]
    return [command, *(str(part) for pair in parts for part in pair)]


def e2_args(study: SimpleNamespace, out: Path, *extra: str, **replace: Any) -> list[str]:
    """The hash of the list of convention items is that of the study's own list unless one is
    given (``expect_convention_sha256=None`` gives none)."""
    options = {
        "--audit-dir": study.audit,
        "--events": study.events,
        "--guide": study.guide,
        "--out-root": study.runs,
        "--out": out,
    }
    if "--expect-convention-sha256" not in extra:
        known = study.marks.is_file()
        options["--expect-convention-sha256"] = sha(study.marks) if known else "0" * 64
    return [*listed("e2", options, study.gold, replace), *extra]


def e5_args(study: SimpleNamespace, out: Path, *extra: str, **replace: Any) -> list[str]:
    options = {
        "--gold": study.e5_gold,
        "--items": study.e5_items,
        "--out-root": study.runs,
        "--out": out,
    }
    return [*listed("e5", options, study.e5_gold, replace), *extra]


ARGS = {"e2": e2_args, "e5": e5_args}


def fresh(tmp_path: Path, name: str = "results") -> Path:
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    return folder / f"scores_{len(list(folder.iterdir()))}.json"


def scored(
    command: str,
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    **replace: Any,
) -> tuple[dict[str, Any], str]:
    """Run a command on the made-up study: the result file and the printout."""
    out = fresh(tmp_path)
    capsys.readouterr()
    assert LS.main(ARGS[command](study, out, *extra, **replace)) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    return json.loads(out.read_text()), printed.out


def refused(
    command: str,
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
    **replace: Any,
) -> str:
    """The reason of a refusal: nothing printed, nothing written."""
    out = fresh(tmp_path, "refused")
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        LS.main(ARGS[command](study, out, *extra, **replace))
    assert isinstance(stop.value.code, str) and stop.value.code.startswith("refused: ")
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == ""
    assert list(out.parent.iterdir()) == []
    return stop.value.code


@contextmanager
def changed(*paths: Path) -> Iterator[None]:
    """Let a test rewrite or remove files of the shared study; every byte is put back."""
    before = {path: path.read_bytes() if path.is_file() else None for path in paths}
    try:
        yield
    finally:
        for path, data in before.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)


@contextmanager
def rewritten(study: SimpleNamespace, run: str, change: Callable[[dict], Any]) -> Iterator[None]:
    """The stored rows of a run passed through ``change`` (None drops a row); the hash of the
    readings is updated in the manifest."""
    folder = study.runs / run
    readings, manifest = folder / "readings.jsonl", folder / "run_manifest.json"
    with changed(readings, manifest):
        rows = [json.loads(line) for line in readings.read_text().splitlines()]
        kept = [new for new in map(change, rows) if new is not None]
        readings.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in kept))
        record = json.loads(manifest.read_text()) | {"readings_sha256": sha(readings)}
        manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        yield


@contextmanager
def json_with(path: Path, change: Callable[[dict], None]) -> Iterator[None]:
    with changed(path):
        record = json.loads(path.read_text())
        change(record)
        path.write_text(json.dumps(record))
        yield


def result_of(report: Mapping[str, Any], *but: str) -> dict[str, Any]:
    """A result without the hashes of the code that wrote it (and without the inputs named):
    two runs are compared on what they computed, whatever happens to a source file between
    them."""
    inputs = {k: v for k, v in report["inputs"].items() if k not in ("code", *but)}
    return {**report, "inputs": inputs, "runs": None if but else report["runs"]}


@pytest.fixture(scope="module")
def e2(study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """One E2 result on the untouched study, with the list of convention items."""
    out = tmp_path_factory.mktemp("e2") / "e2.json"
    assert LS.main(e2_args(study, out)) == 0
    return SimpleNamespace(report=json.loads(out.read_text()), text=out.read_text())


@pytest.fixture(scope="module")
def e5(study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    out = tmp_path_factory.mktemp("e5") / "e5.json"
    assert LS.main(e5_args(study, out)) == 0
    return SimpleNamespace(report=json.loads(out.read_text()), text=out.read_text())


# --------------------------------------------------------------------------------------------
# E2 end to end
# --------------------------------------------------------------------------------------------


def stored(study: SimpleNamespace, run: str) -> dict[str, dict]:
    path = study.runs / run / "readings.jsonl"
    return {row["item_id"]: row for row in map(json.loads, path.read_text().splitlines())}


def gold_rows(study: SimpleNamespace) -> dict[int, dict[str, str]]:
    rows = csv.DictReader(study.gold.open(encoding="utf-8"))
    numbers = {item: n for n, item in study.ids.items()}
    return {numbers[row["item_id"]]: row for row in rows}


def is_correct(given: dict[str, Any] | None, label: Mapping[str, str]) -> bool:
    """The E2 rule from the answer and the label as they were written."""
    if given is None or given["statement_type"] != label["statement_type"]:
        return False
    if given["interval"] == "ABSTAIN" or not label["start"]:
        return given["interval"] == "ABSTAIN" and not label["start"]
    mine = span(given["interval"]["start"], given["interval"]["end"])
    return iou_by_sets(mine, span(label["start"], label["end"])) >= Fraction(1, 2)


def given_by(model: str, template: str, n: int) -> dict[str, Any] | None:
    return None if fails(model, template, n) == 2 else answer(model, template, n)


def test_the_made_up_study_is_what_the_tests_say(study: SimpleNamespace) -> None:
    key = list(csv.DictReader((study.audit / S.KEYS_DIR / "literal_key.csv").open()))
    numbers = {item: n for n, item in study.ids.items()}
    assert {numbers[row["item_id"]]: row["stratum"] for row in key} == STRATA
    rows = gold_rows(study)
    assert sorted(rows) == list(GOLD) and len(GOLD) == 23
    assert {n for n, row in rows.items() if row["adj_decision"] == "gap"} == {GAP_ITEM}
    assert {n for n, row in rows.items() if row["adj_decision"] == "slip"} == {3, 6}
    assert {n for n, row in rows.items() if row["hard"] == "1"} == {11}
    for n, row in rows.items():
        assert {c: row[c] for c in S.ENTERED[:6]} == {c: TRUTH[n][c] for c in S.ENTERED[:6]}
    # the rule reader is wrong, by the E2 rule, on the seven items named and on no other
    wrong = []
    for n in GOLD:
        literal = R.as_literal_v1(R.read(TEXTS[n], DAY))
        if not is_correct(literal, TRUTH[n]):
            wrong.append(n)
    assert tuple(wrong) == RULES_WRONG
    # failed, repaired and refused rows exist where the script says
    rows = stored(study, f"e2-literal-{QWEN}")
    status = {numbers[item]: row["status"] for item, row in rows.items()}
    assert status[2] == "failed" and status[3] == "repaired" and status[16] == "refused"
    assert sorted(set(status.values())) == ["failed", "ok", "refused", "repaired"]
    assert len(study.pairs) == 84 and len(study.plan["runs"]) > 23


def test_e2_result_file_holds_the_registered_record(
    study: SimpleNamespace, e2: SimpleNamespace
) -> None:
    report = e2.report
    assert report["registered"] == {
        "seed": 20261001,
        "draws": 10_000,
        "alpha": 0.05,
        "iou_correct": 0.5,
        "positive_result_bars": {"iou_lead": 0.15, "false_commitment": 0.05},
        "gee": {"tolerance": "1e-10", "steps": 100, "variance_floor": "1e-10"},
        "primaries": [LLAMA, DEEPSEEK],
        "e2": {
            "lines": {V1: "e2-literal", FREE: "e2-literal-free"},
            "models": list(rd.STUDY_MODELS),
            "test_template": V1,
        },
        "e5": {
            "line": "e5",
            "template": V1,
            "models": [m for m in rd.STUDY_MODELS if m != GEMINI],
            "cut_seeds": 50,
        },
        "pattern": {
            "letter_factors": ["surface_form", "granularity"],
            "standing_factors": ["certainty", "stale", "distractor", "silent"],
            "letter_margin": 0.1,
            "standing_floor": 0.1,
            "own_error_floor": 0.1,
        },
        "templates_sha256": {V1: rd.FROZEN_SHA256[V1], FREE: rd.FROZEN_SHA256[FREE]},
    }
    inputs = report["inputs"]
    assert inputs["gold_sha256"] == sha(study.gold)
    assert inputs["items_sha256"] == sha(study.audit / "literal_items.jsonl")
    assert inputs["item_ids_sha256"] == lp.ids_sha256(study.items)
    assert inputs["events_sha256"] == sha(study.events) and inputs["guide_sha256"] == sha(
        study.guide
    )
    assert inputs["plan_sha256"] == sha(lp.plan_path(study.runs))
    assert inputs["convention_items_sha256"] == sha(study.marks) and inputs["key_compared"] is True
    assert inputs["code"]["literal_scores.py"] == sha(Path(LS.__file__))
    assert inputs["code"]["rules.py"] == sha(Path(R.__file__))
    # the gold is the one the manifest of the audit folder records
    manifest = json.loads((study.audit / S.MANIFEST).read_text())
    assert (
        inputs["gold_sha256_in_the_audit_manifest"] == manifest["gold"]["sha256"] == sha(study.gold)
    )
    assert inputs["convention_items"] == (study.audit / "literal_convention_items.csv").as_posix()
    assert report["not_run_checked"] == {}
    assert report["gold"] == {
        "items_in_the_item_file": 24,
        "gold_items": 23,
        "not_in_the_gold": 1,
        "by_decision": {"agree": 20, "gap": 1, "slip": 2},
        "hard": 1,
        "convention_items": 2,
        "with_distractor_roles": 3,
        "with_a_distractor_date": 3,
    }
    assert report["frame"] == {
        name: {"statements": FRAME.get(name, (0, 0))[0], "templates": FRAME.get(name, (0, 0))[1]}
        for name in S.guide_allocation(GUIDE).names
    }
    assert report["not_run"] == LS.NORMALISERS_NOT_RUN
    assert report["where_the_plan_is_silent"] == list(LS.WHERE_THE_PLAN_IS_SILENT)
    assert list(report["item_sets"]) == ["all", "without_gap", "without_convention_items"]
    assert [report["item_sets"][name]["items"] for name in report["item_sets"]] == [23, 22, 21]
    whole = report["item_sets"]["all"]
    assert whole["episodes"] == 21  # 23 items; two pairs of them share an episode
    assert whole["items_by_stratum"] == {
        name: sum(1 for n in GOLD if STRATA[n] == name)
        for name in S.guide_allocation(GUIDE).names
        if any(STRATA[n] == name for n in GOLD)
    }
    assert "vague" not in whole["items_by_stratum"]  # its one item is not in the gold
    assert set(whole["readers"]) == {LS.RULES, *rd.STUDY_MODELS}
    assert all(set(whole["readers"][m]) == {V1, FREE} for m in rd.STUDY_MODELS)


def test_e2_runs_record_failures_and_refusals_apart(e2: SimpleNamespace) -> None:
    runs = e2.report["runs"]
    assert set(runs) == set(rd.STUDY_MODELS)
    record = runs[QWEN][V1]
    assert record["line"] == "e2-literal" and record["rows"] == 24 and record["runs"] == 1
    assert record["by_status"] == {"failed": 1, "ok": 21, "refused": 1, "repaired": 1}
    assert record["parse_failure_rate"] == near(1 / 24)
    assert record["refusal_rate"] == near(1 / 24)
    assert runs[QWEN][FREE]["by_status"] == {"ok": 24}
    assert runs[LLAMA][V1]["parse_failure_rate"] == 0 and runs[LLAMA][V1]["template"] == V1
    assert runs[LLAMA][FREE]["line"] == "e2-literal-free"


def oracle(numbers: Sequence[int], given: Callable[[int], dict | None]) -> dict[str, Fraction]:
    """A few metrics from the scripted answers and the labels as written, item by item."""
    labels = {n: TRUTH[n] for n in numbers}
    answers = {n: given(n) for n in numbers}

    def abstains(n: int) -> bool:
        return answers[n] is None or answers[n]["interval"] == "ABSTAIN"

    silent = [n for n in numbers if not labels[n]["start"]]
    dated = [n for n in numbers if labels[n]["start"]]
    overlaps = []
    for n in dated:
        if abstains(n):
            overlaps.append(Fraction(0))
            continue
        mine = span(answers[n]["interval"]["start"], answers[n]["interval"]["end"])
        overlaps.append(iou_by_sets(mine, span(labels[n]["start"], labels[n]["end"])))
    return {
        "correct": Fraction(sum(is_correct(answers[n], labels[n]) for n in numbers), len(numbers)),
        "statement_type_accuracy": Fraction(
            sum(
                answers[n] is not None
                and answers[n]["statement_type"] == labels[n]["statement_type"]
                for n in numbers
            ),
            len(numbers),
        ),
        "interval_iou": sum(overlaps) / len(dated),
        "false_commitment": Fraction(sum(not abstains(n) for n in silent), len(silent)),
        "abstention_recall": Fraction(sum(abstains(n) for n in silent), len(silent)),
        "certainty_accuracy": Fraction(
            sum(
                answers[n] is not None and answers[n]["certainty"] == labels[n]["certainty"]
                for n in numbers
            ),
            len(numbers),
        ),
        "stale_accuracy": Fraction(
            sum(
                (answers[n]["stale"] if answers[n] else False)
                == bool(labels[n]["end"] and labels[n]["end"] < DAY)
                for n in numbers
            ),
            len(numbers),
        ),
    }


def test_e2_sample_metrics_are_those_of_the_scripted_answers(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]["readers"]
    for model in rd.STUDY_MODELS:
        for template in (V1, FREE):
            expected = oracle(GOLD, lambda n, m=model, t=template: given_by(m, t, n))
            found = whole[model][template]["sample"]
            for name, value in expected.items():
                assert found[name]["value"] == near(float(value)), (model, template, name)
            assert whole[model][template]["n"]["items"] == 23
    rules = oracle(GOLD, lambda n: R.as_literal_v1(R.read(TEXTS[n], DAY)))
    for name, value in rules.items():
        assert whole[LS.RULES]["sample"][name]["value"] == near(float(value)), name
    # values worked by hand
    llama = whole[LLAMA][V1]["sample"]
    assert llama["correct"]["value"] == near(20 / 23)  # wrong on items 5, 12 and 18
    assert llama["statement_type_accuracy"]["value"] == near(22 / 23)
    assert llama["false_commitment"]["value"] == near(1 / 7)  # item 12 of 7
    assert llama["false_commitment_tbd_or_silent"]["value"] == near(1 / 6)
    assert llama["distractor_uptake"]["value"] == near(1 / 3)  # item 18 of 18, 19, 21
    assert whole[LS.RULES]["sample"]["correct"]["value"] == near(16 / 23)
    assert whole[OSS][V1]["sample"]["distractor_uptake"]["value"] == 1.0
    assert whole[GEMMA][V1]["sample"]["false_commitment_tbd_or_silent"]["value"] == near(4 / 6)
    assert whole[GEMMA][V1]["sample"]["abstention_precision"]["value"] == 1.0
    # one stale gold item (4): deepseek misses it; gpt-4o-mini flags two fresh ones and misses it
    assert whole[DEEPSEEK][V1]["sample"]["stale_recall"]["value"] == 0.0
    assert whole[DEEPSEEK][V1]["sample"]["stale_precision"]["value"] is None
    assert whole[MINI][V1]["sample"]["stale_accuracy"]["value"] == near(20 / 23)
    assert whole[MINI][V1]["sample"]["stale_f1"]["value"] == 0.0
    assert whole[GROK][V1]["sample"]["stale_f1"]["value"] == 1.0
    # the failed and the refused reading of qwen abstain: one on a dated item, one on a silent
    qwen = whole[QWEN][V1]
    assert qwen["n"]["parsed"] == 21 and qwen["n"]["reader_abstain"] == 7 + 1
    assert qwen["sample"]["correct"]["value"] == near(21 / 23)
    assert qwen["sample"]["abstention_recall"]["value"] == 1.0
    assert qwen["sample"]["abstention_precision"]["value"] == near(7 / 8)
    assert qwen["sample"]["certainty_kappa"]["value"] == 1.0  # over the 21 parsed readings
    assert qwen["sample"]["certainty_accuracy"]["value"] == near(21 / 23)
    # the convention-free template reads two parts of a month as the month
    assert whole[GROK][FREE]["sample"]["correct"]["value"] == near(21 / 23)
    assert whole[GROK][V1]["sample"]["correct"]["value"] == 1.0
    assert whole[GROK][V1]["sample"]["interval_iou"]["value"] == 1.0
    assert whole[GROK][V1]["sample"]["start_error_days"]["value"] == 0.0
    # gemini hedges every dated reading: wrong on the eight asserted ones
    assert whole[GEMINI][V1]["sample"]["certainty_accuracy"]["value"] == near(15 / 23)


def test_e2_weights_by_event_and_by_template(e2: SimpleNamespace) -> None:
    found = e2.report["item_sets"]["all"]["readers"][LLAMA][V1]
    # llama is wrong on one of three part-of-month items, one of three TBD items and one of two
    # dated targets beside a distractor; every other stratum is right throughout
    by_event = Fraction(8 + 3 * Fraction(2, 3) + 2 + 2 + 6 * Fraction(2, 3) + 3 + 1 + 2 + 1 + 1, 30)
    by_template = Fraction(4 + 2 + 2 + 2 + 4 * Fraction(2, 3) + 3 + 1 + 2 + 1 + 1, 24)
    assert by_event == Fraction(13, 15) and by_template == Fraction(31, 36)
    assert found["weighted_by_event"]["correct"]["value"] == near(float(by_event))
    assert found["weighted_by_template"]["correct"]["value"] == near(float(by_template))
    assert found["sample"]["correct"]["value"] == near(20 / 23)
    # the frame of the vague stratum, which has no gold item, weighs nothing
    assert sum(FRAME[s][0] for s in FRAME if s != "vague") == 30
    for name, expected in (("part_of_month", 2 / 3), ("tbd", 2 / 3), ("dated_distractor", 1 / 2)):
        assert found["by_stratum"][name]["correct"] == near(expected)
    assert found["by_stratum"]["month_year"]["correct"] == 1.0
    assert found["by_stratum"]["tbd"]["n"]["items"] == 3
    assert found["by_stratum"]["tbd"]["false_commitment"] == near(1 / 3)
    assert found["by_stratum"]["month_year"]["false_commitment"] is None
    assert "ci95" not in found["by_stratum"]["tbd"] and "vague" not in found["by_stratum"]
    # false commitment by event: TBD weighs 6 of the gold-ABSTAIN frame of 6 + 3 + 1 (item 21)
    assert found["weighted_by_event"]["false_commitment"]["value"] == near(
        (6 * (1 / 3)) / (6 + 3 + 1)
    )
    assert found["weighted_by_template"]["false_commitment"]["value"] == near(
        (4 * (1 / 3)) / (4 + 3 + 1)
    )
    # every interval holds its estimate, and a reader that is right throughout has none to show
    for weighting in ("sample", "weighted_by_event", "weighted_by_template"):
        span95 = found[weighting]["correct"]["ci95"]
        assert span95["low"] < found[weighting]["correct"]["value"] < span95["high"]
        assert span95["draws"] == 10_000
    grok = e2.report["item_sets"]["all"]["readers"][GROK][V1]["weighted_by_event"]["correct"]
    assert grok == {"value": 1.0, "ci95": {"low": 1.0, "high": 1.0, "draws": 10_000}}


def test_e2_intervals_are_draws_of_episodes(study: SimpleNamespace, e2: SimpleNamespace) -> None:
    """The interval of llama's share correct, from the registered draws written out here: the
    episodes in sorted order, each with the items it holds."""
    wrong = {5, 12, 18}
    episodes = sorted({EPISODES.get(n, n) for n in GOLD})
    members = {k: [n for n in GOLD if EPISODES.get(n, n) == e] for k, e in enumerate(episodes)}
    scored_in = {s: sum(1 for n in GOLD if STRATA[n] == s) for s in set(STRATA.values())}
    drawn = P.cluster_draws(len(episodes), 10_000, 20261001)
    right = np.array([sum(n not in wrong for n in members[k]) for k in members], dtype=float)
    size = np.array([len(members[k]) for k in members], dtype=float)
    sample = (drawn @ right) / (drawn @ size)
    weight = {n: FRAME[STRATA[n]][0] / scored_in[STRATA[n]] for n in GOLD}
    right_w = np.array([sum(weight[n] for n in members[k] if n not in wrong) for k in members])
    size_w = np.array([sum(weight[n] for n in members[k]) for k in members])
    by_event = (drawn @ right_w) / (drawn @ size_w)
    found = e2.report["item_sets"]["all"]["readers"][LLAMA][V1]
    for name, values in (("sample", sample), ("weighted_by_event", by_event)):
        low, high = np.quantile(values, [0.025, 0.975])
        assert found[name]["correct"]["ci95"]["low"] == near(low, abs=1e-6)
        assert found[name]["correct"]["ci95"]["high"] == near(high, abs=1e-6)


def discordant(numbers: Sequence[int], model: str, template: str = V1) -> tuple[int, int]:
    """Items only the model has right, and items only the rule reader has right."""
    only_model = only_rules = 0
    for n in numbers:
        mine = is_correct(given_by(model, template, n), TRUTH[n])
        rules = n not in RULES_WRONG
        only_model += mine and not rules
        only_rules += rules and not mine
    return only_model, only_rules


def test_e2_registered_tests_and_holm(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]
    outside = [n for n in GOLD if STRATA[n] != "month_year"]
    assert len(outside) == 19
    tests = whole["tests"]
    assert [(t["model"], t["template"], t["against"]) for t in tests] == [
        (LLAMA, V1, "rules"),
        (DEEPSEEK, V1, "rules"),
    ]
    assert discordant(outside, LLAMA) == (7, 3) and discordant(outside, DEEPSEEK) == (7, 0)
    llama, deepseek = tests
    assert llama["items"] == deepseek["items"] == 19 and llama["evaluable"] is True
    assert (llama["only_first_correct"], llama["only_second_correct"]) == (7, 3)
    assert llama["p"] == near(2 * (1 + 10 + 45 + 120) / 1024)
    assert deepseek["p"] == near(2 / 128)
    assert deepseek["p_holm"] == near(4 / 128) and deepseek["holds"] is True
    assert llama["p_holm"] == near(llama["p"]) and llama["holds"] is False
    assert llama["favours"] == deepseek["favours"] == "the model"
    assert llama["first_correct"] == 16 and llama["second_correct"] == 12
    # without the gap item the rule reader is wrong on one item less: Holm no longer holds
    fewer = e2.report["item_sets"]["without_gap"]["tests"]
    assert fewer[1]["items"] == 18 and fewer[1]["p"] == near(2 / 64)
    assert fewer[1]["p_holm"] == near(4 / 64) and fewer[1]["holds"] is False
    # without the two convention items (8 and 9): six discordant pairs for deepseek
    marked = e2.report["item_sets"]["without_convention_items"]["tests"]
    assert marked[1]["items"] == 17 and marked[1]["only_first_correct"] == 6
    assert marked[0]["p"] == near(2 * (1 + 9 + 36 + 84) / 512)


def test_e2_every_model_against_the_rules_and_the_two_templates(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]
    outside = [n for n in GOLD if STRATA[n] != "month_year"]
    inside = [n for n in GOLD if STRATA[n] == "month_year"]
    for model in rd.STUDY_MODELS:
        for template in (V1, FREE):
            found = whole["versus_rules"][model][template]
            b, c = discordant(outside, model, template)
            assert (
                found["outside_month_year"]["only_first_correct"],
                found["outside_month_year"]["only_second_correct"],
            ) == (b, c), (model, template)
            assert found["month_year"]["items"] == 4 and found["all"]["items"] == 23
            assert discordant(inside, model, template) == (
                found["month_year"]["only_first_correct"],
                found["month_year"]["only_second_correct"],
            )
            assert set(found["by_stratum"]) == {STRATA[n] for n in GOLD}
            assert sum(v["items"] for v in found["by_stratum"].values()) == 23
    # the sensitivity analysis of section 4: the items the model parsed (qwen failed on item 2
    # and was refused on item 16, which is outside the month-and-year stratum)
    qwen = whole["versus_rules"][QWEN][V1]
    assert qwen["outside_month_year"]["items"] == 19
    assert qwen["outside_month_year_both_parsed"]["items"] == 18
    assert qwen["outside_month_year"]["only_second_correct"] == 1
    assert qwen["outside_month_year_both_parsed"]["only_second_correct"] == 0
    assert qwen["month_year"]["only_second_correct"] == 1  # the failed item 2
    # literal-v1 against literal-free-v1: the two part-of-month items of the free template
    pair = whole["literal_v1_versus_literal_free_v1"][GROK]
    assert pair["all"]["only_first_correct"] == 2 and pair["all"]["only_second_correct"] == 0
    assert pair["by_stratum"]["part_of_month"]["only_first_correct"] == 2
    assert pair["iou"]["part_of_month"]["difference"] == near(
        ((1 - 11 / 31) + (1 - 10 / 31) + 0) / 3
    )
    assert set(whole["literal_v1_versus_literal_free_v1"]) == set(rd.STUDY_MODELS)


def test_e2_iou_lead_and_the_positive_result(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]
    lead = whole["versus_rules"][GROK][V1]["iou"]
    # grok reads every gold interval; the rule reader's IoU by stratum, worked by hand
    assert lead["month_year"] == {
        "items": 4,
        "first": 1.0,
        "second": 1.0,
        "difference": 0.0,
        # a draw that takes no month-and-year item has no difference to show
        "ci95": {"low": 0.0, "high": 0.0, "draws": lead["month_year"]["ci95"]["draws"]},
    }
    assert lead["part_of_month"]["second"] == near((1 + 1 + 10 / 30) / 3)
    assert lead["part_of_month"]["difference"] == near((1 - 10 / 30) / 3)
    assert lead["month_no_year"]["difference"] == near(1 / 2)  # item 8: IoU 0
    assert lead["range"]["second"] == near((30 / 61 + 90 / 182) / 2)
    assert lead["dated_distractor"]["difference"] == 0.0 and lead["dated_distractor"]["items"] == 2
    assert lead["distractor"]["items"] == 1  # item 20; item 21 has no gold interval
    assert lead["distractor_rows"]["items"] == 3
    assert lead["all"]["items"] == 16 and lead["all"]["first"] == 1.0
    assert 9_000 < lead["month_year"]["ci95"]["draws"] < 10_000 == lead["all"]["ci95"]["draws"]
    span95 = lead["part_of_month"]["ci95"]
    assert span95["low"] <= lead["part_of_month"]["difference"] <= span95["high"]
    assert 0 < span95["draws"] <= 10_000
    positive = whole["positive_result"]
    assert set(positive) == set(rd.STUDY_MODELS)
    assert positive[GROK]["month_year"] == {
        "items": 4,
        "model_correct": 4,
        "rules_correct": 4,
        "iou_difference": 0.0,
    }
    # the bar of the lead stands on the four places the plan names: three strata, and the two
    # distractor rows together
    assert positive[GROK]["leads_by_0.15"] == {
        "part_of_month": True,  # 2/9
        "month_no_year": True,
        "range": True,
        "distractor_rows": False,
    }
    assert set(positive[GROK]["iou_lead"]) == set(positive[GROK]["leads_by_0.15"])
    assert positive[GROK]["iou_lead"]["part_of_month"] == near(2 / 9)
    # the relative stratum stands beside them, with no bar; the made-up sample has no such item
    assert positive[GROK]["iou_lead_beside"] == {"relative": None}
    assert lead["relative"] == {
        "items": 0,
        "first": None,
        "second": None,
        "difference": None,
        "ci95": None,
    }
    assert positive[GROK]["false_commitment_above_0.05"] is False
    assert positive[LLAMA]["false_commitment_tbd_or_silent"]["value"] == near(1 / 6)
    assert positive[LLAMA]["false_commitment_above_0.05"] is True
    # the rate over every gold-ABSTAIN item is reported beside it, and held to no bar
    assert positive[LLAMA]["false_commitment_every_gold_abstain"]["value"] == near(1 / 7)
    assert set(positive[LLAMA]) == {
        "month_year",
        "iou_lead",
        "leads_by_0.15",
        "iou_lead_beside",
        "false_commitment_tbd_or_silent",
        "false_commitment_above_0.05",
        "false_commitment_every_gold_abstain",
    }
    # both distractor rows together: llama is behind on one of the three dated items
    assert positive[LLAMA]["iou_lead"]["distractor_rows"] == near(-1 / 3)
    assert positive[LLAMA]["iou_lead"]["distractor_rows"] == near(
        whole["versus_rules"][LLAMA][V1]["iou"]["distractor_rows"]["difference"]
    )
    # llama puts the expiry date where the release is: behind the rules on that row, which is
    # given alone among the leads over the rules and is no place of the bar
    assert whole["versus_rules"][LLAMA][V1]["iou"]["dated_distractor"]["difference"] == near(-1 / 2)
    assert list(whole["versus_rules"][LLAMA][V1]["iou"]) == [
        "all",
        "month_year",
        "part_of_month",
        "month_no_year",
        "range",
        "relative",
        "dated_distractor",
        "distractor",
        "distractor_rows",
        "gold_with_distractor_date",
    ]


def test_e2_literal_ceiling_is_each_annotator_against_the_other(e2: SimpleNamespace) -> None:
    ceiling = e2.report["item_sets"]["all"]["literal_ceiling"]
    assert ceiling["computed"] is True and set(ceiling) == {
        "computed",
        "A1_against_A2",
        "A2_against_A1",
    }
    first, second = ceiling["A1_against_A2"], ceiling["A2_against_A1"]
    # the annotators differ on items 3 (certainty), 6 and 10 (interval) of the 23 gold items
    for found in (first, second):
        assert found["n"]["items"] == 23
        assert found["sample"]["correct"]["value"] == near(21 / 23)
        assert found["sample"]["certainty_accuracy"]["value"] == near(22 / 23)
        assert found["sample"]["statement_type_accuracy"]["value"] == 1.0
        assert found["sample"]["interval_iou"]["value"] == near((14 + 10 / 31 + 30 / 61) / 16)
        assert found["sample"]["distractor_uptake"]["value"] == 0.0
        assert found["by_stratum"]["range"]["correct"] == near(1 / 2)
    # A1 starts item 10 a month after A2: the sign turns with the direction
    assert first["sample"]["start_error_signed_days"]["value"] == near((10 + 31) / 16)
    assert second["sample"]["start_error_signed_days"]["value"] == near(-(10 + 31) / 16)
    # without the gap item the two differ on one interval only
    fewer = e2.report["item_sets"]["without_gap"]["literal_ceiling"]["A1_against_A2"]
    assert fewer["sample"]["correct"]["value"] == near(21 / 22)


def test_e2_without_the_sheets_the_ceiling_is_named_as_not_computed(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    sheet = study.audit / "submitted" / "literal_A2.csv"
    with changed(sheet):
        sheet.write_bytes(sheet.read_bytes().replace(b"09:40", b"09:41"))
        report, _ = scored("e2", study, tmp_path, capsys)
        ceiling = report["item_sets"]["all"]["literal_ceiling"]
        assert ceiling == {
            "computed": False,
            "why": "the submitted sheet of A2 is not the one the manifest records",
        }
        sheet.unlink()
        report, printed = scored("e2", study, tmp_path, capsys)
        why = "the submitted sheet of A2 is not under the audit folder"
        assert report["item_sets"]["without_gap"]["literal_ceiling"]["why"] == why
        # the margins over the annotators go with the ceiling, and the printout says so
        assert report["item_sets"]["all"]["versus_ceiling"] == {"computed": False, "why": why}
        assert f"literal ceiling: not computed ({why})" in printed.splitlines()
    # nothing else moves
    assert report["item_sets"]["all"]["tests"] == e2.report["item_sets"]["all"]["tests"]
    assert report["item_sets"]["all"]["readers"] == e2.report["item_sets"]["all"]["readers"]


def test_e2_a_manifest_whose_record_of_the_sheets_cannot_be_read_gives_no_ceiling(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    """The manifest of the audit folder records the hashes of the submitted sheets under
    ``submitted``. When that is no mapping, the ceiling is named as not computed, with the
    reason, and every other figure stands."""
    manifest = study.audit / S.MANIFEST
    why = "the manifest of the audit folder cannot be read"
    for broken in ([1], None, "sheets"):
        with json_with(manifest, lambda record, broken=broken: record.update(submitted=broken)):
            report, printed = scored("e2", study, tmp_path, capsys)
        whole = report["item_sets"]["all"]
        assert whole["literal_ceiling"] == {"computed": False, "why": why}, broken
        assert f"literal ceiling: not computed ({why})" in printed.splitlines()
        assert whole["tests"] == e2.report["item_sets"]["all"]["tests"]
        assert whole["readers"] == e2.report["item_sets"]["all"]["readers"]
    # the function itself, on a manifest that is no JSON object at all
    folder = tmp_path / "audit"
    folder.mkdir()
    for text in ("{ not JSON", "[1, 2]", "\xff"):
        (folder / S.MANIFEST).write_bytes(text.encode("latin-1"))
        assert LS.annotator_labels(folder) == (None, why), text


def test_e2_item_sets_with_and_without_the_marked_items(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    sets = e2.report["item_sets"]
    assert sets["without_gap"]["items_by_stratum"]["range"] == 1
    assert sets["without_convention_items"]["items_by_stratum"].get("month_no_year") is None
    assert sets["without_convention_items"]["items"] == 21
    # the rule reader is wrong on item 8, one of the two convention items
    rules = [sets[name]["readers"]["rules"]["sample"]["correct"]["value"] for name in sets]
    assert rules == near([16 / 23, 16 / 22, 15 / 21])
    # by event, the frame of a stratum that lost its items weighs nothing: 30 - 2 statements
    found = sets["without_convention_items"]["readers"][LLAMA][V1]["weighted_by_event"]
    assert found["correct"]["value"] == near(float(Fraction(13 * 2 - 2, 28)))
    # without the list nothing is scored: the plan keeps a list in every case, and the report
    # without those items is part of every E2 result
    with changed(study.marks):
        study.marks.unlink()
        why = refused("e2", study, tmp_path, capsys)
        assert why == (
            f"refused: the list of convention items is not there ({study.marks.as_posix()}): "
            "E2 is also reported without those items, and a list that holds its header alone "
            "says that there is none"
        )
    # no word on the command line stands for the list, whether the list is on disk, holds its
    # header alone or is not there, and whatever folder is named
    elsewhere = tmp_path / "audit_without_the_list"
    shutil.copytree(study.audit, elsewhere)
    (elsewhere / LS.E2_CONVENTION_ITEMS).unlink()
    declaration = ("--no-convention-items", "none was marked")
    for where in (study.audit, elsewhere):
        why = refused("e2", study, tmp_path, capsys, *declaration, audit_dir=where)
        assert why == "refused: unrecognized arguments: --no-convention-items none was marked"
    with changed(study.marks):
        study.marks.write_text("item_id\n")
        why = refused("e2", study, tmp_path, capsys, *declaration)
        assert why == "refused: unrecognized arguments: --no-convention-items none was marked"
    with pytest.raises(SystemExit, match="refused: unrecognized arguments"):
        LS.arguments(["e2", "--no-convention-items", "none", "--out", str(tmp_path / "x.json")])
    # the list lies under the folder of the task unless another file is named
    args = LS.arguments(["e2", "--audit-dir", str(elsewhere), "--out", str(tmp_path / "x.json")])
    assert args.convention_items == elsewhere / "literal_convention_items.csv"
    assert not hasattr(args, "no_convention_items")
    why = refused("e2", study, tmp_path, capsys, audit_dir=elsewhere)
    assert why.startswith(
        f"refused: the list of convention items is not there ({args.convention_items.as_posix()})"
    )
    # a list that holds its header alone says that there is none: the third report is then
    # that of every gold item, and nothing of the result is named as not computed
    with changed(study.marks):
        study.marks.write_text("item_id\n")
        report, printed = scored("e2", study, tmp_path, capsys)
    assert report["gold"]["convention_items"] == 0
    assert report["inputs"]["convention_items"] == study.marks.as_posix()
    assert report["inputs"]["convention_items_sha256"] == hashlib.sha256(b"item_id\n").hexdigest()
    assert report["item_sets"]["without_convention_items"] == sets["all"]
    assert report["not_run"] == LS.NORMALISERS_NOT_RUN and "not computed" not in printed
    assert e2.report["not_run"] == LS.NORMALISERS_NOT_RUN
    assert e2.report["inputs"]["convention_items_sha256"] == sha(study.marks)
    assert e2.report["gold"]["convention_items"] == 2


def test_e2_per_item_holds_ids_and_flags_only(study: SimpleNamespace, e2: SimpleNamespace) -> None:
    per_item = e2.report["per_item"]
    assert per_item["columns"] == ["item_id", "correct", "parsed"] and per_item["item_set"] == "all"
    readers = per_item["readers"]
    assert set(readers) == {"rules"} | {f"{m} {t}" for m in rd.STUDY_MODELS for t in (V1, FREE)}
    ids = sorted(study.ids[n] for n in GOLD)
    numbers = {item: n for n, item in study.ids.items()}
    for name, rows in readers.items():
        assert [row[0] for row in rows] == ids
        assert all(len(row) == 3 and row[1] in (0, 1) and row[2] in (0, 1) for row in rows)
        if name != "rules":
            model, template = name.split(" ")
            for item, correct, parsed in rows:
                given = given_by(model, template, numbers[item])
                assert correct == is_correct(given, TRUTH[numbers[item]]), (name, numbers[item])
                assert parsed == (given is not None)
    assert {numbers[row[0]] for row in readers["rules"] if not row[1]} == set(RULES_WRONG)


def no_text_in(study: SimpleNamespace, text: str, but: Sequence[str] = ()) -> None:
    """Nothing of an item but its id: no wording, no drug, no quote, no label of a reading."""
    for wording in {*TEXTS.values(), *PAIR_TEXT.values()}:
        assert wording not in text
    words = ("Examplamine", "Zorvamine", "Acme", "Belcor", "expiry", "NDC", 'ABSTAIN"')
    for word in (w for w in words if w not in but):
        assert word not in text, word
    assert '"quote"' not in text and '"interval":' not in text and "next_delivery" not in text


def test_e2_prints_a_short_table_and_no_text_of_an_item(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    extra = ["--convention-items", str(study.marks), "--expect-convention-sha256", sha(study.marks)]
    report, printed = scored("e2", study, tmp_path, capsys, *extra)
    assert result_of(report) == result_of(e2.report)  # the same result on a second run
    lines = printed.splitlines()
    assert lines[0] == (
        "E2: 23 gold items in 21 episodes; strata weighted by their frame statements"
    )
    assert len(lines) == 2 + 1 + 16 + 6 + 1 and lines[-1].startswith("wrote ")
    # by event the frame holds 30 statements, 20 of them in strata whose gold is dated. The
    # rule reader is wrong on items of weight 8 in all and has the type wrong on one TBD item
    # (weight 2); its IoU is 1 on weight 14, and 10/30, 0, 30/61, 90/182, 1/30 and 0 on six
    # items of weight 1. Llama is wrong on weight 4, has one type wrong, and misses one interval
    rules_iou = (14 + 10 / 30 + 30 / 61 + 90 / 182 + 1 / 30) / 20
    assert lines[2].split() == ["rules", "0.733", "0.933", f"{rules_iou:.3f}", "0.000", "-"]
    assert f"{rules_iou:.3f}" == "0.768"
    row = next(line for line in lines if line.startswith(f"{LLAMA} {V1}"))
    assert row.split()[2:] == ["0.867", "0.967", "0.950", "0.200", "0.000"]
    row = next(line for line in lines if line.startswith(f"{QWEN} {V1}"))
    assert row.split()[-1] == "0.042"
    assert (
        f"all: {DEEPSEEK} against the rules outside month and year, 19 items: 7 against 0 "
        "discordant, p = 0.0156, Holm 0.0312 *"
    ) in lines
    assert sum(line.endswith("*") for line in lines) == 1
    no_text_in(study, printed)
    no_text_in(study, e2.text)
    assert not [item for item in study.items if item in printed]


# --------------------------------------------------------------------------------------------
# E2 refusals
# --------------------------------------------------------------------------------------------


def test_e2_does_nothing_before_the_gold_exists(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The blinding rule: without the gold file no stored reading is opened, whatever else is
    there, and with a gold that is not the hashed one neither."""
    opened: list[str] = []
    real = LS.ev.read_group

    def watched(*args: Any, **kwargs: Any) -> Any:
        opened.append("runs")
        return real(*args, **kwargs)

    monkeypatch.setattr(LS.ev, "read_group", watched)
    monkeypatch.setattr(LS, "frame_of", lambda *a, **k: opened.append("events"))
    monkeypatch.setattr(LS, "rule_reading", lambda *a, **k: opened.append("rules"))
    with changed(study.gold):
        wanted = sha(study.gold)
        study.gold.unlink()
        why = refused("e2", study, tmp_path, capsys, expect_gold_sha256=wanted)
    assert why.startswith("refused: the gold of the literal task is not there")
    assert why.endswith(
        "no reading is compared with the items of the literal task before their gold is fixed"
    )
    why = refused("e2", study, tmp_path, capsys, expect_gold_sha256="0" * 64)
    assert "the gold of the literal task is not the expected file" in why
    assert sha(study.gold)[:16] in why
    why = refused("e2", study, tmp_path, capsys, expect_gold_sha256=None)
    assert (
        why == "refused: --expect-gold-sha256 takes a sha256 or its first 16 or more hex characters"
    )
    why = refused("e2", study, tmp_path, capsys, expect_gold_sha256=sha(study.gold)[:15])
    assert "--expect-gold-sha256 takes a sha256" in why
    with changed(study.gold):
        study.gold.write_bytes(study.gold.read_bytes() + b"\n")
        why = refused("e2", study, tmp_path, capsys, expect_gold_sha256=wanted)
    assert "is not the expected file" in why
    assert opened == []
    # a missing gold is refused first, whatever is given for its hash
    with changed(study.gold):
        study.gold.unlink()
        for given in (wanted[:16], "not a hash", None):
            why = refused("e2", study, tmp_path, capsys, expect_gold_sha256=given)
            assert "is not there" in why and "takes a sha256" not in why
    assert opened == []


def test_the_first_sixteen_characters_of_the_hash_are_enough(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    report, _ = scored("e2", study, tmp_path, capsys, expect_gold_sha256=sha(study.gold)[:16])
    assert report["inputs"]["gold_sha256"] == sha(study.gold)
    assert report["item_sets"]["all"] == e2.report["item_sets"]["all"]


def test_an_output_that_exists_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for command in ("e2", "e5"):
        out = tmp_path / f"{command}.json"
        out.write_text("{}")
        with pytest.raises(SystemExit, match="refused: the output is already there"):
            LS.main(ARGS[command](study, out))
        assert out.read_text() == "{}"
        with pytest.raises(SystemExit, match="refused: the folder of the output does not exist"):
            LS.main(ARGS[command](study, tmp_path / "nowhere" / "x.json"))
        with pytest.raises(SystemExit, match="refused: --out is required"):
            LS.main([a for a in ARGS[command](study, out) if a not in ("--out", str(out))])
        with pytest.raises(SystemExit, match="refused: --out lies in a sealed folder"):
            LS.main(ARGS[command](study, tmp_path / "sealed" / "x.json"))
    assert capsys.readouterr().out == ""


def run_of(line: str, model: str) -> str:
    return f"{line}-{model}"


def with_manifest(study: SimpleNamespace, run: str, **change: Any) -> Any:
    return json_with(study.runs / run / "run_manifest.json", lambda record: record.update(change))


def drop_one(row: dict) -> dict | None:
    return None if row["item_id"] == DROPPED[0] else row


DROPPED: list[str] = []


def another_route(row: dict) -> dict:
    return row | {"model_id": "someone/else"}


def another_pin(row: dict) -> dict:
    return row | {"template_sha256": "0" * 64}


def another_template(row: dict) -> dict:
    return row | {"template": FREE, "template_sha256": rd.FROZEN_SHA256[FREE]}


def shifted(row: dict) -> dict:
    return row | {"shift_years": 4}


REFUSED_RUNS: dict[str, tuple[str, str, Callable[[SimpleNamespace, str], Any], str]] = {
    "a partial run": (
        "e2-literal",
        GEMMA,
        lambda study, run: with_manifest(study, run, complete=False),
        "is not finished (partial)",
    ),
    "no run at all": (
        "e2-literal-free",
        GROK,
        lambda study, run: with_manifest(study, run, complete=False, readings=0),
        "is not finished (partial)",
    ),
    "a run on another item set": (
        "e2-literal",
        LLAMA,
        lambda study, run: with_manifest(study, run, item_ids_sha256="0" * 64),
        "is not finished (mismatch: item_ids_sha256)",
    ),
    "an item missing from the rows": (
        "e2-literal",
        DEEPSEEK,
        lambda study, run: rewritten(study, run, drop_one),
        "the item set is not the registered list (1 items missing, 0 not on the list)",
    ),
    "another route": (
        "e2-literal",
        QWEN,
        lambda study, run: rewritten(study, run, another_route),
        "24 rows with another model id or provider pin than the registered route",
    ),
    "another pin of the template": (
        "e2-literal-free",
        OSS,
        lambda study, run: rewritten(study, run, another_pin),
        "24 rows with another template or pin than the frozen one",
    ),
    "another template": (
        "e2-literal",
        MINI,
        lambda study, run: rewritten(study, run, another_template),
        "24 rows with another template or pin than the frozen one",
    ),
    "shifted dates": (
        "e2-literal",
        GEMINI,
        lambda study, run: rewritten(study, run, shifted),
        "24 rows with masked names, shifted dates or a temperature above zero",
    ),
    "readings that are not those of the manifest": (
        "e2-literal",
        LLAMA,
        lambda study, run: with_manifest(study, run, readings_sha256="0" * 64),
        "the readings of run e2-literal-llama-3.3-70b are not those of its manifest",
    ),
}


@pytest.mark.parametrize("case", list(REFUSED_RUNS))
def test_e2_refuses_a_run_that_is_partial_or_not_the_registered_one(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    line, model, change, reason = REFUSED_RUNS[case]
    DROPPED[:] = [study.ids[7]]
    with change(study, run_of(line, model)):
        why = refused("e2", study, tmp_path, capsys)
    assert why.startswith(
        "refused: no score before every run of the experiment is complete on its registered "
        "item list, route and template: "
    )
    assert f"{model} {line}: " in why and reason in why, why
    assert not [item for item in study.items if item in why]  # a refusal names no item


def test_e2_refuses_a_plan_that_is_missing_or_of_another_list(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = lp.plan_path(study.runs)
    with changed(plan):
        plan.unlink()
        why = refused("e2", study, tmp_path, capsys)
    assert why.startswith("refused: no plan of the runs at ")
    with json_with(plan, lambda p: p["lists"]["e2"].update(item_ids_sha256="0" * 64)):
        why = refused("e2", study, tmp_path, capsys)
    assert "the plan's item list 'e2' is not the literal items" in why
    # the item file the runs read was changed after the plan was made
    copy = Path(study.plan["lists"]["e2"]["path"])
    with changed(copy):
        copy.write_bytes(copy.read_bytes() + b"\n")
        why = refused("e2", study, tmp_path, capsys)
    assert "is not the file the plan was made with" in why
    # an item file with one item less than the runs read
    shorter = tmp_path / "items.jsonl"
    lines = (study.audit / "literal_items.jsonl").read_text().splitlines()
    kept = [line for line in lines if json.loads(line)["item_id"] != study.ids[LEFT_OUT]]
    shorter.write_text("".join(line + "\n" for line in kept))
    why = refused("e2", study, tmp_path, capsys, items=shorter)
    assert "the plan's item list 'e2' is not the literal items" in why
    assert "(0 items missing, 1 not on the list)" in why


def test_a_line_planned_under_another_template_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A plan and runs that agree with each other, with the line of ``literal-v1`` read under
    the convention-free template: every check of the runs passes, and the scorer refuses."""
    other = build_study(tmp_path / "other", {"e2-literal": FREE, "e5": FREE})
    assert (
        LS.ev.read_group(
            other.plan, other.runs, "rest", LLAMA, "e2-literal", list(other.items)
        ).problems
        == ()
    )
    why = refused("e2", other, tmp_path, capsys)
    assert f"{LLAMA} e2-literal: planned under {FREE}, registered under {V1}" in why
    assert why.count("planned under") == 8 and "e2-literal-free: planned" not in why
    why = refused("e5", other, tmp_path, capsys)
    assert f"{GROK} e5: planned under {FREE}, registered under {V1}" in why
    assert why.count("planned under") == 7


def test_e2_refuses_a_gold_or_an_item_file_of_something_else(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def gold_with(change: Callable[[list[dict]], None]) -> str:
        rows = list(csv.DictReader(study.gold.open(encoding="utf-8")))
        change(rows)
        path = tmp_path / "gold.csv"
        path.write_text(S.plain_csv(A.GOLD_COLUMNS, rows), encoding="utf-8")
        return refused("e2", study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))

    why = gold_with(lambda rows: rows[0].update(item_id="I0000000000"))
    assert "the gold is not the gold of the item file: 1 rows of no item" in why
    why = gold_with(lambda rows: rows[3].update(statement_type="availability_until"))
    assert "1 rows of no item or that cannot be read" in why and "availability_until" not in why
    why = gold_with(lambda rows: rows.append(dict(rows[0])))
    assert why.endswith("the gold is not the gold of the item file: 1 rows of a repeated item")
    why = gold_with(lambda rows: rows[2].update(adj_decision="maybe"))
    assert why.endswith(": 1 items with a decision that is not agree, slip or gap")

    def both(rows: list[dict]) -> None:
        rows[0].update(item_id="I0000000000")
        rows[2].update(adj_decision="maybe")
        rows.append(dict(rows[5]))

    assert gold_with(both).endswith(
        ": 1 rows of no item or that cannot be read; 1 rows of a repeated item; 1 items with a "
        "decision that is not agree, slip or gap"
    )
    short = tmp_path / "short.csv"
    kept = [c for c in A.GOLD_COLUMNS if c != "certainty"]
    short.write_text(S.plain_csv(kept, csv.DictReader(study.gold.open(encoding="utf-8"))))
    why = refused("e2", study, tmp_path, capsys, gold=short, expect_gold_sha256=sha(short))
    assert "lacks the columns ['certainty']" in why
    why = gold_with(lambda rows: rows.clear())
    assert "has no rows" in why
    # the events table is of another build: an item is of no statement, or of another day
    events = pd.read_csv(study.events, dtype=str, keep_default_na=False)
    other = tmp_path / "events.csv"
    events[events["statement_group_id"] != "S00005"].to_csv(other, index=False)
    why = refused("e2", study, tmp_path, capsys, events=other)
    assert why == "refused: 1 items are of no statement of the events table given"
    events.loc[events["statement_group_id"] == "S00005", "event_date"] = "2020-03-03"
    events.to_csv(other, index=False)
    why = refused("e2", study, tmp_path, capsys, events=other)
    assert why == "refused: 1 items carry another date than their statement in the events table"
    why = refused("e2", study, tmp_path, capsys, events=tmp_path / "none.csv")
    assert "cannot be read as the sampler reads them (FileNotFoundError)" in why
    guide = tmp_path / "guide.md"
    guide.write_text("# A guide with no table\n")
    why = refused("e2", study, tmp_path, capsys, guide=guide)
    assert "cannot be read as the sampler reads them (ValueError)" in why
    items = tmp_path / "bad_items.jsonl"
    items.write_text('{"item_id": "I1"}\n')
    why = refused("e2", study, tmp_path, capsys, items=items)
    assert why == "refused: the item file is not an item file of the reading harness (KeyError)"


def test_e2_holds_the_key_and_the_convention_list_to_what_they_must_be(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    # a key that puts an item in another stratum than the events table
    key = study.audit / S.KEYS_DIR / "literal_key.csv"
    with changed(key):
        key.write_text(key.read_text().replace(",month_no_year,", ",month_year,", 1))
        why = refused("e2", study, tmp_path, capsys)
        assert (
            why == "refused: the key of the sample puts 1 items in another stratum than the table"
        )
        key.unlink()
        report, _ = scored("e2", study, tmp_path, capsys)
        assert report["inputs"]["key_compared"] is False
        assert report["item_sets"]["all"] == e2.report["item_sets"]["all"]
    # the list of convention items: its hash, its ids
    marks = ["--convention-items", str(study.marks)]
    for extra in (marks, []):  # named, or found under the folder of the task
        why = refused("e2", study, tmp_path, capsys, *extra, expect_convention_sha256=None)
        assert "--expect-convention-sha256 takes a sha256" in why
        wrong = [*extra, "--expect-convention-sha256", "0" * 64]
        why = refused("e2", study, tmp_path, capsys, *wrong)
        assert "the list of convention items is not the expected file" in why
    why = refused("e2", study, tmp_path, capsys, convention_items=tmp_path / "no_list.csv")
    assert why.startswith("refused: the list of convention items is not there (")
    # the list named and the list under the folder of the task are one file here
    report, _ = scored("e2", study, tmp_path, capsys, *marks)
    assert report["item_sets"] == e2.report["item_sets"]
    for text, reason in (
        (f"{study.ids[8]}\nI0000000000\n", "names 1 ids that are not gold items"),
        (f"{study.ids[8]}\n{study.ids[LEFT_OUT]}\n", "names 1 ids that are not gold items"),
        (f"{study.ids[8]}\n{study.ids[8]}\n", "or an id twice"),
    ):
        other = tmp_path / "marks.txt"
        other.write_text(text)
        extra = ["--convention-items", str(other), "--expect-convention-sha256", sha(other)]
        assert reason in refused("e2", study, tmp_path, capsys, *extra)
    # comment lines and quotes are skipped; a list that marks every item leaves nothing
    other = tmp_path / "marks.txt"
    other.write_text(f'# two items\n\n"{study.ids[8]}"\n{study.ids[9]}\n')
    extra = ["--convention-items", str(other), "--expect-convention-sha256", sha(other)[:20]]
    report, _ = scored("e2", study, tmp_path, capsys, *extra)
    assert (
        report["item_sets"]["without_convention_items"]
        == e2.report["item_sets"]["without_convention_items"]
    )
    other.write_text("".join(f"{study.ids[n]}\n" for n in GOLD))
    extra = ["--convention-items", str(other), "--expect-convention-sha256", sha(other)]
    report, _ = scored("e2", study, tmp_path, capsys, *extra)
    assert report["item_sets"]["without_convention_items"] == {
        "computed": False,
        "why": "no gold item is left",
    }


def test_a_model_declared_not_run_is_not_read(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    whole = e2.report["item_sets"]["all"]
    # a secondary model whose run is partial: refused without the declaration, left out with it
    with with_manifest(study, run_of("e2-literal", GEMINI), complete=False):
        assert "is not finished (partial)" in refused("e2", study, tmp_path, capsys)
        report, printed = scored(
            "e2", study, tmp_path, capsys, "--not-run", f"{GEMINI}=cap reached"
        )
    found = report["item_sets"]["all"]
    assert report["not_run"] == LS.NORMALISERS_NOT_RUN | {
        GEMINI: "declared on the command line: cap reached"
    }
    # the declared runs are checked like the others: one of the two lines is not complete, and
    # that is enough for the declaration to stand; neither line is scored
    checked = report["not_run_checked"]
    assert set(checked) == {GEMINI} and set(checked[GEMINI]) == {"e2-literal", "e2-literal-free"}
    assert checked[GEMINI]["e2-literal"]["runs"] == {run_of("e2-literal", GEMINI): "partial"}
    assert any("is not finished (partial)" in gap for gap in checked[GEMINI]["e2-literal"]["found"])
    assert checked[GEMINI]["e2-literal-free"] == {
        "runs": {run_of("e2-literal-free", GEMINI): "finished"},
        "found": [],
    }
    assert GEMINI not in found["readers"] and GEMINI not in report["runs"]
    assert GEMINI not in found["versus_rules"] and GEMINI not in found["positive_result"]
    assert found["tests"] == whole["tests"]
    assert found["readers"][GROK] == whole["readers"][GROK]
    assert not any(name.startswith(GEMINI) for name in report["per_item"]["readers"])
    assert GEMINI not in printed
    # a primary: its test stays in the family with p = 1
    with with_manifest(study, run_of("e2-literal", DEEPSEEK), complete=False):
        report, printed = scored("e2", study, tmp_path, capsys, "--not-run", f"{DEEPSEEK}=no route")
    tests = report["item_sets"]["all"]["tests"]
    assert tests[1] == {
        "model": DEEPSEEK,
        "template": V1,
        "against": "rules",
        "evaluable": False,
        "why": "declared on the command line: no route",
        "p": 1.0,
        "p_holm": 1.0,
        "holds": False,
    }
    assert tests[0]["p"] == whole["tests"][0]["p"]
    assert tests[0]["p_holm"] == near(2 * tests[0]["p"])  # Holm still runs over two
    assert f"all: {DEEPSEEK} against the rules: not run, p = 1" in printed
    for bad in (f"{GEMINI}", f"{GEMINI}=", "nobody=why", f"{GEMINI}=a"):
        extra = ["--not-run", bad] + (["--not-run", bad] if bad.endswith("=a") else [])
        why = refused("e2", study, tmp_path, capsys, *extra)
        assert why.startswith("refused: --not-run takes MODEL=REASON, once for a model of")
    assert "takes MODEL=REASON" in refused(
        "e5", study, tmp_path, capsys, "--not-run", f"{GEMINI}=x"
    )


def in_two_parts(study: SimpleNamespace, run: str) -> Any:
    """One run cut into the two shards the harness would make of it, each with its own
    manifest, and the plan listing the two in its place."""
    whole = study.runs / run
    rows = [json.loads(line) for line in (whole / "readings.jsonl").read_text().splitlines()]
    manifest = json.loads((whole / "run_manifest.json").read_text())
    parts = []
    for k in range(2):
        mine = [row for row in rows if rd.shard_of(row["item_id"], 2) == k]
        folder = study.runs / f"{run}.s{k}"
        folder.mkdir()
        readings = folder / "readings.jsonl"
        readings.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in mine))
        record = manifest | {
            "shard": f"{k}/2",
            "items": len(mine),
            "item_ids_sha256": lp.ids_sha256(row["item_id"] for row in mine),
            "expected_rows": len(mine),
            "readings": len(mine),
            "readings_sha256": sha(readings),
        }
        (folder / "run_manifest.json").write_text(json.dumps(record))
        parts.append((folder, record))

    def split(plan: dict) -> None:
        runs = []
        for planned in plan["runs"]:
            shards = [
                planned
                | {
                    "run": folder.name,
                    "shard": record["shard"],
                    "calls": record["expected_rows"],
                    "item_ids_sha256": record["item_ids_sha256"],
                }
                for folder, record in parts
            ]
            runs += shards if planned["run"] == run else [planned]
        plan["runs"] = runs

    return parts, split


@pytest.mark.parametrize("command", ["e2", "e5"])
def test_a_run_stored_in_several_parts_gives_the_same_result(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    e2: SimpleNamespace,
    e5: SimpleNamespace,
    command: str,
) -> None:
    line, base = ("e2-literal", e2.report) if command == "e2" else ("e5", e5.report)
    run = run_of(line, LLAMA)
    extra = (
        ["--convention-items", str(study.marks), "--expect-convention-sha256", sha(study.marks)]
        if command == "e2"
        else []
    )
    parts, split = in_two_parts(study, run)
    aside = study.runs / f"{run}.aside"
    try:
        assert min(record["items"] for _, record in parts) > 5
        with json_with(lp.plan_path(study.runs), split):
            (study.runs / run).rename(aside)
            report, _ = scored(command, study, tmp_path, capsys, *extra)
            record = report["runs"][LLAMA][V1] if command == "e2" else report["runs"][LLAMA]
            assert record["runs"] == 2 and set(record["readings_sha256"]) == {
                folder.name for folder, _ in parts
            }
            for name in report:
                if name not in ("runs", "inputs"):
                    assert report[name] == base[name], name
            assert set(report) == set(base)
            assert result_of(report, "plan_sha256") == result_of(base, "plan_sha256")
            # one part that is not complete, or not there, is a refusal
            second = parts[1][0] / "run_manifest.json"
            with changed(second):
                second.write_text(json.dumps(parts[1][1] | {"complete": False}))
                why = refused(command, study, tmp_path, capsys, *extra)
            assert f"run {parts[1][0].name} is not finished (partial)" in why
            hidden = parts[1][0].with_name("hidden")
            parts[1][0].rename(hidden)
            try:
                why = refused(command, study, tmp_path, capsys, *extra)
            finally:
                hidden.rename(parts[1][0])
            assert f"({parts[1][1]['items']} items missing, 0 not on the list)" in why
            # an item answered in both parts is a duplicate
            first = parts[0][0] / "readings.jsonl"
            with changed(first, parts[0][0] / "run_manifest.json"):
                twice = (parts[1][0] / "readings.jsonl").read_text().splitlines()[0]
                first.write_text(first.read_text() + twice + "\n")
                record = parts[0][1] | {"readings_sha256": sha(first)}
                (parts[0][0] / "run_manifest.json").write_text(json.dumps(record))
                why = refused(command, study, tmp_path, capsys, *extra)
            assert f"{line}: 1 items were answered twice" in why
    finally:
        if aside.exists():
            aside.rename(study.runs / run)
        for folder, _ in parts:
            shutil.rmtree(folder)


# --------------------------------------------------------------------------------------------
# E5 end to end
# --------------------------------------------------------------------------------------------


SEED_CELL = {"seed": "seed", "seed|certainty": "certainty", "seed|stale": "stale"}
"""The three cells of the unedited items, and a factor whose criterion each one is held to."""


def pair_frame(models: Sequence[str] = tuple(ERRS)) -> pd.DataFrame:
    """The errors of the scripted readings in the rows of the model: one row per seed, factor
    and model, and three for the unedited item of a seed, one under each criterion."""
    rows: list[tuple[str, str, str, float]] = []
    for model in models:
        for s in range(PAIR_SEEDS):
            rows += [
                (f"S{s:02d}", cell, model, float(seed_errs(model, s, held)))
                for cell, held in SEED_CELL.items()
            ]
            rows += [
                (f"S{s:02d}", factor, model, float(pair_errs(model, s, factor)))
                for factor in MP.FACTORS
            ]
    return pd.DataFrame(rows, columns=["seed", "factor", "model", "error"])


def test_e5_result_file_and_error_rates(study: SimpleNamespace, e5: SimpleNamespace) -> None:
    report = e5.report
    assert report["items"] == 84 and report["seeds"] == 12
    assert report["items_by_factor"] == dict.fromkeys(PAIR_FACTORS, 12)
    assert report["items_of_test_period_seeds"] == 14  # two seeds dated 2023 or later
    assert report["not_run"] == {} and set(report["runs"]) == set(ERRS)
    assert report["runs"][LLAMA]["line"] == "e5" and report["runs"][LLAMA]["rows"] == 84
    assert report["runs"][LLAMA]["parse_failure_rate"] == 0
    assert report["inputs"]["gold_sha256"] == sha(study.e5_gold)
    assert report["inputs"]["items_sha256"] == sha(study.e5_items)
    assert report["inputs"]["item_ids_sha256"] == lp.ids_sha256(i.item_id for i in study.pairs)
    assert report["item_set"] == {
        "cut": False,
        "items_in_the_item_file": 84,
        "items": 84,
        "item_ids_sha256": report["inputs"]["item_ids_sha256"],
    }
    assert report["registered"]["e5"]["models"] == list(ERRS)
    assert report["where_the_plan_is_silent"] == list(LS.WHERE_THE_PLAN_IS_SILENT)
    assert list(report["errors"]) == list(ERRS)
    for model, counts in ERRS.items():
        table = report["errors"][model]
        for factor, k in zip(PAIR_FACTORS, counts, strict=True):
            assert table["by_factor"][factor]["items"] == 12
            assert table["by_factor"][factor]["errors"] == k, (model, factor)
            assert table["by_factor"][factor]["rate"] == near(k / 12)
            assert table["by_level"][factor] == {
                PAIR_LEVELS[factor]: {"items": 12, "errors": k, "rate": near(k / 12)}
            }
        # the parts of the error: a wrong certainty class counts on the certainty factor, a
        # wrong stale flag on the stale factor, and nowhere else
        assert table["by_factor"]["certainty"]["not_correct"] == 0
        assert table["by_factor"]["certainty"]["certainty_wrong"] == counts[1]
        assert table["by_factor"]["stale"]["stale_wrong"] == counts[4]
        assert table["by_factor"]["stale"]["not_correct"] == 0
        # six odd seeds answer the surface-form item with a wrong certainty class
        wrong = sum(1 for s in range(12) if s % 2 and not pair_errs(model, s, "surface_form"))
        assert table["by_factor"]["surface_form"]["certainty_wrong"] == wrong > 0
        assert table["by_factor"]["surface_form"]["not_correct"] == counts[2]
        late = sum(1 for s in range(12) if s % 3 == 0 and not pair_errs(model, s, "granularity"))
        assert table["by_factor"]["granularity"]["stale_wrong"] == late
        assert table["by_factor"]["silent"]["certainty_wrong"] == counts[6]  # and no error for it
    # the rule reader reads every made-up pair as the gold has it
    assert all(v["errors"] == 0 for v in report["rule_reader"]["by_factor"].values())
    # the unedited items: llama is not correct on seeds 0 and 1, has the certainty class alone
    # wrong on seeds 5 and 9 and the stale flag alone on seeds 2 and 8
    assert report["seed_items"][LLAMA] == {
        "not_correct": {"items": 12, "errors": 2, "rate": near(2 / 12)},
        "certainty_wrong": {"items": 12, "errors": 2, "rate": near(2 / 12)},
        "stale_wrong": {"items": 12, "errors": 2, "rate": near(2 / 12)},
        "cells": {
            "seed": {"items": 12, "errors": 2, "rate": near(2 / 12)},
            "seed|certainty": {"items": 12, "errors": 4, "rate": near(4 / 12)},
            "seed|stale": {"items": 12, "errors": 4, "rate": near(4 / 12)},
        },
    }
    # the seed row of the error rates is that of the E2 rule
    assert report["errors"][LLAMA]["by_factor"]["seed"] == {
        "items": 12,
        "errors": 2,
        "rate": near(2 / 12),
        "not_correct": 2,
        "certainty_wrong": 2,
        "stale_wrong": 2,
    }


def test_e5_tests_are_the_gee_contrasts_under_holm(e5: SimpleNamespace) -> None:
    report = e5.report
    assert report["gee"]["computed"] is True and report["gee"]["why_not"] is None
    assert report["gee"]["method_in_force"] == "the GEE with its robust variance"
    # the observations of the twelve tests are the rows of the two primaries: each of the 84
    # items once, and each of the twelve unedited ones twice more
    assert report["gee"]["observations"] == 2 * (84 + 2 * 12) and report["gee"]["clusters"] == 12
    assert report["gee"]["cells_at_0_or_1"] == {}
    assert report["gee"]["reference_cell"] == dict.fromkeys(ERRS, "seed")
    assert list(report["gee"]["coefficients"]) == list(ERRS)
    assert all(len(found) == 9 for found in report["gee"]["coefficients"].values())
    tests = report["tests"]
    assert [(t["model"], t["factor"]) for t in tests] == [
        (model, factor) for model in (LLAMA, DEEPSEEK) for factor in MP.FACTORS
    ]
    frame = pair_frame()
    for test in tests:
        model, factor = test["model"], test["factor"]
        k = PAIR_FACTORS.index(factor)
        assert test["primary"] is True and test["evaluable"] is True
        assert test["seeds"] == {"edited": 12, "unedited": 12}
        assert test["edited"] == {
            "items": 12,
            "errors": ERRS[model][k],
            "rate": near(ERRS[model][k] / 12),
        }
        # the unedited items are held to the criterion of the factor
        plain = sum(seed_errs(model, s, factor) for s in range(12))
        assert test["against"] == LS.seed_cell(factor)
        assert test["unedited"] == {"items": 12, "errors": plain, "rate": near(plain / 12)}
        assert test["difference"] == near((ERRS[model][k] - plain) / 12)
        estimate, se = by_cell_means(frame, factor, model, test["against"])
        assert test["gee"]["log_odds_difference"] == near(estimate, abs=1e-6)
        assert test["log_odds_difference"] == near(estimate, abs=1e-6)
        odds = [k / (12 - k) for k in (ERRS[model][k], plain)]
        assert test["log_odds_difference"] == near(np.log(odds[0] / odds[1]))
        assert test["gee"]["se"] == near(se, rel=1e-6)
        assert test["gee"]["p"] == near(2 * stats.norm.sf(abs(estimate / se)), abs=1e-6)
        assert test["p"] == test["gee"]["p"] and test["p_from"] == "gee"
        assert set(test["bootstrap"]) == {"draws", "p", "p_percentile", "ci95"}
        assert test["bootstrap"]["draws"] == 10_000 and 0 < test["bootstrap"]["p"] <= 1
    # llama's unedited items: two errors by the E2 rule, four by the criterion of the certainty
    # factor, four by that of the stale factor
    assert [t["against"] for t in tests[:6]] == [
        "seed|certainty",
        "seed",
        "seed",
        "seed|stale",
        "seed",
        "seed",
    ]
    assert [t["unedited"]["errors"] for t in tests[:6]] == [4, 2, 2, 4, 2, 2]
    assert [t["unedited"]["errors"] for t in tests[6:]] == [3, 1, 1, 3, 1, 1]
    adjusted = LS.ev.holm([t["p"] for t in tests])
    assert [t["p_holm"] for t in tests] == near(adjusted, abs=1e-5)
    assert [t["holds"] for t in tests] == [p < 0.05 for p in adjusted]
    # the smallest p-value is multiplied by twelve
    smallest = min(tests, key=lambda t: t["p"])
    assert smallest["p_holm"] == near(min(1.0, 12 * smallest["p"]), abs=1e-5)
    assert any(t["holds"] for t in tests) and not all(t["holds"] for t in tests)
    # the five other models: the same contrasts, outside the family
    others = report["other_models"]
    assert len(others) == 5 * 6 and {t["model"] for t in others} == set(ERRS) - {LLAMA, DEEPSEEK}
    assert all("p_holm" not in t and t["primary"] is False for t in others)
    for test in others:
        estimate, se = by_cell_means(frame, test["factor"], test["model"], test["against"])
        assert test["gee"]["z"] == near(estimate / se, rel=1e-6)
        assert test["p"] == test["gee"]["p"] and test["p_from"] == "gee"


def test_e5_gee_is_the_one_statsmodels_fits(e5: SimpleNamespace) -> None:
    sm = pytest.importorskip("statsmodels.api")
    frame = pair_frame().sort_values("seed", kind="stable").reset_index(drop=True)
    cells = [*LS.SEED_CELLS, *MP.FACTORS]  # three cells for the unedited items of a reader
    assert len(frame) == 7 * (84 + 2 * 12) and set(frame["factor"]) == set(cells)
    x, names = LS.design(list(frame["factor"]), list(frame["model"]), cells, list(ERRS))
    result = sm.GEE(
        frame["error"].to_numpy(),
        x,
        groups=frame["seed"].to_numpy(),
        family=sm.families.Binomial(),
        cov_struct=sm.cov_struct.Independence(),
    ).fit(maxiter=300, ctol=1e-12)
    # the scorer fits reader by reader: a reader's intercept and factor coefficients are those
    # of the one model with the reader's own terms added
    found = e5.report["gee"]["coefficients"]
    joint = dict(zip(names, result.params, strict=True))
    assert list(found) == list(ERRS)
    for model, mine in found.items():
        assert list(mine) == ["intercept", *(f"factor[{c}]" for c in cells[1:])]
        first = model == LLAMA
        own = 0.0 if first else joint[f"model[{model}]"]
        assert mine["intercept"] == near(joint["intercept"] + own, abs=1e-5)
        for c in cells[1:]:
            own = 0.0 if first else joint[f"factor[{c}]:model[{model}]"]
            assert mine[f"factor[{c}]"] == near(joint[f"factor[{c}]"] + own, abs=1e-5), (model, c)
    for test in (*e5.report["tests"], *e5.report["other_models"]):
        weights = contrast_of(names, test["factor"], test["model"], LLAMA, test["against"])
        theirs = result.t_test(weights)
        assert test["gee"]["se"] == near(float(np.squeeze(theirs.sd)), rel=1e-4)
        assert test["gee"]["p"] == near(float(np.squeeze(theirs.pvalue)), abs=1e-5)


def test_e5_metrics_per_model_and_factor(e5: SimpleNamespace) -> None:
    section = e5.report["metrics"]
    assert set(section) == set(ERRS)
    llama = section[LLAMA]
    assert llama["n"]["items"] == 84 and llama["n"]["gold_with_distractor_date"] == 12
    assert llama["n"]["gold_stale"] == 12 and llama["n"]["gold_abstain"] == 12
    assert set(llama["all"]) == set(LS.METRICS) and set(llama["by_factor"]) == set(PAIR_FACTORS)
    counts = dict(zip(PAIR_FACTORS, ERRS[LLAMA], strict=True))
    # not correct by the E2 rule: every error but those of the certainty and stale factors
    wrong = sum(k for f, k in counts.items() if f not in ("certainty", "stale"))
    assert llama["all"]["correct"]["value"] == near(1 - wrong / 84)
    assert llama["all"]["correct"]["ci95"]["draws"] == 10_000
    assert llama["by_factor"]["distractor"]["distractor_uptake"] == near(5 / 12)
    assert llama["by_factor"]["distractor"]["correct"] == near(7 / 12)
    assert llama["by_factor"]["silent"]["false_commitment"] == 0.0
    assert llama["by_factor"]["silent"]["statement_type_accuracy"] == near(11 / 12)
    assert llama["by_factor"]["stale"]["stale_recall"] == near(3 / 12)
    assert llama["by_factor"]["certainty"]["certainty_accuracy"] == near(6 / 12)
    assert llama["by_factor"]["certainty"]["correct"] == 1.0
    assert llama["by_factor"]["seed"]["interval_iou"] == near(10 / 12)
    assert "ci95" not in llama["by_factor"]["seed"]
    assert llama["all"]["false_commitment_tbd_or_silent"]["value"] is None  # no strata here


def test_e5_per_item_and_printout_hold_no_text(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e5: SimpleNamespace
) -> None:
    report, printed = scored("e5", study, tmp_path, capsys)
    assert result_of(report) == result_of(e5.report)  # the same result on a second run
    per_item = report["per_item"]
    assert per_item["columns"] == ["item_id", "error", "parsed"]
    assert per_item["error"] == (
        "an edited item by the criterion of its factor, an unedited item by the E2 rule"
    )
    assert set(per_item) == {"columns", "error", "readers"}
    assert set(per_item["readers"]) == set(ERRS)
    ids = {item: key for key, item in study.pair_ids.items()}
    alone = 0
    for model, rows in per_item["readers"].items():
        assert [row[0] for row in rows] == sorted(ids)
        for item, error, parsed in rows:
            seed, factor = ids[item]
            assert error == pair_errs(model, seed, factor) and parsed == 1
            # an unedited item whose certainty class alone is wrong is no error here
            alone += factor == "seed" and not error and seed_errs(model, seed, "certainty")
    assert alone == sum(
        seed_errs(m, s, "certainty") - seed_errs(m, s) for m in ERRS for s in range(12)
    )
    assert alone > 12
    lines = printed.splitlines()
    assert lines[0] == "E5: 84 items of 12 seeds; the GEE with its robust variance"
    assert lines[1].split() == [
        "error",
        "rate",
        "seed",
        "certainty",
        "surface_f",
        "granulari",
        "stale",
        "distracto",
        "silent",
    ]
    assert lines[2].split() == [
        LLAMA,
        "0.167",
        "0.500",
        "0.250",
        "0.333",
        "0.750",
        "0.417",
        "0.083",
    ]
    # the twelve tests, one line each: the unedited items at the rate of the factor's criterion
    assert len(lines) == 2 + 7 + 12 + 1 and lines[-1].startswith("wrote ")
    assert lines[9].startswith(f"{LLAMA} certainty: 0.500 against 0.333 unedited, p = ")
    assert lines[10].startswith(f"{LLAMA} surface_form: 0.250 against 0.167 unedited, p = ")
    assert lines[12].startswith(f"{LLAMA} stale: 0.750 against 0.333 unedited, p = ")
    assert not [line for line in lines if "same error" in line or "no test" in line]
    assert sum(line.endswith("*") for line in lines) == sum(t["holds"] for t in report["tests"])
    no_text_in(study, printed)
    no_text_in(study, e5.text, but=("expiry",))  # the name of a level of the distractor factor
    assert not [item for item in ids if item in printed]


def always_right_on(study: SimpleNamespace, model: str, factor: str) -> Any:
    """The run of a model on the minimal pairs with a right reading on every item of a factor:
    a cell of factor by model with no error."""
    there = {item for (_, name), item in study.pair_ids.items() if name == factor}
    seed = next(s for s in range(PAIR_SEEDS) if not pair_errs(model, s, factor))
    right = pair_answer(model, seed, factor)

    def fixed(row: dict) -> dict:
        return row | {"reading": right} if row["item_id"] in there else row

    return rewritten(study, run_of("e5", model), fixed)


def test_e5_a_cell_with_no_error_in_another_model_leaves_the_twelve_as_they_are(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e5: SimpleNamespace
) -> None:
    """A model outside the family with no error on the silent items: the robust variances of
    the twelve are those of the primaries' own rows, the GEE stays in force, and nothing of the
    twelve moves. The model's own contrast on that cell has no Wald test; its others keep theirs."""
    with always_right_on(study, GROK, "silent"):
        report, printed = scored("e5", study, tmp_path, capsys)
    assert report["errors"][GROK]["by_factor"]["silent"]["errors"] == 0
    assert report["gee"] == e5.report["gee"] | {
        "cells_at_0_or_1": {GROK: ["silent"]},
        "coefficients": report["gee"]["coefficients"],
    }
    assert report["gee"]["computed"] is True
    assert report["gee"]["method_in_force"] == "the GEE with its robust variance"
    assert "the GEE with its robust variance" in printed.splitlines()[0]
    assert report["tests"] == e5.report["tests"]
    # the cell has no coefficient in the fit of its model; no other fit moves
    fits, before = report["gee"]["coefficients"], e5.report["gee"]["coefficients"]
    assert list(fits[GROK]) == [n for n in before[GROK] if n != "factor[silent]"]
    assert fits[GROK] == near({n: before[GROK][n] for n in fits[GROK]})
    assert {m: v for m, v in fits.items() if m != GROK} == {
        m: v for m, v in before.items() if m != GROK
    }
    earlier = {(t["model"], t["factor"]): t for t in e5.report["other_models"]}
    for test in report["other_models"]:
        was = earlier[test["model"], test["factor"]]
        if (test["model"], test["factor"]) == (GROK, "silent"):
            # its bootstrap p-value stands, as a description
            assert test["gee"] is None and test["p_from"] == "bootstrap"
            assert test["p"] == test["bootstrap"]["p"] and test["edited"]["errors"] == 0
            assert test["log_odds_difference"] is None and test["difference"] == near(-1 / 12)
        elif test["model"] == GROK:
            assert test["p_from"] == "gee" and test["gee"] == near(was["gee"])
            assert test["bootstrap"] == was["bootstrap"]
        else:
            assert test == was


def test_e5_falls_back_to_the_bootstrap_when_a_cell_of_a_primary_has_no_error(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e5: SimpleNamespace
) -> None:
    """A primary with no error on the silent items: the robust variance of that contrast cannot
    be computed, and all twelve tests come from the cluster bootstrap over seeds. The Wald
    results of the other contrasts stay on display."""
    with always_right_on(study, LLAMA, "silent"):
        report, printed = scored("e5", study, tmp_path, capsys)
    assert report["errors"][LLAMA]["by_factor"]["silent"]["errors"] == 0
    assert report["gee"] == {
        "computed": False,
        "why_not": "the error rate is 0 or 1 in 1 cells of factor by primary",
        "method_in_force": "maximum likelihood with a cluster bootstrap over seeds",
        "observations": 2 * (84 + 2 * 12),
        "clusters": 12,
        "cells_at_0_or_1": {LLAMA: ["silent"]},
        "reference_cell": dict.fromkeys(ERRS, "seed"),
        "coefficients": report["gee"]["coefficients"],
    }
    assert set(report["gee"]["coefficients"]) == set(ERRS)
    assert "maximum likelihood with a cluster bootstrap over seeds" in printed.splitlines()[0]
    drawn = P.cluster_draws(12, 10_000, 20261001).astype(float)
    sideways = []
    for test, before in zip(report["tests"], e5.report["tests"], strict=True):
        model, factor = test["model"], test["factor"]
        lost = (model, factor) == (LLAMA, "silent")
        assert test["p"] == test["bootstrap"]["p"] and test["p_from"] == "bootstrap"
        # the same draws of seeds, with the errors of each seed: twelve items on each side of
        # every draw, so the difference of the two rates is a count of errors over twelve. The
        # p-value in force is the centred one: the draws as far from the difference seen as
        # that is from zero
        edited = np.array([float(pair_errs(model, s, factor) and not lost) for s in range(12)])
        plain = np.array([float(seed_errs(model, s, factor)) for s in range(12)])
        count, seen = drawn @ edited - drawn @ plain, edited.sum() - plain.sum()
        assert test["p"] == near((1 + int((np.abs(count - seen) >= abs(seen)).sum())) / 10_001)
        # the percentile p-value stands beside it, under its own name
        below = (1 + int((count <= 0).sum())) / 10_001
        above = (1 + int((count >= 0).sum())) / 10_001
        assert test["bootstrap"]["p_percentile"] == near(min(1.0, 2 * min(below, above)))
        sideways.append(test["bootstrap"]["p_percentile"])
        gap = count / 12
        low, high = np.quantile(gap, [0.025, 0.975])
        assert test["bootstrap"]["ci95"]["low"] == near(low, abs=1e-6)
        assert test["bootstrap"]["ci95"]["high"] == near(high, abs=1e-6)
        if lost:  # the contrast of the cell itself has no Wald test
            assert test["gee"] is None and test["log_odds_difference"] is None
            assert test["edited"]["errors"] == 0 and test["difference"] == near(-2 / 12)
        else:  # every other contrast keeps the Wald result it had
            assert test["bootstrap"] == before["bootstrap"]
            assert test["gee"] == (before["gee"] if model == DEEPSEEK else near(before["gee"]))
    adjusted = LS.ev.holm([t["p"] for t in report["tests"]])
    assert [t["p_holm"] for t in report["tests"]] == near(adjusted, abs=1e-5)
    # Holm's rule takes the centred p-values, and the percentile ones enter nowhere
    assert [t["p"] for t in report["tests"]] != near(sideways, abs=1e-4)
    assert [t["p_holm"] for t in report["tests"]] != near(LS.ev.holm(sideways), abs=1e-4)
    # the five other models keep their own Wald p-values, outside the family
    assert report["other_models"] == e5.report["other_models"]


def test_e5_a_primary_declared_not_run_keeps_its_tests_in_the_family(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e5: SimpleNamespace
) -> None:
    with with_manifest(study, run_of("e5", DEEPSEEK), complete=False):
        assert "is not finished (partial)" in refused("e5", study, tmp_path, capsys)
        report, printed = scored("e5", study, tmp_path, capsys, "--not-run", f"{DEEPSEEK}=cap")
    assert report["not_run"] == {DEEPSEEK: "declared on the command line: cap"}
    assert DEEPSEEK not in report["errors"] and DEEPSEEK not in report["per_item"]["readers"]
    assert report["gee"]["observations"] == 84 + 2 * 12
    assert set(report["gee"]["coefficients"]) == set(ERRS) - {DEEPSEEK}
    checked = report["not_run_checked"]
    assert set(checked) == {DEEPSEEK} and set(checked[DEEPSEEK]) == {"e5"}
    assert checked[DEEPSEEK]["e5"]["runs"] == {run_of("e5", DEEPSEEK): "partial"}
    assert any("is not finished (partial)" in gap for gap in checked[DEEPSEEK]["e5"]["found"])
    tests = report["tests"]
    assert len(tests) == 12
    for test, before in zip(tests[:6], e5.report["tests"][:6], strict=True):
        # the contrasts of the other primary are its own: nothing of them moves
        apart = ("p_holm", "holds")
        assert {k: v for k, v in test.items() if k not in apart} == {
            k: v for k, v in before.items() if k not in apart
        }
    assert all(
        t
        == {
            "model": DEEPSEEK,
            "factor": t["factor"],
            "primary": True,
            "evaluable": False,
            "why": "declared on the command line: cap",
            "p": 1.0,
            "p_holm": 1.0,
            "holds": False,
        }
        for t in tests[6:]
    )
    adjusted = LS.ev.holm([t["p"] for t in tests])
    assert [t["p_holm"] for t in tests] == near(adjusted, abs=1e-5)
    assert f"{DEEPSEEK} stale: not evaluable, p = 1" in printed


def test_e5_refusals(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    why = refused("e5", study, tmp_path, capsys, gold=tmp_path / "none.csv")
    assert why.startswith("refused: the gold of the minimal pairs is not there")
    why = refused("e5", study, tmp_path, capsys, expect_gold_sha256="1" * 64)
    assert "the gold of the minimal pairs is not the expected file" in why
    why = refused("e5", study, tmp_path, capsys, expect_gold_sha256=None)
    assert "--expect-gold-sha256 takes a sha256" in why

    def gold_with(change: Callable[[list[dict]], None]) -> str:
        rows = list(csv.DictReader(study.e5_gold.open(encoding="utf-8")))
        change(rows)
        path = tmp_path / "e5_gold.csv"
        path.write_text(MP.plain_csv(MP.GOLD_COLUMNS, rows), encoding="utf-8")
        return refused("e5", study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))

    why = gold_with(lambda rows: rows.pop())
    assert why == "refused: the gold is not the gold of the item file: 1 items without a gold row"
    assert gold_with(lambda rows: rows.append(dict(rows[0]))).endswith(
        ": 1 rows of a repeated item"
    )
    why = gold_with(lambda rows: rows[1].update(factor="silent"))
    assert "1 rows of no item, of another seed, factor or level" in why
    assert "1 rows of no item" in gold_with(lambda rows: rows[1].update(seed_id="S99"))
    assert "1 rows of no item" in gold_with(lambda rows: rows[0].update(factor="certainty"))
    assert "1 rows of no item" in gold_with(lambda rows: rows[5].update(stale="often"))
    assert "1 rows of no item" in gold_with(lambda rows: rows[5].update(item_id="P0"))
    assert "1 rows of no item" in gold_with(lambda rows: rows[2].update(start="2020-13-01"))
    # the runs: partial, another item set, another route
    run = run_of("e5", QWEN)
    with with_manifest(study, run, complete=False):
        why = refused("e5", study, tmp_path, capsys)
    assert f"{QWEN} e5: run e5-{QWEN} is not finished (partial)" in why
    dropped = study.pairs[3].item_id
    with rewritten(study, run, lambda row: None if row["item_id"] == dropped else row):
        why = refused("e5", study, tmp_path, capsys)
    assert "the item set is not the registered list (1 items missing, 0 not on the list)" in why
    assert dropped not in why
    with rewritten(study, run, another_route):
        why = refused("e5", study, tmp_path, capsys)
    assert "84 rows with another model id or provider pin than the registered route" in why
    with rewritten(study, run, another_pin):
        why = refused("e5", study, tmp_path, capsys)
    assert "84 rows with another template or pin than the frozen one" in why
    # the registered item file is not the one the runs read
    shorter = tmp_path / "pairs.jsonl"
    shorter.write_text("".join(study.e5_items.read_text().splitlines(keepends=True)[:-7]))
    why = refused("e5", study, tmp_path, capsys, items=shorter)
    assert "the gold is not the gold of the item file" in why


def test_score_e5_without_a_seed_item_or_a_factor_has_nothing_to_test() -> None:
    """Twelve tests always: a factor with no item, or no unedited seed item, leaves its tests
    not evaluable with p = 1, and nothing is fitted on cells that are not there."""
    april = ("2020-04-01", "2020-04-30")
    golds, info, answers = {}, {}, {}
    for s in range(6):
        for factor in ("seed", "certainty", "stale"):
            item = f"P{s}{factor}"
            golds[item] = gold("recovery", *april)
            info[item] = {"seed_id": f"S{s}", "factor": factor, "level": "x"}
            wrong = (s + len(factor)) % 3 == 0
            answers[item] = reading("recovery" if not wrong else "depletion", *april)
    readings = {m: answers for m in LS.E5_MODELS}
    found = LS.score_e5(list(golds), golds, info, readings, {})
    assert len(found["tests"]) == 12 and found["gee"]["computed"] is True
    evaluable = [t for t in found["tests"] if t["evaluable"]]
    assert {t["factor"] for t in evaluable} == {"certainty", "stale"} and len(evaluable) == 4
    assert all(
        t["p"] == 1.0 and t["why"] == "no item of the factor, or no unedited seed item"
        for t in found["tests"]
        if not t["evaluable"]
    )
    assert found["items_by_factor"] == {"seed": 6, "certainty": 6, "stale": 6}
    # no unedited seed item at all
    edited = [i for i in golds if info[i]["factor"] != "seed"]
    found = LS.score_e5(edited, golds, info, readings, {})
    assert found["gee"]["computed"] is False
    assert found["gee"]["why_not"] == "no unedited seed item, or no primary that ran"
    assert all(not t["evaluable"] and t["p_holm"] == 1.0 for t in found["tests"])
    # one model alone: its own contrasts, and the other primary declared not run
    found = LS.score_e5(list(golds), golds, info, {LLAMA: answers}, {DEEPSEEK: "declared: why"})
    assert found["gee"]["observations"] == 18 + 2 * 6 and len(found["errors"]) == 1
    assert sum(t["evaluable"] for t in found["tests"]) == 2
    assert [t["why"] for t in found["tests"][6:]] == ["declared: why"] * 6
    # the five other models alone: twelve tests of no primary, and nothing in force for them
    others = {m: answers for m in LS.E5_MODELS if m not in LS.PRIMARIES}
    found = LS.score_e5(list(golds), golds, info, others, dict.fromkeys(LS.PRIMARIES, "declared"))
    assert found["gee"]["computed"] is False and found["gee"]["observations"] == 0
    assert found["gee"]["why_not"] == "no unedited seed item, or no primary that ran"
    assert all(not t["evaluable"] and t["why"] == "declared" for t in found["tests"])
    fitted = [t for t in found["other_models"] if t["evaluable"]]
    assert len(fitted) == 10 and all(t["gee"] and t["p_from"] == "gee" for t in fitted)


def test_score_e5_needs_an_error_rate_between_0_and_1_in_every_cell_of_a_primary() -> None:
    """A cell of factor by model in which every reading errs, or none does, has no finite log
    odds, and its contrast no Wald test. In a primary, every one of the twelve tests then
    comes from the bootstrap over seeds; in another model, nothing of the twelve moves."""
    golds, info = {}, {}
    for s in range(8):
        for factor in ("seed", "certainty", "stale"):
            item = f"P{s}{factor}"
            golds[item] = gold("recovery", *APRIL)
            info[item] = {"seed_id": f"S{s}", "factor": factor, "level": "x"}

    def answers(sure: dict[str, bool] | None = None) -> dict[str, LS.Reading]:
        out = {}
        for item, facts in info.items():
            wrong = (int(facts["seed_id"][1:]) + len(facts["factor"])) % 3 == 0
            wrong = (sure or {}).get(facts["factor"], wrong)
            out[item] = reading("depletion" if wrong else "recovery", *APRIL)
        return out

    def scored_with(model: str, odd: dict[str, bool] | None) -> dict[str, Any]:
        readings = {m: answers() for m in LS.E5_MODELS} | {model: answers(odd)}
        return LS.score_e5(list(golds), golds, info, readings, {})

    plain = scored_with(QWEN, None)
    assert plain["gee"]["computed"] is True and plain["gee"]["why_not"] is None
    assert plain["gee"]["observations"] == 2 * (24 + 2 * 8)
    assert plain["gee"]["cells_at_0_or_1"] == {}
    assert plain["gee"]["reference_cell"] == dict.fromkeys(LS.E5_MODELS, "seed")
    for odd in ({"stale": True}, {"stale": False}, {"seed": True}):
        (flat,) = odd
        # the unedited items stand in three cells; these readings are right in every field but
        # the E2 rule, so the three hold the same errors
        cells = list(LS.SEED_CELLS) if flat == "seed" else [flat]
        # in a model outside the family
        found = scored_with(QWEN, odd)
        assert found["gee"] == plain["gee"] | {
            "cells_at_0_or_1": {QWEN: cells},
            "reference_cell": found["gee"]["reference_cell"],
            "coefficients": found["gee"]["coefficients"],
        }
        # a reader with no seed cell left has no fit, and so no intercept to name
        assert set(found["gee"]["reference_cell"]) == set(found["gee"]["coefficients"])
        assert (QWEN in found["gee"]["reference_cell"]) == (flat != "seed")
        assert found["tests"] == plain["tests"]
        mine = [t for t in found["other_models"] if t["model"] == QWEN and t["evaluable"]]
        assert len(mine) == 2
        for test in mine:  # a contrast needs both of its cells: the seed's is one of them
            lost = flat in ("seed", test["factor"])
            assert (test["gee"] is None) == lost
            assert test["p_from"] == ("bootstrap" if lost else "gee")
            assert test["p"] == test[test["p_from"]]["p"]
        # in a primary
        found = scored_with(DEEPSEEK, odd)
        assert found["gee"] == {
            "computed": False,
            "why_not": f"the error rate is 0 or 1 in {len(cells)} cells of factor by primary",
            "method_in_force": "maximum likelihood with a cluster bootstrap over seeds",
            "observations": 2 * (24 + 2 * 8),
            "clusters": 8,
            "cells_at_0_or_1": {DEEPSEEK: cells},
            "reference_cell": found["gee"]["reference_cell"],
            "coefficients": found["gee"]["coefficients"],
        }
        for test, before in zip(found["tests"], plain["tests"], strict=True):
            if test["evaluable"]:
                assert test["p"] == test["bootstrap"]["p"] and test["p_from"] == "bootstrap"
                assert before["p"] == before["gee"]["p"] and before["p_from"] == "gee"
                if test["model"] == LLAMA:  # the other primary keeps its Wald results on display
                    assert test["gee"] == before["gee"] and test["bootstrap"] == before["bootstrap"]
                else:
                    assert (test["gee"] is None) == (flat in ("seed", test["factor"]))
    assert scored_with(DEEPSEEK, {"stale": True, "seed": False})["gee"]["why_not"] == (
        "the error rate is 0 or 1 in 4 cells of factor by primary"
    )
    # a primary errs on the certainty item of a seed exactly when it errs on its unedited item:
    # the contrast is zero in every draw, its robust variance is zero, and no Wald test exists
    same = answers()
    for s in range(8):
        same[f"P{s}certainty"] = same[f"P{s}seed"]
    readings = {m: answers() for m in LS.E5_MODELS} | {LLAMA: same}
    found = LS.score_e5(list(golds), golds, info, readings, {})
    assert found["gee"]["computed"] is False and found["gee"]["cells_at_0_or_1"] == {}
    assert found["gee"]["why_not"] == "a contrast of a primary has no finite positive variance"
    first = found["tests"][0]
    assert (first["model"], first["factor"]) == (LLAMA, "certainty")
    assert first["gee"] is None and first["difference"] == 0.0 and first["p"] == 1.0
    assert first["log_odds_difference"] == 0.0 and first["bootstrap"]["ci95"]["low"] == 0.0
    assert LS.GEE_VARIANCE_FLOOR == 1e-10
    other = next(t for t in found["tests"] if (t["model"], t["factor"]) == (LLAMA, "stale"))
    assert other["gee"] is not None and other["p"] == other["bootstrap"]["p"]
    assert other["p_from"] == "bootstrap"
    # the same in a model outside the family: its own contrast takes its bootstrap p-value, and
    # the twelve stay with the GEE
    readings = {m: answers() for m in LS.E5_MODELS} | {QWEN: same}
    found = LS.score_e5(list(golds), golds, info, readings, {})
    assert found["gee"]["computed"] is True and found["tests"] == plain["tests"]
    lost = next(
        t for t in found["other_models"] if (t["model"], t["factor"]) == (QWEN, "certainty")
    )
    assert lost["gee"] is None and lost["p_from"] == "bootstrap"
    assert lost["p"] == lost["bootstrap"]["p"] == 1.0
    # the log odds of two cells, and where they are not finite
    assert LS.log_odds_gap({"items": 12, "errors": 9}, {"items": 12, "errors": 2}) == (
        pytest.approx(np.log(3) - np.log(0.2))
    )
    for errors in (0, 12):
        assert LS.log_odds_gap({"items": 12, "errors": errors}, {"items": 12, "errors": 2}) is None
        assert LS.log_odds_gap({"items": 12, "errors": 2}, {"items": 12, "errors": errors}) is None


def test_the_positive_result_reads_its_two_bars_as_the_plan_words_them() -> None:
    """The models lead "by at least 0.15 IoU" on three strata and on the two distractor rows
    together, with the relative stratum beside them; false commitment "exceeds 5%" over the
    gold-ABSTAIN items of the TBD and silent strata, with the rate over every gold-ABSTAIN item
    beside it. What stands beside a bar is held to none."""

    def figures(
        lead: float | None, rate: float | None, every: float | None, beside: float | None = 0.0
    ) -> dict[str, Any]:
        places = (LS.MONTH_YEAR, *LS.LEAD_STRATA, LS.DISTRACTOR_ROWS)
        iou = {name: {"difference": lead} for name in places}
        iou |= {name: {"difference": beside} for name in (*LS.BESIDE_THE_LEAD, "distractor")}
        counts = {"items": 4, "first_correct": 3, "second_correct": 4}
        against = {"m": {V1: {"iou": iou, LS.MONTH_YEAR: counts}, FREE: {}}}
        sample = {
            "false_commitment_tbd_or_silent": {"value": rate},
            "false_commitment": {"value": every},
        }
        return LS.positive_result({"m": {V1: {"sample": sample}}}, against)["m"]

    assert LS.IOU_LEAD == 0.15 and LS.FALSE_COMMITMENT_BAR == 0.05
    assert LS.LEAD_STRATA == ("part_of_month", "month_no_year", "range")
    assert LS.BESIDE_THE_LEAD == ("relative",)
    assert LS.DISTRACTOR_STRATA == ("dated_distractor", "distractor")
    at = figures(0.15, 0.05, 0.05)
    assert set(at["leads_by_0.15"].values()) == {True}
    assert list(at["leads_by_0.15"]) == [*LS.LEAD_STRATA, "distractor_rows"] == list(at["iou_lead"])
    assert at["false_commitment_above_0.05"] is False
    assert at["month_year"] == {
        "items": 4,
        "model_correct": 3,
        "rules_correct": 4,
        "iou_difference": 0.15,
    }
    assert set(figures(0.1499, 0.0501, 0.0)["leads_by_0.15"].values()) == {False}
    # the relative stratum is reported beside the three and is no part of the bar, whatever its
    # lead; nor is a distractor row alone
    for beside in (0.9, 0.0, -0.4, None):
        found = figures(0.2, 0.0, 0.0, beside)
        assert found["iou_lead_beside"] == {"relative": beside}
        assert found["leads_by_0.15"] == dict.fromkeys((*LS.LEAD_STRATA, "distractor_rows"), True)
        assert figures(0.1, 0.0, 0.0, beside)["leads_by_0.15"] == dict.fromkeys(
            (*LS.LEAD_STRATA, "distractor_rows"), False
        )
    # the 5% bar is read on the two strata; the rate over every gold-ABSTAIN item stands beside
    # it and moves nothing
    for rate, every in ((0.0501, 0.0499), (0.0, 0.143), (2 / 22, 2 / 42)):
        found = figures(0.2, rate, every)
        assert found["false_commitment_above_0.05"] is (rate > 0.05)
        assert found["false_commitment_tbd_or_silent"] == {"value": rate}
        assert found["false_commitment_every_gold_abstain"] == {"value": every}
        assert [name for name in found if name.endswith("above_0.05")] == [
            "false_commitment_above_0.05"
        ]
    nothing = figures(None, None, None)
    assert set(nothing["leads_by_0.15"].values()) == {None}
    assert nothing["false_commitment_above_0.05"] is None
    # two strata with no gold-ABSTAIN item leave the bar open, whatever the rate beside it
    assert figures(0.2, None, 0.2)["false_commitment_above_0.05"] is None
    # a model that did not read the registered template has no figures
    assert LS.positive_result({}, {"m": {FREE: {}}}) == {}


def test_the_lead_on_the_relative_stratum_stands_beside_the_three() -> None:
    """Two relative items and two range items: the lead on each stratum is that of its own
    items, and the positive result takes the one into its bar and the other beside it."""
    golds = [gold("recovery", *APRIL)] * 4
    right, off = reading("recovery", *APRIL), reading("recovery", "2020-04-16", "2020-05-15")
    scope = LS.Scope(
        ids=list("abcd"),
        golds=golds,
        strata=["relative", "relative", "range", "range"],
        marked=[False] * 4,
        bases={"sample": np.ones(4)},
        taken=np.ones((3, 4)),
    )
    first = LS.columns([right, right, right, off], golds)
    second = LS.columns([off, off, right, right], golds)
    found = LS.versus(scope, first, second)
    gap = 1 - float(iou_by_sets(span(*APRIL), span("2020-04-16", "2020-05-15")))
    assert 0.5 < gap < 1
    assert found["iou"]["relative"] == {
        "items": 2,
        "first": 1.0,
        "second": pytest.approx(1 - gap),
        "difference": pytest.approx(gap),
        "ci95": {"low": pytest.approx(gap), "high": pytest.approx(gap), "draws": 3},
    }
    assert found["iou"]["range"]["difference"] == pytest.approx(-gap / 2)
    assert found["iou"]["all"]["difference"] == pytest.approx(gap / 4)
    sample = {
        "false_commitment_tbd_or_silent": {"value": None},
        "false_commitment": {"value": None},
    }
    positive = LS.positive_result({"m": {V1: {"sample": sample}}}, {"m": {V1: found}})["m"]
    assert positive["iou_lead_beside"] == {"relative": pytest.approx(gap)}
    assert positive["iou_lead"]["range"] == pytest.approx(-gap / 2)
    assert positive["leads_by_0.15"] == {
        "part_of_month": None,
        "month_no_year": None,
        "range": False,
        "distractor_rows": None,
    }


def test_files_that_are_not_what_they_must_be_are_refused_without_their_content() -> None:
    items = b'{"item_id": "I1", "date_of_update": "2020-03-02"}\n'
    assert [row["item_id"] for row in LS.read_jsonl(items + b"\n", "the file")] == ["I1"]
    for data, reason in (
        (items + items, "the file is empty or holds an item twice"),
        (b"", "the file is empty or holds an item twice"),
        (b'{"item_id": "I1", "date_of_update": "a secret"}\n', "(ValueError)"),
        (b'{"date_of_update": "2020-03-02"}\n', "(KeyError)"),
        (b"not json\n", "(JSONDecodeError)"),
        (b"\xff\xfe", "(UnicodeDecodeError)"),
    ):
        with pytest.raises(SystemExit) as stop:
            LS.read_jsonl(data, "the file")
        assert reason in str(stop.value) and "secret" not in str(stop.value)
    rows = LS.read_table(b"item_id,stratum\nI1,tbd\n", ("item_id", "stratum"), "the key")
    assert rows == [{"item_id": "I1", "stratum": "tbd"}]
    with pytest.raises(SystemExit, match=r"the key has no rows or lacks the columns \['stratum'\]"):
        LS.read_table(b"item_id,form\nI1,tbd\n", ("item_id", "stratum"), "the key")
    with pytest.raises(SystemExit, match="the key has no rows"):
        LS.read_table(b"item_id,stratum\n", ("item_id", "stratum"), "the key")
    with pytest.raises(SystemExit, match=r"cannot be read as a table \(UnicodeDecodeError\)"):
        LS.read_table(b"\xff\xfe", ("item_id",), "the key")
    assert LS.declared([f"{QWEN}=cap reached", f"{GROK}= x "], LS.E5_MODELS) == {
        QWEN: "declared on the command line: cap reached",
        GROK: "declared on the command line: x",
    }
    for bad in ([f"{QWEN}=a", f"{QWEN}=b"], [f"{GEMINI}=a"], [f"{QWEN}= "], [QWEN]):
        with pytest.raises(SystemExit, match="refused: --not-run takes MODEL=REASON"):
            LS.declared(bad, LS.E5_MODELS)


def test_error_rates_by_factor_and_by_level_of_that_factor() -> None:
    """Two factors may name a level alike; a level's rate is that of its own factor's items."""
    april = ("2020-04-01", "2020-04-30")
    right, wrong = reading("recovery", *april), reading("depletion", *april)
    factors = ["seed", "granularity", "granularity", "surface_form", "surface_form", "stale"]
    levels = ["unedited", "quarter", "mid", "quarter", "quarter", "stale"]
    answers = [right, wrong, right, right, wrong, reading("recovery", *april, stale=True)]
    flags = LS.error_flags(LS.columns(answers, [gold("recovery", *april)] * 6), factors)
    table = LS.error_table(flags, factors, levels)
    assert list(table["by_factor"]) == ["seed", "surface_form", "granularity", "stale"]
    assert table["by_factor"]["granularity"] == {
        "items": 2,
        "errors": 1,
        "rate": 0.5,
        "not_correct": 1,
        "certainty_wrong": 0,
        "stale_wrong": 0,
    }
    assert table["by_factor"]["stale"]["stale_wrong"] == table["by_factor"]["stale"]["errors"] == 1
    assert table["by_factor"]["stale"]["not_correct"] == 0
    assert table["by_level"]["granularity"] == {
        "mid": {"items": 1, "errors": 0, "rate": 0.0},
        "quarter": {"items": 1, "errors": 1, "rate": 1.0},
    }
    assert table["by_level"]["surface_form"] == {"quarter": {"items": 2, "errors": 1, "rate": 0.5}}
    assert table["by_level"]["seed"] == {"unedited": {"items": 1, "errors": 0, "rate": 0.0}}
    assert LS.rate([True, False], [False, False]) == {"items": 0, "errors": 0, "rate": None}


# --------------------------------------------------------------------------------------------
# E5: the registered family rests on the primaries alone
# --------------------------------------------------------------------------------------------


def pairs_of(seeds: int, factors: Sequence[str] = PAIR_FACTORS) -> tuple[dict, dict]:
    """Made-up minimal pairs for ``score_e5``: one item for each seed and factor, one gold."""
    golds, info = {}, {}
    for s in range(seeds):
        for factor in factors:
            item = f"P{s:02d}{factor}"
            golds[item] = gold("recovery", *APRIL, "estimated")
            info[item] = {"seed_id": f"S{s:02d}", "factor": factor, "level": "x"}
    return golds, info


def test_the_twelve_tests_do_not_depend_on_the_other_models() -> None:
    """The twelve registered tests are those of the primaries' own rows: they are the same
    whether the five other models are read, were declared not run, have a cell in which every
    reading errs or none does, or gave no answer at all."""
    golds, info = pairs_of(10)
    limits = (2, 5, 3, 4, 6, 5, 3)

    def answers(shift: int, sure: Mapping[str, bool] | None = None) -> dict[str, LS.Reading]:
        out = {}
        for item, facts in info.items():
            k = PAIR_FACTORS.index(facts["factor"])
            wrong = (int(facts["seed_id"][1:]) + 3 * k + shift) % 10 < limits[k]
            wrong = (sure or {}).get(facts["factor"], wrong)
            out[item] = reading("depletion" if wrong else "recovery", *APRIL, "estimated")
        return out

    primaries = {LLAMA: answers(0), DEEPSEEK: answers(4)}
    others = [m for m in LS.E5_MODELS if m not in primaries]
    read = {m: answers(k + 1) for k, m in enumerate(others)}
    full = LS.score_e5(list(golds), golds, info, primaries | read, {})
    assert full["gee"]["computed"] is True and full["gee"]["cells_at_0_or_1"] == {}
    assert len(full["tests"]) == 12 and full["gee"]["observations"] == 2 * (70 + 2 * 10)
    assert all(t["evaluable"] and t["p_from"] == "gee" for t in full["tests"])
    assert len({round(t["p"], 9) for t in full["tests"]}) > 3  # the twelve are not one test
    alone = LS.score_e5(list(golds), golds, info, primaries, dict.fromkeys(others, "declared"))
    flat = {
        QWEN: answers(1, {"stale": True, "silent": False}),
        GEMMA: answers(2, {"seed": False}),
        OSS: answers(3, {"seed": True}),
        MINI: dict.fromkeys(golds, LS.NO_ANSWER),
        GROK: answers(5, {"certainty": True}),
    }
    assert set(flat) == set(others)
    degenerate = LS.score_e5(list(golds), golds, info, primaries | flat, {})
    assert degenerate["gee"]["cells_at_0_or_1"] == {
        QWEN: ["stale", "silent"],
        GEMMA: list(LS.SEED_CELLS),
        OSS: list(LS.SEED_CELLS),
        MINI: [*LS.SEED_CELLS, *MP.FACTORS],
        GROK: ["certainty"],
    }
    for found in (alone, degenerate):
        assert found["tests"] == full["tests"]
        assert found["gee"]["computed"] is True and found["gee"]["why_not"] is None
        assert found["gee"]["method_in_force"] == "the GEE with its robust variance"
        assert found["gee"]["observations"] == 2 * (70 + 2 * 10)
        for model in primaries:
            assert found["gee"]["coefficients"][model] == full["gee"]["coefficients"][model]
    # a model without a coefficient for its unedited items has no fit and no Wald test at all;
    # one that lacks another cell lacks the Wald test of that cell alone
    assert set(degenerate["gee"]["coefficients"]) == {LLAMA, DEEPSEEK, QWEN, GROK}
    for test in degenerate["other_models"]:
        lost = test["model"] in (GEMMA, OSS, MINI) or (test["model"], test["factor"]) in {
            (QWEN, "stale"),
            (QWEN, "silent"),
            (GROK, "certainty"),
        }
        assert (test["gee"] is None) == lost, (test["model"], test["factor"])
        assert test["p_from"] == ("bootstrap" if lost else "gee")
        assert test["p"] == test[test["p_from"]]["p"]


FEW_SEEDS = "the edited items, or the unedited items, lie on fewer than two seeds"


def test_e5_a_contrast_over_fewer_than_two_seeds_is_not_evaluable() -> None:
    """One seed gives no draw but itself: its contrasts keep their place with p = 1. The seeds
    are counted on each side of the contrast, the edited items and the unedited ones."""
    right = reading("recovery", *APRIL, "estimated")
    wrong = reading("depletion", *APRIL, "estimated")
    golds, info = pairs_of(1, ("seed", "stale"))
    given = {"P00seed": right, "P00stale": wrong}
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given}, {})
    stale = next(t for t in found["tests"] if (t["model"], t["factor"]) == (LLAMA, "stale"))
    assert stale == {
        "model": LLAMA,
        "factor": "stale",
        "primary": True,
        "seeds": {"edited": 1, "unedited": 1},
        "evaluable": False,
        "why": FEW_SEEDS,
        "p": 1.0,
        "p_holm": 1.0,
        "holds": False,
    }
    assert not any(t["evaluable"] or t["holds"] for t in found["tests"])
    # two seeds, each with its unedited item and its certainty item, and a stale item on one of
    # them alone: the stale contrast has two seeds in all and one on its edited side
    golds, info = pairs_of(2, ("seed", "stale", "certainty"))
    del golds["P01stale"], info["P01stale"]
    for stale_answer in (right, wrong):
        given = {
            "P00seed": right,
            "P01seed": wrong,
            "P00stale": stale_answer,
            "P00certainty": wrong,
            "P01certainty": right,
        }
        found = LS.score_e5(list(golds), golds, info, {LLAMA: given}, {})
        by_factor = {t["factor"]: t for t in found["tests"] if t["model"] == LLAMA}
        assert by_factor["stale"]["evaluable"] is False
        assert by_factor["stale"]["why"] == FEW_SEEDS
        assert by_factor["stale"]["seeds"] == {"edited": 1, "unedited": 2}
        assert by_factor["stale"]["p"] == 1.0 and by_factor["stale"]["holds"] is False
        # the certainty contrast has two seeds on each side
        assert by_factor["certainty"]["evaluable"] is True
        assert by_factor["certainty"]["seeds"] == {"edited": 2, "unedited": 2}
        assert by_factor["certainty"]["edited"] == {"items": 2, "errors": 1, "rate": 0.5}
        assert by_factor["certainty"]["unedited"] == {"items": 2, "errors": 1, "rate": 0.5}
    # the other side: the unedited items on one seed, the stale items on two
    golds, info = pairs_of(2, ("seed", "stale"))
    del golds["P01seed"], info["P01seed"]
    given = {"P00seed": right, "P00stale": wrong, "P01stale": wrong}
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given}, {})
    stale = next(t for t in found["tests"] if (t["model"], t["factor"]) == (LLAMA, "stale"))
    assert stale["evaluable"] is False and stale["why"] == FEW_SEEDS and stale["p"] == 1.0
    assert stale["seeds"] == {"edited": 2, "unedited": 1}
    # a factor with no item has no seed to count
    silent = next(t for t in found["tests"] if (t["model"], t["factor"]) == (LLAMA, "silent"))
    assert silent["why"] == "no item of the factor, or no unedited seed item"
    assert "seeds" not in silent


def test_e5_a_side_on_one_seed_gives_no_test_whatever_its_reading() -> None:
    """A side of a contrast that lies on one seed is the same in every draw that holds it, and
    adds nothing to a robust variance: tested, it would reject whatever the reading. Three
    cases, each of them a rejection under Holm when the seeds of the two sides are counted
    together."""
    right = reading("recovery", *APRIL, "estimated")
    wrong = reading("depletion", *APRIL, "estimated")
    recovery = gold("recovery", *APRIL, "estimated")

    def lone(found: Mapping[str, Any], factor: str) -> None:
        tests = [t for t in found["tests"] if t["factor"] == factor]
        assert [t["model"] for t in tests] == [LLAMA, DEEPSEEK]
        for test in tests:
            assert test["evaluable"] is False and test["why"] == FEW_SEEDS
            assert test["p"] == test["p_holm"] == 1.0 and test["holds"] is False
            assert "bootstrap" not in test and "gee" not in test
        assert not any(t["holds"] for t in found["tests"])

    # two items on two seeds: an unedited item read right, a certainty item read wrong
    golds = {"a": recovery, "b": recovery}
    info = {
        "a": {"seed_id": "S0", "factor": "seed", "level": "x"},
        "b": {"seed_id": "S1", "factor": "certainty", "level": "x"},
    }
    given = {"a": right, "b": wrong}
    lone(LS.score_e5(list(golds), golds, info, {LLAMA: given, DEEPSEEK: given}, {}), "certainty")
    # ten seeds with an unedited item each, five of them read wrong, and one silent item: no
    # test of the silent factor, whether that item is read right or wrong
    for silent in (right, wrong):
        golds, info, given = {"z": recovery}, {}, {"z": silent}
        info["z"] = {"seed_id": "S9", "factor": "silent", "level": "x"}
        for k in range(10):
            golds[f"u{k}"] = recovery
            info[f"u{k}"] = {"seed_id": f"S{k}", "factor": "seed", "level": "x"}
            given[f"u{k}"] = wrong if k < 5 else right
        lone(LS.score_e5(list(golds), golds, info, {LLAMA: given, DEEPSEEK: given}, {}), "silent")
    # under the GEE: a hundred unedited items, five read wrong, and two silent items of one
    # seed, one read wrong. No cell of a primary is at 0 or 1, and the fit converges
    golds, info, given = {}, {}, {}
    for k in range(100):
        golds[f"u{k}"] = recovery
        info[f"u{k}"] = {"seed_id": f"S{k:03d}", "factor": "seed", "level": "x"}
        given[f"u{k}"] = wrong if k < 5 else right
    for k in range(2):
        golds[f"z{k}"] = recovery
        info[f"z{k}"] = {"seed_id": "S050", "factor": "silent", "level": "x"}
        given[f"z{k}"] = wrong if k else right
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given, DEEPSEEK: given}, {})
    assert found["gee"]["computed"] is True and found["gee"]["cells_at_0_or_1"] == {}
    assert "factor[silent]" in found["gee"]["coefficients"][LLAMA]
    lone(found, "silent")
    # with the silent items on two seeds the contrast is tested
    info["z1"]["seed_id"] = "S051"
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given, DEEPSEEK: given}, {})
    silent_test = next(t for t in found["tests"] if t["factor"] == "silent")
    assert silent_test["evaluable"] is True and silent_test["p_from"] == "gee"
    assert silent_test["edited"] == {"items": 2, "errors": 1, "rate": 0.5}
    assert silent_test["seeds"] == {"edited": 2, "unedited": 100}


def steady_and_rising(flat: bool = False) -> tuple[dict, dict, dict[str, dict[str, LS.Reading]]]:
    """A hundred seeds, each with an unedited item and one item of the certainty, stale and
    granularity factors, and the readings of two readers. Both are not correct on every item of
    five seeds, and on three more granularity items. The *steady* one has the certainty class
    wrong on 28 unedited items and on 28 certainty items, and the stale flag wrong on 20
    unedited items and on 20 stale items: the same rate on both sides, on other seeds. The
    *rising* one has each wrong on 5 unedited items and on 40 edited ones. ``flat`` leaves both
    without an error on the granularity items: a cell that calls the fallback."""
    golds, info = pairs_of(100, ("seed", "certainty", "stale", "granularity"))
    wrong_class = {
        "steady": {"seed": range(28), "certainty": range(14, 42)},
        "rising": {"seed": range(5), "certainty": range(40)},
    }
    wrong_flag = {
        "steady": {"seed": range(40, 60), "stale": range(50, 70)},
        "rising": {"seed": range(40, 45), "stale": range(40, 80)},
    }
    readers: dict[str, dict[str, LS.Reading]] = {}
    for name in ("steady", "rising"):
        given = {}
        for item, facts in info.items():
            s, factor = int(facts["seed_id"][1:]), facts["factor"]
            lost = s >= (92 if factor == "granularity" else 95)
            lost = lost and not (flat and factor == "granularity")
            # on an item of another factor the two fields are wrong where they are on the
            # unedited item, and that is no error there
            off_class = s in wrong_class[name].get(factor, wrong_class[name]["seed"])
            off_flag = s in wrong_flag[name].get(factor, wrong_flag[name]["seed"])
            given[item] = reading(
                "depletion" if lost else "recovery",
                *APRIL,
                "asserted" if off_class else "estimated",
                stale=off_flag,
            )
        readers[name] = given
    return golds, info, readers


def test_e5_a_contrast_holds_both_of_its_sides_to_one_criterion() -> None:
    """The unedited seed item is held to the criterion of the factor it is compared with. A
    reader whose certainty class, or stale flag, is wrong as often on the unedited items as on
    the items edited on that factor shows no effect of the factor; a reader whose rate rises on
    the edits shows one. Held to the E2 rule alone, the unedited items of the first reader
    would stand at 5 errors against 33 and against 25."""
    golds, info, readers = steady_and_rising()
    readings = {LLAMA: readers["steady"], DEEPSEEK: readers["rising"]}
    found = LS.score_e5(list(golds), golds, info, readings, {})
    assert found["gee"]["computed"] is True and found["gee"]["cells_at_0_or_1"] == {}
    assert found["gee"]["observations"] == 2 * (400 + 2 * 100)  # each unedited item three times
    cells = {
        m: {c: v["errors"] for c, v in found["seed_items"][m]["cells"].items()} for m in readings
    }
    assert cells[LLAMA] == {"seed": 5, "seed|certainty": 33, "seed|stale": 25}
    assert cells[DEEPSEEK] == {"seed": 5, "seed|certainty": 10, "seed|stale": 10}
    assert found["seed_items"][LLAMA]["certainty_wrong"]["errors"] == 28
    assert found["seed_items"][LLAMA]["stale_wrong"]["errors"] == 20
    by = {(t["model"], t["factor"]): t for t in found["tests"] if t["evaluable"]}
    assert len(by) == 6 and all("like_for_like" not in t for t in found["tests"])
    for factor, errors in (("certainty", 33), ("stale", 25)):
        steady = by[LLAMA, factor]
        assert steady["against"] == f"seed|{factor}"
        assert steady["edited"] == {"items": 100, "errors": errors, "rate": errors / 100}
        assert steady["unedited"] == steady["edited"]
        assert steady["difference"] == 0.0 and steady["log_odds_difference"] == 0.0
        assert steady["p_from"] == "gee" and steady["gee"]["z"] == pytest.approx(0.0, abs=1e-8)
        assert steady["p"] == pytest.approx(1.0) and steady["p_holm"] == pytest.approx(1.0)
        assert steady["holds"] is False
        assert steady["bootstrap"]["p"] == 1.0
        rising = by[DEEPSEEK, factor]
        assert rising["against"] == f"seed|{factor}"
        assert rising["edited"] == {"items": 100, "errors": 45, "rate": 0.45}
        assert rising["unedited"] == {"items": 100, "errors": 10, "rate": 0.1}
        assert rising["difference"] == pytest.approx(0.35)
        assert rising["p_from"] == "gee" and rising["p_holm"] < 1e-6 and rising["holds"] is True
    # a factor with no field of its own stands against the unedited items under the E2 rule
    for model in readings:
        granular = by[model, "granularity"]
        assert granular["against"] == "seed"
        assert granular["unedited"] == {"items": 100, "errors": 5, "rate": 0.05}
        assert granular["edited"] == {"items": 100, "errors": 8, "rate": 0.08}
        assert granular["holds"] is False
    # of the six tests with items, two reject: the rising reader's on certainty and on stale
    assert [(t["model"], t["factor"]) for t in found["tests"] if t["holds"]] == [
        (DEEPSEEK, "certainty"),
        (DEEPSEEK, "stale"),
    ]
    # the same under the fallback: no error on the granularity items of either reader
    golds, info, readers = steady_and_rising(flat=True)
    readings = {LLAMA: readers["steady"], DEEPSEEK: readers["rising"]}
    found = LS.score_e5(list(golds), golds, info, readings, {})
    assert found["gee"]["computed"] is False
    assert found["gee"]["why_not"] == "the error rate is 0 or 1 in 2 cells of factor by primary"
    assert found["gee"]["cells_at_0_or_1"] == {LLAMA: ["granularity"], DEEPSEEK: ["granularity"]}
    by = {(t["model"], t["factor"]): t for t in found["tests"] if t["evaluable"]}
    for factor, errors in (("certainty", 33), ("stale", 25)):
        steady, rising = by[LLAMA, factor], by[DEEPSEEK, factor]
        assert steady["unedited"] == steady["edited"]
        assert steady["edited"] == {"items": 100, "errors": errors, "rate": errors / 100}
        assert (
            steady["p_from"] == "bootstrap" and steady["p"] == 1.0
        )  # no difference to be far from
        assert steady["holds"] is False
        assert steady["bootstrap"]["ci95"]["low"] < 0 < steady["bootstrap"]["ci95"]["high"]
        # no draw gives the rising reader a difference of zero or less, or of twice 0.35
        assert rising["p_from"] == "bootstrap" and rising["p"] == pytest.approx(1 / 10_001)
        assert rising["difference"] == pytest.approx(0.35) and rising["holds"] is True
        assert rising["bootstrap"]["ci95"]["low"] > 0.2


def test_e5_the_three_seed_cells_on_the_made_up_study(e5: SimpleNamespace) -> None:
    """Every contrast of the made-up study, of the primaries and of the five other models: the
    unedited side is the seed cell of the factor's criterion, and both bootstrap p-values and
    the interval are those of the registered draws of seeds, counted here."""
    drawn = P.cluster_draws(12, 10_000, 20261001).astype(float)
    cells = e5.report["seed_items"]
    for model in ERRS:
        assert {cell: found["errors"] for cell, found in cells[model]["cells"].items()} == {
            cell: sum(seed_errs(model, s, held) for s in range(12))
            for cell, held in SEED_CELL.items()
        }
    apart = 0
    for test in (*e5.report["tests"], *e5.report["other_models"]):
        model, factor = test["model"], test["factor"]
        assert "like_for_like" not in test
        assert test["against"] == LS.seed_cell(factor)
        assert test["unedited"] == cells[model]["cells"][test["against"]]
        apart += test["unedited"] != cells[model]["cells"]["seed"]
        edited = np.array([float(pair_errs(model, s, factor)) for s in range(12)])
        plain = np.array([float(seed_errs(model, s, factor)) for s in range(12)])
        count, seen = drawn @ edited - drawn @ plain, edited.sum() - plain.sum()
        found = test["bootstrap"]
        assert found["p"] == near((1 + int((np.abs(count - seen) >= abs(seen)).sum())) / 10_001)
        below = (1 + int((count <= 0).sum())) / 10_001
        above = (1 + int((count >= 0).sum())) / 10_001
        assert found["p_percentile"] == near(min(1.0, 2 * min(below, above)))
        low, high = np.quantile(count / 12, [0.025, 0.975])
        assert found["ci95"]["low"] == near(low) and found["ci95"]["high"] == near(high)
    # the criterion matters on this study: fourteen contrasts stand against another count of
    # unedited errors than the E2 rule gives
    assert apart == 14


def test_e5_a_seed_cell_without_a_coefficient_leaves_the_other_seed_cells_their_tests() -> None:
    """A reader that is correct by the E2 rule on every unedited item, with the certainty class
    wrong on three of them: the cells ``seed`` and ``seed|stale`` hold no error and have no
    coefficient, the cell ``seed|certainty`` has one. The contrast of the certainty factor
    keeps its Wald test, and the intercept of the reader's fit is that cell."""
    golds, info = pairs_of(10, ("seed", "certainty", "stale", "silent"))
    lost = {"certainty": (9,), "stale": (7, 8), "silent": (0, 5, 6)}
    off_class = {"seed": (0, 1, 2), "certainty": (2, 3, 4, 5, 6)}
    odd, rows = {}, []
    for item, facts in info.items():
        s, factor = int(facts["seed_id"][1:]), facts["factor"]
        wrong = s in lost.get(factor, ())
        off = s in off_class.get(factor, ())
        odd[item] = reading(
            "depletion" if wrong else "recovery", *APRIL, "asserted" if off else "estimated"
        )
        rows.append(
            (facts["seed_id"], factor, "m", float(wrong or (off and factor == "certainty")))
        )
        if factor == "seed":
            rows.append((facts["seed_id"], "seed|certainty", "m", float(off)))
    frame = pd.DataFrame(rows, columns=["seed", "factor", "model", "error"])

    def plain_answers(shift: int) -> dict[str, LS.Reading]:
        out = {}
        for item, facts in info.items():
            wrong = (int(facts["seed_id"][1:]) + len(facts["factor"]) + shift) % 3 == 0
            out[item] = reading("depletion" if wrong else "recovery", *APRIL, "estimated")
        return out

    # in a model outside the family: its own Wald test where its two cells have a coefficient
    found = LS.score_e5(
        list(golds),
        golds,
        info,
        {LLAMA: plain_answers(0), DEEPSEEK: plain_answers(1), QWEN: odd},
        {},
    )
    assert found["gee"]["computed"] is True
    assert found["gee"]["cells_at_0_or_1"] == {QWEN: ["seed", "seed|stale"]}
    assert found["gee"]["reference_cell"] == {
        LLAMA: "seed",
        DEEPSEEK: "seed",
        QWEN: "seed|certainty",
    }

    def logit(k: int) -> float:
        return float(np.log(k / (10 - k)))

    assert found["gee"]["coefficients"][QWEN] == {
        "intercept": pytest.approx(logit(3)),
        "factor[certainty]": pytest.approx(logit(6) - logit(3)),
        "factor[stale]": pytest.approx(logit(2) - logit(3)),
        "factor[silent]": pytest.approx(0.0, abs=1e-9),
    }
    mine = {t["factor"]: t for t in found["other_models"] if t["model"] == QWEN and t["evaluable"]}
    assert set(mine) == {"certainty", "stale", "silent"}
    estimate, se = by_cell_means(frame, "certainty", "m", "seed|certainty")
    assert mine["certainty"]["against"] == "seed|certainty"
    assert mine["certainty"]["unedited"] == {"items": 10, "errors": 3, "rate": 0.3}
    assert mine["certainty"]["edited"] == {"items": 10, "errors": 6, "rate": 0.6}
    assert mine["certainty"]["gee"]["log_odds_difference"] == pytest.approx(estimate)
    assert mine["certainty"]["gee"]["se"] == pytest.approx(se)
    assert mine["certainty"]["p_from"] == "gee"
    assert mine["certainty"]["p"] == pytest.approx(2 * stats.norm.sf(abs(estimate / se)))
    for factor in ("stale", "silent"):  # their seed cell holds no error
        assert mine[factor]["unedited"] == {"items": 10, "errors": 0, "rate": 0.0}
        assert mine[factor]["gee"] is None and mine[factor]["p_from"] == "bootstrap"
        assert mine[factor]["p"] == mine[factor]["bootstrap"]["p"]
    # in a primary: two cells call the fallback, and the Wald result of the certainty contrast
    # stays on display
    found = LS.score_e5(list(golds), golds, info, {LLAMA: odd, DEEPSEEK: plain_answers(1)}, {})
    assert found["gee"]["why_not"] == "the error rate is 0 or 1 in 2 cells of factor by primary"
    first = found["tests"][0]
    assert (first["model"], first["factor"]) == (LLAMA, "certainty")
    assert first["gee"] == pytest.approx(mine["certainty"]["gee"])
    assert first["p_from"] == "bootstrap" and first["p"] == first["bootstrap"]["p"]


def test_e5_holms_rule_takes_the_centred_p_value_of_the_fallback() -> None:
    """No error on the unedited items, and errors on the silent item of seven seeds: the
    percentile p-value counts the few draws that take none of the seven, and would reject at
    Holm's strictest step. The centred p-value also counts the draws that take them fourteen
    times or more, as the exact sign test of seven seeds would not reject, and it is the one
    in force. With twelve erring seeds it rejects."""
    golds, info = pairs_of(100)

    def answers(erring: int) -> dict[str, LS.Reading]:
        out = {}
        for item, facts in info.items():
            wrong = facts["factor"] == "silent" and int(facts["seed_id"][1:]) < erring
            out[item] = reading("depletion" if wrong else "recovery", *APRIL, "estimated")
        return out

    found = LS.score_e5(list(golds), golds, info, {LLAMA: answers(7), DEEPSEEK: answers(12)}, {})
    assert found["gee"]["computed"] is False
    assert (
        found["gee"]["method_in_force"] == "maximum likelihood with a cluster bootstrap over seeds"
    )
    by = {(t["model"], t["factor"]): t for t in found["tests"]}
    times = P.cluster_draws(100, 10_000, 20261001)
    expected = {}
    for model, erring in ((LLAMA, 7), (DEEPSEEK, 12)):
        taken = times[:, :erring].sum(axis=1)  # every draw holds a hundred items on each side
        centre = (1 + int(((taken == 0) | (taken >= 2 * erring)).sum())) / 10_001
        sign = min(1.0, 2 * (1 + int((taken == 0).sum())) / 10_001)
        test = by[model, "silent"]
        assert test["p_from"] == "bootstrap" and test["bootstrap"]["draws"] == 10_000
        assert test["p"] == test["bootstrap"]["p"] == pytest.approx(centre)
        assert test["bootstrap"]["p_percentile"] == pytest.approx(sign)
        expected[model] = (centre, sign)
    # every other contrast has no error on either side: p = 1, and Holm's first two steps are
    # the two silent contrasts
    assert sorted(t["p"] for t in found["tests"])[2:] == [1.0] * 10
    (seven, seven_sign), (twelve, _) = expected[LLAMA], expected[DEEPSEEK]
    assert twelve < seven and 12 * twelve < 0.05 < 11 * seven
    assert 12 * seven_sign < 0.05  # the percentile p-value would have rejected, at any step
    assert seven > 2 * 0.5**7 / 2  # of the size of the exact sign test of seven seeds
    assert by[DEEPSEEK, "silent"]["p_holm"] == pytest.approx(12 * twelve)
    assert by[DEEPSEEK, "silent"]["holds"] is True
    assert by[LLAMA, "silent"]["p_holm"] == pytest.approx(11 * seven)
    assert by[LLAMA, "silent"]["holds"] is False
    assert sum(t["holds"] for t in found["tests"]) == 1


def test_e5_a_fit_of_a_primary_that_does_not_converge_calls_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second thing that calls the fallback (PLAN section 5, E5): no cell of a primary is
    at 0 or 1, and the fit of a primary does not settle in the steps it is given. All twelve
    then come from the bootstrap, and a fit that did not converge shows no coefficient, no
    reference cell and no Wald result."""
    golds, info = pairs_of(10)
    limits = (2, 5, 3, 4, 6, 5, 3)

    def answers(shift: int) -> dict[str, LS.Reading]:
        out = {}
        for item, facts in info.items():
            k = PAIR_FACTORS.index(facts["factor"])
            wrong = (int(facts["seed_id"][1:]) + 3 * k + shift) % 10 < limits[k]
            out[item] = reading("depletion" if wrong else "recovery", *APRIL, "estimated")
        return out

    readings = {LLAMA: answers(0), DEEPSEEK: answers(4), QWEN: answers(1)}
    settled = LS.score_e5(list(golds), golds, info, readings, {})
    assert settled["gee"]["computed"] is True and settled["gee"]["why_not"] is None
    assert settled["gee"]["reference_cell"] == dict.fromkeys(readings, "seed")
    assert all(t["p_from"] == "gee" and t["gee"] is not None for t in settled["tests"])
    monkeypatch.setattr(LS, "GEE_STEPS", 1)  # one Newton step from zero settles nothing
    found = LS.score_e5(list(golds), golds, info, readings, {})
    assert found["gee"]["computed"] is False
    assert found["gee"]["why_not"] == "the fit of a primary does not converge"
    assert (
        found["gee"]["method_in_force"] == "maximum likelihood with a cluster bootstrap over seeds"
    )
    assert found["gee"]["cells_at_0_or_1"] == {}
    assert found["gee"]["reference_cell"] == {} == found["gee"]["coefficients"]
    assert len(found["tests"]) == 12
    for test, before in zip(found["tests"], settled["tests"], strict=True):
        assert test["evaluable"] is True and test["gee"] is None
        assert test["p_from"] == "bootstrap" and test["p"] == test["bootstrap"]["p"]
        assert test["bootstrap"] == before["bootstrap"] and test["edited"] == before["edited"]
    adjusted = LS.ev.holm([t["bootstrap"]["p"] for t in found["tests"]])
    assert [t["p_holm"] for t in found["tests"]] == pytest.approx(list(adjusted))
    # a model outside the family has no Wald result either, and takes its bootstrap p-value
    assert all(
        t["gee"] is None and t["p_from"] == "bootstrap" and t["p"] == t["bootstrap"]["p"]
        for t in found["other_models"]
        if t["evaluable"]
    )
    assert sum(t["evaluable"] for t in found["other_models"]) == 6


def standing_case() -> tuple[dict, dict, dict[str, LS.Reading]]:
    """Four seeds with one item of every factor, and the readings of one reader, chosen so that
    every standing factor has its own error once, an error of another kind, and letter-factor
    items that err under one criterion and not under another."""
    dated = gold("recovery", *APRIL, "estimated")
    away = [("2022-01-01", "2022-01-31")]
    right = reading("recovery", *APRIL, "estimated")
    elsewhere = reading("recovery", "2020-06-01", "2020-06-30", "estimated")
    other_class = reading("recovery", *APRIL, "asserted")
    flagged = reading("recovery", *APRIL, "estimated", stale=True)
    by_factor = {
        "seed": ([dated] * 4, [right, right, right, elsewhere]),
        # under the E2 rule one error; under the certainty criterion two; under the stale one two
        "surface_form": ([dated] * 4, [elsewhere, other_class, flagged, right]),
        # under the E2 rule one error; under the certainty criterion two; under the stale one one
        "granularity": ([dated] * 4, [right, reading("depletion", *APRIL), other_class, right]),
        # two items whose gold gives no date: a date given on one (the own error); a wrong
        # class on a dated one (an error of another kind)
        "certainty": (
            [gold("recovery", certainty="undetermined")] * 2 + [dated] * 2,
            [right, reading("recovery", certainty="undetermined"), other_class, right],
        ),
        # a period without the flag (the own error); an abstention without the flag and a
        # flagged period elsewhere (errors of another kind)
        "stale": (
            [gold("recovery", *APRIL, "estimated", stale=True)] * 4,
            [
                right,
                reading("recovery", certainty="estimated"),
                flagged,
                reading("recovery", "2020-06-01", "2020-06-30", "estimated", stale=True),
            ],
        ),
        # the distractor's period taken (the own error); a wrong type (another kind)
        "distractor": (
            [gold("recovery", *APRIL, "estimated", distractors=away)] * 4,
            [
                reading("recovery", *away[0], "estimated"),
                reading("depletion", *APRIL, "estimated"),
                right,
                right,
            ],
        ),
        # a date given where the entry is silent (the own error)
        "silent": (
            [gold("none", certainty="no_statement")] * 4,
            [right] + [reading("none", certainty="no_statement")] * 3,
        ),
    }
    golds, info, given = {}, {}, {}
    for factor, (theirs, mine) in by_factor.items():
        for k in range(4):
            item = f"P{k}{factor}"
            golds[item], given[item] = theirs[k], mine[k]
            info[item] = {"seed_id": f"S{k}", "factor": factor, "level": "x"}
    return golds, info, given


def test_e5_what_the_standing_part_of_the_pattern_reads_beside_a_test() -> None:
    """PLAN section 13, the standing part: beside its test, a standing factor has the error
    rate on the items of the two letter factors together under the criterion of the factor,
    with how far its own rate stands above it, and the rate of its own error on the items on
    which it can occur. A letter factor has neither. The floors stand with the twelve tests
    and with no contrast of another model."""
    assert LS.LETTER_FACTORS == ("surface_form", "granularity")
    assert LS.STANDING_FACTORS == ("certainty", "stale", "distractor", "silent")
    assert set(LS.OWN_ERROR) == set(LS.STANDING_FACTORS)
    assert sorted(LS.LETTER_FACTORS + LS.STANDING_FACTORS) == sorted(MP.FACTORS)
    golds, info, given = standing_case()
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given, QWEN: given}, {})
    expected = {
        # factor: errors on its four items; on the eight letter-factor items; own error (of the
        # items on which it can occur); the floors: above the unedited items (one error in
        # four under every criterion), above the letter-factor items, the own error
        "certainty": (2, 4, (1, 2), (True, False, True)),
        "stale": (3, 3, (1, 4), (True, True, True)),
        "distractor": (2, 2, (1, 4), (True, True, True)),
        "silent": (1, 2, (1, 4), (False, False, True)),
    }
    entries = [t for t in (*found["tests"], *found["other_models"]) if t["evaluable"]]
    assert {t["model"] for t in entries} == {LLAMA, QWEN} and len(entries) == 12
    beside = {"above_letter_items", "own_error", "errors_of_another_kind", "floors"}
    for test in entries:
        if test["factor"] in LS.LETTER_FACTORS:
            assert not (beside | {"letter_factors"}) & set(test)
            continue
        errors, letter, (own, can), (seed, letters, own_floor) = expected[test["factor"]]
        assert test["edited"] == {"items": 4, "errors": errors, "rate": errors / 4}
        assert test["unedited"] == {"items": 4, "errors": 1, "rate": 0.25}
        assert test["above_letter_items"] == {
            "items": 8,
            "errors": letter,
            "rate": letter / 8,
            "difference": errors / 4 - letter / 8,
        }
        assert test["own_error"] == {"items": can, "errors": own, "rate": own / can}
        assert test["errors_of_another_kind"] == {
            "errors": errors - own,
            "share": (errors - own) / errors,
        }
        assert "letter_factors" not in test
        if test["model"] == QWEN:  # outside the family of twelve: no pattern, and no floor
            assert "floors" not in test and test["primary"] is False
            continue
        assert test["floors"] == {
            "above_seed": seed,
            "above_letter": letters,
            "own_error": own_floor,
            "met": seed and letters and own_floor,
        }
    # the stale flag: a period given without it is the own error; an abstention without it is
    # an error of the stale criterion and not the own one; so is a flagged period elsewhere
    stale = [f"P{k}stale" for k in range(4)]
    cols = LS.columns([given[i] for i in stale], [golds[i] for i in stale])
    assert cols["unflagged"].tolist() == [1, 0, 0, 0] and cols["stale_ok"].tolist() == [0, 0, 1, 1]
    assert cols["correct"].tolist() == [1, 0, 1, 0]
    # it cannot occur where the gold is not stale
    fresh = LS.columns([reading("recovery", *APRIL)], [gold("recovery", *APRIL)])
    assert fresh["unflagged"].tolist() == [0] and fresh["gold_stale"].tolist() == [0]
    # no error on the items of a factor: nothing of another kind, and no share
    for item in given:
        if info[item]["factor"] == "silent":
            given[item] = reading("none", certainty="no_statement")
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given}, {})
    silent = next(t for t in found["tests"] if t["factor"] == "silent")
    assert silent["own_error"] == {"items": 4, "errors": 0, "rate": 0.0}
    assert silent["errors_of_another_kind"] == {"errors": 0, "share": None}


def test_e5_the_standing_quantities_on_the_made_up_study(e5: SimpleNamespace) -> None:
    """Every contrast of a standing factor on the made-up study, for the seven models. The
    scripted readings put the own error on every erring stale and distractor item (a period
    without the flag; the expiry date taken); the certainty items are dated, so no date can
    be given where the gold gives none; an erring silent item abstains under another type."""
    seen = 0
    for test in (*e5.report["tests"], *e5.report["other_models"]):
        model, factor = test["model"], test["factor"]
        if factor in LS.LETTER_FACTORS:
            assert "above_letter_items" not in test and "own_error" not in test
            assert "floors" not in test
            continue
        seen += 1
        errors = ERRS[model][PAIR_FACTORS.index(factor)]
        # the letter-factor items under the criterion of the factor: the scripted surface-form
        # item of an odd seed has the class wrong, the granularity item of every third seed
        # the stale flag
        letter = 0
        for s in range(12):
            for name, off in (("surface_form", s % 2 == 1), ("granularity", s % 3 == 0)):
                counts = {"surface_form": "certainty", "granularity": "stale"}[name] == factor
                letter += pair_errs(model, s, name) or (off and counts)
        assert test["above_letter_items"] == {
            "items": 24,
            "errors": letter,
            "rate": near(letter / 24),
            "difference": near(errors / 12 - letter / 24),
        }
        own = {"stale": errors, "distractor": errors}.get(factor, 0)
        can = 0 if factor == "certainty" else 12
        assert test["own_error"] == {
            "items": can,
            "errors": own,
            "rate": near(own / can) if can else None,
        }
        assert test["errors_of_another_kind"] == {
            "errors": errors - own,
            "share": near((errors - own) / errors),
        }
        # the floors, for the twelve alone: tenths of the counts, in whole numbers
        assert ("floors" in test) == (model in (LLAMA, DEEPSEEK))
        if "floors" in test:
            plain = sum(seed_errs(model, s, factor) for s in range(12))
            wanted = {
                "above_seed": 10 * (errors - plain) >= 12,
                "above_letter": 10 * (2 * errors - letter) >= 24,
                "own_error": bool(can) and 10 * own >= can,
            }
            assert test["floors"] == wanted | {"met": all(wanted.values())}
    assert seen == 7 * 4
    met = {(t["model"], t["factor"]) for t in e5.report["tests"] if t.get("floors", {}).get("met")}
    # llama: stale 9 of 12 against 4 unedited, distractor 5 against 2, with 7 errors on the 24
    # letter-factor items by the E2 rule; deepseek: distractor 11 against 1
    assert met == {(LLAMA, "stale"), (LLAMA, "distractor"), (DEEPSEEK, "distractor")}
    # the criterion matters: llama's letter-factor items hold 7 errors by the E2 rule
    llama = {
        t["factor"]: t["above_letter_items"]["errors"]
        for t in e5.report["tests"][:6]
        if "above_letter_items" in t
    }
    assert llama["distractor"] == llama["silent"] == 7
    assert llama["certainty"] > 7 and llama["stale"] > 7


# --------------------------------------------------------------------------------------------
# E2: coverage, and the margins over the rule reader and over the annotators
# --------------------------------------------------------------------------------------------


def test_e2_interval_coverage_of_every_reader(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]["readers"]
    # sixteen gold items give an interval; the rule reader gives one on each of them
    assert whole["rules"]["n"]["gold_interval"] == 16 == whole["rules"]["n"]["both_interval"]
    assert whole["rules"]["sample"]["interval_coverage"]["value"] == 1.0
    assert whole["rules"]["weighted_by_event"]["interval_coverage"]["value"] == 1.0
    # qwen's failed reading of item 2 is an abstention on a dated item
    assert whole[QWEN][V1]["sample"]["interval_coverage"]["value"] == near(15 / 16)
    assert whole[QWEN][V1]["by_stratum"]["month_year"]["interval_coverage"] == near(3 / 4)
    assert whole[QWEN][FREE]["sample"]["interval_coverage"]["value"] == 1.0
    # a stratum whose gold gives no interval has none to cover
    assert whole["rules"]["by_stratum"]["tbd"]["interval_coverage"] is None
    assert whole["rules"]["by_stratum"]["silent"]["interval_coverage"] is None
    assert whole["rules"]["by_stratum"]["distractor"]["interval_coverage"] == 1.0  # item 20
    assert "interval_coverage" in LS.METRICS
    assert any("coverage of the rule reader per form" in e for e in LS.WHERE_THE_PLAN_IS_SILENT)


def test_the_margin_is_the_difference_of_two_readers_over_the_same_draws() -> None:
    golds = [g for _, g in CASES]
    clusters = ["a", "a", "b", "c", "c", "d", "e", "e"]
    base = np.array([2.0, 2, 1, 3, 3, 1, 1, 1])
    scope = LS.Scope(
        ids=list("12345678"),
        golds=golds,
        strata=["x"] * 8,
        marked=list(MARKED),
        bases={"sample": np.ones(8), "weighted": base},
        taken=LS.item_draws(clusters, draws=400),
    )
    first = case_columns()
    # a second reader: the gold's own reading everywhere, but a date on item 4 (a false
    # commitment on an item that is not marked)
    others = [g.reading for g in golds]
    others[3] = reading("recovery", "2020-06-01", "2020-06-30")
    second = LS.columns(others, golds, MARKED)
    found = LS.margin(LS.measured(scope, first), LS.measured(scope, second))
    assert set(found) == {"sample", "weighted"}
    assert all(tuple(by_metric) == LS.MARGIN_METRICS for by_metric in found.values())
    sample = found["sample"]
    assert sample["false_commitment"]["first"] == pytest.approx(1 / 3)  # item 5 of 4, 5, 7
    assert sample["false_commitment"]["second"] == pytest.approx(1 / 3)  # item 4
    assert sample["false_commitment"]["difference"] == pytest.approx(0.0)
    marked = sample["false_commitment_tbd_or_silent"]  # items 5 and 7 are marked
    assert (marked["first"], marked["second"], marked["difference"]) == (0.5, 0.0, 0.5)
    uptake = sample["distractor_uptake"]
    assert (uptake["first"], uptake["second"], uptake["difference"]) == (1.0, 0.0, 1.0)
    weighted = found["weighted"]["false_commitment"]  # items 4, 5 and 7 weigh 3, 3 and 1
    assert weighted["first"] == pytest.approx(3 / 7) and weighted["second"] == pytest.approx(3 / 7)
    # the interval: both readers in the same draws, written out one draw at a time
    drawn = P.cluster_draws(5, 400, LS.SEED)
    members = {
        k: [i for i, c in enumerate(clusters) if c == name] for k, name in enumerate("abcde")
    }

    def rate(cols: Mapping[str, np.ndarray], top: str, bottom: str, picked: list, w: Any) -> float:
        below = sum(w[i] * cols[bottom][i] for i in picked)
        return sum(w[i] * cols[top][i] for i in picked) / below if below else np.nan

    parts = {
        "false_commitment": ("false_commitment", "gold_abstains"),
        "false_commitment_tbd_or_silent": ("marked_false_commitment", "marked_gold_abstains"),
        "distractor_uptake": ("uptake", "has_distractor"),
    }
    for weighting, w in (("sample", np.ones(8)), ("weighted", base)):
        for name, (top, bottom) in parts.items():
            gaps = []
            for row in drawn:
                picked = [
                    i for k, times in enumerate(row) for _ in range(times) for i in members[k]
                ]
                gaps.append(
                    rate(first, top, bottom, picked, w) - rate(second, top, bottom, picked, w)
                )
            kept = np.array([g for g in gaps if not np.isnan(g)])
            low, high = np.quantile(kept, [0.025, 0.975])
            assert 0 < len(kept) < 400  # some draws hold no item of the denominator
            assert found[weighting][name]["ci95"] == {
                "low": pytest.approx(low),
                "high": pytest.approx(high),
                "draws": len(kept),
            }, (weighting, name)
    # the paired interval is not the gap between two intervals: a reader against itself
    same = LS.margin(LS.measured(scope, first), LS.measured(scope, first))
    assert same["sample"]["distractor_uptake"]["difference"] == 0.0
    assert same["sample"]["distractor_uptake"]["ci95"]["low"] == 0.0
    assert same["sample"]["distractor_uptake"]["ci95"]["high"] == 0.0


def test_a_margin_takes_each_reader_on_its_own_denominator() -> None:
    """A model is scored against the gold and an annotator against the other annotator's
    labels: the two rates have their own items below the line, and are paired by the draw."""
    golds = [g for _, g in CASES]
    scope = LS.Scope(
        ids=list("12345678"),
        golds=golds,
        strata=["x"] * 8,
        marked=list(MARKED),
        bases={"sample": np.ones(8)},
        taken=LS.item_draws(list("abcdefgh"), draws=300),
    )
    first = case_columns()
    # the other labels abstain on items 6 and 7 only and carry no distractor date; the reader
    # scored against them gives a date on item 6
    labels = [gold("recovery", *APRIL) for _ in CASES]
    labels[5], labels[6] = gold("recovery"), gold("none", certainty="no_statement")
    theirs = [g.reading for g in labels]
    theirs[5] = reading("recovery", *APRIL)
    second = LS.columns(theirs, labels, MARKED)
    found = LS.margin(LS.measured(scope, first), LS.measured(scope, second))["sample"]
    assert found["false_commitment"]["first"] == pytest.approx(1 / 3)  # of items 4, 5, 7
    assert found["false_commitment"]["second"] == pytest.approx(1 / 2)  # of items 6, 7
    assert found["false_commitment"]["difference"] == pytest.approx(1 / 3 - 1 / 2)
    drawn = P.cluster_draws(8, 300, LS.SEED).astype(float)
    mine = (drawn @ first["false_commitment"]) / np.where(
        drawn @ first["gold_abstains"] > 0, drawn @ first["gold_abstains"], np.nan
    )
    other = (drawn @ second["false_commitment"]) / np.where(
        drawn @ second["gold_abstains"] > 0, drawn @ second["gold_abstains"], np.nan
    )
    kept = (mine - other)[np.isfinite(mine - other)]
    low, high = np.quantile(kept, [0.025, 0.975])
    assert found["false_commitment"]["ci95"] == {
        "low": pytest.approx(low),
        "high": pytest.approx(high),
        "draws": len(kept),
    }
    # the draws that count hold an item of each denominator, and are fewer than either's own
    own = LS.measured(scope, first)["sample"][1]["false_commitment"]
    assert len(kept) < int(np.isfinite(own).sum()) < 300
    # a metric that one of the two readers lacks has no difference and no interval
    assert found["distractor_uptake"] == {
        "first": 1.0,
        "second": None,
        "difference": None,
        "ci95": None,
    }


def test_e2_margins_over_the_rule_reader_and_over_the_annotators(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]
    weightings = {"sample", "weighted_by_event", "weighted_by_template"}
    for model in rd.STUDY_MODELS:
        for template in (V1, FREE):
            found = whole["versus_rules"][model][template]["margins"]
            assert set(found) == weightings
            for weighting, by_metric in found.items():
                assert tuple(by_metric) == LS.MARGIN_METRICS
                for name, gap in by_metric.items():
                    mine = whole["readers"][model][template][weighting][name]["value"]
                    rules = whole["readers"]["rules"][weighting][name]["value"]
                    assert gap["first"] == mine and gap["second"] == rules
                    assert gap["difference"] == near(mine - rules)
                    assert gap["ci95"]["low"] <= gap["difference"] <= gap["ci95"]["high"]
    # values worked by hand: llama gives a date on one of the six gold-ABSTAIN items of the TBD
    # and silent strata, and takes up the distractor date of one of three items
    llama = whole["versus_rules"][LLAMA][V1]["margins"]["sample"]
    assert llama["false_commitment_tbd_or_silent"]["difference"] == near(1 / 6)
    assert llama["false_commitment"]["difference"] == near(1 / 7)
    assert llama["distractor_uptake"]["difference"] == near(1 / 3)
    # on those two strata the rule reader abstains by construction: the margin over the rules
    # is the model's own rate, with the model's own interval
    for model in (LLAMA, GEMMA):
        own = whole["readers"][model][V1]["sample"]["false_commitment_tbd_or_silent"]
        gap = whole["versus_rules"][model][V1]["margins"]["sample"][
            "false_commitment_tbd_or_silent"
        ]
        assert gap["second"] == 0.0 and gap["difference"] == own["value"]
        assert gap["ci95"] == own["ci95"]
    # the ceiling: each model against each annotator scored on the other one's labels
    beside = whole["versus_ceiling"]
    assert beside["computed"] is True and set(beside) == {"computed", *rd.STUDY_MODELS}
    names = {"A1_against_A2", "A2_against_A1"}
    for model in rd.STUDY_MODELS:
        assert set(beside[model]) == {V1, FREE}
        for template in (V1, FREE):
            assert set(beside[model][template]) == names
            for name in names:
                found = beside[model][template][name]
                assert set(found) == weightings
                for weighting, by_metric in found.items():
                    assert tuple(by_metric) == LS.MARGIN_METRICS
                    for metric, gap in by_metric.items():
                        mine = whole["readers"][model][template][weighting][metric]["value"]
                        human = whole["literal_ceiling"][name][weighting][metric]["value"]
                        assert gap["first"] == mine and gap["second"] == human
                        assert gap["difference"] == near(mine - human)
    # neither annotator gives a date where the other abstains, or takes up a distractor date
    gemma = beside[GEMMA][V1]["A1_against_A2"]["sample"]
    assert gemma["false_commitment_tbd_or_silent"]["difference"] == near(4 / 6)
    assert gemma["false_commitment_tbd_or_silent"]["ci95"]["high"] == 1.0
    assert beside[OSS][V1]["A2_against_A1"]["sample"]["distractor_uptake"]["difference"] == 1.0
    # the two templates of a model are compared as before, on correctness and IoU
    assert "margins" not in whole["literal_v1_versus_literal_free_v1"][GROK]


def test_e2_the_margins_over_the_ceiling_are_those_over_the_annotators(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    """On the made-up study no annotator gives a date where the other abstains or takes up a
    distractor date, and neither does the rule reader against the gold: over either comparator
    a margin is the model's own figure. Here the second annotator dates a TBD entry (item 12)
    and reads the expiry date of item 18 as its release, so the margins over the annotators
    part from the margins over the rules."""
    audit = tmp_path / "audit"
    shutil.copytree(study.audit, audit)
    name = f"{A.SUBMITTED_DIR}/literal_A2.csv"
    sheet, manifest = audit / name, audit / S.MANIFEST
    meta, rows = S.parse_sheet(sheet.read_text(encoding="utf-8"))
    other = {
        12: lab("recovery", "2020-06-01", "2020-06-30", "estimated"),
        18: TRUTH[18] | {"start": "2022-01-01", "end": "2022-01-31"},
    }
    rows = [row | other.get(number_of(row), {}) for row in rows]
    sheet.write_text(S.sheet_text(S.SHEET_COLUMNS, rows, meta), encoding="utf-8")
    record = json.loads(manifest.read_text())
    record["submitted"][name] = sha(sheet)
    manifest.write_text(json.dumps(record))
    report, _ = scored("e2", study, tmp_path, capsys, audit_dir=audit)
    whole, base = report["item_sets"]["all"], e2.report["item_sets"]["all"]
    for part in ("readers", "tests", "versus_rules", "positive_result"):
        assert whole[part] == base[part]  # the gold and the readings are as they were
    second = whole["literal_ceiling"]["A2_against_A1"]
    assert {m: second["sample"][m]["value"] for m in LS.MARGIN_METRICS} == {
        "false_commitment": near(1 / 7),
        "false_commitment_tbd_or_silent": near(1 / 6),
        "distractor_uptake": near(1 / 3),
    }
    first = whole["literal_ceiling"]["A1_against_A2"]
    assert first["n"]["gold_abstain"] == 6  # the first annotator dates no entry the second left
    assert {m: first["sample"][m]["value"] for m in LS.MARGIN_METRICS} == dict.fromkeys(
        LS.MARGIN_METRICS, 0.0
    )
    weightings = ("sample", "weighted_by_event", "weighted_by_template")
    for model in rd.STUDY_MODELS:
        for template in (V1, FREE):
            for weighting in weightings:
                beside = whole["versus_ceiling"][model][template]["A2_against_A1"][weighting]
                over_rules = whole["versus_rules"][model][template]["margins"][weighting]
                for metric in LS.MARGIN_METRICS:
                    mine = whole["readers"][model][template][weighting][metric]["value"]
                    human = second[weighting][metric]["value"]
                    assert whole["readers"]["rules"][weighting][metric]["value"] == 0.0 < human
                    assert beside[metric]["first"] == mine and beside[metric]["second"] == human
                    assert beside[metric]["difference"] == near(mine - human, abs=2e-6)
                    assert over_rules[metric]["second"] == 0.0
                    assert over_rules[metric]["difference"] == mine
                    assert beside[metric] != over_rules[metric], (model, template, metric)
            other_way = whole["versus_ceiling"][model][template]["A1_against_A2"]["sample"]
            assert all(other_way[metric]["second"] == 0.0 for metric in LS.MARGIN_METRICS)
    # llama dates the same TBD entry as the second annotator and no other: draw by draw the
    # two rates on the TBD and silent strata are one rate, and the margin is zero with an
    # interval of no width, where its margin over the rules keeps the width of its own rate
    name = "false_commitment_tbd_or_silent"
    paired = whole["versus_ceiling"][LLAMA][V1]["A2_against_A1"]["sample"][name]
    assert paired["first"] == paired["second"] == near(1 / 6)
    assert paired["difference"] == 0.0 and paired["ci95"]["low"] == paired["ci95"]["high"] == 0.0
    alone = whole["versus_rules"][LLAMA][V1]["margins"]["sample"][name]
    assert alone["difference"] == near(1 / 6) and alone["ci95"]["high"] > 0.3
    assert paired["ci95"]["draws"] == alone["ci95"]["draws"]


def test_the_lead_over_the_gold_items_with_a_distractor_date(e2: SimpleNamespace) -> None:
    """Three gold items carry a distractor date (18, 19 and 21); two of them give an interval.
    The two distractor rows hold four items (18 to 21), three of them with an interval."""
    lead = e2.report["item_sets"]["all"]["versus_rules"][LLAMA][V1]["iou"]
    assert lead["gold_with_distractor_date"]["items"] == 2
    assert lead["gold_with_distractor_date"]["difference"] == near(-1 / 2)  # the expiry on 18
    assert lead["distractor_rows"]["items"] == 3
    assert lead["distractor_rows"]["difference"] == near(-1 / 3)
    assert lead["dated_distractor"] == lead["gold_with_distractor_date"]


# --------------------------------------------------------------------------------------------
# E2: letter accuracy, the letter reading, exact intervals, the ceiling on every labelled item
# --------------------------------------------------------------------------------------------


def test_the_letter_reading_is_one_difference_per_draw_with_two_intervals() -> None:
    """PLAN section 5, E2, "Letter reading": the difference in letter accuracy over the letter
    items pooled without weights, with its 90% and its 95% percentile interval. Ten letter
    items of which the first reader has eight right and the second nine, and two items that
    are no letter items: the difference is one tenth below, to the last digit, in the figure
    and in every draw that takes each item once."""
    april = gold("recovery", *APRIL)
    golds = [april] * 10 + [gold("recovery"), gold("recovery", *APRIL, distractors=[APRIL])]
    right, off = reading("recovery", *APRIL), reading("recovery", "2020-06-01", "2020-06-30")
    first = LS.columns([off, off] + [right] * 8 + [reading("recovery"), off], golds)
    second = LS.columns([right, off] + [right] * 8 + [off, right], golds)
    scope = LS.Scope(
        ids=[f"I{k:02d}" for k in range(12)],
        golds=golds,
        strata=["x"] * 12,
        marked=[False] * 12,
        bases={"sample": np.ones(12), "weighted": np.array([4.0] + [1.0] * 11)},
        taken=np.ones((3, 12)),
    )
    found = LS.letter_gap(scope, first, second)
    assert set(found) == {"items", "sample", "weighted"} and found["items"] == 10
    assert found["sample"] == {
        "first": 0.8,
        "second": 0.9,
        "difference": -0.1,  # and not 0.8 - 0.9, which is -0.09999999999999998
        "ci90": {"low": -0.1, "high": -0.1, "draws": 3},
        "ci95": {"low": -0.1, "high": -0.1, "draws": 3},
    }
    assert 0.8 - 0.9 != -0.1
    # the first item weighs four: 8 of 13 against 12 of 13
    assert found["weighted"]["first"] == pytest.approx(8 / 13)
    assert found["weighted"]["second"] == pytest.approx(12 / 13)
    assert found["weighted"]["difference"] == pytest.approx(-4 / 13)
    # the two intervals over draws of clusters, written out one draw at a time in fractions; a
    # draw that takes no letter item is left out
    clusters = ["a"] * 3 + ["b"] * 7 + ["c", "d"]
    scope.taken = LS.item_draws(clusters, draws=500)
    found = LS.letter_gap(scope, first, second)["sample"]
    drawn = P.cluster_draws(4, 500, LS.SEED)
    gain = [-1, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # first minus second, item by item
    weights = {"sample": [1] * 10, "weighted": [4] + [1] * 9}
    gaps: dict[str, list[Fraction]] = {name: [] for name in weights}
    for row in drawn:
        times = [row["abcd".index(c)] for c in clusters[:10]]
        for name, w in weights.items():
            if sum(times):
                above = sum(t * g * k for t, g, k in zip(times, gain, w, strict=True))
                gaps[name].append(
                    Fraction(above, sum(t * k for t, k in zip(times, w, strict=True)))
                )
    kept = np.array([float(g) for g in gaps["sample"]])
    assert 0 < len(kept) < 500  # some draws hold the two other clusters alone
    for name, ends in (("ci90", [0.05, 0.95]), ("ci95", [0.025, 0.975])):
        low, high = np.quantile(kept, ends)
        assert found[name] == {
            "low": pytest.approx(low),
            "high": pytest.approx(high),
            "draws": len(kept),
        }
        # under the weights the first item counts four times, above and below the line
        low, high = np.quantile(np.array([float(g) for g in gaps["weighted"]]), ends)
        assert LS.letter_gap(scope, first, second)["weighted"][name] == {
            "low": pytest.approx(low),
            "high": pytest.approx(high),
            "draws": len(kept),
        }
        assert low < found[name]["low"]
    assert found["ci95"]["low"] <= found["ci90"]["low"] < found["difference"] == -0.1
    assert found["ci95"]["high"] == found["ci90"]["high"] == 0.0
    assert LS.interval90(np.arange(101.0)) == {"low": 5.0, "high": 95.0, "draws": 101}
    # it is part of every comparison of two readers; with no letter item there is none
    versus = LS.versus(scope, first, second)
    assert versus["letter_accuracy"]["sample"] == found
    nothing = LS.Scope(
        ids=["a", "b"],
        golds=golds[10:],
        strata=["x"] * 2,
        marked=[False] * 2,
        bases={"sample": np.ones(2)},
        taken=np.ones((3, 2)),
    )
    none = LS.letter_gap(
        nothing, LS.columns([right, off], golds[10:]), LS.columns([off, off], golds[10:])
    )
    assert none == {
        "items": 0,
        "sample": {"first": None, "second": None, "difference": None, "ci90": None, "ci95": None},
    }


LETTER = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 20, 23, 24)
"""The letter items of the made-up gold: the dated items but 18 and 19, which carry a
distractor date."""


def test_e2_letter_accuracy_and_the_letter_reading(
    study: SimpleNamespace, e2: SimpleNamespace
) -> None:
    """Letter accuracy of every reader, and its difference from the rule reader's with the two
    intervals. The rule reader is wrong on six letter items (7, 8, 10, 11, 23, 24); llama on
    one (the type of item 5); qwen on one (the failed reading of item 2); under the
    convention-free prompt every model reads items 5 and 6 as the whole month."""
    whole = e2.report["item_sets"]["all"]
    rows = gold_rows(study)
    assert tuple(n for n in GOLD if rows[n]["start"] and not rows[n]["distractor_quotes"]) == LETTER
    readers = whole["readers"]
    assert readers["rules"]["n"]["letter_items"] == 14
    assert readers["rules"]["sample"]["letter_accuracy"]["value"] == near(8 / 14)
    assert readers[LLAMA][V1]["sample"]["letter_accuracy"]["value"] == near(13 / 14)
    assert readers[QWEN][V1]["sample"]["letter_accuracy"]["value"] == near(13 / 14)
    for model in rd.STUDY_MODELS:
        expected = 13 / 14 if model in (LLAMA, QWEN) else 1.0
        assert readers[model][V1]["sample"]["letter_accuracy"]["value"] == near(expected)
        assert readers[model][FREE]["sample"]["letter_accuracy"]["value"] == near(12 / 14)
        assert readers[model][V1]["n"]["letter_items"] == 14
    # per stratum: the rule reader has one of the three part-of-month items wrong, and a
    # stratum without a letter item has no letter accuracy
    assert readers["rules"]["by_stratum"]["part_of_month"]["letter_accuracy"] == near(2 / 3)
    assert readers["rules"]["by_stratum"]["tbd"]["letter_accuracy"] is None
    assert readers["rules"]["by_stratum"]["dated_distractor"]["letter_accuracy"] is None
    assert readers["rules"]["by_stratum"]["distractor"]["n"]["letter_items"] == 1  # item 20
    # weighted by event the four month-and-year items weigh two each: 18 in all
    by_event = readers["rules"]["weighted_by_event"]["letter_accuracy"]["value"]
    assert by_event == near(12 / 18)
    # the letter reading: model minus rule reader, pooled without weights
    episodes = sorted({EPISODES.get(n, n) for n in GOLD})
    drawn = P.cluster_draws(len(episodes), 10_000, 20261001).astype(float)
    members = {k: [n for n in GOLD if EPISODES.get(n, n) == e] for k, e in enumerate(episodes)}
    rules_wrong = set(RULES_WRONG) & set(LETTER)
    assert len(rules_wrong) == 6
    for model, wrong in ((LLAMA, {5}), (DEEPSEEK, set()), (QWEN, {2})):
        found = whole["versus_rules"][model][V1]["letter_accuracy"]
        assert set(found) == {"items", "sample", "weighted_by_event", "weighted_by_template"}
        assert found["items"] == 14
        gain = np.array(
            [
                sum((n in rules_wrong) - (n in wrong) for n in members[k] if n in LETTER)
                for k in members
            ],
            dtype=float,
        )
        size = np.array([sum(n in LETTER for n in members[k]) for k in members], dtype=float)
        gaps = (drawn @ gain) / (drawn @ size)  # every draw of 22 episodes holds a letter item
        sample = found["sample"]
        assert sample["first"] == near((14 - len(wrong)) / 14) and sample["second"] == near(8 / 14)
        assert sample["difference"] == near((6 - len(wrong)) / 14)
        for name, ends in (("ci90", [0.05, 0.95]), ("ci95", [0.025, 0.975])):
            low, high = np.quantile(gaps, ends)
            assert sample[name] == {"low": near(low), "high": near(high), "draws": 10_000}
        assert sample["ci95"]["low"] <= sample["ci90"]["low"] < sample["difference"]
        assert sample["difference"] < sample["ci90"]["high"] <= sample["ci95"]["high"]
        # the figures are those of the two readers' own blocks
        for weighting in ("sample", "weighted_by_event", "weighted_by_template"):
            mine = readers[model][V1][weighting]["letter_accuracy"]["value"]
            rules = readers["rules"][weighting]["letter_accuracy"]["value"]
            assert found[weighting]["first"] == mine and found[weighting]["second"] == rules
            assert found[weighting]["difference"] == near(mine - rules, abs=2e-6)
    by_event = whole["versus_rules"][LLAMA][V1]["letter_accuracy"]["weighted_by_event"]
    assert by_event["first"] == near(17 / 18) and by_event["difference"] == near(5 / 18)
    assert by_event["ci90"]["low"] > by_event["ci95"]["low"]
    # the two templates of a model: the convention-free prompt loses two letter items
    templates = whole["literal_v1_versus_literal_free_v1"][GROK]["letter_accuracy"]["sample"]
    assert templates["difference"] == near(2 / 14)
    # the annotators: the letter items are those of the gold, the labels those of the other;
    # they differ on the intervals of items 6 and 10
    for name in ("A1_against_A2", "A2_against_A1"):
        ceiling = whole["literal_ceiling"][name]
        assert ceiling["n"]["letter_items"] == 14
        assert ceiling["sample"]["letter_accuracy"]["value"] == near(12 / 14)
    # in the report without the convention items (8 and 9) twelve letter items are left
    fewer = e2.report["item_sets"]["without_convention_items"]
    assert fewer["versus_rules"][LLAMA][V1]["letter_accuracy"]["items"] == 12
    assert fewer["versus_rules"][LLAMA][V1]["letter_accuracy"]["sample"]["second"] == near(7 / 12)


def test_e2_the_letter_items_of_an_annotator_are_those_of_the_gold(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    """The adjudicated gold fixes the letter items, also for an annotator scored against the
    other one's labels. Here the second annotator leaves item 9 without a date and names a
    distractor date on item 1: both stay letter items, and on item 9 the first annotator's
    date is not correct against a label that abstains."""
    audit = tmp_path / "audit"
    shutil.copytree(study.audit, audit)
    name = f"{A.SUBMITTED_DIR}/literal_A2.csv"
    sheet, manifest = audit / name, audit / S.MANIFEST
    meta, rows = S.parse_sheet(sheet.read_text(encoding="utf-8"))
    other = {
        9: lab("next_delivery", certainty="undetermined", reason="tbd"),
        1: TRUTH[1] | {"distractor_roles": "expiry", "distractor_quotes": "(1/2022 expiry)"},
    }
    rows = [row | other.get(number_of(row), {}) for row in rows]
    sheet.write_text(S.sheet_text(S.SHEET_COLUMNS, rows, meta), encoding="utf-8")
    record = json.loads(manifest.read_text())
    record["submitted"][name] = sha(sheet)
    manifest.write_text(json.dumps(record))
    report, _ = scored("e2", study, tmp_path, capsys, audit_dir=audit)
    whole = report["item_sets"]["all"]
    assert whole["readers"] == e2.report["item_sets"]["all"]["readers"]
    for name in ("A1_against_A2", "A2_against_A1"):
        found = whole["literal_ceiling"][name]
        assert found["n"]["letter_items"] == 14  # and not the 13 dated labels without a quote
        assert found["sample"]["letter_accuracy"]["value"] == near(11 / 14)  # items 6, 9, 10
    # by its own labels the second annotator has 13 dated items without a distractor date
    assert whole["literal_ceiling"]["A1_against_A2"]["n"]["gold_interval"] == 15
    assert whole["literal_ceiling"]["A1_against_A2"]["n"]["gold_with_distractor_date"] == 4


def test_e2_the_rates_have_their_counts_and_an_exact_interval(e2: SimpleNamespace) -> None:
    """PLAN section 13, "Support": false commitment and distractor uptake with their counts and
    the exact binomial interval beside the percentile one, for every reader."""
    whole = e2.report["item_sets"]["all"]
    llama = whole["readers"][LLAMA][V1]
    assert list(llama) == [
        "n",
        "exact",
        "sample",
        "weighted_by_event",
        "weighted_by_template",
        "by_stratum",
    ]
    assert tuple(llama["exact"]) == LS.MARGIN_METRICS == tuple(LS.RATE_COLUMNS)
    for name, (count, items) in {
        "false_commitment": (1, 7),
        "false_commitment_tbd_or_silent": (1, 6),
        "distractor_uptake": (1, 3),
    }.items():
        found = llama["exact"][name]
        exact = stats.binomtest(count, items).proportion_ci(0.95, method="exact")
        assert (found["count"], found["items"]) == (count, items)
        assert found["ci95"] == {"low": near(exact.low), "high": near(exact.high)}
        assert llama["sample"][name]["value"] == near(count / items)
        assert found["ci95"]["low"] < count / items < found["ci95"]["high"]
    # the rule reader gives no date on a gold-ABSTAIN item: an interval from zero
    rules = whole["readers"]["rules"]["exact"]["false_commitment"]
    assert rules == {
        "count": 0,
        "items": 7,
        "ci95": {"low": 0.0, "high": near(1 - 0.025 ** (1 / 7))},
    }
    # gemma dates four of the six, and each annotator against the other none
    gemma = whole["readers"][GEMMA][V1]["exact"]["false_commitment_tbd_or_silent"]
    assert (gemma["count"], gemma["items"]) == (4, 6)
    for name in ("A1_against_A2", "A2_against_A1"):
        assert whole["literal_ceiling"][name]["exact"]["distractor_uptake"]["count"] == 0
    # the function, at its ends
    assert LS.exact95(0, 0) is None
    assert LS.exact95(5, 5) == {"low": pytest.approx(0.025 ** (1 / 5)), "high": 1.0}
    assert LS.exact95(0, 22) == {"low": 0.0, "high": pytest.approx(1 - 0.025 ** (1 / 22))}
    middle = LS.exact95(3, 10)
    assert stats.binom.sf(2, 10, middle["low"]) == pytest.approx(0.025)
    assert stats.binom.cdf(3, 10, middle["high"]) == pytest.approx(0.025)


def test_e2_the_ceiling_of_section_8_is_on_every_item_both_labelled(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    """PLAN section 8: the double-labelled items give the ceiling. The made-up sample has 24 of
    them and a gold of 23: item 22 was labelled apart (another certainty class, another reason)
    and left out of the gold. The ceiling on every labelled item holds it; the ceiling of an
    item set does not."""
    found = e2.report["literal_ceiling_on_every_labelled_item"]
    assert list(found) == [
        "computed",
        "A1_against_A2",
        "A2_against_A1",
        "items",
        "items_left_out_of_the_gold",
    ]
    assert found["computed"] is True
    assert (found["items"], found["items_left_out_of_the_gold"]) == (24, 1)
    inside = e2.report["item_sets"]["all"]["literal_ceiling"]
    for name in ("A1_against_A2", "A2_against_A1"):
        every, gold_items = found[name], inside[name]
        assert every["n"]["items"] == 24 and gold_items["n"]["items"] == 23
        # the two differ on the certainty class of items 3 and 22
        assert every["sample"]["certainty_accuracy"]["value"] == near(22 / 24)
        assert gold_items["sample"]["certainty_accuracy"]["value"] == near(22 / 23)
        # both abstain on item 22, under one type: correct by the E2 rule
        assert every["sample"]["correct"]["value"] == near(22 / 24)
        assert every["n"]["gold_abstain"] == 8 and gold_items["n"]["gold_abstain"] == 7
        assert every["by_stratum"]["vague"]["n"]["items"] == 1
        assert "vague" not in gold_items["by_stratum"]
        # an item left out of the gold is no letter item
        assert every["n"]["letter_items"] == 14
        assert every["sample"]["letter_accuracy"]["value"] == near(12 / 14)
        # by event the vague stratum weighs its one statement, 31 in all; item 3 weighs two
        assert every["weighted_by_event"]["certainty_accuracy"]["value"] == near(28 / 31)
        assert gold_items["weighted_by_event"]["certainty_accuracy"]["value"] == near(28 / 30)
        assert every["sample"]["correct"]["ci95"]["draws"] == 10_000
    # without the sheets there is no ceiling of either kind, and the result says why
    sheet = study.audit / "submitted" / "literal_A2.csv"
    with changed(sheet):
        sheet.unlink()
        report, _ = scored("e2", study, tmp_path, capsys)
    assert report["literal_ceiling_on_every_labelled_item"] == {
        "computed": False,
        "why": "the submitted sheet of A2 is not under the audit folder",
    }


def test_the_list_holds_what_the_plan_leaves_open_and_nothing_it_states(
    e2: SimpleNamespace, e5: SimpleNamespace
) -> None:
    """What the plan states is no silence of the plan: what "by form" means in the literal
    task, what the two weights undo, the error of an unedited seed item, what calls the
    fallback and its p-value, where the list of convention items is kept, the item sets of the
    positive result, that a dropped model is still scored, what a failed reading counts as,
    what the statement text is, what a distractor's interval is, which items the sensitivity
    analysis keeps, that the marks of the positive result are no test, and the registered
    pattern of section 13. The list keeps what the scorer decides beyond that, and each of
    those is true of the code."""
    silent = LS.WHERE_THE_PLAN_IS_SILENT
    assert e2.report["where_the_plan_is_silent"] == list(silent)
    assert e5.report["where_the_plan_is_silent"] == list(silent)
    assert len(silent) == len(set(silent)) == 24
    text = " | ".join(silent)
    stated = (
        "results by form",  # sections 2.6 and 5, E2: by stratum of the guide's table
        "undo the allocation",  # section 7.1: what the two weights correct
        "cap of two items",
        "one-third share",
        "inside a stratum every scored item counts the same",
        "is an error when it is not correct",  # E5, Target: the error of an unedited item
        "same error on both sides",
        "does not converge",  # E5, Fallback: what calls it
        "never decide the procedure",
        "percentile p-value of section 6",  # and its p-value
        "literal_convention_items.csv",  # E2, Gold: where the list is kept, and the family
        "has no column",
        "registered family of E2",
        "against the 5% bar",  # E2, Positive result: its item sets
        "for each of the two distractor rows of the guide's table and for both together",
        "sections 9 or 12",  # E2, Readers: a dropped model is still scored
        "guard of form",  # E5, Fallback: fewer than two seeds
        "measurably",  # section 13 holds a registered pattern, and no such word
        "of exactly 0.10",  # section 13, Small points of the reading: each of these
        "exactly -0.10",
        "whose gold gives no period",
        "E2 run of the pattern",
        "plan of the runs",
        "procedure in force",
        "withheld by",
        "the other has none",
        "lowest draw_rank",  # section 12, cut 4
        "registered rows of those seeds",
        "every primary with a pattern",  # section 13, Support: each factor that counts
        "no registered procedure",
        "counts as ABSTAIN",  # section 4: a failed literal reading
        "on the items both readers parsed",  # section 4: the sensitivity analysis
        "more than a bare label",  # section 2.3: the statement text
        "a distractor's interval is",  # section 7.1
        "decide no test",  # E2, Positive result: the three marks are descriptions
        "decides no test",
        "same metrics, on the gold items",  # section 8: the ceiling is of the labelled items
        "its absence is declared",  # E2, Gold: there is a list in every case
    )
    for words in stated:
        assert words not in text, words
    kept = {
        "the frame of the two weights of section 7.1": "gives its frame no weight",
        "the list of convention items is held to a sha256": "a Holm of their own",
        "the two bars of the positive result": "read on the sample figures, model by model",
        "E5: the GEE is fitted reader by reader": "B is the number of draws that hold an item",
        "E5: a test that is not evaluable": "counted on each of its sides",
        "a run declared not run": "is refused",
        "a reading that failed or was refused": "has the stale flag false",
        "the quoted words of a distractor": "uptake is counted against any of them",
        "the exact McNemar test is two-sided": "with a p-value outside Holm's rule",
        "the rule reading of an item is made here": "the two text fields of the item file",
        "with two annotators the leave-one-out ceiling": "on every item both labelled",
        "the letter reading of E2": "from the 5th to the 95th percentile",
        "E5: beside the own error of a standing factor": "the twelve tests alone",
        "the pattern: every decision is taken on whole numbers": "as an exact fraction",
        "E5, cut (section 12)": "byte for byte",
        "the pattern: that E5 is not scored is declared": "--e5-not-scored",
        "the pattern: both results must be written": "a file that cannot be read whole",
        "E5: the gold of the minimal pairs": "the manifest of the generator is not read",
        "beside the rates that section 13 lists as support": "paired by the draw alone",
    }
    for begins, words in kept.items():
        (entry,) = [e for e in silent if e.startswith(begins)]
        assert words in entry, begins
    # the description of the scorer follows the plan's words and names where they stand
    document = " ".join((LS.__doc__ or "").split())
    assert 'which is "by form" in the literal task (PLAN sections 2.6 and 5)' in document
    assert "as PLAN section 7.1 defines the two weights" in document
    assert "every scored item of a stratum counts the same" in document
    assert "is held to the criterion of the factor it is compared with" in document
    assert "(1 + #{|d* - d| >= |d|}) / (B + 1)" in document and "enters no rule" in document
    assert "like_for_like" not in document and "same error on both" not in document
    assert "measurably" not in document and "no-convention-items" not in document
    assert "lie on fewer than two seeds" in document
    assert "Neither command applies the floors" not in document
    assert "``e2`` decides nothing else of the pattern" in document
    assert "A contrast of another model has no floors" in document
    assert "No secondary model has a pattern" in document
    # two items of one stratum weigh the same, whatever their template or their period
    weights, _ = LS.stratum_weights(["silent"] * 4, {"silent": 1000}, "statement")
    assert weights.tolist() == [250.0] * 4
    # a stratum of the frame with no scored item weighs nothing
    sizes = {"tbd": 10, "silent": 7, "range": 99}
    weights, strata = LS.stratum_weights(["tbd", "tbd", "silent"], sizes, "statement")
    assert weights.tolist() == [5.0, 5.0, 7.0] and strata == ["silent", "tbd"]


# --------------------------------------------------------------------------------------------
# The result file keeps its small p-values
# --------------------------------------------------------------------------------------------


def test_a_p_value_keeps_six_significant_digits_in_the_result_file() -> None:
    """Thirty items only the first reader has right: the exact p-value is 2 / 2**30. At six
    decimals it would read 0.0, beside a Holm value and a decision that say otherwise."""
    lone = LS.mcnemar([True] * 30 + [False] * 78, [False] * 108)
    tests = LS.family([{"model": "a"} | lone, {"p": 0.5}])
    report = {"tests": tests, "share": 1 / 3, "gee": {"p": 2e-9, "z": 6.0}, "bad": float("nan")}
    report |= {"count": np.int64(3), "rate": np.float64(0.1234567), "row": (1.0, 2e-9)}
    text = LS.report_text(report)
    found = json.loads(text)
    assert found["tests"][0]["p"] == pytest.approx(2 * 0.5**30, rel=1e-5)
    assert found["tests"][0]["p"] > 0
    assert found["tests"][0]["p_holm"] == pytest.approx(4 * 0.5**30, rel=1e-5)
    assert found["tests"][0]["holds"] is True and found["tests"][1]["holds"] is False
    assert found["gee"] == {"p": 2e-9, "z": 6.0}
    assert found["share"] == 0.333333 and found["bad"] is None
    assert found["count"] == 3 and found["rate"] == 0.123457
    assert found["row"] == [1.0, 0.0]  # a float under no p-value's name has six decimals
    assert found["tests"][1] == {"p": 0.5, "p_holm": 0.5, "holds": False}
    assert text.endswith("\n") and text.startswith('{\n "tests": [')
    # six significant digits, and no more
    assert json.loads(LS.report_text({"p": 0.000123456789}))["p"] == 0.000123457
    assert json.loads(LS.report_text({"p_holm": 1 / 3}))["p_holm"] == 0.333333
    # the percentile p-value of a bootstrap contrast is a p-value too
    beside = {"bootstrap": {"p": 0.000123456789, "p_percentile": 0.000234567891, "draws": 7}}
    assert json.loads(LS.report_text(beside))["bootstrap"] == {
        "p": 0.000123457,
        "p_percentile": 0.000234568,
        "draws": 7,
    }
    assert LS.P_FIELDS == ("p", "p_holm", "p_percentile")
    # every other number is written as the evaluator writes it
    plain = {"a": [1 / 3, {"b": 2 / 3, "c": float("inf")}], "n": 5, "s": "text", "t": True}
    assert LS.report_text(plain) == ev.report_text(plain)


@pytest.mark.parametrize("command", ["e2", "e5"])
def test_the_result_file_is_the_scorers_own_text_of_the_report(
    command: str, study: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Mapping[str, Any]] = []
    real = LS.report_text

    def watched(report: Mapping[str, Any]) -> str:
        seen.append(report)
        return real(report)

    monkeypatch.setattr(LS, "report_text", watched)
    out = fresh(tmp_path)
    assert LS.main(ARGS[command](study, out)) == 0
    assert len(seen) == 1 and out.read_text() == real(seen[0])
    # a p-value below 0.1 is written with more than six decimals: six digits that count
    small = [float(found) for found in re.findall(r'"p(?:_holm)?": (0\.0\d+)', out.read_text())]
    assert small and all(float(f"{p:.6g}") == p for p in small)
    if command == "e5":  # Wald p-values, which no six decimals hold
        assert any(round(p, 6) != p for p in small)


def test_no_p_value_of_a_result_reads_zero(e2: SimpleNamespace, e5: SimpleNamespace) -> None:
    def p_values(value: Any, key: str = "") -> Iterator[float]:
        if isinstance(value, dict):
            for name, item in value.items():
                yield from p_values(item, name)
        elif isinstance(value, list):
            for item in value:
                yield from p_values(item)
        elif key in LS.P_FIELDS:
            yield value

    for report in (e2.report, e5.report):
        found = list(p_values(report))
        assert len(found) > 12 and all(0 < p <= 1 for p in found)


# --------------------------------------------------------------------------------------------
# The pins: the frozen rule reader, the item file the runs read, the gold of the manifest
# --------------------------------------------------------------------------------------------

GENERAL = (
    "refused: no score before every run of the experiment is complete on its registered item "
    "list, route and template: "
)


def items_with(source: Path, tmp_path: Path, change: Callable[[list[dict]], None]) -> Path:
    """A copy of an item file with its rows passed through ``change``."""
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    change(rows)
    path = tmp_path / f"changed_{source.name}"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return path


def e5_gold_with(
    study: SimpleNamespace, tmp_path: Path, change: Callable[[list[dict]], None]
) -> Path:
    rows = list(csv.DictReader(study.e5_gold.open(encoding="utf-8")))
    change(rows)
    path = tmp_path / "e5_gold.csv"
    path.write_text(MP.plain_csv(MP.GOLD_COLUMNS, rows), encoding="utf-8")
    return path


def test_the_rule_reader_must_be_the_frozen_file(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule reader is the comparator of the registered tests of E2 and reads the distractor
    dates of both golds: with another file under its name, neither command scores."""
    assert sha(Path(R.__file__)).startswith(F.RULES_SHA256) and len(F.RULES_SHA256) == 16
    LS.frozen_rules()  # the file of the repository is the frozen one
    other = tmp_path / "rules.py"
    other.write_bytes(Path(R.__file__).read_bytes() + b"\n# one more line\n")
    monkeypatch.setattr(R, "__file__", str(other))
    for command in ("e2", "e5"):
        why = refused(command, study, tmp_path, capsys)
        assert why == (
            f"refused: rules.py is not the frozen rule reader (sha256 prefix {F.RULES_SHA256})"
        )
    # the gold comes first: without it nothing else is looked at
    why = refused("e5", study, tmp_path, capsys, gold=tmp_path / "none.csv")
    assert why.startswith("refused: the gold of the minimal pairs is not there")


def test_the_item_file_given_is_the_file_the_runs_read(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    e2: SimpleNamespace,
    e5: SimpleNamespace,
) -> None:
    """The ids of an item do not depend on its text or its date, so a file with the same ids
    can hold other statements than the models read. The rule reader reads the file given."""
    source = study.audit / "literal_items.jsonl"

    def reworded(rows: list[dict]) -> None:
        row = next(row for row in rows if row["item_id"] == study.ids[7])
        row["availability_information"] = "Next release June 2020."

    why = refused("e2", study, tmp_path, capsys, items=items_with(source, tmp_path, reworded))
    assert why == (
        f"{GENERAL}the item file given is not the file of the plan's item list 'e2', which the "
        "runs read"
    )
    assert not [item for item in study.items if item in why]

    def other_texts(rows: list[dict]) -> None:
        for row in rows[:20]:
            row["availability_information"] = "Backordered. Next release in November 2020."

    def other_day(rows: list[dict]) -> None:
        rows[3]["date_of_update"] = "2020-08-14"

    for change in (other_texts, other_day):
        items = items_with(study.e5_items, tmp_path, change)
        why = refused("e5", study, tmp_path, capsys, items=items)
        assert why == (
            f"{GENERAL}the item file given is not the file of the plan's item list 'e5', which "
            "the runs read"
        )
    # the same bytes under another path are the same file
    for command, path, base in (("e2", source, e2.report), ("e5", study.e5_items, e5.report)):
        copy = tmp_path / f"copy_of_{path.name}"
        shutil.copy(path, copy)
        report, _ = scored(command, study, tmp_path, capsys, items=copy)
        assert report["inputs"]["items"] == copy.as_posix()
        assert report["inputs"]["items_sha256"] == base["inputs"]["items_sha256"]
        assert result_of(report, "items") == result_of(base, "items")
    # a plan made before the item file was on disk holds no hash for it
    plan = lp.plan_path(study.runs)
    with json_with(plan, lambda record: record["lists"]["e5"].update(sha256=None)):
        why = refused("e5", study, tmp_path, capsys)
    assert "the item file given is not the file of the plan's item list 'e5'" in why


def test_the_code_record_names_what_the_numbers_depend_on(
    e2: SimpleNamespace, e5: SimpleNamespace
) -> None:
    named = {"literal_scores.py": LS, "rules.py": R, "read.py": rd, "audit_sample.py": S}
    named |= {"evaluate.py": ev, "forms.py": F, "corpus.py": C, "predictors.py": P}
    for report in (e2.report, e5.report):
        code = report["inputs"]["code"]
        assert set(named) <= set(code)
        for name, module in named.items():
            assert code[name] == sha(Path(module.__file__)), name


def test_e2_the_gold_is_the_one_the_audit_manifest_records(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    e2: SimpleNamespace,
) -> None:
    """A gold changed after adjudication, or a part of it, given with its own hash: it is a
    gold of the item file, and not the one the agreement script wrote. No reading is opened."""
    opened: list[str] = []
    real = LS.ev.read_group

    def watched(*args: Any, **kwargs: Any) -> Any:
        opened.append("runs")
        return real(*args, **kwargs)

    monkeypatch.setattr(LS.ev, "read_group", watched)

    def gold_with(change: Callable[[list[dict]], None]) -> Path:
        rows = list(csv.DictReader(study.gold.open(encoding="utf-8")))
        change(rows)
        path = tmp_path / "gold.csv"
        path.write_text(S.plain_csv(A.GOLD_COLUMNS, rows), encoding="utf-8")
        return path

    def relabelled(rows: list[dict]) -> None:
        row = next(row for row in rows if row["item_id"] == study.ids[7])
        row.update(start="2020-06-21", end="2020-06-30")  # the rule reading of item 7

    for change in (relabelled, lambda rows: rows.__delitem__(slice(1, None))):
        path = gold_with(change)
        why = refused("e2", study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))
        assert why == (
            "refused: the gold is not the one the audit manifest records: its sha256 is "
            f"{sha(path)}, and the manifest holds {sha(study.gold)}; a gold changed by a dated "
            "amendment is written again by audit_agreement gold"
        )
    # the gold is held to the whole hash of the manifest. A record that parts from the gold's
    # hash in its last character, or that is its beginning alone, is the hash of another file
    manifest = study.audit / S.MANIFEST
    whole = sha(study.gold)
    other_end = whole[:-1] + ("0" if whole[-1] != "0" else "1")
    for recorded in (other_end, whole[:16], whole[:63]):

        def record_it(record: dict, recorded: str = recorded) -> None:
            record["gold"]["sha256"] = recorded

        with json_with(manifest, record_it):
            why = refused("e2", study, tmp_path, capsys)
        assert why == (
            "refused: the gold is not the one the audit manifest records: its sha256 is "
            f"{whole}, and the manifest holds {recorded}; a gold changed by a dated amendment is "
            "written again by audit_agreement gold"
        )
    # a manifest that is there and cannot be read holds the gold to nothing: refused
    for data, kind in (
        (b"{ not JSON", "JSONDecodeError"),
        (b"[1, 2]", "not an object"),
        (b"\xff", "UnicodeDecodeError"),
    ):
        with changed(manifest):
            manifest.write_bytes(data)
            why = refused("e2", study, tmp_path, capsys)
        assert why == f"refused: the audit manifest cannot be read ({kind})"
    assert opened == []
    # a manifest with no record of a gold is the state of the folder before the gold is fixed,
    # and a folder with no manifest holds the gold to nothing: neither is scored, whatever gold
    # file is given under its own hash
    no_record = (
        f"refused: the audit manifest holds no record of a gold ({manifest.as_posix()}): the "
        "gold of the literal task is the file that audit_agreement gold writes and records "
        "there, and no reading is compared with another"
    )
    hand_made = gold_with(relabelled)
    with json_with(manifest, lambda record: record.pop("gold")):
        assert refused("e2", study, tmp_path, capsys) == no_record
        why = refused(
            "e2", study, tmp_path, capsys, gold=hand_made, expect_gold_sha256=sha(hand_made)
        )
        assert why == no_record
    with json_with(manifest, lambda record: record["gold"].update(sha256="")):
        assert refused("e2", study, tmp_path, capsys) == no_record
    copy = tmp_path / "audit"
    shutil.copytree(study.audit, copy)
    (copy / S.MANIFEST).unlink()
    for given in (study.gold, hand_made):
        why = refused(
            "e2", study, tmp_path, capsys, audit_dir=copy, gold=given, expect_gold_sha256=sha(given)
        )
        assert why == no_record.replace(manifest.as_posix(), (copy / S.MANIFEST).as_posix())
    # an empty folder named as the folder of the task, with every file of the task named apart
    empty = tmp_path / "empty"
    empty.mkdir()
    named = {
        "audit_dir": empty,
        "gold": hand_made,
        "expect_gold_sha256": sha(hand_made),
        "items": study.audit / LS.E2_ITEMS,
    }
    extra = ("--convention-items", str(study.marks))
    why = refused("e2", study, tmp_path, capsys, *extra, **named)
    assert why == no_record.replace(manifest.as_posix(), (empty / S.MANIFEST).as_posix())
    assert opened == []
    # with its record the gold is scored, and the result holds the hash the manifest records
    assert e2.report["inputs"]["gold_sha256_in_the_audit_manifest"] == sha(study.gold)
    assert e2.report["inputs"]["gold_sha256"] == sha(study.gold)
    report, _ = scored("e2", study, tmp_path, capsys)
    assert report["item_sets"] == e2.report["item_sets"] and opened != []
    # the function: the recorded hash, or none
    assert LS.manifest_gold_sha256(study.audit) == sha(study.gold)
    assert LS.manifest_gold_sha256(copy) is None
    (copy / S.MANIFEST).write_text('{"gold": {"sha256": ""}, "submitted": {}}')
    assert LS.manifest_gold_sha256(copy) is None


# --------------------------------------------------------------------------------------------
# Declarations of runs not run are held to the check of those runs
# --------------------------------------------------------------------------------------------

SCORED_ALL_THE_SAME = (
    "refused: --not-run names runs that are complete on the registered item list, route and "
    "template, and such runs are scored: "
)


def test_a_declaration_for_runs_that_can_be_scored_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A model whose runs are complete is scored: leaving it out is no choice of the command
    line once the readings exist."""
    for command, model, runs in (("e2", GEMINI, 2), ("e2", DEEPSEEK, 2), ("e5", GROK, 1)):
        why = refused(command, study, tmp_path, capsys, "--not-run", f"{model}=cap reached")
        assert why == f"{SCORED_ALL_THE_SAME}{model} ({runs} runs)"
    why = refused("e2", study, tmp_path, capsys, "--not-run", f"{LLAMA}/{FREE}=cap reached")
    assert why == f"{SCORED_ALL_THE_SAME}{LLAMA}/{FREE} (1 runs)"
    extra = ["--not-run", f"{QWEN}=a", "--not-run", f"{GROK}/{V1}=b"]
    why = refused("e2", study, tmp_path, capsys, *extra)
    assert why == f"{SCORED_ALL_THE_SAME}{QWEN} (2 runs), {GROK}/{V1} (1 runs)"
    # a declaration that stands does not excuse one that does not
    with with_manifest(study, run_of("e5", QWEN), complete=False):
        extra = ["--not-run", f"{QWEN}=cap", "--not-run", f"{GROK}=cap"]
        why = refused("e5", study, tmp_path, capsys, *extra)
    assert why == f"{SCORED_ALL_THE_SAME}{GROK} (1 runs)"
    # a model with no error on a cell of the minimal pairs is no exception
    with always_right_on(study, GROK, "silent"):
        why = refused("e5", study, tmp_path, capsys, "--not-run", f"{GROK}=cap")
    assert why == f"{SCORED_ALL_THE_SAME}{GROK} (1 runs)"


@pytest.mark.parametrize("case", list(REFUSED_RUNS))
def test_a_declaration_stands_when_the_check_of_its_runs_finds_a_problem(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    e2: SimpleNamespace,
    case: str,
) -> None:
    """Everything that makes the scorer refuse a run makes its model declarable; the result
    records the state of each declared run and what the check found, without an item."""
    line, model, change, reason = REFUSED_RUNS[case]
    DROPPED[:] = [study.ids[7]]
    with change(study, run_of(line, model)):
        report, _ = scored("e2", study, tmp_path, capsys, "--not-run", f"{model}=why")
    assert set(report["not_run_checked"]) == {model}
    checked = report["not_run_checked"][model]
    assert set(checked) == set(LS.E2_LINES.values())
    assert any(reason in gap for gap in checked[line]["found"]), checked[line]["found"]
    assert all(gap.startswith(f"{model} {line}: ") for gap in checked[line]["found"])
    assert set(checked[line]["runs"]) == {run_of(line, model)}
    assert checked[line]["runs"][run_of(line, model)] in ("partial", "mismatch", "finished")
    (other,) = set(checked) - {line}
    assert checked[other] == {"runs": {run_of(other, model): "finished"}, "found": []}
    text = json.dumps(report["not_run_checked"])
    assert not [item for item in study.items if item in text]
    whole = report["item_sets"]["all"]
    assert model not in whole["readers"] and model not in report["runs"]
    kept = next(m for m in rd.STUDY_MODELS if m not in (model, *rd.PRIMARIES))
    assert whole["readers"][kept] == e2.report["item_sets"]["all"]["readers"][kept]


def test_one_template_of_a_model_can_be_declared_not_run(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    """E2 reads a model under two templates, and its registered test needs ``literal-v1``
    alone: a primary whose convention-free run is not complete keeps its test."""
    whole = e2.report["item_sets"]["all"]
    free, first = run_of("e2-literal-free", LLAMA), run_of("e2-literal", LLAMA)
    with with_manifest(study, free, complete=False):
        assert f"{LLAMA} e2-literal-free: run {free} is not finished" in refused(
            "e2", study, tmp_path, capsys
        )
        report, printed = scored(
            "e2", study, tmp_path, capsys, "--not-run", f"{LLAMA}/{FREE}= cap reached "
        )
    found = report["item_sets"]["all"]
    assert found["tests"] == whole["tests"]
    # the letter part of the pattern reads literal-v1 alone: the letter reading stands
    assert found["letter_reading"] == whole["letter_reading"]
    assert found["positive_result"] == whole["positive_result"]
    assert found["versus_rules"][LLAMA] == {V1: whole["versus_rules"][LLAMA][V1]}
    assert found["readers"][LLAMA] == {V1: whole["readers"][LLAMA][V1]}
    assert set(found["versus_ceiling"][LLAMA]) == {V1} and set(report["runs"][LLAMA]) == {V1}
    assert LLAMA not in found["literal_v1_versus_literal_free_v1"]
    assert set(found["literal_v1_versus_literal_free_v1"]) == set(rd.STUDY_MODELS) - {LLAMA}
    assert report["not_run"] == LS.NORMALISERS_NOT_RUN | {
        f"{LLAMA}/{FREE}": "declared on the command line: cap reached"
    }
    assert report["not_run_checked"][f"{LLAMA}/{FREE}"]["e2-literal-free"]["runs"] == {
        free: "partial"
    }
    assert set(report["not_run_checked"]) == {f"{LLAMA}/{FREE}"}
    assert f"{LLAMA} {V1}" in report["per_item"]["readers"]
    assert f"{LLAMA} {FREE}" not in report["per_item"]["readers"]
    assert f"{LLAMA} {V1}" in printed and f"{LLAMA} {FREE}" not in printed
    # the run of the registered template declared: the test stays in the family with p = 1,
    # and the readings under the other template are kept
    with with_manifest(study, run_of("e2-literal", DEEPSEEK), complete=False):
        report, printed = scored(
            "e2", study, tmp_path, capsys, "--not-run", f"{DEEPSEEK}/{V1}=no route"
        )
        # one template declared does not excuse the other: here the wrong one is named
        why = refused("e2", study, tmp_path, capsys, "--not-run", f"{DEEPSEEK}/{FREE}=cap")
        assert why == f"{SCORED_ALL_THE_SAME}{DEEPSEEK}/{FREE} (1 runs)"
    found = report["item_sets"]["all"]
    assert found["tests"][1] == {
        "model": DEEPSEEK,
        "template": V1,
        "against": "rules",
        "evaluable": False,
        "why": "declared on the command line: no route",
        "p": 1.0,
        "p_holm": 1.0,
        "holds": False,
    }
    assert found["letter_reading"] == [
        whole["letter_reading"][0],
        {
            "model": DEEPSEEK,
            "template": V1,
            "against": "rules",
            "evaluable": False,
            "why": "declared on the command line: no route",
        },
    ]
    assert found["readers"][DEEPSEEK] == {FREE: whole["readers"][DEEPSEEK][FREE]}
    assert DEEPSEEK not in found["positive_result"]
    assert f"all: {DEEPSEEK} against the rules: not run, p = 1" in printed
    # with both runs of a model not complete, one declaration leaves the other run in the way
    with with_manifest(study, free, complete=False), with_manifest(study, first, complete=False):
        why = refused("e2", study, tmp_path, capsys, "--not-run", f"{LLAMA}/{FREE}=cap")
        assert why.startswith(GENERAL) and f"run {first} is not finished (partial)" in why
        assert free not in why
    # what the option takes
    for bad in (
        [f"{LLAMA}/literal-v2=a"],
        [f"{LLAMA}/=a"],
        [f"/{V1}=a"],
        [f"{LLAMA}/{V1}=a", f"{LLAMA}/{V1}=b"],
        [f"{LLAMA}=a", f"{LLAMA}/{V1}=b"],
        [f"{LLAMA}/{V1}=a", f"{LLAMA}=b"],
        [f"{LLAMA}/{V1}= "],
    ):
        extra = [part for value in bad for part in ("--not-run", value)]
        why = refused("e2", study, tmp_path, capsys, *extra)
        assert why == (
            f"refused: --not-run takes MODEL=REASON, once for a model of {list(LS.E2_MODELS)}; "
            f"or MODEL/TEMPLATE=REASON for one of {[V1, FREE]}"
        )
    # the minimal pairs have one template: no model is declared by halves there
    why = refused("e5", study, tmp_path, capsys, "--not-run", f"{QWEN}/{V1}=a")
    assert why == f"refused: --not-run takes MODEL=REASON, once for a model of {list(LS.E5_MODELS)}"
    assert LS.declared([f"{QWEN}/{FREE}=x", f"{GROK}=y"], LS.E2_MODELS, (V1, FREE)) == {
        f"{QWEN}/{FREE}": "declared on the command line: x",
        GROK: "declared on the command line: y",
    }
    skipped = {f"{QWEN}/{FREE}": "one", GROK: "all"}
    assert (
        LS.why_not_read(skipped, QWEN, FREE) == "one" and LS.why_not_read(skipped, QWEN, V1) is None
    )
    assert LS.why_not_read(skipped, GROK, V1) == LS.why_not_read(skipped, GROK, FREE) == "all"
    assert LS.why_not_read(skipped, LLAMA, V1) is None


# --------------------------------------------------------------------------------------------
# A plan, a manifest or a stored row that is not as it is written is a refusal
# --------------------------------------------------------------------------------------------

CELL = "back in stock soon, per the notice"


@contextmanager
def run_files(
    study: SimpleNamespace,
    run: str,
    readings: Callable[[str], str] | None = None,
    manifest: Callable[[str], str | None] | None = None,
    rehash: bool = False,
) -> Iterator[None]:
    """The readings and the manifest of a run as texts passed through a change (a manifest
    changed to None is removed); ``rehash`` writes the hash of the new readings into the
    manifest first."""
    stored, record = study.runs / run / "readings.jsonl", study.runs / run / "run_manifest.json"
    with changed(stored, record):
        if readings is not None:
            stored.write_text(readings(stored.read_text()))
        if rehash:
            new = json.loads(record.read_text()) | {"readings_sha256": sha(stored)}
            record.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n")
        if manifest is not None:
            text = manifest(record.read_text())
            if text is None:
                record.unlink()
            else:
                record.write_text(text)
        yield


def one_row(change: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """``change`` on the first stored row that holds an interval, and no other row."""
    done: list[str] = []

    def changing(row: dict) -> dict:
        dated = isinstance((row.get("reading") or {}).get("interval"), dict)
        if not dated or (done and done[0] != row["item_id"]):
            return row
        done[:] = [row["item_id"]]
        return change(json.loads(json.dumps(row)))

    return changing


def free_text(row: dict) -> dict:
    row["reading"]["interval"]["start"] = CELL
    return row


def no_certainty(row: dict) -> dict:
    del row["reading"]["certainty"]
    return row


def no_sample(row: dict) -> dict:
    del row["sample"]
    return row


def with_reading(**cells: Any) -> Callable[[dict], dict]:
    """A change of a stored row: these cells of its reading, in place of what it holds."""

    def change(row: dict) -> dict:
        row["reading"] |= cells
        return row

    return change


UNREADABLE: dict[str, tuple[Callable[[SimpleNamespace, str], Any], str]] = {
    "a line of the readings that is not JSON": (
        lambda study, run: run_files(study, run, lambda text: text + "{ not JSON\n", rehash=True),
        "JSONDecodeError",
    ),
    "a line that is not JSON, under the hash of the readings as they were": (
        lambda study, run: run_files(study, run, lambda text: text + "{ not JSON\n"),
        "JSONDecodeError",
    ),
    "a stored interval that is no date": (
        lambda study, run: rewritten(study, run, one_row(free_text)),
        "ValueError",
    ),
    "a stored reading without its certainty class": (
        lambda study, run: rewritten(study, run, one_row(no_certainty)),
        "KeyError",
    ),
    "a stored certainty class that is a free text": (
        lambda study, run: rewritten(study, run, one_row(with_reading(certainty=CELL))),
        "ValueError",
    ),
    "a stored statement type that is a free text": (
        lambda study, run: rewritten(study, run, one_row(with_reading(statement_type=CELL))),
        "ValueError",
    ),
    "a stored stale flag that is a text": (
        lambda study, run: rewritten(study, run, one_row(with_reading(stale=CELL))),
        "ValueError",
    ),
    "a stored interval that is a free text": (
        lambda study, run: rewritten(study, run, one_row(with_reading(interval=CELL))),
        "ValueError",
    ),
    "a stored interval that ends before it starts": (
        lambda study, run: rewritten(
            study,
            run,
            one_row(with_reading(interval={"start": "2020-05-31", "end": "2020-05-01"})),
        ),
        "ValueError",
    ),
    "a stored row without its sample": (
        lambda study, run: rewritten(study, run, one_row(no_sample)),
        "KeyError",
    ),
    "an empty manifest": (
        lambda study, run: run_files(study, run, manifest=lambda text: ""),
        "JSONDecodeError",
    ),
    "a manifest cut in half": (
        lambda study, run: run_files(study, run, manifest=lambda text: text[: len(text) // 2]),
        "JSONDecodeError",
    ),
    "readings cut in mid-line and no manifest yet": (
        lambda study, run: run_files(
            study, run, lambda text: text[: len(text) - 25], manifest=lambda text: None
        ),
        "JSONDecodeError",
    ),
}


STORED_READINGS = (
    "a stored interval that is no date",
    "a stored reading without its certainty class",
    "a stored certainty class that is a free text",
    "a stored statement type that is a free text",
    "a stored stale flag that is a text",
    "a stored interval that is a free text",
    "a stored interval that ends before it starts",
)
"""The cases of a stored reading that the harness's parser does not accept. The evaluator's
check of the rows counts such a row before the scorer reads any."""


def row_faults_of(study: SimpleNamespace, run: str, model: str) -> list[str]:
    """What the evaluator's check of a row finds on the stored rows of a run, fault by fault,
    in the evaluator's own words."""
    return [fault for row in stored(study, run).values() for fault in ev.row_faults(row, model, V1)]


def no_row_fault(row: Mapping[str, Any], model: str, template: str) -> list[str]:
    """Stands for a check of the rows that passes every row on to the scorer."""
    return []


@pytest.mark.parametrize("command", ["e2", "e5"])
@pytest.mark.parametrize("case", list(UNREADABLE))
def test_a_run_that_cannot_be_read_as_the_harness_writes_it_is_refused(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    command: str,
) -> None:
    """One sentence, with the model and the line. A stored reading that the harness's parser
    does not accept is counted by the evaluator's check of the rows, in the evaluator's words.
    Whatever stops the check is named by the type of the error alone: the message of the error
    may quote a stored cell and is not passed on. A run caught while its files are being
    written is reported in the same way. Neither sentence names a cell or an item."""
    change, kind = UNREADABLE[case]
    line = "e2-literal" if command == "e2" else "e5"
    run = run_of(line, QWEN)
    stopped = (
        f"{GENERAL}{QWEN} {line}: the check of its runs stopped ({kind}): the plan or the "
        "stored files are not as the launcher and the harness write them, or a run is being "
        "written"
    )
    assert row_faults_of(study, run, QWEN) == []  # the run as the harness wrote it
    with change(study, run):
        said = [refused(command, study, tmp_path, capsys)]
        if case in STORED_READINGS:
            # the evaluator finds one fault, on the one row that was changed
            (fault,) = row_faults_of(study, run, QWEN)
            assert said[0] == f"{GENERAL}{QWEN} {line}: 1 rows with {fault}"
            assert "stopped" not in said[0] and "Error" not in said[0]
            # passed on to the scorer, the row stops its own reading of the stored rows
            monkeypatch.setattr(ev, "row_faults", no_row_fault)
            said.append(refused(command, study, tmp_path, capsys))
        assert said[-1] == stopped
    for why in said:
        assert CELL not in why and "soon" not in why and "2020-05" not in why
        assert not [item for item in (*study.items, *study.pair_ids.values()) if item in why]


@pytest.mark.parametrize("command", ["e2", "e5"])
def test_readings_that_cannot_be_opened_end_in_a_refusal(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    """The readings of a run are on disk and may not be read: the check of that line stops on
    an error of the system, which is one more reason named by its type. Nothing is scored, and
    no error leaves the command but its refusal."""
    line = "e2-literal" if command == "e2" else "e5"
    readings = study.runs / run_of(line, QWEN) / "readings.jsonl"
    mode = readings.stat().st_mode
    readings.chmod(0)
    try:
        if os.access(readings, os.R_OK):  # a user whom no mode keeps out: the same error by hand
            read = Path.read_bytes

            def closed(self: Path) -> bytes:
                if self == readings:
                    raise PermissionError(13, "Permission denied", str(self))
                return read(self)

            monkeypatch.setattr(Path, "read_bytes", closed)
        with pytest.raises(PermissionError):
            readings.read_bytes()
        why = refused(command, study, tmp_path, capsys)
    finally:
        readings.chmod(mode)
    assert why == (
        f"{GENERAL}{QWEN} {line}: the check of its runs stopped (PermissionError): the plan or "
        "the stored files are not as the launcher and the harness write them, or a run is being "
        "written"
    )
    assert readings.as_posix() not in why and "denied" not in why
    assert readings.read_bytes()  # and the file is as it was


def test_a_plan_that_is_not_as_the_launcher_writes_it_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = lp.plan_path(study.runs)
    for missing in ("runs", "routes", "templates"):
        with json_with(plan, lambda record, missing=missing: record.pop(missing)):
            for command, lines in (("e2", 16), ("e5", 7)):
                why = refused(command, study, tmp_path, capsys)
                assert why.startswith(GENERAL)
                assert why.count("the check of its runs stopped (KeyError)") == lines, missing
                assert f"{GROK} {'e5' if command == 'e5' else 'e2-literal-free'}: the check" in why


def test_a_partial_run_is_named_as_partial_whatever_its_rows_hold(
    study: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rows of a run that is refused already are not parsed: the reason is the one the
    evaluator's check gives, and no row stands in its way."""

    def as_text(row: dict) -> dict:
        return row | {"reading": CELL}

    run = run_of("e2-literal", GEMMA)
    with with_manifest(study, run, complete=False), rewritten(study, run, one_row(as_text)):
        why = refused("e2", study, tmp_path, capsys)
    assert f"{GEMMA} e2-literal: run {run} is not finished (partial)" in why
    assert "stopped" not in why and "Error" not in why and CELL not in why
    # the same row in a run that says it is complete: the evaluator's check of the rows counts
    # it as a reading the harness's parser does not accept
    with rewritten(study, run, one_row(as_text)):
        why = refused("e2", study, tmp_path, capsys)
        (fault,) = row_faults_of(study, run, GEMMA)
        assert why == f"{GENERAL}{GEMMA} e2-literal: 1 rows with {fault}"
        assert "stopped" not in why and "Error" not in why and CELL not in why
        # passed on to the scorer, it stops the reading of the stored rows
        monkeypatch.setattr(ev, "row_faults", no_row_fault)
        why = refused("e2", study, tmp_path, capsys)
    assert f"{GEMMA} e2-literal: the check of its runs stopped (TypeError)" in why
    assert CELL not in why


def test_a_run_that_cannot_be_read_can_be_declared_not_run(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e5: SimpleNamespace
) -> None:
    change, kind = UNREADABLE["a line of the readings that is not JSON"]
    with change(study, run_of("e5", QWEN)):
        report, _ = scored("e5", study, tmp_path, capsys, "--not-run", f"{QWEN}=disk full")
    assert report["not_run"] == {QWEN: "declared on the command line: disk full"}
    assert report["not_run_checked"] == {
        QWEN: {
            "e5": {
                "runs": {run_of("e5", QWEN): "finished"},
                "found": [
                    f"{QWEN} e5: the check of its runs stopped ({kind}): the plan or the stored "
                    "files are not as the launcher and the harness write them, or a run is "
                    "being written"
                ],
            }
        }
    }
    assert report["tests"] == e5.report["tests"] and QWEN not in report["errors"]


# --------------------------------------------------------------------------------------------
# Inputs that are not what they must be end in a refusal
# --------------------------------------------------------------------------------------------


def ragged(source: Path, tmp_path: Path, more: bool) -> Path:
    """A copy of a table with one cell too many, or one too few, in its third line."""
    lines = source.read_text(encoding="utf-8").splitlines()
    header = next(csv.reader([lines[0]]))
    lines[2] = lines[2] + ",one more" if more else lines[2][: lines[2].rindex(",")]
    assert len(next(csv.reader([lines[2]]))) == len(header) + (1 if more else -1)
    path = tmp_path / f"ragged_{source.name}"
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


@pytest.mark.parametrize("more", [True, False])
def test_a_gold_row_with_more_or_fewer_cells_than_the_header_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], more: bool
) -> None:
    """A row that lost or gained a cell has every later cell under another name. Read with
    the surplus dropped, or the missing cells empty, it could still pass for a gold row."""
    for command, source, what in (
        ("e2", study.gold, "the gold of the literal task"),
        ("e5", study.e5_gold, "the gold of the minimal pairs"),
    ):
        path = ragged(source, tmp_path, more)
        why = refused(command, study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))
        assert why == f"refused: {what} has 1 rows with more or fewer cells than its header"
    key = study.audit / S.KEYS_DIR / "literal_key.csv"
    with changed(key):
        key.write_bytes(ragged(key, tmp_path, more).read_bytes())
        why = refused("e2", study, tmp_path, capsys)
    assert why == "refused: the key has 1 rows with more or fewer cells than its header"


def test_tables_and_item_files_are_held_to_their_form() -> None:
    with pytest.raises(SystemExit, match="the key has 2 rows with more or fewer cells than its"):
        LS.read_table(b"item_id,stratum\nI1,tbd,x\nI2\nI3,tbd\n", ("item_id", "stratum"), "the key")
    rows = LS.read_table(b'item_id,stratum\n"I1","a, b"\n', ("item_id", "stratum"), "the key")
    assert rows == [{"item_id": "I1", "stratum": "a, b"}]
    for bad in ('["I1"]', '{"a": 1}', "7", '""', "null"):
        data = f'{{"item_id": {bad}, "date_of_update": "2020-03-02"}}\n'.encode()
        with pytest.raises(SystemExit) as stop:
            LS.read_jsonl(data, "the file")
        assert stop.value.code == (
            "refused: the file is not an item file of the reading harness (TypeError)"
        ), bad


def test_item_files_events_and_seeds_that_are_not_what_they_must_be(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    # an item id that is no text
    def listed_id(rows: list[dict]) -> None:
        rows[0]["item_id"] = [rows[0]["item_id"]]

    for command, source in (("e2", study.audit / "literal_items.jsonl"), ("e5", study.e5_items)):
        items = items_with(source, tmp_path, listed_id)
        why = refused(command, study, tmp_path, capsys, items=items)
        assert (
            why == "refused: the item file is not an item file of the reading harness (TypeError)"
        )
    # the events table as a compressed file: read whole, refused when it is cut or damaged
    packed = tmp_path / "events.csv.gz"
    data = gzip.compress(study.events.read_bytes())
    packed.write_bytes(data)
    report, _ = scored("e2", study, tmp_path, capsys, events=packed)
    assert report["item_sets"] == e2.report["item_sets"]
    packed.write_bytes(data[: len(data) // 2])
    why = refused("e2", study, tmp_path, capsys, events=packed)
    assert why == (
        "refused: the events table or the guide cannot be read as the sampler reads them (EOFError)"
    )
    middle = len(data) // 2
    packed.write_bytes(data[:middle] + bytes(40) + data[middle + 40 :])
    why = refused("e2", study, tmp_path, capsys, events=packed)
    assert why == (
        "refused: the events table or the guide cannot be read as the sampler reads them (error)"
    )
    # a seed without an id, in the item file and in the gold alike: its items have no cluster
    one = study.pair_ids[4, "stale"]

    def seedless(rows: list[dict]) -> None:
        next(row for row in rows if row["item_id"] == one)["seed_id"] = ""

    items = items_with(study.e5_items, tmp_path, seedless)
    path = e5_gold_with(study, tmp_path, seedless)
    why = refused(
        "e5", study, tmp_path, capsys, items=items, gold=path, expect_gold_sha256=sha(path)
    )
    assert why == (
        "refused: the gold is not the gold of the item file: 1 rows of no item, of another "
        "seed, factor or level, or that cannot be read; 1 items without a gold row"
    )


# --------------------------------------------------------------------------------------------
# Guards that no other test holds in place
# --------------------------------------------------------------------------------------------


def test_e5_gold_with_a_row_twice_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every item has a row, and one row stands twice."""
    path = e5_gold_with(study, tmp_path, lambda rows: rows.append(dict(rows[0])))
    why = refused("e5", study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))
    assert why == "refused: the gold is not the gold of the item file: 1 rows of a repeated item"


def test_e5_gold_with_one_item_twice_in_place_of_another_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """As many rows as items, and one item without a row."""

    def replace(rows: list[dict]) -> None:
        rows[-1] = dict(rows[0])

    path = e5_gold_with(study, tmp_path, replace)
    why = refused("e5", study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))
    assert why == (
        "refused: the gold is not the gold of the item file: 1 rows of a repeated item; 1 items "
        "without a gold row"
    )


def test_e5_item_file_that_calls_an_edit_a_seed_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def flip(rows: list[dict]) -> None:
        next(row for row in rows if row["factor"] == "stale")["is_seed"] = True

    items = items_with(study.e5_items, tmp_path, flip)
    why = refused("e5", study, tmp_path, capsys, items=items)
    assert "1 rows of no item, of another seed, factor or level" in why


@pytest.mark.parametrize("how_many", ["one item", "every item of a factor"])
def test_e5_a_factor_the_study_does_not_have_is_refused(
    how_many: str, study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The item file and the gold agree on a factor of no test. Scored, one such item would
    leave a cell of one item; twelve would be fitted as unedited seed items, because the
    design has no column for them."""
    one = study.pair_ids[3, "granularity"]

    def rename(rows: list[dict]) -> None:
        for row in rows:
            if row["item_id"] == one or (how_many != "one item" and row["factor"] == "granularity"):
                row["factor"] = "colour"

    items = items_with(study.e5_items, tmp_path, rename)
    path = e5_gold_with(study, tmp_path, rename)
    why = refused(
        "e5", study, tmp_path, capsys, items=items, gold=path, expect_gold_sha256=sha(path)
    )
    count = 1 if how_many == "one item" else PAIR_SEEDS
    assert f": {count} rows of no item, of another seed, factor or level" in why
    assert f"{count} items without a gold row" in why


def test_e5_gold_of_another_level_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = e5_gold_with(study, tmp_path, lambda rows: rows[2].update(level="late"))
    why = refused("e5", study, tmp_path, capsys, gold=path, expect_gold_sha256=sha(path))
    assert "1 rows of no item, of another seed, factor or level" in why


def test_a_key_that_lacks_an_item_is_refused(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key = study.audit / S.KEYS_DIR / "literal_key.csv"
    with changed(key):
        lines = key.read_text().splitlines()
        key.write_text("".join(line + "\n" for line in lines[:-1]))
        why = refused("e2", study, tmp_path, capsys)
    assert why == "refused: the key of the sample puts 1 items in another stratum than the table"


@pytest.mark.parametrize("command", ["e2", "e5"])
def test_a_plan_made_for_another_output_root_is_named(
    command: str, study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = lp.plan_path(study.runs)
    with json_with(plan, lambda p: p["options"].update(out_root=str(tmp_path / "elsewhere"))):
        why = refused(command, study, tmp_path, capsys)
    assert "the plan was made for another output root than the one given" in why


def test_a_submitted_sheet_without_a_gold_item_gives_no_ceiling(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: SimpleNamespace
) -> None:
    name = f"{A.SUBMITTED_DIR}/literal_A2.csv"
    sheet, manifest = study.audit / name, study.audit / S.MANIFEST
    with changed(sheet, manifest):
        meta, rows = S.parse_sheet(sheet.read_text(encoding="utf-8"))
        kept = [row for row in rows if row["item_id"] != study.ids[1]]
        assert len(kept) == len(rows) - 1
        sheet.write_text(S.sheet_text(S.SHEET_COLUMNS, kept, meta), encoding="utf-8")
        record = json.loads(manifest.read_text())
        record["submitted"][name] = sha(sheet)
        manifest.write_text(json.dumps(record))
        report, _ = scored("e2", study, tmp_path, capsys)
    assert report["item_sets"]["all"]["literal_ceiling"] == {
        "computed": False,
        "why": "a submitted sheet lacks a gold item",
    }
    assert report["item_sets"]["all"]["tests"] == e2.report["item_sets"]["all"]["tests"]


@pytest.mark.parametrize("command", ["e2", "e5"])
def test_an_output_that_appears_during_the_run_is_not_overwritten(
    command: str, study: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The output is looked for before anything is read and again when it is written."""
    out = tmp_path / "late.json"
    record = LS.registered_record

    def late() -> dict:
        out.write_text("written by another run")
        return record()

    monkeypatch.setattr(LS, "registered_record", late)
    with pytest.raises(SystemExit, match=r"refused: the output cannot be written \(FileExi"):
        LS.main(ARGS[command](study, out))
    assert out.read_text() == "written by another run"


# --------------------------------------------------------------------------------------------
# Figures that no other test holds in place
# --------------------------------------------------------------------------------------------


def test_false_commitment_on_tbd_or_silent_counts_the_marked_items_only(
    e2: SimpleNamespace,
) -> None:
    """A date where the gold abstains, on an item outside the TBD and silent strata, is a false
    commitment and no false commitment on TBD or silent text."""
    pairs = [
        (reading("next_delivery", "2022-01-01", "2022-01-31"), gold("next_delivery")),
        (reading("recovery", certainty="undetermined"), gold("recovery")),
    ]
    cols = LS.columns([r for r, _ in pairs], [g for _, g in pairs], [False, True])
    found = LS.values(cols, np.ones(2))
    assert found["false_commitment"] == 0.5
    assert found["false_commitment_tbd_or_silent"] == 0.0
    # end to end: gpt-oss-20b gives a date on item 21 (distractor only, gold ABSTAIN) and on no
    # TBD or silent item. The bar of the positive result is read on the two strata: it is not
    # passed, with a rate over every gold-ABSTAIN item of one in seven beside it
    oss = e2.report["item_sets"]["all"]["readers"][OSS][V1]["sample"]
    assert oss["false_commitment"]["value"] == pytest.approx(1 / 7)
    assert oss["false_commitment_tbd_or_silent"]["value"] == 0.0
    positive = e2.report["item_sets"]["all"]["positive_result"][OSS]
    assert positive["false_commitment_above_0.05"] is False
    assert "false_commitment_every_gold_abstain_above_0.05" not in positive
    assert positive["false_commitment_every_gold_abstain"] == oss["false_commitment"]
    assert positive["false_commitment_tbd_or_silent"] == oss["false_commitment_tbd_or_silent"]


def test_distractor_uptake_at_exactly_half() -> None:
    half = reading("recovery", "2020-04-01", "2020-04-15")
    away = gold("recovery", "2020-07-01", "2020-07-31", distractors=[APRIL])
    assert LS.iou(half.interval, span(*APRIL)) == 0.5
    assert LS.columns([half], [away])["uptake"][0] == 1  # 0.5 with the distractor is an uptake
    beside = gold("recovery", *APRIL, distractors=[("2020-04-01", "2020-04-15")])
    cols = LS.columns([half], [beside])
    assert cols["correct"][0] == 1 and cols["uptake"][0] == 0  # 0.5 with the gold is the gold


def test_a_distractor_role_whose_quote_gives_no_date_is_no_distractor_date() -> None:
    row = GOLD_ROW | {
        "distractor_roles": "other",
        "distractor_quotes": "available until further notice",
    }
    theirs = LS.gold_of("I1", row, d(DAY))
    assert theirs.roles == 1 and theirs.distractors == ()
    cols = LS.columns([reading("next_delivery", "2020-01-01", "2020-01-31")], [theirs])
    assert cols["has_distractor"][0] == 0 and cols["uptake"][0] == 0
    assert LS.values(cols, np.ones(1))["distractor_uptake"] is None
    assert LS.counts(cols)["gold_with_distractor_date"] == 0


def test_a_distractor_quote_is_normalised_before_it_is_read() -> None:
    quote = "Current supply expected to deplete by May–June 2020 timeframe"
    plain = "Current supply expected to deplete by May-June 2020 timeframe"
    anchor = d(DAY)
    assert LS.distractor_intervals([quote], anchor) == LS.distractor_intervals([plain], anchor)
    assert LS.distractor_intervals([quote], anchor) == (span(DAY, "2020-06-30"),)
    assert len(R.find_timexes(quote, anchor)) == 2  # read raw, the dash splits the range


def test_the_sensitivity_analysis_needs_both_readers_parsed() -> None:
    golds = [gold("recovery", *APRIL)] * 4
    right = reading("recovery", *APRIL)
    scope = LS.Scope(
        ids=list("abcd"),
        golds=golds,
        strata=["tbd"] * 4,
        marked=[True] * 4,
        bases={"sample": np.ones(4)},
        taken=np.ones((3, 4)),
    )
    first = LS.columns([right, right, LS.NO_ANSWER, right], golds)
    second = LS.columns([right, LS.NO_ANSWER, right, right], golds)
    found = LS.versus(scope, first, second)
    assert found["outside_month_year"]["items"] == 4
    assert found["outside_month_year_both_parsed"]["items"] == 2
    assert found["outside_month_year_both_parsed"]["only_first_correct"] == 0
    assert found["outside_month_year"]["only_first_correct"] == 1
    assert found["outside_month_year"]["only_second_correct"] == 1


def test_a_registered_test_with_no_lead_favours_neither() -> None:
    items = {
        "a": {"item_id": "a", "date_of_update": DAY, "availability_information": TEXTS[1]},
        "b": {"item_id": "b", "date_of_update": DAY, "availability_information": TEXTS[12]},
    }
    rules = {i: LS.rule_reading(item) for i, item in items.items()}
    golds = {i: LS.Gold(i, rules[i]) for i in items}
    frame = LS.Frame(
        stratum=dict.fromkeys(items, "tbd"),
        episode={i: i for i in items},
        day=dict.fromkeys(items, DAY),
        events={"tbd": 2},
        templates={"tbd": 2},
        order=("tbd",),
    )
    readings = {(m, t): rules for m in rd.PRIMARIES for t in (V1, FREE)}
    found = LS.score_e2(list(items), golds, frame, items, readings, {})
    assert [t["favours"] for t in found["tests"]] == ["neither", "neither"]
    assert [t["p"] for t in found["tests"]] == [1.0, 1.0]
    assert found["versus_ceiling"] == {"computed": False}
    # the rule reader ahead
    wrong = {i: reading("depletion") for i in items}
    readings = {(m, t): wrong for m in rd.PRIMARIES for t in (V1, FREE)}
    found = LS.score_e2(list(items), golds, frame, items, readings, {})
    assert [t["favours"] for t in found["tests"]] == ["the rule reader"] * 2


def test_a_draw_without_an_unedited_item_is_left_out() -> None:
    data = gee_data(9)
    mine = data.frame[data.frame["model"] == "m2"].reset_index(drop=True)
    error = mine["error"].to_numpy()
    edited = (mine["factor"] == "stale").to_numpy().astype(float)
    taken = LS.item_draws(list(mine["seed"]), draws=300)
    one = np.zeros(len(error))
    one[int(np.flatnonzero((mine["factor"] == "seed").to_numpy())[0])] = 1.0
    found = LS.drawn_contrast(error, edited, one, taken)
    drawn = P.cluster_draws(9, 300, LS.SEED)
    assert found["draws"] == int((drawn[:, 0] > 0).sum()) < 300
    assert found["ci95"]["draws"] == found["draws"]


def test_the_interval_of_the_iou_lead_is_that_of_the_registered_draws(
    e2: SimpleNamespace,
) -> None:
    """llama against the rules on the dated targets beside a distractor date (items 18 and 19,
    each its own episode): llama's IoU is 0 on item 18 and 1 on item 19, the rule reader's 1 on
    both. The draws are those of the episodes of the gold items in sorted order."""
    episodes = sorted({EPISODES.get(n, n) for n in GOLD})
    drawn = P.cluster_draws(len(episodes), 10_000, 20261001).astype(float)
    t18, t19 = drawn[:, episodes.index(18)], drawn[:, episodes.index(19)]
    kept = (t18 + t19) > 0
    lead = -t18[kept] / (t18[kept] + t19[kept])
    low, high = np.quantile(lead, [0.025, 0.975])
    found = e2.report["item_sets"]["all"]["versus_rules"][LLAMA][V1]["iou"]["dated_distractor"]
    assert found["difference"] == pytest.approx(-0.5)
    assert found["ci95"] == {
        "low": pytest.approx(low, abs=1e-6),
        "high": pytest.approx(high, abs=1e-6),
        "draws": int(kept.sum()),
    }
    assert low == -1.0 and high == 0.0


def test_e5_intervals_of_the_metrics_are_draws_of_seeds(e5: SimpleNamespace) -> None:
    right = np.zeros(PAIR_SEEDS)
    for s in range(PAIR_SEEDS):
        for factor in PAIR_FACTORS:
            wrong = pair_errs(LLAMA, s, factor) and factor not in ("certainty", "stale")
            right[s] += not wrong
    drawn = P.cluster_draws(PAIR_SEEDS, 10_000, 20261001).astype(float)
    share = (drawn @ right) / (drawn.sum(axis=1) * len(PAIR_FACTORS))
    low, high = np.quantile(share, [0.025, 0.975])
    found = e5.report["metrics"][LLAMA]["all"]["correct"]
    assert found["value"] == pytest.approx(right.sum() / 84)
    assert found["ci95"]["low"] == pytest.approx(low, abs=1e-6)
    assert found["ci95"]["high"] == pytest.approx(high, abs=1e-6)


def test_the_ceiling_gives_false_commitment_on_tbd_or_silent_items(e2: SimpleNamespace) -> None:
    for name in ("A1_against_A2", "A2_against_A1"):
        found = e2.report["item_sets"]["all"]["literal_ceiling"][name]
        assert found["n"]["gold_abstain_tbd_or_silent"] == 6
        assert found["sample"]["false_commitment_tbd_or_silent"]["value"] == 0.0
        assert found["sample"]["false_commitment"]["value"] == 0.0


def test_every_stratum_with_a_gold_item_has_its_figures(e2: SimpleNamespace) -> None:
    whole = e2.report["item_sets"]["all"]["readers"]
    strata = {STRATA[n] for n in GOLD}
    assert set(whole["rules"]["by_stratum"]) == strata
    assert set(whole[LLAMA][V1]["by_stratum"]) == strata
    assert whole[LLAMA][V1]["by_stratum"]["exact_day"]["n"]["items"] == 1


def test_the_weighted_interval_of_another_metric_than_correct(e2: SimpleNamespace) -> None:
    """llama's IoU weighted by event: 1 on every dated gold item but item 18 (the expiry date)."""
    episodes = sorted({EPISODES.get(n, n) for n in GOLD})
    members = {k: [n for n in GOLD if EPISODES.get(n, n) == e] for k, e in enumerate(episodes)}
    scored_in = {s: sum(1 for n in GOLD if STRATA[n] == s) for s in set(STRATA.values())}
    weight = {n: FRAME[STRATA[n]][0] / scored_in[STRATA[n]] for n in GOLD}
    dated = {n for n in GOLD if TRUTH[n]["start"]}
    top = np.array([sum(weight[n] for n in members[k] if n in dated and n != 18) for k in members])
    bottom = np.array([sum(weight[n] for n in members[k] if n in dated) for k in members])
    drawn = P.cluster_draws(len(episodes), 10_000, 20261001).astype(float)
    kept = (drawn @ bottom) > 0
    values = (drawn @ top)[kept] / (drawn @ bottom)[kept]
    low, high = np.quantile(values, [0.025, 0.975])
    found = e2.report["item_sets"]["all"]["readers"][LLAMA][V1]["weighted_by_event"]["interval_iou"]
    assert found["value"] == pytest.approx(top.sum() / bottom.sum())
    assert found["ci95"]["low"] == pytest.approx(low, abs=1e-6)
    assert found["ci95"]["high"] == pytest.approx(high, abs=1e-6)
    unweighted = e2.report["item_sets"]["all"]["readers"][LLAMA][V1]["sample"]["interval_iou"]
    assert unweighted["ci95"] != found["ci95"]


# --------------------------------------------------------------------------------------------
# A sealed input is refused without being opened or listed
# --------------------------------------------------------------------------------------------

TOUCHED: list[str] = []
WATCHED: list[str] = []


def _audit(event: str, args: tuple) -> None:
    """Every file opened and every folder listed while a watch is on (an audit hook cannot be
    taken away again, so it records only then). Resolving a path, or asking whether it is a
    file, opens nothing and is not recorded."""
    if WATCHED and event in ("open", "os.listdir", "os.scandir") and args:
        TOUCHED.append(f"{event} {args[0]!s}")


sys.addaudithook(_audit)


@contextmanager
def watching() -> Iterator[list[str]]:
    TOUCHED.clear()
    WATCHED.append("on")
    try:
        yield TOUCHED
    finally:
        WATCHED.clear()


def test_the_watch_sees_a_file_opened_and_a_folder_listed(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"x")
    with watching() as touched:
        (tmp_path / "file").read_bytes()
        list(tmp_path.iterdir())
        (tmp_path / "file").resolve().is_file()
    assert len(touched) == 2 and touched[0].startswith("open ")
    assert touched[1].split()[0] in ("os.listdir", "os.scandir")
    (tmp_path / "file").read_bytes()
    assert len(touched) == 2  # nothing is recorded outside a watch


def test_an_input_named_in_a_sealed_folder_is_refused_unopened(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With real files in a folder named as the sealed one: the refusal comes before any file
    is opened and any folder listed, whether the input is named there as a file, a folder, a
    file that is not there, or through a link from outside."""
    vault = tmp_path / "sealed"
    (vault / "folder").mkdir(parents=True)
    (vault / "file").write_bytes(b"sealed\n")
    (vault / "folder" / "inner.csv").write_bytes(b"sealed\n")
    link = tmp_path / "link.csv"  # a name outside the sealed folder for a file inside it
    link.symlink_to(vault / "file")
    out = tmp_path / "scores.json"
    names = {
        "e2": (
            "gold",
            "items",
            "events",
            "guide",
            "key",
            "audit_dir",
            "out_root",
            "convention_items",
        ),
        "e5": ("gold", "items", "out_root"),
    }
    cases = [
        (command, name, target)
        for command in names
        for name in names[command]
        for target in (vault / "file", vault / "folder", vault / "absent", link)
    ]
    for command, name, target in cases:
        # the hash is given, so that the helper does not open the sealed file to compute one
        argv = ARGS[command](study, out, **{name: target, "expect_gold_sha256": "0" * 64})
        capsys.readouterr()
        with watching() as touched, pytest.raises(SystemExit) as stop:
            LS.main(argv)
        assert stop.value.code == (
            f"refused: --{name.replace('_', '-')} lies in a sealed folder; no sealed file is read"
        ), (command, name, target)
        assert touched == [], (command, name, target)
        printed = capsys.readouterr()
        assert printed.out == "" and printed.err == "" and not out.exists()
    found = sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*"))
    assert found == ["file", "folder", "folder/inner.csv"]
    assert (vault / "file").read_bytes() == b"sealed\n"


@pytest.mark.parametrize("command", ["e2", "e5"])
def test_a_refusal_of_the_command_run_as_a_process(
    study: SimpleNamespace, tmp_path: Path, command: str
) -> None:
    """Status 1, the reason alone on the error stream, nothing printed, nothing written. Every
    path is given and made up, and the refusal comes before any file is opened."""
    vault = tmp_path / "sealed"
    vault.mkdir()
    (vault / "file").write_bytes(b"sealed\n")
    out = tmp_path / "scores.json"
    argv = ARGS[command](study, out, gold=vault / "file", expect_gold_sha256="0" * 64)
    root = Path(LS.__file__).resolve().parents[2]
    env = {name: value for name, value in os.environ.items() if not name.endswith("_API_KEY")}
    done = subprocess.run(
        [sys.executable, "-m", "analysis.coling.literal_scores", *argv],
        cwd=root,
        env=env | {"PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert done.returncode == 1 and done.stdout == ""
    assert done.stderr == "refused: --gold lies in a sealed folder; no sealed file is read\n"
    assert not out.exists() and [path.name for path in vault.iterdir()] == ["file"]


# --------------------------------------------------------------------------------------------
# The registered pattern of section 13: its constants, the floors, the margin
# --------------------------------------------------------------------------------------------

PLAN = Path(LS.__file__).resolve().parent / "plan" / "PLAN.md"
QUOTED = (
    "In E5, surface form and granularity are the *letter factors*: the edit rewrites the period "
    "or changes the period itself.",
    "Certainty marker, stale, distractor date and silent are the *standing factors*: the edit "
    "leaves the words of the period as they are, or takes them away.",
    "the model's letter accuracy (section 7.1) is not more than 0.10 below the rule reader's: "
    "the lower end of the 90% percentile interval of the difference, model minus rule reader, "
    "lies above -0.10 (10,000 draws of shortage episodes, seed 20261001). Condition (a) sets no "
    "upper limit and is read on the interval alone.",
    "The model's error rate on the items of the factor is at least 0.10 above its error rate on "
    "the unedited seed items, and at least 0.10 above its error rate on the items of the two "
    "letter factors taken together, every rate under the criterion of the factor",
    "The factor's own error occurs on at least 0.10 of the items of the factor on which it can "
    "occur.",
    "The own error is a period given where the gold gives none (certainty marker and silent: "
    "the false-commitment rate of section 7.1), the distractor's period taken (distractor date: "
    "distractor uptake, section 7.1), or a period given without the stale flag on an item whose "
    "gold is stale (stale).",
    "E5 down to 474 of its 800 items: the unedited seed item and every edit of the first 50 "
    "seeds of the seed list in its draw order (the 50 lowest draw_rank of "
    "sample_pair_seeds.csv), the same for every reader, fixed before any E5 call. The cut item "
    "file holds the registered rows of those seeds unchanged.",
)
"""What the constants of the pattern quote of the plan, word for word."""
SMALL_POINTS = (
    "Condition (a) sets no upper limit and is read on the interval alone",
    "The E2 run of the pattern is the primary's literal-v1 run, and the pattern is read from "
    "one E2 and one E5 result of the same plan of the runs",
    "an end of exactly -0.10 does not meet (a), and without a gold letter item (a) is not met",
    "A difference or a share of exactly 0.10 meets a floor of the standing part",
    "a floor whose rate has no item is not met",
    "for the certainty marker and for silent, the items whose gold gives no period",
    "the items whose gold carries a distractor date",
    "for stale, the items whose gold is stale",
    "A factor with no such item does not meet (c)",
    "A test of E5 holds by Holm's rule on the p-value of the procedure in force (under the "
    "fallback, the centred bootstrap p-value); its direction is the sign of the difference of "
    "the two error rates; a test that is not evaluable does not hold",
    "When the standing part does not hold: if no test of a standing factor holds with the "
    "higher error rate on the edited items, it is withheld by (a); otherwise the paper names "
    "the floor or the condition (c) that each factor with such a test misses",
    "When the pattern holds for one primary and the other has no pattern, the paper states the "
    "sentence for the first by name and says that the other has none",
    "the same for every reader, fixed before any E5 call",
    "the 50 lowest draw_rank of sample_pair_seeds.csv",
    "the cut item file holds the registered rows of those seeds unchanged",
)
"""What the plan states of the reading, in its own words: each stands in the plan, and in what
the scorer lists as done because the plan says so."""
PLAN_WORDS = (
    "the paper states the sentence for the two primary models",
    "for that model by name",
    "says in the same place which part did not hold for the other",
    "the paper does not state the sentence and reports each part for each primary",
    "is not read as its opposite, and the paper says which condition withheld it",
    "reported as that family's result, with its size, also when a floor or the other part "
    "withholds the sentence",
    "does not write that no effect was detected",
    "has no pattern, and the paper says so",
    "the pattern is read on those items with the same floors",
    "(section 12, cut 4)",
    "the pattern holds for one primary and the other has no pattern",
    "states the sentence for the first by name",
    "says that the other has none",
    "is not scored by the freeze of numbers",
    "the sentence is not stated",
    "whichever way it came out",
    "the paper gives the rate of its own error in the sentence that names it, and the share of "
    "the factor's errors that are of another kind",
    "the paper states the sentence for no secondary model and uses no plural that includes one",
)
"""The words of the plan that the sentence of a pattern result is written in."""


def flat_text(text: str) -> str:
    """A text without its line breaks, its backticks and the typeset minus sign."""
    return " ".join(text.replace("−", "-").replace("`", "").split())


def test_the_constants_of_the_pattern_quote_the_plan() -> None:
    """PLAN section 13, "The registered pattern", and section 12, cut 4: each constant stands
    in the module with the sentence of the plan that fixes it, and the sentence is the plan's."""
    plan = flat_text(PLAN.read_text(encoding="utf-8"))
    source = flat_text(Path(LS.__file__).read_text(encoding="utf-8"))
    for words in QUOTED:
        assert flat_text(words) in plan, words
        assert flat_text(words) in source, words
    assert all(flat_text(words) in plan for words in PLAN_WORDS)
    assert (LS.LETTER_MARGIN, LS.STANDING_FLOOR, LS.OWN_ERROR_FLOOR) == (0.10, 0.10, 0.10)
    assert LS.E5_CUT_SEEDS == 50
    assert LS.LETTER_FACTORS == ("surface_form", "granularity")
    assert LS.STANDING_FACTORS == ("certainty", "stale", "distractor", "silent")
    assert LS.OWN_ERROR == {
        "certainty": ("false_commitment", "gold_abstains"),
        "silent": ("false_commitment", "gold_abstains"),
        "distractor": ("uptake", "has_distractor"),
        "stale": ("unflagged", "gold_stale"),
    }
    assert LS.SENTENCE in flat_text(PLAN.read_text(encoding="utf-8")).lower()
    # what the scorer does because the plan states it names its section, and is no silence
    says = LS.AS_THE_PLAN_SAYS
    assert len(says) == len(set(says)) == 12 and all("(section " in line for line in says)
    assert not set(says) & set(LS.WHERE_THE_PLAN_IS_SILENT)
    stated = " ".join(says)
    for words in ("above -0.10", "at least 0.10 above", "the first 50 seeds", "seed 20261001"):
        assert words in stated, words
    assert "Holm over the twelve tests" in stated
    # the small points of the reading and the cut: the plan's own words, in the plan and here
    assert sum('"Small points of the reading")' in line for line in says) == 4
    assert sum("(section 12, cut 4)" in line for line in says) == 2
    for words in SMALL_POINTS:
        assert flat_text(words).lower() in plan.lower(), words
        assert flat_text(words).lower() in stated.lower(), words


def counted(errors: int, items: int) -> dict[str, Any]:
    """A cell of error counts as a result file holds it."""
    return {"items": items, "errors": errors, "rate": errors / items if items else None}


ALL_MET = {"above_seed": True, "above_letter": True, "own_error": True, "met": True}


def test_a_floor_is_met_at_exactly_one_tenth_and_not_just_below(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAN section 13, the standing part, (b) and (c): "at least 0.10". The floors are read on
    the counts, in whole numbers: three tenths less two tenths is one tenth, which it is not
    in floating point."""
    assert 0.3 - 0.2 < 0.1 and 0.7 - 0.6 < 0.1
    # every floor exactly at 0.10: 3 of 10 against 2 of 10 and 4 of 20; the own error 1 of 10
    assert LS.floors(counted(3, 10), counted(2, 10), counted(4, 20), counted(1, 10)) == ALL_MET
    for k in range(9):
        found = LS.floors(counted(k + 1, 10), counted(k, 10), counted(2 * k, 20), counted(3, 30))
        assert found == ALL_MET, k
    # one error in a thousand short of the floor above the unedited seed items
    short = LS.floors(counted(300, 1000), counted(201, 1000), counted(4, 20), counted(1, 10))
    assert short == ALL_MET | {"above_seed": False, "met": False}
    assert LS.floors(counted(300, 1000), counted(200, 1000), counted(4, 20), counted(1, 10)) == (
        ALL_MET
    )
    # one error in two thousand short of the floor above the letter-factor items
    short = LS.floors(counted(300, 1000), counted(200, 1000), counted(401, 2000), counted(1, 10))
    assert short == ALL_MET | {"above_letter": False, "met": False}
    assert LS.floors(counted(300, 1000), counted(200, 1000), counted(400, 2000), counted(1, 10))[
        "met"
    ]
    # the own error on 99 of 1,000 items on which it can occur, and on 100
    short = LS.floors(counted(3, 10), counted(2, 10), counted(4, 20), counted(99, 1000))
    assert short == ALL_MET | {"own_error": False, "met": False}
    assert LS.floors(counted(3, 10), counted(2, 10), counted(4, 20), counted(100, 1000)) == ALL_MET
    # the lower error rate on the edited items is no floor met
    below = LS.floors(counted(2, 10), counted(3, 10), counted(8, 20), counted(2, 10))
    assert below == {"above_seed": False, "above_letter": False, "own_error": True, "met": False}
    # a rate with no item meets no floor: a floor can only withhold
    none = LS.floors(counted(3, 10), counted(2, 10), counted(0, 0), counted(0, 0))
    assert none == {"above_seed": True, "above_letter": False, "own_error": False, "met": False}
    assert LS.floors(counted(3, 10), counted(0, 0), counted(4, 20), counted(1, 10)) == (
        ALL_MET | {"above_seed": False, "met": False}
    )
    assert LS.reaches(Fraction(1, 10), 0.10) and not LS.reaches(Fraction(999, 10000), 0.10)
    assert not LS.reaches(None, 0.10) and LS.reaches(Fraction(1, 5), 0.2)
    assert LS.above(counted(3, 10), counted(2, 10)) == Fraction(1, 10)
    assert LS.above(counted(3, 10), counted(0, 0)) is None
    assert LS.exact_rate(counted(0, 0)) is None and LS.exact_rate(counted(2, 8)) == Fraction(1, 4)
    # each floor is its own constant
    cells = (counted(3, 10), counted(2, 10), counted(4, 20), counted(1, 10))
    monkeypatch.setattr(LS, "OWN_ERROR_FLOOR", 0.11)
    assert LS.floors(*cells) == ALL_MET | {"own_error": False, "met": False}
    monkeypatch.setattr(LS, "OWN_ERROR_FLOOR", 0.10)
    monkeypatch.setattr(LS, "STANDING_FLOOR", 0.11)
    assert LS.floors(*cells) == {
        "above_seed": False,
        "above_letter": False,
        "own_error": True,
        "met": False,
    }


def tie_case() -> tuple[dict, dict, dict[str, LS.Reading]]:
    """Ten seeds with one item of every factor, and the readings of one reader. On the ten
    items of each standing factor it errs three times, once by the factor's own error and
    twice in another way; on the ten unedited items twice, under every criterion; on the
    twenty letter-factor items four times, under every criterion. So each floor stands at
    exactly 0.10: 0.3 against 0.2, 0.3 against 0.2, and 1 item in 10."""
    dated = gold("recovery", *APRIL, "estimated")
    away = ("2022-01-01", "2022-01-31")
    right = reading("recovery", *APRIL, "estimated")
    elsewhere = reading("recovery", "2020-06-01", "2020-06-30", "estimated")
    by_factor = {
        "seed": ([dated] * 10, [elsewhere] * 2 + [right] * 8),
        "surface_form": ([dated] * 10, [right] * 8 + [elsewhere] * 2),
        "granularity": ([dated] * 10, [right] * 4 + [elsewhere] * 2 + [right] * 4),
        # a period where the gold gives none (the own error); twice the wrong class
        "certainty": (
            [gold("recovery", certainty="undetermined")] * 10,
            [right]
            + [reading("recovery", certainty="estimated")] * 2
            + [reading("recovery", certainty="undetermined")] * 7,
        ),
        # a period without the stale flag (the own error); twice a flagged period elsewhere
        "stale": (
            [gold("recovery", *APRIL, "estimated", stale=True)] * 10,
            [right]
            + [reading("recovery", "2020-06-01", "2020-06-30", "estimated", stale=True)] * 2
            + [reading("recovery", *APRIL, "estimated", stale=True)] * 7,
        ),
        # the distractor's period taken (the own error); twice the wrong statement type
        "distractor": (
            [gold("recovery", *APRIL, "estimated", distractors=[away])] * 10,
            [reading("recovery", *away, "estimated")]
            + [reading("depletion", *APRIL, "estimated")] * 2
            + [right] * 7,
        ),
        # a period where the entry is silent (the own error); twice an abstention of a type
        "silent": (
            [gold("none", certainty="no_statement")] * 10,
            [right]
            + [reading("recovery", certainty="no_statement")] * 2
            + [reading("none", certainty="no_statement")] * 7,
        ),
    }
    golds, info, given = {}, {}, {}
    for factor, (theirs, mine) in by_factor.items():
        for k in range(10):
            item = f"P{k}{factor}"
            golds[item], given[item] = theirs[k], mine[k]
            info[item] = {"seed_id": f"S{k}", "factor": factor, "level": "x"}
    return golds, info, given


def standing_tests(found: Mapping[str, Any], model: str = LLAMA) -> dict[str, dict[str, Any]]:
    tests = (*found["tests"], *found["other_models"])
    return {
        t["factor"]: t for t in tests if t["model"] == model and t["factor"] in LS.STANDING_FACTORS
    }


def test_e5_the_own_error_and_the_floors_of_each_standing_factor_worked_by_hand() -> None:
    """Through the scorer of E5, on readings written out by hand: the own error of each of the
    four standing factors on the items on which it can occur, and the three floors at exactly
    0.10; then each floor missed alone."""
    golds, info, given = tie_case()
    found = LS.score_e5(list(golds), golds, info, {LLAMA: given, GROK: given}, {})
    tests = standing_tests(found)
    assert list(tests) == ["certainty", "stale", "distractor", "silent"]
    for factor, test in tests.items():
        assert test["evaluable"] and test["against"] == LS.seed_cell(factor)
        assert test["edited"] == counted(3, 10) and test["unedited"] == counted(2, 10)
        assert test["above_letter_items"] == counted(4, 20) | {"difference": 0.1}
        assert test["own_error"] == counted(1, 10), factor
        assert test["errors_of_another_kind"] == {"errors": 2, "share": 2 / 3}
        assert test["floors"] == ALL_MET, factor
    # another model has the same quantities and no floors: no pattern is computed for it
    others = standing_tests(found, GROK)
    assert len(others) == 4 and all("floors" not in t for t in others.values())
    assert all(others[f]["own_error"] == tests[f]["own_error"] for f in tests)
    assert all(others[f]["above_letter_items"] == tests[f]["above_letter_items"] for f in tests)
    # a letter factor has none of them
    letters = [t for t in found["tests"] if t["factor"] in LS.LETTER_FACTORS]
    assert len(letters) == 4 and all("floors" not in t and "own_error" not in t for t in letters)

    def again(change: Mapping[str, LS.Reading]) -> dict[str, dict[str, Any]]:
        return standing_tests(LS.score_e5(list(golds), golds, info, {LLAMA: given | change}, {}))

    wrong = reading("recovery", "2020-06-01", "2020-06-30", "estimated")
    # one more error on an unedited item: 0.3 against 0.3
    for factor, test in again({"P5seed": wrong}).items():
        assert test["unedited"] == counted(3, 10)
        assert test["floors"] == ALL_MET | {"above_seed": False, "met": False}, factor
    # one more error on a letter-factor item: 0.3 against 5 of 20
    for factor, test in again({"P0surface_form": wrong}).items():
        assert test["above_letter_items"] == counted(5, 20) | {"difference": near(0.05)}
        assert test["floors"] == ALL_MET | {"above_letter": False, "met": False}, factor
    # the own error in another way: the same three errors, and none of them the factor's own
    other_kind = {
        "P0certainty": reading("recovery", certainty="estimated"),
        "P0stale": reading("recovery", "2020-06-01", "2020-06-30", "estimated", stale=True),
        "P0distractor": reading("depletion", *APRIL, "estimated"),
        "P0silent": reading("recovery", certainty="no_statement"),
    }
    for factor, test in again(other_kind).items():
        assert test["edited"] == counted(3, 10) and test["own_error"] == counted(0, 10)
        assert test["errors_of_another_kind"] == {"errors": 3, "share": 1.0}
        assert test["floors"] == ALL_MET | {"own_error": False, "met": False}, factor
    # where the own error can occur: a certainty item whose gold gives a period, a stale-factor
    # item whose gold is not stale and a distractor item whose quote gives no date are items
    # of their factor on which it cannot
    dated = gold("recovery", *APRIL, "estimated")
    less = dict(golds) | {"P9certainty": dated, "P9stale": dated, "P9distractor": dated}
    right = reading("recovery", *APRIL, "estimated")
    readings = given | {"P9certainty": right, "P9stale": right, "P9distractor": right}
    found = standing_tests(LS.score_e5(list(less), less, info, {LLAMA: readings}, {}))
    assert [found[f]["own_error"] for f in found] == [
        counted(1, 9),
        counted(1, 9),
        counted(1, 9),
        counted(1, 10),
    ]
    assert all(found[f]["edited"] == counted(3, 10) for f in found)
    # the wrong class of a letter-factor item counts under the criterion of the certainty
    # marker alone, its wrong stale flag under that of stale alone
    marked = given | {
        "P0surface_form": reading("recovery", *APRIL, "asserted"),
        "P1granularity": reading("recovery", *APRIL, "estimated", stale=True),
    }
    found = standing_tests(LS.score_e5(list(golds), golds, info, {LLAMA: marked}, {}))
    assert [found[f]["above_letter_items"]["errors"] for f in found] == [5, 5, 4, 4]
    assert [found[f]["floors"]["above_letter"] for f in found] == [False, False, True, True]


def test_e5_the_own_error_of_the_silent_factor_through_the_command(
    study: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str], e5: SimpleNamespace
) -> None:
    """The own error of silent through the command, on stored readings: llama's reading of the
    silent item of three seeds is given a period, where the gold gives none. The scripted
    error on a silent item is an abstention under another type, which is no own error."""
    silent = {study.pair_ids[s, "silent"]: s for s in range(PAIR_SEEDS)}
    dated = pair_answer(LLAMA, 0, "seed")
    given = [s for s in range(PAIR_SEEDS) if not pair_errs(LLAMA, s, "silent")][:3]
    assert dated["interval"] != "ABSTAIN" and len(given) == 3

    def commits(row: dict) -> dict:
        return row | {"reading": dated} if silent.get(row["item_id"]) in given else row

    before = next(t for t in e5.report["tests"][:6] if t["factor"] == "silent")
    assert before["own_error"] == counted(0, 12) | {"rate": 0.0}
    assert before["edited"]["errors"] == 1 and before["errors_of_another_kind"]["errors"] == 1
    with rewritten(study, run_of("e5", LLAMA), commits):
        report, _ = scored("e5", study, tmp_path, capsys)
    test = next(t for t in report["tests"][:6] if t["factor"] == "silent")
    assert test["model"] == LLAMA and test["edited"] == counted(4, 12) | {"rate": near(4 / 12)}
    assert test["own_error"] == counted(3, 12) | {"rate": 0.25}
    assert test["errors_of_another_kind"] == {"errors": 1, "share": 0.25}
    # 4 of 12 against 2 unedited and 7 of the 24 letter-factor items: 0.167 and 0.042 above
    assert test["unedited"]["errors"] == 2 and test["above_letter_items"]["errors"] == 7
    assert test["above_letter_items"]["difference"] == near(4 / 12 - 7 / 24)
    assert test["floors"] == {
        "above_seed": True,
        "above_letter": False,
        "own_error": True,
        "met": False,
    }
    # no other contrast moves: the own error of the other factors is what it was
    for name in ("certainty", "stale", "distractor"):
        mine = next(t for t in report["tests"][:6] if t["factor"] == name)
        theirs = next(t for t in e5.report["tests"][:6] if t["factor"] == name)
        assert mine["own_error"] == theirs["own_error"] and mine["floors"] == theirs["floors"]
    for mine, theirs in zip(report["tests"][6:], e5.report["tests"][6:], strict=True):
        assert mine.get("own_error") == theirs.get("own_error")
        assert mine.get("floors") == theirs.get("floors")


def letter_scope(items: int) -> LS.Scope:
    return LS.Scope(
        ids=[f"I{k:03d}" for k in range(items)],
        golds=[gold("recovery", *APRIL)] * items,
        strata=["x"] * items,
        marked=[False] * items,
        bases={"sample": np.ones(items)},
        taken=np.ones((5, items)),
    )


def letter_cols(right: int, items: int) -> dict[str, np.ndarray]:
    mine, off = reading("recovery", *APRIL), reading("recovery", "2020-06-01", "2020-06-30")
    return LS.columns([mine] * right + [off] * (items - right), [gold("recovery", *APRIL)] * items)


def read_letter(
    scope: LS.Scope, first: Mapping[str, np.ndarray], second: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    """The letter reading of two readers on a scope, as the scorer of E2 makes it: the figures
    of their letter accuracy, and the margin read on the exact lower end."""
    return LS.letter_reading(
        LS.letter_gap(scope, first, second), LS.letter_lower_end(scope, first, second)
    )


def test_the_margin_of_the_letter_part_is_read_on_the_exact_lower_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAN section 13, the letter part, (a), and "Small points of the reading": the lower end
    of the 90% interval must lie above -0.10, and an end of exactly -0.10 does not meet (a).
    The end is read as a fraction of whole numbers; the figure of the interval, which the
    result file shows at six decimals, decides nothing."""

    def found(low: float | None) -> dict[str, Any]:
        """A letter reading whose 90% interval is shown as starting at ``low``; its 95%
        interval starts 0.05 further down, as a wider interval does."""
        ci = None if low is None else {"low": low, "high": 0.0, "draws": 5}
        wider = None if low is None else {"low": low - 0.05, "high": 0.05, "draws": 5}
        pooled = {"first": 0.8, "second": 0.9, "difference": -0.1, "ci90": ci, "ci95": wider}
        return {"items": 10, "sample": pooled, "weighted_by_event": {"ci90": {"low": 0.5}}}

    def above(end: Fraction | None, shown: float | None = -0.5) -> bool | None:
        return LS.letter_reading(found(shown), end)["lower_end_above_minus_margin"]

    tenth, speck = Fraction(1, 10), Fraction(1, 10**9)
    assert above(-tenth) is False and above(-tenth - speck) is False
    assert above(Fraction(-1, 4)) is False
    assert above(-tenth + speck) is True and above(Fraction(0)) is True
    assert above(Fraction(3, 10)) is True
    assert round(float(-tenth + speck), 6) == -0.1  # six decimals would not tell the two apart
    # the figure shown decides nothing, neither that of the 90% interval nor that of the 95%
    assert above(-tenth, shown=0.25) is False and above(Fraction(-2, 25), shown=-0.5) is True
    assert above(Fraction(-2, 25), shown=-0.08) is True and found(-0.08)["sample"]["ci95"][
        "low"
    ] == pytest.approx(-0.13)
    assert above(None, shown=None) is None
    assert LS.letter_reading(found(-0.05), Fraction(-1, 20)) == {
        "items": 10,
        "first": 0.8,
        "second": 0.9,
        "difference": -0.1,
        "ci90": {"low": -0.05, "high": 0.0, "draws": 5},
        "ci95": {"low": -0.1, "high": 0.05, "draws": 5},
        "margin": 0.1,
        "lower_end_above_minus_margin": True,
    }
    # through the letter reading of two readers: 100 letter items, the rule reader right on
    # 99; a model right on 89 stands exactly 0.10 below in every draw, one right on 90 does not
    scope = letter_scope(100)
    rules = letter_cols(99, 100)
    exact = read_letter(scope, letter_cols(89, 100), rules)
    assert exact["difference"] == -0.1 and exact["ci90"] == {"low": -0.1, "high": -0.1, "draws": 5}
    assert LS.letter_lower_end(scope, letter_cols(89, 100), rules) == -tenth
    assert exact["lower_end_above_minus_margin"] is False and exact["items"] == 100
    closer = read_letter(scope, letter_cols(90, 100), rules)
    assert closer["ci90"]["low"] == -0.09 and closer["lower_end_above_minus_margin"] is True
    further = read_letter(scope, letter_cols(88, 100), rules)
    assert further["ci90"]["low"] == -0.11 and further["lower_end_above_minus_margin"] is False
    better = read_letter(scope, letter_cols(100, 100), rules)
    assert better["difference"] == 0.01 and better["lower_end_above_minus_margin"] is True
    # the two intervals on either side of the margin, from draws: a model wrong on 5 of 100
    # letter items that the rule reader has right stands 0.05 below in a draw that takes each
    # item once, and 15 of 110 below in a draw that takes its five wrong items three times.
    # With 4 such draws in 100 the 90% interval starts at -0.05 and the 95% one at -15/110
    spread = letter_scope(100)
    spread.taken = np.ones((100, 100))
    spread.taken[:4, 95:] = 3
    all_right, model = letter_cols(100, 100), letter_cols(95, 100)
    straddling = read_letter(spread, model, all_right)
    assert straddling["ci90"]["low"] == -0.05 and straddling["ci90"]["draws"] == 100
    assert straddling["ci95"]["low"] == pytest.approx(-15 / 110) and -15 / 110 < -0.1
    assert LS.letter_lower_end(spread, model, all_right) == Fraction(-1, 20)
    assert straddling["lower_end_above_minus_margin"] is True
    # with 5 such draws the end lies between the two values, 19 twentieths of the way up
    spread.taken[:5, 95:] = 3
    between = Fraction(-15, 110) + Fraction(19, 20) * (Fraction(-1, 20) - Fraction(-15, 110))
    assert LS.letter_lower_end(spread, model, all_right) == between == Fraction(-239, 4400)
    assert read_letter(spread, model, all_right)["ci90"]["low"] == pytest.approx(float(between))
    assert read_letter(spread, model, all_right)["lower_end_above_minus_margin"] is True
    # with 6 such draws in 100 the 90% interval starts at -15/110 too
    spread.taken[:6, 95:] = 3
    below = read_letter(spread, model, all_right)
    assert below["ci90"]["low"] == pytest.approx(-15 / 110)
    assert LS.letter_lower_end(spread, model, all_right) == Fraction(-3, 22)
    assert below["lower_end_above_minus_margin"] is False
    # without a letter item there is no interval, and no reading of the margin
    empty = LS.Scope(
        ["a"], [gold("recovery")], ["x"], [False], {"sample": np.ones(1)}, np.ones((2, 1))
    )
    cols = LS.columns([reading("recovery")], [gold("recovery")])
    none = read_letter(empty, cols, cols)
    assert none["items"] == 0 and none["ci90"] is None
    assert LS.letter_lower_end(empty, cols, cols) is None
    assert none["lower_end_above_minus_margin"] is None and none["margin"] == 0.1
    # a draw that holds no letter item is left out, as in the interval that is shown
    some = letter_scope(100)
    some.taken = np.ones((40, 100))
    some.taken[:30] = 0
    kept = read_letter(some, letter_cols(89, 100), rules)
    assert kept["ci90"] == {"low": -0.1, "high": -0.1, "draws": 10}
    assert kept["lower_end_above_minus_margin"] is False
    # the margin is the constant
    monkeypatch.setattr(LS, "LETTER_MARGIN", 0.11)
    assert above(-tenth) is True and above(Fraction(-11, 100)) is False
    assert LS.letter_reading(found(-0.1), -tenth)["margin"] == 0.11


INTERPOLATED = (
    (-29, 100, -9, 100),
    (-48, 100, -8, 100),
    (-10, 100, -10, 100),
    (-2, 20, -1, 10),
    (-67, 100, -7, 100),
    (-86, 100, -6, 100),
    (-105, 100, -5, 100),
    (-33, 110, -17, 190),
)
"""Pairs of values ``a`` and ``b`` with ``a + 19 b = -2``: where ``a`` and ``b`` are the two
order statistics around the fifth percentile of 10,000 draws, the percentile is ``a`` plus 19
twentieths of the way to ``b``, which is exactly -1/10."""


def test_the_lower_end_is_an_exact_fraction_at_the_position_of_the_percentile() -> None:
    """The percentile that decides the letter part, in exact fractions: linear interpolation
    between the two order statistics around the position, as the interval shown has it in
    floating point. An end that is -1/10 by interpolation between two other values is exactly
    -1/10, and does not lie above it; in floating point it reads as just above in some cases."""
    # the definition, against the percentile of the interval that is shown
    rows = (
        [Fraction(1, 3), Fraction(-1, 2), Fraction(2, 7), Fraction(0), Fraction(5, 9)],
        [Fraction(k * k - 40, 7 + k % 5) for k in range(23)],
        [Fraction(-1, 10)] * 4 + [Fraction(1, 10)],
    )
    for values in rows:
        above, below = [v.numerator for v in values], [v.denominator for v in values]
        for level in (
            Fraction(0),
            Fraction(5, 100),
            Fraction(1, 2),
            Fraction(95, 100),
            Fraction(1),
        ):
            exact = LS.exact_percentile(above, below, level)
            assert isinstance(exact, Fraction)
            shown = np.quantile([float(v) for v in values], float(level))
            assert float(exact) == pytest.approx(shown, abs=1e-12), (values, level)
    # by hand: 0, 1/2 and 1 at a quarter of the way stand at 1/4; in thirds, 1/3 of the way
    assert LS.exact_percentile([0, 1, 1], [1, 2, 1], Fraction(1, 4)) == Fraction(1, 4)
    assert LS.exact_percentile([1, 0, 1], [1, 1, 2], Fraction(1, 6)) == Fraction(1, 6)
    assert LS.exact_percentile([2, 1, 0, 4], [4, 2, 5, 8], Fraction(1, 2)) == Fraction(1, 2)
    # a place without a denominator is left out; with none left there is no percentile
    assert LS.exact_percentile([5, 0, 1, 7], [0, 1, 2, 0], Fraction(1, 2)) == Fraction(1, 4)
    assert LS.exact_percentile([5, 7], [0, 0], Fraction(1, 2)) is None
    assert LS.exact_percentile([], [], Fraction(1, 2)) is None
    assert LS.exact_percentile([-3], [4], Fraction(1, 20)) == Fraction(-3, 4)
    # the made-up sets of 10,000 draws: 499 below a, then a and b, then 9,499 above b
    shown_above = 0
    for a_num, a_den, b_num, b_den in INTERPOLATED:
        a, b = Fraction(a_num, a_den), Fraction(b_num, b_den)
        assert a + 19 * b == -2
        values = [b + Fraction(1, 20)] * 9499 + [a - Fraction(1, 50)] * 499 + [b, a]
        above, below = [v.numerator for v in values], [v.denominator for v in values]
        assert LS.exact_percentile(above, below, Fraction(5, 100)) == Fraction(-1, 10), (a, b)
        shown = LS.interval90(np.array(above) / np.array(below))
        assert shown["low"] == pytest.approx(-0.1, abs=1e-12) and shown["draws"] == 10_000
        shown_above += bool(shown["low"] > -0.1)
        if a - Fraction(1, 50) < -1:
            continue
        # the same draws as the letter reading of two readers on two letter items: the model
        # has the first wrong and the rule reader has both right, and a draw of value -p/q
        # takes the first item p times and the second q - p times
        golds = [gold("recovery", *APRIL)] * 2
        right, off = reading("recovery", *APRIL), reading("depletion", *APRIL)
        model, rules = LS.columns([off, right], golds), LS.columns([right, right], golds)
        scope = LS.Scope(["a", "b"], golds, ["x"] * 2, [False] * 2, {"sample": np.ones(2)}, None)

        def taken(row: Sequence[Fraction]) -> np.ndarray:
            return np.array([[-v.numerator, v.denominator + v.numerator] for v in row], float)

        scope.taken = taken(values)
        assert LS.letter_lower_end(scope, model, rules) == Fraction(-1, 10)
        found = read_letter(scope, model, rules)
        assert found["ci90"]["low"] == pytest.approx(-0.1, abs=1e-12)
        assert found["lower_end_above_minus_margin"] is False, (a, b)
        # one thousandth up or down at the upper of the two values, and the end is not -1/10
        for step, met in ((Fraction(1, 1000), True), (Fraction(-1, 1000), False)):
            scope.taken = taken([*values[:-2], b + step, a])
            lower, upper = sorted((a, b + step))
            moved = lower + Fraction(19, 20) * (upper - lower)
            assert moved != Fraction(-1, 10) and (moved > Fraction(-1, 10)) is met
            assert LS.letter_lower_end(scope, model, rules) == moved
            assert read_letter(scope, model, rules)["lower_end_above_minus_margin"] is met
    # read in floating point, some of these ends lie above -0.10
    assert shown_above >= 1


def test_a_model_better_than_the_rule_reader_meets_a_by_its_interval_alone() -> None:
    """PLAN section 13, the letter part: "Condition (a) sets no upper limit and is read on the
    interval alone." Three letter items in three episodes, the model right on two and the rule
    reader on the third alone: the model is one third above the rule reader, and a draw that
    takes the third item twice puts it one third below. More than a twentieth of the
    registered draws do, so the lower end is -1/3 and (a) is not met."""
    golds = [gold("recovery", *APRIL)] * 3
    right, off = reading("recovery", *APRIL), reading("depletion", *APRIL)
    scope = LS.Scope(
        ids=["a", "b", "c"],
        golds=golds,
        strata=["x"] * 3,
        marked=[False] * 3,
        bases={"sample": np.ones(3)},
        taken=LS.item_draws(["E1", "E2", "E3"]),
    )
    assert scope.taken.shape == (10_000, 3) and (scope.taken.sum(axis=1) == 3).all()
    model, rules = LS.columns([right, right, off], golds), LS.columns([off, off, right], golds)
    found = read_letter(scope, model, rules)
    assert found["items"] == 3 and found["first"] == pytest.approx(2 / 3)
    assert found["second"] == pytest.approx(1 / 3) and found["difference"] == pytest.approx(1 / 3)
    # the third item is taken three times in about one draw in 27, twice in about six in 27
    thrice = int((scope.taken[:, 2] == 3).sum())
    twice = int((scope.taken[:, 2] == 2).sum())
    assert thrice < 500 < thrice + twice
    assert LS.letter_lower_end(scope, model, rules) == Fraction(-1, 3)
    assert found["ci90"]["low"] == pytest.approx(-1 / 3) and found["ci90"]["draws"] == 10_000
    assert found["lower_end_above_minus_margin"] is False
    # a model as far above the rule reader that no draw puts below it meets (a): here the
    # rule reader is right on the second item alone, which the model has right too
    rules = LS.columns([off, right, off], golds)
    found = read_letter(scope, model, rules)
    assert found["difference"] == pytest.approx(1 / 3)
    assert LS.letter_lower_end(scope, model, rules) == Fraction(0)
    assert found["lower_end_above_minus_margin"] is True


def test_e2_the_letter_reading_of_each_primary(e2: SimpleNamespace) -> None:
    """PLAN section 5, E2, "Letter reading": one entry for each primary on every item set, the
    figures those of the model against the rule reader pooled without weights."""
    for name, scored_set in e2.report["item_sets"].items():
        entries = scored_set["letter_reading"]
        assert [entry["model"] for entry in entries] == [LLAMA, DEEPSEEK], name
        for entry in entries:
            versus = scored_set["versus_rules"][entry["model"]][V1]["letter_accuracy"]
            assert entry == {
                "model": entry["model"],
                "template": V1,
                "against": "rules",
                "evaluable": True,
                "items": versus["items"],
                **versus["sample"],
                "margin": 0.1,
                "lower_end_above_minus_margin": True,
            }
            assert entry["ci90"]["low"] > -0.1
    whole = e2.report["item_sets"]["all"]["letter_reading"]
    assert [entry["items"] for entry in whole] == [14, 14]
    assert whole[0]["first"] == near(13 / 14) and whole[0]["second"] == near(8 / 14)
    assert whole[1]["difference"] == near(6 / 14)


# --------------------------------------------------------------------------------------------
# The command `pattern` on result files written out by hand
# --------------------------------------------------------------------------------------------

STRONG = {"edited": (40, 100), "unedited": (10, 100), "holds": True, "own": (20, 100)}
"""A test of a standing factor that counts: it holds, 0.40 against 0.10 on the unedited items
and 0.20 on the letter-factor items, the own error on 20 of 100 items."""
NO_STANDING_TEST = (
    "(a): no E5 test of a standing factor holds, under Holm over the twelve tests, with the "
    "higher error rate on the edited items"
)
LOWER_END = (
    "(a): the lower end of the 90% interval of the difference in letter accuracy, model minus "
    "rule reader, does not lie above -0.10"
)
NO_SECONDARY = (
    "the paper states the sentence for no secondary model and uses no plural that includes one"
)
BOTH = (
    "the pattern holds for both primaries: the paper states the sentence for the two primary models"
)
NEITHER = (
    "the pattern holds for neither primary: the paper does not state the sentence and reports "
    "each part for each primary"
)


def one_named(model: str, other: str, *parts: str) -> str:
    missed = " part and the ".join(parts)
    return (
        "the pattern holds for one primary: the paper states the sentence for that model by "
        f"name ({model}) and says in the same place which part did not hold for the other "
        f"({other}: the {missed} part)"
    )


def family_result(model: str, factor: str, side: str = "the edited items") -> str:
    return (
        f"{model}, {factor}: this test of the E5 family holds, with the higher error rate on "
        f"{side}; it is reported as that family's result, with its size, also when a floor or "
        "the other part withholds the sentence, and the paper then does not write that no "
        "effect was detected"
    )


def criterion_beside(model: str) -> str:
    return (
        f"{model}: the paragraph that states the sentence gives the outcome of the "
        "overconfidence criterion of section 13 for the model, whichever way it came out"
    )


def own_error_beside(model: str, factor: str) -> str:
    return (
        f"{model}, {factor}: the paper gives the rate of its own error in the sentence that "
        "names it, and the share of the factor's errors that are of another kind"
    )


def not_held(model: str, part: str, *withheld: str) -> str:
    return (
        f"{model}: the {part} part does not hold; it is not read as its opposite, and the paper "
        f"says which condition withheld it: {'; '.join(withheld)}"
    )


def below_floor(factor: str, what: str) -> str:
    return (
        f"(b) on {factor}: the error rate on the items of the factor is not at least 0.10 above "
        f"the error rate on {what}"
    )


def registered() -> dict[str, Any]:
    """The registered record as a result file holds it."""
    return json.loads(LS.report_text(LS.registered_record()))


def letter_of(model: str, low: float = 0.02, **change: Any) -> dict[str, Any]:
    """The letter reading of a primary in a hand-built E2 result: 72 letter items, the model
    right on 63 and the rule reader on 54, and the lower end of the 90% interval as given."""
    entry = {
        "model": model,
        "template": V1,
        "against": "rules",
        "evaluable": True,
        "items": 72,
        "first": 0.875,
        "second": 0.75,
        "difference": 0.125,
        "ci90": {"low": low, "high": 0.25, "draws": 10000},
        "ci95": {"low": low - 0.03, "high": 0.28, "draws": 10000},
        "margin": 0.1,
        "lower_end_above_minus_margin": low > -0.1,
    }
    return entry | change


def no_letter(model: str, why: str = "declared on the command line: no route") -> dict[str, Any]:
    return {"model": model, "template": V1, "against": "rules", "evaluable": False, "why": why}


def made_e2(*entries: dict[str, Any], items: int = 120, plan: str = "a" * 64) -> dict[str, Any]:
    """An E2 result with what the pattern reads of one, and nothing else."""
    ids = [f"L{k:03d}" for k in range(items)]
    scored_as = {f"{e['model']} {V1}": [[i, 1, 1] for i in ids] for e in entries if e["evaluable"]}
    return {
        "about": LS.ABOUT_E2,
        "registered": registered(),
        "inputs": {
            "plan_sha256": plan,
            "gold_sha256": "b" * 64,
            "code": {"literal_scores.py": "c" * 64},
        },
        "not_run": dict(LS.NORMALISERS_NOT_RUN),
        "item_sets": {"all": {"items": items, "letter_reading": list(entries)}},
        "per_item": {
            "columns": ["item_id", "correct", "parsed"],
            "item_set": "all",
            "readers": scored_as,
        },
    }


def pair_test(
    model: str,
    factor: str,
    edited: tuple[int, int] = (20, 100),
    unedited: tuple[int, int] = (20, 100),
    holds: bool = False,
    letter: tuple[int, int] = (40, 200),
    own: tuple[int, int] = (0, 100),
    evaluable: bool = True,
    why: str = FEW_SEEDS,
) -> dict[str, Any]:
    """One test of the twelve in a hand-built E5 result, from the errors and the items of its
    edited and of its unedited side; for a standing factor also from those of the letter-factor
    items and of its own error, with the floors as fractions of whole numbers give them."""
    entry: dict[str, Any] = {"model": model, "factor": factor, "primary": True}
    if not evaluable:
        return entry | {"evaluable": False, "why": why, "p": 1.0, "p_holm": 1.0, "holds": False}
    here, there, tenth = Fraction(*edited), Fraction(*unedited), Fraction(1, 10)
    entry |= {
        "evaluable": True,
        "against": LS.seed_cell(factor),
        "edited": counted(*edited),
        "unedited": counted(*unedited),
        "difference": float(here - there),
        "log_odds_difference": 0.5,
        "p_from": "gee",
        "p": 0.0004 if holds else 0.4,
        "p_holm": 0.0048 if holds else 1.0,
        "holds": holds,
    }
    if factor in LS.STANDING_FACTORS:
        others = Fraction(*letter) if letter[1] else None
        met = {
            "above_seed": here - there >= tenth,
            "above_letter": others is not None and here - others >= tenth,
            "own_error": bool(own[1]) and Fraction(*own) >= tenth,
        }
        gap = None if others is None else float(here - others)
        entry |= {
            "above_letter_items": counted(*letter) | {"difference": gap},
            "own_error": counted(*own),
            "errors_of_another_kind": {
                "errors": edited[0] - own[0],
                "share": (edited[0] - own[0]) / edited[0] if edited[0] else None,
            },
            "floors": met | {"met": all(met.values())},
        }
    return entry


def made_e5(
    tests: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    not_run: Mapping[str, str] | None = None,
    items: int = 800,
    plan: str = "a" * 64,
    cut: Mapping[str, Any] | None = None,
    others: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """An E5 result with what the pattern reads of one. ``tests`` gives what a test of the
    twelve is made of, by model and factor; every other test holds nothing, with 0.20 on each
    side. A primary declared not run has six tests that are not evaluable, and no flags."""
    tests, not_run = dict(tests or {}), dict(not_run or {})
    ids = [f"P{k:04d}" for k in range(items)]
    family = [
        pair_test(model, factor, evaluable=False, why=not_run[model])
        if model in not_run
        else pair_test(model, factor, **tests.get((model, factor), {}))
        for model in (LLAMA, DEEPSEEK)
        for factor in MP.FACTORS
    ]
    whole = {
        "cut": False,
        "items_in_the_item_file": items,
        "items": items,
        "item_ids_sha256": lp.ids_sha256(ids),
    }
    return {
        "about": LS.ABOUT_E5,
        "registered": registered(),
        "inputs": {
            "plan_sha256": plan,
            "gold_sha256": "d" * 64,
            "code": {"literal_scores.py": "c" * 64},
        },
        "item_set": whole | dict(cut or {}),
        "items": items,
        "seeds": items // 8,
        "not_run": not_run,
        "gee": {"method_in_force": "the GEE with its robust variance"},
        "tests": family,
        "other_models": list(others),
        "per_item": {
            "columns": ["item_id", "error", "parsed"],
            "readers": {
                model: [[i, 0, 1] for i in ids]
                for model in (LLAMA, DEEPSEEK)
                if model not in not_run
            },
        },
    }


def pattern_argv(folder: Path, e2: Any, e5: Any, out: Path) -> list[str]:
    """The arguments of ``pattern`` on two results written to ``folder``; ``e5`` None declares
    that E5 is not scored. A result is written as JSON unless it is already a path."""
    argv = ["pattern", "--out", str(out)]
    for name, result in (("e2", e2), ("e5", e5)):
        if result is None:
            argv += ["--e5-not-scored"] if name == "e5" else []
            continue
        path = result if isinstance(result, Path) else folder / f"{name}.json"
        if not isinstance(result, Path):
            path.write_text(json.dumps(result), encoding="utf-8")
        argv += [f"--{name}", str(path)]
    return argv


def patterned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: Any, e5: Any
) -> tuple[dict[str, Any], str]:
    """Run ``pattern`` on two results: its result file and its printout."""
    folder = tmp_path / f"pattern_{len(list(tmp_path.iterdir()))}"
    folder.mkdir()
    out = folder / "pattern.json"
    capsys.readouterr()
    assert LS.main(pattern_argv(folder, e2, e5, out)) == 0
    printed = capsys.readouterr()
    assert printed.err == "" and printed.out.endswith(f"wrote {out.as_posix()}\n")
    return json.loads(out.read_text()), printed.out


def pattern_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], e2: Any, e5: Any, *extra: str
) -> str:
    """The reason ``pattern`` refuses two results for: nothing printed, nothing written."""
    folder = tmp_path / f"refused_{len(list(tmp_path.iterdir()))}"
    folder.mkdir()
    out = folder / "pattern.json"
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        LS.main([*pattern_argv(folder, e2, e5, out), *extra])
    assert isinstance(stop.value.code, str) and stop.value.code.startswith("refused: ")
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == "" and not out.exists()
    return stop.value.code


def test_the_pattern_holds_for_both_primaries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both parts hold for each primary: the sentence is stated for the two primary models."""
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK, low=-0.0999))
    e5 = made_e5(
        {(LLAMA, "certainty"): STRONG, (DEEPSEEK, "stale"): STRONG, (DEEPSEEK, "silent"): STRONG}
    )
    report, printed = patterned(tmp_path, capsys, e2, e5)
    assert list(report) == [
        "about",
        "registered",
        "inputs",
        "e2",
        "e5",
        "primaries",
        "sentence",
        "as_the_plan_says",
        "where_the_plan_is_silent",
    ]
    assert report["about"] == LS.ABOUT_PATTERN and report["registered"] == registered()
    assert report["as_the_plan_says"] == list(LS.AS_THE_PLAN_SAYS)
    assert report["where_the_plan_is_silent"] == list(LS.WHERE_THE_PLAN_IS_SILENT)
    assert report["e2"] == {"item_set": "all", "items": 120}
    assert report["e5"] == {
        "scored": True,
        "item_set": e5["item_set"],
        "items": 800,
        "seeds": 100,
        "method_in_force": "the GEE with its robust variance",
    }
    folder = tmp_path / "pattern_0"
    assert report["inputs"] == {
        "e2": (folder / "e2.json").as_posix(),
        "e2_sha256": sha(folder / "e2.json"),
        "e5": (folder / "e5.json").as_posix(),
        "e5_sha256": sha(folder / "e5.json"),
        "plan_sha256": "a" * 64,
        "gold_sha256": {"e2": "b" * 64, "e5": "d" * 64},
        "code_of_the_results": {"e2": "c" * 64, "e5": "c" * 64},
        "code": report["inputs"]["code"],
    }
    assert report["inputs"]["code"]["literal_scores.py"] == sha(Path(LS.__file__))
    assert list(report["primaries"]) == [LLAMA, DEEPSEEK]
    llama = report["primaries"][LLAMA]
    assert list(llama) == [
        "has_pattern",
        "declared_not_run",
        "letter",
        "standing",
        "holds",
        "e5_tests_that_hold",
    ]
    assert llama["has_pattern"] is True and llama["declared_not_run"] == []
    assert llama["holds"] is True
    plain_test = {
        "evaluable": True,
        "holds": False,
        "p_holm": 1.0,
        "p_from": "gee",
        "edited": counted(20, 100),
        "unedited": counted(20, 100),
        "difference": 0.0,
        "higher_on_edited": False,
    }
    assert llama["letter"] == {
        "e2": {
            "items": 72,
            "first": 0.875,
            "second": 0.75,
            "difference": 0.125,
            "ci90": {"low": 0.02, "high": 0.25, "draws": 10000},
            "ci95": {"low": -0.01, "high": 0.28, "draws": 10000},
            "margin": 0.1,
            "lower_end_above_minus_margin": True,
            "met": True,
        },
        "e5": {
            "surface_form": plain_test | {"withholds": False},
            "granularity": plain_test | {"withholds": False},
            "met": True,
        },
        "holds": True,
        "withheld_by": [],
    }
    standing = llama["standing"]
    assert list(standing) == [*LS.STANDING_FACTORS, "factors_that_count", "holds", "withheld_by"]
    assert standing["certainty"] == {
        "a": {
            "evaluable": True,
            "holds": True,
            "p_holm": 0.0048,
            "p_from": "gee",
            "edited": counted(40, 100),
            "unedited": counted(10, 100),
            "difference": near(0.3),
            "higher_on_edited": True,
            "met": True,
        },
        "b": {
            "floor": 0.1,
            "above_seed": {"difference": near(0.3), "met": True},
            "above_letter": counted(40, 200) | {"difference": near(0.2), "met": True},
            "met": True,
        },
        "c": {"floor": 0.1, **counted(20, 100), "met": True},
        "errors_of_another_kind": {"errors": 20, "share": 0.5},
        "counts": True,
    }
    # a factor without a test: every condition is given, and none is met
    assert standing["stale"] == {
        "a": plain_test | {"met": False},
        "b": {
            "floor": 0.1,
            "above_seed": {"difference": 0.0, "met": False},
            "above_letter": counted(40, 200) | {"difference": 0.0, "met": False},
            "met": False,
        },
        "c": {"floor": 0.1, **counted(0, 100), "met": False},
        "errors_of_another_kind": {"errors": 20, "share": 1.0},
        "counts": False,
    }
    assert standing["factors_that_count"] == ["certainty"] and standing["holds"] is True
    assert standing["withheld_by"] == []
    assert llama["e5_tests_that_hold"] == [
        {
            "factor": "certainty",
            "kind": "standing",
            "higher_error_rate_on": "the edited items",
            "edited": counted(40, 100),
            "unedited": counted(10, 100),
            "difference": near(0.3),
            "log_odds_difference": 0.5,
            "p_holm": 0.0048,
            "p_from": "gee",
        }
    ]
    deepseek = report["primaries"][DEEPSEEK]
    assert deepseek["holds"] is True and deepseek["letter"]["e2"]["met"] is True
    assert deepseek["letter"]["e2"]["ci90"]["low"] == -0.0999
    assert deepseek["standing"]["factors_that_count"] == ["stale", "silent"]
    assert [held["factor"] for held in deepseek["e5_tests_that_hold"]] == ["stale", "silent"]
    assert report["sentence"] == {
        "sentence": "models read the letter of a notice but not its pragmatics",
        "case": "both primaries",
        "stated_for": [LLAMA, DEEPSEEK],
        "paper": BOTH,
        "beside": [
            family_result(LLAMA, "certainty"),
            family_result(DEEPSEEK, "stale"),
            family_result(DEEPSEEK, "silent"),
            criterion_beside(LLAMA),
            own_error_beside(LLAMA, "certainty"),
            criterion_beside(DEEPSEEK),
            own_error_beside(DEEPSEEK, "stale"),
            own_error_beside(DEEPSEEK, "silent"),
            NO_SECONDARY,
        ],
    }
    # the printout: one line for each part of each primary with its numbers, then the sentence
    lines = printed.splitlines()
    assert len(lines) == 1 + 2 * 2 + 1 + 9 + 1
    assert lines[0] == (
        "pattern of PLAN section 13: E2 on 120 gold items; E5 on 800 items of 100 seeds (the "
        "GEE with its robust variance)"
    )
    flat = "0.200 against 0.200 unedited (+0.000), Holm 1.0000, does not hold"
    assert lines[1] == (
        f"{LLAMA} letter: holds; (a) letter accuracy 0.875 against 0.750 of the rule reader on "
        "72 letter items, difference +0.125, 90% interval +0.020 to +0.250, lower end above "
        f"-0.10; (b) surface_form: {flat}; (b) granularity: {flat}"
    )
    none = (
        f"{flat}, 0.200 on the letter-factor items (+0.000), own error 0 of 100, (a, b, c) not met"
    )
    assert lines[2] == (
        f"{LLAMA} standing: holds by certainty; certainty: 0.400 against 0.100 unedited "
        "(+0.300), Holm 0.0048, holds with the higher rate on the edited items, 0.200 on the "
        "letter-factor items (+0.200), own error 20 of 100, counts; "
        f"stale: {none}; distractor: {none}; silent: {none}"
    )
    assert lines[3].startswith(f"{DEEPSEEK} letter: holds; (a) letter accuracy 0.875 against")
    assert "90% interval -0.100 to +0.250, lower end above -0.10" in lines[3]
    assert lines[4].startswith(f"{DEEPSEEK} standing: holds by stale, silent; certainty: {none}; ")
    assert lines[5] == f"sentence: {BOTH}"
    assert lines[6:15] == [f"beside it: {text}" for text in report["sentence"]["beside"]]
    # the result file is the scorer's own text of the report, and the command reads the two
    # result files and its own code, and nothing else
    out = folder / "pattern.json"
    assert out.read_text() == LS.report_text(report)
    out.unlink()
    with watching() as touched:
        assert LS.main(pattern_argv(folder, folder / "e2.json", folder / "e5.json", out)) == 0
    opened = {entry.split(" ", 1)[1] for entry in touched if entry.startswith("open ")}
    here = Path(LS.__file__).resolve().parent
    assert {str(folder / "e2.json"), str(folder / "e5.json"), str(out)} <= opened
    assert all(Path(path).parent in (folder, here) for path in opened), sorted(opened)
    assert not any(entry.startswith("os.") for entry in touched)
    capsys.readouterr()


def test_the_pattern_holds_for_one_primary_and_the_paper_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One primary has both parts; for the other a test of a standing factor holds and a floor
    withholds it: 0.25 on its items against 0.10 on the unedited ones and 0.16 on the
    letter-factor items, which is less than 0.10 above."""
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK))
    near_letter = {"edited": (25, 100), "unedited": (10, 100), "holds": True, "letter": (32, 200)}
    tests = {(LLAMA, "distractor"): STRONG, (DEEPSEEK, "stale"): near_letter | {"own": (25, 100)}}
    report, printed = patterned(tmp_path, capsys, e2, made_e5(tests))
    llama, deepseek = report["primaries"][LLAMA], report["primaries"][DEEPSEEK]
    assert llama["holds"] is True and deepseek["holds"] is False
    assert deepseek["letter"]["holds"] is True and deepseek["standing"]["holds"] is False
    stale = deepseek["standing"]["stale"]
    assert stale["a"]["met"] is True and stale["c"]["met"] is True and stale["counts"] is False
    assert stale["b"] == {
        "floor": 0.1,
        "above_seed": {"difference": near(0.15), "met": True},
        "above_letter": counted(32, 200) | {"difference": near(0.09), "met": False},
        "met": False,
    }
    withheld = below_floor("stale", "the items of the two letter factors taken together")
    assert deepseek["standing"]["withheld_by"] == [withheld]
    assert deepseek["standing"]["factors_that_count"] == []
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "one primary",
        "stated_for": [LLAMA],
        "paper": one_named(LLAMA, DEEPSEEK, "standing"),
        "beside": [
            not_held(DEEPSEEK, "standing", withheld),
            family_result(LLAMA, "distractor"),
            family_result(DEEPSEEK, "stale"),
            criterion_beside(LLAMA),
            own_error_beside(LLAMA, "distractor"),
            NO_SECONDARY,
        ],
    }
    assert f"{DEEPSEEK} standing: does not hold; " in printed
    assert (
        "stale: 0.250 against 0.100 unedited (+0.150), Holm 0.0048, holds with the higher rate "
        "on the edited items, 0.160 on the letter-factor items (+0.090), own error 25 of 100, "
        "(b) not met"
    ) in printed
    # the other way round, and with both parts missed by the other primary
    tests = {
        (DEEPSEEK, "silent"): STRONG,
        (LLAMA, "granularity"): {"edited": (30, 100), "holds": True},
    }
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK, low=0.3))
    report, _ = patterned(tmp_path, capsys, e2, made_e5(tests))
    assert report["sentence"]["stated_for"] == [DEEPSEEK]
    assert report["sentence"]["paper"] == one_named(DEEPSEEK, LLAMA, "letter", "standing")
    assert report["sentence"]["paper"].endswith(f"({LLAMA}: the letter part and the standing part)")
    assert report["sentence"]["beside"][:2] == [
        not_held(
            LLAMA,
            "letter",
            "(b): the E5 test on granularity holds with the higher error rate on the edited items",
        ),
        not_held(LLAMA, "standing", NO_STANDING_TEST),
    ]


def test_the_letter_part_is_withheld_by_the_margin_or_by_a_test_on_a_letter_factor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Neither primary has the pattern though the standing part holds for both. Condition (a):
    a lower end of exactly -0.10, or below it. Condition (b): a test on a letter factor that
    holds with the higher error rate on the edited items."""
    counting = {(LLAMA, "stale"): STRONG, (DEEPSEEK, "stale"): STRONG}
    e2 = made_e2(letter_of(LLAMA, low=-0.1), letter_of(DEEPSEEK, low=-0.25))
    report, printed = patterned(tmp_path, capsys, e2, made_e5(counting))
    for model in (LLAMA, DEEPSEEK):
        found = report["primaries"][model]
        assert found["holds"] is False and found["standing"]["holds"] is True
        assert found["letter"]["e2"]["met"] is False and found["letter"]["e5"]["met"] is True
        assert found["letter"]["e2"]["lower_end_above_minus_margin"] is False
        assert found["letter"]["holds"] is False and found["letter"]["withheld_by"] == [LOWER_END]
    assert report["primaries"][LLAMA]["letter"]["e2"]["ci90"]["low"] == -0.1
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "neither primary",
        "stated_for": [],
        "paper": NEITHER,
        "beside": [
            not_held(LLAMA, "letter", LOWER_END),
            not_held(DEEPSEEK, "letter", LOWER_END),
            family_result(LLAMA, "stale"),
            family_result(DEEPSEEK, "stale"),
            # the factor counts for each, and is named with its own error though the letter
            # part withholds the sentence; the overconfidence criterion goes with a sentence
            own_error_beside(LLAMA, "stale"),
            own_error_beside(DEEPSEEK, "stale"),
            NO_SECONDARY,
        ],
    }
    assert not any("overconfidence" in text for text in report["sentence"]["beside"])
    assert "90% interval -0.100 to +0.250, lower end not above -0.10" in printed
    assert f"{LLAMA} letter: does not hold; " in printed and f"sentence: {NEITHER}\n" in printed
    # an end just above -0.10 meets (a), as the E2 result read it before rounding
    e2 = made_e2(letter_of(LLAMA, low=-0.099999), letter_of(DEEPSEEK, low=-0.25))
    report, _ = patterned(tmp_path, capsys, e2, made_e5(counting))
    assert report["primaries"][LLAMA]["holds"] is True
    assert report["sentence"]["stated_for"] == [LLAMA]
    # the decision is the one of the E2 result, which read the end before rounding: -0.1 in the
    # file, above the margin in the scorer
    rounded = letter_of(LLAMA, low=-0.1, lower_end_above_minus_margin=True)
    report, printed = patterned(
        tmp_path, capsys, made_e2(rounded, letter_of(DEEPSEEK)), made_e5(counting)
    )
    assert report["primaries"][LLAMA]["letter"]["e2"]["met"] is True
    assert "90% interval -0.100 to +0.250, lower end above -0.10" in printed
    # no interval at all: no gold letter item
    empty = letter_of(
        LLAMA, items=0, first=None, second=None, difference=None, ci90=None, ci95=None
    )
    empty["lower_end_above_minus_margin"] = None
    report, printed = patterned(
        tmp_path, capsys, made_e2(empty, letter_of(DEEPSEEK)), made_e5(counting)
    )
    assert report["primaries"][LLAMA]["letter"]["withheld_by"] == [
        "(a): the difference in letter accuracy has no 90% interval (no gold letter item, or no "
        "draw that holds one)"
    ]
    assert report["primaries"][LLAMA]["holds"] is False
    assert "(a) letter accuracy - against - of the rule reader on 0 letter items" in printed
    assert "difference -, 90% interval - to -, lower end not above -0.10" in printed
    # condition (b): a letter-factor test that holds with the higher rate on the edited items
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK))
    higher = {"edited": (35, 100), "unedited": (20, 100), "holds": True}
    lower = {"edited": (5, 100), "unedited": (20, 100), "holds": True}
    tests = counting | {(LLAMA, "surface_form"): higher, (DEEPSEEK, "granularity"): higher}
    report, printed = patterned(tmp_path, capsys, e2, made_e5(tests))
    surface = (
        "(b): the E5 test on surface_form holds with the higher error rate on the edited items"
    )
    granular = (
        "(b): the E5 test on granularity holds with the higher error rate on the edited items"
    )
    llama = report["primaries"][LLAMA]["letter"]
    assert llama["e2"]["met"] is True and llama["holds"] is False
    assert llama["e5"]["met"] is False and llama["withheld_by"] == [surface]
    assert llama["e5"]["surface_form"]["withholds"] is True
    assert llama["e5"]["granularity"]["withholds"] is False
    assert report["primaries"][DEEPSEEK]["letter"]["withheld_by"] == [granular]
    assert report["sentence"]["case"] == "neither primary"
    assert report["sentence"]["beside"] == [
        not_held(LLAMA, "letter", surface),
        not_held(DEEPSEEK, "letter", granular),
        family_result(LLAMA, "surface_form"),
        family_result(LLAMA, "stale"),
        family_result(DEEPSEEK, "granularity"),
        family_result(DEEPSEEK, "stale"),
        own_error_beside(LLAMA, "stale"),
        own_error_beside(DEEPSEEK, "stale"),
        NO_SECONDARY,
    ]
    assert report["primaries"][LLAMA]["e5_tests_that_hold"][0]["kind"] == "letter"
    assert (
        "(b) surface_form: 0.350 against 0.200 unedited (+0.150), Holm 0.0048, holds with the "
        "higher rate on the edited items"
    ) in printed
    # condition (a) sets no upper limit and is read on the interval alone: a model one third
    # above the rule reader on three letter items, with an interval that starts one third below
    above_rules = letter_of(LLAMA, low=-0.333333, items=3, first=0.666667, second=0.333333)
    above_rules |= {"difference": 0.333333}
    assert above_rules["lower_end_above_minus_margin"] is False
    e2 = made_e2(above_rules, letter_of(DEEPSEEK))
    report, printed = patterned(tmp_path, capsys, e2, made_e5(counting))
    llama = report["primaries"][LLAMA]
    assert llama["letter"]["e2"]["difference"] > 0 and llama["letter"]["e2"]["met"] is False
    assert llama["letter"]["withheld_by"] == [LOWER_END] and llama["holds"] is False
    assert report["sentence"]["stated_for"] == [DEEPSEEK]
    assert (
        "(a) letter accuracy 0.667 against 0.333 of the rule reader on 3 letter items, "
        "difference +0.333, 90% interval -0.333 to +0.250, lower end not above -0.10"
    ) in printed
    # both conditions at once are both named
    e2 = made_e2(letter_of(LLAMA, low=-0.2), letter_of(DEEPSEEK))
    report, _ = patterned(tmp_path, capsys, e2, made_e5(tests))
    assert report["primaries"][LLAMA]["letter"]["withheld_by"] == [LOWER_END, surface]
    # a letter-factor test that holds with the lower error rate on the edited items withholds
    # nothing, and neither does one that is not evaluable; each test that holds is reported
    tests = counting | {
        (LLAMA, "surface_form"): lower,
        (LLAMA, "granularity"): {"evaluable": False},
    }
    report, printed = patterned(
        tmp_path, capsys, made_e2(letter_of(LLAMA), letter_of(DEEPSEEK)), made_e5(tests)
    )
    llama = report["primaries"][LLAMA]
    assert llama["holds"] is True and llama["letter"]["e5"]["met"] is True
    assert llama["letter"]["e5"]["surface_form"]["holds"] is True
    assert llama["letter"]["e5"]["surface_form"]["higher_on_edited"] is False
    assert llama["letter"]["e5"]["granularity"] == {
        "evaluable": False,
        "why": FEW_SEEDS,
        "holds": False,
        "higher_on_edited": False,
        "withholds": False,
    }
    assert report["sentence"]["case"] == "both primaries"
    assert (
        family_result(LLAMA, "surface_form", "the unedited seed items")
        in report["sentence"]["beside"]
    )
    assert (
        "holds with the lower rate on the edited items; (b) granularity: not evaluable" in printed
    )


def test_a_standing_test_that_holds_is_withheld_by_a_floor_or_by_the_own_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Conditions (b) and (c) can only withhold: a test of a standing factor holds with the
    higher error rate on the edited items, and the factor does not count. The test is still
    the result of its family."""
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK))
    tests = {
        # 0.19 against 0.10 unedited: 0.09 above; the letter-factor items at 0.02
        (LLAMA, "stale"): {
            "edited": (19, 100),
            "unedited": (10, 100),
            "holds": True,
            "letter": (4, 200),
            "own": (19, 100),
        },
        # every floor of (b) met, and the own error on 9 of 100 items
        (LLAMA, "certainty"): STRONG | {"own": (9, 100)},
        # every floor missed
        (DEEPSEEK, "silent"): {
            "edited": (24, 100),
            "unedited": (15, 100),
            "holds": True,
            "letter": (30, 200),
            "own": (2, 100),
        },
        # the test holds with the lower error rate on the edited items
        (DEEPSEEK, "distractor"): {
            "edited": (2, 100),
            "unedited": (30, 100),
            "holds": True,
            "letter": (2, 200),
            "own": (2, 10),
        },
    }
    report, printed = patterned(tmp_path, capsys, e2, made_e5(tests))
    llama, deepseek = report["primaries"][LLAMA], report["primaries"][DEEPSEEK]
    unedited, letters = (
        "the unedited seed items",
        "the items of the two letter factors taken together",
    )
    own = "the factor's own error does not occur on at least 0.10 of the items of the factor on which it can occur"
    for found in (llama, deepseek):
        assert found["holds"] is False and found["letter"]["holds"] is True
        assert found["standing"]["holds"] is False and found["standing"]["factors_that_count"] == []
    stale, certainty = llama["standing"]["stale"], llama["standing"]["certainty"]
    assert stale["a"]["met"] is True and stale["counts"] is False
    assert stale["b"]["above_seed"] == {"difference": near(0.09), "met": False}
    assert stale["b"]["above_letter"]["met"] is True and stale["b"]["met"] is False
    assert stale["c"] == {"floor": 0.1, **counted(19, 100), "met": True}
    assert certainty["a"]["met"] is True and certainty["b"]["met"] is True
    assert certainty["c"] == {"floor": 0.1, **counted(9, 100), "met": False}
    assert certainty["counts"] is False
    assert certainty["errors_of_another_kind"] == {"errors": 31, "share": near(31 / 40)}
    # the factors in the plan's order, each with the conditions it misses
    assert llama["standing"]["withheld_by"] == [
        f"(c) on certainty: {own}",
        below_floor("stale", unedited),
    ]
    silent, distractor = deepseek["standing"]["silent"], deepseek["standing"]["distractor"]
    assert (
        silent["a"]["met"] is True and silent["b"]["met"] is False and silent["c"]["met"] is False
    )
    assert distractor["a"]["holds"] is True and distractor["a"]["higher_on_edited"] is False
    assert distractor["a"]["met"] is False and distractor["c"]["met"] is True
    assert deepseek["standing"]["withheld_by"] == [
        below_floor("silent", unedited),
        below_floor("silent", letters),
        f"(c) on silent: {own}",
    ]
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "neither primary",
        "stated_for": [],
        "paper": NEITHER,
        "beside": [
            not_held(LLAMA, "standing", *llama["standing"]["withheld_by"]),
            not_held(DEEPSEEK, "standing", *deepseek["standing"]["withheld_by"]),
            family_result(LLAMA, "certainty"),
            family_result(LLAMA, "stale"),
            family_result(DEEPSEEK, "distractor", "the unedited seed items"),
            family_result(DEEPSEEK, "silent"),
            NO_SECONDARY,
        ],
    }
    assert "own error 9 of 100, (c) not met" in printed
    assert "own error 19 of 100, (b) not met" in printed
    assert "own error 2 of 100, (b, c) not met" in printed
    assert (
        "distractor: 0.020 against 0.300 unedited (-0.280), Holm 0.0048, holds with the lower "
        "rate on the edited items, 0.010 on the letter-factor items (+0.010), own error 2 of "
        "10, (a, b) not met"
    ) in printed
    # with no test of a standing factor that holds with the higher rate, (a) withholds, also
    # where every floor is met; a test that is not evaluable has no floors to read
    tests = {
        (LLAMA, "stale"): STRONG | {"holds": False},
        (LLAMA, "silent"): {"evaluable": False},
        (DEEPSEEK, "distractor"): tests[DEEPSEEK, "distractor"],
    }
    report, printed = patterned(tmp_path, capsys, e2, made_e5(tests))
    llama = report["primaries"][LLAMA]["standing"]
    assert llama["stale"]["b"]["met"] is True and llama["stale"]["c"]["met"] is True
    assert llama["stale"]["a"]["met"] is False and llama["stale"]["counts"] is False
    assert llama["silent"] == {
        "a": {
            "evaluable": False,
            "why": FEW_SEEDS,
            "holds": False,
            "higher_on_edited": False,
            "met": False,
        },
        "b": None,
        "c": None,
        "counts": False,
    }
    assert llama["withheld_by"] == [NO_STANDING_TEST]
    assert report["primaries"][DEEPSEEK]["standing"]["withheld_by"] == [NO_STANDING_TEST]
    assert report["primaries"][LLAMA]["e5_tests_that_hold"] == []
    assert "own error 20 of 100, (a) not met; distractor" in printed
    assert "silent: not evaluable\n" in printed
    # a factor that counts beside one that a floor withholds: the part holds, nothing withheld
    tests = {(LLAMA, "stale"): STRONG, (LLAMA, "certainty"): STRONG | {"own": (9, 100)}}
    report, _ = patterned(tmp_path, capsys, e2, made_e5(tests))
    llama = report["primaries"][LLAMA]["standing"]
    assert llama["holds"] is True and llama["factors_that_count"] == ["stale"]
    assert llama["withheld_by"] == [] and llama["certainty"]["counts"] is False
    # a floor whose rate has no item is not met, and is named as that: an item set without an
    # item of the two letter factors, and a factor without an item on which its own error can
    # occur (PLAN section 13, "Small points of the reading")
    tests = {
        (LLAMA, "certainty"): STRONG | {"own": (0, 0)},
        (LLAMA, "stale"): STRONG | {"letter": (0, 0)},
        (DEEPSEEK, "silent"): STRONG | {"letter": (0, 0), "own": (0, 0), "unedited": (35, 100)},
    }
    report, printed = patterned(tmp_path, capsys, e2, made_e5(tests))
    llama, deepseek = (
        report["primaries"][LLAMA]["standing"],
        report["primaries"][DEEPSEEK]["standing"],
    )
    no_letter_items = (
        "the error rate on the items of the two letter factors taken together has no item"
    )
    assert llama["certainty"]["c"] == {"floor": 0.1, **counted(0, 0), "met": False}
    assert llama["stale"]["b"]["above_letter"] == counted(0, 0) | {"difference": None, "met": False}
    assert llama["stale"]["b"]["above_seed"]["met"] is True and llama["stale"]["c"]["met"] is True
    assert llama["holds"] is False and llama["withheld_by"] == [
        "(c) on certainty: the factor has no item on which its own error can occur",
        f"(b) on stale: {no_letter_items}",
    ]
    # beside a floor that is missed by its figures: 0.40 against 0.35 on the unedited items
    assert deepseek["withheld_by"] == [
        below_floor("silent", "the unedited seed items"),
        f"(b) on silent: {no_letter_items}",
        "(c) on silent: the factor has no item on which its own error can occur",
    ]
    assert not any("at least 0.10" in text for text in llama["withheld_by"])
    assert "- on the letter-factor items (-), own error 20 of 100, (b) not met" in printed
    assert "own error 0 of 0, (c) not met" in printed


def test_a_secondary_model_has_no_pattern_whatever_its_contrasts_show(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PLAN section 13, "Support, not the rule": the contrasts of the secondary models are
    outside the family of twelve, so no pattern is computed for them, and the sentence is
    stated for none."""
    shows = pair_test(QWEN, "stale", **STRONG) | {"primary": False}
    del shows["floors"], shows["p_holm"], shows["holds"]
    e2, e5 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK)), made_e5(others=[shows])
    report, printed = patterned(tmp_path, capsys, e2, e5)
    assert list(report["primaries"]) == [LLAMA, DEEPSEEK]
    assert QWEN not in json.dumps([report["primaries"], report["sentence"], report["e5"]])
    assert QWEN not in printed
    for model in (LLAMA, DEEPSEEK):
        found = report["primaries"][model]
        assert found["holds"] is False and found["letter"]["holds"] is True
        assert found["standing"]["withheld_by"] == [NO_STANDING_TEST]
        assert found["e5_tests_that_hold"] == []
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "neither primary",
        "stated_for": [],
        "paper": NEITHER,
        "beside": [
            not_held(LLAMA, "standing", NO_STANDING_TEST),
            not_held(DEEPSEEK, "standing", NO_STANDING_TEST),
            NO_SECONDARY,
        ],
    }
    # a primary's own contrast of that size would have counted
    counted_for = made_e5({(LLAMA, "stale"): STRONG}, others=[shows])
    report, _ = patterned(tmp_path, capsys, e2, counted_for)
    assert report["sentence"]["stated_for"] == [LLAMA]


def test_a_primary_declared_not_run_has_no_pattern(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PLAN section 13, "The sentence": a primary whose E2 or E5 run is declared not run has no
    pattern, and the paper says so."""
    cap = "declared on the command line: cap"
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK))
    e5 = made_e5({(LLAMA, "stale"): STRONG}, not_run={DEEPSEEK: cap})
    report, printed = patterned(tmp_path, capsys, e2, e5)
    assert report["primaries"][DEEPSEEK] == {
        "has_pattern": False,
        "declared_not_run": [f"its E5 run, {cap}"],
        "letter": None,
        "standing": None,
        "holds": None,
        "e5_tests_that_hold": [],
    }
    assert report["primaries"][LLAMA]["holds"] is True
    without = f"{DEEPSEEK} has no pattern, and the paper says so: its E5 run, {cap}"
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "one primary",
        "stated_for": [LLAMA],
        "paper": (
            "the pattern holds for one primary and the other has no pattern: the paper states "
            f"the sentence for the first by name ({LLAMA}) and says that the other has none "
            f"({DEEPSEEK})"
        ),
        "beside": [
            without,
            family_result(LLAMA, "stale"),
            criterion_beside(LLAMA),
            own_error_beside(LLAMA, "stale"),
            NO_SECONDARY,
        ],
    }
    assert f"{DEEPSEEK}: no pattern (its E5 run, {cap})\n" in printed
    assert len(printed.splitlines()) == 1 + 2 + 1 + 1 + 5 + 1
    # the E2 run under literal-v1 declared: no pattern, though the E5 tests of the model stand
    # and one of them holds; the other primary misses its standing part
    route = "declared on the command line: no route"
    e2 = made_e2(no_letter(LLAMA), letter_of(DEEPSEEK))
    report, printed = patterned(tmp_path, capsys, e2, made_e5({(LLAMA, "stale"): STRONG}))
    llama = report["primaries"][LLAMA]
    assert llama["has_pattern"] is False and llama["holds"] is None
    assert llama["letter"] is None and llama["standing"] is None
    assert llama["declared_not_run"] == [f"its E2 run under literal-v1, {route}"]
    assert [held["factor"] for held in llama["e5_tests_that_hold"]] == ["stale"]
    assert (
        report["sentence"]["case"] == "neither primary" and report["sentence"]["paper"] == NEITHER
    )
    assert report["sentence"]["beside"] == [
        f"{LLAMA} has no pattern, and the paper says so: its E2 run under literal-v1, {route}",
        not_held(DEEPSEEK, "standing", NO_STANDING_TEST),
        family_result(LLAMA, "stale"),
        NO_SECONDARY,
    ]
    # both runs of one primary, and a run of the other: neither has a pattern
    e2 = made_e2(no_letter(LLAMA), letter_of(DEEPSEEK))
    e5 = made_e5(not_run={LLAMA: cap, DEEPSEEK: cap})
    report, printed = patterned(tmp_path, capsys, e2, e5)
    assert report["primaries"][LLAMA]["declared_not_run"] == [
        f"its E2 run under literal-v1, {route}",
        f"its E5 run, {cap}",
    ]
    assert (
        report["sentence"]["case"] == "neither primary" and report["sentence"]["stated_for"] == []
    )
    assert report["sentence"]["paper"] == (
        "neither primary has a pattern: the paper does not state the sentence"
    )
    assert printed.splitlines()[1:3] == [
        f"{LLAMA}: no pattern (its E2 run under literal-v1, {route}; its E5 run, {cap})",
        f"{DEEPSEEK}: no pattern (its E5 run, {cap})",
    ]


def test_without_e5_the_sentence_is_not_stated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """PLAN section 13, "The sentence": if E5 is not scored by the freeze of numbers, the
    sentence is not stated. That is declared, and no pattern is read."""
    e2 = made_e2(letter_of(LLAMA), no_letter(DEEPSEEK))
    report, printed = patterned(tmp_path, capsys, e2, None)
    route = "declared on the command line: no route"
    assert report["e5"] == {"scored": False}
    assert report["inputs"]["e5"] is None and report["inputs"]["e5_sha256"] is None
    assert report["inputs"]["gold_sha256"] == {"e2": "b" * 64, "e5": None}
    assert report["inputs"]["code_of_the_results"] == {"e2": "c" * 64, "e5": None}
    assert report["primaries"][LLAMA] == {
        "has_pattern": False,
        "declared_not_run": [],
        "letter": None,
        "standing": None,
        "holds": None,
        "e5_tests_that_hold": [],
    }
    assert report["primaries"][DEEPSEEK]["declared_not_run"] == [
        f"its E2 run under literal-v1, {route}"
    ]
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "E5 is not scored",
        "stated_for": [],
        "paper": "E5 is not scored by the freeze of numbers: the sentence is not stated",
        "beside": [
            f"{DEEPSEEK} has no pattern, and the paper says so: its E2 run under literal-v1, {route}",
            NO_SECONDARY,
        ],
    }
    assert printed.splitlines()[:-1] == [
        "pattern of PLAN section 13: E2 on 120 gold items; E5 not scored",
        f"{LLAMA}: no pattern (E5 is not scored)",
        f"{DEEPSEEK}: no pattern (its E2 run under literal-v1, {route})",
        "sentence: E5 is not scored by the freeze of numbers: the sentence is not stated",
        *(f"beside it: {text}" for text in report["sentence"]["beside"]),
    ]


def test_the_sentence_of_a_pattern_is_written_in_the_words_of_the_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every phrase of ``PLAN_WORDS``, which stands in the plan, is in the sentence of the case
    it belongs to."""
    plan = flat_text(PLAN.read_text(encoding="utf-8"))
    assert all(flat_text(words) in plan for words in PLAN_WORDS)
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK))
    cut = {"cut": True, "first_seeds": 50, "seeds_on_the_list": 100, "first_seeds_with_items": 50}
    cases = [
        (e2, made_e5({(LLAMA, "stale"): STRONG, (DEEPSEEK, "stale"): STRONG}, cut=cut)),
        (e2, made_e5({(LLAMA, "stale"): STRONG, (DEEPSEEK, "stale"): STRONG | {"own": (1, 100)}})),
        (e2, made_e5()),
        (e2, made_e5(not_run={DEEPSEEK: "declared on the command line: cap"})),
        (e2, made_e5({(LLAMA, "stale"): STRONG}, not_run={DEEPSEEK: "declared: cap"})),
        (e2, None),
    ]
    written = []
    for first, second in cases:
        report, printed = patterned(tmp_path, capsys, first, second)
        written.append(" ".join([report["sentence"]["paper"], *report["sentence"]["beside"]]))
        assert all(text in printed for text in report["sentence"]["beside"])
    for words in PLAN_WORDS:
        assert any(words in text for text in written), words
    # a cut E5 is named beside the sentence, with its items
    assert (
        "E5 is cut to 800 items (section 12, cut 4): the pattern is read on those items with "
        "the same floors"
    ) in written[0]
    assert "E5 is cut" not in written[1]
    report, printed = patterned(tmp_path, capsys, *cases[0])
    assert report["e5"]["item_set"]["cut"] is True
    assert "E5 on 800 items of 100 seeds, cut to the first 50 of the seed list (the GEE" in printed


def test_pattern_refuses_what_is_not_two_results_of_this_scorer_on_one_item_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    e2, e5 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK)), made_e5({(LLAMA, "stale"): STRONG})

    def why(first: Any = e2, second: Any = e5, *extra: str) -> str:
        return pattern_refused(tmp_path, capsys, first, second, *extra)

    def altered(result: dict[str, Any], change: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
        copy = json.loads(json.dumps(result))
        change(copy)
        return copy

    # the two results, and the declaration that there is no second
    assert why(None, e5) == "refused: --e2 names the result file of e2"
    one_of_two = (
        "refused: --e5 names the result file of e5, or --e5-not-scored declares that E5 is not "
        "scored by the freeze of numbers: one of the two, and not both"
    )
    assert why(e2, e5, "--e5-not-scored") == one_of_two
    folder = tmp_path / "bare"
    folder.mkdir()
    (folder / "e2.json").write_text(json.dumps(e2))
    with pytest.raises(SystemExit) as stop:
        LS.main(["pattern", "--e2", str(folder / "e2.json"), "--out", str(folder / "out.json")])
    assert stop.value.code == one_of_two and not (folder / "out.json").exists()
    # a file that is not there, is not JSON, is no object, or is another result
    absent = why(tmp_path / "absent.json", e5)
    assert absent.startswith("refused: the result file of e2 cannot be read (FileNotFoundError)")
    not_e2 = "refused: --e2: the file is not the result file of e2 as this scorer writes it"
    not_e5 = "refused: --e5: the file is not the result file of e5 as this scorer writes it"
    text = tmp_path / "text.json"
    text.write_text("{ not JSON")
    assert why(text, e5) == not_e2 and why(e2, text) == not_e5
    text.write_bytes(b"\xff\xfe\x00")
    assert why(text, e5) == not_e2
    assert why([e2], e5) == not_e2 and why(e2, [1, 2]) == not_e5
    assert why(e5, e5) == not_e2 and why(e2, e2) == not_e5
    assert why(altered(e2, lambda r: r.pop("about")), e5) == not_e2
    assert why(e2, altered(e5, lambda r: r.update(about=LS.ABOUT_PATTERN))) == not_e5
    # a result under another registered record: a margin, a floor, the factors, the seed, or a
    # result from before the pattern was registered
    other_e2 = (
        "refused: --e2: the result file of e2 was written under another registered record than "
        "this scorer's (another constant, primary, line or template pin)"
    )
    other_e5 = other_e2.replace("e2", "e5")
    assert why(
        altered(e2, lambda r: r["registered"]["pattern"].update(letter_margin=0.15)), e5
    ) == (other_e2)
    for name in ("standing_floor", "own_error_floor"):
        moved = altered(e5, lambda r, name=name: r["registered"]["pattern"].update({name: 0.05}))
        assert why(e2, moved) == other_e5, name
    moved = altered(e5, lambda r: r["registered"]["pattern"]["standing_factors"].remove("silent"))
    assert why(e2, moved) == other_e5
    assert why(e2, altered(e5, lambda r: r["registered"]["e5"].update(cut_seeds=40))) == other_e5
    assert why(altered(e2, lambda r: r["registered"].update(seed=1)), e5) == other_e2
    assert why(altered(e2, lambda r: r["registered"].pop("pattern")), e5) == other_e2
    assert why(e2, altered(e5, lambda r: r.pop("registered"))) == other_e5
    # the same two files under a scorer with another margin
    monkeypatch.setattr(LS, "LETTER_MARGIN", 0.15)
    assert why() == other_e2
    monkeypatch.setattr(LS, "LETTER_MARGIN", 0.10)
    # two results of different plans of the runs
    apart = "refused: the two results are of different plans of the runs"
    assert why(e2, made_e5(plan="e" * 64)) == apart
    assert why(made_e2(letter_of(LLAMA), letter_of(DEEPSEEK), plan="e" * 64), e5) == apart
    # the two primaries on different items, in either result
    literal = "refused: the E2 result does not score the two primaries on one set of gold items"
    pairs = (
        "refused: the E5 result does not score the two primaries on the item set it records: the "
        "pattern is read on one item set, whole or cut"
    )
    rows = f"{DEEPSEEK} {V1}"
    assert why(altered(e2, lambda r: r["per_item"]["readers"][rows].pop()), e5) == literal
    assert why(
        altered(e2, lambda r: r["per_item"]["readers"][rows][0].__setitem__(0, "L999")), e5
    ) == (literal)
    assert why(altered(e2, lambda r: r["per_item"].update(item_set="without_gap")), e5) == literal
    assert why(altered(e2, lambda r: r["item_sets"]["all"].update(items=119)), e5) == literal

    def first_twice(result: dict[str, Any]) -> None:
        """Each primary's rows with the first item twice, in the place of the second: as many
        rows as gold items, the same for both primaries, and one item short."""
        for rows in result["per_item"]["readers"].values():
            rows[1] = list(rows[0])

    doubled = altered(e2, first_twice)
    assert all(len(rows) == 120 for rows in doubled["per_item"]["readers"].values())
    assert why(doubled, e5) == literal
    for model in (LLAMA, DEEPSEEK):
        fewer = altered(e5, lambda r, model=model: r["per_item"]["readers"][model].pop())
        assert why(e2, fewer) == pairs, model
    other = altered(e5, lambda r: r["per_item"]["readers"][LLAMA][0].__setitem__(0, "P9999"))
    assert why(e2, other) == pairs
    # one primary on the whole item set and the result recording the cut, or the other way
    half = lp.ids_sha256(f"P{k:04d}" for k in range(400))
    assert why(
        e2, altered(e5, lambda r: r["item_set"].update(items=400, item_ids_sha256=half))
    ) == (pairs)
    assert why(e2, altered(e5, lambda r: r["item_set"].update(item_ids_sha256=half))) == pairs
    assert why(e2, altered(e5, lambda r: r.update(items=799))) == pairs
    # a cut that the result does not describe is no result to print: nothing is written
    undescribed = altered(e5, lambda r: r["item_set"].update(cut=True))
    assert why(e2, undescribed) == (
        "refused: the two results cannot be read as this scorer writes them (KeyError)"
    )
    # a result that lacks what the pattern reads, named by the type of the error alone
    unreadable = "refused: the two results cannot be read as this scorer writes them "
    assert why(altered(e2, lambda r: r["item_sets"].pop("all")), e5) == unreadable + "(KeyError)"
    assert why(e2, altered(e5, lambda r: r["tests"].pop())) == unreadable + "(KeyError)"
    assert why(e2, altered(e5, lambda r: r["tests"][3].pop("floors"))) == unreadable + "(KeyError)"
    assert (
        why(e2, altered(e5, lambda r: r["tests"][0].update(model=QWEN)))
        == unreadable + "(KeyError)"
    )
    assert why(e2, altered(e5, lambda r: r.update(tests=5))) == unreadable + "(TypeError)"
    assert why(altered(e2, lambda r: r["item_sets"]["all"].update(letter_reading=[])), e5) == (
        unreadable + "(KeyError)"
    )
    # a figure that cannot be printed: a whole number too large for a float, where a letter
    # accuracy or an error rate stands. One sentence, and no traceback
    huge = 10**400
    too_large = altered(e2, lambda r: r["item_sets"]["all"]["letter_reading"][0].update(first=huge))
    assert why(too_large, e5) == unreadable + "(OverflowError)"
    too_large = altered(e5, lambda r: r["tests"][0]["edited"].update(rate=huge))
    assert why(e2, too_large) == unreadable + "(OverflowError)"
    too_large = altered(e5, lambda r: r["tests"][3]["above_letter_items"].update(rate=huge))
    assert why(e2, too_large) == unreadable + "(OverflowError)"
    # a file nested deeper than the parser reads is no result of this scorer
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200_000 + "]" * 200_000)
    assert why(deep, e5) == not_e2 and why(e2, deep) == not_e5
    deep.write_text('{"about": ' + "[" * 200_000 + "]" * 200_000 + "}")
    assert why(deep, e5) == not_e2 and why(e2, deep) == not_e5
    # the output: named, new, and in a folder that is there
    assert why(e2, e5, "--out", str(tmp_path / "none" / "out.json")).startswith(
        "refused: the folder of the output does not exist"
    )
    there = tmp_path / "there.json"
    there.write_text("kept")
    assert why(e2, e5, "--out", str(there)) == (
        f"refused: the output is already there, and nothing is overwritten: {there.as_posix()}"
    )
    assert there.read_text() == "kept"
    folder = tmp_path / "no_out"
    folder.mkdir()
    argv = pattern_argv(folder, e2, e5, folder / "unused.json")
    with pytest.raises(SystemExit) as stop:
        LS.main([arg for arg in argv if arg not in ("--out", str(folder / "unused.json"))])
    assert (
        stop.value.code == "refused: --out is required: the file to write, which must not exist yet"
    )
    # no refusal quotes an item id
    assert "L000" not in literal and "P0000" not in pairs


def test_pattern_refuses_a_result_named_in_a_sealed_folder_unopened(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    vault = tmp_path / "sealed"
    vault.mkdir()
    (vault / "file").write_bytes(b"sealed\n")
    link = tmp_path / "link.json"
    link.symlink_to(vault / "file")
    folder = tmp_path / "open"
    folder.mkdir()
    e2, e5 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK)), made_e5()
    for name in ("e2", "e5"):
        for target in (vault / "file", vault / "absent", link):
            results = {"e2": e2, "e5": e5} | {name: target}
            argv = pattern_argv(folder, results["e2"], results["e5"], folder / "out.json")
            capsys.readouterr()
            with watching() as touched, pytest.raises(SystemExit) as stop:
                LS.main(argv)
            assert stop.value.code == (
                f"refused: --{name} lies in a sealed folder; no sealed file is read"
            ), (name, target)
            assert touched == [] and not (folder / "out.json").exists()
    with pytest.raises(SystemExit) as stop:
        LS.main(pattern_argv(folder, e2, e5, vault / "out.json"))
    assert (
        stop.value.code == "refused: --out lies in a sealed folder; results are written outside it"
    )
    assert [path.name for path in vault.iterdir()] == ["file"]
    assert (vault / "file").read_bytes() == b"sealed\n"


def test_pattern_run_as_a_process(tmp_path: Path) -> None:
    """Status 0 and the summary on a pair of results; status 1 and the reason alone when the
    output is there already."""
    e2 = made_e2(letter_of(LLAMA), letter_of(DEEPSEEK))
    out = tmp_path / "pattern.json"
    argv = pattern_argv(tmp_path, e2, made_e5({(LLAMA, "stale"): STRONG}), out)
    root = Path(LS.__file__).resolve().parents[2]
    env = {name: value for name, value in os.environ.items() if not name.endswith("_API_KEY")}

    def run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "analysis.coling.literal_scores", *argv],
            cwd=root,
            env=env | {"PYTHONPATH": str(root)},
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

    done = run()
    assert done.returncode == 0 and done.stderr == ""
    assert done.stdout.startswith("pattern of PLAN section 13: E2 on 120 gold items; E5 on 800")
    assert f"\nsentence: {one_named(LLAMA, DEEPSEEK, 'standing')}\n" in done.stdout
    written = out.read_text()
    assert json.loads(written)["sentence"]["stated_for"] == [LLAMA]
    again = run()
    assert again.returncode == 1 and again.stdout == ""
    assert again.stderr == (
        f"refused: the output is already there, and nothing is overwritten: {out.as_posix()}\n"
    )
    assert out.read_text() == written


# --------------------------------------------------------------------------------------------
# The pattern end to end on the made-up study
# --------------------------------------------------------------------------------------------


def pattern_of_files(folder: Path, e2_text: str, e5_text: str) -> SimpleNamespace:
    """``pattern`` on the texts of two result files: its result and its printout."""
    (folder / "e2.json").write_text(e2_text)
    (folder / "e5.json").write_text(e5_text)
    out, printed = folder / "pattern.json", io.StringIO()
    with redirect_stdout(printed):
        assert LS.main(pattern_argv(folder, folder / "e2.json", folder / "e5.json", out)) == 0
    return SimpleNamespace(
        report=json.loads(out.read_text()), text=out.read_text(), printed=printed.getvalue()
    )


@pytest.fixture(scope="module")
def pattern(
    e2: SimpleNamespace, e5: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> SimpleNamespace:
    """The pattern of the two results of the untouched study."""
    return pattern_of_files(tmp_path_factory.mktemp("pattern"), e2.text, e5.text)


def pair_floors(model: str, factor: str, seeds: Sequence[int]) -> dict[str, Any]:
    """What the scripted readings of the minimal pairs give for one standing factor over some
    seeds, counted here: the errors on the items of the factor, on the unedited items and on
    the letter-factor items under the criterion of the factor, the own error, and the floors
    in tenths of whole numbers."""
    n = len(seeds)
    errors = sum(pair_errs(model, s, factor) for s in seeds)
    unedited = sum(seed_errs(model, s, factor) for s in seeds)
    letter = 0
    for s in seeds:
        for name, off in (("surface_form", s % 2 == 1), ("granularity", s % 3 == 0)):
            counts = {"surface_form": "certainty", "granularity": "stale"}[name] == factor
            letter += pair_errs(model, s, name) or (off and counts)
    # the scripted error of a stale or a distractor item is the factor's own; the certainty
    # items are dated, and an erring silent item abstains under another type
    own = (errors if factor in ("stale", "distractor") else 0, 0 if factor == "certainty" else n)
    met = {
        "above_seed": 10 * (errors - unedited) >= n,
        "above_letter": 10 * (2 * errors - letter) >= 2 * n,
        "own_error": bool(own[1]) and 10 * own[0] >= own[1],
    }
    return {
        "edited": errors,
        "unedited": unedited,
        "letter": letter,
        "own": own,
        "floors": met | {"met": all(met.values())},
    }


def check_pattern_against_the_script(
    found: Mapping[str, Any], tests: Sequence[Mapping[str, Any]], model: str, seeds: Sequence[int]
) -> list[str]:
    """One primary's pattern against the scripted readings over ``seeds`` and against its
    tests of the twelve; gives the standing factors that count."""
    n = len(seeds)
    mine = {t["factor"]: t for t in tests if t["model"] == model}
    for factor in LS.LETTER_FACTORS:
        errors = sum(pair_errs(model, s, factor) for s in seeds)
        unedited = sum(seed_errs(model, s, factor) for s in seeds)
        shown = found["letter"]["e5"][factor]
        assert shown["edited"] == counted(errors, n) | {"rate": near(errors / n)}
        assert shown["unedited"] == counted(unedited, n) | {"rate": near(unedited / n)}
        assert shown["holds"] is mine[factor]["holds"] and shown["p_holm"] == mine[factor]["p_holm"]
        assert shown["higher_on_edited"] is (errors > unedited)
        assert shown["withholds"] is (shown["holds"] and errors > unedited)
    counting = []
    for factor in LS.STANDING_FACTORS:
        want, one = pair_floors(model, factor, seeds), found["standing"][factor]
        test = mine[factor]
        assert one["a"]["edited"]["errors"] == want["edited"] and one["a"]["edited"]["items"] == n
        assert one["a"]["unedited"]["errors"] == want["unedited"]
        assert one["a"]["holds"] is test["holds"] and one["a"]["p_from"] == test["p_from"]
        assert one["a"]["higher_on_edited"] is (want["edited"] > want["unedited"])
        assert one["a"]["met"] is (test["holds"] and want["edited"] > want["unedited"])
        assert one["b"]["floor"] == 0.1 and one["c"]["floor"] == 0.1
        assert one["b"]["above_seed"] == {
            "difference": near((want["edited"] - want["unedited"]) / n),
            "met": want["floors"]["above_seed"],
        }
        assert one["b"]["above_letter"] == {
            "items": 2 * n,
            "errors": want["letter"],
            "rate": near(want["letter"] / (2 * n)),
            "difference": near(want["edited"] / n - want["letter"] / (2 * n)),
            "met": want["floors"]["above_letter"],
        }
        assert one["b"]["met"] is (want["floors"]["above_seed"] and want["floors"]["above_letter"])
        errors, items = want["own"]
        assert one["c"] == {
            "floor": 0.1,
            "items": items,
            "errors": errors,
            "rate": near(errors / items) if items else None,
            "met": want["floors"]["own_error"],
        }
        assert one["errors_of_another_kind"] == test["errors_of_another_kind"]
        assert one["counts"] is (one["a"]["met"] and want["floors"]["met"])
        counting += [factor] if one["counts"] else []
    assert found["standing"]["factors_that_count"] == counting
    assert found["standing"]["holds"] is bool(counting)
    return counting


def test_pattern_end_to_end_on_the_made_up_study(
    study: SimpleNamespace, e2: SimpleNamespace, e5: SimpleNamespace, pattern: SimpleNamespace
) -> None:
    """The two result files of the made-up study, read by the pattern. Llama reads the letter
    (13 of 14 letter items against 8 for the rule reader) and no test of a standing factor
    holds for it. Deepseek reads the letter (14 of 14) and errs on 11 of its 12 distractor
    items, each time by taking the expiry date, against 1 of 12 unedited items and 5 of 24
    letter-factor items: its test holds, and the factor counts."""
    report = pattern.report
    assert report["about"] == LS.ABOUT_PATTERN and pattern.text == LS.report_text(report)
    assert report["registered"] == e2.report["registered"] == e5.report["registered"]
    assert report["e2"] == {"item_set": "all", "items": 23}
    assert report["e5"] == {
        "scored": True,
        "item_set": {
            "cut": False,
            "items_in_the_item_file": 84,
            "items": 84,
            "item_ids_sha256": lp.ids_sha256(i.item_id for i in study.pairs),
        },
        "items": 84,
        "seeds": 12,
        "method_in_force": "the GEE with its robust variance",
    }
    assert e5.report["item_set"] == report["e5"]["item_set"]
    inputs = report["inputs"]
    assert inputs["plan_sha256"] == sha(lp.plan_path(study.runs))
    assert inputs["gold_sha256"] == {"e2": sha(study.gold), "e5": sha(study.e5_gold)}
    assert inputs["code_of_the_results"] == dict.fromkeys(("e2", "e5"), sha(Path(LS.__file__)))
    assert inputs["e2_sha256"] == hashlib.sha256(e2.text.encode()).hexdigest()
    assert inputs["e5_sha256"] == hashlib.sha256(e5.text.encode()).hexdigest()
    readings = e2.report["item_sets"]["all"]["letter_reading"]
    described = ("model", "template", "against", "evaluable")
    whole = range(PAIR_SEEDS)
    counting = {}
    for entry, model in zip(readings, (LLAMA, DEEPSEEK), strict=True):
        found = report["primaries"][model]
        assert found["has_pattern"] is True and found["declared_not_run"] == []
        assert found["letter"]["e2"] == {k: v for k, v in entry.items() if k not in described} | {
            "met": True
        }
        assert found["letter"]["e5"]["met"] is True and found["letter"]["holds"] is True
        assert found["letter"]["withheld_by"] == []
        counting[model] = check_pattern_against_the_script(found, e5.report["tests"], model, whole)
        assert found["holds"] is bool(counting[model])
    assert counting == {LLAMA: [], DEEPSEEK: ["distractor"]}
    llama, deepseek = report["primaries"][LLAMA], report["primaries"][DEEPSEEK]
    assert llama["letter"]["e2"]["first"] == near(13 / 14)
    assert llama["letter"]["e2"]["second"] == near(8 / 14) and llama["letter"]["e2"]["items"] == 14
    assert (
        llama["standing"]["withheld_by"] == [NO_STANDING_TEST] and llama["e5_tests_that_hold"] == []
    )
    # llama's floors are met on two factors whose tests do not hold: they do not count
    assert [f for f in LS.STANDING_FACTORS if llama["standing"][f]["b"]["met"]] == [
        "stale",
        "distractor",
    ]
    assert deepseek["letter"]["e2"]["first"] == 1.0
    distractor = deepseek["standing"]["distractor"]
    assert distractor["a"]["edited"] == counted(11, 12) | {"rate": near(11 / 12)}
    assert distractor["a"]["unedited"] == counted(1, 12) | {"rate": near(1 / 12)}
    assert distractor["a"]["holds"] is True and distractor["a"]["p_holm"] < 0.05
    assert distractor["b"]["above_letter"]["errors"] == 5
    assert distractor["b"]["above_letter"]["difference"] == near(17 / 24)
    assert distractor["c"] == {"floor": 0.1, **counted(11, 12), "rate": near(11 / 12), "met": True}
    assert distractor["errors_of_another_kind"] == {"errors": 0, "share": 0.0}
    assert deepseek["standing"]["withheld_by"] == []
    (held,) = deepseek["e5_tests_that_hold"]
    test = e5.report["tests"][6 + MP.FACTORS.index("distractor")]
    assert held == {
        "factor": "distractor",
        "kind": "standing",
        "higher_error_rate_on": "the edited items",
        "edited": test["edited"],
        "unedited": test["unedited"],
        "difference": test["difference"],
        "log_odds_difference": test["log_odds_difference"],
        "p_holm": test["p_holm"],
        "p_from": "gee",
    }
    assert report["sentence"] == {
        "sentence": LS.SENTENCE,
        "case": "one primary",
        "stated_for": [DEEPSEEK],
        "paper": one_named(DEEPSEEK, LLAMA, "standing"),
        "beside": [
            not_held(LLAMA, "standing", NO_STANDING_TEST),
            family_result(DEEPSEEK, "distractor"),
            criterion_beside(DEEPSEEK),
            own_error_beside(DEEPSEEK, "distractor"),
            NO_SECONDARY,
        ],
    }
    lines = pattern.printed.splitlines()
    assert len(lines) == 1 + 4 + 1 + 5 + 1
    assert lines[0] == (
        "pattern of PLAN section 13: E2 on 23 gold items; E5 on 84 items of 12 seeds (the GEE "
        "with its robust variance)"
    )
    assert lines[1].startswith(
        f"{LLAMA} letter: holds; (a) letter accuracy 0.929 against 0.571 of the rule reader on "
        "14 letter items, difference +0.357, 90% interval "
    )
    assert lines[2].startswith(f"{LLAMA} standing: does not hold; certainty: 0.500 against 0.333")
    assert lines[4].startswith(f"{DEEPSEEK} standing: holds by distractor; certainty: ")
    assert (
        "distractor: 0.917 against 0.083 unedited (+0.833), Holm 0.0079, holds with the higher "
        "rate on the edited items, 0.208 on the letter-factor items (+0.708), own error 11 of "
        "12, counts; silent: "
    ) in lines[4]
    assert lines[5] == f"sentence: {one_named(DEEPSEEK, LLAMA, 'standing')}"
    # nothing of an item reaches the pattern: no wording, no reading, and no item id
    for text in (pattern.text, pattern.printed):
        no_text_in(study, text)
        assert not any(item in text for item in study.items)
        assert not any(item.item_id in text for item in study.pairs)
    assert "per_item" not in report and "other_models" not in pattern.text
    assert not any(model in json.dumps(report["primaries"]) for model in (QWEN, GEMMA, GROK))


def test_pattern_end_to_end_when_a_primary_reads_the_letter_worse_than_the_rules(
    study: SimpleNamespace,
    e5: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Condition (a) through both commands. Llama's stored readings are given a wrong statement
    type on seven letter items that the rule reader has right: it is then right on 6 of the 14
    letter items against 8, the lower end of the 90% interval of the difference lies below
    -0.10, and the pattern does not hold for it."""
    numbers = {item: n for n, item in study.ids.items()}
    spoiled = (1, 2, 3, 4, 6, 9, 20)

    def worse(row: dict) -> dict:
        if numbers[row["item_id"]] not in spoiled:
            return row
        row = json.loads(json.dumps(row))
        row["reading"]["statement_type"] = "discontinuation"
        return row

    with rewritten(study, run_of("e2-literal", LLAMA), worse):
        report, _ = scored("e2", study, tmp_path, capsys)
    entry = report["item_sets"]["all"]["letter_reading"][0]
    assert entry["model"] == LLAMA and entry["items"] == 14
    assert entry["first"] == near(6 / 14) and entry["second"] == near(8 / 14)
    assert entry["difference"] == near(-2 / 14)
    # the interval of the difference, from the registered draws of episodes
    episodes = sorted({EPISODES.get(n, n) for n in GOLD})
    drawn = P.cluster_draws(len(episodes), 10_000, 20261001).astype(float)
    members = {k: [n for n in GOLD if EPISODES.get(n, n) == e] for k, e in enumerate(episodes)}
    wrong = {*spoiled, 5}  # the scripted reading of item 5 has the type wrong already
    rules_wrong = set(RULES_WRONG) & set(LETTER)
    gain = np.array(
        [
            sum((n in rules_wrong) - (n in wrong) for n in members[k] if n in LETTER)
            for k in members
        ],
        dtype=float,
    )
    size = np.array([sum(n in LETTER for n in members[k]) for k in members], dtype=float)
    low, high = np.quantile((drawn @ gain) / (drawn @ size), [0.05, 0.95])
    assert entry["ci90"] == {"low": near(low), "high": near(high), "draws": 10_000}
    assert low < -0.1 < high and entry["lower_end_above_minus_margin"] is False
    assert report["item_sets"]["all"]["letter_reading"][1]["lower_end_above_minus_margin"] is True
    found = pattern_of_files(
        tmp_path, (tmp_path / "results" / "scores_0.json").read_text(), e5.text
    )
    llama = found.report["primaries"][LLAMA]
    assert llama["letter"]["e2"]["met"] is False and llama["letter"]["e5"]["met"] is True
    assert llama["letter"]["withheld_by"] == [LOWER_END] and llama["holds"] is False
    assert found.report["sentence"]["stated_for"] == [DEEPSEEK]
    assert found.report["sentence"]["paper"] == one_named(DEEPSEEK, LLAMA, "letter", "standing")
    assert (
        f"{LLAMA} letter: does not hold; (a) letter accuracy 0.429 against 0.571" in found.printed
    )
    assert "lower end not above -0.10" in found.printed


# --------------------------------------------------------------------------------------------
# E5 cut to the first seeds of the seed list (PLAN section 12, cut 4)
# --------------------------------------------------------------------------------------------

CUT_SEEDS = 6
"""How many seeds the cut keeps in these tests, in the place of the registered 50."""
CUT_RANK = {s: 10 * ((7 * s + 3) % PAIR_SEEDS + 1) for s in range(PAIR_SEEDS)}
"""The draw rank of each of the twelve seeds: 10 to 120. In the order of the draw the seeds are
3, 10, 5, 0, 7, 2, 9, 4, 11, 6, 1 and 8; read as text, rank 100 would come before rank 20."""
NO_ITEM = "S99"
"""A seed of the list that gave no item, third in the order of the draw."""
CUT_KEPT = (3, 10, 5, 0, 7)
"""The seeds of the first six of the list that have items."""


def seed_list(ranks: Mapping[str, Any]) -> str:
    """A seed list as the sampler writes one, in the order of the seed ids."""
    rows = [
        {
            "event_id": f"E{seed[1:]}",
            "statement_group_id": seed,
            "thread_id": f"T{seed[1:]}",
            "draw_rank": rank,
            "period": "fit",
        }
        for seed, rank in sorted(ranks.items())
    ]
    return MP.plain_csv(S.LATER_COLUMNS, rows)


def listed_ranks() -> dict[str, Any]:
    return {f"S{s:02d}": rank for s, rank in CUT_RANK.items()} | {NO_ITEM: 25}


def cut_lines(study: SimpleNamespace, seeds: Sequence[int]) -> list[str]:
    """The lines of the item file of the minimal pairs for some seeds."""
    kept = {f"S{s:02d}" for s in seeds}
    lines = study.e5_items.read_text().splitlines(keepends=True)
    return [line for line in lines if json.loads(line)["seed_id"] in kept]


def build_cut(study: SimpleNamespace, root: Path) -> SimpleNamespace:
    """The made-up study with its minimal pairs cut before any call: the seed list, the cut
    item file (the lines of the kept seeds, last line first), a plan whose list of minimal
    pairs is that file, and the runs of E2 and of E5 under that plan."""
    runs, local = root / "read", root / "local"
    for folder in (runs, local):
        folder.mkdir()
    seeds, items = root / "sample_pair_seeds.csv", root / "e5_cut.jsonl"
    seeds.write_text(seed_list(listed_ranks()), encoding="utf-8")
    items.write_text("".join(reversed(cut_lines(study, CUT_KEPT))))
    options = lp.default_options(study.root / "items")
    options |= {"out_root": str(runs), "local_root": str(local)}
    options["items_files"] = {"e5": str(items)}
    options["counts"] = dict.fromkeys(("e3", "tbd", "silent", "stale", "dev"), 50)
    plan = lp.make_plan(options)
    lp.plan_path(runs).parent.mkdir(parents=True, exist_ok=True)
    lp.plan_path(runs).write_text(lp.plan_text(plan), encoding="utf-8")
    for run in plan["runs"]:
        if run["list"] in ("e2", "e5"):
            make_run(plan, run, reply_for(run["model"], run["template"]), local)
    ids = [study.pair_ids[s, factor] for s in CUT_KEPT for factor in PAIR_FACTORS]
    return SimpleNamespace(root=root, runs=runs, seeds=seeds, items=items, ids=ids)


@pytest.fixture(scope="module")
def cut(
    study: SimpleNamespace, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[SimpleNamespace]:
    patch = pytest.MonkeyPatch()
    guard(patch, tmp_path_factory.mktemp("nowhere"))
    try:
        yield build_cut(study, tmp_path_factory.mktemp("cut"))
    finally:
        patch.undo()


def cut_args(
    study: SimpleNamespace, cut: SimpleNamespace, out: Path, *extra: str, **replace: Any
) -> list[str]:
    """The arguments of ``e5`` for the cut; the hash of the seed list is its own unless one is
    given."""
    options = {
        "--gold": study.e5_gold,
        "--items": study.e5_items,
        "--out-root": cut.runs,
        "--out": out,
        "--cut-seed-list": cut.seeds,
        "--cut-items": cut.items,
    }
    if "expect_seed_list_sha256" not in replace:
        named = Path(replace.get("cut_seed_list") or cut.seeds)
        options["--expect-seed-list-sha256"] = sha(named) if named.is_file() else "0" * 64
    return [*listed("e5", options, study.e5_gold, replace), *extra]


def cut_scored(
    study: SimpleNamespace,
    cut: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    **replace: Any,
) -> tuple[dict[str, Any], str, Path]:
    out = fresh(tmp_path)
    capsys.readouterr()
    assert LS.main(cut_args(study, cut, out, **replace)) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    return json.loads(out.read_text()), printed.out, out


def cut_refused(
    study: SimpleNamespace,
    cut: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    **replace: Any,
) -> str:
    out = fresh(tmp_path, "refused")
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        LS.main(cut_args(study, cut, out, **replace))
    assert isinstance(stop.value.code, str) and stop.value.code.startswith("refused: ")
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == "" and list(out.parent.iterdir()) == []
    return stop.value.code


def test_e5_cut_to_the_first_seeds_of_the_seed_list_in_its_draw_order(
    study: SimpleNamespace,
    cut: SimpleNamespace,
    e5: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAN section 12, cut 4: the unedited seed item and every edit of the first seeds of the
    seed list in its draw order. Here the cut keeps six seeds of thirteen; one of the six gave
    no item, so 35 items of five seeds are scored, on the runs that read the cut item file."""
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", CUT_SEEDS)
    order = sorted(listed_ranks(), key=lambda seed: listed_ranks()[seed])
    assert order[:CUT_SEEDS] == ["S03", "S10", NO_ITEM, "S05", "S00", "S07"]
    assert (
        sorted(listed_ranks(), key=lambda seed: str(listed_ranks()[seed]))[:CUT_SEEDS]
        != (order[:CUT_SEEDS])
    )
    report, printed, _ = cut_scored(study, cut, tmp_path, capsys)
    assert report["item_set"] == {
        "cut": True,
        "first_seeds": 6,
        "seeds_on_the_list": 13,
        "first_seeds_with_items": 5,
        "items_in_the_item_file": 84,
        "items": 35,
        "item_ids_sha256": lp.ids_sha256(cut.ids),
    }
    assert report["registered"]["e5"]["cut_seeds"] == 6
    inputs = report["inputs"]
    assert inputs["items"] == study.e5_items.as_posix() == e5.report["inputs"]["items"]
    assert inputs["items_sha256"] == sha(study.e5_items)
    assert inputs["item_ids_sha256"] == e5.report["inputs"]["item_ids_sha256"]
    assert inputs["gold_sha256"] == sha(study.e5_gold)
    assert inputs["seed_list"] == cut.seeds.as_posix() and inputs["seed_list_sha256"] == sha(
        cut.seeds
    )
    assert inputs["cut_items"] == cut.items.as_posix() and inputs["cut_items_sha256"] == sha(
        cut.items
    )
    assert (
        inputs["plan_sha256"] == sha(lp.plan_path(cut.runs)) != e5.report["inputs"]["plan_sha256"]
    )
    assert list(inputs)[:9] == [
        "gold",
        "gold_sha256",
        "items",
        "items_sha256",
        "item_ids_sha256",
        "seed_list",
        "seed_list_sha256",
        "cut_items",
        "cut_items_sha256",
    ]
    assert report["items"] == 35 and report["seeds"] == 5
    assert report["items_by_factor"] == dict.fromkeys(PAIR_FACTORS, 5)
    assert report["items_of_test_period_seeds"] == 7  # seed 10 is dated 2023 or later
    assert all(found["rows"] == 35 for found in report["runs"].values())
    for model, rows in report["per_item"]["readers"].items():
        assert sorted(row[0] for row in rows) == sorted(cut.ids), model
    # the errors are those of the scripted readings on the five seeds, and on no other
    for model in ERRS:
        table = report["errors"][model]["by_factor"]
        for factor in PAIR_FACTORS:
            errors = sum(pair_errs(model, s, factor) for s in CUT_KEPT)
            assert table[factor]["items"] == 5, (model, factor)
            assert table[factor]["errors"] == errors, (model, factor)
    assert all(v["errors"] == 0 for v in report["rule_reader"]["by_factor"].values())
    assert all(v["items"] == 5 for v in report["rule_reader"]["by_factor"].values())
    for test in report["tests"]:
        if not test["evaluable"] or test["factor"] in LS.LETTER_FACTORS:
            continue
        want = pair_floors(test["model"], test["factor"], CUT_KEPT)
        assert test["edited"]["errors"] == want["edited"] and test["edited"]["items"] == 5
        assert test["unedited"]["errors"] == want["unedited"]
        assert test["above_letter_items"]["errors"] == want["letter"]
        assert test["above_letter_items"]["items"] == 10
        assert (test["own_error"]["errors"], test["own_error"]["items"]) == want["own"]
        assert test["floors"] == want["floors"], (test["model"], test["factor"])
    assert sum(t["evaluable"] for t in report["tests"]) == 12
    assert printed.startswith("E5: 35 items of 5 seeds, cut to the first 6 of the seed list; ")
    # the whole item set says that it is whole
    assert e5.report["item_set"] == {
        "cut": False,
        "items_in_the_item_file": 84,
        "items": 84,
        "item_ids_sha256": e5.report["inputs"]["item_ids_sha256"],
    }
    assert e5.text.startswith('{\n "about"') and ", cut to the first" not in e5.text
    assert not any(name.startswith(("seed_list", "cut_items")) for name in e5.report["inputs"])
    # the seed list in another order of its rows, and the cut item file in the order of the
    # item file, give the same result under other hashes
    again = tmp_path / "again"
    again.mkdir()
    rows = seed_list(listed_ranks()).splitlines(keepends=True)
    (again / "seeds.csv").write_text(rows[0] + "".join(reversed(rows[1:])))
    (again / "cut.jsonl").write_text("".join(cut_lines(study, CUT_KEPT)))
    assert sha(again / "cut.jsonl") != sha(cut.items)
    why = cut_refused(study, cut, tmp_path, capsys, cut_items=again / "cut.jsonl")
    assert "the item file given is not the file of the plan's item list 'e5'" in why
    other, _, _ = cut_scored(study, cut, tmp_path, capsys, cut_seed_list=again / "seeds.csv")
    assert other["inputs"]["seed_list_sha256"] == sha(again / "seeds.csv") != sha(cut.seeds)
    assert other["item_set"] == report["item_set"] and other["tests"] == report["tests"]


def test_the_pattern_is_read_on_a_cut_e5_with_the_same_floors(
    study: SimpleNamespace,
    cut: SimpleNamespace,
    e2: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PLAN section 13, "The sentence": if E5 is cut, the pattern is read on those items with
    the same floors. The E2 result is of the same plan of the runs as the cut E5."""
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", CUT_SEEDS)
    scored_cut, _, e5_path = cut_scored(study, cut, tmp_path, capsys)
    e2_path = fresh(tmp_path)
    assert LS.main(e2_args(study, e2_path, out_root=cut.runs)) == 0
    capsys.readouterr()
    report, printed = patterned(tmp_path, capsys, e2_path, e5_path)
    assert report["e5"]["item_set"] == scored_cut["item_set"]
    assert report["e5"]["items"] == 35 and report["e5"]["seeds"] == 5
    assert report["registered"]["pattern"]["standing_floor"] == 0.1
    assert report["inputs"]["plan_sha256"] == sha(lp.plan_path(cut.runs))
    counting = {}
    for model in (LLAMA, DEEPSEEK):
        found = report["primaries"][model]
        assert found["has_pattern"] is True and found["letter"]["e2"]["met"] is True
        counting[model] = check_pattern_against_the_script(
            found, scored_cut["tests"], model, CUT_KEPT
        )
        assert found["holds"] is bool(counting[model])
    stated = [model for model in (LLAMA, DEEPSEEK) if counting[model]]
    assert report["sentence"]["stated_for"] == stated
    assert report["sentence"]["beside"][-2:] == [
        "E5 is cut to 35 items (section 12, cut 4): the pattern is read on those items with the "
        "same floors",
        NO_SECONDARY,
    ]
    assert printed.startswith(
        "pattern of PLAN section 13: E2 on 23 gold items; E5 on 35 items of 5 seeds, cut to the "
        "first 6 of the seed list ("
    )
    # the E2 result of the whole study is of another plan of the runs
    whole = fresh(tmp_path)
    assert LS.main(e2_args(study, whole)) == 0
    capsys.readouterr()
    assert json.loads(whole.read_text())["item_sets"] == e2.report["item_sets"]
    assert pattern_refused(tmp_path, capsys, whole, e5_path) == (
        "refused: the two results are of different plans of the runs"
    )
    # a result of a cut to six seeds is not read by a scorer that registers fifty
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", 50)
    assert pattern_refused(tmp_path, capsys, e2_path, e5_path) == (
        "refused: --e2: the result file of e2 was written under another registered record than "
        "this scorer's (another constant, primary, line or template pin)"
    )


def test_e5_cut_refusals(
    study: SimpleNamespace,
    cut: SimpleNamespace,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", CUT_SEEDS)

    def why(**replace: Any) -> str:
        return cut_refused(study, cut, tmp_path, capsys, **replace)

    # the three options of a cut go together
    together = (
        "refused: a cut of E5 takes --cut-seed-list, --expect-seed-list-sha256 and --cut-items "
        "together"
    )
    assert why(cut_seed_list=None) == together and why(cut_items=None) == together
    assert why(expect_seed_list_sha256=None) == together
    assert why(cut_seed_list=None, cut_items=None) == together
    # the seed list behind its hash
    assert "--expect-seed-list-sha256 takes a sha256" in why(expect_seed_list_sha256="abc")
    assert why(expect_seed_list_sha256="1" * 64).startswith(
        "refused: the seed list is not the expected file: its sha256 starts with "
    )
    assert why(cut_seed_list=tmp_path / "none.csv").startswith(
        "refused: the seed list cannot be read (FileNotFoundError)"
    )
    made = tmp_path / "lists"
    made.mkdir()

    def with_list(text: str) -> str:
        path = made / f"seeds_{len(list(made.iterdir()))}.csv"
        path.write_text(text, encoding="utf-8")
        return why(cut_seed_list=path)

    def with_ranks(change: Mapping[str, Any], drop: Sequence[str] = ()) -> str:
        ranks = listed_ranks() | dict(change)
        return with_list(seed_list({seed: r for seed, r in ranks.items() if seed not in drop}))

    assert with_list("statement_group_id,rank\nS00,1\n") == (
        "refused: the seed list has no rows or lacks the columns ['draw_rank']"
    )
    not_whole = "refused: the seed list holds a draw_rank that is not a whole number"
    assert with_ranks({"S04": "first"}) == not_whole and with_ranks({"S04": "2.5"}) == not_whole
    assert with_ranks({"S04": ""}) == not_whole
    twice = "refused: the seed list repeats a draw_rank or a seed, or holds a row with no seed"
    assert with_ranks({"S04": CUT_RANK[5]}) == twice
    text = seed_list(listed_ranks())
    assert with_list(text + "E77,S04,T77,500,fit\n") == twice
    assert with_list(text + "E77,,T77,500,fit\n") == twice
    assert (
        with_ranks({}, drop=["S04"]) == "refused: 1 seeds of the item file are not on the seed list"
    )
    assert with_ranks({}, drop=["S04", "S03", NO_ITEM]) == (
        "refused: 2 seeds of the item file are not on the seed list"
    )
    # a list that holds no more seeds than the cut keeps is no cut
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", 13)
    assert why() == "refused: the seed list holds 13 seeds: its first 13 are no cut"
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", 14)
    assert why() == "refused: the seed list holds 13 seeds: its first 14 are no cut"
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", CUT_SEEDS)
    # the cut item file: the rows of the items kept, as the item file has them, and no other
    not_the_cut = (
        "refused: the cut item file is not the item file cut to the first 6 seeds of the seed "
        "list: "
    )
    kept, others = cut_lines(study, CUT_KEPT), cut_lines(study, [2])

    def with_items(lines: Sequence[str]) -> str:
        path = made / f"cut_{len(list(made.iterdir()))}.jsonl"
        path.write_text("".join(lines))
        return why(cut_items=path)

    assert with_items(kept[:-2]) == not_the_cut + "2 items of the first seeds are missing"
    assert with_items([*kept, others[0]]) == (
        not_the_cut + "1 items are of other seeds or of no item of the item file"
    )
    changed_row = not_the_cut + "1 items are not as the item file has them, byte for byte"
    moved = json.loads(kept[4]) | {"availability_information": "Backordered."}
    assert with_items([*kept[:4], json.dumps(moved) + "\n", *kept[5:]]) == changed_row
    # a row that reads as the same values and is not the registered row as written: a value
    # written in another way, a cell written twice, the cells in another order, another
    # spacing. Each is another row than the one registered
    row = json.loads(kept[4])
    assert isinstance(row["is_seed"], bool) and kept[4].endswith("}\n")
    as_number = (
        kept[4]
        .replace('"is_seed": true', '"is_seed": 1')
        .replace('"is_seed": false', '"is_seed": 0')
    )
    twice = kept[4][:-2] + f', "seed_id": {json.dumps(row["seed_id"])}' + "}\n"
    reordered = json.dumps(dict(reversed(list(row.items()))), ensure_ascii=False) + "\n"
    spaced = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
    padded = kept[4][:-1] + " \n"
    for other in (as_number, twice, reordered, spaced, padded):
        assert other != kept[4] and json.loads(other) == row
        assert with_items([*kept[:4], other, *kept[5:]]) == changed_row
    two = with_items([as_number, *kept[:4], *kept[5:-1], kept[-1].replace("{", "{ ", 1)])
    assert two == not_the_cut + "2 items are not as the item file has them, byte for byte"
    # the line end is no part of a row: the registered rows under other line ends, or without
    # the last one, are the rows unchanged. Such a file is then not the file the runs read
    for ends in ("".join(kept).replace("\n", "\r\n"), "".join(kept)[:-1]):
        same_rows = with_items([ends])
        assert "not as the item file has them" not in same_rows
        assert "the item file given is not the file of the plan's item list 'e5'" in same_rows
    renamed = json.loads(kept[0]) | {"item_id": "P0000000000"}
    assert with_items([json.dumps(renamed) + "\n", *kept[2:], *others]) == (
        not_the_cut
        + "2 items of the first seeds are missing; 8 items are of other seeds or of no item of "
        "the item file"
    )
    assert json.loads(kept[4])["item_id"] not in with_items([*kept[:4], *kept[5:]])
    # the first six of the draw and not the first six of the file: the cut of seeds 0 to 5
    assert with_items(cut_lines(study, range(6))).startswith(
        not_the_cut + "14 items of the first seeds are missing; 21 items are of other seeds"
    )
    assert with_items([]) == "refused: the cut item file is empty or holds an item twice"
    assert with_items([*kept, kept[0]]) == (
        "refused: the cut item file is empty or holds an item twice"
    )
    assert why(cut_items=tmp_path / "none.jsonl").startswith(
        "refused: the cut item file cannot be read (FileNotFoundError)"
    )
    # the runs must be those of the cut: here the runs of the whole study
    apart = why(out_root=study.runs)
    assert apart.startswith(GENERAL)
    assert "the plan's item list 'e5' is not the minimal pairs of the cut" in apart
    assert "the item file given is not the file of the plan's item list 'e5'" in apart
    # and the runs of the cut are not scored as the whole
    out = fresh(tmp_path, "refused")
    with pytest.raises(SystemExit) as stop:
        LS.main(e5_args(study, out, out_root=cut.runs))
    assert "the plan's item list 'e5' is not the minimal pairs;" in stop.value.code
    assert "which the runs read" in stop.value.code and not out.exists()
    # under the registered fifty, a list of thirteen seeds is no cut
    monkeypatch.setattr(LS, "E5_CUT_SEEDS", 50)
    assert why() == "refused: the seed list holds 13 seeds: its first 50 are no cut"
    # a file of the cut named in a sealed folder is refused unopened
    vault = tmp_path / "sealed"
    vault.mkdir()
    (vault / "file").write_bytes(b"sealed\n")
    for name in ("cut_seed_list", "cut_items"):
        hashed = {"expect_seed_list_sha256": "0" * 64}
        argv = cut_args(study, cut, tmp_path / "out.json", **{name: vault / "file"}, **hashed)
        capsys.readouterr()
        with watching() as touched, pytest.raises(SystemExit) as stop:
            LS.main(argv)
        assert stop.value.code == (
            f"refused: --{name.replace('_', '-')} lies in a sealed folder; no sealed file is read"
        )
        assert touched == [] and not (tmp_path / "out.json").exists()
