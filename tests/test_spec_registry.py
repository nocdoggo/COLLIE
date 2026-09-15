"""Acceptance tests for the closed ShockSpec registry."""

from __future__ import annotations

from collie.contracts import ShockFamily
from collie.spec.registry import FAMILY_SIGNATURE, SIGNATURES, legal_pairs


def test_every_family_has_a_legal_signature() -> None:
    assert set(FAMILY_SIGNATURE) == set(ShockFamily)
    assert all(FAMILY_SIGNATURE[family] for family in ShockFamily)

    registered = set(SIGNATURES)
    used = set().union(*FAMILY_SIGNATURE.values())
    assert used == registered, f"orphaned={registered - used}, unknown={used - registered}"
    assert len(SIGNATURES) == len(registered), "registered signatures must be unique"

    pairs = legal_pairs()
    print(f"legal family/signature pairs: {len(pairs)}")
    assert len(pairs) == 8
    assert len(pairs) == len(set(pairs))
