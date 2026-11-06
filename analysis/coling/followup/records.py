"""Typed, outcome-free reading records for the follow-up.

These objects do not load files and carry no recovery outcomes. A missing
interval is an observed null reading, not an unavailable response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum


class StatementType(str, Enum):
    RECOVERY = "recovery"
    NEXT_DELIVERY = "next_delivery"
    OTHER = "other"
    NONE = "none"


class Certainty(str, Enum):
    ASSERTED = "asserted"
    ESTIMATED = "estimated"
    UNDETERMINED = "undetermined"
    NO_STATEMENT = "no_statement"


class ParseStatus(str, Enum):
    VALID = "valid"
    INVALID_JSON = "invalid_json"
    INVALID_SCHEMA = "invalid_schema"
    TRUNCATED = "truncated"
    UNAVAILABLE = "unavailable"
    CAP_BLOCKED = "cap_blocked"


RETURNED_FAILURES = frozenset({
    ParseStatus.INVALID_JSON, ParseStatus.INVALID_SCHEMA, ParseStatus.TRUNCATED,
})
UNAVAILABLE = frozenset({ParseStatus.UNAVAILABLE, ParseStatus.CAP_BLOCKED})


def require_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a nonempty, trimmed string")


def require_sha256(value: str, name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA256")


def iso_date(value: object) -> date:
    """Parse exactly YYYY-MM-DD, including calendar and leap-day validation."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("date must use YYYY-MM-DD")
    return date.fromisoformat(value)


@dataclass(frozen=True, slots=True)
class CalendarInterval:
    start: date
    end: date

    def __post_init__(self) -> None:
        if type(self.start) is not date or type(self.end) is not date:
            raise TypeError("interval endpoints must be dates without times")
        if self.start > self.end:
            raise ValueError("interval start must not follow its end")


@dataclass(frozen=True, slots=True)
class NaturalReading:
    statement_type: StatementType
    interval: CalendarInterval | None
    certainty: Certainty
    quote: str

    def __post_init__(self) -> None:
        if not isinstance(self.statement_type, StatementType):
            raise TypeError("statement_type must be a StatementType")
        if not isinstance(self.certainty, Certainty):
            raise TypeError("certainty must be a Certainty")
        if self.interval is not None and type(self.interval) is not CalendarInterval:
            raise TypeError("interval must be a CalendarInterval or None")
        if type(self.quote) is not str:
            raise TypeError("quote must be a string")
        no_statement = self.statement_type is StatementType.NONE
        if no_statement != (self.certainty is Certainty.NO_STATEMENT):
            raise ValueError("none and no_statement must occur together")
        if self.interval is not None and (no_statement or self.certainty is Certainty.UNDETERMINED):
            raise ValueError("a finite interval conflicts with the statement type or certainty")


@dataclass(frozen=True, slots=True)
class PartialReferenceReading:
    """A human reading whose finite end can be known while other fields are not."""

    statement_type: StatementType | None
    period_status: str
    start: date | None
    end: date | None
    certainty: Certainty | None
    quote: str

    def __post_init__(self) -> None:
        if self.statement_type is not None and not isinstance(self.statement_type, StatementType):
            raise TypeError("statement_type must be a StatementType or None")
        if type(self.period_status) is not str or self.period_status not in {"finite", "none", "unresolved"}:
            raise ValueError("unknown period status")
        if any(value is not None and type(value) is not date for value in (self.start, self.end)):
            raise TypeError("reference endpoints must be calendar dates or None")
        if self.period_status == "finite" and self.end is None:
            raise ValueError("a finite reference needs an end")
        if self.period_status == "none" and (self.start is not None or self.end is not None):
            raise ValueError("a reference with no period cannot carry endpoints")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("reference start must not follow end")
        if self.certainty is not None and not isinstance(self.certainty, Certainty):
            raise TypeError("certainty must be a Certainty or None")
        if self.period_status == "finite" and (
            self.statement_type is StatementType.NONE
            or self.certainty in {Certainty.UNDETERMINED, Certainty.NO_STATEMENT}
        ):
            raise ValueError("a finite reference conflicts with its known type or certainty")
        if (self.statement_type is not None and self.certainty is not None
                and ((self.statement_type is StatementType.NONE) != (self.certainty is Certainty.NO_STATEMENT))):
            raise ValueError("known none and no_statement must occur together")
        if type(self.quote) is not str:
            raise TypeError("quote must be a string")


def calibration_end(reading: NaturalReading | PartialReferenceReading) -> date | None:
    """Return the dated/no-date calibrator input, or refuse an unknown input.

    Literal interval presence is separate: a finite OTHER interval exists, but
    the original slip mapping treats it as no date. An unknown type matters
    only when a finite interval could otherwise be mapped to a dated input.
    """
    if type(reading) is NaturalReading:
        end = None if reading.interval is None else reading.interval.end
        kind = reading.statement_type
    elif type(reading) is PartialReferenceReading:
        if reading.period_status == "unresolved":
            raise ValueError("reference period is unresolved")
        end = reading.end if reading.period_status == "finite" else None
        kind = reading.statement_type
    else:
        raise TypeError("unsupported calibration reading")
    if end is None:
        return None
    if kind is None:
        raise ValueError("reference type is needed for the calibration mapping")
    return end if kind in {StatementType.RECOVERY, StatementType.NEXT_DELIVERY} else None


