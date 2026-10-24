"""Supported message forms of the deterministic rule policy (contract section 11).

Pure functions: no files, no store, no clock. An observation is interpreted from its own
record, the caller's visible resources, the event date and timezone, and the notices the
policy has already handled.

A notice is read sentence by sentence after a leading ``Fwd:``/``Fw:`` is stripped (and marked
as forwarded), the text is lowercased and its whitespace collapsed, and the dots of ``a.m.``/
``p.m.`` are masked. Sentences end at ``.``, ``!``, ``?`` or ``;`` followed by whitespace. Every
sentence must be one of these forms in full (optional trailing period):

* delay claim: ``[<determiner/possessive>] <subject: 1-3 words> delivery may be [about] N
  minute(s) later than the promised H[:MM] a.m./p.m. arrival``; claimed ETA = the promised
  time on the event date in the event timezone + N minutes;
* cancellation claim: ``[Reminder:|Update:|Notice:] [<subject: 0-2 words>] order P<digits>
  [for the <Month> <day> <0-3 words>] was|has been|is cancel(l)ed[, so no <word> will arrive
  for that booking]``;
* status pointer: ``Please check order P<digits> for the latest status``;
* greeting or sign-off: ``Hi``, ``Hello``, ``Thanks``, ``Thank you``, ``Regards`` (``.``/``!``).

Subject words are words of a registered resource's id or label (a cancellation subject may
start with a determiner or possessive); the words after a date are such words or one of
event, showcase, workshop, session, booking, delivery, rental, hire, meeting, seminar,
lecture, class, conference, talk. A message holds exactly one claim sentence. Any other
sentence, a second claim, no claim, or a claim that does not match its form exactly makes the
whole message ``unresolved`` (field ``wording``); nothing is parsed partially. A question,
negation, condition, retraction, report of someone else's words or hedge is therefore never
asserted: no form admits those words.

The subject is the record's entity when it is a registered resource, else the resource whose
``terms.booking_ref`` the order names, else the delay subject phrase: a phrase equal to a
resource id or label names it; otherwise its last word must be a word of the resource and
every other word must be one of this resource's words (``backup projector`` is
``backup_projector``, never ``projector``). A phrase matching several resources stays
``unresolved`` with the candidates listed; a phrase that contradicts the subject chosen from
the entity or order leaves the subject unresolved.

An order reference must equal the subject resource's ``terms.booking_ref`` and a referenced
date must be the event date; otherwise the notice is ``inapplicable``. A notice with the same
correlation group and normalized text as an already handled notice is a ``duplicate`` (one
evidence lineage, never corroboration). A notice whose ``supersedes`` names a handled notice
from the same ``source_id`` retracts it (``retracts``); a source cannot retract another
source's notice. A claim submitted through an event session (participant or organizer) about
equipment is ``hearsay``. Instruction words are flagged and have no effect.

Verification only. An ``unresolved`` notice (not inapplicable, not a duplicate) that
identifies exactly one registered equipment resource, by the record's entity, by an order
reference equal to its ``booking_ref``, by its exact id or label in the text (a name that is
also part of another resource's name, such as ``projector`` inside ``backup projector``,
identifies neither) or by a claim form's subject phrase, carries ``verify_subject_id``: the
policy may check that resource with its registered status source, but the notice is never a
claim (no hypothesis, hold, ask or plan change comes from it). An order reference that names
no registered booking, or a second identified equipment resource, leaves it unset. Status and
arrival records are typed evidence: their ``structured`` facts are used directly and their
text is never pattern-matched.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from plan_b.domain.models import (
    EventGoal,
    ObservationChannel,
    ObservationKind,
    ObservationRecord,
    ResourceStatus,
    ResourceView,
    Strict,
    UtcDatetime,
)
from plan_b.domain.timeutil import to_utc

PARSER_VERSION = "rules-parser/1.2.0"

ChangeKind = Literal["delay", "unavailability", "availability", "no_change", "unresolved"]
EvidenceStatus = Literal[
    "unresolved", "corroborated", "contradicted", "superseded", "inapplicable", "duplicate"
]
InterpretationBasis = Literal["message_grammar", "typed_status", "check_in_record"]

NOTICE_KINDS: tuple[ObservationKind, ...] = ("notice", "resource_offer", "policy")
# Channels through which an event principal submits content; everything else is delivered or
# recorded by the scenario (fixture, scenario delivery, status tool, arrival record).
SESSION_CHANNELS: tuple[ObservationChannel, ...] = ("participant_session", "organizer_session")
UNSUPPORTED_WORDING = "wording outside the supported message forms"

_FORWARD_PREFIX = re.compile(r"^\s*(?:fwd|fw)\s*:\s*", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")
_INSTRUCTION = re.compile(
    r"\b(ignor\w*|approv\w*|authori[sz]\w*|grant\w*|budget\w*|overrid\w*|disregard\w*|bypass\w*)\b"
)
_ORDER = re.compile(r"\border\s+(?P<order>p\d+)\b")
_MERIDIEM = re.compile(r"(?<![a-z])[ap]\.\s?m\.")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+")
_WORD = r"[a-z0-9][a-z0-9_-]*"
# Words that make an unsupported notice worth verifying: it talks about delivery status.
_STATUS_WORDS = re.compile(
    r"\b(?:late|later|delay\w*|cancel\w*|eta|arriv\w*|deliver\w*|dispatch\w*|shipp\w*"
    r"|minutes?|hours?|on\s+time|postpon\w*|resched\w*|stuck|traffic|won['’]?t\s+make"
    r"|not\s+coming|no\s+longer\s+coming|status|free|availab\w*|unavailab\w*|booked)\b"
)
_PRECEDING_WORD = re.compile(r"([a-z0-9_'’-]+)\s*$")
# Modifiers that make a name refer to a different item ("the spare projector").
_OTHER_ITEM = frozenset(
    {
        "spare",
        "other",
        "another",
        "second",
        "extra",
        "new",
        "replacement",
        "rental",
        "borrowed",
        "different",
        "old",
    }
)
_DETERMINERS = frozenset(
    {"the", "a", "an", "our", "your", "their", "my", "its", "his", "her", "this", "that"}
)
_MONTH = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
# Words that may describe a booking after its date ("for the October 29 workshop").
_BOOKING_WORDS = frozenset(
    {
        "event",
        "showcase",
        "workshop",
        "session",
        "booking",
        "delivery",
        "rental",
        "hire",
        "meeting",
        "seminar",
        "lecture",
        "class",
        "conference",
        "talk",
    }
)
# Sentence forms; each is matched against a whole masked sentence (``fullmatch``).
_DELAY_FORM = re.compile(
    rf"(?:(?:{'|'.join(sorted(_DETERMINERS))})\s+)?(?P<entity>{_WORD}(?:\s+{_WORD}){{0,2}})"
    r"\s+delivery\s+may\s+be\s+(?:about\s+)?(?P<minutes>\d{1,3})\s+minutes?\s+later\s+than"
    r"\s+the\s+promised\s+(?P<hour>\d{1,2})(?::(?P<minute>[0-5]\d))?\s*(?P<meridiem>[ap])_\s?m_"
    r"\s+arrival\.?"
)
_CANCEL_FORM = re.compile(
    rf"(?:(?:reminder|update|notice):\s+)?(?P<subject>(?:{_WORD}\s+){{0,2}})order\s+"
    rf"(?P<order>p\d+)(?:\s+for\s+the\s+(?P<month>{_MONTH})\s+(?P<day>\d{{1,2}})"
    rf"(?:st|nd|rd|th)?(?P<tail>(?:\s+{_WORD}){{0,3}}))?\s+(?:was|has\s+been|is)\s+cancell?ed"
    rf"(?:,\s+so\s+no\s+{_WORD}\s+will\s+arrive\s+for\s+that\s+booking)?\.?"
)
_STATUS_POINTER = re.compile(r"please\s+check\s+order\s+p\d+\s+for\s+the\s+latest\s+status\.?")
_GREETING = re.compile(r"(?:hi|hello|thanks|thank\s+you|regards)[.!]?")
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_DATE = re.compile(
    rf"\b(?P<month>{_MONTH})\.?\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(?P<year>\d{{4}})\b)?"
)


class ClaimDetails(Strict):
    """What the record states. Values are claims until typed evidence answers them."""

    entity_text: str | None = None
    subject_candidates: tuple[str, ...] = ()  # resources an ambiguous entity phrase matches
    order_ref: str | None = None
    promised_at: UtcDatetime | None = None
    delay_minutes: int | None = Field(default=None, ge=0)
    claimed_eta: UtcDatetime | None = None
    referenced_date: date | None = None
    forwarded: bool = False
    reported_status: ResourceStatus | None = None
    reported_eta: UtcDatetime | None = None
    status_code: str | None = None


class Interpretation(Strict):
    """Typed reading of one observation (the runtime form of a planning ``change_spec``).

    ``applicable`` is true only when the record contributes a claim about this event's
    registered resource: the message is a supported form, identity checks passed, the subject
    resolved, and it is not a duplicate of a handled notice. ``hearsay`` marks a claim whose
    submitter does not speak for the subject; ``retracts`` lists handled notices of the same
    source that this one supersedes. ``verify_subject_id`` is set only on an unresolved
    notice that identifies exactly one registered equipment resource: that resource may be
    verified, but the notice is never weighed as a claim. ``evidence_status`` describes the
    record, not a probability.
    """

    observation_id: str
    parser_version: str = PARSER_VERSION
    basis: InterpretationBasis
    observation_kind: ObservationKind
    change_kind: ChangeKind
    subject_id: str | None
    claims: ClaimDetails
    evidence_status: EvidenceStatus
    applicable: bool
    reasons: tuple[str, ...]
    identity_failures: tuple[str, ...] = ()
    contains_instructions: bool
    instruction_words: tuple[str, ...] = ()
    unresolved_fields: tuple[str, ...] = ()
    correlation_group: str
    normalized_text: str
    duplicate_of: str | None = None
    source_id: str
    channel: ObservationChannel
    submitted_by: str | None = None
    hearsay: bool = False
    retracts: tuple[str, ...] = ()
    verify_subject_id: str | None = None
    received_at: UtcDatetime
    revision_after: int


@dataclass(frozen=True)
class _ClaimSentence:
    """The one claim sentence of a supported message."""

    kind: Literal["delay", "cancellation"]
    match: re.Match[str]
    entity_text: str | None


def strip_forward_prefix(text: str) -> tuple[str, bool]:
    """Remove every leading ``Fwd:``/``Fw:`` marker; report whether any was present."""
    forwarded = False
    while True:
        match = _FORWARD_PREFIX.match(text)
        if match is None:
            return text, forwarded
        forwarded = True
        text = text[match.end() :]


def normalize_text(text: str) -> str:
    """Forward prefix stripped, lowercased, whitespace collapsed."""
    stripped, _ = strip_forward_prefix(text)
    return _WHITESPACE.sub(" ", stripped.lower()).strip()


def instruction_words(text: str) -> tuple[str, ...]:
    """Embedded instruction words, in order of first appearance (flagged, never obeyed)."""
    seen: list[str] = []
    for match in _INSTRUCTION.finditer(text.lower()):
        word = match.group(1)
        if word not in seen:
            seen.append(word)
    return tuple(seen)


def event_local_date(goal: EventGoal, timezone: str) -> date:
    """The event's calendar date in its own timezone (from the public start)."""
    return goal.public_start.astimezone(ZoneInfo(timezone)).date()


