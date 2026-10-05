"""Tests for the size check of the confirmatory test procedures (``size_check.py``).

The procedures are checked on inputs small enough to work out by hand or to recompute draw by
draw: the sign-flip test over all sign vectors and with random ones, the cluster-robust t tests
(equal episodes give the t test on episode means; unequal ones are worked out by hand; the
Satterthwaite degrees of freedom are recomputed from the statement-level matrices), the
percentile p-values against ``predictors.py`` on the same input, the bootstrap-t against a
resampling written out statement by statement, the BCa interval against its textbook formula
and against scipy, the larger of two p-values against its two parts, and Holm's rule. The
generators are checked for what they promise: whole blocks of one donor episode, a null that
holds exactly (also when most episodes are all zero), an alternative that moves every statement
(or, when most episodes are all zero, the statements of the others), the dev marginal
distribution and the target within-episode correlation. The simulation is reproducible, does
not depend on the number of worker processes, changes its data sets with the master seed of the
streams and with nothing else, keeps its size under a null and detects a planted effect. The
command line runs on the synthetic statement table of ``test_power.py``, refuses a power
report written for other proxy pairs, and writes nothing when an input changes during the run.

The last test reads the files in the repository and is skipped when they are absent. It fails
until the full command is rerun after any change to its inputs or to ``size_check.py``.

Run::

    PYTHONPATH=. python -m pytest analysis/coling/test_size_check.py -q -p no:cacheprovider
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.special import ndtr, ndtri

from analysis.coling import dataset as D
from analysis.coling import power as W
from analysis.coling import predictors as P
from analysis.coling import size_check as Z
from analysis.coling.test_power import counts_of, eligible_of, synthetic_table


def episodes(sizes: list[int]) -> list[str]:
    """Episode ids for statements in episodes of the given sizes."""
    return [f"e{k:03d}" for k, size in enumerate(sizes) for _ in range(size)]


def skewed(sizes: list[int], seed: int = 0) -> tuple[np.ndarray, list[str]]:
    """Skewed paired differences with an episode effect, and their episode ids."""
    rng = np.random.default_rng([P.SEED, seed])
    effect = np.repeat(rng.normal(0.0, 0.5, len(sizes)), sizes)
    return effect + rng.exponential(1.0, sum(sizes)) - 0.8, episodes(sizes)


# --------------------------------------------------------------------------------------------
# The sign-flip test
# --------------------------------------------------------------------------------------------


def test_flip_matrix_is_exhaustive_for_few_episodes_and_random_for_many() -> None:
    signs, exhaustive = Z.flip_matrix(3, 10_000, P.SEED)
    assert exhaustive and signs.shape == (8, 3)
    assert {tuple(row) for row in signs} == set(itertools.product((1.0, -1.0), repeat=3))
    signs, exhaustive = Z.flip_matrix(30, 500, P.SEED)
    assert not exhaustive and signs.shape == (500, 30) and set(np.unique(signs)) == {-1.0, 1.0}
    assert abs(signs.mean()) < 0.03
    rng = np.random.default_rng(P.SEED)
    assert np.array_equal(signs, 1.0 - 2.0 * rng.integers(0, 2, size=(500, 30)))
    # 2^13 = 8,192 sign vectors are at most 10,000 flips; 2^14 are not.
    assert Z.flip_matrix(13, 10_000, P.SEED)[1] and not Z.flip_matrix(14, 10_000, P.SEED)[1]


def test_sign_flip_by_hand() -> None:
    # Episode sums 1, 2 and 4 (sizes 1, 2, 1). The eight signed sums are +-1 +-2 +-4: 7, 5, 3,
    # 1, -1, -3, -5, -7. Only one is at least 7, all are at most 7, two are 7 in size.
    out = Z.contrast_tests([1.0, 1.0, 1.0, 4.0], ["a", "b", "b", "c"])["sign_flip"]
    assert out["p_upper"] == 1 / 8 and out["p_lower"] == 1.0 and out["p_two_sided"] == 2 / 8
    # Means of the flipped episodes over the seven non-empty sets: a 1, b 1, c 4, ab 1,
    # ac 5/2, bc 2, abc 7/4. Sorted: 1, 1, 1, 1.75, 2, 2.5, 4.
    means = np.array([1.0, 1.0, 1.0, 1.75, 2.0, 2.5, 4.0])
    assert [out["low"], out["high"]] == pytest.approx(list(np.quantile(means, [0.025, 0.975])))
    assert out["high"] == pytest.approx(2.5 + 0.85 * 1.5)
    # Against zero differences the test says nothing.
    flat = Z.contrast_tests([0.0, 0.0, 0.0], ["a", "b", "c"])
    for name in ("sign_flip", "sign_flip_t"):
        assert flat[name]["p_upper"] == flat[name]["p_lower"] == flat[name]["p_two_sided"] == 1.0


def test_sign_flip_without_variance_counts_the_sign_vector_that_flips_nothing() -> None:
    # Every difference is 0.25: no variance, and an infinite statistic. Of the 32 sign vectors
    # of five episodes only the one that flips nothing gives that statistic again, and the one
    # that flips everything its negative: an exact test cannot give a p-value below 1 / 32.
    out = Z.contrast_tests(np.full(14, 0.25), episodes([3, 1, 4, 1, 5]), draws=400)
    for name in ("sign_flip", "sign_flip_t"):
        assert out[name]["p_upper"] == 1 / 32 and out[name]["p_lower"] == 1.0
        assert out[name]["p_two_sided"] == 2 / 32
    # The bootstrap-t rejects (no draw has a statistic as large); the larger of the two does not.
    assert out["studentised"]["p_upper"] == 1 / 401
    assert out["max_t"]["p_upper"] == 1 / 32 and out["max_t"]["p_two_sided"] == 2 / 32
    # With random sign vectors none of them reproduces the observed statistic.
    many = Z.contrast_tests(np.full(60, 0.25), episodes([3] * 20), draws=400, flips=400)
    assert many["sign_flip_t"]["p_upper"] == 1 / 401 and many["sign_flip_t"]["p_lower"] == 1.0


def test_studentised_sign_flip_against_flipped_statement_tables() -> None:
    for sizes, flips in (
        ([3, 1, 4, 2, 6], 10_000),
        ([3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9], 300),
    ):
        values, clusters = skewed(sizes, seed=11)
        values = values + 0.5
        names = sorted(set(clusters))
        signs, exhaustive = Z.flip_matrix(len(names), flips, P.SEED)
        assert exhaustive == (len(sizes) == 5)
        observed = W.clustered_variance(values, clusters)
        t = observed["delta"] / observed["se_clustered"]
        flipped = []
        for row in signs:
            sign = dict(zip(names, row, strict=True))
            star = W.clustered_variance(
                [sign[c] * v for v, c in zip(values, clusters, strict=True)], clusters
            )
            flipped.append(star["delta"] / star["se_clustered"])
        flipped = np.array(flipped)
        one = 0 if exhaustive else 1
        out = Z.contrast_tests(values, clusters, flips=flips)["sign_flip_t"]
        close = 1e-9 * abs(flipped).max()
        assert out["p_upper"] == (one + (flipped >= t - close).sum()) / (len(signs) + one)
        assert out["p_lower"] == (one + (flipped <= t + close).sum()) / (len(signs) + one)
        assert out["p_two_sided"] == (one + (abs(flipped) >= abs(t) - close).sum()) / (
            len(signs) + one
        )
        assert out["p_two_sided"] < 1 and np.isnan(out["low"]) and np.isnan(out["high"])


def test_sign_flip_with_random_signs_uses_the_count_formula() -> None:
    values, clusters = skewed([3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3], seed=1)
    out = Z.contrast_tests(values + 0.4, clusters, flips=400)["sign_flip"]
    sums, _ = P.cluster_sums(values + 0.4, clusters)
    signs, exhaustive = Z.flip_matrix(16, 400, P.SEED)
    assert not exhaustive
    flipped = [float(row @ sums[:, 0]) for row in signs]
    observed = float(sums.sum())
    assert out["p_upper"] == (1 + sum(f >= observed for f in flipped)) / 401
    assert out["p_lower"] == (1 + sum(f <= observed for f in flipped)) / 401
    assert out["p_two_sided"] == (1 + sum(abs(f) >= abs(observed) for f in flipped)) / 401
    # The interval is the set of null values that neither one-sided test rejects at 0.025: at
    # a value just inside an end the smaller one-sided p-value is above 0.025, just outside it
    # is below (the count formula moves the ends by at most one flip in 400).
    width = out["high"] - out["low"]
    for end, sign in ((out["low"], 1), (out["high"], -1)):
        inside = Z.contrast_tests(values + 0.4, clusters, null=end + sign * 0.05 * width, flips=400)
        outside = Z.contrast_tests(
            values + 0.4, clusters, null=end - sign * 0.05 * width, flips=400
        )
        assert min(inside["sign_flip"][k] for k in ("p_upper", "p_lower")) > 0.025
        assert min(outside["sign_flip"][k] for k in ("p_upper", "p_lower")) < 0.025


# --------------------------------------------------------------------------------------------
# The cluster-robust t tests
# --------------------------------------------------------------------------------------------


def test_robust_t_with_equal_episodes_is_the_t_test_on_episode_means() -> None:
    values, clusters = skewed([4] * 7, seed=2)
    means = values.reshape(7, 4).mean(axis=1)
    out = Z.contrast_tests(values, clusters)
    two = stats.ttest_1samp(means, 0.0)
    low, high = two.confidence_interval(0.95)
    for name in ("t_cr1", "t_cr2", "t_cr2_icc", "t_cr3"):
        assert out[name]["p_two_sided"] == pytest.approx(two.pvalue)
        greater = stats.ttest_1samp(means, 0.0, alternative="greater").pvalue
        assert out[name]["p_upper"] == pytest.approx(greater)
        assert out[name]["p_lower"] == pytest.approx(1 - greater)
        assert [out[name]["low"], out[name]["high"]] == pytest.approx([low, high])


def test_robust_t_by_hand_with_unequal_episodes() -> None:
    # Episodes a = (1, 1, 1), b = (0), c = (0, 2): N = 6, delta = 5/6, and
    # e = (3 - 2.5, 0 - 5/6, 2 - 10/6) = (1/2, -5/6, 1/3); e^2 = (1/4, 25/36, 1/9).
    # CR1: 3/2 * (1/4 + 25/36 + 1/9) / 36 = 3/2 * (38/36) / 36.
    # CR2: (1/4 / (1/2) + 25/36 / (5/6) + 1/9 / (2/3)) / 36 = (1/2 + 5/6 + 1/6) / 36 = 1.5 / 36.
    # CR3: 2/3 * (1/4 / (1/4) + 25/36 / (25/36) + 1/9 / (4/9)) / 36 = 2/3 * 2.25 / 36.
    values, clusters = [1.0, 1.0, 1.0, 0.0, 0.0, 2.0], ["a", "a", "a", "b", "c", "c"]
    out = Z.robust_t(Z.episode_sums(values, clusters))
    delta = 5 / 6
    variance = {"t_cr1": 1.5 * (38 / 36) / 36, "t_cr2": 1.5 / 36, "t_cr3": (2 / 3) * 2.25 / 36}
    assert np.sqrt(variance["t_cr1"]) == pytest.approx(
        W.clustered_variance(values, clusters)["se_clustered"]
    )
    for name in ("t_cr1", "t_cr3"):
        t = delta / np.sqrt(variance[name])
        assert out[name][0, 0] == pytest.approx(stats.t.sf(t, 2))
        assert out[name][2, 0] == pytest.approx(2 * stats.t.sf(t, 2))
        reach = stats.t.ppf(0.975, 2) * np.sqrt(variance[name])
        assert list(out[name][3:, 0]) == pytest.approx([delta - reach, delta + reach])
    df = float(Z.satterthwaite(Z.satterthwaite_terms(np.array([[3.0], [1.0], [2.0]])))[0])
    assert 1.0 < df < 2.0  # unequal episodes: fewer than G - 1 = 2
    assert out["t_cr2"][0, 0] == pytest.approx(stats.t.sf(delta / np.sqrt(1.5 / 36), df))


def statement_level_df(sizes: list[int], rho: float) -> float:
    """The Satterthwaite degrees of freedom of the bias-reduced variance, from the matrices
    over statements: ``tr(M)^2 / tr(M^2)`` with ``M_gh = a_g' V a_h``."""
    n, groups = sum(sizes), len(sizes)
    member = np.zeros((n, groups))
    member[np.arange(n), np.repeat(np.arange(groups), sizes)] = 1.0
    residual_maker = np.eye(n) - np.ones((n, n)) / n
    a = residual_maker @ member / (n * np.sqrt(1 - np.asarray(sizes) / n))
    v = (1 - rho) * np.eye(n) + rho * member @ member.T
    m = a.T @ v @ a
    return float(np.trace(m) ** 2 / np.trace(m @ m))


