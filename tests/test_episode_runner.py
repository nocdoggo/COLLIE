"""Task 4 — unit tests for the episode runner, supply physics, and accounting.

Fast and file-free: every instance here is built in memory. The heavyweight differential against
the official pipeline lives in ``tests/test_accounting_equivalence.py`` behind the ``equivalence``
marker.
"""

from __future__ import annotations

import math

import pytest

from collie.contracts import (
    AlertMessage,
    Decision,
    EpisodeSpec,
    HiddenIncident,
    HiddenStateLeak,
    ObservationMode,
    PeriodObservation,
    ShockFamily,
    SupplyRealization,
    find_hidden_state,
)
from collie.sim.accounting import clamp_order, settle_period
from collie.sim.loader import LoadedInstance
from collie.sim.runner import EpisodeRunner
from collie.sim.supply import ArrivalKeyedSupply, LeadTimeSupply

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def make_instance(
    demand: tuple[float, ...],
    lead_times: tuple[float, ...],
    *,
    pause: tuple[bool, ...] = (),
    profit: float = 4.0,
    holding: float = 1.0,
    mode: ObservationMode = ObservationMode.UNCENSORED,
    order_cap: float = math.inf,
    promised_lead_time: int = 0,
    incident: HiddenIncident | None = None,
    episode_id: str = "unit/ep",
) -> LoadedInstance:
    horizon = len(demand)
    assert len(lead_times) == horizon
    spec = EpisodeSpec(
        episode_id=episode_id,
        item_id="X1",
        horizon=horizon,
        promised_lead_time=promised_lead_time,
        profit_per_unit=profit,
        holding_cost_per_unit=holding,
        order_cap=order_cap,
        observation_mode=mode,
    )
    return LoadedInstance(
        spec=spec,
        demand=demand,
        supply=SupplyRealization(lead_times=lead_times, pause_active=pause),
        profits=(profit,) * horizon,
        holding_costs=(holding,) * horizon,
        dates=tuple(f"Period_{t}" for t in range(1, horizon + 1)),
        incident=incident,
    )


class ConstantController:
    """Orders a fixed quantity every period."""

    def __init__(self, quantity: float, arm_id: str = "const") -> None:
        self.quantity = quantity
        self.arm_id = arm_id

    def reset(self) -> None: ...

    def order(self, obs: PeriodObservation) -> Decision:
        return Decision(period=obs.period, order_quantity=self.quantity, arm_id=self.arm_id)


class SwitchController:
    """Orders ``before`` up to and including ``switch_at``, then ``after``.

    Used to prove that a change in action at period ``k`` cannot alter any observation at or
    before ``k``.
    """

    def __init__(self, switch_at: int, before: float, after: float) -> None:
        self.switch_at = switch_at
        self.before = before
        self.after = after
        self.arm_id = "switch"
        self.seen: list[PeriodObservation] = []

    def reset(self) -> None:
        self.seen = []

    def order(self, obs: PeriodObservation) -> Decision:
        self.seen.append(obs)
        qty = self.before if obs.period <= self.switch_at else self.after
        return Decision(period=obs.period, order_quantity=qty, arm_id=self.arm_id)


# ---------------------------------------------------------------------------
# supply: cohort model vs the reference's arrival-keyed dict
# ---------------------------------------------------------------------------

LEAD_TIME_CASES = [
    pytest.param((0,) * 8, id="L0_everywhere"),
    pytest.param((4,) * 8, id="L4_everywhere"),
    pytest.param((1, 2, 3, 1, 2, 3, 1, 2), id="stochastic_finite"),
    pytest.param((2, math.inf, 1, math.inf, 3, 0, math.inf, 2), id="with_losses"),
    pytest.param((math.inf,) * 8, id="all_lost"),
    pytest.param((0, 4, 0, 4, 0, 4, 0, 4), id="alternating"),
]


