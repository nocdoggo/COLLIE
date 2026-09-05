"""Task 6 — baseline harness, shock families, and the generated-episode invariants.

Wave 1 covers the baseline harness: determinism, twin construction, integer cells, and
statistical sanity against the official patterns the baselines are anchored to
(``docs/module01_research_notes.md`` §1).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings

from collie.data.families.base import (
    ONSET_HI,
    ONSET_LO,
    BaselineKind,
    BaselineSpec,
    as_demand_cells,
    draw_baseline,
    draw_onset,
    episode_rngs,
    generate_baseline,
)
from tests.strategies import baseline_specs, horizons, seeds

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
