"""Module 04, Checkpoint 1 — the 72-configuration grid.

Guards `docs/implementation/04-or-compiler.md`'s grid deliverable: the grid is mechanical
(``itertools.product`` over three registered axes), and ``predictive_model`` is a pure function
of the point rather than a fourth free axis, which is what keeps the cardinality at exactly 72.
"""

from __future__ import annotations

import itertools

from collie.contracts import ControlConfig
from collie.control.grid import (
    BASELINE_CONFIG,
    GAMMA_VALUES,
    L_EFF_VALUES,
    M_VALUES,
    all_configs,
    predictive_model_for,
    predictive_model_keys,
)


def test_grid_dimensions_are_registered() -> None:
    assert len(M_VALUES) == 6
    assert len(L_EFF_VALUES) == 4
    assert len(GAMMA_VALUES) == 3
    assert len(M_VALUES) * len(L_EFF_VALUES) * len(GAMMA_VALUES) == 72


def test_grid_has_exactly_72_distinct_configs() -> None:
    configs = all_configs()
    assert len(configs) == 72
    assert len(set(configs)) == 72, "predictive_model must not turn one grid point into several"


def test_every_config_is_reachable() -> None:
    """Reachability from *some legal spec* is asserted end to end in
    ``tests/test_control_mapping.py::test_every_config_is_reachable``, since it needs the mapping.
    Here we only assert the grid's own enumeration is exactly the mechanical cross product, which
    is the half of the claim this module owns."""
    expected = {
        ControlConfig(
            m=m, l_eff=l_eff, gamma=gamma, predictive_model=predictive_model_for(m, l_eff, gamma)
        )
        for m, l_eff, gamma in itertools.product(M_VALUES, L_EFF_VALUES, GAMMA_VALUES)
    }
    assert set(all_configs()) == expected


def test_grid_enumeration_is_deterministic() -> None:
    assert all_configs() == all_configs()


def test_baseline_is_one_of_the_72() -> None:
    assert BASELINE_CONFIG in set(all_configs())
    assert BASELINE_CONFIG.predictive_model == "stationary"


def test_predictive_model_for_is_pure() -> None:
    for m, l_eff, gamma in itertools.product(M_VALUES, L_EFF_VALUES, GAMMA_VALUES):
        assert predictive_model_for(m, l_eff, gamma) == predictive_model_for(m, l_eff, gamma)


def test_predictive_model_keys_are_exactly_the_grids_image() -> None:
    assert predictive_model_keys() == {c.predictive_model for c in all_configs()}


def test_predictive_model_keys_are_nonempty_and_include_stationary() -> None:
    keys = predictive_model_keys()
    assert "stationary" in keys
    assert len(keys) > 1, "a single key for all 72 points would mean the grid carries no signal"
