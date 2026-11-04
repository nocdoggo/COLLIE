"""No-overwrite cache candidate for a separately registered original-run step.

This module does not select or run a study request. It accepts only the fixed
original cache root or an explicitly synthetic fixture root; its private helpers
are not a Python security boundary. A real caller must be prospectively named,
hash-pinned and authorized before reading the original cache. Existing cache
files are opened read-only, without following the final link; new entries are
published by a synced exclusive temporary and a non-overwriting hard link.
Unknown temporaries, unsafe links and conflicting existing entries are refused,
not cleaned up or overwritten.

These checks cannot prove mount provenance, exclusive external workers, provider
identity or billing; same-user races and crashes require additional review. A
cache hit alone does not establish a completed reading or repair. Tests use only
invented fixtures and do not read a real cache, credential or sealed outcome.
"""

from __future__ import annotations

from contextlib import ExitStack
from hashlib import sha256
import json
import os
import re
import secrets
import stat


REAL_ROOT = "/data/noctis/GitHub-Data/COLLIE-coling/results/coling/read/cache"
SYNTHETIC_ROOT = re.compile(r"/tmp/opencode/oss-one-shot-cache-[a-z0-9_]{8}/cache", re.ASCII)
KEY = re.compile(r"sha256:([0-9a-f]{64})", re.ASCII)
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_CREATE = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_MAX_BYTES = 8_000_000


