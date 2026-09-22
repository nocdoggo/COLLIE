"""The frozen forecast estimator, shared by every arm that routes through the OR compiler.

Plain mean and sample standard deviation over observed demand history — deliberately the same
estimator arm 1 uses (``collie/arms/base_stock.py``), frozen at the method freeze, so a profit
difference between arms can never be attributed to a better forecaster. The comparison this
project makes is about hypotheses, not estimators.

One convention carried over from arm 1 and easy to get backwards: the estimator has already seen
period ``t - 1``'s demand when it decides at ``t``. Recording after deciding lags the whole order
sequence by a period — invisible in an aggregate score, obvious at order level
(``docs/env_contract.md`` §8.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["DemandForecaster", "ForecastStats", "forecast_stats"]


@dataclass(frozen=True, slots=True)
class ForecastStats:
    mean: float
    std: float


def forecast_stats(samples: list[float]) -> ForecastStats:
    """Pure function of a sample history. No samples at all gives a zero forecast, matching
    arm 1's convention of ordering nothing until it has seen something."""
    if not samples:
        return ForecastStats(mean=0.0, std=0.0)
    mean = float(np.mean(samples))
    std = float(np.std(samples, ddof=1)) if len(samples) > 1 else 0.0
    return ForecastStats(mean=mean, std=std)


@dataclass(slots=True)
class DemandForecaster:
    """Accumulates observed demand and reports the frozen mean/std estimator.

    Holds no hidden state: everything it accumulates comes from ``prev_demand`` on the
    observations a controller was legitimately handed.
    """

    train_demand: tuple[float, ...] = ()
    _observed: list[float] = field(default_factory=list, repr=False)

    def reset(self) -> None:
        self._observed = []

    def record(self, prev_demand: float | None) -> None:
        """Append one realized demand value. Called once per period, before deciding."""
        if prev_demand is not None:
            self._observed.append(prev_demand)

    def stats(self) -> ForecastStats:
        return forecast_stats([*self.train_demand, *self._observed])
