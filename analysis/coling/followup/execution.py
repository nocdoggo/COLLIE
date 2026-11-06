"""Bounded follow-up request construction and persistent mock execution.

There is deliberately no live HTTP transport in this module. The SQLite mock
permits only one sent attempt at a time across connections; an outstanding sent
attempt fences further dispatch until settlement or independently attested
recovery. This is not proof of real worker quiescence, provider enforcement, or
trusted monotonic time. Those remain hard blockers to live activation, together
with registration, spending authorization, tokenizer and route verification.
Malformed or conflicting charge claims are permanently quarantined: this mock
has no correction/adjudication interface. Evidence digests are caller-supplied
identifiers, not verified proof. The ledger never chooses a file path.
Accounting SQL targets SQLite's main schema. TEMP triggers are refused because
they can act on main tables; discovering one after initialization permanently
fences the schema. An outcome presented on a TEMP-trigger-contaminated
connection cannot safely be recorded there; its caller must retain the evidence.
If storage cannot persist a fence or incident, external shutdown is mandatory.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from itertools import islice
from math import isfinite, nextafter
from threading import RLock, get_ident
from typing import Callable, Iterable, Mapping, NoReturn

from . import prompts
from .records import require_identifier, require_sha256
from .role_analysis import PRIMARY_ROUTES


USER_AGENT = "collie-research-fetch/0.1 (academic research; polite, cached)"
INPUT_LIMIT = 4000
OUTPUT_LIMIT = 1024
HTTP_LIMIT = 1400
PILOT_RETURN_LIMIT = 20
RETRY_DELAY_SECONDS = 60
PICOS_PER_DOLLAR = 1_000_000_000_000
SQLITE_INT_MAX = 2**63 - 1
MAX_MONEY_LENGTH = 128
MAX_MONEY_EXPONENT = 64
MAX_MONEY_EFFECTIVE_EXPONENT = 128
MAX_REQUEST_CHARS = 65_536
MAX_REQUEST_BYTES = 1_048_576
MAX_IDENTIFIER_CHARS = 256
MAX_RESPONSE_CHARS = 65_536
_MAX_METADATA_CHARS = 1024
_MONEY_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?\Z", re.ASCII)
_N_TEMPLATES = frozenset({"january-natural-v1"})
_C_TEMPLATES = frozenset({"january-convention-absent-v1", "january-convention-neutral-v1",
                          "january-convention-explicit-v1"})
_R_TEMPLATES = frozenset({"january-role-v1"})


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _money(value: str, name: str, *, positive: bool = False) -> Decimal:
    if type(value) is not str:
        raise TypeError(f"{name} must be a decimal string")
    if len(value) > MAX_MONEY_LENGTH:
        raise ValueError(f"{name} exceeds the decimal length limit")
    match = _MONEY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"{name} must be a finite decimal")
    exponent = match.group(1)
    if exponent is not None and abs(int(exponent)) > MAX_MONEY_EXPONENT:
        raise ValueError(f"{name} exceeds the decimal exponent limit")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a finite decimal") from error
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise ValueError(f"{name} must be a known {'positive' if positive else 'nonnegative'} decimal")
    if abs(amount.as_tuple().exponent) > MAX_MONEY_EFFECTIVE_EXPONENT:
        raise ValueError(f"{name} exceeds the effective decimal exponent limit")
    return amount


def _picos(value: Decimal | Fraction) -> int:
    scaled = Fraction(value) * PICOS_PER_DOLLAR
    amount = -(-scaled.numerator // scaled.denominator)
    if amount > 9_000_000_000_000_000_000:
        raise ValueError("amount exceeds the accounting range")
    return amount


def _cap_picos(value: Decimal) -> int:
    """Round a spending ceiling down, never up to the next picodollar."""
    scaled = Fraction(value) * PICOS_PER_DOLLAR
    amount = scaled.numerator // scaled.denominator
    if not amount:
        raise ValueError("programme cap is below one picodollar")
    return amount


def _now(value: int) -> None:
    if type(value) is not int or not 0 <= value <= SQLITE_INT_MAX:
        raise ValueError("now must be nonnegative SQLite-range integer seconds")


def _claim_record(value: object) -> str | None:
    """Retain a bounded charge description, including a prefix and its length.

    Oversized strings are deliberately truncated; an evidence digest, when
    supplied, is stored separately. This is not a full-fidelity receipt.
    """
    if value is None:
        return None
    if type(value) is str:
        prefix = value[:MAX_MONEY_LENGTH]
        record = {"type": "str", "length": len(value), "prefix": prefix,
                  "truncated": len(value) > MAX_MONEY_LENGTH}
    elif type(value) is int:
        bits = value.bit_length()
        if bits <= 256:
            record = {"type": "int", "value": str(value)}
        else:
            record = {"type": "int", "bits": bits, "leading_hex": hex(value >> (bits - 128))}
    elif type(value) is float:
        record = {"type": "float", "value": repr(value)}
    elif type(value) is bool:
        record = {"type": "bool", "value": value}
    else:
        record = {"type": type(value).__name__[:64]}
    return json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _claim_picos(record: str | None) -> int | None:
    """Return a bounded numeric claim when the complete decimal text is available."""
    if record is None:
        return None
    try:
        value = json.loads(record)
        if type(value) is not dict or value.get("type") != "str" or value.get("truncated") is not False:
            return None
        return _picos(_money(value.get("prefix"), "reported charge"))
    except (TypeError, ValueError, OverflowError, MemoryError, json.JSONDecodeError):
        return None


def _safe_text(value: object, limit: int) -> str | None:
    if type(value) is not str or len(value) > limit:
        return None
    try:
        value.encode("utf-8")
    except UnicodeError:
        return None
    return value


def _evidence(value: object) -> str | None:
    if type(value) is not str or len(value) != 64:
        return None
    try:
        require_sha256(value, "evidence")
    except (TypeError, ValueError):
        return None
    return value


def _attempt_id(value: int) -> None:
    if type(value) is not int or not 1 <= value <= SQLITE_INT_MAX:
        raise ValueError("attempt_id must be a positive SQLite-range integer")


@dataclass(frozen=True, slots=True)
class TokenCounter:
    """An externally verified tokenizer and full-request token counter."""

    model_id: str
    tokenizer_sha256: str
    count_request: Callable[[bytes], int]

    def __post_init__(self) -> None:
        if self.model_id not in PRIMARY_ROUTES:
            raise ValueError("tokenizer must name a primary model")
        require_sha256(self.tokenizer_sha256, "tokenizer_sha256")
        if not callable(self.count_request):
            raise TypeError("count_request must be callable")


@dataclass(frozen=True, slots=True)
class PriceSchedule:
    model_id: str
    provider_route: str
    precision: str
    prompt_usd_per_token: str
    completion_usd_per_token: str
    request_fee_usd: str
    max_context_tokens: int
    source_sha256: str
    reasoning_in_completion: bool
    no_unmodelled_fees: bool
    max_billable_output_tokens: int
    independent_charge_ceiling_usd: str
    charge_bound_evidence_sha256: str

    def __post_init__(self) -> None:
        if self.model_id not in PRIMARY_ROUTES or PRIMARY_ROUTES[self.model_id] != (
            self.provider_route, self.precision
        ):
            raise ValueError("pricing must name the pinned primary route")
        _money(self.prompt_usd_per_token, "prompt price", positive=True)
        _money(self.completion_usd_per_token, "completion price", positive=True)
        _money(self.request_fee_usd, "request fee")
        if (type(self.max_context_tokens) is not int
                or not INPUT_LIMIT <= self.max_context_tokens <= SQLITE_INT_MAX):
            raise ValueError("known provider context bound is required")
        require_sha256(self.source_sha256, "price source")
        if self.reasoning_in_completion is not True or self.no_unmodelled_fees is not True:
            raise ValueError("unresolved reasoning or fee pricing blocks execution")
        if (type(self.max_billable_output_tokens) is not int
                or not OUTPUT_LIMIT <= self.max_billable_output_tokens <= SQLITE_INT_MAX):
            raise ValueError("a separately established billable-output bound is required")
        ceiling = Fraction(_money(self.independent_charge_ceiling_usd, "independent charge ceiling", positive=True))
        require_sha256(self.charge_bound_evidence_sha256, "charge-bound evidence")
        if ceiling < self.upper_usd(self.max_context_tokens, self.max_billable_output_tokens):
            raise ValueError("independent charge ceiling must cover the stated token and fee bounds")

    def upper_usd(self, input_tokens: int, output_tokens: int) -> Fraction:
        if (type(input_tokens) is not int or type(output_tokens) is not int
                or not 0 <= input_tokens <= SQLITE_INT_MAX or not 0 <= output_tokens <= SQLITE_INT_MAX):
            raise ValueError("token counts must be nonnegative SQLite-range integers")
        return (Fraction(_money(self.prompt_usd_per_token, "prompt price")) * input_tokens
                + Fraction(_money(self.completion_usd_per_token, "completion price")) * output_tokens
                + Fraction(_money(self.request_fee_usd, "request fee")))

    def upper_picos(self, input_tokens: int, output_tokens: int) -> int:
        return _picos(self.upper_usd(input_tokens, output_tokens))

    @property
    def reservation_picos(self) -> int:
        # A requested max_tokens is not itself a hard billing limit. The caller
        # must independently establish a per-attempt charge ceiling, including
        # output overrun, hidden reasoning and all fees, before a live design.
        return _picos(_money(self.independent_charge_ceiling_usd, "independent charge ceiling"))

    @property
    def identity(self) -> str:
        return _sha(_canonical({
            "model": self.model_id, "route": self.provider_route, "precision": self.precision,
            "prompt": self.prompt_usd_per_token, "completion": self.completion_usd_per_token,
            "request_fee": self.request_fee_usd, "context": self.max_context_tokens,
            "source": self.source_sha256, "reasoning_in_completion": self.reasoning_in_completion,
            "no_unmodelled_fees": self.no_unmodelled_fees,
            "max_billable_output_tokens": self.max_billable_output_tokens,
            "independent_charge_ceiling_usd": self.independent_charge_ceiling_usd,
            "charge_bound_evidence_sha256": self.charge_bound_evidence_sha256,
        }))


@dataclass(frozen=True, slots=True)
class RequestSpec:
    request_id: str
    payload_sha256: str
    payload: bytes
    model_input_bytes: bytes
    item_id: str
    cohort: str
    model_id: str
    provider_route: str
    precision: str
    template_id: str
    template_sha256: str
    schema_sha256: str
    decoding_sha256: str
    item_text_sha256: str
    tokenizer_sha256: str
    measured_input_tokens: int
    pricing_sha256: str


def _wire_rate_at_most(value: str, *, multiplier: int, name: str) -> float:
    """Build a JSON number whose decimal spelling does not exceed the schedule.

    This is only a conservative mock payload choice. It cannot establish how a
    provider interprets or enforces its rate filter or bounds a total charge.
    """
    exact = Fraction(_money(value, name)) * multiplier
    try:
        candidate = float(exact)
    except OverflowError as error:
        raise ValueError(f"{name} is not representable in the mock payload") from error
    if not isfinite(candidate) or (exact > 0 and candidate == 0):
        raise ValueError(f"{name} is not representable in the mock payload")
    for _ in range(4):
        # Compare the JSON number's shortest decimal representation, not a
        # binary float against a rounded binary copy of the same schedule.
        if Fraction(Decimal(json.dumps(candidate, allow_nan=False))) <= exact:
            return candidate
        candidate = nextafter(candidate, 0.0)
        if exact > 0 and candidate == 0:
            break
    raise ValueError(f"{name} cannot be conservatively represented")


def _body(model_id: str, template_id: str, model_input: Mapping[str, str], price: PriceSchedule) -> dict:
    if not isinstance(model_input, Mapping) or len(model_input) > 16:
        raise ValueError("model input must be a bounded mapping")
    total = 0
    for index, (key, value) in enumerate(model_input.items()):
        if index >= 16:
            raise ValueError("model input must be a bounded mapping")
        if type(key) is not str or type(value) is not str:
            raise ValueError("model input must contain text fields")
        total += len(key) + len(value)
        if total > MAX_REQUEST_CHARS:
            raise ValueError("model input exceeds the mock byte-safety bound")
        if "@" in unicodedata.normalize("NFKC", value):
            raise ValueError("visible input with an at-sign requires privacy review before any request")
    prompt = prompts.render(template_id, model_input)
    schema = prompts.schema_for(template_id)
    # These fixed router settings are not verified retention or spending guarantees.
    return {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": OUTPUT_LIMIT,
        "provider": {"order": [price.provider_route], "only": [price.provider_route],
                      "allow_fallbacks": False, "quantizations": [price.precision],
                      "require_parameters": True, "data_collection": "deny",
                      "max_price": {
                          "prompt": _wire_rate_at_most(price.prompt_usd_per_token, multiplier=1_000_000,
                                                       name="prompt price"),
                          "completion": _wire_rate_at_most(price.completion_usd_per_token, multiplier=1_000_000,
                                                           name="completion price"),
                          "request": _wire_rate_at_most(price.request_fee_usd, multiplier=1, name="request fee"),
                      }},
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "role_reading" if template_id == prompts.ROLE_ID else "natural_reading",
            "strict": True, "schema": schema,
        }},
    }


def _identity(request: RequestSpec, body: dict) -> str:
    return _sha(_canonical({
        "cohort": request.cohort, "item_id": request.item_id, "model": request.model_id,
        "provider_route": request.provider_route, "precision": request.precision,
        "template_id": request.template_id, "template_sha256": request.template_sha256,
        "item_text_sha256": request.item_text_sha256, "schema_sha256": request.schema_sha256,
        "decoding_sha256": request.decoding_sha256,
        "temperature": 0, "output_limit": OUTPUT_LIMIT,
        "response_format": body["response_format"], "tokenizer_sha256": request.tokenizer_sha256,
        "input_limit": INPUT_LIMIT, "measured_input_tokens": request.measured_input_tokens,
        # The exact payload hash also binds every provider parameter, including
        # the fixed data-collection policy; it is not a provider guarantee.
        "pricing_sha256": request.pricing_sha256, "payload_sha256": request.payload_sha256,
    }))


def _decoding_sha(body: dict) -> str:
    return _sha(_canonical({"temperature": body["temperature"], "max_tokens": body["max_tokens"],
                            "response_format": body["response_format"]}))


@dataclass(frozen=True, slots=True)
class RequestBoundIdentity:
    """Hash-only identity for the exact mock request and parser.

    This is deliberately not a legacy ReadingIdentity. The separately reviewed
    analysis interfaces cannot yet consume it without discarding request fields.
    """

    cohort: str
    request_id: str
    payload_sha256: str
    tokenizer_sha256: str
    pricing_sha256: str
    item_id: str
    model_id: str
    provider_route: str
    precision: str
    template_id: str
    template_sha256: str
    schema_sha256: str
    decoding_sha256: str
    item_text_sha256: str
    measured_input_tokens: int
    parser_sha256: str

    def __post_init__(self) -> None:
        if type(self.cohort) is not str or self.cohort not in {"pilot", "N", "C", "R"}:
            raise ValueError("unknown cohort")
        for name in ("request_id", "payload_sha256", "tokenizer_sha256", "pricing_sha256",
                     "template_sha256", "schema_sha256", "decoding_sha256", "item_text_sha256", "parser_sha256"):
            require_sha256(getattr(self, name), name)
        for name in ("item_id", "model_id", "provider_route", "precision", "template_id"):
            value = getattr(self, name)
            if type(value) is not str or len(value) > MAX_IDENTIFIER_CHARS:
                raise ValueError(f"{name} exceeds the mock identifier bound")
            require_identifier(value, name)
        if type(self.measured_input_tokens) is not int or not 1 <= self.measured_input_tokens <= INPUT_LIMIT:
            raise ValueError("bounded measured input tokens are required")


def request_bound_identity(request: RequestSpec, price: PriceSchedule, *, parser_sha256: str) -> RequestBoundIdentity:
    """Validate a request and retain all request-binding hashes without exposing its text."""
    if type(request) is not RequestSpec or type(price) is not PriceSchedule:
        raise TypeError("request and price must be typed")
    PriceSchedule.__post_init__(price)
    _validate_request(request, price)
    return RequestBoundIdentity(
        request.cohort, request.request_id, request.payload_sha256, request.tokenizer_sha256,
        request.pricing_sha256, request.item_id, request.model_id, request.provider_route, request.precision,
        request.template_id, request.template_sha256, request.schema_sha256, request.decoding_sha256,
        request.item_text_sha256, request.measured_input_tokens, parser_sha256,
    )


def reading_identity(request: RequestSpec, *, parser_sha256: str) -> NoReturn:
    """Disabled: the legacy analysis identity omits material request bindings."""
    if type(request) is not RequestSpec:
        raise TypeError("request must be a RequestSpec")
    require_sha256(parser_sha256, "parser_sha256")
    raise RuntimeError("legacy ReadingIdentity omits request, cohort, payload, tokenizer and pricing; integration blocked")


def _validate_request(request: RequestSpec, price: PriceSchedule) -> None:
    for name in ("request_id", "payload_sha256", "template_sha256", "schema_sha256",
                 "decoding_sha256", "item_text_sha256", "tokenizer_sha256", "pricing_sha256"):
        require_sha256(getattr(request, name), name)
    if type(request.item_id) is not str or len(request.item_id) > MAX_IDENTIFIER_CHARS:
        raise ValueError("item_id exceeds the mock identifier bound")
    require_identifier(request.item_id, "item_id")
    if request.cohort not in {"pilot", "N", "C", "R"}:
        raise ValueError("unknown cohort")
    allowed = {"N": _N_TEMPLATES, "C": _C_TEMPLATES, "R": _R_TEMPLATES,
               "pilot": _N_TEMPLATES | _C_TEMPLATES | _R_TEMPLATES}[request.cohort]
    if request.template_id not in allowed:
        raise ValueError("template is not permitted for this cohort")
    if (request.model_id != price.model_id or request.provider_route != price.provider_route
            or request.precision != price.precision or request.pricing_sha256 != price.identity):
        raise ValueError("request identity or price schedule differs")
    if (type(request.payload) is not bytes or type(request.model_input_bytes) is not bytes
            or len(request.payload) > MAX_REQUEST_BYTES or len(request.model_input_bytes) > MAX_REQUEST_BYTES
            or _sha(request.payload) != request.payload_sha256
            or _sha(request.model_input_bytes) != request.item_text_sha256):
        raise ValueError("request payload or item identity differs")
    if (type(request.measured_input_tokens) is not int or not 1 <= request.measured_input_tokens <= INPUT_LIMIT
            or request.measured_input_tokens + OUTPUT_LIMIT > price.max_context_tokens):
        raise ValueError("tokenizer-measured request exceeds a limit")
    try:
        model_input = json.loads(request.model_input_bytes)
        if _canonical(model_input) != request.model_input_bytes:
            raise ValueError("model input is not canonical")
        body = _body(request.model_id, request.template_id, model_input, price)
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid request model input") from error
    if (_canonical(body) != request.payload or request.template_sha256 != prompts.template_sha256(request.template_id)
            or request.schema_sha256 != prompts.schema_sha256(request.template_id)
            or request.decoding_sha256 != _decoding_sha(body)
            or request.request_id != _identity(request, body)):
        raise ValueError("request configuration or cache identity differs")


def prepare_request(
    *, item_id: str, cohort: str, model_id: str, template_id: str,
    model_input: Mapping[str, str], tokenizer: TokenCounter, price: PriceSchedule,
) -> RequestSpec:
    """Create the exact bounded request and its complete cache identity."""
    if type(item_id) is not str or len(item_id) > MAX_IDENTIFIER_CHARS:
        raise ValueError("item_id exceeds the mock identifier bound")
    require_identifier(item_id, "item_id")
    if cohort not in {"pilot", "N", "C", "R"}:
        raise ValueError("unknown cohort")
    allowed = {"N": _N_TEMPLATES, "C": _C_TEMPLATES, "R": _R_TEMPLATES,
               "pilot": _N_TEMPLATES | _C_TEMPLATES | _R_TEMPLATES}[cohort]
    if template_id not in allowed:
        raise ValueError("template is not permitted for this cohort")
    if type(tokenizer) is not TokenCounter or type(price) is not PriceSchedule:
        raise TypeError("verified tokenizer and price schedule are required")
    TokenCounter.__post_init__(tokenizer)
    PriceSchedule.__post_init__(price)
    if model_id != tokenizer.model_id or model_id != price.model_id:
        raise ValueError("tokenizer, pricing, and request model must match")
    body = _body(model_id, template_id, model_input, price)
    payload = _canonical(body)
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds the mock byte-safety bound")
    token_count = tokenizer.count_request(payload)
    if type(token_count) is not int or token_count < 1:
        raise ValueError("tokenizer must report a positive integer")
    if token_count > INPUT_LIMIT:
        raise ValueError("input exceeds the tokenizer-measured limit")
    if token_count + OUTPUT_LIMIT > price.max_context_tokens:
        raise ValueError("request exceeds the verified context bound")
    template_sha = prompts.template_sha256(template_id)
    schema_sha = prompts.schema_sha256(template_id)
    decoding_sha = _decoding_sha(body)
    input_bytes = _canonical(dict(model_input))
    text_sha = _sha(input_bytes)
    identity = {
        "cohort": cohort, "item_id": item_id, "model": model_id,
        "provider_route": price.provider_route, "precision": price.precision,
        "template_id": template_id, "template_sha256": template_sha,
        "item_text_sha256": text_sha, "schema_sha256": schema_sha,
        "decoding_sha256": decoding_sha,
        "temperature": 0, "output_limit": OUTPUT_LIMIT,
        "response_format": body["response_format"], "tokenizer_sha256": tokenizer.tokenizer_sha256,
        "input_limit": INPUT_LIMIT, "measured_input_tokens": token_count,
        "pricing_sha256": price.identity, "payload_sha256": _sha(payload),
    }
    return RequestSpec(_sha(_canonical(identity)), _sha(payload), payload, input_bytes, item_id, cohort, model_id,
                       price.provider_route, price.precision, template_id, template_sha, schema_sha, decoding_sha,
                       text_sha, tokenizer.tokenizer_sha256, token_count, price.identity)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    reasoning_tokens: int | None
    billed_usd: str


def _usage(usage: Usage | None) -> tuple[int, int, int | None, int, Fraction] | None:
    if type(usage) is not Usage:
        return None
    if any(type(value) is not int or not 0 <= value <= SQLITE_INT_MAX for value in
           (usage.input_tokens, usage.output_tokens, usage.total_tokens)):
        return None
    if usage.total_tokens != usage.input_tokens + usage.output_tokens:
        return None
    if usage.reasoning_tokens is not None and (
        type(usage.reasoning_tokens) is not int or not 0 <= usage.reasoning_tokens <= usage.output_tokens
    ):
        return None
    try:
        exact_charge = Fraction(_money(usage.billed_usd, "billed amount"))
        charged = _picos(exact_charge)
    except (TypeError, ValueError, OverflowError, MemoryError):
        return None
    return usage.input_tokens, usage.output_tokens, usage.reasoning_tokens, charged, exact_charge


@dataclass(frozen=True, slots=True)
class Returned:
    content: str
    finish_reason: str | None
    model_id: str | None
    provider_route: str | None
    precision: str | None
    usage: Usage | None


def _response_claim(response: object) -> str | None:
    if type(response) is Returned:
        usage = response.usage
    elif type(response) is dict:
        usage = response.get("usage")
        if usage is None and "billed_usd" in response:
            return _claim_record(response["billed_usd"])
    else:
        return _claim_record(response)
    if type(usage) is Usage:
        return _claim_record(usage.billed_usd)
    if type(usage) is dict:
        return _claim_record(usage.get("billed_usd"))
    return _claim_record(usage)


def _response_incident_fields(response: object) -> tuple[str | None, ...]:
    if type(response) is Returned:
        values = (response.content, response.finish_reason, response.model_id,
                  response.provider_route, response.precision)
    elif type(response) is dict:
        values = (response.get("content"), response.get("finish_reason"), response.get("model_id"),
                  response.get("provider_route"), response.get("precision"))
    else:
        values = (response, None, None, None, None)
    return tuple(_claim_record(value) for value in values)


@dataclass(frozen=True, slots=True)
class TransportFailure:
    """Raw mock failure; the ledger validates evidence after dispatch."""

    kind: str
    billed_usd: str | None = None
    evidence_sha256: str | None = None
    no_response_evidence_sha256: str | None = None


def _validate_failure(failure: TransportFailure) -> None:
    if type(failure.kind) is not str or len(failure.kind) > 32 or failure.kind not in {"transport", "rate_limit"}:
        raise ValueError("unknown transport failure")
    if (failure.billed_usd is None) != (failure.evidence_sha256 is None):
        raise ValueError("a known transport charge requires evidence")
    if failure.evidence_sha256 is not None and _evidence(failure.evidence_sha256) is None:
        raise ValueError("invalid transport charge evidence")
    if failure.no_response_evidence_sha256 is not None and _evidence(failure.no_response_evidence_sha256) is None:
        raise ValueError("invalid no-response evidence")
    if (failure.evidence_sha256 is not None
            and failure.evidence_sha256 == failure.no_response_evidence_sha256):
        raise ValueError("billing and no-response evidence must be distinct")


def _failure_fields(failure: object) -> tuple[str | None, object, object]:
    if type(failure) is TransportFailure:
        return _claim_record(failure.billed_usd), failure.evidence_sha256, failure.no_response_evidence_sha256
    if type(failure) is dict:
        return (_claim_record(failure.get("billed_usd")), failure.get("evidence_sha256"),
                failure.get("no_response_evidence_sha256"))
    return _claim_record(failure), None, None


class ScriptedTransport:
    """A bounded sequence of test outcomes. It cannot send a network request.

    Malformed returned objects are passed to the ledger for quarantine.
    """

    def __init__(self, outcomes: Iterable[object]):
        self.outcomes = list(islice(outcomes, HTTP_LIMIT + 1))
        if len(self.outcomes) > HTTP_LIMIT:
            raise ValueError("the scripted transport exceeds the mock outcome bound")
        self.payloads: list[bytes] = []
        self.user_agents: list[str] = []

    def send(self, payload: bytes, user_agent: str) -> object:
        if len(self.payloads) >= HTTP_LIMIT:
            raise RuntimeError("the scripted transport exceeds the mock attempt bound")
        self.payloads.append(payload)
        self.user_agents.append(user_agent)
        if not self.outcomes:
            raise RuntimeError("the scripted transport has no outcome")
        return self.outcomes.pop(0)


@dataclass(frozen=True, slots=True)
class Reservation:
    status: str
    attempt_id: int | None = None
    attempt_index: int | None = None
    reason: str | None = None
    content: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RunOutcome:
    status: str
    reason: str | None = None
    content: str | None = None
    finish_reason: str | None = None
    from_cache: bool = False


_SCHEMA_VERSION = 5
_HARD_FENCE_VERSION = 2_147_483_647
_TABLE_SQL = {
    "account": (
        "CREATE TABLE account (id INTEGER PRIMARY KEY CHECK (id = 1), cap INTEGER NOT NULL, "
        "max_attempts INTEGER NOT NULL, max_retries INTEGER NOT NULL, attempts INTEGER NOT NULL, "
        "spent INTEGER NOT NULL, stop_reason TEXT, last_time INTEGER NOT NULL)"
    ),
    "requests": (
        "CREATE TABLE requests (request_id TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL, "
        "item_id TEXT NOT NULL, cohort TEXT NOT NULL, model_id TEXT NOT NULL, template_id TEXT NOT NULL, "
        "route TEXT NOT NULL, precision TEXT NOT NULL, pricing_sha256 TEXT NOT NULL, "
        "UNIQUE(cohort, item_id, model_id, template_id))"
    ),
    "attempts": (
        "CREATE TABLE attempts (attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL, "
        "attempt_index INTEGER NOT NULL, state TEXT NOT NULL, reserved INTEGER NOT NULL, "
        "charge_ceiling_usd TEXT NOT NULL, charge_claim TEXT, billed INTEGER, "
        "started INTEGER NOT NULL, finished INTEGER, failure_kind TEXT, evidence_sha256 TEXT, "
        "no_response_evidence_sha256 TEXT, billing_at INTEGER, no_response_at INTEGER, "
        "input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, "
        "has_response INTEGER NOT NULL DEFAULT 0, response_content BLOB, finish_reason TEXT, "
        "served_model TEXT, served_route TEXT, served_precision TEXT, "
        "FOREIGN KEY(request_id) REFERENCES requests(request_id))"
    ),
    "model_stops": "CREATE TABLE model_stops (model_id TEXT PRIMARY KEY, reason TEXT NOT NULL)",
    "events": (
        "CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL, "
        "code TEXT NOT NULL, timestamp INTEGER)"
    ),
    "incidents": (
        "CREATE TABLE incidents (sequence INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id INTEGER NOT NULL, "
        "request_id TEXT NOT NULL, kind TEXT NOT NULL, prior_state TEXT NOT NULL, observed_at INTEGER, "
        "charge_claim TEXT, billing_evidence_claim TEXT, no_response_evidence_claim TEXT, "
        "response_content_claim TEXT, response_finish_claim TEXT, response_model_claim TEXT, "
        "response_route_claim TEXT, response_precision_claim TEXT, exposure INTEGER NOT NULL, "
        "exposure_unknown INTEGER NOT NULL DEFAULT 1, "
        "FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id))"
    ),
}
_INDEX_SQL = ("CREATE UNIQUE INDEX one_active_attempt_index ON attempts(request_id,attempt_index) "
              "WHERE state != 'cancelled'")


class _TempTriggerError(RuntimeError):
    pass


class _MainSchemaError(RuntimeError):
    pass


class AccountingLedger:
    """Transactional mock reservations, a shared retry quota and response recovery.

    Older databases are refused rather than silently migrated to a new policy.
    One outstanding sent attempt is a shared dispatch fence, even for already
    open connections. Caller-supplied timestamps are ordered as logical records,
    not verified wall time. A false active-worker attestation could still allow
    a real in-flight request to outlive recovery: live use remains prohibited.
    """

    def __init__(self, connection: sqlite3.Connection, *, cap_usd: str = "10", max_attempts: int = HTTP_LIMIT,
                 max_retries: int | None = None):
        if type(connection) is not sqlite3.Connection or connection.in_transaction:
            raise ValueError("a non-transactional SQLite connection is required")
        if connection.row_factory is not None or connection.text_factory is not str:
            raise ValueError("default SQLite row_factory and text_factory are required")
        if type(max_attempts) is not int or not 1 <= max_attempts <= HTTP_LIMIT:
            raise ValueError("the HTTP ceiling must be between 1 and 1400")
        if max_retries is None:
            raise ValueError("an explicit shared retry ceiling is required")
        if type(max_retries) is not int or not 0 <= max_retries <= max_attempts:
            raise ValueError("the shared retry ceiling must be between 0 and the HTTP ceiling")
        cap_value = _money(cap_usd, "programme cap", positive=True)
        if cap_value > 10:
            raise ValueError("the proposed programme cap cannot exceed $10")
        cap = _cap_picos(cap_value)
        self.db = connection
        self._initialized = False
        self._transaction_active = False
        self._transaction_owner = None
        self._lock = RLock()
        self.db.isolation_level = None
        self.db.execute("PRAGMA busy_timeout = 5000")
        with self._transaction():
            version = self.db.execute("PRAGMA main.user_version").fetchone()[0]
            objects = self._main_objects()
            if version == 0:
                if objects:
                    raise ValueError("refusing to initialize a nonempty unrecognized database")
                for statement in _TABLE_SQL.values():
                    self.db.execute(statement.replace("CREATE TABLE ", "CREATE TABLE main.", 1))
                self.db.execute(_INDEX_SQL.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX main.", 1))
                self.db.execute("INSERT INTO main.account VALUES (1,?,?,?,0,0,NULL,0)",
                                (cap, max_attempts, max_retries))
                self.db.execute(f"PRAGMA main.user_version = {_SCHEMA_VERSION}")
                objects = self._main_objects()
            elif version != _SCHEMA_VERSION:
                raise ValueError("persistent accounting schema is not recognized")
            if objects.get(("index", "one_active_attempt_index")) != _INDEX_SQL:
                raise ValueError("persistent accounting retry index is not recognized")
            expected = {("table", name): sql for name, sql in _TABLE_SQL.items()}
            expected[("index", "one_active_attempt_index")] = _INDEX_SQL
            if objects != expected:
                raise ValueError("persistent accounting schema is not recognized")
            row = self.db.execute("SELECT cap,max_attempts,max_retries FROM main.account WHERE id=1").fetchone()
            if row is None:
                raise ValueError("persistent account row is missing; refusing to reset accounting")
            if row != (cap, max_attempts, max_retries):
                raise ValueError("persistent account policy differs from the requested policy")
            attempts, spent, last_time = self.db.execute(
                "SELECT attempts,spent,last_time FROM main.account WHERE id=1"
            ).fetchone()
            if (any(type(value) is not int for value in (attempts, spent, last_time))
                    or not 0 <= attempts <= max_attempts or not 0 <= spent <= cap
                    or not 0 <= last_time <= SQLITE_INT_MAX):
                raise ValueError("persistent account values are not recognized")
        self._initialized = True

    @contextmanager
    def _transaction(self):
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            self._transaction_active = True
            self._transaction_owner = get_ident()
            try:
                self._check_temp_triggers()
                if self._initialized and self.db.execute("PRAGMA main.user_version").fetchone()[0] != _SCHEMA_VERSION:
                    raise ValueError("persistent accounting schema is fenced or unrecognized")
                if self._initialized:
                    self._check_main_schema()
                yield
                self._check_temp_triggers()
                if self._initialized:
                    self._check_main_schema()
            except (_TempTriggerError, _MainSchemaError) as error:
                self.db.rollback()
                if self._initialized:
                    # SQLite TEMP triggers cannot intercept this main-header write.
                    # It permanently fences every ledger connection on this database.
                    self.db.execute("BEGIN IMMEDIATE")
                    try:
                        self.db.execute(f"PRAGMA main.user_version = {_HARD_FENCE_VERSION}")
                        self.db.commit()
                    except BaseException:
                        self.db.rollback()
                        raise
                    raise ValueError("TEMP triggers or changed main schema; accounting schema is fenced") from error
                if isinstance(error, _TempTriggerError):
                    raise ValueError("TEMP triggers are forbidden on the accounting connection") from error
                raise ValueError("persistent accounting schema is not recognized") from error
            except BaseException:
                self.db.rollback()
                raise
            else:
                self.db.commit()
            finally:
                self._transaction_active = False
                self._transaction_owner = None

    def _check_temp_triggers(self) -> None:
        if self.db.execute("SELECT 1 FROM temp.sqlite_master WHERE type='trigger' LIMIT 1").fetchone():
            raise _TempTriggerError("TEMP trigger on accounting connection")

    def _main_objects(self) -> dict[tuple[str, str], str | None]:
        objects = {}
        for kind, name, sql in self.db.execute("SELECT type,name,sql FROM main.sqlite_master"):
            if name.startswith("sqlite_"):
                continue
            objects[(kind, name)] = sql
            if len(objects) > len(_TABLE_SQL) + 1:
                raise _MainSchemaError("unexpected main schema object")
        return objects

    def _check_main_schema(self) -> None:
        expected = {("table", name): sql for name, sql in _TABLE_SQL.items()}
        expected[("index", "one_active_attempt_index")] = _INDEX_SQL
        if self._main_objects() != expected:
            raise _MainSchemaError("main schema differs from the expected definition")

    def _event(self, request_id: str, code: str, now: int | None) -> None:
        self.db.execute("INSERT INTO main.events(request_id,code,timestamp) VALUES (?,?,?)", (request_id, code, now))

    def _advance_time(self, now: int) -> None:
        """Order caller-supplied timestamps; this is not a trusted clock."""
        _now(now)
        last = self.db.execute("SELECT last_time FROM main.account WHERE id=1").fetchone()[0]
        if now < last:
            raise ValueError("time cannot precede a prior recorded event")
        self.db.execute("UPDATE main.account SET last_time=? WHERE id=1", (now,))

    def _stop(self, reason: str, *, sticky: bool) -> None:
        if sticky:
            self.db.execute(
                "UPDATE main.account SET stop_reason=CASE WHEN stop_reason IS NULL OR "
                "stop_reason IN ('unknown_charge','unknown_usage') THEN ? ELSE stop_reason END WHERE id=1",
                (reason,),
            )
        else:
            self.db.execute("UPDATE main.account SET stop_reason=COALESCE(stop_reason,?) WHERE id=1", (reason,))

    def _quarantine(
        self, attempt_id: int, request_id: str, *, returned: bool, reason: str, now: int | None,
        claim: str | None = None, evidence: str | None = None, no_response: str | None = None,
        billed: int | None = None, response: Returned | None = None,
    ) -> None:
        content = _safe_text(response.content, MAX_RESPONSE_CHARS) if type(response) is Returned else None
        finish = _safe_text(response.finish_reason, _MAX_METADATA_CHARS) if type(response) is Returned else None
        model = _safe_text(response.model_id, _MAX_METADATA_CHARS) if type(response) is Returned else None
        route = _safe_text(response.provider_route, _MAX_METADATA_CHARS) if type(response) is Returned else None
        precision = _safe_text(response.precision, _MAX_METADATA_CHARS) if type(response) is Returned else None
        self.db.execute(
            "UPDATE main.attempts SET state=?,has_response=CASE WHEN ? THEN 1 ELSE has_response END, "
            "finished=COALESCE(finished,?),charge_claim=COALESCE(charge_claim,?), "
            "evidence_sha256=COALESCE(evidence_sha256,?), "
            "no_response_evidence_sha256=COALESCE(no_response_evidence_sha256,?), "
            "billed=COALESCE(billed,?),response_content=COALESCE(response_content,?), "
            "finish_reason=COALESCE(finish_reason,?),served_model=COALESCE(served_model,?), "
            "served_route=COALESCE(served_route,?),served_precision=COALESCE(served_precision,?) "
            "WHERE attempt_id=?",
            ("returned_quarantined" if returned else "failed_quarantined", int(returned), now, claim,
             _evidence(evidence), _evidence(no_response), billed,
             None if content is None else content.encode("utf-8"), finish, model, route, precision, attempt_id),
        )
        self._stop(reason, sticky=True)
        self._event(request_id, reason, now)

    def _late_conflict(
        self, attempt_id: int, *, kind: str, now: int, claim: str | None,
        billing_evidence: object = None, no_response_evidence: object = None,
        response: object = None, returned: bool = False,
    ) -> None:
        """Preserve a contradictory observation without charging it again."""
        row = self.db.execute("SELECT state,request_id,reserved,has_response FROM main.attempts WHERE attempt_id=?",
                              (attempt_id,)).fetchone()
        if row is None:
            raise ValueError("attempt does not exist")
        try:
            self._advance_time(now)
            observed = now
        except ValueError:
            observed = None
        prior_exposure = 0
        for (value,) in self.db.execute("SELECT exposure FROM main.incidents WHERE attempt_id=?", (attempt_id,)):
            if type(value) is not int or not 0 <= value <= SQLITE_INT_MAX:
                raise ValueError("persistent incident exposure is not a nonnegative SQLite-range integer")
            prior_exposure += value
        reported = _claim_picos(claim)
        base = 0 if row[0] == "cancelled" else row[2]
        target = max(row[2], 0 if reported is None else reported)
        exposure = max(0, target - base - prior_exposure)
        if row[0] == "cancelled":
            if returned:
                self.db.execute("UPDATE main.attempts SET has_response=1 WHERE attempt_id=?", (attempt_id,))
            self._stop("conflicting_outcome", sticky=True)
            self._event(row[1], "conflicting_outcome", observed)
        else:
            self._quarantine(attempt_id, row[1], returned=returned or row[3] == 1,
                             reason="conflicting_outcome", now=observed, claim=claim,
                             response=response if type(response) is Returned else None)
        fields = _response_incident_fields(response) if returned else (None, None, None, None, None)
        self.db.execute(
            "INSERT INTO main.incidents(attempt_id,request_id,kind,prior_state,observed_at,charge_claim,"
            "billing_evidence_claim,no_response_evidence_claim,response_content_claim,response_finish_claim,"
            "response_model_claim,response_route_claim,response_precision_claim,exposure) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (attempt_id, row[1], kind, row[0], observed, claim, _claim_record(billing_evidence),
             _claim_record(no_response_evidence), *fields, exposure),
        )

    def _add_spend(self, charge: int) -> str | None:
        cap, spent = self.db.execute("SELECT cap,spent FROM main.account WHERE id=1").fetchone()
        if type(spent) is not int or spent < 0 or charge > SQLITE_INT_MAX - spent:
            return "aggregate_out_of_range"
        if spent > cap or charge > cap - spent:
            return "spend_exceeds_cap"
        self.db.execute("UPDATE main.account SET spent=? WHERE id=1", (spent + charge,))
        return None

    def _clear_unknown_stop(self) -> None:
        if not self.db.execute(
            "SELECT 1 FROM main.attempts WHERE state IN "
            "('failed_unknown','returned_unknown','failed_quarantined','returned_quarantined') LIMIT 1"
        ).fetchone():
            self.db.execute("UPDATE main.account SET stop_reason=NULL WHERE id=1 "
                            "AND stop_reason IN ('unknown_charge','unknown_usage')")

    def _record_post_dispatch_failure(
        self, attempt_id: int, *, returned: bool, now: int | None,
        failure: object = None, response: object = None, billing_evidence: object = None,
    ) -> None:
        """Best-effort quarantine; an outstanding sent row remains the fallback fence."""
        try:
            if returned:
                claim, evidence, no_response = _response_claim(response), billing_evidence, None
            else:
                claim, evidence, no_response = _failure_fields(failure)
        except (MemoryError, OverflowError, ValueError, TypeError):
            claim, evidence, no_response = '{"type":"unavailable"}', None, None
        try:
            detail = json.dumps({
                "charge_claim": claim, "billing_evidence": _claim_record(evidence),
                "no_response_evidence": _claim_record(no_response),
                "response_fields": _response_incident_fields(response) if returned else None,
            }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            if len(detail) > 32_768:
                detail = json.dumps({"charge_claim": claim, "detail_truncated": True}, ensure_ascii=True,
                                    sort_keys=True, separators=(",", ":"))
        except (MemoryError, OverflowError, ValueError, TypeError):
            detail = claim if type(claim) is str else '{"type":"unavailable"}'
        with self._transaction():
            row = self.db.execute("SELECT state,request_id,has_response FROM main.attempts WHERE attempt_id=?",
                                  (attempt_id,)).fetchone()
            if row is None:
                raise ValueError("no dispatched attempt can be quarantined")
            try:
                self._advance_time(now)
                recorded = now
            except ValueError:
                recorded = None
            if row[0] in {"cancelled", "reserved"}:
                if returned:
                    self.db.execute("UPDATE main.attempts SET has_response=1 WHERE attempt_id=?", (attempt_id,))
                self._stop("persistence_failure", sticky=True)
                # An outcome for an unmarked attempt makes the HTTP count
                # uncertain. If the incident itself cannot be persisted, fence
                # the whole schema rather than report the count as complete.
                self.db.execute(f"PRAGMA main.user_version = {_HARD_FENCE_VERSION}")
            else:
                self._quarantine(attempt_id, row[1], returned=returned or row[2] == 1,
                                 reason="persistence_failure", now=recorded,
                                 claim=claim, evidence=evidence, no_response=no_response,
                                 response=response if type(response) is Returned else None)
            self._event(row[1], "observation:" + detail, recorded)

    def _attempt_exists(self, attempt_id: int) -> bool:
        try:
            _attempt_id(attempt_id)
        except ValueError:
            return False
        with self._transaction():
            return self.db.execute("SELECT 1 FROM main.attempts WHERE attempt_id=?", (attempt_id,)).fetchone() is not None

    def snapshot(self) -> dict[str, int | str | None]:
        """Return one transactionally consistent view of the persistent account.

        The legacy ``http_attempts`` value counts only attempts marked sent; it
        is not an independently reconciled provider count. An outcome attached
        to a previously unmarked/cancelled attempt makes that count unverified.
        """
        with self._lock:
            if not self.db.in_transaction:
                with self._transaction():
                    return self._snapshot_in_transaction()
            if not self._transaction_active or self._transaction_owner != get_ident():
                raise ValueError("external SQLite transactions are not supported")
            self._check_temp_triggers()
            return self._snapshot_in_transaction()

    def _snapshot_in_transaction(self) -> dict[str, int | str | None]:
        cap, limit, retry_limit, attempts, spent, stop, last_time = self.db.execute(
            "SELECT cap,max_attempts,max_retries,attempts,spent,stop_reason,last_time FROM main.account WHERE id=1"
        ).fetchone()
        def exposure_sum(query: str) -> int:
            total = 0
            for (value,) in self.db.execute(query):
                if type(value) is not int or not 0 <= value <= SQLITE_INT_MAX:
                    raise ValueError("persistent exposure is not a nonnegative SQLite-range integer")
                total += value
            return total

        # SQLite SUM can overflow even when each individual exposure is valid.
        reserved = exposure_sum(
            "SELECT reserved FROM main.attempts WHERE state IN "
            "('reserved','sent','failed_unknown','returned_unknown','failed_quarantined','returned_quarantined')"
        )
        reserved += exposure_sum("SELECT exposure FROM main.incidents")
        retry_attempts, retry_pending = self.db.execute(
            "SELECT COUNT(*) FILTER (WHERE state NOT IN ('reserved','cancelled')), "
            "COUNT(*) FILTER (WHERE state='reserved') FROM main.attempts WHERE attempt_index > 1"
        ).fetchone()
        exposure_unknown = bool(self.db.execute(
            "SELECT 1 FROM main.attempts WHERE state IN "
            "('failed_unknown','returned_unknown','failed_quarantined','returned_quarantined') LIMIT 1"
        ).fetchone() or self.db.execute(
            "SELECT 1 FROM main.incidents WHERE exposure_unknown=1 LIMIT 1"
        ).fetchone())
        attempts_unverified = bool(self.db.execute(
            "SELECT 1 FROM main.incidents WHERE prior_state IN ('reserved','cancelled') LIMIT 1"
        ).fetchone())
        return {"cap_picos": cap, "http_limit": limit, "http_attempts": attempts,
                "marked_sent_attempts": attempts, "http_attempts_unverified": attempts_unverified,
                "retry_limit": retry_limit, "retry_attempts": retry_attempts, "retry_pending": retry_pending,
                "spent_picos": spent, "reserved_picos": reserved, "exposure_unknown": exposure_unknown,
                "stop_reason": stop,
                "last_event_time": last_time,
                "recovery_required": bool(self.db.execute(
                    "SELECT 1 FROM main.attempts WHERE state='sent' LIMIT 1"
                ).fetchone())}

    def reserve(self, request: RequestSpec, price: PriceSchedule, *, now: int) -> Reservation:
        if type(request) is not RequestSpec or type(price) is not PriceSchedule:
            raise TypeError("request and price must be typed")
        _now(now)
        PriceSchedule.__post_init__(price)
        _validate_request(request, price)
        with self._transaction():
            self._advance_time(now)
            account = self.snapshot()
            if account["stop_reason"] is not None:
                self._event(request.request_id, "account_stopped", now)
                return Reservation("blocked", reason="account_stopped")
            if account["recovery_required"]:
                self._event(request.request_id, "recovery_required", now)
                return Reservation("blocked", reason="recovery_required")
            if self.db.execute("SELECT 1 FROM main.model_stops WHERE model_id=?", (request.model_id,)).fetchone():
                self._event(request.request_id, "model_stopped", now)
                return Reservation("blocked", reason="model_stopped")
            old = self.db.execute(
                "SELECT payload_sha256,item_id,cohort,model_id,template_id,route,precision,pricing_sha256 FROM main.requests WHERE request_id=?",
                (request.request_id,),
            ).fetchone()
            wanted = (request.payload_sha256, request.item_id, request.cohort, request.model_id,
                      request.template_id, request.provider_route, request.precision, request.pricing_sha256)
            if old is not None and old != wanted:
                raise ValueError("persistent request identity mismatch")
            assigned = self.db.execute(
                "SELECT request_id FROM main.requests WHERE cohort=? AND item_id=? AND model_id=? AND template_id=?",
                (request.cohort, request.item_id, request.model_id, request.template_id),
            ).fetchone()
            if assigned is not None and assigned[0] != request.request_id:
                self.db.execute("UPDATE main.account SET stop_reason='assignment_identity_conflict' WHERE id=1")
                self._event(request.request_id, "assignment_identity_conflict", now)
                return Reservation("blocked", reason="assignment_identity_conflict")
            previous = self.db.execute(
                "SELECT attempt_id,attempt_index,state,finished,response_content,finish_reason,"
                "billing_at,no_response_at "
                "FROM main.attempts WHERE request_id=? AND state != 'cancelled' ORDER BY attempt_index DESC LIMIT 1", (request.request_id,),
            ).fetchone()
            if previous and previous[2] == "returned":
                self._event(request.request_id, "cache_reuse", now)
                return Reservation("cached", content=bytes(previous[4]).decode("utf-8"), finish_reason=previous[5])
            if previous and previous[2] != "failed_known":
                self._event(request.request_id, "request_not_retryable", now)
                return Reservation("blocked", reason="request_not_retryable")
            index = 1 if previous is None else previous[1] + 1
            if index > 2:
                self._event(request.request_id, "retry_limit", now)
                return Reservation("blocked", reason="retry_limit")
            if previous and (previous[3] is None or previous[6] is None or previous[7] is None
                             or now < max(previous[3] + RETRY_DELAY_SECONDS, previous[6], previous[7])):
                self._event(request.request_id, "retry_delay", now)
                return Reservation("blocked", reason="retry_delay")
            if index > 1 and account["retry_attempts"] + account["retry_pending"] >= account["retry_limit"]:
                self._event(request.request_id, "retry_budget", now)
                return Reservation("blocked", reason="retry_budget")
            active = self.db.execute(
                "SELECT r.model_id FROM main.attempts a JOIN main.requests r USING(request_id) "
                "WHERE a.state IN ('reserved','sent')"
            ).fetchall()
            if any(model == request.model_id for (model,) in active):
                self._event(request.request_id, "model_busy", now)
                return Reservation("blocked", reason="model_busy")
            if len(active) >= 2:
                self._event(request.request_id, "concurrency_limit", now)
                return Reservation("blocked", reason="concurrency_limit")
            pending = self.db.execute("SELECT COUNT(*) FROM main.attempts WHERE state='reserved'").fetchone()[0]
            if account["http_attempts"] + pending >= account["http_limit"]:
                self._event(request.request_id, "attempt_limit", now)
                return Reservation("blocked", reason="attempt_limit")
            if request.cohort == "pilot":
                returned = self.db.execute(
                    "SELECT COUNT(*) FROM main.attempts a JOIN main.requests r USING(request_id) "
                    "WHERE r.cohort='pilot' AND r.model_id=? AND a.has_response=1", (request.model_id,),
                ).fetchone()[0]
                if returned >= PILOT_RETURN_LIMIT:
                    self._event(request.request_id, "pilot_return_limit", now)
                    return Reservation("blocked", reason="pilot_return_limit")
            if account["spent_picos"] + account["reserved_picos"] + price.reservation_picos > account["cap_picos"]:
                self._event(request.request_id, "cap_blocked", now)
                return Reservation("blocked", reason="cap_blocked")
            if old is None:
                self.db.execute("INSERT INTO main.requests VALUES (?,?,?,?,?,?,?,?,?)", (request.request_id, *wanted))
            cursor = self.db.execute(
                "INSERT INTO main.attempts(request_id,attempt_index,state,reserved,charge_ceiling_usd,started) "
                "VALUES (?,?,?,?,?,?)",
                (request.request_id, index, "reserved", price.reservation_picos,
                 price.independent_charge_ceiling_usd, now),
            )
            self._event(request.request_id, "reserved", now)
            return Reservation("reserved", cursor.lastrowid, index)

    def mark_sent(self, attempt_id: int, *, now: int) -> None:
        _attempt_id(attempt_id)
        _now(now)
        with self._transaction():
            row = self.db.execute("SELECT state,request_id,started FROM main.attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row[0] != "reserved":
                raise ValueError("only a reserved attempt can be dispatched")
            if now < row[2]:
                raise ValueError("dispatch time cannot precede the reservation")
            if self.db.execute("SELECT 1 FROM main.attempts WHERE state='sent' LIMIT 1").fetchone():
                raise ValueError("an outstanding sent attempt fences dispatch")
            count, limit, stop = self.db.execute("SELECT attempts,max_attempts,stop_reason FROM main.account WHERE id=1").fetchone()
            if stop is not None or count >= limit:
                raise ValueError("account cannot dispatch another request")
            self._advance_time(now)
            self.db.execute("UPDATE main.attempts SET state='sent',started=? WHERE attempt_id=?", (now, attempt_id))
            self.db.execute("UPDATE main.account SET attempts=attempts+1 WHERE id=1")
            self._event(row[1], "sent", now)

    def fail_transport(self, attempt_id: int, failure: TransportFailure, *, now: int) -> str:
        try:
            return self._fail_transport(attempt_id, failure, now=now)
        except ValueError:
            if not self._attempt_exists(attempt_id):
                raise
            self._record_post_dispatch_failure(attempt_id, returned=False, now=now, failure=failure)
            return "account_stopped"
        except Exception:
            self._record_post_dispatch_failure(attempt_id, returned=False, now=now, failure=failure)
            return "account_stopped"

    def _fail_transport(self, attempt_id: int, failure: TransportFailure, *, now: int) -> str:
        _attempt_id(attempt_id)
        claim, evidence, no_response = _failure_fields(failure)
        with self._transaction():
            row = self.db.execute(
                "SELECT a.state,a.reserved,a.attempt_index,r.model_id,a.started,a.request_id,"
                "a.charge_ceiling_usd FROM main.attempts a "
                "JOIN main.requests r USING(request_id) WHERE a.attempt_id=?", (attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("attempt does not exist")
            if row[0] != "sent":
                self._late_conflict(attempt_id, kind="late_transport_failure", now=now, claim=claim,
                                    billing_evidence=evidence, no_response_evidence=no_response)
                return "account_stopped"
            try:
                self._advance_time(now)
                if now < row[4]:
                    raise ValueError("failure time cannot precede dispatch")
            except ValueError:
                self._quarantine(attempt_id, row[5], returned=False, reason="invalid_timestamp", now=None,
                                 claim=claim, evidence=evidence, no_response=no_response)
                return "account_stopped"
            try:
                if type(failure) is not TransportFailure:
                    raise TypeError("failure must be TransportFailure")
                _validate_failure(failure)
            except (TypeError, ValueError):
                self._quarantine(attempt_id, row[5], returned=False, reason="invalid_transport_evidence", now=now,
                                 claim=claim, evidence=evidence, no_response=no_response)
                return "account_stopped"
            if failure.billed_usd is None:
                self.db.execute(
                    "UPDATE main.attempts SET state='failed_unknown',finished=?,failure_kind=?,"
                    "no_response_evidence_sha256=?,no_response_at=? WHERE attempt_id=?",
                    (now, failure.kind, no_response, now if no_response is not None else None, attempt_id),
                )
                self._stop("unknown_charge", sticky=False)
                self._event(row[5], "unknown_charge", now)
                return "unknown_charge"
            if evidence is None:
                self._quarantine(attempt_id, row[5], returned=False, reason="invalid_transport_evidence", now=now,
                                 claim=claim, no_response=no_response)
                return "account_stopped"
            try:
                exact = Fraction(_money(failure.billed_usd, "transport charge"))
                charge = _picos(exact)
                ceiling = Fraction(_money(row[6], "independent charge ceiling"))
            except (TypeError, ValueError, OverflowError, MemoryError) as error:
                reason = "charge_out_of_range" if "accounting range" in str(error) else "invalid_charge"
                self._quarantine(attempt_id, row[5], returned=False, reason=reason, now=now,
                                 claim=claim, evidence=evidence, no_response=no_response)
                return "account_stopped"
            if exact > ceiling or charge > row[1]:
                self._quarantine(attempt_id, row[5], returned=False, reason="charge_exceeded_ceiling", now=now,
                                 claim=claim, evidence=evidence, no_response=no_response, billed=charge)
                return "account_stopped"
            problem = self._add_spend(charge)
            if problem is not None:
                self._quarantine(attempt_id, row[5], returned=False, reason=problem, now=now,
                                 claim=claim, evidence=evidence, no_response=no_response, billed=charge)
                return "account_stopped"
            state = "failed_known" if no_response is not None else "failed_known_ambiguous"
            self.db.execute(
                "UPDATE main.attempts SET state=?,finished=?,failure_kind=?,billed=?,evidence_sha256=?,"
                "no_response_evidence_sha256=?,charge_claim=?,billing_at=?,no_response_at=? WHERE attempt_id=?",
                (state, now, failure.kind, charge, evidence, no_response, claim, now,
                 now if no_response is not None else None, attempt_id),
            )
            self._event(row[5], state, now)
            if row[2] == 2:
                self.db.execute("INSERT OR REPLACE INTO main.model_stops VALUES (?,?)", (row[3], "two_transport_failures"))
                return "unavailable"
            return "retry_after_delay" if state == "failed_known" else "response_status_unknown"

    def reconcile_transport(
        self, attempt_id: int, *, billed_usd: str, evidence_sha256: str,
        no_response_evidence_sha256: str | None = None, now: int,
    ) -> None:
        """Record caller-supplied billing and optional distinct non-return evidence."""
        failure = TransportFailure("transport", billed_usd, evidence_sha256, no_response_evidence_sha256)
        try:
            self._reconcile_transport(attempt_id, billed_usd=billed_usd, evidence_sha256=evidence_sha256,
                                      no_response_evidence_sha256=no_response_evidence_sha256, now=now)
        except ValueError:
            if not self._attempt_exists(attempt_id):
                raise
            self._record_post_dispatch_failure(attempt_id, returned=False, now=now, failure=failure)
        except Exception:
            self._record_post_dispatch_failure(attempt_id, returned=False, now=now, failure=failure)

    def _reconcile_transport(
        self, attempt_id: int, *, billed_usd: str, evidence_sha256: str,
        no_response_evidence_sha256: str | None = None, now: int,
    ) -> None:
        _attempt_id(attempt_id)
        claim = _claim_record(billed_usd)
        with self._transaction():
            row = self.db.execute(
                "SELECT a.state,a.reserved,a.attempt_index,r.model_id,a.no_response_evidence_sha256,"
                "a.no_response_at,a.request_id,a.charge_ceiling_usd FROM main.attempts a "
                "JOIN main.requests r USING(request_id) WHERE a.attempt_id=?", (attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("attempt does not exist")
            if row[0] != "failed_unknown":
                self._late_conflict(attempt_id, kind="conflicting_transport_reconciliation", now=now, claim=claim,
                                    billing_evidence=evidence_sha256,
                                    no_response_evidence=no_response_evidence_sha256)
                return
            try:
                self._advance_time(now)
            except ValueError:
                self._quarantine(attempt_id, row[6], returned=False, reason="invalid_timestamp", now=None,
                                 claim=claim, evidence=evidence_sha256, no_response=no_response_evidence_sha256)
                return
            proof = row[4] or no_response_evidence_sha256
            if (_evidence(evidence_sha256) is None
                    or (no_response_evidence_sha256 is not None and _evidence(no_response_evidence_sha256) is None)
                    or (row[4] is not None and no_response_evidence_sha256 not in {None, row[4]})
                    or proof == evidence_sha256):
                self._quarantine(attempt_id, row[6], returned=False, reason="invalid_transport_evidence", now=now,
                                 claim=claim, evidence=evidence_sha256, no_response=no_response_evidence_sha256)
                return
            try:
                exact = Fraction(_money(billed_usd, "transport charge"))
                charge = _picos(exact)
                ceiling = Fraction(_money(row[7], "independent charge ceiling"))
            except (TypeError, ValueError, OverflowError, MemoryError) as error:
                reason = "charge_out_of_range" if "accounting range" in str(error) else "invalid_charge"
                self._quarantine(attempt_id, row[6], returned=False, reason=reason, now=now,
                                 claim=claim, evidence=evidence_sha256, no_response=proof)
                return
            if exact > ceiling or charge > row[1]:
                self._quarantine(attempt_id, row[6], returned=False, reason="charge_exceeded_ceiling", now=now,
                                 claim=claim, evidence=evidence_sha256, no_response=proof, billed=charge)
                return
            problem = self._add_spend(charge)
            if problem is not None:
                self._quarantine(attempt_id, row[6], returned=False, reason=problem, now=now,
                                 claim=claim, evidence=evidence_sha256, no_response=proof, billed=charge)
                return
            state = "failed_known" if proof is not None else "failed_known_ambiguous"
            self.db.execute(
                "UPDATE main.attempts SET state=?,billed=?,evidence_sha256=?,no_response_evidence_sha256=?,"
                "charge_claim=?,billing_at=?,no_response_at=? WHERE attempt_id=?",
                (state, charge, evidence_sha256, proof, claim, now,
                 row[5] if row[4] is not None else (now if proof is not None else None), attempt_id),
            )
            self._event(row[6], "transport_reconciled", now)
            self._clear_unknown_stop()
            if row[2] == 2:
                self.db.execute("INSERT OR REPLACE INTO main.model_stops VALUES (?,?)", (row[3], "two_transport_failures"))

    def confirm_no_response(self, attempt_id: int, *, evidence_sha256: str, now: int) -> None:
        """Record a distinct caller-supplied non-return digest and logical time."""
        _attempt_id(attempt_id)
        with self._transaction():
            row = self.db.execute("SELECT state,evidence_sha256,request_id FROM main.attempts WHERE attempt_id=?",
                                  (attempt_id,)).fetchone()
            if row is None or row[0] != "failed_known_ambiguous":
                raise ValueError("attempt does not have a reconciled ambiguous response")
            try:
                self._advance_time(now)
            except ValueError:
                self._quarantine(attempt_id, row[2], returned=False, reason="invalid_timestamp", now=None,
                                 no_response=evidence_sha256)
                return
            if _evidence(evidence_sha256) is None or evidence_sha256 == row[1]:
                self._quarantine(attempt_id, row[2], returned=False, reason="invalid_no_response_evidence", now=now,
                                 no_response=evidence_sha256)
                return
            self.db.execute("UPDATE main.attempts SET state='failed_known',no_response_evidence_sha256=?,"
                            "no_response_at=? WHERE attempt_id=?", (evidence_sha256, now, attempt_id))
            self._event(row[2], "no_response_confirmed", now)

    def complete(self, attempt_id: int, response: Returned, price: PriceSchedule, *, now: int) -> str:
        try:
            return self._complete(attempt_id, response, price, now=now)
        except ValueError:
            if not self._attempt_exists(attempt_id):
                raise
            self._record_post_dispatch_failure(attempt_id, returned=True, now=now, response=response)
            return "account_stopped"
        except Exception:
            self._record_post_dispatch_failure(attempt_id, returned=True, now=now, response=response)
            return "account_stopped"

    def _complete(self, attempt_id: int, response: Returned, price: PriceSchedule, *, now: int) -> str:
        _attempt_id(attempt_id)
        claim = _response_claim(response)
        with self._transaction():
            row = self.db.execute(
                "SELECT a.state,a.reserved,r.model_id,r.route,r.precision,r.pricing_sha256,a.started,"
                "a.request_id,a.charge_ceiling_usd "
                "FROM main.attempts a JOIN main.requests r USING(request_id) WHERE a.attempt_id=?", (attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("attempt does not exist")
            if row[0] != "sent":
                self._late_conflict(attempt_id, kind="late_returned", now=now, claim=claim,
                                    response=response, returned=True)
                return "account_stopped"
            try:
                self._advance_time(now)
                if now < row[6]:
                    raise ValueError("response time cannot precede dispatch")
            except ValueError:
                self._quarantine(attempt_id, row[7], returned=True, reason="invalid_timestamp", now=None,
                                 claim=claim, response=response)
                return "account_stopped"
            try:
                if type(response) is not Returned or type(price) is not PriceSchedule:
                    raise TypeError("a returned response and price schedule are required")
                PriceSchedule.__post_init__(price)
                if row[5] != price.identity:
                    raise ValueError("pricing identity differs")
            except (TypeError, ValueError, OverflowError, MemoryError):
                self._quarantine(attempt_id, row[7], returned=True, reason="invalid_response_or_pricing", now=now,
                                 claim=claim, response=response)
                return "account_stopped"
            content = _safe_text(response.content, MAX_RESPONSE_CHARS)
            finish = _safe_text(response.finish_reason, _MAX_METADATA_CHARS)
            model = _safe_text(response.model_id, _MAX_METADATA_CHARS)
            route = _safe_text(response.provider_route, _MAX_METADATA_CHARS)
            precision = _safe_text(response.precision, _MAX_METADATA_CHARS)
            if content is None or (response.finish_reason is not None and finish is None):
                self._quarantine(attempt_id, row[7], returned=True, reason="returned_unpersistable", now=now,
                                 claim=claim, response=response)
                return "returned_unpersistable"
            if model is None or route is None or precision is None:
                self._quarantine(attempt_id, row[7], returned=True, reason="route_unknown", now=now,
                                 claim=claim, response=response)
                return "route_unknown"
            self.db.execute(
                "UPDATE main.attempts SET has_response=1,response_content=?,finish_reason=?,served_model=?,"
                "served_route=?,served_precision=?,finished=?,charge_claim=? WHERE attempt_id=?",
                (content.encode("utf-8"), finish, model, route, precision, now, claim, attempt_id),
            )
            if response.usage is None:
                self.db.execute("UPDATE main.attempts SET state='returned_unknown' WHERE attempt_id=?", (attempt_id,))
                self._stop("unknown_usage", sticky=False)
                self._event(row[7], "unknown_usage", now)
                return "unknown_usage"
            usage = _usage(response.usage)
            if usage is None:
                self._quarantine(attempt_id, row[7], returned=True, reason="invalid_usage", now=now,
                                 claim=claim, response=response)
                return "unknown_usage"
            return self._settle_response(attempt_id, row, usage, price, now=now)

    def _settle_response(self, attempt_id: int, row: tuple, usage: tuple, price: PriceSchedule, *, now: int) -> str:
        input_tokens, output_tokens, reasoning_tokens, charge, exact_charge = usage
        try:
            ceiling = Fraction(_money(row[8], "independent charge ceiling"))
            mismatch = (input_tokens > INPUT_LIMIT or output_tokens > OUTPUT_LIMIT
                        or output_tokens > price.max_billable_output_tokens
                        or input_tokens + output_tokens > price.max_context_tokens
                        or charge > row[1] or exact_charge > ceiling
                        or exact_charge > price.upper_usd(input_tokens, output_tokens))
        except (TypeError, ValueError, OverflowError, MemoryError):
            self._quarantine(attempt_id, row[7], returned=True, reason="invalid_charge", now=now, billed=charge)
            return "accounting_failed"
        if mismatch:
            self._quarantine(attempt_id, row[7], returned=True, reason="usage_or_pricing_mismatch", now=now,
                             billed=charge)
            return "accounting_failed"
        served = self.db.execute("SELECT served_model,served_route,served_precision FROM main.attempts WHERE attempt_id=?",
                                 (attempt_id,)).fetchone()
        if any(value is None for value in served):
            self._quarantine(attempt_id, row[7], returned=True, reason="route_unknown", now=now, billed=charge)
            return "route_unknown"
        problem = self._add_spend(charge)
        if problem is not None:
            self._quarantine(attempt_id, row[7], returned=True, reason=problem, now=now, billed=charge)
            return "accounting_failed"
        self.db.execute("UPDATE main.attempts SET billed=?,input_tokens=?,output_tokens=?,reasoning_tokens=?,billing_at=? "
                        "WHERE attempt_id=?", (charge, input_tokens, output_tokens, reasoning_tokens, now, attempt_id))
        if served != (row[2], row[3], row[4]):
            self.db.execute("UPDATE main.attempts SET state='route_mismatch' WHERE attempt_id=?", (attempt_id,))
            self.db.execute("INSERT OR REPLACE INTO main.model_stops VALUES (?,?)", (row[2], "route_mismatch"))
            self._event(row[7], "route_mismatch", now)
            return "route_mismatch"
        self.db.execute("UPDATE main.attempts SET state='returned' WHERE attempt_id=?", (attempt_id,))
        self._event(row[7], "returned", now)
        return "returned"

    def record_returned_unpersistable(self, attempt_id: int, *, now: int, response: Returned | None = None) -> None:
        """Record that a response arrived even when its contents could not be persisted."""
        _attempt_id(attempt_id)
        claim = _response_claim(response)
        with self._transaction():
            row = self.db.execute("SELECT state,started,request_id FROM main.attempts WHERE attempt_id=?",
                                  (attempt_id,)).fetchone()
            if row is None:
                raise ValueError("attempt does not exist")
            if row[0] != "sent":
                self._late_conflict(attempt_id, kind="late_unpersistable_response", now=now, claim=claim,
                                    response=response, returned=True)
                return
            try:
                self._advance_time(now)
                if now < row[1]:
                    raise ValueError("response time cannot precede dispatch")
                reason, recorded = "returned_unpersistable", now
            except ValueError:
                reason, recorded = "invalid_timestamp", None
            self._quarantine(attempt_id, row[2], returned=True, reason=reason, now=recorded,
                             claim=claim, response=response)

    def reconcile_response(self, attempt_id: int, usage: Usage, price: PriceSchedule, *, evidence_sha256: str,
                           now: int) -> str:
        try:
            return self._reconcile_response(attempt_id, usage, price, evidence_sha256=evidence_sha256, now=now)
        except ValueError:
            if not self._attempt_exists(attempt_id):
                raise
            self._record_post_dispatch_failure(attempt_id, returned=True, now=now,
                                               response={"usage": usage}, billing_evidence=evidence_sha256)
            return "account_stopped"
        except Exception:
            self._record_post_dispatch_failure(attempt_id, returned=True, now=now,
                                               response={"usage": usage}, billing_evidence=evidence_sha256)
            return "account_stopped"

    def _reconcile_response(self, attempt_id: int, usage: Usage, price: PriceSchedule, *, evidence_sha256: str,
                            now: int) -> str:
        _attempt_id(attempt_id)
        claim = _response_claim({"usage": usage})
        with self._transaction():
            row = self.db.execute(
                "SELECT a.state,a.reserved,r.model_id,r.route,r.precision,r.pricing_sha256,a.started,"
                "a.request_id,a.charge_ceiling_usd "
                "FROM main.attempts a JOIN main.requests r USING(request_id) WHERE a.attempt_id=?", (attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("attempt does not exist")
            if row[0] != "returned_unknown":
                self._late_conflict(attempt_id, kind="conflicting_response_reconciliation", now=now, claim=claim,
                                    billing_evidence=evidence_sha256, returned=True)
                return "account_stopped"
            try:
                self._advance_time(now)
            except ValueError:
                self._quarantine(attempt_id, row[7], returned=True, reason="invalid_timestamp", now=None,
                                 claim=claim, evidence=evidence_sha256)
                return "account_stopped"
            try:
                if type(price) is not PriceSchedule or _evidence(evidence_sha256) is None:
                    raise ValueError("a price schedule and usage evidence are required")
                PriceSchedule.__post_init__(price)
                if row[5] != price.identity:
                    raise ValueError("pricing identity differs")
            except (TypeError, ValueError, OverflowError, MemoryError):
                self._quarantine(attempt_id, row[7], returned=True, reason="invalid_response_or_pricing", now=now,
                                 claim=claim, evidence=evidence_sha256)
                return "account_stopped"
            parsed = _usage(usage)
            if parsed is None:
                self._quarantine(attempt_id, row[7], returned=True, reason="invalid_usage", now=now,
                                 claim=claim, evidence=evidence_sha256)
                return "unknown_usage"
            self.db.execute("UPDATE main.attempts SET evidence_sha256=?,charge_claim=? WHERE attempt_id=?",
                            (evidence_sha256, claim, attempt_id))
            status = self._settle_response(attempt_id, row, parsed, price, now=now)
            if status in {"returned", "route_mismatch"}:
                self._clear_unknown_stop()
            return status

    def recover_interrupted(self, *, confirmed_no_active_workers: bool, now: int) -> int:
        """Mark sent requests as potentially billable after an independently confirmed stop."""
        if confirmed_no_active_workers is not True:
            raise ValueError("active-worker absence must be confirmed before recovery")
        with self._transaction():
            rows = self.db.execute("SELECT attempt_id,request_id,started FROM main.attempts WHERE state='sent'").fetchall()
            try:
                self._advance_time(now)
                if rows and now < max(row[2] for row in rows):
                    raise ValueError("recovery time cannot precede dispatch")
            except ValueError:
                if not rows:
                    raise
                for attempt_id, request_id, _ in rows:
                    self._quarantine(attempt_id, request_id, returned=False, reason="invalid_timestamp", now=None)
                return len(rows)
            for attempt_id, request_id, _ in rows:
                self.db.execute("UPDATE main.attempts SET state='failed_unknown',finished=?,failure_kind='transport' "
                                "WHERE attempt_id=?", (now, attempt_id))
                self._event(request_id, "interrupted", now)
            if rows:
                self._stop("unknown_charge", sticky=False)
            return len(rows)

    def cancel_unsent(self, attempt_id: int, *, now: int) -> None:
        """Release a reservation only when the request was never marked sent."""
        _attempt_id(attempt_id)
        _now(now)
        with self._transaction():
            row = self.db.execute("SELECT state,request_id FROM main.attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row[0] != "reserved":
                raise ValueError("only an unsent reservation can be cancelled")
            self._advance_time(now)
            changed = self.db.execute("UPDATE main.attempts SET state='cancelled' WHERE attempt_id=? AND state='reserved'",
                                      (attempt_id,)).rowcount
            if changed != 1:
                raise ValueError("only an unsent reservation can be cancelled")
            self._event(row[1], "cancelled", now)


def run_mock(
    request: RequestSpec, price: PriceSchedule, ledger: AccountingLedger, transport: ScriptedTransport,
    *, clock: Callable[[], int] | None = None, sleep: Callable[[int], None] = time.sleep,
) -> RunOutcome:
    """Exercise the complete bounded path with a scripted, non-network transport."""
    if type(transport) is not ScriptedTransport:
        raise TypeError("this development runner accepts only the scripted transport")
    clock = clock or (lambda: int(time.time()))

    def post_dispatch_time() -> int | None:
        try:
            return clock()
        except Exception:
            return None

    while True:
        reservation = ledger.reserve(request, price, now=clock())
        if reservation.status == "cached":
            return RunOutcome("returned", content=reservation.content, finish_reason=reservation.finish_reason,
                              from_cache=True)
        if reservation.status != "reserved":
            return RunOutcome("blocked", reason=reservation.reason)
        try:
            ledger.mark_sent(reservation.attempt_id, now=clock())
        except ValueError:
            try:
                ledger.cancel_unsent(reservation.attempt_id, now=clock())
            except ValueError:
                pass
            return RunOutcome("blocked", reason="dispatch_fenced")
        try:
            result = transport.send(request.payload, USER_AGENT)
        except Exception:
            try:
                status = ledger.fail_transport(reservation.attempt_id, TransportFailure("transport"),
                                               now=post_dispatch_time())
            except Exception:
                return RunOutcome("unavailable", reason="persistent_accounting_failure")
            return RunOutcome("unavailable", reason=status)
        if isinstance(result, TransportFailure):
            try:
                status = ledger.fail_transport(reservation.attempt_id, result, now=post_dispatch_time())
            except Exception:
                return RunOutcome("unavailable", reason="persistent_accounting_failure")
            if status == "retry_after_delay":
                sleep(RETRY_DELAY_SECONDS)
                continue
            return RunOutcome("unavailable", reason=status)
        try:
            status = ledger.complete(reservation.attempt_id, result, price, now=post_dispatch_time())
        except Exception:
            try:
                ledger.record_returned_unpersistable(reservation.attempt_id, now=post_dispatch_time(),
                                                      response=result)
            except Exception:
                return RunOutcome("unavailable", reason="persistent_accounting_failure")
            return RunOutcome("unavailable", reason="returned_unpersistable")
        if status != "returned":
            return RunOutcome("unavailable", reason=status)
        return RunOutcome("returned", content=result.content, finish_reason=result.finish_reason)
