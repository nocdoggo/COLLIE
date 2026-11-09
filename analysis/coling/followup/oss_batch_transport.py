"""Counted, paced batch transport for the dekallm re-pin (amendment A11).

This module does not start a study or select a checkpoint. A caller must first
prospectively register the exact batch implementation (amendment A11) and hold
the owner's standing authorization. Where the one-shot transport fenced exactly
one physical request, this transport counts, spaces and journals every physical
send of a paced continuation batch on the re-pinned ``dekallm/bf16`` endpoint:
an append-only per-send journal with monotonic ordinals, a minimum spacing
between sends, a hard send budget, a wall-clock stop, and a consecutive-refusal
fence. Retry and backoff stay where the frozen reader put them (the guarded
transport above this layer); this layer journals every send it passes on,
including those retries.

The request validator accepts only the original model and decoding with the
re-pinned provider object: one endpoint, fallbacks off, the bf16 precision
filter, temperature 0, a single user message, the required research user
agent and no ``max_tokens`` cap. An address fence keeps the owner's identity
out of the traffic: headers may carry no ``@`` at all, and a message may carry
no ``@`` except inside the email-like addresses of the pinned public items
(amendment A19: the earlier body-wide ban refused a public contact address in
one eligible notice, so the fence now names the only addresses a send may
carry instead of banning the corpus). It records only non-content metadata
(HTTP status, rate-limit-related headers) in an already-created owner-only
journal and never prints or retains response content. Tests use
invented requests and HTTPX's mock transport; they make no network or
credential access. These fences do not prove provider billing bounds, retention
or a completed run, and a different process can bypass them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import json
import math
import os
import re
import stat
import threading
import time

import httpx


USER_AGENT = "collie-research-fetch/0.1 (academic research; polite, cached)"
MODEL = "openai/gpt-oss-20b"
URL = "https://openrouter.ai/api/v1/chat/completions"
PROVIDER = {"order": ["dekallm/bf16"], "allow_fallbacks": False, "quantizations": ["bf16"]}
MAX_BODY = 1_000_000
MAX_JOURNAL = 8_000_000
MIN_SPACING_S = 4.0
RUN_LABEL = re.compile(r"[a-z0-9][a-z0-9._-]{0,160}", re.ASCII)
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.ASCII)
_LOCK_TYPE = type(threading.Lock())


class BatchRefusal(RuntimeError):
    """A batch send was refused without making another physical dispatch."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BatchRefusal("request JSON contains duplicate keys")
        result[key] = value
    return result


def _strings(value: object):
    if type(value) is str:
        yield value
    elif type(value) is list:
        for item in value:
            yield from _strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)


def public_addresses(raw: bytes) -> frozenset[str]:
    """The email-like addresses of a pinned items file: the only ones a send may carry.

    Amendment A19 replaces the body-wide ``@`` ban with this provenance pin. The
    item that stopped dispatches 5-9 carries a public contact address in its
    notice text (``related_information``), and the original registered runs of
    every other model already transmitted that same pinned text.
    """
    if type(raw) is not bytes:
        raise BatchRefusal("pinned items bytes are required")
    found = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeError, RecursionError):
            raise BatchRefusal("a pinned items file is not valid JSON") from None
        for text in _strings(row):
            found.update(ADDRESS.findall(text))
    return frozenset(found)


def _validate(request: httpx.Request, allowed_addresses: frozenset[str] = frozenset()) -> None:
    if type(request) is not httpx.Request or request.method != "POST" or str(request.url) != URL:
        raise BatchRefusal("request is not the pinned HTTPS endpoint")
    if request.headers.get("user-agent") != USER_AGENT:
        raise BatchRefusal("research user agent differs")
    if any("@" in value for value in request.headers.values()):
        raise BatchRefusal("request headers may contain an email address")
    try:
        body = request.content
        if len(body) > MAX_BODY:
            raise BatchRefusal("request body exceeds its bound")
        parsed = json.loads(body, object_pairs_hook=_unique, parse_float=Decimal,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError, httpx.RequestNotRead):
        raise BatchRefusal("request body is not valid bounded JSON") from None
    if type(parsed) is not dict or set(parsed) != {"model", "messages", "temperature", "provider"}:
        raise BatchRefusal("request fields differ from original decoding")
    temperature = parsed["temperature"]
    if (parsed["model"] != MODEL or type(temperature) not in (int, Decimal) or temperature != 0
            or type(parsed["provider"]) is not dict or parsed["provider"] != PROVIDER
            or type(parsed["provider"].get("allow_fallbacks")) is not bool):
        raise BatchRefusal("request model, provider, precision or decoding differs")
    messages = parsed["messages"]
    if (type(messages) is not list or len(messages) != 1 or type(messages[0]) is not dict
            or set(messages[0]) != {"role", "content"} or messages[0]["role"] != "user"
            or type(messages[0]["content"]) is not str):
        raise BatchRefusal("request message is invalid")
    content = messages[0]["content"]
    if set(ADDRESS.findall(content)) - allowed_addresses or "@" in ADDRESS.sub("", content):
        raise BatchRefusal("request message carries an address outside the pinned items")


