"""One-physical-attempt transport candidate for the original gpt-oss route.

This module does not start a study or select a checkpoint. A caller must first
prospectively register the exact continuation implementation and obtain the
owner's spending authority. The one-attempt fence and durable intent reduce
retry risk; they do NOT establish a hard billable bound, reconcile historical
charges, authenticate provider privacy, fence a different process, or integrate
the study ledger. One physical request can still exceed a provisional hold.

The implementation accepts only the original model/route/default-decoding JSON,
the required research user agent and a single user message without ``@``. It
records only non-content metadata in an already-created owner-only journal and
will not send a second request, even after an exception. Tests use invented
requests and HTTPX's mock transport; they make no network or credential access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import json
import os
import re
import stat
import threading

import httpx


USER_AGENT = "collie-research-fetch/0.1 (academic research; polite, cached)"
MODEL = "openai/gpt-oss-20b"
URL = "https://openrouter.ai/api/v1/chat/completions"
_PROVIDER = {"order": ["deepinfra/bf16"], "allow_fallbacks": False, "quantizations": ["bf16"]}
_MAX_BODY = 1_000_000
_MAX_JOURNAL = 8192
_LOCK_TYPE = type(threading.Lock())


class OneShotRefusal(RuntimeError):
    """A request was refused without making another physical dispatch."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise OneShotRefusal("request JSON contains duplicate keys")
        result[key] = value
    return result


def _contains_at(value: object) -> bool:
    if type(value) is str:
        return "@" in value
    if type(value) is list:
        return any(_contains_at(item) for item in value)
    if type(value) is dict:
        return any(_contains_at(key) or _contains_at(item) for key, item in value.items())
    return False


def _validate(request: httpx.Request) -> None:
    if type(request) is not httpx.Request or request.method != "POST" or str(request.url) != URL:
        raise OneShotRefusal("request is not the pinned HTTPS endpoint")
    if request.headers.get("user-agent") != USER_AGENT:
        raise OneShotRefusal("research user agent differs")
    if any("@" in value for value in request.headers.values()):
        raise OneShotRefusal("request headers may contain an email address")
    try:
        # The original SDK constructs an already-buffered JSON request. Do not
        # consume an arbitrary streaming body before its size is known.
        body = request.content
        if len(body) > _MAX_BODY:
            raise OneShotRefusal("request body exceeds its bound")
        parsed = json.loads(body, object_pairs_hook=_unique, parse_float=Decimal,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError, httpx.RequestNotRead):
        raise OneShotRefusal("request body is not valid bounded JSON") from None
    if type(parsed) is not dict or set(parsed) != {"model", "messages", "temperature", "provider"}:
        raise OneShotRefusal("request fields differ from original decoding")
    temperature = parsed["temperature"]
    if (parsed["model"] != MODEL or type(temperature) not in (int, Decimal) or temperature != 0
            or type(parsed["provider"]) is not dict or parsed["provider"] != _PROVIDER
            or type(parsed["provider"].get("allow_fallbacks")) is not bool):
        raise OneShotRefusal("request model, provider, precision or decoding differs")
    messages = parsed["messages"]
    if (type(messages) is not list or len(messages) != 1 or type(messages[0]) is not dict
            or set(messages[0]) != {"role", "content"} or messages[0]["role"] != "user"
            or type(messages[0]["content"]) is not str or _contains_at(parsed)):
        raise OneShotRefusal("request message is invalid or may contain an email address")


