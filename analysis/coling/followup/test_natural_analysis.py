"""Synthetic checks of N denominators, uncertainty, and completion ranges."""

from dataclasses import fields
from itertools import product

import pytest

from analysis.coling.followup.measurement_sensitivity import ErrorClass
from analysis.coling.followup.natural_analysis import (
    BRIER_GRID, DISPLACEMENT_GRID, NaturalUnit, _conditional,
    summarize_natural, summarize_threshold_grid,
)
from analysis.coling.followup.parsing import parse_natural
from analysis.coling.followup.records import Certainty, NaturalObservation, StatementType
from analysis.coling.followup.test_semantic import (
    context, forecast, identity, observed, reading, reference, returned, synthetic_snapshot,
)
from analysis.coling.followup.semantic import NaturalMeasurement, measure_natural


def unit(item, episode=None):
    return NaturalUnit(item, episode or "episode-" + item, "c" * 64)


def record(item, end, *, item_identity=None, snapshot=None):
    own_identity = identity(item) if item_identity is None else item_identity
    obs = observed(returned(end=end), item=item, item_identity=own_identity)
    ref = reference(reading(), item=item)
    snapshot = snapshot or synthetic_snapshot()
    ctx = context(snapshot=snapshot, item_id=item, item_text_sha256=own_identity.item_text_sha256)
    return measure_natural(ref, obs, own_identity, assigned_context=ctx,
                           reference_forecast=forecast(source=ref, ctx=ctx, snapshot=snapshot),
                           candidate_forecast=forecast(source=obs.parsed.reading, ctx=ctx, snapshot=snapshot))


def test_unconditional_and_conditional_summaries_have_distinct_denominators():
    units = [unit("N1"), unit("N2"), unit("N3")]
    records = [record("N1", "2028-03-28"), record("N2", "2028-03-14"),
               record("N3", "2028-03-29")]
    summary = summarize_natural(units, records, bootstrap_draws=1000)
    assert summary.scientific_status == "exploratory"
    assert summary.calibration_provenance == "unverified_or_unavailable"
    assert summary.historical_full_precision_equivalent is None
    joint = summary.all_notices.material_error_and_low_sensitivity
    conditional = summary.conditional_on_material_error
    assert (joint.denominator, joint.known_true, joint.known_false, joint.unknown) == (3, 1, 2, 0)
    assert (conditional.known_material_errors, conditional.known_low_among_material_errors,
            conditional.known_not_low_among_material_errors) == (2, 1, 1)
    assert conditional.estimate == .5
    assert (conditional.completion_lower, conditional.completion_upper) == (.5, .5)
    assert conditional.wilson_95.low < .5 < conditional.wilson_95.high
    assert summary.bootstrap.joint_95 is not None
    # Some bootstrap resamples have no material errors. Do not drop them silently.
    assert summary.bootstrap.conditional_undefined_draws > 0
    assert summary.bootstrap.conditional_95 is None
    assert summary.bootstrap.conditional_reason == "undefined_bootstrap_replicates"


def test_zero_material_errors_is_undefined_not_zero():
    summary = summarize_natural([unit("N1")], [record("N1", "2028-03-14")], bootstrap_draws=25)
    conditional = summary.conditional_on_material_error
    assert conditional.known_material_errors == 0
    assert conditional.estimate is None
    assert conditional.completion_lower is None and conditional.completion_upper is None
    assert conditional.zero_denominator_possible
    assert conditional.wilson_95 is None and summary.bootstrap.conditional_95 is None


def test_missing_records_give_completion_ranges_not_complete_case_tests():
    summary = summarize_natural([unit("N1"), unit("N2")], [record("N1", "2028-03-28")],
                                bootstrap_draws=25)
    joint = summary.all_notices.material_error_and_low_sensitivity
    conditional = summary.conditional_on_material_error
    assert (joint.known_true, joint.known_false, joint.unknown) == (1, 0, 1)
    assert (joint.minimum_fraction, joint.maximum_fraction) == (.5, 1.)
    assert conditional.estimate is None
    assert (conditional.known_material_errors, conditional.possible_material_errors) == (1, 2)
    assert (conditional.completion_lower, conditional.completion_upper) == (.5, 1.)
    assert conditional.wilson_95 is None
    assert summary.bootstrap.joint_95 is None
    assert summary.bootstrap.joint_reason == "missing_joint_components"