@dataclass(frozen=True, slots=True)
class RoleReading:
    target_date: date | None
    quote: str

    def __post_init__(self) -> None:
        if self.target_date is not None and type(self.target_date) is not date:
            raise TypeError("target_date must be a date without a time, or None")
        if not isinstance(self.quote, str):
            raise TypeError("quote must be a string")
        if self.target_date is None and self.quote != "":
            raise ValueError("a null role date requires an empty quote")


@dataclass(frozen=True, slots=True)
class ReadingIdentity:
    item_id: str
    model_id: str
    provider_route: str
    precision: str
    template_id: str
    template_sha256: str
    decoding_sha256: str
    item_text_sha256: str
    parser_sha256: str

    def __post_init__(self) -> None:
        for name in ("item_id", "model_id", "provider_route", "precision", "template_id"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} must be a string")
            require_identifier(getattr(self, name), name)
        for name in ("template_sha256", "decoding_sha256", "item_text_sha256", "parser_sha256"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} must be a string")
            require_sha256(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ParsedNatural:
    status: ParseStatus
    reading: NaturalReading | None = None
    quote_valid: bool | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ParseStatus):
            raise TypeError("status must be a ParseStatus")
        if self.status is ParseStatus.VALID:
            if type(self.reading) is not NaturalReading or self.reason is not None:
                raise ValueError("a valid parse requires a reading and no failure reason")
            if self.quote_valid is not None and type(self.quote_valid) is not bool:
                raise TypeError("quote_valid must be bool or None")
        elif self.reading is not None or self.quote_valid is not None:
            raise ValueError("a failed parse cannot carry a reading or quote verdict")
        elif not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("a failed or unavailable parse requires a reason")


@dataclass(frozen=True, slots=True)
class ParsedRole:
    status: ParseStatus
    reading: RoleReading | None = None
    quote_valid: bool | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ParseStatus):
            raise TypeError("status must be a ParseStatus")
        if self.status is ParseStatus.VALID:
            if not isinstance(self.reading, RoleReading) or self.reason is not None:
                raise ValueError("a valid parse requires a reading and no failure reason")
            if self.quote_valid is not None and type(self.quote_valid) is not bool:
                raise TypeError("quote_valid must be bool or None")
        elif self.reading is not None or self.quote_valid is not None:
            raise ValueError("a failed parse cannot carry a reading or quote verdict")
        elif not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("a failed or unavailable parse requires a reason")


@dataclass(frozen=True, slots=True)
class NaturalObservation:
    """A parsed result and its assigned identity, if the identity is available."""

    parsed: ParsedNatural
    identity: ReadingIdentity | None
    identity_missing_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.parsed) is not ParsedNatural:
            raise TypeError("parsed must be a ParsedNatural")
        if self.identity is None:
            if not isinstance(self.identity_missing_reason, str) or not self.identity_missing_reason.strip():
                raise ValueError("missing reading identity requires a reason")
        elif type(self.identity) is not ReadingIdentity or self.identity_missing_reason is not None:
            raise ValueError("a present identity cannot have a missing-identity reason")


@dataclass(frozen=True, slots=True)
class NaturalReference:
    """Adjudicated defensible readings, preserved even if their endpoints differ.

    A first-pass or unfinalized record cannot define a resolved reference. An
    explicit unresolved reason also takes precedence over any alternatives.
    """

    item_id: str
    reference_version: str
    alternatives: tuple[NaturalReading | PartialReferenceReading, ...]
    finalized: bool
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.item_id) is not str or type(self.reference_version) is not str:
            raise TypeError("reference identifiers must be strings")
        require_identifier(self.item_id, "item_id")
        require_identifier(self.reference_version, "reference_version")
        if type(self.alternatives) is not tuple or any(
            type(reading) not in (NaturalReading, PartialReferenceReading) for reading in self.alternatives
        ):
            raise TypeError("alternatives must be a tuple of reference reading values")
        if type(self.finalized) is not bool:
            raise TypeError("finalized must be bool")
        if self.unresolved_reason is not None and (
            type(self.unresolved_reason) is not str or not self.unresolved_reason.strip()
        ):
            raise ValueError("unresolved_reason must be a nonempty string")
        if self.finalized and not self.alternatives and self.unresolved_reason is None:
            raise ValueError("a finalized reference needs alternatives or an unresolved reason")

    @property
    def missing_reason(self) -> str | None:
        if not self.finalized:
            return self.unresolved_reason or "reference_not_finalized"
        if self.unresolved_reason is not None:
            return self.unresolved_reason
        if any(isinstance(reading, PartialReferenceReading) and reading.period_status == "unresolved"
               for reading in self.alternatives):
            return "reference_period_unresolved"
        endpoints = set()
        for reading in self.alternatives:
            if isinstance(reading, NaturalReading):
                endpoints.add(None if reading.interval is None else reading.interval.end)
            else:
                endpoints.add(reading.end if reading.period_status == "finite" else None)
        return None if len(endpoints) == 1 else "reference_endpoint_not_unique"
