"""Durable *invented-fixture* experiment for a one-answer checkpoint outbox.

This is not a live transport, a real budget, or a reader for study files. It
accepts only a caller-owned SQLite connection to an owner-only fixture at
``/tmp/opencode/oss-journal-fixture-XXXXXXXX/journal.sqlite3`` and the separate
synthetic histories accepted by ``oss_sidecar_synthetic``. All responses are
drawn from closed, invented enums; no arbitrary response text is accepted.

Within one unchanged fixture database, a reservation is committed before a
scripted mock is consumed. A sent-but-unrecorded mock result remains unknown
after restart and cannot be resent. A settled synthetic answer is bound to a
durable publication intent before the separate sidecar is touched. A pending
intent can be retried only against the same original file and fixture directory;
unclaimed sidecar temporary files and ambiguous artifacts are preserved and refused.
One request and one added item per
fixture root are supported. The same original digest and item cannot be relabelled
as a second request within one store; this conservative rule can also reject
legitimate distinct runs. The history is a toy format, not the real JSONL or
cache schema, and the accounting limits below are deliberately toy units.

These checks coordinate only cooperating users of the same unchanged database.
A fresh, copied, rolled-back or independently modified store is not a global
authority. SQLite, filesystem and process-crash behaviour depend on the host;
there is no proof of power-loss durability, same-user isolation, mount provenance,
external worker fencing, provider charges, historical liabilities, or a pushed
registration. Never point this experiment at real material, even a copied or
mounted fixture. No real-study execution is enabled by its tests.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import os
import re
import sqlite3
import stat
import threading
from typing import Iterator

from . import oss_sidecar_synthetic as sidecar
from .oss_safeguards import (
    DecodingKind,
    SyntheticDecoding,
    SyntheticHistory,
    SyntheticOutput,
    SyntheticReading,
    append_synthetic,
)


SYNTHETIC_ONLY = True
MOCK_BUDGET_UNITS = 100
MOCK_ATTEMPT_LIMIT = 12
MOCK_ATTEMPTS_PER_REQUEST = 3
_MAX_MOCK_CHARGE = 1_000_000
_DB_PATH = re.compile(r"/tmp/opencode/oss-journal-fixture-[a-z0-9_]{8}/journal\.sqlite3", re.ASCII)
_REQUEST_ID = re.compile(r"SYNTH-REQUEST-[A-Z0-9]{1,24}", re.ASCII)
_ITEM_ID = re.compile(r"SYNTH-ITEM-[A-Z0-9]{1,24}", re.ASCII)
_TICKET_ID = re.compile(r"SYNTH-TICKET-[A-Z0-9]{1,18}", re.ASCII)
_BILL_ID = re.compile(r"SYNTH-BILL-[A-Z0-9]{1,24}", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_TYPE = type(threading.Lock())
_SCOPE = "SYNTHETIC-OSS-ONE-ANSWER-OUTBOX-V1"
_DECODING = SyntheticDecoding(DecodingKind.ORIGINAL_DEFAULT)


class JournalRefusal(RuntimeError):
    """The invented-only operation cannot be safely continued."""


class MockReplyKind(Enum):
    ANSWER = "ANSWER"
    EMPTY_ECHO = "EMPTY_ECHO"
    TRANSIENT = "TRANSIENT"
    REFUSAL = "REFUSAL"
    FATAL = "FATAL"


@dataclass(frozen=True, slots=True)
class MockReply:
    """A closed synthetic result; charge units are not dollars."""

    kind: MockReplyKind
    reading: SyntheticReading | None
    charge_units: int | None

    def __post_init__(self) -> None:
        if type(self.kind) is not MockReplyKind:
            raise ValueError("a closed synthetic reply kind is required")
        if self.kind is MockReplyKind.ANSWER:
            if type(self.reading) is not SyntheticReading:
                raise ValueError("a synthetic answer needs a closed reading value")
        elif self.reading is not None:
            raise ValueError("a synthetic non-answer cannot carry a reading")
        if self.charge_units is not None:
            _charge(self.charge_units)


class MockTransport:
    """An in-memory tuple of invented replies; it has no I/O or callable adapter."""

    __slots__ = ("_replies", "_position", "_lock")

    def __init__(self, replies: tuple[MockReply, ...]) -> None:
        if type(replies) is not tuple or any(type(reply) is not MockReply for reply in replies):
            raise ValueError("only a tuple of closed synthetic replies is accepted")
        for reply in replies:
            MockReply.__post_init__(reply)
        self._replies = replies
        self._position = 0
        self._lock = threading.Lock()

    def _take(self) -> MockReply:
        if type(self._lock) is not _LOCK_TYPE:
            raise JournalRefusal("synthetic transport lock is invalid")
        with self._lock:
            if (type(self._replies) is not tuple or type(self._position) is not int
                    or not 0 <= self._position <= len(self._replies)
                    or any(type(reply) is not MockReply for reply in self._replies)):
                raise JournalRefusal("synthetic transport state is invalid")
            if self._position == len(self._replies):
                raise JournalRefusal("synthetic transport did not return a reply")
            reply = self._replies[self._position]
            self._position += 1
            MockReply.__post_init__(reply)
            return reply

    @property
    def consumed(self) -> int:
        if type(self._lock) is not _LOCK_TYPE:
            raise JournalRefusal("synthetic transport lock is invalid")
        with self._lock:
            return self._position


@dataclass(frozen=True, slots=True)
class MockJournalStatus:
    attempts: int
    spent_units: int
    held_units: int
    unknown_attempts: int
    pending_publications: int
    conflicts: int
    bound_breaches: int
    unmatched_claim_units: int


@dataclass(frozen=True, slots=True)
class MockPublicationReceipt:
    status: str
    original_sha256: str
    sidecar_sha256: str
    response_sha256: str


def _identifier(value: object, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError("an explicitly tagged synthetic identity is required")
    return value


def _charge(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_MOCK_CHARGE:
        raise ValueError("synthetic charge must be a bounded nonnegative integer")
    return value


def _identity_bytes(identity: tuple[int, ...]) -> str:
    return json.dumps([str(part) for part in identity], separators=(",", ":"))


def _validate_identity(value: object, length: int) -> None:
    if type(value) is not str:
        raise JournalRefusal("synthetic filesystem identity is malformed")
    try:
        parts = json.loads(value)
    except (TypeError, ValueError):
        raise JournalRefusal("synthetic filesystem identity is malformed") from None
    if (type(parts) is not list or len(parts) != length
            or any(type(part) is not str or re.fullmatch(r"0|[1-9][0-9]*", part, re.ASCII) is None
                   for part in parts)
            or json.dumps(parts, separators=(",", ":")) != value):
        raise JournalRefusal("synthetic filesystem identity is malformed")


def _reply_bytes(kind: str, reading: str | None) -> bytes:
    try:
        parsed_kind = MockReplyKind(kind)
        parsed_reading = SyntheticReading(reading) if reading is not None else None
        MockReply(parsed_kind, parsed_reading, None)
    except (TypeError, ValueError):
        raise JournalRefusal("stored synthetic reply is invalid") from None
    value = "NONE" if parsed_reading is None else parsed_reading.value
    return f"SYNTH-REPLY-V1|{parsed_kind.value}|{value}\n".encode("ascii")


_SCHEMA = {
    "journal_meta": """CREATE TABLE journal_meta (
        key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL
    )""",
    "journal_requests": """CREATE TABLE journal_requests (
        request_id TEXT PRIMARY KEY NOT NULL, item_id TEXT NOT NULL,
        root TEXT NOT NULL UNIQUE, root_identity TEXT NOT NULL,
        original_identity TEXT NOT NULL, original_sha256 TEXT NOT NULL,
        UNIQUE (original_sha256, item_id)
    )""",
    "journal_attempts": """CREATE TABLE journal_attempts (
        ticket_id TEXT PRIMARY KEY NOT NULL, request_id TEXT NOT NULL,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        bound INTEGER NOT NULL CHECK (bound > 0), state TEXT NOT NULL,
        reply_kind TEXT, reading TEXT, reply_bytes BLOB, reply_sha256 TEXT,
        charge INTEGER, UNIQUE (request_id, ordinal),
        FOREIGN KEY (request_id) REFERENCES journal_requests(request_id)
    )""",
    "journal_bills": """CREATE TABLE journal_bills (
        bill_id TEXT PRIMARY KEY NOT NULL, ticket_id TEXT NOT NULL,
        charge INTEGER NOT NULL CHECK (charge >= 0),
        FOREIGN KEY (ticket_id) REFERENCES journal_attempts(ticket_id)
    )""",
    "journal_conflicts": """CREATE TABLE journal_conflicts (
        id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL, bill_id TEXT NOT NULL,
        charge INTEGER NOT NULL CHECK (charge >= 0), reason TEXT NOT NULL
    )""",
    "journal_publications": """CREATE TABLE journal_publications (
        request_id TEXT PRIMARY KEY NOT NULL, ticket_id TEXT NOT NULL UNIQUE,
        sidecar_sha256 TEXT NOT NULL, response_sha256 TEXT NOT NULL, state TEXT NOT NULL,
        FOREIGN KEY (request_id) REFERENCES journal_requests(request_id),
        FOREIGN KEY (ticket_id) REFERENCES journal_attempts(ticket_id)
    )""",
}


def _database_identity(connection: sqlite3.Connection) -> tuple[str, str, str]:
    """Check a caller-opened fixture connection; this cannot make it a sandbox."""
    if (type(connection) is not sqlite3.Connection or connection.in_transaction
            or connection.isolation_level is not None or connection.row_factory is not None
            or connection.text_factory is not str):
        raise JournalRefusal("an idle, caller-owned synthetic SQLite connection is required")
    # Inspecting sqlite_temp_master itself can instantiate SQLite's empty temp
    # schema. Permit that empty, filename-less schema, but no TEMP objects or
    # attached databases that could redirect or trigger writes to main.
    temp_objects = connection.execute("SELECT 1 FROM sqlite_temp_master WHERE sql IS NOT NULL LIMIT 1").fetchone()
    databases = connection.execute("PRAGMA database_list").fetchall()
    if (not databases or databases[0][1] != "main" or len(databases) > 2
            or (len(databases) == 2 and (databases[1][1] != "temp" or databases[1][2]))):
        raise JournalRefusal("attached and nonempty temporary databases are unavailable")
    filename = databases[0][2]
    if type(filename) is not str or _DB_PATH.fullmatch(filename) is None:
        raise JournalRefusal("database is outside the synthetic fixture scope")
    if (connection.execute("PRAGMA main.journal_mode").fetchone()[0].lower() != "delete"
            or connection.execute("PRAGMA main.synchronous").fetchone()[0] < 2
            or connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1 or temp_objects):
        raise JournalRefusal("synthetic SQLite durability or schema settings are unsupported")
    parts = filename.split("/")[1:]
    with ExitStack() as stack:
        directory = os.open("/", _DIR_FLAGS)
        stack.callback(os.close, directory)
        for part in parts[:-1]:
            directory = os.open(part, _DIR_FLAGS, dir_fd=directory)
            stack.callback(os.close, directory)
        info = os.fstat(directory)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise JournalRefusal("synthetic database directory must be owner-only")
        fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=directory)
        stack.callback(os.close, fd)
        file_info = os.fstat(fd)
        visible = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
        if (not stat.S_ISREG(file_info.st_mode) or not stat.S_ISREG(visible.st_mode)
                or file_info.st_uid != os.geteuid() or visible.st_uid != os.geteuid()
                or stat.S_IMODE(file_info.st_mode) != 0o600 or file_info.st_nlink != 1
                or (file_info.st_dev, file_info.st_ino) != (visible.st_dev, visible.st_ino)):
            raise JournalRefusal("synthetic database file has unsafe identity or permissions")
        return (filename, _identity_bytes((info.st_dev, info.st_ino)),
                _identity_bytes((file_info.st_dev, file_info.st_ino)))


def _fixture_view(root: str, expected_sha256: str, *, require_empty_sidecar: bool = False):
    """Read only an explicitly tagged synthetic history through its fixture root."""
    if type(expected_sha256) is not str or _DIGEST.fullmatch(expected_sha256) is None:
        raise JournalRefusal("synthetic original hash is invalid")
    SyntheticDecoding.__post_init__(_DECODING)
    if _DECODING.kind is not DecodingKind.ORIGINAL_DEFAULT or _DECODING.max_output_tokens is not None:
        raise JournalRefusal("synthetic decoding identity changed")
    with ExitStack() as stack:
        root_fd, parent_fd, name, root_identity = sidecar._open_root(root, stack)
        sidecar._check_root(root_fd, parent_fd, name, root_identity)
        original, original_identity = sidecar._read_regular(root_fd, "history.bin")
        if sha256(original).hexdigest() != expected_sha256:
            raise JournalRefusal("synthetic original hash differs")
        history = SyntheticHistory(original, _DECODING)
        # The sidecar helper's random temporary name is not recorded in this
        # journal. After an abrupt exit, even an apparently complete temporary
        # is therefore indeterminate: never ignore or delete it during recovery.
        if os.listdir not in os.supports_fd:
            raise JournalRefusal("synthetic fixture directory enumeration is unavailable")
        if any(name.startswith(".sidecar-") and name.endswith(".tmp") for name in os.listdir(root_fd)):
            raise JournalRefusal("an unclaimed synthetic sidecar temporary needs review")
        if require_empty_sidecar:
            try:
                os.stat("sidecar.bin", dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise JournalRefusal("an unclaimed synthetic sidecar already exists")
        sidecar._check_root(root_fd, parent_fd, name, root_identity)
        return history, _identity_bytes(root_identity), _identity_bytes(original_identity)


def _fixture_sidecar(root: str) -> bytes:
    with ExitStack() as stack:
        root_fd, parent_fd, name, identity = sidecar._open_root(root, stack)
        data, _ = sidecar._read_regular(root_fd, "sidecar.bin")
        sidecar._check_root(root_fd, parent_fd, name, identity)
        return data


def _sync_fixture_sidecar(root: str, expected: bytes) -> None:
    """Sync even an identical recovered sidecar before acknowledging its intent."""
    with ExitStack() as stack:
        root_fd, parent_fd, name, root_identity = sidecar._open_root(root, stack)
        before, file_identity = sidecar._read_regular(root_fd, "sidecar.bin")
        if before != expected:
            raise JournalRefusal("synthetic sidecar differs before sync")
        fd = os.open("sidecar.bin", _FILE_FLAGS, dir_fd=root_fd)
        stack.callback(os.close, fd)
        info = os.fstat(fd)
        opened_identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if opened_identity != file_identity or info.st_nlink != 1:
            raise JournalRefusal("synthetic sidecar changed before sync")
        os.fsync(fd)
        os.fsync(root_fd)
        after, after_identity = sidecar._read_regular(root_fd, "sidecar.bin")
        sidecar._check_root(root_fd, parent_fd, name, root_identity)
        if after != expected or after_identity != file_identity:
            raise JournalRefusal("synthetic sidecar changed during sync")


class SyntheticJournal:
    """One caller-owned, synthetic SQLite store and its one-answer outboxes."""

    def __init__(self, connection: sqlite3.Connection, *, synthetic_only: bool) -> None:
        if type(synthetic_only) is not bool or synthetic_only is not True:
            raise JournalRefusal("an explicit synthetic-only assertion is required")
        identity = _database_identity(connection)
        self._connection = connection
        self._identity = identity
        self._meta = {"scope": _SCOPE, "database_path": identity[0],
                      "database_root": identity[1], "database_file": identity[2]}
        connection.execute("BEGIN IMMEDIATE")
        try:
            objects = dict(connection.execute(
                "SELECT name, sql FROM main.sqlite_master WHERE sql IS NOT NULL"
            ))
            if not objects:
                for statement in _SCHEMA.values():
                    connection.execute(statement)
                connection.executemany("INSERT INTO main.journal_meta VALUES (?, ?)", self._meta.items())
            self._check_locked()
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    def _check_locked(self) -> None:
        connection = self._connection
        objects = dict(connection.execute("SELECT name, sql FROM main.sqlite_master WHERE sql IS NOT NULL"))
        if objects != _SCHEMA or dict(connection.execute("SELECT key, value FROM main.journal_meta")) != self._meta:
            raise JournalRefusal("synthetic journal schema or identity differs")
        self._audit_locked()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if _database_identity(self._connection) != self._identity:
            raise JournalRefusal("synthetic journal file or directory changed")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._check_locked()
            yield
            self._check_locked()
            self._connection.commit()
        except BaseException:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def _audit_locked(self) -> None:
        """Reject malformed local rows; not authentication against external writers."""
        db = self._connection
        requests = {}
        for row in db.execute("SELECT request_id, item_id, root, root_identity, original_identity, "
                              "original_sha256 FROM main.journal_requests"):
            request_id, item_id, root, root_identity, original_identity, original_sha = row
            try:
                _identifier(request_id, _REQUEST_ID)
                _identifier(item_id, _ITEM_ID)
            except ValueError:
                raise JournalRefusal("synthetic request identity is malformed") from None
            if (type(root) is not str or sidecar._ROOT.fullmatch(root) is None
                    or type(original_sha) is not str or _DIGEST.fullmatch(original_sha) is None):
                raise JournalRefusal("synthetic request binding is malformed")
            _validate_identity(root_identity, 2)
            _validate_identity(original_identity, 5)
            requests[request_id] = row

        attempts = {}
        by_request: dict[str, list[tuple]] = {}
        spent = held = breaches = 0
        for row in db.execute("SELECT ticket_id, request_id, ordinal, bound, state, reply_kind, reading, "
                              "reply_bytes, reply_sha256, charge FROM main.journal_attempts "
                              "ORDER BY request_id, ordinal"):
            ticket, request, ordinal, bound, state, kind, reading, body, digest, charge = row
            try:
                _identifier(ticket, _TICKET_ID)
            except ValueError:
                raise JournalRefusal("synthetic ticket identity is malformed") from None
            if (request not in requests or type(ordinal) is not int or ordinal < 0
                    or type(bound) is not int or not 1 <= bound <= MOCK_BUDGET_UNITS
                    or state not in {"reserved", "sent", "reply_unknown", "settled", "breached"}):
                raise JournalRefusal("synthetic attempt is malformed")
            if state in {"reserved", "sent"}:
                if any(value is not None for value in (kind, reading, body, digest, charge)):
                    raise JournalRefusal("unreturned synthetic attempt has reply data")
                held += bound
            else:
                expected = _reply_bytes(kind, reading)
                if type(body) is not bytes or body != expected or digest != sha256(expected).hexdigest():
                    raise JournalRefusal("synthetic response body or digest differs")
                if state == "reply_unknown":
                    if charge is not None:
                        raise JournalRefusal("unknown synthetic charge is malformed")
                    held += bound
                else:
                    try:
                        _charge(charge)
                    except ValueError:
                        raise JournalRefusal("settled synthetic charge is malformed") from None
                    if (state == "settled" and charge > bound) or (state == "breached" and charge <= bound):
                        raise JournalRefusal("synthetic charge and bound disagree")
                    spent += charge
                    breaches += int(state == "breached")
            attempts[ticket] = row
            by_request.setdefault(request, []).append(row)
        if len(attempts) > MOCK_ATTEMPT_LIMIT:
            raise JournalRefusal("synthetic attempt ceiling is exceeded")
        for rows in by_request.values():
            if len(rows) > MOCK_ATTEMPTS_PER_REQUEST:
                raise JournalRefusal("synthetic request has too many attempts")
            for index, row in enumerate(rows):
                if row[2] != index:
                    raise JournalRefusal("synthetic attempt sequence has a gap")
                if index and (rows[index - 1][4] != "settled"
                              or rows[index - 1][5] not in {"TRANSIENT", "EMPTY_ECHO"}):
                    raise JournalRefusal("synthetic retry lacks a settled non-answer")

        bills = {}
        ticket_bills: dict[str, list[tuple[str, int]]] = {}
        for bill_id, ticket, charge in db.execute(
            "SELECT bill_id, ticket_id, charge FROM main.journal_bills ORDER BY rowid"
        ):
            try:
                _identifier(bill_id, _BILL_ID)
                _charge(charge)
            except ValueError:
                raise JournalRefusal("synthetic bill is malformed") from None
            if ticket not in attempts or attempts[ticket][4] not in {"sent", "reply_unknown", "settled", "breached"}:
                raise JournalRefusal("synthetic bill has no sent attempt")
            bills[bill_id] = (ticket, charge)
            ticket_bills.setdefault(ticket, []).append((bill_id, charge))

        conflict_rows = list(db.execute("SELECT ticket_id, bill_id, charge, reason FROM main.journal_conflicts"))
        for ticket, bill_id, charge, reason in conflict_rows:
            try:
                _identifier(ticket, _TICKET_ID)
                _identifier(bill_id, _BILL_ID)
                _charge(charge)
            except ValueError:
                raise JournalRefusal("synthetic billing conflict is malformed") from None
            if (reason not in {"bill_reused", "charge_conflict", "bill_bound_exceeded",
                               "unrecognized_ticket", "unsent_ticket"}
                    or (reason == "unrecognized_ticket" and ticket in attempts)
                    or (reason != "unrecognized_ticket" and ticket not in attempts)):
                raise JournalRefusal("synthetic billing conflict is malformed")
        for ticket, entries in ticket_bills.items():
            first_charge = entries[0][1]
            attempt = attempts[ticket]
            for index, (bill_id, charge) in enumerate(entries):
                disagreement = ((index > 0 and charge != first_charge)
                                or (attempt[4] in {"settled", "breached"} and charge != attempt[9]))
                if disagreement and (ticket, bill_id, charge, "charge_conflict") not in conflict_rows:
                    raise JournalRefusal("a contradictory synthetic bill was not quarantined")
                if (attempt[4] in {"sent", "reply_unknown"} and charge > attempt[3]
                        and (ticket, bill_id, charge, "bill_bound_exceeded") not in conflict_rows):
                    raise JournalRefusal("a synthetic bill exceeded its unresolved bound")
        if spent + held > MOCK_BUDGET_UNITS and not (breaches or conflict_rows):
            raise JournalRefusal("synthetic exposure exceeds its toy budget")

        for request, ticket, digest, response_digest, state in db.execute(
            "SELECT request_id, ticket_id, sidecar_sha256, response_sha256, state FROM main.journal_publications"
        ):
            attempt = attempts.get(ticket)
            if (request not in requests or attempt is None or attempt[1] != request
                    or attempt[4] != "settled" or attempt[5] != "ANSWER"
                    or state not in {"pending", "complete"} or type(digest) is not str
                    or _DIGEST.fullmatch(digest) is None or response_digest != attempt[8]):
                raise JournalRefusal("synthetic publication binding is malformed")

    def _blocked_locked(self, *, pending: bool = True) -> None:
        db = self._connection
        if db.execute("SELECT 1 FROM main.journal_conflicts LIMIT 1").fetchone():
            raise JournalRefusal("synthetic billing conflict is quarantined")
        if db.execute("SELECT 1 FROM main.journal_attempts WHERE state = 'breached' LIMIT 1").fetchone():
            raise JournalRefusal("synthetic charge bound was breached")
        if pending and db.execute("SELECT 1 FROM main.journal_publications WHERE state = 'pending' LIMIT 1").fetchone():
            raise JournalRefusal("synthetic publication recovery is pending")

    def status(self) -> MockJournalStatus:
        with self._transaction():
            rows = self._connection.execute("SELECT ticket_id, bound, state, charge FROM main.journal_attempts").fetchall()
            claims: dict[str, int] = {}
            for ticket, amount in self._connection.execute("SELECT ticket_id, charge FROM main.journal_bills"):
                claims[ticket] = max(claims.get(ticket, 0), amount)
            unmatched = 0
            for ticket, amount, reason in self._connection.execute(
                "SELECT ticket_id, charge, reason FROM main.journal_conflicts"
            ):
                if reason in {"unrecognized_ticket", "unsent_ticket"}:
                    unmatched += amount
                else:
                    claims[ticket] = max(claims.get(ticket, 0), amount)
            spent = sum(charge for _, _, state, charge in rows if state in {"settled", "breached"})
            held = unmatched
            for ticket, bound, state, charge in rows:
                baseline = charge if state in {"settled", "breached"} else bound
                if state not in {"settled", "breached"}:
                    held += baseline
                held += max(0, claims.get(ticket, 0) - baseline)
            pending = self._connection.execute(
                "SELECT COUNT(*) FROM main.journal_publications WHERE state = 'pending'"
            ).fetchone()[0]
            conflicts = self._connection.execute("SELECT COUNT(*) FROM main.journal_conflicts").fetchone()[0]
            return MockJournalStatus(len(rows), spent, held,
                                     sum(state in {"sent", "reply_unknown"} for _, _, state, _ in rows),
                                     pending, conflicts, sum(state == "breached" for _, _, state, _ in rows),
                                     unmatched)

    def register(self, *, request_id: str, item_id: str, root: str, original_sha256: str) -> None:
        _identifier(request_id, _REQUEST_ID)
        _identifier(item_id, _ITEM_ID)
        with self._transaction():
            self._blocked_locked()
            db = self._connection
            existing = db.execute("SELECT request_id, item_id, root, root_identity, original_identity, "
                                  "original_sha256 FROM main.journal_requests WHERE request_id = ?",
                                  (request_id,)).fetchone()
            history, root_identity, original_identity = _fixture_view(
                root, original_sha256, require_empty_sidecar=existing is None
            )
            if any(record.item_id == item_id for record in history.records):
                raise JournalRefusal("synthetic item already exists in the original history")
            binding = (request_id, item_id, root, root_identity, original_identity, original_sha256)
            if existing is not None:
                if existing != binding:
                    raise JournalRefusal("synthetic request identity was rebound")
                return
            if db.execute("SELECT 1 FROM main.journal_requests WHERE root = ?", (root,)).fetchone():
                raise JournalRefusal("synthetic fixture root is already assigned")
            if db.execute("SELECT 1 FROM main.journal_requests WHERE original_sha256 = ? AND item_id = ?",
                          (original_sha256, item_id)).fetchone():
                raise JournalRefusal("synthetic original and item are already assigned")
            db.execute("INSERT INTO main.journal_requests VALUES (?, ?, ?, ?, ?, ?)", binding)

    def reserve(self, *, request_id: str, ticket_id: str, bound_units: int) -> None:
        _identifier(request_id, _REQUEST_ID)
        _identifier(ticket_id, _TICKET_ID)
        if type(bound_units) is not int or not 1 <= bound_units <= MOCK_BUDGET_UNITS:
            raise ValueError("a positive, bounded synthetic attempt hold is required")
        with self._transaction():
            self._blocked_locked()
            db = self._connection
            if not db.execute("SELECT 1 FROM main.journal_requests WHERE request_id = ?", (request_id,)).fetchone():
                raise JournalRefusal("synthetic request is unknown")
            if db.execute("SELECT 1 FROM main.journal_attempts WHERE ticket_id = ?", (ticket_id,)).fetchone():
                raise JournalRefusal("synthetic ticket was already reserved")
            previous = db.execute("SELECT ordinal, state, reply_kind FROM main.journal_attempts "
                                  "WHERE request_id = ? ORDER BY ordinal DESC LIMIT 1", (request_id,)).fetchone()
            ordinal = 0
            if previous is not None:
                ordinal = previous[0] + 1
                if (ordinal >= MOCK_ATTEMPTS_PER_REQUEST or previous[1] != "settled"
                        or previous[2] not in {"TRANSIENT", "EMPTY_ECHO"}):
                    raise JournalRefusal("synthetic retry needs a settled observed non-answer")
            rows = db.execute("SELECT bound, state, charge FROM main.journal_attempts").fetchall()
            exposure = sum(charge if state in {"settled", "breached"} else bound
                           for bound, state, charge in rows)
            if len(rows) >= MOCK_ATTEMPT_LIMIT or exposure + bound_units > MOCK_BUDGET_UNITS:
                raise JournalRefusal("synthetic attempt or toy budget ceiling is exhausted")
            db.execute("INSERT INTO main.journal_attempts "
                       "(ticket_id, request_id, ordinal, bound, state) VALUES (?, ?, ?, ?, 'reserved')",
                       (ticket_id, request_id, ordinal, bound_units))

    def dispatch(self, ticket_id: str, transport: MockTransport) -> str:
        _identifier(ticket_id, _TICKET_ID)
        if type(transport) is not MockTransport:
            raise JournalRefusal("only the closed synthetic transport is accepted")
        with self._transaction():
            self._blocked_locked()
            db = self._connection
            state = db.execute("SELECT state FROM main.journal_attempts WHERE ticket_id = ?", (ticket_id,)).fetchone()
            if state != ("reserved",):
                raise JournalRefusal("synthetic ticket is not an unsent reservation")
            if db.execute("SELECT 1 FROM main.journal_attempts WHERE state IN ('sent', 'reply_unknown') LIMIT 1").fetchone():
                raise JournalRefusal("an earlier synthetic attempt is unresolved")
            db.execute("UPDATE main.journal_attempts SET state = 'sent' WHERE ticket_id = ?", (ticket_id,))
        # The committed sent state is intentionally retained if the mock fails or
        # the process dies before the returned body is durably recorded.
        reply = MockTransport._take(transport)
        return self._record_mock_reply(ticket_id, reply)

    def _record_mock_reply(self, ticket_id: str, reply: MockReply) -> str:
        if type(reply) is not MockReply:
            raise JournalRefusal("synthetic reply type differs")
        MockReply.__post_init__(reply)
        kind = reply.kind.value
        reading = reply.reading.value if reply.reading is not None else None
        body = _reply_bytes(kind, reading)
        with self._transaction():
            db = self._connection
            row = db.execute("SELECT state, bound FROM main.journal_attempts WHERE ticket_id = ?",
                             (ticket_id,)).fetchone()
            if row is None or row[0] != "sent":
                raise JournalRefusal("synthetic sent state changed before reply recording")
            state = ("reply_unknown" if reply.charge_units is None else
                     "breached" if reply.charge_units > row[1] else "settled")
            db.execute("UPDATE main.journal_attempts SET state = ?, reply_kind = ?, reading = ?, "
                       "reply_bytes = ?, reply_sha256 = ?, charge = ? WHERE ticket_id = ?",
                       (state, kind, reading, body, sha256(body).hexdigest(), reply.charge_units, ticket_id))
            if reply.charge_units is not None:
                for bill_id, charge in db.execute(
                    "SELECT bill_id, charge FROM main.journal_bills WHERE ticket_id = ?", (ticket_id,)
                ).fetchall():
                    if charge != reply.charge_units and not db.execute(
                        "SELECT 1 FROM main.journal_conflicts WHERE ticket_id = ? AND bill_id = ? "
                        "AND charge = ? AND reason = 'charge_conflict'", (ticket_id, bill_id, charge)
                    ).fetchone():
                        db.execute("INSERT INTO main.journal_conflicts (ticket_id, bill_id, charge, reason) "
                                   "VALUES (?, ?, ?, 'charge_conflict')", (ticket_id, bill_id, charge))
            return state

    def record_bill(self, *, ticket_id: str, bill_id: str, charge_units: int) -> str:
        """Record a synthetic bill or quarantine a contradiction; no real proof is supplied."""
        _identifier(ticket_id, _TICKET_ID)
        _identifier(bill_id, _BILL_ID)
        _charge(charge_units)
        with self._transaction():
            db = self._connection
            attempt = db.execute("SELECT state, bound, charge FROM main.journal_attempts WHERE ticket_id = ?",
                                 (ticket_id,)).fetchone()
            if attempt is None or attempt[0] == "reserved":
                reason = "unrecognized_ticket" if attempt is None else "unsent_ticket"
                db.execute("INSERT INTO main.journal_conflicts (ticket_id, bill_id, charge, reason) "
                           "VALUES (?, ?, ?, ?)", (ticket_id, bill_id, charge_units, reason))
                return "conflict"
            known = db.execute("SELECT ticket_id, charge FROM main.journal_bills WHERE bill_id = ?",
                               (bill_id,)).fetchone()
            if known == (ticket_id, charge_units):
                if attempt[0] == "reply_unknown":
                    conflicting = db.execute("SELECT 1 FROM main.journal_bills WHERE ticket_id = ? "
                                             "AND charge != ? LIMIT 1", (ticket_id, charge_units)).fetchone()
                    if conflicting:
                        return "conflict"
                    state = "breached" if charge_units > attempt[1] else "settled"
                    db.execute("UPDATE main.journal_attempts SET state = ?, charge = ? WHERE ticket_id = ?",
                               (state, charge_units, ticket_id))
                    return state
                return "unchanged"
            if known is not None:
                db.execute("INSERT INTO main.journal_conflicts (ticket_id, bill_id, charge, reason) "
                           "VALUES (?, ?, ?, 'bill_reused')", (ticket_id, bill_id, charge_units))
                return "conflict"
            prior = db.execute("SELECT charge FROM main.journal_bills WHERE ticket_id = ? ORDER BY rowid LIMIT 1",
                               (ticket_id,)).fetchone()
            db.execute("INSERT INTO main.journal_bills VALUES (?, ?, ?)", (bill_id, ticket_id, charge_units))
            if attempt[0] in {"sent", "reply_unknown"}:
                conflict = False
                if prior is not None and prior[0] != charge_units:
                    db.execute("INSERT INTO main.journal_conflicts (ticket_id, bill_id, charge, reason) "
                               "VALUES (?, ?, ?, 'charge_conflict')", (ticket_id, bill_id, charge_units))
                    conflict = True
                if charge_units > attempt[1]:
                    db.execute("INSERT INTO main.journal_conflicts (ticket_id, bill_id, charge, reason) "
                               "VALUES (?, ?, ?, 'bill_bound_exceeded')", (ticket_id, bill_id, charge_units))
                    conflict = True
                if attempt[0] == "sent" or conflict:
                    return "conflict" if conflict else "awaiting_response"
            if attempt[0] == "reply_unknown":
                state = "breached" if charge_units > attempt[1] else "settled"
                db.execute("UPDATE main.journal_attempts SET state = ?, charge = ? WHERE ticket_id = ?",
                           (state, charge_units, ticket_id))
                return state
            if charge_units != attempt[2]:
                db.execute("INSERT INTO main.journal_conflicts (ticket_id, bill_id, charge, reason) "
                           "VALUES (?, ?, ?, 'charge_conflict')", (ticket_id, bill_id, charge_units))
                return "conflict"
            return "confirmed"

    def _publication_binding_locked(self, ticket_id: str):
        db = self._connection
        row = db.execute("SELECT a.request_id, a.state, a.reply_kind, a.reading, a.reply_sha256, "
                         "r.item_id, r.root, r.root_identity, r.original_identity, r.original_sha256 "
                         "FROM main.journal_attempts a JOIN main.journal_requests r ON a.request_id = r.request_id "
                         "WHERE a.ticket_id = ?", (ticket_id,)).fetchone()
        if row is None or row[1] != "settled" or row[2] != "ANSWER":
            raise JournalRefusal("a settled synthetic answer is required")
        if db.execute("SELECT 1 FROM main.journal_attempts WHERE state IN "
                      "('reserved', 'sent', 'reply_unknown') LIMIT 1").fetchone():
            raise JournalRefusal("outstanding synthetic attempts block publication")
        request, _, _, reading, response_sha, item, root, root_id, original_id, original_sha = row
        history, actual_root, actual_original = _fixture_view(root, original_sha)
        if (actual_root, actual_original) != (root_id, original_id):
            raise JournalRefusal("synthetic fixture or original identity changed")
        output = SyntheticOutput(item, _DECODING,
                                 "SYNTH-SOURCE-TICKET" + ticket_id.removeprefix("SYNTH-TICKET-"),
                                 SyntheticReading(reading))
        decision = append_synthetic(history, (output,))
        if decision.added_items != (item,) or decision.duplicate_items:
            raise JournalRefusal("synthetic answer is not a new checkpoint item")
        return request, root, original_sha, response_sha, output, decision

    def publish(self, ticket_id: str) -> MockPublicationReceipt:
        """Publish or recheck a single synthetic answer, with a durable prior intent."""
        _identifier(ticket_id, _TICKET_ID)
        with self._transaction():
            self._blocked_locked(pending=False)
            request, root, original_sha, response_sha, output, decision = self._publication_binding_locked(ticket_id)
            db = self._connection
            existing = db.execute("SELECT ticket_id, sidecar_sha256, response_sha256, state "
                                  "FROM main.journal_publications WHERE request_id = ?", (request,)).fetchone()
            if existing is None:
                if db.execute("SELECT 1 FROM main.journal_publications WHERE state = 'pending' LIMIT 1").fetchone():
                    raise JournalRefusal("another synthetic publication needs recovery")
                db.execute("INSERT INTO main.journal_publications VALUES (?, ?, ?, ?, 'pending')",
                           (request, ticket_id, decision.combined_sha256, response_sha))
            elif existing[:3] != (ticket_id, decision.combined_sha256, response_sha):
                raise JournalRefusal("synthetic publication was rebound")
        return self._finish_publication(ticket_id)

    def _finish_publication(self, ticket_id: str) -> MockPublicationReceipt:
        # The intent is committed before this transaction. Holding the SQLite
        # write lock through local publication also fences cooperating bill and
        # dispatch operations until confirmation or a crash.
        with self._transaction():
            self._blocked_locked(pending=False)
            request, root, original_sha, response_sha, output, decision = self._publication_binding_locked(ticket_id)
            db = self._connection
            claim = db.execute("SELECT ticket_id, sidecar_sha256, response_sha256, state "
                               "FROM main.journal_publications WHERE request_id = ?", (request,)).fetchone()
            if claim is None or claim[:3] != (ticket_id, decision.combined_sha256, response_sha):
                raise JournalRefusal("synthetic publication intent differs")
            if claim[3] == "complete":
                # Do not recreate a missing artifact after it was marked complete.
                if _fixture_sidecar(root) != decision.combined_bytes:
                    raise JournalRefusal("completed synthetic sidecar differs")
                if self._publication_binding_locked(ticket_id)[5].combined_bytes != decision.combined_bytes:
                    raise JournalRefusal("completed synthetic fixture changed during verification")
                status = "verified_existing"
            else:
                receipt = sidecar.prepare_synthetic_sidecar(
                    root, expected_original_sha256=original_sha, decoding=_DECODING,
                    additions=(output,), synthetic_only=True,
                )
                if (receipt.original_sha256 != original_sha or receipt.sidecar_sha256 != decision.combined_sha256
                        or receipt.added_count != 1 or receipt.duplicate_count != 0):
                    raise JournalRefusal("synthetic sidecar receipt differs")
                # An identical artifact can be left by an earlier interrupted
                # publication before its directory sync. Re-sync it rather than
                # assuming that observing its name made the link durable.
                _sync_fixture_sidecar(root, decision.combined_bytes)
                # Recheck both fixture identities after publication before the
                # database is allowed to mark the intent complete.
                again = self._publication_binding_locked(ticket_id)
                if again[5].combined_bytes != decision.combined_bytes or _fixture_sidecar(root) != decision.combined_bytes:
                    raise JournalRefusal("synthetic sidecar changed before confirmation")
                db.execute("UPDATE main.journal_publications SET state = 'complete' WHERE request_id = ?",
                           (request,))
                status = receipt.status
            return MockPublicationReceipt(status, original_sha, decision.combined_sha256, response_sha)
