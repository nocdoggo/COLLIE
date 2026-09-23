"""The episode runner. One loop, every arm, no arm-specific branches.

The runner executes the audited event order (``docs/env_contract.md`` §3) and nothing else. It
does not know which arm it is running: an arm is just a
:class:`~collie.contracts.Controller`. That is what makes the comparison across the arm ladder a
comparison of *policies* rather than of harnesses.

Two invariants the runner is responsible for.

**Hidden-state isolation.** ``HiddenIncident``, ``HiddenAlertSpec``, and ``SupplyRealization``
are held by the runner and the supply process, never by an observation. Every observation is
walked by :func:`~collie.contracts.assert_no_hidden_state` before it is handed over, so a leak
through an undeclared attribute or a nested container fails loudly at the period it happens.

**Action ``A_t`` cannot influence observation ``Y_t``.** The observation is fully built and
frozen before ``controller.order`` is called, so the causal ordering holds by construction; the
post-call check here is only a guard against a controller that reaches back through a mutable
field. The claim that ``A_t`` influences ``Y_{t+1}`` *and no earlier* is proved by the
differential test in ``tests/test_episode_runner.py``, which replays an episode with two
controllers that diverge at period ``k`` and requires observations ``1..k`` to be identical.
Note that with ``L = 0`` the order at ``t`` does land at ``t`` and so moves ``Y_{t+1}``; that is
the benchmark's own timing, not a leak.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from collie.contracts import (
    AlertMessage,
    AnalysisClass,
    Controller,
    Decision,
    EpisodeResult,
    HiddenIncident,
    PeriodObservation,
    RunRecord,
    assert_no_hidden_state,
)
from collie.sim.accounting import aggregate_episode, clamp_order, settle_period
from collie.sim.loader import LoadedInstance
from collie.sim.observation import PriorPeriod, build_observation
from collie.sim.supply import LeadTimeSupply

__all__ = ["EpisodeOutcome", "EpisodeRunner"]


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    """Everything one episode produced. ``result`` is the only part that is reported."""

    result: EpisodeResult
    observations: tuple[PeriodObservation, ...]
    decisions: tuple[Decision, ...]
    lost_units: float
    """Units dispatched into a shipment that never arrived. Diagnostic; evaluation side only."""
    undelivered_units: float
    """Lost units plus anything still in transit when the horizon ended."""

    def order_rows(self) -> tuple[tuple[int, int], ...]:
        """``(period, order_quantity)`` pairs in the exact shape ``results.csv`` expects.

        Quantities are integers because :func:`~collie.sim.accounting.clamp_order` applies the
        benchmark's ``max(0, int(q))`` before anything else sees them.
        """
        return tuple((r.period, int(r.order_quantity)) for r in self.result.records)


@dataclass(slots=True)
class EpisodeRunner:
    """Runs one loaded instance under one controller.

    ``instance`` carries the hidden incident; the runner keeps it and passes it to nothing but
    the evaluation side. ``alerts`` and ``template_ids`` are supplied by branch C; the runner
    only routes them, and deliberately routes the template id to the record and never to the
    observation.
    """

    instance: LoadedInstance
    alerts: Mapping[int, AlertMessage] | None = None
    template_ids: Mapping[int, str] | None = None
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY
    lost_orders_visible_in_transit: bool = False
    """``False`` = authoritative ``eval/`` semantics. ``True`` reproduces ``env.py`` for the
    legacy arms, and any comparison across the two must say which was used."""
    strict_isolation: bool = True
    """Walk every observation's object graph for hidden state. Cheap at benchmark scale; the
    only reason to disable it is a large sweep where the walk dominates."""
    check_controller_isolation: bool = False
    """Also walk the controller itself. Turned on by the harness for every arm except the
    oracle, which is *defined* by its access to hidden truth."""

    _supply: LeadTimeSupply = field(init=False, repr=False)

    def __post_init__(self) -> None:
        inst = self.instance
        horizon = inst.spec.horizon
        for name, seq in (
            ("demand", inst.demand),
            ("profits", inst.profits),
            ("holding_costs", inst.holding_costs),
            ("dates", inst.dates),
            ("supply.lead_times", inst.supply.lead_times),
        ):
            if len(seq) != horizon:
                raise ValueError(
                    f"{inst.spec.episode_id}: {name} has {len(seq)} entries but the horizon is "
                    f"{horizon}"
                )
        self._supply = LeadTimeSupply(
            realization=inst.supply,
            lost_orders_visible=self.lost_orders_visible_in_transit,
        )

    @property
    def incident(self) -> HiddenIncident | None:
        """Hidden truth. Read by the evaluator and the oracle arm; by nothing else."""
        return self.instance.incident

    def run(self, controller: Controller) -> EpisodeOutcome:
        """Execute the episode. The controller is reset first so a reused arm cannot carry state."""
        controller.reset()
        if self.check_controller_isolation:
            assert_no_hidden_state(controller, context=f"controller {controller.arm_id!r}")

        inst = self.instance
        spec = inst.spec
        supply = self._supply

        on_hand = 0.0
        prior: PriorPeriod | None = None
        records: list[RunRecord] = []
        observations: list[PeriodObservation] = []
        decisions: list[Decision] = []

        for index in range(spec.horizon):
            period = index + 1
            profit_per_unit = inst.profits[index]
            holding_cost_per_unit = inst.holding_costs[index]

            # --- 1. decision phase -------------------------------------------------
            # in_transit is read BEFORE this period's order is scheduled, so it includes units
            # landing this period but not the order about to be placed.
            on_hand_start = on_hand
            in_transit_start = supply.in_transit_total(period)

            obs = build_observation(
                spec,
                period=period,
                date=inst.dates[index],
                on_hand=on_hand_start,
                in_transit_total=in_transit_start,
                profit_per_unit=profit_per_unit,
                holding_cost_per_unit=holding_cost_per_unit,
                prior=prior,
                alert=self.alerts.get(period) if self.alerts else None,
            )
            if self.strict_isolation:
                assert_no_hidden_state(obs, context=f"observation at period {period}")

            decision = controller.order(obs)
            if decision.period != period:
                raise ValueError(
                    f"{controller.arm_id!r} returned a decision stamped period "
                    f"{decision.period} while the runner was at period {period}"
                )
            # Guards a controller that mutated the observation through a mutable field rather
            # than reading it. The causal ordering itself holds by construction: obs was built
            # before this call.
            if observations and observations[-1] is obs:  # pragma: no cover - defensive
                raise AssertionError("observation identity reused across periods")

            order_quantity = clamp_order(decision.order_quantity, spec.order_cap)

            supply.dispatch(period, order_quantity)

            # --- 2. arrival resolution ---------------------------------------------
            arrivals = supply.receive(period)
            on_hand += arrivals

            # --- 3 + 4. demand resolution and reward -------------------------------
            demand = inst.demand[index]
            acct = settle_period(
                on_hand_after_arrivals=on_hand,
                demand=demand,
                profit_per_unit=profit_per_unit,
                holding_cost_per_unit=holding_cost_per_unit,
            )
            on_hand = acct.on_hand_end

            records.append(
                RunRecord(
                    episode_id=spec.episode_id,
                    arm_id=controller.arm_id,
                    period=period,
                    date=inst.dates[index],
                    on_hand_start=on_hand_start,
                    in_transit_start=in_transit_start,
                    order_quantity=order_quantity,
                    arrivals=arrivals,
                    demand=demand,
                    units_sold=acct.units_sold,
                    lost_sales=acct.lost_sales,
                    on_hand_end=acct.on_hand_end,
                    period_profit=acct.period_profit,
                    period_holding=acct.period_holding,
                    triggered=decision.triggered,
                    llm_called=decision.llm_called,
                    lifecycle_state=decision.lifecycle_state,
                    active_spec_id=decision.active_spec_id,
                    active_spec=decision.active_spec,
                    control_config=decision.control_config,
                    template_id=self.template_ids.get(period) if self.template_ids else None,
                )
            )
            observations.append(obs)
            decisions.append(decision)
            prior = PriorPeriod(
                demand=demand,
                units_sold=acct.units_sold,
                on_hand_end=acct.on_hand_end,
                order_quantity=order_quantity,
                arrivals=arrivals,
            )

        result = aggregate_episode(
            spec,
            arm_id=controller.arm_id,
            records=records,
            perfect_foresight_profit_per_unit=inst.profits[0],
            analysis_class=self.analysis_class,
            calls=(),
        )
        return EpisodeOutcome(
            result=result,
            observations=tuple(observations),
            decisions=tuple(decisions),
            lost_units=supply.lost_total,
            undelivered_units=supply.undelivered_total,
        )
