"""Module 06 wave 6 — arm 2 (telemetry HMM), the compile-once controls, and the upper bounds.

Layout: HMM unit tests, then arm 2, then the detector/keyword controls and the AlertSpec
parsing upper bound, then the oracle, then the two load-bearing cross-arm tests — routing
identity (R5.10) and the negative controls. No arm in ``collie/arms/controls.py`` or
``collie/arms/oracle.py`` calls an LLM, so there is no call ledger to conserve here; the
no-channel property is asserted by construction instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import norm

from collie.arms.base_stock import CappedBaseStockController, base_stock_order
from collie.arms.controls import (
    ALERTSPEC_UB_ARM_ID,
    ARM2_ARM_ID,
    DEMAND_UP_PAYLOAD,
    DETECTOR_CONTROL_ARM_ID,
    DETECTOR_PAYLOAD,
    EMISSION_HORIZON,
    HMM_A00,
    HMM_MU0,
    HMM_MU1,
    HMM_SIGMA0,
    HMM_SIGMA1,
    KEYWORD_CONTROL_ARM_ID,
    KEYWORD_RULES,
    AlertSpecUpperBoundArm,
    CompilerSwitchArm,
    DetectorToCompilerArm,
    KeywordParserArm,
    TelemetryHMMController,
    TwoRegimeHMM,
    alertspec_to_payload,
    parse_alert_text,
    telemetry_order,
)
from collie.arms.oracle import ORACLE_ARM_ID, OracleShockSpecArm, incident_to_payload
from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import ARM8_ARM_ID, ImmediateActivation, ShockSpecArm
from collie.contracts import (
    AlertKind,
    AlertMessage,
    ControlConfig,
    Controller,
    Direction,
    DurationBin,
    HiddenAlertSpec,
    HiddenIncident,
    HiddenStateLeak,
    MagnitudeBin,
    ObservationMode,
    PeriodObservation,
    Persistence,
    ShockFamily,
    Split,
    TargetStream,
    find_hidden_state,
)
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.data.families import generate_episode
from collie.data.families.demand import DEMAND_FAMILIES
from collie.data.splits import build_units
from collie.sim.runner import EpisodeRunner
from collie.trigger.calibration import FROZEN
from collie.trigger.detectors import Cusum
from collie.trigger.protocol import MaxProposalsWrapper, RefractoryWrapper
from tests.strategies_arms import demand_streams, make_observations
from tests.test_arms_direct import _ScriptedTrigger
from tests.test_arms_shockspec import _Parser, _Prompter
from tests.test_episode_runner import make_instance

# ---------------------------------------------------------------------------
# wiring helpers (conftest style: every collaborator injected)
# ---------------------------------------------------------------------------


def _factory(config: ControlConfig, demands: tuple[float, ...]) -> OrCompilerController:
    # No specific instance in scope here; every instance in this file carries the
    # ``make_instance`` default cap, so ``math.inf`` matches the contract exactly.
    return OrCompilerController(order_cap=math.inf, config=config, train_demand=demands)


def _base_kwargs(promised_lead_time: int = 2) -> dict:
    """The shared injections: the shared OR controller at the per-instance arm-1 descriptor."""
    return {
        "controller_factory": _factory,
        "baseline": OrCompilerController(
            order_cap=math.inf, config=baseline_config_for(promised_lead_time)
        ),
        "baseline_config": baseline_config_for(promised_lead_time),
    }


def _detector(trigger, *, compiler=None, promised_lead_time: int = 2) -> DetectorToCompilerArm:
    return DetectorToCompilerArm(
        compiler=compiler or GridCompiler(),
        trigger=trigger,
        **_base_kwargs(promised_lead_time),
    )


def _keyword(*, compiler=None, promised_lead_time: int = 2) -> KeywordParserArm:
    return KeywordParserArm(compiler=compiler or GridCompiler(), **_base_kwargs(promised_lead_time))


def _alert_spec() -> HiddenAlertSpec:
    """A demand-up persistent canonical spec — the class the routing test aligns on."""
    return HiddenAlertSpec(
        family=ShockFamily.DEMAND_LEVEL,
        target_stream=TargetStream.DEMAND,
        direction=Direction.DEMAND_UP,
        onset_window=(0, 0),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.PERSISTENT,
        duration_bin=DurationBin.LONGER,
        prospective_signature="sig_demand_level_up",
        kind=AlertKind.ACCURATE,
    )


def _ub(spec: HiddenAlertSpec, period: int, *, compiler=None) -> AlertSpecUpperBoundArm:
    return AlertSpecUpperBoundArm(
        compiler=compiler or GridCompiler(),
        alert_spec=spec,
        alert_period=period,
        **_base_kwargs(2),
    )


def _incident(onset: int = 12, horizon: int = 24) -> HiddenIncident:
    return HiddenIncident(
        family=ShockFamily.DEMAND_LEVEL,
        onset_period=onset,
        magnitude=1.5,
        duration=horizon - onset + 1,
        conditional_independence=True,
    )


def _oracle(
    incident: HiddenIncident, *, compiler=None, promised_lead_time: int = 2
) -> OracleShockSpecArm:
    return OracleShockSpecArm(
        compiler=compiler or GridCompiler(),
        incident=incident,
        **_base_kwargs(promised_lead_time),
    )


def _wrapped_cusum() -> MaxProposalsWrapper:
    """The LLM arms' exact wrap of a calibrated Cusum (mirrors ``collie/trigger/demo.py``)."""
    inner = Cusum(FROZEN.mu0, FROZEN.sigma0, FROZEN.cusum_k, FROZEN.cusum_h)
    return MaxProposalsWrapper(
        RefractoryWrapper(inner, FROZEN.refractory_window), FROZEN.max_proposals
    )


