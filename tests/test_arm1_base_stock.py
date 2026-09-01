"""Task 5 — arm 1 (capped base-stock) and the official submission path.

The headline check is not that arm 1 scores *near* the published OR baseline but that it produces
**the same orders**: all 1,320 published order sequences, bit for bit, under `env.py` lost-order
semantics. An aggregate score is a weak target, since many different policies could land on it;
order-level identity leaves nowhere to hide.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

from collie.arms.base_stock import (
    ARM1_ARM_ID,
    BaseStockParams,
    CappedBaseStockController,
    base_stock_order,
)
from collie.contracts import ObservationMode, PeriodObservation, find_hidden_state
from collie.data.instances import InstanceKey, enumerate_instances, stratified_sample
from collie.eval.submission import aggregate, run_submission, score_instance, write_results_csv
from collie.sim.loader import LoadedInstance, load_instance
from collie.sim.runner import EpisodeRunner
from tests.test_episode_runner import make_instance
from tools.run_arm1 import PUBLISHED_OVERALL, make_arm1, published_orders, published_scores

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# the order rule
# ---------------------------------------------------------------------------


def test_no_samples_orders_nothing() -> None:
    assert (
        base_stock_order(
            samples=[],
            on_hand=0.0,
            in_transit=0.0,
            promised_lead_time=4,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
        )
        == 0.0
    )


def test_single_sample_uses_zero_dispersion() -> None:
    """``np.std(x, ddof=1)`` is undefined for one sample; upstream substitutes 0."""
    order = base_stock_order(
        samples=[100.0],
        on_hand=0.0,
        in_transit=0.0,
        promised_lead_time=0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
    )
    assert order == 100.0


@pytest.mark.parametrize(
    ("profit", "holding", "expected_fractile"),
    [(19.0, 1.0, 0.95), (4.0, 1.0, 0.8), (1.0, 1.0, 0.5)],
)
def test_critical_fractile_matches_the_three_cost_ratios(
    profit: float, holding: float, expected_fractile: float
) -> None:
    """The benchmark's three cost ratios give exactly these fractiles."""
    assert profit / (profit + holding) == pytest.approx(expected_fractile)


def test_low_margin_orders_the_mean() -> None:
    """At ``p == h`` the fractile is 0.5, ``z* == 0``, so the target is just the mean demand."""
    samples = [90.0, 100.0, 110.0]
    order = base_stock_order(
        samples=samples,
        on_hand=0.0,
        in_transit=0.0,
        promised_lead_time=0,
        profit_per_unit=1.0,
        holding_cost_per_unit=1.0,
    )
    assert order == 100.0


@pytest.mark.parametrize("lead_time", [0, 1, 2, 4, 7, 1000])
def test_the_cap_is_lead_time_independent(lead_time: int) -> None:
    """``mu_hat/(1+L) + z*sigma_hat/sqrt(1+L)`` reduces to ``mean + z*std`` for every L.

    Upstream writes the cap in the expanded form and adds a separate branch for ``L = inf``. The
    algebra shows both compute the same thing, which is why we implement the reduced form; this
    test is what licenses that simplification.
    """
    samples = [83.0, 97.0, 104.0, 111.0, 92.0]
    mean = float(np.mean(samples))
    std = float(np.std(samples, ddof=1))
    z = float(norm.ppf(0.95))

    mu_hat = (1 + lead_time) * mean
    sigma_hat = math.sqrt(1 + lead_time) * std
    upstream_form = mu_hat / (1 + lead_time) + z * sigma_hat / math.sqrt(1 + lead_time)

    assert upstream_form == pytest.approx(mean + z * std, rel=1e-12, abs=1e-12)


def test_order_is_ceilinged_then_floored_at_zero() -> None:
    """Upstream uses ``max(int(ceil(target - inventory)), 0)``."""
    samples = [100.0, 100.0, 100.0]  # std 0, so the target is exactly the mean
    # target 100, on hand 99.5 -> ceil(0.5) = 1
    assert (
        base_stock_order(
            samples=samples,
            on_hand=99.5,
            in_transit=0.0,
            promised_lead_time=0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
        )
        == 1.0
    )
    # already over target -> no negative order
    assert (
        base_stock_order(
            samples=samples,
            on_hand=500.0,
            in_transit=0.0,
            promised_lead_time=0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
        )
        == 0.0
    )


