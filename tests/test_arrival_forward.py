"""Forward-recursion semantics and arrival e-process integration."""

from __future__ import annotations

import ast
import math
import random
from pathlib import Path

import pytest

from collie.contracts import (
    AnalysisClass,
    Direction,
    DurationBin,
    MagnitudeBin,
    ObservationMode,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
    assert_no_hidden_state,
)
from collie.verify.arrival import (
    ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY,
    LOST,
    ArrivalEProcess,
    ArrivalForwardFilter,
    ArrivalModel,
    ArrivalState,
    RegisteredArrivalLaw,
    _sample_path,
    advance_counter,
    family_validity_flags,
    transition_state,
)
from collie.verify.eprocess import EMPIRICAL_ONLY

REPO_ROOT = Path(__file__).resolve().parents[1]


def _arrival_spec(family: ShockFamily = ShockFamily.SHIPMENT_LOSS) -> ShockSpec:
    direction = (
        Direction.ARRIVAL_DELAYED
        if family is ShockFamily.LEAD_TIME_SHIFT
        else Direction.ARRIVAL_INTERRUPTED
    )
    signature = {
        ShockFamily.LEAD_TIME_SHIFT: "sig_arrival_delay",
        ShockFamily.SHIPMENT_LOSS: "sig_arrival_loss",
        ShockFamily.TRANSIT_PAUSE: "sig_arrival_stall",
    }[family]
    duration = DurationBin.SHORT if family is ShockFamily.SHIPMENT_LOSS else DurationBin.MEDIUM
    persistence = (
        Persistence.PERSISTENT if family is ShockFamily.LEAD_TIME_SHIFT else Persistence.TRANSIENT
    )
    return ShockSpec(
        target_stream=TargetStream.ARRIVAL,
        shock_family=family,
        direction=direction,
        onset_window=(0, 2),
        magnitude_bin=MagnitudeBin.MEDIUM,
        persistence=persistence,
        duration_bin=duration,
        evidence_refs=("obs_t2",),
        prospective_signature=signature,
        tau_j=2,
        proposal_index=1,
        model_id="test",
        decoding_hash="frozen",
        prompt_hash="frozen",
    )


def test_pause_freezes_the_state_counters() -> None:
    state = ArrivalState((0.0, 5.0, 7.0))
    receipt, frozen = transition_state(state, dispatch_quantity=3.0, delay=2, paused=True)
    assert receipt == 0.0
    assert frozen.by_remaining == (0.0, 5.0, 10.0)

    complete = ArrivalState((4.0, 5.0, 0.0))
    receipt, frozen = transition_state(complete, dispatch_quantity=0.0, delay=LOST, paused=True)
    assert receipt == 4.0
    assert frozen.by_remaining == (0.0, 5.0, 0.0)


def test_loss_is_absorbing() -> None:
    assert advance_counter(LOST, paused=False) is LOST
    assert advance_counter(LOST, paused=True) is LOST
    state = ArrivalState.empty(2)
    for paused in (False, True):
        receipt, following = transition_state(
            state, dispatch_quantity=11.0, delay=LOST, paused=paused
        )
        assert receipt == 0.0
        assert following == state


def test_zero_delay_dispatch_is_in_the_same_aggregate_receipt() -> None:
    state = ArrivalState((4.0, 5.0, 0.0))
    receipt, following = transition_state(state, dispatch_quantity=3.0, delay=0, paused=False)
    assert receipt == 7.0
    assert following.by_remaining == (5.0, 0.0, 0.0)


def test_forward_step_sums_indistinguishable_assignments() -> None:
    law = RegisteredArrivalLaw((0.25, 0.50), 0.25, name="short")
    forward = ArrivalForwardFilter(ArrivalModel(law))
    assert forward.step(period=1, dispatch_quantity=4.0, receipt=0.0) == pytest.approx(0.75)
    # Receipt zero is compatible with delay one and with permanent loss.  The posterior retains
    # both possibilities rather than selecting a dispatch identity.
    assert len(forward.distribution) == 2


def test_unchanged_model_rejects_active_regime_metadata() -> None:
    with pytest.raises(ValueError, match="unchanged arrival model"):
        ArrivalModel(active_from=3)


def test_arrival_eprocess_is_future_only_and_uses_exact_conditionals() -> None:
    prehistory = ((5.0, 0.0), (5.0, 0.0))
    verifier = ArrivalEProcess.from_spec(
        _arrival_spec(), alpha_episode=0.05, preproposal_history=prehistory
    )
    with pytest.raises(ValueError, match="strictly after tau_j"):
        verifier.observe(2, 5.0, 0.0)
    point = verifier.observe(3, 5.0, 5.0)
    assert point.period == 3
    assert point.validity_label == ANYTIME_VALID_COLLIE_SHOCKSPEC_ONLY
    assert math.isfinite(point.e_value)
    assert_no_hidden_state(verifier, context="arrival verifier")