@pytest.mark.parametrize("lead_times", LEAD_TIME_CASES)
def test_cohort_supply_matches_arrival_keyed_reference(lead_times: tuple[float, ...]) -> None:
    """With no pause, our cohort model must be indistinguishable from the reference dict.

    This is the load-bearing claim: the remaining-time representation exists only so a transit
    pause is expressible, and it must not change anything when no pause is active.
    """
    orders = [3.0, 0.0, 11.0, 7.0, 0.0, 5.0, 13.0, 2.0]
    realization = SupplyRealization(lead_times=lead_times)
    ours = LeadTimeSupply(realization=realization)
    reference = ArrivalKeyedSupply(realization=realization)

    for index, qty in enumerate(orders):
        period = index + 1
        # in-transit is read at decision time, before this period's order is scheduled
        assert ours.in_transit_total(period) == reference.in_transit_total(period), (
            f"in-transit diverged at period {period}"
        )
        ours.dispatch(period, qty)
        reference.dispatch(period, qty)
        assert ours.receive(period) == reference.receive(period), f"arrivals diverged at {period}"


def test_lead_time_zero_lands_in_the_same_period() -> None:
    """Scheduling precedes the arrival pop, so an L=0 order serves this period's demand."""
    supply = LeadTimeSupply(realization=SupplyRealization(lead_times=(0.0, 0.0)))
    supply.dispatch(1, 25.0)
    assert supply.receive(1) == 25.0


def test_in_transit_includes_units_landing_this_period() -> None:
    """At decision time the scalar still counts units about to land, matching the reference."""
    supply = LeadTimeSupply(realization=SupplyRealization(lead_times=(1.0, 1.0, 1.0)))
    supply.dispatch(1, 10.0)
    supply.receive(1)
    # The period-1 order lands at period 2, and is visible while the period-2 decision is made.
    assert supply.in_transit_total(2) == 10.0
    assert supply.receive(2) == 10.0
    assert supply.in_transit_total(3) == 0.0


def test_lost_shipment_is_dropped_under_eval_semantics() -> None:
    supply = LeadTimeSupply(realization=SupplyRealization(lead_times=(math.inf, 0.0)))
    supply.dispatch(1, 40.0)
    assert supply.receive(1) == 0.0
    assert supply.in_transit_total(2) == 0.0
    assert supply.lost_total == 40.0
    assert supply.undelivered_total == 40.0


def test_lost_shipment_stays_visible_under_env_semantics() -> None:
    """``env.py`` keeps lost orders in in-transit forever (``docs/env_contract.md`` §6)."""
    supply = LeadTimeSupply(
        realization=SupplyRealization(lead_times=(math.inf, 0.0, 0.0)),
        lost_orders_visible=True,
    )
    supply.dispatch(1, 40.0)
    supply.receive(1)
    assert supply.in_transit_total(2) == 40.0
    assert supply.in_transit_total(3) == 40.0
    assert supply.receive(2) == 0.0


def test_negative_lead_time_is_refused() -> None:
    """The reference would strand such an order in transit forever; we refuse to load it."""
    with pytest.raises(ValueError, match="negative lead time"):
        LeadTimeSupply(realization=SupplyRealization(lead_times=(1.0, -2.0)))


# ---------------------------------------------------------------------------
# supply: transit pause
# ---------------------------------------------------------------------------


def test_pause_delays_a_moving_shipment_by_exactly_the_pause_length() -> None:
    pause_length = 3
    horizon = 10
    lead_times = (2.0,) * horizon
    # pause covers periods 2, 3, 4
    pause = tuple(2 <= t <= 1 + pause_length for t in range(1, horizon + 1))

    unpaused = LeadTimeSupply(realization=SupplyRealization(lead_times=lead_times))
    paused = LeadTimeSupply(
        realization=SupplyRealization(lead_times=lead_times, pause_active=pause)
    )

    def landing_period(supply: LeadTimeSupply) -> int:
        supply.dispatch(1, 100.0)
        for period in range(1, horizon + 1):
            if supply.receive(period) > 0:
                return period
        raise AssertionError("shipment never landed")

    assert landing_period(unpaused) == 3
    assert landing_period(paused) == 3 + pause_length


def test_pause_does_not_un_land_a_completed_shipment() -> None:
    """A shipment whose transit is already complete lands even during a pause.

    Keeps the invariant that units with zero remaining transit at decision time always arrive
    this period, which is exactly the reference semantics the OR compiler's pipeline crediting
    is built on.
    """
    supply = LeadTimeSupply(
        realization=SupplyRealization(lead_times=(1.0, 1.0, 1.0), pause_active=(False, True, True))
    )
    supply.dispatch(1, 60.0)
    assert supply.receive(1) == 0.0
    # remaining hit 0 at the end of period 1, so period 2's pause cannot hold it back
    assert supply.receive(2) == 60.0


