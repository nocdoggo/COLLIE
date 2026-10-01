"""Sealed counts: the registered counts over the sealed test-period outcomes, and nothing else.

This is the counts-only code of PLAN.md (standing rules on sealing; sections 3, 6 and 12): the
one script that reads ``external_data/sealed/outcomes_test.csv.gz`` before the registered
evaluator runs. It is run once, at the corpus freeze, after the corpus builder has written the
sealed file and the dataset builder has written the eligible list.

Definitions. Nothing about a statement is defined here. The first-sight table (display row,
split, frozen rule reading, ``stated_end``, the two horizons, eligibility) is
``dataset.statement_table`` on the open events table; the horizon events, ``scoreable`` and
``observable31`` are ``dataset.attach_outcomes`` on the sealed rows; the counts are
``dataset.scoreable_counts``. The outcome is the primary one: the bracket of the displayed
presentation under definition B.

What is printed, and written to the file that ``--out`` names. Every count is an integer count
of statements or of shortage episodes.

1. On the E3 eligible list (``eligible_e3.csv``; test split): eligible statements and their
   episodes (first-sight counts, which ``dataset_counts.json`` also holds); scoreable statements
   (both horizon events determined) and their episodes; statements with a horizon event left
   undetermined (eligible and not scoreable). PLAN.md sections 3 and 6 (power) take these.
2. For each model whose post-cutoff slice lies inside the test split: the scoreable statements of
   the slice, the eligible statements dated after the last day of the model's training-cutoff
   month (section 3). ``CUTOFF_MONTH_ENDS`` mirrors MODELS.md (sections 1 and 8) and is not an
   argument: a changed cutoff is an edit of this file, which changes its recorded hash. A model
   whose cutoff month is the last month of the test split or later has no slice and is only
   named.
3. The sha256 of the sealed file, of the eligible list, of the events table and of the capture
   manifest, and of the code that sets the definitions.

``--gate-observable`` adds two counts, the second and the fourth threshold of Gate 1 on the
eligible list (section 12, the second part of the gate record): the eligible statements whose
displayed presentation has an observable outcome (bracket of 31 days or less), and those of
them dated after the cutoff month of ``GATE_MODEL``. An observable outcome is a recovery or a
discontinuation, so these two counts follow a class of outcome: they are off unless asked for.
The first and the third threshold on the eligible list are the eligible statements and their
episodes of item 1. The four counts on the builder's own gate set are printed by the freeze run
of the corpus builder, not here.

What is never printed or written: an outcome value, a date, a bracket, a rate, a mean or a share;
a count broken down by form, company, drug, year, month or outcome; a row or an id; the text of
an error raised while the sealed rows are in memory. Before anything is printed,
``check_record`` and ``check_text`` stop the run if the output holds anything else. Only ``main``
is for use from outside: the functions with a leading underscore hold sealed rows or counts
before masking.

Small counts. A count below ``MASK_BELOW`` is printed as ``<5``, and the run goes on. Nor can a
count below 5 be had by subtraction, from the counts printed and the first-sight counts of
``dataset_counts.json`` (the eligible statements of the list and of each slice, and the eligible
episodes), which are open.

* A count printed beside its total (scoreable and undetermined in the eligible statements;
  scoreable episodes in the eligible episodes; observable in the eligible statements) is exact
  only when it and the rest of the total are both 5 or more. Otherwise the small side is ``<5``
  and the other side a bound (``>N``, more than N, with N the total minus 5). When the total is
  5 to 9 both sides are ``withheld``.
* The list and the slices are nested, so two exact counts give the count between two cutoffs.
  The slices are therefore printed in two steps, those of the primary models and then those of
  the secondary ones. A step is exact only when every count that subtraction would give, among
  its slices and with the counts already printed, is 5 or more on both sides (scoreable and
  undetermined). Otherwise every slice of that step and of the next is printed as what the
  exact counts already imply: a bound (``>N``), ``<5``, or ``withheld`` when they imply nothing
  of use. The two observable counts are nested in the same way.
* Scoreable statements, scoreable episodes and observable statements are masked apart. The
  links between them are inequalities (no more scoreable episodes than scoreable statements; an
  episode with no scoreable statement holds an undetermined one), which could fix a small count
  only on a list of a few statements.

Refusals. The script stops with status 1 and prints only the reason, on the error stream, when:
an argument is unknown (it takes no breakdown and no cutoff) or malformed; ``--expect-sha256`` or
``--expect-eligible-sha256`` is missing, empty, or not the hash of the file read (the full sha256
or its first 16 or more characters), so that it runs only on the frozen build; ``--out`` is
missing, exists already (the script runs once and overwrites nothing), lies in a sealed folder,
or names a folder that does not exist; an open input lies in a sealed folder; a file cannot be
read; the eligible list is not the one the dataset builder gives for the events table; the sealed
rows are not those of that events table; or the dataset builder's rules stop on a sealed row (the
message is withheld, since it may quote a sealed value). The sealed file is opened last, after
every check that does not need it, and is parsed only when its hash is the expected one. A
refused run writes nothing.

The Late split (statements dated 2026 or later) is in the sealed file and is dropped as soon as
the file is parsed: nothing is counted from it.

Usage (from the repository root), once, at the freeze::

    PYTHONPATH=. python -m analysis.coling.sealed_counts \\
        --expect-sha256 <sha256 of outcomes_test.csv.gz, as the freeze run printed it> \\
        --expect-eligible-sha256 <sha256 of analysis/coling/out/eligible_e3.csv> \\
        --out analysis/coling/out/sealed_counts.json

The default inputs are the sealed file, ``analysis/coling/out/events.csv.gz``,
``eligible_e3.csv`` and ``capture_manifest.csv``. There is no default output: the only file
written is the one ``--out`` names, and its folder is not created. The tests build synthetic
files in a temporary folder and pass their paths.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import warnings
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, NoReturn

import pandas as pd

from analysis.coling import corpus, dataset, forms, rules

SEALED = Path("external_data/sealed/outcomes_test.csv.gz")
SEALED_FOLDER = SEALED.parent.name
EVENTS = dataset.EVENTS
ELIGIBLE = dataset.ELIGIBLE
MANIFEST = dataset.MANIFEST
ABOUT = (
    "Counts over the sealed test-period outcomes, as PLAN.md registers them (splits, power, "
    "Gate 1): statements and shortage episodes only, on the displayed presentation under "
    f"definition {dataset.DEFINITION}."
)
COMMAND = (
    "PYTHONPATH=. python -m analysis.coling.sealed_counts --expect-sha256 <sealed file> "
    "--expect-eligible-sha256 <eligible list> --out <counts file>"
)
OBSERVABLE_FLAG = "--gate-observable"
MASK_BELOW = 5
"""A count below this number is printed as ``<5``. It is not an argument."""
WITHHELD = "withheld"
"""Printed in place of a count that could give away a count below ``MASK_BELOW``."""
MIN_HASH_CHARS = 16
GATE_MODEL = "llama-3.3-70b"
"""The primary model with a documented cutoff: Gate 1's fourth threshold is on its cutoff."""
PRIMARY = ("llama-3.3-70b", "deepseek-v3")
"""The primary models: their slices are printed first (see "Small counts")."""
CUTOFF_MONTH_ENDS: dict[str, date] = {
    "llama-3.3-70b": date(2023, 12, 31),
    "deepseek-v3": date(2024, 12, 31),
    "qwen-2.5-7b": date(2024, 9, 30),
    "gemma-3-27b": date(2024, 8, 31),
    "gpt-oss-20b": date(2024, 6, 30),
    "gpt-4o-mini": date(2023, 10, 31),
    "gemini-3.8-flash": date(2026, 3, 31),
    "grok-4.20": date(2026, 3, 31),
}
"""The last day of each model's training-cutoff month (documented, or bounded by the release
month), as MODELS.md gives it: a model's slice starts after this day."""
FLAGS = ("True", "False")
CODE = {"sealed_counts.py": __file__}
CODE.update({f"{m.__name__.rsplit('.', 1)[-1]}.py": m.__file__ for m in (dataset, corpus, forms)})
CODE["rules.py"] = rules.__file__

