"""Table-driven tests for payload validation and provenance injection."""

from __future__ import annotations

import json
from itertools import product
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from collie.contracts import (
    Direction,
    DurationBin,
    MagnitudeBin,
    Persistence,
    ShockFamily,
    ShockSpec,
    TargetStream,
)
from collie.fakes.fake_llm import canned
from collie.spec.parse import validate_extracted_payload
from collie.spec.registry import FAMILY_SIGNATURE, FAMILY_TARGET_STREAM, ONSET_WINDOWS, SIGNATURES
from collie.spec.schema import inject_provenance, validate_payload


def _payload_for(
    family: ShockFamily = ShockFamily.TRANSIT_PAUSE, **overrides: Any
) -> dict[str, Any]:
    signatures = FAMILY_SIGNATURE[family]
    payload: dict[str, Any] = {
        "target_stream": FAMILY_TARGET_STREAM[family].value,
        "shock_family": family.value,
        "direction": Direction.ARRIVAL_INTERRUPTED.value,
        "onset_window": [-1, 1],
        "magnitude_bin": MagnitudeBin.MEDIUM.value,
        "persistence": Persistence.TRANSIENT.value,
        "duration_bin": DurationBin.MEDIUM.value,
        "evidence_refs": ["alert_17", "obs_t17"],
        "prospective_signature": next(
            signature for signature in SIGNATURES if signature in signatures
        ),
    }
    if family is ShockFamily.NO_CHANGE:
        payload.update(
            direction=Direction.NONE.value,
            onset_window=None,
            magnitude_bin=None,
            persistence=Persistence.UNKNOWN.value,
            duration_bin=DurationBin.NONE.value,
            evidence_refs=[],
        )
    elif FAMILY_TARGET_STREAM[family] is TargetStream.DEMAND:
        payload["direction"] = Direction.DEMAND_UP.value
    elif family is ShockFamily.LEAD_TIME_SHIFT:
        payload["direction"] = Direction.ARRIVAL_DELAYED.value
    elif family is ShockFamily.COMPOUND:
        payload["direction"] = Direction.MIXED.value
    payload.update(overrides)
    if family is ShockFamily.DEMAND_LEVEL and "direction" not in overrides:
        payload["direction"] = (
            Direction.DEMAND_DOWN.value
            if payload["prospective_signature"] == "sig_demand_level_down"
            else Direction.DEMAND_UP.value
        )
    return payload


def _spec(payload: dict[str, Any] | None = None, **provenance: Any):
    trusted = {
        "tau_j": 17,
        "generation_period": 17,
        "proposal_index": 1,
        "model_id": "fake-open-weight-7b",
        "decoding_hash": "det-v1",
        "prompt_hash": "abc123",
    }
    trusted.update(provenance)
    return inject_provenance(payload or _payload_for(), **trusted)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        pytest.param("target_stream", "warehouse", id="target_stream"),
        pytest.param("shock_family", "port_strike", id="shock_family"),
        pytest.param("direction", "sideways", id="direction"),
        pytest.param("magnitude_bin", "extreme", id="magnitude_bin"),
        pytest.param("persistence", "forever", id="persistence"),
        pytest.param("duration_bin", "9_12", id="duration_bin"),
    ],
)
def test_enum_closure_per_field(field: str, invalid: str) -> None:
    with pytest.raises(ValidationError):
        validate_payload(_payload_for(**{field: invalid}))


def test_unknown_field_is_rejected_not_ignored() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_payload(_payload_for(confidence=0.91))


def test_post_validation_assignment_raises() -> None:
    spec = _spec()
    with pytest.raises(ValidationError, match="Instance is frozen"):
        spec.direction = Direction.DEMAND_UP


@pytest.mark.parametrize(
    "window",
    [
        pytest.param([-3, 3], id="wider"),
        pytest.param([1, -1], id="reversed"),
        pytest.param([0, 1], id="unregistered"),
    ],
)
def test_onset_window_must_be_registered(window: list[int]) -> None:
    with pytest.raises(ValidationError, match="onset_window"):
        validate_payload(_payload_for(onset_window=window))


