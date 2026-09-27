"""Q3 — the detection asymmetry, measured from the pilot itself. Exploratory.

Run: ``uv run python -m analysis.forensics.q3_detection``.

Three measurements, none of which implements a new detector:

1. **Firing table.** Every permitted firing of the shared wrapped trigger is an arm-10 proposal
   (``llm_called``), and the trigger reads only exogenous streams (``prev_demand`` and alerts;
   ``collie/trigger/detectors.py``), so its trace is identical for every arm on an episode. Each
   firing is attributed to the alert channel when an alert was delivered that period, else to the
   demand CUSUM. The ``no_alert`` condition therefore *is* the demand detector's standalone power.
2. **Where the -565.5 lives**, by family x condition, from ``out/q2_decomposition.json``.
3. **Arrival-side observability.** Two accounting identities over quantities the observation
   contract exposes (``docs/env_contract.md`` §4: previous order, previous arrivals, in-transit
   total, promised lead time) are evaluated on arm 1's stored trajectories:

   * in-transit identity ``r_t = IT_t + q_t - A_t - IT_{t+1}``: under the authoritative ``eval/``
     semantics a lost order never enters in-transit, so ``r_t`` equals ``q_t`` exactly when the
     order at ``t`` was lost and 0 otherwise (checked against the hidden lead times, which are
     used here only to verify the identity, never as a signal);
   * promised-lead residual ``e_t = A_t - q_{t-L}`` with ``L`` the promised lead time.

   Both are readable at decision period ``t + 1``. The latency reported is that decision period
   minus the true onset, next to the demand CUSUM's latency on the same seed.
"""

from __future__ import annotations

import json
import math
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.forensics.common import (
    ARM1,
    ARM10,
    CTRL,
    OUT,
    cluster_bootstrap,
    episode_frame,
    load_raw,
    load_truth,
    parse_episode_id,
    periods_by,
    write_json,
)
from analysis.forensics.harness import pilot_contexts


def firing_rows(stored: dict, frame, truth: dict, contexts: dict) -> list[dict]:
    rows = []
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    for episode in sorted(frame.episode_id.unique()):
        ctx = contexts[episode]
        firings = [p["period"] for p in stored[(episode, ARM10)] if p["llm_called"]]
        ctrl_switch = next(
            (p["period"] for p in stored[(episode, CTRL)] if p["active_spec_id"] is not None), None
        )
        if firings and ctrl_switch != firings[0]:
            raise AssertionError(f"{episode}: control switch {ctrl_switch} != first firing")
        onset = truth[episode]["onset_period"] if episode in truth else None
        sources = ["alert" if period in ctx.alerts else "detector" for period in firings]
        rows.append(
            {
                "episode_id": episode,
                "key": meta.loc[episode, "key"],
                "condition": meta.loc[episode, "condition"],
                "cluster": meta.loc[episode, "cluster"],
                "is_null": bool(meta.loc[episode, "is_null"]),
                "onset": onset,
                "alert_periods": sorted(ctx.alerts),
                "firings": firings,
                "sources": sources,
                "first_latency": None if (not firings or onset is None) else firings[0] - onset,
                "detector_firings": [
                    p for p, s in zip(firings, sources, strict=True) if s == "detector"
                ],
            }
        )
    return rows


def firing_table(rows: list[dict]) -> dict:
    table: dict[str, dict] = defaultdict(dict)
    for key in sorted({r["key"] for r in rows}):
        for condition in ("no_alert", "early_accurate", "late_accurate", "unreliable"):
            cell = [r for r in rows if r["key"] == key and r["condition"] == condition]
            if not cell:
                continue
            fired = [r for r in cell if r["firings"]]
            table[key][condition] = {
                "episodes": len(cell),
                "fired": len(fired),
                "first_firing_source": {
                    s: sum(1 for r in fired if r["sources"][0] == s) for s in ("alert", "detector")
                },
                "firings_per_episode": float(np.mean([len(r["firings"]) for r in cell])),
                "detector_firings_before_onset": sum(
                    1
                    for r in cell
                    if r["onset"] is not None
                    for p in r["detector_firings"]
                    if p < r["onset"]
                ),
                "first_latency": [
                    r["first_latency"] for r in fired if r["first_latency"] is not None
                ],
            }
    return dict(table)


