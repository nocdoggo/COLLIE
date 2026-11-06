"""Outcome-free planning proxies for one primary role-study pair per seed.

This exact multinomial calculation uses a conservative 0.025 first-step
threshold for a two-test family. It is not the joint power of Holm's procedure
and does not account for wording-family dependence or interactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, fsum, isfinite
from numbers import Real

from .role_analysis import _mcnemar


@dataclass(frozen=True, slots=True)
class PlanningScenario:
    independent_seeds: int
    discordance: float
    error_excess: float

    def __post_init__(self) -> None:
        if type(self.independent_seeds) is not int or self.independent_seeds <= 0:
            raise ValueError("independent_seeds must be a positive integer")
        for value in (self.discordance, self.error_excess):
            if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
                raise ValueError("scenario probabilities must be finite real numbers")
        if not 0 <= self.discordance <= 1 or abs(self.error_excess) > self.discordance:
            raise ValueError("excess and discordance imply invalid paired probabilities")


def planning_power(scenario: PlanningScenario) -> float:
    """Probability the exact two-sided paired test has p < 0.025."""
    if not isinstance(scenario, PlanningScenario):
        raise TypeError("scenario must be a PlanningScenario")
    n = scenario.independent_seeds
    a = (scenario.discordance + scenario.error_excess) / 2
    b = (scenario.discordance - scenario.error_excess) / 2
    c = 1 - scenario.discordance
    terms = []
    for competitor_only in range(n + 1):
        for neutral_only in range(n - competitor_only + 1):
            if _mcnemar(competitor_only, neutral_only) < .025:
                neither = n - competitor_only - neutral_only
                terms.append(comb(n, competitor_only) * comb(n - competitor_only, neutral_only)
                             * a ** competitor_only * b ** neutral_only * c ** neither)
    return fsum(terms)


def predefined_grid() -> tuple[tuple[PlanningScenario, float], ...]:
    """Both predefined package sizes and all stated discordance scenarios."""
    scenarios = (PlanningScenario(n, discordance, excess)
                 for n in (50, 80) for discordance in (.3, .5) for excess in (.1, .15, .2))
    return tuple((scenario, planning_power(scenario)) for scenario in scenarios)
