"""Synthetic-only preregistration candidate for privately seeded role materials.

This is an in-memory draft, not a registration, activation, reference adapter,
or authorization to collect judgments or evaluate models. Only explicitly
tagged invented material and the synthetic-test namespace are accepted. Every
declared real/evaluation scope is refused. The legacy generator's four exact
wording families are identified as one lineage; the pilot namespace is reserved
but material generation there is refused. The legacy API cannot supply a
separate pilot family while retaining its structure validator. Whether any
pilot is truly lineage-disjoint from a future test remains unresolved.

The invented tag is a caller assertion, not proof of origin. Caller-supplied
32-byte HMAC material is checked against a commitment and a few weak shapes
are rejected. Neither checks nor commitments prove entropy,
secrecy, prior registration, source-code identity, independent verification,
or absence of prior wording exposure. Use a dedicated CSPRNG-generated secret;
the invented test fixtures are intentionally public and unsuitable for use.
HMAC seed IDs and independently domain-separated group/variant aliases resist
enumerating those IDs only while the key remains secret and unpredictable.
The dates and roles remain readable in the notices; this design cannot prevent
matching every visible text or prove that the intended target is hidden.

The reserve is fixed in opaque-ID order. Supported synthetic delivery requires
a programme-wide lock over every exact assigned and reserve view, after a full
preflight and an explicit caller assertion that no feedback was seen before
the lock. Standalone seed/variant delivery is disabled. This in-memory ordering
and caller-supplied commitment cannot prove prior registration, actual timing,
absence of external feedback, or independent authentication. No replacement,
adjudication, feedback, or outcome interface is implemented; external use could
still choose adaptively. Lock issuance is in-memory only and is not a durable
audit trail. The manifest binds exact view values and their canonical JSON, not
downstream transport bytes. Disclosure checks cover common encodings, not all
transformations or side channels. Internal attributes contain private IDs and
factors and must never be sent or logged as a judge view. Python privacy and redacted
reprs are not a security boundary. There is deliberately no integration with
the existing machine-reference, annotation, or evaluation interfaces. The
original SHA primary-orientation rule does not guarantee balanced counts of
first/last primary orientations across seeds.

The in-memory factory refuses a new lock for an identical programme after any
supported view delivery during this loaded module's lifetime. Reloading the
module or loading another copy resets that local registry, even in one process.
It cannot detect external feedback, prior exposure, or events in another process.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from threading import RLock
from weakref import WeakKeyDictionary

from . import role_materials as original


GENERATOR_VERSION = "role-generator-v2-synthetic-candidate-2"
INVENTED_MATERIAL_TAG = "invented-synthetic-test-only"
TEST_NAMESPACE = "synthetic-test-v2"
PILOT_NAMESPACE = "synthetic-pilot-v2"
WORDING_LINEAGE = "role-materials-draft-v1-existing-families"

_ORIGINAL_VERSION = "role-generator-draft-v1"
_ORIGINAL_SEED = 20261011
_FAMILIES = (
    "Current recovery is expected on {target}.",
    "The current recovery estimate is {target}.",
    "Supply recovery is currently estimated for {target}.",
    "The present supply recovery target is {target}.",
)
_POSITIONS = ("first", "last")
_ARMS = ("competitor", "neutral")
_CELLS = tuple((family, order) for family in range(4) for order in ("earlier", "later"))
_RESERVE_COUNT = 16
_DOMAINS = frozenset({"private-seed", "group-alias", "variant-alias", "private-manifest", "synthetic-lock"})


class PilotIntegrationUnresolved(ValueError):
    """The reserved pilot namespace cannot currently render disjoint families."""


class _PrivateRoleVariant(original.RoleVariant):
    """The inherited fields remain private; do not log or serialize them."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "_PrivateRoleVariant(<private synthetic record>)"

    def model_input(self) -> dict[str, str]:
        raise ValueError("private variant delivery is disabled; use the synthetic programme lock")

    @property
    def model_input_sha256(self) -> str:
        raise ValueError("private variant delivery is disabled; use the synthetic programme lock")