def test_satterthwaite_degrees_of_freedom_from_the_statement_level_matrices() -> None:
    sizes = [3, 1, 2, 5, 9, 1, 4]
    terms = Z.satterthwaite_terms(np.asarray(sizes, dtype=float)[:, None])
    for rho in (0.0, 0.1, 0.5, 1.0):
        assert float(Z.satterthwaite(terms, rho)[0]) == pytest.approx(
            statement_level_df(sizes, rho)
        )
    # The more the statements of an episode move together, the more the large episodes weigh.
    assert Z.satterthwaite(terms, 0.5)[0] < Z.satterthwaite(terms, 0.0)[0] < len(sizes) - 1
    equal = Z.satterthwaite_terms(np.full((6, 1), 4.0))
    for rho in (0.0, 0.3, 1.0):
        assert float(Z.satterthwaite(equal, rho)[0]) == pytest.approx(5.0)
    # Two columns of sizes at once.
    both = Z.satterthwaite_terms(np.column_stack([sizes, sizes[::-1]]).astype(float))
    assert list(Z.satterthwaite(both, 0.2)) == pytest.approx([statement_level_df(sizes, 0.2)] * 2)


def test_standard_error_and_correlation_are_those_of_the_power_module() -> None:
    values, clusters = skewed([5, 1, 8, 2, 13, 3, 1, 1, 21], seed=3)
    sums = Z.episode_sums(values, clusters)
    reference = W.clustered_variance(values, clusters)
    assert float(sums.delta[0]) == pytest.approx(reference["delta"])
    assert float(Z.robust_se(sums)[0]) == pytest.approx(reference["se_clustered"])
    assert float(Z.within_correlation(sums)[0]) == pytest.approx(reference["icc"])
    assert reference["icc"] > 0
    # The second bias-reduced test takes its degrees of freedom at that correlation.
    terms = Z.satterthwaite_terms(sums.size)
    df = float(Z.satterthwaite(terms, reference["icc"])[0])
    assert df < float(Z.satterthwaite(terms)[0]) - 0.5
    out = Z.robust_t(sums)
    variance = float((sums.residual**2 / (1 - sums.size / len(values))).sum()) / len(values) ** 2
    t = reference["delta"] / np.sqrt(variance)
    assert out["t_cr2_icc"][2, 0] == pytest.approx(2 * stats.t.sf(abs(t), df))
    assert out["t_cr2"][2, 0] == pytest.approx(2 * stats.t.sf(abs(t), Z.satterthwaite(terms)[0]))
    assert out["t_cr2_icc"][2, 0] > out["t_cr2"][2, 0]
    # Independent statements: the estimate is kept at zero when the design effect is below 1.
    alternating = np.tile([1.0, -1.0], 10)
    assert float(Z.within_correlation(Z.episode_sums(alternating, episodes([2] * 10)))[0]) == 0.0


# --------------------------------------------------------------------------------------------
# The bootstrap procedures
# --------------------------------------------------------------------------------------------


def test_percentile_is_the_registered_p_value_on_the_same_input() -> None:
    for seed, draws in ((4, 2_000), (5, P.DRAWS)):
        values, clusters = skewed([5, 1, 8, 2, 13, 3, 1, 1, 21, 4, 4], seed=seed)
        values = values - values.mean() + 0.12
        registered = P.bootstrap_means(values, clusters, draws, P.SEED)[:, 0]
        means, _ = Z.bootstrap(Z.episode_sums(values, clusters), draws, P.SEED)
        assert np.array_equal(means[:, 0], registered)
        out = Z.contrast_tests(values, clusters, draws=draws)["percentile"]
        p = P.p_values(registered)
        assert out["p_upper"] == p["one_sided"] and out["p_two_sided"] == p["two_sided"]
        assert out["p_lower"] == P.p_values(-registered)["one_sided"]
        assert [out["low"], out["high"]] == P.interval(registered, 0.95)
        assert 0 < out["p_upper"] < 0.5 < out["p_lower"]


def test_percentile_of_several_columns_is_the_registered_one_column_by_column() -> None:
    values, clusters = skewed([5, 1, 8, 2, 13, 3, 1], seed=6)
    two = np.column_stack([values, 0.3 - values**2])
    means, _ = Z.bootstrap(Z.episode_sums(two, clusters), 500, P.SEED)
    assert np.array_equal(means, P.bootstrap_means(two, clusters, 500, P.SEED))
    out = Z.procedures(Z.episode_sums(two, clusters), draws=500, flips=500)["percentile"]
    for k in range(2):
        p = P.p_values(means[:, k])
        assert (out[0, k], out[2, k]) == (p["one_sided"], p["two_sided"])


def resampled_t(values: np.ndarray, clusters: list[str], draws: int) -> tuple[np.ndarray, float]:
    """The bootstrap-t statistics from resampled statement tables, draw by draw, and the
    observed statistic."""
    names = sorted(set(clusters))
    rows = {name: [i for i, c in enumerate(clusters) if c == name] for name in names}
    observed = W.clustered_variance(values, clusters)
    out = []
    for taken in P.cluster_draws(len(names), draws, P.SEED):
        picked, labels = [], []
        for name, times in zip(names, taken, strict=True):
            for copy in range(times):
                picked += rows[name]
                labels += [f"{name}/{copy}"] * len(rows[name])
        star = W.clustered_variance(values[picked], labels)
        out.append((star["delta"] - observed["delta"]) / star["se_clustered"])
    return np.array(out), observed["delta"] / observed["se_clustered"]


def test_studentised_bootstrap_against_resampled_statement_tables() -> None:
    values, clusters = skewed([5, 1, 8, 2, 13, 3, 1, 4], seed=7)
    values = values + 0.3
    t, observed = resampled_t(values, clusters, 300)
    assert np.isfinite(t).all()
    out = Z.contrast_tests(values, clusters, draws=300)
    equal, symmetric = out["studentised"], out["studentised_symmetric"]
    upper, lower = (1 + (t >= observed).sum()) / 301, (1 + (t <= observed).sum()) / 301
    assert equal["p_upper"] == pytest.approx(upper) and equal["p_lower"] == pytest.approx(lower)
    assert equal["p_two_sided"] == pytest.approx(min(1.0, 2 * min(upper, lower)))
    assert symmetric["p_two_sided"] == pytest.approx((1 + (abs(t) >= abs(observed)).sum()) / 301)
    assert (symmetric["p_upper"], symmetric["p_lower"]) == (equal["p_upper"], equal["p_lower"])
    reference = W.clustered_variance(values, clusters)
    delta, se = reference["delta"], reference["se_clustered"]
    low, high = np.quantile(t, [0.025, 0.975])
    assert [equal["low"], equal["high"]] == pytest.approx([delta - high * se, delta - low * se])
    reach = np.quantile(abs(t), 0.95)
    assert [symmetric["low"], symmetric["high"]] == pytest.approx(
        [delta - reach * se, delta + reach * se]
    )
    # Right-skewed differences: the equal-tailed interval reaches further down than up.
    assert delta - equal["low"] != pytest.approx(equal["high"] - delta, rel=0.05)


