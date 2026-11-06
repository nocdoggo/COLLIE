"""Invented records exercising the complete outcome-free semantic path."""

import json
from dataclasses import asdict, replace
from datetime import date, datetime
from math import nextafter

import numpy as np
import pytest

from analysis.coling import predictors
from analysis.coling.followup.calibration import forecast_reading, forecast_reference, snapshot_calibrator
from analysis.coling.followup.measurement_sensitivity import (
    ErrorClass, ProbabilityPair, aggregate_measurements, exact_brier_perturbation_bounds,
    score_vector_displacement,
)
from analysis.coling.followup.parsing import (
    parse_natural, parse_role, unavailable_natural, unavailable_role,
)
from analysis.coling.followup.records import (
    CalendarInterval, Certainty, NaturalObservation, NaturalReading, NaturalReference,
    PartialReferenceReading, ParseStatus, ReadingIdentity, StatementType, iso_date,
)
from analysis.coling.followup.semantic import (
    CalibrationContext, Forecast, NATURAL_TEMPLATE, SourcePrecision,
    assess_natural, measure_natural,
)


NOTICE = "Current recovery is estimated for 2028-03-14. Review is administrative."


def identity(item="N1", **changes):
    values = dict(item_id=item, model_id="invented-model", template_id=NATURAL_TEMPLATE,
                  provider_route="invented/route", precision="invented",
                  template_sha256="a" * 64, decoding_sha256="b" * 64,
                  item_text_sha256="c" * 64, parser_sha256="d" * 64)
    values.update(changes)
    return ReadingIdentity(**values)


def reading(start="2028-03-01", end="2028-03-14", *, kind=StatementType.RECOVERY,
            certainty=Certainty.ESTIMATED, quote="Current recovery"):
    interval = None if end is None else CalendarInterval(iso_date(start), iso_date(end))
    return NaturalReading(kind, interval, certainty, quote)


def reference(*alternatives, item="N1", finalized=True, reason=None):
    return NaturalReference(item, "reference-v1", tuple(alternatives), finalized, reason)


def returned(start="2028-03-01", end="2028-03-14", *, statement_type="recovery",
             certainty="estimated", quote="Current recovery"):
    interval = None if end is None else {"start": start, "end": end}
    return json.dumps({"statement_type": statement_type, "interval": interval,
                       "certainty": certainty, "quote": quote})


def observed(text=None, *, item="N1", finish="stop", item_identity=None):
    parsed = parse_natural(returned() if text is None else text, NOTICE, finish_reason=finish)
    return NaturalObservation(parsed, identity(item) if item_identity is None else item_identity)


def synthetic_snapshot():
    slip = predictors.Turnbull(np.array([75.5, 100.]), np.array([75.7, 101.]),
                               np.array([.5, .5]), 2, 1, 0.)
    no_date_curve = predictors.Turnbull(np.array([0., 50.]), np.array([10., 60.]),
                                        np.array([.5, .5]), 2, 1, 0.)
    estimate = predictors.Estimate(2, slip, no_date_curve)
    no_date = predictors.AgeTable({predictors.ALL_AGES: no_date_curve}, {}, 100)
    return snapshot_calibrator(predictors.SlipCalibrator({}, {}, estimate, {}, no_date, 100))


def context(*, snapshot=None, **changes):
    snapshot = snapshot or synthetic_snapshot()
    values = dict(earlier_horizon=date(2028, 3, 14), later_horizon=date(2028, 6, 12),
                  form="exact_day", revision_bucket="first", calibration_sha256="e" * 64,
                  baseline_sha256="f" * 64, item_id="N1", item_text_sha256="c" * 64,
                  statement_date=date(2028, 3, 1), listing_age_days=10,
                  state_sha256=snapshot.state_sha256)
    values.update(changes)
    return CalibrationContext(**values)


def forecast(*, source=None, ctx=None, precision=SourcePrecision.FULL, snapshot=None):
    snapshot = snapshot or synthetic_snapshot()
    ctx = ctx or context(snapshot=snapshot)
    source = reading() if source is None else source
    arguments = dict(statement_date=ctx.statement_date, context=ctx, listing_age_days=ctx.listing_age_days)
    result = (forecast_reference(snapshot, source, **arguments) if isinstance(source, NaturalReference)
              else forecast_reading(snapshot, source, **arguments))
    return result if precision is SourcePrecision.FULL else replace(result, claimed_precision=precision)


