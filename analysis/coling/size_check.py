"""Size and power of candidate test procedures for the confirmatory contrasts (PLAN.md section 6).

A confirmatory contrast is the mean, over statements, of a paired difference of the primary loss
(the comparator's loss minus the tested predictor's), and statements cluster in shortage
episodes of very unequal size. This module estimates by simulation, at the real episode
structure, how often each candidate procedure rejects a true null, how often it detects the
minimum detectable differences of ``out/power.json``, how often its 95% interval covers the
truth, and the familywise error of Holm's rule over the six tests. Train-period data only: the
episode structure of the test period is read from the eligible list (ids, no outcome), and the
paired differences come from the scoreable statements of the dev split.

Procedures (``procedures``; each gives a p-value for ``delta > 0``, one for ``delta < 0``, a
two-sided one and a 95% interval). ``S_g`` and ``n_g`` are the sum of the paired differences and
the number of statements of episode ``g``, ``G`` the number of episodes, ``N`` the number of
statements, ``delta = sum S_g / N`` and ``e_g = S_g - delta * n_g``.

* ``percentile``: the registered p-values of PLAN section 6, from ``predictors.cluster_draws``
  (10,000 draws of the episodes, seed 20261001), ``predictors.p_values`` and
  ``predictors.interval``. The mean of a draw is ``sum w_g S_g / sum w_g n_g``, as in the last
  line of ``predictors.bootstrap_means``; the tests check that the two agree exactly.
* ``bca``: the bias-corrected and accelerated interval on the same draws. The bias correction is
  the normal quantile of the share of draws below ``delta``; the acceleration comes from the
  estimates with one episode left out. Its p-value is the level at which the interval's end
  reaches zero, and equals the registered one when both corrections are zero.
* ``studentised`` and ``studentised_symmetric``: the bootstrap-t on the same draws. Each draw
  gives ``t* = (delta* - delta) / se*`` with the cluster-robust standard error of the draw, and
  ``t = delta / se`` is referred to the distribution of ``t*``: its two tails (equal-tailed), or
  ``|t|`` to ``|t*|`` (symmetric; the one-sided p-values are the same in both).
* ``sign_flip``: the cluster sign-flip test on the episode sums (the sensitivity analysis of the
  plan). ``sum S_g`` is referred to ``sum s_g S_g`` over 10,000 random sign vectors, with the
  count formula ``(1 + #) / (flips + 1)``; with so few episodes that all ``2^G`` sign vectors
  number at most ``flips``, all are used and the p-value is the exact share. Its interval is
  the percentile interval of the means over the random halves of the episodes (the episodes
  whose sign is flipped), which is the set of values the one-sided tests do not reject.
* ``sign_flip_t``: the same sign vectors with the studentised mean as the statistic: each
  flipped data set gives ``t* = delta* / se*`` with its own cluster-robust standard error, and
  ``t`` is referred to ``t*`` (the wild cluster bootstrap-t with the null imposed and signs as
  weights). No interval is computed here (it needs the test inverted over null values); its
  coverage is one minus the two-sided rejection rate of the true value.
* ``t_cr1``: the cluster-robust t test, ``se^2 = G / (G - 1) * sum e_g^2 / N^2``, ``G - 1``
  degrees of freedom.
* ``t_cr2`` and ``t_cr2_icc``: the bias-reduced standard error, ``se^2 = sum e_g^2 /
  (1 - n_g / N) / N^2``, with Satterthwaite degrees of freedom under a working model of
  independent statements (``t_cr2``), or of statements equally correlated within an episode at
  the correlation estimated as in ``power.clustered_variance`` (``t_cr2_icc``).
* ``t_cr3``: the leave-one-episode-out (jackknife) standard error, ``se^2 = (G - 1) / G *
  sum e_g^2 / (1 - n_g / N)^2 / N^2``, ``G - 1`` degrees of freedom.
* ``max_t``: each one-sided p-value is the larger of those of ``studentised`` and
  ``sign_flip_t`` (the same statistic ``t``, referred to the bootstrap draws and to the sign
  vectors), and the two-sided p-value is twice the smaller of the two one-sided ones, at most 1.
  It rejects only when both reject, so its size is at most the smaller of their two sizes. Its
  interval (the values the test does not reject) is not computed here; its coverage is one minus
  the two-sided rejection rate of the true value.

A test rejects when its p-value is below the level (0.05/6 and 0.05).

Structures. ``e3``: the episodes of the E3 eligible list. ``dev``: the episodes of the scoreable
dev statements (one registered selection is made there). ``e3_thinned``: the eligible list with
a seeded share of its statements kept (the registered share of scoreable statements once
``power.json`` carries it, else the scoreable share of the dated dev statements). Once
``power.json`` carries the registered counts, its minimum detectable differences are those of
the scoreable statements: ``e3_thinned`` is then the structure they were computed for, and
``e3`` has more statements than they assume.

Generators of the paired differences (every one has mean zero; an alternative adds a constant
to every statement, or under ``empirical_sparse`` to the statements of the active episodes).

* ``empirical``: whole-episode vectors of the real differences of a proxy pair of ``power.py``
  on the scoreable dev statements. Target episodes and dev episodes are each ranked by size
  (ties in the order of the episode ids). A target episode draws one of the ``WINDOW`` dev
  episodes nearest to it in rank share, uniformly, and takes as many consecutive differences
  as it has statements from that episode's differences in time order, from a uniform starting
  point, going round when the end is reached (so a target larger than its donor repeats the
  donor's vector). The constant subtracted from every difference is the expected mean under
  this scheme, so the null holds exactly. Going round keeps a donor's mean for a larger
  target, which raises the within-episode correlation above the dev estimate (the realised
  value is in the output). ``empirical_chained`` errs the other way: a target larger than its
  donor goes on with a new donor from its window, so a large target is several dev episodes
  in a row. ``empirical_any_size`` draws the donor from all dev episodes: a stress case, since
  a large target then often repeats a very small donor and the correlation is several times
  the dev estimate. ``empirical_sizes_drawn`` also draws the sizes: each target is a random
  episode of the structure (with its window), so sizes and differences are drawn together, as
  episodes from a population. There the expected sum of the differences is zero, and the
  mean over statements, a ratio of two random sums, has a small bias (a few hundredths of
  its standard error; the output gives the mean estimate of every scenario).
  ``empirical_sparse`` is ``empirical`` with every difference of an episode set to exactly zero
  unless the episode is active, which it is with chance ``SPARSE_SHARE`` (0.15), independently.
  This is the shape of H2, where the two sides read the statement in the same way, and so have
  the same loss, wherever the model's reading is the rule's. The constant subtracted is that of
  ``empirical`` (each episode's expected sum is scaled by the same chance), so the null holds
  exactly. An alternative is carried by the active episodes alone: the constant, divided by
  ``SPARSE_SHARE``, is added to their statements, so the expected mean moves by the constant
  and the other episodes stay at exactly zero.
* ``copula``: a random-effects model on a latent scale, ``z = sqrt(r) * a_g + sqrt(1 - r) *
  e_gi``, read through the empirical distribution of the pair's dev differences, so the
  marginal distribution (its bounds, skewness and atoms) is that of dev. ``r`` is set so that
  the correlation of two statements of one episode equals the dev estimate; ``copula_icc_half``
  and ``copula_icc_double`` halve and double it. ``copula_heavy`` draws the episode effect from
  a t distribution with 3 degrees of freedom (same marginal, same correlation);
  ``copula_extremes`` puts 2% of the statements at the bound of a Brier difference on the side
  of the longer tail (more skewness and kurtosis).

Familywise error. Six tests under a global null: H1 (one-sided), H2 and H3 (two-sided) for two
models, Holm at 0.05. The three contrasts of a model are drawn jointly: the same donor
statements under ``empirical``, and under ``copula`` latent effects and errors correlated as the
normal scores of the three dev differences are. The second model shares the first one's draw in
a share 0, 0.5 or 1 of the episodes (``empirical``), or has latent correlation 0, 0.5 or 1 with
it (``copula``).

Reproducibility. Replication ``k`` of a generator uses the stream seeded by (20261001, the
CRC-32 of the generator's label, ``k``), so the result does not depend on the number of worker
processes. ``--seed S`` puts ``S`` in place of 20261001 in these streams only, to repeat the
whole simulation on other data sets; the registered output uses 20261001. The draws of the
episodes and the sign vectors are the fixed ones of the procedures (seed 20261001), as they
will be in the analysis; ``other_draws`` reruns one generator with draws seeded (20261001, 1).

Output. ``out/size_check.json``: the settings, the proxy pairs of ``power.py``, the structures,
the dev estimates, and per scenario what the generator produced (the mean and the standard
deviation of the estimate, the mean within-episode correlation), every rejection rate with its
Monte Carlo standard error, the coverage of the intervals, the mean width of the bounded ones and
the share that is unbounded, the familywise error, and the runtime (the only field that changes
between runs). A power report written for other
proxy pairs is refused.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.size_check            # full run, writes the output
    PYTHONPATH=. python -m analysis.coling.size_check --quick    # reduced settings, prints only
    PYTHONPATH=. python -m analysis.coling.size_check --seed S --out FILE   # other data sets
    PYTHONPATH=. python -m pytest analysis/coling/test_size_check.py -q -p no:cacheprovider

Run the full command again after any change to its inputs (the statement table, the eligible
list, ``power.json``) or to this file: ``test_output_is_up_to_date`` fails until then. The
inputs and the code are hashed before the simulation and again after it, and a run during
which one of them changed writes nothing.
"""