_MASKED = re.compile(rf"<{MASK_BELOW}|>\d+|{WITHHELD}")
_HASH = re.compile(r"[0-9a-f]{64}")
_DATE_LIKE = re.compile(
    r"\d{4}-\d{1,2}(?:-\d{1,2})?(?!\d)|(?<!\d)\d{1,2}/\d{1,2}(?:/\d{2,4})?(?!\d)"
)
_FLOAT_LIKE = re.compile(r"\d[.,]\d")


def refuse(reason: str) -> NoReturn:
    """Stop with status 1; the reason is the only thing printed (on the error stream). It is
    never called while an error is being handled, so that no refusal carries another error, and
    with it a message that may quote a cell, as its context."""
    raise SystemExit(f"refused: {reason}")


class Parser(argparse.ArgumentParser):
    """An argument parser that prints the reason alone, without the usage text."""

    def error(self, message: str) -> NoReturn:
        raise SystemExit(f"refused: {message}") from None


# --------------------------------------------------------------------------------------------
# Hashes, files and cutoffs
# --------------------------------------------------------------------------------------------


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_hash(text: str | None, flag: str) -> str:
    """An expected sha256 as given on the command line: 16 to 64 hex characters, lower case."""
    value = (text or "").strip().lower()
    if not re.fullmatch(rf"[0-9a-f]{{{MIN_HASH_CHARS},64}}", value):
        refuse(f"{flag} takes a sha256 or its first {MIN_HASH_CHARS} or more hex characters")
    return value


