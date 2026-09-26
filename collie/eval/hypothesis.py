"""Hypothesis, activation, and lifecycle metrics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from collie.contracts import (
    Direction,
    DurationBin,
    LifecycleState,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    TargetStream,
)

__all__ = [
    "HypothesisCase",
    "HypothesisMetrics",
    "field_macro_f1",
    "macro_f1",
    "score_hypotheses",
]


@dataclass(frozen=True, slots=True)
class HypothesisCase:
    true_family: ShockFamily
    predicted_family: ShockFamily
    activated: bool
    true_target_stream: TargetStream | None = None
    predicted_target_stream: TargetStream | None = None
    true_direction: Direction | None = None
    predicted_direction: Direction | None = None
    true_onset_window: tuple[int, int] | None = None
    predicted_onset_window: tuple[int, int] | None = None
    true_magnitude_bin: MagnitudeBin | None = None
    predicted_magnitude_bin: MagnitudeBin | None = None
    true_persistence: Persistence | None = None
    predicted_persistence: Persistence | None = None
    true_duration_bin: DurationBin | None = None
    predicted_duration_bin: DurationBin | None = None
    activation_period: int | None = None
    proposal_period: int | None = None
    rollback_period: int | None = None
    expiration_period: int | None = None
    lifecycle_state: LifecycleState | None = None
    magnitude_covered: bool | None = None
    benefited_after_activation: bool | None = None


@dataclass(frozen=True, slots=True)
class HypothesisMetrics:
    macro_f1: float
    field_macro_f1: dict[str, float]
    exact_match: float
    abstention_precision: float | None
    abstention_recall: float | None
    magnitude_coverage: float | None
    activation_delay: float | None
    rollback_delay: float | None
    expiration_accuracy: float | None
    false_activation: int
    wrong_family_activation: int
    wrong_spec_exposure: int
    benefit_given_activation: float | None


def macro_f1(y_true: Sequence[object], y_pred: Sequence[object]) -> float:
    labels = sorted(set(y_true) | set(y_pred), key=str)
    if not labels:
        raise ValueError("cannot compute macro-F1 over no labels")
    scores: list[float] = []
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred, strict=True))
        denom = 2 * tp + fp + fn
        scores.append(0.0 if denom == 0 else (2 * tp) / denom)
    return sum(scores) / len(scores)


FIELD_PAIRS = {
    "shock_family": ("true_family", "predicted_family"),
    "target_stream": ("true_target_stream", "predicted_target_stream"),
    "direction": ("true_direction", "predicted_direction"),
    "onset_window": ("true_onset_window", "predicted_onset_window"),
    "magnitude_bin": ("true_magnitude_bin", "predicted_magnitude_bin"),
    "persistence": ("true_persistence", "predicted_persistence"),
    "duration_bin": ("true_duration_bin", "predicted_duration_bin"),
}


def field_macro_f1(cases: Sequence[HypothesisCase]) -> dict[str, float]:
    """Macro-F1 per ShockSpec field, skipping fields not present in the records yet."""
    scores: dict[str, float] = {}
    for field, (true_attr, pred_attr) in FIELD_PAIRS.items():
        pairs = [
            (getattr(case, true_attr), getattr(case, pred_attr))
            for case in cases
            if getattr(case, true_attr) is not None or getattr(case, pred_attr) is not None
        ]
        if not pairs:
            continue
        y_true = [true for true, _ in pairs]
        y_pred = [pred for _, pred in pairs]
        scores[field] = macro_f1(y_true, y_pred)
    return scores


def _case_exact_match(case: HypothesisCase) -> bool:
    for true_attr, pred_attr in FIELD_PAIRS.values():
        true_value = getattr(case, true_attr)
        pred_value = getattr(case, pred_attr)
        if true_value is None and pred_value is None:
            continue
        if true_value != pred_value:
            return False
    return True


def _rate(values: Iterable[bool]) -> float | None:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _mean(values: Iterable[int | float | None]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def score_hypotheses(cases: Sequence[HypothesisCase]) -> HypothesisMetrics:
    if not cases:
        raise ValueError("cannot score no hypothesis cases")
    y_true = [c.true_family for c in cases]
    y_pred = [c.predicted_family for c in cases]
    per_field = field_macro_f1(cases)
    exact = sum(_case_exact_match(case) for case in cases) / len(cases)

    pred_abstain = [c.predicted_family is ShockFamily.NO_CHANGE for c in cases]
    true_abstain = [c.true_family is ShockFamily.NO_CHANGE for c in cases]
    abstain_tp = sum(p and t for p, t in zip(pred_abstain, true_abstain, strict=True))
    abstain_pred = sum(pred_abstain)
    abstain_true = sum(true_abstain)

    false_activation = sum(c.activated and c.true_family is ShockFamily.NO_CHANGE for c in cases)
    wrong_family_activation = sum(
        c.activated
        and c.true_family is not ShockFamily.NO_CHANGE
        and c.predicted_family != c.true_family
        for c in cases
    )
    wrong_spec_exposure = sum(c.activated and not _case_exact_match(c) for c in cases)
    return HypothesisMetrics(
        macro_f1=macro_f1(y_true, y_pred),
        field_macro_f1=per_field,
        exact_match=exact,
        abstention_precision=None if abstain_pred == 0 else abstain_tp / abstain_pred,
        abstention_recall=None if abstain_true == 0 else abstain_tp / abstain_true,
        magnitude_coverage=_rate(
            c.magnitude_covered for c in cases if c.magnitude_covered is not None
        ),
        activation_delay=_mean(
            None
            if c.activation_period is None or c.proposal_period is None
            else c.activation_period - c.proposal_period
            for c in cases
        ),
        rollback_delay=_mean(
            None
            if c.rollback_period is None or c.activation_period is None
            else c.rollback_period - c.activation_period
            for c in cases
        ),
        expiration_accuracy=_rate(
            c.lifecycle_state is LifecycleState.EXPIRED
            for c in cases
            if c.expiration_period is not None
        ),
        false_activation=false_activation,
        wrong_family_activation=wrong_family_activation,
        wrong_spec_exposure=wrong_spec_exposure,
        benefit_given_activation=_rate(
            c.benefited_after_activation
            for c in cases
            if c.activated and c.benefited_after_activation is not None
        ),
    )
