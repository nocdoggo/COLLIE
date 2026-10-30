"""Invented-only tests of the copy-only original checkpoint backup."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

from analysis.coling.followup import oss_checkpoint_backup as backup


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


@pytest.fixture
def invented():
    with tempfile.TemporaryDirectory(prefix='oss-backup-fixture-', dir='/tmp/opencode') as name:
        root = Path(name)
        workspace = root / 'workspace'
        output = workspace / 'analysis/coling/out/read'
        local = workspace / 'results/coling/read'
        launch = output / '_launch'
        locks = launch / 'locks'
        locks.mkdir(parents=True)
        local.mkdir(parents=True)
        private = root / 'private'
        private.mkdir(mode=0o700)
        for index in range(2):
            (locks / f'openrouter.w{index}.lock').write_bytes(b'')
        names = ('SYNTH-PARTIAL-A', 'SYNTH-PARTIAL-B', 'SYNTH-FINISHED', 'SYNTH-MISSING')
        calls = (2, 3, 1, 1)
        plan = {
            'options': {'out_root': 'analysis/coling/out/read', 'local_root': 'results/coling/read'},
            'routes': {'gpt-oss-20b': {'model_id': 'openai/gpt-oss-20b',
                                      'provider': 'deepinfra/bf16', 'quantization': 'bf16'}},
            'templates': {'SYNTH-TEMPLATE': 'a' * 64},
            'tracks': {},
            'lists': {'SYNTH-LIST': {'sha256': 'b' * 64}},
            'runs': [
                {'run': run, 'model': 'gpt-oss-20b', 'lane': 'openrouter', 'calls': count,
                 'template': 'SYNTH-TEMPLATE', 'shard': None, 'limit': None, 'samples': 1,
                 'temperature': 0, 'mask_names': False, 'shift_years': 0, 'track': None,
                 'list': 'SYNTH-LIST', 'item_ids_sha256': 'c' * 64}
                for run, count in zip(names, calls, strict=True)
            ],
        }
        raw_plan = encoded(plan)
        (launch / 'plan.json').write_bytes(raw_plan)
        for name, count, complete in zip(names[:3], calls[:3], (False, False, True), strict=True):
            out = output / name
            out.mkdir()
            raw_reading = ('SYNTH-READING-' + name + '\n').encode()
            (out / 'readings.jsonl').write_bytes(raw_reading)
            (out / 'spend_log.jsonl').write_bytes(('SYNTH-SPEND-' + name + '\n').encode())
            (out / 'invocations.jsonl').write_bytes(('SYNTH-INVOCATION-' + name + '\n').encode())
            manifest = {'model': 'gpt-oss-20b', 'model_id': 'openai/gpt-oss-20b',
                        'provider_object': {'order': ['deepinfra/bf16'], 'allow_fallbacks': False,
                                            'quantizations': ['bf16']},
                        'template': 'SYNTH-TEMPLATE', 'template_sha256': 'a' * 64,
                        'shard': None, 'limit': None, 'samples': 1, 'temperature': 0,
                        'mask_names': False, 'shift_years': 0, 'track_record_sha256': None,
                        'items_sha256': 'b' * 64, 'item_ids_sha256': 'c' * 64,
                        'expected_rows': count, 'readings': 1, 'complete': complete,
                        'readings_sha256': sha256(raw_reading).hexdigest()}
            (out / 'run_manifest.json').write_bytes(encoded(manifest))
            local_run = local / name
            local_run.mkdir()
            (local_run / 'responses.jsonl').write_bytes(('SYNTH-RESPONSE-' + name + '\n').encode())
        yield {'root': root, 'workspace': workspace, 'output': output, 'local': local, 'private': private,
               'plan': plan, 'plan_sha': sha256(raw_plan).hexdigest(), 'names': names}


def run(data, **changes):
    options = {'plan_sha256': data['plan_sha'], 'total_runs': 4, 'total_rows': 7,
               'finished': 1, 'partial': 2, 'missing': 1, 'recorded': 3, 'workers': 2,
               'synthetic_only': True}
    options.update(changes)
    return backup.backup_invented_fixture(str(data['root']), **options)


def test_copies_only_partial_files_to_new_private_snapshot(invented):
    result = run(invented)
    root, names = invented['private'] / 'snapshot', invented['names']
    assert (result.partial_runs, result.missing_runs, result.copied_files) == (2, 1, 10)
    assert root.stat().st_mode & 0o777 == 0o700
    for name in names[:2]:
        for filename in backup._OUT_FILES:
            source = invented['output'] / name / filename
            target = root / 'out' / name / filename
            assert target.read_bytes() == source.read_bytes() and target.stat().st_mode & 0o777 == 0o600
        source = invented['local'] / name / 'responses.jsonl'
        target = root / 'local' / name / 'responses.jsonl'
        assert target.read_bytes() == source.read_bytes() and target.stat().st_mode & 0o777 == 0o600
    assert not (root / 'out' / names[2]).exists() and not (root / 'out' / names[3]).exists()
    marker = json.loads((root / 'COMPLETE.json').read_bytes())
    journal = (root / 'snapshot.journal.jsonl').read_bytes()
    assert marker['journal_sha256'] == sha256(journal).hexdigest() == result.journal_sha256
    assert marker['copied_files'] == 10 and marker['copied_bytes'] == result.copied_bytes
    assert json.loads(journal.splitlines()[-1])['event'] == 'files_verified'


def test_existing_snapshot_is_never_overwritten(invented):
    run(invented)
    root = invented['private'] / 'snapshot'
    marker = (root / 'COMPLETE.json').read_bytes()
    with pytest.raises(FileExistsError):
        run(invented)
    assert (root / 'COMPLETE.json').read_bytes() == marker


@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink'])
def test_unsafe_source_links_are_refused_before_creating_snapshot(invented, unsafe):
    file = invented['output'] / invented['names'][0] / 'readings.jsonl'
    alias = file.parent / 'invented-alias'
    if unsafe == 'symlink':
        file.rename(alias)
        file.symlink_to(alias.name)
    else:
        os.link(file, alias)
    with pytest.raises(backup.BackupRefusal, match='unsafe'):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists() and alias.exists()


def test_changed_reading_hash_leaves_incomplete_snapshot_without_deleting_anything(invented):
    file = invented['output'] / invented['names'][0] / 'readings.jsonl'
    file.write_bytes(b'SYNTH-ALTERED-READING\n')  # Test modifies its own invented fixture.
    with pytest.raises(backup.BackupRefusal, match='manifest'):
        run(invented)
    snapshot = invented['private'] / 'snapshot'
    assert snapshot.is_dir() and not (snapshot / 'COMPLETE.json').exists()
    assert file.read_bytes() == b'SYNTH-ALTERED-READING\n'


@pytest.mark.parametrize('field', ['model_id', 'template_sha256', 'provider_object', 'item_ids_sha256'])
def test_partial_manifest_identity_mismatch_refuses_snapshot(invented, field):
    path = invented['output'] / invented['names'][0] / 'run_manifest.json'
    value = json.loads(path.read_bytes())
    value[field] = 'SYNTH-WRONG'
    path.write_bytes(encoded(value))
    with pytest.raises(backup.BackupRefusal, match='identity'):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists()


@pytest.mark.parametrize(('field', 'bad'), [('mask_names', 0), ('shift_years', False),
                                            ('temperature', False), ('samples', True)])
def test_manifest_booleans_cannot_impersonate_numeric_or_boolean_fields(invented, field, bad):
    path = invented['output'] / invented['names'][0] / 'run_manifest.json'
    value = json.loads(path.read_bytes())
    value[field] = bad
    path.write_bytes(encoded(value))
    with pytest.raises(backup.BackupRefusal, match='identity'):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists()


def test_provider_boolean_cannot_be_relabelled_as_zero(invented):
    path = invented['output'] / invented['names'][0] / 'run_manifest.json'
    value = json.loads(path.read_bytes())
    value['provider_object']['allow_fallbacks'] = 0
    path.write_bytes(encoded(value))
    with pytest.raises(backup.BackupRefusal, match='identity'):
        run(invented)


def test_plan_digest_mismatch_refuses_before_snapshot(invented):
    with pytest.raises(backup.BackupRefusal, match='plan hash'):
        run(invented, plan_sha256='0' * 64)
    assert not (invented['private'] / 'snapshot').exists()


@pytest.mark.parametrize('field,value', [('total_runs', 3), ('total_rows', 8), ('finished', 0),
                                          ('partial', 3), ('missing', 0), ('recorded', 4)])
def test_changed_inventory_or_states_refuse_before_snapshot(invented, field, value):
    with pytest.raises(backup.BackupRefusal):
        run(invented, **{field: value})
    assert not (invented['private'] / 'snapshot').exists()


def test_held_lane_lock_refuses_without_touching_sources(invented):
    lock = invented['output'] / '_launch/locks/openrouter.w0.lock'
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(backup.BackupRefusal, match='worker is active'):
            run(invented)
    finally:
        os.close(fd)
    assert not (invented['private'] / 'snapshot').exists()


@pytest.mark.parametrize('defect', ['missing', 'extra', 'symlink'])
def test_lane_lock_inventory_must_match_exactly(invented, defect):
    locks = invented['output'] / '_launch/locks'
    path = locks / 'openrouter.w1.lock'
    if defect == 'missing':
        path.unlink()
    elif defect == 'extra':
        (locks / 'openrouter.w2.lock').write_bytes(b'')
    else:
        path.unlink()
        path.symlink_to('openrouter.w0.lock')
    with pytest.raises((backup.BackupRefusal, OSError)):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists()


def test_missing_output_run_with_local_directory_is_not_treated_as_empty(invented):
    (invented['local'] / invented['names'][3]).mkdir()
    with pytest.raises(backup.BackupRefusal, match='unexpected local'):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists()


def test_malformed_or_duplicate_manifest_json_is_refused(invented):
    path = invented['output'] / invented['names'][0] / 'run_manifest.json'
    path.write_bytes(b'{"complete":false,"complete":true}\n')
    with pytest.raises(backup.BackupRefusal, match='duplicate'):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists()


def test_copy_failure_leaves_incomplete_snapshot_and_originals_unchanged(invented, monkeypatch):
    first = invented['output'] / invented['names'][0] / 'readings.jsonl'
    before = first.read_bytes()
    original = backup._copy_regular
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('invented disk failure')
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', fail_second)
    with pytest.raises(OSError, match='invented disk failure'):
        run(invented)
    root = invented['private'] / 'snapshot'
    assert root.is_dir() and not (root / 'COMPLETE.json').exists()
    assert first.read_bytes() == before


def test_source_changed_during_copy_is_not_marked_complete(invented, monkeypatch):
    first = invented['output'] / invented['names'][0] / 'readings.jsonl'
    original = backup._write_all
    changed = False

    def change_source(fd, data):
        nonlocal changed
        if not changed and data.startswith(b'SYNTH-READING-'):
            changed = True
            first.write_bytes(b'SYNTH-CHANGED-BY-TEST\n')
        original(fd, data)

    monkeypatch.setattr(backup, '_write_all', change_source)
    with pytest.raises(backup.BackupRefusal, match='changed'):
        run(invented)
    assert not (invented['private'] / 'snapshot/COMPLETE.json').exists()
    assert first.read_bytes() == b'SYNTH-CHANGED-BY-TEST\n'


def test_excessive_source_size_refuses_before_snapshot(invented, monkeypatch):
    monkeypatch.setattr(backup, '_MAX_SOURCE_FILE', 1)
    with pytest.raises(backup.BackupRefusal, match='size'):
        run(invented)
    assert not (invented['private'] / 'snapshot').exists()


@pytest.mark.parametrize('bad', [False, None, 1, 'yes'])
def test_fixture_entry_requires_explicit_synthetic_assertion(invented, bad):
    with pytest.raises(backup.BackupRefusal, match='synthetic-only'):
        run(invented, synthetic_only=bad)
    assert not (invented['private'] / 'snapshot').exists()


def test_fixture_entry_refuses_real_roots_before_access(monkeypatch):
    monkeypatch.setattr(backup, '_snapshot', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('accessed')))
    with pytest.raises(backup.BackupRefusal, match='synthetic scope'):
        backup.backup_invented_fixture('/data/noctis/GitHub-Data/COLLIE-coling', plan_sha256='0' * 64,
                                       total_runs=1, total_rows=1, finished=0, partial=1,
                                       missing=0, recorded=0, workers=1, synthetic_only=True)


def test_real_entry_refuses_without_exact_flag_before_registration_or_file_access(monkeypatch):
    monkeypatch.setattr(backup.sys, 'argv', ['oss_checkpoint_backup'])
    monkeypatch.setattr(backup, '_verify_registration', lambda: (_ for _ in ()).throw(AssertionError('accessed')))
    with pytest.raises(SystemExit, match='exact registered execution flag'):
        backup.main()


def test_fixture_copy_does_not_open_network_or_credentials(invented, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network access attempted')

    with monkeypatch.context() as scoped:
        scoped.setattr(socket, 'socket', forbidden)
        scoped.setattr(socket, 'create_connection', forbidden)
        result = run(invented)
    assert result.copied_files == 10


def test_changed_snapshot_file_is_detected_before_completion(invented, monkeypatch):
    original = backup._copy_regular
    calls = 0
    snapshot = invented['private'] / 'snapshot'
    changed = snapshot / 'out' / invented['names'][0] / 'readings.jsonl'

    def mutate_after_first(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            changed.write_bytes(b'SYNTH-CHANGED-COPY\n')
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', mutate_after_first)
    with pytest.raises(backup.BackupRefusal, match='snapshot file changed'):
        run(invented)
    assert changed.read_bytes() == b'SYNTH-CHANGED-COPY\n' and not (snapshot / 'COMPLETE.json').exists()


def test_snapshot_permissions_changed_before_completion_are_refused(invented, monkeypatch):
    original = backup._copy_regular
    calls = 0
    snapshot = invented['private'] / 'snapshot'
    changed = snapshot / 'out' / invented['names'][0] / 'readings.jsonl'

    def change_mode(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            changed.chmod(0o644)
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', change_mode)
    with pytest.raises(backup.BackupRefusal, match='changed|permissions'):
        run(invented)
    assert not (snapshot / 'COMPLETE.json').exists()


def test_finished_manifest_changed_during_copy_prevents_completion(invented, monkeypatch):
    original = backup._copy_regular
    changed = False
    manifest = invented['output'] / invented['names'][2] / 'run_manifest.json'

    def change_finished(*args):
        nonlocal changed
        if not changed:
            changed = True
            manifest.write_bytes(manifest.read_bytes() + b' ')
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', change_finished)
    with pytest.raises(backup.BackupRefusal, match='run state changed'):
        run(invented)
    assert not (invented['private'] / 'snapshot/COMPLETE.json').exists()


def test_post_marker_sync_failure_never_reports_success_or_deletes_marker(invented, monkeypatch):
    original = os.fsync
    snapshot = invented['private'] / 'snapshot'

    def fail_after_marker(fd):
        try:
            visible = os.readlink(f'/proc/self/fd/{fd}')
        except OSError:
            visible = ''
        if visible == str(snapshot) and (snapshot / 'COMPLETE.json').exists():
            raise OSError('invented final sync failure')
        return original(fd)

    monkeypatch.setattr(backup.os, 'fsync', fail_after_marker)
    with pytest.raises(OSError, match='invented final sync failure'):
        run(invented)
    assert (snapshot / 'COMPLETE.json').is_file()
    assert (invented['output'] / invented['names'][0] / 'readings.jsonl').is_file()


def test_missing_run_appearing_during_copy_prevents_complete_marker(invented, monkeypatch):
    original = backup._copy_regular
    created = False

    def create_missing(*args):
        nonlocal created
        if not created:
            created = True
            (invented['output'] / invented['names'][3]).mkdir()
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', create_missing)
    with pytest.raises(backup.BackupRefusal, match='missing run directory appeared'):
        run(invented)
    assert not (invented['private'] / 'snapshot/COMPLETE.json').exists()


def test_plan_changed_during_copy_prevents_complete_marker(invented, monkeypatch):
    original = backup._copy_regular
    altered = False
    path = invented['output'] / '_launch/plan.json'

    def change_plan(*args):
        nonlocal altered
        if not altered:
            altered = True
            path.write_bytes(path.read_bytes() + b' ')
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', change_plan)
    with pytest.raises(backup.BackupRefusal, match='plan or file count changed'):
        run(invented)
    assert not (invented['private'] / 'snapshot/COMPLETE.json').exists()


def test_snapshot_root_replaced_during_copy_is_not_marked_complete(invented, monkeypatch):
    original = backup._copy_regular
    replaced = False
    snapshot = invented['private'] / 'snapshot'
    moved = invented['private'] / 'invented-moved-snapshot'

    def replace_root(*args):
        nonlocal replaced
        if not replaced:
            replaced = True
            snapshot.rename(moved)
            snapshot.mkdir(mode=0o700)
        return original(*args)

    monkeypatch.setattr(backup, '_copy_regular', replace_root)
    with pytest.raises(backup.BackupRefusal, match='directory identity'):
        run(invented)
    assert not (snapshot / 'COMPLETE.json').exists() and not (moved / 'COMPLETE.json').exists()


@contextmanager
def fake_registration(invented, monkeypatch, defect=None):
    workspace = invented['workspace']
    coling = workspace / 'analysis/coling'
    plan_dir = coling / 'plan'
    followup = coling / 'followup'
    plan_dir.mkdir()
    followup.mkdir()
    source = b'SYNTHETIC REGISTERED SOURCE\n'
    tests = b'SYNTHETIC REGISTERED TESTS\n'
    reader = b'SYNTHETIC FROZEN READER\n'
    launcher = b'SYNTHETIC FROZEN LAUNCHER\n'
    (followup / 'oss_checkpoint_backup.py').write_bytes(source)
    (followup / 'test_oss_checkpoint_backup.py').write_bytes(tests)
    (coling / 'read.py').write_bytes(reader)
    (coling / 'launch.py').write_bytes(launcher)
    prefix = b'SYNTHETIC FROZEN PREFIX\n'
    body = (b'### A3. Copy-only checkpoint preservation\n'
            + f'Backup source SHA256: `{sha256(source).hexdigest()}`\n'.encode()
            + f'Backup fixture tests SHA256: `{sha256(tests).hexdigest()}`\n'.encode())
    plan = prefix + body
    (plan_dir / 'PLAN.md').write_bytes(plan)
    commit = 'a' * 40
    record = invented['private'] / 'A3_BACKUP_GIT_VERIFIED_PRIVATE.json'
    verified = {'commit': commit, 'remote_commit_verified': True, 'user_agent_verified': True}
    record.write_bytes(encoded(verified))
    record.chmod(0o600)
    committed = {'analysis/coling/plan/PLAN.md': plan,
                 'analysis/coling/followup/oss_checkpoint_backup.py': source,
                 'analysis/coling/followup/test_oss_checkpoint_backup.py': tests}
    if defect == 'prefix':
        (plan_dir / 'PLAN.md').write_bytes(b'X' + plan[1:])
    elif defect == 'source':
        (followup / 'oss_checkpoint_backup.py').write_bytes(source + b'X')
    elif defect == 'test':
        (followup / 'test_oss_checkpoint_backup.py').write_bytes(tests + b'X')
    elif defect == 'read':
        (coling / 'read.py').write_bytes(reader + b'X')
    elif defect == 'launch':
        (coling / 'launch.py').write_bytes(launcher + b'X')
    elif defect == 'verification':
        record.write_bytes(encoded(verified | {'remote_commit_verified': False}))
    elif defect == 'user_agent':
        record.write_bytes(encoded(verified | {'user_agent_verified': False}))
    elif defect == 'journal_mode':
        record.chmod(0o644)
    elif defect == 'journal_link':
        alternate = invented['private'] / 'invented-journal.json'
        alternate.write_bytes(record.read_bytes())
        record.unlink()
        record.symlink_to(alternate)
    elif defect == 'duplicate_a3':
        (plan_dir / 'PLAN.md').write_bytes(plan + body)
    elif defect == 'uncommitted_source':
        committed.pop('analysis/coling/followup/oss_checkpoint_backup.py')

    def fake_git(command, **kwargs):
        assert command[0] == 'git'
        if command[1:3] == ['rev-parse', 'HEAD']:
            return SimpleNamespace(stdout=commit + '\n')
        if command[1:3] == ['rev-parse', 'refs/remotes/origin/followup/coling-2027']:
            return SimpleNamespace(stdout=('b' * 40 if defect == 'tracking' else commit) + '\n')
        if command[1:3] == ['branch', '--show-current']:
            return SimpleNamespace(stdout=('wrong-branch' if defect == 'branch' else 'followup/coling-2027') + '\n')
        if command[1] == 'diff':
            if defect == 'dirty':
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(stdout=b'')
        if command[1] == 'show':
            name = command[2].removeprefix('HEAD:')
            if name not in committed:
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(stdout=committed[name])
        raise AssertionError('unexpected Git command')

    with monkeypatch.context() as scoped:
        scoped.setattr(backup, 'WORKSPACE', str(workspace))
        scoped.setattr(backup, 'PRIVATE_PARENT', str(invented['private']))
        scoped.setattr(backup, '__file__', str(followup / 'oss_checkpoint_backup.py'))
        scoped.setattr(backup, 'FROZEN_PREFIX_BYTES', len(prefix))
        scoped.setattr(backup, 'FROZEN_PREFIX_SHA256', sha256(prefix).hexdigest())
        scoped.setattr(backup, 'READ_SHA256', sha256(reader).hexdigest())
        scoped.setattr(backup, 'LAUNCH_SHA256', sha256(launcher).hexdigest())
        scoped.setattr(backup, '_DEADLINE', datetime.now(timezone.utc) + timedelta(hours=1))
        scoped.setattr(backup.subprocess, 'run', fake_git)
        yield


def test_registration_requires_exact_committed_files_and_verified_push(invented, monkeypatch):
    with fake_registration(invented, monkeypatch):
        backup._verify_registration()


@pytest.mark.parametrize('defect', ['tracking', 'branch', 'prefix', 'source', 'test', 'read', 'launch',
                                    'verification', 'user_agent', 'journal_mode', 'journal_link',
                                    'duplicate_a3', 'uncommitted_source', 'dirty'])
def test_registration_refuses_changed_or_unverified_identity(invented, monkeypatch, defect):
    with fake_registration(invented, monkeypatch, defect):
        with pytest.raises(backup.BackupRefusal):
            backup._verify_registration()
