"""Task 18 — shared trigger infrastructure: detectors, wrappers, calibration, feature legality.

The properties under test are the ones the arm ladder stands on: the refractory window and the
two-proposal cap hold in one place for any stream; arms sharing a rule produce bitwise-identical
traces; matched schedules match on realised calls; and no trigger can name forbidden information.
"""

from __future__ import annotations

import ast
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from collie.contracts import Decision, PeriodObservation
from collie.sim.runner import EpisodeRunner
from collie.trigger import (
    FEATURE_DENYLIST,
    AlertOnly,
    AlertOrDetector,
    Cusum,
    FeatureLegalityError,
    MaxProposalsWrapper,
    OnlineFeatures,
    PageHinkley,
    PeriodicEveryK,
    RandomMatched,
    RefractoryWrapper,
    TraceEntry,
    TriggerTrace,
    assert_features_legal,
)
from collie.trigger.calibration import FROZEN
from tests.strategies_arms import (
    alert_placements,
    demand_streams,
    make_observations,
    seeds,
    windows,
)
from tests.test_episode_runner import make_instance

REPO_ROOT = Path(__file__).resolve().parents[1]

# Hand-checkable calibration: K = 12.5 units of slack, H = 100 units of decision interval.
CUSUM = {"mu0": 100.0, "sigma0": 25.0, "k": 0.5, "h": 4.0}
PH = {"mu0": 100.0, "sigma0": 25.0, "delta": 12.5, "threshold": 100.0}

# A level shift 100 -> 150 at period 10: the first shifted demand is seen by the period-11
# observation, and each shifted period adds 150 - 100 - 12.5 = 37.5 to the statistic.
SHIFTED = [100.0] * 9 + [150.0] * 41


def _chain(inner, window=5, cap=2):
    return MaxProposalsWrapper(RefractoryWrapper(inner, window), cap)


def _run(trigger, observations) -> TriggerTrace:
    for obs in observations:
        trigger.should_propose(obs)
    return trigger.trace


# ---------------------------------------------------------------------------
# detectors: hand-computed firings
# ---------------------------------------------------------------------------


def test_cusum_fires_at_the_hand_computed_period() -> None:
    trace = _run(Cusum(**CUSUM), make_observations(SHIFTED))
    assert trace.entries[0] == TraceEntry(13, "cusum_up", 112.5)


def test_cusum_down_fires_on_decrease() -> None:
    demands = [100.0] * 9 + [50.0] * 41
    trace = _run(Cusum(**CUSUM), make_observations(demands))
    assert trace.entries[0] == TraceEntry(13, "cusum_down", 112.5)


def test_page_hinkley_fires_at_the_hand_computed_period() -> None:
    trace = _run(PageHinkley(**PH), make_observations(SHIFTED))
    assert trace.entries[0] == TraceEntry(13, "page_hinkley_up", 112.5)


def test_constant_null_stream_never_fires() -> None:
    stream = make_observations([100.0] * 50)
    assert _run(Cusum(**CUSUM), stream) == TriggerTrace()
    assert _run(PageHinkley(**PH), stream) == TriggerTrace()
    assert _run(AlertOrDetector(Cusum(**CUSUM)), stream) == TriggerTrace()


def test_period_1_reference_init_does_not_enter_the_statistic() -> None:
    """Period 1's prev_demand is the reference's 0.0 initialisation, not a measurement."""
    detector = Cusum(**CUSUM)
    fired = detector.should_propose(make_observations([100.0] * 5)[0])
    assert not fired
    assert detector.statistic == 0.0
    assert detector.trace == TriggerTrace()


def test_alert_only_fires_exactly_on_alerts() -> None:
    stream = make_observations([100.0] * 30, alert_at=[7, 22])
    trace = _run(AlertOnly(), stream)
    assert trace.entries == (
        TraceEntry(7, "alert", 1.0),
        TraceEntry(22, "alert", 1.0),
    )


