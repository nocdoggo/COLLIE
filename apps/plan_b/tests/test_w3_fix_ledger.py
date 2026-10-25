"""The spend ledger under several concurrent episode processes (Wave 3 pre-freeze item 5).

Each test starts real OS processes (``fork``) against one temporary ledger, as concurrent
evaluation episodes would share ``var/model_spend.json``. Every process runs the real provider
and spend guard; only the HTTP opener is scripted (``tests.test_agent_provider.FakeOpener``,
slowed down so calls overlap). Checked: no ledger update is lost under the ``fcntl`` lock; the
per-run cap holds in each process; the cumulative cap holds across all of them, because a
call's upper bound is reserved under the lock before it is sent; and a reservation left by a
process that died before charging is charged at its bound. Nothing reaches the network.
"""

from __future__ import annotations

import contextlib
import json
import math
import multiprocessing as mp
import os
import time
from pathlib import Path
from typing import Any

import pytest

from plan_b.agent.config import ModelConfig
from plan_b.agent.provider import (
    ProviderConfigError,
    SpendCapReached,
    SpendGuard,
    SpendLedger,
    upper_bound_usd,
)
from tests.test_agent_provider import FakeOpener, echo_request, make_config, make_provider

COST = 0.004  # what the scripted provider reports for each call
CTX = mp.get_context("fork")


class SlowOpener(FakeOpener):
    """A reply after a pause, so the processes' calls are in flight at the same time."""

    def open(self, request: Any, timeout: float | None = None) -> Any:
        time.sleep(0.05)
        return super().open(request, timeout)


def _bound(cfg: ModelConfig) -> float:
    provider = make_provider(cfg)
    data = json.dumps(provider.body(echo_request()), ensure_ascii=False).encode("utf-8")
    return upper_bound_usd(cfg.model_id, len(data), echo_request().max_tokens)


def _episode(cfg: ModelConfig, run_id: str, attempts: int, barrier: Any, out: Any) -> None:
    provider = make_provider(cfg, SlowOpener(lambda body: {"word": "hi"}, cost=COST), run_id=run_id)
    barrier.wait()
    outcomes: list[str] = []
    for _ in range(attempts):
        try:
            provider.complete(echo_request())
            outcomes.append("ok")
        except SpendCapReached as exc:
            outcomes.append("per_run" if "per-run" in exc.message else "cumulative")
    out.put((run_id, outcomes, provider.guard.run_spent_usd))


def _appender(path: str, worker: int, n: int, barrier: Any) -> None:
    ledger = SpendLedger(Path(path))
    barrier.wait()
    for i in range(n):
        ledger.append({"run_id": f"w{worker}", "call_id": f"mc_{i:04d}", "cost_usd": 0.001})


def _run_all(target: Any, args: list[tuple[Any, ...]]) -> None:
    procs = [CTX.Process(target=target, args=a) for a in args]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0, p.exitcode


