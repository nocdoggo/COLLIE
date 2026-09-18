"""The imputed FIFO ledger — a control convenience, never evidence.

InventoryBench exposes in-transit inventory as a scalar with no shipment ages
(``docs/env_contract.md`` §4). Any age-resolved view of the pipeline is therefore an
**imputation** from the controller's own order history plus observed aggregate receipts, never an
observation — many different shipment-level histories are consistent with the same aggregate
receipt stream. Every value this module produces carries an explicit imputation marker for that
reason.

When the ledger cannot reconcile — a receipt bigger than every outstanding order can explain — it
**records the inconsistency and moves on**. It never rebalances to make the books look tidy: the
inconsistency is the observable signature of a lost shipment or a stalled pipeline, exactly the
signal a controller needs, and smoothing it away would erase it.

Forbidden inputs, enforced by this module simply never importing them: ``supply.csv``,
``incident.json``, shipment ages, actual lead times. The ledger only ever sees the two aggregate
scalars a controller already legitimately has: the quantities it dispatched itself, and the
aggregate receipts the runner reports.

**The ledger must never reach the verifier.** The verifier's validity argument rests on
conditioning only on quantities whose conditional law is registered; the ledger is inferred from
the controller's own actions, so feeding it to the verifier would condition the test on the policy
being tested. ``scan_for_ledger_references`` is the static half of that guarantee (an AST scan
over ``collie/verify/``, run by ``tests/test_ledger_not_evidence.py``); ``assert_no_ledger_state``
is the runtime half (an object-graph walk over whatever module 05 is about to consume, mirroring
``collie.contracts.assert_no_hidden_state`` but for this module's own types, since
``collie/contracts.py`` is frozen and does not know about the ledger).
"""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "AgedUnits",
    "FIFOLedger",
    "LedgerInconsistency",
    "LedgerLeak",
    "assert_no_ledger_state",
    "find_ledger_state",
    "scan_for_ledger_references",
]


@dataclass(frozen=True, slots=True)
class AgedUnits:
    """One imputed cohort-age assignment. ``imputed`` is always ``True``: this is an inference
    the ledger drew, never a quantity the benchmark observed."""

    age: int
    quantity: float
    imputed: bool = True


@dataclass(frozen=True, slots=True)
class LedgerInconsistency:
    """A receipt no outstanding order can explain, recorded rather than rebalanced away."""

    period: int
    unexplained_quantity: float
    note: str


@dataclass(slots=True)
class _Cohort:
    ordered_period: int
    remaining: float


_EPS = 1e-9


@dataclass(slots=True)
class FIFOLedger:
    """FIFO assignment of aggregate receipts to the controller's own outstanding orders.

    Fed by exactly two calls, ``record_order`` and ``record_receipt``, both of which take
    quantities a controller already legitimately has. Nothing else reaches this class.
    """

    _cohorts: deque[_Cohort] = field(default_factory=deque, repr=False)
    _inconsistencies: list[LedgerInconsistency] = field(default_factory=list, repr=False)
    _aged_log: list[AgedUnits] = field(default_factory=list, repr=False)

    def record_order(self, period: int, quantity: float) -> None:
        if quantity > _EPS:
            self._cohorts.append(_Cohort(ordered_period=period, remaining=quantity))

    def record_receipt(self, period: int, quantity: float) -> None:
        """Assign ``quantity`` to the oldest outstanding cohorts first. Whatever is left over
        once every cohort is exhausted is an inconsistency, not a rebalancing opportunity."""
        remaining = quantity
        while remaining > _EPS and self._cohorts:
            cohort = self._cohorts[0]
            taken = min(remaining, cohort.remaining)
            cohort.remaining -= taken
            remaining -= taken
            self._aged_log.append(AgedUnits(age=period - cohort.ordered_period, quantity=taken))
            if cohort.remaining <= _EPS:
                self._cohorts.popleft()
        if remaining > _EPS:
            self._inconsistencies.append(
                LedgerInconsistency(
                    period=period,
                    unexplained_quantity=remaining,
                    note=(
                        "receipt exceeds every outstanding order; the observable signature of a "
                        "lost shipment surfacing elsewhere or an order placed before this ledger "
                        "started tracking"
                    ),
                )
            )

    @property
    def inconsistencies(self) -> tuple[LedgerInconsistency, ...]:
        return tuple(self._inconsistencies)

    @property
    def outstanding_total(self) -> float:
        return sum(c.remaining for c in self._cohorts)

    def aged_mass(self) -> tuple[AgedUnits, ...]:
        """Every imputed age assignment made so far. Control-side telemetry only; see the module
        docstring for why this must never reach the verifier."""
        return tuple(self._aged_log)


