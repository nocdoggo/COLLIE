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
    gemini_hosted_confirmation,
    gemini_primary,
    resolve_decoding,
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
    "gemini_hosted_confirmation",
    "gemini_primary",
    "resolve_decoding",
]
