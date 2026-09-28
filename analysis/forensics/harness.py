"""Rebuild the pilot's episodes and arms exactly as the frozen pilot path does.

Exploratory instrumentation. Episodes come from the frozen ``tools.run_arms.pilot_instances``;
arms are constructed with the same classes and arguments ``tools.run_arms.run_ladder`` uses, so a
re-simulated arm can be compared bit for bit against ``reports/pilot_records.jsonl`` before any
counterfactual built on it is trusted. Nothing here edits a frozen file or re-runs Gate 3.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from analysis.forensics.common import ARM1, ARM8, ARM10, CTRL, ORACLE
from collie.arms.base_stock import CappedBaseStockController
from collie.arms.controls import DETECTOR_PAYLOAD, CompilerSwitchArm, DetectorToCompilerArm
from collie.arms.oracle import OracleShockSpecArm
from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import ImmediateActivation, ShockSpecArm
from collie.contracts import Decision, EpisodeResult, PeriodObservation
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.demo import scripted_endpoint
from collie.sim.loader import LoadedInstance, load_instance
from collie.sim.runner import EpisodeRunner
from collie.trigger.demo import build_wrapped
from collie.verify import VerifierActivationPolicy
from tools.run_arms import (
    _demo_alert,
    _demo_template_ids,
    _DemoTransport,
    pilot_instances,
    spec_adapters,
)

_FIELDS = ("order_quantity", "arrivals", "units_sold", "on_hand_end", "period_profit")


@dataclass(frozen=True)
class EpisodeContext:
    instance: LoadedInstance
    seed: int
    alerts: dict
    template_ids: dict

    @property
    def episode_id(self) -> str:
        return self.instance.spec.episode_id


def pilot_contexts(root: Path) -> list[EpisodeContext]:
    """The registered 120-episode pilot, regenerated deterministically under ``root``."""
    instances, _truths = pilot_instances(root, 120)
    out = []
    for instance, seed in instances:
        alerts = _demo_alert(instance)
        out.append(EpisodeContext(instance, seed, alerts, _demo_template_ids(instance, alerts)))
    return out


def twin_instance(root: Path, instance: LoadedInstance) -> LoadedInstance:
    """The unshocked baseline twin ``write_pair`` placed next to every shocked rollout."""
    spec = instance.spec
    twin_id = f"{spec.episode_id}__twin"
    return load_instance(
        root / twin_id,
        episode_id=twin_id,
        promised_lead_time=spec.promised_lead_time,
        split=spec.split,
    )


def metered_stack(root: Path) -> MeteredClient:
    return MeteredClient(
        transport=_DemoTransport(),
        endpoint=scripted_endpoint(),
        cache=DiskCache(root / "cache"),
        ledger=CallLedger(),
    )


def _baseline(instance: LoadedInstance) -> OrCompilerController:
    spec = instance.spec
    return OrCompilerController(
        order_cap=spec.order_cap,
        config=baseline_config_for(spec.promised_lead_time),
        train_demand=spec.train_demand,
    )


def _factory(instance: LoadedInstance):
    spec = instance.spec
    train = spec.train_demand

    def factory(config, demands, *, _cap=spec.order_cap, _train=train):
        return OrCompilerController(order_cap=_cap, config=config, train_demand=(*_train, *demands))

    return factory


def _trigger(ctx: EpisodeContext):
    return build_wrapped("alert_or_detector", ctx.instance.spec.horizon, 0, ctx.seed)


def build_arm(arm_id: str, ctx: EpisodeContext, metered: MeteredClient | None = None):
    """(controller, isolation_checked) exactly as ``run_ladder`` wires ``arm_id``."""
    instance = ctx.instance
    spec = instance.spec
    config = baseline_config_for(spec.promised_lead_time)
    if arm_id == ARM1:
        return CappedBaseStockController(train_demand=spec.train_demand), True
    if arm_id == CTRL:
        arm = DetectorToCompilerArm(
            compiler=GridCompiler(),
            trigger=_trigger(ctx),
            baseline=_baseline(instance),
            controller_factory=_factory(instance),
            baseline_config=config,
        )
        return arm, True
    if arm_id == ORACLE:
        arm = OracleShockSpecArm(
            incident=instance.incident,
            compiler=GridCompiler(),
            baseline=_baseline(instance),
            controller_factory=_factory(instance),
            baseline_config=config,
        )
        return arm, False
    if arm_id in (ARM8, ARM10):
        if metered is None:
            raise ValueError("the ShockSpec arms need the metered scripted stack")
        activation = (
            ImmediateActivation()
            if arm_id == ARM8
            else VerifierActivationPolicy(episode_horizon=spec.horizon)
        )
        prompter, parser = spec_adapters()
        arm = ShockSpecArm(
            channel=metered.channel(arm_id=arm_id, episode_id=spec.episode_id),
            prompter=prompter,
            parser=parser,
            compiler=GridCompiler(),
            activation=activation,
            baseline=_baseline(instance),
            controller_factory=_factory(instance),
            trigger=_trigger(ctx),
            baseline_config=config,
            arm_id=arm_id,
        )
        return arm, True
    raise ValueError(f"harness does not build {arm_id!r}")


def run(controller, instance: LoadedInstance, ctx: EpisodeContext | None, *, isolation: bool):
    runner = EpisodeRunner(
        instance,
        alerts=ctx.alerts if ctx is not None else None,
        template_ids=ctx.template_ids if ctx is not None else None,
        check_controller_isolation=isolation,
    )
    return runner.run(controller)


def signature(records: Sequence) -> tuple:
    """Per-period outcome signature for bit-for-bit comparison (RunRecord or stored dict)."""
    rows = []
    for r in records:
        get = r.get if isinstance(r, dict) else lambda f, _r=r: getattr(_r, f)
        rows.append(tuple(float(get(f)) for f in _FIELDS))
    return tuple(rows)


def same_as_stored(result: EpisodeResult, stored_records: Sequence[dict]) -> bool:
    return signature(result.records) == signature(stored_records)


# ---------------------------------------------------------------------------
# counterfactual instruments (exploratory; never registered, never deployable)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PlanController:
    """Replays a fixed order plan. Built from hidden truth, so it runs isolation-unchecked."""

    plan: tuple[float, ...]
    arm_id: str = "forensic_plan"

    def reset(self) -> None:
        return None

    def order(self, obs: PeriodObservation) -> Decision:
        return Decision(
            period=obs.period, order_quantity=self.plan[obs.period - 1], arm_id=self.arm_id
        )


def scheduled_switch_arm(
    ctx: EpisodeContext,
    *,
    switch_period: int | None,
    stand_down_period: int | None = None,
    payload: ProposalPayload = DETECTOR_PAYLOAD,
    arm_id: str = "forensic_scheduled_switch",
):
    """The detector control's exact compile-and-switch seam, but at a *given* period.

    ``switch_period=None`` never switches (the baseline). ``stand_down_period`` reverts dispatch
    to the baseline from that period on, the way the oracle's hazard window does. Used only to
    split the arm-10-minus-control gap into delay and retirement components.
    """
    instance = ctx.instance

    @dataclass(slots=True, kw_only=True)
    class _Scheduled(CompilerSwitchArm):
        at: int | None = None
        until: int | None = None

        def _switch_payload(self, obs: PeriodObservation) -> ProposalPayload | None:
            if self.at is not None and obs.period >= self.at:
                return payload
            return None

        def _dispatch_active(self, obs: PeriodObservation) -> bool:
            return self.until is None or obs.period < self.until

    return _Scheduled(
        compiler=GridCompiler(),
        controller_factory=_factory(instance),
        baseline=_baseline(instance),
        baseline_config=baseline_config_for(instance.spec.promised_lead_time),
        arm_id=arm_id,
        at=switch_period,
        until=stand_down_period,
    )
