"""Candidate, outcome-free evidence gate for the follow-up exclusion catalog.

This module opens no paths. Callers supply canonical inventory bytes, evidence
identities, an independently recorded regeneration, and compressed open-event
bytes. A ``ready`` decision means only that these supplied artifacts satisfy
the checks below; it is not proof of exposure coverage, attestation authenticity,
owner approval, or a pushed registration. Public direct draws are disabled, but
private Python capabilities remain accessible; this is not an access-control boundary.
The supplied expected statement-set digest is SHA256 of the canonical JSON
array of sorted IDs; it is not assumed to use a historical roster's hash format.
The gate does not independently compare that supplied digest with a previous
inventory, an assigned roster, or an external evidence document. Non-corpus
pilot/role identities require a separate lineage registry, not a fabricated
statement ID in this catalog.
The event projector parses the supplied compressed table before discarding
extra columns. A matching digest does not establish that the table is open or
authorize reading protected, outcome, or later-capture data.
All item, event, episode, and evidence identities exported here are keyed HMAC
aliases. Supply a securely generated secret of at least 32 bytes; this module
can check only its type and length, not its entropy. Retain the secret and the
verified input privately for a reversible crosswalk, and review disclosure.

Fragment entries contain only a normalized-text hash and its token count. Old
whole-field hashes are not silently assigned lengths: every one must also have
a counted fragment entry recomputed from separately supplied fragment-source
bytes. The same private source also supplies notice and statement preimages for
versioned regeneration, backed by an authorization attestation. Those bytes are private inputs,
not evidence that authorization is genuine. Actual phrase text must never be
included in an inventory, receipt, manifest, or object representation.
Inventories must declare the new domain-separated fingerprint version and be
regenerated from separately authorized, hash-verified sources. Legacy V3 hashes
are not compatible and must not be relabeled as this version.
The fragment minimum and blank-pair policy are candidate proposals, not
registered or owner-approved sampling choices.

The optional N/C wrappers use the original sampler transiently and return only
hash/ID manifests, not projected events, source bytes, or notice text. Each call
requires the supplied request again and rechecks its actual compressed bytes.
They apply the explicitly recorded conservative policy to all presentations
before the display-row rule. Known whole-notice and domain-tagged statement
fingerprints are likewise propagated to the whole group with their source
categories preserved. C uses all presentations of the retained N groups and
does not redraw N. Draw proofs are in-process tamper guards, not signatures or
a cross-process resume mechanism; a lost proof fails closed rather than redraws.
C additionally requires a pre-access N-manifest lock and a separately supplied
immutable keyed record anchor. The lock, anchor, and claimed timing are supplied
evidence, not proof of registration or approval.
The protocol commitment includes live Python code, defaults and supported closure values and the
declared N/C parameters and expressions; it is not an authenticated source
release or verification of external dependencies and execution environment.
Every exported data-derived digest is a domain-separated keyed commitment;
raw hashes and crosswalks remain private and are not anonymous. Keyed outputs
do not protect privacy if the key is weak, disclosed, or improperly reused.
The blank-policy anchor is an implementation container, not evidence that a blank
item originated in that category; retain the separate policy-reason overlay.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import types
from dataclasses import asdict, dataclass, field
from typing import Any

from . import sampling


SOURCE_SCHEMA = "followup-exclusion-source-v2"
FRAGMENT_SOURCE_SCHEMA = "followup-fingerprint-source-v2"
RECEIPT_SCHEMA = "followup-catalog-gate-v4"
MANIFEST_SCHEMA = "followup-gated-sample-v4"
N_COMMITMENT_SCHEMA = "followup-frozen-n-v2"
FRAGMENT_MODE = "normalized_contiguous_windows"
BLANK_MODE = "exclude_empty_visible_pair_any_presentation"
FRAGMENT_FIELDS = ("availability_text", "related_text", "statement_text")
MIN_FRAGMENT_TOKENS = 3
_CLAIMS = frozenset({"coverage_complete", "empty_after_review", "fragment_from_authorized_source",
                     "fingerprints_from_authorized_source"})
_EVIDENCE_KINDS = frozenset({"source_record", "fragment_source"})
_READY_TOKEN = object()
_DRAW_TOKEN = object()
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """Canonical UTF-8 JSON for inventory, provenance, and receipt identities."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Raw hash for private input verification; never a disclosure artifact."""
    if not isinstance(value, bytes):
        raise TypeError("a digest input must be bytes")
    return hashlib.sha256(value).hexdigest()


class _PrivateRepr:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<private>)"


@dataclass(frozen=True, slots=True, repr=False)
class EvidenceIdentity(_PrivateRepr):
    identity: str
    kind: str
    document_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class Attestation(_PrivateRepr):
    identity: str
    attester_identity: str
    document_sha256: str
    category: str
    claims: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class SourceProvenance(_PrivateRepr):
    category: str
    source_identity: str
    evidence: tuple[EvidenceIdentity, ...]
    attestations: tuple[Attestation, ...]
    expected_statement_count: int
    expected_statement_set_sha256: str
    empty_rationale: str | None = field(repr=False)
    unresolved_count: int
    unmapped_count: int


@dataclass(frozen=True, slots=True, repr=False)
class RegenerationRecord(_PrivateRepr):
    category: str
    identity: str
    regenerator_identity: str
    method_sha256: str
    events_sha256: str
    fragment_source_sha256: str | None
    provenance_sha256: str
    source_inventory_sha256: str
    regenerated_inventory_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class SourceBundle(_PrivateRepr):
    category: str
    inventory_bytes: bytes = field(repr=False)
    inventory_sha256: str
    regenerated_inventory_bytes: bytes = field(repr=False)
    regenerated_inventory_sha256: str
    provenance: SourceProvenance = field(repr=False)
    provenance_sha256: str
    fragment_source_bytes: bytes | None = field(repr=False)
    regeneration: RegenerationRecord = field(repr=False)
    regeneration_sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class CatalogPolicy(_PrivateRepr):
    """All choices are explicit; the minimum is fixed for one catalog."""

    fragment_mode: str
    min_fragment_tokens: int
    blank_mode: str
    blank_anchor_category: str


@dataclass(frozen=True, slots=True, repr=False)
class CatalogRequest(_PrivateRepr):
    declared_status: str
    expected_events_sha256: str
    compressed_events: bytes = field(repr=False)
    sources: tuple[SourceBundle, ...] = field(repr=False)
    policy: CatalogPolicy
    alias_key: bytes = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class FrozenNCommitment(_PrivateRepr):
    """Caller-supplied pre-access record and independently retained anchors."""

    record_bytes: bytes = field(repr=False)
    expected_record_commitment: str
    expected_n_manifest_commitment: str
    evidence_identity: str = field(repr=False)
    evidence_sha256: str = field(repr=False)


@dataclass(frozen=True, slots=True, repr=False)
class FragmentFingerprint(_PrivateRepr):
    sha256: str
    token_count: int


def fingerprint_fragment(text: str, *, min_tokens: int) -> FragmentFingerprint:
    """Return only a normalized fragment hash and token count, never the text."""
    if not isinstance(text, str) or type(min_tokens) is not int or min_tokens < MIN_FRAGMENT_TOKENS:
        raise ValueError("a fragment requires text and a valid fixed minimum")
    tokens = sampling._wording(text).split()
    if len(tokens) < min_tokens:
        raise ValueError("fragment is shorter than the fixed minimum")
    return FragmentFingerprint(sampling._field_fingerprint_normalized(" ".join(tokens)), len(tokens))


@dataclass(frozen=True, slots=True)
class _ValidatedSource:
    source: sampling.ExclusionSource
    fragments: tuple[FragmentFingerprint, ...]