def test_pause_of_zero_length_is_identical_to_no_pause() -> None:
    lead_times = (2.0,) * 6
    no_pause = LeadTimeSupply(realization=SupplyRealization(lead_times=lead_times))
    empty_pause = LeadTimeSupply(
        realization=SupplyRealization(lead_times=lead_times, pause_active=(False,) * 6)
    )
    for period in range(1, 7):
        no_pause.dispatch(period, 4.0)
        empty_pause.dispatch(period, 4.0)
        assert no_pause.receive(period) == empty_pause.receive(period)


# ---------------------------------------------------------------------------
# accounting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "cap", "expected"),
    [
        (12.0, math.inf, 12.0),
        (12.9, math.inf, 12.0),  # int() truncates toward zero
        (-12.9, math.inf, 0.0),  # then max(0, .)
        (-3, math.inf, 0.0),
        (0.4, math.inf, 0.0),
        (50.0, 20.0, 20.0),  # our cap, applied after the benchmark's clamp
        (50.9, 20.0, 20.0),
    ],
)
def test_clamp_order(raw: float, cap: float, expected: float) -> None:
    assert clamp_order(raw, cap) == expected


def test_clamp_order_refuses_non_numbers() -> None:
    with pytest.raises(ValueError, match="NaN"):
        clamp_order(math.nan, math.inf)
    with pytest.raises(ValueError, match="finite"):
        clamp_order(math.inf, math.inf)


def test_holding_is_charged_on_ending_inventory_only() -> None:
    """Units that arrive and sell in the same period are never held."""
    acct = settle_period(
        on_hand_after_arrivals=30.0, demand=30.0, profit_per_unit=4.0, holding_cost_per_unit=1.0
    )
    assert acct.units_sold == 30.0
    assert acct.on_hand_end == 0.0
    assert acct.period_holding == 0.0
    assert acct.period_profit == 120.0


def test_unmet_demand_is_lost_not_backordered() -> None:
    acct = settle_period(
        on_hand_after_arrivals=10.0, demand=25.0, profit_per_unit=4.0, holding_cost_per_unit=1.0
    )
    assert acct.units_sold == 10.0
    assert acct.lost_sales == 15.0
    assert acct.on_hand_end == 0.0


# ---------------------------------------------------------------------------
# runner: event order
# ---------------------------------------------------------------------------


def test_runner_reproduces_the_audited_event_order_with_l0() -> None:
    instance = make_instance(demand=(10.0, 10.0, 10.0), lead_times=(0.0, 0.0, 0.0))
    outcome = EpisodeRunner(instance=instance).run(ConstantController(10.0))

    for record in outcome.result.records:
        assert record.arrivals == 10.0, "L=0 must land in the same period"
        assert record.units_sold == 10.0
        assert record.on_hand_end == 0.0
        assert record.period_holding == 0.0
        assert record.period_profit == 40.0
    assert outcome.result.total_reward == 120.0
    assert outcome.result.normalized_reward == 1.0


def test_runner_charges_holding_on_leftovers() -> None:
    instance = make_instance(demand=(5.0, 5.0), lead_times=(0.0, 0.0))
    outcome = EpisodeRunner(instance=instance).run(ConstantController(10.0))
    records = outcome.result.records
    assert records[0].on_hand_end == 5.0
    assert records[0].period_holding == 5.0
    assert records[1].on_hand_start == 5.0
    assert records[1].on_hand_end == 10.0
    assert records[1].period_holding == 10.0


def test_runner_reports_previous_period_state_as_the_reference_does() -> None:
    instance = make_instance(demand=(8.0, 3.0, 12.0), lead_times=(0.0, 0.0, 0.0))
    controller = SwitchController(switch_at=99, before=6.0, after=6.0)
    EpisodeRunner(instance=instance).run(controller)
    first, second, third = controller.seen

    # Period 1 carries the reference's initialisation, not a measurement.
    assert first.prev_demand == 0.0
    assert first.prev_order == 0.0
    assert first.prev_arrivals == 0.0
    # Afterwards: true demand, the clamped order, and that period's arrivals.
    assert second.prev_demand == 8.0
    assert second.prev_order == 6.0
    assert second.prev_arrivals == 6.0
    assert third.prev_demand == 3.0