class _PrivateRoleSeed(original.RoleSeed):
    """Legacy structure with a redacted repr, not a secrecy boundary."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "_PrivateRoleSeed(<private synthetic record>)"


def _redact_source(source: original.RoleSeed) -> _PrivateRoleSeed:
    if type(source) is _PrivateRoleSeed:
        return source
    if type(source) is not original.RoleSeed or type(source.variants) is not tuple:
        raise TypeError("the exact original role-seed structure is required")
    if any(type(variant) is not original.RoleVariant for variant in source.variants):
        raise TypeError("the exact original role-variant structures are required")
    variants = tuple(_PrivateRoleVariant(variant.item_id, variant.seed_id, variant.arm, variant.position,
                                         variant.primary, variant.update_date, variant.notice_text)
                     for variant in source.variants)
    return _PrivateRoleSeed(source.seed_id, source.wording_family, source.competing_order, source.update_date,
                            source.publication_date, source.superseded_issue_date, source.superseded_target_date,
                            source.target_date, source.competing_date, variants)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _disclosure_tokens(key: bytes, seed_ids: tuple[str, ...]) -> frozenset[str]:
    """Common literal/encoded forms, not a guarantee against every transformation."""
    tokens = set(seed_ids)
    tokens.update(value.upper() for value in seed_ids)
    tokens.update((key.hex(), key.hex().upper()))
    for encoded in (base64.b64encode(key).decode("ascii"), base64.urlsafe_b64encode(key).decode("ascii")):
        tokens.update((encoded, encoded.rstrip("=")))
    byte_repr = repr(key)
    tokens.update((byte_repr, byte_repr[2:-1]))
    for encoding in ("utf-8", "latin-1"):
        try:
            decoded = key.decode(encoding)
        except UnicodeDecodeError:
            continue
        layer = {decoded}
        # Include raw, quoted, and escaped JSON/Python forms at two levels;
        # scanning the actual value and its canonical JSON handles both normal
        # serialization and an already-escaped string in the value.
        for _ in range(2):
            tokens.update(layer)
            next_layer = set()
            for text in layer:
                for quoted in (repr(text), json.dumps(text, ensure_ascii=True),
                               json.dumps(text, ensure_ascii=False)):
                    next_layer.update((quoted, quoted[1:-1]))
            layer = next_layer
        tokens.update(layer)
    return frozenset(token for token in tokens if token)


def _export_strings(value: object):
    if type(value) is str:
        yield value
    elif type(value) in {tuple, list}:
        for item in value:
            yield from _export_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("exported dictionary keys must be strings")
            yield key
            yield from _export_strings(item)
    elif value is not None and type(value) not in {bool, int}:
        raise TypeError("exported values must be JSON primitives")


def _assert_safe_export(tokens: frozenset[str], value: object) -> None:
    # The Python repr can combine structural punctuation and separate fields;
    # checking fields and canonical JSON alone misses that representation.
    strings = (*_export_strings(value), _canonical(value), repr(value))
    normalized_tokens = tuple(unicodedata.normalize("NFKC", token).casefold() for token in tokens)
    normalized_strings = tuple(unicodedata.normalize("NFKC", text).casefold() for text in strings)
    if any(not token for token in normalized_tokens) or any(
        token in text for token in normalized_tokens for text in normalized_strings
    ):
        raise ValueError("private seed or HMAC material cannot enter an exported view or receipt")


def _frame(*parts: bytes) -> bytes:
    """Unambiguous length-prefixed HMAC/commitment input."""
    return b"".join(len(part).to_bytes(4, "big") + part for part in parts)


def _require_sha256(value: object, name: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA256")


def _check_material(value: object) -> None:
    if type(value) is not bytes:
        raise TypeError("private HMAC material must be bytes")
    if (len(value) != 32 or len(set(value)) < 16
            or any(value == value[:size] * (32 // size) for size in (1, 2, 4, 8, 16))):
        raise ValueError("private HMAC material has a weak or invalid 32-byte shape; shape is not entropy")


def _material_commitment(material: bytes) -> str:
    _check_material(material)
    return hashlib.sha256(_frame(b"collie-role-v2-material-commitment", material)).hexdigest()


def material_commitment_sha256(material: bytes) -> str:
    """Commit to caller material; this does not certify its randomness or secrecy."""
    commitment = _material_commitment(material)
    _assert_safe_export(_disclosure_tokens(material, ()), commitment)
    return commitment


class PrivateMaterial:
    """Private, explicitly invented-only HMAC material, not a secrecy boundary."""

    __slots__ = ("_material", "_commitment", "_tag")

    def __init__(self, *, material: bytes, expected_commitment_sha256: str, material_tag: str) -> None:
        if type(material_tag) is not str or material_tag != INVENTED_MATERIAL_TAG:
            raise ValueError("an explicit invented synthetic-test-only material tag is required")
        _require_sha256(expected_commitment_sha256, "material commitment")
        actual = material_commitment_sha256(material)
        if not hmac.compare_digest(actual, expected_commitment_sha256):
            raise ValueError("private HMAC material does not match its commitment")
        object.__setattr__(self, "_material", material)
        object.__setattr__(self, "_commitment", actual)
        object.__setattr__(self, "_tag", material_tag)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("private HMAC material is immutable")

    def __repr__(self) -> str:
        return "PrivateMaterial(<private synthetic material>)"

    def __copy__(self) -> None:
        raise TypeError("private HMAC material cannot be copied or serialized")

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("private HMAC material cannot be copied or serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        raise TypeError("private HMAC material cannot be copied or serialized")

    def _validate(self) -> None:
        if type(self) is not PrivateMaterial:
            raise TypeError("exact private material is required")
        if self._tag != INVENTED_MATERIAL_TAG:
            raise ValueError("invented synthetic material tag changed")
        _require_sha256(self._commitment, "material commitment")
        actual = _material_commitment(self._material)
        if not hmac.compare_digest(actual, self._commitment):
            raise ValueError("private HMAC material does not match its commitment")

    @property
    def commitment_sha256(self) -> str:
        self._validate()
        _assert_safe_export(_disclosure_tokens(self._material, ()), self._commitment)
        return self._commitment

    def _mac(self, domain: str, *parts: str) -> str:
        self._validate()
        if type(domain) is not str or domain not in _DOMAINS:
            raise ValueError("unknown HMAC domain")
        if any(type(part) is not str for part in parts):
            raise TypeError("HMAC context must contain exact strings")
        fields = ("collie-role-generator-v2", GENERATOR_VERSION, INVENTED_MATERIAL_TAG,
                  "synthetic", domain, *parts)
        message = _frame(*(part.encode("utf-8") for part in fields))
        return hmac.new(self._material, message, hashlib.sha256).hexdigest()


def _check_original_lineage() -> None:
    if (original.GENERATOR_VERSION != _ORIGINAL_VERSION or original.SEED != _ORIGINAL_SEED
            or original.FAMILIES != _FAMILIES or original.POSITIONS != _POSITIONS or original.ARMS != _ARMS):
        raise ValueError("original generator or wording-family lineage changed; review is required")


def wording_lineage_sha256() -> str:
    """Identify exact legacy family strings, not semantic novelty or source identity."""
    _check_original_lineage()
    value = {"kind": "role-wording-lineage-v1", "lineage": WORDING_LINEAGE,
             "generator_version": _ORIGINAL_VERSION, "families": _FAMILIES}
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _check_scope(scope: object) -> None:
    if type(scope) is not str or scope != "synthetic":
        raise ValueError("real and evaluation scopes are disabled; synthetic only")


def _check_namespace(namespace: object) -> None:
    if type(namespace) is not str or namespace not in {TEST_NAMESPACE, PILOT_NAMESPACE}:
        raise ValueError("an explicit synthetic test or reserved pilot namespace is required")


def _package_count(package: object) -> int:
    if type(package) is not str or package not in {"full", "reduced"}:
        raise ValueError("package must be full or reduced")
    return 80 if package == "full" else 50


def _phase_count(package: str, phase: object) -> int:
    count = _package_count(package)
    if type(phase) is not str or phase not in {"assigned", "reserve"}:
        raise ValueError("phase must be assigned or reserve")
    return count if phase == "assigned" else _RESERVE_COUNT


def _private_seed_id(material: PrivateMaterial, namespace: str, package: str, phase: str, ordinal: int) -> str:
    """Internal ID derivation; a pilot ID alone does not render pilot material."""
    if type(material) is not PrivateMaterial:
        raise TypeError("exact private material is required")
    _check_namespace(namespace)
    count = _phase_count(package, phase)
    if type(ordinal) is not int or not 1 <= ordinal <= count:
        raise ValueError("seed ordinal is outside its fixed phase")
    return material._mac("private-seed", namespace, wording_lineage_sha256(), package, phase, str(ordinal))


def _allocation(
    material: PrivateMaterial, namespace: str, package: str, phase: str,
) -> tuple[tuple[int, str, int, str], ...]:
    """Freeze the full allocation, without accepting judgments or outcomes."""
    count = _phase_count(package, phase)
    identities = tuple((i, _private_seed_id(material, namespace, package, phase, i))
                       for i in range(1, count + 1))
    if len({seed_id for _, seed_id in identities}) != count:
        raise ValueError("private seed collision; the fixed programme is refused")
    ordered = sorted(identities, key=lambda item: (
        hashlib.sha256(f"{_ORIGINAL_SEED}|role-allocation-v1|{phase}|{item[1]}".encode()).hexdigest(),
        item[1],
    ))
    if count == 50:
        # Six complete eight-cell blocks, plus one earlier and one later in
        # different families: 25/25 date orders and family totals 13/13/12/12.
        cells = _CELLS * 6 + (_CELLS[0], _CELLS[3])
    else:
        cells = _CELLS * (count // len(_CELLS))
    return tuple((ordinal, seed_id, family, order)
                 for (ordinal, seed_id), (family, order) in zip(ordered, cells, strict=True))


def _group_alias(seed: SyntheticRoleSeed) -> str:
    return "G" + seed._material._mac("group-alias", seed.namespace, seed.package, seed.phase,
                                     seed._source.seed_id)


def _variant_alias(seed: SyntheticRoleSeed, variant: original.RoleVariant) -> str:
    return "V" + seed._material._mac("variant-alias", seed.namespace, seed.package, seed.phase,
                                     seed._source.seed_id, variant.arm, variant.position)


def _project_visible(seed: SyntheticRoleSeed) -> dict[str, object]:
    """Construct a private projection for programme-wide preflight, not delivery."""
    notices = [{"item_id": _variant_alias(seed, variant),
                "update_date": variant.update_date.isoformat(), "notice_text": variant.notice_text}
               for variant in seed._source.variants]
    notices.sort(key=lambda item: item["item_id"])
    return {"synthetic_only": True, "group_id": _group_alias(seed), "notices": notices}


def _check_projection(seed: SyntheticRoleSeed, view: object, tokens: frozenset[str]) -> None:
    """Check the exact allowlisted projection as well as common disclosure forms."""
    _assert_safe_export(tokens, view)
    if type(view) is not dict or set(view) != {"synthetic_only", "group_id", "notices"}:
        raise ValueError("synthetic view has an invalid projection shape")
    if type(view["synthetic_only"]) is not bool or view["synthetic_only"] is not True:
        raise ValueError("synthetic view must retain its invented-only marker")
    group_id = view["group_id"]
    if (type(group_id) is not str or re.fullmatch(r"G[0-9a-f]{64}", group_id) is None
            or group_id != _group_alias(seed)):
        raise ValueError("synthetic group projection does not match")
    notices = view["notices"]
    if type(notices) is not list or len(notices) != 4:
        raise ValueError("synthetic view requires exactly four variants")
    expected = {_variant_alias(seed, variant): variant for variant in seed._source.variants}
    if len(expected) != 4:
        raise ValueError("variant alias collision; the seed is refused")
    ids = []
    for notice in notices:
        if (type(notice) is not dict or set(notice) != {"item_id", "update_date", "notice_text"}
                or any(type(value) is not str for value in notice.values())):
            raise ValueError("synthetic variant projection has an invalid shape")
        alias = notice["item_id"]
        if re.fullmatch(r"V[0-9a-f]{64}", alias) is None or alias not in expected:
            raise ValueError("synthetic variant alias does not match")
        variant = expected[alias]
        if (notice["update_date"] != variant.update_date.isoformat()
                or notice["notice_text"] != variant.notice_text):
            raise ValueError("synthetic variant projection differs from the locked material")
        ids.append(alias)
    if len(set(ids)) != 4 or ids != sorted(ids) or set(ids) != set(expected):
        raise ValueError("synthetic variant projection must use each alias in fixed opaque order")


def _preflight_projections(
    material: PrivateMaterial, assigned: tuple[SyntheticRoleSeed, ...], reserve: tuple[SyntheticRoleSeed, ...],
) -> tuple[tuple[dict[str, object], ...], frozenset[str]]:
    seeds = (*assigned, *reserve)
    tokens = _disclosure_tokens(material._material, tuple(seed._source.seed_id for seed in seeds))
    projections = []
    for seed in seeds:
        view = _project_visible(seed)
        _check_projection(seed, view, tokens)
        projections.append(view)
    _assert_safe_export(tokens, tuple(projections[:len(assigned)]))
    _assert_safe_export(tokens, tuple(projections[len(assigned):]))
    return tuple(projections), tokens


def _check_exact_original_material(source: original.RoleSeed) -> None:
    """Check the pinned date formula and rendering without trusting the renderer."""
    digest = hashlib.sha256(f"{_ORIGINAL_SEED}|role-dates-v1|{source.seed_id}".encode()).digest()
    update = date(2027, 1, 1) + timedelta(days=int.from_bytes(digest[:4], "big") % 730)
    target = update + timedelta(days=60 + digest[7] % 90)
    gap = 14 + digest[8] % 14
    sign = -1 if source.competing_order == "earlier" else 1
    actual_dates = (source.update_date, source.publication_date, source.superseded_issue_date,
                    source.superseded_target_date, source.target_date, source.competing_date)
    expected_dates = (update, update - timedelta(days=80 + digest[4] % 20),
                      update - timedelta(days=35 + digest[5] % 15),
                      update - timedelta(days=5 + digest[6] % 20), target,
                      target + timedelta(days=sign * gap))
    if actual_dates != expected_dates:
        raise ValueError("seed dates differ from the pinned original date formula")
    current = _FAMILIES[source.wording_family].format(target=target.isoformat())
    for variant in source.variants:
        other = "Next review" if variant.arm == "competitor" else "Data filing"
        background = (
            f"Published on {source.publication_date.isoformat()}.",
            f"The recovery estimate issued on {source.superseded_issue_date.isoformat()} was "
            f"{source.superseded_target_date.isoformat()} and is superseded.",
            f"{other} is scheduled on {source.competing_date.isoformat()}.",
        )
        expected = " ".join((current, *background) if variant.position == "first" else (*background, current))
        if variant.notice_text != expected:
            raise ValueError("notice rendering differs from the pinned original structure")


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRoleSeed:
    """Private synthetic record; standalone delivery is deliberately disabled."""

    namespace: str
    package: str
    phase: str
    ordinal: int
    _source: original.RoleSeed
    _material: PrivateMaterial

    def __post_init__(self) -> None:
        object.__setattr__(self, "_source", _redact_source(self._source))
        validate_synthetic_seed(self)

    def __repr__(self) -> str:
        return "SyntheticRoleSeed(<private synthetic record>)"

    @property
    def group_id(self) -> str:
        raise ValueError("standalone seed delivery is disabled; use the synthetic programme lock")

    def visible(self) -> dict[str, object]:
        raise ValueError("standalone seed delivery is disabled; use the synthetic programme lock")


def validate_synthetic_seed(seed: SyntheticRoleSeed) -> None:
    """Verify private allocation, legacy 2x2 structure, and exact regenerated bytes."""
    if type(seed) is not SyntheticRoleSeed or type(seed._material) is not PrivateMaterial:
        raise TypeError("an exact synthetic seed and private material are required")
    seed._material._validate()
    _check_original_lineage()
    _check_namespace(seed.namespace)
    if seed.namespace != TEST_NAMESPACE:
        raise PilotIntegrationUnresolved("pilot rendering is unresolved; legacy families cannot be reused")
    count = _phase_count(seed.package, seed.phase)
    if type(seed.ordinal) is not int or not 1 <= seed.ordinal <= count:
        raise ValueError("seed ordinal is outside its fixed phase")
    if type(seed._source) is not _PrivateRoleSeed or type(seed._source.variants) is not tuple:
        raise TypeError("the private original role-seed structure is required")
    if any(type(variant) is not _PrivateRoleVariant for variant in seed._source.variants):
        raise TypeError("the private original role-variant structures are required")
    expected = next(row for row in _allocation(seed._material, seed.namespace, seed.package, seed.phase)
                    if row[0] == seed.ordinal)
    _, seed_id, family, order = expected
    if (seed._source.seed_id, seed._source.wording_family, seed._source.competing_order) != (
        seed_id, family, order
    ):
        raise ValueError("private seed or locked factor allocation does not match")
    original.validate_structure(seed._source)
    _check_exact_original_material(seed._source)
    if seed._source != _redact_source(original._make_seed(seed_id, family, order)):
        raise ValueError("seed does not match the exact original generator")
    bit = hashlib.sha256(f"{_ORIGINAL_SEED}|role-primary-position|{seed_id}".encode()).digest()[0] >> 7
    if any(v.primary != (v.position == _POSITIONS[bit]) for v in seed._source.variants):
        raise ValueError("primary pair does not match the fixed SHA256 orientation")


def _manifest_seed(seed: SyntheticRoleSeed, projection: dict[str, object]) -> dict[str, object]:
    source = seed._source
    return {
        "ordinal": seed.ordinal, "private_seed_id": source.seed_id, "group_id": _group_alias(seed),
        "wording_family": source.wording_family, "competing_order": source.competing_order,
        "dates": [value.isoformat() for value in (
            source.update_date, source.publication_date, source.superseded_issue_date,
            source.superseded_target_date, source.target_date, source.competing_date,
        )],
        "variants": [{"private_item_id": variant.item_id, "alias": _variant_alias(seed, variant),
                      "arm": variant.arm, "position": variant.position, "primary": variant.primary,
                      "update_date": variant.update_date.isoformat(), "notice_text": variant.notice_text}
                     for variant in source.variants],
        "visible_projection": projection,
    }


def _manifest_commitment(
    material: PrivateMaterial, package: str, namespace: str,
    assigned: tuple[SyntheticRoleSeed, ...], reserve: tuple[SyntheticRoleSeed, ...],
    projections: tuple[dict[str, object], ...],
) -> str:
    seeds = (*assigned, *reserve)
    if len(projections) != len(seeds):
        raise ValueError("the private manifest needs every exact assigned and reserve projection")
    private_value = {
        "kind": "synthetic-private-role-programme-v2", "generator_version": GENERATOR_VERSION,
        "scope": "synthetic", "namespace": namespace, "package": package,
        "wording_lineage_sha256": wording_lineage_sha256(), "material_commitment_sha256": material.commitment_sha256,
        "reserve_rule": "fixed-opaque-order-no-replacement-or-feedback-interface-v1",
        "delivery_rule": "preflighted-programme-lock-only-v1",
        "assigned": [_manifest_seed(seed, view) for seed, view in zip(assigned, projections[:len(assigned)],
                                                                      strict=True)],
        "reserve": [_manifest_seed(seed, view) for seed, view in zip(reserve, projections[len(assigned):],
                                                                     strict=True)],
    }
    return material._mac("private-manifest", _canonical(private_value))


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRoleProgramme:
    """Committed private programme; the reserve has no replacement API."""

    scope: str
    namespace: str
    package: str
    wording_lineage_sha256: str
    material_commitment_sha256: str
    manifest_commitment_sha256: str
    assigned: tuple[SyntheticRoleSeed, ...]
    reserve: tuple[SyntheticRoleSeed, ...]
    _material: PrivateMaterial

    def __post_init__(self) -> None:
        validate_synthetic_programme(self)

    def __repr__(self) -> str:
        return "SyntheticRoleProgramme(<private synthetic programme>)"

    def verify_manifest(self, expected_commitment_sha256: str) -> None:
        validate_synthetic_programme(self)
        _require_sha256(expected_commitment_sha256, "programme manifest commitment")
        if not hmac.compare_digest(self.manifest_commitment_sha256, expected_commitment_sha256):
            raise ValueError("programme manifest commitment does not match")


class SyntheticRoleLock:
    """Synthetic-only lock; its caller attestation is not evidence of timing."""

    __slots__ = ("_programme", "_manifest", "_lock_commitment", "__weakref__")

    def __init__(self) -> None:
        raise TypeError("use lock_synthetic_programme to create a synthetic lock")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("synthetic lock is immutable")

    def __repr__(self) -> str:
        return "SyntheticRoleLock(<private synthetic lock>)"

    def __copy__(self) -> None:
        raise TypeError("synthetic locks cannot be copied or serialized")

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("synthetic locks cannot be copied or serialized")

    def __reduce_ex__(self, protocol: int) -> None:
        raise TypeError("synthetic locks cannot be copied or serialized")

    def receipt(self) -> dict[str, object]:
        """Return a checked receipt, not proof of prior registration or timing."""
        _, receipt, _ = _checked_lock(self)
        return receipt

    def visible(self, seed: SyntheticRoleSeed) -> dict[str, object]:
        """Return one exact preflighted view only for a member of this lock."""
        if type(seed) is not SyntheticRoleSeed:
            raise TypeError("an exact synthetic seed is required")
        projections, _, _ = _checked_lock(self)
        seeds = (*self._programme.assigned, *self._programme.reserve)
        for index, member in enumerate(seeds):
            if seed is member:
                _record_delivery(self._programme)
                return projections[index]
        raise ValueError("seed is not bound to this synthetic programme lock")

    def visible_views(self, phase: str) -> tuple[dict[str, object], ...]:
        """Return a phase's exact views after rechecking the whole programme."""
        if type(phase) is not str or phase not in {"assigned", "reserve"}:
            raise ValueError("phase must be assigned or reserve")
        projections, _, tokens = _checked_lock(self)
        split = len(self._programme.assigned)
        views = projections[:split] if phase == "assigned" else projections[split:]
        _assert_safe_export(tokens, views)
        _record_delivery(self._programme)
        return views


