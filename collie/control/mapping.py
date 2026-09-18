"""``ShockSpec`` -> :class:`~collie.contracts.ControlConfig`: total, pure, and registered.

Precedence order, fixed: ``shock_family -> direction -> magnitude_bin -> target_stream``.
``no_change`` maps to the baseline configuration, identically to no proposal at all.

Two tiers, and the split is deliberate rather than an implementation shortcut.

**Tier 1 — the semantic core.** The eight ``(shock_family, direction, target_stream)`` shapes a
well-formed prompt, repair path, or the oracle would actually produce (one per non-abstention
family, plus the up/down split for the two demand families). ``magnitude_bin`` selects severity
within each shape via a shared rank (LOW/MEDIUM/HIGH -> 1/2/3). This is the table the checkpoint
audit should read as the engineering judgement: demand-only families move ``m``; lead-time-shift
moves ``l_eff`` alone (still arriving, just later, so the pipeline stays trusted); shipment-loss
moves ``gamma`` alone (arrivals are the same expected timing, just less trustworthy in count);
transit-pause moves both (delayed *and* less trustworthy); compound moves ``m`` and the supply
pair together.

**Tier 2 — the closure.** Module 02's registry of legal family-signature pairings has not landed
on ``main`` yet (``docs/implementation/README.md``'s dependency graph). Until it does, the
*frozen* ``ShockSpec`` validator in ``collie/contracts.py`` alone defines "legal", and it permits
combinations no real generation path would produce — ``shock_family=demand_level`` paired with
``target_stream=arrival``, for instance. A mapping that raised on those would crash an arm the
day a fuzzer, an adversarial repair, or a wider registry produced one, so every one of them is
given a fixed, deterministic assignment computed once at import time. Enough of them are
routed onto the grid's otherwise-unreached points to make ``all_configs()`` fully reachable
(``test_every_config_is_reachable``); every other currently-legal-but-unintended combination
falls back to the baseline, i.e. behaves as if the model had abstained. When module 02's registry
lands and narrows the legal space to the eight canonical shapes, tier 2 becomes dead code reached
by nothing, which is expected: a total function is defined on the whole type even when most of
the type is not expected to occur, the same discipline as an exhaustive ``match`` statement's
``case _``. Reachability will then need to be re-derived from tier 1 alone, flagged here for
Checkpoint 2 coordination with P3/P4.

The mapping table (tier 1, the part that matters) is registered in ``prereg/prereg_v1.yaml``,
authored jointly with P4 in module 07 (``README.md``'s Checkpoint calendar has this at day 9).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from dataclasses import dataclass

from collie.contracts import (
    ControlConfig,
    Direction,
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.control.grid import (
    BASELINE_CONFIG,
    BASELINE_GAMMA,
    BASELINE_L_EFF,
    BASELINE_M,
    GAMMA_VALUES,
    L_EFF_VALUES,
    M_VALUES,
    predictive_model_for,
)

__all__ = [
    "CANONICAL_SHAPES",
    "compile_spec",
    "iter_legal_specs",
    "mapping_table",
]

# ---------------------------------------------------------------------------
# tier 1 — the semantic core
# ---------------------------------------------------------------------------

_RANK: dict[MagnitudeBin, int] = {MagnitudeBin.LOW: 1, MagnitudeBin.MEDIUM: 2, MagnitudeBin.HIGH: 3}

# Demand multiplier by severity rank. M_VALUES has three values above 1.0 and only two strictly
# below it, so the down side saturates at the floor for medium and high: a "medium" and a "severe"
# demand contraction are given the same, most-conservative multiplier, because understocking is
# the costlier mistake whenever profit exceeds holding cost (true in every registered cost ratio,
# docs/env_contract.md §8.2), so distinguishing them further is not worth a separate grid point.
_M_UP: dict[int, float] = {1: 1.25, 2: 1.5, 3: 2.0}
_M_DOWN: dict[int, float] = {1: 0.75, 2: 0.6, 3: 0.6}

# (l_eff, gamma) by severity rank, one map per supply family. Lead-time-shift moves l_eff alone
# (arrivals are just later; the pipeline is still trusted). Shipment-loss moves gamma alone
# (arrivals are on time; fewer of them can be trusted to still be real).
#
# Transit-pause is deliberately *not* symmetric with the other two. Reducing gamma while a pause
# is active tells the controller to discount in-transit inventory that InventoryBench's
# authoritative `eval/` harness already reports accurately (`docs/env_contract.md` §5): under
# that harness a lost order is simply never added to in-transit, so nothing is silently inflating
# the pipeline count for gamma to correct for. Discounting it anyway just makes the controller
# double-order against stock that is, in fact, still coming, and when a *paused* (as opposed to
# lost) shipment later arrives all at once, that double order and the delayed shipment land
# together — a bullwhip spike this project's own oracle-headroom probe caught directly
# (`grid.py --oracle-headroom`; see `04-or-compiler.md`'s Checkpoint 2 pass criteria). So
# transit-pause moves mostly l_eff, like a lead-time-shift, and reserves a gamma cut for the
# high-severity case only, where genuine conversion to a loss is plausible enough to hedge for.
_SUPPLY_BY_FAMILY: dict[ShockFamily, dict[int, tuple[int, float]]] = {
    ShockFamily.LEAD_TIME_SHIFT: {1: (2, 1.0), 2: (3, 1.0), 3: (4, 1.0)},
    ShockFamily.SHIPMENT_LOSS: {1: (1, 0.5), 2: (1, 0.0), 3: (1, 0.0)},
    ShockFamily.TRANSIT_PAUSE: {1: (2, 1.0), 2: (2, 1.0), 3: (3, 0.5)},
}

# Compound moves m and the supply pair together, at the same rank, and for the same reason the
# transit-pause map above avoids gamma: the oracle-headroom probe showed a gamma cut compounding
# with an m increase overshoots badly once both streams recover simultaneously. Kept mild and
# gamma-preserving through medium severity, escalating only at high. The direction enum has no
# "mixed, but demand down" member, so compound is registered as the up-and-worse case; a model
# believing demand fell *and* the pipeline is unreliable has to express that as two proposals
# under this schema, which the lifecycle already supports (04's controller does not need to know
# about that; it is a module 05/06 concern).
_COMPOUND_BY_RANK: dict[int, tuple[float, int, float]] = {
    1: (1.25, 2, 1.0),
    2: (1.25, 2, 1.0),
    3: (1.5, 3, 1.0),
}

CANONICAL_SHAPES: frozenset[tuple[ShockFamily, Direction, TargetStream]] = frozenset(
    {
        (ShockFamily.DEMAND_LEVEL, Direction.DEMAND_UP, TargetStream.DEMAND),
        (ShockFamily.DEMAND_LEVEL, Direction.DEMAND_DOWN, TargetStream.DEMAND),
        (ShockFamily.TEMPORARY_PULSE, Direction.DEMAND_UP, TargetStream.DEMAND),
        (ShockFamily.TEMPORARY_PULSE, Direction.DEMAND_DOWN, TargetStream.DEMAND),
        (ShockFamily.LEAD_TIME_SHIFT, Direction.ARRIVAL_DELAYED, TargetStream.ARRIVAL),
        (ShockFamily.SHIPMENT_LOSS, Direction.ARRIVAL_INTERRUPTED, TargetStream.ARRIVAL),
        (ShockFamily.TRANSIT_PAUSE, Direction.ARRIVAL_INTERRUPTED, TargetStream.ARRIVAL),
        (ShockFamily.COMPOUND, Direction.MIXED, TargetStream.BOTH),
    }
)
"""The shapes a real generator, repair path, or the oracle is expected to produce. Anticipates
module 02's eventual legal family-signature pairing registry."""


