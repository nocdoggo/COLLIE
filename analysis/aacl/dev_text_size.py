"""DEVELOPMENT ONLY (throwaway pool, base 900000; supports no claim). Does stating the shock's size
in the alert help certify-then-hedge on this simulator?

A scripted reader stands in for a model reading an informative alert: at each trigger firing it
names the true hypothesis (family and direction; shipment losses and compounds are outside the
hypothesis set, so it abstains there, and on silent twins) and states the true size bin with
probability ``q_read``, another bin otherwise; on false-alert twins it names a demand rise
(medium), as the live models mostly did. Two hedges read it:

* ``method``: the registered rule (``lam = 0.25``); the stated size is ignored, sizes come from
  the data under a uniform prior over the candidate grid;
* ``text_sized``: the same, except that for the named hypothesis the size candidates get prior
  ``size_q`` on the stated bin and ``(1 - size_q)`` spread over the others.

Size bins: demand level and pulse by the oracle's provisional ``|m - 1|`` cut points (1.25 and
0.75 low, 1.5 and 0.6 medium, 2.0 high); lead-time offsets 1, 2, 3 as low, medium, high (the
true shift is 2 from a baseline lead of 1 and 1 from 2).

Usage (from the repository root)::

    uv run python -m analysis.aacl.dev_text_size [--profits 4 19] [--out <scratch>/x.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import analysis.commitment.arms  # noqa: F401  (registers the confirm arm set)
from analysis.commitment import confirm
from analysis.commitment.cth import CANONICAL, UNIFORM_WINDOW, CertifyThenHedgeArm
from analysis.commitment.episodes import THROWAWAY_BASE, build_layout, fresh_unit, layout_alerts
from analysis.commitment.registry import ARM_SETS
from collie.arms.oracle import _magnitude_bin
from collie.contracts import AnalysisClass, MagnitudeBin
from collie.data.families.demand import MAGNITUDE_SETS
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from collie.trigger.demo import build_wrapped
from tools.run_arms import _DemoTransport

BINS = (MagnitudeBin.LOW, MagnitudeBin.MEDIUM, MagnitudeBin.HIGH)
LEAD_BIN = {1: MagnitudeBin.LOW, 2: MagnitudeBin.MEDIUM, 3: MagnitudeBin.HIGH}
KEY_OF_FAMILY = {1: "demand_up", 2: "demand_down", 3: "pulse_up", 4: "lead_time"}
MAGS = {
    "demand_up": MAGNITUDE_SETS[1],
    "demand_down": MAGNITUDE_SETS[2],
    "pulse_up": MAGNITUDE_SETS[3],
}


def truth_of(instance) -> tuple[str | None, MagnitudeBin | None]:
    incident = instance.incident
    if incident is None:
        return None, None
    family = int(instance.spec.episode_id.split("/f")[1][0])
    key = KEY_OF_FAMILY.get(family)
    if key is None:
        return None, None
    if key == "lead_time":
        seed = int(instance.spec.episode_id.split("/s")[1].split("/")[0])
        rest = seed % 1_000_000
        params = fresh_unit(4, rest % 100_000, base=rest - rest % 100_000).params
        return key, LEAD_BIN[int(params.disrupted_lead_time - params.baseline_lead_time)]
    return key, _magnitude_bin(float(incident.magnitude))


def payload(key: str, size: MagnitudeBin) -> dict:
    c = CANONICAL[key]
    return {
        "shock_family": c["shock_family"].value,
        "target_stream": c["target_stream"].value,
        "direction": c["direction"].value,
        "onset_window": list(UNIFORM_WINDOW),
        "magnitude_bin": size.value,
        "persistence": c["persistence"].value,
        "duration_bin": c["duration_bin"].value,
        "evidence_refs": [],
        "prospective_signature": c["prospective_signature"],
    }


def reader(episode_id: str, key, size, q_read: float, false_alert: bool):
    def read(period: int):
        if key is None:
            return payload("demand_up", MagnitudeBin.MEDIUM) if false_alert else None
        h = hashlib.sha256(f"{episode_id}|{period}|{q_read}".encode()).digest()
        rng = np.random.default_rng(int.from_bytes(h[:8], "little"))
        if rng.random() < q_read:
            return payload(key, size)
        return payload(key, [b for b in BINS if b is not size][int(rng.integers(0, 2))])

    return read


@dataclass(slots=True)
class TextSizedHedge(CertifyThenHedgeArm):
    read: object = None
    size_q: float = 0.0
    _stated: dict = field(default_factory=dict)

    def _ask(self, obs):
        self.replay = {obs.period: self.read(obs.period)}
        spec = CertifyThenHedgeArm._ask(self, obs)
        if spec is not None and not spec.is_abstention:
            self._stated[self._firings] = spec.magnitude_bin
        return spec

    def _weights(self, h, sizes, bin_of):
        stated = self._stated.get(h.firing) if h.from_llm else None
        if stated is None or self.size_q <= 0.0 or all(bin_of(s) != stated for s in sizes):
            return None
        rest = (1.0 - self.size_q) / (len(sizes) - 1)
        return {s: (self.size_q if bin_of(s) == stated else rest) * len(sizes) for s in sizes}

    def _within_demand(self, h, t):
        cands = CertifyThenHedgeArm._within_demand(self, h, t)
        w = self._weights(h, MAGS[h.key], _magnitude_bin)
        if w is None:
            return cands
        out = [(p * w[params[0]], params) for p, params in cands]
        z = sum(p for p, _ in out)
        return [(p / z, params) for p, params in out]

    def _lt_posterior(self, h, t, lead, it_now):
        cands = CertifyThenHedgeArm._lt_posterior(self, h, t, lead, it_now)
        w = self._weights(h, (1, 2, 3), LEAD_BIN.get)
        if w is None:
            return cands
        out = [(p * w[delta], delta, s) for p, delta, s in cands]
        z = sum(p for p, _, _ in out)
        return [(p / z, delta, s) for p, delta, s in out]


def run_task(task: tuple[float, float, float, str]) -> list[dict]:
    profit, q_read, size_q, name = task
    rows = []
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as cache:
        layout = build_layout(Path(tmp), 8, profit=profit, base=THROWAWAY_BASE)
        alerts = layout_alerts(layout)
        ledger = CallLedger()
        metered = MeteredClient(
            transport=_DemoTransport(),
            endpoint=scripted_endpoint(),
            cache=DiskCache(Path(cache)),
            ledger=ledger,
        )
        for instance, seed in layout.instances:
            spec = instance.spec
            channel = alerts[spec.episode_id]
            if name == "arm1":
                arms = [
                    (a, c, iso)
                    for a, c, iso in ARM_SETS["confirm"](
                        instance, seed, metered=metered, ledger=ledger, sink=lambda r, t: None
                    )
                    if a == confirm.ARM1
                ]
                _, controller, iso = arms[0]
            else:
                key, size = truth_of(instance)
                false_alert = spec.episode_id.endswith("__twin") and bool(channel.alerts)
                controller = TextSizedHedge(
                    lam=1.0 if name == "uniform" else 0.25,
                    promised_lead_time=spec.promised_lead_time,
                    horizon=spec.horizon,
                    train_demand=spec.train_demand,
                    order_cap=spec.order_cap,
                    trigger=build_wrapped("alert_or_detector", spec.horizon, 0, seed),
                    replay={},
                    read=reader(spec.episode_id, key, size, q_read, false_alert),
                    size_q=size_q,
                    arm_id=name,
                )
                iso = False
            result = (
                EpisodeRunner(
                    instance,
                    alerts=channel.alerts,
                    template_ids=channel.template_ids,
                    analysis_class=AnalysisClass.EXPLORATORY,
                    check_controller_isolation=iso,
                )
                .run(controller)
                .result
            )
            rows.append(
                {
                    "profit": profit,
                    "q_read": q_read,
                    "size_q": size_q,
                    "arm": name,
                    "episode_id": spec.episode_id,
                    "net": float(result.total_reward),
                }
            )
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.aacl.dev_text_size")
    ap.add_argument("--profits", nargs="+", type=float, default=[4.0, 19.0])
    ap.add_argument("--q-read", nargs="+", type=float, default=[0.5, 0.9, 1.0])
    ap.add_argument("--size-q", type=float, default=0.8)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    tasks = [(p, 0.0, 0.0, "arm1") for p in args.profits]
    tasks += [(p, 0.0, 0.0, "uniform") for p in args.profits]
    for p in args.profits:
        for q in args.q_read:
            tasks += [(p, q, 0.0, f"method_r{q:g}"), (p, q, args.size_q, f"sized_r{q:g}")]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        frame = pd.DataFrame([r for chunk in pool.map(run_task, tasks) for r in chunk])
    meta = pd.DataFrame(
        [
            {
                "episode_id": e,
                "cluster": e.split("/")[2],
                "fam": int(e.split("/f")[1][0]),
                "twin": e.endswith("__twin"),
            }
            for e in frame.episode_id.unique()
        ]
    ).set_index("episode_id")
    out = {"status": "development only, throwaway pool; no claim", "size_q": args.size_q}
    for p in args.profits:
        part = frame[frame.profit == p]
        piv = part.pivot_table(index="episode_id", columns="arm", values="net")
        block = {}
        for q in args.q_read:
            d = piv[f"sized_r{q:g}"] - piv[f"method_r{q:g}"]
            m = piv[f"method_r{q:g}"] - piv["arm1"]
            u = piv[f"method_r{q:g}"] - piv["uniform"]
            lo, hi = confirm.cluster_bootstrap(
                d, meta.cluster.reindex(d.index), resamples=2000, seed=confirm.SEED
            )
            block[f"q_read={q:g}"] = {
                "sized_minus_method": {"mean": float(d.mean()), "b": [lo, hi]},
                "sized_minus_method_by_family": {
                    str(f): float(
                        d[(meta.fam.reindex(d.index) == f) & ~meta.twin.reindex(d.index)].mean()
                    )
                    for f in range(1, 7)
                },
                "method_minus_arm1": float(m.mean()),
                "method_minus_uniform": float(u.mean()),
            }
        out[f"p={p:g}"] = block
    args.out.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    np.seterr(all="ignore")
    raise SystemExit(main())
