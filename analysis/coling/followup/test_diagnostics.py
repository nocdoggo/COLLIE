"""A23 diagnostics fixtures: the flat mask, saturation, tolerance, and the paired per-horizon
difference vector with its episode-cluster interval and its exactness refusals. Everything
here is invented; no study file is opened."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.coling import predictors as P
from analysis.coling.followup import diagnostics as dg

BRACKETS = ((-7.0, 0.0, 0.2), (0.0, 7.0, 0.3), (7.0, 14.0, 0.0), (14.0, 21.0, 0.5))


def _slip(brackets=BRACKETS) -> P.Turnbull:
    left = [b[0] for b in brackets]
    right = [b[1] for b in brackets]
    mass = np.asarray([b[2] for b in brackets], dtype=float)
    mass = mass / mass.sum()
    return P.Turnbull(np.asarray(left), np.asarray(right), mass, 100, 1, 0.0)


def _calibrator() -> P.SlipCalibrator:
    slip = _slip()
    estimate = P.Estimate(100, slip, slip)
    return P.SlipCalibrator(
        cells={("dated", "initial"): estimate}, forms={}, pooled=estimate,
        cell_counts={("dated", "initial"): 100}, no_date=None, min_cell=1)


def test_the_flat_mask_names_the_blind_regions_of_a_known_curve():
    slip = _slip()
    u = np.array([-20.0, -7.0, 4.0, 8.0, 16.0, 30.0])
    # -20 is below the support; -7 sits at its left corner; 4 rises; 8 is on the massless
    # bracket; 16 rises on the steepest bracket; 30 is beyond the top corner.
    assert dg.flat_mask(slip, u).tolist() == [True, True, False, True, False, True]
    zero, reached = dg.saturated(slip, u)
    assert zero.tolist() == [True, True, False, False, False, False]
    assert reached.tolist() == [False, False, False, False, False, True]


def test_the_tolerance_follows_the_averaged_loss_and_names_its_scope():
    record = dg.tolerance_of(_slip())
    slope = 0.5 / 7.0
    assert record["steepest_slope"] == pytest.approx(slope)
    assert record["tolerance_days_single_horizon"] == pytest.approx(dg.MARGIN / slope)
    assert record["tolerance_days_both_horizons"] == pytest.approx(dg.MARGIN / (2.0 * slope))
    assert record["widest_bracket_days"] == pytest.approx(7.0)


def test_flat_record_counts_per_horizon_and_holds_the_unparsed_apart():
    frame = pd.DataFrame(
        {"form": ["dated"] * 3, "revision": ["initial"] * 3,
         "h_a": [0.0, 14.0, 5.0], "h_b": [90.0, 16.0, 6.0]},
        index=["A", "B", "C"])
    days = pd.Series([20.0, 10.0, np.nan], index=["A", "B", "C"])
    record = dg.flat_record(_calibrator(), frame, days)
    assert record["readings"] == 2 and record["no_stated_period"] == 1
    assert record["evaluable_pairs"] == 4 and record["flat_pairs"] == 2
    assert record["flat_share"] == pytest.approx(0.5)
    assert record["by_horizon"]["h_a"] == {"evaluable": 2, "flat": 1,
                                          "flat_share": pytest.approx(0.5)}
    assert record["by_basis"]["cell:dated:initial"] == {"evaluable_pairs": 4, "flat_pairs": 2}
    assert record["tolerance_by_basis"]["cell:dated:initial"]["tolerance_days_single_horizon"]


def _contrast_fixture():
    ids = ["s1", "s2", "s3", "s4"]
    rows = pd.DataFrame(
        {"y_a": [0.0, 0.0, 1.0, 1.0], "y_b": [1.0, 0.0, 1.0, 0.0],
         "scoreable": [True] * 4, "episode_id": ["e1", "e1", "e2", "e2"]}, index=ids)
    predictions = {
        "rule": pd.DataFrame(
            {"p_a": [0.2, 0.4, 0.6, 0.8], "p_b": [0.5, 0.5, 0.5, 0.5]}, index=ids),
        "model:c": pd.DataFrame(
            {"p_a": [0.4, 0.2, 0.6, 0.8], "p_b": [0.7, 0.3, 0.5, 0.5]}, index=ids),
    }
    return rows, predictions


def test_the_paired_vector_decomposes_and_the_average_is_the_registered_contrast():
    rows, predictions = _contrast_fixture()
    terms_a, terms_b, clusters = dg.horizon_terms(rows, predictions, "rule", "model:c",
                                                  rows.index)
    assert terms_a.tolist() == pytest.approx([-0.12, 0.12, 0.0, 0.0])
    assert terms_b.tolist() == pytest.approx([0.16, 0.16, 0.0, 0.0])
    record = dg.cluster_interval(terms_a, terms_b, clusters)
    # the horizon-a difference cancels to exactly zero while the average is +0.04: the
    # projection the diagnostic exists to expose
    assert record["d_horizon_a"] == pytest.approx(0.0)
    assert record["d_horizon_b"] == pytest.approx(0.08)
    assert record["d_averaged"] == pytest.approx(0.04)
    # every draw is a mean of whole episodes: the interval endpoints are among the
    # episode-level averages {0.08, 0.04, 0.0} at each horizon
    for horizon in ("d_horizon_a", "d_horizon_b", "d_averaged"):
        low, high = record["interval"][horizon]
        assert low <= record[horizon] <= high


def test_a_contrast_that_disagrees_with_its_record_refuses():
    rows, predictions = _contrast_fixture()
    with pytest.raises(SystemExit):
        dg.contrast_record(rows, predictions, "rule", "model:c", rows.index, 3, 0.04)
    with pytest.raises(SystemExit):
        dg.contrast_record(rows, predictions, "rule", "model:c", rows.index, 4, 0.05)
    record = dg.contrast_record(rows, predictions, "rule", "model:c", rows.index, 4, 0.04)
    assert record["statements"] == 4 and record["episodes"] == 2
    assert record["scoreable_set_sha256"] == dg.sha256(
        "\n".join(sorted(rows.index)).encode()).hexdigest()
