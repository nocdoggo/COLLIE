"""Synthetic F1.11 class and matched-swap checks, without outcomes."""

import hashlib
from dataclasses import replace
from datetime import date, timedelta

import pytest

from analysis.coling.followup import e7
from analysis.coling.followup.e7 import (
    ConfirmedReferences, E7Class, LegacyReading, Prediction, PredictionContext,
    RuleReference, confirmed_references, e7_class, swap_class,
)
from analysis.coling.followup.measurement_sensitivity import ProbabilityPair


def reference(item):
    return RuleReference(item, date(2028, 3, 14))


def context(**changes):
    values = dict(earlier_horizon=date(2028, 3, 14), later_horizon=date(2028, 6, 12),
                  form="month_year", revision="first", calibration_sha256=e7.F1_CALIBRATOR_SOURCE_SHA256,
                  baseline_sha256=e7.F1_BASELINE_SHA256, quantile_levels=(.1, .5, .8, .9, .95))
    values.update(changes)
    return PredictionContext(**values)


def prediction(item, *, different=False, ctx=None):
    probabilities = ProbabilityPair(.3, .4) if different else ProbabilityPair(.1, .2)
    return Prediction(item, ctx or context(), probabilities, (10., 20., 30., 40., 50.), "full_precision")


def synthetic_scope(monkeypatch):
    ids = ("A", "B", "C", "D", "E")
    digest = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
    raw = b"statement_group_id\nA\nD\n"
    confirmed_hash = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(e7, "F1_ELIGIBLE_IDS_PREFIX", digest[:16])
    monkeypatch.setattr(e7, "F1_ELIGIBLE_COUNT", len(ids))
    monkeypatch.setattr(e7, "TASK_E_CONFIRMED_SHA256", confirmed_hash)
    monkeypatch.setattr(e7, "TASK_E_CONFIRMED_COUNT", 2)
    return ids, digest, raw


def test_four_registered_classes_and_correct_end_are_disjoint():
    ref = reference("A")
    assert e7_class(ref, LegacyReading("A", True, None, None)) is E7Class.NO_ANSWER
    assert e7_class(ref, LegacyReading("A", False, "recovery", None)) is E7Class.NO_STATED_PERIOD
    assert e7_class(ref, LegacyReading("A", False, "none", date(2028, 3, 20))) is E7Class.NO_STATED_PERIOD
    assert e7_class(ref, LegacyReading("A", False, "next_delivery", date(2028, 3, 15))) is E7Class.END_TOO_LATE
    assert e7_class(ref, LegacyReading("A", False, "recovery", date(2028, 2, 29))) is E7Class.END_TOO_EARLY
    assert e7_class(ref, LegacyReading("A", False, "recovery", date(2028, 3, 14))) is None
    with pytest.raises(ValueError):
        LegacyReading("A", True, "recovery", None)
    with pytest.raises(ValueError):
        e7_class(ref, LegacyReading("B", False, "recovery", None))


@pytest.mark.parametrize("selected", list(E7Class))
def test_class_swap_preserves_other_predictions_and_confirmed_subset(monkeypatch, selected):
    ids, digest, raw = synthetic_scope(monkeypatch)
    refs = [reference(item) for item in ids]
    reads = [LegacyReading("A", True, None, None), LegacyReading("B", False, "recovery", None),
             LegacyReading("C", False, "recovery", date(2028, 3, 20)),
             LegacyReading("D", False, "next_delivery", date(2028, 3, 1)),
             LegacyReading("E", False, "recovery", date(2028, 3, 14))]
    before = [prediction(item) for item in ids]
    after = [prediction(item, different=True) for item in ids]
    result = swap_class(eligible_ids=ids, references=refs, readings=reads,
                        original_predictions=before, reference_predictions=after,
                        selected_class=selected, confirmed_reference_list=confirmed_references(raw),
                        eligible_ids_sha256=digest, rule_reader_sha256=e7.FROZEN_RULE_SHA256)
    assert result.assigned_statements == 5 and result.class_statements == 1
    assert result.scientific_status == "registered_secondary_setup_outcome_free"
    assert result.confirmed_reference_statements == 2
    assert result.confirmed_reference_class_statements == (1 if selected in {E7Class.NO_ANSWER, E7Class.END_TOO_EARLY} else 0)
    for item, original, corrected, used in zip(ids, before, after, result.predictions, strict=True):
        row = next(read for read in reads if read.item_id == item)
        assert used == (corrected if e7_class(reference(item), row) is selected else original)


def test_confirmed_list_is_hash_checked_and_cannot_be_fabricated(monkeypatch):
    _, _, raw = synthetic_scope(monkeypatch)
    confirmed = confirmed_references(raw)
    assert confirmed.item_ids == ("A", "D")
    with pytest.raises(ValueError, match="identity"):
        confirmed_references(raw + b"\n")
    with pytest.raises(ValueError, match="verified"):
        ConfirmedReferences(("A",), "0" * 64, object())


def test_swaps_reject_mismatched_horizons_quantiles_and_coverage(monkeypatch):
    ids, digest, raw = synthetic_scope(monkeypatch)
    refs = [reference(item) for item in ids]
    reads = [LegacyReading(item, False, "recovery", date(2028, 3, 14)) for item in ids]
    before = [prediction(item) for item in ids]
    changed_context = context(earlier_horizon=date(2028, 3, 15), later_horizon=date(2028, 6, 13))
    after = [prediction(item, ctx=changed_context if item == "A" else None) for item in ids]
    args = dict(eligible_ids=ids, references=refs, readings=reads, original_predictions=before,
                reference_predictions=after, selected_class=E7Class.END_TOO_LATE,
                confirmed_reference_list=confirmed_references(raw), eligible_ids_sha256=digest,
                rule_reader_sha256=e7.FROZEN_RULE_SHA256)
    with pytest.raises(ValueError, match="preserve target horizons"):
        swap_class(**args)
    args["reference_predictions"] = before[:-1]
    with pytest.raises(ValueError, match="complete assigned scope"):
        swap_class(**args)
    with pytest.raises(ValueError, match="90 days"):
        context(later_horizon=date(2028, 6, 11))
    with pytest.raises(ValueError, match="quantile levels"):
        context(quantile_levels=(.5, .8, .95))
    with pytest.raises(ValueError, match="quantiles"):
        replace(before[0], quantiles_days=(10., 20., 30., 40., 366.))
    args["reference_predictions"] = [replace(value, source_precision="rounded_source") for value in before]
    with pytest.raises(ValueError, match="rounded"):
        swap_class(**args)
    args["reference_predictions"] = before
    args["rule_reader_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="rule-reader"):
        swap_class(**args)
