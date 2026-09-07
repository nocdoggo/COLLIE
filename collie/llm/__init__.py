"""Branch G (P1). OpenAI-compatible client, prompt/response cache, call ledger."""

from collie.llm.cache import DiskCache, cache_key
from collie.llm.client import (
    DECODING_REGISTRY,
    ArmCallChannel,
    ConfirmatoryRefusalError,
    DecodingConfig,
    EndpointConfig,
    MeteredClient,
    MissingCredentialsError,
    MissingUsageError,
    OpenAICompatClient,
    RawResponse,
    Transport,
    UnsupportedDecodingError,
    gemini_primary,
    grok_hosted_confirmation,
    resolve_decoding,
    zai_endpoint,
)
from collie.llm.ledger import ArmTotals, CallLedger, LedgerSummary

__all__ = [
    "DECODING_REGISTRY",
    "ArmCallChannel",
    "ArmTotals",
    "CallLedger",
    "ConfirmatoryRefusalError",
    "DecodingConfig",
    "DiskCache",
    "EndpointConfig",
    "LedgerSummary",
    "MeteredClient",
    "MissingCredentialsError",
    "MissingUsageError",
    "OpenAICompatClient",
    "RawResponse",
    "Transport",
    "UnsupportedDecodingError",
    "cache_key",
    "gemini_primary",
    "grok_hosted_confirmation",
    "resolve_decoding",
    "zai_endpoint",
]
