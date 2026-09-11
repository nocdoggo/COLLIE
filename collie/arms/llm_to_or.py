"""Arms 5, 6, and 7 — LLM-to-OR parameter revision, upstream's ``llm_to_or`` strategy.

The model never orders directly here: each accepted call revises the three parameters of the
OR backend (``L``, ``mu_hat``, ``sigma_hat``, each a ``{"method": ...}`` choice off the parameter
menu), and the backend — transcribed from ``scripts/run_llm_to_or.py`` — turns parameters into
an order with the same capped base-stock math as arm 1. The user prompt is byte-identical to
the direct-action arms' (``docs/module06_research_notes.md`` §1.5); only the system prompt and
the response schema differ.

* Arm 5 (``arm5_llm_to_or_every_period``): upstream's cadence — a call every period, parameters
  recomputed from scratch each period, nothing persists.
* Arm 6 (``arm6_llm_to_or_sparse``): the same call gated by the shared trigger; between calls
  the default parameters — which make the backend identical to arm 1 (default ``L`` is the
  promised lead time, default ``mu_hat``/``sigma_hat`` are the ``(1+L)``-scaled running mean and
  std) — produce the order. Ephemeral: a call's parameters apply to that period only.
* Arm 7 (``arm7_llm_to_or_persistent``): gated the same way, but a successful call's parameters
  persist for ``PERSISTENCE_EXPIRY`` periods including the call period, then revert to default.

Failure semantics, declared (notes §1.5): upstream *never* fails a parse — ``robust_parse_json``
salvages anything down to regex-extracted defaults — and validation failure silently substitutes
the full default parameter set. We keep that behavior and count it: a response whose own
parameter block was unusable settles ``FALLBACK`` while ordering with exactly the defaults
upstream would have used. The one place upstream *is* fatal — a structurally valid response with
out-of-range values (``gamma=1.5``, ``N=0``, ``L=-1``) kills the run via ``sys.exit(1)`` — becomes
a counted fallback with default parameters here, because a harness that aborts the episode
cannot serve a 640-rollout study. Upstream's duplicate-lead-time re-parsing bug (the whole
accumulated observation re-parsed and re-appended every period) is noted and not reproduced;
our observed lead times come from the same FIFO-attributed history the prompt renders, appended
exactly once per arrival part (``history.py``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.stats import norm

from collie.arms.history import BenchmarkHistory
from collie.arms.prompts import (
    PromptSpec,
    build_llm_to_or_system_prompt,
    build_user_prompt,
)
from collie.contracts import Decision, ParseOutcome, PeriodObservation, Trigger
from collie.llm.client import ArmCallChannel

__all__ = [
    "ARM5_ARM_ID",
    "ARM6_ARM_ID",
    "ARM7_ARM_ID",
    "DEFAULT_PARAMETERS",
    "PERSISTENCE_EXPIRY",
    "LlmToOrArm",
    "compute_L",
    "compute_mu_hat",
    "compute_sigma_hat",
    "extract_parameters_regex",
    "llm_to_or_order",
    "robust_parse_json",
    "validate_item_parameters",
    "validates_llm_to_or_response",
]

ARM5_ARM_ID = "arm5_llm_to_or_every_period"
ARM6_ARM_ID = "arm6_llm_to_or_sparse"
ARM7_ARM_ID = "arm7_llm_to_or_persistent"

PERSISTENCE_EXPIRY = 5
"""Arm 7's fixed expiry, in periods including the call period. Set to the frozen refractory
window (``collie/trigger/calibration.py``): a persisted parameter set covers exactly the silence
the trigger imposes, so persistence — not extra invocation — is what arm 7 measures.
Registered in ``docs/module06_research_notes.md``."""

_MAX_ATTEMPTS = 3
"""Upstream's ``max_retries=3`` (``run_llm_to_or.py:139``), same as the direct arms."""