def test_valid_natural_json_and_quote_diagnostic():
    result = parse_natural(returned(), NOTICE, finish_reason="stop")
    assert result.status is ParseStatus.VALID
    assert result.reading.interval.end == date(2028, 3, 14)
    assert result.quote_valid is True
    hallucinated = parse_natural(returned(quote="not in this notice"), NOTICE, finish_reason="stop")
    assert hallucinated.status is ParseStatus.VALID
    assert hallucinated.quote_valid is False
    empty = parse_natural(returned(quote=""), NOTICE, finish_reason="stop")
    assert empty.status is ParseStatus.VALID and empty.quote_valid is False


@pytest.mark.parametrize("text", [
    "{", "{} trailing", "NaN", '{"x":1,"x":2}',
    '{"statement_type":"recovery","interval":{"start":"2028-03-01",'
    '"end":"2028-03-14","end":"2028-03-15"},"certainty":"estimated","quote":"x"}',
])
def test_invalid_or_duplicate_json_is_a_returned_failure(text):
    parsed = parse_natural(text, NOTICE, finish_reason="stop")
    assert parsed.status is ParseStatus.INVALID_JSON
    result = assess_natural(reference(reading()), NaturalObservation(parsed, identity()), identity())
    assert result.error_class is ErrorClass.RETURNED_FAILURE
    assert result.material_end_error is False
    assert result.task_failure is True


@pytest.mark.parametrize("content", [
    {},
    {"statement_type": "recovery", "interval": None, "certainty": "estimated", "quote": "x", "extra": 1},
    {"statement_type": "recovery", "interval": {"start": "2028-02-30", "end": "2028-03-14"}, "certainty": "estimated", "quote": "x"},
    {"statement_type": "recovery", "interval": {"start": "2028-03-15", "end": "2028-03-14"}, "certainty": "estimated", "quote": "x"},
    {"statement_type": "recovery", "interval": {"start": "20280301", "end": "2028-03-14"}, "certainty": "estimated", "quote": "x"},
    {"statement_type": "recovery", "interval": {"start": "2028-03-01", "end": None}, "certainty": "estimated", "quote": "x"},
    {"statement_type": "recovery", "interval": None, "certainty": "no_statement", "quote": "x"},
    {"statement_type": "none", "interval": None, "certainty": "estimated", "quote": "x"},
    {"statement_type": "none", "interval": {"start": "2028-03-01", "end": "2028-03-14"}, "certainty": "no_statement", "quote": "x"},
    {"statement_type": "recovery", "interval": {"start": "2028-03-01", "end": "2028-03-14"}, "certainty": "undetermined", "quote": "x"},
    {"statement_type": "recovery", "interval": None, "certainty": "estimated", "quote": True},
    {"statement_type": None, "interval": None, "certainty": "estimated", "quote": "x"},
    {"statement_type": "recovery", "interval": {"start": "2028-03-01", "end": "2028-03-14", "other": 1}, "certainty": "estimated", "quote": "x"},
])
def test_invalid_natural_schema_is_a_returned_failure(content):
    parsed = parse_natural(json.dumps(content), NOTICE, finish_reason="stop")
    assert parsed.status is ParseStatus.INVALID_SCHEMA
    result = assess_natural(reference(reading()), NaturalObservation(parsed, identity()), identity())
    assert (result.error_class, result.material_end_error, result.task_failure) == (
        ErrorClass.RETURNED_FAILURE, False, True)


def test_finish_reason_truncation_and_no_response_are_distinct():
    truncated = parse_natural(returned(), NOTICE, finish_reason="length")
    assert truncated.status is ParseStatus.TRUNCATED
    assert assess_natural(reference(reading()), NaturalObservation(truncated, identity()),
                          identity()).material_end_error is False
    unknown_finish = parse_natural(returned(), NOTICE, finish_reason=None)
    assert unknown_finish.status is ParseStatus.INVALID_SCHEMA
    missing = unavailable_natural("transport_failure")
    result = assess_natural(reference(reading()), NaturalObservation(missing, identity()), identity())
    assert result.material_end_error is None and result.error_class is None
    assert result.task_failure is None and result.missing_reasons == ("response:transport_failure",)
    blocked = unavailable_natural("budget_blocked", cap_blocked=True)
    assert blocked.status is ParseStatus.CAP_BLOCKED


def test_unresolved_reference_and_missing_identity_take_precedence_over_failure():
    invalid = parse_natural("{", NOTICE, finish_reason="stop")
    unresolved = reference(reading(), reading(end="2028-03-15"))
    result = assess_natural(unresolved, NaturalObservation(invalid, identity()), identity())
    assert (result.error_class, result.material_end_error, result.task_failure) == (None, None, True)
    assert result.missing_reasons == ("reference:reference_endpoint_not_unique",)
    missing_identity = NaturalObservation(invalid, None, "lost_identity")
    result = assess_natural(reference(reading()), missing_identity, identity())
    assert (result.error_class, result.material_end_error, result.task_failure) == (None, None, None)
    assert result.missing_reasons == ("identity:lost_identity",)
    valid_without_identity = NaturalObservation(parse_natural(returned(), NOTICE, finish_reason="stop"),
                                                 None, "lost_identity")
    unknown = assess_natural(reference(reading()), valid_without_identity, identity())
    assert unknown.literal_period_availability_error is unknown.mapping_availability_error is None


