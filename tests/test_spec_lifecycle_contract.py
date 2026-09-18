"""Joint Module 2/5 lifecycle contract gate.

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


def test_fallback_is_identical_to_no_proposal_in_real_shockspec_arms(tmp_path) -> None:
    if importlib.util.find_spec("collie.arms.shockspec") is None:
        pytest.skip("external integration blocker: Module 6 collie.arms.shockspec does not exist")

    from collie.arms.shockspec import ARM8_ARM_ID, ImmediateActivation
    from collie.contracts import ParseOutcome
    from collie.sim.runner import EpisodeRunner
    from tests.test_arms_direct import _ScriptedTrigger
    from tests.test_arms_shockspec import _arm, _harness, _Parser
    from tests.test_episode_runner import make_instance

    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    transport, ledger, metered = _harness(tmp_path, default="BAD")

    no_proposal_arm = _arm(
        metered,
        instance,
        ImmediateActivation(),
        arm_id="contract_no_proposal",
        trigger=_ScriptedTrigger(set()),
    )
    fallback_arm = _arm(
        metered,
        instance,
        ImmediateActivation(),
        arm_id=ARM8_ARM_ID,
        trigger=_ScriptedTrigger({2}),
        parser=_Parser(payload=None),
    )

    no_proposal = EpisodeRunner(instance).run(no_proposal_arm)
    fallback = EpisodeRunner(instance).run(fallback_arm)

    assert [decision.order_quantity for decision in fallback.decisions] == [
        decision.order_quantity for decision in no_proposal.decisions
    ]
    assert all(
        decision.active_spec_id is None
        and decision.control_config is None
        and decision.lifecycle_state is None
        for decision in fallback.decisions
    )

    charged = ledger.charged_entries()
    assert transport.n_calls == 1
    assert len(charged) == 1
    assert charged[0].arm_id == ARM8_ARM_ID
    assert charged[0].outcome is ParseOutcome.FALLBACK
    ledger.assert_conserved()
