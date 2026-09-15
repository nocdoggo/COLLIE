"""Checkpoint 2 extraction, repair, fallback, and accounting tests."""

from __future__ import annotations

import hashlib
import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from collie.arms.base_stock import CappedBaseStockController
from collie.contracts import AlertMessage, ParseOutcome, PeriodObservation
from collie.fakes.fake_llm import FakeLLM, canned
from collie.spec.parse import extract_json_payload, parse_shockspec, validate_extracted_payload
from collie.spec.prompt import REPAIR_SUFFIX, build_prompt, build_repair_prompt


def _observation(period: int = 17, demand: float = 112.0) -> PeriodObservation:
    return PeriodObservation(
        period=period,
        date=f"2026-01-{period:02d}",
        on_hand=80.0,
        in_transit_total=35.0,
        prev_order=20.0,
        prev_arrivals=0.0,
        profit_per_unit=4.0,
        holding_cost_per_unit=1.0,
        promised_lead_time=2,
        prev_demand=demand,
        alert=AlertMessage(
            alert_id="source-alert",
            period=period,
            text="Transfer-hub processing may be interrupted.",
        ),
    )


def _prompt():
    return build_prompt([_observation()], tau_j=17)


def _parse(client: FakeLLM):
    return parse_shockspec(
        client,
        _prompt(),
        episode_id="episode-safe-id",
        arm_id="arm-8",
        proposal_index=1,
    )


def _invalid_cases() -> list[tuple[str, str]]:
    valid = json.loads(canned.VALID)
    return [
        ("truncated", canned.TRUNCATED),
        ("empty", canned.EMPTY),
        ("extra_field", canned.EXTRA_FIELD),
        ("smuggled_threshold", canned.SMUGGLED_THRESHOLD),
        ("smuggled_falsifier", canned.SMUGGLED_FALSIFIER),
        ("wrong_type", canned.WRONG_TYPE),
        ("unknown_enum", canned.UNKNOWN_ENUM),
        ("incoherent_abstention", canned.INCOHERENT_ABSTENTION),
        ("phantom_evidence", canned.PHANTOM_EVIDENCE),
        ("unregistered_window", json.dumps({**valid, "onset_window": [-3, 3]})),
        (
            "illegal_family_signature",
            json.dumps({**valid, "prospective_signature": "sig_demand_level_up"}),
        ),
        ("numeric_string_enum", json.dumps({**valid, "magnitude_bin": "2"})),
        ("unicode_quotes", canned.VALID.replace('"', "”")),
        ("trailing_comma", canned.VALID[:-1] + ",}"),
        ("null_enum", json.dumps({**valid, "persistence": None})),
        ("json_array", "[]"),
        ("plain_prose", "I cannot determine a shock."),
    ]


@pytest.mark.parametrize(
    "name,raw",
    [
        ("strict", canned.VALID),
        ("prose_wrapper", canned.PROSE_WRAPPED),
        ("json_fence", canned.FENCED),
        ("abstention", canned.ABSTENTION),
        ("abstention_none_spelling", canned.ABSTENTION_NONE_SPELLING),
        ("two_objects", f'{canned.VALID}\n{{"ignored": true}}'),
        ("nested_code_block", f"```text\n```json\n{canned.VALID}\n```\n```"),
    ],
)
def test_extraction_accepts_valid_variants(name: str, raw: str) -> None:
    result = _parse(FakeLLM(responses=[raw]))
    assert result.outcome is ParseOutcome.ACCEPTED, name
    assert result.spec is not None
    assert len(result.calls) == 1


@pytest.mark.parametrize("name,raw", _invalid_cases())
def test_extraction_handles_the_fuzz_corpus(name: str, raw: str) -> None:
    result = _parse(FakeLLM(responses=[raw, canned.VALID]))
    assert result.outcome is ParseOutcome.ACCEPTED_AFTER_REPAIR, name
    assert result.spec is not None
    assert len(result.calls) == 2
    assert result.errors


def test_first_balanced_object_is_selected() -> None:
    first = extract_json_payload(f'prefix {canned.VALID} suffix {{"later": true}}')
    assert first == json.loads(canned.VALID)


def test_evidence_ref_outside_the_set_fails_validation() -> None:
    with pytest.raises(ValueError, match="not present in prompt"):
        validate_extracted_payload(
            canned.PHANTOM_EVIDENCE,
            permitted_evidence_ids=_prompt().evidence_ids,
        )


def test_unknown_fields_are_rejected_not_silently_dropped() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_extracted_payload(
            canned.SMUGGLED_THRESHOLD,
            permitted_evidence_ids=_prompt().evidence_ids,
        )


def test_exactly_one_repair_attempt() -> None:
    client = FakeLLM.always_invalid()
    result = _parse(client)
    assert result.outcome is ParseOutcome.FALLBACK
    assert result.spec is None
    assert client.n_calls == 2
    assert len(result.calls) == 2