def test_all_missing_reasons_are_preserved_and_unfinalized_is_unknown():
    ref = reference(reading(), finalized=False)
    obs = NaturalObservation(unavailable_natural("network"), None, "identity_not_recorded")
    result = assess_natural(ref, obs, identity())
    assert result.missing_reasons == (
        "reference:reference_not_finalized", "identity:identity_not_recorded", "response:network")
    assert result.material_end_error is None
    adjudicated_unknown = reference(reading(), reason="undecided_by_adjudicator")
    assert assess_natural(adjudicated_unknown, observed(), identity()).material_end_error is None


def test_reference_alternatives_same_end_remain_defensible():
    one = reading(start="2028-03-01")
    two = reading(start="2028-03-05")
    result = assess_natural(reference(one, two), observed(returned(start="2028-03-05")), identity())
    assert result.error_class is ErrorClass.CORRECT
    assert result.material_end_error is False
    mixed_period = reference(one, reading(end=None))
    assert assess_natural(mixed_period, observed(), identity()).material_end_error is None


def test_unique_end_remains_known_when_other_reference_fields_are_unresolved():
    partial = PartialReferenceReading(StatementType.RECOVERY, "finite", None,
                                      date(2028, 3, 14), None, "")
    ref = NaturalReference("N1", "reference-v1", (partial,), True)
    obs, ctx = observed(), context()
    equal = assess_natural(ref, obs, identity())
    assert equal.error_class is None and equal.material_end_error is False
    assert equal.missing_reasons == ("reference:non_endpoint_fields_unresolved",)
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx,
                               reference_forecast=forecast(source=ref, ctx=ctx),
                               candidate_forecast=forecast(source=obs.parsed.reading, ctx=ctx))
    summary = aggregate_measurements(["N1"], [measured.as_measurement()], low_sensitivity_threshold=.005)
    assert summary.unclassified == 1 and summary.material_error.known_false == 1
    assert summary.material_error_and_low_sensitivity.known_false == 1
    displaced = assess_natural(ref, observed(returned(end="2028-03-28")), identity())
    assert displaced.error_class is ErrorClass.END_DATE and displaced.material_end_error is True


def test_period_availability_nulls_and_omitted_fields_are_separate():
    no_period = reading(end=None, certainty=Certainty.UNDETERMINED)
    dated = reference(reading())
    empty_answer = observed(returned(end=None, certainty="undetermined"))
    result = assess_natural(dated, empty_answer, identity())
    assert result.error_class is ErrorClass.PERIOD_AVAILABILITY
    assert result.material_end_error is False and result.absolute_end_displacement_days is None
    result = assess_natural(reference(no_period), empty_answer, identity())
    assert result.error_class is ErrorClass.CORRECT and result.material_end_error is False
    other_null = observed(returned(end=None, certainty="estimated"))
    result = assess_natural(reference(no_period), other_null, identity())
    assert result.error_class is ErrorClass.OMITTED_FIELD_ONLY
    result = assess_natural(reference(no_period), observed(), identity())
    assert result.error_class is ErrorClass.PERIOD_AVAILABILITY


@pytest.mark.parametrize("reference_kind,candidate_kind", [
    (StatementType.RECOVERY, "other"), (StatementType.OTHER, "recovery"),
])
def test_mapping_availability_differs_even_when_both_literal_periods_exist(reference_kind, candidate_kind):
    ref = reference(reading(kind=reference_kind))
    obs = observed(returned(statement_type=candidate_kind))
    result = assess_natural(ref, obs, identity())
    assert result.error_class is ErrorClass.MAPPING_AVAILABILITY
    assert result.literal_period_availability_error is False
    assert result.mapping_availability_error is True
    assert (result.absolute_end_displacement_days, result.material_end_error) == (0, False)
    ctx = context()
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx,
                               reference_forecast=forecast(source=ref, ctx=ctx),
                               candidate_forecast=forecast(source=obs.parsed.reading, ctx=ctx))
    assert measured.reference != measured.candidate
    summary = aggregate_measurements(["N1"], [measured.as_measurement()], low_sensitivity_threshold=1.)
    assert dict(summary.error_class_counts)[ErrorClass.MAPPING_AVAILABILITY] == 1
    assert summary.material_error.known_false == summary.material_error_and_low_sensitivity.known_false == 1


