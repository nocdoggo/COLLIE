"""Mock-only execution, accounting, retry, and restart tests."""

import hashlib
import itertools
import json
import sqlite3
import tempfile
import threading
from dataclasses import fields, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from random import Random

import pytest

from analysis.coling.followup import execution, prompts
from analysis.coling.followup.execution import (
    INPUT_LIMIT, MAX_MONEY_LENGTH, MAX_REQUEST_CHARS, MAX_RESPONSE_CHARS, OUTPUT_LIMIT,
    SQLITE_INT_MAX, USER_AGENT, AccountingLedger, PriceSchedule, Returned,
    ScriptedTransport, TokenCounter, TransportFailure, Usage, prepare_request, run_mock,
)
from analysis.coling.followup.parsing import parse_natural
from analysis.coling.followup.records import ParseStatus


LLAMA = "meta-llama/llama-3.3-70b-instruct"
DEEPSEEK = "deepseek/deepseek-chat"


def price(model=LLAMA):
    if model == LLAMA:
        return PriceSchedule(model, "deepinfra/turbo", "fp8", "0.0000001", "0.00000032", "0",
                             131072, "a" * 64, True, True, OUTPUT_LIMIT + 100, "0.02", "f" * 64)
    return PriceSchedule(model, "deepinfra/fp4", "fp4", "0.00000032", "0.00000089", "0",
                         163840, "b" * 64, True, True, OUTPUT_LIMIT + 100, "0.055", "f" * 64)


def request(item="N1", *, model=LLAMA, template="january-natural-v1", cohort="N",
            notice="Fictional recovery is in July.", tokens=800, schedule=None):
    schedule = schedule or price(model)
    counter = TokenCounter(model, "d" * 64, lambda payload: tokens)
    return prepare_request(item_id=item, cohort=cohort, model_id=model, template_id=template,
                           model_input={"update_date": "2028-03-01", "notice_text": notice},
                           tokenizer=counter, price=schedule)


def good_response(model=LLAMA, *, content='{"statement_type":"recovery","interval":null,"certainty":"undetermined","quote":""}',
                  finish="stop", usage=None):
    schedule = price(model)
    return Returned(content, finish, model, schedule.provider_route, schedule.precision,
                    usage or Usage(800, 10, 810, None, "0.00008"))


class Clock:
    def __init__(self):
        self.value = 1000
        self.sleeps = []

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


@pytest.fixture
def ledger():
    connection = sqlite3.connect(":memory:")
    yield AccountingLedger(connection, max_retries=1400)
    connection.close()


def test_exact_request_payload_and_cache_reuse(ledger):
    req, schedule, clock = request(), price(), Clock()
    body = json.loads(req.payload)
    assert body["max_tokens"] == OUTPUT_LIMIT and body["temperature"] == 0
    assert body["provider"] == {"order": ["deepinfra/turbo"], "only": ["deepinfra/turbo"],
                                "allow_fallbacks": False, "quantizations": ["fp8"],
                                "require_parameters": True, "data_collection": "deny",
                                "max_price": {"prompt": .1, "completion": .32, "request": 0.0}}
    assert body["response_format"]["json_schema"]["schema"] == prompts.schema_for("january-natural-v1")
    assert set(json.loads(req.model_input_bytes)) == {"update_date", "notice_text"}
    transport = ScriptedTransport([good_response()])
    first = run_mock(req, schedule, ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert first.status == "returned" and not first.from_cache
    assert transport.payloads == [req.payload] and transport.user_agents == [USER_AGENT]
    before = ledger.snapshot()
    again = run_mock(req, schedule, ledger, ScriptedTransport([]), clock=clock.now, sleep=clock.sleep)
    assert again.status == "returned" and again.from_cache and again.content == first.content
    assert ledger.snapshot() == before
    assert before["http_attempts"] == 1 and before["reserved_picos"] == 0


def test_data_collection_policy_is_pinned_in_payload_and_cache_identity(ledger):
    req, schedule = request(), price()
    assert json.loads(req.payload)["provider"]["data_collection"] == "deny"

    def hypothetical(policy):
        body = json.loads(req.payload)
        if policy is None:
            del body["provider"]["data_collection"]
        else:
            body["provider"]["data_collection"] = policy
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        changed = replace(req, payload=payload, payload_sha256=hashlib.sha256(payload).hexdigest())
        return replace(changed, request_id=execution._identity(changed, body))

    legacy = hypothetical(None)
    relaxed = hypothetical("allow")
    assert len({req.payload_sha256, legacy.payload_sha256, relaxed.payload_sha256}) == 3
    assert len({req.request_id, legacy.request_id, relaxed.request_id}) == 3
    for changed in (legacy, relaxed):
        with pytest.raises(ValueError, match="configuration or cache identity"):
            ledger.reserve(changed, schedule, now=1000)

    # Invent a prior cached assignment without the policy; it must not be
    # reused or silently rerun as the new assignment.
    ledger.db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)", (
        legacy.request_id, legacy.payload_sha256, legacy.item_id, legacy.cohort, legacy.model_id,
        legacy.template_id, legacy.provider_route, legacy.precision, legacy.pricing_sha256,
    ))
    ledger.db.execute(
        "INSERT INTO attempts(request_id,attempt_index,state,reserved,charge_ceiling_usd,started,"
        "finished,has_response,response_content,finish_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (legacy.request_id, 1, "returned", schedule.reservation_picos, schedule.independent_charge_ceiling_usd,
         1000, 1000, 1, b"invented legacy response", "stop"),
    )
    ledger.db.execute("UPDATE account SET attempts=1,last_time=1000 WHERE id=1")
    blocked = ledger.reserve(req, schedule, now=1001)
    assert blocked.status == "blocked" and blocked.reason == "assignment_identity_conflict"
    assert ledger.snapshot()["stop_reason"] == "assignment_identity_conflict"
    assert ledger.snapshot()["http_attempts"] == 1


def test_rate_filter_is_pinned_to_schedule_and_cannot_be_silently_omitted(ledger):
    req, schedule = request(), price()
    body = json.loads(req.payload)
    assert body["provider"]["max_price"] == {"prompt": .1, "completion": .32, "request": 0.0}
    altered = []
    for replacement in (None, {"prompt": 1, "completion": 2, "request": 0}):
        changed_body = json.loads(req.payload)
        if replacement is None:
            del changed_body["provider"]["max_price"]
        else:
            changed_body["provider"]["max_price"] = replacement
        payload = json.dumps(changed_body, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        candidate = replace(req, payload=payload, payload_sha256=hashlib.sha256(payload).hexdigest())
        candidate = replace(candidate, request_id=execution._identity(candidate, changed_body))
        altered.append(candidate)
        with pytest.raises(ValueError, match="configuration or cache identity"):
            ledger.reserve(candidate, schedule, now=1000)
    assert len({req.request_id, *(candidate.request_id for candidate in altered)}) == 3
    legacy = altered[0]
    ledger.db.execute("INSERT INTO main.requests VALUES (?,?,?,?,?,?,?,?,?)", (
        legacy.request_id, legacy.payload_sha256, legacy.item_id, legacy.cohort, legacy.model_id,
        legacy.template_id, legacy.provider_route, legacy.precision, legacy.pricing_sha256,
    ))
    ledger.db.execute(
        "INSERT INTO main.attempts(request_id,attempt_index,state,reserved,charge_ceiling_usd,started,"
        "finished,has_response,response_content,finish_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (legacy.request_id, 1, "returned", schedule.reservation_picos, schedule.independent_charge_ceiling_usd,
         1000, 1000, 1, b"invented legacy response", "stop"),
    )
    ledger.db.execute("UPDATE main.account SET attempts=1,last_time=1000 WHERE id=1")
    blocked = ledger.reserve(req, schedule, now=1001)
    assert blocked.status == "blocked" and blocked.reason == "assignment_identity_conflict"
    assert ledger.snapshot()["http_attempts"] == 1


def test_rate_filter_numbers_are_never_rounded_above_the_exact_schedule():
    schedule = replace(price(), prompt_usd_per_token="0.000000100000000000000016",
                       completion_usd_per_token="0.000000320000000000000016",
                       request_fee_usd="0.000000000000000016")
    req = request(schedule=schedule)
    values = json.loads(req.payload, parse_float=Decimal)["provider"]["max_price"]
    assert set(values) == {"prompt", "completion", "request"}
    assert Decimal(0) < values["prompt"] <= Decimal(schedule.prompt_usd_per_token) * 1_000_000
    assert Decimal(0) < values["completion"] <= Decimal(schedule.completion_usd_per_token) * 1_000_000
    assert Decimal(0) <= values["request"] <= Decimal(schedule.request_fee_usd)


@pytest.mark.parametrize("amount", ["0", "0.1", "0.100000000000000016", "0.99999999999999999",
                                     "1e-64", "0." + "0" * 120 + "1", "123456789.123456789"])
@pytest.mark.parametrize("multiplier", [1, 1_000_000])
def test_wire_rate_json_decimal_is_conservatively_bounded(amount, multiplier):
    result = execution._wire_rate_at_most(amount, multiplier=multiplier, name="invented rate")
    encoded = json.dumps(result, allow_nan=False)
    assert Fraction(Decimal(encoded)) <= Fraction(Decimal(amount)) * multiplier
    assert result >= 0 and (result > 0 or Decimal(amount) == 0)


def test_wire_rate_bound_against_exact_rationals_for_synthetic_values():
    rng = Random(20261030)
    for _ in range(2000):
        amount = f"{rng.randrange(1, 10**30)}e{rng.randrange(-64, 65)}"
        for multiplier in (1, 1_000_000):
            result = execution._wire_rate_at_most(amount, multiplier=multiplier, name="invented rate")
            wire = json.dumps(result, allow_nan=False)
            assert type(result) is float and result > 0
            assert Fraction(Decimal(wire)) <= Fraction(Decimal(amount)) * multiplier


def test_request_identity_changes_with_arm_item_model_text_or_pricing():
    base = request()
    variants = [request("N2"), request(notice="A different fictional notice."),
                request(model=DEEPSEEK),
                request(template="january-convention-absent-v1", cohort="C"),
                request(cohort="pilot"), request(schedule=replace(price(), prompt_usd_per_token="0.00000011"))]
    assert len({base.request_id, *(item.request_id for item in variants)}) == len(variants) + 1
    # The absent and natural task bytes happen to match, but identities do not.
    assert base.payload == variants[3].payload and base.request_id != variants[3].request_id
    assert base.decoding_sha256 == variants[3].decoding_sha256
    arms = [request(template=template, cohort="C") for template in (
        "january-convention-absent-v1", "january-convention-neutral-v1", "january-convention-explicit-v1")]
    assert len({item.decoding_sha256 for item in arms}) == 1


def test_request_bound_identity_separates_pilot_and_n_and_disables_legacy_bridge():
    natural, pilot = request("same-item"), request("same-item", cohort="pilot")
    assert natural.payload == pilot.payload and natural.request_id != pilot.request_id
    natural_id = execution.request_bound_identity(natural, price(), parser_sha256="e" * 64)
    pilot_id = execution.request_bound_identity(pilot, price(), parser_sha256="e" * 64)
    assert natural_id != pilot_id and (natural_id.cohort, pilot_id.cohort) == ("N", "pilot")
    assert natural_id.request_id == natural.request_id and natural_id.payload_sha256 == natural.payload_sha256
    assert natural_id.tokenizer_sha256 == natural.tokenizer_sha256 and natural_id.pricing_sha256 == natural.pricing_sha256
    changed_price = replace(price(), prompt_usd_per_token="0.00000011")
    repriced = request("same-item", schedule=changed_price)
    changed_tokenizer = prepare_request(
        item_id="same-item", cohort="N", model_id=LLAMA, template_id="january-natural-v1",
        model_input={"update_date": "2028-03-01", "notice_text": "Fictional recovery is in July."},
        tokenizer=TokenCounter(LLAMA, "c" * 64, lambda payload: 800), price=price(),
    )
    assert changed_tokenizer.payload == natural.payload
    assert repriced.payload != natural.payload  # The price filter is part of the wire payload.
    assert execution.request_bound_identity(repriced, changed_price, parser_sha256="e" * 64) != natural_id
    assert execution.request_bound_identity(changed_tokenizer, price(), parser_sha256="e" * 64) != natural_id
    assert execution.request_bound_identity(natural, price(), parser_sha256="f" * 64) != natural_id
    for item in (natural, pilot):
        with pytest.raises(RuntimeError, match="integration blocked"):
            execution.reading_identity(item, parser_sha256="e" * 64)
    with pytest.raises(ValueError, match="cache identity"):
        execution.request_bound_identity(replace(natural, tokenizer_sha256="0" * 64), price(),
                                         parser_sha256="e" * 64)


def test_changed_pricing_or_payload_cannot_restart_the_same_assignment(ledger):
    original, clock = request(), Clock()
    assert run_mock(original, price(), ledger, ScriptedTransport([good_response()]),
                    clock=clock.now, sleep=clock.sleep).status == "returned"
    changed_price = replace(price(), prompt_usd_per_token="0.00000011")
    changed_request = request(schedule=changed_price)
    blocked = ledger.reserve(changed_request, changed_price, now=clock.now())
    assert blocked.reason == "assignment_identity_conflict"
    assert ledger.snapshot()["stop_reason"] == "assignment_identity_conflict"
    assert ledger.snapshot()["http_attempts"] == 1


