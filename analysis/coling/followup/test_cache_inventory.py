"""Synthetic-only tests; no study cache, input, endpoint, or credential use."""

from asyncio import CancelledError as AsyncCancelledError
import builtins
from concurrent.futures import CancelledError as FuturesCancelledError
from dataclasses import asdict
import io
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace

import pytest

from analysis.coling.followup import cache_inventory as inventory


_PREFIX = "cache-inventory-fixture-"
_TEMP_PARENT = "/tmp/opencode"
_LEXICAL_ROOT = "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache"


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network access is prohibited")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    yield
    assert not attempts


@pytest.fixture
def fixture_root():
    # Only this freshly created, private temporary tree contains test files.
    with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=_TEMP_PARENT) as parent:
        root = Path(parent) / "cache"
        root.mkdir(mode=0o700)
        yield root


def _root(path):
    return inventory.SyntheticFixtureRoot(str(path))


def _invented_file(root, key):
    shard = root / key[:2]
    shard.mkdir(mode=0o700, exist_ok=True)
    return shard / (key + ".json")


def _counts(root, keys):
    return inventory.inventory_cache_files(root=_root(root), keys=keys)


def _assert_no_synthetic_failures_in_chain(error, failure, origin, synthetic_path):
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert current is not failure and current is not origin
        assert synthetic_path not in str(current)
        if current.__context__ is not None:
            pending.append(current.__context__)
        if current.__cause__ is not None:
            pending.append(current.__cause__)


def test_exact_state_counts_include_each_duplicate_observation(fixture_root, monkeypatch):
    present, missing, denied = "a" * 64, "b" * 64, "c" * 64
    _invented_file(fixture_root, present).write_text("invented", encoding="utf-8")
    _invented_file(fixture_root, missing)
    _invented_file(fixture_root, denied)
    attempts = []
    original_stat = os.stat

    def deny_one_file(path, *args, **kwargs):
        if path == denied + ".json":
            attempts.append(True)
            raise PermissionError("synthetic denial")
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "stat", deny_one_file)
        result = _counts(
            fixture_root,
            [present, present, missing, missing, denied, denied, "bad", None],
        )

    assert asdict(result) == {
        "total": 8,
        "present": 2,
        "missing": 2,
        "errors": 2,
        "invalid": 2,
        "duplicate_occurrences": 3,
    }
    assert len(attempts) == 2  # Duplicates are observed, not assumed cached.
    assert present not in repr(result)
    assert missing not in repr(result)
    assert denied not in repr(result)


def test_invalid_values_never_trigger_file_queries(fixture_root, monkeypatch):
    class StringSubclass(str):
        pass

    invalid = [
        "",
        "bad",
        "bad",  # Invalid values are not counted as duplicate valid keys.
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "a" * 64 + "\n",
        " " + "a" * 64,
        "a" * 64 + ".json",
        "../" + "a" * 64,
        "é" * 64,
        b"a" * 64,
        StringSubclass("a" * 64),
        None,
        12,
        [],
    ]
    original_open = os.open
    opens = []

    def directories_only(path, flags, *args, **kwargs):
        opens.append(path)
        assert path in ("/", "tmp", "opencode", fixture_root.parent.name, "cache")
        return original_open(path, flags, *args, **kwargs)

    def forbidden_stat(*args, **kwargs):
        raise AssertionError("invalid keys must not query file metadata")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", directories_only)
        guarded.setattr(os, "stat", forbidden_stat)
        result = _counts(fixture_root, invalid)

    assert asdict(result) == {
        "total": len(invalid),
        "present": 0,
        "missing": 0,
        "errors": 0,
        "invalid": len(invalid),
        "duplicate_occurrences": 0,
    }
    assert len(opens) == 5


def test_missing_shard_and_missing_file_are_both_missing(fixture_root, monkeypatch):
    absent_shard, absent_file = "d" * 64, "e" * 64
    _invented_file(fixture_root, absent_file)
    original_stat = os.stat
    queries = []

    def observe(path, *args, **kwargs):
        queries.append(path)
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "stat", observe)
        result = _counts(fixture_root, (absent_shard, absent_file))

    assert result.total == result.missing == 2
    assert result.errors == result.present == result.invalid == 0
    assert queries == [absent_file + ".json"]


