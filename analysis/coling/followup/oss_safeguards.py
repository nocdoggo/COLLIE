"""In-memory, synthetic-only budget and output-safety simulation.

This module cannot activate a study. It has no file, credential, cache, process, or
network interface, and accepts only explicitly synthetic records and a scripted mock
transport. Its attestations and hashes describe a synthetic specification, not real
provider guarantees or registered source files.

Python is not a security sandbox. The in-process lock, synthetic receipts and
in-memory records do not provide cross-process coordination, persistent crash
recovery, authenticated billing, or real-provider enforcement.
Missing token counts and completed-run cap histories remain explicitly unknown;
they are never inferred to be zero or compliant.

A real implementation would additionally require a prospective amendment or new
registration with exact source/configuration hashes, independently reviewed before
use, plus authoritative billing and verified provider-side enforcement. A requested
output limit is not a charge ceiling: a separately supplied and independently
verified physical-attempt charge bound must cover all possible overrun, reasoning,
and other charges. A newly capped output is a different decoding condition, never
a silent replacement for an original-default answer. No real execution is
authorized without independent registration, cap, billing, provider and privacy gates.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field, replace
from enum import Enum


# Integer nanodollars avoid floating-point comparisons and rounding at the caps.
NANOS_PER_USD = 1_000_000_000
MODEL_CAP_NANOS = 6 * NANOS_PER_USD
STUDY_CAP_NANOS = 200 * NANOS_PER_USD
OUTER_ATTEMPTS = 8
ECHO_ATTEMPTS = 4
MAX_PHYSICAL_ATTEMPTS = OUTER_ATTEMPTS * ECHO_ATTEMPTS
MAX_SYNTHETIC_HISTORY_BYTES = 65_536
MAX_SYNTHETIC_ROWS = 256
_THREAD_LOCK_TYPE = type(threading.Lock())
# The supplied documentation example is a counterexample, not a universal maximum.
ILLUSTRATIVE_REQUESTED_TOKENS = 300
ILLUSTRATIVE_COMPLETION_TOKENS = 302


class SafetyRefusal(RuntimeError):
    """A simulated action was refused without issuing a synthetic dispatch."""


class OutputConflict(ValueError):
    """Synthetic output identity, provenance, or historical bytes conflict."""


def nanos(text: str) -> int:
    """Parse a nonnegative dollar amount exactly, with at most nine decimals."""
    if type(text) is not str:
        raise ValueError("synthetic amounts must be decimal strings")
    match = re.fullmatch(r"(0|[1-9][0-9]{0,12})(?:\.([0-9]{1,9}))?", text)
    if not match:
        raise ValueError("invalid synthetic dollar amount")
    fraction = (match.group(2) or "").ljust(9, "0")
    return int(match.group(1)) * NANOS_PER_USD + int(fraction)


def _nonnegative(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _synthetic_id(value: str, kind: str) -> None:
    if type(value) is not str or not re.fullmatch(rf"SYNTH-{kind}-[A-Z0-9]{{1,24}}", value):
        raise ValueError(f"expected a synthetic {kind.lower()} identifier")


class DecodingKind(Enum):
    ORIGINAL_DEFAULT = "ORIGINAL"
    CAPPED_FOLLOWUP = "CAPPED"


@dataclass(frozen=True, slots=True)
class SyntheticDecoding:
    kind: DecodingKind
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not DecodingKind:
            raise ValueError("a synthetic decoding kind is required")
        if self.kind is DecodingKind.ORIGINAL_DEFAULT:
            if self.max_output_tokens is not None:
                raise ValueError("original-default decoding has no explicit output limit")
        elif type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise ValueError("a capped follow-up needs a positive synthetic output limit")

    @property
    def cache_identity(self) -> str:
        if self.kind is DecodingKind.ORIGINAL_DEFAULT:
            return "SYNTH-ORIGINAL-DEFAULT"
        return f"SYNTH-CAPPED-{self.max_output_tokens}"

    @property
    def request_features(self) -> tuple[str, ...]:
        """A description, not a request or an HTTP payload."""
        base = ("temperature=0", "reasoning=provider-default")
        if self.kind is DecodingKind.ORIGINAL_DEFAULT:
            return base
        return (*base, f"max_tokens={self.max_output_tokens}")


@dataclass(frozen=True, slots=True)
class SyntheticPhysicalBound:
    """An independent synthetic charge ceiling and its conservative cross-check.

    ``max_output_tokens`` is an independently established bound on *billable*
    output, including any overrun; it is not the requested decoding limit. The
    separately supplied charge ceiling, not the token-price calculation, is
    reserved. The evidence identifier is synthetic and proves nothing about a
    real provider.
    """

    max_input_tokens: int
    max_output_tokens: int
    input_nanos_per_token: int
    output_nanos_per_token: int
    extra_nanos: int = 0
    independent_charge_ceiling_nanos: int | None = None
    bound_evidence_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_input_tokens",
            "max_output_tokens",
            "input_nanos_per_token",
            "output_nanos_per_token",
            "extra_nanos",
        ):
            _nonnegative(getattr(self, name), name)
        if self.independent_charge_ceiling_nanos is None:
            raise ValueError("a separately supplied synthetic charge ceiling is required")
        _nonnegative(self.independent_charge_ceiling_nanos, "independent_charge_ceiling_nanos")
        _synthetic_id(self.bound_evidence_id, "BOUND")
        if self.independent_charge_ceiling_nanos <= 0:
            raise ValueError("the synthetic per-attempt charge ceiling must be positive")
        if self.independent_charge_ceiling_nanos < self.token_price_crosscheck_nanos:
            raise ValueError("the independent ceiling does not cover the synthetic token bound")

    @property
    def token_price_crosscheck_nanos(self) -> int:
        return (
            self.max_input_tokens * self.input_nanos_per_token
            + self.max_output_tokens * self.output_nanos_per_token
            + self.extra_nanos
        )

    @property
    def worst_case_nanos(self) -> int:
        assert self.independent_charge_ceiling_nanos is not None
        return self.independent_charge_ceiling_nanos


@dataclass(frozen=True, slots=True)
class SyntheticSpec:
    """Mock configuration; the known overrun is only a lower bound, never a maximum."""

    decoding: SyntheticDecoding
    physical_bound: SyntheticPhysicalBound
    known_min_overrun_tokens: int = 0

    def __post_init__(self) -> None:
        if type(self.decoding) is not SyntheticDecoding:
            raise ValueError("a synthetic decoding is required")
        if type(self.physical_bound) is not SyntheticPhysicalBound:
            raise ValueError("a synthetic physical-attempt bound is required")
        _nonnegative(self.known_min_overrun_tokens, "known_min_overrun_tokens")
        if self.decoding.kind is DecodingKind.CAPPED_FOLLOWUP:
            requested = self.decoding.max_output_tokens
            assert requested is not None
            if self.known_min_overrun_tokens == 0:
                raise ValueError("a capped request needs an explicit synthetic overrun allowance")
            if (
                requested == ILLUSTRATIVE_REQUESTED_TOKENS
                and self.known_min_overrun_tokens
                < ILLUSTRATIVE_COMPLETION_TOKENS - ILLUSTRATIVE_REQUESTED_TOKENS
            ):
                raise ValueError("the synthetic 300-token request must account for the 302 example")
            if self.physical_bound.max_output_tokens < requested + self.known_min_overrun_tokens:
                raise ValueError("the synthetic billable-output bound excludes known overrun")
        elif self.known_min_overrun_tokens:
            raise ValueError("original-default decoding has no requested output limit to overrun")

    @property
    def fingerprint(self) -> str:
        """Hash the mock specification only; this is not a source-file registration."""
        payload = {
            "about": "synthetic-only-oss-safety-spec-v1",
            "cache_identity": self.decoding.cache_identity,
            "decoding": self.decoding.kind.value,
            "max_output_tokens": self.decoding.max_output_tokens,
            "known_min_overrun_tokens": self.known_min_overrun_tokens,
            "bound": {
                "input_tokens": self.physical_bound.max_input_tokens,
                "output_tokens": self.physical_bound.max_output_tokens,
                "input_nanos_per_token": self.physical_bound.input_nanos_per_token,
                "output_nanos_per_token": self.physical_bound.output_nanos_per_token,
                "extra_nanos": self.physical_bound.extra_nanos,
                "independent_charge_ceiling_nanos": (
                    self.physical_bound.independent_charge_ceiling_nanos
                ),
                "bound_evidence_id": self.physical_bound.bound_evidence_id,
            },
            "model_cap_nanos": MODEL_CAP_NANOS,
            "study_cap_nanos": STUDY_CAP_NANOS,
            "illustrative_overrun_counterexample": [
                ILLUSTRATIVE_REQUESTED_TOKENS,
                ILLUSTRATIVE_COMPLETION_TOKENS,
            ],
            "outer_attempts": OUTER_ATTEMPTS,
            "echo_attempts": ECHO_ATTEMPTS,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SyntheticAssurances:
    """Invented attestations; setting these flags cannot establish real-world safety.

    Token enforcement concerns the independent billable-token bound, not a
    ``max_tokens`` request. The overrun attestation covers *all* possible extra
    charges, not merely the lower-bound example in a synthetic specification.
    """

    quiescent: bool
    billing_reconciled: bool
    pricing_verified: bool
    provider_verified: bool
    token_enforcement_verified: bool
    reasoning_in_bound: bool
    failure_charges_in_bound: bool
    overruns_in_bound: bool
    physical_bound_verified: bool
    independent_bound_verified: bool
    registered_spec_hash: str | None
    independent_review_hash: str | None

    def __post_init__(self) -> None:
        for name in (
            "quiescent",
            "billing_reconciled",
            "pricing_verified",
            "provider_verified",
            "token_enforcement_verified",
            "reasoning_in_bound",
            "failure_charges_in_bound",
            "overruns_in_bound",
            "physical_bound_verified",
            "independent_bound_verified",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a synthetic boolean")
        for name in ("registered_spec_hash", "independent_review_hash"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value)
            ):
                raise ValueError(f"{name} must be a synthetic SHA-256 or None")


class SyntheticModel(Enum):
    OSS = "OSS"
    OTHER = "OTHER"


class LiabilityMaximumKind(Enum):
    UNKNOWN = "unknown"
    SHARED_PHYSICAL = "shared_physical"
    INDEPENDENT = "independent"


@dataclass(frozen=True, slots=True)
class SyntheticRun:
    """A synthetic run; its construction-time spend is an asserted confirmed baseline.

    Prior disputed bookings are not accepted as part of that baseline. This mock
    models disputes only for its own synthetic tickets, not imported histories.
    """

    run_id: str
    model: SyntheticModel
    spent_nanos: int
    cap_nanos: int | None
    complete: bool = False
    completed_cap_nanos: int | None = None

    def __post_init__(self) -> None:
        _synthetic_id(self.run_id, "RUN")
        if type(self.model) is not SyntheticModel:
            raise ValueError("a synthetic model is required")
        _nonnegative(self.spent_nanos, "spent_nanos")
        if type(self.complete) is not bool:
            raise ValueError("complete must be a synthetic boolean")
        if (self.cap_nanos is None) != self.complete:
            raise ValueError("a synthetic run is closed only when explicitly complete")
        if self.completed_cap_nanos is not None:
            _nonnegative(self.completed_cap_nanos, "completed_cap_nanos")
            if not self.complete or self.completed_cap_nanos == 0:
                raise ValueError(
                    "only a completed synthetic run can have a positive historical cap"
                )
        if self.cap_nanos is not None:
            _nonnegative(self.cap_nanos, "cap_nanos")
            if self.cap_nanos == 0:
                raise ValueError("an open synthetic run needs a positive cap")

    @property
    def held_nanos(self) -> int:
        return self.spent_nanos if self.cap_nanos is None else max(self.spent_nanos, self.cap_nanos)


@dataclass(frozen=True, slots=True)
class SyntheticRunCapBreach:
    """Immutable observation of an overspent synthetic run cap."""

    run_id: str
    model: SyntheticModel
    spent_nanos: int
    original_cap_nanos: int
    source_ticket_id: str | None = None


@dataclass(frozen=True, slots=True)
class SyntheticCompletedRunCapHistory:
    """A completed run's cap; None explicitly means its history is unknown."""

    run_id: str
    model: SyntheticModel
    spent_nanos: int
    cap_nanos: int | None


