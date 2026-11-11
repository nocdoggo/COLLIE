"""Synthetic calibration controls and baseline-identity checks."""

import hashlib
from dataclasses import replace
from datetime import date
from math import nan
from types import MappingProxyType

import numpy as np
import pandas as pd
import pytest

from analysis.coling import gbm, predictors
from analysis.coling.followup.calibration import (
    BASELINE_FEATURES, CONTROL_SHIFTS, F1_BASELINE_SHA256, F1_CODE_HASHES, F1_REFIT_COUNTS,
    F1_ELIGIBLE_SHA256, F1_STATEMENTS_SHA256, CalibrationProvenanceUnavailable,
    VerifiedCalibration, baseline_digest, fit_on_open_train, forecast_reading, forecast_reference,
    omitted_field_control, shifted_reading, snapshot_calibrator, verify_f1_baseline,
    verified_forecast, verified_reference_forecast,
    CalibrationProvenance, RecomputedCalibration, recompute_open_calibration,
    recomputed_forecast, recomputed_reference_forecast,
)
from analysis.coling.followup.measurement_sensitivity import exact_brier_perturbation_bounds
from analysis.coling.followup.records import (
    Certainty, NaturalReading, NaturalReference, PartialReferenceReading, StatementType,
)
from analysis.coling.followup.test_semantic import context, reading


def synthetic_calibrator():
    slip = predictors.Turnbull(np.array([0., 100.]), np.array([1., 101.]),
                               np.array([.5, .5]), 2, 1, 0.)
    no_date_curve = predictors.Turnbull(np.array([0., 50.]), np.array([10., 60.]),
                                        np.array([.5, .5]), 2, 1, 0.)
    estimate = predictors.Estimate(2, slip, no_date_curve)
    no_date = predictors.AgeTable({predictors.ALL_AGES: no_date_curve}, {}, 100)
    return predictors.SlipCalibrator({}, {}, estimate, {}, no_date, 100)


def test_fixed_horizons_expose_a_flat_cdf_even_for_a_material_end_shift():
    cal, ref = snapshot_calibrator(synthetic_calibrator()), reading()
    ctx = context(snapshot=cal)
    p = forecast_reading(cal, ref, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=10)
    shifted = shifted_reading(ref, 14)
    q = forecast_reading(cal, shifted, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=10)
    assert (shifted.interval.end - ref.interval.end).days == 14
    assert p.context == q.context and p.probabilities == q.probabilities
    assert exact_brier_perturbation_bounds(p.probabilities, q.probabilities).max_absolute_change == 0
    distant = forecast_reading(cal, shifted_reading(ref, -90), statement_date=date(2028, 3, 1),
                               context=ctx, listing_age_days=10)
    assert distant.probabilities != p.probabilities


def test_omitted_field_control_changes_reading_not_forecast():
    cal, ref = snapshot_calibrator(synthetic_calibrator()), reading()
    altered = omitted_field_control(ref)
    assert altered.statement_type != ref.statement_type
    assert altered.certainty != ref.certainty and altered.interval.end == ref.interval.end
    ctx = context(snapshot=cal)
    one = forecast_reading(cal, ref, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=10)
    two = forecast_reading(cal, altered, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=10)
    assert one.probabilities == two.probabilities


def test_known_reference_end_maps_without_inventing_start_or_certainty():
    partial = PartialReferenceReading(StatementType.RECOVERY, "finite", None,
                                      date(2028, 3, 14), None, "")
    ref = NaturalReference("invented", "v1", (partial,), True)
    cal = snapshot_calibrator(synthetic_calibrator())
    ctx = context(snapshot=cal, item_id="invented")
    predicted = forecast_reference(cal, ref, statement_date=date(2028, 3, 1),
                                   context=ctx, listing_age_days=10)
    full = forecast_reading(cal, reading(), statement_date=date(2028, 3, 1),
                            context=ctx, listing_age_days=10)
    assert predicted.probabilities == full.probabilities
    unknown_type = NaturalReference("invented", "v1", (
        PartialReferenceReading(None, "finite", None, date(2028, 3, 14), None, ""),), True)
    with pytest.raises(ValueError, match="type"):
        forecast_reference(cal, unknown_type, statement_date=date(2028, 3, 1),
                           context=ctx, listing_age_days=10)