def test_rejects_mismatched_or_tampered_payload_and_unmeasured_inputs(ledger):
    with pytest.raises(ValueError, match="input exceeds"):
        request(tokens=INPUT_LIMIT + 1)
    with pytest.raises(ValueError, match="positive integer"):
        request(tokens=True)
    with pytest.raises(ValueError, match="cohort"):
        request(cohort="N", template="january-convention-absent-v1")
    with pytest.raises(ValueError, match="privacy review"):
        request(notice="Fictional contact: example@example.invalid")
    req = request()
    tampered = replace(req, payload=req.payload.replace(b'"max_tokens":1024', b'"max_tokens":2048'))
    with pytest.raises(ValueError, match="payload"):
        ledger.reserve(tampered, price(), now=1000)
    with pytest.raises(ValueError, match="cache identity"):
        ledger.reserve(replace(req, request_id="0" * 64), price(), now=1000)
    with pytest.raises(ValueError, match="configuration"):
        ledger.reserve(replace(req, template_sha256="0" * 64), price(), now=1000)
    with pytest.raises(ValueError, match="tokenizer-measured"):
        ledger.reserve(replace(req, measured_input_tokens=0), price(), now=1000)
    with pytest.raises(ValueError, match="price"):
        ledger.reserve(req, replace(price(), prompt_usd_per_token="0.0000002",
                                    independent_charge_ceiling_usd="0.03"), now=1000)


def test_subclasses_cannot_override_request_or_cost_safeguards(ledger):
    class UnboundedPrice(PriceSchedule):
        @property
        def reservation_picos(self):
            return 0
    class ForgedRequest(type(request())):
        pass
    schedule = price()
    forged_price = UnboundedPrice(*(getattr(schedule, field.name) for field in fields(PriceSchedule)))
    original = request()
    forged_request = ForgedRequest(*(getattr(original, field.name) for field in fields(type(original))))
    with pytest.raises(TypeError, match="typed"):
        ledger.reserve(original, forged_price, now=1000)
    with pytest.raises(TypeError, match="typed"):
        ledger.reserve(forged_request, schedule, now=1000)


def test_pricing_requires_known_route_fees_and_reasoning():
    with pytest.raises(ValueError):
        replace(price(), prompt_usd_per_token="NaN")
    with pytest.raises(ValueError):
        replace(price(), completion_usd_per_token="0")
    with pytest.raises(ValueError):
        replace(price(), no_unmodelled_fees=False)
    with pytest.raises(ValueError):
        replace(price(), reasoning_in_completion=False)
    with pytest.raises(ValueError):
        replace(price(), provider_route="deepinfra/fp4")
    crosscheck = Decimal("131072") * Decimal("0.0000001") + Decimal("1124") * Decimal("0.00000032")
    assert price().reservation_picos == int(Decimal("0.02") * 10**12)
    assert Decimal(price().reservation_picos) / 10**12 > crosscheck
    with pytest.raises(ValueError, match="billable-output bound"):
        replace(price(), max_billable_output_tokens=OUTPUT_LIMIT - 1)
    with pytest.raises(ValueError, match="must cover"):
        replace(price(), independent_charge_ceiling_usd="0.001")
    with pytest.raises(ValueError, match="SHA256"):
        replace(price(), charge_bound_evidence_sha256="invalid")


def test_independent_charge_bound_blocks_a_requested_limit_overrun_before_dispatch():
    schedule = PriceSchedule(LLAMA, "deepinfra/turbo", "fp8", "0.0000000001", "0.009765625", "0",
                             4000, "a" * 64, True, True, 1026, "10.01953165", "f" * 64)
    connection = sqlite3.connect(":memory:")
    ledger = AccountingLedger(connection, max_retries=0)
    candidate = request(schedule=schedule)
    assert schedule.reservation_picos > ledger.snapshot()["cap_picos"]
    assert ledger.reserve(candidate, schedule, now=1000).reason == "cap_blocked"
    assert ledger.snapshot()["http_attempts"] == 0
    connection.close()