def test_a_draw_that_ties_with_the_observed_statistic_counts_on_both_sides() -> None:
    # Three episodes of one statement: -1, 0 and 1. The estimate and its statistic are zero. A
    # draw that takes the first and the third equally often (each of the three once, or the
    # second three times: 7 draws in 27) has a mean of zero too, and its statistic ties with
    # the observed one. As in the registered count of the plan, a tie counts for both sides.
    values, clusters, draws = np.array([-1.0, 0.0, 1.0]), ["a", "b", "c"], 2_000
    taken = P.cluster_draws(3, draws, P.SEED)
    ties = int((taken[:, 0] == taken[:, 2]).sum())
    assert ties / draws == pytest.approx(7 / 27, abs=0.03)
    out = Z.contrast_tests(values, clusters, draws=draws)
    for name in ("percentile", "studentised"):
        both = out[name]["p_upper"] + out[name]["p_lower"]
        assert both == pytest.approx((2 + draws + ties) / (draws + 1), abs=1e-12)
        assert out[name]["p_upper"] == pytest.approx(out[name]["p_lower"], abs=0.05)
    assert out["studentised_symmetric"]["p_two_sided"] == 1.0
    assert out["max_t"]["p_two_sided"] == 1.0 and out["max_t"]["p_upper"] > 0.5


def test_an_undefined_interval_end_is_unbounded() -> None:
    # Differences other than zero in two of eighteen episodes. A draw that takes neither (one in
    # eight) has no variance and a mean of zero, below the estimate: its statistic is minus
    # infinity. The 2.5% quantile of the statistics then lies between two such draws.
    sizes = [1, 1, 2, 3, 5, 8, 13, 21, 2, 2, 4, 30, 1, 6, 9, 3, 2, 17]
    clusters = episodes(sizes)
    values = np.array([0.2 if c == "e011" else -0.05 if c == "e006" else 0.0 for c in clusters])
    neither = P.cluster_draws(len(sizes), 400, P.SEED)[:, [6, 11]].sum(axis=1) == 0
    assert 0.05 < neither.mean() < 0.25 and values.mean() > 0
    out = Z.contrast_tests(values, clusters, draws=400)
    equal, symmetric = out["studentised"], out["studentised_symmetric"]
    assert np.isfinite(equal["low"]) and equal["low"] < values.mean() and equal["high"] == np.inf
    assert (symmetric["low"], symmetric["high"]) == (-np.inf, np.inf)
    # None of those draws counts for a larger statistic, all of them for a smaller one.
    assert equal["p_upper"] <= (1 + (~neither).sum()) / 401
    assert equal["p_lower"] >= (1 + neither.sum()) / 401
    # Both count as unbounded intervals that cover, and neither enters the mean width.
    result = Z.procedures(Z.episode_sums(values, clusters), draws=400, flips=400)
    counted = Z.tally(result, truth=0.0)
    for name in ("studentised", "studentised_symmetric"):
        assert list(counted[name][6:]) == [1.0, 0.0, 1.0]
    assert counted["percentile"][8] == 0.0


def test_bca_by_its_formula() -> None:
    values, clusters = skewed([5, 1, 8, 2, 13, 3, 1, 4, 6, 2], seed=8)
    values = values + 0.25
    draws = 4_000
    means = P.bootstrap_means(values, clusters, draws, P.SEED)[:, 0]
    delta = values.mean()
    z0 = ndtri((means < delta).mean())
    names = sorted(set(clusters))
    left = np.array(
        [np.mean([v for v, c in zip(values, clusters, strict=True) if c != name]) for name in names]
    )
    away = left.mean() - left
    a = (away**3).sum() / (6 * (away**2).sum() ** 1.5)
    assert float(Z.acceleration(Z.episode_sums(values, clusters))[0]) == pytest.approx(a)
    assert a != pytest.approx(0.0, abs=1e-3) and z0 != pytest.approx(0.0, abs=1e-3)
    levels = [ndtr(z0 + (z0 + z) / (1 - a * (z0 + z))) for z in ndtri([0.025, 0.975])]
    out = Z.contrast_tests(values, clusters, draws=draws)["bca"]
    assert [out["low"], out["high"]] == pytest.approx(list(np.quantile(means, levels)))
    # The p-value is the nominal level whose interval end sits at zero: mapping it forward
    # gives back the share of draws at or below zero (with the count formula).
    share = (1 + (means <= 0).sum()) / (draws + 1)
    assert float(Z.bca_level(ndtri(out["p_upper"]), z0, a)) == pytest.approx(share)
    share = 1 - (1 + (means >= 0).sum()) / (draws + 1)
    assert float(Z.bca_level(ndtri(1 - out["p_lower"]), z0, a)) == pytest.approx(share)
    assert out["p_two_sided"] == pytest.approx(2 * min(out["p_upper"], out["p_lower"]))
    assert out["p_upper"] != pytest.approx(P.p_values(means)["one_sided"], rel=0.02)


def test_bca_is_the_percentile_when_both_corrections_are_zero() -> None:
    # Six equal episodes with sums symmetric about their mean: no acceleration. Bootstrap means
    # symmetric about the estimate: no bias correction.
    sums = Z.Sums(
        np.array([[1.0], [2.0], [3.0], [5.0], [6.0], [7.0]]), np.full((6, 1), 4.0), np.array([9.0])
    )
    delta = float(sums.delta[0])
    spread = np.linspace(0.01, 1.5, 500)
    means = np.concatenate([delta - spread, delta + spread])[:, None]
    out = Z.bca(means, sums)[:, 0]
    assert float(Z.acceleration(sums)[0]) == pytest.approx(0.0, abs=1e-15)
    p = P.p_values(means[:, 0])
    assert out[0] == pytest.approx(p["one_sided"]) and out[2] == pytest.approx(p["two_sided"])
    assert list(out[3:]) == pytest.approx(P.interval(means[:, 0], 0.95))


def test_bca_levels_stay_within_reach() -> None:
    # Where the correction has no room (1 - a (z0 + z) <= 0) the level is 0 or 1, not a value
    # from the other branch of the formula.
    assert float(Z.bca_level(3.0, np.array(0.0), np.array(0.5))) == 1.0
    assert float(Z.bca_level(-3.0, np.array(0.0), np.array(-0.5))) == 0.0
    assert float(Z.bca_nominal(np.array(0.001), np.array(0.0), np.array(0.5))) == 0.0
    assert float(Z.bca_nominal(np.array(0.999), np.array(0.0), np.array(-0.5))) == 1.0
    z0, a = np.array(0.1), np.array(0.05)
    for level in (0.004, 0.3, 0.99):
        nominal = Z.bca_nominal(np.array(level), z0, a)
        assert float(Z.bca_level(ndtri(nominal), z0, a)) == pytest.approx(level)


def test_bca_agrees_with_scipy_on_equal_episodes() -> None:
    values, clusters = skewed([3] * 25, seed=9)
    means = values.reshape(25, 3).mean(axis=1)
    reference = stats.bootstrap(
        (means,), np.mean, n_resamples=20_000, method="BCa", rng=np.random.default_rng(P.SEED)
    ).confidence_interval
    out = Z.contrast_tests(values, clusters)["bca"]
    width = reference.high - reference.low
    assert out["low"] == pytest.approx(reference.low, abs=0.03 * width)
    assert out["high"] == pytest.approx(reference.high, abs=0.03 * width)


def test_null_value_and_refusals() -> None:
    values, clusters = skewed([5, 1, 8, 2, 13, 3, 1, 4, 6, 2], seed=10)
    shifted = Z.contrast_tests(values, clusters, null=0.2, draws=400, flips=400)
    plain = Z.contrast_tests(values - 0.2, clusters, draws=400, flips=400)
    assert set(shifted) == set(Z.PROCEDURES)
    for name in Z.PROCEDURES:
        for key in ("p_upper", "p_lower", "p_two_sided"):
            assert shifted[name][key] == plain[name][key]
            assert 0 < shifted[name][key] <= 1
        if name in Z.NO_INTERVAL:
            assert np.isnan([shifted[name]["low"], shifted[name]["high"]]).all()
            continue
        assert shifted[name]["low"] == pytest.approx(plain[name]["low"] + 0.2)
        assert shifted[name]["low"] < values.mean() < shifted[name]["high"]
    with pytest.raises(ValueError, match="at least two episodes"):
        Z.contrast_tests([1.0, 2.0], ["a", "a"])
    with pytest.raises(ValueError, match="one vector"):
        Z.contrast_tests(np.ones((4, 2)), ["a", "a", "b", "b"])
    with pytest.raises(ValueError, match="no cluster"):
        Z.contrast_tests([1.0, 2.0, 3.0], ["a", "", "b"])


