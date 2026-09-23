"""Exact arrival likelihoods from aggregate receipts and known dispatches.

The observable receipt stream does not identify which dispatch produced which units.  The filter
therefore carries a probability distribution over aggregate remaining-time buckets and sums every
compatible latent assignment.  Lost dispatches create no future receipt and a transit pause leaves
all still-moving buckets unchanged, matching the frozen supply semantics.

The registered laws below have common support.  That absolute-continuity requirement matters: an
alternative that assigned mass to an event impossible under the null could not feed the test
martingale from the derivation note.
"""

from __future__ import annotations

import argparse
import itertools
import math
import multiprocessing
import os
import random
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import StrEnum

from collie.contracts import (
    AnalysisClass,
    Direction,
    DurationBin,
    MagnitudeBin,
    ObservationMode,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
    assert_no_hidden_state,
)
from collie.data.families.supply import COMPOUND_PAUSE, LOSS_LENGTHS
from collie.data.nullbank import PROPOSAL_PERIODS, build_nullbank
from collie.verify.alpha import alpha_for_proposal
from collie.verify.eprocess import ANYTIME_VALID, EMPIRICAL_ONLY, EProcessPoint, MixtureEProcess
from collie.verify.registry import resolve_spec

__all__ = [
    "ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY",
    "LOST",
    "REGISTERED_DELAY_ALTERNATIVES",
    "REGISTERED_LOSS_ALTERNATIVES",
    "REGISTERED_NULL_LAW",
    "REGISTERED_PAUSE_ALTERNATIVES",
    "ArrivalEProcess",
    "ArrivalForwardFilter",
    "ArrivalModel",
    "ArrivalState",
    "RegisteredArrivalLaw",
    "ValidityFlag",
    "advance_counter",
    "brute_force_sequence_probability",
    "family_validity_flags",
    "run_arrival_null_calibration",
    "sample_arrival_model_path",
    "transition_state",
]


ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY = "anytime_valid_collie_shockspec_only"
"""The theorem-backed arrival label, whose source restriction must travel with each record."""


class TransitCounter(StrEnum):
    LOST = "lost"


LOST = TransitCounter.LOST


def advance_counter(counter: int | TransitCounter, *, paused: bool) -> int | TransitCounter:
    """Advance one latent counter; the lost outcome is absorbing."""
    if counter is LOST:
        return LOST
    if counter < 0:
        raise ValueError(f"remaining transit time must be non-negative, got {counter}")
    if counter == 0 or paused:
        return counter
    return counter - 1


@dataclass(frozen=True, slots=True)
class RegisteredArrivalLaw:
    """A finite, auditable law for one dispatch and one period's transit transition."""

    finite_delay_probabilities: tuple[float, ...]
    loss_probability: float
    pause_probability: float = 0.0
    name: str = "registered_arrival_law"

    def __post_init__(self) -> None:
        if not self.finite_delay_probabilities:
            raise ValueError("a registered arrival law needs at least delay zero")
        probabilities = (*self.finite_delay_probabilities, self.loss_probability)
        if any(not math.isfinite(value) or value < 0.0 for value in probabilities):
            raise ValueError(
                f"arrival probabilities must be finite and non-negative: {probabilities}"
            )
        if not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("finite-delay and loss probabilities must sum to one")
        if not 0.0 <= self.pause_probability <= 1.0:
            raise ValueError("pause_probability must lie in [0, 1]")

    @property
    def maximum_delay(self) -> int:
        return len(self.finite_delay_probabilities) - 1

    @property
    def outcomes(self) -> tuple[tuple[int | TransitCounter, float], ...]:
        finite = tuple(enumerate(self.finite_delay_probabilities))
        return (*finite, (LOST, self.loss_probability))

    @property
    def pause_outcomes(self) -> tuple[tuple[bool, float], ...]:
        if self.pause_probability == 0.0:
            return ((False, 1.0),)
        if self.pause_probability == 1.0:
            return ((True, 1.0),)
        return ((False, 1.0 - self.pause_probability), (True, self.pause_probability))


# Gate 2 is not frozen yet.  These are the single registered source for CP2's forward-model
# parameters and calibration; no environment or benchmark realization is inspected to set them.
REGISTERED_NULL_LAW = RegisteredArrivalLaw(
    finite_delay_probabilities=(0.02, 0.27, 0.48, 0.18, 0.04),
    loss_probability=0.01,
    pause_probability=0.01,
    name="collie_null_lmax4",
)