def test_alert_or_detector_records_which_channel_fired() -> None:
    stream = make_observations(SHIFTED, alert_at=[5, 13])
    trace = _run(AlertOrDetector(Cusum(**CUSUM)), stream)
    assert trace.entries[:2] == (
        TraceEntry(5, "alert", 1.0),
        TraceEntry(13, "alert+cusum_up", 112.5),
    )
    assert all(e.rule == "cusum_up" for e in trace.entries[2:])


def test_censored_observation_raises() -> None:
    obs = PeriodObservation(
        period=2,
        date="Period_2",
        on_hand=0.0,
        in_transit_total=0.0,
        prev_order=0.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=None,
        prev_sales=50.0,
        prev_availability=True,
    )
    with pytest.raises(ValueError, match="uncensored demand"):
        Cusum(**CUSUM).should_propose(obs)
    with pytest.raises(ValueError, match="uncensored demand"):
        PageHinkley(**PH).should_propose(obs)


# ---------------------------------------------------------------------------
# the wrappers: cap and refractory, in one place
# ---------------------------------------------------------------------------


def test_third_proposal_suppressed() -> None:
    chain = _chain(AlertOnly(), window=5, cap=2)
    trace = _run(chain, make_observations([100.0] * 40, alert_at=[10, 20, 30]))
    assert trace.periods == (10, 20)
    assert trace.n_suppressed == 1


def test_repeated_firing_inside_window_suppressed() -> None:
    chain = _chain(AlertOnly(), window=3, cap=10)
    trace = _run(chain, make_observations([100.0] * 40, alert_at=[10, 11, 12, 14]))
    assert trace.periods == (10, 14)
    assert trace.n_suppressed == 2


def test_refractory_window_edge_is_exact() -> None:
    # window=5 suppresses raw firings through last+5; last+6 is permitted.
    chain = _chain(AlertOnly(), window=5, cap=10)
    trace = _run(chain, make_observations([100.0] * 40, alert_at=[10, 15, 16]))
    assert trace.periods == (10, 16)


def test_permitted_firing_restarts_detector_accumulators() -> None:
    """Restart-after-signal is observable in the raw statistic, not just the trace shape.

    Horizon 20, shift at 10, window 5, cap 2. The raw detector fires at 13 (37.5 x 3 = 112.5),
    the wrapper permits and discharges the accumulators, and the statistic re-accumulates from
    zero: 112.5 at 16, 150 at 17, 187.5 at 18 (all suppressed), 225 at 19 — permitted, exactly
    one window later. Without the restart the 19-period firing would read 337.5 instead.
    """
    detector = Cusum(**CUSUM)
    chain = _chain(detector, window=5, cap=2)
    demands = [100.0] * 9 + [150.0] * 11
    trace = _run(chain, make_observations(demands))
    assert trace.entries == (
        TraceEntry(13, "cusum_up", 112.5),
        TraceEntry(19, "cusum_up", 225.0),
    )
    assert trace.n_suppressed == 3
    assert detector.trace.entries[-1] == TraceEntry(19, "cusum_up", 225.0)
    # Discharged at 19, then one more shifted observation: 37.5, not the 262.5 an
    # unrestarted accumulator would read.
    assert detector.statistic == 37.5


def test_cap_zero_permits_nothing() -> None:
    chain = _chain(AlertOnly(), window=0, cap=0)
    trace = _run(chain, make_observations([100.0] * 10, alert_at=[3, 4]))
    assert trace == TriggerTrace(entries=(), n_suppressed=2)


def test_unwrapped_detector_fires_more_than_the_cap() -> None:
    """Negative control: the cap comes from the wrapper, not from a well-behaved detector."""
    raw = _run(AlertOnly(), make_observations([100.0] * 40, alert_at=[10, 20, 30]))
    assert len(raw) == 3  # would violate the cap if the wrapper were not load-bearing


def test_wrapper_reset_restores_byte_identical_replay() -> None:
    stream = make_observations(SHIFTED, alert_at=[6])
    for kind in ("alert_only", "cusum", "page_hinkley", "alert_or_detector"):
        chain = _chain(_build_detector(kind))
        first = _run(chain, stream)
        chain.reset()
        assert chain.trace == TriggerTrace()
        assert _run(chain, stream) == first