def test_literal_and_mapping_availability_are_independent_for_mixed_errors():
    ref = reference(reading(kind=StatementType.OTHER))
    obs = observed(returned(end=None, statement_type="other", certainty="estimated"))
    result = assess_natural(ref, obs, identity())
    assert result.error_class is ErrorClass.PERIOD_AVAILABILITY
    assert (result.literal_period_availability_error, result.mapping_availability_error) == (True, False)
    displaced = assess_natural(reference(reading()),
                               observed(returned(end="2028-03-28", statement_type="other")), identity())
    assert displaced.error_class is ErrorClass.END_DATE
    assert displaced.material_end_error is True
    assert (displaced.literal_period_availability_error, displaced.mapping_availability_error) == (False, True)


def test_unknown_or_disagreeing_reference_mapping_is_not_silently_correct():
    partial = PartialReferenceReading(None, "finite", None, date(2028, 3, 14), None, "")
    for ref in (reference(partial), reference(reading(), reading(kind=StatementType.OTHER))):
        result = assess_natural(ref, observed(), identity())
        assert result.error_class is None
        assert result.mapping_availability_error is None
        assert result.literal_period_availability_error is False
        assert result.material_end_error is False
        assert result.missing_reasons == ("reference:mapping_availability_unresolved",)
    # A uniquely known literal displacement can still be known even though
    # the separate mapping-availability judgment is unknown.
    displaced = assess_natural(reference(partial), observed(returned(end="2028-03-28")), identity())
    assert displaced.error_class is ErrorClass.END_DATE and displaced.material_end_error is True
    assert displaced.mapping_availability_error is None


def test_nonunique_endpoints_keep_only_availability_facts_common_to_all_alternatives():
    cases = [
        (reference(reading(), reading(end="2028-03-15")), observed(), (False, False)),
        (reference(reading(kind=StatementType.OTHER), reading(end="2028-03-15", kind=StatementType.OTHER)),
         observed(returned(end=None, statement_type="other", certainty="estimated")), (True, False)),
        (reference(reading(kind=StatementType.OTHER), reading(end=None, certainty=Certainty.UNDETERMINED)),
         observed(returned(end=None, statement_type="other", certainty="estimated")), (None, False)),
    ]
    for ref, obs, flags in cases:
        result = assess_natural(ref, obs, identity())
        assert result.error_class is None and result.material_end_error is None
        assert result.missing_reasons == ("reference:reference_endpoint_not_unique",)
        assert (result.literal_period_availability_error, result.mapping_availability_error) == flags


def test_draft_availability_classes_are_not_e7s_registered_four():
    from analysis.coling.followup.e7 import E7Class
    assert {member.value for member in E7Class} == {
        "no_answer", "no_stated_period", "end_too_late", "end_too_early"}
    assert ErrorClass.PERIOD_AVAILABILITY.value not in {member.value for member in E7Class}
    assert ErrorClass.MAPPING_AVAILABILITY.value not in {member.value for member in E7Class}


@pytest.mark.parametrize("end,days,material", [
    ("2028-03-14", 0, False),
    ("2028-03-27", 13, False),
    ("2028-03-28", 14, True),
    ("2028-02-29", 14, True),
    ("2028-02-28", 15, True),
])
def test_displacement_boundaries_across_leap_day(end, days, material):
    obs = observed(returned(start="2028-02-01", end=end))
    result = assess_natural(reference(reading()), obs, identity())
    assert (result.absolute_end_displacement_days, result.material_end_error) == (days, material)
    assert result.error_class is (ErrorClass.END_DATE if days else ErrorClass.OMITTED_FIELD_ONLY)


def test_mixed_errors_follow_end_date_precedence_and_keep_full_days():
    obs = observed(returned(start="2027-12-31", end="2028-01-01",
                            statement_type="next_delivery", certainty="asserted"))
    result = assess_natural(reference(reading()), obs, identity())
    assert result.error_class is ErrorClass.END_DATE and result.material_end_error is True
    assert result.absolute_end_displacement_days == 73
    assert result.at_displacement_threshold(73) is True
    assert result.at_displacement_threshold(74) is False


