"""Invented-only tests of the no-overwrite original-cache candidate."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import tempfile

import pytest

from analysis.coling.followup import oss_one_shot_cache as cache


KEY = 'sha256:' + 'a' * 64


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('network access is forbidden in these tests')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


@pytest.fixture
def root():
    with tempfile.TemporaryDirectory(prefix='oss-one-shot-cache-', dir='/tmp/opencode') as parent:
        path = Path(parent) / 'cache'
        path.mkdir(mode=0o700)
        yield path


def put(root, key=KEY, *, text='SYNTHETIC', served=None):
    return cache.put(str(root), key, text=text, prompt_tokens=3, completion_tokens=4,
                     total_tokens=7, served=served)


def path(root, key=KEY):
    digest = key.removeprefix('sha256:')
    return root / digest[:2] / (digest + '.json')


def test_missing_key_then_new_private_entry_is_readable(root):
    assert cache.get(str(root), KEY) is None
    served = {'model': 'SYNTHETIC', 'provider': 'SYNTHETIC', 'provider_names': ['SYNTHETIC'], 'metadata': None}
    put(root, served=served)
    value = cache.get(str(root), KEY)
    assert value == {'text': 'SYNTHETIC', 'prompt_tokens': 3, 'completion_tokens': 4,
                     'total_tokens': 7, 'served': served}
    target = path(root)
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.read_bytes() == (json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode()
    assert sorted(child.name for child in target.parent.iterdir()) == [target.name]


def test_no_served_metadata_matches_original_cache_shape(root):
    put(root)
    assert set(cache.get(str(root), KEY)) == {'text', 'prompt_tokens', 'completion_tokens', 'total_tokens'}


def test_existing_cache_entry_is_never_overwritten_even_if_identical(root):
    put(root)
    target = path(root)
    before, inode = target.read_bytes(), target.stat().st_ino
    with pytest.raises(cache.CacheRefusal, match='never overwritten'):
        put(root)
    assert target.read_bytes() == before and target.stat().st_ino == inode


@pytest.mark.parametrize('bad', ['sha256:', 'sha256:' + 'A' * 64, 'sha256:' + 'a' * 63,
                                 '../outside', 'sha256:' + 'a' * 64 + '/x', None, 1])
def test_invalid_key_is_refused_before_root_access(root, bad):
    with pytest.raises(cache.CacheRefusal, match='key'):
        cache.get(str(root), bad)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize('bad', ['/data/noctis/GitHub-Data/COLLIE-coling', '/tmp/opencode/../other', None])
def test_other_roots_are_refused_without_access(bad):
    with pytest.raises(cache.CacheRefusal, match='fixed scope'):
        cache.get(bad, KEY)


def test_fixture_root_must_remain_private(root):
    root.chmod(0o755)
    try:
        with pytest.raises(cache.CacheRefusal, match='private'):
            cache.get(str(root), KEY)
    finally:
        root.chmod(0o700)


def test_symlinked_cache_file_is_not_followed(root, tmp_path):
    target = path(root)
    target.parent.mkdir()
    outside = tmp_path / 'invented-outside.json'
    outside.write_text('{"text":"SYNTHETIC","prompt_tokens":3,"completion_tokens":4,"total_tokens":7}\n')
    target.symlink_to(outside)
    with pytest.raises(cache.CacheRefusal, match='unsafe'):
        cache.get(str(root), KEY)
    assert outside.is_file()


def test_hardlinked_cache_file_is_refused(root):
    put(root)
    target = path(root)
    alias = target.parent / 'invented-alias'
    os.link(target, alias)
    with pytest.raises(cache.CacheRefusal, match='links'):
        cache.get(str(root), KEY)
    assert target.is_file() and alias.is_file()


def test_symlinked_shard_is_not_followed(root, tmp_path):
    (root / 'aa').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        cache.get(str(root), KEY)


@pytest.mark.parametrize('raw', [b'{"text":"a","text":"b"}', b'{"text":NaN}', b'not-json', b'[]'])
def test_malformed_or_duplicate_cache_payload_is_refused(root, raw):
    target = path(root)
    target.parent.mkdir()
    target.write_bytes(raw)
    with pytest.raises(cache.CacheRefusal):
        cache.get(str(root), KEY)
    assert target.read_bytes() == raw


@pytest.mark.parametrize(('field', 'bad'), [('text', None), ('prompt_tokens', True),
                                            ('completion_tokens', -1), ('total_tokens', 10_000_001),
                                            ('served', [])])
def test_bad_cache_payload_values_are_refused_without_write(root, field, bad):
    values = {'text': 'SYNTHETIC', 'prompt_tokens': 3, 'completion_tokens': 4, 'total_tokens': 7, 'served': None}
    values[field] = bad
    with pytest.raises(cache.CacheRefusal):
        cache.put(str(root), KEY, **values)
    assert list(root.iterdir()) == []


def test_existing_temporary_blocks_reads_and_writes_without_deletion(root):
    shard = root / 'aa'
    shard.mkdir()
    temporary = shard / '.oneshot-invented.tmp'
    temporary.write_bytes(b'SYNTHETIC UNKNOWN')
    with pytest.raises(cache.CacheRefusal, match='temporary'):
        cache.get(str(root), KEY)
    with pytest.raises(cache.CacheRefusal, match='temporary'):
        put(root)
    assert temporary.read_bytes() == b'SYNTHETIC UNKNOWN'


def test_publication_collision_preserves_existing_entry_and_temporary(root, monkeypatch):
    original = cache._publish_new
    target = path(root)

    def collide(shard, temporary, name):
        target.write_bytes(b'SYNTHETIC EXISTING')
        return original(shard, temporary, name)

    monkeypatch.setattr(cache, '_publish_new', collide)
    with pytest.raises(cache.CacheRefusal, match='never overwritten'):
        put(root)
    assert target.read_bytes() == b'SYNTHETIC EXISTING'
    assert len(list(target.parent.glob('.oneshot-*.tmp'))) == 1


def test_changed_temporary_after_link_is_refused_without_cleanup(root, monkeypatch):
    original = cache._publish_new
    target = path(root)

    def mutate_after_link(shard, temporary, name):
        original(shard, temporary, name)
        fd = os.open(temporary, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, dir_fd=shard)
        try:
            os.write(fd, b'SYNTHETIC TAMPER')
        finally:
            os.close(fd)

    monkeypatch.setattr(cache, '_publish_new', mutate_after_link)
    with pytest.raises(cache.CacheRefusal, match='publication bytes'):
        put(root)
    assert target.read_bytes() == b'SYNTHETIC TAMPER' and target.stat().st_nlink == 2
    with pytest.raises(cache.CacheRefusal, match='temporary'):
        cache.get(str(root), KEY)


def test_sync_failure_preserves_temporary_and_refuses_automatic_retry(root, monkeypatch):
    def fail(_fd):
        raise OSError('synthetic sync failure')

    with monkeypatch.context() as scoped:
        scoped.setattr(cache.os, 'fsync', fail)
        with pytest.raises(OSError, match='synthetic sync failure'):
            put(root)
    # Failure may occur before a temporary is created when syncing a new shard.
    # Whatever exists is left in place; no existing cache entry is overwritten.
    assert not path(root).exists()


@pytest.mark.parametrize('_iteration', range(5))
def test_parallel_new_entries_never_overwrite_one_another(root, _iteration):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(put, root, KEY, text=text) for text in ('SYNTHETIC-A', 'SYNTHETIC-B')]
        results = []
        for future in futures:
            try:
                future.result()
                results.append('created')
            except (cache.CacheRefusal, OSError):
                results.append('refused')
    assert results.count('created') == 1
    target = path(root)
    assert target.is_file() and json.loads(target.read_bytes())['text'] in {'SYNTHETIC-A', 'SYNTHETIC-B'}


def test_excessive_cache_entry_is_refused(root, monkeypatch):
    monkeypatch.setattr(cache, '_MAX_BYTES', 12)
    with pytest.raises(cache.CacheRefusal, match='bound'):
        put(root)
    assert list(root.iterdir()) == []
