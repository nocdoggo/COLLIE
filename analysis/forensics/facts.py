"""Record-level facts behind the forensics. Exploratory; reads stored artefacts only.

Run: ``uv run python -m analysis.forensics.facts`` (writes ``analysis/forensics/out/facts.json``).

Each check is an assertion about the stored pilot records, not a re-run of the pilot. The frozen
evaluator's own functions are imported for the reproduction step so the starting point is the
registered computation, bit for bit.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from analysis.forensics.common import (
    ARM1,
    ARM8,
    ARM10,
    CTRL,
    FAMILY_KEY,
    ORACLE,
    RECORDS,
    TRUTH,
    cluster_bootstrap,
    episode_frame,
    load_raw,
    load_truth,
    normal_interval,
    paired,
    periods_by,
    wilson_interval,
    write_json,
)
from collie.eval.intervals import paired_interval, stratum_weighted_paired_interval
from collie.eval.operational import cvar10, time_to_recovery
from collie.eval.pilot import (
    _headroom_count_from_values,
    _headroom_family_values,
    _headroom_interval,
    _relative_lift,
)
from collie.eval.prereg import load_preregistration, primary_stratum_weights
from collie.eval.records import load_episode_results_jsonl
from collie.eval.truth import load_episode_truth_jsonl, truth_by_episode

_FIELDS = ("order_quantity", "arrivals", "units_sold", "on_hand_end", "period_profit")


def _signature(periods: list[dict]) -> tuple:
    return tuple(tuple(p[f] for f in _FIELDS) for p in periods)


def reproduce_registered() -> dict:
    """The two fired triggers, recomputed with the frozen evaluator's own functions."""
    results = load_episode_results_jsonl(RECORDS)
    truths = truth_by_episode(load_episode_truth_jsonl(TRUTH))
    values = _headroom_family_values(results, truths)
    per_key = {
        key: {
            "n_rows": len(oracle),
            "arm1_mean": float(np.mean(base)),
            "oracle_mean": float(np.mean(oracle)),
            "raw_lift": _relative_lift(float(np.mean(oracle)), float(np.mean(base))),
            "cvar10_lift": _relative_lift(cvar10(tuple(oracle)), cvar10(tuple(base))),
        }
        for key, (oracle, base) in values.items()
    }
    detector = paired_interval(
        results,
        treatment=ARM10,
        control=CTRL,
        endpoint="cumulative_undiscounted_profit",
    )
    weights = primary_stratum_weights(load_preregistration(require_final=True).data)
    return {
        "headroom_count": _headroom_count_from_values(values),
        "headroom_interval": list(_headroom_interval(results, truths=truths)),
        "headroom_per_key": per_key,
        "detector_estimate": detector.estimate,
        "detector_interval": [detector.ci_low, detector.ci_high],
        "detector_n_units": detector.n_units,
        # The two registered primary endpoints on the same contrast, for the collinearity check
        # (profit_lift == p x lost_sales_reduction): the go criteria exactly as the frozen
        # evaluator computes them (registered stratum weights), and unweighted.
        "profit_lift_registered": stratum_weighted_paired_interval(
            results,
            treatment=ARM10,
            control=ARM1,
            endpoint="cumulative_undiscounted_profit",
            weights=weights,
        ).estimate,
        "lost_sales_reduction_registered": stratum_weighted_paired_interval(
            results,
            treatment=ARM1,
            control=ARM10,
            endpoint="total_lost_sales_units",
            weights=weights,
        ).estimate,
        "profit_lift_unweighted": paired_interval(
            results,
            treatment=ARM10,
            control=ARM1,
            endpoint="cumulative_undiscounted_profit",
        ).estimate,
        "lost_sales_reduction_unweighted": -paired_interval(
            results,
            treatment=ARM10,
            control=ARM1,
            endpoint="total_lost_sales_units",
        ).estimate,
    }


