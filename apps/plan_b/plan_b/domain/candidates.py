"""Finite candidate generation from the configured edit templates.

Generation order is fixed: ``keep`` (no edits) first, then every single non-keep edit in
template configuration order, then combinations of 2..``max_combined_edits`` single edits in
lexicographic generation order. A combination is dropped when two edits change the timing of
the same activity (a swap changes both of its activities), two edits substitute the same
(activity, resource), or a substitute and an alternate format, or two alternate formats, touch
the same activity. Identical single edits configured twice are generated once, so signatures
and identifiers stay unique within an evaluation.

Applying a candidate starts from the active plan: timing edits first, then resource edits.
Every activity of the active plan appears in the result, unchanged ones copied as they are.
"""

from __future__ import annotations

import re
from datetime import timedelta
from itertools import combinations

from plan_b.domain.digest import canonical_json, sha256_hex
from plan_b.domain.models import (
    AlternateFormatTemplate,
    Assignment,
    Edit,
    KeepTemplate,
    PlanningConfig,
    ShiftTemplate,
    SubstituteTemplate,
    SwapTemplate,
)

KEEP_LABEL = "Keep the current plan"
TIMING_KINDS = frozenset({"swap", "shift"})
RESOURCE_KINDS = frozenset({"substitute", "alternate_format"})

_EVALUATION_ID = re.compile(r"^eval_(\d+)$")

Template = (
    KeepTemplate | SwapTemplate | ShiftTemplate | SubstituteTemplate | AlternateFormatTemplate
)


def readable(activity_id: str) -> str:
    """Activity id as it reads in labels (``skills_exchange`` -> ``skills exchange``)."""
    return activity_id.replace("_", " ")


def enabled_templates(
    planning: PlanningConfig, requested: tuple[str, ...] | None
) -> tuple[str, ...]:
    """Template kinds used by an evaluation, in configuration order. ``keep`` is always first."""
    names: list[str] = ["keep"]
    for template in planning.edit_templates:
        name = template.template
        if name in names:
            continue
        if requested is None or name in requested:
            names.append(name)
    return tuple(names)


def template_edits(template: Template) -> tuple[Edit, ...]:
    """The single edits one configured template expands to."""
    if isinstance(template, SwapTemplate):
        return (Edit(kind="swap", activity_ids=template.activity_ids),)
    if isinstance(template, ShiftTemplate):
        return tuple(
            Edit(kind="shift", activity_ids=(template.activity_id,), offset_minutes=offset)
            for offset in template.offsets_minutes
        )
    if isinstance(template, SubstituteTemplate):
        return tuple(
            Edit(
                kind="substitute",
                activity_ids=(template.activity_id,),
                resource_id=template.resource_id,
                substitute_id=substitute,
            )
            for substitute in template.substitute_ids
        )
    if isinstance(template, AlternateFormatTemplate):
        return (
            Edit(
                kind="alternate_format",
                activity_ids=(template.activity_id,),
                format_id=template.format_id,
            ),
        )
    return ()


def _edit_key(edit: Edit) -> str:
    return canonical_json(edit.model_dump(mode="json"))


def single_edits(planning: PlanningConfig, enabled: tuple[str, ...]) -> tuple[Edit, ...]:
    """Every non-keep single edit of the enabled templates, in configuration order."""
    edits: list[Edit] = []
    seen: set[str] = set()
    for template in planning.edit_templates:
        if template.template == "keep" or template.template not in enabled:
            continue
        for edit in template_edits(template):
            key = _edit_key(edit)
            if key not in seen:
                seen.add(key)
                edits.append(edit)
    return tuple(edits)


def timing_activities(edit: Edit) -> frozenset[str]:
    """Activities whose start or end an edit changes before resource edits apply."""
    if edit.kind in TIMING_KINDS:
        return frozenset(edit.activity_ids)
    return frozenset()