def test_all_fixed_shift_controls_preserve_interval_order_and_end_shift():
    original = reading(start="2028-02-20", end="2028-03-14")
    assert set(CONTROL_SHIFTS) == {0, -7, 7, -14, 14, -30, 30, -90, 90}
    for days in CONTROL_SHIFTS:
        altered = shifted_reading(original, days)
        assert (altered.interval.end - original.interval.end).days == days
        assert (altered.interval.end - altered.interval.start).days == (
            original.interval.end - original.interval.start).days
    with pytest.raises(ValueError):
        shifted_reading(original, 13)


def test_other_type_and_valid_null_use_the_no_date_fallback():
    cal, dated = snapshot_calibrator(synthetic_calibrator()), reading()
    ctx = context(snapshot=cal, listing_age_days=None)
    other = NaturalReading(StatementType.OTHER, dated.interval, Certainty.ESTIMATED, "")
    null = NaturalReading(StatementType.RECOVERY, None, Certainty.UNDETERMINED, "")
    p = forecast_reading(cal, other, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=None)
    q = forecast_reading(cal, null, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=None)
    assert p.probabilities == q.probabilities
    dated_forecast = forecast_reading(cal, dated, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=None)
    assert dated_forecast.probabilities != p.probabilities
    with pytest.raises(ValueError):
        forecast_reading(cal, dated, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=nan)


class SyntheticPredictor:
    def __init__(self, value):
        self.value = value

    def predict(self, frame):
        result = pd.DataFrame(index=frame.index, columns=predictors.PREDICTION_COLUMNS, dtype=float)
        result["p_a"] = self.value
        result["p_b"] = self.value + .1
        for number, name in enumerate(predictors.QUANTILE_KEYS):
            result[name] = float(10 + number)
        return result


def baseline_inputs():
    values = {name: ["x", "y"] for name in BASELINE_FEATURES}
    for name in ("end_days", "h_a", "h_b", "age", "month"):
        values[name] = [1., 2.]
    return pd.DataFrame(values, index=["invented-a", "invented-b"])


def models():
    return {name: SyntheticPredictor(i / 10) for i, name in enumerate(gbm.PREDICTORS)}


def test_baseline_digest_is_stable_and_requires_first_sight_only_inputs():
    frame, fitted = baseline_inputs(), models()
    digest = baseline_digest(fitted, frame, ["invented-b"])
    assert len(digest) == 64 and digest == baseline_digest(fitted, frame, ["invented-b"])
    assert digest != baseline_digest(fitted, frame, ["invented-a"])
    with pytest.raises(ValueError, match="first-sight"):
        baseline_digest(fitted, frame.assign(outcome=["invented", "invented"]), ["invented-a"])
    with pytest.raises(ValueError, match="probe"):
        baseline_digest(fitted, frame, ["invented-a", "invented-a"])
    with pytest.raises(ValueError, match="predictor"):
        baseline_digest({"base_rate": fitted["base_rate"]}, frame, ["invented-a"])


def test_baseline_digest_matches_the_registered_six_decimal_serialization():
    header = [f"{name}.{column}" for name in gbm.PREDICTORS for column in predictors.PREDICTION_COLUMNS]
    rows = []
    for item in ("invented-a", "invented-b"):
        values = []
        for i in range(len(gbm.PREDICTORS)):
            values.extend([i / 10, i / 10 + .1, 10., 11., 12., 13., 14.])
        rows.append(item + "," + ",".join(f"{number:.6f}" for number in values) + "\n")
    probe_header = [f"base_rate_at_probe_horizons.{column}" for column in predictors.PREDICTION_COLUMNS]
    probe_values = [0., .1, 10., 11., 12., 13., 14.]
    text = ("statement_group_id," + ",".join(header) + "\n" + "".join(rows)
            + "statement_group_id," + ",".join(probe_header) + "\n"
            + "invented-b," + ",".join(f"{number:.6f}" for number in probe_values) + "\n")
    assert baseline_digest(models(), baseline_inputs(), ["invented-b"]) == hashlib.sha256(text.encode()).hexdigest()


