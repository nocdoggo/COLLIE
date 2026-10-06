"""Tests for the figures cited for the result rules (``result_rules_check.py``).

Every statistic is checked on a case small enough to work out by hand, in the comments:
calibration in the large with its interval by episode (the same as ``evaluate.calibration``
gives), its least and greatest value when events are undetermined, the two Turnbull shares, the
loss of always answering no, the difference of two predictors' losses on the scoreable
statements, under the two scenarios and by statement type, the eligible list by statement type,
the letter items of the literal sample and the certainty-marker items of the minimal pairs. The
refusals are checked one by one: an outcome cell on a row outside the train period, dev losses
from another build, an eligible list or a literal sample from another build, other counts of the
minimal pairs, a rule reader that is not the frozen one, a path in the sealed folder.

The command line runs on synthetic tables in a temporary folder. The statement table has no
chance in it, and outcomes on its train-period rows only, so the counts behind every figure are
known by hand. Two runs give the same bytes, and the output holds the ten figures, the hashes
of its inputs and of the code, and the seed.

The last test reads the files in the repository and is skipped when one is absent. It fails
until the command is rerun after any change to an input or to the code.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_result_rules_check.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from analysis.coling import dataset as D
from analysis.coling import forms as F
from analysis.coling import gbm as G
from analysis.coling import power as W
from analysis.coling import predictors as P
from analysis.coling import result_rules_check as R
from analysis.coling.test_power import iso, outcome_cells
from analysis.coling.test_predictors import censored, frame, recovered

NAN = float("nan")
FIGURES = (
    "A_base_rate_calibration_scoreable_dev",
    "B_base_rate_against_turnbull_share",
    "C_calibration_limits_dated_dev",
    "D_turnbull_shares_dev",
    "E_primary_brier_scoreable_dev",
    "F_base_rate_minus_rules_plus_slip",
    "G_turnbull_share_by_statement_type",
    "H_eligible_list_by_statement_type",
    "I_literal_sample_letter_items",
    "J_certainty_marker_minimal_pairs",
)


# --------------------------------------------------------------------------------------------
# Statistics by hand
# --------------------------------------------------------------------------------------------


def test_registered_constants() -> None:
    assert (R.SEED, R.DRAWS, R.COVERAGE, R.TEST_START) == (20261001, 10_000, 0.95, "2023-01-01")
    assert R.TYPES == F.STATEMENT_TYPES[:2] == ("recovery", "next_delivery")
    assert tuple(name for name in G.PREDICTORS if not name.startswith("gbm")) == R.PREDICTORS
    assert R.REPORT == D.OUT / "result_rules_check.json"


def test_calibration_in_the_large_by_hand() -> None:
    # Mean probability 0.35 against one yes in four (0.25): +0.10. Episode a holds the gaps
    # -0.5 and 0.5 (sum 0), episode b holds 0.2 and 0.2 (sum 0.4). A draw of two episodes takes
    # a twice (mean 0), a and b (0.1) or b twice (0.2), a quarter, a half and a quarter of the
    # draws: the 95% percentile interval runs from 0 to 0.2.
    p, y, clusters = [0.5, 0.5, 0.2, 0.2], [1.0, 0.0, 0.0, 0.0], ["a", "a", "b", "b"]
    got = R.calibration(p, y, clusters)
    assert (got["statements"], got["episodes"], got["yes"]) == (4, 2, 1)
    assert got["mean_p"] == pytest.approx(0.35) and got["frequency"] == pytest.approx(0.25)
    assert got["difference"] == pytest.approx(0.10)
    assert got["ci95"] == pytest.approx([0.0, 0.2])
    assert got == R.calibration(p, y, clusters) != R.calibration(p, y, ["a", "b", "a", "b"])


def test_calibration_agrees_with_evaluate_calibration() -> None:
    from analysis.coling import evaluate as E

    rng = np.random.default_rng(P.SEED)
    p, y = rng.random(60), (rng.random(60) < 0.3).astype(float)
    clusters = [f"e{k % 7}" for k in range(60)]
    mine, theirs = R.calibration(p, y, clusters), E.calibration(p, y, clusters, E.DRAWS, E.SEED)
    assert mine["difference"] == theirs["mean_p_minus_frequency"]
    assert mine["ci95"] == theirs["ci95"]
    assert (E.DRAWS, E.SEED) == (R.DRAWS, R.SEED)


def test_least_and_greatest_calibration_by_hand() -> None:
    # Four statements at probability 0.5: one yes, one no, two undetermined.
    # Least: the undetermined count as yes, frequency 3/4, value -0.25. Gaps: a (-0.5, -0.5),
    # b (0.5, -0.5); draws give -0.5 (a twice), -0.25 or 0 (b twice).
    # Greatest: they count as no, frequency 1/4, value +0.25. Gaps: a (-0.5, 0.5), b (0.5, 0.5);
    # draws give 0, 0.25 or 0.5.
    y, clusters = [1.0, NAN, 0.0, NAN], ["a", "a", "b", "b"]
    assert R.event_counts(y) == {"statements": 4, "yes": 1, "no": 1, "undetermined": 2}
    got = R.calibration_limits([0.5] * 4, y, clusters)
    assert got["mean_p"] == 0.5
    assert got["least"]["value"] == pytest.approx(-0.25)
    assert got["least"]["ci95"] == pytest.approx([-0.5, 0.0])
    assert got["greatest"]["value"] == pytest.approx(0.25)
    assert got["greatest"]["ci95"] == pytest.approx([0.0, 0.5])
    # A predictor that is certain of a yes: 1 minus the greatest and the least frequency.
    sure = R.calibration_limits([1.0] * 4, y, clusters)
    assert (sure["least"]["value"], sure["greatest"]["value"]) == pytest.approx((0.25, 0.75))
    # With no undetermined event the two are calibration in the large itself.
    whole = R.calibration_limits([0.5, 0.5, 0.2, 0.2], [1.0, 0.0, 0.0, 0.0], clusters)
    plain = R.calibration([0.5, 0.5, 0.2, 0.2], [1.0, 0.0, 0.0, 0.0], clusters)
    for end in ("least", "greatest"):
        assert whole[end] == {"value": plain["difference"], "ci95": plain["ci95"]}


def test_turnbull_shares_by_hand() -> None:
    # The stated end is 30 days after each statement. Recoveries in (0, 10], (20, 40] and
    # (40, 50] days and one statement still short after 200: slip in (-30, -20], (-10, 10],
    # (10, 20] and above 170. The brackets do not overlap, so each holds a quarter of the mass.
    # By the stated end: the first quarter and half of the second (spread evenly over its
    # bracket), 0.375. Within 90 days of it: three quarters.
    rows = frame([recovered(0, 10), recovered(20, 40), recovered(40, 50), censored(200)])
    got = R.turnbull_shares(rows)
    assert got["statements"] == 4
    assert got["by_stated_end"] == pytest.approx(0.375, abs=1e-6)
    assert got["within_90_days"] == pytest.approx(0.75, abs=1e-6)
    # Probabilities of mean 0.5 stand 0.125 above the share recovered by the stated end.
    against = R.against_turnbull([0.6, 0.6, 0.4, 0.4], rows)
    assert against["statements"] == 4 and against["mean_p_E_end"] == pytest.approx(0.5)
    assert against["turnbull_share_by_stated_end"] == pytest.approx(0.375, abs=1e-6)
    assert against["difference"] == pytest.approx(0.125, abs=1e-6)
    # Without the statement that straddles the stated end: one of three by the stated end.
    assert R.turnbull_shares(rows.iloc[[0, 2, 3]])["by_stated_end"] == pytest.approx(
        1 / 3, abs=1e-6
    )


def dev_case() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Four dated dev statements in two episodes, three of them scoreable, with the outputs of
    two predictors and the statement types."""
    rows = frame(
        [
            {"split": "dev", "episode_id": "e1", "y_a": 0.0, "y_b": 0.0, "scoreable": True},
            {"split": "dev", "episode_id": "e1", "y_a": 1.0, "y_b": 1.0, "scoreable": True},
            {"split": "dev", "episode_id": "e2", "y_a": 0.0, "y_b": 1.0, "scoreable": True},
            {"split": "dev", "episode_id": "e2", "y_a": 0.0, "y_b": NAN, "scoreable": False},
        ]
    )
    half = pd.DataFrame({"p_a": 0.5, "p_b": 0.5}, index=rows.index)
    late = pd.DataFrame({"p_a": 0.0, "p_b": 1.0}, index=rows.index)
    kinds = pd.Series(["recovery", "recovery", "next_delivery", "next_delivery"], index=rows.index)
    return rows, half, late, kinds


