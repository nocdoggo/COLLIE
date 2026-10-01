"""Tests for the dev losses and the power estimate (``power.py``).

The estimators are checked on inputs small enough to work out by hand (the clustered variance,
the design effect and the correlation it implies, with episodes of equal and of unequal size, the
scaled standard error, the critical values, the minimum detectable difference, the dev rows, the
dev losses, and a contrast with its direction, its intervals and its p-values from draws of
episodes). The pipeline runs on
a synthetic statement table in the schema of ``dataset.py``, with outcomes for its train-period
rows only: the two reports are reproducible, hold what the plan asks for, and are refused when a
test-period outcome is present or when the table and the counts are not from the same build.
The command line is checked for reproducible files, ``--check`` and the refusal of the sealed
folder.

The last test reads the files in the repository and is skipped when they are absent. It fails
until the power command is rerun after any change to its inputs or to the three modules.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_power.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from analysis.coling import dataset as D
from analysis.coling import gbm as G
from analysis.coling import power as W
from analysis.coling import predictors as P
from analysis.coling.test_predictors import frame

NAN = float("nan")


# --------------------------------------------------------------------------------------------
# A synthetic statement table
# --------------------------------------------------------------------------------------------


def iso(day: date, days: float) -> str:
    return (day + timedelta(days=int(days))).isoformat()


def outcome_cells(row: dict[str, str], kind: str, lower: int, upper: int | None) -> dict[str, str]:
    """The outcome cells of a train row, by the rules of ``dataset.py``."""
    day = date.fromisoformat(row["event_date"])
    low, high = iso(day, lower), "" if upper is None else iso(day, upper)
    first = D.horizon_event(kind, low, high, row["horizon_a"])
    second = D.horizon_event(kind, low, high, row["horizon_b"])
    target = D.time_target(kind, lower, upper)
    cells = {
        "outcome": kind,
        "lower_date": low,
        "upper_date": high,
        "lower_days": str(lower),
        "upper_days": "" if upper is None else str(upper),
        "ttr_kind": target["kind"],
        **{f"ttr_{key}_days": D.number(target[key]) for key in ("lower", "upper", "mid")},
    }
    if row["analysis_set"] == "dated":
        cells.update(E_end=first, E_end90=second, scoreable=str(D.determined(first, second)))
    else:
        cells.update(E_90=first, E_180=second, scoreable_fallback=str(D.determined(first, second)))
    return cells


def synthetic_table(seed: int = P.SEED) -> pd.DataFrame:
    """240 fit statements (200 dated, 20 TBD, 20 silent), 120 dated dev statements and 60 dated
    test statements. "Fast Co" writes "resupply expected soon" and mostly recovers within weeks;
    "Slow Co" writes "no release date at this time" and mostly recovers late or not at all.
    Train rows have outcomes; test rows have none."""
    rng = np.random.default_rng(seed)
    plan = [("fit", "dated", 200), ("fit", "tbd", 20), ("fit", "silent", 20)]
    plan += [("dev", "dated", 120), ("test", "dated", 60)]
    start = {"fit": date(2020, 1, 1), "dev": date(2021, 1, 1), "test": date(2024, 1, 1)}
    rows, k = [], 0
    for split, kind_of_set, count in plan:
        for _ in range(count):
            k += 1
            fast = k % 2 == 0
            day = start[split] + timedelta(days=int(rng.integers(0, 300)))
            dated = kind_of_set == "dated"
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
                "company_name": "Fast Co" if fast else "Slow Co",
                "therapeutic_category": "Anesthesia" if k % 3 else "Oncology",
                "listing_age_days": "" if k % 10 == 0 else str(int(rng.integers(0, 2500))),
                "reason_for_shortage": "Demand increase for the drug" if k % 4 else "Other",
                "availability_text": (
                    "resupply expected soon" if fast else "no release date at this time"
                ),
                "related_text": "check wholesalers" if k % 5 == 0 else "",
                "merged_form": "month_year" if dated else kind_of_set,
                "stated_end": end,
                "analysis_set": kind_of_set,
                "horizon_a": end if dated else iso(day, 90),
                "horizon_b": iso(day, 120) if dated else iso(day, 180),
            }
            if split != "test":
                quick = fast != (rng.random() < 0.2)  # one in five goes the other way
                if quick:
                    lower = int(rng.integers(0, 45))
                    row.update(outcome_cells(row, "recovered", lower, lower + 8))
                elif rng.random() < 0.6:
                    lower = int(rng.integers(130, 300))
                    row.update(outcome_cells(row, "recovered", lower, lower + 30))
                else:
                    row.update(outcome_cells(row, "censored", 400, None))
            rows.append({**dict.fromkeys(D.COLUMNS, ""), **row})
    return pd.DataFrame(rows, columns=list(D.COLUMNS)).astype(str)


def eligible_of(table: pd.DataFrame) -> pd.DataFrame:
    return table.loc[table["split"] == "test", ["statement_group_id", "episode_id"]]


def counts_of(table: pd.DataFrame) -> dict[str, Any]:
    """The parts of ``dataset_counts.json`` that the power code reads."""
    test = eligible_of(table)
    train = {}
    for split in ("fit", "dev"):
        dated = table[(table["split"] == split) & (table["analysis_set"] == "dated")]
        scoreable = int((dated["scoreable"] == "True").sum())
        train[split] = {"dated": {"statements": len(dated), "scoreable": scoreable}}
    return {
        "e3": {"statements": len(test), "episodes": int(test["episode_id"].nunique())},
        "dev_scoreable": {"statements": train["dev"]["dated"]["scoreable"]},
        "train": train,
    }


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return synthetic_table()


@pytest.fixture(scope="module")
def built(table: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    return W.build(table, counts_of(table), eligible_of(table), draws=500, min_cell=50)


# --------------------------------------------------------------------------------------------
# The pairs and the estimators
# --------------------------------------------------------------------------------------------


def test_one_proxy_pair_per_hypothesis_from_the_model_free_predictors() -> None:
    assert [p.hypothesis for p in W.PROXY_PAIRS] == ["H1", "H2", "H3"]
    assert [p.sides for p in W.PROXY_PAIRS] == [1, 2, 2]
    assert [(p.comparator, p.tested) for p in W.PROXY_PAIRS] == [
        ("face_value", "rules_plus_slip"),
        ("rules_plus_slip", "base_rate"),
        ("gbm_structured", "gbm_text"),
    ]
    for pair in W.PROXY_PAIRS:
        assert {pair.comparator, pair.tested} <= set(G.PREDICTORS)


def test_contrast_pairs_put_the_registered_ones_first() -> None:
    pairs = W.contrast_pairs(list(G.PREDICTORS))
    assert pairs[:4] == [
        ("face_value", "rules_plus_slip"),
        ("rules_plus_slip", "base_rate"),
        ("gbm_structured", "gbm_text"),
        ("gbm_structured", "rules_plus_slip"),
    ]
    assert len(pairs) == 10 and len({frozenset(pair) for pair in pairs}) == 10
    assert W.contrast_pairs(["base_rate", "face_value"]) == [("base_rate", "face_value")]


def test_critical_values_at_the_holm_worst_case() -> None:
    alpha = 0.05 / 6
    assert W.critical_value(1) == pytest.approx(norm.ppf(1 - alpha) + norm.ppf(0.8))
    assert W.critical_value(2) == pytest.approx(norm.ppf(1 - alpha / 2) + norm.ppf(0.8))
    assert W.critical_value(1) == pytest.approx(3.2356, abs=1e-3)
    assert W.critical_value(2) == pytest.approx(3.4799, abs=1e-3)


def test_clustered_variance_by_hand() -> None:
    # d = 1, 1 in episode a and 0, 0 in episode b. Mean 0.5; sd = sqrt(4 * 0.25 / 3).
    # Episode sums of d - mean: +1 and -1. se = sqrt(2 / 1 * 2) / 4 = 0.5.
    # Design effect 0.25 / (1/3 / 4) = 3; m = (4 + 4) / 4 = 2; icc = (3 - 1) / (2 - 1) = 2,
    # kept at 1.
    v = W.clustered_variance([1.0, 1.0, 0.0, 0.0], ["a", "a", "b", "b"])
    assert v["delta"] == pytest.approx(0.5) and v["sd"] == pytest.approx(np.sqrt(1 / 3))
    assert v["se_clustered"] == pytest.approx(0.5)
    assert v["design_effect"] == pytest.approx(3.0) and v["icc"] == 1.0
    # The same values spread over both episodes: the episode sums are 0, so no variance between
    # episodes, a design effect of 0 and a correlation kept at 0.
    v = W.clustered_variance([1.0, 0.0, 1.0, 0.0], ["a", "a", "b", "b"])
    assert v["se_clustered"] == 0.0 and v["design_effect"] == 0.0 and v["icc"] == 0.0
    # One statement per episode: sqrt(4 / 3 * 4 * 0.25) / 4 = sd / sqrt(n).
    v = W.clustered_variance([1.0, 0.0, 1.0, 0.0], ["a", "b", "c", "d"])
    assert v["se_clustered"] == pytest.approx(np.sqrt(1 / 3) / 2)
    assert v["design_effect"] == pytest.approx(1.0) and v["icc"] == 0.0
    with pytest.raises(ValueError, match="at least two clusters"):
        W.clustered_variance([1.0, 0.0], ["a", "a"])


def test_within_episode_correlation_uses_the_size_weighted_episode_size() -> None:
    # d = 1, 1, 1 in episode a and 0 in episode b. Mean 0.75; sd = sqrt(0.75 / 3) = 0.5.
    # Episode sums of d - mean: +0.75 and -0.75. se = sqrt(2 * 2 * 0.5625) / 4 = 0.375.
    # Design effect 0.375^2 / (0.25 / 4) = 2.25. The size-weighted episode size is
    # (9 + 1) / 4 = 2.5, so icc = 1.25 / 1.5 = 5/6 (with the plain mean size, 2, it would be
    # 1.25 and kept at 1).
    v = W.clustered_variance([1.0, 1.0, 1.0, 0.0], ["a", "a", "a", "b"])
    assert (v["delta"], v["sd"], v["se_clustered"]) == pytest.approx((0.75, 0.5, 0.375))
    assert v["design_effect"] == pytest.approx(2.25) and v["icc"] == pytest.approx(5 / 6)
    # Scaled back to the same four statements in the same episodes it returns the same error.
    assert W.scaled_se(v["sd"], v["icc"], 4, 2.5) == pytest.approx(v["se_clustered"])


def test_scaled_standard_error_and_cluster_size() -> None:
    assert W.weighted_cluster_size(["a", "a", "a", "b"]) == pytest.approx((9 + 1) / 4)
    assert W.scaled_se(1.0, 0.0, 100, 7.0) == pytest.approx(0.1)  # no correlation: sd / sqrt(n)
    assert W.scaled_se(1.0, 0.5, 100, 3.0) == pytest.approx(np.sqrt(2 / 100))
    assert W.scaled_se(2.0, 1.0, 100, 4.0) == pytest.approx(2 * np.sqrt(4 / 100))
    assert W.scaled_se(1.0, 0.5, 100, 0.4) == pytest.approx(0.1)  # a size below 1 counts as 1


def test_target_counts() -> None:
    eligible = pd.DataFrame({"episode_id": ["a", "a", "a", "b", "c", "c"]})
    counts = {"e3": {"statements": 6, "episodes": 3}}
    got = W.target_counts(counts, eligible)
    assert (got["statements"], got["episodes"]) == (6, 3)
    assert got["weighted_statements_per_episode"] == pytest.approx((9 + 1 + 4) / 6)
    assert "upper bound" in got["basis"]
    # Registered scoreable numbers: the weighted size shrinks with the scoreable share.
    got = W.target_counts(counts, eligible, statements=3, episodes=2)
    assert (got["statements"], got["episodes"]) == (3, 2)
    assert got["weighted_statements_per_episode"] == pytest.approx((14 / 6) / 2)
    assert (got["eligible_statements"], got["eligible_episodes"]) == (6, 3)
    assert got["basis"].endswith("from the command line")
    named = W.target_counts(counts, eligible, statements=3, episodes=2, source="x.json")
    assert named["basis"].endswith("from x.json")
    with pytest.raises(ValueError, match="not from the same build"):
        W.target_counts({"e3": {"statements": 7, "episodes": 3}}, eligible)
    for statements, episodes in ((3, None), (None, 2), (7, 2), (0, 2), (3, 4), (3, 1)):
        with pytest.raises(ValueError, match="scoreable"):
            W.target_counts(counts, eligible, statements=statements, episodes=episodes)


def test_registered_scoreable_numbers_from_the_counts_only_record() -> None:
    block = {"eligible_statements": 60, "scoreable_statements": 41, "scoreable_episodes": 7}
    assert W.registered_scoreable({"e3_eligible_test": block}) == (41, 7, ())
    # A count printed as a lower bound is taken at the bound: ">55" is 56 or more.
    bounded = {**block, "scoreable_statements": ">55"}
    assert W.registered_scoreable({"e3_eligible_test": bounded}) == (56, 7, ("statements",))
    both = {**bounded, "scoreable_episodes": ">6"}
    assert W.registered_scoreable({"e3_eligible_test": both}) == (56, 7, ("statements", "episodes"))
    assert W.registered_count(">0") == (1, True) and W.registered_count(0) == (0, False)
    # A count that is withheld or masked as small gives no number, and nothing else is read
    # as one.
    for masked in ("<5", "withheld", ">", "> 55", ">5.5", "55", ">=55", 41.0, True, None):
        for key in ("scoreable_statements", "scoreable_episodes"):
            with pytest.raises(ValueError, match="no scoreable number or lower bound"):
                W.registered_scoreable({"e3_eligible_test": {**block, key: masked}})


def dev_frame() -> pd.DataFrame:
    """Four dated dev statements in two episodes; the last has an undetermined horizon event."""
    events = [(0.0, 0.0, "e1"), (0.0, 1.0, "e1"), (1.0, 1.0, "e2"), (0.0, NAN, "e2")]
    rows = [
        {"split": "dev", "y_a": a, "y_b": b, "episode_id": e, "scoreable": not np.isnan(b)}
        for a, b, e in events
    ]
    return frame(rows)


def constant(dev: pd.DataFrame, p_a: float, p_b: float) -> pd.DataFrame:
    out = pd.DataFrame(50.0, index=dev.index, columns=list(P.PREDICTION_COLUMNS))
    return out.assign(p_a=p_a, p_b=p_b)


def test_dev_rows_are_the_dated_statements_of_the_dev_split() -> None:
    rows = frame(
        [
            {"split": "dev"},
            {"split": "fit"},
            {"split": "dev", "analysis_set": "stale"},
            {"split": "dev", "analysis_set": "tbd"},
            {"split": "dev", "analysis_set": "silent"},
            {"split": "test", "period": "test"},
            {"split": "dev"},
        ]
    )
    assert W.dev_rows(rows).index.tolist() == ["S000", "S006"]


def test_outcome_mix() -> None:
    dev = dev_frame()
    assert W.outcome_mix(dev[dev["scoreable"]]) == {"no/no": 1, "no/yes": 1, "yes/yes": 1}


def test_loss_report_by_hand() -> None:
    dev = dev_frame()
    predictions = {
        "face_value": constant(dev, 1.0, 1.0),
        "rules_plus_slip": constant(dev, 0.2, 0.6),
    }
    report = W.loss_report(dev, predictions, draws=200)
    assert report["dev"] == {
        "dated_statements": 4,
        "dated_episodes": 2,
        "scoreable_statements": 3,
        "scoreable_episodes": 2,
        "with_a_horizon_event_undetermined": 1,
        "scoreable_by_E_end_and_E_end90": {"no/no": 1, "no/yes": 1, "yes/yes": 1},
    }
    # Face value on the three scoreable statements: 1, 0.5 and 0. Rules plus slip:
    # (0.04 + 0.36) / 2, (0.04 + 0.16) / 2 and (0.64 + 0.16) / 2.
    face, slip = report["losses"]["face_value"], report["losses"]["rules_plus_slip"]
    assert face["primary_brier"] == pytest.approx(0.5)
    assert slip["primary_brier"] == pytest.approx((0.2 + 0.1 + 0.4) / 3)
    assert slip["brier_E_end"] == pytest.approx((0.04 + 0.04 + 0.64) / 3)
    assert slip["brier_E_end90"] == pytest.approx((0.36 + 0.16 + 0.16) / 3)
    assert (slip["mean_p_E_end"], slip["mean_p_E_end90"]) == pytest.approx((0.2, 0.6))
    # The fourth statement (E_end no, E_end90 undetermined): 0.2 as no and 0.1 as yes.
    assert slip["bounds_all_dated"]["undetermined_as_no"] == pytest.approx(0.9 / 4)
    assert slip["bounds_all_dated"]["undetermined_as_yes"] == pytest.approx(0.8 / 4)
    assert slip["ci95"][0] <= slip["primary_brier"] <= slip["ci95"][1]
    assert set(slip["pinball_all_dated"]) == {"0.50", "0.80", "0.95"}
    (contrast,) = report["contrasts"]
    assert (contrast["comparator"], contrast["tested"]) == ("face_value", "rules_plus_slip")
    assert contrast["delta"] == pytest.approx(0.5 - 0.7 / 3)
    assert contrast["ci90"][0] >= contrast["ci95"][0] and contrast["ci90"][1] <= contrast["ci95"][1]
    assert 0 < contrast["p_one_sided"] <= 1 and 0 < contrast["p_two_sided"] <= 1
    assert report == W.loss_report(dev, predictions, draws=200)  # the same draws every time


def test_loss_report_resamples_episodes_and_keeps_the_direction_of_a_contrast() -> None:
    # Two episodes of ten scoreable statements: every event is no in e1 and yes in e2. Face
    # value loses 1 on each statement of e1 and 0 on e2; a constant 0.2 loses 0.04 and 0.64.
    events = [(0.0, "e1")] * 10 + [(1.0, "e2")] * 10
    dev = frame(
        [
            {"split": "dev", "y_a": y, "y_b": y, "episode_id": e, "scoreable": True}
            for y, e in events
        ]
    )
    predictions = {
        "face_value": constant(dev, 1.0, 1.0),
        "rules_plus_slip": constant(dev, 0.2, 0.2),
    }
    report = W.loss_report(dev, predictions, draws=400)
    assert report["bootstrap"] == {"draws": 400, "seed": 20261001, "clusters": "shortage episodes"}
    # A draw takes e1 twice, one of each, or e2 twice, each a quarter, a half and a quarter of
    # the time: face value's mean loss is 1, 0.5 or 0, so its 95% interval is the whole range.
    # (With statements resampled one by one it would be near 0.3 to 0.7.)
    face = report["losses"]["face_value"]
    assert face["primary_brier"] == pytest.approx(0.5) and face["ci95"] == pytest.approx([0.0, 1.0])
    assert report["losses"]["rules_plus_slip"]["ci95"] == pytest.approx([0.04, 0.64])
    # The contrast is the comparator's loss minus the tested predictor's, in the estimate and
    # in every draw: 0.96 on e1 alone, 0.16 on one of each, -0.64 on e2 alone.
    (contrast,) = report["contrasts"]
    assert contrast["delta"] == pytest.approx(0.16)
    assert contrast["ci95"] == pytest.approx([-0.64, 0.96])
    taken = P.cluster_draws(2, draws=400)[:, 0]  # how often e1 is in each draw
    delta = np.array([-0.64, 0.16, 0.96])[taken]
    # One-sided: the draws at or below zero (e2 twice). Two-sided: twice the smaller tail.
    below, above = (1 + (taken == 0).sum()) / 401, (1 + (taken >= 1).sum()) / 401
    assert 0.15 < below < 0.35 < above
    assert contrast["p_one_sided"] == pytest.approx(below)
    assert contrast["p_two_sided"] == pytest.approx(2 * below)
    assert contrast["ci90"] == pytest.approx(P.interval(delta, 0.90))


def test_contrast_intervals_are_those_of_the_paired_episode_draws() -> None:
    # Twelve statements in six episodes with three kinds of outcome, so that the draws of the
    # contrast take many values and its 90% and 95% intervals differ.
    events = [(0.0, 0.0)] * 6 + [(0.0, 1.0)] * 2 + [(1.0, 1.0)] * 4
    dev = frame(
        [
            {"split": "dev", "y_a": a, "y_b": b, "episode_id": f"e{k // 2}", "scoreable": True}
            for k, (a, b) in enumerate(events)
        ]
    )
    predictions = {
        "face_value": constant(dev, 1.0, 1.0),
        "rules_plus_slip": constant(dev, 0.2, 0.6),
    }
    (contrast,) = W.loss_report(dev, predictions, draws=400)["contrasts"]
    losses = W.primary_losses(dev, predictions)
    assert losses["face_value"].tolist() == pytest.approx([1.0] * 6 + [0.5] * 2 + [0.0] * 4)
    assert losses["rules_plus_slip"].tolist() == pytest.approx([0.2] * 6 + [0.1] * 2 + [0.4] * 4)
    boot = P.bootstrap_means(losses.to_numpy(), dev["episode_id"], draws=400)
    delta = boot[:, 0] - boot[:, 1]
    assert contrast["delta"] == pytest.approx((6 * 0.8 + 2 * 0.4 - 4 * 0.4) / 12)
    assert contrast["ci95"] == pytest.approx(P.interval(delta, 0.95))
    assert contrast["ci90"] == pytest.approx(P.interval(delta, 0.90))
    assert contrast["ci95"][0] < contrast["ci90"][0] < contrast["ci90"][1] < contrast["ci95"][1]
    assert contrast["p_one_sided"] == pytest.approx(P.p_values(delta)["one_sided"])
    assert contrast["p_two_sided"] == pytest.approx(P.p_values(delta)["two_sided"])
    assert contrast["p_one_sided"] < contrast["p_two_sided"]


def test_power_report_by_hand() -> None:
    scoreable = frame([{"episode_id": e} for e in ("a", "a", "b", "b")])
    losses = pd.DataFrame(0.0, index=scoreable.index, columns=list(G.PREDICTORS))
    losses["face_value"] = [1.0, 1.0, 0.0, 0.0]  # H1: d = 1, 1, 0, 0, as in the test above
    losses["gbm_structured"] = [1.0, 0.0, 1.0, 0.0]  # H3: no variance between episodes
    test = {"statements": 100, "episodes": 8, "weighted_statements_per_episode": 5.0}
    report = W.power_report(scoreable, losses, test, {"dev": 0.5})
    assert report["family"]["alpha_per_test"] == pytest.approx(0.05 / 6)
    assert (report["family"]["tests_in_the_family"], report["family"]["power"]) == (6, 0.8)
    assert report["dev"]["scoreable_statements"] == 4 and report["dev"]["scoreable_episodes"] == 2
    assert report["dev"]["weighted_statements_per_episode"] == pytest.approx(2.0)
    h1 = report["hypotheses"]["H1"]
    sd = np.sqrt(1 / 3)
    # icc 1: the standard error on 100 statements in episodes of weighted size 5.
    assert h1["test_se"] == pytest.approx(sd * np.sqrt((1 + 4 * 1.0) / 100))
    assert h1["minimum_detectable_delta"] == pytest.approx(W.critical_value(1) * h1["test_se"])
    half = W.critical_value(1) * sd * np.sqrt((1 + 1.5 * 1.0) / 50)
    assert h1["if_the_scoreable_share_were_that_of"]["dev"] == pytest.approx(half)
    assert h1["from_episodes_alone"] == pytest.approx(W.critical_value(1) * 0.5 * np.sqrt(2 / 8))
    h3 = report["hypotheses"]["H3"]
    assert h3["dev"]["icc"] == 0.0 and h3["sides"] == 2
    assert h3["minimum_detectable_delta"] == pytest.approx(W.critical_value(2) * sd / 10)
    assert report["hypotheses"]["H2"]["minimum_detectable_delta"] == 0.0  # identical losses


# --------------------------------------------------------------------------------------------
# The pipeline on the synthetic table
# --------------------------------------------------------------------------------------------


def test_synthetic_table_is_sealed(table: pd.DataFrame) -> None:
    D.assert_sealed(table)
    test_rows = table[table["period"] == "test"]
    assert len(test_rows) == 60 and (test_rows[list(D.OUTCOME_COLUMNS)] == "").all().all()
    counts = counts_of(table)
    assert counts["train"]["dev"]["dated"]["statements"] == 120
    assert 20 < counts["dev_scoreable"]["statements"] < 120  # some horizon events undetermined


def test_build_reports_every_predictor_and_hypothesis(built: tuple[dict, dict]) -> None:
    losses, power = built
    assert list(losses["losses"]) == list(G.PREDICTORS)
    assert losses["fitting"]["split"] == "fit"
    assert losses["fitting"]["statements_by_analysis_set"] == {
        "dated": 200,
        "stale": 0,
        "tbd": 20,
        "silent": 20,
    }
    assert losses["fitting"]["gbm_structured"]["statements"] == 240
    assert losses["fitting"]["calibrator_all_dated_forms"]["statements"] == 200
    cells = losses["fitting"]["calibrator_cells"]
    assert {c["basis"] for c in cells} == {"cell"} and sum(c["statements"] for c in cells) == 200
    refit = losses["refit_for_the_test_runs"]
    assert refit["statements_by_analysis_set"]["dated"] == 320 and refit["min_cell"] == 50
    assert sum(refit["gbm_targets"].values()) == 360
    assert {c["basis"] for c in refit["calibrator_cells"]} == {"cell"}
    assert sum(b["statements"] for b in refit["base_rate_listing_age_bins"]) == 360
    assert len(losses["contrasts"]) == 10
    mix = losses["dev"]["scoreable_by_E_end_and_E_end90"]
    assert sum(mix.values()) == losses["dev"]["scoreable_statements"]
    assert mix == power["dev"]["scoreable_by_E_end_and_E_end90"]
    # The power estimate rests on the scoreable dev statements, and on no other.
    assert power["dev"]["scoreable_statements"] == losses["dev"]["scoreable_statements"]
    assert power["dev"]["scoreable_episodes"] == losses["dev"]["scoreable_episodes"]
    assert losses["dev"]["scoreable_statements"] < losses["dev"]["dated_statements"] == 120
    for record in losses["losses"].values():
        assert 0 <= record["ci95"][0] <= record["primary_brier"] <= record["ci95"][1] <= 1
    # Reading the notice helps on this table: the text model beats the structured one, and
    # everything beats taking the stated date at face value.
    brier = {name: record["primary_brier"] for name, record in losses["losses"].items()}
    assert brier["face_value"] == max(brier.values())
    assert set(power["hypotheses"]) == {"H1", "H2", "H3"}
    for record in power["hypotheses"].values():
        assert record["minimum_detectable_delta"] > 0
        assert record["minimum_detectable_delta"] == pytest.approx(
            record["critical_value"] * record["test_se"]
        )
    assert power["test"]["statements"] == 60 and power["test"]["episodes"] == 9


def test_build_is_reproducible(table: pd.DataFrame, built: tuple[dict, dict]) -> None:
    again = W.build(table, counts_of(table), eligible_of(table), draws=500, min_cell=50)
    texts = W.write_reports(*built, {"statements": "x"})
    assert texts == W.write_reports(*again, {"statements": "x"})
    for text in texts.values():
        parsed = json.loads(text)
        assert parsed["command"] == W.COMMAND and parsed["parameters"]["seed"] == 20261001
        assert parsed["parameters"]["cap_days"] == P.CAP_DAYS
    assert json.loads(texts[W.DEV_LOSSES.name])["fitting"]["min_cell"] == 50
    assert json.loads(texts[W.POWER_REPORT.name])["family"]["tests_in_the_family"] == 6
    assert json.loads(texts[W.POWER_REPORT.name])["proxy_pairs"][0] == {
        "hypothesis": "H1",
        "comparator": "face_value",
        "tested": "rules_plus_slip",
    }


def test_build_never_uses_a_test_period_outcome(table: pd.DataFrame) -> None:
    leaked = table.copy()
    row = leaked.index[leaked["period"] == "test"][0]
    leaked.loc[row, "outcome"] = "recovered"
    with pytest.raises(ValueError, match="outcome columns filled on test-period statements"):
        W.build(leaked, counts_of(table), eligible_of(table), draws=50, min_cell=50)


def test_build_refuses_counts_from_another_build(table: pd.DataFrame) -> None:
    counts = counts_of(table)
    counts["dev_scoreable"] = {"statements": counts["dev_scoreable"]["statements"] + 1}
    with pytest.raises(ValueError, match="not from the same build"):
        W.build(table, counts, eligible_of(table), draws=50, min_cell=50)


def test_rounded() -> None:
    value = {"a": [0.123456789, np.float64(2.0), np.int64(3)], "b": (1 / 3, "x", None, True)}
    assert W.rounded(value) == {"a": [0.123457, 2.0, 3], "b": [0.333333, "x", None, True]}


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def test_command_line_writes_checks_and_refuses_the_sealed_folder(
    table: pd.DataFrame, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    statements, counts, eligible = (tmp_path / n for n in ("s.csv.gz", "c.json", "e.csv"))
    table.to_csv(statements, index=False, compression=dict(D.forms.GZIP))
    counts.write_text(json.dumps(counts_of(table)), encoding="utf-8")
    eligible_of(table).to_csv(eligible, index=False)
    out, sealed = tmp_path / "out", tmp_path / "counts.json"
    args = ["--statements", str(statements), "--counts", str(counts), "--eligible", str(eligible)]
    args += ["--sealed-counts", str(sealed), "--out", str(out)]
    assert W.main(args) == 0
    assert "minimum detectable" in capsys.readouterr().out
    written = {name: (out / name).read_bytes() for name in (W.DEV_LOSSES.name, W.POWER_REPORT.name)}
    assert W.main([*args, "--check"]) == 0
    assert "up to date" in capsys.readouterr().out
    record = json.loads(written[W.DEV_LOSSES.name])
    assert record["inputs"]["statements_sha256"] == D.sha16(statements.read_bytes())
    assert record["bootstrap"] == {
        "draws": 10_000,
        "seed": 20261001,
        "clusters": "shortage episodes",
    }
    assert record["inputs"]["sealed_counts_sha256"] == ""  # no counts-only record yet
    power = json.loads(written[W.POWER_REPORT.name])
    assert power["test"]["statements"] == 60 and "upper bound" in power["test"]["basis"]
    assert set(power["hypotheses"]["H1"]["if_the_scoreable_share_were_that_of"]) == {"dev", "fit"}
    # Once the counts-only record is there, the same command takes the scoreable numbers from
    # it, the power report changes, and --check says so until the command is rerun.
    block = {"scoreable_statements": 30, "scoreable_episodes": 8}
    sealed.write_text(json.dumps({"e3_eligible_test": block}), encoding="utf-8")
    assert W.main([*args, "--check"]) == 1
    assert "power.json" in capsys.readouterr().out
    assert W.main(args) == 0
    capsys.readouterr()
    power = json.loads((out / W.POWER_REPORT.name).read_text(encoding="utf-8"))
    assert (power["test"]["statements"], power["test"]["episodes"]) == (30, 8)
    assert power["test"]["basis"].endswith("from counts.json")
    assert power["inputs"]["sealed_counts_sha256"] == D.sha16(sealed.read_bytes())
    assert power["hypotheses"]["H1"]["if_the_scoreable_share_were_that_of"] == {}
    assert (out / W.DEV_LOSSES.name).read_bytes() != written[W.DEV_LOSSES.name]  # the input hash
    exact = power["hypotheses"]["H1"]["minimum_detectable_delta"]
    # A record that gives the statements as a lower bound: the bound is used, and said.
    block = {"scoreable_statements": ">28", "scoreable_episodes": 8}
    sealed.write_text(json.dumps({"e3_eligible_test": block}), encoding="utf-8")
    assert W.main(args) == 0
    capsys.readouterr()
    power = json.loads((out / W.POWER_REPORT.name).read_text(encoding="utf-8"))
    assert (power["test"]["statements"], power["test"]["episodes"]) == (29, 8)
    assert power["test"]["basis"].endswith("from counts.json (a lower bound for the statements)")
    assert power["hypotheses"]["H1"]["minimum_detectable_delta"] > exact  # fewer statements
    # A withheld count stops the command; the two numbers can then be given by hand.
    block = {"scoreable_statements": "withheld", "scoreable_episodes": 8}
    sealed.write_text(json.dumps({"e3_eligible_test": block}), encoding="utf-8")
    with pytest.raises(ValueError, match="no scoreable number or lower bound"):
        W.main(args)
    assert W.main([*args, "--test-statements", "30", "--test-episodes", "8"]) == 0
    capsys.readouterr()
    power = json.loads((out / W.POWER_REPORT.name).read_text(encoding="utf-8"))
    assert power["test"]["basis"].endswith("from the command line")
    assert power["hypotheses"]["H1"]["minimum_detectable_delta"] == exact
    with pytest.raises(SystemExit, match="sealed"):
        W.main([*args[:-1], str(tmp_path / "sealed" / "out")])


# --------------------------------------------------------------------------------------------
# The files in the repository
# --------------------------------------------------------------------------------------------


def test_outputs_are_up_to_date() -> None:
    inputs = (D.STATEMENTS, D.COUNTS, D.ELIGIBLE)
    if not all(path.exists() for path in (*inputs, W.DEV_LOSSES, W.POWER_REPORT)):
        pytest.skip("the outputs or their inputs are not in this checkout")
    expected = {
        "statements_sha256": D.sha16(D.STATEMENTS.read_bytes()),
        "dataset_counts_sha256": D.sha16(D.COUNTS.read_bytes()),
        "eligible_e3_sha256": D.sha16(D.ELIGIBLE.read_bytes()),
        "sealed_counts_sha256": (
            D.sha16(W.SEALED_COUNTS.read_bytes()) if W.SEALED_COUNTS.exists() else ""
        ),
        **W.code_record(),
    }
    for path in (W.DEV_LOSSES, W.POWER_REPORT):
        recorded = json.loads(path.read_text(encoding="utf-8"))["inputs"]
        stale = {key for key, value in expected.items() if recorded.get(key) != value}
        assert not stale, f"{path}: rerun `{W.COMMAND}` ({sorted(stale)} changed)"