def test_reset_accumulators_discharges_without_clearing_the_trace() -> None:
    """The outermost wrapper's restart reaches the detector and leaves the record intact."""
    detector = Cusum(**CUSUM)
    chain = _chain(detector)
    stream = make_observations(SHIFTED)
    for obs in stream[:13]:  # through the first firing at 13
        chain.should_propose(obs)
    assert len(chain.trace) == 1
    chain.reset_accumulators()
    assert detector.statistic == 0.0
    assert len(chain.trace) == 1  # the record is not touched


def test_invalid_wrapper_and_detector_parameters_raise() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        RefractoryWrapper(AlertOnly(), -1)
    with pytest.raises(ValueError, match="non-negative"):
        MaxProposalsWrapper(AlertOnly(), -1)
    with pytest.raises(ValueError, match="sigma0"):
        Cusum(100.0, 0.0, 0.5, 4.0)
    with pytest.raises(ValueError, match="positive"):
        Cusum(100.0, 25.0, 0.0, 4.0)
    with pytest.raises(ValueError, match="positive"):
        PageHinkley(100.0, 25.0, 0.0, 100.0)
    with pytest.raises(ValueError, match="positive"):
        PageHinkley(100.0, 25.0, 12.5, 0.0)
    with pytest.raises(ValueError, match="sigma0"):
        PageHinkley(100.0, 0.0, 12.5, 100.0)
    with pytest.raises(ValueError, match="non-negative"):
        PeriodicEveryK.from_budget(-1, 50)
    with pytest.raises(ValueError, match="min_spacing"):
        RandomMatched.from_budget(2, 50, seed=1, min_spacing=0)


# ---------------------------------------------------------------------------
# trace equality: invocation is not a confound
# ---------------------------------------------------------------------------


def test_identical_trace_across_arms_sharing_a_rule() -> None:
    stream = make_observations(SHIFTED, alert_at=[6, 40])
    build = lambda: _chain(AlertOrDetector(Cusum(**CUSUM)))  # noqa: E731
    first, second = build(), build()
    _run(first, stream)
    _run(second, stream)
    assert first.trace == second.trace
    # And not vacuously: the stream exercised both channels and both wrappers.
    assert len(first.trace) == 2
    assert first.trace.n_suppressed > 0


class _TappingController:
    """Feeds every observation to a trigger chain, then defers the order to an inner controller.

    Proves the end-to-end claim: a trigger tapped into a *running* arm sees the same stream as a
    pure replay, because demand and alerts are exogenous to the policy (env contract §3/§4).
    """

    def __init__(self, inner, trigger) -> None:
        self.inner = inner
        self.trigger = trigger
        self.arm_id = "tap"

    def reset(self) -> None:
        self.inner.reset()
        self.trigger.reset()

    def order(self, obs: PeriodObservation) -> Decision:
        self.trigger.should_propose(obs)
        return self.inner.order(obs)


def test_trace_inside_a_running_episode_matches_pure_replay() -> None:
    from collie.fakes import ConstantController

    horizon = 30
    demands = tuple([100.0] * 9 + [150.0] * (horizon - 9))
    instance = make_instance(demands, (0.0,) * horizon)
    tapped = _TappingController(
        ConstantController(quantity=10), _chain(AlertOrDetector(Cusum(**CUSUM)))
    )
    outcome = EpisodeRunner(instance=instance).run(tapped)
    replay = _run(_chain(AlertOrDetector(Cusum(**CUSUM))), make_observations(demands))
    assert tapped.trigger.trace == replay
    # The tap itself is inert: identical orders to the untapped controller.
    assert all(r.order_quantity == 10 for r in outcome.result.records)


# ---------------------------------------------------------------------------
# budget-matched schedules
# ---------------------------------------------------------------------------


