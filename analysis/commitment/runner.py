"""Runner for the commitment study. Exploratory; dev/cal generator only; never writes reports/.

Two layouts:

* ``pilot``: the registered 120 dev/cal pilot episodes with module 03's bank alerts, run through
  ``analysis.real_content_pilot.runner.run_pilot`` unchanged (Stage A, the model ladder);
* ``fresh``: a fresh-seed layout from :mod:`analysis.commitment.episodes` (Stage C). Stage C may
  only run after its registration in ``PLAN.md`` is committed and pushed.

Arm sets: ``nine`` is the real-content pilot's nine arms, wired identically; further sets are
added by :mod:`analysis.commitment.arms` when the method arms exist.

Live endpoints come from the model ladder (:mod:`analysis.commitment.endpoints`) behind the
real-content pilot's :class:`GuardedTransport` (retries, refusal handling, spend and call caps,
``spend_log.jsonl``), with the served model checked on every response. Paid answers are cached
under ``results/commitment/<run>/cache`` (gitignored), so re-running a finished run is free.

Usage::

    uv run python -m analysis.commitment.runner --layout pilot --endpoint gemini-2.5-flash-lite \\
        --run-name ladder-gemini-2.5-flash-lite --allow-live [--episodes ...]
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import analysis.real_content_pilot.runner as rcp
from analysis.commitment.endpoints import LADDER, EchoCheckedClient
from analysis.commitment.episodes import Layout, build_layout, layout_alerts
from analysis.real_content_pilot.alerts import SELECTION_RULE, EpisodeAlerts
from analysis.real_content_pilot.transport import (
    CallCapReached,
    GuardedTransport,
    SpendCapReached,
)
from collie.contracts import AnalysisClass, EpisodeResult
from collie.eval.truth import EpisodeTruth, write_episode_truth_jsonl
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import EndpointConfig
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from tools.run_arms import _attach_calls, _DemoTransport

REPO = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO / "analysis" / "commitment" / "out"
LOCAL_ROOT = REPO / "results" / "commitment"
LIVE_TIMEOUT_S = 180.0
_RUN_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

ArmBuilder = Callable[..., list[tuple[str, object, bool]]]
ARM_SETS: dict[str, ArmBuilder] = {"nine": rcp.build_arms}
"""Arm-set name -> builder with ``rcp.build_arms``'s signature. Extended by the arms module."""


def register_arm_set(name: str, builder: ArmBuilder) -> None:
    ARM_SETS[name] = builder


def build_live(
    name: str, *, spend_log: Path, spend_cap_usd: float, max_physical_calls: int
) -> tuple[EndpointConfig, GuardedTransport]:
    rung = LADDER[name]
    endpoint = rung.endpoint()
    inner = EchoCheckedClient(endpoint, rung.served_as, timeout=LIVE_TIMEOUT_S, max_retries=0)
    guard = GuardedTransport(
        inner=inner,
        endpoint=endpoint,
        spend_log=spend_log,
        spend_cap_usd=spend_cap_usd,
        max_physical_calls=max_physical_calls,
    )
    return endpoint, guard


@dataclass
class Run:
    results: tuple[EpisodeResult, ...]
    truths: tuple[EpisodeTruth, ...]
    ledger: CallLedger
    alerts: dict[str, EpisodeAlerts]
    proposals: list[dict]
    responses: list[dict]
    episode_ids: tuple[str, ...]
    partial: bool
    arm_ids: tuple[str, ...]


def run_pilot_layout(*, endpoint, transport, cache_dir: Path, episode_ids, arm_set: str) -> Run:
    """The registered pilot layout through ``rcp.run_pilot``, with the chosen arm builder."""
    original = rcp.build_arms
    rcp.build_arms = ARM_SETS[arm_set]
    try:
        run = rcp.run_pilot(
            endpoint=endpoint,
            transport=transport,
            alert_source="bank",
            cache_dir=cache_dir,
            episode_ids=episode_ids,
        )
    finally:
        rcp.build_arms = original
    arm_ids = tuple(dict.fromkeys(r.arm_id for r in run.results))
    return Run(
        run.results,
        run.truths,
        run.ledger,
        run.alerts,
        run.proposals,
        run.responses,
        run.episode_ids,
        run.partial,
        arm_ids,
    )


