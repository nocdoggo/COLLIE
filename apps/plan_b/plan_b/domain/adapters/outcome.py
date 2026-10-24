"""Outcome records shared by the core scorer and the domain adapters.

``score_episode`` (``evaluation/scoring.py``) owns the domain-independent parts of an outcome
report: counters, spend limits and runner-side predicates. A domain adapter's
``score_outcome`` owns goal attainment and the executed domain-rule violations. Both read the
same persisted visible records through ``OutcomeRecords``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from plan_b.domain.models import (
    ActivityOutcome,
    ActivityView,
    EpisodeHistory,
    EventStateView,
    PlanView,
)
from plan_b.domain.timeutil import local_label

T = TypeVar("T")


@dataclass(frozen=True)
class Violation:
    category: str
    message: str


@dataclass(frozen=True)
class DomainOutcome:
    """A domain adapter's part of an outcome report."""

    activities: tuple[ActivityOutcome, ...]
    goal_attained: bool  # the domain goal is met, before executed violations are counted
    unmet: tuple[str, ...]  # why it is not (empty when attained)
    violations: tuple[Violation, ...]  # executed domain-rule violations, in report order


class OutcomeRecords:
    """Indexes over the persisted records of one episode."""

    def __init__(self, final: EventStateView, history: EpisodeHistory) -> None:
        self.final = final
        self.history = history
        self.receipts = _merge(history.receipts, final.receipts, lambda r: r.receipt_id)
        self.receipt_by_id = {r.receipt_id: r for r in self.receipts}
        self.decisions = _merge(history.decisions, final.decisions, lambda d: d.decision_id)
        self.resources = {r.definition.resource_id: r.definition for r in final.resources}
        self.observation_revision = {
            rec.observation.observation_id: rec.revision_after for rec in final.observations
        }
        plans = _merge(final.plan_history, (final.plan,), lambda p: str(p.plan_version))
        self.plans = sorted(plans, key=lambda p: p.plan_version)

    def plan_at(self, at: datetime, revision: int | None) -> PlanView:
        """The plan in effect at a start: the latest plan applied before it, else the first."""
        chosen = self.plans[0]
        for plan in self.plans[1:]:
            if plan.applied_at is None:
                continue
            receipt = self.receipt_by_id.get(plan.applied_receipt_id or "")
            if receipt is not None and revision is not None:
                in_effect = receipt.revision_after <= revision
            else:
                in_effect = plan.applied_at <= at
            if in_effect:
                chosen = plan
        return chosen

    def before(
        self, at: datetime, revision: int | None, record_at: datetime, record_rev: int | None
    ) -> bool:
        """Whether a record was persisted no later than (at, revision)."""
        if revision is not None and record_rev is not None:
            return record_rev <= revision and record_at <= at
        return record_at <= at


def activity_outcome(view: ActivityView) -> ActivityOutcome:
    started = next((e.at for e in view.history if e.state == "started"), None)
    completed = next((e.at for e in view.history if e.state == "completed"), None)
    reasons: list[str] = []
    for e in view.history:
        if e.state == "failed":
            reasons.extend(e.reasons)
    return ActivityOutcome(
        activity_id=view.definition.activity_id,
        required=view.definition.required,
        lifecycle=view.lifecycle,
        started_at=started,
        completed_at=completed,
        failure_reasons=tuple(reasons),
    )


def required_completed(
    final: EventStateView, by_id: dict[str, ActivityOutcome], deadline: datetime
) -> tuple[bool, list[str]]:
    """Whether every goal-required activity completed by ``deadline``, and what is missing."""
    missing: list[str] = []
    for aid in final.goal.required_activity_ids:
        outcome = by_id.get(aid)
        if outcome is None:
            missing.append(f"{aid} is not a recorded activity")
        elif outcome.lifecycle != "completed" or outcome.completed_at is None:
            missing.append(f"{aid} is {outcome.lifecycle}")
        elif outcome.completed_at > deadline:
            missing.append(
                f"{aid} completed at {local_label(outcome.completed_at, final.timezone)}, after "
                "the deadline"
            )
    return not missing, missing


def _merge(first: Iterable[T], second: Iterable[T], key: Callable[[T], str]) -> list[T]:
    seen: dict[str, T] = {}
    for item in (*first, *second):
        seen.setdefault(key(item), item)
    return list(seen.values())
