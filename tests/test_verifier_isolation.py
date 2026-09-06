"""Module 05 CP1 isolation checks: verifier code sees observables and registered models only."""

from __future__ import annotations

import ast
from pathlib import Path

from collie.contracts import Direction, assert_no_hidden_state
from collie.data.families.base import BaselineSpec
from collie.verify.demand import DemandEProcess

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SYMBOLS = {"HiddenIncident", "HiddenAlertSpec", "SupplyRealization"}


def test_verifier_reads_no_forbidden_input() -> None:
    offenders: list[str] = []
    for path in (REPO_ROOT / "collie/verify").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_SYMBOLS:
                offenders.append(f"{path.name}:{node.lineno}:{node.id}")
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in FORBIDDEN_SYMBOLS:
                        offenders.append(f"{path.name}:{node.lineno}:{alias.name}")
    assert not offenders


def test_constructed_verifier_object_graph_contains_no_hidden_state() -> None:
    verifier = DemandEProcess.for_level_change(
        baseline=BaselineSpec(),
        direction=Direction.DEMAND_UP,
        tau_j=10,
        alpha_episode=0.05,
        history_before_proposal=(100.0,) * 10,
    )
    assert_no_hidden_state(verifier, context="demand verifier")


def test_verifier_package_never_imports_control_ledger() -> None:
    offenders = []
    for path in (REPO_ROOT / "collie/verify").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "collie.control.ledger" in text:
            offenders.append(path.name)
    assert not offenders
