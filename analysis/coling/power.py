"""Dev losses of the model-free predictors and the power estimate of the confirmatory family
(PLAN.md sections 6 "Power", 7.2 and 8; DECISIONS.md 3, 12 and 13).

What it does, on train-period data only.

1. Fits every model-free predictor (``gbm.fit_all``: base rate by listing age, the stated date at
   face value, rules plus slip, the structured-only and the text-trained gradient-boosted
   models) on the statements of the fit split.
2. Scores them on the dated statements of the dev split: the primary Brier loss on the
   scoreable ones, with 95% percentile intervals from the paired cluster bootstrap by shortage
   episode (10,000 draws, seed 20261001); the two horizon events apart; the bounds with each
   undetermined horizon event set to no and to yes; the pinball loss at 0.5, 0.8 and 0.95 with
   its bounds; and every contrast between two predictors, as the comparator's mean loss minus
   the tested predictor's, with its 95% and 90% intervals and the p-values of PLAN section 6.
3. Estimates the minimum detectable difference of H1, H2 and H3 at 80% power, each test at
   0.05/6 (the Holm worst case), from one pair of model-free predictors per hypothesis.

The proxy pairs (``PROXY_PAIRS``). Each hypothesis has a language model on one side, and no
model call precedes registration. The pairs of H1 and H2 were fixed here before any dev outcome
was read. The pair of H3 was changed with the comparator of H3, after the dev losses had been
seen (PLAN.md, "Changes from the 29 September draft", item 36):

* H1 (one-sided), ``loss(m-a) - loss(m-b)``: face value against rules plus slip. Taking the
  notice at its word against the same reading with the list's track record.
* H2 (two-sided), ``loss(rules + calibrator) - loss(m-c)``: rules plus slip against the base
  rate by listing age.
* H3 (two-sided), ``loss(base rate) - loss(m-best)``: the base rate by listing age against the
  text-trained model.

How the dev variance is scaled to the test set. For a pair, ``d`` is the paired difference of
the primary loss on a scoreable dev statement.

* ``sd`` is the standard deviation of ``d`` over statements, and ``se_clustered`` the standard
  error of its mean with episodes as clusters: ``sqrt(G / (G - 1) * sum_g e_g^2) / N``, with
  ``e_g`` the sum of ``d - mean(d)`` over episode ``g``.
* The design effect on dev is ``se_clustered^2 / (sd^2 / N)``. With ``m = sum_g n_g^2 / N`` (the
  size-weighted mean number of statements per episode), the correlation within an episode is
  ``icc = (design effect - 1) / (m - 1)``, kept within 0 to 1.
* On the test set, ``se = sd * sqrt((1 + (m_test - 1) * icc) / N_test)``, and the minimum
  detectable difference is ``(z(1 - alpha) + z(power)) * se`` for the one-sided H1 and
  ``(z(1 - alpha / 2) + z(power)) * se`` for H2 and H3, with ``alpha = 0.05 / 6``.
* ``N_test`` and the episodes come from ``out/dataset_counts.json`` and ``m_test`` from the
  episodes of ``out/eligible_e3.csv``: the E3-eligible statements, which are an upper bound on
  the scoreable ones (first-sight counts only; no outcome of the test period is read, here or
  anywhere in this module).
* Once the counts-only code (``sealed_counts.py``) has written ``out/sealed_counts.json`` at the
  freeze, the same command takes the registered numbers of scoreable test statements and of
  their episodes from that file (two counts; nothing else in it is used), and ``m_test`` is
  scaled by the share of eligible statements that are scoreable. A count that the record gives
  as a lower bound (``>n``) is taken at the bound, ``n + 1``, and the report says which one is
  a bound; a count that is withheld or masked as small stops the command. ``--test-statements``
  and ``--test-episodes`` give the two numbers by hand instead.
* While only the eligible counts are known, the report also gives the value if the scoreable
  share were what it is on dev and on fit (``N_test`` and ``m_test`` both scaled by the share).
  It always gives the value from the number of episodes alone (``se_clustered * sqrt(G_dev /
  G_test)``).

The values are indicative. The dev split is dominated by "no" answers (its outcome mix is in
both outputs), the proxies are not language models, and fit outcomes are followed past the dev
boundary (PLAN section 3).

Outputs (both rewritten by the one command below; numbers are rounded to six decimals).

* ``out/dev_losses.json``: the fitting record (statements, calibrator cells and their basis,
  listing-age bins, the training rows of the gradient-boosted models), the same counts for the
  refit on fit and dev together that precedes the test runs (counts only: nothing is fitted on
  dev here), the dev set and its outcome mix, the losses and the contrasts.
* ``out/power.json``: the pairs, the dev variances, the test counts and the minimum detectable
  differences.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.power            # write both outputs
    PYTHONPATH=. python -m analysis.coling.power --check    # recompute and compare
    PYTHONPATH=. python -m analysis.coling.power --test-statements N --test-episodes G
    PYTHONPATH=. python -m pytest analysis/coling/test_power.py -q -p no:cacheprovider

Run the command again after any change to ``dataset.py`` or its outputs, ``predictors.py``,
``gbm.py`` or this file: ``--check`` and ``test_outputs_are_up_to_date`` report stale outputs
until then. ``--check`` takes the same flags as the run that wrote the outputs.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from scipy.stats import norm

from analysis.coling import dataset, gbm
from analysis.coling import predictors as P

SEED = P.SEED
DRAWS = P.DRAWS
FAMILY_ALPHA = 0.05
TESTS = 6
POWER = 0.80
OUT = dataset.OUT
DEV_LOSSES = OUT / "dev_losses.json"
POWER_REPORT = OUT / "power.json"
SEALED_COUNTS = OUT / "sealed_counts.json"
"""Written by ``sealed_counts.py`` at the freeze: counts only. Read for two numbers if it exists."""
COMMAND = "PYTHONPATH=. python -m analysis.coling.power"
PINBALL_KEYS = dict(zip(P.PINBALL_LEVELS, ("q50", "q80", "q95"), strict=True))


@dataclass(frozen=True)
class Pair:
    """The pair of model-free predictors that stands for a hypothesis in the power estimate.
    The contrast is the comparator's mean loss minus the tested predictor's."""

    hypothesis: str
    comparator: str
    tested: str
    sides: int
    stands_for: str


PROXY_PAIRS = (
    Pair("H1", "face_value", "rules_plus_slip", 1, "loss(m-a) - loss(m-b)"),
    Pair("H2", "rules_plus_slip", "base_rate", 2, "loss(rules + calibrator) - loss(m-c)"),
    Pair("H3", "base_rate", "gbm_text", 2, "loss(base rate) - loss(m-best)"),
)
SECONDARY_PAIRS = (
    ("gbm_structured", "gbm_text"),
    ("gbm_structured", "rules_plus_slip"),
    ("gbm_structured", "base_rate"),
)
"""The registered secondary contrasts of H3 that are not proxy pairs, as (comparator, tested):
the text-trained model, rules plus slip and the base rate, each against the structured-only
model (the comparator of H3 in the draft of 29 September). Rules plus slip against the base rate
is the H2 proxy pair with its sign reversed."""


# --------------------------------------------------------------------------------------------
# Fit on the fit split, predict on dev
# --------------------------------------------------------------------------------------------


def dev_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """The dated statements of the dev split."""
    return frame[(frame["split"] == "dev") & (frame["analysis_set"] == "dated")]


def fit_and_predict(
    frame: pd.DataFrame, min_cell: int = P.MIN_CELL
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, pd.DataFrame]]:
    """The predictors fitted on the fit split, the dev rows and each predictor's dev output."""
    fitted = gbm.fit_all(frame[frame["split"] == "fit"], min_cell)
    dev = dev_rows(frame)
    if (dev["period"] != "train").any() or not dev["outcome"].isin(P.OUTCOMES).all():
        raise ValueError("a dev statement is outside the train period or has no outcome")
    return fitted, dev, {name: model.predict(dev) for name, model in fitted.items()}


