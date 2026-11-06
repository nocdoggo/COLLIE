"""Blinded first-pass and adjudication records for N and C references.

The functions validate supplied records; they do not distribute sheets, open
model outputs, or infer human interpretations. Attestations and timestamps are
records to verify, not independent proof that blinding occurred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from .records import (
    CalendarInterval, Certainty, NaturalReading, NaturalReference, PartialReferenceReading,
    StatementType, require_identifier,
)


def _utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")


@dataclass(frozen=True, slots=True)
class HumanAlternative:
    """A preserved human interpretation, including values not in the model schema."""

    statement_type: StatementType | None
    period_status: str
    start: date | None
    end: date | None
    human_certainty: str
    model_certainty: Certainty | None
    quote: str

    def __post_init__(self) -> None:
        if self.statement_type is not None and not isinstance(self.statement_type, StatementType):
            raise TypeError("statement_type must be a StatementType or None")
        if self.period_status not in {"finite", "none", "unresolved"}:
            raise ValueError("unknown period status")
        if any(value is not None and type(value) is not date for value in (self.start, self.end)):
            raise TypeError("interval endpoints must be calendar dates or None")
        if self.period_status == "none" and (self.start is not None or self.end is not None):
            raise ValueError("a reading with no period cannot carry an endpoint")
        if self.period_status == "finite" and self.end is None:
            raise ValueError("a finite reading needs its end")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("interval start must not follow end")
        if self.human_certainty not in {"asserted", "estimated", "conditional", "absent", "unresolved"}:
            raise ValueError("unknown human certainty")
        if self.model_certainty is not None and not isinstance(self.model_certainty, Certainty):
            raise TypeError("model_certainty must be an explicit Certainty or None")
        if not isinstance(self.quote, str):
            raise TypeError("quote must be text")

    def as_natural(self) -> NaturalReading | None:
        """Use only an explicit, fully representable adjudicated mapping."""
        if (self.statement_type is None or self.model_certainty is None
                or self.period_status == "unresolved"
                or (self.period_status == "finite" and self.start is None)):
            return None
        interval = CalendarInterval(self.start, self.end) if self.period_status == "finite" else None
        try:
            return NaturalReading(self.statement_type, interval, self.model_certainty, self.quote)
        except (TypeError, ValueError):
            return None

    def as_reference(self) -> PartialReferenceReading | None:
        """Preserve a known endpoint without inventing missing human fields."""
        if (self.period_status == "finite" and
                (self.statement_type is StatementType.NONE
                 or self.model_certainty in {Certainty.UNDETERMINED, Certainty.NO_STATEMENT})):
            return None
        if (self.statement_type is not None and self.model_certainty is not None
                and ((self.statement_type is StatementType.NONE) !=
                     (self.model_certainty is Certainty.NO_STATEMENT))):
            return None
        return PartialReferenceReading(self.statement_type, self.period_status, self.start, self.end,
                                       self.model_certainty, self.quote)

    def as_convention_reading(self) -> ConventionReading | None:
        """Map only the type and interval used in the draft C agreement metric."""
        if (self.statement_type is None or self.period_status == "unresolved"
                or (self.period_status == "finite" and self.start is None)
                or (self.period_status == "finite" and self.statement_type is StatementType.NONE)):
            return None
        interval = CalendarInterval(self.start, self.end) if self.period_status == "finite" else None
        return ConventionReading(self.statement_type, interval)


@dataclass(frozen=True, slots=True)
class ConventionReading:
    statement_type: StatementType
    interval: CalendarInterval | None

    def __post_init__(self) -> None:
        if not isinstance(self.statement_type, StatementType):
            raise TypeError("statement_type must be a StatementType")
        if self.interval is not None and not isinstance(self.interval, CalendarInterval):
            raise TypeError("interval must be a CalendarInterval or None")
        if self.statement_type is StatementType.NONE and self.interval is not None:
            raise ValueError("none cannot carry a finite interval")


@dataclass(frozen=True, slots=True)
class FirstPass:
    judgment_id: str
    item_id: str
    rater_code: str
    stage: str
    options: tuple[HumanAlternative, ...]
    submitted_utc: datetime
    guide_exposure: str
    outputs_seen: bool
    sensitivity_seen: bool
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.judgment_id, "judgment_id")
        require_identifier(self.item_id, "item_id")
        if not isinstance(self.rater_code, str) or re.fullmatch(r"A[1-9][0-9]*", self.rater_code) is None:
            raise ValueError("first-pass raters use anonymous A codes")
        if self.stage not in {"natural", "unspecified"}:
            raise ValueError("unknown first-pass stage")
        if type(self.options) is not tuple or any(not isinstance(option, HumanAlternative) for option in self.options):
            raise TypeError("options must be a tuple of human alternatives")
        _utc(self.submitted_utc, "submitted_utc")
        if self.guide_exposure not in {"prior_original_guide", "new_guide_only", "unspecified"}:
            raise ValueError("guide exposure must be recorded")
        if type(self.outputs_seen) is not bool or type(self.sensitivity_seen) is not bool:
            raise TypeError("exposure flags must be bool")
        if not self.options and (not isinstance(self.unresolved_reason, str) or not self.unresolved_reason.strip()):
            raise ValueError("an empty first pass requires an unresolved reason")
        if self.unresolved_reason is not None and (
            not isinstance(self.unresolved_reason, str) or not self.unresolved_reason.strip()
        ):
            raise ValueError("unresolved reason must be nonempty")


@dataclass(frozen=True, slots=True)
class SpecifiedPass:
    judgment_id: str
    item_id: str
    rater_code: str
    options: tuple[HumanAlternative, ...]
    shown_utc: datetime
    submitted_utc: datetime
    outputs_seen: bool
    sensitivity_seen: bool
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.judgment_id, "judgment_id")
        require_identifier(self.item_id, "item_id")
        if not isinstance(self.rater_code, str) or re.fullmatch(r"A[1-9][0-9]*", self.rater_code) is None:
            raise ValueError("specified-pass raters use anonymous A codes")
        if type(self.options) is not tuple or any(not isinstance(option, HumanAlternative) for option in self.options):
            raise TypeError("options must be a tuple of human alternatives")
        _utc(self.shown_utc, "shown_utc")
        _utc(self.submitted_utc, "submitted_utc")
        if self.shown_utc > self.submitted_utc:
            raise ValueError("specified pass cannot be submitted before it is shown")
        if type(self.outputs_seen) is not bool or type(self.sensitivity_seen) is not bool:
            raise TypeError("exposure flags must be bool")
        if not self.options and (not isinstance(self.unresolved_reason, str) or not self.unresolved_reason.strip()):
            raise ValueError("an empty specified pass requires an unresolved reason")
        if self.unresolved_reason is not None and (
            not isinstance(self.unresolved_reason, str) or not self.unresolved_reason.strip()
        ):
            raise ValueError("unresolved reason must be nonempty")


@dataclass(frozen=True, slots=True)
class NaturalAdjudication:
    reference: NaturalReference
    human_options: tuple[HumanAlternative, ...]
    first_pass_ids: tuple[str, ...]
    adjudicated_utc: datetime
    rationale: str


@dataclass(frozen=True, slots=True)
class ConventionReference:
    item_id: str
    reference_version: str
    defensible: tuple[ConventionReading, ...]
    specified: ConventionReading | None
    defensible_unresolved_reason: str | None
    specified_unresolved_reason: str | None
    first_pass_ids: tuple[str, ...]
    specified_pass_ids: tuple[str, ...]
    adjudicated_utc: datetime
    human_defensible_options: tuple[HumanAlternative, ...]
    human_specified_options: tuple[HumanAlternative, ...]
    rationale: str

    def __post_init__(self) -> None:
        require_identifier(self.item_id, "item_id")
        require_identifier(self.reference_version, "reference_version")
        require_identifier(self.rationale, "adjudication rationale")
        _utc(self.adjudicated_utc, "adjudicated_utc")
        if type(self.defensible) is not tuple or any(not isinstance(value, ConventionReading) for value in self.defensible):
            raise TypeError("defensible readings must be a tuple of ConventionReading values")
        if self.specified is not None and not isinstance(self.specified, ConventionReading):
            raise TypeError("specified must be a ConventionReading or None")
        if not self.defensible and self.defensible_unresolved_reason is None:
            raise ValueError("an empty defensible set needs an unresolved reason")
        if (self.specified is None) != (self.specified_unresolved_reason is not None):
            raise ValueError("specified target and unresolved reason are inconsistent")
        for reason in (self.defensible_unresolved_reason, self.specified_unresolved_reason):
            if reason is not None and (not isinstance(reason, str) or not reason.strip()):
                raise ValueError("unresolved reasons must be nonempty")
        ids = (*self.first_pass_ids, *self.specified_pass_ids)
        if len(self.first_pass_ids) != 2 or len(self.specified_pass_ids) != 2 or len(set(ids)) != 4:
            raise ValueError("reference must identify four distinct pass records")
        if any(not isinstance(value, HumanAlternative) for value in
               (*self.human_defensible_options, *self.human_specified_options)):
            raise TypeError("human alternatives must be preserved")


def _first_passes(item_id: str, passes: Iterable[FirstPass], stage: str) -> tuple[FirstPass, ...]:
    passes = tuple(passes)
    if len(passes) != 2 or any(not isinstance(item, FirstPass) for item in passes):
        raise ValueError("exactly two independent first passes are required")
    if (any(item.item_id != item_id or item.stage != stage for item in passes)
            or len({item.rater_code for item in passes}) != 2
            or len({item.judgment_id for item in passes}) != 2):
        raise ValueError("first-pass identities or stages differ")
    if any(item.outputs_seen or item.sensitivity_seen for item in passes):
        raise ValueError("exposed first passes cannot enter the unexposed reference")
    return passes


def _adjudication(
    item_id: str, reference_version: str, adjudicator: str, adjudicated_utc: datetime,
    outputs_seen: bool, sensitivity_seen: bool, *, not_before: datetime,
) -> None:
    require_identifier(item_id, "item_id")
    require_identifier(reference_version, "reference_version")
    if adjudicator != "ADJ":
        raise ValueError("adjudication uses the anonymous ADJ code")
    _utc(adjudicated_utc, "adjudicated_utc")
    if adjudicated_utc <= not_before:
        raise ValueError("adjudication must follow the submitted judgments")
    if type(outputs_seen) is not bool or type(sensitivity_seen) is not bool:
        raise TypeError("exposure flags must be bool")
    if outputs_seen or sensitivity_seen:
        raise ValueError("adjudication must be blind to outputs and sensitivity")


def _mapped_conventions(options: tuple[HumanAlternative, ...]) -> tuple[tuple[ConventionReading, ...], str | None]:
    if type(options) is not tuple or any(not isinstance(option, HumanAlternative) for option in options):
        raise TypeError("adjudicated options must be a tuple of human alternatives")
    if not options:
        return (), "no_adjudicated_reading"
    converted = tuple(option.as_convention_reading() for option in options)
    if any(option is None for option in converted):
        return tuple(option for option in converted if option is not None), "human_reading_not_fully_mapped"
    return converted, None


def adjudicate_natural(
    *, item_id: str, reference_version: str, first_passes: Iterable[FirstPass],
    options: tuple[HumanAlternative, ...], adjudicator: str, adjudicated_utc: datetime,
    outputs_seen: bool, sensitivity_seen: bool, rationale: str, unresolved_reason: str | None = None,
) -> NaturalAdjudication:
    passes = _first_passes(item_id, first_passes, "natural")
    _adjudication(item_id, reference_version, adjudicator, adjudicated_utc, outputs_seen,
                  sensitivity_seen, not_before=max(item.submitted_utc for item in passes))
    if unresolved_reason is not None and (not isinstance(unresolved_reason, str) or not unresolved_reason.strip()):
        raise ValueError("unresolved reason must be nonempty")
    require_identifier(rationale, "adjudication rationale")
    if type(options) is not tuple or any(not isinstance(option, HumanAlternative) for option in options):
        raise TypeError("adjudicated options must be a tuple of human alternatives")
    converted = tuple(option.as_reference() for option in options)
    alternatives = tuple(option for option in converted if option is not None)
    reason = unresolved_reason
    if not options and reason is None:
        reason = "no_adjudicated_reading"
    if any(option is None for option in converted):
        reason = reason or "inconsistent_reference_fields"
    return NaturalAdjudication(
        NaturalReference(item_id, reference_version, alternatives, True, reason), options,
        tuple(sorted(item.judgment_id for item in passes)), adjudicated_utc, rationale,
    )


def adjudicate_convention(
    *, item_id: str, reference_version: str, first_passes: Iterable[FirstPass],
    specified_passes: Iterable[SpecifiedPass], defensible_options: tuple[HumanAlternative, ...],
    specified_options: tuple[HumanAlternative, ...], adjudicator: str, adjudicated_utc: datetime,
    outputs_seen: bool, sensitivity_seen: bool, rationale: str,
) -> ConventionReference:
    first = _first_passes(item_id, first_passes, "unspecified")
    specified = tuple(specified_passes)
    if len(specified) != 2 or any(not isinstance(item, SpecifiedPass) for item in specified):
        raise ValueError("exactly two specified passes are required")
    if (any(item.item_id != item_id for item in specified)
            or {item.rater_code for item in specified} != {item.rater_code for item in first}
            or len({item.judgment_id for item in (*first, *specified)}) != 4):
        raise ValueError("specified-pass identities must match the independent first passes")
    if any(item.outputs_seen or item.sensitivity_seen for item in specified):
        raise ValueError("specified passes must be blind to outputs and sensitivity")
    if any(item.shown_utc <= max(first_item.submitted_utc for first_item in first) for item in specified):
        raise ValueError("the convention was shown before both first passes were submitted")
    _adjudication(item_id, reference_version, adjudicator, adjudicated_utc, outputs_seen,
                  sensitivity_seen, not_before=max(item.submitted_utc for item in specified))
    require_identifier(rationale, "adjudication rationale")
    defensible, defensible_reason = _mapped_conventions(defensible_options)
    targets, target_reason = _mapped_conventions(specified_options)
    if target_reason is None and len({(item.statement_type, item.interval) for item in targets}) != 1:
        target_reason = "specified_target_not_unique"
    target = targets[0] if target_reason is None else None
    return ConventionReference(item_id, reference_version, defensible, target,
                               defensible_reason, target_reason,
                               tuple(sorted(item.judgment_id for item in first)),
                               tuple(sorted(item.judgment_id for item in specified)), adjudicated_utc,
                               defensible_options, specified_options, rationale)
