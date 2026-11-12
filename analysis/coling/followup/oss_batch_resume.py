"""Prospective, paced batch continuation on the re-pinned dekallm endpoint (A11).

This entry point is disabled until a pushed amendment (A11) names the exact
batch source, tests, transport, cache and private selection identities, and a
separate remote verification record matches. It completes only the missing
item/sample pairs of the original ``gpt-oss-20b`` condition: the original runs
stay untouched (readings, manifests and responses byte-identical to the A3
snapshot; spend and invocation logs append-only), the continuation runs under
new ``<original>.dk`` names on the ``dekallm/bf16`` endpoint with the original
model id, template, prompts and decoding, and analysis pools runs by model and
condition. The route override lives here, at runtime; the frozen reader and
launcher sources are never edited.

Before any continuation request, the batch releases the dead budget
reservations of the blocked original runs (declare-only re-declarations at
their recorded spend, an idempotent ledger append), because those runs can
never make another call on the content-blocked deepinfra endpoint and their
open caps would otherwise exhaust the owner's $10 model cap. The four
historical orphaned pairs (answered but never recorded) are not re-asked, per
the A4 rule.

The frozen reader writes and accounts the ``.dk`` runs itself (spend log,
invocations, ledger declarations, per-run spend and call caps); this wrapper
adds the paced counted transport, the private per-send journal, per-session
key-status freshness, and stop-and-report on any run that does not complete its
target set. A crash is resumed by a fresh selection record and a fresh status
GET under a further registered attempt; answers already cached under the
dekallm route tag are never re-asked. No proven hard billable bound, provider
privacy guarantee, completed run, evaluator rerun or sealed-outcome read is
implied. Never run this before its exact prospective registration.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

from analysis.coling.followup import oss_one_shot_resume as one_shot


DK_SUFFIX = ".dk"
_BATCH_STAGE_PREFIX = "OSS_BATCH_STAGE_"
_ROUTE = {
    "model_id": "openai/gpt-oss-20b",
    "provider": "dekallm/bf16",
    "quantization": "bf16",
    "price_input_usd_per_mtok": "0.029",
    "price_output_usd_per_mtok": "0.14",
    "price_date": "2026-10-30",
}
_PRICE = (0.029, 0.14, "2026-10-30")
_BATCH_SELECTION_SHA = "43ca3320422c289a243167e31bfd3b8f9be9c79d349c1a94dc1b42fbf6af90a5"
_TEMPLATES = ("probe-v1", "predictive-v1", "predictive-track-v1")
_MAX_RUNS = 64
_BATCH_FILES = (
    ("analysis/coling/followup/oss_batch_transport.py", "Batch transport source SHA256"),
    ("analysis/coling/followup/test_oss_batch_transport.py", "Batch transport fixture tests SHA256"),
    ("analysis/coling/followup/oss_batch_resume.py", "Batch source SHA256"),
    ("analysis/coling/followup/test_oss_batch_resume.py", "Batch fixture tests SHA256"),
)
# The counted transport preads the send journal to verify its reservation row,
# so the journal must be opened for reading as well as appending; the first
# dispatch (5 November 2026) stopped pre-send when these flags were write-only.
_SEND_JOURNAL_OPEN = os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class BatchStop(RuntimeError):
    """The paced batch continuation cannot safely proceed or continue."""


@dataclass(frozen=True, slots=True)
class RunSpec:
    """One continuation run: the original's identity, its missing set and its pins."""

    original: str
    new_run: str
    row: dict
    index: one_shot.CheckpointIndex
    target: int
    cap_usd: str
    projected_usd: str
    items_path: str
    items_raw: bytes
    track_path: str | None
    track_sha: str | None
    never_invoked: bool
    prior_calls: int


def _decimal(value: object) -> Decimal:
    if type(value) is not str:
        raise BatchStop("a decimal field is not a string")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise BatchStop("a decimal field is invalid") from None
    if not amount.is_finite():
        raise BatchStop("a decimal field is not finite")
    return amount


def _int(value: object) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise BatchStop("an integer field differs")
    return value


