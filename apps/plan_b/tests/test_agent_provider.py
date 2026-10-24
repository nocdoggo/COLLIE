"""Live-agent configuration, provider client and spend guard, without the network.

The provider is the real ``OpenAICompatibleProvider`` with its HTTP opener replaced by a
scripted ``FakeOpener`` (or, for timeouts and redirects, a 127.0.0.1 server started here). The
key is a planted fake in ``tmp_path``. ``FakeOpener``, ``ScriptedModel`` and ``make_config`` are
shared with the boundary tests.
"""

from __future__ import annotations

import http.server
import io
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from plan_b.agent.config import (
    DEFAULT_MAX_RUN_COST_USD,
    DEFAULT_MAX_TOTAL_COST_USD,
    DEFAULT_MODEL_ID,
    ModelConfig,
    ModelConfigError,
    load_model_config,
    read_endpoint_file,
)
from plan_b.agent.interpret import INTERPRET_SCHEMA_NAME
from plan_b.agent.provider import (
    ModelRequest,
    OpenAICompatibleProvider,
    ProviderConfigError,
    ProviderHTTPError,
    ProviderMalformedJSON,
    ProviderRefusal,
    ProviderSchemaViolation,
    ProviderTimeout,
    SpendCapReached,
    SpendGuard,
    SpendLedger,
    upper_bound_usd,
)

FAKE_KEY = "sk-or-v1-FAKE-0f1e2d3c4b5a69788796a5b4c3d2e1f0-planted-for-tests"
RETURNED_MODEL = "test/scripted-model-20261024"
REQUESTED_MODEL = "test/scripted-model"

Reply = Callable[[dict[str, Any]], Any]


# ---------------------------------------------------------------------------------- helpers


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)


