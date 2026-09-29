"""Stage B development harness: certify-then-hedge on the 120 spent pilot episodes, no API calls.

Each variant of :class:`analysis.commitment.cth.CertifyThenHedgeArm` runs through the real
``EpisodeRunner`` on the registered pilot layout with module 03's bank alerts and the frozen
trigger. Where the arm would consult the model it replays arm 10's cached answer for the same
episode and period from a committed bank (``proposals.jsonl``); the content-free variant
(``lam = 1``) consults nothing. Outcomes are paired by episode with the bank's stored arm 1, 8
and 10 records and summarised with the seed-cluster bootstrap (24 clusters).

Development only: every number here is post hoc on spent episodes and supports no claim.

Usage::

    uv run python -m analysis.commitment.dev [--banks ...] [--variants ...] [--workers 12]
"""

from __future__ import annotations

import argparse
import gzip
import json
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.commitment.cth import CertifyThenHedgeArm
from analysis.forensics.common import cluster_bootstrap, parse_episode_id
from analysis.real_content_pilot.alerts import pilot_bank_alerts
from collie.contracts import AnalysisClass
from collie.sim.runner import EpisodeRunner
from collie.trigger.demo import build_wrapped
from tools.run_arms import pilot_instances

REPO = Path(__file__).resolve().parents[2]
BANK_ROOTS = {
    "scripted-bank": REPO / "analysis" / "real_content_pilot" / "out",
    "gemini-bank": REPO / "analysis" / "real_content_pilot" / "out",
    "grok-bank": REPO / "analysis" / "real_content_pilot" / "out",
}
LADDER_ROOT = REPO / "analysis" / "commitment" / "out"
DEV_OUT = REPO / "analysis" / "commitment" / "out" / "dev"
VARIANTS = {
    "cth": {"lam": 0.25},
    "cth_llm": {"lam": 0.0},
    "cth_uniform": {"lam": 1.0},
    "cth_map": {"lam": 0.25, "scheme": "map"},
    "cth_linear": {"lam": 0.25, "scheme": "linear"},
}
ARM1, ARM8, ARM10 = "arm1_capped_base_stock", "arm8_spec_immediate", "arm10_spec_eprocess"
RESAMPLES = 4000

_INSTANCES = None
_ALERTS = None


def bank_dir(bank: str) -> Path:
    root = BANK_ROOTS.get(bank, LADDER_ROOT)
    return root / bank


def load_replay(bank: str) -> dict[str, dict[int, dict | None]]:
    """Arm 10's final-attempt answer per (episode, period); None where it failed to parse."""
    rows = [json.loads(line) for line in (bank_dir(bank) / "proposals.jsonl").open()]
    out: dict[str, dict[int, dict | None]] = defaultdict(dict)
    for row in sorted(rows, key=lambda r: (r["episode_id"], r["period"], r["attempt_index"])):
        if row["arm_id"] != ARM10:
            continue
        out[row["episode_id"]][row["period"]] = row["payload"] if row["parsed"] else None
    return out


def load_stored(bank: str) -> pd.DataFrame:
    rows = []
    with gzip.open(bank_dir(bank) / "records.jsonl.gz", "rt") as body:
        for line in body:
            r = json.loads(line)
            if r["arm_id"] in (ARM1, ARM8, ARM10):
                rows.append(
                    {
                        "episode_id": r["episode_id"],
                        "arm": r["arm_id"],
                        "net": float(r["total_reward"]),
                        "gross": float(r["total_profit"]),
                    }
                )
    return pd.DataFrame(rows)


def _init() -> None:
    global _INSTANCES, _ALERTS
    tmp = tempfile.mkdtemp(prefix="cth_dev_")
    instances, _ = pilot_instances(Path(tmp), 120)
    _INSTANCES = instances
    _ALERTS = pilot_bank_alerts([i for i, _ in instances])


