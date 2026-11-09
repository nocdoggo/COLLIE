"""Invented-only tests for the counted, paced batch transport (A11)."""

from datetime import datetime, timezone
import json
import os
import stat
import threading

import httpx
import pytest

from analysis.coling.followup import oss_batch_transport as batch
from analysis.coling.followup import oss_one_shot_transport as one_shot


SELECTION = 'a1b2c3d4' * 8


def make_journal(tmp_path, *, mode=0o600, prelude=None, targets=10, max_sends=40):
    path = tmp_path / 'send.journal.jsonl'
    raw = prelude if prelude is not None else batch.batch_reservation_bytes(SELECTION, targets, max_sends)
    path.write_bytes(raw)
    os.chmod(path, mode)
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    return fd, path


def request_body(**overrides):
    body = {'model': batch.MODEL, 'messages': [{'role': 'user', 'content': 'SYNTHETIC PROMPT'}],
            'temperature': 0, 'provider': dict(batch.PROVIDER)}
    body.update(overrides)
    return json.dumps(body).encode()


def make_request(**overrides):
    return httpx.Request('POST', batch.URL, content=request_body(**overrides),
                         headers={'User-Agent': batch.USER_AGENT})


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class RecordingSleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


class MockInner(httpx.BaseTransport):
    def __init__(self, statuses=(200,)):
        self.statuses = list(statuses)
        self.seen = []
        self._lock = threading.Lock()

    def handle_request(self, request):
        with self._lock:
            self.seen.append(request)
        status = self.statuses.pop(0) if self.statuses else 200
        return httpx.Response(status, json={'synthetic': True})

    def close(self):
        pass


def make_transport(tmp_path, inner=None, *, max_sends=40, targets=10, stop=None, clock=None, sleep=None,
                   allowed=frozenset()):
    fd, path = make_journal(tmp_path, targets=targets, max_sends=max_sends)
    transport = batch.CountedPacedTransport(
        inner if inner is not None else MockInner(), fd, selection_sha256=SELECTION,
        planned_targets=targets, max_sends=max_sends, stop_after_utc=stop,
        clock=clock if clock is not None else FakeClock(), sleep=sleep if sleep is not None else RecordingSleep(),
        allowed_addresses=allowed)
    return transport, fd, path


def journal_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- validator -----------------------------------------------------------------------------

def test_validator_accepts_the_exact_dekallm_decoding():
    batch._validate(make_request())


@pytest.mark.parametrize('override', [
    {'model': 'openai/gpt-oss-20b-2020'},
    {'temperature': 1},
    {'temperature': 0.5},
    {'provider': {'order': ['deepinfra/bf16'], 'allow_fallbacks': False, 'quantizations': ['bf16']}},
    {'provider': {'order': ['dekallm/bf16'], 'allow_fallbacks': True, 'quantizations': ['bf16']}},
    {'provider': {'order': ['dekallm/bf16'], 'allow_fallbacks': False}},
    {'provider': {'order': ['dekallm/fp8'], 'allow_fallbacks': False, 'quantizations': ['bf8']}},
    {'messages': [{'role': 'user', 'content': 'SYNTHETIC'}, {'role': 'user', 'content': 'MORE'}]},
    {'messages': [{'role': 'system', 'content': 'SYNTHETIC'}]},
    {'messages': [{'role': 'user', 'content': 'synthetic@@invalid'}]},
])
def test_validator_refuses_every_deviation(override):
    with pytest.raises(batch.BatchRefusal):
        batch._validate(make_request(**override))


def test_validator_refuses_added_fields_and_wrong_shape():
    with pytest.raises(batch.BatchRefusal):
        batch._validate(make_request(max_tokens=512))
    with pytest.raises(batch.BatchRefusal):
        batch._validate(httpx.Request('GET', batch.URL, headers={'User-Agent': batch.USER_AGENT}))
    with pytest.raises(batch.BatchRefusal):
        batch._validate(httpx.Request('POST', 'https://example.invalid/api', content=b'{}',
                                      headers={'User-Agent': batch.USER_AGENT}))


def test_validator_refuses_wrong_user_agent_and_header_email():
    request = httpx.Request('POST', batch.URL, content=request_body(),
                            headers={'User-Agent': 'other-agent/1.0'})
    with pytest.raises(batch.BatchRefusal):
        batch._validate(request)
    request = httpx.Request('POST', batch.URL, content=request_body(),
                            headers={'User-Agent': batch.USER_AGENT, 'X-Note': 'synthetic@@invalid'})
    with pytest.raises(batch.BatchRefusal):
        batch._validate(request)


