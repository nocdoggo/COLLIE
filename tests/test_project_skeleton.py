"""Task 1 acceptance tests: the project imports, and the benchmark is pinned and populated.

These guard collie-platform requirements R1.2 (pinned submodule), R1.3 (submodule is never
modified and only the adapter imports it), and R1.4 (LFS objects present, not pointer files).
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

import collie

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH = REPO_ROOT / "third_party" / "InventoryBench"


def test_package_imports_and_declares_pinned_commit() -> None:
    assert collie.__version__
    assert len(collie.BENCHMARK_COMMIT) == 40, "pin must be a full 40-char SHA"


def test_every_branch_subpackage_is_importable() -> None:
    """Each branch owner must have a package to land code in from day 1."""
    import importlib

    for name in (
        "adapter",
        "sim",
        "fakes",
        "data",
        "spec",
        "control",
        "verify",
        "trigger",
        "llm",
        "arms",
        "eval",
    ):
        mod = importlib.import_module(f"collie.{name}")
        assert mod.__doc__, f"collie.{name} must document its owning branch"


@pytest.mark.needs_benchmark
def test_submodule_is_checked_out_at_the_pinned_commit() -> None:
    head = subprocess.run(
        ["git", "-C", str(BENCH), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == collie.BENCHMARK_COMMIT, (
        f"benchmark submodule is at {head}, expected {collie.BENCHMARK_COMMIT}. "
        "Run: git submodule update --init --recursive"
    )


@pytest.mark.needs_benchmark
def test_submodule_working_tree_is_unmodified() -> None:
    """R1.3: we never modify the benchmark. A dirty submodule invalidates that claim."""
    dirty = subprocess.run(
        ["git", "-C", str(BENCH), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert dirty == "", f"benchmark submodule has local modifications:\n{dirty}"


@pytest.mark.needs_benchmark
def test_lfs_objects_are_materialised_not_pointers() -> None:
    """R1.4: all 1,320 instance CSVs are LFS-tracked. Pointer files would silently
    break the Task 2 audit, so assert real content in one synthetic and one real instance."""
    samples = [
        BENCH / "benchmark/synthetic_trajectory/lead_time_0/p01_stationary_iid"
        "/v1_normal_100_25/r1_med/test.csv",
        next((BENCH / "benchmark/real_trajectory/lead_time_0").iterdir()) / "test.csv",
    ]
    for path in samples:
        assert path.is_file(), f"missing {path}"
        head = path.read_text(encoding="utf-8", errors="replace")[:120]
        assert "git-lfs.github.com" not in head, (
            f"{path} is an unfetched LFS pointer. Run: cd {BENCH} && git lfs pull"
        )
        assert "demand" in head, f"{path} does not look like an instance CSV: {head!r}"


def test_only_the_adapter_imports_the_benchmark() -> None:
    """R1.3/R6.2: exactly one seam. Enforced by AST, not by convention.

    Two evasions are checked, because the adapter itself uses the second one: importing an
    upstream module by name, and reaching the submodule by *path* and loading it with
    :mod:`importlib`. A path-based load is invisible to an import-name check, so any string
    naming the submodule outside ``collie/adapter/`` is treated as a breach of the seam.
    """
    offenders: list[str] = []
    allowed = {Path("collie/adapter")}
    upstream_top_level = {"or_agent", "policy_template", "textarena"}
    path_tells = ("third_party", "InventoryBench")

    for py in (REPO_ROOT / "collie").rglob("*.py"):
        rel = py.relative_to(REPO_ROOT)
        if any(parent in allowed for parent in rel.parents):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))

        # Docstrings are prose and may name the benchmark freely; only live strings can be a path.
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef):
                continue
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in upstream_top_level:
                    offenders.append(f"{rel}:{node.lineno} imports {name}")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and any(tell in node.value for tell in path_tells)
            ):
                offenders.append(
                    f"{rel}:{node.lineno} names the submodule path ({node.value!r}); "
                    "reach it through collie.adapter.inventorybench instead"
                )

    assert not offenders, "only collie/adapter/ may import the benchmark; found:\n  " + "\n  ".join(
        offenders
    )
