"""Branch E (P1). Deterministic compiler, 72-config grid, capped base-stock, FIFO ledger.

``mapping.compile_spec`` is the only path from a ``ShockSpec`` to a ``ControlConfig``,
``controller.OrCompilerController`` is the only controller every OR-compiler arm wraps, and
``ledger.FIFOLedger`` is control-side telemetry that must never reach ``collie/verify/``
(``docs/implementation/04-or-compiler.md``).
"""

from collie.control.controller import OrCompilerController, base_stock_target, critical_fractile
from collie.control.forecast import DemandForecaster, ForecastStats, forecast_stats
from collie.control.grid import (
    BASELINE_CONFIG,
    GAMMA_VALUES,
    L_EFF_VALUES,
    M_VALUES,
    all_configs,
    predictive_model_for,
    predictive_model_keys,
)
from collie.control.ledger import (
    AgedUnits,
    FIFOLedger,
    LedgerInconsistency,
    LedgerLeak,
    assert_no_ledger_state,
    find_ledger_state,
    scan_for_ledger_references,
)
from collie.control.mapping import (
    CANONICAL_SHAPES,
    GridCompiler,
    compile_spec,
    iter_legal_specs,
    mapping_table,
)

__all__ = [
    "BASELINE_CONFIG",
    "CANONICAL_SHAPES",
    "GAMMA_VALUES",
    "L_EFF_VALUES",
    "M_VALUES",
    "AgedUnits",
    "DemandForecaster",
    "FIFOLedger",
    "ForecastStats",
    "GridCompiler",
    "LedgerInconsistency",
    "LedgerLeak",
    "OrCompilerController",
    "all_configs",
    "assert_no_ledger_state",
    "base_stock_target",
    "compile_spec",
    "critical_fractile",
    "find_ledger_state",
    "forecast_stats",
    "iter_legal_specs",
    "mapping_table",
    "predictive_model_for",
    "predictive_model_keys",
    "scan_for_ledger_references",
]
