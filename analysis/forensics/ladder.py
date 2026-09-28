"""The arm ladder by headroom family, read from the stored records. Exploratory.

Run: ``uv run python -m analysis.forensics.ladder`` (writes ``out/ladder.json``).

The ``ctrl_alertspec_upper_bound`` arm compiles the *canonical* alert structure at onset - 1 and
holds it: it is perfect parsing with no verification delay, the most any alert-reading arm could
extract through the frozen compiler. Its contrast with the detector control therefore bounds,
under this compiler and these demo alerts, how much language could ever beat the detector on
the registered endpoint — independently of what the scripted transport proposed.
"""

from __future__ import annotations

import json
from collections import Counter

import numpy as np

from analysis.forensics.common import (
    ARM1,
    ARM8,
    ARM9,
    ARM10,
    CTRL,
    ORACLE,
    OUT,
    episode_frame,
    load_raw,
    write_json,
)

UB = "ctrl_alertspec_upper_bound"
KEYWORD = "ctrl_keyword_parser"
ARM2 = "arm2_telemetry_hmm_or"
ARMS = (ARM1, ARM2, ARM8, ARM9, ARM10, CTRL, KEYWORD, UB, ORACLE)


def main() -> None:
    raw = load_raw()
    frame = episode_frame(raw)
    out: dict[str, object] = {
        "record_analysis_class": dict(Counter(r["analysis_class"] for r in raw)),
        "record_model_ids": dict(Counter(c["model_id"] for r in raw for c in r["calls"])),
    }
    by_key: dict[str, dict] = {}
    for key, g in frame.groupby("key"):
        cells = {}
        for arm in ARMS:
            a = g[g.arm == arm]
            if a.empty:
                continue
            cells[arm] = {
                "n": len(a),
                "gross": float(a.profit.mean()),
                "net": float(a.reward.mean()),
                "lost": float(a.lost.mean()),
                "holding": float(a.holding.mean()),
                "fill": float(a.fill.mean()),
            }
        contrasts = {}
        for treatment in (UB, ARM10, ARM9, KEYWORD, ORACLE):
            if treatment in cells:
                contrasts[f"{treatment}_minus_ctrl"] = {
                    "gross": cells[treatment]["gross"] - cells[CTRL]["gross"],
                    "net": cells[treatment]["net"] - cells[CTRL]["net"],
                }
        contrasts["ctrl_minus_arm1"] = {
            "gross": cells[CTRL]["gross"] - cells[ARM1]["gross"],
            "net": cells[CTRL]["net"] - cells[ARM1]["net"],
        }
        by_key[key] = {"arms": cells, "contrasts": contrasts}
    out["by_key"] = by_key

    q2 = json.loads((OUT / "q2_decomposition.json").read_text())
    episodes = q2["episodes"]
    out["category_by_condition"] = {
        key: {
            cond: dict(
                Counter(
                    e["category"] for e in episodes if e["key"] == key and e["condition"] == cond
                )
            )
            for cond in ("no_alert", "early_accurate", "late_accurate", "unreliable")
        }
        for key in sorted({e["key"] for e in episodes})
    }
    shocked = [e for e in episodes if not e["is_null"]]
    wrong = [
        e for e in shocked if e["category"] == "activated" and e["key"] != "demand_level:demand_up"
    ]
    out["wrong_family_activation"] = {
        "shocked_episodes": len(shocked),
        "wrong_family_activated": len(wrong),
        "rate": len(wrong) / len(shocked),
        "by_key": dict(Counter(e["key"] for e in wrong)),
    }
    # Under scripted transport the proposal ignores alert text, and the early-accurate and
    # unreliable alerts arrive in the same period (onset - 1), so those two conditions should be
    # exact replays for every arm that does not read text itself.
    stored = {(r["episode_id"], r["arm_id"]): r["records"] for r in raw}
    fields = ("order_quantity", "units_sold", "on_hand_end")

    def sig(episode: str, arm: str) -> tuple:
        return tuple(tuple(p[f] for f in fields) for p in stored[(episode, arm)])

    replica = {}
    shocked_frame = frame[~frame.is_null]
    for arm in (ARM8, ARM9, ARM10, CTRL, KEYWORD):
        same = total = 0
        for cluster in sorted(shocked_frame.cluster.unique()):
            base = f"{cluster}/early_accurate"
            other = f"{cluster}/unreliable"
            total += 1
            same += sig(base, arm) == sig(other, arm)
        replica[arm] = {"seeds": total, "early_accurate_equals_unreliable": same}
    out["early_vs_unreliable_replicas"] = replica

    # Perfect language, no verification delay, perfect abstention: the canonical AlertSpec
    # upper bound on shocked episodes (it compiles the true structure at onset - 1 and holds),
    # arm 1 on null episodes. Its contrast with the detector control is a ceiling, under this
    # compiler and endpoint, on what any language arm could add over the detector.
    pivot_g = frame.pivot(index="episode_id", columns="arm", values="profit")
    pivot_n = frame.pivot(index="episode_id", columns="arm", values="reward")
    nulls = frame.drop_duplicates("episode_id").set_index("episode_id")["is_null"]
    bound = {}
    for name, pivot in (("gross", pivot_g), ("net", pivot_n)):
        best = pivot[UB].where(~nulls, pivot[ARM1])
        diff = best - pivot[CTRL]
        bound[name] = {
            "mean_over_120": float(diff.mean()),
            "shocked_mean": float(diff[~nulls].mean()),
            "null_mean": float(diff[nulls].mean()),
        }
    out["perfect_language_bound_vs_detector"] = bound

    # What each switching arm actually compiled while a spec was active, per headroom family:
    # the (m, l_eff, gamma) configurations and how many active periods carried each.
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")["key"]
    compiled: dict[str, dict[str, dict[str, int]]] = {}
    for arm in (CTRL, ARM10, KEYWORD, UB, ORACLE):
        per_key: dict[str, Counter] = {}
        for (episode, arm_id), periods in stored.items():
            if arm_id != arm:
                continue
            counter = per_key.setdefault(meta[episode], Counter())
            for p in periods:
                if p["active_spec_id"] and p["control_config"]:
                    c = p["control_config"]
                    counter[f"({c['m']:g}, {c['l_eff']}, {c['gamma']:g})"] += 1
        compiled[arm] = {k: dict(v) for k, v in sorted(per_key.items())}
    out["compiled_configs_active_periods"] = compiled

    act = [e for e in episodes if e["category"] == "activated"]
    out["activated_by_condition"] = {
        cond: {
            "n": sum(1 for e in act if e["condition"] == cond),
            "median_delay": float(np.median([e["delay"] for e in act if e["condition"] == cond]))
            if any(e["condition"] == cond for e in act)
            else None,
        }
        for cond in ("no_alert", "early_accurate", "late_accurate", "unreliable")
    }
    path = write_json("ladder.json", out)
    print(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