def test_completion_above_requested_limit_is_reserved_but_still_stops_the_account(ledger):
    candidate, schedule = request(), price()
    reserved = ledger.reserve(candidate, schedule, now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    usage = Usage(800, 1026, 1826, None, "0.00040832")
    assert ledger.complete(reserved.attempt_id, good_response(usage=usage), schedule, now=1001) == "accounting_failed"
    snapshot = ledger.snapshot()
    assert snapshot["stop_reason"] == "usage_or_pricing_mismatch"
    assert snapshot["spent_picos"] == 0 and snapshot["reserved_picos"] == schedule.reservation_picos
    assert ledger.db.execute("SELECT state,has_response FROM attempts").fetchone() == ("returned_quarantined", 1)


@pytest.mark.parametrize("reported_input,expected", [(2976, "returned"), (2977, "accounting_failed")])
def test_combined_reported_usage_obeys_declared_context(ledger, reported_input, expected):
    schedule = replace(price(), max_context_tokens=4000)
    candidate = request(schedule=schedule)
    reserved = ledger.reserve(candidate, schedule, now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    usage = Usage(reported_input, 1024, reported_input + 1024, None, "0")
    assert ledger.complete(reserved.attempt_id, good_response(usage=usage), schedule, now=1001) == expected
    if expected == "accounting_failed":
        assert ledger.snapshot()["stop_reason"] == "usage_or_pricing_mismatch"
        assert ledger.snapshot()["reserved_picos"] == schedule.reservation_picos
        assert ledger.db.execute("SELECT state,has_response FROM main.attempts").fetchone() == (
            "returned_quarantined", 1
        )
    else:
        assert ledger.snapshot()["stop_reason"] is None and ledger.snapshot()["reserved_picos"] == 0


def test_reconciled_combined_usage_over_context_is_quarantined(ledger):
    schedule = replace(price(), max_context_tokens=4000)
    reserved = ledger.reserve(request(schedule=schedule), schedule, now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.complete(reserved.attempt_id, replace(good_response(), usage=None), schedule, now=1001) == "unknown_usage"
    usage = Usage(2977, 1024, 4001, None, "0")
    assert ledger.reconcile_response(reserved.attempt_id, usage, schedule, evidence_sha256="e" * 64,
                                     now=1002) == "accounting_failed"
    assert ledger.snapshot()["stop_reason"] == "usage_or_pricing_mismatch"
    assert ledger.snapshot()["reserved_picos"] == schedule.reservation_picos


def test_atomic_concurrent_reservations_do_not_exceed_budget():
    with tempfile.TemporaryDirectory(prefix="followup-account-") as directory:
        path = str(Path(directory) / "account.sqlite")
        a = sqlite3.connect(path, check_same_thread=False)
        b = sqlite3.connect(path, check_same_thread=False)
        one, two = AccountingLedger(a, cap_usd="0.06", max_retries=0), AccountingLedger(b, cap_usd="0.06", max_retries=0)
        barrier = threading.Barrier(2)
        results = []
        failures = []
        def reserve(account, req, schedule):
            try:
                barrier.wait()
                results.append(account.reserve(req, schedule, now=1000))
            except Exception as error:
                failures.append(type(error).__name__)
        threads = [threading.Thread(target=reserve, args=(one, request(), price())),
                   threading.Thread(target=reserve, args=(two, request("N2", model=DEEPSEEK), price(DEEPSEEK)))]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        assert not failures
        assert sorted(result.status for result in results) == ["blocked", "reserved"]
        assert next(result.reason for result in results if result.status == "blocked") == "cap_blocked"
        snapshot = one.snapshot()
        assert snapshot["reserved_picos"] <= snapshot["cap_picos"]
        assert snapshot["http_attempts"] == 0
        a.close()
        b.close()


def test_sequential_model_and_at_most_two_reservations(ledger):
    one = ledger.reserve(request("N1"), price(), now=1000)
    second_same = ledger.reserve(request("N2"), price(), now=1000)
    other = ledger.reserve(request("N3", model=DEEPSEEK), price(DEEPSEEK), now=1000)
    assert one.status == other.status == "reserved"
    assert second_same.reason == "model_busy"
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos + price(DEEPSEEK).reservation_picos


def test_unsent_reservation_can_be_cancelled_without_an_http_attempt(ledger):
    req = request()
    one = ledger.reserve(req, price(), now=1000)
    ledger.cancel_unsent(one.attempt_id, now=1000)
    assert ledger.snapshot()["http_attempts"] == 0 and ledger.snapshot()["reserved_picos"] == 0
    again = ledger.reserve(req, price(), now=1001)
    assert again.status == "reserved" and again.attempt_index == 1
    ledger.mark_sent(again.attempt_id, now=1001)
    with pytest.raises(ValueError, match="unsent"):
        ledger.cancel_unsent(again.attempt_id, now=1001)


def test_mock_runner_releases_its_unsent_reservation_when_dispatch_is_fenced(ledger, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(ledger, "mark_sent", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("synthetic fence")))
    outcome = run_mock(request(), price(), ledger, ScriptedTransport([good_response()]),
                       clock=clock.now, sleep=clock.sleep)
    assert outcome.status == "blocked" and outcome.reason == "dispatch_fenced"
    assert ledger.snapshot()["http_attempts"] == ledger.snapshot()["reserved_picos"] == 0


def test_restart_preserves_potential_charge_and_requires_evidence_before_retry():
    with tempfile.TemporaryDirectory(prefix="followup-restart-") as directory:
        path = str(Path(directory) / "account.sqlite")
        c1 = sqlite3.connect(path)
        before = AccountingLedger(c1, max_retries=1)
        req = request()
        reserved = before.reserve(req, price(), now=1000)
        before.mark_sent(reserved.attempt_id, now=1000)
        c1.close()
        c2 = sqlite3.connect(path)
        after = AccountingLedger(c2, max_retries=1)
        assert after.snapshot()["http_attempts"] == 1
        assert after.snapshot()["recovery_required"] is True
        assert after.reserve(request("N2"), price(), now=1001).reason == "recovery_required"
        with pytest.raises(ValueError, match="absence"):
            after.recover_interrupted(confirmed_no_active_workers=False, now=1010)
        assert after.recover_interrupted(confirmed_no_active_workers=True, now=1010) == 1
        assert after.snapshot()["stop_reason"] == "unknown_charge"
        assert after.reserve(request("N2"), price(), now=1011).reason == "account_stopped"
        assert after.snapshot()["spent_picos"] == 0 and after.snapshot()["reserved_picos"] > 0
        after.reconcile_transport(reserved.attempt_id, billed_usd="0", evidence_sha256="e" * 64, now=1011)
        assert after.snapshot()["stop_reason"] is None
        assert after.reserve(req, price(), now=1069).reason == "request_not_retryable"
        after.confirm_no_response(reserved.attempt_id, evidence_sha256="f" * 64, now=1069)
        assert after.reserve(req, price(), now=1069).reason == "retry_delay"
        second = after.reserve(req, price(), now=1070)
        assert second.status == "reserved" and second.attempt_index == 2
        c2.close()


def test_billing_evidence_alone_never_proves_that_no_response_was_returned(ledger):
    candidate = request()
    reserved = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.fail_transport(reserved.attempt_id, TransportFailure("transport", "0", "e" * 64),
                                 now=1001) == "response_status_unknown"
    assert ledger.reserve(candidate, price(), now=1100).reason == "request_not_retryable"
    ledger.confirm_no_response(reserved.attempt_id, evidence_sha256="f" * 64, now=1100)
    with pytest.raises(ValueError, match="prior recorded event"):
        ledger.reserve(candidate, price(), now=1059)
    assert ledger.reserve(candidate, price(), now=1100).status == "reserved"
    with pytest.raises(ValueError, match="ambiguous"):
        ledger.confirm_no_response(reserved.attempt_id, evidence_sha256="f" * 64, now=1100)


def test_unknown_usage_stops_and_reconciliation_preserves_returned_content(ledger):
    req, schedule = request(), price()
    reserve = ledger.reserve(req, schedule, now=1000)
    ledger.mark_sent(reserve.attempt_id, now=1000)
    response = replace(good_response(), usage=None, content="not json")
    assert ledger.complete(reserve.attempt_id, response, schedule, now=1001) == "unknown_usage"
    assert ledger.snapshot()["stop_reason"] == "unknown_usage"
    assert ledger.snapshot()["reserved_picos"] > 0
    assert ledger.reserve(request("N2"), schedule, now=1002).reason == "account_stopped"
    assert ledger.reconcile_response(reserve.attempt_id, Usage(800, 10, 810, 2, "0.00008"), schedule,
                                     evidence_sha256="e" * 64, now=1002) == "returned"
    assert ledger.snapshot()["stop_reason"] is None and ledger.snapshot()["reserved_picos"] == 0
    cached = ledger.reserve(req, schedule, now=1003)
    assert cached.status == "cached" and cached.content == "not json"
    assert parse_natural(cached.content, "Fictional", finish_reason=cached.finish_reason).status is ParseStatus.INVALID_JSON


@pytest.mark.parametrize("usage", [
    Usage(800, 1025, 1825, None, "0"),
    Usage(4001, 10, 4011, None, "0"),
    Usage(800, 10, 810, None, "1"),
])
def test_provider_limit_or_price_inconsistency_stops_account(ledger, usage):
    req, schedule = request(), price()
    reservation = ledger.reserve(req, schedule, now=1000)
    ledger.mark_sent(reservation.attempt_id, now=1000)
    result = ledger.complete(reservation.attempt_id, good_response(usage=usage), schedule, now=1001)
    assert result == "accounting_failed"
    assert ledger.snapshot()["stop_reason"] == "usage_or_pricing_mismatch"
    assert ledger.reserve(request("N2"), schedule, now=1002).reason == "account_stopped"


def test_subpicodollar_price_mismatch_is_not_hidden_by_rounded_accounting(ledger):
    schedule = replace(price(), request_fee_usd="0.0000000000001")
    candidate = request(schedule=schedule)
    reserved = ledger.reserve(candidate, schedule, now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    usage = Usage(0, 0, 0, None, "0.0000000000009")
    assert schedule.upper_picos(0, 0) == 1
    assert ledger.complete(reserved.attempt_id, good_response(usage=usage), schedule, now=1001) == "accounting_failed"
    assert ledger.snapshot()["spent_picos"] == 0 and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.db.execute("SELECT billed FROM attempts").fetchone() == (1,)
    assert ledger.snapshot()["stop_reason"] == "usage_or_pricing_mismatch"


def test_bad_or_unknown_usage_never_counts_as_zero(ledger):
    req = request()
    reservation = ledger.reserve(req, price(), now=1000)
    ledger.mark_sent(reservation.attempt_id, now=1000)
    invalid = Usage(800, 10, 811, 11, "0")
    assert ledger.complete(reservation.attempt_id, good_response(usage=invalid), price(), now=1001) == "unknown_usage"
    assert ledger.snapshot()["spent_picos"] == 0 and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.reconcile_response(reservation.attempt_id, invalid, price(), evidence_sha256="e" * 64,
                                     now=1002) == "account_stopped"


def test_route_mismatch_stops_only_that_model_after_charge_reconciliation(ledger):
    req, clock = request(), Clock()
    response = replace(good_response(), provider_route="another/route")
    result = run_mock(req, price(), ledger, ScriptedTransport([response]), clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "route_mismatch"
    assert ledger.snapshot()["spent_picos"] > 0 and ledger.snapshot()["stop_reason"] is None
    assert ledger.reserve(request("N2"), price(), now=1001).reason == "model_stopped"
    assert ledger.reserve(request("N3", model=DEEPSEEK), price(DEEPSEEK), now=1001).status == "reserved"


def test_429_with_unknown_charge_never_retries_or_assumes_free(ledger):
    req, clock = request(), Clock()
    transport = ScriptedTransport([TransportFailure("rate_limit")])
    result = run_mock(req, price(), ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "unknown_charge"
    assert len(transport.payloads) == 1 and clock.sleeps == []
    assert ledger.snapshot()["stop_reason"] == "unknown_charge"
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos


def test_unexpected_transport_exception_stops_with_unknown_charge(ledger):
    req, clock = request(), Clock()
    result = run_mock(req, price(), ledger, ScriptedTransport([]), clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "unknown_charge"
    assert ledger.snapshot()["http_attempts"] == 1
    assert ledger.snapshot()["stop_reason"] == "unknown_charge"
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos


@pytest.mark.parametrize("content", [None, "\ud800"])
def test_unpersistable_returned_content_is_terminal_and_never_retried(ledger, content):
    candidate, clock = request(), Clock()
    transport = ScriptedTransport([replace(good_response(), content=content)])
    result = run_mock(candidate, price(), ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "returned_unpersistable"
    assert ledger.snapshot()["http_attempts"] == 1 and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.snapshot()["stop_reason"] == "returned_unpersistable"
    assert ledger.reserve(candidate, price(), now=1060).reason == "account_stopped"
    assert len(transport.payloads) == 1


def test_exception_after_return_is_recorded_as_response_not_transport(ledger, monkeypatch):
    candidate, clock = request(), Clock()
    monkeypatch.setattr(ledger, "complete", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic")))
    transport = ScriptedTransport([good_response()])
    result = run_mock(candidate, price(), ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "returned_unpersistable"
    assert ledger.snapshot()["stop_reason"] == "returned_unpersistable"
    attempt_id, has_response = ledger.db.execute("SELECT attempt_id,has_response FROM attempts").fetchone()
    assert has_response == 1
    assert ledger.reconcile_response(attempt_id, Usage(800, 10, 810, None, "0.00008"), price(),
                                     evidence_sha256="e" * 64, now=1001) == "account_stopped"
    assert ledger.reserve(candidate, price(), now=1060).reason == "account_stopped"
    assert len(transport.payloads) == 1


def test_one_identical_retry_after_exact_delay_then_stop_model(ledger):
    req, clock = request(), Clock()
    transport = ScriptedTransport([TransportFailure("rate_limit", "0", "e" * 64, "a" * 64),
                                   TransportFailure("transport", "0", "f" * 64, "b" * 64)])
    result = run_mock(req, price(), ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "unavailable"
    assert clock.sleeps == [60] and transport.payloads == [req.payload, req.payload]
    assert all(json.loads(payload)["provider"]["data_collection"] == "deny" for payload in transport.payloads)
    assert ledger.snapshot()["http_attempts"] == 2
    assert ledger.reserve(request("N2"), price(), now=clock.now()).reason == "model_stopped"


def test_returned_malformed_or_truncated_content_is_not_repaired_or_retried(ledger):
    req, clock = request(), Clock()
    response = good_response(content="{", finish="length")
    transport = ScriptedTransport([response])
    result = run_mock(req, price(), ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert result.status == "returned" and result.content == "{" and len(transport.payloads) == 1
    assert parse_natural(result.content, "Fictional", finish_reason=result.finish_reason).status is ParseStatus.TRUNCATED
    assert clock.sleeps == []


def test_attempt_ceiling_and_cache_do_not_count_blocked_requests():
    connection = sqlite3.connect(":memory:")
    account = AccountingLedger(connection, max_attempts=1, max_retries=0)
    clock = Clock()
    first = request()
    assert run_mock(first, price(), account, ScriptedTransport([good_response()]),
                    clock=clock.now, sleep=clock.sleep).status == "returned"
    assert run_mock(first, price(), account, ScriptedTransport([]),
                    clock=clock.now, sleep=clock.sleep).from_cache
    assert account.reserve(request("N2"), price(), now=1001).reason == "attempt_limit"
    assert account.snapshot()["http_attempts"] == 1
    connection.close()


def test_existing_unknown_database_or_changed_account_policy_is_refused():
    foreign = sqlite3.connect(":memory:")
    foreign.execute("CREATE TABLE unrelated (value TEXT)")
    foreign.commit()
    with pytest.raises(ValueError, match="unrecognized"):
        AccountingLedger(foreign, max_retries=0)
    assert foreign.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("unrelated",)]
    foreign.close()
    connection = sqlite3.connect(":memory:")
    AccountingLedger(connection, cap_usd="1", max_retries=0)
    with pytest.raises(ValueError, match="policy differs"):
        AccountingLedger(connection, cap_usd="2", max_retries=0)
    connection.close()


@pytest.mark.parametrize("kind", ["table", "trigger"])
def test_unexpected_sqlite_x_named_main_object_is_not_treated_as_internal(kind):
    connection = sqlite3.connect(":memory:")
    AccountingLedger(connection, max_retries=0)
    if kind == "table":
        connection.execute("CREATE TABLE main.sqliteXunexpected (value INTEGER)")
    else:
        connection.execute("CREATE TRIGGER main.sqliteXunexpected AFTER INSERT ON events BEGIN SELECT 1; END")
    with pytest.raises(ValueError, match="schema"):
        AccountingLedger(connection, max_retries=0)
    connection.close()


def test_sqlite_x_named_object_does_not_make_a_nonempty_v0_database_look_empty():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE main.sqliteXunexpected (value INTEGER)")
    with pytest.raises(ValueError, match="unrecognized"):
        AccountingLedger(connection, max_retries=0)
    assert connection.execute("SELECT name FROM main.sqlite_master WHERE type='table'").fetchall() == [
        ("sqliteXunexpected",)
    ]
    connection.close()


def test_schema_filter_does_not_trust_a_caller_overridden_sql_function():
    connection = sqlite3.connect(":memory:")
    AccountingLedger(connection, max_retries=0)
    connection.execute("CREATE TABLE main.sqliteXunexpected (value INTEGER)")
    connection.create_function("substr", 3, lambda *_: "sqlite_")
    with pytest.raises(ValueError, match="schema"):
        AccountingLedger(connection, max_retries=0)
    connection.close()


def test_post_initialization_unexpected_main_trigger_fences_existing_connections():
    uri = "file:synthetic-main-schema-change?mode=memory&cache=shared"
    a, b = sqlite3.connect(uri, uri=True), sqlite3.connect(uri, uri=True)
    worker, standby = AccountingLedger(a, max_retries=0), AccountingLedger(b, max_retries=0)
    a.execute("CREATE TRIGGER main.sqliteXunexpected BEFORE UPDATE ON account BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(ValueError, match="changed main schema"):
        worker.reserve(request(), price(), now=1000)
    assert a.execute("PRAGMA main.user_version").fetchone() == (2_147_483_647,)
    assert a.execute("SELECT attempts,spent FROM main.account").fetchone() == (0, 0)
    with pytest.raises(ValueError, match="fenced or unrecognized"):
        standby.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1000)
    a.close()
    b.close()


def test_retry_policy_must_be_explicit():
    connection = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="explicit shared retry"):
        AccountingLedger(connection)
    assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    connection.close()


def test_missing_account_row_or_retry_index_never_resets_existing_accounting():
    connection = sqlite3.connect(":memory:")
    ledger = AccountingLedger(connection, max_attempts=1, max_retries=0)
    clock = Clock()
    assert run_mock(request(), price(), ledger, ScriptedTransport([good_response()]),
                    clock=clock.now, sleep=clock.sleep).status == "returned"
    attempts = connection.execute("SELECT attempt_id,billed FROM attempts").fetchall()
    connection.execute("DELETE FROM account")
    with pytest.raises(ValueError, match="refusing to reset"):
        AccountingLedger(connection, max_attempts=1, max_retries=0)
    assert connection.execute("SELECT attempt_id,billed FROM attempts").fetchall() == attempts
    assert connection.execute("SELECT * FROM account").fetchall() == []
    connection.close()

    connection = sqlite3.connect(":memory:")
    AccountingLedger(connection, max_retries=0)
    connection.execute("DROP INDEX one_active_attempt_index")
    with pytest.raises(ValueError, match="retry index"):
        AccountingLedger(connection, max_retries=0)
    connection.close()


def test_snapshot_uses_one_database_transaction():
    connection = sqlite3.connect(":memory:")
    ledger = AccountingLedger(connection, max_retries=0)
    states = []
    connection.set_trace_callback(lambda query: states.append(connection.in_transaction)
                                  if query.startswith("SELECT") else None)
    ledger.snapshot()
    connection.set_trace_callback(None)
    assert states and all(states)
    connection.close()


def test_concurrent_snapshot_cannot_mix_pre_and_post_settlement():
    with tempfile.TemporaryDirectory(prefix="followup-snapshot-") as directory:
        path = str(Path(directory) / "account.sqlite")
        writer_db = sqlite3.connect(path, check_same_thread=False)
        reader_db = sqlite3.connect(path, check_same_thread=False)
        writer = AccountingLedger(writer_db, max_retries=0)
        reader = AccountingLedger(reader_db, max_retries=0)
        reserved = writer.reserve(request(), price(), now=1000)
        writer.mark_sent(reserved.attempt_id, now=1000)
        before = reader.snapshot()
        reached, writer_started = threading.Event(), threading.Event()
        def trace(query):
            if query.startswith("SELECT reserved FROM main.attempts"):
                reached.set()
                if not writer_started.wait(timeout=5):
                    raise RuntimeError("synthetic writer did not start")
        reader_db.set_trace_callback(trace)
        snapshots, failures = [], []
        def read_snapshot():
            try:
                snapshots.append(reader.snapshot())
            except Exception as error:
                failures.append(type(error).__name__)
        def settle():
            if not reached.wait(timeout=5):
                failures.append("reader_not_started")
                return
            writer_started.set()
            try:
                writer.complete(reserved.attempt_id, good_response(), price(), now=1001)
            except Exception as error:
                failures.append(type(error).__name__)
        threads = [threading.Thread(target=read_snapshot), threading.Thread(target=settle)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        reader_db.set_trace_callback(None)
        assert not failures and all(not thread.is_alive() for thread in threads)
        after = reader.snapshot()
        assert snapshots == [before]
        assert before["spent_picos"] == 0 and before["reserved_picos"] > 0
        assert after["spent_picos"] > 0 and after["reserved_picos"] == 0
        writer_db.close()
        reader_db.close()


def test_same_connection_snapshot_waits_for_the_owning_transaction():
    db = sqlite3.connect(":memory:", check_same_thread=False)
    ledger = AccountingLedger(db, max_retries=0)
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    entered, release, reader_started, reader_done = (threading.Event() for _ in range(4))
    snapshots, failures = [], []

    def writer():
        try:
            with ledger._transaction():
                db.execute("UPDATE main.account SET spent=1 WHERE id=1")
                entered.set()
                if not release.wait(timeout=5):
                    raise RuntimeError("synthetic reader did not release")
                db.execute("UPDATE main.attempts SET state='returned' WHERE attempt_id=?", (attempt.attempt_id,))
        except Exception as error:
            failures.append(type(error).__name__)

    def reader():
        reader_started.set()
        try:
            snapshots.append(ledger.snapshot())
        except Exception as error:
            failures.append(type(error).__name__)
        finally:
            reader_done.set()

    write_thread = threading.Thread(target=writer)
    read_thread = threading.Thread(target=reader)
    write_thread.start()
    try:
        assert entered.wait(timeout=5)
        read_thread.start()
        assert reader_started.wait(timeout=5)
        assert not reader_done.wait(timeout=.05)
    finally:
        release.set()
        write_thread.join(timeout=5)
        if read_thread.ident is not None:
            read_thread.join(timeout=5)
    assert not failures and not write_thread.is_alive() and not read_thread.is_alive()
    assert (snapshots[0]["spent_picos"], snapshots[0]["reserved_picos"]) == (1, 0)
    db.close()


def test_known_charge_outside_the_integer_range_stops_and_keeps_the_reservation(ledger):
    candidate = request()
    reserved = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    failure = TransportFailure("transport", "9000001", "e" * 64, "f" * 64)
    assert ledger.fail_transport(reserved.attempt_id, failure, now=1001) == "account_stopped"
    snapshot = ledger.snapshot()
    assert snapshot["stop_reason"] == "charge_out_of_range" and snapshot["reserved_picos"] > 0
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"


def test_dispatch_failure_and_recovery_timestamps_cannot_move_backward(ledger):
    candidate = request()
    reserved = ledger.reserve(candidate, price(), now=1000)
    for now in (True, -1, 999, 2**63):
        with pytest.raises(ValueError):
            ledger.mark_sent(reserved.attempt_id, now=now)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.fail_transport(reserved.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                 now=1001) == "retry_after_delay"
    assert ledger.reserve(candidate, price(), now=1001).reason == "retry_delay"
    assert ledger.reserve(candidate, price(), now=1061).status == "reserved"


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_legacy_account_schema_is_refused_without_migration(version):
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE account (id INTEGER PRIMARY KEY, cap INTEGER)")
    connection.execute("INSERT INTO account VALUES (1, 42)")
    connection.execute(f"PRAGMA user_version = {version}")
    connection.commit()
    with pytest.raises(ValueError, match="schema"):
        AccountingLedger(connection, max_retries=0)
    assert connection.execute("PRAGMA user_version").fetchone() == (version,)
    assert connection.execute("SELECT * FROM account").fetchall() == [(1, 42)]
    connection.close()


def test_retry_policy_is_persistent_and_cannot_be_changed_on_reopen():
    connection = sqlite3.connect(":memory:")
    first = AccountingLedger(connection, max_attempts=5, max_retries=1)
    assert first.snapshot()["retry_limit"] == 1
    assert AccountingLedger(connection, max_attempts=5, max_retries=1).snapshot() == first.snapshot()
    with pytest.raises(ValueError, match="policy differs"):
        AccountingLedger(connection, max_attempts=5, max_retries=2)
    with pytest.raises(ValueError, match="retry ceiling"):
        AccountingLedger(sqlite3.connect(":memory:"), max_attempts=5, max_retries=6)
    with pytest.raises(ValueError, match="retry ceiling"):
        AccountingLedger(sqlite3.connect(":memory:"), max_attempts=5, max_retries=True)
    connection.close()


def test_shared_retry_quota_keeps_capacity_for_new_first_attempts():
    connection = sqlite3.connect(":memory:")
    ledger = AccountingLedger(connection, max_attempts=3, max_retries=0)
    clock = Clock()
    transport = ScriptedTransport([TransportFailure("rate_limit", "0", "e" * 64, "a" * 64)])
    result = run_mock(request("N1"), price(), ledger, transport, clock=clock.now, sleep=clock.sleep)
    assert result.status == "blocked" and result.reason == "retry_budget"
    assert len(transport.payloads) == 1
    assert ledger.snapshot()["retry_attempts"] == 0
    next_result = run_mock(request("N2"), price(), ledger, ScriptedTransport([good_response()]),
                           clock=clock.now, sleep=clock.sleep)
    assert next_result.status == "returned" and ledger.snapshot()["http_attempts"] == 2
    connection.close()


def test_cancelled_retry_reservation_does_not_consume_the_quota():
    connection = sqlite3.connect(":memory:")
    ledger = AccountingLedger(connection, max_attempts=4, max_retries=1)
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64, "a" * 64),
                                 now=1001) == "retry_after_delay"
    retry = ledger.reserve(request(), price(), now=1061)
    assert retry.status == "reserved" and ledger.snapshot()["retry_pending"] == 1
    ledger.cancel_unsent(retry.attempt_id, now=1061)
    assert ledger.snapshot()["retry_pending"] == ledger.snapshot()["retry_attempts"] == 0
    again = ledger.reserve(request(), price(), now=1062)
    assert again.status == "reserved" and again.attempt_index == 2
    ledger.mark_sent(again.attempt_id, now=1062)
    assert ledger.snapshot()["retry_pending"] == 0 and ledger.snapshot()["retry_attempts"] == 1
    connection.close()


def test_sent_retry_stays_counted_across_restart_and_reconciliation():
    with tempfile.TemporaryDirectory(prefix="followup-retry-restart-") as directory:
        path = str(Path(directory) / "account.sqlite")
        connection = sqlite3.connect(path)
        before = AccountingLedger(connection, max_attempts=10, max_retries=1)
        req = request()
        first = before.reserve(req, price(), now=1000)
        before.mark_sent(first.attempt_id, now=1000)
        before.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64, "a" * 64), now=1001)
        retry = before.reserve(req, price(), now=1061)
        before.mark_sent(retry.attempt_id, now=1061)
        connection.close()

        connection = sqlite3.connect(path)
        after = AccountingLedger(connection, max_attempts=10, max_retries=1)
        assert after.snapshot()["retry_attempts"] == 1
        assert after.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1062).reason == "recovery_required"
        assert after.recover_interrupted(confirmed_no_active_workers=True, now=1062) == 1
        after.reconcile_transport(retry.attempt_id, billed_usd="0", evidence_sha256="f" * 64, now=1062)
        assert after.snapshot()["retry_attempts"] == 1
        other, schedule = request("N2", model=DEEPSEEK), price(DEEPSEEK)
        new = after.reserve(other, schedule, now=1063)
        assert new.status == "reserved"
        after.mark_sent(new.attempt_id, now=1063)
        after.fail_transport(new.attempt_id, TransportFailure("transport", "0", "e" * 64, "a" * 64), now=1064)
        assert after.reserve(other, schedule, now=1124).reason == "retry_budget"
        connection.close()


def test_concurrent_retry_reservations_share_one_atomic_quota():
    with tempfile.TemporaryDirectory(prefix="followup-retries-") as directory:
        path = str(Path(directory) / "account.sqlite")
        a = sqlite3.connect(path, check_same_thread=False)
        b = sqlite3.connect(path, check_same_thread=False)
        one = AccountingLedger(a, max_attempts=10, max_retries=1)
        two = AccountingLedger(b, max_attempts=10, max_retries=1)
        requests = (request("N1"), request("N2", model=DEEPSEEK))
        schedules = (price(), price(DEEPSEEK))
        for index, (account, req, schedule) in enumerate(zip((one, two), requests, schedules)):
            started = 1000 + 2 * index
            reservation = account.reserve(req, schedule, now=started)
            account.mark_sent(reservation.attempt_id, now=started)
            assert account.fail_transport(reservation.attempt_id, TransportFailure("transport", "0", "e" * 64, "a" * 64),
                                          now=started + 1) == "retry_after_delay"
        barrier, results, failures = threading.Barrier(2), [], []

        def reserve(account, req, schedule):
            try:
                barrier.wait()
                results.append(account.reserve(req, schedule, now=1063))
            except Exception as error:
                failures.append(type(error).__name__)

        threads = [threading.Thread(target=reserve, args=(one, requests[0], schedules[0])),
                   threading.Thread(target=reserve, args=(two, requests[1], schedules[1]))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert not failures
        assert sorted(result.status for result in results) == ["blocked", "reserved"]
        assert next(result.reason for result in results if result.status == "blocked") == "retry_budget"
        assert one.snapshot()["retry_pending"] == 1 and one.snapshot()["retry_attempts"] == 0
        a.close()
        b.close()


def test_cap_rounds_down_and_tiny_cost_rounds_up_exactly():
    connection = sqlite3.connect(":memory:")
    ledger = AccountingLedger(connection, cap_usd="0.000000000001999999999999999999", max_retries=0)
    assert ledger.snapshot()["cap_picos"] == 1
    assert ledger.reserve(request(), price(), now=1000).reason == "cap_blocked"
    with pytest.raises(ValueError, match="below one picodollar"):
        AccountingLedger(sqlite3.connect(":memory:"), cap_usd="0.0000000000009", max_retries=0)
    tiny_fee = replace(price(), request_fee_usd="0.000000000001000000000000000000000000000001")
    assert tiny_fee.upper_picos(0, 0) == 2
    connection.close()


def test_twenty_returned_pilot_responses_per_model_are_the_ceiling(ledger):
    clock = Clock()
    for i in range(20):
        outcome = run_mock(request(f"P{i}", cohort="pilot"), price(), ledger,
                           ScriptedTransport([good_response(content="{}")]),
                           clock=clock.now, sleep=clock.sleep)
        assert outcome.status == "returned"
    blocked = ledger.reserve(request("P20", cohort="pilot"), price(), now=clock.now())
    assert blocked.reason == "pilot_return_limit"
    assert ledger.snapshot()["http_attempts"] == 20


@pytest.mark.parametrize("first_resolution", ["transport", "response"])
def test_concurrent_unknown_charges_cannot_clear_account_early(ledger, first_resolution):
    first, second = request(), request("N2", model=DEEPSEEK)
    a, b = ledger.reserve(first, price(), now=1000), ledger.reserve(second, price(DEEPSEEK), now=1000)
    ledger.mark_sent(a.attempt_id, now=1000)
    with pytest.raises(ValueError, match="fences dispatch"):
        ledger.mark_sent(b.attempt_id, now=1000)
    # Exercise reconciliation defensively for an invented inconsistent database
    # with two sent attempts; the public mock API no longer permits this state.
    ledger.db.execute("UPDATE attempts SET state='sent' WHERE attempt_id=?", (b.attempt_id,))
    ledger.db.execute("UPDATE account SET attempts=attempts+1 WHERE id=1")
    assert ledger.fail_transport(a.attempt_id, TransportFailure("transport"), now=1001) == "unknown_charge"
    response = replace(good_response(DEEPSEEK), usage=None)
    assert ledger.complete(b.attempt_id, response, price(DEEPSEEK), now=1001) == "unknown_usage"
    times = iter((1002, 1003))
    def transport():
        ledger.reconcile_transport(a.attempt_id, billed_usd="0", evidence_sha256="e" * 64, now=next(times))
    def returned():
        ledger.reconcile_response(b.attempt_id, Usage(800, 10, 810, None, "0.0001"),
                                  price(DEEPSEEK), evidence_sha256="f" * 64, now=next(times))
    operations = (transport, returned) if first_resolution == "transport" else (returned, transport)
    operations[0]()
    assert ledger.snapshot()["stop_reason"] is not None
    operations[1]()
    assert ledger.snapshot()["stop_reason"] is None


def test_reconciling_other_unknown_cannot_clear_a_quarantined_claim(ledger):
    a = ledger.reserve(request(), price(), now=1000)
    b = ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1000)
    ledger.mark_sent(a.attempt_id, now=1000)
    ledger.db.execute("UPDATE attempts SET state='sent' WHERE attempt_id=?", (b.attempt_id,))
    ledger.db.execute("UPDATE account SET attempts=attempts+1 WHERE id=1")
    assert ledger.fail_transport(a.attempt_id, TransportFailure("transport"), now=1001) == "unknown_charge"
    bad = good_response(DEEPSEEK, usage=Usage(800, 10, 810, None, "9000001"))
    assert ledger.complete(b.attempt_id, bad, price(DEEPSEEK), now=1001) == "unknown_usage"
    ledger.reconcile_transport(a.attempt_id, billed_usd="0", evidence_sha256="e" * 64, now=1002)
    assert ledger.snapshot()["stop_reason"] == "invalid_usage"
    assert ledger.snapshot()["reserved_picos"] == price(DEEPSEEK).reservation_picos
    assert ledger.reserve(request("N3"), price(), now=1003).reason == "account_stopped"


def test_late_return_after_known_failure_preserves_both_claims_without_double_charge():
    uri = "file:synthetic-late-return?mode=memory&cache=shared"
    first_db = sqlite3.connect(uri, uri=True)
    second_db = sqlite3.connect(uri, uri=True)
    first, second = AccountingLedger(first_db, max_retries=1), AccountingLedger(second_db, max_retries=1)
    attempt = first.reserve(request(), price(), now=1000)
    first.mark_sent(attempt.attempt_id, now=1000)
    assert first.fail_transport(attempt.attempt_id, TransportFailure("transport", "0.001", "e" * 64, "f" * 64),
                                now=1001) == "retry_after_delay"
    assert first.snapshot()["spent_picos"] == 1_000_000_000 and first.snapshot()["reserved_picos"] == 0
    late = good_response(content="invented late response")
    assert first.complete(attempt.attempt_id, late, price(), now=1002) == "account_stopped"
    state, has_response, billed, original = first_db.execute(
        "SELECT state,has_response,billed,charge_claim FROM main.attempts WHERE attempt_id=?", (attempt.attempt_id,)
    ).fetchone()
    assert (state, has_response, billed) == ("returned_quarantined", 1, 1_000_000_000)
    assert json.loads(original)["prefix"] == "0.001"
    kind, claim, content = first_db.execute(
        "SELECT kind,charge_claim,response_content_claim FROM main.incidents"
    ).fetchone()
    assert kind == "late_returned" and json.loads(claim)["prefix"] == "0.00008"
    assert json.loads(content)["prefix"] == "invented late response"
    assert second.snapshot()["spent_picos"] == 1_000_000_000
    assert second.snapshot()["reserved_picos"] == price().reservation_picos
    assert second.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"
    assert first.complete(attempt.attempt_id, late, price(), now=1003) == "account_stopped"
    assert first.snapshot()["spent_picos"] == 1_000_000_000
    assert first.snapshot()["reserved_picos"] == price().reservation_picos
    assert first_db.execute("SELECT COUNT(*) FROM main.incidents").fetchone() == (2,)
    first_db.close()
    second_db.close()


def test_concurrent_duplicate_returns_settle_once_and_stop_with_exposure():
    with tempfile.TemporaryDirectory(prefix="followup-late-race-") as directory:
        path = str(Path(directory) / "account.sqlite")
        a = sqlite3.connect(path, check_same_thread=False)
        b = sqlite3.connect(path, check_same_thread=False)
        first, second = AccountingLedger(a, max_retries=0), AccountingLedger(b, max_retries=0)
        attempt = first.reserve(request(), price(), now=1000)
        first.mark_sent(attempt.attempt_id, now=1000)
        barrier, results, failures = threading.Barrier(2), [], []

        def settle(ledger, content):
            try:
                barrier.wait()
                results.append(ledger.complete(attempt.attempt_id, good_response(content=content), price(), now=1001))
            except Exception as error:
                failures.append(type(error).__name__)

        threads = [threading.Thread(target=settle, args=(first, "invented-a")),
                   threading.Thread(target=settle, args=(second, "invented-b"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert not failures and all(not thread.is_alive() for thread in threads)
        assert sorted(results) == ["account_stopped", "returned"]
        assert first.snapshot()["spent_picos"] == 80_000_000
        assert first.snapshot()["reserved_picos"] == price().reservation_picos
        assert first.snapshot()["stop_reason"] == "conflicting_outcome"
        assert a.execute("SELECT COUNT(*) FROM main.incidents").fetchone() == (1,)
        a.close()
        b.close()


def test_second_conflicting_transport_reconciliation_preserves_prior_and_new_evidence(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    assert ledger.fail_transport(attempt.attempt_id, TransportFailure("transport"), now=1001) == "unknown_charge"
    ledger.reconcile_transport(attempt.attempt_id, billed_usd="0.001", evidence_sha256="e" * 64,
                               no_response_evidence_sha256="f" * 64, now=1002)
    assert ledger.snapshot()["spent_picos"] == 1_000_000_000 and ledger.snapshot()["stop_reason"] is None
    ledger.reconcile_transport(attempt.attempt_id, billed_usd="0.002", evidence_sha256="a" * 64,
                               no_response_evidence_sha256="b" * 64, now=1003)
    row = ledger.db.execute("SELECT state,billed,charge_claim,evidence_sha256,no_response_evidence_sha256 "
                            "FROM main.attempts").fetchone()
    assert row[:2] == ("failed_quarantined", 1_000_000_000)
    assert json.loads(row[2])["prefix"] == "0.001" and row[3:] == ("e" * 64, "f" * 64)
    claim, billing, no_response = ledger.db.execute(
        "SELECT charge_claim,billing_evidence_claim,no_response_evidence_claim FROM main.incidents"
    ).fetchone()
    assert json.loads(claim)["prefix"] == "0.002"
    assert json.loads(billing)["prefix"] == "a" * 64 and json.loads(no_response)["prefix"] == "b" * 64
    assert ledger.snapshot()["spent_picos"] == 1_000_000_000
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1004).reason == "account_stopped"


def test_second_conflicting_response_reconciliation_does_not_double_charge(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    assert ledger.complete(attempt.attempt_id, replace(good_response(), usage=None), price(), now=1001) == "unknown_usage"
    assert ledger.reconcile_response(attempt.attempt_id, Usage(800, 10, 810, None, "0.00008"), price(),
                                     evidence_sha256="e" * 64, now=1002) == "returned"
    assert ledger.reconcile_response(attempt.attempt_id, Usage(800, 10, 810, None, "0.00009"), price(),
                                     evidence_sha256="f" * 64, now=1003) == "account_stopped"
    assert ledger.snapshot()["spent_picos"] == 80_000_000
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    claim, evidence = ledger.db.execute("SELECT charge_claim,billing_evidence_claim FROM main.incidents").fetchone()
    assert json.loads(claim)["prefix"] == "0.00009" and json.loads(evidence)["prefix"] == "f" * 64


def test_late_transport_charge_after_return_keeps_original_spend_and_response(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    assert ledger.complete(attempt.attempt_id, good_response(), price(), now=1001) == "returned"
    assert ledger.fail_transport(attempt.attempt_id, TransportFailure("transport", "0.001", "e" * 64, "f" * 64),
                                 now=1002) == "account_stopped"
    assert ledger.snapshot()["spent_picos"] == 80_000_000
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    assert ledger.db.execute("SELECT state,has_response FROM main.attempts").fetchone() == ("returned_quarantined", 1)
    kind, claim = ledger.db.execute("SELECT kind,charge_claim FROM main.incidents").fetchone()
    assert kind == "late_transport_failure" and json.loads(claim)["prefix"] == "0.001"


def test_late_return_stops_when_retry_is_already_sent_and_retains_both_exposures(ledger):
    candidate = request()
    first = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                 now=1001) == "retry_after_delay"
    retry = ledger.reserve(candidate, price(), now=1061)
    ledger.mark_sent(retry.attempt_id, now=1061)
    assert ledger.complete(first.attempt_id, good_response(), price(), now=1062) == "account_stopped"
    assert ledger.snapshot()["reserved_picos"] == 2 * price().reservation_picos
    assert ledger.complete(retry.attempt_id, good_response(), price(), now=1063) == "returned"
    assert ledger.snapshot()["spent_picos"] == 80_000_000
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1064).reason == "account_stopped"


def test_late_return_for_cancelled_reservation_adds_exposure_only_once(ledger):
    candidate = request()
    first = ledger.reserve(candidate, price(), now=1000)
    ledger.cancel_unsent(first.attempt_id, now=1000)
    replacement = ledger.reserve(candidate, price(), now=1001)
    assert replacement.status == "reserved" and replacement.attempt_index == 1
    assert ledger.complete(first.attempt_id, good_response(), price(), now=1002) == "account_stopped"
    assert ledger.complete(first.attempt_id, good_response(), price(), now=1003) == "account_stopped"
    assert ledger.snapshot()["spent_picos"] == 0
    assert ledger.snapshot()["reserved_picos"] == 2 * price().reservation_picos
    assert ledger.snapshot()["marked_sent_attempts"] == ledger.snapshot()["http_attempts"] == 0
    assert ledger.snapshot()["http_attempts_unverified"] is True
    assert ledger.db.execute("SELECT SUM(exposure) FROM main.incidents").fetchone() == (price().reservation_picos,)
    with pytest.raises(ValueError, match="cannot dispatch"):
        ledger.mark_sent(replacement.attempt_id, now=1003)


@pytest.mark.parametrize("cancelled", [False, True])
def test_unmarked_transport_outcome_makes_attempt_count_unverified(ledger, cancelled):
    attempt = ledger.reserve(request(), price(), now=1000)
    assert ledger.snapshot()["http_attempts_unverified"] is False
    if cancelled:
        ledger.cancel_unsent(attempt.attempt_id, now=1000)
    assert ledger.fail_transport(
        attempt.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64), now=1001
    ) == "account_stopped"
    state = ledger.snapshot()
    assert state["marked_sent_attempts"] == state["http_attempts"] == 0
    assert state["http_attempts_unverified"] is True and state["stop_reason"] == "conflicting_outcome"
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"


def test_unmarked_outcome_with_failed_incident_storage_fences_schema(ledger, monkeypatch):
    attempt = ledger.reserve(request(), price(), now=1000)
    monkeypatch.setattr(ledger, "_late_conflict", lambda *args, **kwargs: (
        _ for _ in ()).throw(sqlite3.OperationalError("synthetic incident failure")))
    assert ledger.complete(attempt.attempt_id, good_response(), price(), now=1001) == "account_stopped"
    with pytest.raises(ValueError, match="fenced or unrecognized"):
        ledger.snapshot()
    with pytest.raises(ValueError, match="fenced or unrecognized"):
        ledger.mark_sent(attempt.attempt_id, now=1002)


def test_incident_exposure_sum_uses_exact_integer_arithmetic(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    # Invented database values exercise a boundary unreachable under the $10 cap.
    for exposure in (SQLITE_INT_MAX, 1):
        ledger.db.execute(
            "INSERT INTO main.incidents(attempt_id,request_id,kind,prior_state,exposure) VALUES (?,?,?,?,?)",
            (attempt.attempt_id, request().request_id, "synthetic", "cancelled", exposure),
        )
    ledger.db.execute("UPDATE main.account SET stop_reason='synthetic_stop' WHERE id=1")
    assert ledger.snapshot()["reserved_picos"] == SQLITE_INT_MAX + 1 + price().reservation_picos
    assert type(ledger.snapshot()["reserved_picos"]) is int


def test_late_return_with_backdated_timestamp_still_stops_and_records_claim(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    assert ledger.fail_transport(attempt.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                 now=1001) == "retry_after_delay"
    assert ledger.complete(attempt.attempt_id, good_response(), price(), now=999) == "account_stopped"
    observed, claim = ledger.db.execute("SELECT observed_at,charge_claim FROM main.incidents").fetchone()
    assert observed is None and json.loads(claim)["prefix"] == "0.00008"
    assert ledger.snapshot()["stop_reason"] == "conflicting_outcome" and ledger.snapshot()["reserved_picos"] > 0


def test_late_return_preserves_bounded_malformed_charge_and_content(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    assert ledger.fail_transport(attempt.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                 now=1001) == "retry_after_delay"
    late = good_response(content="x" * 129, usage=Usage(800, 10, 810, None, "1e10000"))
    assert ledger.complete(attempt.attempt_id, late, price(), now=1002) == "account_stopped"
    charge, content = ledger.db.execute("SELECT charge_claim,response_content_claim FROM main.incidents").fetchone()
    assert json.loads(charge)["prefix"] == "1e10000"
    content_record = json.loads(content)
    assert content_record["length"] == 129 and content_record["truncated"] is True
    assert content_record["prefix"] == "x" * MAX_MONEY_LENGTH
    assert ledger.snapshot()["spent_picos"] == 0 and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.snapshot()["exposure_unknown"] is True


def test_larger_late_charge_raises_exposure_without_double_counting(ledger):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    assert ledger.fail_transport(attempt.attempt_id, TransportFailure("transport", "0.001", "e" * 64, "f" * 64),
                                 now=1001) == "retry_after_delay"
    first = good_response(usage=Usage(800, 10, 810, None, "0.5"))
    second = good_response(usage=Usage(800, 10, 810, None, "0.7"))
    assert ledger.complete(attempt.attempt_id, first, price(), now=1002) == "account_stopped"
    assert ledger.snapshot()["reserved_picos"] == 500_000_000_000
    assert ledger.complete(attempt.attempt_id, second, price(), now=1003) == "account_stopped"
    snapshot = ledger.snapshot()
    assert snapshot["reserved_picos"] == 700_000_000_000 and snapshot["spent_picos"] == 1_000_000_000
    assert snapshot["exposure_unknown"] is True and snapshot["stop_reason"] == "conflicting_outcome"


@pytest.mark.parametrize("operation", ["return", "transport_reconciliation", "response_reconciliation"])
def test_late_incident_persistence_failure_still_stops_and_preserves_claim(ledger, monkeypatch, operation):
    attempt = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(attempt.attempt_id, now=1000)
    if operation == "response_reconciliation":
        assert ledger.complete(attempt.attempt_id, good_response(), price(), now=1001) == "returned"
        expected_spent, claim = 80_000_000, "0.00009"
    else:
        assert ledger.fail_transport(attempt.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                     now=1001) == "retry_after_delay"
        expected_spent = 0
        claim = "0.00008" if operation == "return" else "0.001"
    monkeypatch.setattr(ledger, "_late_conflict", lambda *args, **kwargs: (
        _ for _ in ()).throw(sqlite3.OperationalError("synthetic incident failure")))
    if operation == "return":
        assert ledger.complete(attempt.attempt_id, good_response(), price(), now=1002) == "account_stopped"
    elif operation == "transport_reconciliation":
        ledger.reconcile_transport(attempt.attempt_id, billed_usd=claim, evidence_sha256="a" * 64,
                                   no_response_evidence_sha256="b" * 64, now=1002)
    else:
        assert ledger.reconcile_response(attempt.attempt_id, Usage(800, 10, 810, None, claim), price(),
                                         evidence_sha256="a" * 64, now=1002) == "account_stopped"
    assert ledger.snapshot()["stop_reason"] == "persistence_failure"
    assert ledger.snapshot()["spent_picos"] == expected_spent
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    codes = [row[0] for row in ledger.db.execute("SELECT code FROM main.events ORDER BY sequence")]
    fallback = next(code for code in codes if code.startswith("observation:"))
    assert json.loads(json.loads(fallback.removeprefix("observation:"))["charge_claim"])["prefix"] == claim
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1003).reason == "account_stopped"


def test_late_cancelled_attempt_with_failed_incident_storage_fences_schema(ledger, monkeypatch):
    first = ledger.reserve(request(), price(), now=1000)
    ledger.cancel_unsent(first.attempt_id, now=1000)
    assert ledger.reserve(request(), price(), now=1001).status == "reserved"
    monkeypatch.setattr(ledger, "_late_conflict", lambda *args, **kwargs: (
        _ for _ in ()).throw(sqlite3.OperationalError("synthetic incident failure")))
    assert ledger.complete(first.attempt_id, good_response(), price(), now=1002) == "account_stopped"
    assert ledger.db.execute("PRAGMA main.user_version").fetchone() == (2_147_483_647,)
    assert ledger.db.execute("SELECT spent,stop_reason FROM main.account").fetchone() == (0, "persistence_failure")
    codes = [row[0] for row in ledger.db.execute("SELECT code FROM main.events ORDER BY sequence")]
    fallback = next(code for code in codes if code.startswith("observation:"))
    assert json.loads(json.loads(fallback.removeprefix("observation:"))["charge_claim"])["prefix"] == "0.00008"
    with pytest.raises(ValueError, match="fenced or unrecognized"):
        ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1003)


@pytest.mark.parametrize("value", ["1e10000", "1e-10000", "1e++1", "1e65", "1e-65", "9" * 129])
def test_monetary_syntax_and_exponents_are_bounded_before_fraction(value, monkeypatch):
    schedule = price()
    with monkeypatch.context() as patch:
        patch.setattr(execution, "Fraction", lambda *_: (_ for _ in ()).throw(AssertionError("fraction used")))
        with pytest.raises(ValueError):
            replace(schedule, prompt_usd_per_token=value)


def test_token_request_and_script_sizes_are_bounded_before_use():
    with pytest.raises(ValueError, match="context"):
        replace(price(), max_context_tokens=2**63)
    with pytest.raises(ValueError, match="billable-output"):
        replace(price(), max_billable_output_tokens=2**63)
    with pytest.raises(ValueError, match="SQLite-range"):
        price().upper_usd(2**63, 0)
    with pytest.raises(ValueError, match="byte-safety"):
        request(notice="x" * (MAX_REQUEST_CHARS + 1))
    with pytest.raises(ValueError, match="outcome bound"):
        ScriptedTransport(itertools.repeat(good_response()))


def test_bounded_scientific_notation_remains_usable(ledger):
    schedule = replace(price(), prompt_usd_per_token="1e-7", completion_usd_per_token="3.2e-7",
                       independent_charge_ceiling_usd="2e-2")
    candidate = request(schedule=schedule)
    first = ledger.reserve(candidate, schedule, now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    response = good_response(usage=Usage(800, 10, 810, None, "8e-5"))
    assert ledger.complete(first.attempt_id, response, schedule, now=1001) == "returned"
    assert ledger.snapshot()["spent_picos"] == 80_000_000


@pytest.mark.parametrize("claim", ["9000001", "1e10000", "1e-10000", "1e++1", "x" * 129,
                                     "\ud800", "\U0001f642" * 129])
def test_bad_transport_claim_is_preserved_and_cannot_be_reconciled_to_zero(ledger, claim):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.fail_transport(reserved.attempt_id, TransportFailure("transport", claim, "e" * 64, "f" * 64),
                                 now=1001) == "account_stopped"
    state, stored, evidence = ledger.db.execute(
        "SELECT state,charge_claim,evidence_sha256 FROM attempts WHERE attempt_id=?", (reserved.attempt_id,)
    ).fetchone()
    record = json.loads(stored)
    assert state == "failed_quarantined" and evidence == "e" * 64
    assert record["length"] == len(claim) and record["prefix"] == claim[:MAX_MONEY_LENGTH]
    assert record["truncated"] is (len(claim) > MAX_MONEY_LENGTH) and len(stored) < 2048
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    ledger.reconcile_transport(reserved.attempt_id, billed_usd="0", evidence_sha256="e" * 64, now=1002)
    assert json.loads(ledger.db.execute("SELECT charge_claim FROM main.incidents").fetchone()[0])["prefix"] == "0"
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"


@pytest.mark.parametrize("claim", ["9000001", "1e10000", "1e-10000", "1e++1", "\ud800"])
def test_bad_returned_charge_is_preserved_and_zero_correction_fails_closed(ledger, claim):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    response = good_response(usage=Usage(800, 10, 810, None, claim))
    assert ledger.complete(reserved.attempt_id, response, price(), now=1001) == "unknown_usage"
    state, has_response, stored = ledger.db.execute(
        "SELECT state,has_response,charge_claim FROM attempts WHERE attempt_id=?", (reserved.attempt_id,)
    ).fetchone()
    assert state == "returned_quarantined" and has_response == 1
    assert json.loads(stored)["prefix"] == claim
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    assert ledger.reconcile_response(reserved.attempt_id, Usage(800, 10, 810, None, "0"), price(),
                                     evidence_sha256="e" * 64, now=1002) == "account_stopped"
    assert ledger.snapshot()["stop_reason"] == "invalid_usage"
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"


def test_quarantined_charge_and_reservation_remain_immutable_after_restart():
    with tempfile.TemporaryDirectory(prefix="followup-claim-restart-") as directory:
        path = str(Path(directory) / "account.sqlite")
        db = sqlite3.connect(path)
        before = AccountingLedger(db, max_retries=0)
        reserved = before.reserve(request(), price(), now=1000)
        before.mark_sent(reserved.attempt_id, now=1000)
        response = good_response(usage=Usage(800, 10, 810, None, "9000001"))
        assert before.complete(reserved.attempt_id, response, price(), now=1001) == "unknown_usage"
        db.close()
        db = sqlite3.connect(path)
        after = AccountingLedger(db, max_retries=0)
        assert after.snapshot()["stop_reason"] == "invalid_usage"
        assert after.snapshot()["reserved_picos"] == price().reservation_picos
        assert json.loads(db.execute("SELECT charge_claim FROM attempts").fetchone()[0])["prefix"] == "9000001"
        assert after.reconcile_response(reserved.attempt_id, Usage(800, 10, 810, None, "0"), price(),
                                        evidence_sha256="e" * 64, now=1002) == "account_stopped"
        assert after.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"
        db.close()


def test_bounded_conversion_failure_after_dispatch_is_quarantined(ledger, monkeypatch):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    failure = TransportFailure("transport", "1e-40", "e" * 64, "f" * 64)
    with monkeypatch.context() as patch:
        patch.setattr(execution, "Fraction", lambda *_: (_ for _ in ()).throw(MemoryError("synthetic")))
        assert ledger.fail_transport(reserved.attempt_id, failure, now=1001) == "account_stopped"
    assert ledger.snapshot()["stop_reason"] == "invalid_charge"
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    assert json.loads(ledger.db.execute("SELECT charge_claim FROM attempts").fetchone()[0])["prefix"] == "1e-40"
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"


def test_bounded_conversion_failure_after_return_records_response_and_claim(ledger, monkeypatch):
    schedule = price()
    reserved = ledger.reserve(request(), schedule, now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    response = good_response()
    with monkeypatch.context() as patch:
        patch.setattr(execution, "Fraction", lambda *_: (_ for _ in ()).throw(MemoryError("synthetic")))
        assert ledger.complete(reserved.attempt_id, response, schedule, now=1001) == "account_stopped"
    state, returned, claim = ledger.db.execute("SELECT state,has_response,charge_claim FROM attempts").fetchone()
    assert state == "returned_quarantined" and returned == 1 and json.loads(claim)["prefix"] == "0.00008"
    assert ledger.snapshot()["stop_reason"] == "invalid_response_or_pricing"
    assert ledger.snapshot()["reserved_picos"] > 0


def test_unknown_usage_reconciliation_with_bad_charge_is_permanently_quarantined(ledger):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.complete(reserved.attempt_id, replace(good_response(), usage=None), price(), now=1001) == "unknown_usage"
    assert ledger.reconcile_response(reserved.attempt_id, Usage(800, 10, 810, None, "9000001"), price(),
                                     evidence_sha256="e" * 64, now=1002) == "unknown_usage"
    assert ledger.snapshot()["reserved_picos"] > 0 and ledger.snapshot()["stop_reason"] == "invalid_usage"
    assert ledger.reconcile_response(reserved.attempt_id, Usage(800, 10, 810, None, "0"), price(),
                                     evidence_sha256="f" * 64, now=1003) == "account_stopped"


def test_malformed_usage_mapping_preserves_its_charge_claim(ledger):
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    response = replace(good_response(), usage={"billed_usd": "9000001"})
    assert ledger.complete(first.attempt_id, response, price(), now=1001) == "unknown_usage"
    state, claim = ledger.db.execute("SELECT state,charge_claim FROM attempts").fetchone()
    assert state == "returned_quarantined" and json.loads(claim)["prefix"] == "9000001"
    assert ledger.snapshot()["stop_reason"] == "invalid_usage" and ledger.snapshot()["reserved_picos"] > 0


def test_raw_malformed_scripted_response_retains_claim_after_dispatch(ledger):
    clock = Clock()
    result = run_mock(request(), price(), ledger, ScriptedTransport([{"usage": {"billed_usd": "9000001"}}]),
                      clock=clock.now, sleep=clock.sleep)
    assert result.status == "unavailable" and result.reason == "account_stopped"
    state, has_response, claim = ledger.db.execute("SELECT state,has_response,charge_claim FROM attempts").fetchone()
    assert state == "returned_quarantined" and has_response == 1 and json.loads(claim)["prefix"] == "9000001"
    assert ledger.snapshot()["stop_reason"] == "invalid_response_or_pricing" and ledger.snapshot()["reserved_picos"] > 0


def test_raw_malformed_transport_failure_retains_claim_after_dispatch(ledger):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    failure = {"billed_usd": "1e10000", "evidence_sha256": "e" * 64}
    assert ledger.fail_transport(reserved.attempt_id, failure, now=1001) == "account_stopped"
    state, claim = ledger.db.execute("SELECT state,charge_claim FROM attempts").fetchone()
    assert state == "failed_quarantined" and json.loads(claim)["prefix"] == "1e10000"
    assert ledger.snapshot()["stop_reason"] == "invalid_transport_evidence" and ledger.snapshot()["reserved_picos"] > 0


@pytest.mark.parametrize("kind", ["transport", "response"])
def test_malformed_reconciliation_evidence_preserves_the_charge_claim(ledger, kind):
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    if kind == "transport":
        assert ledger.fail_transport(first.attempt_id, TransportFailure("transport"), now=1001) == "unknown_charge"
        ledger.reconcile_transport(first.attempt_id, billed_usd="9000001", evidence_sha256="invalid", now=1002)
        expected = "failed_quarantined"
    else:
        assert ledger.complete(first.attempt_id, replace(good_response(), usage=None), price(),
                               now=1001) == "unknown_usage"
        assert ledger.reconcile_response(first.attempt_id, Usage(800, 10, 810, None, "9000001"), price(),
                                         evidence_sha256="invalid", now=1002) == "account_stopped"
        expected = "returned_quarantined"
    state, claim = ledger.db.execute("SELECT state,charge_claim FROM attempts").fetchone()
    assert state == expected and json.loads(claim)["prefix"] == "9000001"
    assert ledger.snapshot()["stop_reason"] is not None and ledger.snapshot()["reserved_picos"] > 0


def test_aggregate_integer_overflow_stops_without_real_promotion(ledger):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    # Synthetic inconsistent accumulated spend exercises the overflow guard.
    ledger.db.execute("UPDATE account SET spent=? WHERE id=1", (SQLITE_INT_MAX - 1,))
    failure = TransportFailure("transport", "0.000000000002", "e" * 64, "f" * 64)
    assert ledger.fail_transport(reserved.attempt_id, failure, now=1001) == "account_stopped"
    spent, kind = ledger.db.execute("SELECT spent,typeof(spent) FROM account").fetchone()
    assert spent == SQLITE_INT_MAX - 1 and kind == "integer"
    assert ledger.snapshot()["stop_reason"] == "aggregate_out_of_range"
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos
    assert ledger.db.execute("SELECT state,billed FROM attempts").fetchone() == ("failed_quarantined", 2)


def test_two_in_range_outlier_claims_never_promote_aggregate_or_release_reservations(ledger):
    a = ledger.reserve(request(), price(), now=1000)
    b = ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1000)
    ledger.mark_sent(a.attempt_id, now=1000)
    # Synthetic inconsistent state tests the guard even though public dispatch
    # now permits only one sent attempt at a time.
    ledger.db.execute("UPDATE attempts SET state='sent' WHERE attempt_id=?", (b.attempt_id,))
    ledger.db.execute("UPDATE account SET attempts=attempts+1 WHERE id=1")
    failure = TransportFailure("transport", "8999999.999999999000", "e" * 64, "f" * 64)
    assert ledger.fail_transport(a.attempt_id, failure, now=1001) == "account_stopped"
    assert ledger.fail_transport(b.attempt_id, failure, now=1002) == "account_stopped"
    assert ledger.db.execute("SELECT spent,typeof(spent) FROM account").fetchone() == (0, "integer")
    assert ledger.snapshot()["reserved_picos"] == price().reservation_picos + price(DEEPSEEK).reservation_picos
    assert ledger.db.execute("SELECT COUNT(*) FROM attempts WHERE state='failed_quarantined'").fetchone() == (2,)


@pytest.mark.parametrize("bad_now", [True, -1, 999, 2**63])
def test_bad_failure_timestamp_after_dispatch_stops_and_retains_claim(ledger, bad_now):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    failure = TransportFailure("transport", "0", "e" * 64, "f" * 64)
    assert ledger.fail_transport(reserved.attempt_id, failure, now=bad_now) == "account_stopped"
    assert ledger.snapshot()["stop_reason"] == "invalid_timestamp" and ledger.snapshot()["reserved_picos"] > 0
    state, finished, claim = ledger.db.execute("SELECT state,finished,charge_claim FROM attempts").fetchone()
    assert state == "failed_quarantined" and finished is None and json.loads(claim)["prefix"] == "0"
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1001).reason == "account_stopped"


@pytest.mark.parametrize("bad_now", [True, -1, 999, 2**63])
def test_bad_return_timestamp_records_response_and_stops(ledger, bad_now):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.complete(reserved.attempt_id, good_response(), price(), now=bad_now) == "account_stopped"
    state, has_response, finished = ledger.db.execute("SELECT state,has_response,finished FROM attempts").fetchone()
    assert (state, has_response, finished) == ("returned_quarantined", 1, None)
    assert ledger.snapshot()["stop_reason"] == "invalid_timestamp" and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1001).reason == "account_stopped"


def test_invalid_recovery_time_is_a_persistent_stop(ledger):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.recover_interrupted(confirmed_no_active_workers=True, now=999) == 1
    assert ledger.snapshot()["stop_reason"] == "invalid_timestamp" and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.db.execute("SELECT state,finished FROM attempts").fetchone() == ("failed_quarantined", None)


@pytest.mark.parametrize("operation", ["confirm", "transport", "response"])
def test_bad_evidence_time_after_dispatch_quarantines(operation):
    db = sqlite3.connect(":memory:")
    ledger = AccountingLedger(db, max_retries=1)
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    if operation == "confirm":
        assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64),
                                     now=1001) == "response_status_unknown"
        ledger.confirm_no_response(first.attempt_id, evidence_sha256="f" * 64, now=999)
        expected = "failed_quarantined"
    elif operation == "transport":
        assert ledger.fail_transport(first.attempt_id, TransportFailure("transport"), now=1001) == "unknown_charge"
        ledger.reconcile_transport(first.attempt_id, billed_usd="0", evidence_sha256="e" * 64, now=2**63)
        expected = "failed_quarantined"
    else:
        assert ledger.complete(first.attempt_id, replace(good_response(), usage=None), price(), now=1001) == "unknown_usage"
        assert ledger.reconcile_response(first.attempt_id, Usage(800, 10, 810, None, "0.00008"), price(),
                                         evidence_sha256="e" * 64, now=999) == "account_stopped"
        expected = "returned_quarantined"
    assert ledger.db.execute("SELECT state FROM attempts").fetchone() == (expected,)
    assert ledger.snapshot()["stop_reason"] == "invalid_timestamp" and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"
    db.close()


def test_out_of_range_returned_usage_and_large_content_stop_before_sqlite_binding(ledger):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    response = good_response(usage=Usage(2**63, 0, 2**63, None, "0"))
    assert ledger.complete(reserved.attempt_id, response, price(), now=1001) == "unknown_usage"
    assert ledger.db.execute("SELECT state,has_response FROM attempts").fetchone() == ("returned_quarantined", 1)
    assert ledger.snapshot()["stop_reason"] == "invalid_usage" and ledger.snapshot()["reserved_picos"] > 0

    other_db = sqlite3.connect(":memory:")
    other = AccountingLedger(other_db, max_retries=0)
    reservation = other.reserve(request(), price(), now=1000)
    other.mark_sent(reservation.attempt_id, now=1000)
    assert other.complete(reservation.attempt_id, good_response(content="x" * (MAX_RESPONSE_CHARS + 1)),
                          price(), now=1001) == "returned_unpersistable"
    assert other.snapshot()["stop_reason"] == "returned_unpersistable" and other.snapshot()["reserved_picos"] > 0
    other_db.close()


def test_sqlite_range_usage_still_stops_at_the_study_token_limit(ledger):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    response = good_response(usage=Usage(SQLITE_INT_MAX, 0, SQLITE_INT_MAX, None, "0"))
    assert ledger.complete(reserved.attempt_id, response, price(), now=1001) == "accounting_failed"
    assert ledger.snapshot()["stop_reason"] == "usage_or_pricing_mismatch"
    assert ledger.snapshot()["reserved_picos"] > 0


@pytest.mark.parametrize("finish", ["\ud800", "x" * 1025, 42])
def test_unpersistable_response_metadata_is_not_silently_discarded(ledger, finish):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    assert ledger.complete(reserved.attempt_id, good_response(finish=finish), price(),
                           now=1001) == "returned_unpersistable"
    assert ledger.snapshot()["stop_reason"] == "returned_unpersistable" and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.db.execute("SELECT state,has_response FROM attempts").fetchone() == ("returned_quarantined", 1)


@pytest.mark.parametrize("field,value", [("model_id", None), ("provider_route", "\ud800"),
                                          ("precision", "x" * 1025)])
def test_unknown_served_route_is_quarantined_instead_of_misclassified(ledger, field, value):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    response = replace(good_response(), **{field: value})
    assert ledger.complete(reserved.attempt_id, response, price(), now=1001) == "route_unknown"
    assert ledger.snapshot()["stop_reason"] == "route_unknown" and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.db.execute("SELECT COUNT(*) FROM model_stops").fetchone() == (0,)


@pytest.mark.parametrize("outcome", ["returned", "transport"])
def test_mock_clock_regression_after_dispatch_fails_closed(ledger, outcome):
    ticks = iter((1000, 1000, 999))
    scripted = good_response() if outcome == "returned" else TransportFailure("transport", "0", "e" * 64, "f" * 64)
    result = run_mock(request(), price(), ledger, ScriptedTransport([scripted]), clock=lambda: next(ticks))
    assert result.status == "unavailable" and result.reason == "account_stopped"
    state, has_response = ledger.db.execute("SELECT state,has_response FROM attempts").fetchone()
    assert state == ("returned_quarantined" if outcome == "returned" else "failed_quarantined")
    assert has_response == int(outcome == "returned")
    assert ledger.snapshot()["stop_reason"] == "invalid_timestamp" and ledger.snapshot()["reserved_picos"] > 0


def test_mock_clock_exception_after_return_fails_closed(ledger):
    ticks = iter((1000, 1000))
    result = run_mock(request(), price(), ledger, ScriptedTransport([good_response()]), clock=lambda: next(ticks))
    assert result.status == "unavailable" and result.reason == "account_stopped"
    assert ledger.db.execute("SELECT state,has_response FROM attempts").fetchone() == ("returned_quarantined", 1)
    assert ledger.snapshot()["stop_reason"] == "invalid_timestamp" and ledger.snapshot()["reserved_picos"] > 0


def test_retry_cannot_precede_later_event_or_no_response_evidence(ledger):
    candidate = request()
    first = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64),
                                 now=1001) == "response_status_unknown"
    assert ledger.reserve(candidate, price(), now=2000).reason == "request_not_retryable"
    ledger.confirm_no_response(first.attempt_id, evidence_sha256="f" * 64, now=2001)
    with pytest.raises(ValueError, match="prior recorded event"):
        ledger.reserve(candidate, price(), now=1061)
    retry = ledger.reserve(candidate, price(), now=2001)
    assert retry.status == "reserved" and retry.attempt_index == 2
    assert ledger.db.execute("SELECT billing_at,no_response_at FROM attempts WHERE attempt_id=?",
                             (first.attempt_id,)).fetchone() == (1001, 2001)
    timestamps = [row[0] for row in ledger.db.execute("SELECT timestamp FROM events ORDER BY sequence")]
    assert timestamps == sorted(timestamps)


def test_retry_delay_is_from_failure_not_a_new_delay_after_evidence(ledger):
    candidate = request()
    first = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64),
                                 now=1001) == "response_status_unknown"
    ledger.confirm_no_response(first.attempt_id, evidence_sha256="f" * 64, now=1061)
    assert ledger.reserve(candidate, price(), now=1061).status == "reserved"


def test_reconciled_billing_and_nonreturn_times_gate_retry(ledger):
    candidate = request()
    first = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", no_response_evidence_sha256="f" * 64),
                                 now=1001) == "unknown_charge"
    ledger.reconcile_transport(first.attempt_id, billed_usd="0", evidence_sha256="e" * 64, now=2000)
    assert ledger.db.execute("SELECT billing_at,no_response_at FROM attempts WHERE attempt_id=?",
                             (first.attempt_id,)).fetchone() == (2000, 1001)
    with pytest.raises(ValueError, match="prior recorded event"):
        ledger.reserve(candidate, price(), now=1061)
    assert ledger.reserve(candidate, price(), now=2000).status == "reserved"


def test_billing_and_nonreturn_evidence_cannot_be_the_same_digest(ledger):
    db = sqlite3.connect(":memory:")
    other = AccountingLedger(db, max_retries=0)
    reserved = other.reserve(request(), price(), now=1000)
    other.mark_sent(reserved.attempt_id, now=1000)
    assert other.fail_transport(reserved.attempt_id, TransportFailure("transport", "0", "e" * 64, "e" * 64),
                                now=1001) == "account_stopped"
    assert other.snapshot()["stop_reason"] == "invalid_transport_evidence"
    assert other.snapshot()["reserved_picos"] > 0
    db.close()
    candidate = request()
    first = ledger.reserve(candidate, price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64),
                                 now=1001) == "response_status_unknown"
    ledger.confirm_no_response(first.attempt_id, evidence_sha256="e" * 64, now=1002)
    assert ledger.snapshot()["stop_reason"] == "invalid_no_response_evidence"
    assert ledger.snapshot()["reserved_picos"] > 0
    assert ledger.reserve(candidate, price(), now=1061).reason == "account_stopped"


