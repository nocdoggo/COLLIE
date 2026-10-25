"""The G-LLM gate record names a raised exception by its class and a sanitized message: no
local path and no credential-shaped token reaches the record (audit item D2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent.gate import public_message, run_gate
from plan_b.scenarios.policy_host import PolicyHost
from tests.test_agent_provider import FAKE_KEY, FakeOpener, ScriptedModel, make_config


def test_a_gate_error_message_keeps_no_local_path_or_secret(tmp_path: Path) -> None:
    exc = OSError(
        f"database is locked: {tmp_path}/plan_b_gate_x/gate.sqlite3; ledger '{Path.home()}/l.json'"
        f" ~/keys/x; Authorization: Bearer {FAKE_KEY}; key {FAKE_KEY}; https://openrouter.test/api/v1"
    )
    text = public_message(exc)
    assert "database is locked: <path>; ledger '<path>' <path>;" in text
    assert "Authorization: <redacted>; key <redacted>;" in text
    assert "https://openrouter.test/api/v1" in text  # an endpoint URL is not a local path
    assert str(tmp_path) not in text and str(Path.home()) not in text and FAKE_KEY not in text
    assert len(public_message(OSError("x" * 500))) == 300


def test_the_gate_records_a_raised_exception_without_local_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raising(self: PolicyHost, *args: Any, **kwargs: Any) -> Any:
        raise OSError(f"unable to open {tmp_path}/plan_b_gate_x/gate.sqlite3 with {FAKE_KEY}")

    monkeypatch.setattr(PolicyHost, "run", raising)
    record = run_gate(make_config(tmp_path), opener=FakeOpener(ScriptedModel()), work_dir=tmp_path)
    assert record["verdict"] == "fail"
    assert record["error"] == {
        "type": "OSError",
        "message": "unable to open <path> with <redacted>",
    }
    assert (
        record["reasons"][0] == "the gate run raised OSError: unable to open <path> with <redacted>"
    )
    text = json.dumps(record)
    assert str(tmp_path) not in text and FAKE_KEY not in text
