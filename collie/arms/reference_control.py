"""TEMPORARY stand-in for module 04. Delete when collie/control/ lands.

A minimal ShockSpec -> ControlConfig mapping and a ControlConfig-parameterised capped
base-stock controller, sufficient to run the arm ladder end to end on dev episodes.
No arm may import this module: every arm takes its compiler and controller by injection,
and tests/conftest.py wires this in. Module 04's real implementation drops in unchanged.

Two properties make the stand-in safe to build against:

* :func:`baseline_config` reproduces arm 1 exactly — a differential test over random demand
  streams pins :class:`ReferenceController` at the baseline config to
  :class:`~collie.arms.base_stock.CappedBaseStockController`, so "baseline OR runs while
  PROPOSED" is literally true for arms 8-10.
* The compiler's mapping is a documented placeholder, not a hypothesis about module 04's
  72-point grid: it exists so the dev demo exercises the compile -> control path, and every
  choice it makes is marked provisional in :meth:`ReferenceCompiler.compile`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm

from collie.contracts import (
    ControlConfig,
    Decision,
    Direction,
    PeriodObservation,
    Persistence,
    ShockSpec,
    TargetStream,
)

__all__ = [
    "ReferenceCompiler",
    "ReferenceController",
    "baseline_config",
]

_BASELINE_MODEL = "running"
"""The estimator key corresponding to arm 1: running mean/std over train + observed demand."""

_EWMA_MODEL = "ewma"
"""The stand-in's only alternative: EWMA-smoothed mean with weight ``gamma``."""


def baseline_config(promised_lead_time: int) -> ControlConfig:
    """The config under which :class:`ReferenceController` reproduces arm 1 bit for bit."""
    return ControlConfig(
        m=1.0,
        l_eff=promised_lead_time,
        gamma=1.0,  # unused by the running estimator; carried so the field is never undefined
        predictive_model=_BASELINE_MODEL,
    )


@dataclass(frozen=True, slots=True)
class ReferenceCompiler:
    """Placeholder ShockSpec -> ControlConfig mapping. Module 04 owns the real grid.

    Mapping (provisional, chosen only so the dev demo shows the path working):

    * demand up -> ``m`` scaled by 1.5; demand down -> ``m`` scaled by 0.5
      (a demand-level hypothesis moves the safety-stock multiplier);
    * arrival-stream disruption -> ``l_eff + 1`` (a supply hypothesis lengthens the pipeline the
      target covers);
    * persistent persistence -> the ``ewma`` estimator with ``gamma = 0.3`` (slow adaptation to
      a claimed new regime); anything else leaves the estimator untouched;
    * abstentions (``target_stream == "none"``) compile to the current config unchanged.
    """

    def compile(self, spec: ShockSpec, *, current: ControlConfig) -> ControlConfig:
        if spec.target_stream is TargetStream.NONE:
            return current
        m, l_eff = current.m, current.l_eff
        if spec.direction is Direction.DEMAND_UP:
            m *= 1.5
        elif spec.direction is Direction.DEMAND_DOWN:
            m *= 0.5
        if spec.target_stream is TargetStream.ARRIVAL:
            l_eff += 1
        model, gamma = current.predictive_model, current.gamma
        if spec.persistence is Persistence.PERSISTENT:
            model, gamma = _EWMA_MODEL, 0.3
        return ControlConfig(m=m, l_eff=l_eff, gamma=gamma, predictive_model=model)


@dataclass(slots=True)
class ReferenceController:
    """A ControlConfig-parameterised capped base stock. Implements ``Controller``.

    Arm 1's math with the lead time, safety-stock multiplier, and estimator read from the
    config instead of hard-wired. Same record-then-decide discipline and the same
    uncensored-demand refusal as arm 1. The config may be swapped between periods by the
    owning arm (that is the point of the ladder); the demand history is the controller's own
    and is untouched by swaps.
    """

    config: ControlConfig
    train_demand: tuple[float, ...] = ()
    arm_id: str = "reference_control"
    cap_quantile: float = 0.95
    _observed: list[float] = field(default_factory=list, repr=False)

    def reset(self) -> None:
        self._observed = []

    def order(self, obs: PeriodObservation) -> Decision:
        self._record_demand(obs)
        quantity = self._order_quantity(obs)
        return Decision(
            period=obs.period,
            order_quantity=quantity,
            arm_id=self.arm_id,
            control_config=self.config,
        )

    def _order_quantity(self, obs: PeriodObservation) -> float:
        samples = [*self.train_demand, *self._observed]
        if not samples:
            return 0.0
        mean, std = self._estimates()
        l_eff = self.config.l_eff
        mu_hat = (1.0 + l_eff) * mean
        sigma_hat = math.sqrt(1.0 + l_eff) * std
        critical_fractile = obs.profit_per_unit / (obs.profit_per_unit + obs.holding_cost_per_unit)
        z_star = float(norm.ppf(critical_fractile))
        target = mu_hat + self.config.m * z_star * sigma_hat
        uncapped = max(math.ceil(target - (obs.on_hand + obs.in_transit_total)), 0)
        cap = mean + float(norm.ppf(self.cap_quantile)) * std
        return float(max(min(uncapped, math.ceil(cap)), 0))

    def _estimates(self) -> tuple[float, float]:
        samples = [*self.train_demand, *self._observed]
        if self.config.predictive_model == _EWMA_MODEL:
            mean = self._ewma()
        elif self.config.predictive_model == _BASELINE_MODEL:
            mean = float(np.mean(samples))
        else:
            raise ValueError(
                f"unknown predictive_model {self.config.predictive_model!r}; the stand-in "
                f"knows {_BASELINE_MODEL!r} and {_EWMA_MODEL!r}"
            )
        std = float(np.std(samples, ddof=1)) if len(samples) > 1 else 0.0
        return mean, std

    def _ewma(self) -> float:
        """EWMA over train + observed in order, seeded with the first sample."""
        gamma = self.config.gamma
        if not 0.0 < gamma <= 1.0:
            raise ValueError(f"EWMA gamma must be in (0, 1], got {gamma}")
        acc: float | None = None
        for d in [*self.train_demand, *self._observed]:
            acc = d if acc is None else gamma * d + (1.0 - gamma) * acc
        assert acc is not None  # callers guarantee samples is non-empty
        return acc

    def _record_demand(self, obs: PeriodObservation) -> None:
        if obs.period == 1:
            return
        if obs.prev_demand is None:
            raise ValueError(
                f"{self.arm_id!r} is an uncensored-demand policy but observation at period "
                f"{obs.period} carries no prev_demand."
            )
        self._observed.append(obs.prev_demand)
