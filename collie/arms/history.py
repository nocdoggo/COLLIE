"""Shared per-episode history for arms that render the benchmark's text channel.

The direct-action arms (3, 4, 11) and the LLM-to-OR arms (5, 6, 7) all rebuild the same
upstream observation text: the conclude-block history, the carry-over insights, the demand
history, and the order book that FIFO-attributes arrivals (see ``direct.py``'s module docstring
for the declared approximation). That bookkeeping lives here exactly once, so the two arm
families cannot drift apart in what they show the model.

Everything here is derived from the arm's own decisions and the observation stream — no hidden
state, no file access.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from collie.arms.prompts import PeriodConclusion
from collie.contracts import PeriodObservation

__all__ = ["BenchmarkHistory"]


@dataclass(slots=True)
class BenchmarkHistory:
    """One episode's observable history, rebuilt period by period.

    Usage per period ``t``: :meth:`observe` first (closes out period ``t-1`` from the
    observation's ``prev_*`` fields), then :meth:`record_demand` (arm 1's record-then-decide
    discipline), and after the arm's decision :meth:`note_dispatch` with the quantity actually
    sent. Insights update on model responses via :meth:`update_insights`.

    The arms using this run UNCENSORED only: the verbatim history needs true demand, which the
    censored channel deliberately withholds, so a missing ``prev_demand`` raises.
    """

    arm_id: str
    _conclusions: list[PeriodConclusion] = field(default_factory=list, repr=False)
    _insights: dict[int, str] = field(default_factory=dict, repr=False)
    _queue: list[list[float | int]] = field(default_factory=list, repr=False)
    _demands: list[float] = field(default_factory=list, repr=False)
    _arrivals: list[float] = field(default_factory=list, repr=False)
    _dispatches: dict[int, float] = field(default_factory=dict, repr=False)
    _observed_lead_times: list[int] = field(default_factory=list, repr=False)
    _last_order: float = field(default=0.0, repr=False)
    _prev_on_hand: float = field(default=0.0, repr=False)
    _prev_date: str = field(default="", repr=False)

    def reset(self) -> None:
        self._conclusions = []
        self._insights = {}
        self._queue = []
        self._demands = []
        self._arrivals = []
        self._dispatches = {}
        self._observed_lead_times = []
        self._last_order = 0.0
        self._prev_on_hand = 0.0
        self._prev_date = ""

    @property
    def conclusions(self) -> tuple[PeriodConclusion, ...]:
        return tuple(self._conclusions)

    @property
    def insights(self) -> tuple[tuple[int, str], ...]:
        return tuple(sorted(self._insights.items()))

    @property
    def demands(self) -> tuple[float, ...]:
        """Observed demand history: ``demands[j]`` is period ``j + 1``'s demand."""
        return tuple(self._demands)

    @property
    def arrivals(self) -> tuple[float, ...]:
        """Observed arrival history: ``arrivals[j]`` is the arrivals during period ``j + 1``."""
        return tuple(self._arrivals)

    @property
    def observed_lead_times(self) -> tuple[int, ...]:
        """FIFO-attributed arrival lead times, one per concluded arrival part.

        Matches the information upstream's ``parse_arrivals_from_history`` extracts from the
        conclude text — but appended exactly once per part. (Upstream re-parses the whole
        accumulated observation every period and blindly re-appends, a real upstream bug noted
        in ``docs/module06_research_notes.md`` §1.5 and deliberately not reproduced.)
        """
        return tuple(self._observed_lead_times)

    def observe(self, obs: PeriodObservation) -> None:
        """Close out period ``obs.period - 1`` into the history the next prompt renders."""
        if obs.period == 1:
            self._prev_on_hand = obs.on_hand
            self._prev_date = obs.date
            return
        arrivals = obs.prev_arrivals
        parts: list[tuple[float, int]] = []
        remaining = arrivals
        # FIFO attribution over the arm's own dispatch book. The queue can only exceed true
        # outstanding (a lost cohort never pops), never underflow.
        while remaining > 0 and self._queue:
            head_period, head_qty = self._queue[0]
            take = min(head_qty, remaining)
            parts.append((take, int(head_period)))
            remaining -= take
            if take == head_qty:
                self._queue.pop(0)
            else:
                self._queue[0] = [head_period, head_qty - take]
        demand = obs.prev_demand
        if demand is None:
            raise ValueError(
                f"{self.arm_id!r} renders the benchmark's verbatim history, which needs true "
                f"demand; period {obs.period} carries none. These arms run UNCENSORED only."
            )
        concluded = obs.period - 1
        self._observed_lead_times.extend(concluded - order_period for _, order_period in parts)
        self._arrivals.append(obs.prev_arrivals)
        self._conclusions.append(
            PeriodConclusion(
                period=concluded,
                ordered=self._last_order,
                arrivals=tuple(parts),
                start_on_hand=self._prev_on_hand,
                demand=demand,
                sold=self._prev_on_hand + obs.prev_arrivals - obs.on_hand,
                end_on_hand=obs.on_hand,
                date=self._prev_date,
            )
        )
        self._prev_on_hand = obs.on_hand
        self._prev_date = obs.date

    def record_demand(self, obs: PeriodObservation) -> None:
        """Append the previous period's demand — record-then-decide, as arm 1 does."""
        if obs.period > 1:
            assert obs.prev_demand is not None  # observe() already enforced uncensored
            self._demands.append(obs.prev_demand)

    def note_dispatch(self, period: int, quantity: float) -> None:
        """Record the quantity actually sent this period (post arm-level validation)."""
        self._queue.append([period, quantity])
        self._dispatches[period] = quantity
        self._last_order = quantity

    def dispatch_at(self, period: int) -> float:
        """The quantity the arm itself sent at ``period``, from its own decision record.

        The FIFO ``_queue`` is an attribution structure and is consumed as arrivals land; it
        cannot answer "what did the arm order at period r" once a cohort pops. Activation
        policies need exactly that question answered (an arrival-side construction conditions
        on the dispatch), so the dispatch book is kept separately and never popped.
        """
        try:
            return self._dispatches[period]
        except KeyError:
            raise KeyError(f"{self.arm_id!r} recorded no dispatch at period {period}") from None

    def update_insights(self, period: int, payload: Mapping[str, Any]) -> None:
        """The carry-over rule (``run_llm.py:882-890``), applied to an already-parsed payload.

        Each family parses differently (direct arms: a strict full-JSON parse of the response;
        LLM-to-OR arms: upstream's ``robust_parse_json`` result), so the parse is the caller's
        job and this applies only the bookkeeping: a non-empty memo is stored under the current
        period; an empty one deletes the current period's entry (unreachable through the
        episode flow, pinned by test); anything else updates nothing.
        """
        candidate = payload.get("carry_over_insight")
        memo = candidate.strip() if isinstance(candidate, str) else None
        if memo:
            self._insights[period] = memo
        elif period in self._insights:
            del self._insights[period]
