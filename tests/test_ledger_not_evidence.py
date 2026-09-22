"""Module 04, Checkpoint 2 — the ledger must never reach the verifier.

Two independent checks, both required by ``docs/implementation/04-or-compiler.md``: a static AST
scan over ``collie/verify/`` and a runtime object-graph walk over whatever is about to be handed
to a verifier. Module 05 has landed, so the static scan now runs over the real e-process,
arrival, lifecycle, and adapter sources rather than an empty package. Both checks are also
proven against a deliberately leaky fixture, so they are demonstrated to actually fire rather
than passing vacuously over clean code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from collie.control.ledger import (
    FIFOLedger,
    LedgerLeak,
    assert_no_ledger_state,
    find_ledger_state,
    scan_for_ledger_references,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_DIR = REPO_ROOT / "collie" / "verify"

_LEAKY_SOURCE = """
from collie.control.ledger import FIFOLedger

class LeakyConstruction:
    def __init__(self):
        self.ledger = FIFOLedger()

    def alpha_process(self, obs):
        return self.ledger.outstanding_total
"""


# ---------------------------------------------------------------------------
# static check
# ---------------------------------------------------------------------------


def test_real_verify_package_has_no_ledger_references() -> None:
    """The merged ``collie/verify/`` passes cleanly. This is the check the Checkpoint 2 audit
    runs; it keeps passing now that module 05 has landed precisely because that module must
    never import the ledger. The ``paths`` assertion keeps it from passing vacuously."""
    paths = list(VERIFY_DIR.rglob("*.py"))
    assert paths, "collie/verify/ has no python files to scan; the scan would prove nothing"
    assert scan_for_ledger_references(paths) == []


def test_leaky_verifier_fails_static_check(tmp_path: Path) -> None:
    leaky = tmp_path / "leaky_construction.py"
    leaky.write_text(_LEAKY_SOURCE, encoding="utf-8")

    offenders = scan_for_ledger_references([leaky])
    assert offenders, "the static scan must fire on a construction that imports FIFOLedger"
    assert any("FIFOLedger" in o for o in offenders)


def test_static_scan_catches_attribute_access_too(tmp_path: Path) -> None:
    """Not just an import — reaching the ledger via an already-imported alias must also fire."""
    leaky = tmp_path / "leaky_via_module.py"
    leaky.write_text(
        "import collie.control.ledger as L\n\ndef f(x):\n    return x.aged_mass()\n",
        encoding="utf-8",
    )
    offenders = scan_for_ledger_references([leaky])
    assert offenders


# ---------------------------------------------------------------------------
# runtime check
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _LeakyVerifierInputs:
    """Stands in for the bundle module 05 passes its construction: a plausible verifier-input
    shape that got the ledger smuggled into it through a nested field."""

    period: int
    observed_value: float
    telemetry: dict = field(default_factory=dict)


def test_leaky_verifier_fails_runtime_check() -> None:
    leaky = _LeakyVerifierInputs(period=7, observed_value=3.0, telemetry={"pipeline": FIFOLedger()})
    leaks = find_ledger_state(leaky)
    assert leaks == ["obj.telemetry['pipeline']"]
    with pytest.raises(LedgerLeak):
        assert_no_ledger_state(leaky, context="verifier construction input")


def test_runtime_check_passes_on_clean_verifier_inputs() -> None:
    clean = _LeakyVerifierInputs(period=7, observed_value=3.0, telemetry={"note": "fine"})
    assert find_ledger_state(clean) == []
    assert_no_ledger_state(clean, context="verifier construction input")  # must not raise


def test_runtime_check_catches_a_ledger_nested_several_levels_deep() -> None:
    nested = {"a": [1, 2, {"b": (FIFOLedger(),)}]}
    leaks = find_ledger_state(nested)
    assert leaks == ["obj['a'][2]['b'][0]"]


class _PlainBox:
    """Not a dataclass: the runtime walk must still descend through a plain ``__dict__``."""

    def __init__(self, held) -> None:
        self.held = held


def test_runtime_check_catches_a_ledger_behind_a_plain_object() -> None:
    """A leak hidden in a non-dataclass attribute is the same leak; the ``__dict__`` branch of
    the object-graph walk is what stands between it and the verifier."""
    box = _PlainBox(FIFOLedger())
    assert find_ledger_state(box) == ["obj.held"]
    with pytest.raises(LedgerLeak):
        assert_no_ledger_state(box, context="verifier construction input")


def test_runtime_walk_reports_a_shared_ledger_once() -> None:
    """The same object reachable twice is one leak, not two — the walk's seen-set short-circuits
    the second visit, so leak paths never duplicate."""
    shared = _PlainBox(FIFOLedger())
    leaks = find_ledger_state([shared, shared])
    assert leaks == ["obj[0].held"]
