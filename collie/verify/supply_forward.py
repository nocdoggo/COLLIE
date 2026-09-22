"""Compatibility name for derivation-note §10's supply-forward deliverable.

The checkpoint document and its auditor command name :mod:`collie.verify.arrival`; the derivation
note names ``supply_forward.py``.  The implementation has one source of truth and this module keeps
both documented import paths valid.
"""

from collie.verify.arrival import (
    ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY,
    LOST,
    ArrivalEProcess,
    ArrivalForwardFilter,
    ArrivalModel,
    ArrivalState,
    RegisteredArrivalLaw,
    ValidityFlag,
    advance_counter,
    brute_force_sequence_probability,
    family_validity_flags,
    run_arrival_null_calibration,
    transition_state,
)

__all__ = [
    "ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY",
    "LOST",
    "ArrivalEProcess",
    "ArrivalForwardFilter",
    "ArrivalModel",
    "ArrivalState",
    "RegisteredArrivalLaw",
    "ValidityFlag",
    "advance_counter",
    "brute_force_sequence_probability",
    "family_validity_flags",
    "run_arrival_null_calibration",
    "transition_state",
]