def test_columns_with_sizes_of_their_own_are_tested_as_separate_data_sets() -> None:
    # Two data sets with the same number of episodes and different sizes, side by side (as
    # when the sizes are drawn), against each one alone.
    first, first_ids = skewed([5, 1, 8, 2, 13, 3, 1, 4, 6, 2, 7, 3, 2, 9, 1], seed=12)
    second, second_ids = skewed([2, 2, 3, 9, 1, 1, 20, 4, 1, 5, 5, 6, 1, 2, 8], seed=13)
    alone = [Z.episode_sums(first + 0.3, first_ids), Z.episode_sums(second - 0.2, second_ids)]
    both = Z.Sums(
        np.hstack([s.total for s in alone]),
        np.hstack([s.size for s in alone]),
        np.concatenate([s.squares for s in alone]),
    )
    together = Z.procedures(both, draws=400, flips=400)
    for k, sums in enumerate(alone):
        apart = Z.procedures(sums, draws=400, flips=400)
        for name in Z.PROCEDURES:
            assert together[name][:, k] == pytest.approx(apart[name][:, 0], rel=1e-9, nan_ok=True)
    assert Z.within_correlation(both) == pytest.approx(
        [float(Z.within_correlation(s)[0]) for s in alone]
    )


def test_max_t_is_the_larger_of_the_two_studentised_p_values() -> None:
    for seed, shift in ((14, 0.4), (15, -0.3), (16, 0.0)):
        values, clusters = skewed([5, 1, 8, 2, 13, 3, 1, 4, 6, 2, 7, 3, 2, 9, 1, 4], seed=seed)
        out = Z.contrast_tests(values - values.mean() + shift, clusters, draws=600, flips=600)
        boot, flip, both = out["studentised"], out["sign_flip_t"], out["max_t"]
        for key in ("p_upper", "p_lower"):
            assert both[key] == max(boot[key], flip[key])
        assert both["p_two_sided"] == min(1.0, 2 * min(both["p_upper"], both["p_lower"]))
        assert both["p_two_sided"] >= boot["p_two_sided"]
        assert np.isnan(both["low"]) and np.isnan(both["high"])
    # It rejects only where both parts reject, on every column.
    rng = np.random.default_rng(P.SEED)
    first, second = rng.random((5, 400)), rng.random((5, 400))
    both = Z.larger(first, second)
    assert ((both[0] < 0.05) == ((first[0] < 0.05) & (second[0] < 0.05))).all()
    assert ((both[1] < 0.05) == ((first[1] < 0.05) & (second[1] < 0.05))).all()
    assert np.isnan(both[3:]).all()


def test_holm_by_hand() -> None:
    # Sorted: 0.001, 0.009, 0.02, 0.03, 0.04, 0.5, times 6, 5, 4, 3, 2, 1: 0.006, 0.045, 0.08,
    # 0.09, 0.08, 0.5; made non-decreasing: 0.006, 0.045, 0.08, 0.09, 0.09, 0.5.
    p = [0.001, 0.02, 0.03, 0.04, 0.5, 0.009]
    assert list(Z.holm(p)[0]) == pytest.approx([0.006, 0.08, 0.09, 0.09, 0.5, 0.045])
    assert list(Z.holm([[0.5, 0.9], [0.01, 0.01]])[0]) == [1.0, 1.0]
    assert list(Z.holm([[0.5, 0.9], [0.01, 0.01]])[1]) == [0.02, 0.02]
    rows = np.random.default_rng(P.SEED).random((200, 6))
    assert ((Z.holm(rows) < 0.05).any(axis=1) == (rows.min(axis=1) < 0.05 / 6)).all()


# --------------------------------------------------------------------------------------------
# Structures
# --------------------------------------------------------------------------------------------


def test_structures() -> None:
    assert list(Z.sizes_of(["b", "a", "b", "c", "b"])) == [1, 3, 1]
    record = Z.structure_record(np.array([1, 3, 1]))
    assert (record["episodes"], record["statements"], record["largest_episode"]) == (3, 5, 3)
    assert record["weighted_statements_per_episode"] == pytest.approx(11 / 5)
    assert record["effective_episodes"] == pytest.approx(25 / 11)
    eligible = pd.DataFrame(
        {"statement_group_id": [f"S{k:03d}" for k in range(40)], "episode_id": episodes([30, 10])}
    )
    kept = Z.thinned(eligible, 0.5)
    assert kept.sum() == 20 and len(kept) <= 2
    assert list(kept) == list(Z.thinned(eligible.iloc[::-1], 0.5))  # sorted by id first
    power = {"test": {"statements": 30, "eligible_statements": 40}}
    assert Z.thinning_share(power, 40)[0] == 0.75
    power = {
        "test": {"statements": 40},
        "scoreable_share_of_dated_train_statements": {"dev": 0.4, "fit": 0.6},
    }
    assert Z.thinning_share(power, 40) == (0.4, "the scoreable share of the dated dev statements")


# --------------------------------------------------------------------------------------------
# Generator 1: whole episodes of the dev differences
# --------------------------------------------------------------------------------------------


def toy_donors() -> Z.Donors:
    """Four dev episodes of sizes 2, 2, 7 and 30; the differences of the second pair are 1."""
    sizes = np.array([2, 2, 7, 30])
    rng = np.random.default_rng(P.SEED)
    first = np.concatenate([rng.normal(k, 0.3, size) for k, size in enumerate(sizes)])
    return Z.Donors(np.column_stack([first, np.ones(len(first))]), sizes)


def test_donor_windows_by_hand() -> None:
    # Rank shares: targets 1/6, 3/6, 5/6; donors 1/8, 3/8, 5/8, 7/8.
    windows = Z.donor_windows(np.array([1, 5, 9]), np.array([2, 2, 7, 30]), 2)
    assert windows.tolist() == [[0, 1], [1, 2], [3, 2]]
    assert Z.donor_windows(np.array([9, 1, 5]), np.array([2, 2, 7, 30]), 2).tolist() == [
        [3, 2],
        [0, 1],
        [1, 2],
    ]
    assert Z.donor_windows(np.array([1, 5, 9]), np.array([2, 2, 7, 30]), 9).shape == (3, 4)
    assert list(Z.size_ranks(np.array([4, 4, 1]))) == pytest.approx([1.5 / 3, 2.5 / 3, 0.5 / 3])


def block_sums(values: np.ndarray, length: int) -> set[float]:
    """The sums of ``length`` consecutive values from every starting point, going round."""
    out = set()
    for start in range(len(values)):
        picked = [values[(start + j) % len(values)] for j in range(length)]
        out.add(round(float(np.sum(picked)), 9))
    return out


def test_empirical_takes_consecutive_differences_of_one_donor() -> None:
    donors = toy_donors()
    sizes = np.array([1, 5, 9, 40])
    generator = Z.empirical(donors, sizes, window=2)
    ends = np.cumsum(donors.sizes)
    centred = donors.values[:, 0] - generator.centre[0]
    blocks = [centred[end - size : end] for end, size in zip(ends, donors.sizes, strict=True)]
    seen = set()
    for k in range(60):
        total, size, squares = generator.draw(Z.stream("toy", k))
        assert list(size) == list(sizes)
        for g in range(len(sizes)):
            allowed = {h: block_sums(blocks[h], sizes[g]) for h in generator.window[g]}
            donor = [h for h, sums in allowed.items() if round(float(total[g, 0]), 9) in sums]
            assert len(donor) == 1
            seen.add((g, donor[0]))
            assert round(float(squares[g, 0]), 9) in block_sums(blocks[donor[0]] ** 2, sizes[g])
        # The second pair is the constant 1 before centring: every statement is filled once.
        one = 1.0 - generator.centre[1]
        assert total[:, 1] == pytest.approx(sizes * one)
        assert squares[:, 1] == pytest.approx(sizes * one**2)
    assert seen == {(g, h) for g in range(4) for h in generator.window[g]}


def test_empirical_null_holds_exactly() -> None:
    donors = toy_donors()
    sizes = np.array([1, 5, 9, 40])
    ends = np.cumsum(donors.sizes)
    generator = Z.empirical(donors, sizes, window=2)
    centred = donors.values[:, 0] - generator.centre[0]
    expected = 0.0
    for g, size in enumerate(sizes):
        for h in generator.window[g]:
            block = centred[ends[h] - donors.sizes[h] : ends[h]]
            starts = [
                sum(block[(start + j) % len(block)] for j in range(size))
                for start in range(len(block))
            ]
            expected += np.mean(starts) / 2  # two donors in the window, equally likely
    assert expected == pytest.approx(0.0, abs=1e-10)
    assert generator.centre[1] == pytest.approx(1.0)
    # The constant is not the plain dev mean: large targets weigh their donors more.
    assert generator.centre[0] != pytest.approx(donors.values[:, 0].mean(), abs=0.05)


@pytest.mark.parametrize("options", [{"chained": True}, {"sizes_drawn": True}, {"window": 4}])
def test_empirical_variants_fill_every_statement_and_keep_the_null(options: dict) -> None:
    donors = toy_donors()
    sizes = np.array([1, 5, 9, 40, 3, 3, 12])
    generator = Z.empirical(donors, sizes, **{"window": 2, **options})
    one = 1.0 - generator.centre[1]
    totals, counts = [], []
    for k in range(4_000):
        total, size, squares = generator.draw(Z.stream("toy", k))
        assert total[:, 1] == pytest.approx(size * one, abs=1e-9)
        assert squares[:, 1] == pytest.approx(size * one**2, abs=1e-9)
        if options.get("sizes_drawn"):
            assert set(size) <= set(sizes)
        else:
            assert list(size) == list(sizes)
        totals.append(total[:, 0].sum())
        counts.append(size.sum())
    error = np.std(totals) / np.sqrt(len(totals))
    assert abs(np.mean(totals)) < 3.5 * error
    assert (len(set(counts)) > 1) == bool(options.get("sizes_drawn"))


