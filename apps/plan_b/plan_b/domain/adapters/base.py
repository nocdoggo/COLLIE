"""The narrow domain-adapter interface.

The shared core (store, authority, clock, revisions, idempotency, receipts, tools, replay)
is domain-independent. A domain adapter owns only:

* ``validate_config``: profile-specific checks on a public scenario;
* ``evaluate``: enumerate the configured finite candidate menu, check constraints, rank;
* ``revalidate``: re-run every check on a stored candidate against a fresh snapshot
  (``apply_plan`` calls this inside its write transaction);
* ``check_readiness``: execution prerequisites for one activity at a scenario time;
* ``score_outcome``: domain goal attainment computed from a visible final state.

Adapters are pure: no database handles, no clock mutation, no private runner input. The
executor applies the transitions an adapter's results justify. Wave 2's pantry adapter adds
consumable semantics behind this same interface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from plan_b.domain.models import (
    ActorContext,
    CandidateResult,
    EvaluationRequest,
    EvaluationResult,
    EventStateView,
    PlanningSnapshot,
    PublicScenario,
    ReadinessReport,
)


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
        self, snapshot: PlanningSnapshot, activity_id: str, at: datetime
    ) -> ReadinessReport: ...

    def score_outcome(self, view: EventStateView) -> dict[str, Any]: ...
