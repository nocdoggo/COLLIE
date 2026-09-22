"""Payload validation and trusted provenance injection for ShockSpec."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator, model_validator

from collie.contracts import (
    Direction,
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.spec.registry import (
    FAMILY_SIGNATURE,
    FAMILY_TARGET_STREAM,
    ONSET_WINDOWS,
    expected_direction,
)

__all__ = ["ShockSpecPayload", "inject_provenance", "validate_payload"]


class ShockSpecPayload(BaseModel):
    """The nine fields a model may supply, excluding trusted provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    target_stream: TargetStream
    shock_family: ShockFamily
    direction: Direction
    onset_window: tuple[StrictInt, StrictInt] | None
    magnitude_bin: MagnitudeBin | None
    persistence: Persistence
    duration_bin: DurationBin
    evidence_refs: tuple[str, ...]
    prospective_signature: str

    @model_validator(mode="before")
    @classmethod
    def _contract_abstention_spelling(cls, data: Any) -> Any:
        # Reuse the frozen contract's canonicalizer, including its onset spelling,
        # before stricter payload types run. Do not duplicate the normalization rules.
        return ShockSpec._normalise_abstention_spelling(data)

    @field_validator("onset_window")
    @classmethod
    def _onset_window_is_registered(cls, value: tuple[int, int] | None) -> tuple[int, int] | None:
        if value is not None and value not in ONSET_WINDOWS:
            raise ValueError(f"onset_window must be one of {ONSET_WINDOWS}, got {value}")
        return value

    @model_validator(mode="after")
    def _registered_cross_field_rules(self) -> ShockSpecPayload:
        signatures = FAMILY_SIGNATURE[self.shock_family]
        if self.prospective_signature not in signatures:
            raise ValueError(
                "prospective_signature is not registered for "
                f"{self.shock_family.value}: {self.prospective_signature!r}"
            )

        expected_stream = FAMILY_TARGET_STREAM[self.shock_family]
        if self.target_stream is not expected_stream:
            raise ValueError(
                f"{self.shock_family.value} requires target_stream={expected_stream.value!r}"
            )

        direction = expected_direction(self.shock_family, self.prospective_signature)
        if self.direction is not direction:
            raise ValueError(
                f"{self.shock_family.value}/{self.prospective_signature} "
                f"requires direction={direction.value!r}"
            )

        # Delegate universal abstention/nullity rules to the frozen contract
        # instead of maintaining a second, drift-prone copy in this module.
        ShockSpec(
            **self.model_dump(),
            tau_j=0,
            proposal_index=1,
            model_id="payload-validation",
            decoding_hash="payload-validation",
            prompt_hash="payload-validation",
        )
        return self


def validate_payload(data: Mapping[str, Any]) -> ShockSpecPayload:
    """Validate untrusted model data before trusted fields are attached."""
    return ShockSpecPayload.model_validate(data)


def validate_proposal_context(*, tau_j: int, generation_period: int, proposal_index: int) -> None:
    """Caller errors must fail before transport, not become model-format failures."""
    for name, value in (
        ("tau_j", tau_j),
        ("generation_period", generation_period),
        ("proposal_index", proposal_index),
    ):
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
    if proposal_index < 1:
        raise ValueError("proposal_index is 1-based")
    if tau_j < generation_period:
        raise ValueError(
            f"tau_j={tau_j} cannot be earlier than generation_period={generation_period}"
        )


def inject_provenance(
    payload: ShockSpecPayload | Mapping[str, Any],
    *,
    tau_j: int,
    generation_period: int,
    proposal_index: int,
    model_id: str,
    decoding_hash: str,
    prompt_hash: str,
) -> ShockSpec:
    """Attach system-owned provenance and return the frozen shared contract."""
    validated = payload if isinstance(payload, ShockSpecPayload) else validate_payload(payload)
    validate_proposal_context(
        tau_j=tau_j, generation_period=generation_period, proposal_index=proposal_index
    )
    return ShockSpec(
        **validated.model_dump(),
        tau_j=tau_j,
        proposal_index=proposal_index,
        model_id=model_id,
        decoding_hash=decoding_hash,
        prompt_hash=prompt_hash,
    )