@dataclass(frozen=True, slots=True)
class _ReadyState:
    events: tuple[sampling.SourceEvent, ...] = field(repr=False)
    sources: tuple[_ValidatedSource, ...] = field(repr=False)
    receipt_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class CatalogDecision:
    status: str
    issues: tuple[str, ...]
    gate_commitment: str | None
    policy_commitment: str | None
    protocol_commitment: str | None = None
    _receipt_bytes: bytes | None = field(default=None, repr=False, compare=False)
    _proof: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _DrawProof:
    manifest_commitment: str
    marker: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class GatedDraw:
    """Only an ID/hash manifest is retained; no notice or phrase text is stored."""

    cohort: str
    package: str
    gate_commitment: str
    policy_commitment: str
    protocol_commitment: str
    policy_overlay_commitment: str
    n_wording_overlay_commitment: str
    sample_commitment: str
    _manifest_bytes: bytes = field(repr=False, compare=False)
    _proof: object | None = field(default=None, repr=False, compare=False)


class _Problem(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise _Problem(code)


def _identifier(value: object, code: str) -> None:
    _require(isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None
             and not value.startswith(sampling._RESERVED_PREFIXES), code)


def _sha(value: object, code: str, *, evidence: bool = False) -> None:
    _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None, code)
    if evidence:
        _require(value not in {"0" * 64, _EMPTY_SHA256}, code)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _sorted_strings(value: object, code: str, *, hashes: bool = False) -> tuple[str, ...]:
    _require(type(value) is list and all(isinstance(item, str) for item in value), code)
    _require(value == sorted(value) and len(value) == len(set(value)), code)
    for item in value:
        if hashes:
            _sha(item, code)
        else:
            try:
                sampling.require_private_id(item, "inventory id")
            except sampling.PrivateIdentifierError:
                raise _Problem(code) from None
    return tuple(value)