def test_always_answering_no_by_hand() -> None:
    # Primary loss at probability 0 for both events: 0 on no/no, 1 on yes/yes, 0.5 on no/yes.
    rows = dev_case()[0]
    assert R.always_no(rows[rows["scoreable"]]) == pytest.approx(0.5)
    assert np.isnan(R.always_no(rows))  # an undetermined event has no loss


def test_loss_difference_by_hand() -> None:
    # "half" says 0.5 twice: its loss is 0.25 whatever happens. "late" says no by the stated
    # end and yes by 90 days after it: 0.5 on no/no, 0.5 on yes/yes, 0 on no/yes.
    # Scoreable: (-0.25 - 0.25 + 0.25) / 3 = -1/12. Recovery statements (the first two, one
    # episode): -0.25. The next-delivery statement that is scoreable: +0.25.
    # Scenarios over all four. The fourth has E_end = no and E_end90 undetermined. As no:
    # late loses 0.5, mean (0.5 + 0.5 + 0 + 0.5) / 4 = 0.375, difference 0.25 - 0.375. As yes:
    # late loses 0, mean 0.25, difference 0.
    rows, half, late, kinds = dev_case()
    got = R.loss_difference(rows, half, late, kinds)
    assert got["scoreable"] == {"statements": 3, "episodes": 2, "delta": pytest.approx(-1 / 12)}
    assert got["scenarios_all_dated"] == {
        "statements": 4,
        "undetermined_as_no": pytest.approx(-0.125),
        "undetermined_as_yes": pytest.approx(0.0),
    }
    assert got["by_statement_type_scoreable"] == {
        "recovery": {"statements": 2, "episodes": 1, "delta": pytest.approx(-0.25)},
        "next_delivery": {"statements": 1, "episodes": 1, "delta": pytest.approx(0.25)},
    }
    # The direction is the comparator's loss minus the tested predictor's.
    back = R.loss_difference(rows, late, half, kinds)
    assert back["scoreable"]["delta"] == pytest.approx(1 / 12)
    # A type with no scoreable statement has no difference, and another type is an error.
    one = R.loss_difference(rows, half, late, kinds.replace("next_delivery", "recovery"))
    assert one["by_statement_type_scoreable"]["next_delivery"] == {
        "statements": 0,
        "episodes": 0,
        "delta": None,
    }
    with pytest.raises(ValueError, match="neither a recovery nor a next-delivery"):
        R.loss_difference(rows, half, late, kinds.replace("next_delivery", "depletion"))