def require_hash(data: bytes, expected: str, what: str) -> str:
    """The sha256 of ``data``; refused unless it starts with ``expected``."""
    actual = sha256(data)
    if len(expected) < MIN_HASH_CHARS or not actual.startswith(expected):
        refuse(
            f"{what} is not the expected file: its sha256 starts with {actual[:MIN_HASH_CHARS]}, "
            f"expected {expected[:MIN_HASH_CHARS]}"
        )
    return actual


def file_bytes(path: Path, what: str) -> bytes:
    """The bytes of a file, read once; a file that cannot be read is a refusal."""
    try:
        return path.read_bytes()
    except OSError as error:
        stopped = type(error).__name__
    refuse(f"{what} cannot be read ({stopped}): {path.as_posix()}")


def in_sealed_folder(path: Path) -> bool:
    """Whether a path lies in a folder named as the sealed one, as given or once resolved."""
    return SEALED_FOLDER in path.parts or SEALED_FOLDER in path.resolve().parts


def open_input(path: Path, sealed: Path, what: str) -> Path:
    """The path of an open input. Refused when it lies in a sealed folder or is the sealed file:
    a sealed file is read only as ``--sealed``, behind its hash."""
    if in_sealed_folder(path) or path.resolve() == sealed.resolve():
        refuse(f"{what} would be read from a sealed folder; only --sealed names a sealed file")
    return path


def output_path(path: Path | None) -> Path:
    """The counts file that ``--out`` names. Refused when it is not given, lies in a sealed
    folder, exists already, or its folder does not exist: the run writes this one file, creates
    no folder and overwrites nothing."""
    if path is None or not path.name:
        refuse("--out is required: the counts file to write, which must not exist yet")
    if in_sealed_folder(path):
        refuse("--out lies in a sealed folder; the counts file is written outside it")
    if path.exists() or path.is_symlink():
        refuse(f"the counts file is already there, and this script runs once: {path.as_posix()}")
    if not path.parent.is_dir():
        refuse(f"the folder of the counts file does not exist: {path.parent.as_posix()}")
    return path


def _table_of(data: bytes, gzipped: bool) -> pd.DataFrame:
    """A CSV held in memory, every cell as text."""
    return pd.read_csv(
        io.BytesIO(data), dtype=str, keep_default_na=False, compression="gzip" if gzipped else None
    )


