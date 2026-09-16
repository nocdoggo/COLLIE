"""Branch G (P1). Arms 1-11, non-LLM controls, upper bounds, compile-once.

Arm 1 is the OR baseline: a faithful reimplementation of the published "OR (capped base stock)"
entry, verified to reproduce all 1,320 published order sequences bit for bit
(``reports/arm1_or_baseline.md``). Arms 3, 4, and 11 are the direct-action LLM arms on the
benchmark's own prompts (``docs/module06_research_notes.md`` §1); ``protocols.py`` holds the
injection seams to modules 02/04/05. Module 04's real implementation
(``collie.control.mapping.GridCompiler`` and
``collie.control.controller.OrCompilerController``) is wired into the arms by injection in
``tests/conftest.py`` and ``tools/run_arms.py`` — no arm may import it
(``tests/test_arms_isolation.py`` enforces it).
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
from collie.arms.llm_to_or import (
    ARM5_ARM_ID,
    ARM6_ARM_ID,
    ARM7_ARM_ID,
    PERSISTENCE_EXPIRY,
    LlmToOrArm,
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
    "ARM5_ARM_ID",
    "ARM6_ARM_ID",
    "ARM7_ARM_ID",
    "ARM11_ARM_ID",
    "PERSISTENCE_EXPIRY",
    "ActivationPolicy",
    "BaseStockParams",
    "CappedBaseStockController",
    "DirectActionArm",
    "LlmToOrArm",
    "ProposalPayload",
    "SpecCompiler",
    "SpecParser",
    "base_stock_order",
]