def _lock_commitment(programme: SyntheticRoleProgramme, manifest: str) -> str:
    return programme._material._mac("synthetic-lock", programme.scope, programme.namespace, programme.package,
                                    manifest, "caller-asserts-no-feedback-before-lock")


_ISSUED_LOCKS: WeakKeyDictionary = WeakKeyDictionary()
_DELIVERED_PROGRAMMES: set[tuple[str, ...]] = set()
_DELIVERY_MUTEX = RLock()


def _programme_identity(programme: SyntheticRoleProgramme) -> tuple[str, ...]:
    return (GENERATOR_VERSION, programme.scope, programme.namespace, programme.package,
            programme.material_commitment_sha256, programme.manifest_commitment_sha256)


def _record_delivery(programme: SyntheticRoleProgramme) -> None:
    with _DELIVERY_MUTEX:
        _DELIVERED_PROGRAMMES.add(_programme_identity(programme))


def _lock_receipt(lock: SyntheticRoleLock) -> dict[str, object]:
    programme = lock._programme
    return {"kind": "synthetic-programme-lock-receipt-v1", "synthetic_only": True,
            "generator_version": GENERATOR_VERSION, "scope": programme.scope, "namespace": programme.namespace,
            "package": programme.package, "wording_lineage_sha256": programme.wording_lineage_sha256,
            "material_commitment_sha256": programme.material_commitment_sha256,
            "manifest_commitment_sha256": lock._manifest, "lock_commitment_sha256": lock._lock_commitment,
            "feedback_not_seen_caller_attestation": True}


