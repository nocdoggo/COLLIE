"""Tests for the agreement script of the literal task (``audit_agreement.py``).

Krippendorff's alpha is checked against published worked examples (Krippendorff 2011,
"Computing Krippendorff's Alpha-Reliability": the binary and the nominal example with two
observers, and the four-observer example with missing data under the nominal and the interval
metric; and the three-coder example of the Wikipedia article on the coefficient), against a
value worked by hand, and against a second implementation written from the definition (pairs of
values inside units over pairs of values anywhere). Cohen's kappa is checked against the
textbook two-by-two example. The rest runs on made-up labels and on the made-up corpus of
``test_audit_sample.py``: month offsets and the stale flag on the dates of the guide's worked
examples, the share of identical intervals, the statistics by stratum, the bootstrap, the gate
(threshold, pooling with the pilot, an undefined gate, its constants against the real guide),
the list of disagreements, the gold
rows, and the three commands end to end with their manifest entries and their refusals (a
sheet that does not validate, a blank that is missing or changed, a filled adjudication sheet
in the way) and the gate's note on the guide line of the check sheets. No capture file, no
outcome and nothing sealed is read.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_audit_agreement.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import random
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from analysis.coling import audit_agreement as A
from analysis.coling import audit_sample as S
from analysis.coling import test_audit_sample as T

NA = None


# --------------------------------------------------------------------------------------------
# Krippendorff's alpha and Cohen's kappa
# --------------------------------------------------------------------------------------------

# Krippendorff (2011), section A: two observers, binary data, ten units
BINARY_ONE = [0, 1, 0, 0, 0, 0, 0, 0, 1, 0]
BINARY_TWO = [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]
# section B: two observers, nominal data, twelve units
NOMINAL_ONE = list("aabbdcccedda")
NOMINAL_TWO = list("babbbccceddd")
# sections C and D: four observers, twelve units, missing data
FOUR = [
    [1, 2, 3, 3, 2, 1, 4, 1, 2, NA, NA, NA],
    [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, NA, 3],
    [NA, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, NA],
    [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, NA],
]
# the worked example of the Wikipedia article: three coders, fifteen units
WIKI = [
    [NA, NA, NA, NA, NA, 3, 4, 1, 2, 1, 1, 3, 3, NA, 3],
    [1, NA, 2, 1, 3, 3, 4, 3, NA, NA, NA, NA, NA, NA, NA],
    [NA, NA, 2, 1, 3, 4, 4, NA, 2, 1, 1, 3, 3, NA, 4],
]


def units(*coders: Sequence[Any]) -> list[tuple[Any, ...]]:
    return list(zip(*coders, strict=True))


def alpha_from_the_definition(data: Sequence[Sequence[Any]], metric: str) -> float:
    """1 - D_o / D_e, summed over pairs of values: inside each unit for the observed
    disagreement, over all pairable values for the expected one."""

    def delta(a: Any, b: Any) -> float:
        return float(a != b) if metric == "nominal" else float((a - b) ** 2)

    kept = [[v for v in unit if v is not None] for unit in data]
    kept = [unit for unit in kept if len(unit) >= 2]
    values = [v for unit in kept for v in unit]
    n = len(values)
    observed = sum(
        sum(delta(a, b) for a, b in itertools.permutations(unit, 2)) / (len(unit) - 1)
        for unit in kept
    )
    expected = sum(delta(a, b) for a, b in itertools.permutations(values, 2))
    return 1 - (observed / n) / (expected / (n * (n - 1)))


def test_alpha_binary_example_of_krippendorff_2011() -> None:
    assert A.krippendorff_alpha(units(BINARY_ONE, BINARY_TWO), "nominal") == pytest.approx(
        0.095, abs=5e-4
    )
    # with two values the interval metric gives the same coefficient
    assert A.krippendorff_alpha(units(BINARY_ONE, BINARY_TWO), "interval") == pytest.approx(
        0.095, abs=5e-4
    )


def test_alpha_nominal_example_of_krippendorff_2011() -> None:
    assert A.krippendorff_alpha(units(NOMINAL_ONE, NOMINAL_TWO), "nominal") == pytest.approx(
        0.692, abs=5e-4
    )


def test_alpha_with_four_observers_and_missing_data() -> None:
    data = units(*FOUR)
    assert A.krippendorff_alpha(data, "nominal") == pytest.approx(0.743, abs=5e-4)
    assert A.krippendorff_alpha(data, "interval") == pytest.approx(0.849, abs=5e-4)


def test_alpha_wikipedia_example() -> None:
    data = units(*WIKI)
    assert A.krippendorff_alpha(data, "nominal") == pytest.approx(0.691, abs=5e-4)
    assert A.krippendorff_alpha(data, "interval") == pytest.approx(0.811, abs=5e-4)


def test_alpha_worked_by_hand() -> None:
    """Three units, two coders: (1, 1), (2, 2), (3, 4). One pair differs by 1, so the observed
    sum over ordered pairs is 2; the squared differences over all ordered pairs of the six
    values sum to 82; alpha = 1 - (6 - 1) * 2 / 82 = 36 / 41."""
    assert A.krippendorff_alpha([(1, 1), (2, 2), (3, 4)]) == pytest.approx(36 / 41)
    # nominal: 2 of 6 coincidences off the diagonal; expected pairs of unlike values 26 of 30
    assert A.krippendorff_alpha([(1, 1), (2, 2), (3, 4)], "nominal") == pytest.approx(
        1 - (2 / 6) / (26 / 30)
    )


@pytest.mark.parametrize("metric", ["nominal", "interval"])
def test_alpha_equals_the_definition_on_random_data(metric: str) -> None:
    rng = random.Random(S.SEED)
    for coders in (2, 3, 5):
        for _ in range(20):
            data = [
                tuple(rng.choice([None, *range(-3, 9)]) for _ in range(coders))
                for _ in range(rng.randint(4, 30))
            ]
            pairable = [[v for v in unit if v is not None] for unit in data]
            if len({v for unit in pairable if len(unit) >= 2 for v in unit}) < 2:
                continue
            ours = A.krippendorff_alpha(data, metric)
            assert ours == pytest.approx(alpha_from_the_definition(data, metric), abs=1e-9)
    for example in (units(BINARY_ONE, BINARY_TWO), units(*FOUR), units(*WIKI)):
        assert A.krippendorff_alpha(example, metric) == pytest.approx(
            alpha_from_the_definition(example, metric), abs=1e-12
        )


def test_alpha_properties() -> None:
    offsets = [(0, 0), (1, 1), (2, 3), (5, 5), (12, 10), (-1, -1), (3, 3)]
    alpha = A.krippendorff_alpha(offsets)
    assert alpha is not None and 0.9 < alpha < 1
    assert A.krippendorff_alpha([(b, a) for a, b in offsets]) == pytest.approx(alpha)
    assert A.krippendorff_alpha(offsets[::-1]) == pytest.approx(alpha)
    assert A.krippendorff_alpha([(a + 7, b + 7) for a, b in offsets]) == pytest.approx(alpha)
    assert A.krippendorff_alpha([(3 * a, 3 * b) for a, b in offsets]) == pytest.approx(alpha)
    assert A.krippendorff_alpha([*offsets, (4, None), (None, None)]) == pytest.approx(alpha)
    assert A.krippendorff_alpha([(a, a) for a, _ in offsets]) == 1.0
    assert A.krippendorff_alpha([(0, 5), (5, 0), (0, 5), (5, 0)]) < 0
    # the interval metric forgives a near miss that the nominal one does not
    assert alpha > A.krippendorff_alpha(offsets, "nominal")


def test_alpha_is_undefined_without_variation_or_pairs() -> None:
    assert A.krippendorff_alpha([]) is None
    assert A.krippendorff_alpha([(2, 2), (2, 2), (2, 2)]) is None
    assert A.krippendorff_alpha([(1, None), (None, 2)]) is None
    assert A.krippendorff_alpha([("a", "a")], "nominal") is None
    with pytest.raises(ValueError, match="metric must be nominal or interval"):
        A.krippendorff_alpha([(1, 2)], "ordinal")


def test_cohen_kappa_textbook_example() -> None:
    """Two readers of 50 proposals: both yes 20, yes and no 5, no and yes 10, both no 15.
    Observed agreement 0.7, chance agreement 0.5, kappa 0.4."""
    pairs = [("y", "y")] * 20 + [("y", "n")] * 5 + [("n", "y")] * 10 + [("n", "n")] * 15
    assert A.cohen_kappa(pairs) == pytest.approx(0.4)
    assert A.cohen_kappa([(b, a) for a, b in pairs]) == pytest.approx(0.4)
    assert A.cohen_kappa([("a", "a"), ("b", "b"), ("c", "c")]) == 1.0
    assert A.cohen_kappa([("a", "b"), ("b", "a")]) == pytest.approx(-1.0)
    # three classes, by hand: agreement 4/6; chance (2*3 + 2*2 + 2*1) / 36 = 1/3; kappa 0.5
    three = [("a", "a"), ("a", "a"), ("b", "b"), ("c", "c"), ("b", "a"), ("c", "b")]
    assert A.cohen_kappa(three) == pytest.approx(0.5)
    assert A.cohen_kappa([]) is None
    assert A.cohen_kappa([("a", "a"), ("a", "a")]) is None  # chance agreement is complete


def test_bootstrap_is_seeded_and_counts_undefined_draws() -> None:
    values = [0, 0, 1, 1, 1, 0, 1, 1]

    def mean(rows: Sequence[int]) -> float:
        return sum(values[r] for r in rows) / len(rows)

    one = A.bootstrap(len(values), mean)
    assert one == A.bootstrap(len(values), mean)
    assert one is not None and one["draws"] == A.DRAWS == 2000
    assert 0 <= one["low"] < 5 / 8 < one["high"] <= 1
    assert A.bootstrap(len(values), mean, seed=1) != one
    assert A.bootstrap(len(values), mean, draws=50)["draws"] == 50
    assert A.bootstrap(0, mean) is None
    assert A.bootstrap(3, lambda rows: None) is None

    def alpha(rows: Sequence[int]) -> float | None:
        return A.krippendorff_alpha([[(0, 0), (0, 0), (1, 1)][r] for r in rows])

    some = A.bootstrap(3, alpha, draws=200)  # a draw of one unit three times has no variation
    assert some is not None and 0 < some["draws"] < 200 and some["low"] == some["high"] == 1.0


# --------------------------------------------------------------------------------------------
# Labels, offsets and the statistics of section 8.1
# --------------------------------------------------------------------------------------------


def lab(
    item: str = "I1", start: str = "", end: str = "", anchor: str = "2020-03-02", **changes: str
) -> S.Label:
    """A checked label: an interval when ``start`` is given, else an abstention (``tbd``)."""
    entered = T.GOOD | {"start": start, "end": end or start} if start else T.ABSTAIN
    row = T.SHOWN_ROW | {"item_id": item, "date_of_update": anchor} | entered | changes
    label, errors, _ = S.read_label(row)
    assert label is not None, errors
    return label


def months(a1: Sequence[int | None], a2: Sequence[int | None]) -> list[A.Pair]:
    """Pairs of labels whose intervals are whole months of 2020 (None abstains); the anchor is
    2020-03-02, so month m has the offset m - 3."""
    return [
        (
            lab(f"I{n}", f"2020-{a:02d}" if a else ""),
            lab(f"I{n}", f"2020-{b:02d}" if b else ""),
        )
        for n, (a, b) in enumerate(zip(a1, a2, strict=True))
    ]


@pytest.mark.parametrize(
    ("anchor", "start", "end", "offsets", "stale"),
    [
        ("2019-10-07", "2021-06-01", "2021-06-30", (20, 20), False),  # example 1 of the guide
        ("2020-08-13", "2020-10", "2020-10", (2, 2), False),  # 2
        ("2021-11-17", "2021-10-01", "2022-03-31", (-1, 4), False),  # 6
        ("2019-10-09", "2019-10-28", "2019-11-03", (0, 1), False),  # 7
        ("2022-09-30", "2022-12-29", "2024-03-23", (3, 18), False),  # 9
        ("2020-06-02", "2020-05", "2020-05", (-1, -1), True),  # 18
        ("2020-06-02", "2020-05-21", "2020-05-31", (-1, -1), True),  # 19
        ("2021-09-23", "2019-11", "2019-11", (-22, -22), True),  # 20
        ("2019-12-10", "2019-12-21", "2020-01-10", (0, 1), False),  # H1
    ],
)
def test_offsets_and_stale_of_the_guides_examples(
    anchor: str, start: str, end: str, offsets: tuple[int, int], stale: bool
) -> None:
    label = lab("I1", start, end, anchor)
    found = label.offsets()
    assert (found["start_offset_m"], found["end_offset_m"]) == offsets
    assert label.stale is stale
    assert found["start_offset_d"] == (label.start - label.anchor).days
    assert found["end_offset_d"] == (label.end - label.anchor).days
    assert A.class_value(label, "stale") == ("yes" if stale else "no")


def test_identical_intervals_and_offset_units() -> None:
    pairs = months([4, 5, None, None, 6, 7], [4, 6, None, 5, None, 7])
    assert [A.same_interval(a, b) for a, b in pairs] == [True, False, True, False, False, True]
    assert A.offset_units(pairs, "start_offset_m") == [(1, 1), (2, 3), (4, 4)]
    assert A.offset_units(pairs, "end_offset_m") == [(1, 1), (2, 3), (4, 4)]
    assert A.offset_units(pairs, "start_offset_d") == [(30, 30), (60, 91), (121, 121)]
    stats = A.cell_statistics(pairs, intervals=True)
    assert stats["n"] == 6 and stats["interval_pairs"] == 3
    assert stats["identical_intervals"] == pytest.approx(0.5)
    assert stats["alpha_start_offset_m"] == pytest.approx(
        A.krippendorff_alpha([(1, 1), (2, 3), (4, 4)])
    )
    # the same start but another end is not an identical interval
    other_end = (lab("I1", "2020-04-01", "2020-04-30"), lab("I1", "2020-04-01", "2020-05-31"))
    assert not A.same_interval(*other_end)
    assert A.offset_units([other_end], "start_offset_m") == [(1, 1)]
    assert A.offset_units([other_end], "end_offset_m") == [(1, 2)]


def test_class_statistics_and_marginals() -> None:
    pairs = months([4, 5, None, None, 6, 7], [4, 6, None, 5, None, 7])
    abstain = A.class_statistics(pairs, "abstain")
    assert abstain["n"] == 6 and abstain["raw_agreement"] == pytest.approx(4 / 6)
    assert abstain["marginal_shares"] == {
        "A1": {"no": pytest.approx(4 / 6, abs=1e-6), "yes": pytest.approx(2 / 6, abs=1e-6)},
        "A2": {"no": pytest.approx(4 / 6, abs=1e-6), "yes": pytest.approx(2 / 6, abs=1e-6)},
    }
    values = [("no", "no")] * 3 + [("yes", "yes"), ("yes", "no"), ("no", "yes")]
    assert abstain["kappa"] == pytest.approx(A.cohen_kappa(values), abs=1e-6)
    assert abstain["alpha_nominal"] == pytest.approx(
        A.krippendorff_alpha(values, "nominal"), abs=1e-6
    )
    certainty = A.class_statistics(pairs, "certainty")
    assert set(certainty["marginal_shares"]["A1"]) == {"asserted", "undetermined"}
    one = lab("I1", "2020-04", distractor_roles="expiry", distractor_quotes="(1/2022 expiry)")
    assert A.class_value(one, "any_distractor") == "yes"
    assert A.class_value(lab("I1", "2020-04"), "any_distractor") == "no"
    assert A.class_value(one, "statement_type") == "next_delivery"
    assert A.class_statistics([], "abstain") == {
        "n": 0,
        "kappa": None,
        "raw_agreement": None,
        "alpha_nominal": None,
        "marginal_shares": {},
    }


def test_statistics_by_stratum_give_alpha_only_with_ten_pairs() -> None:
    a1 = [1 + n % 12 for n in range(24)]
    a2 = [1 + (n + (n % 5 == 0)) % 12 for n in range(24)]
    pairs = {f"I{n:02d}": pair for n, pair in enumerate(months(a1, a2))}
    key = {
        item: {"stratum": "range" if n < 9 else "quarter", "period": "train" if n % 2 else "test"}
        for n, item in enumerate(pairs)
    }
    stats = A.statistics(pairs, {"A1": 20, "A2": None}, key)
    assert stats["n"] == 24 and stats["interval_pairs"] == 24
    assert stats["seconds_per_item"] == {"A1": 50.0, "A2": None}
    assert stats["hard"] == {"A1": 0, "A2": 0}
    assert stats["to_adjudication"] == 5
    assert stats["identical_intervals"] == pytest.approx(19 / 24, abs=1e-6)
    assert set(stats["by_stratum"]) == {"range", "quarter"}
    assert stats["by_stratum"]["range"]["n"] == 9
    assert stats["by_stratum"]["range"]["alpha_start_offset_m"] is None  # nine pairs: too few
    assert stats["by_stratum"]["range"]["identical_intervals"] is not None
    assert stats["by_stratum"]["range"]["abstain"]["raw_agreement"] == 1.0
    assert stats["by_stratum"]["quarter"]["n"] == 15
    assert stats["by_stratum"]["quarter"]["alpha_start_offset_m"] is not None
    assert "intervals_95" not in stats["by_stratum"]["quarter"]
    assert set(stats["by_period"]) == {"train", "test"}
    spans = stats["intervals_95"]
    assert set(spans) == {
        "identical_intervals",
        *(f"alpha_{name}" for name in A.OFFSETS),
        *(f"kappa_{name}" for name in A.CLASS_FIELDS),
    }
    low, high = spans["alpha_start_offset_m"]["low"], spans["alpha_start_offset_m"]["high"]
    assert low <= stats["alpha_start_offset_m"] <= high
    assert spans["identical_intervals"]["low"] <= 19 / 24 <= spans["identical_intervals"]["high"]
    assert spans["kappa_abstain"] is None  # nobody abstains: kappa is undefined on every draw
    assert A.statistics(pairs, {"A1": 20, "A2": None}, key) == stats
    assert "by_stratum" not in A.statistics(pairs, {"A1": 20, "A2": 20})
    ten = {item: {"stratum": "range" if n < 10 else "quarter"} for n, item in enumerate(pairs)}
    by_stratum = A.statistics(pairs, {"A1": 20, "A2": 20}, ten)["by_stratum"]
    assert by_stratum["range"]["n"] == 10 and by_stratum["range"]["alpha_end_offset_m"] is not None
    # an item goes to adjudication for any adjudicated field, not only for its interval
    mixed = A.statistics(gold_pairs(), {"A1": None, "A2": None})
    assert mixed["to_adjudication"] == 3 and mixed["identical_intervals"] == pytest.approx(0.6)
    assert mixed["hard"] == {"A1": 0, "A2": 1}


def test_label_rows_carry_the_computed_columns() -> None:
    stale = lab("I2", "2020-01", quote="not in the entry")
    sheets = {
        "A1": S.Checked({"I2": stale, "I1": lab("I1", "2020-04")}, [], [], 10, [], []),
        "A2": S.Checked(
            {"I1": lab("I1"), "I2": lab("I2", "2020-03-02", "2020-03-02")},
            [],
            ["row 1 (I2): quote 'x' is not in the entry", "row 1 (I2): another", "sheet: a note"],
            10,
            [],
            [],
        ),
    }
    rows = A.label_rows(sheets)
    assert [(r["item_id"], r["annotator"]) for r in rows] == [
        ("I1", "A1"),
        ("I1", "A2"),
        ("I2", "A1"),
        ("I2", "A2"),
    ]
    assert all(set(r) == set(A.LABEL_COLUMNS) for r in rows)
    assert [r["stale"] for r in rows] == [0, 0, 1, 0]
    assert (rows[2]["start_offset_m"], rows[2]["end_offset_m"]) == (-2, -2)
    assert (rows[2]["start_offset_d"], rows[2]["end_offset_d"]) == (-61, -31)
    assert (rows[3]["start_offset_m"], rows[3]["start_offset_d"], rows[3]["end_offset_d"]) == (
        0,
        0,
        0,
    )
    assert rows[1]["start_offset_m"] == "" and rows[1]["abstain"] == "1"
    assert [r["check"] for r in rows] == [
        "ok",
        "ok",
        "ok",
        "quote 'x' is not in the entry; another",
    ]


def test_pairing_needs_the_same_items() -> None:
    one = S.Checked({"I1": lab("I1"), "I2": lab("I2")}, [], [], 10, [], [])
    two = S.Checked({"I2": lab("I2"), "I1": lab("I1")}, [], [], 10, [], [])
    assert list(A.paired(one, two)) == ["I1", "I2"]
    two.labels.pop("I2")
    with pytest.raises(ValueError, match="do not hold the same items: \\['I2'\\]"):
        A.paired(one, two)


# --------------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------------

TWELVE = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]


def test_the_gate_constants_are_the_real_guides() -> None:
    """Threshold, pooling limit and bootstrap size as the guide states them (sections 4 and 8)."""
    text = " ".join(T.REAL_GUIDE.read_text(encoding="utf-8").split())
    threshold = re.search(r"on the end month offsets\. Both must be at least (\d\.\d+)\.", text)
    assert threshold and float(threshold[1]) == A.GATE_ALPHA
    pooling = re.search(r"If fewer than (\d+) check items have an interval from both", text)
    assert pooling and int(pooling[1]) == A.MIN_PAIRS
    by_stratum = re.search(r"alpha when a stratum has at least (\d+) pairs of intervals", text)
    assert by_stratum and int(by_stratum[1]) == A.MIN_PAIRS
    draws = re.search(r"bootstrap intervals over items: ([\d,]+) draws, with seed (\d+)", text)
    assert draws and int(draws[1].replace(",", "")) == A.DRAWS and int(draws[2]) == A.SEED


def test_gate_passes_on_close_readings_and_reports_identical_intervals() -> None:
    near = [1, 2, 3, 5, 5, 6, 7, 8, 9, 10, 11, 11]
    result = A.gate(months(TWELVE, near))
    assert result["passed"] is True and result["pooled_with_pilot"] is False
    assert result["threshold"] == A.GATE_ALPHA == 0.6
    assert result["items"] == 12 and result["interval_pairs"] == 12
    assert result["alpha_start_offset_m"] > 0.9 and result["alpha_end_offset_m"] > 0.9
    assert result["identical_intervals"] == pytest.approx(10 / 12, abs=1e-6)
    assert result["reason"] == "both alphas reach the threshold"
    assert A.gate(months(TWELVE, TWELVE))["alpha_start_offset_m"] == 1.0


def test_gate_fails_when_either_alpha_is_low() -> None:
    mixed = [7, 12, 1, 9, 3, 11, 2, 8, 6, 4, 10, 5]
    result = A.gate(months(TWELVE, mixed))
    assert result["passed"] is False and result["reason"] == "an alpha is low"
    assert result["alpha_start_offset_m"] < 0.6
    # the starts agree and the ends do not: the end alpha alone fails the gate
    pairs = [
        (
            lab(f"I{n}", f"2020-{a:02d}-01", "2020-12-31"),
            lab(f"I{n}", f"2020-{a:02d}-01", f"2021-{b:02d}-28"),
        )
        for n, (a, b) in enumerate(zip(TWELVE, mixed, strict=True))
    ]
    result = A.gate(pairs)
    assert result["alpha_start_offset_m"] == 1.0 and result["alpha_end_offset_m"] < 0.6
    assert result["passed"] is False


def test_gate_threshold_is_inclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    pairs = months(TWELVE, [1, 2, 3, 5, 5, 6, 7, 8, 9, 10, 11, 11])
    alpha = A.gate(pairs)["alpha_start_offset_m"]
    monkeypatch.setattr(A, "GATE_ALPHA", alpha)
    assert A.gate(pairs)["passed"] is True
    monkeypatch.setattr(A, "GATE_ALPHA", alpha + 1e-6)
    assert A.gate(pairs)["passed"] is False


def test_gate_pools_the_pilot_when_the_check_set_cannot_decide() -> None:
    few = months([1, 2, 3, 4, 5, 6, 7, 8, 9, None, None], [1, 2, 3, 4, 5, 6, 7, 8, 9, None, 4])
    pilot = months([3, 9, None], [3, 9, None])
    alone = A.gate(few)
    assert alone["passed"] is False and alone["interval_pairs"] == 9
    assert alone["reason"].startswith("undefined") and "give the pilot sheets" in alone["reason"]
    pooled = A.gate(few, pilot)
    assert pooled["pooled_with_pilot"] is True and pooled["passed"] is True
    assert pooled["items"] == 14 and pooled["interval_pairs"] == 11
    assert pooled["check_alone"]["interval_pairs"] == 9 and pooled["check_alone"]["items"] == 11
    assert pooled["identical_intervals"] == pytest.approx(13 / 14, abs=1e-6)
    # ten pairs that do not vary: undefined, pooled; still undefined after pooling: not passed
    flat = months([4] * 10, [4] * 10)
    assert A.gate(flat, months([4, None], [4, None]))["passed"] is False
    assert "undefined" in A.gate(flat, months([4], [4]))["reason"]
    assert A.gate(flat, pilot)["passed"] is True
    # a check set that can decide is not pooled, whatever the pilot says; ten pairs are enough
    enough = months([*TWELVE[:10], None], [*TWELVE[:10], None])
    result = A.gate(enough, months([1, 12], [12, 1]))
    assert result["pooled_with_pilot"] is False and result["interval_pairs"] == A.MIN_PAIRS == 10
    assert result["passed"] is True and result["items"] == 11


# --------------------------------------------------------------------------------------------
# Disagreements and gold
# --------------------------------------------------------------------------------------------


def test_differences_name_the_adjudicated_fields() -> None:
    base = lab("I1", "2020-04")
    assert A.differences(base, lab("I1", "2020-04")) == []
    assert A.differences(base, lab("I1", "2020-04", quote="April 2020")) == []
    assert A.differences(base, lab("I1", "2020-04", hard="1", note="because")) == []
    assert A.differences(base, lab("I1", "2020-04-01", "2020-04-30")) == []  # the shorthand
    assert A.differences(base, lab("I1", "2020-05")) == ["start", "end"]
    assert A.differences(base, lab("I1", "2020-04", statement_type="recovery")) == [
        "statement_type"
    ]
    assert A.differences(base, lab("I1", "2020-04", certainty="estimated")) == ["certainty"]
    assert A.differences(base, lab("I1")) == [
        "statement_type",
        "abstain",
        "start",
        "end",
        "certainty",
        "abstain_reason",
    ]
    assert A.differences(lab("I1"), lab("I1", abstain_reason="no_date")) == ["abstain_reason"]
    roles = {"distractor_roles": "expiry; other", "distractor_quotes": "(1/2022 expiry); expiry"}
    swapped = {"distractor_roles": "other; expiry", "distractor_quotes": "5 month; expiry"}
    one_role = {"distractor_roles": "expiry", "distractor_quotes": "(1/2022 expiry)"}
    assert A.differences(lab("I1", "2020-04", **roles), lab("I1", "2020-04", **swapped)) == []
    assert A.differences(base, lab("I1", "2020-04", **one_role)) == ["distractor_roles"]
    twice = {"distractor_roles": "expiry; expiry", "distractor_quotes": "5 month; expiry"}
    assert A.differences(lab("I1", "2020-04", **one_role), lab("I1", "2020-04", **twice)) == [
        "distractor_roles"
    ]
    assert set(A.ADJUDICATED) == {
        "statement_type",
        "abstain",
        "abstain_reason",
        "start",
        "end",
        "certainty",
        "distractor_roles",
    }


def gold_pairs() -> dict[str, A.Pair]:
    return {
        "I1": (
            lab("I1", "2020-04", quote="Next release April 2020"),
            lab("I1", "2020-04", quote="April 2020", hard="1", note="short"),
        ),
        "I2": (lab("I2", "2020-04"), lab("I2", "2020-05")),
        "I3": (lab("I3"), lab("I3", "2020-06")),
        "I4": (lab("I4", "2020-04"), lab("I4", "2020-04", certainty="estimated")),
        "I5": (lab("I5"), lab("I5")),
    }


def decided(
    item: str, decision: str, entered: dict[str, str] | None = None, note: str = ""
) -> dict[str, str]:
    blank = dict.fromkeys(S.ENTERED, "")
    return (
        T.SHOWN_ROW
        | {"item_id": item}
        | (entered if entered is not None else blank)
        | {"adj_decision": decision, "adj_note": note}
    )


def test_disagreement_rows_show_both_labels_side_by_side() -> None:
    pairs = gold_pairs()
    shown = {item: T.SHOWN_ROW | {"item_id": item, "presentation": "'-10 mg"} for item in pairs}
    rows = A.disagreement_rows(pairs, shown)
    assert [r["item_id"] for r in rows] == ["I2", "I3", "I4"]
    assert rows[0]["differs"] == "start; end" and rows[2]["differs"] == "certainty"
    assert rows[0]["A1_start"] == "2020-04-01" and rows[0]["A2_end"] == "2020-05-31"
    assert rows[1]["A1_abstain"] == "1" and rows[1]["A2_abstain"] == "0"
    assert rows[0]["presentation"] == "-10 mg"  # the guard goes back on when the sheet is written
    assert not [
        c
        for c in A.ADJUDICATION_COLUMNS
        if c not in rows[0] and c not in (*S.ENTERED, "adj_decision", "adj_note")
    ]
    text = S.sheet_text(A.ADJUDICATION_COLUMNS, rows, [("sheet", "literal disagreements")])
    _, parsed = S.parse_sheet(text)
    assert parsed[0]["presentation"] == "'-10 mg" and parsed[0]["adj_decision"] == ""
    assert all(parsed[0][c] == "" for c in S.ENTERED)


def test_gold_takes_agreed_rows_and_decisions() -> None:
    pairs = gold_pairs()
    adjudicated = [
        decided(
            "I2", "slip", T.GOOD | {"start": "2020-05", "end": "2020-05"}, "A1 misread the month"
        ),
        decided("I3", "gap"),  # could not be settled: left out
        decided("I4", "GAP", T.GOOD | {"certainty": "estimated"}, "new convention"),
    ]
    rows, report, errors = A.build_gold(pairs, adjudicated)
    assert errors == []
    assert [r["item_id"] for r in rows] == ["I1", "I2", "I4", "I5"]
    backwards = dict(reversed(pairs.items()))
    assert A.build_gold(backwards, adjudicated[::-1]) == (rows, report, errors)
    assert all(tuple(r) == A.GOLD_COLUMNS for r in rows)
    agreed = rows[0]
    assert agreed["adj_decision"] == "agree" and agreed["quote"] == "April 2020"  # the shorter
    assert agreed["hard"] == "1" and agreed["note"] == "A2: short"
    assert (agreed["start"], agreed["end"]) == ("2020-04-01", "2020-04-30")
    assert rows[1] | {"adj_note": ""} == {"item_id": "I2"} | T.GOOD | {
        "start": "2020-05-01",
        "end": "2020-05-31",
        "adj_decision": "slip",
        "adj_note": "",
    }
    assert rows[1]["adj_note"] == "A1 misread the month"
    assert rows[2]["adj_decision"] == "gap" and rows[2]["certainty"] == "estimated"
    assert rows[3]["adj_decision"] == "agree" and rows[3]["abstain"] == "1"
    assert report == {
        "items": 5,
        "gold_rows": 4,
        "agree": 2,
        "slip": 1,
        "gap": 2,
        "left_out": 1,
        "decisions_by_field": {
            "slip": {"end": 1, "start": 1},
            "gap": {
                "abstain": 1,
                "abstain_reason": 1,
                "certainty": 2,
                "end": 1,
                "start": 1,
                "statement_type": 1,
            },
        },
    }


def test_gold_is_refused_when_the_adjudication_sheet_is_wrong() -> None:
    pairs = gold_pairs()
    good = [
        decided("I2", "slip", T.GOOD),
        decided("I3", "slip", T.ABSTAIN),
        decided("I4", "slip", T.GOOD),
    ]
    assert A.build_gold(pairs, good)[2] == []
    assert A.build_gold(pairs, good[:2])[2] == ["sheet: item I4 is not adjudicated"]
    assert A.build_gold(pairs, [*good, decided("I1", "slip", T.GOOD)])[2] == [
        "row 4 (I1): not an item to adjudicate, or repeated"
    ]
    assert A.build_gold(pairs, [*good, good[0]])[2] == [
        "row 4 (I2): not an item to adjudicate, or repeated"
    ]
    undecided = [decided("I2", "", T.GOOD), *good[1:]]
    assert A.build_gold(pairs, undecided)[2] == [
        "row 1 (I2): adj_decision must be one of slip, gap"
    ]
    wrong = [decided("I2", "slip", T.GOOD | {"start": "2020-06"}), *good[1:]]
    assert A.build_gold(pairs, wrong)[2] == ["row 1 (I2): start is after end"]
    empty_slip = [decided("I2", "slip"), *good[1:]]
    assert A.build_gold(pairs, empty_slip)[2] == ["row 1 (I2): the row is not filled"]


# --------------------------------------------------------------------------------------------
# Commands, on the made-up corpus of test_audit_sample.py
# --------------------------------------------------------------------------------------------


def reading(row: dict[str, str], shift: int = 0) -> dict[str, str]:
    """A made-up annotator: abstains on the wordings that give no time, and otherwise reads a
    month that depends on the item id (so that offsets vary) and on ``shift``."""
    text = row["availability_information"]
    if "TBD" in text:
        return T.ABSTAIN
    if "few months" in text:
        return T.ABSTAIN | {"abstain_reason": "vague", "certainty": "estimated"}
    if text.startswith("On backorder"):
        return T.ABSTAIN | {
            "statement_type": "none",
            "abstain_reason": "no_statement",
            "certainty": "no_statement",
        }
    year = int(row["date_of_update"][:4]) + 1
    month = 1 + (int(row["item_id"][1:], 16) + shift) % 12
    return T.GOOD | {"start": f"{year}-{month:02d}", "end": f"{year}-{month:02d}"}


def careless(row: dict[str, str]) -> dict[str, str]:
    """A second annotator who differs from the first on about a third of the items."""
    pick = int(row["item_id"][1:], 16) % 3
    label = reading(row, shift=1 if pick == 0 else 0)
    return label | {"quote": "On backorder"} if label["abstain"] == "1" and pick == 1 else label


def wild(row: dict[str, str]) -> dict[str, str]:
    """An annotator whose months have nothing to do with the first one's."""
    return reading(row, shift=int(hashlib.sha256(row["item_id"].encode()).hexdigest(), 16) % 12)


