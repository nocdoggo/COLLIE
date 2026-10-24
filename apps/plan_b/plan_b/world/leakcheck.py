"""Detect private runner input in payloads meant for policies, browsers or public traces.

Two kinds of markers:

* structural keys that only private cases use (``status_model``, ``never_expose_to_agent``,
  ``outcome_predicates`` ...), and the case's description and predicate descriptions;
* values that are not yet public at the payload's scenario time: a world event's record id and
  text before it is delivered, and a status record's id and text before an observation of it
  has been received.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from plan_b.domain.models import ObservationRecord, PrivateCase

PRIVATE_KEYS = (
    "never_expose_to_agent",
    "status_model",
    "world_events",
    "actor_scripts",
    "outcome_predicates",
    "expected_outcome",
    "ground_truth_note",
    "candidate_expectation",
    "planning_label",
    "case_ref",
    "available_from",
    "episode_private",
)


def _public_records(observations: Iterable[ObservationRecord], at: datetime | None) -> set[str]:
    return {
        o.observation.source_record_id
        for o in observations
        if at is None or o.observation.received_at <= at
    }


def private_markers(
    case: PrivateCase, observations: Iterable[ObservationRecord], at: datetime | None
) -> list[str]:
    """Strings that must not appear in a payload observed at scenario time ``at``
    (``at=None`` means "by the end of the episode")."""
    public = _public_records(observations, at)
    markers: list[str] = [f'"{k}"' for k in PRIVATE_KEYS]
    markers.append(case.description)
    markers.extend(p.description for p in case.outcome_predicates)
    for rec in case.status_model:
        if rec.response is None:
            continue
        if rec.response.source_record_id not in public:
            markers.append(rec.response.source_record_id)
            markers.append(rec.response.text)
    for ev in case.world_events:
        if ev.source_record_id not in public:
            markers.append(ev.source_record_id)
            markers.append(ev.text)
    # Longest first so reports name the most specific match; drop trivially short strings.
    return sorted({m for m in markers if len(m) >= 6}, key=len, reverse=True)


def find_leaks(
    payload_json: str,
    case: PrivateCase,
    observations: Iterable[ObservationRecord],
    at: datetime | None,
) -> list[str]:
    return [m for m in private_markers(case, list(observations), at) if m in payload_json]