def collinearity(raw: list[dict]) -> dict:
    """Gross profit is p x (demand - lost sales) per episode; demand is exogenous across arms.

    If both hold, every paired profit difference is exactly -p times the paired lost-sales
    difference, so the two registered primary endpoints carry the same information.
    """
    profit_rates: set[float] = set()
    holding_rates: set[float] = set()
    violations = 0
    demand_by_episode: dict[str, set[float]] = defaultdict(set)
    for record in raw:
        own_rates = {
            p["period_profit"] / p["units_sold"] for p in record["records"] if p["units_sold"] > 0
        }
        profit_rates |= own_rates
        holding_rates |= {
            p["period_holding"] / p["on_hand_end"]
            for p in record["records"]
            if p["on_hand_end"] > 0
        }
        if len(own_rates) != 1:
            violations += 1
        else:
            (rate,) = own_rates
            expected = rate * (record["total_demand"] - record["total_lost_sales"])
            if record["total_profit"] != expected:
                violations += 1
        demand_by_episode[record["episode_id"]].add(record["total_demand"])
    return {
        "records_checked": len(raw),
        "profit_per_unit_values": sorted(profit_rates),
        "holding_cost_per_unit_values": sorted(holding_rates),
        "violations_of_profit_eq_p_times_sold": violations,
        "episodes_with_arm_dependent_total_demand": sum(
            1 for demands in demand_by_episode.values() if len(demands) != 1
        ),
    }


def identical_arms(periods: dict, a: str, b: str, episodes: list[str]) -> dict:
    same = [e for e in episodes if _signature(periods[(e, a)]) == _signature(periods[(e, b)])]
    return {"episodes": len(episodes), "bit_identical": len(same)}


def oracle_vs_arm1_by_family(periods: dict, frame: pd.DataFrame, truth: dict) -> dict:
    """Where the oracle's recorded outcome equals arm 1's, and where its orders differ."""
    out = {}
    shocked = frame[(frame.arm == ORACLE)]
    for fam, group in shocked.groupby("fam"):
        identical_outcomes = 0
        order_diffs_outside_window = 0
        for episode in group.episode_id:
            o, b = periods[(episode, ORACLE)], periods[(episode, ARM1)]
            outcome = [(p["arrivals"], p["units_sold"], p["on_hand_end"]) for p in o]
            if outcome == [(p["arrivals"], p["units_sold"], p["on_hand_end"]) for p in b]:
                identical_outcomes += 1
            t = truth[episode]
            for po, pb in zip(o, b, strict=True):
                inside = t["onset_period"] <= po["period"] <= t["final_shock_period"]
                if po["order_quantity"] != pb["order_quantity"] and not inside:
                    order_diffs_outside_window += 1
        out[FAMILY_KEY[int(fam)]] = {
            "episodes": len(group),
            "outcome_identical_to_arm1": identical_outcomes,
            "order_differences_outside_oracle_window": order_diffs_outside_window,
        }
    return out


def condition_replication(periods: dict, frame: pd.DataFrame) -> dict:
    """Distinct per-period trajectories among the four condition replays of each seed."""
    shocked = frame[~frame.is_null]
    out = {}
    for arm in (ARM1, ORACLE, CTRL, ARM10):
        distinct = []
        for _cluster, group in shocked[shocked.arm == arm].groupby("cluster"):
            distinct.append(len({_signature(periods[(e, arm)]) for e in group.episode_id}))
        out[arm] = {
            "clusters": len(distinct),
            "mean_distinct_trajectories_per_cluster": float(np.mean(distinct)),
            "clusters_with_one_trajectory": int(sum(d == 1 for d in distinct)),
        }
    return out