def _baseline_reference(outcome, promised_lead_time: int = 2) -> list[float]:
    """What a baseline-only controller would have ordered over the same observations."""
    check = OrCompilerController(order_cap=math.inf, config=baseline_config_for(promised_lead_time))
    check.reset()
    return [check.order(obs).order_quantity for obs in outcome.observations]


# ---------------------------------------------------------------------------
# TwoRegimeHMM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"a00": 1.0},
        {"a00": 0.0},
        {"a11": 1.0},
        {"sigma0": 0.0},
        {"sigma1": -1.0},
    ],
)
def test_hmm_rejects_degenerate_parameters(overrides) -> None:
    with pytest.raises(ValueError, match="must"):
        TwoRegimeHMM(**overrides)


def test_hmm_matches_a_hand_computed_alpha_pass() -> None:
    """Two steps recomputed independently: predict through the chain, weight, normalise."""
    hmm = TwoRegimeHMM()
    x = 108.0
    p = hmm.update(x)
    e0 = float(norm.pdf(x, loc=HMM_MU0, scale=HMM_SIGMA0))
    e1 = float(norm.pdf(x, loc=HMM_MU1, scale=HMM_SIGMA1))
    # From the degenerate normal prior, the prediction is [a00, 1 - a00].
    a0, a1 = HMM_A00 * e0, (1.0 - HMM_A00) * e1
    assert p == pytest.approx(a1 / (a0 + a1), rel=1e-12)

    # A second step from a non-degenerate alpha exercises both predict terms.
    y = 150.0
    q = hmm.update(y)
    f0 = float(norm.pdf(y, loc=HMM_MU0, scale=HMM_SIGMA0))
    f1 = float(norm.pdf(y, loc=HMM_MU1, scale=HMM_SIGMA1))
    a0n, a1n = a0 / (a0 + a1), a1 / (a0 + a1)
    b0 = (a0n * HMM_A00 + a1n * 0.10) * f0
    b1 = (a0n * (1.0 - HMM_A00) + a1n * 0.90) * f1
    assert q == pytest.approx(b1 / (b0 + b1), rel=1e-12)
    assert hmm.p_disrupted == q


def test_hmm_stays_near_zero_under_stationary_demand() -> None:
    """A seeded stationary draw at the registered law never lifts the regime belief."""
    rng = np.random.Generator(np.random.PCG64(42))
    hmm = TwoRegimeHMM()
    ps = [hmm.update(float(x)) for x in rng.normal(100.0, 25.0, 50)]
    assert max(ps) < 0.2  # observed max 0.136 on this stream
    assert ps[-1] < 0.1  # observed 0.045


def test_hmm_rises_after_a_level_shift() -> None:
    rng = np.random.Generator(np.random.PCG64(7))
    hmm = TwoRegimeHMM()
    pre = [hmm.update(float(x)) for x in rng.normal(100.0, 25.0, 20)]
    post = [hmm.update(float(x)) for x in rng.normal(160.0, 30.0, 30)]
    assert max(pre) < 0.2  # observed 0.116
    assert post[4] > 0.7  # five shifted observations suffice; observed 0.817
    assert post[-1] > 0.99  # observed 0.9994


def test_hmm_hysteresis_remembers_the_disruption() -> None:
    """The sticky chain is history-dependent: the same draw reads differently by context."""
    disturbed = TwoRegimeHMM()
    for x in (200.0,) * 10:
        p = disturbed.update(x)
    assert p > 0.9  # observed 0.998
    p_remembered = disturbed.update(100.0)
    p_fresh = TwoRegimeHMM().update(100.0)
    assert p_fresh < 0.05  # observed 0.0139: with no history the same draw reads as noise
    assert p_remembered > 0.5  # observed 0.859: one normal draw does not collapse the belief


def test_hmm_reset_replays_identically() -> None:
    hmm = TwoRegimeHMM()
    for x in (200.0,) * 5:
        hmm.update(x)
    assert hmm.p_disrupted > 0.9
    hmm.reset()
    assert hmm.p_disrupted == 0.0
    assert hmm.update(100.0) == TwoRegimeHMM().update(100.0)


def test_hmm_underflow_keeps_the_prediction() -> None:
    """Dozens of sigmas from either regime, both emissions underflow; keep the prediction."""
    hmm = TwoRegimeHMM()
    p = hmm.update(1e300)
    assert p == pytest.approx(1.0 - HMM_A00)  # the prediction off the degenerate prior
    assert hmm.p_disrupted == p  # state stayed normalised, no NaN


# ---------------------------------------------------------------------------
# arm 2
# ---------------------------------------------------------------------------

_SAMPLES = st.lists(st.integers(min_value=0, max_value=500), max_size=30).map(
    lambda xs: [float(x) for x in xs]
)
_STOCK = st.integers(min_value=0, max_value=2000).map(float)


