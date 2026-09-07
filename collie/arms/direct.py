"""Direct-action arms 3, 4, and 11 — the benchmark's own LLM strategies inside our runner.

Arm 3 (``arm3_llm_direct``) is upstream's ``llm`` strategy (``scripts/run_llm.py``): an LLM call
every period, direct action, benchmark-verbatim prompt. Arm 4 (``arm4_triggered_llm_direct``)
is the *identical* arm gated by the shared trigger — invocation timing is the only treatment;
when the trigger does not fire, the injected fallback controller's order stands. Arm 11
(``arm11_or_to_llm``) is upstream's ``or_to_llm`` strategy (``scripts/run_or_to_llm.py``), the
strongest published method (0.5380) — added per the Checkpoint-1 audit ruling so the best
existing approach is on the ladder; every-period, with arm 1's capped-OR quantity quoted to the
model each period.

Call, retry, and parse semantics are transcribed from upstream, not re-designed:

* ``LLMAgent.__call__`` (``run_llm.py:165-230``): ``messages = [system, user]``, up to three
  attempts, retries keyed *only* on :func:`validates_as_action_json`. The retry re-sends the
  identical text; under our registered deterministic decoding the channel's attempt-indexed
  cache key keeps each attempt a distinct, replayable call.
* ``env._parse_json_action`` (``env.py:521-627``): the four forgiving parse strategies, in
  order, with ``int(qty``) truncation. Validation passing does not guarantee these succeed
  (a non-numeric quantity validates as JSON but fails coercion), so both paths exist here.
* Insight bookkeeping (``run_llm.py:879-900``): the carry-over memo is read only from a full
  JSON parse of the fence-stripped response; a parse failure updates nothing.
* Upstream failure semantics — an unparseable action is an invalid move that ends their harness
  run — become *counted* fallbacks here: the arm orders 0 that period and the call settles
  ``FALLBACK``. A harness that aborts the episode cannot serve a 640-rollout study; the failure
  is visible in the ledger, which upstream's crash never allowed. Declared at the checkpoints.

Two faithful-reproduction limits are declared, both forced by the frozen observation contract
(``docs/env_contract.md`` §4) rather than by convenience:

* The conclude block's per-cohort ``arrived=`` attribution is inferred FIFO over the arm's own
  order book. The benchmark's text channel leaked shipment ages; ours does not, so on episodes
  where cohorts overtake (per-period stochastic lead times) or a shipment is lost, the
  ``lead_time was`` numbers in *history text* can misattribute. The inference is exact whenever
  cohorts do not overtake. Orders are never affected.
* The board's ``In-transit`` figure follows the authoritative ``eval/`` semantics (a lost
  shipment never enters in-transit), where upstream's ``env.py`` rendering keeps lost units
  forever (§5). The template is verbatim; the number is our harness's observable one.

Both arms run UNCENSORED only, like arm 1: the verbatim history needs true demand, which the
censored channel deliberately withholds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from collie.arms.base_stock import PUBLISHED_PARAMS, base_stock_order
from collie.arms.history import BenchmarkHistory
from collie.arms.prompts import (
    PromptSpec,
    build_or_to_llm_system_prompt,
    build_system_prompt,
    build_user_prompt,
)
from collie.contracts import (
    Controller,
    Decision,
    EpisodeSpec,
    ParseOutcome,
    PeriodObservation,
    Trigger,
)
from collie.llm.client import ArmCallChannel

__all__ = [
    "ARM3_ARM_ID",
    "ARM4_ARM_ID",
    "ARM11_ARM_ID",
    "DirectActionArm",
    "parse_env_action",
    "prompt_spec_from_episode",
    "validates_as_action_json",
]

ARM3_ARM_ID = "arm3_llm_direct"
ARM4_ARM_ID = "arm4_triggered_llm_direct"
ARM11_ARM_ID = "arm11_or_to_llm"

_MAX_ATTEMPTS = 3
"""Upstream's ``max_retries=3`` (``run_llm.py:165``): one initial call plus two retries."""


