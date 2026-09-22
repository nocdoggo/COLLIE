"""The six trigger rules.

``AlertOnly``, ``PageHinkley``, ``Cusum``, ``AlertOrDetector`` (the primary rule), and the two
budget-matched schedules ``PeriodicEveryK`` and ``RandomMatched``. Formulations and calibration
procedure: ``docs/module06_research_notes.md`` §2.

Two invariants hold for everything in this module:

- **Detectors are stateless about suppression.** No firing counters, no refractory logic, no
  budget checks — a detector emits a raw candidate firing and the wrappers
  (:mod:`collie.trigger.protocol`) decide. This is what makes the cap and the window uniform
  across rules, including rules written later.
- **Demand-side detectors read ``prev_demand`` and alerts only.** Both are exogenous to the
  policy (env contract §3/§4), so a trigger trace is a pure function of the episode's demand and
  alert streams — two arms sharing a rule on the same episode must produce bitwise-identical
  traces, and the test suite asserts exactly that.

Period 1 is never a candidate: its ``prev_demand = 0.0`` is the reference's own pre-loop
initialisation (``collie/sim/observation.py``), not a measurement, and feeding it to an
accumulator would inject a spurious ``-mu0`` residual.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

from collie.contracts import PeriodObservation
from collie.trigger.protocol import TraceEntry, TriggerTrace

__all__ = [
    "AlertOnly",
    "AlertOrDetector",
    "Cusum",
    "PageHinkley",
    "PeriodicEveryK",
    "RandomMatched",
]


class _TraceLog:
    """The mutable firing log behind each trigger's immutable trace snapshots."""

    __slots__ = ("entries",)

    def __init__(self) -> None:
        self.entries: list[TraceEntry] = []


def _demand_at(obs: PeriodObservation) -> float | None:
    """The demand observation entering the record at period ``obs.period``, if any.

    Returns ``None`` at period 1 (reference initialisation, not a measurement) and raises in
    censored mode: these detectors are uncensored-demand rules, and silently substituting sales
    for demand would bias every statistic during a stockout.
    """
    if obs.period == 1:
        return None
    if obs.prev_demand is None:
        raise ValueError(
            "demand-side triggers require uncensored demand; period "
            f"{obs.period} carries no prev_demand (observation mode censored)"
        )
    return obs.prev_demand


@dataclass(slots=True)
class AlertOnly:
    """Fire whenever an operational alert arrives. The alert channel's pure form."""

    _log: _TraceLog = field(default_factory=_TraceLog, repr=False)

    def reset(self) -> None:
        self._log.entries.clear()

    @property
    def trace(self) -> TriggerTrace:
        return TriggerTrace(tuple(self._log.entries))

    def reset_accumulators(self) -> None:  # stateless: nothing to restart
        return None

    def should_propose(self, obs: PeriodObservation) -> bool:
        if obs.alert is None:
            return False
        self._log.entries.append(TraceEntry(obs.period, "alert", 1.0))
        return True


@dataclass(slots=True)
class Cusum:
    """Two-sided tabular CUSUM against a frozen null ``(mu0, sigma0)``.

    ``C+ = max(0, C+ + x - mu0 - K)``, ``C- = max(0, C- - (x - mu0) - K)``, fire when either
    exceeds ``H``. Reference value ``K = k * sigma0`` (k = half the standardised shift to detect
    quickly, the NIST convention); decision interval ``H = h * sigma0`` with ``h`` calibrated on
    dev/cal null data and frozen (``collie/trigger/calibration.py``). With the null mean frozen,
    Page-Hinkley coincides with this construction (research notes §2).
    """

    mu0: float
    sigma0: float
    k: float
    h: float
    _c_up: float = field(default=0.0, repr=False)
    _c_down: float = field(default=0.0, repr=False)
    _log: _TraceLog = field(default_factory=_TraceLog, repr=False)

    def __post_init__(self) -> None:
        if self.sigma0 <= 0:
            raise ValueError(f"sigma0 must be positive, got {self.sigma0}")
        if self.k <= 0 or self.h <= 0:
            raise ValueError(f"k and h must be positive, got k={self.k}, h={self.h}")

    def reset(self) -> None:
        self._log.entries.clear()
        self.reset_accumulators()

    def reset_accumulators(self) -> None:
        self._c_up = 0.0
        self._c_down = 0.0

    @property
    def trace(self) -> TriggerTrace:
        return TriggerTrace(tuple(self._log.entries))

    @property
    def statistic(self) -> float:
        """Current two-sided statistic, in raw demand units."""
        return max(self._c_up, self._c_down)

    def should_propose(self, obs: PeriodObservation) -> bool:
        x = _demand_at(obs)
        if x is None:
            return False
        slack = self.k * self.sigma0
        self._c_up = max(0.0, self._c_up + (x - self.mu0) - slack)
        self._c_down = max(0.0, self._c_down - (x - self.mu0) - slack)
        stat = self.statistic
        if stat <= self.h * self.sigma0:
            return False
        rule = "cusum_up" if self._c_up >= self._c_down else "cusum_down"
        self._log.entries.append(TraceEntry(obs.period, rule, stat))
        return True