def test_user_agent_matches_the_registered_research_agent():
    assert batch.USER_AGENT == one_shot.USER_AGENT
    assert batch.USER_AGENT == 'collie-research-fetch/0.1 (academic research; polite, cached)'


# --- address provenance (A19) --------------------------------------------------------------

def pinned_request(content):
    return make_request(messages=[{'role': 'user', 'content': content}])


def test_public_addresses_are_the_pinned_items_email_like_tokens():
    raw = (b'{"item_id": "SYNTH-1", "related_information": "write to synth@example.test"}\n'
           b'{"item_id": "SYNTH-2", "presentation": "10 mg @ 2x daily"}\n')
    assert batch.public_addresses(raw) == frozenset({'synth@example.test'})
    assert batch.public_addresses(b'') == frozenset()
    with pytest.raises(batch.BatchRefusal):
        batch.public_addresses('not bytes')
    with pytest.raises(batch.BatchRefusal):
        batch.public_addresses(b'{"item_id": broken\n')


def test_validator_accepts_a_pinned_address_and_refuses_every_other_at_sign():
    pinned = frozenset({'synth@example.test'})
    batch._validate(pinned_request('SYNTHETIC contact: synth@example.test'), pinned)
    # an address outside the pin, even beside a pinned one
    with pytest.raises(batch.BatchRefusal):
        batch._validate(pinned_request('SYNTHETIC synth@example.test other@example.test'), pinned)
    # a look-alike that merely embeds the pinned address
    with pytest.raises(batch.BatchRefusal):
        batch._validate(pinned_request('SYNTHETIC xsynth@example.test'), pinned)
    # a bare "@" that is not an email-like address
    with pytest.raises(batch.BatchRefusal):
        batch._validate(pinned_request('SYNTHETIC dose 10 mg @ 2x'), pinned)
    # the default pin carries no address at all
    with pytest.raises(batch.BatchRefusal):
        batch._validate(pinned_request('SYNTHETIC synth@example.test'))


@pytest.mark.parametrize('bad', [{'synth@example.test'}, frozenset({'no-at-sign'}),
                                 frozenset({3}), ('synth@example.test',)])
def test_transport_refuses_an_invalid_address_pin(tmp_path, bad):
    with pytest.raises(batch.BatchRefusal):
        make_transport(tmp_path, allowed=bad)


def test_transport_sends_an_address_that_comes_from_the_pin(tmp_path):
    inner = MockInner()
    transport, fd, path = make_transport(tmp_path, inner, allowed=frozenset({'synth@example.test'}))
    try:
        transport.set_run('synth-a.dk')
        response = transport.handle_request(pinned_request('contact synth@example.test'))
        assert response.status_code == 200 and len(inner.seen) == 1
        refused = pinned_request('contact other@example.test')
        with pytest.raises(batch.BatchRefusal):
            transport.handle_request(refused)
        assert len(inner.seen) == 1
        events = [row['event'] for row in journal_rows(path)]
        assert events == ['reserved', 'send_intent', 'send_status']
    finally:
        transport.close()
        os.close(fd)


# --- reservation ---------------------------------------------------------------------------

def test_reservation_bytes_pin_scope_and_spacing():
    raw = batch.batch_reservation_bytes(SELECTION, 3205, 4500)
    row = json.loads(raw)
    assert row == {'event': 'reserved', 'selection_sha256': SELECTION, 'planned_target_pairs': 3205,
                   'max_sends': 4500, 'min_spacing_s': batch.MIN_SPACING_S,
                   'hold_is_proven_maximum': False}
    assert raw.endswith(b'\n')


@pytest.mark.parametrize('bad', [({'selection_sha256': 'zz' * 32},),
                                 ({'planned_targets': -1},), ({'max_sends': 5},)])
def test_reservation_arguments_are_validated(bad):
    kwargs = {'selection_sha256': SELECTION, 'planned_targets': 10, 'max_sends': 40}
    kwargs.update(bad[0])
    with pytest.raises(batch.BatchRefusal):
        batch.batch_reservation_bytes(**kwargs)


# --- construction --------------------------------------------------------------------------