def _journal(fd: int, expected_identity: tuple[int, int], expected_size: int, event: dict) -> int:
    before = os.fstat(fd)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600 or (before.st_dev, before.st_ino) != expected_identity
            or before.st_size != expected_size):
        raise OneShotRefusal("private attempt journal identity or mode differs")
    raw = (json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    offset = 0
    while offset < len(raw):
        count = os.write(fd, raw[offset:])
        if count <= 0:
            raise OneShotRefusal("private attempt journal write did not progress")
        offset += count
    os.fsync(fd)
    after = os.fstat(fd)
    if ((after.st_dev, after.st_ino) != expected_identity or after.st_nlink != 1
            or after.st_uid != os.geteuid() or stat.S_IMODE(after.st_mode) != 0o600
            or after.st_size != expected_size + len(raw)):
        raise OneShotRefusal("private attempt journal changed")
    return after.st_size


def reservation_bytes(selection_sha256: str) -> bytes:
    """Canonical synthetic/real intent identity; the hold is not a charge bound."""
    if type(selection_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", selection_sha256) is None:
        raise OneShotRefusal("selection SHA256 is invalid")
    record = {"event": "reserved", "attempt_limit": 1, "selection_sha256": selection_sha256,
              "provisional_hold_usd": "0.10", "hold_is_proven_maximum": False}
    return (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


class OnePhysicalAttempt(httpx.BaseTransport):
    """Fence one cooperating process; an unknown charge remains unresolved."""

    def __init__(self, inner: httpx.BaseTransport, journal_fd: int, *, selection_sha256: str,
                 stop_after_utc: datetime | None = None) -> None:
        if not isinstance(inner, httpx.BaseTransport) or type(journal_fd) is not int:
            raise OneShotRefusal("an HTTPX transport and private journal are required")
        if stop_after_utc is not None and (type(stop_after_utc) is not datetime or stop_after_utc.tzinfo is not timezone.utc):
            raise OneShotRefusal("attempt deadline must be an exact UTC datetime")
        expected = reservation_bytes(selection_sha256)
        info = os.fstat(journal_fd)
        flags = fcntl.fcntl(journal_fd, fcntl.F_GETFL)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or not (flags & os.O_APPEND)
                or flags & os.O_ACCMODE != os.O_RDWR or info.st_size > _MAX_JOURNAL):
            raise OneShotRefusal("private attempt journal is unsafe")
        try:
            fcntl.flock(journal_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OneShotRefusal("another process holds the private attempt journal") from None
        try:
            raw = os.pread(journal_fd, _MAX_JOURNAL + 1, 0)
            after = os.fstat(journal_fd)
            if (raw != expected or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                    != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)):
                raise OneShotRefusal("private reservation is changed or has already been used")
        except BaseException:
            fcntl.flock(journal_fd, fcntl.LOCK_UN)
            raise
        self._inner = inner
        self._journal_fd = journal_fd
        self._journal_identity = (info.st_dev, info.st_ino)
        self._journal_size = len(expected)
        self._lock = threading.Lock()
        self._used = False
        self._closed = False
        self._stop_after_utc = stop_after_utc

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if type(self._lock) is not _LOCK_TYPE:
            raise OneShotRefusal("attempt lock differs")
        with self._lock:
            if self._used or self._closed:
                raise OneShotRefusal("the single physical attempt has already been consumed")
            if self._stop_after_utc is not None and datetime.now(timezone.utc) >= self._stop_after_utc:
                raise OneShotRefusal("the single-attempt authorization deadline has passed")
            _validate(request)
            # Mark the object used even if journal persistence fails: do not
            # silently try again after an indeterminate local failure.
            self._used = True
            self._journal_size = _journal(self._journal_fd, self._journal_identity, self._journal_size,
                                          {"event": "physical_request_intent", "attempt_limit": 1,
                                           "provisional_hold_usd": "0.10", "hold_is_proven_maximum": False})
            try:
                response = self._inner.handle_request(request)
            except Exception as exc:
                try:
                    self._journal_size = _journal(self._journal_fd, self._journal_identity, self._journal_size,
                                                  {"event": "physical_request_failure", "error_type": type(exc).__name__,
                                                   "charge": "unknown"})
                except Exception:
                    pass
                raise OneShotRefusal("the single physical attempt failed; charge is unknown") from None
            if type(response) is not httpx.Response or not 100 <= response.status_code <= 599:
                raise OneShotRefusal("returned transport response is invalid; charge is unknown")
            self._journal_size = _journal(self._journal_fd, self._journal_identity, self._journal_size,
                                          {"event": "physical_response_status", "http_status": response.status_code,
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