@dataclass(slots=True)
class PageHinkley:
    """Two-sided Page-Hinkley against a frozen null mean.

    ``U += x - mu0 - delta``; ``PH_up = U - min U``; ``L += x - mu0 + delta``;
    ``PH_down = max L - L``; fire when ``max(PH_up, PH_down) > threshold``. With the null mean
    frozen this is CUSUM-with-min (research notes §2); the two co-exist because their
    calibration histories differ — ``threshold`` is set from the null max-statistic
    distribution, not from CUSUM's ``h * sigma0``.
    """

    mu0: float
    sigma0: float
    delta: float
    threshold: float
    _u: float = field(default=0.0, repr=False)
    _min_u: float = field(default=0.0, repr=False)
    _l: float = field(default=0.0, repr=False)
    _max_l: float = field(default=0.0, repr=False)
    _log: _TraceLog = field(default_factory=_TraceLog, repr=False)

    def __post_init__(self) -> None:
        if self.sigma0 <= 0:
            raise ValueError(f"sigma0 must be positive, got {self.sigma0}")
        if self.delta <= 0 or self.threshold <= 0:
            raise ValueError(
                f"delta and threshold must be positive, got {self.delta}, {self.threshold}"
            )

    def reset(self) -> None:
        self._log.entries.clear()
        self.reset_accumulators()

    def reset_accumulators(self) -> None:
        self._u = self._min_u = self._l = self._max_l = 0.0

    @property
    def trace(self) -> TriggerTrace:
        return TriggerTrace(tuple(self._log.entries))

    @property
    def statistic(self) -> float:
        return max(self._u - self._min_u, self._max_l - self._l)

    def should_propose(self, obs: PeriodObservation) -> bool:
        x = _demand_at(obs)
        if x is None:
            return False
        self._u += x - self.mu0 - self.delta
        self._min_u = min(self._min_u, self._u)
        self._l += x - self.mu0 + self.delta
        self._max_l = max(self._max_l, self._l)
        stat = self.statistic
        if stat <= self.threshold:
            return False
        up = self._u - self._min_u
        rule = "page_hinkley_up" if up >= self._max_l - self._l else "page_hinkley_down"
        self._log.entries.append(TraceEntry(obs.period, rule, stat))
        return True


@dataclass(slots=True)
class AlertOrDetector:
    """The primary rule: fire on an operational alert or on the wrapped statistic.

    The rule label records *which* channel fired (``alert``, the detector's own rule, or
    ``alert+<rule>`` when both agree in one period), because the trigger-time table separates
    alert-driven from telemetry-driven proposals.
    """

    detector: Cusum | PageHinkley
    _log: _TraceLog = field(default_factory=_TraceLog, repr=False)

    def reset(self) -> None:
        self.detector.reset()
        self._log.entries.clear()

    def reset_accumulators(self) -> None:
        self.detector.reset_accumulators()

    @property
    def trace(self) -> TriggerTrace:
        return TriggerTrace(tuple(self._log.entries))

    def should_propose(self, obs: PeriodObservation) -> bool:
        detector_fired = self.detector.should_propose(obs)
        alerted = obs.alert is not None
        if not (detector_fired or alerted):
            return False
        if detector_fired:
            inner = self.detector.trace.entries[-1]
            rule = f"alert+{inner.rule}" if alerted else inner.rule
            stat = max(1.0, inner.statistic) if alerted else inner.statistic
        else:
            rule, stat = "alert", 1.0
        self._log.entries.append(TraceEntry(obs.period, rule, stat))
        return True


def _check_budget(n: int, horizon: int, min_spacing: int) -> None:
    if n < 0:
        raise ValueError(f"budget must be non-negative, got {n}")
    if min_spacing < 1:
        raise ValueError(f"min_spacing must be >= 1, got {min_spacing}")
    # n points in 1..horizon with pairwise gaps >= min_spacing need
    # horizon >= n + (n-1)*(min_spacing-1); otherwise the schedule cannot be realised under a
    # refractory window of min_spacing - 1, and raising is what keeps "budget-matched" honest.
    if n > 0 and horizon < n + (n - 1) * (min_spacing - 1):
        raise ValueError(
            f"budget {n} cannot be spaced {min_spacing} apart over horizon {horizon}; "
            "the realised count could not match the comparator's"
        )