def test_empty_key_list_still_establishes_fixture(fixture_root):
    result = _counts(fixture_root, [])
    assert asdict(result) == {
        "total": 0,
        "present": 0,
        "missing": 0,
        "errors": 0,
        "invalid": 0,
        "duplicate_occurrences": 0,
    }


@pytest.mark.parametrize(
    "path",
    [
        None,
        1,
        Path(_LEXICAL_ROOT),
        "cache-inventory-fixture-abcdefgh/cache",
        "/tmp/opencode/credentials/cache-inventory-fixture-abcdefgh/cache",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache/reports",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache/.ssh",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache/.aws",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache/../secrets",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache/../cache",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh//cache",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache/",
        "/tmp/opencode/cache-inventory-fixture-abcDefgh/cache",
        "/tmp/opencode/cache-inventory-fixture-abcdefg/cache",
        "/tmp/opencode/cache-inventory-fixture-abcdefgh/cache\n",
    ],
)
def test_prohibited_or_noncanonical_roots_are_rejected_before_io(path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid root caused a filesystem query")

    with monkeypatch.context() as guarded:
        for name in ("open", "stat", "lstat", "fstat", "access"):
            guarded.setattr(os, name, forbidden)
        with pytest.raises(inventory.InventoryScopeError) as error:
            inventory.SyntheticFixtureRoot(path)

    assert str(error.value) == "root is outside the synthetic fixture scope"


def test_synthetic_root_type_and_eager_keys_are_required_before_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected I/O or lazy iteration")

    def lazy_keys():
        forbidden()
        yield "a" * 64

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", forbidden)
        with pytest.raises(inventory.InventoryScopeError):
            inventory.inventory_cache_files(root=_LEXICAL_ROOT, keys=[])
        with pytest.raises(TypeError):
            inventory.inventory_cache_files(
                root=inventory.SyntheticFixtureRoot(_LEXICAL_ROOT), keys=lazy_keys()
            )


def test_root_is_revalidated_even_if_a_caller_bypasses_dataclass_freezing(monkeypatch):
    root = inventory.SyntheticFixtureRoot(_LEXICAL_ROOT)
    object.__setattr__(root, "path", "/tmp/opencode/credentials/cache")

    def forbidden(*args, **kwargs):
        raise AssertionError("escaped root caused I/O")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", forbidden)
        with pytest.raises(inventory.InventoryScopeError):
            inventory.inventory_cache_files(root=root, keys=[])


def test_unavailable_safe_primitives_fail_before_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported primitives caused I/O")

    with monkeypatch.context() as guarded:
        guarded.setattr(inventory, "_SAFE_FILE_OPERATIONS", False)
        guarded.setattr(os, "open", forbidden)
        with pytest.raises(inventory.InventoryScopeError):
            inventory.inventory_cache_files(
                root=inventory.SyntheticFixtureRoot(_LEXICAL_ROOT), keys=[]
            )


def test_missing_root_fails_closed_instead_of_reporting_missing():
    with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=_TEMP_PARENT) as parent:
        missing_root = Path(parent) / "cache"
        with pytest.raises(inventory.InventoryScopeError) as error:
            _counts(missing_root, ["a" * 64])
    assert str(missing_root) not in str(error.value)