def test_caller_hash_claims_cannot_certify_either_synthetic_frame(monkeypatch):
    hashes = {"statements_sha256": F1_STATEMENTS_SHA256, "eligible_sha256": F1_ELIGIBLE_SHA256,
              **F1_CODE_HASHES}
    record = {"inputs": {"statements_sha256": F1_STATEMENTS_SHA256, "eligible_sha256": F1_ELIGIBLE_SHA256,
                         "code_sha256": {**F1_CODE_HASHES, "numpy": np.__version__,
                                          "pandas": pd.__version__, "scikit_learn": __import__("sklearn").__version__}},
              "predictions_sha256": F1_BASELINE_SHA256, "eligible_statements": 2593,
              "predictors": list(gbm.PREDICTORS),
              "refit": {"splits": "fit and dev", "statements_by_analysis_set": F1_REFIT_COUNTS},
              "probe_statements": 300}
    original = baseline_inputs()
    changed = original.assign(text=["different invented text", "another invented text"])
    assert baseline_digest(models(), original, ["invented-a"]) == baseline_digest(models(), changed, ["invented-a"])
    import analysis.coling.followup.calibration as module
    monkeypatch.setattr(module, "baseline_digest", lambda *args: pytest.fail("verification must fail before prediction"))
    for frame in (original, changed):
        with pytest.raises(CalibrationProvenanceUnavailable, match="provenance"):
            verify_f1_baseline(models(), frame, ["invented-a"], record=record, observed_hashes=hashes)
    with pytest.raises(CalibrationProvenanceUnavailable, match="provenance"):
        VerifiedCalibration(synthetic_calibrator(), F1_BASELINE_SHA256, F1_CODE_HASHES["predictors.py"],
                            F1_STATEMENTS_SHA256, F1_ELIGIBLE_SHA256, object())
    ctx = context()
    for wrapper, source in ((verified_forecast, reading()),
                            (verified_reference_forecast, NaturalReference("N1", "v1", (reading(),), True))):
        with pytest.raises(CalibrationProvenanceUnavailable, match="disabled"):
            wrapper(None, source, statement_date=date(2028, 3, 1), context=ctx, listing_age_days=10)


def test_snapshot_copies_mutable_state_and_replacement_cannot_preserve_its_identity():
    raw = synthetic_calibrator()
    snapshot = snapshot_calibrator(raw)
    ctx = context(snapshot=snapshot)
    original = forecast_reading(snapshot, reading(), statement_date=ctx.statement_date,
                                context=ctx, listing_age_days=ctx.listing_age_days)
    raw.pooled.slip.mass[:] = [.9, .1]
    raw.cells[("exact_day", "second")] = raw.pooled
    changed = snapshot_calibrator(raw)
    assert changed.state_sha256 != snapshot.state_sha256
    assert forecast_reading(snapshot, reading(), statement_date=ctx.statement_date,
                            context=ctx, listing_age_days=ctx.listing_age_days) == original
    with pytest.raises(ValueError, match="state hash"):
        replace(snapshot, state_bytes=changed.state_bytes)
    with pytest.raises(ValueError, match="state hash"):
        replace(snapshot, state_sha256="0" * 64)
    # Replacing both bytes and digest creates a different *unverified* snapshot;
    # it cannot be used under the old assignment or attached to the old forecast.
    other = replace(snapshot, state_bytes=changed.state_bytes, state_sha256=changed.state_sha256)
    assert other == changed
    with pytest.raises(ValueError, match="assigned state"):
        forecast_reading(other, reading(), statement_date=ctx.statement_date,
                         context=ctx, listing_age_days=ctx.listing_age_days)
    with pytest.raises(ValueError, match="snapshot"):
        replace(original, snapshot=other)
    object.__setattr__(snapshot, "state_bytes", changed.state_bytes)
    with pytest.raises(ValueError, match="assigned state"):
        forecast_reading(snapshot, reading(), statement_date=ctx.statement_date,
                         context=ctx, listing_age_days=ctx.listing_age_days)