ILLEGAL_PAIRS = tuple(
    (family, signature)
    for family, signature in product(ShockFamily, SIGNATURES)
    if signature not in FAMILY_SIGNATURE[family]
)


@pytest.mark.parametrize(
    ("family", "signature"),
    ILLEGAL_PAIRS,
    ids=lambda value: value.value if isinstance(value, ShockFamily) else value,
)
def test_illegal_family_signature_pairing_raises(family: ShockFamily, signature: str) -> None:
    with pytest.raises(ValidationError, match="not registered"):
        validate_payload(_payload_for(family, prospective_signature=signature))


LEGAL_PAIRS = tuple(
    (family, signature)
    for family in ShockFamily
    for signature in SIGNATURES
    if signature in FAMILY_SIGNATURE[family]
)


@pytest.mark.parametrize(("family", "signature"), LEGAL_PAIRS)
def test_every_legal_family_signature_pair_is_accepted(family: ShockFamily, signature: str) -> None:
    payload = validate_payload(_payload_for(family, prospective_signature=signature))
    assert payload.shock_family is family
    assert payload.prospective_signature == signature


@pytest.mark.parametrize(
    ("name", "family", "overrides"),
    [
        pytest.param(
            "abstention-stream",
            ShockFamily.NO_CHANGE,
            {"target_stream": "demand"},
            id="no_change_requires_none_stream",
        ),
        pytest.param(
            "abstention-direction",
            ShockFamily.NO_CHANGE,
            {"direction": "demand_up"},
            id="no_change_requires_none_direction",
        ),
        pytest.param(
            "abstention-onset",
            ShockFamily.NO_CHANGE,
            {"onset_window": [-1, 1]},
            id="no_change_requires_null_onset",
        ),
        pytest.param(
            "abstention-magnitude",
            ShockFamily.NO_CHANGE,
            {"magnitude_bin": "medium"},
            id="no_change_requires_null_magnitude",
        ),
        pytest.param(
            "shock-onset",
            ShockFamily.TRANSIT_PAUSE,
            {"onset_window": None},
            id="shock_requires_onset",
        ),
        pytest.param(
            "shock-magnitude-null",
            ShockFamily.TRANSIT_PAUSE,
            {"magnitude_bin": None},
            id="shock_requires_magnitude",
        ),
        pytest.param(
            "shock-magnitude-none",
            ShockFamily.TRANSIT_PAUSE,
            {"magnitude_bin": "none"},
            id="shock_rejects_none_magnitude",
        ),
        pytest.param(
            "shock-stream",
            ShockFamily.TRANSIT_PAUSE,
            {"target_stream": "none"},
            id="shock_requires_registered_stream",
        ),
    ],
)
def test_abstention_nullity_rules(
    name: str, family: ShockFamily, overrides: dict[str, Any]
) -> None:
    assert name
    with pytest.raises(ValidationError):
        validate_payload(_payload_for(family, **overrides))


def test_cooperative_none_spelling_is_normalised_by_frozen_contract() -> None:
    abstention = _spec(_payload_for(ShockFamily.NO_CHANGE, magnitude_bin="none"))
    assert abstention.is_abstention
    assert abstention.magnitude_bin is None
    assert abstention.onset_window is None