def hand_in(
    out: Path,
    work: Path,
    task: str,
    a1: Callable[..., dict] = reading,
    a2: Callable[..., dict] = reading,
) -> list[str]:
    """Fill both blank sheets of a task in ``work`` and return the arguments of ``agree``."""
    work.mkdir(parents=True, exist_ok=True)
    args = ["agree", "--task", task, "--dir", str(out)]
    for annotator, labels in (("A1", a1), ("A2", a2)):
        blank = (out / f"{task}_{annotator}.csv").read_text(encoding="utf-8")
        filled = work / f"{task}_{annotator}.csv"
        filled.write_text(T.fill(blank, labels), encoding="utf-8")
        args += [f"--{annotator.lower()}", str(filled)]
    return args


def manifest_of(out: Path) -> dict[str, Any]:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def test_agree_on_the_pilot_writes_statistics_labels_and_disagreements(
    tmp_path: Path, capsys: Any
) -> None:
    out, _ = T.drawn_folder(tmp_path)
    args = hand_in(out, tmp_path / "work", "pilot", reading, careless)
    # one sheet comes back as a spreadsheet saves it: CRLF line ends and a byte-order mark
    saved = tmp_path / "work" / "pilot_A2.csv"
    saved.write_bytes(b"\xef\xbb\xbf" + saved.read_bytes().replace(b"\n", b"\r\n"))
    capsys.readouterr()
    assert A.main(args) == 0
    printed = capsys.readouterr().out
    assert "pilot: 12 items, 9 with an interval from both" in printed and "gate:" not in printed
    assert (out / "submitted" / "pilot_A2.csv").read_bytes().startswith(b'\xef\xbb\xbf"# task')
    for annotator in S.ANNOTATORS:
        name = f"submitted/pilot_{annotator}.csv"
        copy, filled = out / name, tmp_path / "work" / f"pilot_{annotator}.csv"
        assert copy.read_bytes() == filled.read_bytes()
        assert manifest_of(out)["submitted"][name] == T.sha(copy)
    stats = json.loads((out / "pilot_agreement.json").read_text(encoding="utf-8"))
    assert stats["task"] == "pilot" and stats["n"] == 12 and stats["interval_pairs"] == 9
    assert stats["guide"] == {"A1": S.guide_stamp(T.guide_text(**T.SMALL))} | {
        "A2": S.guide_stamp(T.guide_text(**T.SMALL))
    }
    assert stats["sheets_sha256"]["A1"] == T.sha(out / "submitted" / "pilot_A1.csv")
    assert stats["seconds_per_item"] == {"A1": 100.0, "A2": 100.0}
    assert "gate" not in stats
    assert set(stats["by_stratum"]) == set(T.NAMES) and set(stats["by_period"]) == {"train"}
    assert stats["abstain"]["raw_agreement"] == 1.0 and stats["abstain"]["kappa"] == 1.0
    assert stats["statement_type"]["marginal_shares"]["A1"]["none"] == pytest.approx(
        1 / 12, abs=1e-6
    )
    labels = list(csv.DictReader((out / "pilot_labels.csv").open(encoding="utf-8")))
    assert tuple(labels[0]) == A.LABEL_COLUMNS and len(labels) == 24
    assert [r["annotator"] for r in labels[:2]] == ["A1", "A2"]
    dated = [r for r in labels if r["abstain"] == "0"]
    assert all(r["start_offset_m"] != "" and r["stale"] == "0" for r in dated)
    assert all(r["start_offset_m"] == "" for r in labels if r["abstain"] == "1")
    assert {r["check"] for r in labels} <= {"ok", "quote 'On backorder' is not in the entry"}
    meta, rows = S.read_sheet(out / "pilot_disagreements.csv")
    assert dict(meta)["sheet"] == "pilot disagreements" and dict(meta)["items"] == str(len(rows))
    assert len(rows) == stats["to_adjudication"] > 0
    assert stats["identical_intervals"] == pytest.approx(1 - len(rows) / 12, abs=1e-6)
    assert all(r["differs"] == "start; end" for r in rows)
    assert (
        "adj_decision" not in rows[0] and "A1_start" in rows[0] and "statement_type" not in rows[0]
    )
    recorded = manifest_of(out)["agreement"]["pilot"]
    assert sorted(recorded) == [
        "pilot_agreement.json",
        "pilot_disagreements.csv",
        "pilot_labels.csv",
    ]
    assert all(T.sha(out / name) == digest for name, digest in recorded.items())
    before = {name: (out / name).read_bytes() for name in recorded}
    assert A.main(args) == 0
    assert {name: (out / name).read_bytes() for name in recorded} == before