@given(samples=_SAMPLES, on_hand=_STOCK, in_transit=_STOCK)
@settings(max_examples=50)
def test_telemetry_order_is_arm1_exactly_when_p_zero(samples, on_hand, in_transit) -> None:
    """At zero disrupted probability arm 2 is arm 1, bit for bit — not approximately."""
    got = telemetry_order(
        samples=samples,
        recent=samples[-5:],
        p_disrupted=0.0,
        on_hand=on_hand,
        in_transit=in_transit,
        promised_lead_time=2,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
    )
    expected = base_stock_order(
        samples=list(samples),
        on_hand=on_hand,
        in_transit=in_transit,
        promised_lead_time=2,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
    )
    assert got == expected


def test_telemetry_order_rises_with_the_disrupted_probability() -> None:
    """The blend is a genuine input: a disrupted recent window lifts the order. Spread samples
    and a stocked position keep the order off arm 1's cap, so the blend shows through."""
    kwargs = {
        "samples": [40.0, 160.0] * 5,  # mean 100, std 60: the cap sits at 199
        "recent": [150.0, 160.0],
        "on_hand": 180.0,
        "in_transit": 200.0,
        "promised_lead_time": 2,
        "profit_per_unit": 4.0,
        "holding_cost_per_unit": 1.0,
    }
    p0 = telemetry_order(p_disrupted=0.0, **kwargs)
    p8 = telemetry_order(p_disrupted=0.8, **kwargs)
    assert 0.0 < p0 < p8  # observed 13 then 79: interior orders, strictly rising in p


@given(demands=demand_streams)
@settings(max_examples=20)
def test_arm2_runs_through_the_runner_ordering_legally(demands) -> None:
    instance = make_instance(
        demand=tuple(float(d) for d in demands), lead_times=(0.0,) * len(demands)
    )
    outcome = EpisodeRunner(instance).run(TelemetryHMMController())
    assert len(outcome.decisions) == len(demands)
    for obs, dec in zip(outcome.observations, outcome.decisions, strict=True):
        assert dec.period == obs.period
        assert dec.order_quantity >= 0 and float(dec.order_quantity).is_integer()
        assert not dec.llm_called


def test_arm2_is_isolated() -> None:
    arm = TelemetryHMMController(train_demand=(100.0, 101.0))
    assert find_hidden_state(arm) == []
    instance = make_instance(demand=(100.0,) * 6, lead_times=(0.0,) * 6)
    EpisodeRunner(instance, check_controller_isolation=True).run(arm)


def test_arm2_refuses_censored_demand() -> None:
    instance = make_instance(
        demand=(50.0, 5.0, 5.0), lead_times=(0.0,) * 3, mode=ObservationMode.CENSORED
    )
    with pytest.raises(ValueError, match="uncensored-demand"):
        EpisodeRunner(instance).run(TelemetryHMMController())


def test_arm2_period_1_with_train_matches_arm1() -> None:
    """Period 1: the 0.0 reference init is neither recorded nor filtered, and with only train
    samples the recent window is empty — the fallback and the p=0 path together are arm 1."""
    train = (98.0, 103.0, 101.0)
    arm = TelemetryHMMController(train_demand=train)
    obs = PeriodObservation(
        period=1,
        date="Period_1",
        on_hand=5.0,
        in_transit_total=10.0,
        prev_order=0.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=0.0,
    )
    decision = arm.order(obs)
    expected = base_stock_order(
        samples=list(train),
        on_hand=5.0,
        in_transit=10.0,
        promised_lead_time=2,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
    )
    assert decision.order_quantity == expected
    assert arm._p_disrupted == 0.0 and arm.hmm.p_disrupted == 0.0
    assert arm._observed == []


def test_arm2_reset_replays_the_episode() -> None:
    arm = TelemetryHMMController()
    stream = make_observations([100.0] * 4 + [200.0] * 4)
    first = [arm.order(obs).order_quantity for obs in stream]
    assert arm._p_disrupted > 0.9  # the 200s shifted the regime belief
    arm.reset()
    assert arm._p_disrupted == 0.0 and arm._observed == [] and arm.hmm.p_disrupted == 0.0
    second = [arm.order(obs).order_quantity for obs in stream]
    assert first == second


@pytest.mark.parametrize("overrides", [{"recent_window": 0}, {"cap_quantile": 1.0}])
def test_arm2_validates_its_parameters(overrides) -> None:
    with pytest.raises(ValueError, match="must"):
        TelemetryHMMController(**overrides)


def test_frozen_disrupted_emissions_match_the_dev_registry() -> None:
    """The frozen-calibration discipline, mirroring tools/calibrate_triggers.py --check:
    recompute the disrupted emission from the deterministic dev registry and require exact
    equality — drift in the registry or the derivation fails the suite, not a manual step."""
    cells: list[float] = []
    for unit in build_units(Split.DEV):
        assert unit.params is not None  # dev units always carry params
        if unit.params.family not in DEMAND_FAMILIES:
            continue
        ep = generate_episode(seed=unit.seed, horizon=EMISSION_HORIZON, params=unit.params)
        cells.extend(ep.demand[ep.incident.onset_period - 1 :])  # literal post-onset demand
    assert len(cells) == 598  # 18 demand-side dev units; pins the derivation's sample set
    assert float(np.mean(cells)) == HMM_MU1
    assert float(np.std(cells)) == HMM_SIGMA1  # ddof=0, the Gaussian MLE


