"""End-to-end synthetic paths. All notices, judgments, forecasts and calls are invented."""

import json
import sqlite3

import pytest

from analysis.coling.followup.execution import (
    AccountingLedger, Returned, ScriptedTransport, TokenCounter, Usage, prepare_request,
    reading_identity, request_bound_identity, run_mock,
)
from analysis.coling.followup.parsing import parse_natural, parse_role
from analysis.coling.followup.records import NaturalObservation, ParseStatus
from analysis.coling.followup.role_analysis import RoleObservation
from analysis.coling.followup.role_materials import synthetic_role_programme as role_programme
from analysis.coling.followup.test_execution import DEEPSEEK, LLAMA, Clock, price
from analysis.coling.followup.test_sampling import project_event, source_row


def test_source_to_mock_response_is_request_bound_and_legacy_analysis_is_blocked():
    event = project_event(source_row(1, text="Current recovery is 2028-03-28."))
    model = LLAMA
    schedule = price(model)
    request = prepare_request(
        item_id=event.statement_group_id, cohort="N", model_id=model,
        template_id="january-natural-v1", model_input=event.model_input(),
        tokenizer=TokenCounter(model, "d" * 64, lambda payload: 800), price=schedule,
    )
    assert request.item_text_sha256 == event.model_input_sha256
    content = json.dumps({"statement_type": "recovery",
                          "interval": {"start": "2028-03-01", "end": "2028-03-28"},
                          "certainty": "estimated", "quote": "Current recovery"})
    returned = Returned(content, "stop", model, schedule.provider_route, schedule.precision,
                        Usage(800, 20, 820, None, "0.00008"))
    connection, clock = sqlite3.connect(":memory:"), Clock()
    ledger = AccountingLedger(connection, max_retries=0)
    response = run_mock(request, schedule, ledger, ScriptedTransport([returned]),
                        clock=clock.now, sleep=clock.sleep)
    parsed = parse_natural(response.content, event.notice_text, finish_reason=response.finish_reason)
    assert parsed.status is ParseStatus.VALID
    identity = request_bound_identity(request, schedule, parser_sha256="e" * 64)
    assert identity.cohort == "N" and identity.request_id == request.request_id
    assert identity.payload_sha256 == request.payload_sha256 and identity.item_text_sha256 == request.item_text_sha256
    with pytest.raises(RuntimeError, match="integration blocked"):
        reading_identity(request, parser_sha256="e" * 64)
    with pytest.raises(ValueError, match="present identity"):
        NaturalObservation(parsed, identity)
    assert ledger.snapshot()["http_attempts"] == 1
    connection.close()


def test_two_model_role_mock_path_keeps_all_variants_request_bound():
    seeds = role_programme("reduced").assigned[:3]
    connection, clock = sqlite3.connect(":memory:"), Clock()
    ledger = AccountingLedger(connection, max_retries=0)
    identities = set()
    for model in (LLAMA, DEEPSEEK):
        schedule = price(model)
        for seed in seeds:
            for variant in seed.variants:
                request = prepare_request(
                    item_id=variant.item_id, cohort="R", model_id=model,
                    template_id="january-role-v1", model_input=variant.model_input(),
                    tokenizer=TokenCounter(model, "d" * 64, lambda payload: 800), price=schedule,
                )
                selected = (seed.competing_date if model == LLAMA and variant.primary
                            and variant.arm == "competitor" else seed.target_date)
                text = json.dumps({"date": selected.isoformat(), "quote": ""})
                returned = Returned(text, "stop", model, schedule.provider_route, schedule.precision,
                                    Usage(800, 20, 820, None, "0.00008"))
                response = run_mock(request, schedule, ledger, ScriptedTransport([returned]),
                                    clock=clock.now, sleep=clock.sleep)
                parsed = parse_role(response.content, variant.notice_text, finish_reason=response.finish_reason)
                assert parsed.status is ParseStatus.VALID
                identity = request_bound_identity(request, schedule, parser_sha256="e" * 64)
                assert identity.cohort == "R" and identity.item_id == variant.item_id
                identities.add(identity.request_id)
                with pytest.raises(ValueError, match="reading identity"):
                    RoleObservation(variant.item_id, parsed, identity)
    assert len(identities) == 24
    assert ledger.snapshot()["http_attempts"] == 24
    connection.close()


def test_mock_end_to_end_quarantines_an_out_of_range_returned_charge():
    connection, clock = sqlite3.connect(":memory:"), Clock()
    ledger = AccountingLedger(connection, max_retries=0)
    schedule = price(LLAMA)
    candidate = prepare_request(
        item_id="fictional-1", cohort="N", model_id=LLAMA, template_id="january-natural-v1",
        model_input={"update_date": "2028-03-01", "notice_text": "Fictional recovery is in July."},
        tokenizer=TokenCounter(LLAMA, "d" * 64, lambda payload: 800), price=schedule,
    )
    returned = Returned("{}", "stop", LLAMA, schedule.provider_route, schedule.precision,
                        Usage(800, 10, 810, None, "9000001"))
    result = run_mock(candidate, schedule, ledger, ScriptedTransport([returned]),
                      clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "unknown_usage"
    assert ledger.snapshot()["stop_reason"] == "invalid_usage"
    assert ledger.snapshot()["reserved_picos"] == schedule.reservation_picos
    state, has_response, claim = connection.execute("SELECT state,has_response,charge_claim FROM attempts").fetchone()
    assert state == "returned_quarantined" and has_response == 1 and json.loads(claim)["prefix"] == "9000001"
    other = price(DEEPSEEK)
    second = prepare_request(
        item_id="fictional-2", cohort="N", model_id=DEEPSEEK, template_id="january-natural-v1",
        model_input={"update_date": "2028-03-01", "notice_text": "Another fictional recovery."},
        tokenizer=TokenCounter(DEEPSEEK, "d" * 64, lambda payload: 800), price=other,
    )
    assert ledger.reserve(second, other, now=clock.now()).reason == "account_stopped"
    connection.close()