def test_arrival_eprocess_requires_complete_preproposal_pipeline_history() -> None:
    with pytest.raises(ValueError, match="every period through tau_j"):
        ArrivalEProcess.from_spec(
            _arrival_spec(), alpha_episode=0.05, preproposal_history=((5.0, 0.0),)
        )


def test_official_arrival_output_is_empirical_only() -> None:
    verifier = ArrivalEProcess.from_spec(
        _arrival_spec(),
        alpha_episode=0.05,
        preproposal_history=((5.0, 0.0), (5.0, 0.0)),
        source="official",
    )
    assert verifier.validity_label == EMPIRICAL_ONLY
    with pytest.raises(ValueError, match="empirical_only"):
        ArrivalEProcess.from_spec(
            _arrival_spec(),
            alpha_episode=0.05,
            preproposal_history=((5.0, 0.0), (5.0, 0.0)),
            source="official",
            analysis_class=AnalysisClass.CONFIRMATORY,
        )


def test_anytime_label_requires_a_registered_alternative_grid() -> None:
    custom_alternative = RegisteredArrivalLaw(
        (0.01, 0.15, 0.30, 0.30, 0.04),
        0.20,
        pause_probability=0.01,
        name="unregistered_loss_alternative",
    )
    verifier = ArrivalEProcess(
        null=ArrivalModel(),
        alternatives=(
            ArrivalModel(
                changed=custom_alternative,
                active_from=3,
                active_duration=1,
            ),
        ),
        tau_j=2,
        alpha_j=0.025,
        preproposal_history=((1.0, 0.0), (1.0, 0.0)),
        family=ShockFamily.SHIPMENT_LOSS,
    )
    assert verifier.validity_label == EMPIRICAL_ONLY


def test_anytime_label_requires_the_exact_registered_collie_null() -> None:
    custom = RegisteredArrivalLaw(
        (0.05, 0.25, 0.45, 0.20, 0.04),
        0.01,
        pause_probability=0.01,
        name="unbound_custom_law",
    )
    dispatches = (5.0, 5.0)
    receipts = _sample_path(custom, dispatches, rng=random.Random(7))
    verifier = ArrivalEProcess.from_spec(
        _arrival_spec(),
        alpha_episode=0.05,
        preproposal_history=tuple(zip(dispatches, receipts, strict=True)),
        null_law=custom,
        source="collie_shockspec",
    )
    assert verifier.validity_label == EMPIRICAL_ONLY


def test_no_fifo_identity_used() -> None:
    forbidden_names = {
        "FIFOLedger",
        "LedgerEntry",
        "shipment_ages",
        "actual_lead_time",
        "supply_realization",
    }
    offenders = []
    for path in (REPO_ROOT / "collie/verify").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                offenders.append(f"{path.name}:{node.lineno}:{node.id}")
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                offenders.append(f"{path.name}:{node.lineno}:{node.attr}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                names = [alias.name for alias in node.names]
                if "collie.control.ledger" in {module, *names}:
                    offenders.append(f"{path.name}:{node.lineno}:forbidden control import")
    assert not offenders


def test_validity_flags_match_the_note() -> None:
    expected = {
        "demand_level_up": "anytime_valid",
        "demand_level_down": "anytime_valid",
        "temporary_pulse": "anytime_valid_low_power",
        "lead_time_shift": "anytime_valid_collie_shockspec_only",
        "shipment_loss": "anytime_valid_collie_shockspec_only",
        "transit_pause": "anytime_valid_collie_shockspec_only",
        "compound": "anytime_valid_via_splitting",
    }
    assert {row.family: row.status for row in family_validity_flags()} == expected
    official = {row.family: row.status for row in family_validity_flags(source="official")}
    assert official["lead_time_shift"] == EMPIRICAL_ONLY
    assert official["shipment_loss"] == EMPIRICAL_ONLY
    assert official["transit_pause"] == EMPIRICAL_ONLY
    assert official["compound"] == EMPIRICAL_ONLY
    censored = family_validity_flags(observation_mode=ObservationMode.CENSORED)
    plug_in = family_validity_flags(plug_in=True)
    assert censored[0].status == EMPIRICAL_ONLY
    assert plug_in[0].status == "empirical_only_permanently"
    assert len(family_validity_flags()) + len(censored) + len(plug_in) == 9


def test_derivation_and_checkpoint_import_paths_share_one_implementation() -> None:
    from collie.verify.supply_forward import ArrivalForwardFilter as note_path

    assert note_path is ArrivalForwardFilter