def test_arm_ids_are_the_registered_strings() -> None:
    assert ARM2_ARM_ID == "arm2_telemetry_hmm_or"
    assert DETECTOR_CONTROL_ARM_ID == "ctrl_cusum_to_compiler"
    assert KEYWORD_CONTROL_ARM_ID == "ctrl_keyword_parser"
    assert ALERTSPEC_UB_ARM_ID == "ctrl_alertspec_upper_bound"
    assert ORACLE_ARM_ID == "oracle_shockspec_headroom"


# ---------------------------------------------------------------------------
# the switch base and its no-LLM construction
# ---------------------------------------------------------------------------


def test_bare_switch_arm_never_switches_and_orders_baseline() -> None:
    """The base's condition is "never": every order is the injected baseline's, bit for bit."""
    instance = make_instance(
        demand=(100.0, 110.0, 90.0, 120.0, 80.0, 95.0), lead_times=(2.0,) * 6, promised_lead_time=2
    )
    arm = CompilerSwitchArm(compiler=GridCompiler(), arm_id="never", **_base_kwargs(2))
    outcome = EpisodeRunner(instance).run(arm)
    assert [d.order_quantity for d in outcome.decisions] == _baseline_reference(outcome)
    assert arm._switch_period is None and arm._compiled is None and arm._baseline_handoff is None
    assert all(
        d.control_config is None and d.active_spec_id is None and not d.triggered
        for d in outcome.decisions
    )


def test_no_arm_in_this_wave_can_call_an_llm_by_construction() -> None:
    """No channel attribute anywhere — the no-LLM property is structural, not behavioral."""
    arms = [
        TelemetryHMMController(),
        _detector(_ScriptedTrigger({2})),
        _keyword(),
        _ub(_alert_spec(), 2),
        _oracle(_incident()),
        CompilerSwitchArm(compiler=GridCompiler(), arm_id="never", **_base_kwargs(2)),
    ]
    for arm in arms:
        assert isinstance(arm, Controller)
        assert not hasattr(arm, "channel")


# ---------------------------------------------------------------------------
# control 1 — detector to compiler
# ---------------------------------------------------------------------------


def test_detector_control_switches_on_a_real_cusum_firing() -> None:
    """A 100 -> 150 level shift at period 10: first shifted demand is observed by the
    period-11 observation, each shifted period adds 150 - 100 - 12.5 = 37.5 to the statistic,
    and H = 5.18 * 25 = 129.5 is crossed by the fourth — the firing lands at period 14."""
    demand = (100.0,) * 9 + (150.0,) * 11
    instance = make_instance(demand=demand, lead_times=(2.0,) * 20, promised_lead_time=2)
    trigger = _wrapped_cusum()
    arm = _detector(trigger)
    assert arm.payload is DETECTOR_PAYLOAD
    assert DETECTOR_PAYLOAD is DEMAND_UP_PAYLOAD  # one shared fixed payload, by construction

    outcome = EpisodeRunner(instance).run(arm)

    assert trigger.trace.periods == (14,)  # switched exactly once
    assert arm._switch_period == 14
    # The fixed demand-up/medium payload compiles to the grid's demand-up m (1.5, absolute);
    # the supply axes are the hypothesis-untouched ones, so the seam inherits them from the
    # running baseline descriptor (l_eff=2, gamma=1.0 — the instance's promised lead time).
    expected_config = ControlConfig(m=1.5, l_eff=2, gamma=1.0, predictive_model="demand_up")
    for d in outcome.decisions:
        assert not d.llm_called
        if d.period < 14:
            assert d.control_config is None and d.active_spec_id is None and not d.triggered
        else:
            assert d.control_config == expected_config
            assert d.active_spec_id == "spec-1@tau14"
            assert d.triggered is (d.period == 14)

    # Pre-switch the arm *is* the baseline; the compiled controller differs once the shift
    # has landed in the sample set.
    reference = _baseline_reference(outcome)
    orders = [d.order_quantity for d in outcome.decisions]
    assert orders[:13] == reference[:13]
    assert orders[13:] != reference[13:]

    # The baseline-statistics handoff is the shockspec computation over demands 1..13.
    samples = demand[:13]
    mean = sum(samples) / len(samples)
    std = math.sqrt(sum((s - mean) ** 2 for s in samples) / (len(samples) - 1))
    assert arm._baseline_handoff == (mean, std)


def test_detector_control_stays_on_baseline_when_the_detector_never_fires() -> None:
    instance = make_instance(demand=(100.0,) * 8, lead_times=(2.0,) * 8, promised_lead_time=2)
    trigger = _wrapped_cusum()
    arm = _detector(trigger)
    outcome = EpisodeRunner(instance).run(arm)
    assert trigger.trace.periods == ()
    assert arm._switch_period is None
    assert [d.order_quantity for d in outcome.decisions] == _baseline_reference(outcome)


def test_detector_feeds_the_identical_compiler_as_the_llm_arms(harness) -> None:
    """R5.2: one compiler instance wired into both an LLM arm and the detector control."""
    shared = GridCompiler()
    instance = make_instance(demand=(100.0,) * 6, lead_times=(2.0,) * 6, promised_lead_time=2)
    llm_arm = ShockSpecArm(
        channel=harness.channel(arm_id=ARM8_ARM_ID, episode_id=instance.spec.episode_id),
        prompter=_Prompter(),
        parser=_Parser(),
        compiler=shared,
        activation=ImmediateActivation(),
        baseline=OrCompilerController(order_cap=math.inf, config=baseline_config_for(2)),
        controller_factory=_factory,
        trigger=_ScriptedTrigger({3}),
        baseline_config=baseline_config_for(2),
    )
    control = _detector(_ScriptedTrigger({3}), compiler=shared)
    assert control.compiler is llm_arm.compiler