class CacheRefusal(RuntimeError):
    """A cache identity or no-overwrite operation could not be established."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CacheRefusal("duplicate cache JSON key")
        result[key] = value
    return result


def _root(root: str, stack: ExitStack) -> int:
    if type(root) is not str or not (root == REAL_ROOT or SYNTHETIC_ROOT.fullmatch(root)):
        raise CacheRefusal("cache root is outside the fixed scope")
    fd = os.open("/", _DIR)
    stack.callback(os.close, fd)
    for part in root.split("/")[1:]:
        fd = os.open(part, _DIR, dir_fd=fd)
        stack.callback(os.close, fd)
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise CacheRefusal("cache root is not owned by the current user")
    if SYNTHETIC_ROOT.fullmatch(root) and stat.S_IMODE(info.st_mode) != 0o700:
        raise CacheRefusal("synthetic cache root is not private")
    return fd


def _key(key: object) -> str:
    if type(key) is not str or (match := KEY.fullmatch(key)) is None:
        raise CacheRefusal("cache key is invalid")
    return match.group(1)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink


def _file_info(parent: int, name: str) -> os.stat_result:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
            or info.st_size > _MAX_BYTES):
        raise CacheRefusal("cache file has unsafe identity, links or size")
    return info


def _shard(root_fd: int, prefix: str, stack: ExitStack, *, create: bool) -> int | None:
    try:
        fd = os.open(prefix, _DIR, dir_fd=root_fd)
    except FileNotFoundError:
        if not create:
            return None
        try:
            os.mkdir(prefix, 0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        else:
            os.fsync(root_fd)
        fd = os.open(prefix, _DIR, dir_fd=root_fd)
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    visible = os.stat(prefix, dir_fd=root_fd, follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(visible.st_mode) or info.st_uid != os.geteuid()
            or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)):
        raise CacheRefusal("cache shard changed or is not owned")
    if any(name.startswith(".oneshot-") and name.endswith(".tmp") for name in os.listdir(fd)):
        raise CacheRefusal("unresolved one-shot cache temporary needs review")
    return fd


def _decode(raw: bytes) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError):
        raise CacheRefusal("cache payload is malformed") from None
    base = {"text", "prompt_tokens", "completion_tokens", "total_tokens"}
    if type(value) is not dict or set(value) not in (base, base | {"served"}):
        raise CacheRefusal("cache payload fields differ")
    if (type(value["text"]) is not str or any(type(value[key]) is not int or not 0 <= value[key] <= 10_000_000
                                             for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
            or ("served" in value and value["served"] is not None and type(value["served"]) is not dict)):
        raise CacheRefusal("cache payload values differ")
    return value


def _read(parent: int, name: str) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
    visible = _file_info(parent, name)
    fd = os.open(name, _READ, dir_fd=parent)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if _identity(before) != _identity(visible):
            raise CacheRefusal("cache file changed before reading")
        raw = handle.read(_MAX_BYTES + 1)
        after = os.fstat(handle.fileno())
    current = _file_info(parent, name)
    if len(raw) != before.st_size or _identity(before) != _identity(after) or _identity(after) != _identity(current):
        raise CacheRefusal("cache file changed during reading")
    return raw, _identity(before)


def get(root: str, key: str) -> dict | None:
    """Read one exact cache key; no directory scan or modification is performed."""
    digest = _key(key)
    with ExitStack() as stack:
        root_fd = _root(root, stack)
        shard = _shard(root_fd, digest[:2], stack, create=False)
        if shard is None:
            return None
        try:
            raw, _ = _read(shard, digest + ".json")
        except FileNotFoundError:
            return None
        return _decode(raw)


def _write_all(fd: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        count = os.write(fd, raw[offset:])
        if count <= 0:
            raise CacheRefusal("cache temporary write did not progress")
        offset += count


def _publish_new(shard: int, temporary: str, name: str) -> None:
    os.link(temporary, name, src_dir_fd=shard, dst_dir_fd=shard, follow_symlinks=False)


def put(root: str, key: str, *, text: str, prompt_tokens: int, completion_tokens: int,
        total_tokens: int, served: dict | None) -> None:
    """Publish one new cache entry without replacing an existing entry."""
    digest = _key(key)
    if served is not None and type(served) is not dict:
        raise CacheRefusal("cache served metadata must be an object or None")
    value = {"text": text, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
             "total_tokens": total_tokens}
    if served:
        value["served"] = served
    try:
        raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise CacheRefusal("cache payload cannot be encoded") from None
    if len(raw) > _MAX_BYTES:
        raise CacheRefusal("cache payload exceeds its bound")
    _decode(raw)
    if os.link not in os.supports_dir_fd or os.link not in os.supports_follow_symlinks:
        raise CacheRefusal("non-overwriting cache publication is unavailable")
    with ExitStack() as stack:
        root_fd = _root(root, stack)
        shard = _shard(root_fd, digest[:2], stack, create=True)
        assert shard is not None
        name = digest + ".json"
        try:
            os.stat(name, dir_fd=shard, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CacheRefusal("existing cache entry is never overwritten")
        temporary = ".oneshot-" + secrets.token_hex(16) + ".tmp"
        fd = os.open(temporary, _CREATE, 0o600, dir_fd=shard)
        stack.callback(os.close, fd)
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino)
        _write_all(fd, raw)
        os.fsync(fd)
        before = os.fstat(fd)
        visible = os.stat(temporary, dir_fd=shard, follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(visible.st_mode)
                or before.st_uid != os.geteuid() or stat.S_IMODE(before.st_mode) != 0o600
                or (before.st_dev, before.st_ino) != identity or (visible.st_dev, visible.st_ino) != identity
                or before.st_nlink != 1 or before.st_size != len(raw)):
            raise CacheRefusal("cache temporary changed before publication")
        os.lseek(fd, 0, os.SEEK_SET)
        checked = bytearray()
        while len(checked) <= _MAX_BYTES:
            chunk = os.read(fd, min(65536, _MAX_BYTES + 1 - len(checked)))
            if not chunk:
                break
            checked.extend(chunk)
        after = os.fstat(fd)
        if bytes(checked) != raw or _identity(before) != _identity(after):
            raise CacheRefusal("cache temporary bytes changed")
        try:
            _publish_new(shard, temporary, name)
        except FileExistsError:
            raise CacheRefusal("concurrent cache entry is never overwritten") from None
        linked = os.stat(name, dir_fd=shard, follow_symlinks=False)
        temp = os.stat(temporary, dir_fd=shard, follow_symlinks=False)
        if (not stat.S_ISREG(linked.st_mode) or not stat.S_ISREG(temp.st_mode)
                or (linked.st_dev, linked.st_ino) != identity or (temp.st_dev, temp.st_ino) != identity
                or linked.st_nlink != 2 or temp.st_nlink != 2):
            raise CacheRefusal("cache publication identity differs")
        os.lseek(fd, 0, os.SEEK_SET)
        published = bytearray()
        while len(published) <= _MAX_BYTES:
            chunk = os.read(fd, min(65536, _MAX_BYTES + 1 - len(published)))
            if not chunk:
                break
            published.extend(chunk)
        published_info = os.fstat(fd)
        if (bytes(published) != raw or (published_info.st_dev, published_info.st_ino) != identity
                or published_info.st_nlink != 2 or stat.S_IMODE(published_info.st_mode) != 0o600):
            raise CacheRefusal("cache publication bytes changed")
        os.fsync(shard)
        # Remove only the exact temporary created by this invocation. If it was
        # replaced or an earlier step failed, leave every artifact for review.
        temp = os.stat(temporary, dir_fd=shard, follow_symlinks=False)
        if not stat.S_ISREG(temp.st_mode) or (temp.st_dev, temp.st_ino) != identity:
            raise CacheRefusal("cache temporary was replaced and was not removed")
        os.unlink(temporary, dir_fd=shard)
        os.fsync(shard)
        final, final_id = _read(shard, name)
        if final != raw or final_id[:2] != identity or sha256(final).digest() != sha256(raw).digest():
            raise CacheRefusal("cache entry changed before confirmation")
