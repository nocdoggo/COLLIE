"""Invented-only tests of the one-physical-attempt HTTPX transport."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading

import httpx
import openai
import pytest

from analysis.coling.followup import oss_one_shot_transport as oneshot


SELECTION = 'a' * 64


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network access is forbidden in these tests')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


@pytest.fixture
def journal():
    with tempfile.TemporaryDirectory(prefix='oss-one-shot-test-', dir='/tmp/opencode') as root:
        path = Path(root) / 'attempt.jsonl'
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.write(fd, oneshot.reservation_bytes(SELECTION))
        os.fsync(fd)
        try:
            yield fd, path
        finally:
            os.close(fd)


def payload():
    return {'model': 'openai/gpt-oss-20b', 'messages': [{'role': 'user', 'content': 'SYNTHETIC NOTICE'}],
            'temperature': 0.0, 'provider': {'order': ['deepinfra/bf16'], 'allow_fallbacks': False,
                                             'quantizations': ['bf16']}}


def request(body=None, *, url=oneshot.URL, method='POST', user_agent=oneshot.USER_AGENT, headers=None):
    return httpx.Request(method, url, headers={'User-Agent': user_agent, **(headers or {})}, json=payload() if body is None else body)


@contextmanager
def guarded(journal, handler):
    fd, _ = journal
    guard = oneshot.OnePhysicalAttempt(httpx.MockTransport(handler), fd, selection_sha256=SELECTION)
    try:
        yield guard
    finally:
        guard.close()


def test_one_request_is_dispatched_once_and_journal_contains_no_content(journal):
    observed = []
    with guarded(journal, lambda req: (observed.append(req), httpx.Response(200, content=b'SYNTHETIC-RESPONSE'))[1]) as guard:
        response = guard.handle_request(request())
        assert response.status_code == 200 and response.read() == b'SYNTHETIC-RESPONSE'
        with pytest.raises(oneshot.OneShotRefusal, match='already been consumed'):
            guard.handle_request(request())
    assert len(observed) == 1
    raw = journal[1].read_bytes()
    events = [json.loads(line) for line in raw.splitlines()]
    assert [event['event'] for event in events] == ['reserved', 'physical_request_intent', 'physical_response_status']
    assert events[-1]['charge'] == 'unreconciled'
    assert b'SYNTHETIC NOTICE' not in raw and b'SYNTHETIC-RESPONSE' not in raw and b'Authorization' not in raw


@pytest.mark.parametrize(('url', 'method', 'agent'), [
    ('https://different.invalid/api/v1/chat/completions', 'POST', oneshot.USER_AGENT),
    ('http://openrouter.ai/api/v1/chat/completions', 'POST', oneshot.USER_AGENT),
    (oneshot.URL + '?extra=1', 'POST', oneshot.USER_AGENT),
    (oneshot.URL, 'GET', oneshot.USER_AGENT),
    (oneshot.URL, 'POST', 'wrong-agent'),
])
def test_wrong_endpoint_method_or_agent_never_sends(journal, url, method, agent):
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal):
            guard.handle_request(request(url=url, method=method, user_agent=agent))
        assert not calls
        assert guard.handle_request(request()).status_code == 200


@pytest.mark.parametrize(('field', 'bad'), [
    ('model', 'other-model'), ('temperature', False), ('temperature', 1),
    ('max_tokens', 128), ('max_completion_tokens', 128), ('seed', 1), ('reasoning', {}),
])
def test_changed_model_decoding_or_extra_field_never_sends(journal, field, bad):
    body = payload()
    body[field] = bad
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal):
            guard.handle_request(request(body))
    assert not calls and journal[1].read_bytes() == oneshot.reservation_bytes(SELECTION)


@pytest.mark.parametrize(('field', 'bad'), [
    ('order', ['deepinfra/turbo']), ('allow_fallbacks', True), ('allow_fallbacks', 0),
    ('quantizations', ['fp8']), ('data_collection', 'allow'),
])
def test_changed_provider_pin_never_sends(journal, field, bad):
    body = payload()
    body['provider'][field] = bad
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='provider'):
            guard.handle_request(request(body))
    assert not calls


@pytest.mark.parametrize('messages', [[], [{'role': 'system', 'content': 'SYNTH'}],
                                      [{'role': 'user', 'content': 'SYNTH'}, {'role': 'user', 'content': 'OTHER'}],
                                      [{'role': 'user', 'content': None}], [{'role': 'user', 'content': 'SYNTH', 'extra': 1}]])
def test_changed_message_shape_never_sends(journal, messages):
    body = payload()
    body['messages'] = messages
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='message'):
            guard.handle_request(request(body))
    assert not calls


def test_any_email_like_message_or_header_is_refused(journal):
    body = payload()
    body['messages'][0]['content'] = 'SYNTHETIC name@example.invalid'
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='email'):
            guard.handle_request(request(body))
        with pytest.raises(oneshot.OneShotRefusal, match='email'):
            guard.handle_request(request(headers={'X-Synthetic': 'name@example.invalid'}))
    assert not calls


def test_escaped_at_sign_is_detected_after_json_decoding(journal):
    raw = json.dumps(payload(), separators=(',', ':')).replace('SYNTHETIC NOTICE', 'SYNTHETIC \\u0040')
    req = httpx.Request('POST', oneshot.URL, headers={'User-Agent': oneshot.USER_AGENT}, content=raw)
    with guarded(journal, lambda _: httpx.Response(200)) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='email'):
            guard.handle_request(req)


@pytest.mark.parametrize('raw', [b'{"model":"x","model":"y"}', b'{"temperature":NaN}', b'not-json'])
def test_duplicate_nonfinite_or_invalid_json_never_sends(journal, raw):
    req = httpx.Request('POST', oneshot.URL, headers={'User-Agent': oneshot.USER_AGENT}, content=raw)
    with guarded(journal, lambda _: httpx.Response(200)) as guard:
        with pytest.raises(oneshot.OneShotRefusal):
            guard.handle_request(req)


def test_oversized_body_is_refused_before_sender(journal):
    body = payload()
    body['messages'][0]['content'] = 'S' * oneshot._MAX_BODY
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='bound'):
            guard.handle_request(request(body))
    assert not calls


def test_unbuffered_stream_is_refused_without_consuming_it(journal):
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError('unbounded stream was consumed')

    req = httpx.Request('POST', oneshot.URL, headers={'User-Agent': oneshot.USER_AGENT}, content=Stream())
    calls = []
    with guarded(journal, lambda item: (calls.append(item), httpx.Response(200))[1]) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='valid bounded JSON'):
            guard.handle_request(req)
    assert not calls


def test_transport_failure_is_unknown_and_cannot_be_retried(journal):
    calls = []

    def fail(req):
        calls.append(req)
        raise OSError('SYNTHETIC SECRET DETAILS')

    with guarded(journal, fail) as guard:
        with pytest.raises(oneshot.OneShotRefusal, match='charge is unknown'):
            guard.handle_request(request())
        with pytest.raises(oneshot.OneShotRefusal, match='already been consumed'):
            guard.handle_request(request())
    raw = journal[1].read_bytes()
    assert len(calls) == 1 and b'SYNTHETIC SECRET DETAILS' not in raw
    assert json.loads(raw.splitlines()[-1])['charge'] == 'unknown'


def test_journal_sync_failure_never_dispatches_or_reuses_ticket(journal, monkeypatch):
    calls = []
    with guarded(journal, lambda req: (calls.append(req), httpx.Response(200))[1]) as guard:
        monkeypatch.setattr(oneshot, '_journal', lambda *_: (_ for _ in ()).throw(OSError('synthetic failure')))
        with pytest.raises(OSError):
            guard.handle_request(request())
        with pytest.raises(oneshot.OneShotRefusal, match='already been consumed'):
            guard.handle_request(request())
    assert not calls


def test_closed_guard_and_used_journal_cannot_be_reused(journal):
    with guarded(journal, lambda _: httpx.Response(200)) as guard:
        guard.handle_request(request())
    with pytest.raises(oneshot.OneShotRefusal, match='already been consumed'):
        guard.handle_request(request())
    with pytest.raises(oneshot.OneShotRefusal, match='already been used'):
        oneshot.OnePhysicalAttempt(httpx.MockTransport(lambda _: httpx.Response(200)), journal[0], selection_sha256=SELECTION)


def test_two_open_journal_descriptors_cannot_both_authorize_dispatch(journal):
    other = os.open(journal[1], os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
    try:
        with guarded(journal, lambda _: httpx.Response(200)):
            with pytest.raises(oneshot.OneShotRefusal, match='holds'):
                oneshot.OnePhysicalAttempt(httpx.MockTransport(lambda _: httpx.Response(200)), other, selection_sha256=SELECTION)
    finally:
        os.close(other)


def test_concurrent_calls_share_the_one_physical_attempt(journal):
    observed = []
    barrier = threading.Barrier(2)
    with guarded(journal, lambda req: (observed.append(req), httpx.Response(200))[1]) as guard:
        def worker(_index):
            barrier.wait(timeout=10)
            try:
                return guard.handle_request(request()).status_code
            except oneshot.OneShotRefusal:
                return 'refused'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
    assert set(results) == {200, 'refused'} and len(observed) == 1


def test_redirect_cannot_cause_a_second_physical_request(journal):
    seen = []
    with guarded(journal, lambda req: (seen.append(req), httpx.Response(302, headers={'Location': 'https://other.invalid/'}))[1]) as guard:
        with httpx.Client(transport=guard, follow_redirects=True) as client:
            with pytest.raises(oneshot.OneShotRefusal, match='already been consumed'):
                client.send(request())
    assert len(seen) == 1


@pytest.mark.parametrize('defect', ['mode', 'hardlink', 'append', 'selection', 'existing_intent'])
def test_private_journal_must_be_exact_private_append_only_reservation(journal, defect):
    fd, path = journal
    other = None
    try:
        if defect == 'mode':
            path.chmod(0o644)
        elif defect == 'hardlink':
            os.link(path, path.parent / 'invented-alias')
        elif defect == 'append':
            other = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        elif defect == 'existing_intent':
            os.write(fd, b'{"event":"physical_request_intent"}\n')
        with pytest.raises(oneshot.OneShotRefusal):
            oneshot.OnePhysicalAttempt(httpx.MockTransport(lambda _: httpx.Response(200)),
                                       other if other is not None else fd,
                                       selection_sha256='b' * 64 if defect == 'selection' else SELECTION)
    finally:
        if other is not None:
            os.close(other)
        path.chmod(0o600)


def test_actual_openai_sdk_constructs_a_matching_request_on_fake_transport(journal):
    observed = []

    def reply(req):
        observed.append(req)
        return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 0,
                                        'model': oneshot.MODEL,
                                        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'SYNTH'},
                                                     'finish_reason': 'stop'}],
                                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})

    with guarded(journal, reply) as guard:
        with httpx.Client(transport=guard, trust_env=False, follow_redirects=False) as http:
            sdk = openai.OpenAI(api_key='synthetic-only-key', base_url='https://openrouter.ai/api/v1',
                                max_retries=0, http_client=http, default_headers={'User-Agent': oneshot.USER_AGENT})
            result = sdk.chat.completions.create(model=oneshot.MODEL,
                                                 messages=[{'role': 'user', 'content': 'SYNTHETIC NOTICE'}],
                                                 temperature=0.0, extra_body={'provider': payload()['provider']})
    assert result.choices[0].message.content == 'SYNTH' and len(observed) == 1


def test_actual_process_exit_after_intent_fences_reopening(journal):
    program = """
