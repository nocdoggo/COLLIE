"""The model ladder: which live endpoints the commitment study may call, at what dated price.

Every entry is an ``EndpointConfig``; keys are resolved at runtime by
:meth:`EndpointConfig.resolve_key` from the environment or the gitignored ``cloud_endpoint/``
key files and never handled here. Prices are dated list prices per 1M tokens, retrieved
2026-09-28, with reasoning billed as output (billable output = total - prompt tokens, which on
every provider here equals the completion count including reasoning):

* Gemini: OpenRouter's public model list, which matched Google's list for ``gemini-3.8-flash``
  exactly (research notes §5); Grok: xAI's ``/v1/language-models``;
* OpenRouter rungs (open-weight and legacy models): OpenRouter's list price for the model id;
* StepFun rungs are served on the flat-rate Step Plan (``api.stepfun.ai/step_plan/v1``), so they
  carry a *shadow* price: OpenRouter's list price for ``stepfun/step-3.5-flash`` (also used for
  ``step-3.5-flash-2603``) and ``stepfun/step-3.7-flash`` (also used for ``step-5-preview``,
  which has no public list price).

xAI silently serves retired ids as a current model (on 2026-09-28 ``grok-3``, ``grok-3-mini`` and
``grok-4-fast-non-reasoning`` all came back as ``grok-4.3``). :class:`EchoCheckedClient` therefore
compares the model name each response echoes against the requested one and refuses a mismatch,
so no ladder rung can quietly become another model.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from collie.llm.client import (
    DecodingConfig,
    EndpointConfig,
    MissingUsageError,
    OpenAICompatClient,
    RawResponse,
    UnsupportedDecodingError,
    gemini_primary,
    grok_hosted_confirmation,
)

PRICE_DATE = "2026-09-28"
KEY_DIR = Path(__file__).resolve().parents[2] / "cloud_endpoint"
OPENAI_COMPAT = {
    "stepfun": ("https://api.stepfun.ai/step_plan/v1", "STEPFUN_API_KEY", KEY_DIR / "stepfun.key"),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        KEY_DIR / "openrouter.key",
    ),
}


class ServedModelMismatch(RuntimeError):
    """The provider answered with a different model than the one requested."""


@dataclass(frozen=True)
class Rung:
    name: str
    provider: str
    model_id: str
    released: str
    tier: str
    price_input_per_mtok: float
    price_output_per_mtok: float
    served_as: tuple[str, ...]

    def endpoint(self) -> EndpointConfig:
        if self.provider in OPENAI_COMPAT:
            base_url, key_env, key_file = OPENAI_COMPAT[self.provider]
            return EndpointConfig(
                name=f"{self.provider}:{self.model_id}",
                base_url=base_url,
                model_id=self.model_id,
                key_env=key_env,
                key_file=key_file,
                supports_seed=False,
                bills_thinking_as_output=True,
                price_input_per_mtok=self.price_input_per_mtok,
                price_output_per_mtok=self.price_output_per_mtok,
                price_date=PRICE_DATE,
            )
        base = (
            gemini_primary(self.model_id)
            if self.provider == "gemini"
            else grok_hosted_confirmation(self.model_id)
        )
        if self.name in ("gemini-3.8-flash", "grok-4.20"):
            return base  # the registered defaults keep their original dated prices
        return replace(
            base,
            name=f"{base.name}:{self.model_id}",
            price_input_per_mtok=self.price_input_per_mtok,
            price_output_per_mtok=self.price_output_per_mtok,
            price_date=PRICE_DATE,
        )


_RUNGS = (
    # name, provider, model id, released, tier, $/1M in, $/1M out
    ("gemini-2.5-flash-lite", "gemini", "gemini-2.5-flash-lite", "2025-07", "small", 0.10, 0.40),
    ("gemini-2.5-flash", "gemini", "gemini-2.5-flash", "2025-06", "mid", 0.30, 2.50),
    ("gemini-3-flash-preview", "gemini", "gemini-3-flash-preview", "2025-12", "mid", 0.50, 3.00),
    ("gemini-3.1-flash-lite", "gemini", "gemini-3.1-flash-lite", "2026-05", "small", 0.25, 1.50),
    ("gemini-3.8-flash", "gemini", "gemini-3.8-flash", "2026-09", "mid", 0.75, 3.75),
    ("grok-build-0.1", "grok", "grok-build-0.1", "2025-08", "small", 1.00, 2.00),
    ("grok-4.20", "grok", "grok-4.20-0309-non-reasoning", "2026-03", "mid", 1.25, 2.50),
    ("step-3.5-flash", "stepfun", "step-3.5-flash", "2026-01", "mid", 0.10, 0.30),
    ("step-3.5-flash-2603", "stepfun", "step-3.5-flash-2603", "2026-03", "mid", 0.10, 0.30),
    ("step-3.7-flash", "stepfun", "step-3.7-flash", "2026-05", "mid", 0.20, 1.15),
    ("step-5-preview", "stepfun", "step-5-preview", "2026-09", "large", 0.20, 1.15),
    (
        "llama-3.2-1b",
        "openrouter",
        "meta-llama/llama-3.2-1b-instruct",
        "2024-09",
        "1B",
        0.027,
        0.201,
    ),
    ("llama-3.2-3b", "openrouter", "meta-llama/llama-3.2-3b-instruct", "2024-09", "3B", 0.05, 0.33),
    ("llama-3.1-8b", "openrouter", "meta-llama/llama-3.1-8b-instruct", "2024-07", "8B", 0.05, 0.08),
    (
        "llama-3.3-70b",
        "openrouter",
        "meta-llama/llama-3.3-70b-instruct",
        "2024-12",
        "70B",
        0.10,
        0.32,
    ),
    ("qwen-2.5-7b", "openrouter", "qwen/qwen-2.5-7b-instruct", "2024-10", "7B", 0.10, 0.20),
    ("qwen-2.5-72b", "openrouter", "qwen/qwen-2.5-72b-instruct", "2024-09", "72B", 0.36, 0.40),
    ("gemma-3-27b", "openrouter", "google/gemma-3-27b-it", "2025-03", "27B", 0.08, 0.45),
    ("deepseek-v3", "openrouter", "deepseek/deepseek-chat", "2024-12", "671B-MoE", 0.257, 1.029),
    ("gpt-oss-20b", "openrouter", "openai/gpt-oss-20b", "2025-08", "21B-MoE", 0.018, 0.09),
    ("gpt-3.5-turbo", "openrouter", "openai/gpt-3.5-turbo", "2023-05", "legacy", 0.50, 1.50),
    ("gpt-4o-mini", "openrouter", "openai/gpt-4o-mini", "2024-07", "legacy", 0.15, 0.60),
)
_EXTRA_SERVED_AS = {"grok-build-0.1": ("grok-code-fast-1",)}

LADDER: dict[str, Rung] = {
    name: Rung(
        name,
        provider,
        model_id,
        released,
        tier,
        p_in,
        p_out,
        (model_id, *_EXTRA_SERVED_AS.get(name, ())),
    )
    for name, provider, model_id, released, tier, p_in, p_out in _RUNGS
}


class EchoCheckedClient(OpenAICompatClient):
    """:class:`OpenAICompatClient` that also checks the model name the response echoes."""

    def __init__(self, endpoint: EndpointConfig, served_as: tuple[str, ...], **kwargs) -> None:
        super().__init__(endpoint, **kwargs)
        self._served_as = tuple(served_as)

    def complete_metered(
        self, prompt: str, *, decoding: DecodingConfig, system: str | None = None
    ) -> RawResponse:
        if decoding.seed is not None and not self._endpoint.supports_seed:
            raise UnsupportedDecodingError(f"{self._endpoint.name!r} rejects the seed parameter")
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict = {
            "model": self._endpoint.model_id,
            "messages": messages,
            "temperature": decoding.temperature,
        }
        if decoding.seed is not None:
            kwargs["seed"] = decoding.seed
        if self._endpoint.extra_body is not None:
            kwargs["extra_body"] = dict(self._endpoint.extra_body)
        response = self._client.chat.completions.create(**kwargs)
        served = str(getattr(response, "model", "") or "").removeprefix("models/")
        if served not in self._served_as:
            raise ServedModelMismatch(
                f"requested {self._endpoint.model_id!r} but the response says {served!r}"
            )
        if response.usage is None:
            raise MissingUsageError(f"{self._endpoint.name!r} returned no usage")
        return RawResponse(
            text=response.choices[0].message.content or "",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )
