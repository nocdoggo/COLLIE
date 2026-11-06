"""Paired analyses of the separately identified fictional role experiment.

Each seed contributes one primary pair. Invalid returned answers are task
errors. Missing transports or missing reading identity are unknown and prevent
that model's primary p-value. The module does not call a model or read outcomes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from math import comb
from random import Random
from typing import Iterable

from .natural_analysis import Interval
from .records import (
    ParsedRole, ParseStatus, ReadingIdentity, RETURNED_FAILURES, UNAVAILABLE,
    require_identifier, require_sha256,
)
from .role_materials import RoleSeed, RoleVariant, ValidationDecision, primary_position, validate_structure


ROLE_TEMPLATE = "january-role-v1"
BOOTSTRAP_SEED = 20261011
BOOTSTRAP_DRAWS = 10000
PRIMARY_ROUTES = {
    "meta-llama/llama-3.3-70b-instruct": ("deepinfra/turbo", "fp8"),
    "deepseek/deepseek-chat": ("deepinfra/fp4", "fp4"),
}


@dataclass(frozen=True, slots=True)
class RoleAnalysisConfig:
    model_id: str
    provider_route: str
    precision: str
    template_sha256: str
    decoding_sha256: str
    parser_sha256: str

    def __post_init__(self) -> None:
        if self.model_id not in PRIMARY_ROUTES or PRIMARY_ROUTES[self.model_id] != (
            self.provider_route, self.precision
        ):
            raise ValueError("model and provider must match a registered primary route")
        for name in ("template_sha256", "decoding_sha256", "parser_sha256"):
            require_sha256(getattr(self, name), name)

    def expected_identity(self, variant: RoleVariant) -> ReadingIdentity:
        return ReadingIdentity(variant.item_id, self.model_id, self.provider_route, self.precision,
                               ROLE_TEMPLATE, self.template_sha256, self.decoding_sha256,
                               variant.model_input_sha256, self.parser_sha256)


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    seed: RoleSeed
    validation: ValidationDecision
    post_unblinding_defect: str | None = None

    def __post_init__(self) -> None:
        validate_structure(self.seed)
        raters = self.validation.rater_codes if isinstance(self.validation, ValidationDecision) else ()
        if (not isinstance(self.validation, ValidationDecision)
                or self.validation.seed_id != self.seed.seed_id or self.validation.valid is not True
                or type(self.validation.reasons) is not tuple or self.validation.reasons or type(raters) is not tuple
                or any(not isinstance(code, str) or re.fullmatch(r"A[1-9][0-9]*", code) is None for code in raters)
                or len(set(raters)) != len(raters) or len(raters) < 2):
            raise ValueError("assigned material requires independent human pre-unblinding validation")
        if self.post_unblinding_defect is not None and (
            not isinstance(self.post_unblinding_defect, str) or not self.post_unblinding_defect.strip()
        ):
            raise ValueError("a later defect requires an explicit reason")


@dataclass(frozen=True, slots=True)
class RoleObservation:
    item_id: str
    parsed: ParsedRole
    identity: ReadingIdentity | None
    identity_missing_reason: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        if not isinstance(self.parsed, ParsedRole):
            raise TypeError("parsed must be a ParsedRole")
        if self.identity is None:
            if not isinstance(self.identity_missing_reason, str) or not self.identity_missing_reason.strip():
                raise ValueError("missing reading identity requires a reason")
        elif (not isinstance(self.identity, ReadingIdentity) or self.identity.item_id != self.item_id
              or self.identity_missing_reason is not None):
            raise ValueError("reading identity is inconsistent with the assigned item")


@dataclass(frozen=True, slots=True)
class Effect:
    denominator: int
    complete_pairs: int
    incomplete_pairs: int
    estimate: float | None
    completion_lower: float | None
    completion_upper: float | None


@dataclass(frozen=True, slots=True)
class ArmCounts:
    assigned: int
    target_correct: int
    competing_date_selected: int
    other_date_selected: int
    null_answer: int
    invalid_or_truncated: int
    unavailable: int


@dataclass(frozen=True, slots=True)
class RoleResult:
    model_id: str
    assignment_sha256: str
    primary: Effect
    competitor_only_errors: int | None
    neutral_only_errors: int | None
    p_raw: float | None
    p_holm: float | None
    bootstrap_95: Interval | None
    competitor_diagnostic: ArmCounts
    neutral_diagnostic: ArmCounts
    other_position: Effect
    target_first: Effect
    target_last: Effect
    competitor_earlier: Effect
    competitor_later: Effect
    later_defect_count: int
    without_later_defects: Effect | None
    validation_sha256: str
    later_defects_sha256: str
    scientific_status: str = "development_only_not_registered"


@dataclass(frozen=True, slots=True)
class RoleFamily:
    results: tuple[RoleResult, ...]
    holm_complete: bool
    reason: str | None


def _effect(pairs: list[tuple[bool | None, bool | None]]) -> Effect:
    if not pairs:
        return Effect(0, 0, 0, None, None, None)
    lower = upper = complete = 0
    for competitor, neutral in pairs:
        if competitor is not None and neutral is not None:
            difference = int(competitor) - int(neutral)
            lower += difference
            upper += difference
            complete += 1
        else:
            lower += (0 if competitor is None else int(competitor)) - (1 if neutral is None else int(neutral))
            upper += (1 if competitor is None else int(competitor)) - (0 if neutral is None else int(neutral))
    n = len(pairs)
    return Effect(n, complete, n - complete, lower / n if complete == n else None,
                  lower / n, upper / n)


def _percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    index = p * (len(values) - 1)
    left = int(index)
    if left == len(values) - 1:
        return values[left]
    return values[left] + (values[left + 1] - values[left]) * (index - left)


def _mcnemar(a: int, b: int) -> float:
    n = a + b
    if not n:
        return 1.0
    return min(1.0, 2.0 * sum(comb(n, k) for k in range(min(a, b) + 1)) / 2 ** n)


def _category(seed: RoleSeed, observation: RoleObservation | None) -> tuple[bool | None, str]:
    if observation is None or observation.identity is None or observation.parsed.status in UNAVAILABLE:
        return None, "unavailable"
    if observation.parsed.status in RETURNED_FAILURES:
        return True, "invalid_or_truncated"
    if observation.parsed.status is not ParseStatus.VALID:
        raise ValueError("unsupported role response status")
    target = observation.parsed.reading.target_date
    if target is None:
        return True, "null_answer"
    if target == seed.target_date:
        return False, "target_correct"
    if target == seed.competing_date:
        return True, "competing_date_selected"
    return True, "other_date_selected"


def _counts(categories: list[str]) -> ArmCounts:
    return ArmCounts(len(categories), *(categories.count(name) for name in (
        "target_correct", "competing_date_selected", "other_date_selected", "null_answer",
        "invalid_or_truncated", "unavailable",
    )))


def analyze_role(
    assignments: Iterable[RoleAssignment], observations: Iterable[RoleObservation], *,
    config: RoleAnalysisConfig,
) -> RoleResult:
    """Analyze one model without dropping missing primary pairs."""
    if not isinstance(config, RoleAnalysisConfig):
        raise TypeError("config must be a RoleAnalysisConfig")
    assignments = tuple(assignments)
    if not assignments or any(not isinstance(item, RoleAssignment) for item in assignments):
        raise ValueError("at least one validated seed assignment is required")
    assignments = tuple(sorted(assignments, key=lambda item: item.seed.seed_id))
    if len({item.seed.seed_id for item in assignments}) != len(assignments):
        raise ValueError("seed IDs must be unique")
    variants = {variant.item_id: variant for assignment in assignments for variant in assignment.seed.variants}
    if len(variants) != 4 * len(assignments):
        raise ValueError("variant IDs must be unique across seeds")
    by_item = {}
    for observation in observations:
        if not isinstance(observation, RoleObservation):
            raise TypeError("observations must contain RoleObservation values")
        if observation.item_id not in variants or observation.item_id in by_item:
            raise ValueError("observation IDs must be assigned and unique")
        if (observation.identity is not None
                and observation.identity != config.expected_identity(variants[observation.item_id])):
            raise ValueError("role reading identity does not match the assigned request")
        by_item[observation.item_id] = observation

    primary_pairs, alternate_pairs, first_pairs, last_pairs = [], [], [], []
    earlier_pairs, later_pairs, valid_pairs = [], [], []
    competitor_categories, neutral_categories = [], []
    later_defects = 0
    for assignment in assignments:
        seed = assignment.seed
        data = {}
        for variant in seed.variants:
            data[(variant.arm, variant.position)] = _category(seed, by_item.get(variant.item_id))
        primary = primary_position(seed.seed_id)
        alternate = "last" if primary == "first" else "first"
        pair = (data[("competitor", primary)][0], data[("neutral", primary)][0])
        primary_pairs.append(pair)
        alternate_pairs.append((data[("competitor", alternate)][0], data[("neutral", alternate)][0]))
        first_pairs.append((data[("competitor", "first")][0], data[("neutral", "first")][0]))
        last_pairs.append((data[("competitor", "last")][0], data[("neutral", "last")][0]))
        (earlier_pairs if seed.competing_order == "earlier" else later_pairs).append(pair)
        competitor_categories.append(data[("competitor", primary)][1])
        neutral_categories.append(data[("neutral", primary)][1])
        if assignment.post_unblinding_defect is None:
            valid_pairs.append(pair)
        else:
            later_defects += 1

    effect = _effect(primary_pairs)
    discordant_a = discordant_b = p_value = interval = None
    if not effect.incomplete_pairs:
        discordant_a = sum(a is True and b is False for a, b in primary_pairs)
        discordant_b = sum(a is False and b is True for a, b in primary_pairs)
        p_value = _mcnemar(discordant_a, discordant_b)
        rng = Random(BOOTSTRAP_SEED)
        differences = [int(a) - int(b) for a, b in primary_pairs]
        n = len(differences)
        draws = [sum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(BOOTSTRAP_DRAWS)]
        interval = Interval(_percentile(draws, .025), _percentile(draws, .975))
    identity_payload = [{"seed_id": assignment.seed.seed_id,
                         "primary_position": primary_position(assignment.seed.seed_id),
                         "variant_hashes": [variant.model_input_sha256 for variant in assignment.seed.variants]}
                        for assignment in assignments]
    assignment_hash = hashlib.sha256(json.dumps(identity_payload, sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()
    validation_payload = [{"seed_id": assignment.seed.seed_id, "validation": asdict(assignment.validation)}
                          for assignment in assignments]
    validation_hash = hashlib.sha256(json.dumps(validation_payload, sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()
    defect_payload = [{"seed_id": assignment.seed.seed_id, "reason": assignment.post_unblinding_defect}
                      for assignment in assignments]
    defect_hash = hashlib.sha256(json.dumps(defect_payload, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
    return RoleResult(config.model_id, assignment_hash, effect, discordant_a, discordant_b,
                      p_value, None, interval, _counts(competitor_categories), _counts(neutral_categories),
                      _effect(alternate_pairs), _effect(first_pairs), _effect(last_pairs),
                      _effect(earlier_pairs), _effect(later_pairs), later_defects,
                      _effect(valid_pairs) if later_defects else None, validation_hash, defect_hash)


def holm_role_family(results: Iterable[RoleResult]) -> RoleFamily:
    """Apply Holm over exactly the two primaries, once both tests are available."""
    results = tuple(results)
    if (len(results) != 2 or any(not isinstance(item, RoleResult) for item in results)
            or {item.model_id for item in results} != set(PRIMARY_ROUTES)):
        raise ValueError("the role family contains exactly the two registered primaries")
    for item in results:
        for name in ("assignment_sha256", "validation_sha256", "later_defects_sha256"):
            require_sha256(getattr(item, name), name)
    if len({item.assignment_sha256 for item in results}) != 1:
        raise ValueError("the two primary tests must use the same assigned seeds")
    if len({item.validation_sha256 for item in results}) != 1:
        raise ValueError("the two primary tests must use the same material validation")
    if len({item.later_defects_sha256 for item in results}) != 1:
        raise ValueError("the two primary tests must use the same later-defect record")
    if any(item.p_raw is not None and not 0.0 <= item.p_raw <= 1.0 for item in results):
        raise ValueError("primary p-values must lie in [0,1]")
    if any(item.p_raw is not None and item.primary.incomplete_pairs for item in results):
        raise ValueError("an incomplete primary result cannot carry a p-value")
    if any(item.p_raw is None for item in results):
        return RoleFamily(tuple(replace(item, p_holm=None) for item in results), False,
                          "at least one primary test is unavailable")
    ordered = sorted(results, key=lambda item: (item.p_raw, item.model_id))
    adjusted_small = min(1.0, 2 * ordered[0].p_raw)
    adjusted_large = min(1.0, max(adjusted_small, ordered[1].p_raw))
    adjusted = {ordered[0].model_id: adjusted_small, ordered[1].model_id: adjusted_large}
    return RoleFamily(tuple(replace(item, p_holm=adjusted[item.model_id]) for item in results), True, None)
