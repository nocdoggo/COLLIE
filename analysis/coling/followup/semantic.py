"""Outcome-free adaptation of natural references and returned readings.

The materiality flag is specifically finite end-date displacement. It is not
general semantic correctness and is not an E7 error class.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from datetime import date
from enum import Enum
from math import isfinite
from numbers import Real

from .measurement_sensitivity import (
    BrierBounds, ErrorClass, Measurement, ProbabilityPair, VectorDisplacement,
    classify_reading_error, exact_brier_perturbation_bounds, same_probability_bits, score_vector_displacement,
)
from .records import (
    CalendarInterval, NaturalObservation, NaturalReading, NaturalReference, PartialReferenceReading,
    ParsedNatural, ParseStatus, ReadingIdentity,
    RETURNED_FAILURES, UNAVAILABLE, calibration_end, require_identifier, require_sha256,
)


NATURAL_TEMPLATE = "january-natural-v1"


def _positive_days(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("the end-displacement threshold must be a positive integer")


def _revalidate_reading(reading: NaturalReading | PartialReferenceReading) -> None:
    if type(reading) is NaturalReading:
        NaturalReading.__post_init__(reading)
        if reading.interval is not None:
            CalendarInterval.__post_init__(reading.interval)
    elif type(reading) is PartialReferenceReading:
        PartialReferenceReading.__post_init__(reading)
    else:
        raise TypeError("unsupported natural reading")


def _revalidate_reference(reference: NaturalReference) -> None:
    NaturalReference.__post_init__(reference)
    for alternative in reference.alternatives:
        _revalidate_reading(alternative)


def _revalidate_observation(observation: NaturalObservation) -> None:
    NaturalObservation.__post_init__(observation)
    ParsedNatural.__post_init__(observation.parsed)
    if observation.parsed.reading is not None:
        _revalidate_reading(observation.parsed.reading)
    if observation.identity is not None:
        ReadingIdentity.__post_init__(observation.identity)


@dataclass(frozen=True, slots=True)
class SemanticOutcome:
    error_class: ErrorClass | None
    material_end_error: bool | None
    absolute_end_displacement_days: int | None
    task_failure: bool | None
    missing_reasons: tuple[str, ...]
    # Orthogonal to literal interval availability, including for mixed errors.
    mapping_availability_error: bool | None = None
    literal_period_availability_error: bool | None = None

    def __post_init__(self) -> None:
        if self.error_class is not None and not isinstance(self.error_class, ErrorClass):
            raise TypeError("error_class must be an ErrorClass or None")
        for name in ("material_end_error", "task_failure", "mapping_availability_error",
                     "literal_period_availability_error"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        if type(self.missing_reasons) is not tuple or any(
            not isinstance(reason, str) or not reason.strip() for reason in self.missing_reasons
        ):
            raise TypeError("missing_reasons must be a tuple of nonempty strings")
        if self.error_class is None:
            if self.material_end_error is True or not self.missing_reasons:
                raise ValueError("an unclassified reading must retain its missing reason and cannot be material")
        elif self.material_end_error is None or self.missing_reasons:
            raise ValueError("a classified reading must have known materiality and no missing reason")
        displacement = self.absolute_end_displacement_days
        if displacement is not None and (type(displacement) is not int or displacement < 0):
            raise ValueError("displacement must be a nonnegative integer or None")
        if self.material_end_error is True and (displacement is None or displacement == 0):
            raise ValueError("a material finite-end error needs a positive displacement")
        if self.error_class is ErrorClass.END_DATE and (displacement is None or displacement == 0):
            raise ValueError("an end-date error needs a positive displacement")
        if self.error_class in {ErrorClass.CORRECT, ErrorClass.OMITTED_FIELD_ONLY,
                                ErrorClass.MAPPING_AVAILABILITY,
                                ErrorClass.PERIOD_AVAILABILITY, ErrorClass.RETURNED_FAILURE}:
            if self.material_end_error is not False or displacement not in (None, 0):
                raise ValueError("this class cannot carry a displaced finite end")
        if self.error_class is ErrorClass.RETURNED_FAILURE and self.task_failure is not True:
            raise ValueError("returned failures must be counted as task failures")
        if self.error_class is ErrorClass.MAPPING_AVAILABILITY and self.mapping_availability_error is not True:
            raise ValueError("a mapping-availability class requires a known mapping difference")
        if self.error_class is ErrorClass.PERIOD_AVAILABILITY and self.literal_period_availability_error is not True:
            raise ValueError("a period-availability class requires a literal period difference")

    def at_displacement_threshold(self, days: int) -> bool | None:
        """Re-evaluate only the specified end-displacement criterion."""
        _positive_days(days)
        if self.material_end_error is None:
            return None
        if self.absolute_end_displacement_days is None:
            return False
        return self.absolute_end_displacement_days >= days


def _reference_end(reading: NaturalReading | PartialReferenceReading) -> date | None:
    if isinstance(reading, NaturalReading):
        return None if reading.interval is None else reading.interval.end
    return reading.end if reading.period_status == "finite" else None


def _same_non_end_fields(a: NaturalReading | PartialReferenceReading, b: NaturalReading) -> bool | None:
    """Compare remaining literal fields, allowing unknowns.

    A type difference is not necessarily ignored by the mapping; that is
    checked separately. Quotes are evidence diagnostics, not adjudicated fields.
    """
    if isinstance(a, NaturalReading):
        start_a = a.interval.start if a.interval else None
        type_a, certainty_a, start_known = a.statement_type, a.certainty, True
    else:
        start_a = a.start
        type_a, certainty_a = a.statement_type, a.certainty
        start_known = a.period_status == "none" or a.start is not None
    start_b = b.interval.start if b.interval else None
    checks = ((type_a, b.statement_type, type_a is not None),
              (start_a, start_b, start_known), (certainty_a, b.certainty, certainty_a is not None))
    if any(known and left != right for left, right, known in checks):
        return False
    return True if all(known for _, _, known in checks) else None


def _omitted_field_status(reference: NaturalReference, candidate: NaturalReading) -> bool | None:
    matches = [_same_non_end_fields(alternative, candidate) for alternative in reference.alternatives]
    if any(match is True for match in matches):
        return False
    if all(match is False for match in matches):
        return True
    return None


def _mapping_availability_error(reference: NaturalReference, candidate: NaturalReading) -> bool | None:
    """Compare dated/no-date mapping inputs, retaining ambiguous alternatives."""
    try:
        available = {calibration_end(alternative) is not None for alternative in reference.alternatives}
    except ValueError:
        return None
    if len(available) != 1:
        return None
    return available.pop() != (calibration_end(candidate) is not None)


def _literal_availability_error(reference: NaturalReference, candidate: NaturalReading) -> bool | None:
    """Compare period presence over all alternatives, without selecting an endpoint."""
    available = set()
    for alternative in reference.alternatives:
        if type(alternative) is NaturalReading:
            available.add(alternative.interval is not None)
        elif alternative.period_status == "unresolved":
            return None
        else:
            available.add(alternative.period_status == "finite")
    if len(available) != 1:
        return None
    return available.pop() != (candidate.interval is not None)


def assess_natural(
    reference: NaturalReference,
    observation: NaturalObservation,
    expected_identity: ReadingIdentity,
    *,
    material_days: int = 14,
) -> SemanticOutcome:
    """Apply the ordered finite-end truth table to one assigned N reading.

    The expected identity fixes the model, new template, decoding, notice text,
    and parser. A known incompatible identity is refused rather than treated as
    missing. Multiple adjudicated readings with the same end are preserved:
    matching any such reading is not classified as an omitted-field error.
    Literal period availability and dated/no-date mapping availability are
    recorded separately. The draft class precedence is literal availability,
    finite-end displacement, mapping availability, then omitted fields.
    A nonunique endpoint stays unclassified; an availability flag is retained
    only if all finalized alternatives determine the same flag.
    """
    if type(reference) is not NaturalReference or type(observation) is not NaturalObservation:
        raise TypeError("expected a natural reference and observation")
    if type(expected_identity) is not ReadingIdentity:
        raise TypeError("expected_identity must be a ReadingIdentity")
    _revalidate_reference(reference)
    _revalidate_observation(observation)
    ReadingIdentity.__post_init__(expected_identity)
    _positive_days(material_days)
    if expected_identity.template_id != NATURAL_TEMPLATE:
        raise ValueError("N requires the new natural template identity")
    if reference.item_id != expected_identity.item_id:
        raise ValueError("reference and assigned item identities differ")
    if observation.identity is not None and observation.identity != expected_identity:
        raise ValueError("reading identity differs from the assigned natural condition")

    status = observation.parsed.status
    failure = (None if observation.identity is None or status in UNAVAILABLE
               else status in RETURNED_FAILURES)
    mapping_error = literal_error = None
    if (reference.finalized and reference.unresolved_reason is None
            and observation.identity is not None and status is ParseStatus.VALID):
        candidate = observation.parsed.reading
        literal_error = _literal_availability_error(reference, candidate)
        mapping_error = _mapping_availability_error(reference, candidate)
    missing = []
    if reference.missing_reason is not None:
        missing.append("reference:" + reference.missing_reason)
    if observation.identity is None:
        missing.append("identity:" + observation.identity_missing_reason)
    if status in UNAVAILABLE:
        missing.append("response:" + observation.parsed.reason)
    if missing:
        return SemanticOutcome(None, None, None, failure, tuple(missing), mapping_error, literal_error)

    if status in RETURNED_FAILURES:
        return SemanticOutcome(ErrorClass.RETURNED_FAILURE, False, None, True, ())
    if status is not ParseStatus.VALID:
        raise ValueError("unsupported response state")

    candidate = observation.parsed.reading
    ref = reference.alternatives[0]
    reference_end = _reference_end(ref)
    reference_has_period = reference_end is not None
    candidate_has_period = candidate.interval is not None
    availability_error = reference_has_period != candidate_has_period
    if literal_error is None or literal_error != availability_error:
        raise ValueError("reference alternatives do not determine literal availability")
    if not reference_has_period or not candidate_has_period:
        omitted = False if availability_error else _omitted_field_status(reference, candidate)
        if omitted is None:
            return SemanticOutcome(None, False, None, False, ("reference:non_endpoint_fields_unresolved",),
                                   mapping_error, availability_error)
        kind = classify_reading_error(period_availability_error=availability_error,
                                      end_date_error=False, omitted_field_error=omitted,
                                      mapping_availability_error=mapping_error is True)
        return SemanticOutcome(kind, False, None, False, (), mapping_error, availability_error)

    displacement = abs((candidate.interval.end - reference_end).days)
    omitted = _omitted_field_status(reference, candidate)
    if displacement == 0 and mapping_error is None:
        return SemanticOutcome(None, False, 0, False, ("reference:mapping_availability_unresolved",), None, False)
    if displacement == 0 and mapping_error is False and omitted is None:
        return SemanticOutcome(None, False, 0, False, ("reference:non_endpoint_fields_unresolved",), False, False)
    kind = classify_reading_error(period_availability_error=False,
                                  end_date_error=displacement != 0,
                                  omitted_field_error=bool(omitted),
                                  mapping_availability_error=mapping_error is True)
    return SemanticOutcome(kind, displacement >= material_days, displacement, False, (), mapping_error, False)


class SourcePrecision(str, Enum):
    """A source's claimed precision, not evidence of historical equivalence."""

    FULL = "full_precision"
    ROUNDED = "rounded_source"