def test_switch_at_period_1_hands_over_empty_baseline_stats() -> None:
    instance = make_instance(demand=(100.0,) * 4, lead_times=(2.0,) * 4, promised_lead_time=2)
    arm = _detector(_ScriptedTrigger({1}))
    outcome = EpisodeRunner(instance).run(arm)
    assert arm._switch_period == 1
    assert arm._baseline_handoff == (0.0, 0.0)  # no history yet
    assert outcome.decisions[0].order_quantity == 0.0  # an empty estimator orders nothing
    assert all(d.control_config is not None for d in outcome.decisions)


def test_switch_at_period_2_hands_over_a_single_sample() -> None:
    instance = make_instance(demand=(100.0,) * 4, lead_times=(2.0,) * 4, promised_lead_time=2)
    arm = _detector(_ScriptedTrigger({2}))
    EpisodeRunner(instance).run(arm)
    assert arm._switch_period == 2
    assert arm._baseline_handoff == (100.0, 0.0)  # one sample: mean is it, std is 0


def test_detector_control_is_isolated() -> None:
    arm = _detector(_wrapped_cusum())
    assert find_hidden_state(arm) == []
    instance = make_instance(demand=(100.0,) * 4, lead_times=(2.0,) * 4, promised_lead_time=2)
    EpisodeRunner(instance, check_controller_isolation=True).run(arm)


# ---------------------------------------------------------------------------
# control 2 — the keyword parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_index", "keyword"),
    [(i, kw) for i, (kws, _) in enumerate(KEYWORD_RULES) for kw in kws],
)
def test_every_keyword_maps_to_its_class_payload(rule_index, keyword) -> None:
    """The whole provisional table, one case per keyword, asserted against the template."""
    payload = parse_alert_text(f"the {keyword} was flagged today")
    assert payload == KEYWORD_RULES[rule_index][1]


def test_keyword_matching_is_case_insensitive_substring() -> None:
    assert parse_alert_text("DEMAND SURGE IMMINENT") == DEMAND_UP_PAYLOAD
    # The table's sharpest consequence, pinned deliberately: substring matching means "port"
    # fires inside "report". The table is module 06's control, reviewed at Gate 2.
    arrival = parse_alert_text("status report filed")
    assert arrival is not None and arrival.target_stream is TargetStream.ARRIVAL


def test_keyword_precedence_is_registration_order() -> None:
    """A text hitting several classes takes the first registered one (arrival before demand)."""
    payload = parse_alert_text("supplier reports a demand surge")
    assert payload is not None
    assert payload.target_stream is TargetStream.ARRIVAL
    assert payload.direction is Direction.ARRIVAL_INTERRUPTED


def test_keyword_abstains_on_unrelated_text() -> None:
    assert parse_alert_text("routine status note") is None
    instance = make_instance(demand=(100.0,) * 6, lead_times=(2.0,) * 6, promised_lead_time=2)
    alerts = {3: AlertMessage(alert_id="a3", period=3, text="routine status note")}
    arm = _keyword()
    outcome = EpisodeRunner(instance, alerts=alerts).run(arm)
    assert arm._switch_period is None
    assert [d.order_quantity for d in outcome.decisions] == _baseline_reference(outcome)


def test_keyword_first_decisive_alert_wins() -> None:
    """One spec per episode: the arrival alert at 7 is parsed-or-ignored only after the
    demand alert at 4 has already switched the arm — the config never becomes the arrival one."""
    instance = make_instance(demand=(100.0,) * 10, lead_times=(2.0,) * 10, promised_lead_time=2)
    alerts = {
        4: AlertMessage(alert_id="a4", period=4, text="a demand surge is expected"),
        7: AlertMessage(alert_id="a7", period=7, text="supplier reports a delay"),
    }
    arm = _keyword()
    outcome = EpisodeRunner(instance, alerts=alerts).run(arm)
    assert arm._switch_period == 4
    # An arrival payload would have compiled to the shipment-loss point (m=1.0, gamma=0.0);
    # the demand-up one carries m=1.5 with full pipeline trust.
    assert all(
        d.control_config is not None and d.control_config.m == 1.5 and d.control_config.gamma == 1.0
        for d in outcome.decisions[3:]
    )
    assert arm._spec is not None and arm._spec.evidence_refs == ("a4",)


def test_keyword_control_is_isolated() -> None:
    arm = _keyword()
    assert find_hidden_state(arm) == []
    instance = make_instance(demand=(100.0,) * 4, lead_times=(2.0,) * 4, promised_lead_time=2)
    alerts = {2: AlertMessage(alert_id="a2", period=2, text="demand spike")}
    EpisodeRunner(instance, alerts=alerts, check_controller_isolation=True).run(arm)
    assert arm._switch_period == 2
    assert arm._spec is not None and arm._spec.evidence_refs == ("a2",)


# ---------------------------------------------------------------------------
# the AlertSpec parsing upper bound (R5.5)
# ---------------------------------------------------------------------------


