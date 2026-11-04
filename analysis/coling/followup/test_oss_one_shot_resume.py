"""Invented-only tests for single-attempt continuation mechanics."""

from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace

import httpx
import openai
import pytest

from analysis.coling.followup import oss_one_shot_resume as resume
from analysis.coling.followup import oss_one_shot_transport as transport


def jsonl(*rows):
    return b''.join((json.dumps(row, sort_keys=True) + '\n').encode() for row in rows)


def index(readings, responses, count):
    return resume.index_checkpoint(readings, responses, expected_readings_sha256=sha256(readings).hexdigest(),
                                   expected_responses_sha256=sha256(responses).hexdigest(),
                                   expected_reading_count=count)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network access is forbidden in these tests')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def test_index_keeps_only_completed_and_orphaned_pair_identities():
    readings = jsonl({'item_id': 'SYNTH-A', 'sample': 0, 'reading': {'secret': 'SYNTHETIC-READING'}})
    responses = jsonl({'item_id': 'SYNTH-A', 'sample': 0, 'attempt': 0, 'text': 'SYNTHETIC-ANSWER'},
                      {'item_id': 'SYNTH-B', 'sample': 0, 'attempt': 0, 'text': 'SYNTHETIC-ORPHAN'})
    result = index(readings, responses, 1)
    assert result.completed == frozenset({('SYNTH-A', 0)})
    assert result.orphaned == frozenset({('SYNTH-B', 0)})
    assert 'SYNTHETIC-ANSWER' not in repr(result) and 'SYNTHETIC-READING' not in repr(result)


def test_different_samples_of_one_item_are_distinct():
    readings = jsonl({'item_id': 'SYNTH-A', 'sample': 0}, {'item_id': 'SYNTH-A', 'sample': 1})
    assert index(readings, b'', 2).completed == frozenset({('SYNTH-A', 0), ('SYNTH-A', 1)})


@pytest.mark.parametrize('kind', ['reading', 'response'])
def test_duplicate_checkpoint_identities_are_refused(kind):
    row = {'item_id': 'SYNTH-A', 'sample': 0}
    if kind == 'reading':
        readings, responses, count = jsonl(row, row), b'', 2
    else:
        readings, responses, count = b'', jsonl(row | {'attempt': 0}, row | {'attempt': 0}), 0
    with pytest.raises(resume.ResumeRefusal, match='duplicat'):
        index(readings, responses, count)


@pytest.mark.parametrize(('field', 'bad'), [('item_id', '../outside'), ('item_id', None),
                                            ('sample', True), ('sample', -1), ('sample', 1000)])
def test_invalid_checkpoint_pair_is_refused(field, bad):
    row = {'item_id': 'SYNTH-A', 'sample': 0}
    row[field] = bad
    with pytest.raises(resume.ResumeRefusal, match='identity'):
        index(jsonl(row), b'', 1)


@pytest.mark.parametrize('bad', [True, -1, 2, None, '0'])
def test_invalid_response_attempt_is_refused(bad):
    row = {'item_id': 'SYNTH-A', 'sample': 0, 'attempt': bad}
    with pytest.raises(resume.ResumeRefusal, match='attempt'):
        index(b'', jsonl(row), 0)


@pytest.mark.parametrize('raw', [b'{}', b'{}\n\n', b'{}\r\n', b'\xff\n', b'[]\n',
                                 b'{"item_id":"x","item_id":"y"}\n', b'{"x":NaN}\n'])
def test_truncated_or_malformed_checkpoint_is_refused(raw):
    with pytest.raises(resume.ResumeRefusal):
        index(raw, b'', 0)


def test_checkpoint_hash_and_manifest_count_are_required():
    readings = jsonl({'item_id': 'SYNTH-A', 'sample': 0})
    with pytest.raises(resume.ResumeRefusal, match='byte identity'):
        resume.index_checkpoint(readings, b'', expected_readings_sha256='0' * 64,
                                expected_responses_sha256=sha256(b'').hexdigest(), expected_reading_count=1)
    with pytest.raises(resume.ResumeRefusal, match='count'):
        index(readings, b'', 0)


class SpendCapReached(Exception):
    pass


class CallCapReached(Exception):
    pass


class ServedModelMismatch(Exception):
    pass


READ_MODULE = SimpleNamespace(SpendCapReached=SpendCapReached, CallCapReached=CallCapReached,
                              ServedModelMismatch=ServedModelMismatch)


def test_filtered_reader_skips_completed_and_orphaned_pairs():
    checkpoint = resume.CheckpointIndex(frozenset({('SYNTH-A', 0)}), frozenset({('SYNTH-B', 0)}))
    items = [SimpleNamespace(item_id=name) for name in ('SYNTH-A', 'SYNTH-B', 'SYNTH-C')]
    seen = []
    reader = SimpleNamespace(read=lambda item, sample: (seen.append((item.item_id, sample)) or {'synthetic': True}))
    rows, status = resume.filtered_read_items(READ_MODULE, reader, items, samples=1, rows=[], index=checkpoint)
    assert seen == [('SYNTH-C', 0)] and rows == [{'synthetic': True}]
    assert status == 'partial: one-shot continuation sidecar'