def test_statements_by_type() -> None:
    rows, _, _, kinds = dev_case()
    parts = R.by_type(rows, kinds)
    assert {name: list(part.index) for name, part in parts.items()} == {
        "recovery": ["S000", "S001"],
        "next_delivery": ["S002", "S003"],
    }
    with pytest.raises(ValueError, match="neither a recovery nor a next-delivery"):
        R.by_type(rows, kinds.iloc[:3])  # a statement with no type


def test_tally_follows_the_given_order_and_refuses_other_values() -> None:
    column = pd.Series(["quarter", "month_year", "quarter"])
    assert R.tally(column, F.DATED_FORMS) == {"quarter": 2, "month_year": 1}
    assert list(R.tally(column, F.DATED_FORMS)) == ["quarter", "month_year"]  # inventory order
    with pytest.raises(ValueError, match="unexpected values"):
        R.tally(column, ("quarter",))


# --------------------------------------------------------------------------------------------
# First-sight figures by hand
# --------------------------------------------------------------------------------------------


def first_rows(rows: dict[str, dict[str, str]]) -> pd.DataFrame:
    """First-sight rows by statement id: a recovery statement with a month and its year, no
    distractor date, not stale, not eligible, in episode ``a``, unless a row says otherwise."""
    base = {
        "episode_id": "a",
        "form": "month_year",
        "distractor_dates": "0",
        "statement_type": "recovery",
        "stale_at_issue": "False",
        "e3_eligible": "False",
    }
    index = pd.Index(list(rows), name="statement_group_id")
    return pd.DataFrame([{**base, **row} for row in rows.values()], index=index)


def test_eligible_list_by_statement_type_by_hand() -> None:
    # Four eligible statements in two episodes: three recovery statements (two in a, one in
    # b) and one next-delivery statement (in b). The fifth statement is not on the list.
    yes = {"e3_eligible": "True"}
    first = first_rows(
        {
            "S1": yes,
            "S2": yes,
            "S3": {**yes, "episode_id": "b"},
            "S4": {**yes, "episode_id": "b", "statement_type": "next_delivery"},
            "S5": {"episode_id": "c", "statement_type": "next_delivery"},
        }
    )
    listed = pd.DataFrame({"statement_group_id": ["S4", "S1", "S3", "S2"]})
    assert R.eligible_by_type(listed, first) == {
        "statements": 4,
        "episodes": 2,
        "recovery": {"statements": 3, "episodes": 2},
        "next_delivery": {"statements": 1, "episodes": 1},
    }
    for other in (["S1", "S2", "S3"], ["S1", "S2", "S3", "S4", "S5"]):
        with pytest.raises(SystemExit, match=r"eligible list .* not from the same build"):
            R.eligible_by_type(pd.DataFrame({"statement_group_id": other}), first)


def test_letter_items_of_the_literal_sample_by_hand() -> None:
    # Of the five sampled statements three are letter items: L1 (a month and its year), L2 (a
    # quarter; next delivery; stale) and L3 (a day; no episode). L4 carries a distractor date
    # and L5 has no period. L6 is a letter item that was not sampled.
    first = first_rows(
        {
            "L1": {},
            "L2": {"form": "quarter", "statement_type": "next_delivery", "stale_at_issue": "True"},
            "L3": {"form": "exact_day", "episode_id": ""},
            "L4": {"distractor_dates": "1"},
            "L5": {"form": "tbd"},
            "L6": {"form": "range", "episode_id": "b"},
        }
    )
    sample = pd.DataFrame({"statement_group_id": ["L5", "L4", "L3", "L2", "L1"]})
    # The sample has two strata named after a dated form, with 2 + 1 + 1 = 4 items drawn.
    strata = pd.DataFrame(
        [
            ("literal", "month_year", "train", "2"),
            ("literal", "month_year", "test", "1"),
            ("literal", "quarter", "train", "1"),
            ("literal", "tbd", "train", "1"),
            ("literal", "dated_distractor", "train", "1"),
            ("pilot", "exact_day", "train", "5"),
        ],
        columns=["sample", "stratum", "period", "drawn"],
    )
    assert R.letter_items(sample, strata, first) == {
        "items": 5,
        "letter_items": 3,
        "episodes": 1,
        "with_no_episode": 1,
        "by_form": {"exact_day": 1, "quarter": 1, "month_year": 1},
        "of_forms_other_than_month_year": 2,
        "by_statement_type": {"recovery": 2, "next_delivery": 1},
        "stale_at_issue": 1,
        "strata_named_after_a_dated_form": 2,
        "drawn_from_those_strata": 4,
    }
    with pytest.raises(SystemExit, match="literal sample names a statement"):
        R.letter_items(pd.DataFrame({"statement_group_id": ["L1", "L9"]}), strata, first)


def pair(factor: str, level: str, availability: str, related: str = "") -> dict[str, Any]:
    """An item of the minimal pairs with the keys the figure reads."""
    return {
        "factor": factor,
        "level": level,
        "availability_information": availability,
        "related_information": related,
        "date_of_update": "2021-01-15",
    }


