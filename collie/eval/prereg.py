"""Load and validate the Gate 2 preregistration.

The registration is a method artefact, not just configuration.  This module keeps the shape
checkable before the final owner-supplied thresholds are frozen, and gives the renderer one
authoritative place to ask which analyses may be labelled confirmatory.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_PREREG_PATH",
    "Preregistration",
    "load_preregistration",
    "primary_stratum_weights",
    "registered_confirmatory_ids",
    "render_preregistration_summary",
    "validate_preregistration",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREREG_PATH = REPO_ROOT / "prereg" / "prereg_v1.yaml"

REQUIRED_SECTIONS = (
    "metadata",
    "primary_endpoints",
    "stratum_weights",
    "confirmatory_contrasts",
    "holm_family",
    "alpha_allocation",
    "trigger_thresholds",
    "controller_grid",
    "compiler_mapping_table",
    "schema_thresholds",
    "oracle_mappings",
    "trust_region",
    "power_rule",
    "pilot_policy",
    "go_criteria",
    "kill_thresholds",
    "kill_triggers",
)


@dataclass(frozen=True, slots=True)
class Preregistration:
    """Parsed preregistration with convenience accessors used by the evaluator."""

    path: Path
    data: Mapping[str, Any]

    @property
    def analysis_ids(self) -> frozenset[str]:
        return frozenset(registered_confirmatory_ids(self.data))

    @property
    def is_draft(self) -> bool:
        return bool(self.data.get("metadata", {}).get("draft", False))


def _walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            yield from _walk_strings(key)
            yield from _walk_strings(value)
    elif isinstance(obj, Iterable) and not isinstance(obj, bytes):
        for value in obj:
            yield from _walk_strings(value)


def _contains_placeholder(obj: Any) -> bool:
    placeholders = ("TODO", "TBD", "OWNER_VALUE_REQUIRED", "PLACEHOLDER")
    return any(any(marker in value for marker in placeholders) for value in _walk_strings(obj))


def _members(section: Any) -> list[Mapping[str, Any]]:
    if not isinstance(section, list):
        raise ValueError("holm_family.members must be a list")
    members: list[Mapping[str, Any]] = []
    for item in section:
        if not isinstance(item, Mapping):
            raise ValueError("each Holm family member must be a mapping")
        members.append(item)
    return members


def registered_confirmatory_ids(data: Mapping[str, Any]) -> set[str]:
    """Return the identifiers allowed to travel as confirmatory results."""
    family = data.get("holm_family", {})
    if not isinstance(family, Mapping):
        return set()
    return {str(member["id"]) for member in _members(family.get("members", [])) if "id" in member}


def primary_stratum_weights(data: Mapping[str, Any]) -> dict[tuple[str, str], float]:
    """Cartesian family x information-condition weights for headline shocked episodes."""
    weights = data["stratum_weights"]
    family = weights["family"]
    condition = weights["information_condition"]
    return {
        (str(family_name), str(condition_name)): float(family_weight) * float(condition_weight)
        for family_name, family_weight in family.items()
        for condition_name, condition_weight in condition.items()
    }


def render_preregistration_summary(prereg: Preregistration | Mapping[str, Any]) -> str:
    """Render the Gate 2 commitment summary auditors read before method freeze."""
    data = prereg.data if isinstance(prereg, Preregistration) else prereg
    lines = ["Preregistration summary:", "  Confirmatory contrasts:"]
    for contrast in data["confirmatory_contrasts"]:
        lines.append(f"    {contrast['id']}: {contrast['treatment']} vs {contrast['control']}")
    lines.append("  Holm family:")
    for member in data["holm_family"]["members"]:
        lines.append(f"    {member['id']}: {member['contrast']} / {member['endpoint']}")
    lines.append("  Kill thresholds:")
    for key, value in data["kill_thresholds"].items():
        lines.append(f"    {key}: {value}")
    return "\n".join(lines)


def _sum_weights(weights: Mapping[str, Any], name: str) -> None:
    total = 0.0
    for key, value in weights.items():
        if not isinstance(value, int | float):
            raise ValueError(f"{name}.{key} is not numeric")
        total += float(value)
    if abs(total - 1.0) > 1e-12:
        raise ValueError(f"{name} weights sum to {total}, not 1")


def validate_preregistration(data: Mapping[str, Any], *, require_final: bool = True) -> None:
    """Validate the registration shape and, optionally, final-freeze readiness."""
    missing = [section for section in REQUIRED_SECTIONS if section not in data]
    if missing:
        raise ValueError(f"preregistration missing required sections: {missing}")

    if require_final and data.get("metadata", {}).get("draft", False):
        raise ValueError("preregistration is still marked metadata.draft=true")
    if require_final and _contains_placeholder(data):
        raise ValueError("preregistration contains a placeholder value")

    endpoints = data["primary_endpoints"]
    if endpoints != ["cumulative_undiscounted_profit", "total_lost_sales_units"]:
        raise ValueError("primary_endpoints must name profit and lost-sales units in order")

    weights = data["stratum_weights"]
    if not isinstance(weights, Mapping):
        raise ValueError("stratum_weights must be a mapping")
    for name in ("family", "information_condition", "null_controls"):
        section = weights.get(name)
        if not isinstance(section, Mapping):
            raise ValueError(f"stratum_weights.{name} must be a mapping")
        _sum_weights(section, f"stratum_weights.{name}")

    contrasts = data["confirmatory_contrasts"]
    if not isinstance(contrasts, list) or len(contrasts) != 3:
        raise ValueError("confirmatory_contrasts must contain exactly three contrasts")

    members = _members(data["holm_family"].get("members", []))
    if len(members) != 6:
        raise ValueError("Holm family must contain exactly six endpoint-by-contrast tests")
    seen = {(m.get("contrast"), m.get("endpoint")) for m in members}
    expected = {(c["id"], e) for c in contrasts for e in endpoints}
    if seen != expected:
        raise ValueError(f"Holm family mismatch: expected {expected}, got {seen}")

    kill_thresholds = data["kill_thresholds"]
    if not isinstance(kill_thresholds, Mapping) or len(kill_thresholds) != 7:
        raise ValueError("kill_thresholds must contain exactly seven entries")
    non_numeric = [
        key for key, value in kill_thresholds.items() if not isinstance(value, int | float)
    ]
    if require_final and non_numeric:
        raise ValueError(f"kill thresholds must be numeric: {non_numeric}")

    pilot_policy = data["pilot_policy"]
    if not isinstance(pilot_policy, Mapping):
        raise ValueError("pilot_policy must be a mapping")
    expected_policy = {
        "independent_units": 120,
        "call_budget_per_episode": 4,
        "episode_horizon": 50,
        "never_recovered_value": 51,
        "formal_go_uses_confidence_bound": True,
    }
    mismatches = {
        key: (pilot_policy.get(key), expected)
        for key, expected in expected_policy.items()
        if pilot_policy.get(key) != expected
    }
    if mismatches:
        raise ValueError(
            f"pilot_policy does not match registered implementation limits: {mismatches}"
        )

    kill_triggers = data["kill_triggers"]
    if not isinstance(kill_triggers, list) or len(kill_triggers) != 8:
        raise ValueError("kill_triggers must contain exactly eight entries")


def load_preregistration(
    path: Path | None = None, *, require_final: bool = True
) -> Preregistration:
    target = path or DEFAULT_PREREG_PATH
    import yaml

    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"{target} did not parse to a mapping")
    validate_preregistration(data, require_final=require_final)
    return Preregistration(path=target, data=data)