def _validate_selection(selected: dict) -> None:
    """Validate the private batch selection record's shape and arithmetic."""
    if (selected.get("scope") != "dekallm-batch-continuation-selection"
            or selected.get("launch_plan_sha256") != one_shot._PLAN_SHA
            or selected.get("route") != _ROUTE
            or selected.get("owner_selected_model_cap_usd") != "10"
            or selected.get("registered_study_cap_usd") != "225"
            or selected.get("f1_operational_study_cap_usd") != "200"
            or selected.get("reask_orphaned_pairs") is not False
            or selected.get("release_blocked_reservations") is not True):
        raise BatchStop("batch selection scope, route or caps differ")
    runs = selected.get("runs")
    if type(runs) is not list or not 1 <= len(runs) <= _MAX_RUNS:
        raise BatchStop("batch selection run list differs")
    targets = 0
    caps = Decimal("0")
    orphans = 0
    names = set()
    for entry in runs:
        if type(entry) is not dict:
            raise BatchStop("batch selection entry is not an object")
        original, new_run = entry.get("run"), entry.get("new_run")
        if (type(original) is not str or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,160}", original) is None
                or type(new_run) is not str or new_run != original + DK_SUFFIX
                or original in names):
            raise BatchStop("batch selection run names differ")
        names.add(original)
        if (entry.get("template") not in _TEMPLATES or entry.get("temperature") != 0
                or entry.get("samples") != 1 or type(entry.get("never_invoked")) is not bool
                or entry.get("route_provider") != "deepinfra/bf16"
                or type(entry.get("mask_names")) is not bool
                or entry.get("shard") is not None and re.fullmatch(r"\d+/\d+", entry["shard"]) is None
                or entry.get("limit") is not None and type(entry["limit"]) is not int
                or type(entry.get("shift_years")) is not int or type(entry.get("list")) is not str
                or type(entry.get("allow_test_items")) is not bool
                or type(entry.get("items")) is not str or not entry["items"].endswith(".jsonl")):
            raise BatchStop("batch selection condition differs from the registered transport")
        target = _int(entry.get("target_pairs"))
        if target < 1:
            raise BatchStop("a selected run has no target pairs")
        planned = _int(entry.get("planned_rows"))
        recorded = _int(entry.get("recorded_readings"))
        orphaned = _int(entry.get("orphaned_pairs"))
        if planned < 0 or recorded < 0 or orphaned < 0 or planned != recorded + orphaned + target:
            raise BatchStop("batch selection arithmetic differs")
        cap = _decimal(entry.get("run_cap_usd"))
        if cap <= 0 or cap > Decimal("10"):
            raise BatchStop("batch selection run cap differs")
        per_call = _decimal(entry.get("historical_usd_per_call"))
        projected = _decimal(entry.get("projected_usd"))
        if per_call < 0 or projected < 0 or projected != (per_call * target).quantize(Decimal("0.000001")):
            raise BatchStop("batch selection projection differs")
        if cap < projected + Decimal("0.01"):
            raise BatchStop("batch selection run cap does not cover its projection")
        if type(entry.get("items")) is not str or type(entry.get("items_sha256")) is not str:
            raise BatchStop("batch selection input identity differs")
        for field in ("readings_sha256", "manifest_sha256", "responses_sha256",
                      "spend_log_sha256", "invocations_sha256"):
            if type(entry.get(field)) is not str or re.fullmatch(r"[0-9a-f]{64}", entry[field]) is None:
                raise BatchStop("batch selection checkpoint identity differs")
        _int(entry.get("logged_call_count"))
        _decimal(entry.get("logged_spend_usd"))
        if entry.get("track") not in (None, "fit", "fit+dev"):
            raise BatchStop("batch selection track differs")
        targets += target
        caps += cap
        orphans += orphaned
    if (_int(selected.get("planned_target_pairs")) != targets
            or _int(selected.get("skip_orphaned_pairs")) != orphans
            or _decimal(selected.get("total_run_caps_usd")) != caps
            or _decimal(selected.get("total_projected_usd")) != sum(
                (_decimal(entry["projected_usd"]) for entry in runs), Decimal("0"))
            or selected.get("hold_is_proven_maximum") is not False):
        raise BatchStop("batch selection totals differ")
    if caps > Decimal("10"):
        raise BatchStop("batch selection caps pass the model cap")


def _verify_batch_registration() -> dict:
    """Check pushed A4-chain and A11 identities before any checkpoint or key read."""
    try:
        return _verify_batch_registration_inner()
    except one_shot.ResumeRefusal as exc:
        raise BatchStop(str(exc)) from None


