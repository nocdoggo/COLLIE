"""Draft generator and pre-unblinding validation for fictional role materials.

Only generated, fictional notices are produced. The legacy public evaluation
generator is disabled; private Python internals are not an access-control
sandbox. A separately reviewed and registered generator is required before an
evaluation. Structural checks complement, but do not replace, validation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Iterable, NoReturn

from .records import require_identifier


SEED = 20261011
GENERATOR_VERSION = "role-generator-draft-v1"
TARGET_COUNTS = {"full": 80, "reduced": 50}
RESERVE_COUNT = 16
FAMILIES = (
    "Current recovery is expected on {target}.",
    "The current recovery estimate is {target}.",
    "Supply recovery is currently estimated for {target}.",
    "The present supply recovery target is {target}.",
)
POSITIONS = ("first", "last")
ARMS = ("competitor", "neutral")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def primary_position(seed_id: str) -> str:
    """Map the first SHA256 bit to first (0) or last (1)."""
    require_identifier(seed_id, "seed_id")
    first_bit = hashlib.sha256(f"{SEED}|role-primary-position|{seed_id}".encode()).digest()[0] >> 7
    return POSITIONS[first_bit]


def _render(
    *, family: int, update: date, publication: date, old_issue: date, old_target: date,
    target: date, competing: date, arm: str, position: str,
) -> str:
    if arm not in ARMS or position not in POSITIONS or not 0 <= family < len(FAMILIES):
        raise ValueError("unknown role variant")
    current = FAMILIES[family].format(target=target.isoformat())
    other = "Next review" if arm == "competitor" else "Data filing"
    background = (
        f"Published on {publication.isoformat()}.",
        f"The recovery estimate issued on {old_issue.isoformat()} was {old_target.isoformat()} and is superseded.",
        f"{other} is scheduled on {competing.isoformat()}.",
    )
    return " ".join((current, *background) if position == "first" else (*background, current))


@dataclass(frozen=True, slots=True)
class RoleVariant:
    item_id: str
    seed_id: str
    arm: str
    position: str
    primary: bool
    update_date: date
    notice_text: str

    def model_input(self) -> dict[str, str]:
        return {"update_date": self.update_date.isoformat(), "notice_text": self.notice_text}

    @property
    def model_input_sha256(self) -> str:
        payload = json.dumps(self.model_input(), ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
        return _hash(payload)


@dataclass(frozen=True, slots=True)
class RoleSeed:
    seed_id: str
    wording_family: int
    competing_order: str
    update_date: date
    publication_date: date
    superseded_issue_date: date
    superseded_target_date: date
    target_date: date
    competing_date: date
    variants: tuple[RoleVariant, ...]


def _make_seed(seed_id: str, family: int, competing_order: str) -> RoleSeed:
    require_identifier(seed_id, "seed_id")
    if type(family) is not int or not 0 <= family < len(FAMILIES):
        raise ValueError("unknown wording family")
    if competing_order not in {"earlier", "later"}:
        raise ValueError("unknown date-order factor")
    digest = hashlib.sha256(f"{SEED}|role-dates-v1|{seed_id}".encode()).digest()
    update = date(2027, 1, 1) + timedelta(days=int.from_bytes(digest[:4], "big") % 730)
    publication = update - timedelta(days=80 + digest[4] % 20)
    old_issue = update - timedelta(days=35 + digest[5] % 15)
    old_target = update - timedelta(days=5 + digest[6] % 20)
    target = update + timedelta(days=60 + digest[7] % 90)
    gap = 14 + digest[8] % 14
    competing = target + timedelta(days=-gap if competing_order == "earlier" else gap)
    primary = primary_position(seed_id)
    variants = tuple(
        RoleVariant(
            f"{seed_id}:{arm}:{position}", seed_id, arm, position, position == primary, update,
            _render(family=family, update=update, publication=publication, old_issue=old_issue,
                    old_target=old_target, target=target, competing=competing, arm=arm, position=position),
        )
        for position in POSITIONS for arm in ARMS
    )
    seed = RoleSeed(seed_id, family, competing_order, update, publication, old_issue,
                    old_target, target, competing, variants)
    validate_structure(seed)
    return seed


def validate_structure(seed: RoleSeed) -> None:
    """Check chronology, all roles, paired edits, and the primary orientation."""
    if not isinstance(seed, RoleSeed):
        raise TypeError("seed must be a RoleSeed")
    require_identifier(seed.seed_id, "seed_id")
    dates = (seed.publication_date, seed.superseded_issue_date, seed.superseded_target_date,
             seed.update_date, seed.target_date, seed.competing_date)
    if any(type(value) is not date for value in dates) or len(set(dates)) != len(dates):
        raise ValueError("date roles must be distinct calendar dates")
    if not (seed.publication_date < seed.superseded_issue_date < seed.superseded_target_date < seed.update_date):
        raise ValueError("publication and superseded-estimate chronology is invalid")
    if not (seed.target_date > seed.update_date and seed.competing_date > seed.update_date):
        raise ValueError("current recovery and review or filing must follow the update")
    if seed.competing_order not in {"earlier", "later"} or (
        (seed.competing_date < seed.target_date) != (seed.competing_order == "earlier")
    ):
        raise ValueError("competing-date order is inconsistent")
    if type(seed.wording_family) is not int or not 0 <= seed.wording_family < len(FAMILIES):
        raise ValueError("unknown wording family")
    if len(seed.variants) != 4:
        raise ValueError("a seed requires four variants")
    by_arm = {(v.arm, v.position): v for v in seed.variants}
    if len(by_arm) != 4 or set(by_arm) != set((arm, pos) for pos in POSITIONS for arm in ARMS):
        raise ValueError("a seed needs each arm and position exactly once")
    if len({v.item_id for v in seed.variants}) != 4:
        raise ValueError("variant IDs must be unique")
    primary = primary_position(seed.seed_id)
    for variant in seed.variants:
        if (variant.seed_id != seed.seed_id or variant.item_id != f"{seed.seed_id}:{variant.arm}:{variant.position}"
                or variant.update_date != seed.update_date or type(variant.primary) is not bool
                or variant.primary != (variant.position == primary)):
            raise ValueError("variant identity or primary orientation is inconsistent")
        expected = _render(family=seed.wording_family, update=seed.update_date,
                           publication=seed.publication_date, old_issue=seed.superseded_issue_date,
                           old_target=seed.superseded_target_date, target=seed.target_date,
                           competing=seed.competing_date, arm=variant.arm, position=variant.position)
        if variant.notice_text != expected:
            raise ValueError("variant wording differs from its declared factors")
        for value in (seed.publication_date, seed.superseded_issue_date, seed.superseded_target_date,
                      seed.target_date, seed.competing_date):
            if variant.notice_text.count(value.isoformat()) != 1:
                raise ValueError("each dated role must occur exactly once")
    for position in POSITIONS:
        competitor = by_arm[("competitor", position)].notice_text
        neutral = by_arm[("neutral", position)].notice_text
        if competitor.replace("Next review", "Data filing") != neutral:
            raise ValueError("paired variants differ beyond the declared role")
        if len(competitor) != len(neutral):
            raise ValueError("paired notice lengths must match")


@dataclass(frozen=True, slots=True)
class RoleProgramme:
    package: str
    purpose: str
    assigned: tuple[RoleSeed, ...]
    reserve: tuple[RoleSeed, ...]
    manifest_sha256: str


def _allocate(ids: Iterable[str], phase: str) -> tuple[RoleSeed, ...]:
    ids = tuple(ids)
    if len(ids) != len(set(ids)):
        raise ValueError("seed IDs must be unique")
    order = sorted(ids, key=lambda item: (_hash(f"{SEED}|role-allocation-v1|{phase}|{item}"), item))
    # Eight cells: four wording families crossed with earlier/later competing dates.
    return tuple(_make_seed(item, (i % 8) // 2, ("earlier", "later")[i % 2])
                 for i, item in enumerate(order))


def _programme(package: str, purpose: str, prefix: str) -> RoleProgramme:
    if package not in TARGET_COUNTS:
        raise ValueError("package must be full or reduced")
    assigned = _allocate((f"{prefix}-R{i:03d}" for i in range(1, TARGET_COUNTS[package] + 1)), "assigned")
    reserve = _allocate((f"{prefix}-RR{i:03d}" for i in range(1, RESERVE_COUNT + 1)), "reserve")
    payload = {"version": GENERATOR_VERSION, "seed": SEED, "package": package, "purpose": purpose,
               "assigned": [asdict(item) for item in assigned], "reserve": [asdict(item) for item in reserve]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=lambda value: value.isoformat())
    return RoleProgramme(package, purpose, assigned, reserve, _hash(encoded))


def role_programme(package: str) -> NoReturn:
    """Fail closed: the legacy evaluation namespace is not a registered design."""
    raise RuntimeError("legacy evaluation role programme generation is disabled")


def synthetic_role_programme(package: str) -> RoleProgramme:
    """Generate permanently excluded material for local checks."""
    return _programme(package, "synthetic", "SYNTHETIC")


@dataclass(frozen=True, slots=True)
class PilotNotice:
    item_id: str
    update_date: date
    notice_text: str

    def model_input(self) -> dict[str, str]:
        return {"update_date": self.update_date.isoformat(), "notice_text": self.notice_text}


def pilot_notices() -> tuple[PilotNotice, ...]:
    """Twelve invented practice notices, permanently separate from evaluation."""
    texts = (
        "Practice notice: estimated recovery early April 2028.",
        "Practice notice: the next delivery is expected late June 2028.",
        "Practice notice: recovery is expected the week of 2028-05-08.",
        "Practice notice: next delivery is expected the first week of July 2028.",
        "Practice notice: recovery is anticipated in September.",
        "Practice notice: recovery is estimated within 6 weeks.",
        "Practice notice: estimated recovery is to be determined.",
        "Practice notice: limited inventory is reported, with no timing stated.",
        "Practice notice: the current recovery date is 2028-07-15. A review is on 2028-06-15.",
        "Practice notice: the 2028-04-01 estimate is superseded. Current recovery is 2028-07-10.",
        "Practice notice: the current recovery date is 2028-08-02. A data filing is on 2028-07-02.",
        "Practice notice: review is 2028-08-14. Current recovery is 2028-07-14.",
    )
    return tuple(PilotNotice(f"P{i:02d}", date(2028, 3, 1), text)
                 for i, text in enumerate(texts, start=1))


@dataclass(frozen=True, slots=True)
class RoleChecks:
    unique_current_target: bool | None
    coherent_chronology: bool | None
    competing_role_preserves_target: bool | None
    neutral_role_unrelated: bool | None
    comparable_length_and_syntax: bool | None
    position_preserves_meaning: bool | None

    def __post_init__(self) -> None:
        if any(value is not None and type(value) is not bool for value in asdict(self).values()):
            raise TypeError("each material check must be true, false, or unknown")


@dataclass(frozen=True, slots=True)
class HumanRoleJudgment:
    seed_id: str
    rater_code: str
    targets: tuple[tuple[str, date | None], ...]
    checks: RoleChecks
    material_valid: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.seed_id, "seed_id")
        if not isinstance(self.rater_code, str) or re.fullmatch(r"A[1-9][0-9]*", self.rater_code) is None:
            raise ValueError("first-pass raters use anonymous A codes")
        if type(self.material_valid) is not bool:
            raise TypeError("material_valid must be bool")
        if not isinstance(self.checks, RoleChecks):
            raise TypeError("the six independent material checks are required")
        if self.material_valid and any(value is not True for value in asdict(self.checks).values()):
            raise ValueError("valid material requires all six checks to pass")
        if type(self.targets) is not tuple or any(
            not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str)
            or (pair[1] is not None and type(pair[1]) is not date) for pair in self.targets
        ):
            raise TypeError("targets must be a tuple of variant IDs and dates or None")
        ids = [item_id for item_id, _ in self.targets]
        if any(not item_id.strip() for item_id in ids) or len(ids) != len(set(ids)):
            raise ValueError("judgment variant IDs must be nonempty and unique")
        if not self.material_valid and (not isinstance(self.reason, str) or not self.reason.strip()):
            raise ValueError("invalid material needs an explicit reason")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason.strip()):
            raise ValueError("reason must be nonempty when supplied")


@dataclass(frozen=True, slots=True)
class ValidationDecision:
    seed_id: str
    valid: bool
    reasons: tuple[str, ...]
    rater_codes: tuple[str, ...]


def validate_human(
    seed: RoleSeed, judgments: Iterable[HumanRoleJudgment], *, outputs_viewed: bool,
) -> ValidationDecision:
    """Require independent, complete judgments before any output is viewed."""
    validate_structure(seed)
    if type(outputs_viewed) is not bool:
        raise TypeError("outputs_viewed must be bool")
    if outputs_viewed:
        raise ValueError("material cannot be newly validated after output exposure")
    judgments = tuple(judgments)
    if len(judgments) < 2 or any(not isinstance(j, HumanRoleJudgment) for j in judgments):
        raise ValueError("at least two independent judgments are required")
    raters = [j.rater_code for j in judgments]
    if len(set(raters)) != len(raters) or any(j.seed_id != seed.seed_id for j in judgments):
        raise ValueError("judgments must have distinct raters and the same seed")
    wanted = {variant.item_id for variant in seed.variants}
    reasons = []
    for judgment in judgments:
        recorded = dict(judgment.targets)
        if set(recorded) != wanted:
            raise ValueError("each judgment must cover all four variants")
        if not judgment.material_valid:
            reasons.append(judgment.rater_code + ":" + judgment.reason)
        if any(target != seed.target_date for target in recorded.values()):
            reasons.append(judgment.rater_code + ":target_unconfirmed")
    return ValidationDecision(seed.seed_id, not reasons, tuple(reasons), tuple(sorted(raters)))


def select_reserve(
    programme: RoleProgramme, rejected: RoleSeed, replacement: RoleSeed, *,
    rejected_validation: ValidationDecision, replacement_validation: ValidationDecision,
    output_viewed: bool, used_seed_ids: Iterable[str],
) -> RoleSeed:
    """Replace a pre-unblinding rejection only with a locked matching reserve."""
    if type(output_viewed) is not bool:
        raise TypeError("output_viewed must be bool")
    if output_viewed:
        raise ValueError("post-unblinding defects cannot be replaced")
    if rejected not in programme.assigned or replacement not in programme.reserve:
        raise ValueError("seed and reserve must belong to the locked programme")
    if (not isinstance(rejected_validation, ValidationDecision)
            or rejected_validation.seed_id != rejected.seed_id or rejected_validation.valid
            or not rejected_validation.reasons or len(set(rejected_validation.rater_codes)) < 2):
        raise ValueError("the assigned seed needs an independent pre-unblinding rejection")
    if (not isinstance(replacement_validation, ValidationDecision)
            or replacement_validation.seed_id != replacement.seed_id or not replacement_validation.valid
            or replacement_validation.reasons or len(set(replacement_validation.rater_codes)) < 2):
        raise ValueError("the reserve needs independent pre-unblinding validation")
    if replacement.seed_id in set(used_seed_ids):
        raise ValueError("reserve seed has already been used")
    if (rejected.wording_family, rejected.competing_order) != (
        replacement.wording_family, replacement.competing_order
    ):
        raise ValueError("reserve must preserve the wording and date-order allocation")
    return replacement