def contrast_pairs(names: Sequence[str]) -> list[tuple[str, str]]:
    """(comparator, tested) for every pair of predictors: the proxy pairs and the registered
    secondary first, in their registered direction, then the others in the order of ``names``.
    """
    registered = [*((p.comparator, p.tested) for p in PROXY_PAIRS), *SECONDARY_PAIRS]
    pairs = [pair for pair in registered if set(pair) <= set(names)]
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            if (first, second) not in pairs and (second, first) not in pairs:
                pairs.append((first, second))
    return pairs


def outcome_mix(rows: pd.DataFrame) -> dict[str, int]:
    """Scoreable statements by their two horizon events (``E_end/E_end90``)."""
    word = {0.0: "no", 1.0: "yes"}
    pair = rows["y_a"].map(word) + "/" + rows["y_b"].map(word)
    return {key: int((pair == key).sum()) for key in ("no/no", "no/yes", "yes/yes")}


# --------------------------------------------------------------------------------------------
# Dev losses
# --------------------------------------------------------------------------------------------


def primary_losses(rows: pd.DataFrame, predictions: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """The primary loss of each predictor (columns) on each row of ``rows``."""
    return pd.DataFrame(
        {
            name: P.primary_loss(
                pred.loc[rows.index, "p_a"], pred.loc[rows.index, "p_b"], rows["y_a"], rows["y_b"]
            )
            for name, pred in predictions.items()
        },
        index=rows.index,
    )


def predictor_record(
    dev: pd.DataFrame, pred: pd.DataFrame, loss: np.ndarray, draws: np.ndarray
) -> dict[str, Any]:
    """The dev scores of one predictor: ``loss`` and ``draws`` are its primary losses on the
    scoreable statements and the bootstrap draws of their mean."""
    scoreable = dev[dev["scoreable"]]
    mine = pred.loc[scoreable.index]
    return {
        "primary_brier": float(loss.mean()),
        "ci95": P.interval(draws, 0.95),
        "brier_E_end": float(P.brier(mine["p_a"], scoreable["y_a"]).mean()),
        "brier_E_end90": float(P.brier(mine["p_b"], scoreable["y_b"]).mean()),
        "mean_p_E_end": float(mine["p_a"].mean()),
        "mean_p_E_end90": float(mine["p_b"].mean()),
        "bounds_all_dated": P.brier_bounds(pred["p_a"], pred["p_b"], dev["y_a"], dev["y_b"]),
        "pinball_all_dated": {
            f"{level:.2f}": P.pinball_scores(pred[key], dev, level)
            for level, key in PINBALL_KEYS.items()
        },
    }


def loss_report(
    dev: pd.DataFrame,
    predictions: Mapping[str, pd.DataFrame],
    draws: int = DRAWS,
    seed: int = SEED,
) -> dict[str, Any]:
    """The dev set, each predictor's scores and every contrast (see the module docstring)."""
    scoreable = dev[dev["scoreable"]]
    names = list(predictions)
    losses = primary_losses(scoreable, predictions)
    boot = P.bootstrap_means(losses.to_numpy(), scoreable["episode_id"], draws, seed)
    column = {name: k for k, name in enumerate(names)}
    contrasts = []
    for comparator, tested in contrast_pairs(names):
        delta = boot[:, column[comparator]] - boot[:, column[tested]]
        p = P.p_values(delta)
        contrasts.append(
            {
                "comparator": comparator,
                "tested": tested,
                "delta": float((losses[comparator] - losses[tested]).mean()),
                "ci95": P.interval(delta, 0.95),
                "ci90": P.interval(delta, 0.90),
                "p_one_sided": p["one_sided"],
                "p_two_sided": p["two_sided"],
            }
        )
    return {
        "dev": {
            "dated_statements": len(dev),
            "dated_episodes": int(dev["episode_id"].nunique()),
            "scoreable_statements": len(scoreable),
            "scoreable_episodes": int(scoreable["episode_id"].nunique()),
            "with_a_horizon_event_undetermined": len(dev) - len(scoreable),
            "scoreable_by_E_end_and_E_end90": outcome_mix(scoreable),
        },
        "bootstrap": {"draws": draws, "seed": seed, "clusters": "shortage episodes"},
        "losses": {
            name: predictor_record(
                dev, predictions[name], losses[name].to_numpy(), boot[:, column[name]]
            )
            for name in names
        },
        "contrasts": contrasts,
    }


def fitting_record(fit: pd.DataFrame, fitted: Mapping[str, Any]) -> dict[str, Any]:
    """What the predictors were fitted on, and the choices the data made (which cells and bins
    have an estimate of their own; the training rows of the gradient-boosted models)."""
    sets = fit["analysis_set"].value_counts()
    record: dict[str, Any] = {
        "split": "fit",
        "statements_by_analysis_set": {name: int(sets.get(name, 0)) for name in P.SETS},
    }
    if "base_rate" in fitted:
        record["min_cell"] = fitted["base_rate"].min_cell
        record["base_rate_listing_age_bins"] = fitted["base_rate"].table()
    if "rules_plus_slip" in fitted:
        calibrator = fitted["rules_plus_slip"]
        record["min_cell"] = calibrator.min_cell
        record["calibrator_cells"] = calibrator.table()
        record["calibrator_all_dated_forms"] = {
            "statements": calibrator.pooled.statements,
            "share_by_stated_end": float(calibrator.pooled.slip.cdf(0.0)),
            "share_by_stated_end_90": float(calibrator.pooled.slip.cdf(90.0)),
        }
        record["no_date_listing_age_bins"] = calibrator.no_date.table()
    for name in ("gbm_structured", "gbm_text"):
        if name in fitted:
            record[name] = {
                **fitted[name].rows,
                "categories_kept": {c: len(v) for c, v in fitted[name].codes.items()},
            }
    return record


def refit_record(train: pd.DataFrame, min_cell: int = P.MIN_CELL) -> dict[str, Any]:
    """What the refit on fit and dev together will rest on: the train-period statements by
    set, the basis of every calibrator cell and listing-age bin, and the targets of the
    gradient-boosted models by kind. Counts only; nothing is fitted here."""
    sets = train["analysis_set"].value_counts()
    kinds = P.fitting_rows(train, P.BASE_RATE_SETS)["ttr_kind"].value_counts()
    return {
        "splits": "fit and dev",
        "statements_by_analysis_set": {name: int(sets.get(name, 0)) for name in P.SETS},
        "min_cell": min_cell,
        "base_rate_listing_age_bins": P.backoff_bins(train, P.BASE_RATE_SETS, min_cell),
        "calibrator_cells": P.backoff_cells(train, min_cell),
        "no_date_listing_age_bins": P.backoff_bins(train, P.NO_DATE_SETS, min_cell),
        "gbm_targets": {kind: int(kinds.get(kind, 0)) for kind in P.TTR_KINDS},
    }


# --------------------------------------------------------------------------------------------
# Power
# --------------------------------------------------------------------------------------------


def weighted_cluster_size(clusters: Sequence[str]) -> float:
    """``sum_g n_g^2 / N``: the mean number of statements per cluster, weighted by size."""
    sizes = pd.Series(list(clusters)).value_counts().to_numpy(dtype=float)
    return float((sizes**2).sum() / sizes.sum())


def clustered_variance(d: Any, clusters: Sequence[str]) -> dict[str, float]:
    """The mean of ``d``, its standard deviation over statements, the standard error of the
    mean with clusters, the design effect and the within-cluster correlation it implies."""
    d = np.asarray(d, dtype=float)
    n = len(d)
    sums, sizes = P.cluster_sums(d - d.mean(), clusters)
    groups = len(sizes)
    if groups < 2 or n < 2:
        raise ValueError("the clustered variance needs at least two clusters")
    sd = float(d.std(ddof=1))
    se = float(np.sqrt(groups / (groups - 1) * (sums[:, 0] ** 2).sum()) / n)
    effect = se**2 / (sd**2 / n) if sd > 0 else 1.0
    m = float((sizes**2).sum() / n)
    icc = min(max((effect - 1.0) / (m - 1.0), 0.0), 1.0) if m > 1 else 0.0
    return {
        "delta": float(d.mean()),
        "sd": sd,
        "se_clustered": se,
        "design_effect": float(effect),
        "icc": float(icc),
    }


def critical_value(sides: int, alpha: float = FAMILY_ALPHA / TESTS, power: float = POWER) -> float:
    """``z(1 - alpha / sides) + z(power)``: the minimum detectable difference in standard
    errors."""
    return float(norm.ppf(1.0 - alpha / sides) + norm.ppf(power))


def scaled_se(sd: float, icc: float, statements: float, cluster_size: float) -> float:
    """The standard error of a mean of ``statements`` paired differences in clusters of
    size-weighted mean ``cluster_size``."""
    return float(sd * np.sqrt((1.0 + (max(cluster_size, 1.0) - 1.0) * icc) / statements))


def registered_count(value: Any) -> tuple[int, bool]:
    """A count of the counts-only record as a number, and whether it is a lower bound. A count
    printed as a lower bound (``>n``) is taken at the smallest count it allows, ``n + 1`` (PLAN
    section 6: where a registered number is a lower bound, the bound is used). Stops at a count
    that is withheld or masked as small."""
    if type(value) is int:
        return value, False
    if isinstance(value, str) and re.fullmatch(r">[0-9]+", value):
        return int(value[1:]) + 1, True
    raise ValueError("the counts-only record gives no scoreable number or lower bound")


def registered_scoreable(record: Mapping[str, Any]) -> tuple[int, int, tuple[str, ...]]:
    """The numbers of scoreable test statements and of their episodes in the record of the
    counts-only code, and the names of those that are lower bounds. Stops when either is
    absent, withheld or masked as a small count."""
    block = record["e3_eligible_test"]
    read = {
        name: registered_count(block[f"scoreable_{name}"]) for name in ("statements", "episodes")
    }
    bounds = tuple(name for name, (_, bound) in read.items() if bound)
    return read["statements"][0], read["episodes"][0], bounds


def target_counts(
    counts: Mapping[str, Any],
    eligible: pd.DataFrame,
    statements: int | None = None,
    episodes: int | None = None,
    source: str = "the command line",
) -> dict[str, Any]:
    """The test-set numbers the dev variance is scaled to: the E3-eligible statements and their
    episodes, or the registered scoreable numbers when given (``source`` says from where)."""
    listed, listed_episodes = len(eligible), int(eligible["episode_id"].nunique())
    recorded = counts["e3"]
    if (listed, listed_episodes) != (recorded["statements"], recorded["episodes"]):
        raise ValueError("the eligible list and the counts file are not from the same build")
    size = weighted_cluster_size(eligible["episode_id"])
    if statements is None and episodes is None:
        basis = "E3-eligible statements (an upper bound on the scoreable ones)"
        return {
            "basis": basis,
            "statements": listed,
            "episodes": listed_episodes,
            "weighted_statements_per_episode": size,
        }
    if statements is None or episodes is None or not 0 < statements <= listed:
        raise ValueError("give both scoreable numbers, with statements at most the eligible")
    if not 1 < episodes <= listed_episodes:
        raise ValueError("the scoreable episodes must be more than one and at most the eligible")
    return {
        "basis": f"scoreable test statements and episodes, from {source}",
        "statements": statements,
        "episodes": episodes,
        "weighted_statements_per_episode": size * statements / listed,
        "eligible_statements": listed,
        "eligible_episodes": listed_episodes,
    }


def scoreable_shares(counts: Mapping[str, Any]) -> dict[str, float]:
    """The share of dated statements that are scoreable on dev and on fit (train outcomes)."""
    return {
        split: counts["train"][split]["dated"]["scoreable"]
        / counts["train"][split]["dated"]["statements"]
        for split in ("dev", "fit")
    }


def power_report(
    scoreable: pd.DataFrame,
    losses: pd.DataFrame,
    test: Mapping[str, Any],
    shares: Mapping[str, float],
) -> dict[str, Any]:
    """The minimum detectable difference of each hypothesis from its proxy pair's paired losses
    on the scoreable dev statements (see the module docstring)."""
    clusters = scoreable["episode_id"]
    dev_episodes = int(clusters.nunique())
    n, size = test["statements"], test["weighted_statements_per_episode"]
    hypotheses = {}
    for pair in PROXY_PAIRS:
        variance = clustered_variance(losses[pair.comparator] - losses[pair.tested], clusters)
        z = critical_value(pair.sides)
        se = scaled_se(variance["sd"], variance["icc"], n, size)
        by_share = {
            name: z * scaled_se(variance["sd"], variance["icc"], n * share, size * share)
            for name, share in shares.items()
        }
        episodes_only = variance["se_clustered"] * np.sqrt(dev_episodes / test["episodes"])
        hypotheses[pair.hypothesis] = {
            "stands_for": pair.stands_for,
            "comparator": pair.comparator,
            "tested": pair.tested,
            "sides": pair.sides,
            "critical_value": z,
            "dev": variance,
            "test_se": se,
            "minimum_detectable_delta": z * se,
            "if_the_scoreable_share_were_that_of": by_share,
            "from_episodes_alone": float(z * episodes_only),
        }
    return {
        "family": {
            "familywise_alpha": FAMILY_ALPHA,
            "tests_in_the_family": TESTS,
            "alpha_per_test": FAMILY_ALPHA / TESTS,
            "power": POWER,
        },
        "dev": {
            "scoreable_statements": len(scoreable),
            "scoreable_episodes": dev_episodes,
            "weighted_statements_per_episode": weighted_cluster_size(clusters),
            "scoreable_by_E_end_and_E_end90": outcome_mix(scoreable),
        },
        "test": dict(test),
        "scoreable_share_of_dated_train_statements": dict(shares),
        "hypotheses": hypotheses,
    }


# --------------------------------------------------------------------------------------------
# Reports and the command line
# --------------------------------------------------------------------------------------------


def rounded(value: Any) -> Any:
    """``value`` with every float rounded to six decimals (lists and mappings included)."""
    if isinstance(value, Mapping):
        return {key: rounded(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [rounded(item) for item in value]
    if isinstance(value, float | np.floating):
        return round(float(value), 6)
    if isinstance(value, np.integer):
        return int(value)
    return value


def report_text(report: Mapping[str, Any]) -> str:
    return json.dumps(rounded(report), indent=1, ensure_ascii=False, allow_nan=False) + "\n"


def parameter_record() -> dict[str, Any]:
    """The fixed settings of the predictors and of the resampling."""
    return {
        "seed": SEED,
        "cap_days": P.CAP_DAYS,
        "listing_age_edges_days": list(P.AGE_EDGES),
        "turnbull_tolerance": f"{P.TOLERANCE:g}",
        "quantile_levels_reported": list(P.QUANTILE_LEVELS),
        "gbm_quantile_levels": list(gbm.QUANTILES),
        "gbm_settings": dict(gbm.PARAMS),
        "gbm_tail_points": gbm.TAIL_POINTS,
        "gbm_min_category": gbm.MIN_CATEGORY,
        "tfidf_settings": {key: rounded(value) for key, value in gbm.TFIDF.items()},
    }


def code_record() -> dict[str, str]:
    """The hashes of the code and the versions of the libraries the numbers depend on."""
    files = {"predictors": P.__file__, "gbm": gbm.__file__, "power": __file__}
    record = {
        f"{name}_sha256": dataset.sha16(Path(path).read_bytes()) for name, path in files.items()
    }
    record.update(numpy=np.__version__, pandas=pd.__version__, scikit_learn=sklearn.__version__)
    return record


def build(
    table: pd.DataFrame,
    counts: Mapping[str, Any],
    eligible: pd.DataFrame,
    statements: int | None = None,
    episodes: int | None = None,
    draws: int = DRAWS,
    min_cell: int = P.MIN_CELL,
    source: str = "the command line",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The two reports (dev losses, power) from the statement table, the counts of the dataset
    builder and the E3 eligible list. ``statements`` and ``episodes`` are the scoreable test
    numbers, when they are known, and ``source`` where they come from."""
    test = target_counts(counts, eligible, statements, episodes, source)
    frame = P.prepare(table)
    here, recorded = int(dev_rows(frame)["scoreable"].sum()), counts["dev_scoreable"]["statements"]
    if here != recorded:
        raise ValueError(
            f"{here} scoreable dev statements here, {recorded} in the counts file: "
            "the statement table and the counts are not from the same build"
        )
    fitted, dev, predictions = fit_and_predict(frame, min_cell)
    scoreable = dev[dev["scoreable"]]
    losses = loss_report(dev, predictions, draws)
    train = frame[frame["period"] == "train"]
    losses = {
        "fitting": fitting_record(frame[frame["split"] == "fit"], fitted),
        "refit_for_the_test_runs": refit_record(train, min_cell),
        **losses,
    }
    shares = scoreable_shares(counts) if statements is None else {}
    power = power_report(scoreable, primary_losses(scoreable, predictions), test, shares)
    return losses, power


def write_reports(
    losses: Mapping[str, Any], power: Mapping[str, Any], inputs: Mapping[str, Any]
) -> dict[str, str]:
    """The text of the two output files, by file name."""
    head = {"command": COMMAND, "inputs": dict(inputs), "parameters": parameter_record()}
    about_losses = (
        "Dev losses of the model-free predictors (PLAN.md sections 7.2 and 8): fitted on the "
        "fit split, scored on the dated statements of the dev split. Train-period outcomes only."
    )
    about_power = (
        "Minimum detectable difference of H1, H2 and H3 at 80% power and 0.05/6 per test "
        "(PLAN.md section 6), from one pair of model-free predictors per hypothesis on the "
        "scoreable dev statements. Indicative: the dev outcome mix is given beside it."
    )
    proxies = [
        {"hypothesis": p.hypothesis, "comparator": p.comparator, "tested": p.tested}
        for p in PROXY_PAIRS
    ]
    return {
        DEV_LOSSES.name: report_text({"about": about_losses, **head, **losses}),
        POWER_REPORT.name: report_text(
            {"about": about_power, **head, "proxy_pairs": proxies, **power}
        ),
    }


def print_summary(losses: Mapping[str, Any], power: Mapping[str, Any]) -> None:
    dev = losses["dev"]
    print(
        f"dev: {dev['scoreable_statements']} scoreable statements in "
        f"{dev['scoreable_episodes']} episodes; mix {dev['scoreable_by_E_end_and_E_end90']}"
    )
    for name, record in losses["losses"].items():
        low, high = record["ci95"]
        print(f"  {name:16s} primary Brier {record['primary_brier']:.4f} [{low:.4f}, {high:.4f}]")
    test = power["test"]
    print(f"power, scaled to {test['statements']} statements in {test['episodes']} episodes:")
    for name, record in power["hypotheses"].items():
        print(
            f"  {name} ({record['comparator']} - {record['tested']}): dev delta "
            f"{record['dev']['delta']:.4f}, minimum detectable {record['minimum_detectable_delta']:.4f}"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.power", description=(__doc__ or "").splitlines()[0]
    )
    ap.add_argument("--statements", type=Path, default=dataset.STATEMENTS, help="statement table")
    ap.add_argument("--counts", type=Path, default=dataset.COUNTS, help="dataset_counts.json")
    ap.add_argument("--eligible", type=Path, default=dataset.ELIGIBLE, help="the E3 eligible list")
    ap.add_argument("--out", type=Path, default=OUT, help="folder of the two outputs")
    ap.add_argument("--sealed-counts", type=Path, default=SEALED_COUNTS, help="counts-only record")
    ap.add_argument("--test-statements", type=int, help="registered scoreable test statements")
    ap.add_argument("--test-episodes", type=int, help="registered scoreable test episodes")
    ap.add_argument("--check", action="store_true", help="recompute and compare; write nothing")
    args = ap.parse_args(argv)
    for path in (args.statements, args.counts, args.eligible, args.sealed_counts, args.out):
        dataset.not_sealed(path)
    counts = json.loads(args.counts.read_text(encoding="utf-8"))
    statements, episodes, source = args.test_statements, args.test_episodes, "the command line"
    registered = args.sealed_counts.read_bytes() if args.sealed_counts.exists() else b""
    if registered and statements is None and episodes is None:
        statements, episodes, bounds = registered_scoreable(json.loads(registered))
        source = args.sealed_counts.name
        if bounds:
            source += f" (a lower bound for the {' and the '.join(bounds)})"
    inputs = {
        "statements": args.statements.as_posix(),
        "statements_sha256": dataset.sha16(args.statements.read_bytes()),
        "dataset_counts_sha256": dataset.sha16(args.counts.read_bytes()),
        "eligible_e3_sha256": dataset.sha16(args.eligible.read_bytes()),
        "sealed_counts_sha256": dataset.sha16(registered) if registered else "",
        **code_record(),
    }
    losses, power = build(
        dataset.load_statements(args.statements),
        counts,
        dataset.read_table(args.eligible),
        statements,
        episodes,
        source=source,
    )
    content = write_reports(losses, power, inputs)
    paths = {name: args.out / name for name in content}
    if args.check:
        stale = [
            paths[name].as_posix()
            for name in content
            if not paths[name].exists() or paths[name].read_text(encoding="utf-8") != content[name]
        ]
        print("up to date" if not stale else "differs from a fresh run: " + ", ".join(stale))
        return 1 if stale else 0
    args.out.mkdir(parents=True, exist_ok=True)
    for name, text in content.items():
        paths[name].write_text(text, encoding="utf-8")
    print_summary(losses, power)
    print("wrote " + ", ".join(p.as_posix() for p in paths.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