@pytest.mark.parametrize('set_name', ['completed', 'orphaned'])
def test_historical_pair_outside_assigned_items_stops_before_reading(set_name):
    kwargs = {'completed': frozenset(), 'orphaned': frozenset()}
    kwargs[set_name] = frozenset({('SYNTH-UNASSIGNED', 0)})
    reader = SimpleNamespace(read=lambda *_: (_ for _ in ()).throw(AssertionError('reader called')))
    with pytest.raises(resume.ResumeRefusal, match='assigned run'):
        resume.filtered_read_items(READ_MODULE, reader, [SimpleNamespace(item_id='SYNTH-A')], samples=1,
                                   rows=[], index=resume.CheckpointIndex(**kwargs))


@pytest.mark.parametrize('error', [SpendCapReached('synthetic cap'), CallCapReached('synthetic call cap'),
                                    ServedModelMismatch('synthetic mismatch')])
def test_filtered_reader_preserves_rows_before_a_guarded_stop(error):
    items = [SimpleNamespace(item_id='SYNTH-A'), SimpleNamespace(item_id='SYNTH-B')]
    def read(item, sample):
        if item.item_id == 'SYNTH-B':
            raise error
        return {'item_id': item.item_id, 'sample': sample}
    rows, status = resume.filtered_read_items(READ_MODULE, SimpleNamespace(read=read), items, samples=1, rows=[],
                                               index=resume.CheckpointIndex(frozenset(), frozenset()))
    assert rows == [{'item_id': 'SYNTH-A', 'sample': 0}] and status.startswith('aborted:')


@pytest.fixture
def stage():
    with tempfile.TemporaryDirectory(prefix='oss-one-shot-stage-', dir='/tmp/opencode') as parent:
        path = Path(parent) / 'stage'
        path.mkdir(mode=0o700)
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            yield fd, path
        finally:
            os.close(fd)


def test_new_private_sidecar_is_exclusive_and_never_claims_original_completion(stage):
    fd, root = stage
    rows = [{'item_id': 'SYNTH-C', 'sample': 0, 'reading': 'SYNTHETIC'}]
    responses = [{'item_id': 'SYNTH-C', 'sample': 0, 'text': 'SYNTHETIC'}]
    result = resume.write_private_sidecar(fd, rows, responses, selection_sha256='a' * 64)
    assert result['complete'] is False and result['original_run_closed'] is False
    assert result['new_reading_rows'] == result['new_response_rows'] == 1
    assert (root / 'readings.jsonl').stat().st_mode & 0o777 == 0o600
    assert (root / 'responses.jsonl').stat().st_mode & 0o777 == 0o600
    assert json.loads((root / 'sidecar_manifest.json').read_bytes()) == result
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    with pytest.raises(FileExistsError):
        resume.write_private_sidecar(fd, rows, responses, selection_sha256='a' * 64)
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_existing_sidecar_file_is_not_overwritten(stage):
    fd, root = stage
    (root / 'readings.jsonl').write_bytes(b'SYNTHETIC EXISTING')
    with pytest.raises(FileExistsError):
        resume.write_private_sidecar(fd, [], [], selection_sha256='a' * 64)
    assert (root / 'readings.jsonl').read_bytes() == b'SYNTHETIC EXISTING'
    assert not (root / 'responses.jsonl').exists()


def test_sidecar_directory_must_be_owner_only(stage):
    fd, root = stage
    root.chmod(0o755)
    try:
        with pytest.raises(resume.ResumeRefusal, match='directory'):
            resume.write_private_sidecar(fd, [], [], selection_sha256='a' * 64)
    finally:
        root.chmod(0o700)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('bad', ['', 'A' * 64, 'a' * 63, None])
def test_sidecar_selection_digest_must_be_exact(stage, bad):
    fd, root = stage
    with pytest.raises(resume.ResumeRefusal, match='selection'):
        resume.write_private_sidecar(fd, [], [], selection_sha256=bad)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('kind', ['reading', 'response', 'orphan'])
def test_sidecar_never_reuses_a_protected_historical_pair(kind):
    protected = resume.CheckpointIndex(frozenset({('SYNTH-A', 0)}), frozenset({('SYNTH-B', 0)}))
    rows, responses = [], []
    if kind == 'reading':
        rows = [{'item_id': 'SYNTH-A', 'sample': 0}]
    elif kind == 'response':
        responses = [{'item_id': 'SYNTH-A', 'sample': 0, 'attempt': 0}]
    else:
        rows = [{'item_id': 'SYNTH-B', 'sample': 0}]
    with pytest.raises(resume.ResumeRefusal, match='protected'):
        resume._validate_sidecar_rows(protected, rows, responses)


