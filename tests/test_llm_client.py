"""Task 20 — LLM transport: endpoints, decoding discipline, and the metered client.

Everything here runs against in-memory stubs except the explicitly marked ``needs_llm`` live
smoke test, which runs only when the operator's key material is present and never in CI.
"""

from __future__ import annotations

import types
from typing import ClassVar

import pytest

import collie.llm.client as client_mod
from collie.contracts import Split
from collie.llm import (
    DECODING_REGISTRY,
    ConfirmatoryRefusalError,
    EndpointConfig,
    MissingCredentialsError,
    MissingUsageError,
    OpenAICompatClient,
    UnsupportedDecodingError,
    gemini_hosted_confirmation,
    gemini_primary,
    resolve_decoding,
)
from collie.llm.demo import ScriptedTransport, scripted_endpoint


def _endpoint(**overrides) -> EndpointConfig:
    base = dict(
        name="test-endpoint",
        base_url="memory://none",
        model_id="test-model",
        key_env="COLLIE_TEST_KEY",
        key_file=None,
        supports_seed=True,
        bills_thinking_as_output=False,
        price_input_per_mtok=1.0,
        price_output_per_mtok=2.0,
        price_date="2026-09-06",
    )
    base.update(overrides)
    return EndpointConfig(**base)


# ---------------------------------------------------------------------------
# credentials: raise, never fall back
# ---------------------------------------------------------------------------


