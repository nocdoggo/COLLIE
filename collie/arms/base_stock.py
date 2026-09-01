"""Arm 1 — capped base-stock, the OR baseline.

This is a faithful reimplementation of the published baseline in
``scripts/run_or.py::ORAgent`` (policy ``capped``), which is the "OR (capped base stock)" entry
scoring **0.4447** overall in the shipped results. Reimplemented rather than wrapped because the
published agent reads its state by parsing a text observation built for a game harness, and arm 1
has to run inside our runner alongside every other arm. Verified against the published
per-instance orders in ``tests/test_arm1_base_stock.py``.

The policy, with ``L`` the **promised** lead time (never the actual one, which no policy observes):

.. math::

    q = \\frac{p}{p + h}, \\quad z^* = \\Phi^{-1}(q)

    \\hat\\mu = (1 + L)\\,\\bar{d}, \\quad \\hat\\sigma = \\sqrt{1 + L}\\,s_d

    S = \\hat\\mu + z^* \\hat\\sigma, \\quad
    a_{\\text{uncapped}} = \\max(0, \\lceil S - (\\text{on hand} + \\text{in transit}) \\rceil)

    a = \\max(0, \\min(a_{\\text{uncapped}}, \\lceil \\text{cap} \\rceil))

``\\bar{d}`` and ``s_d`` are the running mean and sample standard deviation (``ddof=1``) of the
train samples followed by every demand observed so far.

Two things about this policy are worth stating plainly, because both are easy to get wrong.

**The cap is L-independent.** Upstream writes it as
``mu_hat / (1 + L) + Phi^-1(0.95) * sigma_hat / sqrt(1 + L)``, but substituting the definitions of
``mu_hat`` and ``sigma_hat`` cancels every ``L``, leaving ``mean + Phi^-1(0.95) * std`` — one
period of demand at the 95th percentile. Upstream's separate ``L = inf`` branch computes exactly
that same expression, so it is mathematically redundant. We implement the simplified form and
assert the equivalence in tests.

**This cap is not our order cap.** It is a policy-internal order smoother, chosen by the
baseline's authors. The *environment* imposes no cap at all (``docs/env_contract.md`` §2.3), so
``EpisodeSpec.order_cap`` is a separate, project-owned constraint that the runner applies after
the policy has spoken. Conflating the two would misattribute our design choice to the benchmark.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm

from collie.contracts import Decision, PeriodObservation

__all__ = [
    "ARM1_ARM_ID",
    "PUBLISHED_PARAMS",
    "BaseStockParams",
    "CappedBaseStockController",
    "base_stock_order",
]

ARM1_ARM_ID = "arm1_capped_base_stock"


@dataclass(frozen=True, slots=True)
class BaseStockParams:
    """Parameters of the published baseline. The defaults *are* the published configuration."""

    cap_quantile: float = 0.95
    """The order smoother's quantile. Upstream's ``norm.ppf(0.95)``."""
    capped: bool = True
    """``False`` gives upstream's ``vanilla`` policy, which is the uncapped base stock."""
    infinite_lead_time_substitute: float = 1000.0
    """Upstream substitutes this for an infinite promised lead time to avoid a NaN. Never
    triggered by the shipped benchmark, whose promised lead times are 0, 2, or 4; kept so the
    reimplementation is faithful rather than merely adequate."""

    def __post_init__(self) -> None:
        if not 0.0 < self.cap_quantile < 1.0:
            raise ValueError(f"cap_quantile must be in (0, 1), got {self.cap_quantile}")


PUBLISHED_PARAMS = BaseStockParams()
"""The published configuration. A module-level singleton so it can be a safe default argument."""


def base_stock_order(
    *,
    samples: list[float],
    on_hand: float,
    in_transit: float,
    promised_lead_time: float,
    profit_per_unit: float,
    holding_cost_per_unit: float,
    params: BaseStockParams = PUBLISHED_PARAMS,
) -> float:
    """Pure order rule, transcribed from ``ORAgent._calculate_order``.

    ``samples`` is the train history followed by every demand observed so far, in order.
    With no samples at all the policy orders nothing, as upstream does.
    """
    if not samples:
        return 0.0

    empirical_mean = float(np.mean(samples))
    empirical_std = float(np.std(samples, ddof=1)) if len(samples) > 1 else 0.0

    lead_time = (
        params.infinite_lead_time_substitute
        if math.isinf(promised_lead_time)
        else promised_lead_time
    )
    mu_hat = (1.0 + lead_time) * empirical_mean
    sigma_hat = math.sqrt(1.0 + lead_time) * empirical_std

    critical_fractile = profit_per_unit / (profit_per_unit + holding_cost_per_unit)
    z_star = float(norm.ppf(critical_fractile))
    target = mu_hat + z_star * sigma_hat

    uncapped = max(int(np.ceil(target - (on_hand + in_transit))), 0)
    if not params.capped:
        return float(uncapped)

    # mu_hat/(1+L) + z*sigma_hat/sqrt(1+L) == mean + z*std for every L, finite or not.
    cap = empirical_mean + float(norm.ppf(params.cap_quantile)) * empirical_std
    return float(max(min(uncapped, int(np.ceil(cap))), 0))


@dataclass(slots=True)
class CappedBaseStockController:
    """Arm 1. Implements :class:`~collie.contracts.Controller`.

    Holds no hidden state: the demand history it accumulates comes from the observations it was
    given, and the promised lead time is the one the benchmark publishes in the directory name.
    """

    train_demand: tuple[float, ...] = ()
    params: BaseStockParams = field(default_factory=BaseStockParams)
    arm_id: str = ARM1_ARM_ID
    _observed: list[float] = field(default_factory=list, repr=False)

    def reset(self) -> None:
        self._observed = []

    def order(self, obs: PeriodObservation) -> Decision:
        # Record first, then decide. Upstream's demand history at period t already contains every
        # demand through period t-1, so deciding first would leave the estimator one observation
        # short and lag every order by a period.
        self._record_demand(obs)
        quantity = base_stock_order(
            samples=[*self.train_demand, *self._observed],
            on_hand=obs.on_hand,
            in_transit=obs.in_transit_total,
            promised_lead_time=obs.promised_lead_time,
            profit_per_unit=obs.profit_per_unit,
            holding_cost_per_unit=obs.holding_cost_per_unit,
            params=self.params,
        )
        return Decision(period=obs.period, order_quantity=quantity, arm_id=self.arm_id)

    def _record_demand(self, obs: PeriodObservation) -> None:
        """Append the previous period's demand, exactly as upstream updates its history.

        Upstream is an uncensored-demand policy. Running it under
        :attr:`~collie.contracts.ObservationMode.CENSORED` would silently substitute sales for
        demand and quietly bias the estimator downward during every stockout, so it refuses
        instead. A censored-mode estimator is a separate arm, not a flag on this one.
        """
        if obs.period == 1:
            # The reference's pre-loop initialisation, not an observation.
            return
        if obs.prev_demand is None:
            raise ValueError(
                f"{self.arm_id!r} is an uncensored-demand policy but observation at period "
                f"{obs.period} carries no prev_demand. Censored operation needs a purpose-built "
                "estimator, not this arm with sales substituted for demand."
            )
        self._observed.append(obs.prev_demand)
