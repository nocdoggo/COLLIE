"""Invented-only tests for the SQLite/sidecar replay experiment."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading

import pytest

from analysis.coling.followup import oss_replay_synthetic as replay
from analysis.coling.followup import oss_sidecar_synthetic as sidecar
from analysis.coling.followup.oss_safeguards import (
    DecodingKind,
    SyntheticDecoding,
    SyntheticHistory,
    SyntheticOutput,
    SyntheticReading,
    append_synthetic,
)


def connect(path):
    connection = sqlite3.connect(str(path), isolation_level=None, timeout=10)
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


@pytest.fixture
def fixtures():
    roots = []
    connections = []

    def directory(prefix):
        root = Path('/tmp/opencode') / (prefix + secrets.token_hex(4))
        root.mkdir(mode=0o700)
        roots.append(root)
        return root

    def database():
        path = directory('oss-journal-fixture-') / 'journal.sqlite3'
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        connection = connect(path)
        connections.append(connection)
        return path, connection, replay.SyntheticJournal(connection, synthetic_only=True)

    def original():
        root = directory('oss-sidecar-fixture-')
        decoding = SyntheticDecoding(DecodingKind.ORIGINAL_DEFAULT)
        history = SyntheticHistory.empty(decoding)
        first = SyntheticOutput('SYNTH-ITEM-A', decoding, 'SYNTH-SOURCE-A', SyntheticReading.ALPHA)
        raw = append_synthetic(history, (first,)).combined_bytes
        path = root / 'history.bin'
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        return root, raw, sha256(raw).hexdigest()

    yield database, original
    for connection in connections:
        connection.close()
    # These directories were created exclusively by this fixture. Never remove
    # anything outside them, including a caller-provided or pre-existing path.
    for root in reversed(roots):
        if root.is_symlink():
            root.unlink()
        elif root.is_dir():
            for child in root.iterdir():
                if child.is_dir() and not child.is_symlink():
                    child.rmdir()
                else:
                    child.unlink()
            root.rmdir()


def register(journal, root, digest, request='SYNTH-REQUEST-A', item='SYNTH-ITEM-B'):
    journal.register(request_id=request, item_id=item, root=str(root), original_sha256=digest)


def reserve(journal, request='SYNTH-REQUEST-A', ticket='SYNTH-TICKET-A', bound=10):
    journal.reserve(request_id=request, ticket_id=ticket, bound_units=bound)


def answer(journal, ticket='SYNTH-TICKET-A', *, reading=SyntheticReading.BETA, charge=7):
    transport = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER, reading, charge),))
    state = journal.dispatch(ticket, transport)
    assert transport.consumed == 1
    return state


def expected_sidecar(raw, ticket='SYNTH-TICKET-A', reading=SyntheticReading.BETA, item='SYNTH-ITEM-B'):
    decoding = SyntheticDecoding(DecodingKind.ORIGINAL_DEFAULT)
    output = SyntheticOutput(item, decoding, 'SYNTH-SOURCE-TICKET' + ticket.removeprefix('SYNTH-TICKET-'), reading)
    return append_synthetic(SyntheticHistory(raw, decoding), (output,)).combined_bytes


def child(path, program):
    script = """
