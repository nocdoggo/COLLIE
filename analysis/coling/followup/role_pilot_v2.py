"""Synthetic-only, three-seed role-pilot lineage candidate.

This draft creates invented fixtures only, not a real pilot or evaluation
programme. A caller's synthetic tag, key shape, commitment and no-feedback
assertion are not proof of source, entropy, secrecy, timing or registration.
The fixed pilot templates are textually distinct from the current evaluation
families, but exact separation does not establish semantic or near-duplicate
separation. A real pilot requires an independently reviewed lineage, privacy,
provider, accounting and prospective-registration process.

The private material and seed records are not an access-control boundary in
Python. Dates and date roles remain visible in the notices. A new evaluation
programme must use separate high-entropy material and a separately registered
generator; the legacy deterministic EVAL namespace is not fresh material.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import role_generator_v2 as privategen
from . import role_materials as original


PILOT_VERSION = "role-pilot-synthetic-candidate-v1"
PILOT_SCOPE = "synthetic"
PILOT_NAMESPACE = "synthetic-pilot-v2"
PILOT_FAMILIES = (
    "The expected restoration date is {target}.",
    "Supply is projected to return on {target}.",
    "The revised availability estimate is {target}.",
)
_ORDERS = ("earlier", "later", "earlier")
_POSITIONS = ("first", "last")
_ARMS = ("competitor", "neutral")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _check_scope(scope: object) -> None:
    if type(scope) is not str or scope != PILOT_SCOPE:
        raise ValueError("real and evaluation pilot scopes are disabled")


def _check_lineage() -> None:
    privategen._check_original_lineage()
    if (type(PILOT_FAMILIES) is not tuple or len(PILOT_FAMILIES) != 3 or len(set(PILOT_FAMILIES)) != 3
            or set(PILOT_FAMILIES) & set(original.FAMILIES)
            or any(type(text) is not str or text.count("{target}") != 1 for text in PILOT_FAMILIES)):
        raise ValueError("pilot family identity conflicts with the declared evaluation lineage")
    if PILOT_NAMESPACE == privategen.TEST_NAMESPACE or PILOT_NAMESPACE != privategen.PILOT_NAMESPACE:
        raise ValueError("pilot and synthetic-test namespaces must remain distinct")


def pilot_lineage_sha256() -> str:
    """Identify the fixed pilot templates, not semantic novelty or registration."""
    _check_lineage()
    value = {"version": PILOT_VERSION, "namespace": PILOT_NAMESPACE, "families": PILOT_FAMILIES,
             "background": ["Bulletin posted on {publication}.",
                            "A prior restoration estimate dated {old_issue} gave {old_target} and is superseded.",
                            "{role} takes place on {competing}."]}
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class _Variant:
    arm: str
    position: str
    primary: bool
    notice_text: str

    def __repr__(self) -> str:
        return "_Variant(<private synthetic pilot>)"


@dataclass(frozen=True, slots=True, repr=False)
class _Seed:
    ordinal: int
    private_seed_id: str
    family: int
    competing_order: str
    update: date
    publication: date
    old_issue: date
    old_target: date
    target: date
    competing: date
    primary_position: str
    variants: tuple[_Variant, ...]

    def __repr__(self) -> str:
        return "_Seed(<private synthetic pilot>)"


def _seed_id(material: privategen.PrivateMaterial, ordinal: int) -> str:
    if type(ordinal) is not int or not 1 <= ordinal <= 3:
        raise ValueError("synthetic pilot ordinal must be one through three")
    return material._mac("private-seed", PILOT_NAMESPACE, PILOT_VERSION, str(ordinal))


def _render(seed: _Seed, arm: str, position: str) -> str:
    if arm not in _ARMS or position not in _POSITIONS:
        raise ValueError("unknown synthetic pilot variant")
    current = PILOT_FAMILIES[seed.family].format(target=seed.target.isoformat())
    role = "Next review" if arm == "competitor" else "Data filing"
    background = (
        f"Bulletin posted on {seed.publication.isoformat()}.",
        f"A prior restoration estimate dated {seed.old_issue.isoformat()} gave {seed.old_target.isoformat()} and is superseded.",
        f"{role} takes place on {seed.competing.isoformat()}.",
    )
    return " ".join((current, *background) if position == "first" else (*background, current))


def _build_seed(material: privategen.PrivateMaterial, ordinal: int) -> _Seed:
    private_id = _seed_id(material, ordinal)
    digest = hashlib.sha256((PILOT_VERSION + "|dates|" + private_id).encode("ascii")).digest()
    update = date(2028, 1, 1) + timedelta(days=int.from_bytes(digest[:2], "big") % 366)
    publication = update - timedelta(days=90 + digest[2] % 15)
    old_issue = update - timedelta(days=45 + digest[3] % 10)
    old_target = update - timedelta(days=7 + digest[4] % 15)
    target = update + timedelta(days=60 + digest[5] % 90)
    distance = 14 + digest[6] % 14
    order = _ORDERS[ordinal - 1]
    competing = target + timedelta(days=-distance if order == "earlier" else distance)
    primary = original.primary_position(private_id)
    partial = _Seed(ordinal, private_id, ordinal - 1, order, update, publication, old_issue,
                    old_target, target, competing, primary, ())
    variants = tuple(_Variant(arm, position, position == primary, _render(partial, arm, position))
                     for position in _POSITIONS for arm in _ARMS)
    return _Seed(ordinal, private_id, ordinal - 1, order, update, publication, old_issue,
                 old_target, target, competing, primary, variants)


def _seed_record(seed: _Seed) -> dict[str, object]:
    return {"ordinal": seed.ordinal, "private_seed_id": seed.private_seed_id, "family": seed.family,
            "competing_order": seed.competing_order, "update": seed.update.isoformat(),
            "publication": seed.publication.isoformat(), "old_issue": seed.old_issue.isoformat(),
            "old_target": seed.old_target.isoformat(), "target": seed.target.isoformat(),
            "competing": seed.competing.isoformat(), "primary_position": seed.primary_position,
            "variants": [{"arm": item.arm, "position": item.position, "primary": item.primary,
                          "notice_text": item.notice_text} for item in seed.variants]}


def _manifest(material: privategen.PrivateMaterial, seeds: tuple[_Seed, ...]) -> str:
    value = {"version": PILOT_VERSION, "scope": PILOT_SCOPE, "namespace": PILOT_NAMESPACE,
             "lineage_sha256": pilot_lineage_sha256(), "material_commitment": material.commitment_sha256,
             "seeds": [_seed_record(seed) for seed in seeds]}
    return material._mac("private-manifest", PILOT_NAMESPACE, PILOT_VERSION, _canonical(value))


def _group_alias(material: privategen.PrivateMaterial, seed: _Seed) -> str:
    return "G" + material._mac("group-alias", PILOT_NAMESPACE, PILOT_VERSION, seed.private_seed_id)


def _variant_alias(material: privategen.PrivateMaterial, seed: _Seed, variant: _Variant) -> str:
    return "V" + material._mac("variant-alias", PILOT_NAMESPACE, PILOT_VERSION, seed.private_seed_id,
                               variant.arm, variant.position)


def _views(material: privategen.PrivateMaterial, seeds: tuple[_Seed, ...]) -> tuple[dict[str, object], ...]:
    values = []
    for seed in seeds:
        group = _group_alias(material, seed)
        expected_group = "G" + material._mac("group-alias", PILOT_NAMESPACE, PILOT_VERSION, seed.private_seed_id)
        if type(group) is not str or re.fullmatch(r"G[0-9a-f]{64}", group) is None or group != expected_group:
            raise ValueError("synthetic pilot group alias differs from its private identity")
        notices = []
        for variant in seed.variants:
            alias = _variant_alias(material, seed, variant)
            expected_alias = "V" + material._mac("variant-alias", PILOT_NAMESPACE, PILOT_VERSION,
                                               seed.private_seed_id, variant.arm, variant.position)
            if type(alias) is not str or re.fullmatch(r"V[0-9a-f]{64}", alias) is None or alias != expected_alias:
                raise ValueError("synthetic pilot variant alias differs from its private identity")
            notices.append({"item_id": alias, "update_date": seed.update.isoformat(),
                            "notice_text": variant.notice_text})
        notices.sort(key=lambda item: item["item_id"])
        values.append({"synthetic_only": True, "group_id": group, "notices": notices})
    if len({view["group_id"] for view in values}) != 3 or len({
        notice["item_id"] for view in values for notice in view["notices"]
    }) != 12:
        raise ValueError("synthetic pilot alias collision")
    tokens = privategen._disclosure_tokens(material._material, tuple(seed.private_seed_id for seed in seeds))
    for view in values:
        privategen._assert_safe_export(tokens, view)
    privategen._assert_safe_export(tokens, tuple(values))
    return tuple(values)


def _validate_seed(seed: _Seed) -> None:
    if (type(seed) is not _Seed or type(seed.variants) is not tuple or len(seed.variants) != 4
            or any(type(item) is not _Variant for item in seed.variants)):
        raise ValueError("synthetic pilot needs four exact variants")
    if (type(seed.ordinal) is not int or not 1 <= seed.ordinal <= 3
            or type(seed.family) is not int or seed.family != seed.ordinal - 1
            or type(seed.private_seed_id) is not str or re.fullmatch(r"[0-9a-f]{64}", seed.private_seed_id) is None
            or type(seed.competing_order) is not str or seed.competing_order != _ORDERS[seed.ordinal - 1]
            or type(seed.primary_position) is not str
            or seed.primary_position != original.primary_position(seed.private_seed_id)
            or any(type(day) is not date for day in (seed.publication, seed.old_issue, seed.old_target,
                                                     seed.update, seed.target, seed.competing))):
        raise ValueError("synthetic pilot seed identity or factors are invalid")
    if not (seed.publication < seed.old_issue < seed.old_target < seed.update < seed.target
            and seed.competing > seed.update and len({seed.publication, seed.old_issue, seed.old_target,
                                                       seed.update, seed.target, seed.competing}) == 6):
        raise ValueError("synthetic pilot chronology is invalid")
    if ((seed.competing < seed.target) != (seed.competing_order == "earlier")
            or seed.competing_order not in {"earlier", "later"}):
        raise ValueError("synthetic pilot date order differs")
    variants = {(item.arm, item.position): item for item in seed.variants}
    if set(variants) != {(arm, position) for arm in _ARMS for position in _POSITIONS}:
        raise ValueError("synthetic pilot requires the full 2x2")
    for item in seed.variants:
        if (type(item.arm) is not str or type(item.position) is not str or type(item.notice_text) is not str
                or type(item.primary) is not bool or item.primary != (item.position == seed.primary_position)
                or item.notice_text != _render(seed, item.arm, item.position)):
            raise ValueError("synthetic pilot variant differs from its fixed design")
        if any(item.notice_text.count(day.isoformat()) != 1
               for day in (seed.publication, seed.old_issue, seed.old_target, seed.target, seed.competing)):
            raise ValueError("synthetic pilot date roles must each appear exactly once")
    for position in _POSITIONS:
        competitor = variants[("competitor", position)].notice_text
        neutral = variants[("neutral", position)].notice_text
        if competitor.replace("Next review", "Data filing") != neutral or len(competitor) != len(neutral):
            raise ValueError("synthetic pilot pairs differ beyond the role contrast")


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticPilotProgramme:
    """Private synthetic candidate; its commitment is not a registration."""

    scope: str
    material: privategen.PrivateMaterial = field(repr=False)
    _seeds: tuple[_Seed, ...] = field(repr=False)
    manifest_commitment: str

    def __post_init__(self) -> None:
        _validate_programme(self)

    def __repr__(self) -> str:
        return "SyntheticPilotProgramme(<private synthetic pilot>)"

    def receipt(self) -> dict[str, object]:
        _validate_programme(self)
        value = {"synthetic_only": True, "version": PILOT_VERSION, "namespace": PILOT_NAMESPACE,
                 "lineage_sha256": pilot_lineage_sha256(), "material_commitment_sha256": self.material.commitment_sha256,
                 "manifest_commitment_sha256": self.manifest_commitment, "seed_count": 3, "variant_count": 12}
        tokens = privategen._disclosure_tokens(self.material._material, tuple(seed.private_seed_id for seed in self._seeds))
        privategen._assert_safe_export(tokens, value)
        return value

    def visible(self, *, expected_manifest_commitment: str, no_feedback_seen: bool) -> tuple[dict[str, object], ...]:
        """Return preflighted synthetic views; the timing assertion is not evidence."""
        if type(no_feedback_seen) is not bool or no_feedback_seen is not True:
            raise ValueError("synthetic pilot delivery requires a no-feedback assertion")
        _validate_programme(self)
        if (type(expected_manifest_commitment) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_commitment) is None
                or not hmac.compare_digest(
            expected_manifest_commitment, self.manifest_commitment
        )):
            raise ValueError("synthetic pilot manifest commitment differs")
        return _views(self.material, self._seeds)


def _validate_programme(programme: SyntheticPilotProgramme) -> None:
    if type(programme) is not SyntheticPilotProgramme or type(programme.material) is not privategen.PrivateMaterial:
        raise TypeError("exact synthetic pilot programme and private material are required")
    _check_scope(programme.scope)
    _check_lineage()
    programme.material._validate()
    if type(programme._seeds) is not tuple or len(programme._seeds) != 3:
        raise ValueError("synthetic pilot requires exactly three seeds")
    expected = tuple(_build_seed(programme.material, ordinal) for ordinal in range(1, 4))
    for seed in programme._seeds:
        _validate_seed(seed)
    if programme._seeds != expected or len({seed.private_seed_id for seed in expected}) != 3:
        raise ValueError("synthetic pilot does not match its fixed private seed derivation")
    expected_commitment = _manifest(programme.material, expected)
    if (type(programme.manifest_commitment) is not str
            or re.fullmatch(r"[0-9a-f]{64}", programme.manifest_commitment) is None
            or not hmac.compare_digest(
        programme.manifest_commitment, expected_commitment
    ) or not hmac.compare_digest(programme.manifest_commitment, _manifest(programme.material, programme._seeds))):
        raise ValueError("synthetic pilot manifest commitment differs")
    _views(programme.material, expected)


def synthetic_pilot_programme(*, material: privategen.PrivateMaterial, scope: str) -> SyntheticPilotProgramme:
    """Build only an invented, permanently excluded three-seed pilot fixture."""
    _check_scope(scope)  # Fail before deriving any seed for real/evaluation scope.
    if type(material) is not privategen.PrivateMaterial:
        raise TypeError("invented private material is required")
    material._validate()
    _check_lineage()
    seeds = tuple(_build_seed(material, ordinal) for ordinal in range(1, 4))
    return SyntheticPilotProgramme(scope, material, seeds, _manifest(material, seeds))