def test_gate_command_pools_the_pilot_and_sets_the_exit_status(tmp_path: Path, capsys: Any) -> None:
    out, _ = T.drawn_folder(tmp_path)
    check = hand_in(out, tmp_path / "work", "check", reading, careless)
    capsys.readouterr()
    assert A.main(check) == 1  # seven check items, and no pilot sheets to pool
    printed = capsys.readouterr().out
    assert "NOT PASSED (undefined" in printed and "give the pilot sheets" in printed
    stats = json.loads((out / "check_agreement.json").read_text(encoding="utf-8"))
    assert stats["gate"]["passed"] is False and stats["gate"]["interval_pairs"] == 7
    assert A.main(hand_in(out, tmp_path / "work", "pilot", reading, careless)) == 0
    capsys.readouterr()
    assert A.main(check) == 0
    printed = capsys.readouterr().out
    assert "threshold 0.6" in printed and "pooled with the pilot: True; PASSED" in printed
    assert "identical intervals" in printed
    gate = json.loads((out / "check_agreement.json").read_text(encoding="utf-8"))["gate"]
    assert gate["passed"] is True and gate["pooled_with_pilot"] is True
    assert gate["items"] == 7 + 12 and gate["interval_pairs"] == 7 + 9
    assert gate["check_alone"]["items"] == 7
    assert gate["alpha_start_offset_m"] >= 0.6 and gate["alpha_end_offset_m"] >= 0.6
    assert A.main(hand_in(out, tmp_path / "wild", "check", reading, wild)) == 1
    assert "NOT PASSED (an alpha is low)" in capsys.readouterr().out
    assert A.main(hand_in(out, tmp_path / "wild", "reserve", reading, reading)) == 0
    gate = json.loads((out / "reserve_agreement.json").read_text(encoding="utf-8"))["gate"]
    assert gate["pooled_with_pilot"] is True  # seven reserve items: pooled like the check set
    assert gate["check_alone"]["alpha_start_offset_m"] == 1.0
    assert gate["check_alone"]["identical_intervals"] == 1.0
    assert sorted(manifest_of(out)["agreement"]) == ["check", "pilot", "reserve"]
    assert sorted(manifest_of(out)["submitted"]) == [
        f"submitted/{task}_{annotator}.csv"
        for task in ("check", "pilot", "reserve")
        for annotator in S.ANNOTATORS
    ]


