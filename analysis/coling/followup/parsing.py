"""Strict parsers for returned follow-up answers, with no repair calls."""

from __future__ import annotations

import json
from typing import Any

from .records import (
    CalendarInterval, Certainty, NaturalReading, ParsedNatural, ParsedRole,
    ParseStatus, RoleReading, StatementType, iso_date,
)


class _DuplicateKey(ValueError):
    pass


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_object, parse_constant=_nonfinite)


def _keys(value: Any, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("unexpected or missing object fields")
    return value


def _quote_valid(quote: str, notice_text: str, has_date: bool) -> bool | None:
    if quote == "":
        return False if has_date else None
    return quote in notice_text


def _returned_status(finish_reason: str | None) -> tuple[ParseStatus, str] | None:
    if finish_reason == "length":
        return ParseStatus.TRUNCATED, "output_token_ceiling"
    if finish_reason != "stop":
        return ParseStatus.INVALID_SCHEMA, "unsupported_or_missing_finish_reason"
    return None


def parse_natural(text: str, notice_text: str, *, finish_reason: str | None) -> ParsedNatural:
    """Parse one returned N/C answer; quote mismatch is recorded, not repaired."""
    if not isinstance(text, str) or not isinstance(notice_text, str):
        raise TypeError("returned content and notice text must be strings")
    terminal = _returned_status(finish_reason)
    if terminal:
        return ParsedNatural(terminal[0], reason=terminal[1])
    try:
        value = _json(text)
    except (json.JSONDecodeError, _DuplicateKey, ValueError, RecursionError):
        return ParsedNatural(ParseStatus.INVALID_JSON, reason="invalid_json")
    try:
        value = _keys(value, {"statement_type", "interval", "certainty", "quote"})
        if not isinstance(value["quote"], str):
            raise ValueError("quote must be a string")
        interval = value["interval"]
        if interval is not None:
            interval = _keys(interval, {"start", "end"})
            interval = CalendarInterval(iso_date(interval["start"]), iso_date(interval["end"]))
        reading = NaturalReading(
            StatementType(value["statement_type"]), interval,
            Certainty(value["certainty"]), value["quote"],
        )
    except (TypeError, ValueError, KeyError):
        return ParsedNatural(ParseStatus.INVALID_SCHEMA, reason="invalid_schema")
    return ParsedNatural(
        ParseStatus.VALID, reading,
        quote_valid=_quote_valid(reading.quote, notice_text, reading.interval is not None),
    )


def parse_role(text: str, notice_text: str, *, finish_reason: str | None) -> ParsedRole:
    """Parse one returned R answer. Evidence quotes are a separate diagnostic."""
    if not isinstance(text, str) or not isinstance(notice_text, str):
        raise TypeError("returned content and notice text must be strings")
    terminal = _returned_status(finish_reason)
    if terminal:
        return ParsedRole(terminal[0], reason=terminal[1])
    try:
        value = _json(text)
    except (json.JSONDecodeError, _DuplicateKey, ValueError, RecursionError):
        return ParsedRole(ParseStatus.INVALID_JSON, reason="invalid_json")
    try:
        value = _keys(value, {"date", "quote"})
        target = None if value["date"] is None else iso_date(value["date"])
        reading = RoleReading(target, value["quote"])
    except (TypeError, ValueError, KeyError):
        return ParsedRole(ParseStatus.INVALID_SCHEMA, reason="invalid_schema")
    return ParsedRole(
        ParseStatus.VALID, reading,
        quote_valid=_quote_valid(reading.quote, notice_text, reading.target_date is not None),
    )


def unavailable_natural(reason: str, *, cap_blocked: bool = False) -> ParsedNatural:
    if type(cap_blocked) is not bool:
        raise TypeError("cap_blocked must be bool")
    return ParsedNatural(ParseStatus.CAP_BLOCKED if cap_blocked else ParseStatus.UNAVAILABLE,
                         reason=reason)


def unavailable_role(reason: str, *, cap_blocked: bool = False) -> ParsedRole:
    if type(cap_blocked) is not bool:
        raise TypeError("cap_blocked must be bool")
    return ParsedRole(ParseStatus.CAP_BLOCKED if cap_blocked else ParseStatus.UNAVAILABLE,
                      reason=reason)
