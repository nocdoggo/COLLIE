"""The narrow domain-adapter interface.

The shared core (store, authority, clock, revisions, idempotency, receipts, tools, replay)
is domain-independent. A domain adapter owns only:

* ``validate_config``: profile-specific checks on a public scenario, including that its
  initial plan passes the adapter's own hard checks;
* ``evaluate``: enumerate the configured finite candidate menu, check constraints, rank;
* ``revalidate``: re-run every check on a stored candidate against a fresh snapshot
  (``apply_plan`` calls this inside its write transaction);
* ``check_readiness``: prerequisites for one activity at a scenario time, strictly at its
  start (the clock engine) or as a preview of current evidence (the projection);
* ``score_outcome``: domain goal attainment and the executed domain-rule violations, computed
  from the visible final state and episode history (``score_episode`` adds counters, spend
  limits and predicates).

Adapters are pure: no database handles, no clock mutation, no private runner input. The
executor applies the transitions an adapter's results justify. Wave 2's pantry adapter adds
consumable semantics behind this same interface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from plan_b.domain.adapters.outcome import DomainOutcome
from plan_b.domain.models import (
    ActivityView,
    ActorContext,
    CandidateResult,
    CheckInView,
    CommitmentView,
    EpisodeHistory,
    EvaluationRequest,
    EvaluationResult,
    EventStateView,
    PlanningSnapshot,
    PlanView,
    PublicScenario,
    ReadinessReport,
    ResourceView,
)

ReadinessMode = Literal["preview", "execution"]


class ReadinessBasis(Protocol):
    """What readiness reads. A ``PlanningSnapshot`` is one; the projection passes the parts it
    has assembled before the snapshot exists (activity views without readiness)."""

    @property
    def activities(self) -> tuple[ActivityView, ...]: ...

    @property
    def plan(self) -> PlanView: ...

    @property
    def resources(self) -> tuple[ResourceView, ...]: ...

    @property
    def checkins(self) -> tuple[CheckInView, ...]: ...

    @property
    def commitments(self) -> tuple[CommitmentView, ...]: ...


class DomainAdapter(Protocol):
    adapter_id: str
    profile_ids: tuple[str, ...]

    def validate_config(self, scenario: PublicScenario) -> list[str]:
        """Return human-readable configuration problems; empty when valid."""
        ...

    def evaluate(
        self,
        snapshot: PlanningSnapshot,
        actor: ActorContext,
        request: EvaluationRequest,
        evaluation_id: str,
    ) -> EvaluationResult:
        """Pure evaluation of the declared candidate menu against one snapshot."""
        ...

    def revalidate(
        self, snapshot: PlanningSnapshot, actor: ActorContext, candidate: CandidateResult
    ) -> CandidateResult:
        """Re-check a stored candidate's assignments against a fresh snapshot.

        Returns a new CandidateResult with the same candidate_id/report_id/signature/edits and
        assignments, and freshly computed checks, assumptions, holds, authorization,
        objective and applicable_now (rank is None)."""
        ...

    def check_readiness(
        self,
        snapshot: ReadinessBasis,
        activity_id: str,
        at: datetime,
        *,
        mode: ReadinessMode = "execution",
    ) -> ReadinessReport: ...

    def score_outcome(self, final: EventStateView, history: EpisodeHistory) -> DomainOutcome:
        """Goal attainment and executed domain-rule violations from visible records only."""
        ...