def test_repair_prompt_adds_no_episode_information() -> None:
    prompt = _prompt()
    client = FakeLLM.repair_then_succeed()
    result = parse_shockspec(
        client,
        prompt,
        episode_id="EPISODE_SECRET_NOT_FOR_PROMPT",
        arm_id="arm-8",
        proposal_index=1,
    )
    assert result.outcome is ParseOutcome.ACCEPTED_AFTER_REPAIR
    assert client.prompts == [prompt.text, f"{prompt.text}\n\n{REPAIR_SUFFIX}"]
    assert "EPISODE_SECRET_NOT_FOR_PROMPT" not in client.prompts[1]


def test_baseline_replay_sanity_does_not_certify_fallback_integration() -> None:
    result = _parse(FakeLLM.always_invalid())
    assert result.spec is None

    # Local sanity only: these controllers do not consume result. This equality
    # cannot establish the Module 4/6 fallback contract; its real gate is explicit
    # in test_spec_verifier_contract.py until those consumers exist.
    failed_proposal_path = CappedBaseStockController(train_demand=(90.0, 100.0))
    no_proposal_path = CappedBaseStockController(train_demand=(90.0, 100.0))
    observations = [_observation(17, 112.0), _observation(18, 105.0)]
    failed_orders = [failed_proposal_path.order(obs).order_quantity for obs in observations]
    baseline_orders = [no_proposal_path.order(obs).order_quantity for obs in observations]
    assert failed_orders == baseline_orders


def test_abstention_distinguished_from_failure() -> None:
    abstention = _parse(FakeLLM(responses=[canned.ABSTENTION]))
    failure = _parse(FakeLLM.always_invalid())
    assert abstention.outcome is ParseOutcome.ACCEPTED
    assert abstention.spec is not None and abstention.spec.is_abstention
    assert failure.outcome is ParseOutcome.FALLBACK
    assert failure.spec is None


def test_ledger_counts_attempted_repaired_and_rejected() -> None:
    prompt = _prompt()
    repair = build_repair_prompt(prompt)
    result = _parse(FakeLLM.repair_then_succeed())
    assert [call.attempt_index for call in result.calls] == [1, 2]
    assert [call.outcome for call in result.calls] == [None, ParseOutcome.ACCEPTED_AFTER_REPAIR]
    assert [call.prompt_hash for call in result.calls] == [prompt.prompt_hash, repair.prompt_hash]
    assert len({call.call_id for call in result.calls}) == 2
    assert all(call.episode_id == "episode-safe-id" for call in result.calls)
    assert all(call.arm_id == "arm-8" for call in result.calls)
    assert all(call.model_id == "fake-open-weight-7b" for call in result.calls)


def test_provenance_is_injected_from_trusted_call_context() -> None:
    prompt = _prompt()
    result = _parse(FakeLLM(responses=[canned.VALID]))
    assert result.spec is not None
    assert result.spec.tau_j == 17
    assert result.spec.proposal_index == 1
    assert result.spec.model_id == "fake-open-weight-7b"
    assert result.spec.decoding_hash == "det-v1"
    assert result.spec.prompt_hash == prompt.prompt_hash


def test_transport_failures_are_counted_and_fall_back() -> None:
    client = FakeLLM(fail_after=0)
    result = _parse(client)
    assert result.outcome is ParseOutcome.FALLBACK
    assert result.spec is None
    assert client.n_calls == 2
    assert len(result.calls) == 2
    assert all("RuntimeError" in error for error in result.errors)


def run(client, **kwargs):
    return parse_shockspec(
        client, _prompt(), episode_id="e", arm_id="a", proposal_index=1, **kwargs
    )


@pytest.mark.parametrize(
    "wrap", [lambda s: s, lambda s: f"```json\n{s}\n```", lambda s: f"answer: {s}"]
)
@pytest.mark.parametrize(
    "raw",
    [
        canned.VALID[:-1] + ',"direction":"arrival_interrupted"}',
        canned.VALID[:-1] + ',"direction":"demand_up","direction":"arrival_interrupted"}',
    ],
)
def test_ambiguous_or_nonobject_payloads_cannot_be_salvaged(wrap, raw) -> None:
    client = FakeLLM(default=wrap(raw))
    result = run(client)
    assert result.outcome is ParseOutcome.FALLBACK
    assert result.spec is None and client.n_calls == 2
    assert len(result.errors) == len(result.calls) == 2


@pytest.mark.parametrize("raw", ["[" + canned.VALID + "]", "```json\n[" + canned.VALID + "]\n```"])
def test_complete_array_is_not_unwrapped_into_a_proposal(raw) -> None:
    result = run(FakeLLM(default=raw))
    assert result.outcome is ParseOutcome.FALLBACK and result.spec is None