def test_in_transit_is_credited_against_the_target() -> None:
    samples = [100.0, 100.0, 100.0]
    with_pipeline = base_stock_order(
        samples=samples,
        on_hand=20.0,
        in_transit=30.0,
        promised_lead_time=0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
    )
    assert with_pipeline == 50.0, "target 100 less 20 on hand less 30 in transit"


def test_the_cap_binds_for_a_long_lead_time() -> None:
    """With L=4 the target covers five periods but the cap allows about one period's demand."""
    samples = [100.0, 120.0, 80.0, 110.0, 90.0]
    capped = base_stock_order(
        samples=samples,
        on_hand=0.0,
        in_transit=0.0,
        promised_lead_time=4,
        profit_per_unit=19.0,
        holding_cost_per_unit=1.0,
        params=BaseStockParams(capped=True),
    )
    uncapped = base_stock_order(
        samples=samples,
        on_hand=0.0,
        in_transit=0.0,
        promised_lead_time=4,
        profit_per_unit=19.0,
        holding_cost_per_unit=1.0,
        params=BaseStockParams(capped=False),
    )
    assert capped < uncapped
    mean = float(np.mean(samples))
    std = float(np.std(samples, ddof=1))
    assert capped == float(math.ceil(mean + float(norm.ppf(0.95)) * std))


def test_infinite_promised_lead_time_does_not_produce_nan() -> None:
    """Never triggered by the shipped benchmark, but upstream guards it and so do we."""
    order = base_stock_order(
        samples=[100.0, 110.0, 90.0],
        on_hand=0.0,
        in_transit=0.0,
        promised_lead_time=math.inf,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
    )
    assert math.isfinite(order)
    assert order >= 0.0


def test_cap_quantile_must_be_a_probability() -> None:
    with pytest.raises(ValueError, match="cap_quantile"):
        BaseStockParams(cap_quantile=1.0)


# ---------------------------------------------------------------------------
# the controller
# ---------------------------------------------------------------------------


def test_history_at_period_t_holds_demands_through_t_minus_one() -> None:
    """Regression guard for an off-by-one that lagged every order by a period.

    Upstream's estimator has already seen period ``t-1``'s demand when it decides at ``t``. An
    implementation that records after deciding is one observation short at every step, which is
    invisible in aggregate but shifts the whole order sequence.
    """
    demand = (10.0, 40.0, 40.0, 40.0)
    instance = make_instance(demand=demand, lead_times=(0.0,) * 4, profit=1.0, holding=1.0)
    controller = CappedBaseStockController(train_demand=(10.0,))
    outcome = EpisodeRunner(instance=instance).run(controller)
    orders = [r.order_quantity for r in outcome.result.records]

    # p == h so the fractile is 0.5 and z* == 0: with L=0 the target is exactly the running mean.
    # period 1: samples (10,)                 -> mean 10, on hand 0            -> 10
    # period 2: samples (10, 10)              -> mean 10, on hand 0            -> 10
    # period 3: samples (10, 10, 40)          -> mean 20, on hand 0            -> 20
    assert orders[0] == 10.0
    assert orders[1] == 10.0
    assert orders[2] == 20.0


def test_reset_clears_the_demand_history() -> None:
    instance = make_instance(demand=(10.0, 90.0, 90.0), lead_times=(0.0,) * 3, profit=1.0)
    controller = CappedBaseStockController(train_demand=(10.0,))
    first = EpisodeRunner(instance=instance).run(controller)
    second = EpisodeRunner(instance=instance).run(controller)
    assert [r.order_quantity for r in first.result.records] == [
        r.order_quantity for r in second.result.records
    ]


def test_the_arm_never_touches_hidden_state() -> None:
    instance = make_instance(demand=(10.0,) * 4, lead_times=(1.0, math.inf, 2.0, 0.0))
    controller = CappedBaseStockController(train_demand=(10.0, 12.0))
    runner = EpisodeRunner(instance=instance, check_controller_isolation=True)
    runner.run(controller)
    assert find_hidden_state(controller) == []


def test_the_arm_cannot_observe_actual_lead_times() -> None:
    """The observation surface has no actual-lead-time field, so the arm cannot key on it.

    Upstream states the same contract: "You do NOT observe actual lead times - must infer from
    arrivals."
    """
    fields = set(PeriodObservation.__slots__)
    assert "promised_lead_time" in fields
    assert not {f for f in fields if "actual" in f or "lead_times" in f}


