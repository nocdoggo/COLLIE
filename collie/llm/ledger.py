"""The call ledger: physical versus charged accounting, per-arm totals, byte-stable CSV.

The distinction that keeps the compute frontier honest (design.md):

- **Physical** entries are what the provider saw — one per real request. ``physical=True``.
- **Charged** entries are what an arm would have paid — one per arm per call it would have
  made, including calls served from cache. ``physical=False``. Arms 8/9/10 sharing one physical
  proposal call each carry a charged copy, so ``physical <= sum(charged)`` is a *property of the
  books*, asserted in tests over random arm sets.

Every attempted call is classified exactly once when the arm settles it: ``ACCEPTED``,
``ACCEPTED_AFTER_REPAIR`` (a repair attempt that parsed), or ``FALLBACK`` (unusable). An
unsettled charged entry fails :meth:`CallLedger.assert_conserved` — conservation is checked, not
assumed. Physical entries carry no outcome: parsing is per-arm business, the provider never sees
it.

Latency is a measurement (client-side ``perf_counter``, connect+queue+generation+transfer) and
is therefore **not** part of replay identity: warm-replay equality is asserted on charged
*totals* — attempted counts, tokens, dated dollars — never on latencies. Dated cost is computed
at log time from the endpoint's registered price table (research notes §5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

from collie.contracts import CallLog, ParseOutcome
from collie.llm.client import EndpointConfig, RawResponse

__all__ = ["ArmTotals", "CallLedger", "LedgerSummary"]


def _usd(raw: RawResponse, endpoint: EndpointConfig) -> float:
    return (
        raw.prompt_tokens * endpoint.price_input_per_mtok
        + raw.billable_output(endpoint) * endpoint.price_output_per_mtok
    ) / 1_000_000.0


def _nearest_rank_ms(latencies: list[float], q: float) -> float:
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


@dataclass(frozen=True, slots=True)
class ArmTotals:
    """One arm's charged-side accounting."""

    arm_id: str
    attempted: int
    accepted: int
    accepted_after_repair: int
    rejected: int
    input_tokens: int
    output_tokens: int
    p50_latency_ms: float
    p95_latency_ms: float
    usd_cost: float


@dataclass(frozen=True, slots=True)
class LedgerSummary:
    """The whole ledger, aggregated. ``physical <= sum(charged)`` holds by construction of
    :class:`CallLedger` and is asserted by :meth:`CallLedger.assert_conserved`."""

    physical: int
    charged: int
    per_arm: tuple[ArmTotals, ...]
    total_usd: float