def test_extraction_priority_strict_then_fenced_then_first_balanced() -> None:
    raw = {"literal": '```json\n{"wrong":1}\n```'}
    assert extract_json_payload(json.dumps(raw)) == raw
    assert extract_json_payload('prefix {"earlier":1}\n```json\n{"fenced":2}\n```') == {"fenced": 2}
    assert extract_json_payload('prefix {"first":1} {"second":2}') == {"first": 1}
    with pytest.raises(ValueError):
        extract_json_payload('prefix {"bad":} {"later":1}')


@given(st.text(max_size=100))
@settings(max_examples=100, derandomize=True)
def test_balanced_scan_respects_json_string_escaping(value) -> None:
    expected = {"text": value, "nested": {"braces": '{}\\"'}}
    assert (
        extract_json_payload("prefix " + json.dumps(expected) + ' suffix {"later":true}')
        == expected
    )


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "[]",
        "null",
        "true",
        '"text"',
        canned.TRUNCATED,
        canned.VALID[:-1] + ",}",
        canned.VALID.replace('"', "”"),
        "[" * 2000 + "]" * 2000,
        "```text\n```json\n{bad}\n```\n```",
    ],
)
def test_two_hostile_outputs_always_end_in_counted_fallback(raw) -> None:
    client = FakeLLM(default=raw)
    result = run(client)
    assert result.outcome is ParseOutcome.FALLBACK and result.spec is None
    assert len(result.calls) == len(result.errors) == client.n_calls == 2
    assert [c.outcome for c in result.calls] == [None, ParseOutcome.FALLBACK]


class ProviderFailure(Exception):
    pass


@pytest.mark.parametrize(
    "error_type", [ProviderFailure, TimeoutError, ConnectionError, RuntimeError]
)
@pytest.mark.parametrize("recover", [False, True])
def test_every_provider_exception_is_logged_with_at_most_one_repair(error_type, recover) -> None:
    class Client:
        model_id = "provider"
        prompts: list[str]

        def __init__(self):
            self.prompts = []

        def complete(self, prompt, *, decoding_hash):
            self.prompts.append(prompt)
            if not recover or len(self.prompts) == 1:
                raise error_type("provider failure")
            return canned.ABSTENTION

    client = Client()
    result = run(client)
    assert len(result.calls) == len(client.prompts) == 2
    assert result.calls[0].outcome is None
    assert len(result.errors) == (1 if recover else 2)
    assert result.outcome is (
        ParseOutcome.ACCEPTED_AFTER_REPAIR if recover else ParseOutcome.FALLBACK
    )
    if recover:
        assert result.spec is not None and result.spec.is_abstention
    else:
        assert result.spec is None
    for call, text in zip(result.calls, client.prompts, strict=True):
        assert call.prompt_hash == hashlib.sha256(text.encode()).hexdigest()
        assert call.physical and call.latency_ms >= 0


@pytest.mark.parametrize("value", [None, [], {}, 1, b"{}"])
def test_non_string_provider_response_is_a_counted_failure(value) -> None:
    result = run(FakeLLM(default=value))
    assert result.outcome is ParseOutcome.FALLBACK and len(result.calls) == 2


@pytest.mark.parametrize("proposal_index", [0, -1, True, 1.5, "1"])
def test_bad_system_provenance_is_rejected_before_charging_a_call(proposal_index) -> None:
    client = FakeLLM(default=canned.ABSTENTION)
    with pytest.raises((ValueError, TypeError)):
        parse_shockspec(
            client, _prompt(), episode_id="e", arm_id="a", proposal_index=proposal_index
        )
    assert client.n_calls == 0


def test_backdated_tau_is_rejected_before_charging_a_call() -> None:
    client = FakeLLM()
    with pytest.raises(ValueError, match="cannot be earlier"):
        run(client, generation_period=18)
    assert client.n_calls == 0


def test_repair_provenance_describes_the_exact_successful_request() -> None:
    client = FakeLLM(responses=[canned.SMUGGLED_THRESHOLD, canned.ABSTENTION])
    result = run(client)
    assert result.spec is not None and result.spec.is_abstention
    assert result.spec.prompt_hash == hashlib.sha256(client.prompts[1].encode()).hexdigest()
    assert result.spec.tau_j == 17 and result.spec.proposal_index == 1
    assert [c.attempt_index for c in result.calls] == [1, 2]


@given(st.text(max_size=500))
@settings(max_examples=100, derandomize=True)
def test_arbitrary_model_text_never_escapes_the_accounted_boundary(raw) -> None:
    client = FakeLLM(default=raw)
    result = run(client)
    assert len(result.calls) == client.n_calls
    assert 1 <= client.n_calls <= 2
    if result.outcome is ParseOutcome.FALLBACK:
        assert result.spec is None and len(result.errors) == client.n_calls == 2
    else:
        assert result.spec is not None
        assert set(result.spec.evidence_refs) <= set(_prompt().evidence_ids)
        assert result.spec.tau_j == 17


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_extractor_rejects_non_json_numeric_extensions(constant) -> None:
    with pytest.raises(ValueError):
        extract_json_payload('{"value":' + constant + "}")
