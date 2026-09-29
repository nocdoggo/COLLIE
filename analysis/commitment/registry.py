"""Arm-set registry shared by the runner and the arm modules (kept apart from the runner so that
``python -m analysis.commitment.runner`` and imported copies see the same dictionary)."""

from __future__ import annotations

from collections.abc import Callable

import analysis.real_content_pilot.runner as rcp

ArmBuilder = Callable[..., list[tuple[str, object, bool]]]
ARM_SETS: dict[str, ArmBuilder] = {"nine": rcp.build_arms}
"""Arm-set name -> builder with ``rcp.build_arms``'s signature."""


def register_arm_set(name: str, builder: ArmBuilder) -> None:
    ARM_SETS[name] = builder
