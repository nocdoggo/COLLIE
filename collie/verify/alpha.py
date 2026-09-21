"""Episode-local alpha spending for adaptively timed ShockSpec proposals.

The proposal index is deliberately one-based.  With the geometric schedule below, starting at
zero would spend the entire episode budget on the first proposal and invalidate the union-bound
argument as soon as a second proposal were allowed.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DEFAULT_MAX_PROPOSALS",
    "AlphaAllocation",
    "alpha_for_proposal",
    "alpha_schedule",
]


DEFAULT_MAX_PROPOSALS = 2
"""The registered sprint design permits at most two proposals in one episode."""


@dataclass(frozen=True, slots=True)
class AlphaAllocation:
    """One proposal's share of the episode-level false-activation budget."""

    alpha_episode: float
    proposal_index: int
    max_proposals: int
    alpha_j: float

    @property
    def threshold(self) -> float:
        """The e-process crossing threshold from Ville's inequality."""
        return 1.0 / self.alpha_j


def _validate(alpha_episode: float, max_proposals: int) -> None:
    if not 0.0 < alpha_episode < 1.0:
        raise ValueError(f"alpha_episode must lie in (0, 1), got {alpha_episode}")
    if max_proposals < 1:
        raise ValueError(f"max_proposals must be positive, got {max_proposals}")


def alpha_schedule(
    alpha_episode: float, *, max_proposals: int = DEFAULT_MAX_PROPOSALS
) -> tuple[AlphaAllocation, ...]:
    """Return the complete preregistered schedule and assert that it fits the budget."""
    _validate(alpha_episode, max_proposals)
    allocations = tuple(
        AlphaAllocation(
            alpha_episode=alpha_episode,
            proposal_index=j,
            max_proposals=max_proposals,
            alpha_j=alpha_episode * 2.0**-j,
        )
        for j in range(1, max_proposals + 1)
    )
    spent = sum(item.alpha_j for item in allocations)
    if spent > alpha_episode:
        raise AssertionError(
            f"proposal schedule spends {spent} but the episode budget is {alpha_episode}"
        )
    return allocations


def alpha_for_proposal(
    alpha_episode: float,
    proposal_index: int,
    *,
    max_proposals: int = DEFAULT_MAX_PROPOSALS,
) -> AlphaAllocation:
    """Allocate ``alpha_episode * 2**-proposal_index`` to one legal proposal."""
    schedule = alpha_schedule(alpha_episode, max_proposals=max_proposals)
    if proposal_index < 1:
        raise ValueError(f"proposal_index is one-based, got {proposal_index}")
    if proposal_index > max_proposals:
        raise ValueError(
            f"proposal_index {proposal_index} exceeds the registered cap {max_proposals}"
        )
    return schedule[proposal_index - 1]
