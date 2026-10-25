"""Freeze manifests of the Wave 3 comparison (``08_evaluation.md``, "Reporting and presentation
gates": freeze the protocol before the first held-out model call).

Two manifests live in ``evaluation/manifests/``:

* ``freeze.json`` (``plan-b eval freeze``) holds the SHA-256 of every *measured* file: every
  file under ``plan_b/`` (policies, prompts, agent modules, tool registry and executor, store
  and clock engine, planner, candidates, constraints, objective, adapters, scoring, metrics,
  runner, policy host, world loader, this harness) plus ``pyproject.toml`` and ``uv.lock``, minus
  the paths in ``EXCLUDED`` (fixture data, these manifests, development records, and the browser
  server, CLI, demo script and report formatter, which do not take part in a measured
  episode). Alongside the hashes it records the model and provider, the generation settings
  the code declares, the per-episode caps, the retry rules, the episode timeout, P3's relevance
  rule, the preregistered seeds and policy-order seed, the policy ids and the protocol version.
* ``heldout.json`` (``plan-b eval lock-heldout``) holds the held-out suites: each case's opaque
  reference and evaluator case id, the hashes of its private case, its evaluator data and its
  public fixture, every file under ``scenarios/private/eval/`` and ``scenarios/public/eval/``,
  and the case-freeze time. Fixture data is therefore covered by ``heldout.json`` and never by
  ``freeze.json``: authoring held-out cases cannot trip the code freeze, while the code that
  loads them stays frozen.

A second held-out set gets its own case-scoped manifest (``plan-b eval lock-heldout --manifest
heldout2.json --cases C09 ...``): it records ``case_scope`` (the evaluator case ids it locks)
and covers only those cases' files (private case, evaluator data, public fixture), so editing
another case's file is not drift for it. A manifest without ``case_scope`` (v1.1's
``heldout.json``) keeps covering every file under both held-out directories.

``verify_freeze`` recomputes both and lists every drift (a changed, added or removed file, a
changed setting). ``plan-b eval verify-freeze`` fails loudly on any drift, and the evaluation
runner refuses to start a held-out run unless both manifests verify.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import pkgutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[2]
PACKAGE_DIR = APP_DIR / "plan_b"
MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"
FREEZE_PATH = MANIFEST_DIR / "freeze.json"
HELDOUT_PATH = MANIFEST_DIR / "heldout.json"
HELDOUT_PRIVATE_DIR = PACKAGE_DIR / "scenarios" / "private" / "eval"
HELDOUT_PUBLIC_DIR = PACKAGE_DIR / "scenarios" / "public" / "eval"

PROTOCOL_VERSION = "plan_b.eval_protocol/1.0.0"
FREEZE_ARTIFACT = "plan_b.eval_freeze"
HELDOUT_ARTIFACT = "plan_b.eval_heldout"
# Preregistered before any held-out run: three seeds for P1-P3, and the seed of the policy order
# within each case. ``plan-b eval freeze --seeds/--order-seed`` may set others; a held-out run
# must use the frozen values.
DEFAULT_SEEDS = (101, 202, 303)
DEFAULT_ORDER_SEED = 20261025
# Wall-clock limit of one episode process. Eight model calls at the provider's 90-second total
# timeout are 720 seconds; the recorded development episodes took 7-75 seconds.
EPISODE_TIMEOUT_S = 900

# Measured files: every file under these roots, minus EXCLUDED (relative to apps/plan_b).
MEASURED_ROOTS = ("plan_b",)
MEASURED_FILES = ("pyproject.toml", "uv.lock")
EXCLUDED = (
    "plan_b/scenarios/public/",  # fixture data: heldout.json and the case hashes cover it
    "plan_b/scenarios/private/",
    "plan_b/evaluation/manifests/",  # the manifests themselves
    "plan_b/evaluation/development/",  # development run records
    "plan_b/api/",  # the browser server; measured episodes run in process through the runner
    "plan_b/cli.py",
    "plan_b/scenarios/demos.py",  # the rejected-actions demonstration
    "plan_b/evaluation/report.py",  # formats metrics.py's output; computes no metric
)
SKIPPED_PARTS = ("__pycache__",)
SKIPPED_SUFFIXES = (".pyc", ".pyo")

# The comparison's policies, by the evaluation plan's names (P0 is the profile's baseline).
POLICY_CHOICES = {"P0": "rules", "P1": "tool-use", "P2": "live", "P3": "verify-all"}
POLICY_MODULES: dict[str, str | dict[str, str]] = {
    "P0": {
        "event": "plan_b.evaluation.policies.rules",
        "pantry": "plan_b.evaluation.policies.pantry_rules",
    },
    "P1": "plan_b.agent.policies.tool_use",
    "P2": "plan_b.agent.orchestrator",
    "P3": "plan_b.agent.policies.verify_all",
}
RETRY_RULES = (
    "Every model call counts against the episode's model-call cap, a repair attempt and a failed"
    " call included; every tool call, failed calls, retries and receipt lookups included, counts"
    " against the tool-call cap.",
    "Malformed or schema-violating model output gets one repair attempt; after it the step is a"
    " visible wait or an unresolved reading, never an invented result.",
    "A provider timeout, HTTP or transport failure is a visible wait, retried at a later wake."
    " Policy 1.2: an HTTP 429 is first waited out inside the call (3 s doubling to 20 s, at"
    " most 60 s of waiting per call) and uses no model call; only one that outlasts the bound is"
    " such a failure.",
    "A rejected mutation (for example a stale revision) is re-read and re-evaluated a bounded"
    " number of times; a lost mutation response is reconciled with its original idempotency key."
    " Policy 1.2: P2 and P3 re-issue a choice rejected only as stale when the re-read menu still"
    " offers the same intent and candidate, without a model call.",
    "P3 checks each relevant source once per unresolved update and retries a failed source once;"
    " it never waits for a failed source.",
    "A reached cap is one host-recorded stop decision; the policy is not woken again and the"
    " episode runs to its hard end, scored as it stands.",
)
# Upper-case module constants of the agent whose names match one of these are recorded as
# generation or retry settings (the hashes cover the code either way).
SETTING_WORDS = (
    "MAX_TOKENS",
    "OUTPUT_TOKENS",
    "TEMPERATURE",
    "TOP_P",
    "SEED",
    "GENERATION",
    "REASONING",
    "TIMEOUT",
    "RETRY",
    "RETRIES",
    "REPAIR",
    "ATTEMPT",
    "MAX_TURNS",
    "MAX_CALLS",
    "MAX_MODEL_CALLS",
    "MAX_TOOL_CALLS",
)


class FreezeError(RuntimeError):
    """A manifest is missing, unreadable, or does not match the tree."""


def manifest_path(value: str | Path) -> Path:
    """A manifest given on the command line: a bare file name (no directory part) is a file in
    ``MANIFEST_DIR``; anything else is a path as given."""
    raw = str(value)
    if os.sep in raw or "/" in raw or (os.altsep and os.altsep in raw):
        return Path(raw)
    return MANIFEST_DIR / raw


@dataclass
class Verification:
    """The outcome of recomputing a manifest. ``ok`` is false on any drift."""

    manifest: str
    present: bool
    drift: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.present and not self.drift

    def as_dict(self) -> dict[str, Any]:
        return {"manifest": self.manifest, "present": self.present, "ok": self.ok} | {
            "drift": list(self.drift)
        }


# ---------------------------------------------------------------------------------- hashing


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(path: Path) -> str | None:
    """The SHA-256 of a manifest file's bytes (None when it is missing): what a held-out lock
    and a run plan bind to, so no field of the manifest can change unnoticed."""
    try:
        return file_hash(path)
    except OSError:
        return None


def _entry_hash(path: Path) -> str:
    """A tree entry's hash: a symbolic link is recorded as its target and the content it
    reaches (a file's hash, or a directory's files without following further links), so adding
    one, pointing it elsewhere or changing what it reaches is drift; an unreadable file is an
    entry as such."""
    if path.is_symlink():
        target = os.readlink(path)
        if path.is_dir():
            root = path.resolve()
            reached = {p.relative_to(root).as_posix(): _entry_hash(p) for p in _walk(root)}
            return f"symlink:{target}:{tree_hash(reached)}"
        return f"symlink:{target}:{_entry_hash(path.resolve()) if path.exists() else 'dangling'}"
    try:
        return file_hash(path)
    except OSError as exc:
        return f"unreadable:{type(exc).__name__}"


def _walk(root: Path) -> list[Path]:
    """Every file and symbolic link under ``root``, without following links."""
    found: list[Path] = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        here = Path(directory)
        found += [here / name for name in files]
        found += [here / name for name in dirs if (here / name).is_symlink()]
    return sorted(found)


def _excluded(rel: str) -> bool:
    return any(rel == e.rstrip("/") or rel.startswith(e) for e in EXCLUDED)


def measured_files(app_dir: Path = APP_DIR) -> dict[str, str]:
    """``{path relative to apps/plan_b: sha256}`` of every measured file, sorted."""
    found: dict[str, str] = {}
    for root in MEASURED_ROOTS:
        for path in _walk(app_dir / root):
            if path.suffix in SKIPPED_SUFFIXES and not path.is_symlink():
                continue
            rel = path.relative_to(app_dir).as_posix()
            if any(part in SKIPPED_PARTS for part in path.parts) or _excluded(rel):
                continue
            found[rel] = _entry_hash(path)
    for name in MEASURED_FILES:
        path = app_dir / name
        if path.is_file() or path.is_symlink():
            found[name] = _entry_hash(path)
    return dict(sorted(found.items()))


def tree_hash(files: dict[str, str]) -> str:
    """One hash over ``path NUL sha256 LF`` lines in path order."""
    text = "".join(f"{p}\0{h}\n" for p, h in sorted(files.items()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compare(recorded: dict[str, str], current: dict[str, str], what: str) -> list[str]:
    drift = [
        f"{what} changed: {p}"
        for p in sorted(recorded)
        if p in current and current[p] != recorded[p]
    ]
    drift += [f"{what} removed: {p}" for p in sorted(recorded) if p not in current]
    drift += [f"{what} added: {p}" for p in sorted(current) if p not in recorded]
    return drift


# ---------------------------------------------------------------------------------- settings


def _jsonable(value: Any) -> Any:
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, timedelta):
        return {"seconds": value.total_seconds()}
    if isinstance(value, frozenset | set):
        return sorted(_jsonable(v) for v in value)
    if isinstance(value, tuple | list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    raise TypeError


def agent_settings() -> dict[str, dict[str, Any]]:
    """Generation, cap and retry constants the agent modules declare, by module."""
    import plan_b.agent as agent

    names = sorted(m.name for m in pkgutil.walk_packages(agent.__path__, prefix="plan_b.agent."))
    out: dict[str, dict[str, Any]] = {}
    for name in names:
        module = importlib.import_module(name)
        found: dict[str, Any] = {}
        for attr, value in sorted(vars(module).items()):
            if not attr.isupper() or not any(w in attr for w in SETTING_WORDS):
                continue
            try:
                found[attr] = _jsonable(value)
            except TypeError:
                continue
        if found:
            out[name] = found
    return out


def request_template(provider: str, model_id: str) -> dict[str, Any]:
    """The provider's request body around the messages and the schema: what every model call
    sends besides its prompt, schema and per-call token limit."""
    from plan_b.agent.config import ModelConfig
    from plan_b.agent.provider import ModelRequest, OpenAICompatibleProvider

    config = ModelConfig(
        provider=provider,
        base_url="https://example.invalid/api/v1",
        key_file=Path("/nonexistent"),
        model_id=model_id,
        max_run_cost_usd=1.0,
        max_total_cost_usd=1.0,
        ledger_path=Path("/nonexistent"),
        repo_root=Path("/nonexistent"),
        sources={},
    )
    from pydantic import BaseModel

    class _Out(BaseModel):
        x: str

    request = ModelRequest(
        purpose="freeze",
        system="s",
        user="u",
        schema_name="freeze",
        schema={"type": "object"},
        output_model=_Out,
    )
    # Building the body reads no key and needs no spend guard.
    body = OpenAICompatibleProvider(config, None).body(request)  # type: ignore[arg-type]
    body.pop("messages", None)
    body.pop("max_tokens", None)  # per call; the policies' limits are in agent_settings
    fmt = body.get("response_format")
    if isinstance(fmt, dict) and isinstance(fmt.get("json_schema"), dict):
        schema = fmt["json_schema"]
        body["response_format"] = {
            "type": fmt.get("type"),
            "json_schema": {"strict": schema.get("strict")},
        }
    return _jsonable(body)


def policy_ids() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, module in POLICY_MODULES.items():
        if isinstance(module, dict):
            out[key] = {
                profile: importlib.import_module(m).POLICY_ID for profile, m in module.items()
            }
        else:
            out[key] = importlib.import_module(module).POLICY_ID
    return out


def episode_caps() -> dict[str, Any]:
    """The caps every policy runs under: the policy host's frozen caps when it declares them,
    else its development values (48 tool calls, 8 model calls)."""
    from plan_b.scenarios import policy_host

    caps = getattr(policy_host, "FROZEN_CAPS", None) or policy_host.DEVELOPMENT_CAPS
    return {"max_tool_calls": caps.max_tool_calls, "max_model_calls": caps.max_model_calls}


def prompts() -> dict[str, str]:
    directory = PACKAGE_DIR / "agent" / "prompts"
    return {p.stem: file_hash(p) for p in sorted(directory.glob("*.txt"))}


def model_settings(model: dict[str, Any] | None = None) -> dict[str, Any]:
    """Model and provider of P1-P3. Read from the server-side endpoint configuration (its
    public form: no key, no local path) unless given."""
    if model is not None:
        return dict(model)
    from plan_b.agent.config import (
        DEFAULT_MAX_RUN_COST_USD,
        DEFAULT_MODEL_ID,
        ModelConfigError,
        load_model_config,
    )

    try:
        cfg = load_model_config()
    except ModelConfigError:
        # A held-out run checks every key, so a freeze written without an endpoint refuses
        # every held-out run of P1-P3 until it is written again with one.
        return {
            "provider": "openrouter",
            "model_id": DEFAULT_MODEL_ID,
            "base_url": None,
            "max_run_cost_usd": DEFAULT_MAX_RUN_COST_USD,
            "source": "defaults (endpoint not configured)",
        }
    return {
        "provider": cfg.provider,
        "model_id": cfg.model_id,
        "base_url": cfg.base_url,
        "max_run_cost_usd": cfg.max_run_cost_usd,  # the per-episode USD cap, frozen with them
        "source": "endpoint configuration",
    }


RUNTIME_DISTRIBUTIONS = ("fastapi", "pydantic", "pydantic-core", "uvicorn")


def runtime() -> dict[str, Any]:
    """The interpreter and the installed runtime dependencies that run a measured episode
    (``uv.lock``'s hash does not prove the environment matches it)."""
    import platform
    import sys
    from importlib import metadata

    versions: dict[str, str | None] = {}
    for name in RUNTIME_DISTRIBUTIONS:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {
        "python": platform.python_version(),
        "implementation": sys.implementation.name,
        "distributions": versions,
    }


def git_head(app_dir: Path = APP_DIR) -> str | None:
    """Read-only: the commit the tree is on, when git is available."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=app_dir, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------- freeze


def settings(
    *,
    seeds: Iterable[int] = DEFAULT_SEEDS,
    order_seed: int = DEFAULT_ORDER_SEED,
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every frozen setting except the file hashes."""
    from plan_b.agent.policies.verify_all import RELEVANCE_RULE
    from plan_b.domain.constraints import PLANNER_VERSION

    seeds = [int(s) for s in seeds]
    if len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError("the protocol preregisters three distinct seeds")
    chosen = model_settings(model)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "model": chosen,
        "generation": {
            "request_template": request_template(chosen["provider"], chosen["model_id"]),
            "agent_constants": agent_settings(),
        },
        "episode_caps": episode_caps(),
        "retry_rules": list(RETRY_RULES),
        "episode_timeout_s": EPISODE_TIMEOUT_S,
        "p3_relevance_rule": RELEVANCE_RULE,
        "seeds": seeds,
        "order_seed": int(order_seed),
        "policies": dict(POLICY_CHOICES),
        "policy_ids": policy_ids(),
        "planner_version": PLANNER_VERSION,
        "prompts": prompts(),
        "model_response_cache": False,
        "runtime": runtime(),
    }


