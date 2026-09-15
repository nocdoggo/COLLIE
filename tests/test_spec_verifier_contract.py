"""Joint Module 2/5 contract gate.

This file deliberately stays skipped until Module 5 publishes its real
construction registry. A fake registry would make the central claim circular.
"""

from __future__ import annotations

import importlib.util

import pytest


def test_spec_maps_to_exactly_one_verifier_construction() -> None:
    if importlib.util.find_spec("collie.verify.registry") is None:
        pytest.skip("external integration blocker: Module 5 collie.verify.registry does not exist")
    pytest.fail(
        "Module 5 registry is now present: P3 and P4 must replace this guard with the "
        "two-direction joint enumeration before Gate 2"
    )


def test_no_change_placeholder_is_ignored_by_real_compiler_and_verifier() -> None:
    missing = [
        name
        for name in ("collie.control.mapping", "collie.verify.registry")
        if importlib.util.find_spec(name) is None
    ]
    if missing:
        pytest.skip(f"external integration blocker: {', '.join(missing)}")
    pytest.fail(
        "Real consumers now exist: implement abstention-first resolution and baseline mapping "
        "checks against them; never resolve the placeholder as a demand-up construction."
    )


def test_fallback_is_identical_to_no_proposal_in_real_shockspec_arms() -> None:
    if importlib.util.find_spec("collie.arms.shockspec") is None:
        pytest.skip("external integration blocker: Module 6 collie.arms.shockspec does not exist")
    pytest.fail(
        "Real ShockSpec arms now exist: run fallback and no-proposal episodes through them, "
        "assert full order-path equality and retained call accounting."
    )