def detector_power(rows: list[dict]) -> dict:
    """The demand CUSUM alone: ``no_alert`` rows, one per seed (conditions are replays)."""
    out = {}
    for key in sorted({r["key"] for r in rows}):
        cell = [r for r in rows if r["key"] == key and r["condition"] == "no_alert"]
        seeds = {r["cluster"]: r for r in cell}
        post_onset = [
            r
            for r in seeds.values()
            if r["firings"] and (r["onset"] is None or r["firings"][0] >= r["onset"])
        ]
        out[key] = {
            "distinct_seeds": len(seeds),
            "fired_at_all": sum(1 for r in seeds.values() if r["firings"]),
            "fired_at_or_after_onset": len(post_onset),
            "latencies": sorted(
                r["first_latency"] for r in post_onset if r["first_latency"] is not None
            ),
        }
    return out


def arrival_observability(stored: dict, frame, truth: dict, contexts: dict) -> dict:
    """Identity residuals on arm 1's trajectories, one per seed, plus every null twin."""
    per_seed = []
    identity_violations = 0
    false_signals = 0
    seen = set()
    for episode in sorted(frame.episode_id.unique()):
        meta = parse_episode_id(episode)
        key = (meta["cluster"], meta["is_null"])
        if key in seen:
            continue
        seen.add(key)
        ctx = contexts[episode]
        records = stored[(episode, ARM1)]
        lead_times = ctx.instance.supply.lead_times
        promised = ctx.instance.spec.promised_lead_time
        q = [r["order_quantity"] for r in records]
        arrivals = [r["arrivals"] for r in records]
        in_transit = [r["in_transit_start"] for r in records]
        horizon = len(records)
        first_identity = None
        first_residual = None
        for t in range(horizon - 1):
            lost = math.isinf(lead_times[t])
            r_t = in_transit[t] + q[t] - arrivals[t] - in_transit[t + 1]
            if r_t != (q[t] if lost else 0.0):
                identity_violations += 1
            if r_t != 0.0 and first_identity is None:
                first_identity = t + 2  # period t+1 (1-based), readable at decision t+2
        for t in range(horizon):
            expected = q[t - promised] if t - promised >= 0 else 0.0
            if arrivals[t] != expected and first_residual is None:
                first_residual = t + 2
        onset = truth[episode]["onset_period"] if episode in truth else None
        # demand-only families and twins: any nonzero signal would be a false alarm
        demand_only_or_twin = onset is None or meta["fam"] in (1, 2, 3)
        if demand_only_or_twin and (first_identity is not None or first_residual is not None):
            false_signals += 1
        per_seed.append(
            {
                "episode_id": episode,
                "family": int(meta["fam"]),
                "is_null": bool(meta["is_null"]),
                "promised_lead_time": promised,
                "onset": onset,
                "loss_signal_decision_period": first_identity,
                "arrival_residual_decision_period": first_residual,
                "loss_signal_latency": None
                if (first_identity is None or onset is None)
                else first_identity - onset,
                "arrival_residual_latency": None
                if (first_residual is None or onset is None)
                else first_residual - onset,
            }
        )
    by_family: dict[str, dict] = {}
    for fam in sorted({p["family"] for p in per_seed if not p["is_null"]}):
        rows = [p for p in per_seed if p["family"] == fam and not p["is_null"]]
        by_family[str(fam)] = {
            "seeds": len(rows),
            "loss_signal_latency": [p["loss_signal_latency"] for p in rows],
            "arrival_residual_latency": [p["arrival_residual_latency"] for p in rows],
        }
    return {
        "identity_violations": identity_violations,
        "false_signals_on_demand_families_and_twins": false_signals,
        "trajectories_checked": len(per_seed),
        "by_family": by_family,
        "per_seed": per_seed,
    }