def test_gate_says_when_the_check_sheets_carry_the_pilots_guide(
    tmp_path: Path, capsys: Any
) -> None:
    out, inputs = T.drawn_folder(tmp_path)
    work = tmp_path / "work"
    check = hand_in(out, work, "check", reading, careless)
    assert A.main(check) == 1  # no pilot sheets yet: nothing to compare the guide line with
    gate = json.loads((out / "check_agreement.json").read_text(encoding="utf-8"))["gate"]
    assert gate["same_guide_as"] is None
    assert A.main(hand_in(out, work, "pilot", reading, careless)) == 0
    capsys.readouterr()
    assert A.main(check) == 0  # the note does not change the gate
    printed = capsys.readouterr().out
    assert "warning: a check sheet carries the guide line of the pilot sheets (v9 test" in printed
    gate = json.loads((out / "check_agreement.json").read_text(encoding="utf-8"))["gate"]
    assert gate["same_guide_as"] == ["pilot"] and gate["passed"] is True

    # the guide is revised and the check sheets are written again under it
    guide = Path(inputs[3])
    guide.write_text(
        guide.read_text(encoding="utf-8").replace("v9 test", "v9.1 test"), encoding="utf-8"
    )
    assert S.main(["sheets", "--task", "check", *inputs]) == 0
    capsys.readouterr()
    assert A.main(hand_in(out, work, "check", reading, careless)) == 0
    printed = capsys.readouterr().out
    assert "warning:" not in printed and "PASSED" in printed
    stats = json.loads((out / "check_agreement.json").read_text(encoding="utf-8"))
    assert stats["gate"]["same_guide_as"] == []
    assert stats["guide"]["A1"].startswith("v9.1 test sha256 ")

    # the reserve is compared with the pilot and with the check set
    assert A.main(hand_in(out, work, "reserve", reading, careless)) == 0
    printed = capsys.readouterr().out
    assert "warning: a reserve sheet carries the guide line of the pilot sheets" in printed
    assert "guide line of the check sheets" not in printed
    assert S.main(["sheets", "--task", "reserve", *inputs]) == 0
    capsys.readouterr()
    assert A.main(hand_in(out, work, "reserve", reading, careless)) == 0
    printed = capsys.readouterr().out
    assert "warning: a reserve sheet carries the guide line of the check sheets (v9.1 " in printed
    assert "guide line of the pilot sheets" not in printed
    gate = json.loads((out / "reserve_agreement.json").read_text(encoding="utf-8"))["gate"]
    assert gate["same_guide_as"] == ["check"]

    # a pilot blank that is no longer the one the submitted sheets came from: no pooling
    blank = out / "pilot_A1.csv"
    blank.write_bytes(blank.read_bytes().replace(b"Examplamine", b"Changedamine"))
    assert A.main(hand_in(out, work, "check", reading, careless)) == 1
    printed = capsys.readouterr().out
    assert "warning: the submitted pilot sheets do not validate against the blanks" in printed
    assert "NOT PASSED (undefined" in printed