def _compile_canonical(spec: ShockSpec) -> ControlConfig:
    rank = _RANK[spec.magnitude_bin]
    family = spec.shock_family
    if family in (ShockFamily.DEMAND_LEVEL, ShockFamily.TEMPORARY_PULSE):
        m = _M_UP[rank] if spec.direction is Direction.DEMAND_UP else _M_DOWN[rank]
        l_eff, gamma = 1, 1.0  # baseline supply: a demand-only belief leaves it untouched
    elif family in _SUPPLY_BY_FAMILY:
        m = 1.0
        l_eff, gamma = _SUPPLY_BY_FAMILY[family][rank]
    elif family is ShockFamily.COMPOUND:
        m, l_eff, gamma = _COMPOUND_BY_RANK[rank]
    else:  # pragma: no cover - CANONICAL_SHAPES is exhaustive over non-abstention families
        raise AssertionError(f"no canonical rule for {family}")
    return ControlConfig(
        m=m, l_eff=l_eff, gamma=gamma, predictive_model=predictive_model_for(m, l_eff, gamma)
    )


# ---------------------------------------------------------------------------
# the legal space, as the frozen ShockSpec validator currently defines it
# ---------------------------------------------------------------------------

_NON_ABSTENTION_FAMILIES: tuple[ShockFamily, ...] = tuple(
    f for f in ShockFamily if f is not ShockFamily.NO_CHANGE
)
_NON_NONE_DIRECTIONS: tuple[Direction, ...] = tuple(d for d in Direction if d is not Direction.NONE)
_NON_NONE_STREAMS: tuple[TargetStream, ...] = tuple(
    t for t in TargetStream if t is not TargetStream.NONE
)
_MAGNITUDES: tuple[MagnitudeBin, ...] = (MagnitudeBin.LOW, MagnitudeBin.MEDIUM, MagnitudeBin.HIGH)