def gap_by_cell() -> dict:
    """The -565.5 by family x condition, from Q2's per-episode rows."""
    q2 = json.loads((OUT / "q2_decomposition.json").read_text())
    cells: dict[str, dict] = defaultdict(dict)
    total = 0.0
    n = len(q2["episodes"])
    for key in sorted({e["key"] for e in q2["episodes"]}):
        for condition in ("no_alert", "early_accurate", "late_accurate", "unreliable"):
            eps = [e for e in q2["episodes"] if e["key"] == key and e["condition"] == condition]
            if not eps:
                continue
            contribution = sum(e["gap_profit"] for e in eps) / n
            total += contribution
            cells[key][condition] = {
                "n": len(eps),
                "fired": sum(1 for e in eps if e["category"] != "no_fire"),
                "contribution_gross": contribution,
                "contribution_net": sum(e["gap_reward"] for e in eps) / n,
            }
    return {"cells": dict(cells), "sum": total}


SUPPLY_KEYS = ("lead_time_shift", "shipment_loss")
"""Families whose shock never touches demand, so the demand CUSUM cannot see them."""


def actionability_class(key: str, condition: str) -> str:
    """Which arm could act on the episode's shock, given the shared trigger and the payloads.

    * ``supply_no_alert``: telemetry-blind shock and no alert. The shared trigger reads only
      ``prev_demand`` and alerts, so neither arm can fire.
    * ``supply_alert_only``: telemetry-blind shock with an alert. Both arms fire on the alert
      alone, and neither can compile the right family: the control's payload is the fixed
      demand-up constant and the scripted proposal is the same demand-up payload.
    * ``demand_visible``: the shock moves demand, so the CUSUM can see it.
    * ``null``: no shock.
    """
    if key == "null":
        return "null"
    if key in SUPPLY_KEYS:
        return "supply_no_alert" if condition == "no_alert" else "supply_alert_only"
    return "demand_visible"


def gap_by_actionability() -> dict:
    """The -565.5 by actionability class, with seed-cluster bootstrap intervals."""
    q2 = json.loads((OUT / "q2_decomposition.json").read_text())
    df = pd.DataFrame(q2["episodes"])
    df["cls"] = [actionability_class(k, c) for k, c in zip(df.key, df.condition, strict=True)]
    total = {c: float(df[f"gap_{c}"].mean()) for c in ("profit", "reward")}
    out: dict[str, object] = {"total_gross": total["profit"], "total_net": total["reward"]}
    classes = ("supply_no_alert", "supply_alert_only", "demand_visible", "null")
    for cls in classes:
        mask = df.cls == cls
        entry: dict[str, object] = {
            "n": int(mask.sum()),
            "categories": df[mask].category.value_counts().to_dict(),
        }
        for c, label in (("profit", "gross"), ("reward", "net")):
            values = df[f"gap_{c}"].where(mask, 0.0).astype(float)
            contribution = float(values.mean())
            entry[f"contribution_{label}"] = contribution
            entry[f"share_of_total_{label}"] = contribution / total[c]
            entry[f"seed_cluster_interval_{label}"] = list(cluster_bootstrap(values, df["cluster"]))
        out[cls] = entry
    check = sum(out[cls]["contribution_gross"] for cls in classes)
    if not math.isclose(check, total["profit"], abs_tol=1e-9):
        raise AssertionError(f"actionability classes sum to {check}, not {total['profit']}")
    return out


def firing_sources(rows: list[dict]) -> dict:
    """What fired first on each of the 120 episodes: the alert, the demand CUSUM, or nothing."""
    counts = {"alert": 0, "detector": 0, "none": 0}
    for row in rows:
        counts[row["sources"][0] if row["firings"] else "none"] += 1
    return counts


def main() -> None:
    raw = load_raw()
    truth = load_truth()
    frame = episode_frame(raw)
    stored = periods_by(raw, [ARM1, ARM10, CTRL])
    with tempfile.TemporaryDirectory() as tmp:
        contexts = {c.episode_id: c for c in pilot_contexts(Path(tmp))}
        rows = firing_rows(stored, frame, truth, contexts)
        observability = arrival_observability(stored, frame, truth, contexts)
    summary = {
        "firing_table": firing_table(rows),
        "first_firing_source": firing_sources(rows),
        "detector_power_no_alert": detector_power(rows),
        "gap_by_cell": gap_by_cell(),
        "gap_by_actionability": gap_by_actionability(),
        "arrival_observability": {k: v for k, v in observability.items() if k != "per_seed"},
    }
    path = write_json(
        "q3_detection.json",
        {"summary": summary, "firings": rows, "observability_per_seed": observability["per_seed"]},
    )
    print(json.dumps(summary, indent=2, default=float))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