def test_reconciliation_cannot_reuse_nonreturn_evidence_as_billing_evidence(ledger):
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, TransportFailure("transport", no_response_evidence_sha256="f" * 64),
                                 now=1001) == "unknown_charge"
    ledger.reconcile_transport(first.attempt_id, billed_usd="0", evidence_sha256="f" * 64, now=1002)
    assert ledger.snapshot()["stop_reason"] == "invalid_transport_evidence"
    assert ledger.snapshot()["reserved_picos"] > 0
    assert ledger.db.execute("SELECT state FROM attempts").fetchone() == ("failed_quarantined",)


@pytest.mark.parametrize("failure", [
    TransportFailure("transport", "9000001", "invalid", None),
    TransportFailure("transport", "1e++1", None, None),
    TransportFailure("not-a-kind", "9000001", "e" * 64, "f" * 64),
])
def test_malformed_failure_metadata_preserves_charge_and_stops(ledger, failure):
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    assert ledger.fail_transport(first.attempt_id, failure, now=1001) == "account_stopped"
    state, claim = ledger.db.execute("SELECT state,charge_claim FROM attempts").fetchone()
    assert state == "failed_quarantined" and json.loads(claim)["prefix"] == failure.billed_usd
    assert ledger.snapshot()["stop_reason"] == "invalid_transport_evidence"
    assert ledger.snapshot()["reserved_picos"] > 0


