"""Draft outcome-free calibration mechanics; not authorized for real use.

No paths or outcome files are opened. F1 verification is disabled: caller
hash claims are not a verified byte-to-frame projection or fitting provenance.
Snapshots identify a recomputed state, not historical full-precision equality.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import isfinite
from numbers import Real
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from analysis.coling import forms, gbm, predictors
from .measurement_sensitivity import ProbabilityPair, same_probability_bits
from .records import CalendarInterval, Certainty, NaturalReading, NaturalReference, StatementType, calibration_end
from .semantic import CalibrationContext, Forecast, SourcePrecision, normalized_listing_age


F1_BASELINE_SHA256 = "20347a6ba004d6753d01ed8683b68c0d8f936c5d6aef2e247e5329f39a8727ea"
F1_STATEMENTS_SHA256 = "bcadc718f4e4e6c05330483196fd63bb8696ecf600e50d1cee8de0b0dc79cdbb"
F1_ELIGIBLE_SHA256 = "8c12fc3e940f250e0a3426ef74355177431273db02736357a946dabb97ef7482"
F1_PREDICTORS_SHA256 = "452254cac0cb7817327ec82f9f555c81ba8c13e7c327dae8c5e55fe3245b3438"
F1_EVALUATOR_SHA256 = "efa033ae67dff7fb8bc9c13dd4a5e047c4c42e9cda92f9d373b09eb9c868cb93"
F1_CODE_HASHES = {
    "evaluate.py": F1_EVALUATOR_SHA256,
    "dataset.py": "2fe95d355d3d5c773310e4cc38de5988c3e19af9bfd63356b4db3cb088f9e3c0",
    "forms.py": "b99502d348ea82bece639ef2da62ebc90914b6d04dc185d6bfcb805b6bab69fd",
    "gbm.py": "1e5eb3791e90b587cd9d7d4d78d101e71ea59dea061b730b6527cf85c54bfce3",
    "power.py": "6948ee5f2f27e111d3b611b414b51a5c2216eb776f2b42bc3e19c9cacc7087fc",
    "predictors.py": F1_PREDICTORS_SHA256,
    "read.py": "54d171783601e72994f960cbe7b5adba157f6061ba3c9a1da30fd23e23be244f",
    "launch.py": "db06bf2900f149e90c97155c7d4060d40cf21b5aa8ca92c234768022181298d5",
    "sealed_counts.py": "22d592e0b65b339b1c25669fbf7b93d6089f6f7c5677213773a4c42709cd61b4",
}
F1_VERSIONS = {"numpy": "2.5.2", "pandas": "2.3.3", "scikit_learn": "1.9.0"}
F1_REFIT_COUNTS = {"dated": 2497, "stale": 23, "tbd": 250, "silent": 306}
BASELINE_FEATURES = frozenset({"form", "revision", "end_days", "h_a", "h_b", "age",
                               "month", "reason", "category", "company", "text"})
CONTROL_SHIFTS = (0, -7, 7, -14, 14, -30, 30, -90, 90)


def fit_on_open_train(frame: pd.DataFrame) -> dict[str, Any]:
    """Fit a caller-labelled train fit/dev frame; this does not prove provenance."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or not frame.index.is_unique:
        raise ValueError("fitting data must be a nonempty frame with unique statement IDs")
    if not frame.columns.is_unique:
        raise ValueError("fitting data must have unique columns")
    if "period" not in frame or "split" not in frame:
        raise ValueError("fitting data must identify its original period and split")
    if frame[["period", "split"]].isna().any().any():
        raise ValueError("fitting period and split must not be missing")
    if not frame["period"].eq("train").all() or not frame["split"].isin(("fit", "dev")).all():
        raise ValueError("fitting is restricted to open fit/dev data")
    return gbm.fit_all(frame)


def _prediction_text(predictions: Mapping[str, pd.DataFrame]) -> str:
    table = pd.concat(dict(predictions), axis=1)
    table.columns = [f"{name}.{column}" for name, column in table.columns]
    return table.to_csv(float_format="%.6f", lineterminator="\n", index_label="statement_group_id")


