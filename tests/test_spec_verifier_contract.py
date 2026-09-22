"""Module 02/05 contract test, in both directions against the merged registries."""

from __future__ import annotations

import json

import pytest

from collie.contracts import (
    Direction,
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.fakes import canned
from collie.verify.registry import CONSTRUCTIONS, resolve_spec, resolve_spec_shape

# Module 02 side of the interface, transcribed independently of Module 05's CONSTRUCTIONS table
# so this file fails when either side drifts.  Module 02 has landed, and the second test below
# compares this transcription against its production registry, which makes the two mutual
# cross-checks: a silent edit to either table, or to this transcription, breaks a test.
MODULE02_ACTIONABLE_SHAPES = {
    (ShockFamily.DEMAND_LEVEL, "sig_demand_level_up", TargetStream.DEMAND, Direction.DEMAND_UP),
    (
        ShockFamily.DEMAND_LEVEL,
        "sig_demand_level_down",
        TargetStream.DEMAND,
        Direction.DEMAND_DOWN,
    ),
    (
        ShockFamily.TEMPORARY_PULSE,
        "sig_demand_pulse",
        TargetStream.DEMAND,
        Direction.DEMAND_UP,
    ),
    (
        ShockFamily.LEAD_TIME_SHIFT,
        "sig_arrival_delay",
        TargetStream.ARRIVAL,
        Direction.ARRIVAL_DELAYED,
    ),
    (
        ShockFamily.SHIPMENT_LOSS,
        "sig_arrival_loss",
        TargetStream.ARRIVAL,
        Direction.ARRIVAL_INTERRUPTED,
    ),
    (
        ShockFamily.TRANSIT_PAUSE,
        "sig_arrival_stall",
        TargetStream.ARRIVAL,
        Direction.ARRIVAL_INTERRUPTED,
    ),
    (ShockFamily.COMPOUND, "sig_compound", TargetStream.BOTH, Direction.MIXED),
}


def _spec_for_shape(
    family: ShockFamily,
    signature: str,
    stream: TargetStream,
    direction: Direction,
) -> ShockSpec:
    return ShockSpec(
        target_stream=stream,
        shock_family=family,
        direction=direction,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.TRANSIENT,
        duration_bin=DurationBin.MEDIUM,
        evidence_refs=("obs_t4",),
        prospective_signature=signature,
        tau_j=4,
        proposal_index=1,
        model_id="contract-test",
        decoding_hash="frozen",
        prompt_hash="frozen",
    )


def test_spec_maps_to_exactly_one_construction() -> None:
    resolved = set()
    for shape in MODULE02_ACTIONABLE_SHAPES:
        spec = _spec_for_shape(*shape)
        construction = resolve_spec(spec)
        assert construction.stream is spec.target_stream
        assert construction.direction is spec.direction
        resolved.add(construction.predictive_model)
    assert resolved == set(CONSTRUCTIONS)
    assert len(resolved) == len(MODULE02_ACTIONABLE_SHAPES) == 7


def test_module02_and_verifier_registries_match() -> None:
    """Module 02's production pairing registry against module 05's construction registry.

    Both sides have landed, so this reads the real ``FAMILY_SIGNATURE`` unconditionally; the
    late-convergence fallback that used to stand in for an absent ``collie.spec.registry`` is
    gone rather than left as a branch nothing can reach.
    """
    from collie.spec.registry import FAMILY_SIGNATURE

    module02_pairs = {
        (family, signature)
        for family, signatures in FAMILY_SIGNATURE.items()
        if family is not ShockFamily.NO_CHANGE
        for signature in signatures
    }
    verifier_pairs = {(item.family, item.signature) for item in CONSTRUCTIONS.values()}
    assert module02_pairs == verifier_pairs
    # And the independent transcription at the top of this file still agrees with both, so a
    # matched edit to the two registries cannot pass unnoticed.
    assert module02_pairs == {
        (family, signature) for family, signature, _, _ in MODULE02_ACTIONABLE_SHAPES
    }


def test_foundation_module02_fake_reaches_the_registered_verifier() -> None:
    payload = json.loads(canned.VALID)
    payload.update(
        tau_j=4,
        proposal_index=1,
        model_id="fake-open-weight-7b",
        decoding_hash="det-v1",
        prompt_hash="fake-contract",
    )
    spec = ShockSpec.model_validate(payload)
    construction = resolve_spec(spec)
    assert construction.predictive_model == "arrival_stall"


def test_schema_cannot_reach_an_unregistered_construction() -> None:
    legal_pairs = {(family, signature) for family, signature, _, _ in MODULE02_ACTIONABLE_SHAPES}
    signatures = {signature for _, signature, _, _ in MODULE02_ACTIONABLE_SHAPES}
    for family in ShockFamily:
        for signature in signatures:
            if (family, signature) in legal_pairs:
                continue
            with pytest.raises(KeyError, match="no verifier construction"):
                resolve_spec_shape(family, signature)


def test_closed_contract_cannot_smuggle_a_custom_test() -> None:
    payload = _spec_for_shape(
        ShockFamily.DEMAND_LEVEL,
        "sig_demand_level_up",
        TargetStream.DEMAND,
        Direction.DEMAND_UP,
    ).model_dump()
    payload["threshold"] = 1.01
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ShockSpec.model_validate(payload)


def test_unregistered_onset_window_cannot_reach_a_verifier() -> None:
    spec = _spec_for_shape(
        ShockFamily.DEMAND_LEVEL,
        "sig_demand_level_up",
        TargetStream.DEMAND,
        Direction.DEMAND_UP,
    ).model_copy(update={"onset_window": (0, 0)})
    with pytest.raises(ValueError, match="unregistered onset_window"):
        resolve_spec(spec)