@dataclass(frozen=True, slots=True)
class SyntheticRunCapResolution:
    """Separate synthetic evidence and proposed cap for one prior breach.

    This does not erase or excuse the historical breach. Its evidence is an
    invented attestation, not an authenticated bill or real approval.
    """

    run_id: str
    evidence_id: str
    confirmed_spent_nanos: int
    confirmed_original_cap_nanos: int
    replacement_cap_nanos: int
    final: bool
    cap_reductions: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        _synthetic_id(self.run_id, "RUN")
        _synthetic_id(self.evidence_id, "RESOLUTION")
        for name in (
            "confirmed_spent_nanos",
            "confirmed_original_cap_nanos",
            "replacement_cap_nanos",
        ):
            _nonnegative(getattr(self, name), name)
        if type(self.final) is not bool:
            raise ValueError("final must be a synthetic boolean")
        if type(self.cap_reductions) is not tuple:
            raise ValueError("synthetic cap reductions must be a tuple")
        for change in self.cap_reductions:
            if type(change) is not tuple or len(change) != 2:
                raise ValueError("each synthetic cap reduction must be a pair")
            _synthetic_id(change[0], "RUN")
            _nonnegative(change[1], "cap_nanos")


@dataclass(frozen=True, slots=True)
class SyntheticCapChange:
    run_id: str
    before_nanos: int
    after_nanos: int


@dataclass(frozen=True, slots=True)
class SyntheticResolutionTransaction:
    evidence_id: str
    changes: tuple[SyntheticCapChange, ...]


@dataclass(frozen=True, slots=True)
class SyntheticLiability:
    """Unknown prior charge outside run holds; None means an unbounded charge.

    An optional synthetic spec hash links this liability to the current OSS bound.
    A finite maximum linked only to that hash derives from the shared bound. A
    separately claimed independent maximum requires its own synthetic evidence.
    An evidence label is not real verification. Without a spec link, token usage
    cannot establish the shared bound.
    """

    liability_id: str
    model: SyntheticModel
    maximum_nanos: int | None
    physical_spec_hash: str | None = None
    independent_max_evidence_id: str | None = None

    def __post_init__(self) -> None:
        _synthetic_id(self.liability_id, "LIABILITY")
        if type(self.model) is not SyntheticModel:
            raise ValueError("a synthetic model is required")
        if self.maximum_nanos is not None:
            _nonnegative(self.maximum_nanos, "maximum_nanos")
        if self.independent_max_evidence_id is not None:
            _synthetic_id(self.independent_max_evidence_id, "INDEPENDENT")
            if self.maximum_nanos is None:
                raise ValueError("independent synthetic evidence needs a finite maximum")
        elif self.maximum_nanos is not None and self.physical_spec_hash is None:
            raise ValueError("a finite independent maximum needs separate synthetic evidence")
        if self.physical_spec_hash is not None:
            if (
                self.model is not SyntheticModel.OSS
                or type(self.physical_spec_hash) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", self.physical_spec_hash)
            ):
                raise ValueError("a linked synthetic liability needs an OSS spec SHA-256")

    @property
    def maximum_kind(self) -> LiabilityMaximumKind:
        if self.maximum_nanos is None:
            return LiabilityMaximumKind.UNKNOWN
        if self.independent_max_evidence_id is not None:
            return LiabilityMaximumKind.INDEPENDENT
        return LiabilityMaximumKind.SHARED_PHYSICAL


@dataclass(frozen=True, slots=True)
class SyntheticReceipt:
    """A final invented bill, tied to one synthetic liability or attempt."""

    subject: str
    receipt_id: str
    charge_nanos: int
    final: bool
    reported_input_tokens: int | None = None
    reported_completion_tokens: int | None = None

    def __post_init__(self) -> None:
        if type(self.subject) is not str or not re.fullmatch(
            r"SYNTH-(?:TICKET|LIABILITY)-[A-Z0-9]{1,24}", self.subject
        ):
            raise ValueError("expected a synthetic receipt subject")
        _synthetic_id(self.receipt_id, "RECEIPT")
        _nonnegative(self.charge_nanos, "charge_nanos")
        if type(self.final) is not bool:
            raise ValueError("final must be a synthetic boolean")
        for name in ("reported_input_tokens", "reported_completion_tokens"):
            value = getattr(self, name)
            if value is not None:
                _nonnegative(value, name)


class ReplyKind(Enum):
    ANSWER = "answer"
    EMPTY_ECHO = "empty_echo"
    TRANSIENT = "transient"
    REFUSAL = "refusal"
    FATAL = "fatal"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class SyntheticReply:
    kind: ReplyKind
    charge_nanos: int | None
    reported_completion_tokens: int | None = None
    reported_input_tokens: int | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not ReplyKind:
            raise ValueError("a synthetic reply kind is required")
        if self.charge_nanos is not None:
            _nonnegative(self.charge_nanos, "charge_nanos")
        if self.reported_completion_tokens is not None:
            _nonnegative(self.reported_completion_tokens, "reported_completion_tokens")
        if self.reported_input_tokens is not None:
            _nonnegative(self.reported_input_tokens, "reported_input_tokens")
        if self.kind is ReplyKind.INTERRUPTED and self.charge_nanos is not None:
            raise ValueError("an interrupted attempt has an unknown charge")


class SyntheticTransport:
    """A closed, in-memory sequence of invented replies, not a callable adapter."""

    __slots__ = ("_replies", "_next_index", "_lock")

    def __init__(self, replies: tuple[SyntheticReply, ...]) -> None:
        if type(replies) is not tuple or any(
            type(reply) is not SyntheticReply for reply in replies
        ):
            raise ValueError("the mock transport accepts only a tuple of synthetic replies")
        self._replies = replies
        self._next_index = 0
        self._lock = threading.Lock()

    def _next(self) -> SyntheticReply | None:
        lock = self._lock
        if type(lock) is not _THREAD_LOCK_TYPE:
            raise SafetyRefusal("invalid synthetic transport lock")
        with lock:
            replies = self._replies
            if type(replies) is not tuple or any(
                type(reply) is not SyntheticReply for reply in replies
            ):
                raise SafetyRefusal("invalid synthetic transport reply store")
            if type(self._next_index) is not int or not 0 <= self._next_index <= len(replies):
                raise SafetyRefusal("invalid synthetic transport position")
            if self._next_index == len(replies):
                return None
            reply = replies[self._next_index]
            self._next_index += 1
            return reply

    @property
    def consumed(self) -> int:
        lock = self._lock
        if type(lock) is not _THREAD_LOCK_TYPE:
            raise SafetyRefusal("invalid synthetic transport lock")
        with lock:
            return self._next_index


