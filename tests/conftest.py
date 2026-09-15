"""Injection wiring for the arm-ladder tests (module brief §3).

Every arm depends on protocols and receives its collaborators here: the metered channel stack
(transport, cache, ledger) from ``collie.llm``, the temporary compiler/controller stand-in from
``collie/arms/reference_control.py`` (deleted when module 04 lands — arms never import it), and
arm 4's fallback (arm 1's controller). No fixture touches a live endpoint; live calls are the
``needs_llm`` tests in ``tests/test_llm_client.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from collie.arms.base_stock import CappedBaseStockController
from collie.arms.reference_control import (
    ReferenceCompiler,
    ReferenceController,
    baseline_config,
)
from collie.contracts import ControlConfig
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
def compiler() -> ReferenceCompiler:
    """The injected SpecCompiler stand-in (module 04's real one drops in unchanged)."""
    return ReferenceCompiler()


@pytest.fixture
def reference_controller() -> ReferenceController:
    """The injected Controller stand-in at the baseline (arm-1-equivalent) config."""
    return ReferenceController(config=baseline_config(promised_lead_time=2))


def make_fallback(**kwargs) -> CappedBaseStockController:
    """Arm 4's fallback: a fresh arm-1 controller (its own demand history per episode)."""
    return CappedBaseStockController(**kwargs)


def make_control_config(**overrides) -> ControlConfig:
    base = dict(m=1.0, l_eff=2, gamma=1.0, predictive_model="running")
    base.update(overrides)
    return ControlConfig(**base)