def pair_items() -> list[dict[str, Any]]:
    """Five items of the certainty-marker factor and two of other factors. The frozen rule
    reader finds a period (March 2021) in the texts of the last two certainty items only."""
    return [
        pair("certainty", "tbd", "Estimated Recovery: TBD"),
        pair("certainty", "no_estimated_date", "No estimated release date at this time"),
        pair("certainty", "as_released", "Product will be made available as it is released"),
        pair("certainty", "expected", "Next delivery expected March 2021"),
        pair("certainty", "estimated", "Estimated recovery: March 2021"),
        pair("silent", "silent", "On backorder", "Check wholesalers"),
        pair("seed", "unedited", "Estimated recovery: March 2021"),
    ]


def pair_counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    """The part of ``e5_counts.json`` that the figure reads."""
    levels = pd.Series([item["level"] for item in items if item["factor"] == "certainty"])
    return {"per_factor_and_level": {"certainty": levels.value_counts().to_dict()}}


def test_certainty_items_of_the_minimal_pairs_by_hand() -> None:
    items = pair_items()
    assert [R.keeps_its_date(item) for item in items[:5]] == [False, False, False, True, True]
    got = R.certainty_items(items, pair_counts(items))
    assert got["items"] == 5
    assert got["date_taken_away"] == {
        "items": 3,
        "levels": ["as_released", "no_estimated_date", "tbd"],
    }
    assert got["date_kept"] == {"items": 2, "levels": ["estimated", "expected"]}
    assert got["by_level"]["tbd"] == {"items": 1, "date_kept": 0}
    assert got["by_level"]["expected"] == {"items": 1, "date_kept": 1}
    # The reading decides, not the name of the level: a level can stand on both sides.
    mixed = [*items, pair("certainty", "tbd", "Estimated recovery: March 2021")]
    got = R.certainty_items(mixed, pair_counts(mixed))
    assert got["by_level"]["tbd"] == {"items": 2, "date_kept": 1}
    assert (got["date_taken_away"]["items"], got["date_kept"]["items"]) == (3, 3)
    assert "tbd" in got["date_taken_away"]["levels"] and "tbd" in got["date_kept"]["levels"]


def test_certainty_items_refuse_other_counts_and_another_rule_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = pair_items()
    counts = pair_counts(items)
    counts["per_factor_and_level"]["certainty"]["tbd"] = 2
    with pytest.raises(SystemExit, match=r"minimal pairs .* not from the same build"):
        R.certainty_items(items, counts)
    with pytest.raises(SystemExit, match="not from the same build"):
        R.certainty_items(items, {})
    monkeypatch.setattr(F, "RULES_SHA256", "0" * 16)
    with pytest.raises(SystemExit, match="not the frozen rule reader"):
        R.certainty_items(items, pair_counts(items))


# --------------------------------------------------------------------------------------------
# Synthetic tables
# --------------------------------------------------------------------------------------------

BRACKETS = (
    ("recovered", 0, 10),  # by the stated end: yes, yes
    ("recovered", 20, 40),  # across the stated end: undetermined, yes
    ("recovered", 40, 50),  # after it, within 90 days: no, yes
    ("recovered", 110, 130),  # across 90 days after it: no, undetermined
    ("recovered", 130, 160),  # later: no, no
    ("censored", 400, None),  # still short after 400 days: no, no
    ("censored", 20, None),  # last seen short after 20 days: undetermined twice
)
"""The outcome of statement ``k`` of the synthetic table is ``BRACKETS[k % 7]``: the bracket of
its recovery in days from the statement, and beside it the two horizon events of a dated
statement, whose stated end is 30 days after the statement."""


def synthetic_table() -> pd.DataFrame:
    """A statement table with no chance in it. Statements ``k`` = 1 to 240 are of the fit split
    (200 dated, then 20 TBD and 20 silent), 241 to 360 are dated dev statements and 361 to 420
    dated test statements, which are the eligible list. Train-period rows have the outcome
    ``BRACKETS[k % 7]``; test rows have none. Statement ``k`` is in episode ``k % 9`` and is a
    next-delivery statement when 3 divides ``k``, so an episode holds one statement type."""
    plan = [("fit", "dated", 200), ("fit", "tbd", 20), ("fit", "silent", 20)]
    plan += [("dev", "dated", 120), ("test", "dated", 60)]
    start = {"fit": date(2020, 1, 1), "dev": date(2021, 1, 1), "test": date(2024, 1, 1)}
    rows, k = [], 0
    for split, kind, count in plan:
        for _ in range(count):
            k += 1
            day = start[split] + timedelta(days=k % 300)
            dated = kind == "dated"
            end = iso(day, 30) if dated else ""
            row = {
                "statement_group_id": f"S{k:04d}",
                "event_id": f"E{k:04d}",
                "episode_id": f"drug{k % 9}@2019-10-20",
                "period": "test" if split == "test" else "train",
                "split": split,
                "event_date": day.isoformat(),
                "at_risk_B": "True",
                "revision": D.REVISION_BUCKETS[k % 3],
                "listing_age_days": "" if k % 10 == 0 else str(100 * (k % 11)),
                "form": "month_year" if dated else kind,
                "merged_form": "month_year" if dated else kind,
                "distractor_dates": "0",
                "statement_type": "next_delivery" if k % 3 == 0 else "recovery",
                "stated_end": end,
                "stale_at_issue": "False",
                "analysis_set": kind,
                "horizon_a": end if dated else iso(day, 90),
                "horizon_b": iso(day, 120) if dated else iso(day, 180),
                "e3_eligible": str(split == "test"),
            }
            if split != "test":
                row.update(outcome_cells(row, *BRACKETS[k % 7]))
            rows.append({**dict.fromkeys(D.COLUMNS, ""), **row})
    table = pd.DataFrame(rows, columns=list(D.COLUMNS)).astype(str)
    by_id = table["statement_group_id"]
    table.loc[by_id == "S0002", "form"] = "quarter"
    table.loc[by_id == "S0003", "distractor_dates"] = "1"
    table.loc[by_id == "S0361", "stale_at_issue"] = "True"
    return table


