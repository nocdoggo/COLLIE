"""Objective components, weights and deterministic ranking.

All terms are integers and shown individually. The weighted total is
``start_shift*w_start + changed*w_change + cents*w_spend // 100 + removed*w_optional +
notifications*w_notify``. Feasible candidates are ranked by the configured tie-breaks
(``objective_total``, ``changed_activities``, ``additional_committed_cents``,
``candidate_signature`` by default), always ending with the signature for a total order.
Every other candidate follows, sorted by signature, without a rank.
"""

from __future__ import annotations

from collections.abc import Callable

from plan_b.domain.models import (
    ActivityDef,
    Assignment,
    CandidateResult,
    ObjectiveComponents,
    ObjectiveWeights,
    ResourceView,
)
from plan_b.domain.timeutil import minutes_between

COMPONENTS = (
    "start_shift_minutes",
    "changed_activities",
    "additional_committed_cents",
    "optional_activities_removed",
    "participant_notifications",
)

SortPart = tuple[int, str]

TIE_BREAKS: dict[str, Callable[[CandidateResult], SortPart]] = {
    "objective_total": lambda c: (c.objective.total, ""),
    "changed_activities": lambda c: (c.objective.changed_activities, ""),
    "additional_committed_cents": lambda c: (c.objective.additional_committed_cents, ""),
    "candidate_signature": lambda c: (0, c.signature),
}


def objective_components(
    *,
    active: dict[str, Assignment],
    assignments: tuple[Assignment, ...],
    changed: tuple[str, ...],
    additional_committed_cents: int,
    activities: dict[str, ActivityDef],
    resources: dict[str, ResourceView],
    weights: ObjectiveWeights,
) -> ObjectiveComponents:
    candidate = {a.activity_id: a for a in assignments}
    shift = sum(
        abs(minutes_between(active[aid].start, new.start))
        for aid, new in candidate.items()
        if aid in active
    )
    removed = sum(
        1
        for aid in active
        if aid not in candidate and aid in activities and not activities[aid].required
    )
    notified: set[str] = set()
    for aid, new in candidate.items():
        old = active.get(aid)
        if old is None or old.start == new.start:
            continue
        for rid in (*old.resource_ids, *new.resource_ids):
            resource = resources.get(rid)
            if resource is not None and resource.definition.kind == "person":
                notified.add(rid)
    terms = {
        "start_shift_minutes": shift,
        "changed_activities": len(changed),
        "additional_committed_cents": additional_committed_cents,
        "optional_activities_removed": removed,
        "participant_notifications": len(notified),
    }
    weighted = {
        "start_shift_minutes": shift * weights.start_shift_per_minute,
        "changed_activities": len(changed) * weights.changed_activity,
        "additional_committed_cents": additional_committed_cents
        * weights.spend_per_100_cents
        // 100,
        "optional_activities_removed": removed * weights.optional_activity_removed,
        "participant_notifications": len(notified) * weights.participant_notification,
    }
    return ObjectiveComponents(
        start_shift_minutes=terms["start_shift_minutes"],
        changed_activities=terms["changed_activities"],
        additional_committed_cents=terms["additional_committed_cents"],
        optional_activities_removed=terms["optional_activities_removed"],
        participant_notifications=terms["participant_notifications"],
        weighted=weighted,
        total=sum(weighted.values()),
    )


def unsupported_tie_breaks(tie_breaks: tuple[str, ...]) -> list[str]:
    return [name for name in tie_breaks if name not in TIE_BREAKS]


def ranking_key(candidate: CandidateResult, tie_breaks: tuple[str, ...]) -> tuple[SortPart, ...]:
    unknown = unsupported_tie_breaks(tie_breaks)
    if unknown:
        raise ValueError(f"unsupported tie-breaks: {', '.join(unknown)}")
    names = [*tie_breaks]
    if "candidate_signature" not in names:
        names.append("candidate_signature")
    return tuple(TIE_BREAKS[name](candidate) for name in names)


def is_feasible(candidate: CandidateResult) -> bool:
    return candidate.constraint_status == "feasible_under_assumptions"


def rank_candidates(
    candidates: list[CandidateResult], tie_breaks: tuple[str, ...]
) -> tuple[CandidateResult, ...]:
    """Feasible candidates by rank (1..n), then the rest by signature with ``rank=None``."""
    feasible = sorted(
        (c for c in candidates if is_feasible(c)), key=lambda c: ranking_key(c, tie_breaks)
    )
    others = sorted((c for c in candidates if not is_feasible(c)), key=lambda c: c.signature)
    ranked = [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(feasible)]
    unranked = [c.model_copy(update={"rank": None}) for c in others]
    return tuple(ranked + unranked)