def test_nontext_large_charge_has_a_bounded_preserved_representation(ledger):
    first = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(first.attempt_id, now=1000)
    failure = TransportFailure("transport", 2**300, "e" * 64, "f" * 64)
    assert ledger.fail_transport(first.attempt_id, failure, now=1001) == "account_stopped"
    record = json.loads(ledger.db.execute("SELECT charge_claim FROM attempts").fetchone()[0])
    assert record["type"] == "int" and record["bits"] == 301 and len(record["leading_hex"]) < 40
    assert ledger.snapshot()["reserved_picos"] > 0 and ledger.snapshot()["stop_reason"] == "invalid_charge"


@pytest.mark.parametrize("route", ["failure", "reconciliation"])
def test_transport_charge_compares_exact_persisted_ceiling_not_rounded_picos(route):
    schedule = replace(price(), prompt_usd_per_token="1e-30", completion_usd_per_token="1e-30",
                       request_fee_usd="0.0000000000001", max_context_tokens=4000,
                       max_billable_output_tokens=1024, independent_charge_ceiling_usd="0.0000000000006")
    db = sqlite3.connect(":memory:")
    ledger = AccountingLedger(db, max_retries=1)
    first = ledger.reserve(request(schedule=schedule), schedule, now=1000)
    assert ledger.snapshot()["reserved_picos"] == 1
    assert db.execute("SELECT charge_ceiling_usd FROM attempts").fetchone() == ("0.0000000000006",)
    ledger.mark_sent(first.attempt_id, now=1000)
    if route == "failure":
        assert ledger.fail_transport(first.attempt_id,
                                     TransportFailure("transport", "0.0000000000009", "e" * 64, "f" * 64),
                                     now=1001) == "account_stopped"
    else:
        assert ledger.fail_transport(first.attempt_id, TransportFailure("transport"), now=1001) == "unknown_charge"
        ledger.reconcile_transport(first.attempt_id, billed_usd="0.0000000000009", evidence_sha256="e" * 64,
                                   no_response_evidence_sha256="f" * 64, now=1002)
    assert ledger.snapshot()["stop_reason"] == "charge_exceeded_ceiling"
    assert ledger.snapshot()["reserved_picos"] == 1 and ledger.snapshot()["spent_picos"] == 0
    assert db.execute("SELECT state,billed FROM attempts").fetchone() == ("failed_quarantined", 1)
    db.close()


