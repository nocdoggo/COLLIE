"""Task 4 — differential accounting equivalence against the official pipeline.

The claim under test: **our runner and the official pipeline produce identical numbers**, to a
maximum absolute difference of exactly ``0.0``, on 216 official instances stratified across the
three lead-time labels and the three cost ratios.

Exact equality rather than a tolerance is the right bar here because the audit established that
every demand, profit, and holding-cost cell in all 1,320 instances is integer-valued, and orders
are integers after the benchmark's own ``max(0, int(q))``. Every product and sum in the accounting
is therefore exact in float64. A nonzero difference would mean a semantic disagreement, not
floating-point noise, so there is no tolerance to negotiate.

Three comparisons, each closing a different gap:

1. **Orders.** Our runner's orders vs :func:`official_simulate_instance` running the same policy
   through upstream's own loop. This is the test of the *observation* plumbing: the policy is fed
   ``on_hand``, ``in_transit_total``, ``previous_demand``, ``previous_order``, and
   ``previous_arrivals`` by two independent code paths, and a one-period slip in any of them
   changes the orders.
2. **Episode aggregates.** Our :class:`~collie.contracts.EpisodeResult` vs
   :func:`official_simulate_and_score` fed our orders. This is the test of the *accounting*, run
   through upstream's code rather than a description of it.
3. **Per-period series.** Our records vs :func:`reference_trace`, a literal transcription of the
   upstream loop, because upstream exposes aggregates only. The transcription is itself pinned to
   upstream by comparison 2's numbers, so it cannot silently drift.

Both sides call the same :func:`~collie.sim.reference_policies.reference_order`, so the policy
arithmetic is identical by construction and cannot mask a harness difference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from collie.adapter.inventorybench import (
    benchmark_root,
    official_detect_promised_lead_time,
    official_policy_base,
    official_simulate_and_score,
    official_simulate_instance,
)
from collie.contracts import Decision, PeriodObservation
from collie.sim.loader import load_instance
from collie.sim.reference_policies import ReferenceController, ReferenceParams, reference_order
from collie.sim.runner import EpisodeRunner
from tools.select_equivalence_set import load_selection

pytestmark = [pytest.mark.equivalence, pytest.mark.needs_benchmark, pytest.mark.slow]

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "reports" / "equivalence_report.md"
REFERENCE_KINDS = ("constant", "base_stock", "chase")

# Populated by the tests, consumed by the session-scoped reporter.
_OBSERVED: list[Diff] = []


@dataclass(frozen=True, slots=True)
class Diff:
    """One instance/kind comparison and the largest disagreement it found."""

    relpath: str
    kind: str
    horizon: int
    max_abs_diff: float
    first_divergent_period: int | None
    field: str | None


# ---------------------------------------------------------------------------
# the upstream-shaped policy and the literal loop transcription
# ---------------------------------------------------------------------------


def make_upstream_policy(params: ReferenceParams, **init_kwargs: Any) -> Any:
    """Build an upstream ``InventoryPolicy`` subclass that defers to :func:`reference_order`.

    Defined here rather than in ``collie/`` because it must subclass a submodule class, and the
    adapter is the only sanctioned place to touch the submodule.
    """
    base = official_policy_base()

    class _UpstreamReferencePolicy(base):  # type: ignore[misc, valid-type]
        def __init__(self, **kwargs: Any) -> None:
            self.params = params  # set first: the base __init__ calls self.reset()
            super().__init__(**kwargs)

        def get_order(
            self,
            period: int,
            current_date: str,
            on_hand_inventory: float,
            in_transit_total: float,
            previous_demand: float,
            previous_order: float,
            previous_arrivals: float,
            profit_per_unit: float,
            holding_cost_per_unit: float,
        ) -> float:
            return reference_order(
                self.params,
                period=period,
                on_hand=on_hand_inventory,
                in_transit=in_transit_total,
                prev_demand=previous_demand,
                prev_order=previous_order,
                prev_arrivals=previous_arrivals,
                promised_lead_time=self.promised_lead_time,
            )

    return _UpstreamReferencePolicy(**init_kwargs)


def _coerce_lead_time(raw: Any) -> float:
    """Upstream's own lead-time coercion, transcribed."""
    if isinstance(raw, str) and raw.lower() == "inf":
        return float("inf")
    if np.isinf(float(raw)):
        return float("inf")
    return float(int(raw))