from __future__ import annotations

import argparse
import json
import time
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
from scipy import stats
from scipy.optimize import brentq
from scipy.special import ndtr, ndtri
from threadpoolctl import threadpool_limits

from analysis.coling import dataset
from analysis.coling import power as W
from analysis.coling import predictors as P

SEED = P.SEED
DRAWS = P.DRAWS
FLIPS = 10_000
FAMILY_ALPHA = W.FAMILY_ALPHA
TESTS = W.TESTS
LEVELS = {"0.05/6": FAMILY_ALPHA / TESTS, "0.05": FAMILY_ALPHA}
COVERAGE = 0.95
SIDES = ("upper", "lower", "two_sided")
"""The alternative of a p-value: ``delta > 0``, ``delta < 0``, or either."""
FIELDS = ("p_upper", "p_lower", "p_two_sided", "low", "high")
"""The rows of a procedure's result: three p-values and the ends of the 95% interval."""
PROCEDURES = {
    "percentile": "registered percentile bootstrap p-value and interval (PLAN section 6)",
    "bca": "bias-corrected and accelerated bootstrap, p-value by inverting the interval",
    "studentised": "bootstrap-t on the cluster-robust standard error, equal-tailed",
    "studentised_symmetric": "bootstrap-t, symmetric two-sided p-value and interval",
    "sign_flip": "cluster sign-flip test on episode sums; interval of half-sample means",
    "sign_flip_t": "cluster sign-flip test on the studentised mean (wild cluster bootstrap-t)",
    "t_cr1": "cluster-robust t, G / (G - 1) correction, G - 1 degrees of freedom",
    "t_cr2": "bias-reduced cluster-robust t, Satterthwaite degrees of freedom (independence)",
    "t_cr2_icc": "bias-reduced cluster-robust t, Satterthwaite at the estimated correlation",
    "t_cr3": "leave-one-episode-out cluster-robust t, G - 1 degrees of freedom",
    "max_t": "larger of the bootstrap-t and studentised sign-flip p-values, each side",
}
NO_INTERVAL = ("sign_flip_t", "max_t")
"""Procedures whose interval is not computed here (the ends are missing)."""
WINDOW = 8
"""Dev episodes a target episode draws its donor from (the nearest in size rank)."""
SPARSE_SHARE = 0.15
"""The chance that an episode of ``empirical_sparse`` has differences other than zero."""
HEAVY_DF = 3
EXTREME_SHARE = 0.02
BRIER_BOUND = 1.0
"""The largest absolute difference of two primary losses."""
NODES = 2_000
"""Points of the midpoint rule over the episode effect when the latent loading is calibrated."""
GRID_REACH = 40.0
GRID_POINTS = 8_001
"""The grid on which the distribution of the latent variable is tabulated when the episode
effect is not normal."""
CHUNK = 250
"""Columns (replications by contrasts) per task. Fixed: the mean widths are summed task by task."""
REPLICATIONS = {"null": 40_000, "power": 10_000, "family": 20_000}
QUICK = {"null": 400, "power": 200, "family": 200, "draws": 1_000, "flips": 1_000}
PAIRS = tuple(pair.hypothesis for pair in W.PROXY_PAIRS)
SIDED = {pair.hypothesis: pair.sides for pair in W.PROXY_PAIRS}
DEPENDENCE = (0.0, 0.5, 1.0)
OUT = dataset.OUT
REPORT = OUT / "size_check.json"
POWER_REPORT = W.POWER_REPORT
COMMAND = "PYTHONPATH=. python -m analysis.coling.size_check"

Seed = int | tuple[int, ...]


# --------------------------------------------------------------------------------------------
# Episode sums
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Sums:
    """Episode totals of one or more contrasts (columns): all a procedure needs."""

    total: np.ndarray
    """Episodes by columns: the sum of the paired differences of each episode."""
    size: np.ndarray
    """Episodes by columns, or by one column when every column has the same sizes."""
    squares: np.ndarray
    """Per column: the sum of the squared differences over all statements."""

    @property
    def statements(self) -> np.ndarray:
        return self.size.sum(axis=0)

    @property
    def delta(self) -> np.ndarray:
        """The mean paired difference over statements."""
        return self.total.sum(axis=0) / self.statements

    @property
    def residual(self) -> np.ndarray:
        """``e_g = S_g - delta * n_g``."""
        return self.total - self.size * self.delta


def episode_sums(values: Any, clusters: Sequence[Any], null: float = 0.0) -> Sums:
    """The episode totals of each column of ``values`` (statements by contrasts) minus ``null``,
    with the episodes in the order of ``predictors.cluster_sums``."""
    values = np.asarray(values, dtype=float)
    values = (values[:, None] if values.ndim == 1 else values) - null
    total, size = P.cluster_sums(values, clusters)
    return Sums(total, size[:, None], (values**2).sum(axis=0))


def robust_se(sums: Sums) -> np.ndarray:
    """The cluster-robust standard error of ``delta``, as ``power.clustered_variance`` has it."""
    groups = len(sums.total)
    return np.sqrt(groups / (groups - 1) * (sums.residual**2).sum(axis=0)) / sums.statements


def within_correlation(sums: Sums) -> np.ndarray:
    """The correlation of two statements of one episode implied by the design effect, kept
    within 0 to 1 (the estimate of ``power.clustered_variance``)."""
    n = sums.statements
    variance = (sums.squares - n * sums.delta**2) / (n - 1)
    weighted = (sums.size**2).sum(axis=0) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        effect = np.where(variance > 0, robust_se(sums) ** 2 / (variance / n), 1.0)
        icc = np.where(weighted > 1, (effect - 1.0) / (weighted - 1.0), 0.0)
    return np.clip(icc, 0.0, 1.0)