def normalized_listing_age(value: Real | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("listing age must be a real number or None")
    age = float(value)
    if not isfinite(age) or age < 0:
        raise ValueError("listing age must be finite and nonnegative")
    return 0.0 if age == 0 else age


@dataclass(frozen=True, slots=True)
class CalibrationContext:
    """A caller-supplied assignment and claimed calibration identities.

    A context alone does not establish that a snapshot exists. State, source
    and baseline hashes are claims, not verified byte-to-frame or historical
    full-precision identities. Real F1 verification is disabled.
    """

    earlier_horizon: date
    later_horizon: date
    form: str
    revision_bucket: str
    calibration_sha256: str
    baseline_sha256: str
    item_id: str
    item_text_sha256: str
    statement_date: date
    listing_age_days: float | None
    state_sha256: str

    def __post_init__(self) -> None:
        if type(self.earlier_horizon) is not date or type(self.later_horizon) is not date:
            raise TypeError("horizons must be dates without times")
        if self.earlier_horizon >= self.later_horizon:
            raise ValueError("the two horizons must be strictly ordered")
        if type(self.statement_date) is not date:
            raise TypeError("statement date must be a date without a time")
        for name in ("item_id", "form", "revision_bucket", "calibration_sha256", "baseline_sha256",
                     "item_text_sha256", "state_sha256"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} must be a string")
        require_identifier(self.item_id, "item_id")
        require_identifier(self.form, "form")
        if self.revision_bucket not in {"first", "second", "third_or_later"}:
            raise ValueError("unknown revision bucket")
        require_sha256(self.calibration_sha256, "calibration_sha256")
        require_sha256(self.baseline_sha256, "baseline_sha256")
        require_sha256(self.item_text_sha256, "item_text_sha256")
        require_sha256(self.state_sha256, "state_sha256")
        object.__setattr__(self, "listing_age_days", normalized_listing_age(self.listing_age_days))


@dataclass(frozen=True, slots=True)
class Forecast:
    """A serializable, untrusted claim; comparisons must rederive it again."""

    probabilities: ProbabilityPair
    context: CalibrationContext
    claimed_precision: SourcePrecision
    source: NaturalReading | NaturalReference
    snapshot: object
    claim_status: str = field(default="untrusted_forecast_claim", init=False)
    historical_full_precision_equivalent: None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if type(self) is not Forecast:
            raise TypeError("Forecast subclasses are not supported")
        if type(self.probabilities) is not ProbabilityPair:
            raise TypeError("probabilities must be a ProbabilityPair")
        ProbabilityPair.__post_init__(self.probabilities)
        if type(self.context) is not CalibrationContext:
            raise TypeError("context must be a CalibrationContext")
        CalibrationContext.__post_init__(self.context)
        if type(self.claimed_precision) is not SourcePrecision:
            raise TypeError("claimed precision must be a SourcePrecision")
        if type(self.claim_status) is not str or self.claim_status != "untrusted_forecast_claim":
            raise ValueError("forecast claim status must remain untrusted")
        if self.historical_full_precision_equivalent is not None:
            raise ValueError("historical full-precision equality is not established")
        if type(self.source) not in (NaturalReading, NaturalReference):
            raise TypeError("a forecast must retain its exact reading or reference")
        if type(self.source) is NaturalReading:
            _revalidate_reading(self.source)
        else:
            _revalidate_reference(self.source)
        # Import lazily: calibration itself imports these record types.
        from .calibration import CalibrationSnapshot, validate_snapshot_forecast
        if type(self.snapshot) is not CalibrationSnapshot or self.snapshot.state_sha256 != self.context.state_sha256:
            raise ValueError("forecast context must bind the actual calibration snapshot")
        CalibrationSnapshot.__post_init__(self.snapshot)
        if type(self.source) is NaturalReference and self.source.item_id != self.context.item_id:
            raise ValueError("reference and calibration item identities differ")
        if self.claimed_precision is SourcePrecision.FULL:
            validate_snapshot_forecast(self)

    @property
    def provenance(self) -> str:
        return "untrusted_forecast_claim"

def _measurement_binding(*values: object) -> str:
    """Detect source replacement; this digest is not evidence of data provenance."""
    from .calibration import CalibrationSnapshot

    records = (ReadingIdentity, NaturalReference, NaturalObservation, NaturalReading, PartialReferenceReading,
               CalendarInterval, ParsedNatural, SemanticOutcome, CalibrationContext, Forecast,
               CalibrationSnapshot, ProbabilityPair)

    def encode(value: object) -> object:
        if value is None:
            return ["none"]
        if isinstance(value, Enum):
            return ["enum", type(value).__module__, type(value).__qualname__, value.value]
        if type(value) in (bool, int, str):
            return [type(value).__name__, value]
        if type(value) is float:
            return ["float", value.hex()]
        if type(value) is date:
            return ["date", value.isoformat()]
        if type(value) is bytes:
            return ["bytes", len(value), hashlib.sha256(value).hexdigest()]
        if type(value) is tuple:
            return ["tuple", [encode(item) for item in value]]
        if type(value) in records:
            return ["record", type(value).__module__, type(value).__qualname__,
                    [[item.name, encode(getattr(value, item.name))] for item in fields(value)]]
        raise TypeError("unsupported measurement source or assignment value")

    payload = json.dumps(encode(values), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _check_assignment(identity: ReadingIdentity, context: CalibrationContext | None, *, required: bool) -> None:
    if context is None:
        if required:
            raise ValueError("an explicit assigned calibration context is required")
        return
    if type(context) is not CalibrationContext:
        raise TypeError("assigned context must be a CalibrationContext")
    CalibrationContext.__post_init__(context)
    if context.item_id != identity.item_id or context.item_text_sha256 != identity.item_text_sha256:
        raise ValueError("assigned calibration context does not match the item identity")


def _check_forecast(forecast: Forecast, source: object, context: CalibrationContext | None) -> None:
    if type(forecast) is not Forecast:
        raise TypeError("forecasts must be exact Forecast values")
    if forecast.context != context:
        raise ValueError("forecast differs from the assigned item, dates, age, cell, or state")
    if forecast.source != source:
        raise ValueError("forecast does not match its assigned reference or reading")
    # Revalidate even a deserialized or bypass-constructed claim. FULL claims
    # are rederived; rounded claims remain untrusted and cannot be compared.
    Forecast.__post_init__(forecast)


@dataclass(frozen=True, slots=True)
class NaturalMeasurement:
    """A draft item bound to its exact sources, even when mapping is missing.

    A retained context is an assignment claim, not proof that any snapshot or
    forecast exists. The binding digest detects changes; it is not provenance.
    """

    identity: ReadingIdentity
    reference_version: str
    semantic: SemanticOutcome
    reference: ProbabilityPair | None
    candidate: ProbabilityPair | None
    vector_displacement: VectorDisplacement | None
    brier_bounds: BrierBounds | None
    mapping_missing_reason: str | None
    mapping_context: CalibrationContext | None = None
    _reference_record: NaturalReference | None = field(default=None, repr=False)
    _observation_record: NaturalObservation | None = field(default=None, repr=False)
    _reference_forecast: Forecast | None = field(default=None, repr=False)
    _candidate_forecast: Forecast | None = field(default=None, repr=False)
    _binding_sha256: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if type(self) is not NaturalMeasurement:
            raise TypeError("NaturalMeasurement subclasses are not supported")
        if type(self.identity) is not ReadingIdentity or type(self.semantic) is not SemanticOutcome:
            raise TypeError("measurement requires its identity and semantic outcome")
        SemanticOutcome.__post_init__(self.semantic)
        if type(self._reference_record) is not NaturalReference or type(self._observation_record) is not NaturalObservation:
            raise ValueError("measurement requires its original reference and observation")
        if type(self.reference_version) is not str:
            raise TypeError("reference_version must be a string")
        require_identifier(self.reference_version, "reference_version")
        if (self.reference_version != self._reference_record.reference_version
                or assess_natural(self._reference_record, self._observation_record, self.identity) != self.semantic):
            raise ValueError("measurement semantic record does not match its source records")
        for value in (self.reference, self.candidate):
            if value is not None and type(value) is not ProbabilityPair:
                raise TypeError("measurement probabilities must be ProbabilityPair values")
            if value is not None:
                ProbabilityPair.__post_init__(value)
        claims = (self._reference_forecast, self._candidate_forecast)
        if any(claim is not None and type(claim) is not Forecast for claim in claims):
            raise TypeError("forecasts must be exact Forecast values")
        _check_assignment(self.identity, self.mapping_context, required=any(claim is not None for claim in claims))
        binding = _measurement_binding(self.identity, self.semantic, self._reference_record, self._observation_record,
                                       self.mapping_context, *claims)
        if type(self._binding_sha256) is not str or self._binding_sha256 != binding:
            raise ValueError("measurement sources or assignment changed; rebuild the measurement")

        unresolved = self.semantic.material_end_error is None or self.semantic.error_class is ErrorClass.RETURNED_FAILURE
        if unresolved:
            if any(claim is not None for claim in claims) or self.reference is not None or self.candidate is not None:
                raise ValueError("no forecast mapping is defined for this reading/reference state")
            reason = "reading_or_reference_unresolved" if self.semantic.material_end_error is None else "returned_failure"
        else:
            sources = (self._reference_record, self._observation_record.parsed.reading)
            for claim, source in zip(claims, sources, strict=True):
                if claim is not None:
                    _check_forecast(claim, source, self.mapping_context)
            rounded = any(claim is not None and claim.claimed_precision is SourcePrecision.ROUNDED for claim in claims)
            if rounded:
                if self.reference is not None or self.candidate is not None:
                    raise ValueError("rounded forecast claims cannot supply comparison probabilities")
                reason = "rounded_source"
            else:
                for probability, claim in zip((self.reference, self.candidate), claims, strict=True):
                    if claim is None:
                        if probability is not None:
                            raise ValueError("measurement probability is not bound to its assigned forecast")
                    elif probability is None or not same_probability_bits(probability, claim.probabilities):
                        raise ValueError("measurement probability is not bound to its assigned forecast")
                reason = None if self.reference is not None and self.candidate is not None else "mapping_unavailable"
        if self.mapping_missing_reason != reason:
            raise ValueError("measurement mapping reason does not match its source records")
        if reason is None:
            if self.vector_displacement != score_vector_displacement(self.reference, self.candidate):
                raise ValueError("vector displacement does not match the forecasts")
            if self.brier_bounds != exact_brier_perturbation_bounds(self.reference, self.candidate):
                raise ValueError("Brier bounds must use all three nested states")
        elif self.vector_displacement is not None or self.brier_bounds is not None:
            raise ValueError("incomplete forecasts cannot carry computed sensitivity")

    @property
    def item_id(self) -> str:
        return self.identity.item_id

    @property
    def calibration_provenance(self) -> str:
        NaturalMeasurement.__post_init__(self)
        return "recomputed_unverified_snapshot" if self.reference is not None or self.candidate is not None else "unavailable"

    def as_measurement(self, *, material_days: int = 14) -> Measurement:
        if type(self) is not NaturalMeasurement:
            raise TypeError("NaturalMeasurement subclasses are not supported")
        NaturalMeasurement.__post_init__(self)
        return Measurement(
            self.item_id, self.semantic.error_class,
            self.semantic.at_displacement_threshold(material_days), self.reference, self.candidate,
            literal_period_availability_error=self.semantic.literal_period_availability_error,
            mapping_availability_error=self.semantic.mapping_availability_error,
        )


def measure_natural(
    reference: NaturalReference,
    observation: NaturalObservation,
    expected_identity: ReadingIdentity,
    *,
    assigned_context: CalibrationContext | None = None,
    reference_forecast: Forecast | None = None,
    candidate_forecast: Forecast | None = None,
) -> NaturalMeasurement:
    """Rederive each claim against the assignment; real-data provenance remains disabled."""
    semantic = assess_natural(reference, observation, expected_identity)
    claims = (reference_forecast, candidate_forecast)
    if any(claim is not None and type(claim) is not Forecast for claim in claims):
        raise TypeError("forecasts must be exact Forecast values")
    _check_assignment(expected_identity, assigned_context, required=any(claim is not None for claim in claims))
    if semantic.material_end_error is None or semantic.error_class is ErrorClass.RETURNED_FAILURE:
        if any(claim is not None for claim in claims):
            raise ValueError("no forecast mapping is defined for this reading/reference state")
        reason = "reading_or_reference_unresolved" if semantic.material_end_error is None else "returned_failure"
        p = q = None
    else:
        for claim, source in zip(claims, (reference, observation.parsed.reading), strict=True):
            if claim is not None:
                _check_forecast(claim, source, assigned_context)
        if any(claim is not None and claim.claimed_precision is SourcePrecision.ROUNDED for claim in claims):
            p = q = None
            reason = "rounded_source"
        else:
            p = reference_forecast.probabilities if reference_forecast is not None else None
            q = candidate_forecast.probabilities if candidate_forecast is not None else None
            reason = None if p is not None and q is not None else "mapping_unavailable"
    binding = _measurement_binding(expected_identity, semantic, reference, observation, assigned_context, *claims)
    return NaturalMeasurement(
        expected_identity, reference.reference_version, semantic, p, q,
        score_vector_displacement(p, q) if reason is None else None,
        exact_brier_perturbation_bounds(p, q) if reason is None else None, reason, assigned_context,
        reference, observation, reference_forecast, candidate_forecast, binding,
    )
