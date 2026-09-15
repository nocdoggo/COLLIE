"""Branch D (P3). Closed ShockSpec schema, registry, prompt construction, parse/repair."""

from collie.spec.prompt import PromptBundle, build_prompt, build_repair_prompt
from collie.spec.registry import FAMILY_SIGNATURE, ONSET_WINDOWS, SIGNATURES
from collie.spec.schema import ShockSpecPayload, inject_provenance, validate_payload

__all__ = [
    "FAMILY_SIGNATURE",
    "ONSET_WINDOWS",
    "SIGNATURES",
    "PromptBundle",
    "ShockSpecPayload",
    "build_prompt",
    "build_repair_prompt",
    "inject_provenance",
    "validate_payload",
]
