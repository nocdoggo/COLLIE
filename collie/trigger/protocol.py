"""Trigger plumbing: the trace type and the two suppression wrappers.

Invocation is infrastructure, not contribution (module 06 brief): every arm that shares a rule
shares the *identical* wrapped trigger, so a contrast measures the representation, the
persistence, or the verification — never an accidental difference in when the model was asked.

Two disciplines live here and nowhere else:

- **The refractory window and the proposal cap are wrappers, not detector logic.** A detector
  emits raw candidate firings; :class:`RefractoryWrapper` and :class:`MaxProposalsWrapper` decide
  what is permitted. Wrapping is what guarantees the rules hold uniformly, including for detectors
  written later.
- **The trace is the comparison object.** ``TriggerTrace`` records every *permitted* firing —
  period, rule, statistic — and equality of traces (not similar counts) is the test that
  invocation timing is not a confound. Two arms making two calls at different times must fail the
  equality check, and they would.

The frozen :class:`collie.contracts.Trigger` protocol is only ``should_propose(obs)``; everything
here layers on top without touching it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from collie.contracts import PeriodObservation, Trigger

__all__ = [
    "MaxProposalsWrapper",
    "RefractoryWrapper",
    "TraceEntry",
    "TraceableTrigger",
    "Trigger",
    "TriggerTrace",
]


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """One permitted firing: when, which rule, and the statistic's value at firing."""

    period: int
    rule: str
    statistic: float


@dataclass(frozen=True, slots=True)
class TriggerTrace:
    """The invocation record of one wrapped trigger over one episode.

    ``entries`` holds permitted firings in order; ``n_suppressed`` counts raw firings the
    wrappers turned away. Equality is total — entries and suppression count — because "the same
    number of calls at different times" is precisely the confound this type exists to expose.
    """

    entries: tuple[TraceEntry, ...] = ()
    n_suppressed: int = 0

    @property
    def periods(self) -> tuple[int, ...]:
        return tuple(e.period for e in self.entries)

    def __len__(self) -> int:
        return len(self.entries)


@runtime_checkable
class TraceableTrigger(Trigger, Protocol):
    """A :class:`Trigger` with episode state and an invocation record.

    Concrete triggers are per-episode stateful machines (the runner resets controllers, not
    triggers; the owning arm resets its trigger chain in its own ``reset``).
    """

    def reset(self) -> None: ...

    @property
    def trace(self) -> TriggerTrace: ...

    def reset_accumulators(self) -> None:
        """Restart sufficient statistics after a *permitted* firing (standard SPC restart).

        Stateless triggers (schedules, alert-only) inherit the no-op. Accumulator detectors
        (CUSUM, Page-Hinkley) restart so a confirmed signal does not re-fire on its own
        accumulated evidence. Called by the wrappers, never by the runner.
        """
        ...


@dataclass(slots=True)
class RefractoryWrapper:
    """Suppress firings within ``window`` periods after the last permitted firing.

    ``window = W`` demands at least ``W`` quiet periods between permitted firings: a firing at
    ``p`` suppresses raw firings through period ``p + W``. ``window = 0`` disables suppression
    (one observation per period already guarantees distinct periods).
    """

    inner: TraceableTrigger
    window: int
    _permitted: list[TraceEntry] = field(default_factory=list, repr=False)
    _n_suppressed: int = field(default=0, repr=False)
    _last_period: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.window < 0:
            raise ValueError(f"refractory window must be non-negative, got {self.window}")

    def reset(self) -> None:
        self.inner.reset()
        self._permitted.clear()
        self._n_suppressed = 0
        self._last_period = None

    @property
    def trace(self) -> TriggerTrace:
        # Suppressions aggregate down the chain: the outermost trace reports every firing any
        # layer turned away, so "how many calls did the rules want versus make" is readable
        # from one number.
        return TriggerTrace(
            tuple(self._permitted), self._n_suppressed + self.inner.trace.n_suppressed
        )

    def reset_accumulators(self) -> None:
        self.inner.reset_accumulators()

    def should_propose(self, obs: PeriodObservation) -> bool:
        if not self.inner.should_propose(obs):
            return False
        entry = self.inner.trace.entries[-1]
        if self._last_period is not None and obs.period - self._last_period <= self.window:
            self._n_suppressed += 1
            return False
        self._last_period = obs.period
        self._permitted.append(entry)
        # Restart after signal: a permitted firing discharges the accumulators so the next
        # proposal must be earned on fresh evidence, not on the residue of the last one.
        self.inner.reset_accumulators()
        return True


@dataclass(slots=True)
class MaxProposalsWrapper:
    """Suppress every firing once ``limit`` proposals have been permitted.

    The primary design's cap is 2 (derivation note §5: ``alpha_j = alpha * 2**-j`` with at least
    ``alpha / 2`` always reserved). Living in one wrapper is what makes the cap hold for every
    detector, including ones written after this module.
    """

    inner: TraceableTrigger
    limit: int
    _permitted: list[TraceEntry] = field(default_factory=list, repr=False)
    _n_suppressed: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError(f"proposal limit must be non-negative, got {self.limit}")

    def reset(self) -> None:
        self.inner.reset()
        self._permitted.clear()
        self._n_suppressed = 0

    @property
    def trace(self) -> TriggerTrace:
        # Suppressions aggregate down the chain: the outermost trace reports every firing any
        # layer turned away, so "how many calls did the rules want versus make" is readable
        # from one number.
        return TriggerTrace(
            tuple(self._permitted), self._n_suppressed + self.inner.trace.n_suppressed
        )

    def reset_accumulators(self) -> None:
        self.inner.reset_accumulators()

    def should_propose(self, obs: PeriodObservation) -> bool:
        if not self.inner.should_propose(obs):
            return False
        entry = self.inner.trace.entries[-1]
        if len(self._permitted) >= self.limit:
            self._n_suppressed += 1
            return False
        self._permitted.append(entry)
        # Restart-after-signal propagates through every wrapper layer, whichever one permits
        # (a second discharge of an already-reset detector is a no-op).
        self.inner.reset_accumulators()
        return True