class OperationState(Enum):
    READY = "ready"
    RESERVED = "reserved"
    WAITING_FOR_BILL = "waiting_for_bill"
    COMPLETE = "complete"
    FAILED = "failed"


class TicketState(Enum):
    RESERVED = "reserved"
    UNKNOWN = "unknown"
    SETTLED = "settled"


class BoundDimension(Enum):
    CHARGE = "charge"
    INPUT_TOKENS = "input_tokens"
    COMPLETION_TOKENS = "completion_tokens"


class BudgetScope(Enum):
    MODEL = "model"
    STUDY = "study"


class BudgetBreachKind(Enum):
    CONFIRMED_SPEND = "confirmed_spend"
    FINITE_HELD = "finite_held"


@dataclass(frozen=True, slots=True)
class SyntheticBudgetBreach:
    """A historical spend or separately observed finite-held cap breach."""

    scope: BudgetScope
    kind: BudgetBreachKind
    observed_nanos: int
    cap_nanos: int
    source: str


@dataclass(frozen=True, slots=True)
class SyntheticContestedBudgetBreach:
    """A historical confirmed-spend observation later affected by a dispute."""

    breach: SyntheticBudgetBreach
    disputed_ticket_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticContestedRunCapBreach:
    """A historical run-cap observation later affected by a dispute."""

    breach: SyntheticRunCapBreach
    disputed_ticket_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticHeldExposureResolution:
    """An audited held-only clearance; prior breach records are not removed."""

    scope: BudgetScope
    source: str
    held_nanos: int
    cap_nanos: int
    cleared_faults: int


@dataclass(frozen=True, slots=True)
class SyntheticPhysicalBoundBreach:
    """An immutable synthetic observation, including its ticket and violated bound."""

    ticket_id: str
    run_id: str
    dimension: BoundDimension
    observed: int
    bound: int

    def __post_init__(self) -> None:
        _synthetic_id(self.ticket_id, "TICKET")
        _synthetic_id(self.run_id, "RUN")
        if type(self.dimension) is not BoundDimension:
            raise ValueError("a synthetic bound dimension is required")
        _nonnegative(self.observed, "observed")
        _nonnegative(self.bound, "bound")


@dataclass(frozen=True, slots=True)
class SyntheticLiabilityBoundBreach:
    liability_id: str
    dimension: BoundDimension
    observed: int
    bound: int


@dataclass(frozen=True, slots=True)
class SyntheticUsageConflict:
    """A new receipt count conflicts with an earlier reply or receipt count."""

    ticket_id: str
    receipt_id: str
    dimension: BoundDimension
    reply_count: int
    receipt_count: int


@dataclass(frozen=True, slots=True)
class SyntheticChargeConflict:
    ticket_id: str
    receipt_id: str
    booked_charge_nanos: int
    conflicting_charge_nanos: int


@dataclass(frozen=True, slots=True)
class SyntheticLiabilityReconciliation:
    liability: SyntheticLiability
    receipt: SyntheticReceipt


@dataclass(frozen=True, slots=True)
class SyntheticOperation:
    operation_id: int
    run_id: str
    state: OperationState = OperationState.READY
    outer_attempt: int = 1
    echo_attempt: int = 1
    physical_attempts: int = 0


@dataclass(frozen=True, slots=True)
class SyntheticTicket:
    ticket_id: str
    operation_id: int
    run_id: str
    outer_attempt: int
    echo_attempt: int
    bound_nanos: int
    state: TicketState = TicketState.RESERVED
    outcome: ReplyKind | None = None
    charge_nanos: int | None = None
    reported_completion_tokens: int | None = None
    reported_input_tokens: int | None = None
    receipt_reported_input_tokens: int | None = None
    receipt_reported_completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class SyntheticSnapshot:
    """Booked spend and conservative exposure; None means no trusted finite bound.

    Indeterminate attempt reservations are not displayed as a finite worst-case
    hold. Historical cap-breach records remain present after a synthetic resolution.
    Booked amounts include disputed charges; confirmed amounts exclude them and
    all unsettled claims. Historical breach observations are retained, with any
    subsequently disputed contributors explicitly qualified as contested.
    """

    model_spent_nanos: int
    model_confirmed_spent_nanos: int
    model_disputed_booked_nanos: int
    model_confirmed_spend_breach: bool
    model_held_nanos: int | None
    study_spent_nanos: int
    study_confirmed_spent_nanos: int
    study_disputed_booked_nanos: int
    study_confirmed_spend_breach: bool
    study_held_nanos: int | None
    attempt_reservations_nanos: int | None
    unknown_count: int
    physical_attempts: int
    faults: tuple[str, ...]
    indeterminate_ticket_ids: tuple[str, ...]
    indeterminate_charge_ticket_ids: tuple[str, ...]
    indeterminate_liability_ids: tuple[str, ...]
    shared_physical_bound_disproved: bool
    shared_physical_bound_untrusted: bool
    disproved_independent_max_evidence_ids: tuple[str, ...]
    physical_bound_breaches: tuple[SyntheticPhysicalBoundBreach, ...]
    liability_bound_breaches: tuple[SyntheticLiabilityBoundBreach, ...]
    budget_breaches: tuple[SyntheticBudgetBreach, ...]
    contested_budget_breaches: tuple[SyntheticContestedBudgetBreach, ...]
    completed_run_cap_history: tuple[SyntheticCompletedRunCapHistory, ...]
    prior_run_cap_breaches: tuple[SyntheticRunCapBreach, ...]
    later_run_cap_breaches: tuple[SyntheticRunCapBreach, ...]
    contested_later_run_cap_breaches: tuple[SyntheticContestedRunCapBreach, ...]
    run_cap_resolutions: tuple[SyntheticRunCapResolution, ...]
    run_cap_resolution_transactions: tuple[SyntheticResolutionTransaction, ...]
    reconciliation_receipts: tuple[SyntheticReceipt, ...]
    liability_reconciliations: tuple[SyntheticLiabilityReconciliation, ...]
    usage_conflicts: tuple[SyntheticUsageConflict, ...]
    charge_conflicts: tuple[SyntheticChargeConflict, ...]
    active_held_breaches: tuple[BudgetScope, ...]
    held_exposure_resolutions: tuple[SyntheticHeldExposureResolution, ...]


