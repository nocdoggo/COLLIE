"""Synthetic checks of probability sensitivity and fixed-denominator accounting."""

from dataclasses import FrozenInstanceError
from itertools import product
from math import inf, nan, nextafter
from random import Random

import pytest

from analysis.coling.followup.measurement_sensitivity import (
    NESTED_LABELS, ErrorClass, Measurement, ProbabilityPair, aggregate_measurements,
    classify_reading_error, exact_brier_perturbation_bounds, score_vector_displacement,
    same_probability_bits, validate_allowed_labels,
)


def direct(p, q, y):
    return sum((b - label) ** 2 - (a - label) ** 2
               for a, b, label in zip((p.earlier, p.later), (q.earlier, q.later), y)) / 2


@pytest.mark.parametrize("pair", [(-.1, .5), (.5, 1.1), (.7, .2), (nan, .5),
                                  (.5, nan), (-inf, .5), (.5, inf)])
def test_invalid_probability_values(pair):
    with pytest.raises(ValueError):
        ProbabilityPair(*pair)


@pytest.mark.parametrize("value", [True, False, "0.5", None, 1 + 0j])
def test_nonnumeric_probabilities(value):
    with pytest.raises(TypeError):
        ProbabilityPair(value, 1)


def test_ordered_boundaries_and_immutability():
    pair = ProbabilityPair(0, 1)
    assert (pair.earlier, pair.later) == (0., 1.)
    assert ProbabilityPair(.4, .4).earlier == .4
    with pytest.raises(FrozenInstanceError):
        pair.earlier = .1


@pytest.mark.parametrize("labels", [[], [(1, 0)], [(2, 2)], [(0,)], [(0, 0, 1)],
                                    [(False, True)], [(0., 1.)], [None],
                                    [(0, 1), (0, 1)]])
def test_invalid_allowed_labels(labels):
    with pytest.raises(ValueError):
        validate_allowed_labels(labels)


def test_subset_order_and_extreme_loss_changes():
    assert validate_allowed_labels([(1, 1), (0, 0)]) == ((0, 0), (1, 1))
    p, q = ProbabilityPair(0, 0), ProbabilityPair(1, 1)
    whole = exact_brier_perturbation_bounds(p, q)
    assert (whole.lower, whole.upper, whole.max_absolute_change) == (-1, 1, 1)
    assert whole.by_label == (((0, 0), 1.), ((0, 1), 0.), ((1, 1), -1.))
    single = exact_brier_perturbation_bounds(p, q, [(0, 1)])
    assert single.lower == single.upper == single.max_absolute_change == 0


def test_analytic_bounds_against_exhaustive_nested_states():
    rng = Random(20261011)
    subsets = [tuple(y for y, keep in zip(NESTED_LABELS, flags) if keep)
               for flags in product((False, True), repeat=3) if any(flags)]
    for _ in range(100):
        p = ProbabilityPair(*sorted((rng.random(), rng.random())))
        q = ProbabilityPair(*sorted((rng.random(), rng.random())))
        for subset in subsets:
            bound = exact_brier_perturbation_bounds(p, q, subset)
            values = [direct(p, q, y) for y in subset]
            assert bound.lower == pytest.approx(min(values), abs=1e-15)
            assert bound.upper == pytest.approx(max(values), abs=1e-15)
            assert bound.max_absolute_change == pytest.approx(max(map(abs, values)), abs=1e-15)
            reverse = exact_brier_perturbation_bounds(q, p, subset)
            assert reverse.lower == -bound.upper
            assert reverse.upper == -bound.lower


def test_identical_vectors_and_precision_near_one():
    p = ProbabilityPair(.123456789123, .987654321987)
    assert exact_brier_perturbation_bounds(p, p).max_absolute_change == 0
    assert score_vector_displacement(p, p).identical
    a = nextafter(1., 0.)
    bound = exact_brier_perturbation_bounds(ProbabilityPair(a, a), ProbabilityPair(1, 1), [(1, 1)])
    assert bound.upper == -(1. - a) ** 2
    assert bound.upper < 0  # Do not erase a small value by display rounding or cancellation.


