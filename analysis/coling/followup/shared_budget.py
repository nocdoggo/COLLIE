"""Synthetic accounting experiment; NOT a provider-facing budget coordinator.

All identities, evidence, amounts and databases supplied here must be invented.
There is no HTTP client, dispatch hook, provider configuration or real-model
identifier.  SQLite must report no database filename, or a specially named
scratch database under /tmp/opencode.  A filename-less SQLite database may also be
an anonymous temporary database.  These checks prevent some accidents; they are
not a security boundary and cannot establish that a caller's claims are true.

The snapshot attester asserts that its item IDs are complete, correctly
attributed, and mutually disjoint physical charges.  Local tags, a hash, and
different attester names do NOT prove billing finality, an upper bound, historical
ledger correctness, quiescence, provider limits, prospective registration, or
external-process fencing.  In particular, the original frozen runner does not
consult this module.  Real-provider use is unavailable, not merely disabled by a
configuration switch; an independently reviewed integrated design is still needed.
Lane roles and target identities are also only synthetic claims: this module cannot
verify a payload, prevent relabelling a logical request, or identify a real model.

Amounts are integer microdollars.  A reservation consumes an HTTP-attempt slot
immediately and cannot be cancelled.  A hold changes to the evidenced final bill
only when that bill is separately supplied; a retry additionally requires a
separately evidenced non-return from a different synthetic attester.  Conflicting
return/non-return evidence, malformed or conflicting bills, and bills exceeding
an asserted bound are retained and permanently block new reservations. A later
return cannot undo an already reserved retry. Unbounded external liabilities block
until separately resolved. No planned-first-attempt slots are reserved here.
The chosen synthetic global retry ceiling is three; each attested snapshot must
explicitly select an allowance no larger than that.  This is not a registered
allowance for any real programme.

SQLite transactions coordinate only cooperating users of the SAME synthetic store.
They do not fence another database, runner, process, or provider.  The caller owns
the connection, must not use it concurrently, and must not dispatch anything before
a reservation commits.  Crash durability depends on SQLite and its filesystem;
this prototype makes no claim about power loss or external writers.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from hashlib import sha256
import json
import os.path
import re
import sqlite3
from types import MappingProxyType
from typing import Iterator, Mapping


MICRODOLLARS = 1_000_000
STUDY_CAP = 200 * MICRODOLLARS
PROGRAMME_CAP = 10 * MICRODOLLARS
HTTP_ATTEMPT_CAP = 1_400
SYNTHETIC_GLOBAL_RETRY_CEILING = 3
SYNTHETIC_ONLY = True
_MAX_SQLITE_INTEGER = (1 << 63) - 1
_SCRATCH_ROOT = "/tmp/opencode"


class Target(Enum):
    """Closed, invented identities, not aliases for actual provider models.

    OTHER_STUDY means a positively attributed non-programme cost, not an
    unknown model or a way to remove an original model's cost from its cap.
    """

    LLAMA = "synthetic:model:llama"
    DEEPSEEK = "synthetic:model:deepseek"
    OSS_20B = "synthetic:model:gpt-oss-20b"
    OSS_120B = "synthetic:model:gpt-oss-120b"
    JUDGE_A = "synthetic:model:judge-a"
    JUDGE_B = "synthetic:model:judge-b"
    ADMIN = "synthetic:operation:admin"
    OTHER_STUDY = "synthetic:category:other-study"


class Role(Enum):
    ORIGINAL = "synthetic:role:original"
    JUDGE = "synthetic:role:judge"
    ADMIN = "synthetic:role:admin"


MODEL_CAPS = MappingProxyType(
    {
        Target.LLAMA: 5 * MICRODOLLARS,
        Target.DEEPSEEK: 12 * MICRODOLLARS,
        Target.OSS_20B: 6 * MICRODOLLARS,
    }
)
_PROGRAMME_ONLY = frozenset(
    {Target.OSS_120B, Target.JUDGE_A, Target.JUDGE_B, Target.ADMIN}
)


class BudgetError(Exception):
    """Base error for this synthetic experiment."""


class InvalidInput(BudgetError):
    """A claim is malformed, ambiguous, or outside the synthetic scope."""


class Blocked(BudgetError):
    """A reservation is not permitted by the synthetic accounting state."""


class SnapshotMismatch(BudgetError):
    """The supplied synthetic snapshot does not match the existing store."""


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    attester: str


@dataclass(frozen=True)
class Lane:
    lane_id: str
    target: Target
    role: Role


@dataclass(frozen=True)
class Preflight:
    """The one invented, already-sent, non-inference key-status attempt."""

    item_id: str
    sent_evidence: Evidence
    final_amount: int | None
    billing_evidence: Evidence | None


@dataclass(frozen=True)
class HistoricalCharge:
    item_id: str
    amount: int
    target: Target
    programme: bool
    billing_evidence: Evidence
    request_id: str | None = None
    lane_id: str | None = None
    is_retry: bool = False


@dataclass(frozen=True)
class ExternalLiability:
    item_id: str
    target: Target
    programme: bool
    observation_evidence: Evidence
    upper_bound: int | None
    bound_evidence: Evidence | None
    request_id: str | None = None
    lane_id: str | None = None
    is_retry: bool = False


@dataclass(frozen=True)
class HistoricalSnapshot:
    """One asserted partition and an explicitly selected global retry allowance."""

    snapshot_id: str
    prepared_by: str
    attestation: Evidence
    attests_complete: bool
    attests_disjoint: bool
    global_retry_allowance: int
    preflight: Preflight
    lanes: tuple[Lane, ...]
    settled: tuple[HistoricalCharge, ...] = ()
    liabilities: tuple[ExternalLiability, ...] = ()


@dataclass(frozen=True)
class WorstCase:
    """Independently supplied synthetic bound for ONE physical attempt."""

    amount: int
    evidence: Evidence


@dataclass(frozen=True)
class Costs:
    study: int
    programme: int
    by_target: Mapping[Target, int]

    def for_target(self, target: Target) -> int:
        return self.by_target.get(target, 0)


@dataclass(frozen=True)
class ConflictClaim:
    item_id: str
    amount: int | None  # None means the claim is unquantified, not a zero charge.
    evidence_id: str
    attester: str
    reason: str


@dataclass(frozen=True)
class BudgetStatus:
    # These categories are disjoint.  A bounded unresolved liability is held at
    # its upper bound, not also counted as settled.  Unbounded items are NOT zero.
    initial_settled: Costs
    external_settled: Costs
    external_holds: Costs
    attempt_settled: Costs
    attempt_holds: Costs
    bounded_unknown_items: tuple[str, ...]
    unbounded_unknown_items: tuple[str, ...]
    conflicts: tuple[ConflictClaim, ...]
    returned_attempts: tuple[str, ...]
    attempts_used: int
    retries_used: int

    @property
    def known_subtotal(self) -> Costs:
        """Not an upper bound when any item is unbounded or bills conflict."""
        parts = (
            self.initial_settled,
            self.external_settled,
            self.external_holds,
            self.attempt_settled,
            self.attempt_holds,
        )
        return Costs(
            sum(part.study for part in parts),
            sum(part.programme for part in parts),
            MappingProxyType(
                {
                    target: sum(part.for_target(target) for part in parts)
                    for target in Target
                }
            ),
        )


@dataclass(frozen=True)
class Reservation:
    attempt_id: str
    request_id: str
    lane_id: str
    target: Target
    role: Role
    worst_case: int
    retry_of: str | None


class BillingResult(Enum):
    RECORDED = "recorded"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"
    BOUND_BREACH = "bound-breach"


class ObservationResult(Enum):
    RECORDED = "recorded"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


def _identity(value: object, kind: str) -> str:
    pattern = rf"synthetic:{kind}:[a-z0-9][a-z0-9-]{{0,63}}"
    if type(value) is not str or re.fullmatch(pattern, value) is None:
        raise InvalidInput(f"expected a tagged synthetic {kind} identity")
    return value


def _amount(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_SQLITE_INTEGER:
        raise InvalidInput("amount must be a nonnegative integer microdollar value")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise InvalidInput("expected an explicit boolean")
    return value


def _evidence(value: object) -> Evidence:
    if type(value) is not Evidence:
        raise InvalidInput("expected synthetic evidence")
    _identity(value.evidence_id, "evidence")
    _identity(value.attester, "actor")
    return value


def _target(value: object) -> Target:
    if type(value) is not Target:
        raise InvalidInput("target must be a closed synthetic Target member")
    return value


def _plain(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if type(value) is tuple:
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class _SnapshotIndex:
    lanes: Mapping[str, Lane]
    historical_items: Mapping[str, HistoricalCharge]
    liabilities: Mapping[str, ExternalLiability]
    item_ids: frozenset[str]
    historical_requests: frozenset[str]
    evidence: tuple[tuple[Evidence, str, str], ...]
    attempts: int
    retries: int


def _validate_snapshot(snapshot: HistoricalSnapshot) -> _SnapshotIndex:
    if type(snapshot) is not HistoricalSnapshot:
        raise InvalidInput("expected a synthetic historical snapshot")
    _identity(snapshot.snapshot_id, "snapshot")
    _identity(snapshot.prepared_by, "actor")
    attestation = _evidence(snapshot.attestation)
    if attestation.attester == snapshot.prepared_by:
        raise InvalidInput("snapshot preparer and synthetic attester must differ")
    if snapshot.attests_complete is not True or snapshot.attests_disjoint is not True:
        raise InvalidInput("snapshot must explicitly attest completeness and disjointness")
    allowance = snapshot.global_retry_allowance
    if type(allowance) is not int or not 0 <= allowance <= SYNTHETIC_GLOBAL_RETRY_CEILING:
        raise InvalidInput("explicit synthetic global retry allowance must be 0 through 3")
    if type(snapshot.lanes) is not tuple or not snapshot.lanes:
        raise InvalidInput("lanes must be a nonempty immutable tuple")
    if type(snapshot.settled) is not tuple or type(snapshot.liabilities) is not tuple:
        raise InvalidInput("snapshot charge partitions must be immutable tuples")
    if any(type(item) is not HistoricalCharge for item in snapshot.settled) or any(
        type(item) is not ExternalLiability for item in snapshot.liabilities
    ):
        raise InvalidInput("settled charges and unresolved liabilities cannot overlap partitions")

    lanes: dict[str, Lane] = {}
    for lane in snapshot.lanes:
        if type(lane) is not Lane:
            raise InvalidInput("invalid lane")
        lane_id = _identity(lane.lane_id, "lane")
        target = _target(lane.target)
        if type(lane.role) is not Role:
            raise InvalidInput("lane role must be a closed synthetic Role member")
        if target is Target.OTHER_STUDY or lane_id in lanes:
            raise InvalidInput("ambiguous or invalid lane")
        if target in MODEL_CAPS:
            allowed_roles = {Role.ORIGINAL, Role.JUDGE}
        elif target is Target.ADMIN:
            allowed_roles = {Role.ADMIN}
        else:
            allowed_roles = {Role.JUDGE}
        if lane.role not in allowed_roles:
            raise InvalidInput("target cannot be used in that synthetic lane role")
        lanes[lane_id] = lane

    evidence: list[tuple[Evidence, str, str]] = []
    seen_evidence: set[str] = set()

    def add_evidence(value: Evidence, kind: str, item_id: str) -> None:
        ev = _evidence(value)
        if ev.evidence_id in seen_evidence:
            raise InvalidInput("snapshot reuses evidence across claims")
        seen_evidence.add(ev.evidence_id)
        evidence.append((ev, kind, item_id))

    add_evidence(attestation, "snapshot", snapshot.snapshot_id)
    preflight = snapshot.preflight
    if type(preflight) is not Preflight:
        raise InvalidInput("exactly one synthetic preflight is required")
    _identity(preflight.item_id, "item")
    add_evidence(preflight.sent_evidence, "preflight-sent", preflight.item_id)
    if preflight.final_amount is None:
        if preflight.billing_evidence is not None:
            raise InvalidInput("unknown preflight cost cannot have a final bill")
    else:
        _amount(preflight.final_amount)
        add_evidence(preflight.billing_evidence, "preflight-bill", preflight.item_id)

    item_ids = {preflight.item_id}
    historical: dict[str, HistoricalCharge] = {}
    liabilities: dict[str, ExternalLiability] = {}
    requests: dict[str, list[HistoricalCharge | ExternalLiability]] = {}
    attempts, retries = 1, 0  # The previously sent non-inference preflight.

    for item in (*snapshot.settled, *snapshot.liabilities):
        if type(item) not in (HistoricalCharge, ExternalLiability):
            raise InvalidInput("invalid historical charge partition")
        item_id = _identity(item.item_id, "item")
        if item_id in item_ids:
            raise InvalidInput("ambiguous overlap between historical item IDs")
        item_ids.add(item_id)
        target = _target(item.target)
        programme = _boolean(item.programme)
        is_retry = _boolean(item.is_retry)
        if programme:
            request_id = _identity(item.request_id, "request")
            lane_id = _identity(item.lane_id, "lane")
            if lane_id not in lanes or lanes[lane_id].target is not target:
                raise InvalidInput("historical lane and target disagree")
            requests.setdefault(request_id, []).append(item)
            attempts += 1
            retries += int(is_retry)
        else:
            if item.request_id is not None or item.lane_id is not None or is_retry:
                raise InvalidInput("non-programme history cannot be a programme attempt")
            if target in _PROGRAMME_ONLY:
                raise InvalidInput("judges and administrative lanes count to programme")

        if type(item) is HistoricalCharge:
            _amount(item.amount)
            add_evidence(item.billing_evidence, "historical-bill", item_id)
            historical[item_id] = item
        else:
            add_evidence(item.observation_evidence, "liability-observed", item_id)
            if item.upper_bound is None:
                if item.bound_evidence is not None:
                    raise InvalidInput("unbounded liability cannot have a bound claim")
            else:
                _amount(item.upper_bound)
                add_evidence(item.bound_evidence, "liability-bound", item_id)
                if item.bound_evidence.attester == snapshot.prepared_by:
                    raise InvalidInput("liability bound needs an independent attester")
            liabilities[item_id] = item

    for group in requests.values():
        if sum(not item.is_retry for item in group) != 1:
            raise InvalidInput("historical request needs exactly one initial attempt")
        if len({(item.lane_id, item.target) for item in group}) != 1:
            raise InvalidInput("historical retries cannot change lane or target")

    return _SnapshotIndex(
        MappingProxyType(lanes),
        MappingProxyType(historical),
        MappingProxyType(liabilities),
        frozenset(item_ids),
        frozenset(requests),
        tuple(evidence),
        attempts,
        retries,
    )


_SCHEMA = {
    "synthetic_meta": """CREATE TABLE synthetic_meta (
        key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL
    )""",
    "synthetic_evidence": """CREATE TABLE synthetic_evidence (
        evidence_id TEXT PRIMARY KEY NOT NULL, kind TEXT NOT NULL,
        item_id TEXT NOT NULL, attester TEXT NOT NULL
    )""",
    "synthetic_attempts": """CREATE TABLE synthetic_attempts (
        attempt_id TEXT PRIMARY KEY NOT NULL, request_id TEXT NOT NULL,
        lane_id TEXT NOT NULL, target TEXT NOT NULL, retry_of TEXT UNIQUE,
        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
        bound INTEGER NOT NULL CHECK (bound >= 0),
        bound_evidence TEXT NOT NULL, bound_attester TEXT NOT NULL,
        final_amount INTEGER, billing_evidence TEXT, billing_attester TEXT,
        UNIQUE (request_id, ordinal),
        CHECK ((final_amount IS NULL AND billing_evidence IS NULL AND billing_attester IS NULL)
            OR (final_amount >= 0 AND billing_evidence IS NOT NULL AND billing_attester IS NOT NULL))
    )""",
    "synthetic_nonreturns": """CREATE TABLE synthetic_nonreturns (
        evidence_id TEXT PRIMARY KEY NOT NULL, attempt_id TEXT NOT NULL,
        attester TEXT NOT NULL
    )""",
    "synthetic_returns": """CREATE TABLE synthetic_returns (
        evidence_id TEXT PRIMARY KEY NOT NULL, attempt_id TEXT NOT NULL,
        attester TEXT NOT NULL
    )""",
    "synthetic_external_finals": """CREATE TABLE synthetic_external_finals (
        item_id TEXT PRIMARY KEY NOT NULL, amount INTEGER NOT NULL CHECK (amount >= 0),
        evidence_id TEXT NOT NULL, attester TEXT NOT NULL
    )""",
    "synthetic_conflicts": """CREATE TABLE synthetic_conflicts (
        id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, amount INTEGER CHECK (amount IS NULL OR amount >= 0),
        evidence_id TEXT NOT NULL, attester TEXT NOT NULL, reason TEXT NOT NULL
    )""",
}


def _connection_is_synthetic(connection: sqlite3.Connection) -> None:
    if type(connection) is not sqlite3.Connection:
        raise InvalidInput("a caller-owned SQLite connection is required")
    if connection.in_transaction or connection.isolation_level is not None:
        raise InvalidInput("connection must be idle and use explicit autocommit transactions")
    if connection.row_factory is not None or connection.text_factory is not str:
        raise InvalidInput("synthetic store needs SQLite's default value factories")
    databases = connection.execute("PRAGMA database_list").fetchall()
    if len(databases) != 1 or databases[0][1] != "main":
        raise InvalidInput("temporary or attached databases are unavailable")
    filename = databases[0][2]
    if filename:
        root = os.path.realpath(_SCRATCH_ROOT)
        path = os.path.realpath(filename)
        if (
            os.path.commonpath((root, path)) != root
            or re.fullmatch(r"synthetic-shared-budget-[a-z0-9-]+\.sqlite3", os.path.basename(path))
            is None
        ):
            raise InvalidInput("file databases must be specially named synthetic scratch stores")
        journal = connection.execute("PRAGMA main.journal_mode").fetchone()[0].lower()
        synchronous = connection.execute("PRAGMA main.synchronous").fetchone()[0]
        if journal not in {"delete", "truncate", "persist", "wal"} or synchronous < 2:
            raise InvalidInput("persistent synthetic stores require durable SQLite settings")


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Iterator[None]:
    _connection_is_synthetic(connection)
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


class _CostBuilder:
    def __init__(self) -> None:
        self.study = 0
        self.programme = 0
        self.by_target: dict[Target, int] = {}

    def add(self, amount: int, target: Target, programme: bool) -> None:
        self.study += amount
        if programme:
            self.programme += amount
        self.by_target[target] = self.by_target.get(target, 0) + amount

    def freeze(self) -> Costs:
        return Costs(self.study, self.programme, MappingProxyType(dict(self.by_target)))


class SyntheticBudget:
    """A coordinator for invented identities and one caller-owned SQLite store."""

    def __init__(self, connection: sqlite3.Connection, snapshot: HistoricalSnapshot):
        self._index = _validate_snapshot(snapshot)
        self._connection = connection
        self._snapshot = snapshot
        payload = {
            "scope": "synthetic-only-v2",
            "study_cap": STUDY_CAP,
            "programme_cap": PROGRAMME_CAP,
            "http_attempt_cap": HTTP_ATTEMPT_CAP,
            "synthetic_global_retry_ceiling": SYNTHETIC_GLOBAL_RETRY_CEILING,
            "model_caps": {target.value: cap for target, cap in MODEL_CAPS.items()},
            "snapshot": _plain(snapshot),
        }
        self._snapshot_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.snapshot_hash = sha256(self._snapshot_json.encode("utf-8")).hexdigest()
        with _transaction(connection):
            objects = connection.execute(
                "SELECT name, sql FROM main.sqlite_master WHERE sql IS NOT NULL"
            ).fetchall()
            if not objects:
                for sql in _SCHEMA.values():
                    connection.execute(sql)
                connection.executemany(
                    "INSERT INTO synthetic_meta (key, value) VALUES (?, ?)",
                    (("snapshot", self._snapshot_json), ("sha256", self.snapshot_hash)),
                )
                connection.executemany(
                    "INSERT INTO synthetic_evidence VALUES (?, ?, ?, ?)",
                    (
                        (ev.evidence_id, kind, item_id, ev.attester)
                        for ev, kind, item_id in self._index.evidence
                    ),
                )
            else:
                if dict(objects) != _SCHEMA:
                    raise InvalidInput("store is not the exact synthetic-only schema")
                self._check_snapshot()

    def _check_snapshot(self) -> None:
        objects = dict(self._connection.execute(
            "SELECT name, sql FROM main.sqlite_master WHERE sql IS NOT NULL"
        ))
        if objects != _SCHEMA:
            raise InvalidInput("store is not the exact synthetic-only schema")
        rows = dict(self._connection.execute("SELECT key, value FROM synthetic_meta"))
        if rows != {"snapshot": self._snapshot_json, "sha256": self.snapshot_hash}:
            raise SnapshotMismatch("synthetic snapshot commitment differs")

    def _known_evidence(self, evidence_id: str) -> tuple[str, str, str] | None:
        return self._connection.execute(
            "SELECT kind, item_id, attester FROM synthetic_evidence WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()

    def _add_evidence(self, ev: Evidence, kind: str, item_id: str) -> None:
        self._connection.execute(
            "INSERT INTO synthetic_evidence VALUES (?, ?, ?, ?)",
            (ev.evidence_id, kind, item_id, ev.attester),
        )

    def _conflict(self, item_id: str, amount: int | None, ev: Evidence, reason: str) -> None:
        self._connection.execute(
            "INSERT INTO synthetic_conflicts (item_id, amount, evidence_id, attester, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (item_id, amount, ev.evidence_id, ev.attester, reason),
        )

    def _status(self) -> BudgetStatus:
        initial, external, external_holds = _CostBuilder(), _CostBuilder(), _CostBuilder()
        settled, holds = _CostBuilder(), _CostBuilder()
        bounded: list[str] = []
        unbounded: list[str] = []
        finals = {
            item_id: amount
            for item_id, amount in self._connection.execute(
                "SELECT item_id, amount FROM synthetic_external_finals"
            )
        }
        preflight = self._snapshot.preflight
        if preflight.final_amount is not None:
            initial.add(preflight.final_amount, Target.ADMIN, True)
        elif preflight.item_id in finals:
            external.add(finals[preflight.item_id], Target.ADMIN, True)
        else:
            unbounded.append(preflight.item_id)
        for item in self._snapshot.settled:
            initial.add(item.amount, item.target, item.programme)
        for item in self._snapshot.liabilities:
            if item.item_id in finals:
                external.add(finals[item.item_id], item.target, item.programme)
            elif item.upper_bound is not None:
                external_holds.add(item.upper_bound, item.target, item.programme)
                bounded.append(item.item_id)
            else:
                unbounded.append(item.item_id)

        attempts = self._index.attempts
        retries = self._index.retries
        rows = self._connection.execute(
            "SELECT target, bound, final_amount, retry_of FROM synthetic_attempts"
        )
        for target_value, bound, final_amount, retry_of in rows:
            target = Target(target_value)
            attempts += 1
            retries += int(retry_of is not None)
            if final_amount is None:
                holds.add(bound, target, True)
            else:
                settled.add(final_amount, target, True)
        conflicts = tuple(
            ConflictClaim(*row)
            for row in self._connection.execute(
                "SELECT item_id, amount, evidence_id, attester, reason "
                "FROM synthetic_conflicts ORDER BY id"
            )
        )
        returned = tuple(row[0] for row in self._connection.execute(
            "SELECT DISTINCT attempt_id FROM synthetic_returns ORDER BY attempt_id"
        ))
        return BudgetStatus(
            initial.freeze(), external.freeze(), external_holds.freeze(),
            settled.freeze(), holds.freeze(), tuple(bounded), tuple(unbounded),
            conflicts, returned, attempts, retries,
        )

    def status(self) -> BudgetStatus:
        with _transaction(self._connection):
            self._check_snapshot()
            return self._status()

    def reserve(
        self,
        *,
        attempt_id: str,
        request_id: str,
        lane_id: str,
        worst_case: WorstCase,
        retry_of: str | None = None,
    ) -> Reservation:
        _identity(attempt_id, "item")
        _identity(request_id, "request")
        _identity(lane_id, "lane")
        if retry_of is not None:
            _identity(retry_of, "item")
        if type(worst_case) is not WorstCase:
            raise InvalidInput("an independently supplied per-attempt bound is required")
        amount = _amount(worst_case.amount)
        ev = _evidence(worst_case.evidence)
        if ev.attester == self._snapshot.prepared_by:
            raise InvalidInput("bound attester must differ from snapshot preparer")
        lane = self._index.lanes.get(lane_id)
        if lane is None:
            raise InvalidInput("lane was not part of the attested synthetic snapshot")
        target = lane.target

        with _transaction(self._connection):
            self._check_snapshot()
            state = self._status()
            if state.unbounded_unknown_items:
                raise Blocked("unknown external cost, including an unknown preflight, is unbounded")
            if state.conflicts:
                raise Blocked("conflicting or breached billing assertions require external review")
            usage = state.known_subtotal
            if (
                usage.study > STUDY_CAP
                or usage.programme > PROGRAMME_CAP
                or any(usage.for_target(model) > cap for model, cap in MODEL_CAPS.items())
            ):
                raise Blocked("the existing synthetic state is already above a cap")
            if state.retries_used > self._snapshot.global_retry_allowance:
                raise Blocked("the existing synthetic state exceeds the global retry allowance")
            if state.attempts_used >= HTTP_ATTEMPT_CAP:
                raise Blocked("global HTTP-attempt allowance exhausted")
            if attempt_id in self._index.item_ids or self._connection.execute(
                "SELECT 1 FROM synthetic_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone():
                raise InvalidInput("attempt item already exists or overlaps historical accounting")
            if self._known_evidence(ev.evidence_id) is not None:
                raise InvalidInput("per-attempt bound evidence is already in use")
            if request_id in self._index.historical_requests:
                raise Blocked("historical programme requests cannot be retried by this candidate")

            previous = self._connection.execute(
                "SELECT attempt_id, lane_id, target, ordinal, final_amount, billing_attester "
                "FROM synthetic_attempts WHERE request_id = ? ORDER BY ordinal DESC LIMIT 1",
                (request_id,),
            ).fetchone()
            if retry_of is None:
                if previous is not None:
                    raise InvalidInput("existing logical request requires an evidenced retry")
                ordinal = 0
            else:
                if previous is None or previous[0] != retry_of:
                    raise Blocked("retry must name the latest attempt of this request")
                if previous[1] != lane_id or previous[2] != target.value:
                    raise Blocked("retry cannot change its pinned lane or target")
                if state.retries_used >= self._snapshot.global_retry_allowance:
                    raise Blocked("global retry allowance exhausted")
                if previous[4] is None:
                    raise Blocked("retry needs separately evidenced final billing")
                if self._connection.execute(
                    "SELECT 1 FROM synthetic_returns WHERE attempt_id = ? LIMIT 1", (retry_of,)
                ).fetchone():
                    raise Blocked("a response already returned for this attempt; retry refused")
                witness = self._connection.execute(
                    "SELECT 1 FROM synthetic_nonreturns WHERE attempt_id = ? AND attester != ? LIMIT 1",
                    (retry_of, previous[5]),
                ).fetchone()
                if witness is None:
                    raise Blocked("retry needs separately evidenced non-return from another attester")
                ordinal = previous[3] + 1

            if usage.study + amount > STUDY_CAP:
                raise Blocked("study cap exceeded")
            if usage.programme + amount > PROGRAMME_CAP:
                raise Blocked("new-programme cap exceeded")
            if target in MODEL_CAPS and usage.for_target(target) + amount > MODEL_CAPS[target]:
                raise Blocked("original model cap exceeded")
            self._add_evidence(ev, "attempt-bound", attempt_id)
            self._connection.execute(
                "INSERT INTO synthetic_attempts "
                "(attempt_id, request_id, lane_id, target, retry_of, ordinal, bound, "
                "bound_evidence, bound_attester) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, request_id, lane_id, target.value, retry_of, ordinal,
                 amount, ev.evidence_id, ev.attester),
            )
        return Reservation(attempt_id, request_id, lane_id, target, lane.role, amount, retry_of)

    def _quarantine_malformed_claim(self, item_id: str, *, external: bool, reason: str) -> None:
        """Record a sanitized, unquantified claim before refusing its malformed input."""
        with _transaction(self._connection):
            self._check_snapshot()
            if external:
                known = (item_id == self._snapshot.preflight.item_id
                         or item_id in self._index.historical_items or item_id in self._index.liabilities)
            else:
                known = bool(self._connection.execute(
                    "SELECT 1 FROM synthetic_attempts WHERE attempt_id = ?", (item_id,)
                ).fetchone())
            # Do not stringify or persist the malformed value or its untrusted
            # metadata. None is an unknown amount, never an asserted zero.
            sentinel = Evidence("synthetic:evidence:malformed", "synthetic:actor:unverified")
            self._conflict(item_id, None, sentinel, reason if known else reason + " for an unrecognized item")
        raise InvalidInput("malformed claim quarantined")

    def record_return(self, attempt_id: str, evidence: Evidence) -> ObservationResult:
        """Retain a synthetic returned-response claim; contradiction freezes dispatch."""
        _identity(attempt_id, "item")
        try:
            ev = _evidence(evidence)
        except InvalidInput:
            self._quarantine_malformed_claim(attempt_id, external=False, reason="malformed return evidence")
        with _transaction(self._connection):
            self._check_snapshot()
            if not self._connection.execute(
                "SELECT 1 FROM synthetic_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone():
                self._conflict(attempt_id, None, ev, "returned response for an unrecognized attempt")
                return ObservationResult.CONFLICT
            existing = self._known_evidence(ev.evidence_id)
            if existing == ("return", attempt_id, ev.attester):
                return ObservationResult.UNCHANGED
            if existing is not None:
                self._conflict(attempt_id, None, ev, "return evidence overlaps another claim")
                return ObservationResult.CONFLICT
            self._add_evidence(ev, "return", attempt_id)
            self._connection.execute(
                "INSERT INTO synthetic_returns VALUES (?, ?, ?)",
                (ev.evidence_id, attempt_id, ev.attester),
            )
            if self._connection.execute(
                "SELECT 1 FROM synthetic_nonreturns WHERE attempt_id = ? LIMIT 1", (attempt_id,)
            ).fetchone():
                self._conflict(attempt_id, None, ev, "returned response conflicts with non-return")
                return ObservationResult.CONFLICT
            return ObservationResult.RECORDED

    def record_nonreturn(self, attempt_id: str, evidence: Evidence) -> ObservationResult:
        _identity(attempt_id, "item")
        ev = _evidence(evidence)
        with _transaction(self._connection):
            self._check_snapshot()
            if not self._connection.execute(
                "SELECT 1 FROM synthetic_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone():
                self._conflict(attempt_id, None, ev, "non-return for an unrecognized attempt")
                return ObservationResult.CONFLICT
            existing = self._known_evidence(ev.evidence_id)
            if existing == ("nonreturn", attempt_id, ev.attester):
                return ObservationResult.UNCHANGED
            returned = bool(self._connection.execute(
                "SELECT 1 FROM synthetic_returns WHERE attempt_id = ? LIMIT 1", (attempt_id,)
            ).fetchone())
            if existing is not None:
                if returned:
                    self._conflict(attempt_id, None, ev, "non-return evidence overlaps a returned response")
                    return ObservationResult.CONFLICT
                raise InvalidInput("non-return evidence is already used for another claim")
            self._add_evidence(ev, "nonreturn", attempt_id)
            self._connection.execute(
                "INSERT INTO synthetic_nonreturns VALUES (?, ?, ?)",
                (ev.evidence_id, attempt_id, ev.attester),
            )
            if returned:
                self._conflict(attempt_id, None, ev, "non-return conflicts with a returned response")
                return ObservationResult.CONFLICT
            return ObservationResult.RECORDED

    def record_final_bill(self, attempt_id: str, amount: int, evidence: Evidence) -> BillingResult:
        _identity(attempt_id, "item")
        try:
            amount = _amount(amount)
            ev = _evidence(evidence)
        except InvalidInput:
            self._quarantine_malformed_claim(attempt_id, external=False, reason="malformed attempt bill")
        with _transaction(self._connection):
            self._check_snapshot()
            row = self._connection.execute(
                "SELECT bound, final_amount, billing_evidence, billing_attester "
                "FROM synthetic_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if row is None:
                self._conflict(attempt_id, amount, ev, "bill for an unrecognized attempt")
                return BillingResult.CONFLICT
            bound, old_amount, old_evidence, old_attester = row
            if old_amount is not None:
                if (amount, ev.evidence_id, ev.attester) == (old_amount, old_evidence, old_attester):
                    return BillingResult.UNCHANGED
                self._conflict(attempt_id, amount, ev, "conflicting final attempt bill")
                return BillingResult.CONFLICT
            if self._known_evidence(ev.evidence_id) is not None:
                self._conflict(attempt_id, amount, ev, "billing evidence overlaps another claim")
                return BillingResult.CONFLICT
            self._add_evidence(ev, "attempt-bill", attempt_id)
            self._connection.execute(
                "UPDATE synthetic_attempts SET final_amount = ?, billing_evidence = ?, "
                "billing_attester = ? WHERE attempt_id = ?",
                (amount, ev.evidence_id, ev.attester, attempt_id),
            )
            if amount > bound:
                self._conflict(attempt_id, amount, ev, "final attempt bill exceeded its bound")
                return BillingResult.BOUND_BREACH
            return BillingResult.RECORDED

    def record_external_final(self, item_id: str, amount: int, evidence: Evidence) -> BillingResult:
        """Resolve a synthetic preflight/liability only with a distinct final bill."""
        _identity(item_id, "item")
        preflight = self._snapshot.preflight
        historical = self._index.historical_items.get(item_id)
        liability = self._index.liabilities.get(item_id)
        try:
            amount = _amount(amount)
            ev = _evidence(evidence)
        except InvalidInput:
            self._quarantine_malformed_claim(item_id, external=True, reason="malformed external bill")

        with _transaction(self._connection):
            self._check_snapshot()
            if item_id != preflight.item_id and historical is None and liability is None:
                self._conflict(item_id, amount, ev, "bill for an unrecognized external item")
                return BillingResult.CONFLICT
            if item_id == preflight.item_id and preflight.final_amount is not None:
                old = (preflight.final_amount, preflight.billing_evidence.evidence_id,
                       preflight.billing_evidence.attester)
            elif historical is not None:
                old = (historical.amount, historical.billing_evidence.evidence_id,
                       historical.billing_evidence.attester)
            else:
                old = self._connection.execute(
                    "SELECT amount, evidence_id, attester FROM synthetic_external_finals "
                    "WHERE item_id = ?", (item_id,)
                ).fetchone()
            if old is not None:
                if (amount, ev.evidence_id, ev.attester) == old:
                    return BillingResult.UNCHANGED
                self._conflict(item_id, amount, ev, "conflicting final external bill")
                return BillingResult.CONFLICT
            if self._known_evidence(ev.evidence_id) is not None:
                self._conflict(item_id, amount, ev, "external billing evidence overlaps another claim")
                return BillingResult.CONFLICT
            self._add_evidence(ev, "external-bill", item_id)
            self._connection.execute(
                "INSERT INTO synthetic_external_finals VALUES (?, ?, ?, ?)",
                (item_id, amount, ev.evidence_id, ev.attester),
            )
            if liability is not None and liability.upper_bound is not None and amount > liability.upper_bound:
                self._conflict(item_id, amount, ev, "final external bill exceeded its bound")
                return BillingResult.BOUND_BREACH
            return BillingResult.RECORDED
