"""Cost-ratio sensitivity: stage C's fresh episodes replayed at other profit-to-holding ratios.

Exploratory and post hoc. Stage C registered one ratio (p/h = 4, critical fractile 0.8); this
re-runs its full arm set on the same 240 fresh episodes at other ratios, with no API call. Each
arm that consulted a model is served the answer that model gave in the registered run at the
same (arm, episode, period). The prompt shows the price, the holding cost and the inventory
position, so at another ratio the model saw a slightly different prompt than it would have; the
answer is held fixed at what it said under p/h = 4. Arms that call no model (arm 1, the
content-free control, the oracle) are exact at every ratio.

Replaying at p/h = 4 must reproduce the registered records exactly; the run checks that before
it reports anything else. A model call at a period the registered run never called at would
have no recorded answer; it is served an abstention and counted (``replay_misses``).

Usage::

    uv run python -m analysis.commitment.sensitivity [--runs ...] [--ratios 1 2 4 9 19]
        [--summarise-only]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import analysis.commitment.arms  # noqa: F401  (registers the confirm arm set)
from analysis.commitment import confirm
from analysis.commitment.cth import CertifyThenHedgeArm
from analysis.commitment.episodes import build_layout, layout_alerts
from analysis.commitment.registry import ARM_SETS
from collie.contracts import AnalysisClass
from collie.llm import CallLedger, MeteredClient
from collie.llm.client import RawResponse
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from tools.run_arms import _attach_calls

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "commitment" / "out"
LOCAL = REPO / "results" / "commitment"
RUNS = ("fresh-gemini-3.8-flash", "fresh-grok-4.20")
RATIOS = (1.0, 2.0, 4.0, 9.0, 19.0)
REGISTERED_RATIO = 4.0
N_PER_FAMILY = 8
ABSTAIN = json.dumps(
    {
        "target_stream": "none",
        "shock_family": "no_change",
        "direction": "none",
        "onset_window": None,
        "magnitude_bin": None,
        "persistence": "unknown",
        "duration_bin": "none",
        "evidence_refs": [],
        "prospective_signature": "sig_demand_level_up",
    }
)
CONTRASTS = (
    ("cth-arm10", confirm.CTH, confirm.ARM10),
    ("cth-arm1", confirm.CTH, confirm.ARM1),
    ("cth-uniform", confirm.CTH, confirm.UNIFORM),
    ("uniform-arm1", confirm.UNIFORM, confirm.ARM1),
    ("arm10-arm1", confirm.ARM10, confirm.ARM1),
    ("arm8-arm1", confirm.ARM8, confirm.ARM1),
)


def load_replay(run: str) -> dict[tuple[str, str, int], str]:
    """The registered run's answer text per (arm, episode, period)."""
    texts = {
        r["call_id"]: r["text"] for r in map(json.loads, (LOCAL / run / "responses.jsonl").open())
    }
    out: dict[tuple[str, str, int], str] = {}
    for row in map(json.loads, (OUT / run / "proposals.jsonl").open()):
        key = (row["arm_id"], row["episode_id"], int(row["period"]))
        if key in out:
            raise ValueError(f"{run}: more than one recorded call at {key}")
        out[key] = texts[row["call_id"]]
    return out


class _NoCache:
    """Every lookup misses, so every call reaches the replay."""

    def get(self, key):
        return None

    def put(self, key, raw) -> None:
        return None


@dataclass
class _ReplayTransport:
    replay: dict[tuple[str, str, int], str]
    context: tuple[str, str, int] | None = None
    misses: list[tuple[str, str, int]] = field(default_factory=list)
    served: int = 0

    @property
    def model_id(self) -> str:
        return "replay"

    def complete_metered(self, prompt: str, *, decoding, system: str | None = None) -> RawResponse:
        text = self.replay.get(self.context)
        if text is None:
            self.misses.append(self.context)
            text = ABSTAIN
        self.served += 1
        n = len(prompt) // 4 + 1
        return RawResponse(text=text, prompt_tokens=n, completion_tokens=1, total_tokens=n + 1)


