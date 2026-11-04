"""Prospective, single-physical-attempt continuation candidate.

This entry point is disabled until a pushed amendment names the exact source,
tests, transport, cache and private selection identities, and a separate remote
verification record matches. It preserves original reading/response files, skips
completed and orphaned item/sample pairs, writes only a new private sidecar,
and uses the original model/prompt/decoding with at most one physical request.
The original ledger and spend/invocation logs are appended by the frozen reader;
new cache entries may be created but never overwrite an existing entry.

The owner explicitly accepted the disclosed spending/checkpoint risks. The
single $0.10 provisional hold is not a proven billable maximum, prior provider
charges and OpenRouter account settings remain unknown, and the F1 reader still
enforces its stricter $200 operational study cap. A different process can bypass
local locks, same-user/mount races remain, and a returned response or crash can
leave an indeterminate private sidecar. This is not a guarantee of the owner's
$10/$225 limits, a completed run, or permission to rerun the evaluator or read
sealed outcomes. Never run it before its exact prospective registration.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import fcntl
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


_MAX_CHECKPOINT = 64_000_000
_MAX_ROWS = 20_000
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_ITEM = re.compile(r"[A-Za-z0-9_.:-]{1,256}", re.ASCII)
_WORKSPACE = "/home/noctis/GitHub/COLLIE-coling"
"""The registered spelling of the study worktree: the one the original runs used
and that the frozen reader's shared-roots anchor pins. The follow-up session's
``/data/noctis/GitHub-Data/COLLIE-coling`` spelling names the same directory
(same device and inode), but the frozen ``check_roots`` compares resolved path
strings, so the continuation must run from the registered spelling."""
_PRIVATE = "/data/noctis/GitHub-Data/COLLIE/owner_review/14_2026-10-29_execution"
_SELECTION_SHA = "5c8b5f558be8b1f6d8dd124bc306232ceec89a968634fe9bc78c92d2f4ca2475"
_PLAN_SHA = "2bf32748015d21d891b661da1149aef5dd7aa7dce7af61b83a70b30d4da7ffd4"
_BACKUP_COMMIT = "6d39ce603c8ba5efda3c19d29adc1c505ac09b4c"
_BACKUP_CODE_SHA = "12947a37cad865ec8b72ea781bd08ff40a04a64b9efa7e6db8b08de198c32e51"
_BACKUP_VERIFICATION_SHA = "a731fbf1c715d561067c3cd9b9b02698b785858b903128ee83102411780ddf4f"
_PREFIX_SHA = "806443831e4748f8f421d83661ffd063dc355dfb0fa2cb82e96fbaf6dfa00953"
_PREFIX_BYTES = 241581
_READ_SHA = "54d171783601e72994f960cbe7b5adba157f6061ba3c9a1da30fd23e23be244f"
_LAUNCH_SHA = "db06bf2900f149e90c97155c7d4060d40cf21b5aa8ca92c234768022181298d5"
_AUTHORITY_BOUND = datetime(2027, 1, 4, 23, 59, 59, tzinfo=timezone.utc)
"""A structural outer bound only: the owner's working completion target. The
original 24-hour delegation expired on 2026-10-30, so any paid dispatch after
that date additionally requires a separately recorded owner renewal; the fresh
key-status check below forces the dispatch chain to run within 300 seconds of
that renewal."""
_DEADLINE = _AUTHORITY_BOUND
_KEY_LIMIT_CEILING = Decimal("250")
"""The provider-reported limit of the owner-installed replacement key of
4 November 2026 (stated to expire in about ten days). The earlier key's
owner-stated ceiling was $225; the A2 model cap, the $225 protocol study
ceiling and the frozen reader's stricter $200 check are unchanged."""
_STAGE_NAME = "OSS_ONE_SHOT_STAGE"


class ResumeRefusal(RuntimeError):
    """The one-shot continuation cannot safely proceed."""


@dataclass(frozen=True, slots=True)
class CheckpointIndex:
    completed: frozenset[tuple[str, int]]
    orphaned: frozenset[tuple[str, int]]


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResumeRefusal("duplicate checkpoint JSON key")
        result[key] = value
    return result


