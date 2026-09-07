"""Cross-arm isolation and seam discipline.

Grows over Waves 3-6: the reference-control import ban (below), then the full-ladder
``check_controller_isolation`` sweep once arms 5-10 exist.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARMS = REPO_ROOT / "collie" / "arms"
STAND_IN = "collie.arms.reference_control"


def test_no_arm_imports_the_reference_control_stand_in() -> None:
    """Module brief §3: the module-04 stand-in reaches arms only by injection.

    Enforced by AST, in the style of
    ``tests/test_project_skeleton.py::test_only_the_adapter_imports_the_benchmark``. The wiring
    (``tests/conftest.py``, ``tools/run_arms.py``) imports the stand-in; no file under
    ``collie/arms/`` may, or module 04's drop-in replacement would not be a clean swap. When the
    stand-in is deleted on module 04's merge, this test goes with it.
    """
    stand_in_path = ARMS / "reference_control.py"
    assert stand_in_path.is_file(), (
        "the stand-in is gone — delete this test with it (module 04 has landed)"
    )
    offenders: list[str] = []
    for py in sorted(ARMS.rglob("*.py")):
        if py.name == "reference_control.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name == STAND_IN or name.startswith(STAND_IN + "."):
                    offenders.append(f"{py.relative_to(REPO_ROOT)} imports {name}")
    assert offenders == [], f"arms must not import the stand-in: {offenders}"
