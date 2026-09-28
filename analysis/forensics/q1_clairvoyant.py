"""Q1 — is the headroom trigger measuring the ceiling, the compiler, or the endpoint?

Exploratory. Run: ``uv run python -m analysis.forensics.q1_clairvoyant``.

The decisive instrument is a **mapping-free clairvoyant**: an agent that knows the episode's
entire future demand and supply realization and picks per-period orders to maximise an
objective, never going through the compiler. It is computed exactly as a linear program:

    variables  q_t (order), s_t (sales), I_t (ending inventory), t = 1..H
    maximise   sum p*s_t              (the registered endpoint: gross profit)
         or    sum p*s_t - h*sum I_t  (net of holding: the benchmark's total_reward)
    subject to I_t = I_{t-1} + sum_{tau: a(tau)=t} q_tau - s_t,   I_0 = 0
               0 <= s_t <= d_t,  I_t >= 0,  0 <= q_t <= cap_t

``a(tau)`` is the period an order placed at ``tau`` lands, read by probing the *frozen*
``collie.sim.supply.LeadTimeSupply`` (so lead-time shifts, lost shipments, and transit pauses
follow the audited physics, not a re-derivation). The constraint matrix is a network matrix,
so with integer data every vertex is integral. Each optimal plan is then **replayed through the
frozen ``EpisodeRunner``** and must score exactly the LP value: greedy selling (the runner's
rule) weakly dominates any sales plan for a fixed arrival stream, and the runner's path is
LP-feasible, so equality holds iff the arrival map and dynamics are modelled correctly. The
LP value is therefore an upper bound that is also achieved.

Bounds are computed in two anchorings and two order envelopes:

* ``onset``-anchored: orders before the true onset are fixed to arm 1's (nobody observes onset
  in advance; the oracle also acts from onset). ``start``: clairvoyant from period 1.
* ``capped``: each order is bounded by the published smoother ``ceil(mean + z_0.95*std)`` that
  every OR-compiler arm and arm 1 apply (``collie/control/controller.py``). Demand is exogenous
  and uncensored, so this cap sequence is identical for every policy on an episode.
  ``uncapped``: the pilot's registered ``EpisodeSpec.order_cap`` is ``inf``.

Clairvoyance also buys *noise* foresight that no hypothesis can convey. So every bound is also
computed on the episode's unshocked **twin** at the same anchor period; the difference in
differences isolates what the *shock itself* makes exploitable.
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix
from scipy.stats import norm

from analysis.forensics.common import (
    ARM1,
    FAMILY_KEY,
    ORACLE,
    load_raw,
    parse_episode_id,
    periods_by,
    write_json,
)
from analysis.forensics.harness import (
    PlanController,
    build_arm,
    pilot_contexts,
    run,
    same_as_stored,
    twin_instance,
)
from collie.sim.loader import LoadedInstance
from collie.sim.supply import LeadTimeSupply

Z95 = float(norm.ppf(0.95))


def arrival_map(instance: LoadedInstance) -> list[int | None]:
    """Landing period of a unit ordered at each period, by probing the frozen supply physics."""
    horizon = instance.spec.horizon
    landing: list[int | None] = []
    for t in range(1, horizon + 1):
        supply = LeadTimeSupply(realization=instance.supply)
        landed = None
        for u in range(1, horizon + 1):
            supply.dispatch(u, 1.0 if u == t else 0.0)
            if supply.receive(u) > 0.0 and landed is None:
                landed = u
        landing.append(landed)
    return landing


def smoother_caps(instance: LoadedInstance) -> list[int]:
    """The published smoother each OR-compiler arm and arm 1 apply, period by period."""
    train = list(instance.spec.train_demand)
    caps = []
    for t in range(1, instance.spec.horizon + 1):
        samples = train + list(instance.demand[: t - 1])
        mean = float(np.mean(samples))
        std = float(np.std(samples, ddof=1)) if len(samples) > 1 else 0.0
        caps.append(max(math.ceil(mean + Z95 * std), 0))
    return caps


def clairvoyant(
    instance: LoadedInstance,
    *,
    objective: str,
    capped: bool,
    prefix: dict[int, float],
    landing: list[int | None],
    caps: list[int],
) -> tuple[float, tuple[float, ...]]:
    """Exact optimum and its order plan. ``prefix`` fixes orders (period -> quantity)."""
    horizon = instance.spec.horizon
    p = float(instance.profits[0])
    h = float(instance.holding_costs[0])
    demand = [float(v) for v in instance.demand]
    big = float(sum(demand)) + 1.0
    n = 3 * horizon  # q | s | I
    cost = np.zeros(n)
    cost[horizon : 2 * horizon] = -p
    if objective == "net":
        cost[2 * horizon :] = h
    elif objective != "gross":
        raise ValueError(objective)
    a_eq = lil_matrix((horizon, n))
    for u in range(horizon):
        a_eq[u, horizon + u] = 1.0  # + s_u
        a_eq[u, 2 * horizon + u] = 1.0  # + I_u
        if u > 0:
            a_eq[u, 2 * horizon + u - 1] = -1.0  # - I_{u-1}
    for t, lands in enumerate(landing, start=1):
        if lands is not None:
            a_eq[lands - 1, t - 1] = -1.0  # - q_t lands at `lands`
    bounds = []
    for t in range(1, horizon + 1):
        if t in prefix:
            bounds.append((prefix[t], prefix[t]))
        elif landing[t - 1] is None:
            bounds.append((0.0, 0.0))  # lost or lands after the horizon: irrelevant, set to 0
        else:
            bounds.append((0.0, float(caps[t - 1]) if capped else big))
    bounds += [(0.0, d) for d in demand]
    bounds += [(0.0, None)] * horizon
    res = linprog(cost, A_eq=a_eq.tocsr(), b_eq=np.zeros(horizon), bounds=bounds, method="highs")
    if res.status != 0:
        raise RuntimeError(f"{instance.spec.episode_id}: LP failed: {res.message}")
    orders = res.x[:horizon]
    rounded = np.round(orders)
    if np.max(np.abs(orders - rounded)) > 1e-6:
        raise RuntimeError(f"{instance.spec.episode_id}: non-integral LP vertex")
    return float(-res.fun), tuple(float(v) for v in rounded)


def replay(instance: LoadedInstance, plan: tuple[float, ...]):
    return run(PlanController(plan=plan), instance, None, isolation=False).result


def _score(result, objective: str) -> float:
    return float(result.total_profit if objective == "gross" else result.total_reward)


ANCHORS = ("onset", "early1", "early2", "start")
"""When the clairvoyant starts acting: at onset (the oracle's own knowledge time), one and two
periods before onset (the early-accurate alert arrives at onset-1), or from period 1."""


def anchor_period(name: str, onset: int) -> int:
    return {"onset": onset, "early1": onset - 1, "early2": onset - 2, "start": 1}[name]


def bounds_for(instance: LoadedInstance, arm1_orders: tuple[float, ...], onset: int) -> dict:
    """All clairvoyant variants plus the information-free max-stock policy, replay-verified."""
    landing = arrival_map(instance)
    caps = smoother_caps(instance)
    out: dict[str, dict] = {}
    for anchor_name in ANCHORS:
        start = anchor_period(anchor_name, onset)
        prefix = {t: arm1_orders[t - 1] for t in range(1, start)}
        for capped in (True, False):
            for objective in ("gross", "net"):
                value, plan = clairvoyant(
                    instance,
                    objective=objective,
                    capped=capped,
                    prefix=prefix,
                    landing=landing,
                    caps=caps,
                )
                result = replay(instance, plan)
                achieved = _score(result, objective)
                if abs(achieved - value) > 1e-6:
                    raise AssertionError(
                        f"{instance.spec.episode_id} {anchor_name}/{capped}/{objective}: LP "
                        f"{value} but frozen runner scored {achieved}"
                    )
                name = f"clv_{objective}_{'cap' if capped else 'uncap'}_{anchor_name}"
                out[name] = outcome(result)
        # Information-free: order the smoother cap every period from the anchor on.
        plan = tuple(
            arm1_orders[t - 1] if t < start else float(caps[t - 1])
            for t in range(1, instance.spec.horizon + 1)
        )
        out[f"maxstock_{anchor_name}"] = outcome(replay(instance, plan))
        # Sales are monotone in orders in a lost-sales system with exogenous arrivals, so under
        # the gross endpoint the information-free max-stock plan must attain the capped optimum.
        if out[f"maxstock_{anchor_name}"]["gross"] != out[f"clv_gross_cap_{anchor_name}"]["gross"]:
            raise AssertionError(
                f"{instance.spec.episode_id} {anchor_name}: max-stock gross "
                f"{out[f'maxstock_{anchor_name}']['gross']} != capped clairvoyant gross "
                f"{out[f'clv_gross_cap_{anchor_name}']['gross']}"
            )
    return out


def outcome(result) -> dict:
    return {
        "gross": float(result.total_profit),
        "net": float(result.total_reward),
        "lost": float(result.total_lost_sales),
        "holding": float(result.total_holding_cost),
        "fill": float(result.fill_rate),
    }


def _cap_binding(orders: list[float], caps: list[int], start: int) -> float:
    window = [(o, c) for t, (o, c) in enumerate(zip(orders, caps, strict=True), 1) if t >= start]
    return float(np.mean([o >= c for o, c in window])) if window else float("nan")


def main() -> None:
    raw = load_raw()
    stored = periods_by(raw, [ARM1, ORACLE])
    per_seed = []
    verified = {"arm1_shocked": 0, "oracle_shocked": 0, "arm1_twin_vs_null_records": 0}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contexts = pilot_contexts(root)
        # The pilot's environment-side order cap, as the frozen loader materialised it.
        verified["episodes_with_infinite_order_cap"] = sum(
            1 for c in contexts if math.isinf(c.instance.spec.order_cap)
        )
        verified["episodes_total"] = len(contexts)
        shocked = [c for c in contexts if c.instance.incident is not None]
        seen_clusters = set()
        for ctx in shocked:
            instance = ctx.instance
            episode_id = ctx.episode_id
            # Bit-for-bit reproduction of arm 1 and the oracle on EVERY shocked episode.
            arm1, iso = build_arm(ARM1, ctx)
            arm1_result = run(arm1, instance, ctx, isolation=iso).result
            if not same_as_stored(arm1_result, stored[(episode_id, ARM1)]):
                raise AssertionError(f"arm 1 does not reproduce on {episode_id}")
            verified["arm1_shocked"] += 1
            oracle, iso = build_arm(ORACLE, ctx)
            oracle_result = run(oracle, instance, ctx, isolation=iso).result
            if not same_as_stored(oracle_result, stored[(episode_id, ORACLE)]):
                raise AssertionError(f"oracle does not reproduce on {episode_id}")
            verified["oracle_shocked"] += 1

            meta = parse_episode_id(episode_id)
            if meta["cluster"] in seen_clusters:
                continue  # arm 1, the oracle, and every bound ignore alerts: one per seed
            seen_clusters.add(meta["cluster"])
            incident = instance.incident
            onset = incident.onset_period
            arm1_orders = tuple(r.order_quantity for r in arm1_result.records)

            twin = twin_instance(root, instance)
            twin_arm1 = run(build_arm(ARM1, ctx)[0], twin, None, isolation=True).result
            twin_orders = tuple(r.order_quantity for r in twin_arm1.records)
            if twin_orders[: onset - 1] != arm1_orders[: onset - 1]:
                raise AssertionError(f"{episode_id}: pre-onset orders differ from the twin's")
            null_key = next(
                (k for k in stored if k[0] == twin.spec.episode_id and k[1] == ARM1), None
            )
            if null_key is not None and same_as_stored(twin_arm1, stored[null_key]):
                verified["arm1_twin_vs_null_records"] += 1

            caps = smoother_caps(instance)
            landing = arrival_map(instance)
            oracle_cfgs = {
                (r.control_config.m, r.control_config.l_eff, r.control_config.gamma)
                for r in oracle_result.records
                if r.active_spec_id is not None
            }
            oracle_window = [r.period for r in oracle_result.records if r.active_spec_id]
            effect = incident.supply_effect
            per_seed.append(
                {
                    "cluster": meta["cluster"],
                    "key": FAMILY_KEY[int(meta["fam"])],
                    "promised_lead_time": instance.spec.promised_lead_time,
                    "onset": onset,
                    "magnitude": incident.magnitude,
                    "duration": incident.duration,
                    "supply_effect": None
                    if effect is None
                    else {
                        "kind": str(effect.kind),
                        "start": effect.start_period,
                        "length": effect.length,
                        "disrupted_lead_time": effect.disrupted_lead_time,
                    },
                    "oracle_compiled_configs": sorted(oracle_cfgs),
                    "oracle_window": [min(oracle_window), max(oracle_window)]
                    if oracle_window
                    else None,
                    "oracle_window_orders_landed": int(
                        sum(
                            1
                            for r in oracle_result.records
                            if r.active_spec_id and landing[r.period - 1] is not None
                        )
                    ),
                    "oracle_window_periods": len(oracle_window),
                    "cap_binding_post_onset": {
                        "arm1": _cap_binding(list(arm1_orders), caps, onset),
                        "oracle": _cap_binding(
                            [r.order_quantity for r in oracle_result.records], caps, onset
                        ),
                    },
                    "arm1": outcome(arm1_result),
                    "oracle": outcome(oracle_result),
                    "shocked": bounds_for(instance, arm1_orders, onset),
                    "twin_arm1": outcome(twin_arm1),
                    "twin": bounds_for(twin, twin_orders, onset),
                }
            )

    summary = summarise(per_seed)
    path = write_json(
        "q1_clairvoyant.json",
        {"verified_reproduction": verified, "per_family": summary, "per_seed": per_seed},
    )
    print(json.dumps({"verified_reproduction": verified, "per_family": summary}, indent=2))
    print(f"\nwrote {path}")


def _registered_rule(bound: list[float], base: list[float]) -> dict:
    """The registered headroom test applied to any bound: raw lift >= 5% or CVaR10 lift >= 10%.

    CVaR10 is taken with the frozen ``cvar10`` over the registered 16-row shape (each seed's
    value replicated across its four condition replays, exactly as the stored records are), so
    the number is the one the frozen evaluator would print for this bound.
    """
    from collie.eval.operational import cvar10
    from collie.eval.pilot import HEADROOM_CVAR10_LIFT, HEADROOM_RAW_PROFIT_LIFT, _relative_lift

    b16 = tuple(v for v in bound for _ in range(4))
    a16 = tuple(v for v in base for _ in range(4))
    raw = _relative_lift(float(np.mean(b16)), float(np.mean(a16)))
    cvar = _relative_lift(cvar10(b16), cvar10(a16))
    return {
        "raw_lift_pct": 100.0 * raw,
        "cvar10_lift_pct": 100.0 * cvar,
        "passes": bool(raw >= HEADROOM_RAW_PROFIT_LIFT or cvar >= HEADROOM_CVAR10_LIFT),
    }


def summarise(per_seed: list[dict]) -> dict:
    """Family means over seeds (one row per independent unit), lifts relative to arm 1."""
    out: dict[str, object] = {}
    keys = [FAMILY_KEY[f] for f in sorted(FAMILY_KEY)]
    bound_names = sorted(per_seed[0]["shocked"])
    for key in keys:
        rows = [r for r in per_seed if r["key"] == key]
        fam: dict[str, object] = {"n_seeds": len(rows)}
        for objective in ("gross", "net"):
            base_values = [r["arm1"][objective] for r in rows]
            base = float(np.mean(base_values))
            twin_base = float(np.mean([r["twin_arm1"][objective] for r in rows]))
            block: dict[str, object] = {
                "arm1": base,
                "oracle": float(np.mean([r["oracle"][objective] for r in rows])),
                "oracle_rule": _registered_rule(
                    [r["oracle"][objective] for r in rows], base_values
                ),
            }
            block["oracle_lift_pct"] = 100.0 * (block["oracle"] - base) / abs(base)
            for name in bound_names:
                values = [r["shocked"][name][objective] for r in rows]
                value = float(np.mean(values))
                twin_value = float(np.mean([r["twin"][name][objective] for r in rows]))
                block[name] = value
                block[f"{name}_lift_pct"] = 100.0 * (value - base) / abs(base)
                block[f"{name}_rule"] = _registered_rule(values, base_values)
                block[f"{name}_twin_gain"] = twin_value - twin_base
                block[f"{name}_shock_attributable"] = (value - base) - (twin_value - twin_base)
                block[f"{name}_shock_attributable_pct"] = (
                    100.0 * ((value - base) - (twin_value - twin_base)) / abs(base)
                )
            fam[objective] = block
        fam["oracle_compiled_configs"] = sorted(
            {tuple(c) for r in rows for c in r["oracle_compiled_configs"]}
        )
        fam["cap_binding_post_onset"] = {
            arm: float(np.mean([r["cap_binding_post_onset"][arm] for r in rows]))
            for arm in ("arm1", "oracle")
        }
        fam["oracle_window_orders_landed"] = [r["oracle_window_orders_landed"] for r in rows]
        fam["oracle_window_periods"] = [r["oracle_window_periods"] for r in rows]
        fam["fill"] = {
            name: float(np.mean([r["shocked"][name]["fill"] for r in rows])) for name in bound_names
        } | {
            "arm1": float(np.mean([r["arm1"]["fill"] for r in rows])),
            "oracle": float(np.mean([r["oracle"]["fill"] for r in rows])),
        }
        fam["parameters"] = [
            {
                "cluster": r["cluster"],
                "promised_lead_time": r["promised_lead_time"],
                "onset": r["onset"],
                "magnitude": r["magnitude"],
                "duration": r["duration"],
                "supply_effect": r["supply_effect"],
            }
            for r in rows
        ]
        out[key] = fam
    counts: dict[str, dict[str, int]] = {}
    for objective in ("gross", "net"):
        counts[objective] = {
            "oracle": sum(out[k][objective]["oracle_rule"]["passes"] for k in keys)
        }
        for name in bound_names:
            counts[objective][name] = sum(out[k][objective][f"{name}_rule"]["passes"] for k in keys)
    out["families_passing_registered_rule"] = counts
    return out


if __name__ == "__main__":
    main()