SAMPLED = ("S0001", "S0002", "S0003", "S0201", "S0361", "S0363")
"""The literal sample of the synthetic table: three dated fit statements (the second a quarter,
the third with a distractor date), a TBD statement and two test-period statements (the first
stale at issue, the second a next-delivery statement)."""
STRATA = (
    "sample,stratum,period,pool,available,quota,drawn\n"
    "literal,month_year,train,200,200,2,2\n"
    "literal,quarter,train,1,1,1,1\n"
    "literal,month_year,test,60,60,2,2\n"
    "literal,tbd,train,20,20,1,1\n"
)


def dev_losses_of(table: pd.DataFrame) -> dict[str, Any]:
    """What ``dev_losses.json`` holds of the three predictors for this table, as it reads back
    from the file, with a further predictor and a contrast that the check must leave aside."""
    _, dev, predictions = R.fit_and_predict(P.prepare(R.train_rows(table)))
    record = json.loads(W.report_text(W.loss_report(dev, predictions)))
    record["losses"]["gbm_text"] = {"primary_brier": 0.2}
    record["contrasts"].append({"comparator": "base_rate", "tested": "gbm_text", "delta": 0.1})
    return record


def write_inputs(folder: Path, table: pd.DataFrame) -> dict[str, Path]:
    """The seven inputs of the command in ``folder``, by their name in ``INPUTS``."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = {name: folder / default.name for name, (default, _) in R.INPUTS.items()}
    table.to_csv(paths["statements"], index=False, compression=dict(F.GZIP))
    table.loc[table["e3_eligible"] == "True", ["statement_group_id", "episode_id"]].to_csv(
        paths["eligible_e3"], index=False
    )
    paths["dev_losses"].write_text(json.dumps(dev_losses_of(table)), encoding="utf-8")
    pd.DataFrame({"statement_group_id": SAMPLED}).to_csv(paths["sample_literal"], index=False)
    paths["strata"].write_text(STRATA, encoding="utf-8")
    paths["e5_pairs"].write_text(D.jsonl(pair_items()), encoding="utf-8")
    paths["e5_counts"].write_text(json.dumps(pair_counts(pair_items())), encoding="utf-8")
    return paths


def arguments(paths: dict[str, Path], out: Path) -> list[str]:
    """The command line that names every input and the output."""
    named = [(f"--{name.replace('_', '-')}", str(path)) for name, path in paths.items()]
    return [part for flag in named for part in flag] + ["--out", str(out)]


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return synthetic_table()


@pytest.fixture(scope="module")
def paths(table: pd.DataFrame, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return write_inputs(tmp_path_factory.mktemp("tables"), table)


@pytest.fixture(scope="module")
def written(paths: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The output of one run of the command on the synthetic tables."""
    out = tmp_path_factory.mktemp("out") / "result_rules_check.json"
    assert R.main(arguments(paths, out)) == 0
    return out


def test_synthetic_table_by_hand(table: pd.DataFrame) -> None:
    # Dev statements are k = 241 to 360, and 241 = 7 * 34 + 3: each of the seven outcomes 17
    # times, and the fourth (no, undetermined) once more.
    D.assert_sealed(table)
    assert table["split"].value_counts().to_dict() == {"fit": 240, "dev": 120, "test": 60}
    assert (table.loc[table["period"] == "test", list(D.OUTCOME_COLUMNS)] == "").all().all()
    dev = table[table["split"] == "dev"]
    assert dev["E_end"].value_counts().to_dict() == {"no": 69, "undetermined": 34, "yes": 17}
    assert dev["E_end90"].value_counts().to_dict() == {"yes": 51, "undetermined": 35, "no": 34}
    assert (dev["scoreable"] == "True").sum() == 68
    assert W.outcome_mix(W.dev_rows(P.prepare(R.train_rows(table))).query("scoreable")) == {
        "no/no": 34,
        "no/yes": 17,
        "yes/yes": 17,
    }


# --------------------------------------------------------------------------------------------
# Rows: the refusal of a test-period outcome
# --------------------------------------------------------------------------------------------


def test_train_rows_are_the_statements_dated_before_2023(table: pd.DataFrame) -> None:
    train = R.train_rows(table)
    assert len(train) == 360 and set(train["split"]) == {"fit", "dev"}
    assert (train["event_date"] < "2023-01-01").all() and (train["outcome"] != "").all()
    first = R.first_sight(table)
    assert len(first) == 420 and first.index.name == "statement_group_id"
    assert not set(first.columns) & set(D.OUTCOME_COLUMNS)  # no outcome column of any row
    assert set(first.columns) | {"statement_group_id"} == set(D.FIRST_SIGHT_COLUMNS)


@pytest.mark.parametrize("column", ["outcome", "E_end", "upper_date_any", "ttr_mid_days"])
def test_an_outcome_cell_on_a_test_period_row_is_refused(table: pd.DataFrame, column: str) -> None:
    leaked = table.copy()
    row = leaked.index[leaked["period"] == "test"][0]
    leaked.loc[row, column] = "no"
    with pytest.raises(SystemExit, match="outcome cell on 1 of its rows dated 2023-01-01") as stop:
        R.train_rows(leaked)
    assert str(stop.value).startswith("refused: ") and "\n" not in str(stop.value)
    assert stop.value.code not in (0, None)  # a sentence: the interpreter exits with status 1
    with pytest.raises(SystemExit, match="outcome cell"):
        R.build(leaked, *[None] * 6)  # refused before anything else is used


