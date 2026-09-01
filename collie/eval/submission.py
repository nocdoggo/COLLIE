"""Write and score a submission through the official harness.

A submission is the directory layout ``eval/evaluate_results.py`` expects::

    <submission>/
      results/<trajectory>/<lead_time>/<...>/results.csv   # period, order_quantity
      scores.json

Every reported number here comes from :func:`official_simulate_and_score`, i.e. from upstream's
own code rather than from our reimplementation of it. Task 4 proved the two agree exactly, so this
is not a hedge; it is what makes the figure we publish the same object as the figure on the
leaderboard.

The aggregation mirrors ``evaluate_results.py``: a batch score is the mean normalized reward over
its instances, and the overall score is the mean over **all** instances, not the mean of the batch
means. Those differ here because the batches are unequal (200 real vs 240 synthetic per lead-time
label), and taking the wrong one shifts the overall figure.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from collie.adapter.inventorybench import benchmark_root, official_simulate_and_score
from collie.contracts import Controller
from collie.data.instances import InstanceKey
from collie.sim.loader import LoadedInstance, load_instance
from collie.sim.runner import EpisodeRunner

__all__ = [
    "BatchScore",
    "InstanceScore",
    "SubmissionScores",
    "aggregate",
    "run_submission",
    "score_instance",
    "write_results_csv",
]

ControllerFactory = Callable[[LoadedInstance], Controller]


@dataclass(frozen=True, slots=True)
class InstanceScore:
    """One instance's official score, plus the identity needed to group it."""

    relpath: str
    batch: str
    item_id: str
    num_periods: int
    normalized_reward: float
    total_reward: float
    total_profit: float
    total_holding_cost: float
    units_sold: float
    units_ordered: float
    service_level: float
    perfect_foresight: float
    ending_inventory: float


@dataclass(frozen=True, slots=True)
class BatchScore:
    name: str
    num_instances: int
    score: float
    service_level_mean: float


@dataclass(frozen=True, slots=True)
class SubmissionScores:
    """Aggregate in the same shape as the official ``scores.json``."""

    overall_score: float
    total_instances: int
    batches: tuple[BatchScore, ...]
    instances: tuple[InstanceScore, ...] = field(repr=False, default=())

    def batch(self, name: str) -> BatchScore:
        for candidate in self.batches:
            if candidate.name == name:
                return candidate
        raise KeyError(f"no batch {name!r}; have {[b.name for b in self.batches]}")

    def to_json(self) -> dict[str, Any]:
        rewards = [s.normalized_reward for s in self.instances]
        return {
            "overall_score": self.overall_score,
            "total_instances": self.total_instances,
            "batches": {
                b.name: {
                    "num_instances": b.num_instances,
                    "score": b.score,
                    "service_level_mean": b.service_level_mean,
                }
                for b in self.batches
            },
            "overall_stats": {
                "mean": float(np.mean(rewards)),
                "median": float(np.median(rewards)),
                "std": float(np.std(rewards)),
                "min": float(np.min(rewards)),
                "max": float(np.max(rewards)),
            }
            if rewards
            else {},
        }


def write_results_csv(path: Path, order_rows: Sequence[tuple[int, int]]) -> None:
    """Write ``period, order_quantity`` exactly as the official runner does."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["period", "order_quantity"])
        writer.writerows(order_rows)


def score_instance(
    relpath: str,
    order_rows: Sequence[tuple[int, int]],
    *,
    root: Path | None = None,
) -> InstanceScore:
    """Score one instance's orders with the official evaluator."""
    base = root or benchmark_root()
    test_df = pd.read_csv(base / relpath / "test.csv")
    item_id = next(c[len("demand_") :] for c in test_df.columns if c.startswith("demand_"))
    results_df = pd.DataFrame(
        {
            "period": [period for period, _ in order_rows],
            "order_quantity": [quantity for _, quantity in order_rows],
        }
    )
    scores = official_simulate_and_score(results_df, test_df, item_id)
    parts = relpath.split("/")
    return InstanceScore(
        relpath=relpath,
        batch=f"{parts[0]}/{parts[1]}",
        item_id=item_id,
        num_periods=len(test_df),
        normalized_reward=float(scores["normalized_reward"]),
        total_reward=float(scores["total_reward"]),
        total_profit=float(scores["total_profit"]),
        total_holding_cost=float(scores["total_holding_cost"]),
        units_sold=float(scores["units_sold"]),
        units_ordered=float(scores["units_ordered"]),
        service_level=float(scores["service_level"]),
        perfect_foresight=float(scores["perfect_foresight"]),
        ending_inventory=float(scores["ending_inventory"]),
    )


def aggregate(instances: Sequence[InstanceScore]) -> SubmissionScores:
    """Aggregate per-instance scores the way the official evaluator does."""
    if not instances:
        raise ValueError("cannot aggregate an empty submission")
    by_batch: dict[str, list[InstanceScore]] = {}
    for score in instances:
        by_batch.setdefault(score.batch, []).append(score)
    batches = tuple(
        BatchScore(
            name=name,
            num_instances=len(group),
            score=float(np.mean([s.normalized_reward for s in group])),
            service_level_mean=float(np.mean([s.service_level for s in group])),
        )
        for name, group in sorted(by_batch.items())
    )
    return SubmissionScores(
        # Instance-weighted, not the mean of the batch means: the batches are unequal.
        overall_score=float(np.mean([s.normalized_reward for s in instances])),
        total_instances=len(instances),
        batches=batches,
        instances=tuple(instances),
    )


def run_submission(
    keys: Sequence[InstanceKey],
    controller_factory: ControllerFactory,
    *,
    out_dir: Path | None = None,
    root: Path | None = None,
    lost_orders_visible_in_transit: bool = False,
    order_cap: float = float("inf"),
    write_scores: bool = True,
) -> SubmissionScores:
    """Run a controller over ``keys``, optionally write a submission, and score it officially.

    ``lost_orders_visible_in_transit`` selects the harness semantics
    (``docs/env_contract.md`` §5 and §8.4). It defaults to the authoritative ``eval/`` behaviour;
    the published OR baseline needs ``True`` to be reproduced, and any figure carrying it must say
    so.
    """
    base = root or benchmark_root()
    scores: list[InstanceScore] = []

    for key in keys:
        instance = load_instance(
            base / key.relpath,
            episode_id=key.relpath,
            promised_lead_time=None,
            order_cap=order_cap,
        )
        runner = EpisodeRunner(
            instance=instance,
            lost_orders_visible_in_transit=lost_orders_visible_in_transit,
        )
        outcome = runner.run(controller_factory(instance))
        order_rows = outcome.order_rows()

        if out_dir is not None:
            write_results_csv(out_dir / "results" / key.relpath / "results.csv", order_rows)

        scores.append(score_instance(key.relpath, order_rows, root=base))

    aggregated = aggregate(scores)
    if out_dir is not None and write_scores:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "scores.json").write_text(
            json.dumps(aggregated.to_json(), indent=2) + "\n", encoding="utf-8"
        )
    return aggregated