def _replace_loss_probability(
    law: RegisteredArrivalLaw, loss_probability: float, *, name: str
) -> RegisteredArrivalLaw:
    finite_total = math.fsum(law.finite_delay_probabilities)
    scale = (1.0 - loss_probability) / finite_total
    return RegisteredArrivalLaw(
        tuple(value * scale for value in law.finite_delay_probabilities),
        loss_probability,
        law.pause_probability,
        name,
    )


def _delay_tilt(law: RegisteredArrivalLaw, strength: float, *, name: str) -> RegisteredArrivalLaw:
    raw = tuple(
        probability * math.exp(strength * delay)
        for delay, probability in enumerate(law.finite_delay_probabilities)
    )
    scale = (1.0 - law.loss_probability) / math.fsum(raw)
    return RegisteredArrivalLaw(
        tuple(value * scale for value in raw),
        law.loss_probability,
        law.pause_probability,
        name,
    )


def _replace_pause_probability(
    law: RegisteredArrivalLaw, pause_probability: float, *, name: str
) -> RegisteredArrivalLaw:
    return RegisteredArrivalLaw(
        law.finite_delay_probabilities,
        law.loss_probability,
        pause_probability,
        name,
    )


REGISTERED_DELAY_ALTERNATIVES = (
    _delay_tilt(REGISTERED_NULL_LAW, 0.55, name="delay_tilt_medium"),
    _delay_tilt(REGISTERED_NULL_LAW, 0.95, name="delay_tilt_high"),
)
REGISTERED_LOSS_ALTERNATIVES = (
    _replace_loss_probability(REGISTERED_NULL_LAW, 0.80, name="loss_medium"),
    _replace_loss_probability(REGISTERED_NULL_LAW, 0.98, name="loss_high"),
)
REGISTERED_PAUSE_ALTERNATIVES = (
    _replace_pause_probability(REGISTERED_NULL_LAW, 0.80, name="pause_medium"),
    _replace_pause_probability(REGISTERED_NULL_LAW, 0.98, name="pause_high"),
)


def _changed_laws_for(
    family: ShockFamily,
    null_law: RegisteredArrivalLaw,
    magnitude_bin: MagnitudeBin,
) -> tuple[RegisteredArrivalLaw, ...]:
    """Apply the frozen alternative transformations to the caller's explicit null law."""
    if family is ShockFamily.LEAD_TIME_SHIFT:
        choices = (
            _delay_tilt(null_law, 0.55, name="delay_tilt_medium"),
            _delay_tilt(null_law, 0.95, name="delay_tilt_high"),
        )
    elif family is ShockFamily.SHIPMENT_LOSS:
        choices = (
            _replace_loss_probability(null_law, 0.80, name="loss_medium"),
            _replace_loss_probability(null_law, 0.98, name="loss_high"),
        )
    elif family in {ShockFamily.TRANSIT_PAUSE, ShockFamily.COMPOUND}:
        choices = (
            _replace_pause_probability(null_law, 0.80, name="pause_medium"),
            _replace_pause_probability(null_law, 0.98, name="pause_high"),
        )
    else:
        raise ValueError(f"unsupported arrival family {family}")
    if magnitude_bin is MagnitudeBin.HIGH:
        return (choices[1],)
    if magnitude_bin in {MagnitudeBin.LOW, MagnitudeBin.MEDIUM}:
        return (choices[0],)
    raise ValueError("an actionable arrival spec needs a registered magnitude bin")


@dataclass(frozen=True, slots=True)
class ArrivalState:
    """Aggregate quantity at each remaining-time value, including zero."""

    by_remaining: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.by_remaining:
            raise ValueError("arrival state must contain the remaining-zero bucket")
        if any(not math.isfinite(value) or value < 0.0 for value in self.by_remaining):
            raise ValueError("arrival-state quantities must be finite and non-negative")

    @classmethod
    def empty(cls, maximum_delay: int) -> ArrivalState:
        if maximum_delay < 0:
            raise ValueError("maximum_delay must be non-negative")
        return cls((0.0,) * (maximum_delay + 1))


def transition_state(
    state: ArrivalState,
    *,
    dispatch_quantity: float,
    delay: int | TransitCounter,
    paused: bool,
) -> tuple[float, ArrivalState]:
    """Apply dispatch, aggregate emission, and then the frozen transit-clock update."""
    if not math.isfinite(dispatch_quantity) or dispatch_quantity < 0.0:
        raise ValueError("dispatch quantity must be finite and non-negative")
    buckets = list(state.by_remaining)
    if delay is not LOST:
        if not 0 <= delay < len(buckets):
            raise ValueError(f"delay {delay} is outside the registered state")
        buckets[delay] += dispatch_quantity

    receipt = buckets[0]
    buckets[0] = 0.0
    if paused:
        return receipt, ArrivalState(tuple(buckets))

    advanced = [0.0] * len(buckets)
    for remaining in range(1, len(buckets)):
        advanced[remaining - 1] += buckets[remaining]
    return receipt, ArrivalState(tuple(advanced))


