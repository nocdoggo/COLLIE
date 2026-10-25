"""OpenAI-compatible chat-completions client for the live agent (standard library only).

One ``complete`` call is one HTTP request: strict structured output (``response_format``
``json_schema`` with ``strict: true``), a bounded total timeout, no redirects, and a typed
``ProviderError`` for every failure (timeout, HTTP status, transport, malformed JSON, schema
violation, refusal, spend cap, configuration). The parsed output is validated against the
request's pydantic model; nothing unvalidated reaches the caller.

The key is read from the key file per call and sent only in the ``Authorization`` header. It
never enters a message, record, ledger entry or exception: error text from the server is
scrubbed of it and exceptions are raised without the urllib context.

Spend. Before each request the ``SpendGuard`` estimates an upper bound (prompt bytes / 3 tokens
plus ``max_tokens`` at the model's per-token prices, or ceiling prices for an unlisted model)
and refuses a call that could exceed the per-run cap or the cumulative ledger cap; otherwise it
reserves the bound in the ledger under its lock, so concurrent episode processes sharing the
ledger cannot together pass the cumulative cap. After the call it charges the provider-reported
cost (OpenRouter usage accounting), else the cost computed from the reported tokens, else
(timeout, unreadable reply) the upper bound, in place of the reservation. The ledger
(``var/model_spend.json``) records every call's model, tokens, cost and outcome.

Generation settings (1.1.0) are the same for every call of P1, P2 and P3: ``MAX_OUTPUT_TOKENS``
output tokens, no sampling parameter (``TEMPERATURE``), strict JSON schema output and, on
OpenRouter, ``require_parameters``. A run may carry a seed (``seed``), sent as the
OpenAI-compatible ``seed`` unless the model's endpoints refuse it (``SEED_UNSUPPORTED``). Every
``CallRecord`` records these settings, whether the seed was sent, and the reply's ``seed`` and
``system_fingerprint`` when it names them.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import math
import os
import socket
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from plan_b.agent.config import ModelConfig

try:  # POSIX advisory lock so two local processes cannot interleave ledger updates
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX hosts fall back to the in-process lock
    fcntl = None  # type: ignore[assignment]

# 1.1.0: one output limit, seeds, recorded settings. 1.2.0: a rate-limit (HTTP 429) backoff.
PROVIDER_VERSION = "plan_b.provider/1.2.0"
DEFAULT_TIMEOUT_S = 90.0
# Rate limits (1.2.0). OpenRouter limits this account to 20 requests per minute for the model,
# one every 3 s. A 429 answer is waited out inside ``complete`` and the same request is sent
# again: the first wait is RETRY_429_BASE_S (or the reply's Retry-After, if longer), doubled
# per further 429 up to RETRY_429_MAX_DELAY_S, and the waits of one call never exceed
# RETRY_429_MAX_WAIT_S of wall time. A 429 therefore uses no model call of the episode (the
# caller sees one call); only a 429 that outlasts the bound reaches the caller, as before.
RETRY_429_BASE_S = 3.0
RETRY_429_MAX_DELAY_S = 20.0
RETRY_429_MAX_WAIT_S = 60.0
# The output-token limit of every model call of P1, P2 and P3 (interpretation, menu choice and
# tool turn alike). Reasoning tokens count against it; 4096 is what P1 needed (W2-D11) and is
# ample for the shorter replies.
MAX_OUTPUT_TOKENS = 4096
# No sampling parameter is sent: none of the configured model's OpenRouter endpoints lists
# ``temperature`` (2026-10-25), and ``require_parameters`` would refuse a request carrying one.
# Every call therefore runs at the provider's default and records ``temperature: null``.
TEMPERATURE: float | None = None
# Models whose OpenRouter endpoints accept no ``seed``. Checked 2026-10-25: the public endpoint
# list of this model names ``seed`` for none of its 8 endpoints, and one seeded request (with
# ``require_parameters``) was refused, HTTP 404 "No endpoints found that can handle the
# requested parameters", not billed. A run's seed is then recorded on every call and not sent,
# so repeated trials are independent runs, not reproducible ones.
SEED_UNSUPPORTED: frozenset[str] = frozenset({"anthropic/claude-sonnet-5.5"})
MAX_RESPONSE_BYTES = 2_000_000
ERROR_EXCERPT_CHARS = 300
# Transport failures known to happen before the request goes out (name resolution, a refused
# connection, a certificate refused): not billed. Any other may follow the request: billed at
# its bound, so the ledger never counts less than may have been spent.
BEFORE_SEND_FAILURES = (socket.gaierror, ConnectionRefusedError, ssl.SSLCertVerificationError)
# USD per million tokens (prompt, completion), as OpenRouter's public model list gave them on
# 2026-10-24; used for the pre-call bound and when the reply reports no cost.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),
    "anthropic/claude-opus-5.5": (4.00, 20.00),
    "anthropic/claude-haiku-5.5": (0.10, 0.50),
}
CEILING_PRICES_PER_MTOK = (10.00, 50.00)  # an unlisted model is bounded well above those prices

Outcome = Literal[
    "ok",
    "timeout",
    "http_status",
    "transport",
    "malformed_json",
    "schema_violation",
    "refused",
    "spend_cap",
    "config",
]
CostBasis = Literal[
    "provider_usage", "computed_from_prices", "upper_bound_estimate", "not_billed", "not_sent"
]


# ---------------------------------------------------------------------------------- records


@dataclass(frozen=True)
class CallRecord:
    """What one model call did, without prompts or secrets. ``call_id`` is assigned by the
    caller (``mc_NNNN`` per episode); ``consumed_tool_call_ids`` names the tool results the
    request carried."""

    call_id: str
    purpose: str
    attempt: int
    requested_model: str
    model_id: str | None
    started_at: str
    latency_ms: int
    outcome: Outcome
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float = 0.0
    cost_basis: CostBasis = "not_sent"
    http_status: int | None = None
    generation_id: str | None = None
    error: str | None = None
    consumed_tool_call_ids: tuple[str, ...] = ()
    prompt_id: str | None = None
    # Generation settings of the request (the response format is always strict JSON schema).
    provider: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None  # None: not sent, the provider's default
    seed: int | None = None  # the run's requested seed (None: no seed requested)
    seed_sent: bool = False  # whether the request carried it as ``seed``
    seed_echo: int | None = None  # a ``seed`` the reply named, when it named one
    system_fingerprint: str | None = None  # the reply's backend fingerprint, when given
    # Provider 1.2.0: HTTP 429 answers waited out inside this call before its final attempt
    # (each one is its own ledger entry, not billed) and the wall time spent waiting.
    rate_limit_retries: int = 0
    rate_limit_wait_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["consumed_tool_call_ids"] = list(self.consumed_tool_call_ids)
        return out


@dataclass(frozen=True)
class ModelRequest:
    """One structured-output request. ``context`` is the structured payload the user message
    was rendered from (scripted test providers read it; it is never sent separately)."""

    purpose: str
    system: str
    user: str
    schema_name: str
    schema: dict[str, Any]
    output_model: type[BaseModel]
    max_tokens: int = MAX_OUTPUT_TOKENS
    context: dict[str, Any] = field(default_factory=dict)
    call_id: str = "mc_0000"
    attempt: int = 1
    consumed_tool_call_ids: tuple[str, ...] = ()
    prompt_id: str | None = None
    repair: tuple[dict[str, str], ...] = ()  # assistant reply + correction, on a repair attempt

    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user},
            *self.repair,
        ]

    def with_repair(self, raw_output: str, problem: str, *, call_id: str) -> ModelRequest:
        """The single repair attempt: the rejected reply and what was wrong with it."""
        correction = (
            "Your previous reply was rejected by the server: "
            f"{problem[:600]}. Reply again with one JSON object that matches the required "
            "schema exactly, choosing only values that the request offers."
        )
        return replace(
            self,
            call_id=call_id,
            attempt=self.attempt + 1,
            repair=(
                {"role": "assistant", "content": raw_output[:4000] or "(empty reply)"},
                {"role": "user", "content": correction},
            ),
        )


@dataclass(frozen=True)
class ModelResponse:
    parsed: BaseModel
    raw_text: str
    record: CallRecord


class ModelProvider(Protocol):
    @property
    def requested_model(self) -> str:
        """The configured model id (the returned id is in each ``CallRecord``)."""
        ...

    def complete(self, request: ModelRequest) -> ModelResponse:
        """One model call. Raises ``ProviderError`` (or a subclass) on any failure."""
        ...


# ---------------------------------------------------------------------------------- errors


class ProviderError(Exception):
    """A model call failed. ``record`` describes the attempt (absent only when nothing was
    attempted); ``raw_text`` is the model's reply for malformed or invalid output."""

    kind: Outcome = "transport"

    def __init__(
        self, message: str, *, record: CallRecord | None = None, raw_text: str = ""
    ) -> None:
        super().__init__(message)
        self.message = message
        self.record = record
        self.raw_text = raw_text


