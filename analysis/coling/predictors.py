"""Model-free predictors of recovery, the censoring module and the scores (PLAN.md sections 7.2
and 8; DECISIONS.md 12).

Input. The statement table of ``dataset.py`` (``out/statements.csv.gz``), whose outcome columns
are blank on every statement dated 2023-01-01 or later. ``prepare`` turns it into a typed frame:
one row per statement at risk under definition B in the analysis sets ``dated``, ``stale``,
``tbd`` and ``silent``, with times in days from the statement date. Every fitting function goes
through ``fitting_rows``, which refuses a row outside the train period or a row with no outcome,
so no test-period outcome can enter a fit. Predicting needs first-sight columns only.

What a predictor returns (``PREDICTION_COLUMNS``): ``p_a`` and ``p_b``, the probabilities of
recovery by horizon A and by horizon B (the stated end and 90 days later for a dated statement:
``P(E_end)`` and ``P(E_end90)``; 90 and 180 days after the statement for ``tbd`` and
``silent``), and ``q10``, ``q50``, ``q80``, ``q90``, ``q95``, quantiles of the days from the
statement date to recovery, kept within 0 to 365.

Censoring module (``turnbull``). The non-parametric maximum-likelihood estimate of a
distribution from interval-censored observations ``(left, right]``, with ``right`` infinite for
a right-censored one (Turnbull 1976).

* The mass can sit only on the *innermost intervals*: ``(a, b]`` with ``a`` a left endpoint,
  ``b`` a right endpoint and no endpoint between them. They are found by sorting all endpoints
  (a right endpoint before a left one of the same value, because the intervals are half-open).
* The masses are found by the self-consistency (EM) iteration from equal masses. It stops when
  the largest derivative of the mean log-likelihood with respect to a mass exceeds 1 by at most
  ``TOLERANCE`` (at the maximum every derivative is at most 1), and fails if that takes more
  than ``MAX_ITERATIONS`` steps.
* Reading the estimate. Inside an innermost interval the likelihood does not say where the mass
  lies. ``cdf`` spreads it evenly over the interval (``how="mid"``, the rule used by every
  predictor; the plan scores an interval-censored target at its midpoint in the same way), or
  puts it at the right end (``"lower"``) or just after the left end (``"upper"``), which bound
  the curve. Mass on an interval with no finite right end is recovery after the last time the
  data can see, or never: no finite time reaches it, and a quantile above the reached mass is
  infinite (a predictor then reports the cap).
* A discontinued statement never recovers (PLAN 2.5: no at every horizon, the cap as its time):
  its bracket is ``(NEVER, inf)``.
* No correction for delayed entry: a statement is first seen at the first capture after its
  date, so every curve is conditional on the shortage having lasted to first sight (PLAN 2.5).

Predictors (each object has ``predict(frame)``).

* ``fit_base_rate``: the base-rate remaining duration by listing age. A Turnbull curve of the
  time to recovery for each listing-age bin (``AGE_EDGES`` in days since the Initial Posting
  Date, plus a bin for an unknown posting date), fitted on the at-risk statements of the sets
  ``dated``, ``tbd`` and ``silent``. A bin with fewer than ``MIN_CELL`` fitting statements uses
  the curve of all bins together. The probabilities are the bin's curve read at the two
  horizons; the quantiles are the bin's, capped.
* ``FaceValue``: the stated date at face value. Both probabilities are 1 and every quantile is
  the stated end minus the statement date. It has no output for a statement with no stated end.
* ``fit_calibrator``: the empirical slip calibrator. Slip is recovery minus the stated end, in
  days; its bracket is the recovery bracket shifted by the stated end. One Turnbull curve of
  slip per *cell* (merged form class by revision bucket), per form and over all dated forms,
  from the ``dated`` fitting statements. A statement uses the smallest of the three that holds
  at least ``MIN_CELL`` fitting statements (DECISIONS 12). Given a reading whose period ends
  ``r`` days after the statement date, the probability of recovery by a horizon ``h`` days after
  it is ``F_slip(h - r)``, and each quantile is ``r`` plus the slip quantile, kept within 0 to
  365. With no reading (ABSTAIN) the calibrator falls back to the no-date table: the listing-age
  table fitted on the ``tbd`` and ``silent`` fitting statements.
* Rules plus slip is the calibrator on the frozen rule reading: ``predict(frame)`` with no
  reading given takes ``r`` from ``stated_end``, so ``P(E_end) = F_slip(0)`` and ``P(E_end90) =
  F_slip(90)``. A language model's literal reading (condition c) is passed as ``reading_days``.
* ``SlipCalibrator.table`` lists every cell with its basis, the number of statements the row
  rests on, the two Turnbull shares and the Turnbull median of the days to recovery, which is
  what the track-record table of the prompts shows. ``backoff_cells`` and ``backoff_bins`` give
  the basis of every cell and listing-age bin from the counts alone, without fitting.

The gradient-boosted predictors are in ``gbm.py``, which also fits all five together
(``gbm.fit_all``).

Scores (PLAN 7.2).

* ``primary_loss``: ``(BS(E_end) + BS(E_end90)) / 2`` with ``BS = (p - y)^2``, defined on a
  scoreable statement (both horizon events determined) and missing otherwise.
* ``brier_bounds``: the mean of the same loss over every statement, with each undetermined
  horizon event set to no, and then to yes.
* ``pinball_scores``: the pinball loss of a quantile against the capped time to recovery. An
  interval-censored target is scored at the midpoint of its bracket; a target known to be at
  the cap is scored at the cap; a target right-censored before the cap is left out and counted.
  The bounds are the means of the smallest and of the largest loss over each bracket (for a
  right-censored target, from its lower bound to the cap) and include every statement.

Resampling (PLAN section 6). ``bootstrap_means`` is the paired cluster bootstrap by shortage
episode: each draw resamples the episodes with replacement (the same draw for every predictor)
and takes each predictor's mean loss over the statements drawn. ``interval`` gives percentile
intervals and ``p_values`` the one-sided and two-sided p-values of a contrast, as section 6
defines them. 10,000 draws, seed 20261001.

This module has no command. ``power.py`` fits the predictors on the fit split, scores them on
dev and writes ``out/dev_losses.json``::

    PYTHONPATH=. python -m analysis.coling.power
    PYTHONPATH=. python -m pytest analysis/coling/test_predictors.py -q -p no:cacheprovider
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analysis.coling import dataset

SEED = 20261001
DRAWS = 10_000
CAP_DAYS = dataset.CAP_DAYS
MIN_CELL = 100
"""The smallest number of fitting statements a cell, a form or a listing-age bin needs for an
estimate of its own (DECISIONS 12)."""
NEVER = 1e9
"""Left end, in days, of the bracket of a statement that never recovers (a discontinuation)."""
TOLERANCE = 1e-8
MAX_ITERATIONS = 1_000_000
QUANTILE_LEVELS = (0.10, 0.50, 0.80, 0.90, 0.95)
QUANTILE_KEYS = ("q10", "q50", "q80", "q90", "q95")
PREDICTION_COLUMNS = ("p_a", "p_b", *QUANTILE_KEYS)
PINBALL_LEVELS = (0.50, 0.80, 0.95)
SETS = ("dated", "stale", "tbd", "silent")
"""Analysis sets that have horizons, and so predictions."""
BASE_RATE_SETS = ("dated", "tbd", "silent")
NO_DATE_SETS = ("tbd", "silent")
REVISIONS = dataset.REVISION_BUCKETS
BASES = ("cell", "form", "all dated forms")
AGE_EDGES = (0, 90, 365, 730, 1095, 1825)
"""Lower edges of the listing-age bins, in days since the Initial Posting Date."""
AGE_LABELS = (
    "under 90 days",
    "90 days to under 1 year",
    "1 to under 2 years",
    "2 to under 3 years",
    "3 to under 5 years",
    "5 years or more",
)
AGE_UNKNOWN = "posting date unknown"
ALL_AGES = "all listing ages"
FRAME_COLUMNS = (
    "episode_id",
    "period",
    "split",
    "analysis_set",
    "form",
    "revision",
    "month",
    "end_days",
    "h_a",
    "h_b",
    "age",
    "reason",
    "category",
    "company",
    "text",
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
OUTCOMES = ("recovered", "censored", "discontinued")
TTR_KINDS = ("interval", "at_cap", "right_censored")


# --------------------------------------------------------------------------------------------
# The typed frame
# --------------------------------------------------------------------------------------------


def _days(later: pd.Series, earlier: pd.Series) -> pd.Series:
    """Whole days between two columns of ISO dates; missing where either cell is blank."""
    a = pd.to_datetime(later.where(later != ""), format="%Y-%m-%d")
    b = pd.to_datetime(earlier.where(earlier != ""), format="%Y-%m-%d")
    return (a - b).dt.days.astype(float)


def _number(column: pd.Series) -> pd.Series:
    """A text column of numbers as floats; missing where the cell is blank."""
    return pd.to_numeric(column.where(column != ""), errors="raise").astype(float)


def _event(column: pd.Series) -> pd.Series:
    """A horizon event as 1 (yes), 0 (no) or missing (undetermined, or not set)."""
    return column.map({"yes": 1.0, "no": 0.0}).astype(float)


def prepare(table: pd.DataFrame) -> pd.DataFrame:
    """The statement table as the typed frame the predictors use, indexed by
    ``statement_group_id`` and sorted by it.

    Rows: statements at risk under B in the sets of ``SETS``. First-sight columns: episode,
    period, split, set, merged form class (``form``), revision bucket, calendar month, the
    stated end and the two horizons in days from the statement date (``end_days``, ``h_a``,
    ``h_b``), listing age in days (``age``), reason, therapeutic category, company and the two
    notice fields joined (``text``). Outcome columns, filled only where the table has them (the
    train period): the outcome kind, the bracket in days (``lower_days``, ``upper_days``), the
    two horizon events as 1, 0 or missing (``y_a``, ``y_b``), ``scoreable``, and the capped
    time-to-recovery target (``ttr_kind``, ``ttr_lower``, ``ttr_upper``, ``ttr_mid``).
    """
    dataset.assert_sealed(table)
    rows = table[dataset.true(table["at_risk_B"]) & table["analysis_set"].isin(SETS)]
    rows = rows.sort_values("statement_group_id").set_index("statement_group_id")
    day = rows["event_date"]
    dated = rows["analysis_set"] == "dated"
    y_a = _event(rows["E_end"]).where(dated, _event(rows["E_90"]))
    y_b = _event(rows["E_end90"]).where(dated, _event(rows["E_180"]))
    frame = pd.DataFrame(
        {
            "episode_id": rows["episode_id"],
            "period": rows["period"],
            "split": rows["split"],
            "analysis_set": rows["analysis_set"],
            "form": rows["merged_form"],
            "revision": rows["revision"],
            "month": pd.to_datetime(day, format="%Y-%m-%d").dt.month,
            "end_days": _days(rows["stated_end"], day),
            "h_a": _days(rows["horizon_a"], day),
            "h_b": _days(rows["horizon_b"], day),
            "age": _number(rows["listing_age_days"]),
            "reason": rows["reason_for_shortage"],
            "category": rows["therapeutic_category"],
            "company": rows["company_name"],
            "text": (rows["availability_text"] + " " + rows["related_text"]).str.strip(),
            "outcome": rows["outcome"],
            "lower_days": _number(rows["lower_days"]),
            "upper_days": _number(rows["upper_days"]),
            "y_a": y_a,
            "y_b": y_b,
            "scoreable": y_a.notna() & y_b.notna(),
            "ttr_kind": rows["ttr_kind"],
            "ttr_lower": _number(rows["ttr_lower_days"]),
            "ttr_upper": _number(rows["ttr_upper_days"]),
            "ttr_mid": _number(rows["ttr_mid_days"]),
        },
        columns=list(FRAME_COLUMNS),
    )
    if frame[["h_a", "h_b"]].isna().any().any():
        raise ValueError("a statement of the analysis sets has no horizon")
    return frame


def load(path: Path = dataset.STATEMENTS) -> pd.DataFrame:
    """The typed frame of the statement table on disk."""
    return prepare(dataset.load_statements(dataset.not_sealed(path)))


def fitting_rows(frame: pd.DataFrame, sets: Sequence[str] = SETS) -> pd.DataFrame:
    """The rows of ``frame`` in ``sets`` that a component is fitted on. Stops unless every row
    is a train-period statement with an outcome: nothing dated 2023-01-01 or later is fitted on.
    """
    rows = frame[frame["analysis_set"].isin(sets)]
    if (rows["period"] != "train").any():
        raise ValueError("a component is fitted on train-period statements only")
    if not rows["outcome"].isin(OUTCOMES).all() or not rows["ttr_kind"].isin(TTR_KINDS).all():
        raise ValueError("a fitting statement has no outcome")
    return rows


# --------------------------------------------------------------------------------------------
# Scores (PLAN 7.2)
# --------------------------------------------------------------------------------------------


def brier(p: Any, y: Any) -> np.ndarray:
    """``(p - y)^2``; missing where the event ``y`` is undetermined."""
    return (np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2


def primary_loss(p_a: Any, p_b: Any, y_a: Any, y_b: Any) -> np.ndarray:
    """The primary Brier loss of each statement: the mean of the Brier scores of its two
    horizon events. Missing unless both events are determined (the statement is scoreable)."""
    return (brier(p_a, y_a) + brier(p_b, y_b)) / 2


def brier_bounds(p_a: Any, p_b: Any, y_a: Any, y_b: Any) -> dict[str, float]:
    """The mean primary loss over every statement with each undetermined horizon event set to
    no (0), and then to yes (1)."""
    out = {}
    for name, value in (("undetermined_as_no", 0.0), ("undetermined_as_yes", 1.0)):
        a = np.where(np.isnan(np.asarray(y_a, dtype=float)), value, y_a)
        b = np.where(np.isnan(np.asarray(y_b, dtype=float)), value, y_b)
        out[name] = float(np.mean(primary_loss(p_a, p_b, a, b)))
    return out


def pinball(q: Any, y: Any, level: float) -> np.ndarray:
    """The pinball loss of the quantile ``q`` at ``level`` against the value ``y``."""
    q, y = np.asarray(q, dtype=float), np.asarray(y, dtype=float)
    return np.where(y >= q, level * (y - q), (1 - level) * (q - y))


def pinball_scores(q: Any, frame: pd.DataFrame, level: float) -> dict[str, float | int | None]:
    """The pinball loss of the quantiles ``q`` (one per row of ``frame``) against the capped
    time to recovery, with its bounds (see the module docstring). ``loss`` is None when every
    target is right-censored before the cap."""
    q = np.asarray(q, dtype=float)
    kind = frame["ttr_kind"].to_numpy()
    if not np.isin(kind, TTR_KINDS).all():
        raise ValueError("a statement has no time-to-recovery target")
    censored = kind == "right_censored"
    low = frame["ttr_lower"].to_numpy(dtype=float)
    high = np.where(censored, float(CAP_DAYS), frame["ttr_upper"].to_numpy(dtype=float))
    ends = np.stack([pinball(q, low, level), pinball(q, high, level)])
    smallest = np.where((low <= q) & (q <= high), 0.0, ends.min(axis=0))
    scored = pinball(q[~censored], frame["ttr_mid"].to_numpy(dtype=float)[~censored], level)
    return {
        "loss": float(scored.mean()) if len(scored) else None,
        "statements": int((~censored).sum()),
        "left_out_right_censored": int(censored.sum()),
        "lower_bound": float(smallest.mean()),
        "upper_bound": float(ends.max(axis=0).mean()),
    }


# --------------------------------------------------------------------------------------------
# Censoring: the Turnbull estimate
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Turnbull:
    """A Turnbull estimate: ``mass[j]`` on the innermost interval ``(left[j], right[j]]``."""

    left: np.ndarray
    right: np.ndarray
    mass: np.ndarray
    n: int
    iterations: int
    gap: float
    """How far the largest likelihood derivative was above 1 when the iteration stopped."""

    @property
    def reached(self) -> float:
        """The mass on intervals with a finite right end: the highest value ``cdf`` takes."""
        return float(self.mass[np.isfinite(self.right)].sum())

    def _knots(self) -> tuple[np.ndarray, np.ndarray]:
        """The corners of the curve that spreads each finite interval's mass evenly."""
        finite = np.isfinite(self.right)
        cum = np.cumsum(self.mass[finite])
        before = np.concatenate([[0.0], cum])[:-1]
        x = np.column_stack([self.left[finite], self.right[finite]]).ravel()
        y = np.column_stack([before, cum]).ravel()
        keep = np.concatenate([[True], np.diff(x) > 0]) if len(x) else np.zeros(0, dtype=bool)
        return x[keep], y[keep]

    def cdf(self, t: Any, how: str = "mid") -> np.ndarray:
        """The estimated probability of a value at or below ``t`` (see the module docstring for
        ``how``: ``mid``, ``lower`` or ``upper``)."""
        t = np.asarray(t, dtype=float)
        finite = np.isfinite(self.right)
        cum = np.concatenate([[0.0], np.cumsum(self.mass[finite])])
        if how == "lower":
            return cum[np.searchsorted(self.right[finite], t, side="right")]
        if how == "upper":
            return cum[np.searchsorted(self.left[finite], t, side="left")]
        if how != "mid":
            raise ValueError(f"unknown rule {how!r}")
        x, y = self._knots()
        if not len(x):
            return np.zeros(t.shape)
        return np.interp(t, x, y, left=0.0, right=y[-1])

    def quantile(self, level: Any) -> np.ndarray:
        """The smallest value whose ``cdf`` (``mid``) is at least ``level``; infinite when the
        curve does not reach ``level``."""
        level = np.asarray(level, dtype=float)
        x, y = self._knots()
        out = np.full(level.shape, np.inf)
        if not len(x):
            return out
        k = np.searchsorted(y, level, side="left")
        first, inside = k == 0, (k > 0) & (k < len(y))
        out[first] = x[0]
        j = k[inside]
        share = (level[inside] - y[j - 1]) / (y[j] - y[j - 1])
        out[inside] = x[j - 1] + share * (x[j] - x[j - 1])
        return out

    def conditional_quantile(self, level: Any, after: Any) -> np.ndarray:
        """The quantile at ``level`` of the estimate given a value above ``after`` (the
        conditional tail beyond a censoring time); infinite where the tail has no finite part
        that far."""
        below = self.cdf(after)
        return self.quantile(below + np.asarray(level, dtype=float) * (1.0 - below))