def _checked_lock(
    lock: SyntheticRoleLock,
) -> tuple[tuple[dict[str, object], ...], dict[str, object], frozenset[str]]:
    if type(lock) is not SyntheticRoleLock:
        raise TypeError("an exact synthetic programme lock is required")
    issued = _ISSUED_LOCKS.get(lock)
    if issued is None:
        raise ValueError("synthetic lock was not issued by this in-memory factory")
    try:
        programme, manifest, commitment = lock._programme, lock._manifest, lock._lock_commitment
    except AttributeError as exc:
        raise ValueError("synthetic lock is incomplete") from exc
    _require_sha256(manifest, "locked programme manifest commitment")
    _require_sha256(commitment, "synthetic lock commitment")
    projections, tokens = _checked_programme(programme)
    if not hmac.compare_digest(manifest, programme.manifest_commitment_sha256):
        raise ValueError("synthetic lock does not match the programme manifest")
    if not hmac.compare_digest(commitment, _lock_commitment(programme, manifest)):
        raise ValueError("synthetic lock commitment does not match")
    if programme is not issued[0] or manifest != issued[1] or commitment != issued[2]:
        raise ValueError("synthetic lock differs from its in-memory issuance")
    receipt = _lock_receipt(lock)
    _assert_safe_export(tokens, receipt)
    expected = {"kind": "synthetic-programme-lock-receipt-v1", "synthetic_only": True,
                "generator_version": GENERATOR_VERSION, "scope": programme.scope, "namespace": programme.namespace,
                "package": programme.package, "wording_lineage_sha256": programme.wording_lineage_sha256,
                "material_commitment_sha256": programme.material_commitment_sha256,
                "manifest_commitment_sha256": manifest, "lock_commitment_sha256": commitment,
                "feedback_not_seen_caller_attestation": True}
    if (type(receipt) is not dict or receipt != expected
            or type(receipt.get("synthetic_only")) is not bool
            or type(receipt.get("feedback_not_seen_caller_attestation")) is not bool):
        raise ValueError("synthetic lock receipt does not match its exact projection")
    return projections, receipt, tokens


