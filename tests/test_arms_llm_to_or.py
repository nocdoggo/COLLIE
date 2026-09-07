"""Task 21 — LLM-to-OR arms 5, 6, 7 (upstream ``llm_to_or`` semantics).

Part A pins the transcribed backend (compute methods, order formula, parse machinery,
validation). Part B runs the arms over the runner with the full channel stack: cadence,
arms 4/6 matched on realised calls, persistence, counted fallbacks, and the prompt-identity
requirement (the user message is byte-identical to the direct arms').
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from scipy.stats import norm

from collie.arms.base_stock import CappedBaseStockController
from collie.arms.direct import ARM3_ARM_ID, ARM4_ARM_ID, DirectActionArm
from collie.arms.llm_to_or import (
    ARM5_ARM_ID,
    ARM6_ARM_ID,
    ARM7_ARM_ID,
    DEFAULT_PARAMETERS,
    PERSISTENCE_EXPIRY,
    LlmToOrArm,
    compute_L,
    compute_mu_hat,
    compute_sigma_hat,
    extract_parameters_regex,
    llm_to_or_order,
    robust_parse_json,
    validate_item_parameters,
    validates_llm_to_or_response,
)
from collie.contracts import ParseOutcome, find_hidden_state
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.client import RawResponse
from collie.llm.demo import scripted_endpoint
from collie.sim.runner import EpisodeRunner
from tests.strategies_arms import demand_streams
from tests.test_arms_direct import (
    _RecordingTransport,
    _ScriptedTrigger,
    _spec,
)
from tests.test_episode_runner import make_instance

ITEM = "X1"


def params_payload(item_params: dict, *, item: str = ITEM, insight: str = "") -> str:
    return json.dumps(
        {
            "rationale": "demand looks elevated",
            "carry_over_insight": insight,
            "parameters": {item: item_params},
        }
    )


ALL_DEFAULT = params_payload(
    {
        "L": {"method": "default"},
        "mu_hat": {"method": "default"},
        "sigma_hat": {"method": "default"},
    }
)


def _harness(root: Path, default: str, responses: list[str] | None = None):
    transport = _RecordingTransport(default=default)
    if responses is not None:
        queued = list(responses)

        def complete_metered(prompt, *, decoding, system=None):
            # Pop the script without mutating ``default``: a scripted response is served once,
            # not latched (latching would make later periods silently reuse the first script).
            text = queued.pop(0) if queued else default
            transport.n_calls += 1
            transport.seen.append((prompt, system))
            return RawResponse(
                text=text,
                prompt_tokens=len(prompt) // 4 + 1,
                completion_tokens=len(text) // 4 + 1,
                total_tokens=(len(prompt) + len(text)) // 4 + 2,
            )

        transport.complete_metered = complete_metered
    ledger = CallLedger()
    metered = MeteredClient(
        transport=transport,
        endpoint=scripted_endpoint(),
        cache=DiskCache(root / "cache"),
        ledger=ledger,
    )
    return transport, ledger, metered


# ---------------------------------------------------------------------------
# part A — the transcribed backend
# ---------------------------------------------------------------------------


def test_compute_L_methods() -> None:
    assert compute_L("default", {}, [], 4) == 4.0
    assert compute_L("calculate", {}, [], 4) == 4.0  # no observations yet -> promised
    assert compute_L("calculate", {}, [2, 4], 4) == 3.0
    assert compute_L("recent_N", {"N": 2}, [1, 2, 4, 4], 0) == 4.0
    assert compute_L("recent_N", {"N": 9}, [2, 4], 0) == 3.0  # short history -> all of it
    assert compute_L("explicit", {"value": 3}, [], 0) == 3.0
    with pytest.raises(ValueError, match="requires 'N'"):
        compute_L("recent_N", {}, [2], 0)
    with pytest.raises(ValueError, match="N must be >= 1"):
        compute_L("recent_N", {"N": 0}, [2], 0)
    with pytest.raises(ValueError, match="requires 'value'"):
        compute_L("explicit", {}, [], 0)
    with pytest.raises(ValueError, match="Invalid method for L"):
        compute_L("guess", {}, [], 0)


def test_compute_mu_hat_methods() -> None:
    samples = [10.0, 20.0, 40.0]
    assert compute_mu_hat("default", {}, samples, 2) == pytest.approx(3 * 70 / 3)
    assert compute_mu_hat("default", {}, [], 2) == 0.0
    assert compute_mu_hat("recent_N", {"N": 2}, samples, 1) == pytest.approx(2 * 30.0)
    # EWMA newest-first, weights 1, gamma, gamma^2: (40 + 0.5*20 + 0.25*10) / 1.75 * (1+1).
    assert compute_mu_hat("EWMA_gamma", {"gamma": 0.5}, samples, 1) == pytest.approx(
        2 * (40 + 10 + 2.5) / 1.75
    )
    # gamma=0 degenerates to the newest sample only (0**0 == 1.0 in the loop's first step).
    assert compute_mu_hat("EWMA_gamma", {"gamma": 0.0}, samples, 0) == pytest.approx(40.0)
    # explicit is used RAW — no (1+L) scaling, despite the menu prose (notes §1.5).
    assert compute_mu_hat("explicit", {"value": 7.0}, samples, 4) == 7.0
    with pytest.raises(ValueError, match="gamma must be in"):
        compute_mu_hat("EWMA_gamma", {"gamma": 1.5}, samples, 0)
    with pytest.raises(ValueError, match="Invalid method for mu_hat"):
        compute_mu_hat("calculate", {}, samples, 0)


def test_compute_sigma_hat_methods() -> None:
    samples = [10.0, 20.0, 40.0]
    assert compute_sigma_hat("default", {}, samples, 3) == pytest.approx(
        2.0 * float(np.std(samples, ddof=1))
    )
    assert compute_sigma_hat("default", {}, [5.0], 3) == 0.0  # fewer than two samples
    assert compute_sigma_hat("recent_N", {"N": 2}, samples, 0) == pytest.approx(
        float(np.std([20.0, 40.0], ddof=1))
    )
    assert compute_sigma_hat("recent_N", {"N": 1}, samples, 0) == 0.0  # one sample window
    assert compute_sigma_hat("explicit", {"value": 2.5}, samples, 3) == 2.5
    with pytest.raises(ValueError, match="Invalid method for sigma_hat"):
        compute_sigma_hat("EWMA_gamma", {}, samples, 0)


def test_llm_to_or_order_is_arm1_math_with_a_cap() -> None:
    # Hand-computed: mu=12, sigma=3, L=2, profit 4, holding 1 -> q=0.8, z=ppf(0.8).
    z = float(norm.ppf(0.8))
    base_stock = 12.0 + z * 3.0
    expected_uncapped = max(math.ceil(base_stock - 5.0), 0)
    cap = 12.0 / 3.0 + float(norm.ppf(0.95)) * 3.0 / math.sqrt(3.0)
    expected = max(min(expected_uncapped, math.ceil(cap)), 0)
    assert (
        llm_to_or_order(
            lead_time=2.0,
            mu_hat=12.0,
            sigma_hat=3.0,
            on_hand=2.0,
            in_transit=3.0,
            profit=4.0,
            holding=1.0,
        )
        == expected
    )


def test_llm_to_or_order_out_of_range_raises_for_the_caller_to_count() -> None:
    with pytest.raises((ValueError, ZeroDivisionError)):
        llm_to_or_order(
            lead_time=-1.0,
            mu_hat=12.0,
            sigma_hat=3.0,
            on_hand=0.0,
            in_transit=0.0,
            profit=4.0,
            holding=1.0,
        )


def test_robust_parse_json_never_fails() -> None:
    payload = params_payload(
        {
            "L": {"method": "explicit", "value": 2},
            "mu_hat": {"method": "default"},
            "sigma_hat": {"method": "default"},
        }
    )
    assert robust_parse_json(payload)["parameters"][ITEM]["L"]["value"] == 2
    # The classic missing-opening-brace error is repaired (step 3).
    assert robust_parse_json(payload.lstrip("{"))["parameters"][ITEM]["L"]["value"] == 2
    # Trailing commas and fences are repaired (step 1).
    messy = '```json\n{"rationale": "x", "parameters": {},}\n```'
    assert robust_parse_json(messy)["parameters"] == {}
    # Pure prose falls through to the regex fallback, which always yields defaults.
    salvaged = robust_parse_json("no json whatsoever")
    assert salvaged["parameters"]["__default__"] == DEFAULT_PARAMETERS


def test_extract_parameters_regex_salvages_explicit_values() -> None:
    text = '"L_method": "explicit", "L_value": 3, "mu_hat_method": "recent_N", "N": 7'
    result = extract_parameters_regex(text)
    default = result["parameters"]["__default__"]
    assert default["L"] == {"method": "explicit", "value": 3.0}
    assert default["mu_hat"] == {"method": "recent_N", "N": 7}
    assert default["sigma_hat"] == {"method": "default"}


def test_validate_item_parameters_structure_and_default_expansion() -> None:
    good = json.loads(ALL_DEFAULT)
    assert validate_item_parameters(good, ITEM)["L"] == {"method": "default"}
    # __default__ expands to the item (without mutating the payload).
    via_default = {"parameters": {"__default__": dict(DEFAULT_PARAMETERS)}}
    assert validate_item_parameters(via_default, ITEM)["mu_hat"] == {"method": "default"}
    assert ITEM not in via_default["parameters"]  # no mutation of the input mapping
    with pytest.raises(ValueError, match="must contain 'parameters'"):
        validate_item_parameters({"rationale": "x"}, ITEM)
    with pytest.raises(ValueError, match="Missing parameters"):
        validate_item_parameters({"parameters": {"WRONG": dict(DEFAULT_PARAMETERS)}}, ITEM)
    bad_method = json.loads(ALL_DEFAULT)
    bad_method["parameters"][ITEM]["mu_hat"]["method"] = "calculate"  # L-only method
    with pytest.raises(ValueError, match="Invalid mu_hat method"):
        validate_item_parameters(bad_method, ITEM)
    missing_gamma = json.loads(ALL_DEFAULT)
    missing_gamma["parameters"][ITEM]["mu_hat"] = {"method": "EWMA_gamma"}
    with pytest.raises(ValueError, match="requires 'gamma'"):
        validate_item_parameters(missing_gamma, ITEM)


def test_weak_gate_matches_upstream() -> None:
    assert validates_llm_to_or_response(ALL_DEFAULT)
    assert validates_llm_to_or_response("the method should be default")
    assert not validates_llm_to_or_response("")
    assert not validates_llm_to_or_response("   ")
    assert not validates_llm_to_or_response("no relevant content")


# ---------------------------------------------------------------------------
# part B — the arms
# ---------------------------------------------------------------------------


def test_arm5_calls_every_period_and_default_params_reproduce_arm1(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0), lead_times=(0.0,) * 4)
    transport, ledger, metered = _harness(tmp_path, ALL_DEFAULT)
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = EpisodeRunner(instance).run(arm)
    assert transport.n_calls == 4
    assert all(d.llm_called and not d.triggered for d in outcome.decisions)
    # With default parameters the backend IS arm 1's math on the same history.
    check = CappedBaseStockController()
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected
    (totals,) = ledger.summary().per_arm
    assert totals.attempted == 4 and totals.accepted == 4 and totals.rejected == 0
    ledger.assert_conserved()


def test_arm5_explicit_parameters_change_the_order(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0), lead_times=(0.0,) * 4)
    big = params_payload(
        {
            "L": {"method": "explicit", "value": 4},
            "mu_hat": {"method": "explicit", "value": 100},
            "sigma_hat": {"method": "explicit", "value": 10},
        }
    )
    _, _, metered = _harness(tmp_path, big)
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = EpisodeRunner(instance).run(arm)
    # Hand-computed first-period order from the raw explicit values (no (1+L) rescaling).
    z = float(norm.ppf(4 / 5))
    base_stock = 100.0 + z * 10.0
    uncapped = max(math.ceil(base_stock - 0.0), 0)
    cap = 100.0 / 5.0 + float(norm.ppf(0.95)) * 10.0 / math.sqrt(5.0)
    expected = max(min(uncapped, math.ceil(cap)), 0)
    assert int(outcome.decisions[0].order_quantity) == expected
    assert expected > 0


def test_arms_4_and_6_are_matched_on_realised_calls(tmp_path) -> None:
    """R3.6: the same wrapped trigger over the same episode fires identically for both."""
    instance = make_instance(demand=(5.0,) * 8, lead_times=(0.0,) * 8)
    fire = {3, 6}
    _, _, m4 = _harness(
        tmp_path / "a",
        json.dumps({"rationale": "r", "carry_over_insight": "", "action": {ITEM: 5}}),
    )
    arm4 = DirectActionArm(
        channel=m4.channel(arm_id=ARM4_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger(fire),
        fallback=CappedBaseStockController(),
    )
    out4 = EpisodeRunner(instance).run(arm4)
    _, _, m6 = _harness(tmp_path / "b", ALL_DEFAULT)
    arm6 = LlmToOrArm(
        channel=m6.channel(arm_id=ARM6_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger(fire),
    )
    out6 = EpisodeRunner(instance).run(arm6)
    calls4 = [d.period for d in out4.decisions if d.llm_called]
    calls6 = [d.period for d in out6.decisions if d.llm_called]
    assert calls4 == calls6 == sorted(fire)


def test_arm6_between_calls_is_exactly_arm1(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0, 7.0, 8.0, 9.0), lead_times=(0.0,) * 5)
    _, _, metered = _harness(tmp_path, ALL_DEFAULT)
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM6_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger(set()),
    )
    outcome = EpisodeRunner(instance).run(arm)
    check = CappedBaseStockController()
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected
    assert not any(d.llm_called for d in outcome.decisions)


def test_arm7_persists_for_the_fixed_expiry_then_reverts(tmp_path) -> None:
    horizon = 10
    instance = make_instance(demand=(5.0,) * horizon, lead_times=(0.0,) * horizon)
    big = params_payload(
        {
            "L": {"method": "explicit", "value": 4},
            "mu_hat": {"method": "explicit", "value": 200},
            "sigma_hat": {"method": "explicit", "value": 0},
        }
    )
    _, _, metered = _harness(tmp_path, big)
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM7_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger({3}),
        expiry=PERSISTENCE_EXPIRY,
    )
    outcome = EpisodeRunner(instance).run(arm)
    assert [d.period for d in outcome.decisions if d.llm_called] == [3]
    # Periods 3..7 carry the persisted parameters (mu 200 raw): the order is the huge capped
    # value, not arm 1's. Period 8 reverts to defaults (window [3, 3+5)).
    cap = 200.0 / 5.0  # sigma 0 kills the second term
    persisted = math.ceil(cap)
    for d in outcome.decisions:
        if d.period in (3, 4, 5, 6, 7):
            assert int(d.order_quantity) == persisted, f"period {d.period}"
    assert int(outcome.decisions[7].order_quantity) != persisted  # period 8: default again


def test_arm7_failed_call_does_not_refresh_persistence(tmp_path) -> None:
    horizon = 9
    instance = make_instance(demand=(5.0,) * horizon, lead_times=(0.0,) * horizon)
    good = params_payload(
        {
            "L": {"method": "explicit", "value": 4},
            "mu_hat": {"method": "explicit", "value": 200},
            "sigma_hat": {"method": "explicit", "value": 0},
        }
    )
    _, ledger, metered = _harness(tmp_path, "total garbage", responses=[good])
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM7_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
        trigger=_ScriptedTrigger({2, 4}),
        expiry=3,
    )
    outcome = EpisodeRunner(instance).run(arm)
    assert [d.period for d in outcome.decisions if d.llm_called] == [2, 4]
    # Period 2 succeeds: window [2, 5). Period 4's call is garbage -> counted fallback, the
    # period-2 parameters still govern period 4 (window intact), expiry arrives at 5.
    persisted = math.ceil(200.0 / 5.0)
    for d in outcome.decisions:
        if d.period in (2, 3, 4):
            assert int(d.order_quantity) == persisted, f"period {d.period}"
    assert int(outcome.decisions[4].order_quantity) != persisted  # period 5: default
    rejected = [c for c in ledger.charged_entries() if c.period == 4]
    assert rejected and all(c.outcome is ParseOutcome.FALLBACK for c in rejected)


def test_structurally_valid_but_out_of_range_values_are_a_counted_fallback(tmp_path) -> None:
    """Upstream dies on sys.exit(1) here (notes §1.5); we count it and order with defaults."""
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0,) * 3)
    bad = params_payload(
        {
            "L": {"method": "explicit", "value": -1},  # 1+L == 0: the cap divides by zero
            "mu_hat": {"method": "explicit", "value": 100},
            "sigma_hat": {"method": "explicit", "value": 10},
        }
    )
    _, ledger, metered = _harness(tmp_path, bad)
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = EpisodeRunner(instance).run(arm)
    # No crash, and the orders are the default-parameter (arm-1) orders.
    check = CappedBaseStockController()
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected
    assert all(
        c.outcome is ParseOutcome.FALLBACK for c in ledger.charged_entries() if c.period == 1
    )


def test_unusable_json_orders_with_defaults_and_is_counted(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, ledger, metered = _harness(tmp_path, "no relevant content")
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = EpisodeRunner(instance).run(arm)
    check = CappedBaseStockController()
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected
    # All three upstream attempts fail the weak gate; the final one settles FALLBACK because the
    # regex fallback only recovered defaults (the gate never passed).
    period1 = [c for c in ledger.charged_entries() if c.period == 1]
    assert len(period1) == 3
    assert all(c.outcome is ParseOutcome.FALLBACK for c in period1)


def test_llm_to_or_user_prompt_is_byte_identical_to_the_direct_arms(tmp_path) -> None:
    """Notes §1.5: the llm_to_or user message is the llm strategy's user message.

    The histories coincide only if the arms' *orders* coincide, so arm 5's script drives its
    backend to the same [7, 7, 7] arm 3 is scripted to order (raw explicit parameters: mu 7, 9,
    10 against on-hand 0, 2, 3 — cap arithmetic hand-checked). That both prompt streams then
    match byte for byte proves the shared history module renders one true text channel.
    """
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0,) * 3)

    def explicit(mu: float) -> str:
        return params_payload(
            {
                "L": {"method": "explicit", "value": 0},
                "mu_hat": {"method": "explicit", "value": mu},
                "sigma_hat": {"method": "explicit", "value": 0},
            }
        )

    t3, _, m3 = _harness(
        tmp_path / "a",
        json.dumps({"rationale": "r", "carry_over_insight": "", "action": {ITEM: 7}}),
    )
    out3 = EpisodeRunner(instance).run(
        DirectActionArm(
            channel=m3.channel(arm_id=ARM3_ARM_ID, episode_id=instance.spec.episode_id),
            prompt_spec=_spec(instance),
        )
    )
    t5, _, m5 = _harness(
        tmp_path / "b", ALL_DEFAULT, responses=[explicit(7), explicit(9), explicit(10)]
    )
    out5 = EpisodeRunner(instance).run(
        LlmToOrArm(
            channel=m5.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
            prompt_spec=_spec(instance),
        )
    )
    # Sanity on the scripting itself: the two arms really did place identical orders.
    assert [d.order_quantity for d in out3.decisions] == [7.0, 7.0, 7.0]
    assert [d.order_quantity for d in out5.decisions] == [7.0, 7.0, 7.0]
    assert [p for p, _ in t3.seen] == [p for p, _ in t5.seen]
    assert all(s3 != s5 for (_, s3), (_, s5) in zip(t3.seen, t5.seen, strict=True))


def test_llm_to_or_arm_construction_and_isolation(tmp_path) -> None:
    instance = make_instance(demand=(5.0, 6.0), lead_times=(0.0, 0.0))
    _, _, metered = _harness(tmp_path, ALL_DEFAULT)
    channel = metered.channel(arm_id="x", episode_id="y")
    with pytest.raises(ValueError, match="arm 5"):
        LlmToOrArm(channel=channel, prompt_spec=_spec(instance), expiry=5)
    with pytest.raises(ValueError, match=">= 1"):
        LlmToOrArm(
            channel=channel,
            prompt_spec=_spec(instance),
            trigger=_ScriptedTrigger({1}),
            expiry=0,
        )
    for arm in (
        LlmToOrArm(channel=channel, prompt_spec=_spec(instance)),
        LlmToOrArm(channel=channel, prompt_spec=_spec(instance), trigger=_ScriptedTrigger({1})),
        LlmToOrArm(
            channel=channel,
            prompt_spec=_spec(instance),
            trigger=_ScriptedTrigger({1}),
            expiry=3,
        ),
    ):
        assert find_hidden_state(arm) == []


@given(demands=demand_streams)
@settings(max_examples=20)
def test_llm_to_or_order_legality_for_any_stream(demands) -> None:
    instance = make_instance(
        demand=tuple(float(d) for d in demands), lead_times=(0.0,) * len(demands)
    )
    with tempfile.TemporaryDirectory() as td:
        _, ledger, metered = _harness(Path(td), ALL_DEFAULT)
        arm = LlmToOrArm(
            channel=metered.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
            prompt_spec=_spec(instance),
        )
        outcome = EpisodeRunner(instance).run(arm)
    for obs, dec in zip(outcome.observations, outcome.decisions, strict=True):
        assert dec.period == obs.period
        assert dec.order_quantity >= 0 and float(dec.order_quantity).is_integer()
    ledger.assert_conserved()


# ---------------------------------------------------------------------------
# part A.2 — branch completion over the transcribed machinery
# ---------------------------------------------------------------------------


def test_compute_L_recent_N_without_observations_falls_back_to_promised() -> None:
    assert compute_L("recent_N", {"N": 3}, [], 2) == 2.0


def test_compute_mu_hat_missing_fields_raise() -> None:
    samples = [10.0, 20.0]
    with pytest.raises(ValueError, match="requires 'value'"):
        compute_mu_hat("explicit", {}, samples, 0)
    with pytest.raises(ValueError, match="requires 'N'"):
        compute_mu_hat("recent_N", {}, samples, 0)
    with pytest.raises(ValueError, match="N must be >= 1"):
        compute_mu_hat("recent_N", {"N": 0}, samples, 0)
    with pytest.raises(ValueError, match="requires 'gamma'"):
        compute_mu_hat("EWMA_gamma", {}, samples, 0)


def test_compute_sigma_hat_missing_fields_raise() -> None:
    samples = [10.0, 20.0]
    with pytest.raises(ValueError, match="requires 'value'"):
        compute_sigma_hat("explicit", {}, samples, 0)
    with pytest.raises(ValueError, match="requires 'N'"):
        compute_sigma_hat("recent_N", {}, samples, 0)
    with pytest.raises(ValueError, match="N must be >= 1"):
        compute_sigma_hat("recent_N", {"N": -2}, samples, 0)


def test_extract_parameters_regex_full_menu() -> None:
    """Every regex branch: L recent_N with a context N, mu explicit with value, sigma
    recent_N with a context N, and a rationale carrying escaped quotes and newlines."""
    text = (
        '"rationale": "he said \\"up\\"\nnow", '
        '"L_method": "recent_N", "N": 4, '
        '"mu_hat_method": "explicit", "mu_hat_value": 12.5, '
        '"sigma_hat_method": "recent_N", "N": 6'
    )
    default = extract_parameters_regex(text)["parameters"]["__default__"]
    assert default["L"] == {"method": "recent_N", "N": 4}
    assert default["mu_hat"] == {"method": "explicit", "value": 12.5}
    assert default["sigma_hat"] == {"method": "recent_N", "N": 6}
    # Upstream quirk, verified by executing upstream's extract_parameters_regex on this exact
    # text: the greedy [^"]* eats the escape backslash before the escape alternative can use it,
    # so an escaped quote truncates the captured rationale. Transcription reproduces it.
    assert extract_parameters_regex(text)["rationale"] == "he said \\"


def test_extract_parameters_regex_generic_n_when_context_misses() -> None:
    # recent_N named but the context regex cannot find an N near the method: generic N = 5.
    result = extract_parameters_regex('"L_method": "recent_N"')["parameters"]["__default__"]
    assert result["L"] == {"method": "recent_N", "N": 5}
    # An explicit L with no value anywhere: method kept, value absent (validate then rejects).
    assert extract_parameters_regex('"L_method": "explicit"')["parameters"]["__default__"]["L"] == {
        "method": "explicit"
    }


def test_robust_parse_json_step3_brace_repair_both_ways() -> None:
    inner = (
        '"rationale": "x", "parameters": {"X1": {"L": {"method": "default"}, '
        '"mu_hat": {"method": "default"}, "sigma_hat": {"method": "default"}}}'
    )
    # Missing opening brace (the most common upstream failure) is added.
    parsed = robust_parse_json(inner)
    assert parsed["parameters"][ITEM]["L"] == {"method": "default"}
    # Missing closing brace is added.
    parsed = robust_parse_json(inner[:-1])
    assert parsed["parameters"][ITEM]["L"] == {"method": "default"}
    # An extra closing brace is trimmed.
    parsed = robust_parse_json(inner + "}")
    assert parsed["parameters"][ITEM]["L"] == {"method": "default"}


def test_robust_parse_json_step4_extracts_between_outer_braces() -> None:
    # Prose on both sides, and the text does not start with a quote (so step 3 skips it).
    text = 'note: {"rationale": "x", "parameters": {}} trailing prose'
    assert robust_parse_json(text)["parameters"] == {}


def test_robust_parse_json_step5_picks_the_candidate_with_expected_keys() -> None:
    # Two balanced JSON objects: the expected-key preference must pick the parameters object
    # over the metadata object.
    first = '{"meta": "noise"}'
    second = (
        '{"parameters": {"X1": {"L": {"method": "default"}, "mu_hat": {"method": "default"}, '
        '"sigma_hat": {"method": "default"}}}}'
    )
    text = f"{first} and then {second}"
    assert robust_parse_json(text)["parameters"][ITEM]["L"] == {"method": "default"}
    # With no expected key anywhere, the LAST valid candidate wins.
    two = '{"a": 1} then {"b": 2}'
    assert robust_parse_json(two) == {"b": 2}


def test_robust_parse_json_step6_wraps_non_object_text() -> None:
    # Quote-leading but braceless: step 3 adds a brace, json still fails, steps 4-5 find no
    # braces, step 6 wraps, still not valid JSON, so step 7's regex salvage answers.
    result = robust_parse_json('"just some text"')
    assert result["parameters"]["__default__"] == DEFAULT_PARAMETERS


@pytest.mark.parametrize(
    "mutation, match",
    [
        (lambda p: p["parameters"][ITEM].pop("L"), "Missing 'L'"),
        (lambda p: p["parameters"][ITEM]["L"].pop("method"), "Missing 'method' in L"),
        (
            lambda p: p["parameters"][ITEM]["L"].update(method="teleport"),
            "Invalid L method",
        ),
        (lambda p: p["parameters"][ITEM]["L"].update(method="recent_N"), "requires 'N'"),
        (
            lambda p: p["parameters"][ITEM]["L"].update(method="explicit"),
            "requires 'value' field",
        ),
        (lambda p: p["parameters"][ITEM].pop("mu_hat"), "Missing 'mu_hat'"),
        (
            lambda p: p["parameters"][ITEM]["mu_hat"].pop("method"),
            "Missing 'method' in mu_hat",
        ),
        (
            lambda p: p["parameters"][ITEM]["mu_hat"].update(method="recent_N"),
            "requires 'N' field",
        ),
        (
            lambda p: p["parameters"][ITEM]["mu_hat"].update(method="explicit"),
            "requires 'value' field",
        ),
        (lambda p: p["parameters"][ITEM].pop("sigma_hat"), "Missing 'sigma_hat'"),
        (
            lambda p: p["parameters"][ITEM]["sigma_hat"].pop("method"),
            "Missing 'method' in sigma_hat",
        ),
        (
            lambda p: p["parameters"][ITEM]["sigma_hat"].update(method="EWMA_gamma"),
            "Invalid sigma_hat method",
        ),
        (
            lambda p: p["parameters"][ITEM]["sigma_hat"].update(method="recent_N"),
            "requires 'N' field",
        ),
        (
            lambda p: p["parameters"][ITEM]["sigma_hat"].update(method="explicit"),
            "requires 'value' field",
        ),
    ],
)
def test_validate_item_parameters_every_rejection(mutation, match) -> None:
    payload = json.loads(ALL_DEFAULT)
    mutation(payload)
    with pytest.raises(ValueError, match=match):
        validate_item_parameters(payload, ITEM)


def test_extract_parameters_regex_sigma_explicit_value() -> None:
    text = '"sigma_hat_method": "explicit", "sigma_hat_value": 7.5'
    default = extract_parameters_regex(text)["parameters"]["__default__"]
    assert default["sigma_hat"] == {"method": "explicit", "value": 7.5}


def test_robust_parse_json_step3_trims_extra_closing_braces() -> None:
    # Two extra closing braces run the trim loop (close > open after the opening-brace
    # repair). Upstream's trim is off by one (removes one, then re-adds one), so the repair
    # still fails and a later step parses the inner object alone — verified faithful by
    # executing upstream's robust_parse_json on this exact text (same result: {'X1': ...}).
    inner = (
        '"rationale": "x", "parameters": {"X1": {"L": {"method": "default"}, '
        '"mu_hat": {"method": "default"}, "sigma_hat": {"method": "default"}}}'
    )
    parsed = robust_parse_json(inner + "}}")
    assert list(parsed.keys()) == ["X1"]
    assert parsed["X1"]["L"] == {"method": "default"}


def test_robust_parse_json_steps_6_and_7_wrap_then_salvage() -> None:
    # '"a": 1}}}': the trim loop runs (extra == 2), the repair still fails, no step finds a
    # parameters payload, and step 7's regex salvage answers — both verified byte-equal to
    # upstream's robust_parse_json on the same inputs.
    assert robust_parse_json('"a": 1}}}')["parameters"]["__default__"] == DEFAULT_PARAMETERS
    # '"a": ': every structural step fails, step 6 appends the closing brace, still invalid,
    # step 7 answers with the same defaults.
    assert robust_parse_json('"a": ')["parameters"]["__default__"] == DEFAULT_PARAMETERS


def test_validate_failure_at_the_arm_is_counted_and_orders_default(tmp_path) -> None:
    """A well-formed payload naming the wrong item fails validation: upstream substitutes
    defaults silently; we keep the defaults and count FALLBACK."""
    instance = make_instance(demand=(5.0, 6.0, 7.0), lead_times=(0.0,) * 3)
    wrong_item = params_payload(
        {
            "L": {"method": "default"},
            "mu_hat": {"method": "default"},
            "sigma_hat": {"method": "default"},
        },
        item="NOT-X1",
    )
    _, ledger, metered = _harness(tmp_path, wrong_item)
    arm = LlmToOrArm(
        channel=metered.channel(arm_id=ARM5_ARM_ID, episode_id=instance.spec.episode_id),
        prompt_spec=_spec(instance),
    )
    outcome = EpisodeRunner(instance).run(arm)
    check = CappedBaseStockController()
    check.reset()
    expected = [check.order(obs).order_quantity for obs in outcome.observations]
    assert [d.order_quantity for d in outcome.decisions] == expected
    period1 = [c for c in ledger.charged_entries() if c.period == 1]
    assert len(period1) == 1  # the weak gate passes (braces present), so no retries
    assert period1[0].outcome is ParseOutcome.FALLBACK


def test_robust_parse_json_repairs_invalid_hex_escapes() -> None:
    """The ``\\x41`` escape is invalid JSON; upstream converts it to ``\\u0041`` (='A')."""
    parsed = robust_parse_json('{"rationale": "A\\x41B", "parameters": {}}')
    assert parsed["rationale"] == "AAB"