def test_wrong_condition_or_identity_is_not_a_missing_or_legacy_fallback():
    ref = reference(reading())
    for change in ({"template_id": "literal-v1"}, {"decoding_sha256": "9" * 64},
                   {"item_text_sha256": "9" * 64}, {"model_id": "another-model"},
                   {"provider_route": "another/route"}, {"precision": "another"},
                   {"parser_sha256": "9" * 64}):
        with pytest.raises(ValueError):
            assess_natural(ref, observed(item_identity=identity(**change)), identity())
    with pytest.raises(ValueError):
        assess_natural(reference(reading(), item="N2"), observed(), identity())
    with pytest.raises(ValueError):
        assess_natural(ref, observed(), identity(template_id="literal-v1"))


def test_fixed_horizons_context_and_full_precision_are_mandatory():
    ref, obs = reference(reading()), observed(returned(start="2028-03-01", end="2028-03-29"))
    ctx = context()
    p, q = forecast(source=ref, ctx=ctx), forecast(source=obs.parsed.reading, ctx=ctx)
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx,
                               reference_forecast=p, candidate_forecast=q)
    assert measured.semantic.material_end_error is True
    assert measured.vector_displacement.identical is False
    assert len(measured.brier_bounds.by_label) == 3
    value = measured.brier_bounds.max_absolute_change
    assert aggregate_measurements(["N1"], [measured.as_measurement()],
                                  low_sensitivity_threshold=value).low_sensitivity.known_true == 1
    assert aggregate_measurements(["N1"], [measured.as_measurement()],
                                  low_sensitivity_threshold=nextafter(value, 0)).low_sensitivity.known_false == 1
    for alteration in ({"form": "month_year"}, {"revision_bucket": "second"},
                        {"later_horizon": date(2028, 6, 13)}, {"baseline_sha256": "9" * 64},
                        {"calibration_sha256": "9" * 64}):
        with pytest.raises(ValueError):
            measure_natural(ref, obs, identity(), assigned_context=ctx, reference_forecast=p,
                            candidate_forecast=replace(q, context=context(**alteration)))


def test_forecasts_are_bound_to_assignment_sources_and_recomputed_state():
    ref, obs, ctx = reference(reading()), observed(returned(end="2028-03-29")), context()
    p, q = forecast(source=ref, ctx=ctx), forecast(source=obs.parsed.reading, ctx=ctx)
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx,
                               reference_forecast=p, candidate_forecast=q)
    assert measured.mapping_context == ctx and measured.vector_displacement.linf > 0
    assert measured.calibration_provenance == "recomputed_unverified_snapshot"
    with pytest.raises(ValueError, match="explicit assigned"):
        measure_natural(ref, obs, identity(), reference_forecast=p, candidate_forecast=q)
    with pytest.raises(ValueError, match="reference or reading"):
        measure_natural(ref, obs, identity(), assigned_context=ctx,
                        reference_forecast=q, candidate_forecast=p)
    # Even a different quote with the same date and forecast is a different reading.
    wrong_reading = replace(obs.parsed.reading, quote="another invented quote")
    with pytest.raises(ValueError, match="reference or reading"):
        measure_natural(ref, obs, identity(), assigned_context=ctx, reference_forecast=p,
                        candidate_forecast=forecast(source=wrong_reading, ctx=ctx))
    wrong_reference = reference(reading(start="2028-03-02"))
    with pytest.raises(ValueError, match="reference or reading"):
        measure_natural(ref, obs, identity(), assigned_context=ctx, candidate_forecast=q,
                        reference_forecast=forecast(source=wrong_reference, ctx=ctx))
    with pytest.raises(ValueError, match="probabilities"):
        replace(q, probabilities=ProbabilityPair(.1, .2))
    forged = replace(q)
    object.__setattr__(forged, "probabilities", ProbabilityPair(.1, .2))
    assert forged.provenance == "untrusted_forecast_claim"
    with pytest.raises(ValueError, match="probabilities"):
        measure_natural(ref, obs, identity(), assigned_context=ctx,
                        reference_forecast=p, candidate_forecast=forged)
    with pytest.raises(ValueError, match="probabilities"):
        replace(q, probabilities=ProbabilityPair(-0.0, q.probabilities.later))
    fake_probability = ProbabilityPair(.1, .2)
    with pytest.raises(ValueError, match="not bound"):
        replace(measured, candidate=fake_probability,
                vector_displacement=score_vector_displacement(measured.reference, fake_probability),
                brier_bounds=exact_brier_perturbation_bounds(measured.reference, fake_probability))
    with pytest.raises(ValueError, match="item identity"):
        measure_natural(ref, obs, identity(), assigned_context=context(item_id="N2"),
                        reference_forecast=p, candidate_forecast=q)
    with pytest.raises(ValueError, match="item identity"):
        measure_natural(ref, obs, identity(), assigned_context=context(item_text_sha256="9" * 64),
                        reference_forecast=p, candidate_forecast=q)