def test_sparse_episodes_are_all_zero_or_whole_donor_blocks_and_keep_the_null() -> None:
    donors = toy_donors()
    sizes = np.array([1, 5, 9, 40, 3, 3, 12, 7, 2, 6] * 6)
    dense = Z.empirical(donors, sizes, window=2)
    sparse = Z.empirical(donors, sizes, window=2, active=0.15)
    assert np.array_equal(sparse.centre, dense.centre)
    kept, totals = [], []
    for k in range(3_000):
        rng = Z.stream("sparse", k)
        total, size, squares = sparse.draw(rng)
        full = dense.draw(Z.stream("sparse", k))  # the same blocks before the episodes are kept
        on = squares[:, 0] > 0  # the first pair's differences are never exactly zero
        assert list(size) == list(sizes)
        assert np.array_equal(total[on], full[0][on]) and np.array_equal(squares[on], full[2][on])
        assert (total[~on] == 0).all() and (squares[~on] == 0).all()
        kept.append(on.mean())
        totals.append(total[:, 0].sum())
    assert np.mean(kept) == pytest.approx(0.15, abs=0.005)
    error = np.std(totals) / np.sqrt(len(totals))
    assert abs(np.mean(totals)) < 3.5 * error
    # With every episode active the draw is the dense one, stream for stream.
    whole = Z.empirical(donors, sizes, window=2, active=1.0)
    assert np.array_equal(whole.draw(Z.stream("s", 3))[0], dense.draw(Z.stream("s", 3))[0])


def test_a_sparse_alternative_is_carried_by_the_active_episodes() -> None:
    donors = toy_donors()
    sizes = np.array([1, 5, 9, 40, 3, 3, 12, 7, 2, 6] * 6)
    sparse = Z.empirical(donors, sizes, window=2, active=0.15)
    moved_by = []
    for k in range(3_000):
        null = sparse.draw(Z.stream("sparse", k))
        total, size, squares = sparse.draw(Z.stream("sparse", k), 0.3)
        on = null[2][:, 0] > 0  # the same episodes are active with and without the alternative
        assert list(size) == list(sizes)
        assert (total[~on] == 0).all() and (squares[~on] == 0).all()
        # Every statement of an active episode moves by 0.3 / 0.15 = 2.
        count = sizes[on][:, None]
        assert total[on] == pytest.approx(null[0][on] + 2.0 * count)
        assert squares[on] == pytest.approx(null[2][on] + 4.0 * null[0][on] + 4.0 * count)
        moved_by.append((total[:, 0].sum() - null[0][:, 0].sum()) / sizes.sum())
    # The mean over statements moves by 0.3 on average, and by 2 times the share of the
    # statements that are in active episodes in each data set.
    error = np.std(moved_by) / np.sqrt(len(moved_by))
    assert np.mean(moved_by) == pytest.approx(0.3, abs=3.5 * error)
    assert np.std(moved_by) > 0.05
    plain, moved = Z.simulate(sparse, "sparse", 0, 50), Z.simulate(sparse, "sparse", 0, 50, 0.3)
    assert (moved.delta - plain.delta)[::2] == pytest.approx(moved_by[:50])
    # With every episode active, every statement moves by the constant itself.
    dense = Z.empirical(donors, sizes, window=2)
    still, there = dense.draw(Z.stream("s", 3)), dense.draw(Z.stream("s", 3), 0.3)
    assert there[0] == pytest.approx(still[0] + 0.3 * sizes[:, None])
    assert there[2] == pytest.approx(still[2] + 0.6 * still[0] + 0.09 * sizes[:, None])


def test_shift_by_hand() -> None:
    # Episodes (1, 2) and (0, 1, 3): sums 3 and 4, sums of squares 5 and 10.
    total, size, squares = np.array([[3.0], [4.0]]), np.array([2.0, 3.0]), np.array([[5.0], [10.0]])
    # Plus 0.5: (1.5, 2.5) and (0.5, 1.5, 3.5).
    moved = Z.shifted(total, size, squares, 0.5)
    assert moved[0].tolist() == [[4.0], [5.5]] and moved[1] is size
    assert moved[2].tolist() == [[1.5**2 + 2.5**2], [0.5**2 + 1.5**2 + 3.5**2]]
    # Plus 2 in the first episode only: (3, 4) and (0, 1, 3).
    one = Z.shifted(total, size, squares, np.array([2.0, 0.0]))
    assert one[0].tolist() == [[7.0], [4.0]] and one[2].tolist() == [[25.0], [10.0]]
    # Several columns at once, and no shift.
    wide = Z.shifted(np.hstack([total, -total]), size, np.hstack([squares, squares]), 0.5)
    assert wide[0].tolist() == [[4.0, -2.0], [5.5, -2.5]]
    assert wide[2][:, 1].tolist() == [0.5**2 + 1.5**2, 0.5**2 + 0.5**2 + 2.5**2]
    same = Z.shifted(total, size, squares, 0.0)
    assert np.array_equal(same[0], total) and np.array_equal(same[2], squares)


def test_chained_donors_lower_the_correlation_and_going_round_raises_it() -> None:
    rng = np.random.default_rng(P.SEED)
    sizes = np.full(40, 4)
    values = np.repeat(rng.normal(0, 0.5, 40), 4) + rng.normal(0, 1.0, 160)
    donors = Z.Donors(values[:, None], sizes)
    targets = np.full(60, 16)
    icc = {}
    for name, options in (("round", {}), ("chained", {"chained": True})):
        generator = Z.empirical(donors, targets, **options)
        icc[name] = float(Z.within_correlation(Z.simulate(generator, name, 0, 300)).mean())
    source = W.clustered_variance(values, episodes([4] * 40))["icc"]
    assert icc["chained"] < source < icc["round"]


def test_two_models_share_a_share_of_the_episodes() -> None:
    donors = toy_donors()
    one = Z.empirical(donors, np.array([1, 5, 9, 40, 3, 3, 12, 6]), window=3)
    same = Z.TwoModels(one, 1.0).draw(Z.stream("two", 0))
    assert same[0].shape == (8, 4) and np.array_equal(same[0][:, :2], same[0][:, 2:])
    apart = Z.TwoModels(one, 0.0).draw(Z.stream("two", 0))
    assert np.array_equal(apart[0][:, :2], same[0][:, :2])
    assert (apart[0][:, 0] != apart[0][:, 2]).mean() > 0.5
    shares = [
        (lambda t: (t[:, 0] == t[:, 2]).mean())(Z.TwoModels(one, 0.5).draw(Z.stream("two", k))[0])
        for k in range(300)
    ]
    assert 0.5 < np.mean(shares) < 0.75  # half shared, and some equal by chance (small donors)


# --------------------------------------------------------------------------------------------
# Generator 2: random effects on a latent scale
# --------------------------------------------------------------------------------------------


def test_marginal() -> None:
    m = Z.marginal(np.array([0.5, -0.1, 0.2, 0.2]))
    assert list(m.support) == pytest.approx([-0.3, 0.0, 0.0, 0.3])
    assert list(m.cumulative) == pytest.approx([0.25, 0.5, 0.75, 1.0])
    assert m.variance == pytest.approx(np.var([0.5, -0.1, 0.2, 0.2]))
    # Left-skewed values: 2% of the mass goes to -1, and the mean is zero again.
    values = np.array([0.8, 0.8, 0.8, 0.8, -0.4])
    extreme = Z.marginal(values, 0.02)
    weights = np.diff(extreme.cumulative, prepend=0.0)
    mean = 0.98 * values.mean() + 0.02 * -1.0
    assert extreme.support[0] == pytest.approx(-1.0 - mean) and weights[0] == pytest.approx(0.02)
    assert float(weights @ extreme.support) == pytest.approx(0.0, abs=1e-12)
    assert weights[1:] == pytest.approx(0.98 / 5)
    right = Z.marginal(-values, 0.02)
    assert right.support[-1] == pytest.approx(1.0 + mean)


@pytest.mark.parametrize("heavy", [False, True])
def test_latent_generator_keeps_the_marginal_and_reaches_the_correlation(heavy: bool) -> None:
    rng = np.random.default_rng(P.SEED)
    values = np.concatenate([np.full(70, 0.8), rng.uniform(-0.45, 0.3, 30)])  # skewed, an atom
    m = Z.marginal(values)
    target = 0.12
    loading = Z.calibrate(m, target, heavy)
    assert Z.induced_correlation(m, loading, heavy) == pytest.approx(target, abs=1e-7)
    assert 0 < loading < 1 and Z.calibrate(m, 0.0, heavy) == 0.0
    assert Z.induced_correlation(m, 0.5, heavy) > Z.induced_correlation(m, 0.2, heavy) > 0
    # Every statement its own episode: the totals are the statement values.
    single = Z.copula(np.ones(20_000, dtype=int), [m], [loading], heavy)
    drawn = single.draw(Z.stream("latent", int(heavy)))[0][:, 0]
    assert set(np.round(drawn, 12)) <= set(np.round(m.support, 12))
    assert np.mean(drawn == m.support[-1]) == pytest.approx(0.70, abs=0.015)
    assert drawn.mean() == pytest.approx(0.0, abs=0.012)
    assert np.quantile(drawn, 0.15) == pytest.approx(np.quantile(m.support, 0.15), abs=0.03)
    # Episodes of 6: the correlation of two statements of one episode is the target.
    generator = Z.copula(np.full(300, 6), [m], [loading], heavy)
    sums = Z.simulate(generator, f"latent/{heavy}", 0, 150)
    between = (sums.total / 6).var(axis=0).mean()
    within = (m.variance - between) * 6 / 5
    assert (m.variance - within) / m.variance == pytest.approx(target, abs=0.02)
    assert float((sums.squares / sums.statements).mean()) == pytest.approx(m.variance, rel=0.03)