def test_full_fixed_sensitivity_grid_has_each_cell_once():
    units = [unit("N1"), unit("N2")]
    records = [record("N1", "2028-03-28"), record("N2", "2028-03-21")]
    grid = summarize_threshold_grid(units, records)
    assert len(grid) == 20
    assert {(cell.material_days, cell.low_sensitivity_threshold) for cell in grid} == set(
        product(DISPLACEMENT_GRID, BRIER_GRID))
    assert all(cell.all_notices.denominator == 2 and cell.bootstrap is None for cell in grid)
    main = next(cell for cell in grid if (cell.material_days, cell.low_sensitivity_threshold) == (14, .005))
    assert main.all_notices.material_error.known_true == 1
    assert main.all_notices.material_error.known_false == 1
    assert all(cell.literal_period_availability_error == main.literal_period_availability_error
               and cell.mapping_availability_error == main.mapping_availability_error for cell in grid)


def test_availability_totals_preserve_mixed_errors_and_nonunique_reference_uncertainty():
    def semantic_record(item, ref, obs):
        return measure_natural(ref, obs, identity(item))

    records = [
        semantic_record("N1", reference(reading(), item="N1"),
                        observed(returned(statement_type="other"), item="N1")),
        semantic_record("N2", reference(reading(), item="N2"),
                        observed(returned(end="2028-03-28", statement_type="other"), item="N2")),
        semantic_record("N3", reference(reading(kind=StatementType.OTHER), item="N3"),
                        observed(returned(end=None, statement_type="other", certainty="estimated"), item="N3")),
        semantic_record("N4", reference(reading(), reading(end="2028-03-15"), item="N4"),
                        observed(returned(statement_type="other"), item="N4")),
        semantic_record("N5", reference(reading(), reading(end=None, certainty=Certainty.UNDETERMINED), item="N5"),
                        observed(item="N5")),
        semantic_record("N6", reference(reading(), item="N6"),
                        NaturalObservation(parse_natural("{", "invented", finish_reason="stop"), identity("N6"))),
        semantic_record("N8", reference(reading(), item="N8", finalized=False), observed(item="N8")),
    ]
    mixed, nonunique, uncertain = records[1], records[3], records[4]
    assert mixed.semantic.error_class is ErrorClass.END_DATE and mixed.semantic.mapping_availability_error is True
    assert nonunique.semantic.error_class is None and nonunique.semantic.material_end_error is None
    assert nonunique.semantic.missing_reasons == ("reference:reference_endpoint_not_unique",)
    assert (nonunique.semantic.literal_period_availability_error,
            nonunique.semantic.mapping_availability_error) == (False, True)
    assert uncertain.semantic.error_class is None
    assert (uncertain.semantic.literal_period_availability_error, uncertain.semantic.mapping_availability_error) == (
        None, None)

    summary = summarize_natural([unit(f"N{i}") for i in range(1, 9)], records, bootstrap_draws=None)
    literal, mapping = summary.literal_period_availability_error, summary.mapping_availability_error
    assert (literal.denominator, literal.known_true, literal.known_false, literal.unknown) == (8, 1, 3, 4)
    assert (literal.minimum_fraction, literal.maximum_fraction) == (1 / 8, 5 / 8)
    assert (mapping.denominator, mapping.known_true, mapping.known_false, mapping.unknown) == (8, 3, 1, 4)
    assert (mapping.minimum_fraction, mapping.maximum_fraction) == (3 / 8, 7 / 8)


def test_bootstrap_is_seeded_and_independent_of_input_order():
    units = [unit(f"N{i}") for i in range(20)]
    records = [record(f"N{i}", "2028-03-28" if i < 12 else "2028-03-14") for i in range(20)]
    one = summarize_natural(units, records, bootstrap_draws=1000, seed=20261011)
    two = summarize_natural(reversed(units), reversed(records), bootstrap_draws=1000, seed=20261011)
    assert one.bootstrap == two.bootstrap
    assert one.bootstrap.conditional_95 is not None
    assert one.bootstrap.conditional_undefined_draws == 0