def test_even_a_bypassed_verified_record_cannot_be_replaced_or_used():
    forged = object.__new__(VerifiedCalibration)
    for name, value in {
        "calibrator": synthetic_calibrator(), "baseline_sha256": F1_BASELINE_SHA256,
        "predictor_source_sha256": F1_CODE_HASHES["predictors.py"],
        "statements_sha256": F1_STATEMENTS_SHA256, "eligible_sha256": F1_ELIGIBLE_SHA256,
        "_proof": object(),
    }.items():
        object.__setattr__(forged, name, value)
    with pytest.raises(CalibrationProvenanceUnavailable, match="disabled"):
        replace(forged, calibrator=synthetic_calibrator())
    with pytest.raises(CalibrationProvenanceUnavailable, match="disabled"):
        verified_forecast(forged, reading(), statement_date=date(2028, 3, 1),
                          context=context(), listing_age_days=10)


@pytest.mark.parametrize("component", [
    "cells", "forms", "cell_counts", "pooled_statements", "slip_left", "slip_right", "slip_mass",
    "slip_n", "slip_iterations", "slip_gap", "ttr_mass", "age_curves", "age_counts",
    "age_fallback_mass", "age_min_cell", "calibrator_min_cell",
])
def test_fingerprint_covers_all_supported_fitted_components(component):
    raw = synthetic_calibrator()
    age_curve = raw.no_date.curves[predictors.ALL_AGES]
    # Separate the original aliased TTR and fallback curves for this test.
    raw.no_date.curves[predictors.ALL_AGES] = replace(
        age_curve, left=age_curve.left.copy(), right=age_curve.right.copy(), mass=age_curve.mass.copy())
    original = snapshot_calibrator(raw)
    changes = {
        "cells": lambda: raw.cells.__setitem__(("exact_day", "first"), raw.pooled),
        "forms": lambda: raw.forms.__setitem__("exact_day", raw.pooled),
        "cell_counts": lambda: raw.cell_counts.__setitem__(("exact_day", "first"), 1),
        "pooled_statements": lambda: object.__setattr__(raw.pooled, "statements", 3),
        "slip_left": lambda: raw.pooled.slip.left.__setitem__(0, -1.),
        "slip_right": lambda: raw.pooled.slip.right.__setitem__(0, 2.),
        "slip_mass": lambda: raw.pooled.slip.mass.__setitem__(slice(None), [.6, .4]),
        "slip_n": lambda: object.__setattr__(raw.pooled.slip, "n", 3),
        "slip_iterations": lambda: object.__setattr__(raw.pooled.slip, "iterations", 2),
        "slip_gap": lambda: object.__setattr__(raw.pooled.slip, "gap", .01),
        "ttr_mass": lambda: raw.pooled.ttr.mass.__setitem__(slice(None), [.6, .4]),
        "age_curves": lambda: raw.no_date.curves.__setitem__("under 90 days", raw.pooled.ttr),
        "age_counts": lambda: raw.no_date.counts.__setitem__("under 90 days", 1),
        "age_fallback_mass": lambda: raw.no_date.curves[predictors.ALL_AGES].mass.__setitem__(slice(None), [.6, .4]),
        "age_min_cell": lambda: object.__setattr__(raw.no_date, "min_cell", 101),
        "calibrator_min_cell": lambda: object.__setattr__(raw, "min_cell", 101),
    }
    changes[component]()
    assert snapshot_calibrator(raw).state_sha256 != original.state_sha256


