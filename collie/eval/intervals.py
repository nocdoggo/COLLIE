"""Paired intervals over independent units."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from collie.contracts import EpisodeResult
from collie.eval.guards import assert_aggregation_unit_frame, result_frame

__all__ = [
    "PairedInterval",
    "bootstrap_paired_interval",
    "holm_adjust",
    "paired_differences",
    "paired_interval",
    "paired_randomization_pvalue",
    "stratum_weighted_paired_interval",
    "wilcoxon_signed_rank_pvalue",
]


@dataclass(frozen=True, slots=True)
class PairedInterval:
    treatment: str
    control: str
    endpoint: str
    estimate: float
    ci_low: float
    ci_high: float
    n_units: int


ENDPOINT_COLUMNS = {
    "cumulative_undiscounted_profit": "total_profit",
    "total_lost_sales_units": "total_lost_sales",
    "fill_rate": "fill_rate",
    "normalized_reward": "normalized_reward",
}


def _two_sided_normal_pvalue(z_score: float) -> float:
    return 2.0 * (1.0 - NormalDist().cdf(abs(z_score)))


def paired_differences(
    results: Sequence[EpisodeResult], *, treatment: str, control: str, endpoint: str
) -> tuple[float, ...]:
    """Return treatment-control differences paired by independent unit."""
    if endpoint not in ENDPOINT_COLUMNS:
        raise ValueError(f"unsupported paired endpoint {endpoint!r}")
    frame = result_frame(results)
    assert_aggregation_unit_frame(frame)
    col = ENDPOINT_COLUMNS[endpoint]
    subset = frame[frame["arm"].isin([treatment, control])]
    pivot = subset.pivot(index="independent_unit_id", columns="arm", values=col)
    if treatment not in pivot or control not in pivot:
        raise ValueError(f"paired contrast needs both arms: {treatment!r}, {control!r}")
    complete = pivot[[treatment, control]].dropna()
    if complete.empty:
        raise ValueError("paired contrast has no complete independent units")
    return tuple(float(v) for v in (complete[treatment] - complete[control]).to_numpy())


def paired_randomization_pvalue(differences: Sequence[float]) -> float:
    """Two-sided paired sign-flip randomization p-value for zero mean difference."""
    diffs = np.asarray(differences, dtype=float)
    if len(diffs) == 0:
        raise ValueError("cannot compute randomization p-value over an empty sequence")
    observed = abs(float(np.mean(diffs)))
    if len(diffs) <= 20:
        extreme = 0
        total = 1 << len(diffs)
        for mask in range(total):
            signs = np.array([1.0 if mask & (1 << i) else -1.0 for i in range(len(diffs))])
            if abs(float(np.mean(diffs * signs))) >= observed:
                extreme += 1
        return extreme / total
    sd = float(np.std(diffs, ddof=1))
    if sd == 0.0:
        return 1.0 if observed == 0.0 else 0.0
    return _two_sided_normal_pvalue(float(np.mean(diffs)) / (sd / np.sqrt(len(diffs))))


def wilcoxon_signed_rank_pvalue(differences: Sequence[float]) -> float:
    """Normal-approximation two-sided Wilcoxon signed-rank p-value."""
    diffs = np.asarray([diff for diff in differences if diff != 0.0], dtype=float)
    if len(diffs) == 0:
        return 1.0
    order = np.argsort(np.abs(diffs))
    ranks = np.empty(len(diffs), dtype=float)
    start = 0
    while start < len(diffs):
        end = start + 1
        while end < len(diffs) and abs(diffs[order[end]]) == abs(diffs[order[start]]):
            end += 1
        ranks[order[start:end]] = (start + 1 + end) / 2.0
        start = end
    positive_rank_sum = float(np.sum(ranks[diffs > 0.0]))
    n = len(diffs)
    mean = n * (n + 1) / 4.0
    variance = n * (n + 1) * (2 * n + 1) / 24.0
    if variance == 0.0:
        return 1.0
    return _two_sided_normal_pvalue((positive_rank_sum - mean) / np.sqrt(variance))


def holm_adjust(pvalues: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values keyed by registered analysis id."""
    adjusted: dict[str, float] = {}
    running_max = 0.0
    ordered = sorted(pvalues.items(), key=lambda item: item[1])
    total = len(ordered)
    for rank, (analysis_id, pvalue) in enumerate(ordered):
        value = min(1.0, (total - rank) * float(pvalue))
        running_max = max(running_max, value)
        adjusted[analysis_id] = running_max
    return adjusted