class FakeOpener:
    """Stands in for the provider's HTTP opener: records every request and answers from a
    script. A reply may be assistant content (str or dict), a full envelope (a dict with
    ``choices``), raw bytes, or an exception to raise."""

    def __init__(
        self, reply: Reply, *, model: str = RETURNED_MODEL, cost: float | None = 0.0012
    ) -> None:
        self.reply = reply
        self.model = model
        self.cost = cost
        self.requests: list[urllib.request.Request] = []
        self.bodies: list[dict[str, Any]] = []

    def open(self, request: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        self.requests.append(request)
        assert isinstance(request.data, bytes)
        body = json.loads(request.data)
        self.bodies.append(body)
        out = self.reply(body)
        if isinstance(out, BaseException):
            raise out
        if isinstance(out, bytes):
            return FakeResponse(200, out)
        if isinstance(out, dict) and "choices" in out:
            return FakeResponse(200, json.dumps(out).encode())
        content = out if isinstance(out, str) else json.dumps(out)
        usage: dict[str, Any] = {
            "prompt_tokens": len(request.data) // 4,
            "completion_tokens": 80,
            "total_tokens": len(request.data) // 4 + 80,
        }
        if self.cost is not None:
            usage["cost"] = self.cost
        payload = {
            "id": f"gen-test-{len(self.requests):03d}",
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }
        return FakeResponse(200, json.dumps(payload).encode())


def section(text: str, tag: str) -> Any:
    match = re.search(rf"<{tag}>\n(.*)\n</{tag}>", text, re.S)
    assert match is not None, f"no <{tag}> block"
    return json.loads(match.group(1))


def schema_name(body: dict[str, Any]) -> str:
    return str(body["response_format"]["json_schema"]["name"])


def menu_ids(body: dict[str, Any]) -> list[str]:
    return list(body["response_format"]["json_schema"]["schema"]["properties"]["option_id"]["enum"])


def state_of(body: dict[str, Any]) -> dict[str, Any]:
    state = section(body["messages"][1]["content"], "plan_b_state")
    assert isinstance(state, dict)
    return state


def observations_of(body: dict[str, Any]) -> list[dict[str, Any]]:
    obs = section(body["messages"][1]["content"], "untrusted_observations")
    assert isinstance(obs, list)
    return obs


def reading(oid: str, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "observation_id": oid,
        "subject_id": None,
        "change_kind": "unresolved",
        "applicability": "unclear",
        "claimed_eta_local": None,
        "promised_local": None,
        "order_ref": None,
        "referenced_date": None,
        "interpretation": "The notice does not state a supported claim.",
        "unresolved_fields": ["wording"],
        "proposed_checks": [],
        "evidence_refs": [oid],
        "contains_instructions": False,
    }
    return base | fields


_DELAY = re.compile(r"(\d+) minutes later than the promised (\d+) p\.m\.")


def default_reading(obs: dict[str, Any]) -> dict[str, Any]:
    """A careful reader: the dev01 delay sentence is a claim, anything else unresolved."""
    match = _DELAY.search(obs["text"].lower())
    if match is None:
        flagged = any(w in obs["text"].lower() for w in ("ignore", "approve", "authorize"))
        return reading(obs["observation_id"], contains_instructions=flagged)
    hour, minutes = int(match.group(2)) + 12, int(match.group(1))
    return reading(
        obs["observation_id"],
        subject_id="projector",
        change_kind="delay",
        applicability="applies",
        claimed_eta_local=f"{hour + minutes // 60:02d}:{minutes % 60:02d}",
        promised_local=f"{hour:02d}:00",
        order_ref="P17",
        interpretation="The projector delivery may arrive after the demonstrations start.",
        unresolved_fields=["current delivery status"],
        proposed_checks=["query_status"],
    )


class ScriptedModel:
    """A scripted model: careful interpretations, and the first menu option whose id starts
    with the earliest preferred prefix. ``interpret``/``choose`` override either part."""

    def __init__(
        self,
        *,
        prefer: tuple[str, ...] = ("query:", "apply:", "hold:", "ask:", "keep", "wait"),
        interpret: Reply | None = None,
        choose: Reply | None = None,
    ) -> None:
        self.prefer = prefer
        self.interpret = interpret
        self.choose = choose

    def __call__(self, body: dict[str, Any]) -> Any:
        if schema_name(body) == INTERPRET_SCHEMA_NAME:
            if self.interpret is not None:
                return self.interpret(body)
            return {"interpretations": [default_reading(o) for o in observations_of(body)]}
        if self.choose is not None:
            return self.choose(body)
        return self.pick(body)

    def pick(self, body: dict[str, Any]) -> dict[str, Any]:
        ids = menu_ids(body)
        state = state_of(body)
        cited = [r["tool_call_id"] for r in state["last_tool_results"]]
        for prefix in self.prefer:
            for option_id in ids:
                if option_id.startswith(prefix):
                    return {
                        "option_id": option_id,
                        "rationale": f"Scripted preference {prefix!r}.",
                        "cited_refs": cited,
                    }
        return {"option_id": ids[-1], "rationale": "Fallback.", "cited_refs": cited}


def make_config(
    tmp_path: Path,
    *,
    run_cap: float = 1.0,
    total_cap: float = 5.0,
    base_url: str = "https://openrouter.test/api/v1",
) -> ModelConfig:
    key = tmp_path / "keys" / "fake.key"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(FAKE_KEY + "\n", encoding="utf-8")
    env = {
        "PLAN_B_MODEL_PROVIDER": "openrouter",
        "PLAN_B_MODEL_BASE_URL": base_url,
        "PLAN_B_MODEL_KEY_FILE": str(key),
        "PLAN_B_MODEL_ID": REQUESTED_MODEL,
        "PLAN_B_MODEL_MAX_RUN_COST_USD": str(run_cap),
        "PLAN_B_MODEL_MAX_TOTAL_COST_USD": str(total_cap),
    }
    return load_model_config(
        env,
        repo_root=tmp_path,
        endpoint_file=tmp_path / "absent.env",
        ledger_path=tmp_path / "var" / "model_spend.json",
    )


def make_provider(
    config: ModelConfig, opener: Any = None, *, run_id: str = "test-run", timeout_s: float = 5.0
) -> OpenAICompatibleProvider:
    guard = SpendGuard(
        SpendLedger(config.ledger_path),
        max_run_usd=config.max_run_cost_usd,
        max_total_usd=config.max_total_cost_usd,
        run_id=run_id,
    )
    provider = OpenAICompatibleProvider(config, guard, timeout_s=timeout_s)
    if opener is not None:
        provider._opener = opener
    return provider


class Echo(BaseModel):
    word: str


ECHO_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["word"],
    "properties": {"word": {"type": "string"}},
}


def echo_request(**kw: Any) -> ModelRequest:
    return ModelRequest(
        purpose="test",
        system="Reply with one word.",
        user="Say hello.",
        schema_name="echo",
        schema=ECHO_SCHEMA,
        output_model=Echo,
        max_tokens=64,
        **kw,
    )


