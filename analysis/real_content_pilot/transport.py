"""A guard around a live transport: bounded retries, logged refusals, and a hard spend cap.

``OpenAICompatClient`` has no retry, pacing or spend control of its own beyond the SDK's short
built-in retries (``docs/module06_research_notes.md``; one exhausted 429 aborts a whole sweep).
This wrapper sits between ``MeteredClient`` and the real client, so it only ever sees cache
misses, i.e. real paid requests:

* **Transient failures** (HTTP 408/409/429/5xx, timeouts, connection errors) are retried with
  exponential backoff, honouring ``Retry-After``. Everything else raises.
* **Refusals** (HTTP 403, e.g. xAI's server-side moderation of JSON-shaped prompts) become an
  empty response with zero tokens. ``MeteredClient`` caches it like any other answer, the arm
  settles it as a parse failure, and the refusal is logged separately so the analysis can tell
  a refusal from a malformed answer.
* **The spend cap** is checked before every request against the cumulative dated cost of every
  physical call in ``spend_log`` (including earlier invocations of the same run), priced with the
  ledger's own rule. Crossing it raises :class:`SpendCapReached`; paid answers stay cached, so a
  rerun resumes for free.

The log records token counts, cost, latency, status and a prompt digest per request. It never
records prompt text, response text, headers or credentials.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from collie.llm.client import DecodingConfig, EndpointConfig, RawResponse, Transport
from collie.llm.ledger import _usd

TRANSIENT_STATUS = frozenset({408, 409, 429})


class SpendCapReached(RuntimeError):
    """The run's cumulative dated cost reached its cap; no further request was sent."""


class CallCapReached(RuntimeError):
    """The run's physical-call cap was reached; no further request was sent."""


def classify_error(exc: BaseException) -> str:
    """``refusal``, ``transient`` or ``fatal`` for an exception raised by the openai SDK."""
    try:
        import openai
    except ImportError:  # pragma: no cover - the llm extra is installed wherever this runs
        return "fatal"
    if isinstance(exc, openai.PermissionDeniedError):
        return "refusal"
    if isinstance(exc, openai.APIStatusError):
        code = int(exc.status_code)
        return "transient" if code in TRANSIENT_STATUS or code >= 500 else "fatal"
    if isinstance(exc, openai.APIConnectionError):  # includes APITimeoutError
        return "transient"
    return "fatal"


def retry_after_seconds(exc: BaseException) -> float | None:
    """The server's requested wait, when it sends a sane one."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    for name, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        value = headers.get(name)
        if value is None:
            continue
        try:
            seconds = float(value) / scale
        except (TypeError, ValueError):
            continue
        if 0.0 <= seconds <= 300.0:
            return seconds
    return None


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:400]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class GuardedTransport:
    """A :class:`~collie.llm.client.Transport` that wraps a live one. See the module docstring."""

    inner: Transport
    endpoint: EndpointConfig
    spend_log: Path
    spend_cap_usd: float
    max_physical_calls: int
    min_interval_s: float = 0.0
    max_attempts: int = 8
    base_delay_s: float = 5.0
    max_delay_s: float = 120.0
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    spent_usd: float = field(init=False, default=0.0)
    physical_calls: int = field(init=False, default=0)
    prior_usd: float = field(init=False, default=0.0)
    prior_calls: int = field(init=False, default=0)
    refusals: int = field(init=False, default=0)
    retries: int = field(init=False, default=0)
    _last_call: float | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.spend_cap_usd <= 0 or self.max_physical_calls <= 0:
            raise ValueError("spend and call caps must be positive")
        if self.spend_log.is_file():
            for line in self.spend_log.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("event") == "call":
                    self.spent_usd += float(row["usd"])
                    self.physical_calls += 1
        self.prior_usd = self.spent_usd
        self.prior_calls = self.physical_calls

    @property
    def model_id(self) -> str:
        return self.inner.model_id

    def _log(self, row: dict) -> None:
        self.spend_log.parent.mkdir(parents=True, exist_ok=True)
        with self.spend_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": _now(), **row}, sort_keys=True) + "\n")

    def complete_metered(
        self, prompt: str, *, decoding: DecodingConfig, system: str | None = None
    ) -> RawResponse:
        if self.spent_usd >= self.spend_cap_usd:
            raise SpendCapReached(
                f"cumulative spend ${self.spent_usd:.4f} reached the ${self.spend_cap_usd:.2f} cap"
            )
        if self.physical_calls >= self.max_physical_calls:
            raise CallCapReached(f"{self.physical_calls} physical calls reached the cap")
        if self.min_interval_s > 0 and self._last_call is not None:
            wait = self.min_interval_s - (self.clock() - self._last_call)
            if wait > 0:
                self.sleep(wait)
        digest = hashlib.sha256(f"{system or ''}\x00{prompt}".encode()).hexdigest()
        status = "ok"
        attempt = 0
        started = time.perf_counter()
        while True:
            attempt += 1
            try:
                raw = self.inner.complete_metered(prompt, decoding=decoding, system=system)
                break
            except Exception as exc:
                kind = classify_error(exc)
                if kind == "refusal":
                    status = "refused"
                    self.refusals += 1
                    raw = RawResponse(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)
                    self._log({"event": "refusal", "prompt_sha256": digest, "error": _short(exc)})
                    break
                if kind == "transient" and attempt < self.max_attempts:
                    delay = retry_after_seconds(exc)
                    if delay is None:
                        delay = min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 1))
                    self.retries += 1
                    self._log(
                        {
                            "event": "retry",
                            "prompt_sha256": digest,
                            "attempt": attempt,
                            "delay_s": delay,
                            "error": _short(exc),
                        }
                    )
                    self.sleep(delay)
                    continue
                self._log(
                    {
                        "event": "error",
                        "prompt_sha256": digest,
                        "attempt": attempt,
                        "error": _short(exc),
                    }
                )
                raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._last_call = self.clock()
        usd = _usd(raw, self.endpoint)
        self.spent_usd += usd
        self.physical_calls += 1
        self._log(
            {
                "event": "call",
                "status": status,
                "attempts": attempt,
                "latency_ms": round(latency_ms, 3),
                "prompt_sha256": digest,
                "prompt_tokens": raw.prompt_tokens,
                "completion_tokens": raw.completion_tokens,
                "total_tokens": raw.total_tokens,
                "billable_output_tokens": raw.billable_output(self.endpoint),
                "usd": usd,
                "cumulative_usd": self.spent_usd,
            }
        )
        return raw

    def stats(self) -> dict:
        return {
            "physical_calls_total": self.physical_calls,
            "physical_calls_this_invocation": self.physical_calls - self.prior_calls,
            "usd_total": self.spent_usd,
            "usd_this_invocation": self.spent_usd - self.prior_usd,
            "refusals_this_invocation": self.refusals,
            "retries_this_invocation": self.retries,
            "spend_cap_usd": self.spend_cap_usd,
            "max_physical_calls": self.max_physical_calls,
        }