class SyntheticSimulation:
    """One locked, in-memory ledger and retry state machine; never a live client.

    An open run's cap includes its recorded spend and any attempt reservations.
    Prior liabilities are specified separately, *outside* the supplied run holds.
    They are not attributed to an individual run. A completed run with no supplied
    historical cap is explicitly unknown, not evidence that its cap was respected.
    Known breaches on completed runs remain blocked; this mock does not reopen them.
    A prior liability's reported usage is checked against the physical bound only
    with an explicit matching synthetic specification link; otherwise it fails closed.
    A disproved shared bound invalidates derived liability maxima, not separately
    evidenced independent maxima. Conflicting final charges remain unresolved.
    Held-only blocks clear with an audit only after relevant liabilities and attempts
    settle and no nonrecoverable fault remains; otherwise the mock stops conservatively.
    A reservation is counted as a possible physical attempt immediately, even if
    interrupted before its mock reply. This deliberately errs toward overcounting.
    """

    def __init__(
        self,
        *,
        spec: SyntheticSpec,
        assurances: SyntheticAssurances,
        runs: tuple[SyntheticRun, ...],
        liabilities: tuple[SyntheticLiability, ...] = (),
    ) -> None:
        if type(spec) is not SyntheticSpec or type(assurances) is not SyntheticAssurances:
            raise ValueError("only a synthetic specification and assurances are accepted")
        if type(runs) is not tuple or any(type(run) is not SyntheticRun for run in runs):
            raise ValueError("runs must be a tuple of synthetic runs")
        if type(liabilities) is not tuple or any(
            type(liability) is not SyntheticLiability for liability in liabilities
        ):
            raise ValueError("liabilities must be a tuple of synthetic liabilities")
        if len({run.run_id for run in runs}) != len(runs):
            raise ValueError("duplicate synthetic run")
        if len({liability.liability_id for liability in liabilities}) != len(liabilities):
            raise ValueError("duplicate synthetic liability")
        if any(
            liability.physical_spec_hash is not None
            and liability.physical_spec_hash != spec.fingerprint
            for liability in liabilities
        ):
            raise ValueError("a synthetic liability names a different physical specification")
        if any(
            liability.maximum_kind is LiabilityMaximumKind.SHARED_PHYSICAL
            and liability.maximum_nanos is not None
            and liability.maximum_nanos < spec.physical_bound.worst_case_nanos
            for liability in liabilities
        ):
            raise ValueError("a shared synthetic maximum must cover the physical bound")
        self._spec = spec
        self._assurances = assurances
        self._runs = {run.run_id: run for run in runs}
        self._liabilities = {liability.liability_id: liability for liability in liabilities}
        self._settled_external_oss = 0
        self._settled_external_other = 0
        self._operations: dict[int, SyntheticOperation] = {}
        self._tickets: dict[str, SyntheticTicket] = {}
        self._receipt_ids: set[str] = set()
        self._reconciliation_receipts: tuple[SyntheticReceipt, ...] = ()
        self._liability_reconciliations: tuple[SyntheticLiabilityReconciliation, ...] = ()
        self._usage_conflicts: tuple[SyntheticUsageConflict, ...] = ()
        self._charge_conflicts: tuple[SyntheticChargeConflict, ...] = ()
        self._indeterminate_tickets: set[str] = set()
        self._indeterminate_charge_tickets: set[str] = set()
        self._shared_physical_bound_disproved = False
        self._shared_physical_bound_untrusted = False
        self._disproved_independent_max_evidence_ids: set[str] = set()
        self._physical_bound_breaches: tuple[SyntheticPhysicalBoundBreach, ...] = ()
        self._liability_bound_breaches: tuple[SyntheticLiabilityBoundBreach, ...] = ()
        self._budget_breaches: tuple[SyntheticBudgetBreach, ...] = ()
        self._budget_breach_ticket_ids: tuple[tuple[str, ...], ...] = ()
        self._last_budget_observations: dict[tuple[BudgetScope, BudgetBreachKind], int | None] = {}
        self._active_held_breaches: set[BudgetScope] = set()
        self._held_exposure_resolutions: tuple[SyntheticHeldExposureResolution, ...] = ()
        completed_history: list[SyntheticCompletedRunCapHistory] = []
        prior_breaches: list[SyntheticRunCapBreach] = []
        for run in runs:
            prior_cap = run.completed_cap_nanos if run.complete else run.cap_nanos
            if run.complete:
                completed_history.append(
                    SyntheticCompletedRunCapHistory(
                        run.run_id, run.model, run.spent_nanos, prior_cap
                    )
                )
            if prior_cap is not None and run.spent_nanos > prior_cap:
                prior_breaches.append(
                    SyntheticRunCapBreach(run.run_id, run.model, run.spent_nanos, prior_cap)
                )
        self._completed_run_cap_history = tuple(completed_history)
        self._prior_run_cap_breaches = tuple(prior_breaches)
        self._later_run_cap_breaches: tuple[SyntheticRunCapBreach, ...] = ()
        self._later_run_cap_breach_ticket_ids: tuple[tuple[str, ...], ...] = ()
        self._run_cap_resolutions: tuple[SyntheticRunCapResolution, ...] = ()
        self._run_cap_resolution_transactions: tuple[SyntheticResolutionTransaction, ...] = ()
        self._resolution_ids: set[str] = set()
        self._faults: list[str] = []
        self._lock = threading.RLock()
        with self._lock:
            self._record_budget_breaches_locked(
                "SYNTH-INITIAL", fault_on_new=False, fault_on_confirmed=True
            )

    def set_assurances(self, assurances: SyntheticAssurances) -> None:
        if type(assurances) is not SyntheticAssurances:
            raise ValueError("only synthetic assurances are accepted")
        with self._lock:
            self._assurances = assurances

    def _liability_indeterminate_locked(self, liability: SyntheticLiability) -> bool:
        if liability.maximum_kind is LiabilityMaximumKind.UNKNOWN:
            return True
        if liability.maximum_kind is LiabilityMaximumKind.SHARED_PHYSICAL:
            return self._shared_physical_bound_disproved or self._shared_physical_bound_untrusted
        return liability.independent_max_evidence_id in self._disproved_independent_max_evidence_ids

    def _disputed_booked_by_run_locked(self) -> dict[str, int]:
        disputed: dict[str, int] = {}
        for ticket_id in self._indeterminate_charge_tickets:
            ticket = self._tickets[ticket_id]
            if ticket.state is not TicketState.SETTLED or ticket.charge_nanos is None:
                raise RuntimeError("a disputed synthetic ticket must have one booked charge")
            disputed[ticket.run_id] = disputed.get(ticket.run_id, 0) + ticket.charge_nanos
        return disputed

    def _confirmed_ticket_ids_locked(
        self, *, scope: BudgetScope | None = None, run_id: str | None = None
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                ticket.ticket_id
                for ticket in self._tickets.values()
                if ticket.state is TicketState.SETTLED
                and ticket.charge_nanos is not None
                and ticket.charge_nanos > 0
                and ticket.ticket_id not in self._indeterminate_charge_tickets
                and (run_id is None or ticket.run_id == run_id)
                and (
                    scope is not BudgetScope.MODEL
                    or self._runs[ticket.run_id].model is SyntheticModel.OSS
                )
            )
        )

    def _snapshot_locked(self) -> SyntheticSnapshot:
        outstanding = [
            ticket for ticket in self._tickets.values() if ticket.state is not TicketState.SETTLED
        ]
        indeterminate = tuple(
            sorted(
                ticket.ticket_id
                for ticket in outstanding
                if ticket.ticket_id in self._indeterminate_tickets
            )
        )
        disputed_charges = tuple(sorted(self._indeterminate_charge_tickets))
        indeterminate_liabilities = tuple(
            sorted(
                liability.liability_id
                for liability in self._liabilities.values()
                if self._liability_indeterminate_locked(liability)
            )
        )
        outstanding_by_run: dict[str, int] = {}
        for ticket in outstanding:
            outstanding_by_run[ticket.run_id] = (
                outstanding_by_run.get(ticket.run_id, 0) + ticket.bound_nanos
            )

        def held(run: SyntheticRun) -> int:
            # An open cap normally contains all still-trustworthy reservations.
            return max(run.held_nanos, run.spent_nanos + outstanding_by_run.get(run.run_id, 0))

        model_runs = [run for run in self._runs.values() if run.model is SyntheticModel.OSS]
        model_spent = sum(run.spent_nanos for run in model_runs) + self._settled_external_oss
        study_spent = (
            sum(run.spent_nanos for run in self._runs.values())
            + self._settled_external_oss
            + self._settled_external_other
        )
        disputed_by_run = self._disputed_booked_by_run_locked()
        model_disputed = sum(disputed_by_run.get(run.run_id, 0) for run in model_runs)
        study_disputed = sum(disputed_by_run.values())
        model_confirmed = model_spent - model_disputed
        study_confirmed = study_spent - study_disputed
        if model_confirmed < 0 or study_confirmed < 0:
            raise RuntimeError("disputed synthetic charges exceed booked spend")
        contested_budget = tuple(
            SyntheticContestedBudgetBreach(breach, affected)
            for breach, contributors in zip(
                self._budget_breaches, self._budget_breach_ticket_ids, strict=True
            )
            if (
                affected := tuple(
                    ticket_id
                    for ticket_id in contributors
                    if ticket_id in self._indeterminate_charge_tickets
                )
            )
        )
        contested_run_caps = tuple(
            SyntheticContestedRunCapBreach(breach, affected)
            for breach, contributors in zip(
                self._later_run_cap_breaches,
                self._later_run_cap_breach_ticket_ids,
                strict=True,
            )
            if (
                affected := tuple(
                    ticket_id
                    for ticket_id in contributors
                    if ticket_id in self._indeterminate_charge_tickets
                )
            )
        )
        model_unknown = [
            liability
            for liability in self._liabilities.values()
            if liability.model is SyntheticModel.OSS
        ]
        model_held = (
            None
            if indeterminate
            or disputed_charges
            or any(self._liability_indeterminate_locked(liability) for liability in model_unknown)
            else sum(held(run) for run in model_runs)
            + self._settled_external_oss
            + sum(
                liability.maximum_nanos
                for liability in model_unknown
                if liability.maximum_nanos is not None
            )
        )
        study_held = (
            None
            if indeterminate
            or disputed_charges
            or indeterminate_liabilities
            else sum(held(run) for run in self._runs.values())
            + self._settled_external_oss
            + self._settled_external_other
            + sum(
                liability.maximum_nanos
                for liability in self._liabilities.values()
                if liability.maximum_nanos is not None
            )
        )
        return SyntheticSnapshot(
            model_spent_nanos=model_spent,
            model_confirmed_spent_nanos=model_confirmed,
            model_disputed_booked_nanos=model_disputed,
            model_confirmed_spend_breach=model_confirmed > MODEL_CAP_NANOS,
            model_held_nanos=model_held,
            study_spent_nanos=study_spent,
            study_confirmed_spent_nanos=study_confirmed,
            study_disputed_booked_nanos=study_disputed,
            study_confirmed_spend_breach=study_confirmed > STUDY_CAP_NANOS,
            study_held_nanos=study_held,
            attempt_reservations_nanos=(
                None
                if indeterminate or disputed_charges
                else sum(ticket.bound_nanos for ticket in outstanding)
            ),
            unknown_count=len(self._liabilities)
            + sum(
                ticket.state is TicketState.UNKNOWN
                or ticket.ticket_id in self._indeterminate_tickets
                for ticket in outstanding
            ) + len(disputed_charges),
            physical_attempts=len(self._tickets),
            faults=tuple(self._faults),
            indeterminate_ticket_ids=indeterminate,
            indeterminate_charge_ticket_ids=disputed_charges,
            indeterminate_liability_ids=indeterminate_liabilities,
            shared_physical_bound_disproved=self._shared_physical_bound_disproved,
            shared_physical_bound_untrusted=(
                self._shared_physical_bound_disproved or self._shared_physical_bound_untrusted
            ),
            disproved_independent_max_evidence_ids=tuple(
                sorted(self._disproved_independent_max_evidence_ids)
            ),
            physical_bound_breaches=self._physical_bound_breaches,
            liability_bound_breaches=self._liability_bound_breaches,
            budget_breaches=self._budget_breaches,
            contested_budget_breaches=contested_budget,
            completed_run_cap_history=self._completed_run_cap_history,
            prior_run_cap_breaches=self._prior_run_cap_breaches,
            later_run_cap_breaches=self._later_run_cap_breaches,
            contested_later_run_cap_breaches=contested_run_caps,
            run_cap_resolutions=self._run_cap_resolutions,
            run_cap_resolution_transactions=self._run_cap_resolution_transactions,
            reconciliation_receipts=self._reconciliation_receipts,
            liability_reconciliations=self._liability_reconciliations,
            usage_conflicts=self._usage_conflicts,
            charge_conflicts=self._charge_conflicts,
            active_held_breaches=tuple(
                scope for scope in BudgetScope if scope in self._active_held_breaches
            ),
            held_exposure_resolutions=self._held_exposure_resolutions,
        )

    def _record_budget_breaches_locked(
        self, source: str, *, fault_on_new: bool, fault_on_confirmed: bool = False
    ) -> None:
        """Record known spending separately from any determinable held exposure."""
        state = self._snapshot_locked()
        observations = (
            (BudgetScope.MODEL, BudgetBreachKind.CONFIRMED_SPEND, state.model_confirmed_spent_nanos,
             MODEL_CAP_NANOS),
            (BudgetScope.MODEL, BudgetBreachKind.FINITE_HELD, state.model_held_nanos,
             MODEL_CAP_NANOS),
            (BudgetScope.STUDY, BudgetBreachKind.CONFIRMED_SPEND, state.study_confirmed_spent_nanos,
             STUDY_CAP_NANOS),
            (BudgetScope.STUDY, BudgetBreachKind.FINITE_HELD, state.study_held_nanos,
             STUDY_CAP_NANOS),
        )
        for scope, kind, amount, cap in observations:
            key = (scope, kind)
            current = amount if amount is not None and amount > cap else None
            if kind is BudgetBreachKind.FINITE_HELD and current is not None:
                self._active_held_breaches.add(scope)
            if current is not None and self._last_budget_observations.get(key) != current:
                breach = SyntheticBudgetBreach(scope, kind, current, cap, source)
                self._budget_breaches = (*self._budget_breaches, breach)
                contributors = (
                    self._confirmed_ticket_ids_locked(scope=scope)
                    if kind is BudgetBreachKind.CONFIRMED_SPEND
                    else ()
                )
                self._budget_breach_ticket_ids = (*self._budget_breach_ticket_ids, contributors)
                if fault_on_new or (
                    fault_on_confirmed and kind is BudgetBreachKind.CONFIRMED_SPEND
                ):
                    self._faults.append(f"synthetic {scope.value} {kind.value} exceeded its cap")
            self._last_budget_observations[key] = current

    def snapshot(self) -> SyntheticSnapshot:
        with self._lock:
            return self._snapshot_locked()

    def operation(self, operation_id: int) -> SyntheticOperation:
        with self._lock:
            if type(operation_id) is not int or operation_id not in self._operations:
                raise SafetyRefusal("unknown synthetic operation")
            return self._operations[operation_id]

    def run(self, run_id: str) -> SyntheticRun:
        _synthetic_id(run_id, "RUN")
        with self._lock:
            if run_id not in self._runs:
                raise SafetyRefusal("unknown synthetic run")
            return self._runs[run_id]

    def ticket(self, ticket_id: str) -> SyntheticTicket:
        with self._lock:
            return self._ticket_locked(ticket_id)

    def _unresolved_prior_breaches_locked(self) -> tuple[SyntheticRunCapBreach, ...]:
        resolved = {record.run_id for record in self._run_cap_resolutions}
        return tuple(
            breach for breach in self._prior_run_cap_breaches if breach.run_id not in resolved
        )

    def _nonrecoverable_cap_adjustment_faults_locked(self) -> tuple[str, ...]:
        recoverable = {
            f"synthetic {scope.value} {BudgetBreachKind.FINITE_HELD.value} exceeded its cap"
            for scope in BudgetScope
        }
        return tuple(fault for fault in self._faults if fault not in recoverable)

    def _clear_resolved_held_exposure_locked(self, source: str) -> None:
        """Clear only resolved held-only blocks, preserving their immutable history."""
        if self._nonrecoverable_cap_adjustment_faults_locked():
            return
        if self._indeterminate_charge_tickets or any(
            ticket.state is not TicketState.SETTLED for ticket in self._tickets.values()
        ):
            return
        state = self._snapshot_locked()
        for scope, held, cap in (
            (BudgetScope.MODEL, state.model_held_nanos, MODEL_CAP_NANOS),
            (BudgetScope.STUDY, state.study_held_nanos, STUDY_CAP_NANOS),
        ):
            relevant = (
                any(
                    liability.model is SyntheticModel.OSS
                    for liability in self._liabilities.values()
                )
                if scope is BudgetScope.MODEL
                else bool(self._liabilities)
            )
            if relevant or held is None or held > cap:
                continue
            marker = (
                f"synthetic {scope.value} {BudgetBreachKind.FINITE_HELD.value} exceeded its cap"
            )
            cleared = self._faults.count(marker)
            if scope not in self._active_held_breaches and not cleared:
                continue
            self._faults = [fault for fault in self._faults if fault != marker]
            self._active_held_breaches.discard(scope)
            resolution = SyntheticHeldExposureResolution(scope, source, held, cap, cleared)
            self._held_exposure_resolutions = (*self._held_exposure_resolutions, resolution)

    def _check_assurances_locked(self) -> None:
        for name in (
            "quiescent",
            "billing_reconciled",
            "pricing_verified",
            "provider_verified",
            "token_enforcement_verified",
            "reasoning_in_bound",
            "failure_charges_in_bound",
            "overruns_in_bound",
            "physical_bound_verified",
            "independent_bound_verified",
        ):
            if getattr(self._assurances, name) is not True:
                raise SafetyRefusal(f"synthetic assurance not established: {name}")
        if self._assurances.registered_spec_hash != self._spec.fingerprint:
            raise SafetyRefusal("synthetic registration hash does not match the specification")
        if self._assurances.independent_review_hash != self._spec.fingerprint:
            raise SafetyRefusal("synthetic independent review does not match the specification")

    def _check_ready_locked(self) -> None:
        self._check_assurances_locked()
        state = self._snapshot_locked()
        if state.faults:
            raise SafetyRefusal("the synthetic simulation is faulted")
        if self._unresolved_prior_breaches_locked():
            raise SafetyRefusal("a prior synthetic run-cap breach requires separate resolution")
        if state.model_confirmed_spent_nanos > MODEL_CAP_NANOS:
            raise SafetyRefusal("synthetic model cap exceeded by confirmed spend")
        if state.study_confirmed_spent_nanos > STUDY_CAP_NANOS:
            raise SafetyRefusal("synthetic study cap exceeded by confirmed spend")
        if state.unknown_count:
            raise SafetyRefusal("unknown synthetic charges require final reconciliation")
        if state.model_held_nanos is None or state.model_held_nanos > MODEL_CAP_NANOS:
            raise SafetyRefusal("synthetic model cap would be exceeded")
        if state.study_held_nanos is None or state.study_held_nanos > STUDY_CAP_NANOS:
            raise SafetyRefusal("synthetic study cap would be exceeded")
        disputed_by_run = self._disputed_booked_by_run_locked()
        if any(
            run.cap_nanos is not None
            and run.spent_nanos - disputed_by_run.get(run.run_id, 0) > run.cap_nanos
            for run in self._runs.values()
        ):
            raise SafetyRefusal("a synthetic run has already exceeded its cap")
        if self._active_held_breaches:
            raise SafetyRefusal("synthetic held exposure requires an audited resolution")

    def reallocate_caps(self, changes: tuple[tuple[str, int], ...]) -> None:
        """Atomically change idle OSS run caps; never close a run or change $6."""
        if type(changes) is not tuple or not changes:
            raise ValueError("changes must be a nonempty tuple of synthetic cap changes")
        with self._lock:
            self._check_assurances_locked()
            if self._unresolved_prior_breaches_locked():
                raise SafetyRefusal("a prior synthetic run-cap breach requires separate resolution")
            if (
                self._nonrecoverable_cap_adjustment_faults_locked()
                or self._snapshot_locked().unknown_count
            ):
                raise SafetyRefusal("faults or unknown synthetic charges block reallocation")
            if any(ticket.state is not TicketState.SETTLED for ticket in self._tickets.values()):
                raise SafetyRefusal("a synthetic attempt is still reserved")
            updated = dict(self._runs)
            seen: set[str] = set()
            for change in changes:
                if type(change) is not tuple or len(change) != 2:
                    raise ValueError("each synthetic cap change is a pair")
                run_id, cap = change
                _synthetic_id(run_id, "RUN")
                _nonnegative(cap, "cap_nanos")
                if run_id in seen:
                    raise ValueError("duplicate synthetic cap change")
                seen.add(run_id)
                run = updated.get(run_id)
                if run is None or run.model is not SyntheticModel.OSS or run.cap_nanos is None:
                    raise SafetyRefusal("only an open synthetic OSS run can be reallocated")
                if cap == 0 or cap < run.spent_nanos:
                    raise SafetyRefusal("a run cap must be positive and cover recorded spend")
                updated[run_id] = replace(run, cap_nanos=cap)
            model_held = sum(
                run.held_nanos for run in updated.values() if run.model is SyntheticModel.OSS
            )
            study_held = sum(run.held_nanos for run in updated.values())
            model_held += self._settled_external_oss
            study_held += self._settled_external_oss + self._settled_external_other
            if model_held > MODEL_CAP_NANOS or study_held > STUDY_CAP_NANOS:
                raise SafetyRefusal("synthetic reallocation would exceed a shared cap")
            self._runs = updated
            self._record_budget_breaches_locked("SYNTH-REALLOCATION", fault_on_new=True)
            self._clear_resolved_held_exposure_locked("SYNTH-REALLOCATION")

    def resolve_prior_run_cap_breach(self, resolution: SyntheticRunCapResolution) -> None:
        """Resolve one open OSS breach and reduce idle caps in one mock transaction.

        Completed-run and other-model prior breaches remain blocked. Multiple
        breaches requiring simultaneous resolution also remain fail-closed.
        """
        if type(resolution) is not SyntheticRunCapResolution:
            raise ValueError("only a synthetic run-cap resolution is accepted")
        with self._lock:
            self._check_assurances_locked()
            if self._nonrecoverable_cap_adjustment_faults_locked():
                raise SafetyRefusal("other synthetic faults block run-cap resolution")
            if self._liabilities or any(
                ticket.state is not TicketState.SETTLED for ticket in self._tickets.values()
            ):
                raise SafetyRefusal("synthetic liabilities or attempts remain unresolved")
            if not resolution.final:
                raise SafetyRefusal("synthetic run-cap evidence must be final")
            if resolution.evidence_id in self._resolution_ids:
                raise SafetyRefusal("synthetic run-cap evidence was already used")
            prior = next(
                (
                    breach
                    for breach in self._unresolved_prior_breaches_locked()
                    if breach.run_id == resolution.run_id
                ),
                None,
            )
            if prior is None:
                raise SafetyRefusal("no unresolved prior synthetic run-cap breach")
            run = self._runs[resolution.run_id]
            if prior.model is not SyntheticModel.OSS or run.cap_nanos is None:
                raise SafetyRefusal("this mock resolves only open synthetic OSS run caps")
            if (
                resolution.confirmed_spent_nanos != prior.spent_nanos
                or resolution.confirmed_original_cap_nanos != prior.original_cap_nanos
                or run.spent_nanos != prior.spent_nanos
                or run.cap_nanos != prior.original_cap_nanos
            ):
                raise SafetyRefusal("synthetic run-cap evidence does not match the breach")
            if resolution.replacement_cap_nanos < run.spent_nanos:
                raise SafetyRefusal("a synthetic replacement cap must cover recorded spend")
            updated = dict(self._runs)
            updated[run.run_id] = replace(run, cap_nanos=resolution.replacement_cap_nanos)
            changes = [
                SyntheticCapChange(run.run_id, run.cap_nanos, resolution.replacement_cap_nanos)
            ]
            seen = {run.run_id}
            for run_id, cap in resolution.cap_reductions:
                if run_id in seen:
                    raise SafetyRefusal("duplicate or target run in synthetic cap reductions")
                seen.add(run_id)
                donor = updated.get(run_id)
                if donor is None or donor.cap_nanos is None:
                    raise SafetyRefusal("a cap reduction needs another open synthetic run")
                if cap == 0 or cap < donor.spent_nanos or cap >= donor.cap_nanos:
                    raise SafetyRefusal("synthetic donor caps may only be reduced above spend")
                updated[run_id] = replace(donor, cap_nanos=cap)
                changes.append(SyntheticCapChange(run_id, donor.cap_nanos, cap))
            model_held = (
                sum(run.held_nanos for run in updated.values() if run.model is SyntheticModel.OSS)
                + self._settled_external_oss
            )
            study_held = (
                sum(run.held_nanos for run in updated.values())
                + self._settled_external_oss
                + self._settled_external_other
            )
            if model_held > MODEL_CAP_NANOS or study_held > STUDY_CAP_NANOS:
                raise SafetyRefusal("synthetic run-cap resolution would exceed a shared cap")
            transaction = SyntheticResolutionTransaction(resolution.evidence_id, tuple(changes))
            resolutions = (*self._run_cap_resolutions, resolution)
            transactions = (
                *self._run_cap_resolution_transactions,
                transaction,
            )
            resolution_ids = self._resolution_ids | {resolution.evidence_id}
            self._runs = updated
            self._run_cap_resolutions = resolutions
            self._run_cap_resolution_transactions = transactions
            self._resolution_ids = resolution_ids
            self._record_budget_breaches_locked(resolution.evidence_id, fault_on_new=True)
            self._clear_resolved_held_exposure_locked(resolution.evidence_id)

    def begin(self, run_id: str) -> SyntheticOperation:
        _synthetic_id(run_id, "RUN")
        with self._lock:
            self._check_ready_locked()
            run = self._runs.get(run_id)
            if run is None or run.model is not SyntheticModel.OSS or run.cap_nanos is None:
                raise SafetyRefusal("an open synthetic OSS run is required")
            operation = SyntheticOperation(operation_id=len(self._operations) + 1, run_id=run_id)
            self._operations[operation.operation_id] = operation
            return operation

    def reserve_next(self, operation_id: int) -> SyntheticTicket:
        with self._lock:
            self._check_ready_locked()
            operation = self.operation(operation_id)
            if operation.state is not OperationState.READY:
                raise SafetyRefusal("the synthetic operation is not ready")
            if operation.physical_attempts >= MAX_PHYSICAL_ATTEMPTS:
                raise SafetyRefusal("the synthetic retry limit is exhausted")
            run = self._runs[operation.run_id]
            if run.cap_nanos is None:
                raise SafetyRefusal("the synthetic run is closed")
            outstanding = sum(
                ticket.bound_nanos
                for ticket in self._tickets.values()
                if ticket.run_id == run.run_id and ticket.state is not TicketState.SETTLED
            )
            bound = self._spec.physical_bound.worst_case_nanos
            if run.spent_nanos + outstanding + bound > run.cap_nanos:
                raise SafetyRefusal("the synthetic run cannot reserve the physical-attempt bound")
            ticket_id = f"SYNTH-TICKET-{len(self._tickets) + 1}"
            ticket = SyntheticTicket(
                ticket_id=ticket_id,
                operation_id=operation_id,
                run_id=run.run_id,
                outer_attempt=operation.outer_attempt,
                echo_attempt=operation.echo_attempt,
                bound_nanos=bound,
            )
            self._tickets[ticket_id] = ticket
            self._operations[operation_id] = replace(
                operation,
                state=OperationState.RESERVED,
                physical_attempts=operation.physical_attempts + 1,
            )
            return ticket

    def _ticket_locked(self, ticket_id: str) -> SyntheticTicket:
        _synthetic_id(ticket_id, "TICKET")
        if ticket_id not in self._tickets:
            raise SafetyRefusal("unknown synthetic ticket")
        return self._tickets[ticket_id]

    def _mark_unknown_locked(self, ticket: SyntheticTicket, outcome: ReplyKind) -> None:
        self._tickets[ticket.ticket_id] = replace(
            ticket, state=TicketState.UNKNOWN, outcome=outcome
        )
        operation = self._operations[ticket.operation_id]
        self._operations[ticket.operation_id] = replace(
            operation, state=OperationState.WAITING_FOR_BILL
        )

    def _mark_unsettled_indeterminate_locked(self) -> None:
        self._indeterminate_tickets.update(
            ticket.ticket_id
            for ticket in self._tickets.values()
            if ticket.state is not TicketState.SETTLED
        )

    def _bound_fault_text(self, dimension: BoundDimension) -> str:
        reason = {
            BoundDimension.CHARGE: (
                "a synthetic physical-attempt charge exceeded its verified bound"
            ),
            BoundDimension.INPUT_TOKENS: "synthetic input exceeded its independent token bound",
            BoundDimension.COMPLETION_TOKENS: (
                "synthetic billable output exceeded its independent token bound"
            ),
        }[dimension]
        return reason

    def _invalidate_physical_bound_locked(
        self, ticket: SyntheticTicket, dimension: BoundDimension, observed: int, bound: int
    ) -> None:
        """The common bound is not reliable for any unsettled synthetic ticket."""
        self._shared_physical_bound_disproved = True
        breach = SyntheticPhysicalBoundBreach(
            ticket.ticket_id, ticket.run_id, dimension, observed, bound
        )
        if breach not in self._physical_bound_breaches:
            self._physical_bound_breaches = (*self._physical_bound_breaches, breach)
            self._faults.append(self._bound_fault_text(dimension))
        self._mark_unsettled_indeterminate_locked()

    def _observe_ticket_usage_locked(
        self, ticket: SyntheticTicket, input_tokens: int | None, completion_tokens: int | None
    ) -> None:
        bound = self._spec.physical_bound
        if input_tokens is not None and input_tokens > bound.max_input_tokens:
            self._invalidate_physical_bound_locked(
                ticket, BoundDimension.INPUT_TOKENS, input_tokens, bound.max_input_tokens
            )
        if completion_tokens is not None and completion_tokens > bound.max_output_tokens:
            self._invalidate_physical_bound_locked(
                ticket, BoundDimension.COMPLETION_TOKENS, completion_tokens, bound.max_output_tokens
            )

    def _record_usage_conflicts_locked(
        self, ticket: SyntheticTicket, receipt: SyntheticReceipt
    ) -> None:
        pairs = (
            (
                BoundDimension.INPUT_TOKENS,
                ticket.reported_input_tokens,
                receipt.reported_input_tokens,
                "reported_input_tokens",
            ),
            (
                BoundDimension.COMPLETION_TOKENS,
                ticket.reported_completion_tokens,
                receipt.reported_completion_tokens,
                "reported_completion_tokens",
            ),
        )
        for dimension, reply_count, receipt_count, field_name in pairs:
            if receipt_count is None:
                continue
            previous = [reply_count]
            previous.extend(
                getattr(prior, field_name)
                for prior in self._reconciliation_receipts
                if prior.subject == ticket.ticket_id
            )
            for earlier in sorted({value for value in previous if value is not None}):
                if earlier == receipt_count:
                    continue
                conflict = SyntheticUsageConflict(
                    ticket.ticket_id, receipt.receipt_id, dimension, earlier, receipt_count
                )
                self._usage_conflicts = (*self._usage_conflicts, conflict)
                self._faults.append("synthetic receipt usage conflicts with the earlier reply")
                self._shared_physical_bound_untrusted = True
                self._mark_unsettled_indeterminate_locked()

    def _invalidate_liability_bound_locked(
        self, liability: SyntheticLiability, dimension: BoundDimension, observed: int, bound: int
    ) -> None:
        self._shared_physical_bound_disproved = True
        breach = SyntheticLiabilityBoundBreach(liability.liability_id, dimension, observed, bound)
        if breach not in self._liability_bound_breaches:
            self._liability_bound_breaches = (*self._liability_bound_breaches, breach)
            self._faults.append(self._bound_fault_text(dimension))
        self._mark_unsettled_indeterminate_locked()

    def interrupt(self, ticket_id: str) -> None:
        """Treat an interrupted reservation as possibly billed, not automatically free."""
        with self._lock:
            ticket = self._ticket_locked(ticket_id)
            if ticket.state is not TicketState.RESERVED:
                raise SafetyRefusal("only a reserved synthetic attempt can be interrupted")
            self._mark_unknown_locked(ticket, ReplyKind.INTERRUPTED)

    def dispatch(self, ticket_id: str, transport: SyntheticTransport) -> SyntheticOperation:
        """Consume one scripted reply; no other transport type is accepted."""
        if type(transport) is not SyntheticTransport:
            raise SafetyRefusal("only the closed synthetic transport is accepted")
        with self._lock:
            self._check_ready_locked()
            ticket = self._ticket_locked(ticket_id)
            if ticket.state is not TicketState.RESERVED:
                raise SafetyRefusal("the synthetic attempt is not reserved")
            try:
                reply = transport._next()
            except SafetyRefusal:
                self._mark_unknown_locked(ticket, ReplyKind.INTERRUPTED)
                raise
            if reply is None:
                self._mark_unknown_locked(ticket, ReplyKind.INTERRUPTED)
                raise SafetyRefusal("synthetic script ended after reservation; charge is unknown")
            ticket = replace(
                ticket,
                reported_completion_tokens=reply.reported_completion_tokens,
                reported_input_tokens=reply.reported_input_tokens,
            )
            self._tickets[ticket.ticket_id] = ticket
            self._observe_ticket_usage_locked(
                ticket, ticket.reported_input_tokens, ticket.reported_completion_tokens
            )
            if reply.charge_nanos is None:
                self._mark_unknown_locked(ticket, reply.kind)
            else:
                self._settle_locked(ticket, reply.kind, reply.charge_nanos)
            return self._operations[ticket.operation_id]

    def _advance_locked(self, operation: SyntheticOperation, kind: ReplyKind) -> SyntheticOperation:
        if kind is ReplyKind.ANSWER:
            return replace(operation, state=OperationState.COMPLETE)
        if kind is ReplyKind.EMPTY_ECHO and operation.echo_attempt < ECHO_ATTEMPTS:
            return replace(
                operation, state=OperationState.READY, echo_attempt=operation.echo_attempt + 1
            )
        if kind is ReplyKind.TRANSIENT and operation.outer_attempt < OUTER_ATTEMPTS:
            return replace(
                operation,
                state=OperationState.READY,
                outer_attempt=operation.outer_attempt + 1,
                echo_attempt=1,
            )
        return replace(operation, state=OperationState.FAILED)

    def _settle_locked(
        self,
        ticket: SyntheticTicket,
        kind: ReplyKind,
        charge: int,
        *,
        evidence_source: str | None = None,
    ) -> None:
        if charge > ticket.bound_nanos:
            self._invalidate_physical_bound_locked(
                ticket, BoundDimension.CHARGE, charge, ticket.bound_nanos
            )
        run = self._runs[ticket.run_id]
        new_spend = run.spent_nanos + charge
        self._runs[ticket.run_id] = replace(run, spent_nanos=new_spend)
        self._tickets[ticket.ticket_id] = replace(
            ticket, state=TicketState.SETTLED, outcome=kind, charge_nanos=charge
        )
        self._indeterminate_tickets.discard(ticket.ticket_id)
        operation = self._operations[ticket.operation_id]
        disputed_run_spend = self._disputed_booked_by_run_locked().get(run.run_id, 0)
        confirmed_run_spend = new_spend - disputed_run_spend
        if confirmed_run_spend < 0:
            raise RuntimeError("disputed synthetic charges exceed booked run spend")
        if run.cap_nanos is not None and confirmed_run_spend > run.cap_nanos and charge > 0:
            breach = SyntheticRunCapBreach(
                run.run_id, run.model, confirmed_run_spend, run.cap_nanos, ticket.ticket_id
            )
            self._later_run_cap_breaches = (*self._later_run_cap_breaches, breach)
            self._later_run_cap_breach_ticket_ids = (
                *self._later_run_cap_breach_ticket_ids,
                self._confirmed_ticket_ids_locked(run_id=run.run_id),
            )
            self._faults.append("a synthetic run cap was exceeded")
        source = evidence_source or ticket.ticket_id
        self._record_budget_breaches_locked(source, fault_on_new=True)
        self._clear_resolved_held_exposure_locked(source)
        self._operations[ticket.operation_id] = (
            replace(operation, state=OperationState.FAILED)
            if self._faults
            else self._advance_locked(operation, kind)
        )

    def _check_receipt_locked(self, receipt: SyntheticReceipt) -> None:
        if type(receipt) is not SyntheticReceipt:
            raise ValueError("only a synthetic final receipt is accepted")
        if not receipt.final:
            raise SafetyRefusal("a non-final synthetic receipt cannot reconcile a charge")
        if receipt.receipt_id in self._receipt_ids:
            raise SafetyRefusal("the synthetic receipt was already used")

    def _late_receipt_enriches_existing_id_locked(
        self, ticket: SyntheticTicket, receipt: SyntheticReceipt
    ) -> bool:
        prior = [
            row for row in self._reconciliation_receipts if row.receipt_id == receipt.receipt_id
        ]
        if not prior or any(
            row.subject != ticket.ticket_id or row.charge_nanos != ticket.charge_nanos
            for row in prior
        ):
            return False
        for field_name in ("reported_input_tokens", "reported_completion_tokens"):
            value = getattr(receipt, field_name)
            known = {
                getattr(row, field_name)
                for row in prior
                if getattr(row, field_name) is not None
            }
            if value is not None and value not in known:
                return True
        return False

    def reconcile_attempt(self, receipt: SyntheticReceipt) -> None:
        with self._lock:
            if type(receipt) is not SyntheticReceipt:
                raise ValueError("only a synthetic final receipt is accepted")
            if not receipt.final:
                raise SafetyRefusal("a non-final synthetic receipt cannot reconcile a charge")
            ticket = self._ticket_locked(receipt.subject)
            if (
                ticket.state not in (TicketState.UNKNOWN, TicketState.SETTLED)
                or ticket.outcome is None
            ):
                raise SafetyRefusal("the synthetic attempt has no unknown charge")
            settled = ticket.state is TicketState.SETTLED
            if settled and ticket.charge_nanos is None:
                raise SafetyRefusal("the synthetic settled attempt has no booked charge")
            contradictory = settled and receipt.charge_nanos != ticket.charge_nanos
            if not contradictory:
                if receipt.receipt_id in self._receipt_ids:
                    if not settled or not self._late_receipt_enriches_existing_id_locked(
                        ticket, receipt
                    ):
                        raise SafetyRefusal("the synthetic receipt was already used")
                else:
                    self._check_receipt_locked(receipt)
                if (
                    settled
                    and receipt.reported_input_tokens is None
                    and receipt.reported_completion_tokens is None
                ):
                    raise SafetyRefusal("the synthetic attempt has no unknown charge or new usage")
            self._record_usage_conflicts_locked(ticket, receipt)
            ticket = replace(
                ticket,
                receipt_reported_input_tokens=(
                    ticket.receipt_reported_input_tokens
                    if ticket.receipt_reported_input_tokens is not None
                    else receipt.reported_input_tokens
                ),
                receipt_reported_completion_tokens=(
                    ticket.receipt_reported_completion_tokens
                    if ticket.receipt_reported_completion_tokens is not None
                    else receipt.reported_completion_tokens
                ),
            )
            self._tickets[ticket.ticket_id] = ticket
            self._observe_ticket_usage_locked(
                ticket, receipt.reported_input_tokens, receipt.reported_completion_tokens
            )
            self._receipt_ids.add(receipt.receipt_id)
            self._reconciliation_receipts = (*self._reconciliation_receipts, receipt)
            if contradictory:
                assert ticket.charge_nanos is not None
                conflict = SyntheticChargeConflict(
                    ticket.ticket_id, receipt.receipt_id, ticket.charge_nanos, receipt.charge_nanos
                )
                self._charge_conflicts = (*self._charge_conflicts, conflict)
                self._indeterminate_charge_tickets.add(ticket.ticket_id)
                self._shared_physical_bound_untrusted = True
                self._faults.append("contradictory synthetic charge evidence")
                self._mark_unsettled_indeterminate_locked()
                self._record_budget_breaches_locked(receipt.receipt_id, fault_on_new=True)
                raise SafetyRefusal("contradictory synthetic charge evidence")
            if settled:
                self._record_budget_breaches_locked(receipt.receipt_id, fault_on_new=True)
                self._clear_resolved_held_exposure_locked(receipt.receipt_id)
                return
            self._settle_locked(
                ticket, ticket.outcome, receipt.charge_nanos, evidence_source=receipt.receipt_id
            )

    def reconcile_liability(self, receipt: SyntheticReceipt) -> None:
        with self._lock:
            self._check_receipt_locked(receipt)
            liability = self._liabilities.get(receipt.subject)
            if liability is None:
                raise SafetyRefusal("unknown synthetic liability")
            self._receipt_ids.add(receipt.receipt_id)
            self._reconciliation_receipts = (*self._reconciliation_receipts, receipt)
            self._liability_reconciliations = (
                *self._liability_reconciliations,
                SyntheticLiabilityReconciliation(liability, receipt),
            )
            del self._liabilities[receipt.subject]
            if liability.model is SyntheticModel.OSS:
                self._settled_external_oss += receipt.charge_nanos
            else:
                self._settled_external_other += receipt.charge_nanos
            if (
                liability.maximum_nanos is not None
                and receipt.charge_nanos > liability.maximum_nanos
            ):
                self._faults.append("a synthetic prior charge exceeded its reserved bound")
                if liability.independent_max_evidence_id is not None:
                    self._disproved_independent_max_evidence_ids.add(
                        liability.independent_max_evidence_id
                    )
            if liability.physical_spec_hash is not None:
                bound = self._spec.physical_bound
                for dimension, observed, limit in (
                    (
                        BoundDimension.INPUT_TOKENS,
                        receipt.reported_input_tokens,
                        bound.max_input_tokens,
                    ),
                    (
                        BoundDimension.COMPLETION_TOKENS,
                        receipt.reported_completion_tokens,
                        bound.max_output_tokens,
                    ),
                    (BoundDimension.CHARGE, receipt.charge_nanos, bound.worst_case_nanos),
                ):
                    if observed is not None and observed > limit:
                        self._invalidate_liability_bound_locked(
                            liability, dimension, observed, limit
                        )
            elif (
                receipt.reported_input_tokens is not None
                or receipt.reported_completion_tokens is not None
            ):
                self._faults.append("synthetic liability usage has no matched physical bound")
                self._mark_unsettled_indeterminate_locked()
            self._record_budget_breaches_locked(receipt.receipt_id, fault_on_new=True)
            self._clear_resolved_held_exposure_locked(receipt.receipt_id)