@pytest.mark.parametrize(
    ("operation", "error_type"),
    [
        ("open", PermissionError),
        ("fstat", PermissionError),
        ("access", PermissionError),
        ("root_close", PermissionError),
        ("root_close", ValueError),
        ("root_close", NotImplementedError),
        ("shard_close", PermissionError),
        ("shard_close", ValueError),
        ("shard_close", NotImplementedError),
    ],
)
def test_public_scope_error_does_not_retain_path_bearing_failures(
    fixture_root, monkeypatch, operation, error_type
):
    synthetic_path = "/invented-fixture/path-component"
    origin = OSError(5, "invented cause", synthetic_path + "/cause")
    if error_type is PermissionError:
        failure = PermissionError(13, "invented denial", synthetic_path + "/failure")
    else:
        failure = error_type("invented denial " + synthetic_path + "/failure")
    original_open = os.open
    original_close = os.close
    shard_fd = None
    failed_close = False
    key = "a" * 64
    if operation == "shard_close":
        _invented_file(fixture_root, key).write_text("invented", encoding="utf-8")

    def fail(*args, **kwargs):
        raise failure from origin

    def open_fixture(path, flags, *args, **kwargs):
        nonlocal shard_fd
        if operation == "open" and path == fixture_root.parent.name:
            fail()
        fd = original_open(path, flags, *args, **kwargs)
        if operation == "shard_close" and path == key[:2]:
            shard_fd = fd
        return fd

    def close_fixture(fd):
        nonlocal failed_close
        original_close(fd)
        if not failed_close and (operation == "root_close" or fd == shard_fd):
            failed_close = True
            fail()

    with monkeypatch.context() as guarded:
        if operation in ("open", "shard_close"):
            guarded.setattr(os, "open", open_fixture)
        if operation == "fstat":
            guarded.setattr(os, "fstat", fail)
        if operation == "access":
            guarded.setattr(os, "access", fail)
        if operation in ("root_close", "shard_close"):
            guarded.setattr(os, "close", close_fixture)
        with pytest.raises(inventory.InventoryScopeError) as captured:
            _counts(fixture_root, [key] if operation == "shard_close" else [])

    error = captured.value
    assert str(error) == "synthetic fixture cannot be safely accessed"
    assert synthetic_path not in str(error)
    assert error is not failure and error is not origin
    assert error.__context__ is None
    assert error.__cause__ is None
    if operation in ("root_close", "shard_close"):
        assert failed_close


@pytest.mark.parametrize("close_error_type", [ValueError, NotImplementedError])
def test_close_failure_during_scope_failure_does_not_leak(
    fixture_root, monkeypatch, close_error_type
):
    synthetic_path = "/invented-fixture/path-component"
    origin = OSError(5, "invented cause", synthetic_path + "/cause")
    original_open, original_close = os.open, os.close
    closed = []

    def deny_fixture_open(path, flags, *args, **kwargs):
        if path == fixture_root.parent.name:
            raise PermissionError(13, "invented denial", synthetic_path) from origin
        return original_open(path, flags, *args, **kwargs)

    def fail_first_close(fd):
        original_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise close_error_type("invented " + synthetic_path + "/close") from origin

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", deny_fixture_open)
        guarded.setattr(os, "close", fail_first_close)
        with pytest.raises(inventory.InventoryScopeError) as captured:
            _counts(fixture_root, [])

    assert len(closed) == 3
    assert synthetic_path not in str(captured.value)
    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("close_error_type", [ValueError, NotImplementedError])
def test_close_error_remains_safe_in_exception_chains(
    fixture_root, monkeypatch, close_error_type, explicit
):
    original_close = os.close
    failed_close = False

    def fail_first_close(fd):
        nonlocal failed_close
        original_close(fd)
        if not failed_close:
            failed_close = True
            raise close_error_type("invented /invented-fixture/close")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "close", fail_first_close)
        with pytest.raises(RuntimeError) as captured:
            try:
                _counts(fixture_root, [])
            except inventory.InventoryScopeError as error:
                if explicit:
                    raise RuntimeError("invented wrapper") from error
                raise RuntimeError("invented wrapper")

    inner = captured.value.__context__
    assert failed_close
    assert isinstance(inner, inventory.InventoryScopeError)
    assert captured.value.__cause__ is (inner if explicit else None)
    assert inner.__context__ is None
    assert inner.__cause__ is None


@pytest.mark.parametrize("operation", ["root_close", "shard_close"])
@pytest.mark.parametrize(
    "interruption_type",
    [KeyboardInterrupt, SystemExit, AsyncCancelledError, FuturesCancelledError],
)
def test_close_does_not_consume_cancellation_or_system_exit(
    fixture_root, monkeypatch, operation, interruption_type
):
    key = "c" * 64
    if operation == "shard_close":
        _invented_file(fixture_root, key)
    interruption = interruption_type("invented interruption")
    original_close = os.close
    closed = []

    def interrupt_first_close(fd):
        original_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise interruption

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "close", interrupt_first_close)
        with pytest.raises(interruption_type) as captured:
            _counts(fixture_root, [key] if operation == "shard_close" else [])

    assert captured.value is interruption
    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None
    assert len(closed) == (6 if operation == "shard_close" else 5)