def lock_synthetic_programme(
    programme: SyntheticRoleProgramme, *, expected_manifest_commitment_sha256: str, feedback_seen: bool,
) -> SyntheticRoleLock:
    """Issue a lock only after full preflight and a caller's no-feedback assertion.

    The assertion and expected commitment do not independently establish when
    any feedback was seen, a registration, or independent authentication.
    """
    if type(feedback_seen) is not bool:
        raise TypeError("feedback_seen must be an explicit boolean caller assertion")
    if feedback_seen:
        raise ValueError("a synthetic programme cannot be locked after declared feedback exposure")
    _require_sha256(expected_manifest_commitment_sha256, "expected programme manifest commitment")
    _checked_programme(programme)
    if not hmac.compare_digest(expected_manifest_commitment_sha256, programme.manifest_commitment_sha256):
        raise ValueError("expected programme manifest commitment does not match")
    with _DELIVERY_MUTEX:
        if _programme_identity(programme) in _DELIVERED_PROGRAMMES:
            raise ValueError("a new synthetic lock cannot be issued after programme view delivery")
        lock = object.__new__(SyntheticRoleLock)
        object.__setattr__(lock, "_programme", programme)
        object.__setattr__(lock, "_manifest", expected_manifest_commitment_sha256)
        object.__setattr__(lock, "_lock_commitment", _lock_commitment(programme, expected_manifest_commitment_sha256))
        _ISSUED_LOCKS[lock] = (programme, lock._manifest, lock._lock_commitment)
        try:
            _checked_lock(lock)
        except Exception:
            _ISSUED_LOCKS.pop(lock, None)
            raise
        return lock