def test_snapshot_serialization_is_canonical_and_rejects_unsupported_state():
    first, second = synthetic_calibrator(), synthetic_calibrator()
    first.forms.update({"range": first.pooled, "exact_day": first.pooled})
    second.forms.update({"exact_day": second.pooled, "range": second.pooled})
    assert snapshot_calibrator(first) == snapshot_calibrator(second)

    original = synthetic_calibrator()
    swapped = synthetic_calibrator()
    opposite = ">f8" if np.little_endian else "<f8"
    object.__setattr__(swapped.pooled.slip, "mass", swapped.pooled.slip.mass.astype(opposite))
    assert snapshot_calibrator(original).state_sha256 != snapshot_calibrator(swapped).state_sha256

    for bad in (np.array([.5, .5], dtype="f4"), np.array([[.5, .5]], dtype="f8"),
                np.array([.5, 9., .5, 9.], dtype="f8")[::2],
                np.array([.5, .5], dtype=np.dtype("f8", metadata={"tag": "invented"}))):
        raw = synthetic_calibrator()
        object.__setattr__(raw.pooled.slip, "mass", bad)
        with pytest.raises(ValueError, match="array"):
            snapshot_calibrator(raw)
    raw = synthetic_calibrator()
    object.__setattr__(raw, "cells", MappingProxyType({}))
    with pytest.raises(ValueError, match="dictionaries"):
        snapshot_calibrator(raw)
    raw = synthetic_calibrator()
    object.__setattr__(raw, "predict", lambda *_: None)
    with pytest.raises(ValueError, match="unsupported SlipCalibrator"):
        snapshot_calibrator(raw)


def test_snapshot_supports_censored_tails_but_refuses_invalid_curves():
    censored = synthetic_calibrator()
    censored.no_date.curves[predictors.ALL_AGES].right[-1] = np.inf
    assert len(snapshot_calibrator(censored).state_sha256) == 64
    for change in (lambda curve: curve.mass.__setitem__(0, -.1),
                   lambda curve: curve.mass.__setitem__(0, np.nan),
                   lambda curve: curve.mass.__setitem__(0, .9),
                   lambda curve: curve.left.__setitem__(0, curve.right[0]),
                   lambda curve: curve.right.__setitem__(0, np.inf)):
        raw = synthetic_calibrator()
        change(raw.pooled.slip)
        with pytest.raises(ValueError, match="Turnbull"):
            snapshot_calibrator(raw)


def test_equal_six_decimal_digest_does_not_identify_full_fitted_state():
    one, two = synthetic_calibrator(), synthetic_calibrator()
    one.pooled.slip.mass[:] = [.6, .4]
    two.pooled.slip.mass[:] = [.60000002, .39999998]
    f = baseline_inputs().assign(form="exact_day", revision="first", end_days=13.,
                                 h_a=13., h_b=103., age=10., month=3.)
    first, second = models(), models()
    first["rules_plus_slip"], second["rules_plus_slip"] = one, two
    assert baseline_digest(first, f, ["invented-a"]) == baseline_digest(second, f, ["invented-a"])
    s1, s2 = snapshot_calibrator(one), snapshot_calibrator(two)
    assert s1.state_sha256 != s2.state_sha256
    c1, c2 = context(snapshot=s1), context(snapshot=s2)
    p = forecast_reading(s1, reading(), statement_date=c1.statement_date, context=c1, listing_age_days=10)
    q = forecast_reading(s2, reading(), statement_date=c2.statement_date, context=c2, listing_age_days=10)
    assert (p.probabilities.later, q.probabilities.later) == (.6, .60000002)
    assert p.claimed_precision.value == q.claimed_precision.value == "full_precision"
    assert p.provenance == q.provenance == "untrusted_forecast_claim"
    assert p.historical_full_precision_equivalent is q.historical_full_precision_equivalent is None


def test_fit_refuses_non_train_rows_before_calling_fit(monkeypatch):
    called = []
    monkeypatch.setattr(gbm, "fit_all", lambda frame: called.append(True))
    invalid = pd.DataFrame({"period": ["test"], "split": ["test"]}, index=["invented"])
    with pytest.raises(ValueError, match="fit/dev"):
        fit_on_open_train(invalid)
    assert called == []
    valid = pd.DataFrame({"period": ["train"], "split": ["fit"]}, index=["invented"])
    fit_on_open_train(valid)
    assert called == [True]


@pytest.mark.parametrize("column", ["period", "split"])
@pytest.mark.parametrize("missing", [pd.NA, None, np.nan])
@pytest.mark.parametrize("dtype", ["object", "string"])
def test_fit_refuses_missing_period_or_split_before_calling_fit(monkeypatch, column, missing, dtype):
    called = []
    monkeypatch.setattr(gbm, "fit_all", lambda frame: called.append(True))
    frame = pd.DataFrame({"period": ["train", "train"], "split": ["fit", "dev"]},
                         index=["invented-a", "invented-b"])
    frame[column] = pd.Series([frame[column].iloc[0], missing], index=frame.index, dtype=dtype)
    with pytest.raises(ValueError, match="must not be missing"):
        fit_on_open_train(frame)
    assert called == []