@pytest.mark.parametrize("operation", ["root_close", "shard_close"])
@pytest.mark.parametrize("close_error_type", [ValueError, NotImplementedError])
@pytest.mark.parametrize(
    "interruption_type",
    [KeyboardInterrupt, SystemExit, AsyncCancelledError, FuturesCancelledError],
)
def test_close_failure_does_not_mask_an_interruption_from_the_body(
    fixture_root, monkeypatch, operation, close_error_type, interruption_type
):
    key = "d" * 64
    _invented_file(fixture_root, key)
    interruption = interruption_type("invented interruption")
    original_open, original_close = os.open, os.close
    opened, closed = [], []
    shard_fd = None
    failed_close = False

    def record_open(path, flags, *args, **kwargs):
        nonlocal shard_fd
        fd = original_open(path, flags, *args, **kwargs)
        opened.append(fd)
        if path == key[:2]:
            shard_fd = fd
        return fd

    def interrupt_stat(*args, **kwargs):
        raise interruption

    def fail_selected_close(fd):
        nonlocal failed_close
        original_close(fd)
        closed.append(fd)
        selected = (fd == shard_fd) if operation == "shard_close" else (fd != shard_fd)
        if selected and not failed_close:
            failed_close = True
            raise close_error_type("invented /invented-fixture/close")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", record_open)
        guarded.setattr(os, "stat", interrupt_stat)
        guarded.setattr(os, "close", fail_selected_close)
        with pytest.raises(interruption_type) as captured:
            _counts(fixture_root, [key])

    assert captured.value is interruption
    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None
    assert failed_close
    assert len(opened) == 6
    assert sorted(opened) == sorted(closed)


@pytest.mark.parametrize("close_error_type", [ValueError, NotImplementedError])
@pytest.mark.parametrize(
    "interruption_type",
    [KeyboardInterrupt, SystemExit, AsyncCancelledError, FuturesCancelledError],
)
def test_later_close_failure_does_not_mask_an_interrupted_close(
    fixture_root, monkeypatch, close_error_type, interruption_type
):
    interruption = interruption_type("invented interruption")
    original_close = os.close
    closed = []

    def close_with_two_failures(fd):
        original_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise interruption
        if len(closed) == 2:
            raise close_error_type("invented /invented-fixture/close")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "close", close_with_two_failures)
        with pytest.raises(interruption_type) as captured:
            _counts(fixture_root, [])

    assert captured.value is interruption
    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None
    assert len(closed) == 5


@pytest.mark.parametrize("close_error_type", [ValueError, NotImplementedError])
@pytest.mark.parametrize(
    "interruption_type",
    [KeyboardInterrupt, SystemExit, AsyncCancelledError, FuturesCancelledError],
)
def test_interruption_after_close_failure_does_not_expose_failure(
    fixture_root, monkeypatch, close_error_type, interruption_type
):
    synthetic_path = "/invented-fixture/path-component"
    failure = close_error_type("invented " + synthetic_path + "/close")
    origin = OSError(5, "invented cause", synthetic_path + "/cause")
    interruption = interruption_type("invented interruption")
    original_close = os.close
    closed = []

    def close_with_two_failures(fd):
        original_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise failure from origin
        if len(closed) == 2:
            raise interruption

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "close", close_with_two_failures)
        with pytest.raises(interruption_type) as captured:
            _counts(fixture_root, [])

    assert captured.value is interruption
    assert len(closed) == 5
    _assert_no_synthetic_failures_in_chain(captured.value, failure, origin, synthetic_path)


