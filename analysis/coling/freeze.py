"""Corpus freeze: the steps of the freeze run in one fixed order, with a record of every hash.

The freeze is the one run that writes the sealed outcome files (PLAN.md, standing rules on
sealing; section 12, Gate 1; section 17). This module runs its steps in order, stops at the
first one that fails, and writes ``analysis/coling/out/freeze_record.json`` with a Markdown
rendering beside it (``freeze_record.md``), laid out like PLAN.md section 17 so that the values
can be copied into the plan. ``plan_check.py`` compares the plan with this record.

Checks before the first step (``preflight``). No other run is under way (``freeze.lock`` in the
output folder is made at the start of a run and removed at its end; a run that was killed
leaves it, and it is then removed by hand). No variable that looks like an API key is set;
PLAN.md section 17 states a hash for ``rules.py``, the capture manifest, the availability-string
list and the lock file, and each file on disk has it; ``--cutoff`` is a day of the month that
the counts-only code holds for its gate model; no record of a run that reached the sealed build
is on disk, none that cannot be read, and no mark of a sealed build (see "One sealed build");
no counts file of the counts-only code is on disk (that script runs once and overwrites
nothing). Every mode but the rehearsal also needs every hashed input on disk and committed
(code, guide, MODELS.md, lock file, capture manifest, availability list; a file that git
ignores counts as not committed), so that the record holds hashes of committed files.

Steps (``steps``; the list is data, and ``--dry-run`` prints it).

1. ``capture manifest``: ``manifest --check --pin <hash from PLAN.md section 17>``.
2. ``availability strings``: ``corpus.write_availability_strings``, which reads the captures
   only. The list is written again by its own command and must keep its bytes, those of the
   list that was checked (PLAN.md section 2.2): if it changes, it is put back and the run stops
   before anything is sealed. The strings that differ are then checked, and the plan says so.
3. ``template pins``: ``read --print-pins``. It reads no table, so it runs before the build.
4. ``open tables``: ``corpus.open_build``, which writes the events table and the train outcomes
   and seals nothing. They are the tables of the freeze: step 9 writes the same bytes again.
5. ``form readings``: ``forms --check``. Its exit status says only that the outputs are stale;
   the step fails when a reading changed on a pair that the old golden file and the new events
   table share, which must not happen while ``rules.py`` is frozen, or when the check stopped
   before it printed its verdict.
6. ``form counts``: ``forms``.
7. ``sample lists``: ``audit_sample draw --fixed pilot check reserve literal``. The four lists
   must keep their bytes: if one changes, every file of the step is put back and the run stops.
   This step comes before the dataset builder, which reads the lists (PLAN.md section 3, sample
   order).
8. ``dataset``: the dataset builder. It must have read all four lists, found every id of them
   in the statement table, and marked every subset final.
9. ``sealed build``: ``python -m analysis.coling.corpus``, the one sealed write. Its two open
   tables must have the hashes of step 4, and its Gate 1 lines must be those of step 4.
10. ``sealed counts``: the counts-only code on the sealed file, with ``--expect-sha256`` from
    step 9 and ``--expect-eligible-sha256`` from step 8, and with ``COUNTS_FLAGS`` (the two
    observable counts of Gate 1 on the eligible list).
11. ``power``: the model-free predictors and the power estimate. It comes after the counts-only
    code because it takes the registered scoreable counts from that script's file: an integer,
    or a lower bound ``>N`` as ``N + 1``. It stops at ``<5`` or ``withheld``, and the run says
    so when the counts are shown.

The sealed build is the one step that cannot be repeated, so it comes after every open step
that could stop the run. The corpus builder writes the open tables before the sealed ones in
the same call, so steps 5 to 8 read the open tables of step 4; the run fails at step 9 if that
build gives other bytes. The steps after it can be run again by ``--continue-after-sealed``,
which keeps a counts step that finished: a failure of step 11 never asks for a second reading
of the sealed file.

Then, in this module: a check that the sealed counts are those of the files now on disk (the
counts file holds the hashes of the eligible list, the events table, the capture manifest and
the code it ran on); the Gate 1 record (the builder's four counts, read from the lines the
build printed, and the four counts on the eligible list, read from the counts file); and the
record itself. The run does not judge Gate 1: it prints and records, for each part, whether the
four thresholds are met, and its exit status says only whether every step passed.

Notes. The freeze run says, and does not stop for: a guide whose version line is not yet
``v1``, a template that still waits for a pilot sentence, and the absence of a complete
rehearsal of the present code. ``plan_check.py`` does stop for the first two.

Modes.

* ``--dry-run`` prints the checks, the steps and their commands, and runs nothing. With another
  mode it prints what that mode would run.
* ``--open-only`` is the rehearsal: every step that touches no sealed data. The record says
  ``not run`` for the sealed fields.
* ``--write-sealed-once`` is the freeze run. It is refused when the record or the mark on disk
  shows that a sealed build was started, whatever became of it.
* ``--continue-after-sealed`` goes on from a freeze run whose sealed build finished: after a
  later step failed, or after an input of a later step changed (the guide, a prompt pin). It
  never builds the corpus. It needs the open tables, the builder's code and the pinned inputs
  on disk to be those of the sealed build; it keeps a sealed step that finished, runs every
  other step again, and writes the record again, with a line for each earlier run. If the
  eligible list, or the code behind the sealed counts, is then no longer what the counts were
  taken on, the run fails: reading the sealed file a second time is a decision for the owner.
  For the same reason a counts step that was started and did not finish is not run again
  unless ``--counts-again`` is given (it may have opened the sealed file before it stopped;
  its refusal, shown when it stopped, says why), and the record then says so.
* ``--verify-rerun`` is the one rerun of the corpus builder that PLAN.md allows before the push
  (standing rules, "the one rerun that checks it"; section 17, "Identity"). After the manifest
  check it runs the build command of the freeze run, which writes the same files to the same
  places; it compares both sealed hashes and both open-table hashes with the record's and adds
  the result to the record, changing nothing else in it. It runs once: a record that holds a
  rerun, begun or finished, refuses another. It is refused, and not used up, when the builder's
  code, the pinned inputs, Python or the libraries are not those of the freeze run, or the
  capture folder is not the manifest's set.

One sealed build. Just before the sealed build starts, the freeze run creates the mark
``external_data/coling_sealed_build_started.json`` (beside the sealed folder, not in it; the
file is created, never written over) and writes the record with the step as ``started``. As
soon as the build has ended the record is written again with what it printed, and the same is
done around the counts-only code. A build that was started and left no record of its end is
therefore known by the mark and by the record, and neither the freeze run nor the rehearsal
starts while one of the two is there. A second sealed build is a decision for the study's
owner, taken by moving the record, the mark and the counts file away and noting it in the
plan. What this module cannot see: the builder run by hand, outside this script.

Sealing. Nothing under ``external_data/sealed/`` is opened, listed or hashed here: the sealed
hashes are the ones the builder prints. Of a sealed step's output only the lines named in the
step are shown or kept (``sealed <file> sha256 <hash>``, ``wrote <file> sha256 <hash>``, the
Gate 1 counts of the builder, a refusal of the counts-only code); when such a step fails, the
rest stays unshown, because it may quote a sealed value. The counts of the counts-only code are
read from the file it writes, which holds counts and hashes only.

The record. Inputs (the cutoff given to the builder, the hashes the plan states, the commit,
the earlier runs of a record that was written again), the environment (Python, the lock file,
the libraries the table bytes depend on), every code hash that section 17 lists, the open
tables as gzip files and as decompressed content, the sealed hashes as printed, the eligible
list and the three secondary lists, the sample lists, the guide, MODELS.md, the template pins,
the Gate 1 record, the counts of the counts file as registered (integers and masks only), the
hash of every file a step wrote, and for each step its command, exit status, start and end
time (UTC, from the clock the caller passes in) and the lines kept from its output.

Usage (from the repository root)::

    PYTHONPATH=. python -m analysis.coling.freeze --dry-run
    PYTHONPATH=. python -m analysis.coling.freeze --open-only            # the rehearsal
    PYTHONPATH=. python -m analysis.coling.freeze --write-sealed-once    # the freeze run
    PYTHONPATH=. python -m analysis.coling.freeze --continue-after-sealed [--counts-again]
    PYTHONPATH=. python -m analysis.coling.freeze --verify-rerun         # once, before the push

``--cutoff`` is a day of the documented training-cutoff month of the primary model that Gate 1
names (PLAN.md section 4); ``--plan`` names the plan file. Exit status 0 when every step passed,
1 otherwise. The tests replace the commands of the step list by small scripts in a temporary
folder.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

SEED = 20261001
SHORT = 16  # hash prefix length used in PLAN.md section 17
HERE = Path("analysis/coling")
OUT = HERE / "out"
PLAN = HERE / "plan" / "PLAN.md"
GUIDE = HERE / "plan" / "AUDIT_GUIDE.md"
MODELS = HERE / "plan" / "MODELS.md"
LOCK = Path("uv.lock")
CAPTURES = Path("external_data/fda_wayback_csv")
RECORD = OUT / "freeze_record.json"
RECORD_MD = OUT / "freeze_record.md"
MANIFEST = OUT / "capture_manifest.csv"
STRINGS = OUT / "availability_strings.csv"
DATASET_COUNTS = OUT / "dataset_counts.json"
ELIGIBLE = OUT / "eligible_e3.csv"
SEALED_COUNTS = OUT / "sealed_counts.json"
OPEN_TABLES = (OUT / "events.csv.gz", OUT / "outcomes_train.csv.gz")
SEALED_FOLDER = "sealed"
SEALED_TABLES = (
    "external_data/sealed/outcomes_test.csv.gz",
    "external_data/sealed/outcomes_train_uncensored.csv.gz",
)
"""Named for the step list and for the builder's printed lines only; never opened here."""
SEALED_TEST = "outcomes_test.csv.gz"
SEALED_MARK = Path("external_data") / "coling_sealed_build_started.json"
"""Created once, just before the sealed build starts, and never written over or removed here.
It lies beside the sealed folder and not in it, so it holds for every checkout that shares the
folder, and it stays when a record is lost or edited."""
RUN_LOCK = OUT / "freeze.lock"
"""Held while a run is under way, so that two runs never work on the same files at once."""
CUTOFF = "2023-12-31"
"""A day of the documented cutoff month of llama-3.3-70b (PLAN.md section 4): December 2023.
The counts-only code holds the same month for its gate model, in its own table."""
COUNTS_FLAGS = ("--gate-observable",)
"""The one choice passed to the counts-only code: the two observable counts of Gate 1 on the
eligible list are asked for (PLAN.md sections 3 and 12; the standing rules allow counts of
events with an observable outcome). The second part of the gate record needs them. Empty this
tuple to leave them out: the gate record then says that the two thresholds cannot be told."""

