"""Stage D secondaries that the evaluator (``confirm_d.py``) does not compute. Committed before the
runs; definitions fixed in ``PLAN.md``, stage D, amendments DA3 and DA4. No multiplicity claim.

* ``across_ratios``: per model, for hedge - gate, hedge - arm 1 and hedge - content-free on net
  reward, the change from ``d1-<model>`` to ``d19-<model>``, paired by episode id (the two runs
  share the pool, the demand and lead-time paths and the alerts). Profit is ``p`` times units
  sold, so a contrast in currency scales with ``p``; the change is therefore read per unit of
  ``p``, ``c19 / 19 - c1 / 1`` per episode, and is also given in currency. Mean and a two-sided
  95% seed-cluster bootstrap over the 48 paired clusters (``confirm``'s seed and draws).
* ``share_of_arm1_net``: for every stage D run and each of those contrasts, the mean gain over
  arm 1's mean net reward, with a ratio-of-means seed-cluster bootstrap (the same cluster draws).
* ``null_safety_scaled``: stage C's null-safety contrast (hedge - arm 1 on the null twins) against
  the -25 margin scaled by ``p / 4``. Descriptive; the registered margin stays -25 in currency.
* ``by_shift``: on the lead-time units, hedge - arm 1 by the true shift (two periods for a
  baseline lead of 1, one for a baseline of 2), shocked episodes only. Means and counts.
* ``stratum`` (noisy-lead runs, amendment DA11): hedge - arm 1 per unit and per information
  condition on the shocked episodes, the two-period units' share of the total gain, and null
  exposure and null safety per baseline lead (4 twins each). Descriptive, untested.

Usage::

    uv run python -m analysis.commitment.readout_d [--out-root out] [--out out/readout_d.json]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from analysis.commitment import confirm
from analysis.commitment.confirm_d import FAMILIES, MODELS, run_name
from analysis.commitment.episodes import FAMILY_STRIDE, fresh_unit
from analysis.forensics.common import cluster_bootstrap

CONTRASTS = (
    ("cth-arm10", confirm.CTH, confirm.ARM10),
    ("cth-arm1", confirm.CTH, confirm.ARM1),
    ("cth-uniform", confirm.CTH, confirm.UNIFORM),
)
LEAD_TIME_FAMILY = 4
_SEED = re.compile(r"/s(\d+)/")


def paired(frame: pd.DataFrame, treat: str, control: str) -> pd.Series:
    pivot = frame.pivot(index="episode_id", columns="arm", values="net")
    diff = pivot[treat] - pivot[control]
    if diff.isna().any():
        raise ValueError(f"{treat} - {control}: unpaired episodes")
    return diff


def clusters_of(frame: pd.DataFrame, index: pd.Index) -> pd.Series:
    return frame.drop_duplicates("episode_id").set_index("episode_id")["cluster"].reindex(index)


def mean_interval(values: pd.Series, clusters: pd.Series) -> dict:
    lo, hi = cluster_bootstrap(values, clusters, resamples=confirm.RESAMPLES, seed=confirm.SEED)
    return {
        "n": len(values),
        "clusters": int(clusters.nunique()),
        "mean": float(values.mean()),
        "b": [lo, hi],
    }


def ratio_interval(numerator: pd.Series, denominator: pd.Series, clusters: pd.Series) -> dict:
    """``mean(numerator) / mean(denominator)`` with a percentile interval from resampling whole
    clusters (the same draws as ``cluster_bootstrap``: groups in sorted cluster order)."""
    num = numerator.groupby(clusters.values).sum().to_numpy(dtype=float)
    den = denominator.groupby(clusters.values).sum().to_numpy(dtype=float)
    rng = np.random.default_rng(confirm.SEED)
    draws = np.empty(confirm.RESAMPLES)
    for index in range(confirm.RESAMPLES):
        chosen = rng.integers(0, len(num), size=len(num))
        draws[index] = num[chosen].sum() / den[chosen].sum()
    lo, hi = np.quantile(draws, [0.025, 0.975])
    return {"share": float(num.sum() / den.sum()), "b": [float(lo), float(hi)]}


def across_ratios(model: str) -> dict:
    low = confirm.episode_frame(run_name("low_margin", model))
    high = confirm.episode_frame(run_name("high_margin", model))
    p_low = FAMILIES["low_margin"]["profit"]
    p_high = FAMILIES["high_margin"]["profit"]
    out = {}
    for name, treat, control in CONTRASTS:
        c_low, c_high = paired(low, treat, control), paired(high, treat, control)
        if set(c_low.index) != set(c_high.index):
            raise ValueError(f"{model}: the two ratios' runs have different episodes")
        c_low = c_low.reindex(c_high.index)
        clusters = clusters_of(high, c_high.index)
        out[name] = {
            "per_unit_of_p": mean_interval(c_high / p_high - c_low / p_low, clusters),
            "currency": mean_interval(c_high - c_low, clusters),
        }
    return out


def share_of_arm1_net(frame: pd.DataFrame) -> dict:
    arm1 = frame[frame.arm == confirm.ARM1].set_index("episode_id")["net"]
    out = {"arm1_net_mean": float(arm1.mean())}
    for name, treat, control in CONTRASTS:
        diff = paired(frame, treat, control)
        out[name] = ratio_interval(diff, arm1.reindex(diff.index), clusters_of(frame, diff.index))
    return out


def null_safety_scaled(frame: pd.DataFrame, profit: float) -> dict:
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    null = confirm.contrast(frame, confirm.CTH, confirm.ARM1, "net", mask=meta["is_null"])
    margin = confirm.NULL_MARGIN * profit / 4.0
    return {**null, "margin": margin, "non_inferior": bool(null["b"][0] > margin)}


def unit_of(episode_id: str):
    seed = int(_SEED.search(episode_id).group(1))
    family, rest = divmod(seed, FAMILY_STRIDE)
    return fresh_unit(family, rest % 100_000, base=rest - rest % 100_000)


def true_shift(episode_id: str) -> int:
    params = unit_of(episode_id).params
    return int(params.disrupted_lead_time - params.baseline_lead_time)


def by_shift(frame: pd.DataFrame) -> dict:
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    shocked = meta[(meta.fam == LEAD_TIME_FAMILY) & ~meta.is_null]
    diff = paired(frame, confirm.CTH, confirm.ARM1).reindex(shocked.index)
    shift = pd.Series({e: true_shift(e) for e in shocked.index})
    return {
        str(s): {"episodes": int((shift == s).sum()), "cth-arm1": float(diff[shift == s].mean())}
        for s in sorted(shift.unique())
    }


def stratum(run: str, frame: pd.DataFrame) -> dict:
    """The noisy-lead stratum, descriptively: hedge - arm 1 per unit and per condition on the
    shocked episodes, the two-period units' share of the total gain, and exposure and null
    safety per baseline lead (two silent and two false-alert twins per baseline)."""
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    diff = paired(frame, confirm.CTH, confirm.ARM1)
    shocked = meta.index[~meta.is_null]
    units = {e: unit_of(e) for e in meta.index}
    by_unit = {}
    for e in shocked:
        u = units[e]
        entry = by_unit.setdefault(
            str(u.index),
            {
                "baseline_lead": int(u.params.baseline_lead_time),
                "shift": true_shift(e),
                "sum": 0.0,
                "episodes": 0,
            },
        )
        entry["sum"] += float(diff[e])
        entry["episodes"] += 1
    for entry in by_unit.values():
        entry["cth-arm1"] = entry.pop("sum") / entry["episodes"]
    total = float(diff.reindex(shocked).sum())
    two = float(sum(diff[e] for e in shocked if true_shift(e) == 2))
    by_condition = {
        str(c): float(diff.reindex(meta.index[~meta.is_null & (meta.condition == c)]).mean())
        for c in sorted(meta.loc[shocked, "condition"].unique())
    }
    log_path = confirm.OUT / run / "cth_log.jsonl.gz"
    mass = pd.DataFrame(confirm._jsonl_gz(log_path)).groupby(["arm_id", "episode_id"]).shock_mass
    mass = mass.sum()
    nulls = meta.index[meta.is_null]
    per_baseline = {}
    for lead in (1, 2):
        ids = [e for e in nulls if units[e].params.baseline_lead_time == lead]
        per_baseline[str(lead)] = {
            "null_episodes": len(ids),
            "null_cth_minus_arm1": float(diff.reindex(ids).mean()),
            "null_exposure": {
                arm: float(mass.reindex([(arm, e) for e in ids]).fillna(0.0).mean())
                for arm in (confirm.CTH, confirm.CTH_LLM, confirm.UNIFORM)
            },
        }
    return {
        "by_unit": by_unit,
        "shift2_share_of_gain": two / total if total else None,
        "by_condition": by_condition,
        "per_baseline": per_baseline,
    }


def readout(root: Path, models=MODELS) -> dict:
    out: dict = {
        "analysis_class": "exploratory; registered secondaries, no multiplicity claim",
        "registered_in": "analysis/commitment/PLAN.md, stage D (amendments DA3 and DA4)",
        "models": list(models),
        "across_ratios": {},
        "runs": {},
    }
    with mock.patch.object(confirm, "OUT", root):
        for model in models:
            out["across_ratios"][model] = across_ratios(model)
            for family, spec in FAMILIES.items():
                run = run_name(family, model)
                frame = confirm.episode_frame(run)
                out["runs"][run] = {
                    "profit": spec["profit"],
                    "share_of_arm1_net": share_of_arm1_net(frame),
                    "null_safety_scaled": null_safety_scaled(frame, spec["profit"]),
                    "by_shift": by_shift(frame),
                }
                if spec["pool"] == "stochastic":
                    out["runs"][run]["stratum"] = stratum(run, frame)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.readout_d")
    ap.add_argument("--out-root", type=Path, default=confirm.OUT)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    args = ap.parse_args(argv)
    report = readout(args.out_root, tuple(args.models))
    path = args.out or args.out_root / "readout_d.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for model, block in report["across_ratios"].items():
        for name, c in block.items():
            u = c["per_unit_of_p"]
            print(
                f"{model:18s} {name:12s} per unit of p {u['mean']:+8.2f} "
                f"[{u['b'][0]:.2f}, {u['b'][1]:.2f}]"
            )
    for run, block in report["runs"].items():
        s = block["share_of_arm1_net"]
        print(
            f"{run:24s} share cth-arm1 {s['cth-arm1']['share']:+.4f} "
            f"[{s['cth-arm1']['b'][0]:+.4f}, {s['cth-arm1']['b'][1]:+.4f}] "
            f"by shift {block['by_shift']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
