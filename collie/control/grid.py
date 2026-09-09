"""The 72-configuration grid: every :class:`~collie.contracts.ControlConfig` the compiler
can emit.

Six demand multipliers, four effective lead times, three pipeline-credit weights:
``6 * 4 * 3 = 72``. The grid is mechanical and knows nothing about ``ShockSpec`` — it is
``mapping.py``'s job to pick a point on it. That separation is what lets this module be
verified in complete isolation: enumerate the 72 points, and check they are distinct.

``predictive_model`` is not a fourth free axis. It is a **pure function of the other three**
(:func:`predictive_model_for`), so the set of :class:`ControlConfig` objects this module
produces has exactly 72 elements rather than ``72 * len(keys)``. The categories fall out of
comparing ``(m, l_eff, gamma)`` against the baseline point rather than being hand-assigned,
which is what keeps this module honest about not encoding per-family knowledge that belongs in
``mapping.py``.
"""

from __future__ import annotations

import itertools
from typing import Any

from collie.contracts import ControlConfig

__all__ = [
    "BASELINE_CONFIG",
    "BASELINE_GAMMA",
    "BASELINE_L_EFF",
    "BASELINE_M",
    "BASELINE_PREDICTIVE_MODEL",
    "GAMMA_VALUES",
    "L_EFF_VALUES",
    "M_VALUES",
    "all_configs",
    "predictive_model_for",
    "predictive_model_keys",
]

M_VALUES: tuple[float, ...] = (0.6, 0.75, 1.0, 1.25, 1.5, 2.0)
"""Demand multiplier. 6 values."""

L_EFF_VALUES: tuple[int, ...] = (1, 2, 3, 4)
"""Compiled effective lead time. 4 values. Deliberately never the episode's actual promised
lead time (``docs/env_contract.md`` §4): the compiler is a pure function of the spec alone and
has no episode in front of it (see ``mapping.py``), so this is a belief, not an observation."""

GAMMA_VALUES: tuple[float, ...] = (0.0, 0.5, 1.0)
"""Pipeline-credit weight applied to in-transit inventory. 3 values."""

# The neutral point. Absent any registered evidence about the supply side, the compiler assumes
# the least cautious posture the grid allows (fastest lead time, full pipeline trust) rather than
# a "typical" one, because the compiler never sees which of the benchmark's three promised lead
# times is actually in force. Assuming caution that turns out to be unwarranted is exactly the
# overordering the mapping must not smuggle in for `no_change`.
BASELINE_M = 1.0
BASELINE_L_EFF = 1
BASELINE_GAMMA = 1.0
BASELINE_PREDICTIVE_MODEL = "stationary"


def predictive_model_for(m: float, l_eff: int, gamma: float) -> str:
    """The verifier-construction key for one grid point, derived from the point alone.

    Two flags, each computed against the baseline: whether the compiled belief moves demand, and
    whether it moves the supply side (and how). Their cross product is the full registered key
    space. Module 05's construction registry resolves every key this produces
    (``test_predictive_model_key_resolves_in_verifier_registry``, joint with P4).
    """
    if m == BASELINE_M:
        demand = "neutral"
    elif m > BASELINE_M:
        demand = "demand_up"
    else:
        demand = "demand_down"

    if l_eff == BASELINE_L_EFF and gamma == BASELINE_GAMMA:
        supply = "neutral"
    elif l_eff > BASELINE_L_EFF and gamma == BASELINE_GAMMA:
        supply = "lead_time_delay"
    elif l_eff == BASELINE_L_EFF and gamma < BASELINE_GAMMA:
        supply = "shipment_loss"
    else:
        supply = "transit_stall"

    if demand == "neutral" and supply == "neutral":
        return BASELINE_PREDICTIVE_MODEL
    if demand == "neutral":
        return supply
    if supply == "neutral":
        return demand
    return f"compound_{demand}_{supply}"


def all_configs() -> tuple[ControlConfig, ...]:
    """Every one of the 72 configurations, in a fixed deterministic order."""
    return tuple(
        ControlConfig(
            m=m, l_eff=l_eff, gamma=gamma, predictive_model=predictive_model_for(m, l_eff, gamma)
        )
        for m, l_eff, gamma in itertools.product(M_VALUES, L_EFF_VALUES, GAMMA_VALUES)
    )


def predictive_model_keys() -> frozenset[str]:
    """Every key reachable from the grid. Module 05 must resolve all of them, and no more may
    exist than the grid can produce (the second half of the joint invariant in 05's doc)."""
    return frozenset(c.predictive_model for c in all_configs())


BASELINE_CONFIG = ControlConfig(
    m=BASELINE_M,
    l_eff=BASELINE_L_EFF,
    gamma=BASELINE_GAMMA,
    predictive_model=BASELINE_PREDICTIVE_MODEL,
)


def _print_table() -> None:  # pragma: no cover - CLI only
    configs = all_configs()
    print(f"{'m':>5}  {'l_eff':>5}  {'gamma':>5}  predictive_model")
    for c in configs:
        print(f"{c.m:>5}  {c.l_eff:>5}  {c.gamma:>5}  {c.predictive_model}")
    print(
        f"\n{len(configs)} configs, {len(set(configs))} distinct, "
        f"{len(predictive_model_keys())} predictive_model keys"
    )


