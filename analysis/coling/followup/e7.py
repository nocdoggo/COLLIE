"""Outcome-free E7 class assignment and matched prediction swaps.

This is not an authorized sealed reader and computes no realized loss. E7's
reference is the frozen rule reading, not a new natural-reference adjudication.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from math import isfinite
from numbers import Real
from typing import Any, Iterable

from .measurement_sensitivity import ProbabilityPair
from .records import require_identifier, require_sha256


class E7Class(str, Enum):
    NO_ANSWER = "no_answer"
    NO_STATED_PERIOD = "no_stated_period"
    END_TOO_LATE = "end_too_late"
    END_TOO_EARLY = "end_too_early"


PERIOD_TYPES = frozenset({"recovery", "next_delivery"})
F1_ELIGIBLE_IDS_PREFIX = "a65983839e361c6e"
F1_ELIGIBLE_COUNT = 2593
TASK_E_CONFIRMED_SHA256 = "11e8f925a818141207bc76b4f4366175c3741e006097108ccb2bf60a22b1bd38"
TASK_E_CONFIRMED_COUNT = 100
FROZEN_RULE_SHA256 = "6a810bcb1ae277b9f4f02e0cfcedc80c5011f902cf679012174a6047bec1b28a"
F1_CALIBRATOR_SOURCE_SHA256 = "452254cac0cb7817327ec82f9f555c81ba8c13e7c327dae8c5e55fe3245b3438"
F1_BASELINE_SHA256 = "20347a6ba004d6753d01ed8683b68c0d8f936c5d6aef2e247e5329f39a8727ea"
_CONFIRMED_TOKEN = object()


@dataclass(frozen=True, slots=True)
class ConfirmedReferences:
    item_ids: tuple[str, ...]
    sha256: str
    _proof: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._proof is not _CONFIRMED_TOKEN:
            raise ValueError("confirmed references must come from the verified task E list")


def confirmed_references(raw: bytes) -> ConfirmedReferences:
    """Consume the private task E list bytes without opening a path."""
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != TASK_E_CONFIRMED_SHA256:
        raise ValueError("confirmed-reference list identity differs from the task E record")
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8"), newline=""))
        header = next(rows)
        if header != ["statement_group_id"]:
            raise ValueError("confirmed-reference header differs")
        items = []
        for row in rows:
            if len(row) != 1:
                raise ValueError("confirmed-reference rows need one ID")
            require_identifier(row[0], "confirmed reference ID")
            items.append(row[0])
    except (UnicodeError, StopIteration, csv.Error) as error:
        raise ValueError("confirmed-reference list is malformed") from error
    if len(items) != TASK_E_CONFIRMED_COUNT or len(set(items)) != len(items):
        raise ValueError("confirmed-reference list must contain the registered unique IDs")
    return ConfirmedReferences(tuple(items), TASK_E_CONFIRMED_SHA256, _CONFIRMED_TOKEN)


@dataclass(frozen=True, slots=True)
class RuleReference:
    item_id: str
    end: date

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        if type(self.end) is not date:
            raise TypeError("the E7 rule reference must have one finite calendar end")


@dataclass(frozen=True, slots=True)
class LegacyReading:
    item_id: str
    answer_failed: bool
    statement_type: str | None
    end: date | None

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        if type(self.answer_failed) is not bool:
            raise TypeError("answer_failed must be bool")
        if self.statement_type is not None and not isinstance(self.statement_type, str):
            raise TypeError("statement_type must be text or None")
        if self.end is not None and type(self.end) is not date:
            raise TypeError("end must be a calendar date or None")
        if self.answer_failed:
            if self.statement_type is not None or self.end is not None:
                raise ValueError("a failed answer cannot carry a parsed reading")
        elif self.statement_type not in {"recovery", "next_delivery", "depletion", "discontinuation", "none"}:
            raise ValueError("a parsed answer needs a registered statement type")


def e7_class(reference: RuleReference, reading: LegacyReading) -> E7Class | None:
    if not isinstance(reference, RuleReference) or not isinstance(reading, LegacyReading):
        raise TypeError("E7 requires its rule reference and legacy reading")
    if reference.item_id != reading.item_id:
        raise ValueError("reference and reading item identities differ")
    if reading.answer_failed:
        return E7Class.NO_ANSWER
    if reading.end is None or reading.statement_type not in PERIOD_TYPES:
        return E7Class.NO_STATED_PERIOD
    if reading.end > reference.end:
        return E7Class.END_TOO_LATE
    if reading.end < reference.end:
        return E7Class.END_TOO_EARLY
    return None


@dataclass(frozen=True, slots=True)
class PredictionContext:
    earlier_horizon: date
    later_horizon: date
    form: str
    revision: str
    calibration_sha256: str
    baseline_sha256: str
    quantile_levels: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.earlier_horizon) is not date or type(self.later_horizon) is not date:
            raise TypeError("horizons must be calendar dates")
        if (self.later_horizon - self.earlier_horizon).days != 90:
            raise ValueError("registered E7 horizons must be 90 days apart")
        require_identifier(self.form, "form")
        require_identifier(self.revision, "revision")
        if self.revision not in {"first", "second", "third or later"}:
            raise ValueError("revision must be a registered bucket")
        require_sha256(self.calibration_sha256, "calibration hash")
        require_sha256(self.baseline_sha256, "baseline hash")
        if (self.calibration_sha256 != F1_CALIBRATOR_SOURCE_SHA256
                or self.baseline_sha256 != F1_BASELINE_SHA256):
            raise ValueError("E7 must keep the F1 calibration and baseline identities")
        if (type(self.quantile_levels) is not tuple or not self.quantile_levels
                or any(isinstance(level, bool) or not isinstance(level, Real) or not isfinite(level)
                       or not 0 < level < 1 for level in self.quantile_levels)
                or any(a >= b for a, b in zip(self.quantile_levels, self.quantile_levels[1:]))):
            raise ValueError("quantile levels must be finite, increasing, and between zero and one")
        if self.quantile_levels != (.10, .50, .80, .90, .95):
            raise ValueError("E7 must keep the registered prediction quantile levels")


@dataclass(frozen=True, slots=True)
class Prediction:
    item_id: str
    context: PredictionContext
    probabilities: ProbabilityPair
    quantiles_days: tuple[float, ...]
    source_precision: str

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        if not isinstance(self.context, PredictionContext) or not isinstance(self.probabilities, ProbabilityPair):
            raise TypeError("prediction requires a context and ordered probabilities")
        if self.source_precision not in {"full_precision", "rounded_source"}:
            raise ValueError("prediction source precision must be explicit")
        if (type(self.quantiles_days) is not tuple or len(self.quantiles_days) != len(self.context.quantile_levels)
                or any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value)
                       or not 0 <= value <= 365 for value in self.quantiles_days)
                or any(a > b for a, b in zip(self.quantiles_days, self.quantiles_days[1:]))):
            raise ValueError("quantiles must be finite, ordered, capped, and match the levels")


@dataclass(frozen=True, slots=True)
class SwapResult:
    selected_class: E7Class
    predictions: tuple[Prediction, ...]
    assigned_statements: int
    class_statements: int
    confirmed_reference_statements: int
    confirmed_reference_class_statements: int
    eligible_ids_sha256: str
    confirmed_list_sha256: str
    scientific_status: str = "registered_secondary_setup_outcome_free"


def _index(values: Iterable[Any], expected: set[str], label: str) -> dict[str, Any]:
    result = {}
    for value in values:
        item_id = getattr(value, "item_id", None)
        if item_id not in expected or item_id in result:
            raise ValueError(f"{label} IDs must be assigned and unique")
        result[item_id] = value
    if set(result) != expected:
        raise ValueError(f"{label} must cover the complete assigned scope")
    return result


def swap_class(
    *, eligible_ids: Iterable[str], references: Iterable[RuleReference],
    readings: Iterable[LegacyReading], original_predictions: Iterable[Prediction],
    reference_predictions: Iterable[Prediction], selected_class: E7Class,
    confirmed_reference_list: ConfirmedReferences, eligible_ids_sha256: str, rule_reader_sha256: str,
) -> SwapResult:
    """Swap one F1.11 class, leaving all other matched predictions unchanged."""
    ids = tuple(eligible_ids)
    for item_id in ids:
        require_identifier(item_id, "eligible item ID")
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("eligible scope must be nonempty and unique")
    require_sha256(eligible_ids_sha256, "eligible list hash")
    if rule_reader_sha256 != FROZEN_RULE_SHA256:
        raise ValueError("E7 requires the frozen rule-reader identity")
    observed_ids_hash = hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()
    if (observed_ids_hash != eligible_ids_sha256 or not observed_ids_hash.startswith(F1_ELIGIBLE_IDS_PREFIX)
            or len(ids) != F1_ELIGIBLE_COUNT):
        raise ValueError("eligible IDs differ from the supplied scope identity")
    if not isinstance(selected_class, E7Class):
        raise TypeError("selected_class must be one of the four F1.11 classes")
    expected = set(ids)
    if (not isinstance(confirmed_reference_list, ConfirmedReferences)
            or confirmed_reference_list.sha256 != TASK_E_CONFIRMED_SHA256):
        raise ValueError("the verified private task E list is required")
    confirmed = confirmed_reference_list.item_ids
    if not set(confirmed).issubset(expected):
        raise ValueError("confirmed-reference IDs must lie within the eligible scope")
    refs = _index(references, expected, "reference")
    reads = _index(readings, expected, "reading")
    original = _index(original_predictions, expected, "original prediction")
    replacement = _index(reference_predictions, expected, "reference prediction")
    chosen, class_ids = [], set()
    for item_id in ids:
        if not isinstance(refs[item_id], RuleReference) or not isinstance(reads[item_id], LegacyReading):
            raise TypeError("E7 inputs must use the registered rule and legacy-reading records")
        before, after = original[item_id], replacement[item_id]
        if not isinstance(before, Prediction) or not isinstance(after, Prediction):
            raise TypeError("E7 forecasts must be Prediction records")
        if before.source_precision != "full_precision" or after.source_precision != "full_precision":
            raise ValueError("E7 cannot certify matched scores from rounded prediction exports")
        if before.context != after.context:
            raise ValueError("E7 swaps must preserve target horizons, cell, and quantile levels")
        if e7_class(refs[item_id], reads[item_id]) is selected_class:
            class_ids.add(item_id)
            chosen.append(after)
        else:
            chosen.append(before)
    return SwapResult(selected_class, tuple(chosen), len(ids), len(class_ids), len(confirmed),
                      len(class_ids.intersection(confirmed)), eligible_ids_sha256, confirmed_reference_list.sha256)
