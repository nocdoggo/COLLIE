"""Injection wiring for the arm-ladder tests (module brief §3).

Every arm depends on protocols and receives its collaborators here: the metered channel stack
(transport, cache, ledger) from ``collie.llm``, module 04's real implementation
(``collie.control.mapping.GridCompiler`` and ``collie.control.controller.OrCompilerController``,
wired here — arms never import them), and arm 4's fallback (arm 1's controller). No fixture
touches a live endpoint; live calls are the ``needs_llm`` tests in ``tests/test_llm_client.py``.

Module 05 adds ``--replications`` below: the Monte Carlo replication count for its
calibration tests (CP2 default 2,000 per registered null).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest

from collie.arms.base_stock import CappedBaseStockController
from collie.contracts import ControlConfig
from collie.control.controller import OrCompilerController
from collie.control.grid import baseline_config_for
from collie.control.mapping import GridCompiler
from collie.llm import CallLedger, DiskCache, MeteredClient
from collie.llm.demo import ScriptedTransport, scripted_endpoint


@dataclass(slots=True)
class Harness:
    """One metered stack: scripted transport, disk cache, ledger, and the channel factory."""

    ledger: CallLedger = field(default_factory=CallLedger)
    transport: ScriptedTransport = field(default_factory=ScriptedTransport)
    cache: DiskCache | None = None
    metered: MeteredClient | None = None

    def channel(self, *, arm_id: str, episode_id: str):
        assert self.metered is not None
        return self.metered.channel(arm_id=arm_id, episode_id=episode_id)


@pytest.fixture
def harness(tmp_path) -> Harness:
    """A fresh metered stack per test, cache on a tmp disk so runs are isolated."""
    h = Harness()
    h.cache = DiskCache(tmp_path / "cache")
    h.metered = MeteredClient(
        transport=h.transport,
        endpoint=scripted_endpoint(),
        cache=h.cache,
        ledger=h.ledger,
    )
    return h


@pytest.fixture
def compiler() -> GridCompiler:
    """The injected SpecCompiler: module 04's real grid mapping."""
    return GridCompiler()


@pytest.fixture
def reference_controller() -> OrCompilerController:
    """The injected shared controller at the baseline (arm-1-equivalent) descriptor."""
    return OrCompilerController(order_cap=math.inf, config=baseline_config_for(2))


def make_fallback(**kwargs) -> CappedBaseStockController:
    """Arm 4's fallback: a fresh arm-1 controller (its own demand history per episode)."""
    return CappedBaseStockController(**kwargs)


def make_control_config(**overrides) -> ControlConfig:
    base = dict(m=1.0, l_eff=2, gamma=1.0, predictive_model="running")
    base.update(overrides)
    return ControlConfig(**base)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--replications",
        action="store",
        default=2000,
        type=int,
        help="Monte Carlo replication count (CP2 default: 2,000 per registered null)",
    )