import os
import sqlite3
import sys
from analysis.coling.followup import oss_replay_synthetic as replay
from analysis.coling.followup import oss_sidecar_synthetic as sidecar
from analysis.coling.followup.oss_safeguards import SyntheticReading
connection = sqlite3.connect(sys.argv[1], isolation_level=None, timeout=10)
connection.execute('PRAGMA foreign_keys=ON')
journal = replay.SyntheticJournal(connection, synthetic_only=True)
""" + program
    environment = {'HOME': '/tmp/opencode', 'TMPDIR': '/tmp/opencode', 'PATH': '/usr/bin:/bin',
                   'PYTHONPATH': '.', 'PYTHONDONTWRITEBYTECODE': '1'}
    worktree = Path(__file__).resolve().parents[3]
    return subprocess.run([sys.executable, '-c', script, str(path)], cwd=worktree, env=environment,
                          capture_output=True, text=True, timeout=20, check=False)


def test_answer_is_durably_bound_to_the_separate_synthetic_sidecar(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    assert answer(journal) == 'settled'
    receipt = journal.publish('SYNTH-TICKET-A')
    expected = expected_sidecar(before)
    assert receipt.status == 'created'
    assert receipt.original_sha256 == digest and receipt.sidecar_sha256 == sha256(expected).hexdigest()
    assert receipt.response_sha256 == sha256(b'SYNTH-REPLY-V1|ANSWER|BETA\n').hexdigest()
    assert (root / 'history.bin').read_bytes() == before
    assert (root / 'sidecar.bin').read_bytes() == expected
    inode = (root / 'sidecar.bin').stat().st_ino
    assert journal.publish('SYNTH-TICKET-A').status == 'verified_existing'
    assert (root / 'sidecar.bin').stat().st_ino == inode
    state = journal.status()
    assert (state.attempts, state.spent_units, state.held_units, state.pending_publications) == (1, 7, 0, 0)


def test_returned_unknown_charge_keeps_the_body_but_blocks_publication_and_retry(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    assert answer(journal, charge=None) == 'reply_unknown'
    assert (journal.status().held_units, journal.status().unknown_attempts) == (10, 1)
    with pytest.raises(replay.JournalRefusal):
        journal.publish('SYNTH-TICKET-A')
    with pytest.raises(replay.JournalRefusal):
        reserve(journal, ticket='SYNTH-TICKET-B')
    with pytest.raises(replay.JournalRefusal):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=7) == 'settled'
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=7) == 'unchanged'
    assert journal.publish('SYNTH-TICKET-A').status == 'created'
    assert (root / 'history.bin').read_bytes() == before
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before)


@pytest.mark.parametrize('kind', [replay.MockReplyKind.TRANSIENT, replay.MockReplyKind.EMPTY_ECHO])
def test_each_observed_synthetic_nonanswer_needs_a_new_reserved_ticket(fixtures, kind):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    first = replay.MockTransport((replay.MockReply(kind, None, 2),))
    assert journal.dispatch('SYNTH-TICKET-A', first) == 'settled'
    reserve(journal, ticket='SYNTH-TICKET-B')
    assert answer(journal, 'SYNTH-TICKET-B') == 'settled'
    receipt = journal.publish('SYNTH-TICKET-B')
    assert receipt.status == 'created' and journal.status().attempts == 2
    assert journal.status().spent_units == 9 and journal.status().held_units == 0
    assert (root / 'history.bin').read_bytes() == before
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before, 'SYNTH-TICKET-B')


@pytest.mark.parametrize('kind', [replay.MockReplyKind.REFUSAL, replay.MockReplyKind.FATAL])
def test_definite_synthetic_refusal_or_fatal_result_cannot_be_retried_or_published(fixtures, kind):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    assert journal.dispatch('SYNTH-TICKET-A', replay.MockTransport((replay.MockReply(kind, None, 2),))) == 'settled'
    with pytest.raises(replay.JournalRefusal, match='retry'):
        reserve(journal, ticket='SYNTH-TICKET-B')
    with pytest.raises(replay.JournalRefusal, match='answer'):
        journal.publish('SYNTH-TICKET-A')
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_missing_synthetic_reply_remains_sent_and_billing_alone_cannot_unlock_it(fixtures):
    database, original = fixtures
    path, connection, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    with pytest.raises(replay.JournalRefusal, match='did not return'):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=0) == 'awaiting_response'
    connection.close()
    reopened_connection = connect(path)
    try:
        reopened = replay.SyntheticJournal(reopened_connection, synthetic_only=True)
        assert (reopened.status().held_units, reopened.status().unknown_attempts) == (10, 1)
        unused = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER, SyntheticReading.BETA, 1),))
        with pytest.raises(replay.JournalRefusal, match='unsent'):
            reopened.dispatch('SYNTH-TICKET-A', unused)
        with pytest.raises(replay.JournalRefusal, match='retry'):
            reserve(reopened, ticket='SYNTH-TICKET-B')
        assert unused.consumed == 0
    finally:
        reopened_connection.close()
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_charge_above_bound_is_retained_and_globally_blocks_mock_use(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    assert answer(journal, charge=11) == 'breached'
    state = journal.status()
    assert (state.attempts, state.spent_units, state.held_units, state.bound_breaches) == (1, 11, 0, 1)
    with pytest.raises(replay.JournalRefusal, match='bound'):
        journal.publish('SYNTH-TICKET-A')
    with pytest.raises(replay.JournalRefusal, match='bound'):
        reserve(journal, ticket='SYNTH-TICKET-B')
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_conflicting_late_synthetic_bill_is_retained_without_deleting_sidecar(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    journal.publish('SYNTH-TICKET-A')
    published = (root / 'sidecar.bin').read_bytes()
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=7) == 'confirmed'
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-B', charge_units=8) == 'conflict'
    assert journal.status().conflicts == 1
    with pytest.raises(replay.JournalRefusal, match='conflict'):
        journal.publish('SYNTH-TICKET-A')
    assert (root / 'history.bin').read_bytes() == before and (root / 'sidecar.bin').read_bytes() == published


def test_one_fixture_root_and_ticket_cannot_be_rebound_in_the_same_journal(fixtures):
    database, original = fixtures
    _, _, journal = database()
    first, before, digest = original()
    second, _, second_digest = original()
    register(journal, first, digest)
    register(journal, first, digest)  # Exact registration is idempotent.
    with pytest.raises(replay.JournalRefusal, match='rebound'):
        register(journal, second, second_digest)
    with pytest.raises(replay.JournalRefusal, match='already assigned'):
        register(journal, first, digest, request='SYNTH-REQUEST-B', item='SYNTH-ITEM-C')
    register(journal, second, second_digest, request='SYNTH-REQUEST-B', item='SYNTH-ITEM-C')
    reserve(journal)
    with pytest.raises(replay.JournalRefusal, match='already reserved'):
        reserve(journal, request='SYNTH-REQUEST-B')
    assert (first / 'history.bin').read_bytes() == before


def test_concurrent_connections_cannot_consume_one_synthetic_ticket_twice(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    transport = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER, SyntheticReading.BETA, 7),))
    barrier = threading.Barrier(2)

    def worker():
        connection = connect(path)
        try:
            local = replay.SyntheticJournal(connection, synthetic_only=True)
            barrier.wait(timeout=10)
            try:
                return local.dispatch('SYNTH-TICKET-A', transport)
            except replay.JournalRefusal:
                return 'refused'
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(results) == ['refused', 'settled']
    assert transport.consumed == 1 and journal.status().attempts == 1


def test_real_process_exit_after_mock_reply_never_resends_the_unknown_attempt(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    result = child(path, """
journal._record_mock_reply = lambda *_: os._exit(41)
transport = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER, SyntheticReading.BETA, 7),))
journal.dispatch('SYNTH-TICKET-A', transport)
""")
    assert result.returncode == 41, result.stderr
    assert (journal.status().held_units, journal.status().unknown_attempts) == (10, 1)
    with pytest.raises(replay.JournalRefusal, match='unsent'):
        answer(journal)
    with pytest.raises(replay.JournalRefusal, match='retry'):
        reserve(journal, ticket='SYNTH-TICKET-B')
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_real_process_exit_after_durable_intent_recovers_the_same_publication(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    result = child(path, """
journal._finish_publication = lambda *_: os._exit(42)
journal.publish('SYNTH-TICKET-A')
""")
    assert result.returncode == 42, result.stderr
    assert journal.status().pending_publications == 1 and not (root / 'sidecar.bin').exists()
    with pytest.raises(replay.JournalRefusal, match='pending'):
        reserve(journal, ticket='SYNTH-TICKET-B')
    assert journal.publish('SYNTH-TICKET-A').status == 'created'
    assert journal.status().pending_publications == 0
    assert (root / 'history.bin').read_bytes() == before
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before)


def test_real_process_exit_after_file_publication_recovers_without_overwrite(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    result = child(path, """
original = sidecar.prepare_synthetic_sidecar
def publish_then_exit(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(43)
sidecar.prepare_synthetic_sidecar = publish_then_exit
journal.publish('SYNTH-TICKET-A')
""")
    assert result.returncode == 43, result.stderr
    assert journal.status().pending_publications == 1
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before)
    inode = (root / 'sidecar.bin').stat().st_ino
    assert journal.publish('SYNTH-TICKET-A').status == 'already_present'
    assert (root / 'sidecar.bin').stat().st_ino == inode
    assert (root / 'history.bin').read_bytes() == before


def test_real_process_exit_mid_hardlink_preserves_ambiguous_files_and_refuses(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    result = child(path, """
original = sidecar._publish_new
def link_then_exit(*args):
    original(*args)
    os._exit(44)
sidecar._publish_new = link_then_exit
journal.publish('SYNTH-TICKET-A')
""")
    assert result.returncode == 44, result.stderr
    assert journal.status().pending_publications == 1
    artifacts = [p for p in root.iterdir() if p.name.startswith('.sidecar-')]
    assert len(artifacts) == 1 and (root / 'sidecar.bin').stat().st_nlink == 2
    with pytest.raises(replay.JournalRefusal, match='temporary'):
        journal.publish('SYNTH-TICKET-A')
    assert artifacts[0].read_bytes() == expected_sidecar(before)
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before)
    assert (root / 'history.bin').read_bytes() == before


def test_process_exit_after_temporary_write_refuses_to_ignore_the_orphan(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    result = child(path, """
original = sidecar._write_all
def write_then_exit(*args):
    original(*args)
    os._exit(49)
sidecar._write_all = write_then_exit
journal.publish('SYNTH-TICKET-A')
""")
    assert result.returncode == 49, result.stderr
    artifacts = [entry for entry in root.iterdir() if entry.name.startswith('.sidecar-')]
    assert len(artifacts) == 1 and not (root / 'sidecar.bin').exists()
    with pytest.raises(replay.JournalRefusal, match='temporary'):
        journal.publish('SYNTH-TICKET-A')
    assert journal.status().pending_publications == 1
    assert artifacts[0].read_bytes() == expected_sidecar(before)
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_unclaimed_sidecar_temporary_blocks_fixture_registration(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    temporary = root / '.sidecar-invented.tmp'
    temporary.write_bytes(b'invented unknown data')
    temporary.chmod(0o600)
    with pytest.raises(replay.JournalRefusal, match='temporary'):
        register(journal, root, digest)
    assert temporary.read_bytes() == b'invented unknown data'
    assert (root / 'history.bin').read_bytes() == before and journal.status().attempts == 0


def test_same_original_and_item_cannot_be_relabelled_as_another_request(fixtures):
    database, original = fixtures
    _, _, journal = database()
    first, _, first_digest = original()
    second, _, second_digest = original()
    assert first_digest == second_digest
    register(journal, first, first_digest)
    with pytest.raises(replay.JournalRefusal, match='already assigned'):
        register(journal, second, second_digest, request='SYNTH-REQUEST-B')
    assert not (first / 'sidecar.bin').exists() and not (second / 'sidecar.bin').exists()


def test_separate_fresh_fixture_stores_are_not_a_global_replay_authority(fixtures):
    database, original = fixtures
    _, _, first = database()
    _, _, second = database()
    root_a, before_a, digest_a = original()
    root_b, before_b, digest_b = original()
    for journal, root, digest in ((first, root_a, digest_a), (second, root_b, digest_b)):
        register(journal, root, digest)
        reserve(journal)
        answer(journal)
        assert journal.publish('SYNTH-TICKET-A').status == 'created'
    # Independent databases have no common authority. This is a limitation,
    # not a real-world replay guarantee.
    assert (root_a / 'sidecar.bin').read_bytes() == expected_sidecar(before_a)
    assert (root_b / 'sidecar.bin').read_bytes() == expected_sidecar(before_b)


def test_copied_database_does_not_silently_become_the_same_authority(fixtures):
    database, original = fixtures
    _, source, journal = database()
    _, destination, _ = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    source.backup(destination)
    with pytest.raises(replay.JournalRefusal, match='identity'):
        replay.SyntheticJournal(destination, synthetic_only=True)
    assert journal.status().held_units == 10


@pytest.mark.parametrize('bad', [False, None, 0, 1, 'true'])
def test_synthetic_assertion_is_required_even_for_an_invented_database(fixtures, bad):
    database, _ = fixtures
    _, connection, _ = database()
    with pytest.raises(replay.JournalRefusal, match='synthetic-only'):
        replay.SyntheticJournal(connection, synthetic_only=bad)


def test_anonymous_and_nonfixture_databases_are_not_accepted(tmp_path):
    for path in (':memory:', str(tmp_path / 'invented.sqlite3')):
        connection = connect(path)
        try:
            with pytest.raises(replay.JournalRefusal, match='fixture scope'):
                replay.SyntheticJournal(connection, synthetic_only=True)
        finally:
            connection.close()


@pytest.mark.parametrize('defect', ['foreign_keys', 'synchronous', 'temp_table', 'temp_trigger', 'main_trigger'])
def test_changed_sqlite_settings_or_schema_fence_further_operations(fixtures, defect):
    database, original = fixtures
    _, connection, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    if defect == 'foreign_keys':
        connection.execute('PRAGMA foreign_keys=OFF')
    elif defect == 'synchronous':
        connection.execute('PRAGMA synchronous=OFF')
    elif defect == 'temp_table':
        connection.execute('CREATE TEMP TABLE journal_attempts (ticket_id TEXT)')
    elif defect == 'temp_trigger':
        connection.execute('CREATE TEMP TRIGGER invented AFTER INSERT ON main.journal_attempts '
                           'BEGIN DELETE FROM journal_attempts WHERE ticket_id = NEW.ticket_id; END')
    else:
        connection.execute('CREATE TRIGGER invented AFTER INSERT ON journal_attempts '
                           'BEGIN DELETE FROM journal_attempts WHERE ticket_id = NEW.ticket_id; END')
    with pytest.raises(replay.JournalRefusal):
        reserve(journal)
    assert connection.execute('SELECT COUNT(*) FROM main.journal_attempts').fetchone()[0] == 0
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


@pytest.mark.parametrize('defect', ['database_mode', 'directory_mode', 'hardlink'])
def test_fixture_database_permissions_and_identity_are_checked_each_time(fixtures, defect):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    if defect == 'database_mode':
        path.chmod(0o640)
    elif defect == 'directory_mode':
        path.parent.chmod(0o750)
    else:
        os.link(path, path.parent / 'invented-alias')
    try:
        with pytest.raises(replay.JournalRefusal):
            reserve(journal)
    finally:
        path.chmod(0o600)
        path.parent.chmod(0o700)
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


@pytest.mark.parametrize('bad', [None, True, False, 0, -1, 101, 1.0, '10'])
def test_each_synthetic_reservation_needs_a_positive_integer_toy_bound(fixtures, bad):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    with pytest.raises(ValueError, match='bound'):
        reserve(journal, bound=bad)
    assert journal.status().attempts == 0


@pytest.mark.parametrize('bad', ['SYNTH-TICKET-', 'SYNTH-TICKET-A-B', 'SYNTH-TICKET-' + 'A' * 19,
                                 'not-synthetic', 1, None])
def test_invalid_ticket_identity_never_reserves_a_mock_attempt(fixtures, bad):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    with pytest.raises(ValueError, match='synthetic identity'):
        reserve(journal, ticket=bad)
    assert journal.status().attempts == 0


@pytest.mark.parametrize('reply', [
    (replay.MockReplyKind.ANSWER, None, 1),
    (replay.MockReplyKind.TRANSIENT, SyntheticReading.BETA, 1),
    ('ANSWER', SyntheticReading.BETA, 1),
    (replay.MockReplyKind.ANSWER, SyntheticReading.BETA, True),
    (replay.MockReplyKind.ANSWER, SyntheticReading.BETA, -1),
])
def test_mock_reply_has_no_arbitrary_text_or_untagged_values(reply):
    with pytest.raises(ValueError):
        replay.MockReply(*reply)


def test_nonmock_transport_is_rejected_before_marking_a_reservation_sent(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)

    class NotAMock:
        def send(self):
            raise AssertionError('non-mock transport must not run')

    with pytest.raises(replay.JournalRefusal, match='closed synthetic'):
        journal.dispatch('SYNTH-TICKET-A', NotAMock())
    assert (journal.status().attempts, journal.status().unknown_attempts, journal.status().held_units) == (1, 0, 10)
    assert (root / 'history.bin').read_bytes() == before


def test_mutated_mock_reply_leaves_a_sent_unknown_not_an_automatic_retry(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    reply = replay.MockReply(replay.MockReplyKind.ANSWER, SyntheticReading.BETA, 7)
    transport = replay.MockTransport((reply,))
    object.__setattr__(reply, 'reading', 'not-a-synthetic-reading')
    with pytest.raises(ValueError):
        journal.dispatch('SYNTH-TICKET-A', transport)
    assert transport.consumed == 1 and journal.status().unknown_attempts == 1
    with pytest.raises(replay.JournalRefusal):
        reserve(journal, ticket='SYNTH-TICKET-B')


def test_toy_budget_counts_all_reserved_physical_attempts(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root_a, _, digest_a = original()
    root_b, _, digest_b = original()
    root_c, _, digest_c = original()
    register(journal, root_a, digest_a)
    register(journal, root_b, digest_b, request='SYNTH-REQUEST-B', item='SYNTH-ITEM-C')
    register(journal, root_c, digest_c, request='SYNTH-REQUEST-C', item='SYNTH-ITEM-D')
    reserve(journal, bound=60)
    reserve(journal, request='SYNTH-REQUEST-B', ticket='SYNTH-TICKET-B', bound=40)
    assert journal.status().held_units == 100 and journal.status().attempts == 2
    with pytest.raises(replay.JournalRefusal, match='budget'):
        reserve(journal, request='SYNTH-REQUEST-C', ticket='SYNTH-TICKET-C', bound=1)
    assert answer(journal, charge=7) == 'settled'
    reserve(journal, request='SYNTH-REQUEST-C', ticket='SYNTH-TICKET-C', bound=1)
    assert (journal.status().attempts, journal.status().spent_units, journal.status().held_units) == (3, 7, 41)


def test_mock_attempt_ceiling_counts_zero_charge_attempts(fixtures):
    database, original = fixtures
    _, _, journal = database()
    for index in range(replay.MOCK_ATTEMPT_LIMIT):
        root, _, digest = original()
        request = f'SYNTH-REQUEST-{index}'
        item = f'SYNTH-ITEM-{index}'
        ticket = f'SYNTH-TICKET-{index}'
        register(journal, root, digest, request=request, item=item)
        reserve(journal, request=request, ticket=ticket, bound=1)
        assert answer(journal, ticket, charge=0) == 'settled'
    root, _, digest = original()
    register(journal, root, digest, request='SYNTH-REQUEST-LAST', item='SYNTH-ITEM-LAST')
    with pytest.raises(replay.JournalRefusal, match='ceiling'):
        reserve(journal, request='SYNTH-REQUEST-LAST', ticket='SYNTH-TICKET-LAST', bound=1)
    assert journal.status().attempts == replay.MOCK_ATTEMPT_LIMIT


def test_synthetic_retry_chain_has_a_fixed_limit(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    for ticket in ('SYNTH-TICKET-A', 'SYNTH-TICKET-B', 'SYNTH-TICKET-C'):
        reserve(journal, ticket=ticket)
        assert journal.dispatch(ticket, replay.MockTransport((
            replay.MockReply(replay.MockReplyKind.TRANSIENT, None, 1),
        ))) == 'settled'
    with pytest.raises(replay.JournalRefusal, match='retry'):
        reserve(journal, ticket='SYNTH-TICKET-D')
    assert (journal.status().attempts, journal.status().spent_units) == (3, 3)


@pytest.mark.parametrize('_iteration', range(5))
def test_concurrent_synthetic_reservations_cannot_fork_one_request(fixtures, _iteration):
    database, original = fixtures
    path, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    barrier = threading.Barrier(2)

    def worker(ticket):
        connection = connect(path)
        try:
            local = replay.SyntheticJournal(connection, synthetic_only=True)
            barrier.wait(timeout=10)
            try:
                reserve(local, ticket=ticket)
                return 'reserved'
            except replay.JournalRefusal:
                return 'refused'
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ('SYNTH-TICKET-A', 'SYNTH-TICKET-B')))
    assert sorted(results) == ['refused', 'reserved'] and journal.status().attempts == 1


def test_bill_for_unrecognized_or_unsent_mock_attempt_is_quarantined(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    assert journal.record_bill(ticket_id='SYNTH-TICKET-UNKNOWN', bill_id='SYNTH-BILL-A', charge_units=8) == 'conflict'
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-B', charge_units=4) == 'conflict'
    state = journal.status()
    assert state.conflicts == 2 and state.unmatched_claim_units == 12 and state.held_units == 22
    with pytest.raises(replay.JournalRefusal, match='conflict'):
        answer(journal)
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_early_mock_bill_does_not_prove_nonreturn_or_release_the_hold(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    with pytest.raises(replay.JournalRefusal, match='did not return'):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=6) == 'awaiting_response'
    connection = connect(path)
    try:
        restored = replay.SyntheticJournal(connection, synthetic_only=True)
        assert (restored.status().held_units, restored.status().unknown_attempts) == (10, 1)
        with pytest.raises(replay.JournalRefusal, match='retry'):
            reserve(restored, ticket='SYNTH-TICKET-B')
    finally:
        connection.close()


def test_unreturned_bill_above_bound_keeps_the_larger_claim_and_fences(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    with pytest.raises(replay.JournalRefusal):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=25) == 'conflict'
    assert (journal.status().held_units, journal.status().conflicts) == (25, 1)
    with pytest.raises(replay.JournalRefusal, match='conflict'):
        reserve(journal, ticket='SYNTH-TICKET-B')


def test_bill_identity_reuse_across_mock_attempts_is_quarantined(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root_a, _, digest_a = original()
    root_b, _, digest_b = original()
    register(journal, root_a, digest_a)
    register(journal, root_b, digest_b, request='SYNTH-REQUEST-B', item='SYNTH-ITEM-C')
    reserve(journal)
    answer(journal)
    reserve(journal, request='SYNTH-REQUEST-B', ticket='SYNTH-TICKET-B')
    answer(journal, 'SYNTH-TICKET-B')
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=7) == 'confirmed'
    assert journal.record_bill(ticket_id='SYNTH-TICKET-B', bill_id='SYNTH-BILL-A', charge_units=9) == 'conflict'
    assert journal.status().conflicts == 1 and journal.status().held_units == 2
    with pytest.raises(replay.JournalRefusal, match='conflict'):
        journal.publish('SYNTH-TICKET-A')


def test_original_replaced_with_identical_bytes_is_not_silently_rebound(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    replacement = root / 'invented-replacement'
    replacement.write_bytes(before)
    replacement.chmod(0o600)
    os.replace(replacement, root / 'history.bin')  # Only this test's invented fixture.
    with pytest.raises(replay.JournalRefusal, match='identity changed'):
        journal.publish('SYNTH-TICKET-A')
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_unclaimed_existing_sidecar_is_preserved_and_not_adopted(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    other = root / 'sidecar.bin'
    other.write_bytes(b'invented pre-existing file')
    other.chmod(0o600)
    with pytest.raises(replay.JournalRefusal, match='unclaimed'):
        register(journal, root, digest)
    assert other.read_bytes() == b'invented pre-existing file'
    assert (root / 'history.bin').read_bytes() == before and journal.status().attempts == 0


def test_completed_sidecar_is_not_recreated_if_removed_from_the_fixture(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    journal.publish('SYNTH-TICKET-A')
    (root / 'sidecar.bin').unlink()  # Remove only the test-created synthetic artifact.
    with pytest.raises(FileNotFoundError):
        journal.publish('SYNTH-TICKET-A')
    assert not (root / 'sidecar.bin').exists() and (root / 'history.bin').read_bytes() == before


def test_corrupted_completed_sidecar_is_not_overwritten(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    journal.publish('SYNTH-TICKET-A')
    (root / 'sidecar.bin').write_bytes(b'invented changed content')
    with pytest.raises(replay.JournalRefusal, match='sidecar differs'):
        journal.publish('SYNTH-TICKET-A')
    assert (root / 'sidecar.bin').read_bytes() == b'invented changed content'
    assert (root / 'history.bin').read_bytes() == before


def test_uncoordinated_response_column_change_is_detected(fixtures):
    database, original = fixtures
    _, connection, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    connection.execute("UPDATE main.journal_attempts SET reading = 'GAMMA' WHERE ticket_id = 'SYNTH-TICKET-A'")
    with pytest.raises(replay.JournalRefusal, match='body or digest'):
        journal.publish('SYNTH-TICKET-A')
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_coherent_external_sql_forgery_is_not_authenticated_by_a_hash(fixtures):
    database, original = fixtures
    _, connection, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    forged = b'SYNTH-REPLY-V1|ANSWER|GAMMA\n'
    connection.execute("UPDATE main.journal_attempts SET reading = ?, reply_bytes = ?, reply_sha256 = ? "
                       "WHERE ticket_id = ?", ('GAMMA', forged, sha256(forged).hexdigest(), 'SYNTH-TICKET-A'))
    # This intentionally demonstrates the limit of a caller-writable database:
    # coherent SQL changes are not authenticated and must be independently fenced.
    journal.publish('SYNTH-TICKET-A')
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before, reading=SyntheticReading.GAMMA)


def test_sync_failure_keeps_pending_intent_and_recovery_syncs_existing_sidecar(fixtures, monkeypatch):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)

    def fail_sync(*_):
        raise OSError('invented sidecar sync failure')

    with monkeypatch.context() as scoped:
        scoped.setattr(replay, '_sync_fixture_sidecar', fail_sync)
        with pytest.raises(OSError, match='invented sidecar sync failure'):
            journal.publish('SYNTH-TICKET-A')
    assert journal.status().pending_publications == 1
    assert (root / 'sidecar.bin').read_bytes() == expected_sidecar(before)
    syncs = []
    original_sync = replay._sync_fixture_sidecar

    def observe_sync(root_name, data):
        syncs.append((root_name, sha256(data).hexdigest()))
        return original_sync(root_name, data)

    with monkeypatch.context() as scoped:
        scoped.setattr(replay, '_sync_fixture_sidecar', observe_sync)
        result = journal.publish('SYNTH-TICKET-A')
    assert result.status == 'already_present' and len(syncs) == 1
    assert syncs[0] == (str(root), sha256(expected_sidecar(before)).hexdigest())
    assert journal.status().pending_publications == 0 and (root / 'history.bin').read_bytes() == before


def test_conflicting_sidecar_after_pending_intent_is_preserved(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    result = child(path, """
journal._finish_publication = lambda *_: os._exit(46)
journal.publish('SYNTH-TICKET-A')
""")
    assert result.returncode == 46, result.stderr
    (root / 'sidecar.bin').write_bytes(b'invented conflicting sidecar')
    (root / 'sidecar.bin').chmod(0o600)
    with pytest.raises(sidecar.SidecarRefusal, match='conflicts'):
        journal.publish('SYNTH-TICKET-A')
    assert journal.status().pending_publications == 1
    assert (root / 'sidecar.bin').read_bytes() == b'invented conflicting sidecar'
    assert (root / 'history.bin').read_bytes() == before


def test_process_exit_after_acknowledgement_does_not_republish(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    result = child(path, """
original = journal._finish_publication
def acknowledge_then_exit(ticket):
    original(ticket)
    os._exit(47)
journal._finish_publication = acknowledge_then_exit
journal.publish('SYNTH-TICKET-A')
""")
    assert result.returncode == 47, result.stderr
    assert journal.status().pending_publications == 0
    inode = (root / 'sidecar.bin').stat().st_ino
    assert journal.publish('SYNTH-TICKET-A').status == 'verified_existing'
    assert (root / 'sidecar.bin').stat().st_ino == inode
    assert (root / 'history.bin').read_bytes() == before


def test_process_exit_after_reservation_before_send_keeps_one_unsent_hold(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    result = child(path, """
journal.reserve(request_id='SYNTH-REQUEST-A', ticket_id='SYNTH-TICKET-A', bound_units=10)
os._exit(48)
""")
    assert result.returncode == 48, result.stderr
    assert (journal.status().attempts, journal.status().held_units, journal.status().unknown_attempts) == (1, 10, 0)
    assert answer(journal) == 'settled'
    with pytest.raises(replay.JournalRefusal, match='unsent'):
        answer(journal)
    assert journal.status().attempts == 1


def test_separate_processes_cannot_both_dispatch_the_same_fixture_ticket(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    program = """
import sqlite3
import sys
from analysis.coling.followup import oss_replay_synthetic as replay
from analysis.coling.followup.oss_safeguards import SyntheticReading
connection = sqlite3.connect(sys.argv[1], isolation_level=None, timeout=10)
connection.execute('PRAGMA foreign_keys=ON')
journal = replay.SyntheticJournal(connection, synthetic_only=True)
transport = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER, SyntheticReading.BETA, 7),))
sys.stdin.buffer.read(1)
try:
    state = journal.dispatch('SYNTH-TICKET-A', transport)
