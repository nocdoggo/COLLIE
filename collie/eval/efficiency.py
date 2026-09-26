"""Call ledger summaries and realised-budget Pareto frontiers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from collie.contracts import CallLog, EpisodeResult, ParseOutcome

__all__ = [
    "EfficiencySummary",
    "FrontierPoint",
    "auc_over_call_fraction",
    "call_logs",
    "efficiency_summary",
    "frontier_from_results",
    "pareto_frontier",
]


@dataclass(frozen=True, slots=True)
class EfficiencySummary:
    arm: str
    attempted_calls: int
    repair_calls: int
    rejected_calls: int
    input_tokens: int
    output_tokens: int
    latency_p50_ms: float
    latency_p95_ms: float
    usd_cost: float
    actions_per_accepted_call: float | None


@dataclass(frozen=True, slots=True)
class FrontierPoint:
    arm: str
    reward: float
    budget: float


def call_logs(results: Sequence[EpisodeResult]) -> tuple[CallLog, ...]:
    return tuple(log for result in results for log in result.calls)


def efficiency_summary(results: Sequence[EpisodeResult]) -> tuple[EfficiencySummary, ...]:
    by_arm: dict[str, list[EpisodeResult]] = {}
    for result in results:
        by_arm.setdefault(result.arm_id, []).append(result)

    summaries: list[EfficiencySummary] = []
    for arm, group in sorted(by_arm.items()):
        logs = [log for result in group for log in result.calls]
        accepted = [
            log
            for log in logs
            if log.outcome in (ParseOutcome.ACCEPTED, ParseOutcome.ACCEPTED_AFTER_REPAIR)
        ]
        n_actions = sum(len(result.records) for result in group)
        latencies = [log.latency_ms for log in logs]
        summaries.append(
            EfficiencySummary(
                arm=arm,
                attempted_calls=len(logs),
                repair_calls=sum(
                    log.attempt_index > 1 or log.outcome is ParseOutcome.ACCEPTED_AFTER_REPAIR
                    for log in logs
                ),
                rejected_calls=sum(log.outcome is ParseOutcome.FALLBACK for log in logs),
                input_tokens=sum(log.input_tokens for log in logs),
                output_tokens=sum(log.output_tokens for log in logs),
                latency_p50_ms=float(np.percentile(latencies, 50)) if latencies else 0.0,
                latency_p95_ms=float(np.percentile(latencies, 95)) if latencies else 0.0,
                usd_cost=sum(log.usd_cost for log in logs),
                actions_per_accepted_call=None if not accepted else n_actions / len(accepted),
            )
        )
    return tuple(summaries)


def pareto_frontier(
    points: Sequence[FrontierPoint], *, higher_reward_better: bool = True
) -> tuple[FrontierPoint, ...]:
    """Keep non-dominated points using realised budgets."""
    ordered = sorted(
        points, key=lambda p: (p.budget, -p.reward if higher_reward_better else p.reward)
    )
    frontier: list[FrontierPoint] = []
    best: float | None = None
    for point in ordered:
        reward = point.reward if higher_reward_better else -point.reward
        if best is None or reward > best:
            frontier.append(point)
            best = reward
    return tuple(frontier)


def auc_over_call_fraction(points: Sequence[FrontierPoint]) -> float:
    """AUC on [0,1] after normalising realised call budgets."""
    if not points:
        raise ValueError("cannot compute AUC over no frontier points")
    max_budget = max(point.budget for point in points)
    if max_budget <= 0:
        return max(point.reward for point in points)
    ordered = sorted((point.budget / max_budget, point.reward) for point in points)
    if ordered[0][0] > 0:
        ordered.insert(0, (0.0, ordered[0][1]))
    # The largest max-normalised budget is exactly 1.0 by construction, so the append below
    # can never fire.
    if ordered[-1][0] < 1:  # pragma: no cover
        ordered.append((1.0, ordered[-1][1]))
    xs = np.asarray([p[0] for p in ordered], dtype=float)
    ys = np.asarray([p[1] for p in ordered], dtype=float)
    return float(np.trapezoid(ys, xs))


def frontier_from_results(
    results: Sequence[EpisodeResult], budget: Callable[[Sequence[EpisodeResult]], float]
) -> tuple[FrontierPoint, ...]:
    by_arm: dict[str, list[EpisodeResult]] = {}
    for result in results:
        by_arm.setdefault(result.arm_id, []).append(result)
    return tuple(
        FrontierPoint(
            arm=arm,
            reward=float(np.mean([r.total_profit for r in group])),
            budget=float(budget(group)),
        )
        for arm, group in sorted(by_arm.items())
    )
