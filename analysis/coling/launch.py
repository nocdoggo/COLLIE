"""The launcher of the model runs of the COLING 2027 study: the run sheet of the reading harness
as an ordered, resumable list of runs, started lane by lane under tmux.

The harness (:mod:`analysis.coling.read`) makes one run at a time and holds every rule on paid
calls: the registration and F1 tags, the routes, the pilot sentences, the caps and the study
ledger. This module only decides *which* command comes next. It calls the harness's own command
line (``python -m analysis.coling.read ... --allow-live``), never a client, and it reads no key;
whatever the harness refuses stays refused, and the launcher stops there and says why.

The plan (``plan``)
-------------------
A plan is the full list of runs, written to ``<out-root>/_launch/plan.json`` with one run per
line. It is made from two things only: the run sheet the harness prints (:func:`read.run_sheet`:
which template reads which item set, by which models, with which cap) and the item files
(``dataset.py --items`` and the two samplers; see ``LISTS``). Nothing is drawn at random: the
order is a sort, and the items of a shard are the harness's own (:func:`read.shard_of`). The same
inputs give the same bytes.

* A run is one model, one template and one condition under one run name (PLAN section 9). A
  sheet line that covers several item lists or conditions becomes several runs (``PARTS``): the
  three secondary lists, the three masked or shifted cells of the 2x2, the three paraphrases.
* Caps. The harness's suggested cap of a line is split over the runs of the line in proportion
  to their calls, in millionths of a dollar. The harness rounds its caps down, so they sum to a
  little under the model's cap; the remainder (under one cent) goes to the model's largest line.
  The caps of a model's runs, with what is held back for runs that cannot be written yet
  (``reserved``), then sum to the model's cap exactly.
* Phases, in the order of PLAN sections 9 and 12:

  - ``trial``: the cost trial, the first 20 dev prompt items per template a model uses;
  - ``dev``: conditions (a), (b) and (c) on the scoreable dev statements, both primaries;
  - ``confirmatory``: E3 conditions (a), (b), (c) and the E4 probe, both primaries, on every
    eligible statement and on the probe subset;
  - ``rest``: everything else (E2, E5, the primaries' secondary lists, 2x2, paraphrases and
    20 samples, and the six other models).

* Lanes. One lane per provider account: ``google`` (gemini-3.8-flash), ``xai`` (grok-4.20) and
  ``openrouter`` (the other six). Within a phase and a lane the runs go cheapest first.
  ``--shards LANE=N`` splits every run of a lane with at least ``SHARD_MIN_CALLS`` calls per
  shard into N runs (``--shard K/N``), read side by side by N workers.

Starting (``run``)
------------------
By default ``run`` prints the commands and what stands in their way. ``--rehearse`` starts the
lanes under tmux and gives every command to the harness as a dry run (no call). ``--live`` starts
them with ``--allow-live``; nothing else makes a paid call. Each lane is started detached under
tmux, as ``coling-<lane>`` on the tmux socket ``coling``, with one window per worker, and no lane
waits for another.

The harness finds its key by itself (``EndpointConfig.resolve_key``): in the environment first,
then in the key file of the checkout that is run. The launcher reads no key and puts none on a
command line. A window gets the environment of the tmux *server*, and the server on the socket
``coling`` takes the environment of the shell that starts it only when it is started: while a
lane of an earlier start is still running, a new lane gets that earlier environment, not the one
of the shell it is started from (``run`` says so when it starts a lane on a server that is
already up). Key files do not depend on any of this.

Before a live lane starts, and again before each of its runs:

* the registration tag for every phase, and the F1 tag for ``confirmatory`` and ``rest``
  (:func:`read.paid_call_refusals`; the harness checks both again);
* the phase order inside the lane: the runs of an earlier phase, for the models asked for, are
  finished or queued ahead in the same start. A worker waits for such a run only while the
  worker that is to read it is alive; a run that no worker of the start will finish (it is not
  queued, or the plan has no file for it) ends the wait at once;
* the plan on disk is the plan its inputs give now, and the item and track-record files have the
  hashes the plan holds.

A run is *finished* when the harness's ``run_manifest.json`` says ``complete`` for the run the
plan describes (the model, the model id and the provider pin that are sent, the template and its
pin, the condition, the shard and the item set), and only then is it skipped; a run that is not
finished is started again under its name, and the harness resumes it from its cache. A manifest
that is complete for anything else stops the lane. What a route says beside the request (its
price, the names it accepts in the echo) is not part of this: entering those at F1 leaves the
cost trial and the dev runs finished.

Every command, its start, end and exit status go to ``<out-root>/_launch/run_log.jsonl``, the
harness's output to ``_launch/output/<run>.log``, and what a worker prints to
``_launch/lanes/<lane>.w<K>.log``. A lane stops at the first run that the harness refuses or
that fails, with the reason in the log, and every worker of the lane stops with it; the other
lanes go on. A run whose item file or track record was not on disk when the plan was made is
left where it is (the plan says so, and ``blocked`` lists it) and does not stop its lane.
``--model`` limits a start to some models, so that a lane can go on without one that cannot
run. A cap is never raised here: a run that its cap stopped is resumed by hand with the
harness's ``--model-cap-usd`` and ``--amendment`` (PLAN section 9), or under a new plan made
with the cost trial's ``--per-call-usd``. The harness keeps a model cap raised that way for the
model's later runs, so the rest of the lane goes on under it with the plan's run caps; a run
resumed by hand under a higher run cap has to be finished by hand, because the launcher would
start it again under the plan's.

Watching (``status``, ``check``, ``blocked``)
---------------------------------------------
``status`` prints counts only, per run and per lane: rows done and left, paid calls, dollars
against the cap, repairs, failed and refused readings. It reads the manifests, the spend logs,
the caps declared in the ledger and the launcher's own log, and prints no answer, no item and
no message of a provider.
``check`` says whether every confirmatory run is finished with its registered item set, using
the harness's completeness check (:func:`read.check_runs`) on those runs alone, named to it.
``blocked`` lists what a live start would be refused for today, by missing value, and says
first when the plan itself has to be made again.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.launch plan --items-dir analysis/coling/out/items \\
        [--items-file LIST=PATH] [--count LIST=N] [--track-fit PATH] [--track-fit-dev PATH] \\
        [--shards google=4] [--price MODEL=IN,OUT] [--per-call-usd MODEL=USD] [--check]
    PYTHONPATH=. python -m analysis.coling.launch run --phase trial [--phase dev] \\
        [--lane google] [--model llama-3.3-70b] [--rehearse | --live]
    PYTHONPATH=. python -m analysis.coling.launch status [--phase trial] [--lane google]
    PYTHONPATH=. python -m analysis.coling.launch check
    PYTHONPATH=. python -m analysis.coling.launch blocked
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from analysis.coling import read as rd

PHASES = ("trial", "dev", "confirmatory", "rest")
SEALED_PHASES = ("confirmatory", "rest")
"""The phases that read test-period items: they wait for the freeze amendment F1."""
CONFIRMATORY_LINES = ("e3-a", "e3-b", "e3-c", "e4-probe")
"""The sheet lines that, read by a primary, are the confirmatory runs of PLAN section 6."""
LANE_OF = {"gemini": "google", "grok": "xai", "openrouter": "openrouter"}
"""The lane of a ladder provider: one lane per provider account."""
LANES = ("google", "xai", "openrouter")
"""The lanes in the order they are started: the Google lane first."""
OUT_ROOT = Path("analysis/coling/out/read")
LOCAL_ROOT = Path("results/coling/read")
"""The harness's two roots, as paths from the repository root, so that a plan names no folder
of one machine."""
ITEMS_DIR = Path("analysis/coling/out/items")
LAUNCH_DIR = "_launch"
"""The launcher's folder under the output root. No run can have this name."""
PLAN_NAME = "plan.json"
RUN_LOG = "run_log.jsonl"
TMUX_SOCKET = "coling"
SHARD_MIN_CALLS = 50
"""A run is split into N shards only if each shard then has this many calls on average."""
MICRO = 1_000_000
"""Caps are split in whole millionths of a dollar."""
PARAPHRASE_PREFIX = "predictive-track-p"
"""The ids of the three paraphrases of ``predictive-track-v1`` start with this (for example
``predictive-track-p1-v1``); until the harness holds three such templates, their runs are not
planned and their share of the caps is held back."""
WAIT_S = 20.0
LOCK_TRIES = 5
LOCK_PAUSE_S = 0.05
"""A worker asks for its lock this many times, this far apart: :func:`workers_alive` holds a
free lock for an instant while it looks, and must not pass for a worker that is running."""
STALE = "the plan on disk is not the plan its inputs give now; make the plan again"
REASON_CHARS = 400
RUN_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
"""What the harness accepts as a run name."""
MODES = ("print", "rehearsal", "live")