def compatible(edits: tuple[Edit, ...]) -> bool:
    """Whether the edits may be combined under the documented combination rules."""
    timed: set[str] = set()
    substituted: set[tuple[str, str]] = set()
    substitute_activities: set[str] = set()
    format_activities: set[str] = set()
    for edit in edits:
        timing = timing_activities(edit)
        if timing & timed:
            return False
        timed |= timing
        if edit.kind == "substitute":
            activity = edit.activity_ids[0]
            key = (activity, edit.resource_id or "")
            if key in substituted or activity in format_activities:
                return False
            substituted.add(key)
            substitute_activities.add(activity)
        elif edit.kind == "alternate_format":
            activity = edit.activity_ids[0]
            if activity in substitute_activities or activity in format_activities:
                return False
            format_activities.add(activity)
    return True


def generate_edit_lists(
    planning: PlanningConfig, enabled: tuple[str, ...]
) -> tuple[tuple[Edit, ...], ...]:
    """The full candidate menu in generation order (before the candidate cap)."""
    singles = single_edits(planning, enabled)
    menu: list[tuple[Edit, ...]] = [()]
    menu.extend((edit,) for edit in singles)
    for size in range(2, planning.max_combined_edits + 1):
        for combo in combinations(singles, size):
            if compatible(combo):
                menu.append(combo)
    return tuple(menu)


def find_format(
    planning: PlanningConfig, activity_id: str, format_id: str | None
) -> AlternateFormatTemplate | None:
    for template in planning.edit_templates:
        if (
            isinstance(template, AlternateFormatTemplate)
            and template.activity_id == activity_id
            and template.format_id == format_id
        ):
            return template
    return None


def _moved(assignment: Assignment, start_delta: timedelta) -> Assignment:
    return Assignment(
        activity_id=assignment.activity_id,
        start=assignment.start + start_delta,
        end=assignment.end + start_delta,
        resource_ids=assignment.resource_ids,
    )


def _swap(current: dict[str, Assignment], edit: Edit) -> None:
    first_id, second_id = edit.activity_ids[0], edit.activity_ids[1]
    first, second = current.get(first_id), current.get(second_id)
    if first is None or second is None:
        return
    earlier, later = (first, second) if first.start <= second.start else (second, first)
    later_length = later.end - later.start
    earlier_length = earlier.end - earlier.start
    later_start = earlier.start
    earlier_start = later_start + later_length
    current[later.activity_id] = Assignment(
        activity_id=later.activity_id,
        start=later_start,
        end=later_start + later_length,
        resource_ids=later.resource_ids,
    )
    current[earlier.activity_id] = Assignment(
        activity_id=earlier.activity_id,
        start=earlier_start,
        end=earlier_start + earlier_length,
        resource_ids=earlier.resource_ids,
    )


def _substitute(current: dict[str, Assignment], edit: Edit) -> None:
    activity_id = edit.activity_ids[0]
    assignment = current.get(activity_id)
    if assignment is None or edit.resource_id not in assignment.resource_ids:
        return
    replaced: list[str] = []
    for rid in assignment.resource_ids:
        new_id = edit.substitute_id if rid == edit.resource_id and edit.substitute_id else rid
        if new_id not in replaced:
            replaced.append(new_id)
    current[activity_id] = assignment.model_copy(update={"resource_ids": tuple(replaced)})


def _alternate_format(current: dict[str, Assignment], edit: Edit, planning: PlanningConfig) -> None:
    activity_id = edit.activity_ids[0]
    assignment = current.get(activity_id)
    fmt = find_format(planning, activity_id, edit.format_id)
    if assignment is None or fmt is None:
        return
    current[activity_id] = Assignment(
        activity_id=activity_id,
        start=assignment.start,
        end=assignment.start + timedelta(minutes=fmt.duration_minutes),
        resource_ids=fmt.required_resources,
    )


