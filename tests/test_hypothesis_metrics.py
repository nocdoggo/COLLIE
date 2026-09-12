from __future__ import annotations

from collie.contracts import Direction, LifecycleState, ShockFamily, TargetStream
from collie.eval.hypothesis import HypothesisCase, macro_f1, score_hypotheses


def test_false_activation_distinct_from_wrong_family() -> None:
    metrics = score_hypotheses(
        [
            HypothesisCase(
                true_family=ShockFamily.NO_CHANGE,
                predicted_family=ShockFamily.DEMAND_LEVEL,
                activated=True,
            ),
            HypothesisCase(
                true_family=ShockFamily.SHIPMENT_LOSS,
                predicted_family=ShockFamily.DEMAND_LEVEL,
                activated=True,
            ),
        ]
    )
    assert metrics.false_activation == 1
    assert metrics.wrong_family_activation == 1
    assert metrics.wrong_spec_exposure == 2


def test_activation_delay_and_benefit_given_activation() -> None:
    metrics = score_hypotheses(
        [
            HypothesisCase(
                true_family=ShockFamily.DEMAND_LEVEL,
                predicted_family=ShockFamily.DEMAND_LEVEL,
                activated=True,
                proposal_period=4,
                activation_period=7,
                benefited_after_activation=True,
                lifecycle_state=LifecycleState.ACTIVE,
            )
        ]
    )
    assert metrics.activation_delay == 3
    assert metrics.benefit_given_activation == 1.0


def test_per_field_macro_f1_scores_shockspec_fields() -> None:
    metrics = score_hypotheses(
        [
            HypothesisCase(
                true_family=ShockFamily.DEMAND_LEVEL,
                predicted_family=ShockFamily.DEMAND_LEVEL,
                true_target_stream=TargetStream.DEMAND,
                predicted_target_stream=TargetStream.DEMAND,
                true_direction=Direction.DEMAND_UP,
                predicted_direction=Direction.DEMAND_UP,
                activated=True,
            ),
            HypothesisCase(
                true_family=ShockFamily.SHIPMENT_LOSS,
                predicted_family=ShockFamily.SHIPMENT_LOSS,
                true_target_stream=TargetStream.ARRIVAL,
                predicted_target_stream=TargetStream.DEMAND,
                true_direction=Direction.ARRIVAL_INTERRUPTED,
                predicted_direction=Direction.DEMAND_UP,
                activated=True,
            ),
        ]
    )
    assert metrics.field_macro_f1["shock_family"] == 1.0
    assert metrics.field_macro_f1["target_stream"] < 1.0
    assert metrics.exact_match == 0.5


def test_macro_f1_uses_equality_for_tuple_labels() -> None:
    true_window = tuple([3, 5])
    predicted_window = tuple([3, 5])
    assert true_window == predicted_window
    assert true_window is not predicted_window
    assert macro_f1([true_window], [predicted_window]) == 1.0


def test_wrong_spec_exposure_counts_correct_family_wrong_field() -> None:
    metrics = score_hypotheses(
        [
            HypothesisCase(
                true_family=ShockFamily.DEMAND_LEVEL,
                predicted_family=ShockFamily.DEMAND_LEVEL,
                true_target_stream=TargetStream.DEMAND,
                predicted_target_stream=TargetStream.ARRIVAL,
                activated=True,
            )
        ]
    )
    assert metrics.wrong_family_activation == 0
    assert metrics.wrong_spec_exposure == 1
