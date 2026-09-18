"""Task 23 / Checkpoint 2 demo: the arm ladder over dev episodes.

Runs every arm — 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, the three non-LLM controls, and the oracle —
over N dev episodes, prints the main-table shape (one row per arm, every cell populated from
stored records), and balances the ledger across the sweep. Run:

    uv run python -m tools.run_arms --split dev --episodes 18 --table

What this is and is not. It IS the integration proof: one runner, one metered stack, the shared
physical proposal call set, and the headroom band between stationary OR and the oracle. It is
NOT a result: the LLM is a scripted transport serving canned payloads (valid action, default
parameters, one ShockSpec proposal), the alert channel is the synthetic accurate-alert stand-in
from the trigger demo (module 03 lands later), and the numbers say nothing about any arm's
merit. Arms 8/9/10's activation spread *is* real (the scripted proposal drives them apart by
construction, which is what the divergence test pins).

Only ``dev`` episodes are ever touched; nothing here reads test material. The two upper-bound
arms (AlertSpec parsing, oracle) are constructed with hidden truth by design and run with the
controller-isolation check off — they are the allowlisted exceptions (tests/test_contracts.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

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
from collie.arms.direct import (
    ARM3_ARM_ID,
    ARM4_ARM_ID,
    ARM11_ARM_ID,
    DirectActionArm,
    prompt_spec_from_episode,
)
from collie.arms.llm_to_or import (
    ARM5_ARM_ID,
    ARM6_ARM_ID,
    ARM7_ARM_ID,
    PERSISTENCE_EXPIRY,
    LlmToOrArm,
)
from collie.arms.oracle import ORACLE_ARM_ID, OracleShockSpecArm, incident_to_payload
from collie.arms.protocols import ProposalPayload
from collie.arms.shockspec import (
    ARM8_ARM_ID,
    ARM9_ARM_ID,
    ARM10_ARM_ID,
    EProcessActivation,
    HeuristicRollbackActivation,
    ImmediateActivation,
    ShockSpecArm,
)
from collie.contracts import (
    AlertKind,
    AlertMessage,
    ControlConfig,
    Direction,
    DurationBin,
    HiddenAlertSpec,
    HiddenIncident,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    Split,
    TargetStream,
)
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.data.families import generate_episode
from collie.data.splits import FAMILIES, build_units
from collie.data.writer import write_pair
from collie.fakes.fake_verifier import FakeVerifier
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import RawResponse
from collie.llm.demo import scripted_endpoint
from collie.sim.loader import LoadedInstance, load_instance
from collie.sim.runner import EpisodeRunner
from collie.trigger.demo import DEMO_HORIZON, build_wrapped

DEMO_HORIZON_LOCAL = DEMO_HORIZON  # the official synthetic horizon (env contract §1)

# ---------------------------------------------------------------------------
# demo-time LLM content: a scripted transport routing by prompt shape
# ---------------------------------------------------------------------------

_DEMO_ACTION_QTY = 100
"""The scripted direct-action order, a round number near the dev demand level (~100/period)."""

_SPEC_PROPOSAL_PREFIX = "spec-proposal|"


class _DemoTransport:
    """Scripted responses by prompt shape. The whole demo's LLM content, clearly labelled."""

    n_calls: int = 0

    @property
    def model_id(self) -> str:
        return "demo-scripted"

    def complete_metered(self, prompt: str, *, decoding, system: str | None = None) -> RawResponse:
        self.n_calls += 1
        if prompt.startswith(_SPEC_PROPOSAL_PREFIX):
            text = json.dumps(
                {
                    "target_stream": "demand",
                    "shock_family": "demand_level",
                    "direction": "demand_up",
                    "onset_window": [-1, 1],
                    "magnitude_bin": "medium",
                    "persistence": "persistent",
                    "duration_bin": "longer",
                    "evidence_refs": [],
                    "prospective_signature": "sig_demand_level_up",
                }
            )
        elif system is not None and "PARAMETER MENU" in system:
            # __default__ expands to the item inside validate_item_parameters.
            text = json.dumps(
                {
                    "rationale": "demo",
                    "carry_over_insight": "",
                    "parameters": {
                        "__default__": {
                            "L": {"method": "default"},
                            "mu_hat": {"method": "default"},
                            "sigma_hat": {"method": "default"},
                        }
                    },
                }
            )
        else:
            text = json.dumps(
                {
                    "rationale": "demo",
                    "carry_over_insight": "",
                    "action": {self._item_from(system): _DEMO_ACTION_QTY},
                }
            )
        return RawResponse(
            text=text,
            prompt_tokens=(len(prompt) + len(system or "")) // 4 + 1,
            completion_tokens=len(text) // 4 + 1,
            total_tokens=(len(prompt) + len(system or "") + len(text)) // 4 + 2,
        )

    @staticmethod
    def _item_from(system: str | None) -> str:
        # The system prompt quotes the item id in ROLE & OBJECTIVE: `SKU "<id>"`.
        if system and 'SKU "' in system:
            return system.split('SKU "', 1)[1].split('"', 1)[0]
        return "item_id"


