"""In-memory, invented-only projection of a small original-reader JSONL subset.

The original reader writes separate ``readings.jsonl`` and ``responses.jsonl``
files, and a response can exist for an item whose reading was never completed.
This exercise preserves supplied historical bytes and models that case without
opening a path. It permits only a closed synthetic literal condition, synthetic
IDs, synthetic prompts and a small set of invented responses. It is NOT a reader
or merger for real checkpoints, even copies, and it cannot authorize evaluation.

The two returned byte strings are in-memory proposals, not an atomic filesystem
publication. Hashes and the supplied assignment inventory are caller claims:
they do not authenticate the original run, cache, provider, response, billing,
or prospective registration. The schema intentionally covers only a subset of
literal, temperature-zero rows, not the actual study's predictive, shifted,
masked, multi-condition, incomplete-file, or cache variations. No network,
credential, real dataset, sealed outcome or original output is accessed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re


SYNTHETIC_ONLY = True
MAX_BYTES = 1_000_000
MAX_ROWS = 1_000
_RUN = re.compile(r"SYNTH-RUN-[A-Z0-9]{1,24}", re.ASCII)
_ITEM = re.compile(r"SYNTH-ITEM-[A-Z0-9]{1,24}", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}", re.ASCII)
_MODEL = "SYNTH-MODEL"
_MODEL_ID = "SYNTH-MODEL-ID"
_PROVIDER = "SYNTH-PROVIDER"
_TEMPLATE = "SYNTH-TEMPLATE-LITERAL"
_TEMPLATE_SHA = sha256(b"SYNTH-TEMPLATE-LITERAL-V1").hexdigest()
_DECODING = "SYNTH-DECODING-ORIGINAL-DEFAULT"
_CONDITION = "SYNTH-CONDITION-ORIGINAL-DEFAULT"
_PERIOD = "SYNTH-PERIOD"
_BAD_TEXT = "SYNTH-NONJSON"
_RESPONSE_KEYS = {"item_id", "sample", "attempt", "prompt_sha256", "text", "served"}
_ATTEMPT_KEYS = {"attempt", "prompt_sha256", "cache_hit", "refused", "served_model", "served_provider",
                 "prompt_tokens", "completion_tokens", "total_tokens", "billable_output_tokens", "usd"}
_READING_KEYS = {"item_id", "period", "sample", "model", "model_id", "provider_pin", "template",
                 "template_sha256", "decoding", "temperature", "mask_names", "shift_years",
                 "track_record_sha256", "condition", "status", "fallback", "echo", "reading",
                 "errors", "warnings", "attempts"}
_SERVED = {"model": _MODEL_ID, "provider": _PROVIDER, "provider_names": [_PROVIDER], "metadata": None}


class SyntheticCheckpointRefusal(ValueError):
    """The invented JSONL fragments cannot be safely combined."""


@dataclass(frozen=True, slots=True)
class SyntheticRunInventory:
    """Caller-supplied toy assignments and historical identities, not provenance."""

    run_id: str
    assignments: tuple[tuple[str, int], ...]
    original_readings_sha256: str
    original_responses_sha256: str

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or _RUN.fullmatch(self.run_id) is None:
            raise SyntheticCheckpointRefusal("an explicitly synthetic run identity is required")
        if type(self.assignments) is not tuple or not 1 <= len(self.assignments) <= MAX_ROWS:
            raise SyntheticCheckpointRefusal("a bounded immutable synthetic assignment inventory is required")
        seen = set()
        for assignment in self.assignments:
            if type(assignment) is not tuple or len(assignment) != 2:
                raise SyntheticCheckpointRefusal("a synthetic assignment must be an item/sample pair")
            item, sample = assignment
            _pair(item, sample)
            if assignment in seen:
                raise SyntheticCheckpointRefusal("duplicate synthetic assignment")
            seen.add(assignment)
        for value in (self.original_readings_sha256, self.original_responses_sha256):
            if type(value) is not str or _SHA.fullmatch(value) is None:
                raise SyntheticCheckpointRefusal("a lowercase synthetic input SHA256 is required")


@dataclass(frozen=True, slots=True)
class SyntheticMerge:
    """A byte-preserving mock proposal; no file has been written or verified."""

    readings_bytes: bytes
    responses_bytes: bytes
    original_readings_sha256: str
    original_responses_sha256: str
    combined_readings_sha256: str
    combined_responses_sha256: str
    original_reading_rows: int
    added_reading_rows: int
    original_response_rows: int
    added_response_rows: int
    outstanding_assignments: int
    orphan_response_rows: int


def _pair(item: object, sample: object) -> tuple[str, int]:
    if type(item) is not str or _ITEM.fullmatch(item) is None:
        raise SyntheticCheckpointRefusal("an explicitly synthetic item identity is required")
    if type(sample) is not int or not 0 <= sample < 20:
        raise SyntheticCheckpointRefusal("a bounded synthetic sample index is required")
    return item, sample


def _object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SyntheticCheckpointRefusal("duplicate synthetic JSON object key")
        result[key] = value
    return result


def _not_json_number(_value: str):
    raise SyntheticCheckpointRefusal("non-finite synthetic JSON number")


def _json_int(value: str) -> int:
    if len(value.lstrip("-")) > 18:
        raise SyntheticCheckpointRefusal("synthetic JSON integer is too large")
    return int(value)


def _json_decimal(value: str) -> Decimal:
    if len(value) > 64:
        raise SyntheticCheckpointRefusal("synthetic JSON decimal is too large")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise SyntheticCheckpointRefusal("synthetic JSON decimal is invalid") from None
    if not number.is_finite() or abs(number.as_tuple().exponent) > 30:
        raise SyntheticCheckpointRefusal("synthetic JSON decimal exponent is unsupported")
    return number


def _rows(raw: object) -> list[dict]:
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise SyntheticCheckpointRefusal("synthetic JSONL must be bounded bytes")
    if not raw:
        return []
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise SyntheticCheckpointRefusal("synthetic JSONL must contain complete LF-terminated rows")
    parts = raw[:-1].split(b"\n")
    if len(parts) > MAX_ROWS or any(not part.strip() for part in parts):
        raise SyntheticCheckpointRefusal("synthetic JSONL has blank or too many rows")
    result = []
    for part in parts:
        try:
            obj = json.loads(part.decode("utf-8"), object_pairs_hook=_object_pairs,
                             parse_int=_json_int, parse_float=_json_decimal, parse_constant=_not_json_number)
        except (UnicodeError, ValueError, RecursionError):
            raise SyntheticCheckpointRefusal("synthetic JSONL row is malformed") from None
        if type(obj) is not dict:
            raise SyntheticCheckpointRefusal("a synthetic JSONL row must be an object")
        result.append(obj)
    return result


def synthetic_answer(label: str) -> str:
    """Return one closed invented literal answer, not a model completion."""
    if type(label) is not str or label not in {"ALPHA", "BETA", "GAMMA"}:
        raise SyntheticCheckpointRefusal("an invented answer label is required")
    reading = {"statement_type": "none", "interval": "ABSTAIN", "certainty": "no_statement",
               "stale": False, "quote": "SYNTH-QUOTE-" + label}
    return json.dumps(reading, sort_keys=True, separators=(",", ":"))


def _kind(text: object) -> tuple[str, dict | None]:
    if type(text) is not str:
        raise SyntheticCheckpointRefusal("synthetic response text is invalid")
    if text == "":
        return "refused", None
    if text == _BAD_TEXT:
        return "bad", None
    for label in ("ALPHA", "BETA", "GAMMA"):
        if text == synthetic_answer(label):
            return "answer", json.loads(text)
    raise SyntheticCheckpointRefusal("response is not one of the closed synthetic texts")


def synthetic_prompt_sha256(item_id: str, sample: int, attempt: int, first_text: str | None = None) -> str:
    """A deterministic toy prompt commitment; it is not the real cache key."""
    _pair(item_id, sample)
    if type(attempt) is not int or attempt not in (0, 1):
        raise SyntheticCheckpointRefusal("only synthetic initial and repair attempts are supported")
    if attempt == 0 and first_text is not None:
        raise SyntheticCheckpointRefusal("a first synthetic attempt has no prior response")
    if attempt == 1 and (type(first_text) is not str or first_text != _BAD_TEXT):
        raise SyntheticCheckpointRefusal("synthetic repair must follow the closed invalid response")
    material = f"SYNTH-PROMPT-V1|{item_id}|{sample}|{attempt}"
    if attempt == 1:
        material += "|" + sha256(first_text.encode("ascii")).hexdigest()
    return sha256(material.encode("ascii")).hexdigest()


def _responses(rows: list[dict], allowed: frozenset[tuple[str, int]]) -> dict[tuple[str, int, int], dict]:
    result = {}
    for row in rows:
        if set(row) != _RESPONSE_KEYS:
            raise SyntheticCheckpointRefusal("synthetic response fields differ")
        pair = _pair(row["item_id"], row["sample"])
        attempt = row["attempt"]
        if pair not in allowed or type(attempt) is not int or attempt not in (0, 1):
            raise SyntheticCheckpointRefusal("synthetic response is outside the assigned item/sample/attempt set")
        kind, _ = _kind(row["text"])
        served = row["served"]
        if (kind == "refused" and served is not None) or (kind != "refused" and served != _SERVED):
            raise SyntheticCheckpointRefusal("synthetic served metadata differs")
        key = (*pair, attempt)
        if key in result:
            raise SyntheticCheckpointRefusal("duplicate synthetic response attempt")
        result[key] = row
    return result


def _response_groups(responses: dict[tuple[str, int, int], dict]) -> None:
    for (item, sample, attempt), row in responses.items():
        first = responses.get((item, sample, 0))
        if first is None:
            raise SyntheticCheckpointRefusal("synthetic repair response lacks its first attempt")
        expected = synthetic_prompt_sha256(item, sample, attempt, first["text"] if attempt == 1 else None)
        if row["prompt_sha256"] != expected:
            raise SyntheticCheckpointRefusal("synthetic response prompt binding differs")


def _nonnegative_integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= 1_000_000


def _attempt(row: object, response: dict, ordinal: int) -> None:
    if type(row) is not dict or set(row) != _ATTEMPT_KEYS:
        raise SyntheticCheckpointRefusal("synthetic reading attempt fields differ")
    kind, _ = _kind(response["text"])
    refused = kind == "refused"
    if (type(row["attempt"]) is not int or row["attempt"] != ordinal
            or row["prompt_sha256"] != response["prompt_sha256"]
            or type(row["cache_hit"]) is not bool or type(row["refused"]) is not bool
            or row["refused"] is not refused
            or row["served_model"] != (None if refused else _MODEL_ID)
            or row["served_provider"] != (None if refused else _PROVIDER)):
        raise SyntheticCheckpointRefusal("synthetic reading and response attempt differ")
    fields = ("prompt_tokens", "completion_tokens", "total_tokens", "billable_output_tokens")
    if any(not _nonnegative_integer(row[field]) for field in fields):
        raise SyntheticCheckpointRefusal("synthetic token counts are invalid")
    prompt, completion, total, billable = (row[field] for field in fields)
    if total < prompt + completion or billable < completion:
        raise SyntheticCheckpointRefusal("synthetic token totals are inconsistent")
    usd = row["usd"]
    if type(usd) not in (int, Decimal) or not 0 <= usd <= 1:
        raise SyntheticCheckpointRefusal("synthetic attempt cost is invalid")
    if refused and (prompt, completion, total, billable, usd) != (0, 0, 0, 0, 0):
        raise SyntheticCheckpointRefusal("synthetic refusal has nonzero usage")


def _literal(value: object, expected: dict) -> bool:
    if type(value) is not dict or set(value) != set(expected):
        return False
    return all(type(value[key]) is type(expected[key]) and value[key] == expected[key] for key in expected)


def _readings(rows: list[dict], allowed: frozenset[tuple[str, int]],
              responses: dict[tuple[str, int, int], dict]) -> dict[tuple[str, int], dict]:
    result = {}
    for row in rows:
        if set(row) != _READING_KEYS:
            raise SyntheticCheckpointRefusal("synthetic reading fields differ")
        pair = _pair(row["item_id"], row["sample"])
        if pair not in allowed or pair in result:
            raise SyntheticCheckpointRefusal("duplicate or unassigned synthetic reading")
        fixed = {"period": _PERIOD, "model": _MODEL, "model_id": _MODEL_ID, "provider_pin": _PROVIDER,
                 "template": _TEMPLATE, "template_sha256": _TEMPLATE_SHA, "decoding": _DECODING,
                 "condition": _CONDITION, "track_record_sha256": None}
        if any(row[name] != value for name, value in fixed.items()):
            raise SyntheticCheckpointRefusal("synthetic reading condition or route differs")
        if (type(row["temperature"]) not in (int, Decimal) or row["temperature"] != 0
                or row["mask_names"] is not False or type(row["shift_years"]) is not int
                or row["shift_years"] != 0):
            raise SyntheticCheckpointRefusal("synthetic decoding, masking or shift differs")
        attempts = row["attempts"]
        if type(attempts) is not list or len(attempts) not in (1, 2):
            raise SyntheticCheckpointRefusal("synthetic reading attempts are invalid")
        matching = [responses.get((*pair, ordinal)) for ordinal in range(len(attempts))]
        if any(response is None for response in matching) or (*pair, len(attempts)) in responses:
            raise SyntheticCheckpointRefusal("synthetic reading does not match its response attempts")
        for ordinal, (attempt, response) in enumerate(zip(attempts, matching, strict=True)):
            _attempt(attempt, response, ordinal)
        first_kind, first_reading = _kind(matching[0]["text"])
        if first_kind == "answer" and len(attempts) == 1:
            status, reading, errors, echo = "ok", first_reading, [], "ok"
        elif first_kind == "refused" and len(attempts) == 1:
            status, reading, errors, echo = "refused", None, ["no JSON object found"], "refused"
        elif first_kind == "bad" and len(attempts) == 2:
            second_kind, second_reading = _kind(matching[1]["text"])
            if second_kind == "answer":
                status, reading, errors, echo = "repaired", second_reading, ["no JSON object found"], "ok"
            else:
                status, reading, errors, echo = "failed", None, ["no JSON object found", "repair: no JSON object found"], "ok"
        else:
            raise SyntheticCheckpointRefusal("synthetic status cannot be derived from its responses")
        if (row["status"] != status or row["echo"] != echo or row["errors"] != errors
                or type(row["warnings"]) is not list or row["warnings"]
                or row["fallback"] != (None if status in {"ok", "repaired"} else "abstain")
                or (reading is None and row["reading"] is not None)
                or (reading is not None and not _literal(row["reading"], reading))):
            raise SyntheticCheckpointRefusal("synthetic reading status or parsed content differs")
        result[pair] = row
    return result


def merge_synthetic_checkpoint(
    inventory: SyntheticRunInventory, *, original_readings: bytes, original_responses: bytes,
    added_readings: bytes, added_responses: bytes, synthetic_only: bool,
) -> SyntheticMerge:
    """Validate and concatenate two synthetic JSONL pairs, preserving original bytes.

    Completed original readings must already have their responses. Orphaned
    original responses may be referenced by a newly completed synthetic row;
    they are retained, not resent or duplicated. Remaining orphans are counted,
    not called completed. This function performs no physical I/O or billing.
    """
    if type(synthetic_only) is not bool or synthetic_only is not True:
        raise SyntheticCheckpointRefusal("an explicit synthetic-only assertion is required")
    if type(inventory) is not SyntheticRunInventory:
        raise SyntheticCheckpointRefusal("an exact synthetic inventory is required")
    SyntheticRunInventory.__post_init__(inventory)
    fragments = (original_readings, original_responses, added_readings, added_responses)
    if any(type(fragment) is not bytes for fragment in fragments):
        raise SyntheticCheckpointRefusal("all synthetic JSONL fragments must be bytes")
    if (len(original_readings) + len(added_readings) > MAX_BYTES
            or len(original_responses) + len(added_responses) > MAX_BYTES):
        raise SyntheticCheckpointRefusal("combined synthetic JSONL is too large")
    if (sha256(original_readings).hexdigest() != inventory.original_readings_sha256
            or sha256(original_responses).hexdigest() != inventory.original_responses_sha256):
        raise SyntheticCheckpointRefusal("synthetic original byte identity differs")
    old_reading_rows, old_response_rows, new_reading_rows, new_response_rows = map(_rows, fragments)
    if (len(old_reading_rows) + len(new_reading_rows) > MAX_ROWS
            or len(old_response_rows) + len(new_response_rows) > MAX_ROWS):
        raise SyntheticCheckpointRefusal("combined synthetic JSONL has too many rows")
    allowed = frozenset(inventory.assignments)
    old_responses = _responses(old_response_rows, allowed)
    _response_groups(old_responses)
    old_readings = _readings(old_reading_rows, allowed, old_responses)
    new_responses = _responses(new_response_rows, allowed)
    if old_responses.keys() & new_responses.keys():
        raise SyntheticCheckpointRefusal("a synthetic response attempt would be duplicated")
    if any((item, sample) in old_readings for item, sample, _ in new_responses):
        raise SyntheticCheckpointRefusal("a completed original synthetic reading cannot gain a new response")
    responses = old_responses | new_responses
    _response_groups(responses)
    new_readings = _readings(new_reading_rows, allowed, responses)
    if old_readings.keys() & new_readings.keys():
        raise SyntheticCheckpointRefusal("a completed original synthetic reading would be duplicated")
    readings = old_readings | new_readings
    orphan_count = sum((item, sample) not in readings for item, sample, _ in responses)
    combined_readings = original_readings + added_readings
    combined_responses = original_responses + added_responses
    return SyntheticMerge(
        combined_readings, combined_responses, inventory.original_readings_sha256,
        inventory.original_responses_sha256, sha256(combined_readings).hexdigest(),
        sha256(combined_responses).hexdigest(), len(old_reading_rows), len(new_reading_rows),
        len(old_response_rows), len(new_response_rows), len(allowed) - len(readings), orphan_count,
    )
