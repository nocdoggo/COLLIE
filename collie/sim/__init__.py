"""Branch A (P1). Episode runner, accounting, supply processes, observation models.

The runner executes the audited event order and knows nothing about which arm it is running.
``docs/env_contract.md`` is the authoritative statement of the semantics reproduced here.
"""

from collie.sim.accounting import (
    PeriodAccounting,
    aggregate_episode,
    clamp_order,
    settle_period,
)
from collie.sim.loader import LoadedInstance, load_instance, promised_lead_time_for
from collie.sim.observation import PriorPeriod, build_observation
from collie.sim.runner import EpisodeOutcome, EpisodeRunner
from collie.sim.supply import ArrivalKeyedSupply, Cohort, LeadTimeSupply

__all__ = [
    "ArrivalKeyedSupply",
    "Cohort",
    "EpisodeOutcome",
    "EpisodeRunner",
    "LeadTimeSupply",
    "LoadedInstance",
    "PeriodAccounting",
    "PriorPeriod",
    "aggregate_episode",
    "build_observation",
    "clamp_order",
    "load_instance",
    "promised_lead_time_for",
    "settle_period",
]