def test_exact_transport_ceiling_survives_restart_before_reconciliation():
    schedule = replace(price(), prompt_usd_per_token="1e-30", completion_usd_per_token="1e-30",
                       request_fee_usd="0.0000000000001", max_context_tokens=4000,
                       max_billable_output_tokens=1024, independent_charge_ceiling_usd="0.0000000000006")
    with tempfile.TemporaryDirectory(prefix="followup-ceiling-restart-") as directory:
        path = str(Path(directory) / "account.sqlite")
        db = sqlite3.connect(path)
        before = AccountingLedger(db, max_retries=1)
        first = before.reserve(request(schedule=schedule), schedule, now=1000)
        before.mark_sent(first.attempt_id, now=1000)
        db.close()
        db = sqlite3.connect(path)
        after = AccountingLedger(db, max_retries=1)
        assert after.recover_interrupted(confirmed_no_active_workers=True, now=1001) == 1
        after.reconcile_transport(first.attempt_id, billed_usd="0.0000000000009", evidence_sha256="e" * 64,
                                  no_response_evidence_sha256="f" * 64, now=1002)
        assert db.execute("SELECT charge_ceiling_usd,state FROM attempts").fetchone() == (
            "0.0000000000006", "failed_quarantined"
        )
        assert after.snapshot()["stop_reason"] == "charge_exceeded_ceiling"
        assert after.snapshot()["reserved_picos"] == 1 and after.snapshot()["spent_picos"] == 0
        db.close()