@pytest.mark.parametrize(
    "field",
    ["tau_j", "proposal_index", "model_id", "decoding_hash", "prompt_hash"],
)
def test_model_cannot_set_provenance(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_payload(_payload_for(**{field: "model-controlled"}))


def test_tau_j_earlier_than_generation_raises() -> None:
    with pytest.raises(ValueError, match="cannot be earlier"):
        _spec(tau_j=16, generation_period=17)


def test_smuggled_threshold_field_raises() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_payload(_payload_for(threshold=2.5))


@pytest.mark.parametrize("family", list(ShockFamily))
def test_target_stream_must_match_family(family: ShockFamily) -> None:
    expected = FAMILY_TARGET_STREAM[family]
    wrong = next(stream for stream in TargetStream if stream is not expected)
    with pytest.raises(ValidationError, match="requires target_stream"):
        validate_payload(_payload_for(family, target_stream=wrong.value))


def test_injected_provenance_is_system_owned_and_frozen() -> None:
    spec = _spec()
    assert spec.tau_j == 17
    assert spec.proposal_index == 1
    assert spec.model_id == "fake-open-weight-7b"
    assert spec.decoding_hash == "det-v1"
    assert spec.prompt_hash == "abc123"
    assert spec.onset_window == (-1, 1)


# Module 1 family definitions + Module 3's canonical example + frozen FakeLLM
# abstention. In particular, the compiler's direction must agree with the test key.
EXPECTED = {
    ("no_change", "sig_demand_level_up"): ("none", "none"),
    ("demand_level", "sig_demand_level_up"): ("demand", "demand_up"),
    ("demand_level", "sig_demand_level_down"): ("demand", "demand_down"),
    ("temporary_pulse", "sig_demand_pulse"): ("demand", "demand_up"),
    ("lead_time_shift", "sig_arrival_delay"): ("arrival", "arrival_delayed"),
    ("shipment_loss", "sig_arrival_loss"): ("arrival", "arrival_interrupted"),
    ("transit_pause", "sig_arrival_stall"): ("arrival", "arrival_interrupted"),
    ("compound", "sig_compound"): ("both", "mixed"),
}
PROVENANCE = dict(
    tau_j=17,
    generation_period=17,
    proposal_index=1,
    model_id="system-model",
    decoding_hash="system-decoding",
    prompt_hash="system-prompt",
)


def test_registry_matches_independent_specification() -> None:
    assert {(str(f), s) for f, ss in FAMILY_SIGNATURE.items() for s in ss} == set(EXPECTED)
    assert set(SIGNATURES) == {s for _, s in EXPECTED}
    assert ONSET_WINDOWS == ((-2, 0), (-1, 1), (0, 2), (-2, 2))


@pytest.mark.parametrize(
    "family,signature", product(sorted({f for f, _ in EXPECTED}), sorted({s for _, s in EXPECTED}))
)
def test_full_family_signature_direction_stream_matrix(family: str, signature: str) -> None:
    for stream, direction in product(TargetStream, Direction):
        raw = json.loads(canned.ABSTENTION if family == "no_change" else canned.VALID)
        raw.update(
            shock_family=family,
            prospective_signature=signature,
            target_stream=stream.value,
            direction=direction.value,
        )
        expected = EXPECTED.get((family, signature)) == (stream.value, direction.value)
        if expected:
            spec = inject_provenance(raw, **PROVENANCE)
            assert (spec.target_stream.value, spec.direction.value) == EXPECTED[family, signature]
            assert type(spec) is ShockSpec
        else:
            with pytest.raises(ValidationError):
                validate_payload(raw)


@pytest.mark.parametrize("window", [["-1", "1"], [False, 2], [-1, True], [-1.0, 1.0], [0, 2.0]])
def test_onset_rejects_coercible_non_integer_cells(window) -> None:
    with pytest.raises(ValidationError):
        validate_payload(json.loads(canned.VALID) | {"onset_window": window})


@pytest.mark.parametrize("window", [(-2, 0), (-1, 1), (0, 2), (-2, 2)])
def test_each_documented_window_is_expressible(window) -> None:
    assert (
        validate_payload(json.loads(canned.VALID) | {"onset_window": list(window)}).onset_window
        == window
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1"])
def test_direct_provenance_injection_also_enforces_one_based_integer_index(value) -> None:
    with pytest.raises(ValueError):
        inject_provenance(json.loads(canned.VALID), **(PROVENANCE | {"proposal_index": value}))


@given(st.tuples(st.integers(-100, 100), st.integers(-100, 100)))
@settings(max_examples=100, derandomize=True)
def test_only_the_four_integer_windows_validate(window) -> None:
    raw = json.loads(canned.VALID) | {"onset_window": list(window)}
    if window in ((-2, 0), (-1, 1), (0, 2), (-2, 2)):
        assert validate_payload(raw).onset_window == window
    else:
        with pytest.raises(ValidationError):
            validate_payload(raw)


@pytest.mark.parametrize(
    "field",
    [
        "target_stream",
        "shock_family",
        "direction",
        "magnitude_bin",
        "persistence",
        "duration_bin",
        "prospective_signature",
    ],
)
@pytest.mark.parametrize("value", [None, 1, True, [], {}, "unknown", "1"])
def test_enum_and_signature_types_are_closed(field, value) -> None:
    # "unknown" is an explicitly registered persistence value.
    if field == "persistence" and value == "unknown":
        assert (
            validate_payload(json.loads(canned.VALID) | {field: value}).persistence
            is Persistence.UNKNOWN
        )
    else:
        with pytest.raises(ValidationError):
            validate_payload(json.loads(canned.VALID) | {field: value})


@pytest.mark.parametrize("onset,magnitude", product([None, "none"], repeat=2))
def test_abstention_spelling_is_canonical_at_payload_and_frozen_boundaries(
    onset, magnitude
) -> None:
    raw = json.loads(canned.ABSTENTION) | {"onset_window": onset, "magnitude_bin": magnitude}
    payload = validate_payload(raw)
    assert payload.onset_window is None
    assert payload.magnitude_bin is None
    spec = inject_provenance(payload, **PROVENANCE)
    assert spec.is_abstention and spec.onset_window is None and spec.magnitude_bin is None


@pytest.mark.parametrize("persistence,duration", product(Persistence, DurationBin))
def test_abstention_does_not_invent_unregistered_persistence_duration_rules(
    persistence, duration
) -> None:
    # Contract only constrains stream, direction, onset, magnitude for abstention.
    raw = json.loads(canned.ABSTENTION) | {
        "persistence": persistence.value,
        "duration_bin": duration.value,
        "evidence_refs": ["obs_t17"],
    }
    payload = validate_extracted_payload(json.dumps(raw), permitted_evidence_ids=("obs_t17",))
    assert inject_provenance(payload, **PROVENANCE).is_abstention


@pytest.mark.parametrize("field", list(json.loads(canned.VALID)))
def test_every_payload_field_is_required(field) -> None:
    raw = json.loads(canned.VALID)
    del raw[field]
    with pytest.raises(ValidationError):
        validate_payload(raw)


@pytest.mark.parametrize("base", [canned.VALID, canned.ABSTENTION])
@pytest.mark.parametrize(
    "field",
    [
        "threshold",
        "falsifier",
        "confidence",
        "likelihood",
        "code",
        "order_formula",
        "tau_j",
        "proposal_index",
        "model_id",
        "decoding_hash",
        "prompt_hash",
    ],
)
def test_smuggling_is_rejected_for_shocks_and_abstentions(base, field) -> None:
    raw = json.loads(base) | {field: {"attack": "set my own test"}}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_payload(raw)


@pytest.mark.parametrize("base", [canned.VALID, canned.ABSTENTION])
@pytest.mark.parametrize(
    "refs", [["obs_t99"], ["obs_t17", "alert_404"], ["__import__('os')"], ["obs_t17\u200b"]]
)
def test_phantom_evidence_is_rejected_even_for_abstention(base, refs) -> None:
    with pytest.raises(ValueError, match="not present in prompt"):
        validate_extracted_payload(
            json.dumps(json.loads(base) | {"evidence_refs": refs}),
            permitted_evidence_ids=("obs_t17", "alert_17"),
        )


def test_accepted_payload_cannot_be_rewritten_via_source_containers() -> None:
    raw = json.loads(canned.VALID)
    spec = inject_provenance(raw, **PROVENANCE)
    raw["evidence_refs"].append("phantom")
    raw["onset_window"][0] = -100
    assert spec.evidence_refs == ("alert_17", "obs_t17")
    assert spec.onset_window == (-1, 1)
    for name, value in spec.model_dump().items():
        with pytest.raises(ValidationError, match="frozen"):
            setattr(spec, name, value)