def _json_rows(raw: bytes) -> list[dict]:
    if type(raw) is not bytes or len(raw) > _MAX_CHECKPOINT:
        raise ResumeRefusal("checkpoint bytes are outside the bound")
    if not raw:
        return []
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise ResumeRefusal("checkpoint JSONL is incomplete")
    lines = raw[:-1].split(b"\n")
    if len(lines) > _MAX_ROWS or any(not line.strip() for line in lines):
        raise ResumeRefusal("checkpoint JSONL has blank or too many rows")
    result = []
    for line in lines:
        try:
            row = json.loads(line, object_pairs_hook=_unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        except (ValueError, UnicodeError, RecursionError):
            raise ResumeRefusal("checkpoint JSONL is invalid") from None
        if type(row) is not dict:
            raise ResumeRefusal("checkpoint JSONL row is not an object")
        result.append(row)
    return result


def _pair(row: dict) -> tuple[str, int]:
    item, sample = row.get("item_id"), row.get("sample")
    if (type(item) is not str or _ITEM.fullmatch(item) is None or type(sample) is not int
            or not 0 <= sample < 1000):
        raise ResumeRefusal("checkpoint item/sample identity is invalid")
    return item, sample


def index_checkpoint(readings: bytes, responses: bytes, *, expected_readings_sha256: str,
                     expected_responses_sha256: str, expected_reading_count: int) -> CheckpointIndex:
    """Extract only item/sample identities; never return reading or response values."""
    if (type(expected_readings_sha256) is not str or type(expected_responses_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_readings_sha256) is None
            or re.fullmatch(r"[0-9a-f]{64}", expected_responses_sha256) is None
            or type(expected_reading_count) is not int or expected_reading_count < 0):
        raise ResumeRefusal("checkpoint identity is invalid")
    if (type(readings) is not bytes or type(responses) is not bytes
            or sha256(readings).hexdigest() != expected_readings_sha256
            or sha256(responses).hexdigest() != expected_responses_sha256):
        raise ResumeRefusal("checkpoint byte identity differs")
    reading_rows, response_rows = _json_rows(readings), _json_rows(responses)
    completed: set[tuple[str, int]] = set()
    for row in reading_rows:
        pair = _pair(row)
        if pair in completed:
            raise ResumeRefusal("checkpoint has a duplicate completed pair")
        completed.add(pair)
    if len(completed) != expected_reading_count:
        raise ResumeRefusal("checkpoint reading count differs")
    response_keys = set()
    attempted = set()
    for row in response_rows:
        pair = _pair(row)
        attempt = row.get("attempt")
        if type(attempt) is not int or attempt not in (0, 1) or (*pair, attempt) in response_keys:
            raise ResumeRefusal("checkpoint response attempt is invalid or duplicated")
        response_keys.add((*pair, attempt))
        attempted.add(pair)
    return CheckpointIndex(frozenset(completed), frozenset(attempted - completed))


def filtered_read_items(read_module, reader, items, *, samples: int, rows: list, index: CheckpointIndex):
    """Use F1's reader only for assigned pairs with no historical output or orphan."""
    if (type(samples) is not int or samples < 1 or type(rows) is not list
            or type(index) is not CheckpointIndex):
        raise ResumeRefusal("filtered reading arguments are invalid")
    expected = {(item.item_id, sample) for item in items for sample in range(samples)}
    if (len(expected) != len(items) * samples or not index.completed <= expected
            or not index.orphaned <= expected or index.completed & index.orphaned):
        raise ResumeRefusal("historical item/sample identities differ from the assigned run")
    try:
        for item in items:
            for sample in range(samples):
                if (item.item_id, sample) in index.completed or (item.item_id, sample) in index.orphaned:
                    continue
                rows.append(reader.read(item, sample))
    except (read_module.SpendCapReached, read_module.CallCapReached) as exc:
        return rows, f"aborted: {exc}"
    except read_module.ServedModelMismatch as exc:
        return rows, f"aborted: served by another model or provider: {exc}"
    # This output is only a continuation sidecar, never a completed original run.
    return rows, "partial: one-shot continuation sidecar"


def _write_all(fd: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        count = os.write(fd, raw[offset:])
        if count <= 0:
            raise ResumeRefusal("sidecar write did not progress")
        offset += count


def _exclusive(parent: int, name: str, raw: bytes) -> None:
    fd = os.open(name, _CREATE, 0o600, dir_fd=parent)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ResumeRefusal("new sidecar file is unsafe")
        _write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(parent)


def _jsonl(rows: list) -> bytes:
    if type(rows) is not list or len(rows) > _MAX_ROWS:
        raise ResumeRefusal("sidecar row count is invalid")
    try:
        raw = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
                       for row in rows)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ResumeRefusal("sidecar rows cannot be encoded") from None
    if len(raw) > _MAX_CHECKPOINT:
        raise ResumeRefusal("sidecar bytes exceed the bound")
    return raw


def _validate_sidecar_rows(index: CheckpointIndex, rows: list, responses: list) -> None:
    if type(index) is not CheckpointIndex or type(rows) is not list or type(responses) is not list:
        raise ResumeRefusal("sidecar row identities are invalid")
    protected = index.completed | index.orphaned
    seen_readings = set()
    seen_responses = set()
    for row in rows:
        if type(row) is not dict:
            raise ResumeRefusal("sidecar reading is not an object")
        pair = _pair(row)
        if pair in protected or pair in seen_readings:
            raise ResumeRefusal("sidecar would duplicate a protected reading")
        seen_readings.add(pair)
    for row in responses:
        if type(row) is not dict:
            raise ResumeRefusal("sidecar response is not an object")
        pair, attempt = _pair(row), row.get("attempt")
        if (pair in protected or type(attempt) is not int or attempt not in (0, 1)
                or (*pair, attempt) in seen_responses):
            raise ResumeRefusal("sidecar would duplicate a protected response")
        seen_responses.add((*pair, attempt))


def write_private_sidecar(stage_fd: int, rows: list, responses: list, *, selection_sha256: str) -> dict:
    """Write non-authoritative continuation files exclusively to a new private stage."""
    info = os.fstat(stage_fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or type(selection_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", selection_sha256) is None):
        raise ResumeRefusal("sidecar directory or selection identity differs")
    reading_bytes, response_bytes = _jsonl(rows), _jsonl(responses)
    _exclusive(stage_fd, "readings.jsonl", reading_bytes)
    _exclusive(stage_fd, "responses.jsonl", response_bytes)
    manifest = {"scope": "non-authoritative-one-shot-sidecar", "selection_sha256": selection_sha256,
                "complete": False, "original_run_closed": False, "new_reading_rows": len(rows),
                "new_response_rows": len(responses), "readings_sha256": sha256(reading_bytes).hexdigest(),
                "responses_sha256": sha256(response_bytes).hexdigest()}
    _exclusive(stage_fd, "sidecar_manifest.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    return manifest


def _decode_object(raw: bytes) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError):
        raise ResumeRefusal("metadata JSON is invalid") from None
    if type(value) is not dict:
        raise ResumeRefusal("metadata JSON is not an object")
    return value


def _open_absolute(path: str, stack: ExitStack) -> int:
    if type(path) is not str or not path.startswith("/") or any(part in {"", ".", ".."} for part in path.split("/")[1:]):
        raise ResumeRefusal("directory path is invalid")
    fd = os.open("/", _DIR)
    stack.callback(os.close, fd)
    for part in path.split("/")[1:]:
        fd = os.open(part, _DIR, dir_fd=fd)
        stack.callback(os.close, fd)
    return fd


def _descend(fd: int, parts: tuple[str, ...], stack: ExitStack) -> int:
    for part in parts:
        fd = os.open(part, _DIR, dir_fd=fd)
        stack.callback(os.close, fd)
    return fd


def _regular(parent: int, name: str, limit: int, *, private: bool = False) -> os.stat_result:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
            or info.st_size > limit or (private and stat.S_IMODE(info.st_mode) & 0o077)):
        raise ResumeRefusal("file identity, ownership, links, mode or size differs")
    return info


def _read_safe(parent: int, name: str, limit: int, *, private: bool = False) -> bytes:
    before = _regular(parent, name, limit, private=private)
    fd = os.open(name, _READ, dir_fd=parent)
    with os.fdopen(fd, "rb") as f:
        opened = os.fstat(f.fileno())
        raw = f.read(limit + 1)
        after = os.fstat(f.fileno())
    visible = _regular(parent, name, limit, private=private)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if (len(raw) != before.st_size or identity(before) != identity(opened)
            or identity(opened) != identity(after) or identity(after) != identity(visible)):
        raise ResumeRefusal("file changed while being read")
    return raw


def _check_environment() -> None:
    # Check only named controls; never print or dump the process environment.
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID",
                 "OPENAI_WEBHOOK_SECRET", "OPENAI_BASE_URL", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        if os.environ.get(name):
            raise ResumeRefusal("a forbidden credential or proxy override is present")


def _registered_files() -> tuple[tuple[str, str], ...]:
    return (
        ("analysis/coling/followup/__init__.py", "Package initializer SHA256"),
        ("analysis/coling/followup/oss_one_shot_resume.py", "Resume source SHA256"),
        ("analysis/coling/followup/test_oss_one_shot_resume.py", "Resume fixture tests SHA256"),
        ("analysis/coling/followup/oss_one_shot_cache.py", "Cache source SHA256"),
        ("analysis/coling/followup/test_oss_one_shot_cache.py", "Cache fixture tests SHA256"),
        ("analysis/coling/followup/oss_one_shot_transport.py", "Transport source SHA256"),
        ("analysis/coling/followup/test_oss_one_shot_transport.py", "Transport fixture tests SHA256"),
    )


def _check_recent_key_status(raw: bytes, expected_sha256: str, now: datetime) -> None:
    if (type(raw) is not bytes or type(expected_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or sha256(raw).hexdigest() != expected_sha256
            or type(now) is not datetime or now.tzinfo is not timezone.utc):
        raise ResumeRefusal("recent key status identity or clock differs")
    rows = _json_rows(raw)
    if (len(rows) != 3 or [row.get("event") for row in rows] != ["reserved", "request_intent", "result"]
            or rows[0].get("reserved_usd") != "0.10"):
        raise ResumeRefusal("recent key status is incomplete")
    result = rows[-1]
    names = ("limit_usd", "usage_usd", "limit_remaining_usd")
    if any(type(result.get(key)) is not str for key in names):
        raise ResumeRefusal("recent key status amounts are invalid")
    try:
        stamp = datetime.fromisoformat(result["timestamp_utc"])
        limit, usage, remaining = (Decimal(result[key]) for key in names)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise ResumeRefusal("recent key status values are invalid") from None
    if (stamp.tzinfo is None or stamp.utcoffset() != timedelta(0) or not 0 <= (now - stamp).total_seconds() <= 300
            or result.get("http_status") != 200 or result.get("metadata_valid") is not True
            or any(not value.is_finite() or value < 0 for value in (limit, usage, remaining))
            or limit > _KEY_LIMIT_CEILING or usage > limit or remaining < Decimal("0.10")
            or abs((limit - usage) - remaining) > Decimal("0.000001")):
        raise ResumeRefusal("recent key headroom or status is insufficient")


def _verify_registration() -> dict:
    """Check pushed A4 identities before any checkpoint content or credential read."""
    if datetime.now(timezone.utc) >= _DEADLINE:
        raise ResumeRefusal("the conservative delegation deadline has passed")
    _check_environment()
    env = {"HOME": "/tmp/opencode", "PATH": "/usr/bin:/bin", "GIT_TERMINAL_PROMPT": "0"}
    paths = ["analysis/coling/plan/PLAN.md", *[path for path, _ in _registered_files()]]
    shared = ["analysis/__init__.py", "analysis/coling/__init__.py", "analysis/commitment/__init__.py",
              "analysis/real_content_pilot/__init__.py", "analysis/coling/read.py", "analysis/coling/launch.py",
              "analysis/commitment/endpoints.py", "analysis/real_content_pilot/transport.py",
              "collie/__init__.py", "collie/contracts.py", "collie/llm/__init__.py", "collie/llm/client.py",
              "collie/llm/cache.py", "collie/llm/ledger.py"]
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_WORKSPACE, env=env,
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        tracking = subprocess.run(["git", "rev-parse", "refs/remotes/origin/followup/coling-2027"],
                                  cwd=_WORKSPACE, env=env, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=_WORKSPACE, env=env,
                                capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        subprocess.run(["git", "merge-base", "--is-ancestor", _BACKUP_COMMIT, "HEAD"], cwd=_WORKSPACE,
                       env=env, capture_output=True, timeout=10, check=True)
        for extra in ([], ["--cached"]):
            subprocess.run(["git", "diff", *extra, "--quiet", "HEAD", "--", *paths, *shared],
                           cwd=_WORKSPACE, env=env, capture_output=True, timeout=10, check=True)
        subprocess.run(["git", "diff", "--quiet", "coling-f1", "HEAD", "--", *shared], cwd=_WORKSPACE,
                       env=env, capture_output=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        raise ResumeRefusal("registered Git or frozen-source identity cannot be verified") from None
    if head != tracking or branch != "followup/coling-2027" or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise ResumeRefusal("registered branch or tracking commit differs")
    with ExitStack() as stack:
        workspace = _open_absolute(_WORKSPACE, stack)
        coling = _descend(workspace, ("analysis", "coling"), stack)
        plan_dir = _descend(coling, ("plan",), stack)
        followup = _descend(coling, ("followup",), stack)
        private = _open_absolute(_PRIVATE, stack)
        plan = _read_safe(plan_dir, "PLAN.md", 1_000_000)
        if len(plan) < _PREFIX_BYTES or sha256(plan[:_PREFIX_BYTES]).hexdigest() != _PREFIX_SHA:
            raise ResumeRefusal("registered plan prefix differs")
        block = plan.split(b"### A4. One-physical-attempt original continuation")
        if len(block) != 2 or f"One-shot selection SHA256: `{_SELECTION_SHA}`".encode() not in block[1]:
            raise ResumeRefusal("pushed A4 does not name the selection")
        raw_files = {}
        for path, label in _registered_files():
            raw = _read_safe(followup, path.rsplit("/", 1)[1], 1_000_000)
            if f"{label}: `{sha256(raw).hexdigest()}`".encode() not in block[1]:
                raise ResumeRefusal("pushed A4 does not name an exact implementation identity")
            raw_files[path] = raw
        try:
            if not os.path.samefile(__file__, os.path.join(_WORKSPACE, "analysis/coling/followup/oss_one_shot_resume.py")):
                raise ResumeRefusal("running continuation module differs")
        except OSError:
            raise ResumeRefusal("running continuation module identity is unavailable") from None
        backup_raw = _read_safe(followup, "oss_checkpoint_backup.py", 1_000_000)
        if sha256(backup_raw).hexdigest() != _BACKUP_CODE_SHA:
            raise ResumeRefusal("registered backup helper differs")
        for name, wanted in (("read.py", _READ_SHA), ("launch.py", _LAUNCH_SHA)):
            raw = _read_safe(coling, name, 1_000_000)
            if sha256(raw).hexdigest() != wanted:
                raise ResumeRefusal("frozen original source differs")
        selection_raw = _read_safe(private, "OSS_ONE_SHOT_SELECTION_PRIVATE.json", 1_000_000, private=True)
        if sha256(selection_raw).hexdigest() != _SELECTION_SHA:
            raise ResumeRefusal("private selection identity differs")
        verification_raw = _read_safe(private, "OSS_CHECKPOINT_BACKUP_VERIFICATION_PRIVATE.json", 1_000_000, private=True)
        if sha256(verification_raw).hexdigest() != _BACKUP_VERIFICATION_SHA:
            raise ResumeRefusal("backup verification identity differs")
        a4_raw = _read_safe(private, "A4_ONESHOT_GIT_VERIFIED_PRIVATE.json", 1_000_000, private=True)
        budget_raw = _read_safe(private, "EXECUTION_MANIFEST_DRAFT.json", 1_000_000)
    for path, raw in [(paths[0], plan), *raw_files.items()]:
        try:
            committed = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=_WORKSPACE, env=env,
                                       capture_output=True, timeout=10, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            raise ResumeRefusal("a registered file is absent from the commit") from None
        if committed != raw:
            raise ResumeRefusal("a registered file differs from its committed blob")
    a4 = _decode_object(a4_raw)
    if a4.get("commit") != head or a4.get("remote_commit_verified") is not True or a4.get("user_agent_verified") is not True:
        raise ResumeRefusal("A4 remote verification differs")
    selected = _decode_object(selection_raw)
    verified = _decode_object(verification_raw)
    budget = _decode_object(budget_raw)
    if (selected.get("launch_plan_sha256") != _PLAN_SHA or type(selected.get("one_physical_attempt_limit")) is not int
            or selected["one_physical_attempt_limit"] != 1
            or selected.get("provisional_attempt_hold_usd") != "0.10"
            or selected.get("provisional_hold_is_proven_maximum") is not False
            or selected.get("owner_selected_model_cap_usd") != "10"
            or selected.get("registered_study_cap_usd") != "225"
            or selected.get("f1_operational_study_cap_usd") != "200"
            or verified.get("source_and_snapshot_hashes_match") is not True):
        raise ResumeRefusal("selection or backup authority differs")
    status_gets = budget.get("verification", {}).get("one_shot_key_status_attempts_reserved")
    status_hold = budget.get("nonfinal_programme_liability_holds", {}).get("one_shot_key_status_get_usd")
    if (type(status_gets) is not int or status_gets not in (1, 2, 3, 4) or type(status_hold) is not str):
        raise ResumeRefusal("one-shot attempt or liability reservations differ")
    try:
        status_hold_amount = Decimal(status_hold)
    except InvalidOperation:
        raise ResumeRefusal("one-shot attempt or liability reservations differ") from None
    if (budget.get("verification", {}).get("a4_git_registration_attempt_slots_reserved") != 20
            or budget.get("verification", {}).get("one_shot_physical_attempts_reserved") != 1
            or budget.get("nonfinal_programme_liability_holds", {}).get("one_shot_original_attempt_usd") != "0.10"
            or not status_hold_amount.is_finite() or status_hold_amount != Decimal("0.10") * status_gets):
        raise ResumeRefusal("one-shot attempt or liability reservations differ")
    status_record = budget.get("one_shot_key_status_preflight", {})
    with ExitStack() as stack:
        private = _open_absolute(_PRIVATE, stack)
        try:
            status_raw = _read_safe(private, "ONE_SHOT_KEY_STATUS_PRIVATE.jsonl", 1_000_000, private=True)
        except FileNotFoundError:
            raise ResumeRefusal("no fresh key status has been recorded for this dispatch") from None
    _check_recent_key_status(status_raw, status_record.get("journal_sha256"), datetime.now(timezone.utc))
    return selected


def _lock_lanes(launch_fd: int, stack: ExitStack) -> None:
    locks = _descend(launch_fd, ("locks",), stack)
    names = {name for name in os.listdir(locks) if re.fullmatch(r"openrouter\.w[0-9]+\.lock", name)}
    expected = {f"openrouter.w{index}.lock" for index in range(8)}
    if names != expected:
        raise ResumeRefusal("OpenRouter lane-lock inventory differs")
    for name in sorted(names):
        fd = os.open(name, _READ, dir_fd=locks)
        stack.callback(os.close, fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ResumeRefusal("lane lock is unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ResumeRefusal("an original lane worker is active") from None


def _check_f1_spend_log_paths(output_fd: int) -> None:
    """Reject links before F1's one-level study-spend log scan."""
    for name in os.listdir(output_fd):
        info = os.stat(name, dir_fd=output_fd, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            raise ResumeRefusal("a study output entry is a link")
        if not stat.S_ISDIR(info.st_mode):
            continue
        fd = os.open(name, _DIR, dir_fd=output_fd)
        try:
            try:
                _regular(fd, "spend_log.jsonl", _MAX_CHECKPOINT)
            except FileNotFoundError:
                pass
        finally:
            os.close(fd)


def _selected_context(selected: dict, stack: ExitStack):
    """Open only the fixed selected run, pinned input and backed-up files."""
    name = selected.get("run")
    if type(name) is not str or re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", name) is None or name in {".", ".."}:
        raise ResumeRefusal("selected run identity is unsafe")
    workspace = _open_absolute(_WORKSPACE, stack)
    private = _open_absolute(_PRIVATE, stack)
    output = _descend(workspace, ("analysis", "coling", "out", "read"), stack)
    local = _descend(workspace, ("results", "coling", "read"), stack)
    launch = _descend(output, ("_launch",), stack)
    _lock_lanes(launch, stack)
    _check_f1_spend_log_paths(output)
    plan_raw = _read_safe(launch, "plan.json", 4_000_000)
    if sha256(plan_raw).hexdigest() != _PLAN_SHA:
        raise ResumeRefusal("pinned launch plan differs")
    plan = _decode_object(plan_raw)
    if (type(plan.get("options")) is not dict or plan["options"].get("out_root") != "analysis/coling/out/read"
            or plan["options"].get("local_root") != "results/coling/read"):
        raise ResumeRefusal("pinned launch roots differ")
    runs = [row for row in plan.get("runs", ()) if type(row) is dict and row.get("run") == name]
    if len(runs) != 1:
        raise ResumeRefusal("selected run is absent or duplicated")
    run = runs[0]
    if (run.get("model") != "gpt-oss-20b" or run.get("track") is not None
            or type(run.get("temperature")) not in (int, float) or run["temperature"] != 0
            or type(run.get("samples")) is not int or run["samples"] < 1
            or type(run.get("allow_test_items")) is not bool
            or type(run.get("cap_usd")) not in (int, float)
            or not math.isfinite(run["cap_usd"]) or run["cap_usd"] <= 0):
        raise ResumeRefusal("selected run condition differs")
    route = plan.get("routes", {}).get("gpt-oss-20b", {})
    if (route.get("model_id") != "openai/gpt-oss-20b" or route.get("provider") != "deepinfra/bf16"
            or route.get("quantization") != "bf16"):
        raise ResumeRefusal("selected model route differs")
    out_run = _descend(output, (name,), stack)
    local_run = _descend(local, (name,), stack)
    snapshot = _descend(private, ("OSS_CHECKPOINT_BACKUP_2026-10-30",), stack)
    if os.fstat(snapshot).st_uid != os.geteuid() or stat.S_IMODE(os.fstat(snapshot).st_mode) != 0o700:
        raise ResumeRefusal("checkpoint snapshot is not private")
    snap_out = _descend(snapshot, ("out", name), stack)
    snap_local = _descend(snapshot, ("local", name), stack)
    checks = ((out_run, snap_out, "readings.jsonl", "readings_sha256"),
              (out_run, snap_out, "run_manifest.json", "manifest_sha256"),
              (out_run, snap_out, "spend_log.jsonl", "spend_log_sha256"),
              (out_run, snap_out, "invocations.jsonl", "invocations_sha256"),
              (local_run, snap_local, "responses.jsonl", "responses_sha256"))
    contents = {}
    for original, saved, filename, field in checks:
        raw = _read_safe(original, filename, _MAX_CHECKPOINT)
        backup_raw = _read_safe(saved, filename, _MAX_CHECKPOINT, private=True)
        if raw != backup_raw or sha256(raw).hexdigest() != selected.get(field):
            raise ResumeRefusal("selected original file differs from its verified snapshot")
        contents[filename] = backup_raw
    manifest = _decode_object(contents["run_manifest.json"])
    if manifest.get("complete") is not False or type(manifest.get("readings")) is not int:
        raise ResumeRefusal("selected original run is no longer partial")
    index = index_checkpoint(contents["readings.jsonl"], contents["responses.jsonl"],
                             expected_readings_sha256=selected["readings_sha256"],
                             expected_responses_sha256=selected["responses_sha256"],
                             expected_reading_count=manifest["readings"])
    spend_rows = _json_rows(contents["spend_log.jsonl"])
    calls = [row for row in spend_rows if row.get("event") == "call"]
    try:
        spent = sum(float(row["usd"]) for row in calls)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ResumeRefusal("selected spend log is invalid") from None
    if len(calls) != selected.get("logged_call_count") or str(spent) != selected.get("logged_spend_usd"):
        raise ResumeRefusal("selected logged calls or spend differ")
    ledger = _read_safe(output, "study_ledger.jsonl", 16_000_000)
    if sha256(ledger).hexdigest() != selected.get("ledger_sha256"):
        raise ResumeRefusal("study ledger changed after selection")
    raw_items = run.get("items")
    if type(raw_items) is not str:
        raise ResumeRefusal("selected item path differs")
    parts = raw_items.split("/")
    if (len(parts) != 5 or tuple(parts[:4]) != ("analysis", "coling", "out", "items")
            or parts[4] in {"", ".", ".."} or re.fullmatch(r"[A-Za-z0-9_.-]+", parts[4]) is None
            or not parts[4].endswith(".jsonl")):
        raise ResumeRefusal("selected input is outside the fixed item scope")
    items_dir = _descend(workspace, tuple(parts[:-1]), stack)
    items_raw = _read_safe(items_dir, parts[-1], _MAX_CHECKPOINT)
    try:
        expected_items_sha = plan["lists"][run["list"]]["sha256"]
    except (KeyError, TypeError):
        raise ResumeRefusal("selected input identity is unavailable") from None
    if sha256(items_raw).hexdigest() != expected_items_sha:
        raise ResumeRefusal("selected item file hash differs")
    try:
        cap = Decimal(selected["proposed_run_cap_usd"])
    except (KeyError, InvalidOperation, TypeError):
        raise ResumeRefusal("selected run cap is invalid") from None
    if not cap.is_finite() or cap <= 0 or cap > Decimal("10") or type(selected.get("logged_call_count")) is not int:
        raise ResumeRefusal("selected run cap or prior call count differs")
    return plan, run, index, items_raw, str(cap), selected["logged_call_count"], private


def _new_stage(parent: int, stack: ExitStack) -> int:
    if os.fstat(parent).st_uid != os.geteuid():
        raise ResumeRefusal("private stage parent is not owned")
    os.mkdir(_STAGE_NAME, 0o700, dir_fd=parent)
    stage = os.open(_STAGE_NAME, _DIR, dir_fd=parent)
    stack.callback(os.close, stage)
    info = os.fstat(stage)
    visible = os.stat(_STAGE_NAME, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(visible.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)):
        raise ResumeRefusal("new private stage identity differs")
    os.fsync(parent)
    return stage


def _pinned_items(read_module, raw: bytes, path: str):
    """Reproduce the selected JSONL loader from already verified input bytes."""
    if not path.endswith(".jsonl"):
        raise ResumeRefusal("selected item format differs")
    try:
        lines = raw.decode("utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()]
        items = [read_module.ReadItem.from_dict(value) for value in values]
    except (ValueError, UnicodeError, TypeError, KeyError, RecursionError):
        raise ResumeRefusal("selected item JSONL is invalid") from None
    ids = [item.item_id for item in items]
    if len(set(ids)) != len(ids):
        raise ResumeRefusal("selected item list contains duplicate IDs")
    return items


def _check_local_budget(read_module, selected: dict, run_cap: str) -> None:
    """Use F1's local list-price ledger; provider liabilities remain unknown."""
    out_root = Path("analysis/coling/out/read")
    held = read_module.held_by_run(out_root)
    name = selected["run"]
    current = held.get(name)
    if (type(current) is not dict or current.get("model") != "gpt-oss-20b" or current.get("open") is not True
            or not math.isfinite(float(current.get("spent_usd", float("nan"))))):
        raise ResumeRefusal("selected run is not open in the local ledger")
    old_cap = Decimal(str(current.get("cap_usd")))
    spent = Decimal(str(current.get("spent_usd")))
    proposed = Decimal(run_cap)
    if (not old_cap.is_finite() or not spent.is_finite() or old_cap < spent or proposed < old_cap
            or proposed < spent + Decimal("0.10")):
        raise ResumeRefusal("selected run cap does not cover the provisional hold")
    other_model = sum(Decimal(str(row["held_usd"])) for key, row in held.items()
                      if key != name and row.get("model") == "gpt-oss-20b")
    other_study = sum(Decimal(str(row["held_usd"])) for key, row in held.items() if key != name)
    if other_model + proposed > Decimal("10") or other_study + proposed + Decimal("0.50") > Decimal("200"):
        raise ResumeRefusal("local model or stricter F1 study cap would be exceeded")


def _install_hooks(read_module, endpoints_module, openai_module, httpx_module, cache_module,
                   transport_module, *, index: CheckpointIndex, stage_fd: int, journal_fd: int,
                   items_raw: bytes, item_path: str, run_name: str):
    """Install the A4 operational changes; tests provide fake providers only."""
    if type(index) is not CheckpointIndex:
        raise ResumeRefusal("checkpoint index is invalid")
    original_cache = read_module.ReadCache
    original_guard = read_module.GuardedTransport
    original_openai = openai_module.OpenAI
    expected_item_sha = sha256(items_raw).hexdigest()

    class PinnedCache(original_cache):
        def _root_name(self):
            if str(self.root) not in ("results/coling/read/cache", cache_module.REAL_ROOT):
                raise ResumeRefusal("F1 cache root differs")
            return cache_module.REAL_ROOT

        def get(self, key):
            return cache_module.get(self._root_name(), key)

        def put(self, key, raw, served=None):
            return cache_module.put(self._root_name(), key, text=raw.text, prompt_tokens=raw.prompt_tokens,
                                    completion_tokens=raw.completion_tokens, total_tokens=raw.total_tokens,
                                    served=served)

    class OneAttemptGuard(original_guard):
        def __init__(self, *args, **kwargs):
            if "max_attempts" in kwargs and kwargs["max_attempts"] != 1:
                raise ResumeRefusal("unexpected F1 retry override")
            kwargs["max_attempts"] = 1
            super().__init__(*args, **kwargs)

        def _log(self, row):
            sanitized = dict(row)
            if "error" in sanitized:
                sanitized["error"] = "details withheld by one-shot guard"
            return super()._log(sanitized)

        def complete_metered(self, *args, **kwargs):
            try:
                return super().complete_metered(*args, **kwargs)
            except (read_module.SpendCapReached, read_module.CallCapReached):
                raise
            except read_module.ServedModelMismatch:
                raise read_module.ServedModelMismatch("one-shot served identity mismatch") from None
            except Exception:
                raise ResumeRefusal("one-shot provider or transport failure; details withheld") from None

    inner = httpx_module.HTTPTransport(verify=True, trust_env=False, retries=0)
    physical = transport_module.OnePhysicalAttempt(inner, journal_fd, selection_sha256=_SELECTION_SHA,
                                                    stop_after_utc=_DEADLINE - timedelta(seconds=10))
    client = httpx_module.Client(transport=physical, trust_env=False, follow_redirects=False, timeout=180.0)

    def pinned_openai(*args, **kwargs):
        if (args or kwargs.get("base_url") != "https://openrouter.ai/api/v1" or kwargs.get("max_retries") != 0
                or "default_headers" in kwargs or "http_client" in kwargs):
            raise ResumeRefusal("F1 client configuration differs")
        kwargs["default_headers"] = {"User-Agent": transport_module.USER_AGENT}
        kwargs["http_client"] = client
        return original_openai(**kwargs)

    def pinned_load(path):
        if str(path) != item_path:
            raise ResumeRefusal("F1 selected input path differs")
        return _pinned_items(read_module, items_raw, item_path)

    def pinned_sha(path):
        if str(path) == item_path:
            return expected_item_sha
        raise ResumeRefusal("F1 requested an unregistered file hash")

    def filtered(reader, items, *, samples=1, rows=None):
        return filtered_read_items(read_module, reader, items, samples=samples,
                                   rows=[] if rows is None else rows, index=index)

    def sidecar(rows, reader, *, out_dir, local_dir, meta, items, samples):
        # F1 writes no original reading/response/manifest in this mode. Its
        # returned ``complete=False`` also prevents closing the original run.
        # The frozen harness passes the plan's RELATIVE roots; the module
        # constants are absolute, so compare on normalized absolute paths.
        expected_out = Path(os.path.abspath(read_module.OUT_ROOT)) / run_name
        expected_local = Path(os.path.abspath(read_module.LOCAL_ROOT)) / run_name
        if (Path(os.path.abspath(out_dir)) != expected_out
                or Path(os.path.abspath(local_dir)) != expected_local
                or Path(out_dir).name != run_name):
            raise ResumeRefusal("F1 output roots or run identity differ")
        del meta, items, samples
        _validate_sidecar_rows(index, rows, reader.responses)
        return write_private_sidecar(stage_fd, rows, reader.responses, selection_sha256=_SELECTION_SHA)

    read_module.ReadCache = PinnedCache
    read_module.GuardedTransport = OneAttemptGuard
    read_module.load_items = pinned_load
    read_module._sha256_file = pinned_sha
    read_module.read_items = filtered
    read_module.write_run = sidecar
    endpoints_module.EMPTY_ECHO_RETRIES = 0
    openai_module.OpenAI = pinned_openai
    return client


def main() -> None:
    if sys.argv[1:] != ["--execute-registered-one-shot"]:
        raise SystemExit("This continuation requires its exact registered execution flag.")
    if os.path.realpath(os.getcwd()) != os.path.realpath(_WORKSPACE):
        raise SystemExit("This continuation must run from the registered study worktree root.")
    try:
        selected = _verify_registration()
        # Imports happen only after the exact committed code and F1 dependencies
        # are checked, before any original checkpoint content is opened.
        import httpx
        import openai
        from analysis.coling import launch, read
        from analysis.commitment import endpoints
        from analysis.coling.followup import oss_one_shot_cache, oss_one_shot_transport

        if httpx.__version__ != "0.28.1" or openai.__version__ != "1.109.1":
            raise ResumeRefusal("HTTPX or OpenAI SDK version differs")
        designated = "/data/noctis/GitHub-Data/COLLIE/cloud_endpoint/openrouter.key"
        if not os.path.samefile(os.path.join(_WORKSPACE, "cloud_endpoint/openrouter.key"), designated):
            raise ResumeRefusal("F1 key-file identity differs")
        with ExitStack() as stack:
            plan, run, index, items_raw, run_cap, prior_calls, private = _selected_context(selected, stack)
            _check_local_budget(read, selected, run_cap)
            stage = _new_stage(private, stack)
            journal = os.open("attempt.journal.jsonl", os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL
                              | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=stage)
            stack.callback(os.close, journal)
            _write_all(journal, oss_one_shot_transport.reservation_bytes(_SELECTION_SHA))
            os.fsync(journal)
            os.fsync(stage)
            client = _install_hooks(read, endpoints, openai, httpx, oss_one_shot_cache, oss_one_shot_transport,
                                    index=index, stage_fd=stage, journal_fd=journal, items_raw=items_raw,
                                    item_path=run["items"], run_name=run["run"])
            stack.callback(client.close)
            args = launch.harness_args(plan, run, "live")
            at = args.index("--spend-cap-usd")
            args[at + 1] = run_cap
            args += ["--model-cap-usd", "10", "--amendment", "A2: prospective gpt-oss cap 10",
                     "--max-physical-calls", str(prior_calls + 1)]
            stdout, stderr = io.StringIO(), io.StringIO()
            result, error_type = None, None
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = read.main(args)
            except Exception as exc:
                error_type = type(exc).__name__
            # Do not persist or print F1 stdout, stderr, exception text, prompts,
            # responses or credentials. The one-shot sidecar and journal remain
            # private; one attempt is never automatically repeated.
            summary = {"scope": "single-attempt-original-continuation", "selection_sha256": _SELECTION_SHA,
                       "f1_return_code": result, "error_type": error_type,
                       "original_run_closed": False, "automatic_retry": False}
            _exclusive(stage, "execution_summary.json", (json.dumps(summary, sort_keys=True, indent=2) + "\n").encode())
    except Exception:
        raise SystemExit("One-shot continuation stopped; review private state before any retry.") from None
    print("One-shot continuation ended; inspect the private journal and sidecar for its recorded outcome.")
    print("No registered evaluator or sealed outcome was read; the original run was not marked complete.")


if __name__ == "__main__":
    main()