class _ReplayMetered(MeteredClient):
    """A metered client whose transport learns the (arm, episode, period) of each call."""

    def _complete(self, prompt, *, arm_id, episode_id, period, **kwargs):
        self.transport.context = (arm_id, episode_id, int(period))
        return MeteredClient._complete(
            self, prompt, arm_id=arm_id, episode_id=episode_id, period=period, **kwargs
        )


def run_one(task: tuple[str, float]) -> dict:
    run, ratio = task
    builder = ARM_SETS["confirm"]
    transport = _ReplayTransport(load_replay(run))
    ledger = CallLedger()
    metered = _ReplayMetered(
        transport=transport, endpoint=scripted_endpoint(), cache=_NoCache(), ledger=ledger
    )
    rows, calls = [], []

    def sink(row: dict, text: str) -> None:
        calls.append((row["arm_id"], row["episode_id"], int(row["period"])))

    with tempfile.TemporaryDirectory() as tmp:
        layout = build_layout(Path(tmp), N_PER_FAMILY, profit=ratio)
        alerts = layout_alerts(layout)
        results = defaultdict(list)
        for instance, seed in layout.instances:
            channel = alerts[instance.spec.episode_id]
            for arm_id, controller, isolation in builder(
                instance, seed, metered=metered, ledger=ledger, sink=sink
            ):
                outcome = EpisodeRunner(
                    instance,
                    alerts=channel.alerts,
                    template_ids=channel.template_ids,
                    analysis_class=AnalysisClass.EXPLORATORY,
                    check_controller_isolation=isolation,
                ).run(controller)
                results[arm_id].append(outcome.result)
                masses = (
                    [m for _, m, _ in controller.log]
                    if isinstance(controller, CertifyThenHedgeArm)
                    else []
                )
                rows.append(
                    {
                        "run": run,
                        "ratio": ratio,
                        "episode_id": instance.spec.episode_id,
                        "arm": arm_id,
                        "net": float(outcome.result.total_reward),
                        "gross": float(outcome.result.total_profit),
                        "exposure": float(sum(masses)) if masses else None,
                    }
                )
        _attach_calls(dict(results), ledger)
        ledger.assert_conserved()
    recorded = {k for k in transport.replay}
    return {
        "run": run,
        "ratio": ratio,
        "rows": rows,
        "calls": len(calls),
        "replay_misses": len(transport.misses),
        "recorded_unused": len(recorded - set(calls)),
    }


def registered_frame(run: str) -> pd.DataFrame:
    return confirm.episode_frame(run)[["episode_id", "arm", "net", "gross"]]


def check_reproduction(frame: pd.DataFrame, run: str) -> dict:
    """At the registered ratio the replay must equal the registered records, arm by arm."""
    ours = frame[(frame.run == run) & (frame.ratio == REGISTERED_RATIO)]
    ref = registered_frame(run)
    merged = ours.merge(ref, on=["episode_id", "arm"], suffixes=("", "_ref"), how="outer")
    diff = (merged.net - merged.net_ref).abs().max(), (merged.gross - merged.gross_ref).abs().max()
    return {
        "pairs": len(merged),
        "missing": int(merged.net.isna().sum() + merged.net_ref.isna().sum()),
        "max_abs_diff_net": float(diff[0]),
        "max_abs_diff_gross": float(diff[1]),
    }