def test_vector_distances_and_no_implicit_near_equality():
    d = score_vector_displacement(ProbabilityPair(.1, .8), ProbabilityPair(.4, .4))
    assert (d.earlier_change, d.later_change) == pytest.approx((.3, -.4))
    assert (d.l1, d.l2, d.linf) == pytest.approx((.7, .5, .4))
    p, q = ProbabilityPair(0, 0), ProbabilityPair(0, nextafter(0, 1))
    assert not score_vector_displacement(p, q).identical
    with pytest.raises(TypeError):
        exact_brier_perturbation_bounds((0, 1), q)


@pytest.mark.parametrize("bad_earlier,bad_later", [
    (nan, .5), (-.1, .5), (.7, .2), (.5, 1.1), (True, .5), (0, .5),
])
def test_arithmetic_and_aggregation_reject_mutated_probability_pairs(bad_earlier, bad_later):
    good = ProbabilityPair(.2, .5)
    bad = ProbabilityPair(.2, .5)
    object.__setattr__(bad, "earlier", bad_earlier)
    object.__setattr__(bad, "later", bad_later)
    for operation in (exact_brier_perturbation_bounds, score_vector_displacement, same_probability_bits):
        with pytest.raises((TypeError, ValueError)):
            operation(good, bad)
        with pytest.raises((TypeError, ValueError)):
            operation(bad, good)
    with pytest.raises((TypeError, ValueError)):
        Measurement("invented", ErrorClass.END_DATE, True, good, bad)
    record = Measurement("invented", ErrorClass.END_DATE, True, good, good)
    object.__setattr__(record, "candidate", bad)
    with pytest.raises((TypeError, ValueError)):
        aggregate_measurements(["invented"], [record], low_sensitivity_threshold=.005)


def test_arithmetic_rejects_probability_pair_subclasses():
    class UnsupportedPair(ProbabilityPair):
        pass

    ordinary = ProbabilityPair(0, 1)
    subclass = UnsupportedPair(0, 1)
    with pytest.raises(TypeError):
        exact_brier_perturbation_bounds(ordinary, subclass)
    with pytest.raises(TypeError):
        score_vector_displacement(subclass, ordinary)
    with pytest.raises(TypeError):
        Measurement("invented", ErrorClass.END_DATE, True, ordinary, subclass)


@pytest.mark.parametrize("kind", [ErrorClass.OMITTED_FIELD_ONLY, ErrorClass.MAPPING_AVAILABILITY,
                                  ErrorClass.PERIOD_AVAILABILITY, ErrorClass.RETURNED_FAILURE])
def test_non_end_date_classes_cannot_claim_a_material_finite_end_error(kind):
    with pytest.raises(ValueError, match="material"):
        Measurement("invented", kind, True, None, None)


def test_disjoint_error_class_precedence_for_every_flag_combination():
    counts = dict.fromkeys(ErrorClass, 0)
    for availability, end, mapping, omitted in product((False, True), repeat=4):
        result = classify_reading_error(period_availability_error=availability,
                                        end_date_error=end, omitted_field_error=omitted,
                                        mapping_availability_error=mapping)
        expected = (ErrorClass.PERIOD_AVAILABILITY if availability else ErrorClass.END_DATE
                    if end else ErrorClass.MAPPING_AVAILABILITY if mapping
                    else ErrorClass.OMITTED_FIELD_ONLY if omitted else ErrorClass.CORRECT)
        assert result is expected
        counts[result] += 1
    assert counts[ErrorClass.RETURNED_FAILURE] == 0
    assert sorted(counts.values()) == [0, 1, 1, 2, 4, 8]
    with pytest.raises(TypeError):
        classify_reading_error(period_availability_error=False, end_date_error=None,
                               omitted_field_error=False)


def item(name, kind=ErrorClass.END_DATE, material=True, reference=None, candidate=None):
    return Measurement(name, kind, material, reference, candidate)


