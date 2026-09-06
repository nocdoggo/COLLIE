"""Frozen construction metadata selected by compiler ``predictive_model`` keys.

This registry contains no fitted parameters and no hidden incident data.  Module 02 validates the
family/signature pair selected by the model; module 04 emits the predictive-model key; this module
turns that registered key into one verifier construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from collie.contracts import ShockFamily, TargetStream

__all__ = ["CONSTRUCTIONS", "Construction", "resolve_construction", "resolve_spec_shape"]


@dataclass(frozen=True, slots=True)
class Construction:
    predictive_model: str
    family: ShockFamily
    signature: str
    stream: TargetStream
    construction: str
    validity: str


_REGISTERED = (
    Construction(
        "demand_level_up",
        ShockFamily.DEMAND_LEVEL,
        "sig_demand_level_up",
        TargetStream.DEMAND,
        "discrete_mixture_lr",
        "anytime_valid",
    ),
    Construction(
        "demand_level_down",
        ShockFamily.DEMAND_LEVEL,
        "sig_demand_level_down",
        TargetStream.DEMAND,
        "discrete_mixture_lr",
        "anytime_valid",
    ),
    Construction(
        "demand_pulse",
        ShockFamily.TEMPORARY_PULSE,
        "sig_demand_pulse",
        TargetStream.DEMAND,
        "bounded_duration_mixture_lr",
        "anytime_valid_low_power",
    ),
    Construction(
        "arrival_delay",
        ShockFamily.LEAD_TIME_SHIFT,
        "sig_arrival_delay",
        TargetStream.ARRIVAL,
        "finite_state_forward",
        "collie_shockspec_only",
    ),
    Construction(
        "arrival_loss",
        ShockFamily.SHIPMENT_LOSS,
        "sig_arrival_loss",
        TargetStream.ARRIVAL,
        "finite_state_forward_absorbing_loss",
        "collie_shockspec_only",
    ),
    Construction(
        "arrival_stall",
        ShockFamily.TRANSIT_PAUSE,
        "sig_arrival_stall",
        TargetStream.ARRIVAL,
        "finite_state_forward_frozen_counters",
        "collie_shockspec_only",
    ),
    Construction(
        "compound_split",
        ShockFamily.COMPOUND,
        "sig_compound",
        TargetStream.BOTH,
        "separate_eprocesses_alpha_split",
        "anytime_valid_via_splitting",
    ),
)

CONSTRUCTIONS: dict[str, Construction] = {item.predictive_model: item for item in _REGISTERED}
_BY_SPEC_SHAPE = {(item.family, item.signature): item for item in _REGISTERED}

if len(CONSTRUCTIONS) != len(_REGISTERED):  # pragma: no cover - import-time registry guard
    raise AssertionError("duplicate predictive_model key in verifier construction registry")
if len(_BY_SPEC_SHAPE) != len(_REGISTERED):  # pragma: no cover - import-time registry guard
    raise AssertionError("one family/signature pair resolves to multiple verifier constructions")


def resolve_construction(predictive_model: str) -> Construction:
    """Resolve the exact key emitted by the deterministic compiler."""
    try:
        return CONSTRUCTIONS[predictive_model]
    except KeyError as exc:
        raise KeyError(f"unregistered predictive_model {predictive_model!r}") from exc


def resolve_spec_shape(family: ShockFamily, signature: str) -> Construction:
    """Resolve the schema-selected family/signature pair without reading hidden truth."""
    try:
        return _BY_SPEC_SHAPE[(family, signature)]
    except KeyError as exc:
        raise KeyError(f"no verifier construction for {(family, signature)!r}") from exc
