"""Synthetic planning-power checks, not achieved-power estimates."""

import pytest

from analysis.coling.followup.role_power import PlanningScenario, planning_power, predefined_grid


def test_simple_edge_cases_and_direction_symmetry():
    assert planning_power(PlanningScenario(1, .3, .2)) == 0
    assert planning_power(PlanningScenario(80, 0, 0)) == 0
    positive = planning_power(PlanningScenario(50, .3, .2))
    negative = planning_power(PlanningScenario(50, .3, -.2))
    assert positive == pytest.approx(negative)
    assert 0 < positive < 1


def test_full_package_large_effect_is_consistent_with_the_illustrative_proxy():
    result = planning_power(PlanningScenario(80, .3, .2))
    assert .80 < result < .90


def test_predefined_grid_includes_full_and_reduced_packages():
    grid = predefined_grid()
    assert len(grid) == 12
    assert {scenario.independent_seeds for scenario, _ in grid} == {50, 80}
    assert all(0 <= value <= 1 for _, value in grid)


@pytest.mark.parametrize("n,discordance,excess", [(0, .3, .2), (True, .3, .2), (50, .2, .3),
                                                  (50, 1.1, .1), (50, float("nan"), .1)])
def test_invalid_planning_scenarios_are_refused(n, discordance, excess):
    with pytest.raises(ValueError):
        PlanningScenario(n, discordance, excess)
