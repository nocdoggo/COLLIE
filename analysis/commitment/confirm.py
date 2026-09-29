"""Stage C evaluation: the registered contrasts on the fresh-seed runs. Committed before the runs.

For every run named on the command line (``out/<run>/``: records, truth, alerts, proposals,
spend log and the certify-then-hedge sidecar ``cth_log.jsonl.gz``):

* paired per-episode differences for the registered contrasts, on net reward (primary endpoint)
  and gross profit (the frozen endpoint, reported alongside), averaged over all episodes;
* the seed-cluster bootstrap 95% interval (clusters are ``split/f<family>/s<seed>``; a unit's four
  conditions and its twin share one; 10,000 draws, seed 20260927) and a one-sided cluster
  sign-flip p-value (100,000 Monte Carlo draws, seed 20260927) on the cluster means;
* Holm's step-down over the primary family (``cth - arm10`` and ``cth - arm1``, net, on the two
  primary endpoints), one-sided at 0.05;
* null safety: ``cth - arm1`` net on the null twins against the non-inferiority margin -25 per
  episode (the lower bootstrap bound must exceed it), and exposure = mean over null twins of the
  summed per-period shock mass;
* net ``cth - arm1`` by family and condition, first-proposal perception (family and direction
  right, abstentions) for the model arms, and provider cost.

Usage::

    uv run python -m analysis.commitment.confirm --runs fresh-gemini-3.8-flash fresh-grok-4.20 \\
        [--secondary fresh-...] [--out out/confirm.json]
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.forensics.common import cluster_bootstrap, parse_episode_id

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "commitment" / "out"
SEED = 20260927
RESAMPLES = 10_000
FLIPS = 100_000
NULL_MARGIN = -25.0
CTH, CTH_LLM, UNIFORM = "arm12_cth", "arm12b_cth_llm", "ctrl_cth_uniform"
ARM1, ARM8, ARM10 = "arm1_capped_base_stock", "arm8_spec_immediate", "arm10_spec_eprocess"
CONTRASTS = (
    ("cth-arm10", CTH, ARM10, "primary"),
    ("cth-arm1", CTH, ARM1, "primary"),
    ("cth-arm8", CTH, ARM8, "secondary"),
    ("cth-uniform", CTH, UNIFORM, "secondary"),
    ("cth_llm-uniform", CTH_LLM, UNIFORM, "secondary"),
    ("uniform-arm1", UNIFORM, ARM1, "secondary"),
    ("arm10-arm1", ARM10, ARM1, "secondary"),
    ("arm8-arm1", ARM8, ARM1, "secondary"),
)


def _jsonl_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _jsonl(path: Path) -> list[dict]:
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def episode_frame(run: str) -> pd.DataFrame:
    rows = []
    for r in _jsonl_gz(OUT / run / "records.jsonl.gz"):
        meta = parse_episode_id(r["episode_id"])
        rows.append(
            {
                "episode_id": r["episode_id"],
                "arm": r["arm_id"],
                "net": float(r["total_reward"]),
                "gross": float(r["total_profit"]),
                "cluster": meta["cluster"],
                "fam": 0 if meta["is_null"] else int(meta["fam"]),
                "is_null": bool(meta["is_null"]),
                "condition": r.get("information_condition"),
            }
        )
    return pd.DataFrame(rows)


def sign_flip_p(values: pd.Series, clusters: pd.Series) -> float:
    """One-sided p for mean > 0 from random sign flips of whole-cluster sums."""
    sums = values.groupby(clusters.values).sum().to_numpy()
    n = len(values)
    observed = sums.sum() / n
    rng = np.random.default_rng(SEED)
    signs = rng.choice((-1.0, 1.0), size=(FLIPS, len(sums)))
    draws = signs @ sums / n
    return float((1 + np.sum(draws >= observed - 1e-12)) / (FLIPS + 1))


def contrast(frame: pd.DataFrame, treat: str, control: str, endpoint: str, mask=None) -> dict:
    pivot = frame.pivot(index="episode_id", columns="arm", values=endpoint)
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    if treat not in pivot or control not in pivot:
        return {}
    diff = (pivot[treat] - pivot[control]).dropna()
    if mask is not None:
        diff = diff[mask.reindex(diff.index).fillna(False).astype(bool)]
    clusters = meta["cluster"].reindex(diff.index)
    lo, hi = cluster_bootstrap(diff, clusters, resamples=RESAMPLES, seed=SEED)
    return {
        "n": len(diff),
        "clusters": int(clusters.nunique()),
        "mean": float(diff.mean()),
        "b": [lo, hi],
        "p_one_sided": sign_flip_p(diff, clusters),
    }


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    order = sorted(pvalues, key=pvalues.get)
    out, stop = {}, False
    for rank, key in enumerate(order):
        threshold = alpha / (len(order) - rank)
        reject = (not stop) and pvalues[key] <= threshold
        stop = stop or not reject
        out[key] = {"p": pvalues[key], "threshold": threshold, "reject": reject}
    return out


def exposure(run: str, frame: pd.DataFrame) -> dict:
    path = OUT / run / "cth_log.jsonl.gz"
    if not path.is_file():
        return {}
    log = pd.DataFrame(_jsonl_gz(path))
    nulls = set(frame.loc[frame.is_null, "episode_id"])
    out = {}
    for arm, part in log.groupby("arm_id"):
        per_episode = part.groupby("episode_id").shock_mass.sum()
        null_part = per_episode[per_episode.index.isin(nulls)]
        maxima = part[part.episode_id.isin(nulls)].groupby("episode_id").shock_mass.max()
        out[arm] = {
            "null_exposure_mean": float(null_part.mean()) if len(null_part) else None,
            "null_max_mass": float(maxima.max()) if len(maxima) else None,
            "null_episodes_mass_ge_half": int((maxima >= 0.5).sum()),
            "shocked_exposure_mean": float(per_episode[~per_episode.index.isin(nulls)].mean()),
        }
    return out


def perception(run: str) -> dict:
    truth = {r["episode_id"]: r for r in _jsonl(OUT / run / "truth.jsonl")}
    path = OUT / run / "proposals.jsonl"
    if not path.is_file():
        return {}
    rows = _jsonl(path)
    first: dict[tuple[str, str], dict] = {}
    for r in sorted(rows, key=lambda r: (r["episode_id"], r["period"], r["attempt_index"])):
        key = (r["arm_id"], r["episode_id"])
        if key in first and r["period"] != first[key]["period"]:
            continue
        first[key] = r  # the last attempt of the first proposal period
    out = {}
    for arm in sorted({a for a, _ in first}):
        shocked = [(e, r) for (a, e), r in first.items() if a == arm and e in truth]
        right = abstain = fail = 0
        for e, r in shocked:
            if not r["parsed"]:
                fail += 1
            elif r["abstention"]:
                abstain += 1
            elif (
                r["payload"]["shock_family"] == truth[e]["family"]
                and r["payload"]["direction"] == truth[e]["direction"]
            ):
                right += 1
        out[arm] = {
            "called_shocked": len(shocked),
            "family_right": right,
            "abstain": abstain,
            "parse_fail": fail,
        }
    return out


def cost(run: str) -> dict:
    path = OUT / run / "spend_log.jsonl"
    if not path.is_file():
        return {}
    calls = [r for r in _jsonl(path) if r["event"] == "call"]
    return {"provider_calls": len(calls), "usd": float(sum(r["usd"] for r in calls))}


def evaluate_run(run: str) -> dict:
    frame = episode_frame(run)
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")
    out = {"episodes": int(meta.shape[0]), "clusters": int(meta.cluster.nunique())}
    out["contrasts"] = {
        f"{name}|{endpoint}": {"role": role, **contrast(frame, t, c, endpoint)}
        for name, t, c, role in CONTRASTS
        for endpoint in ("net", "gross")
    }
    null_mask = meta["is_null"]
    null = contrast(frame, CTH, ARM1, "net", mask=null_mask)
    out["null_safety"] = {
        **null,
        "margin": NULL_MARGIN,
        "non_inferior": bool(null and null["b"][0] > NULL_MARGIN),
    }
    out["by_family_net_cth_minus_arm1"] = {
        str(f): contrast(frame, CTH, ARM1, "net", mask=(meta["fam"] == f))["mean"]
        for f in sorted(meta["fam"].unique())
    }
    out["exposure"] = exposure(run, frame)
    out["perception"] = perception(run)
    out["cost"] = cost(run)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.confirm")
    ap.add_argument("--runs", nargs="+", required=True, help="the primary-endpoint runs")
    ap.add_argument("--secondary", nargs="*", default=[], help="model-scale runs (descriptive)")
    ap.add_argument("--out", type=Path, default=OUT / "confirm.json")
    args = ap.parse_args(argv)
    runs = {name: evaluate_run(name) for name in [*args.runs, *args.secondary]}
    pvalues = {
        f"{name}:{c}": runs[name]["contrasts"][f"{c}|net"]["p_one_sided"]
        for name in args.runs
        for c in ("cth-arm10", "cth-arm1")
    }
    result = {
        "analysis_class": "exploratory",
        "registered_in": "analysis/commitment/PLAN.md, stage C",
        "primary_runs": args.runs,
        "secondary_runs": args.secondary,
        "holm_primary": holm(pvalues),
        "runs": runs,
    }
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    for name, r in runs.items():
        c = r["contrasts"]
        print(
            f"{name:34s} cth-arm10 {c['cth-arm10|net']['mean']:+7.1f} {np.round(c['cth-arm10|net']['b'], 1)} "
            f"| cth-arm1 {c['cth-arm1|net']['mean']:+7.1f} {np.round(c['cth-arm1|net']['b'], 1)} "
            f"| cth-uniform {c['cth-uniform|net']['mean']:+6.1f} | null ok {r['null_safety']['non_inferior']}"
        )
    print(json.dumps(result["holm_primary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