def compute_freeze(
    *,
    seeds: Iterable[int] = DEFAULT_SEEDS,
    order_seed: int = DEFAULT_ORDER_SEED,
    model: dict[str, Any] | None = None,
    app_dir: Path = APP_DIR,
) -> dict[str, Any]:
    files = measured_files(app_dir)
    return {
        "artifact": FREEZE_ARTIFACT,
        "frozen_at": _now(),
        "git_head_at_freeze": git_head(app_dir),
        "excluded": list(EXCLUDED),
        "files_sha256": tree_hash(files),
        "files": files,
        **settings(seeds=seeds, order_seed=order_seed, model=model),
    }


def write_json(data: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def write_freeze(path: Path = FREEZE_PATH, **kwargs: Any) -> dict[str, Any]:
    data = compute_freeze(**kwargs)
    write_json(data, path)
    return data


def load_manifest(path: Path, artifact: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FreezeError(f"no manifest at {path.name}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"{path.name} is unreadable: {exc}") from None
    if not isinstance(data, dict) or data.get("artifact") != artifact:
        raise FreezeError(f"{path.name} is not a {artifact} manifest")
    return data


SETTING_KEYS = (
    "protocol_version",
    "generation",
    "episode_caps",
    "retry_rules",
    "episode_timeout_s",
    "p3_relevance_rule",
    "policies",
    "policy_ids",
    "planner_version",
    "prompts",
    "model_response_cache",
    "runtime",
)


def verify_freeze(path: Path = FREEZE_PATH, app_dir: Path = APP_DIR) -> Verification:
    """Recompute the measured files and the settings the code declares; any difference is
    drift. The model, seeds and order seed are inputs, not code, and are not recomputed."""
    result = Verification(manifest=path.name, present=path.is_file())
    if not result.present:
        result.drift.append(f"no freeze manifest at {path.name}; run `plan-b eval freeze`")
        return result
    try:
        recorded = load_manifest(path, FREEZE_ARTIFACT)
    except FreezeError as exc:
        result.drift.append(str(exc))
        return result
    current = measured_files(app_dir)
    result.drift += _compare(recorded.get("files", {}), current, "measured file")
    if tree_hash(recorded.get("files", {})) != recorded.get("files_sha256"):
        result.drift.append("files_sha256 does not match the recorded file hashes")
    if not result.drift:
        now = settings(
            seeds=recorded["seeds"], order_seed=recorded["order_seed"], model=recorded["model"]
        )
        result.drift += [
            f"setting changed: {key}" for key in SETTING_KEYS if now.get(key) != recorded.get(key)
        ]
    result.detail = {
        "files": len(current),
        "files_sha256": tree_hash(current),
        "recorded_files_sha256": recorded.get("files_sha256"),
    }
    return result


# ---------------------------------------------------------------------------------- held-out


def heldout_files(
    private_dir: Path | None = None, public_dir: Path | None = None
) -> dict[str, str]:
    """Every file under the held-out directories (default: ``HELDOUT_PRIVATE_DIR`` and
    ``HELDOUT_PUBLIC_DIR`` as they are when called), relative to apps/plan_b."""
    found = _files_under(private_dir or HELDOUT_PRIVATE_DIR)
    found |= _files_under(public_dir or HELDOUT_PUBLIC_DIR)
    return dict(sorted(found.items()))


def _files_under(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        _rel(path): _entry_hash(path)
        for path in _walk(root)
        if not any(part in SKIPPED_PARTS for part in path.parts)
    }


def _rel(path: Path) -> str:
    """A path relative to apps/plan_b, symbolic links not resolved (a link and its target are
    two entries)."""
    absolute = Path(os.path.abspath(path))
    try:
        return absolute.relative_to(APP_DIR).as_posix()
    except ValueError:
        return absolute.as_posix()


def select_cases(specs: list[Any], wanted: Iterable[str]) -> list[Any]:
    """The held-out specs named by evaluator case id (``C09``) or case ref, in spec order.
    An unknown, ambiguous or repeated name is refused."""
    names = [w for w in wanted]
    if len(set(names)) != len(names):
        raise FreezeError("a case is named twice in --cases")
    chosen: list[Any] = []
    unknown: list[str] = []
    for name in names:
        hits = [s for s in specs if name in (s.case_id, s.case_ref)]
        if not hits:
            unknown.append(name)
        elif len(hits) > 1:
            raise FreezeError(f"case {name} names more than one held-out case")
        elif hits[0] in chosen:
            raise FreezeError(f"case {name} names {hits[0].case_id} a second time")
        else:
            chosen.append(hits[0])
    if unknown:
        known = ", ".join(sorted({s.case_id for s in specs})) or "none"
        raise FreezeError(
            f"unknown held-out case(s): {', '.join(unknown)}; the held-out cases are {known}"
        )
    if not chosen:
        raise FreezeError("--cases names no case")
    return [s for s in specs if s in chosen]


def _scoped_files(recorded: dict[str, Any]) -> dict[str, str]:
    """The current hashes of the files a case-scoped lock recorded (a missing one is absent)."""
    found: dict[str, str] = {}
    for rel in recorded.get("files", {}):
        path = APP_DIR / rel
        if path.is_symlink() or path.exists():
            found[rel] = _entry_hash(path)
    return dict(sorted(found.items()))


def compute_heldout(
    freeze_path: Path = FREEZE_PATH, cases: Iterable[str] | None = None
) -> dict[str, Any]:
    """The held-out lock. Every case must load and validate through the runner's loader, and
    every designated negative control must pass the evaluator's replay: with a coordinator
    that changes nothing, its original plan completes the goal (``08_evaluation.md``: an
    unnecessary change is counted where replay confirms the original plan stays feasible).

    Given ``cases`` (evaluator case ids or case refs) the lock is case-scoped: it holds only
    those cases, records them as ``case_scope``, and covers only their private case, evaluator
    and public fixture files; its aggregate hashes are over exactly those files."""
    from plan_b.evaluation.run import heldout_specs, replay_original_plan

    freeze = load_manifest(freeze_path, FREEZE_ARTIFACT) if freeze_path.is_file() else None
    specs = heldout_specs()
    if not specs:
        raise FreezeError("no held-out case under scenarios/private/eval/")
    scope = None
    if cases is not None:
        specs = select_cases(specs, cases)
        scope = sorted(s.case_id for s in specs)
    suites: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        replay = replay_original_plan(spec) if spec.negative_control else None
        if replay is not None and not replay["original_plan_completes"]:
            raise FreezeError(
                f"{spec.case_id}: the original plan does not complete the goal without a change"
                f" ({replay['violations']} violation(s)); it cannot be a negative control"
            )
        suites.setdefault(spec.suite, []).append(
            {
                "case_id": spec.case_id,
                "case_ref": spec.case_ref,
                "outcome_class": spec.outcome_class,
                "private_file": _rel(spec.case_file),
                "private_sha256": file_hash(spec.case_file),
                "eval_file": _rel(spec.eval_file) if spec.eval_file else None,
                "eval_sha256": file_hash(spec.eval_file) if spec.eval_file else None,
                "scenario_id": spec.scenario_id,
                "public_file": _rel(spec.public_file),
                "public_sha256": file_hash(spec.public_file),
                "negative_control_replay": replay,
            }
        )
    if scope is not None:
        # Exactly the scoped cases' files: another case's file is outside this lock.
        public = {_rel(s.public_file): _entry_hash(s.public_file) for s in specs}
        private = {_rel(s.case_file): _entry_hash(s.case_file) for s in specs}
        private |= {_rel(s.eval_file): _entry_hash(s.eval_file) for s in specs if s.eval_file}
        files = dict(sorted((public | private).items()))
        return {
            "artifact": HELDOUT_ARTIFACT,
            "protocol_version": PROTOCOL_VERSION,
            "locked_at": _now(),
            "case_scope": scope,
            "freeze_files_sha256": freeze["files_sha256"] if freeze else None,
            "freeze_sha256": manifest_digest(freeze_path) if freeze else None,
            "suites": {k: sorted(v, key=lambda c: c["case_id"]) for k, v in sorted(suites.items())},
            "files_sha256": tree_hash(files),
            "public_files_sha256": tree_hash(public),
            "private_files_sha256": tree_hash(private),
            "files": files,
        }
    files = heldout_files()
    # The public fixtures held-out cases use (development ones included) and the evaluator-only
    # files, each under its own aggregate: a reader with the public fixtures can check theirs.
    public = {c["public_file"]: c["public_sha256"] for cs in suites.values() for c in cs}
    public |= _files_under(HELDOUT_PUBLIC_DIR)
    private = _files_under(HELDOUT_PRIVATE_DIR)
    return {
        "artifact": HELDOUT_ARTIFACT,
        "protocol_version": PROTOCOL_VERSION,
        "locked_at": _now(),
        "freeze_files_sha256": freeze["files_sha256"] if freeze else None,
        "freeze_sha256": manifest_digest(freeze_path) if freeze else None,
        "suites": {k: sorted(v, key=lambda c: c["case_id"]) for k, v in sorted(suites.items())},
        "files_sha256": tree_hash(files),
        "public_files_sha256": tree_hash(public),
        "private_files_sha256": tree_hash(private),
        "files": files,
    }


def write_heldout(
    path: Path = HELDOUT_PATH,
    freeze_path: Path = FREEZE_PATH,
    cases: Iterable[str] | None = None,
) -> dict[str, Any]:
    data = compute_heldout(freeze_path, cases)
    write_json(data, path)
    return data


def case_scope(lock: dict[str, Any]) -> list[str] | None:
    """The evaluator case ids a case-scoped lock covers, or None for a whole-directory lock."""
    scope = lock.get("case_scope")
    return [str(c) for c in scope] if isinstance(scope, list) else None


def verify_heldout(path: Path = HELDOUT_PATH, freeze_path: Path | None = None) -> Verification:
    """Recompute the held-out files and check the lock against itself (its aggregate hash and
    protocol version) and, given ``freeze_path``, against the freeze it was locked with. A
    case-scoped lock recomputes exactly the files it recorded; a lock without ``case_scope``
    recomputes every file under both held-out directories."""
    result = Verification(manifest=path.name, present=path.is_file())
    if not result.present:
        result.drift.append(f"no held-out manifest at {path.name}; run `plan-b eval lock-heldout`")
        return result
    try:
        recorded = load_manifest(path, HELDOUT_ARTIFACT)
    except FreezeError as exc:
        result.drift.append(str(exc))
        return result
    scope = case_scope(recorded)
    if scope is None and "case_scope" in recorded:
        result.drift.append("case_scope is not a list of case ids")
    current = heldout_files() if scope is None else _scoped_files(recorded)
    result.drift += _compare(recorded.get("files", {}), current, "held-out file")
    if scope is not None:
        suites = recorded.get("suites", {}).values()
        locked = sorted(c["case_id"] for cases in suites for c in cases)
        if locked != sorted(scope):
            result.drift.append("case_scope does not match the locked cases")
    if tree_hash(recorded.get("files", {})) != recorded.get("files_sha256"):
        result.drift.append("files_sha256 does not match the recorded held-out file hashes")
    if recorded.get("protocol_version") != PROTOCOL_VERSION:
        result.drift.append(f"protocol version {recorded.get('protocol_version')!r} is not current")
    if freeze_path is not None and recorded.get("freeze_sha256") != manifest_digest(freeze_path):
        result.drift.append(f"the lock was not made against {freeze_path.name} as it is now")
    for suite, cases in recorded.get("suites", {}).items():
        for case in cases:
            for key in ("private", "eval", "public"):
                rel = case.get(f"{key}_file")
                if rel and rel not in current:
                    path_now = APP_DIR / rel
                    if not path_now.is_file() or file_hash(path_now) != case[f"{key}_sha256"]:
                        result.drift.append(f"{suite} {case['case_id']}: {key} file {rel} drifted")
    result.detail = {"files": len(current), "suites": sorted(recorded.get("suites", {}))}
    if scope is not None:
        result.detail["case_scope"] = sorted(scope)
    return result