def apply_edits(
    base: tuple[Assignment, ...], edits: tuple[Edit, ...], planning: PlanningConfig
) -> tuple[Assignment, ...]:
    """Assignments of a candidate: the active plan with timing then resource edits applied.

    An edit whose subject is not in the active plan (an unassigned activity, or a substituted
    resource the activity does not use) changes nothing here; the constraint checks report it.
    """
    current = {a.activity_id: a for a in base}
    for edit in edits:
        if edit.kind == "swap":
            _swap(current, edit)
        elif edit.kind == "shift" and edit.offset_minutes is not None:
            assignment = current.get(edit.activity_ids[0])
            if assignment is not None:
                current[assignment.activity_id] = _moved(
                    assignment, timedelta(minutes=edit.offset_minutes)
                )
    for edit in edits:
        if edit.kind == "substitute":
            _substitute(current, edit)
        elif edit.kind == "alternate_format":
            _alternate_format(current, edit, planning)
    return tuple(current[a.activity_id] for a in base)


def edit_label(edit: Edit, planning: PlanningConfig) -> str:
    if edit.kind == "swap":
        first, second = edit.activity_ids[0], edit.activity_ids[1]
        return f"Swap {readable(first)} and {readable(second)}"
    if edit.kind == "shift":
        return f"Shift {readable(edit.activity_ids[0])} by {edit.offset_minutes or 0:+d} min"
    if edit.kind == "substitute":
        return (
            f"Use {edit.substitute_id} instead of {edit.resource_id} "
            f"for {readable(edit.activity_ids[0])}"
        )
    if edit.kind == "alternate_format":
        activity_id = edit.activity_ids[0]
        fmt = find_format(planning, activity_id, edit.format_id)
        name = fmt.label if fmt is not None else edit.format_id
        return f"Use the {name} format for {readable(activity_id)}"
    return KEEP_LABEL


def candidate_label(edits: tuple[Edit, ...], planning: PlanningConfig) -> str:
    if not edits:
        return KEEP_LABEL
    return " + ".join(edit_label(edit, planning) for edit in edits)


def edits_signature(edits: tuple[Edit, ...]) -> str:
    """``sha256(canonical_json([edit.model_dump(mode="json"), ...]))``; keep signs ``[]``."""
    return sha256_hex(canonical_json([edit.model_dump(mode="json") for edit in edits]))


def candidate_ids(evaluation_id: str, signature: str) -> tuple[str, str]:
    """``(cand_NNNN_<sig8>, rpt_NNNN_<sig8>)`` for evaluation ``eval_NNNN``."""
    match = _EVALUATION_ID.match(evaluation_id)
    if match is None:
        raise ValueError(f"evaluation id {evaluation_id!r} is not of the form eval_NNNN")
    number = match.group(1)
    return f"cand_{number}_{signature[:8]}", f"rpt_{number}_{signature[:8]}"


def describe_template(template: Template) -> str:
    if isinstance(template, SwapTemplate):
        return f"swap({template.activity_ids[0]}, {template.activity_ids[1]})"
    if isinstance(template, ShiftTemplate):
        offsets = ", ".join(f"{offset:+d}" for offset in template.offsets_minutes)
        return f"shift({template.activity_id}: {offsets} min)"
    if isinstance(template, SubstituteTemplate):
        substitutes = ", ".join(template.substitute_ids)
        return f"substitute({template.activity_id}: {template.resource_id} -> {substitutes})"
    if isinstance(template, AlternateFormatTemplate):
        return f"alternate_format({template.activity_id}: {template.format_id})"
    return "keep"


def describe_action_space(
    planning: PlanningConfig,
    enabled: tuple[str, ...],
    *,
    generated: int,
    evaluated: int,
    truncated: bool,
) -> str:
    """One-line statement of the declared action space an evaluation searched."""
    parts = ["keep"]
    for template in planning.edit_templates:
        if template.template != "keep" and template.template in enabled:
            parts.append(describe_template(template))
    cap_note = ", truncated" if truncated else ""
    return (
        f"Templates {'; '.join(parts)}; at most {planning.max_combined_edits} combined edits; "
        f"{generated} candidates generated, {evaluated} evaluated "
        f"(cap {planning.candidate_cap}{cap_note})"
    )
