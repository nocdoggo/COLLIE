"""Module 04, Checkpoint 1 — ``ShockSpec`` -> ``ControlConfig``, total and registered.

Every test here enumerates the legal space rather than sampling it
(``docs/implementation/04-or-compiler.md``'s explicit instruction), because a mapping with a gap
crashes an arm mid-episode on whichever spec falls in it, and sampling could miss that spec
forever.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from collie.contracts import ShockFamily, ShockSpec
from collie.control.grid import all_configs
from collie.control.mapping import CANONICAL_SHAPES, compile_spec, iter_legal_specs, mapping_table

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mapping_is_total_over_the_legal_space() -> None:
    """Every legal spec compiles without raising. Enumerated, not sampled."""
    specs = list(iter_legal_specs())
    assert len(specs) > 0
    for spec in specs:
        compile_spec(spec)  # must not raise


def test_mapping_is_deterministic() -> None:
    for spec in iter_legal_specs():
        assert compile_spec(spec) == compile_spec(spec)


def test_mapping_is_pure_of_anything_but_the_spec() -> None:
    """Calling it twice, interleaved with other specs, gives the same answer: no history, no
    clock, no accumulating state between calls."""
    specs = list(iter_legal_specs())
    first_pass = [compile_spec(s) for s in specs]
    second_pass = [compile_spec(s) for s in reversed(specs)]
    assert first_pass == list(reversed(second_pass))


def test_no_change_maps_to_baseline() -> None:
    from collie.control.grid import BASELINE_CONFIG

    (no_change_spec,) = [s for s in iter_legal_specs() if s.shock_family is ShockFamily.NO_CHANGE]
    assert compile_spec(no_change_spec) == BASELINE_CONFIG


def test_every_config_is_reachable() -> None:
    """The headline totality/surjectivity claim: running the mapping over the whole legal space
    hits every one of the 72 grid points, with no gaps and nothing extra."""
    reached = {compile_spec(spec) for spec in iter_legal_specs()}
    assert reached == set(all_configs())


def test_canonical_shapes_use_the_full_severity_range() -> None:
    """Sanity check on the semantic core (tier 1): magnitude actually moves the config for every
    canonical shape, i.e. LOW, MEDIUM, and HIGH are not silently collapsed to one point across
    the *whole* range (a family may legitimately saturate at the low or high end alone)."""
    from collie.contracts import MagnitudeBin

    for family, direction, stream in CANONICAL_SHAPES:
        if family is ShockFamily.NO_CHANGE:
            continue
        configs = set()
        for magnitude in (MagnitudeBin.LOW, MagnitudeBin.MEDIUM, MagnitudeBin.HIGH):
            spec = next(
                s
                for s in iter_legal_specs()
                if (s.shock_family, s.direction, s.target_stream) == (family, direction, stream)
                and s.magnitude_bin == magnitude
            )
            configs.add(compile_spec(spec))
        assert len(configs) >= 2, (
            f"{family} shows no severity response at all across LOW/MEDIUM/HIGH"
        )


def test_predictive_model_key_resolves_in_verifier_registry() -> None:
    """Joint with P4 (module 05's construction registry). Module 05 has not landed on ``main``
    yet, so this checks 04's own internal consistency today: every key the mapping can emit is
    drawn from the grid's own registered key set, never an ad hoc string invented in ``mapping.py``.
    Extend this to import ``collie.verify.registry.CONSTRUCTIONS`` once 05 lands, per
    ``docs/implementation/05-verifier.md``'s "Keyed by the predictive_model value module 04
    emits."""
    from collie.control.grid import predictive_model_keys

    registered = predictive_model_keys()
    for _, config in mapping_table():
        assert config.predictive_model in registered


def test_iter_legal_specs_covers_every_family_direction_stream_combination() -> None:
    """The enumeration itself is not accidentally narrower than the schema it claims to cover."""
    from collie.contracts import Direction, TargetStream

    specs = list(iter_legal_specs())
    non_abstention = [s for s in specs if s.shock_family is not ShockFamily.NO_CHANGE]
    families = {s.shock_family for s in non_abstention}
    directions = {s.direction for s in non_abstention}
    streams = {s.target_stream for s in non_abstention}
    assert families == {f for f in ShockFamily if f is not ShockFamily.NO_CHANGE}
    assert directions == {d for d in Direction if d is not Direction.NONE}
    assert streams == {t for t in TargetStream if t is not TargetStream.NONE}


def test_abstention_is_the_only_no_change_spec() -> None:
    no_change = [s for s in iter_legal_specs() if s.shock_family is ShockFamily.NO_CHANGE]
    assert len(no_change) == 1
    assert no_change[0].is_abstention


@pytest.mark.parametrize("spec_index", range(0, 271, 17))
def test_compile_spec_is_a_shock_spec_in_control_config_out(spec_index: int) -> None:
    """Smoke-checks a stride of the legal space directly through the public type, guarding
    against a signature drift that the enumeration tests wouldn't catch on their own."""
    specs = list(iter_legal_specs())
    spec = specs[spec_index]
    assert isinstance(spec, ShockSpec)
    config = compile_spec(spec)
    assert config in set(all_configs())


# ---------------------------------------------------------------------------
# hidden-state isolation (project-wide test also covers this; this is the module-local mirror)
# ---------------------------------------------------------------------------


def test_mapping_module_never_names_hidden_state() -> None:
    hidden = {"HiddenIncident", "HiddenAlertSpec", "SupplyRealization"}
    tree = ast.parse((REPO_ROOT / "collie/control/mapping.py").read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not (names & hidden)


# ---------------------------------------------------------------------------
# GridCompiler: the SpecCompiler seam the arms actually receive
# ---------------------------------------------------------------------------


def test_grid_compiler_satisfies_the_spec_compiler_protocol() -> None:
    """Module 06's injection seam, checked structurally: the arms must never need to know which
    concrete compiler they were handed."""
    from collie.arms.protocols import SpecCompiler
    from collie.control.mapping import GridCompiler

    assert isinstance(GridCompiler(), SpecCompiler)


def test_grid_compiler_abstention_returns_current_unchanged() -> None:
    """ "Carry on as before" means exactly that: an abstention must not move whatever config is
    running, including a per-instance baseline descriptor whose ``l_eff`` is the instance's
    promised lead time rather than the grid reference point."""
    from collie.contracts import ControlConfig
    from collie.control.grid import BASELINE_CONFIG
    from collie.control.mapping import GridCompiler

    (no_change_spec,) = [s for s in iter_legal_specs() if s.is_abstention]
    current = ControlConfig(m=1.25, l_eff=4, gamma=0.5, predictive_model="probe")
    assert GridCompiler().compile(no_change_spec, current=current) is current
    # At the registered baseline point the seam agrees with compile_spec's registered answer.
    assert GridCompiler().compile(no_change_spec, current=BASELINE_CONFIG) == compile_spec(
        no_change_spec
    )


def test_grid_compiler_matches_compile_spec_at_the_registered_baseline() -> None:
    """At the grid reference point the seam's composition reduces to the static mapping: inherit
    and offset are both identities when ``current`` is ``BASELINE_CONFIG``."""
    from collie.control.grid import BASELINE_CONFIG
    from collie.control.mapping import GridCompiler

    for spec in iter_legal_specs():
        if not spec.is_abstention:
            assert GridCompiler().compile(spec, current=BASELINE_CONFIG) == compile_spec(spec)


def test_grid_compiler_demand_spec_moves_only_m() -> None:
    """A demand hypothesis must never touch the pipeline axes: ``l_eff``/``gamma`` come from the
    running config, not the reference-anchored grid point. Regression: with an absolute
    (m=1.5, l_eff=1) point applied to a promised-2 baseline, m*(1+l_eff) exactly cancels the
    demand signal and the oracle orders *less* during a demand-up shock."""
    from collie.contracts import ControlConfig, Direction, TargetStream
    from collie.control.mapping import GridCompiler

    spec = next(
        s
        for s in iter_legal_specs()
        if s.target_stream is TargetStream.DEMAND and s.direction is Direction.DEMAND_UP
    )
    current = ControlConfig(m=0.75, l_eff=4, gamma=0.5, predictive_model="probe")
    out = GridCompiler().compile(spec, current=current)
    assert out.m == compile_spec(spec).m  # the belief multiplier is absolute
    assert (out.l_eff, out.gamma) == (4, 0.5)  # the pipeline is inherited
    assert out.predictive_model == compile_spec(spec).predictive_model


def test_grid_compiler_arrival_spec_shifts_supply_axes_relative_to_current() -> None:
    """ "Lengthen the pipeline" means longer than what is running: the grid's offset from the
    reference point is added to ``current.l_eff``, and ``gamma`` scales by the grid's ratio,
    so a supply hypothesis lands on beliefs the instance does not already hold."""
    from collie.contracts import ControlConfig, Direction, TargetStream
    from collie.control.mapping import GridCompiler

    spec = next(
        s
        for s in iter_legal_specs()
        if (s.shock_family, s.direction, s.target_stream)
        == (ShockFamily.LEAD_TIME_SHIFT, Direction.ARRIVAL_DELAYED, TargetStream.ARRIVAL)
    )
    cfg = compile_spec(spec)
    current = ControlConfig(m=1.25, l_eff=2, gamma=0.5, predictive_model="probe")
    out = GridCompiler().compile(spec, current=current)
    assert out.m == 1.25  # the demand axis is inherited
    assert out.l_eff == 2 + (cfg.l_eff - 1)  # offset from the reference point
    assert out.gamma == 0.5 * cfg.gamma  # distrust compounds
    assert out.predictive_model == cfg.predictive_model


def test_grid_compiler_compound_spec_takes_m_absolute_and_supply_relative() -> None:
    from collie.contracts import ControlConfig, Direction, TargetStream
    from collie.control.mapping import GridCompiler

    spec = next(
        s
        for s in iter_legal_specs()
        if (s.shock_family, s.direction, s.target_stream)
        == (ShockFamily.COMPOUND, Direction.MIXED, TargetStream.BOTH)
    )
    cfg = compile_spec(spec)
    current = ControlConfig(m=0.6, l_eff=3, gamma=0.5, predictive_model="probe")
    out = GridCompiler().compile(spec, current=current)
    assert out.m == cfg.m
    assert out.l_eff == 3 + (cfg.l_eff - 1)
    assert out.gamma == 0.5 * cfg.gamma
