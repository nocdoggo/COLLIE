"""LLM transport: endpoint configuration, decoding registry, and the metered client.

The reproducibility contract (research notes §4): deterministic decoding is `temperature=0` with
a recorded decoding hash, and the **disk cache** — not re-issuing seeded requests — is the
reproducibility mechanism. The Gemini OpenAI-compatible endpoint empirically rejects the OpenAI
``seed`` parameter (400 INVALID_ARGUMENT, verified 2026-09-06), so ``EndpointConfig`` carries an
explicit ``supports_seed`` flag and the client raises rather than silently dropping a seed.

Two serving paths, both operator-confirmed 2026-09-06 as Gemini via the OpenAI-compatible
endpoint: the primary sweep path and the hosted confirmation path. A missing key raises
:class:`MissingCredentialsError`; there is no fallback to any other provider or model, because a
silent substitution would make the confirmation subset meaningless.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from collie.contracts import ParseOutcome, Split

if TYPE_CHECKING:
    from collie.llm.cache import DiskCache
    from collie.llm.ledger import CallLedger

__all__ = [
    "DECODING_REGISTRY",
    "ConfirmatoryRefusalError",
    "DecodingConfig",
    "EndpointConfig",
    "MeteredClient",
    "MissingCredentialsError",
    "MissingUsageError",
    "RawResponse",
    "Transport",
    "UnsupportedDecodingError",
    "gemini_hosted_confirmation",
    "gemini_primary",
    "resolve_decoding",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KEY_FILE = REPO_ROOT / "cloud_endpoint" / "gemini.key"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class MissingCredentialsError(RuntimeError):
    """A required API key is absent. Raised, never worked around."""


class UnsupportedDecodingError(RuntimeError):
    """A decoding configuration the configured endpoint cannot honour (e.g. seed on Gemini)."""


class ConfirmatoryRefusalError(RuntimeError):
    """The three-seed robustness mode was asked to run against the confirmatory test set."""


class MissingUsageError(RuntimeError):
    """The provider returned no token usage; silent zeros would corrupt the cost ledger."""


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """One serving path: where, which model, how it is paid for, what it can honour.

    ``bills_thinking_as_output`` selects the billable-output rule: Gemini bills thinking tokens
    as output ("Output price (including thinking tokens)", pricing page), so billable output is
    ``total_tokens - prompt_tokens``; a plain OpenAI-compatible endpoint bills
    ``completion_tokens``. Raw usage fields are stored in the cache payload either way, so the
    rule can be re-derived.
    """

    name: str
    base_url: str
    model_id: str
    key_env: str
    key_file: Path | None
    supports_seed: bool
    bills_thinking_as_output: bool
    price_input_per_mtok: float
    price_output_per_mtok: float
    price_date: str
    """The retrieval date of the price figures (research notes §5). Cost is dated, not live."""

    def resolve_key(self) -> str:
        """The API key, from the environment first, then the key file. Missing raises."""
        import os

        from_env = os.environ.get(self.key_env, "").strip()
        if from_env:
            return from_env
        if self.key_file is not None and self.key_file.is_file():
            from_file = self.key_file.read_text(encoding="utf-8").strip()
            if from_file:
                return from_file
        raise MissingCredentialsError(
            f"endpoint {self.name!r} has no key: set ${self.key_env}"
            + (f" or populate {self.key_file}" if self.key_file is not None else "")
            + ". The hosted path never falls back to another provider."
        )


def gemini_primary(model_id: str = "gemini-3.8-flash") -> EndpointConfig:
    """The primary sweep path. Prices: dated list prices, research notes §5."""
    return EndpointConfig(
        name="gemini-primary",
        base_url=GEMINI_OPENAI_BASE_URL,
        model_id=model_id,
        key_env="GEMINI_API_KEY",
        key_file=DEFAULT_KEY_FILE,
        supports_seed=False,  # verified live 2026-09-06: the endpoint 400s on `seed`
        bills_thinking_as_output=True,
        price_input_per_mtok=0.75,
        price_output_per_mtok=3.75,
        price_date="2026-09-06",
    )


def gemini_hosted_confirmation(model_id: str = "gemini-3.8-flash") -> EndpointConfig:
    """The hosted confirmation path, used only on the preregistered confirmation subset.

    Same provider as the primary path per the operator's 2026-09-06 decision; the distinct name
    keeps confirmation accounting separable. When the operator names a second model for the
    confirmation subset, this factory's default changes and nothing else does.
    """
    return EndpointConfig(
        name="gemini-hosted-confirmation",
        base_url=GEMINI_OPENAI_BASE_URL,
        model_id=model_id,
        key_env="GEMINI_API_KEY",
        key_file=DEFAULT_KEY_FILE,
        supports_seed=False,
        bills_thinking_as_output=True,
        price_input_per_mtok=0.75,
        price_output_per_mtok=3.75,
        price_date="2026-09-06",
    )


@dataclass(frozen=True, slots=True)
class DecodingConfig:
    """One registered decoding configuration. The registered label *is* the decoding hash."""

    decoding_hash: str
    temperature: float
    seed: int | None


DECODING_REGISTRY: dict[str, DecodingConfig] = {
    "det-v1": DecodingConfig("det-v1", 0.0, None),
    "seed-1": DecodingConfig("seed-1", 0.0, 1),
    "seed-2": DecodingConfig("seed-2", 0.0, 2),
    "seed-3": DecodingConfig("seed-3", 0.0, 3),
}
"""The full sweep uses exactly ``det-v1`` (R2.2). The three seed variants exist only for the
stratified robustness subset and may only run where a seed is honoured."""


def resolve_decoding(
    mode: str, *, split: Split | None, endpoint: EndpointConfig
) -> tuple[DecodingConfig, ...]:
    """The decoding configurations a run may use.

    Two refusals are the point (R2.2, R2.7): the robustness mode never executes against the
    confirmatory test set, and it never silently degrades on an endpoint that cannot honour a
    seed.
    """
    if mode == "sweep":
        return (DECODING_REGISTRY["det-v1"],)
    if mode == "robustness":
        if split is Split.TEST:
            raise ConfirmatoryRefusalError(
                "the three-seed robustness mode refuses the confirmatory test set"
            )
        if not endpoint.supports_seed:
            raise UnsupportedDecodingError(
                f"endpoint {endpoint.name!r} does not honour a seed; the robustness mode "
                "cannot run here rather than pretending to vary one"
            )
        return tuple(DECODING_REGISTRY[f"seed-{i}"] for i in (1, 2, 3))
    raise ValueError(f"unknown decoding mode {mode!r}; expected 'sweep' or 'robustness'")


@dataclass(frozen=True, slots=True)
class RawResponse:
    """What a transport returns: text plus the provider's token accounting."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def billable_output(self, endpoint: EndpointConfig) -> int:
        if endpoint.bills_thinking_as_output:
            return max(0, self.total_tokens - self.prompt_tokens)
        return self.completion_tokens