def test_filtered_reader_rejects_duplicate_assigned_items_before_call():
    reader = SimpleNamespace(read=lambda *_: (_ for _ in ()).throw(AssertionError('reader called')))
    items = [SimpleNamespace(item_id='SYNTH-A'), SimpleNamespace(item_id='SYNTH-A')]
    with pytest.raises(resume.ResumeRefusal, match='assigned run'):
        resume.filtered_read_items(READ_MODULE, reader, items, samples=1, rows=[],
                                   index=resume.CheckpointIndex(frozenset(), frozenset()))


def test_local_budget_reserves_inside_model_and_stricter_study_caps():
    held = {'SYNTH-RUN': {'model': 'gpt-oss-20b', 'open': True, 'spent_usd': 0.15,
                          'cap_usd': 0.16, 'held_usd': 0.16},
            'SYNTH-OTHER': {'model': 'gpt-oss-20b', 'open': True, 'spent_usd': 4.0,
                            'cap_usd': 5.0, 'held_usd': 5.0},
            'SYNTH-STUDY': {'model': 'other', 'open': False, 'spent_usd': 60.0,
                            'cap_usd': 60.0, 'held_usd': 60.0}}
    module = SimpleNamespace(held_by_run=lambda _: held)
    resume._check_local_budget(module, {'run': 'SYNTH-RUN'}, '0.250000')
    with pytest.raises(resume.ResumeRefusal, match='hold'):
        resume._check_local_budget(module, {'run': 'SYNTH-RUN'}, '0.200000')
    held['SYNTH-OTHER']['held_usd'] = 9.9
    with pytest.raises(resume.ResumeRefusal, match='cap'):
        resume._check_local_budget(module, {'run': 'SYNTH-RUN'}, '0.250000')


def key_status(now, **changes):
    result = {'event': 'result', 'timestamp_utc': now.isoformat(), 'http_status': 200, 'metadata_valid': True,
              'limit_usd': '220', 'usage_usd': '204', 'limit_remaining_usd': '16'}
    result.update(changes)
    return jsonl({'event': 'reserved', 'reserved_usd': '0.10'}, {'event': 'request_intent'}, result)


def test_recent_key_status_is_verified_as_a_separate_headroom_check():
    now = datetime.now(timezone.utc)
    raw = key_status(now)
    resume._check_recent_key_status(raw, sha256(raw).hexdigest(), now)


@pytest.mark.parametrize(('changes', 'time_shift'), [
    ({}, 301), ({}, -1), ({'limit_usd': '251'}, 0), ({'limit_remaining_usd': '0.09'}, 0),
    ({'limit_remaining_usd': '15'}, 0), ({'metadata_valid': False}, 0), ({'http_status': 403}, 0),
    ({'usage_usd': '251'}, 0), ({'usage_usd': True}, 0), ({'limit_usd': 'NaN'}, 0),
])
def test_stale_inconsistent_or_insufficient_key_status_is_refused(changes, time_shift):
    now = datetime.now(timezone.utc)
    raw = key_status(now - timedelta(seconds=time_shift), **changes)
    with pytest.raises(resume.ResumeRefusal):
        resume._check_recent_key_status(raw, sha256(raw).hexdigest(), now)


def test_owner_replacement_key_limit_of_250_is_accepted():
    now = datetime.now(timezone.utc)
    raw = key_status(now, limit_usd='250', usage_usd='0', limit_remaining_usd='250')
    resume._check_recent_key_status(raw, sha256(raw).hexdigest(), now)


def test_key_status_hash_and_event_order_are_required():
    now = datetime.now(timezone.utc)
    raw = key_status(now)
    with pytest.raises(resume.ResumeRefusal, match='identity'):
        resume._check_recent_key_status(raw, '0' * 64, now)
    malformed = jsonl({'event': 'request_intent'}, {'event': 'reserved', 'reserved_usd': '0.10'},
                      {'event': 'result'})
    with pytest.raises(resume.ResumeRefusal, match='incomplete'):
        resume._check_recent_key_status(malformed, sha256(malformed).hexdigest(), now)


def test_missing_execution_flag_refuses_before_registration(monkeypatch):
    monkeypatch.setattr(resume.sys, 'argv', ['oss_one_shot_resume'])
    monkeypatch.setattr(resume, '_verify_registration', lambda: (_ for _ in ()).throw(AssertionError('accessed')))
    with pytest.raises(SystemExit, match='exact registered execution flag'):
        resume.main()