def test_the_refusal_goes_by_the_date_and_by_the_period(table: pd.DataFrame) -> None:
    # A row marked train but dated in the test period, with its outcome: refused by the date.
    by_date = table.copy()
    row = by_date.index[by_date["split"] == "dev"][0]
    by_date.loc[row, "event_date"] = "2023-01-01"
    with pytest.raises(SystemExit, match="outcome cell on 1 of its rows"):
        R.train_rows(by_date)
    # A row dated before 2023 but marked as of the test period: refused by the period.
    by_period = table.copy()
    by_period.loc[row, "period"] = "test"
    with pytest.raises(SystemExit, match="outcome cell on 1 of its rows"):
        R.train_rows(by_period)
    # Two rows are counted as two, and the last train day keeps its outcome.
    by_period.loc[by_period.index[by_period["period"] == "test"][-1], "outcome"] = "censored"
    with pytest.raises(SystemExit, match="outcome cell on 2 of its rows"):
        R.train_rows(by_period)
    edge = table.copy()
    edge.loc[row, "event_date"] = "2022-12-31"
    assert len(R.train_rows(edge)) == 360


# --------------------------------------------------------------------------------------------
# The same build as the dev losses on disk
# --------------------------------------------------------------------------------------------


def test_same_build_compares_what_the_two_share(table: pd.DataFrame) -> None:
    _, dev, predictions = R.fit_and_predict(P.prepare(R.train_rows(table)))
    report = W.loss_report(dev, predictions)
    recorded = dev_losses_of(table)
    assert list(report["losses"]) == list(R.PREDICTORS)
    assert R.same_build(recorded, report)  # the further predictor and its contrast are left aside
    for part, key in (("dev", "scoreable_statements"), ("bootstrap", "draws")):
        other = json.loads(json.dumps(recorded))
        other[part][key] += 1
        assert not R.same_build(other, report)
    other = json.loads(json.dumps(recorded))
    other["losses"]["rules_plus_slip"]["primary_brier"] += 0.000001
    assert not R.same_build(other, report)
    other = json.loads(json.dumps(recorded))
    other["contrasts"][0]["delta"] += 0.000001
    assert not R.same_build(other, report)
    other = json.loads(json.dumps(recorded))
    del other["losses"]["face_value"]
    assert not R.same_build(other, report)
    assert not R.same_build({}, report)


def test_dev_losses_from_another_build_are_refused(table: pd.DataFrame) -> None:
    recorded = dev_losses_of(table)
    recorded["losses"]["base_rate"]["mean_p_E_end"] += 0.01
    kinds = R.first_sight(table)["statement_type"]
    with pytest.raises(SystemExit, match=r"dev losses on disk .* not from the same build"):
        R.dev_figures(P.prepare(R.train_rows(table)), kinds, recorded)


# --------------------------------------------------------------------------------------------
# The command line on the synthetic tables
# --------------------------------------------------------------------------------------------


def floats(value: Any) -> list[float]:
    if isinstance(value, dict):
        return [x for item in value.values() for x in floats(item)]
    if isinstance(value, list):
        return [x for item in value for x in floats(item)]
    return [value] if isinstance(value, float) else []


def test_the_output_records_its_inputs_the_code_and_the_seed(
    paths: dict[str, Path], written: Path
) -> None:
    report = json.loads(written.read_text(encoding="utf-8"))
    assert list(report) == ["about", "command", "inputs", "parameters", *FIGURES]
    assert report["command"] == R.COMMAND and "no sealed file" in report["about"]
    expected = {f"{name}_sha256": D.sha16(path.read_bytes()) for name, path in paths.items()}
    assert report["inputs"] == {**expected, **R.code_record()}
    assert report["inputs"]["result_rules_check_sha256"] == D.sha16(Path(R.__file__).read_bytes())
    assert report["inputs"]["predictors_sha256"] == D.sha16(Path(P.__file__).read_bytes())
    assert all(len(value) == 16 for value in report["inputs"].values())
    assert report["parameters"] == {
        "seed": 20261001,
        "draws": 10_000,
        "interval": "95% percentile, by shortage episode",
        "outcome_cells_used_on_statements_dated_before": "2023-01-01",
    }
    assert all(round(x, 6) == x for x in floats(report)) and len(floats(report)) > 30