def null_duplicates(periods: dict, frame: pd.DataFrame) -> dict:
    """The 24 nulls are unshocked twins; twins depend on (family, seed) only."""
    nulls = frame[frame.is_null & (frame.arm == ARM1)]
    groups = nulls.groupby(["cluster", "condition"]).episode_id.apply(list)
    arms = sorted(frame[frame.is_null].arm.unique())
    all_identical = True
    for members in groups:
        for arm in arms:
            if len({_signature(periods[(e, arm)]) for e in members}) != 1:
                all_identical = False
    return {
        "null_episodes": len(nulls),
        "distinct_null_trajectories": len(groups),
        "distinct_seeds": int(nulls.cluster.nunique()),
        "group_sizes": {f"{c}|{cond}": len(m) for (c, cond), m in groups.items()},
        "every_arm_identical_within_group": all_identical,
    }


def recovery_construction(truth: dict) -> dict:
    """time_to_recovery with shock_period = final shock-active period, as registered."""
    results = [r for r in load_episode_results_jsonl(RECORDS) if r.arm_id == ARM10]
    by_family: dict[str, list[float]] = defaultdict(list)
    never = defaultdict(int)
    finals = defaultdict(set)
    for result in results:
        if result.episode_id not in truth:
            continue
        t = truth[result.episode_id]
        fam = FAMILY_KEY[int(result.episode_id.split("/")[1][1:])]
        finals[fam].add(t["final_shock_period"])
        value = time_to_recovery(result.records, shock_period=t["final_shock_period"])
        if value is None:
            never[fam] += 1
        by_family[fam].append(51.0 if value is None else float(value))
    flat = [v for values in by_family.values() for v in values]
    return {
        "recovery_time_mean": float(np.mean(flat)),
        "never_recovered_by_family": dict(never),
        "final_shock_periods_by_family": {k: sorted(v) for k, v in finals.items()},
        "mean_by_family": {k: float(np.mean(v)) for k, v in by_family.items()},
    }


def fill_rates(frame: pd.DataFrame) -> dict:
    return {
        arm: {
            "all_episodes": float(g.fill.mean()),
            "shocked": float(g[~g.is_null].fill.mean()),
            "null": float(g[g.is_null].fill.mean()) if g.is_null.any() else None,
            "n": len(g),
        }
        for arm, g in frame.groupby("arm")
    }


def false_activation(frame: pd.DataFrame) -> dict:
    nulls = frame[frame.is_null & (frame.arm == ARM10)]
    activated = nulls[nulls.n_active > 0]
    distinct = nulls.drop_duplicates(["cluster", "condition"])
    distinct_activated = distinct[distinct.n_active > 0]
    registered_wald = normal_interval((nulls.n_active == 0).astype(float))
    return {
        "null_episodes": len(nulls),
        "activated_null_episodes": activated.episode_id.tolist(),
        "activated_null_units": activated.unit.tolist(),
        "control_estimate": float((nulls.n_active == 0).mean()),
        "registered_style_normal_interval": list(registered_wald),
        "wilson_interval_n24": list(wilson_interval(int((nulls.n_active == 0).sum()), len(nulls))),
        "distinct_null_trajectories": len(distinct),
        "distinct_activated": len(distinct_activated),
        "wilson_interval_distinct": list(
            wilson_interval(int((distinct.n_active == 0).sum()), len(distinct))
        ),
    }


def detector_intervals(frame: pd.DataFrame) -> dict:
    out = {}
    for column in ("profit", "lost", "holding", "reward"):
        d = paired(frame, ARM10, CTRL, column)
        cluster_means = d.groupby("cluster")["diff"].mean()
        out[column] = {
            "estimate": float(d["diff"].mean()),
            "registered_style_normal_n120": list(normal_interval(d["diff"])),
            "seed_cluster_bootstrap": list(cluster_bootstrap(d["diff"], d["cluster"])),
            "seed_collapsed_normal": list(normal_interval(cluster_means)),
            "n_episodes": len(d),
            "n_seed_clusters": int(d.cluster.nunique()),
            "shocked_mean": float(d[~d.is_null]["diff"].mean()),
            "null_mean": float(d[d.is_null]["diff"].mean()),
        }
    return out