def test_direct_and_serialized_forecast_claims_are_untrusted_and_full_values_are_rederived():
    snapshot, source = synthetic_snapshot(), reading()
    ctx = context(snapshot=snapshot)
    claim = forecast(source=source, ctx=ctx, snapshot=snapshot)
    assert claim.provenance == claim.claim_status == "untrusted_forecast_claim"
    serialized = asdict(claim)
    assert serialized["claim_status"] == "untrusted_forecast_claim"
    assert serialized["claimed_precision"] is SourcePrecision.FULL
    assert serialized["historical_full_precision_equivalent"] is None
    assert "precision" not in serialized
    assert claim.historical_full_precision_equivalent is None
    with pytest.raises(ValueError, match="probabilities"):
        Forecast(ProbabilityPair(.1, .2), ctx, SourcePrecision.FULL, source, snapshot)
    with pytest.raises(ValueError, match="snapshot"):
        Forecast(claim.probabilities, ctx, SourcePrecision.FULL, source, None)
    bypassed = object.__new__(Forecast)
    assert bypassed.provenance == "untrusted_forecast_claim"
    mislabeled = replace(claim)
    object.__setattr__(mislabeled, "historical_full_precision_equivalent", True)
    with pytest.raises(ValueError, match="historical full-precision"):
        Forecast.__post_init__(mislabeled)
    rounded = replace(claim, claimed_precision=SourcePrecision.ROUNDED, probabilities=ProbabilityPair(.1, .2))
    assert asdict(rounded)["claim_status"] == "untrusted_forecast_claim"
    ref, obs = reference(reading()), observed()
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx,
                               reference_forecast=forecast(source=ref, ctx=ctx, snapshot=snapshot),
                               candidate_forecast=rounded)
    assert measured.reference is measured.candidate is None
    assert measured.mapping_missing_reason == "rounded_source" and measured.calibration_provenance == "unavailable"


@pytest.mark.parametrize("changes", [
    {"statement_date": date(2028, 3, 10)}, {"listing_age_days": 20}, {"item_id": "N2"},
    {"form": "month_year"}, {"revision_bucket": "second"},
])
def test_forecast_context_changes_are_refused_even_at_the_same_horizons(changes):
    ref, obs, assigned = reference(reading()), observed(), context()
    p = forecast(source=ref, ctx=assigned)
    wrong = context(**changes)
    q = forecast(source=obs.parsed.reading, ctx=wrong)
    with pytest.raises(ValueError, match="assigned item, dates, age, cell, or state"):
        measure_natural(ref, obs, identity(), assigned_context=assigned,
                        reference_forecast=p, candidate_forecast=q)


@pytest.mark.parametrize("changes", [{"statement_date": date(2028, 3, 10)}, {"listing_age_days": 20}])
def test_both_forecasts_wrong_in_the_same_way_still_fail_the_assigned_context(changes):
    ref, obs, assigned = reference(reading()), observed(), context()
    wrong = context(**changes)
    p, q = forecast(source=ref, ctx=wrong), forecast(source=obs.parsed.reading, ctx=wrong)
    with pytest.raises(ValueError, match="assigned item, dates, age, cell, or state"):
        measure_natural(ref, obs, identity(), assigned_context=assigned,
                        reference_forecast=p, candidate_forecast=q)


def test_forecast_entry_point_refuses_date_and_age_outside_its_context():
    snapshot = synthetic_snapshot()
    ctx = context(snapshot=snapshot)
    with pytest.raises(ValueError, match="statement date"):
        forecast_reading(snapshot, reading(), statement_date=date(2028, 3, 10),
                         context=ctx, listing_age_days=ctx.listing_age_days)
    with pytest.raises(ValueError, match="listing age"):
        forecast_reading(snapshot, reading(), statement_date=ctx.statement_date,
                         context=ctx, listing_age_days=20)


def test_subclasses_cannot_spoof_reading_or_context_equality():
    class SpoofReading(NaturalReading):
        def __eq__(self, other):
            return True

    class SpoofContext(CalibrationContext):
        def __eq__(self, other):
            return True

    original, snapshot = reading(), synthetic_snapshot()
    spoof = SpoofReading(original.statement_type, original.interval, original.certainty, original.quote)
    ctx = context(snapshot=snapshot)
    with pytest.raises(TypeError, match="valid reading"):
        forecast_reading(snapshot, spoof, statement_date=ctx.statement_date,
                         context=ctx, listing_age_days=ctx.listing_age_days)
    with pytest.raises(TypeError, match="alternatives"):
        NaturalReference("N1", "v1", (spoof,), True)
    liar = SpoofContext(**{name: getattr(ctx, name) for name in ctx.__dataclass_fields__})
    with pytest.raises(TypeError, match="calibration context"):
        forecast_reading(snapshot, original, statement_date=ctx.statement_date,
                         context=liar, listing_age_days=ctx.listing_age_days)


