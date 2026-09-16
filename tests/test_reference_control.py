"""The temporary module-04 stand-in: pinned to arm 1 at baseline, and the compiler's mapping.

The differential property is what makes "baseline OR runs while PROPOSED" literally true for
arms 8-10: at :func:`baseline_config`, the reference controller must reproduce
:class:`~collie.arms.base_stock.CappedBaseStockController` bit for bit on any episode. The
compiler tests pin the documented placeholder mapping so a later edit cannot drift it silently.
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings

from collie.arms.base_stock import CappedBaseStockController
from collie.arms.reference_control import (
    ReferenceCompiler,
    ReferenceController,
    baseline_config,
)
from collie.contracts import (
    ControlConfig,
    Direction,
    DurationBin,
    MagnitudeBin,
    ObservationMode,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.sim.runner import EpisodeRunner
from tests.strategies import seeds
from tests.test_episode_runner import make_instance


def _spec(**overrides) -> ShockSpec:
    """A minimal valid ShockSpec payload, provenance dummied, for compiler tests only."""
    base = dict(
        target_stream=TargetStream.DEMAND,
        shock_family=ShockFamily.DEMAND_LEVEL,
        direction=Direction.DEMAND_UP,
        onset_window=(1, 3),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.TRANSIENT,
        duration_bin=DurationBin.MEDIUM,
        evidence_refs=(),
        prospective_signature="sig_demand_level_up",
        tau_j=5,
        proposal_index=1,
        model_id="test",
        decoding_hash="det-v1",
        prompt_hash="0" * 64,
    )
    base.update(overrides)
    return ShockSpec(**base)


# ---------------------------------------------------------------------------
# the differential pin: reference controller at baseline == arm 1
# ---------------------------------------------------------------------------


@given(seed=seeds)
@settings(max_examples=40)
def test_baseline_config_reproduces_arm1_bit_for_bit(seed) -> None:
    rng = random.Random(seed)
    horizon = rng.randint(8, 30)
    promised = rng.choice([0, 2, 4])
    demand = tuple(float(rng.randint(0, 40)) for _ in range(horizon))
    lead_times = tuple(float(promised) for _ in range(horizon))
    train = tuple(float(rng.randint(0, 40)) for _ in range(rng.randint(0, 10)))
    instance = make_instance(
        demand=demand,
        lead_times=lead_times,
        promised_lead_time=promised,
        profit=float(rng.choice([1, 4, 19])),
    )
    arm1 = CappedBaseStockController(train_demand=train)
    reference = ReferenceController(config=baseline_config(promised), train_demand=train)
    out1 = EpisodeRunner(instance).run(arm1)
    out2 = EpisodeRunner(instance).run(reference)
    assert [d.order_quantity for d in out1.decisions] == [d.order_quantity for d in out2.decisions]


def test_baseline_config_fields() -> None:
    config = baseline_config(4)
    assert config == ControlConfig(m=1.0, l_eff=4, gamma=1.0, predictive_model="running")


# ---------------------------------------------------------------------------
# the compiler's documented placeholder mapping
# ---------------------------------------------------------------------------


def test_compiler_demand_up_and_down_scale_m() -> None:
    current = baseline_config(2)
    up = ReferenceCompiler().compile(_spec(direction=Direction.DEMAND_UP), current=current)
    down = ReferenceCompiler().compile(_spec(direction=Direction.DEMAND_DOWN), current=current)
    assert up.m == pytest.approx(1.5) and down.m == pytest.approx(0.5)
    assert up.l_eff == current.l_eff and down.l_eff == current.l_eff


def test_compiler_arrival_disruption_lengthens_the_pipeline() -> None:
    current = baseline_config(2)
    spec = _spec(
        target_stream=TargetStream.ARRIVAL,
        shock_family=ShockFamily.TRANSIT_PAUSE,
        direction=Direction.ARRIVAL_INTERRUPTED,
    )
    compiled = ReferenceCompiler().compile(spec, current=current)
    assert compiled.l_eff == current.l_eff + 1


def test_compiler_persistent_switches_to_ewma() -> None:
    compiled = ReferenceCompiler().compile(
        _spec(persistence=Persistence.PERSISTENT), current=baseline_config(2)
    )
    assert compiled.predictive_model == "ewma" and compiled.gamma == pytest.approx(0.3)


def test_compiler_abstention_is_the_identity() -> None:
    current = baseline_config(2)
    spec = _spec(
        target_stream=TargetStream.NONE,
        shock_family=ShockFamily.NO_CHANGE,
        direction=Direction.NONE,
        onset_window=None,
        magnitude_bin=None,
        persistence=Persistence.UNKNOWN,
        duration_bin=DurationBin.NONE,
    )
    assert ReferenceCompiler().compile(spec, current=current) == current


# ---------------------------------------------------------------------------
# controller error paths
# ---------------------------------------------------------------------------


def test_unknown_predictive_model_raises() -> None:
    controller = ReferenceController(
        config=ControlConfig(m=1.0, l_eff=2, gamma=1.0, predictive_model="made-up"),
        train_demand=(3.0, 4.0),
    )
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    with pytest.raises(ValueError, match="unknown predictive_model"):
        EpisodeRunner(instance).run(controller)


def test_ewma_gamma_bounds_are_enforced() -> None:
    controller = ReferenceController(
        config=ControlConfig(m=1.0, l_eff=2, gamma=0.0, predictive_model="ewma"),
        train_demand=(3.0, 4.0),
    )
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    with pytest.raises(ValueError, match="gamma"):
        EpisodeRunner(instance).run(controller)


def test_ewma_estimate_is_hand_computable() -> None:
    """EWMA seeded with the first sample: gamma=0.5 over (10, 20, 40) -> 0.5*40 + 0.5*15 = 27.5."""
    controller = ReferenceController(
        config=ControlConfig(m=1.0, l_eff=0, gamma=0.5, predictive_model="ewma"),
        train_demand=(10.0, 20.0, 40.0),
    )
    mean, _ = controller._estimates()
    assert mean == pytest.approx(27.5)


def test_ewma_controller_runs_an_episode() -> None:
    controller = ReferenceController(
        config=ControlConfig(m=1.0, l_eff=0, gamma=0.3, predictive_model="ewma"),
        train_demand=(10.0, 10.0),
    )
    instance = make_instance(demand=(5.0, 30.0, 5.0), lead_times=(0.0,) * 3)
    outcome = EpisodeRunner(instance).run(controller)
    assert all(float(d.order_quantity).is_integer() for d in outcome.decisions)


def test_censored_observations_are_refused() -> None:
    controller = ReferenceController(config=baseline_config(0))
    instance = make_instance(
        demand=(5.0, 6.0), lead_times=(0.0, 0.0), mode=ObservationMode.CENSORED
    )
    with pytest.raises(ValueError, match="uncensored"):
        EpisodeRunner(instance).run(controller)
