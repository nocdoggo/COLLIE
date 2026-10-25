"""The evaluation runner: ``plan-b eval run`` (``08_evaluation.md``, the authoritative protocol).

One run executes one suite (``campus`` or ``pantry``) over a set of cases and policies:

* P0 (the profile's deterministic baseline) once per case, and P1, P2 and P3 once per seed;
* within each case the order of those runs is shuffled by a ``random.Random`` seeded from the
  recorded order seed and the case reference, and the order is written into ``plan.json``;
* every episode runs in its own process (``--jobs`` at a time, ``spawn`` start method), with a
  fresh SQLite database and a fresh policy instance, so no state, memory or model response is
  shared; nothing caches model responses;
* an episode that reaches a cap, times out (``EPISODE_TIMEOUT_S`` of wall time) or crashes stays
  in the results as that outcome; one the harness stopped (the cumulative spend cap, the
  endpoint configuration) is ``aborted``, not scored, and rerun by a resume;
* the run is bound to the measured code, held-out cases and model it started under
  (``plan.json``); an episode process that finds them changed records nothing and the run stops;
* rerunning the same command on the same results directory skips finished episodes.

Truth split. Each episode writes a public record (``episodes/<key>/record.json``), its sanitized
trace (``episodes/<key>/trace.json.gz``, verified before it is written) and an evaluator-side
record (``runner_private/<key>.runner.json``). The public record never carries
``matches_expectation``, predicates, the expected outcome, the evaluator case id, the staff
schedule or anything else from the private case; those go only to ``runner_private/``.

Held-out cases. Every ``*.eval.json`` under ``scenarios/private/eval/`` is the evaluator data
of one held-out case (``EvalCase``): its evaluator id (``C01``..., ``T01``...), the opaque
``case_ref`` of its private case file ``<case_ref>.json`` beside it, its outcome class, the
negative-control designation, recovery data and the message annotations. A case's public
fixture is a development fixture or a file under ``scenarios/public/eval/``. The frozen loaders
(``plan_b.world.world`` and ``plan_b.domain.fixtures``) read only the development directories,
so a run that includes held-out cases installs them into each episode process: the private
cases are copied, together with the development cases, into ``runner_private/cases/``, which
becomes ``plan_b.world.world.PRIVATE_DIR``, and the public fixtures are added to
``plan_b.domain.fixtures.PUBLIC_SCENARIOS``. A held-out run starts only when ``freeze.json``
and ``heldout.json`` both verify and its seeds, policies, caps, timeout, order seed and model
match the freeze.
"""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import importlib
import inspect
import json
import multiprocessing
import os
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from multiprocessing.connection import wait
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from plan_b.evaluation import manifest as mf

if TYPE_CHECKING:
    from plan_b.evaluation.policies.base import Policy
    from plan_b.scenarios.policy_host import EpisodeCaps

RECORD_VERSION = "plan_b.eval_episode/1.0.0"
PRIVATE_RECORD_VERSION = "plan_b.eval_episode_private/1.0.0"
PLAN_ARTIFACT = "plan_b.eval_run_plan"
SUITES = ("campus", "pantry")
OUTCOME_CLASSES = {"campus": ("goal", "infeasible"), "pantry": ("target", "partial")}
POLICY_KEYS = tuple(mf.POLICY_CHOICES)
EVAL_SUFFIX = ".eval.json"
STATUSES = ("completed", "capped", "timeout", "crashed", "aborted")
MESSAGE_CHARS = 300
# An episode process that found the measured code, the held-out cases or the model changed since
# the run started exits with this code and records nothing; the run stops launching episodes.
DRIFT_EXIT = 3
# The protocol's case ids, their outcome classes and the designated negative controls
# (``08_evaluation.md``): a held-out case must carry one of them, in its suite.
CASE_CLASSES = {
    "campus": {f"C0{i}": "goal" for i in range(1, 8)} | {"C08": "infeasible"},
    "pantry": {"T01": "target", "T02": "target", "T03": "partial", "T04": "partial"},
}
NEGATIVE_CONTROLS = frozenset({"C02", "C03", "C04"})
# Wave 3b: a later held-out set uses later ids of the same form (C09 and up, T05 and up). The
# table above stays the rule for the ids it names. A later id takes its outcome class and its
# negative-control flag from its evaluator file, checked against its suite's classes, and a
# negative control still needs its evidence and the original-plan replay at the lock.
CASE_ID_FORMS = {"campus": re.compile(r"^C[0-9]{2}$"), "pantry": re.compile(r"^T[0-9]{2}$")}
# Words that would reveal a condition; a held-out case ref or public scenario id must be opaque.
REVEALING = (
    "alarm",
    "conflict",
    "control",
    "deficit",
    "delay",
    "duplicate",
    "expect",
    "false",
    "forged",
    "infeasib",
    "late",
    "negative",
    "outage",
    "partial",
    "quiet",
    "shortfall",
    "stale",
    "truth",
    "unavailab",
    "wrong",
)

# A hook for dry runs: ``(choice, profile_id, seed, caps, work_dir) -> policy factory`` builds a
# model-driven policy around a scripted provider. Never allowed on held-out cases.
PolicyFactoryHook = Callable[[str, str, "int | None", "EpisodeCaps", Path], Callable[[], "Policy"]]


class RunRefused(RuntimeError):
    """The run cannot start (drift, an unknown case, a different plan in the directory...)."""


# ---------------------------------------------------------------------------------- evaluator data


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MessageAnnotation(_Model):
    """What one message's text states (``08_evaluation.md``, "Extraction and decision errors").
    It describes the text, not hidden truth. ``source_record_id`` is the record id the delivered
    observation carries; ``claimed_change`` uses the readings' change kinds (``delay``,
    ``unavailability``, ``availability``, ``attendance_change``, ``priority_change``, or
    ``no_change`` for a text that states no supported claim)."""

    source_record_id: str
    event_id: str | None = None
    resource_id: str | None = None
    effective_time: str | None = None
    claimed_change: str
    source_id: str | None = None
    booking_ref: str | None = None
    unknown_fields: tuple[str, ...] = ()
    note: str | None = None


