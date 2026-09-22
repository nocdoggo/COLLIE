"""Arm-facing adapter for the registered verifier lifecycle.

The arm proposes at the beginning of period ``tau_j`` while the statistical verifier indexes
``tau_j`` as the final conditioning period.  ``prime`` and ``condition`` are deliberately
separate from :class:`~collie.arms.protocols.ActivationPolicy.observe`: they transfer the
already-observed pre-proposal history without admitting it to the e-process product.  The arm
discovers these two optional hooks by duck typing, so the verifier package remains independent
of ``collie.arms`` and the public activation protocol stays small.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TypeAlias

from collie.contracts import (
    AnalysisClass,
    LifecycleState,
    ObservationMode,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.data.families.base import BaselineKind, BaselineSpec
from collie.verify.arrival import REGISTERED_NULL_LAW, ArrivalEProcess, RegisteredArrivalLaw
from collie.verify.demand import DemandEProcess
from collie.verify.lifecycle import CompoundVerifier, LifecycleEvent, LifecycleManager

__all__ = ["MIN_BASELINE_PARAMETER", "VerifierActivationPolicy"]


MIN_BASELINE_PARAMETER = 1e-6
"""Registered floor used when a finite prefix has zero sample mean or variance."""


StreamVerifier: TypeAlias = DemandEProcess | ArrivalEProcess | CompoundVerifier


@dataclass(slots=True)
class VerifierActivationPolicy:
    """Expose module 05's e-process/lifecycle stack through ``ActivationPolicy``.

    ``baseline`` is the arm-computed ``(mean, sample_sd)`` pair.  A degenerate finite prefix is
    mapped deterministically to a positive ``BaselineSpec`` parameter using
    :data:`MIN_BASELINE_PARAMETER`; this keeps the registered rounded-normal law well-defined
    without estimating anything from post-proposal evidence.

    The adapter supports both registered proposals in an episode.  ``state`` and ``is_active``
    describe the most recently registered proposal, which is the proposal the arm compiles.
    The complete lifecycle, including superseded predecessors and evidence-validity labels, is
    available through :attr:`output_records`.
    """

    episode_horizon: int
    alpha_episode: float = 0.05
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY
    bounded_provisional: bool = False
    null_arrival_law: RegisteredArrivalLaw = REGISTERED_NULL_LAW
    arrival_source: str = "collie_shockspec"
    observation_mode: ObservationMode = ObservationMode.UNCENSORED
    _manager: LifecycleManager = field(init=False, repr=False)
    _current_spec: ShockSpec | None = field(default=None, init=False, repr=False)
    _verifiers: dict[int, StreamVerifier] = field(default_factory=dict, init=False, repr=False)
    _demand_history: tuple[float, ...] = field(default=(), init=False, repr=False)
    _arrival_history: tuple[tuple[float, float], ...] = field(default=(), init=False, repr=False)
    _baseline: BaselineSpec | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._manager = self._new_manager()

    def _new_manager(self) -> LifecycleManager:
        return LifecycleManager(
            episode_horizon=self.episode_horizon,
            alpha_episode=self.alpha_episode,
            analysis_class=self.analysis_class,
            bounded_provisional=self.bounded_provisional,
        )

    def reset(self) -> None:
        self._manager = self._new_manager()
        self._current_spec = None
        self._verifiers.clear()
        self._demand_history = ()
        self._arrival_history = ()
        self._baseline = None

    def prime(
        self,
        demand_history: tuple[float, ...],
        arrival_history: tuple[tuple[float, float], ...],
    ) -> None:
        """Stage observations strictly before the proposal period for conditioning only."""
        if (
            self._current_spec is not None
            and self._current_spec.proposal_index not in self._verifiers
        ):
            raise RuntimeError("finish conditioning the registered proposal before priming another")
        if len(demand_history) != len(arrival_history):
            raise ValueError("demand and arrival conditioning histories must have equal length")
        self._demand_history = tuple(float(value) for value in demand_history)
        self._arrival_history = tuple(
            (float(dispatch), float(receipt)) for dispatch, receipt in arrival_history
        )

    def register(self, spec: ShockSpec, *, baseline: tuple[float, float] | None = None) -> None:
        if baseline is None:
            raise ValueError("the registered demand law requires baseline=(mean, sd)")
        mean, sd = (float(value) for value in baseline)
        if not math.isfinite(mean) or not math.isfinite(sd) or mean < 0.0 or sd < 0.0:
            raise ValueError("baseline mean and sd must be finite and non-negative")
        expected_prefix = max(spec.tau_j - 1, 0)
        if len(self._demand_history) != expected_prefix:
            raise ValueError(
                "adapter needs every demand observation before the proposal period: "
                f"expected {expected_prefix}, got {len(self._demand_history)}"
            )
        if len(self._arrival_history) != expected_prefix:
            raise ValueError(
                "adapter needs every dispatch/receipt pair before the proposal period: "
                f"expected {expected_prefix}, got {len(self._arrival_history)}"
            )
        self._manager.propose(spec)
        self._current_spec = spec
        self._baseline = BaselineSpec(
            BaselineKind.STATIONARY_IID,
            mean=max(mean, MIN_BASELINE_PARAMETER),
            sd=max(sd, MIN_BASELINE_PARAMETER),
        )
        if spec.tau_j == 0:
            self._verifiers[spec.proposal_index] = self._build_verifier(spec)

    def condition(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        """Condition through ``tau_j`` without multiplying the future-only e-process."""
        spec = self._require_spec()
        if period != spec.tau_j:
            raise ValueError(f"conditioning period must equal tau_j={spec.tau_j}, got {period}")
        if spec.proposal_index in self._verifiers:
            raise RuntimeError("the current proposal is already conditioned")
        if dispatch is None or receipt is None:
            raise ValueError("conditioning requires both dispatch and receipt channels")
        self._demand_history = (*self._demand_history, float(demand))
        self._arrival_history = (*self._arrival_history, (float(dispatch), float(receipt)))
        self._verifiers[spec.proposal_index] = self._build_verifier(spec)
        return self.state

    def _build_verifier(self, spec: ShockSpec) -> StreamVerifier:
        assert self._baseline is not None
        if len(self._demand_history) != spec.tau_j or len(self._arrival_history) != spec.tau_j:
            raise ValueError("conditioning history must end exactly at tau_j")
        if spec.shock_family is ShockFamily.COMPOUND:
            return CompoundVerifier.from_spec(
                spec,
                baseline=self._baseline,
                alpha_episode=self.alpha_episode,
                demand_history_before_proposal=self._demand_history,
                arrival_history_before_proposal=self._arrival_history,
                null_arrival_law=self.null_arrival_law,
                arrival_source=self.arrival_source,
                analysis_class=self.analysis_class,
            )
        if spec.target_stream is TargetStream.ARRIVAL:
            return ArrivalEProcess.from_spec(
                spec,
                alpha_episode=self.alpha_episode,
                preproposal_history=self._arrival_history,
                null_law=self.null_arrival_law,
                source=self.arrival_source,
                observation_mode=self.observation_mode,
                analysis_class=self.analysis_class,
            )
        return DemandEProcess.from_spec(
            spec,
            baseline=self._baseline,
            alpha_episode=self.alpha_episode,
            history_before_proposal=self._demand_history,
            analysis_class=self.analysis_class,
        )

    def observe(
        self,
        period: int,
        demand: float,
        *,
        dispatch: float | None = None,
        receipt: float | None = None,
    ) -> LifecycleState:
        spec = self._require_spec()
        proposal = self._manager.proposals[spec.proposal_index]
        if period <= spec.tau_j:
            raise ValueError("verifier evidence must be strictly after tau_j")
        if proposal.state in {
            LifecycleState.REFUTED,
            LifecycleState.EXPIRED,
            LifecycleState.SUPERSEDED,
        }:
            return proposal.state
        try:
            verifier = self._verifiers[spec.proposal_index]
        except KeyError:
            raise RuntimeError(
                "condition(period=tau_j, ...) before post-proposal evidence"
            ) from None
        if isinstance(verifier, DemandEProcess):
            point = verifier.observe(period, demand)
        elif isinstance(verifier, ArrivalEProcess):
            if dispatch is None or receipt is None:
                raise ValueError("arrival verification requires dispatch and receipt channels")
            point = verifier.observe(period, dispatch, receipt)
        else:
            if dispatch is None or receipt is None:
                raise ValueError("compound verification requires dispatch and receipt channels")
            point = verifier.observe(
                period,
                demand_value=demand,
                dispatch_quantity=dispatch,
                receipt=receipt,
            )
        self._manager.consume(spec.proposal_index, point)
        return proposal.state

    def _require_spec(self) -> ShockSpec:
        if self._current_spec is None:
            raise RuntimeError("register a proposal before conditioning or observing")
        return self._current_spec

    @property
    def is_active(self) -> bool:
        return self.state is LifecycleState.ACTIVE

    @property
    def state(self) -> LifecycleState:
        if self._current_spec is None:
            return LifecycleState.PROPOSED
        return self._manager.proposals[self._current_spec.proposal_index].state

    @property
    def output_records(self) -> tuple[LifecycleEvent, ...]:
        """Lifecycle output, including the validity label attached to consumed evidence."""
        return self._manager.output_records

    @property
    def baseline_spec(self) -> BaselineSpec | None:
        """The registered null parameters derived from the arm's frozen prefix."""
        return self._baseline
