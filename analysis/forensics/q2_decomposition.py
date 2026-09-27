"""Q2 — decompose the -565.5 detector gap (arm 10 minus ``ctrl_cusum_to_compiler``).

Exploratory. Run: ``uv run python -m analysis.forensics.q2_decomposition``.

Every episode falls in exactly one category, so the category contributions (sum of episode gaps
over the 120 episodes, divided by 120) add up to the registered estimate exactly:

* ``no_fire``   — the shared wrapped trigger never fires: both arms run the baseline.
* ``blocked``   — the control compiled at the first firing; arm 10 proposed at the same period
                  but its e-process never activated, so it ran the baseline throughout.
* ``activated`` — arm 10 activated at some period ``t_act`` after its proposal.

For ``activated`` episodes the gap is split with one counterfactual replay through the frozen
runner: ``D`` = the control's own compile-and-hold seam, switched at arm 10's activation period
instead of at the firing. Then, telescoping exactly,

    arm10 - ctrl = (D - ctrl)        activation delay: the same config, adopted t_act - tau later
                 + (arm10 - D)       lifecycle: arm 10 standing down (refuted / expired) vs holding

``D`` must equal arm 10 bit for bit on every episode where arm 10 never stands down; the script
asserts it. Scripted-transport provenance applies to every number: the proposal is always the
fixed demand-up/medium payload, which is also the control's payload (arm 8 == control).
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.forensics.common import (
    ARM1,
    ARM8,
    ARM10,
    CTRL,
    cluster_bootstrap,
    episode_frame,
    load_raw,
    periods_by,
    write_json,
)
from analysis.forensics.harness import (
    build_arm,
    metered_stack,
    pilot_contexts,
    run,
    same_as_stored,
    scheduled_switch_arm,
    signature,
)

_SPEC_ID = re.compile(r"^spec-(?P<index>\d+)@tau(?P<tau>\d+)$")
COLUMNS = ("profit", "lost", "holding", "reward")


def _first(periods: list[dict], predicate) -> int | None:
    return next((p["period"] for p in periods if predicate(p)), None)


def classify(stored: dict, episode: str) -> dict:
    a10 = stored[(episode, ARM10)]
    ctrl = stored[(episode, CTRL)]
    switch = _first(ctrl, lambda p: p["active_spec_id"] is not None)
    proposals = [p["period"] for p in a10 if p["llm_called"]]
    active = [p["period"] for p in a10 if p["active_spec_id"] is not None]
    info: dict[str, object] = {
        "ctrl_switch": switch,
        "arm10_proposals": proposals,
        "arm10_active_periods": len(active),
    }
    if switch is None:
        info["category"] = "no_fire"
        if proposals:
            raise AssertionError(f"{episode}: arm 10 proposed but the control never fired")
        return info
    if proposals[0] != switch:
        raise AssertionError(f"{episode}: first proposal {proposals[0]} != control switch {switch}")
    if not active:
        info["category"] = "blocked"
        return info
    t_act = min(active)
    spec_id = next(p["active_spec_id"] for p in a10 if p["period"] == t_act)
    match = _SPEC_ID.match(spec_id)
    assert match is not None, spec_id
    tau = int(match["tau"])
    after = [p for p in a10 if p["period"] > t_act]
    stand_downs = [p["period"] for p in after if p["active_spec_id"] is None]
    info.update(
        category="activated",
        t_act=t_act,
        activated_spec=spec_id,
        activated_proposal_index=int(match["index"]),
        tau=tau,
        delay=t_act - tau,
        delay_from_first_proposal=t_act - switch,
        stood_down=bool(stand_downs),
        first_stand_down=min(stand_downs) if stand_downs else None,
        states_after_activation=sorted({str(p["lifecycle_state"]) for p in after}),
    )
    return info


def main() -> None:
    raw = load_raw()
    frame = episode_frame(raw)
    stored = periods_by(raw, [ARM1, ARM8, ARM10, CTRL])
    episodes = sorted(frame.episode_id.unique())
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    totals = {
        (row.episode_id, row.arm): {c: getattr(row, c) for c in COLUMNS}
        for row in frame.itertuples()
    }

    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contexts = {c.episode_id: c for c in pilot_contexts(root)}
        metered = metered_stack(root)
        for episode in episodes:
            ctx = contexts[episode]
            # Re-simulate both contrast arms and require bit-for-bit reproduction first.
            for arm_id in (CTRL, ARM10):
                controller, iso = build_arm(arm_id, ctx, metered)
                result = run(controller, ctx.instance, ctx, isolation=iso).result
                if not same_as_stored(result, stored[(episode, arm_id)]):
                    raise AssertionError(f"{arm_id} does not reproduce on {episode}")
            info = classify(stored, episode)
            a10, ctrl, a1 = (totals[(episode, arm)] for arm in (ARM10, CTRL, ARM1))
            row = {
                "episode_id": episode,
                "cluster": meta.loc[episode, "cluster"],
                "key": meta.loc[episode, "key"],
                "condition": meta.loc[episode, "condition"],
                "is_null": bool(meta.loc[episode, "is_null"]),
                **info,
            }
            for c in COLUMNS:
                row[f"gap_{c}"] = a10[c] - ctrl[c]
                row[f"a10_vs_arm1_{c}"] = a10[c] - a1[c]
                row[f"ctrl_vs_arm1_{c}"] = ctrl[c] - a1[c]
            if info["category"] in ("no_fire", "blocked") and signature(
                stored[(episode, ARM10)]
            ) != signature(stored[(episode, ARM1)]):
                raise AssertionError(f"{episode}: arm 10 never active but differs from arm 1")
            if info["category"] == "no_fire" and signature(stored[(episode, CTRL)]) != signature(
                stored[(episode, ARM1)]
            ):
                raise AssertionError(f"{episode}: control never fired but differs from arm 1")
            if info["category"] == "activated":
                delayed = scheduled_switch_arm(ctx, switch_period=int(info["t_act"]))
                d = run(delayed, ctx.instance, ctx, isolation=True).result
                if not info["stood_down"] and not same_as_stored(d, stored[(episode, ARM10)]):
                    raise AssertionError(f"{episode}: delayed control != arm 10 without stand-down")
                d_tot = {
                    "profit": d.total_profit,
                    "lost": d.total_lost_sales,
                    "holding": d.total_holding_cost,
                    "reward": d.total_reward,
                }
                for c in COLUMNS:
                    row[f"delay_{c}"] = d_tot[c] - ctrl[c]
                    row[f"lifecycle_{c}"] = a10[c] - d_tot[c]
            rows.append(row)

    df = pd.DataFrame(rows)
    n = len(df)
    for c in COLUMNS:
        for part in ("delay", "lifecycle"):
            df[f"{part}_{c}"] = df.get(f"{part}_{c}", pd.Series(0.0, index=df.index)).fillna(0.0)

    summary = {
        "n_episodes": n,
        "registered_estimate_gross": float(df["gap_profit"].mean()),
        "decomposition": decomposition(df, n),
        "activation": activation_summary(df),
        "benefit_given_activation": benefit_given_activation(df),
        "nulls": null_summary(df),
        "intervals": component_intervals(df),
    }
    path = write_json("q2_decomposition.json", {"summary": summary, "episodes": rows})
    print(json.dumps(summary, indent=2, default=float))
    print(f"\nwrote {path}")


def decomposition(df: pd.DataFrame, n: int) -> dict:
    """Contributions to the 120-episode mean, by stratum x category, for every column."""
    out: dict[str, object] = {}
    strata = [*sorted(k for k in df.key.unique() if k != "null"), "null"]
    for c in COLUMNS:
        cells: dict[str, dict] = {}
        total = 0.0
        for stratum in strata:
            sub = df[df.key == stratum]
            entry: dict[str, object] = {"n": len(sub)}
            for cat in ("no_fire", "blocked", "activated"):
                part = sub[sub.category == cat]
                contribution = float(part[f"gap_{c}"].sum()) / n
                total += contribution
                entry[cat] = {
                    "n": len(part),
                    "mean_gap": float(part[f"gap_{c}"].mean()) if len(part) else 0.0,
                    "contribution": contribution,
                }
                if cat == "activated":
                    entry[cat]["delay_contribution"] = float(part[f"delay_{c}"].sum()) / n
                    entry[cat]["lifecycle_contribution"] = float(part[f"lifecycle_{c}"].sum()) / n
            cells[stratum] = entry
        out[c] = {
            "cells": cells,
            "sum_of_contributions": total,
            "registered_mean": float(df[f"gap_{c}"].mean()),
            "by_category": {
                cat: float(df[df.category == cat][f"gap_{c}"].sum()) / n
                for cat in ("no_fire", "blocked", "activated")
            },
            "activated_split": {
                part: float(df[df.category == "activated"][f"{part}_{c}"].sum()) / n
                for part in ("delay", "lifecycle")
            },
        }
        if abs(total - out[c]["registered_mean"]) > 1e-9:
            raise AssertionError(f"{c}: contributions {total} != mean {out[c]['registered_mean']}")
    return out


def activation_summary(df: pd.DataFrame) -> dict:
    act = df[df.category == "activated"]
    by_key: dict[str, dict] = {}
    for key, g in df.groupby("key"):
        a = g[g.category == "activated"]
        by_key[key] = {
            "episodes": len(g),
            "fired": int((g.category != "no_fire").sum()),
            "activated": len(a),
            "delays": sorted(int(v) for v in a["delay"]) if len(a) else [],
            "activated_proposal_index": sorted(int(v) for v in a["activated_proposal_index"])
            if len(a)
            else [],
            "stood_down": int(a["stood_down"].sum()) if len(a) else 0,
        }
    delays = act["delay"].to_numpy(dtype=float)
    return {
        "activated_episodes": len(act),
        "delay_quantiles": {q: float(np.quantile(delays, q)) for q in (0.0, 0.25, 0.5, 0.75, 1.0)}
        if len(delays)
        else {},
        "by_key": by_key,
    }


def benefit_given_activation(df: pd.DataFrame) -> dict:
    act = df[df.category == "activated"]
    out: dict[str, dict] = {}
    for key, g in [("all_activated", act), *act.groupby("key")]:
        out[key] = {
            "n": len(g),
            **{
                f"{lhs}_{c}": float(g[f"{lhs}_{c}"].mean())
                for lhs in ("gap", "a10_vs_arm1", "ctrl_vs_arm1")
                for c in ("profit", "reward", "holding", "lost")
            },
        }
    return out


def null_summary(df: pd.DataFrame) -> dict:
    nulls = df[df.is_null]
    out = {}
    for condition, g in nulls.groupby("condition"):
        out[condition] = {
            "n": len(g),
            "categories": g.category.value_counts().to_dict(),
            **{
                f"{lhs}_{c}": float(g[f"{lhs}_{c}"].mean())
                for lhs in ("gap", "a10_vs_arm1", "ctrl_vs_arm1")
                for c in ("profit", "reward", "holding", "lost")
            },
        }
    return out


def component_intervals(df: pd.DataFrame) -> dict:
    """Seed-cluster bootstrap for the per-episode component series (mean over all 120)."""
    out: dict[str, list[float]] = {}
    for c in ("profit", "reward"):
        series = {
            "gap": df[f"gap_{c}"],
            "blocked": df[f"gap_{c}"].where(df.category == "blocked", 0.0),
            "activated_delay": df[f"delay_{c}"].where(df.category == "activated", 0.0),
            "activated_lifecycle": df[f"lifecycle_{c}"].where(df.category == "activated", 0.0),
            "null_episodes": df[f"gap_{c}"].where(df.is_null, 0.0),
        }
        for name, values in series.items():
            out[f"{name}_{c}"] = list(cluster_bootstrap(values.astype(float), df["cluster"]))
    return out


if __name__ == "__main__":
    main()