CODE = (
    "corpus.py",
    "rules.py",
    "forms.py",
    "manifest.py",
    "dataset.py",
    "audit_sample.py",
    "audit_outcomes.py",
    "audit_agreement.py",
    "sealed_counts.py",
    "freeze.py",
    "predictors.py",
    "gbm.py",
    "power.py",
)
"""The code PLAN.md section 17 hashes at registration, in its order: builder, rule reader, form
classifier, capture manifest, dataset builder, samplers and sheet generators, agreement code,
counts-only code, this script, calibrator (``predictors.py``), both gradient-boosted models
(``gbm.py``) and the power code. ``plan_check.py`` wants each of these hashes in section 17."""
CODE_OTHER = ("read.py",)
"""Hashed for the record and not listed in section 17: ``read.py`` is hashed at F1."""
BUILD_CODE = ("corpus.py", "manifest.py")
"""What the sealed build runs: the rerun is refused when one of them is not the recorded file."""
FIRST_DRAW = ("pilot", "check", "reserve", "literal")
SAMPLES = OUT / "audit" / "samples"
SAMPLES_LATER = OUT / "audit" / "samples_later"
OUTCOME_SAMPLE = OUT / "audit_outcomes" / "outcome_train_sample.csv"
SECONDARY = ("tbd", "silent", "stale")
NOT_RUN = "not run"

GATE_NEEDS = {"statements": 600, "observable": 250, "episodes": 100, "post_cutoff": 150}
"""The four thresholds of Gate 1 (PLAN.md section 12), as ``corpus.GATE_THRESHOLDS`` has them."""
GATE_ON_THE_LIST = {
    "statements": ("e3_eligible_test", "eligible_statements"),
    "observable": ("gate1_on_the_eligible_list", "observable_statements"),
    "episodes": ("e3_eligible_test", "eligible_episodes"),
    "post_cutoff": ("gate1_on_the_eligible_list", "observable_statements_after_cutoff"),
}
"""Where the file of the counts-only code holds the same four counts on the eligible list."""
SCOREABLE = ("e3_eligible_test", "scoreable_statements")
FOR_POWER = (SCOREABLE, ("e3_eligible_test", "scoreable_episodes"))
"""The two counts that the power code takes from the counts file. It reads an integer, or a
lower bound ``>N`` as ``N + 1`` (PLAN.md section 6: where a registered number is a lower bound,
the bound is used), and stops at ``<5`` or ``withheld``."""
COUNTED_FILES = {"eligible_list": ELIGIBLE, "events": OPEN_TABLES[0], "capture_manifest": MANIFEST}
"""The open inputs whose sha256 the counts file holds under ``inputs``."""

PINNED = {
    "rules.py": (HERE / "rules.py", r"`rules\.py`"),
    "capture_manifest.csv": (MANIFEST, r"capture_manifest\.csv`"),
    "availability_strings.csv": (STRINGS, r"availability-string check"),
    "uv.lock": (LOCK, r"`uv\.lock`"),
}
"""The files whose hash the plan states before the freeze: the path, and the words of section
17 after which the hash stands (the first 16-hex token in backticks of the same list item)."""
KEY_LIKE = re.compile(r"API[_-]?KEY|API[_-]?TOKEN|API[_-]?SECRET|SECRET[_-]?KEY|_KEY$", re.I)

HASH_LINE = r"^(?:wrote|sealed) \S+ sha256 [0-9a-f]{64}$"
GATE_LINE = r"^(?:Gate 1:|  (?:statement events|observable outcome|shortage episodes|dated after) )"
REFUSAL = r"^refused: "
FORM_VERDICT = r"^(?:up to date|differs from a fresh run: )"
_PRINTED_HASH = re.compile(r"^(wrote|sealed) (\S+) sha256 ([0-9a-f]{64})$")
_NEED = re.compile(r"(\d+) \(need >= (\d+)\)")
_CHANGED = re.compile(r"readings changed on shared pairs: (\d+)")
_ERROR_TYPE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))(?::|$)")
_HEX = re.compile(r"[0-9a-f]{64}")
_MASK = re.compile(r"<\d+|>\d+|withheld")

PYTHON = sys.executable
SEALED_HASH = "<sha256 of outcomes_test.csv.gz, as the sealed build printed it>"
ELIGIBLE_HASH = "<sha256 of eligible_e3.csv, as the dataset builder wrote it>"

MANIFEST_CHECK = "capture manifest"
STRING_LIST = "availability strings"
PINS = "template pins"
OPEN_BUILD = "open tables"
SEALED_BUILD = "sealed build"
FORM_CHECK = "form readings"
FORMS = "form counts"
SAMPLE_LISTS = "sample lists"
DATASET = "dataset"
COUNTS = "sealed counts"
POWER = "power"

OPEN_ONLY = "open-only"
FREEZE = "freeze"
CONTINUE = "continue"
VERIFY = "verify-rerun"
MODE_FLAGS = {
    OPEN_ONLY: "--open-only",
    FREEZE: "--write-sealed-once",
    CONTINUE: "--continue-after-sealed",
    VERIFY: "--verify-rerun",
}
COUNTS_AGAIN = "--counts-again"
ABOUT = (
    "Record of the corpus freeze (PLAN.md section 17): hashes and counts only. The sealed "
    "hashes are those the builder printed; nothing under the sealed folder was opened."
)


# --------------------------------------------------------------------------------------------
# Hashes and files
# --------------------------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def say(line: str = "") -> None:
    """Print one line. A terminal that has gone away does not stop a run: what a run gives is
    its record, and a sealed step that has run must reach it."""
    try:
        print(line, flush=True)
    except (OSError, ValueError):
        return


def in_sealed_folder(path: Path) -> bool:
    return SEALED_FOLDER in path.parts or SEALED_FOLDER in path.resolve().parts


def readable(path: Path) -> Path:
    """The path of a file this module may open: never one in a folder named ``sealed``."""
    if in_sealed_folder(path):
        raise SystemExit(f"{path.as_posix()}: this module never opens the sealed folder")
    return path