def test_alertspec_payload_maps_every_field_one_to_one() -> None:
    spec = HiddenAlertSpec(
        family=ShockFamily.TEMPORARY_PULSE,
        target_stream=TargetStream.DEMAND,
        direction=Direction.DEMAND_UP,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.HIGH,
        persistence=Persistence.TRANSIENT,
        duration_bin=DurationBin.SHORT,
        prospective_signature="sig_pulse",
        kind=AlertKind.ACCURATE,
    )
    assert alertspec_to_payload(spec) == ProposalPayload(
        target_stream=spec.target_stream,
        shock_family=spec.family,
        direction=spec.direction,
        onset_window=spec.onset_window,
        magnitude_bin=spec.magnitude_bin,
        persistence=spec.persistence,
        duration_bin=spec.duration_bin,
        evidence_refs=(),  # the one payload field with no canonical counterpart
        prospective_signature=spec.prospective_signature,
    )


def test_alertspec_ub_switches_at_the_alert_period() -> None:
    instance = make_instance(
        demand=(100.0,) * 5 + (150.0,) * 7, lead_times=(2.0,) * 12, promised_lead_time=2
    )
    arm = _ub(_alert_spec(), 6)
    outcome = EpisodeRunner(instance).run(arm)
    assert arm._switch_period == 6
    assert outcome.decisions[5].triggered
    assert all(d.control_config is None for d in outcome.decisions[:5])
    assert all(
        d.control_config == ControlConfig(m=1.5, l_eff=2, gamma=1.0, predictive_model="demand_up")
        and d.active_spec_id == "spec-1@tau6"
        for d in outcome.decisions[5:]
    )
    reference = _baseline_reference(outcome)
    assert [d.order_quantity for d in outcome.decisions[:5]] == reference[:5]


def test_alertspec_ub_is_the_only_control_carrying_hidden_truth() -> None:
    """The negative-space assertion: the walk FINDS the spec here, and nothing anywhere else."""
    arm = _ub(_alert_spec(), 6)
    assert find_hidden_state(arm) == ["obj.alert_spec"]
    assert find_hidden_state(_detector(_ScriptedTrigger({2}))) == []
    assert find_hidden_state(_keyword()) == []
    instance = make_instance(demand=(100.0,) * 6, lead_times=(2.0,) * 6)
    with pytest.raises(HiddenStateLeak, match="ctrl_alertspec_upper_bound"):
        EpisodeRunner(instance, check_controller_isolation=True).run(arm)


def test_alertspec_ub_rejects_a_nonpositive_alert_period() -> None:
    with pytest.raises(ValueError, match="alert_period"):
        _ub(_alert_spec(), 0)


# ---------------------------------------------------------------------------
# the oracle headroom bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("incident", "expected"),
    [
        (
            HiddenIncident(
                family=ShockFamily.DEMAND_LEVEL,
                onset_period=12,
                magnitude=1.5,
                duration=30,
                conditional_independence=True,
            ),
            (
                TargetStream.DEMAND,
                Direction.DEMAND_UP,
                Persistence.PERSISTENT,
                DurationBin.LONGER,
                MagnitudeBin.MEDIUM,
            ),
        ),
        (
            HiddenIncident(
                family=ShockFamily.DEMAND_LEVEL,
                onset_period=12,
                magnitude=0.75,
                duration=5,
                conditional_independence=True,
            ),
            (
                TargetStream.DEMAND,
                Direction.DEMAND_DOWN,
                Persistence.PERSISTENT,
                DurationBin.MEDIUM,
                MagnitudeBin.LOW,
            ),
        ),
        (
            HiddenIncident(
                family=ShockFamily.TEMPORARY_PULSE,
                onset_period=12,
                magnitude=2.0,
                duration=3,
                conditional_independence=True,
            ),
            (
                TargetStream.DEMAND,
                Direction.DEMAND_UP,
                Persistence.TRANSIENT,
                DurationBin.SHORT,
                MagnitudeBin.HIGH,
            ),
        ),
        (
            HiddenIncident(
                family=ShockFamily.LEAD_TIME_SHIFT,
                onset_period=12,
                magnitude=1.0,  # the supply-family fixture convention
                duration=40,
                conditional_independence=True,
            ),
            (
                TargetStream.ARRIVAL,
                Direction.ARRIVAL_DELAYED,
                Persistence.PERSISTENT,
                DurationBin.LONGER,
                MagnitudeBin.LOW,
            ),
        ),
        (
            HiddenIncident(
                family=ShockFamily.SHIPMENT_LOSS,
                onset_period=12,
                magnitude=1.0,
                duration=2,
                conditional_independence=True,
            ),
            (
                TargetStream.ARRIVAL,
                Direction.ARRIVAL_INTERRUPTED,
                Persistence.PERSISTENT,
                DurationBin.SHORT,
                MagnitudeBin.LOW,
            ),
        ),
        (
            HiddenIncident(
                family=ShockFamily.TRANSIT_PAUSE,
                onset_period=12,
                magnitude=1.0,
                duration=4,
                conditional_independence=True,
            ),
            (
                TargetStream.ARRIVAL,
                Direction.ARRIVAL_INTERRUPTED,
                Persistence.PERSISTENT,
                DurationBin.MEDIUM,
                MagnitudeBin.LOW,
            ),
        ),
    ],
)
def test_oracle_maps_truth_to_payload(incident, expected) -> None:
    stream, direction, persistence, duration_bin, magnitude_bin = expected
    payload = incident_to_payload(incident)
    assert payload.target_stream is stream
    assert payload.shock_family is incident.family
    assert payload.direction is direction
    assert payload.persistence is persistence
    assert payload.duration_bin is duration_bin
    assert payload.magnitude_bin is magnitude_bin
    assert payload.onset_window == (0, 0)
    assert payload.evidence_refs == ()
    assert payload.prospective_signature == f"sig_oracle_{incident.family.value}"