class ProviderTimeout(ProviderError):
    kind = "timeout"


class ProviderHTTPError(ProviderError):
    kind = "http_status"

    def __init__(
        self,
        message: str,
        *,
        status: int,
        record: CallRecord | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message, record=record)
        self.status = status
        self.retry_after_s = retry_after_s  # a Retry-After header in seconds, when given


class ProviderTransportError(ProviderError):
    kind = "transport"


class ProviderMalformedJSON(ProviderError):
    kind = "malformed_json"


class ProviderSchemaViolation(ProviderError):
    kind = "schema_violation"


class ProviderRefusal(ProviderError):
    kind = "refused"


class ProviderConfigError(ProviderError):
    kind = "config"


class SpendCapReached(ProviderError):
    kind = "spend_cap"


# ---------------------------------------------------------------------------------- spend


class SpendLedger:
    """Cumulative spend in a JSON file: ``{ledger, version, total_cost_usd, calls: [...]}``, plus
    ``reservations`` while calls are in flight. Updates are atomic (temporary file + replace,
    mode 0600) under a lock: a thread lock and, between processes, an ``fcntl`` lock on a
    sibling ``.lock`` file. An unreadable ledger fails closed: the guard refuses calls rather
    than guess the total.

    Several episode processes may share one ledger. The cumulative cap holds across them
    because a call's upper bound is reserved, under the lock, before it is sent
    (``reserve``): the cap is checked against the charged total plus every other live
    reservation, and the charge (``append``) replaces the reservation with the actual cost.
    A reservation whose process is gone is charged at its bound (outcome ``abandoned``), so the
    ledger never counts less than may have been spent."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "ledger": "plan_b.model_spend",
                "version": 1,
                "total_cost_usd": 0.0,
                "calls": [],
            }
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("calls"), list):
            raise ValueError("ledger has no calls list")
        total = data.get("total_cost_usd")
        if not isinstance(total, int | float) or not math.isfinite(total) or total < 0:
            raise ValueError("ledger total is not a finite non-negative number")
        if not isinstance(data.get("reservations", []), list):
            raise ValueError("ledger reservations are not a list")
        return data

    def total_usd(self) -> float:
        return float(self.read()["total_cost_usd"])

    def reserve(
        self, *, run_id: str, call_id: str, amount_usd: float, max_total_usd: float
    ) -> tuple[str | None, str | None]:
        """Reserve ``amount_usd`` for one call when the charged total plus every live
        reservation plus it stays within ``max_total_usd``: (reservation id, None), else
        (None, the refusal)."""
        with self._locked():
            data = self.read()
            settled = self._settle_abandoned(data)
            total = float(data["total_cost_usd"])
            pending = sum(float(r["amount_usd"]) for r in data.get("reservations", []))
            if total + pending + amount_usd > max_total_usd:
                if settled:
                    self._write(data)
                return None, (
                    f"cumulative cap {max_total_usd:.2f} USD: ledger total {total:.4f}, "
                    f"{pending:.4f} reserved by calls in flight, next call bounded at "
                    f"{amount_usd:.4f}"
                )
            reservation = f"rsv-{os.getpid()}-{run_id}-{call_id}-{time.monotonic_ns()}"
            data.setdefault("reservations", []).append(
                {
                    "reservation_id": reservation,
                    "run_id": run_id,
                    "call_id": call_id,
                    "amount_usd": round(amount_usd, 8),
                    "at": _wall(),
                    "pid": os.getpid(),
                    "pid_start": _process_start(os.getpid()),
                }
            )
            self._write(data)
            return reservation, None

    def release(self, reservation: str | None) -> None:
        """Drop a reservation whose call was never sent (nothing to charge)."""
        if reservation is None:
            return
        with self._locked():
            data = self.read()
            data["reservations"] = [
                r for r in data.get("reservations", []) if r["reservation_id"] != reservation
            ]
            self._settle_abandoned(data)
            self._write(data)

    def abandon(self, reservation: str) -> float:
        """Charge a reservation at its bound (outcome ``abandoned``): its call was sent but
        never charged. Returns the amount charged (0 when it is no longer reserved)."""
        with self._locked():
            data = self.read()
            found = [r for r in data.get("reservations", []) if r["reservation_id"] == reservation]
            data["reservations"] = [
                r for r in data.get("reservations", []) if r["reservation_id"] != reservation
            ]
            for r in found:
                self._charge(data, _abandoned(r, "left by a call that was never charged"))
            self._settle_abandoned(data)
            self._write(data)
            return sum(float(r["amount_usd"]) for r in found)

    def append(self, entry: dict[str, Any], *, reservation: str | None = None) -> float:
        with self._locked():
            data = self.read()
            if reservation is not None:
                data["reservations"] = [
                    r for r in data.get("reservations", []) if r["reservation_id"] != reservation
                ]
            self._charge(data, entry)
            self._settle_abandoned(data)
            self._write(data)
            return float(data["total_cost_usd"])

    @staticmethod
    def _charge(data: dict[str, Any], entry: dict[str, Any]) -> None:
        data["calls"].append(entry)
        data["total_cost_usd"] = round(
            float(data["total_cost_usd"]) + float(entry.get("cost_usd") or 0.0), 8
        )

    def _settle_abandoned(self, data: dict[str, Any]) -> bool:
        """Charge the bound of each reservation whose process no longer exists; True when one
        was charged."""
        live: list[dict[str, Any]] = []
        settled = False
        for r in data.get("reservations", []):
            if _process_alive(int(r.get("pid", 0)), r.get("pid_start")):
                live.append(r)
                continue
            settled = True
            self._charge(
                data, _abandoned(r, "reserved by a process that ended before charging the call")
            )
        if live or "reservations" in data:
            data["reservations"] = live
        return settled

    def _write(self, data: dict[str, Any]) -> None:
        if not data.get("reservations"):
            data.pop("reservations", None)  # the settled file keeps its Wave 2 shape
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".model_spend.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=1, sort_keys=True)
                handle.write("\n")
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        with self._lock:
            if fcntl is None:
                yield
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.path.with_name(self.path.name + ".lock")
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)


class SpendGuard:
    """Per-run and cumulative caps. One guard is one run (a policy episode or a gate run); its
    calls are sequential, so it holds at most one reservation at a time."""

    def __init__(
        self, ledger: SpendLedger, *, max_run_usd: float, max_total_usd: float, run_id: str
    ) -> None:
        self.ledger = ledger
        self.max_run_usd = max_run_usd
        self.max_total_usd = max_total_usd
        self.run_id = run_id
        self.run_spent_usd = 0.0
        self._reservation: str | None = None

    def check(self, estimate_usd: float) -> str | None:
        """Why a call bounded by ``estimate_usd`` is refused, or None when it may proceed (a
        read-only check; ``reserve`` is the one a call makes)."""
        if self.run_spent_usd + estimate_usd > self.max_run_usd:
            return (
                f"per-run cap {self.max_run_usd:.2f} USD: spent {self.run_spent_usd:.4f}, next "
                f"call bounded at {estimate_usd:.4f}"
            )
        try:
            total = self.ledger.total_usd()
        except (OSError, ValueError) as exc:
            return f"spend ledger unreadable ({type(exc).__name__}); refusing to guess the total"
        if total + estimate_usd > self.max_total_usd:
            return (
                f"cumulative cap {self.max_total_usd:.2f} USD: ledger total {total:.4f}, next "
                f"call bounded at {estimate_usd:.4f}"
            )
        return None

    def reserve(self, estimate_usd: float, *, call_id: str = "") -> str | None:
        """Reserve the call's bound in the ledger (``SpendLedger.reserve``), or say why the
        call is refused: the per-run cap, the cumulative cap with every process's calls in
        flight counted, or an unreadable ledger."""
        if self._reservation is not None:
            # An earlier call of this run left before it was charged (an unexpected error
            # after the reply): charge its bound, so neither cap counts less than was spent.
            stale, self._reservation = self._reservation, None
            with contextlib.suppress(OSError, ValueError):
                self.run_spent_usd += self.ledger.abandon(stale)
        if self.run_spent_usd + estimate_usd > self.max_run_usd:
            return (
                f"per-run cap {self.max_run_usd:.2f} USD: spent {self.run_spent_usd:.4f}, next "
                f"call bounded at {estimate_usd:.4f}"
            )
        try:
            self._reservation, refusal = self.ledger.reserve(
                run_id=self.run_id,
                call_id=call_id,
                amount_usd=estimate_usd,
                max_total_usd=self.max_total_usd,
            )
        except (OSError, ValueError) as exc:
            return f"spend ledger unreadable ({type(exc).__name__}); refusing to guess the total"
        return refusal

    def release(self) -> None:
        """The reserved call was never sent."""
        reservation, self._reservation = self._reservation, None
        self.ledger.release(reservation)

    def charge(self, record: CallRecord, *, provider: str) -> None:
        self.run_spent_usd += record.cost_usd
        entry = {
            "at": record.started_at,
            "run_id": self.run_id,
            "provider": provider,
            "call_id": record.call_id,
            "purpose": record.purpose,
            "attempt": record.attempt,
            "model_requested": record.requested_model,
            "model_returned": record.model_id,
            "outcome": record.outcome,
            "http_status": record.http_status,
            "latency_ms": record.latency_ms,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "total_tokens": record.total_tokens,
            "reasoning_tokens": record.reasoning_tokens,
            "cost_usd": record.cost_usd,
            "cost_basis": record.cost_basis,
            "generation_id": record.generation_id,
        }
        reservation, self._reservation = self._reservation, None
        self.ledger.append(entry, reservation=reservation)


def prices_for(model_id: str) -> tuple[tuple[float, float], bool]:
    """(prompt, completion) USD per million tokens, and whether the model is listed."""
    if model_id in PRICES_PER_MTOK:
        return PRICES_PER_MTOK[model_id], True
    return CEILING_PRICES_PER_MTOK, False


def upper_bound_usd(model_id: str, request_bytes: int, max_tokens: int) -> float:
    """Conservative bound: every three request bytes a prompt token, all of ``max_tokens``
    generated (it bounds reasoning tokens too)."""
    (prompt_price, completion_price), _ = prices_for(model_id)
    prompt_tokens = math.ceil(request_bytes / 3)
    return (prompt_tokens * prompt_price + max_tokens * completion_price) / 1_000_000


# ---------------------------------------------------------------------------------- client


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: it would resend the Authorization header elsewhere."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class OpenAICompatibleProvider:
    """``POST {base_url}/chat/completions`` with strict structured output."""

    def __init__(
        self,
        config: ModelConfig,
        guard: SpendGuard,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        seed: int | None = None,
    ) -> None:
        self.config = config
        self.guard = guard
        self.timeout_s = timeout_s
        self.seed = seed
        self._opener = urllib.request.build_opener(_NoRedirect())
        self._sleep = time.sleep  # replaced in tests
        self._monotonic = time.monotonic

    def complete(self, request: ModelRequest) -> ModelResponse:
        """One model call: ``_attempt``, with HTTP 429 answers waited out and retried within
        ``RETRY_429_MAX_WAIT_S`` of wall time (see ``RETRY_429_BASE_S``)."""
        retries = 0
        waited = 0.0
        while True:
            try:
                response = self._attempt(request)
            except ProviderHTTPError as exc:
                if exc.status != 429:
                    raise
                delay = min(RETRY_429_BASE_S * 2**retries, RETRY_429_MAX_DELAY_S)
                if exc.retry_after_s is not None:
                    delay = max(delay, min(exc.retry_after_s, RETRY_429_MAX_DELAY_S))
                if waited + delay > RETRY_429_MAX_WAIT_S:
                    if exc.record is not None:
                        exc.record = _rate_limited(exc.record, retries, waited)
                    raise
                t0 = self._monotonic()
                self._sleep(delay)
                waited += max(self._monotonic() - t0, delay)
                retries += 1
                continue
            except ProviderError as exc:
                if retries and exc.record is not None:
                    exc.record = _rate_limited(exc.record, retries, waited)
                raise
            if retries:
                response = replace(response, record=_rate_limited(response.record, retries, waited))
            return response

    @property
    def sends_seed(self) -> bool:
        """Whether requests carry the run's seed as the OpenAI-compatible ``seed``: when one is
        set, unless the routed endpoints are known to refuse it (``SEED_UNSUPPORTED``)."""
        if self.seed is None:
            return False
        return not (
            self.config.provider == "openrouter" and self.config.model_id in SEED_UNSUPPORTED
        )

    @property
    def requested_model(self) -> str:
        return self.config.model_id

    def body(self, request: ModelRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model_id,
            "messages": request.messages(),
            "max_tokens": request.max_tokens,
            **({"temperature": TEMPERATURE} if TEMPERATURE is not None else {}),
            **({"seed": self.seed} if self.sends_seed else {}),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.schema,
                },
            },
        }
        if self.config.provider == "openrouter":
            body["usage"] = {"include": True}  # usage accounting: cost in the reply
            body["provider"] = {"require_parameters": True}  # only routes honoring the schema
        return body

    def _attempt(self, request: ModelRequest) -> ModelResponse:
        data = json.dumps(self.body(request), ensure_ascii=False).encode("utf-8")
        bound = upper_bound_usd(self.config.model_id, len(data), request.max_tokens)
        started = _wall()
        refusal = self.guard.reserve(bound, call_id=request.call_id)
        if refusal is not None:
            record = self._record(request, started, 0, "spend_cap", error=refusal)
            # The refusal is recorded (cost 0, nothing sent); an unreadable ledger stays closed.
            with contextlib.suppress(OSError, ValueError):
                self.guard.charge(record, provider=self.config.provider)
            raise SpendCapReached(f"spend cap reached: {refusal}", record=record)
        try:
            key = self._read_key(request, started)
        except ProviderConfigError:
            self.guard.release()  # nothing was sent
            raise
        http_request = urllib.request.Request(
            self.config.chat_url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Title": "Plan B sandbox (fictional)",
            },
        )
        t0 = time.monotonic()
        try:
            status, payload_bytes = self._send(http_request, t0 + self.timeout_s)
        except ProviderTimeout:
            record = self._record(
                request,
                started,
                _ms(t0),
                "timeout",
                cost=bound,
                basis="upper_bound_estimate",
                error=f"no complete reply within {self.timeout_s:.0f} s",
            )
            self.guard.charge(record, provider=self.config.provider)
            raise ProviderTimeout(record.error or "timeout", record=record) from None
        except urllib.error.HTTPError as exc:
            excerpt = _scrub(_excerpt(exc), key)
            record = self._record(
                request,
                started,
                _ms(t0),
                "http_status",
                basis="not_billed",
                http_status=exc.code,
                error=f"HTTP {exc.code}: {excerpt}",
            )
            self.guard.charge(record, provider=self.config.provider)
            raise ProviderHTTPError(
                record.error or f"HTTP {exc.code}",
                status=exc.code,
                record=record,
                retry_after_s=_retry_after(exc),
            ) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            reason = _scrub(str(getattr(exc, "reason", exc))[:ERROR_EXCERPT_CHARS], key)
            # A connection lost after the request went out (reset, closed, a reply cut short, a
            # TLS failure mid-reply) may have been generated and billed: charged at its bound,
            # as a timeout is. Only a failure known to precede sending is not billed.
            cause = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            sent = not isinstance(cause, BEFORE_SEND_FAILURES)
            record = self._record(
                request,
                started,
                _ms(t0),
                "transport",
                cost=bound if sent else 0.0,
                basis="upper_bound_estimate" if sent else "not_billed",
                error=f"transport failure: {reason}",
            )
            self.guard.charge(record, provider=self.config.provider)
            raise ProviderTransportError(record.error or "transport", record=record) from None
        finally:
            del http_request
        latency = _ms(t0)
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("reply is not a JSON object")
        except (UnicodeDecodeError, ValueError):
            record = self._record(
                request,
                started,
                latency,
                "malformed_json",
                cost=bound,
                basis="upper_bound_estimate",
                http_status=status,
                error="the reply envelope is not JSON",
            )
            self.guard.charge(record, provider=self.config.provider)
            raise ProviderMalformedJSON(record.error or "", record=record) from None
        record = self._usage_record(request, started, latency, status, payload, bound)
        content, problem, refused = _content(payload)
        if problem is not None:
            outcome: Outcome = "refused" if refused else "malformed_json"
            record = replace(record, outcome=outcome, error=_scrub(problem, key))
            self.guard.charge(record, provider=self.config.provider)
            error_cls = ProviderRefusal if refused else ProviderMalformedJSON
            raise error_cls(record.error or "", record=record, raw_text=content)
        try:
            value = json.loads(content)
        except ValueError:
            record = replace(record, outcome="malformed_json", error="the reply is not JSON")
            self.guard.charge(record, provider=self.config.provider)
            raise ProviderMalformedJSON(
                record.error or "", record=record, raw_text=content
            ) from None
        try:
            parsed = request.output_model.model_validate(value)
        except ValidationError as exc:
            record = replace(record, outcome="schema_violation", error=_validation_text(exc))
            self.guard.charge(record, provider=self.config.provider)
            raise ProviderSchemaViolation(
                record.error or "", record=record, raw_text=content
            ) from None
        self.guard.charge(record, provider=self.config.provider)
        return ModelResponse(parsed=parsed, raw_text=content, record=record)

    # -------------------------------------------------------------------- internals

    def _read_key(self, request: ModelRequest, started: str) -> str:
        try:
            key = self.config.key_file.read_text(encoding="utf-8").strip()
        except OSError:
            key = ""
        if not key or any(c.isspace() for c in key):
            raise ProviderConfigError(
                "the model key file is missing, empty or malformed",
                record=self._record(request, started, 0, "config"),
            )
        return key

    def _send(self, http_request: urllib.request.Request, deadline: float) -> tuple[int, bytes]:
        remaining = deadline - time.monotonic()
        try:
            with self._opener.open(http_request, timeout=max(remaining, 0.1)) as response:
                status = int(response.status)
                if 300 <= status < 400:
                    raise urllib.error.HTTPError(
                        http_request.full_url,
                        status,
                        "redirect not followed",
                        response.headers,
                        None,
                    )
                chunks: list[bytes] = []
                size = 0
                while True:
                    if time.monotonic() > deadline:
                        raise ProviderTimeout("deadline passed while reading")
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        return status, b"\x00"  # oversized: reported as malformed
                    chunks.append(chunk)
                return status, b"".join(chunks)
        except TimeoutError:
            raise ProviderTimeout("socket timeout") from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise ProviderTimeout("socket timeout") from None
            raise

    def _record(
        self,
        request: ModelRequest,
        started: str,
        latency_ms: int,
        outcome: Outcome,
        *,
        cost: float = 0.0,
        basis: CostBasis = "not_sent",
        http_status: int | None = None,
        error: str | None = None,
    ) -> CallRecord:
        return CallRecord(
            call_id=request.call_id,
            purpose=request.purpose,
            attempt=request.attempt,
            requested_model=self.config.model_id,
            model_id=None,
            started_at=started,
            latency_ms=latency_ms,
            outcome=outcome,
            cost_usd=round(cost, 8),
            cost_basis=basis,
            http_status=http_status,
            error=error,
            consumed_tool_call_ids=request.consumed_tool_call_ids,
            prompt_id=request.prompt_id,
            **self._settings(request),
        )

    def _settings(self, request: ModelRequest) -> dict[str, Any]:
        """The request's generation settings, as each call records them."""
        return {
            "provider": self.config.provider,
            "max_tokens": request.max_tokens,
            "temperature": TEMPERATURE,
            "seed": self.seed,
            "seed_sent": self.sends_seed,
        }

    def _usage_record(
        self,
        request: ModelRequest,
        started: str,
        latency_ms: int,
        status: int,
        payload: dict[str, Any],
        bound: float,
    ) -> CallRecord:
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        assert isinstance(usage, dict)
        prompt = _int(usage.get("prompt_tokens"))
        completion = _int(usage.get("completion_tokens"))
        total = _int(usage.get("total_tokens"))
        details = usage.get("completion_tokens_details")
        reasoning = _int(details.get("reasoning_tokens")) if isinstance(details, dict) else None
        reported = usage.get("cost")
        basis: CostBasis
        if isinstance(reported, int | float) and math.isfinite(reported) and reported >= 0:
            cost, basis = float(reported), "provider_usage"
        elif prompt is not None and completion is not None:
            (p_price, c_price), _ = prices_for(self.config.model_id)
            cost, basis = (
                (prompt * p_price + completion * c_price) / 1_000_000,
                "computed_from_prices",
            )
        else:
            cost, basis = bound, "upper_bound_estimate"
        model = payload.get("model")
        generation = payload.get("id")
        echo = payload.get("seed")
        fingerprint = payload.get("system_fingerprint")
        return CallRecord(
            call_id=request.call_id,
            purpose=request.purpose,
            attempt=request.attempt,
            requested_model=self.config.model_id,
            model_id=str(model)[:200] if isinstance(model, str) and model else None,
            started_at=started,
            latency_ms=latency_ms,
            outcome="ok",
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            reasoning_tokens=reasoning,
            cost_usd=round(cost, 8),
            cost_basis=basis,
            http_status=status,
            generation_id=str(generation)[:200] if isinstance(generation, str) else None,
            consumed_tool_call_ids=request.consumed_tool_call_ids,
            prompt_id=request.prompt_id,
            **self._settings(request),
            seed_echo=_int(echo),
            system_fingerprint=str(fingerprint)[:200] if isinstance(fingerprint, str) else None,
        )


