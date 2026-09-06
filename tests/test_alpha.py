"""Module 05 CP1 acceptance tests for episode-local alpha spending."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from collie.verify.alpha import alpha_for_proposal, alpha_schedule


@given(
    alpha_episode=st.floats(min_value=1e-8, max_value=0.5, allow_nan=False),
    max_proposals=st.integers(min_value=1, max_value=100),
)
def test_alpha_budget_never_exceeds_one(alpha_episode: float, max_proposals: int) -> None:
    schedule = alpha_schedule(alpha_episode, max_proposals=max_proposals)
    assert sum(item.alpha_j for item in schedule) <= alpha_episode


def test_alpha_is_one_based() -> None:
    allocation = alpha_for_proposal(0.05, 1)
    assert allocation.alpha_j == pytest.approx(0.025)
    assert allocation.threshold == pytest.approx(40.0)
    with pytest.raises(ValueError, match="one-based"):
        alpha_for_proposal(0.05, 0)


def test_proposal_after_registered_cap_is_rejected() -> None:
    with pytest.raises(ValueError, match="exceeds the registered cap"):
        alpha_for_proposal(0.05, 3)


@pytest.mark.parametrize("bad_alpha", [0.0, 1.0, -0.1, 1.1])
def test_episode_alpha_must_be_a_probability(bad_alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha_episode"):
        alpha_schedule(bad_alpha)