DEFAULT_PARAMETERS: dict[str, dict[str, str]] = {
    "L": {"method": "default"},
    "mu_hat": {"method": "default"},
    "sigma_hat": {"method": "default"},
}
"""Upstream's validation-failure substitute (``run_llm_to_or.py:1586-1596``) — and, because the
default methods reproduce arm 1's math exactly, the non-call policy for arms 6 and 7."""

_L_METHODS = ("default", "calculate", "recent_N", "explicit")
_MU_METHODS = ("default", "recent_N", "EWMA_gamma", "explicit")
_SIGMA_METHODS = ("default", "recent_N", "explicit")


# ---------------------------------------------------------------------------
# the response gate and the backend computations, transcribed
# ---------------------------------------------------------------------------


def validates_llm_to_or_response(text: str) -> bool:
    """The weak retry gate (``run_llm_to_or.py:123-137``): any JSON-like content or menu keyword.

    Deliberately weaker than the direct arms' JSON validation — upstream's parser salvages
    almost anything, so the retry loop only fires on content-free responses.
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    has_json = "{" in stripped or "}" in stripped
    has_keywords = any(kw in stripped.lower() for kw in ("method", "default", "explicit", "recent"))
    return has_json or has_keywords


def compute_L(
    method: str, params: dict, observed_lead_times: list[int], promised_lead_time: float
) -> float:
    """``run_llm_to_or.py:574-615`` verbatim (prints omitted)."""
    if method == "default":
        return float(promised_lead_time)
    if method == "calculate":
        if not observed_lead_times:
            return float(promised_lead_time)
        return float(np.mean(observed_lead_times))
    if method == "recent_N":
        if not observed_lead_times:
            return float(promised_lead_time)
        if "N" not in params:
            raise ValueError("Method 'recent_N' for L requires 'N' field")
        n = int(params["N"])
        if n < 1:
            raise ValueError(f"N must be >= 1, got {n}")
        recent = observed_lead_times[-n:] if len(observed_lead_times) >= n else observed_lead_times
        return float(np.mean(recent))
    if method == "explicit":
        if "value" not in params:
            raise ValueError("Method 'explicit' for L requires 'value' field")
        return float(params["value"])
    raise ValueError(f"Invalid method for L: {method}")


def compute_mu_hat(method: str, params: dict, samples: list[float], lead_time: float) -> float:
    """``run_llm_to_or.py:618-677`` verbatim. ``explicit`` values are used RAW — no ``(1+L)``
    scaling, despite the menu prose saying otherwise; the code is authoritative."""
    if method == "explicit":
        if "value" not in params:
            raise ValueError("Method 'explicit' for mu_hat requires 'value' field")
        return float(params["value"])
    if not samples:
        return 0.0
    if method == "default":
        return float((1 + lead_time) * np.mean(samples))
    if method == "recent_N":
        if "N" not in params:
            raise ValueError("Method 'recent_N' for mu_hat requires 'N' field")
        n = int(params["N"])
        if n < 1:
            raise ValueError(f"N must be >= 1, got {n}")
        recent = samples[-n:] if len(samples) >= n else samples
        return float((1 + lead_time) * np.mean(recent))
    if method == "EWMA_gamma":
        if "gamma" not in params:
            raise ValueError("Method 'EWMA_gamma' for mu_hat requires 'gamma' field")
        gamma = float(params["gamma"])
        if not (0 <= gamma <= 1):
            raise ValueError(f"gamma must be in [0, 1], got {gamma}")
        # EWMA over samples newest-first with weights gamma**i, normalised (upstream's comment:
        # (1+L) * (d_{t-1} + gamma*d_{t-2} + ...) / (1 + gamma + gamma^2 + ...)).
        numerator = 0.0
        denominator = 0.0
        for i, sample in enumerate(reversed(samples)):
            weight = gamma**i
            numerator += weight * sample
            denominator += weight
        if denominator == 0:  # pragma: no cover - unreachable: with non-empty samples the
            return 0.0  # i=0 weight is gamma**0 == 1.0, so the denominator is at least 1.
        return float((1 + lead_time) * (numerator / denominator))
    raise ValueError(f"Invalid method for mu_hat: {method}")


def compute_sigma_hat(method: str, params: dict, samples: list[float], lead_time: float) -> float:
    """``run_llm_to_or.py:680-720`` verbatim."""
    if method == "explicit":
        if "value" not in params:
            raise ValueError("Method 'explicit' for sigma_hat requires 'value' field")
        return float(params["value"])
    if not samples or len(samples) < 2:
        return 0.0
    if method == "default":
        return float(np.sqrt(1 + lead_time) * np.std(samples, ddof=1))
    if method == "recent_N":
        if "N" not in params:
            raise ValueError("Method 'recent_N' for sigma_hat requires 'N' field")
        n = int(params["N"])
        if n < 1:
            raise ValueError(f"N must be >= 1, got {n}")
        recent = samples[-n:] if len(samples) >= n else samples
        if len(recent) < 2:
            return 0.0
        return float(np.sqrt(1 + lead_time) * np.std(recent, ddof=1))
    raise ValueError(f"Invalid method for sigma_hat: {method}")


def llm_to_or_order(
    *,
    lead_time: float,
    mu_hat: float,
    sigma_hat: float,
    on_hand: float,
    in_transit: float,
    profit: float,
    holding: float,
) -> int:
    """The backend's capped order (``run_llm_to_or.py:1686-1701``).

    ``total_inventory`` upstream is regex-parsed out of the observation text; ours is the typed
    ``on_hand + in_transit_total`` — the same number, without the fragility. Out-of-range
    parameters (``L <= -1``, NaN) raise here and are the caller's counted fallback.
    """
    q = profit / (profit + holding)
    z_star = float(norm.ppf(q))
    base_stock = mu_hat + z_star * sigma_hat
    total_inventory = on_hand + in_transit
    order_uncapped = max(int(np.ceil(base_stock - total_inventory)), 0)
    cap = mu_hat / (1 + lead_time) + float(norm.ppf(0.95)) * sigma_hat / np.sqrt(1 + lead_time)
    return max(min(order_uncapped, int(np.ceil(cap))), 0)


# ---------------------------------------------------------------------------
# the parse machinery, transcribed (upstream never fails a parse)
# ---------------------------------------------------------------------------


def extract_parameters_regex(text: str) -> dict:
    """The ultimate fallback (``run_llm_to_or.py:723-852``): regex-extract the menu choices.

    Always returns a usable payload — the ``__default__`` item carries whatever the regexes
    found (or plain defaults), and the backward-compatible flat keys ride along as upstream
    emits them.
    """
    result: dict[str, Any] = {
        "rationale": "Extracted via regex fallback",
        "carry_over_insight": "",
        "parameters": {},
    }
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', text, re.DOTALL)
    if rationale_match:
        result["rationale"] = rationale_match.group(1).replace('\\"', '"').replace("\\n", "\n")

    valid_methods = ["default", "explicit", "recent_N", "calculate"]

    l_method = "default"
    l_match = re.search(r'"L_method"\s*:\s*"(\w+)"', text)
    if l_match and l_match.group(1) in valid_methods:
        l_method = l_match.group(1)
    l_value = None
    if l_method == "explicit":
        l_val_match = re.search(r'"L_value"\s*:\s*(\d+(?:\.\d+)?)', text)
        if l_val_match:
            l_value = float(l_val_match.group(1))
    l_n = None
    if l_method == "recent_N":
        l_n_match = re.search(r'"L_method"[^}]*?"N"\s*:\s*(\d+)', text)
        if l_n_match:
            l_n = int(l_n_match.group(1))

    mu_method = "default"
    mu_match = re.search(r'"mu_hat_method"\s*:\s*"(\w+)"', text)
    if mu_match and mu_match.group(1) in valid_methods:
        mu_method = mu_match.group(1)
    mu_value = None
    if mu_method == "explicit":
        mu_val_match = re.search(r'"mu_hat_value"\s*:\s*(\d+(?:\.\d+)?)', text)
        if mu_val_match:
            mu_value = float(mu_val_match.group(1))
    mu_n = None
    if mu_method == "recent_N":
        mu_n_match = re.search(r'"mu_hat_method"[^}]*?"N"\s*:\s*(\d+)', text)
        if mu_n_match:
            mu_n = int(mu_n_match.group(1))

    sigma_method = "default"
    sigma_match = re.search(r'"sigma_hat_method"\s*:\s*"(\w+)"', text)
    if sigma_match and sigma_match.group(1) in valid_methods:
        sigma_method = sigma_match.group(1)
    sigma_value = None
    if sigma_method == "explicit":
        sigma_val_match = re.search(r'"sigma_hat_value"\s*:\s*(\d+(?:\.\d+)?)', text)
        if sigma_val_match:
            sigma_value = float(sigma_val_match.group(1))
    sigma_n = None
    if sigma_method == "recent_N":
        sigma_n_match = re.search(r'"sigma_hat_method"[^}]*?"N"\s*:\s*(\d+)', text)
        if sigma_n_match:
            sigma_n = int(sigma_n_match.group(1))

    generic_n_match = re.search(r'"N"\s*:\s*(\d+)', text)
    generic_n = int(generic_n_match.group(1)) if generic_n_match else 5

    l_param: dict[str, Any] = {"method": l_method}
    if l_method == "explicit" and l_value is not None:
        l_param["value"] = l_value
    elif l_method == "recent_N":
        l_param["N"] = l_n if l_n else generic_n
    mu_param: dict[str, Any] = {"method": mu_method}
    if mu_method == "explicit" and mu_value is not None:
        mu_param["value"] = mu_value
    elif mu_method == "recent_N":
        mu_param["N"] = mu_n if mu_n else generic_n
    sigma_param: dict[str, Any] = {"method": sigma_method}
    if sigma_method == "explicit" and sigma_value is not None:
        sigma_param["value"] = sigma_value
    elif sigma_method == "recent_N":
        sigma_param["N"] = sigma_n if sigma_n else generic_n

    result["parameters"]["__default__"] = {
        "L": l_param,
        "mu_hat": mu_param,
        "sigma_hat": sigma_param,
    }
    result["L_method"] = l_method
    result["mu_hat_method"] = mu_method
    result["sigma_hat_method"] = sigma_method
    return result


def robust_parse_json(text: str) -> dict:
    """``run_llm_to_or.py:855-1002`` verbatim: seven steps, and it ALWAYS returns a dict."""
    cleaned = _clean_and_repair(text)

    result = _try_parse(cleaned)
    if result:
        return result

    # Step 3: the most common LLM error is a missing opening brace.
    cleaned_stripped = cleaned.strip()
    if cleaned_stripped.startswith('"') and not cleaned_stripped.startswith("{"):
        with_brace = "{" + cleaned_stripped
        open_count = with_brace.count("{")
        close_count = with_brace.count("}")
        if close_count > open_count:
            extra = close_count - open_count
            temp = with_brace.rstrip()
            for _ in range(extra):
                if temp.endswith("}"):
                    temp = temp[:-1].rstrip()
            with_brace = temp + "}"
        elif close_count < open_count:
            with_brace = with_brace + "}" * (open_count - close_count)
        with_brace = _clean_and_repair(with_brace)
        result = _try_parse(with_brace)
        if result:
            return result

    # Step 4: extract from first { to last }.
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        extracted = cleaned[first_brace : last_brace + 1]
        extracted = _clean_and_repair(extracted)
        result = _try_parse(extracted)
        if result:
            return result

    # Step 5: brace-matched candidates, preferring one with an expected key.
    brace_stack: list[int] = []
    json_start: int | None = None
    candidates: list[dict] = []
    for i, char in enumerate(cleaned):
        if char == "{":
            if json_start is None:
                json_start = i
            brace_stack.append(i)
        elif char == "}":
            if brace_stack:
                brace_stack.pop()
                if not brace_stack and json_start is not None:
                    candidate = cleaned[json_start : i + 1]
                    candidate = _clean_and_repair(candidate)
                    parsed = _try_parse(candidate)
                    if parsed:
                        candidates.append(parsed)
                    json_start = None
    expected_keys = ["parameters", "rationale", "action", "carry_over_insight"]
    for candidate in candidates:
        for key in expected_keys:
            if key in candidate:
                return candidate
    if candidates:
        return candidates[-1]

    # Step 6: last resort — wrap the entire content. Provably never returns: a wrapped text can
    # only be a valid JSON object when it starts with a quote, and step 3 already handles every
    # quote-leading text with the same wrap plus brace balancing. Kept for transcription
    # fidelity with run_llm_to_or.py:990-998.
    if not cleaned_stripped.startswith("{"):
        wrapped = "{" + cleaned_stripped
        if not wrapped.rstrip().endswith("}"):
            wrapped = wrapped + "}"
        wrapped = _clean_and_repair(wrapped)
        result = _try_parse(wrapped)
        if result:  # pragma: no cover - dead upstream code, see the comment above
            return result

    # Step 7: regex extraction always returns parameters.
    return extract_parameters_regex(text)


def _fix_invalid_escapes(text: str) -> str:
    def hex_to_unicode(match: re.Match) -> str:
        try:
            code_point = int(match.group(1), 16)
            return f"\\u{code_point:04X}"
        except ValueError:  # pragma: no cover - the regex only matches two hex digits
            return match.group(0)

    text = re.sub(r"(?<!\\)\\\$", "$", text)
    text = re.sub(r"(?<!\\)\\%", "%", text)
    return re.sub(r"\\x([0-9a-fA-F]{2})", hex_to_unicode, text)


def _try_parse(s: str) -> dict | None:
    try:
        result = json.loads(s)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return None


def _clean_and_repair(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    text = _fix_invalid_escapes(text)
    return re.sub(r",(\s*[}\]])", r"\1", text)


def validate_item_parameters(params_json: dict, item_id: str) -> dict:
    """``validate_parameters_json`` (``run_llm_to_or.py:1005-1081``), single-item.

    Returns the item's parameter dict. Raises ``ValueError`` on any structural violation —
    upstream's caller substitutes full defaults in that case, and so does ours. The
    ``__default__`` expansion upstream performs by mutating the payload is done here without
    mutation.
    """
    if "parameters" not in params_json:
        raise ValueError("JSON must contain 'parameters' field")
    parameters = params_json["parameters"]
    if "__default__" in parameters and item_id not in parameters:
        parameters = {**parameters, item_id: dict(parameters["__default__"])}
    if item_id not in parameters:
        raise ValueError(f"Missing parameters for item: {item_id}")
    item = parameters[item_id]

    if "L" not in item:
        raise ValueError(f"Missing 'L' parameter for item {item_id}")
    l_param = item["L"]
    if "method" not in l_param:
        raise ValueError(f"Missing 'method' in L parameter for item {item_id}")
    if l_param["method"] not in _L_METHODS:
        raise ValueError(f"Invalid L method for item {item_id}: {l_param['method']}")
    if l_param["method"] == "recent_N" and "N" not in l_param:
        raise ValueError(f"Method 'recent_N' for L requires 'N' field for item {item_id}")
    if l_param["method"] == "explicit" and "value" not in l_param:
        raise ValueError(f"Method 'explicit' for L requires 'value' field for item {item_id}")

    if "mu_hat" not in item:
        raise ValueError(f"Missing 'mu_hat' parameter for item {item_id}")
    mu_param = item["mu_hat"]
    if "method" not in mu_param:
        raise ValueError(f"Missing 'method' in mu_hat parameter for item {item_id}")
    if mu_param["method"] not in _MU_METHODS:
        raise ValueError(f"Invalid mu_hat method for item {item_id}: {mu_param['method']}")
    if mu_param["method"] == "recent_N" and "N" not in mu_param:
        raise ValueError(f"Method 'recent_N' for mu_hat requires 'N' field for item {item_id}")
    if mu_param["method"] == "EWMA_gamma" and "gamma" not in mu_param:
        raise ValueError(
            f"Method 'EWMA_gamma' for mu_hat requires 'gamma' field for item {item_id}"
        )
    if mu_param["method"] == "explicit" and "value" not in mu_param:
        raise ValueError(f"Method 'explicit' for mu_hat requires 'value' field for item {item_id}")

    if "sigma_hat" not in item:
        raise ValueError(f"Missing 'sigma_hat' parameter for item {item_id}")
    sigma_param = item["sigma_hat"]
    if "method" not in sigma_param:
        raise ValueError(f"Missing 'method' in sigma_hat parameter for item {item_id}")
    if sigma_param["method"] not in _SIGMA_METHODS:
        raise ValueError(f"Invalid sigma_hat method for item {item_id}: {sigma_param['method']}")
    if sigma_param["method"] == "recent_N" and "N" not in sigma_param:
        raise ValueError(f"Method 'recent_N' for sigma_hat requires 'N' field for item {item_id}")
    if sigma_param["method"] == "explicit" and "value" not in sigma_param:
        raise ValueError(
            f"Method 'explicit' for sigma_hat requires 'value' field for item {item_id}"
        )
    return item


# ---------------------------------------------------------------------------
# the arm
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LlmToOrArm:
    """One LLM-to-OR arm. Mode is fixed at construction, never mutated mid-episode.

    * arm 5: ``trigger=None, expiry=None`` — every period;
    * arm 6: ``trigger`` set, ``expiry=None`` — sparse and ephemeral;
    * arm 7: ``trigger`` and ``expiry`` both set — sparse with persistence.

    The channel and trigger are injected. Between calls (or on any counted failure) the order
    comes from :data:`DEFAULT_PARAMETERS`, which reproduces arm 1 exactly — so non-call periods
    of arms 6/7 are precisely the OR baseline, which is what makes the contrast clean.
    """

    channel: ArmCallChannel
    prompt_spec: PromptSpec
    arm_id: str = ARM5_ARM_ID
    trigger: Trigger | None = None
    expiry: int | None = None
    _history: BenchmarkHistory = field(init=False, repr=False)
    _active_params: dict | None = field(default=None, repr=False)
    _active_until: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if self.expiry is not None:
            if self.trigger is None:
                raise ValueError(
                    f"{self.arm_id!r}: persistence without a trigger would call every period "
                    "and the expiry would be meaningless — that is arm 5, not this arm"
                )
            if self.expiry < 1:
                raise ValueError(f"expiry must be >= 1 period, got {self.expiry}")
        self._history = BenchmarkHistory(arm_id=self.arm_id)

    def reset(self) -> None:
        self._history.reset()
        self._active_params = None
        self._active_until = 0

    def order(self, obs: PeriodObservation) -> Decision:
        self.channel.set_period(obs.period)
        self._history.observe(obs)
        self._history.record_demand(obs)

        fired = self.trigger is None or self.trigger.should_propose(obs)
        current = self._propose(obs) if fired else None
        params = self._effective_params(obs.period, current)
        quantity = float(self._backend_order(params, obs))
        self._history.note_dispatch(obs.period, quantity)
        return Decision(
            period=obs.period,
            order_quantity=quantity,
            arm_id=self.arm_id,
            llm_called=fired,
            triggered=self.trigger is not None and fired,
        )

    # -- internals -----------------------------------------------------------

    def _effective_params(self, period: int, current: dict | None) -> dict:
        """The parameters this period's order is computed with.

        A call that produced usable parameters governs its own period on every arm; arm 7's
        persisted set covers the window after it; anything else is the arm-1 default set.
        """
        if current is not None:
            return current
        if (
            self.expiry is not None
            and self._active_params is not None
            and period < self._active_until
        ):
            return self._active_params
        return DEFAULT_PARAMETERS

    def _propose(self, obs: PeriodObservation) -> dict | None:
        """One proposal call set: attempts, parse, validate, and the persistence bookkeeping.

        Returns the accepted parameter dict, or ``None`` when the response was unusable
        (upstream's defaults path, counted ``FALLBACK`` in the ledger).
        """
        user = build_user_prompt(
            self.prompt_spec,
            period=obs.period,
            date=obs.date,
            on_hand=obs.on_hand,
            in_transit=obs.in_transit_total,
            profit=obs.profit_per_unit,
            holding=obs.holding_cost_per_unit,
            conclusions=self._history.conclusions,
            insights=self._history.insights,
        )
        system = build_llm_to_or_system_prompt(self.prompt_spec)

        raw_text = ""
        attempt_ids: list[str] = []
        for attempt in range(_MAX_ATTEMPTS):
            if attempt == 0:
                raw_text = self.channel.complete_with_system(system, user)
            else:
                raw_text = self.channel.complete_attempt(
                    user, decoding_hash="det-v1", attempt_index=attempt, system=system
                )
            seen = self.channel.last_call_id
            assert seen is not None  # the channel stamps every call
            attempt_ids.append(seen)
            if validates_llm_to_or_response(raw_text):
                break

        payload = robust_parse_json(raw_text)
        self._history.update_insights(obs.period, payload)
        item_id = self.prompt_spec.item_id
        try:
            item_params: dict | None = validate_item_parameters(payload, item_id)
        except ValueError:
            item_params = None

        # The compute probe decides whether the parameters are *executable* — the case where
        # upstream dies on sys.exit(1). We probe against the current observation and fall back
        # to defaults on any arithmetic failure.
        usable = item_params is not None
        if usable:
            assert item_params is not None
            try:
                self._backend_order(item_params, obs)
            except (ValueError, TypeError, ZeroDivisionError, OverflowError, FloatingPointError):
                usable = False

        # Settle every attempt exactly once. Mid-loop attempts failed the weak gate by
        # construction (the loop only continues then), so they are unusable calls. For the
        # final text the gate dichotomy is exact: the gate looks for braces or menu keywords,
        # and the regex salvage can only find parameter content when those keywords exist —
        # so a gate-failing text yields pure defaults and the model contributed nothing.
        for call_id in attempt_ids[:-1]:
            self.channel.settle(call_id, ParseOutcome.FALLBACK)
        last = attempt_ids[-1]
        if not validates_llm_to_or_response(raw_text):
            usable = False
        outcome = (
            ParseOutcome.FALLBACK
            if not usable
            else (
                ParseOutcome.ACCEPTED
                if len(attempt_ids) == 1
                else ParseOutcome.ACCEPTED_AFTER_REPAIR
            )
        )
        self.channel.settle(last, outcome)

        if usable:
            assert item_params is not None
            if self.expiry is not None:
                self._active_params = item_params
                self._active_until = obs.period + self.expiry
        return item_params if usable else None

    def _backend_order(self, params: dict, obs: PeriodObservation) -> int:
        """The transcribed backend: parameters to a capped order for the current observation."""
        samples = [*(d for _, d in self.prompt_spec.train_samples), *self._history.demands]
        lead_times = list(self._history.observed_lead_times)
        lead_time = compute_L(
            params["L"]["method"],
            params["L"],
            lead_times,
            self.prompt_spec.promised_lead_time,
        )
        mu_hat = compute_mu_hat(params["mu_hat"]["method"], params["mu_hat"], samples, lead_time)
        sigma_hat = compute_sigma_hat(
            params["sigma_hat"]["method"], params["sigma_hat"], samples, lead_time
        )
        return llm_to_or_order(
            lead_time=lead_time,
            mu_hat=mu_hat,
            sigma_hat=sigma_hat,
            on_hand=obs.on_hand,
            in_transit=obs.in_transit_total,
            profit=obs.profit_per_unit,
            holding=obs.holding_cost_per_unit,
        )