class SyntheticReading(Enum):
    ALPHA = "ALPHA"
    BETA = "BETA"
    GAMMA = "GAMMA"


@dataclass(frozen=True, slots=True)
class SyntheticOutput:
    item_id: str
    decoding: SyntheticDecoding
    provenance: str
    reading: SyntheticReading

    def __post_init__(self) -> None:
        _synthetic_id(self.item_id, "ITEM")
        _synthetic_id(self.provenance, "SOURCE")
        if (
            type(self.decoding) is not SyntheticDecoding
            or type(self.reading) is not SyntheticReading
        ):
            raise ValueError("only synthetic decoding and reading values are accepted")


def _history_header(decoding: SyntheticDecoding) -> bytes:
    limit = "-" if decoding.max_output_tokens is None else str(decoding.max_output_tokens)
    return f"SYNTHETIC-OSS-OUTPUT-V1|{decoding.kind.value}|{limit}\n".encode("ascii")


def _output_line(record: SyntheticOutput) -> bytes:
    return f"{record.item_id}|{record.provenance}|{record.reading.value}\n".encode("ascii")


@dataclass(frozen=True, slots=True)
class SyntheticHistory:
    """A tightly tagged, immutable in-memory synthetic history; never a path."""

    historical_bytes: bytes
    decoding: SyntheticDecoding
    records: tuple[SyntheticOutput, ...] = field(init=False)

    def __post_init__(self) -> None:
        if type(self.historical_bytes) is not bytes or type(self.decoding) is not SyntheticDecoding:
            raise ValueError("a synthetic history needs bytes and synthetic decoding")
        header = _history_header(self.decoding)
        if len(self.historical_bytes) > MAX_SYNTHETIC_HISTORY_BYTES or not (
            self.historical_bytes.startswith(header)
        ):
            raise OutputConflict("not a bounded, tagged synthetic history for this decoding")
        rest = self.historical_bytes[len(header) :]
        if rest and not rest.endswith(b"\n"):
            raise OutputConflict("a synthetic historical row is incomplete")
        rows = rest.splitlines(keepends=True)
        if len(rows) > MAX_SYNTHETIC_ROWS:
            raise OutputConflict("too many synthetic historical rows")
        records: list[SyntheticOutput] = []
        seen: set[str] = set()
        for line in rows:
            try:
                item_id, provenance, reading = line.decode("ascii").rstrip("\n").split("|")
                record = SyntheticOutput(
                    item_id, self.decoding, provenance, SyntheticReading(reading)
                )
            except (UnicodeError, ValueError) as exc:
                raise OutputConflict("invalid synthetic historical row") from exc
            if _output_line(record) != line:
                raise OutputConflict("noncanonical synthetic historical row")
            if item_id in seen:
                raise OutputConflict("duplicate synthetic historical item")
            seen.add(item_id)
            records.append(record)
        object.__setattr__(self, "records", tuple(records))

    @classmethod
    def empty(cls, decoding: SyntheticDecoding) -> SyntheticHistory:
        if type(decoding) is not SyntheticDecoding:
            raise ValueError("synthetic decoding is required")
        return cls(_history_header(decoding), decoding)