@dataclass(frozen=True, slots=True)
class ArrivalModel:
    """A baseline law with an optional prospectively registered regime."""

    baseline: RegisteredArrivalLaw = REGISTERED_NULL_LAW
    changed: RegisteredArrivalLaw | None = None
    active_from: int | None = None
    active_duration: int | None = None

    def __post_init__(self) -> None:
        if self.changed is None and (
            self.active_from is not None or self.active_duration is not None
        ):
            raise ValueError("an unchanged arrival model cannot have an active regime")
        if self.changed is not None:
            if self.changed.maximum_delay != self.baseline.maximum_delay:
                raise ValueError("baseline and changed law must share a finite state space")
            if self.active_from is None:
                raise ValueError("a changed arrival law needs active_from")
        if self.active_duration is not None and self.active_duration < 1:
            raise ValueError("active_duration must be positive")

    def law_at(self, period: int) -> RegisteredArrivalLaw:
        if self.changed is None or self.active_from is None or period < self.active_from:
            return self.baseline
        if self.active_duration is not None and period >= self.active_from + self.active_duration:
            return self.baseline
        return self.changed


@dataclass(slots=True)
class ArrivalForwardFilter:
    """Normalized forward variables plus the exact observable sequence likelihood."""

    model: ArrivalModel
    distribution: dict[ArrivalState, float] = field(init=False)
    sequence_probability: float = field(default=1.0, init=False)
    last_period: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.distribution = {ArrivalState.empty(self.model.baseline.maximum_delay): 1.0}

    def step(self, *, period: int, dispatch_quantity: float, receipt: float) -> float:
        """Return the exact conditional receipt mass and update the latent-state filter."""
        assert_no_hidden_state(
            (period, dispatch_quantity, receipt), context="arrival verifier observation"
        )
        if period != self.last_period + 1:
            raise ValueError(
                f"arrival periods must be consecutive: expected {self.last_period + 1}"
            )
        if not math.isfinite(receipt) or receipt < 0.0:
            raise ValueError("receipt must be finite and non-negative")

        law = self.model.law_at(period)
        compatible: dict[ArrivalState, float] = {}
        for state, state_probability in self.distribution.items():
            for delay, delay_probability in law.outcomes:
                if delay_probability == 0.0:
                    continue
                for paused, pause_probability in law.pause_outcomes:
                    emitted, next_state = transition_state(
                        state,
                        dispatch_quantity=dispatch_quantity,
                        delay=delay,
                        paused=paused,
                    )
                    if math.isclose(emitted, receipt, rel_tol=0.0, abs_tol=1e-9):
                        mass = state_probability * delay_probability * pause_probability
                        compatible[next_state] = compatible.get(next_state, 0.0) + mass

        predictive_probability = math.fsum(compatible.values())
        if predictive_probability <= 0.0:
            raise ValueError(
                f"receipt {receipt} at period {period} is impossible under {law.name!r}"
            )
        self.distribution = {
            state: probability / predictive_probability for state, probability in compatible.items()
        }
        self.sequence_probability *= predictive_probability
        self.last_period = period
        return predictive_probability


def brute_force_sequence_probability(
    law: RegisteredArrivalLaw,
    dispatches: Sequence[float],
    receipts: Sequence[float],
) -> float:
    """Enumerate all short-horizon latent assignments independently of the forward filter."""
    if len(dispatches) != len(receipts):
        raise ValueError("dispatch and receipt sequences must align")
    horizon = len(dispatches)
    total = 0.0
    delay_choices = tuple(law.outcomes)
    pause_choices = tuple(law.pause_outcomes)
    for delay_path in itertools.product(delay_choices, repeat=horizon):
        delay_probability = math.prod(choice[1] for choice in delay_path)
        if delay_probability == 0.0:
            continue
        for pause_path in itertools.product(pause_choices, repeat=horizon):
            path_probability = delay_probability * math.prod(choice[1] for choice in pause_path)
            if path_probability == 0.0:
                continue
            # Deliberately do not call ``transition_state`` here.  This oracle retains each short
            # horizon assignment separately so it can catch a bucket-transition off-by-one in the
            # production recursion.
            cohorts: list[tuple[float, int | TransitCounter]] = []
            matched = True
            for dispatch, observed, delay_choice, pause_choice in zip(
                dispatches, receipts, delay_path, pause_path, strict=True
            ):
                cohorts.append((dispatch, delay_choice[0]))
                emitted = math.fsum(quantity for quantity, counter in cohorts if counter == 0)
                if not math.isclose(emitted, observed, rel_tol=0.0, abs_tol=1e-9):
                    matched = False
                    break
                next_cohorts = []
                for quantity, counter in cohorts:
                    if counter == 0:
                        continue
                    # Keep the oracle independent of the production counter helper as well as the
                    # production transition.  Shared transition primitives would let the same
                    # off-by-one bug pass on both sides of the comparison.
                    next_counter = counter if counter is LOST or pause_choice[0] else counter - 1
                    next_cohorts.append((quantity, next_counter))
                cohorts = next_cohorts
            if matched:
                total += path_probability
    return total