def test_fixed_denominator_missingness_and_three_valued_joint_event():
    zero, one = ProbabilityPair(0, 0), ProbabilityPair(1, 1)
    records = [
        item("blind", reference=zero, candidate=zero),
        item("not_blind", reference=zero, candidate=one),
        item("correct_missing_forecast", ErrorClass.CORRECT, False),
        item("unknown_but_not_blind", None, None, zero, one),
        item("unknown_both", None, None),
        item("materiality_unknown", ErrorClass.OMITTED_FIELD_ONLY, None, zero, zero),
    ]
    ids = [record.item_id for record in records] + ["absent"]
    summary = aggregate_measurements(ids, records, low_sensitivity_threshold=0)
    assert summary.denominator == 7
    assert summary.calibration_provenance == "unverified_arithmetic"
    assert summary.historical_full_precision_equivalent is None
    assert (summary.complete, summary.missing_record, summary.missing_annotation_only,
            summary.missing_forecast_only, summary.missing_annotation_and_forecast) == (2, 1, 2, 1, 1)
    assert sum(n for _, n in summary.error_class_counts) + summary.unclassified == 7
    assert summary.unclassified == 3
    joint = summary.material_error_and_low_sensitivity
    assert (joint.known_true, joint.known_false, joint.unknown) == (1, 3, 3)
    assert (joint.minimum_fraction, joint.maximum_fraction) == (1 / 7, 4 / 7)
    assert summary.material_error.known_true == 2
    assert summary.material_error.known_false == 1
    assert summary.material_error.unknown == 4
    assert summary.low_sensitivity.known_true == 2
    assert summary.low_sensitivity.known_false == 2
    assert summary.low_sensitivity.unknown == 3


def test_availability_rates_use_independent_three_state_fixed_denominators():
    records = [
        Measurement("mixed", ErrorClass.END_DATE, True, None, None,
                    literal_period_availability_error=False, mapping_availability_error=True),
        Measurement("period", ErrorClass.PERIOD_AVAILABILITY, False, None, None,
                    literal_period_availability_error=True, mapping_availability_error=False),
        Measurement("unknown", None, None, None, None, mapping_availability_error=False),
    ]
    summary = aggregate_measurements(["mixed", "period", "unknown", "absent"], records,
                                     low_sensitivity_threshold=0)
    literal, mapping = summary.literal_period_availability_error, summary.mapping_availability_error
    assert (literal.denominator, literal.known_true, literal.known_false, literal.unknown) == (4, 1, 1, 2)
    assert (literal.minimum_fraction, literal.maximum_fraction) == (.25, .75)
    assert (mapping.denominator, mapping.known_true, mapping.known_false, mapping.unknown) == (4, 1, 2, 1)
    assert (mapping.minimum_fraction, mapping.maximum_fraction) == (.25, .5)
    with pytest.raises(ValueError, match="literal period"):
        Measurement("bad", ErrorClass.END_DATE, True, None, None, literal_period_availability_error=True)
    with pytest.raises(ValueError, match="mapping availability"):
        Measurement("bad", ErrorClass.OMITTED_FIELD_ONLY, False, None, None, mapping_availability_error=True)


def test_availability_completion_ranges_cover_all_three_state_combinations():
    options = (False, True, None)
    for literal_values, mapping_values in product(product(options, repeat=3), repeat=2):
        records = [Measurement(str(i), None, None, None, None,
                               literal_period_availability_error=literal_values[i],
                               mapping_availability_error=mapping_values[i]) for i in range(3)]
        summary = aggregate_measurements(["0", "1", "2", "missing"], records, low_sensitivity_threshold=0)
        for values, rate in ((literal_values, summary.literal_period_availability_error),
                             (mapping_values, summary.mapping_availability_error)):
            yes = sum(value is True for value in values)
            no = sum(value is False for value in values)
            unknown = 4 - yes - no
            assert (rate.denominator, rate.known_true, rate.known_false, rate.unknown) == (4, yes, no, unknown)
            assert (rate.minimum_fraction, rate.maximum_fraction) == (yes / 4, (yes + unknown) / 4)


def test_all_missing_and_inclusive_unrounded_threshold():
    empty = aggregate_measurements(["a", "b"], [], low_sensitivity_threshold=.02)
    assert empty.missing_record == 2
    assert empty.material_error_and_low_sensitivity.minimum_fraction == 0
    assert empty.material_error_and_low_sensitivity.maximum_fraction == 1
    p, q = ProbabilityPair(.2, .4), ProbabilityPair(.3, .5)
    threshold = exact_brier_perturbation_bounds(p, q).max_absolute_change
    record = item("a", reference=p, candidate=q)
    same = aggregate_measurements(["a"], [record], low_sensitivity_threshold=threshold)
    below = aggregate_measurements(["a"], [record], low_sensitivity_threshold=nextafter(threshold, 0))
    assert same.material_error_and_low_sensitivity.known_true == 1
    assert below.material_error_and_low_sensitivity.known_false == 1


