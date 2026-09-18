"""Strict alert-bank loading, deterministic rendering and analysis-side validation.

Signature registry integration is explicit and pending Module 02.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from math import prod
from pathlib import Path
from string import Formatter
from typing import Any

import yaml

from collie.contracts import (
    AlertKind,
    Direction,
    DurationBin,
    HiddenAlertSpec,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    Split,
    TargetStream,
)


@dataclass(frozen=True, slots=True)
class AlertTemplate:
    """One authored template and its hidden canonical meaning."""

    template_id: str
    family: ShockFamily
    split: Split
    kind: AlertKind
    wording_family: str
    text: str
    slots: dict[str, tuple[str, ...]]
    alert_spec: HiddenAlertSpec


@dataclass(frozen=True, slots=True)
class RenderedAlert:
    """Rendered stimulus with analysis-only metadata."""

    template_id: str
    split: Split
    wording_family: str
    text: str
    alert_spec: HiddenAlertSpec


_REQUIRED_TEMPLATE_FIELDS = {
    "id",
    "family",
    "split",
    "kind",
    "wording_family",
    "text",
    "slots",
    "alert_spec",
}
_REQUIRED_ALERT_SPEC_FIELDS = {
    "family",
    "target_stream",
    "direction",
    "onset_window",
    "magnitude_bin",
    "persistence",
    "duration_bin",
    "prospective_signature",
    "kind",
}


def _require_fields(data: Any, required: set[str], *, where: str) -> None:
    # Reject missing and extra fields alike, so a typo in YAML is never silently ignored.
    if not isinstance(data, dict) or any(not isinstance(k, str) for k in data):
        raise ValueError(f"{where}: expected a mapping with string keys")
    missing = required - data.keys()
    extra = data.keys() - required
    if missing or extra:
        raise ValueError(f"{where}: missing fields {sorted(missing)}; extra fields {sorted(extra)}")


def _text(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: expected a non-empty string")
    return value


def _parse_alert_spec(raw: dict[str, Any]) -> HiddenAlertSpec:
    # Hidden labels use the frozen contracts enums; only universal constraints are checked here, and legal signature pairings are validated by a separately injected registry.
    _require_fields(raw, _REQUIRED_ALERT_SPEC_FIELDS, where="alert_spec")
    for key in _REQUIRED_ALERT_SPEC_FIELDS - {"onset_window", "magnitude_bin"}:
        _text(raw[key], where=f"alert_spec.{key}")
    onset = raw["onset_window"]
    if onset is not None:
        if (
            not isinstance(onset, list)
            or len(onset) != 2
            or any(type(v) is not int for v in onset)
            or onset[0] > onset[1]
        ):
            raise ValueError("onset_window must be null or two ordered integers")
        onset = tuple(onset)
    magnitude = raw["magnitude_bin"]
    if magnitude is not None:
        magnitude = MagnitudeBin(_text(magnitude, where="magnitude_bin"))
    spec = HiddenAlertSpec(
        family=ShockFamily(raw["family"]),
        target_stream=TargetStream(raw["target_stream"]),
        direction=Direction(raw["direction"]),
        onset_window=onset,
        magnitude_bin=magnitude,
        persistence=Persistence(raw["persistence"]),
        duration_bin=DurationBin(raw["duration_bin"]),
        prospective_signature=raw["prospective_signature"],
        kind=AlertKind(raw["kind"]),
    )
    # Mirror only the universal invariants in frozen ShockSpec.
    # YAML authors must use canonical null, rather than the LLM spelling "none".
    if spec.family is ShockFamily.NO_CHANGE:
        if (
            spec.target_stream is not TargetStream.NONE
            or spec.direction is not Direction.NONE
            or spec.onset_window is not None
            or spec.magnitude_bin is not None
        ):
            raise ValueError("no_change requires none stream/direction and null onset/magnitude")
    elif (
        spec.onset_window is None
        or spec.magnitude_bin in (None, MagnitudeBin.NONE)
        or spec.target_stream is TargetStream.NONE
    ):
        raise ValueError("a shock requires onset, non-none magnitude and target stream")
    return spec


def _placeholders(text: str) -> set[str]:
    # Allow only simple slot names; attribute access or format conversion exceed the scope of template substitution.
    names = set()
    for _, name, format_spec, conversion in Formatter().parse(text):
        if name is None:
            continue
        if not name.isidentifier() or format_spec or conversion:
            raise ValueError("placeholders must be simple names without conversion or format spec")
        names.add(name)
    return names


def _parse_template(raw: dict[str, Any]) -> AlertTemplate:
    # The outer family is for bank grouping; a distractor's hidden truth must be no_change, not a copy of the outer classification.
    _require_fields(raw, _REQUIRED_TEMPLATE_FIELDS, where="template")
    for key in _REQUIRED_TEMPLATE_FIELDS - {"slots", "alert_spec"}:
        _text(raw[key], where=key)
    split = Split(raw["split"])
    if split not in {Split.DEV, Split.CAL, Split.TEST}:
        raise ValueError("template split must be dev/cal/test")
    family = ShockFamily(raw["family"])
    if family is ShockFamily.NO_CHANGE:
        raise ValueError("outer family must be one of the six bank families")
    kind = AlertKind(raw["kind"])
    if kind is AlertKind.NEUTRAL:
        raise ValueError("neutral is a content control, not a base bank kind")
    slots_raw = raw["slots"]
    if not isinstance(slots_raw, dict):
        raise ValueError("template slots must be a mapping")
    slots = {}
    for name, values in slots_raw.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("slot names must be simple identifiers")
        if not isinstance(values, list) or not values:
            raise ValueError(f"slot {name!r} must contain at least one value")
        slots[name] = tuple(_text(v, where=f"slot {name}") for v in values)
        if len(set(slots[name])) != len(slots[name]):
            raise ValueError(f"slot {name!r} has duplicate candidate values")
    names = _placeholders(raw["text"])
    missing = names - slots.keys()
    if missing:
        raise ValueError(f"placeholders have no slot values: {sorted(missing)}")
    if slots.keys() - names:
        raise ValueError("unused slots are not allowed")
    spec = _parse_alert_spec(raw["alert_spec"])
    if spec.kind is not kind:
        raise ValueError("outer and hidden kind must match")
    expected = ShockFamily.NO_CHANGE if kind is AlertKind.DISTRACTOR else family
    if spec.family is not expected:
        raise ValueError(
            "hidden family must match outer family, except distractors require no_change"
        )
    return AlertTemplate(
        template_id=raw["id"],
        family=family,
        split=split,
        kind=kind,
        wording_family=raw["wording_family"],
        text=raw["text"],
        slots=slots,
        alert_spec=spec,
    )


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects overwritten mapping keys."""


