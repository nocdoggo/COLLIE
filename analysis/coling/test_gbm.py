"""Tests for the gradient-boosted quantile predictors (``gbm.py``).

Everything runs on small synthetic frames. Covered: the registered settings; the category codes
and the structured feature matrix; the targets (midpoint, cap, and the conditional tail of a
right-censored statement, on a pooled curve whose quantiles are worked out by hand); reading the
quantiles as a distribution (interpolation, the 0.95 ceiling, quantiles at the cap, horizons at
or beyond the cap, a horizon before the statement); how a prediction is read from the fitted
regressors (sorted, capped, each level and each horizon in its place); the structured-only model
(it separates two companies and gives sorted quantiles within 0 to 365); the text-trained model
(it separates two wordings that the structured features cannot); determinism; the weight of the
tail copies; the refusal of test-period rows; ``fit_all``; and that a prediction uses the
first-sight columns of its own row and nothing else.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_gbm.py -q -p no:cacheprovider
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.coling import gbm as G
from analysis.coling import predictors as P
from analysis.coling.test_predictors import censored, frame, recovered

INF = np.inf
NAN = float("nan")


def curve(left: list[float], right: list[float], mass: list[float]) -> P.Turnbull:
    """A Turnbull estimate written down directly."""
    return P.Turnbull(np.array(left), np.array(right), np.array(mass), n=4, iterations=0, gap=0.0)


POOLED = curve([0.0, 200.0, P.NEVER], [100.0, 300.0, INF], [0.5, 0.25, 0.25])
"""Half the mass evenly on (0, 100], a quarter on (200, 300], a quarter never."""
LATE = curve([0.0, 400.0, P.NEVER], [100.0, 500.0, INF], [0.5, 0.25, 0.25])
"""Half the mass on (0, 100], a quarter on (400, 500] (beyond the cap), a quarter never."""


# --------------------------------------------------------------------------------------------
# Settings and features
# --------------------------------------------------------------------------------------------


def test_registered_settings_are_fixed_in_the_code() -> None:
    assert list(G.QUANTILES) == [round(0.05 * k, 2) for k in range(1, 20)]
    assert (G.SEED, G.CAP_DAYS, G.TAIL_POINTS, G.MIN_CATEGORY) == (20261001, 365, 10, 20)
    assert G.STRUCTURED == ("reason", "category", "company", "month", "age")
    assert G.PARAMS == {
        "learning_rate": 0.05,
        "max_iter": 200,
        "max_leaf_nodes": 8,
        "min_samples_leaf": 40,
        "l2_regularization": 0.0,
        "max_bins": 255,
        "early_stopping": False,
    }
    assert G.TFIDF == {
        "lowercase": True,
        "ngram_range": (1, 2),
        "min_df": 5,
        "max_features": 300,
        "sublinear_tf": True,
    }
    assert G.PREDICTORS == (
        "base_rate",
        "face_value",
        "rules_plus_slip",
        "gbm_structured",
        "gbm_text",
    )


def test_category_codes_keep_frequent_values_in_sorted_order() -> None:
    rows = frame(
        [{"company": "Beta  Inc"}] * 3
        + [{"company": "beta inc"}] * 2
        + [{"company": "Alpha"}] * 5
        + [{"company": "Rare"}] * 4
    )
    codes = G.fit_categories(rows, minimum=5)
    # Lower-cased with spaces collapsed, "Beta  Inc" and "beta inc" are one value seen 5 times.
    assert codes["company"] == {"alpha": 1, "beta inc": 2}
    assert codes["reason"] == {"": 1} and codes["category"] == {"": 1}  # blank on all 14
    assert G.normal("  Demand   Increase ") == "demand increase"


def test_structured_matrix() -> None:
    codes = {"reason": {"other": 1}, "category": {}, "company": {"alpha": 1, "beta inc": 2}}
    rows = frame(
        [
            {"company": "BETA INC", "reason": "Other", "category": "x", "month": 12, "age": 40.0},
            {"company": "Unseen", "reason": "", "category": "", "month": 1, "age": NAN},
        ]
    )
    x = G.structured_matrix(rows, codes)
    assert x.shape == (2, len(G.STRUCTURED))
    assert x[0].tolist() == [1.0, 0.0, 2.0, 11.0, 40.0]  # reason, category, company, month, age
    assert x[1, :4].tolist() == [0.0, 0.0, 0.0, 0.0] and np.isnan(x[1, 4])


# --------------------------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------------------------


def test_conditional_tail_targets_on_a_hand_computed_curve() -> None:
    # Censored at 50: F(50) = 0.25, so 0.75 lies above. Levels 1/6, 1/2 and 5/6 of the tail are
    # the 0.375, 0.625 and 0.875 quantiles of the whole: 75 (on (0, 100]), 250 (halfway through
    # (200, 300]) and never, which is the cap.
    assert G.tail_targets([50.0], POOLED, points=3)[0] == pytest.approx([75.0, 250.0, 365.0])
    # Censored at 150, between the two intervals: F = 0.5. Levels 0.5833, 0.75 and 0.9167:
    # 200 + 100 / 3, 300 and the cap.
    assert G.tail_targets([150.0], POOLED, points=3)[0] == pytest.approx([700 / 3, 300.0, 365.0])
    # A tail quantile beyond the cap is the cap: on LATE everything above 100 is past day 365.
    assert G.tail_targets([100.0], LATE, points=2).tolist() == [[365.0, 365.0]]
    assert G.tail_targets([], POOLED, points=3).shape == (0, 3)


def test_training_targets_midpoint_cap_and_conditional_tail() -> None:
    rows = frame([recovered(10, 30), censored(400), censored(50), recovered(300, 500)])
    assert rows["ttr_kind"].tolist() == ["interval", "at_cap", "right_censored", "interval"]
    position, target, weight = G.training_targets(rows, POOLED, points=3)
    # One row each for the interval and capped statements (midpoint 20; the cap; the midpoint
    # of the capped bracket (300, 365]), then three rows of weight 1/3 for the censored one.
    assert position.tolist() == [0, 1, 3, 2, 2, 2]
    assert target == pytest.approx([20.0, 365.0, 332.5, 75.0, 250.0, 365.0])
    assert weight == pytest.approx([1, 1, 1, 1 / 3, 1 / 3, 1 / 3])
    assert weight.sum() == pytest.approx(len(rows))


# --------------------------------------------------------------------------------------------
# Reading the quantiles
# --------------------------------------------------------------------------------------------


def test_cdf_below_the_cap_interpolates_between_quantiles() -> None:
    steps = np.arange(10.0, 200.0, 10.0)  # the 0.05 quantile is day 10, ..., the 0.95 is day 190
    horizons = [-1.0, 0.0, 5.0, 10.0, 15.0, 190.0, 200.0, 364.0]
    expected = [0.0, 0.0, 0.025, 0.05, 0.075, 0.95, 0.95, 0.95]
    got = G.cdf_at(np.tile(steps, (len(horizons), 1)), horizons, LATE)
    assert got == pytest.approx(expected)


def test_cdf_with_quantiles_at_the_cap_and_with_ties() -> None:
    # Levels 0.05 to 0.45 at days 10 to 90, levels 0.50 and above at the cap.
    capped = np.concatenate([np.arange(10.0, 100.0, 10.0), np.full(10, 365.0)])
    got = G.cdf_at(np.tile(capped, (3, 1)), [90.0, 364.0, 227.5], LATE)
    assert got == pytest.approx([0.45, 0.45 + 0.05 * 274 / 275, 0.475])
    # Every quantile at day 50: the largest level whose quantile is at most the horizon.
    flat = np.full((2, 19), 50.0)
    assert G.cdf_at(flat, [49.0, 50.0], LATE) == pytest.approx([0.05 * 49 / 50, 0.95])


def test_cdf_at_or_beyond_the_cap_continues_with_the_pooled_tail() -> None:
    capped = np.concatenate([np.arange(10.0, 100.0, 10.0), np.full(10, 365.0)])
    # The model puts 0.5 before the cap. On LATE, F(365) = 0.5; of the half beyond, a quarter
    # has recovered by day 450 and a half by day 500 or any later day.
    got = G.cdf_at(np.tile(capped, (4, 1)), [365.0, 450.0, 500.0, 5000.0], LATE)
    assert got == pytest.approx([0.5, 0.5 + 0.5 * 0.25, 0.75, 0.75])
    # With every quantile below the cap the model's own curve stops at 0.95.
    steps = np.arange(10.0, 200.0, 10.0)
    got = G.cdf_at(np.tile(steps, (2, 1)), [365.0, 450.0], LATE)
    assert got == pytest.approx([0.95, 0.95 + 0.05 * 0.25])
    # A pooled curve with nothing beyond the cap adds nothing.
    done = curve([0.0], [100.0], [1.0])
    assert G.cdf_at(np.tile(capped, (1, 1)), [900.0], done) == pytest.approx([0.5])


class Constant:
    """A stand-in for a fitted regressor: the same day for every row."""

    def __init__(self, day: float) -> None:
        self.day = day

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.full(len(x), self.day)


def test_predictions_read_sorted_capped_quantiles_at_each_horizon() -> None:
    # Raw quantiles that cross, fall below 0 and pass the cap: 400, 180, 170, ..., 20, -7 for
    # the levels 0.05 to 0.95. Kept within 0 to 365 and sorted they are 0, 20, 30, ..., 180, 365.
    raw = [400.0, *np.arange(180.0, 10.0, -10.0), -7.0]
    codes: dict[str, dict[str, int]] = {column: {} for column in G.CATEGORICAL}
    model = G.QuantileGBM(codes, None, tuple(Constant(day) for day in raw), LATE, {})
    rows = frame([{"h_a": 25.0, "h_b": 115.0}, {"h_a": 115.0, "h_b": 365.0}])
    q = model.quantiles(rows)
    assert q[0].tolist() == [0.0, *np.arange(20.0, 190.0, 10.0), 365.0] and (q[0] == q[1]).all()
    out = model.predict(rows)
    # The levels 0.10, 0.50, 0.80, 0.90 and 0.95 are the 2nd, 10th, 16th, 18th and 19th.
    assert out.iloc[0][list(P.QUANTILE_KEYS)].tolist() == [20.0, 100.0, 160.0, 180.0, 365.0]
    # Day 25 is halfway from the 0.10 quantile (20) to the 0.15 quantile (30); day 115 is
    # halfway from the 0.55 quantile (110) to the 0.60 quantile (120).
    assert out.iloc[0][["p_a", "p_b"]].tolist() == pytest.approx([0.125, 0.575])
    # At the cap: 0.95 lies before it (the 0.95 quantile is the first at the cap), and on LATE
    # none of the rest has recovered by day 365.
    assert out.iloc[1][["p_a", "p_b"]].tolist() == pytest.approx([0.575, 0.95])


# --------------------------------------------------------------------------------------------
# The models
# --------------------------------------------------------------------------------------------


def two_groups(column: str, fast: str, slow: str, n: int = 120) -> pd.DataFrame:
    """Fitting statements where ``column`` decides the outcome: ``fast`` recovers in (10, 30]
    days, ``slow`` is still open after 400 days."""
    rows = [recovered(10, 30, **{column: fast}), censored(400, **{column: slow})] * n
    return frame(rows)


def new_rows(column: str, values: list[str]) -> pd.DataFrame:
    return frame([{column: value, "h_a": 60.0, "h_b": 150.0} for value in values])


def test_structured_model_separates_two_companies() -> None:
    model = G.fit_gbm(two_groups("company", "Fast Co", "Slow Co"), text=False)
    assert model.vectorizer is None
    assert model.rows == {
        "interval": 120,
        "at_cap": 120,
        "right_censored": 0,
        "statements": 240,
        "training_rows": 240,
        "features": 5,
    }
    rows = new_rows("company", ["Fast Co", "Slow Co"])
    assert len(model.models) == len(G.QUANTILES)
    for level, regressor in zip(G.QUANTILES, model.models, strict=True):
        settings = regressor.get_params()
        assert (settings["loss"], settings["quantile"]) == ("quantile", level)
        assert settings["random_state"] == G.SEED
        assert {key: settings[key] for key in G.PARAMS} == G.PARAMS
        assert settings["categorical_features"] == [0, 1, 2, 3]  # all but the listing age
    q = model.quantiles(rows)
    assert q.shape == (2, len(G.QUANTILES))
    assert (np.diff(q, axis=1) >= 0).all() and q.min() >= 0 and q.max() <= 365
    assert q[0] == pytest.approx(np.full(19, 20.0), abs=0.5)  # the midpoint of (10, 30]
    assert q[1] == pytest.approx(np.full(19, 365.0), abs=0.5)  # the cap
    out = model.predict(rows)
    assert list(out.columns) == list(P.PREDICTION_COLUMNS)
    assert out["p_a"].tolist() == pytest.approx([0.95, 0.05 * 60 / 365], abs=0.01)
    assert out["q50"].tolist() == pytest.approx([20.0, 365.0], abs=0.5)


def test_text_model_separates_two_wordings_that_the_structured_model_cannot() -> None:
    fit = two_groups("text", "resupply expected soon", "no release date at this time")
    rows = new_rows("text", ["resupply expected soon", "no release date at this time"])
    with_text = G.fit_gbm(fit, text=True)
    assert with_text.rows["features"] > len(G.STRUCTURED)
    out = with_text.predict(rows)
    assert out["p_a"].iloc[0] > 0.9 and out["p_a"].iloc[1] < 0.05
    structured = G.fit_gbm(fit, text=False).predict(rows)
    assert structured.iloc[0].tolist() == structured.iloc[1].tolist()


def test_fit_is_deterministic_and_uses_the_conditional_tail() -> None:
    fit = frame(
        [recovered(10, 30, company="Fast Co"), censored(400, company="Slow Co")] * 60
        + [censored(5, company="Fast Co")] * 20
    )
    first, again = G.fit_gbm(fit, text=False), G.fit_gbm(fit, text=False)
    assert first.rows["right_censored"] == 20
    assert first.rows["training_rows"] == 120 + 20 * G.TAIL_POINTS
    rows = new_rows("company", ["Fast Co", "Slow Co", "Unseen Co"])
    assert first.predict(rows).equals(again.predict(rows))
    assert not first.predict(rows).isna().any().any()
    # The pooled curve: half the mass on (10, 30], half never (the 20 statements censored at
    # day 5 fit both). Their tails are 12, 16, 20, 24 and 28 days and five times the cap.
    assert first.pooled.mass == pytest.approx([0.5, 0.5], abs=1e-6)
    tails = G.tail_targets([5.0], first.pooled)[0]
    assert tails == pytest.approx([12, 16, 20, 24, 28, 365, 365, 365, 365, 365], abs=1e-4)
    # Each censored statement weighs one statement in all. For "Fast Co" that is a weight of 60
    # at day 20, 2 each at 12, 16, 20, 24 and 28, and 10 at the cap, of 80: 0.825 of the weight
    # is at or below day 20, so the 0.80 quantile is 20 days and the 0.90 quantile is the cap.
    # With every copy at full weight 100 of 260 rows would be at the cap, and the 0.80 quantile
    # with them.
    fast = first.predict(rows).iloc[0]
    assert fast[["q50", "q80"]].tolist() == pytest.approx([20.0, 20.0], abs=1.0)
    assert fast[["q90", "q95"]].tolist() == pytest.approx([365.0, 365.0], abs=1.0)


def test_fit_refuses_test_period_rows() -> None:
    fit = two_groups("company", "Fast Co", "Slow Co", n=5)
    fit.loc[fit.index[0], "period"] = "test"
    with pytest.raises(ValueError, match="train-period statements only"):
        G.fit_gbm(fit, text=False)
    with pytest.raises(ValueError, match="no fitting statement"):
        G.fit_gbm(frame([recovered(0, 10, analysis_set="stale")]), text=False)


def test_fit_all_gives_the_five_predictors_in_order() -> None:
    dated = [
        recovered(10, 30, company="Fast Co", text="resupply expected soon"),
        censored(400, company="Slow Co", text="no release date at this time"),
    ] * 60
    undated = {"analysis_set": "tbd", "form": "tbd", "end_days": NAN, "h_a": 90.0, "h_b": 180.0}
    no_date = [recovered(0, 100, text="to be determined", **undated)] * 10
    fitted = G.fit_all(frame(dated + no_date), min_cell=50)
    assert tuple(fitted) == G.PREDICTORS
    rows = new_rows("company", ["Fast Co", "Slow Co"])
    for name, model in fitted.items():
        out = model.predict(rows)
        assert list(out.columns) == list(P.PREDICTION_COLUMNS), name
        assert not out.isna().any().any(), name
        assert out[["p_a", "p_b"]].to_numpy().min() >= 0, name
        assert out[["p_a", "p_b"]].to_numpy().max() <= 1, name
        assert out[list(P.QUANTILE_KEYS)].to_numpy().min() >= 0, name
        assert out[list(P.QUANTILE_KEYS)].to_numpy().max() <= 365, name
        assert (np.diff(out[list(P.QUANTILE_KEYS)].to_numpy(), axis=1) >= 0).all(), name


OUTCOME_FIELDS = (
    "outcome",
    "lower_days",
    "upper_days",
    "y_a",
    "y_b",
    "scoreable",
    "ttr_kind",
    "ttr_lower",
    "ttr_upper",
    "ttr_mid",
)
"""The columns of the typed frame that hold outcome information."""


def test_a_prediction_uses_first_sight_columns_of_its_own_row_only() -> None:
    dated = [
        recovered(10, 30, company="Fast Co", text="resupply expected soon", age=30.0),
        censored(400, company="Slow Co", text="no release date at this time", age=900.0),
        censored(40, company="Slow Co", text="resupply expected", age=400.0, month=7),
    ] * 60
    undated = {"analysis_set": "tbd", "form": "tbd", "end_days": NAN, "h_a": 90.0, "h_b": 180.0}
    no_date = [recovered(0, 100, text="to be determined", **undated)] * 10
    fitted = G.fit_all(frame(dated + no_date), min_cell=50)
    rows = frame(
        [
            recovered(10, 30, company="Fast Co", text="resupply expected soon", age=20.0),
            censored(50, company="Slow Co", text="resupply expected", age=500.0, month=7),
            censored(400, company="New Co", text="no release date at this time", age=NAN),
            recovered(0, 5, company="Slow Co", text="soon", revision="second", h_a=5.0, h_b=95.0),
        ]
    )
    assert set(OUTCOME_FIELDS) < set(rows.columns)
    # The same rows as a test-period statement has them: no outcome in any column.
    blank = rows.assign(
        outcome="", ttr_kind="", scoreable=False, **dict.fromkeys(OUTCOME_FIELDS[1:5], NAN)
    ).assign(ttr_lower=NAN, ttr_upper=NAN, ttr_mid=NAN, period="test", split="test")
    # And with the outcomes of other rows.
    swapped = rows.copy()
    swapped[list(OUTCOME_FIELDS)] = rows[list(OUTCOME_FIELDS)].to_numpy()[::-1]
    for name, model in fitted.items():
        out = model.predict(rows)
        assert not out.isna().any().any(), name
        pd.testing.assert_frame_equal(model.predict(blank), out, obj=name)
        pd.testing.assert_frame_equal(model.predict(swapped), out, obj=name)
        # Row by row, and in another order: no row's prediction depends on the other rows.
        alone = pd.concat([model.predict(rows.iloc[[k]]) for k in range(len(rows))])
        pd.testing.assert_frame_equal(alone, out, obj=name)
        pd.testing.assert_frame_equal(model.predict(rows.iloc[::-1]).iloc[::-1], out, obj=name)
    # The text features of a row: the vocabulary and the document frequencies are those of the
    # fitting statements, whatever else is predicted with it.
    text = fitted["gbm_text"]
    assert text.rows["features"] > len(G.STRUCTURED)
    whole = text.features(rows)
    assert (whole[:, len(G.STRUCTURED) :] > 0).any(axis=1).all()
    for k in range(len(rows)):
        assert np.array_equal(text.features(rows.iloc[[k]]), whole[[k]], equal_nan=True)
    structured = fitted["gbm_structured"].features(rows)
    assert np.array_equal(structured, whole[:, : len(G.STRUCTURED)], equal_nan=True)
