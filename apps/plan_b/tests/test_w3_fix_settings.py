"""Equal generation settings and run seeds for P1, P2 and P3 (Wave 3 pre-freeze items 3 and 4).

One output limit (``MAX_OUTPUT_TOKENS``, 4096) for every model call of the three policies, no
sampling parameter (no endpoint of the configured model accepts ``temperature``), and the run's
seed: ``run_case(..., seed=...)`` passes it through the policy factories to the provider, which
sends it as the OpenAI-compatible ``seed`` unless the model's endpoints refuse it (the
configured OpenRouter model does: ``SEED_UNSUPPORTED``). Every call records the settings, the
requested seed, whether it was sent and what the reply echoed. Scripted transports only.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

import plan_b.scenarios.runner as runner
from plan_b.agent.config import ModelConfig, load_model_config
from plan_b.agent.provider import (
    MAX_OUTPUT_TOKENS,
    SEED_UNSUPPORTED,
    TEMPERATURE,
    OpenAICompatibleProvider,
    SpendGuard,
    SpendLedger,
)
from plan_b.scenarios.policy_host import (
    DEVELOPMENT_CAPS,
    live_factory,
    policy_factory_for,
    tool_use_factory,
    verify_all_factory,
)
from plan_b.store.database import Database
from tests.conftest import Sandbox
from tests.test_agent_provider import FAKE_KEY, FakeOpener, echo_request, make_config
from tests.test_live_workflow import build, run_with

KINDS = ("P1", "P2", "P3")


def _openrouter_config(tmp_path: Path, model_id: str) -> ModelConfig:
    key = tmp_path / "keys" / "fake.key"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(FAKE_KEY + "\n", encoding="utf-8")
    return load_model_config(
        {
            "PLAN_B_MODEL_PROVIDER": "openrouter",
            "PLAN_B_MODEL_BASE_URL": "https://openrouter.ai/api/v1",
            "PLAN_B_MODEL_KEY_FILE": str(key),
            "PLAN_B_MODEL_ID": model_id,
        },
        repo_root=tmp_path,
        endpoint_file=tmp_path / "absent.env",
        ledger_path=tmp_path / "var" / "model_spend.json",
    )


@pytest.mark.parametrize("kind", KINDS)
def test_every_model_call_of_p1_p2_and_p3_has_the_same_settings(
    db: Database, tmp_path: Path, kind: str
) -> None:
    policy, opener = build(kind, tmp_path)
    result = run_with(db, "dev01", policy)
    calls = [c for d in result.history.decisions for c in d.details["model"]["calls"]]
    assert calls and len(calls) == len(opener.bodies)
    for call in calls:
        assert (call["max_tokens"], call["temperature"], call["provider"]) == (
            MAX_OUTPUT_TOKENS,
            TEMPERATURE,
            "openrouter",
        ), (kind, call["purpose"])
        assert (call["seed"], call["seed_sent"]) == (None, False)
    for body in opener.bodies:
        assert body["max_tokens"] == MAX_OUTPUT_TOKENS == 4096
        assert "temperature" not in body and "seed" not in body
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["provider"] == {"require_parameters": True}


def test_run_case_takes_a_keyword_only_seed_and_hands_it_to_the_factory(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parameter = inspect.signature(runner.run_case).parameters["seed"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is None
    seen: list[Any] = []
    policy, _ = build("P2", tmp_path)

    def factory_for(choice: str, profile_id: str, **kw: Any) -> Any:
        seen.append((choice, kw.get("seed")))
        return lambda: policy

    monkeypatch.setattr(runner, "policy_factory_for", factory_for)
    runner.run_case(db, "dev01", policy="live", seed=11, live_config=make_config(tmp_path))
    assert seen == [("live", 11)]


@pytest.mark.parametrize("make", [live_factory, tool_use_factory, verify_all_factory])
def test_each_model_factory_gives_its_provider_the_seed(tmp_path: Path, make: Any) -> None:
    cfg = make_config(tmp_path)
    for seed in (None, 3):
        made = make(DEVELOPMENT_CAPS, cfg, seed=seed)()
        provider = made._provider
        assert isinstance(provider, OpenAICompatibleProvider) and provider.seed == seed
    choice = {live_factory: "live", tool_use_factory: "tool-use", verify_all_factory: "verify-all"}
    built = policy_factory_for(choice[make], "campus_showcase", live_config=cfg, seed=5)()._provider  # type: ignore[attr-defined]
    assert built.seed == 5
    assert policy_factory_for("rules", "campus_showcase", seed=5)().policy_id == "rules/1.0.0"


def test_a_seed_is_sent_and_recorded_with_what_the_reply_echoed(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)  # a test model: its endpoints are not known to refuse a seed

    def reply(body: dict[str, Any]) -> Any:
        content = json.dumps({"word": "hi"})
        return {
            "id": "gen-seeded",
            "model": "test/scripted-model-20261024",
            "seed": body.get("seed"),
            "system_fingerprint": "fp_test",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
        }

    opener = FakeOpener(reply)
    provider = _provider(cfg, opener, seed=42)
    record = provider.complete(echo_request()).record
    assert opener.bodies[0]["seed"] == 42
    assert (record.seed, record.seed_sent, record.seed_echo) == (42, True, 42)
    assert record.system_fingerprint == "fp_test" and record.temperature is None


def test_the_configured_openrouter_model_records_its_seed_without_sending_it(
    tmp_path: Path,
) -> None:
    # 2026-10-25: no endpoint of this model lists ``seed``, and a seeded request was refused
    # (HTTP 404 "No endpoints found that can handle the requested parameters", not billed).
    (model,) = sorted(SEED_UNSUPPORTED)
    cfg = _openrouter_config(tmp_path, model)
    opener = FakeOpener(lambda body: {"word": "hi"})
    record = _provider(cfg, opener, seed=42).complete(echo_request()).record
    assert "seed" not in opener.bodies[0]
    assert (record.seed, record.seed_sent, record.seed_echo) == (42, False, None)


def _provider(cfg: ModelConfig, opener: Any, *, seed: int | None) -> OpenAICompatibleProvider:
    guard = SpendGuard(
        SpendLedger(cfg.ledger_path),
        max_run_usd=cfg.max_run_cost_usd,
        max_total_usd=cfg.max_total_cost_usd,
        run_id="seed-test",
    )
    provider = OpenAICompatibleProvider(cfg, guard, timeout_s=5.0, seed=seed)
    provider._opener = opener
    return provider


def test_a_seeded_scripted_run_records_the_seed_on_every_call(db: Database, tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    made = policy_factory_for("live", "campus_showcase", live_config=cfg, seed=9)()
    _, scripted = build("P2", tmp_path / "script")  # the scripted transport of the P2 tests
    made._provider._opener = scripted  # type: ignore[attr-defined]
    sb = Sandbox(db, "dev01")
    result = made.run(sb.agent)
    calls = [c for d in result.decisions for c in d.details["model"]["calls"]]
    assert calls and all((c["seed"], c["seed_sent"]) == (9, True) for c in calls)