def headroom_seed_bootstrap(frame: pd.DataFrame, resamples: int = 10_000) -> dict:
    """The registered headroom count, bootstrapped over seeds rather than episode replays."""
    seed_values = {}
    for key, group in frame[~frame.is_null].groupby("key"):
        wide = group.pivot_table(index="cluster", columns="arm", values="profit", aggfunc="mean")
        seed_values[key] = (wide[ORACLE].to_numpy(), wide[ARM1].to_numpy())
    rng = np.random.default_rng(20260927)
    counts = np.empty(resamples)
    for index in range(resamples):
        draw = {}
        for key, (oracle, base) in seed_values.items():
            chosen = rng.integers(0, len(oracle), size=len(oracle))
            draw[key] = (oracle[chosen], base[chosen])
        counts[index] = _headroom_count_from_values(draw)
    per_seed_lift = {
        key: [float((o - b) / b) for o, b in zip(oracle, base, strict=True)]
        for key, (oracle, base) in seed_values.items()
    }
    return {
        "seeds_per_family": {k: len(v[0]) for k, v in seed_values.items()},
        "point_count": int(_headroom_count_from_values(seed_values)),
        "seed_bootstrap_interval": [float(np.quantile(counts, q)) for q in (0.025, 0.975)],
        "seed_bootstrap_distribution": {
            str(int(c)): float(np.mean(counts == c)) for c in np.unique(counts)
        },
        "per_seed_raw_lift": per_seed_lift,
    }


def start_of_episode(raw: list[dict]) -> dict:
    """Every episode starts with nothing on hand or in transit, for every arm alike.

    The leading run of zero-sale periods is demand no policy can serve (the first order cannot
    land before the promised lead time), so it caps every arm's fill rate identically.
    """
    initial = sorted(
        {
            (float(r["records"][0]["on_hand_start"]), float(r["records"][0]["in_transit_start"]))
            for r in raw
        }
    )
    leading: dict[int, int] = defaultdict(int)
    shares = []
    for record in raw:
        periods = record["records"]
        n = 0
        while n < len(periods) and periods[n]["units_sold"] == 0:
            n += 1
        leading[n] += 1
        demand = sum(p["demand"] for p in periods)
        shares.append(sum(p["lost_sales"] for p in periods[:n]) / demand)
    return {
        "initial_on_hand_and_in_transit": [list(pair) for pair in initial],
        "leading_zero_sale_periods": {str(k): v for k, v in sorted(leading.items())},
        "mean_share_of_demand_lost_in_leading_periods": float(np.mean(shares)),
        "records": len(raw),
    }


def main() -> None:
    raw = load_raw()
    truth = load_truth()
    frame = episode_frame(raw)
    periods = periods_by(raw, [ARM1, ARM8, ARM10, CTRL, ORACLE, *frame.arm.unique()])
    episodes = sorted(frame.episode_id.unique())

    facts = {
        "registered_reproduction": reproduce_registered(),
        "collinearity": collinearity(raw),
        "arm8_vs_ctrl": identical_arms(periods, ARM8, CTRL, episodes),
        "oracle_vs_arm1": oracle_vs_arm1_by_family(periods, frame, truth),
        "condition_replication": condition_replication(periods, frame),
        "null_duplicates": null_duplicates(periods, frame),
        "recovery_time": recovery_construction(truth),
        "fill_rates": fill_rates(frame),
        "false_activation": false_activation(frame),
        "detector_intervals": detector_intervals(frame),
        "headroom_seed_bootstrap": headroom_seed_bootstrap(frame),
        "start_of_episode": start_of_episode(raw),
        "record_counts": {
            "records": len(raw),
            "episodes": len(episodes),
            "arms_per_shocked_episode": int(
                frame[~frame.is_null].groupby("episode_id").arm.nunique().iloc[0]
            ),
            "arms_per_null_episode": int(
                frame[frame.is_null].groupby("episode_id").arm.nunique().iloc[0]
            ),
        },
    }
    path = write_json("facts.json", facts)
    import json

    print(json.dumps(facts, indent=2, sort_keys=True, default=float))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