# ---------------------------------------------------------------------------------------------
# Item lists and the runs of a sheet line
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemList:
    """One item list of the study: where its file is expected and which count of the run sheet
    it adds to."""

    key: str
    """The name used with ``--count`` and ``--items-file``."""
    stem: str
    """The file is ``<items-dir>/<stem>.jsonl`` unless ``--items-file`` names another."""
    count: str
    """The count of the run sheet (``read.SHEET_COUNTS``) the list adds to."""
    source: str
    """What writes the file."""
    planned: int | None = None
    """The size the plan fixes, used while the file is not on disk (None: not fixed)."""
    limit: int | None = None
    """Read only the first N items of the file (the harness's ``--limit``)."""


LISTS: tuple[ItemList, ...] = (
    ItemList(
        "e2",
        "literal_items",
        "e2",
        "audit_sample.py sheets --task literal, as analysis/coling/out/audit/literal_items.jsonl: "
        "copy it, or name it with --items-file e2=PATH",
        120,
    ),
    ItemList("e3", "e3_eligible", "e3", "dataset.py --items"),
    ItemList("tbd", "e3_tbd", "e3_secondary", "dataset.py --items"),
    ItemList("silent", "e3_silent", "e3_secondary", "dataset.py --items"),
    ItemList("stale", "e3_stale", "e3_secondary", "dataset.py --items"),
    ItemList("probe", "subset_probe", "probe", "dataset.py --items", 300),
    ItemList("samples", "subset_samples20", "samples", "dataset.py --items", 300),
    ItemList("paraphrase", "subset_paraphrase", "paraphrase", "dataset.py --items", 200),
    ItemList("twobytwo", "subset_twobytwo", "twobytwo", "dataset.py --items", 300),
    ItemList("dev", "dev_scoreable", "dev", "dataset.py --items"),
    ItemList("trial", "dev_prompt", "trial", "dataset.py --items", 20, limit=20),
    ItemList(
        "e5",
        "e5_pairs",
        "e5",
        "minimal_pairs.py generate, as analysis/coling/out/e5/e5_pairs.jsonl: copy it, or name "
        "it with --items-file e5=PATH",
        800,
    ),
    ItemList("e6", "e6_items", "e6", "E6's amendment", 0),
)
"""The item lists, with the file stems ``dataset.item_lists`` names for those it writes and
``dataset.TRIAL`` for the cost trial (written once the dev prompt list of ``audit_sample.py
draw-later`` is on disk). The two track records (``track_fit.json`` and ``track_fit_dev.json``,
see :func:`default_options`) are written by ``track_record.py --out <items-dir>``."""
LIST_BY_KEY = {spec.key: spec for spec in LISTS}


@dataclass(frozen=True)
class Part:
    """One run a model makes for a sheet line: an item list read under one condition."""

    name: str
    """The run name without the model (and without the shard)."""
    items: str
    """The key of the item list."""
    condition: str
    """The condition in the plan's words."""
    template: str | None = None
    """The template id; None for the template of the sheet line."""
    samples: int = 1
    temperature: float = 0.0
    mask_names: bool = False
    shift_years: int = 0


SHIFT_YEARS = 4
PARTS: dict[str, tuple[Part, ...]] = {
    "e2-literal": (Part("e2-literal", "e2", "literal"),),
    "e2-literal-free": (Part("e2-literal-free", "e2", "literal-free"),),
    "e3-a": (Part("e3-a", "e3", "a"),),
    "e3-b": (Part("e3-b", "e3", "b"),),
    "e3-c": (Part("e3-c", "e3", "c"),),
    "e4-probe": (Part("e4-probe", "probe", "probe"),),
    "e5": (Part("e5", "e5", "literal"),),
    "trial-literal": (Part("trial-literal", "trial", "literal"),),
    "trial-literal-free": (Part("trial-literal-free", "trial", "literal-free"),),
    "trial-a": (Part("trial-a", "trial", "a"),),
    "trial-b": (Part("trial-b", "trial", "b"),),
    "trial-probe": (Part("trial-probe", "trial", "probe"),),
    "e3-secondary-a": tuple(Part(f"e3-{k}-a", k, "a") for k in ("tbd", "silent", "stale")),
    "e3-secondary-b": tuple(Part(f"e3-{k}-b", k, "b") for k in ("tbd", "silent", "stale")),
    "e3-secondary-c": tuple(Part(f"e3-{k}-c", k, "c") for k in ("tbd", "silent", "stale")),
    "dev-a": (Part("dev-a", "dev", "a"),),
    "dev-b": (Part("dev-b", "dev", "b"),),
    "dev-c": (Part("dev-c", "dev", "c"),),
    "e4-2x2": (
        Part("e4-2x2-mask", "twobytwo", "b, names masked", mask_names=True),
        Part("e4-2x2-shift", "twobytwo", "b, dates shifted", shift_years=SHIFT_YEARS),
        Part(
            "e4-2x2-mask-shift",
            "twobytwo",
            "b, names masked and dates shifted",
            mask_names=True,
            shift_years=SHIFT_YEARS,
        ),
    ),
    "e3-samples": (Part("e3-samples", "samples", "a, 20 samples", samples=20, temperature=1.0),),
}
"""The runs of every sheet line but two: the paraphrases, whose templates are looked up in the
harness (:func:`parts_of`), and E6, whose prompt and items come with its amendment."""
E6_WHY = "E6 has no prompt and no item set before its amendment"


def paraphrase_templates() -> list[str]:
    """The ids of the paraphrase templates the harness holds, sorted."""
    return sorted(t for t in rd.TEMPLATES if t.startswith(PARAPHRASE_PREFIX))


def parts_of(line: rd.SheetLine) -> tuple[tuple[Part, ...], str]:
    """The runs one model makes for a sheet line, or none with the reason."""
    if line.name == "e6":
        return (), E6_WHY
    if line.name == "e3-paraphrases":
        found = paraphrase_templates()
        if len(found) != line.per_item:
            return (), (
                f"read.TEMPLATES holds {len(found)} paraphrase templates of predictive-track-v1 "
                f"(ids starting {PARAPHRASE_PREFIX!r}); the plan needs {line.per_item}"
            )
        return tuple(
            Part(f"e3-para{n}", "paraphrase", f"b, paraphrase {n}", template=t)
            for n, t in enumerate(found, start=1)
        ), ""
    if line.name not in PARTS:
        raise SystemExit(f"the run sheet has a line the launcher has no rule for: {line.name!r}")
    return PARTS[line.name], ""


def check_rules() -> None:
    """Stop when the launcher's rules and the harness's run sheet no longer say the same: every
    line has its runs, on the lists that make up the line's count, with the line's calls per
    item."""
    known = {spec.count for spec in LISTS}
    for line in rd.RUN_SHEET:
        if line.count not in known:
            raise SystemExit(f"sheet line {line.name!r} counts {line.count!r}: no item list")
        parts, _ = parts_of(line)
        if not parts:
            continue
        wanted = {spec.key for spec in LISTS if spec.count == line.count}
        per_list = {key: sum(p.samples for p in parts if p.items == key) for key in wanted}
        if {p.items for p in parts} != wanted or set(per_list.values()) != {line.per_item}:
            raise SystemExit(
                f"sheet line {line.name!r} ({line.count} x {line.per_item}) and the launcher's "
                f"runs for it disagree: {per_list}"
            )


def lane_of(model: str) -> str:
    return LANE_OF[rd.LADDER[model].provider]


