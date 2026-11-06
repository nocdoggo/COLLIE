"""Invented aggregate records and display-status checks."""

import hashlib
import json
from decimal import Decimal

import pytest

from analysis.coling.followup import rendering
from analysis.coling.followup.rendering import (
    Cell, CellStatus, display_cell, display_p, number, render_confirmatory, render_e5_tests,
    render_letter_counts, render_probe, render_registered_pattern, unique_count_from_share,
    verify_saved_bytes,
)


def cell(value, source=None):
    return Cell(CellStatus.PRESENT, number(value), source)


def family():
    entries = []
    for model in rendering.STUDY_MODELS:
        for hypothesis in rendering.HYPOTHESES:
            entry = dict(model=model, hypothesis=hypothesis, evaluable=True, holds=False,
                         delta=0.056055, ci95=[-0.002, 0.11218], p=.028397, p_holm=.157184,
                         items="the post-cutoff slice", statements=20, episodes=5,
                         comparator={"H1": f"{model}:a", "H2": "rules_plus_slip", "H3": "base_rate"}[hypothesis],
                         tested={"H1": f"{model}:b", "H2": f"{model}:c", "H3": f"{model}:b"}[hypothesis],
                         sides=1 if hypothesis == "H1" else 2)
            if hypothesis == "H2":
                entry["equivalence"] = {"declared": True}
            entries.append(entry)
    return {"registered": {"p_value_source": "larger_of_studentised_and_sign_flip_t",
                           "tests_in_the_family": 6, "familywise_alpha": .05,
                           "h2_margin": .02, "h3_comparator": "base_rate",
                           "intervals": {"of_the_confirmatory_contrasts_and_delta_gbm": "values_not_rejected_by_the_registered_test"}},
            "h3": {"selections": {model: {"selected": "b"} for model in rendering.STUDY_MODELS}},
            "family": entries}


def test_half_away_from_zero_and_historical_rounding_uncertainty():
    assert display_cell(cell("1.2345"), places=3) == "1.235"
    assert display_cell(cell("-1.2345"), places=3) == "-1.235"
    assert display_cell(cell("0.056055", 6), places=3, signed=True) == "+0.056"
    assert display_cell(cell("0.000500", 6), places=3) == "precision ambiguous"
    assert display_cell(cell("-0.000500", 6), places=3) == "precision ambiguous"
    assert display_p(cell("0.000999", 6)) == "<0.001"
    assert display_p(cell("0.001000", 6)) == "precision ambiguous"


def test_zero_withheld_missing_not_run_and_unbounded_are_distinct():
    values = [display_cell(cell("0"), places=3),
              *(display_cell(Cell(status), places=3) for status in (
                  CellStatus.WITHHELD, CellStatus.NOT_RUN, CellStatus.NOT_EVALUABLE,
                  CellStatus.UNDEFINED, CellStatus.MISSING, CellStatus.UNBOUNDED_LOW, CellStatus.UNBOUNDED_HIGH))]
    assert len(values) == len(set(values))
    assert values == ["0.000", "withheld", "not run", "not evaluable", "undefined",
                      "missing response", "-infinity", "+infinity"]
    with pytest.raises(ValueError):
        cell("NaN")
    with pytest.raises(ValueError):
        Cell(CellStatus.WITHHELD, Decimal(0))


def test_counts_are_derived_only_when_rounding_leaves_one_integer():
    assert unique_count_from_share("0.642857", 70) == 45
    assert unique_count_from_share("0.600000", 70) == 42
    assert unique_count_from_share("1.000000", 70) == 70
    assert unique_count_from_share("0.5", 1_000_000, source_decimal_places=1) is None
    with pytest.raises(ValueError):
        unique_count_from_share("1.1", 70)


def test_all_original_family_rows_and_score_specific_equivalence_are_rendered():
    text = render_confirmatory(family())
    assert text.count("| not rejected") == 6
    assert text.count("loss equivalence declared") == 2
    assert "not literal-reading competence" in text
    assert "comparator loss minus tested-predictor loss" in text
    invalid = family()
    invalid["family"][-1] = invalid["family"][0]
    with pytest.raises(ValueError, match="duplicate or missing"):
        render_confirmatory(invalid)


def test_unbounded_intervals_and_not_evaluable_are_not_zero_or_not_run():
    record = family()
    record["family"][0]["ci95"] = [None, None]
    record["family"][1] = dict(model=rendering.STUDY_MODELS[0], hypothesis="H2",
                               evaluable=False, p_holm=1.0)
    text = render_confirmatory(record)
    assert "[-infinity, +infinity]" in text
    assert "not evaluable" in text
    assert "not run" not in text


def test_verified_result_projection_never_returns_per_item(monkeypatch):
    data = {"registered": {}, "item_sets": {}, "per_item": {"private": "invented"}, "runs": {"private": "invented"}}
    raw = json.dumps(data).encode()
    monkeypatch.setitem(rendering.SAVED_RESULT_HASHES, "e2", hashlib.sha256(raw).hexdigest())
    projected = verify_saved_bytes("e2", raw)
    assert set(projected) == {"registered", "item_sets"}
    assert "invented" not in repr(projected)
    with pytest.raises(ValueError, match="identity"):
        verify_saved_bytes("e2", raw + b" ")


def test_letter_counts_preserve_pooled_denominator():
    record = {"item_sets": {"all": {"letter_reading": [
        {"model": rendering.STUDY_MODELS[0], "evaluable": True, "items": 70,
         "first": .642857, "second": 1.0},
        {"model": rendering.STUDY_MODELS[1], "evaluable": True, "items": 70,
         "first": .6, "second": 1.0},
    ]}}}
    text = render_letter_counts(record)
    assert "| llama-3.3-70b | 70 | 45 |" in text
    assert "| deepseek-v3 | 70 | 42 |" in text
    assert "| Rule reader | 70 | 70 |" in text


def test_e5_direction_and_probe_withholding_are_preserved():
    factors = ("certainty", "surface_form", "granularity", "stale", "distractor", "silent")
    tests = []
    for model in rendering.STUDY_MODELS:
        for factor in factors:
            tests.append(dict(model=model, factor=factor, evaluable=True, holds=True,
                              edited={"errors": 1, "items": 10}, unedited={"errors": 3, "items": 10},
                              difference=-.2 if factor == "silent" else .2, p_holm=.01))
    text = render_e5_tests({"tests": tests})
    assert "| silent | 1/10 | 3/10 | -0.200 |" in text
    probe = {"probe": {rendering.STUDY_MODELS[0]: {"withheld": True},
                       rendering.STUDY_MODELS[1]: {"evaluable": True, "delta": 18.1329, "p": .0053}}}
    text = render_probe(probe)
    assert "| withheld | withheld |" in text and "does not uniquely identify" in text
    assert "holds for neither" in render_registered_pattern({"sentence": {"case": "neither primary", "stated_for": []}})
