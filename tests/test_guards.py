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