def test_order_cap_is_applied_by_the_runner() -> None:
    instance = make_instance(demand=(100.0,), lead_times=(0.0,), order_cap=20.0)
    outcome = EpisodeRunner(instance=instance).run(ConstantController(500.0))
    assert outcome.result.records[0].order_quantity == 20.0


def test_runner_rejects_a_mismatched_decision_period() -> None:
    class Liar:
        arm_id = "liar"

        def reset(self) -> None: ...

        def order(self, obs: PeriodObservation) -> Decision:
            return Decision(period=obs.period + 5, order_quantity=1.0, arm_id=self.arm_id)

    instance = make_instance(demand=(1.0,), lead_times=(0.0,))
    with pytest.raises(ValueError, match="stamped period"):
        EpisodeRunner(instance=instance).run(Liar())


def test_runner_rejects_a_ragged_instance() -> None:
    good = make_instance(demand=(1.0, 2.0), lead_times=(0.0, 0.0))
    ragged = LoadedInstance(
        spec=good.spec,
        demand=(1.0,),  # one short of the horizon
        supply=good.supply,
        profits=good.profits,
        holding_costs=good.holding_costs,
        dates=good.dates,
    )
    with pytest.raises(ValueError, match="demand has 1 entries"):
        EpisodeRunner(instance=ragged)


# ---------------------------------------------------------------------------
# runner: A_t cannot influence Y_t
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("switch_at", [1, 2, 3, 5])
@pytest.mark.parametrize(
    "lead_times",
    [(0.0,) * 8, (4.0,) * 8, (1.0, 2.0, math.inf, 3.0, 1.0, math.inf, 2.0, 1.0)],
)
def test_action_at_k_cannot_change_any_observation_up_to_k(
    switch_at: int, lead_times: tuple[float, ...]
) -> None:
    """Two controllers that agree through period ``k`` must see identical observations 1..k.

    This is the operational form of the ``A_t -> Y_{t+1}`` invariant. It is a differential test
    rather than an assertion because the property is about two counterfactual runs, which no
    single run can check.
    """
    demand = (9.0, 14.0, 3.0, 22.0, 7.0, 11.0, 0.0, 18.0)
    instance = make_instance(demand=demand, lead_times=lead_times, promised_lead_time=2)

    low = SwitchController(switch_at=switch_at, before=10.0, after=0.0)
    high = SwitchController(switch_at=switch_at, before=10.0, after=999.0)
    EpisodeRunner(instance=instance).run(low)
    EpisodeRunner(instance=instance).run(high)

    # The two controllers act identically through `switch_at`, so every observation that is a
    # function of those actions must match. That covers periods 1..switch_at+1: the observation
    # at switch_at+1 still predates the first differing action.
    for period in range(1, min(switch_at + 1, len(demand)) + 1):
        assert low.seen[period - 1] == high.seen[period - 1], (
            f"observation at period {period} moved in response to a later action"
        )
    # And the runs must eventually diverge, or the test proves nothing. The first differing
    # action is at switch_at+1, so the earliest observation that can move is switch_at+2 --
    # later still if that order happens to be a lost shipment.
    if switch_at + 2 <= len(demand):
        assert low.seen[switch_at + 1 :] != high.seen[switch_at + 1 :], (
            "the two arms never diverged, so the invariant was not actually exercised"
        )


# ---------------------------------------------------------------------------
# observation models
# ---------------------------------------------------------------------------


def test_uncensored_mode_exposes_true_demand() -> None:
    instance = make_instance(demand=(50.0, 50.0), lead_times=(0.0, 0.0))
    controller = SwitchController(switch_at=99, before=1.0, after=1.0)
    EpisodeRunner(instance=instance).run(controller)
    # Only 1 unit was available against demand of 50, yet the policy still sees 50.
    assert controller.seen[1].prev_demand == 50.0
    assert controller.seen[1].prev_sales is None