def sha256_file(path: Path) -> str | None:
    """The sha256 of a file's bytes, or None when there is no such file."""
    path = readable(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def content_sha256(path: Path) -> str | None:
    """The sha256 of the decompressed content of a gzip file (None when the file is missing or
    is not a gzip file)."""
    path = readable(path)
    if not path.is_file():
        return None
    try:
        return hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()
    except (OSError, EOFError, zlib.error):
        return None


def read_json(path: Path) -> Any:
    """The content of a JSON file, or None when it is missing or not JSON."""
    try:
        return json.loads(readable(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dig(record: Any, *keys: str) -> Any:
    """``record[k1][k2]...``, or None when a key is missing on the way."""
    for key in keys:
        if not isinstance(record, Mapping) or key not in record:
            return None
        record = record[key]
    return record


def short(value: Any) -> str:
    """A hash as section 17 prints it: its first 16 characters, or the words that stand for it."""
    return value[:SHORT] if isinstance(value, str) and _HEX.fullmatch(value) else str(value)


def data_rows(path: Path) -> int | None:
    """The number of lines after the header line of a text file (None when it is missing)."""
    path = readable(path)
    if not path.is_file():
        return None
    return max(len(path.read_text(encoding="utf-8").splitlines()) - 1, 0)


# --------------------------------------------------------------------------------------------
# What the plan states
# --------------------------------------------------------------------------------------------


def plan_section(text: str, number: int) -> str:
    """The text of one numbered section of the plan (``## 17. ...`` to the next ``## ``)."""
    match = re.search(rf"^## {number}\. .*$", text, re.MULTILINE)
    if match is None:
        return ""
    rest = text[match.start() :]
    following = re.search(r"^## ", rest[1:], re.MULTILINE)
    return rest if following is None else rest[: following.start() + 1]


def hash_after(text: str, anchor: str) -> str | None:
    """The first 16-hex token in backticks after ``anchor``, within the same paragraph or list
    item (None when the anchor or the token is not there)."""
    match = re.search(anchor, text)
    if match is None:
        return None
    item = re.split(r"\n[ \t]*\n|\n[ \t]*[-*] ", text[match.end() :], maxsplit=1)[0]
    found = re.search(rf"`([0-9a-f]{{{SHORT}}})`", item)
    return None if found is None else found.group(1)


def stated_pins(plan_text: str) -> dict[str, str | None]:
    """The hash that section 17 of the plan states for each file of ``PINNED``."""
    section = plan_section(plan_text, 17)
    return {name: hash_after(section, anchor) for name, (_, anchor) in PINNED.items()}


# --------------------------------------------------------------------------------------------
# The files on disk, in the layout of the record
# --------------------------------------------------------------------------------------------


def file_entry(path: Path) -> dict[str, Any]:
    return {"file": path.as_posix(), "sha256": sha256_file(path)}


def guide_version(text: str) -> str:
    """The version in the guide's ``**Version ...`` line (``v1 draft``, ``v1``), as
    ``audit_sample.guide_version`` reads it."""
    match = re.search(r"\*\*Version (v\d+(?:\.\d+)*(?: [^,.*]+)?)", text)
    return match.group(1).strip() if match else "unknown"


def sample_list_files() -> dict[str, Path]:
    """Every sample list of PLAN.md section 3 that can be on disk before registration: the four
    lists of the first draw, the train-half outcome-audit sample, and the lists drawn after it."""
    files = {name: SAMPLES / f"sample_{name}.csv" for name in FIRST_DRAW}
    files["outcome_audit_train"] = OUTCOME_SAMPLE
    for path in sorted(SAMPLES_LATER.glob("sample_*.csv")):
        files[f"later_{path.stem.removeprefix('sample_')}"] = path
    return files


def sample_lists() -> dict[str, Any]:
    return {
        name: {**file_entry(path), "rows": data_rows(path)}
        for name, path in sample_list_files().items()
    }


def table_hashes() -> dict[str, Any]:
    """The open tables (gzip file and decompressed content), the eligible list and the three
    secondary lists; the id hashes and sizes of the lists are those in ``dataset_counts.json``."""
    counts = read_json(DATASET_COUNTS)
    return {
        "open": {
            path.name: {"gzip_sha256": sha256_file(path), "content_sha256": content_sha256(path)}
            for path in OPEN_TABLES
        },
        "eligible_list": {
            **file_entry(ELIGIBLE),
            "ids_sha256": dig(counts, "e3", "ids_sha256"),
            "statements": dig(counts, "e3", "statements"),
        },
        "secondary_lists": {
            name: {
                "ids_sha256": dig(counts, "secondary_lists_test", name, "ids_sha256"),
                "statements": dig(counts, "secondary_lists_test", name, "statements"),
            }
            for name in SECONDARY
        },
    }


def snapshot() -> dict[str, Any]:
    """Every hash of the record that can be read from the files on disk now."""
    guide = readable(GUIDE).read_text(encoding="utf-8") if GUIDE.is_file() else ""
    return {
        "captures": {"manifest": file_entry(MANIFEST)},
        "code": {name: sha256_file(HERE / name) for name in CODE},
        "code_other": {name: sha256_file(HERE / name) for name in CODE_OTHER},
        "tables": table_hashes(),
        "sample_lists": sample_lists(),
        "annotation": {
            "guide": {**file_entry(GUIDE), "version": guide_version(guide)},
            "availability_strings": file_entry(STRINGS),
        },
        "models": file_entry(MODELS),
    }


def registered_hashes(record: Mapping[str, Any]) -> dict[str, Any]:
    """The hashes that PLAN.md section 17 must hold, by label, from a record or a snapshot:
    lock file, capture manifest, code, open tables, eligible and secondary lists, sample lists,
    guide, availability-string list, MODELS.md and template pins. A value is None when the
    record has none. Sealed hashes are not among them."""
    out: dict[str, Any] = {
        "lock file": dig(record, "environment", "lock_file", "sha256"),
        "capture manifest": dig(record, "captures", "manifest", "sha256"),
    }
    out.update({f"code {name}": value for name, value in record.get("code", {}).items()})
    tables = record.get("tables", {})
    for name, pair in tables.get("open", {}).items():
        out[f"table {name} (gzip file)"] = pair.get("gzip_sha256")
        out[f"table {name} (decompressed content)"] = pair.get("content_sha256")
    out["eligible list (file)"] = dig(tables, "eligible_list", "sha256")
    for name in SECONDARY:
        out[f"secondary list {name} (ids)"] = dig(tables, "secondary_lists", name, "ids_sha256")
    for name, entry in record.get("sample_lists", {}).items():
        out[f"sample list {name}"] = entry.get("sha256")
    out["guide"] = dig(record, "annotation", "guide", "sha256")
    out["availability-string list"] = dig(record, "annotation", "availability_strings", "sha256")
    out["MODELS.md"] = dig(record, "models", "sha256")
    for name, pin in (dig(record, "prompts", "templates") or {}).items():
        out[f"template {name}"] = pin.get("sha256")
    return out


def environment() -> dict[str, Any]:
    """Python, the lock file and the libraries on which the bytes of the tables depend."""
    packages = {}
    for name in ("pandas", "numpy", "scikit-learn", "scipy"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {
        "python": platform.python_version(),
        "lock_file": file_entry(LOCK),
        "packages": packages,
    }


# --------------------------------------------------------------------------------------------
# The steps, as data
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One step of the freeze: a command, whether it touches sealed data, the files it writes.

    ``passes`` are the exit statuses that let the run go on. ``fixed`` are files that must keep
    their bytes. Of a sealed step's output, ``keep`` names the lines that go to the record and
    to the checks after the step, and ``echo`` those shown at once; an open step's output is
    shown and kept whole.
    """

    name: str
    command: tuple[str, ...]
    sealed: bool
    writes: tuple[str, ...] = ()
    about: str = ""
    passes: tuple[int, ...] = (0,)
    fixed: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    echo: tuple[str, ...] = ()


def steps(pin: str, cutoff: str = CUTOFF) -> tuple[Step, ...]:
    """The steps of the freeze run, in order. ``pin`` is the hash the plan states for the
    capture manifest; ``cutoff`` goes to the builder's Gate 1 counts."""
    module = (PYTHON, "-m")
    open_tables = tuple(path.as_posix() for path in OPEN_TABLES)
    lists = tuple((SAMPLES / f"sample_{name}.csv").as_posix() for name in FIRST_DRAW)
    open_build = f'from analysis.coling import corpus; corpus.open_build(cutoff="{cutoff}")'
    string_list = "from analysis.coling import corpus; corpus.write_availability_strings()"
    return (
        Step(
            MANIFEST_CHECK,
            (*module, "analysis.coling.manifest", "--check", "--pin", pin),
            sealed=False,
            about="the capture folder is the manifest's set, and the manifest has the plan's hash",
        ),
        Step(
            STRING_LIST,
            (PYTHON, "-c", string_list),
            sealed=False,
            writes=(STRINGS.as_posix(),),
            about="the availability-string list, written again: it must be the list as checked",
            fixed=(STRINGS.as_posix(),),
        ),
        Step(
            PINS,
            (*module, "analysis.coling.read", "--print-pins"),
            sealed=False,
            about="every prompt template has the digest pinned in read.py",
        ),
        Step(
            OPEN_BUILD,
            (PYTHON, "-c", open_build),
            sealed=False,
            writes=open_tables,
            about="events of every period and train outcomes; nothing sealed",
        ),
        Step(
            FORM_CHECK,
            (*module, "analysis.coling.forms", "--check"),
            sealed=False,
            about="no rule reading changed on a pair the old golden file shares with the build",
            passes=(0, 1),
        ),
        Step(
            FORMS,
            (*module, "analysis.coling.forms"),
            sealed=False,
            writes=tuple(
                (OUT / name).as_posix()
                for name in ("form_counts.json", "rule_readings_train_golden.csv.gz")
            ),
            about="form counts and the golden readings, on the frozen events table",
        ),
        Step(
            SAMPLE_LISTS,
            (*module, "analysis.coling.audit_sample", "draw", "--fixed", *FIRST_DRAW),
            sealed=False,
            writes=(
                *lists,
                (SAMPLES / "strata.csv").as_posix(),
                (OUT / "audit" / "manifest.json").as_posix(),
            ),
            about="the four lists that were handed out, held fixed on the frozen events table",
            fixed=lists,
        ),
        Step(
            DATASET,
            (*module, "analysis.coling.dataset"),
            sealed=False,
            writes=tuple(
                path.as_posix() for path in (OUT / "statements.csv.gz", ELIGIBLE, DATASET_COUNTS)
            ),
            about="statement table, eligible list and counts; it reads the four lists",
        ),
        Step(
            SEALED_BUILD,
            (*module, "analysis.coling.corpus", "--cutoff", cutoff),
            sealed=True,
            writes=(*open_tables, *SEALED_TABLES),
            about="the one sealed write; its open tables must be those of the open build",
            keep=(HASH_LINE, GATE_LINE),
            echo=(HASH_LINE,),
        ),
        Step(
            COUNTS,
            (
                *module,
                "analysis.coling.sealed_counts",
                "--expect-sha256",
                SEALED_HASH,
                "--expect-eligible-sha256",
                ELIGIBLE_HASH,
                "--out",
                SEALED_COUNTS.as_posix(),
                *COUNTS_FLAGS,
            ),
            sealed=True,
            writes=(SEALED_COUNTS.as_posix(),),
            about="the counts-only code on the sealed file, with Gate 1 on the eligible list",
            echo=(REFUSAL,),
        ),
        Step(
            POWER,
            (*module, "analysis.coling.power"),
            sealed=False,
            writes=tuple((OUT / name).as_posix() for name in ("dev_losses.json", "power.json")),
            about="model-free predictors and power, with the registered scoreable counts",
        ),
    )


LATE_VALUES: dict[str, Callable[[Mapping[str, Any]], Any]] = {
    SEALED_HASH: lambda values: dig(values, "sealed", SEALED_TEST),
    ELIGIBLE_HASH: lambda values: values.get("eligible"),
}
"""The command arguments that only an earlier step can give."""


def filled(command: Sequence[str], values: Mapping[str, Any]) -> tuple[str, ...]:
    """A command with the hashes from earlier steps put in. Stops when one is not known."""
    out = []
    for part in command:
        value = LATE_VALUES[part](values) if part in LATE_VALUES else part
        if not value:
            raise LookupError(part)
        out.append(value)
    return tuple(out)


def display(command: Sequence[str]) -> str:
    """A command as the module docstrings write it, with ``python`` for the interpreter."""
    if command and command[0] == PYTHON:
        return "PYTHONPATH=. " + shlex.join(["python", *command[1:]])
    return shlex.join(command)


def entry_of(step: Step, status: str = NOT_RUN) -> dict[str, Any]:
    """The record entry of a step that has not run."""
    return {
        "name": step.name,
        "command": display(step.command),
        "sealed": step.sealed,
        "writes": list(step.writes),
        "status": status,
        "exit_status": None,
        "started": None,
        "finished": None,
        "lines": [],
    }


# --------------------------------------------------------------------------------------------
# Running a step
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finished:
    status: int
    stdout: str
    stderr: str


def run_command(command: Sequence[str], environ: Mapping[str, str]) -> Finished:
    """Run one command from the repository root and take its output; nothing is printed. Bytes
    that are not text are replaced, so that no output can stop the run after a step has run."""
    env = {**environ, "PYTHONPATH": "."}
    done = subprocess.run(
        list(command), capture_output=True, text=True, errors="replace", env=env, check=False
    )
    return Finished(done.returncode, done.stdout, done.stderr)


def git(*args: str) -> str | None:
    """The output of a read-only git command (None when it fails). ``GIT_*`` variables are
    dropped, so that the environment cannot point it at another repository."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", *args],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def uncommitted(paths: Sequence[str]) -> list[str] | None:
    """The lines of ``git status --porcelain`` for the paths: modified, staged, untracked and
    ignored files. Empty when all are committed; None when git cannot say."""
    state = git("status", "--porcelain", "--untracked-files=all", "--ignored", "--", *paths)
    return None if state is None else [line for line in state.splitlines() if line.strip()]


def head_commit() -> str | None:
    state = git("rev-parse", "HEAD")
    return state.strip() if state else None


@dataclass(frozen=True)
class Runtime:
    """What a run takes from outside: how a command is run, the clock that gives each step its
    start and end time, the environment, and what git says. The tests pass their own."""

    run: Callable[[Sequence[str], Mapping[str, str]], Finished] = run_command
    clock: Callable[[], str] = utc_now
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    uncommitted: Callable[[Sequence[str]], list[str] | None] = uncommitted
    head: Callable[[], str | None] = head_commit


def matches(patterns: Sequence[str], line: str) -> bool:
    return any(re.search(pattern, line) for pattern in patterns)


def kept_lines(step: Step, done: Finished) -> list[str]:
    """The output lines that go to the record: all of an open step's, the named ones of a
    sealed step's."""
    lines = done.stdout.splitlines()
    return [line for line in lines if matches(step.keep, line)] if step.sealed else lines


def error_type(stderr: str) -> str:
    """The class name of the error on the last line of a traceback, without its message."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    match = _ERROR_TYPE.match(lines[-1]) if lines else None
    return match.group(1) if match else "not given"


def show(step: Step, done: Finished) -> None:
    """Print a step's output: whole for an open step, the lines of ``echo`` for a sealed one."""
    lines = [*done.stdout.splitlines(), *done.stderr.splitlines()]
    if step.sealed:
        lines = [line for line in lines if matches(step.echo, line)]
    for line in lines:
        say(f"    {line}")
    if step.sealed and done.status not in step.passes:
        say(
            "    the rest of the output is withheld, because it may quote a sealed value; "
            f"error type: {error_type(done.stderr)}"
        )


def saved_files(step: Step) -> dict[str, bytes]:
    """The bytes of the files a step with ``fixed`` files writes, as they are before it runs."""
    if not step.fixed:
        return {}
    paths = [Path(name) for name in step.writes if not in_sealed_folder(Path(name))]
    return {path.as_posix(): path.read_bytes() for path in paths if path.is_file()}


def put_back(before: Mapping[str, bytes]) -> None:
    for name, data in before.items():
        Path(name).write_bytes(data)


def run_step(step: Step, values: dict[str, Any], rt: Runtime) -> dict[str, Any]:
    """Run one step and return its record entry: command, exit status, the start and end time
    read from ``rt.clock``, the lines kept, and ``problem`` when it failed. ``values`` carries
    what one step gives to a later one (hashes, the Gate 1 lines)."""
    entry = entry_of(step)
    try:
        command = filled(step.command, values)
    except LookupError as missing:
        return {**entry, "status": "failed", "problem": f"no earlier step gave {missing.args[0]}"}
    before = saved_files(step)
    absent = [name for name in step.fixed if name not in before]
    if absent:
        return {**entry, "status": "failed", "problem": f"not on disk: {', '.join(absent)}"}
    say(f"[{step.name}] {display(command)}")
    started = rt.clock()
    done = rt.run(command, rt.environ)
    finished = rt.clock()
    show(step, done)
    lines = kept_lines(step, done)
    problems = [] if done.status in step.passes else [f"exit status {done.status}"]
    changed = [name for name in step.fixed if sha256_file(Path(name)) != _sha(before[name])]
    if changed:
        put_back(before)
        problems.append(
            f"the step changed {', '.join(changed)}, which must keep its bytes; every file "
            "of the step was put back as it was"
        )
    if not problems:
        problems += AFTER.get(step.name, nothing_to_check)(lines, values)
    entry.update(
        command=display(command),
        status="failed" if problems else "ok",
        exit_status=done.status,
        started=started,
        finished=finished,
        lines=lines,
    )
    if problems:
        entry["problem"] = "; ".join(problems)
    return entry


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------
# Checks after a step
# --------------------------------------------------------------------------------------------


def nothing_to_check(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    return []


def printed_hashes(lines: Sequence[str], verb: str) -> dict[str, str]:
    """``{file name: sha256}`` from the builder's lines ``<verb> <path> sha256 <hash>``."""
    found = (_PRINTED_HASH.match(line) for line in lines)
    return {Path(m.group(2)).name: m.group(3) for m in found if m and m.group(1) == verb}


def gate_lines(lines: Sequence[str]) -> list[str]:
    """The Gate 1 block of the builder's report: counts only."""
    return [line for line in lines if re.search(GATE_LINE, line)]


def after_open_build(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    """Take the hashes of the two open tables and the Gate 1 lines as printed. A report whose
    Gate 1 counts cannot be read stops the run here, long before the sealed build."""
    values["open"] = printed_hashes(lines, "wrote")
    values["gate_lines"] = gate_lines(lines)
    problems = []
    missing = [path.name for path in OPEN_TABLES if path.name not in values["open"]]
    if missing:
        problems.append(f"the builder printed no hash for {', '.join(missing)}")
    if len(gate_counts(values["gate_lines"])) != len(GATE_NEEDS):
        problems.append("the builder's report does not give the four Gate 1 counts as expected")
    return problems


def after_sealed_build(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    """Take the two sealed hashes as printed, and require the open tables and the Gate 1 lines
    of the open build of the same run (the steps between the two builds read those tables)."""
    sealed = printed_hashes(lines, "sealed")
    values["sealed"] = sealed
    values["built_with"] = {name: sha256_file(HERE / name) for name in BUILD_CODE}
    problems = []
    missing = [Path(name).name for name in SEALED_TABLES if Path(name).name not in sealed]
    if missing:
        problems.append(f"the builder printed no sealed hash for {', '.join(missing)}")
    if printed_hashes(lines, "wrote") != values.get("open"):
        problems.append(
            "the open tables of this build do not have the hashes of the open build before it: "
            "the builder does not give the same bytes twice"
        )
    if gate_lines(lines) != values.get("gate_lines"):
        problems.append("the Gate 1 counts of this build are not those of the open build")
    return problems


def after_form_check(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    """No reading changed on a shared pair. The check exits with status 1 for stale outputs,
    which a new build always gives, and so does a script that stops on an error: the step
    passes only when the check printed its verdict."""
    if not any(re.search(FORM_VERDICT, line) for line in lines):
        return ["the check stopped before it compared the outputs"]
    changed = [int(m.group(1)) for line in lines if (m := _CHANGED.search(line))]
    if any(changed):
        return [f"{max(changed)} rule readings changed on pairs shared with the old golden file"]
    return []


def after_dataset(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    """The builder must have read the four lists of the first draw, and the eligible list must
    still be the one the sealed counts were taken on, if they were taken."""
    counts = read_json(DATASET_COUNTS)
    values["eligible"] = sha256_file(ELIGIBLE)
    first = dig(counts, "subsets", "first_draw")
    if not isinstance(first, Mapping) or values["eligible"] is None:
        return [f"{DATASET_COUNTS.name} or {ELIGIBLE.name} is not as the dataset builder writes it"]
    problems = []
    if first.get("lists_missing"):
        problems.append(f"first-draw lists not read: {', '.join(first['lists_missing'])}")
    if first.get("ids_not_in_the_statement_table"):
        problems.append("ids of the first-draw lists are not in the statement table")
    subsets = dig(counts, "subsets") or {}
    loose = [k for k, v in subsets.items() if isinstance(v, Mapping) and v.get("final") is False]
    if loose:
        problems.append(f"subsets not final: {', '.join(loose)}")
    counted = values.get("counted_eligible")
    if counted and counted != values["eligible"]:
        problems.append(
            "the eligible list is no longer the one the sealed counts were taken on "
            f"({short(counted)} then, {short(values['eligible'])} now); reading the sealed file "
            "again is a decision for the owner"
        )
    return problems


def count_lines(record: Any, prefix: str = "") -> list[str]:
    """Every count (an integer or a mask) and every sha256 of a nested record, one per line."""
    if isinstance(record, Mapping):
        return [
            line for key, value in record.items() for line in count_lines(value, f"{prefix}{key}.")
        ]
    is_count = isinstance(record, int) and not isinstance(record, bool)
    is_text = isinstance(record, str) and bool(_MASK.fullmatch(record) or _HEX.fullmatch(record))
    return [f"{prefix.rstrip('.')}: {record}"] if is_count or is_text else []


def counts_drift(counts: Any) -> list[str]:
    """The files that are no longer the ones the counts-only code ran on, by the hashes its
    file holds: the eligible list, the events table, the capture manifest and the code that
    sets the definitions. Empty when all are as they were, or when there is no counts file."""
    moved = []
    for key, path in COUNTED_FILES.items():
        was = dig(counts, "inputs", key, "sha256")
        if was and was != sha256_file(path):
            moved.append(path.name)
    for name, was in (dig(counts, "inputs", "code_sha256") or {}).items():
        if was != sha256_file(HERE / name):
            moved.append(name)
    return moved


def after_sealed_counts(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    """Read the counts from the file the script wrote and show them; its output is not shown."""
    counts = read_json(SEALED_COUNTS)
    if not isinstance(counts, Mapping):
        return [f"{SEALED_COUNTS.as_posix()} was not written"]
    for line in count_lines(counts):
        say(f"    {line}")
    for keys in FOR_POWER:
        value = dig(counts, *keys)
        masked = isinstance(value, str) and bool(_MASK.fullmatch(value))
        if not (isinstance(value, int) or (masked and value.startswith(">"))):
            given = value if masked else "not a count"
            say(f"    note: {keys[-1]} is {given}: the power step needs a count or a bound")
    values["counted_eligible"] = values.get("eligible")
    if dig(counts, "inputs", "sealed_outcomes", "sha256") != dig(values, "sealed", SEALED_TEST):
        return ["the counts file names another sealed file than the one the build printed"]
    return []


def after_pins(lines: Sequence[str], values: dict[str, Any]) -> list[str]:
    try:
        pins = json.loads("\n".join(lines))
    except ValueError:
        pins = None
    if not isinstance(dig(pins, "templates"), Mapping):
        return ["the pins were not printed as JSON with a 'templates' entry"]
    values["pins"] = pins
    for name, pin in pins["templates"].items():
        if pin.get("pending"):
            say(f"    note: {name} still waits for {', '.join(pin['pending'])}")
    return []


AFTER: dict[str, Callable[[Sequence[str], dict[str, Any]], list[str]]] = {
    PINS: after_pins,
    OPEN_BUILD: after_open_build,
    SEALED_BUILD: after_sealed_build,
    FORM_CHECK: after_form_check,
    DATASET: after_dataset,
    COUNTS: after_sealed_counts,
}
"""What is read from a step's kept lines or its files once it has passed; each returns the
problems found, and a step with a problem has failed."""


# --------------------------------------------------------------------------------------------
# Gate 1
# --------------------------------------------------------------------------------------------


def meets(value: Any, need: int) -> bool | None:
    """Whether a count meets a threshold; None when a masked count does not say."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value >= need
    if isinstance(value, str) and value.startswith("<"):
        return False if int(value[1:]) <= need else None
    if isinstance(value, str) and value.startswith(">"):
        return True if int(value[1:]) + 1 >= need else None
    return None


def gate_part(counts: Mapping[str, Any]) -> dict[str, Any]:
    """One part of the gate record: the four counts, each with its threshold, and whether all
    four are met (None when a count is missing or masked so that it cannot be told)."""
    rows = {
        name: {"count": counts.get(name), "need": need, "met": meets(counts.get(name), need)}
        for name, need in GATE_NEEDS.items()
    }
    met = [row["met"] for row in rows.values()]
    return {"thresholds": rows, "passes": None if None in met else all(met)}


def gate_counts(lines: Sequence[str]) -> dict[str, int]:
    """The builder's four counts, from the lines of its report that carry ``(need >= N)``."""
    by_need = {need: name for name, need in GATE_NEEDS.items()}
    counts = {}
    for line in lines:
        for count, need in _NEED.findall(line):
            if int(need) in by_need:
                counts[by_need[int(need)]] = int(count)
    return counts


def builder_gate(lines: Sequence[str]) -> dict[str, Any]:
    """The builder's part of the gate record: its lines as printed, and the four counts."""
    return {"lines": list(lines), **gate_part(gate_counts(lines))}


def list_gate(counts: Any) -> dict[str, Any] | str:
    """The part on the eligible list, from the file of the counts-only code."""
    if not isinstance(counts, Mapping):
        return NOT_RUN
    values = {name: dig(counts, *keys) for name, keys in GATE_ON_THE_LIST.items()}
    return {**gate_part(values), "scoreable_statements": dig(counts, *SCOREABLE)}


def gate_record(values: Mapping[str, Any], counted: bool) -> dict[str, Any]:
    """The Gate 1 record of PLAN.md section 12, in its two parts."""
    return {
        "builder_gate_set": builder_gate(values.get("gate_lines", [])),
        "eligible_list": list_gate(read_json(SEALED_COUNTS)) if counted else NOT_RUN,
    }


def counts_as_registered(counted: bool) -> list[str] | str:
    """Every count of the counts file as it is registered (a masked count as printed; PLAN.md,
    standing rules), one per line with its key; the hashes of its inputs are left to the file.
    Nothing but an integer or a mask is taken from the file."""
    if not counted:
        return NOT_RUN
    lines = count_lines(read_json(SEALED_COUNTS))
    return [line for line in lines if not line.startswith(("inputs.", "masked_below"))]


def gate_text(gate: Mapping[str, Any]) -> list[str]:
    """The gate record as lines: the builder's own lines, then the counts on the eligible list."""
    words = {True: "met", False: "NOT met", None: "cannot be told"}
    builder, listed = gate["builder_gate_set"], gate["eligible_list"]
    lines = [*builder["lines"], f"  builder's gate set: {words[builder['passes']]}"]
    if listed == NOT_RUN:
        return [*lines, f"Gate 1 on the E3 eligible list (counts-only code): {NOT_RUN}"]
    lines.append("Gate 1 on the E3 eligible list (counts-only code, displayed presentation):")
    for name, row in listed["thresholds"].items():
        lines.append(f"  {name} {row['count']} (need >= {row['need']}): {words[row['met']]}")
    lines.append(f"  scoreable statements {listed['scoreable_statements']} (no threshold)")
    lines.append(f"  eligible list: {words[listed['passes']]}")
    return lines


def registered_text(counts: Any) -> list[str]:
    return [NOT_RUN] if counts == NOT_RUN else list(counts)


# --------------------------------------------------------------------------------------------
# The record and its Markdown rendering
# --------------------------------------------------------------------------------------------


def step_outputs(all_steps: Sequence[Step]) -> dict[str, str | None]:
    """The sha256 of every file a step writes outside the sealed folder."""
    names = sorted({name for step in all_steps for name in step.writes})
    return {name: sha256_file(Path(name)) for name in names if not in_sealed_folder(Path(name))}


def sealed_fields(values: Mapping[str, Any]) -> dict[str, str]:
    sealed = values.get("sealed") or {}
    return {Path(name).name: sealed.get(Path(name).name, NOT_RUN) for name in SEALED_TABLES}


def build_record(
    mode: str,
    status: str,
    entries: Sequence[Mapping[str, Any]],
    values: Mapping[str, Any],
    inputs: Mapping[str, Any],
    all_steps: Sequence[Step] = (),
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The record of a run. The file hashes are read only when the run is complete; the sealed
    hashes, as printed, are in it from the moment the build gave them."""
    record: dict[str, Any] = {
        "about": ABOUT,
        "mode": mode,
        "status": status,
        "seed": SEED,
        "inputs": dict(inputs),
        "environment": environment(),
        "tables": {"sealed": sealed_fields(values)},
        "steps": [dict(entry) for entry in entries],
        "carried": dict(values),
    }
    if status == "complete":
        counted = any(e["name"] == COUNTS and e["status"] == "ok" for e in entries)
        found = snapshot()
        found["tables"]["sealed"] = record["tables"]["sealed"]
        record.update(found)
        record["prompts"] = values.get("pins")
        record["counts"] = {
            "gate1": gate_record(values, counted),
            "sealed_counts": counts_as_registered(counted),
        }
        record["outputs"] = step_outputs(all_steps)
    if previous and "verify_rerun" in previous:
        record["verify_rerun"] = previous["verify_rerun"]
    return record


def after_steps(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    """What is checked once every step has passed: the sealed counts, taken in this run or kept
    from an earlier one, must be those of the files and the code now on disk."""
    counted = any(e["name"] == COUNTS and e["status"] == "ok" for e in entries)
    moved = counts_drift(read_json(SEALED_COUNTS)) if counted else []
    if not moved:
        return []
    return [
        f"changed since the sealed counts were taken: {', '.join(moved)}; the counts are not "
        "those of the files on disk, and reading the sealed file again is a decision for the "
        "owner"
    ]


def code_lines(record: Mapping[str, Any]) -> list[str]:
    return [f"- `{name}`: `{short(value)}`" for name, value in record.get("code", {}).items()]


def table_lines(record: Mapping[str, Any]) -> list[str]:
    tables = record["tables"]
    sealed = "; ".join(f"`{name}` `{short(value)}`" for name, value in tables["sealed"].items())
    lines = [f"- Sealed, as printed by the freeze run: {sealed}."]
    for name, pair in tables.get("open", {}).items():
        lines.append(
            f"- Open: `{name}`, gzip file `{short(pair['gzip_sha256'])}`, decompressed content "
            f"`{short(pair['content_sha256'])}`."
        )
    listed = tables.get("eligible_list", {})
    lines.append(
        f"- The E3 eligible list `{listed.get('file')}` ({listed.get('statements')} statements): "
        f"file `{short(listed.get('sha256'))}`, ids `{short(listed.get('ids_sha256'))}`."
    )
    for name, entry in tables.get("secondary_lists", {}).items():
        lines.append(
            f"- Secondary list `{name}` ({entry['statements']} statements): ids "
            f"`{short(entry['ids_sha256'])}`."
        )
    for name, entry in record.get("sample_lists", {}).items():
        lines.append(
            f"- Sample list `{name}` (`{entry['file']}`, {entry['rows']} rows): "
            f"`{short(entry['sha256'])}`."
        )
    return lines


def prompt_lines(record: Mapping[str, Any]) -> list[str]:
    lines = []
    for name, pin in (dig(record, "prompts", "templates") or {}).items():
        pending = f"; waits for {', '.join(pin['pending'])}" if pin.get("pending") else ""
        lines.append(f"- `{name}`: `{pin.get('sha256')}`{pending}")
    return lines or [f"- {NOT_RUN}"]


def rerun_lines(record: Mapping[str, Any]) -> list[str]:
    rerun = record.get("verify_rerun")
    if not rerun:
        return ["The one rerun that checks the sealed hashes: not run yet."]
    said = {True: "both sealed hashes and both open tables as recorded", False: "A DIFFERENCE"}
    result = said.get(rerun.get("matches"), "not finished")
    return [f"The one rerun that checks the sealed hashes: started {rerun['started']}; {result}."]


def history_lines(record: Mapping[str, Any]) -> list[str]:
    """What a record that was written again says of the runs before it."""
    inputs = record["inputs"]
    lines = []
    runs = inputs.get("earlier_runs") or []
    if runs:
        said = "; ".join(f"started {run.get('started')}, {run.get('status')}" for run in runs)
        lines += [f"Written again by {MODE_FLAGS[CONTINUE]}. Earlier runs: {said}.", ""]
    if inputs.get("counts_again"):
        lines += [
            f"The counts-only code was run a second time after it had stopped half way "
            f"({COUNTS_AGAIN}).",
            "",
        ]
    return lines


def render(record: Mapping[str, Any]) -> str:
    """The record as Markdown, in the order of PLAN.md section 17."""
    env, inputs = record["environment"], record["inputs"]
    head = [
        "# Freeze record",
        "",
        f"Rendered from `{RECORD.as_posix()}`. Mode: {record['mode']}. Status: "
        f"{record['status']}. Started {inputs.get('started')}, finished {inputs.get('finished')} "
        f"(UTC). Commit {inputs.get('commit')}. Hashes are the first {SHORT} hex characters of "
        "sha256; the template pins are given whole.",
        "",
        *rerun_lines(record),
        "",
        *history_lines(record),
    ]
    if record["status"] != "complete":
        failed = [f"- {e['name']}: {e.get('problem')}" for e in record["steps"] if e.get("problem")]
        failed += [f"- {line}" for line in record.get("problems", [])]
        sealed = "; ".join(f"`{k}` `{short(v)}`" for k, v in record["tables"]["sealed"].items())
        return "\n".join([*head, "The run did not finish.", *failed, "", f"Sealed: {sealed}.", ""])
    packages = ", ".join(f"{name} {version}" for name, version in env["packages"].items())
    manifest = record["captures"]["manifest"]
    guide = record["annotation"]["guide"]
    strings = record["annotation"]["availability_strings"]
    body = [
        f"**Environment.** Python {env['python']}; the lock file `{env['lock_file']['file']}`, "
        f"hash `{short(env['lock_file']['sha256'])}`; {packages}.",
        "",
        f"**Captures.** The capture manifest `{manifest['file']}`: hash "
        f"`{short(manifest['sha256'])}`; cutoff given to the builder: {inputs.get('cutoff')}.",
        "",
        "**Code (hashed at registration).**",
        "",
        *code_lines(record),
        "",
        "**Tables.**",
        "",
        *table_lines(record),
        "",
        "**Annotation.**",
        "",
        f"- `{guide['file']}` (version line: {guide['version']}): `{short(guide['sha256'])}`.",
        f"- The availability-string list `{strings['file']}`: `{short(strings['sha256'])}`.",
        "",
        "**Counts.** The Gate 1 record (section 12):",
        "",
        "```",
        *gate_text(record["counts"]["gate1"]),
        "```",
        "",
        f"The counts of `{SEALED_COUNTS.as_posix()}`, as registered:",
        "",
        "```",
        *registered_text(record["counts"]["sealed_counts"]),
        "```",
        "",
        f"**Models.** `{record['models']['file']}`: `{short(record['models']['sha256'])}`.",
        "",
        "**Prompts.**",
        "",
        *prompt_lines(record),
        "",
    ]
    return "\n".join([*head, *body])


def write_record(record: Mapping[str, Any]) -> None:
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    RECORD_MD.write_text(render(record), encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Checks before the first step
# --------------------------------------------------------------------------------------------


def key_like(environ: Mapping[str, str]) -> list[str]:
    """The names of the variables that look like an API key and are not empty."""
    return sorted(name for name, value in environ.items() if value and KEY_LIKE.search(name))


def sealed_started(record: Any) -> bool:
    """Whether a record shows that a sealed build was started, or holds a sealed hash."""
    if not isinstance(record, Mapping):
        return False
    built = [e for e in record.get("steps", []) if e.get("name") == SEALED_BUILD]
    hashes = (dig(record, "tables", "sealed") or {}).values()
    return any(e.get("status") != NOT_RUN for e in built) or any(v != NOT_RUN for v in hashes)


def hashed_inputs() -> list[str]:
    """The files whose hash goes into the record and that no step writes: they must be
    committed before the freeze run."""
    code = [(HERE / name).as_posix() for name in (*CODE, *CODE_OTHER)]
    return [*code, *(path.as_posix() for path in (GUIDE, MODELS, LOCK, MANIFEST, STRINGS))]


def check_pins(pins: Mapping[str, str | None]) -> list[str]:
    problems = []
    for name, stated in pins.items():
        found = sha256_file(PINNED[name][0])
        if stated is None:
            problems.append(f"PLAN.md section 17 states no hash for {name}")
        elif found is None or not found.startswith(stated):
            problems.append(f"{name}: the plan states {stated}, the file has {short(found)}")
    return problems


def check_committed(rt: Runtime) -> list[str]:
    """Every hashed input is on disk and is the committed file (not modified, staged, untracked
    or ignored)."""
    names = hashed_inputs()
    missing = [f"not on disk: {name}" for name in names if not readable(Path(name)).is_file()]
    state = rt.uncommitted(names)
    if state is None:
        return [*missing, "git could not say whether the hashed files are committed"]
    return [*missing, *(f"not committed: {line.strip()}" for line in state)]


def check_cutoff(cutoff: str) -> list[str]:
    """Gate 1's fourth threshold is on one cutoff month in both parts of its record: the builder
    takes it from ``--cutoff``, the counts-only code from its own table. A day of another month
    would give a record whose two parts differ, and the sealed build is not run again."""
    if cutoff[:7] == CUTOFF[:7]:
        return []
    return [
        f"--cutoff {cutoff} is not a day of {CUTOFF[:7]}, the cutoff month of the gate model in "
        "the counts-only code; another month is an edit of CUTOFF here and of the table there"
    ]


def sealed_mark() -> Any:
    """The mark of a sealed build that was started, as read from disk: None when there is none,
    and the words ``not readable`` for a file that is there and is not JSON."""
    if not SEALED_MARK.exists():
        return None
    found = read_json(SEALED_MARK)
    return found if isinstance(found, Mapping) else "not readable"


def mark_sealed_build(inputs: Mapping[str, Any], started: str) -> None:
    """Leave the mark that the sealed build is about to start. The file is created, never
    written over: when it is already there, another run has started the sealed build, and this
    one stops before it writes anything."""
    mark = {
        "about": "The sealed build of the corpus freeze was started. It is run once.",
        "started": started,
        "commit": inputs.get("commit"),
        "cutoff": inputs.get("cutoff"),
        "record": RECORD.as_posix(),
    }
    readable(SEALED_MARK).parent.mkdir(parents=True, exist_ok=True)
    try:
        with SEALED_MARK.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(mark, indent=1) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise SystemExit(
            f"refused: {SEALED_MARK.as_posix()} is there: a sealed build was started by another "
            "run. Nothing sealed was written by this one, and the record was left as it was."
        ) from None


def preflight(
    mode: str, pins: Mapping[str, str | None], previous: Any, rt: Runtime, counts_due: bool
) -> list[str]:
    """The reasons not to start, empty when there is none. ``counts_due`` says that the
    counts-only code will run, which needs its output file not to be there yet."""
    problems = [
        f"the environment holds {name}: no API key may be set" for name in key_like(rt.environ)
    ]
    problems += check_pins(pins)
    if RECORD.exists() and not isinstance(previous, Mapping):
        problems.append(
            f"{RECORD.as_posix()} cannot be read as a record; it may be that of a sealed build, "
            "so it is not written over (move it away)"
        )
    if mode in (OPEN_ONLY, FREEZE) and sealed_started(previous):
        problems.append(
            f"{RECORD.as_posix()} is the record of a run that started the sealed build, which "
            "is run once; a second sealed build is the owner's decision (move the record and "
            f"{SEALED_MARK.as_posix()} away and note it in the plan)"
        )
    mark = sealed_mark()
    if mode in (OPEN_ONLY, FREEZE) and mark is not None:
        problems.append(
            f"{SEALED_MARK.as_posix()} is there: a sealed build was started (on "
            f"{dig(mark, 'started') or 'a day the mark does not give'}), and it is run once; a "
            "second sealed build is the owner's decision (move the mark and the record away and "
            "note it in the plan)"
        )
    if counts_due and SEALED_COUNTS.exists():
        problems.append(
            f"{SEALED_COUNTS.as_posix()} is already there; the counts-only code runs once"
        )
    if mode != OPEN_ONLY:
        problems += check_committed(rt)
    return problems


def notes(previous: Any) -> list[str]:
    """What the freeze run says before it starts and does not stop for: a guide that is not yet
    v1, and no complete rehearsal of the present code on record."""
    lines = []
    found = snapshot()
    guide = found["annotation"]["guide"]
    if guide["version"] != "v1":
        lines.append(
            f"the guide's version line says {guide['version']!r}: a guide changed after this "
            "run needs --continue-after-sealed, which stops if the eligible list changes with it"
        )
    rehearsed = dig(previous, "mode") == OPEN_ONLY and dig(previous, "status") == "complete"
    if not rehearsed or dig(previous, "code") != found["code"]:
        lines.append("no complete rehearsal (--open-only) of the present code is on record")
    return lines


def describe_checks(mode: str, pins: Mapping[str, str | None]) -> list[str]:
    """The checks before the first step in words, for the dry run."""
    lines = [
        f"no other run is under way ({RUN_LOCK.as_posix()})",
        "no variable that looks like an API key is set",
    ]
    committed = "every hashed input is on disk and committed: " + " ".join(hashed_inputs())
    if mode == VERIFY:
        lines.append(f"{RECORD.as_posix()} is the record of a complete freeze run, with no rerun")
        lines.append(f"{' and '.join(BUILD_CODE)}, Python and the libraries are the record's")
        lines.append("the capture folder is the manifest's set (step 1, before the rerun counts)")
        return [*lines, committed]
    lines += [f"{name} has the hash the plan states ({stated})" for name, stated in pins.items()]
    if mode in (OPEN_ONLY, FREEZE):
        lines.append(f"--cutoff is a day of {CUTOFF[:7]}, the month the counts-only code holds")
        lines.append(f"no record of a run that started the sealed build ({RECORD.as_posix()})")
        lines.append(f"no mark of a sealed build that was started ({SEALED_MARK.as_posix()})")
    if mode == CONTINUE:
        lines.append(
            f"{RECORD.as_posix()} is the record of a freeze run whose sealed build finished"
        )
        lines.append("the open tables on disk are those of that run")
        lines.append(
            "the counts-only code finished or never started in that run; if it stopped half "
            f"way, {COUNTS_AGAIN} is given"
        )
    if mode != OPEN_ONLY:
        lines.append(f"no counts file yet, unless its step is kept ({SEALED_COUNTS.as_posix()})")
        lines.append(committed)
    return lines


def dry_note(mode: str, step: Step) -> str:
    """What a mode does with a step, when it does not simply run it."""
    if mode == OPEN_ONLY and step.sealed:
        return " (not run in this mode)"
    if mode == VERIFY:
        return "" if step.name in (MANIFEST_CHECK, SEALED_BUILD) else " (not run in this mode)"
    if mode == CONTINUE and step.name in (OPEN_BUILD, SEALED_BUILD):
        return " (not run in this mode)"
    if mode == CONTINUE and step.sealed:
        return f" (kept if it finished; run if it never started, or with {COUNTS_AGAIN})"
    return ""


# --------------------------------------------------------------------------------------------
# The modes
# --------------------------------------------------------------------------------------------


def kept_entries(mode: str, all_steps: Sequence[Step], previous: Any) -> dict[str, dict[str, Any]]:
    """The steps a mode does not run, each with the record entry that stands for it."""
    if mode == OPEN_ONLY:
        return {step.name: entry_of(step) for step in all_steps if step.sealed}
    if mode != CONTINUE:
        return {}
    earlier = {e["name"]: dict(e) for e in previous.get("steps", [])}
    done = {name for name, e in earlier.items() if e.get("sealed") and e.get("status") == "ok"}
    return {name: earlier[name] for name in ({OPEN_BUILD, SEALED_BUILD} | done) if name in earlier}


def build_inputs_moved(record: Mapping[str, Any]) -> list[str]:
    """What the sealed build of a record ran on that is no longer on disk as it was: the code
    of ``BUILD_CODE``, and the capture manifest, rule reader and availability list at the hashes
    the plan stated then."""
    problems = []
    for name, was in (dig(record, "carried", "built_with") or dict.fromkeys(BUILD_CODE)).items():
        if was is None or sha256_file(HERE / name) != was:
            problems.append(f"{name} is not the file the sealed build ran")
    for name, was in (dig(record, "inputs", "plan_states") or {}).items():
        now = sha256_file(PINNED[name][0]) or ""
        if name != LOCK.name and not (was and now.startswith(was)):
            problems.append(f"{name} does not have the hash the plan stated at the freeze run")
    return problems


def counts_stopped_half_way(previous: Any) -> bool:
    """Whether the counts-only code was launched in the run of a record and did not finish. It
    may then have opened the sealed file, although it wrote and printed no count."""
    entry = next((e for e in (dig(previous, "steps") or []) if e.get("name") == COUNTS), {})
    status = entry.get("status")
    return status == "started" or (status == "failed" and bool(entry.get("started")))


def can_continue(previous: Any, counts_again: bool = False) -> list[str]:
    """Why a run cannot go on from the record on disk; empty when it can. ``counts_again`` says
    that the owner lets the counts-only code run a second time after it stopped half way."""
    built = [e for e in (dig(previous, "steps") or []) if e.get("name") == SEALED_BUILD]
    if dig(previous, "mode") != FREEZE or not built or built[0].get("status") != "ok":
        return [
            f"{RECORD.as_posix()} is not the record of a freeze run whose sealed build finished"
        ]
    carried = dig(previous, "carried", "open") or {}
    moved = [p.name for p in OPEN_TABLES if sha256_file(p) != carried.get(p.name)]
    problems = [f"{name} on disk is not the table of the freeze run" for name in moved]
    half_way = counts_stopped_half_way(previous)
    if half_way and not counts_again:
        problems.append(
            "the counts-only code was started in the freeze run and did not finish; it may have "
            "opened the sealed file, and it is run once. Running it again is the owner's "
            f"decision: pass {COUNTS_AGAIN} and note it in the plan"
        )
    if counts_again and not half_way:
        problems.append(
            f"{COUNTS_AGAIN} does not apply: the counts-only code did not stop half way in the "
            "run of the record"
        )
    return problems + build_inputs_moved(previous)


def earlier_runs(previous: Any) -> list[dict[str, Any]]:
    """The runs a record went through before the one that goes on from it: when each started
    and finished, on which commit, and how it ended (``running`` for a run that was killed)."""
    was = dig(previous, "inputs") or {}
    last = {key: was.get(key) for key in ("started", "finished", "commit")}
    return [*(was.get("earlier_runs") or []), {**last, "status": dig(previous, "status")}]


def run_steps(
    all_steps: Sequence[Step],
    kept: Mapping[str, Mapping[str, Any]],
    values: dict[str, Any],
    rt: Runtime,
    checkpoint: Callable[[Sequence[Mapping[str, Any]]], None],
) -> list[dict[str, Any]]:
    """Run the steps in order and return their record entries. A step in ``kept`` is not run
    and has the entry given there; after the first failure nothing more is run.
    ``checkpoint`` is called with the entries so far just before a sealed step starts (its own
    entry then says ``started``) and again as soon as it has ended, so that what a sealed step
    gave is on disk before anything else is run."""
    entries: list[dict[str, Any]] = []
    failed = False
    for step in all_steps:
        if step.name in kept:
            entries.append(dict(kept[step.name]))
        elif failed:
            entries.append(entry_of(step))
        else:
            if step.sealed:
                checkpoint([*entries, entry_of(step, "started")])
            entries.append(run_step(step, values, rt))
            if step.sealed:
                checkpoint(entries)
            failed = entries[-1]["status"] != "ok"
            if failed:
                say(f"FAILED at [{step.name}]: {entries[-1]['problem']}")
    return entries


def run_mode(mode: str, args: argparse.Namespace, rt: Runtime, steps_of: Callable) -> int:
    """The rehearsal, the freeze run, or the continuation of a freeze run."""
    pins = stated_pins(args.plan.read_text(encoding="utf-8"))
    previous = read_json(RECORD)
    cutoff = dig(previous, "inputs", "cutoff") if mode == CONTINUE else args.cutoff
    if mode == CONTINUE:
        problems = can_continue(previous, args.counts_again)
    else:
        problems = check_cutoff(cutoff)
    all_steps = steps_of(pins["capture_manifest.csv"] or "", cutoff or args.cutoff)
    kept = {} if problems else kept_entries(mode, all_steps, previous)
    counts_due = any(step.name == COUNTS and step.name not in kept for step in all_steps)
    problems += preflight(mode, pins, previous, rt, counts_due)
    if problems:
        for line in problems:
            say(f"refused: {line}")
        return 1
    for line in notes(previous) if mode == FREEZE else []:
        say(f"note: {line}")
    values = dict(dig(previous, "carried") or {}) if mode == CONTINUE else {}
    inputs = {
        "cutoff": cutoff,
        "captures": CAPTURES.as_posix(),
        "plan_states": dict(pins),
        "commit": rt.head(),
        "started": rt.clock(),
        "finished": None,
    }
    if mode == CONTINUE:
        inputs["earlier_runs"] = earlier_runs(previous)
        inputs["counts_again"] = args.counts_again or bool(dig(previous, "inputs", "counts_again"))
    label = FREEZE if mode == CONTINUE else mode

    def checkpoint(entries: Sequence[Mapping[str, Any]]) -> None:
        if (entries[-1]["name"], entries[-1]["status"]) == (SEALED_BUILD, "started"):
            mark_sealed_build(inputs, rt.clock())
        write_record(build_record(label, "running", entries, values, inputs, previous=previous))

    entries = run_steps(all_steps, kept, values, rt, checkpoint)
    complete = all(e["status"] == "ok" or e["name"] in kept for e in entries)
    late = after_steps(entries) if complete else []
    for line in late:
        say(f"FAILED: {line}")
    complete = complete and not late
    inputs["finished"] = rt.clock()
    status = "complete" if complete else "failed"
    record = build_record(label, status, entries, values, inputs, all_steps, previous)
    if late:
        record["problems"] = late
    write_record(record)
    if complete:
        for line in gate_text(record["counts"]["gate1"]):
            say(line)
    say(f"{status}: wrote {RECORD.as_posix()} and {RECORD_MD.as_posix()}")
    return 0 if complete else 1


def can_rerun(record: Any, rt: Runtime) -> list[str]:
    """Why the one rerun cannot start; empty when it can."""
    if dig(record, "mode") != FREEZE or dig(record, "status") != "complete":
        return [f"{RECORD.as_posix()} is not the record of a complete freeze run"]
    if "verify_rerun" in record:
        return [f"the one rerun was started on {record['verify_rerun'].get('started')}"]
    problems = [
        f"the environment holds {name}: no API key may be set" for name in key_like(rt.environ)
    ]
    problems += build_inputs_moved(record)
    now = environment()
    for key in ("python", "packages"):
        if now[key] != record["environment"][key]:
            problems.append(f"{key}: {now[key]} here, {record['environment'][key]} in the record")
    return problems + check_committed(rt)


def verify_rerun(rt: Runtime, steps_of: Callable) -> int:
    """Build the corpus once more with the command of the freeze run and compare what it prints
    with the record: both sealed hashes, both open tables. Only the result is added to the
    record."""
    record = read_json(RECORD)
    problems = can_rerun(record, rt)
    if problems:
        for line in problems:
            say(f"refused: {line}")
        return 1
    pin, cutoff = (
        record["inputs"]["plan_states"]["capture_manifest.csv"],
        record["inputs"]["cutoff"],
    )
    by_name = {step.name: step for step in steps_of(pin, cutoff)}
    values = {key: record["carried"][key] for key in ("open", "gate_lines")}
    checked = run_step(by_name[MANIFEST_CHECK], values, rt)
    if checked["status"] != "ok":
        say(f"refused: the capture set is not the manifest's ({checked['problem']})")
        return 1
    record["verify_rerun"] = {"started": rt.clock(), "finished": None, "matches": None}
    write_record(record)
    built = run_step(by_name[SEALED_BUILD], values, rt)
    same = (
        built["status"] == "ok"
        and sealed_fields(values) == record["tables"]["sealed"]
        and all(sha256_file(p) == record["carried"]["open"].get(p.name) for p in OPEN_TABLES)
    )
    record["verify_rerun"].update(
        finished=rt.clock(), matches=same, sealed=sealed_fields(values), steps=[checked, built]
    )
    write_record(record)
    if built.get("problem"):
        say(f"FAILED at [{built['name']}]: {built['problem']}")
    if same:
        say("the rerun gave both sealed hashes and both open tables of the freeze run")
    else:
        say(
            "THE RERUN DOES NOT CONFIRM the freeze run; whatever it wrote is now on disk in "
            "place of the freeze run's files"
        )
    return 0 if same else 1


def dry_run(mode: str, args: argparse.Namespace, steps_of: Callable) -> int:
    """Print the checks and the steps of a mode; nothing is run and nothing is hashed."""
    pins = stated_pins(args.plan.read_text(encoding="utf-8"))
    all_steps = steps_of(pins["capture_manifest.csv"] or "<no hash in the plan>", args.cutoff)
    say(f"dry run of {MODE_FLAGS[mode]}: nothing is run")
    say("checks before the first step:")
    for line in describe_checks(mode, pins):
        say(f"  - {line}")
    say("steps:")
    for number, step in enumerate(all_steps, start=1):
        kind = "SEALED" if step.sealed else "open"
        say(f"  {number:2d}. {step.name} [{kind}]{dry_note(mode, step)}")
        say(f"      {step.about}")
        say(f"      {display(step.command)}")
        say(f"      writes: {', '.join(step.writes) or 'nothing'}")
    if mode == VERIFY:
        say(f"then: the comparison with {RECORD.as_posix()}, and its result added to it")
    else:
        say(f"then: the Gate 1 record, {RECORD.as_posix()} and {RECORD_MD.as_posix()}")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m analysis.coling.freeze", description=(__doc__ or "").splitlines()[0]
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--open-only", action="store_true", help="the rehearsal: no sealed step")
    mode.add_argument(
        "--write-sealed-once",
        action="store_true",
        help="the freeze run: the sealed build and the counts-only code, each run once",
    )
    mode.add_argument(
        "--continue-after-sealed",
        action="store_true",
        help="go on from a freeze run whose sealed build finished; the corpus is not built",
    )
    mode.add_argument(
        "--verify-rerun",
        action="store_true",
        help="the one rerun of the builder that checks the sealed hashes of the record",
    )
    ap.add_argument(
        COUNTS_AGAIN,
        action="store_true",
        help="with --continue-after-sealed, by the owner's decision: run the counts-only code "
        "again after it stopped half way",
    )
    ap.add_argument("--dry-run", action="store_true", help="print the steps; run nothing")
    ap.add_argument("--plan", type=Path, default=PLAN, help="the plan (its section 17)")
    ap.add_argument(
        "--cutoff",
        default=CUTOFF,
        help="a day of the primary model's documented training-cutoff month (Gate 1)",
    )
    return ap


def take_lock(flag: str) -> bool:
    """Create the lock file of a run; False when one is already there. The file is made, never
    written over, so of two runs started together one is refused."""
    readable(RUN_LOCK).parent.mkdir(parents=True, exist_ok=True)
    try:
        with RUN_LOCK.open("x", encoding="utf-8") as handle:
            handle.write(f"{flag}, process {os.getpid()}\n")
    except FileExistsError:
        return False
    return True


def main(
    argv: Sequence[str] | None = None,
    rt: Runtime | None = None,
    steps_of: Callable[[str, str], Sequence[Step]] = steps,
) -> int:
    ap = parser()
    args = ap.parse_args(None if argv is None else list(argv))
    try:
        args.cutoff = date.fromisoformat(args.cutoff).isoformat()
    except ValueError:
        ap.error("--cutoff takes a date (YYYY-MM-DD)")
    if not readable(args.plan).is_file():
        ap.error(f"no plan at {args.plan.as_posix()}")
    chosen = [
        mode for mode, flag in MODE_FLAGS.items() if getattr(args, flag[2:].replace("-", "_"))
    ]
    if args.counts_again and chosen != [CONTINUE]:
        ap.error(f"{COUNTS_AGAIN} goes with {MODE_FLAGS[CONTINUE]}")
    if args.dry_run:
        return dry_run(chosen[0] if chosen else FREEZE, args, steps_of)
    if not chosen:
        ap.error(f"name a mode: --dry-run, {', '.join(MODE_FLAGS.values())}")
    if not take_lock(MODE_FLAGS[chosen[0]]):
        say(
            f"refused: {RUN_LOCK.as_posix()} is there: another run is under way in this folder. "
            "If that run was killed, read the record first, then remove the file by hand"
        )
        return 1
    try:
        if chosen[0] == VERIFY:
            return verify_rerun(rt or Runtime(), steps_of)
        return run_mode(chosen[0], args, rt or Runtime(), steps_of)
    finally:
        RUN_LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