# ---------------------------------------------------------------------------------- config


def test_config_sources_defaults_and_relative_paths(tmp_path: Path) -> None:
    endpoint = tmp_path / ".local" / "keys" / "model_endpoint.env"
    endpoint.parent.mkdir(parents=True)
    endpoint.write_text(
        "# comment\nexport PLAN_B_MODEL_PROVIDER=openrouter\n"
        "PLAN_B_MODEL_BASE_URL='https://openrouter.ai/api/v1'\n"
        "PLAN_B_MODEL_KEY_FILE=.local/keys/openrouter.key\n"
        "OPENROUTER_API_KEY=sk-not-a-config-name\n",
        encoding="utf-8",
    )
    assert "OPENROUTER_API_KEY" not in read_endpoint_file(endpoint)
    cfg = load_model_config({}, repo_root=tmp_path)
    assert cfg.provider == "openrouter" and cfg.base_url == "https://openrouter.ai/api/v1"
    assert cfg.key_file == (tmp_path / ".local/keys/openrouter.key").resolve()
    assert cfg.model_id == DEFAULT_MODEL_ID == "anthropic/claude-sonnet-5.5"
    assert (
        (cfg.max_run_cost_usd, cfg.max_total_cost_usd)
        == (
            DEFAULT_MAX_RUN_COST_USD,
            DEFAULT_MAX_TOTAL_COST_USD,
        )
        == (0.50, 20.00)
    )
    assert cfg.sources["PLAN_B_MODEL_BASE_URL"] == "endpoint_file"
    assert cfg.sources["PLAN_B_MODEL_ID"] == "default"
    # The environment wins over the file.
    env = {"PLAN_B_MODEL_ID": "anthropic/claude-haiku-5.5", "PLAN_B_MODEL_MAX_RUN_COST_USD": "0.1"}
    cfg2 = load_model_config(env, repo_root=tmp_path)
    assert cfg2.model_id == "anthropic/claude-haiku-5.5" and cfg2.max_run_cost_usd == 0.1
    assert cfg2.sources["PLAN_B_MODEL_ID"] == "environment"
    public = json.dumps(cfg2.public())
    assert str(tmp_path) not in public and cfg2.public()["key_file"] == ".local/keys/openrouter.key"
    assert cfg2.public()["key_file_present"] is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PLAN_B_MODEL_PROVIDER", "anthropic_direct"),
        ("PLAN_B_MODEL_BASE_URL", "http://openrouter.ai/api/v1"),
        ("PLAN_B_MODEL_BASE_URL", "https://user:secret@openrouter.ai/api/v1"),
        ("PLAN_B_MODEL_BASE_URL", "https://openrouter.ai/api/v1?key=abc"),
        ("PLAN_B_MODEL_ID", "two words"),
        ("PLAN_B_MODEL_MAX_RUN_COST_USD", "-1"),
        ("PLAN_B_MODEL_MAX_RUN_COST_USD", "nan"),
        ("PLAN_B_MODEL_MAX_TOTAL_COST_USD", "0.01"),
    ],
)
def test_config_rejects_invalid_values(tmp_path: Path, name: str, value: str) -> None:
    env = {
        "PLAN_B_MODEL_PROVIDER": "openrouter",
        "PLAN_B_MODEL_BASE_URL": "https://openrouter.ai/api/v1",
        "PLAN_B_MODEL_KEY_FILE": "k.key",
        name: value,
    }
    with pytest.raises(ModelConfigError) as caught:
        load_model_config(env, repo_root=tmp_path, endpoint_file=tmp_path / "none.env")
    assert "secret" not in str(caught.value)


def test_config_requires_the_endpoint_names(tmp_path: Path) -> None:
    with pytest.raises(ModelConfigError, match="not configured"):
        load_model_config({}, repo_root=tmp_path, endpoint_file=tmp_path / "none.env")


def test_local_http_base_url_is_allowed_only_for_this_machine(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, base_url="http://127.0.0.1:9/api/v1")
    assert cfg.chat_url == "http://127.0.0.1:9/api/v1/chat/completions"


# ---------------------------------------------------------------------------------- provider