@pytest.mark.parametrize(
    "interruption_type",
    [KeyboardInterrupt, SystemExit, AsyncCancelledError, FuturesCancelledError],
)
def test_interrupted_cleanup_does_not_expose_setup_failure(
    fixture_root, monkeypatch, interruption_type
):
    synthetic_path = "/invented-fixture/path-component"
    failure = PermissionError(13, "invented denial", synthetic_path + "/open")
    origin = OSError(5, "invented cause", synthetic_path + "/cause")
    interruption = interruption_type("invented interruption")
    original_open, original_close = os.open, os.close
    closed = []

    def deny_fixture_open(path, flags, *args, **kwargs):
        if path == fixture_root.parent.name:
            raise failure from origin
        return original_open(path, flags, *args, **kwargs)

    def interrupt_first_close(fd):
        original_close(fd)
        closed.append(fd)
        if len(closed) == 1:
            raise interruption

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", deny_fixture_open)
        guarded.setattr(os, "close", interrupt_first_close)
        with pytest.raises(interruption_type) as captured:
            _counts(fixture_root, [])

    assert captured.value is interruption
    assert len(closed) == 3
    _assert_no_synthetic_failures_in_chain(captured.value, failure, origin, synthetic_path)


@pytest.mark.parametrize("operation", ["root_close", "shard_close"])
def test_handled_caller_interruption_does_not_hide_a_close_failure(
    fixture_root, monkeypatch, operation
):
    key = "e" * 64
    if operation == "shard_close":
        _invented_file(fixture_root, key)
    original_close = os.close
    failed_close = False

    def fail_first_close(fd):
        nonlocal failed_close
        original_close(fd)
        if not failed_close:
            failed_close = True
            raise ValueError("invented /invented-fixture/close")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "close", fail_first_close)
        try:
            raise SystemExit("already handled by caller")
        except SystemExit:
            with pytest.raises(inventory.InventoryScopeError) as captured:
                _counts(fixture_root, [key] if operation == "shard_close" else [])

    assert failed_close
    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None


@pytest.mark.parametrize("explicit", [False, True])
def test_scope_error_remains_safe_in_normal_and_explicit_exception_chains(
    fixture_root, monkeypatch, explicit
):
    def denied(*args, **kwargs):
        raise PermissionError(13, "invented denial", "/invented-fixture/path-component")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "access", denied)
        with pytest.raises(RuntimeError) as captured:
            try:
                _counts(fixture_root, [])
            except inventory.InventoryScopeError as error:
                if explicit:
                    raise RuntimeError("invented wrapper") from error
                raise RuntimeError("invented wrapper")

    outer = captured.value
    inner = outer.__context__
    assert isinstance(inner, inventory.InventoryScopeError)
    assert outer.__cause__ is (inner if explicit else None)
    assert inner.__context__ is None
    assert inner.__cause__ is None


@pytest.mark.parametrize(
    ("operation", "error_type"),
    [
        ("constructor", inventory.InventoryScopeError),
        ("root_type", inventory.InventoryScopeError),
        ("keys_type", TypeError),
        ("filesystem", inventory.InventoryScopeError),
    ],
)
def test_public_errors_do_not_retain_an_active_caller_os_error(
    fixture_root, monkeypatch, operation, error_type
):
    root = _root(fixture_root)

    def denied(*args, **kwargs):
        raise PermissionError(13, "invented denial", "/invented-fixture/current")

    with monkeypatch.context() as guarded:
        if operation == "filesystem":
            guarded.setattr(os, "access", denied)
        try:
            raise OSError(5, "invented caller error", "/invented-fixture/caller")
        except OSError:
            with pytest.raises(error_type) as captured:
                if operation == "constructor":
                    inventory.SyntheticFixtureRoot("/invented-fixture/not-allowed")
                elif operation == "root_type":
                    inventory.inventory_cache_files(root=str(fixture_root), keys=[])
                elif operation == "keys_type":
                    inventory.inventory_cache_files(root=root, keys=object())
                else:
                    inventory.inventory_cache_files(root=root, keys=[])

    assert captured.value.__context__ is None
    assert captured.value.__cause__ is None


def test_file_errors_return_only_aggregate_counts(fixture_root, monkeypatch):
    key = "b" * 64
    _invented_file(fixture_root, key)

    def denied(*args, **kwargs):
        origin = OSError(5, "invented cause", "/invented-fixture/cause")
        raise PermissionError(13, "invented denial", "/invented-fixture/file") from origin

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "stat", denied)
        result = _counts(fixture_root, [key])

    assert asdict(result) == {
        "total": 1,
        "present": 0,
        "missing": 0,
        "errors": 1,
        "invalid": 0,
        "duplicate_occurrences": 0,
    }
    assert all(type(value) is int for value in asdict(result).values())


