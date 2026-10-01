"""Tests for the model-free predictors, the censoring module and the scores (``predictors.py``).

Everything runs on small synthetic inputs whose answers are worked out by hand in the comments.
Covered: the Turnbull estimate (innermost intervals, ties, mass on the innermost intervals only,
the empirical distribution on exact observations, the product-limit estimate with right
censoring only, mass that no finite time reaches, the three readings of the curve, quantiles and
the conditional tail, a comparison with a plain EM on random brackets, the stopping rule,
refusals); the brackets of time to recovery and of slip (a discontinuation never recovers); the
primary Brier loss, its bounds and the pinball loss on interval-censored, capped and
right-censored targets; the typed frame (types, horizon events, sealing); the registered
constants; the listing-age bins and the base rate with its backoff; face value; the slip
calibrator (the backoff of cell, form and all dated forms, the minimum of 100 statements at its
boundary, stale statements left out, rules plus slip, a reading that differs from the rule's,
ABSTAIN, the table); and the paired cluster bootstrap (determinism, pairing, a two-cluster case,
a statement with no cluster, intervals and p-values).

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_predictors.py -q -p no:cacheprovider
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from analysis.coling import dataset as D
from analysis.coling import predictors as P

INF = np.inf
NAN = float("nan")
TARGET_KEYS = ("lower", "upper", "mid")


def frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """A typed frame from partial rows: a dated fit statement that recovered in (0, 10] days
    unless a row says otherwise."""
    base = {
        "episode_id": "e1",
        "period": "train",
        "split": "fit",
        "analysis_set": "dated",
        "form": "month_year",
        "revision": "first",
        "month": 1,
        "end_days": 30.0,
        "h_a": 30.0,
        "h_b": 120.0,
        "age": 10.0,
        "reason": "",
        "category": "",
        "company": "",
        "text": "",
        "outcome": "recovered",
        "lower_days": 0.0,
        "upper_days": 10.0,
        "y_a": NAN,
        "y_b": NAN,
        "scoreable": False,
        "ttr_kind": "interval",
        "ttr_lower": 0.0,
        "ttr_upper": 10.0,
        "ttr_mid": 5.0,
    }
    index = pd.Index([f"S{k:03d}" for k in range(len(rows))], name="statement_group_id")
    return pd.DataFrame([{**base, **row} for row in rows], index=index, columns=P.FRAME_COLUMNS)


def outcome(kind: str, lower: float, upper: float | None, **more: Any) -> dict[str, Any]:
    """The outcome cells of a row whose bracket is ``(lower, upper]`` days, with the capped
    time-to-recovery target that ``dataset.py`` derives from it."""
    target = D.time_target(kind, lower, upper)
    return {
        "outcome": kind,
        "lower_days": float(lower),
        "upper_days": NAN if upper is None else float(upper),
        "ttr_kind": target["kind"],
        **{f"ttr_{key}": NAN if target[key] == "" else float(target[key]) for key in TARGET_KEYS},
        **more,
    }


def recovered(lower: float, upper: float, **more: Any) -> dict[str, Any]:
    return outcome("recovered", lower, upper, **more)


def censored(lower: float, **more: Any) -> dict[str, Any]:
    return outcome("censored", lower, None, **more)


def discontinued(lower: float, upper: float, **more: Any) -> dict[str, Any]:
    return outcome("discontinued", lower, upper, **more)


# --------------------------------------------------------------------------------------------
# Turnbull
# --------------------------------------------------------------------------------------------


def test_innermost_intervals_put_a_right_endpoint_before_a_left_one_at_a_tie() -> None:
    # (0, 2] and (2, 4] do not overlap, so both are innermost.
    a, b = P.innermost(np.array([0.0, 2.0]), np.array([2.0, 4.0]))
    assert a.tolist() == [0.0, 2.0] and b.tolist() == [2.0, 4.0]
    # (0, 2] and (1, 3] overlap on (1, 2]: the only place the mass can sit.
    a, b = P.innermost(np.array([0.0, 1.0]), np.array([2.0, 3.0]))
    assert a.tolist() == [1.0] and b.tolist() == [2.0]
    assert P.turnbull([0, 1, 1], [2, 3, 3]).mass.tolist() == [1.0]


def test_turnbull_on_a_hand_computed_case() -> None:
    # Observations (0,1], (0,1], (0,2], (1,2]. Innermost intervals (0,1] and (1,2] with masses
    # p and 1 - p. Likelihood p * p * 1 * (1 - p), largest at p = 2/3.
    t = P.turnbull([0, 0, 0, 1], [1, 1, 2, 2])
    assert t.left.tolist() == [0.0, 1.0] and t.right.tolist() == [1.0, 2.0]
    assert t.mass == pytest.approx([2 / 3, 1 / 3], abs=1e-6)
    assert t.n == 4 and t.gap <= P.TOLERANCE and t.reached == pytest.approx(1.0)
    # The three readings of the curve at 0.5 and at the ends of the first interval.
    assert t.cdf(0.5) == pytest.approx(1 / 3, abs=1e-6)  # mass spread evenly over (0, 1]
    assert t.cdf(0.5, "lower") == pytest.approx(0.0)  # mass at the right end
    assert t.cdf(0.5, "upper") == pytest.approx(2 / 3, abs=1e-6)  # mass just after the left end
    assert t.cdf([0.0, 1.0, 1.5, 2.0, 9.0]) == pytest.approx([0, 2 / 3, 5 / 6, 1, 1], abs=1e-6)
    assert t.cdf([1.0, 2.0], "lower") == pytest.approx([2 / 3, 1.0], abs=1e-6)
    assert t.cdf([-1.0, 0.0], "upper") == pytest.approx([0.0, 0.0])
    # Quantiles invert the evenly spread curve: 0.5 is reached at 0.5 / (2/3) = 0.75, and 0.9
    # at 1 + (0.9 - 2/3) / (1/3) = 1.7.
    assert t.quantile([0.0, 0.5, 5 / 6, 0.9]) == pytest.approx([0.0, 0.75, 1.5, 1.7], abs=1e-5)
    with pytest.raises(ValueError, match="unknown rule"):
        t.cdf(1.0, "middle")


def test_turnbull_needs_iteration_when_the_brackets_are_uneven() -> None:
    # (0,1] once, (0,2] once, (1,2] twice: likelihood p * 1 * (1 - p)^2, largest at p = 1/3.
    t = P.turnbull([0, 0, 1, 1], [1, 2, 2, 2])
    assert t.mass == pytest.approx([1 / 3, 2 / 3], abs=1e-6)
    assert t.iterations > 1


def test_turnbull_equals_the_product_limit_estimate_on_narrow_brackets() -> None:
    # Events in (1,2], (3,4] and (5,6], one observation censored at 2.5. Product-limit: 1/4 at
    # the first event; of the 3/4 left, the censored one leaves 2 at risk: 3/8 and 3/8.
    t = P.turnbull([1, 3, 2.5, 5], [2, 4, INF, 6])
    assert t.right.tolist() == [2.0, 4.0, 6.0]
    assert t.mass == pytest.approx([0.25, 0.375, 0.375], abs=1e-6)


def test_mass_sits_only_on_the_innermost_intervals() -> None:
    # (0,3], (2,5] and (4,7]. The innermost intervals are (2,3] and (4,5], with masses p and
    # 1 - p; the middle observation holds both, so the likelihood is p * 1 * (1 - p): p = 1/2.
    # Nothing sits on (3,4], which only the middle observation covers.
    t = P.turnbull([0, 2, 4], [3, 5, 7])
    assert t.left.tolist() == [2.0, 4.0] and t.right.tolist() == [3.0, 5.0]
    assert t.mass == pytest.approx([0.5, 0.5], abs=1e-9)
    days = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
    assert t.cdf(days) == pytest.approx([0, 0.25, 0.5, 0.5, 0.5, 0.75, 1, 1], abs=1e-9)
    assert t.cdf([2.9, 3.0], "lower") == pytest.approx([0.0, 0.5], abs=1e-9)
    assert t.cdf([2.0, 2.1], "upper") == pytest.approx([0.0, 0.5], abs=1e-9)


def test_turnbull_is_the_empirical_distribution_on_exact_observations() -> None:
    # A value known to the day is the bracket (day - 1, day]. Six values with three tied at
    # day 3 and one at day 4, whose bracket starts where theirs ends: no two brackets overlap,
    # so each holds its share of the observations, reached in one step from equal masses.
    days = np.array([3.0, 1.0, 3.0, 4.0, 3.0, 7.0])
    t = P.turnbull(days - 1, days)
    assert t.left.tolist() == [0.0, 2.0, 3.0, 6.0] and t.right.tolist() == [1.0, 3.0, 4.0, 7.0]
    assert t.mass == pytest.approx([1 / 6, 3 / 6, 1 / 6, 1 / 6], abs=1e-12)
    assert t.iterations == 2 and t.reached == pytest.approx(1.0)
    # With the mass at the right ends the curve is the empirical distribution function.
    rng = np.random.default_rng(P.SEED)
    days = rng.integers(1, 31, size=200).astype(float)
    grid = np.arange(0.0, 32.0, 0.5)
    empirical = [(days <= day).mean() for day in grid]
    assert P.turnbull(days - 1, days).cdf(grid, "lower") == pytest.approx(empirical, abs=1e-12)


def kaplan_meier(days: np.ndarray, observed: np.ndarray) -> dict[float, float]:
    """The product-limit estimate of the probability of a value at or below each event day. An
    observation censored at a day is known to be above it, so it is at risk on that day."""
    below, alive = {}, 1.0
    for day in np.unique(days[observed]):
        events, at_risk = (observed & (days == day)).sum(), (days >= day).sum()
        alive *= 1 - events / at_risk
        below[float(day)] = 1 - alive
    return below


def test_turnbull_equals_kaplan_meier_with_right_censoring_only() -> None:
    # 150 whole-day values with ties, about four in ten censored, and one more censored after
    # every event: the last part of the mass is never placed at a finite time.
    rng = np.random.default_rng(P.SEED)
    days = np.append(rng.integers(1, 41, size=150).astype(float), 50.0)
    observed = np.append(rng.random(150) < 0.6, False)
    t = P.turnbull(np.where(observed, days - 1, days), np.where(observed, days, INF))
    expected = kaplan_meier(days, observed)
    assert len(expected) > 20 and 50 < observed.sum() < 130
    assert t.cdf(list(expected), "lower") == pytest.approx(list(expected.values()), abs=1e-6)
    assert t.reached == pytest.approx(max(expected.values()), abs=1e-6) and t.reached < 0.99
    assert np.isinf(t.right[-1]) and np.isinf(t.quantile(0.995))


def test_mass_beyond_the_last_observation_is_never_reached() -> None:
    # (0,1], censored at 0, censored at 1. Innermost (0,1] and (1, inf): p * 1 * (1 - p), p = 1/2.
    t = P.turnbull([0, 0, 1], [1, INF, INF])
    assert t.right.tolist() == [1.0, INF]
    assert t.mass == pytest.approx([0.5, 0.5], abs=1e-6)
    assert t.reached == pytest.approx(0.5, abs=1e-6)
    assert t.cdf([0.5, 1.0, 1e6]) == pytest.approx([0.25, 0.5, 0.5], abs=1e-6)
    assert t.quantile([0.25, 0.4]) == pytest.approx([0.5, 0.8], abs=1e-5)
    assert np.isinf(t.quantile([0.6, 0.99])).all()
    # Given a value above 0.5 (three quarters of the mass): the 0.2 quantile of the tail is the
    # 0.25 + 0.2 * 0.75 = 0.4 quantile of the whole, at 0.8; the tail's median is never reached.
    assert t.conditional_quantile(0.2, 0.5) == pytest.approx(0.8, abs=1e-5)
    assert np.isinf(t.conditional_quantile(0.5, 0.5))


def test_turnbull_with_only_censored_observations_reaches_nothing() -> None:
    t = P.turnbull([3, 5], [INF, INF])
    assert t.reached == 0.0
    assert t.cdf([0.0, 10.0]).tolist() == [0.0, 0.0]
    assert np.isinf(t.quantile([0.1])).all()


def plain_em(left: np.ndarray, right: np.ndarray, steps: int = 20_000) -> np.ndarray:
    """The textbook self-consistency iteration with the full observation-by-interval matrix."""
    a, b = P.innermost(left, right)
    inside = (left[:, None] <= a[None, :]) & (b[None, :] <= right[:, None])
    mass = np.full(len(a), 1.0 / len(a))
    for _ in range(steps):
        weights = inside * mass
        mass = (weights / weights.sum(axis=1, keepdims=True)).mean(axis=0)
    return mass


def random_brackets(n: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """Whole-day brackets with many shared endpoints, about three in ten right-censored."""
    rng = np.random.default_rng(P.SEED)
    left = rng.integers(0, 30, size=n).astype(float)
    right = left + rng.integers(1, 15, size=n)
    right[rng.random(n) < 0.3] = INF
    return left, right


def test_turnbull_matches_a_plain_em_on_random_brackets() -> None:
    left, right = random_brackets()
    t = P.turnbull(left, right)
    assert t.mass == pytest.approx(plain_em(left, right), abs=1e-5)
    assert t.mass.sum() == pytest.approx(1.0)
    assert (np.diff(t.cdf(np.arange(0, 50))) >= -1e-12).all()


def test_turnbull_stops_at_the_maximum_or_fails() -> None:
    left, right = random_brackets()
    t = P.turnbull(left, right)
    assert t.iterations > 1 and 0 <= t.gap <= P.TOLERANCE
    # At the maximum no mass can be moved to raise the likelihood: its derivative with respect
    # to each mass (the mean over observations of 1 / P(observation) where the observation
    # holds the interval) is at most 1, and it is 1 on every interval that keeps mass.
    holds = (left[:, None] <= t.left[None, :]) & (t.right[None, :] <= right[:, None])
    assert holds.any(axis=1).all()
    derivative = (holds / (holds @ t.mass)[:, None]).mean(axis=0)
    assert derivative.max() <= 1 + 1e-7
    assert derivative[t.mass > 0.01] == pytest.approx(1.0, abs=1e-6)
    # A looser tolerance stops earlier; a step limit that is too small is an error, not an
    # unconverged estimate.
    assert P.turnbull(left, right, tolerance=1e-3).iterations < t.iterations
    with pytest.raises(RuntimeError, match="did not converge"):
        P.turnbull(left, right, max_iterations=3)


def test_turnbull_refuses_bad_brackets() -> None:
    with pytest.raises(ValueError, match="left < right"):
        P.turnbull([0, 2], [1, 2])
    with pytest.raises(ValueError, match="left < right"):
        P.turnbull([0, NAN], [1, 2])
    with pytest.raises(ValueError, match="no observation"):
        P.turnbull([], [])


def test_brackets_of_time_to_recovery_and_of_slip() -> None:
    rows = frame([recovered(5, 40), censored(100), discontinued(3, 9)])
    left, right = P.ttr_brackets(rows)
    assert left.tolist() == [5.0, 100.0, P.NEVER] and right.tolist() == [40.0, INF, INF]
    # Slip is recovery minus the stated end (30 days after the statement).
    left, right = P.slip_brackets(rows)
    assert left.tolist() == [-25.0, 70.0, P.NEVER] and right.tolist() == [10.0, INF, INF]
    with pytest.raises(ValueError, match="stated end"):
        P.slip_brackets(frame([{"end_days": NAN}]))


def test_a_discontinuation_never_recovers() -> None:
    # One recovery in (0, 10] and one discontinuation: half the mass is never reached.
    t = P.turnbull(*P.ttr_brackets(frame([recovered(0, 10), discontinued(0, 5)])))
    assert t.cdf([10.0, 1e6]) == pytest.approx([0.5, 0.5], abs=1e-6)
    assert np.isinf(t.quantile([0.75])).all()


# --------------------------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------------------------


def test_primary_brier_is_the_mean_of_the_two_horizon_scores() -> None:
    # (0.2 - 0)^2 = 0.04 and (0.7 - 1)^2 = 0.09: mean 0.065.
    assert P.primary_loss([0.2], [0.7], [0.0], [1.0]) == pytest.approx([0.065])
    assert P.primary_loss([1.0], [1.0], [0.0], [0.0]) == pytest.approx([1.0])
    # An undetermined horizon event leaves the statement out of the complete case.
    assert np.isnan(P.primary_loss([0.2, 0.2], [0.7, 0.7], [0.0, NAN], [NAN, 1.0])).all()


def test_brier_bounds_set_undetermined_events_to_no_and_then_to_yes() -> None:
    # Statement 1 is scoreable: 0.065. Statement 2 has E_end = no and E_end90 undetermined:
    # as no, (0.25 + 0.81) / 2 = 0.53; as yes, (0.25 + 0.01) / 2 = 0.13.
    bounds = P.brier_bounds([0.2, 0.5], [0.7, 0.9], [0.0, 0.0], [1.0, NAN])
    assert bounds["undetermined_as_no"] == pytest.approx((0.065 + 0.53) / 2)
    assert bounds["undetermined_as_yes"] == pytest.approx((0.065 + 0.13) / 2)


def test_pinball_loss() -> None:
    assert P.pinball([25.0, 25.0], [20.0, 365.0], 0.8) == pytest.approx([1.0, 272.0])
    assert P.pinball([10.0], [10.0], 0.5) == pytest.approx([0.0])


def test_pinball_on_censored_targets() -> None:
    rows = frame(
        [
            {"ttr_kind": "interval", "ttr_lower": 10.0, "ttr_upper": 30.0, "ttr_mid": 20.0},
            {"ttr_kind": "at_cap", "ttr_lower": 365.0, "ttr_upper": 365.0, "ttr_mid": 365.0},
            {"ttr_kind": "right_censored", "ttr_lower": 100.0, "ttr_upper": NAN, "ttr_mid": NAN},
        ]
    )
    scores = P.pinball_scores([25.0, 25.0, 25.0], rows, 0.8)
    # Interval: midpoint 20 is below 25, so 0.2 * 5 = 1; the bracket holds 25, so the smallest
    # loss is 0 and the largest is max(0.2 * 15, 0.8 * 5) = 4.
    # At the cap: 0.8 * (365 - 25) = 272, with no bracket.
    # Right-censored at 100: left out; bounds at 100 (0.8 * 75 = 60) and at the cap (272).
    assert scores["loss"] == pytest.approx((1 + 272) / 2)
    assert scores["statements"] == 2 and scores["left_out_right_censored"] == 1
    assert scores["lower_bound"] == pytest.approx((0 + 272 + 60) / 3)
    assert scores["upper_bound"] == pytest.approx((4 + 272 + 272) / 3)
    only_censored = P.pinball_scores([25.0], rows.iloc[[2]], 0.5)
    assert only_censored["loss"] is None and only_censored["statements"] == 0
    with pytest.raises(ValueError, match="no time-to-recovery target"):
        P.pinball_scores([25.0], frame([{"ttr_kind": ""}]), 0.5)


# --------------------------------------------------------------------------------------------
# The typed frame
# --------------------------------------------------------------------------------------------


def table(rows: list[dict[str, str]]) -> pd.DataFrame:
    """A statement table in the schema of ``dataset.py`` from partial rows of text cells."""
    filled = [{**dict.fromkeys(D.COLUMNS, ""), **row} for row in rows]
    return pd.DataFrame(filled, columns=list(D.COLUMNS)).astype(str)


TRAIN_ROW = {
    "statement_group_id": "S2",
    "episode_id": "drug@2019-10-20",
    "period": "train",
    "split": "fit",
    "event_date": "2020-03-10",
    "at_risk_B": "True",
    "revision": "second",
    "company_name": "Acme",
    "therapeutic_category": "Anesthesia",
    "initial_posting_date": "2020-01-10",
    "listing_age_days": "60",
    "reason_for_shortage": "Other",
    "availability_text": "Next release April 2020",
    "related_text": "Check wholesalers",
    "merged_form": "month_year",
    "stated_end": "2020-04-30",
    "analysis_set": "dated",
    "horizon_a": "2020-04-30",
    "horizon_b": "2020-07-29",
    "outcome": "recovered",
    "lower_days": "40",
    "upper_days": "70",
    "E_end": "undetermined",
    "E_end90": "yes",
    "scoreable": "False",
    "ttr_kind": "interval",
    "ttr_lower_days": "40",
    "ttr_upper_days": "70",
    "ttr_mid_days": "55",
}
TBD_ROW = {
    **TRAIN_ROW,
    "statement_group_id": "S1",
    "merged_form": "tbd",
    "stated_end": "",
    "analysis_set": "tbd",
    "horizon_a": "2020-06-08",
    "horizon_b": "2020-09-06",
    "listing_age_days": "",
    "outcome": "censored",
    "lower_days": "400",
    "upper_days": "",
    "E_end": "",
    "E_end90": "",
    "E_90": "no",
    "E_180": "no",
    "scoreable": "",
    "ttr_kind": "at_cap",
    "ttr_lower_days": "365",
    "ttr_upper_days": "365",
    "ttr_mid_days": "365",
}
TEST_ROW = {
    key: value
    for key, value in {**TRAIN_ROW, "statement_group_id": "S3", "period": "test"}.items()
    if key not in D.OUTCOME_COLUMNS
} | {
    "split": "test",
    "event_date": "2024-03-10",
    "stated_end": "2024-04-30",
    "horizon_a": "2024-04-30",
    "horizon_b": "2024-07-29",
}


def test_prepare_types_the_statement_table() -> None:
    not_at_risk = {**TRAIN_ROW, "statement_group_id": "S0", "at_risk_B": "False"}
    no_set = {**TRAIN_ROW, "statement_group_id": "S4", "analysis_set": "none"}
    f = P.prepare(table([TRAIN_ROW, TEST_ROW, TBD_ROW, not_at_risk, no_set]))
    assert f.index.tolist() == ["S1", "S2", "S3"]  # sorted; at risk and in an analysis set
    assert list(f.columns) == list(P.FRAME_COLUMNS)
    dated = f.loc["S2"]
    assert (dated["end_days"], dated["h_a"], dated["h_b"]) == (51.0, 51.0, 141.0)
    assert (dated["month"], dated["age"], dated["form"]) == (3, 60.0, "month_year")
    assert dated["text"] == "Next release April 2020 Check wholesalers"
    assert (dated["lower_days"], dated["upper_days"], dated["ttr_mid"]) == (40.0, 70.0, 55.0)
    assert np.isnan(dated["y_a"]) and dated["y_b"] == 1.0 and not dated["scoreable"]
    # A TBD statement takes its horizon events from the 90 and 180 day horizons.
    tbd = f.loc["S1"]
    assert (tbd["h_a"], tbd["h_b"]) == (90.0, 180.0) and np.isnan(tbd["end_days"])
    assert (tbd["y_a"], tbd["y_b"], tbd["scoreable"]) == (0.0, 0.0, True)
    assert np.isnan(tbd["age"]) and np.isnan(tbd["upper_days"])
    # A test-period statement has first-sight columns and no outcome.
    sealed = f.loc["S3"]
    assert sealed["outcome"] == "" and np.isnan(sealed["lower_days"]) and np.isnan(sealed["y_a"])
    assert sealed["h_b"] == 141.0


def test_prepare_refuses_a_test_period_outcome() -> None:
    leaked = {**TEST_ROW, "E_end": "yes"}
    with pytest.raises(ValueError, match="outcome columns filled on test-period statements"):
        P.prepare(table([TRAIN_ROW, leaked]))


def test_registered_constants() -> None:
    assert (P.SEED, P.DRAWS, P.MIN_CELL, P.CAP_DAYS) == (20261001, 10_000, 100, 365)
    assert P.REVISIONS == ("first", "second", "third or later")
    assert P.BASES == ("cell", "form", "all dated forms")
    assert P.QUANTILE_LEVELS == (0.10, 0.50, 0.80, 0.90, 0.95)
    assert P.PINBALL_LEVELS == (0.50, 0.80, 0.95)
    assert P.AGE_EDGES == (0, 90, 365, 730, 1095, 1825)
    assert (P.BASE_RATE_SETS, P.NO_DATE_SETS) == (("dated", "tbd", "silent"), ("tbd", "silent"))


def test_fitting_refuses_test_period_rows_and_rows_with_no_outcome() -> None:
    good = frame([recovered(0, 10), censored(20, analysis_set="tbd")])
    assert len(P.fitting_rows(good)) == 2 and len(P.fitting_rows(good, ("dated",))) == 1
    with pytest.raises(ValueError, match="train-period statements only"):
        P.fitting_rows(frame([recovered(0, 10), recovered(0, 10, period="test")]))
    with pytest.raises(ValueError, match="no outcome"):
        P.fitting_rows(frame([recovered(0, 10), {"outcome": "", "ttr_kind": ""}]))
    for fit in (P.fit_base_rate, P.fit_calibrator):
        with pytest.raises(ValueError, match="train-period statements only"):
            fit(frame([recovered(0, 10), recovered(0, 10, period="test")]))


# --------------------------------------------------------------------------------------------
# Predictors
# --------------------------------------------------------------------------------------------


def test_listing_age_bins() -> None:
    ages = [0, 89, 90, 364, 365, 729, 730, 1094, 1095, 1824, 1825, 9000, NAN]
    labels = [P.AGE_LABELS[k] for k in (0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5)]
    assert P.age_bin(ages).tolist() == [*labels, P.AGE_UNKNOWN]


def test_base_rate_by_listing_age_with_backoff() -> None:
    young = [recovered(0, 10, age=5.0), recovered(0, 10, age=50.0)]
    old = [censored(50, age=2000.0)]
    fit = frame([*young, *old, recovered(0, 10, analysis_set="stale", age=5.0)])
    base = P.fit_base_rate(fit, min_cell=2)
    # The stale statement is not a fitting statement. The young bin has two statements and a
    # curve of its own; the old bin has one and uses all three: (0,10] twice and (50, inf).
    assert base.counts[P.AGE_LABELS[0]] == 2 and base.counts[P.AGE_LABELS[5]] == 1
    assert set(base.curves) == {P.ALL_AGES, P.AGE_LABELS[0]}
    assert [row["basis"] for row in base.table()] == ["bin", *[P.ALL_AGES] * 6]
    new = frame(
        [
            {"age": 20.0, "h_a": 5.0, "h_b": 10.0},
            {"age": 3000.0, "h_a": 5.0, "h_b": 10.0},
            {"age": NAN, "h_a": -3.0, "h_b": 400.0},
        ]
    )
    out = base.predict(new)
    assert list(out.columns) == list(P.PREDICTION_COLUMNS)
    # Young bin: all mass evenly on (0, 10]. Quantiles 1, 5, 8, 9, 9.5.
    assert out.iloc[0].tolist() == pytest.approx([0.5, 1.0, 1.0, 5.0, 8.0, 9.0, 9.5], abs=1e-5)
    # Pooled: 2/3 on (0, 10], 1/3 never. q10 = 10 * 0.1 / (2/3) = 1.5, q50 = 7.5, then the cap.
    assert out.iloc[1].tolist() == pytest.approx([1 / 3, 2 / 3, 1.5, 7.5, 365, 365, 365], abs=1e-5)
    # Unknown posting date: pooled too. Nothing recovers before the statement.
    assert out.iloc[2][["p_a", "p_b"]].tolist() == pytest.approx([0.0, 2 / 3], abs=1e-6)


def test_face_value() -> None:
    rows = frame([{"end_days": 30.0}, {"end_days": 400.0}, {"end_days": -5.0}, {"end_days": NAN}])
    out = P.FaceValue().predict(rows)
    assert out.iloc[0].tolist() == [1.0, 1.0, 30.0, 30.0, 30.0, 30.0, 30.0]
    assert out.iloc[1][list(P.QUANTILE_KEYS)].tolist() == [365.0] * 5  # kept within the cap
    assert out.iloc[2][list(P.QUANTILE_KEYS)].tolist() == [0.0] * 5  # stale at issue
    assert out.iloc[3].isna().all()  # no stated end, no output


def calibrator_rows() -> list[dict[str, Any]]:
    """Dated fitting statements in three forms, and two no-date ones.

    month_year / first (3 statements): stated end at 30 days; two recover in (20, 40], so their
    slip is in (-10, 10]; one is discontinued. month_year / second (1 statement): recovery in
    (50, 70], slip in (20, 40]. quarter / first (2 statements): slip in (0, 20]. year / first
    (1 statement): censored at 100, slip above 70.
    """
    cell = [recovered(20, 40), recovered(20, 40), discontinued(5, 9)]
    second = [recovered(50, 70, revision="second")]
    quarter = [recovered(30, 50, form="quarter"), recovered(30, 50, form="quarter")]
    year = [censored(100, form="year")]
    no_date = [
        recovered(0, 100, analysis_set="tbd", form="tbd", end_days=NAN, h_a=90.0, h_b=180.0),
        censored(200, analysis_set="silent", form="silent", end_days=NAN, h_a=90.0, h_b=180.0),
    ]
    return [*cell, *second, *quarter, *year, *no_date]


def calibrator_frame() -> pd.DataFrame:
    return frame(calibrator_rows())


def test_calibrator_backoff_cell_then_form_then_all_dated_forms() -> None:
    cal = P.fit_calibrator(calibrator_frame(), min_cell=3)
    assert cal.cell_counts[("month_year", "first")] == 3
    assert set(cal.cells) == {("month_year", "first")} and set(cal.forms) == {"month_year"}
    assert cal.basis("month_year", "first")[0] == "cell"
    assert cal.basis("month_year", "second")[0] == "form"  # 1 in the cell, 4 in the form
    assert cal.basis("quarter", "first")[0] == "all dated forms"  # 2 in the form
    assert cal.basis("tbd", "first")[0] == "all dated forms"  # not a dated form
    assert cal.basis("month_year", "first")[1].statements == 3
    assert cal.basis("month_year", "second")[1].statements == 4
    assert cal.basis("quarter", "first")[1].statements == cal.pooled.statements == 7
    assert P.BASES == ("cell", "form", "all dated forms")


def test_the_minimum_is_one_hundred_statements_at_every_level() -> None:
    # The registered minimum, through the defaults. month_year: 100 first statements (a cell of
    # its own) and 99 second ones (the form, which holds 199). quarter: 60 and 40, so neither
    # cell reaches 100 and the form holds exactly 100. year: 99 statements, all dated forms.
    dated = [
        *[recovered(20, 40)] * 100,
        *[recovered(20, 40, revision="second")] * 99,
        *[recovered(30, 50, form="quarter")] * 60,
        *[recovered(30, 50, form="quarter", revision="second")] * 40,
        *[recovered(30, 50, form="year")] * 99,
    ]
    no_date = {"analysis_set": "tbd", "form": "tbd", "end_days": NAN, "h_a": 90.0, "h_b": 180.0}
    young = [recovered(0, 100, age=5.0, **no_date)] * 100
    old = [recovered(0, 100, age=2000.0, **no_date)] * 99
    fit = frame([*dated, *young, *old])
    cal = P.fit_calibrator(fit)
    assert cal.min_cell == 100
    assert cal.basis("month_year", "first")[0] == "cell"
    assert cal.basis("month_year", "second")[0] == "form"
    assert [cal.basis("quarter", r)[0] for r in P.REVISIONS] == ["form"] * 3
    assert cal.basis("quarter", "first")[1].statements == 100
    assert cal.basis("year", "first")[0] == "all dated forms"
    assert cal.pooled.statements == 398
    assert [row["basis"] for row in P.backoff_cells(fit)] == [r["basis"] for r in cal.table()]
    # The listing-age bins follow the same minimum: 100 statements give a curve, 99 do not.
    assert set(cal.no_date.curves) == {P.ALL_AGES, P.AGE_LABELS[0]}
    assert cal.no_date.counts[P.AGE_LABELS[5]] == 99
    base = P.fit_base_rate(fit)
    assert base.min_cell == 100 and set(base.curves) == {P.ALL_AGES, P.AGE_LABELS[0]}
    assert (base.counts[P.AGE_LABELS[0]], base.counts[P.AGE_LABELS[5]]) == (498, 99)


def test_calibrator_leaves_out_statements_that_are_stale_at_issue() -> None:
    # Four statements whose stated end was already past when they were issued, in the form and
    # revision bucket of the three-statement cell: they are not dated fitting statements, so no
    # count, basis or curve changes.
    stale = [recovered(20, 40, analysis_set="stale", end_days=-5.0, h_a=-5.0, h_b=85.0)] * 4
    plain = P.fit_calibrator(calibrator_frame(), min_cell=3)
    with_stale = frame([*calibrator_rows(), *stale])
    cal = P.fit_calibrator(with_stale, min_cell=3)
    assert cal.cell_counts == plain.cell_counts and cal.pooled.statements == 7
    assert cal.table() == plain.table()
    assert P.backoff_cells(with_stale, 3) == P.backoff_cells(calibrator_frame(), 3)
    assert cal.no_date.table() == plain.no_date.table()
    # A stale statement is still given a prediction, from the estimate of its cell.
    out = cal.predict(with_stale.iloc[[-1]])
    assert out["p_a"].iloc[0] == pytest.approx(1 / 3, abs=1e-6)


def test_rules_plus_slip_on_a_hand_computed_cell() -> None:
    cal = P.fit_calibrator(calibrator_frame(), min_cell=3)
    # The cell's slip curve: 2/3 spread evenly on (-10, 10], 1/3 never (the discontinuation).
    slip = cal.cells[("month_year", "first")].slip
    assert slip.cdf([-10.0, 0.0, 10.0, 90.0]) == pytest.approx([0, 1 / 3, 2 / 3, 2 / 3], abs=1e-6)
    out = cal.predict(frame([{"end_days": 30.0, "h_a": 30.0, "h_b": 120.0}]))
    # P(E_end) = F_slip(0) = 1/3 and P(E_end90) = F_slip(90) = 2/3. Slip quantiles: 0.1 at
    # -10 + 20 * 0.1 / (2/3) = -7, 0.5 at 5; 0.8 and above are never reached. Plus 30 days.
    assert out.iloc[0].tolist() == pytest.approx([1 / 3, 2 / 3, 23, 35, 365, 365, 365], abs=1e-4)


def test_calibrator_on_a_reading_that_differs_from_the_rule() -> None:
    cal = P.fit_calibrator(calibrator_frame(), min_cell=3)
    rows = frame([{"end_days": 30.0, "h_a": 30.0, "h_b": 120.0}] * 3)
    # A reading that ends 20 days later than the rule's: F_slip(30 - 50) = 0 and F_slip(70).
    # A reading that ends 25 days earlier: F_slip(25) and F_slip(115), both 2/3; the quantiles
    # start at 5 - 7 = -2 days, which is kept at 0.
    reading = pd.Series([50.0, 5.0, NAN], index=rows.index)
    out = cal.predict(rows, reading)
    assert out.iloc[0].tolist() == pytest.approx([0, 2 / 3, 43, 55, 365, 365, 365], abs=1e-4)
    assert out.iloc[1].tolist() == pytest.approx([2 / 3, 2 / 3, 0, 10, 365, 365, 365], abs=1e-4)
    # ABSTAIN: the no-date table (one recovery in (0, 100], one censored at 200), read at the
    # statement's own horizons: F(30) = 0.15 and F(120) = 0.5.
    fallback = cal.no_date.predict(rows.iloc[[2]])
    assert out.iloc[2].tolist() == pytest.approx(fallback.iloc[0].tolist())
    assert out.iloc[2][["p_a", "p_b"]].tolist() == pytest.approx([0.15, 0.5], abs=1e-6)


def test_calibrator_table() -> None:
    rows = P.fit_calibrator(calibrator_frame(), min_cell=3).table()
    assert [(r["form"], r["revision"]) for r in rows[:3]] == [
        ("month_year", "first"),
        ("month_year", "second"),
        ("month_year", "third or later"),
    ]
    assert len(rows) == 3 * 3  # three forms by three revision buckets
    first, second, third = rows[:3]
    assert (first["basis"], first["cell_statements"], first["statements"]) == ("cell", 3, 3)
    assert first["share_by_stated_end"] == pytest.approx(1 / 3, abs=1e-6)
    assert first["share_by_stated_end_90"] == pytest.approx(2 / 3, abs=1e-6)
    # Days to recovery in the cell: 2/3 evenly on (20, 40], so the median is 20 + 20 * 0.75.
    assert first["median_days_to_recovery"] == pytest.approx(35.0, abs=1e-4)
    assert (second["basis"], second["cell_statements"], second["statements"]) == ("form", 1, 4)
    assert (third["basis"], third["cell_statements"]) == ("form", 0)
    year = next(r for r in rows if r["form"] == "year" and r["revision"] == "first")
    assert (year["basis"], year["statements"]) == ("all dated forms", 7)


def test_backoff_from_counts_alone_agrees_with_the_fitted_tables() -> None:
    fit = calibrator_frame()
    for min_cell in (1, 2, 3, 5, 100):
        cal = P.fit_calibrator(fit, min_cell=min_cell)
        counted = P.backoff_cells(fit, min_cell)
        assert counted == [{key: row[key] for key in counted[0]} for row in cal.table()]
        assert P.backoff_bins(fit, P.NO_DATE_SETS, min_cell) == cal.no_date.table()
        assert P.backoff_bins(fit, min_cell=min_cell) == P.fit_base_rate(fit, min_cell).table()


def test_calibrator_needs_dated_and_no_date_fitting_statements() -> None:
    with pytest.raises(ValueError, match="no dated fitting statement"):
        P.fit_calibrator(frame([recovered(0, 10, analysis_set="tbd")]))
    with pytest.raises(ValueError, match="no fitting statement"):
        P.fit_calibrator(frame([recovered(0, 10)]))


# --------------------------------------------------------------------------------------------
# Resampling
# --------------------------------------------------------------------------------------------


def test_cluster_draws_are_deterministic_and_resample_every_cluster_slot() -> None:
    first, again = P.cluster_draws(7, draws=50), P.cluster_draws(7, draws=50)
    assert first.shape == (50, 7) and (first == again).all()
    assert (first.sum(axis=1) == 7).all()
    assert not (first == P.cluster_draws(7, draws=50, seed=1)).all()


def test_cluster_sums_follow_the_sorted_cluster_ids() -> None:
    sums, sizes = P.cluster_sums([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], ["b", "a", "b"])
    assert sums.tolist() == [[3.0, 4.0], [6.0, 8.0]] and sizes.tolist() == [1.0, 2.0]
    with pytest.raises(ValueError, match="a loss is missing"):
        P.cluster_sums([1.0, NAN], ["a", "b"])
    # A statement with no episode is refused: blank ids would be resampled as one cluster.
    for ids in (["a", ""], ["a", None]):
        with pytest.raises(ValueError, match="no cluster"):
            P.cluster_sums([1.0, 2.0], ids)
        with pytest.raises(ValueError, match="no cluster"):
            P.bootstrap_means([1.0, 2.0], ids, draws=10)


def test_bootstrap_on_two_clusters() -> None:
    # Cluster a holds two statements with loss 1, cluster b one with loss 0. A draw takes a
    # twice (mean 1), a and b (mean 2/3) or b twice (mean 0).
    values, clusters = [1.0, 1.0, 0.0], ["a", "a", "b"]
    means = P.bootstrap_means(values, clusters, draws=200)[:, 0]
    taken = P.cluster_draws(2, draws=200)
    expected = {2: 1.0, 1: 2 / 3, 0: 0.0}
    assert means == pytest.approx([expected[int(k)] for k in taken[:, 0]])
    assert {round(float(m), 6) for m in means} == {1.0, round(2 / 3, 6), 0.0}
    assert (means == P.bootstrap_means(values, clusters, draws=200)[:, 0]).all()
    assert (means != P.bootstrap_means(values, clusters, draws=200, seed=3)[:, 0]).any()


def test_bootstrap_is_paired_across_predictors() -> None:
    rng = np.random.default_rng(P.SEED)
    first = rng.random(40)
    clusters = [f"e{k % 6}" for k in range(40)]
    means = P.bootstrap_means(np.column_stack([first, first + 0.1]), clusters, draws=300)
    # The second predictor's loss is 0.1 above the first on every statement, so on every draw.
    assert means[:, 1] - means[:, 0] == pytest.approx(np.full(300, 0.1))
    assert means[:, 0].std() > 0


def test_interval_and_p_values() -> None:
    assert P.interval(np.arange(101.0)) == pytest.approx([2.5, 97.5])
    assert P.interval(np.arange(101.0), 0.90) == pytest.approx([5.0, 95.0])
    # Four draws, one at or below zero and three at or above it:
    # one-sided (1 + 1) / 5; two-sided 2 * min(2/5, 4/5).
    p = P.p_values([1.0, 2.0, -1.0, 3.0])
    assert p == {"one_sided": pytest.approx(0.4), "two_sided": pytest.approx(0.8)}
    assert P.p_values([1.0] * 9)["one_sided"] == pytest.approx(0.1)
    assert P.p_values([0.0] * 9)["two_sided"] == 1.0