def validates_as_action_json(text: str) -> bool:
    """Transcription of ``LLMAgent._validate_json_action`` (``run_llm.py:119-163``).

    Fence-stripped, then the first balanced ``{...}`` block must parse and carry an ``action``
    dict. This — and only this — decides whether upstream retries.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    json_start = text.find("{")
    if json_start == -1:
        return False
    depth = 0
    in_string = False
    escape = False
    for i, c in enumerate(text[json_start:], json_start):
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                json_str = text[json_start : i + 1]
                try:
                    data = json.loads(json_str)
                    if "action" in data and isinstance(data["action"], dict):
                        return True
                except (ValueError, TypeError):
                    pass
                break
    return False


def parse_env_action(text: str) -> dict[str, int] | None:
    """Transcription of ``env._parse_json_action`` (``env.py:521-627``), four strategies in order.

    Returns the orders dict with ``int(qty)`` truncation, or ``None`` when nothing yields a
    usable action. The rationale the upstream tuple carries is unused here (the arm records
    history itself), so only the orders are returned.
    """
    action = text.strip()
    # Strategy 0: remove markdown code fences.
    action = re.sub(r"^```(?:json)?\s*", "", action)
    action = re.sub(r"\s*```$", "", action)
    action = action.strip()

    # Strategy 1: first balanced-brace JSON object.
    json_str = _find_balanced_json(action)
    if json_str:
        try:
            data = json.loads(json_str)
            if "action" in data and isinstance(data["action"], dict):
                return {str(item_id): int(qty) for item_id, qty in data["action"].items()}
        except (ValueError, TypeError):
            pass

    # Strategy 2: naive first/last brace slice.
    json_start = action.find("{")
    json_end = action.rfind("}") + 1
    if json_start != -1 and json_end > 0:
        json_str = action[json_start:json_end]
        try:
            data = json.loads(json_str)
            if "action" in data and isinstance(data["action"], dict):
                return {str(item_id): int(qty) for item_id, qty in data["action"].items()}
        except (ValueError, TypeError):
            pass

    # Strategy 3: regex extraction of the "action" object's contents.
    match = re.search(r'"action"\s*:\s*\{([^}]+)\}', action)
    if match:
        pairs = re.findall(r'"([^"]+)"\s*:\s*(\d+)', match.group(1))
        result = {str(item_id): int(qty) for item_id, qty in pairs}
        if result:
            return result

    # Strategy 4: last resort — any "digits": digits pair anywhere in the text.
    matches = re.findall(r'"(\d+)"\s*:\s*(\d+)', action)
    if matches:
        return {str(item_id): int(qty) for item_id, qty in matches}

    return None


def _find_balanced_json(s: str) -> str | None:
    """The first balanced ``{...}`` block of ``s`` (``env.py:542-568``)."""
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i, c in enumerate(s[start:], start):
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def prompt_spec_from_episode(
    spec: EpisodeSpec, *, train_samples: tuple[tuple[str, float], ...]
) -> PromptSpec:
    """Map the frozen episode spec onto prompt constants.

    ``train_samples`` are ``(date, demand)`` pairs in CSV order; the frozen loader drops train
    dates, so the harness supplies them from the instance's ``train.csv`` (public prior data,
    never hidden state). ``description=None`` reproduces upstream's doubled header on synthetic
    instances, where no description column exists.
    """
    return PromptSpec(
        item_id=spec.item_id,
        description=spec.product_text,
        promised_lead_time=spec.promised_lead_time,
        horizon=spec.horizon,
        train_samples=train_samples,
    )


@dataclass(slots=True)
class DirectActionArm:
    """One direct-action arm. Mode is fixed at construction, never mutated mid-episode.

    * arm 3: ``trigger=None, fallback=None, or_to_llm=False`` — call every period;
    * arm 4: ``trigger`` and ``fallback`` both set — call only when the trigger fires, the
      fallback's order stands otherwise. The fallback's ``order`` is invoked every period
      regardless, so its demand estimator never skips an observation;
    * arm 11: ``or_to_llm=True`` (``trigger=None``) — every period, with the capped-OR
      recommendation recomputed from the same demand history and quoted in the prompt.

    The channel, trigger, and fallback are injected; this class imports no concrete transport
    or compiler. Per-episode state (conclusions, insights, order book, demand history) is
    cleared by :meth:`reset`, which the runner calls before every episode.
    """

    channel: ArmCallChannel
    prompt_spec: PromptSpec
    arm_id: str = ARM3_ARM_ID
    trigger: Trigger | None = None
    fallback: Controller | None = None
    or_to_llm: bool = False
    _history: BenchmarkHistory = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.trigger is not None and self.fallback is None:
            raise ValueError(
                f"{self.arm_id!r}: a trigger-gated arm needs a fallback controller for the "
                "periods the trigger does not fire"
            )
        if self.or_to_llm and self.trigger is not None:
            raise ValueError(
                f"{self.arm_id!r}: the or_to_llm arm is every-period by design (Checkpoint-1 "
                "ruling); a triggered variant is a different arm, not this one"
            )
        self._history = BenchmarkHistory(arm_id=self.arm_id)

    def reset(self) -> None:
        self._history.reset()
        if self.fallback is not None:
            self.fallback.reset()

    def order(self, obs: PeriodObservation) -> Decision:
        self.channel.set_period(obs.period)
        self._history.observe(obs)
        self._history.record_demand(obs)

        fallback_qty = 0.0
        if self.fallback is not None:
            fallback_qty = self.fallback.order(obs).order_quantity

        fired = self.trigger is None or self.trigger.should_propose(obs)
        if not fired:
            return self._decide(obs, fallback_qty, llm_called=False, triggered=False)

        user = self._user_prompt(obs)
        orders, raw_text = self._call_and_parse(user)
        self._update_insights(obs.period, raw_text)
        quantity = self._quantity_from(orders)
        return self._decide(obs, quantity, llm_called=True, triggered=self.trigger is not None)

    # -- prompt assembly ----------------------------------------------------

    def _system_prompt(self) -> str:
        if self.or_to_llm:
            return build_or_to_llm_system_prompt(self.prompt_spec)
        return build_system_prompt(self.prompt_spec)

    def _user_prompt(self, obs: PeriodObservation) -> str:
        or_recommendation: int | None = None
        if self.or_to_llm:
            or_recommendation = int(
                base_stock_order(
                    samples=[
                        *(d for _, d in self.prompt_spec.train_samples),
                        *self._history.demands,
                    ],
                    on_hand=obs.on_hand,
                    in_transit=obs.in_transit_total,
                    promised_lead_time=obs.promised_lead_time,
                    profit_per_unit=obs.profit_per_unit,
                    holding_cost_per_unit=obs.holding_cost_per_unit,
                    params=PUBLISHED_PARAMS,
                )
            )
        return build_user_prompt(
            self.prompt_spec,
            period=obs.period,
            date=obs.date,
            on_hand=obs.on_hand,
            in_transit=obs.in_transit_total,
            profit=obs.profit_per_unit,
            holding=obs.holding_cost_per_unit,
            conclusions=self._history.conclusions,
            insights=self._history.insights,
            or_recommendation=or_recommendation,
        )

    # -- the call loop, upstream's semantics ---------------------------------

    def _call_and_parse(self, user: str) -> tuple[dict[str, int] | None, str]:
        """Up to ``_MAX_ATTEMPTS`` calls, retries keyed only on validation, then the env parse.

        Every attempt settles exactly once: an unusable mid-loop attempt settles ``FALLBACK``,
        a validating one ``ACCEPTED`` (first) or ``ACCEPTED_AFTER_REPAIR`` (later), and a final
        text that fails validation but still yields an action under the env's forgiving parse
        settles ``ACCEPTED_AFTER_REPAIR`` — upstream's env would have executed that action.
        """
        system = self._system_prompt()
        raw_text = ""
        call_id = ""
        for attempt in range(_MAX_ATTEMPTS):
            if attempt == 0:
                raw_text = self.channel.complete_with_system(system, user)
            else:
                raw_text = self.channel.complete_attempt(
                    user, decoding_hash="det-v1", attempt_index=attempt, system=system
                )
            seen = self.channel.last_call_id
            assert seen is not None  # the channel stamps every call
            call_id = seen
            if validates_as_action_json(raw_text):
                self.channel.settle(
                    call_id,
                    ParseOutcome.ACCEPTED if attempt == 0 else ParseOutcome.ACCEPTED_AFTER_REPAIR,
                )
                return parse_env_action(raw_text), raw_text
            if attempt < _MAX_ATTEMPTS - 1:
                self.channel.settle(call_id, ParseOutcome.FALLBACK)
        orders = parse_env_action(raw_text)
        self.channel.settle(
            call_id,
            ParseOutcome.ACCEPTED_AFTER_REPAIR if orders is not None else ParseOutcome.FALLBACK,
        )
        return orders, raw_text

    # -- bookkeeping: delegated to BenchmarkHistory ---------------------------

    def _update_insights(self, period: int, raw_text: str) -> None:
        """``run_llm.py:879-890``: the memo counts only from a full JSON parse of the response."""
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except (ValueError, TypeError):
            return
        if isinstance(data, dict):
            self._history.update_insights(period, data)

    def _quantity_from(self, orders: dict[str, int] | None) -> float:
        """Upstream's move validation (``env.py:289-296``): unknown item or negative -> invalid."""
        if not orders:
            return 0.0
        if any(item_id != self.prompt_spec.item_id for item_id in orders):
            return 0.0
        quantity = orders.get(self.prompt_spec.item_id, 0)
        if quantity < 0:
            return 0.0
        return float(quantity)

    def _decide(
        self, obs: PeriodObservation, quantity: float, *, llm_called: bool, triggered: bool
    ) -> Decision:
        self._history.note_dispatch(obs.period, quantity)
        return Decision(
            period=obs.period,
            order_quantity=quantity,
            arm_id=self.arm_id,
            llm_called=llm_called,
            triggered=triggered,
        )