def test_periodic_and_random_matched_on_realised_calls() -> None:
    stream = make_observations([100.0] * 50, alert_at=[10, 30])
    comparator = _run(_chain(AlertOnly()), stream)  # realised: 2 calls
    n = len(comparator)

    periodic = _chain(PeriodicEveryK.from_budget(n, 50, min_spacing=6))
    random_m = _chain(RandomMatched.from_budget(n, 50, seed=7, min_spacing=6))
    assert _run(periodic, make_observations([100.0] * 50)).periods == (17, 34)
    assert _run(random_m, make_observations([100.0] * 50)).__len__() == n

    # Zero realised calls -> empty schedules, never a gratuitous call.
    empty = _run(_chain(AlertOnly()), make_observations([100.0] * 50))
    assert len(empty) == 0
    assert PeriodicEveryK.from_budget(0, 50, min_spacing=6).periods == ()
    assert RandomMatched.from_budget(0, 50, seed=7, min_spacing=6).periods == ()


def test_schedules_reset_and_replay_identically() -> None:
    stream = make_observations([100.0] * 50)
    for schedule in (
        PeriodicEveryK.from_budget(2, 50, min_spacing=6),
        RandomMatched.from_budget(2, 50, seed=11, min_spacing=6),
    ):
        chain = _chain(schedule)
        first = _run(chain, stream)
        chain.reset()
        assert chain.trace == TriggerTrace()
        assert _run(chain, stream) == first


def test_infeasible_budgets_raise_instead_of_under_delivering() -> None:
    with pytest.raises(ValueError, match="cannot be spaced"):
        PeriodicEveryK.from_budget(10, 20, min_spacing=6)
    with pytest.raises(ValueError, match="cannot be spaced"):
        RandomMatched.from_budget(10, 20, seed=1, min_spacing=6)


def test_random_matched_is_deterministic_given_seed() -> None:
    first = RandomMatched.from_budget(3, 50, seed=99, min_spacing=2)
    second = RandomMatched.from_budget(3, 50, seed=99, min_spacing=2)
    assert first.periods == second.periods
    assert len(set(first.periods)) == 3
    assert all(b - a >= 2 for a, b in pairwise(first.periods))


# ---------------------------------------------------------------------------
# feature legality
# ---------------------------------------------------------------------------


def test_trigger_reads_no_denylisted_feature() -> None:
    """Runtime: the legal builder's schema passes the denylist, on every period of a stream."""
    features = OnlineFeatures()
    stream = make_observations([100.0] * 20 + [200.0] * 20, alert_at=[25])
    keys: set[str] = set()
    for obs in stream:
        out = features.update(obs)  # raises here if a key is ever illegal
        keys |= set(out)
    assert_features_legal(keys)
    # Pin the exact schema: adding a key is a deliberate, reviewed act.
    assert keys == {
        "period",
        "on_hand",
        "in_transit_total",
        "prev_order",
        "prev_arrivals",
        "profit_per_unit",
        "holding_cost_per_unit",
        "promised_lead_time",
        "critical_fractile",
        "n_demand_obs",
        "demand_mean",
        "demand_sd",
        "demand_last",
        "demand_residual_vs_running_mean",
        "demand_residual_vs_registered_null",
        "alert_arrived",
    }


def test_peeking_feature_builder_fails_the_check() -> None:
    """Negative control: the legality check must fire, or it is decoration."""
    with pytest.raises(FeatureLegalityError, match="denylisted"):
        assert_features_legal(["future_demand"])
    with pytest.raises(FeatureLegalityError, match="denylisted"):
        assert_features_legal(["demand_mean", "onset_gap"])  # substring, not exact
    assert_features_legal(["demand_mean", "on_hand"])  # legal keys pass


def test_peeking_builder_inside_online_features_fails_at_runtime(monkeypatch) -> None:
    import collie.trigger.features as features_mod

    original = features_mod.assert_features_legal

    def poisoned(keys):
        original([*list(keys), "future_demand"])

    monkeypatch.setattr(features_mod, "assert_features_legal", poisoned)
    features = OnlineFeatures()
    obs = make_observations([100.0] * 5)
    with pytest.raises(FeatureLegalityError, match="period 1"):
        features.update(obs[0])