@pytest.mark.parametrize(
    ("incident", "match"),
    [
        (
            HiddenIncident(
                family=ShockFamily.COMPOUND,
                onset_period=12,
                magnitude=1.5,
                duration=8,
                conditional_independence=False,
            ),
            "does not map",
        ),
        (
            HiddenIncident(
                family=ShockFamily.DEMAND_LEVEL,
                onset_period=12,
                magnitude=1.0,
                duration=8,
                conditional_independence=True,
            ),
            "non-shock",
        ),
        (
            HiddenIncident(
                family=ShockFamily.DEMAND_LEVEL,
                onset_period=0,
                magnitude=1.5,
                duration=8,
                conditional_independence=True,
            ),
            "onset_period",
        ),
        (
            HiddenIncident(
                family=ShockFamily.DEMAND_LEVEL,
                onset_period=12,
                magnitude=1.5,
                duration=0,
                conditional_independence=True,
            ),
            "duration",
        ),
    ],
)
def test_oracle_refuses_unmappable_truth_at_construction(incident, match) -> None:
    with pytest.raises(ValueError, match=match):
        _oracle(incident)


def _step_instance(seed: int = 1, horizon: int = 24, onset: int = 12):
    """A dev-style shocked episode: the registered baseline law (seeded ~N(100, 25)) with a
    1.5x demand step at onset — family 1's shape, scripted. The seed is the first of the fixed
    PCG64 sequence, not a searched value; the margins below are pinned in the two tests."""
    rng = np.random.Generator(np.random.PCG64(seed))
    base = np.floor(np.maximum(rng.normal(100.0, 25.0, horizon), 0.0) + 0.5)
    demand = tuple(float(v) for v in base[: onset - 1]) + (150.0,) * (horizon - onset + 1)
    incident = HiddenIncident(
        family=ShockFamily.DEMAND_LEVEL,
        onset_period=onset,
        magnitude=1.5,
        duration=horizon - onset + 1,
        conditional_independence=True,
    )
    instance = make_instance(
        demand=demand,
        lead_times=(2.0,) * horizon,
        promised_lead_time=2,
        incident=incident,
    )
    return instance, incident


def test_oracle_switches_at_the_true_onset() -> None:
    instance, incident = _step_instance()
    arm = _oracle(incident)
    outcome = EpisodeRunner(instance).run(arm)
    assert arm._switch_period == incident.onset_period == 12
    assert all(d.control_config is None for d in outcome.decisions[:11])
    assert outcome.decisions[11].triggered
    assert all(d.active_spec_id == "spec-1@tau12" for d in outcome.decisions[11:])
    spec = arm._spec
    assert spec is not None
    assert spec.tau_j == 12 and spec.proposal_index == 1
    assert spec.direction is Direction.DEMAND_UP
    assert spec.persistence is Persistence.PERSISTENT
    assert spec.duration_bin is DurationBin.LONGER  # duration 13
    assert spec.magnitude_bin is MagnitudeBin.MEDIUM  # |1.5 - 1| = 0.5
    assert spec.model_id == "none"  # no model produced this spec — provenance is honest


def test_oracle_beats_arm1_on_the_shocked_episode() -> None:
    """The headroom test: switching at exactly the right period is worth +0.0273 normalized
    reward here (arm 1 scores 0.7838, the oracle 0.8111 — pinned values, this scenario,
    measured through module 04's real compiler and shared controller)."""
    instance, incident = _step_instance()
    arm1 = EpisodeRunner(instance).run(CappedBaseStockController()).result.normalized_reward
    oracle = EpisodeRunner(instance).run(_oracle(incident)).result.normalized_reward
    assert oracle >= arm1
    assert oracle > arm1 + 0.01  # a real margin, not a tie


def test_oracle_margin_is_sensitive_to_the_onset() -> None:
    """Negative control (b): the same oracle told the onset is one period later keeps a
    strictly smaller margin over arm 1 (+0.0167 vs +0.0273 here) — the headroom test would
    notice a mistimed switch."""
    instance, incident = _step_instance()
    arm1 = EpisodeRunner(instance).run(CappedBaseStockController()).result.normalized_reward
    margin_true = EpisodeRunner(instance).run(_oracle(incident)).result.normalized_reward - arm1
    late = replace(incident, onset_period=incident.onset_period + 1)
    margin_late = EpisodeRunner(instance).run(_oracle(late)).result.normalized_reward - arm1
    assert margin_true > 0.0
    assert 0.0 < margin_late < margin_true


def test_oracle_stands_down_when_the_hazard_window_closes() -> None:
    """Module 04's checkpoint finding, pinned: a hazard config held past a short-lived shock
    manufactures losses, so the oracle — privileged to know the true duration — reverts to the
    baseline dispatch after ``onset + duration - 1``. With duration 2 the compiled config
    governs periods 12-13 only; from period 14 on every decision carries no config and orders
    exactly what a baseline-only controller orders (its estimator never skipped a period)."""
    instance, incident = _step_instance()
    outcome = EpisodeRunner(instance).run(_oracle(replace(incident, duration=2)))
    assert all(d.control_config is None for d in outcome.decisions[:11])
    assert [d.active_spec_id for d in outcome.decisions[11:13]] == ["spec-1@tau12"] * 2
    assert all(
        d.control_config is None and d.active_spec_id is None and not d.triggered
        for d in outcome.decisions[13:]
    )
    reference = _baseline_reference(outcome)
    assert [d.order_quantity for d in outcome.decisions[13:]] == reference[13:]