def test_existing_connections_share_the_sent_fence_and_healthy_completion_clears_it():
    uri = "file:synthetic-shared-fence?mode=memory&cache=shared"
    a = sqlite3.connect(uri, uri=True)
    b = sqlite3.connect(uri, uri=True)
    first_ledger = AccountingLedger(a, max_retries=1)
    standby = AccountingLedger(b, max_retries=1)
    first = first_ledger.reserve(request(), price(), now=1000)
    pending = standby.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1000)
    first_ledger.mark_sent(first.attempt_id, now=1000)
    with pytest.raises(ValueError, match="fences dispatch"):
        standby.mark_sent(pending.attempt_id, now=1000)
    assert standby.reserve(request("N3", model=DEEPSEEK), price(DEEPSEEK), now=1001).reason == "recovery_required"
    a.close()  # invented crash; standby was opened before dispatch
    assert standby.snapshot()["recovery_required"]
    with pytest.raises(ValueError, match="absence"):
        standby.recover_interrupted(confirmed_no_active_workers=False, now=1001)
    assert standby.recover_interrupted(confirmed_no_active_workers=True, now=1001) == 1
    assert standby.snapshot()["stop_reason"] == "unknown_charge"
    standby.cancel_unsent(pending.attempt_id, now=1001)
    standby.reconcile_transport(first.attempt_id, billed_usd="0", evidence_sha256="e" * 64,
                                no_response_evidence_sha256="f" * 64, now=1002)
    assert standby.reserve(request(), price(), now=1061).status == "reserved"
    b.close()

    uri = "file:synthetic-healthy-fence?mode=memory&cache=shared"
    a = sqlite3.connect(uri, uri=True)
    worker = AccountingLedger(a, max_retries=0)
    first = worker.reserve(request(), price(), now=1000)
    worker.mark_sent(first.attempt_id, now=1000)
    b = sqlite3.connect(uri, uri=True)
    joining = AccountingLedger(b, max_retries=0)
    assert joining.snapshot()["recovery_required"]
    assert worker.complete(first.attempt_id, good_response(), price(), now=1001) == "returned"
    assert not joining.snapshot()["recovery_required"]
    assert joining.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).status == "reserved"
    a.close()
    b.close()