def test_aggregation_revalidates_a_mutated_measurement():
    ref, obs, ctx = reference(reading()), observed(returned(end="2028-03-29")), context()
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx,
                               reference_forecast=forecast(source=ref, ctx=ctx),
                               candidate_forecast=forecast(source=obs.parsed.reading, ctx=ctx))
    object.__setattr__(measured, "brier_bounds", exact_brier_perturbation_bounds(
        ProbabilityPair(0, 0), ProbabilityPair(1, 1)))
    with pytest.raises(ValueError, match="Brier bounds"):
        measured.as_measurement()


def test_rounded_values_cannot_certify_equality_or_thresholds():
    ref, obs = reference(reading()), observed()
    ctx = context()
    rounded = forecast(source=ref, ctx=ctx, precision=SourcePrecision.ROUNDED)
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx, reference_forecast=rounded,
                               candidate_forecast=forecast(source=obs.parsed.reading, ctx=ctx))
    assert measured.mapping_missing_reason == "rounded_source"
    assert measured.brier_bounds is None and measured.vector_displacement is None
    assert measured.reference is None and measured.candidate is None


@pytest.mark.parametrize("kind", ["no_forecast", "returned_failure", "unavailable", "rounded"])
def test_measurement_retains_sources_and_assignment_even_without_usable_forecasts(kind):
    ref, ctx = reference(reading()), context()
    if kind == "returned_failure":
        obs = NaturalObservation(parse_natural("{", NOTICE, finish_reason="stop"), identity())
    elif kind == "unavailable":
        obs = NaturalObservation(unavailable_natural("synthetic_unavailable"), None, "identity_missing")
    else:
        obs = observed()
    kwargs = {}
    if kind == "rounded":
        kwargs = {"reference_forecast": forecast(source=ref, ctx=ctx, precision=SourcePrecision.ROUNDED),
                  "candidate_forecast": forecast(source=obs.parsed.reading, ctx=ctx)}
    measured = measure_natural(ref, obs, identity(), assigned_context=ctx, **kwargs)
    assert measured._reference_record == ref and measured._observation_record == obs
    assert measured.mapping_context == ctx and measured.calibration_provenance == "unavailable"
    assert measured.reference is measured.candidate is None
    with pytest.raises(ValueError, match="original reference and observation"):
        replace(measured, _reference_record=None)
    with pytest.raises(ValueError, match="original reference and observation"):
        replace(measured, _observation_record=None)
    if kind == "rounded":
        assert measured._reference_forecast is kwargs["reference_forecast"]
        assert measured._candidate_forecast is kwargs["candidate_forecast"]

    # Changing only an ignored quote leaves the semantic class unchanged, but
    # it still changes the bound source and requires a new measurement.
    altered_ref = reference(reading(quote="different invented quote"))
    assert assess_natural(altered_ref, obs, identity()) == measured.semantic
    with pytest.raises(ValueError, match="sources or assignment changed"):
        replace(measured, _reference_record=altered_ref)
    if obs.parsed.status is ParseStatus.VALID:
        altered_obs = observed(returned(quote="different invented quote"))
    else:
        altered_obs = replace(obs, parsed=replace(obs.parsed, reason="different synthetic reason"))
    with pytest.raises(ValueError):
        replace(measured, _observation_record=altered_obs)
    with pytest.raises(ValueError):
        replace(measured, identity=identity(model_id="different-invented-model"))
    with pytest.raises(ValueError, match="sources or assignment changed"):
        replace(measured, mapping_context=context(statement_date=date(2028, 3, 10)))
    with pytest.raises(ValueError, match="mapping reason"):
        replace(measured, mapping_missing_reason="different_reason")


def test_missing_forecast_measurement_detects_in_place_source_mutation_at_aggregation():
    ref, obs = reference(reading()), observed()
    measured = measure_natural(ref, obs, identity())
    with pytest.raises(ValueError, match="sources or assignment changed"):
        replace(measured, mapping_context=context())
    object.__setattr__(ref.alternatives[0], "quote", "mutated invented quote")
    with pytest.raises(ValueError, match="sources or assignment changed"):
        measured.as_measurement()


def test_missing_forecast_path_revalidates_source_and_assignment_structure():
    ref, obs = reference(reading()), observed()
    measured = measure_natural(ref, obs, identity())
    object.__setattr__(obs.parsed, "reason", "invalid for a valid parse")
    with pytest.raises(ValueError, match="valid parse"):
        measured.as_measurement()
    bad_context = context()
    object.__setattr__(bad_context, "state_sha256", "not-a-sha256")
    with pytest.raises(ValueError, match="state_sha256"):
        measure_natural(reference(reading()), observed(), identity(), assigned_context=bad_context)