def test_fit_refuses_duplicate_split_columns_before_calling_fit(monkeypatch):
    monkeypatch.setattr(gbm, "fit_all", lambda frame: pytest.fail("must not fit"))
    frame = pd.DataFrame([["train", "fit", "dev"]], columns=["period", "split", "split"], index=["invented"])
    with pytest.raises(ValueError, match="unique columns"):
        fit_on_open_train(frame)


# --- A26 governed recomputed-state path -------------------------------------------------------

def _open_frame():
    return pd.DataFrame({"period": ["train", "train"], "split": ["fit", "dev"],
                         "analysis_set": ["dated", "stale"]},
                        index=["invented-a", "invented-b"])


def _recompute(monkeypatch, frame=None):
    import analysis.coling.followup.calibration as module
    monkeypatch.setattr(module.gbm, "fit_all", lambda data: models())
    monkeypatch.setattr(module.predictors, "fit_calibrator", lambda data: synthetic_calibrator())
    return recompute_open_calibration(
        _open_frame() if frame is None else frame, baseline_inputs(), ["invented-b"],
        statements_sha256="a" * 64, eligible_sha256="b" * 64,
        code_sha256={"predictors.py": "c" * 64}, versions={"numpy": "synthetic"})


def test_recomputed_state_binds_provenance_and_forecasts(monkeypatch):
    verified = _recompute(monkeypatch)
    record = verified.state_record()
    assert record["state_sha256"] == verified.snapshot.state_sha256
    assert record["baseline_sha256"] == baseline_digest(models(), baseline_inputs(), ["invented-b"])
    assert record["refit_counts"] == {"dated": 1, "stale": 1}
    assert record["procedure"] == "recomputed-open-fit-dev-v1"
    ctx = context(snapshot=verified.snapshot, item_id="invented")
    forecast = recomputed_forecast(verified, reading(), statement_date=ctx.statement_date,
                                   context=ctx, listing_age_days=ctx.listing_age_days)
    assert forecast.probabilities == forecast_reading(
        verified.snapshot, reading(), statement_date=ctx.statement_date,
        context=ctx, listing_age_days=ctx.listing_age_days).probabilities
    reference = NaturalReference("invented", "v1", (reading(),), True)
    assert recomputed_reference_forecast(
        verified, reference, statement_date=ctx.statement_date,
        context=ctx, listing_age_days=ctx.listing_age_days).probabilities == forecast.probabilities


def test_recomputed_state_cannot_be_certified_by_hash_strings_alone(monkeypatch):
    verified = _recompute(monkeypatch)
    with pytest.raises(CalibrationProvenanceUnavailable, match="recompute_open_calibration"):
        RecomputedCalibration(verified.snapshot, verified.baseline_sha256,
                              verified.provenance, object())


def test_recomputed_state_refuses_sealed_fitting_rows(monkeypatch):
    import analysis.coling.followup.calibration as module
    monkeypatch.setattr(module.gbm, "fit_all", lambda data: pytest.fail("must not fit sealed data"))
    sealed = _open_frame().assign(period=["test", "train"])
    with pytest.raises(ValueError, match="open fit/dev"):
        _recompute(monkeypatch, frame=sealed)


def test_recomputed_state_refuses_malformed_hashes(monkeypatch):
    import analysis.coling.followup.calibration as module
    monkeypatch.setattr(module.gbm, "fit_all", lambda data: models())
    monkeypatch.setattr(module.predictors, "fit_calibrator", lambda data: synthetic_calibrator())
    with pytest.raises(ValueError, match="SHA256"):
        recompute_open_calibration(_open_frame(), baseline_inputs(), ["invented-b"],
                                   statements_sha256="short", eligible_sha256="b" * 64,
                                   code_sha256={}, versions={})