def _loaded_instance_from_fixture(fx: Any) -> Any:  # pragma: no cover - CLI only
    """Adapt a fixture episode into a ``LoadedInstance`` for the demo scripts below.

    Fixture episodes carry one scalar profit/holding pair on ``spec`` rather than the per-period
    columns ``LoadedInstance`` expects, so this repeats them across the horizon; every shipped
    instance does the same thing in practice (``docs/env_contract.md`` §8.2).
    """
    from collie.sim.loader import LoadedInstance

    spec = fx.spec
    horizon = spec.horizon
    return LoadedInstance(
        spec=spec,
        demand=fx.demand,
        supply=fx.supply,
        profits=(spec.profit_per_unit,) * horizon,
        holding_costs=(spec.holding_cost_per_unit,) * horizon,
        dates=tuple(f"t{i}" for i in range(1, horizon + 1)),
        incident=fx.incident,
    )


def _regret_sweep(family_name: str, *, seeds: int = 6) -> None:  # pragma: no cover - CLI only
    """Run every one of the 72 configs against several seeds of one family's fixture episode and
    report which region of the grid the family actually rewards. Registered as exploratory: it
    informs the Checkpoint 2 audit, not a paper claim."""
    from collie.contracts import ShockFamily
    from collie.control.controller import OrCompilerController
    from collie.fakes import fixture_episode
    from collie.sim.runner import EpisodeRunner

    family = ShockFamily(family_name)
    instances = [
        _loaded_instance_from_fixture(fixture_episode(family, seed=seed)) for seed in range(seeds)
    ]

    scored: list[tuple[float, ControlConfig]] = []
    for config in all_configs():
        rewards = []
        for inst in instances:
            controller = OrCompilerController(order_cap=inst.spec.order_cap, config=config)
            outcome = EpisodeRunner(instance=inst, strict_isolation=True).run(controller)
            rewards.append(outcome.result.total_reward)
        scored.append((sum(rewards) / len(rewards), config))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    print(f"regret sweep: family={family.value}, seeds={seeds}, {len(scored)} configs")
    print(f"\n{'rank':>4}  {'mean_reward':>12}  m  l_eff  gamma  predictive_model")
    for rank, (reward, c) in enumerate(scored[:5], start=1):
        print(f"{rank:>4}  {reward:>12.2f}  {c.m}  {c.l_eff}  {c.gamma}  {c.predictive_model}")
    print("  ...")
    for rank, (reward, c) in enumerate(scored[-5:], start=len(scored) - 4):
        print(f"{rank:>4}  {reward:>12.2f}  {c.m}  {c.l_eff}  {c.gamma}  {c.predictive_model}")


def _oracle_headroom(*, seeds_per_family: int = 3) -> None:  # pragma: no cover - CLI only
    """The oracle-ShockSpec arm against stationary OR on the fixture's dev episodes.

    6 families * 3 seeds = 18 episodes, matching the Checkpoint 2 pass criterion. This is the
    headroom number: if the oracle barely beats stationary OR here, the shocks module 01
    generates are too mild for anything downstream to detect."""
    from collie.arms.oracle import oracle_controller_for
    from collie.contracts import ShockFamily
    from collie.control.controller import OrCompilerController
    from collie.fakes import fixture_episode
    from collie.sim.runner import EpisodeRunner

    families = [f for f in ShockFamily if f is not ShockFamily.NO_CHANGE]
    oracle_total = 0.0
    stationary_total = 0.0
    n = 0
    for family in families:
        for seed in range(seeds_per_family):
            inst = _loaded_instance_from_fixture(fixture_episode(family, seed=seed))
            oracle = oracle_controller_for(inst.incident, order_cap=inst.spec.order_cap)
            stationary = OrCompilerController(order_cap=inst.spec.order_cap, config=BASELINE_CONFIG)
            oracle_reward = EpisodeRunner(instance=inst).run(oracle).result.total_reward
            stationary_reward = EpisodeRunner(instance=inst).run(stationary).result.total_reward
            oracle_total += oracle_reward
            stationary_total += stationary_reward
            n += 1

    print(
        f"oracle-ShockSpec headroom over stationary OR, {n} dev episodes ({len(families)} "
        f"families x {seeds_per_family} seeds)"
    )
    print(f"  oracle mean reward:      {oracle_total / n:.2f}")
    print(f"  stationary mean reward:  {stationary_total / n:.2f}")
    print(f"  gap:                     {(oracle_total - stationary_total) / n:.2f}")


if __name__ == "__main__":  # pragma: no cover - CLI only
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--print-table", action="store_true")
    parser.add_argument("--regret-sweep", action="store_true")
    parser.add_argument("--family", default=None)
    parser.add_argument("--oracle-headroom", action="store_true")
    args = parser.parse_args()

    if args.regret_sweep:
        if not args.family:
            parser.error("--regret-sweep requires --family")
        _regret_sweep(args.family)
    elif args.oracle_headroom:
        _oracle_headroom()
    else:
        _print_table()