def test_oracle_arrival_stream_switch_hands_over_arrival_stats() -> None:
    """A supply-family oracle switch reads the arrival stream for the baseline handoff."""
    incident = HiddenIncident(
        family=ShockFamily.SHIPMENT_LOSS,
        onset_period=4,
        magnitude=1.0,
        duration=2,
        conditional_independence=True,
    )
    instance = make_instance(demand=(100.0,) * 8, lead_times=(2.0,) * 8, promised_lead_time=2)
    arm = _oracle(incident)
    outcome = EpisodeRunner(instance).run(arm)
    assert arm._switch_period == 4
    arrivals = [r.arrivals for r in outcome.result.records if r.period < 4]
    mean = sum(arrivals) / len(arrivals)
    std = math.sqrt(sum((a - mean) ** 2 for a in arrivals) / (len(arrivals) - 1))
    assert arm._baseline_handoff == (mean, std)
    # The arrival interruption compiled to the shipment-loss grid gamma (0.5, scaling the
    # running trust); demand level and the pipeline length are hypothesis-untouched, so the
    # seam inherits them from the baseline descriptor (m=1.0, l_eff=2).
    assert outcome.decisions[3].control_config == ControlConfig(
        m=1.0, l_eff=2, gamma=0.5, predictive_model="shipment_loss"
    )


def test_oracle_carries_the_incident_and_the_runner_knows() -> None:
    arm = _oracle(_incident())
    assert find_hidden_state(arm) == ["obj.incident"]
    instance = make_instance(demand=(100.0,) * 4, lead_times=(2.0,) * 4)
    with pytest.raises(HiddenStateLeak, match="oracle_shockspec_headroom"):
        EpisodeRunner(instance, check_controller_isolation=True).run(arm)


# ---------------------------------------------------------------------------
# routing identity (R5.10) — the row the auditor reads first
# ---------------------------------------------------------------------------


def test_every_control_and_the_oracle_route_identically() -> None:
    """Given the same compiled config at the same period, all four arms produce byte-identical
    order streams: the compiler -> controller path is shared, so only the *condition* differs.

    The detector control takes a scripted trigger here on purpose — this test isolates the
    routing, and the detector's real firing timing is pinned separately against a genuine
    wrapped Cusum above. All four switch at period 6 onto the demand-up persistent config."""
    period = 6
    demand = (100.0,) * 5 + (150.0,) * 7
    instance = make_instance(demand=demand, lead_times=(2.0,) * 12, promised_lead_time=2)
    alerts = {period: AlertMessage(alert_id="a6", period=period, text="demand surge expected")}
    shared_compiler = GridCompiler()

    arms = {
        "detector": _detector(_ScriptedTrigger({period}), compiler=shared_compiler),
        "keyword": _keyword(compiler=shared_compiler),
        "alertspec_ub": _ub(_alert_spec(), period, compiler=shared_compiler),
        "oracle": _oracle(_incident(onset=period, horizon=12), compiler=shared_compiler),
    }
    streams: dict[str, list[float]] = {}
    for name, arm in arms.items():
        outcome = EpisodeRunner(instance, alerts=alerts).run(arm)
        assert arm._switch_period == period, name
        streams[name] = [d.order_quantity for d in outcome.decisions]
        assert all(not d.llm_called for d in outcome.decisions), name
        assert [d.triggered for d in outcome.decisions] == [False] * 5 + [True] + [False] * 6
        assert [d.active_spec_id for d in outcome.decisions] == [None] * 5 + ["spec-1@tau6"] * 7

    distinct = {tuple(stream) for stream in streams.values()}
    assert len(distinct) == 1, f"routing diverged: {streams}"

    # Non-vacuousness: the never-switch baseline over the same episode orders differently.
    never = CompilerSwitchArm(compiler=shared_compiler, arm_id="never", **_base_kwargs(2))
    baseline_outcome = EpisodeRunner(instance, alerts=alerts).run(never)
    baseline_stream = [d.order_quantity for d in baseline_outcome.decisions]
    assert baseline_stream != next(iter(distinct))


# ---------------------------------------------------------------------------
# negative control (a) — the isolation scan must fire
# ---------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True)
class _PeekingKeywordArm(KeywordParserArm):
    """A keyword arm that also holds the incident — the leak the scan exists to catch."""

    truth: HiddenIncident | None = None


def test_a_peeking_keyword_arm_fails_the_isolation_scan() -> None:
    """If this test ever passed trivially, the isolation walk would be broken, not the arm."""
    arm = _PeekingKeywordArm(compiler=GridCompiler(), truth=_incident(), **_base_kwargs(2))
    assert find_hidden_state(arm) == ["obj.truth"]
    instance = make_instance(demand=(100.0,) * 4, lead_times=(2.0,) * 4)
    with pytest.raises(HiddenStateLeak):
        EpisodeRunner(instance, check_controller_isolation=True).run(arm)