STATIC_SCAN_EXEMPTIONS = {"demo.py"}


def test_trigger_sources_read_no_denylisted_attribute() -> None:
    """Static legality: AST-scan the trigger package for denylisted attribute reads.

    ``demo.py`` is the single named exemption: it is generation-side tooling that materialises
    episodes (reading registry seeds and realised onsets) and never feeds a policy. The
    exemption list itself is asserted, so widening it is a deliberate act.
    """
    import collie.trigger as trigger_pkg

    pkg = Path(trigger_pkg.__file__).parent
    scanned = {p.name for p in pkg.glob("*.py") if p.name not in STATIC_SCAN_EXEMPTIONS}
    assert scanned == {
        "__init__.py",
        "calibration.py",
        "detectors.py",
        "features.py",
        "protocol.py",
    }, f"a new trigger module needs a legality review: {scanned}"

    offenders: list[str] = []
    for name in scanned:
        path = pkg / name
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.lower() in FEATURE_DENYLIST:
                offenders.append(f"{name}:{node.lineno} reads .{node.attr}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and str(node.args[1].value).lower() in FEATURE_DENYLIST
            ):
                offenders.append(f"{name}:{node.lineno} getattr(..., {node.args[1].value!r})")
    assert not offenders, "denylisted reads in trigger code:\n  " + "\n  ".join(offenders)


def test_online_features_reset_clears_demand_history() -> None:
    features = OnlineFeatures()
    stream = make_observations([100.0] * 5 + [300.0] * 5)
    for obs in stream:
        features.update(obs)
    out = features.update(stream[0])  # period 1 carries no demand measurement
    assert out["n_demand_obs"] == 9.0
    features.reset()
    assert features.update(stream[0])["n_demand_obs"] == 0.0
    assert features.update(stream[1])["demand_mean"] == 100.0  # only period 1's demand seen


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------


def test_frozen_calibration_matches_regeneration() -> None:
    """R1.9: the frozen thresholds are exactly what the dev/cal-only procedure recomputes."""
    from tools.calibrate_triggers import compute

    got = compute()
    assert got.n_null_episodes == 60  # 36 dev + 24 cal twins
    assert FROZEN.cusum_h == got.cusum_h
    assert FROZEN.ph_threshold == got.ph_threshold
    # The realised null fire rate of the frozen thresholds on the calibration set.
    assert got.null_fires_cusum == got.null_fires_ph == 3


def test_calibration_cli_check_passes() -> None:
    from tools.calibrate_triggers import main

    assert main(["--check"]) == 0


# ---------------------------------------------------------------------------
# the Checkpoint 1 demo
# ---------------------------------------------------------------------------


def test_trigger_table_demo_runs_and_primary_beats_matched_random() -> None:
    from collie.trigger.demo import trigger_table

    table = trigger_table(6)
    assert "dev/f1/s1050000" in table and "dev/f6/s6050000" in table
    # The auditor's check: the primary rule fires near onset far more than budget-matched random.
    assert "alert_or_detector 6, random_matched 0" in table


def test_detectors_module_cli_entry() -> None:
    from collie.trigger.detectors import main

    main(["--trigger-table", "--episodes", "6"])  # prints the table; would raise on failure


def test_trigger_table_rejects_a_non_multiple_of_six() -> None:
    from collie.trigger.demo import trigger_table

    with pytest.raises(ValueError, match="multiple of 6"):
        trigger_table(7)


# ---------------------------------------------------------------------------
# properties (hypothesis)
# ---------------------------------------------------------------------------

DETECTOR_KINDS = st.sampled_from(["alert_only", "cusum", "page_hinkley", "alert_or_detector"])
CAPS = st.integers(min_value=0, max_value=4)