def _parse_inventory(bundle: SourceBundle, expected_events: str, policy: CatalogPolicy) -> tuple[
    tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[FragmentFingerprint, ...]
]:
    _require(type(bundle.inventory_bytes) is bytes, "inventory_invalid")
    _sha(bundle.inventory_sha256, "inventory_hash_invalid")
    _require(sha256_bytes(bundle.inventory_bytes) == bundle.inventory_sha256, "inventory_hash_mismatch")
    try:
        payload = json.loads(bundle.inventory_bytes.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid constant")))
        canonical = canonical_json_bytes(payload)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _Problem("inventory_invalid") from None
    _require(type(payload) is dict and canonical == bundle.inventory_bytes, "inventory_not_canonical")
    _require(set(payload) == {"schema", "fingerprint_version", "category", "events_sha256", "provenance_sha256",
                              "statement_ids", "notice_fingerprints", "whole_field_fingerprints",
                              "fragments"}, "inventory_schema_invalid")
    _require(payload["schema"] == SOURCE_SCHEMA and payload["category"] == bundle.category,
             "inventory_identity_mismatch")
    _require(payload["fingerprint_version"] == sampling.FINGERPRINT_VERSION, "fingerprint_version_mismatch")
    _require(payload["events_sha256"] == expected_events, "inventory_events_mismatch")
    _require(payload["provenance_sha256"] == bundle.provenance_sha256, "inventory_provenance_mismatch")
    ids = _sorted_strings(payload["statement_ids"], "inventory_ids_invalid")
    notices = _sorted_strings(payload["notice_fingerprints"], "inventory_fingerprints_invalid", hashes=True)
    whole = _sorted_strings(payload["whole_field_fingerprints"], "inventory_fingerprints_invalid", hashes=True)
    raw_fragments = payload["fragments"]
    _require(type(raw_fragments) is list, "fragments_invalid")
    fragments = []
    for item in raw_fragments:
        _require(type(item) is dict and set(item) == {"sha256", "token_count"}, "fragments_invalid")
        _sha(item["sha256"], "fragments_invalid")
        _require(type(item["token_count"]) is int and item["token_count"] >= policy.min_fragment_tokens,
                 "fragment_token_count_invalid")
        fragments.append(FragmentFingerprint(item["sha256"], item["token_count"]))
    _require(fragments == sorted(fragments, key=lambda item: (item.token_count, item.sha256))
             and len({item.sha256 for item in fragments}) == len(fragments), "fragments_invalid")
    _require(set(whole).issubset({item.sha256 for item in fragments}), "whole_field_token_counts_missing")
    return ids, notices, whole, tuple(fragments)


def _validate_provenance(bundle: SourceBundle, *, ids: tuple[str, ...], empty: bool) -> None:
    provenance = bundle.provenance
    _require(type(provenance) is SourceProvenance and provenance.category == bundle.category,
             "provenance_invalid")
    _identifier(provenance.source_identity, "provenance_invalid")
    _require(type(provenance.expected_statement_count) is int and provenance.expected_statement_count >= 0,
             "statement_count_invalid")
    _require(provenance.expected_statement_count == len(ids), "statement_count_mismatch")
    _sha(provenance.expected_statement_set_sha256, "statement_set_hash_invalid")
    _require(provenance.expected_statement_set_sha256 == sha256_bytes(canonical_json_bytes(list(ids))),
             "statement_set_hash_mismatch")
    _require(type(provenance.unresolved_count) is int and provenance.unresolved_count >= 0
             and type(provenance.unmapped_count) is int and provenance.unmapped_count >= 0,
             "provenance_invalid")
    _require(provenance.unresolved_count == 0, "unresolved")
    _require(provenance.unmapped_count == 0, "unmapped")
    _require(type(provenance.evidence) is tuple and provenance.evidence
             and all(type(item) is EvidenceIdentity for item in provenance.evidence), "evidence_invalid")
    _require(tuple(item.identity for item in provenance.evidence)
             == tuple(sorted({item.identity for item in provenance.evidence})), "evidence_invalid")
    evidence = {}
    for item in provenance.evidence:
        _identifier(item.identity, "evidence_invalid")
        _require(item.kind in _EVIDENCE_KINDS, "evidence_invalid")
        _sha(item.document_sha256, "evidence_invalid", evidence=True)
        evidence[item.identity] = item
    _require(any(item.kind == "source_record" for item in evidence.values()), "source_evidence_missing")
    _require(type(provenance.attestations) is tuple and provenance.attestations
             and all(type(item) is Attestation for item in provenance.attestations), "attestation_invalid")
    _require(tuple(item.identity for item in provenance.attestations)
             == tuple(sorted({item.identity for item in provenance.attestations})), "attestation_invalid")
    covered_claims: set[str] = set()
    for item in provenance.attestations:
        _identifier(item.identity, "attestation_invalid")
        _identifier(item.attester_identity, "attestation_invalid")
        _sha(item.document_sha256, "attestation_invalid", evidence=True)
        _require(item.category == bundle.category, "attestation_invalid")
        _require(type(item.claims) is tuple and item.claims == tuple(sorted(set(item.claims)))
                 and bool(item.claims) and set(item.claims).issubset(_CLAIMS), "attestation_invalid")
        _require(type(item.evidence_ids) is tuple and item.evidence_ids
                 and item.evidence_ids == tuple(sorted(set(item.evidence_ids)))
                 and set(item.evidence_ids).issubset(evidence), "attestation_invalid")
        referenced = tuple(evidence[identity] for identity in item.evidence_ids)
        for claim in item.claims:
            kind = ("fragment_source" if claim in {"fragment_from_authorized_source",
                                                   "fingerprints_from_authorized_source"} else "source_record")
            _require(any(ref.kind == kind and ref.document_sha256 != item.document_sha256
                         for ref in referenced), "attestation_support_missing")
            covered_claims.add(claim)
    _require("coverage_complete" in covered_claims, "coverage_attestation_missing")
    if empty:
        rationale = provenance.empty_rationale
        _require(isinstance(rationale, str) and rationale == rationale.strip()
                 and len(rationale) >= 32 and len(re.findall(r"\w", rationale)) >= 24,
                 "empty_rationale_missing")
        _require("empty_after_review" in covered_claims, "empty_attestation_missing")
    else:
        _require(provenance.empty_rationale is None, "unexpected_empty_rationale")
    # A nonempty source needs evidence for the fragment result even when that
    # result is empty; otherwise omitting its fragment list would silently
    # weaken the selected conservative policy.
    if not empty:
        _require("fragment_from_authorized_source" in covered_claims, "fragment_evidence_missing")
        _require("fingerprints_from_authorized_source" in covered_claims, "fingerprint_evidence_missing")
    _sha(bundle.provenance_sha256, "provenance_hash_invalid")
    _require(sha256_bytes(canonical_json_bytes(asdict(provenance))) == bundle.provenance_sha256,
             "provenance_hash_mismatch")


def _validate_fragment_source(bundle: SourceBundle, *, empty: bool, policy: CatalogPolicy,
                              notices: tuple[str, ...], fragments: tuple[FragmentFingerprint, ...]) -> str | None:
    if empty:
        _require(bundle.fragment_source_bytes is None, "unexpected_fragment_source")
        return None
    raw = bundle.fragment_source_bytes
    _require(type(raw) is bytes, "fragment_source_missing")
    source_sha256 = sha256_bytes(raw)
    evidence_ids = {item.identity for item in bundle.provenance.evidence
                    if item.kind == "fragment_source" and item.document_sha256 == source_sha256}
    _require(bool(evidence_ids), "fragment_source_hash_mismatch")
    _require(all(any(claim in item.claims and evidence_ids.intersection(item.evidence_ids)
                     for item in bundle.provenance.attestations)
                 for claim in ("fragment_from_authorized_source", "fingerprints_from_authorized_source")),
             "fragment_source_attestation_missing")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid constant")))
        canonical = canonical_json_bytes(payload)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _Problem("fragment_source_invalid") from None
    _require(type(payload) is dict and canonical == raw
             and set(payload) == {"schema", "fingerprint_version", "phrases", "notices", "statements"}
             and payload["schema"] == FRAGMENT_SOURCE_SCHEMA
             and payload["fingerprint_version"] == sampling.FINGERPRINT_VERSION, "fragment_source_invalid")
    phrases = payload["phrases"]
    _require(type(phrases) is list and all(isinstance(phrase, str) for phrase in phrases)
             and phrases == sorted(phrases) and len(phrases) == len(set(phrases)), "fragment_source_invalid")
    try:
        regenerated = {fingerprint_fragment(phrase, min_tokens=policy.min_fragment_tokens) for phrase in phrases}
    except (ValueError, TypeError, UnicodeError):
        raise _Problem("fragment_source_invalid") from None
    _require(tuple(sorted(regenerated, key=lambda item: (item.token_count, item.sha256))) == fragments,
             "fragment_regeneration_mismatch")
    raw_notices, raw_statements = payload["notices"], payload["statements"]
    _require(type(raw_notices) is list and all(type(item) is dict and set(item) == {"availability", "related"}
             and isinstance(item["availability"], str) and isinstance(item["related"], str)
             for item in raw_notices), "fingerprint_source_invalid")
    pairs = [(item["availability"], item["related"]) for item in raw_notices]
    _require(pairs == sorted(pairs) and len(pairs) == len(set(pairs)), "fingerprint_source_invalid")
    _require(type(raw_statements) is list and all(isinstance(item, str) for item in raw_statements)
             and raw_statements == sorted(raw_statements) and len(raw_statements) == len(set(raw_statements)),
             "fingerprint_source_invalid")
    statement_fingerprints = {sampling.statement_fingerprint(item) for item in raw_statements}
    _require(None not in statement_fingerprints, "fingerprint_source_invalid")
    regenerated_notices = {sampling.notice_fingerprint(availability, related) for availability, related in pairs}
    regenerated_notices.update(statement_fingerprints)
    _require(regenerated_notices == set(notices), "fingerprint_regeneration_mismatch")
    return source_sha256


def _validate_regeneration(bundle: SourceBundle, expected_events: str,
                           fragment_source_sha256: str | None) -> None:
    _require(type(bundle.regenerated_inventory_bytes) is bytes, "regeneration_invalid")
    _sha(bundle.regenerated_inventory_sha256, "regeneration_invalid")
    _require(sha256_bytes(bundle.regenerated_inventory_bytes) == bundle.regenerated_inventory_sha256,
             "regeneration_hash_mismatch")
    _require(bundle.regenerated_inventory_bytes == bundle.inventory_bytes
             and bundle.regenerated_inventory_sha256 == bundle.inventory_sha256,
             "regeneration_inventory_mismatch")
    record = bundle.regeneration
    _require(type(record) is RegenerationRecord and record.category == bundle.category,
             "regeneration_invalid")
    _identifier(record.identity, "regeneration_invalid")
    _identifier(record.regenerator_identity, "regeneration_invalid")
    _require(record.identity != bundle.provenance.source_identity, "regeneration_identity_not_separate")
    _sha(record.method_sha256, "regeneration_invalid", evidence=True)
    _require(record.events_sha256 == expected_events and record.fragment_source_sha256 == fragment_source_sha256
             and record.provenance_sha256 == bundle.provenance_sha256
             and record.source_inventory_sha256 == bundle.inventory_sha256
             and record.regenerated_inventory_sha256 == bundle.regenerated_inventory_sha256,
             "regeneration_binding_mismatch")
    _sha(bundle.regeneration_sha256, "regeneration_invalid")
    _require(sha256_bytes(canonical_json_bytes(asdict(record))) == bundle.regeneration_sha256
             and bundle.regeneration_sha256 not in {bundle.inventory_sha256, bundle.provenance_sha256},
             "regeneration_record_hash_mismatch")


def _policy_record(policy: CatalogPolicy) -> dict[str, object]:
    return {**asdict(policy), "fragment_fields": list(FRAGMENT_FIELDS),
            "normalization": "sampling-wording-nfkc-casefold-alphanumeric-v1",
            "fingerprint_version": sampling.FINGERPRINT_VERSION,
            "scope": "all_presentations_before_display_selection",
            "source_fingerprint_scope": "any_presentation_per_statement_group",
            "c_n_wording_scope": "any_presentation_of_assigned_n_and_candidate_groups"}


def _implementation_value(value: object) -> object:
    if value is None or type(value) in {bool, int, str}:
        return {"type": type(value).__name__, "value": value}
    if type(value) is float:
        return {"float": value.hex()}
    if type(value) is complex:
        return {"complex": [value.real.hex(), value.imag.hex()]}
    if type(value) is bytes:
        return {"bytes": value.hex()}
    if type(value) is type:
        # A class cell binds a mutable object whose module.qualname can be shared by
        # distinct definitions; bind its contents, not its name alone (the 6 November
        # 2026 re-review swapped same-qualname classes through the name-only record).
        return {"class": value.__module__ + "." + value.__qualname__,
                "class_identity": _class_record(value)}
    if type(value) is types.FunctionType:
        return {"function": value.__module__ + "." + value.__qualname__, "identity": _function_record(value)}
    if isinstance(value, types.CodeType):
        return {"code": _code_record(value)}
    if isinstance(value, (tuple, list)):
        return {type(value).__name__: [_implementation_value(item) for item in value]}
    if isinstance(value, (set, frozenset)):
        items = [_implementation_value(item) for item in value]
        return {type(value).__name__: sorted(items, key=canonical_json_bytes)}
    if isinstance(value, dict):
        return {"dict": sorted(([_implementation_value(key), _implementation_value(item)] for key, item in value.items()),
                               key=canonical_json_bytes)}
    # A type name alone does not bind an object's mutable contents. Refuse an
    # unsupported capture rather than treating distinct values as identical.
    raise ValueError("unsupported value in runtime implementation identity")


def _code_record(code: types.CodeType) -> dict[str, object]:
    """Stable executable structure; excludes mutable interpreter specialization."""
    return {"bytecode": code.co_code.hex(), "constants": [_implementation_value(item) for item in code.co_consts],
            "names": code.co_names, "variables": code.co_varnames, "freevars": code.co_freevars,
            "cellvars": code.co_cellvars, "argcount": code.co_argcount, "posonly": code.co_posonlyargcount,
            "kwonly": code.co_kwonlyargcount, "nlocals": code.co_nlocals, "stacksize": code.co_stacksize,
            "flags": code.co_flags, "exceptiontable": code.co_exceptiontable.hex()}


def _function_record(function: types.FunctionType) -> dict[str, object]:
    cells = function.__closure__ or ()
    if len(cells) != len(function.__code__.co_freevars):
        raise ValueError("runtime closure does not match its code")
    try:
        closure = [_implementation_value(cell.cell_contents) for cell in cells]
    except ValueError as error:
        raise ValueError("unsupported or empty runtime closure") from error
    return {"code": sha256_bytes(canonical_json_bytes(_code_record(function.__code__))),
            "defaults": _implementation_value(function.__defaults__),
            "kwdefaults": _implementation_value(function.__kwdefaults__), "closure": closure}


_CLASS_RECORD_DEPTH = 0


def _class_record(value: type) -> dict[str, object]:
    """Content record of a class captured in a closure: bases by qualified name, slots and
    methods by function record, mirroring the module-level classes section. A class whose
    methods close over the class itself is cut off at a small fixed depth rather than
    recursing forever; post-definition class-attribute mutation stays outside this record."""
    global _CLASS_RECORD_DEPTH
    if _CLASS_RECORD_DEPTH >= 4:
        return {"depth_exhausted": True}
    _CLASS_RECORD_DEPTH += 1
    try:
        methods: dict[str, object] = {}
        for attribute, member in sorted(vars(value).items()):
            if isinstance(member, (staticmethod, classmethod)):
                member = member.__func__
            if isinstance(member, property):
                for label, function in (("get", member.fget), ("set", member.fset),
                                        ("delete", member.fdel)):
                    if isinstance(function, types.FunctionType):
                        methods[attribute + ":" + label] = _function_record(function)
            elif isinstance(member, types.FunctionType):
                methods[attribute] = _function_record(member)
        slots = value.__dict__.get("__slots__", ())
        return {"bases": [base.__module__ + "." + base.__qualname__ for base in value.__bases__],
                "slots": [slots] if isinstance(slots, str) else list(slots), "methods": methods}
    finally:
        _CLASS_RECORD_DEPTH -= 1


def _implementation_record() -> dict[str, object]:
    """Identify the live Python code, not an externally authenticated source release."""
    result: dict[str, object] = {"python": list(sys.version_info[:3])}
    for module in (sampling, sys.modules[__name__]):
        functions = {}
        classes = {}
        for name, value in sorted(vars(module).items()):
            if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
                functions[name] = _function_record(value)
            elif isinstance(value, type) and value.__module__ == module.__name__:
                methods = {}
                for attribute, member in sorted(vars(value).items()):
                    if isinstance(member, (staticmethod, classmethod)):
                        member = member.__func__
                    if isinstance(member, property):
                        for label, function in (("get", member.fget), ("set", member.fset), ("delete", member.fdel)):
                            if isinstance(function, types.FunctionType):
                                methods[attribute + ":" + label] = _function_record(function)
                    elif isinstance(member, types.FunctionType):
                        methods[attribute] = _function_record(member)
                slots = value.__dict__.get("__slots__", ())
                classes[name] = {"slots": [slots] if isinstance(slots, str) else list(slots), "methods": methods}
        result[module.__name__] = {"functions": functions, "classes": classes}
    result["record_validators"] = {
        name: _function_record(getattr(sampling, name))
        for name in ("iso_date", "require_identifier", "require_sha256")
    }
    return result


def _protocol_commitments(request: CatalogRequest) -> tuple[str, str]:
    implementation = sampling.private_commitment(request.alias_key, "implementation",
                                                  canonical_json_bytes(_implementation_record()))
    patterns = {}
    for name in ("_MONTH_RE", "_PART", "_WEEK", "_YEAR", "_SHORT_NUMBER", "_RELATIVE", "_MAY_VERB"):
        pattern = getattr(sampling, name)
        if not isinstance(pattern, re.Pattern):
            raise ValueError("invalid protocol expression")
        patterns[name] = {"pattern": pattern.pattern, "flags": pattern.flags}
    protocol = {
        "n_targets": sampling.N_TARGETS, "c_quotas": sampling.C_QUOTAS, "strata_precedence": sampling.STRATA,
        "expressions": patterns, "display_seed": sampling.DISPLAY_SEED, "followup_seed": sampling.FOLLOWUP_SEED,
        "display_tag": sampling.DISPLAY_TAG, "n_episode_tag": sampling.N_EPISODE_TAG,
        "n_notice_tag": sampling.N_NOTICE_TAG, "c_tag": sampling.C_TAG,
        "required_exclusions": sorted(sampling.REQUIRED_EXCLUSIONS), "source_fields": sampling.SOURCE_FIELDS,
        "fingerprint_version": sampling.FINGERPRINT_VERSION, "alias_version": sampling.ALIAS_VERSION,
        "commitment_version": sampling.COMMITMENT_VERSION, "policy": _policy_record(request.policy),
        "alias_domains": sorted(sampling._ALIAS_DOMAINS), "commitment_domains": sorted(sampling._COMMITMENT_DOMAINS),
        "reserved_prefixes": sampling._RESERVED_PREFIXES, "month_expression": sampling._MONTH,
        "implementation_commitment": implementation,
    }
    return implementation, sampling.private_commitment(request.alias_key, "protocol", canonical_json_bytes(protocol))


def _receipt(request: CatalogRequest, implementation: str, protocol: str) -> dict[str, object]:
    sources = []
    key = request.alias_key
    aliases = sampling._AliasGuard(key)
    evidence_identities: dict[str, tuple[str, str]] = {}
    attestation_identities: dict[str, tuple[str, str]] = {}
    regeneration_identities: dict[str, str] = {}
    for bundle in sorted(request.sources, key=lambda item: item.category):
        provenance = bundle.provenance
        rationale = provenance.empty_rationale
        for item in provenance.evidence:
            identity = (item.kind, item.document_sha256)
            if item.identity in evidence_identities and evidence_identities[item.identity] != identity:
                raise ValueError("conflicting evidence identity")
            evidence_identities[item.identity] = identity
        for item in provenance.attestations:
            identity = (item.attester_identity, item.document_sha256)
            if item.identity in attestation_identities and attestation_identities[item.identity] != identity:
                raise ValueError("conflicting attestation identity")
            attestation_identities[item.identity] = identity
        if (bundle.regeneration.identity in regeneration_identities
                and regeneration_identities[bundle.regeneration.identity] != bundle.regeneration_sha256):
            raise ValueError("conflicting regeneration identity")
        regeneration_identities[bundle.regeneration.identity] = bundle.regeneration_sha256
        sources.append({
            "category": bundle.category,
            "inventory_commitment": sampling.digest_commitment(key, "inventory", bundle.inventory_sha256),
            "regenerated_inventory_commitment": sampling.digest_commitment(
                key, "regenerated_inventory", bundle.regenerated_inventory_sha256),
            "provenance_commitment": sampling.digest_commitment(key, "provenance", bundle.provenance_sha256),
            "regeneration_commitment": sampling.digest_commitment(key, "regeneration", bundle.regeneration_sha256),
            "fragment_source_commitment": (None if bundle.fragment_source_bytes is None else
                sampling.digest_commitment(key, "fingerprint_source", sha256_bytes(bundle.fragment_source_bytes))),
            "source_identity": aliases.alias("source", provenance.source_identity),
            "expected_statement_count": provenance.expected_statement_count,
            "expected_statement_set_alias": aliases.alias("idset", provenance.expected_statement_set_sha256),
            "evidence": [{"identity": aliases.alias("evidence", item.identity),
                          "kind": item.kind,
                          "document_commitment": sampling.digest_commitment(key, "evidence_document", item.document_sha256)}
                         for item in provenance.evidence],
            "attestations": [{"identity": aliases.alias("attestation", item.identity),
                              "attester_identity": aliases.alias("actor", item.attester_identity),
                              "document_commitment": sampling.digest_commitment(key, "attestation_document", item.document_sha256),
                              "category": item.category,
                              "claims": list(item.claims),
                              "evidence_ids": [aliases.alias("evidence", identity) for identity in item.evidence_ids]}
                             for item in provenance.attestations],
            "empty_rationale_commitment": (None if rationale is None else
                                          sampling.private_commitment(key, "empty_rationale", rationale.encode("utf-8"))),
            "unresolved_count": provenance.unresolved_count,
            "unmapped_count": provenance.unmapped_count,
            "regeneration_identity": aliases.alias("regeneration", bundle.regeneration.identity),
            "regenerator_identity": aliases.alias("actor", bundle.regeneration.regenerator_identity),
            "regeneration_method_commitment": sampling.digest_commitment(key, "regeneration_method", bundle.regeneration.method_sha256),
        })
    return {"schema": RECEIPT_SCHEMA, "status": "ready", "scope": "candidate_not_authorization",
            "events_commitment": sampling.digest_commitment(key, "events", request.expected_events_sha256),
            "fingerprint_version": sampling.FINGERPRINT_VERSION,
            "alias_version": sampling.ALIAS_VERSION, "alias_key_commitment": sampling.alias_key_commitment(key),
            "commitment_version": sampling.COMMITMENT_VERSION,
            "implementation_commitment": implementation, "protocol_commitment": protocol,
            "policy": _policy_record(request.policy),
            "sources": sources}


def _assess_catalog(request: CatalogRequest) -> tuple[CatalogDecision, _ReadyState | None]:
    if type(request) is not CatalogRequest:
        return CatalogDecision("not_ready", ("request_invalid",), None, None), None
    if request.declared_status != "ready":
        issue = "declared_not_ready" if request.declared_status == "not_ready" else "status_invalid"
        return CatalogDecision("not_ready", (issue,), None, None), None
    try:
        sampling.alias_key_commitment(request.alias_key)
    except (ValueError, TypeError):
        return CatalogDecision("not_ready", ("alias_key_invalid",), None, None), None
    policy = request.policy
    if (type(policy) is not CatalogPolicy or policy.fragment_mode != FRAGMENT_MODE
            or type(policy.min_fragment_tokens) is not int or policy.min_fragment_tokens < MIN_FRAGMENT_TOKENS
            or policy.blank_mode != BLANK_MODE or not isinstance(policy.blank_anchor_category, str)
            or policy.blank_anchor_category not in sampling.REQUIRED_EXCLUSIONS):
        return CatalogDecision("not_ready", ("policy_invalid",), None, None), None
    if (type(request.sources) is not tuple or any(type(item) is not SourceBundle for item in request.sources)
            or any(not isinstance(item.category, str) for item in request.sources)
            or len(request.sources) != len(sampling.REQUIRED_EXCLUSIONS)
            or {item.category for item in request.sources} != sampling.REQUIRED_EXCLUSIONS):
        return CatalogDecision("not_ready", ("categories_invalid",), None, None), None
    try:
        events = sampling.project_open_events(request.compressed_events, expected_sha256=request.expected_events_sha256)
    except sampling.PrivateIdentifierError:
        return CatalogDecision("not_ready", ("event_identifier_invalid",), None, None), None
    except (ValueError, TypeError, UnicodeError, csv.Error, RecursionError):
        return CatalogDecision("not_ready", ("events_invalid_or_hash_mismatch",), None, None), None
    if not events:
        return CatalogDecision("not_ready", ("events_empty",), None, None), None
    if len({event.event_id for event in events}) != len(events):
        return CatalogDecision("not_ready", ("events_duplicate_ids",), None, None), None
    try:
        sampling.private_alias_index(events, alias_key=request.alias_key)
    except (ValueError, TypeError, UnicodeError):
        return CatalogDecision("not_ready", ("alias_mapping_invalid",), None, None), None
    event_statement_ids = {event.statement_group_id for event in events}
    issues = []
    validated = []
    for bundle in sorted(request.sources, key=lambda item: item.category):
        try:
            ids, notices, whole, fragments = _parse_inventory(bundle, request.expected_events_sha256, policy)
            empty = not (ids or notices or whole or fragments)
            _validate_provenance(bundle, ids=ids, empty=empty)
            fragment_source_sha256 = _validate_fragment_source(bundle, empty=empty, policy=policy,
                                                               notices=notices, fragments=fragments)
            _validate_regeneration(bundle, request.expected_events_sha256, fragment_source_sha256)
            id_set, notice_set = set(ids), set(notices)
            _require(id_set.issubset(event_statement_ids), "unmapped_statement_ids")
            _require(all(event.exclusion_fingerprints.issubset(notice_set) for event in events
                         if event.statement_group_id in id_set), "source_id_fingerprints_missing")
            source = sampling.ExclusionSource(bundle.category, frozenset(ids), frozenset(notices),
                                              frozenset(whole), bundle.provenance_sha256, True)
            validated.append(_ValidatedSource(source, fragments))
        except _Problem as error:
            issues.append(f"{bundle.category}:{error.code}")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            issues.append(f"{bundle.category}:invalid_evidence")
    if issues:
        return CatalogDecision("not_ready", tuple(issues), None, None), None
    try:
        implementation, protocol = _protocol_commitments(request)
    except (ValueError, TypeError, UnicodeError, RecursionError, AttributeError, RuntimeError):
        return CatalogDecision("not_ready", ("protocol_invalid",), None, None), None
    try:
        receipt_bytes = canonical_json_bytes(_receipt(request, implementation, protocol))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return CatalogDecision("not_ready", ("alias_mapping_invalid",), None, None), None
    policy_commitment = sampling.private_commitment(request.alias_key, "policy", canonical_json_bytes(_policy_record(policy)))
    state = _ReadyState(events, tuple(validated), receipt_bytes)
    return CatalogDecision("ready", (), sampling.private_commitment(request.alias_key, "gate", receipt_bytes),
                           policy_commitment, protocol, receipt_bytes, _READY_TOKEN), state


def assess_catalog(request: CatalogRequest) -> CatalogDecision:
    """Fail closed; validate supplied records without drawing an N or C sample."""
    decision, _ = _assess_catalog(request)
    return decision


def _ready_state(request: CatalogRequest, decision: CatalogDecision) -> tuple[CatalogDecision, _ReadyState]:
    if (type(decision) is not CatalogDecision or decision.status != "ready" or decision._proof is not _READY_TOKEN
            or type(decision._receipt_bytes) is not bytes
            or sampling.private_commitment(request.alias_key, "gate", decision._receipt_bytes) != decision.gate_commitment):
        raise ValueError("candidate catalog is not ready")
    fresh, state = _assess_catalog(request)
    if (fresh.status != "ready" or fresh.gate_commitment != decision.gate_commitment
            or fresh.policy_commitment != decision.policy_commitment
            or fresh.protocol_commitment != decision.protocol_commitment or fresh._receipt_bytes != decision._receipt_bytes
            or state is None):
        raise ValueError("candidate catalog no longer matches its evidence")
    return fresh, state


def gate_receipt(request: CatalogRequest, decision: CatalogDecision) -> dict[str, object]:
    """Return the hash-bound metadata receipt, with no inventory or phrase text."""
    fresh, _ = _ready_state(request, decision)
    return json.loads(fresh._receipt_bytes)


def _effective_sources(state: _ReadyState, policy: CatalogPolicy, alias_key: bytes) -> tuple[
    tuple[sampling.ExclusionSource, ...], bytes
]:
    index: dict[int, dict[str, set[str]]] = {}
    source_fingerprints: dict[str, set[str]] = {}
    for item in state.sources:
        for fragment in item.fragments:
            index.setdefault(fragment.token_count, {}).setdefault(fragment.sha256, set()).add(item.source.name)
        for fingerprint in item.source.notice_fingerprints:
            source_fingerprints.setdefault(fingerprint, set()).add(item.source.name)
    matches: dict[str, set[str]] = {}
    for event in state.events:
        group = event.statement_group_id
        for name in source_fingerprints.get(event.wording_sha256, ()):
            matches.setdefault(group, set()).add("source_notice_fingerprint:" + name)
        statement_fingerprint = event.statement_wording_sha256
        if statement_fingerprint is not None:
            for name in source_fingerprints.get(statement_fingerprint, ()):
                matches.setdefault(group, set()).add("source_statement_fingerprint:" + name)
        fields = {name: sampling._wording(getattr(event, name)).split() for name in FRAGMENT_FIELDS}
        if not fields["availability_text"] and not fields["related_text"]:
            matches.setdefault(group, set()).add("policy_blank_pair")
        for tokens in fields.values():
            for length, digests in index.items():
                for start in range(len(tokens) - length + 1):
                    digest = sampling._field_fingerprint_normalized(" ".join(tokens[start:start + length]))
                    for name in digests.get(digest, ()):
                        matches.setdefault(group, set()).add("policy_fragment:" + name)
    derived = []
    for item in state.sources:
        name = item.source.name
        policy_ids = {group for group, reasons in matches.items()
                      if "policy_fragment:" + name in reasons
                      or "source_notice_fingerprint:" + name in reasons
                      or "source_statement_fingerprint:" + name in reasons
                      or (name == policy.blank_anchor_category and "policy_blank_pair" in reasons)}
        source = item.source
        derived.append(sampling.ExclusionSource(name, source.statement_ids | frozenset(policy_ids),
                                                source.notice_fingerprints, source.whole_field_fingerprints,
                                                source.provenance_sha256, True))
    overlay = sorted(({"statement_group_id": sampling.private_alias(alias_key, "item", group),
                       "reasons": sorted(reasons)} for group, reasons in matches.items()),
                     key=lambda item: item["statement_group_id"])
    return tuple(derived), canonical_json_bytes(overlay)


def _wrap_draw(request: CatalogRequest, decision: CatalogDecision, draw: sampling.SampleDraw,
               overlay: bytes, n_wording_overlay: bytes,
               n_commitment: FrozenNCommitment | None = None) -> GatedDraw:
    key = request.alias_key
    payload = {"schema": MANIFEST_SCHEMA, "gate_commitment": decision.gate_commitment,
               "fingerprint_version": sampling.FINGERPRINT_VERSION, "alias_version": sampling.ALIAS_VERSION,
               "commitment_version": sampling.COMMITMENT_VERSION,
               "alias_key_commitment": sampling.alias_key_commitment(key),
               "policy_commitment": decision.policy_commitment, "protocol_commitment": decision.protocol_commitment,
               "policy": _policy_record(request.policy),
               "policy_overlay_commitment": sampling.private_commitment(key, "policy_overlay", overlay),
               "policy_exclusions": json.loads(overlay),
               "n_wording_overlay_commitment": sampling.private_commitment(key, "n_wording_overlay", n_wording_overlay),
               "n_wording_exclusions": json.loads(n_wording_overlay),
               "frozen_n_manifest_commitment": (None if n_commitment is None else
                                                n_commitment.expected_n_manifest_commitment),
               "n_commitment_record": (None if n_commitment is None else n_commitment.expected_record_commitment),
               "sample": sampling.sample_manifest(draw, events_sha256=request.expected_events_sha256,
                                                   alias_key=key, _gate_token=sampling._DRAW_CAPABILITY)}
    payload["manifest_commitment"] = sampling.private_commitment(key, "gated_manifest", canonical_json_bytes(payload))
    manifest_bytes = canonical_json_bytes(payload)
    return GatedDraw(draw.cohort, draw.package, decision.gate_commitment, decision.policy_commitment,
                     decision.protocol_commitment, sampling.private_commitment(key, "policy_overlay", overlay),
                     sampling.private_commitment(key, "n_wording_overlay", n_wording_overlay),
                     sampling.digest_commitment(key, "sample", draw.sample_sha256), manifest_bytes,
                     _DrawProof(sampling.private_commitment(key, "draw_manifest", manifest_bytes), _DRAW_TOKEN))


def _checked_draw(request: CatalogRequest, decision: CatalogDecision, draw: GatedDraw) -> dict[str, object]:
    if (type(draw) is not GatedDraw or type(draw._proof) is not _DrawProof or draw._proof.marker is not _DRAW_TOKEN
            or type(draw._manifest_bytes) is not bytes
            or sampling.private_commitment(request.alias_key, "draw_manifest", draw._manifest_bytes)
            != draw._proof.manifest_commitment
            or draw.gate_commitment != decision.gate_commitment or draw.policy_commitment != decision.policy_commitment
            or draw.protocol_commitment != decision.protocol_commitment):
        raise ValueError("draw does not match the gated frame")
    try:
        payload = json.loads(draw._manifest_bytes, object_pairs_hook=_unique_pairs)
        sample = payload["sample"]
        manifest_commitment = payload["manifest_commitment"]
        sample_manifest_commitment = sample["manifest_commitment"]
        valid = (
            type(payload) is dict and set(payload) == {
                "schema", "gate_commitment", "fingerprint_version", "alias_version", "commitment_version",
                "alias_key_commitment", "policy_commitment", "protocol_commitment", "policy",
                "policy_overlay_commitment", "policy_exclusions", "n_wording_overlay_commitment",
                "n_wording_exclusions", "frozen_n_manifest_commitment", "n_commitment_record", "sample",
                "manifest_commitment",
            }
            and canonical_json_bytes(payload) == draw._manifest_bytes
            and sampling.private_commitment(request.alias_key, "gated_manifest", canonical_json_bytes(
                {k: v for k, v in payload.items() if k != "manifest_commitment"})) == manifest_commitment
            and sampling.private_commitment(request.alias_key, "sample_manifest", canonical_json_bytes(
                {k: v for k, v in sample.items() if k != "manifest_commitment"})) == sample_manifest_commitment
            and payload["schema"] == MANIFEST_SCHEMA and payload["gate_commitment"] == draw.gate_commitment
            and payload["fingerprint_version"] == sampling.FINGERPRINT_VERSION
            and payload["alias_version"] == sampling.ALIAS_VERSION
            and payload["commitment_version"] == sampling.COMMITMENT_VERSION
            and payload["alias_key_commitment"] == sampling.alias_key_commitment(request.alias_key)
            and payload["policy_commitment"] == draw.policy_commitment
            and payload["protocol_commitment"] == draw.protocol_commitment
            and payload["policy"] == _policy_record(request.policy)
            and payload["policy_overlay_commitment"] == draw.policy_overlay_commitment
            and sampling.private_commitment(request.alias_key, "policy_overlay", canonical_json_bytes(
                payload["policy_exclusions"])) == draw.policy_overlay_commitment
            and payload["n_wording_overlay_commitment"] == draw.n_wording_overlay_commitment
            and sampling.private_commitment(request.alias_key, "n_wording_overlay", canonical_json_bytes(
                payload["n_wording_exclusions"])) == draw.n_wording_overlay_commitment
            and sample["cohort"] == draw.cohort and sample["package"] == draw.package
            and sample["sample_commitment"] == draw.sample_commitment
            and sample["events_commitment"] == sampling.digest_commitment(request.alias_key, "events",
                                                                            request.expected_events_sha256)
            and sample["fingerprint_version"] == sampling.FINGERPRINT_VERSION
            and sample["alias_version"] == sampling.ALIAS_VERSION
            and sample["commitment_version"] == sampling.COMMITMENT_VERSION
            and sample["alias_key_commitment"] == sampling.alias_key_commitment(request.alias_key)
        )
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ValueError("draw does not match the gated frame") from None
    if not valid:
        raise ValueError("draw does not match the gated frame")
    return payload


def _check_n_commitment(commitment: FrozenNCommitment, independent_record_commitment: str,
                        request: CatalogRequest, decision: CatalogDecision, package: str,
                        n_manifest_commitment: str) -> None:
    """Check a supplied lock; neither its authenticity nor timing can be proven here."""
    try:
        _require(type(commitment) is FrozenNCommitment and type(commitment.record_bytes) is bytes,
                 "n_commitment_invalid")
        sampling.require_commitment(commitment.expected_record_commitment, "n_lock_record")
        sampling.require_commitment(commitment.expected_n_manifest_commitment, "draw_manifest")
        sampling.require_commitment(independent_record_commitment, "n_lock_record")
        _require(independent_record_commitment == commitment.expected_record_commitment, "n_commitment_record_mismatch")
        _require(sampling.private_commitment(request.alias_key, "n_lock_record", commitment.record_bytes)
                 == commitment.expected_record_commitment,
                 "n_commitment_record_mismatch")
        record = json.loads(commitment.record_bytes.decode("utf-8"), object_pairs_hook=_unique_pairs)
        _require(type(record) is dict and canonical_json_bytes(record) == commitment.record_bytes
                 and set(record) == {"schema", "gate_commitment", "protocol_commitment", "fingerprint_version",
                                     "commitment_version", "alias_key_commitment", "package", "n_manifest_commitment",
                                     "before_reference_and_evaluation", "evidence_identity", "evidence_commitment"},
                 "n_commitment_invalid")
        _identifier(commitment.evidence_identity, "n_commitment_invalid")
        _require(record["evidence_identity"] == sampling.private_alias(request.alias_key, "evidence",
                                                                       commitment.evidence_identity),
                 "n_commitment_invalid")
        _sha(commitment.evidence_sha256, "n_commitment_invalid", evidence=True)
        _require(record["evidence_commitment"] == sampling.digest_commitment(request.alias_key, "evidence_document",
                                                                              commitment.evidence_sha256),
                 "n_commitment_invalid")
        _require(record["schema"] == N_COMMITMENT_SCHEMA and record["gate_commitment"] == decision.gate_commitment
                 and record["protocol_commitment"] == decision.protocol_commitment
                 and record["fingerprint_version"] == sampling.FINGERPRINT_VERSION
                 and record["commitment_version"] == sampling.COMMITMENT_VERSION
                 and record["alias_key_commitment"] == sampling.alias_key_commitment(request.alias_key)
                 and record["package"] == package and record["before_reference_and_evaluation"] is True
                 and record["n_manifest_commitment"] == commitment.expected_n_manifest_commitment == n_manifest_commitment,
                 "n_commitment_mismatch")
    except (_Problem, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("the independently supplied N commitment does not match") from None


def _restore_n_from_manifest(request: CatalogRequest, state: _ReadyState,
                             sources: tuple[sampling.ExclusionSource, ...], natural: GatedDraw,
                             payload: dict[str, object]) -> sampling.SampleDraw:
    """Restore the retained N identities; verify the frame without drawing N again."""
    sources, exclusions_sha256 = sampling._catalog(sources)
    frame = sampling._frame(state.events, sources)
    frame_sha256 = sampling._frame_hash(frame)
    sample = payload["sample"]
    try:
        rows = sample["frame"]
        valid = (type(rows) is list and len(rows) == len(frame)
                 and sample["cohort"] == "N" and sample["package"] == natural.package
                 and sample["target"] == sampling.N_TARGETS[natural.package]
                 and sample["frame_commitment"] == sampling.digest_commitment(request.alias_key, "frame", frame_sha256)
                 and sample["exclusions_commitment"] == sampling.digest_commitment(request.alias_key, "exclusions", exclusions_sha256)
                 and sample["parent_sample_commitment"] is None
                 and sample["requested_quotas"] == [] and sample["achieved_quotas"] == [])
        if not valid:
            raise ValueError
        selected = _retained_selected(request, state.events, frame, rows, cohort="N")
        sample_sha256 = sampling._sample_hash(selected)
        if ([item.selection_rank for item in selected] != list(range(1, len(selected) + 1))
                or sample["shortfall"] != sample["target"] - len(selected)
                or sample["sample_commitment"] != sampling.digest_commitment(request.alias_key, "sample", sample_sha256)
                or sample["sample_commitment"] != natural.sample_commitment):
            raise ValueError
        retained = sampling.SampleDraw("N", natural.package, sample["target"], frame, selected,
                                       sample["shortfall"], exclusions_sha256, frame_sha256, sample_sha256)
        if canonical_json_bytes(sampling.sample_manifest(retained, events_sha256=request.expected_events_sha256,
                                                        alias_key=request.alias_key,
                                                        _gate_token=sampling._DRAW_CAPABILITY)) != canonical_json_bytes(sample):
            raise ValueError
    except (KeyError, TypeError, ValueError, IndexError):
        raise ValueError("the retained N draw does not match the gated frame") from None
    return sampling._seal_n_draw(retained, state.events)


def _retained_selected(request: CatalogRequest, events: tuple[sampling.SourceEvent, ...],
                       frame: tuple[sampling.FrameEntry, ...], rows: list, *,
                       cohort: str) -> tuple[sampling.SelectedNotice, ...]:
    index = sampling.private_alias_index(events, alias_key=request.alias_key)
    frame_by_id = {entry.event.statement_group_id: entry for entry in frame}
    aliases = [row["item_id"] for row in rows]
    if aliases != sorted(aliases) or len(aliases) != len(set(aliases)) or len(aliases) != len(frame):
        raise ValueError
    selected = []
    for row in rows:
        raw_id = index.resolve("item", row["item_id"])
        entry = frame_by_id[raw_id]
        event = entry.event
        statement_alias = (None if event.statement_wording_sha256 is None else
                           sampling.private_alias(request.alias_key, "statement", event.statement_wording_sha256))
        if (type(row) is not dict
                or row["event_id"] != sampling.private_alias(request.alias_key, "event", event.event_id)
                or row["episode_id"] != sampling.private_alias(request.alias_key, "episode", event.episode_id)
                or row["visible_input_alias"] != sampling.private_alias(request.alias_key, "visible", event.model_input_sha256)
                or row["wording_alias"] != sampling.private_alias(request.alias_key, "notice", event.wording_sha256)
                or row["statement_wording_alias"] != statement_alias
                or row["exclusions"] != list(entry.exclusions)):
            raise ValueError
        rank, key_alias = row["selected_rank"], row["selected_draw_key_alias"]
        if rank is not None:
            stratum = None if cohort == "N" else row["stratum"]
            if cohort == "C" and stratum not in sampling.STRATA:
                raise ValueError
            tag = sampling.N_NOTICE_TAG + event.episode_id if cohort == "N" else sampling.C_TAG + stratum
            key = sampling._draw_key(sampling.FOLLOWUP_SEED, tag, event.statement_group_id)
            if (type(rank) is not int or rank < 1 or entry.exclusions
                    or key_alias != sampling.private_alias(request.alias_key, "draw", key)):
                raise ValueError
            selected.append(sampling.SelectedNotice(event, rank, key, stratum))
        elif key_alias is not None:
            raise ValueError
    return tuple(sorted(selected, key=lambda item: item.selection_rank))


def _restore_c_from_manifest(request: CatalogRequest, state: _ReadyState,
                             sources: tuple[sampling.ExclusionSource, ...], natural: sampling.SampleDraw,
                             draw: GatedDraw, payload: dict[str, object]) -> None:
    sources, exclusions_sha256 = sampling._catalog(sources)
    ids = frozenset(item.event.statement_group_id for item in natural.selected)
    notice_groups, statement_groups = sampling._n_wording_groups(state.events, ids)
    frame = sampling._frame(state.events, sources, ids, notice_groups | statement_groups)
    frame_sha256 = sampling._frame_hash(frame)
    sample = payload["sample"]
    try:
        rows = sample["frame"]
        valid = (type(rows) is list and len(rows) == len(frame)
                 and sample["cohort"] == "C" and sample["package"] == draw.package
                 and sample["target"] == sum(sampling.C_QUOTAS[draw.package])
                 and sample["frame_commitment"] == sampling.digest_commitment(request.alias_key, "frame", frame_sha256)
                 and sample["exclusions_commitment"] == sampling.digest_commitment(request.alias_key, "exclusions", exclusions_sha256)
                 and sample["parent_sample_commitment"] == sampling.digest_commitment(request.alias_key, "sample", natural.sample_sha256))
        if not valid:
            raise ValueError
        selected = _retained_selected(request, state.events, frame, rows, cohort="C")
        sample_sha256 = sampling._sample_hash(selected)
        if (sample["shortfall"] != sample["target"] - len(selected)
                or sample["sample_commitment"] != sampling.digest_commitment(request.alias_key, "sample", sample_sha256)
                or sample["sample_commitment"] != draw.sample_commitment):
            raise ValueError
        retained = sampling.SampleDraw("C", draw.package, sample["target"], frame, selected,
                                       sample["shortfall"], exclusions_sha256, frame_sha256,
                                       sample_sha256, tuple(map(tuple, sample["requested_quotas"])),
                                       tuple(map(tuple, sample["achieved_quotas"])), natural.sample_sha256)
        if canonical_json_bytes(sampling.sample_manifest(retained, events_sha256=request.expected_events_sha256,
                                                        alias_key=request.alias_key,
                                                        _gate_token=sampling._DRAW_CAPABILITY)) != canonical_json_bytes(sample):
            raise ValueError
    except (KeyError, TypeError, ValueError, IndexError):
        raise ValueError("the retained C draw does not match the gated frame") from None


def _n_wording_overlay(events: tuple[sampling.SourceEvent, ...], natural: sampling.SampleDraw,
                       alias_key: bytes) -> bytes:
    selected_ids = frozenset(item.event.statement_group_id for item in natural.selected)
    notice_groups, statement_groups = sampling._n_wording_groups(events, selected_ids)
    rows = []
    for group in sorted(notice_groups | statement_groups):
        reasons = []
        if group in notice_groups:
            reasons.append("assigned_n_notice_fingerprint")
        if group in statement_groups:
            reasons.append("assigned_n_statement_fingerprint")
        rows.append({"statement_group_id": sampling.private_alias(alias_key, "item", group), "reasons": reasons})
    return canonical_json_bytes(sorted(rows, key=lambda item: item["statement_group_id"]))


def gated_select_n(request: CatalogRequest, decision: CatalogDecision, *, package: str) -> GatedDraw:
    fresh, state = _ready_state(request, decision)
    sources, overlay = _effective_sources(state, request.policy, request.alias_key)
    return _wrap_draw(request, fresh, sampling.select_n(state.events, sources, package=package,
                                                       _gate_token=sampling._DRAW_CAPABILITY), overlay,
                      canonical_json_bytes([]))


def gated_select_c(request: CatalogRequest, decision: CatalogDecision, *, package: str,
                   natural: GatedDraw, n_commitment: FrozenNCommitment, n_anchor_commitment: str) -> GatedDraw:
    fresh, state = _ready_state(request, decision)
    if (type(natural) is not GatedDraw or natural.cohort != "N"
            or natural.package != package or natural.gate_commitment != fresh.gate_commitment
            or natural.policy_commitment != fresh.policy_commitment
            or natural.protocol_commitment != fresh.protocol_commitment):
        raise ValueError("C requires the gated N draw from the same catalog and package")
    payload = _checked_draw(request, fresh, natural)
    _check_n_commitment(n_commitment, n_anchor_commitment, request, fresh, package,
                        sampling.private_commitment(request.alias_key, "draw_manifest", natural._manifest_bytes))
    sources, overlay = _effective_sources(state, request.policy, request.alias_key)
    if (natural.policy_overlay_commitment != sampling.private_commitment(request.alias_key, "policy_overlay", overlay)
            or payload["policy_exclusions"] != json.loads(overlay) or payload["n_wording_exclusions"] != []):
        raise ValueError("the gated N draw does not match the policy")
    original = _restore_n_from_manifest(request, state, sources, natural, payload)
    draw = sampling.select_c(state.events, sources, package=package, natural_draw=original,
                             _gate_token=sampling._DRAW_CAPABILITY)
    return _wrap_draw(request, fresh, draw, overlay, _n_wording_overlay(state.events, original, request.alias_key),
                      n_commitment)


def gated_sample_manifest(request: CatalogRequest, decision: CatalogDecision, draw: GatedDraw, *,
                          n_commitment: FrozenNCommitment | None = None,
                          natural: GatedDraw | None = None, n_anchor_commitment: str | None = None) -> dict[str, object]:
    """Return a private ID/hash manifest; no notice or fragment text is exported."""
    fresh, state = _ready_state(request, decision)
    if (type(draw) is not GatedDraw or draw.cohort not in {"N", "C"}
            or draw.gate_commitment != fresh.gate_commitment or draw.policy_commitment != fresh.policy_commitment
            or draw.protocol_commitment != fresh.protocol_commitment):
        raise ValueError("draw does not belong to this candidate catalog")
    payload = _checked_draw(request, fresh, draw)
    sources, overlay = _effective_sources(state, request.policy, request.alias_key)
    if (draw.policy_overlay_commitment != sampling.private_commitment(request.alias_key, "policy_overlay", overlay)
            or payload["policy_exclusions"] != json.loads(overlay)):
        raise ValueError("draw does not match the gated frame")
    if draw.cohort == "C":
        if (type(natural) is not GatedDraw or natural.cohort != "N" or natural.package != draw.package
                or natural.gate_commitment != fresh.gate_commitment):
            raise ValueError("C requires the retained N draw and commitment")
        natural_payload = _checked_draw(request, fresh, natural)
        _check_n_commitment(n_commitment, n_anchor_commitment, request, fresh, draw.package,
                            sampling.private_commitment(request.alias_key, "draw_manifest", natural._manifest_bytes))
        if (payload.get("n_commitment_record") != n_commitment.expected_record_commitment
                or payload.get("frozen_n_manifest_commitment") != n_commitment.expected_n_manifest_commitment):
            raise ValueError("the independently supplied N commitment does not match")
        original = _restore_n_from_manifest(request, state, sources, natural, natural_payload)
        n_overlay = _n_wording_overlay(state.events, original, request.alias_key)
        if (draw.n_wording_overlay_commitment != sampling.private_commitment(request.alias_key, "n_wording_overlay", n_overlay)
                or payload["n_wording_exclusions"] != json.loads(n_overlay)):
            raise ValueError("draw does not match the gated frame")
        _restore_c_from_manifest(request, state, sources, original, draw, payload)
    elif (payload.get("frozen_n_manifest_commitment") is not None
          or payload.get("n_commitment_record") is not None or payload["n_wording_exclusions"] != []):
        raise ValueError("draw does not match the gated frame")
    else:
        _restore_n_from_manifest(request, state, sources, draw, payload)
    return payload
