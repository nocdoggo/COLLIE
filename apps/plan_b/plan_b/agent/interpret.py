"""Strict interpretation of new notices into planning ``change_spec`` records.

The model extracts what a notice claims (subject, change kind, times, order and date
references, evidence ids); the server decides what that reading may mean for planning:

* Server-side first: a notice with the same correlation group and normalized text as a handled
  one is a ``duplicate`` (one evidence lineage, no model call); ``supersedes`` naming a handled
  notice of the same source retracts it.
* Every referenced entity is checked against public state. An unknown subject makes the
  interpretation ``unresolved`` (failure ``unknown_entity``) and is never kept; evidence ids
  that name no visible observation are dropped; an order reference must be the subject's
  ``booking_ref`` and a referenced date must be the event date, else the notice is
  ``inapplicable``. Times are parsed on the event date in the event timezone.
* Hearsay: an equipment claim submitted through a participant or organizer session.
* One structured-output repair attempt; after a second malformed or invalid reply the batch
  stays unresolved (failure ``malformed_output``).

Observation text is sent as quoted JSON inside ``<untrusted_observations>``; nothing in it can
create an entity, a grant or a tool call, because the reply is only ever a ``change_spec``.
Status, arrival and check-in records are typed evidence and are not interpreted here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from plan_b.agent.prompts import Prompt, load_prompt
from plan_b.agent.provider import (
    CallRecord,
    ModelRequest,
    ModelResponse,
    ProviderMalformedJSON,
    ProviderSchemaViolation,
)
from plan_b.domain.models import (
    PLANNING_SCHEMA_VERSION,
    EventStateView,
    ObservationChannel,
    ObservationRecord,
    Strict,
    UtcDatetime,
)
from plan_b.domain.timeutil import fmt_ts, local_label, to_utc
from plan_b.evaluation.policies.parser import (
    NOTICE_KINDS,
    SESSION_CHANNELS,
    event_local_date,
    normalize_text,
)

INTERPRET_PROMPT = "interpret.v1"
INTERPRET_SCHEMA_NAME = "plan_b_change_interpretation"
MAX_NOTICES_PER_CALL = 6
MAX_TEXT_CHARS = 400
CHANGE_KINDS = (
    "delay",
    "unavailability",
    "availability",
    "attendance_change",
    "priority_change",
    "no_change",
    "unresolved",
)
_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_ORDER = re.compile(r"^[A-Za-z]{1,4}\d{1,8}$")

ChangeKind = Literal[
    "delay",
    "unavailability",
    "availability",
    "attendance_change",
    "priority_change",
    "no_change",
    "unresolved",
]
Standing = Literal["claim", "no_claim", "unresolved", "inapplicable", "duplicate"]
InterpretFailure = Literal["unknown_entity", "malformed_output", "provider_error", "missing"]

# A model call with the caps and accounting of the caller; it raises ProviderError subclasses.
CallModel = Callable[[ModelRequest], ModelResponse]


# ---------------------------------------------------------------------------------- shapes


class PlanningWindow(Strict):
    start: str
    end: str


class ChangeSpec(Strict):
    """Planning 0.2.0 ``change_spec`` (``planning.schema.json#/$defs/ChangeSpec``)."""

    artifact_type: Literal["change_spec"] = "change_spec"
    schema_version: Literal["0.2.0"] = PLANNING_SCHEMA_VERSION
    change_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    based_on_revision: int = Field(ge=0)
    subject_id: str = Field(min_length=1)
    change_kind: ChangeKind
    valid_window: PlanningWindow
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    interpretation: str = Field(min_length=1)
    unresolved_fields: tuple[str, ...]
    proposed_checks: tuple[str, ...]


class InterpretItem(Strict):
    """One model reading (the structured-output item)."""

    observation_id: str
    subject_id: str | None
    change_kind: ChangeKind
    applicability: Literal["applies", "inapplicable", "unclear"]
    claimed_eta_local: str | None
    promised_local: str | None
    order_ref: str | None
    referenced_date: str | None
    interpretation: str
    unresolved_fields: tuple[str, ...]
    proposed_checks: tuple[Literal["query_status"], ...]
    evidence_refs: tuple[str, ...]
    contains_instructions: bool


class InterpretOutput(Strict):
    interpretations: tuple[InterpretItem, ...]


class LiveInterpretation(Strict):
    """The server-validated reading of one notice."""

    observation_id: str
    change_spec: ChangeSpec
    standing: Standing
    subject_resource_id: str | None  # a registered resource the claim is about
    claimed_eta: UtcDatetime | None = None
    promised_at: UtcDatetime | None = None
    hearsay: bool = False
    channel: ObservationChannel
    source_id: str
    submitted_by: str | None = None
    received_at: UtcDatetime
    revision_after: int
    correlation_group: str
    normalized_text: str
    duplicate_of: str | None = None
    retracts: tuple[str, ...] = ()
    contains_instructions: bool = False
    failure: InterpretFailure | None = None
    server_notes: tuple[str, ...] = ()  # what validation rejected or changed
    model_call_ids: tuple[str, ...] = ()

    @property
    def is_claim(self) -> bool:
        return self.standing == "claim"


def interpret_schema(observation_ids: Sequence[str]) -> dict[str, Any]:
    """Strict JSON schema of ``InterpretOutput`` (every property required, no extras)."""
    nullable = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": list(InterpretItem.model_fields),
        "properties": {
            "observation_id": {"type": "string", "enum": list(observation_ids)},
            "subject_id": nullable,
            "change_kind": {"type": "string", "enum": list(CHANGE_KINDS)},
            "applicability": {"type": "string", "enum": ["applies", "inapplicable", "unclear"]},
            "claimed_eta_local": nullable,
            "promised_local": nullable,
            "order_ref": nullable,
            "referenced_date": nullable,
            "interpretation": {"type": "string"},
            "unresolved_fields": {"type": "array", "items": {"type": "string"}},
            "proposed_checks": {
                "type": "array",
                "items": {"type": "string", "enum": ["query_status"]},
            },
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "contains_instructions": {"type": "boolean"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["interpretations"],
        "properties": {"interpretations": {"type": "array", "items": item}},
    }


# ---------------------------------------------------------------------------------- entry


def new_notices(view: EventStateView, handled: Sequence[str]) -> list[ObservationRecord]:
    """Visible notices not yet interpreted, in arrival order."""
    seen = set(handled)
    return [
        r
        for r in view.observations
        if r.observation.kind in NOTICE_KINDS and r.observation.observation_id not in seen
    ]


def server_prefilter(
    view: EventStateView,
    records: Sequence[ObservationRecord],
    handled: Sequence[LiveInterpretation],
) -> tuple[list[LiveInterpretation], list[ObservationRecord]]:
    """Duplicates resolved without the model, and the records that need it."""
    known = list(handled)
    done: list[LiveInterpretation] = []
    to_model: list[ObservationRecord] = []
    for record in records:
        obs = record.observation
        normalized = normalize_text(obs.text)
        original = next(
            (
                h
                for h in known
                if h.correlation_group == obs.correlation_group
                and h.normalized_text == normalized
                and h.observation_id != obs.observation_id
            ),
            None,
        )
        if original is None:
            to_model.append(record)
            continue
        spec = original.change_spec.model_copy(
            update={
                "change_id": f"chg_{obs.observation_id}",
                "based_on_revision": view.revision,
                "evidence_refs": (obs.observation_id, original.observation_id),
                "change_kind": "no_change",
                "interpretation": (
                    f"Same correlation group and text as {original.observation_id}: one "
                    "evidence lineage, not corroboration."
                ),
            }
        )
        dup = _base(record, view, spec).model_copy(
            update={"standing": "duplicate", "duplicate_of": original.observation_id}
        )
        done.append(dup)
        known.append(dup)
    return done, to_model


def interpret_batch(
    call_model: CallModel,
    view: EventStateView,
    records: Sequence[ObservationRecord],
    handled: Sequence[LiveInterpretation],
    *,
    call_ids: Callable[[], str],
    prompt: Prompt | None = None,
) -> tuple[list[LiveInterpretation], list[CallRecord]]:
    """Interpret up to ``MAX_NOTICES_PER_CALL`` records with one call (plus one repair).

    Provider failures other than malformed or invalid output propagate to the caller."""
    prompt = prompt or load_prompt(INTERPRET_PROMPT)
    batch = list(records)[:MAX_NOTICES_PER_CALL]
    ids = [r.observation.observation_id for r in batch]
    context = _context(view)
    observations = [_observation_payload(r, view) for r in batch]
    request = ModelRequest(
        purpose="interpret",
        system=prompt.system,
        user=prompt.render(context=context, observations=observations),
        schema_name=INTERPRET_SCHEMA_NAME,
        schema=interpret_schema(ids),
        output_model=InterpretOutput,
        context={"event": context, "observations": observations},
        call_id=call_ids(),
        prompt_id=prompt.prompt_id,
    )
    records_out: list[CallRecord] = []
    output: InterpretOutput | None = None
    problem = ""
    for attempt in (1, 2):
        try:
            response = call_model(request)
        except (ProviderMalformedJSON, ProviderSchemaViolation) as exc:
            if exc.record is not None:
                records_out.append(exc.record)
            problem = exc.message
            if attempt == 1:
                request = request.with_repair(exc.raw_text, problem, call_id=call_ids())
            continue
        records_out.append(response.record)
        assert isinstance(response.parsed, InterpretOutput)
        output = response.parsed
        break
    used = tuple(r.call_id for r in records_out)
    if output is None:
        return [
            unresolved_interpretation(
                r, view, failure="malformed_output", note=problem, call_ids=used
            )
            for r in batch
        ], records_out
    by_id: dict[str, InterpretItem] = {}
    extra: list[str] = []
    for item in output.interpretations:
        if item.observation_id in ids and item.observation_id not in by_id:
            by_id[item.observation_id] = item
        else:
            extra.append(item.observation_id)
    results: list[LiveInterpretation] = []
    for record in batch:
        oid = record.observation.observation_id
        reading = by_id.get(oid)
        if reading is None:
            results.append(
                unresolved_interpretation(
                    record,
                    view,
                    failure="missing",
                    note="no interpretation returned",
                    call_ids=used,
                )
            )
            continue
        live = validate_item(reading, record, view, handled=[*handled, *results])
        notes = live.server_notes
        if extra:
            notes = (*notes, f"ignored readings for ids outside the batch: {', '.join(extra)}")
        results.append(live.model_copy(update={"model_call_ids": used, "server_notes": notes}))
    return results, records_out


def unresolved_interpretation(
    record: ObservationRecord,
    view: EventStateView,
    *,
    failure: InterpretFailure,
    note: str,
    call_ids: tuple[str, ...] = (),
) -> LiveInterpretation:
    """A notice that could not be read: kept as evidence, contributes no claim."""
    obs = record.observation
    spec = ChangeSpec(
        change_id=f"chg_{obs.observation_id}",
        event_id=view.event_id,
        based_on_revision=view.revision,
        subject_id=_record_subject(record, view) or view.event_id,
        change_kind="unresolved",
        valid_window=_window(record),
        evidence_refs=(obs.observation_id,),
        interpretation=f"Not interpreted ({failure}); the notice contributes no claim.",
        unresolved_fields=("interpretation",),
        proposed_checks=(),
    )
    return _base(record, view, spec).model_copy(
        update={
            "standing": "unresolved",
            "failure": failure,
            "server_notes": (note[:MAX_TEXT_CHARS],) if note else (),
            "model_call_ids": call_ids,
        }
    )


# ---------------------------------------------------------------------------------- validation


def validate_item(
    item: InterpretItem,
    record: ObservationRecord,
    view: EventStateView,
    *,
    handled: Sequence[LiveInterpretation],
) -> LiveInterpretation:
    """Resolve the model's reading against public state (never trusting its ids)."""
    obs = record.observation
    resources = {r.definition.resource_id: r for r in view.resources}
    entities = set(resources) | {a.definition.activity_id for a in view.activities}
    entities.add(view.event_id)
    notes: list[str] = []
    unresolved = list(dict.fromkeys(f.strip()[:64] for f in item.unresolved_fields if f.strip()))
    failure: InterpretFailure | None = None
    kind: ChangeKind = item.change_kind
    standing: Standing = "no_claim"

    subject = (item.subject_id or "").strip() or None
    if subject is not None and subject not in entities:
        notes.append(f"subject {subject[:64]!r} is not a registered entity; left unresolved")
        failure, subject, kind = "unknown_entity", None, "unresolved"
        unresolved.append("subject")
    record_subject = _record_subject(record, view)
    if subject is not None and record_subject is not None and subject != record_subject:
        notes.append(f"subject {subject} conflicts with the record's entity {record_subject}")
        subject, kind = None, "unresolved"
        unresolved.append("subject")
    order = (item.order_ref or "").strip().upper() or None
    if order is not None and not _ORDER.match(order):
        notes.append("order reference is not a booking reference; ignored")
        order = None
    if order is not None and subject is None and failure is None and kind != "unresolved":
        named = [rid for rid, r in resources.items() if r.definition.terms.booking_ref == order]
        if len(named) == 1:
            subject = named[0]
            notes.append(f"subject {subject} resolved from its booking reference {order}")
    inapplicable: list[str] = []
    if item.applicability == "inapplicable":
        inapplicable.append("the reading marks it as about another event or booking")
    if order is not None and subject in resources:
        booking = resources[subject].definition.terms.booking_ref
        if booking != order:
            inapplicable.append(f"order {order} is not {subject}'s booking ({booking or 'none'})")
    referenced = _date(item.referenced_date)
    day = event_local_date(view.goal, view.timezone)
    if referenced == "invalid":
        notes.append("referenced date is not YYYY-MM-DD; ignored")
    elif referenced is not None and referenced != day:
        inapplicable.append(f"referenced date {referenced.isoformat()} is not the event date")

    eta = _local_time(item.claimed_eta_local, day, view.timezone)
    promised = _local_time(item.promised_local, day, view.timezone)
    if eta == "invalid":
        notes.append("claimed ETA is not HH:MM; left unresolved")
        unresolved.append("claimed_eta")
        eta = None
    if promised == "invalid":
        notes.append("promised time is not HH:MM; ignored")
        promised = None
    assert not isinstance(eta, str) and not isinstance(promised, str)

    resource_id = subject if subject in resources else None
    if kind in ("delay", "unavailability"):
        if resource_id is None:
            notes.append(f"a {kind} claim needs a registered resource subject")
            kind = "unresolved"
            unresolved.append("subject")
        elif kind == "delay" and eta is None:
            unresolved.append("claimed_eta")
    if kind != "delay":
        eta = None
    if inapplicable:
        standing = "inapplicable"
    elif kind == "unresolved":
        standing = "unresolved"
    elif kind in ("delay", "unavailability") and resource_id is not None:
        standing = "claim"
    hearsay = (
        standing == "claim"
        and record.channel in SESSION_CHANNELS
        and resources[resource_id].definition.kind == "equipment"
        if resource_id is not None
        else False
    )
    visible = {r.observation.observation_id for r in view.observations}
    refs = [obs.observation_id]
    for ref in item.evidence_refs:
        if ref in visible and ref not in refs:
            refs.append(ref)
        elif ref not in visible:
            notes.append(f"evidence id {ref[:64]!r} names no visible observation; dropped")
    text = " ".join(item.interpretation.split())[:MAX_TEXT_CHARS] or "No interpretation text."
    spec = ChangeSpec(
        change_id=f"chg_{obs.observation_id}",
        event_id=view.event_id,
        based_on_revision=view.revision,
        subject_id=subject or record_subject or view.event_id,
        change_kind=kind,
        valid_window=_window(record),
        evidence_refs=tuple(refs),
        interpretation=text,
        unresolved_fields=tuple(dict.fromkeys(unresolved))[:8],
        proposed_checks=tuple(dict.fromkeys(item.proposed_checks)),
    )
    retracts = tuple(
        h.observation_id
        for h in handled
        if h.observation_id in obs.supersedes and h.source_id == obs.source_id
    )
    return _base(record, view, spec).model_copy(
        update={
            "standing": standing,
            "subject_resource_id": resource_id,
            "claimed_eta": eta,
            "promised_at": promised,
            "hearsay": hearsay,
            "retracts": retracts,
            "contains_instructions": item.contains_instructions,
            "failure": failure,
            "server_notes": tuple(notes + [f"inapplicable: {why}" for why in inapplicable]),
        }
    )


# ---------------------------------------------------------------------------------- helpers


def _base(record: ObservationRecord, view: EventStateView, spec: ChangeSpec) -> LiveInterpretation:
    obs = record.observation
    return LiveInterpretation(
        observation_id=obs.observation_id,
        change_spec=spec,
        standing="no_claim",
        subject_resource_id=None,
        channel=record.channel,
        source_id=obs.source_id,
        submitted_by=record.submitted_by,
        received_at=obs.received_at,
        revision_after=record.revision_after,
        correlation_group=obs.correlation_group,
        normalized_text=normalize_text(obs.text),
    )


def _record_subject(record: ObservationRecord, view: EventStateView) -> str | None:
    """The record's own entity when it is a registered resource (server-side provenance)."""
    entity = record.observation.entity_id
    return entity if any(r.definition.resource_id == entity for r in view.resources) else None


def _window(record: ObservationRecord) -> PlanningWindow:
    window = record.observation.valid_window
    return PlanningWindow(start=fmt_ts(window.start), end=fmt_ts(window.end))


def _date(text: str | None) -> date | None | Literal["invalid"]:
    if text is None or not text.strip():
        return None
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return "invalid"


def _local_time(text: str | None, day: date, tz: str) -> datetime | None | Literal["invalid"]:
    if text is None or not text.strip():
        return None
    match = _HHMM.match(text.strip())
    if match is None:
        return "invalid"
    local = datetime.combine(day, time(int(match.group(1)), int(match.group(2))), ZoneInfo(tz))
    return to_utc(local)


def _context(view: EventStateView) -> dict[str, Any]:
    return {
        "event_id": view.event_id,
        "event_date": event_local_date(view.goal, view.timezone).isoformat(),
        "timezone": view.timezone,
        "now_local": local_label(view.clock, view.timezone),
        "revision": view.revision,
        "registered_resources": [
            {
                "resource_id": r.definition.resource_id,
                "label": r.definition.label,
                "kind": r.definition.kind,
                "booking_ref": r.definition.terms.booking_ref,
                "status": r.status,
            }
            for r in view.resources
        ],
        "registered_activities": [
            {"activity_id": a.definition.activity_id, "label": a.definition.label}
            for a in view.activities
        ],
    }


def _observation_payload(record: ObservationRecord, view: EventStateView) -> dict[str, Any]:
    obs = record.observation
    return {
        "observation_id": obs.observation_id,
        "kind": obs.kind,
        "record_entity_id": obs.entity_id,
        "source_id": obs.source_id,
        "channel": record.channel,
        "observed_at_local": local_label(obs.observed_at, view.timezone),
        "received_at_local": local_label(obs.received_at, view.timezone),
        "correlation_group": obs.correlation_group,
        "supersedes": list(obs.supersedes),
        "text": obs.text,
    }
