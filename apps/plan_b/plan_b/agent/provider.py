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
and refuses a call that could exceed the per-run cap or the cumulative ledger cap. After the
call it charges the provider-reported cost (OpenRouter usage accounting), else the cost
computed from the reported tokens, else (timeout, unreadable reply) the upper bound. The
ledger (``var/model_spend.json``) records every call's model, tokens, cost and outcome.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import math
import os
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

PROVIDER_VERSION = "plan_b.provider/1.0.0"
DEFAULT_TIMEOUT_S = 90.0
MAX_RESPONSE_BYTES = 2_000_000
ERROR_EXCERPT_CHARS = 300
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
    max_tokens: int = 4096
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

    def __init__(self, message: str, *, status: int, record: CallRecord | None = None) -> None:
        super().__init__(message, record=record)
        self.status = status


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
    """Cumulative spend in a JSON file: ``{ledger, version, total_cost_usd, calls: [...]}``.
    Updates are atomic (temporary file + replace, mode 0600) under a lock. An unreadable
    ledger fails closed: the guard refuses calls rather than guess the total."""

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
        return data

    def total_usd(self) -> float:
        return float(self.read()["total_cost_usd"])

    def append(self, entry: dict[str, Any]) -> float:
        with self._locked():
            data = self.read()
            data["calls"].append(entry)
            data["total_cost_usd"] = round(
                float(data["total_cost_usd"]) + float(entry.get("cost_usd") or 0.0), 8
            )
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
            return float(data["total_cost_usd"])

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
    """Per-run and cumulative caps. One guard is one run (a policy episode or a gate run)."""

    def __init__(
        self, ledger: SpendLedger, *, max_run_usd: float, max_total_usd: float, run_id: str
    ) -> None:
        self.ledger = ledger
        self.max_run_usd = max_run_usd
        self.max_total_usd = max_total_usd
        self.run_id = run_id
        self.run_spent_usd = 0.0

    def check(self, estimate_usd: float) -> str | None:
        """Why a call bounded by ``estimate_usd`` is refused, or None when it may proceed."""
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
        self.ledger.append(entry)


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
        self, config: ModelConfig, guard: SpendGuard, *, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> None:
        self.config = config
        self.guard = guard
        self.timeout_s = timeout_s
        self._opener = urllib.request.build_opener(_NoRedirect())

    @property
    def requested_model(self) -> str:
        return self.config.model_id

    def body(self, request: ModelRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model_id,
            "messages": request.messages(),
            "max_tokens": request.max_tokens,
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

    def complete(self, request: ModelRequest) -> ModelResponse:
        data = json.dumps(self.body(request), ensure_ascii=False).encode("utf-8")
        bound = upper_bound_usd(self.config.model_id, len(data), request.max_tokens)
        started = _wall()
        refusal = self.guard.check(bound)
        if refusal is not None:
            record = self._record(request, started, 0, "spend_cap", error=refusal)
            # The refusal is recorded (cost 0, nothing sent); an unreadable ledger stays closed.
            with contextlib.suppress(OSError, ValueError):
                self.guard.charge(record, provider=self.config.provider)
            raise SpendCapReached(f"spend cap reached: {refusal}", record=record)
        key = self._read_key(request, started)
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
                record.error or f"HTTP {exc.code}", status=exc.code, record=record
            ) from None
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            reason = _scrub(str(getattr(exc, "reason", exc))[:ERROR_EXCERPT_CHARS], key)
            record = self._record(
                request,
                started,
                _ms(t0),
                "transport",
                basis="not_billed",
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
        )

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


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "[redacted]") if key else text


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _ms(t0: float) -> int:
    return int(round((time.monotonic() - t0) * 1000))


def _wall() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