def test_missing_hosted_key_raises(monkeypatch, tmp_path) -> None:
    """The hosted path raises on a missing key; there is no local fallback to take."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(client_mod, "DEFAULT_KEY_FILE", tmp_path / "absent.key")
    with pytest.raises(MissingCredentialsError, match="never falls back"):
        gemini_hosted_confirmation().resolve_key()


def test_key_resolution_prefers_env_then_file(monkeypatch, tmp_path) -> None:
    endpoint = _endpoint(key_file=tmp_path / "k.key")
    monkeypatch.setenv("COLLIE_TEST_KEY", "from-env")
    assert endpoint.resolve_key() == "from-env"
    monkeypatch.delenv("COLLIE_TEST_KEY")
    with pytest.raises(MissingCredentialsError):
        endpoint.resolve_key()
    (tmp_path / "k.key").write_text("from-file\n")
    assert endpoint.resolve_key() == "from-file"  # whitespace stripped


def test_empty_key_file_is_missing(monkeypatch, tmp_path) -> None:
    (tmp_path / "k.key").write_text("\n")
    monkeypatch.delenv("COLLIE_TEST_KEY", raising=False)
    with pytest.raises(MissingCredentialsError):
        _endpoint(key_file=tmp_path / "k.key").resolve_key()


# ---------------------------------------------------------------------------
# decoding discipline
# ---------------------------------------------------------------------------


def test_sweep_mode_is_one_deterministic_configuration() -> None:
    (only,) = resolve_decoding("sweep", split=Split.TEST, endpoint=gemini_primary())
    assert only is DECODING_REGISTRY["det-v1"]
    assert only.temperature == 0.0 and only.seed is None


def test_robustness_mode_refuses_the_confirmatory_set() -> None:
    with pytest.raises(ConfirmatoryRefusalError, match="confirmatory test set"):
        resolve_decoding("robustness", split=Split.TEST, endpoint=scripted_endpoint())


def test_robustness_mode_requires_seed_support() -> None:
    """Gemini rejects ``seed`` (verified live), so the robustness mode cannot run there."""
    with pytest.raises(UnsupportedDecodingError, match="does not honour a seed"):
        resolve_decoding("robustness", split=Split.DEV, endpoint=gemini_primary())


def test_robustness_mode_yields_three_seeds_where_honoured() -> None:
    configs = resolve_decoding("robustness", split=Split.NULL_AUDIT, endpoint=scripted_endpoint())
    assert [c.seed for c in configs] == [1, 2, 3]
    assert [c.decoding_hash for c in configs] == ["seed-1", "seed-2", "seed-3"]


def test_unknown_decoding_mode_raises() -> None:
    with pytest.raises(ValueError, match="unknown decoding mode"):
        resolve_decoding("yolo", split=Split.DEV, endpoint=scripted_endpoint())


# ---------------------------------------------------------------------------
# the OpenAI-compatible transport, against a recording stub
# ---------------------------------------------------------------------------


class _StubOpenAI:
    """Records constructor and create() kwargs; returns a canned completion.

    Class attribute ``usage_result``: the sentinel ``_DEFAULT`` yields prompt 16 / completion 5 /
    total 96 (75 hidden thinking tokens); set it to ``None`` to simulate a provider that omits
    usage entirely.
    """

    _DEFAULT: ClassVar = object()
    init_kwargs: ClassVar[dict] = {}
    create_kwargs: ClassVar[list[dict]] = []
    usage_result: ClassVar[object] = _DEFAULT

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs

        def create(**kw):
            type(self).create_kwargs.append(kw)
            usage = type(self).usage_result
            if usage is _StubOpenAI._DEFAULT:
                usage = types.SimpleNamespace(
                    prompt_tokens=16, completion_tokens=5, total_tokens=96
                )
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{}"))],
                usage=usage,
            )

        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))


@pytest.fixture
def stub_openai(monkeypatch):
    _StubOpenAI.init_kwargs = {}
    _StubOpenAI.create_kwargs = []
    _StubOpenAI.usage_result = _StubOpenAI._DEFAULT
    monkeypatch.setenv("COLLIE_TEST_KEY", "stub-key")
    monkeypatch.setattr("openai.OpenAI", _StubOpenAI)
    return _StubOpenAI


def test_client_constructs_with_base_url_and_key(stub_openai) -> None:
    client = OpenAICompatClient(
        _endpoint(base_url="http://example.invalid/v1"), timeout=30, max_retries=0
    )
    assert client.model_id == "test-model"
    assert stub_openai.init_kwargs == {
        "api_key": "stub-key",
        "base_url": "http://example.invalid/v1",
        "timeout": 30,
        "max_retries": 0,
    }


def test_construction_raises_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("COLLIE_TEST_KEY", raising=False)
    with pytest.raises(MissingCredentialsError):
        OpenAICompatClient(_endpoint())


def test_seed_omitted_for_plain_sweep_decoding(stub_openai) -> None:
    client = OpenAICompatClient(_endpoint())
    raw = client.complete_metered("hello", decoding=DECODING_REGISTRY["det-v1"])
    assert "seed" not in stub_openai.create_kwargs[0]
    assert stub_openai.create_kwargs[0]["temperature"] == 0.0
    assert raw.text == "{}"


def test_seed_sent_when_supported_and_requested(stub_openai) -> None:
    client = OpenAICompatClient(_endpoint())
    client.complete_metered("hello", decoding=DECODING_REGISTRY["seed-2"])
    assert stub_openai.create_kwargs[0]["seed"] == 2


def test_seed_raises_on_an_endpoint_that_rejects_it(stub_openai) -> None:
    """The Gemini path must refuse to pretend a seed was set (verified live 2026-09-06)."""
    client = OpenAICompatClient(gemini_primary())
    with pytest.raises(UnsupportedDecodingError, match="rejects the seed"):
        client.complete_metered("hello", decoding=DECODING_REGISTRY["seed-1"])
    assert stub_openai.create_kwargs == []  # no request was ever sent


def test_system_and_user_messages_rendered_in_order(stub_openai) -> None:
    client = OpenAICompatClient(_endpoint())
    client.complete_metered("user text", decoding=DECODING_REGISTRY["det-v1"], system="sys text")
    assert stub_openai.create_kwargs[0]["messages"] == [
        {"role": "system", "content": "sys text"},
        {"role": "user", "content": "user text"},
    ]


def test_billable_output_rules(stub_openai) -> None:
    client = OpenAICompatClient(_endpoint())
    raw = client.complete_metered("hello", decoding=DECODING_REGISTRY["det-v1"])
    # Stubbed usage: prompt 16, completion 5, total 96 -> 75 hidden thinking tokens.
    assert raw.billable_output(_endpoint()) == 5
    assert raw.billable_output(gemini_primary()) == 80  # thinking billed as output


def test_missing_usage_raises_loudly(stub_openai) -> None:
    stub_openai.usage_result = None
    client = OpenAICompatClient(_endpoint())
    with pytest.raises(MissingUsageError, match="no usage"):
        client.complete_metered("hello", decoding=DECODING_REGISTRY["det-v1"])


# ---------------------------------------------------------------------------
# channel discipline
# ---------------------------------------------------------------------------


def test_unregistered_decoding_hash_raises(tmp_path) -> None:
    from collie.llm import CallLedger, DiskCache, MeteredClient

    metered = MeteredClient(
        transport=ScriptedTransport(),
        endpoint=scripted_endpoint(),
        cache=DiskCache(tmp_path),
        ledger=CallLedger(),
    )
    channel = metered.channel(arm_id="a", episode_id="e")
    with pytest.raises(ValueError, match="unregistered decoding hash"):
        channel.complete("hi", decoding_hash="made-up")


# ---------------------------------------------------------------------------
# the live smoke test — never in CI, only with operator key material
# ---------------------------------------------------------------------------

_KEY_FILE = client_mod.DEFAULT_KEY_FILE


@pytest.mark.needs_llm
@pytest.mark.skipif(
    not _KEY_FILE.is_file() and not __import__("os").environ.get("GEMINI_API_KEY"),
    reason="no Gemini key material present",
)
def test_live_gemini_smoke() -> None:
    """One real call through the OpenAI-compatible path: text, usage, and model echo."""
    client = OpenAICompatClient(gemini_primary(), timeout=60.0, max_retries=0)
    raw = client.complete_metered(
        'Reply with exactly the JSON object {"ok": true} and nothing else.',
        decoding=DECODING_REGISTRY["det-v1"],
    )
    assert raw.text.strip()
    assert raw.prompt_tokens > 0 and raw.total_tokens >= raw.prompt_tokens
