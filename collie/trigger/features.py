"""Legal online features and the legality denylist.

The value-of-computation gate is deferred this sprint, but the legality machinery it will depend
on is not: anything that turns observation history into decision input — a gate feature builder
now, a classifier later — must be provably unable to see the future or the hidden truth.

Two enforcement mechanisms:

- **Runtime**: :func:`assert_features_legal` validates the keys of any feature mapping.
  :class:`OnlineFeatures` calls it on its own output every call, so an illegal key fails at the
  period it appears, not in a later audit.
- **Static**: ``tests/test_triggers.py`` AST-scans ``collie/trigger/`` for denylisted attribute
  and name usage, in the style of the hidden-state mechanism-2 check in
  ``tests/test_contracts.py``.

The denylist names the categories the standing rules forbid: future demand, benchmark pattern
names, instance and article identifiers, test labels, and every ``incident.json`` field. It is
deliberately over-broad on substrings (``onset``, ``twin``, ``pattern``, ``label``): a legal
feature can always be renamed, while a peeking feature renamed innocuously is how leaks survive
review.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from collie.contracts import PeriodObservation
from collie.trigger.calibration import FROZEN

__all__ = [
    "FEATURE_DENYLIST",
    "FEATURE_DENYLIST_SUBSTRINGS",
    "FeatureLegalityError",
    "OnlineFeatures",
    "assert_features_legal",
]


FEATURE_DENYLIST: frozenset[str] = frozenset(
    {
        # future information
        "future_demand",
        "future_arrivals",
        # benchmark pattern names and dataset identity
        "pattern",
        "pattern_name",
        "instance_id",
        "episode_id",
        "article_id",
        "item_id",
        # test labels and split membership
        "split",
        "test_label",
        "label",
        # every incident.json field (the hidden truth, docs/env_contract.md §7)
        "family",
        "onset_period",
        "onset",
        "magnitude",
        "duration",
        "conditional_independence",
        "supply_effect",
        "baseline_twin_id",
        "seed",
        "held_out_combo",
        # alert template identity is analysis-side only (contracts: AlertMessage docstring)
        "template_id",
        "alert_id",
    }
)

FEATURE_DENYLIST_SUBSTRINGS: tuple[str, ...] = (
    "future",
    "pattern",
    "article",
    "incident",
    "template",
    "hidden",
    "onset",
    "twin",
    "family",
    "label",
    "split",
    "seed",
)
"""Case-insensitive fragments that make ANY key containing them illegal. Over-broad on purpose:
``demand_seed`` and ``onset_gap`` are not legal features with innocuous names."""


class FeatureLegalityError(ValueError):
    """Raised when a feature mapping carries a denylisted key."""


def assert_features_legal(keys: Iterable[str]) -> None:
    """Raise :class:`FeatureLegalityError` if any key names or contains forbidden information."""
    bad: list[str] = []
    for key in keys:
        normalised = key.strip().lower()
        if normalised in FEATURE_DENYLIST:
            bad.append(f"{key!r} is a denylisted key")
        elif any(fragment in normalised for fragment in FEATURE_DENYLIST_SUBSTRINGS):
            bad.append(f"{key!r} contains a denylisted fragment")
    if bad:
        raise FeatureLegalityError(
            "illegal feature keys: "
            + "; ".join(bad)
            + ". The denylist forbids future demand, benchmark pattern names, instance/article "
            "identifiers, test labels, and incident fields."
        )


@dataclass(slots=True)
class OnlineFeatures:
    """The legal feature view: a stateful builder fed one observation per period.

    Every emitted key is either a verbatim field of :class:`PeriodObservation` or a statistic of
    demands *already observed* (running mean/sd over ``t-1`` and earlier, residuals against
    them). Period 1's ``prev_demand`` is the reference's pre-loop initialisation, not a
    measurement, so it never enters the demand statistics (``n_demand_obs`` stays 0 there).

    The output validates itself against the denylist on every call: a future maintainer adding an
    illegal key breaks the build at the first update, inside the episode, with the period named.
    """

    mu0: float = FROZEN.mu0
    """The registered stationary-law mean — the residual anchor. Defaults to the frozen
    calibration, never a literal, so a re-calibration moves this feature with everything else."""
    _demands: list[float] = field(default_factory=list, repr=False)

    def reset(self) -> None:
        self._demands.clear()

    def update(self, obs: PeriodObservation) -> dict[str, float]:
        if obs.period > 1 and obs.prev_demand is not None:
            self._demands.append(obs.prev_demand)
        n = len(self._demands)
        mean = sum(self._demands) / n if n else 0.0
        sd = (sum((d - mean) ** 2 for d in self._demands) / (n - 1)) ** 0.5 if n > 1 else 0.0
        last = self._demands[-1] if n else 0.0
        features = {
            "period": float(obs.period),
            "on_hand": obs.on_hand,
            "in_transit_total": obs.in_transit_total,
            "prev_order": obs.prev_order,
            "prev_arrivals": obs.prev_arrivals,
            "profit_per_unit": obs.profit_per_unit,
            "holding_cost_per_unit": obs.holding_cost_per_unit,
            "promised_lead_time": float(obs.promised_lead_time),
            "critical_fractile": obs.profit_per_unit
            / (obs.profit_per_unit + obs.holding_cost_per_unit),
            "n_demand_obs": float(n),
            "demand_mean": mean,
            "demand_sd": sd,
            "demand_last": last,
            "demand_residual_vs_running_mean": last - mean if n else 0.0,
            "demand_residual_vs_registered_null": last - self.mu0 if n else 0.0,
            "alert_arrived": 1.0 if obs.alert is not None else 0.0,
        }
        try:
            assert_features_legal(features)
        except FeatureLegalityError as exc:
            raise FeatureLegalityError(f"period {obs.period}: {exc}") from exc
        return features