import os, sys, httpx
from analysis.coling.followup import oss_one_shot_transport as candidate
fd = os.open(sys.argv[1], os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW)
def die(_): os._exit(79)
guard = candidate.OnePhysicalAttempt(httpx.MockTransport(die), fd, selection_sha256='a'*64)
body = {'model':'openai/gpt-oss-20b','messages':[{'role':'user','content':'SYNTHETIC'}],
        'temperature':0,'provider':{'order':['deepinfra/bf16'],'allow_fallbacks':False,'quantizations':['bf16']}}
req = httpx.Request('POST',candidate.URL,headers={'User-Agent':candidate.USER_AGENT},json=body)
guard.handle_request(req)
"""
    environment = {'HOME': '/tmp/opencode', 'TMPDIR': '/tmp/opencode', 'PATH': '/usr/bin:/bin',
                   'PYTHONPATH': '.', 'PYTHONDONTWRITEBYTECODE': '1'}
    worktree = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, '-c', program, str(journal[1])], cwd=worktree, env=environment,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 79, result.stderr
    events = [json.loads(line) for line in journal[1].read_bytes().splitlines()]
    assert [event['event'] for event in events] == ['reserved', 'physical_request_intent']
    with pytest.raises(oneshot.OneShotRefusal, match='already been used'):
        oneshot.OnePhysicalAttempt(httpx.MockTransport(lambda _: httpx.Response(200)), journal[0], selection_sha256=SELECTION)


def test_expired_deadline_refuses_before_sending(journal):
    calls = []
    guard = oneshot.OnePhysicalAttempt(httpx.MockTransport(lambda req: (calls.append(req), httpx.Response(200))[1]),
                                       journal[0], selection_sha256=SELECTION,
                                       stop_after_utc=datetime.now(timezone.utc) - timedelta(seconds=1))
    try:
        with pytest.raises(oneshot.OneShotRefusal, match='deadline'):
            guard.handle_request(request())
    finally:
        guard.close()
    assert not calls and journal[1].read_bytes() == oneshot.reservation_bytes(SELECTION)