def test_censored_mode_exposes_sales_and_availability_only() -> None:
    instance = make_instance(
        demand=(50.0, 5.0, 5.0),
        lead_times=(0.0, 0.0, 0.0),
        mode=ObservationMode.CENSORED,
    )
    controller = SwitchController(switch_at=99, before=10.0, after=10.0)
    EpisodeRunner(instance=instance).run(controller)

    stockout, satisfied = controller.seen[1], controller.seen[2]
    assert stockout.prev_demand is None
    assert stockout.prev_sales == 10.0, "sold what was on hand, not the 50 demanded"
    assert stockout.prev_availability is False, "ended empty, so the sales figure is censored"
    assert satisfied.prev_sales == 5.0
    assert satisfied.prev_availability is True


def test_alerts_reach_the_observation_and_template_ids_do_not() -> None:
    instance = make_instance(demand=(1.0, 1.0), lead_times=(0.0, 0.0))
    alert = AlertMessage(alert_id="a1", period=2, text="supplier reports a delay")
    controller = SwitchController(switch_at=99, before=1.0, after=1.0)
    runner = EpisodeRunner(instance=instance, alerts={2: alert}, template_ids={2: "tpl_07"})
    outcome = runner.run(controller)

    assert controller.seen[0].alert is None
    assert controller.seen[1].alert == alert
    # template_id is analysis-side: it must reach the record and not the observation.
    assert not hasattr(controller.seen[1].alert, "template_id")
    assert outcome.result.records[1].template_id == "tpl_07"


# ---------------------------------------------------------------------------
# hidden-state isolation
# ---------------------------------------------------------------------------


def test_observations_never_expose_hidden_incident_or_supply() -> None:
    incident = HiddenIncident(
        family=ShockFamily.DEMAND_LEVEL,
        onset_period=2,
        magnitude=2.0,
        duration=3,
        conditional_independence=True,
    )
    instance = make_instance(
        demand=(5.0, 20.0, 20.0), lead_times=(0.0, 0.0, 0.0), incident=incident
    )
    controller = SwitchController(switch_at=99, before=5.0, after=5.0)
    runner = EpisodeRunner(instance=instance)
    runner.run(controller)

    assert runner.incident is incident, "the evaluator still needs the truth"
    for obs in controller.seen:
        assert find_hidden_state(obs) == []


def test_a_controller_holding_hidden_truth_is_caught_when_checking_is_on() -> None:
    incident = HiddenIncident(
        family=ShockFamily.SHIPMENT_LOSS,
        onset_period=1,
        magnitude=1.0,
        duration=1,
        conditional_independence=True,
    )

    class Cheater:
        arm_id = "cheater"

        def __init__(self, truth: HiddenIncident) -> None:
            self.truth = truth

        def reset(self) -> None: ...

        def order(self, obs: PeriodObservation) -> Decision:
            return Decision(period=obs.period, order_quantity=0.0, arm_id=self.arm_id)

    instance = make_instance(demand=(1.0,), lead_times=(0.0,))
    runner = EpisodeRunner(instance=instance, check_controller_isolation=True)
    with pytest.raises(HiddenStateLeak, match="cheater"):
        runner.run(Cheater(incident))


# ---------------------------------------------------------------------------
# outcome plumbing
# ---------------------------------------------------------------------------


def test_order_rows_are_shaped_for_results_csv() -> None:
    instance = make_instance(demand=(1.0, 1.0, 1.0), lead_times=(0.0, 0.0, 0.0))
    outcome = EpisodeRunner(instance=instance).run(ConstantController(3.7))
    assert outcome.order_rows() == ((1, 3), (2, 3), (3, 3))


def test_normalized_reward_is_floored_at_zero() -> None:
    """A policy that only accrues holding cost scores 0, not a negative number."""
    instance = make_instance(demand=(0.0, 0.0), lead_times=(0.0, 0.0))
    outcome = EpisodeRunner(instance=instance).run(ConstantController(10.0))
    assert outcome.result.total_reward < 0
    assert outcome.result.normalized_reward == 0.0


def test_undelivered_units_are_reported() -> None:
    instance = make_instance(demand=(1.0, 1.0), lead_times=(math.inf, 4.0))
    outcome = EpisodeRunner(instance=instance).run(ConstantController(10.0))
    assert outcome.lost_units == 10.0
    # 10 lost plus 10 still in transit when the horizon ended
    assert outcome.undelivered_units == 20.0
