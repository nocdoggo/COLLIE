"""Capped base-stock controller, parameterised by :class:`~collie.contracts.ControlConfig`.

Every arm that routes through the OR compiler — the detector control, the parsing upper bound,
the oracle, and all three ShockSpec arms — uses exactly this class. They differ only in *which*
``ControlConfig`` is active on a given period, never in what happens once one is chosen. That is
the property ``test_shared_control_path_byte_identical`` in ``tests/test_controller.py`` checks,
and it is what makes a profit difference between arms attributable to the hypothesis rather than
to the plumbing around it.

::

    IP_t = I_t + gamma * P_t
    S_t  = base_stock(m, l_eff, forecast, critical_fractile)
    q_t  = min(max(0, S_t - IP_t), C_t)

``l_eff`` is a *compiled belief*, never the observation's ``promised_lead_time``. The compiler
(``mapping.py``) is a pure function of the ``ShockSpec`` alone with no episode in front of it, so
there is nothing per-episode for it to read; the base-stock target is built entirely from the
registered grid point. This is a deliberate difference from arm 1, which legitimately reads
``promised_lead_time`` because it is not testing a hypothesis about it.

``order_cap`` is ``C_t``: read from the environment contract at construction time (the caller
passes the loaded instance's ``spec.order_cap``) and never a literal in this module
(``test_cap_comes_from_the_contract``). The runner also clamps with the same cap
(``collie/sim/accounting.py::clamp_order``) after any controller speaks; the controller clamping
too is what makes ``0 <= q_t <= C_t`` a property of this class in isolation, not just of the
runner wrapped around it.

**Age-binned telemetry** (``ledger`` below) is an *ablation flag*, never a per-arm feature: any
``OrCompilerController``, regardless of ``arm_id``, records identically into whatever
:class:`~collie.control.ledger.FIFOLedger` its caller attaches. Handing a richer, ledger-derived
observation to one arm and not another would let an apparent hypothesis-driven profit advantage
actually come from the observation being richer — a confound the harness (module 06) must not
introduce (``docs/implementation/04-or-compiler.md``, Checkpoint 2). The order rule itself never
reads the ledger back; it only feeds it, so attaching one changes what telemetry is available
after the fact and never changes an order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from scipy.stats import norm

from collie.contracts import ControlConfig, Decision, PeriodObservation
from collie.control.forecast import DemandForecaster
from collie.control.ledger import FIFOLedger

__all__ = ["OrCompilerController", "base_stock_target", "critical_fractile"]


def critical_fractile(profit_per_unit: float, holding_cost_per_unit: float) -> float:
    """``p / (p + h)``, read from the per-period cost columns every period rather than assumed
    constant, because the benchmark carries them as columns even though they are constant within
    any one shipped instance."""
    return profit_per_unit / (profit_per_unit + holding_cost_per_unit)


def base_stock_target(config: ControlConfig, *, mean: float, std: float, fractile: float) -> float:
    """``S_t``: the compiled base-stock target. Pure arithmetic, no episode state.

    Structurally the same shape as arm 1's uncapped target (``mu_hat + z* sigma_hat`` with
    ``mu_hat = (1+L)*mean``, ``sigma_hat = sqrt(1+L)*std``), with ``config.l_eff`` standing in for
    ``L`` and ``config.m`` scaling the demand level the compiler believes is in force.
    """
    mu_hat = config.m * (1.0 + config.l_eff) * mean
    sigma_hat = math.sqrt(1.0 + config.l_eff) * std
    z_star = float(norm.ppf(fractile))
    return mu_hat + z_star * sigma_hat


@dataclass(slots=True)
class OrCompilerController:
    """The one controller every OR-compiler arm shares.

    ``config`` is fixed for the life of the controller; an arm whose active config changes over
    the episode (e.g. a lifecycle-gated ShockSpec arm reverting to baseline once refuted) wraps
    this class and swaps ``config`` between periods rather than subclassing the order rule
    itself — the order rule must never know why a config changed, only what it is.
    """

    order_cap: float
    config: ControlConfig
    arm_id: str = "or_compiler"
    train_demand: tuple[float, ...] = ()
    ledger: FIFOLedger | None = None
    """``None`` by default (the ablation is off). When attached, every arm wrapping this class
    records into it identically; see the module docstring."""
    _forecaster: DemandForecaster = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.order_cap < 0:
            raise ValueError(f"order_cap must be non-negative, got {self.order_cap}")
        self._forecaster = DemandForecaster(train_demand=self.train_demand)

    def reset(self) -> None:
        self._forecaster.reset()

    def order(self, obs: PeriodObservation) -> Decision:
        # Record first, decide second: the estimator at period t must have already seen t-1's
        # demand (docs/env_contract.md §8.5), matching arm 1's convention exactly.
        self._forecaster.record(obs.prev_demand)
        if self.ledger is not None and obs.period > 1:
            self.ledger.record_receipt(obs.period, obs.prev_arrivals)
        stats = self._forecaster.stats()
        fractile = critical_fractile(obs.profit_per_unit, obs.holding_cost_per_unit)
        target = base_stock_target(self.config, mean=stats.mean, std=stats.std, fractile=fractile)
        position = obs.on_hand + self.config.gamma * obs.in_transit_total
        quantity = min(max(0.0, target - position), self.order_cap)
        if self.ledger is not None:
            self.ledger.record_order(obs.period, quantity)
        return Decision(
            period=obs.period,
            order_quantity=quantity,
            arm_id=self.arm_id,
            control_config=self.config,
        )
