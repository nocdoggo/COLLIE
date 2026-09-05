"""Shock-family generators: baseline process, demand families, supply families."""

from __future__ import annotations

from collie.data.families import demand, supply
from collie.data.families.base import FamilyParams, GeneratedEpisode

__all__ = ["demand", "generate_episode", "supply"]


def generate_episode(*, seed: int, horizon: int, params: FamilyParams) -> GeneratedEpisode:
    """Dispatch to the family module. Families 1-3 perturb demand, 4-6 perturb supply.

    ``FamilyParams`` already constrains the number to 1-6, and ``supply.generate`` validates
    its own range, so the dispatch needs no third branch.
    """
    if params.family in demand.DEMAND_FAMILIES:
        return demand.generate(seed=seed, horizon=horizon, params=params)
    return supply.generate(seed=seed, horizon=horizon, params=params)
