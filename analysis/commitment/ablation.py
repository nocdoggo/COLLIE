"""Ablations of certify-then-hedge on stage C's fresh episodes, with the model's answers held fixed.

Exploratory and post hoc; not part of any registration. Variants of the method (``arm12_cth``,
``lam = 0.25``, the hedge rule):

* the prior weight on the model's hypothesis, ``lam`` in {0, 0.1, 0.25, 0.5, 0.75, 1};
* the decision rule at ``lam = 0.25``: ``hedge`` (the registered mixture quantile), ``map``
  (the compiled target once the shock mass reaches 1/2) and ``linear`` (the target interpolated
  by the shock mass).

Every variant with ``lam < 1`` is served, at each (episode, period), the answer text the model
gave ``arm12_cth`` in the registered run, through the same parser and repair path
(``sensitivity.py``'s replay, under the variant's own arm id). The shared trigger fires on
alerts and the demand detector, not on orders, so the variants consult the model at the same
periods as ``arm12_cth``; a call at any other period is served an abstention and counted
(``replay_misses``). The counterfactual is therefore "the same answer at the same decision
point": exact for ``lam = 0.25`` with the hedge rule (checked against the registered records)
and for ``lam = 1`` (no model call; checked against ``ctrl_cth_uniform``), and a replay for every
other variant. ``lam = 0`` is not ``arm12b_cth_llm``: that arm made its own calls, whose prompts
differ from ``arm12_cth``'s after the first firing.

Each variant is compared with arm 1, the gate (arm 10) and the method itself from the registered
records at ``p/h = 4``, and from ``sensitivity.py``'s replay at ``p/h = 19`` (arm 1 exact there,
the gate and the method replays), with stage C's seed-cluster bootstrap and sign-flip test
(one-sided, variant above its comparator; read two-sided through the interval). Values are
stored unrounded.

Usage::

    uv run python -m analysis.commitment.ablation [--ratios 4 19] [--workers 24]
"""

from __future__ import annotations

import argparse
import json
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

import analysis.real_content_pilot.runner as rcp
from analysis.commitment import confirm
from analysis.commitment.cth import CertifyThenHedgeArm
from analysis.commitment.episodes import build_layout, layout_alerts
from analysis.commitment.sensitivity import (
    N_PER_FAMILY,
    OUT,
    RUNS,
    _NoCache,
    _ReplayMetered,
    _ReplayTransport,
    load_replay,
)
from collie.contracts import AnalysisClass
from collie.llm import CallLedger
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from collie.trigger.demo import build_wrapped
from tools.run_arms import spec_adapters

LAMS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
SCHEMES = ("hedge", "map", "linear")
METHOD_LAM = 0.25
RATIOS = (4.0, 19.0)
REGISTERED_RATIO = 4.0


def variants() -> tuple[tuple[str, float, str], ...]:
    out = [(f"abl_lam{lam:g}_hedge", lam, "hedge") for lam in LAMS]
    out += [(f"abl_lam{METHOD_LAM:g}_{s}", METHOD_LAM, s) for s in SCHEMES if s != "hedge"]
    return tuple(out)


def variant_arm(instance, seed, *, vid, lam, scheme, metered, ledger, sink):
    spec = instance.spec
    kwargs = {}
    if lam < 1.0:
        prompter, parser = spec_adapters()
        channel = metered.channel(arm_id=vid, episode_id=spec.episode_id)
        kwargs = {
            "channel": channel,
            "prompter": prompter,
            "parser": rcp.RecordingParser(parser, channel, ledger, sink, rule_u_horizon=None),
        }
    return CertifyThenHedgeArm(
        lam=lam,
        scheme=scheme,
        promised_lead_time=spec.promised_lead_time,
        horizon=spec.horizon,
        train_demand=spec.train_demand,
        order_cap=spec.order_cap,
        trigger=build_wrapped("alert_or_detector", spec.horizon, 0, seed),
        arm_id=vid,
        **kwargs,
    )


def run_one(task: tuple[str, float, str, float, str]) -> dict:
    run, ratio, vid, lam, scheme = task
    recorded = load_replay(run)
    replay = {(vid, e, p): text for (a, e, p), text in recorded.items() if a == confirm.CTH}
    transport = _ReplayTransport(replay)
    ledger = CallLedger()
    metered = _ReplayMetered(
        transport=transport, endpoint=scripted_endpoint(), cache=_NoCache(), ledger=ledger
    )
    rows, calls = [], []

    def sink(row: dict, text: str) -> None:
        calls.append((row["episode_id"], int(row["period"])))

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_layout(Path(tmp), N_PER_FAMILY, profit=ratio)
        alerts = layout_alerts(layout)
        for instance, seed in layout.instances:
            channel = alerts[instance.spec.episode_id]
            arm = variant_arm(
                instance,
                seed,
                vid=vid,
                lam=lam,
                scheme=scheme,
                metered=metered,
                ledger=ledger,
                sink=sink,
            )
            outcome = EpisodeRunner(
                instance,
                alerts=channel.alerts,
                template_ids=channel.template_ids,
                analysis_class=AnalysisClass.EXPLORATORY,
                check_controller_isolation=True,
            ).run(arm)
            masses = [m for _, m, _ in arm.log]
            rows.append(
                {
                    "run": run,
                    "ratio": ratio,
                    "episode_id": instance.spec.episode_id,
                    "arm": vid,
                    "lam": lam,
                    "scheme": scheme,
                    "net": float(outcome.result.total_reward),
                    "gross": float(outcome.result.total_profit),
                    "exposure": float(sum(masses)) if masses else 0.0,
                }
            )
    return {
        "run": run,
        "ratio": ratio,
        "variant": vid,
        "rows": rows,
        "calls": len(calls),
        "replay_misses": len(transport.misses),
        "recorded_unused": len({(e, p) for (_, e, p) in replay} - set(calls)),
    }


