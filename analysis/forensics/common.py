"""Shared loaders and interval helpers for the kill-trigger forensics.

Exploratory only. Every frame built here carries ``analysis_class = "exploratory"`` and is read
from the stored pilot artefacts (``reports/pilot_records.jsonl``, ``reports/pilot_truth.jsonl``),
never from a re-run of Gate 3.

Aggregation-unit doctrine (``docs/implementation/07-evaluation-and-prereg.md``): the four
information conditions of a seed are paired replays of one independent unit. Intervals here
therefore resample **seed clusters** (``split/f<family>/s<seed>``), never episodes. The pilot's
null controls are the unshocked twins of family-1/2 seeds, so they join their source seed's
cluster rather than counting as extra independent units.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
RECORDS = REPO / "reports" / "pilot_records.jsonl"
TRUTH = REPO / "reports" / "pilot_truth.jsonl"
OUT = REPO / "analysis" / "forensics" / "out"

ANALYSIS_CLASS = "exploratory"
PROVENANCE = (
    "scripted transport (scripted-fake-7b, one fixed demand_up/medium ShockSpec payload) and "
    "demo alerts, through the real frozen arms, parser, compiler, verifier, and ledger"
)
BOOTSTRAP_SEED = 20260927
BOOTSTRAP_RESAMPLES = 10_000

ARM1 = "arm1_capped_base_stock"
ARM8 = "arm8_spec_immediate"
ARM9 = "arm9_spec_heuristic_rollback"
ARM10 = "arm10_spec_eprocess"
CTRL = "ctrl_cusum_to_compiler"
ORACLE = "oracle_shockspec_headroom"

FAMILY_KEY = {
    1: "demand_level:demand_up",
    2: "demand_level:demand_down",
    3: "temporary_pulse",
    4: "lead_time_shift",
    5: "shipment_loss",
    6: "compound",
}
"""Generator family number -> the frozen evaluator's six headroom keys (collie/eval/pilot.py)."""

_EPISODE = re.compile(
    r"^(?P<split>dev|cal)/f(?P<fam>\d)/s(?P<seed>\d+)/(?P<cond>[a-z_]+?)(?P<twin>__twin)?$"
)


def parse_episode_id(episode_id: str) -> dict[str, object]:
    """``dev/f1/s1050000/no_alert`` (shocked) or ``..._accurate__twin`` (a null control)."""
    match = _EPISODE.match(episode_id)
    if match is None:
        raise ValueError(f"unrecognised pilot episode id {episode_id!r}")
    parts = match.groupdict()
    return {
        "split": parts["split"],
        "fam": int(parts["fam"]),
        "seed": int(parts["seed"]),
        "rollout_condition": parts["cond"],
        "is_null": parts["twin"] is not None,
        "cluster": f"{parts['split']}/f{parts['fam']}/s{parts['seed']}",
    }


def load_raw() -> list[dict]:
    """Every stored ``EpisodeResult`` as a plain dict, in file order."""
    with RECORDS.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_truth() -> dict[str, dict]:
    with TRUTH.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {row["episode_id"]: row for row in rows}


def episode_frame(raw: Sequence[dict]) -> pd.DataFrame:
    """One row per (episode, arm) with totals, net reward, and the seed-cluster id."""
    rows = []
    for record in raw:
        meta = parse_episode_id(record["episode_id"])
        periods = record["records"]
        rows.append(
            {
                "episode_id": record["episode_id"],
                "arm": record["arm_id"],
                "unit": record["independent_unit_id"],
                "condition": record["information_condition"],
                "family_label": record["family"],
                **meta,
                "key": "null" if meta["is_null"] else FAMILY_KEY[int(meta["fam"])],
                "profit": float(record["total_profit"]),
                "holding": float(record["total_holding_cost"]),
                "reward": float(record["total_reward"]),
                "lost": float(record["total_lost_sales"]),
                "sold": float(record["total_sold"]),
                "demand": float(record["total_demand"]),
                "n_calls": len(record["calls"]),
                "n_active": sum(1 for p in periods if p.get("active_spec_id")),
                "analysis_class": ANALYSIS_CLASS,
            }
        )
    frame = pd.DataFrame(rows)
    frame["fill"] = np.where(frame["demand"] > 0, frame["sold"] / frame["demand"], 1.0)
    return frame


def periods_by(raw: Sequence[dict], arms: Sequence[str]) -> dict[tuple[str, str], list[dict]]:
    """Per-period records for the requested arms, keyed by (episode_id, arm)."""
    wanted = set(arms)
    return {(r["episode_id"], r["arm_id"]): r["records"] for r in raw if r["arm_id"] in wanted}


def paired(frame: pd.DataFrame, treatment: str, control: str, column: str) -> pd.DataFrame:
    """Per-episode treatment-minus-control differences, with cluster and stratum columns."""
    pivot = frame.pivot(index="episode_id", columns="arm", values=column)
    meta = frame.drop_duplicates("episode_id").set_index("episode_id")[
        ["cluster", "key", "fam", "condition", "is_null", "split"]
    ]
    out = meta.join((pivot[treatment] - pivot[control]).rename("diff"), how="inner")
    return out.dropna(subset=["diff"])


def cluster_bootstrap(
    values: pd.Series,
    clusters: pd.Series,
    *,
    statistic: Callable[[np.ndarray], float] = np.mean,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile interval resampling whole seed clusters with replacement.

    The statistic is recomputed on the pooled rows of the resampled clusters, so the estimand is
    the same row-weighted mean the registered interval reports; only the unit of resampling
    changes (seed, not episode-condition).
    """
    groups = [np.asarray(v, dtype=float) for _, v in values.groupby(clusters.values)]
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples)
    for index in range(resamples):
        chosen = rng.integers(0, len(groups), size=len(groups))
        draws[index] = statistic(np.concatenate([groups[i] for i in chosen]))
    low, high = np.quantile(draws, [0.025, 0.975])
    return float(low), float(high)


def normal_interval(values: Sequence[float], z: float = 1.959963984540054) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    half = z * float(np.std(arr, ddof=1)) / np.sqrt(len(arr))
    return float(arr.mean() - half), float(arr.mean() + half)


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return float(centre - half), float(centre + half)


def write_json(name: str, payload: dict) -> Path:
    """Write one output under ``analysis/forensics/out``, stamped exploratory."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    body = {"analysis_class": ANALYSIS_CLASS, "provenance": PROVENANCE, **payload}
    path.write_text(json.dumps(body, indent=2, sort_keys=True, default=float) + "\n")
    return path