def test_exact_hooks_preserve_f1_request_shape_and_filter_old_pairs(stage, tmp_path, monkeypatch):
    stage_fd, stage_path = stage
    journal_path = tmp_path / 'synthetic-journal'
    journal_fd = os.open(journal_path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.write(journal_fd, transport.reservation_bytes(resume._SELECTION_SHA))
    os.fsync(journal_fd)
    network = []
    cache_calls = []

    class BaseCache:
        def __init__(self, root):
            self.root = Path(root)

    class BaseGuard:
        def __init__(self, *args, **kwargs):
            self.max_attempts = kwargs.get('max_attempts')
            self.logged = []
        def _log(self, row):
            self.logged.append(row)
        def complete_metered(self, *_args, **_kwargs):
            raise RuntimeError('SYNTHETIC SECRET DETAIL')

    class FakeItem:
        def __init__(self, item_id):
            self.item_id = item_id
        @classmethod
        def from_dict(cls, value):
            return cls(value['item_id'])

    module = SimpleNamespace(ReadCache=BaseCache, GuardedTransport=BaseGuard,
                             _sha256_file=lambda *_: (_ for _ in ()).throw(AssertionError('unexpected hash')),
                             ReadItem=FakeItem, SpendCapReached=SpendCapReached,
                             CallCapReached=CallCapReached, ServedModelMismatch=ServedModelMismatch,
                             OUT_ROOT=tmp_path / 'workspace/analysis/coling/out/read',
                             LOCAL_ROOT=tmp_path / 'workspace/results/coling/read')
    endpoints = SimpleNamespace(EMPTY_ECHO_RETRIES=3)
    openai_module = SimpleNamespace(OpenAI=openai.OpenAI)
    fake_cache = SimpleNamespace(REAL_ROOT='/synthetic-fixed-cache',
                                 get=lambda root, key: cache_calls.append(('get', root, key)) or None,
                                 put=lambda root, key, **values: cache_calls.append(('put', root, key, values)))

    def response(req):
        network.append(req)
        return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion', 'created': 0,
                                        'model': transport.MODEL,
                                        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'SYNTH'},
                                                     'finish_reason': 'stop'}],
                                        'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})

    def mock_transport(**kwargs):
        assert kwargs == {'verify': True, 'trust_env': False, 'retries': 0}
        return httpx.MockTransport(response)

    httpx_module = SimpleNamespace(HTTPTransport=mock_transport, Client=httpx.Client)
    index = resume.CheckpointIndex(frozenset({('SYNTH-A', 0)}), frozenset({('SYNTH-B', 0)}))
    input_raw = jsonl({'item_id': 'SYNTH-A'}, {'item_id': 'SYNTH-B'}, {'item_id': 'SYNTH-C'})
    monkeypatch.setattr(resume, '_DEADLINE', datetime.now(timezone.utc) + timedelta(hours=1))
    (tmp_path / 'workspace').mkdir()
    monkeypatch.chdir(tmp_path / 'workspace')
    try:
        client = resume._install_hooks(module, endpoints, openai_module, httpx_module, fake_cache, transport,
                                       index=index, stage_fd=stage_fd, journal_fd=journal_fd,
                                       items_raw=input_raw, item_path='analysis/coling/out/items/synthetic.jsonl',
                                       run_name='SYNTH-RUN')
        try:
            assert endpoints.EMPTY_ECHO_RETRIES == 0
            cache_instance = module.ReadCache('results/coling/read/cache')
            assert cache_instance.get('synthetic-key') is None
            assert cache_calls[0] == ('get', '/synthetic-fixed-cache', 'synthetic-key')
            with pytest.raises(resume.ResumeRefusal, match='cache root'):
                module.ReadCache('wrong').get('synthetic-key')
            guard = module.GuardedTransport()
            assert guard.max_attempts == 1
            guard._log({'event': 'error', 'error': 'SYNTHETIC SECRET DETAIL'})
            assert guard.logged[-1]['error'] == 'details withheld by one-shot guard'
            with pytest.raises(resume.ResumeRefusal, match='details withheld'):
                guard.complete_metered('SYNTHETIC')
            items = module.load_items(Path('analysis/coling/out/items/synthetic.jsonl'))
            assert module._sha256_file(Path('analysis/coling/out/items/synthetic.jsonl')) == sha256(input_raw).hexdigest()
            with pytest.raises(resume.ResumeRefusal, match='unregistered'):
                module._sha256_file(Path('/unregistered'))
            seen = []
            reader = SimpleNamespace(read=lambda item, sample: (seen.append((item.item_id, sample))
                                                                 or {'item_id': item.item_id, 'sample': sample}),
                                     responses=[])
            rows, _ = module.read_items(reader, items, samples=1, rows=[])
            assert seen == [('SYNTH-C', 0)]
            result = module.write_run(rows, reader, out_dir=Path('analysis/coling/out/read/SYNTH-RUN'),
                                      local_dir=Path('results/coling/read/SYNTH-RUN'), meta={}, items=items, samples=1)
            assert result['complete'] is False and (stage_path / 'sidecar_manifest.json').is_file()
            with pytest.raises(resume.ResumeRefusal, match='output roots'):
                module.write_run(rows, reader, out_dir=Path('analysis/coling/out/read/OTHER-RUN'),
                                 local_dir=Path('results/coling/read/SYNTH-RUN'), meta={}, items=items, samples=1)
            with pytest.raises(resume.ResumeRefusal, match='output roots'):
                module.write_run(rows, reader, out_dir=Path('elsewhere/SYNTH-RUN'),
                                 local_dir=Path('results/coling/read/SYNTH-RUN'), meta={}, items=items, samples=1)
            sdk = openai_module.OpenAI(api_key='synthetic-only-key', base_url='https://openrouter.ai/api/v1',
                                       timeout=180, max_retries=0)
            reply = sdk.chat.completions.create(model=transport.MODEL,
                                                messages=[{'role': 'user', 'content': 'SYNTHETIC NOTICE'}],
                                                temperature=0.0, extra_body={'provider': {
                                                    'order': ['deepinfra/bf16'], 'allow_fallbacks': False,
                                                    'quantizations': ['bf16']}})
            assert reply.choices[0].message.content == 'SYNTH' and len(network) == 1
        finally:
            client.close()
    finally:
        os.close(journal_fd)


