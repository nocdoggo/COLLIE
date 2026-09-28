"""Exploratory real-content pilot runner. Nothing here is registered or confirmatory.

Run (live endpoints make paid calls and need ``--allow-live``)::

    uv run python -m analysis.real_content_pilot.runner --endpoint scripted --run-name scripted-bank
    uv run python -m analysis.real_content_pilot.runner --endpoint gemini --run-name gemini-bank \\
        --allow-live

What it runs: the registered 120-episode dev/cal pilot (``tools.run_arms.pilot_instances``,
frozen) through nine arms built exactly as the frozen ``tools.run_arms.run_ladder`` builds them:
arms 1, 2, 8, 9, 10, the detector control, the keyword parser, the AlertSpec upper bound and the
oracle. Only arms 8, 9 and 10 call the LLM; they share one physical ShockSpec proposal call
through the cache, as in the registered design. Nothing in the frozen tree is edited.

What differs from ``run_ladder``, and only this:

* the transport and endpoint are injected (``scripted`` reproduces the registered pilot);
* the alert channel is module 03's bank (``--alerts bank``, see ``alerts.py``) or the frozen demo
  stand-in (``--alerts demo``, for equivalence checks);
* every record is stamped ``exploratory``, and any non-dev/cal instance is refused;
* each arm-8/9/10 parse is recorded (``RecordingParser``, which returns module 02's parser's
  answer unchanged), so abstentions and rejected proposals are analysable;
* Rule U, arm 10 only: a proposal module 02 accepts but module 05's lifecycle cannot register
  (``persistence`` or ``duration_bin`` of ``none``, or a proposal at the horizon) reaches arm 10
  as module 02's canonical abstention instead of aborting the run. Arms 8 and 9 get the
  proposal unchanged, and every coercion is logged (``RecordingParser``);
* live endpoints go through ``GuardedTransport`` (retries, logged refusals, hard spend cap).

Outputs (committed): ``analysis/real_content_pilot/out/<run>/`` with ``records.jsonl.gz``,
``ledger.csv``, ``proposals.jsonl``, ``alerts.jsonl``, ``spend_log.jsonl``, ``invocations.jsonl``
and ``run_manifest.json``. Local only (``results/`` is gitignored): the response cache and the raw
response texts, ``results/real_content_pilot/<run>/``.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from analysis.real_content_pilot.alerts import (
    SELECTION_RULE,
    EpisodeAlerts,
    pilot_bank_alerts,
    pilot_demo_alerts,
)
from analysis.real_content_pilot.transport import (
    CallCapReached,
    GuardedTransport,
    SpendCapReached,
)
from collie.arms.base_stock import ARM1_ARM_ID, CappedBaseStockController
from collie.arms.controls import (
    ALERTSPEC_UB_ARM_ID,
    ARM2_ARM_ID,
    DETECTOR_CONTROL_ARM_ID,
    KEYWORD_CONTROL_ARM_ID,
    AlertSpecUpperBoundArm,
    DetectorToCompilerArm,
    KeywordParserArm,
    TelemetryHMMController,
)
from collie.arms.oracle import ORACLE_ARM_ID, OracleShockSpecArm
from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import (
    ARM8_ARM_ID,
    ARM9_ARM_ID,
    ARM10_ARM_ID,
    HeuristicRollbackActivation,
    ImmediateActivation,
    ShockSpecArm,
)
from collie.contracts import (
    AnalysisClass,
    DurationBin,
    EpisodeResult,
    Persistence,
    ShockFamily,
    Split,
)
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.eval.records import episode_result_to_dict
from collie.eval.truth import EpisodeTruth, write_episode_truth_jsonl
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import (
    ArmCallChannel,
    EndpointConfig,
    Transport,
    gemini_primary,
    grok_hosted_confirmation,
)
from collie.llm.demo import scripted_endpoint
from collie.sim.loader import LoadedInstance
from collie.sim.runner import EpisodeRunner
from collie.spec.adapters import ShockSpecParser
from collie.spec.parse import validate_extracted_payload
from collie.trigger.demo import build_wrapped
from collie.verify import VerifierActivationPolicy
from tools.run_arms import (
    _attach_calls,
    _DemoTransport,
    _hidden_alert_spec,
    pilot_instances,
    spec_adapters,
)

REPO = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO / "analysis" / "real_content_pilot" / "out"
LOCAL_ROOT = REPO / "results" / "real_content_pilot"
STORED_TRUTH = REPO / "reports" / "pilot_truth.jsonl"

ARMS = (
    ARM1_ARM_ID,
    ARM2_ARM_ID,
    ARM8_ARM_ID,
    ARM9_ARM_ID,
    ARM10_ARM_ID,
    DETECTOR_CONTROL_ARM_ID,
    KEYWORD_CONTROL_ARM_ID,
    ALERTSPEC_UB_ARM_ID,
    ORACLE_ARM_ID,
)
LLM_ARMS = (ARM8_ARM_ID, ARM9_ARM_ID, ARM10_ARM_ID)
LIVE_ENDPOINTS: dict[str, Callable[[], EndpointConfig]] = {
    "gemini": gemini_primary,
    "grok": grok_hosted_confirmation,
}
ENDPOINT_CHOICES = ("scripted", *LIVE_ENDPOINTS)
DEFAULT_SPEND_CAP_USD = 3.0
DEFAULT_MAX_PHYSICAL_CALLS = 1000
LIVE_TIMEOUT_S = 180.0
_RUN_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class RefusedSplitError(RuntimeError):
    """An instance outside dev/cal reached the runner. The held-out test set is never run here."""


def assert_dev_cal(instances: Sequence[tuple[LoadedInstance, int]]) -> None:
    bad = [i.spec.episode_id for i, _ in instances if i.spec.split not in (Split.DEV, Split.CAL)]
    if bad:
        raise RefusedSplitError(f"refusing non-dev/cal episodes: {bad[:5]}")


# ---------------------------------------------------------------------------
# proposal recording (behaviour-neutral)
# ---------------------------------------------------------------------------


RULE_U = "U-v1"
# Module 02's own abstention, exactly as its prompt spells it out (collie/spec/prompt.py,
# ABSTENTION) and parsed by its own validator, so arm 10 sees what a model's no_change yields.
CANONICAL_ABSTENTION = ProposalPayload(
    **validate_extracted_payload(
        json.dumps(
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
        ),
        permitted_evidence_ids=(),
    ).model_dump()
)


def rule_u_reason(payload: ProposalPayload, *, tau_j: int, horizon: int) -> str | None:
    """Why module 05's lifecycle cannot register this module-02-legal proposal, if it cannot.

    Mirrors the two refusals in ``collie/verify/lifecycle.py`` that module 02 does not screen
    for: ``maximum_lifetime`` has no lifetime for a ``none`` persistence or duration, and
    ``LifecycleManager.propose`` refuses ``tau_j >= episode_horizon``. Every other shape module
    02 accepts resolves (checked by the tests). ``None`` means register it as usual.
    """
    if payload.shock_family is ShockFamily.NO_CHANGE:
        return None
    reasons = []
    if payload.persistence is Persistence.NONE:
        reasons.append("persistence_none")
    if payload.duration_bin is DurationBin.NONE:
        reasons.append("duration_none")
    if tau_j >= horizon:
        reasons.append("tau_at_horizon")
    return "+".join(reasons) or None


@dataclass(slots=True)
class RecordingParser:
    """Module 02's parser, plus a record of every parse for the proposal log.

    ``parse`` returns exactly what the wrapped ``ShockSpecParser`` returns, with one registered
    exception: when ``rule_u_horizon`` is set (arm 10 only), a proposal module 05's lifecycle
    cannot register is returned as ``CANONICAL_ABSTENTION`` (Rule U). The frozen stack would
    raise inside ``VerifierActivationPolicy.register`` and abort the run. The model's own
    payload stays in the log row. On a rejection the parser re-runs module 02's validator once
    more, only to capture the reason.
    """

    inner: ShockSpecParser
    channel: ArmCallChannel
    ledger: CallLedger
    sink: Callable[[dict, str], None]
    rule_u_horizon: int | None = None

    def parse(self, text: str):
        payload = self.inner.parse(text)
        error = None
        if payload is None:
            try:
                validate_extracted_payload(
                    text, permitted_evidence_ids=self.inner.prompter.bundle.evidence_ids
                )
            except (ValueError, TypeError) as exc:
                error = f"{type(exc).__name__}: {exc}"[:300]
        entry = self.ledger.entries[-1]
        if entry.call_id != self.channel.last_call_id:
            raise RuntimeError("proposal log out of step with the ledger")
        tau_j = self.inner.prompter.bundle.tau_j
        if tau_j != entry.period:
            raise RuntimeError("prompt tau_j and ledger period disagree")
        reason = None
        if payload is not None and self.rule_u_horizon is not None:
            reason = rule_u_reason(payload, tau_j=tau_j, horizon=self.rule_u_horizon)
        row = {
            "episode_id": entry.episode_id,
            "arm_id": entry.arm_id,
            "period": entry.period,
            "attempt_index": entry.attempt_index,
            "call_id": entry.call_id,
            "cache_hit": entry.cache_hit,
            "prompt_key": entry.prompt_hash,
            "parsed": payload is not None,
            "error": error,
            "payload": None if payload is None else _payload_dict(payload),
            "abstention": None if payload is None else payload.shock_family.value == "no_change",
            "arm10_coerced_abstention": reason is not None,
            "rule_u_reason": reason,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_chars": len(text),
        }
        self.sink(row, text)
        return CANONICAL_ABSTENTION if reason is not None else payload


def _payload_dict(payload) -> dict:
    out = {}
    for key, value in asdict(payload).items():
        if isinstance(value, tuple):
            value = list(value)
        out[key] = value.value if hasattr(value, "value") else value
    return out


# ---------------------------------------------------------------------------
# the nine arms, wired exactly as tools/run_arms.py::run_ladder wires them
# ---------------------------------------------------------------------------


def build_arms(
    instance: LoadedInstance,
    seed: int,
    *,
    metered: MeteredClient,
    ledger: CallLedger,
    sink: Callable[[dict, str], None],
) -> list[tuple[str, object, bool]]:
    """(arm_id, controller, isolation_checked) for one episode, in run_ladder's order."""
    spec = instance.spec
    promised = spec.promised_lead_time
    horizon = spec.horizon
    episode_id = spec.episode_id
    train_demands = spec.train_demand
    compiler = GridCompiler()

    def factory(config, demands, *, _cap=spec.order_cap, _train=train_demands):
        return OrCompilerController(order_cap=_cap, config=config, train_demand=(*_train, *demands))

    def fresh_trigger():
        return build_wrapped("alert_or_detector", horizon, 0, seed)

    def baseline() -> OrCompilerController:
        return OrCompilerController(
            order_cap=spec.order_cap,
            config=baseline_config_for(promised),
            train_demand=train_demands,
        )

    arms: list[tuple[str, object, bool]] = [
        (ARM1_ARM_ID, CappedBaseStockController(train_demand=train_demands), True),
        (ARM2_ARM_ID, TelemetryHMMController(train_demand=train_demands), True),
    ]
    for arm_id, activation in (
        (ARM8_ARM_ID, ImmediateActivation()),
        (ARM9_ARM_ID, HeuristicRollbackActivation()),
        (ARM10_ARM_ID, VerifierActivationPolicy(episode_horizon=horizon)),
    ):
        prompter, parser = spec_adapters()
        channel = metered.channel(arm_id=arm_id, episode_id=episode_id)
        recording = RecordingParser(
            parser,
            channel,
            ledger,
            sink,
            rule_u_horizon=horizon if arm_id == ARM10_ARM_ID else None,
        )
        arms.append(
            (
                arm_id,
                ShockSpecArm(
                    channel=channel,
                    prompter=prompter,
                    parser=recording,
                    compiler=compiler,
                    activation=activation,
                    baseline=baseline(),
                    controller_factory=factory,
                    trigger=fresh_trigger(),
                    baseline_config=baseline_config_for(promised),
                    arm_id=arm_id,
                ),
                True,
            )
        )
    arms.append(
        (
            DETECTOR_CONTROL_ARM_ID,
            DetectorToCompilerArm(
                compiler=compiler,
                trigger=fresh_trigger(),
                baseline=baseline(),
                controller_factory=factory,
                baseline_config=baseline_config_for(promised),
            ),
            True,
        )
    )
    arms.append(
        (
            KEYWORD_CONTROL_ARM_ID,
            KeywordParserArm(
                compiler=compiler,
                baseline=baseline(),
                controller_factory=factory,
                baseline_config=baseline_config_for(promised),
            ),
            True,
        )
    )
    if instance.incident is not None:
        arms.append(
            (
                ALERTSPEC_UB_ARM_ID,
                AlertSpecUpperBoundArm(
                    alert_spec=_hidden_alert_spec(instance.incident),
                    alert_period=instance.incident.onset_period - 1,
                    compiler=compiler,
                    baseline=baseline(),
                    controller_factory=factory,
                    baseline_config=baseline_config_for(promised),
                ),
                False,  # carries hidden truth by design (allowlisted upper bound)
            )
        )
        arms.append(
            (
                ORACLE_ARM_ID,
                OracleShockSpecArm(
                    incident=instance.incident,
                    compiler=compiler,
                    baseline=baseline(),
                    controller_factory=factory,
                    baseline_config=baseline_config_for(promised),
                ),
                False,  # the oracle reads hidden truth by definition
            )
        )
    return arms