def baseline_digest(
    fitted: Mapping[str, Any], eligible: pd.DataFrame, probe_ids: Sequence[str],
) -> str:
    """Hash six-decimal predictions, not input provenance or full fitted state."""
    if set(fitted) != set(gbm.PREDICTORS):
        raise ValueError("every original model-free predictor is required")
    if not isinstance(eligible, pd.DataFrame) or set(eligible.columns) != BASELINE_FEATURES:
        raise ValueError("baseline inputs must contain exactly the permitted first-sight features")
    if eligible.empty or not eligible.index.is_unique:
        raise ValueError("baseline inputs need unique nonempty item IDs")
    probe_ids = tuple(probe_ids)
    if len(set(probe_ids)) != len(probe_ids) or not set(probe_ids).issubset(set(eligible.index)):
        raise ValueError("probe IDs must be unique members of the eligible set")
    predictions = {name: fitted[name].predict(eligible) for name in gbm.PREDICTORS}
    probe = fitted["base_rate"].predict(eligible.loc[list(probe_ids)].assign(h_a=90.0, h_b=180.0))
    for name, value in (*predictions.items(), ("base_at_probe", probe)):
        expected_index = eligible.index if name != "base_at_probe" else eligible.loc[list(probe_ids)].index
        if (not isinstance(value, pd.DataFrame) or not value.index.equals(expected_index)
                or tuple(value.columns) != tuple(predictors.PREDICTION_COLUMNS)
                or not np.isfinite(value.to_numpy(dtype=float)).all()):
            raise ValueError("a baseline prediction has incompatible rows, columns, or values")
    text = _prediction_text(predictions) + _prediction_text({"base_rate_at_probe_horizons": probe})
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_STATE_SCHEMA = "collie-slip-calibrator-state-v1"


def _fields(value: object, cls: type, names: tuple[str, ...]) -> None:
    # Frozen predictor dataclasses still have a __dict__. Extra instance
    # attributes could override methods and are not part of the known schema.
    if type(value) is not cls or set(vars(value)) != set(names):
        raise ValueError(f"unsupported {cls.__name__} state")


