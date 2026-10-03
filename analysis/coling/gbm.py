"""Gradient-boosted quantile predictors of the time to recovery: the structured-only model (a
registered secondary of H3) and the text-trained model (PLAN.md section 8; DECISIONS.md 16).

Both models predict the quantiles 0.05, 0.10, ..., 0.95 of the days from the statement date to
recovery, capped at 365, with one scikit-learn ``HistGradientBoostingRegressor`` per quantile
(pinball loss, the fixed settings of ``PARAMS``, seed 20261001; nothing is tuned).

Fitting statements. The train-period statements at risk under B in the sets ``dated``, ``tbd``
and ``silent`` that are passed in (the fit split for the dev runs, fit and dev for the test
runs). ``predictors.fitting_rows`` refuses anything else.

Features.

* Structured (both models): reason for shortage, therapeutic category and company, each as one
  category per value after lower-casing and collapsing spaces, where a value seen on fewer than
  ``MIN_CATEGORY`` fitting statements (or not seen) is the category "other"; the calendar month
  of the statement date, as a category; and the days since the Initial Posting Date, as a
  number (missing when the posting date is unknown). Status is not a feature (constant on
  at-risk statements), and no free text enters the structured-only model.
* Text (the text-trained model only): TF-IDF of the Availability Information and the Related
  Information joined, with the settings of ``TFIDF``; the vocabulary and the document
  frequencies come from the fitting statements alone.

Targets (censoring in fitting). The target is the capped time to recovery of ``dataset.py``.

* An interval-censored statement is given the midpoint of its capped bracket.
* A statement known to be at the cap (not recovered 365 days after its date, or discontinued) is
  given the cap.
* **The conditional-tail rule.** A statement right-censored before the cap, at ``c`` days, is
  represented by ``TAIL_POINTS`` copies of its row, each with weight ``1 / TAIL_POINTS``. Their
  targets are the quantiles at the levels ``(k - 0.5) / TAIL_POINTS`` of the *conditional tail*:
  the distribution of the time to recovery given that it is above ``c``, under the pooled
  Turnbull estimate of the uncapped time to recovery of all fitting statements
  (``predictors.turnbull`` on ``predictors.ttr_brackets``; mass spread evenly inside an
  innermost interval). A quantile that falls beyond the cap, or in the mass the estimate cannot
  place at a finite time, is the cap. Every other statement has one row of weight 1.

Reading the model.

* The predicted quantiles of a statement are kept within 0 to 365 and sorted, so that they
  never decrease.
* The quantile function is the straight-line interpolation through the points (level 0, day 0)
  and (level, predicted quantile). The probability of recovery by a horizon ``h`` days after
  the statement, for ``h`` below the cap, is the largest level at which the quantile function
  is at most ``h``; it is never above 0.95, because the model does not place the last 5%.
* For a horizon at or beyond the cap the capped model says nothing, so the curve is continued
  with the pooled conditional tail: ``F(h) = F(cap-) + (1 - F(cap-)) * G(h)``, where ``F(cap-)``
  is the model's probability of recovery before the cap and ``G(h)`` is the pooled Turnbull
  probability of recovery by ``h`` given no recovery by the cap.
* The quantiles reported are those at 0.10, 0.50, 0.80, 0.90 and 0.95.

``fit_all`` fits every model-free predictor of PLAN section 8 on one fitting frame, in the
order of ``PREDICTORS``: the base rate by listing age, the stated date at face value, rules plus
slip (all three in ``predictors.py``), then the two models of this file. Each has
``predict(frame)``.

This module has no command. ``power.py`` fits the predictors on the fit split, scores them on
dev and writes ``out/dev_losses.json``::

    PYTHONPATH=. python -m analysis.coling.power
    PYTHONPATH=. python -m pytest analysis/coling/test_gbm.py -q -p no:cacheprovider
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer

from analysis.coling import predictors as P

SEED = P.SEED
CAP_DAYS = P.CAP_DAYS
QUANTILES = tuple(round(0.05 * k, 2) for k in range(1, 20))
TAIL_POINTS = 10
MIN_CATEGORY = 20
CATEGORICAL = ("reason", "category", "company")
STRUCTURED = (*CATEGORICAL, "month", "age")
PARAMS: dict[str, Any] = {
    "learning_rate": 0.05,
    "max_iter": 200,
    "max_leaf_nodes": 8,
    "min_samples_leaf": 40,
    "l2_regularization": 0.0,
    "max_bins": 255,
    "early_stopping": False,
}
TFIDF: dict[str, Any] = {
    "lowercase": True,
    "ngram_range": (1, 2),
    "min_df": 5,
    "max_features": 300,
    "sublinear_tf": True,
}
PREDICTORS = ("base_rate", "face_value", "rules_plus_slip", "gbm_structured", "gbm_text")
OTHER = 0
"""The code of a category value that is rare in, or absent from, the fitting statements."""


# --------------------------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------------------------


def normal(value: str) -> str:
    """A category value lower-cased, with runs of spaces collapsed."""
    return " ".join(str(value).lower().split())


def fit_categories(rows: pd.DataFrame, minimum: int = MIN_CATEGORY) -> dict[str, dict[str, int]]:
    """For each categorical column, the code of every value seen on at least ``minimum``
    fitting statements: 1, 2, ... in the order of the sorted values (``OTHER`` is the rest)."""
    codes = {}
    for column in CATEGORICAL:
        counts = rows[column].map(normal).value_counts()
        kept = sorted(value for value, count in counts.items() if count >= minimum)
        codes[column] = {value: k for k, value in enumerate(kept, start=1)}
    return codes


def structured_matrix(frame: pd.DataFrame, codes: Mapping[str, Mapping[str, int]]) -> np.ndarray:
    """The structured features of ``frame``, one column per name of ``STRUCTURED``."""
    columns = [
        frame[column].map(normal).map(codes[column]).fillna(OTHER).to_numpy(dtype=float)
        for column in CATEGORICAL
    ]
    columns.append(frame["month"].to_numpy(dtype=float) - 1.0)
    columns.append(frame["age"].to_numpy(dtype=float))
    return np.column_stack(columns)


def fit_vectorizer(texts: pd.Series) -> TfidfVectorizer:
    """The TF-IDF vocabulary and weights of the fitting statements' notice text."""
    return TfidfVectorizer(**TFIDF).fit(texts.tolist())


