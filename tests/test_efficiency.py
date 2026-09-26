from __future__ import annotations

import pytest

from collie.contracts import CallLog, EpisodeResult, ParseOutcome
from collie.eval.efficiency import (
    FrontierPoint,
    auc_over_call_fraction,
    call_logs,
    efficiency_summary,
    pareto_frontier,
)


def result(arm: str, calls: tuple[CallLog, ...] = ()) -> EpisodeResult:
    return EpisodeResult(
        episode_id=f"e-{arm}",
        arm_id=arm,
        total_profit=10.0,
        total_holding_cost=0.0,
        total_reward=10.0,
        total_demand=10.0,
        total_sold=10.0,
        total_lost_sales=0.0,
        perfect_foresight=10.0,
        normalized_reward=1.0,
        calls=calls,
        independent_unit_id=f"u-{arm}",
    )


def log(arm: str, *, outcome: ParseOutcome, cost: float = 0.0, attempt_index: int = 1) -> CallLog:
    return CallLog(
        call_id=f"c-{arm}",
        arm_id=arm,
        episode_id=f"e-{arm}",
        period=1,
        model_id="fake",
        prompt_hash="p",
        decoding_hash="d",
        attempt_index=attempt_index,
        outcome=outcome,
        input_tokens=2,
        output_tokens=3,
        latency_ms=10.0,
        usd_cost=cost,
    )


def test_efficiency_counts_calls_and_tokens() -> None:
    summary = efficiency_summary((result("a", (log("a", outcome=ParseOutcome.ACCEPTED),)),))[0]
    assert summary.attempted_calls == 1
    assert summary.input_tokens == 2
    assert summary.output_tokens == 3


def test_repair_calls_do_not_double_count_a_repaired_attempt() -> None:
    summary = efficiency_summary(
        (result("a", (log("a", outcome=ParseOutcome.ACCEPTED_AFTER_REPAIR, attempt_index=2),)),)
    )[0]
    assert summary.repair_calls == 1


def test_pareto_uses_realised_budgets() -> None:
    frontier = pareto_frontier(
        [
            FrontierPoint("cheap", reward=10.0, budget=1.0),
            FrontierPoint("dominated", reward=9.0, budget=1.0),
            FrontierPoint("expensive", reward=12.0, budget=3.0),
        ]
    )
    assert [p.arm for p in frontier] == ["cheap", "expensive"]


def test_call_logs_flattens_every_episode_ledger() -> None:
    entries = (log("a", outcome=ParseOutcome.ACCEPTED), log("b", outcome=ParseOutcome.FALLBACK))
    results = (
        result("a", (entries[0],)),
        result("b", (entries[1],)),
    )
    assert call_logs(results) == entries


def test_auc_requires_at_least_one_frontier_point() -> None:
    with pytest.raises(ValueError, match="no frontier points"):
        auc_over_call_fraction(())


def test_auc_normalises_realised_call_budgets() -> None:
    points = (
        FrontierPoint("cheap", reward=10.0, budget=1.0),
        FrontierPoint("expensive", reward=14.0, budget=2.0),
    )
    assert auc_over_call_fraction(points) == pytest.approx(11.0)
