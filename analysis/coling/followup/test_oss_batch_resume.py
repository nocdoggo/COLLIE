"""Invented-only tests for the paced dekallm batch continuation (A11)."""

from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace

import pytest

from analysis.coling.followup import oss_batch_resume as batch
from analysis.coling.followup import oss_batch_transport as transport
from analysis.coling.followup import oss_one_shot_resume as one_shot


def jsonl(*rows):
    return b''.join((json.dumps(row, sort_keys=True) + '\n').encode() for row in rows)


def index(readings, responses, count):
    return one_shot.index_checkpoint(readings, responses,
                                     expected_readings_sha256=sha256(readings).hexdigest(),
                                     expected_responses_sha256=sha256(responses).hexdigest(),
                                     expected_reading_count=count)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network access is forbidden in these tests')

    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


# --- selection-record validation -----------------------------------------------------------

def make_selection(**overrides):
    runs = [
        {'run': 'synth-a', 'new_run': 'synth-a.dk', 'template': 'predictive-v1', 'track': None,
         'temperature': 0, 'samples': 1, 'shard': '0/2', 'limit': None, 'mask_names': False,
         'shift_years': 0, 'list': 'synth', 'items': 'analysis/coling/out/items/synth.jsonl',
         'allow_test_items': True, 'never_invoked': False, 'route_provider': 'deepinfra/bf16',
         'planned_rows': 5, 'recorded_readings': 2, 'orphaned_pairs': 1, 'target_pairs': 2,
         'readings_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64, 'responses_sha256': 'c' * 64,
         'spend_log_sha256': 'd' * 64, 'invocations_sha256': 'e' * 64, 'logged_call_count': 1,
         'logged_spend_usd': '0.010000', 'historical_usd_per_call': '0.005000',
         'projected_usd': '0.010000', 'run_cap_usd': '0.05', 'items_sha256': 'f' * 64,
         'track_sha256': None},
        {'run': 'synth-b', 'new_run': 'synth-b.dk', 'template': 'predictive-track-v1', 'track': 'fit+dev',
         'temperature': 0, 'samples': 1, 'shard': '1/2', 'limit': None, 'mask_names': False,
         'shift_years': 0, 'list': 'synth', 'items': 'analysis/coling/out/items/synth.jsonl',
         'allow_test_items': True, 'never_invoked': True, 'route_provider': 'deepinfra/bf16',
         'planned_rows': 3, 'recorded_readings': 0, 'orphaned_pairs': 0, 'target_pairs': 3,
         'readings_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64, 'responses_sha256': 'c' * 64,
         'spend_log_sha256': 'd' * 64, 'invocations_sha256': 'e' * 64, 'logged_call_count': 0,
         'logged_spend_usd': '0.000000', 'historical_usd_per_call': '0.005000',
         'projected_usd': '0.015000', 'run_cap_usd': '0.05', 'items_sha256': 'f' * 64,
         'track_sha256': '1' * 64},
    ]
    selected = {'scope': 'dekallm-batch-continuation-selection', 'launch_plan_sha256': 'b2c3d4e5' * 8,
                'route': dict(batch._ROUTE), 'owner_selected_model_cap_usd': '10',
                'registered_study_cap_usd': '225', 'f1_operational_study_cap_usd': '200',
                'reask_orphaned_pairs': False, 'release_blocked_reservations': True,
                'planned_target_pairs': 5, 'skip_orphaned_pairs': 1,
                'total_run_caps_usd': '0.10', 'total_projected_usd': '0.025000',
                'hold_is_proven_maximum': False, 'runs': runs, 'ledger_sha256': '2' * 64}
    selected.update(overrides)
    return selected


SYNTH_PLAN_SHA = 'b2c3d4e5' * 8


@pytest.fixture()
def pinned_plan_sha(monkeypatch):
    monkeypatch.setattr(one_shot, '_PLAN_SHA', SYNTH_PLAN_SHA)


def test_selection_validation_accepts_the_invented_record(pinned_plan_sha):
    batch._validate_selection(make_selection())


@pytest.mark.parametrize('override', [
    {'scope': 'other'}, {'launch_plan_sha256': 'x' * 64},
    {'route': dict(batch._ROUTE, provider='deepinfra/bf16')},
    {'route': dict(batch._ROUTE, price_date='2026-10-01')},
    {'owner_selected_model_cap_usd': '6'}, {'f1_operational_study_cap_usd': '225'},
    {'reask_orphaned_pairs': True}, {'release_blocked_reservations': False},
    {'planned_target_pairs': 4}, {'skip_orphaned_pairs': 0},
    {'total_run_caps_usd': '0.20'}, {'total_projected_usd': '0.030000'},
    {'hold_is_proven_maximum': True},
])
def test_selection_validation_refuses_global_defects(pinned_plan_sha, override):
    with pytest.raises(batch.BatchStop):
        batch._validate_selection(make_selection(**override))


@pytest.mark.parametrize('mutation', [
    lambda runs: runs[0].update(new_run='synth-a.other'),
    lambda runs: runs[1].update(new_run='synth-a.dk'),
    lambda runs: runs[0].update(template='literal-v1'),
    lambda runs: runs[0].update(temperature=1),
    lambda runs: runs[0].update(samples=20),
    lambda runs: runs[0].update(target_pairs=0),
    lambda runs: runs[0].update(target_pairs=3),
    lambda runs: runs[0].update(planned_rows=6),
    lambda runs: runs[0].update(run_cap_usd='0.01'),
    lambda runs: runs[0].update(run_cap_usd='11'),
    lambda runs: runs[0].update(historical_usd_per_call=0.005),
    lambda runs: runs[0].update(projected_usd='0.020000'),
    lambda runs: runs[0].update(readings_sha256='short'),
    lambda runs: runs[0].update(track='other'),
    lambda runs: runs[0].update(route_provider='dekallm/bf16'),
    lambda runs: runs[0].update(mask_names='no'),
    lambda runs: runs[0].pop('items'),
    lambda runs: runs.append(dict(runs[0])),
])
def test_selection_validation_refuses_run_defects(pinned_plan_sha, mutation):
    selected = make_selection()
    mutation(selected['runs'])
    with pytest.raises(batch.BatchStop):
        batch._validate_selection(selected)


def test_selection_caps_may_not_pass_the_model_cap():
    selected = make_selection()
    for entry in selected['runs']:
        entry['run_cap_usd'] = '9.00'
    selected['total_run_caps_usd'] = '18.00'
    with pytest.raises(batch.BatchStop):
        batch._validate_selection(selected)


# --- the registration gate -----------------------------------------------------------------

