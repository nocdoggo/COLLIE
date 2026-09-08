"""Demand-side likelihood-ratio e-processes for registered ShockSpec alternatives.

The theorem-backed path uses the parameters supplied by ``BaselineSpec``.  The optional plug-in
path re-estimates a Gaussian null from the online history and is permanently labelled as carrying
no finite-sample guarantee.
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.special import gammaln, log_ndtr, logsumexp

from collie.contracts import Direction, ShockFamily, ShockSpec, TargetStream, assert_no_hidden_state
from collie.data.families.base import BaselineKind, BaselineSpec, as_demand_cells, draw_baseline
from collie.data.families.demand import MAGNITUDE_SETS, PULSE_DURATION
from collie.verify.alpha import alpha_for_proposal
from collie.verify.eprocess import (
    ANYTIME_VALID,
    NO_FINITE_SAMPLE_GUARANTEE,
    EProcessPoint,
    MixtureEProcess,
)
from collie.verify.registry import resolve_spec_shape

__all__ = [
    "CalibrationSummary",
    "DemandEProcess",
    "RegisteredDemandLaw",
    "run_null_calibration",
]


def _logdiffexp(larger: float, smaller: float) -> float:
    """Return ``log(exp(larger) - exp(smaller))`` for ordered log values."""
    if smaller == -math.inf:
        return larger
    if not larger > smaller:
        return -math.inf
    return larger + math.log1p(-math.exp(smaller - larger))


def _log_rounded_normal_mass(value: float, mean: float, sd: float) -> float:
    """Exact mass after the generator's half-up rounding and clipping at zero."""
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
        return -math.inf
    if sd <= 0.0 or not math.isfinite(sd):
        raise ValueError(f"normal standard deviation must be finite and positive, got {sd}")
    if numeric == 0.0:
        return float(log_ndtr((0.5 - mean) / sd))

    lo = (numeric - 0.5 - mean) / sd
    hi = (numeric + 0.5 - mean) / sd
    if lo >= 0.0:
        # In the right tail subtract survival functions; subtracting two CDFs would cancel.
        return _logdiffexp(float(log_ndtr(-lo)), float(log_ndtr(-hi)))
    return _logdiffexp(float(log_ndtr(hi)), float(log_ndtr(lo)))


@dataclass(frozen=True, slots=True)
class RegisteredDemandLaw:
    """One auditable conditional demand law used as a null or mixture component."""

    baseline: BaselineSpec
    multiplier: float = 1.0
    active_from: int | None = None
    active_duration: int | None = None
    plug_in: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.multiplier) or self.multiplier <= 0.0:
            raise ValueError(f"multiplier must be finite and positive, got {self.multiplier}")
        if self.active_duration is not None and self.active_duration < 1:
            raise ValueError(f"active_duration must be positive, got {self.active_duration}")

    @property
    def theorem_backed(self) -> bool:
        # The rounded AR(1) observable needs a latent-state filter not specified by the current
        # contract.  Keeping it out of the formal path is more honest than treating the last
        # rounded observation as the latent state.
        return not self.plug_in and self.baseline.kind is not BaselineKind.DEPENDENT

    def _active(self, period: int) -> bool:
        if self.active_from is None or period < self.active_from:
            return False
        if self.active_duration is None:
            return True
        return period < self.active_from + self.active_duration

    def _mean_sd(self, period: int, history: Sequence[float]) -> tuple[float, float]:
        spec = self.baseline
        if self.plug_in and len(history) >= 2:
            values = np.asarray(history, dtype=float)
            return float(values.mean()), max(float(values.std(ddof=1)), 1e-6)
        if spec.kind is BaselineKind.SEASONAL:
            angle = 2.0 * math.pi * (period - 1) / spec.seasonal_period
            return spec.mean + spec.seasonal_amplitude * math.sin(angle), spec.sd
        if spec.kind is BaselineKind.DEPENDENT:
            previous = history[-1] if history else spec.mean
            return spec.mean + spec.ar_phi * (previous - spec.mean), spec.sd
        return spec.mean, spec.sd

    def _base_log_pmf(self, value: float, *, period: int, history: Sequence[float]) -> float:
        mean, sd = self._mean_sd(period, history)
        if self.baseline.kind is BaselineKind.OVERDISPERSED and not self.plug_in:
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
                return -math.inf
            baseline_var = self.baseline.sd**2
            if baseline_var <= self.baseline.mean:
                raise ValueError("registered overdispersed law requires variance greater than mean")
            shape = self.baseline.mean**2 / (baseline_var - self.baseline.mean)
            probability = shape / (shape + mean)
            return float(
                gammaln(numeric + shape)
                - gammaln(shape)
                - gammaln(numeric + 1.0)
                + shape * math.log(probability)
                + numeric * math.log1p(-probability)
            )
        return _log_rounded_normal_mass(value, mean, sd)

    def log_pmf(self, value: float, *, period: int, history: Sequence[float]) -> float:
        """Log mass of the exact exposed integer-valued observable for this kernel.

        Module 01 shocks an already rounded/clipped baseline cell ``X`` and exposes
        ``floor(multiplier * X + 0.5)``. Summing the baseline masses over that integer map's
        preimage matches the generator exactly; merely shifting a Gaussian mean would not.
        """
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
            return -math.inf
        if not self._active(period) or self.multiplier == 1.0:
            return self._base_log_pmf(numeric, period=period, history=history)

        lower = max(0, math.ceil((numeric - 0.5) / self.multiplier))
        upper = math.ceil((numeric + 0.5) / self.multiplier) - 1
        if upper < lower:
            return -math.inf
        return float(
            logsumexp(
                [
                    self._base_log_pmf(source, period=period, history=history)
                    for source in range(lower, upper + 1)
                ]
            )
        )