def run_fresh_layout(
    *,
    endpoint,
    transport,
    cache_dir: Path,
    n_per_family: int,
    profit: float,
    arm_set: str,
    episode_ids: Sequence[str] | None = None,
) -> Run:
    builder = ARM_SETS[arm_set]
    with tempfile.TemporaryDirectory() as tmp:
        layout: Layout = build_layout(Path(tmp), n_per_family, profit=profit)
        rcp.assert_dev_cal(layout.instances)
        alerts = layout_alerts(layout)
        instances = layout.instances
        partial = episode_ids is not None
        if partial:
            wanted = set(episode_ids)
            unknown = sorted(wanted - set(layout.episode_ids))
            if unknown:
                raise ValueError(f"not layout episodes: {unknown[:5]}")
            instances = [(i, s) for i, s in instances if i.spec.episode_id in wanted]
        ledger = CallLedger()
        metered = MeteredClient(
            transport=transport, endpoint=endpoint, cache=DiskCache(cache_dir), ledger=ledger
        )
        proposals: list[dict] = []
        responses: list[dict] = []

        def sink(row: dict, text: str) -> None:
            proposals.append(row)
            responses.append(
                {"prompt_key": row["prompt_key"], "call_id": row["call_id"], "text": text}
            )

        results: dict[str, list[EpisodeResult]] = {}
        for instance, seed in instances:
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
                results.setdefault(arm_id, []).append(outcome.result)
        attached = _attach_calls(results, ledger)
        ledger.assert_conserved()
        flat = tuple(result for arm_results in attached.values() for result in arm_results)
        if any(r.analysis_class is not AnalysisClass.EXPLORATORY for r in flat):
            raise AssertionError("a record escaped the exploratory stamp")
        kept = {i.spec.episode_id for i, _ in instances}
        return Run(
            flat,
            tuple(t for t in layout.truths if t.episode_id in kept),
            ledger,
            {k: v for k, v in alerts.items() if k in kept},
            proposals,
            responses,
            tuple(i.spec.episode_id for i, _ in instances),
            partial,
            tuple(results),
        )