def test_agree_refuses_sheets_that_do_not_validate(tmp_path: Path, capsys: Any) -> None:
    out, _ = T.drawn_folder(tmp_path)
    work = tmp_path / "work"
    args = hand_in(out, work, "pilot")
    blank = (out / "pilot_A2.csv").read_text(encoding="utf-8")
    (work / "pilot_A2.csv").write_text(T.fill(blank, times=("", "")), encoding="utf-8")
    capsys.readouterr()
    assert A.main(args) == 2
    printed = capsys.readouterr().out
    assert "error: header: give one sitting_start" in printed and "nothing was scored" in printed
    assert not (out / "submitted").exists() and not (out / "pilot_agreement.json").exists()
    assert "submitted" not in manifest_of(out)
    (work / "pilot_A2.csv").write_text(T.fill(blank), encoding="utf-8")
    swapped = ["agree", "--task", "pilot", "--dir", str(out)]
    swapped += ["--a1", str(work / "pilot_A2.csv"), "--a2", str(work / "pilot_A1.csv")]
    assert A.main(swapped) == 2
    assert "the header says pilot A2, not pilot A1" in capsys.readouterr().out
    wrong_task = ["agree", "--task", "check", "--dir", str(out)]
    wrong_task += ["--a1", str(work / "pilot_A1.csv"), "--a2", str(work / "pilot_A2.csv")]
    assert A.main(wrong_task) == 2
    assert "the header says pilot A1, not check A1" in capsys.readouterr().out
    assert not (out / "submitted").exists()