def interpret_observation(
    record: ObservationRecord,
    *,
    resources: Sequence[ResourceView],
    event_date: date | None,
    timezone: str,
    goal: EventGoal,
    event_id: str | None = None,
    handled: Sequence[Interpretation] = (),
) -> Interpretation:
    """Interpret one observation against visible state and previously handled notices."""
    obs = record.observation
    normalized = normalize_text(obs.text)
    _, forwarded = strip_forward_prefix(obs.text)
    words = instruction_words(normalized)
    day = event_date if event_date is not None else event_local_date(goal, timezone)
    by_id = {r.definition.resource_id: r for r in resources}

    if obs.kind == "status":
        return _typed_status(record, by_id, normalized, words)
    if obs.kind == "check_in":
        subject = obs.entity_id if obs.entity_id in by_id else None
        return _build(
            record,
            normalized,
            words,
            basis="check_in_record",
            change_kind="availability",
            subject_id=subject,
            claims=ClaimDetails(),
            evidence_status="corroborated",
            applicable=subject is not None,
            reasons=("participant check-in recorded by the server within the participant's scope",),
            unresolved_fields=() if subject is not None else ("subject",),
        )

    reasons: list[str] = []
    inapplicable: list[str] = []
    unresolved: list[str] = []
    change: ChangeKind = "unresolved"
    entity_text: str | None = None
    promised_at: datetime | None = None
    delay_minutes: int | None = None
    claimed_eta: datetime | None = None

    orders = sorted({m.group("order").upper() for m in _ORDER.finditer(normalized)})
    order_ref = orders[0] if len(orders) == 1 else None
    if len(orders) > 1:
        unresolved.append("order_ref")
        reasons.append(f"several order references ({', '.join(orders)})")

    # Only the dots of a.m./p.m. are masked, so they never end a sentence.
    masked = _MERIDIEM.sub(lambda m: m.group(0).replace(".", "_"), normalized)
    claim, problem = _read_form(masked, _vocabulary(resources))
    if claim is None:
        unresolved.append("wording")
        reasons.append(f"{UNSUPPORTED_WORDING} ({problem}); nothing in it is read as a claim")
    elif claim.kind == "delay":
        match = claim.match
        entity_text = claim.entity_text
        delay_minutes = int(match.group("minutes"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        if 1 <= hour <= 12:
            hour24 = hour % 12 + (12 if match.group("meridiem") == "p" else 0)
            local = datetime.combine(day, time(hour24, minute), tzinfo=ZoneInfo(timezone))
            promised_at = to_utc(local)
            claimed_eta = promised_at + timedelta(minutes=delay_minutes)
            change = "delay" if delay_minutes > 0 else "no_change"
            reasons.append(
                f"delay form: {delay_minutes} minutes after the promised "
                f"{hour}:{minute:02d} {match.group('meridiem')}.m. arrival on {day.isoformat()}"
            )
        else:
            unresolved.append("promised_time")
            reasons.append(f"promised hour {hour} is not a 12-hour clock time")
    else:
        entity_text = claim.entity_text
        change = "unavailability"
        reasons.append(f"cancellation form for order {claim.match.group('order').upper()}")

    referenced = _referenced_date(normalized, day.year)
    if referenced == "invalid":
        unresolved.append("referenced_date")
        reasons.append("text names a calendar date that does not exist")
        referenced_date: date | None = None
    else:
        referenced_date = referenced
        if referenced_date is not None and referenced_date != day:
            inapplicable.append(
                f"refers to {referenced_date.isoformat()} but the event is on {day.isoformat()}"
            )

    if event_id is not None and obs.event_id != event_id:
        inapplicable.append(f"observation is scoped to event {obs.event_id}, not {event_id}")

    subject_id: str | None = None
    ambiguous: list[str] = []
    if change != "unresolved":
        subject_id = _resolve_subject(
            obs.entity_id,
            entity_text,
            order_ref,
            by_id,
            inapplicable,
            unresolved,
            reasons,
            ambiguous,
        )
    hearsay = (
        record.channel in SESSION_CHANNELS
        and subject_id is not None
        and by_id[subject_id].definition.kind == "equipment"
    )
    if hearsay:
        reasons.append(
            f"submitted by {record.submitted_by or obs.source_id} through {record.channel}: an "
            f"event principal speaks for its own role, not for {subject_id}'s delivery, so the "
            "claim is hearsay (it may prompt verification but is not weighed as a declared "
            "outcome)"
        )

    retracts = _retractions(record, handled, reasons)
    duplicate_of = _duplicate_of(obs.observation_id, obs.correlation_group, normalized, handled)
    if words:
        reasons.append(
            f"embedded instruction words ({', '.join(words)}) are data and have no effect"
        )

    status: EvidenceStatus
    if duplicate_of is not None:
        status = "duplicate"
        reasons.append(
            f"same correlation group and text as handled notice {duplicate_of}: one evidence "
            "lineage, not corroboration"
        )
    elif inapplicable:
        status = "inapplicable"
    else:
        status = "unresolved"
    applicable = (
        duplicate_of is None
        and not inapplicable
        and not unresolved
        and change != "unresolved"
        and subject_id is not None
    )
    verify_subject_id: str | None = None
    if not applicable and status == "unresolved":
        named = set(ambiguous)
        if entity_text is not None:
            named.update(r.definition.resource_id for r in _phrase_matches(entity_text, resources))
        verify_subject_id = _verify_subject(
            obs.entity_id, orders, normalized, named, by_id, reasons
        )
    return _build(
        record,
        normalized,
        words,
        basis="message_grammar",
        change_kind=change,
        subject_id=subject_id,
        claims=ClaimDetails(
            entity_text=entity_text,
            subject_candidates=tuple(ambiguous),
            order_ref=order_ref,
            promised_at=promised_at,
            delay_minutes=delay_minutes,
            claimed_eta=claimed_eta,
            referenced_date=referenced_date,
            forwarded=forwarded,
        ),
        evidence_status=status,
        applicable=applicable,
        reasons=tuple(inapplicable + reasons),
        identity_failures=tuple(inapplicable),
        unresolved_fields=tuple(dict.fromkeys(unresolved)),
        duplicate_of=duplicate_of,
        hearsay=hearsay,
        retracts=retracts,
        verify_subject_id=verify_subject_id,
    )


def assess_claim(
    claim: Interpretation,
    *,
    domain_status: ResourceStatus,
    reported_eta: datetime | None,
) -> EvidenceStatus:
    """Relate a notice's claim to typed status evidence received after it.

    Delay: an ETA after the promised time corroborates, an ETA at or before it contradicts;
    a status without ETA, an arrival or an unavailability supersedes the claim. Cancellation:
    unavailable corroborates, available/expected contradicts."""
    if claim.change_kind == "delay":
        if domain_status != "expected" or reported_eta is None:
            return "superseded"
        promised = claim.claims.promised_at
        if promised is not None and reported_eta <= promised:
            return "contradicted"
        return "corroborated"
    if claim.change_kind == "unavailability":
        if domain_status == "unavailable":
            return "corroborated"
        if domain_status in ("available", "expected"):
            return "contradicted"
        return "superseded"
    if claim.change_kind == "no_change":
        return "superseded"
    return claim.evidence_status


def _build(
    record: ObservationRecord,
    normalized: str,
    words: tuple[str, ...],
    *,
    basis: InterpretationBasis,
    change_kind: ChangeKind,
    subject_id: str | None,
    claims: ClaimDetails,
    evidence_status: EvidenceStatus,
    applicable: bool,
    reasons: tuple[str, ...],
    identity_failures: tuple[str, ...] = (),
    unresolved_fields: tuple[str, ...] = (),
    duplicate_of: str | None = None,
    hearsay: bool = False,
    retracts: tuple[str, ...] = (),
    verify_subject_id: str | None = None,
) -> Interpretation:
    obs = record.observation
    return Interpretation(
        observation_id=obs.observation_id,
        basis=basis,
        observation_kind=obs.kind,
        change_kind=change_kind,
        subject_id=subject_id,
        claims=claims,
        evidence_status=evidence_status,
        applicable=applicable,
        reasons=reasons,
        identity_failures=identity_failures,
        contains_instructions=bool(words),
        instruction_words=words,
        unresolved_fields=unresolved_fields,
        correlation_group=obs.correlation_group,
        normalized_text=normalized,
        duplicate_of=duplicate_of,
        source_id=obs.source_id,
        channel=record.channel,
        submitted_by=record.submitted_by,
        hearsay=hearsay,
        retracts=retracts,
        verify_subject_id=verify_subject_id,
        received_at=obs.received_at,
        revision_after=record.revision_after,
    )


def _typed_status(
    record: ObservationRecord,
    by_id: dict[str, ResourceView],
    normalized: str,
    words: tuple[str, ...],
) -> Interpretation:
    obs = record.observation
    subject = obs.entity_id if obs.entity_id in by_id else None
    facts = record.structured
    if facts is None:
        return _build(
            record,
            normalized,
            words,
            basis="typed_status",
            change_kind="no_change",
            subject_id=subject,
            claims=ClaimDetails(),
            evidence_status="unresolved",
            applicable=False,
            reasons=(
                "status record without structured facts; its effect is read from the resource view",
            ),
            unresolved_fields=("structured",),
        )
    change: ChangeKind
    if facts.domain_status == "available":
        change = "availability"
    elif facts.domain_status == "unavailable":
        change = "unavailability"
    else:
        change = "no_change"
    return _build(
        record,
        normalized,
        words,
        basis="typed_status",
        change_kind=change,
        subject_id=subject,
        claims=ClaimDetails(
            reported_status=facts.domain_status,
            reported_eta=facts.reported_eta,
            status_code=facts.status_code,
        ),
        evidence_status="corroborated",
        applicable=subject is not None,
        reasons=(
            f"typed {obs.authority_scope} facts from {obs.source_id} ({facts.fact}: "
            f"{facts.status_code}, {facts.domain_status}) used directly",
        ),
        unresolved_fields=() if subject is not None else ("subject",),
    )


def _read_form(masked: str, vocabulary: Collection[str]) -> tuple[_ClaimSentence | None, str]:
    """The message's one claim sentence when every sentence is a supported form; otherwise
    None and what is unsupported."""
    sentences = [s for s in _SENTENCE_BREAK.split(masked) if s]
    claim: _ClaimSentence | None = None
    for index, sentence in enumerate(sentences, start=1):
        if _STATUS_POINTER.fullmatch(sentence) or _GREETING.fullmatch(sentence):
            continue
        found = _claim_sentence(sentence, vocabulary)
        where = f"sentence {index} of {len(sentences)}"
        if found is None:
            return None, f"{where} is not a supported form"
        if claim is not None:
            return None, f"{where} is a second claim"
        claim = found
    if claim is None:
        return None, "no sentence is a supported delay or cancellation form"
    return claim, ""


def _claim_sentence(sentence: str, vocabulary: Collection[str]) -> _ClaimSentence | None:
    delay = _DELAY_FORM.fullmatch(sentence)
    if delay is not None:
        entity = delay.group("entity")
        if all(w in vocabulary for w in entity.split()):
            return _ClaimSentence("delay", delay, entity)
        return None
    cancel = _CANCEL_FORM.fullmatch(sentence)
    if cancel is None:
        return None
    subject = cancel.group("subject").split()
    if subject and subject[0] in _DETERMINERS:
        subject = subject[1:]
    tail = (cancel.group("tail") or "").split()
    if not all(w in vocabulary for w in subject):
        return None
    if not all(w in vocabulary or w in _BOOKING_WORDS for w in tail):
        return None
    return _ClaimSentence("cancellation", cancel, " ".join(subject) or None)


def _referenced_date(text: str, year: int) -> date | None | Literal["invalid"]:
    match = _DATE.search(text)
    if match is None:
        return None
    month = _MONTHS[match.group("month")[:3]]
    try:
        return date(int(match.group("year") or year), month, int(match.group("day")))
    except ValueError:
        return "invalid"


def _entity_words(resource: ResourceView) -> set[str]:
    d = resource.definition
    words = {d.resource_id.lower(), *d.resource_id.lower().split("_")}
    words.update(w for w in re.split(r"[^a-z0-9]+", d.label.lower()) if w)
    return words


def _vocabulary(resources: Sequence[ResourceView]) -> set[str]:
    """Every word of a registered resource's id or label: the only subject words a form
    admits."""
    return set().union(*(_entity_words(r) for r in resources))


def _names(resource: ResourceView) -> set[str]:
    """Whole phrases that name the resource exactly: its id (with or without underscores)
    and its label."""
    d = resource.definition
    rid = d.resource_id.lower()
    return {rid, rid.replace("_", " "), _WHITESPACE.sub(" ", d.label.lower()).strip()}


def _compatible(phrase: str, resource: ResourceView, known: set[str]) -> bool:
    """The phrase's last word is a word of the resource, and every other word that is a word
    of some registered resource is a word of this one."""
    words = phrase.split()
    own = _entity_words(resource)
    return words[-1] in own and all(w in own for w in words[:-1] if w in known)


def _phrase_matches(phrase: str, resources: Sequence[ResourceView]) -> list[ResourceView]:
    exact = [r for r in resources if phrase in _names(r)]
    if exact:
        return exact
    known = _vocabulary(resources)
    return [r for r in resources if _compatible(phrase, r, known)]


def _phrase_in(phrase: str, text: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"(?<![a-z0-9_-]){re.escape(phrase)}(?![a-z0-9_-])", text))


def _named_in_text(
    text: str, candidates: Sequence[ResourceView], resources: Sequence[ResourceView]
) -> set[str]:
    """Candidates whose exact id or label occurs in the text as a whole phrase. Where names
    overlap in the text, the longer one wins ("backup projector" names ``backup_projector``,
    not ``projector``). This only selects what may be *verified*; it never makes a claim."""
    del resources  # kept for the call signature; overlap is decided on the text itself
    spans: list[tuple[int, int, str]] = []
    for r in candidates:
        rid = r.definition.resource_id
        for name in _names(r):
            for m in _phrase_in(name, text):
                before = _PRECEDING_WORD.search(text[: m.start()])
                if before is not None and before.group(1) in _OTHER_ITEM:
                    continue  # "the spare projector" may be another item
                spans.append((m.start(), m.end(), rid))
    kept: list[tuple[int, int, str]] = []
    for start, end, rid in sorted(spans, key=lambda s: (s[0] - s[1], s[0])):
        if any(s < end and start < e and e - s > end - start for s, e, _ in kept):
            continue
        kept.append((start, end, rid))
    return {rid for _, _, rid in kept}


def _verify_subject(
    entity_id: str,
    orders: Sequence[str],
    normalized: str,
    named: set[str],
    by_id: dict[str, ResourceView],
    reasons: list[str],
) -> str | None:
    """The one registered equipment resource an unresolved notice identifies (entity, order
    reference, exact id or label, or the claim's own subject phrase), else None. A notice that
    says nothing about delivery status (no word such as late, delay, cancelled, ETA, arrival)
    identifies nothing: there is nothing to verify."""
    if not _STATUS_WORDS.search(normalized):
        reasons.append("it says nothing about delivery status, so nothing is verified")
        return None
    equipment = [r for r in by_id.values() if r.definition.kind == "equipment"]
    found = {r.definition.resource_id for r in equipment if r.definition.resource_id == entity_id}
    for order in orders:
        booked = [
            r for r in by_id.values() if (r.definition.terms.booking_ref or "").upper() == order
        ]
        if not booked:
            reasons.append(f"order {order} matches no registered booking, so nothing is verified")
            return None
        found.update(r.definition.resource_id for r in booked if r.definition.kind == "equipment")
    found.update(_named_in_text(normalized, equipment, tuple(by_id.values())))
    found.update(rid for rid in named if rid in by_id and by_id[rid].definition.kind == "equipment")
    if len(found) > 1:
        reasons.append(
            f"it identifies several equipment resources ({', '.join(sorted(found))}), so nothing "
            "is verified"
        )
        return None
    if not found:
        return None
    rid = found.pop()
    reasons.append(
        f"verification only: it identifies {rid}, so {rid}'s registered status source may be "
        "checked; the notice itself is never weighed as a claim"
    )
    return rid


def _resolve_subject(
    entity_id: str,
    entity_text: str | None,
    order_ref: str | None,
    by_id: dict[str, ResourceView],
    inapplicable: list[str],
    unresolved: list[str],
    reasons: list[str],
    ambiguous: list[str],
) -> str | None:
    subject = by_id.get(entity_id)
    booked = [
        r
        for r in by_id.values()
        if order_ref is not None and (r.definition.terms.booking_ref or "").upper() == order_ref
    ]
    if subject is None and len(booked) == 1:
        subject = booked[0]
    if subject is None and entity_text is not None:
        matches = _phrase_matches(entity_text, tuple(by_id.values()))
        if len(matches) == 1:
            subject = matches[0]
        elif len(matches) > 1:
            ambiguous.extend(sorted(r.definition.resource_id for r in matches))
            unresolved.append("subject")
            reasons.append(
                f"'{entity_text}' is ambiguous: it matches several resources "
                f"({', '.join(ambiguous)}), so the subject is not guessed"
            )
            return None
    if order_ref is not None:
        if subject is None:
            if not booked:
                inapplicable.append(f"order {order_ref} matches no registered booking")
        else:
            ref = subject.definition.terms.booking_ref
            rid = subject.definition.resource_id
            if ref is None:
                inapplicable.append(f"order {order_ref} cited but {rid} has no booking reference")
            elif ref.upper() != order_ref:
                inapplicable.append(f"order {order_ref} is not {rid}'s booking {ref}")
    if subject is None:
        if not inapplicable:
            unresolved.append("subject")
            reasons.append("the affected resource could not be resolved")
        return None
    known = _vocabulary(tuple(by_id.values()))
    if entity_text is not None and not _compatible(entity_text, subject, known):
        unresolved.append("subject")
        reasons.append(
            f"text names '{entity_text}' but the record concerns {subject.definition.resource_id}"
        )
    return subject.definition.resource_id


def _retractions(
    record: ObservationRecord, handled: Sequence[Interpretation], reasons: list[str]
) -> tuple[str, ...]:
    """Handled notices this record supersedes that came from the same source."""
    obs = record.observation
    prior = {h.observation_id: h for h in handled if h.basis == "message_grammar"}
    retracts: list[str] = []
    for ref in obs.supersedes:
        earlier = prior.get(ref)
        if earlier is None:
            reasons.append(f"supersedes {ref}, which is not a handled notice; nothing is retracted")
        elif earlier.source_id != obs.source_id:
            reasons.append(
                f"supersedes {ref} from {earlier.source_id}, but only that source can retract "
                "its notice"
            )
        else:
            retracts.append(ref)
            reasons.append(f"retracts {ref}, an earlier notice from the same source")
    return tuple(dict.fromkeys(retracts))


def _duplicate_of(
    observation_id: str,
    correlation_group: str,
    normalized: str,
    handled: Sequence[Interpretation],
) -> str | None:
    for prior in handled:
        if (
            prior.basis == "message_grammar"
            and prior.observation_id != observation_id
            and prior.correlation_group == correlation_group
            and prior.normalized_text == normalized
        ):
            return prior.duplicate_of or prior.observation_id
    return None