def reference_trace(
    test_df: pd.DataFrame, item_id: str, orders: list[float]
) -> list[dict[str, float]]:
    """Literal transcription of the upstream loop, emitting the per-period series.

    Mirrors ``evaluate_results.simulate_and_score`` step for step. ``in_transit_start`` is read
    before the current order is scheduled, which is where the policy reads it in
    ``run_baseline_policy.simulate_instance``.
    """
    on_hand = 0.0
    in_transit: dict[float, float] = {}
    rows: list[dict[str, float]] = []

    for index in range(len(test_df)):
        period = index + 1
        test_row = test_df.iloc[index]
        order_quantity = float(orders[index])
        demand = float(test_row[f"demand_{item_id}"])
        profit_per_unit = float(test_row[f"profit_{item_id}"])
        holding_cost_per_unit = float(test_row[f"holding_cost_{item_id}"])
        lead_time = _coerce_lead_time(test_row[f"lead_time_{item_id}"])

        on_hand_start = on_hand
        in_transit_start = math.fsum(in_transit.values())

        # 1. decision phase: schedule the arrival unless the shipment is lost
        if not math.isinf(lead_time):
            arrival_period = period + lead_time
            in_transit[arrival_period] = in_transit.get(arrival_period, 0.0) + order_quantity

        # 2. arrival resolution
        arrivals = in_transit.pop(float(period), 0.0)
        on_hand += arrivals

        # 3. demand resolution
        units_sold = min(demand, on_hand)
        on_hand -= units_sold

        # 4. reward computation, on ENDING inventory
        rows.append(
            {
                "period": float(period),
                "on_hand_start": on_hand_start,
                "in_transit_start": in_transit_start,
                "order_quantity": order_quantity,
                "arrivals": arrivals,
                "demand": demand,
                "units_sold": units_sold,
                "on_hand_end": on_hand,
                "period_profit": profit_per_unit * units_sold,
                "period_holding": holding_cost_per_unit * on_hand,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

_DF_CACHE: dict[str, tuple[pd.DataFrame, pd.DataFrame, str]] = {}


def _load_official(relpath: str) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if relpath not in _DF_CACHE:
        instance_dir = benchmark_root() / relpath
        train_df = pd.read_csv(instance_dir / "train.csv")
        test_df = pd.read_csv(instance_dir / "test.csv")
        item_id = next(c[len("demand_") :] for c in test_df.columns if c.startswith("demand_"))
        _DF_CACHE[relpath] = (train_df, test_df, item_id)
    return _DF_CACHE[relpath]


SELECTION = load_selection()


def test_selection_is_large_enough_and_stratified() -> None:
    """The evidence base must be the set the plan asked for, not whatever happened to be handy."""
    assert len(SELECTION) >= 200, f"only {len(SELECTION)} instances selected"
    labels = {"lead_time_0": 0, "lead_time_4": 0, "lead_time_stochastic": 0}
    ratios = {"high": 0, "med": 0, "low": 0}
    for relpath in SELECTION:
        for label in labels:
            if label in relpath.split("/"):
                labels[label] += 1
    assert all(count > 0 for count in labels.values()), labels
    # Cost ratios are checked from the data, since real paths carry no ratio token.
    for relpath in SELECTION:
        _, test_df, item_id = _load_official(relpath)
        profit = float(test_df.iloc[0][f"profit_{item_id}"])
        ratios[{19.0: "high", 4.0: "med", 1.0: "low"}[profit]] += 1
    assert all(count > 0 for count in ratios.values()), ratios


# ---------------------------------------------------------------------------
# the differential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relpath", SELECTION, ids=lambda p: p.replace("/", ":"))
def test_runner_matches_official_pipeline_exactly(relpath: str) -> None:
    train_df, test_df, item_id = _load_official(relpath)
    instance_dir = benchmark_root() / relpath

    # Our loader's derived promised lead time must equal upstream's.
    ours = load_instance(instance_dir, episode_id=relpath)
    assert ours.spec.promised_lead_time == official_detect_promised_lead_time(instance_dir)
    assert ours.spec.item_id == item_id
    assert ours.spec.horizon == len(test_df)

    # Train parsing is compared on its own, so a mismatch there cannot be mistaken for an
    # accounting difference later.
    official_train = [float(v) for v in train_df[f"demand_{item_id}"].tolist()]
    assert list(ours.spec.train_demand) == official_train

    train_mean = sum(official_train) / len(official_train) if official_train else 0.0
    initial_samples = list(
        zip(
            train_df[f"exact_dates_{item_id}"].tolist(),
            train_df[f"demand_{item_id}"].tolist(),
            strict=True,
        )
    )
    first_row = test_df.iloc[0]
    desc_col = f"description_{item_id}"

    for kind in REFERENCE_KINDS:
        params = ReferenceParams(kind=kind, train_mean=train_mean)

        # --- our side ------------------------------------------------------
        outcome = EpisodeRunner(instance=ours).run(
            ReferenceController(params=params, arm_id=f"ref_{kind}")
        )
        our_orders = [float(r.order_quantity) for r in outcome.result.records]

        # --- official policy loop -------------------------------------------
        policy = make_upstream_policy(
            params,
            item_id=item_id,
            initial_samples=initial_samples,
            promised_lead_time=official_detect_promised_lead_time(instance_dir),
            profit_per_unit=float(first_row[f"profit_{item_id}"]),
            holding_cost_per_unit=float(first_row[f"holding_cost_{item_id}"]),
            product_description=str(first_row[desc_col]) if desc_col in first_row else None,
        )
        official_results = official_simulate_instance(policy, test_df, item_id)
        official_orders = [float(v) for v in official_results["order_quantity"].tolist()]

        first_bad = next(
            (
                period
                for period, (a, b) in enumerate(
                    zip(our_orders, official_orders, strict=True), start=1
                )
                if a != b
            ),
            None,
        )
        assert first_bad is None, (
            f"{relpath} [{kind}]: orders diverge from the official policy loop at period "
            f"{first_bad} (ours={our_orders[first_bad - 1]}, "
            f"official={official_orders[first_bad - 1]})"
        )

        # --- official accounting on our orders ------------------------------
        results_df = pd.DataFrame(
            {"period": [r.period for r in outcome.result.records], "order_quantity": our_orders}
        )
        official_scores = official_simulate_and_score(results_df, test_df, item_id)

        aggregate_pairs = {
            "total_reward": (outcome.result.total_reward, official_scores["total_reward"]),
            "total_profit": (outcome.result.total_profit, official_scores["total_profit"]),
            "total_holding_cost": (
                outcome.result.total_holding_cost,
                official_scores["total_holding_cost"],
            ),
            "units_sold": (outcome.result.total_sold, official_scores["units_sold"]),
            "perfect_foresight": (
                outcome.result.perfect_foresight,
                official_scores["perfect_foresight"],
            ),
            "normalized_reward": (
                outcome.result.normalized_reward,
                official_scores["normalized_reward"],
            ),
            "fill_rate": (outcome.result.fill_rate, official_scores["service_level"]),
        }
        max_abs = 0.0
        worst_field: str | None = None
        for name, (mine, theirs) in aggregate_pairs.items():
            diff = abs(float(mine) - float(theirs))
            if diff > max_abs:
                max_abs, worst_field = diff, name
        assert max_abs == 0.0, (
            f"{relpath} [{kind}]: {worst_field} differs from the official evaluator by "
            f"{max_abs!r} (ours={aggregate_pairs[worst_field][0]!r}, "
            f"official={aggregate_pairs[worst_field][1]!r})"
        )

        # --- per-period series ----------------------------------------------
        trace = reference_trace(test_df, item_id, our_orders)
        per_period_fields = (
            "on_hand_start",
            "in_transit_start",
            "arrivals",
            "demand",
            "units_sold",
            "on_hand_end",
            "period_profit",
            "period_holding",
        )
        first_divergent: int | None = None
        divergent_field: str | None = None
        for record, expected in zip(outcome.result.records, trace, strict=True):
            for name in per_period_fields:
                diff = abs(float(getattr(record, name)) - expected[name])
                if diff > max_abs:
                    max_abs, worst_field = diff, name
                if diff != 0.0 and first_divergent is None:
                    first_divergent, divergent_field = record.period, name
        assert first_divergent is None, (
            f"{relpath} [{kind}]: per-period {divergent_field} first diverges at period "
            f"{first_divergent}"
        )

        # The transcription is only trustworthy if it reproduces upstream's own aggregates.
        assert math.fsum(row["period_profit"] for row in trace) == official_scores["total_profit"]
        assert (
            math.fsum(row["period_holding"] for row in trace)
            == official_scores["total_holding_cost"]
        )

        _OBSERVED.append(
            Diff(
                relpath=relpath,
                kind=kind,
                horizon=ours.spec.horizon,
                max_abs_diff=max_abs,
                first_divergent_period=first_divergent,
                field=worst_field,
            )
        )


# ---------------------------------------------------------------------------
# the documented harness divergence, pinned down
# ---------------------------------------------------------------------------


class ReplayController:
    """Emits a fixed order sequence, ignoring observations entirely.

    Lets a run be reproduced independently of whatever the policy was shown, which is how the
    harness-divergence test separates *policy inputs* from *physics*.
    """

    arm_id = "replay"

    def __init__(self, orders: list[float]) -> None:
        self.orders = list(orders)

    def reset(self) -> None: ...

    def order(self, obs: PeriodObservation) -> Decision:
        return Decision(
            period=obs.period,
            order_quantity=self.orders[obs.period - 1],
            arm_id=self.arm_id,
        )


def _selected_with_losses() -> tuple[str, ...]:
    found = []
    for relpath in SELECTION:
        if "lead_time_stochastic" not in relpath.split("/"):
            continue
        instance = load_instance(benchmark_root() / relpath, episode_id=relpath)
        if instance.supply.n_lost > 0:
            found.append(relpath)
    return tuple(found)


def test_lost_shipments_exist_only_under_the_stochastic_label() -> None:
    """Cross-checks the audit: losses never appear under a deterministic lead-time label."""
    for relpath in SELECTION:
        instance = load_instance(benchmark_root() / relpath, episode_id=relpath)
        stochastic = "lead_time_stochastic" in relpath.split("/")
        if not stochastic:
            assert instance.supply.n_lost == 0, f"{relpath} has a lost shipment"
    assert _selected_with_losses(), "the selection contains no lost shipments to test with"


def test_harness_divergence_moves_policy_inputs_not_the_accounting() -> None:
    """``env.py`` vs ``eval/`` on lost orders: what it changes, and what it does not.

    The two upstream harnesses disagree only about whether a lost shipment stays *visible* in
    in-transit (``docs/env_contract.md`` §6). So the divergence reaches a policy that reads
    ``in_transit_total`` and cannot reach one that ignores it, and it never changes the physics:
    lost units land under neither harness. That is why ``eval/`` semantics are authoritative for
    our runner while the legacy arms may still be run the other way, provided the comparison
    says which was used.
    """
    with_losses = _selected_with_losses()
    assert with_losses

    constant_identical = True
    base_stock_diverged = False

    for relpath in with_losses:
        instance = load_instance(benchmark_root() / relpath, episode_id=relpath)
        train = instance.spec.train_demand
        train_mean = sum(train) / len(train) if train else 0.0

        for kind in ("constant", "base_stock"):
            params = ReferenceParams(kind=kind, train_mean=train_mean)
            eval_side = EpisodeRunner(instance=instance).run(
                ReferenceController(params=params, arm_id="eval_path")
            )
            env_side = EpisodeRunner(instance=instance, lost_orders_visible_in_transit=True).run(
                ReferenceController(params=params, arm_id="env_path")
            )

            eval_orders = [r.order_quantity for r in eval_side.result.records]
            env_orders = [r.order_quantity for r in env_side.result.records]

            if kind == "constant":
                # A policy that ignores in-transit cannot see the difference at all.
                constant_identical &= eval_orders == env_orders
                assert eval_side.result.total_reward == env_side.result.total_reward
                assert eval_side.lost_units == env_side.lost_units
            elif eval_orders != env_orders:
                base_stock_diverged = True

            # The physics is not in dispute: replaying the env-side orders under eval semantics
            # reproduces the env-side accounting exactly, because the harnesses differ only in
            # what the *policy is shown*, never in what actually arrives. A base-stock policy
            # orders less under env semantics and so loses fewer units, but that is a consequence
            # of the different orders, not of different physics.
            replay = EpisodeRunner(instance=instance).run(ReplayController(env_orders))
            assert replay.result.total_reward == env_side.result.total_reward
            assert replay.lost_units == env_side.lost_units
            assert [r.arrivals for r in replay.result.records] == [
                r.arrivals for r in env_side.result.records
            ]

    assert constant_identical, "a policy ignoring in-transit somehow saw the harness difference"
    assert base_stock_diverged, (
        "no base-stock divergence found, so the recorded harness difference would be untested"
    )


# ---------------------------------------------------------------------------
# the Gate 1 artifact
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _write_equivalence_report() -> Any:
    yield
    if not _OBSERVED:
        return
    worst = max(d.max_abs_diff for d in _OBSERVED)
    instances = sorted({d.relpath for d in _OBSERVED})
    by_label: dict[str, int] = {}
    for relpath in instances:
        for label in ("lead_time_0", "lead_time_4", "lead_time_stochastic"):
            if label in relpath.split("/"):
                by_label[label] = by_label.get(label, 0) + 1
    lines = [
        "# Accounting equivalence report (Task 4)",
        "",
        "Generated by `make equivalence`. Do not hand-edit.",
        "",
        f"- comparisons: **{len(_OBSERVED)}** ({len(instances)} instances "
        f"x {len(REFERENCE_KINDS)} reference policies)",
        f"- maximum absolute difference: **{worst!r}**",
        "- required: exactly `0.0` (all quantities are integer-valued, so any "
        "difference is semantic, not numerical)",
        "",
        "## Instances by lead-time label",
        "",
    ]
    lines += [f"- `{label}`: {count}" for label, count in sorted(by_label.items())]
    lines += [
        "",
        "## What was compared",
        "",
        "1. Orders, against `run_baseline_policy.simulate_instance` driving the same policy.",
        "2. Episode aggregates, against `evaluate_results.simulate_and_score` on our orders:",
        "   total reward, profit, holding cost, units sold, perfect foresight, normalized",
        "   reward, service level.",
        "3. Per-period `on_hand_start`, `in_transit_start`, `arrivals`, `demand`, `units_sold`,",
        "   `on_hand_end`, `period_profit`, `period_holding`, against a literal transcription of",
        "   the upstream loop whose own aggregates are pinned to upstream by (2).",
        "",
        "The instance set is committed at `manifests/equivalence_instances.txt`.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
