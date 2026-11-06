"""Invented-only filesystem fixtures for the synthetic checkpoint sidecar."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
import secrets

import pytest

from analysis.coling.followup import oss_sidecar_synthetic as candidate
from analysis.coling.followup import oss_safeguards as safety
from analysis.coling.followup import test_oss_safeguards as safety_fixtures
from analysis.coling.followup.oss_safeguards import (
    DecodingKind,
    OutputConflict,
    SyntheticDecoding,
    SyntheticHistory,
    SyntheticOutput,
    SyntheticReading,
    append_synthetic,
)


@pytest.fixture
def fixture_root():
    root = Path('/tmp/opencode') / ('oss-sidecar-fixture-' + secrets.token_hex(4))
    root.mkdir(mode=0o700)
    try:
        yield root
    finally:
        if root.is_symlink():
            root.unlink()
        elif root.is_dir():
            for child in root.iterdir():
                if child.is_dir() and not child.is_symlink():
                    child.rmdir()
                else:
                    child.unlink()
            root.rmdir()


def original_decoding():
    return SyntheticDecoding(DecodingKind.ORIGINAL_DEFAULT)


def record(item='A', source='A', reading=SyntheticReading.ALPHA, decoding=None):
    return SyntheticOutput('SYNTH-ITEM-' + item, decoding or original_decoding(),
                           'SYNTH-SOURCE-' + source, reading)


def make_original(root, records=(record(),)):
    decoding = original_decoding()
    empty = SyntheticHistory.empty(decoding)
    raw = append_synthetic(empty, records).combined_bytes
    path = root / 'history.bin'
    path.write_bytes(raw)
    path.chmod(0o600)
    return raw, sha256(raw).hexdigest(), decoding


def prepare(root, digest, decoding, additions, synthetic_only=True):
    return candidate.prepare_synthetic_sidecar(str(root), expected_original_sha256=digest,
                                               decoding=decoding, additions=additions,
                                               synthetic_only=synthetic_only)


def guarded_output(ticket, *, item='B', decoding=None):
    suffix = ticket.ticket_id.removeprefix('SYNTH-TICKET-')
    return SyntheticOutput('SYNTH-ITEM-' + item, decoding or original_decoding(),
                           'SYNTH-SOURCE-TICKET' + suffix, SyntheticReading.BETA)


def guarded(root, digest, simulation, operation, ticket, output=None):
    return candidate.prepare_guarded_synthetic_sidecar(
        str(root), expected_original_sha256=digest, simulation=simulation,
        operation_id=operation.operation_id, ticket_id=ticket.ticket_id,
        output=output or guarded_output(ticket), synthetic_only=True,
    )


def successful_mock():
    simulation = safety_fixtures.simulation()
    operation = simulation.begin('SYNTH-RUN-A')
    ticket = simulation.reserve_next(operation.operation_id)
    transport = safety.SyntheticTransport((safety.SyntheticReply(safety.ReplyKind.ANSWER, 7, 1, 1),))
    complete = simulation.dispatch(ticket.ticket_id, transport)
    assert complete.state is safety.OperationState.COMPLETE and transport.consumed == 1
    return simulation, complete, ticket


def test_sidecar_is_new_and_original_bytes_are_unchanged(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    addition = record('B', 'B', SyntheticReading.BETA)
    receipt = prepare(fixture_root, digest, decoding, (addition,))
    after = (fixture_root / 'history.bin').read_bytes()
    sidecar = (fixture_root / 'sidecar.bin').read_bytes()
    expected = append_synthetic(SyntheticHistory(before, decoding), (addition,))
    assert receipt.status == 'created' and receipt.added_count == 1 and receipt.duplicate_count == 0
    assert before == after and sidecar == expected.combined_bytes and sidecar.startswith(before)
    assert receipt.original_sha256 == digest and receipt.sidecar_sha256 == sha256(sidecar).hexdigest()
    assert (fixture_root / 'sidecar.bin').stat().st_mode & 0o777 == 0o600
    assert sorted(item.name for item in fixture_root.iterdir()) == ['history.bin', 'sidecar.bin']


def test_guarded_synthetic_publication_requires_settled_answer_and_keeps_original(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    receipt = guarded(fixture_root, digest, simulation, operation, ticket)
    assert receipt.status == 'created' and receipt.added_count == 1
    assert (fixture_root / 'history.bin').read_bytes() == before
    expected = append_synthetic(SyntheticHistory(before, decoding), (guarded_output(ticket),)).combined_bytes
    assert (fixture_root / 'sidecar.bin').read_bytes() == expected
    assert simulation.snapshot().physical_attempts == 1


@pytest.mark.parametrize('kind', [safety.ReplyKind.ANSWER, safety.ReplyKind.TRANSIENT])
def test_unknown_charge_blocks_guarded_synthetic_publication(fixture_root, kind):
    before, digest, _ = make_original(fixture_root)
    simulation = safety_fixtures.simulation()
    operation = simulation.begin('SYNTH-RUN-A')
    ticket = simulation.reserve_next(operation.operation_id)
    result = simulation.dispatch(ticket.ticket_id, safety.SyntheticTransport((safety.SyntheticReply(kind, None),)))
    assert result.state is safety.OperationState.WAITING_FOR_BILL
    with pytest.raises(safety.SafetyRefusal, match='unknown'):
        guarded(fixture_root, digest, simulation, operation, ticket)
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_final_synthetic_receipt_can_clear_unknown_charge_before_publication(fixture_root):
    before, digest, _ = make_original(fixture_root)
    simulation = safety_fixtures.simulation()
    operation = simulation.begin('SYNTH-RUN-A')
    ticket = simulation.reserve_next(operation.operation_id)
    simulation.dispatch(ticket.ticket_id, safety.SyntheticTransport((safety.SyntheticReply(safety.ReplyKind.ANSWER, None),)))
    with pytest.raises(safety.SafetyRefusal, match='unknown'):
        guarded(fixture_root, digest, simulation, operation, ticket)
    simulation.reconcile_attempt(safety_fixtures.receipt(ticket.ticket_id, 'A', 7, input_tokens=1, completion_tokens=1))
    receipt = guarded(fixture_root, digest, simulation, operation, ticket)
    assert receipt.status == 'created' and (fixture_root / 'history.bin').read_bytes() == before


@pytest.mark.parametrize('first_kind', [safety.ReplyKind.TRANSIENT, safety.ReplyKind.EMPTY_ECHO])
def test_each_synthetic_retry_is_reserved_and_last_answer_can_publish(fixture_root, first_kind):
    before, digest, _ = make_original(fixture_root)
    simulation = safety_fixtures.simulation()
    operation = simulation.begin('SYNTH-RUN-A')
    first = simulation.reserve_next(operation.operation_id)
    replies = safety.SyntheticTransport((safety.SyntheticReply(first_kind, 2, 1, 1),
                                         safety.SyntheticReply(safety.ReplyKind.ANSWER, 7, 1, 1)))
    assert simulation.dispatch(first.ticket_id, replies).state is safety.OperationState.READY
    second = simulation.reserve_next(operation.operation_id)
    assert simulation.dispatch(second.ticket_id, replies).state is safety.OperationState.COMPLETE
    receipt = guarded(fixture_root, digest, simulation, operation, second)
    assert receipt.status == 'created' and simulation.snapshot().physical_attempts == 2
    assert (fixture_root / 'history.bin').read_bytes() == before


def test_late_conflicting_bill_blocks_republication_without_deleting_sidecar(fixture_root):
    before, digest, _ = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    guarded(fixture_root, digest, simulation, operation, ticket)
    sidecar_before = (fixture_root / 'sidecar.bin').read_bytes()
    with pytest.raises(safety.SafetyRefusal, match='contradictory'):
        simulation.reconcile_attempt(safety_fixtures.receipt(ticket.ticket_id, 'A', 8, input_tokens=1, completion_tokens=1))
    with pytest.raises(safety.SafetyRefusal, match='faulted'):
        guarded(fixture_root, digest, simulation, operation, ticket)
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert (fixture_root / 'sidecar.bin').read_bytes() == sidecar_before


def test_unfinished_retry_and_exceeded_bound_block_guarded_publication(fixture_root):
    before, digest, _ = make_original(fixture_root)
    simulation = safety_fixtures.simulation()
    operation = simulation.begin('SYNTH-RUN-A')
    ticket = simulation.reserve_next(operation.operation_id)
    ready = simulation.dispatch(ticket.ticket_id, safety.SyntheticTransport((safety.SyntheticReply(safety.ReplyKind.TRANSIENT, 2),)))
    assert ready.state is safety.OperationState.READY
    with pytest.raises(candidate.SidecarRefusal, match='settled synthetic answer'):
        guarded(fixture_root, digest, simulation, operation, ticket)
    bad = safety_fixtures.simulation()
    other = bad.begin('SYNTH-RUN-A')
    bad_ticket = bad.reserve_next(other.operation_id)
    bad.dispatch(bad_ticket.ticket_id, safety.SyntheticTransport((safety.SyntheticReply(safety.ReplyKind.ANSWER, 11),)))
    with pytest.raises(safety.SafetyRefusal, match='faulted'):
        guarded(fixture_root, digest, bad, other, bad_ticket)
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_other_outstanding_ticket_blocks_guarded_publication(fixture_root):
    before, digest, _ = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    other = simulation.begin('SYNTH-RUN-A')
    simulation.reserve_next(other.operation_id)
    with pytest.raises((candidate.SidecarRefusal, safety.SafetyRefusal)):
        guarded(fixture_root, digest, simulation, operation, ticket)
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


@pytest.mark.parametrize('defect', ['wrong_operation', 'wrong_source', 'wrong_decoding', 'invalid_lock'])
def test_guarded_synthetic_publication_refuses_mismatched_evidence(fixture_root, defect):
    before, digest, _ = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    output = guarded_output(ticket)
    if defect == 'wrong_operation':
        operation = simulation.begin('SYNTH-RUN-A')
    elif defect == 'wrong_source':
        output = record('B', 'UNRELATED', SyntheticReading.BETA)
    elif defect == 'wrong_decoding':
        output = guarded_output(ticket, decoding=SyntheticDecoding(DecodingKind.CAPPED_FOLLOWUP, 128))
    else:
        simulation._lock = object()
    with pytest.raises((candidate.SidecarRefusal, safety.SafetyRefusal)):
        guarded(fixture_root, digest, simulation, operation, ticket, output)
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


@pytest.mark.parametrize('defect', ['negative_charge', 'changed_bound', 'changed_ticket_id',
                                    'boolean_operation_id', 'boolean_attempt_count'])
def test_guarded_publication_revalidates_mutated_mock_evidence(fixture_root, defect):
    before, digest, _ = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    stored_ticket = simulation.ticket(ticket.ticket_id)
    stored_operation = simulation.operation(operation.operation_id)
    if defect == 'negative_charge':
        object.__setattr__(stored_ticket, 'charge_nanos', -1)
    elif defect == 'changed_bound':
        object.__setattr__(stored_ticket, 'bound_nanos', 999)
    elif defect == 'changed_ticket_id':
        object.__setattr__(stored_ticket, 'ticket_id', 'SYNTH-TICKET-999')
    elif defect == 'boolean_operation_id':
        object.__setattr__(stored_operation, 'operation_id', True)
    else:
        object.__setattr__(stored_operation, 'physical_attempts', True)
    with pytest.raises((candidate.SidecarRefusal, safety.SafetyRefusal, ValueError)):
        candidate.prepare_guarded_synthetic_sidecar(
            str(fixture_root), expected_original_sha256=digest, simulation=simulation,
            operation_id=1, ticket_id='SYNTH-TICKET-1', output=guarded_output(ticket), synthetic_only=True,
        )
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_guarded_publication_ignores_shadowed_public_accessors(fixture_root, monkeypatch):
    before, digest, _ = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    monkeypatch.setattr(simulation, 'operation', lambda *_: (_ for _ in ()).throw(AssertionError('shadow used')))
    monkeypatch.setattr(simulation, 'ticket', lambda *_: (_ for _ in ()).throw(AssertionError('shadow used')))
    monkeypatch.setattr(simulation, 'snapshot', lambda: (_ for _ in ()).throw(AssertionError('shadow used')))
    receipt = guarded(fixture_root, digest, simulation, operation, ticket)
    assert receipt.status == 'created' and (fixture_root / 'history.bin').read_bytes() == before


def test_guarded_publication_refuses_shadowed_private_ledger_methods(fixture_root, monkeypatch):
    before, digest, _ = make_original(fixture_root)
    simulation, operation, ticket = successful_mock()
    stale = simulation.snapshot()
    other = simulation.begin('SYNTH-RUN-A')
    simulation.reserve_next(other.operation_id)
    monkeypatch.setattr(simulation, '_snapshot_locked', lambda: stale)
    with pytest.raises(candidate.SidecarRefusal, match='shadow'):
        guarded(fixture_root, digest, simulation, operation, ticket)
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_identical_repeat_is_idempotent_without_overwriting_either_file(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    additions = (record('B', 'B', SyntheticReading.BETA),)
    first = prepare(fixture_root, digest, decoding, additions)
    sidecar = (fixture_root / 'sidecar.bin').read_bytes()
    inode = (fixture_root / 'sidecar.bin').stat().st_ino
    second = prepare(fixture_root, digest, decoding, additions)
    assert first.status == 'created' and second.status == 'already_present'
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert (fixture_root / 'sidecar.bin').read_bytes() == sidecar
    assert (fixture_root / 'sidecar.bin').stat().st_ino == inode


def test_existing_sidecar_changed_during_comparison_is_not_reported_as_success(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    additions = (record('B', 'B', SyntheticReading.BETA),)
    prepare(fixture_root, digest, decoding, additions)
    original_read = candidate._read_regular
    original_reads = 0

    def mutate_during_second_original_read(root_fd, name):
        nonlocal original_reads
        result = original_read(root_fd, name)
        if name == 'history.bin':
            original_reads += 1
            if original_reads == 2:
                (fixture_root / 'sidecar.bin').write_bytes(b'invented changed sidecar')
        return result

    monkeypatch.setattr(candidate, '_read_regular', mutate_during_second_original_read)
    with pytest.raises(candidate.SidecarRefusal, match='sidecar changed'):
        prepare(fixture_root, digest, decoding, additions)
    assert (fixture_root / 'history.bin').read_bytes() == before


def test_conflicting_existing_sidecar_is_never_overwritten(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    sidecar = fixture_root / 'sidecar.bin'
    sidecar.write_bytes(b'invented existing sidecar\n')
    sidecar.chmod(0o600)
    with pytest.raises(candidate.SidecarRefusal, match='conflicts'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert sidecar.read_bytes() == b'invented existing sidecar\n'
    assert (fixture_root / 'history.bin').read_bytes() == before


def test_wrong_expected_original_hash_prevents_any_publication(fixture_root):
    before, _, decoding = make_original(fixture_root)
    with pytest.raises(candidate.SidecarRefusal, match='hash differs'):
        prepare(fixture_root, '0' * 64, decoding, (record('B', 'B'),))
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert sorted(item.name for item in fixture_root.iterdir()) == ['history.bin']


def test_identical_duplicate_is_skipped_but_conflicting_duplicate_is_refused(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    receipt = prepare(fixture_root, digest, decoding, (record(), record('B', 'B')))
    assert receipt.added_count == receipt.duplicate_count == 1
    assert (fixture_root / 'history.bin').read_bytes() == before
    (fixture_root / 'sidecar.bin').unlink()
    with pytest.raises(OutputConflict, match='conflicting'):
        prepare(fixture_root, digest, decoding, (record(reading=SyntheticReading.GAMMA),))
    assert not (fixture_root / 'sidecar.bin').exists() and (fixture_root / 'history.bin').read_bytes() == before


def test_new_decoding_cannot_fill_original_default_history(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    capped = SyntheticDecoding(DecodingKind.CAPPED_FOLLOWUP, 128)
    with pytest.raises(OutputConflict, match='distinct decoding'):
        prepare(fixture_root, digest, decoding, (record('B', 'B', decoding=capped),))
    assert not (fixture_root / 'sidecar.bin').exists() and (fixture_root / 'history.bin').read_bytes() == before


@pytest.mark.parametrize('bad', [False, None, 1, 'yes'])
def test_explicit_synthetic_assertion_is_required(fixture_root, bad):
    before, digest, decoding = make_original(fixture_root)
    with pytest.raises(candidate.SidecarRefusal, match='synthetic-only'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),), synthetic_only=bad)
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


@pytest.mark.parametrize('bad', ['/data/noctis/GitHub-Data/COLLIE-coling', '/tmp/opencode/../other',
                                 '/tmp/opencode/oss-sidecar-fixture-TOO_LONG', None])
def test_other_roots_are_refused_without_access(bad):
    with pytest.raises(candidate.SidecarRefusal, match='fixture scope'):
        candidate.prepare_synthetic_sidecar(bad, expected_original_sha256='0' * 64,
                                            decoding=original_decoding(), additions=(), synthetic_only=True)


def test_root_permissions_must_remain_private(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    fixture_root.chmod(0o755)
    try:
        with pytest.raises(candidate.SidecarRefusal, match='owner-only'):
            prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    finally:
        fixture_root.chmod(0o700)
    assert (fixture_root / 'history.bin').read_bytes() == before


def test_original_file_must_be_private_and_single_linked(fixture_root, tmp_path):
    before, digest, decoding = make_original(fixture_root)
    path = fixture_root / 'history.bin'
    path.chmod(0o644)
    with pytest.raises(candidate.SidecarRefusal, match='unsafe type'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    path.chmod(0o600)
    alias = tmp_path / 'invented-hardlink'
    os.link(path, alias)
    with pytest.raises(candidate.SidecarRefusal, match='links'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    alias.unlink()
    assert path.read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_symlinked_original_or_sidecar_is_not_followed(fixture_root, tmp_path):
    before, digest, decoding = make_original(fixture_root)
    original = fixture_root / 'history.bin'
    outside = tmp_path / 'invented-outside.bin'
    outside.write_bytes(before)
    outside.chmod(0o600)
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(OSError):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    original.unlink()
    original.write_bytes(before)
    original.chmod(0o600)
    sidecar = fixture_root / 'sidecar.bin'
    sidecar.symlink_to(outside)
    with pytest.raises(OSError):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert outside.read_bytes() == before and original.read_bytes() == before


def test_symlinked_root_is_not_followed(fixture_root, tmp_path):
    fixture_root.rmdir()
    fixture_root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        prepare(fixture_root, '0' * 64, original_decoding(), ())


def test_interrupted_hardlink_publication_is_not_silently_repaired(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    additions = (record('B', 'B'),)
    combined = append_synthetic(SyntheticHistory(before, decoding), additions).combined_bytes
    sidecar = fixture_root / 'sidecar.bin'
    sidecar.write_bytes(combined)
    sidecar.chmod(0o600)
    leftover = fixture_root / '.sidecar-invented.tmp'
    os.link(sidecar, leftover)
    with pytest.raises(candidate.SidecarRefusal, match='links'):
        prepare(fixture_root, digest, decoding, additions)
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert sidecar.read_bytes() == combined and leftover.read_bytes() == combined


def test_oversized_original_is_refused_without_sidecar(fixture_root):
    path = fixture_root / 'history.bin'
    raw = b'x' * (candidate.MAX_SYNTHETIC_HISTORY_BYTES + 1)
    path.write_bytes(raw)
    path.chmod(0o600)
    with pytest.raises(candidate.SidecarRefusal, match='size'):
        prepare(fixture_root, sha256(raw).hexdigest(), original_decoding(), ())
    assert path.read_bytes() == raw and not (fixture_root / 'sidecar.bin').exists()


def test_unmarked_nonfixture_bytes_are_refused_without_publication(fixture_root):
    path = fixture_root / 'history.bin'
    raw = b'invented but not a valid synthetic history\n'
    path.write_bytes(raw)
    path.chmod(0o600)
    with pytest.raises(OutputConflict, match='synthetic history'):
        prepare(fixture_root, sha256(raw).hexdigest(), original_decoding(), ())
    assert path.read_bytes() == raw and not (fixture_root / 'sidecar.bin').exists()


def test_mutated_synthetic_record_is_revalidated_before_any_write(fixture_root):
    before, digest, decoding = make_original(fixture_root)
    altered = record('B', 'B')
    object.__setattr__(altered, 'item_id', 'not-synthetic')
    with pytest.raises(ValueError, match='synthetic'):
        prepare(fixture_root, digest, decoding, (altered,))
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_publication_failure_preserves_original_and_removes_own_temporary(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)

    def fail(*args):
        raise OSError('invented publication failure')

    monkeypatch.setattr(candidate, '_publish_new', fail)
    with pytest.raises(OSError, match='invented publication failure'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert sorted(item.name for item in fixture_root.iterdir()) == ['history.bin']


def test_preexisting_temporary_name_is_never_overwritten_or_deleted(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    name = '.sidecar-' + ('0' * 32) + '.tmp'
    existing = fixture_root / name
    existing.write_bytes(b'invented preexisting temporary')
    existing.chmod(0o600)
    monkeypatch.setattr(candidate.secrets, 'token_hex', lambda _: '0' * 32)
    with pytest.raises(FileExistsError):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert existing.read_bytes() == b'invented preexisting temporary'
    assert (fixture_root / 'history.bin').read_bytes() == before and not (fixture_root / 'sidecar.bin').exists()


def test_replaced_temporary_is_not_deleted_or_reported_as_valid(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    original_publish = candidate._publish_new

    def replace_with_link(root_fd, temporary):
        os.unlink(temporary, dir_fd=root_fd)
        os.symlink('history.bin', temporary, dir_fd=root_fd)
        original_publish(root_fd, temporary)

    monkeypatch.setattr(candidate, '_publish_new', replace_with_link)
    with pytest.raises(candidate.SidecarRefusal, match='temporary'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert (fixture_root / 'sidecar.bin').is_symlink()
    assert any(item.name.startswith('.sidecar-') and item.is_symlink() for item in fixture_root.iterdir())


def test_mutated_temporary_cannot_be_reported_as_a_valid_sidecar(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    original_publish = candidate._publish_new

    def mutate_then_publish(root_fd, temporary):
        fd = os.open(temporary, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            os.write(fd, b'invented tamper')
        finally:
            os.close(fd)
        original_publish(root_fd, temporary)

    monkeypatch.setattr(candidate, '_publish_new', mutate_then_publish)
    with pytest.raises(candidate.SidecarRefusal, match='temporary'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert (fixture_root / 'sidecar.bin').read_bytes() == b'invented tamper'


def test_original_changed_during_publication_is_not_reported_as_success(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    original_publish = candidate._publish_new

    def mutate_then_publish(root_fd, temporary):
        path = fixture_root / 'history.bin'
        path.write_bytes(before + b'SYNTH-ITEM-Z|SYNTH-SOURCE-Z|BETA\n')
        path.chmod(0o600)
        original_publish(root_fd, temporary)

    monkeypatch.setattr(candidate, '_publish_new', mutate_then_publish)
    with pytest.raises(candidate.SidecarRefusal, match='original changed after publication'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert (fixture_root / 'sidecar.bin').is_file()
    assert (fixture_root / 'history.bin').read_bytes() != before  # The test, not the candidate, changed it.


def test_directory_sync_failure_after_publication_is_indeterminate_but_recoverable(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    additions = (record('B', 'B'),)
    with monkeypatch.context() as scoped:
        scoped.setattr(candidate, '_sync_directory', lambda *args: (_ for _ in ()).throw(OSError('invented sync failure')))
        with pytest.raises(OSError, match='invented sync failure'):
            prepare(fixture_root, digest, decoding, additions)
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert (fixture_root / 'sidecar.bin').is_file()
    receipt = prepare(fixture_root, digest, decoding, additions)
    assert receipt.status == 'already_present' and (fixture_root / 'history.bin').read_bytes() == before


def test_sidecar_changed_before_receipt_is_not_reported_as_success(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    original_sync = candidate._sync_directory
    syncs = 0

    def mutate_then_sync(root_fd):
        nonlocal syncs
        syncs += 1
        if syncs == 1:
            (fixture_root / 'sidecar.bin').write_bytes(b'invented changed sidecar')
        original_sync(root_fd)

    monkeypatch.setattr(candidate, '_sync_directory', mutate_then_sync)
    with pytest.raises(candidate.SidecarRefusal, match='sidecar changed before receipt'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert (fixture_root / 'history.bin').read_bytes() == before


def test_changed_original_before_publication_stops_without_sidecar(fixture_root, monkeypatch):
    before, digest, decoding = make_original(fixture_root)
    original_read = candidate._read_regular
    calls = 0

    def mutate_before_second_original_read(root_fd, name):
        nonlocal calls
        if name == 'history.bin':
            calls += 1
            if calls == 2:
                path = fixture_root / 'history.bin'
                path.write_bytes(before + b'SYNTH-ITEM-Z|SYNTH-SOURCE-Z|BETA\n')
                path.chmod(0o600)
        return original_read(root_fd, name)

    monkeypatch.setattr(candidate, '_read_regular', mutate_before_second_original_read)
    with pytest.raises(candidate.SidecarRefusal, match='original changed'):
        prepare(fixture_root, digest, decoding, (record('B', 'B'),))
    assert not (fixture_root / 'sidecar.bin').exists()
    assert sorted(item.name for item in fixture_root.iterdir()) == ['history.bin']


@pytest.mark.parametrize('_iteration', range(10))
def test_parallel_publications_never_overwrite_original_or_conflicting_sidecar(fixture_root, _iteration):
    before, digest, decoding = make_original(fixture_root)
    additions = (record('B', 'B'),)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(prepare, fixture_root, digest, decoding, additions) for _ in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result().status)
            except (candidate.SidecarRefusal, OSError):
                outcomes.append('safe_refusal')
    assert 'created' in outcomes and set(outcomes) <= {'created', 'already_present', 'safe_refusal'}
    expected = append_synthetic(SyntheticHistory(before, decoding), additions).combined_bytes
    assert (fixture_root / 'history.bin').read_bytes() == before
    assert (fixture_root / 'sidecar.bin').read_bytes() == expected


@pytest.mark.parametrize('_iteration', range(10))
def test_parallel_conflicting_publications_keep_only_one_complete_sidecar(fixture_root, _iteration):
    before, digest, decoding = make_original(fixture_root)
    variants = ((record('B', 'B', SyntheticReading.BETA),), (record('C', 'C', SyntheticReading.GAMMA),))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(prepare, fixture_root, digest, decoding, additions) for additions in variants]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result().status)
            except (candidate.SidecarRefusal, OSError):
                outcomes.append('safe_refusal')
    expected = {append_synthetic(SyntheticHistory(before, decoding), additions).combined_bytes for additions in variants}
    assert outcomes.count('created') == 1 and (fixture_root / 'sidecar.bin').read_bytes() in expected
    assert (fixture_root / 'history.bin').read_bytes() == before
