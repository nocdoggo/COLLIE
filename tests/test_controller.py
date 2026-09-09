"""Module 04, Checkpoint 1 — the shared capped base-stock controller.

``test_shared_control_path_byte_identical`` is called out in
``docs/implementation/04-or-compiler.md`` as the single most valuable test in this module: every
arm-level profit comparison in the paper is only meaningful if arms differ solely in *which*
``ControlConfig`` is active, never in what a controller does with one.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from collie.contracts import ControlConfig, PeriodObservation
from collie.control.controller import OrCompilerController, base_stock_target, critical_fractile
from collie.control.grid import BASELINE_CONFIG, GAMMA_VALUES, L_EFF_VALUES, M_VALUES

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_SRC = REPO_ROOT / "collie/control/controller.py"


def _obs(
    period: int,
    *,
    on_hand: float = 0.0,
    in_transit_total: float = 0.0,
    profit_per_unit: float = 4.0,
    holding_cost_per_unit: float = 1.0,
    prev_demand: float | None = 0.0,
    promised_lead_time: int = 2,
) -> PeriodObservation:
    return PeriodObservation(
        period=period,
        date=f"t{period}",
        on_hand=on_hand,
        in_transit_total=in_transit_total,
        prev_order=0.0,
        prev_arrivals=0.0,
        profit_per_unit=profit_per_unit,
        holding_cost_per_unit=holding_cost_per_unit,
        promised_lead_time=promised_lead_time,
        prev_demand=prev_demand,
    )


# ---------------------------------------------------------------------------
# arithmetic
# ---------------------------------------------------------------------------


def test_critical_fractile_arithmetic() -> None:
    assert critical_fractile(19.0, 1.0) == pytest.approx(19.0 / 20.0)
    assert critical_fractile(4.0, 1.0) == pytest.approx(4.0 / 5.0)
    assert critical_fractile(1.0, 1.0) == pytest.approx(0.5)


def test_base_stock_target_matches_hand_computation() -> None:
    from scipy.stats import norm

    config = ControlConfig(m=1.0, l_eff=1, gamma=1.0, predictive_model="stationary")
    fractile = critical_fractile(19.0, 1.0)
    target = base_stock_target(config, mean=100.0, std=10.0, fractile=fractile)
    expected = 2 * 100.0 + float(norm.ppf(fractile)) * math.sqrt(2) * 10.0
    assert target == pytest.approx(expected)


def test_higher_m_raises_the_target() -> None:
    config_lo = ControlConfig(m=0.6, l_eff=2, gamma=1.0, predictive_model="probe")
    config_hi = ControlConfig(m=2.0, l_eff=2, gamma=1.0, predictive_model="probe")
    lo = base_stock_target(config_lo, mean=100.0, std=10.0, fractile=0.8)
    hi = base_stock_target(config_hi, mean=100.0, std=10.0, fractile=0.8)
    assert hi > lo


@given(
    m1=st.sampled_from(M_VALUES),
    m2=st.sampled_from(M_VALUES),
    l_eff=st.sampled_from(L_EFF_VALUES),
    mean=st.floats(min_value=1.0, max_value=500.0),
    std=st.floats(min_value=0.0, max_value=100.0),
    fractile=st.floats(min_value=0.05, max_value=0.95),
)
def test_higher_m_raises_the_target_property(
    m1: float, m2: float, l_eff: int, mean: float, std: float, fractile: float
) -> None:
    lo_m, hi_m = sorted((m1, m2))
    lo = base_stock_target(
        ControlConfig(m=lo_m, l_eff=l_eff, gamma=1.0, predictive_model="probe"),
        mean=mean,
        std=std,
        fractile=fractile,
    )
    hi = base_stock_target(
        ControlConfig(m=hi_m, l_eff=l_eff, gamma=1.0, predictive_model="probe"),
        mean=mean,
        std=std,
        fractile=fractile,
    )
    assert hi >= lo - 1e-9


@given(
    gamma1=st.sampled_from(GAMMA_VALUES),
    gamma2=st.sampled_from(GAMMA_VALUES),
    in_transit=st.floats(min_value=0.0, max_value=1000.0),
)
def test_higher_gamma_lowers_the_order(gamma1: float, gamma2: float, in_transit: float) -> None:
    lo_g, hi_g = sorted((gamma1, gamma2))
    common = dict(order_cap=math.inf, train_demand=(100.0,) * 20)
    ctrl_lo = OrCompilerController(
        config=ControlConfig(m=1.0, l_eff=2, gamma=lo_g, predictive_model="probe"), **common
    )
    ctrl_hi = OrCompilerController(
        config=ControlConfig(m=1.0, l_eff=2, gamma=hi_g, predictive_model="probe"), **common
    )
    obs = _obs(1, in_transit_total=in_transit)
    q_lo = ctrl_lo.order(obs).order_quantity
    q_hi = ctrl_hi.order(obs).order_quantity
    assert q_hi <= q_lo + 1e-9


# ---------------------------------------------------------------------------
# the cap
# ---------------------------------------------------------------------------


@given(
    on_hand=st.floats(min_value=0.0, max_value=2000.0),
    in_transit=st.floats(min_value=0.0, max_value=2000.0),
    order_cap=st.floats(min_value=0.0, max_value=500.0),
    config=st.builds(
        ControlConfig,
        m=st.sampled_from(M_VALUES),
        l_eff=st.sampled_from(L_EFF_VALUES),
        gamma=st.sampled_from(GAMMA_VALUES),
        predictive_model=st.just("probe"),
    ),
)
def test_order_is_within_cap(
    on_hand: float, in_transit: float, order_cap: float, config: ControlConfig
) -> None:
    ctrl = OrCompilerController(
        order_cap=order_cap, config=config, train_demand=(80.0, 120.0, 100.0)
    )
    q = ctrl.order(_obs(1, on_hand=on_hand, in_transit_total=in_transit)).order_quantity
    assert 0.0 <= q <= order_cap


def test_cap_comes_from_the_contract() -> None:
    """AST check: ``order_cap`` must be a required field with no numeric default anywhere in this
    module. A literal here would silently override the registered, per-episode cap."""
    tree = ast.parse(CONTROLLER_SRC.read_text(encoding="utf-8"))
    class_def = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "OrCompilerController"
    )
    for stmt in class_def.body:
        if isinstance(stmt, ast.AnnAssign) and getattr(stmt.target, "id", None) == "order_cap":
            assert stmt.value is None, "order_cap must have no default; it comes from the contract"
            return
    pytest.fail("OrCompilerController has no order_cap field to check")


def test_no_numeric_cap_literal_anywhere_in_the_module() -> None:
    tree = ast.parse(CONTROLLER_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            # 0/0.0/1.0 appear in max(0, ...) and the (1+l_eff) term; neither is a cap value.
            assert node.value in (0, 0.0, 1.0), (
                f"suspicious numeric literal in controller.py: {node.value}"
            )


# ---------------------------------------------------------------------------
# isolation
# ---------------------------------------------------------------------------


def test_controller_never_reads_actual_lead_times() -> None:
    """``PeriodObservation`` has no actual-lead-time field to begin with; this guards against one
    being added later and this controller reaching for it instead of ``l_eff``."""
    src = CONTROLLER_SRC.read_text(encoding="utf-8")
    for forbidden in (
        "actual_lead_time",
        "HiddenIncident",
        "SupplyRealization",
        "supply.csv",
        "incident.json",
    ):
        assert forbidden not in src


def test_controller_has_no_hidden_state_reachable() -> None:
    from collie.contracts import assert_no_hidden_state

    ctrl = OrCompilerController(order_cap=100.0, config=BASELINE_CONFIG, train_demand=(1.0, 2.0))
    assert_no_hidden_state(ctrl, context="OrCompilerController")


# ---------------------------------------------------------------------------
# determinism, statelessness between resets, and the shared path
# ---------------------------------------------------------------------------


def test_order_is_deterministic_given_the_same_history() -> None:
    ctrl_a = OrCompilerController(
        order_cap=1000.0, config=BASELINE_CONFIG, train_demand=(100.0,) * 5
    )
    ctrl_b = OrCompilerController(
        order_cap=1000.0, config=BASELINE_CONFIG, train_demand=(100.0,) * 5
    )
    for period, demand in enumerate((90.0, 110.0, 95.0, 105.0), start=1):
        obs = _obs(period, prev_demand=None if period == 1 else demand)
        assert ctrl_a.order(obs) == ctrl_b.order(obs)


def test_reset_clears_accumulated_history() -> None:
    ctrl = OrCompilerController(order_cap=math.inf, config=BASELINE_CONFIG, train_demand=())
    ctrl.order(_obs(1, prev_demand=None))
    ctrl.order(_obs(2, prev_demand=50.0))
    with_history = ctrl.order(_obs(3, prev_demand=500.0)).order_quantity
    ctrl.reset()
    ctrl.order(_obs(1, prev_demand=None))
    fresh = ctrl.order(_obs(2, prev_demand=50.0)).order_quantity
    assert with_history != fresh


def test_shared_control_path_byte_identical() -> None:
    """Every OR-compiler arm — the detector control, the parsing upper bound, and the oracle —
    is, as of this checkpoint, an instance of this exact class wrapping a chosen
    ``ControlConfig``. Two such instances, given the same config and the same observation
    sequence, must produce byte-identical decisions: any divergence would mean two arms could
    differ for a reason other than which hypothesis was active, which is the one thing the
    paper's arm ladder cannot tolerate.

    Once module 06 exists, extend this to construct the detector/parsing-upper-bound/oracle
    controllers through their real code paths and assert equality against a bare
    ``OrCompilerController`` directly, rather than two bare instances of it as done here.
    """
    config = ControlConfig(m=1.5, l_eff=3, gamma=0.5, predictive_model="probe")
    observations = [
        _obs(1, on_hand=0.0, in_transit_total=0.0, prev_demand=None),
        _obs(2, on_hand=10.0, in_transit_total=40.0, prev_demand=95.0),
        _obs(3, on_hand=0.0, in_transit_total=80.0, prev_demand=120.0),
        _obs(4, on_hand=5.0, in_transit_total=30.0, prev_demand=100.0),
    ]

    detector_control = OrCompilerController(
        order_cap=500.0, config=config, arm_id="detector_control"
    )
    parsing_upper_bound = OrCompilerController(
        order_cap=500.0, config=config, arm_id="parsing_upper_bound"
    )
    oracle = OrCompilerController(order_cap=500.0, config=config, arm_id="oracle_shockspec")

    for obs in observations:
        d1 = detector_control.order(obs)
        d2 = parsing_upper_bound.order(obs)
        d3 = oracle.order(obs)
        assert d1.order_quantity == d2.order_quantity == d3.order_quantity
        assert d1.control_config == d2.control_config == d3.control_config


def test_negative_order_cap_is_rejected() -> None:
    with pytest.raises(ValueError, match="order_cap"):
        OrCompilerController(order_cap=-1.0, config=BASELINE_CONFIG)
