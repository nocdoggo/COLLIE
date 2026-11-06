"""Aggregate-only rendering helpers for private review.

The functions open no paths and do not authorize publication. Historical
six-decimal exports are treated as rounded inputs, not as full precision.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Mapping


SAVED_RESULT_HASHES = {
    "confirmatory": "e70343e6857fadfe426561397bd61db71acb1dbc85106aab8e3d908228bde35a",
    "e2": "8169a95640413807f3b58bbc2adcbb93a00b985cd3614d5e437c83d7ef1c2402",
    "e5": "af0d8c232148b701d396ec2b999b34bbcb1f1965abad49322932864735aa02d3",
    "pattern": "a89523473a2e980d485d49d730c6134c64da8e600b336913489a1dceaded29c2",
}
AGGREGATE_BLOCKS = {
    "confirmatory": frozenset({"registered", "family", "probe", "h3"}),
    "e2": frozenset({"item_sets", "registered"}),
    "e5": frozenset({"tests", "registered"}),
    "pattern": frozenset({"sentence", "primaries", "registered"}),
}
STUDY_MODELS = ("llama-3.3-70b", "deepseek-v3")
HYPOTHESES = ("H1", "H2", "H3")


class CellStatus(str, Enum):
    PRESENT = "present"
    WITHHELD = "withheld"
    NOT_RUN = "not run"
    NOT_EVALUABLE = "not evaluable"
    UNDEFINED = "undefined"
    MISSING = "missing response"
    UNBOUNDED_LOW = "-infinity"
    UNBOUNDED_HIGH = "+infinity"


@dataclass(frozen=True, slots=True)
class Cell:
    status: CellStatus
    value: Decimal | None = None
    source_decimal_places: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, CellStatus):
            raise TypeError("cell status must be explicit")
        if self.status is CellStatus.PRESENT:
            if not isinstance(self.value, Decimal) or not self.value.is_finite():
                raise ValueError("a present cell requires a finite Decimal")
            if self.source_decimal_places is not None and (
                type(self.source_decimal_places) is not int or self.source_decimal_places < 0
            ):
                raise ValueError("source precision must be a nonnegative integer or None")
        elif self.value is not None or self.source_decimal_places is not None:
            raise ValueError("a non-present cell cannot carry a numeric value")


def number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise TypeError("numeric value is required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("numeric value must be finite") from error
    if not result.is_finite():
        raise ValueError("numeric value must be finite")
    return result


def _source_range(cell: Cell) -> tuple[Decimal, Decimal]:
    if cell.source_decimal_places is None:
        return cell.value, cell.value
    radius = Decimal("0.5").scaleb(-cell.source_decimal_places)
    return cell.value - radius, cell.value + radius


def display_cell(cell: Cell, *, places: int, signed: bool = False) -> str:
    """Round once, half away from zero, or flag a historical precision ambiguity."""
    if not isinstance(cell, Cell) or type(places) is not int or places < 0 or type(signed) is not bool:
        raise ValueError("typed cell, nonnegative places, and boolean sign flag are required")
    if cell.status is not CellStatus.PRESENT:
        return cell.status.value
    quantum = Decimal(1).scaleb(-places)
    lower, upper = _source_range(cell)
    low = lower.quantize(quantum, rounding=ROUND_HALF_UP)
    high = upper.quantize(quantum, rounding=ROUND_HALF_UP)
    if low != high:
        return "precision ambiguous"
    if low == 0:
        low = abs(low)
    shown = format(low, f".{places}f")
    if signed and low >= 0 and not shown.startswith("-"):
        shown = "+" + shown
    return shown


def display_p(cell: Cell, *, places: int = 3) -> str:
    if cell.status is not CellStatus.PRESENT:
        return cell.status.value
    low, high = _source_range(cell)
    if low > 1 or high < 0:
        raise ValueError("p-values must lie in [0,1]")
    cutoff = Decimal(1).scaleb(-places)
    if high < cutoff:
        return "<" + format(cutoff, f".{places}f")
    if low < cutoff <= high:
        return "precision ambiguous"
    return display_cell(cell, places=places)


def unique_count_from_share(value: Any, denominator: int, *, source_decimal_places: int = 6) -> int | None:
    """Recover a count only if exactly one integer is compatible with the rounded share."""
    if type(denominator) is not int or denominator <= 0:
        raise ValueError("denominator must be a positive integer")
    cell = Cell(CellStatus.PRESENT, number(value), source_decimal_places)
    low, high = _source_range(cell)
    if cell.value < 0 or cell.value > 1:
        raise ValueError("share must lie in [0,1]")
    candidates = [count for count in range(denominator + 1)
                  if low <= Decimal(count) / Decimal(denominator) <= high]
    return candidates[0] if len(candidates) == 1 else None


def _skip_json_value(text: str, position: int) -> int:
    """Skip a top-level value without decoding or materializing its contents."""
    start = position
    if text[position] in "{[":
        stack = []
        quoted = escaped = False
        while position < len(text):
            character = text[position]
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "{[":
                stack.append(character)
            elif character in "}]":
                if not stack or (stack.pop(), character) not in (("{", "}"), ("[", "]")):
                    raise ValueError("malformed JSON value")
                if not stack:
                    return position + 1
            position += 1
        raise ValueError("unterminated JSON value")
    if text[position] == '"':
        position += 1
        escaped = False
        while position < len(text):
            character = text[position]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                return position + 1
            position += 1
        raise ValueError("unterminated JSON string")
    while position < len(text) and text[position] not in ",}] \t\r\n":
        position += 1
    if position == start:
        raise ValueError("missing JSON value")
    return position


def _aggregate_projection(raw: bytes, allowed: frozenset[str]) -> dict[str, Any]:
    text = raw.decode("utf-8")
    decoder = json.JSONDecoder()
    position = 0
    def whitespace() -> None:
        nonlocal position
        while position < len(text) and text[position] in " \t\r\n":
            position += 1
    whitespace()
    if position >= len(text) or text[position] != "{":
        raise ValueError("saved result must be an object")
    position += 1
    result, seen = {}, set()
    while True:
        whitespace()
        if position >= len(text):
            raise ValueError("unterminated saved result")
        if text[position] == "}":
            position += 1
            break
        key, position = decoder.raw_decode(text, position)
        if not isinstance(key, str) or key in seen:
            raise ValueError("saved result keys must be unique strings")
        seen.add(key)
        whitespace()
        if position >= len(text) or text[position] != ":":
            raise ValueError("saved result key lacks a value")
        position += 1
        whitespace()
        if position >= len(text):
            raise ValueError("saved result value is missing")
        if key in allowed:
            result[key], position = decoder.raw_decode(text, position)
        else:
            position = _skip_json_value(text, position)
        whitespace()
        if position >= len(text):
            raise ValueError("unterminated saved result")
        if text[position] == ",":
            position += 1
        elif text[position] != "}":
            raise ValueError("invalid saved result separator")
    whitespace()
    if position != len(text):
        raise ValueError("unexpected text after saved result")
    return result


def verify_saved_bytes(name: str, raw: bytes) -> dict[str, Any]:
    """Verify one saved result identity and decode only aggregate top-level blocks."""
    if name not in SAVED_RESULT_HASHES or not isinstance(raw, bytes):
        raise ValueError("a known aggregate result and bytes are required")
    if hashlib.sha256(raw).hexdigest() != SAVED_RESULT_HASHES[name]:
        raise ValueError("saved result identity differs from the registered record")
    # E2 and E5 files can carry per-item records. Their top-level values are
    # skipped without JSON-decoding them.
    return _aggregate_projection(raw, AGGREGATE_BLOCKS[name])


def _present(value: Any, *, source_places: int = 6) -> Cell:
    return Cell(CellStatus.PRESENT, number(value), source_places)


def _interval(value: Any, *, places: int) -> str:
    if value is None:
        return CellStatus.UNDEFINED.value
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("an interval must have two endpoints")
    low = (Cell(CellStatus.UNBOUNDED_LOW) if value[0] is None else _present(value[0]))
    high = (Cell(CellStatus.UNBOUNDED_HIGH) if value[1] is None else _present(value[1]))
    return f"[{display_cell(low, places=places, signed=True)}, {display_cell(high, places=places, signed=True)}]"


def render_confirmatory(record: Mapping[str, Any], *, places: int = 3) -> str:
    """Render all six original tests from the registered aggregate structure."""
    registered = record.get("registered", {})
    if (registered.get("p_value_source") != "larger_of_studentised_and_sign_flip_t"
            or registered.get("tests_in_the_family") != 6
            or number(registered.get("familywise_alpha")) != Decimal("0.05")
            or number(registered.get("h2_margin")) != Decimal("0.02")
            or registered.get("h3_comparator") != "base_rate"
            or registered.get("intervals", {}).get("of_the_confirmatory_contrasts_and_delta_gbm")
            != "values_not_rejected_by_the_registered_test"):
        raise ValueError("confirmatory record does not match the registered family")
    family = record.get("family")
    if not isinstance(family, list) or len(family) != 6:
        raise ValueError("the original family must contain six entries")
    by_key = {(entry.get("model"), entry.get("hypothesis")): entry for entry in family}
    if set(by_key) != {(model, hypothesis) for model in STUDY_MODELS for hypothesis in HYPOTHESES}:
        raise ValueError("the original family has duplicate or missing tests")
    selections = record.get("h3", {}).get("selections", {})
    lines = [
        "| Model | Test | Item set | Statements | Episodes | Delta | 95% interval | Raw p | Holm p | Result |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---|",
    ]
    for model in STUDY_MODELS:
        for hypothesis in HYPOTHESES:
            entry = by_key[(model, hypothesis)]
            if entry.get("evaluable") is False:
                lines.append(f"| {model} | {hypothesis} | not evaluable | not evaluable | not evaluable | "
                             f"not evaluable | undefined | not evaluable | "
                             f"{display_p(_present(entry['p_holm']), places=places)} | not evaluable |")
                continue
            if entry.get("evaluable") is not True or type(entry.get("holds")) is not bool:
                raise ValueError("test evaluability and result must be explicit")
            expected_pair = {
                "H1": (f"{model}:a", f"{model}:b", 1),
                "H2": ("rules_plus_slip", f"{model}:c", 2),
                "H3": ("base_rate", f"{model}:{selections.get(model, {}).get('selected')}", 2),
            }[hypothesis]
            if (entry.get("comparator"), entry.get("tested"), entry.get("sides")) != expected_pair:
                raise ValueError("contrast direction, selection, or test sides differ from the record")
            if (not isinstance(entry.get("items"), str) or type(entry.get("statements")) is not int
                    or type(entry.get("episodes")) is not int):
                raise ValueError("each evaluable test needs its item set and cluster counts")
            delta = display_cell(_present(entry["delta"]), places=places, signed=True)
            interval = _interval(entry.get("ci95"), places=places)
            raw = display_p(_present(entry["p"]), places=places)
            adjusted = display_p(_present(entry["p_holm"]), places=places)
            verdict = "rejected" if entry["holds"] else "not rejected"
            if hypothesis == "H2":
                equivalence = entry.get("equivalence")
                if not isinstance(equivalence, Mapping) or type(equivalence.get("declared")) is not bool:
                    raise ValueError("H2 requires the separately registered equivalence verdict")
                verdict += "; loss equivalence declared" if equivalence["declared"] else "; no equivalence declared"
            lines.append(f"| {model} | {hypothesis} | {entry['items']} | {entry['statements']} | "
                         f"{entry['episodes']} | {delta} | {interval} | {raw} | {adjusted} | {verdict} |")
    lines.append("")
    lines.append("Delta is comparator loss minus tested-predictor loss. H2 equivalence concerns the "
                 "specified two-horizon forecast loss, not literal-reading competence.")
    return "\n".join(lines) + "\n"


def render_letter_counts(e2: Mapping[str, Any], *, item_set: str = "all") -> str:
    """Render pooled letter counts, never event-weighted overall correctness as letter accuracy."""
    readings = e2["item_sets"][item_set]["letter_reading"]
    by_model = {entry["model"]: entry for entry in readings}
    if not set(STUDY_MODELS).issubset(by_model):
        raise ValueError("both primary letter readings are required")
    lines = ["| Reader | Letter items | Correct |", "|---|---:|---:|"]
    rule_values = set()
    for model in STUDY_MODELS:
        entry = by_model[model]
        if entry.get("evaluable") is False:
            lines.append(f"| {model} | not evaluable | not evaluable |")
            continue
        if entry.get("evaluable") is not True:
            raise ValueError("letter-reading evaluability must be explicit")
        count = unique_count_from_share(entry["first"], entry["items"])
        rule = unique_count_from_share(entry["second"], entry["items"])
        rule_values.add((entry["items"], rule))
        lines.append(f"| {model} | {entry['items']} | {count if count is not None else 'precision ambiguous'} |")
    if len(rule_values) == 1:
        items, count = next(iter(rule_values))
        lines.append(f"| Rule reader | {items} | {count if count is not None else 'precision ambiguous'} |")
    elif rule_values:
        raise ValueError("rule letter counts disagree across primary records")
    lines.append("")
    lines.append("Counts are reported only when uniquely determined by the stored rounded share and denominator.")
    return "\n".join(lines) + "\n"


def render_e5_tests(e5: Mapping[str, Any], *, places: int = 3) -> str:
    """Render all registered primary E5 contrasts, retaining their directions."""
    tests = e5.get("tests")
    if not isinstance(tests, list) or len(tests) != 12:
        raise ValueError("the E5 family must contain all twelve tests")
    lines = ["| Model | Factor | Edited errors/items | Seed errors/items | Difference | Holm p | Result |",
             "|---|---|---:|---:|---:|---:|---|"]
    seen = set()
    for entry in tests:
        key = (entry.get("model"), entry.get("factor"))
        if key in seen or key[0] not in STUDY_MODELS:
            raise ValueError("E5 tests must have unique primary model/factor identities")
        seen.add(key)
        if entry.get("evaluable") is False:
            lines.append(f"| {key[0]} | {key[1]} | not evaluable | not evaluable | not evaluable | not evaluable | not evaluable |")
            continue
        if entry.get("evaluable") is not True or type(entry.get("holds")) is not bool:
            raise ValueError("E5 evaluability and result must be explicit")
        edited, seed = entry["edited"], entry["unedited"]
        for block in (edited, seed):
            if (type(block.get("items")) is not int or type(block.get("errors")) is not int
                    or not 0 <= block["errors"] <= block["items"]):
                raise ValueError("E5 error counts and denominators are inconsistent")
        difference = display_cell(_present(entry["difference"]), places=places, signed=True)
        p = display_p(_present(entry["p_holm"]), places=places)
        result = "rejected" if entry["holds"] else "not rejected"
        lines.append(f"| {key[0]} | {key[1]} | {edited['errors']}/{edited['items']} | "
                     f"{seed['errors']}/{seed['items']} | {difference} | {p} | {result} |")
    factors = {"certainty", "surface_form", "granularity", "stale", "distractor", "silent"}
    if seen != {(model, factor) for model in STUDY_MODELS for factor in factors}:
        raise ValueError("the E5 family does not contain the registered factors")
    return "\n".join(lines) + "\n"


def render_probe(record: Mapping[str, Any], *, places: int = 3) -> str:
    """Render the original probe, including its metadata-based identification limit."""
    probes = record.get("probe")
    if not isinstance(probes, Mapping):
        raise ValueError("probe aggregates are required")
    lines = ["| Model | Base minus probe pinball loss, days | Raw p |",
             "|---|---:|---:|"]
    for model in STUDY_MODELS:
        entry = probes.get(model)
        if entry is None:
            lines.append(f"| {model} | not run | not run |")
        elif entry.get("withheld") is True:
            lines.append(f"| {model} | withheld | withheld |")
        elif entry.get("evaluable") is not True:
            lines.append(f"| {model} | not evaluable | not evaluable |")
        else:
            delta = display_cell(_present(entry["delta"]), places=places, signed=True)
            p = display_p(_present(entry["p"]), places=places)
            lines.append(f"| {model} | {delta} | {p} |")
    lines.append("")
    lines.append("The no-notice probe retains drug, company and other metadata. Its advantage does not uniquely identify memorized outcomes.")
    return "\n".join(lines) + "\n"


def render_registered_pattern(pattern: Mapping[str, Any]) -> str:
    sentence = pattern.get("sentence")
    if not isinstance(sentence, Mapping) or not isinstance(sentence.get("stated_for"), list):
        raise ValueError("the registered pattern record is required")
    if sentence.get("case") == "neither primary" and sentence["stated_for"] == []:
        return "The original registered headline pattern holds for neither primary model.\n"
    raise ValueError("pattern case requires a separately verified rendering")
