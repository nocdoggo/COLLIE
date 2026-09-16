"""Checkpoint 1 demo: a 10-episode fake run's cost ledger, then a warm replay.

Two demo probe arms make the *same* proposal call at every trigger firing, which is what
produces one physical entry and two charged entries per firing. Episode 0's first firing runs a
scripted repair sequence (malformed, then valid) so the ledger shows a repair and a rejection.
The cold run writes the CSV; the warm replay runs over the populated cache with a fresh ledger
and a fresh transport that must record **zero** physical calls; the two ledgers' charged totals
(attempted, tokens, dated dollars — never latencies, which are measurements) must be identical.

Run: ``uv run python -m collie.llm.demo --episodes 10 --out /tmp/ledger.csv``.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from collie.contracts import ParseOutcome, PeriodObservation
from collie.fakes import fixture_episodes
from collie.fakes.fake_llm import canned
from collie.llm.cache import DiskCache
from collie.llm.client import (
    DecodingConfig,
    EndpointConfig,
    MeteredClient,
    RawResponse,
)
from collie.llm.ledger import CallLedger
from collie.trigger import FROZEN, AlertOrDetector, Cusum
from collie.trigger.protocol import MaxProposalsWrapper, RefractoryWrapper

__all__ = [
    "ScriptedTransport",
    "assert_warm_matches",
    "demo",
    "run_fake_sweep",
    "scripted_endpoint",
]


@dataclass
class ScriptedTransport:
    """A deterministic in-memory ``Transport``: scripted queue, then a default.

    Token counts are derived from the payload lengths — deterministic, nonzero, and clearly
    synthetic — so the accounting path is exercised with real arithmetic.
    """

    responses: list[str] = field(default_factory=list)
    default: str = canned.VALID
    model_id: str = "scripted-fake-7b"
    n_calls: int = 0

    def complete_metered(
        self, prompt: str, *, decoding: DecodingConfig, system: str | None = None
    ) -> RawResponse:
        self.n_calls += 1
        text = self.responses.pop(0) if self.responses else self.default
        prompt_tokens = (len(prompt) + len(system or "")) // 4 + 1
        completion_tokens = len(text) // 4 + 1
        return RawResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


def scripted_endpoint() -> EndpointConfig:
    """The in-memory endpoint standing in for a provider in tests and the demo.

    ``supports_seed=True`` so the robustness decoding path is exercisable; prices mirror the
    registered Gemini list prices so demo dollar figures are realistic in shape.
    """
    return EndpointConfig(
        name="scripted-fake",
        base_url="memory://none",
        model_id="scripted-fake-7b",
        key_env="SCRIPTED_FAKE_NEVER_USED",
        key_file=None,
        supports_seed=True,
        bills_thinking_as_output=False,
        price_input_per_mtok=0.75,
        price_output_per_mtok=3.75,
        price_date="2026-09-06",
    )


def _fixture_stream(index: int) -> tuple[str, list[PeriodObservation]]:
    fixture = fixture_episodes(seed=index // 6)[index % 6]
    spec = fixture.spec
    stream = [
        PeriodObservation(
            period=t,
            date=f"Period_{t}",
            on_hand=0.0,
            in_transit_total=0.0,
            prev_order=0.0,
            prev_arrivals=0.0,
            profit_per_unit=spec.profit_per_unit,
            holding_cost_per_unit=spec.holding_cost_per_unit,
            promised_lead_time=spec.promised_lead_time,
            prev_demand=0.0 if t == 1 else fixture.demand[t - 2],
            alert=fixture.alert
            if fixture.alert is not None and fixture.alert.period == t
            else None,
        )
        for t in range(1, spec.horizon + 1)
    ]
    return spec.episode_id, stream


def _classify(text: str, attempt_index: int) -> ParseOutcome:
    try:
        json.loads(text)
    except (ValueError, TypeError):
        return ParseOutcome.FALLBACK
    return ParseOutcome.ACCEPTED_AFTER_REPAIR if attempt_index else ParseOutcome.ACCEPTED


def run_fake_sweep(
    episodes: int, *, cache: DiskCache, ledger: CallLedger, transport: ScriptedTransport
) -> None:
    """One cold or warm sweep: two probe arms sharing every proposal call."""
    metered = MeteredClient(
        transport=transport, endpoint=scripted_endpoint(), cache=cache, ledger=ledger
    )
    for index in range(episodes):
        episode_id, stream = _fixture_stream(index)
        chain = MaxProposalsWrapper(
            RefractoryWrapper(
                AlertOrDetector(Cusum(FROZEN.mu0, FROZEN.sigma0, FROZEN.cusum_k, FROZEN.cusum_h)),
                FROZEN.refractory_window,
            ),
            FROZEN.max_proposals,
        )
        channels = [
            metered.channel(arm_id=arm, episode_id=episode_id)
            for arm in ("demo_probe_a", "demo_probe_b")
        ]
        for obs in stream:
            if not chain.should_propose(obs):
                continue
            prompt = (
                "Assess the demand regime for a ShockSpec proposal.\n"
                f"Decision point: {episode_id}#{obs.period}\n"
                f"prev_demand: {obs.prev_demand}"
            )
            for channel in channels:
                channel.set_period(obs.period)
                text = channel.complete(prompt)
                first_call = channel.last_call_id
                outcome = _classify(text, 0)
                if outcome is ParseOutcome.FALLBACK:
                    # One repair attempt: a re-ask with the format repeated. Counted as a
                    # second attempted call with attempt_index 1.
                    repair = prompt + "\nRespond with valid JSON only, no prose."
                    text = channel.complete_attempt(repair, decoding_hash="det-v1", attempt_index=1)
                    channel.settle(channel.last_call_id, _classify(text, 1))
                channel.settle(first_call, outcome)


def assert_warm_matches(
    cold_ledger: CallLedger, warm_ledger: CallLedger, warm_transport: ScriptedTransport
) -> None:
    """The replay verdict, as checks that are themselves tested (tests/test_cache_ledger.py)."""
    if warm_transport.n_calls != 0:
        raise AssertionError(
            f"warm replay made {warm_transport.n_calls} physical calls; the cache "
            "must serve every one"
        )
    if cold_ledger.charged_totals() != warm_ledger.charged_totals():
        raise AssertionError("warm replay charged totals differ from the cold run")


def demo(episodes: int, out: Path) -> str:
    """Run cold, write the CSV, replay warm, and compare charged totals."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(Path(tmp) / "cache")
        cold_ledger = CallLedger()
        cold_transport = ScriptedTransport(responses=[canned.MALFORMED_JSON])
        run_fake_sweep(episodes, cache=cache, ledger=cold_ledger, transport=cold_transport)
        cold_ledger.assert_conserved()
        cold_ledger.to_csv(out)

        warm_ledger = CallLedger()
        warm_transport = ScriptedTransport(responses=[canned.MALFORMED_JSON])
        run_fake_sweep(episodes, cache=cache, ledger=warm_ledger, transport=warm_transport)
        warm_ledger.assert_conserved()
        assert_warm_matches(cold_ledger, warm_ledger, warm_transport)

        summary = cold_ledger.summary()
        lines = [
            f"fake sweep: {episodes} episodes x 2 probe arms, trigger-gated proposal calls",
            f"physical calls: {summary.physical}   charged calls: {summary.charged}",
            f"cache entries: {len(cache)}   cold transport calls: {cold_transport.n_calls}",
            f"warm replay physical calls: {warm_transport.n_calls} (must be 0)",
            "warm replay charged totals identical to cold: True",
            f"total dated cost: ${summary.total_usd:.6f} (list prices 2026-09-06)",
            f"ledger CSV: {out}",
            "",
            "per-arm totals (charged side):",
        ]
        for arm in summary.per_arm:
            lines.append(
                f"  {arm.arm_id}: attempted={arm.attempted} accepted={arm.accepted} "
                f"repaired={arm.accepted_after_repair} rejected={arm.rejected} "
                f"in_tok={arm.input_tokens} out_tok={arm.output_tokens} "
                f"p50={arm.p50_latency_ms:.2f}ms p95={arm.p95_latency_ms:.2f}ms "
                f"usd={arm.usd_cost:.6f}"
            )
        return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m collie.llm.demo")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("/tmp/module06_ledger_demo.csv"))
    args = parser.parse_args(argv)
    print(demo(args.episodes, args.out))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
