"""Post-hoc readouts of the stage C runs and the stage A ladder. Written after the results were
seen; decides nothing.

Contrasts use the registered evaluator's own helper (``confirm.contrast``: seed-cluster
bootstrap and cluster sign-flip, same seeds). The exposure ratio has its own cluster bootstrap
(a ratio of cluster sums), described at :func:`exposure_ratio`. Values are stored unrounded;
round them once, for display only. The readouts answer questions two independent audits raised:

* **Where the gain comes from.** Certify-then-hedge minus arm 1 by family; the share of the
  total from the 32 shocked lead-time episodes (arithmetic on the registered per-family readout)
  and from the lead-time units (those episodes and their twins); and the contrasts without the
  lead-time units, so whole clusters drop.
* **Prior contact.** The primary contrasts without the six clusters of units ``i = 0``, whose
  outcomes a pre-registration structural test computed (PLAN.md, stage C amendment C3).
* **Null episodes.** Null safety split into silent and false-alert twins; the method against
  the content-free control on the twins.
* **What the model's label buys.** Null exposure of the method against the content-free control,
  as a ratio with a cluster bootstrap interval, split by twin type and by the hypothesis that
  carried the mass.
* **Endpoint sign.** Every stage C contrast on net and gross, flagged where the sign differs.
* **The ladder** (stage A): how acting at once relates to commitment and to accuracy across the
  finished rungs, descriptively.

Usage::

    uv run python -m analysis.commitment.posthoc [--out out/posthoc.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.commitment import confirm
from analysis.commitment.ladder import run_name as ladder_run_name
from analysis.commitment.readout_d import true_shift

OUT = confirm.OUT
RUNS = (
    "fresh-gemini-3.8-flash",
    "fresh-grok-4.20",
    "fresh-gemini-2.5-flash-lite",
    "fresh-llama-3.1-8b",
    "fresh-deepseek-v3",
    "fresh-gpt-3.5-turbo",
)
LEAD_TIME_FAMILY = 4
STRUCTURAL_TEST_INDEX = 0
FRESH_BASE = 100_000
MIN_RATIO_CLUSTERS = 5
"""Below this many clusters with nonzero content-free exposure, the ratio is not estimated."""


def _contrast(frame: pd.DataFrame, treat: str, control: str, mask=None) -> dict:
    c = confirm.contrast(frame, treat, control, "net", mask=mask)
    return {k: c[k] for k in ("n", "clusters", "mean", "b", "p_one_sided")} if c else {}


def frame_with_units(run: str) -> pd.DataFrame:
    frame = confirm.episode_frame(run)
    unit = frame["cluster"].str.extract(r"f(?P<unit_fam>\d)/s(?P<seed>\d+)$").astype(int)
    frame["unit_fam"] = unit["unit_fam"]
    frame["unit_index"] = unit["seed"] - unit["unit_fam"] * 1_000_000 - FRESH_BASE
    frame["false_alert_twin"] = frame["is_null"] & (frame["condition"] == "unreliable")
    return frame


def cth_log(run: str) -> pd.DataFrame:
    return pd.DataFrame(confirm._jsonl_gz(OUT / run / "cth_log.jsonl.gz"))


def exposure_ratio(exp: pd.DataFrame, meta: pd.DataFrame, mask: pd.Series) -> dict:
    """Summed null exposure of the method over the content-free control's.

    The interval resamples clusters (10,000 draws, the evaluator's seed) and takes the ratio of
    the resampled sums; draws whose content-free sum is zero have no ratio and are dropped, and
    their count is reported. With fewer than ``MIN_RATIO_CLUSTERS`` clusters carrying nonzero
    content-free exposure the ratio is not estimated.
    """
    ids = mask[mask].index
    part = exp.reindex(ids).fillna(0.0)
    clusters = meta.loc[ids, "cluster"]
    num = part[confirm.CTH].groupby(clusters.values).sum()
    den = part[confirm.UNIFORM].groupby(clusters.values).sum()
    out = {
        "episodes": len(ids),
        "cth_mean": float(part[confirm.CTH].mean()),
        "cth_llm_mean": float(part[confirm.CTH_LLM].mean()),
        "uniform_mean": float(part[confirm.UNIFORM].mean()),
        "episodes_uniform_zero": int((part[confirm.UNIFORM] == 0).sum()),
        "clusters_uniform_nonzero": int((den > 0).sum()),
    }
    if out["clusters_uniform_nonzero"] < MIN_RATIO_CLUSTERS:
        return {**out, "cth_over_uniform": None, "b": None, "note": "not estimable"}
    rng = np.random.default_rng(confirm.SEED)
    keys = num.index.to_numpy()
    draws = []
    for _ in range(confirm.RESAMPLES):
        pick = rng.integers(0, len(keys), len(keys))
        d = den.iloc[pick].sum()
        if d > 0:
            draws.append(num.iloc[pick].sum() / d)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {
        **out,
        "cth_over_uniform": float(num.sum() / den.sum()),
        "b": [float(lo), float(hi)],
        "valid_draws": len(draws),
    }


def exposure_by_hypothesis(log: pd.DataFrame, null_ids) -> dict:
    """Mean summed null-twin shock mass per arm, split by the period's top hypothesis."""
    part = log[log.episode_id.isin(null_ids)]
    n = len(null_ids)
    out = {}
    for arm, rows in part.groupby("arm_id"):
        by_top = rows.groupby(rows["top"].fillna("none")).shock_mass.sum() / n
        out[arm] = {str(k): float(v) for k, v in by_top.items()}
    return out


STATED_PERIODS = {"low": 1, "medium": 2, "high": 3}
"""The lead-time shift each magnitude bin compiles to, on top of the running lead
(``collie/control/mapping.py``: l_eff 2, 3, 4 against a reference of 1)."""


def lead_time_proposals(run: str) -> dict:
    """Arm 10 on the shocked lead-time episodes: the first lead-time proposal's magnitude, its
    stated size against the true shift (two periods from a baseline lead of 1, one from 2; every
    family-4 unit moves to a lead of 3), and periods from that proposal to the gate's first active
    period."""
    truth = {r["episode_id"]: r for r in confirm._jsonl(OUT / run / "truth.jsonl")}
    shocked = {e for e in truth if f"/f{LEAD_TIME_FAMILY}/" in e and not e.endswith("__twin")}
    first: dict[str, dict] = {}
    for p in sorted(
        confirm._jsonl(OUT / run / "proposals.jsonl"), key=lambda r: (r["episode_id"], r["period"])
    ):
        if p["arm_id"] != confirm.ARM10 or p["episode_id"] not in shocked or not p["parsed"]:
            continue
        if p["payload"]["shock_family"] == "lead_time_shift" and p["episode_id"] not in first:
            first[p["episode_id"]] = p
    delays = []
    for r in confirm._jsonl_gz(OUT / run / "records.jsonl.gz"):
        if r["arm_id"] != confirm.ARM10 or r["episode_id"] not in first:
            continue
        active = [x["period"] for x in r["records"] if x.get("active_spec_id")]
        if active:
            delays.append(min(active) - first[r["episode_id"]]["period"])
    magnitudes: dict[str, int] = {}
    versus = {"right": 0, "too_large": 0, "too_small": 0}
    for episode, p in first.items():
        key = str(p["payload"]["magnitude_bin"])
        magnitudes[key] = magnitudes.get(key, 0) + 1
        stated, true = STATED_PERIODS[key], true_shift(episode)
        versus["right" if stated == true else "too_large" if stated > true else "too_small"] += 1
    return {
        "shocked_episodes": len(shocked),
        "true_magnitudes": sorted({str(truth[e].get("magnitude_bin")) for e in shocked}),
        "with_lead_time_proposal": len(first),
        "first_proposal_magnitude": magnitudes,
        "first_proposal_vs_true_shift": versus,
        "gate_activated": len(delays),
        "gate_delay_median": float(np.median(delays)) if delays else None,
        "gate_delays": sorted(delays),
    }


def readout(run: str) -> dict:
    frame = frame_with_units(run)
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    out: dict = {}

    pivot = frame.pivot(index="episode_id", columns="arm", values="net")
    diff = pivot[confirm.CTH] - pivot[confirm.ARM1]
    total = float(diff.sum())
    lead_episodes = float(diff[meta["fam"] == LEAD_TIME_FAMILY].sum())
    lead_units = float(diff[meta["unit_fam"] == LEAD_TIME_FAMILY].sum())
    without_lead = meta["unit_fam"] != LEAD_TIME_FAMILY
    out["gain_source"] = {
        "cth_minus_arm1_total": total,
        "lead_time_episodes_share": lead_episodes / total if total else None,
        "lead_time_units_share": lead_units / total if total else None,
        "cth-arm1|net|without_lead_time_units": _contrast(
            frame, confirm.CTH, confirm.ARM1, without_lead
        ),
        "uniform-arm1|net|without_lead_time_units": _contrast(
            frame, confirm.UNIFORM, confirm.ARM1, without_lead
        ),
        "cth-arm10|net|without_lead_time_units": _contrast(
            frame, confirm.CTH, confirm.ARM10, without_lead
        ),
        "by_family_net": {
            name: {
                str(f): float((pivot[t] - pivot[confirm.ARM1])[meta["fam"] == f].mean())
                for f in sorted(meta["fam"].unique())
            }
            for name, t in (
                ("cth-arm1", confirm.CTH),
                ("uniform-arm1", confirm.UNIFORM),
                ("arm10-arm1", confirm.ARM10),
            )
        },
        "by_family_cth-arm1|net": {
            str(f): _contrast(frame, confirm.CTH, confirm.ARM1, meta["fam"] == f)
            for f in sorted(meta["fam"].unique())
        },
    }

    untouched = meta["unit_index"] != STRUCTURAL_TEST_INDEX
    out["without_structural_test_clusters"] = {
        f"{name}|net": _contrast(frame, treat, control, untouched)
        for name, treat, control in (
            ("cth-arm10", confirm.CTH, confirm.ARM10),
            ("cth-arm1", confirm.CTH, confirm.ARM1),
        )
    }

    null = meta["is_null"]
    fa = meta["false_alert_twin"]
    out["null_cth_minus_uniform"] = _contrast(frame, confirm.CTH, confirm.UNIFORM, null)
    out["null_safety_split"] = {
        "silent": _contrast(frame, confirm.CTH, confirm.ARM1, null & ~fa),
        "false_alert": _contrast(frame, confirm.CTH, confirm.ARM1, fa),
        "silent_nonzero_episodes": int(((diff != 0) & null & ~fa).sum()),
        "worst_null_episode": float(diff[null].min()),
    }

    log = cth_log(run)
    exp = log.groupby(["arm_id", "episode_id"]).shock_mass.sum().unstack(0)
    out["null_exposure"] = {
        "all_twins": exposure_ratio(exp, meta, null),
        "false_alert_twins": exposure_ratio(exp, meta, fa),
        "silent_twins": exposure_ratio(exp, meta, null & ~fa),
        "by_top_hypothesis": exposure_by_hypothesis(log, set(meta.index[null])),
    }

    signs = {}
    piv = {e: frame.pivot(index="episode_id", columns="arm", values=e) for e in ("net", "gross")}
    for name, treat, control, _role in confirm.CONTRASTS:
        means = {e: float((piv[e][treat] - piv[e][control]).mean()) for e in piv}
        signs[name] = {
            **means,
            "sign_differs": bool(np.sign(means["net"]) != np.sign(means["gross"])),
        }
    out["net_vs_gross"] = signs
    out["lead_time_proposals"] = lead_time_proposals(run)
    return out


def ladder_readout() -> dict:
    """Across finished rungs: acting at once against commitment and accuracy (descriptive)."""
    rungs = json.loads((OUT / "ladder.json").read_text())["rungs"]
    rungs = rungs if isinstance(rungs, list) else list(rungs.values())
    rows = []
    for r in rungs:
        proposals = OUT / ladder_run_name(r["rung"]) / "proposals.jsonl"
        committed = {
            p["episode_id"]
            for p in map(json.loads, proposals.open())
            if p["arm_id"] == confirm.ARM8 and p["parsed"] and not p["abstention"]
        }
        rows.append(
            {
                "rung": r["rung"],
                "arm8_arm1_net": r["arm8_arm1_net"]["mean"],
                "family_right": r["family_right"],
                "episodes_committed_arm8": len(committed),
                "arm10_arm1_net": r["arm10_arm1_net"]["mean"],
                "arm10_arm1_b": r["arm10_arm1_net"]["cluster_bootstrap"],
            }
        )
    frame = pd.DataFrame(rows)
    loss, right, commit = (
        frame["arm8_arm1_net"],
        frame["family_right"],
        frame["episodes_committed_arm8"],
    )
    return {
        "rungs": len(frame),
        "pearson": {
            "loss_vs_family_right": float(loss.corr(right)),
            "loss_vs_committed": float(loss.corr(commit)),
            "committed_vs_family_right": float(commit.corr(right)),
        },
        "spearman": {
            "loss_vs_family_right": float(loss.corr(right, method="spearman")),
            "loss_vs_committed": float(loss.corr(commit, method="spearman")),
        },
        "gate_interval_below_zero": [
            {"rung": r["rung"], "mean": r["arm10_arm1_net"], "b": r["arm10_arm1_b"]}
            for r in rows
            if r["arm10_arm1_b"][1] < 0
        ],
        "per_rung": rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.posthoc")
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--out", type=Path, default=OUT / "posthoc.json")
    args = ap.parse_args(argv)
    report = {
        "status": "post hoc: written after the stage C results were seen; decides nothing",
        "rounding": "values are unrounded; round once, for display",
        "runs": {run: readout(run) for run in args.runs},
        "ladder": ladder_readout(),
    }
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for run, r in report["runs"].items():
        g, s, n = r["gain_source"], r["without_structural_test_clusters"], r["null_exposure"]
        w = g["cth-arm1|net|without_lead_time_units"]
        print(
            f"{run}: lead share {g['lead_time_episodes_share']:.4f} / "
            f"{g['lead_time_units_share']:.4f}; cth-arm1 w/o lead {w['mean']:.2f} "
            f"[{w['b'][0]:.2f}, {w['b'][1]:.2f}]; 42 clusters p "
            f"{s['cth-arm10|net']['p_one_sided']:.5f}, {s['cth-arm1|net']['p_one_sided']:.5f}; "
            f"exposure ratio {n['all_twins']['cth_over_uniform']:.3f}"
        )
    lad = report["ladder"]
    print(
        "ladder", lad["rungs"], lad["pearson"], [x["rung"] for x in lad["gate_interval_below_zero"]]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
