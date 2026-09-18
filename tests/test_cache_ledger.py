"""Task 20 — the disk cache and the physical-versus-charged ledger.

The invariants under test are the ones the compute frontier stands on: cache keys that change
when any component changes, one physical call charged to every arm that would have made it, warm
replays with identical charged totals, and per-arm conservation of attempted calls. The stateful
machine at the bottom interleaves calls, cache hits, and replays across arms — the ordering bugs
a flat ``@given`` test would miss live there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from collie.contracts import ParseOutcome
from collie.llm import (
    DECODING_REGISTRY,
    CallLedger,
    DiskCache,
    MeteredClient,
    cache_key,
)
from collie.llm.demo import ScriptedTransport, run_fake_sweep, scripted_endpoint
from collie.llm.ledger import _nearest_rank_ms
from tests.strategies_arms import decoding

PROMPTS = st.text(alphabet=st.characters(categories=("L", "N", "P", "S")), min_size=1, max_size=200)


def _metered(tmp_path: Path, *, ledger: CallLedger | None = None, cache: DiskCache | None = None):
    transport = ScriptedTransport()
    metered = MeteredClient(
        transport=transport,
        endpoint=scripted_endpoint(),
        cache=cache or DiskCache(tmp_path / "cache"),
        ledger=ledger or CallLedger(),
    )
    return metered, transport


# ---------------------------------------------------------------------------
# cache keys
# ---------------------------------------------------------------------------


def test_cache_key_includes_full_prompt_hash() -> None:
    """The key is a SHA-256 over the full prompt text — recompute it independently."""
    import hashlib

    prompt = "x" * 100_000 + "a final character that a truncated hash would miss"
    key = cache_key(model_id="m", prompt=prompt, state="s", decoding_hash="det-v1")
    envelope = json.dumps(
        {
            "decoding_hash": "det-v1",
            "model_id": "m",
            "prompt": prompt,
            "state": "s",
            "system": None,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert key == "sha256:" + hashlib.sha256(envelope.encode("utf-8")).hexdigest()


def test_cache_key_sensitivity() -> None:
    """Changing ANY component changes the key."""
    base = dict(model_id="m", prompt="p", state="s", decoding_hash="det-v1", system=None)
    key = cache_key(**base)
    for field, value in (
        ("model_id", "m2"),
        ("prompt", "p "),
        ("state", "s2"),
        ("decoding_hash", "seed-1"),
        ("system", "sys"),
    ):
        assert cache_key(**{**base, field: value}) != key, field


@given(prompt_a=PROMPTS, prompt_b=PROMPTS)
@settings(max_examples=200)
def test_cache_key_determinism_and_prompt_sensitivity(prompt_a, prompt_b) -> None:
    first = cache_key(model_id="m", prompt=prompt_a, state="s", decoding_hash="det-v1")
    again = cache_key(model_id="m", prompt=prompt_a, state="s", decoding_hash="det-v1")
    assert first == again
    if prompt_a != prompt_b:
        other = cache_key(model_id="m", prompt=prompt_b, state="s", decoding_hash="det-v1")
        assert first != other


def test_disk_cache_roundtrip_and_atomic_write(tmp_path) -> None:
    cache = DiskCache(tmp_path / "cache")
    key = cache_key(model_id="m", prompt="p", state="s", decoding_hash="det-v1")
    assert cache.get(key) is None
    from collie.llm.client import RawResponse

    cache.put(key, RawResponse(text="hello", prompt_tokens=3, completion_tokens=2, total_tokens=5))
    assert cache.get(key) == {
        "text": "hello",
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
    }
    assert len(cache) == 1
    # Byte-stable and atomic: re-put leaves identical bytes, and no tmp files linger.
    path = next(iter((tmp_path / "cache").rglob("*.json")))
    before = path.read_bytes()
    cache.put(key, RawResponse(text="hello", prompt_tokens=3, completion_tokens=2, total_tokens=5))
    assert path.read_bytes() == before
    assert not list((tmp_path / "cache").rglob("*.tmp"))


# ---------------------------------------------------------------------------
# physical versus charged
# ---------------------------------------------------------------------------


def test_three_arms_one_call_gives_one_physical_three_charged(tmp_path) -> None:
    metered, transport = _metered(tmp_path)
    for arm in ("arm8", "arm9", "arm10"):
        channel = metered.channel(arm_id=arm, episode_id="ep1")
        channel.set_period(17)
        channel.complete("same prompt", decoding_hash="det-v1")
        channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)

    assert transport.n_calls == 1
    physical = [e for e in metered.ledger.entries if e.physical]
    charged = [e for e in metered.ledger.entries if not e.physical]
    assert len(physical) == 1 and len(charged) == 3
    assert physical[0].arm_id == "arm8"  # the arm that caused the request
    assert [e.arm_id for e in charged] == ["arm8", "arm9", "arm10"]
    assert [e.cache_hit for e in charged] == [False, True, True]
    # A cached call is charged as if made: same tokens, same dated dollars.
    assert len({(e.input_tokens, e.output_tokens, e.usd_cost) for e in charged}) == 1
    metered.ledger.assert_conserved()


def test_shared_call_returns_identical_text(tmp_path) -> None:
    metered, _t = _metered(tmp_path)
    texts = []
    for arm in ("arm8", "arm9", "arm10"):
        channel = metered.channel(arm_id=arm, episode_id="ep1")
        channel.set_period(17)
        texts.append(channel.complete("same prompt", decoding_hash="det-v1"))
    assert len(set(texts)) == 1


@given(
    arm_sets=st.lists(
        st.sampled_from(["arm2", "arm3", "arm4", "arm5", "arm6", "arm7", "arm8", "arm9", "arm10"]),
        min_size=1,
        max_size=10,
        unique=True,
    ),
    n_prompts=st.integers(min_value=1, max_value=6),
    decoding=decoding,
)
@settings(max_examples=200)
def test_physical_never_exceeds_charged(tmp_path_factory, arm_sets, n_prompts, decoding) -> None:
    """For any arm set sharing any prompt set, physical <= sum(charged)."""
    tmp = tmp_path_factory.mktemp("cache-ledger")
    metered, _transport = _metered(tmp)
    for arm in arm_sets:
        channel = metered.channel(arm_id=arm, episode_id="ep")
        channel.set_period(7)
        for i in range(n_prompts):
            channel.complete(f"prompt-{i}", decoding_hash=decoding)
            channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)
    metered.ledger.assert_conserved()
    physical = sum(1 for e in metered.ledger.entries if e.physical)
    charged = sum(1 for e in metered.ledger.entries if not e.physical)
    assert physical == n_prompts  # one per distinct prompt, no matter how many arms asked
    assert charged == n_prompts * len(arm_sets)


# ---------------------------------------------------------------------------
# warm replay
# ---------------------------------------------------------------------------


def test_warm_replay_returns_identical_responses(tmp_path) -> None:
    cache = DiskCache(tmp_path / "cache")
    cold_ledger, warm_ledger = CallLedger(), CallLedger()
    run_fake_sweep(6, cache=cache, ledger=cold_ledger, transport=ScriptedTransport())
    # The cold run's charged side is the reference: warm replays log charged entries only.
    cold_charged = [e.prompt_hash for e in cold_ledger.entries if not e.physical]

    warm_transport = ScriptedTransport()
    run_fake_sweep(6, cache=cache, ledger=warm_ledger, transport=warm_transport)
    assert warm_transport.n_calls == 0
    warm_charged = [e.prompt_hash for e in warm_ledger.entries]
    assert all(not e.physical for e in warm_ledger.entries)
    assert warm_charged == cold_charged


def test_warm_replay_identical_charged_totals(tmp_path) -> None:
    cache = DiskCache(tmp_path / "cache")
    cold_ledger, warm_ledger = CallLedger(), CallLedger()
    run_fake_sweep(10, cache=cache, ledger=cold_ledger, transport=ScriptedTransport())
    run_fake_sweep(10, cache=cache, ledger=warm_ledger, transport=ScriptedTransport())
    assert cold_ledger.charged_totals() == warm_ledger.charged_totals()
    cold_ledger.assert_conserved()
    warm_ledger.assert_conserved()


# ---------------------------------------------------------------------------
# ledger fields, conservation, settlement
# ---------------------------------------------------------------------------


def test_ledger_records_every_field(tmp_path) -> None:
    metered, _t = _metered(tmp_path)
    channel = metered.channel(arm_id="arm4", episode_id="ep9")
    channel.set_period(23)
    channel.complete("p", decoding_hash="det-v1")
    channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED_AFTER_REPAIR)
    (physical, charged) = metered.ledger.entries
    assert physical.physical and not physical.cache_hit
    for entry in (physical, charged):
        assert entry.call_id and entry.arm_id == "arm4"
        assert entry.episode_id == "ep9" and entry.period == 23
        assert entry.model_id == "scripted-fake-7b"
        assert entry.prompt_hash.startswith("sha256:")
        assert entry.decoding_hash == "det-v1"
        assert entry.attempt_index == 0
        assert entry.input_tokens > 0 and entry.output_tokens > 0
        assert entry.latency_ms >= 0.0
        assert entry.usd_cost > 0.0
    assert physical.outcome is None  # parsing is per-arm; the provider fact stays unclassified
    assert charged.outcome is ParseOutcome.ACCEPTED_AFTER_REPAIR


def test_conservation_fails_on_an_unsettled_entry(tmp_path) -> None:
    """Negative control: the conservation assertion must fire, or it is decoration."""
    metered, _t = _metered(tmp_path)
    channel = metered.channel(arm_id="arm3", episode_id="ep")
    channel.complete("p", decoding_hash="det-v1")
    with pytest.raises(AssertionError, match="unsettled"):
        metered.ledger.assert_conserved()


def test_double_settle_and_unknown_id_raise(tmp_path) -> None:
    metered, _t = _metered(tmp_path)
    channel = metered.channel(arm_id="arm3", episode_id="ep")
    channel.complete("p", decoding_hash="det-v1")
    call_id = channel.last_call_id
    channel.settle(call_id, ParseOutcome.ACCEPTED)
    with pytest.raises(ValueError, match="double-settle"):
        channel.settle(call_id, ParseOutcome.FALLBACK)
    with pytest.raises(KeyError):
        channel.settle("call-999999", ParseOutcome.ACCEPTED)


def test_summary_percentiles_and_totals(tmp_path) -> None:
    metered, _t = _metered(tmp_path)
    for arm in ("b", "a"):
        channel = metered.channel(
            arm_id=arm, episode_id=f"ep-{arm}"
        )  # distinct episodes: no sharing
        for i in range(3):
            channel.set_period(i + 1)
            channel.complete(f"p{i}", decoding_hash="det-v1")
            channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)
    summary = metered.ledger.summary()
    assert summary.physical == 6 and summary.charged == 6
    assert [a.arm_id for a in summary.per_arm] == ["a", "b"]  # sorted
    for arm in summary.per_arm:
        assert arm.attempted == arm.accepted == 3
        assert 0.0 <= arm.p50_latency_ms <= arm.p95_latency_ms
        assert arm.usd_cost > 0
    assert summary.total_usd == pytest.approx(sum(a.usd_cost for a in summary.per_arm))


def test_nearest_rank_percentile_exact() -> None:
    values = [10.0, 1.0, 5.0, 3.0, 7.0]
    assert _nearest_rank_ms(values, 0.5) == 5.0
    assert _nearest_rank_ms(values, 0.95) == 10.0
    assert _nearest_rank_ms([], 0.5) == 0.0


def test_cache_root_and_empty_length(tmp_path) -> None:
    cache = DiskCache(tmp_path / "nothing-here")
    assert cache.root == tmp_path / "nothing-here"
    assert len(cache) == 0  # root not yet created


def test_system_message_is_part_of_the_key(tmp_path) -> None:
    """The same user prompt with and without a system message is two different calls."""
    metered, transport = _metered(tmp_path)
    channel = metered.channel(arm_id="arm3", episode_id="ep")
    channel.set_period(4)
    assert channel.model_id == "scripted-fake-7b"
    channel.complete("p", decoding_hash="det-v1")
    channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)
    channel.complete_with_system("sys", "p", decoding_hash="det-v1")
    channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)
    assert transport.n_calls == 2  # no cache hit across the system boundary


def test_demo_end_to_end(tmp_path) -> None:
    from collie.llm.demo import demo, main

    out = tmp_path / "ledger.csv"
    text = demo(4, out)
    assert "warm replay physical calls: 0" in text
    assert "warm replay charged totals identical to cold: True" in text
    assert out.read_text().splitlines()[0].startswith("call_id,arm_id")
    main_out = tmp_path / "ledger2.csv"
    main(["--episodes", "4", "--out", str(main_out)])
    assert main_out.is_file()


def test_demo_verdict_checks_fire(tmp_path) -> None:
    """Negative control: the demo's own replay assertions must fail loudly when violated."""
    from collie.llm.demo import assert_warm_matches

    cache = DiskCache(tmp_path / "cache")
    cold, warm = CallLedger(), CallLedger()
    run_fake_sweep(2, cache=cache, ledger=cold, transport=ScriptedTransport())

    # A "warm" replay that physically called the provider.
    leaky_transport = ScriptedTransport()
    leaky_transport.complete_metered("p", decoding=DECODING_REGISTRY["det-v1"], system=None)
    with pytest.raises(AssertionError, match="physical calls"):
        assert_warm_matches(cold, warm, leaky_transport)

    # A warm replay whose charged totals drifted.
    drifted = CallLedger()
    metered = MeteredClient(
        transport=ScriptedTransport(),
        endpoint=scripted_endpoint(),
        cache=cache,
        ledger=drifted,
    )
    channel = metered.channel(arm_id="demo_probe_a", episode_id="extra")
    channel.complete("one more call than the cold run", decoding_hash="det-v1")
    with pytest.raises(AssertionError, match="charged totals differ"):
        assert_warm_matches(cold, drifted, ScriptedTransport())


