"""A numerically stable discrete-mixture likelihood-ratio e-process.

The mixture is outside the product: every component maintains its own cumulative likelihood
ratio, then the fixed prior averages component wealth.  Multiplying period-wise mixture averages
would define a different process and would not implement the derivation note.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "ANYTIME_VALID",
    "NO_FINITE_SAMPLE_GUARANTEE",
    "EProcessPoint",
    "MixtureEProcess",
]


ANYTIME_VALID = "anytime_valid"
NO_FINITE_SAMPLE_GUARANTEE = "no_finite_sample_guarantee"


def _logsumexp(values: Sequence[float]) -> float:
    largest = max(values)
    if largest == -math.inf:
        return -math.inf
    if largest == math.inf:
        return math.inf
    return largest + math.log(math.fsum(math.exp(value - largest) for value in values))


@dataclass(frozen=True, slots=True)
class EProcessPoint:
    """One auditable point on an evidence path."""

    period: int
    e_value: float
    threshold: float
    activated: bool
    activation_period: int | None
    validity_label: str


@dataclass(slots=True)
class MixtureEProcess:
    """Discrete mixture of component likelihood-ratio test martingales."""

    tau_j: int
    alpha_j: float
    weights: tuple[float, ...]
    validity_label: str = ANYTIME_VALID
    _log_wealth: list[float] = field(init=False, repr=False)
    _log_weights: tuple[float, ...] = field(init=False, repr=False)
    _last_period: int = field(init=False, repr=False)
    _activation_period: int | None = field(default=None, init=False, repr=False)
    _trace: list[EProcessPoint] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.tau_j < 0:
            raise ValueError(f"tau_j must be non-negative, got {self.tau_j}")
        if not 0.0 < self.alpha_j < 1.0:
            raise ValueError(f"alpha_j must lie in (0, 1), got {self.alpha_j}")
        if not self.weights:
            raise ValueError("a mixture needs at least one component")
        if any(not math.isfinite(weight) or weight <= 0.0 for weight in self.weights):
            raise ValueError(f"mixture weights must be finite and positive, got {self.weights}")
        total = math.fsum(self.weights)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"mixture weights must sum to one, got {total}")
        self._log_weights = tuple(math.log(weight) for weight in self.weights)
        self._log_wealth = [0.0] * len(self.weights)
        self._last_period = self.tau_j

    @property
    def threshold(self) -> float:
        return 1.0 / self.alpha_j

    @property
    def log_e_value(self) -> float:
        return _logsumexp(
            tuple(
                weight + wealth
                for weight, wealth in zip(self._log_weights, self._log_wealth, strict=True)
            )
        )

    @property
    def e_value(self) -> float:
        value = self.log_e_value
        return (
            math.exp(value)
            if value < math.log(float.fromhex("0x1.fffffffffffffp+1023"))
            else math.inf
        )

    @property
    def activated(self) -> bool:
        return self._activation_period is not None

    @property
    def activation_period(self) -> int | None:
        return self._activation_period

    @property
    def trace(self) -> tuple[EProcessPoint, ...]:
        return tuple(self._trace)

    def update(self, period: int, log_likelihood_ratios: Sequence[float]) -> EProcessPoint:
        """Consume exactly one strictly post-proposal observation.

        ``log_likelihood_ratios[k]`` is the current observation's log alternative/null ratio for
        mixture component ``k``.  Passing log ratios keeps long episodes away from underflow.
        """
        if period <= self.tau_j:
            raise ValueError(
                f"future-only violation: period {period} is not strictly after tau_j={self.tau_j}"
            )
        if period <= self._last_period:
            raise ValueError(
                f"evidence periods must increase strictly: got {period} after {self._last_period}"
            )
        if len(log_likelihood_ratios) != len(self.weights):
            raise ValueError(
                f"expected {len(self.weights)} component ratios, got {len(log_likelihood_ratios)}"
            )
        if any(math.isnan(value) or value == math.inf for value in log_likelihood_ratios):
            raise ValueError("log likelihood ratios may be finite or -inf, never nan or +inf")

        for index, increment in enumerate(log_likelihood_ratios):
            self._log_wealth[index] += increment
        self._last_period = period

        if self._activation_period is None and self.log_e_value >= math.log(self.threshold):
            self._activation_period = period
        point = EProcessPoint(
            period=period,
            e_value=self.e_value,
            threshold=self.threshold,
            activated=self.activated,
            activation_period=self._activation_period,
            validity_label=self.validity_label,
        )
        self._trace.append(point)
        return point
