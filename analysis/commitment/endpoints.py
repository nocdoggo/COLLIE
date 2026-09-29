"""The model ladder: which live endpoints the commitment study may call, at what dated price.

Every entry is an ``EndpointConfig`` built from the project's own factories, so keys are resolved
at runtime by :meth:`EndpointConfig.resolve_key` and never handled here. Prices are dated list
prices per 1M tokens (thinking billed as output), retrieved 2026-09-28: Gemini from OpenRouter's
public model list (``openrouter.ai/api/v1/models``), which matched Google's list for
``gemini-3.8-flash`` exactly (research notes §5); Grok from xAI's ``/v1/language-models``.

xAI silently serves retired ids as a current model (on 2026-09-28 ``grok-3``, ``grok-3-mini`` and
``grok-4-fast-non-reasoning`` all came back as ``grok-4.3``). :class:`EchoCheckedClient` therefore
compares the model name each response echoes against the requested one and refuses a mismatch,
so no ladder rung can quietly become another model.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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


LADDER: dict[str, Rung] = {
    rung.name: rung
    for rung in (
        Rung(
            "gemini-2.5-flash-lite",
            "gemini",
            "gemini-2.5-flash-lite",
            "2025-07",
            "small",
            0.10,
            0.40,
            ("gemini-2.5-flash-lite",),
        ),
        Rung(
            "gemini-2.5-flash",
            "gemini",
            "gemini-2.5-flash",
            "2025-06",
            "mid",
            0.30,
            2.50,
            ("gemini-2.5-flash",),
        ),
        Rung(
            "gemini-3-flash-preview",
            "gemini",
            "gemini-3-flash-preview",
            "2025-12",
            "mid",
            0.50,
            3.00,
            ("gemini-3-flash-preview",),
        ),
        Rung(
            "gemini-3.1-flash-lite",
            "gemini",
            "gemini-3.1-flash-lite",
            "2026-05",
            "small",
            0.25,
            1.50,
            ("gemini-3.1-flash-lite",),
        ),
        Rung(
            "gemini-3.8-flash",
            "gemini",
            "gemini-3.8-flash",
            "2026-09",
            "mid",
            0.75,
            3.75,
            ("gemini-3.8-flash",),
        ),
        Rung(
            "grok-build-0.1",
            "grok",
            "grok-build-0.1",
            "2025-08",
            "small",
            1.00,
            2.00,
            ("grok-build-0.1", "grok-code-fast-1"),
        ),
        Rung(
            "grok-4.20",
            "grok",
            "grok-4.20-0309-non-reasoning",
            "2026-03",
            "mid",
            1.25,
            2.50,
            ("grok-4.20-0309-non-reasoning",),
        ),
    )
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