def _journal(fd: int, expected_identity: tuple[int, int], expected_size: int, event: dict) -> int:
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600 or (before.st_dev, before.st_ino) != expected_identity
            or before.st_size != expected_size):
        raise BatchRefusal("private send journal identity or mode differs")
    raw = (json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    offset = 0
    while offset < len(raw):
        count = os.write(fd, raw[offset:])
        if count <= 0:
            raise BatchRefusal("private send journal write did not progress")
        offset += count
    os.fsync(fd)
    after = os.fstat(fd)
    if ((after.st_dev, after.st_ino) != expected_identity or after.st_nlink != 1
            or after.st_uid != os.geteuid() or stat.S_IMODE(after.st_mode) != 0o600
            or after.st_size != expected_size + len(raw)):
        raise BatchRefusal("private send journal changed")
    return after.st_size


def batch_reservation_bytes(selection_sha256: str, planned_targets: int, max_sends: int) -> bytes:
    """Canonical batch intent identity; the hold is not a charge bound."""
    if (type(selection_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", selection_sha256) is None
            or type(planned_targets) is not int or planned_targets < 0
            or type(max_sends) is not int or not planned_targets <= max_sends):
        raise BatchRefusal("batch reservation arguments are invalid")
    record = {"event": "reserved", "selection_sha256": selection_sha256,
              "planned_target_pairs": planned_targets, "max_sends": max_sends,
              "min_spacing_s": MIN_SPACING_S, "hold_is_proven_maximum": False}
    return (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


class CountedPacedTransport(httpx.BaseTransport):
    """Count, space and journal every physical send of one cooperating process."""

    def __init__(self, inner: httpx.BaseTransport, journal_fd: int, *, selection_sha256: str,
                 planned_targets: int, max_sends: int, stop_after_utc: datetime | None = None,
                 clock: object = time.monotonic, sleep: object = time.sleep,
                 allowed_addresses: frozenset[str] = frozenset()) -> None:
        if not isinstance(inner, httpx.BaseTransport) or type(journal_fd) is not int:
            raise BatchRefusal("an HTTPX transport and private journal are required")
        if stop_after_utc is not None and (type(stop_after_utc) is not datetime
                                           or stop_after_utc.tzinfo is not timezone.utc):
            raise BatchRefusal("batch deadline must be an exact UTC datetime")
        if not callable(clock) or not callable(sleep):
            raise BatchRefusal("a monotonic clock and a sleep are required")
        if (type(allowed_addresses) is not frozenset
                or any(type(address) is not str or ADDRESS.fullmatch(address) is None
                       for address in allowed_addresses)):
            raise BatchRefusal("the allowed address pin is invalid")
        expected = batch_reservation_bytes(selection_sha256, planned_targets, max_sends)
        info = os.fstat(journal_fd)
        flags = fcntl.fcntl(journal_fd, fcntl.F_GETFL)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or not (flags & os.O_APPEND)
                or flags & os.O_ACCMODE != os.O_RDWR or info.st_size > MAX_JOURNAL):
            raise BatchRefusal("private send journal is unsafe")
        try:
            fcntl.flock(journal_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BatchRefusal("another process holds the private send journal") from None
        try:
            raw = os.pread(journal_fd, MAX_JOURNAL + 1, 0)
            after = os.fstat(journal_fd)
            if (raw != expected or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)):
                raise BatchRefusal("private batch reservation is changed or has already been used")
        except BaseException:
            fcntl.flock(journal_fd, fcntl.LOCK_UN)
            raise
        self._inner = inner
        self._journal_fd = journal_fd
        self._journal_identity = (info.st_dev, info.st_ino)
        self._journal_size = len(expected)
        self._lock = threading.Lock()
        self._closed = False
        self._run = None
        self._sends = 0
        self._max_sends = max_sends
        self._allowed_addresses = allowed_addresses
        self._consecutive_refusals = 0
        self._last_send = None
        self._stop_after_utc = stop_after_utc
        self._clock = clock
        self._sleep = sleep

    def set_run(self, label: object) -> None:
        """Name the continuation run the next sends belong to (journal label only)."""
        if type(label) is not str or RUN_LABEL.fullmatch(label) is None:
            raise BatchRefusal("batch run label is invalid")
        with self._lock:
            if self._closed:
                raise BatchRefusal("batch transport is closed")
            self._run = label

    def stats(self) -> dict:
        with self._lock:
            return {"sends": self._sends, "max_sends": self._max_sends,
                    "consecutive_refusals": self._consecutive_refusals}

    def _wait_spacing(self) -> None:
        if self._last_send is not None:
            wait = MIN_SPACING_S - (self._clock() - self._last_send)
            if wait > 0:
                self._sleep(wait)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if type(self._lock) is not _LOCK_TYPE:
            raise BatchRefusal("batch lock differs")
        with self._lock:
            if self._closed:
                raise BatchRefusal("the batch transport is closed")
            if self._run is None:
                raise BatchRefusal("no continuation run is selected for this send")
            if self._sends >= self._max_sends:
                raise BatchRefusal("the batch send budget is exhausted")
            if self._stop_after_utc is not None and datetime.now(timezone.utc) >= self._stop_after_utc:
                raise BatchRefusal("the batch authorization deadline has passed")
            if self._consecutive_refusals >= 30:
                raise BatchRefusal("too many consecutive refused sends; the batch stops")
            _validate(request, self._allowed_addresses)
            self._wait_spacing()
            # Count and journal the send before it leaves: a crash between the
            # journal write and the response leaves an indeterminate charge on
            # record, never a silent retry.
            self._sends += 1
            ordinal = self._sends
            label = self._run
            self._journal_size = _journal(self._journal_fd, self._journal_identity, self._journal_size,
                                          {"event": "send_intent", "ordinal": ordinal, "run": label})
            mark = self._clock()
            try:
                response = self._inner.handle_request(request)
            except Exception as exc:
                self._last_send = mark
                self._consecutive_refusals += 1
                try:
                    self._journal_size = _journal(
                        self._journal_fd, self._journal_identity, self._journal_size,
                        {"event": "send_failure", "ordinal": ordinal, "run": label,
                         "error_type": type(exc).__name__, "charge": "unknown"})
                except Exception:
                    pass
                raise
            if type(response) is not httpx.Response or not 100 <= response.status_code <= 599:
                self._last_send = mark
                self._consecutive_refusals += 1
                try:
                    self._journal_size = _journal(
                        self._journal_fd, self._journal_identity, self._journal_size,
                        {"event": "send_invalid_response", "ordinal": ordinal, "run": label,
                         "charge": "unknown"})
                except Exception:
                    pass
                raise BatchRefusal("returned transport response is invalid; charge is unknown") from None
            self._last_send = mark
            if response.status_code == 429:
                self._consecutive_refusals += 1
            elif response.status_code < 400:
                self._consecutive_refusals = 0
            retry_after = response.headers.get("retry-after")
            if retry_after is not None and (type(retry_after) is not str or len(retry_after) > 32):
                retry_after = None
            self._journal_size = _journal(
                self._journal_fd, self._journal_identity, self._journal_size,
                {"event": "send_status", "ordinal": ordinal, "run": label,
                 "http_status": response.status_code, "retry_after": retry_after,
                 "charge": "unreconciled"})
            return response

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._closed = True
                try:
                    self._inner.close()
                finally:
                    fcntl.flock(self._journal_fd, fcntl.LOCK_UN)


def spacing_okay(elapsed: float) -> bool:
    """Whether a measured gap between send marks satisfies the minimum spacing."""
    return type(elapsed) is float and math.isfinite(elapsed) and elapsed >= MIN_SPACING_S
