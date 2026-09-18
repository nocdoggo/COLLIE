"""Two-rater provenance audit: rubric scoring, agreement, and unconditional leakage pruning.

Five criteria, each scored 1-5 by both raters over all 180 base templates plus a stratified
sample of instantiated renderings. Leakage is not negotiable by consensus: one below-threshold
``no_leakage`` score from either rater removes the base template. Low agreement shrinks the
bank to 120 (8 per family-split cell) and requires a dated prereg deviation, because template
count enters the language-level uncertainty calculation.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from collie.data.alerts.bank import AlertTemplate, render_alert

CRITERIA = (
    "operational_plausibility",
    "label_consistency",
    "contemporaneous_knowledge",
    "no_leakage",
    "realistic_uncertainty",
)

SHEET_COLUMNS = (
    "sample_id",
    "template_id",
    "split",
    "family",
    "kind",
    "rater",
    "criterion",
    "score",
    "text",
)


def default_audit_config() -> dict:
    """Registered audit defaults. Returns a fresh copy; callers mutate freely."""
    return {
        "raters": ["P3", "P4"],
        "status": "pending_team_confirmation",
        "length_tolerance": 0,
        "unreliable_offset": -1,
        "render_sample_size": 24,
        "render_seed": 20260908,
        "leakage_threshold": 4,
        "kappa_threshold": 0.6,
        "fallback_bank_size": 120,
        "fallback_cell_floor": 4,
    }


@dataclass(frozen=True, slots=True)
class Rating:
    """One rater's 1-5 score for one criterion on one sample."""

    sample_id: str
    rater: str
    criterion: str
    score: int

    def __post_init__(self) -> None:
        if not self.sample_id.strip() or not self.rater.strip():
            raise ValueError("rating needs a sample id and a rater")
        if self.criterion not in CRITERIA:
            raise ValueError(f"unknown criterion: {self.criterion!r}")
        if type(self.score) is not int or not 1 <= self.score <= 5:
            raise ValueError(f"score must be an integer from 1 to 5, got {self.score!r}")


def review_samples(
    bank: Sequence[AlertTemplate],
    selected: Sequence[AlertTemplate],
    seed: int,
) -> dict[str, tuple[AlertTemplate, str]]:
    """The scored population: every base template plus rendered draws of the stratified sample.

    Keys are ``base:<template_id>`` and ``render:<template_id>``; values are
    ``(template, visible_text)``. A rendered sample's leakage failure removes its base template,
    so the value always carries the base template, never the rendering wrapper.
    """
    by_id: dict[str, AlertTemplate] = {}
    for template in bank:
        if template.template_id in by_id:
            raise ValueError(f"duplicate template id in bank: {template.template_id}")
        by_id[template.template_id] = template
    if not by_id:
        raise ValueError("empty bank")
    samples: dict[str, tuple[AlertTemplate, str]] = {
        f"base:{t.template_id}": (t, t.text) for t in bank
    }
    seen: set[str] = set()
    for template in selected:
        if template.template_id not in by_id:
            raise ValueError(f"review sample not in bank: {template.template_id}")
        if template.template_id in seen:
            raise ValueError(f"duplicate review sample: {template.template_id}")
        seen.add(template.template_id)
        samples[f"render:{template.template_id}"] = (template, render_alert(template, seed).text)
    return samples