def test_agree_needs_the_blank_that_was_handed_out(tmp_path: Path, capsys: Any) -> None:
    out, _ = T.drawn_folder(tmp_path)
    work = tmp_path / "work"
    args = hand_in(out, work, "pilot")
    blank = out / "pilot_A1.csv"
    original = blank.read_bytes()
    blank.write_bytes(original.replace(b"Examplamine", b"Changedamine"))
    (work / "pilot_A1.csv").write_text(T.fill(blank.read_text(encoding="utf-8")), encoding="utf-8")
    capsys.readouterr()
    assert A.main(args) == 2
    assert "is not the blank sheet the manifest records" in capsys.readouterr().out
    blank.write_text(T.fill(original.decode("utf-8")), encoding="utf-8")  # filled in place
    in_place = ["agree", "--task", "pilot", "--dir", str(out)]
    in_place += ["--a1", str(blank), "--a2", str(work / "pilot_A2.csv")]
    assert A.main(in_place) == 2
    assert "is missing or is the file given" in capsys.readouterr().out
    blank.write_bytes(original)
    (work / "pilot_A1.csv").write_text(T.fill(original.decode("utf-8")), encoding="utf-8")
    assert A.main(args) == 0


def adjudicate(
    sheet: Path, target: Path, decide: Callable[[int, dict[str, str]], dict[str, str]]
) -> None:
    meta, rows = S.read_sheet(sheet)
    filled = [row | decide(n, row) for n, row in enumerate(rows)]
    target.write_text(S.sheet_text(A.ADJUDICATION_COLUMNS, filled, meta), encoding="utf-8")