# ---------------------------------------------------------------------------
# running
# ---------------------------------------------------------------------------


@dataclass
class PilotRun:
    results: tuple[EpisodeResult, ...]
    truths: tuple[EpisodeTruth, ...]
    ledger: CallLedger
    alerts: dict[str, EpisodeAlerts]
    proposals: list[dict]
    responses: list[dict]
    episode_ids: tuple[str, ...]
    partial: bool


def run_pilot(
    *,
    endpoint: EndpointConfig,
    transport: Transport,
    alert_source: str,
    cache_dir: Path,
    episode_ids: Sequence[str] | None = None,
) -> PilotRun:
    """Run the nine arms over the registered pilot (or a named subset of its episodes)."""
    if alert_source not in ("bank", "demo"):
        raise ValueError(f"unknown alert source {alert_source!r}")
    with tempfile.TemporaryDirectory() as tmp:
        instances, truths = pilot_instances(Path(tmp), 120)
        assert_dev_cal(instances)
        all_ids = tuple(instance.spec.episode_id for instance, _ in instances)
        partial = episode_ids is not None
        if partial:
            wanted = set(episode_ids)
            unknown = sorted(wanted - set(all_ids))
            if unknown:
                raise ValueError(f"not pilot episodes: {unknown[:5]}")
            instances = [(i, s) for i, s in instances if i.spec.episode_id in wanted]
        loaded = [instance for instance, _ in instances]
        alerts = pilot_bank_alerts(loaded) if alert_source == "bank" else pilot_demo_alerts(loaded)

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
            for arm_id, controller, isolation in build_arms(
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
        return PilotRun(
            results=flat,
            truths=truths,
            ledger=ledger,
            alerts=alerts,
            proposals=proposals,
            responses=responses,
            episode_ids=tuple(instance.spec.episode_id for instance, _ in instances),
            partial=partial,
        )


# ---------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------


def records_gz_bytes(results: Sequence[EpisodeResult]) -> bytes:
    """The frozen record writer's exact line format, gzipped byte-stably (mtime 0)."""
    body = "".join(
        json.dumps(episode_result_to_dict(r), sort_keys=True, separators=(",", ":")) + "\n"
        for r in results
    )
    return gzip.compress(body.encode("utf-8"), compresslevel=9, mtime=0)


def _write_jsonl(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def truth_matches_stored(truths: Sequence[EpisodeTruth]) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "truth.jsonl"
        write_episode_truth_jsonl(path, truths)
        return path.read_bytes() == STORED_TRUTH.read_bytes()


def write_run(run: PilotRun, *, out_dir: Path, local_dir: Path, meta: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    local_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.jsonl.gz").write_bytes(records_gz_bytes(run.results))
    run.ledger.to_csv(out_dir / "ledger.csv")
    _write_jsonl(out_dir / "proposals.jsonl", run.proposals)
    _write_jsonl(out_dir / "alerts.jsonl", [run.alerts[e].to_row() for e in run.episode_ids])
    _write_jsonl(local_dir / "responses.jsonl", run.responses)
    summary = run.ledger.summary()
    manifest = {
        "analysis_class": "exploratory",
        "not_a_gate3_vote": True,
        **meta,
        "partial": run.partial,
        "episodes": len(run.episode_ids),
        "arms": list(ARMS),
        "llm_arms": list(LLM_ARMS),
        "records": len(run.results),
        "truth_identical_to_reports_pilot_truth": (
            None if run.partial else truth_matches_stored(run.truths)
        ),
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
            "version": RULE_U,
            "arm10_coerced_abstentions": sum(
                1 for p in run.proposals if p["arm10_coerced_abstention"]
            ),
            "by_reason": {
                reason: sum(1 for p in run.proposals if p["rule_u_reason"] == reason)
                for reason in sorted(
                    {p["rule_u_reason"] for p in run.proposals if p["rule_u_reason"]}
                )
            },
        },
        "outputs_sha256": {
            name: _sha256(out_dir / name)
            for name in ("records.jsonl.gz", "ledger.csv", "proposals.jsonl", "alerts.jsonl")
        },
    }
    (out_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _endpoint_meta(endpoint: EndpointConfig) -> dict:
    return {
        "name": endpoint.name,
        "model_id": endpoint.model_id,
        "base_url": endpoint.base_url,
        "supports_seed": endpoint.supports_seed,
        "bills_thinking_as_output": endpoint.bills_thinking_as_output,
        "price_input_per_mtok": endpoint.price_input_per_mtok,
        "price_output_per_mtok": endpoint.price_output_per_mtok,
        "price_date": endpoint.price_date,
        "extra_body": endpoint.extra_body,
    }


def build_stack(
    name: str,
    *,
    spend_log: Path,
    spend_cap_usd: float,
    max_physical_calls: int,
    min_interval_s: float,
) -> tuple[EndpointConfig, Transport, GuardedTransport | None]:
    if name == "scripted":
        return scripted_endpoint(), _DemoTransport(), None
    endpoint = LIVE_ENDPOINTS[name]()
    from collie.llm.client import OpenAICompatClient

    inner = OpenAICompatClient(endpoint, timeout=LIVE_TIMEOUT_S, max_retries=0)
    guard = GuardedTransport(
        inner=inner,
        endpoint=endpoint,
        spend_log=spend_log,
        spend_cap_usd=spend_cap_usd,
        max_physical_calls=max_physical_calls,
        min_interval_s=min_interval_s,
    )
    return endpoint, guard, guard


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.real_content_pilot.runner")
    ap.add_argument("--endpoint", choices=ENDPOINT_CHOICES, required=True)
    ap.add_argument("--alerts", choices=("bank", "demo"), default="bank")
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--episodes", nargs="+", help="a subset of pilot episode ids (smoke runs)")
    ap.add_argument("--spend-cap-usd", type=float, default=DEFAULT_SPEND_CAP_USD)
    ap.add_argument("--max-physical-calls", type=int, default=DEFAULT_MAX_PHYSICAL_CALLS)
    ap.add_argument("--min-interval-s", type=float, default=0.0)
    ap.add_argument(
        "--allow-live",
        action="store_true",
        help="required for gemini/grok: these send prompts to a paid provider",
    )
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--local-root", type=Path, default=LOCAL_ROOT)
    args = ap.parse_args(argv)

    if args.endpoint in LIVE_ENDPOINTS and not args.allow_live:
        raise SystemExit(f"--endpoint {args.endpoint} makes paid calls; pass --allow-live")
    if not _RUN_NAME.match(args.run_name):
        raise SystemExit("--run-name must be lowercase letters, digits, '-' or '_'")
    out_dir = args.out_root / args.run_name
    local_dir = args.local_root / args.run_name
    endpoint, transport, guard = build_stack(
        args.endpoint,
        spend_log=out_dir / "spend_log.jsonl",
        spend_cap_usd=args.spend_cap_usd,
        max_physical_calls=args.max_physical_calls,
        min_interval_s=args.min_interval_s,
    )
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    invocation = {
        "started_at": started.isoformat(timespec="seconds"),
        "endpoint": args.endpoint,
        "alerts": args.alerts,
        "episodes": args.episodes,
        "spend_cap_usd": args.spend_cap_usd,
        "max_physical_calls": args.max_physical_calls,
        "git_sha": _git("rev-parse", "HEAD"),
    }
    status = "error"  # replaced on every path that returns normally
    manifest = None
    try:
        run = run_pilot(
            endpoint=endpoint,
            transport=transport,
            alert_source=args.alerts,
            cache_dir=local_dir / "cache",
            episode_ids=args.episodes,
        )
        meta = {
            "run_name": args.run_name,
            "endpoint": _endpoint_meta(endpoint),
            "decoding": "det-v1 (temperature 0.0, no seed), module 02 prompt, no system prompt",
            "alert_source": args.alerts,
            "alert_selection_rule": SELECTION_RULE if args.alerts == "bank" else None,
            "git": {
                "sha": _git("rev-parse", "HEAD"),
                "branch": _git("branch", "--show-current"),
                "dirty_paths": (_git("status", "--porcelain") or "").splitlines(),
            },
            "versions": {"python": platform.python_version(), "openai": _openai_version()},
            "guard": None if guard is None else guard.stats(),
        }
        manifest = write_run(run, out_dir=out_dir, local_dir=local_dir, meta=meta)
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
        print(
            json.dumps(
                {"ledger": manifest["ledger"], "alerts": manifest["alert_sources"]}, indent=2
            )
        )
    return 0 if status == "complete" else 3


def _openai_version() -> str | None:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return None
    return openai.__version__


if __name__ == "__main__":
    raise SystemExit(main())