def test_the_arm_refuses_censored_observations() -> None:
    """Substituting sales for demand would bias the estimator down at every stockout."""
    instance = make_instance(
        demand=(50.0, 50.0, 50.0),
        lead_times=(0.0, 0.0, 0.0),
        mode=ObservationMode.CENSORED,
    )
    with pytest.raises(ValueError, match="uncensored-demand policy"):
        EpisodeRunner(instance=instance).run(CappedBaseStockController(train_demand=(10.0,)))


def test_arm_id_is_stable() -> None:
    """The arm id lands in every record and every table, so it is part of the contract."""
    assert ARM1_ARM_ID == "arm1_capped_base_stock"
    assert CappedBaseStockController().arm_id == ARM1_ARM_ID


def test_our_order_cap_is_applied_on_top_of_the_policy_cap() -> None:
    """The policy's smoother and our registered cap are different things and compose."""
    instance = make_instance(
        demand=(1000.0, 1000.0), lead_times=(0.0, 0.0), profit=19.0, order_cap=5.0
    )
    outcome = EpisodeRunner(instance=instance).run(
        CappedBaseStockController(train_demand=(900.0, 1100.0))
    )
    assert all(r.order_quantity <= 5.0 for r in outcome.result.records)


# ---------------------------------------------------------------------------
# the submission path
# ---------------------------------------------------------------------------


def test_write_results_csv_has_the_official_header(tmp_path: Path) -> None:
    path = tmp_path / "results.csv"
    write_results_csv(path, ((1, 5), (2, 0), (3, 12)))
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["period", "order_quantity"]
    assert rows[1:] == [["1", "5"], ["2", "0"], ["3", "12"]]


def test_aggregate_refuses_an_empty_submission() -> None:
    with pytest.raises(ValueError, match="empty submission"):
        aggregate([])


@pytest.mark.needs_benchmark
def test_overall_score_is_instance_weighted_not_batch_weighted() -> None:
    """The batches are unequal (200 real vs 240 synthetic), so the two differ.

    Checked against the published file: the instance-weighted mean reproduces the published
    overall score, the mean of batch means does not.
    """
    published = published_scores()
    batch_scores = [b["score"] for b in published["batches"].values()]
    batch_sizes = [b["num_instances"] for b in published["batches"].values()]

    instance_weighted = sum(s * n for s, n in zip(batch_scores, batch_sizes, strict=True)) / sum(
        batch_sizes
    )
    batch_mean = sum(batch_scores) / len(batch_scores)

    assert instance_weighted == pytest.approx(PUBLISHED_OVERALL, abs=1e-15)
    assert batch_mean != pytest.approx(PUBLISHED_OVERALL, abs=1e-6)


# ---------------------------------------------------------------------------
# reproducing the published baseline
# ---------------------------------------------------------------------------


def _subset(per_cell: int = 4) -> tuple[InstanceKey, ...]:
    return stratified_sample(enumerate_instances(), per_cell=per_cell)


@pytest.mark.needs_benchmark
@pytest.mark.slow
def test_arm1_reproduces_published_orders_under_env_semantics() -> None:
    """Bit-for-bit order identity on a stratified subset, including the stochastic batches."""
    mismatches: list[str] = []
    for key in _subset():
        instance = load_instance(key.path(), episode_id=key.relpath)
        outcome = EpisodeRunner(instance=instance, lost_orders_visible_in_transit=True).run(
            make_arm1(instance)
        )
        ours = [quantity for _, quantity in outcome.order_rows()]
        theirs = published_orders(key.relpath)
        if ours != theirs:
            first = next(
                (i + 1 for i, (a, b) in enumerate(zip(ours, theirs, strict=True)) if a != b),
                None,
            )
            mismatches.append(f"{key.relpath} first differs at period {first}")
    assert not mismatches, "arm 1 diverged from the published baseline:\n  " + "\n  ".join(
        mismatches
    )


@pytest.mark.needs_benchmark
@pytest.mark.slow
def test_the_eval_harness_matches_published_orders_only_where_nothing_is_lost() -> None:
    """Under the authoritative harness, agreement holds exactly on instances with no lost shipment.

    This is the whole content of the divergence: it is confined to instances that actually lose a
    shipment, and on those it is systematic rather than occasional.
    """
    agree_without_loss = 0
    disagree_with_loss = 0
    for key in _subset():
        instance = load_instance(key.path(), episode_id=key.relpath)
        outcome = EpisodeRunner(instance=instance).run(make_arm1(instance))
        ours = [quantity for _, quantity in outcome.order_rows()]
        matches = ours == published_orders(key.relpath)
        has_loss = instance.supply.n_lost > 0
        if not has_loss:
            assert matches, f"{key.relpath} has no lost shipment yet diverged"
            agree_without_loss += 1
        else:
            assert not matches, f"{key.relpath} loses a shipment yet matched the env-path orders"
            disagree_with_loss += 1
    assert agree_without_loss > 0
    assert disagree_with_loss > 0