def _unique_mapping(loader, node, deep=False):
    # Plain YAML loading overwrites duplicate keys; raise instead, so an earlier label is never silently replaced.
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ValueError("YAML mapping keys must be strings")
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _unique_mapping,
)


def load_template_file(path: str | Path) -> tuple[AlertTemplate, ...]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.load(handle, Loader=_UniqueKeyLoader)
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a YAML list of templates")
    templates = tuple(_parse_template(item) for item in raw)
    ids = [template.template_id for template in templates]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate template ids")
    return templates


def load_alert_bank(directory: str | Path) -> tuple[AlertTemplate, ...]:
    # IDs must be unique within and across files, so later RunRecord entries can trace back to one template.
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"bank directory does not exist: {directory}")
    paths = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    if not paths:
        raise ValueError("bank directory contains no YAML files")
    templates: list[AlertTemplate] = []
    for path in paths:
        templates.extend(load_template_file(path))
    ids = [template.template_id for template in templates]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate template ids across alert-bank files")
    return tuple(templates)


def draw_slots(template: AlertTemplate, seed: int) -> tuple[tuple[str, str], ...]:
    """Render stable choices for unchanged template content and integer seed."""
    # Fix the slot order and use SHA256, so Python's randomized hashing or dict insertion order cannot break cross-process reproduction.
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    chosen: dict[str, str] = {}
    for name in sorted(template.slots):
        values = template.slots[name]
        if not values:
            raise ValueError(f"slot {name!r} must contain at least one value")
        key = json.dumps(
            [template.template_id, seed, name],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(key).digest()
        index = int.from_bytes(digest, byteorder="big") % len(values)
        chosen[name] = values[index]
    return tuple(sorted(chosen.items()))


def render_alert(template: AlertTemplate, seed: int) -> RenderedAlert:
    # The return value still carries analysis-side labels; hand only the visible text to a policy or LLM, never the whole object.
    chosen = dict(draw_slots(template, seed))
    return RenderedAlert(
        template_id=template.template_id,
        split=template.split,
        wording_family=template.wording_family,
        text=template.text.format(**chosen),
        alert_spec=template.alert_spec,
    )


# First-stage explicit rules, not an exhaustive natural-language detector.
# Real incident values, benchmark names, article IDs and paths must be supplied.
_LEAKAGE_RULES = (
    (
        "exact_multiplier",
        re.compile(
            r"(?<!\w)(?:"
            r"\d+(?:\.\d+)?\s*%"
            r"|\d+(?:\.\d+)?\s*(?:x\b|×|times\b|percent\b)"
            r"|\d+\.\d+\b"
            r"|half\b"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        "latent_family",
        re.compile(
            r"\b(?:"
            r"demand[_\s-]+level"
            r"|temporary[_\s-]+pulse"
            r"|lead[_\s-]+time[_\s-]+shift"
            r"|shipment[_\s-]+loss"
            r"|transit[_\s-]+pause"
            r"|compound"
            r"|no[_\s-]+change"
            r"|level[_\s-]+shift"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exact_onset",
        re.compile(
            r"\b(?:period|week|day|step)\s*(?:#\s*)?\d+\b"
            r"|\bt\s*=\s*\d+\b",
            re.IGNORECASE,
        ),
    ),
    (
        "exact_duration",
        re.compile(
            r"\b(?:for|lasting|lasts|duration(?:\s+of)?)"
            r"\s+(?:exactly\s+)?"
            r"(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)"
            r"\s+(?:periods?|weeks?|days?|steps?)\b",
            re.IGNORECASE,
        ),
    ),
)


@lru_cache(maxsize=16)
def _literal_pattern(literals):
    if not literals:
        return None
    if any(not value.strip() for value in literals):
        raise ValueError("forbidden literals must not be empty")
    return re.compile(
        r"(?<!\w)(?:"
        + "|".join(re.escape(v) for v in sorted(literals, key=len, reverse=True))
        + r")(?!\w)",
        re.IGNORECASE,
    )


def scan_text_for_leakage(
    text: str,
    *,
    forbidden_literals: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return detected leakage in model-visible text, never hidden metadata."""
    findings: list[str] = []
    for label, pattern in _LEAKAGE_RULES:
        for match in pattern.finditer(text):
            findings.append(f"{label}: {match.group(0)!r}")
    pattern = _literal_pattern(forbidden_literals)
    if pattern:
        findings.extend(f"forbidden_literal: {m.group(0)!r}" for m in pattern.finditer(text))
    return tuple(findings)


def assert_no_text_leakage(
    text: str,
    *,
    forbidden_literals: tuple[str, ...] = (),
) -> None:
    """Raise ValueError when the text scanner detects leakage."""
    findings = scan_text_for_leakage(text, forbidden_literals=forbidden_literals)
    if findings:
        raise ValueError("alert text leakage: " + "; ".join(findings))


def all_rendered_texts(template: AlertTemplate, *, max_combinations: int = 100_000):
    """Enumerate all authored slot combinations; refuse rather than sample on overflow."""
    # Enumerate all slot combinations; refuse to run past the limit rather than sample and claim a complete leakage scan.
    names = sorted(template.slots)
    count = prod(len(template.slots[name]) for name in names)
    if type(max_combinations) is not int or max_combinations < 1:
        raise ValueError("max_combinations must be a positive integer")
    if count == 0 or count > max_combinations:
        raise ValueError(
            f"{template.template_id}: invalid or excessive slot combinations ({count})"
        )
    for values in product(*(template.slots[name] for name in names)):
        yield template.text.format(**dict(zip(names, values, strict=True)))


def validate_template_leakage(
    template: AlertTemplate,
    *,
    forbidden_literals: tuple[str, ...] = (),
    max_combinations: int = 100_000,
) -> None:
    """Scan every possible rendered text, including leaks spanning slot boundaries."""
    # Scan the fully assembled sentence, so leakage that forms only when two slots combine is detected.
    for text in all_rendered_texts(template, max_combinations=max_combinations):
        try:
            assert_no_text_leakage(text, forbidden_literals=forbidden_literals)
        except ValueError as exc:
            raise ValueError(f"{template.template_id}: {exc}") from exc


def validate_bank_composition(templates: tuple[AlertTemplate, ...]) -> None:
    """Require six non-no_change enum families, three splits, and 4/2/2/2 per cell."""
    # A correct total is not enough: every cell of the six families by three splits must satisfy 4/2/2/2.
    families = set(ShockFamily) - {ShockFamily.NO_CHANGE}
    splits = {Split.DEV, Split.CAL, Split.TEST}
    expected = Counter(
        {
            AlertKind.ACCURATE: 4,
            AlertKind.OVERSTATED: 2,
            AlertKind.AMBIGUOUS: 2,
            AlertKind.DISTRACTOR: 2,
        }
    )
    if len(templates) != 180:
        raise ValueError(f"expected 180 templates, got {len(templates)}")
    if len({t.template_id for t in templates}) != len(templates):
        raise ValueError("duplicate template ids")
    if any(t.family not in families or t.split not in splits for t in templates):
        raise ValueError("invalid bank family or split")
    for family in sorted(families):
        for split in sorted(splits):
            counts = Counter(t.kind for t in templates if t.family == family and t.split == split)
            if counts != expected:
                raise ValueError(f"{family}/{split}: expected 4/2/2/2, got {dict(counts)}")


def validate_wording_holdout(templates: tuple[AlertTemplate, ...]) -> None:
    """The document forbids test wording families in dev/cal; dev-cal sharing is allowed."""
    # Isolation applies to wording families, not just strings; test wording families must not appear in dev or cal.
    test = {t.wording_family for t in templates if t.split is Split.TEST}
    other = {t.wording_family for t in templates if t.split in {Split.DEV, Split.CAL}}
    overlap = test & other
    if overlap:
        raise ValueError(f"test wording families appear in dev/cal: {sorted(overlap)}")


def validate_no_repeated_renderings(
    templates: tuple[AlertTemplate, ...],
    *,
    max_combinations: int = 100_000,
) -> None:
    """Reject exact cross-template text collisions within each split, over all slots.

    Replaying the same template/seed is deliberately allowed. Finite slot pools
    cannot guarantee unique text for arbitrarily many seeds of the same template.
    """
    # Check text collisions between different templates within one split; reuse across independent experimental units is handled by the rollout check below.
    seen = {}
    for template in templates:
        for text in all_rendered_texts(template, max_combinations=max_combinations):
            key = (template.split, text)
            previous = seen.get(key)
            if previous is not None and previous != template.template_id:
                raise ValueError(f"repeated rendered text: {previous} / {template.template_id}")
            seen[key] = template.template_id


def validate_rollout_renderings(rows):
    """Rows are (independent_unit_id, RenderedAlert); paired replays may share text.

    Enforce uniqueness on the actual finite allocation, not on an unbounded seed space.
    """
    # Paired conditions of the same independent unit may share text; different units must not use this to pose as distinct stimuli.
    seen = {}
    for unit_id, rendered in rows:
        key = (rendered.split, rendered.text)
        if key in seen and seen[key] != unit_id:
            raise ValueError(f"repeated rollout text: {seen[key]} / {unit_id}")
        seen[key] = unit_id


def validate_registry(templates, *, onset_windows, family_signatures):
    """Inject Module 02's registry; absence is not silently treated as validation."""
    # Signature validation counts only with the real mappings injected by Module 02; placeholder signatures are not a formal registration result.
    for template in templates:
        spec = template.alert_spec
        if spec.onset_window is not None and spec.onset_window not in onset_windows:
            raise ValueError(f"{template.template_id}: unregistered onset window")
        if spec.prospective_signature not in family_signatures.get(spec.family, ()):
            raise ValueError(f"{template.template_id}: illegal family/signature pairing")


def scalar_literals(value):
    """Keep every non-null JSON value, including numbers and nested incident values."""
    if isinstance(value, dict):
        for child in value.values():
            yield from scalar_literals(child)
    elif isinstance(value, list):
        for child in value:
            yield from scalar_literals(child)
    elif value is not None:
        text = str(value).lower() if isinstance(value, bool) else str(value)
        if text.strip():
            yield text
        if isinstance(value, float) and value.is_integer():
            yield str(int(value))


def forbidden_from_metadata(benchmark_path, shock_path, incident_paths=()):
    """Use the audited manifest seam; never reach into the benchmark checkout."""
    # Read only the manifest and explicitly supplied sidecars; never touch the upstream benchmark directory or pass hidden values to the policy.
    benchmark = json.loads(Path(benchmark_path).read_text())
    shocks = json.loads(Path(shock_path).read_text())
    values = set()
    for row in benchmark["instances"]:
        for key in ("family", "article_id", "rel_path"):
            values.update(scalar_literals(row.get(key)))
    for row in shocks["rollouts"]:
        for key in (
            "instance",
            "twin",
            "shock_family",
            "seed",
            "onset",
            "magnitude",
            "duration",
            "supply_effect",
        ):
            values.update(scalar_literals(row.get(key)))
    for path in incident_paths:
        values.update(scalar_literals(json.loads(Path(path).read_text())))
    if not values:
        raise ValueError("empty leakage metadata")
    return tuple(sorted(values))
