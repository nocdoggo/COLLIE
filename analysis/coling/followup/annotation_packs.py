"""Legacy in-memory pack mechanics, retained for invented-data tests only.

No new human annotation is planned. These mechanics do not enforce the current
evidence gate, return raw input IDs for N/C and use predictable role aliases;
they are not a private or approved interface for constructing real packs.
Existing human annotations are not changed or accessed here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable

from .references import FirstPass
from .role_materials import PilotNotice, RoleSeed, validate_structure
from .sampling import SampleDraw


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rater(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"A[1-9][0-9]*", value) is None:
        raise ValueError("annotation packs use anonymous A codes")


@dataclass(frozen=True, slots=True)
class ShownNotice:
    item_id: str
    update_date: str
    notice_text: str
    group_id: str | None = None


@dataclass(frozen=True, slots=True)
class AnnotationPack:
    rater_code: str
    cohort: str
    stage: str
    notices: tuple[ShownNotice, ...]
    condition_block: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RolePack:
    """The transferable view is separate from its private variant mapping."""

    view: AnnotationPack
    private_identity_map: tuple[tuple[str, str], ...]


def _pack(rater: str, cohort: str, stage: str, notices: Iterable[ShownNotice], block: str = "") -> AnnotationPack:
    _rater(rater)
    notices = tuple(notices)
    if len({notice.item_id for notice in notices}) != len(notices):
        raise ValueError("shown item IDs must be unique")
    notices = tuple(sorted(notices, key=lambda item: (
        _hash(f"20261011|annotation-group-order-v1|{cohort}|{stage}|{rater}|{item.group_id or item.item_id}"),
        _hash(f"20261011|annotation-item-order-v1|{cohort}|{stage}|{rater}|{item.item_id}"), item.item_id,
    )))
    content = {"rater_code": rater, "cohort": cohort, "stage": stage,
               "notices": [asdict(item) for item in notices], "condition_block": block}
    digest = _hash(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return AnnotationPack(rater, cohort, stage, notices, block, digest)


def natural_pack(draw: SampleDraw, *, rater: str) -> AnnotationPack:
    if not isinstance(draw, SampleDraw) or draw.cohort != "N":
        raise ValueError("a natural sample draw is required")
    rows = (ShownNotice(item.event.statement_group_id, item.event.event_date, item.event.notice_text)
            for item in draw.selected)
    return _pack(rater, "N", "natural", rows)


def convention_first_pack(draw: SampleDraw, *, rater: str) -> AnnotationPack:
    if not isinstance(draw, SampleDraw) or draw.cohort != "C":
        raise ValueError("a convention sample draw is required")
    rows = (ShownNotice(item.event.statement_group_id, item.event.event_date, item.event.notice_text)
            for item in draw.selected)
    return _pack(rater, "C", "unspecified", rows)


def convention_specified_pack(
    draw: SampleDraw, *, rater: str, first_passes: Iterable[FirstPass],
    shown_utc: datetime, condition_block: str, block_sha256: str,
) -> AnnotationPack:
    """Show the convention only after both first-pass sheets are submitted."""
    if not isinstance(draw, SampleDraw) or draw.cohort != "C":
        raise ValueError("a convention sample draw is required")
    _rater(rater)
    if (not isinstance(shown_utc, datetime) or shown_utc.tzinfo is None
            or shown_utc.utcoffset() != timezone.utc.utcoffset(shown_utc)):
        raise ValueError("shown_utc must be a timezone-aware UTC datetime")
    if not isinstance(condition_block, str) or not condition_block or _hash(condition_block) != block_sha256:
        raise ValueError("the explicit convention block must match its recorded hash")
    passes = tuple(first_passes)
    expected = {item.event.statement_group_id for item in draw.selected}
    by_item = {item: [] for item in expected}
    judgment_ids = set()
    for first in passes:
        if not isinstance(first, FirstPass) or first.item_id not in by_item or first.stage != "unspecified":
            raise ValueError("first passes must be assigned unspecified-stage records")
        if first.judgment_id in judgment_ids or first.outputs_seen or first.sensitivity_seen:
            raise ValueError("first-pass identities must be unique and unexposed")
        judgment_ids.add(first.judgment_id)
        by_item[first.item_id].append(first)
    for item, found in by_item.items():
        if len(found) != 2 or len({entry.rater_code for entry in found}) != 2 or rater not in {entry.rater_code for entry in found}:
            raise ValueError("each item needs both independent first-pass submissions")
        if shown_utc <= max(entry.submitted_utc for entry in found):
            raise ValueError("the specified block must follow both submissions")
    rows = (ShownNotice(item.event.statement_group_id, item.event.event_date, item.event.notice_text)
            for item in draw.selected)
    return _pack(rater, "C", "specified", rows, condition_block)


def pilot_pack(notices: Iterable[PilotNotice], *, rater: str) -> AnnotationPack:
    notices = tuple(notices)
    if len(notices) != 12 or any(not isinstance(item, PilotNotice) for item in notices):
        raise ValueError("the excluded development pilot contains exactly 12 invented notices")
    return _pack(rater, "pilot", "practice",
                 (ShownNotice(item.item_id, item.update_date.isoformat(), item.notice_text) for item in notices))


def role_pack(seeds: Iterable[RoleSeed], *, rater: str) -> RolePack:
    seeds = tuple(seeds)
    if not seeds or any(not isinstance(seed, RoleSeed) for seed in seeds):
        raise ValueError("a nonempty set of fictional role seeds is required")
    if len({seed.seed_id for seed in seeds}) != len(seeds):
        raise ValueError("role seeds must be unique")
    view, identities = [], []
    for seed in seeds:
        validate_structure(seed)
        group_id = "G" + _hash("20261011|role-blind-group-v1|" + seed.seed_id)[:20]
        for variant in seed.variants:
            shown_id = "V" + _hash("20261011|role-blind-id-v1|" + variant.item_id)[:20]
            view.append(ShownNotice(shown_id, variant.update_date.isoformat(), variant.notice_text, group_id))
            identities.append((shown_id, variant.item_id))
    if len({shown_id for shown_id, _ in identities}) != len(identities):
        raise ValueError("blinded role IDs must be unique")
    return RolePack(_pack(rater, "R", "role_validation", view), tuple(sorted(identities)))