def validate_synthetic_programme(programme: SyntheticRoleProgramme) -> None:
    """Preflight the complete programme and its exact views; return no material."""
    _checked_programme(programme)


def _checked_programme(
    programme: SyntheticRoleProgramme,
) -> tuple[tuple[dict[str, object], ...], frozenset[str]]:
    if type(programme) is not SyntheticRoleProgramme or type(programme._material) is not PrivateMaterial:
        raise TypeError("an exact synthetic programme and private material are required")
    _check_scope(programme.scope)
    _check_namespace(programme.namespace)
    if programme.namespace != TEST_NAMESPACE:
        raise PilotIntegrationUnresolved("pilot rendering is unresolved; legacy families cannot be reused")
    count = _package_count(programme.package)
    _require_sha256(programme.wording_lineage_sha256, "wording lineage")
    if not hmac.compare_digest(programme.wording_lineage_sha256, wording_lineage_sha256()):
        raise ValueError("wording lineage does not match the fixed legacy families")
    _require_sha256(programme.material_commitment_sha256, "material commitment")
    if not hmac.compare_digest(programme.material_commitment_sha256, programme._material.commitment_sha256):
        raise ValueError("private HMAC material commitment does not match")
    _require_sha256(programme.manifest_commitment_sha256, "programme manifest commitment")
    if type(programme.assigned) is not tuple or type(programme.reserve) is not tuple:
        raise TypeError("assigned and reserve must be fixed tuples")
    if len(programme.assigned) != count or len(programme.reserve) != _RESERVE_COUNT:
        raise ValueError("programme needs the complete fixed assigned and reserve sets")
    for phase, collection in (("assigned", programme.assigned), ("reserve", programme.reserve)):
        for seed in collection:
            validate_synthetic_seed(seed)
            if (seed._material is not programme._material or seed.namespace != programme.namespace
                    or seed.package != programme.package or seed.phase != phase):
                raise ValueError("seed does not belong to this fixed programme and phase")
        if {seed.ordinal for seed in collection} != set(range(1, len(collection) + 1)):
            raise ValueError("seed ordinals must cover the fixed phase exactly once")
        groups = [_group_alias(seed) for seed in collection]
        if groups != sorted(groups):
            raise ValueError("programme and reserve must use the fixed opaque group order")
    seeds = (*programme.assigned, *programme.reserve)
    if len({seed._source.seed_id for seed in seeds}) != len(seeds):
        raise ValueError("private seed IDs must be unique across assigned and reserve")
    groups = [_group_alias(seed) for seed in seeds]
    aliases = [_variant_alias(seed, variant) for seed in seeds for variant in seed._source.variants]
    texts = [variant.notice_text for seed in seeds for variant in seed._source.variants]
    if len(set(groups)) != len(groups) or len(set(aliases)) != len(aliases) or len(set(texts)) != len(texts):
        raise ValueError("group, variant, or notice collision; the fixed programme is refused")
    assigned_cells = Counter((seed._source.wording_family, seed._source.competing_order)
                             for seed in programme.assigned)
    expected_cells = Counter(_CELLS * (10 if count == 80 else 6))
    if count == 50:
        expected_cells.update((_CELLS[0], _CELLS[3]))
    reserve_cells = Counter((seed._source.wording_family, seed._source.competing_order)
                            for seed in programme.reserve)
    if assigned_cells != expected_cells or reserve_cells != Counter(_CELLS * 2):
        raise ValueError("fixed wording and date-order factor balance is invalid")
    projections, tokens = _preflight_projections(programme._material, programme.assigned, programme.reserve)
    header = {"synthetic_only": True, "generator_version": GENERATOR_VERSION, "scope": programme.scope,
              "namespace": programme.namespace, "package": programme.package,
              "wording_lineage_sha256": programme.wording_lineage_sha256,
              "material_commitment_sha256": programme.material_commitment_sha256,
              "manifest_commitment_sha256": programme.manifest_commitment_sha256}
    _assert_safe_export(tokens, header)
    actual = _manifest_commitment(programme._material, programme.package, programme.namespace,
                                  programme.assigned, programme.reserve, projections)
    if not hmac.compare_digest(actual, programme.manifest_commitment_sha256):
        raise ValueError("programme manifest commitment does not match the fixed material")
    return projections, tokens


