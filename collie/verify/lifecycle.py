"""Registered hypothesis lifecycle and compound alpha accounting.

Activation is accepted only from an :class:`EProcessPoint`.  Retirement rules are deliberately
separate and every emitted record labels them empirical and outside the activation theorem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from collie.contracts import (
    AnalysisClass,
    DurationBin,
    LifecycleState,
    Persistence,
    ShockFamily,
    ShockSpec,
)
from collie.data.families.base import BaselineSpec
from collie.verify.alpha import DEFAULT_MAX_PROPOSALS, alpha_for_proposal
from collie.verify.arrival import ArrivalEProcess, RegisteredArrivalLaw
from collie.verify.demand import DemandEProcess
from collie.verify.eprocess import EMPIRICAL_ONLY, EProcessPoint
from collie.verify.registry import resolve_spec

__all__ = [
    "ACTIVATION_CLAIM",
    "RETIREMENT_CLAIM",
    "CompoundAlphaAllocation",
    "CompoundEvidencePoint",
    "CompoundVerifier",
    "LifecycleEvent",
    "LifecycleManager",
    "ProposalLifecycle",
    "RegisteredRetirementRules",
    "compound_alpha_allocation",
    "compound_evidence_point",
    "maximum_lifetime",
]


ACTIVATION_CLAIM = "model_conditional_anytime_valid_per_episode_false_activation"
RETIREMENT_CLAIM = "empirical_outside_activation_theorem"


_DURATION_UPPER = {
    DurationBin.SHORT: 3,
    DurationBin.MEDIUM: 8,
}


def maximum_lifetime(
    duration_bin: DurationBin,
    persistence: Persistence,
    *,
    remaining_horizon: int,
) -> int:
    """Resolve the registered duration/persistence pair into a finite operational lifetime."""
    if remaining_horizon < 1:
        raise ValueError("remaining_horizon must be positive")
    if duration_bin is DurationBin.NONE or persistence is Persistence.NONE:
        raise ValueError("an actionable proposal needs non-none duration and persistence")
    if duration_bin is DurationBin.LONGER or persistence is Persistence.PERSISTENT:
        return remaining_horizon
    base = _DURATION_UPPER[duration_bin]
    if persistence in {Persistence.TRANSIENT, Persistence.UNKNOWN}:
        return base
    raise ValueError(f"unsupported persistence {persistence}")


@dataclass(frozen=True, slots=True)
class RegisteredRetirementRules:
    """Operational retirement thresholds, intentionally outside the activation theorem."""

    refutation_e_value: float = 0.5
    refutation_streak: int = 2

    def __post_init__(self) -> None:
        if not 0.0 < self.refutation_e_value < 1.0:
            raise ValueError("refutation_e_value must lie in (0, 1)")
        if self.refutation_streak < 1:
            raise ValueError("refutation_streak must be positive")


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    period: int
    proposal_index: int
    previous_state: LifecycleState | None
    state: LifecycleState
    reason: str
    proposal_alpha: float
    activation_claim: str
    retirement_claim: str
    expiry_period: int
    refutation_e_value: float
    refutation_streak: int
    evidence_validity_label: str | None
    activation_delay: int | None
    analysis_class: AnalysisClass
    exploratory_provisional: bool


@dataclass(slots=True)
class ProposalLifecycle:
    spec: ShockSpec
    alpha_j: float
    rules: RegisteredRetirementRules
    analysis_class: AnalysisClass
    exploratory_provisional: bool
    episode_horizon: int
    state: LifecycleState = LifecycleState.PROPOSED
    activation_period: int | None = None
    evidence_points: int = 0
    low_evidence_streak: int = 0
    last_evidence_period: int | None = None
    evidence_validity_label: str | None = None
    history: list[LifecycleEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.history.append(self._event(self.spec.tau_j, None, self.state, "proposal_frozen"))

    @property
    def expiry_period(self) -> int:
        remaining = self.episode_horizon - self.spec.tau_j
        lifetime = maximum_lifetime(
            self.spec.duration_bin,
            self.spec.persistence,
            remaining_horizon=remaining,
        )
        return min(self.spec.tau_j + lifetime, self.episode_horizon)

    @property
    def may_influence_orders(self) -> bool:
        return self.state is LifecycleState.ACTIVE

    @property
    def control_mode(self) -> str:
        return "verified_adaptation" if self.may_influence_orders else "baseline_or"

    @property
    def activation_delay(self) -> int | None:
        """Primary operational metric from proposal time to verified activation."""
        if self.activation_period is None:
            return None
        return self.activation_period - self.spec.tau_j

    def _event(
        self,
        period: int,
        previous: LifecycleState | None,
        state: LifecycleState,
        reason: str,
    ) -> LifecycleEvent:
        return LifecycleEvent(
            period=period,
            proposal_index=self.spec.proposal_index,
            previous_state=previous,
            state=state,
            reason=reason,
            proposal_alpha=self.alpha_j,
            activation_claim=ACTIVATION_CLAIM,
            retirement_claim=RETIREMENT_CLAIM,
            expiry_period=self.expiry_period,
            refutation_e_value=self.rules.refutation_e_value,
            refutation_streak=self.rules.refutation_streak,
            evidence_validity_label=self.evidence_validity_label,
            activation_delay=self.activation_delay,
            analysis_class=self.analysis_class,
            exploratory_provisional=self.exploratory_provisional,
        )

    def _transition(self, period: int, state: LifecycleState, reason: str) -> LifecycleEvent:
        legal = {
            LifecycleState.PROPOSED: {
                LifecycleState.ACTIVE,
                LifecycleState.EXPIRED,
                LifecycleState.SUPERSEDED,
            },
            LifecycleState.ACTIVE: {
                LifecycleState.REFUTED,
                LifecycleState.EXPIRED,
                LifecycleState.SUPERSEDED,
            },
        }
        if state not in legal.get(self.state, set()):
            raise ValueError(f"illegal lifecycle transition {self.state.value} -> {state.value}")
        previous = self.state
        self.state = state
        event = self._event(period, previous, state, reason)
        self.history.append(event)
        return event

    def consume(self, point: EProcessPoint | CompoundEvidencePoint) -> LifecycleEvent | None:
        """Consume registered evidence; no caller-supplied boolean can activate a proposal."""
        if self.spec.shock_family is ShockFamily.COMPOUND:
            if not isinstance(point, CompoundEvidencePoint):
                raise TypeError("compound activation requires two separately tested streams")
            expected = compound_evidence_point(
                point.demand,
                point.arrival,
                allocation=CompoundAlphaAllocation(
                    proposal_alpha=self.alpha_j,
                    demand_alpha=self.alpha_j / 2.0,
                    arrival_alpha=self.alpha_j / 2.0,
                    construction="separate_eprocesses_alpha_split",
                ),
            )
            if point != expected:
                raise ValueError("compound evidence fields must be derived from both stream points")
            effective_e_value = min(point.demand.e_value, point.arrival.e_value)
        else:
            if not isinstance(point, EProcessPoint):
                raise TypeError("activation evidence must be an EProcessPoint")
            effective_e_value = point.e_value
        if point.period <= self.spec.tau_j:
            raise ValueError("lifecycle evidence must be strictly after tau_j")
        if self.last_evidence_period is not None and point.period <= self.last_evidence_period:
            raise ValueError("lifecycle evidence periods must increase strictly")
        if isinstance(point, EProcessPoint):
            expected_threshold = 1.0 / self.alpha_j
            if not math.isclose(point.threshold, expected_threshold, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(
                    "evidence threshold does not match this proposal's alpha allocation"
                )
        if point.analysis_class is not self.analysis_class:
            raise ValueError("evidence and lifecycle analysis classes must match")
        if (
            self.analysis_class is AnalysisClass.CONFIRMATORY
            and point.validity_label == EMPIRICAL_ONLY
        ):
            raise ValueError("empirical_only evidence cannot activate a confirmatory lifecycle")
        if point.activated and point.activation_period is None:
            raise ValueError("an activated evidence point must retain its crossing period")
        if not point.activated and point.activation_period is not None:
            raise ValueError("non-activated evidence cannot have a crossing period")
        if point.activation_period is not None and not (
            self.spec.tau_j < point.activation_period <= point.period
        ):
            raise ValueError("activation period must be post-proposal and no later than evidence")
        if (
            isinstance(point, EProcessPoint)
            and self.state is LifecycleState.PROPOSED
            and point.activated
            and point.e_value < point.threshold
        ):
            raise ValueError("initial activation requires an observed threshold crossing")
        if self.state in {
            LifecycleState.REFUTED,
            LifecycleState.EXPIRED,
            LifecycleState.SUPERSEDED,
        }:
            return None
        self.evidence_points += 1
        self.last_evidence_period = point.period
        self.evidence_validity_label = point.validity_label
        if point.period >= self.expiry_period:
            return self._transition(point.period, LifecycleState.EXPIRED, "registered_expiry")
        if self.state is LifecycleState.PROPOSED:
            if point.activated:
                self.activation_period = point.activation_period
                return self._transition(
                    point.period, LifecycleState.ACTIVE, "e_process_threshold_crossing"
                )
            return None

        if effective_e_value <= self.rules.refutation_e_value:
            self.low_evidence_streak += 1
        else:
            self.low_evidence_streak = 0
        if self.low_evidence_streak >= self.rules.refutation_streak:
            return self._transition(
                point.period, LifecycleState.REFUTED, "registered_empirical_refutation"
            )
        return None

    def advance(self, period: int) -> LifecycleEvent | None:
        """Expire stale beliefs even if no further observable can update their e-process."""
        if (
            self.state
            in {
                LifecycleState.PROPOSED,
                LifecycleState.ACTIVE,
            }
            and period >= self.expiry_period
        ):
            return self._transition(period, LifecycleState.EXPIRED, "registered_expiry")
        return None

    def _supersede_after_successor_test(self, period: int) -> LifecycleEvent:
        return self._transition(period, LifecycleState.SUPERSEDED, "tested_successor")


@dataclass(frozen=True, slots=True)
class CompoundAlphaAllocation:
    proposal_alpha: float
    demand_alpha: float
    arrival_alpha: float
    construction: str


def compound_alpha_allocation(
    *, alpha_episode: float, proposal_index: int, family: ShockFamily
) -> CompoundAlphaAllocation:
    """Return the only permitted compound path: two tests with a prior alpha split."""
    if family is not ShockFamily.COMPOUND:
        raise ValueError("stream alpha splitting is registered only for compound specs")
    proposal_alpha = alpha_for_proposal(alpha_episode, proposal_index).alpha_j
    stream_alpha = proposal_alpha / 2.0
    return CompoundAlphaAllocation(
        proposal_alpha=proposal_alpha,
        demand_alpha=stream_alpha,
        arrival_alpha=stream_alpha,
        construction="separate_eprocesses_alpha_split",
    )


@dataclass(frozen=True, slots=True)
class CompoundEvidencePoint:
    """Two separately thresholded stream points, with no combined e-value field."""

    period: int
    demand: EProcessPoint
    arrival: EProcessPoint
    activated: bool
    activation_period: int | None
    analysis_class: AnalysisClass
    validity_label: str


@dataclass(frozen=True, slots=True)
class CompoundVerifier:
    """The real compound path: two separately constructed and thresholded e-processes."""

    spec: ShockSpec
    allocation: CompoundAlphaAllocation
    demand: DemandEProcess
    arrival: ArrivalEProcess

    @classmethod
    def from_spec(
        cls,
        spec: ShockSpec,
        *,
        baseline: BaselineSpec,
        alpha_episode: float,
        demand_history_before_proposal: tuple[float, ...],
        arrival_history_before_proposal: tuple[tuple[float, float], ...],
        null_arrival_law: RegisteredArrivalLaw,
        arrival_source: str = "collie_shockspec",
        analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY,
    ) -> CompoundVerifier:
        if spec.shock_family is not ShockFamily.COMPOUND:
            raise ValueError("compound verifier requires a compound ShockSpec")
        allocation = compound_alpha_allocation(
            alpha_episode=alpha_episode,
            proposal_index=spec.proposal_index,
            family=spec.shock_family,
        )
        demand = DemandEProcess.from_spec(
            spec,
            baseline=baseline,
            alpha_episode=alpha_episode,
            history_before_proposal=demand_history_before_proposal,
            analysis_class=analysis_class,
        )
        arrival = ArrivalEProcess.from_spec(
            spec,
            alpha_episode=alpha_episode,
            preproposal_history=arrival_history_before_proposal,
            null_law=null_arrival_law,
            source=arrival_source,
            analysis_class=analysis_class,
        )
        if not math.isclose(demand.alpha_j, allocation.demand_alpha, abs_tol=1e-12):
            raise AssertionError("compound demand verifier did not receive its alpha split")
        if not math.isclose(arrival.alpha_j, allocation.arrival_alpha, abs_tol=1e-12):
            raise AssertionError("compound arrival verifier did not receive its alpha split")
        return cls(spec, allocation, demand, arrival)

    def observe(
        self,
        period: int,
        *,
        demand_value: float,
        dispatch_quantity: float,
        receipt: float,
    ) -> CompoundEvidencePoint:
        demand_point = self.demand.observe(period, demand_value)
        arrival_point = self.arrival.observe(period, dispatch_quantity, receipt)
        return compound_evidence_point(
            demand_point,
            arrival_point,
            allocation=self.allocation,
        )

    @property
    def activated(self) -> bool:
        return self.demand.activated and self.arrival.activated

    @property
    def activation_period(self) -> int | None:
        if not self.activated:
            return None
        assert self.demand.activation_period is not None
        assert self.arrival.activation_period is not None
        return max(self.demand.activation_period, self.arrival.activation_period)


def compound_evidence_point(
    demand: EProcessPoint,
    arrival: EProcessPoint,
    *,
    allocation: CompoundAlphaAllocation,
) -> CompoundEvidencePoint:
    """Gate a compound claim without constructing a product of marginal evidence."""
    if demand.period != arrival.period:
        raise ValueError("compound stream evidence must refer to the same period")
    if demand.analysis_class is not arrival.analysis_class:
        raise ValueError("compound stream analysis classes must match")
    expected_demand = 1.0 / allocation.demand_alpha
    expected_arrival = 1.0 / allocation.arrival_alpha
    if not math.isclose(demand.threshold, expected_demand, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("demand threshold does not match its compound alpha split")
    if not math.isclose(arrival.threshold, expected_arrival, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("arrival threshold does not match its compound alpha split")
    if (
        demand.activated
        and demand.activation_period == demand.period
        and demand.e_value < demand.threshold
    ):
        raise ValueError("demand activation requires its observed threshold crossing")
    if (
        arrival.activated
        and arrival.activation_period == arrival.period
        and arrival.e_value < arrival.threshold
    ):
        raise ValueError("arrival activation requires its observed threshold crossing")
    activated = demand.activated and arrival.activated
    activation_period = None
    if activated:
        if demand.activation_period is None or arrival.activation_period is None:
            raise ValueError("activated compound streams must retain both crossing periods")
        activation_period = max(demand.activation_period, arrival.activation_period)
    validity_label = (
        "anytime_valid_via_splitting"
        if demand.validity_label.startswith("anytime_valid")
        and arrival.validity_label.startswith("anytime_valid")
        else EMPIRICAL_ONLY
    )
    return CompoundEvidencePoint(
        period=demand.period,
        demand=demand,
        arrival=arrival,
        activated=activated,
        activation_period=activation_period,
        analysis_class=demand.analysis_class,
        validity_label=validity_label,
    )


@dataclass(slots=True)
class LifecycleManager:
    """Episode-local proposal cap, supersession, expiry, and output metadata."""

    episode_horizon: int
    alpha_episode: float = 0.05
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY
    bounded_provisional: bool = False
    rules: RegisteredRetirementRules = field(default_factory=RegisteredRetirementRules)
    max_proposals: int = DEFAULT_MAX_PROPOSALS
    proposals: dict[int, ProposalLifecycle] = field(default_factory=dict, init=False)
    _pending_successor: int | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.episode_horizon < 1:
            raise ValueError("episode_horizon must be positive")
        if self.bounded_provisional and self.analysis_class is AnalysisClass.CONFIRMATORY:
            raise ValueError("confirmatory runner refuses the exploratory provisional flag")
        if self.max_proposals != DEFAULT_MAX_PROPOSALS:
            raise ValueError("the registered lifecycle permits exactly two proposals")

    def propose(self, spec: ShockSpec) -> ProposalLifecycle:
        if spec.is_abstention:
            raise ValueError("no_change is an abstention, not a lifecycle proposal")
        resolve_spec(spec)
        if not 0 <= spec.tau_j < self.episode_horizon:
            raise ValueError("proposal tau_j must precede the episode horizon")
        expected_index = len(self.proposals) + 1
        if spec.proposal_index != expected_index:
            raise ValueError(
                f"expected one-based proposal_index {expected_index}, got {spec.proposal_index}"
            )
        if expected_index > self.max_proposals:
            raise ValueError("third proposal rejected: episode proposal cap is two")
        allocation = alpha_for_proposal(
            self.alpha_episode, spec.proposal_index, max_proposals=self.max_proposals
        )
        proposal = ProposalLifecycle(
            spec=spec,
            alpha_j=allocation.alpha_j,
            rules=self.rules,
            analysis_class=self.analysis_class,
            exploratory_provisional=self.bounded_provisional,
            episode_horizon=self.episode_horizon,
        )
        self.proposals[spec.proposal_index] = proposal
        if spec.proposal_index > 1:
            self._pending_successor = spec.proposal_index
        return proposal

    def consume(
        self, proposal_index: int, point: EProcessPoint | CompoundEvidencePoint
    ) -> LifecycleEvent | None:
        proposal = self.proposals[proposal_index]
        result = proposal.consume(point)
        if self._pending_successor == proposal_index and proposal.evidence_points >= 1:
            predecessor = self.proposals[proposal_index - 1]
            if predecessor.state in {LifecycleState.PROPOSED, LifecycleState.ACTIVE}:
                predecessor._supersede_after_successor_test(point.period)
            self._pending_successor = None
        return result

    def advance(self, period: int) -> tuple[LifecycleEvent, ...]:
        events = []
        for proposal in self.proposals.values():
            event = proposal.advance(period)
            if event is not None:
                events.append(event)
        return tuple(events)

    @property
    def active(self) -> ProposalLifecycle | None:
        active = [proposal for proposal in self.proposals.values() if proposal.may_influence_orders]
        if len(active) > 1:
            raise AssertionError("at most one proposal may influence orders")
        return active[0] if active else None

    @property
    def output_records(self) -> tuple[LifecycleEvent, ...]:
        records = [event for proposal in self.proposals.values() for event in proposal.history]
        return tuple(sorted(records, key=lambda item: (item.period, item.proposal_index)))


def compound_demo_timeline(spec: ShockSpec, *, episode_horizon: int) -> tuple[LifecycleEvent, ...]:
    """Run a real paired verifier and return its deterministic compound lifecycle timeline."""
    if spec.shock_family is not ShockFamily.COMPOUND:
        raise ValueError("compound timeline needs a compound spec")
    import random

    import numpy as np

    from collie.data.families.base import as_demand_cells, draw_baseline
    from collie.data.families.supply import (
        COMPOUND_DURATION,
        COMPOUND_MAGNITUDES,
        COMPOUND_PAUSE,
    )
    from collie.verify.arrival import (
        REGISTERED_NULL_LAW,
        REGISTERED_PAUSE_ALTERNATIVES,
        ArrivalModel,
        sample_arrival_model_path,
    )

    manager = LifecycleManager(episode_horizon=episode_horizon, alpha_episode=0.05)
    proposal = manager.propose(spec)
    dispatches = (10.0,) * manager.episode_horizon
    arrival_model = ArrivalModel(
        baseline=REGISTERED_NULL_LAW,
        changed=REGISTERED_PAUSE_ALTERNATIVES[-1],
        active_from=spec.tau_j + 1,
        active_duration=COMPOUND_PAUSE[1],
    )
    receipts = sample_arrival_model_path(arrival_model, dispatches, rng=random.Random(3))
    baseline = BaselineSpec()
    unshocked = draw_baseline(np.random.default_rng(7), baseline, manager.episode_horizon)
    shock_end = spec.tau_j + COMPOUND_DURATION[0]
    demand = (
        *unshocked[: spec.tau_j],
        *as_demand_cells(np.asarray(unshocked[spec.tau_j : shock_end]) * COMPOUND_MAGNITUDES[-1]),
        *unshocked[shock_end:],
    )
    verifier = CompoundVerifier.from_spec(
        spec,
        baseline=baseline,
        alpha_episode=manager.alpha_episode,
        demand_history_before_proposal=tuple(demand[: spec.tau_j]),
        arrival_history_before_proposal=tuple(
            zip(
                dispatches[: spec.tau_j],
                receipts[: spec.tau_j],
                strict=True,
            )
        ),
        null_arrival_law=REGISTERED_NULL_LAW,
    )
    for period in range(spec.tau_j + 1, proposal.expiry_period + 1):
        point = verifier.observe(
            period,
            demand_value=demand[period - 1],
            dispatch_quantity=dispatches[period - 1],
            receipt=receipts[period - 1],
        )
        manager.consume(spec.proposal_index, point)
        manager.advance(period)
    return manager.output_records
