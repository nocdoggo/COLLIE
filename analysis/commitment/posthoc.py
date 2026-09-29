"""Post-hoc readouts of the stage C runs. Written after the results were seen; decides nothing.

Every number here is computed from the committed ``out/fresh-*`` files with the registered
evaluator's own helpers (``confirm.contrast``: seed-cluster bootstrap and cluster sign-flip, same
seeds). They answer questions an independent audit of stage C raised:

* **Where the gain comes from.** Certify-then-hedge minus arm 1 by family, the share of the total
  that the lead-time family supplies, and the contrast without the lead-time units (their shocked
  episodes and their twins, so whole clusters drop).
* **Prior contact.** The primary contrasts without the six clusters of units ``i = 0``, whose
  outcomes a pre-registration structural test computed (PLAN.md, stage C amendment C3).
* **Null episodes.** Null safety split into silent and false-alert twins.
* **What the model's label buys.** Null exposure of the method against the content-free control,
  as a ratio with a seed-cluster bootstrap interval, split by twin type.
* **Endpoint sign.** Every stage C contrast on net and gross, flagged where the sign differs.

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


def _round(c: dict) -> dict:
    if not c:
        return {}
    return {
        "n": c["n"],
        "clusters": c["clusters"],
        "mean": round(c["mean"], 3),
        "b": [round(c["b"][0], 3), round(c["b"][1], 3)],
        "p_one_sided": round(c["p_one_sided"], 5),
    }


def frame_with_units(run: str) -> pd.DataFrame:
    frame = confirm.episode_frame(run)
    unit = frame["cluster"].str.extract(r"f(?P<unit_fam>\d)/s(?P<seed>\d+)$").astype(int)
    frame["unit_fam"] = unit["unit_fam"]
    frame["unit_index"] = unit["seed"] - unit["unit_fam"] * 1_000_000 - FRESH_BASE
    frame["false_alert_twin"] = frame["is_null"] & (frame["condition"] == "unreliable")
    return frame


def episode_exposure(run: str) -> pd.DataFrame:
    log = pd.DataFrame(confirm._jsonl_gz(OUT / run / "cth_log.jsonl.gz"))
    return log.groupby(["arm_id", "episode_id"]).shock_mass.sum().unstack(0)


def exposure_ratio(exp: pd.DataFrame, meta: pd.DataFrame, mask: pd.Series) -> dict:
    """Null exposure of the method over the content-free control, with a cluster bootstrap."""
    ids = mask[mask].index
    part = exp.reindex(ids).fillna(0.0)
    clusters = meta.loc[ids, "cluster"]
    num = part[confirm.CTH].groupby(clusters.values).sum()
    den = part[confirm.UNIFORM].groupby(clusters.values).sum()
    rng = np.random.default_rng(confirm.SEED)
    keys = num.index.to_numpy()
    draws = []
    for _ in range(confirm.RESAMPLES):
        pick = rng.integers(0, len(keys), len(keys))
        d = den.iloc[pick].sum()
        if d > 0:
            draws.append(num.iloc[pick].sum() / d)
    ratio = float(num.sum() / den.sum()) if den.sum() > 0 else None
    lo, hi = np.percentile(draws, [2.5, 97.5]) if draws else (None, None)
    return {
        "episodes": len(ids),
        "cth_mean": round(float(part[confirm.CTH].mean()), 3),
        "cth_llm_mean": round(float(part[confirm.CTH_LLM].mean()), 3),
        "uniform_mean": round(float(part[confirm.UNIFORM].mean()), 3),
        "cth_over_uniform": None if ratio is None else round(ratio, 3),
        "b": None if lo is None else [round(float(lo), 3), round(float(hi), 3)],
        "episodes_uniform_zero": int((part[confirm.UNIFORM] == 0).sum()),
    }


def readout(run: str) -> dict:
    frame = frame_with_units(run)
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    out: dict = {}

    pivot = frame.pivot(index="episode_id", columns="arm", values="net")
    diff = pivot[confirm.CTH] - pivot[confirm.ARM1]
    total = float(diff.sum())
    lead = float(diff[meta["fam"] == LEAD_TIME_FAMILY].sum())
    without_lead = meta["unit_fam"] != LEAD_TIME_FAMILY
    out["gain_source"] = {
        "cth_minus_arm1_total": round(total, 1),
        "lead_time_share": round(lead / total, 3) if total else None,
        "cth-arm1|net|without_lead_time_units": _round(
            confirm.contrast(frame, confirm.CTH, confirm.ARM1, "net", mask=without_lead)
        ),
        "uniform-arm1|net|without_lead_time_units": _round(
            confirm.contrast(frame, confirm.UNIFORM, confirm.ARM1, "net", mask=without_lead)
        ),
        "cth-arm10|net|without_lead_time_units": _round(
            confirm.contrast(frame, confirm.CTH, confirm.ARM10, "net", mask=without_lead)
        ),
        "by_family_net": {
            name: {
                str(f): round(float((pivot[t] - pivot[confirm.ARM1])[meta["fam"] == f].mean()), 1)
                for f in sorted(meta["fam"].unique())
            }
            for name, t in (
                ("cth-arm1", confirm.CTH),
                ("uniform-arm1", confirm.UNIFORM),
                ("arm10-arm1", confirm.ARM10),
            )
        },
    }

    untouched = meta["unit_index"] != STRUCTURAL_TEST_INDEX
    primary = {}
    for name, treat, control in (
        ("cth-arm10", confirm.CTH, confirm.ARM10),
        ("cth-arm1", confirm.CTH, confirm.ARM1),
    ):
        primary[f"{name}|net"] = _round(
            confirm.contrast(frame, treat, control, "net", mask=untouched)
        )
    out["without_structural_test_clusters"] = primary

    null = meta["is_null"]
    fa = meta["false_alert_twin"]
    out["null_cth_minus_uniform"] = _round(
        confirm.contrast(frame, confirm.CTH, confirm.UNIFORM, "net", mask=null)
    )
    out["null_safety_split"] = {
        "silent": _round(
            confirm.contrast(frame, confirm.CTH, confirm.ARM1, "net", mask=null & ~fa)
        ),
        "false_alert": _round(confirm.contrast(frame, confirm.CTH, confirm.ARM1, "net", mask=fa)),
        "silent_nonzero_episodes": int(((diff != 0) & null & ~fa).sum()),
        "worst_null_episode": round(float(diff[null].min()), 1),
    }

    exp = episode_exposure(run)
    out["null_exposure"] = {
        "all_twins": exposure_ratio(exp, meta, null),
        "false_alert_twins": exposure_ratio(exp, meta, fa),
        "silent_twins": exposure_ratio(exp, meta, null & ~fa),
    }

    signs = {}
    for name, treat, control, _role in confirm.CONTRASTS:
        piv = {
            e: frame.pivot(index="episode_id", columns="arm", values=e) for e in ("net", "gross")
        }
        means = {e: float((piv[e][treat] - piv[e][control]).mean()) for e in piv}
        signs[name] = {
            "net": round(means["net"], 1),
            "gross": round(means["gross"], 1),
            "sign_differs": bool(np.sign(means["net"]) != np.sign(means["gross"])),
        }
    out["net_vs_gross"] = signs
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.posthoc")
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--out", type=Path, default=OUT / "posthoc.json")
    args = ap.parse_args(argv)
    report = {
        "status": "post hoc: written after the stage C results were seen; decides nothing",
        "runs": {run: readout(run) for run in args.runs},
    }
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    for run, r in report["runs"].items():
        g, s, n = r["gain_source"], r["without_structural_test_clusters"], r["null_exposure"]
        print(
            f"{run}: lead-time share {g['lead_time_share']}, cth-arm1 w/o lead "
            f"{g['cth-arm1|net|without_lead_time_units']['mean']} "
            f"{g['cth-arm1|net|without_lead_time_units']['b']}; 42 clusters cth-arm10 "
            f"{s['cth-arm10|net']['mean']} p {s['cth-arm10|net']['p_one_sided']}, cth-arm1 "
            f"{s['cth-arm1|net']['mean']} p {s['cth-arm1|net']['p_one_sided']}; exposure ratio "
            f"{n['all_twins']['cth_over_uniform']} {n['all_twins']['b']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