def test_heavy_episode_effects_have_heavier_tails() -> None:
    m = Z.marginal(np.linspace(-1, 1, 201))
    spread = {}
    for heavy in (False, True):
        generator = Z.copula(np.full(400, 10), [m], [Z.calibrate(m, 0.3, heavy)], heavy)
        means = Z.simulate(generator, "tails", 0, 60).total / 10
        spread[heavy] = float(stats.kurtosis(means.ravel()))
    assert spread[True] > spread[False] + 0.3


def test_columns_of_the_latent_generator_are_correlated_as_asked() -> None:
    rng = np.random.default_rng(P.SEED)
    raw = rng.normal(size=(500, 3))
    raw[:, 1] += 0.8 * raw[:, 0]
    raw[:, 2] = np.round(raw[:, 2] - 0.5 * raw[:, 0])  # ties
    within = Z.normal_scores(raw)
    assert within.shape == (3, 3) and np.allclose(np.diag(within), 1.0)
    assert within[0, 1] > 0.5 and within[0, 2] < -0.3
    for dependence in (0.0, 0.5, 1.0):
        big = np.kron(np.array([[1.0, dependence], [dependence, 1.0]]), within)
        assert np.allclose(Z.root(big) @ Z.root(big).T, big)  # singular at 1: eigenvectors
        factor = Z.two_model_root(dependence, within)
        assert np.allclose(factor @ factor.T, big)
    assert np.array_equal(Z.root(within), np.linalg.cholesky(within))
    assert np.array_equal(Z.normal_scores(np.ones((5, 2))), np.eye(2))  # a constant column
    marginals = [Z.marginal(raw[:, k]) for k in range(3)] * 2
    same = Z.copula(
        np.ones(4_000, dtype=int), marginals, [0.2] * 6, mix=Z.two_model_root(1.0, within)
    )
    drawn = same.draw(Z.stream("columns", 0))[0]
    assert np.array_equal(drawn[:, :3], drawn[:, 3:])
    assert np.corrcoef(drawn[:, 0], drawn[:, 1])[0, 1] > 0.4
    apart = Z.copula(
        np.ones(4_000, dtype=int), marginals, [0.2] * 6, mix=Z.two_model_root(0.0, within)
    ).draw(Z.stream("columns", 0))[0]
    assert abs(np.corrcoef(apart[:, 0], apart[:, 3])[0, 1]) < 0.06


# --------------------------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------------------------


def toy_generators() -> dict[str, object]:
    sizes = np.array([1, 1, 2, 2, 3, 3, 4, 5, 6, 8, 9, 12, 15, 20, 30] * 2)
    m = Z.marginal(np.random.default_rng(P.SEED).exponential(1.0, 300))
    return {
        "toy/copula/H1": Z.copula(sizes, [m], [Z.calibrate(m, 0.1)]),
        "toy/copula/family_0.5": Z.copula(
            sizes, [m] * 6, [0.1] * 6, mix=Z.two_model_root(0.5, np.eye(3))
        ),
    }


def test_simulate_does_not_depend_on_the_block_and_adds_the_shift() -> None:
    generator = toy_generators()["toy/copula/H1"]
    whole = Z.simulate(generator, "toy", 0, 6)
    part = Z.simulate(generator, "toy", 4, 2)
    assert whole.total.shape == (30, 6) and whole.size.shape == (30, 1)
    assert np.array_equal(whole.total[:, 4:], part.total)
    assert np.array_equal(whole.squares[4:], part.squares)
    assert not np.array_equal(whole.total[:, 0], whole.total[:, 1])
    assert not np.array_equal(whole.total, Z.simulate(generator, "other", 0, 6).total)
    # Another master seed gives other data sets; the default is the registered seed.
    assert np.array_equal(whole.total, Z.simulate(generator, "toy", 0, 6, seed=P.SEED).total)
    assert not np.array_equal(whole.total, Z.simulate(generator, "toy", 0, 6, seed=7).total)
    shifted = Z.simulate(generator, "toy", 0, 6, shift=0.25)
    assert shifted.delta == pytest.approx(whole.delta + 0.25)
    # Statement by statement: every statement its own episode.
    single = Z.copula(np.ones(50, dtype=int), [Z.marginal(np.arange(7.0))], [0.0])
    plain, moved = Z.simulate(single, "s", 0, 3), Z.simulate(single, "s", 0, 3, shift=-0.5)
    assert moved.squares == pytest.approx(((plain.total - 0.5) ** 2).sum(axis=0))
    # Sizes that change between replications are kept column by column.
    drawn = Z.empirical(toy_donors(), np.array([1, 5, 9, 40]), window=2, sizes_drawn=True)
    sums = Z.simulate(drawn, "toy", 0, 5, shift=1.0)
    assert sums.size.shape == (4, 10) and np.array_equal(sums.size[:, 0], sums.size[:, 1])
    assert len(set(sums.statements)) > 1
    one = 1.0 - drawn.centre[1]
    assert sums.total[:, 1::2] == pytest.approx(sums.size[:, 1::2] * (one + 1.0))
    assert sums.squares[1::2] == pytest.approx(sums.statements[1::2] * (one + 1.0) ** 2)


def test_tally_by_hand() -> None:
    result = np.array(
        [
            [0.001, 0.02, 0.5, 0.9],  # p for delta > 0
            [0.999, 0.98, 0.5, 0.004],  # p for delta < 0
            [0.002, 0.04, 1.0, 0.008],  # two-sided
            [0.1, -0.1, -0.3, -0.9],  # low
            [0.5, 0.4, 0.2, -0.2],  # high
        ]
    )
    counted = Z.tally({"x": result}, truth=0.0)["x"]
    # upper at 0.05/6 and 0.05, lower, two-sided; then intervals covering 0; then summed widths
    # of the bounded intervals, and the number of unbounded ones.
    assert list(counted[:6]) == [1, 2, 1, 1, 2, 3]
    assert counted[6] == 2 and counted[7] == pytest.approx(0.4 + 0.5 + 0.5 + 0.7)
    assert counted[8] == 0 and len(counted) == 9
    assert Z.tally({"x": result}, truth=0.3)["x"][6] == 2
    # An unbounded interval covers, is counted, and stays out of the mean width.
    open_ended = result.copy()
    open_ended[3, 0], open_ended[4, 3] = -np.inf, np.inf
    wide = Z.tally({"x": open_ended}, truth=0.0)["x"]
    assert wide[6] == 4 and wide[7] == pytest.approx(0.5 + 0.5) and wide[8] == 2
    record = Z.scenario_record(
        Z.Scenario("s", "g", "H1", "null", 0.0, 4),
        {**dict.fromkeys(Z.PROCEDURES, wide), Z.DATA: np.zeros(3)},
    )
    cell = record["procedures"]["studentised"]
    assert cell["mean_width95"] == pytest.approx(1.0 / 2) and cell["unbounded95"][0] == 0.5
    assert record["procedures"]["max_t"]["unbounded95"] is None
    # A p-value equal to the level does not reject ("below"); an end equal to the truth covers.
    edge = np.array([[0.05], [0.05 / 6], [1.0], [0.0], [0.5]])
    assert list(Z.tally({"x": edge}, truth=0.0)["x"][:7]) == [0, 0, 0, 1, 0, 0, 1]
    data = np.array([0.4, 0.2, 1.0])  # four estimates: sum 0.4, sum of squares 0.2
    full = {**dict.fromkeys(Z.PROCEDURES, counted), Z.DATA: data}
    record = Z.scenario_record(Z.Scenario("s", "g", "H1", "null", 0.0, 4), full)
    assert record["data"] == {
        "mean_estimate": pytest.approx(0.1),
        "sd_of_estimate": pytest.approx(0.2),
        "mean_within_correlation": 0.25,
    }
    cell = record["procedures"]["percentile"]
    assert cell["rejection"]["upper"] == {
        "0.05/6": [0.25, np.sqrt(0.25 * 0.75 / 4)],
        "0.05": [0.5, 0.25],
    }
    assert cell["rejection"]["two_sided"]["0.05"][0] == 0.75
    assert cell["coverage95"][0] == 0.5 and cell["mean_width95"] == pytest.approx(2.1 / 4)
    # A procedure with no interval: its coverage is that of the two-sided test of the truth
    # (three of four rejected at 0.05), and is not given under an alternative.
    flipped = record["procedures"]["sign_flip_t"]
    assert flipped["coverage95"][0] == 0.25 and flipped["mean_width95"] is None
    moved = Z.scenario_record(Z.Scenario("s", "g", "H1", "plus_mdd", 0.1, 4), full)
    assert moved["procedures"]["sign_flip_t"]["coverage95"] is None
    assert moved["procedures"]["percentile"]["coverage95"][0] == 0.5
    assert Z.rate(83, 10_000) == [0.0083, pytest.approx(0.000907, abs=1e-6)]


def test_family_tally_by_hand() -> None:
    # Two replications of six tests (H1 one-sided, H2 and H3 two-sided, for two models). In the
    # first, the two-sided p of the fifth test is 0.008 < 0.05/6; in the second the smallest
    # p-value that counts is 0.02: no rejection under Holm, one unadjusted.
    result = np.ones((5, 12))
    result[2, 4] = 0.008
    result[0, 4] = 0.0001  # not the side that counts for a two-sided test
    result[2, 6] = 0.0001  # not the side that counts for H1
    result[0, 6] = 0.02
    counted = Z.family_tally({"x": result}, 2)["x"]
    assert list(counted) == [1.0, 2.0]
    scenario = Z.Scenario("s", "g", "family", "0.5", 0.0, 2, family=True)
    record = Z.scenario_record(scenario, {"x": counted})
    assert record["models_dependence"] == "0.5" and scenario.label == "s/g/family_0.5"
    assert record["procedures"]["x"]["holm_familywise_error"][0] == 0.5


