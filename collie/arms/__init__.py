"""Branch G (P1). Arms 1-10, non-LLM controls, upper bounds, compile-once.

Arm 1 is the OR baseline: a faithful reimplementation of the published "OR (capped base stock)"
entry, verified to reproduce all 1,320 published order sequences bit for bit
(``reports/arm1_or_baseline.md``).
"""

from collie.arms.base_stock import (
    ARM1_ARM_ID,
    BaseStockParams,
    CappedBaseStockController,
    base_stock_order,
)
from collie.arms.oracle import ORACLE_ARM_ID, oracle_config_for, oracle_controller_for

__all__ = [
    "ARM1_ARM_ID",
    "ORACLE_ARM_ID",
    "BaseStockParams",
    "CappedBaseStockController",
    "base_stock_order",
    "oracle_config_for",
    "oracle_controller_for",
]