def summarise(frame: pd.DataFrame) -> dict:
    meta = confirm.episode_frame(RUNS[0]).drop_duplicates("episode_id")
    meta = meta.set_index("episode_id")[["cluster", "fam", "is_null"]]
    out = {}
    for (run, ratio), part in frame.groupby(["run", "ratio"]):
        part = part.join(meta, on="episode_id")
        entry = {"critical_fractile": round(ratio / (ratio + 1.0), 4)}
        for name, treat, control in CONTRASTS:
            for endpoint in ("net", "gross"):
                c = confirm.contrast(part, treat, control, endpoint)
                entry[f"{name}|{endpoint}"] = {
                    "mean": round(c["mean"], 3),
                    "b": [round(c["b"][0], 3), round(c["b"][1], 3)],
                    "p_one_sided": round(c["p_one_sided"], 5),
                }
        nulls = part[part.is_null]
        piv = nulls.pivot(index="episode_id", columns="arm", values="net")
        entry["null_cth_minus_arm1"] = round(
            float((piv[confirm.CTH] - piv[confirm.ARM1]).mean()), 1
        )
        exp = nulls.pivot(index="episode_id", columns="arm", values="exposure")
        entry["null_exposure"] = {
            arm: round(float(exp[arm].mean()), 3)
            for arm in (confirm.CTH, confirm.CTH_LLM, confirm.UNIFORM)
        }
        arm1 = part[part.arm == confirm.ARM1].net.mean()
        entry["arm1_net_mean"] = round(float(arm1), 1)
        piv = part.pivot(index="episode_id", columns="arm", values="net")
        fam = meta["fam"].reindex(piv.index)
        for name, treat in (("cth", confirm.CTH), ("uniform", confirm.UNIFORM)):
            diff = piv[treat] - piv[confirm.ARM1]
            entry[f"by_family_{name}_minus_arm1"] = {
                str(int(f)): round(float(diff[fam == f].mean()), 1) for f in sorted(fam.unique())
            }
        entry["cth-arm1|net|without_family_4"] = {
            k: round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v]
            for k, v in confirm.contrast(
                part, confirm.CTH, confirm.ARM1, "net", mask=meta["fam"].ne(4)
            ).items()
            if k in ("mean", "b")
        }
        out.setdefault(run, {})[f"{ratio:g}"] = entry
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.sensitivity")
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--ratios", nargs="+", type=float, default=list(RATIOS))
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--out", type=Path, default=OUT / "sensitivity.json")
    ap.add_argument(
        "--summarise-only", action="store_true", help="re-read the per-episode file; no replay"
    )
    args = ap.parse_args(argv)
    if REGISTERED_RATIO not in args.ratios:
        raise SystemExit("include the registered ratio 4: it is the replay's reproduction check")
    episodes = args.out.with_suffix(".episodes.csv.gz")
    if args.summarise_only:
        # Re-summarise the committed per-episode replay without re-running it.
        frame = pd.read_csv(episodes)
        replay = json.loads(args.out.read_text())["replay"]
        done = [
            {"run": k.split("|")[0], "ratio": float(k.split("|")[1]), **v}
            for k, v in replay.items()
        ]
    else:
        tasks = [(run, ratio) for run in args.runs for ratio in args.ratios]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            done = list(pool.map(run_one, tasks))
        frame = pd.DataFrame([row for d in done for row in d["rows"]])
    checks = {run: check_reproduction(frame, run) for run in args.runs}
    for run, check in checks.items():
        if (
            check["missing"]
            or check["max_abs_diff_net"] > 1e-9
            or check["max_abs_diff_gross"] > 1e-9
        ):
            raise SystemExit(f"{run}: the replay at p/h = 4 does not reproduce stage C: {check}")
    report = {
        "status": "exploratory, post hoc; not part of the stage C registration",
        "registered_ratio": REGISTERED_RATIO,
        "reproduction_at_registered_ratio": checks,
        "replay": {
            f"{d['run']}|{d['ratio']:g}": {
                "calls": d["calls"],
                "replay_misses": d["replay_misses"],
                "recorded_unused": d["recorded_unused"],
            }
            for d in done
        },
        "results": summarise(frame),
    }
    args.out.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    if not args.summarise_only:
        with gzip.open(episodes, "wt", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(frame.columns))
            writer.writeheader()
            writer.writerows(frame.to_dict("records"))
    for run, by_ratio in report["results"].items():
        for ratio, e in by_ratio.items():
            print(
                f"{run} p/h={ratio}: cth-arm10 {e['cth-arm10|net']['mean']:+.0f} "
                f"cth-arm1 {e['cth-arm1|net']['mean']:+.0f} {e['cth-arm1|net']['b']} "
                f"cth-uniform {e['cth-uniform|net']['mean']:+.0f} "
                f"arm8-arm1 {e['arm8-arm1|net']['mean']:+.0f} "
                f"misses {report['replay'][f'{run}|{ratio}']['replay_misses']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