def test_transport_requires_exact_reservation_prelude(tmp_path):
    fd, path = make_journal(tmp_path, prelude=b'{"event":"other"}\n')
    with pytest.raises(batch.BatchRefusal, match='reservation'):
        batch.CountedPacedTransport(MockInner(), fd, selection_sha256=SELECTION,
                                    planned_targets=10, max_sends=40, clock=FakeClock())
    os.close(fd)


def test_transport_refuses_journal_reuse(tmp_path):
    transport, fd, path = make_transport(tmp_path)
    transport.set_run('synth-run.dk')
    transport.handle_request(make_request())
    transport.close()
    with pytest.raises(batch.BatchRefusal, match='already been used'):
        batch.CountedPacedTransport(MockInner(), fd, selection_sha256=SELECTION,
                                    planned_targets=10, max_sends=40, clock=FakeClock())


def test_transport_refuses_wrong_journal_mode(tmp_path):
    fd, path = make_journal(tmp_path, mode=0o644)
    with pytest.raises(batch.BatchRefusal, match='unsafe'):
        batch.CountedPacedTransport(MockInner(), fd, selection_sha256=SELECTION,
                                    planned_targets=10, max_sends=40, clock=FakeClock())
    os.close(fd)


def test_transport_holds_an_exclusive_journal_lock(tmp_path):
    transport, fd, path = make_transport(tmp_path)
    fd2 = os.open(path, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        with pytest.raises(batch.BatchRefusal, match='another process'):
            batch.CountedPacedTransport(MockInner(), fd2, selection_sha256=SELECTION,
                                        planned_targets=10, max_sends=40, clock=FakeClock())
    finally:
        os.close(fd2)
        transport.close()


def test_transport_validates_deadline_and_helpers(tmp_path):
    fd, _ = make_journal(tmp_path)
    with pytest.raises(batch.BatchRefusal):
        batch.CountedPacedTransport(MockInner(), fd, selection_sha256=SELECTION,
                                    planned_targets=10, max_sends=40,
                                    stop_after_utc=datetime(2027, 1, 4, 23, 59, 59), clock=FakeClock())
    with pytest.raises(batch.BatchRefusal):
        batch.CountedPacedTransport(MockInner(), fd, selection_sha256=SELECTION,
                                    planned_targets=10, max_sends=40, clock=None)
    os.close(fd)


# --- send fencing --------------------------------------------------------------------------

def test_sends_are_counted_journaled_and_spaced(tmp_path):
    clock = FakeClock()
    sleep = RecordingSleep()
    inner = MockInner(statuses=[200, 200, 200])
    transport, fd, path = make_transport(tmp_path, inner, clock=clock, sleep=sleep)
    transport.set_run('synth-run.dk')
    transport.handle_request(make_request())
    clock.now += 1.0
    transport.handle_request(make_request())
    clock.now += 10.0
    transport.handle_request(make_request())
    transport.close()
    rows = journal_rows(path)
    assert [r['event'] for r in rows[1:]] == ['send_intent', 'send_status'] * 3
    assert [r['ordinal'] for r in rows[1:]] == [1, 1, 2, 2, 3, 3]
    assert all(r['run'] == 'synth-run.dk' for r in rows[1:])
    assert sleep.calls and all(call >= batch.MIN_SPACING_S - 1.0 for call in sleep.calls)
    assert len(sleep.calls) == 1  # only the 1.0s gap needed a wait
    assert transport.stats() == {'sends': 3, 'max_sends': 40, 'consecutive_refusals': 0}
    os.close(fd)


def test_no_run_label_or_closed_transport_refuses_sends(tmp_path):
    transport, fd, path = make_transport(tmp_path)
    with pytest.raises(batch.BatchRefusal, match='no continuation run'):
        transport.handle_request(make_request())
    transport.set_run('synth-run.dk')
    transport.close()
    with pytest.raises(batch.BatchRefusal, match='closed'):
        transport.handle_request(make_request())
    with pytest.raises(batch.BatchRefusal):
        transport.set_run('synth-run.dk')
    os.close(fd)


def test_run_label_is_validated(tmp_path):
    transport, fd, path = make_transport(tmp_path)
    for bad in ('../outside', 'UPPER', None, 7, 'x' * 200):
        with pytest.raises(batch.BatchRefusal):
            transport.set_run(bad)
    transport.close()
    os.close(fd)


def test_send_budget_and_deadline_are_enforced(tmp_path):
    inner = MockInner()
    transport, fd, path = make_transport(tmp_path, inner, max_sends=2, targets=2)
    transport.set_run('synth-run.dk')
    transport.handle_request(make_request())
    transport.handle_request(make_request())
    with pytest.raises(batch.BatchRefusal, match='budget'):
        transport.handle_request(make_request())
    transport.close()
    os.close(fd)
    past = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transport2, fd2, path2 = make_transport(tmp_path, stop=past)
    transport2.set_run('synth-run.dk')
    with pytest.raises(batch.BatchRefusal, match='deadline'):
        transport2.handle_request(make_request())
    transport2.close()
    os.close(fd2)


def test_429_is_passed_through_journaled_and_counted(tmp_path):
    inner = MockInner(statuses=[429, 429, 200])
    transport, fd, path = make_transport(tmp_path, inner)
    transport.set_run('synth-run.dk')
    first = transport.handle_request(make_request())
    second = transport.handle_request(make_request())
    third = transport.handle_request(make_request())
    transport.close()
    assert [first.status_code, second.status_code, third.status_code] == [429, 429, 200]
    rows = journal_rows(path)
    statuses = [r for r in rows if r['event'] == 'send_status']
    assert [r['http_status'] for r in statuses] == [429, 429, 200]
    assert transport.stats()['consecutive_refusals'] == 0  # the 200 reset the fence
    os.close(fd)


def test_consecutive_refusal_fence_stops_the_batch(tmp_path):
    inner = MockInner(statuses=[429] * 35)
    transport, fd, path = make_transport(tmp_path, inner, max_sends=40)
    transport.set_run('synth-run.dk')
    with pytest.raises(batch.BatchRefusal, match='consecutive'):
        for _ in range(35):
            transport.handle_request(make_request())
    transport.close()
    os.close(fd)


def test_transport_failure_is_journaled_and_reraised(tmp_path):
    class Failing(httpx.BaseTransport):
        def handle_request(self, request):
            raise OSError('synthetic connection failure')

        def close(self):
            pass

    transport, fd, path = make_transport(tmp_path, Failing())
    transport.set_run('synth-run.dk')
    with pytest.raises(OSError):
        transport.handle_request(make_request())
    transport.close()
    rows = journal_rows(path)
    failure = [r for r in rows if r['event'] == 'send_failure']
    assert len(failure) == 1 and failure[0]['charge'] == 'unknown'
    assert failure[0]['error_type'] == 'OSError'
    os.close(fd)


def test_invalid_requests_never_reach_the_wire(tmp_path):
    inner = MockInner()
    transport, fd, path = make_transport(tmp_path, inner)
    transport.set_run('synth-run.dk')
    with pytest.raises(batch.BatchRefusal):
        transport.handle_request(make_request(temperature=1))
    assert not inner.seen and transport.stats()['sends'] == 0
    transport.close()
    os.close(fd)


def test_journal_rows_stay_append_only_with_monotonic_ordinals(tmp_path):
    inner = MockInner(statuses=[200] * 5)
    transport, fd, path = make_transport(tmp_path, inner)
    transport.set_run('synth-run.dk')
    for _ in range(5):
        transport.handle_request(make_request())
    transport.close()
    rows = journal_rows(path)
    intents = [r['ordinal'] for r in rows if r['event'] == 'send_intent']
    assert intents == [1, 2, 3, 4, 5]
    before = path.read_bytes()
    assert path.read_bytes() == before  # a closed transport writes nothing further
    os.close(fd)


def test_spacing_helper():
    assert batch.spacing_okay(batch.MIN_SPACING_S)
    assert batch.spacing_okay(4.5)
    assert not batch.spacing_okay(3.9)
    assert not batch.spacing_okay(float('nan'))
    assert not batch.spacing_okay(4)


# --- journal identity ----------------------------------------------------------------------

def test_journal_refuses_replacement_or_removal(tmp_path):
    transport, fd, path = make_transport(tmp_path)
    transport.set_run('synth-run.dk')
    transport.handle_request(make_request())
    os.unlink(path)
    path.write_bytes(b'{"event":"tampered"}\n')
    os.chmod(path, 0o600)
    with pytest.raises(batch.BatchRefusal):
        transport.handle_request(make_request())
    transport.close()
    os.close(fd)


def test_journal_mode_is_owner_only(tmp_path):
    transport, fd, path = make_transport(tmp_path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    transport.close()
    os.close(fd)