@pytest.mark.needs_benchmark
@pytest.mark.slow
def test_arm1_reproduces_the_published_batch_scores_under_env_semantics() -> None:
    """Scored by the official evaluator, our batch means equal the published batch means."""
    published = published_scores()["batches"]
    scores = run_submission(
        enumerate_instances(),
        make_arm1,
        out_dir=None,
        lost_orders_visible_in_transit=True,
    )
    assert scores.total_instances == 1320
    for name, expected in sorted(published.items()):
        assert scores.batch(name).score == pytest.approx(expected["score"], abs=1e-12), name
        assert scores.batch(name).service_level_mean == pytest.approx(
            expected["service_level_mean"], abs=1e-12
        ), name
    # One ULP of slack: the published overall is the same mean accumulated in a different order.
    assert scores.overall_score == pytest.approx(PUBLISHED_OVERALL, abs=1e-15)


@pytest.mark.needs_benchmark
@pytest.mark.slow
def test_arm1_runs_from_both_harnesses_and_the_gap_is_confined_to_stochastic(
    tmp_path: Path,
) -> None:
    """Gate 1 requirement: arm 1 runs under both harnesses, and the difference is accounted for."""
    keys = _subset()
    eval_scores = run_submission(
        keys, make_arm1, out_dir=tmp_path / "eval", lost_orders_visible_in_transit=False
    )
    env_scores = run_submission(
        keys, make_arm1, out_dir=tmp_path / "env", lost_orders_visible_in_transit=True
    )

    for batch in eval_scores.batches:
        env_batch = env_scores.batch(batch.name)
        if "stochastic" in batch.name:
            assert batch.score != pytest.approx(env_batch.score, abs=1e-9), (
                f"{batch.name} should differ between harnesses"
            )
            assert batch.score > env_batch.score, (
                "the eval path should do better: it does not credit inventory that never arrives"
            )
        else:
            assert batch.score == pytest.approx(env_batch.score, abs=1e-12), (
                f"{batch.name} has no lost shipments and must be identical"
            )

    # Both runs produced a real submission on disk.
    for harness in ("eval", "env"):
        written = list((tmp_path / harness / "results").rglob("results.csv"))
        assert len(written) == len(keys)
        assert (tmp_path / harness / "scores.json").is_file()


@pytest.mark.needs_benchmark
def test_score_instance_agrees_with_our_runner_on_one_instance() -> None:
    """The submission path and the in-process runner must not drift apart."""
    key = _subset(per_cell=1)[0]
    instance = load_instance(key.path(), episode_id=key.relpath)
    outcome = EpisodeRunner(instance=instance).run(make_arm1(instance))
    official = score_instance(key.relpath, outcome.order_rows())

    assert official.normalized_reward == outcome.result.normalized_reward
    assert official.total_reward == outcome.result.total_reward
    assert official.units_sold == outcome.result.total_sold
    assert official.service_level == outcome.result.fill_rate


@pytest.mark.needs_benchmark
def test_make_arm1_seeds_the_estimator_from_train_csv() -> None:
    key = _subset(per_cell=1)[0]
    instance: LoadedInstance = load_instance(key.path(), episode_id=key.relpath)
    controller = make_arm1(instance)
    assert controller.train_demand == instance.spec.train_demand
    assert controller.train_demand, "train.csv should provide initial samples"


# ---------------------------------------------------------------------------
# the published report artifact
# ---------------------------------------------------------------------------


def test_the_baseline_report_records_the_exact_reproduction() -> None:
    """Guards the Gate 1 artifact against being regenerated into something weaker."""
    report = (REPO_ROOT / "reports" / "arm1_or_baseline.md").read_text(encoding="utf-8")
    assert "1320/1320" in report, "the report must state order-level identity"
    assert "880" in report, "the report must state where the eval path still agrees"
    assert "0.44471016183446377" in report
    for fragment in ("env", "eval", "harness"):
        assert fragment in report
