"""Joint Module 2/5 lifecycle contract — live since both registries landed.

Module 02 owns the legal family/signature registry; module 05 owns the construction registry.
This file pins the convergence of the two, in both directions, against the production code —
no mirror tables. It also pins that the abstention placeholder resolves to nothing on either
side. Until both modules shared a tree, these tests carried fail-forward skip guards; the
guards did their job and are gone.
"""

from __future__ import annotations

import pytest

from collie.contracts import (
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
)
from collie.spec.registry import (
    FAMILY_TARGET_STREAM,
    ONSET_WINDOWS,
    expected_direction,
    legal_pairs,
)
from collie.verify.registry import (
    CONSTRUCTIONS,
    REGISTERED_ONSET_WINDOWS,
    resolve_spec,
    resolve_spec_shape,
)


def _spec_for(family: ShockFamily, signature: str) -> ShockSpec:
    """A schema-valid spec for one registered pair, built from module 02's vocabulary."""
    is_abstention = family is ShockFamily.NO_CHANGE
    return ShockSpec(
        target_stream=FAMILY_TARGET_STREAM[family],
        shock_family=family,
        direction=expected_direction(family, signature),
        onset_window=None if is_abstention else ONSET_WINDOWS[0],
        magnitude_bin=None if is_abstention else MagnitudeBin.MEDIUM,
        persistence=Persistence.NONE if is_abstention else Persistence.PERSISTENT,
        duration_bin=DurationBin.NONE if is_abstention else DurationBin.LONGER,
        evidence_refs=(),
        prospective_signature=signature,
        tau_j=12,
        proposal_index=1,
        model_id="spec_lifecycle_contract",
        decoding_hash="d" * 8,
        prompt_hash="p" * 8,
    )


def test_onset_window_registries_agree() -> None:
    """Both modules registered onset windows independently; the joint claim needs one truth."""
    assert tuple(ONSET_WINDOWS) == tuple(REGISTERED_ONSET_WINDOWS)


def test_spec_maps_to_exactly_one_verifier_construction() -> None:
    """The two-direction joint enumeration, over production registries.

    Forward: every legal non-abstention pair resolves to exactly one construction, through
    both entry points, with family/signature/stream/direction all agreeing. Reverse: every
    registered construction is reached by exactly one legal pair — none orphaned, none
    doubly claimed.
    """
    seen: dict[tuple[ShockFamily, str], str] = {}
    for family, signature in legal_pairs():
        if family is ShockFamily.NO_CHANGE:
            continue  # the abstention placeholder has its own test below
        spec = _spec_for(family, signature)
        construction = resolve_spec(spec)
        assert resolve_spec_shape(family, signature) is construction
        assert construction.family is family
        assert construction.signature == signature
        assert construction.stream is spec.target_stream
        assert construction.direction is spec.direction
        seen[(family, signature)] = construction.predictive_model

    assert set(seen.values()) == set(CONSTRUCTIONS), (
        f"constructions unreachable from module 02's registry: "
        f"{sorted(set(CONSTRUCTIONS) - set(seen.values()))}"
    )
    assert len(seen.values()) == len(set(seen.values())), (
        "two legal pairs claim the same construction"
    )


def test_no_change_placeholder_is_ignored_by_real_compiler_and_verifier() -> None:
    """The registered abstention placeholder (``sig_demand_level_up`` under ``no_change``)
    resolves to nothing on either side: never a demand-up construction, and the compiler
    leaves the running config untouched."""
    from collie.control.grid import baseline_config_for
    from collie.control.mapping import GridCompiler

    spec = _spec_for(ShockFamily.NO_CHANGE, "sig_demand_level_up")
    assert spec.is_abstention

    with pytest.raises(ValueError, match="abstention"):
        resolve_spec(spec)
    with pytest.raises(KeyError):
        resolve_spec_shape(ShockFamily.NO_CHANGE, "sig_demand_level_up")

    current = baseline_config_for(2)
    assert GridCompiler().compile(spec, current=current) == current


def test_fallback_is_identical_to_no_proposal_in_real_shockspec_arms(tmp_path) -> None:
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