def innermost(left: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The innermost intervals of the observations ``(left, right]``: a left endpoint followed
    directly by a right endpoint when all endpoints are sorted (right before left at a tie)."""
    lows, highs = np.unique(left), np.unique(right)
    values = np.concatenate([highs, lows])
    is_left = np.concatenate([np.zeros(len(highs), dtype=bool), np.ones(len(lows), dtype=bool)])
    order = np.lexsort((is_left, values))
    values, is_left = values[order], is_left[order]
    k = np.flatnonzero(is_left[:-1] & ~is_left[1:])
    return values[k], values[k + 1]


def turnbull(
    left: Any, right: Any, tolerance: float = TOLERANCE, max_iterations: int = MAX_ITERATIONS
) -> Turnbull:
    """The Turnbull estimate from observations known to lie in ``(left[i], right[i]]``;
    ``right[i]`` is infinite for a right-censored observation."""
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    n = len(left)
    if n == 0 or len(right) != n:
        raise ValueError("no observation, or bounds of different lengths")
    if np.isnan(left).any() or np.isnan(right).any() or (left >= right).any():
        raise ValueError("every observation needs left < right")
    a, b = innermost(left, right)
    m = len(a)
    # Each observation covers a run of consecutive innermost intervals: first[i] to last[i].
    first = np.searchsorted(a, left, side="left")
    last = np.searchsorted(b, right, side="right") - 1
    mass = np.full(m, 1.0 / m)
    for step in range(1, max_iterations + 1):
        cum = np.concatenate([[0.0], np.cumsum(mass)])
        inverse = 1.0 / np.maximum(cum[last + 1] - cum[first], np.finfo(float).tiny)
        change = np.bincount(first, weights=inverse, minlength=m + 1)
        change -= np.bincount(last + 1, weights=inverse, minlength=m + 1)
        derivative = np.cumsum(change[:m]) / n
        gap = float(derivative.max() - 1.0)
        mass = mass * derivative
        if gap <= tolerance:
            mass = mass / mass.sum()
            return Turnbull(a, b, mass, n, step, gap)
    raise RuntimeError(f"the Turnbull iteration did not converge in {max_iterations} steps")


def ttr_brackets(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The bracket of the days from the statement date to recovery, per row: ``(lower_days,
    upper_days]`` when recovered, ``(lower_days, inf)`` when censored, ``(NEVER, inf)`` when
    discontinued."""
    kind = rows["outcome"].to_numpy()
    left = np.where(kind == "discontinued", NEVER, rows["lower_days"].to_numpy(dtype=float))
    right = np.where(kind == "recovered", rows["upper_days"].to_numpy(dtype=float), np.inf)
    return left, right


def slip_brackets(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """The bracket of slip (recovery minus the stated end, in days) per row of dated
    statements."""
    left, right = ttr_brackets(rows)
    end = rows["end_days"].to_numpy(dtype=float)
    if np.isnan(end).any():
        raise ValueError("slip needs a stated end on every row")
    return np.where(left == NEVER, NEVER, left - end), right - end


# --------------------------------------------------------------------------------------------
# Predictors
# --------------------------------------------------------------------------------------------


def _capped(days: Any) -> np.ndarray:
    """Days kept within 0 to the cap (an infinite quantile becomes the cap)."""
    return np.clip(np.asarray(days, dtype=float), 0.0, float(CAP_DAYS))


def _blank(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(np.nan, index=frame.index, columns=list(PREDICTION_COLUMNS))


def age_bin(age: Any) -> np.ndarray:
    """The listing-age bin of each age in days (``AGE_LABELS``); ``AGE_UNKNOWN`` when missing."""
    age = np.asarray(age, dtype=float)
    k = np.searchsorted(np.asarray(AGE_EDGES[1:], dtype=float), np.nan_to_num(age), side="right")
    return np.where(np.isnan(age), AGE_UNKNOWN, np.asarray(AGE_LABELS)[k])


@dataclass(frozen=True)
class AgeTable:
    """Turnbull curves of the time to recovery by listing-age bin, with the pooled curve for a
    bin that holds fewer than ``min_cell`` fitting statements."""

    curves: Mapping[str, Turnbull]
    """The bins with a curve of their own, and ``ALL_AGES``."""
    counts: Mapping[str, int]
    """Fitting statements per bin."""
    min_cell: int = MIN_CELL

    def curve(self, label: str) -> Turnbull:
        return self.curves.get(label, self.curves[ALL_AGES])

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = _blank(frame)
        bins = age_bin(frame["age"])
        for label in sorted(set(bins)):
            rows, curve = bins == label, self.curve(label)
            out.loc[rows, "p_a"] = curve.cdf(frame.loc[rows, "h_a"])
            out.loc[rows, "p_b"] = curve.cdf(frame.loc[rows, "h_b"])
            out.loc[rows, list(QUANTILE_KEYS)] = _capped(curve.quantile(QUANTILE_LEVELS))
        return out

    def table(self) -> list[dict[str, Any]]:
        """One row per bin: its fitting statements and whether it has a curve of its own."""
        return [
            {
                "listing_age": label,
                "statements": int(self.counts.get(label, 0)),
                "basis": "bin" if label in self.curves else ALL_AGES,
            }
            for label in (*AGE_LABELS, AGE_UNKNOWN)
        ]


def fit_age_table(
    frame: pd.DataFrame, sets: Sequence[str] = BASE_RATE_SETS, min_cell: int = MIN_CELL
) -> AgeTable:
    """The listing-age table of the time to recovery from the fitting statements of ``sets``."""
    rows = fitting_rows(frame, sets)
    if not len(rows):
        raise ValueError(f"no fitting statement in {tuple(sets)}")
    bins = age_bin(rows["age"])
    curves = {ALL_AGES: turnbull(*ttr_brackets(rows))}
    counts = {label: int((bins == label).sum()) for label in (*AGE_LABELS, AGE_UNKNOWN)}
    for label, count in counts.items():
        if count >= min_cell:
            curves[label] = turnbull(*ttr_brackets(rows[bins == label]))
    return AgeTable(curves, counts, min_cell)


def fit_base_rate(frame: pd.DataFrame, min_cell: int = MIN_CELL) -> AgeTable:
    """The base-rate predictor: remaining duration by listing age (PLAN section 8)."""
    return fit_age_table(frame, BASE_RATE_SETS, min_cell)


@dataclass(frozen=True)
class FaceValue:
    """The stated date at face value: recovery by the stated end is certain."""

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = _blank(frame)
        stated = frame["end_days"].notna()
        out.loc[stated, ["p_a", "p_b"]] = 1.0
        for key in QUANTILE_KEYS:
            out.loc[stated, key] = _capped(frame.loc[stated, "end_days"])
        return out


@dataclass(frozen=True)
class Estimate:
    """The Turnbull curves of one group of dated fitting statements."""

    statements: int
    slip: Turnbull
    ttr: Turnbull


def _estimate(rows: pd.DataFrame) -> Estimate:
    return Estimate(len(rows), turnbull(*slip_brackets(rows)), turnbull(*ttr_brackets(rows)))


@dataclass(frozen=True)
class SlipCalibrator:
    """The empirical slip calibrator: slip curves by cell, by form and over all dated forms,
    with the no-date table for a reading that abstains."""

    cells: Mapping[tuple[str, str], Estimate]
    forms: Mapping[str, Estimate]
    pooled: Estimate
    cell_counts: Mapping[tuple[str, str], int]
    no_date: AgeTable
    min_cell: int = MIN_CELL

    def basis(self, form: str, revision: str) -> tuple[str, Estimate]:
        """The estimate a statement of this form and revision bucket uses, and its basis: the
        smallest of cell, form and all dated forms with at least ``min_cell`` statements."""
        if (form, revision) in self.cells:
            return "cell", self.cells[(form, revision)]
        if form in self.forms:
            return "form", self.forms[form]
        return "all dated forms", self.pooled

    def predict(self, frame: pd.DataFrame, reading_days: pd.Series | None = None) -> pd.DataFrame:
        """Predictions from a literal reading whose period ends ``reading_days`` after the
        statement date (missing for ABSTAIN). With no reading given, the frozen rule reading
        (``end_days``) is used: rules plus slip."""
        reading = frame["end_days"] if reading_days is None else reading_days.reindex(frame.index)
        reading = reading.astype(float)
        read = reading.notna().to_numpy()
        out = _blank(frame)
        if (~read).any():
            out.loc[~read] = self.no_date.predict(frame.loc[~read]).to_numpy()
        form_of, revision_of = frame["form"].to_numpy(), frame["revision"].to_numpy()
        for form, revision in sorted(set(zip(form_of[read], revision_of[read], strict=True))):
            rows = read & (form_of == form) & (revision_of == revision)
            slip = self.basis(form, revision)[1].slip
            r = reading[rows].to_numpy()
            out.loc[rows, "p_a"] = slip.cdf(frame.loc[rows, "h_a"].to_numpy() - r)
            out.loc[rows, "p_b"] = slip.cdf(frame.loc[rows, "h_b"].to_numpy() - r)
            quantiles = r[:, None] + slip.quantile(QUANTILE_LEVELS)[None, :]
            out.loc[rows, list(QUANTILE_KEYS)] = _capped(quantiles)
        return out

    def table(self) -> list[dict[str, Any]]:
        """One row per form class and revision bucket of the fitting statements: the cell's own
        count, the basis, the number of statements the estimate rests on, the Turnbull shares
        recovered by the stated end and by 90 days after it, and the Turnbull median of the
        days from the statement to recovery (None when half have not recovered within reach)."""
        rows = []
        for form in sorted({form for form, _ in self.cell_counts}):
            for revision in REVISIONS:
                basis, estimate = self.basis(form, revision)
                median = float(estimate.ttr.quantile(0.5))
                rows.append(
                    {
                        "form": form,
                        "revision": revision,
                        "cell_statements": int(self.cell_counts.get((form, revision), 0)),
                        "basis": basis,
                        "statements": estimate.statements,
                        "share_by_stated_end": float(estimate.slip.cdf(0.0)),
                        "share_by_stated_end_90": float(estimate.slip.cdf(90.0)),
                        "median_days_to_recovery": median if np.isfinite(median) else None,
                    }
                )
        return rows


def fit_calibrator(frame: pd.DataFrame, min_cell: int = MIN_CELL) -> SlipCalibrator:
    """The slip calibrator from the ``dated`` fitting statements of ``frame``, and its no-date
    table from the ``tbd`` and ``silent`` ones."""
    rows = fitting_rows(frame, ("dated",))
    if not len(rows):
        raise ValueError("no dated fitting statement")
    cell_counts = {key: len(group) for key, group in rows.groupby(["form", "revision"])}
    cells = {
        key: _estimate(group)
        for key, group in rows.groupby(["form", "revision"])
        if len(group) >= min_cell
    }
    by_form = {
        form: _estimate(group) for form, group in rows.groupby("form") if len(group) >= min_cell
    }
    no_date = fit_age_table(frame, NO_DATE_SETS, min_cell)
    return SlipCalibrator(cells, by_form, _estimate(rows), cell_counts, no_date, min_cell)


def backoff_cells(frame: pd.DataFrame, min_cell: int = MIN_CELL) -> list[dict[str, Any]]:
    """Which estimate each cell would use if the calibrator were fitted on ``frame``, from the
    counts of its dated fitting statements alone (nothing is fitted). The rows agree with
    ``SlipCalibrator.table`` on every key they hold."""
    rows = fitting_rows(frame, ("dated",))
    by_form = rows.groupby("form").size()
    by_cell = rows.groupby(["form", "revision"]).size()
    out = []
    for form in sorted(by_form.index):
        for revision in REVISIONS:
            cell = int(by_cell.get((form, revision), 0))
            rests_on = {"cell": cell, "form": int(by_form[form]), "all dated forms": len(rows)}
            basis = next((b for b in BASES[:2] if rests_on[b] >= min_cell), BASES[2])
            out.append(
                {
                    "form": form,
                    "revision": revision,
                    "cell_statements": cell,
                    "basis": basis,
                    "statements": rests_on[basis],
                }
            )
    return out


def backoff_bins(
    frame: pd.DataFrame, sets: Sequence[str] = BASE_RATE_SETS, min_cell: int = MIN_CELL
) -> list[dict[str, Any]]:
    """Which listing-age bins would have a curve of their own if the table were fitted on the
    statements of ``sets`` in ``frame``, from their counts alone. The rows are those of
    ``AgeTable.table``."""
    bins = pd.Series(age_bin(fitting_rows(frame, sets)["age"])).value_counts()
    return [
        {
            "listing_age": label,
            "statements": int(bins.get(label, 0)),
            "basis": "bin" if bins.get(label, 0) >= min_cell else ALL_AGES,
        }
        for label in (*AGE_LABELS, AGE_UNKNOWN)
    ]


# --------------------------------------------------------------------------------------------
# Resampling: the paired cluster bootstrap (PLAN section 6)
# --------------------------------------------------------------------------------------------


def cluster_draws(clusters: int, draws: int = DRAWS, seed: int = SEED) -> np.ndarray:
    """``draws`` resamples of ``clusters`` clusters with replacement, as the number of times
    each cluster is taken (one row per draw)."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(clusters, np.full(clusters, 1.0 / clusters), size=draws)


def cluster_sums(values: Any, clusters: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """Per cluster, in the order of the sorted cluster ids: the sum of each column of
    ``values`` (statements by predictors) and the number of statements. Stops at a missing or
    blank cluster id: statements with no episode would otherwise be resampled as one cluster."""
    values = np.asarray(values, dtype=float)
    values = values[:, None] if values.ndim == 1 else values
    if np.isnan(values).any():
        raise ValueError("a loss is missing: score the same statements for every predictor")
    ids = list(clusters)
    codes = pd.Categorical(ids).codes
    if (codes < 0).any() or "" in ids:
        raise ValueError("a statement has no cluster")
    sizes = np.bincount(codes).astype(float)
    sums = np.stack(
        [np.bincount(codes, weights=column, minlength=len(sizes)) for column in values.T], axis=1
    )
    return sums, sizes


def bootstrap_means(
    values: Any, clusters: Sequence[str], draws: int = DRAWS, seed: int = SEED
) -> np.ndarray:
    """The mean of each column of ``values`` in each bootstrap draw of the clusters (draws by
    columns). Every column is computed on the same draws, so differences of columns are paired.
    """
    sums, sizes = cluster_sums(values, clusters)
    taken = cluster_draws(len(sizes), draws, seed).astype(float)
    return (taken @ sums) / (taken @ sizes)[:, None]


def interval(draws: Any, coverage: float = 0.95) -> list[float]:
    """The percentile interval of a bootstrap distribution."""
    tail = (1.0 - coverage) / 2
    low, high = np.quantile(np.asarray(draws, dtype=float), [tail, 1.0 - tail])
    return [float(low), float(high)]


def p_values(delta_draws: Any) -> dict[str, float]:
    """The p-values of a contrast from its bootstrap distribution (PLAN section 6): one-sided
    for ``delta > 0`` and two-sided."""
    delta = np.asarray(delta_draws, dtype=float)
    below = (1 + int((delta <= 0).sum())) / (len(delta) + 1)
    above = (1 + int((delta >= 0).sum())) / (len(delta) + 1)
    return {"one_sided": float(below), "two_sided": float(min(1.0, 2 * min(below, above)))}