@pytest.mark.parametrize("component", ["fixture", "cache"])
def test_nonprivate_fixture_directories_fail_closed(fixture_root, component):
    directory = fixture_root.parent if component == "fixture" else fixture_root
    directory.chmod(0o750)
    try:
        with pytest.raises(inventory.InventoryScopeError):
            _counts(fixture_root, [])
    finally:
        directory.chmod(0o700)


def test_unsearchable_root_fails_closed_even_with_no_keys(fixture_root, monkeypatch):
    attempts = []

    def denied(path, mode, *, dir_fd, effective_ids):
        attempts.append((path, mode, dir_fd, effective_ids))
        return False

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "access", denied)
        with pytest.raises(inventory.InventoryScopeError):
            _counts(fixture_root, [])

    assert len(attempts) == 1
    assert attempts[0][0:2] == (".", os.X_OK)
    assert attempts[0][3] is True


def test_unowned_fixture_directory_fails_closed(fixture_root, monkeypatch):
    original_fstat = os.fstat

    def wrong_owner(fd):
        metadata = original_fstat(fd)
        return SimpleNamespace(st_uid=os.geteuid() + 1, st_mode=metadata.st_mode)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "fstat", wrong_owner)
        with pytest.raises(inventory.InventoryScopeError):
            _counts(fixture_root, [])


def test_shard_permission_error_is_not_misreported_as_missing(fixture_root, monkeypatch):
    key = "d" * 64
    original_open = os.open

    def denied_shard(path, flags, *args, **kwargs):
        if path == key[:2]:
            raise PermissionError("synthetic denial")
        return original_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", denied_shard)
        result = _counts(fixture_root, [key])

    assert result.total == result.errors == 1
    assert result.missing == result.present == result.invalid == 0


@pytest.mark.parametrize("component", ["fixture", "cache"])
def test_symlinked_root_components_do_not_reach_target(
    fixture_root, component, monkeypatch
):
    original_open = os.open
    opens = []

    def nofollow_directories(path, flags, *args, **kwargs):
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_DIRECTORY
        assert flags & os.O_PATH
        opens.append(path)
        return original_open(path, flags, *args, **kwargs)

    def forbidden_stat(*args, **kwargs):
        raise AssertionError("a symlinked root reached a cache file")

    with tempfile.TemporaryDirectory(prefix=_PREFIX, dir=_TEMP_PARENT) as parent:
        parent = Path(parent)
        if component == "fixture":
            parent.rmdir()
            parent.symlink_to(fixture_root.parent, target_is_directory=True)
            alias_root = parent / "cache"
        else:
            alias_root = parent / "cache"
            alias_root.symlink_to(fixture_root, target_is_directory=True)
        try:
            with monkeypatch.context() as guarded:
                guarded.setattr(os, "open", nofollow_directories)
                guarded.setattr(os, "stat", forbidden_stat)
                with pytest.raises(inventory.InventoryScopeError):
                    _counts(alias_root, ["a" * 64])
        finally:
            if component == "fixture":
                parent.unlink()
                parent.mkdir(mode=0o700)

    assert opens[-1] == (parent.name if component == "fixture" else "cache")


def test_symlinked_shard_is_an_error_without_querying_target(fixture_root, monkeypatch):
    key = "f" * 64
    target = fixture_root / "invented-shard-target"
    target.mkdir(mode=0o700)
    (target / (key + ".json")).write_text("invented", encoding="utf-8")
    (fixture_root / key[:2]).symlink_to(target, target_is_directory=True)
    original_open = os.open

    def nofollow_directories(path, flags, *args, **kwargs):
        assert flags & os.O_NOFOLLOW
        return original_open(path, flags, *args, **kwargs)

    def forbidden_stat(*args, **kwargs):
        raise AssertionError("a symlinked shard reached a cache file")

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "open", nofollow_directories)
        guarded.setattr(os, "stat", forbidden_stat)
        result = _counts(fixture_root, [key])

    assert result.total == result.errors == 1
    assert result.present == result.missing == 0


