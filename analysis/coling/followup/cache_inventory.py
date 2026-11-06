"""Metadata-only inventory of *synthetic* content-addressed cache fixtures.

This is not a reader for the study cache. A caller must explicitly assert that
the root and every key describe exclusively invented, privately controlled
fixture data. The only accepted root spelling is
``/tmp/opencode/cache-inventory-fixture-XXXXXXXX/cache``, where each ``X`` is
an ASCII lowercase letter, digit, or underscore. Both the fixture directory
and its ``cache`` child must be owned by the effective user and have no
group/other permissions. All other roots, including real cache paths, fail
closed. No path is normalized, expanded, or resolved.

The private fixture must reside on a local, non-network filesystem and must
not contain real study files, hard links to them, or mount aliases. Its owner
must control it throughout the call: a pathname and directory permissions
alone cannot establish file provenance, verify the filesystem's backing, or
protect against a privileged or same-user actor replacing fixture contents.
This candidate must not be used on a real cache, even one copied into the
sandbox.

The root and shard directories are opened without following links. Directory
metadata and search permission are checked only to establish the fixture
scope. For each syntactically valid key, the only file query is a no-follow
metadata lookup of ``<first2>/<key>.json``. File contents are never opened or
read, directory entries are never enumerated, and no files are written.

``present`` means only that this particular metadata lookup found a regular
file. It establishes neither a valid answer nor completion, provider identity,
repair-call availability, or billing. A duplicate is counted for each valid
key occurrence after its first occurrence; each occurrence is independently
queried and classified, because a file can change during an inventory. Invalid
values are never considered duplicates. Results contain aggregate counts only.

Clearing exception links does not erase traceback frames or their locals.
Traceback locals are not a security boundary and can retain caller-supplied
paths or keys; do not disclose them or use this candidate on real data.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import partial
import os
import re
import stat
from typing import NoReturn


_ROOT_PATTERN = re.compile(
    r"/tmp/opencode/cache-inventory-fixture-[a-z0-9_]{8}/cache", re.ASCII
)
_KEY_PATTERN = re.compile(r"[0-9a-f]{64}", re.ASCII)

# These checks do not query the filesystem. Do not silently fall back to a
# path-based implementation on platforms without the required primitives.
_DIRECTORY_FLAGS = (
    getattr(os, "O_PATH", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_SAFE_FILE_OPERATIONS = (
    all(
        hasattr(os, name)
        for name in ("O_PATH", "O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "geteuid")
    )
    and os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.access in os.supports_dir_fd
    and os.access in os.supports_effective_ids
)


class InventoryScopeError(ValueError):
    """The explicitly synthetic fixture could not be established safely."""


def _clear_exception_chain(error: BaseException) -> None:
    # ``from None`` hides context in tracebacks but does not remove the object.
    # Clear both links while catching the public error, then use a bare raise.
    error.__cause__ = None
    error.__context__ = None


def _raise_scope_access_error() -> NoReturn:
    # Clean the error before cleanup can attach it to a later interruption.
    try:
        raise InventoryScopeError("synthetic fixture cannot be safely accessed") from None
    except InventoryScopeError as error:
        _clear_exception_chain(error)
        raise


def _root_parts(path: object) -> tuple[str, ...]:
    # A closed lexical allowlist rejects protected components, traversal,
    # alternate spellings, and arbitrary PathLike hooks before any I/O.
    if type(path) is not str or _ROOT_PATTERN.fullmatch(path) is None:
        raise InventoryScopeError("root is outside the synthetic fixture scope")
    return tuple(path.split("/")[1:])


@dataclass(frozen=True)
class SyntheticFixtureRoot:
    """Caller attestation of an exclusively synthetic, controlled fixture.

    ``path`` is a fixed, absolute string in the namespace documented above.
    This type does not prove the provenance of the fixture's contents.
    """

    path: str

    def __post_init__(self) -> None:
        try:
            _root_parts(self.path)
        except InventoryScopeError as error:
            _clear_exception_chain(error)
            raise


@dataclass(frozen=True)
class InventoryCounts:
    """Counts of observations; duplicate occurrences overlap other states.

    ``total == present + missing + errors + invalid``. A repeated valid key
    contributes to ``duplicate_occurrences`` as well as exactly one of
    ``present``, ``missing``, and ``errors`` for that occurrence.
    """

    total: int
    present: int
    missing: int
    errors: int
    invalid: int
    duplicate_occurrences: int


def _require_private_owned_directory(fd: int) -> None:
    metadata = os.fstat(fd)
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise InventoryScopeError("synthetic fixture is not private and owned")


def _close_directory_on_exit(fd: int, _exc_type, error, _traceback) -> bool:
    try:
        os.close(fd)
    except (OSError, ValueError, NotImplementedError):
        if error is None:
            _raise_scope_access_error()
        # Do not replace an exception already unwinding, including cancellation
        # or system exit, with a bounded descriptor-close failure.
    return False


@contextmanager
def _open_fixture_root(parts: tuple[str, ...]):
    if not _SAFE_FILE_OPERATIONS:
        raise InventoryScopeError("safe fixture operations are unavailable")

    with ExitStack() as opened:
        try:
            fd = os.open("/", _DIRECTORY_FLAGS)
            opened.push(partial(_close_directory_on_exit, fd))
            for index, component in enumerate(parts):
                fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=fd)
                opened.push(partial(_close_directory_on_exit, fd))
                if index >= 2:  # The fixture directory and its cache child.
                    _require_private_owned_directory(fd)
            if not os.access(".", os.X_OK, dir_fd=fd, effective_ids=True):
                raise InventoryScopeError("synthetic fixture is not searchable")
        except (OSError, NotImplementedError, TypeError, ValueError):
            _raise_scope_access_error()
        yield fd


def _file_state(root_fd: int, key: str) -> str:
    try:
        shard_fd = os.open(key[:2], _DIRECTORY_FLAGS, dir_fd=root_fd)
    except FileNotFoundError:
        return "missing"
    except (OSError, NotImplementedError, TypeError, ValueError):
        return "errors"

    with ExitStack() as opened:
        opened.push(partial(_close_directory_on_exit, shard_fd))
        try:
            metadata = os.stat(key + ".json", dir_fd=shard_fd, follow_symlinks=False)
        except FileNotFoundError:
            return "missing"
        except (OSError, NotImplementedError, TypeError, ValueError):
            return "errors"
        return "present" if stat.S_ISREG(metadata.st_mode) else "errors"


def inventory_cache_files(
    *, root: SyntheticFixtureRoot, keys: list[object] | tuple[object, ...]
) -> InventoryCounts:
    """Count metadata observations for caller-supplied, already-computed keys.

    Only plain lists or tuples are accepted, so this helper does not invoke an
    arbitrary lazy key source. A key is valid only if it is a plain string of
    exactly 64 lowercase ASCII hexadecimal characters. Invalid keys do not
    cause file lookups. A missing root or unsafe root permissions raise
    ``InventoryScopeError`` rather than being reported as missing cache files.
    """

    try:
        return _inventory_cache_files(root=root, keys=keys)
    except (InventoryScopeError, TypeError) as error:
        _clear_exception_chain(error)
        raise
    except OSError:
        # Any otherwise uncaught OS error also fails closed without retaining
        # it in the public error.
        _raise_scope_access_error()


def _inventory_cache_files(
    *, root: SyntheticFixtureRoot, keys: list[object] | tuple[object, ...]
) -> InventoryCounts:
    if type(root) is not SyntheticFixtureRoot:
        raise InventoryScopeError("an explicit synthetic fixture root is required")
    parts = _root_parts(root.path)
    if type(keys) not in (list, tuple):
        raise TypeError("keys must be a plain list or tuple of precomputed values")
    items = tuple(keys)

    present = missing = errors = invalid = duplicates = 0
    seen: set[str] = set()
    with _open_fixture_root(parts) as root_fd:
        for key in items:
            if type(key) is not str or _KEY_PATTERN.fullmatch(key) is None:
                invalid += 1
                continue
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)

            state = _file_state(root_fd, key)
            if state == "present":
                present += 1
            elif state == "missing":
                missing += 1
            else:
                errors += 1

    return InventoryCounts(
        total=len(items),
        present=present,
        missing=missing,
        errors=errors,
        invalid=invalid,
        duplicate_occurrences=duplicates,
    )