def _content(payload: dict[str, Any]) -> tuple[str, str | None, bool]:
    """(text, problem, refused) of the first choice."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", "the reply has no choices", False
    choice = choices[0]
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    assert isinstance(message, dict)
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return "", f"the model refused: {refusal[:ERROR_EXCERPT_CHARS]}", True
    content = message.get("content")
    if isinstance(content, list):  # content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        return "", "the reply has no content", False
    if choice.get("finish_reason") == "length":
        return content, "the reply was cut off at max_tokens", False
    return content, None, False


def _validation_text(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:5]:
        where = ".".join(str(p) for p in error.get("loc", ())) or "(root)"
        parts.append(f"{where}: {error.get('msg', 'invalid')}")
    return "schema violation: " + "; ".join(parts)


def _excerpt(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read(ERROR_EXCERPT_CHARS * 4)
    except Exception:  # noqa: BLE001 - an unreadable error body is reported as absent
        return "(no readable body)"
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""
    return " ".join(text.split())[:ERROR_EXCERPT_CHARS] or "(empty body)"


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """A Retry-After header given in seconds (an HTTP date is ignored)."""
    value = exc.headers.get("Retry-After") if exc.headers is not None else None
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and math.isfinite(seconds) and seconds >= 0 else None


def _rate_limited(record: CallRecord, retries: int, waited_s: float) -> CallRecord:
    return replace(record, rate_limit_retries=retries, rate_limit_wait_ms=round(waited_s * 1000))


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "[redacted]") if key else text


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _ms(t0: float) -> int:
    return int(round((time.monotonic() - t0) * 1000))


def _wall() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _abandoned(reservation: dict[str, Any], note: str) -> dict[str, Any]:
    """The ledger entry charging a reservation at its bound."""
    return {
        "at": reservation.get("at"),
        "run_id": reservation.get("run_id"),
        "call_id": reservation.get("call_id"),
        "outcome": "abandoned",
        "cost_usd": float(reservation["amount_usd"]),
        "cost_basis": "upper_bound_estimate",
        "note": note,
    }


def _process_start(pid: int) -> str | None:
    """The process's start time in clock ticks since boot (Linux ``/proc``), or None."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_bytes()
    except OSError:
        return None
    fields = stat[stat.rfind(b")") + 2 :].split()  # the name may hold any bytes, even ")"
    return fields[19].decode("ascii", "replace") if len(fields) > 19 else None


def _process_alive(pid: int, start: str | None = None) -> bool:
    """Whether a reservation's owner still runs: a local process with this id exists and,
    when its start time was recorded, started then (a reused id is another process)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists under another user
    if start is not None:
        now = _process_start(pid)
        return now is None or now == start
    return True