@pytest.fixture
def selected_fixture(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    private = tmp_path / 'private'
    output = workspace / 'analysis/coling/out/read'
    local = workspace / 'results/coling/read'
    item_dir = workspace / 'analysis/coling/out/items'
    locks = output / '_launch/locks'
    locks.mkdir(parents=True)
    local.mkdir(parents=True)
    item_dir.mkdir(parents=True)
    private.mkdir(mode=0o700)
    for i in range(8):
        (locks / f'openrouter.w{i}.lock').write_bytes(b'')
    name = 'SYNTH-RUN'
    out_run, local_run = output / name, local / name
    out_run.mkdir()
    local_run.mkdir()
    readings = jsonl({'item_id': 'SYNTH-A', 'sample': 0, 'reading': 'SYNTHETIC-OLD'})
    responses = jsonl({'item_id': 'SYNTH-A', 'sample': 0, 'attempt': 0, 'text': 'SYNTHETIC'},
                      {'item_id': 'SYNTH-B', 'sample': 0, 'attempt': 0, 'text': 'SYNTHETIC-ORPHAN'})
    manifest = jsonl({'complete': False, 'readings': 1})
    spend = jsonl({'event': 'call', 'usd': 0.15}, {'event': 'retry'})
    invocations = jsonl({'status': 'SYNTHETIC'})
    ledger = jsonl({'event': 'declare', 'run': name, 'model': 'gpt-oss-20b', 'cap_usd': 0.16})
    for filename, raw in (('readings.jsonl', readings), ('run_manifest.json', manifest),
                          ('spend_log.jsonl', spend), ('invocations.jsonl', invocations)):
        (out_run / filename).write_bytes(raw)
    (local_run / 'responses.jsonl').write_bytes(responses)
    (output / 'study_ledger.jsonl').write_bytes(ledger)
    snapshot = private / 'OSS_CHECKPOINT_BACKUP_2026-10-30'
    snapshot.mkdir(mode=0o700)
    snap_out, snap_local = snapshot / 'out' / name, snapshot / 'local' / name
    snap_out.mkdir(parents=True)
    snap_local.mkdir(parents=True)
    for filename in ('readings.jsonl', 'run_manifest.json', 'spend_log.jsonl', 'invocations.jsonl'):
        (snap_out / filename).write_bytes((out_run / filename).read_bytes())
        (snap_out / filename).chmod(0o600)
    (snap_local / 'responses.jsonl').write_bytes(responses)
    (snap_local / 'responses.jsonl').chmod(0o600)
    item_raw = jsonl({'item_id': 'SYNTH-A'}, {'item_id': 'SYNTH-B'}, {'item_id': 'SYNTH-C'})
    (item_dir / 'synthetic.jsonl').write_bytes(item_raw)
    run = {'run': name, 'model': 'gpt-oss-20b', 'track': None, 'temperature': 0, 'samples': 1,
           'items': 'analysis/coling/out/items/synthetic.jsonl', 'list': 'SYNTH-LIST',
           'allow_test_items': True, 'cap_usd': 0.16}
    plan = {'options': {'out_root': 'analysis/coling/out/read', 'local_root': 'results/coling/read'},
            'runs': [run], 'routes': {'gpt-oss-20b': {'model_id': 'openai/gpt-oss-20b',
                                                      'provider': 'deepinfra/bf16', 'quantization': 'bf16'}},
            'lists': {'SYNTH-LIST': {'sha256': sha256(item_raw).hexdigest()}}}
    plan_raw = jsonl(plan)
    (output / '_launch/plan.json').write_bytes(plan_raw)
    selected = {'run': name, 'readings_sha256': sha256(readings).hexdigest(), 'responses_sha256': sha256(responses).hexdigest(),
                'manifest_sha256': sha256(manifest).hexdigest(), 'spend_log_sha256': sha256(spend).hexdigest(),
                'invocations_sha256': sha256(invocations).hexdigest(), 'ledger_sha256': sha256(ledger).hexdigest(),
                'logged_call_count': 1, 'logged_spend_usd': '0.15', 'proposed_run_cap_usd': '0.250000'}
    monkeypatch.setattr(resume, '_WORKSPACE', str(workspace))
    monkeypatch.setattr(resume, '_PRIVATE', str(private))
    monkeypatch.setattr(resume, '_PLAN_SHA', sha256(plan_raw).hexdigest())
    return {'workspace': workspace, 'private': private, 'output': output, 'local': local,
            'items': item_dir / 'synthetic.jsonl', 'snapshot': snapshot, 'selected': selected, 'plan': plan}


def test_selected_context_uses_only_matching_snapshot_and_skips_orphan(selected_fixture):
    with ExitStack() as stack:
        plan, run, index, raw_items, cap, calls, _ = resume._selected_context(selected_fixture['selected'], stack)
        assert run['run'] == 'SYNTH-RUN' and plan == selected_fixture['plan']
        assert index.completed == frozenset({('SYNTH-A', 0)}) and index.orphaned == frozenset({('SYNTH-B', 0)})
        assert b'SYNTH-C' in raw_items and cap == '0.250000' and calls == 1


@pytest.mark.parametrize('defect', ['reading', 'response', 'manifest', 'spend', 'invocations', 'ledger',
                                    'item_content', 'item_link', 'output_link', 'held_lock', 'run_name'])
def test_selected_context_refuses_changed_or_unsafe_sources(selected_fixture, defect):
    data = selected_fixture
    name = 'SYNTH-RUN'
    mapping = {'reading': data['output'] / name / 'readings.jsonl',
               'response': data['local'] / name / 'responses.jsonl',
               'manifest': data['output'] / name / 'run_manifest.json',
               'spend': data['output'] / name / 'spend_log.jsonl',
               'invocations': data['output'] / name / 'invocations.jsonl',
               'ledger': data['output'] / 'study_ledger.jsonl', 'item_content': data['items']}
    lockfd = None
    if defect in mapping:
        path = mapping[defect]
        path.write_bytes(path.read_bytes() + b' ')
    elif defect == 'item_link':
        path = data['items']
        saved = path.with_name('invented-original.jsonl')
        path.rename(saved)
        path.symlink_to(saved.name)
    elif defect == 'output_link':
        (data['output'] / 'invented-link').symlink_to(data['output'] / name, target_is_directory=True)
    elif defect == 'held_lock':
        import fcntl
        lockfd = os.open(data['output'] / '_launch/locks/openrouter.w0.lock', os.O_RDONLY | os.O_NOFOLLOW)
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        data['selected']['run'] = '../outside'
    try:
        with ExitStack() as stack, pytest.raises((resume.ResumeRefusal, OSError)):
            resume._selected_context(data['selected'], stack)
    finally:
        if lockfd is not None:
            os.close(lockfd)
    assert not (data['private'] / resume._STAGE_NAME).exists()


@contextmanager
def fake_registration(tmp_path, monkeypatch, defect=None):
    """An invented pushed-A4 world; no real worktree, Git state or key is used."""
    workspace = tmp_path / 'workspace'
    private = tmp_path / 'private'
    coling = workspace / 'analysis/coling'
    followup = coling / 'followup'
    (coling / 'plan').mkdir(parents=True)
    followup.mkdir(parents=True)
    private.mkdir(mode=0o700)
    selection_sha, plan_sha = 'a1b2c3d4' * 8, 'b2c3d4e5' * 8
    head, backup_commit = 'ab' * 20, 'cd' * 20

    file_bytes = {
        '__init__.py': b'SYNTHETIC PACKAGE INIT\n',
        'oss_one_shot_resume.py': b'SYNTHETIC RESUME SOURCE\n',
        'test_oss_one_shot_resume.py': b'SYNTHETIC RESUME TESTS\n',
        'oss_one_shot_cache.py': b'SYNTHETIC CACHE SOURCE\n',
        'test_oss_one_shot_cache.py': b'SYNTHETIC CACHE TESTS\n',
        'oss_one_shot_transport.py': b'SYNTHETIC TRANSPORT SOURCE\n',
        'test_oss_one_shot_transport.py': b'SYNTHETIC TRANSPORT TESTS\n',
        'oss_checkpoint_backup.py': b'SYNTHETIC BACKUP SOURCE\n',
    }
    for name, raw in file_bytes.items():
        (followup / name).write_bytes(raw)
    reader = (coling / 'read.py')
    launcher = (coling / 'launch.py')
    reader.parent.mkdir(parents=True, exist_ok=True)
    reader.write_bytes(b'SYNTHETIC FROZEN READER\n')
    launcher.write_bytes(b'SYNTHETIC FROZEN LAUNCHER\n')
    backup_code_sha = sha256(file_bytes['oss_checkpoint_backup.py']).hexdigest()
    read_sha = sha256((coling / 'read.py').read_bytes()).hexdigest()
    launch_sha = sha256((coling / 'launch.py').read_bytes()).hexdigest()

    selected = {'run': 'SYNTH-RUN', 'launch_plan_sha256': plan_sha,
                'one_physical_attempt_limit': 1, 'provisional_attempt_hold_usd': '0.10',
                'provisional_hold_is_proven_maximum': False, 'owner_selected_model_cap_usd': '10',
                'registered_study_cap_usd': '225', 'f1_operational_study_cap_usd': '200'}
    selection_raw = (json.dumps(selected, sort_keys=True, indent=2) + '\n').encode()
    selection_sha = sha256(selection_raw).hexdigest()
    verification_raw = (json.dumps({'source_and_snapshot_hashes_match': True, 'verified_files': 80},
                                   sort_keys=True, indent=2) + '\n').encode()
    backup_verify_sha = sha256(verification_raw).hexdigest()
    a4_record = {'commit': head if defect != 'a4_record_commit' else 'ef' * 20,
                 'remote_commit_verified': True, 'user_agent_verified': True}
    a4_raw = (json.dumps(a4_record, sort_keys=True, indent=2) + '\n').encode()

    prefix = (b'SYNTHETIC FROZEN PREFIX\n' * 20000)[:241581]
    on_disk_prefix = b'X' + prefix[1:] if defect == 'prefix' else prefix
    a4 = [b'### A4. One-physical-attempt original continuation',
          b'One-shot selection SHA256: `%s`' % selection_sha.encode()]
    for path, label in resume._registered_files():
        a4.append(('%s: `%s`' % (label, sha256(file_bytes[path.rsplit('/', 1)[1]]).hexdigest())).encode())
    plan = on_disk_prefix + b'\n' + b'\n'.join(a4) + b'\n'
    if defect == 'a4_heading':
        plan = plan.replace(b'### A4. One-physical-attempt original continuation', b'### A4. Removed')
    if defect == 'selection_line':
        plan = plan.replace(('One-shot selection SHA256: `%s`' % selection_sha).encode(), b'')
    if defect == 'resume_source':
        (followup / 'oss_one_shot_resume.py').write_bytes(b'SYNTHETIC ALTERED SOURCE\n')
    if defect == 'backup_code':
        (followup / 'oss_checkpoint_backup.py').write_bytes(b'SYNTHETIC ALTERED BACKUP\n')
    if defect == 'read_source':
        reader.write_bytes(b'SYNTHETIC ALTERED READER\n')
    (coling / 'plan/PLAN.md').write_bytes(plan)

    for name, raw in (('OSS_ONE_SHOT_SELECTION_PRIVATE.json', selection_raw),
                      ('OSS_CHECKPOINT_BACKUP_VERIFICATION_PRIVATE.json', verification_raw),
                      ('A4_ONESHOT_GIT_VERIFIED_PRIVATE.json', a4_raw)):
        (private / name).write_bytes(raw)
        (private / name).chmod(0o600)
    if defect == 'selection_record':
        (private / 'OSS_ONE_SHOT_SELECTION_PRIVATE.json').write_bytes(selection_raw + b' ')
    if defect == 'backup_verification':
        (private / 'OSS_CHECKPOINT_BACKUP_VERIFICATION_PRIVATE.json').write_bytes(verification_raw + b' ')

    now = datetime.now(timezone.utc)
    stamp = now - timedelta(seconds=400 if defect == 'key_status_stale' else 5)
    status_rows = jsonl({'event': 'reserved', 'reserved_usd': '0.10'}, {'event': 'request_intent'},
                        {'event': 'result', 'timestamp_utc': stamp.isoformat(), 'http_status': 200,
                         'metadata_valid': True, 'limit_usd': '220', 'usage_usd': '204',
                         'limit_remaining_usd': '16'})
    (private / 'ONE_SHOT_KEY_STATUS_PRIVATE.jsonl').write_bytes(status_rows)
    (private / 'ONE_SHOT_KEY_STATUS_PRIVATE.jsonl').chmod(0o600)
    if defect == 'key_status_missing':
        (private / 'ONE_SHOT_KEY_STATUS_PRIVATE.jsonl').unlink()

    holds = {'one_shot_original_attempt_usd': '0.10', 'one_shot_key_status_get_usd': '0.10'}
    verification = {'a4_git_registration_attempt_slots_reserved': 20,
                    'one_shot_physical_attempts_reserved': 1,
                    'one_shot_key_status_attempts_reserved': 1}
    if defect == 'budget_fields':
        verification.pop('one_shot_physical_attempts_reserved')
    if defect == 'budget_four_gets':
        verification['one_shot_key_status_attempts_reserved'] = 4
    if defect == 'budget_hold_mismatch':
        verification['one_shot_key_status_attempts_reserved'] = 2
    manifest = {'verification': verification, 'nonfinal_programme_liability_holds': holds,
                'one_shot_key_status_preflight': {'journal_sha256': sha256(status_rows).hexdigest()}}
    (private / 'EXECUTION_MANIFEST_DRAFT.json').write_bytes((json.dumps(manifest, sort_keys=True,
                                                                        indent=2) + '\n').encode())

    committed = {'analysis/coling/plan/PLAN.md': plan}
    for path, _ in resume._registered_files():
        committed[path] = file_bytes[path.rsplit('/', 1)[1]]
    if defect == 'absent_blob':
        committed.pop('analysis/coling/followup/oss_one_shot_cache.py')
    if defect == 'blob_differs':
        committed['analysis/coling/followup/oss_one_shot_transport.py'] += b'X'

    def fake_git(command, **_kwargs):
        assert command[0] == 'git'
        if command[1:3] == ['rev-parse', 'HEAD']:
            return SimpleNamespace(stdout=head + '\n')
        if command[1:3] == ['rev-parse', 'refs/remotes/origin/followup/coling-2027']:
            return SimpleNamespace(stdout=('ef' * 20 if defect == 'tracking' else head) + '\n')
        if command[1:3] == ['branch', '--show-current']:
            return SimpleNamespace(stdout=('wrong-branch' if defect == 'branch' else 'followup/coling-2027') + '\n')
        if command[1:3] == ['merge-base', '--is-ancestor']:
            if defect == 'ancestor':
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(stdout='')
        if command[1] == 'diff':
            if defect in ('dirty', 'f1_changed'):
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(stdout='')
        if command[1] == 'show':
            name = command[2].removeprefix('HEAD:')
            if name not in committed:
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(stdout=committed[name])
        raise AssertionError('unexpected Git command')

    for name in ('OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID',
                 'OPENAI_WEBHOOK_SECRET', 'OPENAI_BASE_URL', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)
    with monkeypatch.context() as scoped:
        scoped.setattr(resume, '_WORKSPACE', str(workspace))
        scoped.setattr(resume, '_PRIVATE', str(private))
        scoped.setattr(resume, '_SELECTION_SHA', selection_sha)
        scoped.setattr(resume, '_PLAN_SHA', plan_sha)
        scoped.setattr(resume, '_BACKUP_COMMIT', backup_commit)
        scoped.setattr(resume, '_BACKUP_CODE_SHA', backup_code_sha)
        scoped.setattr(resume, '_BACKUP_VERIFICATION_SHA', backup_verify_sha)
        scoped.setattr(resume, '_READ_SHA', read_sha)
        scoped.setattr(resume, '_LAUNCH_SHA', launch_sha)
        scoped.setattr(resume, '_PREFIX_SHA', sha256(prefix).hexdigest())
        scoped.setattr(resume, '_PREFIX_BYTES', len(prefix))
        scoped.setattr(resume, '_DEADLINE',
                       now - timedelta(seconds=1) if defect == 'deadline' else now + timedelta(hours=1))
        scoped.setattr(resume, '__file__',
                       str(followup / ('elsewhere.py' if defect == 'running_module' else 'oss_one_shot_resume.py')))
        scoped.setattr(resume.subprocess, 'run', fake_git)
        if defect == 'env':
            monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic')
        yield


def test_registration_accepts_exact_pushed_identities_and_fresh_key_status(tmp_path, monkeypatch):
    with fake_registration(tmp_path, monkeypatch):
        selected = resume._verify_registration()
    assert selected['run'] == 'SYNTH-RUN' and selected['one_physical_attempt_limit'] == 1


@pytest.mark.parametrize('defect', ['prefix', 'a4_heading', 'selection_line', 'resume_source', 'running_module',
                                    'backup_code', 'read_source', 'selection_record', 'backup_verification',
                                    'a4_record_commit', 'budget_fields', 'budget_four_gets', 'budget_hold_mismatch',
                                    'key_status_stale', 'key_status_missing',
                                    'env', 'deadline', 'tracking', 'branch', 'ancestor', 'dirty', 'f1_changed',
                                    'absent_blob', 'blob_differs'])
def test_registration_refuses_every_identity_or_authority_defect(tmp_path, monkeypatch, defect):
    with fake_registration(tmp_path, monkeypatch, defect):
        with pytest.raises(resume.ResumeRefusal):
            resume._verify_registration()