def test_the_figures_of_the_synthetic_tables(
    table: pd.DataFrame, paths: dict[str, Path], written: Path
) -> None:
    # The counts are those of ``test_synthetic_table_by_hand``: of the 120 dated dev statements
    # 17 recovered by the stated end, 34 have that event undetermined and 68 are scoreable.
    report = json.loads(written.read_text(encoding="utf-8"))
    recorded = json.loads(paths["dev_losses"].read_text(encoding="utf-8"))["losses"]
    a = report["A_base_rate_calibration_scoreable_dev"]
    assert (a["event"], a["statements"], a["episodes"], a["yes"]) == ("E_end", 68, 9, 17)
    assert a["frequency"] == 0.25 and a["mean_p"] == recorded["base_rate"]["mean_p_E_end"]
    assert a["difference"] == pytest.approx(a["mean_p"] - 0.25, abs=2e-6)
    assert a["ci95"][0] <= a["difference"] <= a["ci95"][1]
    b = report["B_base_rate_against_turnbull_share"]
    assert (b["dev"]["statements"], b["fit"]["statements"]) == (120, 200)
    for split in ("dev", "fit"):
        gap = b[split]["mean_p_E_end"] - b[split]["turnbull_share_by_stated_end"]
        assert b[split]["difference"] == pytest.approx(gap, abs=2e-6)
    # The fit mean is that of P(E_end), read on the dated fit statements by the table fitted on
    # the fit split.
    frame = P.prepare(R.train_rows(table))
    fit, dev = frame[frame["split"] == "fit"], W.dev_rows(frame)
    base_rate = P.fit_base_rate(fit)
    on_fit = base_rate.predict(fit[fit["analysis_set"] == "dated"])
    assert b["fit"]["mean_p_E_end"] == pytest.approx(on_fit["p_a"].mean(), abs=2e-6)
    assert on_fit["p_a"].mean() < on_fit["p_b"].mean() - 0.01
    c = report["C_calibration_limits_dated_dev"]
    counts = {key: c[key] for key in ("event", "statements", "yes", "no", "undetermined")}
    assert counts == {"event": "E_end", "statements": 120, "yes": 17, "no": 69, "undetermined": 34}
    assert c["episodes"] == 9
    # Face value says 1. Least: 1 - (17 + 34) / 120. Greatest: 1 - 17 / 120.
    face, base = c["face_value"], c["base_rate"]
    assert (face["mean_p"], face["least"]["value"], face["greatest"]["value"]) == (
        1.0,
        0.575,
        0.858333,
    )
    assert base["mean_p"] == b["dev"]["mean_p_E_end"]
    assert base["least"]["value"] == pytest.approx(base["mean_p"] - 51 / 120, abs=2e-6)
    assert base["greatest"]["value"] == pytest.approx(base["mean_p"] - 17 / 120, abs=2e-6)
    for end in ("least", "greatest"):
        assert base[end]["ci95"][0] <= base[end]["value"] <= base[end]["ci95"][1]
    # The intervals are by episode: the nine episodes are drawn, not the 120 statements.
    for name, p in (("face_value", 1.0), ("base_rate", base_rate.predict(dev)["p_a"])):
        for end, value in (("least", 1.0), ("greatest", 0.0)):
            gap = (p - dev["y_a"].fillna(value)).to_numpy()
            draws = P.bootstrap_means(gap, list(dev["episode_id"]))[:, 0]
            assert c[name][end]["ci95"] == pytest.approx(P.interval(draws), abs=2e-6)
            apart = P.bootstrap_means(gap, list(dev.index))[:, 0]
            assert c[name][end]["ci95"] != pytest.approx(P.interval(apart), abs=2e-6)
    # The scoreable statements have four outcomes, 17 each, with slip in (-30, -20], (10, 20],
    # (100, 130] and above 370: a quarter by the stated end, a half within 90 days of it.
    d = report["D_turnbull_shares_dev"]
    assert d["scoreable"] == {"statements": 68, "by_stated_end": 0.25, "within_90_days": 0.5}
    assert d["dated"]["statements"] == 120
    assert d["dated"]["by_stated_end"] == b["dev"]["turnbull_share_by_stated_end"]
    assert d["dated"]["by_stated_end"] < d["dated"]["within_90_days"] < 1
    # Always no: 17 statements lose 1 (yes, yes), 17 lose 0.5 (no, yes) and 34 nothing.
    e = report["E_primary_brier_scoreable_dev"]
    assert e["statements"] == 68
    assert e["by_E_end_and_E_end90"] == {"no/no": 34, "no/yes": 17, "yes/yes": 17}
    assert e["always_no"] == 0.375
    assert e["base_rate"] == pytest.approx(recorded["base_rate"]["primary_brier"], abs=2e-6)
    f = report["F_base_rate_minus_rules_plus_slip"]
    delta = recorded["base_rate"]["primary_brier"] - recorded["rules_plus_slip"]["primary_brier"]
    assert f["scoreable"]["statements"] == 68 and f["scoreable"]["episodes"] == 9
    assert f["scoreable"]["delta"] == pytest.approx(delta, abs=2e-6)
    assert f["scenarios_all_dated"]["statements"] == 120
    for scenario in ("undetermined_as_no", "undetermined_as_yes"):
        base, rules = (
            recorded[name]["bounds_all_dated"][scenario]
            for name in ("base_rate", "rules_plus_slip")
        )
        assert f["scenarios_all_dated"][scenario] == pytest.approx(base - rules, abs=2e-6)
    # A scoreable dev statement is a next-delivery statement when k is 0, 9, 12 or 18 modulo
    # 21: 23 of the 68, in the three episodes whose number 3 divides.
    by_type = f["by_statement_type_scoreable"]
    assert {name: (part["statements"], part["episodes"]) for name, part in by_type.items()} == {
        "recovery": (45, 6),
        "next_delivery": (23, 3),
    }
    weighted = sum(part["statements"] * part["delta"] for part in by_type.values())
    assert weighted / 68 == pytest.approx(f["scoreable"]["delta"], abs=2e-6)
    # Every third statement is a next-delivery statement: 66 of 200 and 40 of 120.
    g = report["G_turnbull_share_by_statement_type"]
    assert {
        split: {name: part["statements"] for name, part in g[split].items()} for split in g
    } == {
        "fit": {"recovery": 134, "next_delivery": 66},
        "dev": {"recovery": 80, "next_delivery": 40},
    }
    assert report["H_eligible_list_by_statement_type"] == {
        "statements": 60,
        "episodes": 9,
        "recovery": {"statements": 40, "episodes": 6},
        "next_delivery": {"statements": 20, "episodes": 3},
    }
    # The literal sample: S0003 carries a distractor date and S0201 is a TBD statement. The
    # four letter items are statements 1, 2, 361 and 363, in episodes 1, 2, 1 and 3.
    assert report["I_literal_sample_letter_items"] == {
        "items": 6,
        "letter_items": 4,
        "episodes": 3,
        "with_no_episode": 0,
        "by_form": {"quarter": 1, "month_year": 3},
        "of_forms_other_than_month_year": 1,
        "by_statement_type": {"recovery": 3, "next_delivery": 1},
        "stale_at_issue": 1,
        "strata_named_after_a_dated_form": 2,
        "drawn_from_those_strata": 5,
    }
    j = report["J_certainty_marker_minimal_pairs"]
    assert (j["items"], j["date_taken_away"]["items"], j["date_kept"]["items"]) == (5, 3, 2)