def _legal_shapes() -> list[tuple[ShockFamily, Direction, TargetStream]]:
    return list(
        itertools.product(_NON_ABSTENTION_FAMILIES, _NON_NONE_DIRECTIONS, _NON_NONE_STREAMS)
    )


def _residual_shapes() -> list[tuple[ShockFamily, Direction, TargetStream]]:
    return sorted(
        (s for s in _legal_shapes() if s not in CANONICAL_SHAPES),
        key=lambda s: (s[0].value, s[1].value, s[2].value),
    )


def _make_spec(
    family: ShockFamily,
    direction: Direction,
    magnitude: MagnitudeBin | None,
    stream: TargetStream,
    *,
    tag: str,
) -> ShockSpec:
    """Build a valid, fully-provenanced ``ShockSpec`` for exactly the four precedence fields, with
    every other field pinned to an arbitrary-but-valid placeholder. Used by the enumeration tests
    and by ``--print-table``; never by episode code."""
    is_abstention = family is ShockFamily.NO_CHANGE
    return ShockSpec(
        target_stream=stream,
        shock_family=family,
        direction=direction,
        onset_window=None if is_abstention else (1, 5),
        magnitude_bin=None if is_abstention else magnitude,
        persistence=Persistence.NONE if is_abstention else Persistence.PERSISTENT,
        duration_bin=DurationBin.NONE if is_abstention else DurationBin.LONGER,
        evidence_refs=(),
        prospective_signature=tag,
        tau_j=1,
        proposal_index=1,
        model_id="mapping_enumeration",
        decoding_hash="d" * 8,
        prompt_hash="p" * 8,
    )


def iter_legal_specs() -> Iterator[ShockSpec]:
    """Every ``ShockSpec`` shape the frozen validator currently accepts, exactly once each.

    Enumerated, not sampled, so ``test_mapping_is_total_over_the_legal_space`` and
    ``test_every_config_is_reachable`` can assert against the whole space rather than a corner
    of it. This will need to shrink to ``CANONICAL_SHAPES`` once module 02's registry lands.
    """
    yield _make_spec(
        ShockFamily.NO_CHANGE, Direction.NONE, None, TargetStream.NONE, tag="sig_no_change"
    )
    for family, direction, stream in _legal_shapes():
        for magnitude in _MAGNITUDES:
            tag = f"sig_{family.value}_{direction.value}_{stream.value}_{magnitude.value}"
            yield _make_spec(family, direction, magnitude, stream, tag=tag)


# ---------------------------------------------------------------------------
# tier 2 — the closure
# ---------------------------------------------------------------------------


def _all_grid_cells() -> list[tuple[float, int, float]]:
    return list(itertools.product(M_VALUES, L_EFF_VALUES, GAMMA_VALUES))


def _tier1_cells() -> set[tuple[float, int, float]]:
    cells = {(1.0, 1, 1.0)}  # the baseline / no_change point
    for family, direction, stream in CANONICAL_SHAPES:
        for magnitude in _MAGNITUDES:
            spec = _make_spec(family, direction, magnitude, stream, tag="probe")
            config = _compile_canonical(spec)
            cells.add((config.m, config.l_eff, config.gamma))
    return cells


def _build_closure_table() -> dict[
    tuple[ShockFamily, Direction, TargetStream, MagnitudeBin], tuple[float, int, float]
]:
    missing = [c for c in _all_grid_cells() if c not in _tier1_cells()]
    residual_specs = [
        (family, direction, stream, magnitude)
        for family, direction, stream in _residual_shapes()
        for magnitude in _MAGNITUDES
    ]
    if len(residual_specs) < len(missing):  # pragma: no cover - defensive, would be a design bug
        raise AssertionError(
            f"{len(missing)} grid points unreached by tier 1 but only {len(residual_specs)} "
            "residual specs available to close them; the schema shrank without updating the map"
        )
    return dict(zip(residual_specs, missing, strict=False))


_CLOSURE_TABLE = _build_closure_table()


# ---------------------------------------------------------------------------
# the public mapping
# ---------------------------------------------------------------------------