# --------------------------------------------------------------------------------------------
# Targets: midpoints, the cap and the conditional tail
# --------------------------------------------------------------------------------------------


def tail_targets(censored_at: Any, pooled: P.Turnbull, points: int = TAIL_POINTS) -> np.ndarray:
    """The targets that stand for statements right-censored at ``censored_at`` days: per
    statement, the ``points`` quantiles of the pooled conditional tail, capped (one row each).
    """
    levels = (np.arange(points) + 0.5) / points
    after = np.asarray(censored_at, dtype=float)
    tail = pooled.conditional_quantile(levels[None, :], after[:, None])
    return np.minimum(tail, float(CAP_DAYS))


def training_targets(
    rows: pd.DataFrame, pooled: P.Turnbull, points: int = TAIL_POINTS
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The training rows of the quantile models: for each, the position of its statement in
    ``rows``, its target in days and its weight (see the module docstring)."""
    kind = rows["ttr_kind"].to_numpy()
    censored = np.flatnonzero(kind == "right_censored")
    whole = np.flatnonzero(kind != "right_censored")
    tails = tail_targets(rows["ttr_lower"].to_numpy(dtype=float)[censored], pooled, points)
    position = np.concatenate([whole, np.repeat(censored, points)])
    target = np.concatenate([rows["ttr_mid"].to_numpy(dtype=float)[whole], tails.ravel()])
    weight = np.concatenate([np.ones(len(whole)), np.full(len(censored) * points, 1.0 / points)])
    if np.isnan(target).any():
        raise ValueError("a fitting statement has no target")
    return position, target, weight


# --------------------------------------------------------------------------------------------
# Reading the quantiles as a distribution
# --------------------------------------------------------------------------------------------


def cdf_at(quantiles: Any, horizon: Any, pooled: P.Turnbull) -> np.ndarray:
    """The probability of recovery by ``horizon`` days (one per row) from each row's sorted,
    capped quantiles at the levels of ``QUANTILES`` (see "Reading the model")."""
    quantiles = np.asarray(quantiles, dtype=float)
    h = np.asarray(horizon, dtype=float)
    n = len(h)
    levels = np.concatenate([[0.0], QUANTILES])
    knots = np.column_stack([np.zeros(n), quantiles])
    last = len(levels) - 1
    # Below the cap: interpolate between the last knot at or below h and the next one.
    k = (knots <= h[:, None]).sum(axis=1)
    low, high = np.clip(k - 1, 0, last), np.clip(k, 0, last)
    rows = np.arange(n)
    span = knots[rows, high] - knots[rows, low]
    share = np.divide(h - knots[rows, low], span, out=np.zeros(n), where=span > 0)
    below = levels[low] + share * (levels[high] - levels[low])
    below = np.where(k == 0, 0.0, below)
    # At or beyond the cap: the model's mass before the cap, then the pooled conditional tail.
    before_cap = levels[np.minimum((knots < CAP_DAYS).sum(axis=1), last)]
    pooled_at_cap = float(pooled.cdf(float(CAP_DAYS)))
    rest = 1.0 - pooled_at_cap
    tail = np.clip((pooled.cdf(h) - pooled_at_cap) / rest, 0.0, 1.0) if rest > 0 else np.zeros(n)
    return np.where(h >= CAP_DAYS, before_cap + (1.0 - before_cap) * tail, below)


# --------------------------------------------------------------------------------------------
# The models
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class QuantileGBM:
    """A fitted gradient-boosted quantile model of the capped time to recovery."""

    codes: Mapping[str, Mapping[str, int]]
    vectorizer: TfidfVectorizer | None
    """The TF-IDF of the text-trained model; None for the structured-only model."""
    models: tuple[HistGradientBoostingRegressor, ...]
    pooled: P.Turnbull
    rows: Mapping[str, int]
    """Fitting statements by kind of target, and the training rows they gave."""

    def features(self, frame: pd.DataFrame) -> np.ndarray:
        return features(frame, self.codes, self.vectorizer)

    def quantiles(self, frame: pd.DataFrame) -> np.ndarray:
        """The quantiles at ``QUANTILES`` for each row: kept within 0 to the cap and sorted."""
        x = self.features(frame)
        raw = np.column_stack([model.predict(x) for model in self.models])
        return np.sort(np.clip(raw, 0.0, float(CAP_DAYS)), axis=1)

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        q = self.quantiles(frame)
        out = pd.DataFrame(index=frame.index, columns=list(P.PREDICTION_COLUMNS), dtype=float)
        out["p_a"] = cdf_at(q, frame["h_a"], self.pooled)
        out["p_b"] = cdf_at(q, frame["h_b"], self.pooled)
        for key, level in zip(P.QUANTILE_KEYS, P.QUANTILE_LEVELS, strict=True):
            out[key] = q[:, QUANTILES.index(round(level, 2))]
        return out


def features(
    frame: pd.DataFrame, codes: Mapping[str, Mapping[str, int]], vectorizer: TfidfVectorizer | None
) -> np.ndarray:
    """The feature matrix: the structured columns, then the TF-IDF columns if there are any."""
    structured = structured_matrix(frame, codes)
    if vectorizer is None:
        return structured
    return np.hstack([structured, vectorizer.transform(frame["text"].tolist()).toarray()])


def fit_gbm(frame: pd.DataFrame, text: bool) -> QuantileGBM:
    """The structured-only model (``text=False``) or the text-trained model (``text=True``),
    fitted on the fitting statements of ``frame``."""
    rows = P.fitting_rows(frame, P.BASE_RATE_SETS)
    if not len(rows):
        raise ValueError("no fitting statement")
    pooled = P.turnbull(*P.ttr_brackets(rows))
    position, target, weight = training_targets(rows, pooled)
    codes = fit_categories(rows)
    vectorizer = fit_vectorizer(rows["text"]) if text else None
    x = features(rows, codes, vectorizer)[position]
    categorical = list(range(len(CATEGORICAL) + 1))
    models = tuple(
        HistGradientBoostingRegressor(
            loss="quantile",
            quantile=level,
            categorical_features=categorical,
            random_state=SEED,
            **PARAMS,
        ).fit(x, target, sample_weight=weight)
        for level in QUANTILES
    )
    kinds = rows["ttr_kind"].value_counts()
    counts = {kind: int(kinds.get(kind, 0)) for kind in P.TTR_KINDS}
    counts.update(statements=len(rows), training_rows=len(position), features=x.shape[1])
    return QuantileGBM(codes, vectorizer, models, pooled, counts)


def fit_all(frame: pd.DataFrame, min_cell: int = P.MIN_CELL) -> dict[str, Any]:
    """Every model-free predictor of PLAN section 8, fitted on the fitting statements of
    ``frame``, by its name in ``PREDICTORS``."""
    fitted = {
        "base_rate": P.fit_base_rate(frame, min_cell),
        "face_value": P.FaceValue(),
        "rules_plus_slip": P.fit_calibrator(frame, min_cell),
        "gbm_structured": fit_gbm(frame, text=False),
        "gbm_text": fit_gbm(frame, text=True),
    }
    return {name: fitted[name] for name in PREDICTORS}