def test_symlinked_leaf_is_an_error_without_following_it(fixture_root, monkeypatch):
    key = "a" * 64
    target = fixture_root / "invented-target"
    target.write_text("invented", encoding="utf-8")
    _invented_file(fixture_root, key).symlink_to(target)
    original_stat = os.stat
    queries = []

    def nofollow_file(path, *args, **kwargs):
        assert path == key + ".json"
        assert kwargs.get("follow_symlinks") is False
        assert isinstance(kwargs.get("dir_fd"), int)
        queries.append(path)
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "stat", nofollow_file)
        result = _counts(fixture_root, [key])

    assert result.total == result.errors == 1
    assert result.present == result.missing == 0
    assert queries == [key + ".json"]


def test_nonregular_cache_path_is_an_error(fixture_root):
    key = "b" * 64
    _invented_file(fixture_root, key).mkdir(mode=0o700)
    result = _counts(fixture_root, [key])
    assert result.total == result.errors == 1
    assert result.present == result.missing == 0


def test_duplicate_observations_do_not_reuse_the_first_result(fixture_root, monkeypatch):
    key = "c" * 64
    _invented_file(fixture_root, key).write_text("invented", encoding="utf-8")
    original_stat = os.stat
    attempts = []

    def change_after_first_observation(path, *args, **kwargs):
        if path == key + ".json":
            attempts.append(True)
            if len(attempts) == 2:
                raise PermissionError("synthetic second-observation denial")
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "stat", change_after_first_observation)
        result = _counts(fixture_root, [key, key])

    assert asdict(result) == {
        "total": 2,
        "present": 1,
        "missing": 0,
        "errors": 1,
        "invalid": 0,
        "duplicate_occurrences": 1,
    }


def test_key_list_is_snapshotted_before_file_queries(fixture_root, monkeypatch):
    first, second = "e" * 64, "f" * 64
    _invented_file(fixture_root, first).write_text("invented", encoding="utf-8")
    keys = [first]
    original_stat = os.stat

    def mutate_caller_list(path, *args, **kwargs):
        if path == first + ".json":
            keys.append(second)
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(os, "stat", mutate_caller_list)
        result = _counts(fixture_root, keys)

    assert keys == [first, second]
    assert result.total == result.present == 1
    assert result.missing == result.errors == result.invalid == 0


def test_metadata_only_no_content_open_read_write_or_network(fixture_root, monkeypatch):
    key = "d" * 64
    _invented_file(fixture_root, key).write_bytes(b"invented and never read")
    original_open = os.open
    original_stat = os.stat
    original_fstat = os.fstat
    file_queries = []
    opened_directories = {}
    directory_checks = []

    def forbidden(*args, **kwargs):
        raise AssertionError("content I/O or a write was attempted")

    def directory_open(path, flags, *args, **kwargs):
        assert flags & os.O_PATH
        assert flags & os.O_DIRECTORY
        assert flags & os.O_NOFOLLOW
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        assert path != key + ".json"
        fd = original_open(path, flags, *args, **kwargs)
        opened_directories[fd] = path
        return fd

    def fixture_directory_metadata_only(fd):
        name = opened_directories[fd]
        assert name in (fixture_root.parent.name, "cache")
        directory_checks.append(name)
        return original_fstat(fd)

    def one_nofollow_file_query(path, *args, **kwargs):
        assert path == key + ".json"
        assert kwargs.get("follow_symlinks") is False
        assert isinstance(kwargs.get("dir_fd"), int)
        file_queries.append(path)
        return original_stat(path, *args, **kwargs)

    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(io, "open", forbidden)
        guarded.setattr(Path, "open", forbidden)
        guarded.setattr(Path, "glob", forbidden)
        guarded.setattr(Path, "rglob", forbidden)
        for name in (
            "read", "readv", "pread", "preadv", "write", "writev", "pwrite",
            "pwritev", "mkdir", "unlink", "remove", "listdir", "scandir", "walk", "fwalk",
        ):
            if hasattr(os, name):
                guarded.setattr(os, name, forbidden)
        guarded.setattr(os, "open", directory_open)
        guarded.setattr(os, "stat", one_nofollow_file_query)
        guarded.setattr(os, "fstat", fixture_directory_metadata_only)
        result = _counts(fixture_root, [key])

    assert result.total == result.present == 1
    assert result.errors == result.missing == result.invalid == 0
    assert file_queries == [key + ".json"]
    assert directory_checks == [fixture_root.parent.name, "cache"]