except replay.JournalRefusal:
    state = 'refused'
print(state, transport.consumed)
connection.close()
"""
    environment = {'HOME': '/tmp/opencode', 'TMPDIR': '/tmp/opencode', 'PATH': '/usr/bin:/bin',
                   'PYTHONPATH': '.', 'PYTHONDONTWRITEBYTECODE': '1'}
    worktree = Path(__file__).resolve().parents[3]
    processes = [subprocess.Popen([sys.executable, '-c', program, str(path)], cwd=worktree, env=environment,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
    try:
        for process in processes:
            process.stdin.write('x')
            process.stdin.flush()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, stderr
            results.append(stdout.strip())
        assert sorted(results) == ['refused 0', 'settled 1']
        assert (journal.status().attempts, journal.status().spent_units, journal.status().held_units) == (1, 7, 0)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.parametrize(('early_charge', 'reply_charge', 'expected_state', 'expected_conflicts'), [
    (7, 7, 'settled', 0),
    (9, 7, 'settled', 1),
    (7, None, 'reply_unknown', 0),
    (11, 7, 'settled', 2),
])
def test_early_mock_bill_and_later_reply_are_both_preserved(
    fixtures, monkeypatch, early_charge, reply_charge, expected_state, expected_conflicts
):
    database, original = fixtures
    path, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    entered = threading.Event()
    release = threading.Event()
    original_take = replay.MockTransport._take

    def delayed_take(transport):
        entered.set()
        if not release.wait(timeout=10):
            raise AssertionError('invented test barrier timed out')
        return original_take(transport)

    monkeypatch.setattr(replay.MockTransport, '_take', delayed_take)

    def worker():
        connection = connect(path)
        try:
            local = replay.SyntheticJournal(connection, synthetic_only=True)
            transport = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER,
                                                               SyntheticReading.BETA, reply_charge),))
            return local.dispatch('SYNTH-TICKET-A', transport)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        try:
            assert entered.wait(timeout=10)
            bill_state = journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A',
                                             charge_units=early_charge)
            assert bill_state == ('conflict' if early_charge > 10 else 'awaiting_response')
        finally:
            release.set()
        assert future.result(timeout=10) == expected_state
    state = journal.status()
    assert state.conflicts == expected_conflicts
    if expected_state == 'reply_unknown':
        assert state.held_units == 10
        assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A',
                                   charge_units=early_charge) == 'settled'
        assert journal.publish('SYNTH-TICKET-A').status == 'created'
    elif expected_conflicts:
        assert state.held_units == max(0, early_charge - reply_charge)
        with pytest.raises(replay.JournalRefusal, match='conflict'):
            journal.publish('SYNTH-TICKET-A')
    else:
        assert journal.publish('SYNTH-TICKET-A').status == 'created'
    assert (root / 'history.bin').read_bytes() == before


def test_unknown_charge_above_bound_remains_held_and_permanently_fenced(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    assert answer(journal, charge=None) == 'reply_unknown'
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=20) == 'conflict'
    assert (journal.status().held_units, journal.status().conflicts) == (20, 1)
    with pytest.raises(replay.JournalRefusal, match='conflict'):
        journal.publish('SYNTH-TICKET-A')
    assert (root / 'history.bin').read_bytes() == before and not (root / 'sidecar.bin').exists()


def test_contradictory_bills_while_sent_preserve_both_claims_and_do_not_unlock(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    with pytest.raises(replay.JournalRefusal):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-A', charge_units=3) == 'awaiting_response'
    assert journal.record_bill(ticket_id='SYNTH-TICKET-A', bill_id='SYNTH-BILL-B', charge_units=8) == 'conflict'
    assert (journal.status().held_units, journal.status().unknown_attempts, journal.status().conflicts) == (10, 1, 1)
    with pytest.raises(replay.JournalRefusal, match='conflict'):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))


def test_real_study_or_unmarked_paths_are_refused_without_opening_them(fixtures):
    database, _ = fixtures
    _, _, journal = database()
    with pytest.raises(sidecar.SidecarRefusal, match='fixture scope'):
        journal.register(request_id='SYNTH-REQUEST-A', item_id='SYNTH-ITEM-B',
                         root='/data/noctis/GitHub-Data/COLLIE-coling', original_sha256='0' * 64)
    assert journal.status().attempts == 0


def test_other_outstanding_fixture_ticket_blocks_answer_publication(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root_a, before_a, digest_a = original()
    root_b, before_b, digest_b = original()
    register(journal, root_a, digest_a)
    register(journal, root_b, digest_b, request='SYNTH-REQUEST-B', item='SYNTH-ITEM-C')
    reserve(journal)
    reserve(journal, request='SYNTH-REQUEST-B', ticket='SYNTH-TICKET-B')
    answer(journal)
    with pytest.raises(replay.JournalRefusal, match='outstanding'):
        journal.publish('SYNTH-TICKET-A')
    assert not (root_a / 'sidecar.bin').exists()
    answer(journal, 'SYNTH-TICKET-B')
    assert journal.publish('SYNTH-TICKET-A').status == 'created'
    assert (root_a / 'history.bin').read_bytes() == before_a
    assert (root_b / 'history.bin').read_bytes() == before_b


def test_unresolved_sent_attempt_blocks_another_reserved_dispatch(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root_a, _, digest_a = original()
    root_b, _, digest_b = original()
    register(journal, root_a, digest_a)
    register(journal, root_b, digest_b, request='SYNTH-REQUEST-B', item='SYNTH-ITEM-C')
    reserve(journal)
    reserve(journal, request='SYNTH-REQUEST-B', ticket='SYNTH-TICKET-B')
    with pytest.raises(replay.JournalRefusal, match='did not return'):
        journal.dispatch('SYNTH-TICKET-A', replay.MockTransport(()))
    unused = replay.MockTransport((replay.MockReply(replay.MockReplyKind.ANSWER, SyntheticReading.BETA, 1),))
    with pytest.raises(replay.JournalRefusal, match='unresolved'):
        journal.dispatch('SYNTH-TICKET-B', unused)
    assert unused.consumed == 0 and (journal.status().attempts, journal.status().held_units) == (2, 20)


def test_attached_database_is_refused_without_consuming_a_mock_ticket(fixtures):
    database, original = fixtures
    _, connection, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    connection.execute("ATTACH DATABASE ':memory:' AS invented_other")
    with pytest.raises(replay.JournalRefusal, match='attached'):
        reserve(journal)
    assert connection.execute('SELECT COUNT(*) FROM main.journal_attempts').fetchone()[0] == 0
    assert (root / 'history.bin').read_bytes() == before


def test_symlinked_synthetic_history_is_not_followed(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, _, digest = original()
    other, other_bytes, other_digest = original()
    assert digest == other_digest
    (root / 'history.bin').unlink()  # The test replaces only its own invented file.
    (root / 'history.bin').symlink_to(other / 'history.bin')
    with pytest.raises(OSError):
        register(journal, root, digest)
    assert (other / 'history.bin').read_bytes() == other_bytes and journal.status().attempts == 0


def test_replaced_fixture_directory_is_not_silently_rebound(fixtures):
    database, original = fixtures
    _, _, journal = database()
    root, before, digest = original()
    register(journal, root, digest)
    reserve(journal)
    answer(journal)
    backup = root.with_name('invented-saved-' + secrets.token_hex(8))
    assert not os.path.lexists(backup)
    root.rename(backup)
    try:
        root.mkdir(mode=0o700)
        (root / 'history.bin').write_bytes(before)
        (root / 'history.bin').chmod(0o600)
        with pytest.raises(replay.JournalRefusal, match='identity changed'):
            journal.publish('SYNTH-TICKET-A')
        assert not (root / 'sidecar.bin').exists()
        assert (backup / 'history.bin').read_bytes() == before
    finally:
        (root / 'history.bin').unlink()
        root.rmdir()
        backup.rename(root)


def test_replaced_database_name_does_not_redirect_an_existing_journal(fixtures):
    database, original = fixtures
    path, _, journal = database()
    root, _, digest = original()
    register(journal, root, digest)
    reserve(journal)
    saved = path.parent / 'invented-original-database'
    path.rename(saved)  # Only this test's synthetic database is moved.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    with pytest.raises(replay.JournalRefusal, match='changed'):
        journal.status()
    assert saved.is_file() and path.is_file() and not (root / 'sidecar.bin').exists()
