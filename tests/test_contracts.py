"""Task 3 acceptance tests: contracts round-trip, ShockSpec is immutable, hidden state is
unreachable, and the fakes are usable by every branch.

Guards collie-platform R2 and R3.
"""

from __future__ import annotations

import ast
import json
import math
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from collie.contracts import (
    AlertKind,
    AlertMessage,
    Controller,
    Decision,
    Direction,
    DurationBin,
    HiddenAlertSpec,
    HiddenIncident,
    HiddenStateLeak,
    LifecycleState,
    MagnitudeBin,
    ObservationMode,
    PeriodObservation,
    Persistence,
    ShockFamily,
    ShockSpec,
    SupplyRealization,
    TargetStream,
    assert_no_hidden_state,
    find_hidden_state,
)
from collie.fakes import (
    ConstantController,
    FakeGenerator,
    FakeLLM,
    FakeVerifier,
    NullController,
    canned,
    fixture_episode,
    fixture_episodes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_spec(**overrides: object) -> ShockSpec:
    payload: dict[str, object] = {
        "target_stream": TargetStream.ARRIVAL,
        "shock_family": ShockFamily.TRANSIT_PAUSE,
        "direction": Direction.ARRIVAL_INTERRUPTED,
        "onset_window": (-1, 1),
        "magnitude_bin": MagnitudeBin.MEDIUM,
        "persistence": Persistence.TRANSIENT,
        "duration_bin": DurationBin.MEDIUM,
        "evidence_refs": ("alert_17", "obs_t17"),
        "prospective_signature": "sig_arrival_stall",
        "tau_j": 17,
        "proposal_index": 1,
        "model_id": "fake-open-weight-7b",
        "decoding_hash": "det-v1",
        "prompt_hash": "p-abc",
    }
    payload.update(overrides)
    return ShockSpec(**payload)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# R2.1 / R2.2 — round-trip and immutability
# ---------------------------------------------------------------------------


def test_shockspec_round_trips_through_json() -> None:
    spec = make_spec()
    again = ShockSpec.model_validate(json.loads(spec.model_dump_json()))
    assert again == spec


def test_shockspec_is_immutable_after_construction() -> None:
    """The hypothesis is frozen at tau_j; evidence that later tests it must not edit it."""
    spec = make_spec()
    with pytest.raises(ValidationError):
        spec.magnitude_bin = MagnitudeBin.HIGH  # type: ignore[misc]


def test_frozen_dataclasses_reject_assignment() -> None:
    obs = PeriodObservation(
        period=1,
        date="2019/2/11",
        on_hand=0.0,
        in_transit_total=0.0,
        prev_order=0.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=0.0,
    )
    with pytest.raises(FrozenInstanceError):
        obs.on_hand = 5.0  # type: ignore[misc]


def test_unknown_fields_are_rejected_not_ignored() -> None:
    """A model must not be able to add a field the schema does not define."""
    with pytest.raises(ValidationError):
        make_spec(confidence=0.9)


def test_a_smuggled_threshold_is_rejected() -> None:
    """The model may never choose its own test; that is what makes the selection admissible."""
    with pytest.raises(ValidationError):
        ShockSpec.model_validate(
            json.loads(canned.SMUGGLED_THRESHOLD)
            | {
                "tau_j": 5,
                "proposal_index": 1,
                "model_id": "m",
                "decoding_hash": "d",
                "prompt_hash": "p",
            }
        )


def test_unknown_enum_member_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_spec(shock_family="port_strike")


# ---------------------------------------------------------------------------
# abstention semantics
# ---------------------------------------------------------------------------


def test_abstention_is_a_first_class_complete_response() -> None:
    spec = make_spec(
        shock_family=ShockFamily.NO_CHANGE,
        target_stream=TargetStream.NONE,
        direction=Direction.NONE,
        onset_window=None,
        magnitude_bin=None,
        duration_bin=DurationBin.NONE,
        persistence=Persistence.UNKNOWN,
        evidence_refs=(),
    )
    assert spec.is_abstention


def test_the_string_none_is_normalised_for_an_abstention() -> None:
    """A model writing "none" instead of null is cooperative; normalise rather than reject."""
    spec = ShockSpec.model_validate(
        json.loads(canned.ABSTENTION_NONE_SPELLING)
        | {
            "tau_j": 5,
            "proposal_index": 1,
            "model_id": "m",
            "decoding_hash": "d",
            "prompt_hash": "p",
        }
    )
    assert spec.is_abstention
    assert spec.magnitude_bin is None, "post-validation invariant: abstention magnitude is null"


def test_incoherent_abstention_is_rejected() -> None:
    """no_change with an onset is not a coherent commitment."""
    with pytest.raises(ValidationError):
        make_spec(shock_family=ShockFamily.NO_CHANGE, onset_window=(-1, 1))


def test_non_abstention_requires_onset_and_magnitude() -> None:
    with pytest.raises(ValidationError):
        make_spec(onset_window=None)
    with pytest.raises(ValidationError):
        make_spec(magnitude_bin=MagnitudeBin.NONE)


def test_proposal_index_is_one_based_for_alpha_allocation() -> None:
    """alpha_j = alpha * 2**-j needs j >= 1 so that the geometric series sums to 1."""
    with pytest.raises(ValidationError):
        make_spec(proposal_index=0)


def test_onset_window_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        make_spec(onset_window=(2, -2))


# ---------------------------------------------------------------------------
# R2.3-R2.5 — hidden-state isolation, mechanism 1 (runtime object-graph walk)
# ---------------------------------------------------------------------------


def test_observation_carries_no_hidden_state() -> None:
    ep = fixture_episode(ShockFamily.TRANSIT_PAUSE)
    obs = PeriodObservation(
        period=11,
        date="p11",
        on_hand=50.0,
        in_transit_total=100.0,
        prev_order=100.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=120.0,
        alert=ep.alert,
    )
    assert find_hidden_state(obs) == []
    assert_no_hidden_state(obs, context="PeriodObservation")


def test_the_walk_actually_finds_a_leak() -> None:
    """A test that only ever passes is worthless; prove the detector fires."""
    ep = fixture_episode(ShockFamily.COMPOUND)

    class LeakyObs:
        def __init__(self) -> None:
            self.period = 3
            self.truth = ep.incident  # the leak

    leaks = find_hidden_state(LeakyObs())
    assert leaks == ["obj.truth"]
    with pytest.raises(HiddenStateLeak, match="hidden ground truth reachable"):
        assert_no_hidden_state(LeakyObs(), context="LeakyObs")


@pytest.mark.parametrize(
    "wrapper",
    [
        lambda inc: {"payload": inc},
        lambda inc: [inc],
        lambda inc: (0, {"deep": [{"deeper": inc}]}),
    ],
    ids=["dict", "list", "nested"],
)
def test_the_walk_is_structural_not_name_based(wrapper) -> None:
    """Leaks through containers and undeclared attributes are caught the same way."""
    inc = fixture_episode(ShockFamily.DEMAND_LEVEL).incident
    assert find_hidden_state(wrapper(inc)), "container-nested hidden state must be found"


def test_supply_realization_and_alert_spec_are_treated_as_hidden() -> None:
    """supply.csv content and the canonical AlertSpec are as sensitive as the incident."""
    assert find_hidden_state(SupplyRealization(lead_times=(1.0, math.inf)))
    assert find_hidden_state(
        HiddenAlertSpec(
            family=ShockFamily.DEMAND_LEVEL,
            target_stream=TargetStream.DEMAND,
            direction=Direction.DEMAND_UP,
            onset_window=(-1, 1),
            magnitude_bin=MagnitudeBin.HIGH,
            persistence=Persistence.PERSISTENT,
            duration_bin=DurationBin.LONGER,
            prospective_signature="sig_demand_level_up",
            kind=AlertKind.ACCURATE,
        )
    )


def test_the_walk_terminates_on_cycles() -> None:
    node: dict[str, object] = {}
    node["self"] = node
    assert find_hidden_state(node) == []


# ---------------------------------------------------------------------------
# R2.3-R2.5 — hidden-state isolation, mechanism 2 (static reachability)
# ---------------------------------------------------------------------------

HIDDEN_SYMBOLS = {"HiddenIncident", "HiddenAlertSpec", "SupplyRealization"}
# Defining, generating, simulating, and evaluating hidden state is legitimate.
# Deciding, triggering, verifying, and prompting on it is not.
ALLOWED_PREFIXES = (
    "collie/contracts.py",
    "collie/fakes/",
    "collie/sim/",
    "collie/data/",
    "collie/eval/",
    "collie/arms/oracle.py",
    "collie/arms/controls.py",
)
FORBIDDEN_DIRS = (
    "collie/verify/",
    "collie/trigger/",
    "collie/control/",
    "collie/spec/",
    "collie/llm/",
)


def test_hidden_state_is_statically_unreachable_from_decision_making_code() -> None:
    """Mechanism 2: no verifier, trigger, compiler, schema, or transport module may even name
    hidden state. Guards collie-or-compiler R3.4 and collie-verifier R2.5 in advance."""
    offenders: list[str] = []
    for py in (REPO_ROOT / "collie").rglob("*.py"):
        rel = py.relative_to(REPO_ROOT).as_posix()
        if not rel.startswith(FORBIDDEN_DIRS):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in HIDDEN_SYMBOLS:
                offenders.append(f"{rel}:{node.lineno} references {node.id}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in HIDDEN_SYMBOLS:
                        offenders.append(f"{rel}:{node.lineno} imports {alias.name}")
    assert not offenders, (
        "hidden ground truth must be unreachable from decision-making code:\n  "
        + "\n  ".join(offenders)
    )


def test_the_allowlist_is_not_vacuous() -> None:
    """If nothing legitimately touches hidden state, mechanism 2 proves nothing."""
    touching = [
        py.relative_to(REPO_ROOT).as_posix()
        for py in (REPO_ROOT / "collie").rglob("*.py")
        if any(sym in py.read_text(encoding="utf-8") for sym in HIDDEN_SYMBOLS)
    ]
    assert touching, "expected some modules to reference hidden state"
    assert all(t.startswith(ALLOWED_PREFIXES) for t in touching), (
        f"unexpected module touching hidden state: {touching}"
    )


# ---------------------------------------------------------------------------
# R3 — the fakes
# ---------------------------------------------------------------------------


def test_null_controller_satisfies_the_controller_protocol() -> None:
    assert isinstance(NullController(), Controller)
    assert isinstance(ConstantController(), Controller)


def test_null_controller_completes_a_five_period_fixture_episode() -> None:
    """Task 3 demo: an episode runs end to end through fakes only, before any runner exists."""
    ep = fixture_episode(ShockFamily.DEMAND_LEVEL, horizon=5, onset=3)
    ctl = NullController()
    ctl.reset()
    decisions: list[Decision] = []
    on_hand = 0.0
    for t in range(1, ep.spec.horizon + 1):
        obs = PeriodObservation(
            period=t,
            date=f"p{t}",
            on_hand=on_hand,
            in_transit_total=0.0,
            prev_order=0.0,
            prev_arrivals=0.0,
            profit_per_unit=ep.spec.profit_per_unit,
            holding_cost_per_unit=ep.spec.holding_cost_per_unit,
            promised_lead_time=ep.spec.promised_lead_time,
            prev_demand=ep.demand[t - 2] if t > 1 else 0.0,
        )
        assert_no_hidden_state(obs, context=f"period {t}")
        decisions.append(ctl.order(obs))
    assert len(decisions) == 5
    assert all(d.order_quantity == 0.0 for d in decisions)
    assert len(ctl.seen) == 5


def test_fake_llm_scripts_a_repair_then_succeed_sequence() -> None:
    llm = FakeLLM.repair_then_succeed()
    first = llm.complete("prompt-1", decoding_hash="det-v1")
    second = llm.complete("prompt-1-repair", decoding_hash="det-v1")
    assert first == canned.MALFORMED_JSON
    assert json.loads(second)["shock_family"] == "transit_pause"
    assert llm.n_calls == 2, "both attempts must be countable for the ledger"
    assert llm.prompts == ["prompt-1", "prompt-1-repair"]


def test_fake_llm_exposes_the_invalid_corpus_for_fuzzing() -> None:
    assert len(canned.INVALID_CORPUS) >= 8
    assert canned.EMPTY in canned.INVALID_CORPUS


def test_fake_verifier_activates_on_schedule_and_reports_delay() -> None:
    v = FakeVerifier(activate_after=2)
    v.register(make_spec(tau_j=10))
    assert v.observe(11, 130.0) is LifecycleState.PROPOSED
    assert v.observe(12, 128.0) is LifecycleState.ACTIVE
    assert v.is_active
    assert v.activation_delay == 2


def test_fake_verifier_refuses_evidence_at_or_before_tau_j() -> None:
    """The future-only boundary is the property under test, so even the fake enforces it."""
    v = FakeVerifier(activate_after=1)
    v.register(make_spec(tau_j=10))
    with pytest.raises(ValueError, match="future-only violation"):
        v.observe(10, 100.0)


def test_fake_verifier_immediate_mode_reproduces_arm_8() -> None:
    v = FakeVerifier(activate_after=0)
    v.register(make_spec(tau_j=4))
    assert v.observe(5, 1.0) is LifecycleState.ACTIVE


def test_fake_verifier_can_expire_and_refute() -> None:
    v = FakeVerifier(activate_after=1, max_lifetime=2)
    v.register(make_spec(tau_j=1))
    v.observe(2, 1.0)
    v.observe(3, 1.0)
    assert v.observe(4, 1.0) is LifecycleState.EXPIRED

    w = FakeVerifier(activate_after=1, refute_at=1)
    w.register(make_spec(tau_j=1))
    w.observe(2, 1.0)
    assert w.observe(3, 1.0) is LifecycleState.REFUTED


def test_fake_generator_produces_one_episode_per_family() -> None:
    eps = fixture_episodes()
    assert len(eps) == 6, "six controlled families, excluding the no_change abstention case"
    assert {e.incident.family for e in eps} == set(ShockFamily) - {ShockFamily.NO_CHANGE}


def test_fixture_episodes_are_deterministic_by_seed() -> None:
    a = fixture_episode(ShockFamily.COMPOUND, seed=3)
    b = fixture_episode(ShockFamily.COMPOUND, seed=3)
    c = fixture_episode(ShockFamily.COMPOUND, seed=4)
    assert a.demand == b.demand and a.supply == b.supply
    assert a.demand != c.demand


def test_shocked_episode_matches_its_twin_strictly_before_onset() -> None:
    """The paired-twin property that makes a shock comparison meaningful."""
    for ep in fixture_episodes():
        onset = ep.incident.onset_period
        assert ep.demand[:onset] == ep.baseline_demand[:onset], ep.incident.family


def test_only_the_compound_family_is_conditionally_dependent() -> None:
    """Branch F reads this flag to choose a joint likelihood vs explicit alpha splitting."""
    flags = {e.incident.family: e.incident.conditional_independence for e in fixture_episodes()}
    assert flags[ShockFamily.COMPOUND] is False
    assert all(v for f, v in flags.items() if f is not ShockFamily.COMPOUND)


def test_supply_families_write_the_expected_supply_realization() -> None:
    loss = fixture_episode(ShockFamily.SHIPMENT_LOSS)
    assert loss.supply.n_lost == 2, "lead_time=inf encodes a lost shipment"

    pause = fixture_episode(ShockFamily.TRANSIT_PAUSE)
    assert sum(pause.supply.pause_active) == 4
    assert pause.supply.n_lost == 0, "a pause freezes cohorts; it does not lose them"

    shift = fixture_episode(ShockFamily.LEAD_TIME_SHIFT)
    assert set(shift.supply.lead_times[shift.incident.onset_period :]) == {4.0}


def test_fixture_hidden_truth_is_not_attached_to_the_observable_episode() -> None:
    """The fixture returns truth alongside the episode, never inside it, so a test that leaks
    hidden state into a controller fails the walk instead of quietly passing."""
    ep = fixture_episode(ShockFamily.TRANSIT_PAUSE)
    assert find_hidden_state(ep.spec) == []
    assert find_hidden_state(ep.alert) == []
    assert find_hidden_state(ep.incident), "the incident itself is of course hidden state"


def test_fake_generator_wrapper_is_stable() -> None:
    g = FakeGenerator(seed=1)
    assert len(g.episodes()) == 6
    assert g.episode(ShockFamily.DEMAND_LEVEL).incident.family is ShockFamily.DEMAND_LEVEL


def test_censored_mode_can_be_requested_on_a_fixture() -> None:
    ep = fixture_episode(ShockFamily.DEMAND_LEVEL, observation_mode=ObservationMode.CENSORED)
    assert ep.spec.observation_mode is ObservationMode.CENSORED


def test_observation_requires_a_demand_or_sales_signal_after_period_one() -> None:
    with pytest.raises(ValueError, match="prev_demand"):
        PeriodObservation(
            period=4,
            date="p4",
            on_hand=1.0,
            in_transit_total=0.0,
            prev_order=0.0,
            prev_arrivals=0.0,
            profit_per_unit=4.0,
            holding_cost_per_unit=1.0,
            promised_lead_time=2,
        )


def test_alert_message_does_not_carry_template_identity() -> None:
    """template_id is analysis-side (RunRecord), so a policy cannot key on it."""
    assert not hasattr(AlertMessage(alert_id="a", period=1, text="t"), "template_id")


def test_hidden_incident_is_frozen() -> None:
    inc = HiddenIncident(
        family=ShockFamily.DEMAND_LEVEL,
        onset_period=10,
        magnitude=1.5,
        duration=5,
        conditional_independence=True,
    )
    with pytest.raises(FrozenInstanceError):
        inc.magnitude = 2.0  # type: ignore[misc]
