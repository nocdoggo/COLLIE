"""Task 23 / Checkpoint 2 demo: the arm ladder over dev episodes.

Runs every arm — 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, the three non-LLM controls, and the oracle —
over N dev episodes, prints the main-table shape (one row per arm, every cell populated from
stored records), and balances the ledger across the sweep. Run:

    uv run python -m tools.run_arms --split dev --episodes 18 --table

What this is and is not. It IS the integration proof: one runner, one metered stack, the shared
physical proposal call set, and the headroom band between stationary OR and the oracle. Every
collaborator is the owning module's real implementation — module 02's ``ShockSpecPrompter`` /
``ShockSpecParser``, module 04's ``GridCompiler`` / ``OrCompilerController``, module 05's
``VerifierActivationPolicy`` for arm 10 — so a proposal here is really registry-validated and
really evidence-gated.

It is NOT a result. Two inputs are deliberately synthetic and neither is a missing dependency:
the LLM is a scripted transport serving canned payloads (valid action, default parameters, one
ShockSpec proposal), and the alert channel is one synthetic accurate alert at ``onset - 1``
rather than module 03's bank, so the ladder's shape does not depend on template sampling or on
the bank's noise and decoy conditions. The numbers say nothing about any arm's merit. Arms
8/9/10's activation spread *is* real (the scripted proposal drives them apart by construction,
which is what the divergence test pins).

Only ``dev`` episodes are ever touched; nothing here reads test material. The two upper-bound
arms (AlertSpec parsing, oracle) are constructed with hidden truth by design and run with the
controller-isolation check off — they are the allowlisted exceptions (tests/test_contracts.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from dataclasses import dataclass, replace
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
from collie.arms.shockspec import (
    ARM8_ARM_ID,
    ARM9_ARM_ID,
    ARM10_ARM_ID,
    HeuristicRollbackActivation,
    ImmediateActivation,
    ShockSpecArm,
)
from collie.contracts import (
    AlertKind,
    AlertMessage,
    AnalysisClass,
    ControlConfig,
    EpisodeResult,
    HiddenAlertSpec,
    HiddenIncident,
    InformationCondition,
    ShockFamily,
    Split,
)
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.data.families import generate_episode
from collie.data.splits import CONDITIONS, FAMILIES, Rollout, build_rollouts, build_units
from collie.data.writer import write_pair
from collie.eval.records import write_episode_results_jsonl
from collie.eval.truth import EpisodeTruth, episode_truth_from_incident, write_episode_truth_jsonl
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import RawResponse
from collie.llm.demo import scripted_endpoint
from collie.sim.loader import LoadedInstance, load_instance
from collie.sim.runner import EpisodeRunner
from collie.spec.adapters import ShockSpecParser, ShockSpecPrompter
from collie.trigger.demo import DEMO_HORIZON, build_wrapped
from collie.verify import VerifierActivationPolicy

DEMO_HORIZON_LOCAL = DEMO_HORIZON  # the official synthetic horizon (env contract §1)

# ---------------------------------------------------------------------------
# demo-time LLM content: a scripted transport routing by prompt shape
# ---------------------------------------------------------------------------

_DEMO_ACTION_QTY = 100
"""The scripted direct-action order, a round number near the dev demand level (~100/period)."""

_SPEC_PROPOSAL_MARKER = "bounded ShockSpec"
"""Routes the scripted transport to the ShockSpec payload.

Module 02 owns the real proposal prompt (``collie.spec.prompt.build_prompt``), so the demo does
not invent a prefix of its own: this is a substring of that prompt's first line, and
``tests/test_run_arms.py`` pins that it still matches a freshly built prompt, so a wording change
on module 02's side fails a test instead of silently misrouting to the direct-action payload. A
repair prompt appends to the same text, so attempt 2 routes identically.
"""


class _DemoTransport:
    """Scripted responses by prompt shape. The whole demo's LLM content, clearly labelled."""

    n_calls: int = 0

    @property
    def model_id(self) -> str:
        return "demo-scripted"

    def complete_metered(self, prompt: str, *, decoding, system: str | None = None) -> RawResponse:
        self.n_calls += 1
        if _SPEC_PROPOSAL_MARKER in prompt:
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