def synthetic_role_programme(
    package: str, *, material: PrivateMaterial, scope: str, namespace: str, expected_lineage_sha256: str,
) -> SyntheticRoleProgramme:
    """Build only a fictional test programme; pilot and real/evaluation fail closed."""
    _check_scope(scope)
    _check_namespace(namespace)
    if namespace == PILOT_NAMESPACE:
        raise PilotIntegrationUnresolved("pilot rendering is unresolved; legacy families cannot be reused")
    _package_count(package)
    if type(material) is not PrivateMaterial:
        raise TypeError("exact private material is required")
    material._validate()
    _require_sha256(expected_lineage_sha256, "expected wording lineage")
    if not hmac.compare_digest(expected_lineage_sha256, wording_lineage_sha256()):
        raise ValueError("expected wording lineage does not match the fixed legacy families")

    def build(phase: str) -> tuple[SyntheticRoleSeed, ...]:
        seeds = tuple(SyntheticRoleSeed(namespace, package, phase, ordinal,
                                        original._make_seed(seed_id, family, order), material)
                      for ordinal, seed_id, family, order in _allocation(material, namespace, package, phase))
        return tuple(sorted(seeds, key=_group_alias))

    assigned, reserve = build("assigned"), build("reserve")
    projections, _ = _preflight_projections(material, assigned, reserve)
    manifest = _manifest_commitment(material, package, namespace, assigned, reserve, projections)
    return SyntheticRoleProgramme("synthetic", namespace, package, wording_lineage_sha256(),
                                  material.commitment_sha256, manifest, assigned, reserve, material)