def toy_tasks(replications: int = 40) -> list[Z.Task]:
    scenarios = [
        Z.Scenario("toy", "copula", "H1", "null", 0.0, replications),
        Z.Scenario("toy", "copula", "H1", "plus_mdd", 0.5, replications),
        Z.Scenario("toy", "copula", "family", "0.5", 0.0, replications, family=True),
    ]
    return Z.build_tasks(scenarios, draws=300, flips=300)


def test_tasks_cover_every_replication_once() -> None:
    tasks = Z.build_tasks([Z.Scenario("s", "g", "H2", "null", 0.0, 600)], 100, 100)
    assert [(t.first, t.count) for t in tasks] == [(0, 250), (250, 250), (500, 100)]
    assert {t.streams for t in tasks} == {P.SEED}
    other = Z.build_tasks([Z.Scenario("s", "g", "H2", "null", 0.0, 600)], 100, 100, streams=5)
    assert {t.streams for t in other} == {5} and {t.seed for t in other} == {P.SEED}
    family = Z.build_tasks([Z.Scenario("s", "g", "family", "1", 0.0, 100, family=True)], 100, 100)
    assert [(t.first, t.count) for t in family] == [(0, 41), (41, 41), (82, 18)]
    assert all(t.family and t.generator == "s/g/family_1" for t in family)


def test_run_is_reproducible_and_does_not_depend_on_the_workers() -> None:
    generators, tasks = toy_generators(), toy_tasks()
    first = Z.run_tasks(tasks, generators, workers=1)
    again = Z.run_tasks(tasks, generators, workers=1)
    spread = Z.run_tasks(tasks, generators, workers=2)
    assert set(first) == {0, 1, 2}
    for scenario, counted in first.items():
        assert set(counted) - {Z.DATA} == set(Z.PROCEDURES)
        for name, values in counted.items():
            assert np.array_equal(values, again[scenario][name])
            assert np.array_equal(values, spread[scenario][name])
    # The null and the shifted scenario are the same data: the widths agree, the tests do not.
    assert first[0]["t_cr1"][7] == pytest.approx(first[1]["t_cr1"][7])
    assert first[1]["t_cr1"][1] > first[0]["t_cr1"][1]


def test_a_planted_effect_is_detected_and_a_true_null_is_mostly_kept() -> None:
    generators = toy_generators()
    scenarios = [
        Z.Scenario("toy", "copula", "H1", "null", 0.0, 500),
        Z.Scenario("toy", "copula", "H1", "plus_mdd", 0.6, 500),
        Z.Scenario("toy", "copula", "H1", "minus_mdd", -0.6, 500),
    ]
    totals = Z.run_tasks(Z.build_tasks(scenarios, 500, 500), generators)
    records = [Z.scenario_record(s, totals[k])["procedures"] for k, s in enumerate(scenarios)]
    for name in Z.PROCEDURES:
        null, plus, minus = (record[name] for record in records)
        assert 0.01 <= null["rejection"]["two_sided"]["0.05"][0] <= 0.12
        assert null["rejection"]["two_sided"]["0.05/6"][0] <= 0.04
        assert 0.88 <= null["coverage95"][0] <= 0.99
        assert plus["rejection"]["upper"]["0.05"][0] > 0.9
        assert plus["rejection"]["two_sided"]["0.05/6"][0] > 0.6
        assert plus["rejection"]["lower"]["0.05"][0] == 0.0
        assert minus["rejection"]["lower"]["0.05"][0] > 0.9
        assert minus["rejection"]["upper"]["0.05"][0] == 0.0
        if name in Z.NO_INTERVAL:
            assert null["coverage95"][0] == 1 - null["rejection"]["two_sided"]["0.05"][0]
            assert plus["coverage95"] is None and minus["coverage95"] is None
        else:
            # A shift moves the interval with the estimate: the coverage is that of the null.
            assert plus["coverage95"] == null["coverage95"] == minus["coverage95"]
    # The larger of two p-values rejects at most as often as either part.
    for record in records:
        for side in Z.SIDES[:2]:
            for level in Z.LEVELS:
                both = record["max_t"]["rejection"][side][level][0]
                for part in ("studentised", "sign_flip_t"):
                    assert both <= record[part]["rejection"][side][level][0]


# --------------------------------------------------------------------------------------------
# Scenarios and the command line
# --------------------------------------------------------------------------------------------


def test_scenarios_of_a_run() -> None:
    rng = np.random.default_rng(P.SEED)
    sizes = np.array([3, 1, 6, 2, 9, 4, 5, 2])
    donors = Z.Donors(
        rng.normal(0.02, 0.2, (32, 3)) + np.repeat(rng.normal(0, 0.1, 8), sizes)[:, None], sizes
    )
    pairs = Z.pair_record(donors)
    assert list(pairs) == ["H1", "H2", "H3"] and pairs["H1"]["sides"] == 1
    structures = {
        "e3": np.array([4, 9, 1, 30, 2, 2]),
        "dev": sizes,
        "e3_thinned": np.array([2, 5, 14]),
    }
    detectable = {"H1": 0.06, "H2": 0.015, "H3": 0.017}
    replications = {"null": 30, "power": 20, "family": 10}
    scenarios, generators = Z.build_scenarios(structures, donors, pairs, detectable, replications)
    plain = [s for s in scenarios if not s.family and s.effect != "other_draws"]
    for structure, names in (
        ("e3", Z.GENERATORS),
        ("dev", Z.GENERATORS),
        ("e3_thinned", Z.THINNED_GENERATORS),
    ):
        mine = [s for s in plain if s.structure == structure]
        assert {s.generator for s in mine} == set(names)
        # H1: the null and the detectable difference; H2 and H3: both directions as well.
        assert len(mine) == len(names) * (2 + 3 + 3)
    assert {(s.effect, s.shift) for s in plain if s.pair == "H2"} == {
        ("null", 0.0),
        ("plus_mdd", 0.015),
        ("minus_mdd", -0.015),
    }
    assert {s.replications for s in plain if s.effect == "null"} == {30}
    assert {s.replications for s in plain if s.effect != "null"} == {20}
    family = [s for s in scenarios if s.family]
    assert len(family) == 2 * 2 * 3 and {s.structure for s in family} == {"e3", "dev"}
    assert {s.effect for s in family} == {"0", "0.5", "1"}
    other = [s for s in scenarios if s.effect == "other_draws"]
    assert [(s.structure, s.generator, s.seed) for s in other] == [
        ("e3", "copula", (P.SEED, 1))
    ] * 3
    assert {s.label for s in scenarios} == set(generators)
    assert all(generators[s.label].columns == (6 if s.family else 1) for s in scenarios)
    # Each variant of the whole-episode generator is the one its name says.
    options = {
        name: (g.chained, g.sizes_drawn, g.active, g.window.shape[1])
        for name in Z.GENERATORS
        if isinstance(g := generators[f"e3/{name}/H2"], Z.Empirical)
    }
    assert options == {
        "empirical": (False, False, 1.0, 8),
        "empirical_chained": (True, False, 1.0, 8),
        "empirical_any_size": (False, False, 1.0, 8),
        "empirical_sizes_drawn": (False, True, 1.0, 8),
        "empirical_sparse": (False, False, Z.SPARSE_SHARE, 8),
    }
    assert not generators["e3/copula/H2"].heavy and generators["e3/copula_heavy/H2"].heavy
    record = Z.generator_record(generators)
    assert record["e3/empirical/H1"]["constant_subtracted"][0] == pytest.approx(
        float(generators["e3/empirical/H1"].centre[0])
    )
    assert 0 <= record["dev/copula_icc_double/H2"]["latent_loading"][0] < 1
    other_draws = Z.build_tasks(other, 50, 50)
    assert {t.seed for t in other_draws} == {(P.SEED, 1)}
    assert not np.array_equal(Z.draw_matrix(6, 50, P.SEED), Z.draw_matrix(6, 50, (P.SEED, 1)))


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """The synthetic statement table of the power tests, its eligible list and power report."""
    folder = tmp_path_factory.mktemp("size_check")
    table = synthetic_table()
    paths = {name: folder / name for name in ("s.csv.gz", "c.json", "e.csv")}
    table.to_csv(paths["s.csv.gz"], index=False, compression=dict(D.forms.GZIP))
    paths["c.json"].write_text(json.dumps(counts_of(table)), encoding="utf-8")
    eligible_of(table).to_csv(paths["e.csv"], index=False)
    args = ["--statements", str(paths["s.csv.gz"]), "--counts", str(paths["c.json"])]
    args += ["--eligible", str(paths["e.csv"]), "--sealed-counts", str(folder / "none.json")]
    assert W.main([*args, "--out", str(folder)]) == 0
    return {**paths, "power": folder / W.POWER_REPORT.name, "folder": folder}