class EvalCase(_Model):
    """Evaluator data of one held-out case (``<case_ref>.eval.json``). Never agent-visible."""

    artifact: Literal["plan_b.eval_case"]
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.\-]{1,32}$")
    case_ref: str = Field(pattern=r"^[A-Za-z0-9_.\-]{1,64}$")
    suite: Literal["campus", "pantry"]
    condition: str
    outcome_class: Literal["goal", "infeasible", "target", "partial"]
    negative_control: bool = False
    negative_control_evidence: str | None = None
    requires_recovery: bool = False
    actionable_record_ids: tuple[str, ...] = ()
    target_quantity: int | None = None
    achievable_on_time: int | None = None
    annotations: tuple[MessageAnnotation, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class CaseSpec:
    """A resolved case: where its files are and what the evaluator knows about it."""

    case_ref: str
    case_id: str
    suite: str
    heldout: bool
    scenario_id: str
    profile_id: str
    outcome_class: str
    case_file: Path
    public_file: Path
    eval_file: Path | None = None
    condition: str | None = None
    negative_control: bool = False
    negative_control_evidence: str | None = None
    requires_recovery: bool = False
    actionable_record_ids: tuple[str, ...] = ()
    target_quantity: int | None = None
    achievable_on_time: int | None = None
    annotations: tuple[dict[str, Any], ...] = ()

    def evaluator(self) -> dict[str, Any]:
        """The evaluator-only view (``runner_private/cases.json``)."""
        return {
            "case_ref": self.case_ref,
            "case_id": self.case_id,
            "suite": self.suite,
            "heldout": self.heldout,
            "condition": self.condition,
            "outcome_class": self.outcome_class,
            "negative_control": self.negative_control,
            "negative_control_evidence": self.negative_control_evidence,
            "requires_recovery": self.requires_recovery,
            "actionable_record_ids": list(self.actionable_record_ids),
            "target_quantity": self.target_quantity,
            "achievable_on_time": self.achievable_on_time,
            "annotations": list(self.annotations),
            "scenario_id": self.scenario_id,
            "profile_id": self.profile_id,
        }


def _suite_of(profile_id: str) -> str:
    from plan_b.domain.adapters.registry import CAMPUS_PROFILES, PANTRY_PROFILES

    if profile_id in CAMPUS_PROFILES:
        return "campus"
    if profile_id in PANTRY_PROFILES:
        return "pantry"
    raise RunRefused(f"profile {profile_id!r} belongs to no evaluation suite")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunRefused(f"{path.name} is unreadable: {exc}") from None


def heldout_public_fixtures(public_dir: Path | None = None) -> dict[str, Path]:
    """``{scenario_id: file}`` of the public fixtures under ``scenarios/public/eval/``, its
    subdirectories included (a later held-out set may keep its files in one, Wave 3b)."""
    from plan_b.domain.fixtures import PUBLIC_SCENARIOS

    root = public_dir or mf.HELDOUT_PUBLIC_DIR
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*.json")) if root.is_dir() else []:
        data = _read_json(path)
        if not isinstance(data, dict) or data.get("artifact") != "plan_b.public_scenario":
            continue
        sid = data.get("scenario_id")
        if not isinstance(sid, str) or sid in found or sid in PUBLIC_SCENARIOS:
            raise RunRefused(f"{path.name}: scenario id {sid!r} is missing or already taken")
        found[sid] = path
    return found


def _public_file(scenario_id: str, heldout_public: dict[str, Path]) -> Path:
    from plan_b.domain.fixtures import public_scenario_path

    if scenario_id in heldout_public:
        return heldout_public[scenario_id]
    try:
        return public_scenario_path(scenario_id)
    except KeyError:
        raise RunRefused(f"no public fixture for scenario {scenario_id!r}") from None


def _opaque_problem(name: str, case_id: str) -> str | None:
    """Why an agent- or public-visible identifier is not opaque, or None."""
    low = name.lower()
    if case_id.lower() in low or re.search(r"(^|[^a-z0-9])[ct][0-9]{2}([^0-9]|$)", low):
        return f"{name!r} names a case id"
    hit = next((w for w in REVEALING if w in low), None)
    return f"{name!r} contains the revealing word {hit!r}" if hit else None


def _world_digest(case: Any) -> str:
    """What an episode's world is made of beyond the public fixture: statuses, world events
    and scripted actors."""
    parts = [case.status_model, case.world_events, case.actor_scripts]
    text = json.dumps([[x.model_dump(mode="json") for x in part] for part in parts], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def heldout_specs(
    private_dir: Path | None = None, public_dir: Path | None = None
) -> list[CaseSpec]:
    """Every held-out case, validated the way the runner loads it, in ``scenarios/private/eval/``
    and its subdirectories (Wave 3b: a later set may keep its files in one). A private case
    without evaluator data, evaluator data without its case, or a case ref used twice, is an
    error, never a silent omission."""
    from plan_b.domain.models import PrivateCase, PublicScenario
    from plan_b.world.validate import validate_case
    from plan_b.world.world import available_cases

    root = private_dir or mf.HELDOUT_PRIVATE_DIR
    if not root.is_dir():
        return []
    public = heldout_public_fixtures(public_dir)
    cases: dict[str, Path] = {}
    evals: dict[str, tuple[EvalCase, Path]] = {}
    for path in sorted(root.rglob("*.json")):
        data = _read_json(path)
        artifact = data.get("artifact") if isinstance(data, dict) else None
        if path.name.endswith(EVAL_SUFFIX):
            try:
                ev = EvalCase.model_validate(data)
            except ValueError as exc:
                raise RunRefused(f"{path.name}: invalid evaluator data: {exc}") from None
            if path.name != f"{ev.case_ref}{EVAL_SUFFIX}":
                raise RunRefused(
                    f"{path.name}: evaluator data must be named {ev.case_ref}.eval.json"
                )
            if ev.case_ref in evals:
                raise RunRefused(f"{path.name}: case ref {ev.case_ref} has two evaluator files")
            evals[ev.case_ref] = (ev, path)
        elif artifact == "plan_b.private_case":
            if path.stem in cases:
                raise RunRefused(f"{path.name}: case ref {path.stem} has two case files")
            cases[path.stem] = path
    dev = set(available_cases())
    problems = [f"held-out case {r} has no evaluator data" for r in sorted(set(cases) - set(evals))]
    problems += [f"evaluator data {r} has no case file" for r in sorted(set(evals) - set(cases))]
    problems += [
        f"held-out case {r} reuses a development case ref" for r in sorted(set(cases) & dev)
    ]
    if problems:
        raise RunRefused("; ".join(problems))
    from plan_b.world.world import load_case

    developed = {_world_digest(load_case(r)): r for r in sorted(dev)}
    specs: list[CaseSpec] = []
    seen_ids: dict[tuple[str, str], str] = {}
    for ref in sorted(cases):
        ev, eval_path = evals[ref]
        case = PrivateCase.model_validate_json(cases[ref].read_text(encoding="utf-8"))
        if case.case_ref != ref:
            raise RunRefused(f"{cases[ref].name}: its case_ref is {case.case_ref!r}")
        if (copied := developed.get(_world_digest(case))) is not None:
            raise RunRefused(f"held-out case {ref} repeats the world of development case {copied}")
        named = [ref, *([case.scenario_id] if case.scenario_id in public else [])]
        opaque = [why for n in named if (why := _opaque_problem(n, ev.case_id))]
        if opaque:
            raise RunRefused(
                f"held-out case {ref}: identifiers must be opaque: {'; '.join(opaque)}"
            )
        public_path = _public_file(case.scenario_id, public)
        scenario = PublicScenario.model_validate_json(public_path.read_text(encoding="utf-8"))
        issues = validate_case(scenario, case)
        if issues:
            raise RunRefused(f"held-out case {ref} failed validation: " + "; ".join(issues))
        suite = _suite_of(scenario.profile_id)
        if suite != ev.suite or ev.outcome_class not in OUTCOME_CLASSES[suite]:
            raise RunRefused(
                f"held-out case {ref}: suite or outcome class does not fit its profile"
            )
        protocol = CASE_CLASSES[suite]
        if ev.case_id in protocol or not CASE_ID_FORMS[suite].match(ev.case_id):
            if protocol.get(ev.case_id) != ev.outcome_class:
                raise RunRefused(
                    f"held-out case {ref}: {ev.case_id} is not a {suite} case of the protocol"
                    f" with outcome class {ev.outcome_class}"
                )
            if ev.negative_control != (ev.case_id in NEGATIVE_CONTROLS):
                raise RunRefused(
                    f"held-out case {ref}: the designated negative controls are C02, C03 and C04"
                )
        if ev.negative_control and not (ev.negative_control_evidence or "").strip():
            raise RunRefused(
                f"held-out case {ref}: a negative control states why its original plan stays"
                " feasible (negative_control_evidence)"
            )
        if (suite, ev.case_id) in seen_ids:
            raise RunRefused(
                f"case id {ev.case_id} is used by {seen_ids[(suite, ev.case_id)]} and {ref}"
            )
        seen_ids[(suite, ev.case_id)] = ref
        specs.append(
            CaseSpec(
                case_ref=ref,
                case_id=ev.case_id,
                suite=suite,
                heldout=True,
                scenario_id=case.scenario_id,
                profile_id=scenario.profile_id,
                outcome_class=ev.outcome_class,
                case_file=cases[ref],
                public_file=public_path,
                eval_file=eval_path,
                condition=ev.condition,
                negative_control=ev.negative_control,
                negative_control_evidence=ev.negative_control_evidence,
                requires_recovery=ev.requires_recovery,
                actionable_record_ids=ev.actionable_record_ids,
                target_quantity=ev.target_quantity,
                achievable_on_time=ev.achievable_on_time,
                annotations=tuple(a.model_dump(mode="json") for a in ev.annotations),
            )
        )
    return specs


def development_spec(case_ref: str) -> CaseSpec:
    """A development case's evaluator view, derived from its private case (for dry runs; never
    reported): the outcome class from its expected outcome, a recovery required on a completable
    case unless a predicate expects no applied plan, the achievable on-time quantity from its
    service predicate. No negative-control designation and no annotations."""
    from plan_b.domain.fixtures import load_public_scenario, public_scenario_path
    from plan_b.world.world import case_path, load_case

    case = load_case(case_ref)
    profile = load_public_scenario(case.scenario_id).profile_id
    suite = _suite_of(profile)
    complete = case.expected_outcome == "goal_complete"
    outcome_class = {"campus": ("goal", "infeasible"), "pantry": ("target", "partial")}[suite][
        0 if complete else 1
    ]
    params = {p.kind: p.params for p in case.outcome_predicates}
    plans = params.get("applied_plan_count", {}).get("count")
    on_time = params.get("service_on_time_equals", {}).get("quantity")
    return CaseSpec(
        case_ref=case_ref,
        case_id=case_ref,
        suite=suite,
        heldout=False,
        scenario_id=case.scenario_id,
        profile_id=profile,
        outcome_class=outcome_class,
        case_file=case_path(case_ref),
        public_file=public_scenario_path(case.scenario_id),
        condition=None,
        requires_recovery=complete and plans != 0,
        achievable_on_time=on_time if isinstance(on_time, int) and not complete else None,
    )


def resolve_cases(suite: str, ids: Sequence[str] | None) -> tuple[bool, list[CaseSpec]]:
    """``(heldout, specs)`` for ``--cases``: held-out cases by evaluator id or opaque ref (all
    of the suite when ``ids`` is empty), or development case refs. Mixing them is refused."""
    from plan_b.world.world import available_cases

    if suite not in SUITES:
        raise RunRefused(f"unknown suite {suite!r}; choose campus or pantry")
    if ids and len(set(ids)) != len(ids):
        raise RunRefused("a case is named twice")
    dev = set(available_cases())
    if ids and all(i in dev for i in ids):
        specs = [development_spec(i) for i in ids]
        wrong = [s.case_ref for s in specs if s.suite != suite]
        if wrong:
            raise RunRefused(f"not {suite} cases: {', '.join(wrong)}")
        return False, specs
    heldout = [s for s in heldout_specs() if s.suite == suite]
    if not ids:
        if not heldout:
            raise RunRefused(
                f"no held-out {suite} case exists; name development cases with --cases"
            )
        return True, heldout
    by_id = {s.case_id: s for s in heldout} | {s.case_ref: s for s in heldout}
    unknown = [i for i in ids if i not in by_id and i not in dev]
    if unknown:
        raise RunRefused(f"unknown {suite} case(s): {', '.join(unknown)}")
    if any(i not in by_id for i in ids):
        raise RunRefused("a run is either held-out or development; do not mix the two")
    chosen = [by_id[i] for i in ids]
    if len({s.case_ref for s in chosen}) != len(chosen):
        raise RunRefused("a case is named twice")
    return True, chosen


# ---------------------------------------------------------------------------------- loader install


@dataclass
class CaseRegistry:
    """Makes held-out cases loadable by the frozen loaders inside one process."""

    private_dir: Path
    # scenario_id -> path relative to scenarios/public (absolute for a fixture elsewhere, which
    # ``PUBLIC_DIR / path`` resolves to itself; the tests' temporary held-out directories)
    public: dict[str, str]
    _saved: tuple[Path, dict[str, str]] | None = None

    @classmethod
    def build(cls, work: Path, specs: Sequence[CaseSpec]) -> CaseRegistry:
        """Copy the development and held-out private cases into ``<work>/cases`` (evaluator
        side: the run puts it under ``runner_private/``)."""
        from plan_b.domain.fixtures import PUBLIC_DIR
        from plan_b.world import world

        target = work / "cases"
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for path in sorted(world.PRIVATE_DIR.glob("*.json")):
            shutil.copyfile(path, target / path.name)
        public: dict[str, str] = {}
        for spec in specs:
            if spec.heldout:
                shutil.copyfile(spec.case_file, target / f"{spec.case_ref}.json")
                file = spec.public_file.resolve()
                root = PUBLIC_DIR.resolve()
                public[spec.scenario_id] = (
                    file.relative_to(root).as_posix() if file.is_relative_to(root) else str(file)
                )
        return cls(private_dir=target, public=public)

    def install(self) -> None:
        from plan_b.domain import fixtures
        from plan_b.world import world

        if self._saved is None:
            self._saved = (world.PRIVATE_DIR, dict(fixtures.PUBLIC_SCENARIOS))
        world.PRIVATE_DIR = self.private_dir
        for sid, rel in self.public.items():
            if fixtures.PUBLIC_SCENARIOS.get(sid, rel) != rel:
                raise RunRefused(f"scenario id {sid!r} is already registered")
            fixtures.PUBLIC_SCENARIOS[sid] = rel
        world.load_case.cache_clear()

    def uninstall(self) -> None:
        from plan_b.domain import fixtures
        from plan_b.world import world

        if self._saved is None:
            return
        world.PRIVATE_DIR, saved = self._saved
        fixtures.PUBLIC_SCENARIOS.clear()
        fixtures.PUBLIC_SCENARIOS.update(saved)
        world.load_case.cache_clear()
        self._saved = None

    @contextmanager
    def installed(self) -> Iterator[CaseRegistry]:
        self.install()
        try:
            yield self
        finally:
            self.uninstall()


class _KeepOriginalPlan:
    """The evaluator's replay coordinator: it reads nothing and changes nothing."""

    policy_id = "evaluator-replay/keep-original-plan"

    def run(self, client: Any, max_tool_calls: int = 16) -> Any:
        from plan_b.domain.models import PolicyRunResult

        return PolicyRunResult(
            policy_id=self.policy_id, status="waiting", decisions=(), tool_calls=0
        )


def replay_original_plan(spec: CaseSpec) -> dict[str, Any]:
    """Run a case with a coordinator that changes nothing, in this process and a temporary
    database: whether the original plan completes the goal with no executed violation. The
    evaluator's replay behind a negative-control designation (``08_evaluation.md``)."""
    import tempfile

    from plan_b.scenarios.runner import run_case
    from plan_b.store.database import Database

    with tempfile.TemporaryDirectory(prefix="plan_b_replay_") as tmp:
        registry = CaseRegistry.build(Path(tmp), [spec]) if spec.heldout else None
        with registry.installed() if registry is not None else contextlib.nullcontext():
            result = run_case(
                Database(Path(tmp) / "replay.sqlite3"),
                spec.case_ref,
                policy_factory=_KeepOriginalPlan,
            )
    report = result.report
    return {
        "coordinator": _KeepOriginalPlan.policy_id,
        "original_plan_completes": bool(report.goal_complete) and not report.violations,
        "goal_complete": report.goal_complete,
        "violations": len(report.violations),
        "applied_plans": report.applied_plans,
    }


# ---------------------------------------------------------------------------------- the plan


@dataclass(frozen=True)
class Episode:
    key: str
    case_ref: str
    policy: str  # P0..P3
    seed: int | None
    trial: int
    position: int  # 1-based position of this run within its case's shuffled order

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "case_ref": self.case_ref,
            "policy": self.policy,
            "choice": mf.POLICY_CHOICES[self.policy],
            "seed": self.seed,
            "trial": self.trial,
            "position": self.position,
        }


def episode_key(case_ref: str, policy: str, seed: int | None) -> str:
    return f"{case_ref}__{policy}__{'once' if seed is None else f's{seed}'}"


def build_plan(
    case_refs: Sequence[str], policies: Sequence[str], seeds: Sequence[int], order_seed: int
) -> list[Episode]:
    """P0 once per case, P1-P3 once per seed; the runs of each case in a shuffled order drawn
    from ``random.Random(f"{order_seed}:{case_ref}")`` over all four policies, so a run of a
    subset keeps the positions its episodes have in the full order (a comparison assembled
    from several such runs is not order-randomized; ``plan.json`` says when a run is one)."""
    episodes: list[Episode] = []
    for ref in case_refs:
        runs: list[tuple[str, int | None, int]] = []
        for policy in POLICY_KEYS:
            if policy == "P0":
                runs.append(("P0", None, 1))
            else:
                runs += [(policy, seed, i) for i, seed in enumerate(seeds, start=1)]
        random.Random(f"{order_seed}:{ref}").shuffle(runs)
        episodes += [
            Episode(episode_key(ref, p, s), ref, p, s, trial, position)
            for position, (p, s, trial) in enumerate(runs, start=1)
            if p in policies
        ]
    return episodes


def _parse_policies(policies: Sequence[str]) -> list[str]:
    out = [p.strip().upper() for p in policies if p.strip()]
    unknown = [p for p in out if p not in POLICY_KEYS]
    if unknown or not out or len(set(out)) != len(out):
        raise RunRefused(f"policies must be distinct names among {', '.join(POLICY_KEYS)}")
    return sorted(out)


def seed_supported() -> bool:
    """Whether ``run_case`` takes the keyword-only ``seed`` (the provider's ``seed`` parameter)."""
    from plan_b.scenarios.runner import run_case

    return "seed" in inspect.signature(run_case).parameters


def _app_tree_clean() -> bool | None:
    try:
        done = subprocess.run(
            ["git", "status", "--porcelain", "--", "."],
            cwd=mf.APP_DIR,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() == "" if done.returncode == 0 else None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def record_path(out: Path, key: str) -> Path:
    return out / "episodes" / key / "record.json"


def trace_path(out: Path, key: str) -> Path:
    return out / "episodes" / key / "trace.json.gz"


def private_path(out: Path, key: str) -> Path:
    return out / "runner_private" / f"{key}.runner.json"


def has_records(out: Path, key: str) -> bool:
    """Both records of an episode exist: its public record (written last) and its
    evaluator-side record."""
    try:
        json.loads(record_path(out, key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return private_path(out, key).is_file()


def finished(out: Path, key: str) -> bool:
    """An episode is finished when it has both records and the harness did not abort it (an
    ``aborted`` episode is rerun by a resume)."""
    return has_records(out, key) and _status_of(out, key) != "aborted"


# ---------------------------------------------------------------------------------- guards


# The model configuration a run is bound to (the cumulative spend cap is a budget that may be
# raised to resume a run it stopped, so it is recorded but not bound).
MODEL_KEYS = ("provider", "model_id", "base_url", "max_run_cost_usd")


@dataclass
class FrozenSettings:
    caps: dict[str, int]
    timeout_s: float
    model: dict[str, Any] | None
    freeze: dict[str, Any] = field(default_factory=dict)
    heldout: dict[str, Any] = field(default_factory=dict)


def scoped_heldout_cases(heldout_path: Path, suite: str) -> list[str] | None:
    """The default ``--cases`` of a held-out run under a case-scoped lock: the lock's cases of
    ``suite``. None when the lock is missing, unreadable or not case-scoped (``check_frozen``
    reports those), so the default stays every held-out case of the suite."""
    try:
        lock = mf.load_manifest(heldout_path, mf.HELDOUT_ARTIFACT)
    except mf.FreezeError:
        return None
    if mf.case_scope(lock) is None:
        return None
    ids = [c["case_id"] for c in lock.get("suites", {}).get(suite, [])]
    if not ids:
        raise RunRefused(f"{heldout_path.name} locks no {suite} case")
    return ids


def check_frozen(
    *,
    specs: Sequence[CaseSpec],
    policies: Sequence[str],
    seeds: Sequence[int],
    order_seed: int,
    timeout_s: float | None,
    freeze_path: Path,
    heldout_path: Path,
) -> FrozenSettings:
    """Refuse a held-out run on any drift or any departure from the frozen protocol."""
    freeze_check = mf.verify_freeze(freeze_path)
    heldout_check = mf.verify_heldout(heldout_path)
    problems = [*freeze_check.drift, *heldout_check.drift]
    if problems:
        raise RunRefused("the freeze does not verify: " + "; ".join(problems))
    freeze = mf.load_manifest(freeze_path, mf.FREEZE_ARTIFACT)
    lock = mf.load_manifest(heldout_path, mf.HELDOUT_ARTIFACT)
    # The lock binds the whole freeze manifest (seeds, order seed, model and caps included),
    # not only its file hashes: an edited freeze.json is drift.
    if lock.get("freeze_files_sha256") != freeze["files_sha256"] or lock.get(
        "freeze_sha256"
    ) != mf.manifest_digest(freeze_path):
        problems.append(f"{heldout_path.name} was locked against a different freeze")
    locked = {(s, c["case_ref"]): c for s, cases in lock["suites"].items() for c in cases}
    for spec in specs:
        entry = locked.get((spec.suite, spec.case_ref))
        if entry is None or entry["case_id"] != spec.case_id:
            problems.append(
                f"case {spec.case_ref} ({spec.case_id}) is not in the held-out lock"
                f" {heldout_path.name}"
            )
    if list(seeds) != list(freeze["seeds"]):
        problems.append(f"seeds {list(seeds)} are not the frozen {freeze['seeds']}")
    if int(order_seed) != int(freeze["order_seed"]):
        problems.append(f"order seed {order_seed} is not the frozen {freeze['order_seed']}")
    if timeout_s is not None and float(timeout_s) != float(freeze["episode_timeout_s"]):
        problems.append("the episode timeout is not the frozen one")
    if set(policies) - set(freeze["policies"]):
        problems.append("a policy outside the frozen set")
    if problems:
        raise RunRefused("; ".join(problems))
    return FrozenSettings(
        caps=dict(freeze["episode_caps"]),
        timeout_s=float(freeze["episode_timeout_s"]),
        model=dict(freeze["model"]),
        freeze=freeze_check.as_dict()
        | {"files_sha256": freeze["files_sha256"], "sha256": mf.manifest_digest(freeze_path)},
        heldout=heldout_check.as_dict()
        | {"files_sha256": lock["files_sha256"], "sha256": mf.manifest_digest(heldout_path)},
    )


def _model_config_public(
    policies: Sequence[str], frozen_model: dict[str, Any] | None, hook: str | None
) -> dict[str, Any] | None:
    """Load the endpoint configuration once (no key read) for a run with model policies, and
    check it against the frozen model."""
    if hook is not None or not set(policies) - {"P0"}:
        return None
    from plan_b.agent.config import ModelConfigError, load_model_config

    try:
        cfg = load_model_config()
    except ModelConfigError as exc:
        raise RunRefused(f"the model policies are not configured: {exc}") from None
    public = cfg.public()
    if frozen_model is not None:
        for key in MODEL_KEYS:  # a None in the freeze must match too: never a wildcard
            if frozen_model.get(key) != public.get(key):
                raise RunRefused(f"the configured {key} is not the frozen one")
    return {k: public[k] for k in MODEL_KEYS} | {"max_total_cost_usd": public["max_total_cost_usd"]}


# ---------------------------------------------------------------------------------- the run


@dataclass
class RunSummary:
    out: Path
    planned: int
    skipped: int
    ran: int
    statuses: dict[str, int]
    heldout: bool


def run_evaluation(
    *,
    suite: str,
    cases: Sequence[str] | None,
    policies: Sequence[str],
    seeds: Sequence[int],
    out: Path,
    jobs: int = 1,
    order_seed: int | None = None,
    timeout_s: float | None = None,
    policy_factory: str | None = None,
    freeze_path: Path = mf.FREEZE_PATH,
    heldout_path: Path = mf.HELDOUT_PATH,
    log: Callable[[str], None] = print,
) -> RunSummary:
    """Run (or resume) one suite into ``out``; see the module docstring."""
    from plan_b.evaluation.manifest import DEFAULT_ORDER_SEED

    if jobs < 1:
        raise RunRefused("--jobs must be at least 1")
    chosen = _parse_policies(policies)
    seed_list = [int(s) for s in seeds]
    if set(chosen) - {"P0"} and (
        not 1 <= len(seed_list) <= 3 or len(set(seed_list)) != len(seed_list)
    ):
        raise RunRefused("give one to three distinct seeds (the protocol preregisters three)")
    if not cases:  # a case-scoped held-out lock names the default cases
        cases = scoped_heldout_cases(heldout_path, suite)
    heldout, specs = resolve_cases(suite, cases)
    order = DEFAULT_ORDER_SEED if order_seed is None else int(order_seed)
    if heldout:
        if policy_factory is not None:
            raise RunRefused("scripted policy factories are for development dry runs only")
        if len(seed_list) != 3:
            raise RunRefused("a held-out run uses the three frozen seeds")
        frozen = check_frozen(
            specs=specs,
            policies=chosen,
            seeds=seed_list,
            order_seed=order,
            timeout_s=timeout_s,
            freeze_path=freeze_path,
            heldout_path=heldout_path,
        )
    else:
        verification = mf.verify_freeze(freeze_path)
        frozen = FrozenSettings(
            caps=mf.episode_caps(),
            timeout_s=float(timeout_s or mf.EPISODE_TIMEOUT_S),
            model=None,
            freeze=verification.as_dict(),
        )
    model = _model_config_public(chosen, frozen.model, policy_factory)
    episodes = build_plan([s.case_ref for s in specs], chosen, seed_list, order)
    # The run is bound to the code, cases and model it started under: a resume under others is
    # refused, and each episode process checks them again before it runs.
    measured = mf.tree_hash(mf.measured_files())
    heldout_dirs = (str(mf.HELDOUT_PRIVATE_DIR), str(mf.HELDOUT_PUBLIC_DIR))
    heldout_hash = mf.tree_hash(mf.heldout_files(*map(Path, heldout_dirs))) if heldout else None
    bound_model = {k: model[k] for k in MODEL_KEYS} if model is not None else None
    plan = {
        "artifact": PLAN_ARTIFACT,
        "protocol_version": mf.PROTOCOL_VERSION,
        "suite": suite,
        "heldout": heldout,
        "case_refs": [s.case_ref for s in specs],
        "policies": chosen,
        "seeds": seed_list,
        "order_seed": order,
        "episodes": [e.as_dict() for e in episodes],
        "episode_caps": frozen.caps | {"phase": "frozen" if heldout else "development"},
        "episode_timeout_s": frozen.timeout_s,
        "dry_run": policy_factory is not None,
        "policy_factory": policy_factory,
        "model_response_cache": False,
        "start_method": "spawn",
        "order_over": list(POLICY_KEYS),
        "policy_subset": set(chosen) != set(POLICY_KEYS),
        "measured_files_sha256": measured,
        "heldout_files_sha256": heldout_hash,
        "freeze_sha256": frozen.freeze.get("sha256") if heldout else None,
        "heldout_sha256": frozen.heldout.get("sha256") if heldout else None,
        "model": bound_model,
    }
    out.mkdir(parents=True, exist_ok=True)
    with _results_lock(out):
        return _run_plan(
            plan=plan,
            out=out,
            specs=specs,
            episodes=episodes,
            heldout=heldout,
            frozen=frozen,
            model=model,
            policy_factory=policy_factory,
            jobs=jobs,
            log=log,
            expect={
                "measured_files_sha256": measured,
                "heldout_files_sha256": heldout_hash,
                "heldout_dirs": list(heldout_dirs),
                "model": bound_model,
            },
        )


@contextmanager
def _results_lock(out: Path) -> Iterator[None]:
    """One invocation at a time on a results directory (an exclusive ``fcntl`` lock)."""
    try:
        import fcntl
    except ImportError:  # not POSIX: no lock
        yield
        return
    fd = os.open(out / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RunRefused(f"another invocation is running on {out.name}") from None
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _run_plan(
    *,
    plan: dict[str, Any],
    out: Path,
    specs: Sequence[CaseSpec],
    episodes: Sequence[Episode],
    heldout: bool,
    frozen: FrozenSettings,
    model: dict[str, Any] | None,
    policy_factory: str | None,
    jobs: int,
    log: Callable[[str], None],
    expect: dict[str, Any],
) -> RunSummary:
    plan_file = out / "plan.json"
    if plan_file.exists():
        previous = _read_json(plan_file)
        keys = [k for k in plan if k not in ("created_at",)]
        if any(previous.get(k) != plan[k] for k in keys):
            raise RunRefused(f"{out.name} holds a different run plan; use a new --out directory")
    else:
        _write(plan_file, plan | {"created_at": _now()})
    _write(out / "runner_private" / "cases.json", {"cases": [s.evaluator() for s in specs]})
    invocation = {
        "started_at": _now(),
        "git_head": mf.git_head(),
        "app_tree_clean": _app_tree_clean(),
        "freeze": frozen.freeze,
        "heldout_lock": frozen.heldout or None,
        "seed_parameter_supported": seed_supported(),
        "model": model,
        "jobs": jobs,
    }
    with (out / "invocations.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(invocation, sort_keys=True) + "\n")

    todo = [e for e in episodes if not finished(out, e.key)]
    skipped = len(episodes) - len(todo)
    if skipped:
        log(f"resuming: {skipped} of {len(episodes)} episodes already finished")
    work = out / "work"
    registry = CaseRegistry.build(out / "runner_private", specs) if heldout else None
    by_ref = {s.case_ref: s for s in specs}
    statuses: Counter[str] = Counter()
    drifted: list[str] = []
    try:
        for e in todo:
            _clear_partial(out, work, e.key)
        tasks = [
            _task(e, by_ref[e.case_ref], out, work, registry, frozen, policy_factory, heldout)
            | {"expect": expect}
            for e in todo
        ]
        for task, status in _schedule(tasks, jobs, frozen.timeout_s):
            statuses[status] += 1
            if status == "drift":
                drifted.append(_drift_reason(out, task["episode"]["key"]))
                continue
            log(_line(out, task["episode"]["key"]))
    finally:
        if registry is not None:
            shutil.rmtree(registry.private_dir, ignore_errors=True)
        if work.is_dir() and not any(work.iterdir()):
            work.rmdir()
    if drifted:
        raise RunRefused(
            f"stopped: {sorted(set(drifted))[0]} since the run started; {len(drifted)} episode(s)"
            " recorded nothing and no further episode was started. The results directory is"
            " bound to the state it started under: restore it and rerun to resume."
        )
    return RunSummary(
        out=out,
        planned=len(episodes),
        skipped=skipped,
        ran=len(todo),
        statuses=dict(statuses),
        heldout=heldout,
    )


def _clear_partial(out: Path, work: Path, key: str) -> None:
    shutil.rmtree(out / "episodes" / key, ignore_errors=True)
    private_path(out, key).unlink(missing_ok=True)
    _cleanup_work(work, key)


def _task(
    episode: Episode,
    spec: CaseSpec,
    out: Path,
    work: Path,
    registry: CaseRegistry | None,
    frozen: FrozenSettings,
    hook: str | None,
    heldout: bool,
) -> dict[str, Any]:
    return {
        "episode": episode.as_dict(),
        "suite": spec.suite,
        "case_id": spec.case_id,
        "profile_id": spec.profile_id,
        "expected_class": spec.outcome_class,
        "out": str(out),
        "work": str(work),
        "registry": None
        if registry is None
        else {"private_dir": str(registry.private_dir), "public": registry.public},
        "caps": frozen.caps,
        "phase": "frozen" if heldout else "development",
        "hook": hook,
        "cwd": os.getcwd(),
        "sys_path": list(sys.path),
    }


def _schedule(
    tasks: list[dict[str, Any]], jobs: int, timeout_s: float
) -> Iterator[tuple[dict[str, Any], str]]:
    """Run each task in its own spawned process, ``jobs`` at a time, in plan order. A process
    over ``timeout_s`` is terminated; one that exits without its records crashed. Both are
    recorded as outcomes. A process that found the frozen state changed (``DRIFT_EXIT``)
    records nothing, and no further task is started (status ``drift``)."""
    ctx = multiprocessing.get_context("spawn")
    pending = list(tasks)
    running: dict[Any, tuple[Any, dict[str, Any], float]] = {}
    while pending or running:
        while pending and len(running) < jobs:
            task = pending.pop(0) | {"watch_parent": True}
            proc = ctx.Process(target=episode_process, args=(task,), daemon=True)
            proc.start()
            running[proc.sentinel] = (proc, task, time.monotonic())
        wait(list(running), timeout=0.5)
        for sentinel in list(running):
            proc, task, started = running[sentinel]
            key = task["episode"]["key"]
            out = Path(task["out"])
            elapsed = time.monotonic() - started
            if proc.is_alive():
                if elapsed <= timeout_s:
                    continue
                proc.terminate()
                proc.join(10)
                if proc.is_alive():
                    proc.kill()
                    proc.join(10)
                _record_failure(task, "timeout", f"no result after {timeout_s:.0f} s", elapsed)
            else:
                proc.join()
                if proc.exitcode == DRIFT_EXIT and not has_records(out, key):
                    pending.clear()
                    del running[sentinel]
                    yield task, "drift"
                    continue
                if not has_records(out, key):
                    _record_failure(
                        task,
                        "crashed",
                        f"the episode process exited with code {proc.exitcode}",
                        elapsed,
                    )
            del running[sentinel]
            yield task, _status_of(out, key)


def _drift_reason(out: Path, key: str) -> str:
    path = out / "runner_private" / f"{key}.drift.txt"
    try:
        return path.read_text(encoding="utf-8").strip() or "the frozen state changed"
    except OSError:
        return "the frozen state changed"
    finally:
        path.unlink(missing_ok=True)


def _status_of(out: Path, key: str) -> str:
    try:
        return str(json.loads(record_path(out, key).read_text(encoding="utf-8"))["status"])
    except (OSError, json.JSONDecodeError, KeyError):
        return "crashed"


def _line(out: Path, key: str) -> str:
    """The console line of a finished episode: public facts only."""
    try:
        record = json.loads(record_path(out, key).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"{key}: no record"
    outcome = record.get("outcome") or {}
    model = record.get("model") or {}
    return (
        f"{key}: {record['status']} goal_complete={outcome.get('goal_complete')}"
        f" infeasibility_reported={outcome.get('infeasibility_reported')}"
        f" violations={len(outcome.get('violations') or [])}"
        f" model_calls={model.get('calls', 0)}"
        f" tool_calls={(record.get('tool_calls') or {}).get('total')}"
        f" cost_usd={model.get('cost_usd', 0.0)}"
    )


def _base_record(task: dict[str, Any], status: str, wall: float) -> dict[str, Any]:
    episode = task["episode"]
    return {
        "record": RECORD_VERSION,
        "key": episode["key"],
        "suite": task["suite"],
        "case_ref": episode["case_ref"],
        "policy": episode["policy"],
        "choice": episode["choice"],
        "seed": episode["seed"],
        "trial": episode["trial"],
        "order_position": episode["position"],
        "status": status,
        "dry_run": task["hook"] is not None,
        "model_source": "none"
        if episode["policy"] == "P0"
        else (f"scripted:{task['hook']}" if task["hook"] else "provider"),
        "wall_seconds": round(wall, 1),
        "finished_at": _now(),
    }


def _record_failure(
    task: dict[str, Any],
    status: str,
    message: str,
    wall: float,
    *,
    detail: dict[str, Any] | None = None,
) -> None:
    """The record of an episode that produced none: kept in every denominator. ``message`` is
    the harness's own public wording; an exception's text (which privileged code may have
    composed from private data) goes only to the evaluator record. The episode's database is
    kept beside it (``runner_private/failed/``: it holds private tables) as its evidence."""
    out = Path(task["out"])
    key = task["episode"]["key"]
    kept = _keep_database(out, Path(task["work"]), key)
    # A trace written before the failure is kept with the database, not as the episode's record.
    stray = trace_path(out, key)
    if stray.is_file():
        (out / "runner_private" / "failed").mkdir(parents=True, exist_ok=True)
        shutil.move(str(stray), out / "runner_private" / "failed" / f"{key}.trace.json.gz")
        kept.append(f"runner_private/failed/{key}.trace.json.gz")
    _write(
        private_path(out, key),
        {
            "record": PRIVATE_RECORD_VERSION,
            "key": key,
            "case_ref": task["episode"]["case_ref"],
            "case_id": task["case_id"],
            "status": status,
            "matches_expectation": False,
            "expected_class": task["expected_class"],
            "report": None,
            "error_detail": detail,
            "database": kept,
        },
    )
    record = _base_record(task, status, wall) | {
        "outcome": None,
        "errors": [{"kind": status, "message": message}],
        "trace": None,
    }
    _write(record_path(out, key), record)
    _cleanup_work(Path(task["work"]), key)


def _keep_database(out: Path, work: Path, key: str) -> list[str]:
    """Move a failed episode's database files into ``runner_private/failed/``."""
    target = out / "runner_private" / "failed"
    kept = []
    for path in sorted(work.glob(f"{key}.sqlite3*")) if work.is_dir() else []:
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), target / path.name)
        kept.append(f"runner_private/failed/{path.name}")
    return kept


# ---------------------------------------------------------------------------------- one episode


def _resolve_hook(spec: str, cwd: str) -> PolicyFactoryHook:
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ValueError("--policy-factory takes MODULE:CALLABLE")
    hook = getattr(importlib.import_module(module_name), attr)
    if not callable(hook):
        raise ValueError(f"{spec} is not callable")
    return hook


def public_text(text: str, *dirs: str) -> str:
    """An exception's text without local paths."""
    for local, placeholder in (
        *((d, "<work>") for d in dirs if d),
        (str(mf.APP_DIR.parents[1]), "<repo>"),
        (str(Path.home()), "~"),
    ):
        text = text.replace(local, placeholder)
    return text[:MESSAGE_CHARS]


def _model_summary(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [
        c
        for d in decisions
        for c in ((d["details"].get("model") or {}).get("calls") or [])
        if isinstance(c, dict)
    ]

    def total(name: str) -> int:
        return sum(int(c.get(name) or 0) for c in calls)

    seeds = sorted(
        {json.dumps({k: v for k, v in c.items() if "seed" in k}, sort_keys=True) for c in calls}
    )
    return {
        "calls": len(calls),
        "by_purpose": dict(Counter(str(c.get("purpose")) for c in calls)),
        "outcomes": dict(Counter(str(c.get("outcome")) for c in calls)),
        "retries": sum(1 for c in calls if int(c.get("attempt") or 1) > 1),
        "failed": sum(1 for c in calls if c.get("outcome") != "ok"),
        "returned": sorted({str(c["model_id"]) for c in calls if c.get("model_id")}),
        "prompt_tokens": total("prompt_tokens"),
        "completion_tokens": total("completion_tokens"),
        "reasoning_tokens": total("reasoning_tokens"),
        "latency_ms": total("latency_ms"),
        "cost_usd": round(sum(float(c.get("cost_usd") or 0.0) for c in calls), 8),
        "cost_basis": sorted({str(c["cost_basis"]) for c in calls if c.get("cost_basis")}),
        "max_tokens": sorted({int(c["max_tokens"]) for c in calls if c.get("max_tokens")}),
        "seed_fields": [json.loads(s) for s in seeds if s != "{}"],
    }


def episode_process(task: dict[str, Any]) -> None:
    """Entry point of one episode process (also callable in process, for tests)."""
    for entry in task.get("sys_path", []):
        if entry not in sys.path:
            sys.path.append(entry)
    if task.get("watch_parent"):
        _exit_with_parent()
    out = Path(task["out"])
    work = Path(task["work"])
    work.mkdir(parents=True, exist_ok=True)
    reason = _drift(task)
    if reason is not None:
        key = task["episode"]["key"]
        path = out / "runner_private" / f"{key}.drift.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(reason + "\n", encoding="utf-8")
        sys.exit(DRIFT_EXIT)
    registry = None
    if task["registry"] is not None:
        registry = CaseRegistry(
            private_dir=Path(task["registry"]["private_dir"]),
            public=dict(task["registry"]["public"]),
        )
        registry.install()
    try:
        _run_episode(task, out, work)
    finally:
        if registry is not None:
            registry.uninstall()


def _exit_with_parent() -> None:
    """End this episode process when the runner that started it is gone (killed), so no
    orphan keeps writing into the results directory."""
    import threading

    parent = os.getppid()

    def watch() -> None:
        while True:
            time.sleep(1.0)
            if os.getppid() != parent:
                os._exit(1)

    threading.Thread(target=watch, name="parent-watch", daemon=True).start()


def _drift(task: dict[str, Any]) -> str | None:
    """Why this episode must not run: the measured code, the held-out cases or the model
    configuration differ from the state the run is bound to (``plan.json``), else None."""
    expect = task.get("expect") or {}
    want = expect.get("measured_files_sha256")
    if want is not None and mf.tree_hash(mf.measured_files()) != want:
        return "the measured code changed"
    want = expect.get("heldout_files_sha256")
    dirs = [Path(d) for d in expect.get("heldout_dirs") or ()]
    if want is not None and mf.tree_hash(mf.heldout_files(*dirs)) != want:
        return "the held-out cases changed"
    bound = expect.get("model")
    if bound is not None and task["episode"]["choice"] != "rules" and not task["hook"]:
        from plan_b.agent.config import ModelConfigError, load_model_config

        try:
            public = load_model_config().public()
        except ModelConfigError:
            return "the model endpoint is no longer configured"
        if any(public.get(k) != bound.get(k) for k in MODEL_KEYS):
            return "the model configuration changed"
    return None


def _run_episode(task: dict[str, Any], out: Path, work: Path) -> None:
    from plan_b.evaluation.export_trace import build_trace, verify_trace_bytes, write_trace
    from plan_b.evaluation.scoring import public_summary
    from plan_b.scenarios.policy_host import EpisodeCaps
    from plan_b.scenarios.runner import run_case
    from plan_b.store.database import Database

    episode = task["episode"]
    key, choice, seed = episode["key"], episode["choice"], episode["seed"]
    caps = EpisodeCaps(
        max_tool_calls=task["caps"]["max_tool_calls"],
        max_model_calls=task["caps"]["max_model_calls"],
        phase=task["phase"],
    )
    t0 = time.monotonic()
    started = _now()
    db_path = work / f"{key}.sqlite3"
    kwargs: dict[str, Any] = {"policy": choice, "caps": caps}
    seed_passed = False
    if seed is not None and seed_supported():
        kwargs["seed"] = seed
        seed_passed = True
    error: dict[str, Any] | None = None
    result = None
    trace: dict[str, Any] | None = None
    db = Database(db_path)
    try:
        if choice != "rules":
            if task["hook"]:
                hook = _resolve_hook(task["hook"], task["cwd"])
                kwargs["policy_factory"] = hook(choice, task["profile_id"], seed, caps, work / key)
            else:
                from plan_b.agent.config import load_model_config

                kwargs["live_config"] = load_model_config()  # server-side; no key read here
        result = run_case(db, episode["case_ref"], **kwargs)
        trace = build_trace(db, result.episode_id, policy_id=result.report.policy_id)
    except Exception as exc:  # noqa: BLE001 - recorded as the episode's outcome, never hidden
        error = {
            "kind": "exception",
            "type": type(exc).__name__,
            "message": public_text(str(exc), str(work), str(out)),
            "where": public_text(traceback.format_exc().strip().splitlines()[-1], str(work)),
        }
    wall = time.monotonic() - t0
    if result is None or trace is None:
        # The public record names only the exception's type: its text may come from privileged
        # code (the trace exporter's leak refusal quotes what it refused).
        _record_failure(
            task,
            "crashed",
            f"{error['type']} in the episode process" if error else "no result",
            wall,
            detail=error,
        )
        return
    report = result.report
    tmp_trace = work / f"{key}.trace.json"
    write_trace(trace, tmp_trace)
    data = tmp_trace.read_bytes()
    tmp_trace.unlink()
    problems = verify_trace_bytes(data)
    _write_bytes(trace_path(out, key), gzip.compress(data, mtime=0))
    caps_report = report.episode_caps.model_dump(mode="json") if report.episode_caps else None
    status = _episode_status(caps_report, trace["decisions"])
    _write(
        private_path(out, key),
        {
            "record": PRIVATE_RECORD_VERSION,
            "key": key,
            "case_ref": episode["case_ref"],
            "case_id": task["case_id"],
            "status": status,
            "expected_class": task["expected_class"],
            "expected_outcome": report.expected_outcome,
            "matches_expectation": report.matches_expectation,
            "predicates": [p.model_dump(mode="json") for p in report.predicates],
            "report": report.model_dump(mode="json"),
            "actor_log": result.actor_log,
        },
    )
    agent = next(
        (t["actor_id"] for t in trace["tool_calls"] if t["actor_role"] == "coordinator_agent"),
        None,
    )
    calls = [t for t in trace["tool_calls"] if t["actor_id"] == agent]
    decisions = trace["decisions"]
    record = _base_record(task, status, wall) | {
        "started_at": started,
        "measured_files_sha256": (task.get("expect") or {}).get("measured_files_sha256"),
        "policy_id": report.policy_id,
        "mode_label": report.mode_label,
        "seed_passed": seed_passed,
        "outcome": public_summary(report),
        "episode_caps": caps_report,
        "model": _model_summary(decisions),
        "tool_calls": {
            "total": len(calls),
            "by_tool": dict(Counter(t["tool"] for t in calls)),
            "by_status": dict(Counter(t["envelope_status"] for t in calls)),
            "rejected": [
                {"call_id": t["call_id"], "tool": t["tool"], "error_code": t["error_code"]}
                for t in calls
                if t["envelope_status"] == "rejected"
            ],
        },
        "errors": [
            {
                "kind": "decision_failure",
                "decision_id": d["decision_id"],
                "decision_kind": d["kind"],
                "failure": d["details"]["failure"],
                "recorded_by": d["details"].get("recorded_by", "policy"),
            }
            for d in decisions
            if d["details"].get("failure")
        ],
        "trace": {
            "file": trace_path(out, key).name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "verify": problems or "intact",
        },
    }
    _write(record_path(out, key), record)
    _cleanup_work(work, key)


def _episode_status(caps: dict[str, Any] | None, decisions: list[dict[str, Any]]) -> str:
    """``aborted`` when the harness, not the policy, stopped its model calls (the cumulative
    spend cap, an unreadable ledger, or the endpoint configuration): not scored, and rerun by a
    resume. ``capped`` when an episode cap was reached, the per-run spend cap included (frozen
    with the caps, the episode's own budget). Else ``completed``."""
    for d in decisions:
        failure = d["details"].get("failure")
        if failure == "provider_config" or (
            failure == "spend_cap" and "per-run cap" not in d["summary"]
        ):
            return "aborted"
    stopped = any(
        d["details"].get("failure") == "spend_cap" and "per-run cap" in d["summary"]
        for d in decisions
    )
    return "capped" if (caps and caps.get("reached")) or stopped else "completed"


def _cleanup_work(work: Path, key: str) -> None:
    """Remove an episode's database and its scratch directory (a dry run's fake key and
    ledger)."""
    if not work.is_dir():
        return
    for path in work.glob(f"{key}.*"):
        path.unlink(missing_ok=True)
    shutil.rmtree(work / key, ignore_errors=True)


# ---------------------------------------------------------------------------------- reading results


def _trace_problems(record: dict[str, Any], data: bytes) -> list[str]:
    """The trace as read now against its record: the hash recorded when it was written and
    the exporter's own verification. A trace that fails is not scored silently."""
    from plan_b.evaluation.export_trace import verify_trace_bytes

    problems = []
    if hashlib.sha256(data).hexdigest() != (record.get("trace") or {}).get("sha256"):
        problems.append("trace sha256 differs from its record")
    problems += [str(p) for p in verify_trace_bytes(data)]
    return problems


def load_results(out: Path) -> dict[str, Any]:
    """The plan, every episode's records and trace, and the evaluator case data of a results
    directory (for metrics and the report; evaluator-side)."""
    plan = _read_json(out / "plan.json")
    cases_file = out / "runner_private" / "cases.json"
    cases = (
        {c["case_ref"]: c for c in _read_json(cases_file)["cases"]} if cases_file.exists() else {}
    )
    episodes: list[dict[str, Any]] = []
    for e in plan["episodes"]:
        key = e["key"]
        entry: dict[str, Any] = {
            "plan": e,
            "record": None,
            "private": None,
            "trace": None,
            "integrity": [],
        }
        if has_records(out, key):
            entry["record"] = _read_json(record_path(out, key))
            entry["private"] = _read_json(private_path(out, key))
            tp = trace_path(out, key)
            if tp.is_file():
                data = gzip.decompress(tp.read_bytes())
                entry["integrity"] = _trace_problems(entry["record"], data)
                entry["trace"] = json.loads(data)
            elif (entry["record"].get("trace") or {}).get("file"):
                entry["integrity"] = ["the recorded trace file is missing"]
        episodes.append(entry)
    invocations = []
    inv = out / "invocations.jsonl"
    if inv.is_file():
        invocations = [json.loads(line) for line in inv.read_text().splitlines() if line.strip()]
    return {"plan": plan, "cases": cases, "episodes": episodes, "invocations": invocations}