def test_concurrent_processes_lose_no_ledger_update(tmp_path: Path) -> None:
    path = tmp_path / "var" / "model_spend.json"
    workers, per_worker = 8, 25
    barrier = CTX.Barrier(workers)
    _run_all(_appender, [(str(path), w, per_worker, barrier) for w in range(workers)])
    data = json.loads(path.read_text())
    assert len(data["calls"]) == workers * per_worker
    assert math.isclose(data["total_cost_usd"], workers * per_worker * 0.001)
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_per_run_and_cumulative_caps_hold_across_processes(tmp_path: Path) -> None:
    probe = make_config(tmp_path, run_cap=1.0, total_cap=5.0)
    bound = _bound(probe)
    assert bound >= COST  # the scripted cost stays within the bound the guard reserves
    # Each run may make two calls; the whole ledger allows six, fewer than the 8 x 2 asked.
    run_cap = 2 * COST + bound * 0.99
    total_cap = 6 * COST + bound * 0.5
    cfg = make_config(tmp_path, run_cap=run_cap, total_cap=total_cap)
    workers, attempts = 8, 4
    barrier = CTX.Barrier(workers)
    out = CTX.Queue()
    _run_all(
        _episode,
        [(cfg, f"episode-{w}", attempts, barrier, out) for w in range(workers)],
    )
    results = [out.get(timeout=10) for _ in range(workers)]
    ledger = json.loads(cfg.ledger_path.read_text())
    ok = sum(r[1].count("ok") for r in results)
    # The cumulative cap held: never more spent than allowed, every call accounted for.
    assert ledger["total_cost_usd"] <= total_cap
    assert math.isclose(ledger["total_cost_usd"], ok * COST)
    assert ok <= 6 and any("cumulative" in r[1] for r in results)
    assert len(ledger["calls"]) == workers * attempts  # refusals are recorded, at cost 0
    assert "reservations" not in ledger  # nothing left in flight
    # The per-run cap held in every process.
    for run_id, outcomes, spent in results:
        assert outcomes.count("ok") <= 2 and spent <= run_cap, run_id
        charged = [
            c["cost_usd"] for c in ledger["calls"] if c["run_id"] == run_id and c["outcome"] == "ok"
        ]
        assert math.isclose(sum(charged), spent), run_id


def _reserve_and_die(path: str, out: Any) -> None:
    ledger = SpendLedger(Path(path))
    guard = SpendGuard(ledger, max_run_usd=1.0, max_total_usd=1.0, run_id="crashed")
    out.put(guard.reserve(0.25, call_id="mc_0001"))
    out.close()
    out.join_thread()
    os._exit(0)  # dies before charging the call


def test_a_reservation_of_a_dead_process_is_charged_at_its_bound(tmp_path: Path) -> None:
    path = tmp_path / "var" / "model_spend.json"
    out = CTX.Queue()
    proc = CTX.Process(target=_reserve_and_die, args=(str(path), out))
    proc.start()
    proc.join(30)
    assert out.get(timeout=5) is None  # the reservation was granted
    assert json.loads(path.read_text())["reservations"][0]["amount_usd"] == 0.25
    ledger = SpendLedger(path)
    guard = SpendGuard(ledger, max_run_usd=1.0, max_total_usd=1.0, run_id="next")
    assert guard.reserve(0.80, call_id="mc_0001") is not None  # 0.25 + 0.80 > 1.0
    data = json.loads(path.read_text())
    abandoned = [c for c in data["calls"] if c["outcome"] == "abandoned"]
    assert [(c["run_id"], c["cost_usd"]) for c in abandoned] == [("crashed", 0.25)]
    assert data["total_cost_usd"] == 0.25 and "reservations" not in data
    assert guard.reserve(0.70, call_id="mc_0002") is None


def test_a_live_reservation_counts_against_the_cumulative_cap(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "model_spend.json")
    first = SpendGuard(ledger, max_run_usd=1.0, max_total_usd=1.0, run_id="a")
    second = SpendGuard(ledger, max_run_usd=1.0, max_total_usd=1.0, run_id="b")
    assert first.reserve(0.6, call_id="mc_0001") is None
    refusal = second.reserve(0.6, call_id="mc_0001")
    assert refusal is not None and "reserved by calls in flight" in refusal
    first.release()
    assert second.reserve(0.6, call_id="mc_0001") is None


@pytest.mark.parametrize("missing", [True, False])
def test_a_call_never_sent_releases_its_reservation(tmp_path: Path, missing: bool) -> None:
    cfg = make_config(tmp_path)
    if missing:
        cfg.key_file.unlink()  # a configuration failure: nothing is sent
    provider = make_provider(cfg, FakeOpener(lambda body: {"word": "hi"}))
    with contextlib.suppress(ProviderConfigError):  # the configuration failure is the point
        provider.complete(echo_request())
    data = json.loads(cfg.ledger_path.read_text()) if cfg.ledger_path.exists() else {}
    assert "reservations" not in data