def take_a1(n: int, row: dict[str, str]) -> dict[str, str]:
    """The adjudicator sides with A1, calls the second item a gap, and cannot settle the first."""
    if n == 0:
        return {"adj_decision": "gap", "adj_note": "no convention decides"}
    label = {c: row[f"A1_{c}"] for c in S.ENTERED}
    return label | {"adj_decision": "gap" if n == 1 else "slip", "adj_note": f"note {n}"}


def test_literal_task_from_sheets_to_gold(tmp_path: Path, capsys: Any) -> None:
    out, _ = T.drawn_folder(tmp_path)
    work = tmp_path / "work"
    gold = ["gold", "--dir", str(out), "--adjudication", str(work / "adjudicated.csv")]
    work.mkdir()
    (work / "adjudicated.csv").write_text("", encoding="utf-8")
    assert A.main(gold) == 2  # nothing was submitted yet
    assert "run agree first" in capsys.readouterr().out
    assert A.main(hand_in(out, work, "literal", reading, careless)) == 0
    assert "gate:" not in capsys.readouterr().out
    stats = json.loads((out / "literal_agreement.json").read_text(encoding="utf-8"))
    assert stats["n"] == 36 and set(stats["by_period"]) == {"train", "test"}
    assert not (out / "literal_disagreements.csv").exists()
    sheet = out / "literal_adjudication.csv"
    meta, rows = S.read_sheet(sheet)
    header = next(line for line in csv.reader(sheet.open(encoding="utf-8")) if line[0] == "item_id")
    assert tuple(header) == A.ADJUDICATION_COLUMNS
    assert dict(meta)["values of adj_decision"] == "slip | gap"
    assert len(rows) == stats["to_adjudication"] >= 3
    assert all(r["adj_decision"] == "" and r["start"] == "" and r["A1_start"] for r in rows)

    adjudicate(sheet, work / "adjudicated.csv", lambda n, row: {})
    assert A.main(gold) == 2
    printed = capsys.readouterr().out
    assert printed.count("adj_decision must be one of slip, gap") == len(rows)
    assert "no gold was written" in printed and not (out / "literal_gold.csv").exists()

    adjudicate(sheet, work / "adjudicated.csv", take_a1)
    assert A.main(gold) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["items"] == 36 and report["left_out"] == 1 and report["gold_rows"] == 35
    assert report["agree"] == 36 - len(rows) and report["gap"] == 2
    assert report["slip"] == len(rows) - 2
    assert report["decisions_by_field"]["gap"] == {"end": 2, "start": 2}
    assert report["file"] == "literal_gold.csv" and report["sha256"] == T.sha(
        out / "literal_gold.csv"
    )
    assert manifest_of(out)["gold"] == report
    copy = out / "submitted" / "literal_adjudication.csv"
    assert copy.read_bytes() == (work / "adjudicated.csv").read_bytes()
    assert report["adjudication_sha256"] == T.sha(copy)
    rows_gold = list(csv.DictReader((out / "literal_gold.csv").open(encoding="utf-8")))
    assert tuple(rows_gold[0]) == A.GOLD_COLUMNS and len(rows_gold) == 35
    assert [r["item_id"] for r in rows_gold] == sorted(r["item_id"] for r in rows_gold)
    assert rows[0]["item_id"] not in {r["item_id"] for r in rows_gold}
    assert {r["adj_decision"] for r in rows_gold} == {"agree", "slip", "gap"}
    a1 = S.check_file(out / "submitted" / "literal_A1.csv", None, out).labels
    for row in rows_gold:
        entered = a1[row["item_id"]].entered()
        assert {c: row[c] for c in ("statement_type", "start", "end", "abstain", "certainty")} == {
            c: entered[c] for c in ("statement_type", "start", "end", "abstain", "certainty")
        }
        assert len(row["start"]) in (0, 10)  # dates in full
    first = (out / "literal_gold.csv").read_bytes()
    assert A.main(gold) == 0
    assert (out / "literal_gold.csv").read_bytes() == first

    # a submitted sheet changed after agree: the gold is refused
    submitted = out / "submitted" / "literal_A2.csv"
    submitted.write_bytes(submitted.read_bytes().replace(b"09:20", b"09:21"))
    capsys.readouterr()
    assert A.main(gold) == 2
    assert "is not the sheet the manifest records" in capsys.readouterr().out


