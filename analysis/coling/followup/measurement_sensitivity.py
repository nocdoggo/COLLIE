"""Outcome-free sensitivity of an averaged two-horizon Brier score.

All functions are pure. The signed perturbation is candidate loss minus reference
loss, at the same two fixed horizons. Bounds are exact over the supplied nested
binary label states, subject to floating-point arithmetic. Nothing is rounded.
They do not describe sampling uncertainty or the probability of a label state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import fsum, hypot, isfinite
from numbers import Integral, Real
from typing import Iterable


Label = tuple[int, int]
NESTED_LABELS: tuple[Label, ...] = ((0, 0), (0, 1), (1, 1))


def _number(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, excluding bool")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("item identifiers must be nonempty strings")


@dataclass(frozen=True, slots=True)
class ProbabilityPair:
    """Cumulative recovery probabilities at earlier and later fixed horizons."""

    earlier: float
    later: float

    def __post_init__(self) -> None:
        earlier = _number(self.earlier, "earlier")
        later = _number(self.later, "later")
        if not 0.0 <= earlier <= later <= 1.0:
            raise ValueError("probabilities must satisfy 0 <= earlier <= later <= 1")
        object.__setattr__(self, "earlier", earlier)
        object.__setattr__(self, "later", later)


def _pair(value: ProbabilityPair, name: str) -> None:
    # Frozen records can still be altered through low-level mutation or arrive
    # from untrusted serialization. Validate again at each arithmetic boundary.
    if type(value) is not ProbabilityPair:
        raise TypeError(f"{name} must be an exact ProbabilityPair")
    if type(value.earlier) is not float or type(value.later) is not float:
        raise TypeError(f"{name} must contain canonical floating-point probabilities")
    if not (isfinite(value.earlier) and isfinite(value.later)
            and 0.0 <= value.earlier <= value.later <= 1.0):
        raise ValueError(f"{name} must contain finite, ordered probabilities in [0,1]")


def same_probability_bits(left: ProbabilityPair, right: ProbabilityPair) -> bool:
    """Compare the stored binary floats exactly, including the sign of zero."""
    _pair(left, "left")
    _pair(right, "right")
    return (left.earlier.hex(), left.later.hex()) == (right.earlier.hex(), right.later.hex())


def validate_allowed_labels(labels: Iterable[Label] | None = None) -> tuple[Label, ...]:
    """Validate a nonempty subset and return it in canonical nested-state order.

    Duplicate states are rejected to expose accidental repeated inputs. No state
    is inferred from a probability pair. None permits all three nested states.
    """
    if labels is None:
        return NESTED_LABELS
    found: set[Label] = set()
    for state in labels:
        try:
            one, two = state
        except (TypeError, ValueError) as error:
            raise ValueError("each label state must contain two binary integers") from error
        if any(isinstance(v, bool) or not isinstance(v, Integral) for v in (one, two)):
            raise ValueError("each label state must contain two binary integers")
        label = (int(one), int(two))
        if label not in NESTED_LABELS:
            raise ValueError("labels must be one of (0,0), (0,1), (1,1)")
        if label in found:
            raise ValueError("duplicate label state")
        found.add(label)
    if not found:
        raise ValueError("at least one label state must be allowed")
    return tuple(state for state in NESTED_LABELS if state in found)


@dataclass(frozen=True, slots=True)
class VectorDisplacement:
    earlier_change: float
    later_change: float
    l1: float
    l2: float
    linf: float
    identical: bool


def score_vector_displacement(
    reference: ProbabilityPair, candidate: ProbabilityPair
) -> VectorDisplacement:
    """Signed probability changes and unrounded vector distances; no tolerance is hidden."""
    _pair(reference, "reference")
    _pair(candidate, "candidate")
    a = candidate.earlier - reference.earlier
    b = candidate.later - reference.later
    return VectorDisplacement(a, b, fsum((abs(a), abs(b))), hypot(a, b), max(abs(a), abs(b)),
                              a == 0.0 and b == 0.0)


@dataclass(frozen=True, slots=True)
class BrierBounds:
    lower: float
    upper: float
    max_absolute_change: float
    by_label: tuple[tuple[Label, float], ...]


def exact_brier_perturbation_bounds(
    reference: ProbabilityPair,
    candidate: ProbabilityPair,
    allowed_labels: Iterable[Label] | None = None,
) -> BrierBounds:
    """Extrema of candidate-minus-reference mean Brier loss over allowed states.

    Each state's difference is sum((q-p)*((q-y)+(p-y)))/2. Using the
    factorisation avoids subtraction of two nearly equal squared losses.
    A restricted label subset changes the bound's scope; it is not a default
    claim that unknown outcomes are independently selectable across statements.
    """
    _pair(reference, "reference")
    _pair(candidate, "candidate")
    states = validate_allowed_labels(allowed_labels)
    changes = []
    for state in states:
        terms = [
            (q - p) * fsum((q - y, p - y))
            for p, q, y in zip((reference.earlier, reference.later),
                               (candidate.earlier, candidate.later), state, strict=True)
        ]
        changes.append((state, fsum(terms) / 2.0))
    lower = min(value for _, value in changes)
    upper = max(value for _, value in changes)
    return BrierBounds(lower, upper, max(abs(lower), abs(upper)), tuple(changes))


class ErrorClass(str, Enum):
    """Draft natural-reading classes; these are not E7's registered four classes."""

    CORRECT = "correct"
    OMITTED_FIELD_ONLY = "omitted_field_only"
    MAPPING_AVAILABILITY = "mapping_availability"
    END_DATE = "end_date"
    PERIOD_AVAILABILITY = "period_availability"
    RETURNED_FAILURE = "returned_failure"


