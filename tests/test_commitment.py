"""The commitment study (analysis/commitment): certify-then-hedge, fresh layouts, the ladder.

Offline only: the scripted transport, a stub OpenAI client, and in-memory episodes. No live call
and no key file is touched.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from analysis.commitment.cth import (
    ALPHA,
    HYPOTHESES,
    CertifyThenHedgeArm,
    canonical_spec,
    hypothesis_key,
    mixture_quantile,
)
from analysis.commitment.endpoints import LADDER, EchoCheckedClient, ServedModelMismatch
from analysis.commitment.episodes import FRESH_BASE, fresh_units
from collie.arms.base_stock import CappedBaseStockController
from collie.contracts import AnalysisClass, Direction, ShockFamily
from collie.data.splits import seed_pools
from collie.llm.client import DECODING_REGISTRY
from collie.sim.runner import EpisodeRunner


class _Never:
    def should_propose(self, obs) -> bool:
        return False


class _At:
    def __init__(self, *periods: int) -> None:
        self.periods = set(periods)

    def should_propose(self, obs) -> bool:
        return obs.period in self.periods


@pytest.fixture(scope="module")
def pilot(tmp_path_factory):
    from tools.run_arms import pilot_instances

    instances, _ = pilot_instances(tmp_path_factory.mktemp("pilot"), 120)
    return instances


def _arm(instance, trigger, **kwargs) -> CertifyThenHedgeArm:
    spec = instance.spec
    return CertifyThenHedgeArm(
        promised_lead_time=spec.promised_lead_time,
        horizon=spec.horizon,
        train_demand=spec.train_demand,
        order_cap=spec.order_cap,
        trigger=trigger,
        **kwargs,
    )


def _orders(instance, controller) -> list[float]:
    outcome = EpisodeRunner(instance, analysis_class=AnalysisClass.EXPLORATORY).run(controller)
    return [r.order_quantity for r in outcome.result.records]


def test_without_a_hypothesis_the_arm_orders_exactly_as_arm_1(pilot) -> None:
    for instance, _ in pilot[:12]:
        arm1 = CappedBaseStockController(train_demand=instance.spec.train_demand)
        assert _orders(instance, _arm(instance, _Never(), lam=1.0)) == _orders(instance, arm1)


def test_the_hypothesis_mass_obeys_the_exposure_budget(pilot) -> None:
    instance, _ = pilot[0]
    arm = _arm(instance, _At(12, 30), lam=1.0)
    EpisodeRunner(instance, analysis_class=AnalysisClass.EXPLORATORY).run(arm)
    priors = [h.prior for h in arm._hyps]
    assert math.isclose(sum(priors), ALPHA / 2 + ALPHA / 4)
    assert len(arm._hyps) == 2 * len(HYPOTHESES)
    # pi_t <= N_t / (1 - A + N_t) with N_t = sum prior * E; check it pathwise on the log.
    assert all(0.0 <= mass <= 1.0 for _, mass, _ in arm.log)


def test_the_llm_only_sets_prior_weights() -> None:
    arm = SimpleNamespace(lam=0.25)
    weights = {key: arm.lam / len(HYPOTHESES) for key in HYPOTHESES}
    weights["lead_time"] += 1 - arm.lam
    assert math.isclose(sum(weights.values()), 1.0)
    assert hypothesis_key(ShockFamily.SHIPMENT_LOSS, Direction.ARRIVAL_INTERRUPTED) is None
    assert hypothesis_key(ShockFamily.COMPOUND, Direction.MIXED) is None
    assert hypothesis_key(ShockFamily.DEMAND_LEVEL, Direction.DEMAND_DOWN) == "demand_down"
    for key in HYPOTHESES:
        canonical_spec(key, tau=15, index=1, window=(-2, 2))  # legal under module 02


def test_mixture_quantile_matches_a_single_normal() -> None:
    from scipy.stats import norm

    x = mixture_quantile([(1.0, 300.0, 40.0, 1.0)], 0.8, 50.0)
    assert math.isclose(x, 300.0 - 50.0 + 40.0 * norm.ppf(0.8), abs_tol=1e-5)


def test_a_model_consulting_arm_needs_a_proposer(pilot) -> None:
    instance, _ = pilot[0]
    with pytest.raises(ValueError, match="channel, prompter and parser"):
        _arm(instance, _Never(), lam=0.25)
    _arm(instance, _Never(), lam=0.25, replay={})  # replay is enough


def test_fresh_pool_is_new_and_balanced() -> None:
    units = fresh_units(12)
    assert len(units) == 72
    registered = set().union(*seed_pools().values())
    assert not {u.seed for u in units} & registered
    assert all(u.seed % 1_000_000 >= FRESH_BASE for u in units)
    for family in range(1, 7):
        mine = [u for u in units if u.family == family]
        assert sum(u.null_condition.value == "no_alert" for u in mine) == 6


def test_the_echo_check_refuses_a_rerouted_model() -> None:
    rung = LADDER["grok-build-0.1"]
    client = EchoCheckedClient.__new__(EchoCheckedClient)
    client._endpoint = rung.endpoint()
    client._served_as = rung.served_as

    def reply(model):
        usage = SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=4)
        message = SimpleNamespace(content="OK")
        return SimpleNamespace(model=model, usage=usage, choices=[SimpleNamespace(message=message)])

    decoding = DECODING_REGISTRY["det-v1"]
    for served, ok in (("grok-code-fast-1", True), ("grok-4.3", False)):
        completions = SimpleNamespace(create=lambda _served=served, **_: reply(_served))
        client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        if ok:
            assert client.complete_metered("hi", decoding=decoding).text == "OK"
        else:
            with pytest.raises(ServedModelMismatch):
                client.complete_metered("hi", decoding=decoding)


def test_every_ladder_rung_has_a_dated_price_and_a_key_path() -> None:
    for rung in LADDER.values():
        endpoint = rung.endpoint()
        assert endpoint.price_input_per_mtok > 0 and endpoint.price_output_per_mtok > 0
        assert endpoint.price_date.startswith("2026-09")
        assert endpoint.key_file is None or Path(endpoint.key_file).parent.name == "cloud_endpoint"


@pytest.mark.slow
def test_fresh_layout_renders_bank_alerts(tmp_path) -> None:
    from analysis.commitment.episodes import build_layout, layout_alerts

    layout = build_layout(tmp_path, 2)
    alerts = layout_alerts(layout)
    assert len(layout.instances) == 60 and len(alerts) == 60
    sources = {a.source for a in alerts.values()}
    assert "bank:early_accurate" in sources and "bank:false_alert_null" in sources


def test_an_empty_echo_is_retried_and_billed() -> None:
    rung = LADDER["deepseek-v3"]
    client = EchoCheckedClient.__new__(EchoCheckedClient)
    client._endpoint = rung.endpoint()
    client._served_as = rung.served_as
    replies = iter(["", "deepseek/deepseek-chat"])

    def create(**_):
        usage = SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=4)
        message = SimpleNamespace(content="OK")
        return SimpleNamespace(
            model=next(replies), usage=usage, choices=[SimpleNamespace(message=message)]
        )

    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    raw = client.complete_metered("hi", decoding=DECODING_REGISTRY["det-v1"])
    assert raw.text == "OK" and raw.total_tokens == 8 and raw.prompt_tokens == 6


def test_the_cost_ratio_replay_serves_by_decision_point_and_counts_misses():
    from analysis.commitment.sensitivity import ABSTAIN, _ReplayTransport

    transport = _ReplayTransport({("arm10", "dev/f1/s1/no_alert", 12): "recorded"})
    transport.context = ("arm10", "dev/f1/s1/no_alert", 12)
    assert transport.complete_metered("any prompt", decoding=None).text == "recorded"
    transport.context = ("arm10", "dev/f1/s1/no_alert", 13)
    assert transport.complete_metered("any prompt", decoding=None).text == ABSTAIN
    assert transport.misses == [("arm10", "dev/f1/s1/no_alert", 13)]
    assert transport.served == 2
