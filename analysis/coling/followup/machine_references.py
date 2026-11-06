"""Outcome-free, blinded machine-reference records for N, C, and R.

These records are machine judgments, not human annotations, human gold,
independent human judgments, or a replication. They are deliberately separate
from the existing human reference and role-validation types. This module reads
and writes no files, makes no calls, draws no samples, and performs no model
evaluation. A separate, later registration and independently checked approval
are required before any real collection or evaluation.

Identity and exposure fields are attestations, not proof of the served model,
checkpoint, route, blinding, registration, or independence of model errors.
Only the allowlisted request payload is intended for a judge; the enclosing
record also contains private assignment and provenance information. A declared
synthetic scope does not prove that its supplied material is invented. Real
scope is disabled even when registration claims are supplied. Source projection
and membership, final prompt bytes, full privacy review, served identities, a
verified pushed registration, and a durable call ledger remain external hard
prerequisites. Attempt identities are checked only within the supplied record,
not globally. Source and summary hashes commit to supplied records, not raw
transport bytes.

N/C first-pass answers contain exactly ``alternatives`` and
``unresolved_reason``. Each alternative contains ``statement_type``,
``period_status`` (finite, none, or unresolved), ``start``, ``end``,
``certainty``, and ``quote``; unknown fields use null. An N adjudication
contains ``reference`` and ``rationale``; C contains separate ``defensible``,
``specified``, and ``rationale`` fields. R answers contain ``targets``, six
named ``checks``, ``material_valid``, and ``reason``. Each target identifies an
opaque variant and carries its status, target date, alternative dates, quote,
and date roles. R adjudication contains ``reference`` and ``rationale``.
All fields are required, and dates are ISO calendar dates or null.

Literal ISO dates in quoted source text provide only limited lexical support;
co-occurrence does not establish semantic truth. The at-sign refusal does not
detect all personal information or an answer embedded as ordinary notice text.
Recognizable redaction markers are refused in forwarded quotes, but their
absence does not prove that a source or quote was never redacted.
An adjudicated machine-valid label does not establish true material validity.
Even unanimous machine material rejections remain unresolved candidates.
Role HMAC aliases require caller-supplied private material. Format checks do not
establish entropy, and deterministic notice text may still be matched against
generated material. Blinded role eligibility is disabled pending a separate
generator revision and independent verification. Supplied seed commitments do
not establish source membership, a published registration, or a generator lock.
Private-material filtering checks known representations, not complete privacy.

The selected synthetic draft adds a separate MADJ blind proposal before the
exposed adjudication. C uses two separate exposed adjudications: the absent
stage completes before any specified view is prepared. Blind views contain only
source material and, after the absent adjudication, the pinned convention. Each
exposed view excludes MADJ's private proposals. The older three-stage draft is
diagnostic only. Local records do not prove submission timing or model context.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timezone
from enum import Enum
from typing import Iterable

from .parsing import _json, _keys
from .records import (
    Certainty, ParseStatus, StatementType, iso_date, require_identifier as _record_identifier,
    require_sha256 as _record_sha256,
)
from .role_materials import GENERATOR_VERSION, RoleSeed, RoleVariant, _make_seed, validate_structure


_FIRST_STAGE = {"N": "natural", "C": "unspecified", "R": "role"}
_JUDGE_CODES = frozenset({"M1", "M2", "MADJ"})
LEGACY_PROTOCOL = "legacy_three_stage_draft"
SELECTED_PROTOCOL = "blind_madj_separate_c_adjudications_synthetic_v2"
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:+-]*")
_ROLE_NAMES = frozenset({
    "current_recovery", "next_review", "publication", "superseded_issue", "superseded_recovery",
    "administrative", "other",
})
_CHECK_NAMES = (
    "unique_current_target", "coherent_chronology", "competing_role_preserves_target",
    "neutral_role_unrelated", "comparable_length_and_syntax", "position_preserves_meaning",
)


def _exact(value: object, expected: type, name: str) -> None:
    if type(value) is not expected:
        raise TypeError(f"{name} must be an exact {expected.__name__}")


def _utf8(value: str, name: str) -> None:
    _exact(value, str, name)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid Unicode text") from exc


def require_identifier(value: str, name: str) -> None:
    _utf8(value, name)
    _record_identifier(value, name)


def require_sha256(value: str, name: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{name} must be a lowercase SHA256")
    _record_sha256(value, name)


def _utc(value: datetime, name: str) -> None:
    if type(value) is not datetime or value.tzinfo is not timezone.utc:
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _model_id(value: str, name: str) -> None:
    if type(value) is not str or _MODEL_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact provider-qualified model ID")


def _pinned(value: str, name: str) -> None:
    require_identifier(value, name)
    if value.casefold() in {
        "auto", "automatic", "default", "any", "unknown", "unspecified", "latest", "current",
    } or "*" in value:
        raise ValueError(f"{name} must identify a pinned value")


def _reason(value: str | None, name: str) -> None:
    if value is not None:
        require_identifier(value, name)


@dataclass(frozen=True, slots=True)
class Judge:
    code: str
    model_id: str
    model_revision: str
    provider_route: str
    precision: str

    def __post_init__(self) -> None:
        _exact(self, Judge, "judge")
        _exact(self.code, str, "judge code")
        if self.code not in _JUDGE_CODES:
            raise ValueError("machine judges use only M1, M2, and MADJ")
        _model_id(self.model_id, "judge model_id")
        _pinned(self.model_revision, "model_revision")
        _pinned(self.provider_route, "provider_route")
        _pinned(self.precision, "precision")


@dataclass(frozen=True, slots=True)
class StageBinding:
    judge_code: str
    cohort: str
    stage: str
    template_id: str
    template_sha256: str
    decoding_sha256: str
    schema_sha256: str
    parser_sha256: str
    condition_sha256: str | None = None

    def __post_init__(self) -> None:
        _exact(self, StageBinding, "stage binding")
        for name in ("judge_code", "cohort", "stage"):
            _exact(getattr(self, name), str, name)
        if self.judge_code not in _JUDGE_CODES or self.cohort not in _FIRST_STAGE:
            raise ValueError("unknown judge or cohort")
        allowed = ({"adjudication", "adjudication_absent", "adjudication_specified",
                    "blind_unspecified", "blind_specified"} if self.cohort == "C" else
                   {"adjudication", "blind_proposal"}) if self.judge_code == "MADJ" else {
            _FIRST_STAGE[self.cohort], *({"specified"} if self.cohort == "C" else set()),
        }
        if self.stage not in allowed:
            raise ValueError("stage does not match the machine judge and cohort")
        require_identifier(self.template_id, "template_id")
        for name in ("template_sha256", "decoding_sha256", "schema_sha256", "parser_sha256"):
            require_sha256(getattr(self, name), name)
        needs_condition = self.cohort == "C" and self.stage in {
            "specified", "blind_specified", "adjudication", "adjudication_specified",
        }
        if needs_condition:
            require_sha256(self.condition_sha256, "condition_sha256")
        elif self.condition_sha256 is not None:
            raise ValueError("this stage must not include the convention block")


@dataclass(frozen=True, slots=True)
class MachineProtocol:
    """Draft identity manifest; constructing it is not registration."""

    protocol_id: str
    evaluated_model_ids: tuple[str, ...]
    judges: tuple[Judge, ...]
    bindings: tuple[StageBinding, ...]
    reference_version: str
    data_scope: str
    role_alias_commitment_sha256: str | None
    role_seed_commitments: tuple[str, ...]
    protocol_design: str

    def __post_init__(self) -> None:
        _exact(self, MachineProtocol, "protocol")
        require_identifier(self.protocol_id, "protocol_id")
        require_identifier(self.reference_version, "reference_version")
        _exact(self.data_scope, str, "data_scope")
        if self.data_scope not in {"synthetic", "real"}:
            raise ValueError("data_scope must be explicitly synthetic or real")
        _exact(self.protocol_design, str, "protocol_design")
        if self.protocol_design not in {LEGACY_PROTOCOL, SELECTED_PROTOCOL}:
            raise ValueError("protocol_design must explicitly identify the draft")
        if type(self.evaluated_model_ids) is not tuple or not self.evaluated_model_ids:
            raise ValueError("the complete evaluated-model ID set must be supplied")
        for model in self.evaluated_model_ids:
            _model_id(model, "evaluated model_id")
        evaluated = [model.casefold() for model in self.evaluated_model_ids]
        if len(set(evaluated)) != len(evaluated):
            raise ValueError("evaluated-model IDs must be distinct")
        if type(self.judges) is not tuple or len(self.judges) != 3 or any(
            type(judge) is not Judge for judge in self.judges
        ):
            raise ValueError("exactly three machine judges are required")
        for judge in self.judges:
            Judge.__post_init__(judge)
        if {judge.code for judge in self.judges} != _JUDGE_CODES:
            raise ValueError("exactly one M1, M2, and MADJ is required")
        models = [judge.model_id.casefold() for judge in self.judges]
        if len(set(models)) != 3 or set(models) & set(evaluated):
            raise ValueError("judge and evaluated model IDs must all be distinct")
        if type(self.bindings) is not tuple or not self.bindings or any(
            type(binding) is not StageBinding for binding in self.bindings
        ):
            raise ValueError("explicit stage bindings are required")
        for binding in self.bindings:
            StageBinding.__post_init__(binding)
        has_role = any(binding.cohort == "R" for binding in self.bindings)
        if has_role or self.role_alias_commitment_sha256 is not None:
            require_sha256(self.role_alias_commitment_sha256, "role_alias_commitment_sha256")
        if type(self.role_seed_commitments) is not tuple or (has_role and not self.role_seed_commitments):
            raise ValueError("role stages require an explicit private seed commitment manifest")
        for value in self.role_seed_commitments:
            require_sha256(value, "role_seed_commitment")
        if len(set(self.role_seed_commitments)) != len(self.role_seed_commitments):
            raise ValueError("role seed commitments must be distinct")
        if self.role_seed_commitments and self.role_alias_commitment_sha256 is None:
            raise ValueError("role seed commitments require an alias-key commitment")
        identities = [(item.judge_code, item.cohort, item.stage) for item in self.bindings]
        if len(set(identities)) != len(identities):
            raise ValueError("each judge and stage needs exactly one binding")
        blind_bindings = [item for item in self.bindings if item.judge_code == "MADJ" and item.stage.startswith("blind_")]
        if self.protocol_design == LEGACY_PROTOCOL and blind_bindings:
            raise ValueError("legacy draft cannot contain selected blind proposal stages")
        if self.protocol_design == LEGACY_PROTOCOL and any(
            item.judge_code == "MADJ" and item.stage in {"adjudication_absent", "adjudication_specified"}
            for item in self.bindings
        ):
            raise ValueError("legacy draft cannot contain the selected separate C adjudications")
        if self.protocol_design == SELECTED_PROTOCOL:
            for cohort in {item.cohort for item in self.bindings}:
                required = {(code, cohort, _FIRST_STAGE[cohort]) for code in ("M1", "M2")}
                if cohort == "C":
                    if ("MADJ", "C", "adjudication") in identities:
                        raise ValueError("selected C cannot use a combined exposed adjudication")
                    required.update((code, cohort, "specified") for code in ("M1", "M2"))
                    required.update({("MADJ", cohort, "blind_unspecified"), ("MADJ", cohort, "adjudication_absent"),
                                     ("MADJ", cohort, "blind_specified"), ("MADJ", cohort, "adjudication_specified")})
                else:
                    required.update({("MADJ", cohort, "blind_proposal"), ("MADJ", cohort, "adjudication")})
                if not required <= set(identities):
                    raise ValueError("selected protocol requires every pinned blind and exposed stage")
                madj = [item for item in self.bindings if item.judge_code == "MADJ" and item.cohort == cohort]
                for name in ("template_id", "template_sha256", "parser_sha256"):
                    if len({getattr(item, name) for item in madj}) != len(madj):
                        raise ValueError("MADJ blind and exposed template and parser identities must differ")
        template_hashes: dict[str, str] = {}
        conditions = set()
        for binding in self.bindings:
            previous = template_hashes.setdefault(binding.template_id, binding.template_sha256)
            if previous != binding.template_sha256:
                raise ValueError("one template ID cannot identify different template hashes")
            if binding.condition_sha256 is not None:
                conditions.add(binding.condition_sha256)
        if len(conditions) > 1:
            raise ValueError("C specified and adjudication stages must share the same convention block")

    def judge(self, code: str) -> Judge:
        MachineProtocol.__post_init__(self)
        _exact(code, str, "judge code")
        for judge in self.judges:
            if judge.code == code:
                return judge
        raise ValueError("judge is not assigned")

    def binding(self, code: str, cohort: str, stage: str) -> StageBinding:
        MachineProtocol.__post_init__(self)
        for value, name in ((code, "judge code"), (cohort, "cohort"), (stage, "stage")):
            _exact(value, str, name)
        for binding in self.bindings:
            if (binding.judge_code, binding.cohort, binding.stage) == (code, cohort, stage):
                return binding
        raise ValueError("no exact binding for this judge, cohort, and stage")

    @property
    def sha256(self) -> str:
        MachineProtocol.__post_init__(self)
        value = {
            "kind": "machine-reference-protocol-v1",
            "protocol_id": self.protocol_id,
            "reference_version": self.reference_version,
            "data_scope": self.data_scope,
            "protocol_design": self.protocol_design,
            "role_alias_commitment_sha256": self.role_alias_commitment_sha256,
            "role_seed_commitments": sorted(self.role_seed_commitments),
            "evaluated_model_ids": sorted(self.evaluated_model_ids),
            "judges": [asdict(item) for item in sorted(self.judges, key=lambda item: item.code)],
            "bindings": [asdict(item) for item in sorted(
                self.bindings, key=lambda item: (item.judge_code, item.cohort, item.stage)
            )],
        }
        return _sha256(_canonical(value))

    @property
    def role_seed_manifest_sha256(self) -> str | None:
        MachineProtocol.__post_init__(self)
        if not self.role_seed_commitments:
            return None
        value = {"kind": "machine-private-role-seed-manifest-v2",
                 "role_alias_commitment_sha256": self.role_alias_commitment_sha256,
                 "role_seed_commitments": sorted(self.role_seed_commitments)}
        return _sha256(_canonical(value))


@dataclass(frozen=True, slots=True)
class BlindNotice:
    item_id: str
    update_date: date
    notice_text: str

    def __post_init__(self) -> None:
        _exact(self, BlindNotice, "notice")
        require_identifier(self.item_id, "item_id")
        if type(self.update_date) is not date:
            raise TypeError("update_date must be a calendar date")
        _utf8(self.notice_text, "notice_text")
        if not self.notice_text.strip():
            raise ValueError("notice_text must be nonempty text")

    def visible(self) -> dict[str, str]:
        BlindNotice.__post_init__(self)
        value = {"update_date": self.update_date.isoformat(), "notice_text": self.notice_text}
        _refuse_at_sign(value)
        return value


class PrivateRoleBlinding:
    """Private caller-supplied claims; shape checks do not establish entropy."""

    __slots__ = ("_private_seed_id", "_alias_key")

    def __init__(self, *, private_seed_id: str, alias_key: bytes) -> None:
        _exact(self, PrivateRoleBlinding, "private role blinding")
        object.__setattr__(self, "_private_seed_id", private_seed_id)
        object.__setattr__(self, "_alias_key", alias_key)
        PrivateRoleBlinding._validate(self)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("private role blinding is immutable")

    def __repr__(self) -> str:
        return "PrivateRoleBlinding(<private>)"

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("private role blinding cannot be serialized into a judge view")

    def _validate(self) -> None:
        _exact(self, PrivateRoleBlinding, "private role blinding")
        if (type(self._private_seed_id) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self._private_seed_id) is None
                or len(set(self._private_seed_id)) < 8):
            raise ValueError("private role seed needs a high-entropy-looking 64-hex identity; format is not proof")
        if type(self._alias_key) is not bytes or len(self._alias_key) != 32 or len(set(self._alias_key)) < 16:
            raise ValueError("role alias key needs a high-entropy-looking 32-byte value; format is not proof")

    @property
    def key_commitment_sha256(self) -> str:
        PrivateRoleBlinding._validate(self)
        return hashlib.sha256(b"collie-machine-role-key-commitment-v2\x00" + self._alias_key).hexdigest()

    @property
    def seed_commitment_sha256(self) -> str:
        PrivateRoleBlinding._validate(self)
        message = b"collie-machine-role-seed-commitment-v2\x00" + self._private_seed_id.encode("ascii")
        return hmac.new(self._alias_key, message, hashlib.sha256).hexdigest()

    @property
    def group_id(self) -> str:
        PrivateRoleBlinding._validate(self)
        message = b"collie-machine-role-group-v2\x00" + self._private_seed_id.encode("ascii")
        return "G" + hmac.new(self._alias_key, message, hashlib.sha256).hexdigest()

    def opaque_variant_map(self) -> tuple[tuple[str, str], ...]:
        PrivateRoleBlinding._validate(self)
        result = []
        for position in ("first", "last"):
            for arm in ("competitor", "neutral"):
                variant_id = f"{self._private_seed_id}:{arm}:{position}"
                message = b"collie-machine-role-variant-v2\x00" + variant_id.encode("ascii")
                result.append(("V" + hmac.new(self._alias_key, message, hashlib.sha256).hexdigest(), variant_id))
        return tuple(result)


def _visible_strings(value: object, seen: set[int] | None = None, depth: int = 0) -> Iterable[str]:
    """Walk decoded payload strings, rejecting unsupported or cyclic structures."""
    if depth > 40:
        raise ValueError("visible payload nesting exceeds the validation limit")
    if type(value) is str:
        _utf8(value, "visible payload")
        yield value
        return
    if value is None or type(value) in {bool, int}:
        return
    if type(value) not in {dict, list, tuple}:
        raise TypeError("visible payload must use plain JSON values")
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        raise ValueError("visible payload contains a cycle")
    seen.add(identity)
    try:
        if type(value) is dict:
            for key, item in value.items():
                _exact(key, str, "visible payload key")
                yield from _visible_strings(key, seen, depth + 1)
                yield from _visible_strings(item, seen, depth + 1)
        else:
            for item in value:
                yield from _visible_strings(item, seen, depth + 1)
    finally:
        seen.remove(identity)


def _refuse_private_role_material(blinding: PrivateRoleBlinding, visible: object) -> None:
    """Refuse normalized private representations in decoded payload strings."""
    PrivateRoleBlinding._validate(blinding)
    representations = [blinding._private_seed_id, blinding._alias_key.hex(),
                       base64.b64encode(blinding._alias_key).decode("ascii")]
    try:
        representations.append(blinding._alias_key.decode("utf-8"))
    except UnicodeDecodeError:
        pass
    private_values = tuple(unicodedata.normalize("NFKC", value).casefold() for value in representations)
    if any(not value for value in private_values):
        raise ValueError("private role material has an uncheckable normalized representation")
    for text in _visible_strings(visible):
        normalized = unicodedata.normalize("NFKC", text).casefold()
        if any(value in normalized for value in private_values):
            raise ValueError("private role seed or alias material cannot enter a judge view")


@dataclass(frozen=True, slots=True)
class BlindRoleSet:
    """Four opaque variants; seed factors and the expected target stay outside."""

    group_id: str
    notices: tuple[BlindNotice, ...]
    blinding: PrivateRoleBlinding = field(repr=False)

    def __post_init__(self) -> None:
        _exact(self, BlindRoleSet, "role material")
        _exact(self.blinding, PrivateRoleBlinding, "private role blinding")
        PrivateRoleBlinding._validate(self.blinding)
        if type(self.group_id) is not str or re.fullmatch(r"G[0-9a-f]{64}", self.group_id) is None:
            raise ValueError("role groups require an opaque G identifier")
        if self.group_id != self.blinding.group_id:
            raise ValueError("role group does not match its private HMAC binding")
        if type(self.notices) is not tuple or len(self.notices) != 4 or any(
            type(notice) is not BlindNotice for notice in self.notices
        ):
            raise ValueError("a role group requires four notices")
        for notice in self.notices:
            BlindNotice.__post_init__(notice)
        ids = [notice.item_id for notice in self.notices]
        if len(set(ids)) != 4 or any(re.fullmatch(r"V[0-9a-f]{64}", item) is None for item in ids):
            raise ValueError("role variants require distinct opaque V identifiers")
        if set(ids) != {opaque for opaque, _ in self.blinding.opaque_variant_map()}:
            raise ValueError("role variants do not match the private HMAC mapping")

    def visible(self) -> dict[str, object]:
        BlindRoleSet.__post_init__(self)
        value = {"notices": [{"item_id": notice.item_id, **notice.visible()} for notice in self.notices]}
        _refuse_private_role_material(self.blinding, value)
        _refuse_at_sign(value)
        return value


@dataclass(frozen=True, slots=True)
class CallIdentity:
    judge_code: str
    cohort: str
    stage: str
    protocol_sha256: str
    subject_id: str
    material_sha256: str
    attempt_id: str
    sources_sha256: str = field(repr=False)
    model_id: str
    model_revision: str
    provider_route: str
    precision: str
    template_id: str
    template_sha256: str
    decoding_sha256: str
    schema_sha256: str
    parser_sha256: str
    input_sha256: str

    def __post_init__(self) -> None:
        _exact(self, CallIdentity, "call identity")
        for name in ("judge_code", "cohort", "stage"):
            _exact(getattr(self, name), str, name)
        if self.judge_code not in _JUDGE_CODES or self.cohort not in _FIRST_STAGE:
            raise ValueError("unknown identity judge or cohort")
        require_identifier(self.stage, "stage")
        require_identifier(self.subject_id, "subject_id")
        require_identifier(self.attempt_id, "attempt_id")
        _model_id(self.model_id, "model_id")
        _pinned(self.model_revision, "model_revision")
        _pinned(self.provider_route, "provider_route")
        _pinned(self.precision, "precision")
        require_identifier(self.template_id, "template_id")
        for name in ("protocol_sha256", "material_sha256", "sources_sha256", "template_sha256", "decoding_sha256",
                     "schema_sha256", "parser_sha256", "input_sha256"):
            require_sha256(getattr(self, name), name)


class DateSupport(str, Enum):
    LITERAL_ISO = "literal_iso_in_source_quote"
    UNVERIFIED = "date_support_unverified"
    NOT_APPLICABLE = "date_support_not_applicable"


@dataclass(frozen=True, slots=True)
class MachineAlternative:
    statement_type: StatementType | None
    period_status: str
    start: date | None
    end: date | None
    certainty: Certainty | None
    quote: str
    quote_valid: bool | None
    start_support: DateSupport
    end_support: DateSupport

    def __post_init__(self) -> None:
        _exact(self, MachineAlternative, "machine alternative")
        if self.statement_type is not None and type(self.statement_type) is not StatementType:
            raise TypeError("statement_type must be a StatementType or None")
        _exact(self.period_status, str, "period_status")
        if self.period_status not in {"finite", "none", "unresolved"}:
            raise ValueError("unknown period status")
        if any(value is not None and type(value) is not date for value in (self.start, self.end)):
            raise TypeError("endpoints must be calendar dates or None")
        if self.period_status == "none" and (self.start is not None or self.end is not None):
            raise ValueError("no period cannot carry endpoints")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not follow end")
        if self.certainty is not None and type(self.certainty) is not Certainty:
            raise TypeError("certainty must be a Certainty or None")
        if self.period_status == "finite" and (
            self.statement_type is StatementType.NONE
            or self.certainty in {Certainty.UNDETERMINED, Certainty.NO_STATEMENT}
        ):
            raise ValueError("finite period conflicts with the known type or certainty")
        if self.statement_type is not None and self.certainty is not None and (
            (self.statement_type is StatementType.NONE) != (self.certainty is Certainty.NO_STATEMENT)
        ):
            raise ValueError("known none and no_statement must occur together")
        if type(self.quote) is not str or (self.quote_valid is not None and type(self.quote_valid) is not bool):
            raise TypeError("quote and its verdict have invalid types")
        if type(self.start_support) is not DateSupport or type(self.end_support) is not DateSupport:
            raise TypeError("date support must use the machine evidence labels")


@dataclass(frozen=True, slots=True)
class MachineReading:
    alternatives: tuple[MachineAlternative, ...]
    unresolved_reason: str | None

    def __post_init__(self) -> None:
        _exact(self, MachineReading, "machine reading")
        if type(self.alternatives) is not tuple or any(
            type(item) is not MachineAlternative for item in self.alternatives
        ):
            raise TypeError("alternatives must be a tuple of machine readings")
        for item in self.alternatives:
            MachineAlternative.__post_init__(item)
        _reason(self.unresolved_reason, "unresolved_reason")
        if not self.alternatives and self.unresolved_reason is None:
            raise ValueError("an empty reading needs an unresolved reason")


@dataclass(frozen=True, slots=True)
class MachineDateRole:
    role: str | None
    date: date | None
    quote: str
    quote_valid: bool | None


@dataclass(frozen=True, slots=True)
class MachineRoleTarget:
    variant_id: str
    status: str
    target_date: date | None
    alternatives: tuple[date, ...]
    quote: str
    quote_valid: bool | None
    date_roles: tuple[MachineDateRole, ...]


@dataclass(frozen=True, slots=True)
class MachineRoleChecks:
    unique_current_target: bool | None
    coherent_chronology: bool | None
    competing_role_preserves_target: bool | None
    neutral_role_unrelated: bool | None
    comparable_length_and_syntax: bool | None
    position_preserves_meaning: bool | None

    def __post_init__(self) -> None:
        _exact(self, MachineRoleChecks, "role checks")
        if any(value is not None and type(value) is not bool for value in asdict(self).values()):
            raise TypeError("role checks must be true, false, or unknown")


@dataclass(frozen=True, slots=True)
class MachineRoleReading:
    targets: tuple[MachineRoleTarget, ...]
    checks: MachineRoleChecks
    material_valid: bool | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class NaturalDecision:
    reference: MachineReading
    rationale: str


@dataclass(frozen=True, slots=True)
class ConventionDecision:
    defensible: MachineReading
    specified: MachineReading
    rationale: str


@dataclass(frozen=True, slots=True)
class RoleDecision:
    reference: MachineRoleReading
    rationale: str


@dataclass(frozen=True, slots=True)
class BlindReceipt:
    """Private chronology commitment; it contains no blind response text."""

    protocol_sha256: str
    material_sha256: str
    subject_id: str
    cohort: str
    stage: str
    judgment_id: str
    attempt_id: str
    returned: bool
    submitted_utc: datetime
    record_sha256: str

    def __post_init__(self) -> None:
        _exact(self, BlindReceipt, "blind receipt")
        for name in ("protocol_sha256", "material_sha256", "record_sha256"):
            require_sha256(getattr(self, name), name)
        for name in ("subject_id", "cohort", "stage", "judgment_id", "attempt_id"):
            require_identifier(getattr(self, name), name)
        allowed = {"blind_unspecified", "blind_specified"} if self.cohort == "C" else {"blind_proposal"}
        if self.cohort not in _FIRST_STAGE or self.stage not in allowed:
            raise ValueError("blind receipt cohort or stage is invalid")
        if type(self.returned) is not bool:
            raise TypeError("blind receipt returned flag must be bool")
        _utc(self.submitted_utc, "submitted_utc")


class _PrivateRequestGuard:
    __slots__ = ()

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("private request context cannot be serialized as a judge view")


class _PrivateStageEvidence:
    """Actual earlier records retained privately for chronology revalidation."""

    __slots__ = ("_blind_passes", "_absent_adjudication")

    def __init__(self, blind_passes: tuple[MachineJudgment, ...],
                 absent_adjudication: MachineJudgment | None) -> None:
        _exact(self, _PrivateStageEvidence, "private stage evidence")
        if type(blind_passes) is not tuple:
            raise TypeError("private blind records must be a tuple")
        if absent_adjudication is not None and type(absent_adjudication) is not MachineJudgment:
            raise TypeError("private absent adjudication must be an exact machine judgment")
        object.__setattr__(self, "_blind_passes", blind_passes)
        object.__setattr__(self, "_absent_adjudication", absent_adjudication)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("private stage evidence is immutable")

    def __repr__(self) -> str:
        return "_PrivateStageEvidence(<private>)"

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("private stage evidence cannot be serialized as a judge view")


@dataclass(frozen=True, slots=True)
class BlindRequest:
    """The shown timestamp is an earliest permitted view time, not proof of delivery."""

    protocol: MachineProtocol = field(repr=False)
    protocol_sha256: str
    data_scope: str
    authorization: RegisteredUse | None
    judge_code: str
    cohort: str
    stage: str
    material: BlindNotice | BlindRoleSet
    material_sha256: str
    attempt_id: str
    condition_block: str | None
    shown_utc: datetime
    sources: tuple[MachineJudgment, ...] = field(repr=False)
    blind_receipts: tuple[BlindReceipt, ...] = field(repr=False)
    _private_evidence: _PrivateStageEvidence = field(repr=False)
    sources_sha256: str = field(repr=False)
    _visible_json: str = field(repr=False)
    input_sha256: str
    _private_guard: _PrivateRequestGuard = field(default_factory=_PrivateRequestGuard, init=False, repr=False)

    @property
    def subject_id(self) -> str:
        _exact(self, BlindRequest, "request")
        if type(self.material) is BlindRoleSet:
            BlindRoleSet.__post_init__(self.material)
            return self.material.group_id
        _exact(self.material, BlindNotice, "request material")
        BlindNotice.__post_init__(self.material)
        return self.material.item_id

    @property
    def visible_json(self) -> str:
        """Revalidate the serialized judge-facing view before exposing it."""
        _exact(self, BlindRequest, "request")
        _check_request(self.protocol, self)
        _utf8(self._visible_json, "visible_json")
        _refuse_at_sign(self._visible_json)
        if _sha256(self._visible_json) != self.input_sha256:
            raise ValueError("visible payload identity mismatch")
        decoded = json.loads(self._visible_json)
        _refuse_at_sign(decoded)
        if self.cohort == "R":
            _refuse_private_role_material(self.material.blinding, decoded)
        return self._visible_json

    @property
    def payload(self) -> dict[str, object]:
        """Return only the allowlisted judge-facing view, detached from the record."""
        return json.loads(BlindRequest.visible_json.__get__(self))


@dataclass(frozen=True, slots=True)
class RawAnswer:
    kind: str
    content: str | None
    finish_reason: str | None
    reason: str | None

    def __post_init__(self) -> None:
        _exact(self, RawAnswer, "raw answer")
        _exact(self.kind, str, "answer kind")
        if self.kind == "returned":
            if type(self.content) is not str or self.reason is not None:
                raise ValueError("returned answers need text and no unavailable reason")
            if self.finish_reason is not None and type(self.finish_reason) is not str:
                raise TypeError("finish_reason must be text or None")
        elif self.kind in {"unavailable", "cap_blocked"}:
            if self.content is not None or self.finish_reason is not None:
                raise ValueError("unavailable answers cannot contain returned text")
            require_identifier(self.reason, "unavailable reason")
        else:
            raise ValueError("unknown answer kind")

    @property
    def content_sha256(self) -> str | None:
        """Hash UTF-8 encoded text only; this is never a transport-byte hash."""
        RawAnswer.__post_init__(self)
        if self.content is None:
            return None
        try:
            return _sha256(self.content)
        except UnicodeEncodeError:
            return None

    @property
    def content_hash_evidence(self) -> str:
        RawAnswer.__post_init__(self)
        if self.content is None:
            return "no_returned_text"
        return "utf8_text_only_not_transport_bytes" if self.content_sha256 is not None else "invalid_unicode_text_hash_unavailable"


@dataclass(frozen=True, slots=True)
class MachineJudgment:
    judgment_id: str
    request: BlindRequest
    observed_identity: CallIdentity | None
    answer: RawAnswer = field(repr=False)
    status: ParseStatus
    result: MachineReading | MachineRoleReading | NaturalDecision | ConventionDecision | RoleDecision | None = field(repr=False)
    parse_reason: str | None
    submitted_utc: datetime
    evaluated_outputs_seen: bool
    rule_proposals_seen: bool
    sensitivity_seen: bool
    outcomes_seen: bool
    blind_madj_response_seen: bool
    prior_madj_adjudication_seen: bool
    convention_or_specified_preexposed: bool
    other_judgments_seen: bool | None

    def __post_init__(self) -> None:
        _exact(self, MachineJudgment, "judgment")

    @property
    def view_seen(self) -> bool | None:
        """A return indicates a view; a cap stop did not show one; absence is unknown."""
        _exact(self, MachineJudgment, "judgment")
        _exact(self.answer, RawAnswer, "answer")
        RawAnswer.__post_init__(self.answer)
        _exact(self.request, BlindRequest, "request")
        _check_judgment(self.request.protocol, self)
        return True if self.answer.kind == "returned" else False if self.answer.kind == "cap_blocked" else None


def _primitive(value: object, seen: set[int] | None = None, depth: int = 0) -> object:
    """Project exact trusted records to primitives without invoking caller equality."""
    if depth > 40:
        raise ValueError("record nesting exceeds the validation limit")
    kind = type(value)
    if value is None or kind in {str, bool, int}:
        return value
    if kind is datetime:
        _utc(value, "record timestamp")
        return {"datetime": value.isoformat()}
    if kind is date:
        return {"date": value.isoformat()}
    if kind is PrivateRoleBlinding:
        PrivateRoleBlinding._validate(value)
        return {"private_role_blinding": {"key_commitment_sha256": value.key_commitment_sha256,
                                          "seed_commitment_sha256": value.seed_commitment_sha256}}
    if kind is _PrivateRequestGuard:
        return {"private_request_guard": True}
    if kind is _PrivateStageEvidence:
        if seen is None:
            seen = set()
        identity = id(value)
        if identity in seen:
            raise ValueError("record contains a cycle")
        seen.add(identity)
        try:
            nested = _primitive((value._blind_passes, value._absent_adjudication), seen, depth + 1)
            encoded = json.dumps(nested, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            return {"private_stage_evidence_sha256": _sha256(encoded)}
        finally:
            seen.remove(identity)
    enums = (StatementType, Certainty, ParseStatus, DateSupport, Agreement, ReferenceState, MachineValidity)
    if kind in enums:
        return {"enum": kind.__name__, "value": value.value}
    records = (
        Judge, StageBinding, MachineProtocol, BlindNotice, BlindRoleSet, CallIdentity, MachineAlternative,
        MachineReading, MachineDateRole, MachineRoleTarget, MachineRoleChecks, MachineRoleReading,
        NaturalDecision, ConventionDecision, RoleDecision, BlindReceipt, BlindRequest, RawAnswer, MachineJudgment,
        LaterRegistration, RegistrationVerification, RegisteredUse, RoleSeed, RoleVariant,
    )
    if kind is not tuple and kind not in records:
        raise TypeError("record contains an untrusted or unsupported type")
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        raise ValueError("record contains a cycle")
    seen.add(identity)
    try:
        if kind is tuple:
            return [_primitive(item, seen, depth + 1) for item in value]
        return {"record": kind.__name__, "fields": {
            field.name: _primitive(getattr(value, field.name), seen, depth + 1) for field in fields(value)
        }}
    finally:
        seen.remove(identity)


def _record_value(value: object) -> str:
    return json.dumps(_primitive(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _refuse_at_sign(visible: object) -> None:
    for text in _visible_strings(visible):
        if "@" in unicodedata.normalize("NFKC", text):
            raise ValueError("judge-facing payload contains a refused at-sign")


def _evidence(quote: str, notice: str, *, required: bool, target: date | None = None) -> bool | None:
    if type(quote) is not str:
        raise TypeError("quote must be text")
    if quote == "":
        return False if required else None
    if target is None:
        return quote in notice
    literal = target.isoformat()
    offsets = []
    offset = quote.find(literal)
    while offset != -1:
        offsets.append(offset)
        offset = quote.find(literal, offset + 1)
    if not offsets:
        return False
    occurrence = notice.find(quote)
    while occurrence != -1:
        for offset in offsets:
            start = occurrence + offset
            end = start + len(literal)
            if ((start == 0 or not notice[start - 1].isdecimal())
                    and (end == len(notice) or not notice[end].isdecimal())):
                return True
        occurrence = notice.find(quote, occurrence + 1)
    return False


def _optional_date(value: object) -> date | None:
    return None if value is None else iso_date(value)


def _date_support(value: date | None, period_status: str, quote: str, quote_valid: bool | None) -> DateSupport:
    if period_status == "none":
        return DateSupport.NOT_APPLICABLE
    if period_status == "finite" and value is not None and quote_valid is True:
        literal = re.escape(value.isoformat())
        if re.search(rf"(?<![0-9]){literal}(?![0-9])", quote):
            return DateSupport.LITERAL_ISO
    return DateSupport.UNVERIFIED


def _parse_reading(value: object, notice: BlindNotice) -> MachineReading:
    value = _keys(value, {"alternatives", "unresolved_reason"})
    if type(value["alternatives"]) is not list:
        raise TypeError("alternatives must be an array")
    alternatives = []
    for raw in value["alternatives"]:
        raw = _keys(raw, {"statement_type", "period_status", "start", "end", "certainty", "quote"})
        statement = None if raw["statement_type"] is None else StatementType(raw["statement_type"])
        certainty = None if raw["certainty"] is None else Certainty(raw["certainty"])
        start, end = _optional_date(raw["start"]), _optional_date(raw["end"])
        needed = (raw["period_status"] == "finite" or statement not in {None, StatementType.NONE}
                  or certainty not in {None, Certainty.NO_STATEMENT})
        quote_valid = _evidence(raw["quote"], notice.notice_text, required=needed)
        alternatives.append(MachineAlternative(
            statement, raw["period_status"], start, end, certainty, raw["quote"], quote_valid,
            _date_support(start, raw["period_status"], raw["quote"], quote_valid),
            _date_support(end, raw["period_status"], raw["quote"], quote_valid),
        ))
    return MachineReading(tuple(alternatives), value["unresolved_reason"])


def _parse_roles(value: object, material: BlindRoleSet) -> MachineRoleReading:
    value = _keys(value, {"targets", "checks", "material_valid", "reason"})
    if type(value["targets"]) is not list:
        raise TypeError("role targets must be an array")
    raw_checks = _keys(value["checks"], set(_CHECK_NAMES))
    checks = MachineRoleChecks(**raw_checks)
    valid = value["material_valid"]
    if valid is not None and type(valid) is not bool:
        raise TypeError("material_valid must be true, false, or unknown")
    _reason(value["reason"], "role reason")
    if valid is not True and value["reason"] is None:
        raise ValueError("invalid or unknown material requires a reason")
    notices = {notice.item_id: notice for notice in material.notices}
    targets = []
    for raw in value["targets"]:
        raw = _keys(raw, {"variant_id", "status", "target_date", "alternatives", "quote", "date_roles"})
        if type(raw["variant_id"]) is not str or raw["variant_id"] not in notices:
            raise ValueError("role target is not an assigned opaque variant")
        if raw["status"] not in {"exact", "none", "unresolved"}:
            raise ValueError("unknown role-target status")
        target = _optional_date(raw["target_date"])
        if (raw["status"] == "exact") != (target is not None):
            raise ValueError("an exact target requires one date; other statuses require null")
        if type(raw["alternatives"]) is not list or type(raw["date_roles"]) is not list:
            raise TypeError("role alternatives and date roles must be arrays")
        alternatives = tuple(iso_date(item) for item in raw["alternatives"])
        if len(set(alternatives)) != len(alternatives):
            raise ValueError("role alternatives must be distinct")
        notice = notices[raw["variant_id"]].notice_text
        roles = []
        for role in raw["date_roles"]:
            role = _keys(role, {"role", "date", "quote"})
            if role["role"] is not None and role["role"] not in _ROLE_NAMES:
                raise ValueError("unknown date-role label")
            role_date = _optional_date(role["date"])
            roles.append(MachineDateRole(
                role["role"], role_date, role["quote"],
                _evidence(role["quote"], notice, required=role_date is not None, target=role_date),
            ))
        targets.append(MachineRoleTarget(
            raw["variant_id"], raw["status"], target, alternatives, raw["quote"],
            _evidence(raw["quote"], notice, required=target is not None, target=target), tuple(roles),
        ))
    ids = [target.variant_id for target in targets]
    if len(ids) != 4 or len(set(ids)) != 4 or set(ids) != set(notices):
        raise ValueError("each role judgment must cover all four variants exactly once")
    return MachineRoleReading(tuple(targets), checks, valid, value["reason"])


def _parse_answer(request: BlindRequest, answer: RawAnswer) -> tuple[ParseStatus, object | None, str | None]:
    if answer.kind == "unavailable":
        return ParseStatus.UNAVAILABLE, None, answer.reason
    if answer.kind == "cap_blocked":
        return ParseStatus.CAP_BLOCKED, None, answer.reason
    if answer.finish_reason == "length":
        return ParseStatus.TRUNCATED, None, "output_token_ceiling"
    if answer.finish_reason != "stop":
        return ParseStatus.INVALID_SCHEMA, None, "unsupported_or_missing_finish_reason"
    try:
        raw = _json(answer.content)
        # Reject unpaired surrogates and finite-looking numbers that decode as infinity.
        _canonical(raw).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError):
        return ParseStatus.INVALID_JSON, None, "invalid_json"
    try:
        if request.stage not in {"adjudication", "adjudication_absent", "adjudication_specified"}:
            result = (_parse_roles(raw, request.material) if request.cohort == "R"
                      else _parse_reading(raw, request.material))
        elif request.cohort == "C" and request.stage == "adjudication":
            raw = _keys(raw, {"defensible", "specified", "rationale"})
            require_identifier(raw["rationale"], "rationale")
            result = ConventionDecision(_parse_reading(raw["defensible"], request.material),
                                        _parse_reading(raw["specified"], request.material), raw["rationale"])
        else:
            raw = _keys(raw, {"reference", "rationale"})
            require_identifier(raw["rationale"], "rationale")
            result = (RoleDecision(_parse_roles(raw["reference"], request.material), raw["rationale"])
                      if request.cohort == "R" else
                      NaturalDecision(_parse_reading(raw["reference"], request.material), raw["rationale"]))
    except (TypeError, ValueError, KeyError, RecursionError):
        return ParseStatus.INVALID_SCHEMA, None, "invalid_schema"
    return ParseStatus.VALID, result, None


def _reading_view(reading: MachineReading) -> dict[str, object]:
    return {
        "alternatives": [{
            "statement_type": None if item.statement_type is None else item.statement_type.value,
            "period_status": item.period_status,
            "start": None if item.start is None else item.start.isoformat(),
            "end": None if item.end is None else item.end.isoformat(),
            "certainty": None if item.certainty is None else item.certainty.value,
            "quote": item.quote, "quote_valid": item.quote_valid,
            "start_support": item.start_support.value, "end_support": item.end_support.value,
        } for item in reading.alternatives],
        "unresolved_status": "reported" if reading.unresolved_reason is not None else "not_reported",
    }


def _roles_view(reading: MachineRoleReading) -> dict[str, object]:
    return {
        "targets": [{
            "variant_id": item.variant_id, "status": item.status,
            "target_date": None if item.target_date is None else item.target_date.isoformat(),
            "alternatives": [value.isoformat() for value in item.alternatives],
            "quote": item.quote, "quote_valid": item.quote_valid,
            "date_roles": [{"role": role.role, "date": None if role.date is None else role.date.isoformat(),
                            "quote": role.quote, "quote_valid": role.quote_valid} for role in item.date_roles],
        } for item in reading.targets],
        "checks": asdict(reading.checks), "material_valid": reading.material_valid,
        "reason_status": "reported" if reading.reason is not None else "not_reported",
    }


def _require_forwardable_quote(quote: str, verdict: bool | None) -> None:
    _refuse_at_sign(quote)
    if verdict is False:
        raise ValueError("invalid source quotes cannot be forwarded")
    normalized = unicodedata.normalize("NFKC", quote).casefold()
    if re.search(r"(?:[\[<{]\s*(?:redacted|removed|masked|omitted)\s*[\]>}]|█{2,}|\*{3,})", normalized):
        raise ValueError("redacted source quotes cannot be forwarded")


def _source_view(judgment: MachineJudgment) -> dict[str, object]:
    value: dict[str, object] = {"judge_code": judgment.request.judge_code, "status": judgment.status.value}
    if type(judgment.result) is MachineReading:
        for item in judgment.result.alternatives:
            _require_forwardable_quote(item.quote, item.quote_valid)
        value["reading"] = _reading_view(judgment.result)
    elif type(judgment.result) is MachineRoleReading:
        for item in judgment.result.targets:
            _require_forwardable_quote(item.quote, item.quote_valid)
            for role in item.date_roles:
                _require_forwardable_quote(role.quote, role.quote_valid)
        value["reading"] = _roles_view(judgment.result)
    return value


def _material_value(material: BlindNotice | BlindRoleSet) -> dict[str, object]:
    if type(material) is BlindNotice:
        BlindNotice.__post_init__(material)
        return {"kind": "notice", "item_id": material.item_id, **material.visible()}
    _exact(material, BlindRoleSet, "material")
    BlindRoleSet.__post_init__(material)
    return {"kind": "role_group", "group_id": material.group_id,
            "alias_key_commitment_sha256": material.blinding.key_commitment_sha256,
            "private_seed_commitment_sha256": material.blinding.seed_commitment_sha256, **material.visible()}


def _material_sha256(material: BlindNotice | BlindRoleSet) -> str:
    return _sha256(_canonical(_material_value(material)))


def _pass_set(
    protocol: MachineProtocol, material: BlindNotice | BlindRoleSet, cohort: str, stage: str,
    passes: Iterable[MachineJudgment], *, require_two: bool = False,
) -> tuple[MachineJudgment, ...]:
    if type(passes) not in {tuple, list}:
        raise TypeError("machine passes must be a tuple or list")
    passes = tuple(passes)
    if len(passes) > 2 or (require_two and len(passes) != 2):
        raise ValueError("exactly two machine passes are required" if require_two else "at most two machine passes are permitted")
    for item in passes:
        _exact(item, MachineJudgment, "machine pass")
        _check_judgment(protocol, item)
        if (item.request.protocol_sha256 != protocol.sha256
                or _record_value(item.request.material) != _record_value(material)
                or item.request.cohort != cohort or item.request.stage != stage
                or item.request.judge_code not in {"M1", "M2"}):
            raise ValueError("pass identities, materials, or stages do not match")
    codes = [item.request.judge_code for item in passes]
    if len(set(codes)) != len(codes):
        raise ValueError("machine passes must use distinct M1 and M2 codes")
    if len({item.judgment_id for item in passes}) != len(passes):
        raise ValueError("judgment IDs must be distinct")
    if len({item.request.attempt_id for item in passes}) != len(passes):
        raise ValueError("attempt IDs must be distinct within the record")
    return tuple(sorted(passes, key=lambda item: item.request.judge_code))


def _source_views(passes: tuple[MachineJudgment, ...]) -> list[dict[str, object]]:
    by_code = {item.request.judge_code: item for item in passes}
    return [_source_view(by_code[code]) if code in by_code else {"judge_code": code, "status": "missing"}
            for code in ("M1", "M2")]


def _record_subset(present: tuple[MachineJudgment, ...], original: tuple[MachineJudgment, ...]) -> bool:
    by_stage = {(item.request.judge_code, item.request.stage): _record_value(item) for item in original}
    return all(by_stage.get((item.request.judge_code, item.request.stage)) == _record_value(item) for item in present)


def _blind_pass_set(protocol: MachineProtocol, material: BlindNotice | BlindRoleSet, cohort: str,
                    passes: Iterable[MachineJudgment]) -> tuple[MachineJudgment, ...]:
    if type(passes) not in {tuple, list}:
        raise TypeError("blind proposals must be a tuple or list")
    passes = tuple(passes)
    allowed = {"blind_unspecified", "blind_specified"} if cohort == "C" else {"blind_proposal"}
    if len(passes) > len(allowed):
        raise ValueError("too many MADJ blind proposals")
    for item in passes:
        _exact(item, MachineJudgment, "blind proposal")
        _check_judgment(protocol, item)
        if (item.request.judge_code != "MADJ" or item.request.cohort != cohort
                or item.request.stage not in allowed
                or _record_value(item.request.material) != _record_value(material)):
            raise ValueError("blind proposal identity, material, or stage mismatch")
    stages = [item.request.stage for item in passes]
    if len(set(stages)) != len(stages):
        raise ValueError("each MADJ blind stage needs a distinct proposal")
    if len({item.judgment_id for item in passes}) != len(passes) or len(
        {item.request.attempt_id for item in passes}
    ) != len(passes):
        raise ValueError("blind judgment and attempt identities must be distinct")
    return tuple(sorted(passes, key=lambda item: (item.request.stage != "blind_unspecified", item.request.stage)))


def _blind_receipt(protocol: MachineProtocol, item: MachineJudgment) -> BlindReceipt:
    _check_judgment(protocol, item)
    return BlindReceipt(protocol.sha256, item.request.material_sha256, item.request.subject_id,
                        item.request.cohort, item.request.stage, item.judgment_id, item.request.attempt_id,
                        item.answer.kind == "returned", item.submitted_utc, _sha256(_record_value(item)))


def _receipt_set(protocol: MachineProtocol, material: BlindNotice | BlindRoleSet, cohort: str,
                 receipts: Iterable[BlindReceipt]) -> tuple[BlindReceipt, ...]:
    if type(receipts) not in {tuple, list}:
        raise TypeError("blind receipts must be a tuple or list")
    receipts = tuple(receipts)
    allowed = {"blind_unspecified", "blind_specified"} if cohort == "C" else {"blind_proposal"}
    if len(receipts) > len(allowed):
        raise ValueError("too many blind receipts")
    subject = material.group_id if type(material) is BlindRoleSet else material.item_id
    for receipt in receipts:
        _exact(receipt, BlindReceipt, "blind receipt")
        BlindReceipt.__post_init__(receipt)
        if (receipt.protocol_sha256 != protocol.sha256 or receipt.material_sha256 != _material_sha256(material)
                or receipt.subject_id != subject or receipt.cohort != cohort or receipt.stage not in allowed):
            raise ValueError("blind receipt identity, material, or stage mismatch")
    if (len({receipt.stage for receipt in receipts}) != len(receipts)
            or len({receipt.judgment_id for receipt in receipts}) != len(receipts)
            or len({receipt.attempt_id for receipt in receipts}) != len(receipts)):
        raise ValueError("blind receipt stages and identities must be distinct")
    return tuple(sorted(receipts, key=lambda item: (item.stage != "blind_unspecified", item.stage)))


def _validate_absent_adjudication(protocol: MachineProtocol, material: BlindNotice,
                                  adjudication: MachineJudgment | None) -> MachineJudgment:
    if adjudication is None:
        raise ValueError("an actual completed absent adjudication is required")
    _exact(adjudication, MachineJudgment, "absent adjudication")
    _check_judgment(protocol, adjudication)
    if (adjudication.request.judge_code != "MADJ" or adjudication.request.cohort != "C"
            or adjudication.request.stage != "adjudication_absent"
            or _record_value(adjudication.request.material) != _record_value(material)):
        raise ValueError("absent adjudication identity or material mismatch")
    if adjudication.answer.kind != "returned" or adjudication.status is not ParseStatus.VALID:
        raise ValueError("a valid returned absent adjudication is required before specified views")
    return adjudication


def prepare_request(
    protocol: MachineProtocol, material: BlindNotice | BlindRoleSet, *, judge_code: str,
    cohort: str, stage: str, shown_utc: datetime, attempt_id: str, condition_block: str | None = None,
    authorization: RegisteredUse | None = None,
    first_passes: Iterable[MachineJudgment] = (), specified_passes: Iterable[MachineJudgment] = (),
    blind_passes: Iterable[MachineJudgment] = (), blind_receipts: Iterable[BlindReceipt] = (),
    absent_adjudication: MachineJudgment | None = None,
) -> BlindRequest:
    """Build an in-memory allowlisted view, never a transport or an evaluation."""
    _exact(protocol, MachineProtocol, "protocol")
    MachineProtocol.__post_init__(protocol)
    require_identifier(attempt_id, "attempt_id")
    for value, name in ((judge_code, "judge_code"), (cohort, "cohort"), (stage, "stage")):
        _exact(value, str, name)
    binding = protocol.binding(judge_code, cohort, stage)
    protocol.judge(judge_code)
    _utc(shown_utc, "shown_utc")
    if protocol.data_scope != "synthetic":
        raise ValueError("real use is disabled pending separate registration and external review")
    if authorization is not None:
        raise ValueError("synthetic requests cannot use a real-data registration")
    if (cohort == "R" and type(material) is not BlindRoleSet) or (
        cohort in {"N", "C"} and type(material) is not BlindNotice
    ):
        raise TypeError("material does not match the cohort")
    _material_value(material)
    if cohort == "R" and protocol.role_alias_commitment_sha256 != material.blinding.key_commitment_sha256:
        raise ValueError("role HMAC key commitment does not match the protocol")
    if cohort == "R" and material.blinding.seed_commitment_sha256 not in protocol.role_seed_commitments:
        raise ValueError("role seed commitment is absent from the claimed protocol manifest")
    if binding.condition_sha256 is None:
        if condition_block is not None:
            raise ValueError("this stage must not see a convention block")
    else:
        _utf8(condition_block, "condition_block")
        if not condition_block or _sha256(condition_block) != binding.condition_sha256:
            raise ValueError("convention block does not match its pinned hash")
    if any(type(items) not in {tuple, list} for items in (first_passes, specified_passes, blind_passes, blind_receipts)):
        raise TypeError("pass collections must be tuples or lists")
    first, specified = tuple(first_passes), tuple(specified_passes)
    if blind_receipts:
        _receipt_set(protocol, material, cohort, blind_receipts)
        raise ValueError("actual prior blind submissions are required; receipts cannot authorize views")
    if protocol.protocol_design == LEGACY_PROTOCOL and (blind_passes or absent_adjudication is not None):
        raise ValueError("legacy draft cannot use MADJ blind proposals")
    blinds = _blind_pass_set(protocol, material, cohort, blind_passes) if blind_passes else ()
    receipts = _receipt_set(protocol, material, cohort, tuple(_blind_receipt(protocol, item) for item in blinds))
    sources: tuple[MachineJudgment, ...] = ()
    visible: dict[str, object] = material.visible()
    selected = protocol.protocol_design == SELECTED_PROTOCOL
    exposed = judge_code == "MADJ" and stage in {"adjudication", "adjudication_absent", "adjudication_specified"}
    blind_first = next((item for item in blinds if item.request.stage in {"blind_proposal", "blind_unspecified"}), None)
    blind_second = next((item for item in blinds if item.request.stage == "blind_specified"), None)
    if selected and exposed:
        required = "blind_specified" if stage == "adjudication_specified" else (
            "blind_unspecified" if cohort == "C" else "blind_proposal"
        )
        relevant = next((item for item in blinds if item.request.stage == required), None)
        if relevant is None or relevant.answer.kind != "returned":
            raise ValueError("an actual prior returned blind submission is required before exposure")
        if any(item.submitted_utc >= shown_utc for item in blinds):
            raise ValueError("blind submissions must precede the exposed view")
    if exposed:
        first = _pass_set(protocol, material, cohort, _FIRST_STAGE[cohort], first)
        if cohort == "C":
            specified = _pass_set(protocol, material, cohort, "specified", specified)
            if selected and stage == "adjudication_absent":
                if specified or absent_adjudication is not None or len(blinds) != 1 or blind_first is None:
                    raise ValueError("absent adjudication cannot receive specified or prior adjudication records")
            elif selected and stage == "adjudication_specified":
                absent = _validate_absent_adjudication(protocol, material, absent_adjudication)
                if blind_first is None or blind_second is None or len(blinds) != 2:
                    raise ValueError("specified adjudication requires both actual blind submissions")
                if not _record_subset(first, absent.request.sources):
                    raise ValueError("specified adjudication first-pass identities mismatch")
                if _record_value(absent.request._private_evidence._blind_passes) != _record_value((blind_first,)):
                    raise ValueError("specified adjudication must use the original blind first submission")
                if any(_record_value(item.request._private_evidence._absent_adjudication) != _record_value(absent)
                       for item in (*specified, blind_second)):
                    raise ValueError("specified records must follow the same absent adjudication")
                if any(_record_value(item.request._private_evidence._blind_passes) != _record_value((blind_first,))
                       for item in (*specified, blind_second)):
                    raise ValueError("specified records must follow the same blind first submission")
                if any(not _record_subset(first, item.request.sources) for item in (*specified, blind_second)):
                    raise ValueError("specified records must follow the same first-pass identities")
                if absent.submitted_utc >= shown_utc:
                    raise ValueError("specified adjudication must follow the absent adjudication")
            else:
                if any(_record_value(item.request.sources) != _record_value(first) for item in specified):
                    raise ValueError("specified passes must follow these exact first passes")
        elif specified:
            raise ValueError("specified passes are only defined for C")
        elif absent_adjudication is not None:
            raise ValueError("absent adjudication applies only to C specified stages")
        sources = (specified if selected and stage == "adjudication_specified" else
                   first if selected and stage == "adjudication_absent" else (*first, *specified))
        if len({item.judgment_id for item in sources}) != len(sources):
            raise ValueError("all source judgment IDs must be distinct")
        submitted_times = [item.submitted_utc for item in sources] + [item.submitted_utc for item in receipts]
        if submitted_times and shown_utc <= max(submitted_times):
            raise ValueError("adjudication must follow all source submissions")
        if selected and stage == "adjudication_specified":
            visible = {"material": material.visible(), "specified_passes": _source_views(specified),
                       "condition_block": condition_block}
        else:
            visible = {"material": material.visible(), "first_passes": _source_views(first)}
        if cohort == "C" and not selected:
            visible["specified_passes"] = _source_views(specified)
            visible["condition_block"] = condition_block
    elif cohort == "C" and stage in {"specified", "blind_specified"}:
        first = _pass_set(protocol, material, cohort, "unspecified", first, require_two=True)
        if specified:
            raise ValueError("specified passes cannot be sources for another specified pass")
        if any(item.answer.kind != "returned" for item in first):
            raise ValueError("both first passes must be submitted before the convention is shown")
        if selected:
            if len(blinds) != 1 or blind_first is None or blind_first.answer.kind != "returned":
                raise ValueError("the convention requires all three actual blind first submissions")
            absent = _validate_absent_adjudication(protocol, material, absent_adjudication)
            if _record_value(absent.request.sources) != _record_value(first):
                raise ValueError("specified views must follow the absent adjudication first passes")
            if _record_value(absent.request._private_evidence._blind_passes) != _record_value((blind_first,)):
                raise ValueError("specified views must follow the absent adjudication blind submission")
            if absent.submitted_utc >= shown_utc:
                raise ValueError("specified views must follow the completed absent adjudication")
        submitted_times = [item.submitted_utc for item in first] + [item.submitted_utc for item in receipts]
        if shown_utc <= max(submitted_times):
            raise ValueError("the convention must follow all first-pass submissions")
        sources = first
        visible = {**visible, "condition_block": condition_block}
    elif first or specified or receipts or absent_adjudication is not None:
        raise ValueError("first-pass views cannot contain other judgments")
    identity_sources = (absent_adjudication.request.sources + specified
                        if selected and stage == "adjudication_specified" else sources)
    attempt_ids = [item.request.attempt_id for item in identity_sources] + [item.attempt_id for item in receipts]
    if absent_adjudication is not None:
        attempt_ids.append(absent_adjudication.request.attempt_id)
    if len(set(attempt_ids)) != len(attempt_ids) or attempt_id in attempt_ids:
        raise ValueError("attempt IDs must be distinct within the record")
    judgment_ids = [item.judgment_id for item in identity_sources] + [item.judgment_id for item in receipts]
    if absent_adjudication is not None:
        judgment_ids.append(absent_adjudication.judgment_id)
    if len(set(judgment_ids)) != len(judgment_ids):
        raise ValueError("source judgment IDs must be distinct within the record")
    if cohort == "R":
        _refuse_private_role_material(material.blinding, visible)
    _refuse_at_sign(visible)
    visible_json = _canonical(visible)
    _refuse_at_sign(visible_json)
    evidence = _PrivateStageEvidence(blinds, absent_adjudication)
    return BlindRequest(protocol, protocol.sha256, protocol.data_scope, authorization, judge_code, cohort, stage,
                        material, _material_sha256(material), attempt_id, condition_block, shown_utc, sources,
                        receipts, evidence, _sha256(_record_value((sources, receipts, evidence))),
                        visible_json, _sha256(visible_json))


def assigned_identity(protocol: MachineProtocol, request: BlindRequest) -> CallIdentity:
    """The assigned identity is not evidence of what a provider actually served."""
    _check_request(protocol, request)
    return _assigned_identity(protocol, request)


def _assigned_identity(protocol: MachineProtocol, request: BlindRequest) -> CallIdentity:
    judge = protocol.judge(request.judge_code)
    binding = protocol.binding(request.judge_code, request.cohort, request.stage)
    return CallIdentity(request.judge_code, request.cohort, request.stage, protocol.sha256,
                        request.subject_id, request.material_sha256, request.attempt_id, request.sources_sha256,
                        judge.model_id,
                        judge.model_revision, judge.provider_route, judge.precision,
                        binding.template_id, binding.template_sha256,
                        binding.decoding_sha256, binding.schema_sha256, binding.parser_sha256, request.input_sha256)


def _check_request(protocol: MachineProtocol, request: BlindRequest) -> None:
    _exact(protocol, MachineProtocol, "protocol")
    MachineProtocol.__post_init__(protocol)
    _exact(request, BlindRequest, "request")
    original = _record_value(request)
    _exact(request.protocol, MachineProtocol, "request protocol")
    MachineProtocol.__post_init__(request.protocol)
    if _record_value(protocol) != _record_value(request.protocol):
        raise ValueError("request protocol identity mismatch")
    _exact(request.cohort, str, "cohort")
    if request.cohort not in _FIRST_STAGE:
        raise ValueError("unknown request cohort")
    if type(request.sources) is not tuple or any(type(item) is not MachineJudgment for item in request.sources):
        raise TypeError("request sources must be exact machine judgments")
    if type(request.blind_receipts) is not tuple or any(type(item) is not BlindReceipt for item in request.blind_receipts):
        raise TypeError("request blind receipts must be exact private receipts")
    _exact(request._private_evidence, _PrivateStageEvidence, "private stage evidence")
    if (type(request._private_evidence._blind_passes) is not tuple
            or (request._private_evidence._absent_adjudication is not None
                and type(request._private_evidence._absent_adjudication) is not MachineJudgment)):
        raise TypeError("private stage evidence has invalid record types")
    for item in request.sources:
        _exact(item.request, BlindRequest, "source request")
    first = tuple(item for item in request.sources if item.request.stage == _FIRST_STAGE[request.cohort])
    specified = tuple(item for item in request.sources if item.request.stage == "specified")
    rebuilt = prepare_request(protocol, request.material, judge_code=request.judge_code, cohort=request.cohort,
                              stage=request.stage, shown_utc=request.shown_utc,
                              attempt_id=request.attempt_id, condition_block=request.condition_block,
                              authorization=request.authorization,
                              first_passes=first,
                              specified_passes=specified, blind_passes=request._private_evidence._blind_passes,
                              absent_adjudication=request._private_evidence._absent_adjudication)
    if _record_value(rebuilt) != original:
        raise ValueError("blinded request or its source identity was altered")


def ingest_judgment(
    protocol: MachineProtocol, request: BlindRequest, *, judgment_id: str, answer: RawAnswer,
    observed_identity: CallIdentity | None, submitted_utc: datetime, evaluated_outputs_seen: bool,
    rule_proposals_seen: bool, sensitivity_seen: bool, outcomes_seen: bool, blind_madj_response_seen: bool,
    prior_madj_adjudication_seen: bool, convention_or_specified_preexposed: bool,
    other_judgments_seen: bool | None,
) -> MachineJudgment:
    """Parse a supplied answer without repair; retain its raw text and failure state."""
    _check_request(protocol, request)
    require_identifier(judgment_id, "judgment_id")
    _exact(answer, RawAnswer, "answer")
    RawAnswer.__post_init__(answer)
    _utc(submitted_utc, "submitted_utc")
    if submitted_utc < request.shown_utc:
        raise ValueError("submission cannot precede the shown view")
    if (any(type(flag) is not bool for flag in (evaluated_outputs_seen, rule_proposals_seen, sensitivity_seen,
                                                outcomes_seen, blind_madj_response_seen, prior_madj_adjudication_seen,
                                                convention_or_specified_preexposed))
            or (other_judgments_seen is not None and type(other_judgments_seen) is not bool)):
        raise TypeError("exposure attestations must be booleans, except unknown other-judgment exposure")
    if (evaluated_outputs_seen or rule_proposals_seen or sensitivity_seen or outcomes_seen
            or blind_madj_response_seen or prior_madj_adjudication_seen or convention_or_specified_preexposed):
        raise ValueError("machine judgments must be blind to outputs, rules, sensitivity, outcomes, prior MADJ responses, and out-of-order C exposure")
    expected_other_exposure = (None if answer.kind == "unavailable" else False if answer.kind == "cap_blocked"
                               else request.judge_code == "MADJ" and request.stage in {
                                   "adjudication", "adjudication_absent", "adjudication_specified",
                               } and bool(request.sources))
    if other_judgments_seen is not expected_other_exposure:
        raise ValueError("other machine-judgment exposure must match the observed availability and stage")
    if answer.kind == "returned":
        if type(observed_identity) is not CallIdentity:
            raise ValueError("observed model, route, template, parser, or input identity mismatch")
        CallIdentity.__post_init__(observed_identity)
        if _record_value(observed_identity) != _record_value(_assigned_identity(protocol, request)):
            raise ValueError("observed model, route, template, parser, or input identity mismatch")
    elif observed_identity is not None:
        raise ValueError("unavailable answers cannot assert an observed served identity")
    status, result, reason = _parse_answer(request, answer)
    return MachineJudgment(judgment_id, request, observed_identity, answer, status, result, reason,
                           submitted_utc, evaluated_outputs_seen, rule_proposals_seen, sensitivity_seen,
                           outcomes_seen, blind_madj_response_seen, prior_madj_adjudication_seen,
                           convention_or_specified_preexposed, other_judgments_seen)


def _check_judgment(protocol: MachineProtocol, judgment: MachineJudgment) -> None:
    _exact(judgment, MachineJudgment, "judgment")
    original = _record_value(judgment)
    rebuilt = ingest_judgment(protocol, judgment.request, judgment_id=judgment.judgment_id,
                              answer=judgment.answer, observed_identity=judgment.observed_identity,
                              submitted_utc=judgment.submitted_utc,
                              evaluated_outputs_seen=judgment.evaluated_outputs_seen,
                              rule_proposals_seen=judgment.rule_proposals_seen,
                              sensitivity_seen=judgment.sensitivity_seen,
                              outcomes_seen=judgment.outcomes_seen,
                              blind_madj_response_seen=judgment.blind_madj_response_seen,
                              prior_madj_adjudication_seen=judgment.prior_madj_adjudication_seen,
                              convention_or_specified_preexposed=judgment.convention_or_specified_preexposed,
                              other_judgments_seen=judgment.other_judgments_seen)
    if _record_value(rebuilt) != original:
        raise ValueError("parsed judgment was altered")


class Agreement(str, Enum):
    AGREED = "machine_agreed"
    DISAGREED = "machine_disagreed"
    UNKNOWN = "machine_agreement_unknown"


class ReferenceState(str, Enum):
    ADJUDICATED = "machine_adjudicated"
    PARTIAL = "machine_partially_resolved"
    UNRESOLVED = "machine_unresolved"


class MachineValidity(str, Enum):
    VALID = "machine_valid_adjudicated"
    INVALID = "machine_invalid_adjudicated"
    UNRESOLVED = "machine_validity_unresolved"


def _reading_incomplete(reading: MachineReading) -> bool:
    return _reading_unresolved_reason(reading) is not None


def _reading_semantic_key(reading: MachineReading) -> frozenset[tuple[object, ...]]:
    return frozenset((item.statement_type, item.period_status, item.start, item.end, item.certainty)
                     for item in reading.alternatives)


def _reading_semantic_unknown(reading: MachineReading) -> bool:
    return reading.unresolved_reason is not None or any(
        item.statement_type is None or item.certainty is None or item.period_status == "unresolved"
        or (item.period_status == "finite" and (item.start is None or item.end is None))
        for item in reading.alternatives
    )


def _reading_unresolved_reason(reading: MachineReading) -> str | None:
    if _reading_semantic_unknown(reading):
        return "unresolved"
    if any(item.quote_valid is False for item in reading.alternatives):
        return "invalid_quote"
    if any(item.period_status == "finite" and (
        item.start_support is not DateSupport.LITERAL_ISO or item.end_support is not DateSupport.LITERAL_ISO
    ) for item in reading.alternatives):
        return "date_support_unverified"
    return None


def _reading_agreement(passes: tuple[MachineJudgment, ...]) -> Agreement:
    if len(passes) != 2 or any(item.status is not ParseStatus.VALID or type(item.result) is not MachineReading
                               or _reading_semantic_unknown(item.result) for item in passes):
        return Agreement.UNKNOWN
    left, right = (_reading_semantic_key(item.result) for item in passes)
    return Agreement.AGREED if left == right else Agreement.DISAGREED


def _reading_quote_agreement(passes: tuple[MachineJudgment, ...]) -> Agreement:
    if _reading_agreement(passes) is not Agreement.AGREED:
        return Agreement.UNKNOWN
    values = [frozenset(((item.statement_type, item.period_status, item.start, item.end, item.certainty), item.quote)
                        for item in entry.result.alternatives) for entry in passes]
    return Agreement.AGREED if values[0] == values[1] else Agreement.DISAGREED


@dataclass(frozen=True, slots=True)
class MachineProvenance:
    protocol_sha256: str
    material_sha256: str
    records_sha256: str
    cohort: str
    subject_id: str
    reference_version: str
    protocol_design: str
    candidate_track: str
    judgment_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    label: str = field(default="machine_generated_not_human", init=False)
    use_status: str = field(default="synthetic_claim_only_not_authorized", init=False)

    def __post_init__(self) -> None:
        _exact(self, MachineProvenance, "machine provenance")
        if type(self.label) is not str or self.label != "machine_generated_not_human":
            raise ValueError("machine provenance label cannot be changed")
        if type(self.use_status) is not str or self.use_status != "synthetic_claim_only_not_authorized":
            raise ValueError("machine provenance use status cannot be changed")
        require_sha256(self.protocol_sha256, "protocol_sha256")
        require_sha256(self.material_sha256, "material_sha256")
        require_sha256(self.records_sha256, "records_sha256")
        for name in ("cohort", "subject_id", "reference_version", "protocol_design", "candidate_track"):
            require_identifier(getattr(self, name), name)
        expected_track = ("selected_four_stage_separate_c_synthetic_only" if self.protocol_design == SELECTED_PROTOCOL else
                          "legacy_three_stage_diagnostic_not_selected" if self.protocol_design == LEGACY_PROTOCOL else None)
        if self.candidate_track != expected_track:
            raise ValueError("candidate track must match the protocol design")
        for values in (self.judgment_ids, self.attempt_ids):
            if type(values) is not tuple:
                raise TypeError("provenance identities must be tuples")
            for value in values:
                require_identifier(value, "provenance identity")
            if len(set(values)) != len(values):
                raise ValueError("provenance identities must be distinct within the record")
        if len(self.judgment_ids) != len(self.attempt_ids):
            raise ValueError("judgment and attempt provenance must align")

def _provenance(protocol: MachineProtocol, material: BlindNotice | BlindRoleSet, cohort: str,
                first: tuple[MachineJudgment, ...], specified: tuple[MachineJudgment, ...],
                blind_passes: tuple[MachineJudgment, ...], adjudication: MachineJudgment | None,
                specified_adjudication: MachineJudgment | None = None) -> MachineProvenance:
    records = (*first, *specified, *blind_passes, *((adjudication,) if adjudication is not None else ()),
               *((specified_adjudication,) if specified_adjudication is not None else ()))
    subject = material.group_id if type(material) is BlindRoleSet else material.item_id
    track = ("selected_four_stage_separate_c_synthetic_only" if protocol.protocol_design == SELECTED_PROTOCOL else
             "legacy_three_stage_diagnostic_not_selected")
    return MachineProvenance(protocol.sha256, _material_sha256(material), _sha256(_record_value(records)),
                             cohort, subject, protocol.reference_version, protocol.protocol_design, track,
                             tuple(item.judgment_id for item in records),
                             tuple(item.request.attempt_id for item in records))


class MachineEndpoint:
    """A live projection; detached serialized copies are never trusted inputs."""

    __slots__ = ("_parent",)

    def __init__(self, parent: ReconciledReadings) -> None:
        _exact(self, MachineEndpoint, "machine endpoint")
        _exact(parent, ReconciledReadings, "endpoint parent")
        ReconciledReadings._parts(parent)
        object.__setattr__(self, "_parent", parent)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("machine endpoints are immutable projections")

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("use the explicit untrusted projection export")

    def _parts(self) -> dict[str, object]:
        _exact(self, MachineEndpoint, "machine endpoint")
        _exact(self._parent, ReconciledReadings, "endpoint parent")
        return ReconciledReadings._parts(self._parent)

    @property
    def period_status(self) -> str:
        return MachineEndpoint._parts(self)["endpoint_fields"][0]

    @property
    def end(self) -> date | None:
        return MachineEndpoint._parts(self)["endpoint_fields"][1]

    @property
    def unresolved_reason(self) -> str | None:
        return MachineEndpoint._parts(self)["endpoint_fields"][2]

    @property
    def provenance(self) -> MachineProvenance:
        return MachineEndpoint._parts(self)["provenance"]

    @property
    def semantic_truth(self) -> str:
        MachineEndpoint._parts(self)
        return "not_verified"

    @property
    def date_evidence(self) -> str:
        status = MachineEndpoint._parts(self)["endpoint_fields"][0]
        return "literal_iso_cooccurrence_only" if status == "finite" else "not_applicable" if status == "none" else "unverified"

    def export(self) -> dict[str, object]:
        """Export a detached, untrusted machine-labelled snapshot; never an evaluation input."""
        parts = MachineEndpoint._parts(self)
        status, end, reason = parts["endpoint_fields"]
        provenance = parts["provenance"]
        return {"machine_reference_label": "machine_generated_not_human",
                "detached_value_status": "untrusted_detached_serialization", "period_status": status,
                "semantic_truth": "not_verified", "real_use_authorized": False,
                "protocol_design": provenance.protocol_design, "candidate_track": provenance.candidate_track,
                "selected_candidate_resolved": provenance.protocol_design == SELECTED_PROTOCOL and
                                               parts["state"] is ReferenceState.ADJUDICATED,
                "blind_vs_exposed": parts["blind_vs_exposed"].value,
                "date_evidence": "literal_iso_cooccurrence_only" if status == "finite" else
                                 "not_applicable" if status == "none" else "unverified",
                "end": None if end is None else end.isoformat(), "unresolved_reason": reason,
                "provenance": asdict(provenance)}

    def export_json(self) -> str:
        """Serialize a freshly rederived, explicitly untrusted detached snapshot."""
        return _canonical(MachineEndpoint.export(self))


def _endpoint(reading: MachineReading | None, process_complete: bool) -> tuple[str, date | None, str | None]:
    if not process_complete or reading is None:
        return "unresolved", None, "machine_process_incomplete"
    if reading.unresolved_reason is not None:
        return "unresolved", None, reading.unresolved_reason
    if any(item.quote_valid is False for item in reading.alternatives):
        return "unresolved", None, "machine_evidence_unverified"
    if any(item.period_status == "unresolved" or (item.period_status == "finite" and item.end is None)
           for item in reading.alternatives):
        return "unresolved", None, "machine_period_unresolved"
    if any(item.period_status == "finite" and item.end_support is not DateSupport.LITERAL_ISO
           for item in reading.alternatives):
        return "unresolved", None, "machine_end_support_unverified"
    ends = {(item.period_status, item.end) for item in reading.alternatives}
    if len(ends) != 1:
        return "unresolved", None, "machine_endpoint_not_unique"
    status, end = next(iter(ends))
    return status, end, None


class MachineConventionTarget:
    """A live C projection; exported snapshots have no independent authority."""

    __slots__ = ("_parent",)

    def __init__(self, parent: ReconciledReadings) -> None:
        _exact(self, MachineConventionTarget, "machine convention target")
        _exact(parent, ReconciledReadings, "convention parent")
        ReconciledReadings._parts(parent)
        if parent.cohort != "C":
            raise ValueError("only C has a specified convention target")
        object.__setattr__(self, "_parent", parent)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("machine convention targets are immutable projections")

    def __deepcopy__(self, memo: dict) -> None:
        raise TypeError("use the explicit untrusted projection export")

    def _parts(self) -> dict[str, object]:
        _exact(self, MachineConventionTarget, "machine convention target")
        _exact(self._parent, ReconciledReadings, "convention parent")
        parts = ReconciledReadings._parts(self._parent)
        if self._parent.cohort != "C":
            raise ValueError("only C has a specified convention target")
        return parts

    @property
    def statement_type(self) -> StatementType | None:
        return MachineConventionTarget._parts(self)["target_fields"][0]

    @property
    def period_status(self) -> str:
        return MachineConventionTarget._parts(self)["target_fields"][1]

    @property
    def start(self) -> date | None:
        return MachineConventionTarget._parts(self)["target_fields"][2]

    @property
    def end(self) -> date | None:
        return MachineConventionTarget._parts(self)["target_fields"][3]

    @property
    def unresolved_reason(self) -> str | None:
        return MachineConventionTarget._parts(self)["target_fields"][4]

    @property
    def provenance(self) -> MachineProvenance:
        return MachineConventionTarget._parts(self)["provenance"]

    @property
    def semantic_truth(self) -> str:
        MachineConventionTarget._parts(self)
        return "not_verified"

    @property
    def date_evidence(self) -> str:
        status = MachineConventionTarget._parts(self)["target_fields"][1]
        return "literal_iso_cooccurrence_only" if status == "finite" else "not_applicable" if status == "none" else "unverified"

    def export(self) -> dict[str, object]:
        """Export a detached, untrusted machine-labelled snapshot; never an evaluation input."""
        parts = MachineConventionTarget._parts(self)
        statement, status, start, end, reason = parts["target_fields"]
        provenance = parts["provenance"]
        return {"machine_reference_label": "machine_generated_not_human",
                "detached_value_status": "untrusted_detached_serialization",
                "semantic_truth": "not_verified", "real_use_authorized": False,
                "protocol_design": provenance.protocol_design, "candidate_track": provenance.candidate_track,
                "selected_candidate_resolved": provenance.protocol_design == SELECTED_PROTOCOL and
                                               parts["state"] is ReferenceState.ADJUDICATED,
                "blind_vs_exposed": parts["blind_vs_exposed"].value,
                "blind_vs_exposed_first": parts["blind_vs_exposed_first"].value,
                "blind_vs_exposed_specified": parts["blind_vs_exposed_specified"].value,
                "date_evidence": "literal_iso_cooccurrence_only" if status == "finite" else
                                 "not_applicable" if status == "none" else "unverified",
                "statement_type": None if statement is None else statement.value, "period_status": status,
                "start": None if start is None else start.isoformat(), "end": None if end is None else end.isoformat(),
                "unresolved_reason": reason, "provenance": asdict(provenance)}

    def export_json(self) -> str:
        """Serialize a freshly rederived, explicitly untrusted detached snapshot."""
        return _canonical(MachineConventionTarget.export(self))


def _convention_target(reading: MachineReading | None, process_complete: bool) -> tuple[
    StatementType | None, str, date | None, date | None, str | None
]:
    unknown = lambda reason: (None, "unresolved", None, None, reason)
    if not process_complete or reading is None:
        return unknown("machine_process_incomplete")
    if reading.unresolved_reason is not None:
        return unknown(reading.unresolved_reason)
    if any(item.quote_valid is False or item.statement_type is None or item.period_status == "unresolved"
           or (item.period_status == "finite" and (item.start is None or item.end is None
               or item.start_support is not DateSupport.LITERAL_ISO or item.end_support is not DateSupport.LITERAL_ISO))
           for item in reading.alternatives):
        return unknown("machine_specified_fields_unresolved")
    values = {(item.statement_type, item.period_status, item.start, item.end) for item in reading.alternatives}
    if len(values) != 1:
        return unknown("machine_specified_target_not_unique")
    statement, status, start, end = next(iter(values))
    return statement, status, start, end, None


def _sources_and_adjudication(
    protocol: MachineProtocol, material: BlindNotice | BlindRoleSet, cohort: str,
    first_passes: Iterable[MachineJudgment], specified_passes: Iterable[MachineJudgment],
    blind_passes: Iterable[MachineJudgment], adjudication: MachineJudgment | None,
    specified_adjudication: MachineJudgment | None = None,
) -> tuple[tuple[MachineJudgment, ...], tuple[MachineJudgment, ...], tuple[MachineJudgment, ...]]:
    _exact(protocol, MachineProtocol, "protocol")
    MachineProtocol.__post_init__(protocol)
    if protocol.data_scope != "synthetic":
        raise ValueError("real use is disabled pending separate registration and external review")
    _material_value(material)
    first = _pass_set(protocol, material, cohort, _FIRST_STAGE[cohort], first_passes)
    if type(blind_passes) not in {tuple, list}:
        raise TypeError("blind proposals must be a tuple or list")
    if protocol.protocol_design == LEGACY_PROTOCOL and blind_passes:
        raise ValueError("legacy draft cannot use MADJ blind proposals")
    blinds = _blind_pass_set(protocol, material, cohort, blind_passes) if blind_passes else ()
    if cohort == "C":
        specified = _pass_set(protocol, material, cohort, "specified", specified_passes)
        if any((not _record_subset(first, item.request.sources) if protocol.protocol_design == SELECTED_PROTOCOL
                else _record_value(item.request.sources) != _record_value(first)) for item in specified):
            raise ValueError("specified passes do not follow these first passes")
        if protocol.protocol_design == SELECTED_PROTOCOL:
            blind_first = next((item for item in blinds if item.request.stage == "blind_unspecified"), None)
            blind_second = next((item for item in blinds if item.request.stage == "blind_specified"), None)
            if blind_first is not None:
                if any(_record_value(item.request._private_evidence._blind_passes) != _record_value((blind_first,))
                       for item in specified):
                    raise ValueError("specified passes must identify the same blind first submission")
                if (blind_second is not None and
                        _record_value(blind_second.request._private_evidence._blind_passes) != _record_value((blind_first,))):
                    raise ValueError("blind specified proposal must identify the same blind first submission")
            if blind_second is not None and not _record_subset(first, blind_second.request.sources):
                raise ValueError("blind specified proposal must follow these first-pass identities")
            if adjudication is not None:
                for item in (*specified, *((blind_second,) if blind_second is not None else ())):
                    if _record_value(item.request._private_evidence._absent_adjudication) != _record_value(adjudication):
                        raise ValueError("specified records must follow the same absent adjudication")
    else:
        if type(specified_passes) not in {tuple, list} or specified_passes:
            raise ValueError("specified passes are only defined for C")
        specified = ()
    sources = (*first, *specified, *blinds)
    if specified_adjudication is not None and (cohort != "C" or protocol.protocol_design != SELECTED_PROTOCOL):
        raise ValueError("separate specified adjudication belongs only to selected C")
    exposed = (*((adjudication,) if adjudication is not None else ()),
               *((specified_adjudication,) if specified_adjudication is not None else ()))
    for output in exposed:
        _exact(output, MachineJudgment, "adjudication")
        _check_judgment(protocol, output)
    all_records = (*sources, *exposed)
    if len({item.judgment_id for item in all_records}) != len(all_records):
        raise ValueError("all source judgment IDs must be distinct")
    if len({item.request.attempt_id for item in all_records}) != len(all_records):
        raise ValueError("all source attempt IDs must be distinct")
    for output in exposed:
        selected_c = cohort == "C" and protocol.protocol_design == SELECTED_PROTOCOL
        expected_stage = ("adjudication_specified" if output is specified_adjudication else "adjudication_absent") \
            if selected_c else "adjudication"
        exposed_sources = specified if selected_c and output is specified_adjudication else (
            first if selected_c else (*first, *specified)
        )
        if (output.request.judge_code != "MADJ" or output.request.cohort != cohort
                or output.request.stage != expected_stage
                or _record_value(output.request.material) != _record_value(material)
                or (not _record_subset(exposed_sources, output.request.sources)
                    if protocol.protocol_design == SELECTED_PROTOCOL else
                    _record_value(output.request.sources) != _record_value(exposed_sources))):
            raise ValueError("adjudication must identify these exact earlier passes")
        if selected_c and output is specified_adjudication and adjudication is not None:
            if _record_value(output.request._private_evidence._absent_adjudication) != _record_value(adjudication):
                raise ValueError("specified adjudication must follow the same absent adjudication")
        actual_blinds = {item.request.stage: _record_value(item)
                         for item in output.request._private_evidence._blind_passes}
        if any(item.request.stage in actual_blinds and actual_blinds[item.request.stage] != _record_value(item)
               for item in blinds):
            raise ValueError("adjudication must identify the actual prior blind submissions")
    return first, specified, blinds


def _source_reasons(passes: tuple[MachineJudgment, ...], phase: str, cohort: str,
                    material: BlindNotice | BlindRoleSet) -> list[str]:
    by_code = {item.request.judge_code: item for item in passes}
    reasons = []
    for code in ("M1", "M2"):
        item = by_code.get(code)
        if item is None:
            reasons.append(f"machine_{phase}_{code}_missing")
        elif item.status is not ParseStatus.VALID:
            reasons.append(f"machine_{phase}_{code}_{item.status.value}")
        elif cohort == "R" and type(item.result) is MachineRoleReading and item.result.material_valid is False:
            reasons.append(f"machine_{phase}_{code}_material_invalid")
        elif cohort == "R" and _role_source_unresolved(item.result, material):
            reasons.append(f"machine_{phase}_{code}_unresolved")
        elif cohort != "R":
            problem = (_reading_unresolved_reason(item.result) if type(item.result) is MachineReading else "unresolved")
            if problem is not None:
                reasons.append(f"machine_{phase}_{code}_{problem}")
    agreement = _role_agreement(passes) if cohort == "R" else _reading_agreement(passes)
    if agreement is Agreement.DISAGREED:
        reasons.append(f"machine_{phase}_semantic_disagreement")
    return reasons


def _blind_at(passes: tuple[MachineJudgment, ...], stage: str) -> MachineJudgment | None:
    return next((item for item in passes if item.request.stage == stage), None)


def _blind_was_committed(adjudication: MachineJudgment | None, blind: MachineJudgment | None) -> bool:
    return (adjudication is not None and blind is not None
            and any(item.request.stage == blind.request.stage and _record_value(item) == _record_value(blind)
                    for item in adjudication.request._private_evidence._blind_passes))


def _blind_reasons(item: MachineJudgment | None, phase: str, cohort: str,
                   material: BlindNotice | BlindRoleSet) -> list[str]:
    prefix = f"machine_blind_{phase}_MADJ_"
    if item is None:
        return [prefix + "missing"]
    if item.status is not ParseStatus.VALID:
        return [prefix + item.status.value]
    if cohort == "R":
        if type(item.result) is MachineRoleReading and item.result.material_valid is False:
            return [prefix + "material_invalid"]
        return [prefix + "unresolved"] if _role_source_unresolved(item.result, material) else []
    if type(item.result) is not MachineReading:
        return [prefix + "unresolved"]
    reason = _reading_unresolved_reason(item.result)
    return [] if reason is None else [prefix + reason]


def _reading_blind_agreement(blind: MachineJudgment | None, other: MachineReading | None) -> Agreement:
    if (blind is None or blind.status is not ParseStatus.VALID or type(blind.result) is not MachineReading
            or other is None or _reading_incomplete(blind.result) or _reading_incomplete(other)):
        return Agreement.UNKNOWN
    return Agreement.AGREED if _reading_semantic_key(blind.result) == _reading_semantic_key(other) else Agreement.DISAGREED


def _blind_against_readings(blind: MachineJudgment | None, passes: tuple[MachineJudgment, ...]) -> Agreement:
    if _reading_agreement(passes) is not Agreement.AGREED or any(_reading_incomplete(item.result) for item in passes):
        return Agreement.UNKNOWN
    return _reading_blind_agreement(blind, passes[0].result)


def _reading_parts(protocol: MachineProtocol, material: BlindNotice, cohort: str, reference_version: str,
                   first_passes: tuple[MachineJudgment, ...], specified_passes: tuple[MachineJudgment, ...],
                   blind_passes: tuple[MachineJudgment, ...], adjudication: MachineJudgment | None,
                   specified_adjudication: MachineJudgment | None) -> dict[str, object]:
    _exact(material, BlindNotice, "material")
    if type(cohort) is not str or cohort not in {"N", "C"}:
        raise ValueError("N or C requires a blinded notice")
    require_identifier(reference_version, "reference_version")
    _exact(protocol, MachineProtocol, "protocol")
    MachineProtocol.__post_init__(protocol)
    if reference_version != protocol.reference_version:
        raise ValueError("reference_version must match the pinned protocol")
    first, specified, blinds = _sources_and_adjudication(protocol, material, cohort, first_passes,
                                                          specified_passes, blind_passes, adjudication,
                                                          specified_adjudication)
    reasons = _source_reasons(first, "first", cohort, material)
    if cohort == "C":
        reasons.extend(_source_reasons(specified, "specified", cohort, material))
    blind_first = blind_second = None
    blind_first_agreement = blind_second_agreement = Agreement.UNKNOWN
    if protocol.protocol_design == SELECTED_PROTOCOL:
        blind_first = _blind_at(blinds, "blind_unspecified" if cohort == "C" else "blind_proposal")
        reasons.extend(_blind_reasons(blind_first, "first", cohort, material))
        blind_first_agreement = _blind_against_readings(blind_first, first)
        if blind_first_agreement is Agreement.DISAGREED:
            reasons.append("machine_blind_first_semantic_disagreement")
        if cohort == "C":
            blind_second = _blind_at(blinds, "blind_specified")
            reasons.extend(_blind_reasons(blind_second, "specified", cohort, material))
            blind_second_agreement = _blind_against_readings(blind_second, specified)
            if blind_second_agreement is Agreement.DISAGREED:
                reasons.append("machine_blind_specified_semantic_disagreement")
    defensible = specified_reading = None
    selected_c = cohort == "C" and protocol.protocol_design == SELECTED_PROTOCOL
    absent_prefix = "machine_adjudication_absent_" if selected_c else "machine_adjudication_"
    if adjudication is None:
        reasons.append(absent_prefix + "missing")
    elif adjudication.status is not ParseStatus.VALID:
        reasons.append(absent_prefix + adjudication.status.value)
    elif (cohort == "N" or selected_c) and type(adjudication.result) is NaturalDecision:
        defensible = adjudication.result.reference
    elif cohort == "C" and type(adjudication.result) is ConventionDecision:
        defensible, specified_reading = adjudication.result.defensible, adjudication.result.specified
    else:
        raise ValueError("adjudication result does not match the cohort")
    if selected_c:
        if specified_adjudication is None:
            reasons.append("machine_adjudication_specified_missing")
        elif specified_adjudication.status is not ParseStatus.VALID:
            reasons.append(f"machine_adjudication_specified_{specified_adjudication.status.value}")
        elif type(specified_adjudication.result) is NaturalDecision:
            specified_reading = specified_adjudication.result.reference
        else:
            raise ValueError("specified adjudication result does not match C")
    if defensible is not None:
        problem = _reading_unresolved_reason(defensible)
        if problem is not None:
            reasons.append(absent_prefix + problem)
        if _reading_agreement(first) is Agreement.AGREED and not _reading_semantic_unknown(defensible):
            if _reading_semantic_key(first[0].result) != _reading_semantic_key(defensible):
                reasons.append(absent_prefix + "semantic_disagreement")
    if specified_reading is not None:
        problem = _reading_unresolved_reason(specified_reading)
        if problem is not None:
            reasons.append(f"machine_specified_adjudication_{problem}")
        if _reading_agreement(specified) is Agreement.AGREED and not _reading_semantic_unknown(specified_reading):
            if _reading_semantic_key(specified[0].result) != _reading_semantic_key(specified_reading):
                reasons.append("machine_specified_adjudication_semantic_disagreement")
    if protocol.protocol_design == SELECTED_PROTOCOL and adjudication is not None:
        if blind_first is not None and not _blind_was_committed(adjudication, blind_first):
            reasons.append("machine_blind_first_receipt_missing")
        if (cohort == "C" and blind_second is not None and specified_adjudication is not None
                and not _blind_was_committed(specified_adjudication, blind_second)):
            reasons.append("machine_blind_specified_receipt_missing")
    blind_exposed_first = (_reading_blind_agreement(blind_first, defensible)
                           if _blind_was_committed(adjudication, blind_first) else Agreement.UNKNOWN)
    blind_exposed_second = (_reading_blind_agreement(blind_second, specified_reading)
                            if _blind_was_committed(specified_adjudication, blind_second) else Agreement.UNKNOWN)
    if blind_exposed_first is Agreement.DISAGREED:
        reasons.append("machine_blind_vs_exposed_first_disagreement")
    if blind_exposed_second is Agreement.DISAGREED:
        reasons.append("machine_blind_vs_exposed_specified_disagreement")
    comparisons = (blind_exposed_first, blind_exposed_second) if cohort == "C" else (blind_exposed_first,)
    blind_exposed = (Agreement.DISAGREED if Agreement.DISAGREED in comparisons else
                     Agreement.UNKNOWN if Agreement.UNKNOWN in comparisons else Agreement.AGREED)
    complete = not reasons
    provenance = _provenance(protocol, material, cohort, first, specified, blinds, adjudication, specified_adjudication)
    endpoint = _endpoint(defensible, complete)
    target = _convention_target(specified_reading, complete) if cohort == "C" else None
    state = ReferenceState.UNRESOLVED if not complete else ReferenceState.ADJUDICATED
    if complete and ((cohort == "N" and endpoint[2] is not None)
                     or (cohort == "C" and target[4] is not None)):
        state = ReferenceState.PARTIAL
        reasons.append("machine_target_not_unique")
    return {"first": first, "specified_passes": specified, "defensible": defensible,
            "specified": specified_reading, "complete": complete, "state": state, "reasons": tuple(reasons),
            "blind_passes": blinds, "blind_first_agreement": blind_first_agreement,
            "blind_specified_agreement": blind_second_agreement,
            "blind_vs_exposed_first": blind_exposed_first, "blind_vs_exposed_specified": blind_exposed_second,
            "blind_vs_exposed": blind_exposed,
            "endpoint_fields": endpoint, "target_fields": target, "provenance": provenance}


@dataclass(frozen=True, slots=True)
class ReconciledReadings:
    protocol: MachineProtocol
    material: BlindNotice
    cohort: str
    reference_version: str
    first_passes: tuple[MachineJudgment, ...]
    specified_passes: tuple[MachineJudgment, ...]
    blind_passes: tuple[MachineJudgment, ...]
    adjudication: MachineJudgment | None
    specified_adjudication: MachineJudgment | None

    def __post_init__(self) -> None:
        _exact(self, ReconciledReadings, "reconciled readings")
        if any(type(items) is not tuple for items in (self.first_passes, self.specified_passes, self.blind_passes)):
            raise TypeError("reconciled pass records must be tuples")
        ReconciledReadings._parts(self)

    def _parts(self) -> dict[str, object]:
        _exact(self, ReconciledReadings, "reconciled readings")
        return _reading_parts(self.protocol, self.material, self.cohort, self.reference_version,
                              self.first_passes, self.specified_passes, self.blind_passes, self.adjudication,
                              self.specified_adjudication)

    @property
    def item_id(self) -> str:
        ReconciledReadings._parts(self)
        return self.material.item_id

    @property
    def first_agreement(self) -> Agreement:
        return _reading_agreement(ReconciledReadings._parts(self)["first"])

    @property
    def first_quote_agreement(self) -> Agreement:
        return _reading_quote_agreement(ReconciledReadings._parts(self)["first"])

    @property
    def specified_agreement(self) -> Agreement | None:
        parts = ReconciledReadings._parts(self)
        return _reading_agreement(parts["specified_passes"]) if self.cohort == "C" else None

    @property
    def specified_quote_agreement(self) -> Agreement | None:
        parts = ReconciledReadings._parts(self)
        return _reading_quote_agreement(parts["specified_passes"]) if self.cohort == "C" else None

    @property
    def blind_first_agreement(self) -> Agreement:
        return ReconciledReadings._parts(self)["blind_first_agreement"]

    @property
    def blind_specified_agreement(self) -> Agreement | None:
        parts = ReconciledReadings._parts(self)
        return parts["blind_specified_agreement"] if self.cohort == "C" else None

    @property
    def blind_vs_exposed(self) -> Agreement:
        return ReconciledReadings._parts(self)["blind_vs_exposed"]

    @property
    def blind_vs_exposed_first(self) -> Agreement:
        return ReconciledReadings._parts(self)["blind_vs_exposed_first"]

    @property
    def blind_vs_exposed_specified(self) -> Agreement | None:
        parts = ReconciledReadings._parts(self)
        return parts["blind_vs_exposed_specified"] if self.cohort == "C" else None

    @property
    def selected_candidate_resolved(self) -> bool:
        parts = ReconciledReadings._parts(self)
        return self.protocol.protocol_design == SELECTED_PROTOCOL and parts["state"] is ReferenceState.ADJUDICATED

    @property
    def defensible(self) -> MachineReading | None:
        return ReconciledReadings._parts(self)["defensible"]

    @property
    def specified(self) -> MachineReading | None:
        return ReconciledReadings._parts(self)["specified"]

    @property
    def process_complete(self) -> bool:
        return ReconciledReadings._parts(self)["complete"]

    @property
    def state(self) -> ReferenceState:
        return ReconciledReadings._parts(self)["state"]

    @property
    def reasons(self) -> tuple[str, ...]:
        return ReconciledReadings._parts(self)["reasons"]

    @property
    def provenance(self) -> MachineProvenance:
        return ReconciledReadings._parts(self)["provenance"]

    @property
    def endpoint(self) -> MachineEndpoint:
        return MachineEndpoint(self)

    @property
    def convention_target(self) -> MachineConventionTarget:
        ReconciledReadings._parts(self)
        if self.cohort != "C":
            raise ValueError("only C has a specified convention target")
        return MachineConventionTarget(self)


def reconcile_readings(
    protocol: MachineProtocol, material: BlindNotice, *, cohort: str, reference_version: str,
    first_passes: Iterable[MachineJudgment], specified_passes: Iterable[MachineJudgment] = (),
    blind_passes: Iterable[MachineJudgment] = (),
    adjudication: MachineJudgment | None = None, specified_adjudication: MachineJudgment | None = None,
) -> ReconciledReadings:
    """Preserve all N/C passes; agreement alone never creates a reference."""
    parts = _reading_parts(protocol, material, cohort, reference_version, first_passes, specified_passes,
                           blind_passes, adjudication, specified_adjudication)
    return ReconciledReadings(protocol, material, cohort, reference_version, parts["first"],
                              parts["specified_passes"], parts["blind_passes"], adjudication, specified_adjudication)


def revalidate_readings(reference: ReconciledReadings) -> None:
    """Revalidate a machine record without converting it to a human reference."""
    _exact(reference, ReconciledReadings, "reconciled readings")
    ReconciledReadings._parts(reference)


def _role_problem(reading: MachineRoleReading, material: BlindRoleSet) -> str | None:
    if reading.material_valid is None:
        return "machine_material_validity_unknown"
    if reading.material_valid is False:
        return None
    if any(value is not True for value in asdict(reading.checks).values()):
        return "machine_validity_conflicts_with_checks"
    if any(item.status != "exact" or item.quote_valid is not True
           or any(value != item.target_date for value in item.alternatives) for item in reading.targets):
        return "machine_role_target_unresolved"
    if len({item.target_date for item in reading.targets}) != 1:
        return "machine_role_targets_differ"
    notices = {notice.item_id: notice for notice in material.notices}
    if len({notice.update_date for notice in material.notices}) != 1:
        return "machine_update_dates_differ"
    dated_roles = []
    for item in reading.targets:
        if any(role.role is None or role.date is None or role.quote_valid is not True for role in item.date_roles):
            return "machine_date_role_unresolved"
        by_role: dict[str, set[date]] = {}
        for role in item.date_roles:
            by_role.setdefault(role.role, set()).add(role.date)
        if not {"publication", "superseded_recovery"} <= set(by_role):
            return "machine_date_roles_incomplete"
        competing = set(by_role) & {"next_review", "administrative"}
        if not competing:
            return "machine_date_roles_incomplete"
        if len(competing) != 1 or any(len(dates) != 1 for role, dates in by_role.items() if role != "other"):
            return "machine_date_role_not_unique"
        if "current_recovery" in by_role and by_role["current_recovery"] != {item.target_date}:
            return "machine_date_role_conflicts_with_target"
        publication = next(iter(by_role["publication"]))
        issue = next(iter(by_role["superseded_issue"])) if "superseded_issue" in by_role else None
        superseded = next(iter(by_role["superseded_recovery"]))
        competitor = next(iter(by_role[next(iter(competing))]))
        update = notices[item.variant_id].update_date
        if (not (publication < superseded < update < item.target_date and update < competitor)
                or (issue is not None and not publication < issue < superseded)):
            return "machine_role_chronology_conflict"
        if len({publication, superseded, update, item.target_date, competitor}) != 5:
            return "machine_role_dates_not_distinct"
        # The generic schema also supports notices with no issue date. If any
        # variant labels one, however, all four must label the same date.
        dated_roles.append((publication, issue, superseded, competitor))
    if len(set(dated_roles)) != 1:
        return "machine_role_dates_differ_across_variants"
    return None


def _role_semantic_unknown(reading: MachineRoleReading) -> bool:
    return (reading.material_valid is None or any(value is None for value in asdict(reading.checks).values())
            or any(target.status == "unresolved" or any(role.role is None or role.date is None
                   for role in target.date_roles) for target in reading.targets))


def _role_semantic_key(reading: MachineRoleReading) -> tuple[object, ...]:
    targets = tuple(sorted((target.variant_id, target.status, target.target_date,
                            frozenset(target.alternatives), frozenset((role.role, role.date)
                            for role in target.date_roles)) for target in reading.targets))
    return targets, tuple(asdict(reading.checks).values()), reading.material_valid


def _role_source_unresolved(reading: object, material: BlindRoleSet) -> bool:
    if type(reading) is not MachineRoleReading or _role_semantic_unknown(reading):
        return True
    if any(target.quote_valid is False or not target.date_roles or any(
        role.quote_valid is not True for role in target.date_roles
    ) for target in reading.targets):
        return True
    return _role_problem(reading, material) is not None


def _role_agreement(passes: tuple[MachineJudgment, ...]) -> Agreement:
    if len(passes) != 2 or any(item.status is not ParseStatus.VALID or type(item.result) is not MachineRoleReading
                               or _role_semantic_unknown(item.result) for item in passes):
        return Agreement.UNKNOWN
    left, right = (_role_semantic_key(item.result) for item in passes)
    return Agreement.AGREED if left == right else Agreement.DISAGREED


def _role_quote_agreement(passes: tuple[MachineJudgment, ...]) -> Agreement:
    if _role_agreement(passes) is not Agreement.AGREED:
        return Agreement.UNKNOWN
    def quotes(reading: MachineRoleReading) -> tuple[object, ...]:
        return tuple(sorted((target.variant_id, target.quote, frozenset(
            (role.role, role.date, role.quote) for role in target.date_roles
        )) for target in reading.targets))
    left, right = (quotes(item.result) for item in passes)
    return Agreement.AGREED if left == right else Agreement.DISAGREED


def _role_blind_agreement(blind: MachineJudgment | None, other: MachineRoleReading | None,
                          material: BlindRoleSet) -> Agreement:
    if (blind is None or blind.status is not ParseStatus.VALID or type(blind.result) is not MachineRoleReading
            or other is None or _role_source_unresolved(blind.result, material) or _role_source_unresolved(other, material)):
        return Agreement.UNKNOWN
    return Agreement.AGREED if _role_semantic_key(blind.result) == _role_semantic_key(other) else Agreement.DISAGREED


def _blind_against_roles(blind: MachineJudgment | None, passes: tuple[MachineJudgment, ...],
                         material: BlindRoleSet) -> Agreement:
    if (_role_agreement(passes) is not Agreement.AGREED
            or any(_role_source_unresolved(item.result, material) for item in passes)):
        return Agreement.UNKNOWN
    return _role_blind_agreement(blind, passes[0].result, material)


def _role_parts(protocol: MachineProtocol, material: BlindRoleSet, reference_version: str,
                first_passes: tuple[MachineJudgment, ...], blind_passes: tuple[MachineJudgment, ...],
                adjudication: MachineJudgment | None) -> dict[str, object]:
    _exact(material, BlindRoleSet, "role material")
    _exact(protocol, MachineProtocol, "protocol")
    MachineProtocol.__post_init__(protocol)
    require_identifier(reference_version, "reference_version")
    if reference_version != protocol.reference_version:
        raise ValueError("reference_version must match the pinned protocol")
    first, _, blinds = _sources_and_adjudication(protocol, material, "R", first_passes, (), blind_passes, adjudication)
    reasons = _source_reasons(first, "first", "R", material)
    blind = None
    blind_first_agreement = Agreement.UNKNOWN
    if protocol.protocol_design == SELECTED_PROTOCOL:
        blind = _blind_at(blinds, "blind_proposal")
        reasons.extend(_blind_reasons(blind, "first", "R", material))
        blind_first_agreement = _blind_against_roles(blind, first, material)
        if blind_first_agreement is Agreement.DISAGREED:
            reasons.append("machine_blind_first_semantic_disagreement")
    decision = None
    if adjudication is None:
        reasons.append("machine_adjudication_missing")
    elif adjudication.status is not ParseStatus.VALID:
        reasons.append(f"machine_adjudication_{adjudication.status.value}")
    elif type(adjudication.result) is not RoleDecision:
        raise ValueError("adjudication result does not match the role cohort")
    else:
        decision = adjudication.result.reference
        if _role_source_unresolved(decision, material):
            reasons.append("machine_adjudication_unresolved")
            problem = _role_problem(decision, material)
            if problem is not None:
                reasons.append(problem)
        if (_role_agreement(first) is Agreement.AGREED and not _role_semantic_unknown(decision)
                and _role_semantic_key(first[0].result) != _role_semantic_key(decision)):
            reasons.append("machine_adjudication_semantic_disagreement")
    if protocol.protocol_design == SELECTED_PROTOCOL and adjudication is not None and blind is not None and not _blind_was_committed(adjudication, blind):
        reasons.append("machine_blind_first_receipt_missing")
    blind_exposed = (_role_blind_agreement(blind, decision, material)
                     if _blind_was_committed(adjudication, blind) else Agreement.UNKNOWN)
    if blind_exposed is Agreement.DISAGREED:
        reasons.append("machine_blind_vs_exposed_first_disagreement")
    validity = MachineValidity.UNRESOLVED
    if not reasons and decision is not None:
        validity = MachineValidity.VALID if decision.material_valid else MachineValidity.INVALID
    return {"first": first, "decision": decision, "validity": validity, "reasons": tuple(reasons),
            "blind_passes": blinds, "blind_first_agreement": blind_first_agreement,
            "blind_vs_exposed": blind_exposed,
            "provenance": _provenance(protocol, material, "R", first, (), blinds, adjudication)}


@dataclass(frozen=True, slots=True)
class ReconciledRole:
    protocol: MachineProtocol
    material: BlindRoleSet
    reference_version: str
    first_passes: tuple[MachineJudgment, ...]
    blind_passes: tuple[MachineJudgment, ...]
    adjudication: MachineJudgment | None

    def __post_init__(self) -> None:
        _exact(self, ReconciledRole, "reconciled role")
        if type(self.first_passes) is not tuple or type(self.blind_passes) is not tuple:
            raise TypeError("reconciled pass records must be a tuple")
        ReconciledRole._parts(self)

    def _parts(self) -> dict[str, object]:
        _exact(self, ReconciledRole, "reconciled role")
        return _role_parts(self.protocol, self.material, self.reference_version, self.first_passes,
                           self.blind_passes, self.adjudication)

    @property
    def group_id(self) -> str:
        ReconciledRole._parts(self)
        return self.material.group_id

    @property
    def first_agreement(self) -> Agreement:
        return _role_agreement(ReconciledRole._parts(self)["first"])

    @property
    def first_quote_agreement(self) -> Agreement:
        return _role_quote_agreement(ReconciledRole._parts(self)["first"])

    @property
    def blind_first_agreement(self) -> Agreement:
        return ReconciledRole._parts(self)["blind_first_agreement"]

    @property
    def blind_vs_exposed(self) -> Agreement:
        return ReconciledRole._parts(self)["blind_vs_exposed"]

    @property
    def selected_candidate_resolved(self) -> bool:
        """R remains ineligible until separate generator-bound review is complete."""
        ReconciledRole._parts(self)
        return False

    @property
    def decision(self) -> MachineRoleReading | None:
        return ReconciledRole._parts(self)["decision"]

    @property
    def validity(self) -> MachineValidity:
        return ReconciledRole._parts(self)["validity"]

    @property
    def reasons(self) -> tuple[str, ...]:
        return ReconciledRole._parts(self)["reasons"]

    @property
    def provenance(self) -> MachineProvenance:
        return ReconciledRole._parts(self)["provenance"]

    def export(self) -> dict[str, object]:
        """Export a rederived machine-only R summary with no human-gold claim."""
        parts = ReconciledRole._parts(self)
        provenance = parts["provenance"]
        return {"machine_reference_label": "machine_generated_not_human",
                "detached_value_status": "untrusted_detached_serialization",
                "semantic_truth": "not_verified", "real_use_authorized": False,
                "protocol_design": provenance.protocol_design, "candidate_track": provenance.candidate_track,
                "machine_validity": parts["validity"].value, "blind_vs_exposed": parts["blind_vs_exposed"].value,
                "selected_candidate_resolved": False,
                "generator_eligibility": "unresolved_separate_generator_revision_required",
                "reasons": list(parts["reasons"]), "provenance": asdict(provenance)}

    def export_json(self) -> str:
        """Serialize a freshly rederived, explicitly untrusted R summary."""
        return _canonical(ReconciledRole.export(self))


def reconcile_role(
    protocol: MachineProtocol, material: BlindRoleSet, *, reference_version: str,
    first_passes: Iterable[MachineJudgment], blind_passes: Iterable[MachineJudgment] = (),
    adjudication: MachineJudgment | None = None,
) -> ReconciledRole:
    """Produce only a machine-validity label, retaining every source judgment."""
    parts = _role_parts(protocol, material, reference_version, first_passes, blind_passes, adjudication)
    return ReconciledRole(protocol, material, reference_version, parts["first"], parts["blind_passes"], adjudication)


def revalidate_role(reference: ReconciledRole) -> None:
    """Revalidate the supplied machine role record, not human material validity."""
    _exact(reference, ReconciledRole, "reconciled role")
    ReconciledRole._parts(reference)


@dataclass(frozen=True, slots=True)
class MachineRoleEligibility:
    """Invented checks only; the private seed and mapping must not enter a judge view."""

    reference: ReconciledRole = field(repr=False)
    seed: RoleSeed = field(repr=False)
    opaque_variant_map: tuple[tuple[str, str], ...] = field(repr=False)
    generator_version: str

    def __post_init__(self) -> None:
        _exact(self, MachineRoleEligibility, "machine role eligibility")
        MachineRoleEligibility._parts(self)

    def _parts(self) -> tuple[MachineProvenance, tuple[str, ...]]:
        _exact(self, MachineRoleEligibility, "machine role eligibility")
        return _role_eligibility_parts(self.reference, self.seed, self.opaque_variant_map, self.generator_version)

    @property
    def provenance(self) -> MachineProvenance:
        return MachineRoleEligibility._parts(self)[0]

    @property
    def reasons(self) -> tuple[str, ...]:
        return (*MachineRoleEligibility._parts(self)[1], "machine_role_deterministic_text_matching_unresolved",
                "machine_role_separate_generator_revision_required")

    @property
    def structural_checks_pass(self) -> bool:
        return not MachineRoleEligibility._parts(self)[1]

    @property
    def eligible_for_synthetic_checks(self) -> bool:
        MachineRoleEligibility._parts(self)
        return False

    @property
    def blinded_role_eligible(self) -> bool:
        MachineRoleEligibility._parts(self)
        return False


def _validate_seed_types(seed: RoleSeed) -> None:
    _exact(seed, RoleSeed, "role seed")
    require_identifier(seed.seed_id, "seed_id")
    _exact(seed.wording_family, int, "wording_family")
    _exact(seed.competing_order, str, "competing_order")
    for name in ("update_date", "publication_date", "superseded_issue_date", "superseded_target_date",
                 "target_date", "competing_date"):
        _exact(getattr(seed, name), date, name)
    if type(seed.variants) is not tuple:
        raise TypeError("seed variants must be a tuple")
    for variant in seed.variants:
        _exact(variant, RoleVariant, "role variant")
        for name in ("item_id", "seed_id", "arm", "position", "notice_text"):
            require_identifier(getattr(variant, name), name)
        _exact(variant.primary, bool, "primary")
        _exact(variant.update_date, date, "update_date")


def _role_eligibility_parts(
    reference: ReconciledRole, seed: RoleSeed, opaque_variant_map: tuple[tuple[str, str], ...],
    generator_version: str,
) -> tuple[MachineProvenance, tuple[str, ...]]:
    _exact(reference, ReconciledRole, "reconciled role")
    parts = ReconciledRole._parts(reference)
    _validate_seed_types(seed)
    require_identifier(generator_version, "generator_version")
    if type(opaque_variant_map) is not tuple or any(
        type(pair) is not tuple or len(pair) != 2 or any(type(value) is not str for value in pair)
        for pair in opaque_variant_map
    ):
        raise TypeError("opaque variant mapping must be a tuple of string pairs")
    for opaque, variant_id in opaque_variant_map:
        require_identifier(opaque, "opaque variant ID")
        require_identifier(variant_id, "variant ID")
    reasons = []
    if generator_version != GENERATOR_VERSION:
        reasons.append("machine_role_generator_version_mismatch")
    blinding = reference.material.blinding
    PrivateRoleBlinding._validate(blinding)
    seed_shaped = (re.fullmatch(r"[0-9a-f]{64}", seed.seed_id) is not None and len(set(seed.seed_id)) >= 8)
    if not seed_shaped:
        reasons.append("machine_role_private_seed_not_high_entropy_shaped")
    elif seed.seed_id != blinding._private_seed_id:
        reasons.append("machine_role_private_seed_mismatch")
    else:
        try:
            validate_structure(seed)
            expected_seed = _make_seed(seed.seed_id, seed.wording_family, seed.competing_order)
            if _record_value(seed) != _record_value(expected_seed):
                reasons.append("machine_role_generator_mismatch")
        except (TypeError, ValueError):
            reasons.append("machine_role_seed_structure_invalid")
    expected_group = blinding.group_id
    expected_map = set(blinding.opaque_variant_map())
    if reference.protocol.role_alias_commitment_sha256 != blinding.key_commitment_sha256:
        reasons.append("machine_role_alias_commitment_mismatch")
    if blinding.seed_commitment_sha256 not in reference.protocol.role_seed_commitments:
        reasons.append("machine_role_seed_commitment_unlisted")
    if (reference.material.group_id != expected_group or len(opaque_variant_map) != 4
            or len(set(opaque_variant_map)) != 4 or set(opaque_variant_map) != expected_map):
        reasons.append("machine_role_mapping_mismatch")
    notices = {notice.item_id: notice for notice in reference.material.notices}
    variants = {variant.item_id: variant for variant in seed.variants}
    if (set(notices) != {pair[0] for pair in expected_map}
            or set(variants) != {pair[1] for pair in expected_map}):
        reasons.append("machine_role_variant_hash_mismatch")
    else:
        for opaque, variant_id in expected_map:
            actual = notices[opaque].visible()
            variant = variants[variant_id]
            expected = {"update_date": variant.update_date.isoformat(), "notice_text": variant.notice_text}
            if _sha256(_canonical(actual)) != _sha256(_canonical(expected)) or actual != expected:
                reasons.append("machine_role_variant_hash_mismatch")
                break
    if parts["validity"] is not MachineValidity.VALID:
        reasons.append("machine_role_reference_unresolved")
    decision = parts["decision"]
    if decision is None or any(target.status != "exact" or target.target_date != seed.target_date
                               for target in decision.targets):
        reasons.append("machine_role_target_mismatch")
    readings = tuple(item.result for item in (*parts["first"], *parts["blind_passes"])
                     if type(item.result) is MachineRoleReading)
    if decision is not None:
        readings += (decision,)
    if readings:
        variant_by_opaque = {opaque: variants.get(variant_id) for opaque, variant_id in expected_map}
        for reading in readings:
            for target in reading.targets:
                variant = variant_by_opaque.get(target.variant_id)
                if variant is None:
                    reasons.append("machine_role_generator_date_roles_unverified")
                    break
                role = "next_review" if variant.arm == "competitor" else "administrative"
                required = {
                    ("publication", seed.publication_date),
                    ("superseded_issue", seed.superseded_issue_date),
                    ("superseded_recovery", seed.superseded_target_date),
                    (role, seed.competing_date),
                }
                supported = {(item.role, item.date) for item in target.date_roles if item.quote_valid is True}
                allowed_with_target = required | {("current_recovery", seed.target_date)}
                if (len(supported) != len(target.date_roles)
                        or (supported != required and supported != allowed_with_target)):
                    reasons.append("machine_role_generator_date_roles_unverified")
                    break
            else:
                continue
            break
    return parts["provenance"], tuple(reasons)


def assess_synthetic_role_eligibility(
    reference: ReconciledRole, *, seed: RoleSeed, opaque_variant_map: tuple[tuple[str, str], ...],
    generator_version: str,
) -> MachineRoleEligibility:
    """Bind to the current draft generator for invented checks, not a proof of a lock."""
    return MachineRoleEligibility(reference, seed, opaque_variant_map, generator_version)


@dataclass(frozen=True, slots=True)
class LaterRegistration:
    registration_id: str
    protocol_sha256: str
    implementation_sha256: str
    material_plan_sha256: str
    record_sha256: str
    commit_sha: str
    implementation_frozen_utc: datetime
    recorded_utc: datetime
    pushed_utc: datetime
    role_alias_commitment_sha256: str | None
    role_seed_manifest_sha256: str | None

    def __post_init__(self) -> None:
        _exact(self, LaterRegistration, "registration")
        require_identifier(self.registration_id, "registration_id")
        for name in ("protocol_sha256", "implementation_sha256", "material_plan_sha256", "record_sha256"):
            require_sha256(getattr(self, name), name)
        if self.role_alias_commitment_sha256 is not None:
            require_sha256(self.role_alias_commitment_sha256, "role_alias_commitment_sha256")
        if self.role_seed_manifest_sha256 is not None:
            require_sha256(self.role_seed_manifest_sha256, "role_seed_manifest_sha256")
        if type(self.commit_sha) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.commit_sha) is None:
            raise ValueError("commit_sha must be a full lowercase commit identity")
        _utc(self.implementation_frozen_utc, "implementation_frozen_utc")
        _utc(self.recorded_utc, "recorded_utc")
        _utc(self.pushed_utc, "pushed_utc")
        if self.recorded_utc <= self.implementation_frozen_utc:
            raise ValueError("registration must follow the implementation freeze")
        if self.pushed_utc < self.recorded_utc:
            raise ValueError("registration cannot be pushed before it is recorded")


@dataclass(frozen=True, slots=True)
class RegistrationVerification:
    """Externally supplied verification attestation, not proof by itself."""

    commit_sha: str
    record_sha256: str
    implementation_sha256: str
    verified_utc: datetime
    pushed: bool

    def __post_init__(self) -> None:
        _exact(self, RegistrationVerification, "registration verification")
        if type(self.commit_sha) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.commit_sha) is None:
            raise ValueError("verification needs a full commit identity")
        require_sha256(self.record_sha256, "record_sha256")
        require_sha256(self.implementation_sha256, "implementation_sha256")
        _utc(self.verified_utc, "verified_utc")
        if type(self.pushed) is not bool:
            raise TypeError("pushed must be bool")


@dataclass(frozen=True, slots=True)
class RegisteredUse:
    """Supplied real-use records; actual registration verification stays external."""

    registration: LaterRegistration
    verification: RegistrationVerification
    implementation_sha256: str
    material_plan_sha256: str
    first_real_activity_utc: datetime

    def __post_init__(self) -> None:
        _exact(self, RegisteredUse, "registered use")
        _exact(self.registration, LaterRegistration, "registration")
        _exact(self.verification, RegistrationVerification, "verification")
        LaterRegistration.__post_init__(self.registration)
        RegistrationVerification.__post_init__(self.verification)
        require_sha256(self.implementation_sha256, "implementation_sha256")
        require_sha256(self.material_plan_sha256, "material_plan_sha256")
        _utc(self.first_real_activity_utc, "first_real_activity_utc")


def check_later_registration_claim(
    protocol: MachineProtocol, *, registration: LaterRegistration | None,
    verification: RegistrationVerification | None, implementation_sha256: str,
    material_plan_sha256: str, first_real_activity_utc: datetime, evaluation_utc: datetime | None = None,
) -> None:
    """Check supplied records only; real approval and verification remain external.

    Passing this check does not perform or authorize evaluation. The separately
    recorded, pushed registration and its identities must actually be verified
    before the first real collection, not merely before analysis. An omitted
    evaluation timestamp remains unknown; it is not inferred from collection.
    """
    if registration is None or verification is None:
        raise ValueError("a separate later registration and external verification are required")
    _exact(registration, LaterRegistration, "registration")
    _exact(verification, RegistrationVerification, "verification")
    _exact(protocol, MachineProtocol, "protocol")
    _record_value((registration, verification, protocol))
    LaterRegistration.__post_init__(registration)
    RegistrationVerification.__post_init__(verification)
    MachineProtocol.__post_init__(protocol)
    if protocol.data_scope != "real":
        raise ValueError("a synthetic protocol cannot authorize real activity")
    require_sha256(implementation_sha256, "implementation_sha256")
    require_sha256(material_plan_sha256, "material_plan_sha256")
    _utc(first_real_activity_utc, "first_real_activity_utc")
    if evaluation_utc is not None:
        _utc(evaluation_utc, "evaluation_utc")
    if registration.registration_id == protocol.protocol_id:
        raise ValueError("registration must have a separate identity")
    if (registration.protocol_sha256 != protocol.sha256
            or registration.role_alias_commitment_sha256 != protocol.role_alias_commitment_sha256
            or registration.role_seed_manifest_sha256 != protocol.role_seed_manifest_sha256
            or registration.implementation_sha256 != implementation_sha256
            or registration.material_plan_sha256 != material_plan_sha256
            or verification.commit_sha != registration.commit_sha
            or verification.record_sha256 != registration.record_sha256
            or verification.implementation_sha256 != implementation_sha256
            or not verification.pushed):
        raise ValueError("registration or verification identities do not match")
    if (not (registration.recorded_utc <= registration.pushed_utc <= verification.verified_utc
             < first_real_activity_utc)
            or (evaluation_utc is not None and evaluation_utc < first_real_activity_utc)):
        raise ValueError("registration and verification must precede all real activity and evaluation")