@runtime_checkable
class Transport(Protocol):
    """One request in, one metered response out. Latency is measured by the caller."""

    @property
    def model_id(self) -> str: ...

    def complete_metered(
        self, prompt: str, *, decoding: DecodingConfig, system: str | None = None
    ) -> RawResponse: ...


class OpenAICompatClient:
    """A :class:`Transport` over any OpenAI-compatible chat-completions endpoint.

    ``openai`` is imported lazily: the ``llm`` extra is optional, and importing
    ``collie.llm`` must work without it. Construction resolves the key eagerly — a missing key
    fails here, at setup, not mid-episode.
    """

    def __init__(
        self,
        endpoint: EndpointConfig,
        *,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        key = endpoint.resolve_key()
        import openai

        self._endpoint = endpoint
        self._client = openai.OpenAI(
            api_key=key,
            base_url=endpoint.base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    @property
    def model_id(self) -> str:
        return self._endpoint.model_id

    def complete_metered(
        self, prompt: str, *, decoding: DecodingConfig, system: str | None = None
    ) -> RawResponse:
        if decoding.seed is not None and not self._endpoint.supports_seed:
            raise UnsupportedDecodingError(
                f"endpoint {self._endpoint.name!r} rejects the seed parameter (verified "
                "2026-09-06); refusing to pretend it was set"
            )
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
        response = self._client.chat.completions.create(**kwargs)
        if response.usage is None:
            raise MissingUsageError(
                f"endpoint {self._endpoint.name!r} returned no usage for a call; the ledger "
                "needs real token counts, not zeros"
            )
        return RawResponse(
            text=response.choices[0].message.content or "",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )


@dataclass(slots=True)
class MeteredClient:
    """The harness-level client: cache lookup, one physical call on miss, ledger writes.

    Arms never touch this directly; they hold an :class:`ArmCallChannel` from
    :meth:`channel`, which supplies the arm/episode/period context every ``CallLog`` needs and
    keeps the frozen :class:`~collie.contracts.LLMClient` protocol shape for parsers.
    """

    transport: Transport
    endpoint: EndpointConfig
    cache: DiskCache
    ledger: CallLedger

    def channel(self, *, arm_id: str, episode_id: str) -> ArmCallChannel:
        return ArmCallChannel(self, arm_id=arm_id, episode_id=episode_id)

    def _complete(
        self,
        prompt: str,
        *,
        decoding: DecodingConfig,
        state: str,
        arm_id: str,
        episode_id: str,
        period: int,
        attempt_index: int,
        system: str | None,
    ) -> tuple[str, str]:
        """One call, cached and charged. Returns ``(call_id, response_text)``."""
        from collie.llm.cache import cache_key

        key = cache_key(
            model_id=self.endpoint.model_id,
            prompt=prompt,
            state=state,
            decoding_hash=decoding.decoding_hash,
            system=system,
        )
        payload = self.cache.get(key)
        started = time.perf_counter()
        if payload is not None:
            raw = RawResponse(
                text=payload["text"],
                prompt_tokens=payload["prompt_tokens"],
                completion_tokens=payload["completion_tokens"],
                total_tokens=payload["total_tokens"],
            )
            cache_hit = True
        else:
            raw = self.transport.complete_metered(prompt, decoding=decoding, system=system)
            cache_hit = False
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not cache_hit:
            self.cache.put(key, raw)
            self.ledger.record_physical(
                arm_id=arm_id,
                episode_id=episode_id,
                period=period,
                model_id=self.endpoint.model_id,
                prompt_hash=key,
                decoding_hash=decoding.decoding_hash,
                attempt_index=attempt_index,
                raw=raw,
                latency_ms=latency_ms,
                endpoint=self.endpoint,
            )
        call_id = self.ledger.record_charged(
            arm_id=arm_id,
            episode_id=episode_id,
            period=period,
            model_id=self.endpoint.model_id,
            prompt_hash=key,
            decoding_hash=decoding.decoding_hash,
            attempt_index=attempt_index,
            raw=raw,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            endpoint=self.endpoint,
        )
        return call_id, raw.text


class ArmCallChannel:
    """An arm's view of the metered client. Implements the frozen ``LLMClient`` shape.

    ``complete(prompt, decoding_hash=...) -> str`` is the protocol method parsers use. The
    channel stamps each call with the arm, episode, and current period; the caller settles the
    entry with its parse outcome via :meth:`settle`. The ``state`` cache-key component is the
    decision-point identity (``episode_id#period``): identical prompts at the same decision
    point share one call; across decision points they never merge.
    """

    def __init__(self, metered: MeteredClient, *, arm_id: str, episode_id: str) -> None:
        self._metered = metered
        self.arm_id = arm_id
        self.episode_id = episode_id
        self._period = 0
        self._last_call_id: str | None = None

    @property
    def model_id(self) -> str:
        return self._metered.endpoint.model_id

    def set_period(self, period: int) -> None:
        self._period = period

    @property
    def last_call_id(self) -> str | None:
        return self._last_call_id

    def complete(self, prompt: str, *, decoding_hash: str = "det-v1") -> str:
        return self._call(prompt, decoding_hash=decoding_hash, system=None, attempt_index=0)

    def complete_with_system(self, system: str, user: str, *, decoding_hash: str = "det-v1") -> str:
        """The two-message form the benchmark agents use (system prompt plus observation)."""
        return self._call(user, decoding_hash=decoding_hash, system=system, attempt_index=0)

    def complete_attempt(
        self, prompt: str, *, decoding_hash: str, attempt_index: int, system: str | None = None
    ) -> str:
        """A repair attempt: same machinery, explicit attempt index for the ledger."""
        return self._call(
            prompt, decoding_hash=decoding_hash, system=system, attempt_index=attempt_index
        )

    def _call(
        self, prompt: str, *, decoding_hash: str, system: str | None, attempt_index: int
    ) -> str:
        decoding = DECODING_REGISTRY.get(decoding_hash)
        if decoding is None:
            raise ValueError(
                f"unregistered decoding hash {decoding_hash!r}; register it in "
                "DECODING_REGISTRY so the sweep's decoding is auditable"
            )
        self._last_call_id, text = self._metered._complete(
            prompt,
            decoding=decoding,
            state=f"{self.episode_id}#{self._period}",
            arm_id=self.arm_id,
            episode_id=self.episode_id,
            period=self._period,
            attempt_index=attempt_index,
            system=system,
        )
        return text

    def settle(self, call_id: str, outcome: ParseOutcome) -> None:
        """Record the parse outcome of a logged call. Every attempted call must settle."""
        self._metered.ledger.settle(call_id, outcome)