def spec_adapters() -> tuple[ShockSpecPrompter, ShockSpecParser]:
    """One module-02 prompter/parser pair, for exactly one arm.

    The pair is per-arm, never shared: ``ShockSpecParser`` validates a proposal against the
    evidence identifiers of its own prompter's last rendered prompt, so two arms sharing a pair
    would validate against each other's evidence set (``collie/spec/adapters.py``). Arms 8/9/10
    still share the *physical* call, because the prompt bytes are a pure function of the visible
    history and the cache keys on them, not on which arm asked.
    """
    prompter = ShockSpecPrompter()
    return prompter, ShockSpecParser(prompter)


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


def _alert_text(incident: HiddenIncident, *, accurate: bool) -> str:
    demand_side = incident.family in (
        ShockFamily.DEMAND_LEVEL,
        ShockFamily.TEMPORARY_PULSE,
        ShockFamily.COMPOUND,
    )
    if not accurate:
        demand_side = not demand_side
    content = "demand increase expected" if demand_side else "shipment delay expected"
    return f"[demo stand-in for module 03] supplier advisory: {content}"


def _demo_alert(instance: LoadedInstance) -> dict[int, AlertMessage]:
    """One synthetic accurate alert at onset-1, the demo's labelled module-03 stand-in.

    The text is family-aware so the keyword-parser control has something to parse: a demand
    phrase on demand-side incidents, a shipment phrase on supply-side ones.
    """
    condition = instance.spec.information_condition or InformationCondition.EARLY_ACCURATE
    if condition is InformationCondition.NO_ALERT:
        return {}
    onset = instance.incident.onset_period if instance.incident else None
    if instance.incident is None:
        period = 10
        return {
            period: AlertMessage(
                alert_id=f"demo_alert_{condition.value}_{period}",
                period=period,
                text="[demo stand-in for module 03] supplier advisory: demand increase expected",
            )
        }
    if onset is None or onset <= 1:
        return {}
    period = onset if condition is InformationCondition.LATE_ACCURATE else onset - 1
    accurate = condition is not InformationCondition.UNRELIABLE
    return {
        period: AlertMessage(
            alert_id=f"demo_alert_{condition.value}_{period}",
            period=period,
            text=_alert_text(instance.incident, accurate=accurate),
        )
    }


def _demo_template_ids(instance: LoadedInstance, alerts: dict[int, AlertMessage]) -> dict[int, str]:
    if not alerts:
        return {}
    condition = instance.spec.information_condition or InformationCondition.EARLY_ACCURATE
    split = instance.spec.split.value if instance.spec.split is not None else "dev"
    return {period: f"tpl_{split}_{condition.value}" for period in alerts}


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


def _attach_calls(
    results: dict[str, list[EpisodeResult]], ledger: CallLedger
) -> dict[str, list[EpisodeResult]]:
    calls: dict[tuple[str, str], list] = {}
    for entry in ledger.charged_entries():
        calls.setdefault((entry.episode_id, entry.arm_id), []).append(entry)
    return {
        arm_id: [
            replace(result, calls=tuple(calls.get((result.episode_id, arm_id), ())))
            for result in arm_results
        ]
        for arm_id, arm_results in results.items()
    }


