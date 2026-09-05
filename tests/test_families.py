"""Task 6 — baseline harness, shock families, and the generated-episode invariants.

Wave 1 covers the baseline harness: determinism, twin construction, integer cells, and
statistical sanity against the official patterns the baselines are anchored to
(``docs/module01_research_notes.md`` §1). Wave 2 adds demand families 1-3: the pre-onset
invariance, post-onset divergence, and parameter recovery. Wave 3 adds supply families
4-5 and unit conservation under the frozen supply physics.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collie.contracts import ShockFamily, SupplyEffectKind, SupplyRealization
from collie.data.families import demand, supply
from collie.data.families.base import (
    ONSET_HI,
    ONSET_LO,
    BaselineKind,
    BaselineSpec,
    FamilyParams,
    GeneratedEpisode,
    as_demand_cells,
    draw_baseline,
    draw_onset,
    episode_rngs,
    generate_baseline,
)
from collie.data.families.supply import COMPOUND_DURATION, COMPOUND_MAGNITUDES, COMPOUND_PAUSE
from collie.sim.supply import ArrivalKeyedSupply, LeadTimeSupply
from tests.strategies import (
    baseline_specs,
    dispatch_seqs,
    horizons,
    seeds,
    shock_horizons,
)

# ---------------------------------------------------------------------------
# rounding rule
# ---------------------------------------------------------------------------


def test_rounding_is_half_up_not_bankers() -> None:
    # 2.5 must go to 3; Python's round() would give 2.
    assert as_demand_cells([2.5, 3.5, 100.49, 100.5]) == (3.0, 4.0, 100.0, 101.0)


def test_rounding_clips_negative_draws_at_zero() -> None:
    # The official data shows min = 0 (p01 v2), so emitted cells never go negative.
    assert as_demand_cells([-4.2, -0.4, 0.0]) == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# determinism and twin construction
# ---------------------------------------------------------------------------


@given(seed=seeds, horizon=horizons, spec=baseline_specs())
@settings(max_examples=200)
def test_baseline_generation_is_bitwise_deterministic(
    seed: int, horizon: int, spec: BaselineSpec
) -> None:
    first = generate_baseline(seed=seed, horizon=horizon, spec=spec)
    second = generate_baseline(seed=seed, horizon=horizon, spec=spec)
    assert first == second, "same seed must reproduce the episode bit for bit"


@given(seed=seeds, horizon=horizons, spec=baseline_specs())
@settings(max_examples=200)
def test_twin_equals_baseline_before_any_shock(seed: int, horizon: int, spec: BaselineSpec) -> None:
    pair = generate_baseline(seed=seed, horizon=horizon, spec=spec)
    assert pair.twin == pair.baseline
    assert len(pair.baseline) == horizon
    assert len(pair.train) == 5, "official synthetic train.csv carries five rows"


@given(seed=seeds, horizon=horizons, spec=baseline_specs())
@settings(max_examples=200)
def test_every_emitted_cell_is_a_nonnegative_integer(
    seed: int, horizon: int, spec: BaselineSpec
) -> None:
    pair = generate_baseline(seed=seed, horizon=horizon, spec=spec)
    for cell in (*pair.baseline, *pair.train):
        assert cell == int(cell), f"non-integer cell {cell}"
        assert cell >= 0.0


def test_distinct_seeds_give_distinct_paths() -> None:
    a = generate_baseline(seed=1, horizon=30)
    b = generate_baseline(seed=2, horizon=30)
    assert a.baseline != b.baseline


def test_sub_streams_are_independent() -> None:
    # Drawing the onset must not move the baseline stream: spawn order is fixed and positional.
    rngs = episode_rngs(7)
    expected = draw_baseline(episode_rngs(7).baseline, BaselineSpec(), 30)
    draw_onset(rngs.onset)
    assert draw_baseline(rngs.baseline, BaselineSpec(), 30) == expected


@given(seed=seeds)
@settings(max_examples=200)
def test_onset_is_drawn_uniformly_in_range(seed: int) -> None:
    onset = draw_onset(episode_rngs(seed).onset)
    assert ONSET_LO <= onset <= ONSET_HI


def test_onset_draw_covers_the_whole_range() -> None:
    seen = {draw_onset(episode_rngs(s).onset) for s in range(200)}
    assert seen == set(range(ONSET_LO, ONSET_HI + 1))


def test_negative_seed_is_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        episode_rngs(-1)


# ---------------------------------------------------------------------------
# statistical sanity against the official patterns
# ---------------------------------------------------------------------------


def test_stationary_iid_matches_p01_v1() -> None:
    spec = BaselineSpec(kind=BaselineKind.STATIONARY_IID)
    cells = np.array(generate_baseline(seed=11, horizon=50, spec=spec).baseline)
    assert abs(cells.mean() - 100.0) < 10.0
    assert abs(cells.std(ddof=1) - 25.0) < 8.0


def test_seasonal_matches_p07_v1_period_and_amplitude() -> None:
    spec = BaselineSpec(kind=BaselineKind.SEASONAL)
    cells = np.array(generate_baseline(seed=12, horizon=50, spec=spec).baseline)
    centered = cells - cells.mean()
    # The period-10 sinusoid must dominate the autocorrelation at lag 10.
    ac10 = float(np.corrcoef(centered[:-10], centered[10:])[0, 1])
    ac5 = float(np.corrcoef(centered[:-5], centered[5:])[0, 1])
    assert ac10 > 0.5
    assert ac5 < 0.0, "half a period away the seasonal component anti-aligns"


def test_overdispersed_exceeds_poisson_like_spread() -> None:
    spec = BaselineSpec(kind=BaselineKind.OVERDISPERSED, sd=50.0)
    cells = np.array(generate_baseline(seed=13, horizon=50, spec=spec).baseline)
    # Registered dispersion: variance 2500 against the Poisson-like 100-scale of p02/p03.
    assert cells.var(ddof=1) > 5.0 * cells.mean()


def test_dependent_recovers_the_registered_ar_coefficient() -> None:
    spec = BaselineSpec(kind=BaselineKind.DEPENDENT, ar_phi=0.7)
    # n=50 per realization is far too noisy for a single-path estimate (the official p10
    # recovery hit the same wall), so pool the regression over 20 independent paths.
    num = den = 0.0
    for seed in range(20):
        cells = np.array(generate_baseline(seed=1000 + seed, horizon=50, spec=spec).baseline)
        centered = cells - cells.mean()
        num += float(np.sum(centered[1:] * centered[:-1]))
        den += float(np.sum(centered[:-1] ** 2))
    assert abs(num / den - 0.7) < 0.1


def test_baseline_specs_are_validated() -> None:
    with pytest.raises(ValueError, match="mean must be positive"):
        BaselineSpec(mean=0.0)
    with pytest.raises(ValueError, match="sd must be positive"):
        BaselineSpec(sd=0.0)
    with pytest.raises(ValueError, match="ar_phi"):
        BaselineSpec(ar_phi=1.0)
    with pytest.raises(ValueError, match="sd\*\*2 > mean"):
        draw_baseline(
            episode_rngs(0).baseline,
            BaselineSpec(kind=BaselineKind.OVERDISPERSED, mean=100.0, sd=9.0),
            10,
        )


# ---------------------------------------------------------------------------
# demand families 1-3
# ---------------------------------------------------------------------------

DEMAND = (1, 2, 3)


@given(
    seed=seeds,
    horizon=shock_horizons,
    family=st.sampled_from(DEMAND),
    spec=baseline_specs(),
)
@settings(max_examples=200)
def test_twin_identical_before_onset(
    seed: int, horizon: int, family: int, spec: BaselineSpec
) -> None:
    ep = demand.generate(seed=seed, horizon=horizon, params=FamilyParams(family, baseline=spec))
    onset = ep.incident.onset_period
    assert ep.demand[: onset - 1] == ep.twin_demand[: onset - 1]
    assert ep.lead_times == ep.twin_lead_times, "demand families never touch the supply path"
    assert ep.pause_active == ()


@given(
    seed=seeds,
    horizon=shock_horizons,
    family=st.sampled_from(DEMAND),
    spec=baseline_specs(),
)
@settings(max_examples=200)
def test_twin_differs_after_onset(seed: int, horizon: int, family: int, spec: BaselineSpec) -> None:
    ep = demand.generate(seed=seed, horizon=horizon, params=FamilyParams(family, baseline=spec))
    onset, duration = ep.incident.onset_period, ep.incident.duration
    window = slice(onset - 1, onset - 1 + duration)
    assert ep.demand[window] != ep.twin_demand[window], "the shock must be visible somewhere"


@given(seed=seeds, horizon=shock_horizons, family=st.sampled_from(DEMAND))
@settings(max_examples=200)
def test_onset_recorded_is_in_range_and_applies_the_multiplier(
    seed: int, horizon: int, family: int
) -> None:
    ep = demand.generate(seed=seed, horizon=horizon, params=FamilyParams(family))
    onset = ep.incident.onset_period
    assert ONSET_LO <= onset <= ONSET_HI
    # Every post-onset cell in the shock window is the twin cell scaled by m, half-up rounded.
    last = onset - 1 + ep.incident.duration
    for twin_cell, shocked_cell in zip(
        ep.twin_demand[onset - 1 : last], ep.demand[onset - 1 : last], strict=True
    ):
        assert shocked_cell == float(max(0, math.floor(twin_cell * ep.incident.magnitude + 0.5)))


@pytest.mark.parametrize(
    ("family", "magnitude"),
    [(1, 1.25), (1, 1.5), (2, 0.6), (2, 0.75), (3, 1.5), (3, 2.0)],
)
def test_parameter_recovery(family: int, magnitude: float) -> None:
    ep = demand.generate(
        seed=101,
        horizon=50,
        params=FamilyParams(
            family, onset=17, magnitude=magnitude, duration=3 if family == 3 else None
        ),
    )
    assert ep.incident.magnitude == magnitude
    onset, duration = ep.incident.onset_period, ep.incident.duration
    shocked = np.asarray(ep.demand[onset - 1 : onset - 1 + duration])
    twin = np.asarray(ep.twin_demand[onset - 1 : onset - 1 + duration])
    ratios = shocked[twin > 0] / twin[twin > 0]
    # Rounding moves each ratio by at most ~0.5/cell; the mean is far tighter.
    assert abs(float(ratios.mean()) - magnitude) < 0.01
    assert bool(np.all(np.abs(ratios - magnitude) < 0.03))


def test_persistent_families_run_to_the_horizon() -> None:
    for family in (1, 2):
        ep = demand.generate(
            seed=7,
            horizon=50,
            params=FamilyParams(family, onset=17, magnitude=1.25 if family == 1 else 0.75),
        )
        assert ep.incident.duration == 50 - 17 + 1
        assert ep.demand[16:] != ep.twin_demand[16:]
        assert ep.demand[:16] == ep.twin_demand[:16]


def test_pulse_truncates_at_the_horizon() -> None:
    ep = demand.generate(
        seed=7, horizon=24, params=FamilyParams(3, onset=22, magnitude=2.0, duration=4)
    )
    assert ep.incident.duration == 3, "22, 23, 24 — the fourth period falls off the end"
    assert ep.demand[21:] != ep.twin_demand[21:]


def test_onset_invisible_same_seed_different_onset() -> None:
    # The onset stream is independent of the baseline stream: two episodes that differ only in
    # onset must coincide on every period before the earlier onset.
    early = demand.generate(seed=42, horizon=50, params=FamilyParams(1, onset=14))
    late = demand.generate(seed=42, horizon=50, params=FamilyParams(1, onset=22))
    assert early.demand[:13] == late.demand[:13] == early.twin_demand[:13]


def test_conditional_independence_true_for_demand_families() -> None:
    for family in DEMAND:
        ep = demand.generate(seed=5, horizon=50, params=FamilyParams(family))
        assert ep.incident.conditional_independence is True
        assert ep.incident.supply_effect is None


def test_monotone_severity() -> None:
    kw = {"seed": 9, "horizon": 50}
    mild = demand.generate(**kw, params=FamilyParams(1, onset=17, magnitude=1.25))
    strong = demand.generate(**kw, params=FamilyParams(1, onset=17, magnitude=1.5))

    def deviation(ep: object) -> float:
        return float(np.sum(np.asarray(ep.demand) - np.asarray(ep.twin_demand)))

    assert deviation(strong) > deviation(mild) > 0.0


def test_demand_generate_rejects_supply_families() -> None:
    with pytest.raises(ValueError, match=r"demand\.generate handles"):
        demand.generate(seed=0, horizon=50, params=FamilyParams(4))


def test_onset_beyond_horizon_is_refused() -> None:
    with pytest.raises(ValueError, match="beyond the horizon"):
        demand.generate(seed=0, horizon=20, params=FamilyParams(1, onset=22))


def test_wrong_direction_magnitude_is_refused() -> None:
    with pytest.raises(ValueError, match="must exceed 1"):
        demand.generate(seed=0, horizon=50, params=FamilyParams(1, magnitude=0.75))
    with pytest.raises(ValueError, match=r"lie in \(0, 1\)"):
        demand.generate(seed=0, horizon=50, params=FamilyParams(2, magnitude=1.25))


def test_unknown_family_number_is_refused() -> None:
    with pytest.raises(ValueError, match="family must be one of"):
        FamilyParams(7)


# ---------------------------------------------------------------------------
# supply families 4-5
# ---------------------------------------------------------------------------


@given(
    seed=seeds,
    horizon=shock_horizons,
    family=st.sampled_from((4, 5)),
    spec=baseline_specs(),
)
@settings(max_examples=200)
def test_supply_twin_identical_before_onset(
    seed: int, horizon: int, family: int, spec: BaselineSpec
) -> None:
    ep = supply.generate(seed=seed, horizon=horizon, params=FamilyParams(family, baseline=spec))
    onset = ep.incident.onset_period
    assert ep.lead_times[: onset - 1] == ep.twin_lead_times[: onset - 1]
    assert ep.demand == ep.twin_demand, "supply families never touch the demand path"
    assert ep.pause_active == ()


@given(seed=seeds, horizon=shock_horizons, family=st.sampled_from((4, 5)))
@settings(max_examples=200)
def test_supply_twin_diverges_after_onset(seed: int, horizon: int, family: int) -> None:
    ep = supply.generate(seed=seed, horizon=horizon, params=FamilyParams(family))
    onset = ep.incident.onset_period
    assert ep.lead_times[onset - 1 :] != ep.twin_lead_times[onset - 1 :]


def test_lead_time_shift_parameter_recovery() -> None:
    ep = supply.generate(
        seed=202,
        horizon=50,
        params=FamilyParams(4, onset=15, baseline_lead_time=1, disrupted_lead_time=4),
    )
    assert ep.lead_times[:14] == (1.0,) * 14
    assert ep.lead_times[14:] == (4.0,) * 36
    assert ep.twin_lead_times == (1.0,) * 50
    effect = ep.incident.supply_effect
    assert effect is not None
    assert effect.kind is SupplyEffectKind.LEAD_TIME_SHIFT
    assert effect.start_period == 15
    assert effect.length == 36
    assert effect.disrupted_lead_time == 4
    assert ep.incident.duration == 36


def test_lead_time_shift_draws_stay_in_the_registered_sets() -> None:
    for seed in range(100):
        ep = supply.generate(seed=seed, horizon=50, params=FamilyParams(4))
        baseline = ep.twin_lead_times[0]
        effect = ep.incident.supply_effect
        assert baseline in (1.0, 2.0)
        assert effect is not None and effect.disrupted_lead_time in (3, 4)


def test_lead_time_shift_validation() -> None:
    with pytest.raises(ValueError, match="baseline lead time must be in"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(4, baseline_lead_time=3))
    with pytest.raises(ValueError, match=r"must be in .* and exceed"):
        supply.generate(
            seed=0,
            horizon=50,
            params=FamilyParams(4, baseline_lead_time=2, disrupted_lead_time=2),
        )


def test_shipment_loss_marks_exactly_the_burst() -> None:
    ep = supply.generate(seed=303, horizon=50, params=FamilyParams(5, onset=18, loss_length=3))
    expected = tuple(math.inf if 18 <= t <= 20 else 2.0 for t in range(1, 51))
    assert ep.lead_times == expected
    assert SupplyRealization(lead_times=ep.lead_times).n_lost == 3
    effect = ep.incident.supply_effect
    assert effect is not None
    assert effect.kind is SupplyEffectKind.SHIPMENT_LOSS
    assert effect.length == 3


def test_shipment_loss_burst_truncates_at_the_horizon() -> None:
    ep = supply.generate(seed=303, horizon=23, params=FamilyParams(5, onset=22, loss_length=3))
    assert ep.incident.duration == 2
    assert SupplyRealization(lead_times=ep.lead_times).n_lost == 2


def test_shipment_loss_draws_cover_the_registered_range() -> None:
    seen = {
        supply.generate(seed=s, horizon=50, params=FamilyParams(5)).incident.duration
        for s in range(200)
    }
    assert seen == {1, 2, 3}


@given(seed=seeds, dispatches=dispatch_seqs, family=st.sampled_from((4, 5)))
@settings(max_examples=200)
def test_supply_unit_conservation(seed: int, dispatches: list[int], family: int) -> None:
    horizon = max(len(dispatches), 24)
    orders = [float(q) for q in dispatches] + [0.0] * (horizon - len(dispatches))
    ep = supply.generate(seed=seed, horizon=horizon, params=FamilyParams(family))
    proc = LeadTimeSupply(SupplyRealization(lead_times=ep.lead_times))
    for t in range(1, horizon + 1):
        proc.dispatch(t, orders[t - 1])
        proc.receive(t)
        assert proc.dispatched_total == pytest.approx(
            proc.delivered_total + proc.in_transit_total(t) + proc.lost_total
        ), f"period {t}: dispatched != delivered + in transit + lost"


def test_conditional_independence_true_for_supply_families() -> None:
    for family in (4, 5):
        ep = supply.generate(seed=5, horizon=50, params=FamilyParams(family))
        assert ep.incident.conditional_independence is True
        assert ep.incident.supply_effect is not None


# ---------------------------------------------------------------------------
# family 6: compound demand shift with transit pause
# ---------------------------------------------------------------------------


def _run_arrivals(
    lead_times: tuple[float, ...], pause: tuple[bool, ...], orders: list[float]
) -> tuple[list[float], LeadTimeSupply]:
    proc = LeadTimeSupply(SupplyRealization(lead_times=lead_times, pause_active=pause))
    arrivals = []
    for t, qty in enumerate(orders, start=1):
        proc.dispatch(t, qty)
        arrivals.append(proc.receive(t))
    return arrivals, proc


def _compound(seed: int = 404, horizon: int = 50, **kw: object) -> GeneratedEpisode:
    params = FamilyParams(6, onset=17, **kw)
    return supply.generate(seed=seed, horizon=horizon, params=params)


def test_compound_shape_and_flag() -> None:
    ep = _compound(magnitude=1.5, duration=8, pause_length=4)
    assert ep.incident.family is ShockFamily.COMPOUND
    assert ep.incident.conditional_independence is False, (
        "one incident drives both streams; multiplying marginal ratios is prohibited"
    )
    assert ep.incident.duration == 8
    effect = ep.incident.supply_effect
    assert effect is not None
    assert effect.kind is SupplyEffectKind.TRANSIT_PAUSE
    assert effect.start_period == ep.incident.onset_period
    assert effect.length == 4
    # demand scaled on periods 17..24, pause active on 17..20
    assert ep.demand[:16] == ep.twin_demand[:16]
    assert ep.demand[16:24] != ep.twin_demand[16:24]
    assert ep.demand[24:] == ep.twin_demand[24:]
    assert ep.pause_active == tuple(17 <= t <= 20 for t in range(1, 51))
    assert ep.lead_times == ep.twin_lead_times == (2.0,) * 50


# Family 6 needs room for the full registered duration past the latest onset.
compound_horizons = st.integers(min_value=27, max_value=60)


@given(seed=seeds, horizon=compound_horizons)
@settings(max_examples=200)
def test_compound_draws_stay_in_the_registered_ranges(seed: int, horizon: int) -> None:
    ep = supply.generate(seed=seed, horizon=horizon, params=FamilyParams(6))
    assert ep.incident.magnitude in COMPOUND_MAGNITUDES
    assert COMPOUND_DURATION[0] <= ep.incident.duration <= COMPOUND_DURATION[1]
    effect = ep.incident.supply_effect
    assert effect is not None and COMPOUND_PAUSE[0] <= effect.length <= COMPOUND_PAUSE[1]


@given(seed=seeds, dispatches=dispatch_seqs)
@settings(max_examples=200)
def test_pause_conservation(seed: int, dispatches: list[int]) -> None:
    horizon = max(len(dispatches), 27)
    orders = [float(q) for q in dispatches] + [0.0] * (horizon - len(dispatches))
    ep = supply.generate(seed=seed, horizon=horizon, params=FamilyParams(6))
    proc = LeadTimeSupply(SupplyRealization(lead_times=ep.lead_times, pause_active=ep.pause_active))
    for t in range(1, horizon + 1):
        proc.dispatch(t, orders[t - 1])
        proc.receive(t)
        assert proc.dispatched_total == pytest.approx(
            proc.delivered_total + proc.in_transit_total(t) + proc.lost_total
        ), f"period {t}: dispatched != delivered + in transit + lost"
    assert proc.lost_total == 0.0, "a pause never loses units"


@given(seed=seeds, dispatches=dispatch_seqs)
@settings(max_examples=200)
def test_zero_arrivals_during_pause_and_correct_resumption(
    seed: int, dispatches: list[int]
) -> None:
    horizon = max(len(dispatches), 27)
    orders = [float(q) for q in dispatches] + [0.0] * (horizon - len(dispatches))
    ep = supply.generate(seed=seed, horizon=horizon, params=FamilyParams(6))
    effect = ep.incident.supply_effect
    assert effect is not None
    start, length = effect.start_period, effect.length
    arrivals, proc = _run_arrivals(ep.lead_times, ep.pause_active, orders)
    # A cohort whose transit completes exactly at the first paused period still lands
    # (frozen semantics, env contract §8.3); strictly inside the pause nothing can arrive.
    for t in range(start + 1, min(start + length, horizon + 1)):
        assert arrivals[t - 1] == 0.0, f"arrival of {arrivals[t - 1]} during pause period {t}"
    # Resumption: every dispatched unit eventually lands; nothing vanishes into the pause.
    assert proc.delivered_total + proc.in_transit_total(horizon) == pytest.approx(
        proc.dispatched_total
    )


def test_pause_delays_by_exactly_the_pause_length() -> None:
    horizon, onset, baseline_lt, pause_k = 40, 17, 2, 4
    ep = supply.generate(
        seed=404,
        horizon=horizon,
        params=FamilyParams(6, onset=onset, pause_length=pause_k, baseline_lead_time=baseline_lt),
    )

    def landing(order_period: int, pause: tuple[bool, ...]) -> int:
        orders = [1.0 if t == order_period else 0.0 for t in range(1, horizon + 1)]
        arrivals, _ = _run_arrivals(ep.lead_times, pause, orders)
        return next(t for t, a in enumerate(arrivals, start=1) if a > 0)

    no_pause = (False,) * horizon
    for t0 in range(1, horizon - baseline_lt - pause_k):
        normal = landing(t0, no_pause)
        paused = landing(t0, ep.pause_active)
        assert normal == t0 + baseline_lt
        if normal <= onset:
            # transit already complete at pause start: never held back (§8.3)
            assert paused == normal
        elif t0 < onset:
            # still moving when the pause starts: delayed by exactly the pause length
            assert paused == normal + pause_k
        else:
            # launched into (or after) the frozen pipeline: only the paused receives between
            # dispatch and recovery freeze it (research notes §3)
            assert paused == normal + max(0, onset + pause_k - t0)


def test_pause_matches_arrival_keyed_reference_when_inactive() -> None:
    # With pause_active all False the cohort model must be indistinguishable from the
    # arrival-keyed reference — the property the whole sidecar argument rests on.
    ep = supply.generate(seed=404, horizon=40, params=FamilyParams(6, onset=17, pause_length=4))
    orders = [float((37 * t) % 23) for t in range(1, 41)]
    paused_arrivals, _ = _run_arrivals(ep.lead_times, (False,) * 40, orders)
    ref = ArrivalKeyedSupply(SupplyRealization(lead_times=ep.lead_times))
    reference = []
    for t, qty in enumerate(orders, start=1):
        ref.dispatch(t, qty)
        reference.append(ref.receive(t))
    assert paused_arrivals == reference


def test_compound_needs_runway_for_the_registered_ranges() -> None:
    with pytest.raises(ValueError, match="periods of runway"):
        supply.generate(seed=0, horizon=26, params=FamilyParams(6, onset=22))


def test_compound_validation() -> None:
    with pytest.raises(ValueError, match="pipeline to freeze"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(6, baseline_lead_time=0))
    with pytest.raises(ValueError, match="magnitude must exceed 1"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(6, magnitude=0.8))
    with pytest.raises(ValueError, match="pause length must be"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(6, pause_length=0))


# ---------------------------------------------------------------------------
# guard coverage (audit note F4)
# ---------------------------------------------------------------------------


def test_horizon_must_be_positive() -> None:
    with pytest.raises(ValueError, match="horizon must be >= 1"):
        draw_baseline(episode_rngs(0).baseline, BaselineSpec(), 0)


def test_params_onset_out_of_range_is_refused() -> None:
    with pytest.raises(ValueError, match="onset must lie in"):
        FamilyParams(1, onset=5)


def test_supply_rejects_demand_families() -> None:
    with pytest.raises(ValueError, match=r"supply\.generate handles"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(1))


def test_negative_baseline_lead_time_is_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(5, baseline_lead_time=-1))
    with pytest.raises(ValueError, match="non-negative"):
        demand.generate(seed=0, horizon=50, params=FamilyParams(1, baseline_lead_time=-1))


def test_zero_lengths_are_refused() -> None:
    with pytest.raises(ValueError, match="at least one period"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(5, loss_length=0))
    with pytest.raises(ValueError, match="pulse duration must be"):
        demand.generate(seed=0, horizon=50, params=FamilyParams(3, duration=0))
    with pytest.raises(ValueError, match="compound duration must be"):
        supply.generate(seed=0, horizon=50, params=FamilyParams(6, duration=0))


def test_remaining_guards() -> None:
    with pytest.raises(ValueError, match="seasonal_period"):
        BaselineSpec(kind=BaselineKind.SEASONAL, seasonal_period=1)
    with pytest.raises(ValueError, match="beyond the horizon"):
        supply.generate(seed=0, horizon=20, params=FamilyParams(4, onset=22))