def _build_detector(kind: str):
    if kind == "alert_only":
        return AlertOnly()
    if kind == "cusum":
        return Cusum(**CUSUM)
    if kind == "page_hinkley":
        return PageHinkley(**PH)
    return AlertOrDetector(Cusum(**CUSUM))


@given(demands=demand_streams, alerts=alert_placements, window=windows, kind=DETECTOR_KINDS)
@settings(max_examples=200)
def test_trace_equality_property(demands, alerts, window, kind) -> None:
    """Arms sharing a rule produce bitwise-identical traces on any observation stream."""
    stream = make_observations(demands, alert_at=alerts)
    first = _run(_chain(_build_detector(kind), window=window), stream)
    second = _run(_chain(_build_detector(kind), window=window), stream)
    assert first == second


@given(demands=demand_streams, alerts=alert_placements, window=windows, kind=DETECTOR_KINDS)
@settings(max_examples=200)
def test_proposal_cap_holds_for_any_stream(demands, alerts, window, kind) -> None:
    chain = _chain(_build_detector(kind), window=window, cap=2)
    trace = _run(chain, make_observations(demands, alert_at=alerts))
    assert len(trace) <= 2


@given(demands=demand_streams, alerts=alert_placements, window=windows, kind=DETECTOR_KINDS)
@settings(max_examples=200)
def test_refractory_gaps_hold_for_any_window(demands, alerts, window, kind) -> None:
    chain = _chain(_build_detector(kind), window=window, cap=20)
    trace = _run(chain, make_observations(demands, alert_at=alerts))
    for earlier, later in pairwise(trace.entries):
        assert later.period - earlier.period > window


@given(demands=demand_streams, alerts=alert_placements, kind=DETECTOR_KINDS)
@settings(max_examples=200)
def test_permitted_entries_are_a_subsequence_of_raw_firings(demands, alerts, kind) -> None:
    """The wrappers only ever *subtract* from the detector's raw firings."""
    detector = _build_detector(kind)
    chain = RefractoryWrapper(detector, window=3)
    trace = _run(chain, make_observations(demands, alert_at=alerts))
    raw = detector.trace.entries
    it = iter(raw)
    for entry in trace.entries:
        assert entry in it, f"permitted {entry} not found in order in the raw trace"


@given(
    n=st.integers(min_value=0, max_value=20),
    horizon=st.integers(min_value=5, max_value=60),
    spacing=st.integers(min_value=1, max_value=8),
    seed=seeds,
)
@settings(max_examples=200)
def test_budget_matching_property(n, horizon, spacing, seed) -> None:
    """Matched schedules realise exactly the budget whenever the budget is realisable."""
    feasible = n == 0 or horizon >= n + (n - 1) * (spacing - 1)
    stream = make_observations([100.0] * horizon)
    if not feasible:
        with pytest.raises(ValueError, match="cannot be spaced"):
            PeriodicEveryK.from_budget(n, horizon, min_spacing=spacing)
        with pytest.raises(ValueError, match="cannot be spaced"):
            RandomMatched.from_budget(n, horizon, seed=seed, min_spacing=spacing)
        return
    for schedule in (
        PeriodicEveryK.from_budget(n, horizon, min_spacing=spacing),
        RandomMatched.from_budget(n, horizon, seed=seed, min_spacing=spacing),
    ):
        wrapped = _chain(schedule, window=spacing - 1, cap=max(n, 1))
        assert len(_run(wrapped, stream)) == n


@given(demands=demand_streams, alerts=alert_placements)
@settings(max_examples=200)
def test_feature_legality_property(demands, alerts) -> None:
    features = OnlineFeatures()
    for obs in make_observations(demands, alert_at=alerts):
        assert_features_legal(features.update(obs))


@given(demands=demand_streams)
@settings(max_examples=200)
def test_demand_detectors_never_fire_at_period_1(demands) -> None:
    for detector in (Cusum(**CUSUM), PageHinkley(**PH), AlertOrDetector(Cusum(**CUSUM))):
        trace = _run(detector, make_observations(demands))
        assert all(e.period > 1 for e in trace.entries)