def bootstrap_paired_interval(
    differences: Sequence[float],
    *,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap interval resampling paired independent-unit differences."""
    diffs = np.asarray(differences, dtype=float)
    if len(diffs) == 0:
        raise ValueError("cannot bootstrap over an empty sequence")
    if resamples < 1:
        raise ValueError("resamples must be positive")
    rng = np.random.default_rng(seed)
    draws = rng.choice(diffs, size=(resamples, len(diffs)), replace=True)
    means = np.mean(draws, axis=1)
    alpha = 1.0 - confidence
    low, high = np.quantile(means, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(low), float(high)


def paired_interval(
    results: Sequence[EpisodeResult],
    *,
    treatment: str,
    control: str,
    endpoint: str,
    confidence: float = 0.95,
) -> PairedInterval:
    """Normal-approximation paired interval for a treatment-control contrast."""
    diffs = np.asarray(
        paired_differences(results, treatment=treatment, control=control, endpoint=endpoint),
        dtype=float,
    )
    estimate = float(np.mean(diffs))
    if len(diffs) == 1:
        half_width = 0.0
    else:
        alpha = 1.0 - confidence
        z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
        half_width = float(z * np.std(diffs, ddof=1) / np.sqrt(len(diffs)))
    return PairedInterval(
        treatment=treatment,
        control=control,
        endpoint=endpoint,
        estimate=estimate,
        ci_low=estimate - half_width,
        ci_high=estimate + half_width,
        n_units=len(diffs),
    )


def stratum_weighted_paired_interval(
    results: Sequence[EpisodeResult],
    *,
    treatment: str,
    control: str,
    endpoint: str,
    weights: Mapping[tuple, float],
    strata: Sequence[str] = ("family", "information_condition"),
    confidence: float = 0.95,
) -> PairedInterval:
    """Paired interval for a contrast after applying registered stratum weights."""
    if endpoint not in ENDPOINT_COLUMNS:
        raise ValueError(f"unsupported paired endpoint {endpoint!r}")
    frame = result_frame(results)
    assert_aggregation_unit_frame(frame)
    col = ENDPOINT_COLUMNS[endpoint]
    alpha = 1.0 - confidence
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)

    weighted_estimate = 0.0
    weighted_variance = 0.0
    used_weight = 0.0
    n_units = 0
    for key, weight in weights.items():
        if not isinstance(key, tuple):
            key = (key,)
        if len(key) != len(strata):
            raise ValueError(f"weight key {key!r} does not match strata {strata!r}")
        mask = frame["arm"].isin([treatment, control])
        for col_name, value in zip(strata, key, strict=True):
            if col_name not in frame.columns:
                raise ValueError(f"missing stratum column {col_name!r}")
            mask &= frame[col_name] == value
        subset = frame[mask]
        if subset.empty:
            continue
        pivot = subset.pivot(index="independent_unit_id", columns="arm", values=col)
        if treatment not in pivot or control not in pivot:
            continue
        complete = pivot[[treatment, control]].dropna()
        if complete.empty:
            continue
        diffs = (complete[treatment] - complete[control]).to_numpy(dtype=float)
        stratum_weight = float(weight)
        weighted_estimate += float(np.mean(diffs)) * stratum_weight
        if len(diffs) > 1:
            weighted_variance += (
                stratum_weight**2 * float(np.var(diffs, ddof=1)) / float(len(diffs))
            )
        used_weight += stratum_weight
        n_units += len(diffs)
    if used_weight == 0.0:
        raise ValueError("paired contrast has no complete populated strata")
    estimate = weighted_estimate / used_weight
    half_width = z * float(np.sqrt(weighted_variance)) / used_weight
    return PairedInterval(
        treatment=treatment,
        control=control,
        endpoint=endpoint,
        estimate=estimate,
        ci_low=estimate - half_width,
        ci_high=estimate + half_width,
        n_units=n_units,
    )