def _object(value: object, names: tuple[str, ...]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("invalid serialized calibration state")
    return value


def _integer(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError("calibration counts and thresholds must be nonnegative integers")
    return value


def _array(value: object) -> dict[str, Any]:
    # The frozen fitter creates 1-D float64 arrays. Refuse other representations
    # rather than silently lose dtype, metadata, shape, or subclass behaviour.
    if (type(value) is not np.ndarray or value.ndim != 1 or value.size == 0
            or value.dtype.kind != "f" or value.dtype.itemsize != 8
            or value.dtype.fields is not None or value.dtype.metadata is not None
            or not value.flags.c_contiguous or value.strides != (value.dtype.itemsize,)):
        raise ValueError("unsupported calibration array dtype or shape")
    return {"dtype": value.dtype.str, "shape": list(value.shape), "bytes": value.tobytes(order="C").hex()}


def _decode_array(value: object) -> np.ndarray:
    item = _object(value, ("dtype", "shape", "bytes"))
    if type(item["dtype"]) is not str or type(item["shape"]) is not list or len(item["shape"]) != 1:
        raise ValueError("invalid calibration array metadata")
    length = _integer(item["shape"][0], positive=True)
    dtype = np.dtype(item["dtype"])
    if dtype.kind != "f" or dtype.itemsize != 8 or dtype.fields is not None or dtype.metadata is not None:
        raise ValueError("unsupported calibration array dtype")
    if type(item["bytes"]) is not str:
        raise ValueError("invalid calibration array bytes")
    raw = bytes.fromhex(item["bytes"])
    if len(raw) != length * dtype.itemsize:
        raise ValueError("calibration array byte length does not match its shape")
    return np.frombuffer(raw, dtype=dtype).copy()


def _curve(value: predictors.Turnbull) -> dict[str, Any]:
    _fields(value, predictors.Turnbull, ("left", "right", "mass", "n", "iterations", "gap"))
    left, right, mass = _array(value.left), _array(value.right), _array(value.mass)
    if left["shape"] != right["shape"] or left["shape"] != mass["shape"]:
        raise ValueError("calibration curve arrays must have the same shape")
    if (not np.isfinite(value.left).all() or np.isnan(value.right).any()
            or (value.left >= value.right).any()
            or (value.left[1:] < value.right[:-1]).any()
            or not np.isfinite(value.mass).all() or (value.mass < 0).any()
            or abs(float(value.mass.sum()) - 1.0) > 1e-12):
        raise ValueError("invalid fitted Turnbull intervals or probability mass")
    if type(value.gap) is not float or not isfinite(value.gap):
        raise ValueError("calibration convergence gap must be a finite float")
    return {"left": left, "right": right, "mass": mass,
            "n": _integer(value.n, positive=True), "iterations": _integer(value.iterations, positive=True),
            "gap": value.gap.hex()}


def _decode_curve(value: object) -> predictors.Turnbull:
    item = _object(value, ("left", "right", "mass", "n", "iterations", "gap"))
    if type(item["gap"]) is not str:
        raise ValueError("invalid calibration convergence gap")
    gap = float.fromhex(item["gap"])
    if not isfinite(gap):
        raise ValueError("calibration convergence gap must be finite")
    return predictors.Turnbull(_decode_array(item["left"]), _decode_array(item["right"]),
                               _decode_array(item["mass"]), _integer(item["n"], positive=True),
                               _integer(item["iterations"], positive=True), gap)


def _estimate(value: predictors.Estimate) -> dict[str, Any]:
    _fields(value, predictors.Estimate, ("statements", "slip", "ttr"))
    return {"statements": _integer(value.statements, positive=True),
            "slip": _curve(value.slip), "ttr": _curve(value.ttr)}


def _decode_estimate(value: object) -> predictors.Estimate:
    item = _object(value, ("statements", "slip", "ttr"))
    return predictors.Estimate(_integer(item["statements"], positive=True),
                               _decode_curve(item["slip"]), _decode_curve(item["ttr"]))


def _mapping(value: object, encode: Any, *, cells: bool = False) -> list[list[Any]]:
    if type(value) is not dict:
        raise ValueError("calibration mappings must be ordinary dictionaries")
    for key in value:
        valid = (type(key) is tuple and len(key) == 2 and all(type(part) is str for part in key)
                 if cells else type(key) is str)
        if not valid:
            raise ValueError("unsupported calibration mapping key")
    return [[list(key) if cells else key, encode(value[key])] for key in sorted(value)]


def _decode_mapping(value: object, decode: Any, *, cells: bool = False) -> dict[Any, Any]:
    if type(value) is not list:
        raise ValueError("invalid serialized calibration mapping")
    result = {}
    for entry in value:
        if type(entry) is not list or len(entry) != 2:
            raise ValueError("invalid serialized calibration entry")
        key = entry[0]
        if cells:
            if type(key) is not list or len(key) != 2 or any(type(part) is not str for part in key):
                raise ValueError("invalid serialized calibration cell")
            key = tuple(key)
        elif type(key) is not str:
            raise ValueError("invalid serialized calibration key")
        if key in result:
            raise ValueError("duplicate calibration mapping key")
        result[key] = decode(entry[1])
    return result


def _age_table(value: predictors.AgeTable) -> dict[str, Any]:
    _fields(value, predictors.AgeTable, ("curves", "counts", "min_cell"))
    if type(value.curves) is not dict or predictors.ALL_AGES not in value.curves:
        raise ValueError("the no-date table needs its pooled fallback curve")
    return {"curves": _mapping(value.curves, _curve), "counts": _mapping(value.counts, _integer),
            "min_cell": _integer(value.min_cell, positive=True)}


def _decode_age_table(value: object) -> predictors.AgeTable:
    item = _object(value, ("curves", "counts", "min_cell"))
    return predictors.AgeTable(_decode_mapping(item["curves"], _decode_curve),
                               _decode_mapping(item["counts"], _integer),
                               _integer(item["min_cell"], positive=True))


def _serialize_calibrator(value: predictors.SlipCalibrator) -> bytes:
    _fields(value, predictors.SlipCalibrator, ("cells", "forms", "pooled", "cell_counts", "no_date", "min_cell"))
    data = {"schema": _STATE_SCHEMA, "cells": _mapping(value.cells, _estimate, cells=True),
            "forms": _mapping(value.forms, _estimate), "pooled": _estimate(value.pooled),
            "cell_counts": _mapping(value.cell_counts, _integer, cells=True),
            "no_date": _age_table(value.no_date), "min_cell": _integer(value.min_cell, positive=True)}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _restore_state(payload: bytes) -> predictors.SlipCalibrator:
    try:
        data = _object(json.loads(payload.decode("utf-8")),
                       ("schema", "cells", "forms", "pooled", "cell_counts", "no_date", "min_cell"))
        if data["schema"] != _STATE_SCHEMA:
            raise ValueError("unknown calibration state schema")
        value = predictors.SlipCalibrator(
            _decode_mapping(data["cells"], _decode_estimate, cells=True),
            _decode_mapping(data["forms"], _decode_estimate), _decode_estimate(data["pooled"]),
            _decode_mapping(data["cell_counts"], _integer, cells=True),
            _decode_age_table(data["no_date"]), _integer(data["min_cell"], positive=True),
        )
        if _serialize_calibrator(value) != payload:
            raise ValueError("noncanonical or incomplete calibration state")
        return value
    except (KeyError, TypeError, UnicodeError, OverflowError, json.JSONDecodeError) as error:
        raise ValueError("invalid serialized calibration state") from error


@dataclass(frozen=True, slots=True)
class CalibrationSnapshot:
    """Immutable copied fitted state; this is *not* proof of F1 provenance."""

    state_bytes: bytes = field(repr=False)
    state_sha256: str

    def __post_init__(self) -> None:
        if (type(self.state_bytes) is not bytes or type(self.state_sha256) is not str
                or hashlib.sha256(self.state_bytes).hexdigest() != self.state_sha256):
            raise ValueError("calibration snapshot bytes and state hash differ")
        _restore_state(self.state_bytes)


def snapshot_calibrator(calibrator: predictors.SlipCalibrator) -> CalibrationSnapshot:
    """Deep-copy and fingerprint the supported complete fitted state, without F1 claims.

    Unknown subclasses, extra instance attributes, mappings, dtypes and shapes
    fail closed. The immutable bytes have no aliases to the supplied arrays.
    Code/runtime identity and the provenance of the original fit remain unproved.
    """
    original = _serialize_calibrator(calibrator)
    copied = _serialize_calibrator(copy.deepcopy(calibrator))
    if original != copied or _serialize_calibrator(calibrator) != original:
        raise ValueError("calibration state changed while it was copied")
    return CalibrationSnapshot(copied, hashlib.sha256(copied).hexdigest())


class CalibrationProvenanceUnavailable(RuntimeError):
    """Actual source-byte-to-frame and fitting provenance is not established."""


@dataclass(frozen=True, slots=True)
class VerifiedCalibration:
    """Reserved F1 capability: construction is disabled until provenance exists."""

    calibrator: predictors.SlipCalibrator
    baseline_sha256: str
    predictor_source_sha256: str
    statements_sha256: str
    eligible_sha256: str
    _proof: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        raise CalibrationProvenanceUnavailable("F1 verification is disabled: actual input and fit provenance is unavailable")


def verify_f1_baseline(
    fitted: Mapping[str, Any], eligible: pd.DataFrame, probe_ids: Sequence[str],
    *, record: Mapping[str, Any], observed_hashes: Mapping[str, str],
) -> VerifiedCalibration:
    """Fail closed until actual bytes, projections, source and refit are bound.

    Supplying matching hash strings, sizes, or rounded predictions cannot
    establish these identities. No evaluator or protected input is opened here.
    """
    raise CalibrationProvenanceUnavailable("F1 verification is disabled: actual input and fit provenance is unavailable")


def forecast_reading(
    calibrator: CalibrationSnapshot, reading: NaturalReading, *,
    statement_date: date, context: CalibrationContext, listing_age_days: Real | None,
) -> Forecast:
    """Map one reading from an unverified snapshot; intended for synthetic checks."""
    if type(reading) is not NaturalReading:
        raise TypeError("a valid reading is required")
    probabilities = _forecast_end(calibrator, calibration_end(reading), statement_date=statement_date,
                                  context=context, listing_age_days=listing_age_days)
    return Forecast(probabilities, context, SourcePrecision.FULL, reading, calibrator)


def _forecast_end(
    calibrator: CalibrationSnapshot, period_end: date | None, *, statement_date: date,
    context: CalibrationContext, listing_age_days: Real | None,
) -> ProbabilityPair:
    if type(calibrator) is not CalibrationSnapshot:
        raise TypeError("an immutable calibration snapshot is required")
    if type(statement_date) is not date or type(context) is not CalibrationContext:
        raise TypeError("a statement date and calibration context are required")
    if (hashlib.sha256(calibrator.state_bytes).hexdigest() != calibrator.state_sha256
            or context.state_sha256 != calibrator.state_sha256):
        raise ValueError("calibration snapshot and assigned state differ")
    if statement_date != context.statement_date:
        raise ValueError("statement date differs from the assigned context")
    age = normalized_listing_age(listing_age_days)
    if age != context.listing_age_days:
        raise ValueError("listing age differs from the assigned context")
    if context.form not in forms.FORM_NAMES:
        raise ValueError("unknown original form class")
    revision = "third or later" if context.revision_bucket == "third_or_later" else context.revision_bucket
    frame = pd.DataFrame({
        "form": [context.form], "revision": [revision], "end_days": [np.nan],
        "h_a": [(context.earlier_horizon - statement_date).days],
        "h_b": [(context.later_horizon - statement_date).days], "age": [np.nan if age is None else age],
    }, index=["item"])
    end = float((period_end - statement_date).days) if period_end is not None else np.nan
    # Restore a new model for each call; no caller can mutate its backing state.
    predicted = _restore_state(calibrator.state_bytes).predict(
        frame, pd.Series([end], index=frame.index, dtype=float))
    return ProbabilityPair(float(predicted.loc["item", "p_a"]), float(predicted.loc["item", "p_b"]))


def forecast_reference(
    calibrator: CalibrationSnapshot, reference: NaturalReference, *,
    statement_date: date, context: CalibrationContext, listing_age_days: Real | None,
) -> Forecast:
    """Map an independently adjudicated endpoint without inventing its start or certainty."""
    end = _reference_mapping_end(reference, context)
    probabilities = _forecast_end(calibrator, end, statement_date=statement_date,
                                  context=context, listing_age_days=listing_age_days)
    return Forecast(probabilities, context, SourcePrecision.FULL, reference, calibrator)


def _reference_mapping_end(reference: NaturalReference, context: CalibrationContext) -> date | None:
    if type(reference) is not NaturalReference or reference.missing_reason is not None:
        raise ValueError("a unique resolved reference endpoint is required")
    if type(context) is not CalibrationContext or reference.item_id != context.item_id:
        raise ValueError("reference and assigned calibration item differ")
    ends = {calibration_end(alternative) for alternative in reference.alternatives}
    if len(ends) != 1:
        raise ValueError("reference alternatives do not share one calibration input")
    return ends.pop()


def validate_snapshot_forecast(forecast: Forecast) -> None:
    """Rederive a full-precision claim; this does not establish input provenance."""
    if type(forecast) is not Forecast:
        raise TypeError("a bound forecast is required")
    if forecast.claimed_precision is not SourcePrecision.FULL:
        raise ValueError("rounded forecast claims cannot be validated as full precision")
    context = forecast.context
    if type(forecast.source) is NaturalReading:
        end = calibration_end(forecast.source)
    elif type(forecast.source) is NaturalReference:
        end = _reference_mapping_end(forecast.source, context)
    else:
        raise TypeError("unsupported forecast source")
    expected = _forecast_end(forecast.snapshot, end, statement_date=context.statement_date,
                             context=context, listing_age_days=context.listing_age_days)
    if not same_probability_bits(forecast.probabilities, expected):
        raise ValueError("forecast probabilities do not match the bound snapshot and reading")


def verified_forecast(
    verified: VerifiedCalibration, reading: NaturalReading, *, statement_date: date,
    context: CalibrationContext, listing_age_days: Real | None,
) -> Forecast:
    raise CalibrationProvenanceUnavailable("verified F1 forecasts are disabled until input and fit provenance exists")


def verified_reference_forecast(
    verified: VerifiedCalibration, reference: NaturalReference, *, statement_date: date,
    context: CalibrationContext, listing_age_days: Real | None,
) -> Forecast:
    raise CalibrationProvenanceUnavailable("verified F1 forecasts are disabled until input and fit provenance exists")


def shifted_reading(reading: NaturalReading, days: int) -> NaturalReading:
    """Translate the complete interval, giving the specified end-date shift."""
    if not isinstance(reading, NaturalReading) or reading.interval is None:
        raise ValueError("a finite reading is required")
    if type(days) is not int or days not in CONTROL_SHIFTS:
        raise ValueError("shift must belong to the fixed control grid")
    shifted = CalendarInterval(reading.interval.start + timedelta(days=days),
                               reading.interval.end + timedelta(days=days))
    return NaturalReading(reading.statement_type, shifted, reading.certainty, reading.quote)


def omitted_field_control(reading: NaturalReading) -> NaturalReading:
    """Change only fields ignored by the mapping while keeping a finite end."""
    if (not isinstance(reading, NaturalReading) or reading.interval is None
            or reading.statement_type not in {StatementType.RECOVERY, StatementType.NEXT_DELIVERY}):
        raise ValueError("an eligible finite reading is required")
    other_type = (StatementType.NEXT_DELIVERY if reading.statement_type is StatementType.RECOVERY
                  else StatementType.RECOVERY)
    other_certainty = (Certainty.ASSERTED if reading.certainty is Certainty.ESTIMATED else Certainty.ESTIMATED)
    return NaturalReading(other_type, CalendarInterval(reading.interval.end, reading.interval.end),
                          other_certainty, reading.quote)