def reference_frame(run: str, ratio: float) -> pd.DataFrame:
    """Arm 1, the gate and the registered certify-then-hedge arms at ``ratio``."""
    if ratio == REGISTERED_RATIO:
        frame = confirm.episode_frame(run)
    else:
        replay = pd.read_csv(OUT / "sensitivity.episodes.csv.gz")
        frame = replay[(replay.run == run) & (replay.ratio == ratio)]
    arms = (confirm.ARM1, confirm.ARM10, confirm.CTH, confirm.CTH_LLM, confirm.UNIFORM)
    return frame[frame.arm.isin(arms)][["episode_id", "arm", "net", "gross"]]


def check(frame: pd.DataFrame, reference: pd.DataFrame, ours: str, theirs: str) -> dict:
    a = frame[frame.arm == ours].set_index("episode_id")
    b = reference[reference.arm == theirs].set_index("episode_id").reindex(a.index)
    return {
        "episodes": len(a),
        "missing": int(b.net.isna().sum()),
        "max_abs_diff_net": float((a.net - b.net).abs().max()),
        "max_abs_diff_gross": float((a.gross - b.gross).abs().max()),
        "episodes_differing": int(((a.net - b.net).abs() > 1e-9).sum()),
    }


def summarise(frame: pd.DataFrame, done: list[dict]) -> dict:
    meta = confirm.episode_frame(RUNS[0]).drop_duplicates("episode_id")
    meta = meta.set_index("episode_id")[["cluster", "fam", "is_null"]]
    out: dict = {}
    for (run, ratio), part in frame.groupby(["run", "ratio"]):
        reference = reference_frame(run, ratio)
        both = pd.concat([part[reference.columns], reference]).join(meta, on="episode_id")
        entry: dict = {"checks": {}, "variants": {}}
        if ratio == REGISTERED_RATIO:
            entry["checks"]["lam0.25_hedge_vs_arm12_cth"] = check(
                part, reference, "abl_lam0.25_hedge", confirm.CTH
            )
        entry["checks"]["lam1_hedge_vs_ctrl_cth_uniform"] = check(
            part, reference, "abl_lam1_hedge", confirm.UNIFORM
        )
        entry["checks"]["lam0_hedge_vs_arm12b_cth_llm"] = check(
            part, reference, "abl_lam0_hedge", confirm.CTH_LLM
        )
        nulls = part.join(meta, on="episode_id")
        for vid, rows in part.groupby("arm"):
            v = {"lam": float(rows.lam.iloc[0]), "scheme": rows.scheme.iloc[0]}
            for name, control in (
                ("arm1", confirm.ARM1),
                ("arm10", confirm.ARM10),
                ("cth", confirm.CTH),
            ):
                c = confirm.contrast(both, vid, control, "net")
                v[f"minus_{name}|net"] = {k: c[k] for k in ("mean", "b", "p_one_sided", "n")}
            null_rows = nulls[(nulls.arm == vid) & nulls.is_null]
            v["null_exposure"] = float(null_rows.exposure.mean())
            v["null_net_minus_arm1"] = confirm.contrast(
                both, vid, confirm.ARM1, "net", mask=meta["is_null"]
            )["mean"]
            d = next(x for x in done if (x["run"], x["ratio"], x["variant"]) == (run, ratio, vid))
            v["replay"] = {k: d[k] for k in ("calls", "replay_misses", "recorded_unused")}
            entry["variants"][vid] = v
        out.setdefault(run, {})[f"{ratio:g}"] = entry
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.ablation")
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--ratios", nargs="+", type=float, default=list(RATIOS))
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--out", type=Path, default=OUT / "ablation.json")
    args = ap.parse_args(argv)
    if REGISTERED_RATIO not in args.ratios:
        raise SystemExit("include p/h = 4: it carries the reproduction check")
    tasks = [
        (run, ratio, vid, lam, scheme)
        for run in args.runs
        for ratio in args.ratios
        for vid, lam, scheme in variants()
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        done = list(pool.map(run_one, tasks))
    frame = pd.DataFrame([row for d in done for row in d["rows"]])
    results = summarise(frame, done)
    for run, block in results.items():
        c = block[f"{REGISTERED_RATIO:g}"]["checks"]
        for name in ("lam0.25_hedge_vs_arm12_cth", "lam1_hedge_vs_ctrl_cth_uniform"):
            if c[name]["missing"] or c[name]["max_abs_diff_net"] > 1e-9:
                raise SystemExit(f"{run}: {name} does not reproduce the registered run: {c[name]}")
    report = {
        "status": "exploratory, post hoc; model answers held fixed (arm12_cth's)",
        "results": results,
    }
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    frame.to_csv(args.out.with_suffix(".episodes.csv.gz"), index=False)
    for run, block in results.items():
        for ratio, entry in block.items():
            for vid, v in entry["variants"].items():
                a1, a10 = v["minus_arm1|net"], v["minus_arm10|net"]
                print(
                    f"{run:24s} p/h {ratio:>2s} {vid:22s} -arm1 {a1['mean']:+8.2f} "
                    f"[{a1['b'][0]:+.1f}, {a1['b'][1]:+.1f}] -gate {a10['mean']:+8.2f} "
                    f"[{a10['b'][0]:+.1f}, {a10['b'][1]:+.1f}] null exp {v['null_exposure']:.3f} "
                    f"misses {v['replay']['replay_misses']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