def has_slice(cutoff: date) -> bool:
    """Whether a slice that starts after ``cutoff`` lies inside the test split: the cutoff month
    ends before the last day of the split (PLAN.md section 3)."""
    return cutoff + timedelta(days=1) < forms.LATE_START


# --------------------------------------------------------------------------------------------
# Open inputs: the first-sight table and the eligible list
# --------------------------------------------------------------------------------------------


def listed_statements(table: pd.DataFrame, eligible: pd.DataFrame) -> pd.DataFrame:
    """The rows of the first-sight table that the eligible list names, sorted by id. Refused
    unless the list is the one ``dataset.py`` gives for this table: the same statements, with
    the same display row, episode, date, form and stated end."""
    base = list(dataset.ELIGIBLE_BASE)
    missing = [c for c in base if c not in eligible.columns]
    if missing:
        refuse(f"the eligible list lacks {missing}")
    own = table[dataset.true(table["e3_eligible"])].sort_values("statement_group_id")
    theirs = eligible.sort_values("statement_group_id")
    if own[base].values.tolist() != theirs[base].values.tolist():
        refuse(
            "the eligible list is not the one the dataset builder gives for this events table "
            f"({len(theirs)} listed, {len(own)} eligible); rerun the dataset builder"
        )
    if not ((own["split"] == "test") & (own["analysis_set"] == "dated")).all():
        refuse("the eligible list holds a statement outside the test split or not dated")
    return own.reset_index(drop=True)


# --------------------------------------------------------------------------------------------
# Sealed rows: checks and counts
# --------------------------------------------------------------------------------------------


def flag(column: pd.Series) -> pd.Series:
    """A text column of True and False as booleans; any other cell stops the run."""
    if not column.isin(FLAGS).all():
        raise ValueError(f"{column.name} is not a column of True and False")
    return column == "True"


