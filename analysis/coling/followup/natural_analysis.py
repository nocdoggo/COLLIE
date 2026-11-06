"""Fixed-denominator, outcome-free summaries for the N sample.

Completion ranges are not sampling intervals. No per-item actual outcome or
outcome-restricted state is accepted by these functions. Calibration contexts
are unverified claims; these draft summaries are not authorized for real use.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from random import Random
from statistics import NormalDist
from typing import Iterable

from .measurement_sensitivity import FixedDenominatorRate, MeasurementSummary, aggregate_measurements
from .records import require_identifier, require_sha256
from .semantic import NATURAL_TEMPLATE, NaturalMeasurement


DISPLACEMENT_GRID = (1, 7, 14, 30)
BRIER_GRID = (0.0, 0.001, 0.005, 0.01, 0.02)


@dataclass(frozen=True, slots=True)
class NaturalUnit:
    item_id: str
    episode_id: str
    item_text_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        require_identifier(self.episode_id, "episode_id")
        require_sha256(self.item_text_sha256, "item_text_sha256")


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class ConditionalRate:
    """Low sensitivity among material errors, with missing-data completion ranges."""

    known_material_errors: int
    possible_material_errors: int
    known_low_among_material_errors: int
    known_not_low_among_material_errors: int
    unknown_sensitivity_among_material_errors: int
    unknown_materiality: int
    estimate: float | None
    completion_lower: float | None
    completion_upper: float | None
    zero_denominator_possible: bool
    wilson_95: Interval | None


@dataclass(frozen=True, slots=True)
class BootstrapIntervals:
    draws: int
    seed: int
    joint_95: Interval | None
    conditional_95: Interval | None
    conditional_undefined_draws: int | None
    joint_reason: str | None
    conditional_reason: str | None


@dataclass(frozen=True, slots=True)
class NaturalSummary:
    material_days: int
    low_sensitivity_threshold: float
    all_notices: MeasurementSummary
    conditional_on_material_error: ConditionalRate
    bootstrap: BootstrapIntervals | None
    scientific_status: str = "exploratory"
    calibration_provenance: str = "unverified_or_unavailable"
    historical_full_precision_equivalent: None = None

    @property
    def literal_period_availability_error(self) -> FixedDenominatorRate:
        return self.all_notices.literal_period_availability_error

    @property
    def mapping_availability_error(self) -> FixedDenominatorRate:
        return self.all_notices.mapping_availability_error


def _inputs(
    units: Iterable[NaturalUnit], measurements: Iterable[NaturalMeasurement]
) -> tuple[tuple[NaturalUnit, ...], dict[str, NaturalMeasurement]]:
    units = tuple(units)
    if not units or any(type(unit) is not NaturalUnit for unit in units):
        raise ValueError("the N sample must contain NaturalUnit values")
    ids = [unit.item_id for unit in units]
    episodes = [unit.episode_id for unit in units]
    if len(set(ids)) != len(ids) or len(set(episodes)) != len(episodes):
        raise ValueError("N requires unique items and one item per episode")
    expected = {unit.item_id: unit for unit in units}
    records = {}
    condition = None
    calibration_condition = None
    for measurement in measurements:
        if type(measurement) is not NaturalMeasurement:
            raise TypeError("measurements must contain exact NaturalMeasurement values")
        NaturalMeasurement.__post_init__(measurement)
        item_id = measurement.item_id
        if item_id not in expected or item_id in records:
            raise ValueError("measurement identifiers must be expected and unique")
        identity = measurement.identity
        if identity.template_id != NATURAL_TEMPLATE:
            raise ValueError("N requires the natural template identity")
        if identity.item_text_sha256 != expected[item_id].item_text_sha256:
            raise ValueError("assigned and returned notice text identities differ")
        signature = (identity.model_id, identity.provider_route, identity.precision,
                     identity.template_id, identity.template_sha256,
                     identity.decoding_sha256, identity.parser_sha256)
        if condition is None:
            condition = signature
        elif signature != condition:
            raise ValueError("N measurements must share one model and execution identity")
        # An assignment can name a state hash without any snapshot or usable
        # forecast. Only rederived probabilities establish a snapshot here.
        if measurement.reference is not None or measurement.candidate is not None:
            context = measurement.mapping_context
            mapping = (context.state_sha256, context.calibration_sha256, context.baseline_sha256)
            if calibration_condition is None:
                calibration_condition = mapping
            elif mapping != calibration_condition:
                raise ValueError("N measurements must share one calibration snapshot and source claims")
        records[item_id] = measurement
    return tuple(sorted(units, key=lambda unit: unit.item_id)), records


def _values(
    units: tuple[NaturalUnit, ...], records: dict[str, NaturalMeasurement],
    material_days: int, threshold: float,
) -> list[tuple[bool | None, bool | None]]:
    values = []
    for unit in units:
        record = records.get(unit.item_id)
        if record is None:
            values.append((None, None))
            continue
        material = record.semantic.at_displacement_threshold(material_days)
        low = None if record.brier_bounds is None else record.brier_bounds.max_absolute_change <= threshold
        values.append((material, low))
    return values


def _joint(material: bool | None, low: bool | None) -> bool | None:
    if material is False or low is False:
        return False
    if material is True and low is True:
        return True
    return None


def _wilson(successes: int, total: int) -> Interval:
    z = NormalDist().inv_cdf(0.975)
    p = successes / total
    z2 = z * z
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    radius = z * sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / (1 + z2 / total)
    return Interval(max(0.0, center - radius), min(1.0, center + radius))


def _conditional(values: list[tuple[bool | None, bool | None]]) -> ConditionalRate:
    a = sum(m is True and low is True for m, low in values)
    b = sum(m is True and low is False for m, low in values)
    c = sum(m is True and low is None for m, low in values)
    d = sum(m is None and low is True for m, low in values)
    e = sum(m is None and low is False for m, low in values)
    f = sum(m is None and low is None for m, low in values)
    known_errors = a + b + c
    unknown_materiality = d + e + f
    possible_errors = known_errors + unknown_materiality
    estimate = a / known_errors if known_errors and not unknown_materiality and not c else None
    wilson = _wilson(a, known_errors) if estimate is not None else None

    # Extremize over all missing materiality and sensitivity components, but
    # only among completions where the conditional denominator is nonzero.
    low_denom = a + b + c + e + f
    lower = a / low_denom if low_denom else (1.0 if d else None)
    high_denom = a + b + c + d + f
    upper = (a + c + d + f) / high_denom if high_denom else (0.0 if e else None)
    return ConditionalRate(known_errors, possible_errors, a, b, c, unknown_materiality,
                           estimate, lower, upper, known_errors == 0, wilson)


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = probability * (len(ordered) - 1)
    left = int(index)
    if left == len(ordered) - 1:
        return ordered[left]
    return ordered[left] + (ordered[left + 1] - ordered[left]) * (index - left)


def _bootstrap(
    values: list[tuple[bool | None, bool | None]], draws: int, seed: int
) -> BootstrapIntervals:
    if type(draws) is not int or draws < 1 or type(seed) is not int:
        raise ValueError("bootstrap draws must be positive and seed must be an integer")
    joint = [_joint(m, low) for m, low in values]
    joint_ready = all(value is not None for value in joint)
    conditional_ready = all(m is not None and (m is False or low is not None) for m, low in values)
    has_errors = any(m is True for m, _ in values)
    if not joint_ready and not (conditional_ready and has_errors):
        return BootstrapIntervals(draws, seed, None, None, None,
                                  "missing_joint_components", "missing_or_zero_error_denominator")
    rng = Random(seed)
    joint_draws = []
    conditional_draws = []
    undefined = 0
    n = len(values)
    for _ in range(draws):
        indices = [rng.randrange(n) for _ in range(n)]
        if joint_ready:
            joint_draws.append(sum(joint[i] is True for i in indices) / n)
        if conditional_ready and has_errors:
            error_indices = [i for i in indices if values[i][0] is True]
            if not error_indices:
                undefined += 1
            else:
                conditional_draws.append(sum(values[i][1] is True for i in error_indices) / len(error_indices))
    joint_interval = (Interval(_percentile(joint_draws, .025), _percentile(joint_draws, .975))
                      if joint_ready else None)
    conditional_interval = (
        Interval(_percentile(conditional_draws, .025), _percentile(conditional_draws, .975))
        if conditional_ready and has_errors and not undefined else None
    )
    return BootstrapIntervals(
        draws, seed, joint_interval, conditional_interval,
        undefined if conditional_ready and has_errors else None,
        None if joint_ready else "missing_joint_components",
        None if conditional_interval is not None else
        "undefined_bootstrap_replicates" if undefined else "missing_or_zero_error_denominator",
    )


def summarize_natural(
    units: Iterable[NaturalUnit], measurements: Iterable[NaturalMeasurement], *,
    material_days: int = 14, low_sensitivity_threshold: float = .005,
    bootstrap_draws: int | None = 10000, seed: int = 20261011,
) -> NaturalSummary:
    """Summarize one primary on the assigned episode-balanced N sample."""
    if type(material_days) is not int or material_days < 1:
        raise ValueError("the end-displacement threshold must be a positive integer")
    units, records = _inputs(units, measurements)
    all_notices = aggregate_measurements(
        [unit.item_id for unit in units],
        [NaturalMeasurement.as_measurement(record, material_days=material_days) for record in records.values()],
        low_sensitivity_threshold=low_sensitivity_threshold,
    )
    values = _values(units, records, material_days, low_sensitivity_threshold)
    conditional = _conditional(values)
    intervals = None if bootstrap_draws is None else _bootstrap(values, bootstrap_draws, seed)
    return NaturalSummary(material_days, low_sensitivity_threshold, all_notices, conditional, intervals)


def summarize_threshold_grid(
    units: Iterable[NaturalUnit], measurements: Iterable[NaturalMeasurement],
) -> tuple[NaturalSummary, ...]:
    """Return all 4 x 5 prespecified cells, without selecting a favorable cell."""
    units, measurements = tuple(units), tuple(measurements)
    return tuple(
        summarize_natural(units, measurements, material_days=days,
                          low_sensitivity_threshold=threshold, bootstrap_draws=None)
        for days in DISPLACEMENT_GRID for threshold in BRIER_GRID
    )