def test_request_is_strict_structured_output_with_usage_accounting(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    opener = FakeOpener(lambda body: {"word": "hello"})
    response = make_provider(cfg, opener).complete(echo_request())
    assert isinstance(response.parsed, Echo) and response.parsed.word == "hello"
    body = opener.bodies[0]
    assert body["model"] == REQUESTED_MODEL and body["max_tokens"] == 64
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == ECHO_SCHEMA
    assert body["usage"] == {"include": True}
    assert body["provider"] == {"require_parameters": True}
    request = opener.requests[0]
    assert request.full_url == "https://openrouter.test/api/v1/chat/completions"
    assert request.get_header("Authorization") == f"Bearer {FAKE_KEY}"
    assert FAKE_KEY not in request.data.decode() if isinstance(request.data, bytes) else True
    record = response.record
    assert record.model_id == RETURNED_MODEL and record.requested_model == REQUESTED_MODEL
    assert record.outcome == "ok" and record.cost_basis == "provider_usage"
    assert record.cost_usd == 0.0012 and record.prompt_tokens and record.completion_tokens == 80
    assert record.latency_ms >= 0 and record.generation_id == "gen-test-001"
    ledger = json.loads(cfg.ledger_path.read_text())
    assert ledger["total_cost_usd"] == 0.0012
    (entry,) = ledger["calls"]
    assert entry["model_requested"] == REQUESTED_MODEL
    assert entry["model_returned"] == RETURNED_MODEL
    assert entry["prompt_tokens"] == record.prompt_tokens and entry["completion_tokens"] == 80
    assert entry["cost_usd"] == 0.0012 and entry["outcome"] == "ok"
    assert cfg.ledger_path.stat().st_mode & 0o777 == 0o600


def test_cost_is_computed_from_prices_when_the_reply_reports_none(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    cfg = ModelConfig(**{**cfg.__dict__, "model_id": "anthropic/claude-sonnet-5.5"})
    opener = FakeOpener(lambda body: {"word": "hi"}, cost=None)
    record = make_provider(cfg, opener).complete(echo_request()).record
    assert record.cost_basis == "computed_from_prices"
    expected = (record.prompt_tokens or 0) * 2.0 / 1e6 + 80 * 10.0 / 1e6
    assert math.isclose(record.cost_usd, round(expected, 8))


def test_key_is_read_per_call(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    opener = FakeOpener(lambda body: {"word": "hi"})
    provider = make_provider(cfg, opener)
    provider.complete(echo_request())
    cfg.key_file.write_text("sk-or-v1-rotated-key\n", encoding="utf-8")
    provider.complete(echo_request())
    assert opener.requests[1].get_header("Authorization") == "Bearer sk-or-v1-rotated-key"
    cfg.key_file.unlink()
    with pytest.raises(ProviderConfigError) as caught:
        provider.complete(echo_request())
    assert len(opener.requests) == 2  # nothing was sent without a key
    assert "rotated" not in caught.value.message


@pytest.mark.parametrize(
    ("reply", "error", "outcome"),
    [
        (b"<html>not json</html>", ProviderMalformedJSON, "malformed_json"),
        ("this is prose, not JSON", ProviderMalformedJSON, "malformed_json"),
        ({"words": "hi"}, ProviderSchemaViolation, "schema_violation"),
        (
            {"choices": [{"message": {"role": "assistant", "refusal": "no"}}], "usage": {}},
            ProviderRefusal,
            "refused",
        ),
        (
            {
                "choices": [{"message": {"content": '{"word": "h'}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 64},
            },
            ProviderMalformedJSON,
            "malformed_json",
        ),
        ({"choices": [], "usage": {}}, ProviderMalformedJSON, "malformed_json"),
    ],
)
def test_malformed_and_invalid_replies_are_typed(
    tmp_path: Path, reply: Any, error: type[Exception], outcome: str
) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(error) as caught:
        make_provider(cfg, FakeOpener(lambda body: reply)).complete(echo_request())
    exc = caught.value
    assert getattr(exc, "record", None) is not None and exc.record.outcome == outcome  # type: ignore[attr-defined]
    entry = json.loads(cfg.ledger_path.read_text())["calls"][-1]
    assert entry["outcome"] == outcome


def test_http_status_errors_are_typed_and_scrubbed(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    body = json.dumps({"error": {"message": f"rate limited for key {FAKE_KEY}"}}).encode()

    def reply(_: dict[str, Any]) -> Exception:
        return urllib.error.HTTPError(cfg.chat_url, 429, "Too Many", None, io.BytesIO(body))  # type: ignore[arg-type]

    with pytest.raises(ProviderHTTPError) as caught:
        make_provider(cfg, FakeOpener(reply)).complete(echo_request())
    assert caught.value.status == 429
    assert FAKE_KEY not in caught.value.message and "[redacted]" in caught.value.message
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert FAKE_KEY not in cfg.ledger_path.read_text()


def test_transport_timeout_is_typed_and_charged_at_the_bound(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    with pytest.raises(ProviderTimeout) as caught:
        make_provider(cfg, FakeOpener(lambda body: TimeoutError("slow"))).complete(echo_request())
    record = caught.value.record
    assert record is not None and record.outcome == "timeout"
    assert record.cost_basis == "upper_bound_estimate" and record.cost_usd > 0


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        _SlowHandler.hits.append(self.path)
        if self.path.endswith("/redirect/chat/completions"):
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.end_headers()
            return
        time.sleep(2.0)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        return None


@pytest.fixture
def local_server() -> Iterator[str]:
    _SlowHandler.hits = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_bounded_timeout_against_a_local_server(tmp_path: Path, local_server: str) -> None:
    cfg = make_config(tmp_path, base_url=f"{local_server}/api/v1")
    provider = make_provider(cfg, timeout_s=0.5)
    t0 = time.monotonic()
    with pytest.raises(ProviderTimeout):
        provider.complete(echo_request())
    assert time.monotonic() - t0 < 1.8


def test_redirects_are_never_followed(tmp_path: Path, local_server: str) -> None:
    cfg = make_config(tmp_path, base_url=f"{local_server}/redirect")
    with pytest.raises(ProviderHTTPError) as caught:
        make_provider(cfg).complete(echo_request())
    assert caught.value.status == 302
    assert _SlowHandler.hits == ["/redirect/chat/completions"]


# ---------------------------------------------------------------------------------- spend


def test_spend_guard_refuses_a_call_over_the_per_run_cap(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, run_cap=0.0001, total_cap=5.0)
    opener = FakeOpener(lambda body: {"word": "hi"})
    with pytest.raises(SpendCapReached) as caught:
        make_provider(cfg, opener).complete(echo_request())
    assert opener.requests == []  # refused before anything was sent
    assert "per-run cap" in caught.value.message
    entry = json.loads(cfg.ledger_path.read_text())["calls"][-1]
    assert entry["outcome"] == "spend_cap" and entry["cost_usd"] == 0.0


def test_spend_guard_refuses_a_call_over_the_cumulative_cap(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, run_cap=1.0, total_cap=2.0)
    cfg.ledger_path.parent.mkdir(parents=True)
    cfg.ledger_path.write_text(
        json.dumps(
            {"ledger": "plan_b.model_spend", "version": 1, "total_cost_usd": 1.9999, "calls": []}
        ),
        encoding="utf-8",
    )
    opener = FakeOpener(lambda body: {"word": "hi"})
    with pytest.raises(SpendCapReached) as caught:
        make_provider(cfg, opener).complete(echo_request())
    assert "cumulative cap" in caught.value.message and opener.requests == []


def test_spend_guard_fails_closed_on_an_unreadable_ledger(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    cfg.ledger_path.parent.mkdir(parents=True)
    cfg.ledger_path.write_text("{not json", encoding="utf-8")
    opener = FakeOpener(lambda body: {"word": "hi"})
    with pytest.raises(SpendCapReached, match="unreadable"):
        make_provider(cfg, opener).complete(echo_request())
    assert opener.requests == []


def test_per_run_spend_accumulates_and_the_ledger_sums_every_call(tmp_path: Path) -> None:
    cfg = make_config(tmp_path, run_cap=0.05, total_cap=5.0)
    opener = FakeOpener(lambda body: {"word": "hi"}, cost=0.01)
    provider = make_provider(cfg, opener)
    for _ in range(3):
        provider.complete(echo_request())
    assert math.isclose(provider.guard.run_spent_usd, 0.03)
    ledger = json.loads(cfg.ledger_path.read_text())
    assert len(ledger["calls"]) == 3 and math.isclose(ledger["total_cost_usd"], 0.03)
    assert all(c["run_id"] == "test-run" for c in ledger["calls"])


def test_upper_bound_covers_max_tokens_at_ceiling_prices_for_unlisted_models() -> None:
    listed = upper_bound_usd("anthropic/claude-sonnet-5.5", 3000, 1000)
    unlisted = upper_bound_usd("someone/unknown-model", 3000, 1000)
    assert math.isclose(listed, (1000 * 2.0 + 1000 * 10.0) / 1e6)
    assert unlisted > listed