def run_variant(task: tuple[str, str]) -> list[dict]:
    bank, variant = task
    if _INSTANCES is None:
        _init()
    replay = load_replay(bank) if VARIANTS[variant]["lam"] < 1.0 else {}
    out = []
    for instance, seed in _INSTANCES:
        spec = instance.spec
        channel = _ALERTS[spec.episode_id]
        arm = CertifyThenHedgeArm(
            promised_lead_time=spec.promised_lead_time,
            horizon=spec.horizon,
            train_demand=spec.train_demand,
            order_cap=spec.order_cap,
            trigger=build_wrapped("alert_or_detector", spec.horizon, 0, seed),
            replay=replay.get(spec.episode_id, {}),
            arm_id=f"dev_{variant}",
            **VARIANTS[variant],
        )
        result = (
            EpisodeRunner(
                instance,
                alerts=channel.alerts,
                template_ids=channel.template_ids,
                analysis_class=AnalysisClass.EXPLORATORY,
                check_controller_isolation=True,
            )
            .run(arm)
            .result
        )
        masses = [m for _, m, _ in arm.log]
        out.append(
            {
                "bank": bank,
                "variant": variant,
                "episode_id": spec.episode_id,
                "net": float(result.total_reward),
                "gross": float(result.total_profit),
                "exposure": float(sum(masses)),
                "max_mass": float(max(masses) if masses else 0.0),
            }
        )
    return out


def _ci(diff: pd.Series, clusters: pd.Series) -> dict:
    lo, hi = cluster_bootstrap(diff, clusters, resamples=RESAMPLES)
    return {"mean": round(float(diff.mean()), 1), "b": [round(lo, 1), round(hi, 1)]}


def summarise(frame: pd.DataFrame, bank: str, variant: str) -> dict:
    stored = load_stored(bank).pivot(index="episode_id", columns="arm")
    ours = frame.set_index("episode_id")
    meta = pd.DataFrame([parse_episode_id(e) | {"episode_id": e} for e in ours.index]).set_index(
        "episode_id"
    )
    out = {"bank": bank, "variant": variant}
    for arm, label in ((ARM1, "arm1"), (ARM10, "arm10"), (ARM8, "arm8")):
        for endpoint in ("net", "gross"):
            diff = ours[endpoint] - stored[(endpoint, arm)].reindex(ours.index)
            out[f"vs_{label}|{endpoint}"] = _ci(diff, meta["cluster"])
    diff = ours["net"] - stored[("net", ARM1)].reindex(ours.index)
    nulls = meta["is_null"]
    out["null_net_vs_arm1"] = round(float(diff[nulls].mean()), 1)
    out["null_worst_vs_arm1"] = round(float(diff[nulls].min()), 1)
    out["null_exposure"] = round(float(ours.loc[nulls, "exposure"].mean()), 3)
    out["null_max_mass"] = round(float(ours.loc[nulls, "max_mass"].max()), 3)
    fam = meta["fam"].where(~nulls, other=0)
    out["by_family_net_vs_arm1"] = {
        str(int(f)): round(float(diff[fam == f].mean()), 1) for f in sorted(fam.unique())
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.dev")
    ap.add_argument("--banks", nargs="+", default=["scripted-bank", "gemini-bank", "grok-bank"])
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--tag", default="dev")
    args = ap.parse_args(argv)
    tasks = []
    for variant in args.variants:
        if VARIANTS[variant]["lam"] >= 1.0:
            tasks.append((args.banks[0], variant))  # content-free: identical on every bank
        else:
            tasks.extend((bank, variant) for bank in args.banks)
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init) as pool:
        rows = [row for chunk in pool.map(run_variant, tasks) for row in chunk]
    frame = pd.DataFrame(rows)
    summaries = []
    for (bank, variant), part in frame.groupby(["bank", "variant"]):
        banks = args.banks if VARIANTS[variant]["lam"] >= 1.0 else [bank]
        for b in banks:
            summaries.append(summarise(part.drop(columns=["bank", "variant"]), b, variant))
    DEV_OUT.mkdir(parents=True, exist_ok=True)
    (DEV_OUT / f"{args.tag}.json").write_text(
        json.dumps({"summaries": summaries, "episodes": rows}, indent=1, sort_keys=True) + "\n"
    )
    for s in summaries:
        print(
            f"{s['bank']:30s} {s['variant']:12s} vs arm1 net {s['vs_arm1|net']['mean']:+7.1f} "
            f"{s['vs_arm1|net']['b']} | vs arm10 net {s['vs_arm10|net']['mean']:+7.1f} "
            f"{s['vs_arm10|net']['b']} | vs arm8 net {s['vs_arm8|net']['mean']:+8.1f} | "
            f"gross vs arm1 {s['vs_arm1|gross']['mean']:+7.1f} | null {s['null_net_vs_arm1']:+.1f} "
            f"exp {s['null_exposure']:.3f}"
        )
    return 0


if __name__ == "__main__":
    np.seterr(all="ignore")
    raise SystemExit(main())