def compile_spec(spec: ShockSpec) -> ControlConfig:
    """The compiler. Total, pure, deterministic: no episode state, no history, no clock."""
    if spec.is_abstention:
        return BASELINE_CONFIG

    shape = (spec.shock_family, spec.direction, spec.target_stream)
    if shape in CANONICAL_SHAPES:
        return _compile_canonical(spec)

    key = (spec.shock_family, spec.direction, spec.target_stream, spec.magnitude_bin)
    cell = _CLOSURE_TABLE.get(key)
    if cell is None:
        return BASELINE_CONFIG
    m, l_eff, gamma = cell
    return ControlConfig(
        m=m, l_eff=l_eff, gamma=gamma, predictive_model=predictive_model_for(m, l_eff, gamma)
    )


def mapping_table() -> tuple[tuple[ShockSpec, ControlConfig], ...]:
    """Every legal spec shape against the config it compiles to. What ``--print-table`` prints
    and what Checkpoint 1's audit reads."""
    return tuple((spec, compile_spec(spec)) for spec in iter_legal_specs())


@dataclass(frozen=True, slots=True)
class GridCompiler:
    """The ``collie.arms.protocols.SpecCompiler`` seam, satisfied structurally by the grid.

    ``compile_spec`` is absolute around the grid reference point (m=1, l_eff=1, gamma=1), but
    the arms run per-instance baselines whose promised lead time is 0, 2, or 4 — applying the
    absolute point wholesale would change axes the hypothesis does not concern (a demand-up
    spec compiled to l_eff=1 silently cuts pipeline coverage below a promised 2, which exactly
    cancels the demand signal at ``m*(1+l_eff)``; measured on dev fixtures, the oracle's
    headroom collapsed to ~0 from this alone). The seam therefore composes, per the tier-1
    docstring's own axis semantics and the protocol's "given what is currently running":

    * abstention returns ``current`` unchanged ("carry on as before");
    * an axis the grid point leaves at the reference value is inherited from ``current`` —
      a demand hypothesis never touches the pipeline, a supply hypothesis never touches the
      demand multiplier, and the composition reduces to the static mapping exactly when
      ``current`` is ``BASELINE_CONFIG``;
    * an axis the grid point moves is applied relative to ``current``: ``m`` as the absolute
      belief multiplier, ``l_eff`` as the reference offset added to the running value,
      ``gamma`` as the reference ratio against the running value — "lengthen the pipeline"
      means longer than what is running, not the reference-anchored point the instance
      already sits at.

    ``predictive_model`` stays the label of the absolute grid point the mapping selected: it
    records the tier-1 belief *before* composition, which is instance-independent, so it is
    deliberately not recomputed from the composed axes. The verifier derives the hypothesis it
    tests from the spec itself, never from this label (prereg/deviations.md, 2026-09-18).
    Arms never import this module — the harness wires one instance in (``tests/conftest.py``).
    """

    def compile(self, spec: ShockSpec, *, current: ControlConfig) -> ControlConfig:
        if spec.is_abstention:
            return current
        cfg = compile_spec(spec)
        m = cfg.m if cfg.m != BASELINE_M else current.m
        if cfg.l_eff != BASELINE_L_EFF:
            l_eff = current.l_eff + (cfg.l_eff - BASELINE_L_EFF)
        else:
            l_eff = current.l_eff
        if cfg.gamma != BASELINE_GAMMA:
            gamma = current.gamma * (cfg.gamma / BASELINE_GAMMA)
        else:
            gamma = current.gamma
        return ControlConfig(m=m, l_eff=l_eff, gamma=gamma, predictive_model=cfg.predictive_model)


def _print_table() -> None:  # pragma: no cover - CLI only
    rows = mapping_table()
    print(
        f"{'family':<16} {'direction':<20} {'magnitude':<8} {'stream':<8}  ->  "
        f"{'m':>5} {'l_eff':>5} {'gamma':>5}  predictive_model"
    )
    for spec, config in rows:
        tier = (
            "tier1"
            if (spec.shock_family, spec.direction, spec.target_stream) in CANONICAL_SHAPES
            else "tier2"
        )
        mag = spec.magnitude_bin.value if spec.magnitude_bin else "-"
        print(
            f"{spec.shock_family.value:<16} {spec.direction.value:<20} {mag:<8} "
            f"{spec.target_stream.value:<8}  ->  {config.m:>5} {config.l_eff:>5} {config.gamma:>5}  "
            f"{config.predictive_model:<30} [{tier}]"
        )
    distinct = {(c.m, c.l_eff, c.gamma, c.predictive_model) for _, c in rows}
    print(f"\n{len(rows)} legal specs enumerated, {len(distinct)} distinct configs reached")


if __name__ == "__main__":  # pragma: no cover - CLI only
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--print-table", action="store_true")
    args = parser.parse_args()
    _print_table()
