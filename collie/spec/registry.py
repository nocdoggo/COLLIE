"""Registered vocabularies for model-selectable ShockSpec fields.

The model selects keys from this module; it never supplies a statistical
construction. Keeping the vocabulary closed lets downstream modules derive
exactly one verifier and controller mapping from a validated spec.
"""

from __future__ import annotations

from collie.contracts import Direction, ShockFamily, TargetStream

__all__ = [
    "FAMILY_SIGNATURE",
    "FAMILY_TARGET_STREAM",
    "ONSET_WINDOWS",
    "SIGNATURES",
    "SIGNATURE_DIRECTION",
    "expected_direction",
    "legal_pairs",
]


ONSET_WINDOWS: tuple[tuple[int, int], ...] = ((-2, 0), (-1, 1), (0, 2), (-2, 2))

SIGNATURES: tuple[str, ...] = (
    "sig_demand_level_up",
    "sig_demand_level_down",
    "sig_demand_pulse",
    "sig_arrival_delay",
    "sig_arrival_loss",
    "sig_arrival_stall",
    "sig_compound",
)

FAMILY_SIGNATURE: dict[ShockFamily, frozenset[str]] = {
    # prospective_signature is required by the frozen wire contract. The
    # existing FakeLLM uses this registered value as an ignored placeholder for
    # an abstention; consumers must branch on spec.is_abstention first.
    ShockFamily.NO_CHANGE: frozenset({"sig_demand_level_up"}),
    ShockFamily.DEMAND_LEVEL: frozenset({"sig_demand_level_up", "sig_demand_level_down"}),
    ShockFamily.TEMPORARY_PULSE: frozenset({"sig_demand_pulse"}),
    ShockFamily.LEAD_TIME_SHIFT: frozenset({"sig_arrival_delay"}),
    ShockFamily.SHIPMENT_LOSS: frozenset({"sig_arrival_loss"}),
    ShockFamily.TRANSIT_PAUSE: frozenset({"sig_arrival_stall"}),
    ShockFamily.COMPOUND: frozenset({"sig_compound"}),
}

FAMILY_TARGET_STREAM: dict[ShockFamily, TargetStream] = {
    ShockFamily.NO_CHANGE: TargetStream.NONE,
    ShockFamily.DEMAND_LEVEL: TargetStream.DEMAND,
    ShockFamily.TEMPORARY_PULSE: TargetStream.DEMAND,
    ShockFamily.LEAD_TIME_SHIFT: TargetStream.ARRIVAL,
    ShockFamily.SHIPMENT_LOSS: TargetStream.ARRIVAL,
    ShockFamily.TRANSIT_PAUSE: TargetStream.ARRIVAL,
    ShockFamily.COMPOUND: TargetStream.BOTH,
}


SIGNATURE_DIRECTION: dict[str, Direction] = {
    "sig_demand_level_up": Direction.DEMAND_UP,
    "sig_demand_level_down": Direction.DEMAND_DOWN,
    "sig_demand_pulse": Direction.DEMAND_UP,
    "sig_arrival_delay": Direction.ARRIVAL_DELAYED,
    "sig_arrival_loss": Direction.ARRIVAL_INTERRUPTED,
    "sig_arrival_stall": Direction.ARRIVAL_INTERRUPTED,
    "sig_compound": Direction.MIXED,
}
"""Module 1's pulse is an increase; direction must agree with the selected test.

Otherwise a direction-driven compiler could act against the very alternative the
signature asks the verifier to test. Abstention's placeholder is never a demand claim.
"""


def expected_direction(family: ShockFamily, signature: str) -> Direction:
    """Resolve direction only for a registered family/signature pair."""
    if signature not in FAMILY_SIGNATURE[family]:
        raise ValueError(f"unregistered family/signature pair: {family}, {signature}")
    return Direction.NONE if family is ShockFamily.NO_CHANGE else SIGNATURE_DIRECTION[signature]


def legal_pairs() -> tuple[tuple[ShockFamily, str], ...]:
    """Return every registered family/signature pair in stable order."""
    return tuple(
        (family, signature)
        for family in ShockFamily
        for signature in SIGNATURES
        if signature in FAMILY_SIGNATURE[family]
    )


def _validate_registry() -> None:
    families = set(ShockFamily)
    if set(FAMILY_SIGNATURE) != families:
        missing = families - set(FAMILY_SIGNATURE)
        extra = set(FAMILY_SIGNATURE) - families
        raise RuntimeError(f"family/signature registry mismatch: missing={missing}, extra={extra}")
    if set(FAMILY_TARGET_STREAM) != families:
        raise RuntimeError("family/target-stream registry must cover every ShockFamily")
    if any(not signatures for signatures in FAMILY_SIGNATURE.values()):
        raise RuntimeError("every ShockFamily must have at least one legal signature")
    registered = set(SIGNATURES)
    if set(SIGNATURE_DIRECTION) != registered:
        raise RuntimeError("every signature must have exactly one registered direction")
    used = set().union(*FAMILY_SIGNATURE.values())
    if used != registered:
        raise RuntimeError(
            f"signature registry mismatch: orphaned={registered - used}, unknown={used - registered}"
        )
    if len(registered) != len(SIGNATURES):
        raise RuntimeError("SIGNATURES must not contain duplicates")


_validate_registry()


if __name__ == "__main__":
    print(f"legal family/signature pairs: {len(legal_pairs())}")
