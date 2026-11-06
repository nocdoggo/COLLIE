"""Outcome-free, item-weighted convention contrasts clustered by episode.

Agreement is defined here as exact equality of statement type and interval
endpoints. Certainty and quoted evidence remain separate diagnostics. This
definition is a draft decision that must be registered before evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Iterable

from .natural_analysis import Interval
from .records import (
    NaturalReading, ParsedNatural, ParseStatus, ReadingIdentity, RETURNED_FAILURES, UNAVAILABLE,
    require_identifier, require_sha256,
)
from .references import ConventionReading, ConventionReference
from .role_analysis import PRIMARY_ROUTES


ARM_TEMPLATES = {
    "absent": "january-convention-absent-v1",
    "neutral": "january-convention-neutral-v1",
    "explicit": "january-convention-explicit-v1",
}
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20261011


@dataclass(frozen=True, slots=True)
class ConventionUnit:
    item_id: str
    episode_id: str
    item_text_sha256: str

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        require_identifier(self.episode_id, "episode_id")
        require_sha256(self.item_text_sha256, "item_text_sha256")


@dataclass(frozen=True, slots=True)
class ConventionConfig:
    model_id: str
    provider_route: str
    precision: str
    template_hashes: tuple[tuple[str, str], ...]
    decoding_sha256: str
    parser_sha256: str

    def __post_init__(self) -> None:
        if self.model_id not in PRIMARY_ROUTES or PRIMARY_ROUTES[self.model_id] != (
            self.provider_route, self.precision
        ):
            raise ValueError("model and provider must match a registered primary route")
        if type(self.template_hashes) is not tuple or len(self.template_hashes) != 3:
            raise ValueError("all three convention template identities are required")
        hashes = dict(self.template_hashes)
        if len(hashes) != 3 or set(hashes) != set(ARM_TEMPLATES):
            raise ValueError("all three convention arms must appear exactly once")
        for value in hashes.values():
            require_sha256(value, "template hash")
        require_sha256(self.decoding_sha256, "decoding hash")
        require_sha256(self.parser_sha256, "parser hash")

    def expected_identity(self, unit: ConventionUnit, arm: str) -> ReadingIdentity:
        if arm not in ARM_TEMPLATES:
            raise ValueError("unknown convention arm")
        return ReadingIdentity(unit.item_id, self.model_id, self.provider_route, self.precision,
                               ARM_TEMPLATES[arm], dict(self.template_hashes)[arm], self.decoding_sha256,
                               unit.item_text_sha256, self.parser_sha256)


@dataclass(frozen=True, slots=True)
class ConventionObservation:
    item_id: str
    arm: str
    parsed: ParsedNatural
    identity: ReadingIdentity | None
    identity_missing_reason: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        if self.arm not in ARM_TEMPLATES or not isinstance(self.parsed, ParsedNatural):
            raise ValueError("unknown convention arm or parse record")
        if self.identity is None:
            if not isinstance(self.identity_missing_reason, str) or not self.identity_missing_reason.strip():
                raise ValueError("missing reading identity requires a reason")
        elif (not isinstance(self.identity, ReadingIdentity) or self.identity.item_id != self.item_id
              or self.identity_missing_reason is not None):
            raise ValueError("reading identity is inconsistent with the assigned item")


@dataclass(frozen=True, slots=True)
class Rate:
    denominator: int
    known_true: int
    known_false: int
    unknown: int
    estimate: float | None
    completion_lower: float
    completion_upper: float


@dataclass(frozen=True, slots=True)
class ConventionArm:
    assigned: int
    valid: int
    returned_failure: int
    unavailable_response: int
    missing_identity: int
    missing_record: int
    specified_agreement: Rate
    defensible_membership: Rate


@dataclass(frozen=True, slots=True)
class ConventionContrast:
    denominator: int
    complete_pairs: int
    estimate: float | None
    completion_lower: float
    completion_upper: float
    bootstrap_95: Interval | None
    interval_reason: str | None


@dataclass(frozen=True, slots=True)
class ConventionSummary:
    model_id: str
    arms: tuple[tuple[str, ConventionArm], ...]
    specified_explicit_minus_neutral: ConventionContrast
    specified_explicit_minus_absent: ConventionContrast
    defensible_explicit_minus_neutral: ConventionContrast
    defensible_explicit_minus_absent: ConventionContrast
    episodes: int
    scientific_status: str = "exploratory"


def _reading_key(reading: NaturalReading | ConventionReading) -> tuple:
    interval = None if reading.interval is None else (reading.interval.start, reading.interval.end)
    return reading.statement_type, interval


def _result(
    observation: ConventionObservation | None, reference: ConventionReference | None,
) -> tuple[str, bool | None, bool | None]:
    if observation is None:
        return "missing_record", None, None
    if observation.identity is None:
        return "missing_identity", None, None
    status = observation.parsed.status
    if status in UNAVAILABLE:
        return "unavailable_response", None, None
    if status in RETURNED_FAILURES:
        return "returned_failure", False, False
    if status is not ParseStatus.VALID:
        raise ValueError("unknown convention response status")
    if reference is None:
        return "valid", None, None
    key = _reading_key(observation.parsed.reading)
    agreement = None if reference.specified is None else key == _reading_key(reference.specified)
    known = any(key == _reading_key(reading) for reading in reference.defensible)
    membership = True if known else (None if reference.defensible_unresolved_reason is not None else False)
    return "valid", agreement, membership


def _rate(values: list[bool | None]) -> Rate:
    yes = sum(value is True for value in values)
    no = sum(value is False for value in values)
    unknown = len(values) - yes - no
    return Rate(len(values), yes, no, unknown, yes / len(values) if not unknown else None,
                yes / len(values), (yes + unknown) / len(values))


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = p * (len(ordered) - 1)
    lower = int(position)
    if lower == len(ordered) - 1:
        return ordered[lower]
    return ordered[lower] + (ordered[lower + 1] - ordered[lower]) * (position - lower)


def _contrast(
    units: tuple[ConventionUnit, ...], left: list[bool | None], right: list[bool | None],
) -> ConventionContrast:
    lower = upper = complete = 0
    for a, b in zip(left, right, strict=True):
        if a is not None and b is not None:
            complete += 1
        lower += (0 if a is None else int(a)) - (1 if b is None else int(b))
        upper += (1 if a is None else int(a)) - (0 if b is None else int(b))
    n = len(units)
    if complete != n:
        return ConventionContrast(n, complete, None, lower / n, upper / n, None, "missing_paired_components")
    estimate = lower / n
    groups: dict[str, list[int]] = {}
    for i, unit in enumerate(units):
        groups.setdefault(unit.episode_id, []).append(i)
    episodes = sorted(groups)
    if len(episodes) < 2:
        return ConventionContrast(n, complete, estimate, estimate, estimate, None, "fewer_than_two_episodes")
    differences = [int(a) - int(b) for a, b in zip(left, right, strict=True)]
    rng = Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        chosen = [episodes[rng.randrange(len(episodes))] for _ in episodes]
        indices = [i for episode in chosen for i in groups[episode]]
        draws.append(sum(differences[i] for i in indices) / len(indices))
    interval = Interval(_percentile(draws, .025), _percentile(draws, .975))
    return ConventionContrast(n, complete, estimate, estimate, estimate, interval, None)


def summarize_conventions(
    units: Iterable[ConventionUnit], references: Iterable[ConventionReference],
    observations: Iterable[ConventionObservation], *, config: ConventionConfig,
) -> ConventionSummary:
    if not isinstance(config, ConventionConfig):
        raise TypeError("config must be a ConventionConfig")
    units = tuple(units)
    if not units or any(not isinstance(unit, ConventionUnit) for unit in units):
        raise ValueError("the C sample must contain ConventionUnit values")
    if len({unit.item_id for unit in units}) != len(units):
        raise ValueError("C item IDs must be unique")
    episodes = [unit.episode_id for unit in units]
    if any(episodes.count(episode) > 2 for episode in set(episodes)):
        raise ValueError("C permits at most two notices per episode")
    units = tuple(sorted(units, key=lambda item: item.item_id))
    by_id = {unit.item_id: unit for unit in units}
    refs = {}
    pass_ids = set()
    for reference in references:
        if not isinstance(reference, ConventionReference):
            raise TypeError("references must contain ConventionReference values")
        if reference.item_id not in by_id or reference.item_id in refs:
            raise ValueError("reference IDs must be assigned and unique")
        ids = set((*reference.first_pass_ids, *reference.specified_pass_ids))
        if pass_ids.intersection(ids):
            raise ValueError("human judgment IDs must be unique across references")
        pass_ids.update(ids)
        refs[reference.item_id] = reference
    obs = {}
    for observation in observations:
        if not isinstance(observation, ConventionObservation):
            raise TypeError("observations must contain ConventionObservation values")
        key = (observation.item_id, observation.arm)
        if observation.item_id not in by_id or key in obs:
            raise ValueError("observation item/arm pairs must be assigned and unique")
        if (observation.identity is not None
                and observation.identity != config.expected_identity(by_id[observation.item_id], observation.arm)):
            raise ValueError("reading identity differs from the assigned convention condition")
        obs[key] = observation
    results = {arm: [_result(obs.get((unit.item_id, arm)), refs.get(unit.item_id)) for unit in units]
               for arm in ARM_TEMPLATES}
    arms = []
    for arm, values in results.items():
        statuses = [value[0] for value in values]
        arms.append((arm, ConventionArm(
            len(units), *(statuses.count(name) for name in
                          ("valid", "returned_failure", "unavailable_response", "missing_identity", "missing_record")),
            _rate([value[1] for value in values]), _rate([value[2] for value in values]),
        )))
    def paired(metric: int, comparator: str) -> ConventionContrast:
        return _contrast(units, [value[metric] for value in results["explicit"]],
                         [value[metric] for value in results[comparator]])
    return ConventionSummary(config.model_id, tuple(arms), paired(1, "neutral"), paired(1, "absent"),
                             paired(2, "neutral"), paired(2, "absent"), len(set(episodes)))
