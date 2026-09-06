"""Calibrate the trigger thresholds on dev/cal null data (Task 18.2, R1.9).

Data discipline: only the dev and cal **twin** episodes enter — 36 + 24 stationary paths of
horizon 50 under the registered stationary-IID law. Test data never enters, and the frozen output
(``collie/trigger/calibration.py``) records the provenance string so a reviewer can see what the
numbers were allowed to look at.

The rule (research notes §2): per episode, the maximum of the raw two-sided statistic under the
null; the threshold is the nearest-rank 95% quantile of those 60 maxima — pure stdlib, no numpy
quantile-method ambiguity. Raw detectors are used (no wrapper reset), which is conservative: a
permitted firing only ever lowers the accumulators afterwards, so the in-production null max is
never larger than the calibrated one.

Usage::

    uv run python -m tools.calibrate_triggers          # print the computed calibration
    uv run python -m tools.calibrate_triggers --check  # compare against the frozen constants
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass

from collie.contracts import PeriodObservation, Split
from collie.data.families import generate_episode
from collie.data.splits import build_units
from collie.trigger.detectors import Cusum, PageHinkley

HORIZON = 50  # official synthetic horizon (env contract §1), as tools/build_shockspec.py
NULL_QUANTILE = 0.95
MU0, SIGMA0 = 100.0, 25.0  # the registered stationary-IID law (collie/data/families/base.py)
CUSUM_K = 0.5  # NIST convention: reference = half the standardised shift to detect quickly
PH_DELTA = 0.5 * SIGMA0  # same allowance, raw units (research notes §2)
REFRACTORY_WINDOW = 5
"""Covers the longest registered pulse (4) and pause (5) so one incident is one firing cluster."""
MAX_PROPOSALS = 2
"""The primary design's cap (derivation note §5: alpha_j = alpha * 2**-j)."""


def null_twin_demands() -> tuple[tuple[float, ...], ...]:
    """The calibration set: dev and cal twin paths, in episode order (deterministic)."""
    series: list[tuple[float, ...]] = []
    for split in (Split.DEV, Split.CAL):
        for unit in build_units(split):
            assert unit.params is not None
            ep = generate_episode(seed=unit.seed, horizon=HORIZON, params=unit.params)
            series.append(ep.twin_demand)
    return tuple(series)


def _obs(period: int, prev_demand: float) -> PeriodObservation:
    """A minimal observation carrying exactly what a demand detector may read."""
    return PeriodObservation(
        period=period,
        date=f"Period_{period}",
        on_hand=0.0,
        in_transit_total=0.0,
        prev_order=0.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=prev_demand,
    )


def episode_max_statistics(demand: tuple[float, ...]) -> tuple[float, float]:
    """Per-episode null maxima: CUSUM in sigma units, Page-Hinkley in raw units."""
    cusum = Cusum(MU0, SIGMA0, CUSUM_K, h=math.inf)  # h=inf: never fires, just accumulates
    ph = PageHinkley(MU0, SIGMA0, PH_DELTA, threshold=math.inf)
    cusum_max = ph_max = 0.0
    for t in range(1, len(demand) + 1):
        obs = _obs(t, 0.0 if t == 1 else demand[t - 2])
        cusum.should_propose(obs)
        ph.should_propose(obs)
        cusum_max = max(cusum_max, cusum.statistic)
        ph_max = max(ph_max, ph.statistic)
    return cusum_max / SIGMA0, ph_max


def nearest_rank(values: list[float], q: float) -> float:
    """The nearest-rank quantile: smallest value with at least ``q`` mass at or below it."""
    if not values:
        raise ValueError("no values to rank")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


@dataclass(frozen=True, slots=True)
class ComputedCalibration:
    cusum_h: float
    ph_threshold: float
    n_null_episodes: int
    null_fires_cusum: int
    null_fires_ph: int

    def as_frozen_literal(self) -> str:
        return (
            f"    mu0={MU0!r},\n"
            f"    sigma0={SIGMA0!r},\n"
            f"    cusum_k={CUSUM_K!r},\n"
            f"    cusum_h={self.cusum_h!r},\n"
            f"    ph_delta={PH_DELTA!r},\n"
            f"    ph_threshold={self.ph_threshold!r},\n"
            f"    refractory_window={REFRACTORY_WINDOW!r},\n"
            f"    max_proposals={MAX_PROPOSALS!r},"
        )


def compute() -> ComputedCalibration:
    twins = null_twin_demands()
    cusum_maxima: list[float] = []
    ph_maxima: list[float] = []
    for series in twins:
        c_max, p_max = episode_max_statistics(series)
        cusum_maxima.append(c_max)
        ph_maxima.append(p_max)
    cusum_h = nearest_rank(cusum_maxima, NULL_QUANTILE)
    ph_threshold = nearest_rank(ph_maxima, NULL_QUANTILE)
    return ComputedCalibration(
        cusum_h=cusum_h,
        ph_threshold=ph_threshold,
        n_null_episodes=len(twins),
        # Episodes whose null max strictly exceeds the threshold would fire under the null.
        null_fires_cusum=sum(1 for v in cusum_maxima if v > cusum_h),
        null_fires_ph=sum(1 for v in ph_maxima if v > ph_threshold),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.calibrate_triggers")
    parser.add_argument(
        "--check", action="store_true", help="compare against the frozen constants, exit 1 on drift"
    )
    args = parser.parse_args(argv)

    got = compute()
    if not args.check:
        print(
            f"calibration over {got.n_null_episodes} dev+cal twin episodes (horizon {HORIZON}); "
            f"nearest-rank q{NULL_QUANTILE}"
        )
        print(
            f"  null fire rate: cusum {got.null_fires_cusum}/{got.n_null_episodes}, "
            f"page-hinkley {got.null_fires_ph}/{got.n_null_episodes}"
        )
        print("paste into collie/trigger/calibration.py:")
        print(got.as_frozen_literal())
        return 0

    from collie.trigger.calibration import FROZEN

    problems = []
    if FROZEN.cusum_h != got.cusum_h:
        problems.append(f"cusum_h: frozen {FROZEN.cusum_h!r} != recomputed {got.cusum_h!r}")
    if FROZEN.ph_threshold != got.ph_threshold:
        problems.append(
            f"ph_threshold: frozen {FROZEN.ph_threshold!r} != recomputed {got.ph_threshold!r}"
        )
    if FROZEN.mu0 != MU0 or FROZEN.sigma0 != SIGMA0:
        problems.append("mu0/sigma0 drifted from the registered stationary law")
    if FROZEN.cusum_k != CUSUM_K or FROZEN.ph_delta != PH_DELTA:
        problems.append("k/ph_delta drifted from the registered allowances")
    if FROZEN.refractory_window != REFRACTORY_WINDOW or FROZEN.max_proposals != MAX_PROPOSALS:
        problems.append("refractory_window/max_proposals drifted from the registered values")
    if problems:
        print("STALE calibration, regenerate collie/trigger/calibration.py:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("trigger calibration intact")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