def classify_reading_error(
    *, period_availability_error: bool, end_date_error: bool, omitted_field_error: bool,
    mapping_availability_error: bool = False,
) -> ErrorClass:
    """Assign a draft class: literal availability > end > mapping availability > omitted.

    Literal period availability and the calibrator's dated/no-date mapping
    availability are distinct. The precedence is bookkeeping, not severity;
    callers must retain mapping availability separately for mixed errors.
    Unknown judgments remain unclassified outside this function.
    """
    flags = (period_availability_error, end_date_error, omitted_field_error,
             mapping_availability_error)
    if any(type(value) is not bool for value in flags):
        raise TypeError("all error flags must be bool")
    if period_availability_error:
        return ErrorClass.PERIOD_AVAILABILITY
    if end_date_error:
        return ErrorClass.END_DATE
    if mapping_availability_error:
        return ErrorClass.MAPPING_AVAILABILITY
    if omitted_field_error:
        return ErrorClass.OMITTED_FIELD_ONLY
    return ErrorClass.CORRECT


@dataclass(frozen=True, slots=True)
class Measurement:
    """One sampled item; None denotes an explicitly missing component.

    Probability pairs here are arithmetic inputs, not provenance-verified
    forecasts. They are not authorization to score real study data.
    Materiality is supplied by a separately fixed semantic criterion, never
    derived from forecast sensitivity. A correct reading must be marked
    nonmaterial. An unclassified reading may be known nonmaterial when its
    finite end is resolved but other reference fields remain uncertain.
    """

    item_id: str
    error_class: ErrorClass | None
    material_error: bool | None
    reference: ProbabilityPair | None
    candidate: ProbabilityPair | None
    allowed_labels: tuple[Label, ...] = NESTED_LABELS
    literal_period_availability_error: bool | None = None
    mapping_availability_error: bool | None = None

    def __post_init__(self) -> None:
        _identifier(self.item_id)
        if self.error_class is not None and not isinstance(self.error_class, ErrorClass):
            raise TypeError("error_class must be ErrorClass or None")
        if self.material_error is not None and type(self.material_error) is not bool:
            raise TypeError("material_error must be bool or None")
        if self.error_class is None and self.material_error is True:
            raise ValueError("an unclassified reading cannot be a material end-date error")
        if (self.material_error is True and self.error_class in {
            ErrorClass.OMITTED_FIELD_ONLY, ErrorClass.MAPPING_AVAILABILITY,
            ErrorClass.PERIOD_AVAILABILITY, ErrorClass.RETURNED_FAILURE,
        }):
            raise ValueError("this class cannot be a material finite-end error")
        if self.error_class is ErrorClass.CORRECT and self.material_error is not False:
            raise ValueError("a correct reading must have material_error=False")
        for name in ("literal_period_availability_error", "mapping_availability_error"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        if (self.literal_period_availability_error is True
                and self.error_class not in (None, ErrorClass.PERIOD_AVAILABILITY)):
            raise ValueError("literal period availability conflicts with the disjoint class")
        if self.error_class is ErrorClass.PERIOD_AVAILABILITY and self.literal_period_availability_error is False:
            raise ValueError("literal period availability conflicts with the disjoint class")
        if (self.mapping_availability_error is True
                and self.error_class in (ErrorClass.CORRECT, ErrorClass.OMITTED_FIELD_ONLY)):
            raise ValueError("mapping availability conflicts with the disjoint class")
        if self.error_class is ErrorClass.MAPPING_AVAILABILITY and self.mapping_availability_error is False:
            raise ValueError("mapping availability conflicts with the disjoint class")
        for name in ("reference", "candidate"):
            value = getattr(self, name)
            if value is not None:
                _pair(value, name)
        object.__setattr__(self, "allowed_labels", validate_allowed_labels(self.allowed_labels))


@dataclass(frozen=True, slots=True)
class FixedDenominatorRate:
    """Descriptive completion range, not a confidence interval or missingness model."""

    denominator: int
    known_true: int
    known_false: int
    unknown: int
    minimum_fraction: float
    maximum_fraction: float


def _rate(values: Iterable[bool | None]) -> FixedDenominatorRate:
    values = tuple(values)
    yes = sum(value is True for value in values)
    no = sum(value is False for value in values)
    missing = len(values) - yes - no
    return FixedDenominatorRate(len(values), yes, no, missing,
                                yes / len(values), (yes + missing) / len(values))


@dataclass(frozen=True, slots=True)
class MeasurementSummary:
    denominator: int
    low_sensitivity_threshold: float
    # These five coverage counts are disjoint and sum to denominator.
    complete: int
    missing_record: int
    missing_annotation_only: int
    missing_forecast_only: int
    missing_annotation_and_forecast: int
    # Class counts plus unclassified sum to denominator, independently of coverage.
    error_class_counts: tuple[tuple[ErrorClass, int], ...]
    unclassified: int
    material_error: FixedDenominatorRate
    low_sensitivity: FixedDenominatorRate
    material_error_and_low_sensitivity: FixedDenominatorRate
    literal_period_availability_error: FixedDenominatorRate
    mapping_availability_error: FixedDenominatorRate
    calibration_provenance: str = "unverified_arithmetic"
    historical_full_precision_equivalent: None = None


def aggregate_measurements(
    expected_ids: Iterable[str],
    measurements: Iterable[Measurement],
    *,
    low_sensitivity_threshold: float,
) -> MeasurementSummary:
    """Summarise a fixed, nonempty item list without dropping missing components.

    Every expected item remains in every denominator. Extra or repeated item
    identifiers are refused. Low sensitivity means max_absolute_change <= the
    supplied threshold. Its scope is each item's declared allowed label subset.
    The joint event uses three-valued logic: a known False component makes it
    False even if the other component is missing. No conditional error-only
    denominator or complete-case prevalence is silently substituted.
    """
    ids = tuple(expected_ids)
    for item_id in ids:
        _identifier(item_id)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("expected_ids must be nonempty and unique")
    threshold = _number(low_sensitivity_threshold, "low_sensitivity_threshold")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("low_sensitivity_threshold must lie in [0,1]")
    expected = set(ids)
    records = {}
    for record in measurements:
        if type(record) is not Measurement:
            raise TypeError("measurements must contain exact Measurement values")
        Measurement.__post_init__(record)
        if record.item_id not in expected or record.item_id in records:
            raise ValueError("measurement identifiers must be expected and unique")
        records[record.item_id] = record
    coverage = dict.fromkeys(("complete", "missing_record", "missing_annotation_only",
                              "missing_forecast_only", "missing_annotation_and_forecast"), 0)
    classes = dict.fromkeys(ErrorClass, 0)
    unclassified = 0
    material, low, joint, literal_availability, mapping_availability = [], [], [], [], []
    for item_id in ids:
        record = records.get(item_id)
        if record is None:
            coverage["missing_record"] += 1
            unclassified += 1
            material.append(None)
            low.append(None)
            joint.append(None)
            literal_availability.append(None)
            mapping_availability.append(None)
            continue
        if record.error_class is None:
            unclassified += 1
        else:
            classes[record.error_class] += 1
        annotation_missing = record.error_class is None or record.material_error is None
        forecast_missing = record.reference is None or record.candidate is None
        category = {
            (False, False): "complete", (True, False): "missing_annotation_only",
            (False, True): "missing_forecast_only", (True, True): "missing_annotation_and_forecast",
        }[annotation_missing, forecast_missing]
        coverage[category] += 1
        sensitive = None
        if not forecast_missing:
            bounds = exact_brier_perturbation_bounds(record.reference, record.candidate,
                                                     record.allowed_labels)
            sensitive = bounds.max_absolute_change <= threshold
        material.append(record.material_error)
        low.append(sensitive)
        literal_availability.append(record.literal_period_availability_error)
        mapping_availability.append(record.mapping_availability_error)
        joint.append(False if record.material_error is False or sensitive is False
                     else True if record.material_error is True and sensitive is True else None)
    return MeasurementSummary(len(ids), threshold, **coverage,
                               error_class_counts=tuple(classes.items()), unclassified=unclassified,
                               material_error=_rate(material), low_sensitivity=_rate(low),
                               material_error_and_low_sensitivity=_rate(joint),
                               literal_period_availability_error=_rate(literal_availability),
                               mapping_availability_error=_rate(mapping_availability))
