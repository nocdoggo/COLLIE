"""Shared hypothesis strategies for the shock-generator suite (brief §7.1).

One module so every test file draws from the same registered ranges; a strategy that drifts
from the registered values would silently weaken the property it feeds.
"""

from __future__ import annotations

import math

from hypothesis import strategies as st

from collie.contracts import ShockFamily
from collie.data.families import base

seeds = st.integers(min_value=0, max_value=2**31 - 1)
horizons = st.integers(min_value=20, max_value=60)
onsets = st.integers(min_value=base.ONSET_LO, max_value=base.ONSET_HI)
multipliers = st.sampled_from([0.6, 0.75, 1.25, 1.5, 2.0])
lead_times = st.sampled_from([0, 1, 2, 3, 4, math.inf])
dispatch_seqs = st.lists(st.integers(min_value=0, max_value=500), min_size=1, max_size=60)
families = st.sampled_from(list(ShockFamily))

# A shock needs periods on both sides of its onset to be observable: enough runway before onset
# for the pre-onset invariance to mean something, and at least one period after it.
shock_horizons = st.integers(min_value=base.ONSET_HI + 2, max_value=60)


@st.composite
def baseline_specs(draw: st.DrawFn) -> base.BaselineSpec:
    kind = draw(st.sampled_from(list(base.BaselineKind)))
    if kind is base.BaselineKind.OVERDISPERSED:
        # var must exceed the mean, or the negative-binomial map is undefined.
        sd = draw(st.floats(min_value=math.sqrt(101.0) + 0.5, max_value=80.0))
        return base.BaselineSpec(kind=kind, sd=sd)
    if kind is base.BaselineKind.SEASONAL:
        return base.BaselineSpec(
            kind=kind,
            seasonal_period=draw(st.integers(min_value=3, max_value=25)),
            seasonal_amplitude=draw(st.floats(min_value=5.0, max_value=60.0)),
        )
    if kind is base.BaselineKind.DEPENDENT:
        return base.BaselineSpec(kind=kind, ar_phi=draw(st.floats(min_value=-0.9, max_value=0.9)))
    return base.BaselineSpec(kind=kind)


@st.composite
def family_params(
    draw: st.DrawFn,
    *,
    family: ShockFamily | None = None,
    baseline: base.BaselineSpec | None = None,
) -> base.FamilyParams:
    """Whole-episode configurations. ``None`` fields stay undrawn so the seed decides them."""
    return base.FamilyParams(
        family=family or draw(st.sampled_from(list(ShockFamily))),
        baseline=baseline or draw(baseline_specs()),
        onset=draw(st.one_of(st.none(), onsets)),
    )