def test_restricted_labels_have_explicit_effect_on_low_sensitivity():
    record = Measurement("a", ErrorClass.END_DATE, True, ProbabilityPair(0, 0),
                         ProbabilityPair(1, 1), ((0, 1),))
    assert aggregate_measurements(["a"], [record], low_sensitivity_threshold=0).low_sensitivity.known_true == 1


def test_returned_failure_is_false_for_finite_end_displacement_but_sensitivity_unknown():
    record = Measurement("failed", ErrorClass.RETURNED_FAILURE, False,
                         ProbabilityPair(.2, .8), None)
    summary = aggregate_measurements(["failed"], [record], low_sensitivity_threshold=.005)
    assert summary.denominator == 1
    assert summary.missing_forecast_only == 1
    assert (summary.complete, summary.missing_record, summary.missing_annotation_only,
            summary.missing_annotation_and_forecast, summary.unclassified) == (0, 0, 0, 0, 0)
    assert dict(summary.error_class_counts)[ErrorClass.RETURNED_FAILURE] == 1
    assert sum(count for _, count in summary.error_class_counts) == 1
    for rate in (summary.material_error, summary.material_error_and_low_sensitivity):
        assert (rate.known_true, rate.known_false, rate.unknown) == (0, 1, 0)
        assert rate.minimum_fraction == rate.maximum_fraction == 0
    assert (summary.low_sensitivity.known_true, summary.low_sensitivity.known_false,
            summary.low_sensitivity.unknown) == (0, 0, 1)
    assert (summary.low_sensitivity.minimum_fraction, summary.low_sensitivity.maximum_fraction) == (0, 1)


@pytest.mark.parametrize("threshold", [-.01, 1.01, nan, inf])
def test_invalid_thresholds(threshold):
    with pytest.raises(ValueError):
        aggregate_measurements(["a"], [], low_sensitivity_threshold=threshold)


def test_denominator_and_measurement_identity_validation():
    for ids, records in [([], []), (["a", "a"], []), (["a"], [item("b")]),
                         (["a"], [item("a"), item("a")]), ([""], [])]:
        with pytest.raises(ValueError):
            aggregate_measurements(ids, records, low_sensitivity_threshold=0)
    with pytest.raises(TypeError):
        aggregate_measurements(["a"], [None], low_sensitivity_threshold=0)
    with pytest.raises(TypeError):
        aggregate_measurements(["a"], [], low_sensitivity_threshold=True)


def test_aggregate_rejects_measurement_subclasses():
    class SpoofMeasurement(Measurement):
        pass

    spoof = SpoofMeasurement("a", ErrorClass.CORRECT, False, None, None)
    with pytest.raises(TypeError, match="exact Measurement"):
        aggregate_measurements(["a"], [spoof], low_sensitivity_threshold=0)


@pytest.mark.parametrize("kind,material", [(ErrorClass.CORRECT, True),
                                          (ErrorClass.CORRECT, None), (None, True)])
def test_inconsistent_annotation_is_rejected(kind, material):
    with pytest.raises(ValueError):
        item("a", kind, material)


def test_unclassified_other_fields_can_coexist_with_known_nonmaterial_end():
    record = item("a", None, False, ProbabilityPair(.2, .4), ProbabilityPair(.2, .4))
    summary = aggregate_measurements(["a"], [record], low_sensitivity_threshold=0)
    assert summary.unclassified == 1 and summary.missing_annotation_only == 1
    assert summary.material_error.known_false == 1
    assert summary.material_error_and_low_sensitivity.known_false == 1


def test_single_class_and_boolean_materiality_are_enforced():
    with pytest.raises(TypeError):
        item("a", [ErrorClass.END_DATE, ErrorClass.OMITTED_FIELD_ONLY])
    with pytest.raises(TypeError):
        item("a", material=1)
