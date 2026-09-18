"""Acceptance tests for the closed ShockSpec registry."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "table,key,value,message",
    [
        ("FAMILY_SIGNATURE", ShockFamily.NO_CHANGE, None, "family/signature registry mismatch"),
        ("FAMILY_TARGET_STREAM", ShockFamily.NO_CHANGE, None, "cover every ShockFamily"),
        ("FAMILY_SIGNATURE", ShockFamily.NO_CHANGE, frozenset(), "at least one legal signature"),
        ("SIGNATURE_DIRECTION", "sig_compound", None, "exactly one registered direction"),
        (
            "FAMILY_SIGNATURE",
            ShockFamily.COMPOUND,
            frozenset({"unknown"}),
            "signature registry mismatch",
        ),
    ],
)
def test_registry_rejects_invalid_tables(monkeypatch, table, key, value, message):
    from collie.spec import registry

    changed = dict(getattr(registry, table))
    if value is None:
        del changed[key]
    else:
        changed[key] = value
    monkeypatch.setattr(registry, table, changed)
    with pytest.raises(RuntimeError, match=message):
        registry._validate_registry()


def test_registry_rejects_duplicate_signatures(monkeypatch):
    from collie.spec import registry

    monkeypatch.setattr(registry, "SIGNATURES", (*SIGNATURES, SIGNATURES[0]))
    with pytest.raises(RuntimeError, match="must not contain duplicates"):
        registry._validate_registry()


def test_unregistered_pair_has_no_direction():
    from collie.spec.registry import expected_direction

    with pytest.raises(ValueError, match="unregistered family/signature pair"):
        expected_direction(ShockFamily.COMPOUND, "sig_demand_level_up")


def test_registry_cli(capsys):
    import runpy
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("collie.spec.registry", run_name="__main__")
    assert "legal family/signature pairs: 8" in capsys.readouterr().out