def test_csv_is_byte_stable_and_complete(tmp_path) -> None:
    metered, _t = _metered(tmp_path)
    channel = metered.channel(arm_id="arm3", episode_id="ep")
    channel.set_period(4)
    channel.complete("p", decoding_hash="det-v1")
    channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    metered.ledger.to_csv(first)
    metered.ledger.to_csv(second)
    assert first.read_bytes() == second.read_bytes()
    lines = first.read_text().splitlines()
    assert lines[0].startswith("call_id,arm_id,episode_id,period,")
    assert len(lines) == 3  # header + one physical + one charged
    assert lines[1].endswith(",false,true")
    assert lines[2].endswith(",false,false")


# ---------------------------------------------------------------------------
# the stateful machine: interleaved calls, hits, and replays
# ---------------------------------------------------------------------------


class CacheLedgerMachine(RuleBasedStateMachine):
    """Interleave calls across arms and decoding configs with full warm replays.

    Model state: the sequence of (arm, episode, period, prompt, decoding) calls made and the
    distinct cache keys they imply. Invariants after every step: physical == number of distinct
    keys; physical <= charged; per-arm attempted equals the model's count; conservation holds
    (every call is settled inline).
    """

    def __init__(self) -> None:
        super().__init__()
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.cache = DiskCache(Path(self._tmp.name) / "cache")
        self.ledger = CallLedger()
        self.transport = ScriptedTransport()
        self.metered = MeteredClient(
            transport=self.transport,
            endpoint=scripted_endpoint(),
            cache=self.cache,
            ledger=self.ledger,
        )
        self.calls: list[tuple[str, str, int, str, str]] = []

    def teardown(self) -> None:
        self._tmp.cleanup()

    @rule(
        arm=st.sampled_from(["arm8", "arm9", "arm10"]),
        episode=st.sampled_from(["ep0", "ep1"]),
        period=st.integers(min_value=1, max_value=4),
        prompt=st.sampled_from(["alpha", "beta", "gamma"]),
        decoding=decoding,
        outcome=st.sampled_from(
            [ParseOutcome.ACCEPTED, ParseOutcome.ACCEPTED_AFTER_REPAIR, ParseOutcome.FALLBACK]
        ),
    )
    def call(self, arm, episode, period, prompt, decoding, outcome) -> None:
        channel = self.metered.channel(arm_id=arm, episode_id=episode)
        channel.set_period(period)
        channel.complete(prompt, decoding_hash=decoding)
        channel.settle(channel.last_call_id, outcome)
        self.calls.append((arm, episode, period, prompt, decoding))

    @rule()
    def warm_replay(self) -> None:
        """A full replay over the warm cache: zero physical calls, identical charged totals."""
        replay_ledger = CallLedger()
        replay_transport = ScriptedTransport()
        metered = MeteredClient(
            transport=replay_transport,
            endpoint=scripted_endpoint(),
            cache=self.cache,
            ledger=replay_ledger,
        )
        for arm, episode, period, prompt, dec in self.calls:
            channel = metered.channel(arm_id=arm, episode_id=episode)
            channel.set_period(period)
            channel.complete(prompt, decoding_hash=dec)
            channel.settle(channel.last_call_id, ParseOutcome.ACCEPTED)
        assert replay_transport.n_calls == 0
        assert replay_ledger.charged_totals() == self.ledger.charged_totals()

    @invariant()
    def physical_equals_distinct_keys_and_never_exceeds_charged(self) -> None:
        physical = [e for e in self.ledger.entries if e.physical]
        charged = [e for e in self.ledger.entries if not e.physical]
        assert len(physical) == len({e.prompt_hash for e in charged})
        assert len(physical) <= len(charged)
        per_arm: dict[str, int] = {}
        for arm, _episode, _period, _prompt, _decoding in self.calls:
            per_arm[arm] = per_arm.get(arm, 0) + 1
        for arm, count in per_arm.items():
            assert len(self.ledger.charged_entries(arm)) == count
        self.ledger.assert_conserved()


TestCacheLedger = CacheLedgerMachine.TestCase
TestCacheLedger.settings = settings(max_examples=10, stateful_step_count=30, deadline=None)
