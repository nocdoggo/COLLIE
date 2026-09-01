"""The **only** module permitted to import from ``third_party/InventoryBench``.

The submodule is pinned and read-only. Every other part of the project reaches upstream through
this one door, and ``tests/test_import_boundary.py`` walks the AST of ``collie/`` to prove it. The
point is not tidiness: it is that when the pin moves, exactly one file has to be re-audited.

Upstream is a collection of scripts, not a package — ``eval/`` has no ``__init__.py`` and
``run_baseline_policy.py`` mutates ``sys.path`` at import time so it can do
``from policy_template import ExamplePolicy``. So the modules are loaded by file location rather
than by import name, and the loaded objects are cached.

What upstream is used for, and nothing more:

- ``official_simulate_instance`` / ``official_simulate_and_score`` — the authoritative accounting,
  used as the oracle in the Task 4 equivalence suite and as the scorer for submissions.
- ``official_detect_promised_lead_time`` — cross-checks our mirrored mapping.
- ``InventoryPolicy`` — the base class a submission must subclass.

Upstream's own policy docstring states the policy "does NOT observe actual lead times — must
infer from arrivals", which is the contract :class:`~collie.contracts.PeriodObservation` encodes.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

__all__ = [
    "InventoryBenchAdapter",
    "benchmark_root",
    "official_detect_promised_lead_time",
    "official_load_instance",
    "official_policy_base",
    "official_simulate_and_score",
    "official_simulate_instance",
    "submodule_root",
]

_ENV_VAR = "COLLIE_BENCH_ROOT"
_DEFAULT_RELATIVE = Path("third_party") / "InventoryBench"


def _repo_root() -> Path:
    # collie/adapter/inventorybench.py -> collie/adapter -> collie -> repo root
    return Path(__file__).resolve().parents[2]


def submodule_root() -> Path:
    """Absolute path to the pinned submodule.

    Overridable with ``COLLIE_BENCH_ROOT`` so CI can point at a cached checkout without the
    project growing a second notion of where the benchmark lives.
    """
    override = os.environ.get(_ENV_VAR)
    root = Path(override).expanduser().resolve() if override else _repo_root() / _DEFAULT_RELATIVE
    if not root.is_dir():
        raise FileNotFoundError(
            f"InventoryBench not found at {root}. Run `make setup` to initialise the submodule "
            f"and fetch its LFS objects, or set {_ENV_VAR}."
        )
    return root


def benchmark_root() -> Path:
    """Absolute path to the ``benchmark/`` tree holding the 1,320 instances."""
    root = submodule_root() / "benchmark"
    if not root.is_dir():
        raise FileNotFoundError(
            f"{root} is missing. The submodule is present but its benchmark tree is not; "
            "`git submodule update --init --recursive` then `git lfs pull` inside it."
        )
    return root


def _load_by_path(relative: str, module_name: str) -> ModuleType:
    path = submodule_root() / relative
    if not path.is_file():
        raise FileNotFoundError(f"expected upstream module at {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec_module because upstream code may look itself up by name.
    sys.modules[module_name] = module
    # `eval/` is not a package and `run_baseline_policy` imports `policy_template` as a
    # top-level name, so its directory has to be importable.
    eval_dir = str(path.parent)
    inserted = eval_dir not in sys.path
    if inserted:
        sys.path.insert(0, eval_dir)
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


@lru_cache(maxsize=1)
def _runner_module() -> ModuleType:
    return _load_by_path("eval/run_baseline_policy.py", "_collie_upstream_run_baseline_policy")


@lru_cache(maxsize=1)
def _evaluator_module() -> ModuleType:
    return _load_by_path("eval/evaluate_results.py", "_collie_upstream_evaluate_results")


@lru_cache(maxsize=1)
def _policy_module() -> ModuleType:
    return _load_by_path("eval/policy_template.py", "_collie_upstream_policy_template")


# ---------------------------------------------------------------------------
# thin pass-throughs — no reinterpretation, no defaults of our own
# ---------------------------------------------------------------------------


def official_simulate_instance(policy: Any, test_df: Any, item_id: str) -> Any:
    """``run_baseline_policy.simulate_instance``: run a policy, return ``(period, order_quantity)``."""
    return _runner_module().simulate_instance(policy, test_df, item_id)


def official_simulate_and_score(results_df: Any, test_df: Any, item_id: str) -> dict[str, Any]:
    """``evaluate_results.simulate_and_score``: the authoritative episode score."""
    return _evaluator_module().simulate_and_score(results_df, test_df, item_id)


def official_detect_promised_lead_time(instance_dir: Path | str) -> int:
    """``run_baseline_policy.detect_promised_lead_time``: path label -> promised lead time."""
    return _runner_module().detect_promised_lead_time(str(instance_dir))


def official_load_instance(instance_dir: Path | str) -> tuple[Any, Any, str]:
    """``run_baseline_policy.load_instance``: ``(train_df, test_df, item_id)`` via pandas."""
    return _runner_module().load_instance(Path(instance_dir))


def official_policy_base() -> type:
    """``policy_template.InventoryPolicy``, the base class a submission must subclass."""
    return _policy_module().InventoryPolicy


@dataclass(frozen=True, slots=True)
class InventoryBenchAdapter:
    """Named handle for the upstream seam.

    Exists so callers can depend on an object rather than a module of free functions, which
    keeps the submission path in Task 5 injectable in tests.
    """

    @property
    def root(self) -> Path:
        return submodule_root()

    @property
    def benchmark(self) -> Path:
        return benchmark_root()

    def load(self, instance_dir: Path | str) -> tuple[Any, Any, str]:
        return official_load_instance(instance_dir)

    def promised_lead_time(self, instance_dir: Path | str) -> int:
        return official_detect_promised_lead_time(instance_dir)

    def simulate(self, policy: Any, test_df: Any, item_id: str) -> Any:
        return official_simulate_instance(policy, test_df, item_id)

    def score(self, results_df: Any, test_df: Any, item_id: str) -> dict[str, Any]:
        return official_simulate_and_score(results_df, test_df, item_id)

    def policy_base(self) -> type:
        return official_policy_base()