class _DemoPrompter:
    """Module-02 stand-in: a deterministic proposal prompt from observable fields only."""

    def prompt(self, obs) -> str:
        alert = obs.alert.text if obs.alert else ""
        return (
            f"{_SPEC_PROPOSAL_PREFIX}p={obs.period}|on_hand={obs.on_hand}"
            f"|transit={obs.in_transit_total}|prev_demand={obs.prev_demand}|alert={alert}"
        )


class _DemoParser:
    """Module-02 stand-in: json -> ProposalPayload; None on anything unparseable."""

    def parse(self, text: str) -> ProposalPayload | None:
        try:
            data = json.loads(text)
            return ProposalPayload(
                target_stream=TargetStream(data["target_stream"]),
                shock_family=ShockFamily(data["shock_family"]),
                direction=Direction(data["direction"]),
                onset_window=tuple(data["onset_window"])
                if data.get("onset_window") is not None
                else None,
                magnitude_bin=MagnitudeBin(data["magnitude_bin"])
                if data.get("magnitude_bin") is not None
                else None,
                persistence=Persistence(data["persistence"]),
                duration_bin=DurationBin(data["duration_bin"]),
                evidence_refs=tuple(data.get("evidence_refs", ())),
                prospective_signature=data["prospective_signature"],
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return None


# ---------------------------------------------------------------------------
# dev episode materialisation (same convention as the trigger demo)
# ---------------------------------------------------------------------------


def dev_instances(root: Path, episodes: int) -> list[tuple[LoadedInstance, int]]:
    """Materialise ``episodes`` dev episodes (one per family per cycle) and load them.

    The dev pool is finite (``build_units(Split.DEV)`` units per family); asking for more
    cycles than the pool holds must fail loudly, not fall off the end of the registry with a
    bare ``IndexError``.
    """
    units = build_units(Split.DEV)
    by_family = {f: [u for u in units if u.family == f] for f in FAMILIES}
    cycles = episodes // len(FAMILIES)
    if cycles < 1 or episodes % len(FAMILIES) != 0:
        raise ValueError(f"--episodes must be a positive multiple of 6, got {episodes}")
    per_family = min(len(by_family[f]) for f in FAMILIES)
    pool = per_family * len(FAMILIES)
    if episodes > pool:
        raise ValueError(
            f"--episodes {episodes} exceeds the dev episode pool of {pool} "
            f"({per_family} units x {len(FAMILIES)} families); "
            "the dev split is finite by design and larger sweeps are for the pilot, not the demo"
        )
    out = []
    for i in range(cycles):
        for family in FAMILIES:
            unit = by_family[family][i]
            assert unit.params is not None  # dev units always carry params
            ep = generate_episode(seed=unit.seed, horizon=DEMO_HORIZON_LOCAL, params=unit.params)
            relpath = f"dev/f{family}/s{unit.seed}"
            write_pair(root, ep, relpath=relpath)
            instance = load_instance(
                root / relpath, episode_id=relpath, promised_lead_time=unit.promised_lead_time
            )
            out.append((instance, unit.seed))
    return out


def _train_samples(root: Path, relpath: str) -> tuple[tuple[str, float], ...]:
    """The (date, demand) pairs the frozen loader drops the dates from; read back directly."""
    with (root / relpath / "train.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return tuple((r[0], float(r[1])) for r in rows[1:])


def _demo_alert(instance: LoadedInstance) -> dict[int, AlertMessage]:
    """One synthetic accurate alert at onset-1, the demo's labelled module-03 stand-in.

    The text is family-aware so the keyword-parser control has something to parse: a demand
    phrase on demand-side incidents, a shipment phrase on supply-side ones.
    """
    onset = instance.incident.onset_period if instance.incident else None
    if onset is None or onset <= 1:
        return {}
    demand_side = instance.incident.family in (
        ShockFamily.DEMAND_LEVEL,
        ShockFamily.TEMPORARY_PULSE,
        ShockFamily.COMPOUND,
    )
    content = "demand increase expected" if demand_side else "shipment delay expected"
    return {
        onset - 1: AlertMessage(
            alert_id=f"demo_alert_{onset - 1}",
            period=onset - 1,
            text=f"[demo stand-in for module 03] supplier advisory: {content}",
        )
    }


def _hidden_alert_spec(incident: HiddenIncident) -> HiddenAlertSpec:
    """The canonical alert structure behind the demo alert, from truth (harness side only).

    The field mapping is the oracle's own truth-to-vocabulary map, so the parsing upper bound
    and the headroom bound read the same truth the same way.
    """
    payload = incident_to_payload(incident)
    return HiddenAlertSpec(
        family=incident.family,
        target_stream=payload.target_stream,
        direction=payload.direction,
        onset_window=payload.onset_window,
        magnitude_bin=payload.magnitude_bin,
        persistence=payload.persistence,
        duration_bin=payload.duration_bin,
        prospective_signature=payload.prospective_signature,
        kind=AlertKind.ACCURATE,
    )


# ---------------------------------------------------------------------------
# the ladder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmRow:
    arm_id: str
    mean_score: float
    fill_rate: float
    calls: int
    in_tokens: int
    out_tokens: int
    usd: float
    p95_ms: float


def run_ladder(
    instances: list[tuple[LoadedInstance, int]], root: Path
) -> tuple[list[ArmRow], CallLedger]:
    """Run every arm over every episode on one metered stack; return per-arm rows + ledger."""
    ledger = CallLedger()
    transport = _DemoTransport()
    metered = MeteredClient(
        transport=transport,
        endpoint=scripted_endpoint(),
        cache=DiskCache(root / "cache"),
        ledger=ledger,
    )
    results: dict[str, list] = {}
    for instance, seed in instances:
        spec = instance.spec
        promised = spec.promised_lead_time
        train = _train_samples(root, spec.episode_id)
        prompt_spec = prompt_spec_from_episode(spec, train_samples=train)
        alerts = _demo_alert(instance)
        compiler = GridCompiler()

        horizon = spec.horizon
        episode_id = spec.episode_id
        train_demands = spec.train_demand

        def factory(
            config: ControlConfig,
            demands: tuple[float, ...],
            *,
            _cap: float = spec.order_cap,
            _train: tuple[float, ...] = train_demands,
        ) -> OrCompilerController:
            # The compiled controller's samples: the episode's train history plus what the arm
            # observed before the switch (the arm excludes the switch period's prev_demand,
            # which the new controller records itself).
            return OrCompilerController(
                order_cap=_cap, config=config, train_demand=(*_train, *demands)
            )

        def fresh_trigger(*, _horizon: int = horizon, _seed: int = seed) -> object:
            return build_wrapped("alert_or_detector", _horizon, 0, _seed)

        def channel(arm_id: str, *, _episode_id: str = episode_id):
            return metered.channel(arm_id=arm_id, episode_id=_episode_id)

        arms: list[tuple[str, object, bool]] = []  # (arm_id, controller, isolation_checked)
        arms.append((ARM1_ARM_ID, CappedBaseStockController(train_demand=train_demands), True))
        # The HMM's defaults ARE the frozen, dev-calibrated constants.
        arms.append((ARM2_ARM_ID, TelemetryHMMController(train_demand=train_demands), True))
        for arm_id, kwargs in (
            (ARM3_ARM_ID, {}),
            (
                ARM4_ARM_ID,
                {
                    "trigger": fresh_trigger(),
                    "fallback": CappedBaseStockController(train_demand=train_demands),
                },
            ),
            (ARM11_ARM_ID, {"or_to_llm": True}),
        ):
            arms.append(
                (
                    arm_id,
                    DirectActionArm(
                        channel=channel(arm_id), prompt_spec=prompt_spec, arm_id=arm_id, **kwargs
                    ),
                    True,
                )
            )
        for arm_id, kwargs in (
            (ARM5_ARM_ID, {}),
            (ARM6_ARM_ID, {"trigger": fresh_trigger()}),
            (
                ARM7_ARM_ID,
                {"trigger": fresh_trigger(), "expiry": PERSISTENCE_EXPIRY},
            ),
        ):
            arms.append(
                (
                    arm_id,
                    LlmToOrArm(
                        channel=channel(arm_id), prompt_spec=prompt_spec, arm_id=arm_id, **kwargs
                    ),
                    True,
                )
            )
        for arm_id, activation in (
            (ARM8_ARM_ID, ImmediateActivation()),
            (ARM9_ARM_ID, HeuristicRollbackActivation()),
            (ARM10_ARM_ID, EProcessActivation(FakeVerifier(activate_after=2))),
        ):
            arms.append(
                (
                    arm_id,
                    ShockSpecArm(
                        channel=channel(arm_id),
                        prompter=_DemoPrompter(),
                        parser=_DemoParser(),
                        compiler=compiler,
                        activation=activation,
                        baseline=OrCompilerController(
                            order_cap=spec.order_cap,
                            config=baseline_config_for(promised),
                            train_demand=train_demands,
                        ),
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
                    baseline=OrCompilerController(
                        order_cap=spec.order_cap,
                        config=baseline_config_for(promised),
                        train_demand=train_demands,
                    ),
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
                    baseline=OrCompilerController(
                        order_cap=spec.order_cap,
                        config=baseline_config_for(promised),
                        train_demand=train_demands,
                    ),
                    controller_factory=factory,
                    baseline_config=baseline_config_for(promised),
                ),
                True,
            )
        )
        # The two hidden-truth upper bounds run where the truth-to-vocabulary map is defined.
        # Compound incidents are excluded: the oracle refuses them by design (a joint
        # demand+supply construction is module 05's), so the headroom band below covers
        # families 1-5 — stated on the table, never silently dropped.
        if instance.incident is not None and instance.incident.family is not ShockFamily.COMPOUND:
            arms.append(
                (
                    ALERTSPEC_UB_ARM_ID,
                    AlertSpecUpperBoundArm(
                        alert_spec=_hidden_alert_spec(instance.incident),
                        alert_period=instance.incident.onset_period - 1,
                        compiler=compiler,
                        baseline=OrCompilerController(
                            order_cap=spec.order_cap,
                            config=baseline_config_for(promised),
                            train_demand=train_demands,
                        ),
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
                        baseline=OrCompilerController(
                            order_cap=spec.order_cap,
                            config=baseline_config_for(promised),
                            train_demand=train_demands,
                        ),
                        controller_factory=factory,
                        baseline_config=baseline_config_for(promised),
                    ),
                    False,  # the oracle reads hidden truth by definition
                )
            )

        for arm_id, controller, isolation in arms:
            runner = EpisodeRunner(
                instance,
                alerts=alerts,
                check_controller_isolation=isolation,
            )
            outcome = runner.run(controller)
            results.setdefault(arm_id, []).append(outcome.result)

    rows: list[ArmRow] = []
    per_arm = {t.arm_id: t for t in ledger.summary().per_arm}
    for arm_id, arm_results in results.items():
        n = len(arm_results)
        totals = per_arm.get(arm_id)
        rows.append(
            ArmRow(
                arm_id=arm_id,
                mean_score=sum(r.normalized_reward for r in arm_results) / n,
                fill_rate=sum(r.fill_rate for r in arm_results) / n,
                calls=totals.attempted if totals else 0,
                in_tokens=totals.input_tokens if totals else 0,
                out_tokens=totals.output_tokens if totals else 0,
                usd=totals.usd_cost if totals else 0.0,
                p95_ms=totals.p95_latency_ms if totals else 0.0,
            )
        )
    return rows, ledger


def render_table(rows: list[ArmRow], episodes: int) -> str:
    """The main-table shape on dev: one row per arm, every cell from stored records."""
    lines = [
        f"Module 06 arm ladder — dev split, {episodes} episodes, horizon {DEMO_HORIZON_LOCAL}.",
        "Scripted LLM transport (canned payloads) and a synthetic accurate-alert stand-in —",
        "the shape is real, the numbers are placeholder-grade and say nothing about merit.",
        "",
        "| Arm | mean norm. reward | fill rate | calls | in tok | out tok | USD | p95 ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.arm_id} | {r.mean_score:.4f} | {r.fill_rate:.4f} | {r.calls} | "
            f"{r.in_tokens} | {r.out_tokens} | {r.usd:.6f} | {r.p95_ms:.1f} |"
        )
    return "\n".join(lines)


def render_headroom(rows: list[ArmRow]) -> str:
    """The control table: the band between stationary OR (arm 1) and the oracle."""
    by_id = {r.arm_id: r for r in rows}
    floor = by_id[ARM1_ARM_ID].mean_score
    ceiling = by_id[ORACLE_ARM_ID].mean_score
    return "\n".join(
        [
            "",
            "Headroom band (dev, placeholder content):",
            f"  stationary OR (arm 1):  {floor:.4f}",
            f"  oracle headroom bound:  {ceiling:.4f}",
            f"  band width:             {ceiling - floor:+.4f}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="dev", choices=["dev"], help="dev only, ever")
    ap.add_argument("--episodes", type=int, default=18)
    ap.add_argument("--table", action="store_true", help="print the main-table shape")
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        instances = dev_instances(root, args.episodes)
        rows, ledger = run_ladder(instances, root)
    ledger.assert_conserved()
    table = render_table(rows, args.episodes) + render_headroom(rows)
    print(table)
    physical = sum(1 for c in ledger.entries if c.physical)
    charged = len(ledger.charged_entries())
    print(
        f"\nledger: physical {physical}, charged {charged}, conserved; "
        f"shared proposal calls across arms 8/9/10 collapse to one physical call each."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
