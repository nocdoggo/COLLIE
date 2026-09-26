from __future__ import annotations

import pandas as pd
import pytest

from collie.contracts import AnalysisClass
from collie.eval.guards import (
    assert_aggregation_unit_frame,
    assert_confirmatory_registered,
    classify_analysis,
)


def test_aggregation_unit_guard_raises_on_duplicate_rows() -> None:
    frame = pd.DataFrame(
        [
            {"independent_unit_id": "u1", "arm": "a", "analysis_class": "confirmatory"},
            {"independent_unit_id": "u1", "arm": "a", "analysis_class": "confirmatory"},
        ]
    )
    with pytest.raises(ValueError, match="more than one row"):
        assert_aggregation_unit_frame(frame)


def test_aggregation_unit_guard_allows_exploratory_duplicates() -> None:
    frame = pd.DataFrame(
        [
            {"independent_unit_id": "u1", "arm": "a", "analysis_class": "exploratory"},
            {"independent_unit_id": "u1", "arm": "a", "analysis_class": "exploratory"},
        ]
    )
    assert_aggregation_unit_frame(frame)


def test_confirmatory_render_guard_refuses_unregistered() -> None:
    with pytest.raises(ValueError, match="not registered"):
        assert_confirmatory_registered(
            "unregistered",
            AnalysisClass.CONFIRMATORY,
            {"holm_family": {"members": [{"id": "registered"}]}},
        )


def test_confirmatory_render_guard_allows_registered() -> None:
    assert_confirmatory_registered(
        "registered",
        AnalysisClass.CONFIRMATORY,
        {"holm_family": {"members": [{"id": "registered"}]}},
    )


def test_family_level_cvar_forced_to_exploratory() -> None:
    label = classify_analysis(
        "registered",
        AnalysisClass.CONFIRMATORY,
        family_level=True,
        metric="cvar10",
        prereg={"holm_family": {"members": [{"id": "registered"}]}},
    )
    assert label is AnalysisClass.EXPLORATORY


def test_aggregation_unit_guard_requires_its_columns() -> None:
    frame = pd.DataFrame([{"independent_unit_id": "u1"}])
    with pytest.raises(ValueError, match="requires columns"):
        assert_aggregation_unit_frame(frame)


def test_aggregation_unit_guard_checks_rows_without_an_analysis_column() -> None:
    frame = pd.DataFrame(
        [
            {"independent_unit_id": "u1", "arm": "a"},
            {"independent_unit_id": "u1", "arm": "a"},
        ]
    )
    with pytest.raises(ValueError, match="more than one row"):
        assert_aggregation_unit_frame(frame)


def test_confirmatory_guard_defaults_to_the_registered_preregistration() -> None:
    with pytest.raises(ValueError, match="not registered"):
        assert_confirmatory_registered("unregistered", AnalysisClass.CONFIRMATORY)
    assert_confirmatory_registered("arm10_vs_arm1:profit", AnalysisClass.CONFIRMATORY)


def test_confirmatory_guard_accepts_an_iterable_of_ids() -> None:
    assert_confirmatory_registered("registered", AnalysisClass.CONFIRMATORY, ["registered"])
    with pytest.raises(ValueError, match="not registered"):
        assert_confirmatory_registered("other", AnalysisClass.CONFIRMATORY, ["registered"])


def test_exploratory_statistics_skip_the_registry() -> None:
    assert_confirmatory_registered("anything", AnalysisClass.EXPLORATORY, [])


def test_classify_analysis_keeps_registered_confirmatory_labels() -> None:
    label = classify_analysis(
        "registered",
        AnalysisClass.CONFIRMATORY,
        prereg={"holm_family": {"members": [{"id": "registered"}]}},
    )
    assert label is AnalysisClass.CONFIRMATORY