def test_a_filled_adjudication_sheet_is_not_written_over(tmp_path: Path, capsys: Any) -> None:
    out, _ = T.drawn_folder(tmp_path)
    work = tmp_path / "work"
    args = hand_in(out, work, "literal", reading, careless)
    assert A.main(args) == 0
    sheet = out / A.ADJUDICATION
    assert not A.decisions_entered(sheet) and not A.decisions_entered(out / "absent.csv")
    assert A.main(args) == 0  # nothing decided yet: the sheet may be written again
    blank = sheet.read_bytes()
    recorded = (out / "submitted" / "literal_A1.csv").read_bytes()
    for decide in (
        take_a1,
        lambda n, row: {"adj_note": "to discuss"} if n == 0 else {},
        lambda n, row: {"certainty": "asserted"} if n == 0 else {},
    ):
        adjudicate(sheet, sheet, decide)  # the adjudicator worked in place
        filled = sheet.read_bytes()
        assert A.decisions_entered(sheet)
        capsys.readouterr()
        # the second annotator sends a corrected sheet: agree must not run over the decisions
        assert A.main(hand_in(out, work, "literal", reading, reading)) == 2
        assert "holds adjudication decisions and would be overwritten" in capsys.readouterr().out
        assert sheet.read_bytes() == filled
        assert (out / "submitted" / "literal_A1.csv").read_bytes() == recorded
        sheet.write_bytes(blank)
    # the other tasks have no adjudication sheet and are not held up
    adjudicate(sheet, sheet, take_a1)
    assert A.main(hand_in(out, work, "pilot")) == 0
    # the gold reads the sheet filled in place, and one that is not UTF-8 is one clear error
    gold = ["gold", "--dir", str(out), "--adjudication"]
    capsys.readouterr()
    assert A.main([*gold, str(sheet)]) == 0
    legacy = work / "legacy.csv"
    legacy.write_bytes(sheet.read_text(encoding="utf-8").replace("note 2", "né").encode("cp1252"))
    capsys.readouterr()
    assert A.main([*gold, str(legacy)]) == 2
    assert "the file is not UTF-8 text" in capsys.readouterr().out
    sheet.write_bytes("café".encode("cp1252"))  # unreadable: counts as filled
    assert A.decisions_entered(sheet) and A.main(args) == 2


def test_validate_command_is_the_samplers(tmp_path: Path, capsys: Any) -> None:
    out, _ = T.drawn_folder(tmp_path)
    args = hand_in(out, tmp_path / "work", "pilot")
    capsys.readouterr()
    assert A.main(["validate", args[args.index("--a1") + 1], "--dir", str(out)]) == 0
    assert "12 rows, 12 valid, 0 errors" in capsys.readouterr().out
    assert A.main(["validate", str(out / "pilot_A1.csv"), "--dir", str(out)]) == 1
    assert "the row is not filled" in capsys.readouterr().out
