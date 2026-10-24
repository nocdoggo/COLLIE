"""Detect private runner input in payloads meant for policies, browsers or public traces.

Two kinds of markers:

* structural keys that only private cases use (``status_model``, ``never_expose_to_agent``,
  ``outcome_predicates`` ...), and the case's description and predicate descriptions;
* values that are not yet public at the payload's scenario time: a world event's record id and
  text before it is delivered, and a status record's id, text and lineage
  (``response.correlation_group``) before an observation of it has been received.

What is public at a scenario time is every observation received by then: the episode's own
observations the caller passes, plus the public scenario's visible observations, which every
episode holds from its start. A lineage is public as soon as any public observation carries it,
so a status record whose lineage is a public notice's (the shipped ``projector_delivery_01`` of
the fixture notice ``obs_notice_01``) gets no lineage marker.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from plan_b.domain.fixtures import load_public_scenario
from plan_b.domain.models import Observation, ObservationRecord, PrivateCase

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


def _public_observations(
    case: PrivateCase, observations: Iterable[ObservationRecord], at: datetime | None
) -> list[Observation]:
    """Observations received by ``at`` (``None``: by the end of the episode), including the
    public scenario's visible ones, so a caller that passes no episode observations still
    counts the fixture notice."""
    received = [o.observation for o in observations]
    received.extend(load_public_scenario(case.scenario_id).visible_observations)
    return [o for o in received if at is None or o.received_at <= at]


def private_markers(
    case: PrivateCase, observations: Iterable[ObservationRecord], at: datetime | None
) -> list[str]:
    """Strings that must not appear in a payload observed at scenario time ``at``
    (``at=None`` means "by the end of the episode")."""
    public = _public_observations(case, observations, at)
    records = {o.source_record_id for o in public}
    lineages = {o.correlation_group for o in public}
    markers: list[str] = [f'"{k}"' for k in PRIVATE_KEYS]
    markers.append(case.description)
    markers.extend(p.description for p in case.outcome_predicates)
    for rec in case.status_model:
        if rec.response is None:
            continue
        if rec.response.source_record_id not in records:
            markers.append(rec.response.source_record_id)
            markers.append(rec.response.text)
            # Without a lineage of its own the observation joins "<entity_id>_status", which
            # names only a public entity. A lineage some public observation carries is public.
            group = rec.response.correlation_group
            if group is not None and group not in lineages:
                markers.append(group)
    for ev in case.world_events:
        if ev.source_record_id not in records:
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