def cohen_kappa(a: Sequence[int], b: Sequence[int]) -> float | None:
    """Per-criterion Cohen's kappa. ``None`` when chance agreement is 1 (both raters constant):
    agreement is then perfect but unprovable, which must not report as κ = 1."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two equal, non-empty score sequences")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    categories = set(a) | set(b)
    expected = sum(a.count(c) / n * (b.count(c) / n) for c in categories)
    if expected == 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def audit_ratings(
    samples: Mapping[str, tuple[AlertTemplate, str]],
    ratings: Sequence[Rating],
    config: dict,
) -> dict:
    """Validate completeness, score agreement, prune leakage, and apply the 120-bank fallback."""
    raters = list(config["raters"])
    if len(raters) != 2 or len(set(raters)) != 2:
        raise ValueError("the audit requires exactly two distinct raters")
    expected = {
        (sample_id, rater, criterion)
        for sample_id in samples
        for rater in raters
        for criterion in CRITERIA
    }
    seen: set[tuple[str, str, str]] = set()
    for rating in ratings:
        key = (rating.sample_id, rating.rater, rating.criterion)
        if rating.sample_id not in samples:
            raise ValueError(f"rating for unknown sample: {rating.sample_id!r}")
        if rating.rater not in raters:
            raise ValueError(f"rating from unregistered rater: {rating.rater!r}")
        if key in seen:
            raise ValueError(f"duplicate rating: {key}")
        seen.add(key)
    missing = expected - seen
    if missing:
        raise ValueError(f"missing {len(missing)} ratings")

    by_cell = {(r.sample_id, r.rater, r.criterion): r.score for r in ratings}
    order = list(samples)
    kappa = {
        criterion: cohen_kappa(
            [by_cell[(s, raters[0], criterion)] for s in order],
            [by_cell[(s, raters[1], criterion)] for s in order],
        )
        for criterion in CRITERIA
    }
    undefined_kappa = any(value is None for value in kappa.values())

    threshold = config["leakage_threshold"]
    removals: list[dict] = []
    removed_ids: set[str] = set()
    for sample_id in order:
        template = samples[sample_id][0]
        for rater in raters:
            score = by_cell[(sample_id, rater, "no_leakage")]
            if score < threshold:
                removed_ids.add(template.template_id)
                removals.append(
                    {
                        "template_id": template.template_id,
                        "sample_id": sample_id,
                        "rater": rater,
                        "score": score,
                        "criterion": "no_leakage",
                        "reason": f"no_leakage {score} below registered threshold {threshold}",
                    }
                )

    base_templates = list(_bank_templates(samples))
    disagreement = {
        t.template_id: sum(
            abs(
                by_cell[(f"base:{t.template_id}", raters[0], c)]
                - by_cell[(f"base:{t.template_id}", raters[1], c)]
            )
            for c in CRITERIA
        )
        for t in base_templates
    }
    adjudication_log = [
        {
            "sample_id": sample_id,
            "criterion": criterion,
            "scores": (
                by_cell[(sample_id, raters[0], criterion)],
                by_cell[(sample_id, raters[1], criterion)],
            ),
        }
        for sample_id in order
        for criterion in CRITERIA
        if by_cell[(sample_id, raters[0], criterion)] != by_cell[(sample_id, raters[1], criterion)]
    ]

    fallback_required = any(
        value is not None and value < config["kappa_threshold"] for value in kappa.values()
    )
    fallback_removed: set[str] = set()
    if fallback_required:
        # The registered fallback is 120 templates (R4.6); its "8 per cell" parenthetical is
        # arithmetic-inconsistent with 18 cells (8 x 18 = 144), so the 120 total governs.
        # Remove the most-disagreed templates globally, never dropping a family-split cell
        # below its accurate count, so every cell stays represented in the shrunken bank.
        to_remove = len(base_templates) - config["fallback_bank_size"]
        floor = config["fallback_cell_floor"]
        cell_counts = Counter(
            (t.family.value, t.split.value)
            for t in base_templates
            if t.template_id not in removed_ids
        )
        worst_first = sorted(
            (t for t in base_templates if t.template_id not in removed_ids),
            key=lambda t: (disagreement[t.template_id], t.template_id),
            reverse=True,
        )
        for template in worst_first:
            if len(fallback_removed) >= to_remove:
                break
            cell = (template.family.value, template.split.value)
            if cell_counts[cell] <= floor:
                continue
            cell_counts[cell] -= 1
            fallback_removed.add(template.template_id)

    retained = sorted(
        t.template_id for t in base_templates if t.template_id not in removed_ids | fallback_removed
    )
    clean = not removals and not fallback_required and not undefined_kappa
    return {
        "kappa": kappa,
        "undefined_kappa": undefined_kappa,
        "removals": removals,
        "retained_template_ids": retained,
        "fallback_required": fallback_required,
        "dated_deviation_required": fallback_required,
        "fallback_removed_template_ids": sorted(fallback_removed),
        "adjudication_log": adjudication_log,
        "status": "ready" if clean and config.get("status") == "confirmed" else "needs_review",
    }


def _bank_templates(samples: Mapping[str, tuple[AlertTemplate, str]]) -> tuple[AlertTemplate, ...]:
    return tuple(value[0] for key, value in samples.items() if key.startswith("base:"))


def rating_sheet_rows(
    samples: Mapping[str, tuple[AlertTemplate, str]],
    raters: Sequence[str],
):
    """One empty-scored row per (sample, rater, criterion), in a stable order."""
    for sample_id, (template, text) in samples.items():
        for rater in raters:
            for criterion in CRITERIA:
                yield {
                    "sample_id": sample_id,
                    "template_id": template.template_id,
                    "split": template.split.value,
                    "family": template.family.value,
                    "kind": template.kind.value,
                    "rater": rater,
                    "criterion": criterion,
                    "score": "",
                    "text": text,
                }


def write_rating_sheet(
    path: Path,
    samples: Mapping[str, tuple[AlertTemplate, str]],
    raters: Sequence[str],
) -> None:
    """Write an empty scoring sheet. Refuses to overwrite: an existing sheet holds scores."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"rating sheet already exists: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SHEET_COLUMNS))
        writer.writeheader()
        writer.writerows(rating_sheet_rows(samples, raters))


def read_ratings(
    path: Path, samples: Mapping[str, tuple[AlertTemplate, str]]
) -> tuple[Rating, ...]:
    """Read a scoring sheet. A row whose text differs from the current sample is stale: the
    stimulus changed after scoring, so the score is void rather than inherited."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if rows and tuple(rows[0]) != SHEET_COLUMNS:
        raise ValueError(f"rating sheet columns must be {list(SHEET_COLUMNS)}")
    ratings = []
    for row in rows:
        sample_id = row["sample_id"]
        if sample_id not in samples:
            raise ValueError(f"rating sheet names unknown sample: {sample_id!r}")
        if row["text"] != samples[sample_id][1]:
            raise ValueError(f"stale rating sheet: {sample_id} text changed since scoring")
        if row["score"] == "":
            continue
        try:
            score = int(row["score"])
        except ValueError:
            raise ValueError(
                f"score must be an integer from 1 to 5, got {row['score']!r}"
            ) from None
        ratings.append(Rating(sample_id, row["rater"], row["criterion"], score))
    return tuple(ratings)