def test_missing_mapping_and_failures_never_become_zero_forecasts():
    ref = reference(reading())
    ctx = context()
    measured = measure_natural(ref, observed(), identity(), assigned_context=ctx,
                               reference_forecast=forecast(source=ref, ctx=ctx))
    assert measured.reference is not None and measured.candidate is None
    assert measured.mapping_missing_reason == "mapping_unavailable"
    failed = NaturalObservation(parse_natural("{", NOTICE, finish_reason="stop"), identity())
    measured = measure_natural(ref, failed, identity())
    assert measured.semantic.error_class is ErrorClass.RETURNED_FAILURE
    assert measured.semantic.material_end_error is False and measured.brier_bounds is None
    with pytest.raises(ValueError):
        measure_natural(ref, failed, identity(), candidate_forecast=forecast())


def test_synthetic_path_keeps_assigned_denominator_and_three_state_logic():
    ref1 = reference(reading(), item="N1")
    obs1, ctx = observed(returned(end="2028-03-28")), context()
    a = measure_natural(ref1, obs1, identity(), assigned_context=ctx,
                        reference_forecast=forecast(source=ref1, ctx=ctx),
                        candidate_forecast=forecast(source=obs1.parsed.reading, ctx=ctx))
    invalid = NaturalObservation(parse_natural("{", NOTICE, finish_reason="stop"), identity("N2"))
    b = measure_natural(reference(reading(), item="N2"), invalid, identity("N2"))
    missing = NaturalObservation(unavailable_natural("transport_failure"), identity("N3"))
    c = measure_natural(reference(reading(), item="N3"), missing, identity("N3"))
    ids = ["N1", "N2", "N3", "N4"]
    summary = aggregate_measurements(ids, [a.as_measurement(), b.as_measurement(), c.as_measurement()],
                                     low_sensitivity_threshold=.005)
    assert summary.denominator == 4
    assert (summary.material_error_and_low_sensitivity.known_true,
            summary.material_error_and_low_sensitivity.known_false,
            summary.material_error_and_low_sensitivity.unknown) == (1, 1, 2)
    assert (summary.material_error_and_low_sensitivity.minimum_fraction,
            summary.material_error_and_low_sensitivity.maximum_fraction) == (.25, .75)
    assert dict(summary.error_class_counts)[ErrorClass.RETURNED_FAILURE] == 1


def test_role_parser_preserves_invalid_unavailable_and_quote_diagnostics():
    role_notice = "Current recovery is 2028-03-14. The review is 2028-03-20."
    correct = parse_role('{"date":"2028-03-14","quote":"invented quote"}', role_notice,
                         finish_reason="stop")
    assert correct.status is ParseStatus.VALID and correct.reading.target_date == date(2028, 3, 14)
    assert correct.quote_valid is False
    assert parse_role('{"date":null,"quote":""}', role_notice, finish_reason="stop").status is ParseStatus.VALID
    assert parse_role('{"date":null,"quote":"x"}', role_notice, finish_reason="stop").status is ParseStatus.INVALID_SCHEMA
    assert parse_role('{"date":"2028-02-30","quote":"x"}', role_notice, finish_reason="stop").status is ParseStatus.INVALID_SCHEMA
    assert parse_role('{"date":"2028-03-14","date":"2028-03-20","quote":"x"}',
                      role_notice, finish_reason="stop").status is ParseStatus.INVALID_JSON
    assert parse_role('{"date":"2028-03-14","quote":"x"}', role_notice,
                      finish_reason="length").status is ParseStatus.TRUNCATED
    assert unavailable_role("network").status is ParseStatus.UNAVAILABLE


def test_calendar_and_record_type_validation():
    assert iso_date("2028-02-29") == date(2028, 2, 29)
    for value in ("2027-02-29", "2028-2-29", "2028-02-29T00:00:00", "20280229", None):
        with pytest.raises(ValueError):
            iso_date(value)
    with pytest.raises(TypeError):
        CalendarInterval(datetime(2028, 1, 1), date(2028, 1, 1))
    with pytest.raises(ValueError):
        CalendarInterval(date(2028, 2, 1), date(2028, 1, 1))
    with pytest.raises(ValueError):
        identity(parser_sha256="not-a-hash")
    with pytest.raises(ValueError):
        reference()
    with pytest.raises(ValueError):
        context(later_horizon=date(2028, 3, 14))