def phase_of(line: rd.SheetLine, model: str) -> str:
    if line.experiment in ("trial", "dev"):
        return line.experiment
    if line.name in CONFIRMATORY_LINES and model in rd.PRIMARIES:
        return "confirmatory"
    return "rest"


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_sha256(ids: Iterable[str]) -> str:
    """One digest for a set of item ids, as the harness writes it to a run's manifest: the
    sha256 of the sorted ids, one per line."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


def split_units(total: int, weights: Sequence[int]) -> list[int]:
    """``total`` whole units split in proportion to the weights (largest remainder; ties go to
    the earlier part), so that the parts sum to the total exactly."""
    whole = sum(weights)
    if total < 0 or whole <= 0 or any(w < 0 for w in weights):
        raise ValueError("a split needs a non-negative total and weights that are not all zero")
    parts = [total * w // whole for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % whole), i))
    for i in order[: total - sum(parts)]:
        parts[i] += 1
    return parts


def read_jsonl(path: Path) -> list[dict]:
    """The rows of a JSON Lines file ([] when there is none). A last line that does not parse is
    one a run in flight is still writing, and is left out."""
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for n, line in enumerate(lines, start=1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if n < len(lines):
                raise
    return rows


def launch_dir(plan: Mapping[str, Any]) -> Path:
    return Path(plan["options"]["out_root"]) / LAUNCH_DIR


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_launch_id() -> str:
    """A name for one start of the lanes: the time to the microsecond."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on ``path`` (created if missing)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def log_event(folder: Path, **row: Any) -> None:
    """One line of the run log, written under a lock: the workers of every lane share it."""
    folder.mkdir(parents=True, exist_ok=True)
    with locked(folder / f"{RUN_LOG}.lock"), (folder / RUN_LOG).open("a", encoding="utf-8") as out:
        out.write(json.dumps({"ts": now(), **row}, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------------------------


def default_options(items_dir: Path) -> dict[str, Any]:
    """The options of a plan, with nothing given but the folder of the item files."""
    return {
        "items_dir": items_dir.as_posix(),
        "items_files": {},
        "counts": {},
        "tracks": {
            "fit": (items_dir / "track_fit.json").as_posix(),
            "fit+dev": (items_dir / "track_fit_dev.json").as_posix(),
        },
        "shards": {},
        "prices": {},
        "per_call_usd": {},
        "repair_rate": 0.0,
        "sheet_items": None,
        "out_root": OUT_ROOT.as_posix(),
        "local_root": LOCAL_ROOT.as_posix(),
    }


def list_record(spec: ItemList, options: Mapping[str, Any]) -> tuple[dict, list[str] | None]:
    """What the plan holds about an item list, and its item ids when the file is on disk."""
    given = options["items_files"].get(spec.key)
    path = Path(given) if given else Path(options["items_dir"]) / f"{spec.stem}.jsonl"
    count = options["counts"].get(spec.key)
    record: dict[str, Any] = {"path": path.as_posix(), "written_by": spec.source}
    if not path.is_file():
        size = spec.planned if count is None else count
        if size is None:
            raise SystemExit(
                f"list {spec.key!r}: {path} is not on disk and the plan fixes no size for it; "
                f"write the file ({spec.source}) or give --count {spec.key}=N"
            )
        size = size if spec.limit is None else min(size, spec.limit)
        record |= {"on_disk": False, "items": size, "items_in_file": None, "limit": spec.limit}
        return record | {"sha256": None, "item_ids_sha256": None, "sealed_items": None}, None
    try:
        items = rd.load_items(path)
    except (ValueError, KeyError) as exc:
        raise SystemExit(f"list {spec.key!r}: {path} is not an item file: {exc}") from exc
    limit = spec.limit if spec.limit is not None and len(items) > spec.limit else None
    read = items[:limit]
    if count is not None and count != len(read):
        raise SystemExit(f"list {spec.key!r}: {path} holds {len(read)} items, not --count {count}")
    ids = [item.item_id for item in read]
    record |= {
        "on_disk": True,
        "items": len(read),
        "items_in_file": len(items),
        "limit": limit,
        "sha256": sha256_file(path),
        "item_ids_sha256": ids_sha256(ids),
        "sealed_items": sum(1 for item in read if item.period in rd.SEALED_PERIODS),
    }
    return record, ids


def track_record(path: str) -> dict:
    """The path and hash of a track-record file. The file is hashed, never parsed: it holds
    train-period outcomes, and only the harness reads those."""
    on_disk = Path(path).is_file()
    return {
        "path": path,
        "on_disk": on_disk,
        "sha256": sha256_file(Path(path)) if on_disk else None,
    }


def shards_of(
    ids: Sequence[str] | None, items: int, samples: int, shards: int, limit: int | None
) -> list[tuple[int | None, int, str | None]]:
    """How a run is split: (shard index, items, digest of the item ids) per run. A run stays
    whole (index None) when its lane has one worker, when it reads a limited list, or when its
    shards would be smaller than ``SHARD_MIN_CALLS`` calls; an empty shard gives no run."""
    whole = [(None, items, ids_sha256(ids) if ids is not None else None)]
    if shards < 2 or limit is not None or items * samples < SHARD_MIN_CALLS * shards:
        return whole
    if ids is None:
        sizes = split_units(items, [1] * shards)
        return [(k, size, None) for k, size in enumerate(sizes) if size]
    groups: list[list[str]] = [[] for _ in range(shards)]
    for item_id in ids:
        groups[rd.shard_of(item_id, shards)].append(item_id)
    return [(k, len(group), ids_sha256(group)) for k, group in enumerate(groups) if group]


def make_plan(options: Mapping[str, Any]) -> dict[str, Any]:
    """The plan for the given options (see :func:`default_options`): every run in order, with
    what the caps and the item lists were when it was made. Reads the item files and the
    harness's run sheet; calls nothing and writes nothing."""
    check_rules()
    unknown = sorted((set(options["counts"]) | set(options["items_files"])) - set(LIST_BY_KEY))
    if unknown:
        raise SystemExit(f"unknown item lists {unknown}; the launcher knows {list(LIST_BY_KEY)}")
    shards = {lane: int(n) for lane, n in options["shards"].items()}
    if set(shards) - set(LANES) or any(n < 1 for n in shards.values()):
        raise SystemExit(f"--shards takes LANE=N with a lane of {list(LANES)} and N at least 1")
    lists: dict[str, dict] = {}
    ids: dict[str, list[str] | None] = {}
    for spec in LISTS:
        lists[spec.key], ids[spec.key] = list_record(spec, options)
    counts = {name: 0 for name in rd.SHEET_COUNTS}
    for spec in LISTS:
        counts[spec.count] += lists[spec.key]["items"]
    sheet_items = rd.load_items(Path(options["sheet_items"])) if options["sheet_items"] else None
    priced_with = Path(options["tracks"]["fit+dev"])
    sheet = rd.run_sheet(
        counts,
        items=sheet_items,
        track=rd.load_track_record(priced_with) if priced_with.is_file() else None,
        prices={m: (p[0], p[1]) for m, p in options["prices"].items()},
        per_call_usd=dict(options["per_call_usd"]),
        repair_rate=options["repair_rate"],
    )
    tracks = {key: track_record(path) for key, path in options["tracks"].items()}
    rows: list[dict] = []
    reserved: list[dict] = []
    for model in rd.STUDY_MODELS:
        slot = sheet["models"][model]
        units = {name: round(entry["cap_usd"] * MICRO) for name, entry in slot["lines"].items()}
        spare = round(rd.MODEL_CAPS_USD[model] * MICRO) - sum(units.values())
        if not units or not 0 <= spare < MICRO // 100:
            raise SystemExit(
                f"the run sheet's caps for {model} sum to ${sum(units.values()) / MICRO:.4f}, "
                f"which is not its ${rd.MODEL_CAPS_USD[model]:.2f} cap less rounding"
            )
        units[max(units, key=lambda name: units[name])] += spare
        for line in rd.RUN_SHEET:
            if line.name not in units:
                continue
            entry = slot["lines"][line.name]
            parts, why = parts_of(line)
            if not parts:
                reserved.append(
                    {
                        "line": line.name,
                        "model": model,
                        "calls": entry["calls"],
                        "cap_usd": units[line.name] / MICRO,
                        "why": why,
                    }
                )
                continue
            weights = [lists[p.items]["items"] * p.samples for p in parts]
            caps = split_units(units[line.name], weights)
            for part, weight, cap in zip(parts, weights, caps, strict=True):
                if weight:
                    usd = entry["usd_typical"] * weight / sum(weights)
                    rows += run_rows(line, part, model, cap, usd, lists, ids, shards)
    rows.sort(
        key=lambda r: (
            PHASES.index(r["phase"]),
            LANES.index(r["lane"]),
            r["_cost"],
            r["_part"],
            r["worker"],
        )
    )
    runs = [
        {"n": n, **{k: v for k, v in row.items() if not k.startswith("_")}}
        for n, row in enumerate(rows, start=1)
    ]
    names = [run["run"] for run in runs]
    bad = [name for name in names if not RUN_NAME.match(name)]
    if bad or len(set(names)) != len(names):
        raise SystemExit(f"run names must be unique and of the harness's form: {bad[:3]}")
    if any(run["cap_usd"] <= 0 for run in runs):
        raise SystemExit("a run would get no cap: the model's cap is too small to split so far")
    early = sorted(
        {r["list"] for r in runs if r["phase"] not in SEALED_PHASES and r["sealed_items"]}
    )
    if early:
        raise SystemExit(
            f"the cost trial and the dev runs read train-period items only; these lists hold "
            f"items dated {rd.TEST_START} or later: {early}"
        )
    for run in runs:
        del run["sealed_items"]
    return {
        "about": "the runs of the COLING 2027 study in order; made by analysis.coling.launch",
        "read_py_sha256": sha256_file(Path(rd.__file__)),
        "options": json.loads(json.dumps(options)),
        "counts": sheet["counts"],
        "lists": lists,
        "tracks": tracks,
        "templates": {t: rd.TEMPLATES[t].sha256 for t in sorted({r["template"] for r in runs})},
        "routes": {m: json.loads(json.dumps(asdict(rd.ROUTES[m]))) for m in rd.STUDY_MODELS},
        "models": {m: model_record(m, sheet, runs, reserved) for m in rd.STUDY_MODELS},
        "reserved": reserved,
        "runs": runs,
    }


def run_rows(
    line: rd.SheetLine,
    part: Part,
    model: str,
    cap: int,
    usd: float,
    lists: Mapping[str, dict],
    ids: Mapping[str, list[str] | None],
    shards: Mapping[str, int],
) -> list[dict]:
    """The runs of one part for one model: one, or one per shard, with the part's cap split in
    proportion to the items of each shard."""
    record = lists[part.items]
    lane, phase = lane_of(model), phase_of(line, model)
    template = part.template or line.template
    needs_track = rd.TEMPLATES[template].needs_track
    split = shards_of(
        ids[part.items], record["items"], part.samples, shards.get(lane, 1), record["limit"]
    )
    caps = split_units(cap, [size for _, size, _ in split])
    costs = split_units(round(usd * MICRO), [size for _, size, _ in split])
    rows = []
    for (k, size, digest), cap_k, cost_k in zip(split, caps, costs, strict=True):
        rows.append(
            {
                "phase": phase,
                "lane": lane,
                "worker": k or 0,
                "run": f"{part.name}-{model}" + ("" if k is None else f".s{k}"),
                "model": model,
                "line": line.name,
                "template": template,
                "condition": part.condition,
                "list": part.items,
                "items": record["path"],
                "shard": None if k is None else f"{k}/{shards[lane]}",
                "limit": record["limit"],
                "samples": part.samples,
                "temperature": part.temperature,
                "mask_names": part.mask_names,
                "shift_years": part.shift_years,
                "track": ("fit+dev" if phase in SEALED_PHASES else "fit") if needs_track else None,
                "allow_test_items": phase in SEALED_PHASES and record["sealed_items"] != 0,
                "cap_usd": cap_k / MICRO,
                "calls": size * part.samples,
                "usd_typical": cost_k / MICRO,
                "item_ids_sha256": digest,
                "sealed_items": record["sealed_items"],
                "_cost": round(usd * MICRO),
                "_part": f"{part.name}-{model}",
            }
        )
    return rows


def model_record(
    model: str, sheet: Mapping, runs: Sequence[dict], reserved: Sequence[dict]
) -> dict:
    """The figures of one model: what the sheet projects, and where its cap went."""
    slot = sheet["models"][model]
    mine = [run for run in runs if run["model"] == model]
    return {
        "lane": lane_of(model),
        "runs": len(mine),
        "calls": sum(run["calls"] for run in mine),
        "usd_typical": slot["usd_typical"],
        "usd_upper": slot["usd_upper"],
        "usd_per_mtok": slot["usd_per_mtok"],
        "cap_usd": slot["cap_usd"],
        "run_caps_usd": sum(round(run["cap_usd"] * MICRO) for run in mine) / MICRO,
        "reserved_usd": sum(round(r["cap_usd"] * MICRO) for r in reserved if r["model"] == model)
        / MICRO,
        "upper_within_cap": slot["upper_within_cap"],
    }


def plan_text(plan: Mapping[str, Any]) -> str:
    """The plan as JSON with one run per line, so that two plans can be compared line by line."""
    head = json.dumps({k: v for k, v in plan.items() if k != "runs"}, indent=1)
    runs = ",\n".join("  " + json.dumps(run) for run in plan["runs"])
    return head[: head.rindex("}")].rstrip() + ',\n "runs": [\n' + runs + "\n ]\n}\n"


def plan_path(out_root: Path) -> Path:
    return out_root / LAUNCH_DIR / PLAN_NAME


def load_plan(out_root: Path) -> dict[str, Any]:
    path = plan_path(out_root)
    if not path.is_file():
        raise SystemExit(f"no plan at {path}; make it with the plan command")
    plan = json.loads(path.read_text(encoding="utf-8"))
    made_for = Path(plan["options"]["out_root"])
    if made_for.resolve() != out_root.resolve():  # its paths are those of the folder it was made in
        raise SystemExit(
            f"the plan at {path} was made for the output root {made_for}, seen from the folder "
            "the plan command was run in; run the launcher from there, or make the plan again"
        )
    return plan


def plan_is_stale(plan: Mapping[str, Any]) -> bool:
    """Whether the inputs of the plan (the harness, the item files, the track records) no longer
    give the plan as written."""
    return plan_text(make_plan(plan["options"])) != plan_text(plan)


def select(
    plan: Mapping[str, Any],
    phases: Iterable[str] = PHASES,
    lanes: Iterable[str] = LANES,
    models: Iterable[str] = (),
) -> list[dict]:
    """The runs of the given phases and lanes, for the given models (all when none), in order."""
    phases, lanes, models = set(phases), set(lanes), set(models)
    return [
        run
        for run in plan["runs"]
        if run["phase"] in phases
        and run["lane"] in lanes
        and (not models or run["model"] in models)
    ]


def summary_lines(plan: Mapping[str, Any]) -> list[str]:
    """The plan in short: runs, calls and projected dollars by phase, lane and model; the caps;
    and what was held back."""
    out = [f"{'phase':13s} {'lane':11s} {'model':17s} {'runs':>5s} {'calls':>7s} {'usd':>9s}"]
    for phase in PHASES:
        for lane in LANES:
            for model in rd.STUDY_MODELS:
                runs = select(plan, [phase], [lane], [model])
                if runs:
                    calls = sum(run["calls"] for run in runs)
                    usd = sum(run["usd_typical"] for run in runs)
                    out.append(
                        f"{phase:13s} {lane:11s} {model:17s} {len(runs):5d} {calls:7d} {usd:9.4f}"
                    )
    out += ["", f"{'model':17s} {'calls':>7s} {'typical':>9s} {'upper':>9s} {'cap':>8s}  caps"]
    for model, slot in plan["models"].items():
        note = "" if slot["upper_within_cap"] else "  upper estimate passes the cap"
        held = f" + {slot['reserved_usd']:.6f} held back" if slot["reserved_usd"] else ""
        out.append(
            f"{model:17s} {slot['calls']:7d} {slot['usd_typical']:9.4f} {slot['usd_upper']:9.4f} "
            f"{slot['cap_usd']:8.2f}  runs {slot['run_caps_usd']:.6f}{held}{note}"
        )
    for entry in plan["reserved"]:
        out.append(
            f"not planned: {entry['line']} for {entry['model']} ({entry['calls']} calls, "
            f"${entry['cap_usd']:.6f} held back): {entry['why']}"
        )
    return out


# ---------------------------------------------------------------------------------------------
# The harness's records of a run
# ---------------------------------------------------------------------------------------------


def manifest_of(plan: Mapping[str, Any], run: Mapping[str, Any]) -> dict:
    """The harness's manifest of a run ({} when there is none, or while it is being written: a
    run with no readable manifest is never taken as finished)."""
    path = Path(plan["options"]["out_root"]) / run["run"] / "run_manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except json.JSONDecodeError:
        return {}


def manifest_differences(
    plan: Mapping[str, Any], run: Mapping[str, Any], manifest: Mapping[str, Any]
) -> list[str]:
    """The fields of a run's manifest that are not what the plan says of the run: the model,
    the template and its pin, the condition, the shard and the item set, and, of the model's
    route, what is sent: the model id and the provider pin (:func:`read.provider_object`), which
    are what the harness itself holds a run name to (``read.IDENTITY_KEYS``). The rest of a
    route row (its price and the day it was read, the names accepted in the echo) may be entered
    or corrected after a run without making it another run."""
    track = plan["tracks"][run["track"]]["sha256"] if run["track"] else None
    route = plan["routes"][run["model"]]
    pin = rd.Route(route["model_id"], route["provider"], route["quantization"])
    wanted = {
        "model": run["model"],
        "model_id": route["model_id"],
        "provider_object": rd.provider_object(pin),
        "template": run["template"],
        "template_sha256": plan["templates"][run["template"]],
        "shard": run["shard"],
        "limit": run["limit"],
        "samples": run["samples"],
        "temperature": run["temperature"],
        "mask_names": run["mask_names"],
        "shift_years": run["shift_years"],
        "track_record_sha256": track,
        "items_sha256": plan["lists"][run["list"]]["sha256"],
        "item_ids_sha256": run["item_ids_sha256"],
        "expected_rows": run["calls"],
    }
    return [name for name, value in wanted.items() if manifest.get(name) != value]


def run_state(plan: Mapping[str, Any], run: Mapping[str, Any]) -> str:
    """What the harness's manifest says of a run: ``finished`` (complete, and for the run the
    plan describes: see :func:`manifest_differences`), ``mismatch`` (complete, for something
    else), ``partial`` (not complete) or ``none`` (no manifest)."""
    manifest = manifest_of(plan, run)
    if not manifest:
        return "none"
    if not manifest.get("complete"):
        return "partial"
    return "mismatch" if manifest_differences(plan, run, manifest) else "finished"


def unfinished(plan: Mapping[str, Any], runs: Iterable[Mapping[str, Any]]) -> list[str]:
    return [run["run"] for run in runs if run_state(plan, run) != "finished"]


# ---------------------------------------------------------------------------------------------
# Guards and what is blocked
# ---------------------------------------------------------------------------------------------


def phase_refusals(phase: str) -> list[str]:
    """Why no live run of the phase may start (empty when one may): the harness's own two tag
    checks, with the F1 tag asked of every run of a phase that reads test-period items."""
    found = rd.paid_call_refusals(rd.SEALED_PERIODS if phase in SEALED_PHASES else ())
    return [f"phase {phase}: {reason}" for reason in found]


def run_files(plan: Mapping[str, Any], run: Mapping[str, Any]) -> list[tuple[str, dict]]:
    """The files a run reads, each with what the plan holds about it."""
    files = [(f"the item file of list {run['list']!r}", plan["lists"][run["list"]])]
    if run["track"]:
        files.append((f"the {run['track']} track record", plan["tracks"][run["track"]]))
    return files


def plan_gaps(plan: Mapping[str, Any], run: Mapping[str, Any]) -> list[str]:
    """The files of a run that the plan was made without (empty when it had them all). Such a
    run is known not to be ready: a lane leaves it and goes on."""
    found = []
    for what, record in run_files(plan, run):
        if not record["on_disk"]:
            late = "; it is there now: plan again" if Path(record["path"]).is_file() else ""
            found.append(f"{what} is not on disk: {record['path']}{late}")
    return found


def file_problems(plan: Mapping[str, Any], run: Mapping[str, Any]) -> list[str]:
    """Why the files of a run are no longer those the plan was made with (empty when they
    are): one is gone, or has other bytes."""
    found = []
    for what, record in run_files(plan, run):
        path = Path(record["path"])
        if record["on_disk"] and not path.is_file():
            found.append(f"{what} is not on disk any more: {path}")
        elif record["on_disk"] and record["sha256"] != sha256_file(path):
            found.append(f"{what} is not the file the plan was made with ({path}): plan again")
    return found


def harness_refusals(run: Mapping[str, Any]) -> list[str]:
    """What the harness would refuse a live start of the run for today
    (:func:`read.live_refusals`: the route, the pilot sentences, the two tags)."""
    template = rd.TEMPLATES.get(run["template"])
    if template is None:
        return [f"template {run['template']!r} is not in read.TEMPLATES"]
    periods = rd.SEALED_PERIODS if run["phase"] in SEALED_PHASES else ()
    return rd.live_refusals(run["model"], template, periods)


def blocked_lines(plan: Mapping[str, Any]) -> list[str]:
    """What is blocked today, by missing value: each reason with the number of runs it stops,
    the harness's reasons first and then the files that are not on disk."""
    reasons: dict[str, list[dict]] = {}
    refusals: dict[tuple, list[str]] = {}
    files: dict[tuple, list[str]] = {}
    free = 0
    for run in plan["runs"]:
        asked = (run["model"], run["template"], run["phase"] in SEALED_PHASES)
        if asked not in refusals:
            refusals[asked] = harness_refusals(run)
        read = (run["list"], run["track"])
        if read not in files:
            files[read] = plan_gaps(plan, run) + file_problems(plan, run)
        found = refusals[asked] + files[read]
        free += not found
        for reason in found:
            reasons.setdefault(reason, []).append(run)
    out = [f"{free} of {len(plan['runs'])} runs could start live today"]
    for reason, runs in reasons.items():
        phases = ", ".join(p for p in PHASES if any(run["phase"] == p for run in runs))
        out.append(f"- {len(runs)} runs ({phases}): {reason}")
    for key, record in plan["lists"].items():
        if not record["on_disk"] and record["items"]:
            out.append(
                f"- list {key!r} is planned at {record['items']} items (the plan's fixed size, "
                f"or --count), not from a file: {record['path']} (written by: "
                f"{record['written_by']})"
            )
    for entry in plan["reserved"]:
        out.append(f"- not planned: {entry['line']} for {entry['model']}: {entry['why']}")
    return out


# ---------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------


def harness_args(plan: Mapping[str, Any], run: Mapping[str, Any], mode: str) -> list[str]:
    """The arguments of the harness for one run: a live run, or the same run as a dry run."""
    options = plan["options"]
    args = ["--items", run["items"], "--template", run["template"], "--model", run["model"]]
    if run["track"]:
        args += ["--track-record", plan["tracks"][run["track"]]["path"]]
    if run["samples"] != 1 or run["temperature"]:
        args += ["--samples", str(run["samples"]), "--temperature", f"{run['temperature']:g}"]
    if run["mask_names"]:
        args.append("--mask-names")
    if run["shift_years"]:
        args += ["--shift-years", str(run["shift_years"])]
    if run["shard"]:
        args += ["--shard", run["shard"]]
    if run["limit"] is not None:
        args += ["--limit", str(run["limit"])]
    args += ["--out-root", options["out_root"], "--local-root", options["local_root"]]
    if mode == "rehearsal":
        return [*args, "--dry-run"]
    args += ["--run-name", run["run"], "--spend-cap-usd", f"{run['cap_usd']:.6f}", "--allow-live"]
    return [*args, "--allow-test-items"] if run["allow_test_items"] else args


def harness_command(plan: Mapping[str, Any], run: Mapping[str, Any], mode: str) -> list[str]:
    return [sys.executable, "-m", "analysis.coling.read", *harness_args(plan, run, mode)]


Runner = Callable[[Sequence[str], Path], int]
"""Runs one harness command with its output appended to the given file; returns the exit
status."""


def harness_runner(command: Sequence[str], output: Path) -> int:
    """The harness as a child process, from the working directory of the launcher."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("ab") as handle:
        handle.write(f"\n$ {shlex.join(command)}\n".encode())
        handle.flush()
        done = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, check=False)
    return done.returncode


def failure_reason(plan: Mapping[str, Any], run: Mapping[str, Any], code: int, output: Path) -> str:
    """Why a run did not finish: the status the harness recorded for a run it stopped (exit 3),
    else the last line it printed (the refusal, or the error)."""
    if code == 3:
        rows = read_jsonl(Path(plan["options"]["out_root"]) / run["run"] / "invocations.jsonl")
        if rows:
            return f"the harness stopped the run: {rows[-1].get('status')}"[:REASON_CHARS]
    lines = (
        output.read_text(encoding="utf-8", errors="replace").splitlines()
        if output.is_file()
        else []
    )
    last = next((line.strip() for line in reversed(lines) if line.strip()), "no output")
    return f"the harness refused the run or failed (exit {code}): {last}"[:REASON_CHARS]


# ---------------------------------------------------------------------------------------------
# A lane
# ---------------------------------------------------------------------------------------------


def lock_path(folder: Path, lane: str, worker: int) -> Path:
    return folder / "locks" / f"{lane}.w{worker}.lock"


@contextmanager
def lane_lock(folder: Path, lane: str, worker: int) -> Iterator[None]:
    """Held by a worker for as long as it runs; a second worker of the same lane and number is
    refused. The lock is asked for ``LOCK_TRIES`` times: a status command or a waiting worker
    that looks whether this worker is alive (:func:`workers_alive`) holds it for an instant."""
    path = lock_path(folder, lane, worker)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for left in reversed(range(LOCK_TRIES)):
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not left:
                    raise SystemExit(f"lane {lane}, worker {worker} is already running") from None
                time.sleep(LOCK_PAUSE_S)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def workers_alive(folder: Path, lane: str, but: int | None = None) -> list[int]:
    """The workers of a lane that hold their lock now (leaving out the caller's own)."""
    alive = []
    for path in sorted((folder / "locks").glob(f"{lane}.w*.lock")):
        worker = int(path.name.removeprefix(f"{lane}.w").removesuffix(".lock"))
        if worker == but:
            continue
        with path.open("a", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                alive.append(worker)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
    return alive


def stop_path(folder: Path, lane: str) -> Path:
    return folder / "stops" / f"{lane}.json"


def lane_stop(folder: Path, lane: str, launch_id: str) -> dict | None:
    """The stop a worker of this start left for the lane, if any. The file is put in place
    whole (:func:`write_stop`), so a worker never reads half of one."""
    path = stop_path(folder, lane)
    record = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return record if record and record.get("launch_id") == launch_id else None


def write_stop(folder: Path, lane: str, record: Mapping[str, Any]) -> None:
    """Leave the lane's stop for the other workers of the start: written beside its place and
    moved there in one step."""
    path = stop_path(folder, lane)
    path.parent.mkdir(parents=True, exist_ok=True)
    beside = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    beside.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(beside, path)


def earlier_runs(plan: Mapping[str, Any], run: Mapping[str, Any], models: Iterable[str]) -> list:
    """The runs of the lane, for the models asked for, in the phases before the run's phase."""
    before = PHASES[: PHASES.index(run["phase"])]
    return select(plan, before, [run["lane"]], models)


def run_lane(
    plan: Mapping[str, Any],
    lane: str,
    worker: int = 0,
    phases: Iterable[str] = PHASES,
    models: Iterable[str] = (),
    *,
    mode: str = "rehearsal",
    launch_id: str | None = None,
    runner: Runner | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """One worker of one lane: its runs of the given phases, one after the other.

    A live worker skips a run the harness has finished, and stops the lane (for every worker of
    this start) at the first run that may not start, that the harness refuses or that fails. A
    run whose files the plan itself was made without is known not to be ready: it is left, with
    a line in the log, and the lane goes on. A rehearsal gives every command to the harness as a
    dry run and goes on after a failure, so that one pass shows everything that does not render.
    Returns 0 when every run went through, 3 otherwise.
    """
    if mode not in ("rehearsal", "live"):
        raise ValueError(f"a lane runs as a rehearsal or live, not {mode!r}")
    folder = launch_dir(plan)
    runner = runner or harness_runner
    launch_id = launch_id or new_launch_id()
    models = list(models)
    queued = select(plan, phases, [lane], models)
    mine = [run for run in queued if run["worker"] == worker]
    theirs = {run["run"] for run in queued if run["worker"] != worker and not plan_gaps(plan, run)}
    here = {"lane": lane, "worker": worker, "mode": mode, "launch_id": launch_id}
    failed = 0

    def stop(run: Mapping[str, Any], reason: str) -> int:
        record = {"launch_id": launch_id, "run": run["run"], "reason": reason, "ts": now()}
        write_stop(folder, lane, record)
        log_event(folder, event="stop", run=run["run"], reason=reason, **here)
        print(f"lane {lane} stopped at {run['run']}: {reason}", flush=True)
        return 3

    def wait_for_phase(run: Mapping[str, Any]) -> str | None:
        """Hold a run until the lane's runs of the earlier phases are finished, and give the
        reason when they will not be.

        Only another worker of this start can still finish one: a run queued for it
        (``theirs``), which leaves out the runs the plan has no file for. The run waits while
        a worker that owns such a run is alive, and once more when none is (a worker of the
        same start may not have taken its lock yet). A run that is left and is not one of
        those will not be finished in this start, and the reason comes at once: this worker's
        own earlier runs (it has passed them), runs that are not queued, and runs without
        their file. Two workers therefore never wait for each other: the one that waits is in
        a later phase than the run it waits for.
        """
        alone, told = 0, False
        while True:
            earlier = earlier_runs(plan, run, models)
            left = [other for other in earlier if run_state(plan, other) != "finished"]
            if not left:
                return None
            never = [other for other in left if other["run"] not in theirs]
            owners = {other["worker"] for other in left}
            alone = 0 if owners & set(workers_alive(folder, lane, but=worker)) else alone + 1
            if never or alone > 1 or lane_stop(folder, lane, launch_id):
                return (
                    f"phase {run['phase']} comes after {len(left)} runs of this lane that are "
                    f"not finished (first: {left[0]['run']})"
                )
            if not told:
                log_event(folder, event="wait", run=run["run"], left=len(left), **here)
                print(f"wait {run['run']}: {len(left)} runs of earlier phases are left", flush=True)
                told = True
            sleep(WAIT_S)

    with lane_lock(folder, lane, worker):
        log_event(folder, event="lane-start", runs=len(mine), **here)
        if mode == "live" and plan_is_stale(plan):
            log_event(folder, event="stop", run=None, reason=STALE, **here)
            print(f"lane {lane} not started: {STALE}", flush=True)
            return 3
        for run in mine:
            name = run["run"]
            other = lane_stop(folder, lane, launch_id)
            if other:
                print(f"lane {lane} was stopped at {other['run']}: {other['reason']}", flush=True)
                return 3
            problems: list[str] = []
            if mode == "live":
                problems = phase_refusals(run["phase"])
                late = None if problems else wait_for_phase(run)
                problems += [late] if late else []
            gaps = [] if problems else plan_gaps(plan, run)
            if gaps:
                log_event(folder, event="blocked", run=name, reason="; ".join(gaps), **here)
                print(f"blocked {name}: {'; '.join(gaps)}", flush=True)
                failed += 1
                continue
            problems += file_problems(plan, run)
            if not problems and mode == "live":
                state = run_state(plan, run)
                if state == "finished":
                    log_event(folder, event="skip", run=name, why="the harness's manifest", **here)
                    print(f"skip {name}: finished", flush=True)
                    continue
                if state == "mismatch":
                    differs = manifest_differences(plan, run, manifest_of(plan, run))
                    problems = [
                        f"its manifest is complete for another run than the plan's: {differs}; "
                        "it is not read again while its folder is there"
                    ]
            if problems:
                if mode == "live":
                    return stop(run, "; ".join(problems))
                log_event(folder, event="blocked", run=name, reason="; ".join(problems), **here)
                print(f"blocked {name}: {'; '.join(problems)}", flush=True)
                failed += 1
                continue
            command = harness_command(plan, run, mode)
            output = folder / "output" / f"{name}.log"
            log_event(folder, event="start", run=name, phase=run["phase"], command=command, **here)
            print(f"start {name} ({run['calls']} calls, cap ${run['cap_usd']:.6f})", flush=True)
            started = time.monotonic()
            code = runner(command, output)
            seconds = round(time.monotonic() - started, 1)
            reason = None if code == 0 else failure_reason(plan, run, code, output)
            if code == 0 and mode == "live" and run_state(plan, run) != "finished":
                reason = "the harness returned 0 and its manifest is not complete for this run"
            log_event(
                folder, event="end", run=name, exit=code, seconds=seconds, reason=reason, **here
            )
            print(f"end {name}: exit {code} after {seconds} s", flush=True)
            if reason and mode == "live":
                return stop(run, reason)
            if reason:
                print(f"blocked {name}: {reason}", flush=True)
                failed += 1
        log_event(folder, event="lane-end", failed=failed, **here)
        print(f"lane {lane}, worker {worker}: {len(mine)} runs, {failed} not through", flush=True)
    return 3 if failed else 0


# ---------------------------------------------------------------------------------------------
# Starting the lanes under tmux
# ---------------------------------------------------------------------------------------------

Tmux = Callable[[Sequence[str]], int]


SERVER_UP = (
    f"note: a tmux server is already running on the socket {TMUX_SOCKET!r}; the lanes started "
    "now get the environment it was started with, not this shell's (key files are not affected)"
)


def tmux_call(args: Sequence[str]) -> int:
    """One tmux command on the launcher's own socket. A server that this command starts takes
    the environment of this process; one that is already running keeps the environment it was
    started with, and so do the windows opened on it."""
    try:
        done = subprocess.run(["tmux", "-L", TMUX_SOCKET, *args], capture_output=True, check=False)
    except FileNotFoundError:
        raise SystemExit(
            "tmux is not installed; run each lane in the foreground with the lane command"
        ) from None
    return done.returncode


def tmux_name(lane: str) -> str:
    return f"coling-{lane}"


def worker_shell(
    plan: Mapping[str, Any],
    lane: str,
    worker: int,
    phases: Sequence[str],
    models: Sequence[str],
    mode: str,
    launch_id: str,
) -> str:
    """The shell line of one tmux window: the lane command from the launcher's working
    directory, with what it prints kept in ``_launch/lanes/``."""
    args = ["--out-root", plan["options"]["out_root"], "--lane", lane, "--worker", str(worker)]
    args += ["--launch-id", launch_id]
    for phase in phases:
        args += ["--phase", phase]
    for model in models:
        args += ["--model", model]
    args.append("--live" if mode == "live" else "--rehearse")
    command = [sys.executable, "-m", "analysis.coling.launch", "lane", *args]
    kept = launch_dir(plan) / "lanes" / f"{lane}.w{worker}.log"
    path = os.environ.get("PYTHONPATH") or "."
    return (
        f"cd {shlex.quote(str(Path.cwd()))} && PYTHONPATH={shlex.quote(path)} "
        f"{shlex.join(command)} 2>&1 | tee -a {shlex.quote(str(kept))}"
    )


def tmux_commands(
    plan: Mapping[str, Any],
    lane: str,
    workers: int,
    phases: Sequence[str],
    models: Sequence[str],
    mode: str,
    launch_id: str,
) -> list[list[str]]:
    """The tmux commands that start a lane, detached: one window per worker."""
    name = tmux_name(lane)
    out = []
    for worker in range(workers):
        shell = worker_shell(plan, lane, worker, phases, models, mode, launch_id)
        first = ["new-session", "-d", "-s", name]
        head = first if worker == 0 else ["new-window", "-d", "-t", f"{name}:"]
        out.append([*head, "-n", f"w{worker}", shell])
    return out


def lane_refusals(
    plan: Mapping[str, Any], lane: str, phases: Sequence[str], models: Sequence[str]
) -> list[str]:
    """Why a live start of the lane is refused before anything runs (empty when it is not): a
    tag a phase with unfinished runs waits for, or an earlier phase that is neither finished nor
    queued in this start."""
    found: list[str] = []
    for phase in phases:
        runs = select(plan, [phase], [lane], models)
        if not unfinished(plan, runs):
            continue
        found += phase_refusals(phase)
        before = [p for p in PHASES[: PHASES.index(phase)] if p not in phases]
        left = unfinished(plan, select(plan, before, [lane], models))
        if left:
            found.append(
                f"phase {phase} comes after {len(left)} runs of this lane that are not "
                f"finished (first: {left[0]}); finish them, or queue their phase in this start"
            )
    return list(dict.fromkeys(found))


def start(
    plan: Mapping[str, Any],
    phases: Iterable[str],
    lanes: Iterable[str] = LANES,
    models: Iterable[str] = (),
    *,
    mode: str = "print",
    tmux: Tmux | None = None,
) -> int:
    """Print the commands of the lanes (the default), or start each lane under tmux as a
    rehearsal or live. Every lane is judged and started on its own, the Google lane first, so a
    lane that is refused or busy holds up no other. Returns 0 when no lane was refused."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    phases = [p for p in PHASES if p in set(phases)]
    lanes = [lane for lane in LANES if lane in set(lanes)]
    models = [m for m in rd.STUDY_MODELS if m in set(models)]
    folder = launch_dir(plan)
    tmux = tmux or tmux_call
    launch_id = new_launch_id()
    stale = mode != "print" and plan_is_stale(plan)
    refused, started = 0, 0
    for lane in lanes:
        runs = select(plan, phases, [lane], models)
        if not runs:
            later = [p for p in PHASES if p not in phases and select(plan, [p], [lane], models)]
            hint = f"; its runs are in: {', '.join(later)}" if later else ""
            print(f"lane {lane}: no run in {', '.join(phases)}{hint}")
            continue
        workers = 1 + max(run["worker"] for run in runs)
        shown = "live" if mode == "print" else mode
        commands = tmux_commands(plan, lane, workers, phases, models, shown, launch_id)
        left = unfinished(plan, runs)
        print(f"lane {lane}: {len(runs)} runs, {len(runs) - len(left)} finished, {workers} workers")
        if mode == "print":
            for run in runs:
                state = run_state(plan, run)
                mark = (
                    "skip (finished)"
                    if state == "finished"
                    else f"{run['phase']}, w{run['worker']}"
                )
                print(f"  [{mark}] {shlex.join(harness_command(plan, run, 'live'))}")
            for reason in lane_refusals(plan, lane, phases, models):
                print(f"  a live start would be refused: {reason}")
            for command in commands:
                print(f"  tmux -L {TMUX_SOCKET} {shlex.join(command)}")
            continue
        problems = [STALE] if stale else []
        if mode == "live":
            problems += lane_refusals(plan, lane, phases, models)
            if not left:
                print(f"lane {lane}: nothing to do, every run is finished")
                continue
        if tmux(["has-session", "-t", f"={tmux_name(lane)}"]) == 0 or workers_alive(folder, lane):
            problems.append(f"the lane is running (tmux: {tmux_name(lane)})")
        if problems:
            refused += 1
            for reason in problems:
                print(f"lane {lane} not started: {reason}")
            continue
        if not started and tmux(["has-session"]) == 0:  # a session of any name: the server is up
            print(SERVER_UP)
        stop_path(folder, lane).unlink(missing_ok=True)
        (folder / "lanes").mkdir(parents=True, exist_ok=True)
        log_event(folder, event="launch", lane=lane, mode=mode, launch_id=launch_id, tmux=commands)
        started += 1
        if any(tmux(command) != 0 for command in commands):
            refused += 1
            print(f"lane {lane} not started: tmux refused a command")
            continue
        print(f"lane {lane} started ({mode}): tmux -L {TMUX_SOCKET} attach -t {tmux_name(lane)}")
    return 3 if refused else 0


# ---------------------------------------------------------------------------------------------
# Status and the completeness check
# ---------------------------------------------------------------------------------------------

STATUS_COLUMNS = ("done", "left", "paid", "spent", "cap", "repairs", "failed", "refused")


def declared_caps(plan: Mapping[str, Any]) -> dict[str, float]:
    """The cap each run last declared in the harness's ledger. It is the plan's cap unless the
    run was resumed by hand under another one (PLAN section 9)."""
    rows = read_jsonl(Path(plan["options"]["out_root"]) / rd.LEDGER_NAME)
    return {row["run"]: float(row["cap_usd"]) for row in rows if row.get("event") == "declare"}


def run_counts(
    plan: Mapping[str, Any],
    run: Mapping[str, Any],
    log: Sequence[dict],
    alive: Sequence[int] | None = None,
    caps: Mapping[str, float] | None = None,
) -> dict:
    """The numbers of one run, from the harness's manifest, spend log and ledger and from the
    launcher's log: nothing of what any item or answer says. ``alive`` (the lane's workers that
    run now) and ``caps`` (:func:`declared_caps`) are looked up here when they are not given."""
    manifest = manifest_of(plan, run)
    by_status = manifest.get("by_status", {})
    spend = read_jsonl(Path(plan["options"]["out_root"]) / run["run"] / "spend_log.jsonl")
    calls = [row for row in spend if row.get("event") == "call"]
    done = min(int(manifest.get("readings", 0)), run["calls"])
    state = run_state(plan, run)
    events = [row for row in log if row.get("run") == run["run"] and row.get("mode") == "live"]
    last = events[-1] if events else {}
    if state != "finished":
        alive = workers_alive(launch_dir(plan), run["lane"]) if alive is None else alive
        if last.get("event") == "start" and last.get("worker") in alive:
            state = "running"
        elif state == "none":
            state = "failed" if last.get("event") in ("end", "stop") else "pending"
    caps = declared_caps(plan) if caps is None else caps
    return {
        "state": state,
        "done": done,
        "left": run["calls"] - done,
        "paid": len(calls),
        "spent": sum(float(row["usd"]) for row in calls),
        "cap": caps.get(run["run"], run["cap_usd"]),
        "repairs": by_status.get("repaired", 0) + by_status.get("failed", 0),
        "failed": by_status.get("failed", 0),
        "refused": by_status.get("refused", 0),
    }


def _cells(counts: Mapping[str, Any]) -> str:
    return (
        f"{counts['done']:7d} {counts['left']:7d} {counts['paid']:7d} {counts['spent']:10.4f} "
        f"{counts['cap']:10.4f} {counts['repairs']:7d} {counts['failed']:7d} {counts['refused']:7d}"
    )


def status_lines(
    plan: Mapping[str, Any], phases: Iterable[str] = PHASES, lanes: Iterable[str] = LANES
) -> list[str]:
    """One line of counts per run and one per lane. ``done`` and ``left`` are reading rows, which
    the harness writes when an invocation ends; ``paid`` counts the calls in the spend log, which
    moves while a run is in flight. ``cap`` is the cap the run last declared in the ledger, and
    the plan's before that. ``repairs`` are repair calls, ``failed`` readings that still failed
    after theirs."""
    log = read_jsonl(launch_dir(plan) / RUN_LOG)
    caps = declared_caps(plan)
    head = (
        f"{'phase':13s} {'lane':11s} {'run':40s} {'state':9s} "
        + " ".join(f"{c:>7s}" for c in STATUS_COLUMNS[:3])
        + f" {'spent':>10s} {'cap':>10s} "
        + " ".join(f"{c:>7s}" for c in STATUS_COLUMNS[5:])
    )
    out = [head]
    totals = []
    for lane in [name for name in LANES if name in set(lanes)]:
        runs = select(plan, phases, [lane])
        if not runs:
            continue
        alive = workers_alive(launch_dir(plan), lane)
        rows = [run_counts(plan, run, log, alive, caps) for run in runs]
        for run, counts in zip(runs, rows, strict=True):
            out.append(
                f"{run['phase']:13s} {lane:11s} {run['run']:40s} {counts['state']:9s} "
                + _cells(counts)
            )
        total = {name: sum(counts[name] for counts in rows) for name in STATUS_COLUMNS}
        states = sorted({counts["state"] for counts in rows})
        mix = ", ".join(f"{sum(1 for c in rows if c['state'] == s)} {s}" for s in states)
        totals.append(f"{'lane ' + lane:66s} {'':9s} {_cells(total)}  ({len(rows)} runs: {mix})")
    return [*out, *totals]


def confirmatory_report(plan: Mapping[str, Any]) -> tuple[list[dict], bool]:
    """Whether every confirmatory run is finished with its registered item set (PLAN section 6:
    no evaluation before that).

    For each primary and each confirmatory line: every planned run (every shard) must be
    finished by its manifest (:func:`run_state`), and the harness's completeness check
    (:func:`read.check_runs`) must find the group ready against the ids of the item list: no
    partial run, no duplicate, every echo acceptable, exactly the expected items. The harness
    pools the runs of an output root by model and condition, and the trial, dev and secondary
    runs share their condition with the confirmatory ones, so the runs of the group are named
    to it (``runs``) and nothing else is pooled. The expected ids are read from the item file
    only while it is the file the plan was made with; a list that has changed since, or is
    gone, leaves the group not ready.
    """
    out_root = Path(plan["options"]["out_root"])
    groups: dict[tuple[str, str], list[dict]] = {}
    for run in select(plan, ["confirmatory"]):
        groups.setdefault((run["model"], run["line"]), []).append(run)
    report = []
    for (model, line), runs in groups.items():
        record, names = plan["lists"][runs[0]["list"]], [run["run"] for run in runs]
        left = unfinished(plan, runs)
        entry = {"model": model, "line": line, "runs": len(runs), "finished": len(runs) - len(left)}
        entry |= {"expected": record["items"], "answered": 0, "missing": record["items"]}
        entry |= {"unexpected": 0, "duplicates": 0, "ready": False}
        report.append(entry)
        path = Path(record["path"])
        if not record["on_disk"] or not path.is_file() or sha256_file(path) != record["sha256"]:
            continue
        expected = [item.item_id for item in rd.load_items(path)]
        found = rd.check_runs(out_root, expected=expected, template=runs[0]["template"], runs=names)
        if len(found) == 1 and found[0]["model"] == model:
            entry |= {
                "answered": found[0]["items_answered"],
                "missing": found[0]["missing"],
                "unexpected": found[0]["unexpected"],
                "duplicates": found[0]["duplicates"],
                "ready": bool(found[0]["ready"]) and not left,
            }
    return report, bool(report) and all(entry["ready"] for entry in report)


def check_lines(plan: Mapping[str, Any]) -> tuple[list[str], bool]:
    report, ready = confirmatory_report(plan)
    out = [
        f"{'model':17s} {'line':9s} {'runs':>5s} {'finished':>8s} {'expected':>8s} "
        f"{'answered':>8s} {'missing':>7s} {'unexpected':>10s} {'duplicates':>10s}  ready"
    ]
    for e in report:
        out.append(
            f"{e['model']:17s} {e['line']:9s} {e['runs']:5d} {e['finished']:8d} {e['expected']:8d} "
            f"{e['answered']:8d} {e['missing']:7d} {e['unexpected']:10d} {e['duplicates']:10d}  "
            f"{'yes' if e['ready'] else 'no'}"
        )
    out.append(
        "every confirmatory run of the launcher is finished with its registered item set"
        if ready
        else "NOT complete: no evaluation against test outcomes yet (PLAN section 6)"
    )
    out.append(
        "not checked here: the test predictions of the model-free predictors (PLAN section 6)"
    )
    return out, ready


# ---------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------


def _pairs(values: Sequence[str], option: str) -> dict[str, str]:
    pairs = {}
    for value in values:
        name, sep, rest = value.partition("=")
        if not sep or not name or not rest:
            raise SystemExit(f"{option} takes NAME=VALUE: {value!r}")
        pairs[name] = rest
    return pairs


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.launch", description=(__doc__ or "").splitlines()[0]
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def command(name: str, text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=text)
        sp.add_argument("--out-root", type=Path, default=OUT_ROOT, help="the study's one root")
        return sp

    def choice(sp: argparse.ArgumentParser, required: bool = False) -> None:
        sp.add_argument("--phase", action="append", choices=PHASES, required=required)
        sp.add_argument("--lane", action="append", choices=LANES)

    sp = command("plan", "make the plan and write it (or compare it with the one on disk)")
    sp.add_argument("--items-dir", type=Path, default=ITEMS_DIR)
    sp.add_argument("--items-file", action="append", default=[], metavar="LIST=PATH")
    sp.add_argument("--count", action="append", default=[], metavar="LIST=N")
    sp.add_argument("--track-fit", type=Path, help="the fit track record (trial and dev runs)")
    sp.add_argument("--track-fit-dev", type=Path, help="the fit+dev track record (test runs)")
    sp.add_argument("--shards", action="append", default=[], metavar="LANE=N")
    sp.add_argument("--price", action="append", default=[], metavar="MODEL=IN,OUT")
    sp.add_argument("--per-call-usd", action="append", default=[], metavar="MODEL=USD")
    sp.add_argument("--repair-rate", type=float, default=0.0)
    sp.add_argument("--sheet-items", type=Path, help="price the sheet on these items")
    sp.add_argument("--local-root", type=Path, default=LOCAL_ROOT)
    sp.add_argument("--check", action="store_true", help="compare with the plan on disk")
    sp = command("run", "print the commands, or start the lanes under tmux")
    choice(sp, required=True)
    sp.add_argument("--model", action="append", choices=rd.STUDY_MODELS)
    how = sp.add_mutually_exclusive_group()
    how.add_argument("--rehearse", action="store_true", help="start the lanes as dry runs")
    how.add_argument("--live", action="store_true", help="start the lanes with paid calls")
    sp = command("lane", "one worker of one lane, in the foreground (what a tmux window runs)")
    sp.add_argument("--phase", action="append", choices=PHASES, required=True)
    sp.add_argument("--lane", choices=LANES, required=True)
    sp.add_argument("--worker", type=int, default=0)
    sp.add_argument("--model", action="append", choices=rd.STUDY_MODELS)
    sp.add_argument("--launch-id")
    how = sp.add_mutually_exclusive_group(required=True)
    how.add_argument("--rehearse", action="store_true")
    how.add_argument("--live", action="store_true")
    choice(command("status", "counts per run and per lane"))
    command("check", "whether every confirmatory run is finished")
    command("blocked", "what a live start would be refused for today")
    return ap


def _plan_options(args: argparse.Namespace) -> dict[str, Any]:
    options = default_options(args.items_dir)
    options["items_files"] = dict(sorted(_pairs(args.items_file, "--items-file").items()))
    options["counts"] = {k: int(v) for k, v in sorted(_pairs(args.count, "--count").items())}
    if args.track_fit:
        options["tracks"]["fit"] = args.track_fit.as_posix()
    if args.track_fit_dev:
        options["tracks"]["fit+dev"] = args.track_fit_dev.as_posix()
    options["shards"] = {k: int(v) for k, v in sorted(_pairs(args.shards, "--shards").items())}
    for model, pair in sorted(_pairs(args.price, "--price").items()):
        low, _, high = pair.partition(",")
        options["prices"][model] = [float(low), float(high)]
    per_call = _pairs(args.per_call_usd, "--per-call-usd")
    options["per_call_usd"] = {m: float(v) for m, v in sorted(per_call.items())}
    stray = sorted((set(options["prices"]) | set(per_call)) - set(rd.STUDY_MODELS))
    if stray:
        raise SystemExit(f"not among the eight readers: {stray}")
    options["repair_rate"] = args.repair_rate
    options["sheet_items"] = args.sheet_items.as_posix() if args.sheet_items else None
    options["out_root"] = args.out_root.as_posix()
    options["local_root"] = args.local_root.as_posix()
    return options


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "plan":
        plan = make_plan(_plan_options(args))
        text, path = plan_text(plan), plan_path(args.out_root)
        if args.check:
            same = path.is_file() and path.read_text(encoding="utf-8") == text
            print("up to date" if same else f"differs from a fresh plan: {path}")
            return 0 if same else 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print("\n".join([*summary_lines(plan), "", *blocked_lines(plan)]))
        print(f"wrote {path}: {len(plan['runs'])} runs, sha256 {sha256_file(path)[:16]}")
        return 0
    plan = load_plan(args.out_root)
    if args.command == "run":
        mode = "live" if args.live else "rehearsal" if args.rehearse else "print"
        return start(plan, args.phase, args.lane or LANES, args.model or (), mode=mode)
    if args.command == "lane":
        return run_lane(
            plan,
            args.lane,
            args.worker,
            args.phase,
            args.model or (),
            mode="live" if args.live else "rehearsal",
            launch_id=args.launch_id,
        )
    if args.command == "status":
        print("\n".join(status_lines(plan, args.phase or PHASES, args.lane or LANES)))
        return 0
    if args.command == "check":
        lines, ready = check_lines(plan)
        print("\n".join(lines))
        return 0 if ready else 3
    if plan_is_stale(plan):  # a live start checks this first, whatever the lines below say
        print(f"- every run: {STALE}")
    print("\n".join(blocked_lines(plan)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