def write_outputs(run: Run, *, out_dir: Path, local_dir: Path, meta: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    local_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.jsonl.gz").write_bytes(rcp.records_gz_bytes(run.results))
    run.ledger.to_csv(out_dir / "ledger.csv")
    rcp._write_jsonl(out_dir / "proposals.jsonl", run.proposals)
    rcp._write_jsonl(out_dir / "alerts.jsonl", [run.alerts[e].to_row() for e in run.episode_ids])
    write_episode_truth_jsonl(out_dir / "truth.jsonl", run.truths)
    rcp._write_jsonl(local_dir / "responses.jsonl", run.responses)
    summary = run.ledger.summary()
    manifest = {
        "analysis_class": "exploratory",
        "not_a_gate3_vote": True,
        **meta,
        "partial": run.partial,
        "episodes": len(run.episode_ids),
        "arms": list(run.arm_ids),
        "records": len(run.results),
        "ledger": {
            "physical_this_invocation": summary.physical,
            "charged": summary.charged,
            "charged_usd": summary.total_usd,
            "per_arm": [asdict(arm) for arm in summary.per_arm],
        },
        "alert_sources": {
            source: sum(1 for a in run.alerts.values() if a.source == source)
            for source in sorted({a.source for a in run.alerts.values()})
        },
        "rule_u": {
            "version": rcp.RULE_U,
            "arm10_coerced_abstentions": sum(
                1 for p in run.proposals if p["arm10_coerced_abstention"]
            ),
        },
        "outputs_sha256": {
            name: rcp._sha256(out_dir / name)
            for name in (
                "records.jsonl.gz",
                "ledger.csv",
                "proposals.jsonl",
                "alerts.jsonl",
                "truth.jsonl",
            )
        },
    }
    (out_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.commitment.runner")
    ap.add_argument("--layout", choices=("pilot", "fresh"), required=True)
    ap.add_argument("--endpoint", choices=("scripted", *LADDER), required=True)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--arm-set", default="nine")
    ap.add_argument("--episodes", nargs="+", help="a subset of layout episode ids (smoke runs)")
    ap.add_argument("--n-per-family", type=int, default=8, help="fresh layout only")
    ap.add_argument("--profit", type=float, default=4.0, help="fresh layout only; holding is 1")
    ap.add_argument("--spend-cap-usd", type=float, default=2.0)
    ap.add_argument("--max-physical-calls", type=int, default=1500)
    ap.add_argument("--allow-live", action="store_true")
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--local-root", type=Path, default=LOCAL_ROOT)
    args = ap.parse_args(argv)
    live = args.endpoint != "scripted"
    if live and not args.allow_live:
        raise SystemExit(f"--endpoint {args.endpoint} makes paid calls; pass --allow-live")
    if not _RUN_NAME.match(args.run_name):
        raise SystemExit("--run-name must be lowercase letters, digits, '.', '-' or '_'")
    if args.arm_set not in ARM_SETS:
        import analysis.commitment.arms  # noqa: F401  (registers the method arm sets)
    if args.arm_set not in ARM_SETS:
        raise SystemExit(f"unknown arm set {args.arm_set!r}; known: {sorted(ARM_SETS)}")
    out_dir = args.out_root / args.run_name
    local_dir = args.local_root / args.run_name
    guard = None
    if live:
        endpoint, transport = build_live(
            args.endpoint,
            spend_log=out_dir / "spend_log.jsonl",
            spend_cap_usd=args.spend_cap_usd,
            max_physical_calls=args.max_physical_calls,
        )
        guard = transport
    else:
        endpoint, transport = scripted_endpoint(), _DemoTransport()
    invocation = {
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "layout": args.layout,
        "endpoint": args.endpoint,
        "arm_set": args.arm_set,
        "episodes": args.episodes,
        "n_per_family": args.n_per_family if args.layout == "fresh" else None,
        "profit": args.profit if args.layout == "fresh" else 4.0,
        "spend_cap_usd": args.spend_cap_usd,
        "max_physical_calls": args.max_physical_calls,
        "git_sha": rcp._git("rev-parse", "HEAD"),
    }
    t0 = time.perf_counter()
    status, manifest = "error", None
    try:
        if args.layout == "pilot":
            run = run_pilot_layout(
                endpoint=endpoint,
                transport=transport,
                cache_dir=local_dir / "cache",
                episode_ids=args.episodes,
                arm_set=args.arm_set,
            )
        else:
            run = run_fresh_layout(
                endpoint=endpoint,
                transport=transport,
                cache_dir=local_dir / "cache",
                n_per_family=args.n_per_family,
                profit=args.profit,
                arm_set=args.arm_set,
                episode_ids=args.episodes,
            )
        meta = {
            "run_name": args.run_name,
            "layout": args.layout,
            "arm_set": args.arm_set,
            "n_per_family": invocation["n_per_family"],
            "profit": invocation["profit"],
            "endpoint": rcp._endpoint_meta(endpoint),
            "ladder_rung": asdict(LADDER[args.endpoint]) if live else None,
            "decoding": "det-v1 (temperature 0.0, no seed), module 02 prompt, no system prompt",
            "alert_source": "bank",
            "alert_selection_rule": SELECTION_RULE,
            "git": {
                "sha": rcp._git("rev-parse", "HEAD"),
                "branch": rcp._git("branch", "--show-current"),
                "dirty_paths": (rcp._git("status", "--porcelain") or "").splitlines(),
            },
            "versions": {"python": platform.python_version(), "openai": rcp._openai_version()},
            "guard": None if guard is None else guard.stats(),
        }
        manifest = write_outputs(run, out_dir=out_dir, local_dir=local_dir, meta=meta)
        status = "complete"
    except (SpendCapReached, CallCapReached) as exc:
        status = f"aborted: {exc}"
    finally:
        invocation.update(
            {
                "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "wall_seconds": round(time.perf_counter() - t0, 1),
                "status": status,
                "guard": None if guard is None else guard.stats(),
            }
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "invocations.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(invocation, sort_keys=True) + "\n")
    print(json.dumps({"status": status, "invocation": invocation}, indent=2, sort_keys=True))
    if manifest is not None:
        print(json.dumps({"ledger": manifest["ledger"]["physical_this_invocation"]}, indent=2))
    return 0 if status == "complete" else 3


if __name__ == "__main__":
    raise SystemExit(main())