def _durations_for_family(family: ShockFamily) -> tuple[int | None, ...]:
    if family is ShockFamily.SHIPMENT_LOSS:
        return tuple(range(LOSS_LENGTHS[0], LOSS_LENGTHS[1] + 1))
    if family is ShockFamily.TRANSIT_PAUSE:
        return tuple(range(COMPOUND_PAUSE[0], COMPOUND_PAUSE[1] + 1))
    return (None,)


@dataclass(frozen=True, slots=True)
class ArrivalEProcess:
    """Future-only likelihood-ratio adapter around paired exact forward filters."""

    null: ArrivalModel
    alternatives: tuple[ArrivalModel, ...]
    tau_j: int
    alpha_j: float
    preproposal_history: tuple[tuple[float, float], ...] = ()
    family: ShockFamily | None = None
    source: str = "collie_shockspec"
    observation_mode: ObservationMode = ObservationMode.UNCENSORED
    analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY
    _engine: MixtureEProcess = field(init=False, repr=False)
    _null_filter: ArrivalForwardFilter = field(init=False, repr=False)
    _alternative_filters: tuple[ArrivalForwardFilter, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        assert_no_hidden_state(
            (self.null, self.alternatives, self.preproposal_history),
            context="arrival verifier inputs",
        )
        if not self.alternatives:
            raise ValueError("an arrival e-process needs at least one registered alternative")
        if len(self.preproposal_history) != self.tau_j:
            raise ValueError(
                "arrival recursion needs one dispatch/receipt pair for every period through "
                f"tau_j={self.tau_j}; got {len(self.preproposal_history)}"
            )
        if any(
            model.baseline.maximum_delay != self.null.baseline.maximum_delay
            for model in self.alternatives
        ):
            raise ValueError("all arrival models must share the registered finite state")

        registered_null_bound = (
            self.null == ArrivalModel(REGISTERED_NULL_LAW)
            and self.family
            in {
                ShockFamily.LEAD_TIME_SHIFT,
                ShockFamily.SHIPMENT_LOSS,
                ShockFamily.TRANSIT_PAUSE,
                ShockFamily.COMPOUND,
            }
            and _models_are_registered(self.family, self.tau_j, self.alternatives)
        )
        validity = (
            ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY
            if self.source == "collie_shockspec"
            and self.observation_mode is ObservationMode.UNCENSORED
            and registered_null_bound
            else EMPIRICAL_ONLY
        )
        if validity == EMPIRICAL_ONLY and self.analysis_class is AnalysisClass.CONFIRMATORY:
            raise ValueError("empirical_only arrival verifier cannot be labelled confirmatory")
        weight = 1.0 / len(self.alternatives)
        object.__setattr__(
            self,
            "_engine",
            MixtureEProcess(
                tau_j=self.tau_j,
                alpha_j=self.alpha_j,
                weights=(weight,) * len(self.alternatives),
                validity_label=validity,
                analysis_class=self.analysis_class,
            ),
        )
        null_filter = ArrivalForwardFilter(ArrivalModel(self.null.baseline))
        for period, (dispatch, receipt) in enumerate(self.preproposal_history, start=1):
            null_filter.step(period=period, dispatch_quantity=dispatch, receipt=receipt)
        # The pre-proposal posterior is common to every prospectively changed model.  Copy it into
        # filters whose transition switches only when future evidence is consumed.
        conditioned = null_filter.distribution.copy()
        object.__setattr__(
            self,
            "_null_filter",
            ArrivalForwardFilter(self.null),
        )
        self._null_filter.distribution = conditioned.copy()
        self._null_filter.last_period = len(self.preproposal_history)
        object.__setattr__(
            self,
            "_alternative_filters",
            tuple(ArrivalForwardFilter(model) for model in self.alternatives),
        )
        for alternative_filter in self._alternative_filters:
            alternative_filter.distribution = conditioned.copy()
            alternative_filter.last_period = len(self.preproposal_history)

    @classmethod
    def from_spec(
        cls,
        spec: ShockSpec,
        *,
        alpha_episode: float,
        preproposal_history: Sequence[tuple[float, float]] = (),
        null_law: RegisteredArrivalLaw = REGISTERED_NULL_LAW,
        source: str = "collie_shockspec",
        observation_mode: ObservationMode = ObservationMode.UNCENSORED,
        analysis_class: AnalysisClass = AnalysisClass.EXPLORATORY,
    ) -> ArrivalEProcess:
        construction = resolve_spec(spec)
        compound = spec.shock_family is ShockFamily.COMPOUND
        expected_stream = TargetStream.BOTH if compound else TargetStream.ARRIVAL
        if construction.stream is not expected_stream or spec.target_stream is not expected_stream:
            raise ValueError(
                "arrival verifier requires a registered arrival spec or compound both-stream spec"
            )
        if spec.direction is not construction.direction:
            raise ValueError("spec direction does not match its registered arrival construction")
        if spec.onset_window is None:
            raise ValueError("an arrival spec needs an onset window")

        assert spec.magnitude_bin is not None
        changed_laws = _changed_laws_for(
            spec.shock_family,
            null_law,
            spec.magnitude_bin,
        )
        starts = tuple(spec.tau_j + offset for offset in range(*_inclusive(spec.onset_window)))
        durations = _durations_for_family(
            ShockFamily.TRANSIT_PAUSE if compound else spec.shock_family
        )
        alternatives = tuple(
            ArrivalModel(
                baseline=null_law,
                changed=changed,
                active_from=start,
                active_duration=duration,
            )
            for changed in changed_laws
            for start in starts
            for duration in durations
        )
        allocation = alpha_for_proposal(alpha_episode, spec.proposal_index)
        return cls(
            null=ArrivalModel(null_law),
            alternatives=alternatives,
            tau_j=spec.tau_j,
            alpha_j=allocation.alpha_j / 2.0 if compound else allocation.alpha_j,
            preproposal_history=tuple(preproposal_history),
            family=spec.shock_family,
            source=source,
            observation_mode=observation_mode,
            analysis_class=analysis_class,
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

    def observe(self, period: int, dispatch_quantity: float, receipt: float) -> EProcessPoint:
        self._engine.validate_period(period)
        null_probability = self._null_filter.step(
            period=period, dispatch_quantity=dispatch_quantity, receipt=receipt
        )
        ratios = []
        for alternative_filter in self._alternative_filters:
            alternative_probability = alternative_filter.step(
                period=period, dispatch_quantity=dispatch_quantity, receipt=receipt
            )
            ratios.append(math.log(alternative_probability) - math.log(null_probability))
        return self._engine.update(period, tuple(ratios))


def _models_are_registered(
    family: ShockFamily,
    tau_j: int,
    models: Sequence[ArrivalModel],
) -> bool:
    """Keep the theorem label bound to the pre-registered alternative grid too."""
    laws = {
        ShockFamily.LEAD_TIME_SHIFT: REGISTERED_DELAY_ALTERNATIVES,
        ShockFamily.SHIPMENT_LOSS: REGISTERED_LOSS_ALTERNATIVES,
        ShockFamily.TRANSIT_PAUSE: REGISTERED_PAUSE_ALTERNATIVES,
        ShockFamily.COMPOUND: REGISTERED_PAUSE_ALTERNATIVES,
    }[family]
    durations = _durations_for_family(
        ShockFamily.TRANSIT_PAUSE if family is ShockFamily.COMPOUND else family
    )
    allowed_starts = {tau_j + offset for offset in range(-2, 3)}
    return all(
        model.baseline == REGISTERED_NULL_LAW
        and model.changed in laws
        and model.active_from in allowed_starts
        and model.active_duration in durations
        for model in models
    )


def _inclusive(window: tuple[int, int]) -> tuple[int, int]:
    return window[0], window[1] + 1


@dataclass(frozen=True, slots=True)
class ValidityFlag:
    family: str
    stream: str
    construction: str
    status: str


def family_validity_flags(
    *,
    source: str = "collie_shockspec",
    observation_mode: ObservationMode = ObservationMode.UNCENSORED,
    plug_in: bool = False,
) -> tuple[ValidityFlag, ...]:
    """Return the authoritative §9 rows for the requested observation/construction view."""
    if plug_in:
        status = "empirical_only_permanently"
        return (ValidityFlag("any", "either", "plug_in", status),)
    if observation_mode is ObservationMode.CENSORED:
        return (ValidityFlag("any", "either", "censored_model_pending", EMPIRICAL_ONLY),)
    arrival_status = (
        ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY if source == "collie_shockspec" else EMPIRICAL_ONLY
    )
    compound_status = (
        "anytime_valid_via_splitting" if source == "collie_shockspec" else EMPIRICAL_ONLY
    )
    return (
        ValidityFlag("demand_level_up", "demand", "discrete_mixture_lr", ANYTIME_VALID),
        ValidityFlag("demand_level_down", "demand", "discrete_mixture_lr", ANYTIME_VALID),
        ValidityFlag(
            "temporary_pulse", "demand", "bounded_duration_mixture_lr", "anytime_valid_low_power"
        ),
        ValidityFlag("lead_time_shift", "arrival", "finite_state_forward", arrival_status),
        ValidityFlag(
            "shipment_loss", "arrival", "finite_state_forward_absorbing_loss", arrival_status
        ),
        ValidityFlag(
            "transit_pause", "arrival", "finite_state_forward_frozen_counters", arrival_status
        ),
        ValidityFlag("compound", "both", "separate_eprocesses_alpha_split", compound_status),
    )


@dataclass(frozen=True, slots=True)
class ArrivalCalibrationSummary:
    family: ShockFamily
    replications: int
    activations: int
    alpha_episode: float
    proposal_alpha: float
    rate: float
    wilson_low: float
    wilson_high: float
    validity_label: str
    analysis_class: AnalysisClass


def _wilson(successes: int, trials: int) -> tuple[float, float]:
    z = 1.959963984540054
    proportion = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    centre = (proportion + z2 / (2.0 * trials)) / denominator
    half = z * math.sqrt(proportion * (1.0 - proportion) / trials + z2 / (4.0 * trials**2))
    half /= denominator
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == trials else min(1.0, centre + half)
    return low, high


def _sample_path(
    law: RegisteredArrivalLaw,
    dispatches: Sequence[float],
    *,
    rng: random.Random,
) -> tuple[float, ...]:
    state = ArrivalState.empty(law.maximum_delay)
    receipts = []
    outcome_values = tuple(value for value, _ in law.outcomes)
    outcome_weights = tuple(probability for _, probability in law.outcomes)
    for dispatch in dispatches:
        delay = rng.choices(outcome_values, weights=outcome_weights, k=1)[0]
        paused = rng.random() < law.pause_probability
        receipt, state = transition_state(
            state, dispatch_quantity=dispatch, delay=delay, paused=paused
        )
        receipts.append(receipt)
    return tuple(receipts)


def sample_arrival_model_path(
    model: ArrivalModel,
    dispatches: Sequence[float],
    *,
    rng: random.Random,
) -> tuple[float, ...]:
    """Sample the exact registered period-varying law used by a power/demo alternative."""
    state = ArrivalState.empty(model.baseline.maximum_delay)
    receipts = []
    for period, dispatch in enumerate(dispatches, start=1):
        law = model.law_at(period)
        delay = rng.choices(
            tuple(value for value, _ in law.outcomes),
            weights=tuple(probability for _, probability in law.outcomes),
            k=1,
        )[0]
        paused = rng.random() < law.pause_probability
        receipt, state = transition_state(
            state, dispatch_quantity=dispatch, delay=delay, paused=paused
        )
        receipts.append(receipt)
    return tuple(receipts)


def _spec_for_family(
    family: ShockFamily,
    *,
    tau_j: int,
    magnitude_bin: MagnitudeBin = MagnitudeBin.MEDIUM,
) -> ShockSpec:
    fields = {
        ShockFamily.LEAD_TIME_SHIFT: (
            Direction.ARRIVAL_DELAYED,
            "sig_arrival_delay",
        ),
        ShockFamily.SHIPMENT_LOSS: (
            Direction.ARRIVAL_INTERRUPTED,
            "sig_arrival_loss",
        ),
        ShockFamily.TRANSIT_PAUSE: (
            Direction.ARRIVAL_INTERRUPTED,
            "sig_arrival_stall",
        ),
    }
    direction, signature = fields[family]
    duration_bin = {
        ShockFamily.LEAD_TIME_SHIFT: DurationBin.LONGER,
        ShockFamily.SHIPMENT_LOSS: DurationBin.SHORT,
        ShockFamily.TRANSIT_PAUSE: DurationBin.MEDIUM,
    }[family]
    persistence = (
        Persistence.PERSISTENT if family is ShockFamily.LEAD_TIME_SHIFT else Persistence.TRANSIENT
    )

    return ShockSpec(
        target_stream=TargetStream.ARRIVAL,
        shock_family=family,
        direction=direction,
        onset_window=(0, 2),
        magnitude_bin=magnitude_bin,
        persistence=persistence,
        duration_bin=duration_bin,
        evidence_refs=(f"obs_t{tau_j}",),
        prospective_signature=signature,
        tau_j=tau_j,
        proposal_index=1,
        model_id="calibration",
        decoding_hash="frozen",
        prompt_hash="frozen",
    )


def _compound_demo_spec(*, tau_j: int) -> ShockSpec:
    return ShockSpec(
        target_stream=TargetStream.BOTH,
        shock_family=ShockFamily.COMPOUND,
        direction=Direction.MIXED,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.HIGH,
        persistence=Persistence.TRANSIENT,
        duration_bin=DurationBin.MEDIUM,
        evidence_refs=(f"obs_t{tau_j}",),
        prospective_signature="sig_compound",
        tau_j=tau_j,
        proposal_index=1,
        model_id="demo",
        decoding_hash="frozen",
        prompt_hash="frozen",
    )


def run_arrival_null_calibration(
    *,
    family: ShockFamily,
    replications: int,
    alpha_episode: float = 0.05,
    horizon: int,
    tau_j: int = PROPOSAL_PERIODS[0],
    seed: int = 20260908,
    workers: int | None = None,
) -> ArrivalCalibrationSummary:
    if family not in {
        ShockFamily.LEAD_TIME_SHIFT,
        ShockFamily.SHIPMENT_LOSS,
        ShockFamily.TRANSIT_PAUSE,
    }:
        raise ValueError("arrival calibration requires one registered arrival family")
    if replications < 1:
        raise ValueError("replications must be positive")
    if not 0 <= tau_j < horizon:
        raise ValueError(f"tau_j must lie in [0, horizon), got {tau_j} for horizon {horizon}")
    proposal_alpha = alpha_for_proposal(alpha_episode, 1).alpha_j
    # Equal unit dispatches preserve every ambiguity the aggregate-receipt filter must marginalise
    # while keeping the full 2,000 x 50 audit under five minutes.  The theorem permits any
    # predictable action sequence; calibration fixes this one before drawing receipts.
    dispatches = (1.0,) * horizon
    workers = min(8, os.cpu_count() or 1) if workers is None else workers
    if workers < 1:
        raise ValueError("workers must be positive")
    workers = min(workers, replications)
    chunks = tuple(tuple(range(worker, replications, workers)) for worker in range(workers))
    arguments = (
        (family, chunk, horizon, tau_j, alpha_episode, seed, dispatches)
        for chunk in chunks
        if chunk
    )
    if workers == 1 or replications < 32:
        activations = sum(_arrival_null_chunk(*argument) for argument in arguments)
    else:
        activations = _run_forked_chunks(tuple(arguments))
    rate = activations / replications
    low, high = _wilson(activations, replications)
    return ArrivalCalibrationSummary(
        family=family,
        replications=replications,
        activations=activations,
        alpha_episode=alpha_episode,
        proposal_alpha=proposal_alpha,
        rate=rate,
        wilson_low=low,
        wilson_high=high,
        validity_label=ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY,
        analysis_class=AnalysisClass.EXPLORATORY,
    )


def _run_forked_chunks(arguments: tuple[tuple[object, ...], ...]) -> int:
    """Use pipes rather than multiprocessing semaphores, which restricted audit hosts may disable."""
    if not hasattr(os, "fork"):
        return _run_spawned_chunks(arguments)

    children: list[tuple[int, int]] = []
    for argument in arguments:
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:  # pragma: no cover - child result is asserted by the parent
            try:
                os.close(read_fd)
                result = _arrival_null_chunk(*argument)  # type: ignore[arg-type]
                os.write(write_fd, str(result).encode("ascii"))
                os.close(write_fd)
                os._exit(0)
            except BaseException:
                os._exit(1)
        os.close(write_fd)
        children.append((pid, read_fd))

    total = 0
    for pid, read_fd in children:
        payload = os.read(read_fd, 64)
        os.close(read_fd)
        _, status = os.waitpid(pid, 0)
        if status != 0 or not payload:
            raise RuntimeError(f"arrival calibration worker {pid} failed")
        total += int(payload.decode("ascii"))
    return total


def _run_spawned_chunks(arguments: tuple[tuple[object, ...], ...]) -> int:
    context = multiprocessing.get_context("spawn")
    worker_count = max(1, len(arguments))
    total = 0
    with ProcessPoolExecutor(max_workers=worker_count, mp_context=context) as executor:
        futures = {
            executor.submit(_arrival_null_chunk_from_argument, argument): index
            for index, argument in enumerate(arguments)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                total += future.result()
            except BaseException as exc:
                raise RuntimeError(f"arrival calibration worker local-{index} failed") from exc
    return total


def _arrival_null_chunk_from_argument(argument: tuple[object, ...]) -> int:
    return _arrival_null_chunk(*argument)  # type: ignore[arg-type]


def _arrival_null_chunk(
    family: ShockFamily,
    replication_indices: Sequence[int],
    horizon: int,
    tau_j: int,
    alpha_episode: float,
    seed: int,
    dispatches: Sequence[float],
) -> int:
    """Run deterministic per-replication seeds so worker count cannot change the audit result."""
    activations = 0
    spec = _spec_for_family(family, tau_j=tau_j)
    family_offset = list(ShockFamily).index(family) * 10_000_000
    for replication in replication_indices:
        rng = random.Random(seed + family_offset + replication)
        receipts = _sample_path(REGISTERED_NULL_LAW, dispatches, rng=rng)
        verifier = ArrivalEProcess.from_spec(
            spec,
            alpha_episode=alpha_episode,
            preproposal_history=tuple(zip(dispatches[:tau_j], receipts[:tau_j], strict=True)),
        )
        for period in range(tau_j + 1, horizon + 1):
            verifier.observe(period, dispatches[period - 1], receipts[period - 1])
            if verifier.activated:
                activations += 1
                break
    return activations


def _demo() -> None:
    from collie.verify.lifecycle import compound_demo_timeline

    tau_j = PROPOSAL_PERIODS[0]
    horizon = build_nullbank()[0].horizon
    dispatches = (10.0,) * horizon
    loss_spec = _spec_for_family(
        ShockFamily.SHIPMENT_LOSS,
        tau_j=tau_j,
        magnitude_bin=MagnitudeBin.HIGH,
    )

    null_receipts = _sample_path(REGISTERED_NULL_LAW, dispatches, rng=random.Random(20260908))
    null_verifier = ArrivalEProcess.from_spec(
        loss_spec,
        alpha_episode=0.05,
        preproposal_history=tuple(zip(dispatches[:tau_j], null_receipts[:tau_j], strict=True)),
    )
    for period in range(tau_j + 1, horizon + 1):
        null_verifier.observe(period, dispatches[period - 1], null_receipts[period - 1])

    burst_model = ArrivalModel(
        baseline=REGISTERED_NULL_LAW,
        changed=REGISTERED_LOSS_ALTERNATIVES[-1],
        active_from=tau_j + 1,
        active_duration=LOSS_LENGTHS[1],
    )
    burst_receipts = sample_arrival_model_path(burst_model, dispatches, rng=random.Random(41))
    burst_verifier = ArrivalEProcess.from_spec(
        loss_spec,
        alpha_episode=0.05,
        preproposal_history=tuple(zip(dispatches[:tau_j], burst_receipts[:tau_j], strict=True)),
    )
    for period in range(tau_j + 1, horizon + 1):
        burst_verifier.observe(period, dispatches[period - 1], burst_receipts[period - 1])

    print("arrival demo")
    print(
        f"lost-shipment burst: activated={burst_verifier.activated} "
        f"at={burst_verifier.activation_period} e={burst_verifier.e_value:.3f}"
    )
    print(
        f"noisy registered null: activated={null_verifier.activated} "
        f"at={null_verifier.activation_period} e={null_verifier.e_value:.3f}"
    )
    print("validity table")
    for row in family_validity_flags():
        print(f"  {row.family:20s} {row.status}")
    print("official arrival scope")
    for row in family_validity_flags(source="official"):
        if row.stream in {"arrival", "both"}:
            print(f"  {row.family:20s} {row.status}")
    for row in family_validity_flags(observation_mode=ObservationMode.CENSORED):
        print(f"  {row.family:20s} {row.status}")
    for row in family_validity_flags(plug_in=True):
        print(f"  {row.family:20s} {row.status}")
    print("compound lifecycle timeline")
    for event in compound_demo_timeline(_compound_demo_spec(tau_j=tau_j), episode_horizon=horizon):
        print(
            f"  t={event.period:02d} proposal={event.proposal_index} "
            f"state={event.state.value:10s} reason={event.reason} "
            f"retirement={event.retirement_claim}"
        )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(tuple(argv) if argv is not None else None)
    if args.demo:
        _demo()


if __name__ == "__main__":  # pragma: no cover - exercised by the audit command
    main()
