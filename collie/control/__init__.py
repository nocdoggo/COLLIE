"""Branch E (P1). Deterministic compiler, 72-config grid, capped base-stock, FIFO ledger.

``mapping.compile_spec`` is the only path from a ``ShockSpec`` to a ``ControlConfig``, and
``controller.OrCompilerController`` is the only controller every OR-compiler arm wraps
(``docs/implementation/04-or-compiler.md``). The FIFO ledger is a Checkpoint 2 deliverable and
lands in a later commit.
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
from collie.control.mapping import CANONICAL_SHAPES, compile_spec, iter_legal_specs, mapping_table

__all__ = [
    "BASELINE_CONFIG",
    "CANONICAL_SHAPES",
    "GAMMA_VALUES",
    "L_EFF_VALUES",
    "M_VALUES",
    "DemandForecaster",
    "ForecastStats",
    "OrCompilerController",
    "all_configs",
    "base_stock_target",
    "compile_spec",
    "critical_fractile",
    "forecast_stats",
    "iter_legal_specs",
    "mapping_table",
    "predictive_model_for",
    "predictive_model_keys",
]
