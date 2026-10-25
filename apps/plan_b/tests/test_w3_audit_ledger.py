"""Spend-ledger fixes of the Wave 3 freeze audit: the ledger never counts less than may have
been spent (audit B4-B6). A temporary ledger and a scripted opener; nothing reaches a network.

* A reservation an earlier call of the same run left (an unexpected error after the reply) is
  charged at its bound before the next call, so a refusal can no longer drop it (B4).
* A connection lost after the request went out is charged at its bound, as a timeout is; a
  failure before sending (a refused connection) and an HTTP error status stay unbilled (B5).
* Reservations of ended processes are settled on every ledger update, not only on the next
  reservation, and a reused process id with another start time is not the owner (B6).
"""

from __future__ import annotations

import json
import os
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent.provider import (
    SpendCapReached,
    SpendLedger,
    _process_start,
    upper_bound_usd,
)
from tests.test_agent_provider import FakeOpener, echo_request, make_config, make_provider


def _ledger(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bound(provider: Any) -> float:
    data = json.dumps(provider.body(echo_request()), ensure_ascii=False).encode("utf-8")
    return upper_bound_usd(provider.config.model_id, len(data), echo_request().max_tokens)


def test_a_reservation_left_by_an_escaped_call_is_charged_before_the_next_call(
    tmp_path: Path,
) -> None:
    cfg = make_config(tmp_path, run_cap=1.0, total_cap=5.0)
    # Content parts with a null text: parsing raises TypeError after the call was answered.
    envelope = {
        "id": "gen-x",
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": [{"type": "text", "text": None}]},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.004},
    }
    provider = make_provider(cfg, FakeOpener(lambda body: envelope))
    bound = _bound(provider)
    with pytest.raises(TypeError):
        provider.complete(echo_request())
    assert _ledger(cfg.ledger_path)["reservations"]  # in flight, never charged
    provider.guard.max_run_usd = 0.0  # the run's next call is refused by its per-run cap
    with pytest.raises(SpendCapReached):
        provider.complete(echo_request())
    data = _ledger(cfg.ledger_path)
    assert "reservations" not in data
    assert [c["outcome"] for c in data["calls"]] == ["abandoned", "spend_cap"]
    assert data["total_cost_usd"] == pytest.approx(bound)
    assert provider.guard.run_spent_usd == pytest.approx(bound)


def test_a_connection_lost_after_sending_is_charged_at_its_bound(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)
    provider = make_provider(cfg, FakeOpener(lambda body: ConnectionResetError("reset by peer")))
    bound = _bound(provider)
    with pytest.raises(Exception, match="transport"):
        provider.complete(echo_request())
    call = _ledger(cfg.ledger_path)["calls"][-1]
    assert (call["outcome"], call["cost_basis"]) == ("transport", "upper_bound_estimate")
    assert call["cost_usd"] == pytest.approx(bound)


def test_failures_before_sending_and_http_statuses_stay_unbilled(tmp_path: Path) -> None:
    cfg = make_config(tmp_path)

    def refused(body: dict[str, Any]) -> Exception:
        return urllib.error.URLError(ConnectionRefusedError("connection refused"))

    def status(body: dict[str, Any]) -> Exception:
        import io

        return urllib.error.HTTPError(
            cfg.chat_url,
            503,
            "Unavailable",
            None,  # type: ignore[arg-type]
            io.BytesIO(b"down"),
        )

    for reply in (refused, status):
        provider = make_provider(cfg, FakeOpener(reply))
        with pytest.raises(Exception):  # noqa: B017 - the typed provider errors
            provider.complete(echo_request())
    calls = _ledger(cfg.ledger_path)["calls"]
    assert [(c["outcome"], c["cost_usd"], c["cost_basis"]) for c in calls] == [
        ("transport", 0.0, "not_billed"),
        ("http_status", 0.0, "not_billed"),
    ]


def _reserve_as(ledger: SpendLedger, pid: int, pid_start: str | None) -> None:
    """Rewrite the newest reservation's owner (another process, or a reused id)."""
    data = ledger.read()
    data["reservations"][-1] |= {"pid": pid, "pid_start": pid_start}
    ledger._write(data)


def test_reservations_of_ended_processes_are_settled_on_any_update(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "model_spend.json")
    rid, refusal = ledger.reserve(run_id="r1", call_id="c1", amount_usd=0.01, max_total_usd=1.0)
    assert rid is not None and refusal is None
    _reserve_as(ledger, 2**22 + 12345, None)  # no such process
    total = ledger.append({"run_id": "r2", "outcome": "ok", "cost_usd": 0.002})
    data = ledger.read()
    assert "reservations" not in data
    assert [c["outcome"] for c in data["calls"]] == ["ok", "abandoned"]
    assert total == pytest.approx(0.012)


@pytest.mark.skipif(_process_start(os.getpid()) is None, reason="needs /proc")
def test_a_reused_process_id_is_not_the_reservations_owner(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "model_spend.json")
    ledger.reserve(run_id="r1", call_id="c1", amount_usd=0.01, max_total_usd=1.0)
    assert ledger.read()["reservations"][-1]["pid_start"] == _process_start(os.getpid())
    _reserve_as(ledger, os.getpid(), "0")  # this pid, but a different start time
    ledger.release(None)
    ledger.append({"run_id": "r2", "outcome": "ok", "cost_usd": 0.0})
    assert [c["outcome"] for c in ledger.read()["calls"]] == ["ok", "abandoned"]
    # The live owner (this process, its start time) keeps its reservation.
    ledger.reserve(run_id="r3", call_id="c3", amount_usd=0.01, max_total_usd=1.0)
    ledger.append({"run_id": "r4", "outcome": "ok", "cost_usd": 0.0})
    assert len(ledger.read()["reservations"]) == 1


def test_a_tls_failure_mid_reply_is_charged_at_its_bound(tmp_path: Path) -> None:
    import ssl

    cfg = make_config(tmp_path)
    provider = make_provider(
        cfg, FakeOpener(lambda body: urllib.error.URLError(ssl.SSLError("bad record mac")))
    )
    bound = _bound(provider)
    with pytest.raises(Exception, match="transport"):
        provider.complete(echo_request())
    call = _ledger(cfg.ledger_path)["calls"][-1]
    assert call["cost_basis"] == "upper_bound_estimate" and call["cost_usd"] == pytest.approx(bound)