def _verify_batch_registration_inner() -> dict:
    if datetime.now(timezone.utc) >= one_shot._DEADLINE:
        raise BatchStop("the conservative delegation deadline has passed")
    one_shot._check_environment()
    env = {"HOME": "/tmp/opencode", "PATH": "/usr/bin:/bin", "GIT_TERMINAL_PROMPT": "0"}
    paths = ["analysis/coling/plan/PLAN.md", *[path for path, _ in one_shot._registered_files()],
             *[path for path, _ in _BATCH_FILES]]
    shared = ["analysis/__init__.py", "analysis/coling/__init__.py", "analysis/commitment/__init__.py",
              "analysis/real_content_pilot/__init__.py", "analysis/coling/read.py", "analysis/coling/launch.py",
              "analysis/commitment/endpoints.py", "analysis/real_content_pilot/transport.py",
              "collie/__init__.py", "collie/contracts.py", "collie/llm/__init__.py", "collie/llm/client.py",
              "collie/llm/cache.py", "collie/llm/ledger.py"]
    try:
        head = one_shot.subprocess.run(["git", "rev-parse", "HEAD"], cwd=one_shot._WORKSPACE, env=env,
                                       capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        tracking = one_shot.subprocess.run(["git", "rev-parse", "refs/remotes/origin/followup/coling-2027"],
                                           cwd=one_shot._WORKSPACE, env=env, capture_output=True, text=True,
                                           timeout=10, check=True).stdout.strip()
        branch = one_shot.subprocess.run(["git", "branch", "--show-current"], cwd=one_shot._WORKSPACE,
                                         env=env, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        one_shot.subprocess.run(["git", "merge-base", "--is-ancestor", one_shot._BACKUP_COMMIT, "HEAD"],
                                cwd=one_shot._WORKSPACE, env=env, capture_output=True, timeout=10, check=True)
        for extra in ([], ["--cached"]):
            one_shot.subprocess.run(["git", "diff", *extra, "--quiet", "HEAD", "--", *paths, *shared],
                                    cwd=one_shot._WORKSPACE, env=env, capture_output=True, timeout=10, check=True)
        one_shot.subprocess.run(["git", "diff", "--quiet", "coling-f1", "HEAD", "--", *shared],
                                cwd=one_shot._WORKSPACE, env=env, capture_output=True, timeout=10, check=True)
    except (OSError, one_shot.subprocess.SubprocessError):
        raise BatchStop("registered Git or frozen-source identity cannot be verified") from None
    if head != tracking or branch != "followup/coling-2027" or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise BatchStop("registered branch or tracking commit differs")
    with ExitStack() as stack:
        workspace = one_shot._open_absolute(one_shot._WORKSPACE, stack)
        coling = one_shot._descend(workspace, ("analysis", "coling"), stack)
        plan_dir = one_shot._descend(coling, ("plan",), stack)
        followup = one_shot._descend(coling, ("followup",), stack)
        private = one_shot._open_absolute(one_shot._PRIVATE, stack)
        plan = one_shot._read_safe(plan_dir, "PLAN.md", 1_000_000)
        if len(plan) < one_shot._PREFIX_BYTES or sha256(plan[:one_shot._PREFIX_BYTES]).hexdigest() != one_shot._PREFIX_SHA:
            raise BatchStop("registered plan prefix differs")
        block = plan.split(b"### A4. One-physical-attempt original continuation")
        if len(block) != 2:
            raise BatchStop("pushed A4 heading differs")
        if b"### A11. " not in block[1]:
            raise BatchStop("pushed A11 amendment is absent")
        raw_files = {}
        for path, label in (*one_shot._registered_files(), *_BATCH_FILES):
            raw = one_shot._read_safe(followup, path.rsplit("/", 1)[1], 1_000_000)
            if f"{label}: `{sha256(raw).hexdigest()}`".encode() not in block[1]:
                raise BatchStop("pushed A4/A11 does not name an exact implementation identity")
            raw_files[path] = raw
        try:
            if not os.path.samefile(__file__, os.path.join(
                    one_shot._WORKSPACE, "analysis/coling/followup/oss_batch_resume.py")):
                raise BatchStop("running batch module differs")
        except OSError:
            raise BatchStop("running batch module identity is unavailable") from None
        backup_raw = one_shot._read_safe(followup, "oss_checkpoint_backup.py", 1_000_000)
        if sha256(backup_raw).hexdigest() != one_shot._BACKUP_CODE_SHA:
            raise BatchStop("registered backup helper differs")
        for name, wanted in (("read.py", one_shot._READ_SHA), ("launch.py", one_shot._LAUNCH_SHA)):
            raw = one_shot._read_safe(coling, name, 1_000_000)
            if sha256(raw).hexdigest() != wanted:
                raise BatchStop("frozen original source differs")
        selection_raw = one_shot._read_safe(private, "OSS_BATCH_SELECTION_PRIVATE.json", 4_000_000, private=True)
        if sha256(selection_raw).hexdigest() != _BATCH_SELECTION_SHA:
            raise BatchStop("private batch selection identity differs")
        verification_raw = one_shot._read_safe(private, "OSS_CHECKPOINT_BACKUP_VERIFICATION_PRIVATE.json",
                                               1_000_000, private=True)
        if sha256(verification_raw).hexdigest() != one_shot._BACKUP_VERIFICATION_SHA:
            raise BatchStop("backup verification identity differs")
        a4_raw = one_shot._read_safe(private, "A4_ONESHOT_GIT_VERIFIED_PRIVATE.json", 1_000_000, private=True)
        budget_raw = one_shot._read_safe(private, "EXECUTION_MANIFEST_DRAFT.json", 4_000_000)
    for path, raw in [(paths[0], plan), *raw_files.items()]:
        try:
            committed = one_shot.subprocess.run(["git", "show", f"HEAD:{path}"], cwd=one_shot._WORKSPACE,
                                                env=env, capture_output=True, timeout=10, check=True).stdout
        except (OSError, one_shot.subprocess.SubprocessError):
            raise BatchStop("a registered file is absent from the commit") from None
        if committed != raw:
            raise BatchStop("a registered file differs from its committed blob")
    a4 = one_shot._decode_object(a4_raw)
    if (a4.get("commit") != head or a4.get("remote_commit_verified") is not True
            or a4.get("user_agent_verified") is not True):
        raise BatchStop("A4/A11 remote verification differs")
    budget = one_shot._decode_object(budget_raw)
    verification = budget.get("verification", {})
    holds = budget.get("nonfinal_programme_liability_holds", {})
    status_gets = verification.get("one_shot_key_status_attempts_reserved")
    status_hold = holds.get("one_shot_key_status_get_usd")
    if (type(status_gets) is not int or status_gets not in range(1, 37) or type(status_hold) is not str
            or verification.get("a4_git_registration_attempt_slots_reserved") != 20
            or verification.get("one_shot_physical_attempts_reserved") != 1
            or verification.get("a11_git_registration_attempt_slots_reserved") != 20
            or holds.get("one_shot_original_attempt_usd") != "0.10"):
        raise BatchStop("one-shot or batch attempt reservations differ")
    try:
        if Decimal(status_hold) != Decimal("0.10") * status_gets:
            raise BatchStop("one-shot status liability hold differs")
    except InvalidOperation:
        raise BatchStop("one-shot status liability hold differs") from None
    selected = one_shot._decode_object(selection_raw)
    _validate_selection(selected)
    if (verification.get("a11_batch_targets_reserved") != selected["planned_target_pairs"]
            or holds.get("a11_batch_run_caps_usd") != selected["total_run_caps_usd"]):
        raise BatchStop("batch manifest reservations differ from the selection")
    status_record = budget.get("one_shot_key_status_preflight", {})
    with ExitStack() as stack:
        private = one_shot._open_absolute(one_shot._PRIVATE, stack)
        try:
            status_raw = one_shot._read_safe(private, "ONE_SHOT_KEY_STATUS_PRIVATE.jsonl", 1_000_000, private=True)
        except FileNotFoundError:
            raise BatchStop("no fresh key status has been recorded for this dispatch") from None
    one_shot._check_recent_key_status(status_raw, status_record.get("journal_sha256"),
                                      datetime.now(timezone.utc))
    return selected


def _spend_calls(raw: bytes) -> tuple[int, Decimal]:
    rows = one_shot._json_rows(raw)
    calls = [row for row in rows if row.get("event") == "call"]
    try:
        spent = sum((Decimal(str(row["usd"])) for row in calls), Decimal("0"))
    except (KeyError, TypeError, InvalidOperation):
        raise BatchStop("a spend log is invalid") from None
    return len(calls), spent


def _batch_context(selected: dict, stack: ExitStack) -> tuple[dict, list[RunSpec], int]:
    """Verify every original run against its pins; build the continuation specs."""
    try:
        return _batch_context_inner(selected, stack)
    except one_shot.ResumeRefusal as exc:
        raise BatchStop(str(exc)) from None


def _batch_context_inner(selected: dict, stack: ExitStack) -> tuple[dict, list[RunSpec], int]:
    workspace = one_shot._open_absolute(one_shot._WORKSPACE, stack)
    private = one_shot._open_absolute(one_shot._PRIVATE, stack)
    output = one_shot._descend(workspace, ("analysis", "coling", "out", "read"), stack)
    local = one_shot._descend(workspace, ("results", "coling", "read"), stack)
    launch = one_shot._descend(output, ("_launch",), stack)
    one_shot._lock_lanes(launch, stack)
    one_shot._check_f1_spend_log_paths(output)
    plan_raw = one_shot._read_safe(launch, "plan.json", 4_000_000)
    if sha256(plan_raw).hexdigest() != one_shot._PLAN_SHA:
        raise BatchStop("pinned launch plan differs")
    plan = one_shot._decode_object(plan_raw)
    if (type(plan.get("options")) is not dict or plan["options"].get("out_root") != "analysis/coling/out/read"
            or plan["options"].get("local_root") != "results/coling/read"):
        raise BatchStop("pinned launch roots differ")
    route = plan.get("routes", {}).get("gpt-oss-20b", {})
    if (route.get("model_id") != "openai/gpt-oss-20b" or route.get("provider") != "deepinfra/bf16"
            or route.get("quantization") != "bf16"):
        raise BatchStop("the launch plan no longer pins the original blocked route")
    ledger = one_shot._read_safe(output, "study_ledger.jsonl", 32_000_000)
    if sha256(ledger).hexdigest() != selected.get("ledger_sha256"):
        raise BatchStop("the study ledger changed after selection")
    snapshot = one_shot._descend(private, ("OSS_CHECKPOINT_BACKUP_2026-10-30",), stack)
    if os.fstat(snapshot).st_uid != os.geteuid() or stat.S_IMODE(os.fstat(snapshot).st_mode) != 0o700:
        raise BatchStop("checkpoint snapshot is not private")
    specs: list[RunSpec] = []
    prior_total = 0
    for entry in selected["runs"]:
        name = entry["run"]
        rows = [row for row in plan.get("runs", ()) if type(row) is dict and row.get("run") == name]
        if len(rows) != 1:
            raise BatchStop("a selected run is absent or duplicated in the launch plan")
        row = rows[0]
        if (row.get("model") != "gpt-oss-20b" or row.get("template") != entry["template"]
                or row.get("track") != entry["track"] or row.get("temperature") != 0
                or row.get("samples") != 1 or row.get("shard") != entry.get("shard")
                or row.get("limit") != entry.get("limit") or row.get("mask_names") != entry["mask_names"]
                or row.get("shift_years") != entry["shift_years"] or row.get("list") != entry["list"]
                or row.get("items") != entry["items"]
                or row.get("allow_test_items") != entry["allow_test_items"]):
            raise BatchStop("a selected plan row differs from its selection pin")
        items_dir = one_shot._descend(workspace, tuple(entry["items"].split("/")[:-1]), stack)
        items_raw = one_shot._read_safe(items_dir, entry["items"].rsplit("/", 1)[1], one_shot._MAX_CHECKPOINT)
        try:
            items_sha = plan["lists"][row["list"]]["sha256"]
        except (KeyError, TypeError):
            raise BatchStop("selected input identity is unavailable") from None
        if (sha256(items_raw).hexdigest() != items_sha
                or sha256(items_raw).hexdigest() != entry["items_sha256"]):
            raise BatchStop("a selected item file hash differs")
        track_path, track_sha, track_raw = None, None, None
        if row["track"]:
            try:
                track_spec = plan["tracks"][row["track"]]
                track_path, track_sha = track_spec["path"], track_spec["sha256"]
            except (KeyError, TypeError):
                raise BatchStop("selected track identity is unavailable") from None
            if track_sha != entry.get("track_sha256"):
                raise BatchStop("a selected track hash differs from its pin")
            track_dir = one_shot._descend(workspace, tuple(track_path.split("/")[:-1]), stack)
            track_raw = one_shot._read_safe(track_dir, track_path.rsplit("/", 1)[1], one_shot._MAX_CHECKPOINT)
            if sha256(track_raw).hexdigest() != track_sha:
                raise BatchStop("a selected track file hash differs")
        if entry["never_invoked"]:
            for base in (output, local):
                try:
                    one_shot._descend(base, (name,), stack)
                except OSError:
                    continue
                raise BatchStop("a never-invoked run unexpectedly has an output directory")
            index = one_shot.CheckpointIndex(frozenset(), frozenset())
            prior_calls, logged_calls, logged_spend = 0, 0, Decimal("0")
        else:
            out_run = one_shot._descend(output, (name,), stack)
            local_run = one_shot._descend(local, (name,), stack)
            snap_out = one_shot._descend(snapshot, ("out", name), stack)
            snap_local = one_shot._descend(snapshot, ("local", name), stack)
            contents = {}
            for original, saved, filename, field in (
                    (out_run, snap_out, "readings.jsonl", "readings_sha256"),
                    (out_run, snap_out, "run_manifest.json", "manifest_sha256"),
                    (out_run, snap_out, "spend_log.jsonl", "spend_log_sha256"),
                    (out_run, snap_out, "invocations.jsonl", "invocations_sha256"),
                    (local_run, snap_local, "responses.jsonl", "responses_sha256")):
                raw = one_shot._read_safe(original, filename, one_shot._MAX_CHECKPOINT)
                backup_raw = one_shot._read_safe(saved, filename, one_shot._MAX_CHECKPOINT, private=True)
                if filename in ("spend_log.jsonl", "invocations.jsonl"):
                    if not raw.startswith(backup_raw):
                        raise BatchStop("an append-only original log rewrote history")
                elif raw != backup_raw:
                    raise BatchStop("an original file differs from its verified snapshot")
                if sha256(raw).hexdigest() != entry[field]:
                    raise BatchStop("an original file differs from its selection pin")
                contents[filename] = raw
            manifest = one_shot._decode_object(contents["run_manifest.json"])
            if (manifest.get("complete") is not False
                    or type(manifest.get("readings")) is not int
                    or manifest.get("readings") != entry["recorded_readings"]):
                raise BatchStop("an original run is no longer partial at its recorded count")
            index = one_shot.index_checkpoint(
                contents["readings.jsonl"], contents["responses.jsonl"],
                expected_readings_sha256=entry["readings_sha256"],
                expected_responses_sha256=entry["responses_sha256"],
                expected_reading_count=manifest["readings"])
            logged_calls, logged_spend = _spend_calls(contents["spend_log.jsonl"])
            if (logged_calls != entry["logged_call_count"]
                    or logged_spend.quantize(Decimal("0.000001")) != _decimal(entry["logged_spend_usd"])):
                raise BatchStop("an original run's logged calls or spend differ")
            prior_calls = 0
        prior_dk = 0
        try:
            dk_out = one_shot._descend(output, (entry["new_run"],), stack)
        except OSError:
            dk_out = None
        if dk_out is not None:
            try:
                dk_spend = one_shot._read_safe(dk_out, "spend_log.jsonl", one_shot._MAX_CHECKPOINT)
            except FileNotFoundError:
                prior_dk = 0
            else:
                prior_dk, _ = _spend_calls(dk_spend)
            try:
                dk_manifest_raw = one_shot._read_safe(dk_out, "run_manifest.json", one_shot._MAX_CHECKPOINT)
            except FileNotFoundError:
                pass
            else:
                dk_manifest = one_shot._decode_object(dk_manifest_raw)
                if (dk_manifest.get("model") != "gpt-oss-20b"
                        or dk_manifest.get("provider_object") != {"order": ["dekallm/bf16"],
                                                                  "allow_fallbacks": False,
                                                                  "quantizations": ["bf16"]}
                        or dk_manifest.get("template") != entry["template"]
                        or dk_manifest.get("temperature") != 0 or dk_manifest.get("samples") != 1
                        or dk_manifest.get("shard") != entry.get("shard")):
                    raise BatchStop("an existing continuation run holds another identity")
        prior_total += prior_dk
        specs.append(RunSpec(original=name, new_run=entry["new_run"], row=row, index=index,
                             target=entry["target_pairs"], cap_usd=entry["run_cap_usd"],
                             projected_usd=entry["projected_usd"], items_path=entry["items"],
                             items_raw=items_raw, track_path=track_path, track_sha=track_sha,
                             never_invoked=entry["never_invoked"], prior_calls=prior_dk))
    if sum(spec.target for spec in specs) != selected["planned_target_pairs"]:
        raise BatchStop("the continuation targets differ from the selection total")
    return plan, specs, prior_total


def _release_reservations(read_module, launch_module, plan: dict, specs: list[RunSpec],
                          selected: dict) -> list[tuple[str, str]]:
    """Idempotently re-declare blocked original runs at their recorded spend."""
    if selected.get("release_blocked_reservations") is not True:
        raise BatchStop("the selection does not authorize reservation release")
    held = read_module.held_by_run(Path("analysis/coling/out/read"))
    released = []
    for spec in specs:
        if spec.never_invoked:
            continue
        entry = held.get(spec.original)
        if (type(entry) is not dict or entry.get("model") != "gpt-oss-20b"
                or entry.get("open") is not True):
            raise BatchStop("an original run is not open in the ledger")
        spent, cap = Decimal(str(entry["spent_usd"])), Decimal(str(entry["cap_usd"]))
        if cap <= spent + Decimal("0.000001"):
            continue
        args = launch_module.harness_args(plan, spec.row, "live")
        at = args.index("--spend-cap-usd")
        args[at + 1] = f"{spent:.6f}"
        args.remove("--allow-live")
        args += ["--declare-only"]
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = read_module.main(args)
        except (Exception, SystemExit) as error:
            raise BatchStop(("reservation release refused: " + str(error))[:200]) from None
        if code != 0:
            raise BatchStop("reservation release returned a refusal")
        released.append((spec.original, f"{spent:.6f}"))
    return released


def _check_batch_budget(read_module, specs: list[RunSpec]) -> None:
    """The owner's caps after the release, under the batch's sequential declarations.

    The runs are declared one at a time and each closes when it completes its
    target set, so at most one continuation cap is reserved beyond the spend
    already banked. The pre-check below bounds that worst moment: everything
    other runs of the model hold, plus the whole projected continuation spend,
    plus the largest single run's reservation overhead. The frozen reader's own
    declaration check enforces the running bound during the batch and stops it
    cleanly (before any request) if an overrun appears; this wrapper fence only
    refuses a selection that could not even start. Study bound: the stricter
    F1 ceiling of $200 with a $0.50 buffer, as the one-shot gate used.
    """
    held = read_module.held_by_run(Path("analysis/coling/out/read"))
    new_names = {spec.new_run for spec in specs}
    projected = sum((Decimal(spec.projected_usd) for spec in specs), Decimal("0"))
    worst_open = max((Decimal(spec.cap_usd) - Decimal(spec.projected_usd) for spec in specs),
                     default=Decimal("0")) + Decimal("0.02")
    other_model = sum((Decimal(str(row["held_usd"])) for key, row in held.items()
                       if key not in new_names and row.get("model") == "gpt-oss-20b"), Decimal("0"))
    other_study = sum((Decimal(str(row["held_usd"])) for key, row in held.items()
                       if key not in new_names), Decimal("0"))
    if other_model + projected + worst_open > Decimal("10") + Decimal("0.000001"):
        raise BatchStop("the local model cap would be exceeded")
    if other_study + projected + worst_open + Decimal("0.50") > Decimal("200"):
        raise BatchStop("the stricter F1 study cap would be exceeded")
    for spec in specs:
        entry = held.get(spec.new_run)
        if entry is not None and Decimal(spec.cap_usd) < Decimal(str(entry["spent_usd"])):
            raise BatchStop("a continuation run cap is below its recorded spend")


def _track_from_verified_bytes(raw: bytes, name: str):
    """Parse the exact bytes whose digest was pinned (A24), never a second path read.

    This mirrors the frozen reader's ``load_track_record`` validation without reopening the
    file: a replacement between the hash read and a parse read must not change the record
    that reaches a prompt. The frozen reader itself is not edited.
    """
    from analysis.coling import read as frozen_read

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{name} is not a UTF-8 JSON file: {exc}") from None
    found = frozen_read.track_file_errors(data)
    if found:
        raise ValueError(f"{name} is not a valid track record: " + "; ".join(found))
    track = frozen_read.TrackRecord(
        through=data["through"],
        slip_table=tuple(frozen_read.SlipRow(**row) for row in data["slip_table"]),
        examples=tuple(frozen_read.ResolvedExample(**ex) for ex in data["examples"]),
        since=data["since"], split=data["split"], min_cell=data["min_cell"],
        sha256=sha256(raw).hexdigest())
    track.check()
    return track


def _install_batch_hooks(read_module, endpoints_module, openai_module, httpx_module, cache_module,
                         batch_transport_module, specs: list[RunSpec], *, send_journal_fd: int,
                         stop_after_utc: datetime) -> tuple[object, object, dict]:
    """Install the A11 runtime changes; tests provide fake modules only."""
    route = read_module.Route("openai/gpt-oss-20b", "dekallm/bf16", "bf16", _PRICE)
    if read_module.provider_object(route) != batch_transport_module.PROVIDER:
        raise BatchStop("the runtime route pin differs from the registered transport")
    if read_module.ROUTES["gpt-oss-20b"].provider != "deepinfra/bf16":
        raise BatchStop("the frozen route table was already changed")
    original_cache = read_module.ReadCache
    original_guard = read_module.GuardedTransport
    original_openai = openai_module.OpenAI
    original_sha = read_module._sha256_file
    # The frozen harness passes the plan's RELATIVE roots while the module constants are
    # absolute (the one-shot wrapper hit the same trap); every pinned-key comparison is
    # therefore made on the normalized absolute spelling, which asks nothing of the
    # filesystem.
    items_by_path = {os.path.abspath(spec.items_path): (spec.items_raw, sha256(spec.items_raw).hexdigest())
                     for spec in specs}
    items_list_by_path = {os.path.abspath(spec.items_path): one_shot._pinned_items(read_module, spec.items_raw, spec.items_path)
                          for spec in specs}
    track_paths = {os.path.abspath(spec.track_path) for spec in specs if spec.track_path is not None}
    readings_paths = {str(Path(os.path.abspath(read_module.OUT_ROOT)) / spec.new_run / "readings.jsonl")
                      for spec in specs}
    read_path = os.path.abspath(read_module.__file__)
    state = {"spec": None}

    class PinnedCache(original_cache):
        def _root_name(self):
            if str(self.root) not in ("results/coling/read/cache", cache_module.REAL_ROOT):
                raise BatchStop("F1 cache root differs")
            return cache_module.REAL_ROOT

        def get(self, key):
            return cache_module.get(self._root_name(), key)

        def put(self, key, raw, served=None):
            return cache_module.put(self._root_name(), key, text=raw.text, prompt_tokens=raw.prompt_tokens,
                                    completion_tokens=raw.completion_tokens, total_tokens=raw.total_tokens,
                                    served=served)

    class BatchGuard(original_guard):
        def __init__(self, *args, **kwargs):
            for name, wanted in (("max_attempts", 6), ("min_interval_s", batch_transport_module.MIN_SPACING_S),
                                 ("base_delay_s", 8.0), ("max_delay_s", 240.0)):
                if name in kwargs and kwargs[name] != wanted:
                    raise BatchStop("unexpected F1 retry override")
                kwargs[name] = wanted
            super().__init__(*args, **kwargs)

        def _log(self, row):
            sanitized = dict(row)
            if "error" in sanitized:
                sanitized["error"] = "details withheld by batch guard"
            return super()._log(sanitized)

    inner = httpx_module.HTTPTransport(verify=True, trust_env=False, retries=0)
    # A19: the only addresses a send may carry are the public contact addresses of the
    # hash-pinned items themselves; the earlier body-wide "@" ban refused one of them.
    allowed_addresses = frozenset().union(
        *(batch_transport_module.public_addresses(spec.items_raw) for spec in specs))
    physical = batch_transport_module.CountedPacedTransport(
        inner, send_journal_fd, selection_sha256=_BATCH_SELECTION_SHA,
        planned_targets=sum(spec.target for spec in specs),
        max_sends=2 * sum(spec.target for spec in specs) + 12 * len(specs) + 600,
        stop_after_utc=stop_after_utc, allowed_addresses=allowed_addresses)
    client = httpx_module.Client(transport=physical, trust_env=False, follow_redirects=False, timeout=240.0)

    def pinned_openai(*args, **kwargs):
        if (args or kwargs.get("base_url") != "https://openrouter.ai/api/v1" or kwargs.get("max_retries") != 0
                or "default_headers" in kwargs or "http_client" in kwargs):
            raise BatchStop("F1 client configuration differs")
        kwargs["default_headers"] = {"User-Agent": batch_transport_module.USER_AGENT}
        kwargs["http_client"] = client
        return original_openai(**kwargs)

    def pinned_load(path):
        key = os.path.abspath(os.fspath(path))
        if key not in items_by_path:
            raise BatchStop("F1 requested an unregistered input path")
        return list(items_list_by_path[key])

    def pinned_track(path):
        key = os.path.abspath(os.fspath(path))
        if key not in track_paths:
            raise BatchStop("F1 requested an unregistered track path")
        # A21: only specs that carry a track may be compared. The A11 generator below ran
        # os.path.abspath over every spec, and the untracked runs carry track_path None, so the
        # first track-condition run (e3-b.s0, 10 November 2026) stopped before its first send.
        owner = next((spec for spec in specs if spec.track_path is not None
                      and os.path.abspath(spec.track_path) == key), None)
        if owner is None:
            raise BatchStop("F1 requested an unregistered track path")
        raw = Path(key).read_bytes()
        if sha256(raw).hexdigest() != owner.track_sha:
            raise BatchStop("a track file changed after verification")
        # A24: parse these verified bytes; a second read of the path could return a
        # replacement that was never hash-checked.
        return _track_from_verified_bytes(raw, Path(key).name)

    def pinned_sha(path):
        key = os.path.abspath(os.fspath(path))
        if key in items_by_path:
            return items_by_path[key][1]
        if key == read_path:
            return one_shot._READ_SHA
        if key in readings_paths and state["spec"] is not None and key.endswith(state["spec"].new_run + "/readings.jsonl"):
            return original_sha(Path(key))
        raise BatchStop("F1 requested an unregistered file hash")

    def filtered(reader, items, *, samples=1, rows=None):
        spec = state["spec"]
        if spec is None:
            raise BatchStop("no continuation run is selected")
        rows = [] if rows is None else rows
        got, status = one_shot.filtered_read_items(read_module, reader, items, samples=samples,
                                                   rows=rows, index=spec.index)
        if status.startswith("aborted:"):
            return got, status
        if len(got) != spec.target:
            return got, f"partial: batch read {len(got)} of {spec.target} target pairs"
        return got, "complete"

    read_module.ROUTES["gpt-oss-20b"] = route
    read_module.ReadCache = PinnedCache
    read_module.GuardedTransport = BatchGuard
    read_module.load_items = pinned_load
    read_module.load_track_record = pinned_track
    read_module._sha256_file = pinned_sha
    read_module.read_items = filtered
    endpoints_module.EMPTY_ECHO_RETRIES = 0
    openai_module.OpenAI = pinned_openai
    return client, physical, state


def _new_stage(parent_fd: int, stack: ExitStack) -> int:
    name = _BATCH_STAGE_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    stage = os.open(name, one_shot._DIR, dir_fd=parent_fd)
    stack.callback(os.close, stage)
    info = os.fstat(stage)
    visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(visible.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or (info.st_dev, info.st_ino) != (visible.st_dev, visible.st_ino)):
        raise BatchStop("new private batch stage identity differs")
    os.fsync(parent_fd)
    return stage


def _journal_rows(fd: int, rows: list[dict]) -> None:
    raw = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
                   for row in rows)
    one_shot._write_all(fd, raw)
    os.fsync(fd)


def _run_batch(read_module, launch_module, plan: dict, specs: list[RunSpec], state: dict,
               physical, stage_fd: int, batch_journal_fd: int) -> dict:
    """Run each continuation run to its target; stop and report on any shortfall."""
    summary_rows = []
    stopped = None
    for spec in specs:
        state["spec"] = spec
        physical.set_run(spec.new_run)
        args = launch_module.harness_args(plan, spec.row, "live")
        at = args.index("--run-name")
        args[at + 1] = spec.new_run
        at = args.index("--spend-cap-usd")
        args[at + 1] = spec.cap_usd
        args += ["--model-cap-usd", "10", "--amendment", "A2: prospective gpt-oss cap 10",
                 "--max-physical-calls", str(spec.prior_calls + 2 * spec.target + 12)]
        _journal_rows(batch_journal_fd, [{"event": "run_intent", "run": spec.new_run,
                                          "original_run": spec.original, "target_pairs": spec.target,
                                          "run_cap_usd": spec.cap_usd,
                                          "max_physical_calls": spec.prior_calls + 2 * spec.target + 12}])
        stdout, stderr = io.StringIO(), io.StringIO()
        code, error_type = None, None
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = read_module.main(args)
        except (Exception, SystemExit) as error:
            error_type = f"raised {type(error).__name__}: {error}"[:200]
        out_dir = Path(read_module.OUT_ROOT) / spec.new_run
        try:
            manifest = json.loads((out_dir / "run_manifest.json").read_text())
        except (OSError, ValueError):
            manifest = {}
        row = {"event": "run_result", "run": spec.new_run, "f1_return_code": code,
               "error_type": error_type, "status": manifest.get("status"),
               "readings": manifest.get("readings"), "target_pairs": spec.target,
               "guard": manifest.get("guard")}
        ok = (code == 0 and error_type is None and manifest.get("status") == "complete"
              and manifest.get("readings") == spec.target)
        if ok:
            try:
                calls, spent = _spend_calls((out_dir / "spend_log.jsonl").read_bytes())
            except (OSError, one_shot.ResumeRefusal, BatchStop) as exc:
                row["close_error"] = type(exc).__name__
                row["closed"] = False
                stopped = spec.new_run
            else:
                read_module.close_run(Path("analysis/coling/out/read"), run=spec.new_run,
                                      model="gpt-oss-20b", spent_usd=float(spent))
                row["closed"] = True
                row["logged_calls"] = calls
                row["logged_spend_usd"] = f"{spent:.6f}"
        else:
            row["closed"] = False
            stopped = spec.new_run
        summary_rows.append(row)
        _journal_rows(batch_journal_fd, [row])
        if stopped is not None:
            _journal_rows(batch_journal_fd, [{"event": "batch_stopped", "run": stopped}])
            break
    return {"runs": summary_rows, "stopped_run": stopped,
            "complete_runs": sum(1 for row in summary_rows if row["closed"])}


def main() -> None:
    if sys.argv[1:] != ["--execute-registered-batch"]:
        raise SystemExit("This batch continuation requires its exact registered execution flag.")
    if os.path.realpath(os.getcwd()) != os.path.realpath(one_shot._WORKSPACE):
        raise SystemExit("This batch continuation must run from the registered study worktree root.")
    try:
        selected = _verify_batch_registration()
        import httpx
        import openai
        from analysis.coling import launch, read
        from analysis.commitment import endpoints
        from analysis.coling.followup import oss_one_shot_cache, oss_batch_transport

        if httpx.__version__ != "0.28.1" or openai.__version__ != "1.109.1":
            raise BatchStop("HTTPX or OpenAI SDK version differs")
        designated = "/data/noctis/GitHub-Data/COLLIE/cloud_endpoint/openrouter.key"
        if not os.path.samefile(os.path.join(one_shot._WORKSPACE, "cloud_endpoint/openrouter.key"), designated):
            raise BatchStop("F1 key-file identity differs")
        with ExitStack() as stack:
            plan, specs, prior_total = _batch_context(selected, stack)
            released = _release_reservations(read, launch, plan, specs, selected)
            _check_batch_budget(read, specs)
            stage = _new_stage(one_shot._open_absolute(one_shot._PRIVATE, stack), stack)
            batch_journal = os.open(
                "batch.journal.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT
                | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=stage)
            stack.callback(os.close, batch_journal)
            send_journal = os.open(
                "send.journal.jsonl", _SEND_JOURNAL_OPEN, 0o600, dir_fd=stage)
            stack.callback(os.close, send_journal)
            _journal_rows(batch_journal, [
                {"event": "reserved", "selection_sha256": _BATCH_SELECTION_SHA,
                 "planned_target_pairs": selected["planned_target_pairs"], "runs": len(specs),
                 "prior_dk_calls": prior_total, "reservation_release": "registered",
                 "released_runs": len(released),
                 "hold_is_proven_maximum": False}])
            one_shot._write_all(send_journal, oss_batch_transport.batch_reservation_bytes(
                _BATCH_SELECTION_SHA, selected["planned_target_pairs"],
                2 * selected["planned_target_pairs"] + 12 * len(specs) + 600))
            os.fsync(send_journal)
            os.fsync(stage)
            client, physical, state = _install_batch_hooks(
                read, endpoints, openai, httpx, oss_one_shot_cache, oss_batch_transport, specs,
                send_journal_fd=send_journal, stop_after_utc=one_shot._DEADLINE - timedelta(seconds=10))
            stack.callback(client.close)
            result = _run_batch(read, launch, plan, specs, state, physical, stage, batch_journal)
            summary = {"scope": "paced-batch-dekallm-continuation", "selection_sha256": _BATCH_SELECTION_SHA,
                       "runs": len(result["runs"]), "complete_runs": result["complete_runs"],
                       "stopped_run": result["stopped_run"], "automatic_retry": False,
                       "originals_untouched": True, "released_reservations": len(released)}
            one_shot._exclusive(stage, "execution_summary.json",
                                (json.dumps(summary, sort_keys=True, indent=2) + "\n").encode())
    except (Exception, SystemExit):
        raise SystemExit("Paced batch continuation stopped; review private state before any retry.") from None
    print("Paced batch continuation ended; inspect the private journals and summary for its recorded outcome.")
    print("No registered evaluator or sealed outcome was read; original runs were not modified.")


if __name__ == "__main__":
    main()