@dataclass(frozen=True, slots=True)
class DemandEProcess:
    """Demand observation adapter around the shared discrete-mixture e-process."""

    null: RegisteredDemandLaw
    alternatives: tuple[RegisteredDemandLaw, ...]
    tau_j: int
    alpha_j: float
    history_before_proposal: tuple[float, ...] = ()
    _engine: MixtureEProcess = field(init=False, repr=False)
    _history: list[float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        assert_no_hidden_state(
            (self.null, self.alternatives, self.history_before_proposal),
            context="demand verifier inputs",
        )
        if not self.alternatives:
            raise ValueError("a demand e-process needs at least one registered alternative")
        weight = 1.0 / len(self.alternatives)
        validity = ANYTIME_VALID if self.null.theorem_backed else NO_FINITE_SAMPLE_GUARANTEE
        object.__setattr__(
            self,
            "_engine",
            MixtureEProcess(
                tau_j=self.tau_j,
                alpha_j=self.alpha_j,
                weights=(weight,) * len(self.alternatives),
                validity_label=validity,
            ),
        )
        object.__setattr__(self, "_history", list(self.history_before_proposal))

    @classmethod
    def for_level_change(
        cls,
        *,
        baseline: BaselineSpec,
        direction: Direction,
        tau_j: int,
        alpha_episode: float,
        proposal_index: int = 1,
        onset_window: tuple[int, int] = (0, 0),
        history_before_proposal: Sequence[float] = (),
        plug_in: bool = False,
    ) -> DemandEProcess:
        if direction is Direction.DEMAND_UP:
            multipliers = MAGNITUDE_SETS[1]
        elif direction is Direction.DEMAND_DOWN:
            multipliers = MAGNITUDE_SETS[2]
        else:
            raise ValueError(f"demand level construction cannot use direction {direction}")
        starts = tuple(tau_j + offset for offset in range(onset_window[0], onset_window[1] + 1))
        alternatives = tuple(
            RegisteredDemandLaw(
                baseline,
                multiplier=multiplier,
                active_from=start,
                plug_in=plug_in,
            )
            for multiplier in multipliers
            for start in starts
        )
        allocation = alpha_for_proposal(alpha_episode, proposal_index)
        return cls(
            null=RegisteredDemandLaw(baseline, plug_in=plug_in),
            alternatives=alternatives,
            tau_j=tau_j,
            alpha_j=allocation.alpha_j,
            history_before_proposal=tuple(history_before_proposal),
        )

    @classmethod
    def from_spec(
        cls,
        spec: ShockSpec,
        *,
        baseline: BaselineSpec,
        alpha_episode: float,
        history_before_proposal: Sequence[float] = (),
        plug_in: bool = False,
    ) -> DemandEProcess:
        """Compile a legal demand ShockSpec into its fixed discrete mixture."""
        construction = resolve_spec_shape(spec.shock_family, spec.prospective_signature)
        if (
            construction.stream is not TargetStream.DEMAND
            or spec.target_stream is not TargetStream.DEMAND
        ):
            raise ValueError(
                "demand verifier cannot consume registered stream "
                f"{construction.stream} with spec stream {spec.target_stream}"
            )
        if spec.direction is not construction.direction:
            raise ValueError(
                f"direction {spec.direction} does not match registered signature "
                f"{spec.prospective_signature!r}"
            )
        if spec.onset_window is None:
            raise ValueError("a non-abstaining demand spec needs an onset window")
        if spec.shock_family is ShockFamily.DEMAND_LEVEL:
            return cls.for_level_change(
                baseline=baseline,
                direction=spec.direction,
                tau_j=spec.tau_j,
                alpha_episode=alpha_episode,
                proposal_index=spec.proposal_index,
                onset_window=spec.onset_window,
                history_before_proposal=history_before_proposal,
                plug_in=plug_in,
            )
        if spec.shock_family is not ShockFamily.TEMPORARY_PULSE:
            raise ValueError(f"unsupported demand shock family {spec.shock_family}")

        starts = tuple(
            spec.tau_j + offset for offset in range(spec.onset_window[0], spec.onset_window[1] + 1)
        )
        alternatives = tuple(
            RegisteredDemandLaw(
                baseline,
                multiplier=multiplier,
                active_from=start,
                active_duration=duration,
                plug_in=plug_in,
            )
            for multiplier in MAGNITUDE_SETS[3]
            for start in starts
            for duration in range(PULSE_DURATION[0], PULSE_DURATION[1] + 1)
        )
        allocation = alpha_for_proposal(alpha_episode, spec.proposal_index)
        return cls(
            null=RegisteredDemandLaw(baseline, plug_in=plug_in),
            alternatives=alternatives,
            tau_j=spec.tau_j,
            alpha_j=allocation.alpha_j,
            history_before_proposal=tuple(history_before_proposal),
        )

    @property
    def e_value(self) -> float:
        return self._engine.e_value

    @property
    def activated(self) -> bool:
        return self._engine.activated

    @property
    def activation_period(self) -> int | None:
        return self._engine.activation_period

    @property
    def trace(self) -> tuple[EProcessPoint, ...]:
        return self._engine.trace

    @property
    def validity_label(self) -> str:
        return self._engine.validity_label

    def observe(self, period: int, value: float) -> EProcessPoint:
        # Reject the post-selection boundary before even evaluating a density.  The shared engine
        # repeats this guard so direct users receive the same protection.
        if period <= self.tau_j:
            raise ValueError(
                f"future-only violation: period {period} is not strictly after tau_j={self.tau_j}"
            )
        log_null = self.null.log_pmf(value, period=period, history=self._history)
        if log_null == -math.inf:
            raise ValueError(
                f"registered null assigns zero mass to demand {value} at period {period}"
            )
        ratios = tuple(
            alternative.log_pmf(value, period=period, history=self._history) - log_null
            for alternative in self.alternatives
        )
        point = self._engine.update(period, ratios)
        self._history.append(value)
        return point


@dataclass(frozen=True, slots=True)
class CalibrationSummary:
    baseline_kind: BaselineKind
    replications: int
    activations: int
    alpha_episode: float
    proposal_alpha: float
    validity_label: str
    rate: float
    wilson_low: float
    wilson_high: float


def _wilson_interval(
    successes: int, trials: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    if trials < 1:
        raise ValueError("trials must be positive")
    proportion = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    centre = (proportion + z2 / (2.0 * trials)) / denominator
    half = z * math.sqrt(proportion * (1.0 - proportion) / trials + z2 / (4.0 * trials**2))
    half /= denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def run_null_calibration(
    *,
    replications: int,
    alpha_episode: float,
    horizon: int,
    tau_j: int,
    seed: int,
    baseline: BaselineSpec | None = None,
) -> CalibrationSummary:
    """Reduced Monte Carlo calibration under one registered demand null.

    The dependent rounded AR(1) row is deliberately retained as an empirical-only diagnostic so
    every registered uncensored null is exercised without implying an unavailable theorem.
    """
    if replications < 1:
        raise ValueError("replications must be positive")
    if not 0 <= tau_j < horizon:
        raise ValueError(f"tau_j must lie in [0, horizon), got {tau_j} for horizon {horizon}")
    baseline = baseline if baseline is not None else BaselineSpec(BaselineKind.STATIONARY_IID)
    rng = np.random.default_rng(seed)
    activations = 0
    for _ in range(replications):
        observations = draw_baseline(rng, baseline, horizon)
        verifier = DemandEProcess.for_level_change(
            baseline=baseline,
            direction=Direction.DEMAND_UP,
            tau_j=tau_j,
            alpha_episode=alpha_episode,
            history_before_proposal=observations[:tau_j],
        )
        for period, value in enumerate(observations[tau_j:], start=tau_j + 1):
            verifier.observe(period, value)
            if verifier.activated:
                activations += 1
                break
    low, high = _wilson_interval(activations, replications)
    proposal_alpha = alpha_for_proposal(alpha_episode, 1).alpha_j
    return CalibrationSummary(
        baseline_kind=baseline.kind,
        replications=replications,
        activations=activations,
        alpha_episode=alpha_episode,
        proposal_alpha=proposal_alpha,
        validity_label=(
            ANYTIME_VALID
            if baseline.kind is not BaselineKind.DEPENDENT
            else NO_FINITE_SAMPLE_GUARANTEE
        ),
        rate=activations / replications,
        wilson_low=low,
        wilson_high=high,
    )


def _demo(plot: Path | None) -> None:
    baseline = BaselineSpec(BaselineKind.STATIONARY_IID)
    seed = 1
    horizon = 32
    tau_j = 12
    onset = 14
    multiplier = 1.5
    unshocked = draw_baseline(np.random.default_rng(seed), baseline, horizon)
    observations = (
        *unshocked[: onset - 1],
        *as_demand_cells(np.asarray(unshocked[onset - 1 :]) * multiplier),
    )
    verifier = DemandEProcess.for_level_change(
        baseline=baseline,
        direction=Direction.DEMAND_UP,
        tau_j=tau_j,
        alpha_episode=0.05,
        onset_window=(1, 3),
        history_before_proposal=observations[:tau_j],
    )
    print(f"registered episode: seed={seed}, onset={onset}, multiplier={multiplier}, tau_j={tau_j}")
    print(f"{'period':>6} {'demand':>8} {'e_value':>14} {'threshold':>12}  state")
    for period, value in enumerate(observations[tau_j:], start=tau_j + 1):
        point = verifier.observe(period, value)
        state = "active" if point.activated else "proposed"
        print(f"{period:>6} {value:>8.0f} {point.e_value:>14.6f} {point.threshold:>12.3f}  {state}")

    if plot is not None:
        import matplotlib.pyplot as plt

        plot.parent.mkdir(parents=True, exist_ok=True)
        periods = [point.period for point in verifier.trace]
        evidence = [point.e_value for point in verifier.trace]
        figure, axis = plt.subplots(figsize=(7.2, 4.2))
        axis.plot(periods, evidence, marker="o", label="e-process")
        axis.axhline(
            verifier.trace[0].threshold, color="firebrick", linestyle="--", label="1/alpha_j"
        )
        axis.axvline(tau_j, color="slategray", linestyle="-.", label="proposal tau_j")
        if verifier.activation_period is not None:
            axis.axvline(
                verifier.activation_period, color="darkgreen", linestyle=":", label="activation"
            )
        axis.set_yscale("log")
        axis.set_xlabel("period")
        axis.set_ylabel("e-value (log scale)")
        axis.legend()
        figure.tight_layout()
        figure.savefig(plot, dpi=160)
        plt.close(figure)
        print(f"wrote {plot}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="print one prospective evidence path")
    parser.add_argument("--plot", type=Path, help="with --demo, write the evidence trace plot")
    args = parser.parse_args(argv)
    if not args.demo:
        parser.error("--demo is required")
    _demo(args.plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