# ---------------------------------------------------------------------------
# ledger-is-not-evidence: static half
# ---------------------------------------------------------------------------

_LEDGER_MODULE = "collie.control.ledger"
_LEDGER_SYMBOLS: frozenset[str] = frozenset(
    {
        "FIFOLedger",
        "AgedUnits",
        "LedgerInconsistency",
        "aged_mass",
        "record_order",
        "record_receipt",
        "outstanding_total",
    }
)


class LedgerLeak(AssertionError):
    """Raised when the imputed ledger is reachable from verifier source or verifier inputs."""


def scan_for_ledger_references(paths: Iterable[Path]) -> list[str]:
    """AST scan for any reference to this module or its symbols. Static half of the
    ledger-is-not-evidence guarantee; ``assert_no_ledger_state`` is the runtime half."""
    offenders: list[str] = []
    for py in paths:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _LEDGER_SYMBOLS:
                offenders.append(f"{py}:{node.lineno} references {node.id}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == _LEDGER_MODULE or mod.startswith(_LEDGER_MODULE + "."):
                    offenders.append(f"{py}:{node.lineno} imports from {mod}")
                for alias in node.names:
                    if alias.name in _LEDGER_SYMBOLS:
                        offenders.append(f"{py}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.Attribute) and node.attr in _LEDGER_SYMBOLS:
                offenders.append(f"{py}:{node.lineno} accesses .{node.attr}")
    return offenders


# ---------------------------------------------------------------------------
# ledger-is-not-evidence: runtime half
# ---------------------------------------------------------------------------

_LEDGER_TYPES: tuple[type, ...] = (FIFOLedger, AgedUnits, LedgerInconsistency)
_ATOMIC = (str, bytes, int, float, bool, complex, type(None))
_MAX_DEPTH = 12


def _children(obj: Any) -> Iterator[tuple[str, Any]]:
    if is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            yield f".{f.name}", getattr(obj, f.name, None)
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            yield f"[{k!r}]", v
    elif isinstance(obj, Sequence | set | frozenset) and not isinstance(obj, str | bytes):
        for i, v in enumerate(obj):
            yield f"[{i}]", v
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            yield f".{k}", v


def find_ledger_state(obj: Any, *, root: str = "obj") -> list[str]:
    """Walk the object graph and return the access path of every ledger object reachable.
    Structural, mirroring ``collie.contracts.find_hidden_state``: a leak through an undeclared
    attribute or a nested container is caught the same way as a declared field."""
    found: list[str] = []
    seen: set[int] = set()

    def walk(node: Any, path: str, depth: int) -> None:
        if depth > _MAX_DEPTH or isinstance(node, _ATOMIC):
            return
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, _LEDGER_TYPES):
            found.append(path)
            return
        for suffix, child in _children(node):
            walk(child, path + suffix, depth + 1)

    walk(obj, root, 0)
    return found


def assert_no_ledger_state(obj: Any, *, context: str = "") -> None:
    """Raise :class:`LedgerLeak` if the imputed ledger is reachable from ``obj``."""
    leaks = find_ledger_state(obj)
    if leaks:
        where = f" in {context}" if context else ""
        raise LedgerLeak(
            f"imputed ledger reachable{where} via: {', '.join(sorted(leaks))}. "
            "The ledger informs control only; feeding it to the verifier conditions the "
            "sequential test on the policy being tested."
        )
