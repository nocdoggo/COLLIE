"""Branch G (P1). Arms 1-11, non-LLM controls, upper bounds, compile-once.

Arm 1 is the OR baseline: a faithful reimplementation of the published "OR (capped base stock)"
entry, verified to reproduce all 1,320 published order sequences bit for bit
(``reports/arm1_or_baseline.md``). Arms 3, 4, and 11 are the direct-action LLM arms on the
benchmark's own prompts (``docs/module06_research_notes.md`` §1); ``protocols.py`` holds the
injection seams to modules 02/04/05, and ``reference_control.py`` is the temporary module-04
stand-in that no arm may import (``tests/test_arms_isolation.py`` enforces it).
"""

from collie.arms.base_stock import (
    ARM1_ARM_ID,
    BaseStockParams,
    CappedBaseStockController,
    base_stock_order,
)
from collie.arms.direct import (
    ARM3_ARM_ID,
    ARM4_ARM_ID,
    ARM11_ARM_ID,
    DirectActionArm,
)
from collie.arms.protocols import (
    ActivationPolicy,
    ProposalPayload,
    SpecCompiler,
    SpecParser,
)

__all__ = [
    "ARM1_ARM_ID",
    "ARM3_ARM_ID",
    "ARM4_ARM_ID",
    "ARM11_ARM_ID",
    "ActivationPolicy",
    "BaseStockParams",
    "CappedBaseStockController",
    "DirectActionArm",
    "ProposalPayload",
    "SpecCompiler",
    "SpecParser",
    "base_stock_order",
]