@contextmanager
def fake_batch_world(tmp_path, monkeypatch, defect=None):
    """An invented pushed-A4/A11 world; no real worktree, Git state or key is used."""
    workspace = tmp_path / 'workspace'
    private = tmp_path / 'private'
    coling = workspace / 'analysis/coling'
    followup = coling / 'followup'
    (coling / 'plan').mkdir(parents=True)
    followup.mkdir(parents=True)
    private.mkdir(mode=0o700)
    head, backup_commit = 'ab' * 20, 'cd' * 20

    file_bytes = {'__init__.py': b'SYNTHETIC PACKAGE INIT\n',
                  'oss_one_shot_resume.py': b'SYNTHETIC RESUME SOURCE\n',
                  'test_oss_one_shot_resume.py': b'SYNTHETIC RESUME TESTS\n',
                  'oss_one_shot_cache.py': b'SYNTHETIC CACHE SOURCE\n',
                  'test_oss_one_shot_cache.py': b'SYNTHETIC CACHE TESTS\n',
                  'oss_one_shot_transport.py': b'SYNTHETIC TRANSPORT SOURCE\n',
                  'test_oss_one_shot_transport.py': b'SYNTHETIC TRANSPORT TESTS\n',
                  'oss_batch_transport.py': b'SYNTHETIC BATCH TRANSPORT SOURCE\n',
                  'test_oss_batch_transport.py': b'SYNTHETIC BATCH TRANSPORT TESTS\n',
                  'oss_batch_resume.py': b'SYNTHETIC BATCH SOURCE\n',
                  'test_oss_batch_resume.py': b'SYNTHETIC BATCH TESTS\n',
                  'oss_checkpoint_backup.py': b'SYNTHETIC BACKUP SOURCE\n'}
    for name, raw in file_bytes.items():
        (followup / name).write_bytes(raw)
    if defect == 'batch_source':
        (followup / 'oss_batch_resume.py').write_bytes(b'SYNTHETIC ALTERED BATCH SOURCE\n')
    reader, launcher = coling / 'read.py', coling / 'launch.py'
    reader.parent.mkdir(parents=True, exist_ok=True)
    reader.write_bytes(b'SYNTHETIC FROZEN READER\n')
    launcher.write_bytes(b'SYNTHETIC FROZEN LAUNCHER\n')
    read_sha = sha256(reader.read_bytes()).hexdigest()
    launch_sha = sha256(launcher.read_bytes()).hexdigest()
    if defect == 'read_source':
        reader.write_bytes(b'SYNTHETIC ALTERED READER\n')

    selected = make_selection()
    if defect == 'selection_scope':
        selected['scope'] = 'other'
    selection_raw = (json.dumps(selected, sort_keys=True, indent=2) + '\n').encode()
    selection_sha = sha256(selection_raw).hexdigest()
    verification_raw = (json.dumps({'source_and_snapshot_hashes_match': True, 'verified_files': 80},
                                   sort_keys=True, indent=2) + '\n').encode()
    a4_record = {'commit': head if defect != 'a4_record_commit' else 'ef' * 20,
                 'remote_commit_verified': True, 'user_agent_verified': True}
    a4_raw = (json.dumps(a4_record, sort_keys=True, indent=2) + '\n').encode()

    prefix = (b'SYNTHETIC FROZEN PREFIX\n' * 20000)[:241581]
    on_disk_prefix = b'X' + prefix[1:] if defect == 'prefix' else prefix
    plan_tail = [b'### A4. One-physical-attempt original continuation',
                 b'One-shot selection SHA256: `%s`' % ('a1b2c3d4' * 8).encode()]
    for path, label in (*one_shot._registered_files(), *batch._BATCH_FILES):
        name = path.rsplit('/', 1)[1]
        if defect == 'batch_hash_line' and name == 'oss_batch_resume.py':
            continue
        plan_tail.append(('%s: `%s`' % (label, sha256(file_bytes[name]).hexdigest())).encode())
    plan_tail.append(b'### A11. Synthetic batch continuation')
    if defect == 'a11_heading':
        plan_tail[-1] = b'### A12. Not this one'
    plan = on_disk_prefix + b'\n' + b'\n'.join(plan_tail) + b'\n'
    if defect == 'a4_heading':
        plan = plan.replace(b'### A4. One-physical-attempt original continuation', b'### A4. Removed')
    (coling / 'plan/PLAN.md').write_bytes(plan)

    for name, raw in (('OSS_BATCH_SELECTION_PRIVATE.json', selection_raw),
                      ('OSS_CHECKPOINT_BACKUP_VERIFICATION_PRIVATE.json', verification_raw),
                      ('A4_ONESHOT_GIT_VERIFIED_PRIVATE.json', a4_raw)):
        (private / name).write_bytes(raw)
        (private / name).chmod(0o600)
    if defect == 'selection_record':
        (private / 'OSS_BATCH_SELECTION_PRIVATE.json').write_bytes(selection_raw + b' ')

    now = datetime.now(timezone.utc)
    stamp = now - timedelta(seconds=400 if defect == 'key_status_stale' else 5)
    status_rows = jsonl({'event': 'reserved', 'reserved_usd': '0.10'}, {'event': 'request_intent'},
                        {'event': 'result', 'timestamp_utc': stamp.isoformat(), 'http_status': 200,
                         'metadata_valid': True, 'limit_usd': '250', 'usage_usd': '0',
                         'limit_remaining_usd': '250'})
    (private / 'ONE_SHOT_KEY_STATUS_PRIVATE.jsonl').write_bytes(status_rows)
    (private / 'ONE_SHOT_KEY_STATUS_PRIVATE.jsonl').chmod(0o600)

    gets = 37 if defect == 'budget_thirteen_gets' else 36
    verification = {'a4_git_registration_attempt_slots_reserved': 20,
                    'one_shot_physical_attempts_reserved': 1,
                    'one_shot_key_status_attempts_reserved': gets,
                    'a11_git_registration_attempt_slots_reserved': 19 if defect == 'budget_a11_slots' else 20,
                    'a11_batch_targets_reserved': 4 if defect == 'budget_targets' else 5}
    holds = {'one_shot_original_attempt_usd': '0.10',
             'one_shot_key_status_get_usd': f'{gets / 10:.2f}',
             'a11_batch_run_caps_usd': '0.20' if defect == 'budget_caps' else '0.10'}
    manifest = {'verification': verification, 'nonfinal_programme_liability_holds': holds,
                'one_shot_key_status_preflight': {'journal_sha256': sha256(status_rows).hexdigest()}}
    (private / 'EXECUTION_MANIFEST_DRAFT.json').write_bytes(
        (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())

    committed = {'analysis/coling/plan/PLAN.md': plan}
    for path, _ in (*one_shot._registered_files(), *batch._BATCH_FILES):
        committed[path] = file_bytes[path.rsplit('/', 1)[1]]
    if defect == 'blob_differs':
        committed['analysis/coling/followup/oss_batch_transport.py'] += b'X'

    def fake_git(command, **_kwargs):
        assert command[0] == 'git'
        if command[1:3] == ['rev-parse', 'HEAD']:
            return SimpleNamespace(stdout=head + '\n')
        if command[1:3] == ['rev-parse', 'refs/remotes/origin/followup/coling-2027']:
            return SimpleNamespace(stdout=('ef' * 20 if defect == 'tracking' else head) + '\n')
        if command[1:3] == ['branch', '--show-current']:
            return SimpleNamespace(stdout=('wrong' if defect == 'branch' else 'followup/coling-2027') + '\n')
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
        scoped.setattr(one_shot, '_WORKSPACE', str(workspace))
        scoped.setattr(one_shot, '_PRIVATE', str(private))
        scoped.setattr(one_shot, '_PLAN_SHA', 'b2c3d4e5' * 8)
        scoped.setattr(one_shot, '_BACKUP_COMMIT', backup_commit)
        scoped.setattr(one_shot, '_BACKUP_CODE_SHA', sha256(file_bytes['oss_checkpoint_backup.py']).hexdigest())
        scoped.setattr(one_shot, '_BACKUP_VERIFICATION_SHA', sha256(verification_raw).hexdigest())
        scoped.setattr(one_shot, '_READ_SHA', read_sha)
        scoped.setattr(one_shot, '_LAUNCH_SHA', launch_sha)
        scoped.setattr(one_shot, '_PREFIX_SHA', sha256(prefix).hexdigest())
        scoped.setattr(one_shot, '_PREFIX_BYTES', len(prefix))
        scoped.setattr(one_shot, '_DEADLINE',
                       now - timedelta(seconds=1) if defect == 'deadline' else now + timedelta(hours=1))
        scoped.setattr(one_shot.subprocess, 'run', fake_git)
        scoped.setattr(batch, '_BATCH_SELECTION_SHA', selection_sha)
        scoped.setattr(batch, '__file__',
                       str(followup / ('elsewhere.py' if defect == 'running_module' else 'oss_batch_resume.py')))
        if defect == 'env':
            monkeypatch.setenv('OPENROUTER_API_KEY', 'synthetic')
        yield


def test_gate_accepts_exact_pushed_identities_and_fresh_key_status(tmp_path, monkeypatch):
    with fake_batch_world(tmp_path, monkeypatch):
        selected = batch._verify_batch_registration()
    assert selected['planned_target_pairs'] == 5 and len(selected['runs']) == 2


@pytest.mark.parametrize('defect', ['prefix', 'a4_heading', 'a11_heading', 'batch_hash_line', 'batch_source',
                                    'running_module', 'read_source', 'selection_record', 'selection_scope',
                                    'a4_record_commit', 'budget_thirteen_gets', 'budget_a11_slots',
                                    'budget_targets', 'budget_caps', 'key_status_stale', 'env', 'deadline',
                                    'tracking', 'branch', 'ancestor', 'dirty', 'f1_changed', 'blob_differs'])
def test_gate_refuses_every_identity_or_authority_defect(tmp_path, monkeypatch, defect):
    with fake_batch_world(tmp_path, monkeypatch, defect):
        with pytest.raises(batch.BatchStop):
            batch._verify_batch_registration()


# --- batch context --------------------------------------------------------------------------

@contextmanager
def fake_study(tmp_path, monkeypatch, defect=None):
    """An invented two-run study tree: one partial original, one never-invoked run."""
    workspace = tmp_path / 'workspace'
    private = tmp_path / 'private'
    out = workspace / 'analysis/coling/out/read'
    local = workspace / 'results/coling/read'
    items_dir = workspace / 'analysis/coling/out/items'
    for folder in (out / '_launch', out / 'synth-a', local / 'synth-a', items_dir,
                   private / 'OSS_CHECKPOINT_BACKUP_2026-10-30/out/synth-a',
                   private / 'OSS_CHECKPOINT_BACKUP_2026-10-30/local/synth-a'):
        folder.mkdir(parents=True)
    private.chmod(0o700)
    (private / 'OSS_CHECKPOINT_BACKUP_2026-10-30').chmod(0o700)
    locks = out / '_launch/locks'
    locks.mkdir()
    for worker in range(8):
        (locks / f'openrouter.w{worker}.lock').write_bytes(b'')

    items_raw = jsonl({'item_id': 'SYNTH-A-1', 'synthetic': True}, {'item_id': 'SYNTH-A-2', 'synthetic': True})
    track_raw = b'{"synthetic": "track"}\n'
    (items_dir / 'synth.jsonl').write_bytes(items_raw)
    (items_dir / 'track_synth.json').write_bytes(track_raw)

    readings = jsonl({'item_id': 'SYNTH-A-1', 'sample': 0}, {'item_id': 'SYNTH-A-2', 'sample': 0})
    responses = jsonl({'item_id': 'SYNTH-A-1', 'sample': 0, 'attempt': 0},
                      {'item_id': 'SYNTH-A-2', 'sample': 0, 'attempt': 0},
                      {'item_id': 'SYNTH-A-9', 'sample': 0, 'attempt': 0})
    manifest = {'complete': False, 'readings': 2, 'expected_rows': 5}
    spend_snapshot = jsonl({'event': 'call', 'usd': 0.01})
    spend = spend_snapshot + jsonl({'event': 'error', 'error': 'synthetic one-shot row'})
    invocation_snapshot = jsonl({'model': 'gpt-oss-20b'})
    invocation = invocation_snapshot + jsonl({'status': 'error', 'model': 'gpt-oss-20b'})
    if defect == 'spend_rewritten':
        spend = jsonl({'event': 'call', 'usd': 0.02})
    (out / 'synth-a/readings.jsonl').write_bytes(readings)
    (out / 'synth-a/run_manifest.json').write_bytes((json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())
    (out / 'synth-a/spend_log.jsonl').write_bytes(spend)
    (out / 'synth-a/invocations.jsonl').write_bytes(invocation)
    (local / 'synth-a/responses.jsonl').write_bytes(responses)
    if defect == 'readings_touched':
        (out / 'synth-a/readings.jsonl').write_bytes(readings + jsonl({'item_id': 'SYNTH-A-3', 'sample': 0}))
    snap = private / 'OSS_CHECKPOINT_BACKUP_2026-10-30'
    for name, raw in (('readings.jsonl', readings), ('run_manifest.json',
                                                      (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()),
                      ('invocations.jsonl', invocation_snapshot),
                      ('spend_log.jsonl', spend_snapshot)):
        (snap / 'out/synth-a' / name).write_bytes(raw)
        (snap / 'out/synth-a' / name).chmod(0o600)
    (snap / 'local/synth-a/responses.jsonl').write_bytes(responses)
    (snap / 'local/synth-a/responses.jsonl').chmod(0o600)
    if defect == 'virgin_dir':
        (out / 'synth-b').mkdir()
    if defect == 'dk_foreign':
        dk = out / 'synth-a.dk'
        dk.mkdir()
        (dk / 'run_manifest.json').write_bytes((json.dumps(
            {'model': 'gpt-oss-20b', 'provider_object': {'order': ['deepinfra/bf16'], 'allow_fallbacks': False},
             'template': 'predictive-v1', 'temperature': 0, 'samples': 1, 'shard': '0/2'},
            sort_keys=True, indent=2) + '\n').encode())

    plan = {'options': {'out_root': 'analysis/coling/out/read', 'local_root': 'results/coling/read'},
            'routes': {'gpt-oss-20b': {'model_id': 'openai/gpt-oss-20b', 'provider':
                                       'siliconflow/fp8' if defect == 'route_changed' else 'deepinfra/bf16',
                                       'quantization': 'bf16'}},
            'lists': {'synth': {'sha256': sha256(items_raw).hexdigest()}},
            'tracks': {'fit+dev': {'path': 'analysis/coling/out/items/track_synth.json',
                                   'sha256': sha256(track_raw).hexdigest()}},
            'runs': [
                {'run': 'synth-a', 'model': 'gpt-oss-20b', 'template': 'predictive-v1', 'track': None,
                 'temperature': 0.0, 'samples': 1, 'shard': '0/2', 'limit': None, 'mask_names': False,
                 'shift_years': 0, 'list': 'synth', 'items': 'analysis/coling/out/items/synth.jsonl',
                 'cap_usd': 0.5, 'allow_test_items': True},
                {'run': 'synth-b', 'model': 'gpt-oss-20b', 'template': 'predictive-track-v1',
                 'track': 'fit+dev', 'temperature': 0.0, 'samples': 1, 'shard': '1/2', 'limit': None,
                 'mask_names': False, 'shift_years': 0, 'list': 'synth',
                 'items': 'analysis/coling/out/items/synth.jsonl', 'cap_usd': 0.5, 'allow_test_items': True}]}
    if defect == 'plan_row':
        plan['runs'][0]['template'] = 'probe-v1'
    plan_raw = (json.dumps(plan, sort_keys=True, indent=2) + '\n').encode()
    (out / '_launch/plan.json').write_bytes(plan_raw)

    ledger = jsonl({'event': 'declare', 'run': 'synth-a', 'model': 'gpt-oss-20b', 'cap_usd': 0.5})
    (out / 'study_ledger.jsonl').write_bytes(ledger if defect != 'ledger_changed' else ledger + jsonl({'event': 'declare'}))

    selected = make_selection()
    selected['ledger_sha256'] = sha256(ledger).hexdigest()
    for entry, field, raw in ((selected['runs'][0], 'readings_sha256', readings),
                              (selected['runs'][0], 'manifest_sha256', (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()),
                              (selected['runs'][0], 'responses_sha256', responses),
                              (selected['runs'][0], 'spend_log_sha256', spend),
                              (selected['runs'][0], 'invocations_sha256', invocation)):
        entry[field] = sha256(raw).hexdigest()
    selected['runs'][0]['items_sha256'] = sha256(items_raw).hexdigest()
    selected['runs'][1]['items_sha256'] = sha256(items_raw).hexdigest()
    selected['runs'][1]['track_sha256'] = sha256(track_raw).hexdigest()
    if defect == 'items_hash':
        (items_dir / 'synth.jsonl').write_bytes(items_raw + jsonl({'item_id': 'SYNTH-A-3'}))
        selected['runs'][0]['items_sha256'] = sha256(items_raw).hexdigest()

    with monkeypatch.context() as scoped:
        scoped.setattr(one_shot, '_WORKSPACE', str(workspace))
        scoped.setattr(one_shot, '_PRIVATE', str(private))
        scoped.setattr(one_shot, '_PLAN_SHA', sha256(plan_raw).hexdigest())
        yield {'workspace': workspace, 'out': out, 'local': local, 'selected': selected}


def take_specs(tmp_path, monkeypatch, defect=None):
    with fake_study(tmp_path, monkeypatch, defect) as world, ExitStack() as stack:
        plan, specs, prior = batch._batch_context(world['selected'], stack)
        return plan, specs, prior, world


def test_batch_context_builds_specs_from_verified_originals(tmp_path, monkeypatch):
    plan, specs, prior, world = take_specs(tmp_path, monkeypatch)
    assert [spec.original for spec in specs] == ['synth-a', 'synth-b']
    assert [spec.new_run for spec in specs] == ['synth-a.dk', 'synth-b.dk']
    assert [spec.target for spec in specs] == [2, 3]
    assert specs[0].index.completed == frozenset({('SYNTH-A-1', 0), ('SYNTH-A-2', 0)})
    assert specs[0].index.orphaned == frozenset({('SYNTH-A-9', 0)})
    assert specs[1].index.completed == frozenset() and specs[1].never_invoked is True
    assert prior == 0 and specs[0].items_raw == (world['workspace'] / 'analysis/coling/out/items/synth.jsonl').read_bytes()


@pytest.mark.parametrize('defect', ['readings_touched', 'spend_rewritten', 'ledger_changed', 'plan_row',
                                    'route_changed', 'virgin_dir', 'dk_foreign', 'items_hash'])
def test_batch_context_refuses_state_defects(tmp_path, monkeypatch, defect):
    with pytest.raises(batch.BatchStop):
        take_specs(tmp_path, monkeypatch, defect)


# --- reservation release --------------------------------------------------------------------

class FakeReadForRelease:
    def __init__(self, held, code=0, fail=False):
        self.held_map = held
        self.calls = []
        self.code = code
        self.fail = fail

    def held_by_run(self, out_root):
        return self.held_map

    def main(self, args):
        self.calls.append(list(args))
        if self.fail:
            raise RuntimeError('synthetic refusal')
        return self.code


class FakeLaunch:
    @staticmethod
    def harness_args(plan, row, mode):
        return ['--items', row['items'], '--template', row['template'], '--model', row['model'],
                '--out-root', 'analysis/coling/out/read', '--local-root', 'results/coling/read',
                '--run-name', row['run'], '--spend-cap-usd', f"{row['cap_usd']:.6f}", '--allow-live']


def spec_pair(never_invoked=False):
    row = {'run': 'synth-a', 'items': 'analysis/coling/out/items/synth.jsonl', 'template': 'predictive-v1',
           'model': 'gpt-oss-20b', 'cap_usd': 0.5}
    items_raw = jsonl({'item_id': 'SYNTH-A-1'}, {'item_id': 'SYNTH-A-2'})
    return batch.RunSpec(original='synth-a', new_run='synth-a.dk', row=row,
                         index=one_shot.CheckpointIndex(frozenset(), frozenset()), target=2,
                         cap_usd='0.30', projected_usd='0.250000', items_path=row['items'],
                         items_raw=items_raw, track_path=None, track_sha=None,
                         never_invoked=never_invoked, prior_calls=0)


def test_pinned_track_skips_specs_that_carry_no_track(tmp_path, monkeypatch):
    """10 November 2026: the first track-condition run stopped before its first send with
    TypeError, because the pinned-track hash lookup called os.path.abspath over every spec's
    track_path and the untracked runs carry None. The lookup must consider only specs with a
    track, and must still refuse a path that no spec pins."""
    import dataclasses
    from hashlib import sha256 as sha256_file
    track = tmp_path / 'track.json'
    track.write_bytes(b'{"schema": "synth"}\n')
    digest = sha256_file(track.read_bytes()).hexdigest()
    tracked = dataclasses.replace(spec_pair(), track_path=str(track), track_sha=digest)
    untracked = dataclasses.replace(spec_pair(), new_run='synth-b.dk')
    read, client, physical, state, fd = installed(tmp_path, monkeypatch,
                                                  specs=[untracked, tracked])
    try:
        assert read.load_track_record(Path(track)).synthetic is True
        with pytest.raises(batch.BatchStop, match='unregistered track path'):
            read.load_track_record(tmp_path / 'other.json')
    finally:
        client.close()
        os.close(fd)


def test_release_redeclares_blocked_runs_at_their_recorded_spend():
    read = FakeReadForRelease({'synth-a': {'model': 'gpt-oss-20b', 'open': True, 'spent_usd': 0.12,
                                            'cap_usd': 0.50, 'held_usd': 0.50}})
    selected = make_selection()
    released = batch._release_reservations(read, FakeLaunch, {'runs': []}, [spec_pair()], selected)
    assert released == [('synth-a', '0.120000')]
    args = read.calls[0]
    assert args[args.index('--spend-cap-usd') + 1] == '0.120000'
    assert '--declare-only' in args and '--allow-live' not in args


def test_release_is_idempotent_and_skips_virgin_runs():
    read = FakeReadForRelease({'synth-a': {'model': 'gpt-oss-20b', 'open': True, 'spent_usd': 0.12,
                                            'cap_usd': 0.120000, 'held_usd': 0.12}})
    released = batch._release_reservations(read, FakeLaunch, {'runs': []},
                                           [spec_pair(), spec_pair(never_invoked=True)], make_selection())
    assert released == [] and read.calls == []


@pytest.mark.parametrize('held, kind', [
    ({'synth-a': {'model': 'other', 'open': True, 'spent_usd': 0.1, 'cap_usd': 0.5}}, 'not open'),
    ({'synth-a': {'model': 'gpt-oss-20b', 'open': False, 'spent_usd': 0.1, 'cap_usd': 0.5}}, 'not open'),
    ({}, 'not open'),
])
def test_release_refuses_runs_not_open_for_the_model(held, kind):
    read = FakeReadForRelease(held)
    with pytest.raises(batch.BatchStop):
        batch._release_reservations(read, FakeLaunch, {'runs': []}, [spec_pair()], make_selection())


def test_release_refuses_unauthorized_or_failing_declarations():
    selected = make_selection(release_blocked_reservations=False)
    with pytest.raises(batch.BatchStop):
        batch._release_reservations(FakeReadForRelease({}), FakeLaunch, {'runs': []}, [spec_pair()], selected)
    failing = FakeReadForRelease({'synth-a': {'model': 'gpt-oss-20b', 'open': True, 'spent_usd': 0.12,
                                               'cap_usd': 0.50, 'held_usd': 0.50}}, fail=True)
    with pytest.raises(batch.BatchStop):
        batch._release_reservations(failing, FakeLaunch, {'runs': []}, [spec_pair()], make_selection())
    refusing = FakeReadForRelease({'synth-a': {'model': 'gpt-oss-20b', 'open': True, 'spent_usd': 0.12,
                                                'cap_usd': 0.50, 'held_usd': 0.50}}, code=3)
    with pytest.raises(batch.BatchStop):
        batch._release_reservations(refusing, FakeLaunch, {'runs': []}, [spec_pair()], make_selection())


# --- batch budget ---------------------------------------------------------------------------

def test_budget_accepts_the_released_envelope():
    read = SimpleNamespace(held_by_run=lambda root: {
        'other-gpt': {'model': 'gpt-oss-20b', 'held_usd': 9.60},
        'other-model': {'model': 'llama-3.3-70b', 'held_usd': 100.0},
        'synth-a.dk': {'model': 'gpt-oss-20b', 'held_usd': 0.20, 'spent_usd': 0.19}})
    batch._check_batch_budget(read, [spec_pair()])


def test_budget_refuses_model_study_and_run_cap_breaches():
    over_model = SimpleNamespace(held_by_run=lambda root: {
        'other-gpt': {'model': 'gpt-oss-20b', 'held_usd': 9.75}})
    with pytest.raises(batch.BatchStop):
        batch._check_batch_budget(over_model, [spec_pair()])
    over_study = SimpleNamespace(held_by_run=lambda root: {
        'other-model': {'model': 'llama-3.3-70b', 'held_usd': 199.50}})
    with pytest.raises(batch.BatchStop):
        batch._check_batch_budget(over_study, [spec_pair()])
    spent_dk = SimpleNamespace(held_by_run=lambda root: {
        'synth-a.dk': {'model': 'gpt-oss-20b', 'held_usd': 0.35, 'spent_usd': 0.35}})
    with pytest.raises(batch.BatchStop):
        batch._check_batch_budget(spent_dk, [spec_pair()])


# --- hooks ----------------------------------------------------------------------------------

class FakeReadModule:
    SpendCapReached = one_shot.ResumeRefusal
    CallCapReached = one_shot.ResumeRefusal
    ServedModelMismatch = one_shot.ResumeRefusal

    class ReadItem:
        @classmethod
        def from_dict(cls, value):
            return SimpleNamespace(item_id=value['item_id'])

    class Route:
        def __init__(self, model_id, provider, quantization, price):
            self.model_id, self.provider, self.quantization, self.price = model_id, provider, quantization, price

    class ReadCache:
        def __init__(self, root):
            self.root = root

    class GuardedTransport:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    ROUTES = {'gpt-oss-20b': Route('openai/gpt-oss-20b', 'deepinfra/bf16', 'bf16', (0.03, 0.14, '2026-10-01'))}
    OUT_ROOT = '/synthetic/out/read'
    LOCAL_ROOT = '/synthetic/local/read'

    @staticmethod
    def provider_object(route):
        pin = {'order': [route.provider], 'allow_fallbacks': False}
        if route.quantization:
            pin['quantizations'] = [route.quantization]
        return pin

    @staticmethod
    def load_items(path):
        raise AssertionError('unhooked load_items was called')

    @staticmethod
    def load_track_record(path):
        return SimpleNamespace(synthetic=True)

    @staticmethod
    def _sha256_file(path):
        return sha256(Path(path).read_bytes()).hexdigest()

    @staticmethod
    def read_items(reader, items, *, samples=1, rows=None):
        raise AssertionError('unhooked read_items was called')


def installed(tmp_path, monkeypatch, specs=None, pre_override=False):
    import httpx as httpx_module
    read = FakeReadModule()
    read.ROUTES = dict(FakeReadModule.ROUTES)
    read.OUT_ROOT = str(tmp_path / 'out/read')
    read.LOCAL_ROOT = str(tmp_path / 'local/read')
    if pre_override:
        read.ROUTES['gpt-oss-20b'] = FakeReadModule.Route('openai/gpt-oss-20b', 'dekallm/bf16', 'bf16',
                                                          batch._PRICE)
    read.__file__ = str(tmp_path / 'read.py')
    (tmp_path / 'read.py').write_bytes(b'SYNTHETIC FROZEN READER\n')
    endpoints = SimpleNamespace(EMPTY_ECHO_RETRIES=2)
    openai_module = SimpleNamespace(OpenAI=lambda *a, **k: SimpleNamespace())
    cache = SimpleNamespace(REAL_ROOT=str(tmp_path / 'cache'))
    journal = tmp_path / 'send.journal.jsonl'
    planned = sum(spec.target for spec in (specs or [spec_pair()]))
    journal.write_bytes(transport.batch_reservation_bytes('0' * 64, planned,
                                                          2 * planned + 12 * len(specs or [spec_pair()]) + 600))
    journal.chmod(0o600)
    fd = os.open(journal, os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    with monkeypatch.context() as scoped:
        scoped.setattr(batch, '_BATCH_SELECTION_SHA', '0' * 64)
        client, physical, state = batch._install_batch_hooks(
            read, endpoints, openai_module, httpx_module, cache, transport,
            specs or [spec_pair()], send_journal_fd=fd,
            stop_after_utc=datetime(2027, 1, 4, 23, 59, 49, tzinfo=timezone.utc))
    return read, client, physical, state, fd


def test_hooks_pin_the_dekallm_route_and_registered_transport(tmp_path, monkeypatch):
    read, client, physical, state, fd = installed(tmp_path, monkeypatch)
    route = read.ROUTES['gpt-oss-20b']
    assert (route.provider, route.quantization, route.price) == ('dekallm/bf16', 'bf16', batch._PRICE)
    assert read.provider_object(route) == transport.PROVIDER
    client.close()
    os.close(fd)


def test_hooks_refuse_an_already_changed_route_table(tmp_path, monkeypatch):
    with pytest.raises(batch.BatchStop):
        installed(tmp_path, monkeypatch, pre_override=True)


def test_hooks_force_the_paced_guard_parameters(tmp_path, monkeypatch):
    read, client, physical, state, fd = installed(tmp_path, monkeypatch)
    guard = read.GuardedTransport(inner=None, endpoint=None, spend_log=None,
                                  spend_cap_usd=1, max_physical_calls=5)
    assert (guard.kwargs['max_attempts'], guard.kwargs['min_interval_s'],
            guard.kwargs['base_delay_s'], guard.kwargs['max_delay_s']) == (6, transport.MIN_SPACING_S, 8.0, 240.0)
    client.close()
    os.close(fd)
    with pytest.raises(batch.BatchStop):
        read.GuardedTransport(inner=None, endpoint=None, spend_log=None, spend_cap_usd=1,
                              max_physical_calls=5, max_attempts=2)


def test_hooks_pin_inputs_and_file_hashes(tmp_path, monkeypatch):
    spec = spec_pair()
    read, client, physical, state, fd = installed(tmp_path, monkeypatch, specs=[spec])
    items = read.load_items(spec.items_path)
    assert [item.item_id for item in items] == ['SYNTH-A-1', 'SYNTH-A-2']
    assert read._sha256_file(spec.items_path) == sha256(spec.items_raw).hexdigest()
    assert read._sha256_file(read.__file__) == one_shot._READ_SHA
    state['spec'] = spec
    readings = str(Path(read.OUT_ROOT) / 'synth-a.dk/readings.jsonl')
    Path(readings).parent.mkdir(parents=True, exist_ok=True)
    Path(readings).write_bytes(b'{"synthetic": true}\n')
    assert read._sha256_file(readings) == sha256(b'{"synthetic": true}\n').hexdigest()
    with pytest.raises(batch.BatchStop):
        read.load_items('analysis/coling/out/items/other.jsonl')
    with pytest.raises(batch.BatchStop):
        read._sha256_file('/unregistered/anywhere')
    client.close()
    os.close(fd)


def test_hooks_accept_the_harness_relative_root_spellings(tmp_path, monkeypatch):
    """The third dispatch stopped because pinned_sha compared the harness's RELATIVE root
    spelling of the readings file against absolute allowlist keys; every pinned-key
    comparison is now made on the normalized absolute spelling."""
    spec = spec_pair()
    read, client, physical, state, fd = installed(tmp_path, monkeypatch, specs=[spec])
    assert read._sha256_file(Path(spec.items_path)) == sha256(spec.items_raw).hexdigest()
    state['spec'] = spec
    readings = Path(read.OUT_ROOT) / 'synth-a.dk/readings.jsonl'
    readings.parent.mkdir(parents=True, exist_ok=True)
    readings.write_bytes(b'{"synthetic": true}\n')
    monkeypatch.chdir(tmp_path)
    relative = readings.relative_to(tmp_path)
    assert read._sha256_file(relative) == sha256(b'{"synthetic": true}\n').hexdigest()
    with pytest.raises(batch.BatchStop):
        read._sha256_file(Path('unregistered') / 'relative.jsonl')
    client.close()
    os.close(fd)


def test_hooks_pin_the_addresses_of_the_registered_items(tmp_path, monkeypatch):
    """A19: the counted transport may carry only the public contact addresses of the
    hash-pinned items. The body-wide "@" ban refused item 58 of e3-a.s7.dk, whose
    notice text carries one such address, so the pin is derived from the items here."""
    import dataclasses
    spec = dataclasses.replace(spec_pair(), items_raw=jsonl(
        {'item_id': 'SYNTH-A-1', 'related_information': 'write to synth@example.test'},
        {'item_id': 'SYNTH-A-2'}))
    read, client, physical, state, fd = installed(tmp_path, monkeypatch, specs=[spec])
    try:
        assert physical._allowed_addresses == frozenset({'synth@example.test'})
    finally:
        client.close()
        os.close(fd)


def test_mains_send_journal_open_flags_satisfy_the_counted_transport(tmp_path):
    """The 5 November 2026 dispatch stopped pre-send: main() opened the send
    journal write-only while the counted transport preads its reservation row,
    so the shared flags must open the journal for reading as well as appending."""
    import httpx as httpx_module
    planned = 11
    journal = tmp_path / 'send.journal.jsonl'
    fd = os.open(journal, batch._SEND_JOURNAL_OPEN, 0o600)
    try:
        os.write(fd, transport.batch_reservation_bytes('0' * 64, planned, 2 * planned + 600))
        os.fsync(fd)
        transport.CountedPacedTransport(
            httpx_module.HTTPTransport(verify=True, trust_env=False, retries=0), fd,
            selection_sha256='0' * 64, planned_targets=planned, max_sends=2 * planned + 600,
            stop_after_utc=datetime(2027, 1, 4, 23, 59, 49, tzinfo=timezone.utc))
    finally:
        os.close(fd)


def test_a_write_only_send_journal_is_refused_by_the_counted_transport(tmp_path):
    """The inverse pin: a write-only journal fd must keep being refused."""
    import httpx as httpx_module
    planned = 11
    journal = tmp_path / 'send.journal.jsonl'
    journal.write_bytes(transport.batch_reservation_bytes('0' * 64, planned, 2 * planned + 600))
    journal.chmod(0o600)
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        with pytest.raises(transport.BatchRefusal, match='private send journal is unsafe'):
            transport.CountedPacedTransport(
                httpx_module.HTTPTransport(verify=True, trust_env=False, retries=0), fd,
                selection_sha256='0' * 64, planned_targets=planned, max_sends=2 * planned + 600,
                stop_after_utc=datetime(2027, 1, 4, 23, 59, 49, tzinfo=timezone.utc))
    finally:
        os.close(fd)


def test_filtered_reader_completes_exactly_the_target_set(tmp_path, monkeypatch):
    items = [SimpleNamespace(item_id=name) for name in ('SYNTH-A-1', 'SYNTH-A-2', 'SYNTH-A-9',
                                                        'SYNTH-A-3', 'SYNTH-A-4')]

    def make_spec(target):
        return batch.RunSpec(original='synth-a', new_run='synth-a.dk', row={},
                             index=one_shot.CheckpointIndex(frozenset({('SYNTH-A-1', 0)}),
                                                            frozenset({('SYNTH-A-9', 0)})),
                             target=target, cap_usd='0.30', projected_usd='0.250000',
                             items_path='synth.jsonl',
                             items_raw=jsonl({'item_id': 'SYNTH-A-1'}), track_path=None,
                             track_sha=None, never_invoked=False, prior_calls=0)

    spec = make_spec(4)
    read, client, physical, state, fd = installed(tmp_path, monkeypatch, specs=[spec])
    state['spec'] = spec
    seen = []

    class Reader:
        responses = []

        def read(self, item, sample):
            seen.append((item.item_id, sample))
            return {'item_id': item.item_id, 'sample': sample}

    rows, status = read.read_items(Reader(), items, samples=1, rows=[])
    assert seen == [('SYNTH-A-2', 0), ('SYNTH-A-3', 0), ('SYNTH-A-4', 0)] and len(rows) == 3
    assert status == 'partial: batch read 3 of 4 target pairs'
    state['spec'] = make_spec(3)
    rows, status = read.read_items(Reader(), items, samples=1, rows=[])
    assert len(rows) == 3 and status == 'complete'
    state['spec'] = None
    with pytest.raises(batch.BatchStop):
        read.read_items(Reader(), items, samples=1, rows=[])
    client.close()
    os.close(fd)


# --- run loop -------------------------------------------------------------------------------

class RunLoopRead:
    OUT_ROOT = None

    def __init__(self, results, tmp_path):
        self.results = results
        self.closed = []
        self.main_calls = []
        self.held = {}
        RunLoopRead.OUT_ROOT = str(tmp_path / 'out/read')

    def main(self, args):
        self.main_calls.append(list(args))
        new_run = args[args.index('--run-name') + 1]
        behavior = self.results[new_run]
        out_dir = Path(self.OUT_ROOT) / new_run
        out_dir.mkdir(parents=True, exist_ok=True)
        if behavior['fail']:
            raise SystemExit('refused: synthetic refusal') if behavior['fail'] == 'exit' else RuntimeError('synthetic failure')
        manifest = {'status': behavior['status'], 'readings': behavior['readings'],
                    'complete': False, 'guard': {'physical_calls_total': behavior['readings']}}
        (out_dir / 'run_manifest.json').write_text(json.dumps(manifest, sort_keys=True))
        if behavior.get('bad_spend'):
            (out_dir / 'spend_log.jsonl').write_bytes(b'{"event": "call"}\n')
        else:
            (out_dir / 'spend_log.jsonl').write_bytes(
                jsonl(*[{'event': 'call', 'usd': 0.01} for _ in range(behavior.get('calls', behavior['readings']))]))
        return behavior['code']

    def close_run(self, out_root, *, run, model, spent_usd):
        self.closed.append((run, model, spent_usd))


class RunLoopLaunch:
    @staticmethod
    def harness_args(plan, row, mode):
        return ['--items', row['items'], '--run-name', row['run'], '--spend-cap-usd', '0.500000',
                '--allow-live', '--out-root', 'analysis/coling/out/read']


def run_loop_specs():
    row_a = {'run': 'synth-a', 'items': 'i.jsonl', 'template': 'predictive-v1', 'model': 'gpt-oss-20b',
             'cap_usd': 0.5}
    row_c = {'run': 'synth-c', 'items': 'i.jsonl', 'template': 'predictive-v1', 'model': 'gpt-oss-20b',
             'cap_usd': 0.5}
    return [batch.RunSpec(original='synth-a', new_run='synth-a.dk', row=row_a,
                          index=one_shot.CheckpointIndex(frozenset(), frozenset()), target=2,
                          cap_usd='0.30', projected_usd='0.250000', items_path='i.jsonl',
                          items_raw=b'{"item_id": "SYNTH-A-1"}\n', track_path=None,
                          track_sha=None, never_invoked=False, prior_calls=0),
            batch.RunSpec(original='synth-c', new_run='synth-c.dk', row=row_c,
                          index=one_shot.CheckpointIndex(frozenset(), frozenset()), target=1,
                          cap_usd='0.20', projected_usd='0.100000', items_path='i.jsonl',
                          items_raw=b'{"item_id": "SYNTH-A-1"}\n', track_path=None,
                          track_sha=None, never_invoked=False, prior_calls=0)]


class FakePhysical:
    def __init__(self):
        self.runs = []

    def set_run(self, label):
        self.runs.append(label)


def test_run_loop_closes_complete_runs_and_stops_at_shortfalls(tmp_path):
    read = RunLoopRead({'synth-a.dk': {'status': 'complete', 'readings': 2, 'code': 0, 'fail': False},
                        'synth-c.dk': {'status': 'aborted: synthetic', 'readings': 0, 'code': 3, 'fail': False}},
                       tmp_path)
    specs = run_loop_specs()
    physical = FakePhysical()
    journal = tmp_path / 'batch.journal.jsonl'
    journal.write_bytes(b'')
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = batch._run_batch(read, RunLoopLaunch, {}, specs, {'spec': None}, physical, None, fd)
    os.close(fd)
    assert read.closed == [('synth-a.dk', 'gpt-oss-20b', 0.02)]
    assert result['complete_runs'] == 1 and result['stopped_run'] == 'synth-c.dk'
    assert physical.runs == ['synth-a.dk', 'synth-c.dk']
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    assert [row['event'] for row in rows] == ['run_intent', 'run_result', 'run_intent', 'run_result', 'batch_stopped']
    assert rows[1]['closed'] is True and rows[3]['closed'] is False
    args = read.main_calls[0]
    assert args[args.index('--run-name') + 1] == 'synth-a.dk'
    assert args[args.index('--spend-cap-usd') + 1] == '0.30'
    assert args[args.index('--max-physical-calls') + 1] == str(0 + 2 * 2 + 12)
    assert '--model-cap-usd' in args and 'A2: prospective gpt-oss cap 10' in args


def test_run_loop_stops_after_an_exception_and_never_continues(tmp_path):
    read = RunLoopRead({'synth-a.dk': {'status': 'error', 'readings': 1, 'code': 3, 'fail': True},
                        'synth-c.dk': {'status': 'complete', 'readings': 1, 'code': 0, 'fail': False}},
                       tmp_path)
    specs = run_loop_specs()
    journal = tmp_path / 'batch.journal.jsonl'
    journal.write_bytes(b'')
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = batch._run_batch(read, RunLoopLaunch, {}, specs, {'spec': None}, FakePhysical(), None, fd)
    os.close(fd)
    assert result['stopped_run'] == 'synth-a.dk' and read.closed == []
    assert [call[call.index('--run-name') + 1] for call in read.main_calls] == ['synth-a.dk']
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    assert rows[1]['error_type'] == 'raised RuntimeError: synthetic failure'


def test_run_loop_records_a_reader_systemexit_refusal_and_stops_cleanly(tmp_path):
    """The frozen reader signals refusals with SystemExit, which the loop must record as a
    named failure — not let it escape and lose the run_result and batch_stopped rows."""
    read = RunLoopRead({'synth-a.dk': {'status': 'refused', 'readings': 0, 'code': None, 'fail': 'exit'},
                        'synth-c.dk': {'status': 'complete', 'readings': 1, 'code': 0, 'fail': False}},
                       tmp_path)
    specs = run_loop_specs()
    journal = tmp_path / 'batch.journal.jsonl'
    journal.write_bytes(b'')
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = batch._run_batch(read, RunLoopLaunch, {}, specs, {'spec': None}, FakePhysical(), None, fd)
    os.close(fd)
    assert result['stopped_run'] == 'synth-a.dk' and read.closed == []
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    assert rows[1]['error_type'] == 'raised SystemExit: refused: synthetic refusal'
    assert rows[1]['closed'] is False and rows[2]['event'] == 'batch_stopped'


def test_run_loop_records_close_error_on_a_malformed_spend_row(tmp_path):
    """A spend log the wrapper's own validator rejects (BatchStop) is journalled as a
    close_error stop, not an unrecorded crash."""
    read = RunLoopRead({'synth-a.dk': {'status': 'complete', 'readings': 2, 'code': 0, 'fail': False,
                                       'bad_spend': True}}, tmp_path)
    specs = run_loop_specs()[:1]
    journal = tmp_path / 'batch.journal.jsonl'
    journal.write_bytes(b'')
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = batch._run_batch(read, RunLoopLaunch, {}, specs, {'spec': None}, FakePhysical(), None, fd)
    os.close(fd)
    assert result['stopped_run'] == 'synth-a.dk' and read.closed == []
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    assert rows[1]['close_error'] == 'BatchStop' and rows[1]['closed'] is False
    assert rows[2]['event'] == 'batch_stopped'


def test_run_loop_refuses_a_target_shortfall(tmp_path):
    read = RunLoopRead({'synth-a.dk': {'status': 'complete', 'readings': 1, 'code': 0, 'fail': False}},
                       tmp_path)
    specs = run_loop_specs()[:1]
    journal = tmp_path / 'batch.journal.jsonl'
    journal.write_bytes(b'')
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC)
    result = batch._run_batch(read, RunLoopLaunch, {}, specs, {'spec': None}, FakePhysical(), None, fd)
    os.close(fd)
    assert result['stopped_run'] == 'synth-a.dk' and read.closed == []


# --- the frozen reader's own route machinery ------------------------------------------------

def test_the_real_frozen_reader_accepts_the_runtime_route_override():
    from analysis.coling import read as real_read
    original = real_read.ROUTES['gpt-oss-20b']
    assert original.provider == 'deepinfra/bf16'
    route = real_read.Route('openai/gpt-oss-20b', 'dekallm/bf16', 'bf16', batch._PRICE)
    assert real_read.provider_object(route) == transport.PROVIDER
    assert real_read.route_tag(route) != real_read.route_tag(original)
    endpoint = real_read.route_endpoint('gpt-oss-20b')
    assert (endpoint.price_input_per_mtok, endpoint.price_output_per_mtok, endpoint.price_date) == (0.03, 0.14, '2026-10-01')
    real_read.ROUTES['gpt-oss-20b'] = route
    try:
        endpoint = real_read.route_endpoint('gpt-oss-20b')
        assert (endpoint.price_input_per_mtok, endpoint.price_output_per_mtok, endpoint.price_date) == batch._PRICE
        assert endpoint.extra_body['provider'] == transport.PROVIDER
        assert real_read.route_errors('gpt-oss-20b') == []
    finally:
        real_read.ROUTES['gpt-oss-20b'] = original