class CallLedger:
    """Append-only record of every attempted call, physical and charged.

    ``call_id`` values are sequential (``call-000001``, ...), so a byte-identical replay
    produces byte-identical ids.
    """

    def __init__(self) -> None:
        self._entries: list[CallLog] = []
        self._index: dict[str, int] = {}

    @property
    def entries(self) -> tuple[CallLog, ...]:
        return tuple(self._entries)

    def _record(self, *, physical: bool, cache_hit: bool, **fields) -> str:
        call_id = f"call-{len(self._entries) + 1:06d}"
        raw: RawResponse = fields.pop("raw")
        endpoint: EndpointConfig = fields.pop("endpoint")
        entry = CallLog(
            call_id=call_id,
            outcome=None,  # settled by the arm; see settle()
            input_tokens=raw.prompt_tokens,
            output_tokens=raw.billable_output(endpoint),
            latency_ms=fields.pop("latency_ms"),
            usd_cost=_usd(raw, endpoint),
            cache_hit=cache_hit,
            physical=physical,
            **fields,
        )
        self._entries.append(entry)
        self._index[call_id] = len(self._entries) - 1
        return call_id

    def record_physical(self, **fields) -> str:
        """One real provider request. Exactly one per cache miss, never more."""
        return self._record(physical=True, cache_hit=False, **fields)

    def record_charged(self, *, cache_hit: bool, **fields) -> str:
        """The charge copy for one arm that made or would have made the call."""
        return self._record(physical=False, cache_hit=cache_hit, **fields)

    def settle(self, call_id: str, outcome: ParseOutcome) -> None:
        """Classify an attempted call. Every charged entry must be settled exactly once."""
        position = self._index.get(call_id)
        if position is None:
            raise KeyError(f"unknown call_id {call_id!r}")
        entry = self._entries[position]
        if entry.outcome is not None:
            raise ValueError(f"{call_id} is already settled as {entry.outcome}; double-settle")
        self._entries[position] = replace(entry, outcome=outcome)

    def charged_entries(self, arm_id: str | None = None) -> tuple[CallLog, ...]:
        """The accounting view: charged entries only (physical entries are nobody's charge)."""
        return tuple(
            e for e in self._entries if not e.physical and (arm_id is None or e.arm_id == arm_id)
        )

    def charged_totals(self) -> dict[str, tuple[int, int, int, float]]:
        """Per-arm (attempted, input tokens, output tokens, usd) — the replay identity."""
        totals: dict[str, tuple[int, int, int, float]] = {}
        for entry in self.charged_entries():
            attempted, tokens_in, tokens_out, usd = totals.get(entry.arm_id, (0, 0, 0, 0.0))
            totals[entry.arm_id] = (
                attempted + 1,
                tokens_in + entry.input_tokens,
                tokens_out + entry.output_tokens,
                usd + entry.usd_cost,
            )
        return totals

    def assert_conserved(self) -> None:
        """The two ledger invariants, checked rather than assumed.

        ``physical <= sum(charged)``; and per arm, attempted == accepted + repaired + rejected
        over charged entries, with any unsettled entry a failure.
        """
        physical = sum(1 for e in self._entries if e.physical)
        charged = sum(1 for e in self._entries if not e.physical)
        assert physical <= charged, (
            f"physical calls ({physical}) exceed charged calls ({charged}): a call was made "
            "without being charged to every arm that would have made it"
        )
        by_arm: dict[str, list[CallLog]] = {}
        for entry in self.charged_entries():
            by_arm.setdefault(entry.arm_id, []).append(entry)
        for arm_id, entries in sorted(by_arm.items()):
            unsettled = [e.call_id for e in entries if e.outcome is None]
            assert not unsettled, f"arm {arm_id}: unsettled charged calls {unsettled}"
            classified = sum(
                1
                for e in entries
                if e.outcome
                in (
                    ParseOutcome.ACCEPTED,
                    ParseOutcome.ACCEPTED_AFTER_REPAIR,
                    ParseOutcome.FALLBACK,
                )
            )
            assert classified == len(entries), (
                f"arm {arm_id}: attempted {len(entries)} != classified {classified}"
            )

    def summary(self) -> LedgerSummary:
        by_arm: dict[str, list[CallLog]] = {}
        for entry in self.charged_entries():
            by_arm.setdefault(entry.arm_id, []).append(entry)
        per_arm: list[ArmTotals] = []
        for arm_id, entries in sorted(by_arm.items()):
            latencies = [e.latency_ms for e in entries]
            per_arm.append(
                ArmTotals(
                    arm_id=arm_id,
                    attempted=len(entries),
                    accepted=sum(1 for e in entries if e.outcome is ParseOutcome.ACCEPTED),
                    accepted_after_repair=sum(
                        1 for e in entries if e.outcome is ParseOutcome.ACCEPTED_AFTER_REPAIR
                    ),
                    rejected=sum(1 for e in entries if e.outcome is ParseOutcome.FALLBACK),
                    input_tokens=sum(e.input_tokens for e in entries),
                    output_tokens=sum(e.output_tokens for e in entries),
                    p50_latency_ms=_nearest_rank_ms(latencies, 0.50),
                    p95_latency_ms=_nearest_rank_ms(latencies, 0.95),
                    usd_cost=sum(e.usd_cost for e in entries),
                )
            )
        return LedgerSummary(
            physical=sum(1 for e in self._entries if e.physical),
            charged=sum(1 for e in self._entries if not e.physical),
            per_arm=tuple(per_arm),
            total_usd=sum(a.usd_cost for a in per_arm),
        )

    _CSV_HEADER = (
        "call_id,arm_id,episode_id,period,model_id,prompt_hash,decoding_hash,attempt_index,"
        "outcome,input_tokens,output_tokens,latency_ms,usd_cost,cache_hit,physical"
    )

    def to_csv(self, path: Path) -> None:
        """Byte-stable: insertion order, fixed formats, LF endings, trailing newline."""
        lines = [self._CSV_HEADER]
        for e in self._entries:
            lines.append(
                ",".join(
                    [
                        e.call_id,
                        e.arm_id,
                        e.episode_id,
                        str(e.period),
                        e.model_id,
                        e.prompt_hash,
                        e.decoding_hash,
                        str(e.attempt_index),
                        "" if e.outcome is None else str(e.outcome.value),
                        str(e.input_tokens),
                        str(e.output_tokens),
                        f"{e.latency_ms:.3f}",
                        f"{e.usd_cost:.10f}",
                        "true" if e.cache_hit else "false",
                        "true" if e.physical else "false",
                    ]
                )
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
