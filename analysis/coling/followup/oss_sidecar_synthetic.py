"""Synthetic-only, byte-preserving checkpoint sidecar experiment.

This candidate operates only on explicitly invented fixtures in private,
owner-controlled directories named ``/tmp/opencode/oss-sidecar-fixture-XXXXXXXX``.
It has no credential, model, network, study-ledger or real-cache interface and
must not be pointed at actual study outputs, even via a copy or mount alias.

The original synthetic history is never opened for writing. A separate sidecar
is created without overwrite after an in-memory conflict/decoding check, using
an exclusive temporary file, file fsync, atomic hard-link publication and
directory fsync. Existing sidecars are accepted only if byte-identical.
Caller-controlled paths, in-process checks and local filesystem calls do not
establish real-world provenance, independent review, reliable crash recovery,
budget authority or a prospective amendment. Python is not a security sandbox.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from hashlib import sha256
import os
import re
import secrets
import stat
import threading

from .oss_safeguards import (
    MAX_SYNTHETIC_HISTORY_BYTES,
    OperationState,
    ReplyKind,
    SyntheticDecoding,
    SyntheticHistory,
    SyntheticModel,
    SyntheticOperation,
    SyntheticOutput,
    SyntheticPhysicalBound,
    SyntheticRun,
    SyntheticSimulation,
    SyntheticSnapshot,
    SyntheticSpec,
    SyntheticTicket,
    TicketState,
    append_synthetic,
)


_ROOT = re.compile(r"/tmp/opencode/oss-sidecar-fixture-[a-z0-9_]{8}", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_ORIGINAL_NAME = "history.bin"
_SIDECAR_NAME = "sidecar.bin"
_RLOCK_TYPE = type(threading.RLock())


class SidecarRefusal(ValueError):
    """The synthetic sidecar could not be safely prepared or published."""


@dataclass(frozen=True, slots=True)
class SyntheticSidecarReceipt:
    """A synthetic snapshot, not evidence of real output preservation."""

    status: str
    original_sha256: str
    sidecar_sha256: str
    added_count: int
    duplicate_count: int


def _open_root(root: object, stack: ExitStack) -> tuple[int, int, str, tuple[int, int]]:
    if type(root) is not str or _ROOT.fullmatch(root) is None:
        raise SidecarRefusal("root is outside the synthetic fixture scope")
    parts = root.split("/")[1:]
    directory = os.open("/", _DIR_FLAGS)
    stack.callback(os.close, directory)
    parent = -1
    for index, part in enumerate(parts):
        parent = directory
        directory = os.open(part, _DIR_FLAGS, dir_fd=parent)
        stack.callback(os.close, directory)
        if index == len(parts) - 1:
            info = os.fstat(directory)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise SidecarRefusal("synthetic fixture root must be owner-only")
            visible = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if (visible.st_dev, visible.st_ino) != (info.st_dev, info.st_ino):
                raise SidecarRefusal("synthetic fixture root changed")
            return directory, parent, part, (info.st_dev, info.st_ino)
    raise SidecarRefusal("invalid synthetic fixture root")


def _check_root(root_fd: int, parent_fd: int, name: str, identity: tuple[int, int]) -> None:
    info = os.fstat(root_fd)
    visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (not stat.S_ISDIR(visible.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or (info.st_dev, info.st_ino) != identity or (visible.st_dev, visible.st_ino) != identity):
        raise SidecarRefusal("synthetic fixture root changed")


def _read_regular(root_fd: int, name: str) -> tuple[bytes, tuple[int, int, int, int, int]]:
    fd = os.open(name, _FILE_FLAGS, dir_fd=root_fd)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o077 or before.st_nlink != 1
                or before.st_size > MAX_SYNTHETIC_HISTORY_BYTES):
            raise SidecarRefusal("synthetic file has unsafe type, ownership, mode, links or size")
        raw = handle.read(MAX_SYNTHETIC_HISTORY_BYTES + 1)
        after = os.fstat(handle.fileno())
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    visible = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    visible_id = (visible.st_dev, visible.st_ino, visible.st_size, visible.st_mtime_ns, visible.st_ctime_ns)
    if (len(raw) != before.st_size or len(raw) > MAX_SYNTHETIC_HISTORY_BYTES or before_id != after_id
            or visible_id != before_id or not stat.S_ISREG(visible.st_mode) or visible.st_uid != os.geteuid()
            or stat.S_IMODE(visible.st_mode) & 0o077 or visible.st_nlink != 1):
        raise SidecarRefusal("synthetic file changed during read")
    return raw, before_id


def _write_all(fd: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(fd, content[offset:])
        if written <= 0:
            raise SidecarRefusal("synthetic sidecar write did not progress")
        offset += written


def _publish_new(root_fd: int, temporary: str) -> None:
    os.link(temporary, _SIDECAR_NAME, src_dir_fd=root_fd, dst_dir_fd=root_fd, follow_symlinks=False)


def _sync_directory(root_fd: int) -> None:
    os.fsync(root_fd)


def _verify_temporary(root_fd: int, temporary: str, fd: int, identity: tuple[int, int],
                      expected: bytes, links: int) -> None:
    before = os.fstat(fd)
    visible = os.stat(temporary, dir_fd=root_fd, follow_symlinks=False)
    if (not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(visible.st_mode)
            or before.st_uid != os.geteuid() or visible.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600 or stat.S_IMODE(visible.st_mode) != 0o600
            or (before.st_dev, before.st_ino) != identity or (visible.st_dev, visible.st_ino) != identity
            or before.st_nlink != links or visible.st_nlink != links or before.st_size != len(expected)):
        raise SidecarRefusal("synthetic temporary file changed")
    os.lseek(fd, 0, os.SEEK_SET)
    raw = bytearray()
    while len(raw) <= MAX_SYNTHETIC_HISTORY_BYTES:
        chunk = os.read(fd, min(65536, MAX_SYNTHETIC_HISTORY_BYTES + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
    after = os.fstat(fd)
    visible_after = os.stat(temporary, dir_fd=root_fd, follow_symlinks=False)
    before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_nlink)
    after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink)
    visible_id = (visible_after.st_dev, visible_after.st_ino, visible_after.st_size,
                  visible_after.st_mtime_ns, visible_after.st_ctime_ns, visible_after.st_nlink)
    if bytes(raw) != expected or before_id != after_id or visible_id != after_id or not stat.S_ISREG(visible_after.st_mode):
        raise SidecarRefusal("synthetic temporary file changed during verification")


def _verify_publication(root_fd: int, temporary: str, fd: int, identity: tuple[int, int], expected: bytes) -> None:
    _verify_temporary(root_fd, temporary, fd, identity, expected, 2)
    sidecar = os.stat(_SIDECAR_NAME, dir_fd=root_fd, follow_symlinks=False)
    info = os.fstat(fd)
    if (not stat.S_ISREG(sidecar.st_mode) or sidecar.st_uid != os.geteuid()
            or stat.S_IMODE(sidecar.st_mode) != 0o600 or sidecar.st_nlink != 2
            or (sidecar.st_dev, sidecar.st_ino) != identity
            or (sidecar.st_size, sidecar.st_mtime_ns, sidecar.st_ctime_ns)
            != (info.st_size, info.st_mtime_ns, info.st_ctime_ns)):
        raise SidecarRefusal("synthetic sidecar publication changed")


def _remove_owned_temporary(root_fd: int, temporary: str, identity: tuple[int, int]) -> None:
    try:
        visible = os.stat(temporary, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(visible.st_mode) or (visible.st_dev, visible.st_ino) != identity:
        raise SidecarRefusal("synthetic temporary was replaced and was not removed")
    os.unlink(temporary, dir_fd=root_fd)


def prepare_synthetic_sidecar(
    root: str, *, expected_original_sha256: str, decoding: SyntheticDecoding,
    additions: tuple[SyntheticOutput, ...], synthetic_only: bool,
) -> SyntheticSidecarReceipt:
    """Publish one synthetic sidecar without opening the original for writing.

    ``synthetic_only`` is an assertion, not proof of fixture provenance. A
    failed or interrupted publication can leave an owned temporary file; never
    remove unknown files or assume a failed call means no sidecar exists.
    """
    if type(synthetic_only) is not bool or synthetic_only is not True:
        raise SidecarRefusal("explicit synthetic-only assertion is required")
    if type(expected_original_sha256) is not str or _DIGEST.fullmatch(expected_original_sha256) is None:
        raise SidecarRefusal("expected original identity must be a lowercase SHA256")
    if type(decoding) is not SyntheticDecoding or type(additions) is not tuple:
        raise SidecarRefusal("exact synthetic decoding and addition tuple are required")
    SyntheticDecoding.__post_init__(decoding)
    for record in additions:
        if type(record) is not SyntheticOutput:
            raise SidecarRefusal("only exact synthetic outputs are accepted")
        SyntheticOutput.__post_init__(record)
        SyntheticDecoding.__post_init__(record.decoding)
    if (os.link not in os.supports_dir_fd or os.stat not in os.supports_dir_fd
            or os.link not in os.supports_follow_symlinks or os.stat not in os.supports_follow_symlinks):
        raise SidecarRefusal("required no-overwrite filesystem operations are unavailable")

    with ExitStack() as stack:
        root_fd, parent_fd, root_name, root_identity = _open_root(root, stack)
        _check_root(root_fd, parent_fd, root_name, root_identity)
        original, original_identity = _read_regular(root_fd, _ORIGINAL_NAME)
        if sha256(original).hexdigest() != expected_original_sha256:
            raise SidecarRefusal("synthetic original hash differs")
        history = SyntheticHistory(original, decoding)
        decision = append_synthetic(history, additions)

        try:
            existing, existing_identity = _read_regular(root_fd, _SIDECAR_NAME)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            current, current_identity = _read_regular(root_fd, _ORIGINAL_NAME)
            _check_root(root_fd, parent_fd, root_name, root_identity)
            if current != original or current_identity != original_identity:
                raise SidecarRefusal("synthetic original changed before comparison")
            if existing != decision.combined_bytes:
                raise SidecarRefusal("existing synthetic sidecar conflicts")
            current_sidecar, current_sidecar_identity = _read_regular(root_fd, _SIDECAR_NAME)
            _check_root(root_fd, parent_fd, root_name, root_identity)
            if current_sidecar != existing or current_sidecar_identity != existing_identity:
                raise SidecarRefusal("existing synthetic sidecar changed during comparison")
            return SyntheticSidecarReceipt("already_present", decision.historical_sha256,
                                           decision.combined_sha256, len(decision.added_items),
                                           len(decision.duplicate_items))

        temporary = ".sidecar-" + secrets.token_hex(16) + ".tmp"
        created = False
        temporary_identity = None
        published_identity = None
        published_status = "created"
        fd = None
        try:
            fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=root_fd)
            created = True
            temporary_info = os.fstat(fd)
            temporary_identity = (temporary_info.st_dev, temporary_info.st_ino)
            _write_all(fd, decision.combined_bytes)
            os.fsync(fd)
            _verify_temporary(root_fd, temporary, fd, temporary_identity, decision.combined_bytes, 1)
            current, current_identity = _read_regular(root_fd, _ORIGINAL_NAME)
            _check_root(root_fd, parent_fd, root_name, root_identity)
            if current != original or current_identity != original_identity:
                raise SidecarRefusal("synthetic original changed before publication")
            try:
                _publish_new(root_fd, temporary)
            except FileExistsError:
                concurrent, concurrent_identity = _read_regular(root_fd, _SIDECAR_NAME)
                if concurrent != decision.combined_bytes:
                    raise SidecarRefusal("concurrent synthetic sidecar conflicts") from None
                published_status = "already_present"
                published_identity = concurrent_identity[:2]
            else:
                _verify_publication(root_fd, temporary, fd, temporary_identity, decision.combined_bytes)
                published_identity = temporary_identity
                current, current_identity = _read_regular(root_fd, _ORIGINAL_NAME)
                _check_root(root_fd, parent_fd, root_name, root_identity)
                if current != original or current_identity != original_identity:
                    raise SidecarRefusal("synthetic original changed after publication")
                _sync_directory(root_fd)
        finally:
            if fd is not None:
                os.close(fd)
            if created and temporary_identity is not None:
                _remove_owned_temporary(root_fd, temporary, temporary_identity)
        _sync_directory(root_fd)
        current, current_identity = _read_regular(root_fd, _ORIGINAL_NAME)
        current_sidecar, current_sidecar_identity = _read_regular(root_fd, _SIDECAR_NAME)
        _check_root(root_fd, parent_fd, root_name, root_identity)
        if current != original or current_identity != original_identity:
            raise SidecarRefusal("synthetic original changed before receipt")
        if current_sidecar != decision.combined_bytes or current_sidecar_identity[:2] != published_identity:
            raise SidecarRefusal("synthetic sidecar changed before receipt")
        return SyntheticSidecarReceipt(published_status, decision.historical_sha256,
                                       decision.combined_sha256, len(decision.added_items),
                                       len(decision.duplicate_items))


def prepare_guarded_synthetic_sidecar(
    root: str, *, expected_original_sha256: str, simulation: SyntheticSimulation,
    operation_id: int, ticket_id: str, output: SyntheticOutput, synthetic_only: bool,
) -> SyntheticSidecarReceipt:
    """Link one invented output to a settled mock ticket before sidecar publication.

    The output's synthetic reading remains a caller assertion: the mock reply
    does not carry actual response bytes. This in-process guard has no durable
    or cross-process budget authority and cannot authenticate provider billing,
    cache provenance, original content, or a real registration. It is not a
    live runner and must not be used for actual study material.
    """
    if type(synthetic_only) is not bool or synthetic_only is not True:
        raise SidecarRefusal("explicit synthetic-only assertion is required")
    if type(simulation) is not SyntheticSimulation or type(output) is not SyntheticOutput:
        raise SidecarRefusal("exact synthetic simulation and output are required")
    if type(operation_id) is not int or type(ticket_id) is not str:
        raise SidecarRefusal("synthetic operation and ticket identities are required")
    if type(simulation._lock) is not _RLOCK_TYPE:
        raise SidecarRefusal("synthetic simulation lock is invalid")
    SyntheticOutput.__post_init__(output)
    with simulation._lock:
        if any(name.startswith("_") and callable(vars(SyntheticSimulation).get(name))
               for name in vars(simulation)):
            raise SidecarRefusal("synthetic simulation shadows a private ledger method")
        SyntheticSimulation._check_ready_locked(simulation)
        operation = SyntheticSimulation.operation(simulation, operation_id)
        ticket = SyntheticSimulation.ticket(simulation, ticket_id)
        snapshot = SyntheticSimulation.snapshot(simulation)
        specification = simulation._spec
        if (type(specification) is not SyntheticSpec or type(operation) is not SyntheticOperation
                or type(ticket) is not SyntheticTicket or type(snapshot) is not SyntheticSnapshot):
            raise SidecarRefusal("synthetic specification is invalid")
        SyntheticSpec.__post_init__(specification)
        SyntheticDecoding.__post_init__(specification.decoding)
        SyntheticPhysicalBound.__post_init__(specification.physical_bound)
        run = SyntheticSimulation.run(simulation, operation.run_id)
        if type(run) is not SyntheticRun:
            raise SidecarRefusal("synthetic run is invalid")
        SyntheticRun.__post_init__(run)
        if (operation.state is not OperationState.COMPLETE or ticket.state is not TicketState.SETTLED
                or ticket.outcome is not ReplyKind.ANSWER or type(operation.operation_id) is not int
                or operation.operation_id != operation_id or type(ticket.operation_id) is not int
                or ticket.ticket_id != ticket_id or ticket.operation_id != operation.operation_id
                or ticket.run_id != operation.run_id or run.run_id != operation.run_id
                or type(ticket.charge_nanos) is not int or ticket.charge_nanos < 0
                or type(ticket.bound_nanos) is not int or ticket.bound_nanos != specification.physical_bound.worst_case_nanos
                or ticket.charge_nanos > ticket.bound_nanos or type(operation.physical_attempts) is not int
                or operation.physical_attempts < 1
                or run.model is not SyntheticModel.OSS or run.cap_nanos is None
                or snapshot.attempt_reservations_nanos != 0):
            raise SidecarRefusal("a matching settled synthetic answer is required")
        suffix = ticket.ticket_id.removeprefix("SYNTH-TICKET-")
        if output.provenance != "SYNTH-SOURCE-TICKET" + suffix or output.decoding != specification.decoding:
            raise SidecarRefusal("synthetic output provenance or decoding differs")
        return prepare_synthetic_sidecar(root, expected_original_sha256=expected_original_sha256,
                                         decoding=specification.decoding, additions=(output,),
                                         synthetic_only=True)