def run_ladder(
    instances: list[tuple[LoadedInstance, int]],
    root: Path,
    *,
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY,
    return_results: bool = False,
) -> tuple[list[ArmRow], CallLedger] | tuple[list[ArmRow], CallLedger, tuple[EpisodeResult, ...]]:
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
        template_ids = _demo_template_ids(instance, alerts)
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
            (ARM10_ARM_ID, VerifierActivationPolicy(episode_horizon=horizon)),
        ):
            prompter, parser = spec_adapters()
            arms.append(
                (
                    arm_id,
                    ShockSpecArm(
                        channel=channel(arm_id),
                        prompter=prompter,
                        parser=parser,
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
        # The two hidden-truth upper bounds run where the truth-to-vocabulary map is defined,
        # including compound through the compiler's registered joint (both, mixed) shape.
        if instance.incident is not None:
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
                template_ids=template_ids,
                analysis_class=analysis_class,
                check_controller_isolation=isolation,
            )
            outcome = runner.run(controller)
            results.setdefault(arm_id, []).append(outcome.result)

    results = _attach_calls(results, ledger)
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
    if return_results:
        flat = tuple(result for arm_results in results.values() for result in arm_results)
        return rows, ledger, flat
    return rows, ledger


def _interleaved_rollouts() -> tuple[Rollout, ...]:
    grouped: dict[tuple[int, InformationCondition], list[Rollout]] = {}
    for split in (Split.DEV, Split.CAL):
        for rollout in build_rollouts(split):
            if rollout.family is None or rollout.params is None:
                continue
            grouped.setdefault((rollout.family, rollout.information_condition), []).append(rollout)
    ordered: list[Rollout] = []
    for family in FAMILIES:
        for condition in CONDITIONS:
            rows = grouped[(family, condition)]
            dev = [row for row in rows if row.split is Split.DEV]
            cal = [row for row in rows if row.split is Split.CAL]
            for i in range(max(len(dev), len(cal))):
                if i < len(dev):
                    ordered.append(dev[i])
                if i < len(cal):
                    ordered.append(cal[i])
    return tuple(ordered)


def pilot_instances(
    root: Path, episodes: int
) -> tuple[list[tuple[LoadedInstance, int]], tuple[EpisodeTruth, ...]]:
    """Materialise a stratified dev/cal pilot sample and its evaluation-only truth sidecar."""
    if episodes != 120:
        raise ValueError("the generated pilot path is registered for --episodes 120")
    strata = len(FAMILIES) * len(CONDITIONS)
    null_episodes = len(CONDITIONS) * len(FAMILIES)
    shocked_episodes = episodes - null_episodes
    if shocked_episodes % strata != 0:
        raise ValueError(f"--episodes minus null controls must be a multiple of {strata}")
    per_stratum = shocked_episodes // strata
    selected: list[Rollout] = []
    grouped: dict[tuple[int, InformationCondition], list[Rollout]] = {}
    for rollout in _interleaved_rollouts():
        grouped.setdefault((int(rollout.family), rollout.information_condition), []).append(rollout)
    for family in FAMILIES:
        for condition in CONDITIONS:
            rows = grouped[(family, condition)]
            if len(rows) < per_stratum:
                raise ValueError(
                    f"not enough dev/cal rollouts for family {family} / {condition.value}"
                )
            selected.extend(rows[:per_stratum])

    instances: list[tuple[LoadedInstance, int]] = []
    truths: list[EpisodeTruth] = []
    null_conditions = (
        *(InformationCondition.NO_ALERT for _ in range(null_episodes // 2)),
        *(InformationCondition.UNRELIABLE for _ in range(null_episodes // 2)),
    )
    for rollout_index, rollout in enumerate(selected):
        assert rollout.params is not None
        ep = generate_episode(seed=rollout.seed, horizon=DEMO_HORIZON_LOCAL, params=rollout.params)
        write_pair(root, ep, relpath=rollout.rollout_id)
        loaded = load_instance(
            root / rollout.rollout_id,
            episode_id=rollout.rollout_id,
            promised_lead_time=int(rollout.promised_lead_time),
            split=rollout.split,
        )
        spec = replace(
            loaded.spec,
            independent_unit_id=rollout.rollout_id,
            information_condition=rollout.information_condition,
        )
        instance = replace(loaded, spec=spec)
        instances.append((instance, rollout.seed))
        assert instance.incident is not None
        truths.append(
            episode_truth_from_incident(
                instance.spec.episode_id,
                str(instance.spec.independent_unit_id),
                instance.incident,
            )
        )
        if rollout_index < null_episodes:
            condition = null_conditions[rollout_index]
            null_id = (
                f"{rollout.split.value}/null/{rollout_index:02d}/s{rollout.seed}/{condition.value}"
            )
            null_episode_id = f"{rollout.rollout_id}__twin"
            null_loaded = load_instance(
                root / null_episode_id,
                episode_id=null_episode_id,
                promised_lead_time=int(rollout.promised_lead_time),
                split=rollout.split,
            )
            null_spec = replace(
                null_loaded.spec,
                family=ShockFamily.NO_CHANGE,
                independent_unit_id=null_id,
                information_condition=condition,
            )
            instances.append((replace(null_loaded, spec=null_spec), rollout.seed))
    return instances, tuple(truths)


def dev_report_instances(root: Path, episodes: int) -> list[tuple[LoadedInstance, int]]:
    """Materialise balanced dev rollouts for the section-07 report renderer."""
    strata = len(FAMILIES) * len(CONDITIONS)
    if episodes % strata != 0:
        raise ValueError(f"--episodes must be a multiple of {strata} for dev report records")
    per_stratum = episodes // strata
    grouped: dict[tuple[int, InformationCondition], list[Rollout]] = {}
    for rollout in build_rollouts(Split.DEV):
        if rollout.family is None or rollout.params is None:
            continue
        grouped.setdefault((rollout.family, rollout.information_condition), []).append(rollout)

    selected: list[Rollout] = []
    for family in FAMILIES:
        for condition in CONDITIONS:
            rows = grouped[(family, condition)]
            if len(rows) < per_stratum:
                raise ValueError(
                    f"--episodes {episodes} exceeds the dev report pool for family {family} / "
                    f"{condition.value}; max is {len(rows) * strata}"
                )
            selected.extend(rows[:per_stratum])

    instances: list[tuple[LoadedInstance, int]] = []
    for rollout in selected:
        assert rollout.params is not None
        ep = generate_episode(seed=rollout.seed, horizon=DEMO_HORIZON_LOCAL, params=rollout.params)
        write_pair(root, ep, relpath=rollout.rollout_id)
        loaded = load_instance(
            root / rollout.rollout_id,
            episode_id=rollout.rollout_id,
            promised_lead_time=int(rollout.promised_lead_time),
            split=rollout.split,
        )
        spec = replace(
            loaded.spec,
            independent_unit_id=rollout.rollout_id,
            information_condition=rollout.information_condition,
        )
        instances.append((replace(loaded, spec=spec), rollout.seed))
    return instances


@dataclass(frozen=True)
class PilotRunArtifacts:
    results: tuple[EpisodeResult, ...]
    truths: tuple[EpisodeTruth, ...]
    ledger: CallLedger


def run_pilot_artifacts(
    root: Path,
    *,
    episodes: int,
    records_out: Path | None = None,
    truth_out: Path | None = None,
) -> PilotRunArtifacts:
    instances, truths = pilot_instances(root, episodes)
    _rows, ledger, results = run_ladder(
        instances,
        root,
        analysis_class=AnalysisClass.CONFIRMATORY,
        return_results=True,
    )
    ledger.assert_conserved()
    if records_out is not None:
        write_episode_results_jsonl(records_out, results)
    if truth_out is not None:
        write_episode_truth_jsonl(truth_out, truths)
    return PilotRunArtifacts(results=results, truths=truths, ledger=ledger)


def run_dev_record_artifacts(
    root: Path,
    *,
    episodes: int,
    records_out: Path,
    shock_periods_out: Path | None = None,
    baseline_inventory_out: Path | None = None,
) -> tuple[EpisodeResult, ...]:
    instances = dev_report_instances(root, episodes)
    truths = {
        instance.spec.episode_id: episode_truth_from_incident(
            instance.spec.episode_id,
            str(instance.spec.independent_unit_id),
            instance.incident,
        )
        for instance, _seed in instances
        if instance.incident is not None
    }
    _rows, ledger, results = run_ladder(
        instances,
        root,
        analysis_class=AnalysisClass.EXPLORATORY,
        return_results=True,
    )
    ledger.assert_conserved()
    write_episode_results_jsonl(records_out, results)
    if shock_periods_out is not None:
        shock_periods_out.parent.mkdir(parents=True, exist_ok=True)
        shock_periods_out.write_text(
            json.dumps(
                {
                    episode_id: truth.final_shock_period
                    for episode_id, truth in sorted(truths.items())
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    if baseline_inventory_out is not None:
        shock_periods = {
            episode_id: truth.final_shock_period for episode_id, truth in truths.items()
        }
        baselines: dict[str, float] = {}
        for result in results:
            if result.arm_id != ARM1_ARM_ID or result.episode_id not in shock_periods:
                continue
            post_shock = [
                record.on_hand_end
                for record in result.records
                if record.period > shock_periods[result.episode_id]
            ]
            baselines[result.episode_id] = sum(post_shock) / len(post_shock) if post_shock else 0.0
        baseline_inventory_out.parent.mkdir(parents=True, exist_ok=True)
        baseline_inventory_out.write_text(
            json.dumps(baselines, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return results


def render_table(rows: list[ArmRow], episodes: int) -> str:
    """The main-table shape on dev: one row per arm, every cell from stored records."""
    lines = [
        f"Module 06 arm ladder — dev split, {episodes} episodes, horizon {DEMO_HORIZON_LOCAL}.",
        "Real collaborators throughout: module 02's prompter/parser, module 04's compiler and",
        "controller, module 05's verifier activation policy on arm 10. Synthetic by choice:",
        "a scripted LLM transport (canned payloads) and one accurate alert at onset-1 — so the",
        "shape is real and the numbers are placeholder-grade, saying nothing about merit.",
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


@dataclass(frozen=True)
class ProposalSharing:
    """Measured call sharing across arms 8/9/10, rather than an asserted collapse factor.

    Every proposal decision point is charged to all three arms, so ``charged == 3 * points``
    always. ``physical`` is only equal to ``points`` when all three arms rendered identical
    prompt bytes there — true for the first proposal, where the three have not yet diverged,
    and false for a second proposal after their own orders have moved the observable state
    the module-02 prompt reports. Printing the measurement keeps the demo from claiming a
    uniform collapse it does not have.
    """

    points: int
    physical: int
    charged: int


def proposal_sharing(ledger: CallLedger) -> ProposalSharing:
    """Restrict the ledger to arms 8/9/10 and count decision points, physical, and charged."""
    spec_arms = {ARM8_ARM_ID, ARM9_ARM_ID, ARM10_ARM_ID}
    charged = [c for c in ledger.charged_entries() if c.arm_id in spec_arms]
    points = {(c.episode_id, c.period, c.attempt_index) for c in charged}
    return ProposalSharing(
        points=len(points),
        physical=sum(1 for c in ledger.entries if c.physical and c.arm_id in spec_arms),
        charged=len(charged),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="dev", choices=["dev"], help="dev only, ever")
    ap.add_argument("--episodes", type=int, default=18)
    ap.add_argument("--table", action="store_true", help="print the main-table shape")
    ap.add_argument(
        "--records-out",
        type=Path,
        help="write balanced dev EpisodeResult JSONL for collie.eval.report",
    )
    ap.add_argument(
        "--shock-periods-out",
        type=Path,
        help="write JSON episode_id -> final shock period for report recovery metrics",
    )
    ap.add_argument(
        "--baseline-inventory-out",
        type=Path,
        help="write JSON episode_id -> arm-1 post-shock baseline inventory for report metrics",
    )
    args = ap.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if args.records_out is not None:
            results = run_dev_record_artifacts(
                root,
                episodes=args.episodes,
                records_out=args.records_out,
                shock_periods_out=args.shock_periods_out,
                baseline_inventory_out=args.baseline_inventory_out,
            )
            print(f"wrote dev records: {args.records_out} ({len(results)} arm-episode rows)")
            return 0
        instances = dev_instances(root, args.episodes)
        rows, ledger = run_ladder(instances, root)
    ledger.assert_conserved()
    table = render_table(rows, args.episodes) + render_headroom(rows)
    print(table)
    physical = sum(1 for c in ledger.entries if c.physical)
    charged = len(ledger.charged_entries())
    sharing = proposal_sharing(ledger)
    print(
        f"\nledger: physical {physical}, charged {charged}, conserved.\n"
        f"arms 8/9/10 proposals: {sharing.points} decision points, {sharing.charged} charged "
        f"copies, {sharing.physical} physical — identical prompt bytes share one physical call, "
        f"and a second proposal stops sharing once the arms' own orders diverge."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