def _schedule_periods(n: int, horizon: int, min_spacing: int) -> tuple[int, ...]:
    """``n`` evenly spaced firing periods inside ``1..horizon``.

    Even spacing is the default; when even spacing would land closer than ``min_spacing``
    (legal by the feasibility check but tighter than the window), fall back to a centered
    arithmetic placement at exactly ``min_spacing``, so any feasible budget is realisable.
    """
    _check_budget(n, horizon, min_spacing)
    if n == 0:
        return ()
    periods = tuple(i * (horizon + 1) // (n + 1) for i in range(1, n + 1))
    gaps = [b - a for a, b in pairwise(periods)]
    if all(gap >= min_spacing for gap in gaps):
        return periods
    start = max(1, (horizon - (n - 1) * min_spacing) // 2)
    return tuple(start + i * min_spacing for i in range(n))


@dataclass(slots=True)
class PeriodicEveryK:
    """A fixed schedule budget-matched to a comparator's *realised* call count.

    Constructed with :meth:`from_budget` — the realised trace length of the arm it is compared
    against, never an intended count, because wrapper suppression changes the intended count
    (R1.4). ``min_spacing`` enforces the refractory window at construction time so the realised
    count equals the budget exactly; infeasible combinations raise rather than silently
    under-delivering the budget.
    """

    periods: tuple[int, ...]
    _log: _TraceLog = field(default_factory=_TraceLog, repr=False)
    _next: int = field(default=0, repr=False)

    @classmethod
    def from_budget(cls, n: int, horizon: int, *, min_spacing: int = 1) -> PeriodicEveryK:
        return cls(periods=_schedule_periods(n, horizon, min_spacing))

    def reset(self) -> None:
        self._log.entries.clear()
        self._next = 0

    def reset_accumulators(self) -> None:
        return None

    @property
    def trace(self) -> TriggerTrace:
        return TriggerTrace(tuple(self._log.entries))

    def should_propose(self, obs: PeriodObservation) -> bool:
        if self._next >= len(self.periods) or obs.period != self.periods[self._next]:
            return False
        self._next += 1
        self._log.entries.append(TraceEntry(obs.period, "periodic", 1.0))
        return True


@dataclass(slots=True)
class RandomMatched:
    """A seeded random schedule, budget-matched like :class:`PeriodicEveryK`.

    Answers "does the *timing* of calls matter, or only the number?" against the primary rule.
    Seeded with an explicit ``numpy`` PCG64 generator — never global state (NEP 19, research
    notes §5 of module 01).
    """

    periods: tuple[int, ...]
    _log: _TraceLog = field(default_factory=_TraceLog, repr=False)
    _next: int = field(default=0, repr=False)

    @classmethod
    def from_budget(cls, n: int, horizon: int, *, seed: int, min_spacing: int = 1) -> RandomMatched:
        _check_budget(n, horizon, min_spacing)
        if n == 0:
            return cls(periods=())
        rng = np.random.Generator(np.random.PCG64(seed))
        # Spaced sampling without rejection: choose n distinct ranks q_i from the contracted
        # range [1, H - (n-1)(s-1)], then expand p_i = q_i + (i-1)(s-1). Uniform over
        # gap-respecting subsets and exact, so the schedule never needs a second draw.
        contracted = horizon - (n - 1) * (min_spacing - 1)
        chosen = sorted(int(q) for q in rng.choice(contracted, size=n, replace=False) + 1)
        periods = tuple(q + i * (min_spacing - 1) for i, q in enumerate(chosen))
        return cls(periods=periods)

    def reset(self) -> None:
        self._log.entries.clear()
        self._next = 0

    def reset_accumulators(self) -> None:
        return None

    @property
    def trace(self) -> TriggerTrace:
        return TriggerTrace(tuple(self._log.entries))

    def should_propose(self, obs: PeriodObservation) -> bool:
        if self._next >= len(self.periods) or obs.period != self.periods[self._next]:
            return False
        self._next += 1
        self._log.entries.append(TraceEntry(obs.period, "random", 1.0))
        return True


def main(argv: list[str] | None = None) -> None:
    """CLI entry. The demo itself lives in :mod:`collie.trigger.demo`."""
    parser = argparse.ArgumentParser(prog="python -m collie.trigger.detectors")
    parser.add_argument("--trigger-table", action="store_true", help="print the trigger-time table")
    parser.add_argument("--episodes", type=int, default=12)
    args = parser.parse_args(argv)
    if args.trigger_table:
        from collie.trigger.demo import trigger_table

        print(trigger_table(args.episodes))
    else:  # pragma: no cover - CLI guard
        parser.error("nothing to do: pass --trigger-table")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
