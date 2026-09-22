"""Module 04 <-> 05 joint consistency: compiler labels vs verifier constructions.

This is the executable form of the 2026-09-18 key-space decision (prereg/deviations.md): the
compiler's ``predictive_model`` is descriptive metadata derived from grid coordinates, and the
verifier derives its construction from the ``ShockSpec`` itself. The joint invariant is a
**compatibility** relation, asserted in both directions plus per spec:

1. every label the grid can emit has a table entry — no unlabelled key, no stale entry;
2. every non-baseline label is compatible with at least one construction;
3. every construction is reachable from at least one label;
4. for every spec the verifier accepts, the compiled label is compatible with the resolved
   construction — including the pulse cell, where one compiler label legitimately covers two
   different constructions (level shift and bounded-duration pulse);
5. a shape outside the registered space (pulse-down) is rejected loudly, so it cannot silently
   become expressible later. Module 02's pairing registry has landed and settled the question
   the other way from module 04's tier-1 table: ``collie.spec.registry`` registers
   ``sig_demand_pulse`` as ``demand_up`` only, so pulse-down is not expressible on the spec
   side and this assertion is now the standing guard rather than a placeholder.
"""

from __future__ import annotations

import pytest

from collie.contracts import (
    Direction,
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockSpec,
)
from collie.control.grid import predictive_model_keys
from collie.control.mapping import compile_spec
from collie.verify.registry import CONSTRUCTIONS, resolve_spec

# The joint-seam table. Left: a label module 04's grid can emit. Right: the verifier
# constructions a spec resolved through ``collie.verify.registry`` may hold when the compiler
# reports that label. ``stationary`` is the baseline point: an abstention compiles to it and
# has no construction by design (``resolve_spec`` raises on abstention).
#
# ``lead_time_delay`` legitimately covers ``arrival_stall`` as well as ``arrival_delay``:
# module 04's tier-1 row expresses a low/medium-severity transit pause as a longer pipeline
# with full pipeline credit — coordinate-identical to a delay — so a pause spec compiles to
# the delay label while the verifier correctly tests the frozen-counter construction. The
# pairing can be tightened if module 04's owner recalibrates that row (the open tier-1
# question from the 2026-09-16 deviation entry); the test stays green either way.
COMPILER_LABEL_COMPATIBILITY: dict[str, frozenset[str]] = {
    "demand_up": frozenset({"demand_level_up", "demand_pulse"}),
    "demand_down": frozenset({"demand_level_down"}),
    "lead_time_delay": frozenset({"arrival_delay", "arrival_stall"}),
    "shipment_loss": frozenset({"arrival_loss"}),
    "transit_stall": frozenset({"arrival_stall"}),
    "compound_demand_up_lead_time_delay": frozenset({"compound_split"}),
    "compound_demand_up_shipment_loss": frozenset({"compound_split"}),
    "compound_demand_up_transit_stall": frozenset({"compound_split"}),
    "compound_demand_down_lead_time_delay": frozenset({"compound_split"}),
    "compound_demand_down_shipment_loss": frozenset({"compound_split"}),
    "compound_demand_down_transit_stall": frozenset({"compound_split"}),
    "stationary": frozenset(),
}


def _spec_for(construction_key: str) -> ShockSpec:
    """A schema-valid spec resolving to exactly the given registered construction."""
    construction = CONSTRUCTIONS[construction_key]
    return ShockSpec(
        target_stream=construction.stream,
        shock_family=construction.family,
        direction=construction.direction,
        onset_window=(-2, 0),  # one of the registry's REGISTERED_ONSET_WINDOWS
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=Persistence.PERSISTENT,
        duration_bin=DurationBin.LONGER,
        evidence_refs=(),
        prospective_signature=construction.signature,
        tau_j=12,
        proposal_index=1,
        model_id="joint_compatibility_test",
        decoding_hash="d" * 8,
        prompt_hash="p" * 8,
    )


def test_the_table_covers_the_grid_label_space_exactly() -> None:
    """Direction 1: no compiler label without a table entry, no stale table entry."""
    assert set(COMPILER_LABEL_COMPATIBILITY) == set(predictive_model_keys())


def test_every_non_baseline_label_has_a_compatible_construction() -> None:
    """Direction 2: the compiler cannot emit a belief the verifier cannot test."""
    for label, constructions in COMPILER_LABEL_COMPATIBILITY.items():
        if label == "stationary":
            continue
        assert constructions, f"compiler label {label!r} has no compatible construction"
        assert constructions <= set(CONSTRUCTIONS), (
            f"table names constructions the registry does not hold: "
            f"{sorted(constructions - set(CONSTRUCTIONS))}"
        )


def test_every_construction_is_reachable_from_a_label() -> None:
    """Direction 3: no registered construction is orphaned by the compiler's label space."""
    reachable = set().union(*COMPILER_LABEL_COMPATIBILITY.values())
    assert set(CONSTRUCTIONS) <= reachable, (
        f"constructions no compiler label reaches: {sorted(set(CONSTRUCTIONS) - reachable)}"
    )


@pytest.mark.parametrize("construction_key", sorted(CONSTRUCTIONS))
def test_compiled_label_is_compatible_with_the_resolved_construction(
    construction_key: str,
) -> None:
    """Direction 4, per spec: compile and resolve the same spec, then relate the two."""
    spec = _spec_for(construction_key)
    compiled_label = compile_spec(spec).predictive_model
    resolved = resolve_spec(spec)
    assert resolved.predictive_model == construction_key
    assert resolved.predictive_model in COMPILER_LABEL_COMPATIBILITY[compiled_label], (
        f"spec resolving to {construction_key!r} compiles to label {compiled_label!r}, "
        f"which the joint table does not admit for it"
    )


def test_pulse_down_is_rejected_loudly() -> None:
    """Direction 5: module 04's tier-1 table compiles a downward pulse, module 05 registers pulse
    only as DEMAND_UP, and the derivation note lists pulse once. Module 02's registry has landed
    and agrees with module 05 (``sig_demand_pulse`` is ``demand_up``), so a pulse-down spec must
    keep failing here — loudly, so the shape cannot leak through as a level shift and so any
    later widening of the pairing registry has to come through this test."""
    spec = _spec_for("demand_pulse")
    pulse_down = ShockSpec(**{**spec.model_dump(), "direction": Direction.DEMAND_DOWN})
    with pytest.raises(ValueError, match="direction does not match"):
        resolve_spec(pulse_down)