def test_command_line_writes_the_report_and_refuses_the_sealed_folder(
    files: dict[str, Path], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Z, "NODES", 200)
    monkeypatch.setattr(Z, "GRID_POINTS", 801)
    Z.effect_nodes.cache_clear()
    out = files["folder"] / "size_check.json"
    args = ["--statements", str(files["s.csv.gz"]), "--eligible", str(files["e.csv"])]
    args += ["--power", str(files["power"]), "--quick", "--workers", "1"]
    args += ["--replications", "6", "--draws", "120"]
    try:
        assert Z.main(args) == 0
        printed = capsys.readouterr().out
        assert "rejection of a true null at 0.05/6" in printed and "wrote" not in printed
        assert not out.exists()  # --quick writes nothing unless told where
        assert Z.main([*args, "--out", str(out)]) == 0
    finally:
        Z.effect_nodes.cache_clear()
    again = capsys.readouterr().out
    assert f"wrote {out.as_posix()}" in again
    # The same numbers on the second run: the printed table is the same, line for line.
    table = [line for line in printed.splitlines() if not line.startswith("runtime")]
    assert table and table == again.splitlines()[: len(table)]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["command"].endswith("--quick")
    assert report["inputs"]["statements_sha256"] == D.sha16(files["s.csv.gz"].read_bytes())
    assert report["inputs"]["size_check_sha256"] == D.sha16(Path(Z.__file__).read_bytes())
    settings = report["settings"]
    assert (settings["seed"], settings["bootstrap_draws"], settings["sign_flips"]) == (
        P.SEED,
        120,
        120,
    )
    assert settings["replication_seed"] == P.SEED and settings["sparse_share"] == Z.SPARSE_SHARE
    assert settings["replications"] == {"null": 6, "power": 6, "family": 6}
    power = json.loads(files["power"].read_text(encoding="utf-8"))
    assert report["proxy_pairs"] == power["proxy_pairs"] == Z.proxy_pairs()
    assert report["proxy_pairs"][2] == {
        "hypothesis": "H3",
        "comparator": "base_rate",
        "tested": "gbm_text",
    }
    for h, pair in zip(("H1", "H2", "H3"), W.PROXY_PAIRS, strict=True):
        assert (report["dev_pairs"][h]["comparator"], report["dev_pairs"][h]["tested"]) == (
            pair.comparator,
            pair.tested,
        )
    assert report["structures"]["e3"]["statements"] == power["test"]["statements"] == 60
    assert report["structures"]["dev"]["statements"] == power["dev"]["scoreable_statements"]
    share = power["scoreable_share_of_dated_train_statements"]["dev"]
    assert report["structures"]["e3_thinned"]["statements"] == round(share * 60)
    assert report["minimum_detectable_delta"] == {
        h: power["hypotheses"][h]["minimum_detectable_delta"] for h in ("H1", "H2", "H3")
    }
    for h in ("H1", "H2", "H3"):
        assert report["dev_pairs"][h]["icc"] == pytest.approx(power["hypotheses"][h]["dev"]["icc"])
        assert report["dev_pairs"][h]["delta"] == pytest.approx(
            power["hypotheses"][h]["dev"]["delta"]
        )
    assert len(report["results"]) == (2 * len(Z.GENERATORS) + len(Z.THINNED_GENERATORS)) * 8 + 3
    assert len(report["familywise"]) == 12
    for record in report["results"]:
        assert set(record["procedures"]) == set(Z.PROCEDURES) and record["replications"] == 6
        for cell in record["procedures"].values():
            assert set(cell["rejection"]) == set(Z.SIDES)
            assert all(
                0 <= cell["rejection"][side][level][0] <= 1
                for side in Z.SIDES
                for level in Z.LEVELS
            )
    assert report["run"]["workers"] == 1 and report["run"]["runtime_seconds"] >= 0
    # Another master seed: other data sets, the same draws, and the command says so.
    other = files["folder"] / "size_check_other.json"
    try:
        assert Z.main([*args, "--seed", "7", "--out", str(other)]) == 0
    finally:
        Z.effect_nodes.cache_clear()
    moved = json.loads(other.read_text(encoding="utf-8"))
    assert moved["command"].endswith("--quick --seed 7")
    assert moved["settings"]["replication_seed"] == 7 and moved["settings"]["seed"] == P.SEED
    assert moved["results"] != report["results"]
    assert [r["data"]["mean_estimate"] for r in moved["results"]] != [
        r["data"]["mean_estimate"] for r in report["results"]
    ]
    with pytest.raises(SystemExit, match="sealed"):
        Z.main([*args, "--out", str(files["folder"] / "sealed" / "size_check.json")])
    with pytest.raises(SystemExit, match="sealed"):
        Z.main(["--statements", "external_data/sealed/statements.csv.gz", *args[2:]])


def test_command_line_writes_nothing_when_an_input_changes_during_the_run(
    files: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    power = tmp_path / "power.json"
    power.write_bytes(files["power"].read_bytes())
    out = tmp_path / "size_check.json"
    args = ["--statements", str(files["s.csv.gz"]), "--eligible", str(files["e.csv"])]
    args += ["--power", str(power), "--quick", "--workers", "1", "--out", str(out)]
    record = Z.input_record(files["s.csv.gz"], files["e.csv"], power)
    assert record["power_report_sha256"] == D.sha16(power.read_bytes())
    assert record["eligible_e3_sha256"] == D.sha16(files["e.csv"].read_bytes())
    assert record["size_check_sha256"] == D.sha16(Path(Z.__file__).read_bytes())
    calls = []

    def rebuilt_meanwhile(*given: object) -> dict:
        calls.append(given)
        power.write_text(power.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return {}

    monkeypatch.setattr(Z, "build", rebuilt_meanwhile)
    with pytest.raises(SystemExit, match="changed during the run"):
        Z.main(args)
    assert len(calls) == 1 and not out.exists()


def test_build_refuses_inputs_from_different_builds(files: dict[str, Path]) -> None:
    table = D.load_statements(files["s.csv.gz"])
    eligible = D.read_table(files["e.csv"])
    power = json.loads(files["power"].read_text(encoding="utf-8"))
    replications = {"null": 2, "power": 2, "family": 2}
    with pytest.raises(ValueError, match="eligible list and the power report"):
        Z.build(table, eligible.iloc[1:], power, replications, 50, 50)
    wrong = {**power, "dev": {**power["dev"], "scoreable_statements": 1}}
    with pytest.raises(ValueError, match="statement table and the power report"):
        Z.build(table, eligible, wrong, replications, 50, 50)
    # A power report written before the H3 pair changed (or with no pairs at all).
    old = [dict(p) for p in power["proxy_pairs"]]
    old[2] = {"hypothesis": "H3", "comparator": "gbm_structured", "tested": "gbm_text"}
    for stale in (
        {**power, "proxy_pairs": old},
        {k: v for k, v in power.items() if k != "proxy_pairs"},
    ):
        with pytest.raises(ValueError, match="other proxy pairs"):
            Z.build(table, eligible, stale, replications, 50, 50)
    leaked = table.copy()
    leaked.loc[leaked["period"] == "test", "outcome"] = "recovered"
    with pytest.raises(ValueError):
        Z.build(leaked, eligible, power, replications, 50, 50)


def test_dev_donors_are_the_proxy_pairs_in_time_order(files: dict[str, Path]) -> None:
    table = D.load_statements(files["s.csv.gz"])
    donors = Z.dev_donors(table)
    frame = P.prepare(table)
    _, dev, predictions = W.fit_and_predict(frame)
    scoreable = dev[dev["scoreable"]]
    losses = W.primary_losses(scoreable, predictions)
    assert donors.values.shape == (len(scoreable), 3)
    assert list(donors.sizes) == list(Z.sizes_of(scoreable["episode_id"]))
    days = table.set_index("statement_group_id")["event_date"]
    at = 0
    for episode, size in zip(sorted(set(scoreable["episode_id"])), donors.sizes, strict=True):
        ids = scoreable.index[scoreable["episode_id"] == episode]
        ordered = sorted(ids, key=lambda i: (days[i], i))
        for k, pair in enumerate(W.PROXY_PAIRS):
            expected = (losses[pair.comparator] - losses[pair.tested]).loc[ordered]
            assert donors.values[at : at + size, k] == pytest.approx(expected.to_numpy())
        at += size
    assert [days[i] for i in ordered] == sorted(days[i] for i in ordered)


# --------------------------------------------------------------------------------------------
# The file in the repository
# --------------------------------------------------------------------------------------------


def test_output_is_up_to_date() -> None:
    inputs = (D.STATEMENTS, D.ELIGIBLE, Z.POWER_REPORT)
    if not all(path.exists() for path in (*inputs, Z.REPORT)):
        pytest.skip("the output or its inputs are not in this checkout")
    report = json.loads(Z.REPORT.read_text(encoding="utf-8"))
    expected = Z.input_record(D.STATEMENTS, D.ELIGIBLE, Z.POWER_REPORT)
    assert expected["statements_sha256"] == D.sha16(D.STATEMENTS.read_bytes())
    stale = {key for key, value in expected.items() if report["inputs"].get(key) != value}
    assert not stale, f"{Z.REPORT}: rerun `{Z.COMMAND}` ({sorted(stale)} changed)"
    settings = report["settings"]
    assert report["command"] == Z.COMMAND and settings["replications"] == Z.REPLICATIONS
    assert (settings["bootstrap_draws"], settings["sign_flips"]) == (P.DRAWS, Z.FLIPS)
    assert settings["seed"] == settings["replication_seed"] == P.SEED
    assert report["proxy_pairs"] == Z.proxy_pairs()
    assert set(report["procedures"]) == set(Z.PROCEDURES)
    assert set(report["generators"]) == set(Z.GENERATORS)
    # The Monte Carlo standard error of a rejection rate of 0.05/6 is at most 0.001.
    assert np.sqrt((0.05 / 6) * (1 - 0.05 / 6) / settings["replications"]["null"]) <= 0.001
