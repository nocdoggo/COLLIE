"""Outcome-free implementation of aggregate feasible ranking calculations.

Only synthetic states may be supplied before an authorized sealed reader and a
joint disclosure policy are registered. This module opens no files and returns
no per-statement state or outcome export. Its intervals describe identification
on a fixed sample, not sampling confidence regions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from math import fsum
from typing import Iterable

from .measurement_sensitivity import ProbabilityPair, exact_brier_perturbation_bounds, validate_allowed_labels
from .records import require_identifier, require_sha256


@dataclass(frozen=True, slots=True)
class RankingRow:
    item_id: str
    earlier_horizon: date
    later_horizon: date
    comparator: ProbabilityPair
    tested: ProbabilityPair
    allowed_labels: tuple[tuple[int, int], ...]
    latent_event_id: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        if type(self.earlier_horizon) is not date or type(self.later_horizon) is not date:
            raise TypeError("horizons must be calendar dates")
        if self.earlier_horizon >= self.later_horizon:
            raise ValueError("horizons must be strictly ordered")
        if not isinstance(self.comparator, ProbabilityPair) or not isinstance(self.tested, ProbabilityPair):
            raise TypeError("both predictors need ordered probability pairs")
        if type(self.allowed_labels) is not tuple:
            raise TypeError("allowed states must be supplied explicitly as a tuple")
        object.__setattr__(self, "allowed_labels", validate_allowed_labels(self.allowed_labels))
        if self.latent_event_id is not None:
            require_identifier(self.latent_event_id, "latent_event_id")


@dataclass(frozen=True, slots=True)
class SharedEvent:
    """An explicitly established single latent recovery event, not an episode."""

    latent_event_id: str
    construction: str
    construction_sha256: str
    earliest: date | None
    latest: date | None

    def __post_init__(self) -> None:
        require_identifier(self.latent_event_id, "latent_event_id")
        if self.construction != "same_latent_recovery_event":
            raise ValueError("company or broad episode membership does not establish a shared event")
        require_sha256(self.construction_sha256, "event-construction hash")
        if any(value is not None and type(value) is not date for value in (self.earliest, self.latest)):
            raise TypeError("event limits must be dates or None")
        if self.earliest is not None and self.latest is not None and self.earliest > self.latest:
            raise ValueError("event limits must be ordered")


@dataclass(frozen=True, slots=True)
class RankingInterval:
    statements: int
    rowwise_lower: float
    rowwise_upper: float
    constrained_lower: float
    constrained_upper: float
    shared_event_groups: int
    sign_convention: str = "comparator loss minus tested-predictor loss"


@dataclass(frozen=True, slots=True)
class RankingScope:
    model: str
    comparison: str
    fixed_slice_ids_sha256: str

    def __post_init__(self) -> None:
        if self.model not in {"llama-3.3-70b", "deepseek-v3"} or self.comparison not in {"H1", "H2", "H3"}:
            raise ValueError("only the three original comparisons for each primary are supported")
        require_sha256(self.fixed_slice_ids_sha256, "fixed slice hash")


@dataclass(frozen=True, slots=True)
class ScopedRanking:
    scope: RankingScope
    interval: RankingInterval
    scientific_status: str = "exploratory"


def _delta(row: RankingRow, label: tuple[int, int]) -> float:
    # The pure Brier helper gives tested minus comparator. Reverse for the
    # original comparison convention: positive favors the tested predictor.
    return -exact_brier_perturbation_bounds(row.comparator, row.tested, (label,)).lower


def _joint_values(rows: tuple[RankingRow, ...], event: SharedEvent) -> tuple[float, ...]:
    horizons = {h for row in rows for h in (row.earlier_horizon, row.later_horizon)}
    candidates = set(horizons)
    for horizon in horizons:
        if horizon < date.max:
            candidates.add(horizon + timedelta(days=1))
    if event.earliest is not None:
        candidates.add(event.earliest)
    if event.latest is not None:
        candidates.add(event.latest)
    possible = [value for value in candidates
                if (event.earliest is None or value >= event.earliest)
                and (event.latest is None or value <= event.latest)]
    # A never-recovered or later-than-every-horizon state is possible only
    # when the feasible event has no finite upper limit.
    dates: list[date | None] = list(possible)
    if event.latest is None:
        dates.append(None)
    values = []
    for event_date in dates:
        labels = tuple((int(event_date is not None and event_date <= row.earlier_horizon),
                        int(event_date is not None and event_date <= row.later_horizon)) for row in rows)
        if all(label in row.allowed_labels for row, label in zip(rows, labels, strict=True)):
            values.append(fsum(_delta(row, label) for row, label in zip(rows, labels, strict=True)))
    if not values:
        raise ValueError("the stated shared-event constraints have no feasible completion")
    return tuple(values)


def feasible_ranking(rows: Iterable[RankingRow], shared_events: Iterable[SharedEvent] = ()) -> RankingInterval:
    """Return the rowwise relaxation and the declared shared-event interval."""
    rows, shared_events = tuple(rows), tuple(shared_events)
    if not rows or any(not isinstance(row, RankingRow) for row in rows):
        raise ValueError("a nonempty set of ranking rows is required")
    if len({row.item_id for row in rows}) != len(rows):
        raise ValueError("ranking item IDs must be unique")
    if any(not isinstance(event, SharedEvent) for event in shared_events):
        raise TypeError("shared event records must have explicit construction evidence")
    events = {event.latent_event_id: event for event in shared_events}
    if len(events) != len(shared_events):
        raise ValueError("shared-event identities must be unique")
    used = {row.latent_event_id for row in rows if row.latent_event_id is not None}
    if set(events) != used:
        raise ValueError("every shared group must have exactly one explicit event record")
    row_bounds = [tuple(_delta(row, label) for label in row.allowed_labels) for row in rows]
    row_lower = fsum(min(values) for values in row_bounds) / len(rows)
    row_upper = fsum(max(values) for values in row_bounds) / len(rows)
    independent = [values for row, values in zip(rows, row_bounds, strict=True) if row.latent_event_id is None]
    grouped = {key: tuple(row for row in rows if row.latent_event_id == key) for key in events}
    if any(len(group) < 2 for group in grouped.values()):
        raise ValueError("a shared event must link at least two statements")
    joint = [_joint_values(grouped[key], events[key]) for key in sorted(events)]
    lower = fsum(min(values) for values in (*independent, *joint)) / len(rows)
    upper = fsum(max(values) for values in (*independent, *joint)) / len(rows)
    return RankingInterval(len(rows), row_lower, row_upper, lower, upper, len(events))


def scoped_feasible_ranking(
    scope: RankingScope, rows: Iterable[RankingRow], shared_events: Iterable[SharedEvent] = (),
) -> ScopedRanking:
    """Hold a primary-specific slice fixed and label this existing-data analysis exploratory."""
    if not isinstance(scope, RankingScope):
        raise TypeError("a declared ranking scope is required")
    rows = tuple(rows)
    if any(not isinstance(row, RankingRow) for row in rows):
        raise TypeError("ranking rows must be typed")
    digest = hashlib.sha256("\n".join(sorted(row.item_id for row in rows)).encode("utf-8")).hexdigest()
    if digest != scope.fixed_slice_ids_sha256:
        raise ValueError("ranking rows do not match the fixed eligible slice")
    return ScopedRanking(scope, feasible_ranking(rows, shared_events))
