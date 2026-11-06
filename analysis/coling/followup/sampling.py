"""First-sight projection and deterministic N/C sampling.

The only tabular input accepted here is a caller-supplied, hash-checked open
events byte stream. This module opens no paths and does not read a statements
table, model output, rule reading, or outcome. A real draw remains inactive
until every required exclusion inventory is complete and the sampling protocol
is recorded before labels or evaluation outputs are inspected. C retains the
original in-process N selection and refuses a changed projected event set; the
in-process proof is not external authentication or a cross-process resume path.
Public direct draws are disabled; the candidate gate validates typed source
evidence before invoking the private draw capability. Python private APIs are
not an access-control sandbox. Legacy/untyped fingerprints must not be used:
regenerate inventories from separately authorized, hash-verified sources.
Manifests require a caller-supplied secret of at least 32 bytes. Length checks do
not establish entropy: generate it securely outside this module, retain the key
and raw crosswalk privately, and review any disclosure separately. Keyed
commitments and aliases are not anonymous if the key is weak or compromised.
IDs may contain bounded Unicode and internal spaces, but must be trimmed,
at most 256 UTF-8 bytes, free of control/format characters, and outside the
reserved ``a1_``/``c1_`` output namespaces. These constraints do not establish
anonymity or eliminate all disclosure risks.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import hmac
import io
import json
import re
import unicodedata
import zlib
from dataclasses import asdict, dataclass, field, replace
from types import MappingProxyType
from typing import Iterable, Mapping

from .records import iso_date, require_identifier, require_sha256


SOURCE_FIELDS = (
    "event_id", "statement_group_id", "episode_id", "listing", "status_at_statement",
    "availability_class", "event_date", "revision_index", "generic_name", "company_name",
    "presentation", "therapeutic_category", "initial_posting_date", "type_of_update",
    "availability_text", "related_text", "statement_text", "reason_for_shortage",
)
REQUIRED_EXCLUSIONS = frozenset({
    "pilot_check_literal", "guide_prompt_examples", "task_e", "prior_development_reference",
    "inspected_item_outputs", "new_prompt_development",
})
N_TARGETS = {"full": 100, "reduced": 60}
STRATA = ("part_of_month", "week_expression", "missing_year", "numbered_relative")
C_QUOTAS = {
    "full": (20, 20, 5, 5),
    "reduced": (12, 12, 3, 3),
}
DISPLAY_SEED = 20261001
FOLLOWUP_SEED = 20261011
DISPLAY_TAG = "display/"
N_EPISODE_TAG = "january-n-episode-v1"
N_NOTICE_TAG = "january-n-notice-v1/"
C_TAG = "january-c-v1/"
FINGERPRINT_VERSION = "followup-fingerprint-v2"
ALIAS_VERSION = "followup-private-hmac-v1"
COMMITMENT_VERSION = "followup-private-commit-v1"
_DRAW_CAPABILITY = object()
_RESERVED_PREFIXES = ("a1_", "c1_")
_ALIAS_DOMAINS = frozenset({"item", "event", "episode", "draw", "visible", "notice", "statement",
                            "source", "evidence", "attestation", "actor", "regeneration", "idset"})
_COMMITMENT_DOMAINS = frozenset({"key", "events", "inventory", "regenerated_inventory", "provenance",
    "regeneration", "fingerprint_source", "evidence_document", "attestation_document", "empty_rationale",
    "regeneration_method", "gate", "policy", "protocol", "implementation", "policy_overlay", "n_wording_overlay",
    "sample", "frame", "exclusions", "sample_manifest", "gated_manifest", "draw_manifest", "n_lock_record"})


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _draw_key(seed: int, tag: str, item_id: str) -> str:
    return _digest(f"{seed}\x1f{tag}\x1f{item_id}".encode("utf-8"))


def _wording(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join("".join(character if character.isalnum() else " " for character in normalized).split())


def _typed_fingerprint(kind: str, values: list[str]) -> str:
    return _digest(_canonical({"version": FINGERPRINT_VERSION, "kind": kind, "values": values}))


def _field_fingerprint_normalized(value: str) -> str:
    return _typed_fingerprint("field", [value])


def field_fingerprint(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("visible text must be a string")
    return _field_fingerprint_normalized(_wording(value))


def notice_fingerprint(availability: str, related: str) -> str:
    """Punctuation-insensitive paired fields, independent of company and date."""
    if not isinstance(availability, str) or not isinstance(related, str):
        raise TypeError("visible text must be strings")
    return _typed_fingerprint("notice", [_wording(availability), _wording(related)])


def statement_fingerprint(value: str) -> str | None:
    if not isinstance(value, str):
        raise TypeError("visible text must be a string")
    text = _wording(value)
    return _typed_fingerprint("statement", [text]) if text else None


def _require_alias_key(key: bytes) -> None:
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("a private alias key must be bytes of at least 32 bytes")


def private_commitment(key: bytes, kind: str, value: bytes) -> str:
    """Keyed, domain-separated commitment; not a claim of anonymity."""
    _require_alias_key(key)
    if not isinstance(kind, str) or kind not in _COMMITMENT_DOMAINS or type(value) is not bytes:
        raise ValueError("invalid private commitment input")
    message = (COMMITMENT_VERSION + "\x00" + kind + "\x00").encode() + value
    return f"c1_{kind}_" + hmac.new(key, message, hashlib.sha256).hexdigest()


def digest_commitment(key: bytes, kind: str, digest: str) -> str:
    require_sha256(digest, "private digest")
    return private_commitment(key, kind, bytes.fromhex(digest))


def alias_key_commitment(key: bytes) -> str:
    """Public commitment; high-entropy key generation remains external."""
    return private_commitment(key, "key", b"")


def require_commitment(value: str, kind: str) -> None:
    if (not isinstance(value, str) or kind not in _COMMITMENT_DOMAINS
            or re.fullmatch(r"c1_" + re.escape(kind) + r"_[0-9a-f]{64}", value) is None):
        raise ValueError("invalid private commitment")


class PrivateIdentifierError(ValueError):
    """A bounded identity cannot safely enter the private alias namespace."""


def require_private_id(value: str, name: str) -> None:
    try:
        valid = (isinstance(value, str) and bool(value) and value == value.strip()
                 and len(value.encode("utf-8")) <= 256 and not value.startswith(_RESERVED_PREFIXES)
                 and not any(unicodedata.category(character).startswith("C") for character in value))
    except UnicodeError:
        valid = False
    if not valid:
        raise PrivateIdentifierError(f"{name} is not a bounded private identifier")


def private_alias(key: bytes, kind: str, value: str) -> str:
    """Domain-separated private pseudonym; never returns the input identifier."""
    _require_alias_key(key)
    if (not isinstance(kind, str) or kind not in _ALIAS_DOMAINS or not isinstance(value, str)
            or not value or value != value.strip()):
        raise ValueError("invalid private alias input")
    message = (ALIAS_VERSION + "\x00" + kind + "\x00" + value).encode("utf-8")
    return f"a1_{kind}_" + hmac.new(key, message, hashlib.sha256).hexdigest()


class _AliasGuard:
    def __init__(self, key: bytes) -> None:
        _require_alias_key(key)
        self._key = key
        self._seen: dict[tuple[str, str], str] = {}

    def alias(self, kind: str, value: str) -> str:
        alias = private_alias(self._key, kind, value)
        identity = (kind, alias)
        if identity in self._seen and self._seen[identity] != value:
            raise ValueError("private alias collision")
        self._seen[identity] = value
        return alias


@dataclass(frozen=True, slots=True, repr=False)
class PrivateAliasIndex:
    """Private crosswalk; resolve only in an authorized, non-logging context."""

    key_commitment: str
    _values: Mapping[str, Mapping[str, str]] = field(repr=False)

    def __repr__(self) -> str:
        return "PrivateAliasIndex(<private>)"

    def resolve(self, kind: str, alias: str) -> str:
        try:
            return self._values[kind][alias]
        except (KeyError, TypeError):
            raise ValueError("unknown private alias") from None


def private_alias_index(events: Iterable[SourceEvent], *, alias_key: bytes) -> PrivateAliasIndex:
    """Rebuild a private reversible crosswalk from verified projected events."""
    _require_alias_key(alias_key)
    values: dict[str, dict[str, str]] = {kind: {} for kind in ("item", "event", "episode")}
    for event in events:
        if not isinstance(event, SourceEvent):
            raise TypeError("events must be first-sight records")
        for kind, raw in (("item", event.statement_group_id), ("event", event.event_id),
                          ("episode", event.episode_id)):
            if not raw:
                continue
            alias = private_alias(alias_key, kind, raw)
            if alias in values[kind] and values[kind][alias] != raw:
                raise ValueError("private alias collision")
            values[kind][alias] = raw
    frozen = MappingProxyType({kind: MappingProxyType(items) for kind, items in values.items()})
    return PrivateAliasIndex(alias_key_commitment(alias_key), frozen)


@dataclass(frozen=True, slots=True, repr=False)
class SourceEvent:
    event_id: str
    statement_group_id: str
    episode_id: str
    listing: str
    status_at_statement: str
    availability_class: str
    event_date: str
    revision_index: str
    generic_name: str
    company_name: str
    presentation: str
    therapeutic_category: str
    initial_posting_date: str
    type_of_update: str
    availability_text: str
    related_text: str
    statement_text: str
    reason_for_shortage: str

    def __repr__(self) -> str:
        return "SourceEvent(<private>)"

    def __post_init__(self) -> None:
        for name in SOURCE_FIELDS:
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be text")
        for name in ("event_id", "statement_group_id"):
            require_private_id(getattr(self, name), name)
        for name in ("listing", "status_at_statement"):
            require_identifier(getattr(self, name), name)
        if self.episode_id:
            require_private_id(self.episode_id, "episode_id")
        iso_date(self.event_date)
        if not self.revision_index.isascii() or not self.revision_index.isdigit():
            raise ValueError("revision_index must be a nonnegative integer in decimal text")
        if self.availability_class not in {"blank", "unavailable", "limited", "available", "other"}:
            raise ValueError("unknown first-sight availability class")

    @property
    def at_risk_b(self) -> bool:
        return (self.listing == "shortage" and self.status_at_statement == "current"
                and self.availability_class != "available")

    @property
    def in_natural_frame(self) -> bool:
        return self.listing == "shortage" and self.status_at_statement == "current" and bool(self.episode_id)

    @property
    def notice_text(self) -> str:
        return ("Availability information: " + self.availability_text + "\n"
                + "Related information: " + self.related_text)

    def model_input(self) -> dict[str, str]:
        """Only the fields shown in the common N/C task, without references or metadata."""
        return {"update_date": self.event_date, "notice_text": self.notice_text}

    @property
    def model_input_sha256(self) -> str:
        return _digest(_canonical(self.model_input()))

    @property
    def wording_sha256(self) -> str:
        return notice_fingerprint(self.availability_text, self.related_text)

    @property
    def statement_wording_sha256(self) -> str | None:
        return statement_fingerprint(self.statement_text)

    @property
    def exclusion_fingerprints(self) -> frozenset[str]:
        values = {self.wording_sha256}
        if self.statement_wording_sha256 is not None:
            values.add(self.statement_wording_sha256)
        return frozenset(values)


def project_event(row: Mapping[str, str]) -> SourceEvent:
    """Read exactly the allowlisted keys, without inspecting other source fields."""
    try:
        values = {name: row[name] for name in SOURCE_FIELDS}
    except KeyError as error:
        raise ValueError("events row lacks an allowlisted field") from error
    return SourceEvent(**values)


def project_open_events(compressed: bytes, *, expected_sha256: str) -> tuple[SourceEvent, ...]:
    """Verify and project CSV-gzip bytes supplied by the caller.

    This function never opens or hashes a path. The expected identity must come
    from a permitted open-table record, not from a sealed input.
    """
    if not isinstance(compressed, bytes):
        raise TypeError("open event input must be bytes")
    require_sha256(expected_sha256, "expected_sha256")
    if _digest(compressed) != expected_sha256:
        raise ValueError("open events identity does not match")
    try:
        text = gzip.decompress(compressed).decode("utf-8-sig")
    except (OSError, EOFError, UnicodeError, zlib.error) as error:
        raise ValueError("invalid compressed event table") from error
    rows = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(rows)
    except StopIteration as error:
        raise ValueError("empty events table") from error
    if len(header) != len(set(header)) or any(name not in header for name in SOURCE_FIELDS):
        raise ValueError("events header lacks unique allowlisted fields")
    positions = [header.index(name) for name in SOURCE_FIELDS]
    result = []
    for row in rows:
        if len(row) != len(header):
            raise ValueError("events row has the wrong number of fields")
        result.append(SourceEvent(**{name: row[index] for name, index in zip(SOURCE_FIELDS, positions, strict=True)}))
    return tuple(result)


def display_events(events: Iterable[SourceEvent]) -> tuple[SourceEvent, ...]:
    """Reproduce the registered first-sight display-row rule without outcomes."""
    groups: dict[str, list[SourceEvent]] = {}
    event_ids = set()
    for event in events:
        if not isinstance(event, SourceEvent):
            raise TypeError("events must contain SourceEvent values")
        if event.event_id in event_ids:
            raise ValueError("duplicate event_id")
        event_ids.add(event.event_id)
        groups.setdefault(event.statement_group_id, []).append(event)
    result = []
    for group, members in sorted(groups.items()):
        def rank(event: SourceEvent) -> tuple[str, str, str]:
            key = _draw_key(DISPLAY_SEED, DISPLAY_TAG + group, event.event_id) if event.at_risk_b else event.event_id
            return ("0" if event.at_risk_b else "1", key, event.event_id)
        result.append(min(members, key=rank))
    return tuple(result)


@dataclass(frozen=True, slots=True, repr=False)
class ExclusionSource:
    """An independently prepared ID and wording inventory with explicit provenance."""

    name: str
    statement_ids: frozenset[str]
    notice_fingerprints: frozenset[str]
    whole_field_fingerprints: frozenset[str]
    provenance_sha256: str
    verified_complete: bool

    def __repr__(self) -> str:
        return "ExclusionSource(<private>)"

    def __post_init__(self) -> None:
        require_identifier(self.name, "exclusion name")
        require_sha256(self.provenance_sha256, "exclusion provenance")
        if type(self.verified_complete) is not bool:
            raise TypeError("verified_complete must be bool")
        for name in ("statement_ids", "notice_fingerprints", "whole_field_fingerprints"):
            values = getattr(self, name)
            if not isinstance(values, frozenset):
                raise TypeError(f"{name} must be a frozenset")
            for value in values:
                if name == "statement_ids":
                    require_private_id(value, "excluded statement id")
                else:
                    require_sha256(value, "excluded text fingerprint")


def _catalog(sources: Iterable[ExclusionSource]) -> tuple[tuple[ExclusionSource, ...], str]:
    sources = tuple(sources)
    if any(not isinstance(source, ExclusionSource) for source in sources):
        raise TypeError("exclusions must be ExclusionSource values")
    names = [source.name for source in sources]
    if len(names) != len(set(names)) or set(names) != REQUIRED_EXCLUSIONS:
        raise ValueError("every required exclusion category must appear exactly once")
    if not all(source.verified_complete for source in sources):
        raise ValueError("exclusion inventories must be verified complete before drawing")
    sources = tuple(sorted(sources, key=lambda source: source.name))
    payload = [dict(name=source.name, statement_ids=sorted(source.statement_ids),
                    notice_fingerprints=sorted(source.notice_fingerprints),
                    whole_field_fingerprints=sorted(source.whole_field_fingerprints),
                    provenance_sha256=source.provenance_sha256, verified_complete=True)
               for source in sources]
    return sources, _digest(_canonical({"fingerprint_version": FINGERPRINT_VERSION, "sources": payload}))


def _exclusion_reasons(event: SourceEvent, sources: tuple[ExclusionSource, ...]) -> tuple[str, ...]:
    nonempty_fields = [value for value in (event.availability_text, event.related_text) if _wording(value)]
    return tuple(source.name for source in sources if (
        event.statement_group_id in source.statement_ids
        or not event.exclusion_fingerprints.isdisjoint(source.notice_fingerprints)
        or (_wording(event.statement_text) and
            field_fingerprint(event.statement_text) in source.whole_field_fingerprints)
        or (nonempty_fields and all(field_fingerprint(value) in source.whole_field_fingerprints
                                    for value in nonempty_fields))
    ))


@dataclass(frozen=True, slots=True, repr=False)
class FrameEntry:
    event: SourceEvent
    exclusions: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class SelectedNotice:
    event: SourceEvent
    selection_rank: int
    draw_key: str
    stratum: str | None = None


_NATURAL_DRAW_TOKEN = object()


@dataclass(frozen=True, slots=True)
class _NaturalDrawProof:
    binding_sha256: str
    projected_events_sha256: str
    marker: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True, repr=False)
class SampleDraw:
    cohort: str
    package: str
    target: int
    frame: tuple[FrameEntry, ...]
    selected: tuple[SelectedNotice, ...]
    shortfall: int
    exclusions_sha256: str
    frame_sha256: str
    sample_sha256: str
    requested_quotas: tuple[tuple[str, int], ...] = ()
    achieved_quotas: tuple[tuple[str, int], ...] = ()
    parent_sample_sha256: str | None = None
    _natural_proof: _NaturalDrawProof | None = field(default=None, repr=False, compare=False)

    def __repr__(self) -> str:
        return "SampleDraw(<private>)"


def _natural_binding(draw: SampleDraw, projected_events_sha256: str) -> str:
    return _digest(_canonical({
        "cohort": draw.cohort, "package": draw.package, "target": draw.target, "shortfall": draw.shortfall,
        "exclusions_sha256": draw.exclusions_sha256, "frame_sha256": draw.frame_sha256,
        "sample_sha256": draw.sample_sha256, "requested_quotas": draw.requested_quotas,
        "achieved_quotas": draw.achieved_quotas, "parent_sample_sha256": draw.parent_sample_sha256,
        "projected_events_sha256": projected_events_sha256,
    }))


def _events_hash(events: tuple[SourceEvent, ...]) -> str:
    """Order-independent identity of every projected presentation, not just display rows."""
    return _digest(_canonical([asdict(event) for event in sorted(events, key=lambda event: event.event_id)]))


def _seal_n_draw(draw: SampleDraw, events: tuple[SourceEvent, ...]) -> SampleDraw:
    """Bind an in-process N draw; this is not an external authentication mechanism."""
    if not isinstance(draw, SampleDraw) or draw.cohort != "N":
        raise ValueError("only a retained N draw can be sealed")
    events_sha256 = _events_hash(events)
    return replace(draw, _natural_proof=_NaturalDrawProof(_natural_binding(draw, events_sha256), events_sha256,
                                                          _NATURAL_DRAW_TOKEN))


def _frame(events: Iterable[SourceEvent], sources: tuple[ExclusionSource, ...],
           additional_ids: frozenset[str] = frozenset(),
           additional_wording_ids: frozenset[str] = frozenset()) -> tuple[FrameEntry, ...]:
    return tuple(
        FrameEntry(event, _exclusion_reasons(event, sources) +
                   (("selected_n",) if event.statement_group_id in additional_ids else ()) +
                   (("selected_n_wording",) if event.statement_group_id in additional_wording_ids else ()))
        for event in display_events(events) if event.in_natural_frame
    )


def _frame_hash(frame: tuple[FrameEntry, ...]) -> str:
    return _digest(_canonical([{"event": asdict(entry.event), "exclusions": entry.exclusions}
                               for entry in frame]))


def _sample_hash(selected: tuple[SelectedNotice, ...]) -> str:
    return _digest(_canonical([{
        "item_id": item.event.statement_group_id, "event_id": item.event.event_id,
        "episode_id": item.event.episode_id, "model_input_sha256": item.event.model_input_sha256,
        "selection_rank": item.selection_rank, "draw_key": item.draw_key, "stratum": item.stratum,
    } for item in selected]))


def select_n(events: Iterable[SourceEvent], sources: Iterable[ExclusionSource], *, package: str,
             _gate_token: object | None = None) -> SampleDraw:
    """Private gate entry; direct calls fail closed before reading a frame."""
    if _gate_token is not _DRAW_CAPABILITY:
        raise ValueError("direct draws are disabled; use the evidence gate")
    if package not in N_TARGETS:
        raise ValueError("package must be full or reduced")
    sources, exclusions_hash = _catalog(sources)
    events = tuple(events)
    frame = _frame(events, sources)
    episodes: dict[str, list[SourceEvent]] = {}
    for entry in frame:
        if not entry.exclusions:
            episodes.setdefault(entry.event.episode_id, []).append(entry.event)
    order = sorted(episodes, key=lambda episode: (_draw_key(FOLLOWUP_SEED, N_EPISODE_TAG, episode), episode))
    selected = []
    for episode in order[:N_TARGETS[package]]:
        def key(event: SourceEvent) -> tuple[str, str]:
            return (_draw_key(FOLLOWUP_SEED, N_NOTICE_TAG + episode, event.statement_group_id),
                    event.statement_group_id)
        event = min(episodes[episode], key=key)
        selected.append(SelectedNotice(event, len(selected) + 1, key(event)[0]))
    selected = tuple(selected)
    return _seal_n_draw(SampleDraw("N", package, N_TARGETS[package], frame, selected,
                                   N_TARGETS[package] - len(selected), exclusions_hash,
                                   _frame_hash(frame), _sample_hash(selected)), events)


_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember|t)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_MONTH_RE = re.compile(r"\b" + _MONTH + r"\b", re.I)
_PART = re.compile(r"\b(?:early|mid|middle|late|end|beginning|start)(?:\s+of)?[\s-]+" + _MONTH +
                   r"\b|\b" + _MONTH + r"\s+(?:end|middle)\b", re.I)
_WEEK = re.compile(r"\b(?:this|next|first|second|third|fourth|fifth|last|[1-5](?:st|nd|rd|th))\s+week\b"
                   r"|\bweek\s+(?:of\b|[1-5]\s+of\b)", re.I)
_YEAR = re.compile(r"\b(?:19|20)[0-9]{2}\b")
_SHORT_NUMBER = re.compile(r"\b[0-9]{1,2}\b")
_RELATIVE = re.compile(r"\b[0-9]{1,3}(?:\s*(?:to|-|–)\s*[0-9]{1,3})?\s+(?:days?|weeks?|months?)\b", re.I)
_MAY_VERB = re.compile(
    r"\s+(?:be|not|have|also|vary|continue|experience|take|need|result|cause|still|require|"
    r"occur|impact|affect|see|receive|become|change|apply|include|contain|last|run|increase|"
    r"ship|deliver|recover|arrive|return|provide|manufacture|release)\b", re.I,
)


def _named_month_in(clause: str) -> bool:
    for match in _MONTH_RE.finditer(clause):
        if match.group().casefold() == "may" and (
            not match.group()[0].isupper() or _MAY_VERB.match(clause[match.end():])
        ):
            continue
        return True
    return False


def convention_stratum(event: SourceEvent) -> str | None:
    """Assign the first matched fixed expression class from visible notice text.

    Missing-year detection is deliberately conservative: a clause containing a
    four-digit year or a short number does not qualify for that stratum. This
    avoids silently deciding ambiguous two-digit dates and is a draft rule to
    register before a real frame is sampled.
    """
    text = event.availability_text + "\n" + event.related_text
    if _PART.search(text):
        return "part_of_month"
    if _WEEK.search(text):
        return "week_expression"
    for clause in re.split(r"[;\n!?]", text):
        if _named_month_in(clause) and not _YEAR.search(clause) and not _SHORT_NUMBER.search(clause):
            return "missing_year"
    if _RELATIVE.search(text):
        return "numbered_relative"
    return None


def _n_wording_groups(events: tuple[SourceEvent, ...], selected_ids: frozenset[str]) -> tuple[
    frozenset[str], frozenset[str]
]:
    """Groups matching any N presentation, separated by fingerprint type."""
    notice_hashes = {event.wording_sha256 for event in events if event.statement_group_id in selected_ids}
    statement_hashes = {event.statement_wording_sha256 for event in events
                        if event.statement_group_id in selected_ids and event.statement_wording_sha256 is not None}
    notice_groups = frozenset(event.statement_group_id for event in events if event.wording_sha256 in notice_hashes)
    statement_groups = frozenset(event.statement_group_id for event in events
                                 if event.statement_wording_sha256 in statement_hashes)
    return notice_groups, statement_groups


def _c_selection(frame: tuple[FrameEntry, ...], package: str) -> tuple[
    tuple[SelectedNotice, ...], tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]
]:
    """Deterministic C allocation, also used to validate a retained manifest."""
    pool: dict[str, list[SourceEvent]] = {stratum: [] for stratum in STRATA}
    for entry in frame:
        stratum = convention_stratum(entry.event) if not entry.exclusions else None
        if stratum is not None:
            pool[stratum].append(entry.event)
    for stratum in STRATA:
        pool[stratum].sort(key=lambda event: (
            _draw_key(FOLLOWUP_SEED, C_TAG + stratum, event.statement_group_id),
            event.statement_group_id,
        ))
    counts = dict.fromkeys(STRATA, 0)
    episode_counts: dict[str, int] = {}
    positions = dict.fromkeys(STRATA, 0)
    selected = []

    def take_one(stratum: str) -> bool:
        while positions[stratum] < len(pool[stratum]):
            event = pool[stratum][positions[stratum]]
            positions[stratum] += 1
            if episode_counts.get(event.episode_id, 0) >= 2:
                continue
            episode_counts[event.episode_id] = episode_counts.get(event.episode_id, 0) + 1
            counts[stratum] += 1
            selected.append(SelectedNotice(
                event, len(selected) + 1,
                _draw_key(FOLLOWUP_SEED, C_TAG + stratum, event.statement_group_id), stratum,
            ))
            return True
        return False

    quotas = dict(zip(STRATA, C_QUOTAS[package], strict=True))
    for stratum in STRATA:
        for _ in range(quotas[stratum]):
            if not take_one(stratum):
                break
    target = sum(quotas.values())
    while len(selected) < target:
        progress = False
        for stratum in STRATA:
            if len(selected) == target:
                break
            progress = take_one(stratum) or progress
        if not progress:
            break
    return tuple(selected), tuple(quotas.items()), tuple(counts.items())


def select_c(
    events: Iterable[SourceEvent], sources: Iterable[ExclusionSource], *, package: str,
    natural_draw: SampleDraw, _gate_token: object | None = None,
) -> SampleDraw:
    """Draw fixed C strata and redistribute shortfalls in their fixed order."""
    if _gate_token is not _DRAW_CAPABILITY:
        raise ValueError("direct draws are disabled; use the evidence gate")
    if package not in C_QUOTAS:
        raise ValueError("package must be full or reduced")
    if not isinstance(natural_draw, SampleDraw) or natural_draw.cohort != "N" or natural_draw.package != package:
        raise ValueError("C requires the N draw from the same package")
    if (type(natural_draw.selected) is not tuple
            or any(type(item) is not SelectedNotice or not isinstance(item.event, SourceEvent)
                   for item in natural_draw.selected)):
        raise ValueError("the N draw does not match the supplied frame or exclusions")
    ids = tuple(item.event.statement_group_id for item in natural_draw.selected)
    if len(ids) != len(set(ids)):
        raise ValueError("N exclusion IDs must be unique")
    sources, exclusions_hash = _catalog(sources)
    events = tuple(events)
    first_frame = _frame(events, sources)
    proof = natural_draw._natural_proof
    events_sha256 = _events_hash(events)
    if (type(proof) is not _NaturalDrawProof or proof.marker is not _NATURAL_DRAW_TOKEN
            or proof.projected_events_sha256 != events_sha256
            or proof.binding_sha256 != _natural_binding(natural_draw, events_sha256)
            or natural_draw.frame != first_frame or natural_draw.frame_sha256 != _frame_hash(first_frame)
            or natural_draw.exclusions_sha256 != exclusions_hash
            or natural_draw.sample_sha256 != _sample_hash(natural_draw.selected)
            or natural_draw.target != N_TARGETS[package]
            or len(ids) > natural_draw.target
            or natural_draw.shortfall != natural_draw.target - len(ids)
            or natural_draw.requested_quotas or natural_draw.achieved_quotas
            or natural_draw.parent_sample_sha256 is not None):
        raise ValueError("the N draw does not match the supplied frame or exclusions")
    by_id = {entry.event.statement_group_id: entry for entry in first_frame}
    if not set(ids).issubset(by_id):
        raise ValueError("every N exclusion must be present in the natural frame")
    if any(by_id[item_id].exclusions for item_id in ids):
        raise ValueError("an N exclusion was not eligible under the supplied inventories")
    if ([item.selection_rank for item in natural_draw.selected] != list(range(1, len(ids) + 1))
            or len({item.event.episode_id for item in natural_draw.selected}) != len(ids)
            or any(item.event != by_id[item.event.statement_group_id].event or item.stratum is not None
                   or item.draw_key != _draw_key(FOLLOWUP_SEED, N_NOTICE_TAG + item.event.episode_id,
                                                 item.event.statement_group_id) for item in natural_draw.selected)):
        raise ValueError("the N draw does not match the supplied frame or exclusions")
    notice_groups, statement_groups = _n_wording_groups(events, frozenset(ids))
    frame = _frame(events, sources, frozenset(ids), notice_groups | statement_groups)
    selected, quotas, counts = _c_selection(frame, package)
    target = sum(C_QUOTAS[package])
    return SampleDraw("C", package, target, frame, selected, target - len(selected),
                      exclusions_hash, _frame_hash(frame), _sample_hash(selected),
                      quotas, counts, natural_draw.sample_sha256)


def sample_manifest(draw: SampleDraw, *, events_sha256: str, alias_key: bytes,
                    _gate_token: object | None = None) -> dict:
    """Materialize a private, keyed-alias frame for locking and later reconciliation."""
    if _gate_token is not _DRAW_CAPABILITY:
        raise ValueError("direct manifests are disabled; use the evidence gate")
    if not isinstance(draw, SampleDraw) or draw.cohort not in {"N", "C"}:
        raise ValueError("an N or C draw is required")
    _require_alias_key(alias_key)
    require_sha256(events_sha256, "open events hash")
    if (draw.frame_sha256 != _frame_hash(draw.frame) or draw.sample_sha256 != _sample_hash(draw.selected)
            or draw.shortfall != draw.target - len(draw.selected)):
        raise ValueError("draw hashes or shortfall do not match the retained records")
    if [item.selection_rank for item in draw.selected] != list(range(1, len(draw.selected) + 1)):
        raise ValueError("selected ranks must be consecutive")
    eligible = [entry.event for entry in draw.frame if not entry.exclusions]
    by_id = {entry.event.statement_group_id: entry for entry in draw.frame}
    if len(by_id) != len(draw.frame):
        raise ValueError("the retained frame has duplicate statement identities")
    private_alias_index((entry.event for entry in draw.frame), alias_key=alias_key)
    aliases = _AliasGuard(alias_key)
    selected = {item.event.statement_group_id: item for item in draw.selected}
    if (len(selected) != len(draw.selected)
            or any(item_id not in by_id or by_id[item_id].exclusions
                   or by_id[item_id].event != item.event for item_id, item in selected.items())):
        raise ValueError("selected items must be distinct eligible frame records")
    episode_rank, within_episode_rank, stratum_rank = {}, {}, {}
    if draw.cohort == "N":
        if draw.package not in N_TARGETS or draw.target != N_TARGETS[draw.package]:
            raise ValueError("N target must match a predefined package")
        episodes = sorted({event.episode_id for event in eligible},
                          key=lambda episode: (_draw_key(FOLLOWUP_SEED, N_EPISODE_TAG, episode), episode))
        episode_rank = {episode: i + 1 for i, episode in enumerate(episodes)}
        for episode in episodes:
            members = [event for event in eligible if event.episode_id == episode]
            members.sort(key=lambda event: (
                _draw_key(FOLLOWUP_SEED, N_NOTICE_TAG + episode, event.statement_group_id),
                event.statement_group_id,
            ))
            within_episode_rank.update({event.statement_group_id: i + 1 for i, event in enumerate(members)})
        if len({item.event.episode_id for item in draw.selected}) != len(draw.selected):
            raise ValueError("N requires one notice per episode")
        expected_order = [event.statement_group_id for episode in episodes[:draw.target]
                          for event in eligible if event.episode_id == episode
                          and within_episode_rank[event.statement_group_id] == 1]
        if [item.event.statement_group_id for item in draw.selected] != expected_order:
            raise ValueError("N sample differs from the fixed episode and notice ranks")
        if any(item.draw_key != _draw_key(FOLLOWUP_SEED, N_NOTICE_TAG + item.event.episode_id,
                                          item.event.statement_group_id) for item in draw.selected):
            raise ValueError("N selected draw keys do not match their identities")
    else:
        if draw.parent_sample_sha256 is None:
            raise ValueError("C must retain its parent N sample identity")
        require_sha256(draw.parent_sample_sha256, "parent N sample hash")
        if (draw.package not in C_QUOTAS or draw.target != sum(C_QUOTAS[draw.package])
                or draw.requested_quotas != tuple(zip(STRATA, C_QUOTAS[draw.package], strict=True))):
            raise ValueError("C quotas must match a predefined package")
        expected_selected, expected_quotas, expected_achieved = _c_selection(draw.frame, draw.package)
        if (draw.selected != expected_selected or draw.requested_quotas != expected_quotas
                or draw.achieved_quotas != expected_achieved):
            raise ValueError("C selection differs from its fixed frame and quotas")
        for stratum in STRATA:
            members = [event for event in eligible if convention_stratum(event) == stratum]
            members.sort(key=lambda event: (_draw_key(FOLLOWUP_SEED, C_TAG + stratum,
                                                      event.statement_group_id), event.statement_group_id))
            stratum_rank.update({event.statement_group_id: i + 1 for i, event in enumerate(members)})
        episodes = [item.event.episode_id for item in draw.selected]
        if any(episodes.count(episode) > 2 for episode in set(episodes)):
            raise ValueError("C exceeds its episode cap")
        if any(item.stratum not in STRATA or item.stratum != convention_stratum(item.event)
               or item.draw_key != _draw_key(FOLLOWUP_SEED, C_TAG + item.stratum,
                                              item.event.statement_group_id) for item in draw.selected):
            raise ValueError("C strata or draw keys differ from their fixed expressions")
        achieved = tuple((stratum, sum(item.stratum == stratum for item in draw.selected)) for stratum in STRATA)
        if draw.achieved_quotas != achieved:
            raise ValueError("C achieved quotas do not match the selected items")
    frame_rows = []
    for entry in draw.frame:
        event = entry.event
        item = selected.get(event.statement_group_id)
        frame_rows.append({
            "item_id": aliases.alias("item", event.statement_group_id),
            "event_id": aliases.alias("event", event.event_id),
            "episode_id": aliases.alias("episode", event.episode_id),
            "visible_input_alias": aliases.alias("visible", event.model_input_sha256),
            "wording_alias": aliases.alias("notice", event.wording_sha256),
            "statement_wording_alias": (None if event.statement_wording_sha256 is None else
                                        aliases.alias("statement", event.statement_wording_sha256)),
            "exclusions": list(entry.exclusions), "episode_rank": episode_rank.get(event.episode_id),
            "within_episode_rank": within_episode_rank.get(event.statement_group_id),
            "stratum": convention_stratum(event) if draw.cohort == "C" and not entry.exclusions else None,
            "within_stratum_rank": stratum_rank.get(event.statement_group_id),
            "selected_rank": None if item is None else item.selection_rank,
            "selected_draw_key_alias": None if item is None else aliases.alias("draw", item.draw_key),
        })
    frame_rows.sort(key=lambda row: row["item_id"])
    manifest = {
        "schema": "followup-private-sample-v3", "fingerprint_version": FINGERPRINT_VERSION,
        "alias_version": ALIAS_VERSION, "alias_key_commitment": alias_key_commitment(alias_key),
        "commitment_version": COMMITMENT_VERSION,
        "cohort": draw.cohort, "package": draw.package, "target": draw.target,
        "shortfall": draw.shortfall, "events_commitment": digest_commitment(alias_key, "events", events_sha256),
        "exclusions_commitment": digest_commitment(alias_key, "exclusions", draw.exclusions_sha256),
        "frame_commitment": digest_commitment(alias_key, "frame", draw.frame_sha256),
        "sample_commitment": digest_commitment(alias_key, "sample", draw.sample_sha256),
        "parent_sample_commitment": (None if draw.parent_sample_sha256 is None else
                                     digest_commitment(alias_key, "sample", draw.parent_sample_sha256)),
        "requested_quotas": list(draw.requested_quotas), "achieved_quotas": list(draw.achieved_quotas),
        "frame": frame_rows,
    }
    manifest["manifest_commitment"] = private_commitment(alias_key, "sample_manifest", _canonical(manifest))
    return manifest