def test_two_runs_give_the_same_bytes(
    table: pd.DataFrame,
    paths: dict[str, Path],
    written: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    again = tmp_path / "again.json"
    assert R.main(arguments(paths, again)) == 0
    printed = capsys.readouterr().out
    assert again.read_bytes() == written.read_bytes()
    assert again.read_bytes().endswith(b"}\n")
    assert printed.count("\n") == len(FIGURES) + 1 and f"wrote {again.as_posix()}" in printed
    # The same tables written to another folder give the same bytes: no path is recorded.
    elsewhere = tmp_path / "elsewhere.json"
    assert R.main(arguments(write_inputs(tmp_path / "copy", table), elsewhere)) == 0
    assert elsewhere.read_bytes() == written.read_bytes()


def test_check_compares_with_a_fresh_run_and_writes_nothing(
    table: pd.DataFrame, written: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mine = write_inputs(tmp_path / "tables", table)
    out = tmp_path / "out.json"
    assert R.main([*arguments(mine, out), "--check"]) == 1 and not out.exists()
    assert "differs from a fresh run" in capsys.readouterr().out
    out.write_bytes(written.read_bytes())
    assert R.main([*arguments(mine, out), "--check"]) == 0
    assert capsys.readouterr().out.strip() == "up to date"
    # An input that changes makes the output stale, also where no figure moves: its hash.
    mine["strata"].write_text(STRATA + "pilot,quarter,train,1,1,1,1\n", encoding="utf-8")
    assert R.main([*arguments(mine, out), "--check"]) == 1
    assert out.read_bytes() == written.read_bytes()


def test_the_command_refuses_and_writes_nothing(
    table: pd.DataFrame, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out.json"
    # A test-period outcome cell in the statement table.
    leaked = table.copy()
    leaked.loc[leaked.index[leaked["period"] == "test"][0], "E_end90"] = "yes"
    mine = write_inputs(tmp_path / "leaked", table)
    leaked.to_csv(mine["statements"], index=False, compression=dict(F.GZIP))
    with pytest.raises(SystemExit, match="refused: the statement table has an outcome") as stop:
        R.main(arguments(mine, out))
    assert stop.value.code not in (0, None) and not out.exists()
    # Dev losses of another build.
    mine = write_inputs(tmp_path / "other", table)
    recorded = json.loads(mine["dev_losses"].read_text(encoding="utf-8"))
    recorded["dev"]["dated_statements"] += 1
    mine["dev_losses"].write_text(json.dumps(recorded), encoding="utf-8")
    with pytest.raises(SystemExit, match="refused: the dev losses on disk"):
        R.main(arguments(mine, out))
    # An eligible list of another build.
    mine = write_inputs(tmp_path / "listed", table)
    mine["eligible_e3"].write_text("statement_group_id,episode_id\nS0361,x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="refused: the eligible list"):
        R.main(arguments(mine, out))
    assert not out.exists() and capsys.readouterr().out == ""
    # An input or an output in the sealed folder.
    mine = write_inputs(tmp_path / "plain", table)
    with pytest.raises(SystemExit, match="sealed"):
        R.main(arguments(mine, tmp_path / "sealed" / "out.json"))
    with pytest.raises(SystemExit, match="sealed"):
        R.main(arguments({**mine, "e5_pairs": tmp_path / "sealed" / "pairs.jsonl"}, out))
    assert not out.exists() and not (tmp_path / "sealed").exists()


# --------------------------------------------------------------------------------------------
# The file in the repository
# --------------------------------------------------------------------------------------------


def test_output_is_up_to_date(capsys: pytest.CaptureFixture[str]) -> None:
    inputs = {name: path for name, (path, _) in R.INPUTS.items()}
    if not all(path.exists() for path in (*inputs.values(), R.REPORT)):
        pytest.skip("the output or one of its tables is not in this checkout")
    report = json.loads(R.REPORT.read_text(encoding="utf-8"))
    expected = {f"{name}_sha256": D.sha16(path.read_bytes()) for name, path in inputs.items()}
    expected.update(R.code_record())
    stale = {key for key, value in expected.items() if report["inputs"].get(key) != value}
    assert not stale, f"{R.REPORT}: rerun `{R.COMMAND}` ({sorted(stale)} changed)"
    assert list(report)[4:] == list(FIGURES) and report["parameters"]["seed"] == P.SEED
    # The figures themselves, computed again from the tables.
    assert R.main(["--check"]) == 0, f"{R.REPORT}: rerun `{R.COMMAND}`"
    assert capsys.readouterr().out.strip() == "up to date"