@dataclass(frozen=True, slots=True)
class SyntheticAppendDecision:
    historical_bytes: bytes
    appended_bytes: bytes
    combined_bytes: bytes
    historical_sha256: str
    combined_sha256: str
    added_items: tuple[str, ...]
    duplicate_items: tuple[str, ...]


def append_synthetic(
    history: SyntheticHistory, additions: tuple[SyntheticOutput, ...]
) -> SyntheticAppendDecision:
    """Return an all-or-nothing append decision without modifying historical bytes."""
    if type(history) is not SyntheticHistory or type(additions) is not tuple:
        raise ValueError("only synthetic history and a tuple of synthetic additions are accepted")
    if any(type(record) is not SyntheticOutput for record in additions):
        raise ValueError("only synthetic outputs are accepted")
    known = {record.item_id: record for record in history.records}
    fresh: list[SyntheticOutput] = []
    duplicates: list[str] = []
    for record in additions:
        if record.decoding != history.decoding:
            raise OutputConflict("a distinct decoding cannot fill this synthetic history")
        prior = known.get(record.item_id)
        if prior is not None:
            if prior != record:
                raise OutputConflict("conflicting synthetic reading or provenance")
            duplicates.append(record.item_id)
            continue
        known[record.item_id] = record
        fresh.append(record)
    if len(known) > MAX_SYNTHETIC_ROWS:
        raise OutputConflict("too many synthetic output rows")
    appended = b"".join(_output_line(record) for record in fresh)
    combined = history.historical_bytes + appended
    if len(combined) > MAX_SYNTHETIC_HISTORY_BYTES:
        raise OutputConflict("synthetic output exceeds the in-memory limit")
    return SyntheticAppendDecision(
        historical_bytes=history.historical_bytes,
        appended_bytes=appended,
        combined_bytes=combined,
        historical_sha256=hashlib.sha256(history.historical_bytes).hexdigest(),
        combined_sha256=hashlib.sha256(combined).hexdigest(),
        added_items=tuple(record.item_id for record in fresh),
        duplicate_items=tuple(duplicates),
    )