def _checked_rows(outcomes: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """The sealed rows of the test split. Refused unless the file is the test-period outcome
    table of this events table: its columns, test-period rows only, one row per shortage event
    of the period. Rows of the Late split are dropped here and never counted."""
    missing = [c for c in dataset.OUTCOME_FIELDS if c not in outcomes.columns]
    if missing:
        refuse(f"the sealed file lacks {missing}")
    if (outcomes["period"] != "test").any() or outcomes["event_id"].duplicated().any():
        refuse("the sealed file is not the table of test-period outcomes")
    shortage = (events["listing"] == "shortage") & (events["period"] == "test")
    if set(events.loc[shortage, "event_id"]) != set(outcomes["event_id"]):
        refuse("the sealed file and the events table are not from the same build")
    late = outcomes["event_date"] >= forms.LATE_START.isoformat()
    return outcomes[~late].reset_index(drop=True)


def _same_build(listed: pd.DataFrame, outcomes: pd.DataFrame) -> None:
    """Refuse unless every listed statement has the outcome row of its display row."""
    rows = outcomes.set_index("event_id").reindex(listed["event_id"])
    same = (rows["statement_group_id"].to_numpy() == listed["statement_group_id"].to_numpy()) & (
        rows["event_date"].to_numpy() == listed["event_date"].to_numpy()
    )
    if not same.all():
        refuse(
            f"{int((~same).sum())} eligible statements have no outcome row of their display row; "
            "the sealed file and the events table are not from the same build"
        )


def _sealed_counts(
    listed: pd.DataFrame,
    outcomes: pd.DataFrame,
    cutoffs: Mapping[str, date],
    with_observable: bool = False,
) -> dict[str, Any]:
    """Every count as an integer, before masking. ``listed`` is the eligible rows of the
    first-sight table and ``outcomes`` the sealed rows of the test split. The table with the
    outcomes attached lives only inside this function. ``slices`` holds the counts of
    ``dataset.scoreable_counts`` for each model with a slice; ``observable``, only when asked
    for, holds ``(eligible, observable)`` on the list and after the cutoff of ``GATE_MODEL``."""
    _same_build(listed, outcomes)
    filled = dataset.attach_outcomes(listed, outcomes)
    if not filled["scoreable"].isin(FLAGS).all():
        raise ValueError("an eligible statement has no horizon event")
    after = {
        model: filled["event_date"] > day.isoformat()
        for model, day in cutoffs.items()
        if has_slice(day)
    }
    raw: dict[str, Any] = {
        "e3": dataset.scoreable_counts(filled),
        "slices": {model: dataset.scoreable_counts(filled[rows]) for model, rows in after.items()},
    }
    if with_observable:
        observable = flag(filled["observable31"])
        rows = after[GATE_MODEL]
        raw["observable"] = {
            "all": (len(filled), int(observable.sum())),
            "after_cutoff": (int(rows.sum()), int((observable & rows).sum())),
        }
    return raw


# --------------------------------------------------------------------------------------------
# Masking, the record and its checks
# --------------------------------------------------------------------------------------------


def shown(n: int) -> int | str:
    """A count as printed: the integer, or ``<5`` when it is below the mask."""
    return int(n) if n >= MASK_BELOW else f"<{MASK_BELOW}"


def shown_pair(total: int, part: int) -> tuple[int | str, int | str]:
    """``part`` and ``total - part`` as printed, for a total that is open. Both are exact only
    when both are at or above the mask. Otherwise the small one is ``<5`` and the other a bound
    (more than ``total - 5``), which says no more than the mask does. A total of 5 to 9 cannot
    be split in that way without narrowing a small count, so both are withheld; below 5 both
    are ``<5``, which the total says already."""
    rest = total - part
    small = f"<{MASK_BELOW}"
    if total < MASK_BELOW:
        return small, small
    if total < 2 * MASK_BELOW:
        return WITHHELD, WITHHELD
    bound = f">{total - MASK_BELOW}"
    if part < MASK_BELOW:
        return small, bound
    if rest < MASK_BELOW:
        return bound, small
    return int(part), int(rest)


def apart(one: tuple[int, int], other: tuple[int, int]) -> bool:
    """Whether two nested sets, each given as ``(total, part)``, can both be printed exactly:
    they are the same set, or the statements in one and not in the other are at least
    ``MASK_BELOW`` inside the part and at least ``MASK_BELOW`` outside it."""
    total, part = abs(one[0] - other[0]), abs(one[1] - other[1])
    return (total, part) == (0, 0) or min(part, total - part) >= MASK_BELOW


def implied(total: int, exact: Sequence[tuple[int, int]], first: int | str) -> str:
    """What the counts already printed say of the part of a nested set of ``total`` statements
    that is not printed itself: ``exact`` are the sets printed exactly, and ``first`` is the
    part of the whole list as printed. Nothing new is said: a bound, ``<5`` or ``withheld``."""
    low = max(p if t <= total else total - (t - p) for t, p in exact)
    high = min(total - (t - p) if t <= total else p for t, p in exact)
    if first == f"<{MASK_BELOW}":
        high = min(high, MASK_BELOW - 1)
    elif isinstance(first, str) and first.startswith(">"):
        low = max(low, total - (MASK_BELOW - 1))
    if high < MASK_BELOW:
        return f"<{MASK_BELOW}"
    return f">{low - 1}" if low >= MASK_BELOW else WITHHELD


def shown_nested(steps: Sequence[Sequence[tuple[int, int]]]) -> list[list[int | str]]:
    """The parts of nested sets as printed, from the ``(total, part)`` of each; the totals are
    open. ``steps[0]`` holds the whole list alone and the later steps its subsets, in the order
    of printing. A step is exact only when every earlier step is and every pair of its sets,
    and of its sets with those already printed and with the empty set, is ``apart``. A step
    that is not exact is printed as ``implied`` (the whole list: as ``shown_pair``), and so is
    every later step, so that an exact count is never printed after a withheld one."""
    first = shown_pair(*steps[0][0])[0]
    exact: list[tuple[int, int]] = [(0, 0)]
    printed: list[list[int | str]] = []
    open_so_far = True
    for index, step in enumerate(steps):
        open_so_far = open_so_far and all(
            apart(one, other) for i, one in enumerate(step) for other in (*exact, *step[:i])
        )
        if open_so_far:
            exact.extend(step)
            printed.append([shown(part) for _, part in step])
        elif index == 0:
            printed.append([first])
        else:
            printed.append([implied(total, exact, first) for total, _ in step])
    return printed


def record_of(
    raw: Mapping[str, Any], inputs: Mapping[str, Any], with_observable: bool = False
) -> dict[str, Any]:
    """The output: masked counts, the hashes, and names. No date and no outcome value."""
    e3, slices = raw["e3"], raw["slices"]
    ranked = [m for m in slices if m in PRIMARY], [m for m in slices if m not in PRIMARY]
    steps = [
        [(slices[m]["statements"], slices[m]["scoreable"]) for m in models] for models in ranked
    ]
    whole, *sizes = shown_nested([[(e3["statements"], e3["scoreable"])], *steps])
    size_of = dict(zip([*ranked[0], *ranked[1]], [*sizes[0], *sizes[1]], strict=True))
    record: dict[str, Any] = {
        "about": ABOUT,
        "command": COMMAND + (f" {OBSERVABLE_FLAG}" if with_observable else ""),
        "inputs": dict(inputs),
        "masked_below": MASK_BELOW,
        "e3_eligible_test": {
            "eligible_statements": shown(e3["statements"]),
            "eligible_episodes": shown(e3["episodes"]),
            "scoreable_statements": whole[0],
            "scoreable_episodes": shown_pair(e3["episodes"], e3["scoreable_episodes"])[0],
            "undetermined_statements": shown_pair(e3["statements"], e3["scoreable"])[1],
        },
        "post_cutoff_slices": {
            "scoreable_statements": {m: size_of[m] for m in slices},
            "models_without_a_slice": [m for m in CUTOFF_MONTH_ENDS if m not in slices],
        },
    }
    if with_observable:
        observable = raw["observable"]
        on_list, after_cutoff = shown_nested([[observable["all"]], [observable["after_cutoff"]]])
        record[OPTIONAL_KEY] = {
            "model": GATE_MODEL,
            "observable_statements": on_list[0],
            "observable_statements_after_cutoff": after_cutoff[0],
        }
    return record


def is_count(value: Any) -> bool:
    """An integer at or above the mask, or a masked count (``<5``, ``>N``, ``withheld``)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= MASK_BELOW
    return isinstance(value, str) and bool(_MASKED.fullmatch(value))


TOP_KEYS = (
    "about",
    "command",
    "inputs",
    "masked_below",
    "e3_eligible_test",
    "post_cutoff_slices",
)
OPTIONAL_KEY = "gate1_on_the_eligible_list"
FILE_INPUTS = ("sealed_outcomes", "eligible_list", "events", "capture_manifest")
SECTION_KEYS = {
    "inputs": (*FILE_INPUTS, "code_sha256"),
    "e3_eligible_test": (
        "eligible_statements",
        "eligible_episodes",
        "scoreable_statements",
        "scoreable_episodes",
        "undetermined_statements",
    ),
    "post_cutoff_slices": ("scoreable_statements", "models_without_a_slice"),
    OPTIONAL_KEY: ("model", "observable_statements", "observable_statements_after_cutoff"),
}
"""The keys of the record, section by section; the last section is there only when asked for."""


def check_record(record: Mapping[str, Any]) -> None:
    """Stop unless the record holds what the docstring lists and nothing else: the keys of
    ``TOP_KEYS`` and ``SECTION_KEYS``, the two fixed texts, counts that are integers or masks,
    the model names of the cutoff table, file names and sha256 values."""
    try:
        asked = OPTIONAL_KEY in record
        keys = tuple(record) == ((*TOP_KEYS, OPTIONAL_KEY) if asked else TOP_KEYS) and all(
            tuple(record[name]) == wanted for name, wanted in SECTION_KEYS.items() if name in record
        )
        e3, slices, inputs = (
            record["e3_eligible_test"],
            record["post_cutoff_slices"],
            record["inputs"],
        )
        gate = dict(record[OPTIONAL_KEY]) if asked else {"model": GATE_MODEL}
        with_slice = [m for m, day in CUTOFF_MONTH_ENDS.items() if has_slice(day)]
        counts = [*e3.values(), *slices["scoreable_statements"].values()]
        counts += [value for key, value in gate.items() if key != "model"]
        hashes = [inputs[name]["sha256"] for name in FILE_INPUTS]
        hashes += inputs["code_sha256"].values()
        ok = (
            keys
            and record["about"] == ABOUT
            and record["command"] == COMMAND + (f" {OBSERVABLE_FLAG}" if asked else "")
            and record["masked_below"] == MASK_BELOW
            and all(tuple(inputs[name]) == ("file", "sha256") for name in FILE_INPUTS)
            and all(isinstance(inputs[name]["file"], str) for name in FILE_INPUTS)
            and tuple(inputs["code_sha256"]) == tuple(CODE)
            and all(isinstance(h, str) and _HASH.fullmatch(h) for h in hashes)
            and list(slices["scoreable_statements"]) == with_slice
            and slices["models_without_a_slice"]
            == [m for m in CUTOFF_MONTH_ENDS if m not in with_slice]
            and gate["model"] == GATE_MODEL
            and all(is_count(v) for v in counts)
        )
    except (KeyError, TypeError, AttributeError):
        ok = False
    if not ok:
        refuse("the output would hold something other than the registered counts")


def check_text(text: str) -> None:
    """Stop if the text to print holds a date-like string or a number with a decimal part, the
    model names set aside (their version numbers have dots)."""
    for name in sorted(CUTOFF_MONTH_ENDS, key=len, reverse=True):
        text = text.replace(name, "")
    if _DATE_LIKE.search(text) or _FLOAT_LIKE.search(text):
        refuse("the output would hold a date or a number that is not a count")


def lines_of(record: Mapping[str, Any]) -> list[str]:
    """The printout: the counts and the hashes of the record."""
    e3, slices, inputs = record["e3_eligible_test"], record["post_cutoff_slices"], record["inputs"]
    lines = [
        "sealed counts: statements and shortage episodes only (displayed presentation, "
        f"definition {dataset.DEFINITION})",
        f"reading a count: <{MASK_BELOW} is fewer than {MASK_BELOW}; >N is more than N; "
        f"{WITHHELD} is a count not printed, because it would give away one below {MASK_BELOW}",
        "E3 eligible list, test split:",
        f"  eligible statements: {e3['eligible_statements']}",
        f"  shortage episodes among the eligible: {e3['eligible_episodes']}",
        f"  scoreable statements: {e3['scoreable_statements']}",
        f"  shortage episodes among the scoreable: {e3['scoreable_episodes']}",
        f"  statements with a horizon event undetermined: {e3['undetermined_statements']}",
        "scoreable statements of each post-cutoff slice:",
        *(f"  {model}: {n}" for model, n in slices["scoreable_statements"].items()),
    ]
    if slices["models_without_a_slice"]:
        lines.append(
            "without a slice inside the test split: " + ", ".join(slices["models_without_a_slice"])
        )
    if OPTIONAL_KEY in record:
        gate = record[OPTIONAL_KEY]
        lines += [
            "Gate 1 on the eligible list, observable statements (bracket of "
            f"{corpus.OBSERVABLE_WIDTH_DAYS} days or less), displayed presentation:",
            f"  second threshold, all eligible statements: {gate['observable_statements']}",
            f"  fourth threshold, dated after the cutoff month of {gate['model']}: "
            f"{gate['observable_statements_after_cutoff']}",
        ]
    lines += [
        f"sha256 of the sealed outcome file: {inputs['sealed_outcomes']['sha256']}",
        f"sha256 of the eligible list: {inputs['eligible_list']['sha256']}",
    ]
    return lines


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = Parser(
        prog="python -m analysis.coling.sealed_counts",
        description=(__doc__ or "").splitlines()[0],
        allow_abbrev=False,
    )
    ap.add_argument("--expect-sha256", help="sha256 of the sealed file (the freeze run prints it)")
    ap.add_argument("--expect-eligible-sha256", help="sha256 of the eligible list")
    ap.add_argument("--out", type=Path, help="the counts file to write; it must not exist yet")
    ap.add_argument("--sealed", type=Path, default=SEALED, help="the sealed test outcomes")
    ap.add_argument("--events", type=Path, default=EVENTS, help="the open events table")
    ap.add_argument("--eligible", type=Path, default=ELIGIBLE, help="the E3 eligible list")
    ap.add_argument("--manifest", type=Path, default=MANIFEST, help="the capture manifest")
    ap.add_argument(
        OBSERVABLE_FLAG,
        action="store_true",
        help="also print Gate 1's second and fourth thresholds on the eligible list",
    )
    args, unknown = ap.parse_known_args(None if argv is None else list(argv))
    if unknown:
        refuse(
            f"unknown argument {unknown[0]!r}: this script prints the registered counts only "
            "and takes no breakdown and no cutoff"
        )
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = arguments(argv)
    want_sealed = expected_hash(args.expect_sha256, "--expect-sha256")
    want_eligible = expected_hash(args.expect_eligible_sha256, "--expect-eligible-sha256")
    if dataset.DEFINITION != corpus.GATE_PRIMARY:
        refuse("the dataset builder and the gate use different recovery definitions")
    out = output_path(args.out)
    for path, what in (
        (args.eligible, "the eligible list"),
        (args.events, "the events table"),
        (args.manifest, "the capture manifest"),
    ):
        open_input(path, args.sealed, what)

    # open inputs first: the sealed file is not opened unless these are in order
    names = [path.name for path in (args.sealed, args.eligible, args.events, args.manifest)]
    check_text(" ".join(names))  # the file names go into the record
    eligible_bytes = file_bytes(args.eligible, "the eligible list")
    eligible_sha = require_hash(eligible_bytes, want_eligible, "the eligible list")
    events_bytes = file_bytes(args.events, "the events table")
    manifest_bytes = file_bytes(args.manifest, "the capture manifest")
    code = {name: sha256(file_bytes(Path(path), name)) for name, path in CODE.items()}
    stopped = ""
    try:
        events = _table_of(events_bytes, args.events.suffix == ".gz")
        days = dataset.capture_days(io.BytesIO(manifest_bytes))  # type: ignore[arg-type]
        table = dataset.statement_table(events, days[-1])
        eligible = _table_of(eligible_bytes, args.eligible.suffix == ".gz")
    except Exception as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"the open inputs are not as the builders write them ({stopped})")
    listed = listed_statements(table, eligible)

    # the sealed file: hashed as bytes, parsed only when the hash is the expected one
    sealed_bytes = file_bytes(args.sealed, "the sealed file")
    sealed_sha = require_hash(sealed_bytes, want_sealed, "the sealed file")
    inputs = {
        "sealed_outcomes": {"file": args.sealed.name, "sha256": sealed_sha},
        "eligible_list": {"file": args.eligible.name, "sha256": eligible_sha},
        "events": {"file": args.events.name, "sha256": sha256(events_bytes)},
        "capture_manifest": {"file": args.manifest.name, "sha256": sha256(manifest_bytes)},
        "code_sha256": code,
    }
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # a warning may quote a cell
            outcomes = _checked_rows(_table_of(sealed_bytes, True), events)
            raw = _sealed_counts(listed, outcomes, CUTOFF_MONTH_ENDS, args.gate_observable)
            record = record_of(raw, inputs, args.gate_observable)
    except Exception as error:
        stopped = type(error).__name__  # the error itself, and its message, go no further
    if stopped:
        refuse(
            f"the rules stopped on the sealed rows ({stopped}); the message is withheld "
            "because it may quote a sealed value"
        )
    del outcomes, raw

    check_record(record)
    lines = lines_of(record)
    text = json.dumps(record, indent=1) + "\n"
    check_text("\n".join(lines))
    check_text(text)
    try:
        with out.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        stopped = type(error).__name__
    if stopped:
        refuse(f"the counts file cannot be written ({stopped}): {out.as_posix()}")
    print("\n".join(lines))
    print(f"wrote {out.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
