"""Evaluation guards that fail loudly before a misleading statistic can render."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

from collie.contracts import AnalysisClass, EpisodeResult
from collie.eval.prereg import Preregistration, load_preregistration

__all__ = [
    "assert_aggregation_unit_frame",
    "assert_confirmatory_registered",
    "classify_analysis",
    "result_frame",
]


def result_frame(results: Sequence[EpisodeResult]) -> pd.DataFrame:
    """Flatten episode results to the minimum frame expected by the metric code."""
    return pd.DataFrame(
        {
            "episode_id": r.episode_id,
            "independent_unit_id": r.independent_unit_id,
            "arm": r.arm_id,
            "family": r.family.value if r.family is not None else None,
            "information_condition": (
                r.information_condition.value if r.information_condition is not None else None
            ),
            "split": r.split.value if r.split is not None else None,
            "analysis_class": r.analysis_class.value,
            "total_profit": r.total_profit,
            "total_lost_sales": r.total_lost_sales,
            "fill_rate": r.fill_rate,
            "normalized_reward": r.normalized_reward,
        }
        for r in results
    )


def assert_aggregation_unit_frame(frame: pd.DataFrame) -> None:
    """Refuse confirmatory aggregation with duplicate independent-unit rows per arm."""
    required = {"independent_unit_id", "arm"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"aggregation guard requires columns {sorted(missing)}")
    if "analysis_class" in frame.columns:
        checked = frame[frame["analysis_class"] == AnalysisClass.CONFIRMATORY.value]
    else:
        checked = frame
    duplicates = checked.duplicated(["independent_unit_id", "arm"], keep=False)
    if duplicates.any():
        bad = (
            checked.loc[duplicates, ["independent_unit_id", "arm"]]
            .value_counts()
            .head(10)
            .to_dict()
        )
        raise ValueError(
            f"confirmatory statistic has more than one row per (independent_unit_id, arm): {bad}"
        )


def _registered_ids(prereg: Preregistration | Mapping[str, Any] | Iterable[str] | None) -> set[str]:
    if prereg is None:
        return set(load_preregistration().analysis_ids)
    if isinstance(prereg, Preregistration):
        return set(prereg.analysis_ids)
    if isinstance(prereg, Mapping):
        from collie.eval.prereg import registered_confirmatory_ids

        return registered_confirmatory_ids(prereg)
    return {str(x) for x in prereg}


def assert_confirmatory_registered(
    analysis_id: str,
    analysis_class: AnalysisClass,
    prereg: Preregistration | Mapping[str, Any] | Iterable[str] | None = None,
) -> None:
    """Refuse to label an unregistered statistic as confirmatory."""
    if analysis_class is not AnalysisClass.CONFIRMATORY:
        return
    allowed = _registered_ids(prereg)
    if analysis_id not in allowed:
        raise ValueError(
            f"{analysis_id!r} is not registered as confirmatory; allowed ids are {sorted(allowed)}"
        )


def classify_analysis(
    analysis_id: str,
    requested: AnalysisClass,
    *,
    family_level: bool = False,
    metric: str | None = None,
    prereg: Preregistration | Mapping[str, Any] | Iterable[str] | None = None,
) -> AnalysisClass:
    """Return the effective label after applying preregistration constraints."""
    if family_level and metric in {"cvar10", "worst_decile"}:
        return AnalysisClass.EXPLORATORY
    assert_confirmatory_registered(analysis_id, requested, prereg)
    return requested