def shifted(
    total: np.ndarray, size: np.ndarray, squares: np.ndarray, shift: Any
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The episode totals, the sizes and the episode sums of squares (episodes by columns) when
    ``shift`` is added to every paired difference: one number, or one per episode."""
    shift = np.asarray(shift, dtype=float).reshape(-1, 1)
    count = size.reshape(-1, 1)
    return total + shift * count, size, squares + 2 * shift * total + shift**2 * count


# --------------------------------------------------------------------------------------------
# Bootstrap procedures: percentile (registered), BCa, studentised
# --------------------------------------------------------------------------------------------


@lru_cache(maxsize=8)
def draw_matrix(clusters: int, draws: int = DRAWS, seed: Seed = SEED) -> np.ndarray:
    """The registered draws of the episodes (``predictors.cluster_draws``), as floats."""
    return P.cluster_draws(clusters, draws, seed).astype(float)


def bootstrap(sums: Sums, draws: int = DRAWS, seed: Seed = SEED) -> tuple[np.ndarray, np.ndarray]:
    """The mean and its cluster-robust standard error in each draw of the episodes (draws by
    columns). The means are those of ``predictors.bootstrap_means``."""
    groups = len(sums.total)
    taken = draw_matrix(groups, draws, seed)
    n = taken @ sums.size
    drawn = taken @ sums.total
    drawn[np.abs(drawn) <= 1e-12 * np.maximum(1.0, np.abs(sums.total).max(axis=0))] = 0.0
    means = drawn / n
    shift, e = means - sums.delta, sums.residual
    squares = (
        taken @ e**2 - 2 * shift * (taken @ (e * sums.size)) + shift**2 * (taken @ sums.size**2)
    )
    return means, np.sqrt(groups / (groups - 1) * np.maximum(squares, 0.0)) / n


def by_column(draws: np.ndarray) -> np.ndarray:
    """The columns of ``draws`` as the rows of a new array (each one contiguous, which is what
    makes counting and sorting them fast)."""
    return np.ascontiguousarray(draws.T)


def column_quantiles(draws: np.ndarray, levels: Any) -> np.ndarray:
    """The quantiles of each column of ``draws`` (levels by columns, or columns for one level)."""
    return np.quantile(by_column(draws), levels, axis=1)


def percentile(means: np.ndarray) -> np.ndarray:
    """The registered p-values and percentile interval of each column of bootstrap means."""
    out = np.empty((len(FIELDS), means.shape[1]))
    for k, column in enumerate(by_column(means)):
        p = P.p_values(column)
        lower = P.p_values(-column)["one_sided"]
        out[:, k] = p["one_sided"], lower, p["two_sided"], *P.interval(column, COVERAGE)
    return out


def left_out(sums: Sums) -> np.ndarray:
    """The estimate with each episode left out in turn (episodes by columns)."""
    return (sums.total.sum(axis=0) - sums.total) / (sums.statements - sums.size)


def acceleration(sums: Sums) -> np.ndarray:
    """The acceleration constant of the BCa interval, from the leave-one-episode-out estimates."""
    away = left_out(sums)
    away = away.mean(axis=0) - away
    cube, square = (away**3).sum(axis=0), (away**2).sum(axis=0)
    return np.where(square > 0, cube / (6 * np.where(square > 0, square, 1.0) ** 1.5), 0.0)


def bca_level(z: Any, z0: np.ndarray, a: np.ndarray) -> np.ndarray:
    """The level of the bootstrap distribution that the BCa interval reads for the nominal
    normal quantile ``z``."""
    v = z0 + z
    room = 1 - a * v
    ok = room > 0
    return ndtr(z0 + np.where(ok, v / np.where(ok, room, 1.0), np.where(v > 0, np.inf, -np.inf)))


def bca_nominal(level: np.ndarray, z0: np.ndarray, a: np.ndarray) -> np.ndarray:
    """The inverse of ``bca_level``: the nominal level whose BCa end sits at ``level`` of the
    bootstrap distribution."""
    w = ndtri(level) - z0
    room = 1 + a * w
    ok = room > 0
    u = np.where(ok, w / np.where(ok, room, 1.0), np.where(w > 0, np.inf, -np.inf))
    return ndtr(u - z0)


def bca(means: np.ndarray, sums: Sums) -> np.ndarray:
    """The BCa p-values and interval of each column (see the module docstring)."""
    draws, delta = len(means), sums.delta
    edge = 0.5 / (draws + 1)
    below = ((means < delta).sum(axis=0) + 0.5 * (means == delta).sum(axis=0)) / draws
    z0, a = ndtri(np.clip(below, edge, 1 - edge)), acceleration(sums)
    at_most = np.clip((1 + (means <= 0).sum(axis=0)) / (draws + 1), edge, 1 - edge)
    under = np.clip(1 - (1 + (means >= 0).sum(axis=0)) / (draws + 1), edge, 1 - edge)
    upper, lower = bca_nominal(at_most, z0, a), 1 - bca_nominal(under, z0, a)
    tail = (1 - COVERAGE) / 2
    levels = np.stack([bca_level(ndtri(tail), z0, a), bca_level(ndtri(1 - tail), z0, a)])
    ends = [np.quantile(column, levels[:, k]) for k, column in enumerate(by_column(means))]
    two = np.minimum(1.0, 2 * np.minimum(upper, lower))
    return np.stack([upper, lower, two, *np.asarray(ends).T])


def studentised(means: np.ndarray, errors: np.ndarray, sums: Sums) -> tuple[np.ndarray, np.ndarray]:
    """The bootstrap-t results of each column: equal-tailed, and symmetric."""
    draws, delta, se = len(means), sums.delta, robust_se(sums)
    keep = {"nan": 0.0, "posinf": np.inf, "neginf": -np.inf}
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.nan_to_num((means - delta) / errors, **keep)
        observed = np.nan_to_num(delta / se, **keep)
        upper = (1 + (t >= observed).sum(axis=0)) / (draws + 1)
        lower = (1 + (t <= observed).sum(axis=0)) / (draws + 1)
        beyond = (1 + (np.abs(t) >= np.abs(observed)).sum(axis=0)) / (draws + 1)
        tail = (1 - COVERAGE) / 2
        low, high = column_quantiles(t, [tail, 1 - tail])
        reach = column_quantiles(np.abs(t), COVERAGE)
        # A quantile between two draws without variance is undefined: that end is unbounded.
        low, high = np.nan_to_num(low, nan=-np.inf), np.nan_to_num(high, nan=np.inf)
        reach = np.nan_to_num(reach, nan=np.inf)
        two = np.minimum(1.0, 2 * np.minimum(upper, lower))
        equal = np.stack([upper, lower, two, delta - high * se, delta - low * se])
        symmetric = np.stack([upper, lower, beyond, delta - reach * se, delta + reach * se])
    return equal, symmetric


# --------------------------------------------------------------------------------------------
# The cluster sign-flip test
# --------------------------------------------------------------------------------------------


@lru_cache(maxsize=8)
def flip_matrix(clusters: int, flips: int = FLIPS, seed: Seed = SEED) -> tuple[np.ndarray, bool]:
    """Sign vectors (rows) for ``clusters`` episodes, and whether they are all ``2^clusters``
    of them: every vector when there are at most ``flips``, else ``flips`` random ones."""
    if 2**clusters <= flips:
        bits = (np.arange(2**clusters)[:, None] >> np.arange(clusters)[None, :]) & 1
        return 1.0 - 2.0 * bits, True
    rng = np.random.default_rng(seed)
    return 1.0 - 2.0 * rng.integers(0, 2, size=(flips, clusters)), False


def flip_p_values(flipped: np.ndarray, observed: np.ndarray, exhaustive: bool) -> list[np.ndarray]:
    """The p-values of ``observed`` among the statistics of the flipped data (flips by
    columns): for a larger value, a smaller one, a larger size. The count formula ``(1 + #) /
    (flips + 1)`` with random sign vectors, the exact share when all of them are used. A
    flipped statistic that falls short of the observed one by less than 1e-9 times the largest
    finite absolute flipped statistic counts as reaching it."""
    finite = np.where(np.isfinite(flipped), np.abs(flipped), 0.0)
    slack = 1e-9 * np.maximum(finite.max(axis=0), 1e-300)
    one = 0 if exhaustive else 1
    upper = (flipped >= observed - slack).sum(axis=0)
    lower = (flipped <= observed + slack).sum(axis=0)
    beyond = (np.abs(flipped) >= np.abs(observed) - slack).sum(axis=0)
    return [(one + count) / (len(flipped) + one) for count in (upper, lower, beyond)]


def sign_flip(sums: Sums, flips: int = FLIPS, seed: Seed = SEED) -> tuple[np.ndarray, np.ndarray]:
    """The sign-flip results of each column: on the episode sums, with the interval of the
    half-sample means; and on the studentised mean, with no interval."""
    signs, exhaustive = flip_matrix(len(sums.total), flips, seed)
    groups, n, total = len(sums.total), sums.statements, sums.total
    flipped = signs @ total
    half = (1.0 - signs) / 2
    half = half[half.sum(axis=1) > 0]
    means = (half @ total) / (half @ sums.size)
    tail = (1 - COVERAGE) / 2
    ends = column_quantiles(means, [tail, 1 - tail])
    plain = np.stack([*flip_p_values(flipped, total.sum(axis=0), exhaustive), *ends])
    mean = flipped / n
    squares = (total**2).sum(axis=0) - 2 * mean * (signs @ (total * sums.size))
    squares += mean**2 * (sums.size**2).sum(axis=0)
    keep = {"nan": 0.0, "posinf": np.inf, "neginf": -np.inf}
    with np.errstate(divide="ignore", invalid="ignore"):
        error = np.sqrt(groups / (groups - 1) * np.maximum(squares, 0.0)) / n
        t = np.nan_to_num(mean / error, **keep)
        observed = np.nan_to_num(sums.delta / robust_se(sums), **keep)
        p = flip_p_values(t, observed, exhaustive)
    missing = np.full(len(observed), np.nan)
    return plain, np.stack([*p, missing, missing])


# --------------------------------------------------------------------------------------------
# Cluster-robust t tests
# --------------------------------------------------------------------------------------------


def satterthwaite_terms(size: np.ndarray) -> dict[str, np.ndarray]:
    """The traces from which the Satterthwaite degrees of freedom of the bias-reduced variance
    follow at any within-episode correlation (per column of ``size``).

    The variance estimate is ``sum_g (a_g' y)^2`` with ``a_g = (I - H) 1_g / (N sqrt(1 -
    h_g))`` and ``h_g = n_g / N``. Under a working covariance ``(1 - rho) I + rho B`` (``B``
    the indicator of two statements sharing an episode) its degrees of freedom are ``tr(M)^2 /
    tr(M^2)`` with ``M_gh = a_g' ((1 - rho) I + rho B) a_h``. ``N a_g' a_h`` is ``independent``
    below and ``N a_g' B a_h`` is ``shared``.
    """
    n = size.sum(axis=0)
    h = size / n
    q = h / np.sqrt(1 - h)
    outer = q[:, None, :] * q[None, :, :]
    eye = np.eye(len(size))[:, :, None]
    independent = eye * (h / (1 - h))[None, :, :] - outer
    spread = (h**2).sum(axis=0) - h[:, None, :] - h[None, :, :]
    shared = n * (eye * (q**2)[None, :, :] + outer * spread)
    return {
        "t_i": np.einsum("iik->k", independent),
        "t_s": np.einsum("iik->k", shared),
        "ii": (independent**2).sum(axis=(0, 1)),
        "is": (independent * shared).sum(axis=(0, 1)),
        "ss": (shared**2).sum(axis=(0, 1)),
    }


def satterthwaite(terms: Mapping[str, np.ndarray], rho: Any = 0.0) -> np.ndarray:
    """The degrees of freedom at within-episode correlation ``rho``."""
    rho = np.asarray(rho, dtype=float)
    top = ((1 - rho) * terms["t_i"] + rho * terms["t_s"]) ** 2
    mixed = 2 * rho * (1 - rho) * terms["is"]
    return top / ((1 - rho) ** 2 * terms["ii"] + mixed + rho**2 * terms["ss"])


def t_result(delta: np.ndarray, variance: np.ndarray, df: Any) -> np.ndarray:
    """The p-values and interval of a t test of ``delta`` with the given variance."""
    se = np.sqrt(variance)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.nan_to_num(delta / se, nan=0.0, posinf=np.inf, neginf=-np.inf)
    upper, lower = stats.t.sf(t, df), stats.t.cdf(t, df)
    reach = stats.t.ppf(1 - (1 - COVERAGE) / 2, df) * se
    return np.stack([upper, lower, 2 * stats.t.sf(np.abs(t), df), delta - reach, delta + reach])


def robust_t(sums: Sums) -> dict[str, np.ndarray]:
    """The four cluster-robust t tests of each column (see the module docstring)."""
    groups, n, delta = len(sums.total), sums.statements, sums.delta
    e2, rest = sums.residual**2, 1 - sums.size / n
    cr1 = groups / (groups - 1) * e2.sum(axis=0) / n**2
    cr2 = (e2 / rest).sum(axis=0) / n**2
    cr3 = (groups - 1) / groups * (e2 / rest**2).sum(axis=0) / n**2
    terms = satterthwaite_terms(sums.size)
    return {
        "t_cr1": t_result(delta, cr1, groups - 1),
        "t_cr2": t_result(delta, cr2, satterthwaite(terms)),
        "t_cr2_icc": t_result(delta, cr2, satterthwaite(terms, within_correlation(sums))),
        "t_cr3": t_result(delta, cr3, groups - 1),
    }


# --------------------------------------------------------------------------------------------
# All procedures, and Holm's rule
# --------------------------------------------------------------------------------------------


def procedures(
    sums: Sums, draws: int = DRAWS, flips: int = FLIPS, seed: Seed = SEED
) -> dict[str, np.ndarray]:
    """Every procedure on every column of ``sums``: by name, an array of ``FIELDS`` by columns."""
    if len(sums.total) < 2:
        raise ValueError("the procedures need at least two episodes")
    means, errors = bootstrap(sums, draws, seed)
    equal, symmetric = studentised(means, errors, sums)
    plain, flipped_t = sign_flip(sums, flips, seed)
    out = {
        "percentile": percentile(means),
        "bca": bca(means, sums),
        "studentised": equal,
        "studentised_symmetric": symmetric,
        "sign_flip": plain,
        "sign_flip_t": flipped_t,
        **robust_t(sums),
        "max_t": larger(equal, flipped_t),
    }
    return {name: out[name] for name in PROCEDURES}


def larger(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """The one-sided p-values of two procedures, the larger on each side; the two-sided one is
    twice the smaller of the two, at most 1; no interval."""
    upper, lower = np.maximum(first[0], second[0]), np.maximum(first[1], second[1])
    missing = np.full(len(upper), np.nan)
    return np.stack([upper, lower, np.minimum(1.0, 2 * np.minimum(upper, lower)), missing, missing])


def contrast_tests(
    values: Any,
    clusters: Sequence[Any],
    null: float = 0.0,
    draws: int = DRAWS,
    flips: int = FLIPS,
    seed: Seed = SEED,
) -> dict[str, dict[str, float]]:
    """Every procedure on one vector of paired differences, testing ``delta = null``."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1:
        raise ValueError("one vector of paired differences")
    out = {}
    for name, result in procedures(
        episode_sums(values, clusters, null), draws, flips, seed
    ).items():
        row = dict(zip(FIELDS, (float(x) for x in result[:, 0]), strict=True))
        out[name] = {**row, "low": row["low"] + null, "high": row["high"] + null}
    return out


def holm(p: Any) -> np.ndarray:
    """Holm's step-down adjusted p-values of each row of ``p``."""
    p = np.atleast_2d(np.asarray(p, dtype=float))
    order = np.argsort(p, axis=1, kind="stable")
    ranked = np.take_along_axis(p, order, axis=1) * (p.shape[1] - np.arange(p.shape[1]))
    ranked = np.minimum(1.0, np.maximum.accumulate(ranked, axis=1))
    out = np.empty_like(p)
    np.put_along_axis(out, order, ranked, axis=1)
    return out


# --------------------------------------------------------------------------------------------
# Structures
# --------------------------------------------------------------------------------------------


def sizes_of(episodes: Sequence[str]) -> np.ndarray:
    """Statements per episode, in the order of the sorted episode ids."""
    return pd.Series(list(episodes)).value_counts().sort_index().to_numpy()


def thinned(eligible: pd.DataFrame, share: float, seed: int = SEED) -> np.ndarray:
    """The episode sizes when a share of the eligible statements is kept: the statements are
    sorted by id, permuted with the seed, and the first ``round(share * N)`` are kept."""
    rows = eligible.sort_values("statement_group_id")
    keep = np.random.default_rng(seed).permutation(len(rows))[: round(share * len(rows))]
    return sizes_of(rows["episode_id"].to_numpy()[np.sort(keep)])


def structure_record(sizes: np.ndarray) -> dict[str, Any]:
    """What a structure looks like: the numbers that govern the tests."""
    n, ordered = int(sizes.sum()), np.sort(sizes)[::-1]
    return {
        "episodes": len(sizes),
        "statements": n,
        "weighted_statements_per_episode": float((sizes**2).sum() / n),
        "effective_episodes": float(n**2 / (sizes**2).sum()),
        "largest_episode": int(ordered[0]),
        "share_of_statements_in_the_10_largest": float(ordered[:10].sum() / n),
    }


# --------------------------------------------------------------------------------------------
# The dev differences
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Donors:
    """The paired differences of the proxy pairs on the scoreable dev statements, episode by
    episode (sorted ids) and in time order inside an episode."""

    values: np.ndarray
    """Statements by pairs (``PAIRS``)."""
    sizes: np.ndarray
    """Statements per dev episode."""


def dev_donors(table: pd.DataFrame, frame: pd.DataFrame | None = None) -> Donors:
    """Fit the model-free predictors on the fit split (``power.fit_and_predict``) and take the
    paired differences of the proxy pairs on the scoreable dev statements. ``frame`` is the
    typed frame of ``table`` when it is already at hand."""
    frame = P.prepare(table) if frame is None else frame
    with threadpool_limits(limits=1):
        _, dev, predictions = W.fit_and_predict(frame)
    scoreable = dev[dev["scoreable"]]
    losses = W.primary_losses(scoreable, predictions)
    day = table.set_index("statement_group_id")["event_date"].reindex(scoreable.index)
    rows = pd.DataFrame({"episode": scoreable["episode_id"], "day": day, "id": scoreable.index})
    order = rows.sort_values(["episode", "day", "id"]).index
    values = np.column_stack(
        [(losses[p.comparator] - losses[p.tested]).loc[order] for p in W.PROXY_PAIRS]
    )
    return Donors(values, sizes_of(scoreable["episode_id"]))


def pair_record(donors: Donors) -> dict[str, dict[str, Any]]:
    """The dev estimates each generator is matched to, per proxy pair."""
    clusters = np.repeat([f"{k:06d}" for k in range(len(donors.sizes))], donors.sizes)
    out = {}
    for k, pair in enumerate(W.PROXY_PAIRS):
        d = donors.values[:, k]
        spread = d.std() > 0
        out[pair.hypothesis] = {
            "comparator": pair.comparator,
            "tested": pair.tested,
            "sides": pair.sides,
            **W.clustered_variance(d, clusters),
            "skewness": float(stats.skew(d)) if spread else 0.0,
            "excess_kurtosis": float(stats.kurtosis(d)) if spread else 0.0,
            "smallest": float(d.min()),
            "largest": float(d.max()),
            "distinct_values": len(np.unique(d)),
        }
    return out


# --------------------------------------------------------------------------------------------
# Generator 1: whole episodes of the dev differences
# --------------------------------------------------------------------------------------------


def size_ranks(sizes: np.ndarray) -> np.ndarray:
    """The rank share of each episode by size, in 0 to 1 (ties in the order given)."""
    ranks = np.empty(len(sizes))
    ranks[np.argsort(sizes, kind="stable")] = np.arange(len(sizes))
    return (ranks + 0.5) / len(sizes)


def donor_windows(targets: np.ndarray, donors: np.ndarray, window: int) -> np.ndarray:
    """For each target episode, the ``window`` donor episodes nearest in size rank (targets by
    window; a nearer donor first, ties in the order of the donors)."""
    gap = np.abs(size_ranks(targets)[:, None] - size_ranks(donors)[None, :])
    return np.argsort(gap, axis=1, kind="stable")[:, : min(window, len(donors))]


@dataclass(frozen=True)
class Empirical:
    """Whole-episode draws of the dev differences (see the module docstring)."""

    sizes: np.ndarray
    window: np.ndarray
    donor_sizes: np.ndarray
    base: np.ndarray
    """Where each donor's running sums start in ``first`` and ``second``."""
    first: np.ndarray
    """Running sums of each donor's centred differences, written out twice (to go round)."""
    second: np.ndarray
    """The same for their squares."""
    centre: np.ndarray
    """The constant subtracted from the differences of each pair."""
    chained: bool = False
    """A target larger than its donor goes on with a new donor instead of going round."""
    sizes_drawn: bool = False
    active: float = 1.0
    """The chance that an episode keeps its differences; the others are all zero."""

    @property
    def columns(self) -> int:
        return self.first.shape[1]

    def draw(
        self, rng: np.random.Generator, shift: float = 0.0
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """One data set: per episode, the sum of each pair's differences, the number of
        statements, and the sum of the squared differences. ``shift`` is the alternative,
        added to every difference; when not every episode is active, it is divided by the
        chance of being active and added to the differences of the active episodes alone."""
        total, size, squares = self.dense(rng)
        if self.active >= 1:
            return shifted(total, size, squares, shift)
        kept = rng.random(len(size)) < self.active
        total = np.where(kept[:, None], total, 0.0)
        squares = np.where(kept[:, None], squares, 0.0)
        return shifted(total, size, squares, shift * kept / self.active)

    def dense(self, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """``draw`` with every episode active."""
        groups = len(self.sizes)
        slot = rng.integers(0, groups, groups) if self.sizes_drawn else np.arange(groups)
        size = self.sizes[slot]
        left, rows = size.copy(), np.arange(groups)
        total, squares = np.zeros((groups, self.columns)), np.zeros((groups, self.columns))
        while len(rows):
            donor = self.window[slot[rows], rng.integers(0, self.window.shape[1], len(rows))]
            length = self.donor_sizes[donor]
            start = self.base[donor] + (rng.random(len(rows)) * length).astype(int)
            take = np.minimum(left[rows], length) if self.chained else left[rows]
            copies, rest = np.divmod(take, length)
            for out, running in ((total, self.first), (squares, self.second)):
                once = running[self.base[donor] + length] - running[self.base[donor]]
                out[rows] += copies[:, None] * once + running[start + rest] - running[start]
            left[rows] -= take
            rows = rows[left[rows] > 0]
        return total, size.astype(float), squares


def expected_totals(
    sizes: np.ndarray,
    windows: np.ndarray,
    donor_sizes: np.ndarray,
    means: np.ndarray,
    chained: bool,
) -> np.ndarray:
    """The expected sum of each target episode (targets by pairs) when the donors' mean
    differences are ``means``: the size times the mean over the window when a donor is gone
    round; when donors are chained, by recursion on the statements still to fill."""
    plain = sizes[:, None] * means[windows].mean(axis=1)
    if not chained:
        return plain
    out = np.empty_like(plain)
    for g, size in enumerate(sizes):
        length, mean = donor_sizes[windows[g]], means[windows[g]]
        filled = np.zeros((size + 1, means.shape[1]))
        for r in range(1, size + 1):
            more = filled[np.maximum(r - length, 0)]
            filled[r] = (np.minimum(r, length)[:, None] * mean + more).mean(axis=0)
        out[g] = filled[size]
    return out


def empirical(
    donors: Donors,
    sizes: np.ndarray,
    window: int = WINDOW,
    chained: bool = False,
    sizes_drawn: bool = False,
    active: float = 1.0,
) -> Empirical:
    """The whole-episode generator for target episodes of the given sizes, centred so that the
    expected sum of the differences over all statements is zero. With ``active`` below 1 an
    episode keeps its differences with that chance and is all zero otherwise; the constant is
    the same, since every episode's expected sum is scaled by the same chance."""
    windows = donor_windows(sizes, donors.sizes, window)
    ends = np.cumsum(donors.sizes)
    starts = ends - donors.sizes
    means = np.stack([donors.values[a:b].mean(axis=0) for a, b in zip(starts, ends, strict=True)])
    expected = expected_totals(sizes, windows, donors.sizes, means, chained)
    centre = expected.sum(axis=0) / sizes.sum()
    first, second, base, at = [], [], [], 0
    for a, b in zip(starts, ends, strict=True):
        twice = np.concatenate([donors.values[a:b], donors.values[a:b]]) - centre
        zero = np.zeros((1, twice.shape[1]))
        first.append(np.concatenate([zero, np.cumsum(twice, axis=0)]))
        second.append(np.concatenate([zero, np.cumsum(twice**2, axis=0)]))
        base.append(at)
        at += len(twice) + 1
    return Empirical(
        sizes,
        windows,
        donors.sizes,
        np.asarray(base),
        np.concatenate(first),
        np.concatenate(second),
        centre,
        chained,
        sizes_drawn,
        active,
    )


@dataclass(frozen=True)
class TwoModels:
    """Two models' contrasts on the same episodes: the second model shares the first one's
    draw in a share of the episodes and has a draw of its own in the others."""

    one: Empirical
    share: float

    @property
    def columns(self) -> int:
        return 2 * self.one.columns

    def draw(
        self, rng: np.random.Generator, shift: float = 0.0
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        total, size, squares = self.one.draw(rng, shift)
        other_total, _, other_squares = self.one.draw(rng, shift)
        same = (rng.random(len(size)) < self.share)[:, None]
        return (
            np.hstack([total, np.where(same, total, other_total)]),
            size,
            np.hstack([squares, np.where(same, squares, other_squares)]),
        )


# --------------------------------------------------------------------------------------------
# Generator 2: random effects on a latent scale, read through the dev distribution
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Marginal:
    """A discrete distribution of the paired difference, with mean zero."""

    support: np.ndarray
    """Its values, sorted."""
    cumulative: np.ndarray
    """The probability of a value at or below each one."""

    @property
    def variance(self) -> float:
        weights = np.diff(self.cumulative, prepend=0.0)
        return float((weights * self.support**2).sum())


def marginal(values: np.ndarray, extreme_share: float = 0.0) -> Marginal:
    """The empirical distribution of ``values``, centred. With ``extreme_share``, that share of
    the mass is moved to the bound of a Brier difference on the side of the longer tail."""
    values = np.asarray(values, dtype=float)
    weights = np.full(len(values), (1.0 - extreme_share) / len(values))
    if extreme_share > 0:
        side = -BRIER_BOUND if stats.skew(values) < 0 else BRIER_BOUND
        values, weights = np.append(values, side), np.append(weights, extreme_share)
    order = np.argsort(values, kind="stable")
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    return Marginal(values - (weights * values).sum(), cumulative / cumulative[-1])


@lru_cache(maxsize=2)
def effect_nodes(heavy: bool) -> np.ndarray:
    """Equally likely values of the episode effect (unit variance): normal, or t with
    ``HEAVY_DF`` degrees of freedom."""
    levels = (np.arange(NODES) + 0.5) / NODES
    if heavy:
        return stats.t.ppf(levels, HEAVY_DF) / np.sqrt(HEAVY_DF / (HEAVY_DF - 2))
    return ndtri(levels)


def latent_cuts(cumulative: np.ndarray, loading: float, heavy: bool) -> np.ndarray:
    """The quantiles of the latent variable at the cumulative probabilities but the last: the
    points where the paired difference steps from one value of its support to the next."""
    levels = cumulative[:-1]
    if not heavy or loading <= 0:
        return ndtri(levels)
    grid = np.linspace(-GRID_REACH, GRID_REACH, GRID_POINTS)
    scaled = np.sqrt(loading) * effect_nodes(True)
    blocks = [grid[k : k + 500, None] for k in range(0, len(grid), 500)]
    cdf = [ndtr((block - scaled) / np.sqrt(1 - loading)).mean(axis=1) for block in blocks]
    return np.interp(levels, np.concatenate(cdf), grid)


def induced_correlation(m: Marginal, loading: float, heavy: bool = False) -> float:
    """The correlation of two statements of one episode when the latent loading (the share of
    the latent variance that is the episode effect) is ``loading``."""
    if loading <= 0 or m.variance <= 0:
        return 0.0
    cuts = latent_cuts(m.cumulative, loading, heavy)
    effect = np.sqrt(loading) * effect_nodes(heavy)
    below = ndtr((cuts[None, :] - effect[:, None]) / np.sqrt(1 - loading))
    episode_mean = m.support[-1] - below @ np.diff(m.support)
    return float(episode_mean.var() / m.variance)


def calibrate(m: Marginal, target: float, heavy: bool = False) -> float:
    """The latent loading at which the within-episode correlation is ``target``."""
    top = 1.0 - 1e-6
    if target <= 0 or m.variance <= 0:
        return 0.0
    if induced_correlation(m, top, heavy) <= target:
        return top
    return float(brentq(lambda r: induced_correlation(m, r, heavy) - target, 1e-9, top, xtol=1e-10))


def normal_scores(values: np.ndarray) -> np.ndarray:
    """The correlation matrix of the normal scores of the columns (ties share a mean rank)."""
    ranks = stats.rankdata(values, axis=0)
    scores = ndtri((ranks - 0.5) / len(values))
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.corrcoef(scores, rowvar=False)
    corr = np.where(np.isfinite(corr), corr, 0.0)
    np.fill_diagonal(corr, 1.0)
    return corr


def root(correlation: np.ndarray) -> np.ndarray:
    """A factor ``F`` with ``F F' = correlation``: the lower-triangular one, or one from the
    eigenvectors when the matrix is singular."""
    try:
        return np.linalg.cholesky(correlation)
    except np.linalg.LinAlgError:
        values, vectors = np.linalg.eigh(correlation)
        return vectors * np.sqrt(np.maximum(values, 0.0))


def two_model_root(dependence: float, within: np.ndarray) -> np.ndarray:
    """A factor of the correlation of two models' contrasts: ``within`` inside a model, and
    ``dependence`` times ``within`` between the models (which may be 1)."""
    between = np.array([[1.0, 0.0], [dependence, np.sqrt(1.0 - dependence**2)]])
    return np.kron(between, root(within))


@dataclass(frozen=True)
class Copula:
    """The latent random-effects generator (see the module docstring), for one contrast or for
    several correlated ones (columns)."""

    sizes: np.ndarray
    supports: tuple[np.ndarray, ...]
    cuts: tuple[np.ndarray, ...]
    loading: np.ndarray
    mix: np.ndarray
    """The factor of the correlation between the columns' latent effects and errors."""
    heavy: bool = False

    @property
    def columns(self) -> int:
        return len(self.supports)

    def draw(
        self, rng: np.random.Generator, shift: float = 0.0
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        groups, columns = len(self.sizes), self.columns
        effect = rng.standard_normal((groups, columns)) @ self.mix.T
        if self.heavy:
            effect /= np.sqrt(rng.chisquare(HEAVY_DF, groups) / (HEAVY_DF - 2))[:, None]
        noise = rng.standard_normal((int(self.sizes.sum()), columns)) @ self.mix.T
        latent = np.sqrt(self.loading) * np.repeat(effect, self.sizes, axis=0)
        latent += np.sqrt(1 - self.loading) * noise
        values = np.column_stack(
            [self.supports[k][np.searchsorted(self.cuts[k], latent[:, k])] for k in range(columns)]
        )
        starts = np.cumsum(self.sizes) - self.sizes
        return shifted(
            np.add.reduceat(values, starts, axis=0),
            self.sizes.astype(float),
            np.add.reduceat(values**2, starts, axis=0),
            shift,
        )


def copula(
    sizes: np.ndarray,
    marginals: Sequence[Marginal],
    loadings: Sequence[float],
    heavy: bool = False,
    mix: np.ndarray | None = None,
) -> Copula:
    """The latent generator for episodes of the given sizes: one column per marginal, each
    with its latent loading (``calibrate``). ``mix`` is a factor of the correlation between
    the columns (none: independent columns)."""
    pairs = list(zip(marginals, loadings, strict=True))
    cuts = tuple(latent_cuts(m.cumulative, r, heavy) for m, r in pairs)
    mix = np.eye(len(pairs)) if mix is None else mix
    supports = tuple(m.support for m in marginals)
    return Copula(sizes, supports, cuts, np.asarray(loadings, dtype=float), mix, heavy)


# --------------------------------------------------------------------------------------------
# The simulation
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """One block of replications of one scenario."""

    scenario: int
    generator: str
    """The label of the generator: structure, generator and pair (or ``family``)."""
    shift: float
    first: int
    count: int
    draws: int
    flips: int
    seed: Seed = SEED
    """The seed of the bootstrap draws and the sign vectors."""
    family: bool = False
    streams: int = SEED
    """The master seed of the replications' random streams."""


DATA = "data"
"""The key of a scenario's tally of what its generator produced (beside the procedures)."""
_GENERATORS: dict[str, Any] = {}


def _start(generators: Mapping[str, Any], worker: bool = True) -> None:
    """Hand the generators to ``run_task``; a worker process is also kept to one thread."""
    if worker:
        threadpool_limits(limits=1)
    _GENERATORS.clear()
    _GENERATORS.update(generators)


def stream(label: str, replication: int, seed: int = SEED) -> np.random.Generator:
    """The random stream of one replication of the generator ``label``."""
    return np.random.default_rng([seed, zlib.crc32(label.encode()), replication])


def simulate(
    generator: Any, label: str, first: int, count: int, shift: float = 0.0, seed: int = SEED
) -> Sums:
    """Replications ``first`` to ``first + count - 1`` of a generator as columns (replication
    by replication, a generator's own columns side by side), under the alternative ``shift``
    (added to every paired difference, or as the generator carries it). ``seed`` is the master
    seed of the streams."""
    parts = [generator.draw(stream(label, first + k, seed), shift) for k in range(count)]
    total = np.concatenate([part[0] for part in parts], axis=1)
    squares = np.concatenate([part[2] for part in parts], axis=1)
    sizes = np.stack([part[1] for part in parts], axis=1)
    same = bool((sizes == sizes[:, :1]).all())
    size = sizes[:, :1] if same else np.repeat(sizes, generator.columns, axis=1)
    return Sums(total, size, squares.sum(axis=0))


def tally(results: Mapping[str, np.ndarray], truth: float) -> dict[str, np.ndarray]:
    """Per procedure: the rejections by side and level (in the order of ``SIDES`` and
    ``LEVELS``), the intervals that cover ``truth``, the summed widths of the bounded intervals,
    and the number of unbounded ones (a bootstrap-t interval is unbounded when more draws than
    its tail have no variance and a mean other than the estimate)."""
    out = {}
    for name, result in results.items():
        rejections = [
            (result[k] < level).sum() for k in range(len(SIDES)) for level in LEVELS.values()
        ]
        low, high = result[3], result[4]
        covered = ((low <= truth) & (truth <= high)).sum()
        width = high - low
        bounded = np.isfinite(width)
        counted = [covered, width[bounded].sum(), np.isinf(width).sum()]
        out[name] = np.array([*rejections, *counted], dtype=float)
    return out


def data_tally(sums: Sums) -> np.ndarray:
    """What the generator produced, summed over the columns: the estimate, its square, and the
    estimated within-episode correlation."""
    delta = sums.delta
    return np.array([delta.sum(), (delta**2).sum(), within_correlation(sums).sum()])


def family_tally(results: Mapping[str, np.ndarray], count: int) -> dict[str, np.ndarray]:
    """Per procedure: the replications in which Holm's rule rejects at least one of the six
    true nulls, and those in which the smallest unadjusted p-value is below 0.05."""
    sides = [0 if SIDED[pair] == 1 else 2 for pair in PAIRS] * 2
    row = np.tile(sides, count)
    out = {}
    for name, result in results.items():
        p = result[row, np.arange(len(row))].reshape(count, len(sides))
        any_holm = (holm(p) < FAMILY_ALPHA).any(axis=1).sum()
        out[name] = np.array([any_holm, (p < FAMILY_ALPHA).any(axis=1).sum()], dtype=float)
    return out


def run_task(task: Task) -> tuple[int, dict[str, np.ndarray]]:
    """The tallies of one block of replications."""
    generator = _GENERATORS[task.generator]
    sums = simulate(generator, task.generator, task.first, task.count, task.shift, task.streams)
    results = procedures(sums, task.draws, task.flips, task.seed)
    if task.family:
        return task.scenario, family_tally(results, task.count)
    return task.scenario, {**tally(results, task.shift), DATA: data_tally(sums)}


def run_tasks(
    tasks: Sequence[Task], generators: Mapping[str, Any], workers: int = 1
) -> dict[int, dict[str, np.ndarray]]:
    """The summed tallies of every scenario. The sums are taken in the order of ``tasks``, so
    the result does not depend on ``workers``."""
    totals: dict[int, dict[str, np.ndarray]] = {}

    def add(scenario: int, counted: Mapping[str, np.ndarray]) -> None:
        mine = totals.setdefault(scenario, {})
        for name, values in counted.items():
            mine[name] = mine.get(name, 0.0) + values

    if workers <= 1:
        _start(generators, worker=False)
        with threadpool_limits(limits=1):
            for task in tasks:
                add(*run_task(task))
        return totals
    with get_context("spawn").Pool(workers, initializer=_start, initargs=(generators,)) as pool:
        for scenario, counted in pool.imap(run_task, tasks, chunksize=1):
            add(scenario, counted)
    return totals


# --------------------------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------------------------

GENERATORS = {
    "empirical": "whole dev episodes of similar size rank; a donor is gone round",
    "empirical_chained": "whole dev episodes of similar size rank; donors are chained",
    "empirical_any_size": "whole dev episodes of any size, gone round (stress case)",
    "empirical_sizes_drawn": "as empirical, with the episode sizes drawn as well (a ratio)",
    "empirical_sparse": "as empirical, all differences zero but in a random 15% of the episodes",
    "copula": "latent random effects, dev marginal, dev within-episode correlation",
    "copula_icc_half": "as copula, half the correlation",
    "copula_icc_double": "as copula, double the correlation",
    "copula_heavy": "as copula, episode effect from a t distribution with 3 degrees of freedom",
    "copula_extremes": "as copula, 2% of the mass at the bound on the side of the longer tail",
}
THINNED_GENERATORS = ("empirical", "copula")
"""The generators run on the thinned structure."""


@dataclass(frozen=True)
class Scenario:
    """A structure, a generator, a pair (or the family of six) and an effect."""

    structure: str
    generator: str
    pair: str
    effect: str
    """``null``, ``plus_mdd`` or ``minus_mdd``; for the family, the dependence of the two
    models; ``other_draws`` for the null under another set of bootstrap draws."""
    shift: float
    replications: int
    family: bool = False
    seed: Seed = SEED

    @property
    def label(self) -> str:
        """The label of the generator that this scenario draws from."""
        tail = f"family_{self.effect}" if self.family else self.pair
        return f"{self.structure}/{self.generator}/{tail}"


@dataclass(frozen=True)
class Calibration:
    """The marginal distributions of one proxy pair and the latent loadings that give each
    random-effects generator its within-episode correlation."""

    plain: Marginal
    extremes: Marginal
    loading: Mapping[str, float]
    """By generator name."""


def calibration(values: np.ndarray, icc: float) -> Calibration:
    """Calibrate every random-effects generator of one pair to the dev correlation ``icc``."""
    plain, extremes = marginal(values), marginal(values, EXTREME_SHARE)
    loading = {
        "copula": calibrate(plain, icc),
        "copula_icc_half": calibrate(plain, icc / 2),
        "copula_icc_double": calibrate(plain, min(2 * icc, 1.0)),
        "copula_heavy": calibrate(plain, icc, heavy=True),
        "copula_extremes": calibrate(extremes, icc),
    }
    return Calibration(plain, extremes, loading)


def pair_generators(
    donors: Donors, sizes: np.ndarray, column: int, fitted: Calibration
) -> dict[str, Any]:
    """Every generator of one proxy pair on one structure, by its name in ``GENERATORS``."""
    one = Donors(donors.values[:, [column]], donors.sizes)
    out: dict[str, Any] = {
        "empirical": empirical(one, sizes),
        "empirical_chained": empirical(one, sizes, chained=True),
        "empirical_any_size": empirical(one, sizes, window=len(donors.sizes)),
        "empirical_sizes_drawn": empirical(one, sizes, sizes_drawn=True),
        "empirical_sparse": empirical(one, sizes, active=SPARSE_SHARE),
    }
    for name, loading in fitted.loading.items():
        base = fitted.extremes if name == "copula_extremes" else fitted.plain
        out[name] = copula(sizes, [base], [loading], heavy=name == "copula_heavy")
    return out


def family_generators(
    donors: Donors, sizes: np.ndarray, fitted: Sequence[Calibration]
) -> dict[tuple[str, str], Any]:
    """The generators of the six tests on one structure, by generator and dependence."""
    marginals = [c.plain for c in fitted] * 2
    loadings = [c.loading["copula"] for c in fitted] * 2
    within = normal_scores(donors.values)
    out: dict[tuple[str, str], Any] = {}
    for dependence in DEPENDENCE:
        name = f"{dependence:g}"
        out["empirical", name] = TwoModels(empirical(donors, sizes), dependence)
        mix = two_model_root(dependence, within)
        out["copula", name] = copula(sizes, marginals, loadings, mix=mix)
    return out


def build_scenarios(
    structures: Mapping[str, np.ndarray],
    donors: Donors,
    pairs: Mapping[str, Mapping[str, Any]],
    detectable: Mapping[str, float],
    replications: Mapping[str, int],
) -> tuple[list[Scenario], dict[str, Any]]:
    """Every scenario of the run and the generators they draw from, by label."""
    scenarios: list[Scenario] = []
    generators: dict[str, Any] = {}
    fitted = [calibration(donors.values[:, k], pairs[pair]["icc"]) for k, pair in enumerate(PAIRS)]
    for structure, sizes in structures.items():
        names = THINNED_GENERATORS if structure == "e3_thinned" else GENERATORS
        for column, pair in enumerate(PAIRS):
            built = pair_generators(donors, sizes, column, fitted[column])
            effects = [("null", 0.0, "null"), ("plus_mdd", detectable[pair], "power")]
            if SIDED[pair] == 2:
                effects.append(("minus_mdd", -detectable[pair], "power"))
            for name in names:
                for effect, shift, kind in effects:
                    scenario = Scenario(structure, name, pair, effect, shift, replications[kind])
                    scenarios.append(scenario)
                    generators[scenario.label] = built[name]
        if structure == "e3_thinned":
            continue
        for (name, dependence), generator in family_generators(donors, sizes, fitted).items():
            scenario = Scenario(
                structure, name, "family", dependence, 0.0, replications["family"], family=True
            )
            scenarios.append(scenario)
            generators[scenario.label] = generator
    first = next(iter(structures))
    for pair in PAIRS:
        scenarios.append(
            Scenario(
                first, "copula", pair, "other_draws", 0.0, replications["null"], seed=(SEED, 1)
            )
        )
    return scenarios, generators


def build_tasks(
    scenarios: Sequence[Scenario], draws: int, flips: int, streams: int = SEED
) -> list[Task]:
    """The blocks of ``CHUNK`` replications of every scenario; ``streams`` is the master seed
    of the replications."""
    tasks = []
    for index, s in enumerate(scenarios):
        step = CHUNK // (2 * len(PAIRS)) if s.family else CHUNK
        for first in range(0, s.replications, step):
            count = min(step, s.replications - first)
            tasks.append(
                Task(index, s.label, s.shift, first, count, draws, flips, s.seed, s.family, streams)
            )
    return tasks


def rate(count: float, replications: int) -> list[float]:
    """A share of the replications and its Monte Carlo standard error."""
    share = count / replications
    return [share, float(np.sqrt(share * (1 - share) / replications))]


def scenario_record(scenario: Scenario, counted: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """The rates of one scenario, per procedure."""
    n = scenario.replications
    head = {
        "structure": scenario.structure,
        "generator": scenario.generator,
        "pair": scenario.pair,
        ("models_dependence" if scenario.family else "effect"): scenario.effect,
        "replications": n,
    }
    if scenario.family:
        rows = {
            name: {
                "holm_familywise_error": rate(c[0], n),
                "any_unadjusted_below_0.05": rate(c[1], n),
            }
            for name, c in counted.items()
        }
        return {**head, "procedures": rows}
    first, second, icc = counted[DATA] / n
    data = {
        "mean_estimate": float(first),
        "sd_of_estimate": float(np.sqrt(max(second - first**2, 0.0))),
        "mean_within_correlation": float(icc),
    }
    rows = {}
    for name in PROCEDURES:
        c = counted[name]
        cells = iter(c[: len(SIDES) * len(LEVELS)])
        rejection = {side: {level: rate(next(cells), n) for level in LEVELS} for side in SIDES}
        covered, widths, unbounded = c[len(SIDES) * len(LEVELS) :]
        rows[name] = {
            "rejection": rejection,
            "coverage95": rate(covered, n),
            "mean_width95": float(widths / (n - unbounded)) if unbounded < n else None,
            "unbounded95": rate(unbounded, n),
        }
        if name in NO_INTERVAL:
            kept = n - c[len(SIDES) * len(LEVELS) - 1] if scenario.shift == 0 else None
            rows[name].update(
                coverage95=None if kept is None else rate(kept, n),
                mean_width95=None,
                unbounded95=None,
            )
    return {**head, "shift": scenario.shift, "data": data, "procedures": rows}


# --------------------------------------------------------------------------------------------
# The report and the command line
# --------------------------------------------------------------------------------------------


def code_record() -> dict[str, str]:
    """The hashes of the code and the versions of the libraries the numbers depend on."""
    files = {"size_check": __file__, "predictors": P.__file__, "power": W.__file__}
    record = {
        f"{name}_sha256": dataset.sha16(Path(path).read_bytes()) for name, path in files.items()
    }
    record.update(numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__)
    return record


def input_record(statements: Path, eligible: Path, power: Path) -> dict[str, str]:
    """The hashes of the three input files and of the code, as the report records them."""
    return {
        "statements_sha256": dataset.sha16(statements.read_bytes()),
        "eligible_e3_sha256": dataset.sha16(eligible.read_bytes()),
        "power_report_sha256": dataset.sha16(power.read_bytes()),
        **code_record(),
    }


def thinning_share(power: Mapping[str, Any], eligible: int) -> tuple[float, str]:
    """The share of the eligible statements kept in the thinned structure, and its basis."""
    test = power["test"]
    if "eligible_statements" in test:
        return test["statements"] / eligible, "the registered scoreable test statements"
    share = power["scoreable_share_of_dated_train_statements"]["dev"]
    return share, "the scoreable share of the dated dev statements"


def generator_record(generators: Mapping[str, Any]) -> dict[str, Any]:
    """What each generator was set to: the centring constant of the whole-episode draws, the
    latent loading of the random-effects draws."""
    out: dict[str, Any] = {}
    for label, generator in generators.items():
        if isinstance(generator, TwoModels):
            generator = generator.one
        if isinstance(generator, Empirical):
            out[label] = {"constant_subtracted": [float(x) for x in generator.centre]}
        elif isinstance(generator, Copula):
            out[label] = {"latent_loading": [float(x) for x in generator.loading]}
    return out


def proxy_pairs() -> list[dict[str, Any]]:
    """The proxy pairs of ``power.py``, as this report and the power report record them."""
    return [
        {"hypothesis": p.hypothesis, "comparator": p.comparator, "tested": p.tested}
        for p in W.PROXY_PAIRS
    ]


def build(
    table: pd.DataFrame,
    eligible: pd.DataFrame,
    power: Mapping[str, Any],
    replications: Mapping[str, int],
    draws: int = DRAWS,
    flips: int = FLIPS,
    workers: int = 1,
    streams: int = SEED,
) -> dict[str, Any]:
    """The report (without its head) from the statement table, the eligible list and the power
    report. ``streams`` is the master seed of the replications."""
    pairs_now = proxy_pairs()
    if power.get("proxy_pairs") != pairs_now:
        raise ValueError("the power report was written for other proxy pairs: rerun power.py")
    frame = P.prepare(table)
    if int(W.dev_rows(frame)["scoreable"].sum()) != power["dev"]["scoreable_statements"]:
        raise ValueError("the statement table and the power report are not from the same build")
    listed = power["test"].get("eligible_statements", power["test"]["statements"])
    if len(eligible) != listed:
        raise ValueError("the eligible list and the power report are not from the same build")
    donors = dev_donors(table, frame)
    share, basis = thinning_share(power, len(eligible))
    structures = {
        "e3": sizes_of(eligible["episode_id"]),
        "dev": donors.sizes,
        "e3_thinned": thinned(eligible, share),
    }
    pairs = pair_record(donors)
    detectable = {h: power["hypotheses"][h]["minimum_detectable_delta"] for h in PAIRS}
    scenarios, generators = build_scenarios(structures, donors, pairs, detectable, replications)
    totals = run_tasks(build_tasks(scenarios, draws, flips, streams), generators, workers)
    records = [scenario_record(s, totals[k]) for k, s in enumerate(scenarios)]
    return {
        "settings": {
            "seed": SEED,
            "replication_seed": streams,
            "bootstrap_draws": draws,
            "sign_flips": flips,
            "replications": dict(replications),
            "columns_per_task": CHUNK,
            "levels": dict(LEVELS),
            "interval_coverage": COVERAGE,
            "donor_window": WINDOW,
            "sparse_share": SPARSE_SHARE,
            "heavy_effect_degrees_of_freedom": HEAVY_DF,
            "extreme_share": EXTREME_SHARE,
        },
        "proxy_pairs": pairs_now,
        "structures": {
            name: {
                **structure_record(sizes),
                **({"share_kept": share, "share_from": basis} if name == "e3_thinned" else {}),
            }
            for name, sizes in structures.items()
        },
        "dev_pairs": pairs,
        "minimum_detectable_delta": detectable,
        "procedures": dict(PROCEDURES),
        "generators": dict(GENERATORS),
        "generator_settings": generator_record(generators),
        "results": [r for r, s in zip(records, scenarios, strict=True) if not s.family],
        "familywise": [r for r, s in zip(records, scenarios, strict=True) if s.family],
    }


def print_summary(report: Mapping[str, Any]) -> None:
    """The size of every procedure at 0.05/6 on the first structure, generator by generator."""
    first = next(iter(report["structures"]))
    print(f"rejection of a true null at 0.05/6 on {first} (registered side), in percent:")
    print(f"  {'generator':24s}{'pair':5s}" + "".join(f"{name[:12]:>13s}" for name in PROCEDURES))
    for record in report["results"]:
        if record["structure"] != first or record["effect"] != "null":
            continue
        side = "upper" if SIDED[record["pair"]] == 1 else "two_sided"
        cells = [record["procedures"][name]["rejection"][side]["0.05/6"][0] for name in PROCEDURES]
        row = "".join(f"{100 * cell:13.2f}" for cell in cells)
        print(f"  {record['generator']:24s}{record['pair']:5s}{row}")
    for record in report["familywise"]:
        cells = [record["procedures"][name]["holm_familywise_error"][0] for name in PROCEDURES]
        row = "".join(f"{100 * cell:13.2f}" for cell in cells)
        head = f"{record['structure']} {record['generator']} {record['models_dependence']}"
        print(f"  Holm, {head:23s}{row}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.size_check", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("--statements", type=Path, default=dataset.STATEMENTS, help="statement table")
    ap.add_argument("--eligible", type=Path, default=dataset.ELIGIBLE, help="the E3 eligible list")
    ap.add_argument("--power", type=Path, default=POWER_REPORT, help="power.json")
    ap.add_argument("--out", type=Path, help=f"the report (default {REPORT}; none with --quick)")
    ap.add_argument("--quick", action="store_true", help="reduced settings; print, write nothing")
    ap.add_argument("--replications", type=int, help="replications of every scenario")
    ap.add_argument("--draws", type=int, help="bootstrap draws and sign flips")
    ap.add_argument("--workers", type=int, default=16, help="worker processes")
    ap.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help=f"master seed of the replications (default {SEED}; draws and signs keep {SEED})",
    )
    args = ap.parse_args(argv)
    out = args.out if args.out or args.quick else REPORT
    for path in (args.statements, args.eligible, args.power, *([out] if out else [])):
        dataset.not_sealed(path)
    started = time.time()
    replications = {kind: QUICK[kind] if args.quick else n for kind, n in REPLICATIONS.items()}
    if args.replications:
        replications = dict.fromkeys(replications, args.replications)
    draws = args.draws or (QUICK["draws"] if args.quick else DRAWS)
    flips = args.draws or (QUICK["flips"] if args.quick else FLIPS)
    inputs = input_record(args.statements, args.eligible, args.power)
    power = json.loads(args.power.read_text(encoding="utf-8"))
    report = build(
        dataset.load_statements(args.statements),
        dataset.read_table(args.eligible),
        power,
        replications,
        draws,
        flips,
        args.workers,
        args.seed,
    )
    if input_record(args.statements, args.eligible, args.power) != inputs:
        raise SystemExit("an input or the code changed during the run: run the command again")
    options = (" --quick" if args.quick else "") + (
        f" --seed {args.seed}" if args.seed != SEED else ""
    )
    head = {
        "about": (
            "Size, power and interval coverage of candidate test procedures for the "
            "confirmatory contrasts (PLAN.md section 6), by simulation at the episode structure "
            "of the E3 eligible list and of the scoreable dev statements. Train-period data only."
        ),
        "command": COMMAND + options,
        "inputs": inputs,
    }
    run = {"runtime_seconds": round(time.time() - started, 1), "workers": args.workers}
    print_summary(report)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(W.report_text({**head, **report, "run": run}), encoding="utf-8")
        print(f"wrote {out.as_posix()}")
    print(f"runtime {run['runtime_seconds']} s with {args.workers} workers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