@pytest.mark.parametrize("before_initialization", [True, False])
def test_temp_account_and_attempt_shadows_cannot_change_main_accounting(before_initialization):
    uri = f"file:synthetic-temp-shadow-{int(before_initialization)}?mode=memory&cache=shared"
    a, b = sqlite3.connect(uri, uri=True), sqlite3.connect(uri, uri=True)

    def shadows():
        a.execute("CREATE TEMP TABLE account (id INTEGER,cap INTEGER,max_attempts INTEGER,max_retries INTEGER,"
                  "attempts INTEGER,spent INTEGER,stop_reason TEXT,last_time INTEGER)")
        a.execute("INSERT INTO temp.account VALUES (1,1,1400,0,0,0,NULL,0)")
        a.execute("CREATE TEMP TABLE attempts (attempt_id INTEGER,state TEXT,reserved INTEGER)")
        a.commit()

    if before_initialization:
        shadows()
    worker, standby = AccountingLedger(a, max_retries=0), AccountingLedger(b, max_retries=0)
    if not before_initialization:
        shadows()
    attempt = worker.reserve(request(), price(), now=1000)
    assert attempt.status == "reserved"
    worker.mark_sent(attempt.attempt_id, now=1000)
    assert standby.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1001).reason == "recovery_required"
    assert worker.complete(attempt.attempt_id, good_response(), price(), now=1001) == "returned"
    assert standby.snapshot()["spent_picos"] == 80_000_000
    assert a.execute("SELECT cap,attempts,spent FROM temp.account").fetchone() == (1, 0, 0)
    assert a.execute("SELECT COUNT(*) FROM temp.attempts").fetchone() == (0,)
    assert a.execute("SELECT attempts,spent FROM main.account").fetchone() == (1, 80_000_000)
    a.close()
    b.close()


def test_late_return_with_post_initialization_temp_shadows_still_stops_main_account():
    uri = "file:synthetic-temp-late?mode=memory&cache=shared"
    a, b = sqlite3.connect(uri, uri=True), sqlite3.connect(uri, uri=True)
    worker, standby = AccountingLedger(a, max_retries=1), AccountingLedger(b, max_retries=1)
    attempt = worker.reserve(request(), price(), now=1000)
    worker.mark_sent(attempt.attempt_id, now=1000)
    assert worker.fail_transport(attempt.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                 now=1001) == "retry_after_delay"
    for name in ("account", "attempts", "requests", "events", "incidents", "model_stops"):
        a.execute(f"CREATE TEMP TABLE {name} (marker TEXT)")
    assert worker.complete(attempt.attempt_id, good_response(), price(), now=1002) == "account_stopped"
    assert standby.snapshot()["stop_reason"] == "conflicting_outcome"
    assert standby.snapshot()["reserved_picos"] == price().reservation_picos
    assert standby.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"
    assert a.execute("SELECT COUNT(*) FROM main.incidents").fetchone() == (1,)
    assert a.execute("SELECT COUNT(*) FROM temp.incidents").fetchone() == (0,)
    a.close()
    b.close()


def test_preexisting_temp_trigger_is_refused_without_initializing_main():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TEMP TABLE scratch (value INTEGER)")
    connection.execute("CREATE TEMP TRIGGER scratch_trigger AFTER INSERT ON scratch BEGIN SELECT 1; END")
    with pytest.raises(ValueError, match="TEMP triggers"):
        AccountingLedger(connection, max_retries=0)
    assert connection.execute("PRAGMA main.user_version").fetchone() == (0,)
    assert connection.execute("SELECT name FROM main.sqlite_master WHERE type='table'").fetchall() == []
    assert connection.execute("SELECT COUNT(*) FROM temp.sqlite_master WHERE type='trigger'").fetchone() == (1,)
    connection.close()


def test_post_initialization_temp_trigger_fences_all_connections_without_firing_it():
    uri = "file:synthetic-temp-trigger?mode=memory&cache=shared"
    a, b = sqlite3.connect(uri, uri=True), sqlite3.connect(uri, uri=True)
    worker, standby = AccountingLedger(a, max_retries=0), AccountingLedger(b, max_retries=0)
    attempt = worker.reserve(request(), price(), now=1000)
    worker.mark_sent(attempt.attempt_id, now=1000)
    a.execute("CREATE TEMP TRIGGER block_account BEFORE UPDATE ON main.account BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(ValueError, match="TEMP triggers"):
        worker.complete(attempt.attempt_id, good_response(), price(), now=1001)
    assert a.execute("PRAGMA main.user_version").fetchone() == (2_147_483_647,)
    assert a.execute("SELECT state,reserved FROM main.attempts").fetchone() == ("sent", price().reservation_picos)
    with pytest.raises(ValueError, match="fenced or unrecognized"):
        standby.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1001)
    a.close()
    b.close()


@pytest.mark.parametrize("literal", ["can celled", "CANCELLED"])
def test_altered_index_literal_cannot_be_normalized_to_the_expected_predicate(literal):
    db = sqlite3.connect(":memory:")
    AccountingLedger(db, max_retries=0)
    db.execute("DROP INDEX one_active_attempt_index")
    db.execute("CREATE UNIQUE INDEX one_active_attempt_index ON attempts(request_id,attempt_index) "
               f"WHERE state != '{literal}'")
    with pytest.raises(ValueError, match="retry index"):
        AccountingLedger(db, max_retries=0)
    db.close()


def test_nondefault_sqlite_row_and_text_factories_are_refused_before_initialization():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    with pytest.raises(ValueError, match="row_factory"):
        AccountingLedger(db, max_retries=0)
    db.row_factory = None
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    db.text_factory = bytes
    with pytest.raises(ValueError, match="text_factory"):
        AccountingLedger(db, max_retries=0)
    db.close()


@pytest.mark.parametrize("outcome", ["returned", "transport"])
@pytest.mark.parametrize("error_type", [sqlite3.OperationalError, ValueError, MemoryError])
def test_post_dispatch_persistence_exception_quarantines_when_sqlite_recovers(ledger, monkeypatch, outcome, error_type):
    reserved = ledger.reserve(request(), price(), now=1000)
    ledger.mark_sent(reserved.attempt_id, now=1000)
    monkeypatch.setattr(ledger, "_add_spend", lambda *_: (_ for _ in ()).throw(error_type("synthetic")))
    if outcome == "returned":
        status = ledger.complete(reserved.attempt_id, good_response(), price(), now=1001)
    else:
        status = ledger.fail_transport(reserved.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64),
                                       now=1001)
    assert status == "account_stopped"
    state, has_response, claim = ledger.db.execute("SELECT state,has_response,charge_claim FROM attempts").fetchone()
    assert state == ("returned_quarantined" if outcome == "returned" else "failed_quarantined")
    assert has_response == int(outcome == "returned") and claim is not None
    assert ledger.snapshot()["stop_reason"] == "persistence_failure" and ledger.snapshot()["reserved_picos"] > 0
    assert ledger.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1002).reason == "account_stopped"


def test_failed_quarantine_write_leaves_a_shared_sent_fence(monkeypatch):
    uri = "file:synthetic-write-failure?mode=memory&cache=shared"
    a = sqlite3.connect(uri, uri=True)
    b = sqlite3.connect(uri, uri=True)
    worker = AccountingLedger(a, max_retries=0)
    standby = AccountingLedger(b, max_retries=0)
    first = worker.reserve(request(), price(), now=1000)
    worker.mark_sent(first.attempt_id, now=1000)
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic unavailable storage")
    monkeypatch.setattr(worker, "_add_spend", broken)
    monkeypatch.setattr(worker, "_record_post_dispatch_failure", broken)
    with pytest.raises(sqlite3.OperationalError, match="unavailable storage"):
        worker.fail_transport(first.attempt_id, TransportFailure("transport", "0", "e" * 64, "f" * 64), now=1001)
    assert standby.snapshot()["recovery_required"] and standby.snapshot()["reserved_picos"] > 0
    assert standby.reserve(request("N2", model=DEEPSEEK), price(DEEPSEEK), now=1001).reason == "recovery_required"
    a.close()
    b.close()