def test_summary_refuses_mixed_calibration_states():
    from analysis.coling.followup.calibration import _restore_state, snapshot_calibrator
    original = synthetic_snapshot()
    changed = _restore_state(original.state_bytes)
    changed.pooled.slip.mass[:] = [.4, .6]
    other = snapshot_calibrator(changed)
    records = [record("N1", "2028-03-14", snapshot=original),
               record("N2", "2028-03-14", snapshot=other)]
    with pytest.raises(ValueError, match="one calibration snapshot"):
        summarize_natural([unit("N1"), unit("N2")], records, bootstrap_draws=None)


def test_context_without_forecast_does_not_claim_an_existing_snapshot():
    ref, obs = reference(reading(), item="N1"), observed(item="N1")
    claimed = context(item_id="N1", state_sha256="9" * 64)
    missing = measure_natural(ref, obs, identity("N1"), assigned_context=claimed)
    assert missing.calibration_provenance == "unavailable"
    summary = summarize_natural([unit("N1"), unit("N2")],
                                [missing, record("N2", "2028-03-14")], bootstrap_draws=None)
    assert summary.calibration_provenance == "unverified_or_unavailable"
    assert summary.all_notices.missing_forecast_only == 1


def test_summary_rejects_measurement_subclass_before_overridden_conversion():
    calls = []

    class SpoofMeasurement(NaturalMeasurement):
        def __post_init__(self):
            pass

        def as_measurement(self, **kwargs):
            calls.append(True)
            return None

    original = record("N1", "2028-03-28")
    spoof = SpoofMeasurement(**{item.name: getattr(original, item.name) for item in fields(NaturalMeasurement)})
    with pytest.raises(TypeError, match="exact NaturalMeasurement"):
        summarize_natural([unit("N1")], [spoof], bootstrap_draws=None)
    assert calls == []
    with pytest.raises(TypeError, match="subclasses"):
        NaturalMeasurement.as_measurement(spoof)


@pytest.mark.parametrize("units,records", [
    ([], []),
    ([unit("N1"), unit("N1", "episode-2")], []),
    ([unit("N1", "episode"), unit("N2", "episode")], []),
    ([unit("N1")], [record("N2", "2028-03-14")]),
    ([unit("N1")], [record("N1", "2028-03-14"), record("N1", "2028-03-14")]),
    ([NaturalUnit("N1", "episode", "9" * 64)], [record("N1", "2028-03-14")]),
    ([unit("N1"), unit("N2")], [record("N1", "2028-03-14"),
                                  record("N2", "2028-03-14", item_identity=identity("N2", decoding_sha256="9" * 64))]),
])
def test_identity_duplicates_or_episode_dependence_are_refused(units, records):
    with pytest.raises(ValueError):
        summarize_natural(units, records, bootstrap_draws=None)


@pytest.mark.parametrize("days", [0, -1, True, 1.5])
def test_invalid_threshold_refused_even_without_measurements(days):
    with pytest.raises(ValueError):
        summarize_natural([unit("N1")], [], material_days=days, bootstrap_draws=None)


def test_completion_bounds_match_exhaustive_binary_completions():
    options = (False, True, None)
    pairs = tuple(product(options, options))
    for values in product(pairs, repeat=3):
        candidates = []
        has_zero = False
        possibilities = [tuple(product((False, True) if m is None else (m,),
                                      (False, True) if low is None else (low,)))
                         for m, low in values]
        for completion in product(*possibilities):
            denominator = sum(m for m, _ in completion)
            if denominator == 0:
                has_zero = True
            else:
                candidates.append(sum(m and low for m, low in completion) / denominator)
        result = _conditional(list(values))
        assert result.zero_denominator_possible == has_zero
        assert result.completion_lower == (min(candidates) if candidates else None)
        assert result.completion_upper == (max(candidates) if candidates else None)
