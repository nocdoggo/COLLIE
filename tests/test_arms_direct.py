"""Task 21 — direct-action arms 3, 4, and 11 on the benchmark-verbatim prompt.

The parser unit tests (part A) pin the transcribed upstream semantics; the arm tests (part B)
run the full channel stack (cache + ledger) over the runner and assert invocation timing,
prompt identity, accounting conservation, and legality. Byte-exactness of the prompt builders
themselves is proven in ``tests/test_prompts_verbatim.py`` against the executed upstream code;
here the prompt assertions are cross-arm identity and golden content.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from hypothesis import given, settings

from collie.arms.base_stock import CappedBaseStockController, base_stock_order
from collie.arms.direct import (
    ARM3_ARM_ID,
    ARM4_ARM_ID,
    ARM11_ARM_ID,
    DirectActionArm,
    parse_env_action,
    prompt_spec_from_episode,
    validates_as_action_json,
)
from collie.contracts import (
    ObservationMode,
    ParseOutcome,
    PeriodObservation,
    find_hidden_state,
)
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import RawResponse
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from tests.conftest import make_fallback
from tests.strategies_arms import demand_streams
from tests.test_episode_runner import make_instance

ITEM = "X1"  # make_instance's item id


def _spec(instance) -> object:
    """The prompt constants for ``instance`` — the horizon must match the episode being run."""
    return prompt_spec_from_episode(instance.spec, train_samples=())


def action_payload(qty, *, item: str = ITEM, insight: str = "") -> str:
    return json.dumps(
        {"rationale": "because reasons", "carry_over_insight": insight, "action": {item: qty}}
    )


class _ScriptedTrigger:
    """Fires on exactly the given periods. Test-local so the fired set is explicit."""

    arm_id = "scripted-trigger"

    def __init__(self, fire_periods: set[int]):
        self._fire = set(fire_periods)

    def should_propose(self, obs: PeriodObservation) -> bool:
        return obs.period in self._fire


@dataclass
class _RecordingTransport:
    """A ``Transport`` that records every (prompt, system) pair it physically serves."""

    default: str
    seen: list[tuple[str, str | None]] = field(default_factory=list)
    n_calls: int = 0

    @property
    def model_id(self) -> str:
        return "recording-fake-7b"

    def complete_metered(self, prompt: str, *, decoding, system: str | None = None) -> RawResponse:
        self.n_calls += 1
        self.seen.append((prompt, system))
        return RawResponse(
            text=self.default,
            prompt_tokens=len(prompt) // 4 + 1,
            completion_tokens=len(self.default) // 4 + 1,
            total_tokens=(len(prompt) + len(self.default)) // 4 + 2,
        )


@dataclass
class _QueueTransport(_RecordingTransport):
    """Serves a scripted sequence of texts, then the default, recording each call."""

    responses: list[str] = field(default_factory=list)

    def complete_metered(self, prompt: str, *, decoding, system: str | None = None) -> RawResponse:
        if self.responses:
            self.default = self.responses.pop(0)
        return super().complete_metered(prompt, decoding=decoding, system=system)


def _recording_harness(cache_root, default: str, responses: list[str] | None = None):
    transport = _QueueTransport(default=default, responses=list(responses or []))
    ledger = CallLedger()
    metered = MeteredClient(
        transport=transport,
        endpoint=scripted_endpoint(),
        cache=DiskCache(cache_root / "cache"),
        ledger=ledger,
    )
    return transport, ledger, metered


def _run(arm, instance):
    return EpisodeRunner(instance).run(arm)


# ---------------------------------------------------------------------------
# part A — the transcribed parser
# ---------------------------------------------------------------------------


def test_validate_accepts_plain_fenced_and_prose_wrapped() -> None:
    assert validates_as_action_json(action_payload(3))
    assert validates_as_action_json(f"```json\n{action_payload(3)}\n```")
    assert validates_as_action_json(f"Here is my decision:\n\n{action_payload(3)}\n\nThanks.")


def test_validate_rejects_non_json_and_actionless_json() -> None:
    assert not validates_as_action_json("no json here at all")
    assert not validates_as_action_json('{"rationale": "no action key"}')
    assert not validates_as_action_json('{"action": 42}')
    assert not validates_as_action_json('{"action": {"X1": 5')  # truncated


def test_parse_strategy_order_and_coercion() -> None:
    # Strategy 1: balanced JSON, int() truncation of a float quantity (env.py:578).
    assert parse_env_action(action_payload(7.9)) == {ITEM: 7}
    # Strategy 3: regex rescue of a broken document carrying a well-formed action object.
    broken = 'prefix {"rationale": "x", "action": {"X1": 12}, "carry'
    assert not validates_as_action_json(broken)
    assert parse_env_action(broken) == {ITEM: 12}
    # Strategy 4: last-resort digits pairs anywhere.
    assert parse_env_action('nothing parses {"108775044": 33} here') == {"108775044": 33}
    assert parse_env_action("total garbage") is None
    # A JSON-valid action with a non-numeric quantity validates but fails coercion everywhere.
    weird = json.dumps({"action": {ITEM: "lots"}})
    assert validates_as_action_json(weird)
    assert parse_env_action(weird) is None


def test_scanners_ignore_braces_inside_strings_and_escapes() -> None:
    """The balanced-brace scan is string-aware (env.py:542-568): ``{`` inside a quoted
    rationale, and an escaped quote before it, must not change depth bookkeeping."""
    payload = json.dumps(
        {"rationale": 'she said "hi { not a brace" and \\ paths', "action": {ITEM: 2}}
    )
    assert validates_as_action_json(payload)
    assert parse_env_action(payload) == {ITEM: 2}
    # A balanced block that is not JSON at all: the scan finds it, json.loads fails, done.
    assert not validates_as_action_json("{not json at all}")
    assert parse_env_action("{not json at all}") is None
    # No closing brace at all: strategies 1-3 fail, strategy 4 rescues a digits-id pair.
    assert parse_env_action('{"action": {"108775044": 5') == {"108775044": 5}


# ---------------------------------------------------------------------------
# part B — the arms over the full channel stack
# ---------------------------------------------------------------------------


def test_arm3_calls_every_period_and_orders_the_parsed_quantity(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0), lead_times=(0.0,) * 4)
    transport, ledger, metered = _recording_harness(tmp_path, action_payload(7))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = _run(arm, instance)
    assert transport.n_calls == 4  # one physical call per period, none shared
    assert all(d.llm_called and not d.triggered for d in outcome.decisions)
    assert [int(d.order_quantity) for d in outcome.decisions] == [7, 7, 7, 7]
    (totals,) = ledger.summary().per_arm
    assert totals.attempted == 4 and totals.accepted == 4
    assert totals.accepted_after_repair == 0 and totals.rejected == 0
    ledger.assert_conserved()


def test_arms_3_and_4_emit_identical_prompts_at_the_same_state(tmp_path) -> None:
    """The prompt-identity requirement: invocation timing must be the only treatment."""
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0), lead_times=(0.0,) * 4)
    default = action_payload(7)
    t3, _, m3 = _recording_harness(tmp_path / "a", default)
    arm3 = DirectActionArm(
        channel=m3.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    _run(arm3, instance)

    t4, _, m4 = _recording_harness(tmp_path / "b", default)
    arm4 = DirectActionArm(
        channel=m4.channel(arm_id=ARM4_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger({1, 2, 3, 4}),
        fallback=make_fallback(),
    )
    _run(arm4, instance)

    assert len(t3.seen) == len(t4.seen) == 4
    for (p3, s3), (p4, s4) in zip(t3.seen, t4.seen, strict=True):
        assert s3 == s4  # the system prompt
        assert p3 == p4  # the user prompt, byte for byte
        digest3 = hashlib.sha256((s3 + " " + p3).encode()).hexdigest()
        assert digest3 == hashlib.sha256((s4 + " " + p4).encode()).hexdigest()


def test_arm4_without_a_firing_never_calls_and_matches_the_fallback(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0), lead_times=(0.0,) * 4)
    transport, _, metered = _recording_harness(tmp_path, action_payload(7))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM4_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger(set()),
        fallback=make_fallback(),
    )
    outcome = _run(arm, instance)
    assert transport.n_calls == 0
    assert not any(d.llm_called or d.triggered for d in outcome.decisions)
    # Every order equals what arm 1 computes from the same observation.
    check = CappedBaseStockController()
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected


def test_arm4_calls_only_on_fired_periods(tmp_path) -> None:
    instance = make_instance(demand=(5.0,) * 6, lead_times=(0.0,) * 6)
    _, _, metered = _recording_harness(tmp_path, action_payload(9))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM4_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger({2, 5}),
        fallback=make_fallback(),
    )
    outcome = _run(arm, instance)
    fired = [d.period for d in outcome.decisions if d.llm_called]
    assert fired == [2, 5]
    assert [d.triggered for d in outcome.decisions] == [p in {2, 5} for p in range(1, 7)]
    assert [int(d.order_quantity) for d in outcome.decisions if d.llm_called] == [9, 9]
    # Non-fired periods order exactly what arm 1 would, given the arm's actual history.
    check = CappedBaseStockController()
    check.reset()
    for obs, dec in zip(outcome.observations, outcome.decisions, strict=True):
        if not dec.llm_called:
            assert dec.order_quantity == check.order(obs).order_quantity
        else:
            check.order(obs)


def test_repair_then_succeed_is_counted(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, ledger, metered = _recording_harness(
        tmp_path, action_payload(4), responses=["not json at all", action_payload(4)]
    )
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = _run(arm, instance)
    assert int(outcome.decisions[0].order_quantity) == 4
    period1 = [c for c in ledger.charged_entries() if c.period == 1]
    assert [c.attempt_index for c in period1] == [0, 1]
    assert [c.outcome for c in period1] == [
        ParseOutcome.FALLBACK,
        ParseOutcome.ACCEPTED_AFTER_REPAIR,
    ]
    # The repair was a distinct physical call (attempt-indexed cache key), both charged.
    assert sum(1 for c in ledger.entries if c.period == 1 and c.physical) == 2
    ledger.assert_conserved()


def test_always_invalid_orders_zero_and_settles_fallback(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, ledger, metered = _recording_harness(tmp_path, "useless prose, no braces")
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = _run(arm, instance)
    assert int(outcome.decisions[0].order_quantity) == 0
    period1 = [c for c in ledger.charged_entries() if c.period == 1]
    assert len(period1) == 3  # upstream's max_retries=3
    assert all(c.outcome is ParseOutcome.FALLBACK for c in period1)
    ledger.assert_conserved()


def test_env_parse_rescue_after_failed_validation_is_accepted_after_repair(tmp_path) -> None:
    """Upstream hands the env the final raw text; its forgiving parse can still yield an order."""
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    rescue = 'broken json but "action": {"X1": 11} recoverable'
    _, ledger, metered = _recording_harness(tmp_path, rescue)
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = _run(arm, instance)
    assert int(outcome.decisions[0].order_quantity) == 11
    period1 = [c for c in ledger.charged_entries() if c.period == 1]
    assert [c.outcome for c in period1] == [
        ParseOutcome.FALLBACK,
        ParseOutcome.FALLBACK,
        ParseOutcome.ACCEPTED_AFTER_REPAIR,
    ]


def test_unknown_item_and_negative_quantity_are_invalid_moves(tmp_path) -> None:
    for i, bad in enumerate((action_payload(3, item="NOT-X1"), action_payload(-4))):
        instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
        _, _, metered = _recording_harness(tmp_path / str(i), bad)
        arm = DirectActionArm(
            channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
            prompt_spec=_spec(instance),
        )
        outcome = _run(arm, instance)
        assert [int(d.order_quantity) for d in outcome.decisions] == [0, 0]


def test_carry_over_insight_enters_the_next_prompt_and_persists(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0,) * 3)
    transport, _, metered = _recording_harness(
        tmp_path,
        action_payload(7),
        responses=[
            action_payload(7, insight="Demand regime shifted up at Period 1"),
            action_payload(7),
        ],
    )
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    _run(arm, instance)
    period2_prompt = transport.seen[1][0]
    assert "CARRY-OVER INSIGHTS (Key Discoveries):" in period2_prompt
    assert "Period 1: Demand regime shifted up at Period 1" in period2_prompt
    # An empty memo later does not delete an earlier period's insight (upstream deletes only
    # the *current* period's key, and each period keys at most once).
    period3_prompt = transport.seen[2][0]
    assert "Period 1: Demand regime shifted up at Period 1" in period3_prompt


def test_empty_memo_deletes_the_current_periods_key(tmp_path) -> None:
    """Upstream's deletion branch (run_llm.py:889-890): an empty memo removes the current
    period's existing entry. Unreachable through the public flow (each period keys at most
    once, and a non-empty memo sets before the check), so it is pinned directly here — a
    'simplification' that drops the branch would silently diverge from upstream."""
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _recording_harness(tmp_path, action_payload(7))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    arm._update_insights(3, action_payload(7, insight="kept"))
    assert arm._history.insights == ((3, "kept"),)
    arm._update_insights(3, action_payload(7, insight=""))
    assert arm._history.insights == ()
    # A memo that is not a string (model wrote null) updates nothing.
    arm._update_insights(4, json.dumps({"carry_over_insight": None, "action": {ITEM: 1}}))
    assert arm._history.insights == ()
    # And a wholly unparseable response updates nothing (upstream's try/except).
    arm._update_insights(5, "not json")
    assert arm._history.insights == ()


def test_fifo_attribution_partially_consumes_an_overtaken_cohort(tmp_path) -> None:
    """A later order with a shorter actual lead time overtakes: 3 units arriving during period 2
    partially consume the 7-unit period-1 queue head. This is the declared FIFO approximation
    (module docstring, limit 1): the period-3 prompt misattributes those 3 units to the period-1
    dispatch, and the book stays conserved — period 4's conclusion splits the remaining 4 + 3
    and every arrived unit is attributed exactly once."""
    instance = make_instance(demand=(1.0, 1.0, 1.0, 1.0), lead_times=(2.0, 0.0, 0.0, 0.0))
    transport, _, metered = _recording_harness(
        tmp_path,
        action_payload(0),
        responses=[action_payload(7), action_payload(3)],
    )
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    _run(arm, instance)
    period3_prompt = transport.seen[2][0]
    # Truth: the 3 units are the period-2 same-period order. FIFO cannot know.
    assert "3 units (ordered on Period 1, lead_time was 1 periods)" in period3_prompt
    period4_prompt = transport.seen[3][0]
    assert "4 units (ordered on Period 1, lead_time was 2 periods)" in period4_prompt
    assert "3 units (ordered on Period 2, lead_time was 1 periods)" in period4_prompt


def test_censored_observations_are_refused(tmp_path) -> None:
    instance = make_instance(
        demand=(5.0, 6.0),
        lead_times=(0.0, 0.0),
        mode=ObservationMode.CENSORED,
    )
    _, _, metered = _recording_harness(tmp_path, action_payload(7))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    with pytest.raises(ValueError, match="UNCENSORED"):
        _run(arm, instance)


def test_arm11_quotes_the_or_recommendation_every_period(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0,) * 3)
    transport, _, metered = _recording_harness(tmp_path, action_payload(7))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM11_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        or_to_llm=True,
    )
    outcome = _run(arm, instance)
    assert transport.n_calls == 3
    assert all(d.llm_called for d in outcome.decisions)
    # The quoted recommendation equals arm 1's capped math from the same samples and state, and
    # rides in the dedicated suffix, not just anywhere in the prompt. The arm records demand
    # before deciding (arm 1's discipline), so the check does the same.
    demands: list[float] = []
    for obs, (prompt, _) in zip(outcome.observations, transport.seen, strict=True):
        if obs.period > 1:
            assert obs.prev_demand is not None
            demands.append(obs.prev_demand)
        expected = int(
            base_stock_order(
                samples=demands,
                on_hand=obs.on_hand,
                in_transit=obs.in_transit_total,
                promised_lead_time=obs.promised_lead_time,
                profit_per_unit=obs.profit_per_unit,
                holding_cost_per_unit=obs.holding_cost_per_unit,
            )
        )
        assert "OR ALGORITHM RECOMMENDATIONS" in prompt
        suffix = prompt.rsplit("OR ALGORITHM RECOMMENDATIONS", 1)[1]
        assert f"  {ITEM}: {expected} units" in suffix


def test_arm_construction_validation(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _recording_harness(tmp_path, action_payload(7))
    channel = metered.channel(arm_id="x", episode_id="y")
    with pytest.raises(ValueError, match="fallback"):
        DirectActionArm(channel=channel, prompt_spec=_spec(instance), trigger=_ScriptedTrigger({1}))
    with pytest.raises(ValueError, match="every-period"):
        DirectActionArm(
            channel=channel,
            prompt_spec=_spec(instance),
            or_to_llm=True,
            trigger=_ScriptedTrigger({1}),
            fallback=make_fallback(),
        )


def test_direct_arms_carry_no_hidden_state(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _recording_harness(tmp_path, action_payload(7))
    channel = metered.channel(arm_id="x", episode_id="y")
    spec = _spec(instance)
    arms = [
        DirectActionArm(channel=channel, prompt_spec=spec),
        DirectActionArm(
            channel=channel,
            prompt_spec=spec,
            trigger=_ScriptedTrigger({1}),
            fallback=make_fallback(),
        ),
        DirectActionArm(channel=channel, prompt_spec=spec, or_to_llm=True),
    ]
    for arm in arms:
        assert find_hidden_state(arm) == []


def test_runner_isolation_check_passes_for_direct_arms(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _recording_harness(tmp_path, action_payload(7))
    arm = DirectActionArm(
        channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    EpisodeRunner(instance, check_controller_isolation=True).run(arm)


# ---------------------------------------------------------------------------
# properties
# ---------------------------------------------------------------------------


@given(demands=demand_streams)
@settings(max_examples=30)
def test_order_legality_for_any_demand_stream(demands) -> None:
    """Every direct arm returns an integral, non-negative, correctly stamped decision."""
    instance = make_instance(
        demand=tuple(float(d) for d in demands), lead_times=(0.0,) * len(demands)
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, kwargs in enumerate(
            (
                {},
                {"trigger": _ScriptedTrigger({2, 4}), "fallback": make_fallback()},
                {"or_to_llm": True},
            )
        ):
            _, _, metered = _recording_harness(root / str(i), action_payload(7))
            arm = DirectActionArm(
                channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
                prompt_spec=_spec(instance),
                **kwargs,
            )
            outcome = _run(arm, instance)
            for obs, dec in zip(outcome.observations, outcome.decisions, strict=True):
                assert dec.period == obs.period
                assert dec.order_quantity >= 0 and float(dec.order_quantity).is_integer()


@given(demands=demand_streams)
@settings(max_examples=30)
def test_ledger_conservation_holds_for_the_direct_arms(demands) -> None:
    """attempted == accepted + repaired + rejected, and physical <= charged, on any stream."""
    instance = make_instance(
        demand=tuple(float(d) for d in demands), lead_times=(0.0,) * len(demands)
    )
    with tempfile.TemporaryDirectory() as td:
        _, ledger, metered = _recording_harness(Path(td), action_payload(7))
        arm = DirectActionArm(
            channel=metered.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
            prompt_spec=_spec(instance),
        )
        _run(arm, instance)
    ledger.assert_conserved()
    (totals,) = ledger.summary().per_arm
    assert totals.attempted == len(demands)
    assert totals.attempted == totals.accepted + totals.accepted_after_repair + totals.rejected


@given(demands=demand_streams)
@settings(max_examples=30)
def test_prompt_identity_holds_for_any_stream(demands) -> None:
    """Property form of the identity requirement: arms 3 and 4 never diverge in prompt bytes."""
    instance = make_instance(
        demand=tuple(float(d) for d in demands), lead_times=(0.0,) * len(demands)
    )
    default = action_payload(7)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        t3, _, m3 = _recording_harness(root / "a", default)
        _run(
            DirectActionArm(
                channel=m3.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
                prompt_spec=_spec(instance),
            ),
            instance,
        )
        t4, _, m4 = _recording_harness(root / "b", default)
        _run(
            DirectActionArm(
                channel=m4.channel(arm_id=ARM4_ARM_ID, episode_id=instance.spec.episode_id),
                prompt_spec=_spec(instance),
                trigger=_ScriptedTrigger(set(range(1, len(demands) + 1))),
                fallback=make_fallback(),
            ),
            instance,
        )
    assert [hashlib.sha256(p.encode()).hexdigest() for p, _ in t3.seen] == [
        hashlib.sha256(p.encode()).hexdigest() for p, _ in t4.seen
    ]
