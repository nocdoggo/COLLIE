"""Copy-only preservation of the unfinished original gpt-oss checkpoints.

The registered entry point below has one fixed study worktree, launch-plan hash,
target model, destination parent and output name. It reads no cache, credential,
item file or sealed outcome, makes no network call, and never opens an original
checkpoint for writing. It copies only five named files for each of the 16
identity-checked partial runs to a new owner-only private directory. The single
run without a manifest is required to have neither an output nor a local run
directory. A complete marker is written only after all files have been copied,
synced, hashed and rechecked. Failure can leave an incomplete private directory;
this module never deletes or overwrites it. A marker seen after an interrupted or
failed command is not a success receipt and requires independent verification.

The real entry requires a pushed plan amendment that names this exact source and
test hash, a matching local tracking reference and a separately verified push
journal. The synthetic entry accepts only explicitly invented fixtures under
``/tmp/opencode/oss-backup-fixture-XXXXXXXX``. Neither checks prove protection
from same-user/privileged attackers, bind mounts, direct workers ignoring lane
locks, power loss, outstanding provider requests, or dishonest Git metadata.
This is a backup, not a complete cache snapshot, live runner, budget authority,
or permission to alter existing outputs. Never use its private helpers as an
alternative real-data interface.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import json
import math
import os
import re
import stat
import subprocess
import sys


WORKSPACE = "/data/noctis/GitHub-Data/COLLIE-coling"
PRIVATE_PARENT = "/data/noctis/GitHub-Data/COLLIE/owner_review/14_2026-10-29_execution"
BACKUP_NAME = "OSS_CHECKPOINT_BACKUP_2026-10-30"
PLAN_SHA256 = "2bf32748015d21d891b661da1149aef5dd7aa7dce7af61b83a70b30d4da7ffd4"
FROZEN_PREFIX_SHA256 = "806443831e4748f8f421d83661ffd063dc355dfb0fa2cb82e96fbaf6dfa00953"
FROZEN_PREFIX_BYTES = 241581
READ_SHA256 = "54d171783601e72994f960cbe7b5adba157f6061ba3c9a1da30fd23e23be244f"
LAUNCH_SHA256 = "db06bf2900f149e90c97155c7d4060d40cf21b5aa8ca92c234768022181298d5"
SYNTHETIC_ROOT = re.compile(r"/tmp/opencode/oss-backup-fixture-[a-z0-9_]{8}", re.ASCII)
RUN_NAME = re.compile(r"[A-Za-z0-9_.-]{1,160}", re.ASCII)
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_MAX_PLAN = 4_000_000
_MAX_MANIFEST = 1_000_000
_MAX_SOURCE_FILE = 64_000_000
_MAX_TOTAL = 128_000_000
_DEADLINE = datetime(2026, 10, 30, 23, 49, 59, tzinfo=timezone.utc)
_OUT_FILES = ("readings.jsonl", "run_manifest.json", "spend_log.jsonl", "invocations.jsonl")
_LOCAL_FILES = ("responses.jsonl",)


class BackupRefusal(RuntimeError):
    """The bounded copy-only snapshot cannot be safely established."""


@dataclass(frozen=True, slots=True)
class BackupResult:
    partial_runs: int
    missing_runs: int
    copied_files: int
    copied_bytes: int
    journal_sha256: str


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupRefusal("duplicate metadata JSON key")
        result[key] = value
    return result


def _parse(raw: bytes) -> dict:
    try:
        result = json.loads(raw, object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError):
        raise BackupRefusal("study metadata is malformed") from None
    if type(result) is not dict:
        raise BackupRefusal("study metadata is not an object")
    return result


def _same_metadata(actual: object, expected: object) -> bool:
    if type(expected) in (int, float):
        if type(actual) not in (int, float):
            return False
        try:
            return math.isfinite(actual) and actual == expected
        except OverflowError:
            return False
    if type(expected) is dict:
        return (type(actual) is dict and actual.keys() == expected.keys()
                and all(_same_metadata(actual[key], value) for key, value in expected.items()))
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(
            _same_metadata(left, right) for left, right in zip(actual, expected, strict=True)
        )
    return type(actual) is type(expected) and actual == expected


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _open_absolute(path: str, stack: ExitStack) -> int:
    if type(path) is not str or not path.startswith("/") or any(part in {"", ".", ".."} for part in path.split("/")[1:]):
        raise BackupRefusal("directory path is not an exact absolute path")
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


def _regular_info(parent: int, name: str, limit: int) -> os.stat_result:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
            or info.st_size < 0 or info.st_size > limit):
        raise BackupRefusal("a source file has unsafe type, owner, links or size")
    return info


def _private_file_info(parent: int, name: str, limit: int) -> os.stat_result:
    info = _regular_info(parent, name, limit)
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise BackupRefusal("snapshot file permissions differ")
    return info


def _read_metadata(parent: int, name: str, limit: int) -> tuple[bytes, tuple[int, int, int, int, int]]:
    visible = _regular_info(parent, name, limit)
    fd = os.open(name, _READ, dir_fd=parent)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if _identity(before) != _identity(visible):
            raise BackupRefusal("metadata changed before reading")
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    visible_after = _regular_info(parent, name, limit)
    if len(raw) != before.st_size or _identity(before) != _identity(after) or _identity(after) != _identity(visible_after):
        raise BackupRefusal("metadata changed while reading")
    return raw, _identity(before)


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        count = os.write(fd, data[offset:])
        if count <= 0:
            raise BackupRefusal("snapshot write did not progress")
        offset += count


def _check_dir(parent: int, name: str, fd: int) -> None:
    info = os.fstat(fd)
    visible = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(visible.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700
            or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)):
        raise BackupRefusal("new snapshot directory identity differs")


def _create_dir(parent: int, name: str, stack: ExitStack) -> int:
    os.mkdir(name, 0o700, dir_fd=parent)
    fd = os.open(name, _DIR, dir_fd=parent)
    stack.callback(os.close, fd)
    _check_dir(parent, name, fd)
    os.fsync(parent)
    return fd


def _copy_regular(source_parent: int, target_parent: int, name: str,
                  expected: tuple[int, int, int, int, int]) -> tuple[int, str, tuple[int, int, int, int, int]]:
    """Copy one named file, without overwriting or interpreting its contents."""
    source_info = _regular_info(source_parent, name, _MAX_SOURCE_FILE)
    if _identity(source_info) != expected:
        raise BackupRefusal("source changed before copying")
    source = os.open(name, _READ, dir_fd=source_parent)
    try:
        before = os.fstat(source)
        if _identity(before) != expected:
            raise BackupRefusal("source changed while opening")
        target = os.open(name, _CREATE, 0o600, dir_fd=target_parent)
        try:
            target_info = os.fstat(target)
            if (not stat.S_ISREG(target_info.st_mode) or target_info.st_uid != os.geteuid()
                    or stat.S_IMODE(target_info.st_mode) != 0o600 or target_info.st_nlink != 1):
                raise BackupRefusal("new snapshot file metadata differs")
            digest = sha256()
            count = 0
            while True:
                chunk = os.read(source, min(65536, _MAX_SOURCE_FILE + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                if count > _MAX_SOURCE_FILE:
                    raise BackupRefusal("source grew beyond its bound")
                digest.update(chunk)
                _write_all(target, chunk)
            os.fsync(target)
            after_source = os.fstat(source)
            after_target = os.fstat(target)
        finally:
            os.close(target)
        visible_source = _regular_info(source_parent, name, _MAX_SOURCE_FILE)
        if (count != before.st_size or _identity(after_source) != expected
                or _identity(visible_source) != expected or after_target.st_size != count):
            raise BackupRefusal("source or snapshot changed during copying")
        os.fsync(target_parent)
        # Re-read the new private file only; the original is never opened writable.
        copied, copied_identity = _read_metadata(target_parent, name, _MAX_SOURCE_FILE)
        private_info = _private_file_info(target_parent, name, _MAX_SOURCE_FILE)
        if (len(copied) != count or sha256(copied).hexdigest() != digest.hexdigest()
                or copied_identity != _identity(after_target) or _identity(private_info) != copied_identity):
            raise BackupRefusal("snapshot bytes differ from their source")
        return count, digest.hexdigest(), copied_identity
    finally:
        os.close(source)


def _event(fd: int, payload: dict) -> None:
    _write_all(fd, (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())
    os.fsync(fd)


def _expected_specs(plan: dict, total_runs: int, total_rows: int) -> tuple[dict, ...]:
    if (type(plan.get("options")) is not dict or plan["options"].get("out_root") != "analysis/coling/out/read"
            or plan["options"].get("local_root") != "results/coling/read"):
        raise BackupRefusal("launch roots differ")
    runs = [row for row in plan.get("runs", ()) if type(row) is dict and row.get("model") == "gpt-oss-20b"]
    if (len(runs) != total_runs or len({row.get("run") for row in runs}) != total_runs
            or any(type(row.get("calls")) is not int or row["calls"] < 0 or row.get("lane") != "openrouter" for row in runs)
            or sum(row["calls"] for row in runs) != total_rows):
        raise BackupRefusal("launch target inventory differs")
    route = plan["routes"]["gpt-oss-20b"]
    if (route.get("model_id") != "openai/gpt-oss-20b" or route.get("provider") != "deepinfra/bf16"
            or route.get("quantization") != "bf16"):
        raise BackupRefusal("registered model route differs")
    provider = {"order": [route["provider"]], "allow_fallbacks": False, "quantizations": [route["quantization"]]}
    specs = []
    for row in runs:
        name = row["run"]
        if type(name) is not str or RUN_NAME.fullmatch(name) is None or name in {".", ".."}:
            raise BackupRefusal("run identity is unsafe")
        expected = {
            "model": row["model"], "model_id": route["model_id"], "provider_object": provider,
            "template": row["template"], "template_sha256": plan["templates"][row["template"]],
            "shard": row["shard"], "limit": row["limit"], "samples": row["samples"],
            "temperature": row["temperature"], "mask_names": row["mask_names"], "shift_years": row["shift_years"],
            "track_record_sha256": plan["tracks"][row["track"]]["sha256"] if row["track"] else None,
            "items_sha256": plan["lists"][row["list"]]["sha256"], "item_ids_sha256": row["item_ids_sha256"],
            "expected_rows": row["calls"],
        }
        specs.append({"name": name, "calls": row["calls"], "expected": expected})
    return tuple(specs)


def _locked_lanes(launch_fd: int, workers: int, stack: ExitStack) -> None:
    if type(workers) is not int or not 1 <= workers <= 16:
        raise BackupRefusal("lane worker count differs")
    locks = _descend(launch_fd, ("locks",), stack)
    names = {name for name in os.listdir(locks) if re.fullmatch(r"openrouter\.w[0-9]+\.lock", name)}
    expected = {f"openrouter.w{index}.lock" for index in range(workers)}
    if names != expected:
        raise BackupRefusal("lane lock inventory differs")
    for name in sorted(expected):
        fd = os.open(name, _READ, dir_fd=locks)
        stack.callback(os.close, fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
            raise BackupRefusal("lane lock is not a regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupRefusal("a registered lane worker is active") from None


def _snapshot(workspace_path: str, parent_path: str, *, destination_name: str, plan_hash: str,
              total_runs: int, total_rows: int, expected_finished: int, expected_partial: int,
              expected_missing: int, expected_recorded: int, workers: int) -> BackupResult:
    """Internal mechanism; only the two closed public entry points may call it."""
    if type(destination_name) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,100}", destination_name) is None:
        raise BackupRefusal("snapshot destination name is invalid")
    if (type(plan_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", plan_hash) is None
            or any(type(value) is not int or value < 0 for value in (
                total_runs, total_rows, expected_finished, expected_partial, expected_missing, expected_recorded
            ))):
        raise BackupRefusal("snapshot identity or expected counts are invalid")
    with ExitStack() as stack:
        workspace = _open_absolute(workspace_path, stack)
        parent = _open_absolute(parent_path, stack)
        if os.fstat(parent).st_uid != os.geteuid():
            raise BackupRefusal("snapshot parent is not owned by the current user")
        output = _descend(workspace, ("analysis", "coling", "out", "read"), stack)
        local = _descend(workspace, ("results", "coling", "read"), stack)
        launch = _descend(output, ("_launch",), stack)
        plan_raw, plan_identity = _read_metadata(launch, "plan.json", _MAX_PLAN)
        if sha256(plan_raw).hexdigest() != plan_hash:
            raise BackupRefusal("launch plan hash differs")
        plan = _parse(plan_raw)
        try:
            specs = _expected_specs(plan, total_runs, total_rows)
        except (KeyError, TypeError):
            raise BackupRefusal("launch plan schema differs") from None
        _locked_lanes(launch, workers, stack)
        partial = []
        expected_reading_hashes = {}
        source_directories = []
        manifest_identities = []
        missing_names = []
        recorded = finished = missing = 0
        files: list[tuple[str, int, str, str, tuple[int, int, int, int, int]]] = []
        total_bytes = 0
        for spec in specs:
            name = spec["name"]
            try:
                run_fd = os.open(name, _DIR, dir_fd=output)
            except FileNotFoundError:
                missing += 1
                missing_names.append(name)
                try:
                    absent_local = os.open(name, _DIR, dir_fd=local)
                except FileNotFoundError:
                    pass
                else:
                    os.close(absent_local)
                    raise BackupRefusal("a missing output run has an unexpected local directory")
                continue
            stack.callback(os.close, run_fd)
            source_directories.append((output, name, run_fd))
            manifest_raw, manifest_identity = _read_metadata(run_fd, "run_manifest.json", _MAX_MANIFEST)
            manifest_identities.append((run_fd, manifest_identity))
            manifest = _parse(manifest_raw)
            if (type(manifest.get("complete")) is not bool or type(manifest.get("readings")) is not int
                    or not 0 <= manifest["readings"] <= spec["calls"]
                    or any(key not in manifest or not _same_metadata(manifest[key], value)
                           for key, value in spec["expected"].items())):
                raise BackupRefusal("run manifest identity or count differs")
            recorded += manifest["readings"]
            if manifest["complete"]:
                if manifest["readings"] != spec["calls"]:
                    raise BackupRefusal("finished manifest count differs")
                finished += 1
                continue
            partial.append(name)
            reading_hash = manifest.get("readings_sha256")
            if type(reading_hash) is not str or re.fullmatch(r"[0-9a-f]{64}", reading_hash) is None:
                raise BackupRefusal("partial manifest has no valid reading identity")
            expected_reading_hashes[name] = reading_hash
            local_fd = os.open(name, _DIR, dir_fd=local)
            stack.callback(os.close, local_fd)
            source_directories.append((local, name, local_fd))
            for source_parent, area, names in ((run_fd, "out", _OUT_FILES), (local_fd, "local", _LOCAL_FILES)):
                for filename in names:
                    info = _regular_info(source_parent, filename, _MAX_SOURCE_FILE)
                    total_bytes += info.st_size
                    files.append((name, source_parent, area, filename, _identity(info)))
        if ((finished, len(partial), missing, recorded) !=
                (expected_finished, expected_partial, expected_missing, expected_recorded)):
            raise BackupRefusal("run states changed; refresh the snapshot plan")
        if total_bytes > _MAX_TOTAL:
            raise BackupRefusal("snapshot exceeds the byte limit")
        # The destination is created only after all source metadata checks and
        # registered lane locks have succeeded. Existing paths are never reused.
        destination = _create_dir(parent, destination_name, stack)
        journal = os.open("snapshot.journal.jsonl", _CREATE, 0o600, dir_fd=destination)
        stack.callback(os.close, journal)
        _event(journal, {"event": "started", "scope": "copy-only-partial-gpt-oss", "plan_sha256": plan_hash,
                         "partial_runs": len(partial), "missing_runs": missing, "planned_files": len(files)})
        out_dest = _create_dir(destination, "out", stack)
        local_dest = _create_dir(destination, "local", stack)
        dest_dirs = {}
        created_dirs = [(parent, destination_name, destination), (destination, "out", out_dest),
                        (destination, "local", local_dest)]
        for name in partial:
            dest_dirs[("out", name)] = _create_dir(out_dest, name, stack)
            dest_dirs[("local", name)] = _create_dir(local_dest, name, stack)
            created_dirs.extend(((out_dest, name, dest_dirs[("out", name)]),
                                 (local_dest, name, dest_dirs[("local", name)])))
        copied_bytes = 0
        copied_files = []
        for name, source_parent, area, filename, expected in files:
            target_parent = dest_dirs[(area, name)]
            size, digest, target_identity = _copy_regular(source_parent, target_parent, filename, expected)
            if filename == "readings.jsonl" and digest != expected_reading_hashes[name]:
                raise BackupRefusal("partial reading bytes differ from their manifest")
            copied_bytes += size
            copied_files.append((target_parent, filename, size, digest, target_identity))
            _event(journal, {"event": "copied", "run": name, "area": area, "file": filename,
                             "bytes": size, "sha256": digest})
        for _, source_parent, _, filename, expected in files:
            if _identity(_regular_info(source_parent, filename, _MAX_SOURCE_FILE)) != expected:
                raise BackupRefusal("source changed before snapshot completion")
        for run_fd, expected in manifest_identities:
            if _identity(_regular_info(run_fd, "run_manifest.json", _MAX_MANIFEST)) != expected:
                raise BackupRefusal("run state changed before snapshot completion")
        for directory_parent, name, directory in source_directories:
            visible = os.stat(name, dir_fd=directory_parent, follow_symlinks=False)
            info = os.fstat(directory)
            if not stat.S_ISDIR(visible.st_mode) or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino):
                raise BackupRefusal("source run directory changed")
        for name in missing_names:
            for directory in (output, local):
                try:
                    os.stat(name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise BackupRefusal("a previously missing run directory appeared")
        if _identity(_regular_info(launch, "plan.json", _MAX_PLAN)) != plan_identity or copied_bytes != total_bytes:
            raise BackupRefusal("plan or file count changed before snapshot completion")
        for directory_parent, name, directory in created_dirs:
            _check_dir(directory_parent, name, directory)
        for target_parent, filename, size, digest, identity in copied_files:
            raw, current = _read_metadata(target_parent, filename, _MAX_SOURCE_FILE)
            if (current != identity or _identity(_private_file_info(target_parent, filename, _MAX_SOURCE_FILE)) != identity
                    or len(raw) != size or sha256(raw).hexdigest() != digest):
                raise BackupRefusal("snapshot file changed before completion")
        with ExitStack() as check:
            current_workspace = _open_absolute(workspace_path, check)
            current_parent = _open_absolute(parent_path, check)
            current_output = _descend(current_workspace, ("analysis", "coling", "out", "read"), check)
            current_local = _descend(current_workspace, ("results", "coling", "read"), check)
            current_launch = _descend(current_output, ("_launch",), check)
            for old, new in ((workspace, current_workspace), (parent, current_parent), (output, current_output),
                             (local, current_local), (launch, current_launch)):
                a, b = os.fstat(old), os.fstat(new)
                if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                    raise BackupRefusal("snapshot source or destination root changed")
        _event(journal, {"event": "files_verified", "copied_files": len(files), "copied_bytes": copied_bytes})
        os.fsync(destination)
        raw, journal_identity = _read_metadata(destination, "snapshot.journal.jsonl", 1_000_000)
        if (_identity(os.fstat(journal)) != journal_identity
                or _identity(_private_file_info(destination, "snapshot.journal.jsonl", 1_000_000)) != journal_identity):
            raise BackupRefusal("snapshot journal identity or mode differs")
        marker = os.open("COMPLETE.json", _CREATE, 0o600, dir_fd=destination)
        try:
            _write_all(marker, (json.dumps({"scope": "copy-only-partial-gpt-oss", "copied_files": len(files),
                                           "copied_bytes": copied_bytes, "journal_sha256": sha256(raw).hexdigest()},
                                          sort_keys=True, separators=(",", ":")) + "\n").encode())
            os.fsync(marker)
        finally:
            os.close(marker)
        os.fsync(destination)
        _private_file_info(destination, "COMPLETE.json", _MAX_MANIFEST)
        for directory_parent, name, directory in created_dirs:
            _check_dir(directory_parent, name, directory)
        os.fsync(parent)
        return BackupResult(len(partial), missing, len(files), copied_bytes, sha256(raw).hexdigest())


def backup_invented_fixture(root: str, *, plan_sha256: str, total_runs: int, total_rows: int,
                            finished: int, partial: int, missing: int, recorded: int,
                            workers: int, synthetic_only: bool) -> BackupResult:
    """Exercise only an invented scratch tree; the assertion is not provenance."""
    if type(synthetic_only) is not bool or synthetic_only is not True:
        raise BackupRefusal("explicit synthetic-only assertion is required")
    if type(root) is not str or SYNTHETIC_ROOT.fullmatch(root) is None:
        raise BackupRefusal("fixture root is outside the synthetic scope")
    return _snapshot(root + "/workspace", root + "/private", destination_name="snapshot",
                     plan_hash=plan_sha256, total_runs=total_runs, total_rows=total_rows,
                     expected_finished=finished, expected_partial=partial, expected_missing=missing,
                     expected_recorded=recorded, workers=workers)


def _verify_registration() -> None:
    """Require a clean, locally tracked, separately verified A3 before real reads."""
    if datetime.now(timezone.utc) >= _DEADLINE:
        raise BackupRefusal("the conservative delegation deadline has passed")
    env = {"HOME": "/tmp/opencode", "PATH": "/usr/bin:/bin", "GIT_TERMINAL_PROMPT": "0"}
    files = ("analysis/coling/plan/PLAN.md", "analysis/coling/followup/oss_checkpoint_backup.py",
             "analysis/coling/followup/test_oss_checkpoint_backup.py")
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=WORKSPACE, env=env, capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
        tracking = subprocess.run(["git", "rev-parse", "refs/remotes/origin/followup/coling-2027"],
                                  cwd=WORKSPACE, env=env, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=WORKSPACE, env=env, capture_output=True,
                                text=True, timeout=10, check=True).stdout.strip()
        for extra in ([], ["--cached"]):
            subprocess.run(["git", "diff", *extra, "--quiet", "HEAD", "--", *files], cwd=WORKSPACE,
                           env=env, capture_output=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        raise BackupRefusal("registered source or Git state cannot be verified") from None
    if head != tracking or branch != "followup/coling-2027" or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise BackupRefusal("registered branch or tracking commit differs")
    with ExitStack() as stack:
        workspace = _open_absolute(WORKSPACE, stack)
        coling = _descend(workspace, ("analysis", "coling"), stack)
        plan_dir = _descend(coling, ("plan",), stack)
        followup = _descend(coling, ("followup",), stack)
        private = _open_absolute(PRIVATE_PARENT, stack)
        plan, _ = _read_metadata(plan_dir, "PLAN.md", 1_000_000)
        if len(plan) < FROZEN_PREFIX_BYTES or sha256(plan[:FROZEN_PREFIX_BYTES]).hexdigest() != FROZEN_PREFIX_SHA256:
            raise BackupRefusal("registered plan prefix differs")
        source, _ = _read_metadata(followup, "oss_checkpoint_backup.py", 1_000_000)
        tests, _ = _read_metadata(followup, "test_oss_checkpoint_backup.py", 1_000_000)
        try:
            if not os.path.samefile(__file__, os.path.join(WORKSPACE, files[1])):
                raise BackupRefusal("running backup module is not the registered file")
        except OSError:
            raise BackupRefusal("running backup module identity is unavailable") from None
        source_sha, test_sha = sha256(source).hexdigest(), sha256(tests).hexdigest()
        heading = b"### A3. Copy-only checkpoint preservation"
        block = plan.split(heading)
        if (len(block) != 2 or f"Backup source SHA256: `{source_sha}`".encode() not in block[1]
                or f"Backup fixture tests SHA256: `{test_sha}`".encode() not in block[1]):
            raise BackupRefusal("pushed amendment does not name these exact backup files")
        for name, wanted in (("read.py", READ_SHA256), ("launch.py", LAUNCH_SHA256)):
            raw, _ = _read_metadata(coling, name, 1_000_000)
            if sha256(raw).hexdigest() != wanted:
                raise BackupRefusal("frozen original runner source differs")
        private_info = _regular_info(private, "A3_BACKUP_GIT_VERIFIED_PRIVATE.json", _MAX_MANIFEST)
        if stat.S_IMODE(private_info.st_mode) & 0o077:
            raise BackupRefusal("remote verification record is not private")
        verified_raw, _ = _read_metadata(private, "A3_BACKUP_GIT_VERIFIED_PRIVATE.json", _MAX_MANIFEST)
    # ``git diff`` alone ignores untracked files. Compare each protected file
    # to its exact committed blob as well, without reading any other paths.
    for name, raw in zip(files, (plan, source, tests), strict=True):
        try:
            committed = subprocess.run(["git", "show", f"HEAD:{name}"], cwd=WORKSPACE, env=env,
                                       capture_output=True, timeout=10, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            raise BackupRefusal("registered file is absent from the commit") from None
        if committed != raw:
            raise BackupRefusal("registered file differs from its committed blob")
    verified = _parse(verified_raw)
    if (verified.get("commit") != head or verified.get("remote_commit_verified") is not True
            or verified.get("user_agent_verified") is not True):
        raise BackupRefusal("remote push verification is unavailable")


def main() -> None:
    if sys.argv[1:] != ["--execute-registered-copy-only"]:
        raise SystemExit("This copy-only tool requires its exact registered execution flag.")
    try:
        _verify_registration()
        result = _snapshot(WORKSPACE, PRIVATE_PARENT, destination_name=BACKUP_NAME, plan_hash=PLAN_SHA256,
                           total_runs=40, total_rows=9219, expected_finished=23, expected_partial=16,
                           expected_missing=1, expected_recorded=6010, workers=8)
    except Exception:
        raise SystemExit("Copy-only backup stopped; inspect the private snapshot state before any retry.") from None
    print(f"Copied {result.copied_files} named files from {result.partial_runs} partial runs to a private snapshot.")
    print("No model call, cache access, original-file write or sealed-outcome read occurred.")


if __name__ == "__main__":
    main()
